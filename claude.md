# ProbeHub

ProbeHub collects JSON data from client machines and stores it centrally.

- **probe** (client): a small pure-Python collector that runs on client machines,
  gathers data, and sends it to the hub as JSON over HTTP.
- **hub** (backend): a Python API that receives probe data and saves it to PostgreSQL.

```
 client machine                 VPS (public)              this machine (hub host)
┌──────────────┐  HTTP POST   ┌──────────────┐  autossh   ┌──────────────┐  SQL   ┌────────────┐
│    probe     │ ───────────▶ │ <vps-ip>:8100│ ◀───────── │     hub      │ ─────▶ │ PostgreSQL │
│ (stdlib only)│  /api/v1/data│ (sshd -R)    │  reverse   │ 127.0.0.1:8100│ JSONB │ db probehub│
└──────────────┘              └──────────────┘  tunnel    └──────────────┘        └────────────┘
```

The hub only listens on `127.0.0.1:8100`. It is published on the VPS by a reverse SSH tunnel
(`-R 8100:localhost:8100`), kept alive by autossh under systemd. See **Deployment** below.

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
│   │   ├── guard.py        # ASGI middleware: optional bearer token + body-size limit
│   │   └── main.py         # FastAPI app
│   └── tests/
├── deploy/                 # example systemd unit for the VPS tunnel
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

## Deployment (hub published on the VPS)

Status: **live** at `http://<vps-ip>:8100` (plain HTTP, **no auth**, by decision; see warnings below).

| Piece | How it runs | Survives reboot via |
|-------|-------------|---------------------|
| Hub | pm2 app `probehub-hub` on `127.0.0.1:8100` | `pm2 save` + `pm2-<user>` systemd unit |
| Tunnel | `probehub-tunnel.service` (autossh, `-R 8100:localhost:8100`, `Restart=always`) | `systemctl enable` |
| PostgreSQL | local, `127.0.0.1:5432` only | `postgresql.service` |

Setup, once:

1. **VPS:** sshd needs `GatewayPorts yes` (or `clientspecified`). Open the port: `sudo ufw allow 8100/tcp`
   (and in the provider's web firewall if there is one). Port 8000 stays reserved for the primebuild
   nginx `/api/` route, and the VPS ports 80, 443, 9090-9092 and 11436 are already in use.
2. **Hub host:** put `HUB_PORT=8100` in `.env`; `pm2 start ecosystem.config.js && pm2 save`.
3. **Tunnel:** install `deploy/probehub-tunnel.service.example` as `/etc/systemd/system/probehub-tunnel.service`
   (set `<vps-ip>`), then `sudo systemctl enable --now probehub-tunnel`.
4. **Probes:** `PROBEHUB_URL=http://<vps-ip>:8100 python -m probe --interval 60`.

Quick checks:

```bash
curl -i http://<vps-ip>:8100/health            # 200 {"status":"ok","db":"ok"}
systemctl is-active probehub-tunnel            # active
journalctl -u probehub-tunnel -b --no-pager | tail
```

Emergency stop (closes the public port instantly): on the VPS `sudo ufw delete allow 8100/tcp`,
or on the hub host `sudo systemctl stop probehub-tunnel`.

**Warnings**

- The endpoint is **open to the internet with no authentication**, and traffic is **unencrypted HTTP**.
  Anyone who finds the address can insert rows. Don't send sensitive data or photos until
  `HUB_API_TOKEN` is set (T8) and TLS is in place (T9b).
- DB access: the hub connects over the local Unix socket as the OS user
  (`DATABASE_URL=postgresql:///probehub?host=/var/run/postgresql` in `.env`), so no DB password is needed.
  The `biswa` role also has a password for TCP clients (DBeaver, psql); it lives outside the repo.
- Real values (VPS IP, DB password, tokens) are never committed. The repo is public.

## Configuration

The hub reads its settings from environment variables, or from `.env` at the repo root:

| Var            | Default                                       | Notes                               |
|----------------|-----------------------------------------------|-------------------------------------|
| `DATABASE_URL` | `postgresql://biswa@127.0.0.1:5432/probehub`  | code default. In `.env` use `postgresql:///probehub?host=/var/run/postgresql` (socket, no password) or `postgresql://biswa:<pw>@127.0.0.1:5432/probehub` (URL-encode special chars, e.g. `@` -> `%40`) |
| `HUB_HOST`     | `127.0.0.1`                                   | keep `127.0.0.1`: the VPS tunnel reaches it locally, so nothing else needs to bind publicly |
| `HUB_PORT`     | `8100`                                        | 8000 is reserved for primebuild's nginx `/api/` |
| `HUB_API_TOKEN` | *(empty)*                                    | empty = open endpoint, no auth (current choice). If set, probes must send `Authorization: Bearer <token>` |
| `HUB_MAX_BODY_BYTES` | `1048576`                               | requests over this get `413`; raise it for photos |

The probe takes CLI flags, or env vars as a fallback: `--hub-url` / `PROBEHUB_URL`
(default `http://127.0.0.1:8100`), `--probe-id` / `PROBE_ID`, `--token` / `PROBEHUB_TOKEN` (prefer the env var), `--category` (default `system`), `--interval` (seconds; 0 = send once),
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
5. **Which DB, and where is "external sss"?** *Unclear* (external SSD? external server?). → It is
   the local PostgreSQL 18 on `127.0.0.1:5432`, database `probehub`, user `biswa`. The location is
   only set by `DATABASE_URL`, so moving the DB later is a config change. **Resolved:** local DB.
6. **Do the credentials `biswa` / `biswa` work?** No: the role existed with a different password.
   **Resolved:** the hub uses the Unix socket (no password), and `biswa` got a new password for TCP clients.
7. **What changes when the hub moves to the VPS?** Config plus a reverse tunnel. An endpoint open to the
   internet also needs authentication, TLS, and request-size and rate limits. **Update:** the hub is now public
   with auth deliberately switched off (T8 is built but unset) and no TLS or rate limit yet; see Deployment warnings.
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
- [x] T7 Local end-to-end run: probe → hub → DB (verified over the Unix socket)

Phase 2: VPS / remote clients

- [x] T8 Auth: optional shared API token on `/api/*` (`hub/guard.py`). **Currently disabled on purpose**
  (no token in `.env`, endpoint is open). Set `HUB_API_TOKEN` to turn it on before real/sensitive data
- [x] T9a Expose on the VPS as `http://<vps-ip>:8100` via an autossh systemd unit (`probehub-tunnel.service`,
  `-R 8100:localhost:8100`); VPS firewall port 8100 opened. Live, plain HTTP
- [ ] T9b TLS. The VPS's 80 and 443 are taken (80 = existing web tunnel, 443 = sshd), so this needs
  another port, a different front (e.g. Cloudflare) or a DNS-validated cert
- [ ] T9c Full reboot test (both hub host and tunnel should come back on their own)
- [x] T10a Request size limit (`HUB_MAX_BODY_BYTES`, 413)
- [ ] T10b Rate limiting
- [ ] T11 Probe offline buffering, so data is resent after the hub comes back
- [x] T12a Hub runs as a pm2 service (`ecosystem.config.js`)
- [ ] T12b Run the probe as a service on client machines (systemd or pm2)
- [x] T14 `category` key in the envelope + per-category collectors on the probe
- [ ] T15 Photo category (base64). Needs a request-size limit on the hub (T10) and probably
  storing images outside JSONB (file/object storage) once volume grows
- [ ] T13 Read API for the stored data (filter by probe and time range)
