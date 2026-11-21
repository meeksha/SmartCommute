from pathlib import Path
import osmnx as ox
import networkx as nx

BASE = Path(__file__).resolve().parents[2]

path = BASE / "data/raw/walking/bengaluru_walking_network.graphml"

G = ox.load_graphml(path)

loops = list(nx.selfloop_edges(G, keys=True, data=True))

print("Total self-loops:", len(loops))

for u, v, key, data in loops[:20]:
    print({
        "node": u,
        "edge_key": key,
        "length": data.get("length"),
        "highway": data.get("highway"),
        "name": data.get("name")
    })