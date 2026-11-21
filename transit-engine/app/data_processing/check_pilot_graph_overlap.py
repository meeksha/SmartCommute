
import os
import osmnx as ox
import pandas as pd
from scipy.spatial import cKDTree
import numpy as np

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

THRESHOLDS = [10, 25, 50, 100]

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

# Convert longitude and latitude to approximate
# local metre coordinates for nearest-node checks.

original_coords = np.radians(
    original_nodes[["y", "x"]].to_numpy()
)

earth_radius = 6371000

original_xy = np.column_stack([
    original_coords[:, 1] * earth_radius *
    np.cos(np.mean(original_coords[:, 0])),

    original_coords[:, 0] * earth_radius
])

tree = cKDTree(original_xy)

print("Original graph nodes:", len(original_nodes))

# --------------------------------------------------
# CHECK EACH PILOT GRAPH
# --------------------------------------------------

for pilot_name, filename in PILOT_GRAPHS.items():

    print("\n" + "=" * 65)
    print("CHECKING PILOT:", pilot_name)
    print("=" * 65)

    filepath = os.path.join(
        EXPANSION_DIR,
        filename
    )

    G_pilot = ox.load_graphml(filepath)

    pilot_nodes = ox.graph_to_gdfs(
        G_pilot,
        nodes=True,
        edges=False
    )

    pilot_coords = np.radians(
        pilot_nodes[["y", "x"]].to_numpy()
    )

    pilot_xy = np.column_stack([
        pilot_coords[:, 1] * earth_radius *
        np.cos(np.mean(pilot_coords[:, 0])),

        pilot_coords[:, 0] * earth_radius
    ])

    distances, _ = tree.query(
        pilot_xy,
        k=1
    )

    print("Pilot nodes:", len(pilot_nodes))

    print("\nDISTANCE TO ORIGINAL GRAPH")

    for threshold in THRESHOLDS:

        count = int(
            np.sum(distances <= threshold)
        )

        percentage = (
            count / len(pilot_nodes) * 100
        )

        print(
            f"Within {threshold} m: "
            f"{count} nodes ({percentage:.2f}%)"
        )

    print(
        "\nAverage nearest distance:",
        round(float(np.mean(distances)), 2),
        "m"
    )

    print(
        "Median nearest distance:",
        round(float(np.median(distances)), 2),
        "m"
    )

    print(
        "Maximum nearest distance:",
        round(float(np.max(distances)), 2),
        "m"
    )

    del G_pilot

print("\nOVERLAP ANALYSIS COMPLETED.")
