"""SQLite cache: raw fetches, normalized itineraries, and a price history for tracking."""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime
from pathlib import Path

from .models import Itinerary

SCHEMA = """
CREATE TABLE IF NOT EXISTS fetches (
    source TEXT, origin TEXT, destination TEXT, depart TEXT, ret TEXT,
    fetched_on TEXT, fetched_at TEXT, itineraries_json TEXT,
    PRIMARY KEY (source, origin, destination, depart, ret, fetched_on)
);
CREATE TABLE IF NOT EXISTS price_history (
    source TEXT, origin TEXT, destination TEXT, depart TEXT, ret TEXT,
    fetched_at TEXT, min_price INTEGER, airline TEXT, stops INTEGER
);
CREATE INDEX IF NOT EXISTS ph_route ON price_history (origin, destination, depart, ret);
"""


class Cache:
    def __init__(self, path: str | Path = "planner.sqlite"):
        self.conn = sqlite3.connect(str(path))
        self.conn.executescript(SCHEMA)

    def get(self, source: str, origin: str, dest: str, depart: date, ret: date, fetched_on: date) -> list[Itinerary] | None:
        row = self.conn.execute(
            "SELECT itineraries_json FROM fetches WHERE source=? AND origin=? AND destination=? AND depart=? AND ret=? AND fetched_on=?",
            (source, origin, dest, depart.isoformat(), ret.isoformat(), fetched_on.isoformat()),
        ).fetchone()
        if row is None:
            return None
        return [Itinerary.from_json(d) for d in json.loads(row[0])]

    def latest(self, source: str, origin: str, dest: str, depart: date, ret: date) -> list[Itinerary] | None:
        row = self.conn.execute(
            "SELECT itineraries_json FROM fetches WHERE source=? AND origin=? AND destination=? AND depart=? AND ret=? ORDER BY fetched_on DESC LIMIT 1",
            (source, origin, dest, depart.isoformat(), ret.isoformat()),
        ).fetchone()
        if row is None:
            return None
        return [Itinerary.from_json(d) for d in json.loads(row[0])]

    def all_latest(self, source: str, origin: str, dest: str) -> list[Itinerary]:
        rows = self.conn.execute(
            """SELECT f.itineraries_json FROM fetches f
               JOIN (SELECT depart, ret, MAX(fetched_on) m FROM fetches
                     WHERE source=? AND origin=? AND destination=? GROUP BY depart, ret) x
               ON f.depart=x.depart AND f.ret=x.ret AND f.fetched_on=x.m
               WHERE f.source=? AND f.origin=? AND f.destination=?""",
            (source, origin, dest, source, origin, dest),
        ).fetchall()
        out: list[Itinerary] = []
        for (js,) in rows:
            out.extend(Itinerary.from_json(d) for d in json.loads(js))
        return out

    def put(self, source: str, origin: str, dest: str, depart: date, ret: date, its: list[Itinerary]) -> None:
        now = datetime.now()
        self.conn.execute(
            "INSERT OR REPLACE INTO fetches VALUES (?,?,?,?,?,?,?,?)",
            (source, origin, dest, depart.isoformat(), ret.isoformat(), now.date().isoformat(), now.isoformat(),
             json.dumps([i.to_json() for i in its])),
        )
        if its:
            best = min(its, key=lambda i: i.price)
            self.conn.execute(
                "INSERT INTO price_history VALUES (?,?,?,?,?,?,?,?,?)",
                (source, origin, dest, depart.isoformat(), ret.isoformat(), now.isoformat(),
                 best.price, "/".join(best.airlines), best.stops),
            )
        self.conn.commit()

    def history(self, origin: str, dest: str, depart: date, ret: date) -> list[tuple[str, int]]:
        return self.conn.execute(
            "SELECT fetched_at, min_price FROM price_history WHERE origin=? AND destination=? AND depart=? AND ret=? ORDER BY fetched_at",
            (origin, dest, depart.isoformat(), ret.isoformat()),
        ).fetchall()
