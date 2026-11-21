import pandas as pd
from pathlib import Path

DATA_PATH = Path("data/raw/bmtc")
OUTPUT_PATH = Path("data/processed")

def load_gtfs(filename):
    path = DATA_PATH / filename

    if not path.exists():
        print(f"Missing: {filename}")
        return pd.DataFrame()

    return pd.read_csv(path, dtype=str).fillna("")


def load_bmtc_data():

    print("\nLoading BMTC GTFS data...\n")

    files = {
        "agency": "agency.txt",
        "calendar": "calendar.txt",
        "stops": "stops.txt",
        "routes": "routes.txt",
        "trips": "trips.txt",
        "stop_times": "stop_times.txt",
        "shapes": "shapes.txt"
    }

    data = {}

    for name, filename in files.items():

        df = load_gtfs(filename)
        data[name] = df

        print(f"{name}: {len(df):,} records")

    return data


def process_bmtc():

    OUTPUT_PATH.mkdir(parents=True, exist_ok=True)

    data = load_bmtc_data()

    for name, df in data.items():

        if not df.empty:

            output_file = OUTPUT_PATH / f"bmtc_{name}.csv"

            df.to_csv(output_file, index=False)

            print(f"Saved: {output_file}")

    print("\nBMTC processing completed!")


if __name__ == "__main__":
    process_bmtc()
