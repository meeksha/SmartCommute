from pathlib import Path
import networkx as nx
import osmnx as ox
from pyrosm import OSM

pbf_path = Path(r"C:\Users\1011s\Downloads\southern-zone-261116.osm.pbf")
original_path = Path("data/raw/walking/bengaluru_walking_network.graphml")
pilot_path = Path("data/raw/walking/expansions/bmtc_cluster_32_2.graphml")

bbox = [77.736982, 12.998558, 77.783980, 13.049594]

print("Extracting walking network from PBF...")
osm = OSM(str(pbf_path), bounding_box=bbox)
nodes, edges = osm.get_network(network_type="walking", nodes=True)

# Construct a directed graph using OSM node IDs.
G = nx.MultiDiGraph()

for node_id in nodes["id"]:
    G.add_node(str(node_id))

for row in edges[["u", "v", "length"]].itertuples(index=False):
    G.add_edge(str(row.u), str(row.v), length=float(row.length))

components = sorted(
    nx.weakly_connected_components(G),
    key=len,
    reverse=True
)

print("\n--- Extracted PBF graph ---")
print("Nodes:", G.number_of_nodes())
print("Edges:", G.number_of_edges())
print("Weakly connected components:", len(components))
print("Largest component:", len(components[0]))
print("Largest component coverage: {:.2f}%".format(
    len(components[0]) / G.number_of_nodes() * 100
))
print("Components with 10 or fewer nodes:", sum(len(c) <= 10 for c in components))

print("\nTop 10 component sizes:")
print([len(c) for c in components[:10]])

# Compare exact OSM node IDs with the existing city graph.
print("\nLoading original Bengaluru walking graph...")
original = ox.load_graphml(original_path)
original_ids = {str(n) for n in original.nodes}
pbf_ids = {str(n) for n in G.nodes}

shared_original = pbf_ids & original_ids

print("\n--- Overlap with original city graph ---")
print("Original graph nodes:", len(original_ids))
print("PBF nodes:", len(pbf_ids))
print("Shared OSM node IDs:", len(shared_original))

# Compare with the existing Cluster 32-2 pilot graph.
print("\nLoading existing Cluster 32-2 pilot graph...")
pilot = ox.load_graphml(pilot_path)
pilot_ids = {str(n) for n in pilot.nodes}
shared_pilot = pbf_ids & pilot_ids

print("\n--- Overlap with Cluster 32-2 pilot ---")
print("Pilot graph nodes:", len(pilot_ids))
print("Shared OSM node IDs:", len(shared_pilot))

# Determine whether shared nodes occur in the largest PBF component.
largest_shared = len(set(components[0]) & shared_original)
largest_pilot_shared = len(set(components[0]) & pilot_ids)

print("\n--- Largest component anchors ---")
print("Shared nodes with original graph:", largest_shared)
print("Shared nodes with pilot graph:", largest_pilot_shared)

print("\nConnectivity analysis completed.")
