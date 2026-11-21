
from pathlib import Path
import osmnx as ox

BASE = Path(__file__).resolve().parents[2]

RAW_DIR = BASE / "data" / "raw" / "walking"
RAW_DIR.mkdir(parents=True, exist_ok=True)

OUTPUT_FILE = RAW_DIR / "bengaluru_walking_network.graphml"


def main():
    print("Downloading Bengaluru pedestrian network...")
    print("Source: OpenStreetMap")

    ox.settings.use_cache = True
    ox.settings.log_console = True

    graph = ox.graph_from_place(
        "Bengaluru, Karnataka, India",
        network_type="walk",
        simplify=True
    )

    print("\nDownload completed.")

    print("Nodes:", len(graph.nodes))
    print("Edges:", len(graph.edges))
    print("CRS:", graph.graph["crs"])

    ox.save_graphml(graph, OUTPUT_FILE)

    print("\nSaved to:", OUTPUT_FILE)


if __name__ == "__main__":
    main()

