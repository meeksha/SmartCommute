import pandas as pd
import numpy as np
from pathlib import Path

BASE = Path("data/processed")

print("Loading BMTC connections...")
df = pd.read_csv(BASE / "bmtc_connections.csv")

stops = pd.read_csv(BASE / "bmtc_stops.csv")

# Convert numeric fields.
for col in ["departure_seconds", "arrival_seconds", "duration_seconds"]:
    df[col] = pd.to_numeric(df[col], errors="coerce")

df = df.dropna(
    subset=[
        "departure_seconds",
        "arrival_seconds",
        "duration_seconds"
    ]
).copy()

# Time features.
df["departure_hour"] = (
    (df["departure_seconds"] // 3600) % 24
).astype(int)

df["departure_minute"] = (
    (df["departure_seconds"] // 60) % 60
).astype(int)

df["scheduled_duration_min"] = (
    df["duration_seconds"] / 60
)

# Prepare stop coordinates.
stops["stop_lat"] = pd.to_numeric(stops["stop_lat"])
stops["stop_lon"] = pd.to_numeric(stops["stop_lon"])

origin = stops[
    ["stop_id", "stop_lat", "stop_lon"]
].rename(columns={
    "stop_lat": "origin_lat",
    "stop_lon": "origin_lon"
})

destination = stops[
    ["stop_id", "stop_lat", "stop_lon"]
].rename(columns={
    "stop_id": "next_stop_id",
    "stop_lat": "destination_lat",
    "stop_lon": "destination_lon"
})

df = df.merge(origin, on="stop_id", how="left")
df = df.merge(destination, on="next_stop_id", how="left")

# Haversine distance between consecutive stops.
lat1 = np.radians(df["origin_lat"])
lon1 = np.radians(df["origin_lon"])
lat2 = np.radians(df["destination_lat"])
lon2 = np.radians(df["destination_lon"])

a = (
    np.sin((lat2 - lat1) / 2) ** 2
    + np.cos(lat1) * np.cos(lat2)
    * np.sin((lon2 - lon1) / 2) ** 2
)

df["distance_km"] = (
    6371 * 2 * np.arcsin(np.sqrt(a))
)

# Scheduled trip frequency for each route, segment and hour.
frequency = (
    df.groupby(
        ["route_id", "stop_id", "next_stop_id", "departure_hour"]
    )["trip_id"]
    .nunique()
    .rename("trips_per_hour")
    .reset_index()
)

df = df.merge(
    frequency,
    on=["route_id", "stop_id", "next_stop_id", "departure_hour"],
    how="left"
)

# Remove unusable records.
df = df.replace([np.inf, -np.inf], np.nan)

df = df.dropna(
    subset=[
        "distance_km",
        "scheduled_duration_min",
        "origin_lat",
        "origin_lon",
        "destination_lat",
        "destination_lon"
    ]
)

df = df[
    (df["scheduled_duration_min"] > 0)
    & (df["distance_km"] > 0)
].copy()

# Save model-ready dataset.
output_columns = [
    "trip_id",
    "route_id",
    "route_short_name",
    "stop_id",
    "next_stop_id",
    "departure_hour",
    "departure_minute",
    "origin_lat",
    "origin_lon",
    "destination_lat",
    "destination_lon",
    "distance_km",
    "trips_per_hour",
    "scheduled_duration_min"
]

output = BASE / "bmtc_prediction_dataset.csv"
df[output_columns].to_csv(output, index=False)

print("\nBMTC PREDICTION DATASET CREATED")
print("--------------------------------")
print("Records:", len(df))
print("Unique routes:", df["route_id"].nunique())
print("Unique trips:", df["trip_id"].nunique())
print("Unique stop pairs:", df.groupby(
    ["stop_id", "next_stop_id"]
).ngroups)

print("\nScheduled duration statistics (minutes):")
print(df["scheduled_duration_min"].describe().round(2))

print("\nDistance statistics (km):")
print(df["distance_km"].describe().round(2))

print("\nSaved:", output)
print("\nTarget: scheduled_duration_min")
print("Note: This is scheduled GTFS data, not observed traffic duration.")
