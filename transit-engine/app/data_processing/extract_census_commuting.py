import openpyxl
import pandas as pd
from pathlib import Path

source = Path("data/raw/employees/census_b28_karnataka_2011.xlsx")
output_dir = Path("data/processed/employees")
output_dir.mkdir(parents=True, exist_ok=True)

workbook = openpyxl.load_workbook(
    source,
    read_only=True,
    data_only=True
)

sheet = workbook["B-28"]

distance_columns = [
    "no_travel",
    "distance_0_1_km",
    "distance_2_5_km",
    "distance_6_10_km",
    "distance_11_20_km",
    "distance_21_30_km",
    "distance_31_50_km",
    "distance_51_plus_km",
    "distance_not_stated"
]

records = []

for row in sheet.iter_rows(min_row=7, values_only=True):
    if str(row[2]).strip() != "572":
        continue

    if row[3] != "Urban":
        continue

    record = {
        "district": "Bangalore",
        "district_code": 572,
        "area_type": "Urban",
        "mode": row[5],
        "total_persons": row[6],
    }

    for index, column in zip(
        [9, 12, 15, 18, 21, 24, 27, 30, 33],
        distance_columns
    ):
        record[column] = row[index] or 0

    records.append(record)

workbook.close()

df = pd.DataFrame(records)

df["source"] = "Census of India 2011, Table B-28"
df["survey_year"] = 2011

output_file = output_dir / "bangalore_urban_commuting_statistics.csv"
df.to_csv(output_file, index=False)

print("Extraction completed.")
print("Records:", len(df))
print("Output:", output_file)
print("\nTransport statistics:")
print(df[["mode", "total_persons"]].to_string(index=False))
