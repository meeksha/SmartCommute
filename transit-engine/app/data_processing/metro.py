
import shutil
from pathlib import Path
import pandas as pd

RAW_DIR = Path("data/raw/metro")
OUTPUT_DIR = Path("data/processed/metro")

FEEDS = ["standard", "frequencies"]

REQUIRED_FILES = {
    "standard": [
        "agency.txt",
        "routes.txt",
        "stops.txt",
        "trips.txt",
        "stop_times.txt",
        "calendar.txt",
        "calendar_dates.txt",
        "transfers.txt",
    ],
    "frequencies": [
        "agency.txt",
        "routes.txt",
        "stops.txt",
        "trips.txt",
        "stop_times.txt",
        "frequencies.txt",
        "calendar.txt",
        "calendar_dates.txt",
        "transfers.txt",
    ],
}


def process_feed(feed_name):
    source_dir = RAW_DIR / feed_name
    output_dir = OUTPUT_DIR / feed_name

    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"\nProcessing {feed_name.upper()} Metro feed")
    print("-" * 45)

    missing = [
        filename
        for filename in REQUIRED_FILES[feed_name]
        if not (source_dir / filename).exists()
    ]

    if missing:
        raise FileNotFoundError(
            f"Missing required files in {feed_name}: {missing}"
        )

    # Preserve every original GTFS text file.
    # GTFS files are already CSV-formatted.
    for source_file in source_dir.glob("*.txt"):
        destination = output_dir / (
            source_file.stem + ".csv"
        )

        shutil.copy2(source_file, destination)

    # Validate important datasets.
    required_tables = [
        "agency",
        "routes",
        "stops",
        "trips",
        "stop_times",
    ]

    if feed_name == "frequencies":
        required_tables.append("frequencies")

    counts = {}

    for table in required_tables:
        file_path = output_dir / f"{table}.csv"

        df = pd.read_csv(
            file_path,
            dtype=str,
            low_memory=False
        )

        counts[table] = len(df)

        print(f"{table}: {len(df):,} records")

    # Referential integrity checks.
    stops = pd.read_csv(
        output_dir / "stops.csv",
        dtype=str
    )

    trips = pd.read_csv(
        output_dir / "trips.csv",
        dtype=str
    )

    stop_times = pd.read_csv(
        output_dir / "stop_times.csv",
        dtype=str
    )

    missing_trip_ids = (
        set(stop_times["trip_id"])
        - set(trips["trip_id"])
    )

    missing_stop_ids = (
        set(stop_times["stop_id"])
        - set(stops["stop_id"])
    )

    if missing_trip_ids:
        raise ValueError(
            f"{len(missing_trip_ids)} stop_times trip IDs "
            "are missing from trips"
        )

    if missing_stop_ids:
        raise ValueError(
            f"{len(missing_stop_ids)} stop IDs "
            "are missing from stops"
        )

    if feed_name == "frequencies":
        frequencies = pd.read_csv(
            output_dir / "frequencies.csv",
            dtype=str
        )

        frequency_trip_ids = set(frequencies["trip_id"])
        available_trip_ids = set(trips["trip_id"])

        invalid_frequency_ids = (
            frequency_trip_ids - available_trip_ids
        )

        if invalid_frequency_ids:
            raise ValueError(
                f"{len(invalid_frequency_ids)} frequency "
                "trip IDs are missing from trips"
            )

        print(
            "Frequency trip references: VALID"
        )

    print("Stop-time trip references: VALID")
    print("Stop-time stop references: VALID")
    print(f"Processed output: {output_dir}")

    return counts


def main():
    print("BENGALURU METRO GTFS PROCESSOR")
    print("=" * 45)

    results = {}

    for feed in FEEDS:
        results[feed] = process_feed(feed)

    print("\nMETRO PROCESSING COMPLETED")
    print("=" * 45)

    for feed, counts in results.items():
        print(f"\n{feed.upper()}")

        for table, count in counts.items():
            print(f"{table}: {count:,}")

    print("\nOriginal raw GTFS files were not modified.")


if __name__ == "__main__":
    main()

