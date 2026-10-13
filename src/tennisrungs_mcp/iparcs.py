"""Separate adapter boundary. No private ACTIVE Net endpoints or checkout writes."""
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class CourtSlot:
    resource_id: int
    start: str
    end: str
    timezone: str = "America/New_York"


class CourtAvailabilityAdapter(Protocol):
    def availability(self, resource_ids: list[int], start: str, end: str) -> list[CourtSlot]: ...


def court_url(resource_id: int) -> str:
    if isinstance(resource_id, bool) or not isinstance(resource_id, int) or resource_id <= 0:
        raise ValueError("Resource ID must be positive")
    # Court-only deep link. Date/time query contract has not been established.
    return f"https://anc.apm.activecommunities.com/atlantadprca/reservation/landing/search/detail/{resource_id}"
