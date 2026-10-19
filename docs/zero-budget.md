# Zero-budget profile — Vercel deployed, Firebase pending

**Hard requirement: no mandatory payment, trial, credit card or billing-enabled project.** Vercel Hobby project `hugoaalen-projects/padeltime` is deployed at https://padeltime-two.vercel.app and connected to GitHub. Firebase and Cloudflare remain unconfigured. Nothing here enables Blaze or purchases a paid API.

## Selected architecture

- Vercel **Hobby**: static PWA and short request-scoped Python API, with platform subdomain (no domain purchase). Hobby is limited to personal/non-commercial use; review eligibility before any commercial launch.
- Firebase **Spark**: anonymous Auth, Firestore and Cloud Messaging. Keep billing account unlinked. Do not upgrade to Blaze. No Cloud Functions, Cloud Scheduler, Storage bucket or Data Connect dependency.
- Cloudflare **Workers Free**: tiny three-minute cron that signs a fixed HTTPS Vercel request. It does not scrape, store user data or send notifications itself. CPU-heavy work stays in Vercel function. Do not subscribe to paid Workers.
- Source: existing experimental public Premier Padel adapter, not a paid API. Published FIP restrictions remain respected; no FIP collector.

Current official references checked 19 October 2026:

- https://vercel.com/docs/plans/hobby
- https://vercel.com/docs/cron-jobs/usage-and-pricing (Hobby cron only daily; not used)
- https://firebase.google.com/docs/projects/billing/firebase-pricing-plans
- https://firebase.google.com/docs/firestore/quotas
- https://firebase.google.com/pricing
- https://developers.cloudflare.com/workers/platform/pricing/
- https://developers.cloudflare.com/workers/configuration/cron-triggers/

Free plan limits are service limits, not an uptime SLA. Requests may fail or be suspended after quota exhaustion; **never upgrade automatically**. A billing budget is not a spending cap; do not link billing at all.

## Concrete code

- `apps/api/padeltime/cloud.py` (`padeltime/cloud.py`): separate serverless app, avoiding SQLite and embedded infinite worker.
- `cloud_state.py`: shared pure transition/outbox logic. Confirmed warm-up, live and finish transitions; unknown court order never creates predecessor alerts.
- `infra/clock`: signed cron, fixed destination, no public manual trigger. Three-minute polling, not second-by-second live coverage.
- Firestore transactions hold short collector lease, monotonic revisions, deduplicated inbox and preference updates. Different processes use durable state. FCM delivery is retried; a stable event ID/tag limits duplicate visible notifications. Push is not an exactly-once delivery guarantee.
- `firebase.json` / `infra/firestore.rules`: deny direct client storage access; anonymous identity verified by backend. Client-supplied audience IDs ignored.
- PWA manifest, generated PNG icons, bundled module service worker, Firebase device registration and explicit permission button. Frontend never prompts on page load. Shell cache excludes API data; source outages cannot be mistaken for cached fresh scores.
- `PushSettings`: honest disabled state until Firebase config exists, plus test and disable controls.

## Scope/capacity

Initial cloud pilot explicitly caps registered anonymous devices at **20**, retains 250 recent fixture observations and 30 inbox events per device, checks snapshot size below 750 kB, reserves a conservative collector write budget of 12,000/day, and caps signed collection attempts at 480/day. Public read endpoints use short shared HTTP caches; client polling slows to three minutes in cloud mode. Firebase's Spark quotas remain the final hard service limits, including reads and network. Device/API abuse or cache misses can exhaust quotas earlier. Limits mean requests stop, not charges; this is not unlimited free hosting.

Collector discovers the tournament metadata currently embedded in Premier's public homepage. It checks venue-local dates and idles if no active event is found; prior results are never re-timestamped as fresh. Coverage is only what that page exposes, not guaranteed enumeration of every circuit event. Public site schema and access can change. Court order remains **unconfirmed** unless verifiable evidence exists; no positions are fabricated from array order.

## When accounts exist — setup checklist

Vercel project creation and GitHub linking are complete. Remaining Firebase/Cloudflare setup follows:

1. Create personal GitHub repository (optional for CLI deployment) and Vercel Hobby project at repo root. Use `vercel.json`; no Vercel cron is configured. If a paid plan or card is demanded, stop.
2. Create Firebase project on Spark, without Google Cloud billing. Enable anonymous sign-in, create Firestore database on free quota and apply `infra/firestore.rules`. Enable Firebase Cloud Messaging web configuration/VAPID public key. Add deployment domain to Auth authorized domains.
3. Put public web config from `apps/web/.env.example` in Vercel build variables and set `VITE_CLOUD_MODE=true`. Public Firebase web API key is not the service-account private key.
4. Put service-account JSON only in encrypted server variable `FIREBASE_SERVICE_ACCOUNT`; use least-privilege Firestore/FCM permissions. Set `FIREBASE_PLAN=spark`. Code refuses cloud storage without this explicit declaration; it cannot independently prove the project has no billing account, so verify Spark in console.
5. Generate a random collector secret of at least 32 characters locally; set it only in server variable `COLLECT_SECRET` and Cloudflare secret of the same name. Never paste secrets into chat, Git or browser bundles.
6. Create Workers Free account/project, edit fixed `COLLECT_URL` in `infra/clock/wrangler.toml` to your Vercel subdomain and deploy that worker. Do not attach paid Workers, external paid schedulers or paid source tokens.
7. First signed tick creates real snapshot. Check `/api/health`, freshness, quota usage and source restrictions. A source access restriction blocks further source polling; operator intervention needed.
8. On iPhone/iPad 16.4+: Add to Home Screen, reopen installed app, then press Enable device notifications. Android browser support varies; install recommended. Grant permission yourself. Use explicit Test notification and verify actual arrival with app closed.
9. Follow a player and replay deterministic test fixture in a separate local test environment. Then validate an actual tournament. Do not label fixture events real or claim mobile delivery from server-only tests.

No credential was generated or stored by this change. No push was sent to a real device. Source redistribution permission and actual complete order/latency remain unresolved; a free infrastructure path does not fix source completeness.

## Local verification

```sh
pnpm install --frozen-lockfile
pnpm build
node --test infra/clock/worker.test.mjs
cd apps/api
.venv/bin/python -m pytest -q
```

Local existing `padeltime.main:app` retains demo/snapshot behavior. Production service entrypoint is `asgi.py`, forwarding to `padeltime.cloud.app`, rooted at `apps/api`; `api/index.py` is a legacy compatibility wrapper, not a third service. For a local production PWA preview use `pnpm --dir apps/web exec vite preview --host 127.0.0.1`; Firebase controls remain disabled without configuration. A local preview cannot replace a real iOS/Android push delivery test.

## Vercel Services routing

Root `vercel.json` defines two independently built services: `web` (Vite at `apps/web`) and `api` (FastAPI at `apps/api`). Public `/api` and `/api/*` go to `api`, preserving the original path; all other requests go to `web`. Web service rewrites navigation URLs to `index.html`, leaving assets and service worker paths intact. Keep Vercel project Root Directory at repository root.

There are no server-to-server calls between these services, so no service bindings are declared. Browser JavaScript calls same-origin `/api`, not an internal service URL. Leave `VITE_API_URL` unset or `/api`; never expose runtime binding URLs via `VITE_*`. Firebase and Premier are external dependencies, not services in this project. Cloudflare calls the public signed `/api/collect` endpoint.

Run `vercel dev -L` from repository root with a current Vercel CLI to test both services together. Existing `pnpm dev` plus local Python server remains a separate developer workflow; its localhost proxy is not a production service call. Production Firebase configuration is still required.

## Production verification — 19 October 2026

Vercel built both services successfully with Python 3.12. Public checks on `https://padeltime-two.vercel.app`: `/` and `/settings` return HTML 200; manifest and `/sw.js` return 200 with correct content types; `/api/health` returns intentional JSON 503 requesting Firebase Spark configuration; unknown API route returns JSON 404. `VITE_CLOUD_MODE=true` is saved in Vercel Production configuration. No Firebase credentials, real snapshot or push delivery are configured.

The explicit `apps/api/asgi.py` callable forwards ASGI scopes to the cloud FastAPI app. It avoids the deployed Python analyzer rejecting the original module entrypoint. Local ASGI smoke test confirms the same missing-configuration 503 and unknown-route 404.
