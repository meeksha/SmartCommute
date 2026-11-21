import json
from pathlib import Path

folder = Path("data/raw/namma_yatri")

files = [
    "funnel_cumulative_ca.json",
    "funnel_live_ca.json",
    "trends_live_ca.json",
    "driver_eda_ca.json",
]

for filename in files:
    path = folder / filename

    print("\n" + "=" * 90)
    print("FILE:", filename)

    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    print("Top-level type:", type(data).__name__)

    if isinstance(data, dict):
        print("Top-level keys:", list(data.keys()))

        for key, value in data.items():
            print(f"\nKey: {key}")
            print("Value type:", type(value).__name__)

            if isinstance(value, list):
                print("Number of entries:", len(value))
                if value:
                    print("First entry:")
                    print(json.dumps(value[0], indent=2)[:3000])

            elif isinstance(value, dict):
                print("Nested keys:", list(value.keys())[:40])
                print("Sample:")
                print(json.dumps(value, indent=2)[:3000])

            else:
                print("Value:", str(value)[:500])

    elif isinstance(data, list):
        print("Number of entries:", len(data))
        if data:
            print("First entry:")
            print(json.dumps(data[0], indent=2)[:3000])

