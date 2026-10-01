"""Layer 5: render HTML + Markdown reports from scored itineraries."""

from __future__ import annotations

import calendar as pycal
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .calendar import is_workday
from .config import TripConfig
from .models import DatePair, Itinerary
from .score import Profiles

TEMPLATES = Path(__file__).parent / "templates"


def _hm(minutes: int) -> str:
    return f"{minutes // 60}h {minutes % 60:02d}m"


def _price_color(p: int | None, lo: int, hi: int) -> str:
    if p is None:
        return "transparent"
    t = 0.0 if hi == lo else (p - lo) / (hi - lo)
    # green -> amber -> red
    r = int(255 * min(1, 2 * t))
    g = int(255 * min(1, 2 * (1 - t)))
    return f"rgba({r},{g},90,0.55)"


def build_heatmap(cfg: TripConfig, its: list[Itinerary], pairs: list[DatePair]) -> list[dict]:
    """Per month: 7-col grid of departure days with cheapest verified price across feasible returns."""
    best: dict[date, Itinerary] = {}
    for it in its:
        cur = best.get(it.depart_date)
        if cur is None or it.price < cur.price:
            best[it.depart_date] = it
    feasible_departs = {p.depart for p in pairs}
    prices = [i.price for i in best.values()]
    lo, hi = (min(prices), max(prices)) if prices else (0, 0)

    months = []
    d = cfg.search_window.earliest_depart.replace(day=1)
    end = cfg.search_window.latest_return
    while d <= end:
        weeks = []
        for week in pycal.Calendar(firstweekday=0).monthdatescalendar(d.year, d.month):
            cells = []
            for day in week:
                in_month = day.month == d.month
                it = best.get(day) if in_month else None
                cells.append({
                    "day": day.day if in_month else "",
                    "date": day.isoformat(),
                    "price": it.price if it else None,
                    "airline": "/".join(it.airlines) if it else "",
                    "ret": it.return_date.isoformat() if it else "",
                    "color": _price_color(it.price if it else None, lo, hi),
                    "feasible": in_month and day in feasible_departs,
                    "off": in_month and not is_workday(day, cfg.work_calendar),
                    "in_month": in_month,
                })
            weeks.append(cells)
        months.append({"label": d.strftime("%B %Y"), "weeks": weeks})
        d = (d.replace(day=28) + (date.resolution * 4)).replace(day=1)
    return months


def pto_efficiency_table(its: list[Itinerary]) -> list[dict]:
    by_pto: dict[int, Itinerary] = {}
    for it in its:
        cur = by_pto.get(it.pto_cost)
        if cur is None or (it.nights, -it.price) > (cur.nights, -cur.price):
            by_pto[it.pto_cost] = it
    return [
        {"pto": k, "nights": v.nights, "price": v.price, "depart": v.depart_date, "ret": v.return_date,
         "airline": "/".join(v.airlines), "link": v.deep_link}
        for k, v in sorted(by_pto.items())
    ]


def render(cfg: TripConfig, its: list[Itinerary], profiles: Profiles, pairs: list[DatePair],
           verified_pairs: int, out_dir: Path, sources: list[str]) -> tuple[Path, Path]:
    env = Environment(loader=FileSystemLoader(str(TEMPLATES)), autoescape=select_autoescape(["html"]))
    env.filters["hm"] = _hm
    env.filters["money"] = lambda v: f"${v:,.0f}" if v is not None else "—"
    env.filters["dow"] = lambda d: d.strftime("%a %b %d")

    best_per_pair: dict[tuple, Itinerary] = {}
    for it in its:
        k = it.pair_key
        if k not in best_per_pair or it.value_score < best_per_pair[k].value_score:
            best_per_pair[k] = it
    table = sorted(best_per_pair.values(), key=lambda i: i.value_score)
    frontier = sorted([i for i in its if i.pareto], key=lambda i: i.price)

    ctx = dict(
        cfg=cfg, profiles=profiles, table=table, frontier=frontier,
        heatmap=build_heatmap(cfg, its, pairs), pto_table=pto_efficiency_table(its),
        n_pairs=len(pairs), n_verified=verified_pairs, n_its=len(its),
        generated=datetime.now().strftime("%Y-%m-%d %H:%M"), sources=sources,
        fetched_range=(min(i.fetched_at for i in its).strftime("%Y-%m-%d %H:%M"), max(i.fetched_at for i in its).strftime("%Y-%m-%d %H:%M")) if its else ("", ""),
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d")
    html_path = out_dir / f"{cfg.name}-{stamp}.html"
    md_path = out_dir / f"{cfg.name}-{stamp}.md"
    html_path.write_text(env.get_template("report.html.j2").render(**ctx))
    md_path.write_text(env.get_template("report.md.j2").render(**ctx))
    return html_path, md_path
