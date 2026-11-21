
from pathlib import Path

import networkx as nx
import osmnx as ox
import numpy as np
from pyproj import Transformer
from scipy.spatial import cKDTree


# Input graphs
city_path = Path(
    "data/raw/walking/bengaluru_walking_network.graphml"
)

candidates = {
    "Cluster 21-2": Path(
        "data/processed/walking/cluster_21_2_pbf_candidate.graphml"
    ),
    "Cluster 32-2": Path(
        "data/processed/walking/cluster_32_2_pbf_candidate.graphml"
    ),
}

print("Loading original Bengaluru walking network...")
city = ox.load_graphml(city_path)

city_nodes = set(city.nodes)
city_coords = np.array([
    [float(data["x"]), float(data["y"])]
    for _, data in city.nodes(data=True)
])

# Project coordinates to metres for distance calculations.
transformer = Transformer.from_crs(
    "EPSG:4326", "EPSG:32643", always_xy=True
)

city_x, city_y = transformer.transform(
    city_coords[:, 0], city_coords[:, 1]
)

city_tree = cKDTree(np.column_stack([city_x, city_y]))

print("Original city nodes:", len(city_nodes))


for name, path in candidates.items():
    print("\n" + "=" * 55)
    print(name)
    print("=" * 55)

    G = ox.load_graphml(path)

    components = list(nx.weakly_connected_components(G))
    shared_nodes = set(G.nodes) & city_nodes

    anchored_components = [
        component for component in components
        if component & shared_nodes
    ]

    anchored_nodes = set().union(*anchored_components) if anchored_components else set()
    unanchored_components = [
        component for component in components
        if not component & shared_nodes
    ]

    new_anchored_nodes = anchored_nodes - city_nodes

    print("Candidate nodes:", G.number_of_nodes())
    print("Candidate edges:", G.number_of_edges())
    print("Shared OSM nodes:", len(shared_nodes))
    print("Anchored components:", len(anchored_components))
    print("Nodes in anchored components:", len(anchored_nodes))
    print("New nodes in anchored components:", len(new_anchored_nodes))
    print("Unanchored components:", len(unanchored_components))

    if unanchored_components:
        results = []

        for component in unanchored_components:
            coords = np.array([
                [float(G.nodes[n]["x"]), float(G.nodes[n]["y"])]
                for n in component
            ])

            x, y = transformer.transform(coords[:, 0], coords[:, 1])
            distances, _ = city_tree.query(
                np.column_stack([x, y]),
                k=1
            )

            results.append({
                "size": len(component),
                "nearest_city_distance_m": float(distances.min()),
            })

        results.sort(
            key=lambda item: item["nearest_city_distance_m"]
        )

        print("\nClosest unanchored components:")
        for result in results[:5]:
            print(
                f"Size: {result['size']:>5} | "
                f"Nearest city node: "
                f"{result['nearest_city_distance_m']:.2f} m"
            )

    print("\nIntegration analysis completed for", name)

print("\nAll candidate comparisons completed.")
