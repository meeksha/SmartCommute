from datetime import datetime, timedelta
from pathlib import Path
from functools import lru_cache

import pandas as pd

from app.routing.planner import (
    load_walking_data,
    nearest_reachable_station,
    nearest_reachable_stations,
    WALKING_SPEED_M_PER_MIN,
)
from app.routing.metro_planner import plan_metro
from app.routing.metro_fares import calculate_metro_journey_fare

from app.routing.bmtc_latest_planner import (
    load_bmtc_latest_data,
    active_bmtc_services,
    build_legs,
    to_seconds,
    TRANSFER_BUFFER_SECONDS,
    load_bmtc_connections_for_date,
    is_airport_trip,
)
from app.routing.bmtc_connection_scan import (
    scan_bmtc_connections,
    earliest_label,
)

from app.routing.bmtc_latest_stop_matcher import find_nearby_bmtc_stops
from app.routing.bmtc_fares import calculate_bmtc_journey_fare

from app.services.carbon import (
    calculate_bmtc_journey_distance,
    calculate_bmtc_emission_scenarios,
    calculate_emissions,
)


CURRENT_INTERCHANGES = Path(
    "data/processed/bmtc_latest/metro_bmtc_current_interchanges.csv"
)


@lru_cache(maxsize=1)
def _current_interchanges():
    return pd.read_csv(CURRENT_INTERCHANGES)


def plan_bmtc_then_metro(
    origin_lat,
    origin_lon,
    destination_lat,
    destination_lon,
    travel_date,
    departure_time,
    search_radius_m=1000,
    candidates_per_side=5,
    max_interchanges=5,
):
    """
    Plan a BMTC -> Metro journey using the November 2026 BMTC feed
    and the standard Metro GTFS timetable.

    BMTC timetable is scanned once to find reachable interchange stops.
    Metro journeys are then checked from those interchange stations.
    """

    origin_lat = float(origin_lat)
    origin_lon = float(origin_lon)
    destination_lat = float(destination_lat)
    destination_lon = float(destination_lon)

    requested_dt = datetime.strptime(
        f"{travel_date} {departure_time}",
        "%Y-%m-%d %H:%M",
    )

    requested_seconds = to_seconds(departure_time)

    # Find BMTC boarding stops near the origin.
    origin_matches = find_nearby_bmtc_stops(
        origin_lat,
        origin_lon,
        radius_m=search_radius_m,
        limit=candidates_per_side,
    )

    if origin_matches["status"] != "success":
        return {
            "status": "unavailable",
            "message": "No BMTC boarding stop found near the origin.",
            "origin_search": origin_matches,
        }

    # Load BMTC data and select services operating on the requested date.
    connections, bmtc_stops, calendar = load_bmtc_latest_data()
    services = active_bmtc_services(calendar, travel_date)

    if not services:
        return {
            "status": "unavailable",
            "message": "No active BMTC services for this date.",
        }

    # Reuse the cached, date-filtered and departure-sorted timetable.
    connections = load_bmtc_connections_for_date(
        travel_date,
        exclude_airport_routes=not is_airport_trip(
            origin_lat, origin_lon, destination_lat, destination_lon
        ),
    )

    # Load modelled Metro-BMTC interchange connections.
    if not CURRENT_INTERCHANGES.exists():
        return {
            "status": "unavailable",
            "message": "Metro-BMTC interchange dataset was not found.",
        }

    interchange_df = _current_interchanges().copy()

    interchange_df = interchange_df[
        (interchange_df["interchange_status"] == "CURRENT_FEED_APPROXIMATE_WALK")
        & interchange_df["bmtc_stop_id"].notna()
    ].copy()

    interchange_df["bmtc_stop_id"] = (
        interchange_df["bmtc_stop_id"].astype(str)
    )

    # Seed the shared scanner with each feasible origin stop independently.
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
        }
        origin_candidates.append({
            "stop_id": stop_id,
            "ready_seconds": to_seconds(ready_dt.strftime("%H:%M")),
        })

    if not origin_candidates:
        return {
            "status": "unavailable",
            "message": "No usable BMTC boarding stop found.",
        }

    interchange_stop_ids = set(
        interchange_df["bmtc_stop_id"].astype(str)
    )
    labels_by_stop = scan_bmtc_connections(
        connections,
        origin_candidates,
        transfer_buffer_seconds=TRANSFER_BUFFER_SECONDS,
        target_stop_ids=interchange_stop_ids,
        progress_label="Searching BMTC timetable for interchange stops",
    )

    # Keep only interchange stops reached by a valid BMTC journey.
    reachable = []

    for row in interchange_df.to_dict("records"):
        stop_id = row["bmtc_stop_id"]

        label = earliest_label(labels_by_stop, stop_id)
        if label is None:
            continue

        if label["origin_id"] not in origin_details:
            continue

        walk_metres = float(row["estimated_total_walk_m"])
        walk_minutes = float(row["estimated_walk_minutes"])

        reachable.append({
            "interchange": row,
            "label": label,
            "walk_metres": walk_metres,
            "walk_minutes": walk_minutes,
        })

    if not reachable:
        return {
            "status": "unavailable",
            "message": (
                "No modelled Metro interchange was reachable by BMTC "
                "from the selected origin and departure time."
            ),
            "interchanges_checked": len(interchange_df),
        }

    # Prefer interchanges reached earliest, including interchange walking.
    reachable.sort(
        key=lambda item: (
            item["label"]["arrival"] / 60
            + item["walk_minutes"]
        )
    )
    # Evaluate a wider shortlist than the former hard top-5 so a slightly
    # later BMTC arrival can still win with a much better onward Metro route.
    reachable = reachable[:max(1, int(max_interchanges)) * 2]

    # Load the walking network and destination Metro station once.
    graph, stations, entrances = load_walking_data()

    destination_metros = nearest_reachable_stations(
        destination_lat,
        destination_lon,
        graph,
        stations,
        entrances,
        limit=5,
    )

    station_lookup = stations.set_index("stop_id")["stop_name"].to_dict()

    journeys = []

    for candidate in reachable:
        for destination_metro in destination_metros:
            interchange = candidate["interchange"]
            label = candidate["label"]

            station_id = str(interchange["metro_station_id"])
            station_name = station_lookup.get(station_id)

            if not station_name:
                continue

            origin_id = label["origin_id"]
            origin_info = origin_details[origin_id]

            bmtc_path = label["path"]
            bmtc_legs = build_legs(bmtc_path, bmtc_stops)

            bmtc_arrival_seconds = label["arrival"]

            # Add modelled interchange walking plus a conservative
            # three-minute allowance for entering and reaching the platform.
            interchange_minutes = (
                candidate["walk_minutes"] + 3.0
            )

            raw_metro_ready = requested_dt + timedelta(
                seconds=bmtc_arrival_seconds - requested_seconds
            ) + timedelta(minutes=interchange_minutes)

            metro_ready = raw_metro_ready.replace(
                second=0,
                microsecond=0,
            )

            if metro_ready < raw_metro_ready:
                metro_ready += timedelta(minutes=1)

            if metro_ready.date() != requested_dt.date():
                continue

            metro_result = plan_metro(
                station_name,
                destination_metro["station_name"],
                travel_date,
                metro_ready.strftime("%H:%M"),
            )

            if metro_result.get("status") != "success":
                continue

            metro_legs = metro_result.get("legs", [])

            if not metro_legs:
                continue

            metro_fare = calculate_metro_journey_fare(metro_legs)

            bmtc_fare = calculate_bmtc_journey_fare(bmtc_legs)

            bmtc_distance = calculate_bmtc_journey_distance(bmtc_legs)

            if bmtc_distance.get("status") != "success":
                continue

            metro_distance = metro_fare.get("distance_km")

            if metro_distance is None:
                continue

            bmtc_emissions = calculate_bmtc_emission_scenarios(
                bmtc_distance["distance_km"]
            )

            metro_emissions = calculate_emissions(
                metro_distance,
                "metro_ips",
            )

            metro_emission_kg = metro_emissions["emissions_kg_co2e"]

            egress_minutes = destination_metro["walking_minutes"]

            total_minutes = (
                (bmtc_arrival_seconds - requested_seconds) / 60
                + interchange_minutes
                + metro_result["duration_minutes"]
                + egress_minutes
            )

            total_walking_metres = (
                origin_info["stop"]["straight_line_distance_m"]
                + candidate["walk_metres"]
                + destination_metro["walking_distance_m"]
            )

            # Preserve the BMTC fuel scenarios rather than assuming a fuel type.
            combined_scenarios = {}

            for fuel, scenario in bmtc_emissions.get("scenarios", {}).items():
                if isinstance(scenario, dict):
                    bus_kg = scenario.get("emissions_kg_co2e")
                else:
                    bus_kg = scenario

                if bus_kg is not None:
                    combined_scenarios[fuel] = {
                        "bmtc_emissions_kg_co2e": round(float(bus_kg), 4),
                        "metro_emissions_kg_co2e": round(
                            float(metro_emission_kg), 4
                        ),
                        "total_emissions_kg_co2e": round(
                            float(bus_kg) + float(metro_emission_kg), 4
                        ),
                    }

            journeys.append({
                "total_estimated_duration_minutes": round(total_minutes, 1),
                "total_estimated_walking_metres": round(
                    total_walking_metres, 1
                ),
                "origin_access": {
                    "stop_id": origin_id,
                    "stop_name": origin_info["stop"]["stop_name"],
                    "distance_m": round(
                        origin_info["stop"]["straight_line_distance_m"], 1
                    ),
                    "walking_minutes": round(
                        origin_info["walking_minutes"], 1
                    ),
                },
                "bmtc_journey": {
                    "legs": bmtc_legs,
                    "fare": bmtc_fare,
                    "distance": bmtc_distance,
                    "arrival_at_interchange": bmtc_legs[-1]["arrival_time"],
                },
                "interchange": {
                    "metro_station_id": station_id,
                    "metro_station_name": station_name,
                    "bmtc_stop_id": str(interchange["bmtc_stop_id"]),
                    "bmtc_stop_name": str(interchange["bmtc_stop_name"]),
                    "walking_distance_m": candidate["walk_metres"],
                    "walking_minutes": candidate["walk_minutes"],
                    "additional_platform_buffer_minutes": 3.0,
                },
                "metro_journey": metro_result,
                "metro_fare": metro_fare,
                "destination_metro": destination_metro,
                "emissions": {
                    "bmtc_scenarios": bmtc_emissions,
                    "metro": metro_emissions,
                    "combined_scenarios": combined_scenarios,
                    "is_estimate": True,
                },
                "fare": {
                    "bmtc": bmtc_fare,
                    "metro": metro_fare,
                },
                "data_warning": (
                    "BMTC timetable is community-published and scheduled. "
                    "Interchange walking is modelled. Metro uses scheduled "
                    "GTFS timings. No live transit positions are available."
                ),
            })
    if not journeys:
        return {
            "status": "unavailable",
            "message": (
                "BMTC interchange stops were reachable, but no usable "
                "onward Metro journey was found."
            ),
        }

    # Rank by conservative estimated emissions first.
    # BMTC vehicle fuel type is unknown, so use the highest available
    # emissions scenario for each journey. Duration breaks ties.
    for journey in journeys:
        scenarios = (
            journey.get("emissions", {})
            .get("combined_scenarios", {})
        )

        scenario_totals = [
            float(scenario["total_emissions_kg_co2e"])
            for scenario in scenarios.values()
            if isinstance(scenario, dict)
            and scenario.get("total_emissions_kg_co2e") is not None
        ]

        journey["emissions"]["ranking_emissions_kg_co2e"] = (
            round(max(scenario_totals), 4)
            if scenario_totals
            else None
        )

    journeys.sort(
        key=lambda item: (
            item["emissions"]["ranking_emissions_kg_co2e"]
            if item["emissions"]["ranking_emissions_kg_co2e"] is not None
            else float("inf"),
            item["total_estimated_duration_minutes"],
        )
    )

    return {
        "status": "success",
        "mode": "BMTC + Metro",
        "travel_date": travel_date,
        "requested_departure": departure_time,
        "origin_coordinates": [origin_lat, origin_lon],
        "destination_coordinates": [destination_lat, destination_lon],
        "best_journey": journeys[0],
        "alternative_journeys": journeys[1:],
        "journeys_compared": len(journeys),
        "search_method": "shared_BMTC_scan_then_all_reachable_Metro_checks",
        "limitations": [
            "Current-feed BMTC stops are matched to Metro entrances using approximate walking distances (straight-line distance multiplied by 1.3); these are not pedestrian-network routes.",
            "A three-minute platform access buffer is assumed.",
            "BMTC and Metro use scheduled timetable data, not live positions.",
            "BMTC vehicle fuel type is unknown; emissions are scenarios.",
            "Walking access and egress estimates are not field verified.",
        ],
    }


if __name__ == "__main__":
    result = plan_bmtc_then_metro(
        origin_lat=12.9585,
        origin_lon=77.5635,
        destination_lat=13.0105,
        destination_lon=77.5540,
        travel_date="2026-11-18",
        departure_time="08:00",
    )

    print("\n===== BMTC + METRO RESULT =====")
    print("Status:", result["status"])

    if result["status"] == "success":
        journey = result["best_journey"]

        print(
            "Total duration:",
            journey["total_estimated_duration_minutes"],
            "minutes",
        )
        print(
            "Total walking:",
            journey["total_estimated_walking_metres"],
            "metres",
        )
        print("Interchange:", journey["interchange"])
        print("BMTC legs:", len(journey["bmtc_journey"]["legs"]))
        print("Metro legs:", len(journey["metro_journey"]["legs"]))
        print("Combined emissions:", journey["emissions"]["combined_scenarios"])
        print("BMTC fare:", journey["fare"]["bmtc"])
        print("Metro fare:", journey["fare"]["metro"])
    else:
        print("Message:", result.get("message"))
