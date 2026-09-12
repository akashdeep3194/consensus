# Ruleset V1.1 — Authoritative Game Rules

Supersedes §1–§3 of the v2.1 design document. Everything else in v2.1 stands.

`ruleset_version = "1.1"` · `algorithm_version = "1.1.0"`

## Change from v2.1

| | v2.1 | **V1.1** |
|---|---|---|
| Outcome engine | D'Hondt allocation across 3 positions | **Rank the three most-voted digits** |
| Winning number | any of 1000, repdigits common | **always 3 distinct digits — 720 possible** |
| Arithmetic | rational (`Fraction`), to avoid float drift | **integer comparison only** |
| Prediction space | 1000 (`000`–`999`) | **720 — distinct digits only** |
| Scoring | digit distance, single winner set | **two boards: tiers + position-weighted mandate** |
| Tie-break | permanent lower-digit | unchanged — **lower digit ranks higher** |
| Zero-vote case | `000` | **`012`** |
| Coordination | permitted but degenerate (see F1) | **core mechanic, structurally safe** |

The D'Hondt engine collapsed to a repeated digit (`777`) whenever any single bloc
passed 25% of the vote — and since joining the visible leader cost a player
nothing, the game drifted there on its own. Ranking distinct digits removes that
failure mode structurally: a repdigit is no longer representable.

## 1. Core rules

Each player controls two independent choices per round:

- a **prediction** — three **distinct** digits, ordered (720 valid predictions)
- a **vote** — one digit, `0–9`

Predictions carry distinct digits because the winning number always does; allowing
`111` would only sell players a ticket that cannot win.

Votes determine the collective outcome. Predictions are scored against it afterward.

## 2. Outcome engine

```
counts[d] = committed vote count for digit d, d in 0..9

winning_number = first three of
    sort(digits 0..9) by (count descending, digit ascending)
```

That is the whole engine. Integer comparison, no division, no rational arithmetic,
no float. The outcome is a pure function of the count vector.

**Tie-break.** Equal counts resolve to the lower digit, permanently and at every
position. This is the only tie-break in the system.

**Zero votes.** Every count is 0, so every comparison ties and the lower digits
win in order: the result is `012`. No special case is needed.

### Examples

| Votes | Winning number | Why |
|---|---|---|
| `9:500  0:400  3:300` | `903` | straight count order |
| `5:100  2:100  7:50` | `257` | 2 and 5 tie at 100 — lower digit ranks higher |
| all digits `0` | `012` | every count ties; lower digits win in order |

## 3. Scoring — two boards

Digit distance is **retired**. Under V1.1 a digit is a faction identity, not a
magnitude: digit 4 is not "nearly" digit 5, it is a different bloc that lost. The
numeric adjacency of the labels carries no game meaning, so scoring on it measured
something the game does not model.

### 3.1 Board A — The Number

Who called the outcome. This is where the prize sits.

| Tier | Condition |
|---|---|
| 🏆 **TRIFECTA** | prediction equals the winning number exactly, in order |
| 📦 **BOXED** | same three digits as the winner, different order |
| **TWO** | exactly two of the prediction's digits are in the winning set |
| **ONE** | exactly one |
| **NONE** | none |

**Every player in a tier shares that tier.** There is no intra-tier ranking and no
timestamp tie-break — if 694 players hit the Trifecta, all 694 are Trifecta winners.

### 3.2 Board B — The Mandate

Who read the electorate. Ranked by a **position-weighted vote total**:

```
mandate_score(P) = 3·C[P₁] + 2·C[P₂] + 1·C[P₃]
```

where `C[d]` is the committed vote count for digit `d`.

Three properties make this the right metric:

1. **Its unique maximum is the Trifecta.** By the rearrangement inequality, pairing
   the largest count with the largest weight is optimal, so the top of the Mandate
   board is always the true winning number in exact order.
2. **Misordering costs exactly the margin you misread.** Swapping two positions
   costs the difference in those digits' vote counts — so misordering two near-tied
   digits barely hurts, while misordering a landslide hurts a lot. The penalty is
   proportional to how hard the call actually was.
3. **It ranks finely.** Raw unweighted summation is order-blind, so it can never
   exceed one rank per digit *set* — a hard cap of `C(10,3) = 120`. Weighting always
   separates strictly further, reaching ~670 of 720 at realistic vote volumes. (The
   exact figure depends on the count vector; the 120 cap is structural.)

**Eligibility: only entries committed before T+12h score on this board.** Without
that cutoff the board is a copying contest — the vote distribution is public, so a
player who checks the standings just before blackout scores 99.99% of maximum and
is beaten by roughly one prediction in 720. An early lock carries genuine risk: the
slate leading at T+12h keeps the same three digits only 18–46% of the time.

Late lock-ins and drafts auto-committed at seal still compete for the Trifecta —
they simply do not appear on this board.

> This does not violate the no-timestamp-tie-break invariant. That invariant governs
> the winner set for the number, and it is untouched: no player's Board A standing
> depends on when they committed. Board B is an opt-in contest with an entry
> deadline, which is a different thing.

### 3.3 Why two boards and not one merged ranking

The two metrics genuinely disagree, and the disagreement is not a rounding error.
For a winner of `738` with counts `7:175,000 · 3:125,000 · 8:25,000`, **49
predictions holding only two of the three winning digits outscore the worst BOXED
permutation**. A single merged ranking would therefore place a partial hit above a
player who had every winning digit — which is indefensible.

They measure different things and must be reported separately: Board A is *did you
call the result*, Board B is *did you read the electorate*.

### 3.4 What the player sees

Board B ranks by `mandate_score`, but the number displayed is the interpretable one
— the share of all votes the player's three digits commanded:

> *"Your slate commanded **51.1%** of the vote."*

Well-defined in every round. Under coordination it separates sharply (winning slate
~51% at one bloc, ~73% at three); with no coordination everyone sits near 30%, which
is honest — in a round where nobody organised, no slate commanded anything.

### 3.5 Feedback, not scoring

The prediction histogram and the vote-outcome story ("your digit finished 2nd") are
descriptive. They are computed only after the winning number is fixed and can never
feed back into outcome resolution.

## 4. Non-negotiable invariants

- One account holds at most one entry **per round**.
- A committed entry can never be edited, withdrawn or replaced.
- Prediction and vote are independent; a vote need not appear in the prediction.
- Prediction frequency never changes the winning number or any distance.
- Vote choice affects only the collective outcome.
- All players in a result tier share that tier; there is no intra-tier ranking.
- **The winning number always has three distinct digits.**
- **A prediction must also be three distinct digits**, or it is invalid.
- A draft is valid only if both prediction and vote are present and in range;
  invalid drafts are discarded at seal and counted in the audit record.

## 5. Coordination is a game mechanic

Social coordination — organising blocs, campaigning for a digit, planning in public
— is **intended gameplay**, not an exploit. The live vote distribution is published
during the OPEN phase precisely so that it can be played against.

The rules make this safe to permit:

| Organised | Positions locked | Outcomes still live | Nature of the play |
|---|---|---|---|
| Nobody | none | 720 of 720 | pure prediction |
| One bloc ≥ ~20% | position 1 | **72** | the common, interesting case |
| Two blocs, distinct sizes | positions 1–2 | **8** | a real alliance |
| Three blocs, ordered sizes | all three | **1** | a genuine, visible feat |

Locking the whole number requires three separately organised blocs holding
*deliberately different* sizes, in public, for 23 hours. That is an achievement
rather than an accident — and it is contestable: the standings are visible to
everyone, so a lock invites disruption, and the final hour is dark.

The anti-abuse boundary remains automated and fraudulent participation — sybil
accounts, bots, technical circumvention — never strategic coalition behaviour.

## 6. Round lifecycle

Unchanged from v2.1 §1.1.

| Phase | Time | Behaviour |
|---|---|---|
| Open | T+0 → T+23h | Drafts editable, manual lock-in, live public metrics |
| Blackout | T+23h → T+24h | Live metrics hidden; submissions still accepted |
| Sealing | T+24h | No mutations; valid remaining drafts auto-commit |
| Resolution | T+24h → T+30h | Immutable tally, ranking, winners, audit |
| Reveal | T+30h | Winning number, histogram, personal result, audit |

Manual lock-in and deadline auto-lock are the same transition: `DRAFT → COMMITTED`.
Only the initiator differs.
