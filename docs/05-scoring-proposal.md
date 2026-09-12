# Scoring & Leaderboards — Design Proposal

Status: **proposal, not yet ruleset.** Analysis in `analysis/boards.py`.

Two ideas under discussion: a named top prize for an exact hit, and a second
leaderboard ranking players by the total votes their three predicted digits
received. Both work. One needs a structural fix.

---

## 1. Name the top tiers — and borrow vocabulary that already exists

In horse racing a **trifecta** is picking the top three finishers *in exact order*,
and a **boxed** trifecta is the same three in *any* order. That is precisely this
game's structure, so the words come with meaning already attached — no invented
branding required.

| Tier | Condition | Players at N=500k |
|---|---|---|
| 🏆 **TRIFECTA** | all three digits, exact order | ~694 |
| 📦 **BOXED** | all three digits, any order | ~3,472 |
| — | two of three | ~— |
| — | one of three | ~— |

Counts assume uniform guessing over the 720 valid predictions.

**BOXED is also the fix for F14.** The order penalty finding was that misordering
the winning digits scores worse than guessing unrelated ones. Making "right three,
wrong order" a *named, respected result* rather than a catastrophic distance score
resolves it at the presentation layer, without touching any invariant.

Resist naming the lower tiers. Naming everything cheapens the top two.

---

## 2. The vote-sum board — good idea, two problems, both fixable

Proposal: `score(P) = C[P₁] + C[P₂] + C[P₃]` — the total votes your three digits
drew. Rank players by it.

### Problem A — it only produces 120 ranks, not 720

Raw summation is **order-blind**, so every player who picked the same three digits
ties exactly. There are only `C(10,3) = 120` distinct digit sets, so at 500k players
each rank holds ~4,000 people. It is a leaderboard of digit *sets*, not of players.

### Fix — weight by position, `3 / 2 / 1`

```
mandate_score(P) = 3·C[P₁] + 2·C[P₂] + 1·C[P₃]
```

| Scenario | raw sum | weighted 3/2/1 |
|---|---|---|
| uniform voting | 120 tiers | **660** |
| one bloc at 30% | 119 tiers | **678** |
| two blocs 30/20 | 120 tiers | **671** |

By the rearrangement inequality the maximum is achieved **only** by the true
winning number in exact order — so the Mandate board's #1 is always the Trifecta.

**And it produces a fairness property digit distance cannot.** The cost of
misordering two positions is *exactly the vote margin between those digits*:

> Round with winner `738` — counts `7: 174,917`, `3: 124,876`, `8: 25,177`
>
> | Prediction | Weighted score | Cost | Equals |
> |---|---|---|---|
> | `738` perfect | 799,680 | — | — |
> | `783` swap pos 2/3 | 699,981 | 99,699 | margin between 3 and 8 = **99,699** |
> | `378` swap pos 1/2 | 749,639 | 50,041 | margin between 7 and 3 = **50,041** |

Misordering two near-tied digits barely hurts; misordering two digits separated by a
landslide hurts a lot. **The penalty is proportional to how hard the call actually
was.** Digit distance scored those same two swaps at 8 and 10 — numbers derived from
the arbitrary numeric values of the digit labels, not from anything about the round.

### Problem B — the answer is published in real time 🔴

This is the serious one. The thing being predicted is the vote distribution, and the
vote distribution is **public throughout the OPEN phase**. So the optimal play is to
look at the standings shortly before blackout and copy the top three.

Measured (400 rounds, 480k votes visible, 20k cast during blackout):

| Scenario | Copier's score | Predictions that beat them |
|---|---|---|
| uniform voting | **99.99%** of max | 2.9 of 720 |
| one bloc at 30% | **100.00%** of max | 0.8 of 720 |

As specified, the Mandate board is a test of whether you remembered to refresh the
page. It measures no skill at all.

### Fix — eligibility requires an early lock

**Only entries committed before T+12h score on the Mandate board.** Entries locked
later, and drafts auto-committed at seal, still compete for the Trifecta — they just
do not appear on this board.

That converts it from a copying contest into a genuine forecasting contest, because
an early lock carries real risk:

| Scenario | T+12 leader keeps same 3 digits | keeps exact order |
|---|---|---|
| uniform voting | 17.8% | 5.5% |
| one bloc at 30% | 26.0% | 14.0% |
| two blocs 30/20 | 46.3% | 46.3% |

**This also repairs something already broken in the design.** Under v2.1, manual
lock-in is strategically *pointless* — auto-commit at seal performs the identical
transition, so no rational player ever locks early; they edit until the deadline.
Mandate eligibility gives early commitment a purpose and creates the game's first
real risk/reward decision:

> **Lock early** to compete on the Mandate board, accepting you can no longer react
> — or **stay flexible** to chase the Trifecta, and forfeit the Mandate.

*Note this does not violate the "no timestamp tie-break" invariant. That invariant
governs the winner set for the number; it says timestamps never eliminate equal
predictions. An opt-in board with an entry deadline is a different thing — no
player's Trifecta standing is affected by when they committed.*

---

## 3. What players actually see

Rank the board by `mandate_score`, but **show the interpretable number**: the share
of all votes the player's three digits commanded.

> *"Your slate commanded **51.1%** of the vote."*

| Scenario | Winning slate | Median slate | Worst slate |
|---|---|---|---|
| uniform voting | 30.1% | 30.0% | 29.8% |
| one bloc at 30% | 51.1% | 21.0% | 20.9% |
| two blocs 30/20 | 65.0% | 35.0% | 14.9% |
| three blocs | 73.4% | 31.3% | 11.4% |

This is well-defined in every round. Under coordination it separates sharply; under
uniform voting everyone sits near 30%, which is *honest* — in a round where nobody
organised, no slate commanded anything. Displaying share (readable) while ranking by
weighted score (fine-grained) gets both properties.

---

## 4. The question this raises: does digit distance still belong?

Worth confronting directly. Digit distance treats digits as **magnitudes** — `|5-4| = 1`,
so predicting 4 when 5 won is "almost right."

Under ruleset V1.1 that is no longer what a digit is. A digit is a **faction
identity** — a bloc that campaigned for votes. Digit 4 is not "nearly" digit 5; it
is a different group of people who lost. The numeric adjacency of the labels carries
no game meaning, and scoring on it measures something the game no longer models.

Distance is a holdover from the v2.1 framing where the outcome was *a number*. Under
V1.1 the outcome is *a ranked slate of three blocs*, and the tiers that describe it
honestly are Trifecta / Boxed / two-of-three / one-of-three — membership and order,
not arithmetic proximity.

**Options:**

| | Approach | Consequence |
|---|---|---|
| A | Keep distance as the winner rule; add both boards on top | Smallest change; F14 persists in the raw score but is masked by the BOXED tier |
| B | **Winner = Trifecta tier; rank below it by Mandate score; drop distance** | Coherent with what V1.1 actually is; one metric fewer; loses the intuitive "you were 1 away" |
| C | Keep distance for flavour on the result card only, never for ranking | Compromise; two numbers to explain |

**Recommendation: B**, with distance retired. It removes a metric, removes F14 at the
root rather than masking it, and every remaining number means something concrete
about the round. If the intuitive closeness of "you were one away" turns out to
matter in playtesting, C is a cheap retreat.

---

## 5. Net effect on open questions

- **N1** — settled: predictions must be three distinct digits (720 space).
- **N2** — resolved by the BOXED tier, and dissolved entirely under option B.
- **F13** (no retention loop) — substantially addressed. Two boards rewarding
  different skills, a named top prize, and a real early-lock decision is the
  beginning of an actual retention loop.
- **New** — pick the Mandate eligibility deadline. T+12h is a reasonable default;
  it is a tunable game parameter, not a structural choice.
