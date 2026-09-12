# Technology Stack — Implementation Layer

The v2.1 stack (§7.1) is sound. This document confirms most of it, **disagrees on
two choices**, and fills in the layers the design never specified (auth, hosting,
reveal fanout, testing).

## Recommended V1 stack

| Layer | Choice | Status vs. v2.1 |
|---|---|---|
| Resolution engine | Pure Python 3.12, zero dependencies, **integer comparison only** | **new — extracted as its own package** |
| API | FastAPI + Pydantic v2 + `asyncpg` | confirmed |
| Database | PostgreSQL 17 or 18, managed | confirmed |
| Migrations | Alembic, or plain numbered SQL | **new — unspecified** |
| Cache / limits | Valkey 8 (or Redis 7.x), strictly derived | confirmed, **with a licensing note** |
| Lifecycle orchestration | Postgres-backed scheduler + advisory locks | **disagree — Temporal is wrong for V1** |
| Derived/background work | `arq` (async, Redis) | disagree with Celery |
| Web | Next.js App Router + React + TypeScript | confirmed |
| UI | Tailwind CSS + Framer Motion + TanStack Query | confirmed, +data layer |
| Realtime | HTTP polling with server-directed intervals | **new — not websockets at V1** |
| Auth | OAuth (Google/Apple) via Auth.js or Clerk | **new — entirely unspecified** |
| Edge | Cloudflare CDN + TLS + Turnstile | confirmed, **CDN is load-bearing** |
| Observability | OpenTelemetry + Prometheus + Sentry + structured JSON | confirmed, + integrity metrics |
| Testing | pytest + Hypothesis + testcontainers + k6 | **new — unspecified** |

---

## The two disagreements

### 1. Temporal is the wrong tool for V1 orchestration

§7.1 prefers Temporal. Temporal is genuinely good at durable multi-step workflows —
but this system has roughly **four scheduled transitions per round** (open, blackout,
seal, reveal), and the design already insists (§6.1) that *"the database, not an
application timer alone, is authoritative for whether a transition is legal"* and
that every mutation re-checks round state.

That means Temporal would be running a second, weaker copy of a state machine that
must live in Postgres anyway — paying a cluster (or Temporal Cloud spend), a new
deployment model, and a new failure domain for scheduling four timers.

**Use instead:** a small Postgres-backed scheduler. Transitions are rows; a worker
polls for due transitions, takes a `pg_advisory_xact_lock` on the round, re-checks
state, and performs the transition idempotently. Multiple workers are safe by
construction. Total: a few hundred lines, no new infrastructure, and the state
machine exists in exactly one place.

**Adopt Temporal when** resolution grows into a genuinely long multi-stage pipeline
with external calls (payouts, notifications, third-party attestation) — realistically
post-V1. The migration is easy precisely because transitions are already idempotent.

For *derived* work (leaderboard materialisation, cache warming) a Redis queue is
fine — losing one of those jobs delays a view, it cannot corrupt a round. Prefer
**arq** over Celery: async-native, pairs cleanly with FastAPI, far simpler.

### 2. The resolution engine must be its own dependency-free package

Not in the document, but it is what makes acceptance criterion §9.4 achievable
rather than aspirational.

```
engine/                    # pure functions, zero I/O, zero dependencies
  rank.py                  # counts[10] -> winning number (3 distinct digits)
  distance.py              # (prediction, winner) -> digit distance
  resolve.py               # submissions -> winners, histogram, audit ledger
  canonical.py             # canonical encoding + Merkle root
  VERSION                  # algorithm_version, frozen per ruleset
```

Under ruleset V1.1 (`00-ruleset.md`) `rank.py` is a sort on
`(count desc, digit asc)` — integer comparison, no division, no rational
arithmetic. The v2.1 float-drift concern no longer applies, which removes a whole
class of test.

The API imports it. The sealing worker imports it. The **public audit CLI** imports
it and nothing else. An independent third party can then reproduce the result from
the published dataset by running the same code path — which is the entire point of
§8.3 and §8.4.

It is also the only part of the system that can be *exhaustively* tested: all
720,000 (prediction, winner) pairs for distance, plus Hypothesis property tests
over count vectors for ranking, plus frozen golden vectors that fail loudly if
anyone changes behaviour without bumping `algorithm_version`.

Build this first. It has no dependencies, it is where correctness actually lives,
and under V1.1 it is small enough to finish in a day or two.

---

## Reveal fanout — the part with no design yet

Per F2, T+30h is the real 500k-concurrent event. Resolution has a **six-hour
window** (T+24 → T+30) to precompute everything, so almost none of this needs to be
live:

1. **Global payload is identical for every player** — winning number, histogram,
   audit ledger, Merkle root. Write it once during resolution as a static immutable
   JSON object, publish to the CDN at exactly T+30. One object serves 500k clients
   at zero database cost.
2. **Personal result cards are precomputed**, one row per player, written during
   resolution. Reveal then serves a single indexed keyed read — no computation, no
   join, trivially cacheable per user.
3. **Clients poll with server-directed jitter.** `GET /time` returns server time
   plus a per-client `reveal_after` offset spread over ~60s. Never let 500k clients
   fire at the same instant because their own clocks said so.

This converts the hardest scaling problem in the system into one CDN object plus
cheap keyed reads. It is why websockets are not needed at V1: state changes hourly
during OPEN, and the one true event is a scheduled, precomputable broadcast.

---

## Notes on the confirmed choices

**PostgreSQL** — the authoritative call is right and load-bearing. Add: one primary
for all writes, a read replica for history/metrics reads (never for submission
paths — replica lag would violate read-your-writes on a durable ack). Postgres 18
is available and fine; 17 is the safer floor.

**Valkey vs Redis** — Redis relicensed at 7.4 (RSALv2/SSPL). Valkey is the BSD-licensed
fork, drop-in compatible, and what most managed providers now run. Either works;
just make it a deliberate choice rather than inheriting a licence you didn't read.

**FastAPI + asyncpg** — for the transactional core (draft update, lock-in, sealing),
write **explicit SQL** rather than ORM-generated queries. The surface is ~9
endpoints and every transaction is correctness-critical; you want each one readable
in full. Use SQLAlchemy Core only if you want it for the non-critical read paths.

**Next.js** — App Router is a good fit: server components for history and reveal,
a thin client island for the console. Two rules the design implies but doesn't say:
the countdown must be driven by server time (§6.4), and the console must render
from authoritative round state, never from a local timer's opinion of the phase.

**Cloudflare** — not merely "protection and bot friction" as §7.1 frames it. The
CDN in front of aggregate and reveal endpoints is a core scaling component per the
section above. Turnstile at signup and lock-in.

**Auth** — buy, don't build. Auth.js (self-hosted, free) or Clerk (managed, faster).
Google + Apple OAuth only, httpOnly cookie sessions, `user_id` as the single
identity across the schema. No password reset flows to own, and a verified provider
identity is meaningfully better sybil friction than an email field.

---

## Repository shape

```
consensus/
  engine/        # pure deterministic resolver (build first)
  db/            # migrations + schema, single source of DDL truth
  api/           # FastAPI service
  workers/       # lifecycle scheduler, sealing, resolution, materialisation
  web/           # Next.js console + reveal
  audit/         # public CLI: re-derive results from published data, imports engine only
  loadtest/      # k6 scenarios (draft write, seal, reveal fanout)
  analysis/      # game-balance simulation  <- already present
  docs/          # design docs + ADR log
```

Monorepo. The dependency rule that matters: **`engine/` imports nothing from the
rest of the tree**, and `audit/` depends only on `engine/`. Enforce it in CI.

## CI gates from day one

- `engine/` test suite on every commit — non-negotiable, it is the product
- Golden-vector test that fails if resolution behaviour changes without an
  `algorithm_version` bump
- Real Postgres in CI via testcontainers, not SQLite — the constraints *are* the design
- Migration apply + rollback check
