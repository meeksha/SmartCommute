from pathlib import Path
import pandas as pd

path = Path("data/processed/namma_yatri/city_hourly_demand.csv")
df = pd.read_csv(path)

df["date"] = pd.to_datetime(df["date"], errors="coerce")
for col in ["earning", "done_ride"]:
    df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

# Exclude combined totals; retain individual vehicle categories.
vehicles = df[df["vehicle_type"].isin(["Auto", "Cab"])].copy()

print("DATE COVERAGE")
print(vehicles["date"].min(), "to", vehicles["date"].max())

print("\nTOTALS BY VEHICLE TYPE AND TRIP CATEGORY")
summary = vehicles.groupby(
    ["vehicle_type", "trip_category"], dropna=False
).agg(
    completed_rides=("done_ride", "sum"),
    total_earning=("earning", "sum"),
).reset_index()

summary["earning_per_completed_ride"] = (
    summary["total_earning"] /
    summary["completed_rides"].replace(0, pd.NA)
)

print(summary.round(2).to_string(index=False))

print("\nDAILY EARNING PER COMPLETED RIDE")
daily = vehicles.groupby(
    ["date", "vehicle_type", "trip_category"], dropna=False
).agg(
    completed_rides=("done_ride", "sum"),
    total_earning=("earning", "sum"),
).reset_index()

daily = daily[daily["completed_rides"] > 0].copy()
daily["earning_per_completed_ride"] = (
    daily["total_earning"] / daily["completed_rides"]
)

print(daily.round(2).to_string(index=False))

print("\nMEDIAN DAILY ESTIMATE BY VEHICLE AND CATEGORY")
print(
    daily.groupby(["vehicle_type", "trip_category"])[
        "earning_per_completed_ride"
    ].agg(["count", "median", "mean", "min", "max"]).round(2).to_string()
)

print("\nNOTE")
print("Earning per completed ride is an aggregate proxy, not a live fare quote.")
