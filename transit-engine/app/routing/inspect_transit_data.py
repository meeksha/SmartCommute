import inspect
import pandas as pd
from datetime import date

from app.routing.metro_planner import load_metro_data
from app.routing.bmtc_latest_planner import load_bmtc_latest_data
from app.routing.planner import INTERCHANGES


def describe(name, obj):
    print(f"\n--- {name} ---")
    print("Type:", type(obj))

    if isinstance(obj, tuple):
        print("Tuple length:", len(obj))
        for i, item in enumerate(obj):
            describe(f"{name}[{i}]", item)

    elif isinstance(obj, dict):
        print("Keys:", list(obj.keys()))
        for key, value in obj.items():
            if isinstance(value, pd.DataFrame):
                describe(key, value)

    elif isinstance(obj, pd.DataFrame):
        print("Columns:", list(obj.columns))
        print("Rows:", len(obj))
        print(obj.head(3).to_string(index=False))

    else:
        print(str(obj)[:1000])


print("===== METRO DATA =====")
print("Loader expects:", inspect.signature(load_metro_data))
metro_data = load_metro_data(date(2026, 11, 18))
describe("METRO DATA", metro_data)

print("\n===== BMTC DATA =====")
print("Loader expects:", inspect.signature(load_bmtc_latest_data))
bmtc_data = load_bmtc_latest_data()
describe("BMTC DATA", bmtc_data)

print("\n===== INTERCHANGE DATA =====")
print("Path:", INTERCHANGES)

if INTERCHANGES.exists():
    interchange_df = pd.read_csv(INTERCHANGES)
    describe("INTERCHANGE DATAFRAME", interchange_df)
else:
    print("Interchange file not found.")
