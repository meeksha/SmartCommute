import pandas as pd

files = {
    "Cluster 21-2": "data/processed/walking/cluster_21_2_access_classified.csv",
    "Cluster 32-2": "data/processed/walking/cluster_32_2_walking_access_classified.csv"
}

for name, path in files.items():
    df = pd.read_csv(path)
    print(f"\n--- {name} ---")

    if "motorroad" not in df.columns:
        print("motorroad column: not present")
        continue

    print("motorroad values:")
    print(df["motorroad"].value_counts(dropna=False).to_string())
