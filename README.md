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
python -m probe --category screenshot                                        # or capture and send a screenshot
```

To run the hub as a service under pm2:

```bash
pm2 start ecosystem.config.js   # app name: probehub-hub
pm2 save                        # restore it after reboots (needs `pm2 startup` once)
```

Endpoints:

- `POST /api/v1/data`: takes `{"probe_id": "...", "category": "system", "collected_at": "<ISO-8601>", "data": {...}}`
- `GET /health`: reports whether the hub and its DB are up

## Probe categories

The probe supports multiple data categories via `--category`:

- **`all`** (default): everything in one payload — the `system` metrics at the top level plus a
  `screenshot` key. Nothing to choose; this is what `python -m probe` and the launchd service send.
- **`system`**: OS metrics only — hostname, CPU count, memory, disk, load average, uptime
- **`screenshot`**: Captures every connected display and sends them as an array of base64-encoded PNGs: `{"images": [<main display>, <extra monitor>, ...], "count": N, "format": "png", "timestamp": ...}`. On macOS you get one image per monitor (main first). On Linux the whole desktop comes back as a single stitched image. Returns an error dict on other platforms. Size: roughly 0.3–1.4 MiB of base64 per display.

Examples:

```bash
python -m probe                         # collect everything and send once (category all)
python -m probe --category system       # system metrics only
python -m probe --category screenshot   # capture and send one screenshot
python -m probe --category screenshot --interval 60  # send screenshot every 60 seconds
```

**Note on size limits:** base64 inflates a PNG by ~4/3, so one Retina capture (~850 KiB) arrives as ~1.13 MiB, and every extra monitor adds its own image. That would be rejected with `413` at the 1 MiB code default. `.env.example` therefore sets `HUB_MAX_BODY_BYTES=8388608` (8 MiB); restart the hub after changing it.

## Shipping the probe

Package the probe as a single portable `.pyz` with the hub URL baked in, then install it as a
macOS login service (no pm2 — pm2 stays reserved for the hub):

```bash
python3 probe/build_pyz.py --hub-url <url> -o dist/probe.pyz   # single-file .pyz, no flags needed at runtime
python3 dist/probe.pyz service install|uninstall|status        # registers/removes a launchd LaunchAgent, or reports its status
```

macOS-only for now.

## Public deployment

The hub listens on `127.0.0.1:8100` and is published on a VPS through an autossh reverse tunnel
(`deploy/probehub-tunnel.service.example`). Probes anywhere send to `http://<vps-ip>:8100`:

```bash
PROBEHUB_URL=http://<vps-ip>:8100 python -m probe --interval 60
curl -i http://<vps-ip>:8100/health
```

Auth is optional (`HUB_API_TOKEN`) and currently off; there is no TLS yet. Request bodies are capped
by `HUB_MAX_BODY_BYTES` (10 MiB). Details, setup steps and warnings are in `claude.md` under *Deployment*.

See `claude.md` for the design notes and the task list.
