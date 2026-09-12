"""Round resolution — the whole game, as a pure function.

`resolve()` takes the immutable committed submission set and returns everything
the reveal needs: winning number, per-player tiers, both boards, the audit ledger
and the commitment root. No I/O, no clock, no database.

Mandate eligibility is passed in per submission rather than computed here: the
engine must not know about wall-clock time (ruleset V1.1 §3.2 gates on T+12h,
which is the caller's business).
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from fractions import Fraction

from engine.canonical import canonical_submission, leaf_hash, merkle_root
from engine.mandate import mandate_score, vote_share
from engine.rank import full_ranking, validate_prediction, validate_vote, winning_number
from engine.tiers import Tier, tier_of
from engine.version import ALGORITHM_VERSION, RULESET_VERSION


@dataclass(frozen=True, slots=True)
class Submission:
    """One immutable committed entry."""

    round_id: str
    submission_id: str
    user_id: str
    prediction: tuple[int, int, int]
    vote: int
    commit_sequence: int
    mandate_eligible: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "prediction", validate_prediction(self.prediction))
        validate_vote(self.vote)


@dataclass(frozen=True, slots=True)
class PlayerResult:
    submission_id: str
    user_id: str
    prediction: tuple[int, int, int]
    vote: int
    tier: Tier
    mandate_score: int
    vote_share: Fraction
    mandate_rank: int | None  # None when not eligible for Board B


@dataclass(frozen=True, slots=True)
class AuditSlot:
    """One position of the outcome, with the margin that decided it."""

    position: int
    digit: int
    votes: int
    runner_up_digit: int
    runner_up_votes: int
    margin: int
    decided_by_tie_break: bool


@dataclass(frozen=True, slots=True)
class RoundResult:
    round_id: str
    winning_number: tuple[int, int, int]
    counts: tuple[int, ...]
    total_votes: int
    full_ranking: tuple[int, ...]
    players: list[PlayerResult]
    tier_histogram: dict[Tier, int]
    mandate_board: list[PlayerResult]
    audit: list[AuditSlot]
    commitment_root: str
    ruleset_version: str = RULESET_VERSION
    algorithm_version: str = ALGORITHM_VERSION
    winners: list[PlayerResult] = field(default_factory=list)


def tally(submissions: Sequence[Submission]) -> tuple[int, ...]:
    """Committed vote counts per digit."""
    counts = [0] * 10
    for s in submissions:
        counts[s.vote] += 1
    return tuple(counts)


def _audit(counts: Sequence[int], ranking: Sequence[int]) -> list[AuditSlot]:
    slots = []
    for i in range(3):
        d = ranking[i]
        runner = ranking[i + 1]
        margin = counts[d] - counts[runner]
        slots.append(
            AuditSlot(
                position=i + 1,
                digit=d,
                votes=counts[d],
                runner_up_digit=runner,
                runner_up_votes=counts[runner],
                margin=margin,
                # equal counts mean the lower-digit rule, not the vote, decided it
                decided_by_tie_break=(margin == 0),
            )
        )
    return slots


def resolve(round_id: str, submissions: Sequence[Submission]) -> RoundResult:
    """Resolve a sealed round. Deterministic and order-independent."""
    counts = tally(submissions)
    winner = winning_number(counts)
    ranking = full_ranking(counts)

    players = [
        PlayerResult(
            submission_id=s.submission_id,
            user_id=s.user_id,
            prediction=s.prediction,
            vote=s.vote,
            tier=tier_of(s.prediction, winner),
            mandate_score=mandate_score(s.prediction, counts),
            vote_share=vote_share(s.prediction, counts),
            mandate_rank=None,
        )
        for s in sorted(submissions, key=lambda s: s.commit_sequence)
    ]

    histogram = dict.fromkeys(Tier, 0)
    for p in players:
        histogram[p.tier] += 1

    # Board B: eligible entries only, ranked by weighted score. Equal scores share
    # a rank (competition ranking) — consistent with the no-tie-break invariant.
    eligible_ids = {s.submission_id for s in submissions if s.mandate_eligible}
    board = sorted(
        (p for p in players if p.submission_id in eligible_ids),
        key=lambda p: -p.mandate_score,
    )
    ranked_board, prev_score, prev_rank = [], None, 0
    for i, p in enumerate(board, start=1):
        rank = prev_rank if p.mandate_score == prev_score else i
        ranked = PlayerResult(
            p.submission_id, p.user_id, p.prediction, p.vote,
            p.tier, p.mandate_score, p.vote_share, rank,
        )
        ranked_board.append(ranked)
        prev_score, prev_rank = p.mandate_score, rank

    by_id = {p.submission_id: p for p in ranked_board}
    players = [by_id.get(p.submission_id, p) for p in players]

    root = merkle_root(
        leaf_hash(
            canonical_submission(
                s.round_id, s.submission_id, s.prediction, s.vote, s.commit_sequence
            )
        )
        for s in sorted(submissions, key=lambda s: s.commit_sequence)
    )

    return RoundResult(
        round_id=round_id,
        winning_number=winner,
        counts=counts,
        total_votes=sum(counts),
        full_ranking=ranking,
        players=players,
        tier_histogram=histogram,
        mandate_board=ranked_board,
        audit=_audit(counts, ranking),
        commitment_root=root,
        winners=[p for p in players if p.tier is Tier.TRIFECTA],
    )
