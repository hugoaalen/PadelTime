# API (demo v0.1)

Interactive Pydantic/OpenAPI contracts: `/docs` and `/openapi.json`.

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/health` | Health + demo marker |
| GET | `/api/players` | Player directory |
| GET | `/api/tournaments` | Current/upcoming demo tournaments |
| GET | `/api/matches?tournament_id=` | Fixtures with tracking and estimates |
| GET | `/api/matches/{id}` | Fixture details, 404 if absent |
| GET | `/api/tournaments/{id}/order-of-play?date=YYYY-MM-DD` | Day fixtures; empty for unpublished days |
| POST | `/api/notifications/sync` | Generate initial/approaching events and return inbox |
| GET | `/api/notifications/{audience}` | Latest 50 events for anonymous device |
| POST | `/api/demo/{id}` | Development mutation, requires `DEMO_MODE=true` |

Sync body: `{ "audience": "anonymous-uuid", "favorites": ["2", "3"] }`.
Demo body adds `"action": "advance" | "score" | "delay" | "reschedule"`.
Conflicting transitions return 409; disabled mutation returns 403. Only live fixtures accept score progress. Production build hides demo controls; backend gate remains independent.

In `DATA_PROVIDER=snapshot` mode the same read endpoints serve the collected file, not mocks. `/api/health` includes `source`, `snapshot`, `fetched_at`, `stale`, `date` and warnings. Match records include `day`, `court_id`, `schedule_label`, `source_url` and `order_confirmed`. Unconfirmed sequence has `tracking.remaining=null`, no predecessor and no estimate. Notification sync returns an empty list; demo mutations return 403. See [collector documentation](public-collector.md).

With `COLLECTOR_ENABLED=true`, snapshot mode additionally reports worker state (`starting`, `collecting`, `running`, `idle`, `error`, `blocked`), last success, error and next attempt in `/api/health`. Notification sync persists anonymous favorite subscriptions plus optional `enabled` flag (default true), returning durable in-app events. Without the worker, snapshot notifications remain disabled.

`GET /api/tracking/history?match_id=` returns latest 50 persisted status/schedule observations. Source warm-up and on-court statuses are represented as `WARMUP` and `ON_COURT`; neither is falsely mapped to `LIVE`.
