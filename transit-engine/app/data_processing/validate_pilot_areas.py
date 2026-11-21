
import pandas as pd

PILOT_FILE = "data/processed/walking/walking_pilot_areas.csv"
GROUP_FILE = "data/processed/walking/walking_expansion_subclusters.csv"

pilots = pd.read_csv(PILOT_FILE)
groups = pd.read_csv(GROUP_FILE)

merged = pilots.merge(
    groups,
    on=["parent_cluster", "subcluster"],
    suffixes=("_pilot", "_group")
)

print("\n" + "=" * 70)
print("PILOT AREA COVERAGE VALIDATION")
print("=" * 70)

all_valid = True

for _, row in merged.iterrows():

    # Check whether the pilot rectangle contains
    # the complete geographical extent of its group.
    contains_all = (
        row["south_pilot"] <= row["south_group"] and
        row["north_pilot"] >= row["north_group"] and
        row["west_pilot"] <= row["west_group"] and
        row["east_pilot"] >= row["east_group"]
    )

    print(
        f"\nPilot {int(row['parent_cluster'])}-"
        f"{int(row['subcluster'])}"
    )

    print("Stops:", int(row["stop_count_group"]))
    print("Pilot box contains every group extent:", contains_all)

    if not contains_all:
        all_valid = False
        print("Required group extent:")
        print(
            "South:", row["south_group"],
            "North:", row["north_group"],
            "West:", row["west_group"],
            "East:", row["east_group"]
        )

print("\n" + "=" * 70)

if all_valid and len(merged) == len(pilots):
    print("RESULT: Both pilot areas cover their complete groups.")
else:
    print("RESULT: At least one pilot area needs adjustment.")
