"""Layer 3: real itineraries from Google Flights via fast-flights.

Round-trip queries return the *outbound* options with the round-trip price (same as
the first page of Google Flights). Comfort is scored on the outbound leg set.
"""

from __future__ import annotations

import random
import time
from datetime import date, datetime

from fast_flights import FlightQuery, FlightsNotFound, Passengers, create_query, get_flights

from ..airlines import resolve
from ..models import Itinerary, Leg, total_duration
from .base import ItinerarySource


def _dt(sd) -> datetime:
    (y, m, d), (hh, mm) = sd.date, sd.time
    return datetime(y, m, d, hh, mm)


def _is_overnight(prev_arrive: datetime, next_depart: datetime) -> bool:
    gap_min = (next_depart - prev_arrive).total_seconds() / 60
    return gap_min >= 300 and next_depart.date() != prev_arrive.date()


class GoogleFlightsSource(ItinerarySource):
    name = "google_flights"

    def __init__(self, passengers: int = 1, seat: str = "economy", currency: str = "USD",
                 min_sleep: float = 2.0, max_sleep: float = 4.5, proxy: str | None = None):
        self.passengers = passengers
        self.seat = seat
        self.currency = currency
        self.min_sleep, self.max_sleep = min_sleep, max_sleep
        self.proxy = proxy
        self._last_fetch = 0.0

    def _throttle(self) -> None:
        wait = self._last_fetch + random.uniform(self.min_sleep, self.max_sleep) - time.time()
        if wait > 0:
            time.sleep(wait)
        self._last_fetch = time.time()

    def build_query(self, origin: str, dest: str, depart: date, ret: date):
        return create_query(
            flights=[
                FlightQuery(date=depart.isoformat(), from_airport=origin, to_airport=dest),
                FlightQuery(date=ret.isoformat(), from_airport=dest, to_airport=origin),
            ],
            trip="round-trip",
            seat=self.seat,  # type: ignore[arg-type]
            passengers=Passengers(adults=self.passengers),
            currency=self.currency,  # type: ignore[arg-type]
            language="en-US",
        )

    def fetch_round_trip(self, origin: str, dest: str, depart: date, ret: date) -> list[Itinerary]:
        q = self.build_query(origin, dest, depart, ret)
        self._throttle()
        try:
            results = get_flights(q, proxy=self.proxy)
        except FlightsNotFound:
            return []
        name_to_code = {a.name: a.code for a in getattr(results, "metadata", None).airlines} if getattr(results, "metadata", None) else {}
        now = datetime.now()
        out: list[Itinerary] = []
        for f in results:
            if not f.flights or not isinstance(f.price, int) or f.price <= 0:
                continue
            legs = [
                Leg(
                    from_airport=s.from_airport.code,
                    to_airport=s.to_airport.code,
                    depart=_dt(s.departure),
                    arrive=_dt(s.arrival),
                    duration_min=s.duration,
                    plane=s.plane_type or "",
                )
                for s in f.flights
            ]
            layovers = [(legs[i].arrive, legs[i + 1].depart, legs[i].to_airport) for i in range(len(legs) - 1)]
            layover_mins = [int((b - a).total_seconds() // 60) for a, b, _ in layovers]
            out.append(
                Itinerary(
                    origin=origin,
                    destination=dest,
                    depart_date=depart,
                    return_date=ret,
                    price=int(f.price),
                    currency=self.currency,
                    airlines=list(f.airlines),
                    airline_codes=[resolve(a, name_to_code.get(a, "")) for a in f.airlines],
                    stops=len(legs) - 1,
                    total_duration_min=total_duration(legs),
                    depart_dt=legs[0].depart,
                    arrive_dt=legs[-1].arrive,
                    layover_airports=[ap for _, _, ap in layovers],
                    layover_max_min=max(layover_mins, default=0),
                    overnight_layover=any(_is_overnight(a, b) for a, b, _ in layovers),
                    legs=legs,
                    source=self.name,
                    fetched_at=now,
                    deep_link=q.url(),
                    extras={"type": f.type},
                )
            )
        return out
