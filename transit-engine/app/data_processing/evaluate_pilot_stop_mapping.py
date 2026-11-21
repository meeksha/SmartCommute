
import os
import pandas as pd
import osmnx as ox

# --------------------------------------------------
# CONFIGURATION
# --------------------------------------------------

BMTC_STOPS = "data/processed/bmtc_stops.csv"

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

# --------------------------------------------------
# LOAD BMTC STOPS
# --------------------------------------------------

print("\nLoading BMTC stops...")

stops = pd.read_csv(BMTC_STOPS)

print("Total BMTC stops:", len(stops))

# --------------------------------------------------
# LOAD ORIGINAL WALKING GRAPH
# --------------------------------------------------

print("\nLoading original Bengaluru walking graph...")

G_original = ox.load_graphml(ORIGINAL_GRAPH)

print("Original graph nodes:", len(G_original.nodes))

# --------------------------------------------------
# HELPER: CALCULATE NEAREST NODE DISTANCES
# --------------------------------------------------

def calculate_distances(G, stop_data):

    valid_stops = stop_data.dropna(
        subset=["stop_lat", "stop_lon"]
    ).copy()

    nearest_nodes = ox.distance.nearest_nodes(
        G,
        X=valid_stops["stop_lon"].to_numpy(),
        Y=valid_stops["stop_lat"].to_numpy()
    )

    node_x = pd.Series(nearest_nodes).map(
        lambda node: G.nodes[node]["x"]
    ).to_numpy()

    node_y = pd.Series(nearest_nodes).map(
        lambda node: G.nodes[node]["y"]
    ).to_numpy()

    distances = ox.distance.great_circle(
        valid_stops["stop_lat"].to_numpy(),
        valid_stops["stop_lon"].to_numpy(),
        node_y,
        node_x
    )

    result = valid_stops[
        ["stop_id", "stop_name", "stop_lat", "stop_lon"]
    ].copy()

    result["nearest_node"] = nearest_nodes
    result["distance_m"] = distances

    return result

# --------------------------------------------------
# ORIGINAL GRAPH DISTANCES
# --------------------------------------------------

print("\nCalculating original graph distances...")

original_results = calculate_distances(
    G_original,
    stops
)

original_results = original_results.rename(
    columns={"distance_m": "original_distance_m"}
)

# --------------------------------------------------
# EVALUATE EACH PILOT GRAPH
# --------------------------------------------------

all_results = []

for pilot_name, filename in PILOT_GRAPHS.items():

    filepath = os.path.join(
        EXPANSION_DIR,
        filename
    )

    print("\n" + "=" * 65)
    print("EVALUATING PILOT:", pilot_name)
    print("=" * 65)

    if not os.path.exists(filepath):
        print("Graph file missing:", filepath)
        continue

    G_pilot = ox.load_graphml(filepath)

    print("Pilot nodes:", len(G_pilot.nodes))

    # Only evaluate stops geographically inside
    # the pilot graph's bounding box.

    min_lat = min(
        data["y"] for _, data in G_pilot.nodes(data=True)
    )
    max_lat = max(
        data["y"] for _, data in G_pilot.nodes(data=True)
    )
    min_lon = min(
        data["x"] for _, data in G_pilot.nodes(data=True)
    )
    max_lon = max(
        data["x"] for _, data in G_pilot.nodes(data=True)
    )

    local_stops = stops[
        stops["stop_lat"].between(min_lat, max_lat)
        & stops["stop_lon"].between(min_lon, max_lon)
    ].copy()

    print("BMTC stops inside pilot bounds:", len(local_stops))

    if local_stops.empty:
        print("No BMTC stops found inside this pilot area.")
        continue

    pilot_results = calculate_distances(
        G_pilot,
        local_stops
    )

    # Calculate original graph distances for same stops.

    comparison = pilot_results.merge(
        original_results[
            ["stop_id", "original_distance_m"]
        ],
        on="stop_id",
        how="left"
    )

    comparison = comparison.rename(
        columns={"distance_m": "pilot_distance_m"}
    )

    comparison["pilot_area"] = pilot_name

    comparison["improvement_m"] = (
        comparison["original_distance_m"]
        - comparison["pilot_distance_m"]
    )

    comparison["within_50m"] = (
        comparison["pilot_distance_m"] <= 50
    )

    comparison["within_100m"] = (
        comparison["pilot_distance_m"] <= 100
    )

    comparison["within_250m"] = (
        comparison["pilot_distance_m"] <= 250
    )

    print("\nDISTANCE COMPARISON")
    print(
        "Average original distance:",
        round(comparison["original_distance_m"].mean(), 2),
        "m"
    )

    print(
        "Average pilot distance:",
        round(comparison["pilot_distance_m"].mean(), 2),
        "m"
    )

    print(
        "Stops within 50m:",
        int(comparison["within_50m"].sum())
    )

    print(
        "Stops within 100m:",
        int(comparison["within_100m"].sum())
    )

    print(
        "Stops within 250m:",
        int(comparison["within_250m"].sum())
    )

    print(
        "Average distance improvement:",
        round(comparison["improvement_m"].mean(), 2),
        "m"
    )

    all_results.append(comparison)

    del G_pilot

# --------------------------------------------------
# SAVE RESULTS
# --------------------------------------------------

if all_results:

    final_results = pd.concat(
        all_results,
        ignore_index=True
    )

    output_file = os.path.join(
        OUTPUT_DIR,
        "pilot_bmtc_stop_mapping_evaluation.csv"
    )

    final_results.to_csv(
        output_file,
        index=False
    )

    print("\n" + "=" * 65)
    print("EVALUATION COMPLETED")
    print("=" * 65)

    print("Total evaluated stop records:", len(final_results))
    print("Saved:", output_file)

else:
    print("\nNo pilot areas were evaluated.")

print("\nPROCESS FINISHED.")
