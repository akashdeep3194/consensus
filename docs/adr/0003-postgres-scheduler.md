# ADR 0003 — Postgres-backed scheduler instead of Temporal for V1

**Status:** accepted · **Date:** 2026-09-12 · **Supersedes:** v2.1 §7.1

## Context

v2.1 preferred Temporal for lifecycle orchestration. There are ~4 scheduled transitions
per round, and §6.1 already requires the database — not an application timer — to be
authoritative for whether a transition is legal.

## Decision

A Postgres-backed scheduler with `pg_advisory_xact_lock`. Transitions are rows; a worker
polls for due transitions, takes the lock, re-checks state, and acts idempotently.

## Consequences

- One state machine, in the place the design already declares authoritative.
- No cluster, no new failure domain, no Temporal Cloud spend.
- Redis queues (arq) remain acceptable for *derived* work only — losing such a job delays
  a view, never a round.
- Adopt Temporal later if resolution grows external calls; migration is easy because the
  transitions are already idempotent.
