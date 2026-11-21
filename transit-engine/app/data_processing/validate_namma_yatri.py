from pathlib import Path
import json
import pandas as pd

BASE = Path(__file__).resolve().parents[2]
DATA = BASE / "data" / "raw" / "namma_yatri"


def load(name):
    with open(DATA / name, encoding="utf-8") as f:
        return pd.DataFrame(json.load(f))


def inspect(name, date_col=None, dimensions=None, city_filter=False):
    df = load(name)

    print("\n" + "=" * 65)
    print(name)
    print("=" * 65)
    print("Rows:", len(df))
    print("Columns:", list(df.columns))

    if city_filter and "city_code" in df.columns:
        print("City distribution:")
        print(df["city_code"].value_counts().to_string())
        df = df[df["city_code"] == "BLR"]
        print("Bengaluru rows:", len(df))

    if date_col and date_col in df.columns:
        dates = pd.to_datetime(df[date_col], errors="coerce")
        print("Date range:", dates.min(), "to", dates.max())
        print("Invalid dates:", dates.isna().sum())

    if dimensions:
        for col in dimensions:
            if col in df.columns:
                print(f"\n{col} values:")
                print(df[col].value_counts(dropna=False).head(20).to_string())

    print("\nMissing values:")
    print(df.isna().sum()[df.isna().sum() > 0].to_string()
          or "No missing values")

    return df


def main():
    inspect(
        "city_agg_cumulative_stats.json",
        date_col="date",
        city_filter=True
    )

    inspect(
        "city_agg_live_trends.json",
        date_col="date",
        dimensions=["trip_category", "vehicle_type", "booking_type"],
        city_filter=True
    )

    inspect(
        "trends_live_ward.json",
        date_col="date",
        dimensions=["ward_num"]
    )

    inspect(
        "trends_live_ca.json",
        date_col="date",
        dimensions=["ac_num"]
    )

    inspect(
        "daily_stats.json",
        date_col="date_created"
    )

    inspect(
        "city_agg_driver_eda.json",
        dimensions=["city", "city_code", "vehicle_type"]
    )

    inspect(
        "driver_eda_wards.json",
        dimensions=["ward_num", "active", "vehicle_type"]
    )

    inspect(
        "driver_eda_ca.json",
        dimensions=["ac_num", "active", "vehicle_type"]
    )


if __name__ == "__main__":
    main()
