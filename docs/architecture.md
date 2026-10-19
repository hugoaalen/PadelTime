# Architecture

## Boundaries

`apps/web`: React, TypeScript, Vite, Tailwind, React Router, TanStack Query. CSS tokens define graphite/lime palette and light appearance. Radix supplies switch behavior; native HTML dialog traps focus and handles Escape. Bottom navigation respects safe areas; reduced motion suppresses transitions. No remote imagery or font dependency.

`apps/api/padeltime/domain.py`: pure tracking, dependency, transition and deterministic range functions. Finished, retired, walkover and cancelled matches release court dependency. Suspended/delayed predecessor prevents estimates. Court changes and sequence changes trigger schedule events.

`provider.py`: typed provider protocol, implemented by mutable MockProvider. Provider methods cover tournaments, players, matches, day order and live scores. Replace provider via dependency wiring when adding authorized integrations. Current API explicitly instantiates MockProvider. Dates anchored to server UTC day; UI converts timestamps to selected IANA zone. Production provider must define venue-local tournament dates and court-day identity.

`models.py`: SQLAlchemy models for users, players, tournaments/circuits, courts, matches, participants, favorites, preferences, event outbox and history. Participants attach to individual fixtures, so pairs can change. Demo provider data is in memory; events and history persist in SQLite by default. Favorites/settings stay in browser storage. Models for accounts/preferences are foundations, not active synchronization.

Use PostgreSQL via `DATABASE_URL=postgresql+psycopg://...`; schema uses portable types. Alembic initial migration supplied (`cd apps/api; .venv/bin/alembic upgrade head`). Local API bootstrap creates missing tables. Production should remove bootstrap, version all schema changes with explicit migrations, and apply migrations before serving. Initial migration imports current metadata; freeze explicit operations before subsequent schema revisions.

## Timing and notifications

Pending scheduled predecessor: 65–120 minutes plus 10–15 minutes turnaround. Live predecessor: 20–75 minutes plus turnaround. These intentionally broad demo constants are not validated sports predictions. Earliest official time acts as floor. No pending predecessor gives unknown actual start, even after prior match finishes. Score set count only informs explanatory copy. No fabricated imminent-start state.

Notification sync emits scheduled and, only within 15 minutes of official earliest time with clear court, approaching alerts. Wording explicitly avoids promising actual start. Mutations emit started, finished, previous-finished and schedule-change events. A unique `(audience, match, event type, revision)` constraint prevents retries from duplicating an event. History persists revisions. This is a single-process demo; production needs transactional provider ingestion, durable fixture revisions, concurrent insert conflict handling, authenticated event audience, rate limits and an outbox delivery worker. A schedule-changing revision may legitimately create a new scheduled event.

## Legitimate live integration

1. Obtain licensed feed/API and written usage rights; inspect terms, rate limits, caching and display attribution requirements.
2. Map stable provider IDs to internal IDs; retain source provenance, update timestamps and fixture revisions.
3. Normalize venue time zones, court/day order, score format, retirements, walkovers, cancellations and reschedules.
4. Preserve unknown/missing data and stale feed state. Never infer a start from an unavailable score.
5. Add replay fixtures and contract tests; use backoff, health monitoring, reconciliation and transactional event generation.

No Premier Padel public endpoint assumed; no scraping, authentication bypass or invented API URLs.

## Next production work

Licensed data adapter, durable match repository, authoritative ingestion clock, authenticated accounts and row-level policies for Supabase, event-specific preferences, external push, stale-score UI, schema-generated frontend contracts and browser regression suite. Capacitor can wrap frontend later; native safe-area and viewport rules already present.

## Optional public snapshot adapter

`collectors/premier.py` implements a one-shot public website collector; `snapshot.py` provides the validated JSON through the existing API. FIP extraction was excluded after checking its restrictions. Public snapshot mode deliberately suppresses dependency estimates and notifications when order is unconfirmed, isolates favorites, and labels stale observations. Details and observed source contracts: [public collector](public-collector.md).
