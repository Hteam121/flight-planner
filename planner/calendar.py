"""Layer 1: enumerate feasible (depart, return) pairs and compute PTO cost.

Pure functions, no network. The PTO estimate here is *optimistic*: it assumes
an evening departure (if that rule is on) because flight times are unknown.
`pto_cost_exact` re-evaluates once real times are available.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Iterator

from .config import TravelDayRules, TripConfig, WorkCalendar
from .models import DatePair


def is_workday(d: date, cal: WorkCalendar) -> bool:
    if cal.weekends_off and d.weekday() >= 5:
        return False
    if d.weekday() in cal.extra_days_off:
        return False
    if d in cal.holidays:
        return False
    return True


def _days(a: date, b: date) -> Iterator[date]:
    cur = a
    while cur <= b:
        yield cur
        cur += timedelta(days=1)


def pto_cost(
    depart: date,
    home_arrival: date,
    cal: WorkCalendar,
    rules: TravelDayRules,
    depart_hour: int | None = None,
    arrive_hour: int | None = None,
) -> int:
    """Working days consumed by being away from `depart` through `home_arrival` inclusive.

    depart_hour / arrive_hour are local clock hours of the outbound departure and the
    final homebound arrival. None means "unknown": the departure is assumed to satisfy
    the evening rule (optimistic); the arrival is assumed to cost a day if it's a workday.
    """
    cost = sum(1 for d in _days(depart, home_arrival) if is_workday(d, cal))

    if is_workday(depart, cal) and rules.evening_departure_free:
        if depart_hour is None or depart_hour >= rules.evening_departure_hour:
            cost -= 1

    if home_arrival != depart and is_workday(home_arrival, cal):
        if not rules.return_arrival_costs_pto:
            cost -= 1
        elif (
            rules.return_arrival_free_before_hour is not None
            and arrive_hour is not None
            and arrive_hour < rules.return_arrival_free_before_hour
        ):
            cost -= 1

    return max(cost, 0)


def feasible_pairs(cfg: TripConfig) -> list[DatePair]:
    """All (depart, return) pairs inside the window that fit the PTO budget."""
    w, tl = cfg.search_window, cfg.trip_length
    out: list[DatePair] = []
    for depart in _days(w.earliest_depart, w.latest_return - timedelta(days=tl.min_nights)):
        for nights in range(tl.min_nights, tl.max_nights + 1):
            ret = depart + timedelta(days=nights)
            if ret > w.latest_return:
                break
            cost = pto_cost(depart, ret, cfg.work_calendar, cfg.travel_day_rules)
            if cost <= cfg.pto_budget:
                out.append(DatePair(depart=depart, ret=ret, nights=nights, pto_cost=cost))
    return out


def rank_pairs_for_verification(cfg: TripConfig, pairs: list[DatePair], top_n: int) -> list[DatePair]:
    """Pick which pairs to spend Google Flights requests on when no price hint exists.

    Heuristic: best nights-per-PTO first, then longer trips, then weekend departures.
    Always include long trips when `verify_long_trip_fraction` is set.
    """
    must = set()
    if cfg.verify_long_trip_fraction is not None:
        threshold = cfg.trip_length.max_nights * cfg.verify_long_trip_fraction
        must = {p for p in pairs if p.nights >= threshold}

    ranked = sorted(
        pairs,
        key=lambda p: (-p.pto_efficiency, -p.nights, 0 if p.depart.weekday() >= 4 else 1, p.depart),
    )
    chosen: list[DatePair] = []
    seen = set()
    for p in list(must) + ranked:
        if p.key in seen:
            continue
        if p not in must and len(chosen) - len([c for c in chosen if c in must]) >= top_n:
            continue
        chosen.append(p)
        seen.add(p.key)
    return sorted(chosen, key=lambda p: (p.depart, p.ret))
