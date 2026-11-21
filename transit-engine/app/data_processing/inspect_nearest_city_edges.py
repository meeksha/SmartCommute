
from pathlib import Path

import networkx as nx
import osmnx as ox
import pandas as pd
from pyproj import Transformer


city_path = Path(
    "data/raw/walking/bengaluru_walking_network.graphml"
)

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


print("Loading original city graph...")
city = ox.load_graphml(city_path)

print("Projecting city graph...")
city_projected = ox.project_graph(city)

projected_crs = city_projected.graph["crs"]

transformer = Transformer.from_crs(
    "EPSG:4326",
    projected_crs,
    always_xy=True
)

print("Projected CRS:", projected_crs)


for cluster, config in candidates.items():

    print("\n" + "=" * 65)
    print("CLUSTER", cluster)
    print("=" * 65)

    G = ox.load_graphml(config["path"])

    components = list(
        nx.weakly_connected_components(G)
    )

    for component_number in config["components"]:

        component = components[component_number - 1]

        print(
            f"\nComponent {component_number} "
            f"({len(component)} nodes)"
        )

        results = []

        for node in component:

            data = G.nodes[node]

            x, y = transformer.transform(
                float(data["x"]),
                float(data["y"])
            )

            nearest_edge, distance = ox.distance.nearest_edges(
                city_projected,
                X=x,
                Y=y,
                return_dist=True
            )

            u, v, key = nearest_edge

            edge_data = city_projected.edges[u, v, key]

            results.append({
                "node": str(node),
                "distance_m": float(distance),
                "city_edge_u": str(u),
                "city_edge_v": str(v),
                "city_highway": str(edge_data.get("highway", "")),
                "city_access": str(edge_data.get("access", "")),
                "city_name": str(edge_data.get("name", "")),
                "candidate_lat": float(data["y"]),
                "candidate_lon": float(data["x"]),
            })

        results.sort(key=lambda item: item["distance_m"])

        print("\nThree closest candidate nodes to city road edges:")

        for result in results[:3]:
            print(
                f"Candidate node: {result['node']}\n"
                f"Distance: {result['distance_m']:.2f} m\n"
                f"City edge: "
                f"{result['city_edge_u']} -> "
                f"{result['city_edge_v']}\n"
                f"Highway: {result['city_highway']}\n"
                f"Access: {result['city_access']}\n"
                f"Name: {result['city_name']}\n"
            )

print("\nNearest-edge analysis completed.")
print("No graph files were modified.")
