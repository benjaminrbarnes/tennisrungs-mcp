from dataclasses import asdict, dataclass, field
from typing import Any, Literal


class IntegrationError(Exception):
    """Safe diagnostic. Do not attach response bodies or credential material."""


class AuthenticationRequired(IntegrationError):
    pass


class UnsupportedContract(IntegrationError):
    pass


@dataclass(frozen=True)
class Ladder:
    ladder_id: int
    name: str
    team_id: int | None = None


@dataclass(frozen=True)
class Match:
    challenge_id: int | None
    ladder_name: str
    opponent: str
    status: Literal["PROPOSED", "ACCEPTED", "PENDING", "UNKNOWN"]
    scheduled_text: str | None = None
    venue: str | None = None
    opponent_team_id: int | None = None
    ladder_id: int | None = None


@dataclass(frozen=True)
class Proposal:
    challenge_id: int
    accept_team_id: int
    proposer: str
    ladder_name: str
    scheduled_text: str
    venue: str | None


@dataclass(frozen=True)
class Ranking:
    team_id: int
    name: str
    rank: str
    rating: str
    record: str
    points: str
    streak: str


@dataclass(frozen=True)
class HistoryRow:
    date: str
    opponent: str
    opponent_team_id: int | None
    result: str
    score: str


@dataclass(frozen=True)
class ReadResult:
    source_url: str
    observed_at: str
    rows: list[Any]
    complete: bool
    warnings: list[str] = field(default_factory=list)

    def to_dict(self):
        return asdict(self)
