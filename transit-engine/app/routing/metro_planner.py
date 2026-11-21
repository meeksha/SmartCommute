from pathlib import Path
from datetime import datetime
import argparse
from functools import lru_cache
import pandas as pd

METRO_DIR = Path(__file__).resolve().parents[2] / "data" / "processed" / "metro" / "standard"

ALIASES = {
    "majestic": "Nadaprabhu Kempegowda Station, Majestic",
    "kempegowda": "Nadaprabhu Kempegowda Station, Majestic",
    "yeshwanthpur": "Yeshwantpur",
}


def gtfs_seconds(value):
    if pd.isna(value) or not str(value).strip():
        return None
    try:
        h, m, s = map(int, str(value).split(":"))
        return h * 3600 + m * 60 + s
    except (ValueError, TypeError):
        return None


def seconds_time(value):
    value = int(value)
    return f"{value // 3600:02d}:{(value % 3600) // 60:02d}:{value % 60:02d}"


METRO_SEARCH_HORIZON_SECONDS = 3 * 3600


@lru_cache(maxsize=8)
def active_services(date):
    date_text = date.strftime("%Y%m%d")
    weekday = date.strftime("%A").lower()

    calendar = pd.read_csv(METRO_DIR / "calendar.csv", dtype=str)
    exceptions = pd.read_csv(
        METRO_DIR / "calendar_dates.csv", dtype=str
    )

    active = set()

    for _, row in calendar.iterrows():
        if row["start_date"] <= date_text <= row["end_date"]:
            if row[weekday] == "1":
                active.add(row["service_id"])

    for _, row in exceptions[
        exceptions["date"] == date_text
    ].iterrows():
        if row["exception_type"] == "1":
            active.add(row["service_id"])
        elif row["exception_type"] == "2":
            active.discard(row["service_id"])

    return active


@lru_cache(maxsize=4)
def load_metro_data(date):
    stops = pd.read_csv(METRO_DIR / "stops.csv", dtype=str)
    trips = pd.read_csv(METRO_DIR / "trips.csv", dtype=str)
    times = pd.read_csv(METRO_DIR / "stop_times.csv", dtype=str)
    routes = pd.read_csv(METRO_DIR / "routes.csv", dtype=str)
    transfers = pd.read_csv(METRO_DIR / "transfers.csv", dtype=str)

    trips = trips[trips["service_id"].isin(active_services(date))].copy()
    times = times[times["trip_id"].isin(trips["trip_id"])].copy()

    times["stop_sequence"] = pd.to_numeric(
        times["stop_sequence"], errors="coerce"
    )
    times["departure"] = times["departure_time"].map(gtfs_seconds)
    times["arrival"] = times["arrival_time"].map(gtfs_seconds)
    times = times.dropna(
        subset=["stop_sequence", "departure", "arrival"]
    )
    times = times.sort_values(["trip_id", "stop_sequence"])

    grouped = times.groupby("trip_id", sort=False)
    times["to_stop"] = grouped["stop_id"].shift(-1)
    times["next_arrival"] = grouped["arrival"].shift(-1)
    connections = times.dropna(
        subset=["to_stop", "next_arrival"]
    ).copy()

    connections = connections.merge(
        trips[["trip_id", "route_id", "trip_headsign"]],
        on="trip_id",
        how="inner"
    )

    connections["next_arrival"] = pd.to_numeric(
        connections["next_arrival"]
    )
    connections = connections.rename(columns={
        "stop_id": "from_stop",
        "next_arrival": "to_arrival"
    })
    connections = connections.sort_values(
        ["departure", "arrival"]
    ).reset_index(drop=True)

    transfers = transfers.rename(columns={
        "from_stop_id": "from_stop",
        "to_stop_id": "to_stop"
    })
    transfers["transfer_type"] = pd.to_numeric(
        transfers["transfer_type"], errors="coerce"
    )
    transfers["min_transfer_time"] = pd.to_numeric(
        transfers["min_transfer_time"], errors="coerce"
    ).fillna(0)

    # Rules indexed by the platform where the next train is boarded.
    transfer_lookup = {}

    for row in transfers.to_dict("records"):
        if row["transfer_type"] == 3:
            continue

        key = (row["to_stop"], row["to_route_id"])
        transfer_lookup.setdefault(key, []).append({
            "from_stop": row["from_stop"],
            "from_route": row["from_route_id"],
            "minimum": int(row["min_transfer_time"])
        })

    return stops, routes, connections, transfer_lookup


def find_station(stops, name):
    requested = name.strip()
    requested = ALIASES.get(requested.casefold(), requested)

    stations = stops[stops["location_type"] == "1"].copy()
    exact = stations[
        stations["stop_name"].str.casefold() == requested.casefold()
    ]

    if exact.empty:
        matches = stations[
            stations["stop_name"].str.contains(
                requested, case=False, na=False, regex=False
            )
        ]
        if len(matches) == 1:
            exact = matches
        else:
            choices = matches["stop_name"].tolist()
            raise ValueError(
                f"Station '{name}' not found or ambiguous. "
                f"Possible matches: {choices[:10]}"
            )

    station_id = exact.iloc[0]["stop_id"]
    platforms = set(
        stops.loc[
            stops["parent_station"] == station_id, "stop_id"
        ].tolist()
    )
    platforms.add(station_id)
    return station_id, platforms


def plan_metro(origin, destination, travel_date, departure_time):
    date = datetime.strptime(travel_date, "%Y-%m-%d").date()
    time_text = departure_time
    if len(time_text.split(":")) == 2:
        time_text += ":00"

    requested = gtfs_seconds(time_text)
    if requested is None:
        raise ValueError("Departure time must be HH:MM or HH:MM:SS.")

    stops, routes, connections, transfer_lookup = load_metro_data(date)

    origin_id, origin_platforms = find_station(stops, origin)
    destination_id, destination_platforms = find_station(
        stops, destination
    )

    if origin_id == destination_id:
        return {
            "status": "success",
            "origin": origin,
            "destination": destination,
            "departure": seconds_time(requested),
            "arrival": seconds_time(requested),
            "duration_minutes": 0,
            "legs": []
        }

    # State = (platform stop ID, route used to arrive there).
    # Keeping route in the state prevents invalid cross-line transfers.
    labels = {}
    previous = {}

    for platform in origin_platforms:
        state = (platform, None)
        labels[state] = requested

    labels_at_stop = {}

    def set_label(state, arrival, predecessor):
        old = labels.get(state, float("inf"))
        if arrival < old:
            labels[state] = arrival
            previous[state] = predecessor
            labels_at_stop.setdefault(state[0], {})[state[1]] = arrival

    for platform in origin_platforms:
        labels_at_stop.setdefault(platform, {})[None] = requested

    # Connections are sorted by departure: start at the requested time and
    # stop after a bounded horizon instead of scanning the whole day.
    start_index = int(connections["departure"].searchsorted(requested, side="left"))
    horizon = requested + METRO_SEARCH_HORIZON_SECONDS
    for connection in connections.iloc[start_index:].itertuples(index=False):
        if connection.departure > horizon:
            break
        boarding_stop = connection.from_stop
        next_stop = connection.to_stop
        route = connection.route_id
        departure = int(connection.departure)
        arrival = int(connection.to_arrival)

        if departure < requested:
            continue

        candidates = []

        # Board at the same platform from the origin or continue on same line.
        for previous_route, ready_time in list(
            labels_at_stop.get(boarding_stop, {}).items()
        ):
            if previous_route is None or previous_route == route:
                candidates.append((
                    (boarding_stop, previous_route), ready_time, 0
                ))

        # Change platforms only when an explicit GTFS transfer rule exists.
        for rule in transfer_lookup.get((boarding_stop, route), []):
            previous_state = (rule["from_stop"], rule["from_route"])
            ready_time = labels.get(previous_state, float("inf"))
            if ready_time != float("inf"):
                candidates.append((
                    previous_state, ready_time, rule["minimum"]
                ))

        for previous_state, ready_time, minimum_transfer in candidates:
            if ready_time + minimum_transfer > departure:
                continue

            new_state = (next_stop, route)
            predecessor = {
                "state": previous_state,
                "trip_id": connection.trip_id,
                "route_id": route,
                "headsign": connection.trip_headsign,
                "from_stop": boarding_stop,
                "to_stop": next_stop,
                "departure": departure,
                "arrival": arrival
            }

            set_label(new_state, arrival, predecessor)

    # Earliest reachable destination platform, across all incoming lines.
    destinations = [
        (state, arrival)
        for state, arrival in labels.items()
        if state[0] in destination_platforms
    ]

    if not destinations:
        return {
            "status": "unavailable",
            "message": (
                "No scheduled Metro journey found for this date and time."
            ),
            "legs": []
        }

    final_state, final_arrival = min(
        destinations, key=lambda item: item[1]
    )

    # Reconstruct the connection sequence.
    segments = []
    current = final_state
    visited = set()

    while current in previous:
        if current in visited:
            raise RuntimeError("Cycle detected while reconstructing journey.")
        visited.add(current)

        item = previous[current]
        segments.append(item)
        current = item["state"]

    segments.reverse()

    if not segments:
        return {
            "status": "unavailable",
            "message": "No usable train connection found.",
            "legs": []
        }

    # Combine consecutive stop-to-stop connections on the same train.
    legs = []

    for segment in segments:
        if legs and legs[-1]["trip_id"] == segment["trip_id"]:
            legs[-1]["to_stop"] = segment["to_stop"]
            legs[-1]["arrival"] = segment["arrival"]
            legs[-1]["stop_ids"].append(segment["to_stop"])
        else:
            legs.append({
                "stop_ids": [segment["from_stop"], segment["to_stop"]],
                "trip_id": segment["trip_id"],
                "route_id": segment["route_id"],
                "headsign": segment["headsign"],
                "from_stop": segment["from_stop"],
                "to_stop": segment["to_stop"],
                "departure": segment["departure"],
                "arrival": segment["arrival"]
            })

    stop_names = stops.set_index("stop_id")["stop_name"].to_dict()
    route_names = routes.set_index("route_id")[
        "route_long_name"
    ].to_dict()

    for leg in legs:
        leg["from_station"] = stop_names.get(
            leg["from_stop"], leg["from_stop"]
        )
        leg["to_station"] = stop_names.get(
            leg["to_stop"], leg["to_stop"]
        )
        leg["route_name"] = route_names.get(
            leg["route_id"], leg["route_id"]
        )
        leg["departure_time"] = seconds_time(leg["departure"])
        leg["arrival_time"] = seconds_time(leg["arrival"])

    for index, leg in enumerate(legs):
        if index > 0:
            previous_leg = legs[index - 1]
            leg["transfer_station"] = previous_leg["to_station"]
            leg["transfer_wait_minutes"] = round(
                (leg["departure"] - previous_leg["arrival"]) / 60, 1
            )

    return {
        "status": "success",
        "travel_date": travel_date,
        "origin": origin,
        "destination": destination,
        "departure": seconds_time(requested),
        "arrival": seconds_time(final_arrival),
        "duration_minutes": round((final_arrival - requested) / 60, 1),
        "legs": legs,
        "note": (
            "Scheduled standard-feed Metro timings only. "
            "No live delays or real-time train positions."
        )
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Bengaluru Metro timetable planner"
    )
    parser.add_argument("--origin", required=True)
    parser.add_argument("--destination", required=True)
    parser.add_argument("--date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--time", required=True, help="HH:MM")
    args = parser.parse_args()

    result = plan_metro(
        args.origin, args.destination, args.date, args.time
    )

    print("\nMETRO JOURNEY RESULT")
    print("--------------------")

    for key, value in result.items():
        if key != "legs":
            print(f"{key}: {value}")

    for index, leg in enumerate(result.get("legs", []), start=1):
        print(f"\nLeg {index}: {leg['route_name']}")
        print(f"Trip ID: {leg['trip_id']}")
        print(
            f"{leg['from_station']} ({leg['departure_time']}) "
            f"-> {leg['to_station']} ({leg['arrival_time']})"
        )
        print(f"Train destination: {leg['headsign']}")
        if "transfer_wait_minutes" in leg:
            print(
                f"Transfer at {leg['transfer_station']}: "
                f"{leg['transfer_wait_minutes']} minutes"
            )
