# ADR 0002 — Retire digit distance; score on two boards

**Status:** accepted · **Date:** 2026-09-12 · **Supersedes:** v2.1 §3

## Context

Under ADR 0001 the winner always has three distinct digits, so rank became the whole
skill and "right digits, wrong order" the commonest near-miss. Digit distance punished
it absurdly: for winner `527`, three of five permutations scored 10 against a mean of
8.7 over all 720 predictions, while an unrelated `427` scored 1.

More fundamentally, distance treats a digit as a **magnitude**. Under V1.1 a digit is a
**faction identity** — 4 is not "nearly" 5, it is a different bloc that lost.

## Decision

- **Board A — The Number:** tiers TRIFECTA / BOXED / TWO / ONE / NONE. Membership and
  order, never arithmetic proximity. Everyone in a tier shares it; no tie-break.
- **Board B — The Mandate:** ranked by `3·C[P₁] + 2·C[P₂] + 1·C[P₃]`, eligible to
  entries committed before T+12h.
- Digit distance is removed entirely.

## Why weighted, and why gated

Unweighted summation is order-blind and capped at one rank per digit set (`C(10,3) = 120`).
Weighting separates strictly further (~670 of 720 at realistic volumes), its maximum is
uniquely the Trifecta by the rearrangement inequality, and the cost of misordering two
positions equals exactly the vote margin between those digits — the penalty is
proportional to how hard the call was.

Without the eligibility gate the board is a copying contest: the vote distribution is
public, so a player copying the standings before blackout scores 99.99% of maximum and is
beaten by ~1 prediction in 720. The gate also repairs a pre-existing flaw — manual
lock-in was strategically pointless, since auto-commit at seal did the same thing.

## Why two boards and not one ranking

They genuinely disagree. For winner `738` with counts `7:175,000 · 3:125,000 · 8:25,000`,
**49 predictions holding only two winning digits outscore the worst BOXED permutation**
(asserted in `tests/test_mandate.py`). A merged ranking would place a partial hit above a
player who had every winning digit.
