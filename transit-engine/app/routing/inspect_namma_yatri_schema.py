from pathlib import Path
import pandas as pd

folder = Path("data/processed/namma_yatri")

for path in sorted(folder.glob("*.csv")):
    print("\n" + "=" * 90)
    print("FILE:", path.name)

    try:
        df = pd.read_csv(path, nrows=5)

        print("Columns:", len(df.columns))
        print("\nCOLUMN NAMES:")
        for col in df.columns:
            print(" -", col)

        print("\nSAMPLE DATA:")
        print(df.head(2).to_string(index=False))

    except Exception as exc:
        print("ERROR:", exc)

print("\n" + "=" * 90)
print("DATA QUALITY REPORT")

report = folder / "data_quality_report.txt"
if report.exists():
    print(report.read_text(encoding="utf-8"))
