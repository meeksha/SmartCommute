
import os
import osmnx as ox
import pandas as pd
import numpy as np
from scipy.spatial import cKDTree

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

EARTH_RADIUS = 6371000

os.makedirs(OUTPUT_DIR, exist_ok=True)

# --------------------------------------------------
# DISTANCE FUNCTION
# --------------------------------------------------

def to_local_xy(lat, lon, reference_lat):

    lat_rad = np.radians(lat)
    lon_rad = np.radians(lon)
    reference_lat_rad = np.radians(reference_lat)

    x = EARTH_RADIUS * lon_rad * np.cos(reference_lat_rad)
    y = EARTH_RADIUS * lat_rad

    return np.column_stack((x, y))


# --------------------------------------------------
# LOAD ORIGINAL GRAPH
# --------------------------------------------------

print("\nLoading original graph...")

G_original = ox.load_graphml(ORIGINAL_GRAPH)

original_nodes = ox.graph_to_gdfs(
    G_original,
    nodes=True,
    edges=False
)

reference_lat = original_nodes["y"].mean()

original_xy = to_local_xy(
    original_nodes["y"].to_numpy(),
    original_nodes["x"].to_numpy(),
    reference_lat
)

tree = cKDTree(original_xy)

print("Original nodes:", len(original_nodes))

# --------------------------------------------------
# ANALYZE PILOT GRAPHS
# --------------------------------------------------

all_candidates = []

for pilot_name, filename in PILOT_GRAPHS.items():

    print("\n" + "=" * 65)
    print("ANALYZING:", pilot_name)
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

    pilot_xy = to_local_xy(
        pilot_nodes["y"].to_numpy(),
        pilot_nodes["x"].to_numpy(),
        reference_lat
    )

    distances, indices = tree.query(
        pilot_xy,
        k=1
    )

    # --------------------------------------------------
    # FIND CLOSEST PILOT-TO-ORIGINAL NODE PAIRS
    # --------------------------------------------------

    candidates = pd.DataFrame({
        "pilot_area": pilot_name,
        "pilot_node": pilot_nodes.index.astype(str),
        "pilot_lat": pilot_nodes["y"].to_numpy(),
        "pilot_lon": pilot_nodes["x"].to_numpy(),
        "original_node": original_nodes.index.to_numpy()[indices].astype(str),
        "original_lat": original_nodes["y"].to_numpy()[indices],
        "original_lon": original_nodes["x"].to_numpy()[indices],
        "distance_m": distances
    })

    candidates = candidates.sort_values(
        "distance_m"
    )

    print("\nCLOSEST NODE PAIRS")

    print(
        candidates.head(10).to_string(index=False)
    )

    print("\nDISTANCE GROUPS")

    for threshold in [100, 250, 500, 1000, 2000, 5000]:
        count = int(
            (candidates["distance_m"] <= threshold).sum()
        )

        print(
            f"Within {threshold} m: {count}"
        )

    # Save all node-pair candidates
    all_candidates.append(candidates)

    del G_pilot

# --------------------------------------------------
# SAVE RESULTS
# --------------------------------------------------

if all_candidates:

    result = pd.concat(
        all_candidates,
        ignore_index=True
    )

    output_file = os.path.join(
        OUTPUT_DIR,
        "pilot_connection_candidates.csv"
    )

    result.to_csv(
        output_file,
        index=False
    )

    print("\nSaved:", output_file)

print("\nCONNECTION CANDIDATE ANALYSIS COMPLETED.")
