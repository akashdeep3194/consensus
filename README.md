# Consensus 3D

A deterministic, asynchronous social prediction game. Players vote for a digit;
the three most-voted digits become the winning number. Separately, players
predict what that number will be. Organising a voting bloc is not cheating —
it's the game.

```bash
make venv          # one-time
make demo          # reset, seed a finished round + a live one, start the server
```

Then open the link it prints — **http://localhost:8099/dev/login?handle=you**

No Docker needed: it runs a local PostgreSQL cluster under `.devdata/`.

---

## The rules, in full

**Outcome** — the three most-voted digits, ranked by vote count, ties to the
lower digit. Always three distinct digits, so 720 outcomes are possible.
Integer comparison only; zero votes yields `012` with no special case.

**Two boards.** They measure different things and disagree often enough that
merging them would be dishonest:

| Board | Question | How it ranks |
|---|---|---|
| **A — The Number** | Did you call the result? | `TRIFECTA` (exact order) → `BOXED` (right three, any order) → `TWO` → `ONE` |
| **B — The Mandate** | Did you read the electorate? | `3·C[P₁] + 2·C[P₂] + 1·C[P₃]` |

Board B's weighting does real work: its maximum is uniquely the Trifecta, and
**misordering two positions costs exactly the vote margin between those
digits** — so misreading a near-tie barely hurts, while misreading a landslide
does. Only entries locked before T+12h score on it, because the vote
distribution is public and an ungated board would just reward copying the
standings before blackout.

**Round shape** — 24h open, 1h blackout with standings hidden, seal at T+24,
reveal at T+30. Rounds open daily, so two are live at once.

Full ruleset: [`docs/00-ruleset.md`](docs/00-ruleset.md).

---

## Architecture

Four layers, dependencies pointing inward only. `tools/check_layering.py`
fails CI on any violation, so this stays true rather than aspirational.

```
engine/     pure resolution maths — stdlib only, no I/O
domain/     round lifecycle, scheduling — stdlib only, no I/O
ports/      Protocols the services depend on
adapters/   postgres, in-memory
services/   use cases, composed from ports
api/        FastAPI — parse, authorise, delegate, serialise
web/        console (vanilla; the API is UI-agnostic)
```

Two decisions worth knowing:

- **PostgreSQL is authoritative for anything that can change an outcome.** Every
  invariant the engine enforces is *also* a database constraint, so it holds
  even when application code is wrong. Committed entries are immutable and
  append-only by trigger; a sealed round rejects writes through every path.
- **The engine is dependency-free and reused verbatim** by the API, the sealing
  worker, and (eventually) a public audit tool — which is what makes
  "an independent party can reproduce the result" achievable rather than a
  slogan.

## Commands

```bash
make demo      # fresh database, seeded, running
make run       # start without wiping
make test      # 202 tests
make lint      # ruff
make arch      # verify the dependency arrows
make db-test   # apply migrations, then prove each constraint rejects
make stop
```

## Status

Milestone A and most of B are done: the engine, schema, state machine,
transactional entry path, sealing and resolution, the HTTP API, and a playable
console. Not yet built: real OAuth (dev handles stand in), the derived Redis
serving layer, anti-abuse, load testing, and the public audit CLI.

| | |
|---|---|
| [`docs/00-ruleset.md`](docs/00-ruleset.md) | Authoritative rules |
| [`docs/01-design-evaluation.md`](docs/01-design-evaluation.md) | 14 findings against the original design |
| [`docs/02-tech-stack.md`](docs/02-tech-stack.md) | Stack rationale |
| [`docs/03-roadmap.md`](docs/03-roadmap.md) | Modules and exit criteria |
| [`docs/adr/`](docs/adr/) | Decisions and why |
| [`analysis/`](analysis/) | Simulations behind the rule choices |

> PostgreSQL defines what happened. The game rules define who won.
