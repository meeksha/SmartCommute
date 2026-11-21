
import os
import pandas as pd
import osmnx as ox
import networkx as nx

# --------------------------------------------------
# CONFIGURATION
# --------------------------------------------------

GRAPH_DIR = "data/raw/walking/expansions"

GRAPH_FILES = [
    "bmtc_cluster_21_2.graphml",
    "bmtc_cluster_32_2.graphml"
]

# --------------------------------------------------
# VALIDATION FUNCTION
# --------------------------------------------------

def validate_graph(filename):

    filepath = os.path.join(GRAPH_DIR, filename)

    print("\n" + "=" * 70)
    print("VALIDATING:", filename)
    print("=" * 70)

    if not os.path.exists(filepath):
        print("ERROR: File does not exist.")
        return

    # Load graph
    G = ox.load_graphml(filepath)

    # Basic counts
    node_count = len(G.nodes)
    edge_count = len(G.edges)

    print("\n1. GRAPH SIZE")
    print("Nodes:", node_count)
    print("Edges:", edge_count)

    # CRS
    crs = G.graph.get("crs", "Unknown")

    print("\n2. COORDINATE REFERENCE SYSTEM")
    print("CRS:", crs)

    # Node coordinates
    nodes = ox.graph_to_gdfs(
        G,
        nodes=True,
        edges=False
    )

    invalid_coordinates = nodes[
        nodes["x"].isna() |
        nodes["y"].isna() |
        (nodes["x"] < -180) |
        (nodes["x"] > 180) |
        (nodes["y"] < -90) |
        (nodes["y"] > 90)
    ]

    print("\n3. NODE COORDINATES")
    print("Invalid coordinate records:", len(invalid_coordinates))
    print("Minimum latitude:", nodes["y"].min())
    print("Maximum latitude:", nodes["y"].max())
    print("Minimum longitude:", nodes["x"].min())
    print("Maximum longitude:", nodes["x"].max())

    # Edge lengths
    edges = ox.graph_to_gdfs(
        G,
        nodes=False,
        edges=True
    )

    missing_lengths = edges["length"].isna().sum()

    invalid_lengths = (
        edges["length"].isna() |
        (edges["length"] <= 0) |
        (~edges["length"].map(
            lambda value: pd.notna(value) and value < float("inf")
        ))
    ).sum()

    print("\n4. EDGE LENGTHS")
    print("Missing lengths:", missing_lengths)
    print("Invalid lengths:", invalid_lengths)

    if len(edges) > 0:
        print("Minimum length (m):", edges["length"].min())
        print("Maximum length (m):", edges["length"].max())
        print("Average length (m):", round(edges["length"].mean(), 2))

    # Connectivity
    undirected_graph = G.to_undirected()

    components = list(
        nx.connected_components(undirected_graph)
    )
        # Sort components from largest to smallest
    component_sizes = sorted(
        [len(component) for component in components],
        reverse=True
    )

    print("\nCOMPONENT SIZE ANALYSIS")
    print("Total components:", len(component_sizes))
    print("Largest 10 component sizes:", component_sizes[:10])

    print(
        "Components with 10 or fewer nodes:",
        sum(1 for size in component_sizes if size <= 10)
    )

    print(
        "Nodes outside largest component:",
        node_count - component_sizes[0]
    )

    largest_component = (
        max(len(component) for component in components)
        if components else 0
    )

    print("\n5. CONNECTIVITY")
    print("Connected components:", len(components))
    print("Largest component nodes:", largest_component)

    if node_count > 0:
        print(
            "Largest component coverage:",
            round(largest_component / node_count * 100, 2),
            "%"
        )

    # Self-loops
    self_loops = nx.number_of_selfloops(G)

    print("\n6. SELF-LOOPS")
    print("Self-loop count:", self_loops)

    # File size
    file_size_mb = os.path.getsize(filepath) / (1024 * 1024)

    print("\n7. FILE INFORMATION")
    print(f"File size: {file_size_mb:.2f} MB")

    # Basic validation result
    valid = (
        node_count > 0
        and edge_count > 0
        and len(invalid_coordinates) == 0
        and invalid_lengths == 0
        and str(crs).lower() == "epsg:4326"
    )

    print("\n8. VALIDATION RESULT")

    if valid:
        print("PASS: Basic graph checks passed.")
    else:
        print("FAIL: One or more basic graph checks failed.")

    print("=" * 70)


# --------------------------------------------------
# VALIDATE BOTH PILOT GRAPHS
# --------------------------------------------------

print("\nPILOT WALKING NETWORK VALIDATION")
print("=" * 70)

for filename in GRAPH_FILES:
    validate_graph(filename)

print("\nVALIDATION PROCESS COMPLETED.")
