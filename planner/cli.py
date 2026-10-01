"""CLI: planner pairs|run|report <trip.yaml>"""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

import typer
from rich.console import Console
from rich.progress import Progress
from rich.table import Table

from .cache import Cache
from .calendar import feasible_pairs, rank_pairs_for_verification, spread_pairs
from .config import TripConfig, load_trip
from .models import DatePair, Itinerary
from .report import render
from .score import annotate, pick_profiles
from .sources.google_flights import GoogleFlightsSource
from .sources.travelpayouts import TravelpayoutsSource

app = typer.Typer(add_completion=False, help="Constraint-driven cheapest-date flight finder.")
console = Console()


def _pairs_table(pairs: list[DatePair], limit: int = 40) -> None:
    t = Table(title=f"{len(pairs)} feasible date pairs (showing {min(limit, len(pairs))})")
    for c in ("Depart", "Return", "Nights", "PTO", "Nights/PTO"):
        t.add_column(c)
    for p in sorted(pairs, key=lambda p: (-p.pto_efficiency, -p.nights))[:limit]:
        t.add_row(p.depart.strftime("%a %Y-%m-%d"), p.ret.strftime("%a %Y-%m-%d"), str(p.nights), str(p.pto_cost), f"{p.pto_efficiency:.1f}")
    console.print(t)


@app.command()
def pairs(trip: Path, limit: int = 40):
    """List feasible (depart, return) pairs under the PTO budget. No network."""
    cfg = load_trip(trip)
    _pairs_table(feasible_pairs(cfg), limit)


def _select_pairs(cfg: TripConfig, all_pairs: list[DatePair], top: int, verify_all: bool, hints, spread: bool | None) -> list[DatePair]:
    if verify_all:
        return all_pairs
    window_days = (cfg.search_window.latest_return - cfg.search_window.earliest_depart).days
    if spread or (spread is None and not hints and window_days > 90):
        return spread_pairs(cfg, all_pairs)
    if hints:
        # Rank by cached price hint; unpriced pairs go after priced ones, then by heuristic.
        priced = sorted((p for p in all_pairs if p.key in hints), key=lambda p: hints[p.key][0])
        rest = rank_pairs_for_verification(cfg, [p for p in all_pairs if p.key not in hints], top)
        chosen = (priced + rest)[:top]
        must = []
        if cfg.verify_long_trip_fraction is not None:
            thr = cfg.trip_length.max_nights * cfg.verify_long_trip_fraction
            must = [p for p in all_pairs if p.nights >= thr and p not in chosen]
        return sorted(chosen + must, key=lambda p: (p.depart, p.ret))
    return rank_pairs_for_verification(cfg, all_pairs, top)


@app.command()
def run(
    trip: Path,
    top: int = typer.Option(None, help="How many date pairs to verify on Google Flights (default: trip's verify_top_n)."),
    all_pairs: bool = typer.Option(False, "--all", help="Verify every feasible pair (slow: ~5s each)."),
    dry_run: bool = typer.Option(False, help="Only list which pairs would be fetched."),
    spread: bool = typer.Option(None, "--spread/--no-spread", help="Sample one pair per week across the window (auto when window > 90 days and no price hints)."),
    refresh: bool = typer.Option(False, help="Ignore today's cached fetches and refetch."),
    comfort_weight: float = typer.Option(None, help="Dollars per comfort point for the Balanced profile."),
    out: Path = Path("out"),
    db: Path = Path("planner.sqlite"),
):
    """Enumerate feasible pairs, verify prices on Google Flights, score, and write the report."""
    cfg = load_trip(trip)
    if comfort_weight is not None:
        cfg.comfort_lambda = comfort_weight
    pairs_ = feasible_pairs(cfg)
    console.print(f"[bold]{cfg.name}[/]: {len(pairs_)} feasible date pairs within {cfg.pto_budget} PTO days")
    if not pairs_:
        raise typer.Exit(1)

    hints: dict = {}
    tp = TravelpayoutsSource(currency=cfg.currency)
    sources = ["google_flights"]
    if tp.available and not dry_run:
        months = sorted({p.depart.strftime("%Y-%m") for p in pairs_})
        nights = sorted({p.nights for p in pairs_})
        for o in cfg.origin:
            for d in cfg.destination:
                hints.update(tp.price_hints(o, d, months, nights))
        sources.append("travelpayouts (ranking hints only)")
        console.print(f"Travelpayouts hints for {len(hints)} pairs")

    top_n = top or cfg.verify_top_n
    selected = _select_pairs(cfg, pairs_, top_n, all_pairs, hints, spread)
    console.print(f"Will verify {len(selected)} pairs × {len(cfg.origin) * len(cfg.destination)} route(s)")
    if dry_run:
        _pairs_table(selected, limit=len(selected))
        return

    cache = Cache(db)
    gf = GoogleFlightsSource(passengers=cfg.passengers, seat=cfg.seat, currency=cfg.currency)
    today = date.today()
    its: list[Itinerary] = []
    verified = 0
    with Progress(console=console) as prog:
        task = prog.add_task("Fetching Google Flights", total=len(selected) * len(cfg.origin) * len(cfg.destination))
        for p in selected:
            for o in cfg.origin:
                for d in cfg.destination:
                    cached = None if refresh else cache.get(gf.name, o, d, p.depart, p.ret, today)
                    if cached is None:
                        try:
                            cached = gf.fetch_round_trip(o, d, p.depart, p.ret)
                        except Exception as e:  # keep going on transient failures
                            console.print(f"[red]fetch failed[/] {o}->{d} {p.depart}/{p.ret}: {e}")
                            cached = []
                        cache.put(gf.name, o, d, p.depart, p.ret, cached)
                    verified += 1
                    its.extend(cached)
                    prog.advance(task)

    _finish(cfg, its, pairs_, verified, out, sources)


@app.command()
def report(trip: Path, out: Path = Path("out"), db: Path = Path("planner.sqlite"), comfort_weight: float = None):
    """Re-render the report from everything cached for this trip (no network)."""
    cfg = load_trip(trip)
    if comfort_weight is not None:
        cfg.comfort_lambda = comfort_weight
    pairs_ = feasible_pairs(cfg)
    keys = {p.key for p in pairs_}
    cache = Cache(db)
    its: list[Itinerary] = []
    for o in cfg.origin:
        for d in cfg.destination:
            its.extend(i for i in cache.all_latest("google_flights", o, d) if i.pair_key in keys)
    _finish(cfg, its, pairs_, len({i.pair_key for i in its}), out, ["google_flights (cached)"])


def _finish(cfg: TripConfig, its: list[Itinerary], pairs_: list[DatePair], verified: int, out: Path, sources: list[str]) -> None:
    if not its:
        console.print("[red]No itineraries found.[/] Google may have returned no data; try again or use --refresh.")
        raise typer.Exit(1)
    annotate(its, cfg)
    profiles = pick_profiles(its, cfg)
    html, md = render(cfg, its, profiles, pairs_, verified, out, sources)

    t = Table(title="Top picks")
    for c in ("Profile", "Dates", "Nights", "PTO", "Price", "Airlines", "Stops", "Duration"):
        t.add_column(c)
    for label, it in (("Cheapest", profiles.cheapest), ("Balanced", profiles.balanced), ("Comfort", profiles.comfort), ("Longest", profiles.longest_trip)):
        if it:
            t.add_row(label, f"{it.depart_date:%a %b %d} → {it.return_date:%a %b %d}", str(it.nights), str(it.pto_cost),
                      f"${it.price:,}", " + ".join(it.airlines), str(it.stops), f"{it.total_duration_min // 60}h{it.total_duration_min % 60:02d}")
    console.print(t)
    console.print(f"Report: [link=file://{html.resolve()}]{html}[/]  ·  {md}")


if __name__ == "__main__":
    app()
