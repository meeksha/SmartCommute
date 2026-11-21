from pathlib import Path
import pandas as pd

folder = Path("data/processed/walking/connection_inspection")

for cluster, components in {
    "21-2": [44, 5],
    "32-2": [52, 31, 32, 38]
}.items():

    for component in components:
        prefix = f"cluster_{cluster}_{component}"

        nodes = pd.read_csv(folder / f"{prefix}_nodes.csv")
        edges = pd.read_csv(folder / f"{prefix}_edges.csv")

        print("\n" + "=" * 65)
        print(f"CLUSTER {cluster} | COMPONENT {component}")
        print("=" * 65)

        print("\nNODES:")
        print(nodes.to_string(index=False))

        print("\nEDGES:")
        if edges.empty:
            print("No edges found.")
        else:
            print(edges.to_string(index=False))
