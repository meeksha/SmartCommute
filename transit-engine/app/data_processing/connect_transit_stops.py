
from pathlib import Path
import pandas as pd
import osmnx as ox

BASE = Path(__file__).resolve().parents[2]

WALKING_FILE = (
    BASE / "data" / "raw" / "walking"
    / "bengaluru_walking_network.graphml"
)

BMTC_FILE = BASE / "data" / "processed" / "bmtc_stops.csv"
METRO_FILE = BASE / "data" / "raw" / "metro" / "standard" / "stops.txt"

OUTPUT_DIR = BASE / "data" / "processed" / "walking"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def map_stops(df, source_name):
    df = df.copy()

    df["stop_lat"] = pd.to_numeric(df["stop_lat"], errors="coerce")
    df["stop_lon"] = pd.to_numeric(df["stop_lon"], errors="coerce")

    valid = (
        df["stop_lat"].notna()
        & df["stop_lon"].notna()
        & df["stop_lat"].between(-90, 90)
        & df["stop_lon"].between(-180, 180)
    )

    invalid_count = int((~valid).sum())

    print(f"\n{source_name}")
    print("Total stops:", len(df))
    print("Invalid coordinates:", invalid_count)

    valid_df = df.loc[valid].copy()

    nearest_nodes = ox.distance.nearest_nodes(
        G,
        X=valid_df["stop_lon"].to_numpy(),
        Y=valid_df["stop_lat"].to_numpy()
    )

    valid_df["walking_node_id"] = nearest_nodes

    distances = []

    for _, row in valid_df.iterrows():
        node = G.nodes[row["walking_node_id"]]

        distance = ox.distance.great_circle(
            row["stop_lat"],
            row["stop_lon"],
            node["y"],
            node["x"]
        )

        distances.append(distance)

    valid_df["nearest_node_distance_m"] = distances
    valid_df["mapping_source"] = source_name

    valid_df["access_status"] = pd.cut(
        valid_df["nearest_node_distance_m"],
        bins=[-1, 50, 100, 250, float("inf")],
        labels=[
            "very_close",
            "close",
            "review",
            "far"
        ]
    )

    print("Mapped stops:", len(valid_df))
    print(
        "Average nearest-node distance (m):",
        round(valid_df["nearest_node_distance_m"].mean(), 2)
    )
    print(
        "Maximum nearest-node distance (m):",
        round(valid_df["nearest_node_distance_m"].max(), 2)
    )

    print("\nAccess distance categories:")
    print(valid_df["access_status"].value_counts().to_string())

    return valid_df


def main():
    global G

    print("Loading walking graph...")
    G = ox.load_graphml(WALKING_FILE)

    print("Walking nodes:", len(G.nodes))

    # BMTC stops
    bmtc = pd.read_csv(BMTC_FILE)

    bmtc_mapped = map_stops(
        bmtc,
        "BMTC"
    )

    bmtc_mapped.to_csv(
        OUTPUT_DIR / "bmtc_walking_node_mapping.csv",
        index=False
    )

    # Metro stops
    metro = pd.read_csv(METRO_FILE)

    metro_mapped = map_stops(
        metro,
        "Metro"
    )

    metro_mapped.to_csv(
        OUTPUT_DIR / "metro_walking_node_mapping.csv",
        index=False
    )

    print("\n===== MAPPING COMPLETED =====")
    print("BMTC mapped:", len(bmtc_mapped))
    print("Metro mapped:", len(metro_mapped))
    print("Output folder:", OUTPUT_DIR)


if __name__ == "__main__":
    main()
