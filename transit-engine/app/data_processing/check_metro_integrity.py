from pathlib import Path
import pandas as pd

BASE = Path(__file__).resolve().parents[2]
METRO = BASE / "data" / "raw" / "metro"

STANDARD = METRO / "standard"
FREQUENCY = METRO / "frequencies"


def load(folder, filename):
    return pd.read_csv(folder / filename, dtype=str)


def report_invalid(label, values):
    invalid = len(values)
    print(f"{label}: {invalid}")
    return invalid


def check_feed(folder, name):

    print(f"\n========== {name} INTEGRITY ==========")

    stops = load(folder, "stops.txt")
    routes = load(folder, "routes.txt")
    trips = load(folder, "trips.txt")
    times = load(folder, "stop_times.txt")

    stop_ids = set(stops["stop_id"].dropna())
    route_ids = set(routes["route_id"].dropna())
    trip_ids = set(trips["trip_id"].dropna())

    report_invalid(
        "Stop-time records with unknown trip IDs",
        times.loc[~times["trip_id"].isin(trip_ids)]
    )

    report_invalid(
        "Stop-time records with unknown stop IDs",
        times.loc[~times["stop_id"].isin(stop_ids)]
    )

    report_invalid(
        "Trips with unknown route IDs",
        trips.loc[~trips["route_id"].isin(route_ids)]
    )

    if "parent_station" in stops.columns:
        parents = stops["parent_station"].dropna()

        report_invalid(
            "Stops with unknown parent stations",
            parents[~parents.isin(stop_ids)]
        )

    for filename, source_col, target_col in [
        ("transfers.txt", "from_stop_id", "to_stop_id"),
        ("pathways.txt", "from_stop_id", "to_stop_id")
    ]:

        path = folder / filename

        if not path.exists():
            continue

        data = load(folder, filename)

        invalid = data[
            ~data[source_col].isin(stop_ids)
            | ~data[target_col].isin(stop_ids)
        ]

        report_invalid(
            f"{filename} records with unknown stop IDs",
            invalid
        )

    duplicate_trip_ids = trips[
        trips["trip_id"].duplicated(keep=False)
    ]

    report_invalid(
        "Duplicate trip IDs",
        duplicate_trip_ids
    )

    duplicate_stop_times = times[
        times.duplicated(
            subset=["trip_id", "stop_sequence"],
            keep=False
        )
    ]

    report_invalid(
        "Duplicate trip/stop-sequence combinations",
        duplicate_stop_times
    )

    print("Trips:", len(trips))
    print("Stops:", len(stops))
    print("Stop-time records:", len(times))


def compare_feeds():

    print("\n========== FEED SCHEDULE COMPARISON ==========")

    standard_trips = load(STANDARD, "trips.txt")
    frequency_trips = load(FREQUENCY, "trips.txt")

    standard_times = load(STANDARD, "stop_times.txt")
    frequency_times = load(FREQUENCY, "stop_times.txt")

    common_ids = (
        set(standard_trips["trip_id"])
        & set(frequency_trips["trip_id"])
    )

    fields = [
        "trip_id",
        "stop_id",
        "stop_sequence",
        "arrival_time",
        "departure_time"
    ]

    a = standard_times[
        standard_times["trip_id"].isin(common_ids)
    ][fields].copy()

    b = frequency_times[
        frequency_times["trip_id"].isin(common_ids)
    ][fields].copy()

    a = a.sort_values(
        ["trip_id", "stop_sequence"]
    ).reset_index(drop=True)

    b = b.sort_values(
        ["trip_id", "stop_sequence"]
    ).reset_index(drop=True)

    identical = a.equals(b)

    print("Common trip IDs:", len(common_ids))
    print("Common-trip stop-time tables identical:", identical)

    if not identical:

        merged = a.merge(
            b,
            on=["trip_id", "stop_id", "stop_sequence"],
            how="outer",
            suffixes=("_standard", "_frequency"),
            indicator=True
        )

        print(
            "Different or missing stop-time records:",
            len(merged[merged["_merge"] != "both"])
        )

        time_differences = merged[
            (merged["_merge"] == "both")
            & (
                (merged["arrival_time_standard"]
                 != merged["arrival_time_frequency"])
                | (merged["departure_time_standard"]
                   != merged["departure_time_frequency"])
            )
        ]

        print("Records with different times:", len(time_differences))

        if not time_differences.empty:
            print("\nSample differences:")
            print(time_differences.head(10).to_string(index=False))


def main():

    check_feed(STANDARD, "STANDARD")
    check_feed(FREQUENCY, "FREQUENCY")
    compare_feeds()

    print("\n========== INTEGRITY CHECK COMPLETE ==========")


if __name__ == "__main__":
    main()
