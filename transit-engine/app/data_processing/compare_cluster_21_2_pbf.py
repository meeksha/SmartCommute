from pathlib import Path
import osmnx as ox
from pyrosm import OSM

pbf = r"C:\Users\1011s\Downloads\southern-zone-261116.osm.pbf"
pilot_path = Path("data/raw/walking/expansions/bmtc_cluster_21_2.graphml")

bbox = [77.641748, 12.819710, 77.688746, 12.870746]

osm = OSM(pbf, bounding_box=bbox)
nodes, edges = osm.get_network(network_type="walking", nodes=True)

pilot = ox.load_graphml(pilot_path)

pbf_nodes = {str(n) for n in nodes["id"]}
pilot_nodes = {str(n) for n in pilot.nodes}

pbf_edges = {
    (str(r.u), str(r.v))
    for r in edges[["u", "v"]].itertuples(index=False)
}

pilot_edges = {
    (str(u), str(v))
    for u, v, k in pilot.edges(keys=True)
}

shared_nodes = pbf_nodes & pilot_nodes
shared_edges = pbf_edges & pilot_edges
new_edges = pbf_edges - pilot_edges

print("\n--- Cluster 21-2 comparison ---")
print("PBF nodes:", len(pbf_nodes))
print("Pilot nodes:", len(pilot_nodes))
print("Shared nodes:", len(shared_nodes))
print("New PBF nodes:", len(pbf_nodes - pilot_nodes))
print("PBF directed edges:", len(pbf_edges))
print("Pilot directed edges:", len(pilot_edges))
print("Shared edges:", len(shared_edges))
print("New PBF edges:", len(new_edges))
print("New edges touching pilot nodes:", sum(
    1 for u, v in new_edges
    if u in pilot_nodes or v in pilot_nodes
))

print("\nComparison completed. Source files unchanged.")
