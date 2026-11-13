# ProbeHub

ProbeHub collects JSON data from client machines and stores it centrally.

- **probe** (client): a small pure-Python collector that runs on client machines,
  gathers data, and sends it to the hub as JSON over HTTP.
- **hub** (backend): a Python API that receives probe data and saves it to PostgreSQL.

```
 client machine                     server (local now, VPS later)
┌──────────────┐  HTTP POST JSON   ┌──────────────┐   SQL    ┌──────────────┐
│    probe     │ ────────────────▶ │     hub      │ ───────▶ │  PostgreSQL  │
│ (stdlib only)│  /api/v1/data     │  (FastAPI)   │  JSONB   │  db probehub │
└──────────────┘                   └──────────────┘          └──────────────┘
```

## Layout

```
probehub/
├── probe/                  # client, stdlib only (no third-party deps)
│   ├── pyproject.toml
│   ├── src/probe/
│   │   ├── collector.py    # one collector per category -> dict
│   │   ├── sender.py       # POSTs the envelope to the hub (urllib)
│   │   └── cli.py          # `python -m probe` entry point
│   └── tests/
├── hub/                    # backend API
│   ├── pyproject.toml
│   ├── src/hub/
│   │   ├── config.py       # settings from env / .env
│   │   ├── db.py           # Postgres store + schema
│   │   ├── schemas.py      # request/response models
│   │   └── main.py         # FastAPI app
│   └── tests/
├── .env.example            # copy to .env (gitignored), holds DB credentials
├── ecosystem.config.js     # pm2 config: runs the hub as `probehub-hub`
├── claude.md
└── README.md
```

## Data contract

`POST /api/v1/data` with this JSON envelope:

```json
{
  "probe_id": "laptop-01",
  "category": "system",
  "collected_at": "2026-11-11T16:45:00Z",
  "data": { "...": "any JSON object" }
}
```

- `probe_id`: string of 1–128 characters. Defaults to the client's hostname.
- `category`: what kind of data this is (e.g. `system`, later `photo`). Required. Lowercase slug,
  1–64 characters, matching `^[a-z0-9][a-z0-9_.-]{0,63}$`. The hub stores it in its own indexed column.
- `collected_at`: ISO-8601 datetime. Include a timezone.
- `data`: any JSON object. The hub doesn't check what's inside it.

The hub replies `201 {"id": <int>, "received_at": "<datetime>"}`.
`GET /health` returns `200` when the DB is reachable and `503` when it isn't.

Storage is a single table, `probe_data`, with columns `id`, `probe_id`, `category`, `collected_at`, `received_at` and
`payload JSONB`. The schema is created on hub startup with `CREATE TABLE IF NOT EXISTS`, plus idempotent
`ALTER TABLE ... ADD COLUMN IF NOT EXISTS` migrations for older tables.

On the probe, each category has a collector function registered in `COLLECTORS` in
`probe/src/probe/collector.py`. Only `system` exists today. To add one (e.g. `photo`), write a
function that returns a dict and register it. Binary data such as images goes in as base64 strings.

## Configuration

The hub reads its settings from environment variables, or from `.env` at the repo root:

| Var            | Default                                       | Notes                               |
|----------------|-----------------------------------------------|-------------------------------------|
| `DATABASE_URL` | `postgresql://biswa@127.0.0.1:5432/probehub`  | DB user `biswa`, password goes in `.env` |
| `HUB_HOST`     | `127.0.0.1`                                   | change to `0.0.0.0` when exposing on the VPS |
| `HUB_PORT`     | `8000`                                        |                                     |

The probe takes CLI flags, or env vars as a fallback: `--hub-url` / `PROBEHUB_URL`
(default `http://127.0.0.1:8000`), `--probe-id` / `PROBE_ID`, `--category` (default `system`), `--interval` (seconds; 0 = send once),
and `--dry-run` (print the envelope instead of sending it).

## Commands

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -e "hub[dev]" -e probe        # dev setup (both packages + pytest)
cp .env.example .env                       # then set the real DB password

python -m hub                              # run hub in the foreground (dev)
pm2 start ecosystem.config.js              # run hub as a service (probehub-hub)
pm2 logs probehub-hub                      # hub logs; restart after code/.env changes
python -m probe                            # collect + send once
python -m probe --interval 60              # send every 60 s
python -m probe --dry-run                  # print the JSON envelope, don't send

python -m pytest hub/tests probe/tests     # run tests
```

## Conventions

- The probe must stay **stdlib-only** so it can be copied onto any machine that has Python 3.10+
  without needing pip.
- The hub API runs as a service under **pm2** (`probehub-hub`). Don't use nohup or ad-hoc background runs.
- Never commit secrets. `.env` is gitignored; only `.env.example` gets committed.
- Don't hardcode hosts or URLs. Everything that changes between local and the VPS goes in config.
- Development is task-based. Work through the task list below and update each task's status as you go.

## Design analysis (Socratic)

The questions below were asked of the original instruction before development started.

1. **What is being asked?** A client (probe) sends JSON to a backend (hub), and the hub stores it in a DB.
   It runs locally for now. Later the hub moves behind a VPS port so remote clients can reach it.
2. **What exactly does the probe collect?** *Not specified.* → Assumption: basic host metrics
   (hostname, OS, CPU count, load, memory, disk, uptime). The hub accepts any JSON object as `data`,
   so the collected data can change without changing the hub.
3. **What does "pure Python" mean for the probe?** → Assumption: standard library only, with zero pip deps.
4. **How should JSON be stored?** → In a PostgreSQL `JSONB` column. `probe_id` and the timestamps are
   kept in their own columns so data can be filtered by client or time.
5. **Which DB, and where is "external sss"?** *Unclear* (external SSD? external server?). → For now
   it's the local PostgreSQL 18 on `127.0.0.1:5432`, database `probehub`, user `biswa`. The location is
   only set by `DATABASE_URL`, so moving the DB later is a config change. **Open question.**
6. **Do the credentials `biswa` / `biswa` work?** The role `biswa` already existed, and the password
   `biswa` was rejected. **Open question:** use the real password, or reset it.
7. **What changes when the hub moves to the VPS?** The host and port (config only). An endpoint open to the
   internet also needs authentication, TLS, and request-size and rate limits. That's Phase 2. **Don't expose
   the hub to the internet until the auth task is done.**
8. **What if the hub is unreachable?** For now the probe logs the error and tries again on the next
   interval. Data from a failed send is lost; local buffering is a Phase 2 task.
9. **How do we know it works?** Unit tests for both sides, plus a local end-to-end run that
   goes probe → hub → row in `probe_data`.

## Tasks

Phase 1: local

- [x] T1 Write claude.md (project overview, Socratic analysis, task list)
- [x] T2 Repo scaffolding: `.gitignore`, `.env.example`, README, pyproject files
- [x] T3 Database: create the `probehub` DB owned by `biswa`, plus the `probe_data` table
- [x] T4 Hub: `POST /api/v1/data`, `GET /health`, settings from env
- [x] T5 Probe: collector, sender, CLI (once / interval / dry-run)
- [x] T6 Tests for the hub and the probe
- [x] T7 Local end-to-end run: probe → hub → DB (verified over the Unix socket; the `biswa` password in `.env` is still wrong, see Q6)

Phase 2: VPS / remote clients

- [ ] T8 Auth: per-probe or shared API token (`Authorization: Bearer ...`)
- [ ] T9 Expose on the VPS: bind/port mapping, reverse proxy with TLS (e.g. nginx or Caddy)
- [ ] T10 Request size limit and rate limiting
- [ ] T11 Probe offline buffering, so data is resent after the hub comes back
- [x] T12a Hub runs as a pm2 service (`ecosystem.config.js`)
- [ ] T12b Run the probe as a service on client machines (systemd or pm2)
- [x] T14 `category` key in the envelope + per-category collectors on the probe
- [ ] T15 Photo category (base64). Needs a request-size limit on the hub (T10) and probably
  storing images outside JSONB (file/object storage) once volume grows
- [ ] T13 Read API for the stored data (filter by probe and time range)
