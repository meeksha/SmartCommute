import pandas as pd

source = "data/processed/bmtc_metro_walk_validation_corrected.csv"
output = "data/processed/metro_bmtc_best_interchanges.csv"

df = pd.read_csv(source)

valid = df[
    df["corrected_validation_status"]
    == "OSM_PATH_FOUND_WITH_ENDPOINT_ESTIMATES"
].copy()

best = (
    valid.sort_values("estimated_total_walk_m")
    .drop_duplicates(subset="metro_station_id", keep="first")
)

best = best[[
    "metro_station_id",
    "metro_entrance_name",
    "bmtc_stop_id",
    "bmtc_stop_name",
    "straight_line_distance_m",
    "estimated_total_walk_m",
    "estimated_walk_minutes"
]].sort_values("metro_station_id")

best.to_csv(output, index=False)

print("METRO STATION INTERCHANGE SUMMARY")
print("----------------------------------")
print("Stations with a validated candidate:", len(best))
print("Saved:", output)
print("\nSample:")
print(best.head(20).to_string(index=False))
