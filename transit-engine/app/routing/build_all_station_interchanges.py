import pandas as pd

stations = pd.read_csv("data/processed/metro/standard/stops.csv")
stations["location_type"] = pd.to_numeric(
    stations["location_type"], errors="coerce"
)
stations = stations[stations["location_type"] == 1].copy()

best = pd.read_csv("data/processed/metro_bmtc_best_interchanges.csv")
validation = pd.read_csv(
    "data/processed/bmtc_metro_walk_validation_corrected.csv"
)

result = stations[["stop_id", "stop_name", "stop_lat", "stop_lon"]].copy()
result = result.rename(columns={
    "stop_id": "metro_station_id",
    "stop_name": "metro_station_name",
    "stop_lat": "metro_lat",
    "stop_lon": "metro_lon"
})

result = result.merge(best, on="metro_station_id", how="left")

status = validation.groupby("metro_station_id")[
    "corrected_validation_status"
].agg(lambda x: ", ".join(sorted(set(x)))).reset_index()

result = result.merge(status, on="metro_station_id", how="left")

result["interchange_status"] = "NO_NEARBY_BMTC_CANDIDATE"

result.loc[
    result["corrected_validation_status"].str.contains(
        "LONG_WALK", na=False
    ),
    "interchange_status"
] = "POTENTIAL_LONG_WALK"

result.loc[
    result["corrected_validation_status"].str.contains(
        "SNAP_TOO_FAR", na=False
    ),
    "interchange_status"
] = "POTENTIAL_GRAPH_COVERAGE_ISSUE"

result.loc[
    result["bmtc_stop_id"].notna(),
    "interchange_status"
] = "OSM_MODELLED_CONNECTION"

output = "data/processed/metro_bmtc_all_station_interchanges.csv"
result.to_csv(output, index=False)

print("Total Metro stations:", len(result))
print("\nInterchange categories:")
print(result["interchange_status"].value_counts().to_string())
print("\nSaved:", output)
