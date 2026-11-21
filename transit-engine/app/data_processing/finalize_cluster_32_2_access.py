from pathlib import Path
import pandas as pd

source = Path("data/processed/walking/cluster_32_2_walking_access_classified.csv")
output = Path("data/processed/walking/cluster_32_2_final_access.csv")

df = pd.read_csv(source)

def clean(value):
    return "" if pd.isna(value) else str(value).strip().lower()

def classify(row):
    access = clean(row["access"])
    foot = clean(row["foot"])

    # Explicit pedestrian permissions override general access restrictions.
    if foot in ("yes", "designated"):
        return "include_explicit_foot_access"

    if foot == "permissive":
        return "include_permissive"

    # Explicit pedestrian restrictions.
    if foot in ("no", "private"):
        return "exclude_foot_restricted"

    # General restrictions, unless overridden by a foot permission.
    if access in ("no", "private"):
        return "exclude_general_restricted"

    if access == "destination":
        return "destination_only"

    if access == "permissive":
        return "include_permissive"

    if access == "yes":
        return "include_explicit_access"

    return "review_highway_default"

df["final_access_class"] = df.apply(classify, axis=1)

print("--- Final access classification ---")
print(df["final_access_class"].value_counts().to_string())

print("\n--- Classification by highway ---")
print(
    pd.crosstab(df["highway"], df["final_access_class"])
    .to_string()
)

print("\n--- Restricted edge summary ---")
restricted = df[
    df["final_access_class"].str.startswith("exclude_")
]
print("Foot-restricted:", (restricted["final_access_class"] == "exclude_foot_restricted").sum())
print("General-restricted:", (restricted["final_access_class"] == "exclude_general_restricted").sum())

df.to_csv(output, index=False)
print("\nSaved:", output)
