# Roadmap — Work Breakdown

The document's §9.3 gives six phases. They are correctly ordered but too coarse to
execute against. Below: **12 modules in 4 milestones**, each with a concrete
deliverable and a testable exit criterion.

Sequencing principle: *the risky and the cheap go first.* The engine is small
under ruleset V1.1 and everything else depends on it, so it runs first.

**Updated for ruleset V1.1** (`00-ruleset.md`): the outcome engine is now a sort,
not D'Hondt. M1 shrinks considerably and the M1.5 balance gate is discharged — the
decision it existed to force has been made.

---

## Milestone A — Provably correct core
*A full round runs end to end from scripts. No UI, no users, no auth.*

### M0 · Foundations
Repo skeleton per `02-tech-stack.md`, `docker-compose` with Postgres + Valkey,
migration tooling, CI pipeline, ADR log seeded with the decisions in these docs.
**Exit:** `make test` green on a clean checkout; CI runs on push.

### M1 · Deterministic engine *(build first)*
Pure `engine/` package: rank-by-count outcome, result tiers (Trifecta / Boxed /
two / one / none), position-weighted mandate score, histogram, audit ledger,
canonical encoding + Merkle root.
**Exit:** all 720 × 720 (prediction, winner) pairs verified exhaustively;
Hypothesis properties green (determinism, invariance to vote arrival order,
output always three distinct digits, zero-vote → `012`, lower-digit tie-break at
every position, mandate score maximised uniquely by the Trifecta); golden-vector
file frozen; `00-ruleset.md` §2 and §3 examples reproduce.

### ~~M1.5 · Game-balance gate~~ ✅ *discharged*
Resolved by ruleset V1.1 — see F1 in `01-design-evaluation.md`. Ranking distinct
digits removes the degenerate regime structurally, and coordination is retained as
a core mechanic. One item carries forward into M11 as a **game-health metric**:
alert when the live outcome space falls below ~10 possibilities before blackout.

### M2 · Data model & state machine
Schema with real constraints (F6), round lifecycle as DB-authoritative transitions,
**daily overlapping rounds** (Q3), mandate eligibility timestamp (S3), UTC boundaries.
**Exit:** illegal transitions rejected at the database level; round cadence
documented; migrations apply and roll back cleanly.

### M3 · Submission core
Durable draft writes with optimistic versioning, lock-in transaction, idempotency
keys, status lookup.
**Exit:** the §9.2 concurrency and idempotency suites pass — two-tab conflict, retry
after timeout, no duplicate submission under burst.

### M4 · Sealing & resolution
Atomic cutoff + chunked idempotent materialisation (F5), deterministic seal-time
`commit_sequence` (F4), resolution pipeline, per-player result precomputation,
audit ledger, **Merkle root published at seal** (F3).
**Exit:** kill the sealing worker at any point mid-run and restart — identical final
state, no duplicates; independent replay reproduces number, histogram and winners.

> **End of Milestone A:** the game is provably correct. Everything after this is
> access, presentation and scale.

---

## Milestone B — Playable
*Real people can play a real round.*

### M5 · Auth & accounts
OAuth (Google/Apple), sessions, one account per verified identity, Turnstile,
registration rate limits (F9).
**Exit:** account cannot hold two entries in one round; signup abuse throttled.

### M6 · API surface
Full endpoint set including the pieces §7.2 omits — server time, history, round
list, health, operator surface (F12); `/metrics` vs `/results` split (F10);
server-side validation everywhere.
**Exit:** OpenAPI contract published; no sealed round is mutable through any path.

### M7 · Game console
Next.js console: draft entry, autosave, explicit lock-in, server-time countdown,
and the OPEN / BLACKOUT / LOCKED / SEALED phase states from §7.4.
**Exit:** every phase renders correctly from authoritative state; client clock skew
never changes what a player can do.

### M8 · Reveal experience
CDN-published global payload, precomputed personal result card, prediction
histogram, the two post-round stories (§3.3), audit viewer, reveal animation.
**Exit:** result card matches `audit/` CLI output for a sample of players; reveal
served without a database read on the global payload.

---

## Milestone C — Scalable & defensible

### M9 · Derived serving layer
Redis/Valkey materialisation, CDN cache policy, blackout freeze with identical bytes
(F8), stated Redis-outage degradation policy (F11).
**Exit:** kill Redis under load — no authoritative state lost, no acknowledged write
dropped, views degrade only.

### M10 · Integrity & anti-abuse
Bot/sybil heuristics, anomaly flagging, an entry-void path that never touches the
resolver, security test suite from §9.2.
**Exit:** voiding an entry changes results only through the normal deterministic
re-derivation; §9.2 security suite passes.

### M11 · Load, observability & operations
k6 scenarios for all three real load profiles (F2: draft writes, sealing at 500k,
**reveal fanout at 500k**), OTel traces, integrity dashboards (ack latency, seal
duration, drafts-vs-submissions reconciliation), runbooks, DR restore drill.
**Exit:** §9.1 target met against the *corrected* profile; a restore-from-backup
drill completed and timed; game-health alert live for outcome-space collapse
(carried over from the discharged M1.5).

---

## Milestone D — Verifiable in public

### M12 · Independent audit tooling
Public CLI depending only on `engine/`, published dataset format, documented
canonicalisation (field order, encoding, zero-padding, ordering key,
`algorithm_version`), root published at seal to an append-only location.
**Exit:** a third party, given only published data and the CLI, reproduces the
winning number, every distance, and the full winner set.

---

## Dependency graph

```
M0 ──> M1 ──> M2 ──> M3 ──> M4 ──┬──> M5 ──> M6 ──> M7 ──> M8
                                  │
                                  ├──> M9 ──> M11
                                  ├──> M10
                                  └──> M12
```

M9–M12 can run in parallel with Milestone B once M4 lands.

---

## Mapping back to §9.3

| v2.1 phase | Modules here | Change |
|---|---|---|
| Phase 1 — schema, state machine, drafts | M0, M2, M3 | unchanged |
| Phase 2 — outcome engine + tests | **M1** | **moved first**; much smaller under V1.1 |
| Phase 3 — API, idempotency, sealing | M4, M6 | + auth (M5), which §9.3 omits |
| Phase 4 — Next.js console, reveal | M7, M8 | + CDN reveal strategy |
| Phase 5 — Redis, workers | M9 | orchestration simplified (no Temporal) |
| Phase 6 — commitment, observability, load | M10, M11, M12 | root published at **seal**, not reveal |

One substantive change remains: the engine moves ahead of the schema. The
game-balance gate that formerly sat here has been discharged by ruleset V1.1.

---

## Suggested first week

1. `M0` — repo, compose, CI *(~1 day)*
2. `M1` — `engine/` with exhaustive + property tests *(~1–2 days under V1.1)*
3. `M2` — schema, constraints, round state machine *(~2 days)*

The engine is now small enough that the first week reaches into the data model.
At the end of it the resolver is proven correct against an exhaustive test suite
and frozen golden vectors, and everything downstream builds on a fixed foundation.
