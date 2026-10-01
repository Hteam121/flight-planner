# flight-planner

Constraint-driven cheapest-date finder. You describe a trip as constraints (PTO budget,
weekends, holidays, trip length, date window); it enumerates every feasible
(depart, return) pair, prices them on Google Flights, scores price vs comfort, and writes
an HTML report with top picks, a Pareto table, a departure-date heatmap and deep links.

## Setup

```bash
uv sync
```

## Usage

```bash
# 1. See which date pairs fit your PTO rules (no network)
uv run planner pairs trips/chennai-nov-2026.yaml

# 2. See which pairs would be priced (no network)
uv run planner run trips/chennai-nov-2026.yaml --dry-run

# 3. Price them on Google Flights and write out/<trip>-<date>.html
uv run planner run trips/chennai-nov-2026.yaml            # verify_top_n pairs + all long trips
uv run planner run trips/chennai-nov-2026.yaml --all      # every feasible pair (~5 s each)
uv run planner run trips/chennai-nov-2026.yaml --comfort-weight 120   # value comfort more

# 4. Re-render from cache without fetching (e.g. after changing comfort weights / tiers)
uv run planner report trips/chennai-nov-2026.yaml
```

Fetches are cached per day in `planner.sqlite`; `--refresh` forces a refetch.
Every fetch also appends to `price_history`, so running it daily builds a price trend
(phase 3: `planner track` + alerts).

## Trip config

See `trips/*.yaml`. Key knobs:

| key | meaning |
|---|---|
| `search_window` | earliest departure, latest return |
| `trip_length.min_nights/max_nights` | inclusive range of nights |
| `pto_budget` | max working days you'll burn |
| `work_calendar.holidays` | company days off (don't cost PTO) |
| `travel_day_rules.evening_departure_free` | departing a workday after `evening_departure_hour` costs 0 PTO |
| `preferred_window` | soft bonus (in $) for departures inside a range |
| `comfort_lambda` | dollars per comfort point for the Balanced profile |
| `airline_tiers` | IATA code → 1 (best) .. 3 (avoid) |
| `verify_top_n` / `verify_long_trip_fraction` | how many pairs to spend requests on |
| `group_size` | multiplies card prices for groups |

Comfort penalty = stops + extra hours vs fastest option + long layovers (>3h) + overnight
layover + red-eye departure + airline tier. Weights are in `comfort_weights`.

## Optional: Travelpayouts price hints

Set `TRAVELPAYOUTS_TOKEN` (free at travelpayouts.com) and `run` will pull cached
month-calendar prices first and verify the cheapest-looking pairs instead of the heuristic
ranking. Those cached prices are never shown as results, only used for ranking.

## Caveats

- `fast-flights` is an unofficial Google Flights scraper. If Google changes its page, the
  `GoogleFlightsSource` class is the only thing to swap (SerpApi has the same shape).
- Round-trip searches list outbound options with the round-trip fare, like Google's first
  page. Comfort is scored on the outbound; open the deep link to pick the return.
- PTO assumes you are home on the return date. For routes where the return lands next
  day, add a day to `min_nights`/`max_nights` or set `return_arrival_costs_pto` accordingly.
