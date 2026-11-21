
import os
import pandas as pd
import osmnx as ox

# --------------------------------------------------
# CONFIGURATION
# --------------------------------------------------

CANDIDATE_FILE = (
    "data/processed/walking/"
    "pilot_component_connection_candidates.csv"
)

ORIGINAL_GRAPH = (
    "data/raw/walking/bengaluru_walking_network.graphml"
)

EXPANSION_DIR = "data/raw/walking/expansions"

PILOT_GRAPHS = {
    "21-2": "bmtc_cluster_21_2.graphml",
    "32-2": "bmtc_cluster_32_2.graphml"
}

# --------------------------------------------------
# LOAD DATA
# --------------------------------------------------

print("\nLoading connection candidates...")

candidates = pd.read_csv(CANDIDATE_FILE)

print("\nLoading original graph...")

G_original = ox.load_graphml(ORIGINAL_GRAPH)

# --------------------------------------------------
# HELPER: FIND NODE BY STRING ID
# --------------------------------------------------

def find_node(G, node_id):

    for node in G.nodes:
        if str(node) == str(node_id):
            return node

    return None


# --------------------------------------------------
# HELPER: INSPECT NODE AND NEIGHBOURS
# --------------------------------------------------

def inspect_node(G, node_id, graph_name):

    node = find_node(G, node_id)

    print(f"\n{graph_name} NODE:", node_id)

    if node is None:
        print("Node not found.")
        return

    print("Node attributes:")
    print(G.nodes[node])

    print("\nConnected road segments:")

    neighbours = list(G.neighbors(node))

    if not neighbours:
        print("No outgoing neighbours.")
        return

    for neighbour in neighbours[:10]:

        edges = G.get_edge_data(node, neighbour)

        for key, data in edges.items():

            print({
                "neighbour": str(neighbour),
                "highway": data.get("highway"),
                "name": data.get("name"),
                "length": data.get("length"),
                "oneway": data.get("oneway")
            })


# --------------------------------------------------
# FIND CLOSEST UNANCHORED COMPONENTS
# --------------------------------------------------

for pilot_name, filename in PILOT_GRAPHS.items():

    print("\n" + "=" * 70)
    print("PILOT:", pilot_name)
    print("=" * 70)

    subset = candidates[
        (candidates["pilot_area"] == pilot_name)
        & (~candidates["anchored"].astype(bool))
    ].copy()

    if subset.empty:
        print("No unanchored components found.")
        continue

    # Closest unanchored component
    closest = subset.sort_values(
        "distance_m"
    ).iloc[0]

    # Largest unanchored component
    largest = subset.sort_values(
        "component_size",
        ascending=False
    ).iloc[0]

    print("\nCLOSEST UNANCHORED COMPONENT")

    print(
        closest[
            [
                "component_number",
                "component_size",
                "distance_m",
                "pilot_node",
                "original_node",
                "pilot_lat",
                "pilot_lon",
                "original_lat",
                "original_lon"
            ]
        ].to_string()
    )

    print("\nLARGEST UNANCHORED COMPONENT")

    print(
        largest[
            [
                "component_number",
                "component_size",
                "distance_m",
                "pilot_node",
                "original_node",
                "pilot_lat",
                "pilot_lon",
                "original_lat",
                "original_lon"
            ]
        ].to_string()
    )

    # --------------------------------------------------
    # LOAD PILOT GRAPH
    # --------------------------------------------------

    pilot_path = os.path.join(
        EXPANSION_DIR,
        filename
    )

    G_pilot = ox.load_graphml(pilot_path)

    # --------------------------------------------------
    # INSPECT CLOSEST PAIR
    # --------------------------------------------------

    print("\n" + "-" * 60)
    print("CLOSEST PAIR: NODE DETAILS")
    print("-" * 60)

    inspect_node(
        G_pilot,
        closest["pilot_node"],
        "PILOT"
    )

    inspect_node(
        G_original,
        closest["original_node"],
        "ORIGINAL"
    )

    # --------------------------------------------------
    # INSPECT LARGEST COMPONENT PAIR
    # --------------------------------------------------

    print("\n" + "-" * 60)
    print("LARGEST COMPONENT: NODE DETAILS")
    print("-" * 60)

    inspect_node(
        G_pilot,
        largest["pilot_node"],
        "PILOT"
    )

    inspect_node(
        G_original,
        largest["original_node"],
        "ORIGINAL"
    )

print("\nCONNECTION CANDIDATE INSPECTION COMPLETED.")
