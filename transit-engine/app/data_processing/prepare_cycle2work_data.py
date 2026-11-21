
import pandas as pd
import json
from pathlib import Path

FILES = [
    "data/raw/employees/cycle2work_january_2019.csv",
    "data/raw/employees/cycle2work_february_2019.csv",
]

OUTPUT_DIR = Path("data/processed/employees")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

MIN_LAT, MAX_LAT = 12.7, 13.2
MIN_LON, MAX_LON = 77.3, 77.9

frames = []

for file in FILES:
    df = pd.read_csv(file)

    df["route_points"] = df["route"].apply(json.loads)

    df["start_lat"] = df["route_points"].apply(
        lambda r: r[0][0]
    )
    df["start_lon"] = df["route_points"].apply(
        lambda r: r[0][1]
    )
    df["end_lat"] = df["route_points"].apply(
        lambda r: r[-1][0]
    )
    df["end_lon"] = df["route_points"].apply(
        lambda r: r[-1][1]
    )

    start_inside = (
        df["start_lat"].between(MIN_LAT, MAX_LAT)
        & df["start_lon"].between(MIN_LON, MAX_LON)
    )
    end_inside = (
        df["end_lat"].between(MIN_LAT, MAX_LAT)
        & df["end_lon"].between(MIN_LON, MAX_LON)
    )

    df = df[start_inside & end_inside].copy()

    df["start_time"] = pd.to_datetime(
        df["start_date(DD/MM/YYYY HH:MM:SS)"],
        format="%d/%m/%Y %H:%M:%S",
        errors="coerce"
    )

    df["distance_km"] = df["distance(m)"] / 1000

    df["duration_seconds"] = pd.to_timedelta(
        df["moving_time(HH:MM:SS)"],
        errors="coerce"
    ).dt.total_seconds()

    df["duration_minutes"] = df["duration_seconds"] / 60

    df["average_speed_kmh"] = (
        df["distance_km"] / (df["duration_seconds"] / 3600)
    )

    df["mode"] = "cycling"
    df["source"] = "Cycle2Work Bengaluru, 2019"

    frames.append(df)

result = pd.concat(frames, ignore_index=True)

# Flag records that fail validation.
result["rejection_reason"] = ""

result.loc[
    result["start_time"].isna(),
    "rejection_reason"
] += "Invalid timestamp; "

result.loc[
    result["distance_km"].isna() | (result["distance_km"] <= 0),
    "rejection_reason"
] += "Invalid distance; "

result.loc[
    result["duration_seconds"].isna()
    | (result["duration_seconds"] <= 0),
    "rejection_reason"
] += "Invalid or zero duration; "

result.loc[
    result["duration_seconds"] > 12 * 3600,
    "rejection_reason"
] += "Duration exceeds 12 hours; "

result.loc[
    result["average_speed_kmh"].isna()
    | (result["average_speed_kmh"] <= 0)
    | (result["average_speed_kmh"] > 40),
    "rejection_reason"
] += "Implausible average speed; "

rejected = result[result["rejection_reason"] != ""].copy()
clean = result[result["rejection_reason"] == ""].copy()

columns = [
    "start_time",
    "distance_km",
    "duration_minutes",
    "average_speed_kmh",
    "start_lat",
    "start_lon",
    "end_lat",
    "end_lon",
    "route",
    "mode",
    "source",
]

clean[columns].to_csv(
    OUTPUT_DIR / "bengaluru_cycling_journeys.csv",
    index=False
)

rejected.to_csv(
    OUTPUT_DIR / "bengaluru_cycling_rejected_records.csv",
    index=False
)

print("\nCYCLING DATA QUALITY REPORT")
print("-" * 40)
print("Bengaluru journeys:", len(result))
print("Valid journeys:", len(clean))
print("Rejected journeys:", len(rejected))

print("\nRejection reasons:")
print(
    rejected["rejection_reason"]
    .value_counts()
    .to_string()
)

print("\nValid journey statistics:")
print(
    clean[[
        "distance_km",
        "duration_minutes",
        "average_speed_kmh"
    ]].describe().round(2)
)
