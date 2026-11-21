from pathlib import Path
import pandas as pd

path = Path("data/processed/walking/cluster_21_2_access_classified.csv")
df = pd.read_csv(path)

def clean(value):
    return "" if pd.isna(value) else str(value).strip().lower()

def classify(row):
    access = clean(row["access"])
    foot = clean(row["foot"])

    # Pedestrian-specific permission takes precedence.
    if foot in ("yes", "designated", "permissive"):
        return "include_explicit_foot_access"

    # Explicit pedestrian restrictions.
    if foot in ("no", "private"):
        return "exclude_foot_restricted"

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

print("\n--- Final access classification ---")
print(df["final_access_class"].value_counts().to_string())

print("\n--- Classification by highway ---")
print(pd.crosstab(
    df["highway"],
    df["final_access_class"]
).to_string())

output = Path("data/processed/walking/cluster_21_2_final_access.csv")
df.to_csv(output, index=False)

print("\nSaved:", output)
