
from pathlib import Path

import networkx as nx
import osmnx as ox
import pandas as pd

candidate_file = Path(
    "data/processed/walking/walking_connection_candidates.csv"
)

city_path = Path(
    "data/raw/walking/bengaluru_walking_network.graphml"
)

candidate_paths = {
    "21-2": Path(
        "data/processed/walking/cluster_21_2_pbf_candidate.graphml"
    ),
    "32-2": Path(
        "data/processed/walking/cluster_32_2_pbf_candidate.graphml"
    ),
}

df = pd.read_csv(candidate_file)

city = ox.load_graphml(city_path)

# Inspect the closest six candidates from each cluster.
selected = (
    df.sort_values("distance_m")
    .groupby("cluster")
    .head(6)
)

for cluster, group in selected.groupby("cluster"):
    G = ox.load_graphml(candidate_paths[cluster])

    print(f"\n========== CLUSTER {cluster} ==========")

    for row in group.itertuples(index=False):
        candidate_node = int(row.candidate_node)
        city_node = int(row.city_node)

        print("\nComponent:", row.component_number)
        print("Component size:", row.component_size)
        print("Distance:", row.distance_m, "m")

        print(
            "Candidate coordinates:",
            row.candidate_lat,
            row.candidate_lon
        )

        print(
            "City coordinates:",
            row.city_lat,
            row.city_lon
        )

        print("Candidate adjacent edges:")

        for u, v, key, data in G.edges(
            candidate_node,
            keys=True,
            data=True
        ):
            print(
                " ",
                u, "->", v,
                "highway:", data.get("highway"),
                "access:", data.get("access"),
                "foot:", data.get("foot"),
                "length:", data.get("length")
            )

        print("City adjacent edges:")

        for u, v, key, data in city.edges(
            city_node,
            keys=True,
            data=True
        ):
            print(
                " ",
                u, "->", v,
                "highway:", data.get("highway"),
                "access:", data.get("access"),
                "length:", data.get("length")
            )

print("\nInspection completed. No graph was modified.")
