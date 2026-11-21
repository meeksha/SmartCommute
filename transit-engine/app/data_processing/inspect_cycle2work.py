
import pandas as pd
from pathlib import Path

files = [
    Path("data/raw/employees/cycle2work_january_2019.csv"),
    Path("data/raw/employees/cycle2work_february_2019.csv"),
]

for file in files:
    print("\n" + "=" * 70)
    print(f"FILE: {file.name}")

    df = pd.read_csv(file, low_memory=False)

    print("Shape:", df.shape)
    print("\nColumns:")
    for column in df.columns:
        print(f" - {column}")

    print("\nData types:")
    print(df.dtypes)

    print("\nFirst 5 records:")
    print(df.head().to_string())

    print("\nMissing values:")
    print(df.isna().sum().to_string())
