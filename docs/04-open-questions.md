# Open Questions

Decision tracker for ruleset V1.1 (`00-ruleset.md`) and the scoring model
(`05-scoring-proposal.md`).

## ✅ Settled

| | Question | Decision |
|---|---|---|
| Q1 | Publish the live vote distribution during OPEN? | **Yes.** Coordination and social planning are core mechanics; the standings are what make them playable |
| Q2 | D'Hondt or Sainte-Laguë? | **Neither.** The winning number is the three most-voted digits, ranked, always distinct, ties to the lower digit |
| Q3 | Round cadence — overlapping or sequential? | **Daily, overlapping.** Round N resolves six hours into round N+1; the one-entry invariant is scoped per round |
| Q4 | What counts as a valid draft at seal? | **Both fields required**, enforced by `CHECK`; invalid drafts discarded at seal and counted in the audit record |
| Q5 | Where is the Merkle root published? | **At seal (T+24h)**, to an append-only public location. Upgrade the venue later |
| Q7 | Auth provider and signup friction? | **Google + Apple OAuth**, bought not built. One account per verified provider identity |
| Q9 | Redis-outage policy for rate limits? | **Fail open, alarm loudly.** Turnstile and the unique-entry constraint still hold |
| Q10 | Is the blackout snapshot advantage intended? | **Yes.** The dark hour is what keeps a multi-bloc lock contestable |
| N1 | Must predictions be three distinct digits? | **Yes.** 720 ordered distinct-digit slates |
| S1 | Does digit distance survive? | **No — retired.** A digit is a faction identity, not a magnitude. Replaced by the Board A tiers |
| S2 | Is the Mandate board in V1? | **Yes.** Ranked by position-weighted vote total `3·C[P₁] + 2·C[P₂] + 1·C[P₃]` |
| S3 | Mandate eligibility deadline | **T+12h.** A tunable game parameter |

## Still open

| # | Question | Blocks | Why it matters |
|---|---|---|---|
| **Q8** | **What does a winner actually win?** | M8, launch | 🔴 **The remaining release risk.** No prize, score, streak, rank or season is defined. Every other open item has a safe engineering default; this one has none, and the game can be technically complete and still not launchable |
| Q6 | Are individual entries public after reveal? | M4, M12 | Determines whether Merkle leaves need per-submission randomness. A leaf is otherwise brute-forceable in 7,200 guesses |
| Q11 | Expected launch population? | M11 | 500k is a target, not a forecast. Sizing, cost and the reveal-fanout design all scale from the real number |

All three are product calls with no engineering default. None blocks Milestones A
or B — Q6 is needed by M4, Q8 and Q11 before launch.
