from pathlib import Path
from pyrosm import OSM
import pandas as pd

pbf_path = Path(r"C:\Users\1011s\Downloads\southern-zone-261116.osm.pbf")
bbox = [77.736982, 12.998558, 77.783980, 13.049594]

osm = OSM(str(pbf_path), bounding_box=bbox)
nodes, edges = osm.get_network(network_type="walking", nodes=True)

print("Total extracted edges:", len(edges))

checks = {
    "access_no": edges["access"].astype(str).str.lower().eq("no"),
    "foot_no": edges["foot"].astype(str).str.lower().eq("no"),
    "motorroad_yes": edges["motorroad"].astype(str).str.lower().eq("yes"),
    "access_private": edges["access"].astype(str).str.lower().eq("private"),
    "foot_private": edges["foot"].astype(str).str.lower().eq("private"),
}

print("\n--- Access restriction audit ---")
for name, mask in checks.items():
    print(f"{name}: {mask.sum()}")

restricted = edges.loc[
    checks["access_no"] |
    checks["foot_no"] |
    checks["motorroad_yes"] |
    checks["access_private"] |
    checks["foot_private"]
]

print("\nRestricted edge records:", len(restricted))

columns = [
    "id", "u", "v", "highway", "access",
    "foot", "motorroad", "name", "length"
]

print("\nRestricted edge examples:")
if len(restricted):
    print(restricted[columns].head(30).to_string(index=False))
else:
    print("No explicit restrictions found.")

output = Path("data/processed/walking/cluster_32_2_access_restrictions.csv")
restricted[columns].to_csv(output, index=False)

print("\nSaved:", output)
