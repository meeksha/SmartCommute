
from pathlib import Path

import networkx as nx
import osmnx as ox
import pandas as pd
from pyrosm import OSM


# --------------------------------------------------
# 1. Paths and extraction settings
# --------------------------------------------------

pbf = r"C:\Users\1011s\Downloads\southern-zone-261116.osm.pbf"

bbox = [
    77.736982,   # west
    12.998558,   # south
    77.783980,   # east
    13.049594    # north
]

access_file = Path(
    "data/processed/walking/cluster_32_2_final_access.csv"
)

output = Path(
    "data/processed/walking/cluster_32_2_pbf_candidate.graphml"
)


# --------------------------------------------------
# 2. Check input file
# --------------------------------------------------

if not Path(pbf).exists():
    raise FileNotFoundError(f"PBF file not found: {pbf}")

if not access_file.exists():
    raise FileNotFoundError(
        f"Final access classification not found: {access_file}"
    )


# --------------------------------------------------
# 3. Load finalized access classification
# --------------------------------------------------

print("Loading finalized access classification...")

access_df = pd.read_csv(access_file)

required_columns = {
    "id",
    "u",
    "v",
    "final_access_class"
}

missing_columns = required_columns - set(access_df.columns)

if missing_columns:
    raise ValueError(
        f"Missing columns in access file: {missing_columns}"
    )

if access_df.duplicated(["id", "u", "v"]).any():
    raise ValueError(
        "Duplicate (id, u, v) combinations found in access file."
    )

print("Classified edges:", len(access_df))


# --------------------------------------------------
# 4. Extract walking network from PBF
# --------------------------------------------------

print("\nExtracting Cluster 32-2 from PBF...")

osm = OSM(pbf, bounding_box=bbox)

nodes, edges = osm.get_network(
    network_type="walking",
    nodes=True
)

print("Extracted nodes:", len(nodes))
print("Extracted edges:", len(edges))


# --------------------------------------------------
# 5. Merge access classification
# --------------------------------------------------

print("\nMatching extracted edges with access classifications...")

# An OSM way ID can occur on multiple edge segments.
# Therefore, use id + u + v as the unique edge identifier.

edges = edges.merge(
    access_df[
        ["id", "u", "v", "final_access_class"]
    ],
    on=["id", "u", "v"],
    how="left",
    validate="one_to_one"
)

if len(edges) != len(access_df):
    raise ValueError(
        "Edge count mismatch: "
        f"extracted={len(edges)}, classified={len(access_df)}"
    )

if edges["final_access_class"].isna().any():
    missing = edges[
        edges["final_access_class"].isna()
    ]

    raise ValueError(
        f"{len(missing)} extracted edges have no access classification."
    )

print("All extracted edges matched successfully.")


# --------------------------------------------------
# 6. Build NetworkX walking graph
# --------------------------------------------------

print("\nBuilding walking graph...")

G = nx.MultiDiGraph()

G.graph["crs"] = "EPSG:4326"
G.graph["network_type"] = "walking"
G.graph["source"] = "Geofabrik Southern Zone OSM PBF"
G.graph["area"] = "Bengaluru Cluster 32-2 expanded"


# --------------------------------------------------
# 7. Add nodes
# --------------------------------------------------

print("Adding nodes...")

for row in nodes[
    ["id", "lon", "lat"]
].itertuples(index=False):

    G.add_node(
        int(row.id),
        x=float(row.lon),
        y=float(row.lat)
    )


# --------------------------------------------------
# 8. Add directed edges
# --------------------------------------------------

print("Adding edges...")

def clean(value):
    return "" if pd.isna(value) else str(value)


for row in edges.itertuples(index=False):

    G.add_edge(
        int(row.u),
        int(row.v),

        length=float(row.length),

        osmid=int(row.id),

        highway=clean(row.highway),
        access=clean(row.access),
        foot=clean(row.foot),
        name=clean(row.name),

        access_class=row.final_access_class
    )


# --------------------------------------------------
# 9. Basic graph checks
# --------------------------------------------------

print("\nChecking graph...")

if G.number_of_nodes() != len(nodes):
    raise ValueError("Node count mismatch after graph construction.")

if G.number_of_edges() != len(edges):
    raise ValueError("Edge count mismatch after graph construction.")

if G.number_of_edges() != 10355:
    print(
        "WARNING: Expected 10,355 edges based on the earlier "
        "extraction. Verify if the PBF source or bounding box changed."
    )


# --------------------------------------------------
# 10. Save candidate GraphML
# --------------------------------------------------

output.parent.mkdir(
    parents=True,
    exist_ok=True
)

print("\nSaving candidate GraphML...")

ox.save_graphml(
    G,
    filepath=output
)


# --------------------------------------------------
# 11. Print summary
# --------------------------------------------------

print("\n========== CLUSTER 32-2 CANDIDATE ==========")

print("Nodes:", G.number_of_nodes())
print("Directed edges:", G.number_of_edges())

print("\nAccess classification:")

classification_counts = pd.Series(
    [
        data["access_class"]
        for _, _, _, data in G.edges(
            keys=True,
            data=True
        )
    ]
)

print(
    classification_counts.value_counts().to_string()
)

print("\nSaved:", output)
print("Original PBF and pilot GraphML files unchanged.")
print("\nCandidate graph creation completed.")
