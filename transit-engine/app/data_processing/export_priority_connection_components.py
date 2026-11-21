
from pathlib import Path

import networkx as nx
import osmnx as ox
import pandas as pd

candidates = {
    "21-2": {
        "path": "data/processed/walking/cluster_21_2_pbf_candidate.graphml",
        "components": [44, 5],
    },
    "32-2": {
        "path": "data/processed/walking/cluster_32_2_pbf_candidate.graphml",
        "components": [52, 31, 32, 38],
    },
}

output_dir = Path("data/processed/walking/connection_inspection")
output_dir.mkdir(parents=True, exist_ok=True)

for cluster, config in candidates.items():
    print(f"\nProcessing Cluster {cluster}...")

    G = ox.load_graphml(config["path"])

    components = list(nx.weakly_connected_components(G))

    for component_number in config["components"]:
        if component_number > len(components):
            print("Invalid component:", component_number)
            continue

        component = components[component_number - 1]

        print(
            f"Component {component_number}: "
            f"{len(component)} nodes"
        )

        node_rows = []

        for node in component:
            data = G.nodes[node]

            node_rows.append({
                "cluster": cluster,
                "component": component_number,
                "node_id": str(node),
                "lat": float(data["y"]),
                "lon": float(data["x"]),
                "degree": G.degree(node),
                "in_degree": G.in_degree(node),
                "out_degree": G.out_degree(node),
            })

        edge_rows = []

        for u, v, key, data in G.edges(
            component,
            keys=True,
            data=True
        ):
            edge_rows.append({
                "cluster": cluster,
                "component": component_number,
                "u": str(u),
                "v": str(v),
                "length_m": float(data.get("length", 0)),
                "highway": str(data.get("highway", "")),
                "access": str(data.get("access", "")),
                "foot": str(data.get("foot", "")),
                "access_class": str(data.get("access_class", "")),
                "name": str(data.get("name", "")),
            })

        prefix = f"cluster_{cluster}_{component_number}"

        pd.DataFrame(node_rows).to_csv(
            output_dir / f"{prefix}_nodes.csv",
            index=False
        )

        pd.DataFrame(edge_rows).to_csv(
            output_dir / f"{prefix}_edges.csv",
            index=False
        )

print("\nComponent exports completed.")
print("Output directory:", output_dir)
print("No graph files were modified.")
