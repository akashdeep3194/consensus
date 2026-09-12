# Design Evaluation — Project Consensus 3D v2.1

Review of `project_vision/Project_Consensus_3D_v2_1_Implementation_Design.pdf` (10pp, 12 Sep 2026).

## Verdict

The **systems** design is strong and unusually disciplined. The correctness posture
(PostgreSQL authoritative, Redis strictly derived, durable ack only after commit,
deterministic resolver, immutable submission set) is the right spine, and most
teams get this wrong. Sections 4–6 are close to build-ready.

The **game** design had one unresolved problem larger than any engineering issue in
the document. **It has since been resolved** by replacing the outcome engine — see
F1 below and `00-ruleset.md`. The remaining twelve findings are implementation
concerns and all still stand.

Findings are graded:

- 🔴 **Blocking** — resolve before writing code in that area
- 🟠 **Important** — will cause rework or an incident if left
- 🟡 **Decide** — a legitimate choice the document never makes

---

## F1 ✅ RESOLVED — the coordination cliff

**Status: fixed in ruleset V1.1 by replacing the outcome engine.** Recorded here
because it is why the engine changed.

### The finding

D'Hondt over 3 slots did not degrade gracefully as coordination rose — it snapped
at a closed-form threshold. With the leading digit holding share *s* and the other
nine splitting the remainder evenly (`analysis/dhondt_equilibrium.py`, exact
rational arithmetic):

| Leading digit's share | Outcome shape |
|---|---|
| < 18.2% (= 2/11) | `ABC` three distinct digits |
| 18.2% – 25% | `AAB` |
| **> 25% (= 1/4)** | **`AAA` repdigit — trivially predictable** |

The problem was not the threshold but the incentive gradient. Because vote and
prediction are independent, and prediction frequency never changes the outcome,
**joining the visibly leading digit cost a player nothing.** There was no
counter-pressure toward fragmentation at all, so the game drifted to a repdigit on
its own: everyone votes *k*, outcome is *kkk*, everyone predicts *kkk*, everyone
wins, winning conveys nothing.

### The resolution

The winning number is now the **three most-voted digits, ranked by count, always
distinct**, ties to the lower digit (`00-ruleset.md` §2). A repdigit is no longer
representable, so the failure mode is gone structurally rather than mitigated.

It is also a large simplification: ranking needs **integer comparison only** — no
D'Hondt, no quotients, no `Fraction`, no float-drift risk. The v2.1 requirement for
exact rational arithmetic (§2.2) disappears entirely.

### What coordination now buys

Coordination is retained as a deliberate core mechanic. The rules make that safe
(`analysis/outcome_rule.py`, 50k voters, 6k rounds):

| Organised | Outcomes still live | Best single guess |
|---|---|---|
| Nobody | 720 of 720 | 0.3% |
| One bloc at 30% | **72** | 1.9% |
| Two blocs, 30% + 20% | **8** | 13.2% |
| Three blocs, 30/20/12% | **1** | 100% |

A single bandwagon — the natural, self-reinforcing behaviour that broke D'Hondt —
now locks only position 1 and leaves 72 outcomes live. That is the interesting
case, and it is where most rounds will sit.

### Residual risk 🟡

Three separately organised blocs holding *deliberately different* sizes still lock
the number completely. This is far harder to reach than a single bandwagon and is
arguably a legitimate, impressive play rather than a failure — but it should be
watched:

- the lock is **visible** in the public standings for 23 hours, so it invites
  disruption, and only a modest fourth bloc is needed to break it
- the blackout hour now carries real weight — it is the one window where a lock
  cannot be verified before sealing
- **track it in production**: alert when the outcome space falls below ~10 live
  possibilities before blackout. It is a game-health metric, not a bug

> The v2.1 D'Hondt math was correct — all three worked examples in §2.3 reproduce
> exactly, including the zero-vote `000` case (`analysis/dhondt_verify_examples.py`).
> The problem was never correctness; it was equilibrium.

## F2 🔴 The stated load target is aimed at the wrong phase

§9.1 targets "500,000 concurrent submissions in the final 10 minutes."

But the design has already engineered that spike away: drafts are durable for 24
hours and §1.2 auto-commits every valid remaining draft at seal. A player who does
nothing still participates. There is no deadline rush to build for — the
architecture's own strength makes the stated target largely fictional.

The real concurrency wall is **reveal fanout at T+30h**, where up to 500k clients
simultaneously request a result. That is a read/fanout problem, not a write
problem, and it needs a completely different solution (see `02-tech-stack.md` §
Reveal). The three loads actually worth benchmarking:

1. Draft writes — spread over 24h, low peak, but must be durable-acked
2. Sealing — one bulk job over up to 500k rows, bounded by DB throughput
3. **Reveal reads — genuine 500k-concurrent spike**

Retarget §9.1 accordingly.

---

## F3 🟠 Merkle root published at reveal proves nothing

§8.3 says publish the commitment root *at reveal* (T+30h). The root is computed at
seal (T+24h) and the operator controls both the data and the clock. A root
disclosed at the same moment as the result it commits to provides no
non-manipulation guarantee whatsoever.

**Fix:** publish the root at **T+24h, immediately on seal**, before resolution
begins — and ideally to somewhere the operator cannot rewrite (a public append-only
log, a signed feed, a third-party timestamp service). This is cheap and it is the
difference between real and decorative auditability.

Secondary: the leaf preimage in §8.3 is
`round_id | submission_id | prediction | vote | commit_sequence`. Prediction × vote
is only 10,000 combinations, so any leaf is brute-forceable — individual entries
are not private, even before reveal. Fine if entries are considered public (the
histogram is published anyway), but it must be a stated decision, and if you ever
want private entries, leaves need per-submission randomness.

## F4 🟠 Merkle root reproducibility depends on an unspecified ordering

§8.3 hashes leaves "in commit order," and §5.4 makes `commit_sequence` authoritative
DB order. For manual lock-ins that is well-defined. For the up-to-500k drafts
auto-committed at seal, `commit_sequence` would be whatever arbitrary order the
batch job inserted rows — which is **not reproducible** by an independent auditor,
and not stable across a crash-and-restart of the sealing job.

That directly breaks acceptance criterion §9.4 ("an independent resolver can
reproduce... from the committed dataset").

**Fix:** seal-time `commit_sequence` must be a *specified deterministic function of
the data*, e.g. ordered by `(draft.updated_at, user_id)`. Write it into the spec
as canonicalization, alongside field order and encoding.

## F5 🟠 "Atomically finalize every valid remaining draft" conflicts with "restartable"

§5.3 asks for both atomic sealing and crash-restartability over what may be 500k
rows. One transaction gives atomicity but no partial restart, long lock hold and
WAL pressure; chunked commits give restartability but not atomicity.

**Resolution:** the atomic moment is the **status transition**, not the data
movement. `OPEN → SEALING` flips in one small transaction and establishes the
authoritative cutoff. Materialization then runs as idempotent chunked
`INSERT … SELECT … ON CONFLICT DO NOTHING` batches, followed by a reconciliation
check (valid drafts counted == submissions created), and only then `→ SEALED`.
Restart at any point is safe because every chunk is idempotent and the cutoff
already happened.

## F6 🟠 "Valid remaining draft" is undefined, and it changes the tally

§5.3 auto-commits "every valid remaining draft," but the §4.3 schema declares no
`NOT NULL` and no `CHECK` constraints. A draft with a prediction but no vote — or a
vote but no prediction — is a real state a player can reach, and whether those
drafts commit directly alters `C[d]` and therefore the winning number.

**Fix:** define validity in §1.3 as an invariant (both fields present and in range),
and enforce it in the schema, not only in the API — the document declares Postgres
the authority, so the constraints belong there:

```sql
prediction CHAR(3) CHECK (prediction ~ '^[0-9]{3}$')
vote       SMALLINT CHECK (vote BETWEEN 0 AND 9)
```

Also record discarded invalid drafts at seal, so the count is auditable.

## F7 🟠 Rounds overlap, and nothing in the document acknowledges it

The lifecycle is 24h of entry plus 6h of resolution = **30 hours**, but
`cycle_number` implies a regular cadence. If a round opens daily, round N is still
resolving 6 hours into round N+1. That is workable, but it means:

- "One account may have at most one active *round* entry" (§1.3) must be scoped
  per-round, not globally — a player will legitimately hold a committed entry in
  round N and a draft in round N+1 simultaneously
- `GET /rounds/current` is ambiguous when two rounds are live
- The console must render two rounds in different phases at once

Decide the cadence explicitly: daily-overlapping, or every 30h+ non-overlapping.

## F8 🟡 Blackout has a side channel — and it now carries real weight

§7.3 says stop serving live tallies during blackout. To hold, every aggregate
endpoint must return the **identical frozen T+23 snapshot** — same bytes, same
ETag — rather than erroring or varying, or response size and timing leak state.
Personal endpoints must not expose rank either.

The second half of this finding is now **answered by design**: the frozen snapshot
advantages organised blocs, and under V1.1 that is intended. Coordination is a core
mechanic (`00-ruleset.md` §5), and the dark hour is the one window where a bloc
lock cannot be verified before sealing — which is precisely what keeps a
three-bloc lock contestable (F1, residual risk). Blackout is load-bearing game
design now, not just an information-policy detail.

## F9 🟠 No identity model exists — and it now defines the boundary of fair play

*Raised from "decide" to "important" by the V1.1 change.* Under v2.1 this was one
control among several. Now that organising a voting bloc is **legitimate, encouraged
gameplay**, the only thing separating a real coalition from one person running
10,000 accounts is the identity model — and the document specifies none. No signup
method, no friction, no verification.

Coordination being permitted makes sybil resistance *more* load-bearing, not less:
the rules invite players to accumulate voting power, so the system must ensure that
power is accumulated by persuasion rather than by scripting.

V1 needs *a* decision, and a cheap one is available: OAuth (Google/Apple) only, one
account per verified provider identity, Turnstile at signup, per-IP/ASN registration
rate limits, and an anomaly path that can **void entries without touching the
algorithm** (voiding is a data action; the resolver stays pure).

## F10 🟡 `/leaderboard` cannot exist during a round

Predictions are unrankable before the winning number exists, so during OPEN the
"leaderboard" can only be the vote distribution / prediction popularity — which is
precisely the coordination signal from F1, on the highest-traffic endpoint in the
system. The naming hides that.

Split it: `GET /rounds/{id}/metrics` (live aggregates, frozen in blackout, possibly
removed entirely per F1) and `GET /rounds/{id}/results` (post-reveal rankings).

## F11 🟡 Redis outage policy is unstated for rate limits

§6.2 says a Redis outage degrades derived views. But rate limits live in Redis
(§4.1): on outage, does the API fail open (bot flood) or closed (nobody plays)?
Recommend **fail open with alarm** — Turnstile and the unique-entry constraint
still hold the line — but state it.

## F12 🟡 API surface is missing its non-game half

Absent from §7.2: authentication, user profile/history, round list/pagination,
server time (the console must never trust a client clock, §6.4), health/readiness,
an operator surface for forcing or inspecting transitions, and any push channel for
reveal.

## F13 🟡 No retention loop is defined

The document specifies a correct round but never says what a win *is* — no prize,
score, streak, rank, or season. For a "massive multiplayer" game this is the
difference between a launch and a product. Out of scope for the systems design, but
it belongs on the roadmap before Phase 6, and F1 makes it urgent: if everyone wins,
no reward scheme can mean anything.

## F14 ✅ RESOLVED — the order penalty

**Status: fixed by retiring digit distance (S1).** Recorded because it is why the
scoring model changed.

Under distance scoring the winning number always had three distinct digits and rank
was the whole skill, so "right digits, wrong order" was the commonest near-miss —
and it was punished brutally. For winner `527`, three of the five permutations of
the winning digits scored distance 10, against a mean of 8.7 over all 720 valid
predictions, while an unrelated `427` scored 1. A player who identified every
winning digit and misjudged only the order finished behind one who guessed wrong.

Resolved two ways at once (`00-ruleset.md` §3):

- **BOXED** is now a named tier on Board A — right three digits, any order — so the
  result is recognised rather than buried under a bad number.
- **The Mandate board's penalty for misordering is exactly the vote margin between
  the two digits**, so misreading a near-tie barely costs anything while misreading
  a landslide costs a lot. The penalty is proportional to how hard the call was,
  which digit distance could never express.

---

## What the document gets right, and should not be revisited

- Postgres-authoritative with Redis strictly derived (§4.1, §4.2) — correct, and the
  reasoning in §4.2 is exactly right
- Durable acknowledgement only after commit (§5.1)
- ~~Exact rational arithmetic (§2.2)~~ — no longer needed under V1.1; ranking is integer comparison
- ~~Digit distance scoring (§3)~~ — retired under S1; replaced by result tiers plus the Mandate board
- Permanent lower-digit tie-break, carried into V1.1 — makes `012` fall out of the ordinary path
- No timestamp tie-break among equal predictions (§1.3, §3.1)
- Optimistic versioning on drafts (§5.2)
- Idempotency keys on lock-in (§6.3)
- UTC `timestamptz`, DB-authoritative boundaries (§6.4)
- `ruleset_version` + `algorithm_version` (§8.1)
- The mandatory test matrix (§9.2) — adopt as written
