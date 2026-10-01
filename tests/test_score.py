from datetime import date, datetime

from planner.config import SearchWindow, TripConfig, TripLength, WorkCalendar
from planner.models import Itinerary, Leg
from planner.score import annotate, pick_profiles


def _cfg() -> TripConfig:
    return TripConfig(
        name="t", origin=["DFW"], destination=["MAA"],
        search_window=SearchWindow(earliest_depart=date(2026, 11, 1), latest_return=date(2026, 12, 20)),
        trip_length=TripLength(min_nights=10, max_nights=18), pto_budget=10,
        work_calendar=WorkCalendar(holidays=[date(2026, 11, 25), date(2026, 11, 26)]),
        airline_tiers={"QR": 1, "AA": 2, "ET": 3}, comfort_lambda=100,
    )


def _it(price, stops, dur_h, codes, depart_hour=20, layover_max=120, overnight=False) -> Itinerary:
    d0 = datetime(2026, 11, 20, depart_hour, 0)
    return Itinerary(
        origin="DFW", destination="MAA", depart_date=date(2026, 11, 20), return_date=date(2026, 12, 6),
        price=price, currency="USD", airlines=codes, airline_codes=codes, stops=stops,
        total_duration_min=dur_h * 60, depart_dt=d0, arrive_dt=d0, layover_airports=[],
        layover_max_min=layover_max, overnight_layover=overnight,
        legs=[Leg("DFW", "MAA", d0, d0, dur_h * 60)], source="test", fetched_at=d0, deep_link="",
    )


def test_pareto_drops_dominated():
    cfg = _cfg()
    cheap_bad = _it(1200, 2, 30, ["ET"])
    mid = _it(1500, 1, 22, ["QR"])
    dominated = _it(1600, 2, 32, ["ET"])  # pricier AND less comfortable than cheap_bad
    its = annotate([cheap_bad, mid, dominated], cfg)
    assert cheap_bad.pareto and mid.pareto and not dominated.pareto


def test_profiles_pick_expected_rows():
    cfg = _cfg()
    cheap_bad = _it(1200, 2, 30, ["ET"])
    mid = _it(1450, 1, 22, ["AA"])
    luxe = _it(2400, 0, 19, ["QR"])
    its = annotate([cheap_bad, mid, luxe], cfg)
    p = pick_profiles(its, cfg)
    assert p.cheapest is cheap_bad
    assert p.comfort is luxe
    # lambda=100: cheap_bad = 1200 + 100*(2 + 0.35*11 + 1.0) = 1200+685 = 1885
    #             mid       = 1450 + 100*(1 + 0.35*3 + 0.4)  = 1450+245 = 1695
    #             luxe      = 2400 + 0                         = 2400
    assert p.balanced is mid


def test_exact_pto_uses_departure_hour():
    cfg = _cfg()
    evening = _it(1000, 1, 20, ["QR"], depart_hour=21)
    morning = _it(1000, 1, 20, ["QR"], depart_hour=8)
    annotate([evening, morning], cfg)
    assert evening.pto_cost == 8
    assert morning.pto_cost == 9
