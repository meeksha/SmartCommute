from pathlib import Path
import networkx as nx
import osmnx as ox
from pyrosm import OSM

pbf_path = Path(r"C:\Users\1011s\Downloads\southern-zone-261116.osm.pbf")
pilot_path = Path("data/raw/walking/expansions/bmtc_cluster_32_2.graphml")

bbox = [77.736982, 12.998558, 77.783980, 13.049594]

print("Extracting PBF network...")
osm = OSM(str(pbf_path), bounding_box=bbox)
nodes, edges = osm.get_network(network_type="walking", nodes=True)

print("Loading existing pilot graph...")
pilot = ox.load_graphml(pilot_path)

# Build a temporary graph. Neither source file is modified.
combined = nx.MultiDiGraph()

for node_id in nodes["id"]:
    combined.add_node(str(node_id))

for row in edges[["u", "v", "length"]].itertuples(index=False):
    combined.add_edge(
        str(row.u),
        str(row.v),
        length=float(row.length),
        source="pbf"
    )

for node_id, data in pilot.nodes(data=True):
    combined.add_node(str(node_id), **data)

for u, v, key, data in pilot.edges(keys=True, data=True):
    combined.add_edge(str(u), str(v), **data)

components = sorted(
    nx.weakly_connected_components(combined),
    key=len,
    reverse=True
)

pilot_ids = {str(n) for n in pilot.nodes}
pbf_ids = {str(n) for n in nodes["id"]}

largest = components[0]
largest_pilot_nodes = len(largest & pilot_ids)
largest_pbf_nodes = len(largest & pbf_ids)

print("\n--- Combined graph results ---")
print("Combined nodes:", combined.number_of_nodes())
print("Combined directed edges:", combined.number_of_edges())
print("Weakly connected components:", len(components))
print("Largest component:", len(largest))
print("Largest component coverage: {:.2f}%".format(
    len(largest) / combined.number_of_nodes() * 100
))

print("\n--- Largest component composition ---")
print("Pilot nodes included:", largest_pilot_nodes, "/", len(pilot_ids))
print("PBF nodes included:", largest_pbf_nodes, "/", len(pbf_ids))
print("Pilot nodes outside largest:", len(pilot_ids - largest))
print("PBF nodes outside largest:", len(pbf_ids - largest))

print("\nTop 10 component sizes:")
print([len(c) for c in components[:10]])

print("\nCombined graph test completed.")
print("No source graph or PBF file was modified.")
