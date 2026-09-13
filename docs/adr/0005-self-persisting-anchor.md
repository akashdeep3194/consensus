# ADR 0005 — A self-persisting round anchor, and self-healing round scheduling

**Status:** accepted · **Date:** 2026-09-14

## Context

Production reached a state where `GET /api/rounds` returned `[]` — no round
was live, and nothing was creating one. Traced to `api/deps.py::_anchor()`:
whenever `ROUND_ANCHOR` is unset (true in production — `render.yaml` never
set it), the anchor was recomputed as "midnight UTC today" on every process
restart. Render's free tier restarts often (idle spin-down). Cycle numbers
are counted forward from the anchor (`domain/schedule.py::schedule_for`), and
`cycle_number` is a database-unique column — so a restart landing on a new
calendar day computed the same low cycle number an earlier restart already
used, `ensure_scheduled()` handed back that pre-existing (now long-expired)
row unchanged, and `advance_due()` fast-forwarded it straight to `REVEALED`.
Nothing in the passive path ever created a fresh round for the actual
current day: the one thing that could (`api/main.py::_open_next_round()`)
was wired only to the manual admin force-seal endpoint.

Two independent gaps, either one sufficient to eventually strand the game:
an anchor that isn't actually fixed, and no self-recovery when nothing is
live for any reason.

## Decision

**A self-persisting anchor.** `schedule_anchor` (`db/migrations/0006`) is a
singleton table — a `boolean PRIMARY KEY DEFAULT true` with a `CHECK (id)`
makes a second row impossible at the schema level, not by convention.
`services/anchor.py::resolve_anchor(pool, seed=None)` reads it if present;
otherwise inserts `seed` (or midnight UTC) via `INSERT ... ON CONFLICT DO
NOTHING` and re-reads. `ROUND_ANCHOR` becomes an optional one-time seed,
consulted only on a database's first-ever boot, rather than a value that
must be set correctly in every environment forever — removing the actual
class of failure (an operator forgetting to configure something) rather
than documenting around it.

**Self-healing scheduling.** `RoundService.ensure_open_round()` (relocated
from `_open_next_round()`, through the ports rather than raw-pool/private-
attribute access) opens `highest_cycle()+1` — deliberately anchor-independent,
since anchor-derived arithmetic is exactly what got this wrong — whenever
nothing is `OPEN`/`BLACKOUT`. `ensure_current()` calls it every time, since
it is already, per its own contract, the one entry point both the request
path and the background scheduler share to bring round state up to date.
`force_seal()` calls the same method for its "open the successor early"
behaviour, rather than a second implementation of the same idea.

## Consequences

- Layer 1 alone does not retroactively fix an already-stuck database — the
  stale `cycle_number` rows still exist. Layer 2 is what actually recovers:
  the next request or sweep after this deploys sees nothing live and opens
  a fresh round, no manual intervention required.
- `RoundReader` gains `highest_cycle()`, implemented identically in both
  adapters and covered by the shared conformance suite — the same LSP
  discipline ADR 0004 already established for every other port method.
- `Container.build` becomes `async` (one call site, already inside an async
  `lifespan()` that awaits other setup first).
- A round opened by `ensure_open_round()` at a cycle number far ahead of
  `(now - anchor)/cadence` can show schedule timestamps that don't line up
  with wall-clock time, even though its `status` is correctly forced open.
  Status gates entry, not the displayed timestamps. This is inherited
  unchanged from `_open_next_round()` (the existing demo-acceleration path
  already produces it on purpose) — not introduced by this fix, and left for
  a separate ticket.
