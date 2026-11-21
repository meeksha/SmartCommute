
import os
import osmnx as ox

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

# --------------------------------------------------
# LOAD ORIGINAL GRAPH
# --------------------------------------------------

print("\nLoading original walking graph...")

G_original = ox.load_graphml(ORIGINAL_GRAPH)

original_nodes = {
    str(node) for node in G_original.nodes
}

original_edge_pairs = {
    (str(u), str(v))
    for u, v in G_original.edges()
}

original_keyed_edges = {
    (str(u), str(v), str(key))
    for u, v, key in G_original.edges(keys=True)
}

print("Original nodes:", len(original_nodes))
print("Original directed edge pairs:", len(original_edge_pairs))
print("Original keyed edges:", len(original_keyed_edges))

# --------------------------------------------------
# COMPARE EACH PILOT GRAPH
# --------------------------------------------------

for pilot_name, filename in PILOT_GRAPHS.items():

    print("\n" + "=" * 70)
    print("COMPARING PILOT:", pilot_name)
    print("=" * 70)

    filepath = os.path.join(
        EXPANSION_DIR,
        filename
    )

    if not os.path.exists(filepath):
        print("ERROR: Graph file not found:", filepath)
        continue

    G_pilot = ox.load_graphml(filepath)

    pilot_nodes = {
        str(node) for node in G_pilot.nodes
    }

    pilot_edge_pairs = {
        (str(u), str(v))
        for u, v in G_pilot.edges()
    }

    pilot_keyed_edges = {
        (str(u), str(v), str(key))
        for u, v, key in G_pilot.edges(keys=True)
    }

    # --------------------------------------------------
    # NODE OVERLAP
    # --------------------------------------------------

    shared_nodes = original_nodes.intersection(
        pilot_nodes
    )

    pilot_only_nodes = pilot_nodes - original_nodes

    print("\n1. NODE OVERLAP")

    print("Pilot nodes:", len(pilot_nodes))
    print("Exact shared node IDs:", len(shared_nodes))
    print("Pilot-only nodes:", len(pilot_only_nodes))

    print(
        "Percentage of pilot nodes already in original:",
        round(
            len(shared_nodes) / len(pilot_nodes) * 100,
            2
        ),
        "%"
    )

    # --------------------------------------------------
    # DIRECTED EDGE OVERLAP
    # --------------------------------------------------

    shared_edge_pairs = original_edge_pairs.intersection(
        pilot_edge_pairs
    )

    pilot_only_edge_pairs = (
        pilot_edge_pairs - original_edge_pairs
    )

    print("\n2. DIRECTED EDGE-PAIR OVERLAP")

    print("Pilot directed edge pairs:", len(pilot_edge_pairs))
    print("Exact shared edge pairs:", len(shared_edge_pairs))
    print("Pilot-only edge pairs:", len(pilot_only_edge_pairs))

    print(
        "Percentage of pilot edge pairs already in original:",
        round(
            len(shared_edge_pairs) / len(pilot_edge_pairs) * 100,
            2
        ),
        "%"
    )

    # --------------------------------------------------
    # KEYED EDGE OVERLAP
    # --------------------------------------------------

    shared_keyed_edges = original_keyed_edges.intersection(
        pilot_keyed_edges
    )

    pilot_only_keyed_edges = (
        pilot_keyed_edges - original_keyed_edges
    )

    print("\n3. KEYED EDGE OVERLAP")

    print("Pilot keyed edges:", len(pilot_keyed_edges))
    print("Exact shared keyed edges:", len(shared_keyed_edges))
    print("Pilot-only keyed edges:", len(pilot_only_keyed_edges))

    # --------------------------------------------------
    # FINAL INTERPRETATION
    # --------------------------------------------------

    print("\n4. PRELIMINARY INTERPRETATION")

    if len(pilot_only_nodes) == 0 and len(pilot_only_edge_pairs) == 0:
        print(
            "Pilot graph is fully represented in the original "
            "graph by node IDs and directed edge pairs."
        )

    elif len(shared_nodes) > 0:
        print(
            "Pilot graph partially overlaps the original graph. "
            "Further inspection is needed before integration."
        )

    else:
        print(
            "No exact node-ID overlap detected. "
            "Investigate graph alignment."
        )

    del G_pilot

print("\nGRAPH CONTENT COMPARISON COMPLETED.")
