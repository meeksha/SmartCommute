from pathlib import Path
import pandas as pd

BASE = Path(__file__).resolve().parents[2]
METRO = BASE / "data" / "raw" / "metro"

STD = METRO / "standard"
FREQ = METRO / "frequencies"


def read(folder, filename):
    return pd.read_csv(folder / filename, dtype=str)


def to_seconds(value):
    if pd.isna(value):
        return None

    parts = str(value).split(":")

    if len(parts) != 3:
        return None

    return (
        int(parts[0]) * 3600
        + int(parts[1]) * 60
        + int(float(parts[2]))
    )


def main():

    standard = read(STD, "stop_times.txt")
    frequency = read(FREQ, "stop_times.txt")

    standard_trips = read(STD, "trips.txt")
    frequency_trips = read(FREQ, "trips.txt")

    frequency_windows = read(FREQ, "frequencies.txt")

    common = (
        set(standard["trip_id"])
        & set(frequency["trip_id"])
    )

    print("\n========== SCHEDULE OFFSET ANALYSIS ==========")

    results = []

    for trip_id in sorted(common):

        a = standard[standard["trip_id"] == trip_id].copy()
        b = frequency[frequency["trip_id"] == trip_id].copy()

        a = a.sort_values("stop_sequence")
        b = b.sort_values("stop_sequence")

        if len(a) != len(b):
            continue

        a = a.reset_index(drop=True)
        b = b.reset_index(drop=True)

        if not (
            a["stop_id"].equals(b["stop_id"])
            and a["stop_sequence"].equals(b["stop_sequence"])
        ):
            continue

        offsets = []

        for i in range(len(a)):
            std_time = to_seconds(a.loc[i, "arrival_time"])
            freq_time = to_seconds(b.loc[i, "arrival_time"])

            if std_time is not None and freq_time is not None:
                offsets.append(std_time - freq_time)

        if offsets:
            results.append({
                "trip_id": trip_id,
                "stop_count": len(a),
                "offset_min": min(offsets) / 60,
                "offset_max": max(offsets) / 60,
                "constant_offset": len(set(offsets)) == 1,
                "offset_minutes": offsets[0] / 60
            })

    result = pd.DataFrame(results)

    print("Trips compared:", len(result))
    print(
        "Trips with constant time offset:",
        result["constant_offset"].sum()
    )
    print(
        "Trips with varying time offsets:",
        (~result["constant_offset"]).sum()
    )

    print("\nMost common time offsets (minutes):")
    print(
        result["offset_minutes"]
        .round(2)
        .value_counts()
        .head(15)
        .to_string()
    )

    print("\nSample trip offsets:")
    print(result.head(20).to_string(index=False))

    print("\n========== FREQUENCY WINDOWS ==========")

    print(
        frequency_windows[
            ["trip_id", "start_time", "end_time",
             "headway_secs", "exact_times"]
        ].head(20).to_string(index=False)
    )

    print("\n========== TRIP METADATA COMPARISON ==========")

    metadata = standard_trips[
        ["trip_id", "route_id", "service_id", "trip_headsign"]
    ].merge(
        frequency_trips[
            ["trip_id", "route_id", "service_id", "trip_headsign"]
        ],
        on="trip_id",
        suffixes=("_standard", "_frequency")
    )

    for column in ["route_id", "service_id", "trip_headsign"]:

        differences = (
            metadata[f"{column}_standard"]
            != metadata[f"{column}_frequency"]
        ).sum()

        print(f"{column} differences:", differences)


if __name__ == "__main__":
    main()
