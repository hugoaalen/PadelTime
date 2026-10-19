# PadelTime

A mobile-first professional padel companion. Default mock mode uses **demonstration schedules, ranks, scores and events**. Recognizable player names in that mode do not imply actual partnerships or fixtures. Optional public snapshot mode reads real collected results, explicitly labeled with source and freshness; see the collector section below.

## Run locally

Requirements: Node 20.19+ (tested with Node 26), pnpm 11, Python 3.9+.

From repository root:

```sh
pnpm install
python3 -m venv apps/api/.venv
apps/api/.venv/bin/pip install -r apps/api/requirements.txt
```

Terminal one:

```sh
cd apps/api
DEMO_MODE=true .venv/bin/uvicorn padeltime.main:app --reload --host 127.0.0.1 --port 8000
```

Terminal two, from root:

```sh
pnpm dev
```

Open http://localhost:5173. Vite proxies `/api` to FastAPI. API docs: http://127.0.0.1:8000/docs.

```sh
pnpm build
cd apps/api
.venv/bin/python -m pytest -q
```

The `.env.example` lists supported variables. Export backend variables in your shell (the API does not automatically load `.env`). Set frontend `VITE_API_URL` in `apps/web/.env.local` if needed. Keep frontend/backend same-origin in deployment; CORS is intentionally not enabled.

## Explore

- Home: Galán/Chingotto follow a third-set demo on Centre Court.
- Favorites: search names with or without accents, follow individual players; browser-local persistence.
- Tournaments: fixtures grouped by court and sequence; upcoming tournaments have unpublished orders.
- Match detail: local development controls change status, score, delay and earliest time. Complete preceding matches before starting the next one. Changes reset on API restart.
- Bell: durable in-app notifications scoped by anonymous browser UUID. Polling every 15 seconds. Settings pause notifications and set appearance/time zone.

External push, real data, authentication and account synchronization are not connected. Anonymous UUID is a demo partition, **not production authentication**. Do not deploy demo endpoints publicly.

## Architecture and limits

See [architecture](docs/architecture.md), [API contract](docs/api.md) and [validation](docs/validation.md). `packages/` reserved for future generated API types; no artificial shared library yet.

Applied skill: `caveman` for agent communication. Requested `emil-design-eng`, `mobile-native`, `apple-design`, `pick-ui-library`, `animate`, `break-ui` were not installed in accessible skill directories. UI follows the supplied design requirements directly; Radix Switch selected for accessible keyboard/touch toggles, Lucide for icons.

## Real public-web snapshot prototype

An optional one-shot Premier Padel collector and JSON provider now exist. See [collector instructions, source checks and limitations](docs/public-collector.md). The demo instructions above still launch mock mode. Snapshot mode shows real collected results with provenance and freshness labels; it does not provide continuous live alerts. FIP scraping was not enabled because its published terms prohibit automated extraction.

Background tracking now available with `COLLECTOR_ENABLED=true`, a bootstrapped tournament snapshot and `COLLECTOR_SLUG`; active polling defaults to 90 seconds. Worker saves match revisions, subscriptions, history and in-app events transactionally. Ended/upcoming tournament stays idle. See [background tracking and reviewed court order](docs/public-collector.md#background-tracking-local-development). Official court sequence remains unconfirmed unless independently reviewed; external push is still pending.

## Mandatory zero-budget deployment profile

**No paid APIs, no Blaze, no billing account.** Prepared Vercel Hobby + Firebase Spark adapter, PWA/push client and Cloudflare Workers Free signed clock. No cloud accounts, GitHub repository or deployments exist yet. See [zero-budget profile and exact remaining setup](docs/zero-budget.md). Existing local mode still works; production integration is not claimed tested against real Firebase or a mobile device.
