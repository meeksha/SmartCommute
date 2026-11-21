import networkx as nx
import osmnx as ox
from pyrosm import OSM

pbf = r"C:\Users\1011s\Downloads\southern-zone-261116.osm.pbf"
pilot_path = "data/raw/walking/expansions/bmtc_cluster_21_2.graphml"

bbox = [77.641748, 12.819710, 77.688746, 12.870746]

osm = OSM(pbf, bounding_box=bbox)
nodes, edges = osm.get_network(network_type="walking", nodes=True)
pilot = ox.load_graphml(pilot_path)

G = nx.MultiDiGraph()

for row in nodes[["id", "lon", "lat"]].itertuples(index=False):
    G.add_node(str(row.id), x=float(row.lon), y=float(row.lat))

for row in edges[["u", "v", "length"]].itertuples(index=False):
    G.add_edge(str(row.u), str(row.v), length=float(row.length))

for node_id, data in pilot.nodes(data=True):
    G.add_node(str(node_id), **data)

for u, v, key, data in pilot.edges(keys=True, data=True):
    G.add_edge(str(u), str(v), **data)

components = sorted(
    nx.weakly_connected_components(G),
    key=len,
    reverse=True
)

pbf_ids = {str(n) for n in nodes["id"]}
pilot_ids = {str(n) for n in pilot.nodes}
largest = components[0]

print("\n--- Combined Cluster 21-2 results ---")
print("Combined nodes:", G.number_of_nodes())
print("Combined directed edges:", G.number_of_edges())
print("Components:", len(components))
print("Largest component:", len(largest))
print("Largest component coverage: {:.2f}%".format(
    len(largest) / G.number_of_nodes() * 100
))
print("PBF nodes in largest:", len(largest & pbf_ids))
print("Pilot nodes in largest:", len(largest & pilot_ids))
print("Pilot nodes outside largest:", len(pilot_ids - largest))
print("PBF nodes outside largest:", len(pbf_ids - largest))

print("\nTop 10 component sizes:")
print([len(c) for c in components[:10]])
