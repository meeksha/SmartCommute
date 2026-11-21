from pathlib import Path
import pandas as pd

folder = Path("data/processed/namma_yatri")

files = [
    "city_live_funnel.csv",
    "city_cumulative_funnel.csv",
    "city_hourly_demand.csv",
    "ac_live_funnel.csv",
    "ac_cumulative_funnel.csv",
    "ac_hourly_demand.csv",
    "ac_driver_source_snapshot.csv",
    "city_driver_availability.csv",
]

for filename in files:
    path = folder / filename
    df = pd.read_csv(path)

    print("\n" + "=" * 85)
    print(filename, "| Rows:", len(df))

    for col in ["vehicle_type", "trip_category", "booking_type"]:
        if col in df.columns:
            print(f"{col} categories:", sorted(
                df[col].dropna().astype(str).unique().tolist()
            ))

    if "ac_num" in df.columns:
        print("AC identifiers:", df["ac_num"].nunique())
        print("AC identifier range:",
              df["ac_num"].min(), "to", df["ac_num"].max())

    if "date" in df.columns:
        dates = pd.to_datetime(df["date"], errors="coerce")
        print("Date coverage:", dates.min(), "to", dates.max())

    if {"avg_fare", "avg_dist_pr_trip"}.issubset(df.columns):
        valid = df[
            (df["avg_fare"] > 0) &
            (df["avg_dist_pr_trip"] > 0)
        ].copy()

        valid["observed_fare_per_km"] = (
            valid["avg_fare"] / valid["avg_dist_pr_trip"]
        )

        print("\nFare statistics:")
        print(valid[
            ["avg_fare", "avg_dist_pr_trip", "observed_fare_per_km"]
        ].describe().round(2).to_string())

        if "vehicle_type" in valid.columns:
            print("\nBy vehicle type:")
            print(valid.groupby("vehicle_type")[
                ["avg_fare", "avg_dist_pr_trip", "observed_fare_per_km"]
            ].median().round(2).to_string())

print("\nINSPECTION COMPLETE")
