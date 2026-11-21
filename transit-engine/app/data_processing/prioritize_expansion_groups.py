
import pandas as pd

FILE = "data/processed/walking/walking_expansion_subclusters.csv"

df = pd.read_csv(FILE)

print("\n" + "=" * 70)
print("EXPANSION GROUP SUMMARY")
print("=" * 70)

summary = (
    df.groupby("parent_cluster")
    .agg(
        compact_groups=("subcluster", "count"),
        total_stops=("stop_count", "sum"),
        inside_stops=("inside_stops", "sum"),
        outside_stops=("outside_stops", "sum")
    )
)

print(summary.to_string())

# Groups containing at least one stop inside
# the original graph's bounding rectangle.
priority = df[df["inside_stops"] > 0].copy()

priority = priority.sort_values(
    ["inside_stops", "stop_count"],
    ascending=False
)

print("\n" + "=" * 70)
print("PRIORITY EXPANSION GROUPS")
print("=" * 70)

print("Groups containing inside-rectangle stops:", len(priority))
print("Inside stops represented:", priority["inside_stops"].sum())

columns = [
    "parent_cluster",
    "subcluster",
    "stop_count",
    "inside_stops",
    "outside_stops",
    "centre_lat",
    "centre_lon",
    "average_gap_m",
    "maximum_gap_m"
]

print("\nTop 30 groups:")
print(priority[columns].head(30).to_string(index=False))

OUTPUT = "data/processed/walking/priority_expansion_groups.csv"
priority.to_csv(OUTPUT, index=False)

print("\nSaved to:", OUTPUT)
