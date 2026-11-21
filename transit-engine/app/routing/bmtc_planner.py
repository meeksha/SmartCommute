from pathlib import Path
from datetime import datetime
from functools import lru_cache
import pandas as pd
from app.routing.bmtc_duration_predictor import predict_segment_duration


BASE = Path("data/processed")
TRANSFER_BUFFER_SECONDS = 300


def to_seconds(value):
    parts = list(map(int, str(value).split(":")))
    if len(parts) == 2:
        parts.append(0)
    if len(parts) != 3:
        raise ValueError("Time must be HH:MM or HH:MM:SS.")
    h, m, s = parts
    return h * 3600 + m * 60 + s


def format_time(seconds):
    seconds = int(seconds)
    h, remainder = divmod(seconds, 3600)
    m, s = divmod(remainder, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


@lru_cache(maxsize=1)
def load_bmtc_data():
    connections = pd.read_csv(
        BASE / "bmtc_connections.csv", dtype=str
    )
    stops = pd.read_csv(
        BASE / "bmtc_stops.csv", dtype=str
    )
    calendar = pd.read_csv(
        BASE / "bmtc_calendar.csv", dtype=str
    )

    for column in ["departure_seconds", "arrival_seconds"]:
        connections[column] = pd.to_numeric(
            connections[column], errors="coerce"
        )

    connections = connections.dropna(
        subset=["departure_seconds", "arrival_seconds"]
    )

    connections["departure_seconds"] = (
        connections["departure_seconds"].astype(int)
    )
    connections["arrival_seconds"] = (
        connections["arrival_seconds"].astype(int)
    )

    connections = connections.sort_values(
        "departure_seconds"
    ).reset_index(drop=True)

    return connections, stops, calendar


def active_bmtc_services(calendar, travel_date):
    date = datetime.strptime(travel_date, "%Y-%m-%d").date()
    weekday = date.strftime("%A").lower()
    date_number = date.strftime("%Y%m%d")

    active = calendar[
        (calendar[weekday] == "1")
        & (calendar["start_date"] <= date_number)
        & (calendar["end_date"] >= date_number)
    ]

    return set(active["service_id"].astype(str))


def find_bmtc_stop(stops, name):
    # Allow an exact stop ID, avoiding ambiguity from duplicate stop names.
    by_id = stops[
        stops["stop_id"].astype(str) == str(name).strip()
    ]

    if len(by_id) == 1:
        return by_id.iloc[0]

    exact = stops[
        stops["stop_name"].str.casefold() == name.strip().casefold()
    ]

    if len(exact) == 1:
        return exact.iloc[0]

    matches = stops[
        stops["stop_name"].str.contains(
            name.strip(), case=False, na=False, regex=False
        )
    ]

    if len(matches) == 1:
        return matches.iloc[0]

    if matches.empty:
        raise ValueError(f"BMTC stop not found: {name}")

    raise ValueError(
        f"Ambiguous stop '{name}'. Possible matches: "
        f"{matches['stop_name'].head(15).tolist()}"
    )


def plan_bmtc(
    origin,
    destination,
    travel_date,
    departure_time,
    transfer_buffer_minutes=5
):
    connections, stops, calendar = load_bmtc_data()

    services = active_bmtc_services(calendar, travel_date)

    if not services:
        return {
            "status": "unavailable",
            "message": (
                f"No BMTC service calendar available for {travel_date}. "
                "The available feed covers 2024-11-07 to 2024-11-13."
            ),
            "legs": []
        }

    connections = connections[
        connections["service_id"].astype(str).isin(services)
    ].copy()

    origin_stop = find_bmtc_stop(stops, origin)
    destination_stop = find_bmtc_stop(stops, destination)

    origin_id = origin_stop["stop_id"]
    destination_id = destination_stop["stop_id"]

    requested = to_seconds(departure_time)

    if origin_id == destination_id:
        return {
            "status": "success",
            "origin": origin_stop["stop_name"],
            "destination": destination_stop["stop_name"],
            "departure": format_time(requested),
            "arrival": format_time(requested),
            "duration_minutes": 0,
            "legs": []
        }

    # Each stop stores its earliest arrival and the path used.
    best = {
        origin_id: {
            "arrival": requested,
            "path": []
        }
    }

    # Preserve the path of passengers already aboard each trip.
    active_trips = set()
    trip_paths = {}

    transfer_buffer = int(transfer_buffer_minutes * 60)

    for row in connections.itertuples(index=False):
        trip_id = row.trip_id
        from_stop = row.stop_id
        to_stop = row.next_stop_id
        departure = row.departure_seconds
        arrival = row.arrival_seconds

        if departure < requested:
            continue

        # Continue travelling on a bus already boarded.
        if trip_id in active_trips:
            path = trip_paths[trip_id]

        # Otherwise, check whether the passenger can board here.
        elif from_stop in best:
            ready = best[from_stop]["arrival"]

            required_wait = (
                0 if from_stop == origin_id else transfer_buffer
            )

            if ready + required_wait > departure:
                continue

            active_trips.add(trip_id)
            path = best[from_stop]["path"]

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
                "path": new_path
            }

    if destination_id not in best:
        return {
            "status": "unavailable",
            "message": (
                "No scheduled BMTC journey found for these stops, "
                "date and departure time."
            ),
            "legs": []
        }

    path = best[destination_id]["path"]

    # Combine consecutive connections on the same bus trip.
    legs = []

    for segment in path:
        if legs and legs[-1]["trip_id"] == segment["trip_id"]:
            legs[-1]["to_stop"] = segment["to_stop"]
            legs[-1]["arrival"] = segment["arrival"]
        else:
            legs.append(segment.copy())

    # Add historical duration estimates without changing timetable routing.
    estimates_by_trip = {}

    for segment in path:
        trip_id = segment["trip_id"]
        scheduled_duration = (
            segment["arrival"] - segment["departure"]
        ) / 60

        try:
            prediction = predict_segment_duration(
                route_id=segment["route_id"],
                stop_id=segment["from_stop"],
                next_stop_id=segment["to_stop"],
                departure_time=format_time(segment["departure"])
            )
        except Exception:
            prediction = {"status": "unavailable"}

        entry = estimates_by_trip.setdefault(
            trip_id,
            {
                "predicted_total": 0.0,
                "scheduled_total": 0.0,
                "successful_segments": 0,
                "total_segments": 0,
                "methods": set()
            }
        )

        entry["scheduled_total"] += scheduled_duration
        entry["total_segments"] += 1

        if prediction.get("status") == "success":
            entry["predicted_total"] += prediction[
                "predicted_duration_min"
            ]
            entry["successful_segments"] += 1
            entry["methods"].add(prediction["method"])

    stop_names = stops.set_index("stop_id")["stop_name"].to_dict()

    for leg in legs:
        leg["from_stop_name"] = stop_names.get(
            leg["from_stop"], leg["from_stop"]
        )
        leg["to_stop_name"] = stop_names.get(
            leg["to_stop"], leg["to_stop"]
        )
        leg["departure_time"] = format_time(leg["departure"])
        leg["arrival_time"] = format_time(leg["arrival"])

        estimate = estimates_by_trip.get(leg["trip_id"])

        if estimate and estimate["successful_segments"] == estimate["total_segments"]:
            leg["duration_estimate_min"] = round(
                estimate["predicted_total"], 2
            )
            leg["scheduled_segment_duration_min"] = round(
                estimate["scheduled_total"], 2
            )

            methods = sorted(estimate["methods"])
            leg["duration_estimate_method"] = (
                methods[0] if len(methods) == 1 else "mixed"
            )
            leg["duration_estimate_status"] = "success"
        else:
            leg["duration_estimate_min"] = None
            leg["scheduled_segment_duration_min"] = (
                round(estimate["scheduled_total"], 2)
                if estimate else None
            )
            leg["duration_estimate_method"] = "unavailable"
            leg["duration_estimate_status"] = "incomplete"

        leg["duration_estimate_note"] = (
            "Historical schedule estimate; does not account for "
            "live traffic or delays. Does not change scheduled journey times."
        )

    for index in range(1, len(legs)):
        previous = legs[index - 1]
        current = legs[index]

        current["transfer_wait_minutes"] = round(
            (current["departure"] - previous["arrival"]) / 60, 1
        )
        current["transfer_at"] = previous["to_stop_name"]

    final_arrival = best[destination_id]["arrival"]

    return {
        "status": "success",
        "travel_date": travel_date,
        "origin": origin_stop["stop_name"],
        "destination": destination_stop["stop_name"],
        "departure": departure_time,
        "arrival": format_time(final_arrival),
        "duration_minutes": round(
            (final_arrival - requested) / 60, 1
        ),
        "number_of_bus_legs": len(legs),
        "legs": legs,
        "data_warning": (
            "Historical BMTC GTFS feed valid only from "
            "2024-11-07 to 2024-11-13. Not current service information."
        )
    }
