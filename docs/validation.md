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

## Product iteration — 30 October 2026

- Owner supplied physical iPhone screenshots of three real match alerts: predecessor finished, warm-up and live start. These verify the real source-to-device chain, superseding earlier live-delivery limitations.
- Added immutable match context to alerts: followed player, both teams, court, tournament, official timing and final set scores. Text renders in device language and stored IANA time zone; old events retain legacy rendering. Existing event IDs and deduplication are unchanged.
- Persistent player directory seeded from Premier's public rankings: 100 men and 100 women. The upstream endpoint caps each requested page at 100. This is an explicit initial directory, not all 14,052 source profiles. It retains previously seen players and merges current fixtures; daily bounded refresh does not depend on continued tournament participation.
- `/api/bootstrap` combines the four public startup queries into one cacheable request. Public reads do not wait for anonymous Firebase authentication. Settings and Firebase messaging load separately; recent startup data is reused for at most two minutes only while its source timestamp is still fresh. Loading uses skeletons; private sync failures are visible.
- Local production build: initial main JS 371.94 kB / 117.98 kB gzip versus previous production approximately 510 kB / 145 kB gzip. This is bundle-size evidence, not a measured iPhone load-time guarantee.
- Mobile browser 390×844: verified new score rows, compact freshness bar, home match discovery without favorites, female category search for Salazar, and players absent from the current draw. No test match push was sent to production devices.
- 52 backend tests and 3 preference tests pass; frontend production build passes.
- Device capacity now counts meaningful subscriptions rather than empty browser sessions. Upgrade script adds an `active` query field transactionally, retaining all tokens, preferences and events. Initial execution checked 20 records, one active, without deleting any device data.

## iOS icon background and opening safe area — 30 October 2026

Installed-app PNGs are now explicitly opaque RGB on `#0b1117`; `sips` verified no alpha channel at 192×192 and 512×512. The supplied original remains untouched. Header/settings retain a separate transparent logo under `/assets/padeltime-logo.png`. Icon URLs and the shell cache were versioned to avoid reusing the previous transparent icons; manifest and theme colors match the current surfaces.

Standalone layouts below 900px reserve `max(20px, env(safe-area-inset-top, 0px))` before the workspace. This moves the opening header away from iOS's top region without adding a fake blur or changing normal browser layout. Uses WebKit's documented safe-area approach: https://webkit.org/blog/7929/designing-websites-for-iphone-x/. The native iOS progressive blur and installed-icon refresh require confirmation on the user's physical iPhone; desktop browser checks cannot establish those OS effects.

Production build and three preference checks pass. No backend or notification-trigger behavior changed.
