from datetime import datetime, timedelta
import math

from app.routing.bmtc_stop_matcher import find_nearby_bmtc_stops
from app.routing.bmtc_planner import (
    load_bmtc_data,
    active_bmtc_services,
    to_seconds,
    format_time
)
from app.routing.bmtc_duration_predictor import predict_segment_duration


WALKING_SPEED_M_PER_MIN = 80
TRANSFER_BUFFER_SECONDS = 300


def straight_line_distance_m(lat1, lon1, lat2, lon2):
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


def round_up_minute(value):
    value = value.replace(second=0, microsecond=0)

    if value < datetime.now().replace(
        hour=value.hour,
        minute=value.minute,
        second=0,
        microsecond=0
    ):
        pass

    return value


def build_legs(path, stops):
    """Combine consecutive stop connections on the same bus."""

    legs = []

    for segment in path:
        if legs and legs[-1]["trip_id"] == segment["trip_id"]:
            legs[-1]["to_stop"] = segment["to_stop"]
            legs[-1]["arrival"] = segment["arrival"]
        else:
            legs.append(segment.copy())

    stop_names = (
        stops.set_index("stop_id")["stop_name"].to_dict()
    )

    for leg in legs:
        leg["from_stop_name"] = stop_names.get(
            leg["from_stop"], leg["from_stop"]
        )
        leg["to_stop_name"] = stop_names.get(
            leg["to_stop"], leg["to_stop"]
        )

        leg["departure_time"] = format_time(leg["departure"])
        leg["arrival_time"] = format_time(leg["arrival"])

    for index in range(1, len(legs)):
        previous = legs[index - 1]
        current = legs[index]

        current["transfer_wait_minutes"] = round(
            (current["departure"] - previous["arrival"]) / 60,
            1
        )
        current["transfer_at"] = previous["to_stop_name"]

    return legs


def add_duration_estimates(legs, path):
    """Attach historical segment estimates to each bus leg."""

    estimates = {}

    for segment in path:
        trip_id = segment["trip_id"]

        entry = estimates.setdefault(
            trip_id,
            {
                "predicted": 0.0,
                "scheduled": 0.0,
                "successful": 0,
                "total": 0,
                "methods": set()
            }
        )

        entry["scheduled"] += (
            segment["arrival"] - segment["departure"]
        ) / 60

        entry["total"] += 1

        try:
            prediction = predict_segment_duration(
                route_id=segment["route_id"],
                stop_id=segment["from_stop"],
                next_stop_id=segment["to_stop"],
                departure_time=format_time(segment["departure"])
            )
        except Exception:
            prediction = {"status": "unavailable"}

        if prediction.get("status") == "success":
            entry["predicted"] += prediction[
                "predicted_duration_min"
            ]
            entry["successful"] += 1
            entry["methods"].add(prediction["method"])

    for leg in legs:
        entry = estimates[leg["trip_id"]]

        leg["scheduled_segment_duration_min"] = round(
            entry["scheduled"], 2
        )

        if entry["successful"] == entry["total"]:
            leg["duration_estimate_min"] = round(
                entry["predicted"], 2
            )

            methods = sorted(entry["methods"])

            leg["duration_estimate_method"] = (
                methods[0] if len(methods) == 1 else "mixed"
            )

            leg["duration_estimate_status"] = "success"
        else:
            leg["duration_estimate_min"] = None
            leg["duration_estimate_method"] = "unavailable"
            leg["duration_estimate_status"] = "incomplete"

        leg["duration_estimate_note"] = (
            "Historical scheduled duration estimate; "
            "not a live traffic prediction."
        )


def plan_bmtc_from_gps(
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
    Plan BMTC travel from arbitrary GPS coordinates.

    All origin candidates are searched in one timetable scan.
    Destination candidates are evaluated from the resulting labels.
    """

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
            "message": "No BMTC boarding stop found near the origin.",
            "origin_search": origin_matches
        }

    if destination_matches["status"] != "success":
        return {
            "status": "unavailable",
            "message": "No BMTC stop found near the destination.",
            "destination_search": destination_matches
        }

    requested_dt = datetime.strptime(
        f"{travel_date} {departure_time}",
        "%Y-%m-%d %H:%M"
    )

    requested_seconds = to_seconds(departure_time)

    connections, stops, calendar = load_bmtc_data()
    services = active_bmtc_services(calendar, travel_date)

    if not services:
        return {
            "status": "unavailable",
            "message": (
                "No BMTC service calendar available for this date. "
                "The available feed covers 2024-11-07 to 2024-11-13."
            )
        }

    connections = connections[
        connections["service_id"].astype(str).isin(services)
    ]

    stop_names = (
        stops.set_index("stop_id")["stop_name"].to_dict()
    )

    # Seed all origin stops into one shared search.
    best = {}
    origin_details = {}

    for candidate in origin_matches["matches"]:
        access_distance = candidate["straight_line_distance_m"]
        access_minutes = access_distance / WALKING_SPEED_M_PER_MIN

        ready_dt = requested_dt + timedelta(minutes=access_minutes)

        ready_dt = ready_dt.replace(second=0, microsecond=0)

        if ready_dt < requested_dt + timedelta(minutes=access_minutes):
            ready_dt += timedelta(minutes=1)

        if ready_dt.date() != requested_dt.date():
            continue

        ready_seconds = to_seconds(ready_dt.strftime("%H:%M"))
        stop_id = candidate["stop_id"]

        origin_details[stop_id] = {
            "stop": candidate,
            "walking_minutes": access_minutes,
            "ready_time": ready_dt.strftime("%H:%M")
        }

        old = best.get(stop_id)

        if old is None or ready_seconds < old["arrival"]:
            best[stop_id] = {
                "arrival": ready_seconds,
                "path": [],
                "origin_id": stop_id
            }

    if not best:
        return {
            "status": "unavailable",
            "message": (
                "Walking access reaches the next calendar day; "
                "this historical timetable search does not support "
                "that date transition."
            )
        }

    minimum_ready = min(
        label["arrival"] for label in best.values()
    )

    # One shared scan for every origin candidate.
    eligible = connections[
        connections["departure_seconds"] >= minimum_ready
    ]

    active_trips = set()
    trip_paths = {}

    print(
        "Searching shared BMTC timetable:",
        len(eligible),
        "connections...",
        flush=True
    )

    transfer_buffer = TRANSFER_BUFFER_SECONDS

    for row in eligible.itertuples(index=False):
        trip_id = row.trip_id
        from_stop = row.stop_id
        to_stop = row.next_stop_id

        departure = row.departure_seconds
        arrival = row.arrival_seconds

        if trip_id in active_trips:
            path = trip_paths[trip_id]

        elif from_stop in best:
            label = best[from_stop]

            required_wait = (
                0 if not label["path"] else transfer_buffer
            )

            if label["arrival"] + required_wait > departure:
                continue

            active_trips.add(trip_id)
            path = label["path"]

        else:
            continue

        segment = {
            "trip_id": trip_id,
            "route_id": row.route_id,
            "route_short_name": row.route_short_name,
            "route_long_name": row.route_long_name,
            "from_stop": from_stop,
            "to_stop": to_stop,
            "departure": departure,
            "arrival": arrival
        }

        new_path = path + [segment]
        trip_paths[trip_id] = new_path

        old = best.get(to_stop)

        if old is None or arrival < old["arrival"]:
            best[to_stop] = {
                "arrival": arrival,
                "path": new_path,
                "origin_id": (
                    best[from_stop]["origin_id"]
                    if from_stop in best
                    else None
                )
            }

    # Evaluate all destination candidates.
    journeys = []

    for destination in destination_matches["matches"]:
        destination_id = destination["stop_id"]

        if destination_id not in best:
            continue

        label = best[destination_id]
        path = label["path"]

        if not path:
            continue

        origin_id = label["origin_id"]

        if origin_id not in origin_details:
            continue

        origin_info = origin_details[origin_id]
        origin_stop = origin_info["stop"]

        legs = build_legs(path, stops)
        add_duration_estimates(legs, path)

        arrival_seconds = label["arrival"]

        egress_distance = straight_line_distance_m(
            destination["latitude"],
            destination["longitude"],
            destination_lat,
            destination_lon
        )

        egress_minutes = (
            egress_distance / WALKING_SPEED_M_PER_MIN
        )

        access_minutes = origin_info["walking_minutes"]

        # Arrival - original departure already includes access and waiting.
        total_minutes = (
            (arrival_seconds - requested_seconds) / 60
            + egress_minutes
        )

        bus_start_seconds = legs[0]["departure"]

        bmtc_journey = {
            "status": "success",
            "travel_date": travel_date,
            "origin": origin_stop["stop_name"],
            "destination": destination["stop_name"],
            "departure": format_time(bus_start_seconds),
            "arrival": format_time(arrival_seconds),
            "duration_minutes": round(
                (arrival_seconds - bus_start_seconds) / 60, 1
            ),
            "number_of_bus_legs": len(legs),
            "legs": legs,
            "data_warning": (
                "Historical BMTC GTFS feed valid only from "
                "2024-11-07 to 2024-11-13. Not current service information."
            )
        }

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
            "bmtc_journey": bmtc_journey
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
        "travel_date": travel_date,
        "requested_departure": departure_time,
        "origin_coordinates": [origin_lat, origin_lon],
        "destination_coordinates": [destination_lat, destination_lon],
        "best_journey": journeys[0],
        "alternative_journeys": journeys[1:],
        "journeys_compared": len(journeys),
        "search_method": "single_shared_timetable_scan",
        "limitations": [
            "BMTC timetable is historical, valid only 2024-11-07 to 2024-11-13.",
            "Walking access and egress use straight-line distances.",
            "Walking speed is assumed to be 80 metres per minute.",
            "No live BMTC positions, traffic or delays are included."
        ]
    }
