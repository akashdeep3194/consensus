# ADR 0004 — Ports and adapters, with the layering enforced in CI

**Status:** accepted · **Date:** 2026-09-12

## Context

M2 introduces I/O. The v2.1 design makes two architectural demands that only
hold if the boundary is real: PostgreSQL is authoritative while Redis is
strictly derived (§4.1), and an independent auditor must reproduce a round using
the same resolver the service runs (§9.4).

Both fail the moment persistence concerns leak into the rules.

## Decision

Four layers, with dependencies pointing inward only:

| Layer | May import | Holds |
|---|---|---|
| `engine/` | stdlib | resolution maths — pure, no I/O |
| `domain/` | stdlib | round lifecycle, scheduling — pure, no I/O |
| `ports/` | domain, engine | Protocols: the contracts services depend on |
| `adapters/` | ports, domain, engine, drivers | Postgres, Redis, in-memory |

`tools/check_layering.py` walks the ASTs and fails CI on any violation, and on
any third-party import inside `engine/` or `domain/`.

## How the SOLID pressures are applied

- **SRP** — resolution maths, lifecycle rules, contracts and I/O each change for
  a different reason and live in different packages.
- **OCP** — round transitions are a frozen data table, mirrored into
  `round_transitions`. Adding a phase is data, in both places; the enforcing
  trigger and `is_legal()` never change.
- **LSP** — `tests/test_port_conformance.py` is parameterised by adapter. The
  Postgres adapter joins by adding one fixture parameter, and must pass the
  same assertions unchanged or it is not a valid substitute.
- **ISP** — roles, not tables: `RoundReader` is separate from `RoundWriter`, and
  the sealing worker's bulk `DraftScanner` is not reachable from the request
  path.
- **DIP** — services depend on Protocols; `asyncpg` appears only under
  `adapters/`.

## Consequences

- Two definitions of the state machine, in Python and in SQL. That is a real
  drift risk, accepted deliberately because the database must be able to refuse
  an illegal transition on its own (§6.1). `tests/test_schema_contract.py`
  parses the migration and fails if the two disagree — verified to catch drift
  in both directions.
- The in-memory adapter is not merely a test double; it is the reference
  implementation of each port's contract.
- Scale work stays localised: chunked sealing, read replicas and caching are
  adapter concerns and cannot reach the rules.
