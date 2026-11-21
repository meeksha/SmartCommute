from pathlib import Path
import pandas as pd

BASE = Path(__file__).resolve().parents[2]
METRO = BASE / "data" / "raw" / "metro"

standard = METRO / "standard"
frequency = METRO / "frequencies"


def read(feed, filename):
    return pd.read_csv(
        feed / filename,
        low_memory=False,
        dtype=str
    )


print("\n========== METRO FEED COMPARISON ==========")

standard_trips = read(standard, "trips.txt")
frequency_trips = read(frequency, "trips.txt")

standard_ids = set(standard_trips["trip_id"])
frequency_ids = set(frequency_trips["trip_id"])

print("\nTRIP COMPARISON")
print("Standard trips:", len(standard_ids))
print("Frequency trips:", len(frequency_ids))
print("Common trip IDs:", len(standard_ids & frequency_ids))
print("Standard-only trips:", len(standard_ids - frequency_ids))
print("Frequency-only trips:", len(frequency_ids - standard_ids))


print("\nROUTE DISTRIBUTION")

routes = read(standard, "routes.txt")
print(routes[["route_id", "route_short_name"]].to_string(index=False))

print("\nTrips per route:")
print(
    standard_trips.groupby("route_id")
    .size()
    .to_string()
)


print("\nCALENDAR EXCEPTIONS")

calendar_dates = read(standard, "calendar_dates.txt")

print(
    calendar_dates.groupby(
        ["service_id", "exception_type"]
    ).size().to_string()
)

print("\nException type meanings:")
print("1 = Service added")
print("2 = Service removed")


print("\nSTATION HIERARCHY")

stops = read(standard, "stops.txt")

print("Total stop records:", len(stops))
print("Unique stop IDs:", stops["stop_id"].nunique())
print("Parent station records:", stops["parent_station"].isna().sum())
print("Records with parent station:", stops["parent_station"].notna().sum())
print("Location type distribution:")
print(stops["location_type"].value_counts(dropna=False).to_string())


print("\nACCESSIBILITY")

print("Wheelchair boarding values:")
print(stops["wheelchair_boarding"].value_counts(dropna=False).to_string())

print("\nTrip wheelchair accessibility:")
print(
    standard_trips["wheelchair_accessible"]
    .value_counts(dropna=False)
    .to_string()
)


print("\nFREQUENCY INFORMATION")

frequency_data = read(frequency, "frequencies.txt")

print("Frequency records:", len(frequency_data))
print("Exact-times distribution:")
print(frequency_data["exact_times"].value_counts(dropna=False).to_string())

print("\nHeadway distribution (seconds):")
print(
    pd.to_numeric(
        frequency_data["headway_secs"],
        errors="coerce"
    ).describe().to_string()
)


print("\nFEED INFORMATION")

feed_info = read(standard, "feed_info.txt")
print(feed_info.to_string(index=False))


print("\n========== VALIDATION COMPLETE ==========")
