from pathlib import Path
from datetime import datetime, timedelta
from functools import lru_cache
from copy import deepcopy
import math

import pandas as pd

from app.routing.bmtc_latest_stop_matcher import (
    find_nearby_bmtc_stops
)
from app.routing.bmtc_connection_scan import scan_bmtc_connections, earliest_label

BASE = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "processed"
    / "bmtc_latest"
)

TRANSFER_BUFFER_SECONDS = 300
WALKING_SPEED_M_PER_MIN = 80


def to_seconds(value):
    parts = list(map(int, str(value).split(":")))
    if len(parts) == 2:
        parts.append(0)
    if len(parts) != 3:
        raise ValueError("Invalid GTFS time.")
    return parts[0] * 3600 + parts[1] * 60 + parts[2]


def format_time(seconds):
    seconds = int(seconds)
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def haversine(lat1, lon1, lat2, lon2):
    radius = 6371000
    p1 = math.radians(float(lat1))
    p2 = math.radians(float(lat2))
    dp = math.radians(float(lat2) - float(lat1))
    dl = math.radians(float(lon2) - float(lon1))

    a = (
        math.sin(dp / 2) ** 2
        + math.cos(p1) * math.cos(p2)
        * math.sin(dl / 2) ** 2
    )

    return 2 * radius * math.asin(math.sqrt(a))


@lru_cache(maxsize=1)
def load_bmtc_latest_data():
    required = [
        "bmtc_connections.csv",
        "bmtc_stops.csv",
        "bmtc_calendar.csv"
    ]

    for filename in required:
        if not (BASE / filename).exists():
            raise FileNotFoundError(BASE / filename)

    print("Loading 2026-2027 BMTC timetable...")

    connections = pd.read_csv(
        BASE / "bmtc_connections.csv",
        dtype=str
    )
    stops = pd.read_csv(
        BASE / "bmtc_stops.csv",
        dtype=str
    )
    calendar = pd.read_csv(
        BASE / "bmtc_calendar.csv",
        dtype=str
    )

    for column in ["departure_seconds", "arrival_seconds"]:
        connections[column] = pd.to_numeric(
            connections[column], errors="coerce"
        )

    connections = connections.dropna(
        subset=["departure_seconds", "arrival_seconds"]
    )

    connections["departure_seconds"] = (
        connections["departure_seconds"].astype("int32")
    )
    connections["arrival_seconds"] = (
        connections["arrival_seconds"].astype("int32")
    )

    connections = connections.sort_values(
        "departure_seconds"
    ).reset_index(drop=True)

    stops = stops.dropna(
        subset=["stop_id", "stop_name"]
    )

    print("Connections loaded:", len(connections))
    print("Stops loaded:", len(stops))

    return connections, stops, calendar


def active_bmtc_services(calendar, travel_date):
    date = datetime.strptime(
        travel_date, "%Y-%m-%d"
    ).date()

    weekday = date.strftime("%A").lower()
    date_number = date.strftime("%Y%m%d")

    active = calendar[
        (calendar[weekday] == "1")
        & (calendar["start_date"] <= date_number)
        & (calendar["end_date"] >= date_number)
    ]

    return set(active["service_id"].astype(str))


# Kempegowda International Airport. Airport express routes (KIA-*) charge
# premium fares and are only sensible for trips to or from the airport.
AIRPORT_COORDS = (13.1989, 77.7068)
AIRPORT_RADIUS_M = 8000
AIRPORT_ROUTE_PREFIXES = ("KIA",)


def is_airport_trip(origin_lat, origin_lon, destination_lat, destination_lon):
    return (
        haversine(origin_lat, origin_lon, *AIRPORT_COORDS) <= AIRPORT_RADIUS_M
        or haversine(destination_lat, destination_lon, *AIRPORT_COORDS) <= AIRPORT_RADIUS_M
    )


@lru_cache(maxsize=8)
def load_bmtc_connections_for_date(travel_date, exclude_airport_routes=False):
    """Return one reusable, date-filtered timetable frame per service date.

    With exclude_airport_routes=True, KIA-* airport express services are
    removed so city commutes are never routed over premium airport buses.
    """
    connections, _stops, calendar = load_bmtc_latest_data()
    services = active_bmtc_services(calendar, travel_date)
    if not services:
        return None
    mask = connections["service_id"].isin(services)
    if exclude_airport_routes:
        names = connections["route_short_name"].astype(str).str.upper()
        mask &= ~names.str.startswith(AIRPORT_ROUTE_PREFIXES)
    # The cached frame is treated as read-only by the connection scanner.
    # Same ordering the original per-request planners used.
    return connections.loc[mask].sort_values(
        ["departure_seconds", "arrival_seconds"]
    ).reset_index(drop=True)


def build_legs(path, stops):
    legs = []

    for segment in path:
        if legs and legs[-1]["trip_id"] == segment["trip_id"]:
            legs[-1]["to_stop"] = segment["to_stop"]
            legs[-1]["arrival"] = segment["arrival"]
            legs[-1]["stop_ids"].append(segment["to_stop"])
        else:
            leg = segment.copy()
            # Ordered stops served on this leg (for map geometry).
            leg["stop_ids"] = [segment["from_stop"], segment["to_stop"]]
            legs.append(leg)

    stop_names = stops.set_index(
        "stop_id"
    )["stop_name"].to_dict()

    for leg in legs:
        leg["from_stop_name"] = stop_names.get(
            leg["from_stop"], leg["from_stop"]
        )
        leg["to_stop_name"] = stop_names.get(
            leg["to_stop"], leg["to_stop"]
        )
        leg["departure_time"] = format_time(leg["departure"])
        leg["arrival_time"] = format_time(leg["arrival"])
        leg["scheduled_duration_minutes"] = round(
            (leg["arrival"] - leg["departure"]) / 60, 1
        )

    for index in range(1, len(legs)):
        previous = legs[index - 1]
        current = legs[index]

        current["transfer_wait_minutes"] = round(
            (current["departure"] - previous["arrival"]) / 60,
            1
        )
        current["transfer_at"] = previous["to_stop_name"]

    return legs


def _haversine_km(a, b, c, d):
    from math import radians, sin, cos, asin, sqrt
    a, b, c, d = map(radians, (a, b, c, d))
    return 6371.0 * 2 * asin(sqrt(sin((c - a) / 2) ** 2 + cos(a) * cos(c) * sin((d - b) / 2) ** 2))


def _plan_bmtc_latest_from_gps_uncached(
    origin_lat,
    origin_lon,
    destination_lat,
    destination_lon,
    travel_date,
    departure_time,
    search_radius_m=1000,
    candidates_per_side=5
):
    """
    GPS-based BMTC planner using the November 2026 GTFS feed.
    """

    origin_lat = float(origin_lat)
    origin_lon = float(origin_lon)
    destination_lat = float(destination_lat)
    destination_lon = float(destination_lon)

    requested_dt = datetime.strptime(
        f"{travel_date} {departure_time}",
        "%Y-%m-%d %H:%M"
    )

    requested_seconds = to_seconds(departure_time)

    origin_matches = find_nearby_bmtc_stops(
        origin_lat,
        origin_lon,
        radius_m=search_radius_m,
        limit=candidates_per_side
    )

    destination_matches = find_nearby_bmtc_stops(
        destination_lat,
        destination_lon,
        radius_m=search_radius_m,
        limit=candidates_per_side
    )

    if origin_matches["status"] != "success":
        return {
            "status": "unavailable",
            "message": "No BMTC stop found near the origin.",
            "origin_search": origin_matches
        }

    if destination_matches["status"] != "success":
        return {
            "status": "unavailable",
            "message": "No BMTC stop found near the destination.",
            "destination_search": destination_matches
        }

    connections, stops, calendar = load_bmtc_latest_data()

    services = active_bmtc_services(calendar, travel_date)

    if not services:
        return {
            "status": "unavailable",
            "message": (
                f"No active BMTC services found for {travel_date}. "
                "The feed covers 2026-11-09 to 2027-11-09."
            )
        }

    airport_trip = is_airport_trip(origin_lat, origin_lon, destination_lat, destination_lon)
    connections = load_bmtc_connections_for_date(
        travel_date, exclude_airport_routes=not airport_trip
    )

    # Seed the shared connection scanner with every nearby origin stop.
    origin_details = {}
    origin_candidates = []

    for candidate in origin_matches["matches"]:
        access_distance = float(candidate["straight_line_distance_m"])
        access_minutes = access_distance / WALKING_SPEED_M_PER_MIN

        raw_ready = requested_dt + timedelta(minutes=access_minutes)
        ready_dt = raw_ready.replace(second=0, microsecond=0)
        if ready_dt < raw_ready:
            ready_dt += timedelta(minutes=1)
        if ready_dt.date() != requested_dt.date():
            continue

        stop_id = str(candidate["stop_id"])
        origin_details[stop_id] = {
            "stop": candidate,
            "walking_minutes": access_minutes,
            "ready_time": ready_dt.strftime("%H:%M"),
        }
        origin_candidates.append({
            "stop_id": stop_id,
            "ready_seconds": to_seconds(ready_dt.strftime("%H:%M")),
        })

    if not origin_candidates:
        return {
            "status": "unavailable",
            "message": "No usable boarding stop found.",
        }

    destination_ids = [
        str(item["stop_id"]) for item in destination_matches["matches"]
    ]
    labels_by_stop = scan_bmtc_connections(
        connections,
        origin_candidates,
        transfer_buffer_seconds=TRANSFER_BUFFER_SECONDS,
        target_stop_ids=destination_ids,
        progress_label="Searching 2026 BMTC timetable",
        # Intercity Vajra Vistara trips (e.g. Majestic -> Tumakuru) take ~3 h 15 min,
        # so long trips need a longer search horizon than city commutes.
        max_journey_seconds=(5 * 3600 if _haversine_km(origin_lat, origin_lon, destination_lat,
                                                       destination_lon) > 35 else 3 * 3600),
    )

    journeys = []

    for destination in destination_matches["matches"]:
        destination_id = destination["stop_id"]

        label = earliest_label(labels_by_stop, destination_id)
        if label is None:
            continue

        path = label["path"]

        origin_id = label["origin_id"]

        if origin_id not in origin_details:
            continue

        origin_info = origin_details[origin_id]
        origin_stop = origin_info["stop"]

        legs = build_legs(path, stops)

        arrival_seconds = label["arrival"]

        egress_distance = haversine(
            destination["latitude"],
            destination["longitude"],
            destination_lat,
            destination_lon
        )

        access_minutes = origin_info["walking_minutes"]
        egress_minutes = (
            egress_distance / WALKING_SPEED_M_PER_MIN
        )

        total_minutes = (
            (arrival_seconds - requested_seconds) / 60
            + egress_minutes
        )

        journeys.append({
            "total_estimated_duration_minutes": round(
                total_minutes, 1
            ),
            "origin_access": {
                "stop_id": origin_id,
                "stop_name": origin_stop["stop_name"],
                "distance_m": round(
                    origin_stop["straight_line_distance_m"], 1
                ),
                "walking_minutes": round(access_minutes, 1)
            },
            "destination_egress": {
                "stop_id": destination_id,
                "stop_name": destination["stop_name"],
                "distance_m": round(egress_distance, 1),
                "walking_minutes": round(egress_minutes, 1)
            },
            "bmtc_journey": {
                "status": "success",
                "travel_date": travel_date,
                "departure": legs[0]["departure_time"],
                "arrival": format_time(arrival_seconds),
                "duration_minutes": round(
                    (arrival_seconds - legs[0]["departure"]) / 60,
                    1
                ),
                "number_of_bus_legs": len(legs),
                "legs": legs
            }
        })

    if not journeys:
        return {
            "status": "unavailable",
            "message": (
                "No scheduled BMTC journey found between the nearby "
                "stops for this date and departure time."
            ),
            "origin_candidates": origin_matches["matches"],
            "destination_candidates": destination_matches["matches"]
        }

    journeys.sort(
        key=lambda item: item["total_estimated_duration_minutes"]
    )

    return {
        "status": "success",
        "feed_version": "2026-11-09",
        "feed_validity": "2026-11-09 to 2027-11-09",
        "travel_date": travel_date,
        "requested_departure": departure_time,
        "origin_coordinates": [origin_lat, origin_lon],
        "destination_coordinates": [
            destination_lat, destination_lon
        ],
        "best_journey": journeys[0],
        "alternative_journeys": journeys[1:],
        "journeys_compared": len(journeys),
        "search_method": "shared_stop_trip_state_connection_scan",
        "airport_routes_included": airport_trip,
        "data_warning": (
            "Uses a community-published BMTC GTFS feed. "
            "Scheduled times are not live bus arrival predictions."
        ),
        "limitations": [
            "Walking access and egress use straight-line distances.",
            "Walking speed is assumed to be 80 metres per minute.",
            "No live BMTC vehicle positions or delay information.",
            "No ML duration adjustment is applied to this new feed."
        ]
    }


@lru_cache(maxsize=256)
def _cached_bmtc_result(
    origin_lat, origin_lon, destination_lat, destination_lon,
    travel_date, departure_time, search_radius_m, candidates_per_side
):
    """Cache identical feeder requests across Metro station-pair evaluation."""
    return _plan_bmtc_latest_from_gps_uncached(
        origin_lat, origin_lon, destination_lat, destination_lon,
        travel_date, departure_time, search_radius_m, candidates_per_side,
    )


def plan_bmtc_latest_from_gps(
    origin_lat,
    origin_lon,
    destination_lat,
    destination_lon,
    travel_date,
    departure_time,
    search_radius_m=1000,
    candidates_per_side=5,
):
    """Cached public wrapper; identical feeder requests are computed once."""
    result = _cached_bmtc_result(
        float(origin_lat), float(origin_lon),
        float(destination_lat), float(destination_lon),
        str(travel_date), str(departure_time),
        float(search_radius_m), int(candidates_per_side),
    )
    return deepcopy(result)


def clear_bmtc_planner_caches():
    """Clear cached timetable frames and feeder results after data updates."""
    _cached_bmtc_result.cache_clear()
    load_bmtc_connections_for_date.cache_clear()
    load_bmtc_latest_data.cache_clear()


if __name__ == "__main__":
    result = plan_bmtc_latest_from_gps(
        origin_lat=12.9585,
        origin_lon=77.5635,
        destination_lat=13.0105,
        destination_lon=77.5540,
        travel_date="2026-11-18",
        departure_time="08:00"
    )

    print("\n2026 BMTC GPS JOURNEY")
    print("=====================")
    print("Status:", result["status"])

    if result["status"] == "success":
        best = result["best_journey"]

        print(
            "Total duration:",
            best["total_estimated_duration_minutes"],
            "minutes"
        )

        print("Boarding:", best["origin_access"]["stop_name"])
        print("Destination:", best["destination_egress"]["stop_name"])

        journey = best["bmtc_journey"]

        print("BMTC departure:", journey["departure"])
        print("BMTC arrival:", journey["arrival"])
        print("Bus legs:", journey["number_of_bus_legs"])

        for leg in journey["legs"]:
            print(
                leg["route_short_name"],
                "|",
                leg["from_stop_name"],
                "->",
                leg["to_stop_name"],
                "|",
                leg["departure_time"],
                "->",
                leg["arrival_time"]
            )

        print("\nFeed warning:", result["data_warning"])

    else:
        print("Reason:", result["message"])
