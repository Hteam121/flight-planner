from datetime import date

from planner.calendar import feasible_pairs, is_workday, pto_cost
from planner.config import SearchWindow, TravelDayRules, TripConfig, TripLength, WorkCalendar

CAL = WorkCalendar(weekends_off=True, holidays=[date(2026, 11, 25), date(2026, 11, 26)])
RULES = TravelDayRules()


def test_workday_basics():
    assert is_workday(date(2026, 11, 20), CAL)  # Friday
    assert not is_workday(date(2026, 11, 21), CAL)  # Saturday
    assert not is_workday(date(2026, 11, 26), CAL)  # Thanksgiving holiday


def test_fri_nov20_to_sun_dec6_is_8_pto():
    # Nov 23, 24, 27, Nov 30-Dec 4 = 8; Fri 20 free by evening-departure rule
    assert pto_cost(date(2026, 11, 20), date(2026, 12, 6), CAL, RULES) == 8


def test_fri_nov20_to_tue_dec8_is_10_pto():
    assert pto_cost(date(2026, 11, 20), date(2026, 12, 8), CAL, RULES) == 10


def test_morning_departure_costs_the_departure_day():
    assert pto_cost(date(2026, 11, 20), date(2026, 12, 6), CAL, RULES, depart_hour=9) == 9
    assert pto_cost(date(2026, 11, 20), date(2026, 12, 6), CAL, RULES, depart_hour=20) == 8


def test_mon_nov16_to_fri_nov27_eleven_nights():
    # Nov 16-20 (5) + 23, 24 (2) + 27 (1) = 8, minus evening departure = 7
    assert pto_cost(date(2026, 11, 16), date(2026, 11, 27), CAL, RULES) == 7


def test_early_arrival_can_save_the_arrival_day():
    rules = TravelDayRules(return_arrival_free_before_hour=8)
    # Return lands Mon Dec 7 at 06:00 -> Monday not charged
    assert pto_cost(date(2026, 11, 20), date(2026, 12, 7), CAL, rules, arrive_hour=6) == 8
    assert pto_cost(date(2026, 11, 20), date(2026, 12, 7), CAL, rules, arrive_hour=14) == 9


def _chennai() -> TripConfig:
    return TripConfig(
        name="t",
        origin=["DFW"],
        destination=["MAA"],
        search_window=SearchWindow(earliest_depart=date(2026, 11, 1), latest_return=date(2026, 12, 20)),
        trip_length=TripLength(min_nights=10, max_nights=18),
        pto_budget=10,
        work_calendar=CAL,
    )


def test_feasible_pairs_respect_budget_and_window():
    cfg = _chennai()
    pairs = feasible_pairs(cfg)
    assert pairs, "expected some feasible pairs"
    for p in pairs:
        assert p.pto_cost <= 10
        assert 10 <= p.nights <= 18
        assert p.depart >= date(2026, 11, 1)
        assert p.ret <= date(2026, 12, 20)
    keys = {(p.depart, p.ret): p for p in pairs}
    assert keys[(date(2026, 11, 20), date(2026, 12, 6))].pto_cost == 8
    assert keys[(date(2026, 11, 20), date(2026, 12, 8))].pto_cost == 10
    # 19 nights would exceed max; 11 PTO pairs excluded
    assert (date(2026, 11, 20), date(2026, 12, 9)) not in keys
