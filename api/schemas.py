"""Request and response models. Validation happens here and again in the engine."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class DraftIn(BaseModel):
    prediction: str | None = Field(None, description="Three distinct digits, e.g. 527")
    vote: int | None = Field(None, ge=0, le=9)
    version: int | None = Field(None, description="Omit to create; required to update")

    @field_validator("prediction")
    @classmethod
    def _distinct_digits(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if len(v) != 3 or not v.isdigit() or len(set(v)) != 3:
            raise ValueError("prediction must be three distinct digits")
        return v


class RoundOut(BaseModel):
    round_id: UUID
    cycle_number: int
    status: str
    opens_at: datetime
    mandate_deadline: datetime
    blackout_at: datetime
    seals_at: datetime
    reveals_at: datetime
    winning_number: str | None = None
    commitment_root: str | None = None
    server_time: datetime


class EntryOut(BaseModel):
    committed: bool
    prediction: str | None = None
    vote: int | None = None
    version: int | None = None
    updated_at: datetime | None = Field(
        None, description="Draft only — when it was last edited, for the Mandate cutoff"
    )
    commit_sequence: int | None = None
    mandate_eligible: bool | None = None
    committed_at: datetime | None = None


class RoundSummaryOut(BaseModel):
    round_id: UUID
    cycle_number: int
    opens_at: datetime
    reveals_at: datetime
    winning_number: str
    commitment_root: str


class RoundHistoryOut(BaseModel):
    rounds: list[RoundSummaryOut]
    next_before_cycle: int | None = None


class TierCount(BaseModel):
    tier: str
    players: int


class ResultOut(BaseModel):
    round_id: UUID
    winning_number: str
    counts: list[int]
    total_votes: int
    full_ranking: list[int]
    tier_histogram: list[TierCount]
    commitment_root: str
    algorithm_version: str
    mandate_board: list["MandateRow"]


class MandateRow(BaseModel):
    rank: int
    handle: str
    prediction: str
    mandate_score: int
    vote_share: float
    tier: str


class MyResultOut(BaseModel):
    round_id: UUID
    winning_number: str
    prediction: str
    vote: int
    tier: str
    points: int
    streak: int
    mandate_score: int
    mandate_rank: int | None
    vote_share: float
    vote_finished: int | None = Field(
        None, description="Where the player's voted digit finished, 1-10"
    )
