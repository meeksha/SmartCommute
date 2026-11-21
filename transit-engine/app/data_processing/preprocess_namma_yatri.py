from pathlib import Path
import json
import pandas as pd

BASE = Path(__file__).resolve().parents[2]
RAW = BASE / "data" / "raw" / "namma_yatri"
OUT = BASE / "data" / "processed" / "namma_yatri"

OUT.mkdir(parents=True, exist_ok=True)


def load_json(filename):
    path = RAW / filename

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    return pd.DataFrame(data)


def save_csv(df, filename):
    df.to_csv(OUT / filename, index=False)
    print(f"Saved {filename}: {len(df)} rows")


def add_source(df, source):
    df = df.copy()
    df["source_file"] = source
    return df


def process_city_dataset(source, output):
    df = load_json(source)

    if "city_code" in df.columns:
        df = df[df["city_code"] == "BLR"].copy()

    df = add_source(df, source)
    save_csv(df, output)

    return df


def main():
    print("\n===== NAMMA YATRI PREPROCESSING =====\n")

    # 1. Bengaluru city cumulative statistics
    process_city_dataset(
        "city_agg_cumulative_stats.json",
        "city_cumulative_stats.csv"
    )

    # 2. Bengaluru hourly demand
    process_city_dataset(
        "city_agg_live_trends.json",
        "city_hourly_demand.csv"
    )

    # 3. Bengaluru city driver statistics
    city_drivers = process_city_dataset(
        "city_agg_driver_eda.json",
        "city_driver_availability.csv"
    )

    # 4. Ward-level hourly demand
    ward_trends = load_json("trends_live_ward.json")
    ward_trends = add_source(
        ward_trends, "trends_live_ward.json"
    )
    save_csv(ward_trends, "ward_hourly_demand.csv")

    # 5. Assembly Constituency hourly demand
    ac_trends = load_json("trends_live_ca.json")
    ac_trends = add_source(
        ac_trends, "trends_live_ca.json"
    )
    save_csv(ac_trends, "ac_hourly_demand.csv")

    # 6. Ward driver availability
    ward_drivers = load_json("driver_eda_wards.json")

    for col in [
        "active_drvr",
        "drvr_notonride",
        "drvr_onride"
    ]:
        ward_drivers[col] = pd.to_numeric(
            ward_drivers[col], errors="coerce"
        )

    ward_drivers["driver_counts_consistent"] = (
        ward_drivers["active_drvr"]
        == ward_drivers["drvr_notonride"]
        + ward_drivers["drvr_onride"]
    )

    ward_drivers = add_source(
        ward_drivers, "driver_eda_wards.json"
    )
    save_csv(ward_drivers, "ward_driver_availability.csv")

    # 7. AC driver source snapshot
    # Keep original values, but mark inconsistent fields.
    ac_drivers = load_json("driver_eda_ca.json")

    for col in [
        "active_drvr",
        "drvr_notonride",
        "drvr_onride"
    ]:
        ac_drivers[col] = pd.to_numeric(
            ac_drivers[col], errors="coerce"
        )

    ac_drivers["driver_counts_consistent"] = (
        ac_drivers["active_drvr"]
        == ac_drivers["drvr_notonride"]
        + ac_drivers["drvr_onride"]
    )

    ac_drivers["onride_split_usable"] = False

    ac_drivers = add_source(
        ac_drivers, "driver_eda_ca.json"
    )
    save_csv(ac_drivers, "ac_driver_source_snapshot.csv")

    # 8. Daily statistics
    # Geographic scope is not established, so keep separate.
    daily = load_json("daily_stats.json")
    daily = add_source(daily, "daily_stats.json")
    save_csv(daily, "daily_stats_unassigned_scope.csv")

    # 9. Funnel datasets
    funnel_files = {
        "city_agg_cumulative_funnel.json":
            "city_cumulative_funnel.csv",

        "city_agg_live_funnel.json":
            "city_live_funnel.csv",

        "funnel_cumulative_ca.json":
            "ac_cumulative_funnel.csv",

        "funnel_cumulative_ward.json":
            "ward_cumulative_funnel.csv",

        "funnel_live_ca.json":
            "ac_live_funnel.csv",

        "funnel_live_ward.json":
            "ward_live_funnel.csv"
    }

    for source, output in funnel_files.items():
        process_city_dataset(source, output)

    # 10. Data quality report
    report = [
        "NAMMA YATRI DATA QUALITY REPORT",
        "================================",
        "",
        "Source: data/raw/namma_yatri/",
        "Output: data/processed/namma_yatri/",
        "",
        "1. City-level datasets are filtered to city_code BLR.",
        "2. Ward and AC datasets are retained separately.",
        "3. Original date and hour fields are preserved.",
        "4. Ward driver counts passed consistency validation.",
        "5. AC driver on-ride and not-on-ride fields are inconsistent.",
        "6. AC driver source values are retained but not approved",
        "   for driver availability calculations.",
        "7. Daily statistics are kept separate because their",
        "   geographic scope is not established.",
        "8. Inactive ward b_77 is retained in the ward driver file.",
        "9. Raw JSON files are not modified.",
        "10. Ward and AC hourly trends have different reporting dates",
        "    from the city hourly trends. Do not combine as simultaneous data.",
        "",
        f"City cumulative rows: {1323}",
        f"City hourly trend rows: {len(load_json('city_agg_live_trends.json').query('city_code == \"BLR\"'))}",
        f"Ward hourly trend rows: {len(ward_trends)}",
        f"AC hourly trend rows: {len(ac_trends)}",
        f"Ward driver rows: {len(ward_drivers)}",
        f"AC driver rows: {len(ac_drivers)}",
        "",
        "Note: These datasets are aggregate statistics, not individual",
        "passenger journeys or live vehicle GPS traces."
    ]

    (OUT / "data_quality_report.txt").write_text(
        "\n".join(report),
        encoding="utf-8"
    )

    print("\n===== PREPROCESSING COMPLETED =====")
    print("Output folder:", OUT)
    print("Files created:", len(list(OUT.iterdir())))


if __name__ == "__main__":
    main()
