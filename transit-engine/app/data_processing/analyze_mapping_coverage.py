
from pathlib import Path
import pandas as pd
import osmnx as ox

BASE = Path(__file__).resolve().parents[2]

GRAPH_FILE = BASE / "data/raw/walking/bengaluru_walking_network.graphml"
WALK_DIR = BASE / "data/processed/walking"


def analyze(filename, label, G):
    df = pd.read_csv(WALK_DIR / filename)

    bounds = G.graph["bbox"] if "bbox" in G.graph else None

    # Obtain graph bounds directly from node coordinates.
    nodes = pd.DataFrame([
        {"x": data["x"], "y": data["y"]}
        for _, data in G.nodes(data=True)
    ])

    min_lon, max_lon = nodes["x"].min(), nodes["x"].max()
    min_lat, max_lat = nodes["y"].min(), nodes["y"].max()

    inside = (
        df["stop_lat"].between(min_lat, max_lat)
        & df["stop_lon"].between(min_lon, max_lon)
    )

    df["inside_graph_bounds"] = inside

    print("\n" + "=" * 60)
    print(label)
    print("=" * 60)

    print("Total stops:", len(df))
    print("Inside graph bounds:", int(inside.sum()))
    print("Outside graph bounds:", int((~inside).sum()))

    print("\nDistance categories INSIDE graph bounds:")
    print(
        df.loc[inside, "access_status"]
        .value_counts()
        .to_string()
    )

    print("\nDistance categories OUTSIDE graph bounds:")
    print(
        df.loc[~inside, "access_status"]
        .value_counts()
        .to_string()
    )

    print("\nInside-boundary distance statistics:")
    print(
        df.loc[inside, "nearest_node_distance_m"]
        .describe()
        .to_string()
    )


def main():
    print("Loading walking graph...")
    G = ox.load_graphml(GRAPH_FILE)

    analyze(
        "bmtc_walking_node_mapping.csv",
        "BMTC COVERAGE",
        G
    )

    analyze(
        "metro_walking_node_mapping.csv",
        "METRO COVERAGE",
        G
    )


if __name__ == "__main__":
    main()
