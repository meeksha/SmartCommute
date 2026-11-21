
from pathlib import Path
import pandas as pd
import osmnx as ox

BASE = Path(__file__).resolve().parents[2]

RAW = BASE / "data" / "raw"
PROCESSED = BASE / "data" / "processed" / "walking"

GRAPH_FILE = RAW / "walking" / "bengaluru_walking_network.graphml"


def inspect_mapping(filename, label):
    path = PROCESSED / filename
    df = pd.read_csv(path)

    print("\n" + "=" * 65)
    print(label)
    print("=" * 65)

    print("Records:", len(df))
    print("Latitude range:",
          df["stop_lat"].min(), "to", df["stop_lat"].max())
    print("Longitude range:",
          df["stop_lon"].min(), "to", df["stop_lon"].max())

    print("\nDistance statistics (metres):")
    print(df["nearest_node_distance_m"].describe().to_string())

    print("\nDistance percentiles:")
    print(
        df["nearest_node_distance_m"]
        .quantile([0, 0.25, 0.50, 0.75, 0.90, 0.95, 0.99, 1])
        .to_string()
    )

    print("\nStops farther than 250 metres:")
    far = df[df["nearest_node_distance_m"] > 250]

    columns = [
        col for col in [
            "stop_id", "stop_name", "stop_lat", "stop_lon",
            "walking_node_id", "nearest_node_distance_m",
            "access_status"
        ]
        if col in df.columns
    ]

    print("Count:", len(far))
    print(far[columns].head(15).to_string(index=False))


def main():
    print("Loading walking graph...")
    G = ox.load_graphml(GRAPH_FILE)

    nodes = pd.DataFrame([
        {
            "node_id": node,
            "latitude": data["y"],
            "longitude": data["x"]
        }
        for node, data in G.nodes(data=True)
    ])

    print("\n===== WALKING GRAPH BOUNDS =====")
    print("Latitude:", nodes["latitude"].min(),
          "to", nodes["latitude"].max())
    print("Longitude:", nodes["longitude"].min(),
          "to", nodes["longitude"].max())

    for filename, label in [
        ("bmtc_walking_node_mapping.csv", "BMTC"),
        ("metro_walking_node_mapping.csv", "METRO")
    ]:
        inspect_mapping(filename, label)

    print("\n===== BMTC ORIGINAL STOP COORDINATES =====")

    bmtc = pd.read_csv(BASE / "data" / "processed" / "bmtc_stops.csv")

    print("Latitude:", bmtc["stop_lat"].min(),
          "to", bmtc["stop_lat"].max())
    print("Longitude:", bmtc["stop_lon"].min(),
          "to", bmtc["stop_lon"].max())

    graph_min_lat = nodes["latitude"].min()
    graph_max_lat = nodes["latitude"].max()
    graph_min_lon = nodes["longitude"].min()
    graph_max_lon = nodes["longitude"].max()

    outside = (
        (bmtc["stop_lat"] < graph_min_lat)
        | (bmtc["stop_lat"] > graph_max_lat)
        | (bmtc["stop_lon"] < graph_min_lon)
        | (bmtc["stop_lon"] > graph_max_lon)
    )

    print("BMTC stops outside graph bounding box:", int(outside.sum()))
    print("\nExamples outside graph bounds:")
    print(
        bmtc.loc[outside].head(15).to_string(index=False)
    )


if __name__ == "__main__":
    main()
