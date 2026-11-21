import json
from pathlib import Path
from collections import defaultdict

path = Path("data/raw/namma_yatri/driver_eda_ca.json")

with path.open("r", encoding="utf-8") as f:
    records = json.load(f)

mapping = defaultdict(set)

for row in records:
    mapping[str(row["ac_num"])].add(row.get("vehicle_type"))

print("AC identifiers:", len(mapping))
print("\nVehicle types associated with each identifier:")

for ac_num in sorted(mapping):
    print(f"{ac_num}: {sorted(str(x) for x in mapping[ac_num])}")

unique_auto = sum(types == {"Auto"} for types in mapping.values())
unique_cab = sum(types == {"Cab"} for types in mapping.values())
both = sum({"Auto", "Cab"}.issubset(types) for types in mapping.values())

print("\nSUMMARY")
print("Auto only:", unique_auto)
print("Cab only:", unique_cab)
print("Both Auto and Cab:", both)
