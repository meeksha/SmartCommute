import pandas as pd

source = "data/processed/bmtc_metro_walk_validation.csv"
output = "data/processed/bmtc_metro_walk_validation_corrected.csv"

df = pd.read_csv(source)

df["estimated_total_walk_m"] = (
    df["bmtc_snap_distance_m"]
    + df["walk_distance_m"]
    + df["entrance_snap_distance_m"]
).round(1)

df["estimated_walk_minutes"] = (
    df["estimated_total_walk_m"] / 80
).round(1)

df["corrected_validation_status"] = df["validation_status"]

valid = df["validation_status"] == "OSM_PATH_FOUND"

df.loc[
    valid & (df["estimated_total_walk_m"] > 600),
    "corrected_validation_status"
] = "LONG_WALK"

df.loc[
    valid & (df["estimated_total_walk_m"] <= 600),
    "corrected_validation_status"
] = "OSM_PATH_FOUND_WITH_ENDPOINT_ESTIMATES"

df.to_csv(output, index=False)

print("CORRECTED WALKING VALIDATION")
print("--------------------------------")
print("Saved:", output)
print("\nStatus counts:")
print(df["corrected_validation_status"].value_counts().to_string())

print("\nCorrected zero-distance records:",
      (df.loc[valid, "estimated_total_walk_m"] == 0).sum())

print("\nAverage estimated walking distance:",
      round(df.loc[valid, "estimated_total_walk_m"].mean(), 1), "metres")

print("\nSample corrected connections:")
print(
    df.loc[valid, [
        "bmtc_stop_name",
        "metro_entrance_name",
        "straight_line_distance_m",
        "estimated_total_walk_m",
        "estimated_walk_minutes",
        "corrected_validation_status"
    ]].head(15).to_string(index=False)
)
