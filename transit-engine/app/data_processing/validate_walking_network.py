
from pathlib import Path
import math
import networkx as nx
import osmnx as ox

BASE = Path(__file__).resolve().parents[2]

GRAPH_FILE = (
    BASE / "data" / "raw" / "walking"
    / "bengaluru_walking_network.graphml"
)


def main():
    print("Loading Bengaluru walking network...")

    G = ox.load_graphml(GRAPH_FILE)

    print("\n===== BASIC NETWORK INFORMATION =====")
    print("Graph type:", type(G).__name__)
    print("Nodes:", G.number_of_nodes())
    print("Edges:", G.number_of_edges())
    print("CRS:", G.graph.get("crs"))

    # 1. Validate node coordinates
    invalid_coordinates = 0
    latitudes = []
    longitudes = []

    for node, data in G.nodes(data=True):
        x = data.get("x")
        y = data.get("y")

        try:
            x = float(x)
            y = float(y)

            if not (math.isfinite(x) and math.isfinite(y)):
                invalid_coordinates += 1
                continue

            if not (-180 <= x <= 180 and -90 <= y <= 90):
                invalid_coordinates += 1
                continue

            longitudes.append(x)
            latitudes.append(y)

        except (TypeError, ValueError):
            invalid_coordinates += 1

    print("\n===== NODE COORDINATE VALIDATION =====")
    print("Invalid coordinate records:", invalid_coordinates)

    if latitudes:
        print("Latitude range:", min(latitudes), "to", max(latitudes))
        print("Longitude range:", min(longitudes), "to", max(longitudes))

    # 2. Validate edge lengths
    missing_lengths = 0
    invalid_lengths = 0
    valid_lengths = []

    for u, v, key, data in G.edges(keys=True, data=True):
        length = data.get("length")

        if length is None:
            missing_lengths += 1
            continue

        try:
            length = float(length)

            if not math.isfinite(length) or length <= 0:
                invalid_lengths += 1
            else:
                valid_lengths.append(length)

        except (TypeError, ValueError):
            invalid_lengths += 1

    print("\n===== EDGE LENGTH VALIDATION =====")
    print("Edges missing length:", missing_lengths)
    print("Edges with invalid length:", invalid_lengths)
    print("Edges with valid length:", len(valid_lengths))

    if valid_lengths:
        print("Minimum edge length (m):", min(valid_lengths))
        print("Maximum edge length (m):", max(valid_lengths))
        print("Average edge length (m):",
              round(sum(valid_lengths) / len(valid_lengths), 2))

    # 3. Connectivity analysis
    print("\n===== CONNECTIVITY ANALYSIS =====")

    components = list(nx.weakly_connected_components(G))
    components.sort(key=len, reverse=True)

    print("Weakly connected components:", len(components))
    print("Largest component nodes:", len(components[0]))
    print("Largest component coverage (%):",
          round(len(components[0]) / G.number_of_nodes() * 100, 2))

    print("\nLargest 10 components:")
    for i, component in enumerate(components[:10], start=1):
        print(f"Component {i}: {len(component)} nodes")

    # 4. Isolated nodes
    isolated = list(nx.isolates(G))

    print("\n===== ISOLATED NODE ANALYSIS =====")
    print("Isolated nodes:", len(isolated))

    # 5. Self-loop check
    self_loops = list(nx.selfloop_edges(G))
    print("Self-loop edges:", len(self_loops))

    print("\n===== VALIDATION SUMMARY =====")
    if invalid_coordinates == 0 and missing_lengths == 0 and invalid_lengths == 0:
        print("Coordinate and edge-length checks passed.")
    else:
        print("Some coordinate or edge-length issues need investigation.")

    print("Connectivity results must be reviewed separately.")
    print("\nWalking network validation completed.")


if __name__ == "__main__":
    main()
