from pathlib import Path
from zipfile import ZipFile
import pandas as pd
import io

ZIP_PATH = Path("data/raw/bmtc_latest/bmtc_latest.zip")
OUTPUT = Path("data/processed/bmtc_latest")
OUTPUT.mkdir(parents=True, exist_ok=True)


def read_gtfs(archive, filename):
    return pd.read_csv(
        io.BytesIO(archive.read(filename)),
        dtype=str,
        low_memory=False
    )


def time_to_seconds(series):
    parts = series.str.split(":", expand=True)
    hours = pd.to_numeric(parts[0], errors="coerce")
    minutes = pd.to_numeric(parts[1], errors="coerce")
    seconds = pd.to_numeric(parts[2], errors="coerce")

    return hours * 3600 + minutes * 60 + seconds


print("Reading new BMTC GTFS feed...")

with ZipFile(ZIP_PATH) as archive:
    stops = read_gtfs(archive, "stops.txt")
    routes = read_gtfs(archive, "routes.txt")
    trips = read_gtfs(archive, "trips.txt")
    stop_times = read_gtfs(archive, "stop_times.txt")
    calendar = read_gtfs(archive, "calendar.txt")

print("Sorting stop times...")
stop_times["stop_sequence"] = pd.to_numeric(
    stop_times["stop_sequence"], errors="coerce"
)
stop_times = stop_times.dropna(
    subset=["trip_id", "stop_id", "stop_sequence",
            "departure_time", "arrival_time"]
)
stop_times = stop_times.sort_values(
    ["trip_id", "stop_sequence"]
).reset_index(drop=True)

print("Generating consecutive-stop connections...")

grouped = stop_times.groupby("trip_id", sort=False)

stop_times["next_stop_id"] = grouped["stop_id"].shift(-1)
stop_times["next_arrival_time"] = grouped["arrival_time"].shift(-1)

connections = stop_times.dropna(
    subset=["next_stop_id", "next_arrival_time"]
).copy()

connections["departure_seconds"] = time_to_seconds(
    connections["departure_time"]
)
connections["arrival_seconds"] = time_to_seconds(
    connections["next_arrival_time"]
)

connections = connections.dropna(
    subset=["departure_seconds", "arrival_seconds"]
)

connections["duration_seconds"] = (
    connections["arrival_seconds"]
    - connections["departure_seconds"]
)

invalid = (connections["duration_seconds"] < 0).sum()

connections = connections[
    connections["duration_seconds"] >= 0
].copy()

print("Joining trip and route information...")

connections = connections.merge(
    trips[["trip_id", "route_id", "service_id"]],
    on="trip_id",
    how="inner",
    validate="many_to_one"
)

connections = connections.merge(
    routes[["route_id", "route_short_name", "route_long_name"]],
    on="route_id",
    how="left",
    validate="many_to_one"
)

connections = connections[[
    "trip_id",
    "route_id",
    "route_short_name",
    "route_long_name",
    "stop_id",
    "next_stop_id",
    "departure_time",
    "next_arrival_time",
    "departure_seconds",
    "arrival_seconds",
    "duration_seconds",
    "service_id"
]]

print("Saving separate BMTC datasets...")

stops.to_csv(OUTPUT / "bmtc_stops.csv", index=False)
routes.to_csv(OUTPUT / "bmtc_routes.csv", index=False)
trips.to_csv(OUTPUT / "bmtc_trips.csv", index=False)
calendar.to_csv(OUTPUT / "bmtc_calendar.csv", index=False)
connections.to_csv(
    OUTPUT / "bmtc_connections.csv",
    index=False
)

print("\nNEW BMTC DATASET CREATED")
print("========================")
print("Stops:", len(stops))
print("Routes:", len(routes))
print("Trips:", len(trips))
print("Connections:", len(connections))
print("Negative-duration connections removed:", invalid)
print("Unique services:", connections["service_id"].nunique())
print("Output folder:", OUTPUT.resolve())

print("\nSample connections:")
print(connections.head(5).to_string(index=False))
