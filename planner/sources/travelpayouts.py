"""Layer 2 (phase 2): cached price hints from the Travelpayouts Data API.

Free token: https://www.travelpayouts.com/programs/100/tools/api  (env TRAVELPAYOUTS_TOKEN)
Prices are cached/affiliate data: used ONLY to rank which date pairs to verify.
"""

from __future__ import annotations

import os

import httpx

from .base import PriceHintSource

BASE = "https://api.travelpayouts.com"


class TravelpayoutsSource(PriceHintSource):
    name = "travelpayouts"

    def __init__(self, token: str | None = None, currency: str = "usd"):
        self.token = token or os.environ.get("TRAVELPAYOUTS_TOKEN", "")
        self.currency = currency.lower()
        self.client = httpx.Client(timeout=30, headers={"X-Access-Token": self.token, "Accept-Encoding": "gzip"})

    @property
    def available(self) -> bool:
        return bool(self.token)

    def price_hints(self, origin, dest, months, nights):
        hints: dict[tuple[str, str], tuple[int, str, int]] = {}
        for month in months:
            for n in nights:
                r = self.client.get(
                    f"{BASE}/v1/prices/calendar",
                    params={"origin": origin, "destination": dest, "depart_date": month,
                            "calendar_type": "departure_date", "length": n, "currency": self.currency},
                )
                if r.status_code != 200:
                    continue
                data = r.json().get("data") or {}
                for depart_iso, row in data.items():
                    ret_iso = (row.get("return_at") or "")[:10]
                    if not ret_iso:
                        continue
                    key = (depart_iso, ret_iso)
                    cand = (int(row["price"]), row.get("airline", ""), int(row.get("transfers", 0)))
                    if key not in hints or cand[0] < hints[key][0]:
                        hints[key] = cand
        return hints
