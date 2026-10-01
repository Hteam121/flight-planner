"""Source protocols. Swap implementations (fast-flights, SerpApi, Amadeus) behind these."""

from __future__ import annotations

from datetime import date
from typing import Protocol

from ..models import Itinerary


class ItinerarySource(Protocol):
    name: str

    def fetch_round_trip(self, origin: str, dest: str, depart: date, ret: date) -> list[Itinerary]: ...


class PriceHintSource(Protocol):
    """Cheap, possibly stale per-date-pair price hints used only to rank pairs for verification."""

    name: str

    def price_hints(self, origin: str, dest: str, months: list[str], nights: list[int]) -> dict[tuple[str, str], tuple[int, str, int]]:
        """Return {(depart_iso, return_iso): (price, airline_code, transfers)}."""
        ...
