# Graph Report - probehub  (2026-11-13)

## Corpus Check
- Corpus is ~4,307 words - fits in a single context window. You may not need a graph.

## Summary
- 173 nodes · 254 edges · 14 communities (8 shown, 6 thin omitted)
- Extraction: 96% EXTRACTED · 4% INFERRED · 0% AMBIGUOUS · INFERRED: 9 edges (avg confidence: 0.89)
- Token cost: 65,257 input · 0 output

## Community Hubs (Navigation)
- Hub Database Layer
- Hub API Tests
- Probe Collector & Tests
- Probe CLI & Sender
- Deployment & Roadmap
- Data Contract & Config
- Hub Settings
- Auth & Request Guard
- API Endpoints & Service
- Ecosystem Config Fragment
- Hub Service Name
- Probe Service Name

## God Nodes (most connected - your core abstractions)
1. `hub (backend)` - 15 edges
2. `create_app()` - 11 edges
3. `Tasks list (Phase 1 / Phase 2)` - 10 edges
4. `PostgresStore` - 9 edges
5. `send()` - 9 edges
6. `build_envelope()` - 8 edges
7. `run_once()` - 7 edges
8. `collect()` - 7 edges
9. `hub (backend)` - 7 edges
10. `Public deployment (VPS tunnel)` - 7 edges

## Surprising Connections (you probably didn't know these)
- `tracking_send()` --indirect_call--> `send()`  [INFERRED]
  hub/src/hub/guard.py → probe/src/probe/sender.py
- `create_app()` --uses--> `Guard`  [INFERRED]
  hub/src/hub/main.py → hub/src/hub/guard.py
- `main()` --calls--> `load_settings()`  [EXTRACTED]
  hub/src/hub/__main__.py → hub/src/hub/config.py
- `create_app()` --calls--> `load_settings()`  [EXTRACTED]
  hub/src/hub/main.py → hub/src/hub/config.py
- `lifespan()` --calls--> `load_settings()`  [EXTRACTED]
  hub/src/hub/main.py → hub/src/hub/config.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Probe-to-hub-to-PostgreSQL data flow** — claude_probe, claude_hub, claude_postgresql, claude_probe_data_table, claude_data_contract [EXTRACTED 1.00]
- **VPS public exposure via reverse tunnel and pm2** — claude_hub, claude_vps, claude_autossh_reverse_tunnel, claude_probehub_tunnel_service, claude_ecosystem_config_js [EXTRACTED 1.00]
- **Security hardening roadmap (auth, TLS, rate limit, body-size cap)** — claude_hub_api_token, claude_tls_plan, claude_rate_limiting_plan, claude_hub_max_body_bytes [INFERRED 0.85]

## Communities (14 total, 6 thin omitted)

### Community 0 - "Hub Database Layer"
Cohesion: 0.10
Nodes (7): probe_data table, PostgresStore, create_app(), ingest(), lifespan(), IngestResult, ProbeEnvelope

### Community 1 - "Hub API Tests"
Cohesion: 0.10
Nodes (9): anon(), client(), FakeStore, store(), test_health_db_down(), test_ingest_rejects_invalid(), test_ingest_rejects_missing_field(), test_ingest_requires_valid_token() (+1 more)

### Community 2 - "Probe Collector & Tests"
Cohesion: 0.10
Nodes (8): collect(), collect_system(), _meminfo(), _uptime_seconds(), fake_hub(), test_collect_is_json_serialisable(), test_collect_unknown_category_raises(), test_every_collector_is_json_serialisable_and_named_validly()

### Community 3 - "Probe CLI & Sender"
Cohesion: 0.14
Nodes (10): main(), parse_args(), run_once(), build_envelope(), send(), SendError, test_build_envelope_has_aware_timestamp(), test_send_includes_bearer_token() (+2 more)

### Community 4 - "Deployment & Roadmap"
Cohesion: 0.12
Nodes (16): Full reboot test (T9c, pending), HUB_MAX_BODY_BYTES (request size limit), Photo category (T15, pending), Probe offline buffering (T11, pending), Run probe as a service (T12b, pending), ProbeHub (project), probehub-tunnel.service.example, Rate limiting (T10b, pending) (+8 more)

### Community 5 - "Data Contract & Config"
Cohesion: 0.22
Nodes (10): biswa (Postgres role), category field + per-category collectors (T14), Data contract (JSON envelope), DATABASE_URL, hub (backend), HUB_HOST, HUB_PORT, PostgreSQL (+2 more)

### Community 6 - "Hub Settings"
Cohesion: 0.24
Nodes (3): load_settings(), Settings, main()

### Community 8 - "API Endpoints & Service"
Cohesion: 0.25
Nodes (8): ecosystem.config.js (pm2 config), ecosystem.config.js (pm2 config), FastAPI, GET /health, hub (backend), POST /api/v1/data, PostgreSQL, probe (client)

## Knowledge Gaps
- **17 isolated node(s):** `path`, `probehub-hub`, `probehub-probe`, `probe (client)`, `FastAPI` (+12 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 80 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **6 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `hub (backend)` connect `Data Contract & Config` to `Hub Database Layer`, `Deployment & Roadmap`, `Hub Settings`, `Auth & Request Guard`, `API Endpoints & Service`?**
  _High betweenness centrality (0.204) - this node is a cross-community bridge._
- **Why does `Tasks list (Phase 1 / Phase 2)` connect `Deployment & Roadmap` to `Data Contract & Config`?**
  _High betweenness centrality (0.105) - this node is a cross-community bridge._
- **Why does `HUB_API_TOKEN (auth, deliberately disabled)` connect `Deployment & Roadmap` to `Auth & Request Guard`?**
  _High betweenness centrality (0.085) - this node is a cross-community bridge._
- **Are the 3 inferred relationships involving `create_app()` (e.g. with `Guard` and `lifespan()`) actually correct?**
  _`create_app()` has 3 INFERRED edges - model-reasoned connections that need verification._
- **What connects `path`, `probehub-hub`, `probehub-probe` to the rest of the system?**
  _17 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Hub Database Layer` be split into smaller, more focused modules?**
  _Cohesion score 0.09655172413793103 - nodes in this community are weakly interconnected._
- **Should `Hub API Tests` be split into smaller, more focused modules?**
  _Cohesion score 0.1 - nodes in this community are weakly interconnected._