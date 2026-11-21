from pathlib import Path
import pandas as pd

root = Path("data/raw/metro/standard")

def find_file(name):
    matches = list(root.rglob(name))
    if not matches:
        raise FileNotFoundError(f"{name} not found under {root}")
    return matches[0]

stop_times_path = find_file("stop_times.txt")
trips_path = find_file("trips.txt")

stop_times = pd.read_csv(stop_times_path)
trips = pd.read_csv(trips_path)

trip_id = "t2549"

trip = trips[trips["trip_id"].astype(str) == trip_id]
rows = stop_times[stop_times["trip_id"].astype(str) == trip_id].copy()

print("Trip record:")
print(trip.to_string(index=False))

print("\nStop-time columns:", list(stop_times.columns))
print("\nJourney stop records:")

if "stop_sequence" in rows.columns:
    rows = rows.sort_values("stop_sequence")

columns = [
    col for col in [
        "trip_id", "stop_id", "stop_sequence",
        "arrival_time", "departure_time", "shape_dist_traveled"
    ] if col in rows.columns
]

print(rows[columns].to_string(index=False))
