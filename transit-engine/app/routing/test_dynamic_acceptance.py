"""
Optimized dynamic real-data acceptance test:
VLS International School -> UB City Mall.

Metro stations are discovered from the active local Metro GTFS feed.
BMTC feeder searches are shared by station side:
  * one origin-feeder search per discovered origin-side Metro station;
  * one destination-feeder search per destination-side Metro station,
    after selecting the earliest feasible Metro arrival at that station.

This removes the old 8 x 8 x 2 BMTC search pattern. The Metro station
names and coordinates are never hardcoded.

Run from the transit-engine project root:
    python -m app.routing.test_dynamic_acceptance
"""

from datetime import datetime, timedelta
from math import radians, sin, cos, asin, sqrt
from pathlib import Path
from pprint import pprint
import inspect

import pandas as pd

from app.routing.recommendation_engine import get_recommendations
from app.routing.bmtc_latest_planner import (
    plan_bmtc_latest_from_gps,
)
from app.routing.bmtc_metro_bmtc_planner import (
    DEFAULT_LIMITS,
    _bmtc_best,
    _plus_minutes,
    _walk_m,
)
from app.routing.metro_planner import load_metro_data, plan_metro
from app.routing.fare_tariff_config import load_fare_data


# ---------------------------------------------------------
# Test inputs
# ---------------------------------------------------------

ORIGIN_NAME = "VLS International School, Basaveshwaranagar, Bengaluru"
DESTINATION_NAME = "UB City Mall, Bengaluru"

ORIGIN = {"lat": 12.99076, "lon": 77.53776}
DESTINATION = {"lat": 12.97231, "lon": 77.59594}

TRAVEL_DATE = "2026-11-19"
DEPARTURE_TIME = "13:43"

ROUTING_LIMITS = {**DEFAULT_LIMITS}
MAX_STATIONS_PER_SIDE = 8


# ---------------------------------------------------------
# Geographic utilities and dynamic station discovery
# ---------------------------------------------------------

def haversine_m(lat1, lon1, lat2, lon2):
    radius_km = 6371.0088
    lat1, lon1, lat2, lon2 = map(
        radians, (float(lat1), float(lon1), float(lat2), float(lon2))
    )
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = (
        sin(dlat / 2) ** 2
        + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    )
    return 2 * radius_km * asin(sqrt(a)) * 1000


def discover_metro_stations(travel_date):
    date = datetime.strptime(travel_date, "%Y-%m-%d").date()
    stops, _, _, _ = load_metro_data(date)

    required = {
        "stop_id", "stop_name", "stop_lat", "stop_lon", "location_type"
    }
    missing = required - set(stops.columns)
    if missing:
        raise RuntimeError(
            f"Metro GTFS stops.csv is missing columns: {sorted(missing)}"
        )

    stations = stops[
        stops["location_type"].astype(str) == "1"
    ].copy()
    stations["stop_lat"] = pd.to_numeric(
        stations["stop_lat"], errors="coerce"
    )
    stations["stop_lon"] = pd.to_numeric(
        stations["stop_lon"], errors="coerce"
    )
    stations = stations.dropna(subset=["stop_lat", "stop_lon"])
    stations = stations[
        stations["stop_lat"].between(-90, 90)
        & stations["stop_lon"].between(-180, 180)
    ].drop_duplicates(subset=["stop_id"])

    if stations.empty:
        raise RuntimeError("No geocoded Metro stations found in active GTFS data.")
    return stations


def nearest_station_candidates(stations, location, maximum_candidates):
    candidates = []
    for row in stations.itertuples(index=False):
        distance = haversine_m(
            location["lat"], location["lon"], row.stop_lat, row.stop_lon
        )
        candidates.append({
            "station_name": str(row.stop_name),
            "station_id": str(row.stop_id),
            "lat": float(row.stop_lat),
            "lon": float(row.stop_lon),
            "straight_line_distance_m": round(distance, 1),
        })
    return sorted(
        candidates, key=lambda item: item["straight_line_distance_m"]
    )[:maximum_candidates]


# ---------------------------------------------------------
# Shared-search station-pair evaluation
# ---------------------------------------------------------

def _clock_seconds(value):
    parts = list(map(int, str(value).split(":")))
    if len(parts) == 2:
        parts.append(0)
    return parts[0] * 3600 + parts[1] * 60 + parts[2]


def _arrival_datetime(travel_date, value):
    fmt = "%H:%M:%S" if len(str(value).split(":")) == 3 else "%H:%M"
    return datetime.strptime(
        f"{travel_date} {value}", f"%Y-%m-%d {fmt}"
    )


def _valid_origin_feeder(result):
    first = _bmtc_best(result)
    if first is None:
        return None
    if _walk_m(first.get("origin_access")) > ROUTING_LIMITS["origin_access_m"]:
        return None
    if _walk_m(first.get("destination_egress")) > ROUTING_LIMITS["feeder_egress_m"]:
        return None
    return first


def _valid_destination_feeder(result):
    second = _bmtc_best(result)
    if second is None:
        return None
    if _walk_m(second.get("origin_access")) > ROUTING_LIMITS["metro_to_feeder_access_m"]:
        return None
    if _walk_m(second.get("destination_egress")) > ROUTING_LIMITS["destination_egress_m"]:
        return None
    return second


def discover_best_three_mode_route():
    stations = discover_metro_stations(TRAVEL_DATE)
    origin_candidates = nearest_station_candidates(
        stations, ORIGIN, MAX_STATIONS_PER_SIDE
    )
    destination_candidates = nearest_station_candidates(
        stations, DESTINATION, MAX_STATIONS_PER_SIDE
    )

    print("\nDISCOVERED ORIGIN-SIDE METRO STATIONS")
    for station in origin_candidates:
        print(
            station["station_name"], "| straight-line distance:",
            station["straight_line_distance_m"], "m"
        )

    print("\nDISCOVERED DESTINATION-SIDE METRO STATIONS")
    for station in destination_candidates:
        print(
            station["station_name"], "| straight-line distance:",
            station["straight_line_distance_m"], "m"
        )

    # Stage 1: each origin-side Metro station needs one origin feeder result.
    # Crucially, this result is independent of the destination-side station.
    print("\nSTAGE 1: ORIGIN FEEDERS")
    origin_feeders = {}
    for index, station in enumerate(origin_candidates, start=1):
        print(
            f"Origin feeder {index}/{len(origin_candidates)}: "
            f"{station['station_name']}"
        )
        raw = plan_bmtc_latest_from_gps(
            ORIGIN["lat"], ORIGIN["lon"],
            station["lat"], station["lon"],
            TRAVEL_DATE, DEPARTURE_TIME,
        )
        feeder = _valid_origin_feeder(raw)
        if feeder is not None:
            origin_feeders[station["station_id"]] = {
                "station": station,
                "journey": feeder,
            }

    if not origin_feeders:
        raise AssertionError("No valid BMTC origin feeder reached any discovered Metro station.")

    # Stage 2: evaluate Metro connections. For each destination station,
    # retain the earliest Metro arrival across all feasible origin stations.
    # An earlier arrival at the same destination station dominates a later
    # arrival because the downstream BMTC timetable is identical and can wait.
    print("\nSTAGE 2: METRO PAIR EVALUATION")
    best_metro_by_destination = {}
    metro_pair_count = 0
    metro_success_count = 0

    for origin_station_id, origin_data in origin_feeders.items():
        origin_station = origin_data["station"]
        first = origin_data["journey"]
        first_bus = first["bmtc_journey"]
        first_egress = first["destination_egress"]

        metro_ready = _plus_minutes(
            first_bus["arrival"],
            float(first_egress.get("walking_minutes", 0) or 0)
            + ROUTING_LIMITS["minimum_transfer_minutes"],
        )

        for destination_station in destination_candidates:
            if origin_station_id == destination_station["station_id"]:
                continue

            metro_pair_count += 1
            metro = plan_metro(
                origin_station["station_name"],
                destination_station["station_name"],
                TRAVEL_DATE,
                metro_ready,
            )
            if not isinstance(metro, dict) or metro.get("status") != "success":
                continue

            metro_success_count += 1
            current = best_metro_by_destination.get(
                destination_station["station_id"]
            )
            arrival_seconds = _clock_seconds(metro["arrival"])
            if current is None or arrival_seconds < current["arrival_seconds"]:
                best_metro_by_destination[destination_station["station_id"]] = {
                    "origin_station": origin_station,
                    "destination_station": destination_station,
                    "origin_feeder": first,
                    "metro": metro,
                    "metro_ready": metro_ready,
                    "arrival_seconds": arrival_seconds,
                }

    if not best_metro_by_destination:
        raise AssertionError("No scheduled Metro journey connected the discovered station candidates.")

    # Stage 3: each destination-side station needs only one downstream feeder
    # search, using its earliest feasible Metro arrival.
    print("\nSTAGE 3: DESTINATION FEEDERS")
    successful = []
    for index, (destination_id, route_data) in enumerate(
        best_metro_by_destination.items(), start=1
    ):
        destination_station = route_data["destination_station"]
        metro = route_data["metro"]
        second_ready = _plus_minutes(
            metro["arrival"], ROUTING_LIMITS["minimum_transfer_minutes"]
        )

        print(
            f"Destination feeder {index}/{len(best_metro_by_destination)}: "
            f"{destination_station['station_name']} after Metro arrival "
            f"{metro['arrival']}"
        )

        second_raw = plan_bmtc_latest_from_gps(
            destination_station["lat"], destination_station["lon"],
            DESTINATION["lat"], DESTINATION["lon"],
            TRAVEL_DATE, second_ready,
        )
        second = _valid_destination_feeder(second_raw)
        if second is None:
            continue

        final_bus_arrival = second["bmtc_journey"]["arrival"]
        end_dt = _arrival_datetime(TRAVEL_DATE, final_bus_arrival)
        start_dt = datetime.strptime(
            f"{TRAVEL_DATE} {DEPARTURE_TIME}", "%Y-%m-%d %H:%M"
        )
        if end_dt < start_dt:
            end_dt += timedelta(days=1)
        end_dt += timedelta(
            minutes=float(
                second["destination_egress"].get("walking_minutes", 0) or 0
            )
        )

        first = route_data["origin_feeder"]
        first_access = first["origin_access"]
        first_egress = first["destination_egress"]
        second_access = second["origin_access"]
        second_egress = second["destination_egress"]

        walking_m = sum(_walk_m(section) for section in (
            first_access, first_egress, second_access, second_egress
        ))

        combined = {
            "status": "success",
            "journey_type": "BMTC + Metro + BMTC",
            "travel_date": TRAVEL_DATE,
            "departure": DEPARTURE_TIME,
            "arrival": end_dt.strftime("%H:%M:%S"),
            "total_duration_minutes": round(
                (end_dt - start_dt).total_seconds() / 60, 1
            ),
            "walking_m": round(walking_m, 1),
            "legs": [
                {
                    "mode": "BMTC feeder",
                    "from": "Origin",
                    "to": route_data["origin_station"]["station_name"],
                    "journey": first,
                },
                {
                    "mode": "Metro",
                    "from": route_data["origin_station"]["station_name"],
                    "to": destination_station["station_name"],
                    "journey": metro,
                },
                {
                    "mode": "BMTC feeder",
                    "from": destination_station["station_name"],
                    "to": "Destination",
                    "journey": second,
                },
            ],
            "transfer_buffer_minutes": ROUTING_LIMITS["minimum_transfer_minutes"],
            "data_warnings": [
                "BMTC and Metro legs use scheduled GTFS data, not live vehicle positions.",
                "BMTC access and egress distances use straight-line approximations.",
            ],
        }

        successful.append({
            "result": combined,
            "origin_station": route_data["origin_station"],
            "destination_station": destination_station,
            "origin_feeder": first,
            "metro": metro,
            "destination_feeder": second,
        })

    if not successful:
        raise AssertionError("No valid three-mode journey survived feeder and walking constraints.")

    successful.sort(
        key=lambda item: (
            item["result"]["total_duration_minutes"],
            item["result"]["walking_m"],
        )
    )

    print("\nSEARCH SUMMARY")
    print("Origin feeder BMTC searches:", len(origin_candidates))
    print("Metro pairs evaluated:", metro_pair_count)
    print("Successful Metro pairs:", metro_success_count)
    print("Destination feeder BMTC searches:", len(best_metro_by_destination))
    print("Successful complete journeys:", len(successful))
    print(
        "BMTC scans are now bounded by station-side candidates, "
        "not by the Cartesian product of station pairs."
    )

    return successful[0], successful


# ---------------------------------------------------------
# Main acceptance test
# ---------------------------------------------------------

def main():
    print("=" * 70)
    print("DYNAMIC COMMUTE RECOMMENDATION ACCEPTANCE TEST")
    print("=" * 70)
    print("Origin:", ORIGIN_NAME)
    print("Destination:", DESTINATION_NAME)
    print("Date:", TRAVEL_DATE)
    print("Departure:", DEPARTURE_TIME)

    fares = load_fare_data()
    print(
        "Fare tariff data:",
        "loaded" if fares else "not configured; unknown fares remain unknown",
    )

    best, all_successful = discover_best_three_mode_route()
    origin_station = best["origin_station"]
    destination_station = best["destination_station"]

    print("\nSELECTED STATIONS — DISCOVERED FROM GTFS")
    print(
        origin_station["station_name"], "->",
        destination_station["station_name"]
    )
    print("Three-mode duration:", best["result"]["total_duration_minutes"], "minutes")
    print("Three-mode walking:", best["result"]["walking_m"], "m")

    # Keep the existing recommendation engine as the final integration check.
    # It receives only the selected, dynamically discovered station pair.
    three_mode_config = {
        "metro_origin_station": origin_station["station_name"],
        "metro_origin_lat": origin_station["lat"],
        "metro_origin_lon": origin_station["lon"],
        "metro_destination_station": destination_station["station_name"],
        "metro_destination_lat": destination_station["lat"],
        "metro_destination_lon": destination_station["lon"],
        "limits": ROUTING_LIMITS,
    }
    if fares:
        three_mode_config["fare_data"] = fares

    kwargs = {
        "origin_lat": ORIGIN["lat"],
        "origin_lon": ORIGIN["lon"],
        "destination_lat": DESTINATION["lat"],
        "destination_lon": DESTINATION["lon"],
        "travel_date": TRAVEL_DATE,
        "departure_time": DEPARTURE_TIME,
        "three_mode_config": three_mode_config,
    }

    signature = inspect.signature(get_recommendations)
    if "ranking_profile" in signature.parameters:
        kwargs["ranking_profile"] = "green_first"

    print("\nSTAGE 4: RECOMMENDATION ENGINE INTEGRATION")
    result = get_recommendations(**kwargs)
    recommendations = result.get("recommendations", [])
    errors = result.get("errors", [])

    print("\nRECOMMENDATION ENGINE STATUS:", result.get("status"))
    print("Recommendations returned:", len(recommendations))
    for rank, candidate in enumerate(recommendations, start=1):
        print(
            f"{rank}. {candidate.get('mode')} | "
            f"duration={candidate.get('duration_minutes')} min | "
            f"walking={candidate.get('distance_walking_m')} m | "
            f"fare={candidate.get('fare')}"
        )

    three_mode = next(
        (
            candidate for candidate in recommendations
            if candidate.get("mode") == "BMTC + Metro + BMTC"
        ),
        None,
    )
    if three_mode is None:
        print("\nThree-mode recommendation missing from recommendation pipeline.")
        pprint(errors, sort_dicts=False, width=140)
        raise AssertionError(
            "Shared search found a journey, but recommendation engine did not retain it."
        )

    print("\nTHREE-MODE RECOMMENDATION")
    print("=" * 70)
    print("Selected Metro origin:", origin_station["station_name"])
    print("Selected Metro destination:", destination_station["station_name"])
    pprint(three_mode, sort_dicts=False, width=140)

    print("\n" + "=" * 70)
    print("ACCEPTANCE TEST COMPLETED")
    print("=" * 70)
    print("Dynamic station discovery: SUCCESS")
    print("Shared feeder search: SUCCESS")
    print("Recommendation integration: SUCCESS")
    print("Organization Digital Twin: DEFERRED (as requested)")


if __name__ == "__main__":
    main()
