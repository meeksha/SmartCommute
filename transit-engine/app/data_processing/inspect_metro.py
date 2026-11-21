from pathlib import Path
import pandas as pd

BASE_DIR = Path(__file__).resolve().parents[2]
METRO_DIR = BASE_DIR / "data" / "raw" / "metro"

FEEDS = {
    "STANDARD": METRO_DIR / "standard",
    "FREQUENCIES": METRO_DIR / "frequencies"
}

IMPORTANT_FILES = [
    "agency.txt",
    "routes.txt",
    "stops.txt",
    "trips.txt",
    "stop_times.txt",
    "calendar.txt",
    "calendar_dates.txt",
    "frequencies.txt",
    "transfers.txt",
    "pathways.txt",
    "fare_attributes.txt",
    "fare_rules.txt",
    "fare_products.txt",
    "fare_leg_rules.txt",
    "shapes.txt",
    "feed_info.txt"
]


def inspect_feed(feed_name, folder):

    print("\n" + "=" * 65)
    print(f" {feed_name} METRO FEED")
    print("=" * 65)

    if not folder.exists():
        print("Feed folder not found:", folder)
        return

    for filename in IMPORTANT_FILES:

        filepath = folder / filename

        if not filepath.exists():
            continue

        try:
            df = pd.read_csv(filepath, low_memory=False)

            print(f"\n--- {filename} ---")
            print("Rows:", len(df))
            print("Columns:", list(df.columns))

            if filename == "stops.txt":
                print("Unique stop IDs:", df["stop_id"].nunique())
                print("Sample:")
                print(df.head(5).to_string(index=False))

            elif filename == "routes.txt":
                print("Unique routes:", df["route_id"].nunique())
                print(df.head(5).to_string(index=False))

            elif filename == "trips.txt":
                print("Unique trips:", df["trip_id"].nunique())
                print(df.head(5).to_string(index=False))

            elif filename == "stop_times.txt":
                print("Unique trips:", df["trip_id"].nunique())
                print("Unique stops:", df["stop_id"].nunique())
                print(df.head(5).to_string(index=False))

            elif filename == "calendar.txt":
                print(df.to_string(index=False))

            elif filename == "calendar_dates.txt":
                print(df.head(10).to_string(index=False))

            elif filename == "frequencies.txt":
                print(df.head(10).to_string(index=False))

            elif filename in [
                "transfers.txt",
                "pathways.txt",
                "fare_attributes.txt",
                "fare_rules.txt",
                "fare_products.txt",
                "fare_leg_rules.txt",
                "feed_info.txt"
            ]:
                print(df.head(5).to_string(index=False))

        except Exception as error:
            print(f"Could not inspect {filename}: {error}")


def main():

    for feed_name, folder in FEEDS.items():
        inspect_feed(feed_name, folder)


if __name__ == "__main__":
    main()
