
import pandas as pd
import json
from pathlib import Path

files = [
    "data/raw/employees/cycle2work_january_2019.csv",
    "data/raw/employees/cycle2work_february_2019.csv",
]

# Approximate Bengaluru geographic bounds
MIN_LAT, MAX_LAT = 12.7, 13.2
MIN_LON, MAX_LON = 77.3, 77.9

total = 0
bengaluru_start = 0
bengaluru_both_ends = 0
invalid_routes = 0

for file in files:
    df = pd.read_csv(file)
    total += len(df)

    for route_text in df["route"]:
        try:
            route = json.loads(route_text)

            if len(route) < 2:
                invalid_routes += 1
                continue

            start_lat, start_lon = route[0]
            end_lat, end_lon = route[-1]

            start_inside = (
                MIN_LAT <= start_lat <= MAX_LAT
                and MIN_LON <= start_lon <= MAX_LON
            )

            end_inside = (
                MIN_LAT <= end_lat <= MAX_LAT
                and MIN_LON <= end_lon <= MAX_LON
            )

            if start_inside:
                bengaluru_start += 1

            if start_inside and end_inside:
                bengaluru_both_ends += 1

        except (ValueError, TypeError, IndexError):
            invalid_routes += 1

print("\nCYCLE2WORK LOCATION REPORT")
print("-" * 40)
print("Total journeys:", total)
print("Bengaluru starting points:", bengaluru_start)
print("Both endpoints in Bengaluru:", bengaluru_both_ends)
print("Invalid routes:", invalid_routes)
