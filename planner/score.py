"""Layer 4: comfort penalty, value score, Pareto frontier and named profiles."""

from __future__ import annotations

from dataclasses import dataclass

from .airlines import resolve
from .calendar import pto_cost
from .config import TripConfig
from .models import Itinerary, total_duration


def airline_penalty(it: Itinerary, cfg: TripConfig) -> float:
    w = cfg.comfort_weights
    tier_w = {1: w.airline_tier_1, 2: w.airline_tier_2, 3: w.airline_tier_3}
    pens = []
    codes = [resolve(n, c) for n, c in zip(it.airlines, it.airline_codes)] or it.airline_codes
    for code in codes:
        tier = cfg.airline_tiers.get(code)
        pens.append(tier_w.get(tier, w.unknown_airline) if tier else w.unknown_airline)
    return max(pens) if pens else w.unknown_airline


def comfort_penalty(it: Itinerary, cfg: TripConfig, route_min_duration: int) -> float:
    w = cfg.comfort_weights
    extra_hours = max(0, it.total_duration_min - route_min_duration) / 60
    long_layover_hours = max(0, it.layover_max_min - 180) / 60
    redeye = 1 if 0 <= it.depart_dt.hour < 5 else 0
    return (
        w.per_stop * it.stops
        + w.per_extra_hour * extra_hours
        + w.per_long_layover_hour * long_layover_hours
        + w.overnight_layover * (1 if it.overnight_layover else 0)
        + w.redeye_departure * redeye
        + airline_penalty(it, cfg)
    )


def annotate(its: list[Itinerary], cfg: TripConfig, lam: float | None = None) -> list[Itinerary]:
    """Fill nights, exact pto_cost, comfort_penalty, value_score and pareto flag in place."""
    if not its:
        return its
    lam = cfg.comfort_lambda if lam is None else lam
    for it in its:  # recompute from legs so older cached rows get the timezone-safe value
        if it.legs:
            it.total_duration_min = total_duration(it.legs)
    route_min = min(i.total_duration_min for i in its)
    for it in its:
        it.nights = (it.return_date - it.depart_date).days
        # Exact PTO: use real outbound departure hour. Homebound arrival date is unknown for
        # round-trip pages (only outbound legs are listed), so assume arrival on return_date.
        it.pto_cost = pto_cost(
            it.depart_date, it.return_date, cfg.work_calendar, cfg.travel_day_rules,
            depart_hour=it.depart_dt.hour,
        )
        it.comfort_penalty = round(comfort_penalty(it, cfg, route_min), 3)
        bonus = 0.0
        if cfg.preferred_window and cfg.preferred_window.start <= it.depart_date <= cfg.preferred_window.end:
            bonus = cfg.preferred_window.bonus_usd
        it.value_score = round(it.price + lam * it.comfort_penalty - bonus, 2)
    mark_pareto(its)
    return its


def mark_pareto(its: list[Itinerary]) -> None:
    """Pareto frontier over (price, comfort_penalty): keep rows not beaten on both."""
    srt = sorted(its, key=lambda i: (i.price, i.comfort_penalty))
    best_pen = float("inf")
    for it in srt:
        it.pareto = it.comfort_penalty < best_pen
        if it.pareto:
            best_pen = it.comfort_penalty


@dataclass
class Profiles:
    cheapest: Itinerary | None
    balanced: Itinerary | None
    comfort: Itinerary | None
    longest_trip: Itinerary | None  # cheapest among max-nights options


def pick_profiles(its: list[Itinerary], cfg: TripConfig) -> Profiles:
    if not its:
        return Profiles(None, None, None, None)
    budget_ok = [i for i in its if i.pto_cost <= cfg.pto_budget] or its
    cheapest = min(budget_ok, key=lambda i: (i.price, i.comfort_penalty))
    balanced = min(budget_ok, key=lambda i: (i.value_score, i.price))
    comfort = min(budget_ok, key=lambda i: (i.comfort_penalty, i.price))
    max_n = max(i.nights for i in budget_ok)
    longest = min((i for i in budget_ok if i.nights == max_n), key=lambda i: i.price)
    return Profiles(cheapest, balanced, comfort, longest)
