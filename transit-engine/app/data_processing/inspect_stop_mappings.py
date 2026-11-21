
import pandas as pd

files = [
    "data/processed/walking/bmtc_walking_node_mapping.csv",
    "data/processed/walking/metro_walking_node_mapping.csv"
]

for file in files:
    df = pd.read_csv(file)

    print("\n" + "=" * 60)
    print("FILE:", file)
    print("=" * 60)

    print("\nCOLUMNS:")
    print(df.columns.tolist())

    print("\nFIRST TWO ROWS:")
    print(df.head(2).to_string(index=False))
