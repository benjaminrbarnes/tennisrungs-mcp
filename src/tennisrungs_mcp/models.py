from dataclasses import asdict, dataclass, field
from typing import Any, Literal


class IntegrationError(Exception):
    """Safe diagnostic. Do not attach response bodies or credential material."""


class AuthenticationRequired(IntegrationError):
    pass


class UnsupportedContract(IntegrationError):
    pass


class SafetyError(IntegrationError):
    pass


class UnknownOutcome(IntegrationError):
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


@dataclass(frozen=True)
class ProposalInput:
    team_id: int
    ladder_id: int
    location_id: int
    match_date: str  # ISO date, formatted to site convention at transport boundary
    hour: int
    minute: int
    am_or_pm: str
    preferred_location: str
    show_email: bool = False


@dataclass(frozen=True)
class ScoreInput:
    challenge_id: int
    ladder_id: int
    winner_team_id: int
    score: str
    outcome: str = "PlayedThrough"


@dataclass(frozen=True)
class WriteResult:
    operation_key: str
    state: str
    challenge_id: int | None = None
    message: str = ""

    def to_dict(self):
        return asdict(self)
