import zipfile
import pandas as pd
from pathlib import Path

zip_path = Path("data/raw/bmtc_latest/bmtc_latest.zip")

with zipfile.ZipFile(zip_path) as archive:
    for filename in ["fare_attributes.txt", "fare_rules.txt"]:
        print(f"\n{'=' * 55}")
        print(filename)

        if filename not in archive.namelist():
            print("File not found in GTFS feed.")
            continue

        with archive.open(filename) as file:
            df = pd.read_csv(file)

        print("Rows:", len(df))
        print("Columns:", list(df.columns))
        print("\nSample records:")
        print(df.head(10).to_string(index=False))
