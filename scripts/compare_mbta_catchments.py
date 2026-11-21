"""Compare Blue Line station access at two ready times using a local official GTFS archive."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from collections import defaultdict
from datetime import date
from functools import lru_cache
from math import ceil
from pathlib import Path
from zipfile import ZipFile

from civicdecision.optimization.facility import (
    DemandPoint,
    FacilityPlanningConfig,
    enumerate_facility_plans,
    rank_reliable_access,
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

    @lru_cache(maxsize=256)
    def travel_times_at(ready: int):
        times: dict[str, dict[str, float]] = {s: {s: 0.0} for s in ids}
        for rows in trips.values():
            for i, (_, origin, _, depart, board, _) in enumerate(rows):
                if not board or not ready <= depart <= ready + 25 * 60:
                    continue
                for _, site, arrive, _, _, alight in rows[i + 1 :]:
                    if alight and arrive >= depart:
                        minutes = (arrive - ready) / 60
                        times[origin][site] = min(minutes, times[origin].get(site, float("inf")))
        return times

    def plans_at(ready: int, minutes: int = 15):
        return enumerate_facility_plans(
            pts, config, travel_minutes=travel_times_at(ready), minute_limit=minutes
        )

    scenarios = {}
    info = {}
    for stamp in ("08:00:00", "22:00:00"):
        plans = plans_at(seconds(stamp))
        scenarios[stamp] = plans
        best = select_best_plan(plans)
        assert best
        info[stamp] = {"best": best.selected_ids, "covered_stations": len(best.covered_ids)}
    geographic = select_best_plan(enumerate_facility_plans(pts, config))
    robust = select_robust_plan(scenarios)
    assert robust and geographic

    def departure_grid(offset_minutes: int, minutes: int):
        snapshots = {
            str(t): plans_at(t, minutes) for t in range((360 + offset_minutes) * 60, 23 * 3600, 600)
        }
        return rank_reliable_access(pts, snapshots, required_departures=ceil(0.90 * len(snapshots)))

    grids = {
        minutes: (departure_grid(0, minutes), departure_grid(5, minutes))
        for minutes in (8, 10, 12, 15, 20, 25)
    }
    standards = []
    for minutes, (train, validation) in grids.items():
        selected = train[0].selected_ids
        frozen = next(row for row in validation if row.selected_ids == selected)
        standards.append(
            {
                "minute_limit": minutes,
                "site": selected,
                "fit_reliable_stations": len(train[0].reliable_ids),
                "holdout_reliable_stations": len(frozen.reliable_ids),
            }
        )
    training, held_out = grids[15]
    mean_choice = min(training, key=lambda plan: (-plan.mean_need_share, plan.selected_ids))
    selections = {
        "reliable_access": training[0].selected_ids,
        "mean_access": mean_choice.selected_ids,
        "two_instant_minimax": robust[0],
        "geographic_radius": geographic.selected_ids,
    }
    held_by_site = {plan.selected_ids: plan for plan in held_out}
    policies = {}
    for policy, sites in selections.items():
        result = held_by_site[sites]
        policies[policy] = {
            "sites": sites,
            "holdout_reliable_stations": len(result.reliable_ids),
            "holdout_mean_covered_stations": result.mean_need_share * len(ids),
            "holdout_departures_per_origin": result.departures_covered_by_origin,
        }
    return {
        "departure_reliability": {
            "departure_grid": "06:00-22:50 every 10 minutes; validation offset +5 minutes",
            "fit_departures": training[0].observed_departures,
            "holdout_departures": held_out[0].observed_departures,
            "required_departures": held_out[0].required_departures,
            "policies": policies,
            "service_standard_frontier": standards,
        },
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
