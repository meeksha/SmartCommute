from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from app.routing.metro_planner import load_metro_data
from app.routing.bmtc_latest_planner import (
    load_bmtc_latest_data,
    active_bmtc_services,
)

TRAVEL_DATE = "2026-11-18"
MAX_STRAIGHT_LINE_DISTANCE_M = 300
STOPS_PER_STATION = 3
WALKING_SPEED_M_PER_MIN = 80

OUTPUT = Path(
    "data/processed/bmtc_latest/"
    "metro_bmtc_current_interchanges.csv"
)

print("Loading current Metro and BMTC feeds...")

metro_stops, _, _, _ = load_metro_data(date(2026, 11, 18))
connections, bmtc_stops, calendar = load_bmtc_latest_data()

services = active_bmtc_services(calendar, TRAVEL_DATE)

active_connections = connections[
    connections["service_id"].isin(services)
]

active_ids = (
    set(active_connections["stop_id"].astype(str))
    | set(active_connections["next_stop_id"].astype(str))
)

bmtc_stops = bmtc_stops.copy()
bmtc_stops["stop_id"] = bmtc_stops["stop_id"].astype(str)
bmtc_stops["stop_lat"] = pd.to_numeric(
    bmtc_stops["stop_lat"], errors="coerce"
)
bmtc_stops["stop_lon"] = pd.to_numeric(
    bmtc_stops["stop_lon"], errors="coerce"
)

bmtc_stops = bmtc_stops.dropna(
    subset=["stop_lat", "stop_lon"]
)
bmtc_stops = bmtc_stops[
    bmtc_stops["stop_id"].isin(active_ids)
].reset_index(drop=True)

entrances = metro_stops[
    pd.to_numeric(metro_stops["location_type"], errors="coerce") == 2
].copy()

entrances = entrances.dropna(
    subset=["parent_station", "stop_lat", "stop_lon"]
)

entrances["stop_lat"] = pd.to_numeric(entrances["stop_lat"])
entrances["stop_lon"] = pd.to_numeric(entrances["stop_lon"])

stations = metro_stops[
    pd.to_numeric(metro_stops["location_type"], errors="coerce") == 1
].copy()

station_names = stations.set_index("stop_id")["stop_name"].to_dict()

bus_lat = bmtc_stops["stop_lat"].to_numpy(dtype=float)
bus_lon = bmtc_stops["stop_lon"].to_numpy(dtype=float)

earth_radius = 6371000
candidate_rows = []

print("Finding nearby active BMTC stops...")

for entrance in entrances.itertuples(index=False):
    lat1 = np.radians(float(entrance.stop_lat))
    lon1 = np.radians(float(entrance.stop_lon))
    lat2 = np.radians(bus_lat)
    lon2 = np.radians(bus_lon)

    delta_lat = lat2 - lat1
    delta_lon = lon2 - lon1

    a = (
        np.sin(delta_lat / 2) ** 2
        + np.cos(lat1) * np.cos(lat2)
        * np.sin(delta_lon / 2) ** 2
    )

    distances = (
        2 * earth_radius
        * np.arcsin(np.sqrt(np.clip(a, 0, 1)))
    )

    eligible_indices = np.where(
        distances <= MAX_STRAIGHT_LINE_DISTANCE_M
    )[0]

    if len(eligible_indices) == 0:
        continue

    nearest = eligible_indices[
        np.argsort(distances[eligible_indices])[:STOPS_PER_STATION]
    ]

    station_id = str(entrance.parent_station)

    for index in nearest:
        stop = bmtc_stops.iloc[index]
        straight_distance = float(distances[index])

        candidate_rows.append({
            "metro_station_id": station_id,
            "metro_station_name": station_names.get(
                station_id, station_id
            ),
            "metro_entrance_name": str(entrance.stop_name),
            "bmtc_stop_id": str(stop["stop_id"]),
            "bmtc_stop_name": str(stop["stop_name"]),
            "bmtc_lat": float(stop["stop_lat"]),
            "bmtc_lon": float(stop["stop_lon"]),
            "straight_line_distance_m": round(
                straight_distance, 1
            ),
        })

if not candidate_rows:
    raise SystemExit("No interchange candidates found.")

result = pd.DataFrame(candidate_rows)

# Keep the closest entrance for each station-stop pair.
result = (
    result.sort_values("straight_line_distance_m")
    .drop_duplicates(
        subset=["metro_station_id", "bmtc_stop_id"]
    )
)

# Keep the closest three unique BMTC stops per Metro station.
result = (
    result.sort_values("straight_line_distance_m")
    .groupby("metro_station_id", group_keys=False)
    .head(STOPS_PER_STATION)
    .copy()
)

# Explicit approximation; not represented as an OSM walking route.
result["estimated_total_walk_m"] = (
    result["straight_line_distance_m"] * 1.3
).round(1)

result["estimated_walk_minutes"] = (
    result["estimated_total_walk_m"]
    / WALKING_SPEED_M_PER_MIN
).round(1)

result["interchange_status"] = "CURRENT_FEED_APPROXIMATE_WALK"
result["walking_distance_method"] = "straight_line_x_1.3"
result["feed_version"] = "2026-11-09"

OUTPUT.parent.mkdir(parents=True, exist_ok=True)
result.to_csv(OUTPUT, index=False)

print("\n===== NEW INTERCHANGE DATASET =====")
print("Saved:", OUTPUT)
print("Candidate connections:", len(result))
print("Metro stations covered:", result["metro_station_id"].nunique())

print("\n===== KR MARKET CANDIDATES =====")
print(
    result[result["metro_station_id"] == "KRMT"][
        [
            "metro_station_name",
            "bmtc_stop_id",
            "bmtc_stop_name",
            "straight_line_distance_m",
            "estimated_total_walk_m",
            "estimated_walk_minutes",
        ]
    ].to_string(index=False)
)

print("\nOld interchange dataset was not modified.")
