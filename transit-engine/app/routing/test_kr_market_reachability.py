import numpy as np
import pandas as pd
from datetime import datetime, timedelta

from app.routing.bmtc_latest_planner import (
    load_bmtc_latest_data,
    active_bmtc_services,
    to_seconds,
    TRANSFER_BUFFER_SECONDS,
    format_time,
)
from app.routing.bmtc_latest_stop_matcher import find_nearby_bmtc_stops

DATE = "2026-11-18"
DEPARTURE = "08:00"
ORIGIN_LAT = 12.9585
ORIGIN_LON = 77.5635

print("Loading timetable and stops...")
connections, stops, calendar = load_bmtc_latest_data()

services = active_bmtc_services(calendar, DATE)
connections = connections[
    connections["service_id"].isin(services)
].sort_values(["departure_seconds", "arrival_seconds"])

# Find current-feed BMTC stops near the KR Market Metro station.
target = stops.copy()
target["stop_lat"] = pd.to_numeric(target["stop_lat"], errors="coerce")
target["stop_lon"] = pd.to_numeric(target["stop_lon"], errors="coerce")
target = target.dropna(subset=["stop_lat", "stop_lon"])

lat1 = np.radians(12.960879)
lon1 = np.radians(77.574660)
lat2 = np.radians(target["stop_lat"].to_numpy(dtype=float))
lon2 = np.radians(target["stop_lon"].to_numpy(dtype=float))

a = (
    np.sin((lat2 - lat1) / 2) ** 2
    + np.cos(lat1) * np.cos(lat2)
    * np.sin((lon2 - lon1) / 2) ** 2
)
target["distance_m"] = (
    6371000 * 2 * np.arcsin(np.sqrt(a))
)

target = target[target["distance_m"] <= 600].sort_values("distance_m")
target = target[
    target["stop_id"].astype(str).isin(
        set(connections["stop_id"].astype(str))
        | set(connections["next_stop_id"].astype(str))
    )
]

target_ids = set(target["stop_id"].astype(str))

print("\nKR Market target stops:")
print(
    target[["stop_id", "stop_name", "distance_m"]]
    .head(15).to_string(index=False)
)

origin_matches = find_nearby_bmtc_stops(
    ORIGIN_LAT, ORIGIN_LON, radius_m=1000, limit=5
)

if origin_matches["status"] != "success":
    raise SystemExit("No origin BMTC stops found.")

requested_dt = datetime.strptime(
    f"{DATE} {DEPARTURE}", "%Y-%m-%d %H:%M"
)
requested_seconds = to_seconds(DEPARTURE)

best = {}

for candidate in origin_matches["matches"]:
    access_minutes = (
        candidate["straight_line_distance_m"] / 80
    )
    raw_ready = requested_dt + timedelta(minutes=access_minutes)
    ready_dt = raw_ready.replace(second=0, microsecond=0)

    if ready_dt < raw_ready:
        ready_dt += timedelta(minutes=1)

    if ready_dt.date() != requested_dt.date():
        continue

    stop_id = candidate["stop_id"]
    ready = to_seconds(ready_dt.strftime("%H:%M"))

    best[stop_id] = {
        "arrival": ready,
        "path": [],
        "origin_id": stop_id,
    }

minimum_ready = min(item["arrival"] for item in best.values())
eligible = connections[
    connections["departure_seconds"] >= minimum_ready
]

active_trips = set()
trip_paths = {}

print("\nScanning", len(eligible), "connections...")

for row in eligible.itertuples(index=False):
    trip_id = row.trip_id
    from_stop = str(row.stop_id)
    to_stop = str(row.next_stop_id)

    departure = int(row.departure_seconds)
    arrival = int(row.arrival_seconds)

    if trip_id in active_trips:
        path = trip_paths[trip_id]
    elif from_stop in best:
        label = best[from_stop]
        wait = 0 if not label["path"] else TRANSFER_BUFFER_SECONDS

        if label["arrival"] + wait > departure:
            continue

        active_trips.add(trip_id)
        path = label["path"]
    else:
        continue

    segment = {
        "trip_id": trip_id,
        "route": row.route_short_name,
        "from_stop": from_stop,
        "to_stop": to_stop,
        "departure": departure,
        "arrival": arrival,
    }

    new_path = path + [segment]
    trip_paths[trip_id] = new_path

    old = best.get(to_stop)

    if old is None or arrival < old["arrival"]:
        best[to_stop] = {
            "arrival": arrival,
            "path": new_path,
            "origin_id": best[from_stop]["origin_id"],
        }

reached = []

for stop_id in target_ids:
    if stop_id in best and best[stop_id]["path"]:
        label = best[stop_id]
        reached.append((stop_id, label))

print("\n===== REACHABILITY RESULT =====")
print("Target stops:", len(target_ids))
print("Reachable target stops:", len(reached))

stop_names = stops.set_index("stop_id")["stop_name"].to_dict()

for stop_id, label in sorted(reached, key=lambda x: x[1]["arrival"]):
    path = label["path"]
    print("\nStop:", stop_names.get(stop_id, stop_id), stop_id)
    print("Arrival:", format_time(label["arrival"]))
    print("Bus legs:", len(path))
    for leg in path:
        print(
            leg["route"],
            stop_names.get(leg["from_stop"], leg["from_stop"]),
            "->",
            stop_names.get(leg["to_stop"], leg["to_stop"]),
            format_time(leg["departure"]),
            "to",
            format_time(leg["arrival"]),
        )

if not reached:
    print("No KR Market interchange stop was reached by this search.")
    print("Origin candidates:")
    for item in origin_matches["matches"]:
        print(item)
