import pandas as pd
from pathlib import Path

base = Path("data/processed")

files = [
    "bmtc_stop_times.csv",
    "bmtc_trips.csv",
    "bmtc_routes.csv",
    "bmtc_shapes.csv"
]

for filename in files:
    path = base / filename

    print(f"\n--- {filename} ---")

    df = pd.read_csv(path, nrows=5)

    print("Columns:", df.columns.tolist())
    print(df.head(2).to_string(index=False))

print("\n--- Raw BMTC files ---")

raw_path = Path("data/raw/bmtc")

for file in raw_path.rglob("*"):
    if file.is_file():
        print(file.name)
