
from pathlib import Path
import json
import pandas as pd

BASE = Path(__file__).resolve().parents[2]
DATA = BASE / "data" / "raw" / "namma_yatri"


def load(filename):
    with open(DATA / filename, encoding="utf-8") as f:
        return pd.DataFrame(json.load(f))


def check_duplicates(filename, keys):
    df = load(filename)
    valid_keys = [key for key in keys if key in df.columns]

    duplicates = df.duplicated(subset=valid_keys, keep=False)

    print(f"\n{filename}")
    print("Rows:", len(df))
    print("Duplicate rows:", int(duplicates.sum()))
    print("Unique key combinations:", df[valid_keys].drop_duplicates().shape[0])

    if duplicates.any():
        print("Duplicate examples:")
        print(df.loc[duplicates, valid_keys].head(10).to_string(index=False))


def check_hours(filename, area_column=None):
    df = load(filename)

    print(f"\nHourly coverage: {filename}")
    print("Hours present:", sorted(df["hour"].dropna().unique().tolist()))

    if area_column:
        counts = df.groupby(area_column)["hour"].nunique()
        print("Areas:", len(counts))
        print("Minimum distinct hours per area:", counts.min())
        print("Maximum distinct hours per area:", counts.max())


def check_driver_counts(filename, area_column):
    df = load(filename)

    for col in ["active_drvr", "drvr_notonride", "drvr_onride"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df["calculated_total"] = (
        df["drvr_notonride"] + df["drvr_onride"]
    )

    df["difference"] = df["active_drvr"] - df["calculated_total"]

    print(f"\nDriver count audit: {filename}")
    print("Records:", len(df))
    print("Records where active drivers != on-ride + not-on-ride:",
          int((df["difference"] != 0).sum()))

    print("\nLargest differences:")
    print(
        df.sort_values("difference", key=lambda x: x.abs(), ascending=False)
        [[area_column, "vehicle_type", "active_drvr",
          "drvr_notonride", "drvr_onride", "difference"]]
        .head(10)
        .to_string(index=False)
    )


def check_numeric_values(filename):
    df = load(filename)
    numeric = df.select_dtypes(include="number")

    print(f"\nNumeric audit: {filename}")

    if numeric.empty:
        print("No numeric columns")
        return

    print("Negative values:")
    negatives = (numeric < 0).sum()
    print(negatives[negatives > 0].to_string() or "None")


def main():
    # Duplicate checks
    check_duplicates(
        "city_agg_cumulative_stats.json",
        ["date", "city_code"]
    )

    check_duplicates(
        "city_agg_live_trends.json",
        ["date", "hour", "city_code", "trip_category",
         "vehicle_type", "booking_type"]
    )

    check_duplicates(
        "trends_live_ward.json",
        ["ward_num", "date", "hour"]
    )

    check_duplicates(
        "trends_live_ca.json",
        ["ac_num", "date", "hour"]
    )

    check_duplicates(
        "daily_stats.json",
        ["date_created", "hour_created"]
    )

    # Hourly coverage
    check_hours("city_agg_live_trends.json")
    check_hours("trends_live_ward.json", "ward_num")
    check_hours("trends_live_ca.json", "ac_num")

    # Driver consistency
    check_driver_counts("driver_eda_wards.json", "ward_num")
    check_driver_counts("driver_eda_ca.json", "ac_num")

    # Negative numeric values
    check_numeric_values("city_agg_live_trends.json")
    check_numeric_values("trends_live_ward.json")
    check_numeric_values("trends_live_ca.json")


if __name__ == "__main__":
    main()
