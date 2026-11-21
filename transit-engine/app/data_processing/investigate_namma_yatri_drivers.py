from pathlib import Path
import json
import pandas as pd

BASE = Path(__file__).resolve().parents[2]
DATA = BASE / "data" / "raw" / "namma_yatri"


def load(filename):
    with open(DATA / filename, encoding="utf-8") as f:
        return pd.DataFrame(json.load(f))


def main():
    # AC-level driver data
    ac = load("driver_eda_ca.json")

    for col in ["active_drvr", "drvr_notonride", "drvr_onride"]:
        ac[col] = pd.to_numeric(ac[col], errors="coerce")

    print("\n===== AC DRIVER DATA =====")
    print(ac.to_string(index=False))

    print("\nOn-ride equals not-on-ride:")
    print((ac["drvr_onride"] == ac["drvr_notonride"]).value_counts())

    print("\nDifference between on-ride and not-on-ride:")
    print((ac["drvr_onride"] - ac["drvr_notonride"]).value_counts())

    # City-level driver data
    city = load("city_agg_driver_eda.json")
    print("\n===== BENGALURU CITY DRIVER DATA =====")
    print(
        city[city["city_code"] == "BLR"].to_string(index=False)
    )

    # Ward-level driver data
    ward = load("driver_eda_wards.json")
    print("\n===== WARD DRIVER DATA SUMMARY =====")
    print("Rows:", len(ward))
    print("Vehicle types:")
    print(ward["vehicle_type"].value_counts(dropna=False).to_string())
    print("Special vehicle_type=0 records:")
    print(ward[ward["vehicle_type"] == "0"].to_string(index=False))


if __name__ == "__main__":
    main()
