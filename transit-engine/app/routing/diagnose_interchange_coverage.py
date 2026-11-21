import math
import pandas as pd

from app.routing.bmtc_latest_planner import (
    load_bmtc_latest_data,
    active_bmtc_services,
)

INTERCHANGE_FILE = "data/processed/metro_bmtc_all_station_interchanges.csv"
DATE = "2026-11-18"


def haversine(lat1, lon1, lat2, lon2):
    radius = 6371000
    p1 = math.radians(float(lat1))
    p2 = math.radians(float(lat2))
    dp = math.radians(float(lat2) - float(lat1))
    dl = math.radians(float(lon2) - float(lon1))

    a = (
        math.sin(dp / 2) ** 2
        + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    )
    return 2 * radius * math.atan2(math.sqrt(a), math.sqrt(1 - a))


connections, stops, calendar = load_bmtc_latest_data()
services = active_bmtc_services(calendar, DATE)

active = connections[
    connections["service_id"].isin(services)
]

interchanges = pd.read_csv(INTERCHANGE_FILE)
interchanges = interchanges[
    interchanges["interchange_status"] == "OSM_MODELLED_CONNECTION"
].copy()

stops["stop_id"] = stops["stop_id"].astype(str)
interchanges["bmtc_stop_id"] = interchanges["bmtc_stop_id"].astype(str)

stop_ids = set(stops["stop_id"])
active_stop_ids = set(active["stop_id"]) | set(active["next_stop_id"])

mapped_ids = set(interchanges["bmtc_stop_id"])

print("\n===== INTERCHANGE COVERAGE =====")
print("Modelled interchange rows:", len(interchanges))
print("Mapped IDs present in BMTC stops:", len(mapped_ids & stop_ids))
print("Mapped IDs used by active timetable:", len(mapped_ids & active_stop_ids))

print("\n===== UNMATCHED MAPPED STOPS =====")
missing = interchanges[
    ~interchanges["bmtc_stop_id"].isin(stop_ids)
]
print(missing[
    ["metro_station_name", "bmtc_stop_id", "bmtc_stop_name"]
].head(15).to_string(index=False))

print("\n===== KR MARKET INTERCHANGE =====")
kr = interchanges[
    interchanges["metro_station_id"].astype(str) == "KRMT"
]
print(kr.to_string(index=False))

print("\n===== NEARBY BMTC STOPS FOR KR MARKET =====")
if not kr.empty:
    row = kr.iloc[0]
    distances = stops.apply(
        lambda stop: haversine(
            row["metro_lat"], row["metro_lon"],
            stop["stop_lat"], stop["stop_lon"]
        ),
        axis=1
    )
    nearby = stops.copy()
    nearby["distance_m"] = distances
    nearby = nearby.sort_values("distance_m").head(15)

    nearby["used_by_active_timetable"] = nearby["stop_id"].isin(
        active_stop_ids
    )

    print(nearby[
        ["stop_id", "stop_name", "distance_m",
         "used_by_active_timetable"]
    ].to_string(index=False))

print("\n===== ACTIVE TIMETABLE STOP COVERAGE =====")
print("Unique active boarding stops:", active["stop_id"].nunique())
print("Unique active alighting stops:", active["next_stop_id"].nunique())
print("Active services:", len(services))
