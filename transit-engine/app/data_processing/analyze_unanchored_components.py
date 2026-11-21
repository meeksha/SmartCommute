
import os
import osmnx as ox
import networkx as nx
import pandas as pd
import numpy as np

from scipy.spatial import cKDTree
from pyproj import Transformer

# --------------------------------------------------
# CONFIGURATION
# --------------------------------------------------

ORIGINAL_GRAPH = (
    "data/raw/walking/bengaluru_walking_network.graphml"
)

EXPANSION_DIR = "data/raw/walking/expansions"

PILOT_GRAPHS = {
    "21-2": "bmtc_cluster_21_2.graphml",
    "32-2": "bmtc_cluster_32_2.graphml"
}

OUTPUT_DIR = "data/processed/walking"

os.makedirs(OUTPUT_DIR, exist_ok=True)

# Bengaluru is in UTM zone 43N.
transformer = Transformer.from_crs(
    "EPSG:4326",
    "EPSG:32643",
    always_xy=True
)

# --------------------------------------------------
# LOAD ORIGINAL GRAPH
# --------------------------------------------------

print("\nLoading original walking graph...")

G_original = ox.load_graphml(ORIGINAL_GRAPH)

original_nodes = ox.graph_to_gdfs(
    G_original,
    nodes=True,
    edges=False
)

original_ids = {
    str(node) for node in G_original.nodes
}

original_x, original_y = transformer.transform(
    original_nodes["x"].to_numpy(),
    original_nodes["y"].to_numpy()
)

original_xy = np.column_stack([
    original_x,
    original_y
])

tree = cKDTree(original_xy)

print("Original graph nodes:", len(original_nodes))

# --------------------------------------------------
# ANALYZE PILOT COMPONENTS
# --------------------------------------------------

all_component_results = []
all_candidate_results = []

for pilot_name, filename in PILOT_GRAPHS.items():

    print("\n" + "=" * 70)
    print("ANALYZING PILOT:", pilot_name)
    print("=" * 70)

    filepath = os.path.join(
        EXPANSION_DIR,
        filename
    )

    G = ox.load_graphml(filepath)

    components = sorted(
        nx.connected_components(G.to_undirected()),
        key=len,
        reverse=True
    )

    print("Total components:", len(components))

    # --------------------------------------------------
    # ANALYZE EACH COMPONENT
    # --------------------------------------------------

    for component_number, component in enumerate(
        components,
        start=1
    ):

        component_ids = {
            str(node) for node in component
        }

        shared_nodes = component_ids.intersection(
            original_ids
        )

        component_data = [
            G.nodes[node] for node in component
        ]

        lons = np.array([
            float(data["x"])
            for data in component_data
        ])

        lats = np.array([
            float(data["y"])
            for data in component_data
        ])

        x, y = transformer.transform(lons, lats)

        component_xy = np.column_stack([x, y])

        distances, nearest_indices = tree.query(
            component_xy,
            k=1
        )

        nearest_position = int(np.argmin(distances))

        pilot_node = list(component)[nearest_position]

        original_position = int(
            nearest_indices[nearest_position]
        )

        original_node = original_nodes.index[
            original_position
        ]

        min_distance = float(distances.min())

        shared_count = len(shared_nodes)

        result = {
            "pilot_area": pilot_name,
            "component_number": component_number,
            "component_size": len(component),
            "shared_original_nodes": shared_count,
            "new_nodes": len(component) - shared_count,
            "anchored": shared_count > 0,
            "minimum_distance_to_original_m": min_distance,
            "median_distance_to_original_m": float(
                np.median(distances)
            ),
            "average_distance_to_original_m": float(
                np.mean(distances)
            ),
            "maximum_distance_to_original_m": float(
                np.max(distances)
            ),
            "nearest_pilot_node": str(pilot_node),
            "nearest_pilot_lat": float(
                G.nodes[pilot_node]["y"]
            ),
            "nearest_pilot_lon": float(
                G.nodes[pilot_node]["x"]
            ),
            "nearest_original_node": str(original_node),
            "nearest_original_lat": float(
                original_nodes.iloc[original_position]["y"]
            ),
            "nearest_original_lon": float(
                original_nodes.iloc[original_position]["x"]
            )
        }

        all_component_results.append(result)

        # --------------------------------------------------
        # PRINT IMPORTANT COMPONENTS
        # --------------------------------------------------

        if component_number <= 10:

            print(
                f"\nComponent {component_number}"
            )

            print("Nodes:", len(component))
            print("Shared original nodes:", shared_count)

            print(
                "Minimum distance to original:",
                round(min_distance, 2),
                "m"
            )

            print(
                "Median distance:",
                round(float(np.median(distances)), 2),
                "m"
            )

            print(
                "Average distance:",
                round(float(np.mean(distances)), 2),
                "m"
            )

            print(
                "Nearest pilot node:",
                pilot_node
            )

            print(
                "Nearest original node:",
                original_node
            )

        # Save the closest node pair for every component.
        all_candidate_results.append({
            "pilot_area": pilot_name,
            "component_number": component_number,
            "component_size": len(component),
            "anchored": shared_count > 0,
            "pilot_node": str(pilot_node),
            "pilot_lat": float(G.nodes[pilot_node]["y"]),
            "pilot_lon": float(G.nodes[pilot_node]["x"]),
            "original_node": str(original_node),
            "original_lat": float(
                original_nodes.iloc[original_position]["y"]
            ),
            "original_lon": float(
                original_nodes.iloc[original_position]["x"]
            ),
            "distance_m": min_distance
        })

    del G

# --------------------------------------------------
# SAVE REPORTS
# --------------------------------------------------

component_df = pd.DataFrame(all_component_results)

candidate_df = pd.DataFrame(all_candidate_results)

component_path = os.path.join(
    OUTPUT_DIR,
    "pilot_unanchored_component_distances.csv"
)

candidate_path = os.path.join(
    OUTPUT_DIR,
    "pilot_component_connection_candidates.csv"
)

component_df.to_csv(
    component_path,
    index=False
)

candidate_df.to_csv(
    candidate_path,
    index=False
)

# --------------------------------------------------
# FINAL SUMMARY
# --------------------------------------------------

print("\n" + "=" * 70)
print("UNANCHORED COMPONENT ANALYSIS COMPLETED")
print("=" * 70)

for pilot_name in PILOT_GRAPHS:

    subset = component_df[
        component_df["pilot_area"] == pilot_name
    ]

    unanchored = subset[
        ~subset["anchored"]
    ]

    print("\nPilot:", pilot_name)

    print("Unanchored components:", len(unanchored))

    if not unanchored.empty:

        print(
            "Largest unanchored component:",
            int(unanchored["component_size"].max())
        )

        print(
            "Closest unanchored component:",
            round(
                unanchored[
                    "minimum_distance_to_original_m"
                ].min(),
                2
            ),
            "m"
        )

print("\nSaved reports:")
print(component_path)
print(candidate_path)

print("\nPROCESS FINISHED.")
