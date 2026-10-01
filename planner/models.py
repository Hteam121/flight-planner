"""Shared data types passed between pipeline layers."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from typing import Any


@dataclass(frozen=True)
class DatePair:
    depart: date
    ret: date  # date the return flight departs
    nights: int
    pto_cost: int  # optimistic estimate (no flight times known yet)

    @property
    def pto_efficiency(self) -> float:
        return self.nights / max(self.pto_cost, 1)

    @property
    def key(self) -> tuple[str, str]:
        return (self.depart.isoformat(), self.ret.isoformat())


@dataclass
class Leg:
    from_airport: str
    to_airport: str
    depart: datetime
    arrive: datetime
    duration_min: int
    plane: str = ""


@dataclass
class Itinerary:
    origin: str
    destination: str
    depart_date: date
    return_date: date
    price: int
    currency: str
    airlines: list[str]  # display names, e.g. "Qatar Airways"
    airline_codes: list[str]  # IATA codes when resolvable, e.g. "QR"
    stops: int
    total_duration_min: int
    depart_dt: datetime
    arrive_dt: datetime
    layover_airports: list[str]
    layover_max_min: int
    overnight_layover: bool
    legs: list[Leg]
    source: str
    fetched_at: datetime
    deep_link: str
    # Filled in by the scorer / calendar re-evaluation:
    nights: int = 0
    pto_cost: int = 0
    comfort_penalty: float = 0.0
    value_score: float = 0.0
    pareto: bool = False
    extras: dict[str, Any] = field(default_factory=dict)

    @property
    def pair_key(self) -> tuple[str, str]:
        return (self.depart_date.isoformat(), self.return_date.isoformat())

    def to_json(self) -> dict[str, Any]:
        d = asdict(self)
        for k in ("depart_date", "return_date", "depart_dt", "arrive_dt", "fetched_at"):
            d[k] = getattr(self, k).isoformat()
        for leg in d["legs"]:
            leg["depart"] = leg["depart"].isoformat()
            leg["arrive"] = leg["arrive"].isoformat()
        return d

    @classmethod
    def from_json(cls, d: dict[str, Any]) -> "Itinerary":
        d = dict(d)
        d["depart_date"] = date.fromisoformat(d["depart_date"])
        d["return_date"] = date.fromisoformat(d["return_date"])
        for k in ("depart_dt", "arrive_dt", "fetched_at"):
            d[k] = datetime.fromisoformat(d[k])
        d["legs"] = [
            Leg(
                from_airport=l["from_airport"],
                to_airport=l["to_airport"],
                depart=datetime.fromisoformat(l["depart"]),
                arrive=datetime.fromisoformat(l["arrive"]),
                duration_min=l["duration_min"],
                plane=l.get("plane", ""),
            )
            for l in d["legs"]
        ]
        return cls(**d)
