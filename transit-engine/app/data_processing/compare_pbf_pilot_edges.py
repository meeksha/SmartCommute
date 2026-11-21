from pathlib import Path
from pyrosm import OSM
import osmnx as ox

pbf_path = Path(r"C:\Users\1011s\Downloads\southern-zone-261116.osm.pbf")
pilot_path = Path("data/raw/walking/expansions/bmtc_cluster_32_2.graphml")

bbox = [77.736982, 12.998558, 77.783980, 13.049594]

print("Extracting PBF network...")
osm = OSM(str(pbf_path), bounding_box=bbox)
nodes, edges = osm.get_network(network_type="walking", nodes=True)

print("Loading existing pilot graph...")
pilot = ox.load_graphml(pilot_path)

# Convert node IDs to strings so the comparison uses consistent types.
pbf_pairs = set(
    (str(row.u), str(row.v))
    for row in edges[["u", "v"]].itertuples(index=False)
)

pilot_pairs = set(
    (str(u), str(v))
    for u, v, key in pilot.edges(keys=True)
)

shared_edges = pbf_pairs & pilot_pairs
new_edges = pbf_pairs - pilot_pairs
pilot_only_edges = pilot_pairs - pbf_pairs

pbf_nodes = set(str(n) for n in nodes["id"])
pilot_nodes = set(str(n) for n in pilot.nodes)

print("\n--- Edge comparison ---")
print("PBF directed edges:", len(pbf_pairs))
print("Pilot directed edges:", len(pilot_pairs))
print("Shared directed edges:", len(shared_edges))
print("New PBF directed edges:", len(new_edges))
print("Pilot-only directed edges:", len(pilot_only_edges))

print("\n--- Node comparison ---")
print("PBF nodes:", len(pbf_nodes))
print("Pilot nodes:", len(pilot_nodes))
print("Shared nodes:", len(pbf_nodes & pilot_nodes))
print("New PBF nodes:", len(pbf_nodes - pilot_nodes))

# Check whether new PBF edges attach to existing pilot nodes.
new_edge_anchors = sum(
    1 for u, v in new_edges
    if u in pilot_nodes or v in pilot_nodes
)

print("\n--- New edge connectivity ---")
print("New edges touching at least one pilot node:", new_edge_anchors)
print("New edges touching neither pilot node:", len(new_edges) - new_edge_anchors)

print("\nComparison completed. No source graph was modified.")
