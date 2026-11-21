
import os
import osmnx as ox
import networkx as nx
import pandas as pd

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

# --------------------------------------------------
# LOAD ORIGINAL GRAPH
# --------------------------------------------------

print("\nLoading original walking graph...")

G_original = ox.load_graphml(ORIGINAL_GRAPH)

original_nodes = {
    str(node) for node in G_original.nodes
}

print("Original nodes:", len(original_nodes))

# --------------------------------------------------
# ANALYZE EACH PILOT
# --------------------------------------------------

summary = []
component_records = []

for pilot_name, filename in PILOT_GRAPHS.items():

    print("\n" + "=" * 70)
    print("ANALYZING INTEGRATION READINESS:", pilot_name)
    print("=" * 70)

    filepath = os.path.join(
        EXPANSION_DIR,
        filename
    )

    G_pilot = ox.load_graphml(filepath)

    pilot_nodes = {
        str(node) for node in G_pilot.nodes
    }

    shared_nodes = pilot_nodes.intersection(
        original_nodes
    )

    new_nodes = pilot_nodes - original_nodes

    # Use undirected connectivity for component analysis.
    G_undirected = G_pilot.to_undirected()

    components = sorted(
        nx.connected_components(G_undirected),
        key=len,
        reverse=True
    )

    connected_to_original_nodes = 0
    new_nodes_in_anchored_components = 0
    new_nodes_in_unanchored_components = 0
    anchored_component_count = 0

    print("\nCOMPONENT ANALYSIS")

    for index, component in enumerate(components, start=1):

        component_ids = {
            str(node) for node in component
        }

        shared_count = len(
            component_ids.intersection(shared_nodes)
        )

        new_count = len(
            component_ids.intersection(new_nodes)
        )

        anchored = shared_count > 0

        if anchored:
            anchored_component_count += 1
            connected_to_original_nodes += len(component)
            new_nodes_in_anchored_components += new_count
        else:
            new_nodes_in_unanchored_components += new_count

        component_records.append({
            "pilot_area": pilot_name,
            "component_number": index,
            "component_size": len(component),
            "shared_original_nodes": shared_count,
            "new_nodes": new_count,
            "connected_to_original": anchored
        })

        if index <= 10:
            print(
                f"Component {index}: "
                f"nodes={len(component)}, "
                f"shared={shared_count}, "
                f"new={new_count}, "
                f"anchored={anchored}"
            )

    # --------------------------------------------------
    # SUMMARY
    # --------------------------------------------------

    print("\nINTEGRATION READINESS SUMMARY")

    print("Total pilot nodes:", len(pilot_nodes))
    print("Shared original nodes:", len(shared_nodes))
    print("New pilot nodes:", len(new_nodes))

    print("Total components:", len(components))

    print(
        "Components containing shared nodes:",
        anchored_component_count
    )

    print(
        "Total nodes in anchored components:",
        connected_to_original_nodes
    )

    print(
        "New nodes in anchored components:",
        new_nodes_in_anchored_components
    )

    print(
        "New nodes in unanchored components:",
        new_nodes_in_unanchored_components
    )

    summary.append({
        "pilot_area": pilot_name,
        "total_nodes": len(pilot_nodes),
        "shared_nodes": len(shared_nodes),
        "new_nodes": len(new_nodes),
        "total_components": len(components),
        "anchored_components": anchored_component_count,
        "nodes_in_anchored_components": connected_to_original_nodes,
        "new_nodes_in_anchored_components": new_nodes_in_anchored_components,
        "new_nodes_in_unanchored_components": new_nodes_in_unanchored_components
    })

    del G_pilot

# --------------------------------------------------
# SAVE REPORTS
# --------------------------------------------------

summary_df = pd.DataFrame(summary)

component_df = pd.DataFrame(component_records)

summary_path = os.path.join(
    OUTPUT_DIR,
    "pilot_integration_readiness_summary.csv"
)

component_path = os.path.join(
    OUTPUT_DIR,
    "pilot_component_analysis.csv"
)

summary_df.to_csv(summary_path, index=False)
component_df.to_csv(component_path, index=False)

print("\n" + "=" * 70)
print("INTEGRATION READINESS ANALYSIS COMPLETED")
print("=" * 70)

print("\nSummary:")
print(summary_df.to_string(index=False))

print("\nSaved:")
print(summary_path)
print(component_path)
