# ADR 0001 — Rank the three most-voted digits instead of D'Hondt allocation

**Status:** accepted · **Date:** 2026-09-12 · **Supersedes:** v2.1 §2

## Context

v2.1 allocated three positions by D'Hondt. Measurement (`analysis/dhondt_equilibrium.py`,
exact rational arithmetic) showed the outcome shape is a step function of the leading
digit's vote share: `ABC` below 18.2% (2/11), `AAB` to 25%, and a **repdigit above 25%**
(1/4). Because vote and prediction are independent and prediction frequency cannot move
the outcome, joining the visibly leading digit costs a player nothing — there is no
counter-pressure toward fragmentation, so the game drifts to a repdigit unaided.

## Decision

The winning number is the three most-voted digits, ranked by count, ties to the lower
digit. Always three distinct digits.

## Consequences

- A repdigit is not representable; the failure mode is gone structurally.
- Integer comparison only — the v2.1 exact-rational requirement (§2.2) disappears.
- Outcome space 1000 → 720; predictions constrained to distinct digits to match.
- Zero votes yield `012` by the ordinary tie-break, needing no special case.
- Coordination is retained as a core mechanic: one bloc locks position 1 and leaves
  72 outcomes live. A full lock needs three organised blocs of deliberately different
  sizes — tracked as a game-health metric, not prevented.
