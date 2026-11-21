import pandas as pd

path = "data/processed/walking/cluster_32_2_final_access.csv"
df = pd.read_csv(path)

print("Total rows:", len(df))
print("Unique way IDs:", df["id"].nunique())
print("Duplicate (id, u, v) rows:", df.duplicated(["id", "u", "v"]).sum())

duplicates = df[df.duplicated(["id", "u", "v"], keep=False)]
print("\nDuplicate edge examples:")
print(duplicates[["id", "u", "v", "highway", "access", "foot", "final_access_class"]].head(15).to_string(index=False))
