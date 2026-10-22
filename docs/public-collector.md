# Public Premier Padel collector (local prototype)

## What works now

A single command reads the current public tournament metadata and one tournament day's public schedule into a normalized JSON snapshot. It fetches both male and female schedules, merges fixture IDs, and retains stable player IDs. The API reads that file; the frontend clearly labels it as a snapshot and separates real favorites from demo favorites. No signup, token, authentication cookies or payment used.

Executed on 18 October 2026 for `milano-p1-2`: 1 tournament, 8 players, 2 completed finals, including men's set scores 4–6 / 6–3 / 6–2 and women's 7–6 / 6–3. This is an observed capture, not evidence that ongoing live coverage or latency meets production needs.

## Run

From `apps/api` (venv dependencies include httpx):

```sh
.venv/bin/python -m padeltime.collectors.premier \
  --date 2026-10-18 --slug milano-p1-2 --output ../../data/premier.json

DATA_PROVIDER=snapshot \
SNAPSHOT_PATH="$PWD/../../data/premier.json" \
.venv/bin/uvicorn padeltime.main:app --reload --host 127.0.0.1 --port 8000
```

Run `pnpm dev` from repository root. Repeat the collection command manually to refresh that day; API reopens the atomic snapshot on each request. Use venue-local date and the slug actually shown in the official tournament URL. Only the selected tournament day is imported; this is not a whole-season crawler.

To restore demo, omit `DATA_PROVIDER`/`SNAPSHOT_PATH` and start with `DEMO_MODE=true`.

## Source inspection

- User-provided FIP calendar and Milano event pages were viewable without account. FIP legal page explicitly prohibits “data mining, robots or similar data gathering or extraction methods”: https://www.padelfip.com/legal/ . No FIP collector implemented or enabled. Inspection downloads were temporary and not imported into app.
- Premier public tournament page: https://premierpadel.com/es/tournaments-detail/milano-p1-2 . Its server-rendered HTML embeds JSON in Next.js Flight script text. Parser decodes JSON only, never runs downloaded JavaScript.
- Public schedule mechanism observed in its linked frontend scripts: POST `https://api-prod.premierpadel.com/api/tournament/getTournamentMatches`, with `slug`, `date`, `gender=male|female`, `isFavourite=false`, `matchStatus=All`; language header `es`. Unauthenticated responses were actually fetched successfully. This is an undocumented website endpoint, **not a promised public API contract**.
- `robots.txt` returned 404 on both Premier origins during collector run. Collector checks policies on every new run, respects exclusions/crawl-delay, and stops on unclear policies, redirects, 401/403/429 or other failures. Reuses same-day snapshot for 60 seconds to limit repeat commands. No retries, proxy rotation, CAPTCHA handling or credential fallback.
- Premier's linked terms page currently displayed a privacy notice: https://premierpadel.com/es/terms-and-conditions . Inspection did not establish a data redistribution license. Local prototype is not published as an external data service. Confirm provider permission/rights before public redistribution or recurring deployment; accessibility and robots allowance do not grant a license.

## Correctness limits

1. `player_id` is used for player identity; nested `id` varied per tournament participant.
2. Teams sorted by `team_no`; set scores preserve both sides and null/unavailable sets.
3. Observed `start_date_time` repeated session start even when header said “Not before 5:00 PM”. Only explicit `Starting at`/`Not before` header text is converted, using tournament IANA timezone. Unknown labels remain unknown, never guessed.
4. Source array was reverse chronological. No explicit court sequence was present. Sort by explicit header time for display, but mark `order_confirmed=false`. Previous-match tracking, ETA and next-on-court inference remain disabled for these records. Do not treat display index as official sequence.
5. Snapshot older than 120 seconds is stale. A cached LIVE status becomes UNKNOWN in served fixtures, preserving original raw observation in file. Completed results remain visible. Header always says snapshot, even when freshly collected.
6. Snapshot mode disables automatic event generation and demo mutation. Continuous ingestion, persisted authoritative revisions and verified official court order are needed before trustworthy notifications.
7. Failed fetch/parse preserves last JSON via atomic replace. No fake/demo fallback. Missing or invalid snapshot returns service unavailable.
8. Unknown source statuses map to UNKNOWN. More examples needed for cancellations, retirements, walkovers, tie-break display, following-match headers and daylight-saving edge cases. Scores do not prove completion; source status drives state.

## Next

Resolve legitimate recurring/public usage, confirm official order (including mixed men's/women's court days), then add bounded background ingestion, durable revisions and alert generation. This change intentionally does not schedule an unattended crawler or publish collected data externally.

## Background tracking (local development)

An opt-in worker now runs inside FastAPI's lifespan. With a single API process:

```sh
DATA_PROVIDER=snapshot \
SNAPSHOT_PATH="$PWD/../../data/premier.json" \
COLLECTOR_ENABLED=true \
COLLECTOR_SLUG=milano-p1-2 \
COLLECTOR_INTERVAL=90 \
.venv/bin/uvicorn padeltime.main:app --host 127.0.0.1 --port 8000
```

Uses the tournament venue's current date, never the historical snapshot date as live. Minimum interval 60 seconds; failures back off to 15 minutes. 401/403 or robots exclusions stop collection until configuration/source access is resolved and service restarts. No persistent scheduler outside API, and no external deployment or data republication performed. Do not run multiple Uvicorn workers with this embedded collector. For production use a dedicated worker with a distributed lease.

Milano ended on 18 October; on 19 October this configuration correctly stays **idle** without fetching old finals repeatedly. Change `COLLECTOR_SLUG` to the actual public URL slug of the next tournament and bootstrap its snapshot with the one-shot command before starting. Automatic season-wide discovery is not implemented.

`TrackedMatch` stores normalized observations with monotonic revisions; history and outbox commit in one transaction. Replaying an observation, restarting the process or polling inbox cannot recreate the same event. Missing fixtures are not inferred cancelled/finished. Source status `W` means warm-up, `C` on court, `P` live; only warm-up supports an approaching alert. Scores alone never imply match end. In-app subscriptions persist anonymously; browser preferences sync through `/api/notifications/sync` including `enabled=false` to pause. No authenticated or cross-device ownership guarantee yet.

### Reviewed court order

Public feed still has no verified sequence field. A local reviewed order can be applied via `ORDER_FILE` after checking a legitimate official order of play. Generate an **unconfirmed template**, not an automatic inference:

```sh
.venv/bin/python -m padeltime.order ../../data/premier.json > /tmp/order-template.json
```

For each complete court day, manually arrange `match_ids`, provide HTTPS `source_url` evidence and timezone-aware `reviewed_at`, then set `ORDER_FILE` to that reviewed JSON. Fingerprint binds confirmation to current participant IDs, court/day and timing labels. A schedule change withdraws confirmation; fresh results continue collecting, while predecessor alerts stay disabled until new review. This does not fetch FIP PDFs or bypass its restrictions. No order review has been fabricated for the real captured finals.

### Validation added

Backend tests exercise replay/restart deduplication, paused subscriptions, score-only changes, stale/missing observations, real status transitions, reviewed/unconfirmed predecessor events, schedule-change invalidation, venue-day selection, idle behavior, backoff and cancellation. `/api/tracking/history?match_id=` exposes latest 50 persisted changes. Actual in-play feed latency and real push delivery remain unverified.

## Current integration: mixed order widget (22 October 2026)

The earlier unconfirmed-order limitation is now resolved for courts that can be matched completely against the public MatchScorer Live court column linked by FIP. `collectors/matchscorer.py` joins that ordered, mixed-gender column to Premier identities; it never infers order from Premier arrays, timestamps or match IDs. Complete identity/day checks are required on every capture, so a changed or incomplete schedule withdraws confirmation automatically. See `zero-budget.md` for executed validation and current Kuwait publication limits. The optional manually reviewed order file remains supported by the local worker.
