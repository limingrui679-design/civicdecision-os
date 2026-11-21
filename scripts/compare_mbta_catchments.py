"""Compare Blue Line station access at two ready times using a local official GTFS archive."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from collections import defaultdict
from datetime import date
from pathlib import Path
from zipfile import ZipFile

from civicdecision.optimization.facility import (
    DemandPoint,
    FacilityPlanningConfig,
    enumerate_facility_plans,
    select_best_plan,
    select_robust_plan,
)


def seconds(stamp: str) -> int:
    h, m, s = map(int, stamp.split(":"))
    return 3600 * h + 60 * m + s


def compare(path: Path, day: date) -> dict[str, object]:
    key = day.strftime("%Y%m%d")
    weekday = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")[
        day.weekday()
    ]
    with ZipFile(path) as archive:

        def read(table: str):
            with (
                archive.open(table + ".txt") as raw,
                io.TextIOWrapper(raw, encoding="utf-8-sig", newline="") as stream,
            ):
                yield from csv.DictReader(stream)

        active = {
            r["service_id"]
            for r in read("calendar")
            if r["start_date"] <= key <= r["end_date"] and r[weekday] == "1"
        }
        for r in read("calendar_dates"):
            if r["date"] == key:
                if r["exception_type"] == "1":
                    active.add(r["service_id"])
                elif r["exception_type"] == "2":
                    active.discard(r["service_id"])
        trip_ids = {
            r["trip_id"]
            for r in read("trips")
            if r["route_id"] == "Blue" and r["service_id"] in active
        }
        if not trip_ids:
            raise ValueError("No scheduled Blue Line trips on this service date")
        stops = {r["stop_id"]: r for r in read("stops")}
        trips = defaultdict(list)
        for r in read("stop_times"):
            if r["trip_id"] in trip_ids:
                point = stops[r["stop_id"]]
                station = point["parent_station"] or point["stop_id"]
                trips[r["trip_id"]].append(
                    (
                        int(r["stop_sequence"]),
                        station,
                        seconds(r["arrival_time"]),
                        seconds(r["departure_time"]),
                        r.get("pickup_type", "") in ("", "0"),
                        r.get("drop_off_type", "") in ("", "0"),
                    )
                )
    for rows in trips.values():
        rows.sort()
    ids = sorted({r[1] for rows in trips.values() for r in rows})
    pts = [
        DemandPoint(
            id=s,
            latitude=float(stops[s]["stop_lat"]),
            longitude=float(stops[s]["stop_lon"]),
            population=1,
            estimated_need=1,
            priority_rate=0,
        )
        for s in ids
    ]
    config = FacilityPlanningConfig(
        max_facilities=1, facility_cost=1, budget=1, minimum_priority_coverage=0, cost_penalty=0
    )
    scenarios = {}
    info = {}
    for stamp in ("08:00:00", "22:00:00"):
        ready = seconds(stamp)
        times: dict[str, dict[str, float]] = {s: {s: 0.0} for s in ids}
        for rows in trips.values():
            for i, (_, origin, _, depart, board, _) in enumerate(rows):
                if not board or not ready <= depart <= ready + 900:
                    continue
                for _, site, arrive, _, _, alight in rows[i + 1 :]:
                    if alight and arrive >= depart:
                        minutes = (arrive - ready) / 60
                        times[origin][site] = min(minutes, times[origin].get(site, float("inf")))
        plans = enumerate_facility_plans(pts, config, travel_minutes=times, minute_limit=15)
        scenarios[stamp] = plans
        best = select_best_plan(plans)
        assert best
        info[stamp] = {"best": best.selected_ids, "covered_stations": len(best.covered_ids)}
    geographic = select_best_plan(enumerate_facility_plans(pts, config))
    robust = select_robust_plan(scenarios)
    assert robust and geographic
    return {
        "archive_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "service_date": day.isoformat(),
        "stations": len(ids),
        "scheduled_trips": len(trips),
        "ready_times": info,
        "geographic_1_25km": {
            "best": geographic.selected_ids,
            "covered_stations": len(geographic.covered_ids),
        },
        "geographic_site_on_timetable": {
            stamp: len(
                next(p for p in plans if p.selected_ids == geographic.selected_ids).covered_ids
            )
            for stamp, plans in scenarios.items()
        },
        "robust_site": robust[0],
        "regret_share": robust[1],
        "robust_covered": {
            k: len(next(p for p in v if p.selected_ids == robust[0]).covered_ids)
            for k, v in scenarios.items()
        },
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("gtfs", type=Path)
    parser.add_argument("--date", type=date.fromisoformat, required=True)
    args = parser.parse_args()
    print(json.dumps(compare(args.gtfs, args.date), indent=2))
