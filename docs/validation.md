# Executed validation

- `pnpm build`: TypeScript strict check + Vite production build passed. Bundle approximately 345 kB JS / 108 kB gzip; no build errors.
- `cd apps/api && .venv/bin/python -m pytest -q`: 10 passed. Includes favorite pair changes, court/tournament isolation, next court match, transitions, schedule changes, estimate floor/ranges, no false imminence, API reads, notification deduplication/device isolation, progression conflict, previous-finished/start events, demo guard and conservative approaching events.
- Alembic `upgrade head` executed against temporary SQLite database.
- Uvicorn startup executed; API loaded through Vite proxy in actual browser.
- Browser mobile viewport inspected visually. Navigated Home → Favorites → Tournaments → unpublished Milano order → Home. Searched `lebron` (matched accented Lebrón), added and removed favorite (counter 4 → 5 → 4). Opened alerts, verified scheduled notification, Escape closed dialog and restored trigger focus.
- Mobile screenshot: `mobile-preview.png`.

Not executed: real PostgreSQL migration, licensed provider integration, external push, production concurrency, automated browser tests, desktop screenshot, explicit 320 px viewport, synthetic long-name injection or network-failure simulation. Loading/error/empty fallback implementations exist but only unpublished-order empty state was browser exercised. Do not treat implemented fallbacks as tested cases.

## Public collector increment

- Live one-shot collector executed against Premier Padel public site: saved one Milano tournament, eight players and two completed finals into `data/premier.json` (ignored by Git).
- 19 backend tests passed including nine new collector/provider cases: public metadata parsing, player identity and scores, contradictory timing header, unconfirmed order, malformed source rejection, atomic file and stale-live suppression, robots/access failures, day isolation, real API/demo/notification separation.
- `pnpm build` passed after source-aware UI changes.
- Browser verified public snapshot label, stale warning, Milano final results and unconfirmed sequence. No account used.
- Not verified: actual in-progress tournament latency, official preceding-match sequence, full season enumeration or permission for public redistribution. No recurring scraper scheduled.

## Background tracking increment

- Backend suite: 30 tests passed, including durable transition events, replay/restart idempotence, pause/resume subscriptions, stale and missing data, reviewed court dependencies, source-order invalidation, worker idle state, backoff and shutdown.
- Alembic `upgrade head` (0001 → 0002) passed against a temporary SQLite database.
- Frontend TypeScript/Vite build passed after collector-aware source labels and notification settings.
- Local API launched with `COLLECTOR_ENABLED=true`, Milano slug and 90-second active interval. Actual browser showed `Automatic collector · idle · data outdated`; no historical matches were polled as live on 19 October.
- No current live tournament cycle, external push, public deployment, automatic next-tournament discovery or source-provided official court sequence was validated. Tests use injected deterministic source observations for transitions.

## Zero-budget / PWA increment

- `pnpm build`: strict TypeScript + production PWA bundle passed; manifest, worker and icons generated.
- Backend tests: 37 passed, including signed trigger expiry/tampering, serverless event replay, stale-source safety, anonymous-identity isolation and refusal of unconfigured cloud calls.
- Node scheduler tests: 2 passed (HMAC contract, fixed HTTPS destination and missing-config rejection).
- Firebase Admin SDK imports and WebpushConfig message construction executed locally without credentials or network sends.
- Production preview served on localhost:4173; browser rendered Settings and disabled notification buttons with explicit Firebase-not-configured message. Browser warning/error log empty after API restored.
- Not executed: Vercel deployment validation, Firestore live transactions/rules emulator, actual Cloudflare Cron invocation, FCM delivery, installation on physical iPhone/Android, background push or source order verification. No accounts, repo, billing or hosted resources created.

## Mixed official court order — 22 October 2026

- 48 backend tests passed. Added actual-source mixed order parsing, ambiguous/incomplete/wrong-day rejection, metadata-to-widget addressing, tomorrow's discovery and two-day collection. A verified women's predecessor finishing generates one alert for Coello's following men's match; replay and repeated mocked push delivery produce no duplicates.
- Live collector against both public sources: six Milano matches on 17–18 October, six confirmed positions, 13 seconds. Kuwait 23–24 October: zero published matches, 7.4 seconds. Historical records were not installed in production.
- Owner confirmed actual iPhone push delivery with app open and closed; lock-screen screenshot supplied. This supersedes earlier physical-push test limitations above.
- Real in-play source latency, Kuwait qualifying coverage and its future published court mapping are still unverified.

- Frontend build and three preference tests pass. Browser verified separate 17/18 October headings and the mixed verified court sequence using an isolated local preview of real historical data.
