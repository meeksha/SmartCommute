import pandas as pd

path = "data/processed/metro/standard/stops.csv"
stations = pd.read_csv(path)

# Numeric comparison avoids the 1 versus 1.0 problem.
stations["location_type"] = pd.to_numeric(
    stations["location_type"], errors="coerce"
)

all_stations = stations[stations["location_type"] == 1].copy()

best = pd.read_csv(
    "data/processed/metro_bmtc_best_interchanges.csv"
)

validation = pd.read_csv(
    "data/processed/bmtc_metro_walk_validation_corrected.csv"
)

covered = set(best["metro_station_id"].astype(str))
all_stations["stop_id"] = all_stations["stop_id"].astype(str)

missing = all_stations[
    ~all_stations["stop_id"].isin(covered)
]

print("TOTAL METRO STATIONS:", len(all_stations))
print("COVERED:", len(covered))
print("MISSING:", len(missing))

for _, station in missing.iterrows():
    sid = station["stop_id"]

    records = validation[
        validation["metro_station_id"].astype(str) == sid
    ]

    print(f"\n{sid} - {station['stop_name']}")

    if records.empty:
        print("  No candidate within initial 600m straight-line search")
    else:
        print("  Status:", records["corrected_validation_status"].value_counts().to_dict())
        print(
            "  Nearest straight-line candidate:",
            round(records["straight_line_distance_m"].min()), "m"
        )
