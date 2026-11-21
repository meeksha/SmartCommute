
from pathlib import Path
import pandas as pd

BASE = Path(__file__).resolve().parents[2]
OUT = BASE / "data" / "processed" / "namma_yatri"

files = sorted(OUT.glob("*.csv"))

print("NAMMA YATRI PROCESSED DATA VERIFICATION")
print("=" * 60)

for path in files:
    df = pd.read_csv(path)

    print(f"\nFile: {path.name}")
    print("Rows:", len(df))
    print("Columns:", len(df.columns))
    print("Duplicate rows:", df.duplicated().sum())
    print("Source column present:", "source_file" in df.columns)

    if "date" in df.columns:
        dates = pd.to_datetime(df["date"], errors="coerce")
        print("Date range:", dates.min(), "to", dates.max())

    if "city_code" in df.columns:
        print("City codes:", df["city_code"].dropna().unique().tolist())

print("\n" + "=" * 60)
print("Total CSV files:", len(files))
print("Verification completed.")

