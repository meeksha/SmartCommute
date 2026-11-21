from pathlib import Path
import networkx as nx
import osmnx as ox
import pandas as pd
from pyrosm import OSM

pbf = r"C:\Users\1011s\Downloads\southern-zone-261116.osm.pbf"
bbox = [77.641748, 12.819710, 77.688746, 12.870746]

print("Extracting Cluster 21-2...")
osm = OSM(pbf, bounding_box=bbox)
nodes, edges = osm.get_network(
    network_type="walking",
    nodes=True
)

def clean(value):
    return "" if pd.isna(value) else str(value)

def classify(row):
    access = clean(row["access"]).lower()
    foot = clean(row["foot"]).lower()

    if foot in ("yes", "designated", "permissive"):
        return "include_explicit_foot_access"
    if foot in ("no", "private"):
        return "exclude_foot_restricted"
    if access in ("no", "private"):
        return "exclude_general_restricted"
    if access == "destination":
        return "destination_only"
    if access == "permissive":
        return "include_permissive"
    if access == "yes":
        return "include_explicit_access"
    return "review_highway_default"

edges["access_class"] = edges.apply(classify, axis=1)

G = nx.MultiDiGraph()
G.graph["crs"] = "EPSG:4326"
G.graph["network_type"] = "walking"
G.graph["source"] = "Geofabrik Southern Zone OSM PBF"
G.graph["area"] = "Bengaluru Cluster 21-2 expanded"

print("Adding nodes...")
for row in nodes[["id", "lon", "lat"]].itertuples(index=False):
    G.add_node(
        int(row.id),
        x=float(row.lon),
        y=float(row.lat)
    )

print("Adding edges...")
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
        access_class=row.access_class
    )

output = Path(
    "data/processed/walking/cluster_21_2_pbf_candidate.graphml"
)
output.parent.mkdir(parents=True, exist_ok=True)

ox.save_graphml(G, filepath=output)

print("\n--- Candidate created ---")
print("Nodes:", G.number_of_nodes())
print("Directed edges:", G.number_of_edges())
print("\nAccess classification:")
print(edges["access_class"].value_counts().to_string())
print("\nSaved:", output)
print("Original source files unchanged.")
