
"""
Dynamic real-data acceptance test:
VLS International School -> UB City Mall

- Discovers Metro stations from the local Metro GTFS dataset.
- Evaluates station pairs using the existing BMTC + Metro + BMTC planner.
- Sends the selected station pair into the recommendation engine.
- Prints the complete three-mode recommendation.
- Runs the organization Digital Twin when real input files are supplied.

Run from the transit-engine project root:
    python -m app.routing.test_dynamic_acceptance

Optional environment variables:
    COMMUTE_EMPLOYEES_FILE=data/input/employee_profiles.json
    COMMUTE_VEHICLES_FILE=data/input/vehicle_profiles.json
    COMMUTE_FUEL_PRICES_FILE=data/input/fuel_prices.json
"""

import json
import os
from datetime import datetime
from math import radians, sin, cos, asin, sqrt
from pathlib import Path
from pprint import pprint

import pandas as pd

from app.routing.recommendation_engine import get_recommendations
from app.routing.bmtc_metro_bmtc_planner import (
    plan_bmtc_metro_bmtc,
    DEFAULT_LIMITS,
)
from app.routing.metro_planner import load_metro_data
from app.routing.fare_tariff_config import load_fare_data
from app.routing.digital_twin import run_participation_scenarios


# ---------------------------------------------------------
# Test inputs: locations and requested departure
# ---------------------------------------------------------

ORIGIN_NAME = "VLS International School, Basaveshwaranagar, Bengaluru"
DESTINATION_NAME = "UB City Mall, Bengaluru"

ORIGIN = {
    "lat": 12.99076,
    "lon": 77.53776,
}

DESTINATION = {
    "lat": 12.97231,
    "lon": 77.59594,
}

TRAVEL_DATE = "2026-11-19"
DEPARTURE_TIME = "13:43"

# These are general journey constraints, not selected stations.
ROUTING_LIMITS = {
    **DEFAULT_LIMITS,
}

# Search breadth is configurable. The stations themselves are discovered
# from GTFS, not typed into this script.
MAX_STATIONS_PER_SIDE = 8


# ---------------------------------------------------------
# Geographic utilities
# ---------------------------------------------------------

def haversine_m(lat1, lon1, lat2, lon2):
    radius_km = 6371.0088

    lat1, lon1, lat2, lon2 = map(
        radians,
        (float(lat1), float(lon1), float(lat2), float(lon2)),
    )

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = (
        sin(dlat / 2) ** 2
        + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    )

    return 2 * radius_km * asin(sqrt(a)) * 1000


# ---------------------------------------------------------
# Dynamic Metro station discovery
# ---------------------------------------------------------

def discover_metro_stations(travel_date):
    """
    Load active Metro GTFS data and return station records with valid
    coordinates. No station names or coordinates are supplied manually.
    """
    date = datetime.strptime(travel_date, "%Y-%m-%d").date()

    stops, _, _, _ = load_metro_data(date)

    required = {
        "stop_id",
        "stop_name",
        "stop_lat",
        "stop_lon",
        "location_type",
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

    stations = stations.dropna(
        subset=["stop_lat", "stop_lon"]
    )

    stations = stations[
        (stations["stop_lat"].between(-90, 90))
        & (stations["stop_lon"].between(-180, 180))
    ]

    stations = stations.drop_duplicates(subset=["stop_id"])

    if stations.empty:
        raise RuntimeError(
            "No geocoded Metro stations found in active GTFS data."
        )

    return stations


def nearest_station_candidates(
    stations,
    location,
    maximum_candidates,
):
    candidates = []

    for row in stations.itertuples(index=False):
        distance = haversine_m(
            location["lat"],
            location["lon"],
            row.stop_lat,
            row.stop_lon,
        )

        candidates.append({
            "station_name": str(row.stop_name),
            "station_id": str(row.stop_id),
            "lat": float(row.stop_lat),
            "lon": float(row.stop_lon),
            "straight_line_distance_m": round(distance, 1),
        })

    return sorted(
        candidates,
        key=lambda item: item["straight_line_distance_m"],
    )[:maximum_candidates]


# ---------------------------------------------------------
# Evaluate discovered station combinations
# ---------------------------------------------------------

def discover_best_three_mode_route():
    stations = discover_metro_stations(TRAVEL_DATE)

    origin_candidates = nearest_station_candidates(
        stations,
        ORIGIN,
        MAX_STATIONS_PER_SIDE,
    )

    destination_candidates = nearest_station_candidates(
        stations,
        DESTINATION,
        MAX_STATIONS_PER_SIDE,
    )

    print("\nDISCOVERED ORIGIN-SIDE METRO STATIONS")

    for station in origin_candidates:
        print(
            station["station_name"],
            "| straight-line distance:",
            station["straight_line_distance_m"],
            "m",
        )

    print("\nDISCOVERED DESTINATION-SIDE METRO STATIONS")

    for station in destination_candidates:
        print(
            station["station_name"],
            "| straight-line distance:",
            station["straight_line_distance_m"],
            "m",
        )

    successful = []
    rejected = []

    for origin_station in origin_candidates:
        for destination_station in destination_candidates:

            if (
                origin_station["station_id"]
                == destination_station["station_id"]
            ):
                continue

            try:
                result = plan_bmtc_metro_bmtc(
                    origin_lat=ORIGIN["lat"],
                    origin_lon=ORIGIN["lon"],
                    destination_lat=DESTINATION["lat"],
                    destination_lon=DESTINATION["lon"],
                    travel_date=TRAVEL_DATE,
                    departure_time=DEPARTURE_TIME,

                    # Discovered from GTFS at runtime:
                    metro_origin_station=origin_station["station_name"],
                    metro_origin_lat=origin_station["lat"],
                    metro_origin_lon=origin_station["lon"],

                    metro_destination_station=destination_station["station_name"],
                    metro_destination_lat=destination_station["lat"],
                    metro_destination_lon=destination_station["lon"],

                    limits=ROUTING_LIMITS,
                )

                if result.get("status") == "success":
                    successful.append({
                        "result": result,
                        "origin_station": origin_station,
                        "destination_station": destination_station,
                    })
                else:
                    rejected.append({
                        "origin_station": origin_station["station_name"],
                        "destination_station": destination_station["station_name"],
                        "status": result.get("status"),
                        "stage": result.get("stage"),
                        "message": result.get("message"),
                    })

            except Exception as exc:
                rejected.append({
                    "origin_station": origin_station["station_name"],
                    "destination_station": destination_station["station_name"],
                    "status": "error",
                    "message": str(exc),
                })

    if not successful:
        print("\nNo valid three-mode station combination found.")
        print("\nRejected combinations:")
        pprint(rejected, sort_dicts=False, width=140)

        raise AssertionError(
            "No valid dynamically discovered BMTC + Metro + BMTC journey."
        )

    # Prefer a viable journey with less total time, then less walking.
    successful.sort(
        key=lambda item: (
            item["result"]["total_duration_minutes"],
            item["result"]["walking_m"],
        )
    )

    print(
        f"\nSuccessful station combinations: {len(successful)}"
    )
    print(
        f"Rejected station combinations: {len(rejected)}"
    )

    return successful[0], successful, rejected


# ---------------------------------------------------------
# Load real Digital Twin input files
# ---------------------------------------------------------

def load_json_file(environment_variable):
    path_text = os.getenv(environment_variable)

    if not path_text:
        return None

    path = Path(path_text)

    if not path.is_file():
        raise FileNotFoundError(
            f"{environment_variable} points to a missing file: {path}"
        )

    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def run_digital_twin():
    """
    The Digital Twin requires organization-level data.
    No synthetic employees or invented vehicle data are generated here.
    """
    employees = load_json_file("COMMUTE_EMPLOYEES_FILE")
    vehicles = load_json_file("COMMUTE_VEHICLES_FILE")
    fuel_prices = load_json_file("COMMUTE_FUEL_PRICES_FILE") or {}

    print("\n" + "=" * 70)
    print("ORGANIZATION DIGITAL TWIN")
    print("=" * 70)

    if not employees or not vehicles:
        print("Digital Twin status: NOT RUN")
        print(
            "Reason: real employee profiles and vehicle profiles "
            "were not both supplied."
        )
        print(
            "Provide COMMUTE_EMPLOYEES_FILE and "
            "COMMUTE_VEHICLES_FILE to run the organization simulation."
        )
        return {
            "status": "not_run",
            "reason": "Required organization input files are missing.",
        }

    if not isinstance(employees, list):
        raise TypeError("Employee profile JSON must contain a list.")

    if not isinstance(vehicles, dict):
        raise TypeError(
            "Vehicle profile JSON must be keyed by employee_id."
        )

    scenarios = run_participation_scenarios(
        employee_profiles=employees,
        vehicle_profiles=vehicles,
        fuel_prices=fuel_prices,
    )

    print("Digital Twin status: SUCCESS")
    print("Employees supplied:", len(employees))
    print("\nPARTICIPATION SCENARIOS")

    for scenario in scenarios:
        print(
            "\nParticipation:",
            scenario["scenario"]["carpool_participation_rate"],
        )
        print("Organization metrics:")
        pprint(
            scenario["organization_metrics"],
            sort_dicts=False,
            width=140,
        )
        print("Baseline:")
        pprint(
            scenario["baseline"],
            sort_dicts=False,
            width=140,
        )
        print("Scenario result:")
        pprint(
            scenario["scenario_result"],
            sort_dicts=False,
            width=140,
        )
        print("Estimated savings:")
        pprint(
            scenario["estimated_savings"],
            sort_dicts=False,
            width=140,
        )
        print("Data quality:")
        pprint(
            scenario["data_quality"],
            sort_dicts=False,
            width=140,
        )

    return {
        "status": "success",
        "scenarios": scenarios,
    }


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

    # 1. Discover Metro stations and evaluate possible three-mode journeys.
    best, all_successful, rejected = discover_best_three_mode_route()

    origin_station = best["origin_station"]
    destination_station = best["destination_station"]

    print("\nSELECTED STATIONS — DISCOVERED FROM GTFS")
    print(
        origin_station["station_name"],
        "->",
        destination_station["station_name"],
    )

    # 2. Pass the discovered stations into the existing recommendation API.
    # This preserves the current engine interface while removing manually
    # typed station names and coordinates from the test configuration.
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

    import inspect

    signature = inspect.signature(get_recommendations)

    if "ranking_profile" in signature.parameters:
        kwargs["ranking_profile"] = "green_first"

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
            candidate
            for candidate in recommendations
            if candidate.get("mode") == "BMTC + Metro + BMTC"
        ),
        None,
    )

    if three_mode is None:
        print("\nThree-mode recommendation missing.")
        print("Planner found a valid combination, but the recommendation")
        print("pipeline did not retain it.")
        print("\nErrors:")
        pprint(errors, sort_dicts=False, width=140)
        raise AssertionError(
            "Three-mode route was discovered but not returned by recommendations."
        )

    print("\n" + "=" * 70)
    print("THREE-MODE RECOMMENDATION")
    print("=" * 70)

    print("Selected Metro origin:", origin_station["station_name"])
    print("Selected Metro destination:", destination_station["station_name"])
    pprint(three_mode, sort_dicts=False, width=140)

    # 3. Run the Digital Twin independently.
    digital_twin_result = run_digital_twin()

    print("\n" + "=" * 70)
    print("ACCEPTANCE TEST COMPLETED")
    print("=" * 70)

    print(
        "Journey recommendation:",
        "SUCCESS",
    )
    print(
        "Organization Digital Twin:",
        digital_twin_result["status"].upper(),
    )


if __name__ == "__main__":
    main()
