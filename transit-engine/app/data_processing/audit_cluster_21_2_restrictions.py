from pathlib import Path
import pandas as pd

file = Path(
    "data/processed/walking/cluster_21_2_access_classified.csv"
)

edges = pd.read_csv(file)

print("--- Access and foot tag combinations ---")

summary = (
    edges.groupby(
        ["access", "foot", "highway"],
        dropna=False
    )
    .agg(
        edge_records=("length", "size"),
        unique_ways=("id", "nunique"),
        total_length=("length", "sum")
    )
    .reset_index()
    .sort_values("edge_records", ascending=False)
)

print(summary.to_string(index=False))

print("\n--- Explicitly restricted combinations ---")

restricted = edges[
    edges["access"].isin(["private", "no", "destination"])
    | edges["foot"].isin(["no", "private"])
]

print("Restricted candidate records:", len(restricted))
print(
    restricted[
        ["id", "u", "v", "highway", "access", "foot", "length"]
    ].head(40).to_string(index=False)
)

print("\nAudit completed.")
