# ProbeHub

Probes running on client machines collect data and send it as JSON to a central hub.
The hub stores the data in PostgreSQL.

- `probe/`: the client, pure Python (standard library only)
- `hub/`: the backend API (FastAPI + PostgreSQL)

## Quick start (local)

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -e "hub[dev]" -e probe
cp .env.example .env          # set the DB password and HUB_API_TOKEN

python -m hub                 # hub on http://127.0.0.1:8100
PROBEHUB_URL=http://127.0.0.1:8100 PROBEHUB_TOKEN=<token> python -m probe   # in another shell: collect and send once
```

To run the hub as a service under pm2:

```bash
pm2 start ecosystem.config.js   # app name: probehub-hub
pm2 save                        # restore it after reboots (needs `pm2 startup` once)
```

Endpoints:

- `POST /api/v1/data`: takes `{"probe_id": "...", "category": "system", "collected_at": "<ISO-8601>", "data": {...}}`
- `GET /health`: reports whether the hub and its DB are up

## Public deployment

The hub listens on `127.0.0.1:8100` and is published on a VPS through an autossh reverse tunnel
(`deploy/probehub-tunnel.service.example`). Probes anywhere send to `http://<vps-ip>:8100`:

```bash
PROBEHUB_URL=http://<vps-ip>:8100 python -m probe --interval 60
curl -i http://<vps-ip>:8100/health
```

Auth is optional (`HUB_API_TOKEN`) and currently off; there is no TLS yet. Request bodies are capped
by `HUB_MAX_BODY_BYTES` (1 MiB). Details, setup steps and warnings are in `claude.md` under *Deployment*.

See `claude.md` for the design notes and the task list.
