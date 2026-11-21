
from pathlib import Path

import networkx as nx
import osmnx as ox
import pandas as pd
import numpy as np
from pyproj import Transformer
from scipy.spatial import cKDTree

city_path = Path("data/raw/walking/bengaluru_walking_network.graphml")

candidates = {
    "21-2": Path("data/processed/walking/cluster_21_2_pbf_candidate.graphml"),
    "32-2": Path("data/processed/walking/cluster_32_2_pbf_candidate.graphml"),
}

output = Path(
    "data/processed/walking/walking_connection_candidates.csv"
)

print("Loading original walking graph...")
city = ox.load_graphml(city_path)

city_nodes = list(city.nodes)
city_coords = np.array([
    [float(city.nodes[n]["x"]), float(city.nodes[n]["y"])]
    for n in city_nodes
])

transformer = Transformer.from_crs(
    "EPSG:4326", "EPSG:32643", always_xy=True
)

cx, cy = transformer.transform(
    city_coords[:, 0], city_coords[:, 1]
)

tree = cKDTree(np.column_stack([cx, cy]))

results = []

for cluster, path in candidates.items():
    print(f"\nAnalyzing Cluster {cluster}...")

    G = ox.load_graphml(path)
    shared = set(G.nodes) & set(city.nodes)

    components = list(nx.weakly_connected_components(G))

    for component_number, component in enumerate(components, start=1):
        if component & shared:
            continue

        component_nodes = list(component)

        coords = np.array([
            [float(G.nodes[n]["x"]), float(G.nodes[n]["y"])]
            for n in component_nodes
        ])

        x, y = transformer.transform(coords[:, 0], coords[:, 1])

        distances, indices = tree.query(
            np.column_stack([x, y]), k=1
        )

        best_index = int(np.argmin(distances))
        candidate_node = component_nodes[best_index]
        city_node = city_nodes[int(indices[best_index])]

        def road_types(graph, node):
            values = set()
            for _, _, data in graph.in_edges(node, data=True):
                values.add(str(data.get("highway", "")))
            for _, _, data in graph.out_edges(node, data=True):
                values.add(str(data.get("highway", "")))
            return ";".join(sorted(values))

        results.append({
            "cluster": cluster,
            "component_number": component_number,
            "component_size": len(component),
            "candidate_node": str(candidate_node),
            "city_node": str(city_node),
            "distance_m": round(float(distances[best_index]), 2),
            "candidate_lat": float(G.nodes[candidate_node]["y"]),
            "candidate_lon": float(G.nodes[candidate_node]["x"]),
            "city_lat": float(city.nodes[city_node]["y"]),
            "city_lon": float(city.nodes[city_node]["x"]),
            "candidate_highways": road_types(G, candidate_node),
            "city_highways": road_types(city, city_node),
        })

df = pd.DataFrame(results)

if not df.empty:
    df = df.sort_values(["cluster", "distance_m"])

    print("\n--- Closest 10 connection candidates ---")
    print(df.groupby("cluster", group_keys=False).head(10).to_string(index=False))

    output.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output, index=False)

    print("\nSaved:", output)
else:
    print("No unanchored components found.")

print("\nNo graph connections were created or modified.")
