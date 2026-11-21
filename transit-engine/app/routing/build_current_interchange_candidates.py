import numpy as np
import pandas as pd
from datetime import date

from app.routing.metro_planner import load_metro_data
from app.routing.bmtc_latest_planner import (
    load_bmtc_latest_data,
    active_bmtc_services,
)

TRAVEL_DATE = "2026-11-18"
MAX_DISTANCE_M = 600
TOP_STOPS_PER_ENTRANCE = 3

print("Loading current Metro and BMTC data...")

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
].copy()

stations = metro_stops[
    pd.to_numeric(metro_stops["location_type"], errors="coerce") == 1
].copy()

entrances = metro_stops[
    pd.to_numeric(metro_stops["location_type"], errors="coerce") == 2
].copy()

entrances = entrances.dropna(
    subset=["parent_station", "stop_lat", "stop_lon"]
)

for column in ["stop_lat", "stop_lon"]:
    entrances[column] = pd.to_numeric(entrances[column])

lat = bmtc_stops["stop_lat"].to_numpy(dtype=float)
lon = bmtc_stops["stop_lon"].to_numpy(dtype=float)

def distances_from(lat1, lon1):
    radius = 6371000
    p1 = np.radians(float(lat1))
    p2 = np.radians(lat)
    dp = p2 - p1
    dl = np.radians(lon - float(lon1))

    a = (
        np.sin(dp / 2) ** 2
        + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    )
    return 2 * radius * np.arcsin(np.sqrt(a))

station_names = stations.set_index("stop_id")["stop_name"].to_dict()

results = []

for entrance in entrances.itertuples(index=False):
    distances = distances_from(
        entrance.stop_lat,
        entrance.stop_lon,
    )

    indices = np.argsort(distances)[:TOP_STOPS_PER_ENTRANCE]

    for index in indices:
        distance = float(distances[index])

        if distance > MAX_DISTANCE_M:
            continue

        stop = bmtc_stops.iloc[index]
        station_id = str(entrance.parent_station)

        results.append({
            "metro_station_id": station_id,
            "metro_station_name": station_names.get(
                station_id, station_id
            ),
            "metro_entrance_name": str(entrance.stop_name),
            "bmtc_stop_id": stop["stop_id"],
            "bmtc_stop_name": stop["stop_name"],
            "bmtc_lat": float(stop["stop_lat"]),
            "bmtc_lon": float(stop["stop_lon"]),
            "straight_line_distance_m": round(distance, 1),
        })

result = pd.DataFrame(results)

print("\n===== CURRENT-FEED INTERCHANGE CANDIDATES =====")
print("Active BMTC stops:", len(bmtc_stops))
print("Metro entrances:", len(entrances))
print("Candidate connections within 600m:", len(result))
print(
    "Metro stations with candidates:",
    result["metro_station_id"].nunique() if not result.empty else 0,
)

if not result.empty:
    print("\n===== KR MARKET CANDIDATES =====")
    print(
        result[
            result["metro_station_id"] == "KRMT"
        ].sort_values("straight_line_distance_m").head(10).to_string(index=False)
    )

    print("\n===== SAMPLE CANDIDATES =====")
    print(
        result.sort_values("straight_line_distance_m")
        .head(20)
        .to_string(index=False)
    )

    print("\n===== COVERAGE BY METRO STATION =====")
    print(
        result.groupby(
            ["metro_station_id", "metro_station_name"]
        ).size().sort_values(ascending=False).head(20).to_string()
    )
else:
    print("No candidates found. Check coordinate fields and feed coverage.")
