"""Trip configuration models (loaded from trips/*.yaml)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, model_validator


class SearchWindow(BaseModel):
    earliest_depart: date
    latest_return: date


class TripLength(BaseModel):
    min_nights: int = Field(ge=1)
    max_nights: int = Field(ge=1)

    @model_validator(mode="after")
    def _ordered(self) -> "TripLength":
        if self.max_nights < self.min_nights:
            raise ValueError("max_nights must be >= min_nights")
        return self


class WorkCalendar(BaseModel):
    weekends_off: bool = True
    holidays: list[date] = Field(default_factory=list)
    # Extra non-working weekdays, e.g. a compressed schedule. 0=Mon..6=Sun.
    extra_days_off: list[int] = Field(default_factory=list)


class TravelDayRules(BaseModel):
    # A departure on a workday costs no PTO if the flight leaves at/after this hour.
    evening_departure_free: bool = True
    evening_departure_hour: int = 17
    # Landing back home on a workday costs PTO unless you land before this hour (None = always costs).
    return_arrival_costs_pto: bool = True
    return_arrival_free_before_hour: int | None = None


class PreferredWindow(BaseModel):
    start: date
    end: date
    bonus_usd: float = 75.0  # soft bonus subtracted from the value score


class ComfortWeights(BaseModel):
    """Comfort penalty weights. Units are 'comfort points'; lambda converts to dollars."""

    per_stop: float = 1.0
    per_extra_hour: float = 0.35
    per_long_layover_hour: float = 0.5  # beyond 3h
    overnight_layover: float = 1.0
    redeye_departure: float = 0.3
    airline_tier_1: float = 0.0
    airline_tier_2: float = 0.4
    airline_tier_3: float = 1.0
    unknown_airline: float = 0.6


class TripConfig(BaseModel):
    name: str
    origin: list[str]
    destination: list[str]
    search_window: SearchWindow
    trip_length: TripLength
    pto_budget: int = Field(ge=0)
    work_calendar: WorkCalendar = Field(default_factory=WorkCalendar)
    travel_day_rules: TravelDayRules = Field(default_factory=TravelDayRules)
    preferred_window: PreferredWindow | None = None
    group_size: int = Field(default=1, ge=1)
    passengers: int = Field(default=1, ge=1, le=9)
    seat: str = "economy"
    currency: str = "USD"
    comfort_weights: ComfortWeights = Field(default_factory=ComfortWeights)
    # Dollars per comfort point used for the "Balanced" profile.
    comfort_lambda: float = 60.0
    # Airline IATA code -> tier (1 best .. 3 worst). Unlisted -> unknown_airline weight.
    airline_tiers: dict[str, int] = Field(default_factory=dict)
    # Deep-verify budget: how many date pairs to fetch from Google Flights per run.
    verify_top_n: int = 25
    # Always verify pairs whose nights >= this fraction of max_nights (maximize-trip goals).
    verify_long_trip_fraction: float | None = None

    @model_validator(mode="after")
    def _airports_upper(self) -> "TripConfig":
        self.origin = [a.upper() for a in self.origin]
        self.destination = [a.upper() for a in self.destination]
        return self


def load_trip(path: str | Path) -> TripConfig:
    with open(path) as f:
        raw = yaml.safe_load(f)
    return TripConfig.model_validate(raw)
