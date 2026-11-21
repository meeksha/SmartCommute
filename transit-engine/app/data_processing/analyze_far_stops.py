
import pandas as pd

files = {
    "BMTC": "data/processed/walking/bmtc_walking_node_mapping.csv",
    "METRO": "data/processed/walking/metro_walking_node_mapping.csv"
}

for system, file in files.items():
    df = pd.read_csv(file)

    # Stops more than 250 metres from their nearest walking node
    far = df[df["nearest_node_distance_m"] > 250].copy()

    far = far.sort_values(
        "nearest_node_distance_m",
        ascending=False
    )

    print("\n" + "=" * 75)
    print(f"{system}: FAR STOPS (>250 METRES)")
    print("=" * 75)

    print("Total problematic records:", len(far))

    if system == "METRO":
        print("\nLocation type distribution:")
        print(far["location_type"].value_counts(dropna=False))

    columns = [
        "stop_name",
        "stop_id",
        "stop_lat",
        "stop_lon",
        "nearest_node_distance_m",
        "access_status"
    ]

    if system == "METRO":
        columns.insert(2, "parent_station")
        columns.append("location_type")

    print("\nTop 30 farthest stops:")
    print(
        far[columns]
        .head(30)
        .to_string(index=False)
    )

    print("\nDistance summary (metres):")
    print(far["nearest_node_distance_m"].describe())
