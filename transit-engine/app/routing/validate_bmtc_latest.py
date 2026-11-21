from zipfile import ZipFile
from pathlib import Path
import pandas as pd
import io

ZIP_PATH = Path("data/raw/bmtc_latest/bmtc_latest.zip")
TEST_DATE = "20261118"

with ZipFile(ZIP_PATH) as archive:

    def read_csv(name):
        return pd.read_csv(
            io.BytesIO(archive.read(name)),
            low_memory=False
        )

    print("\n1. FEED INFORMATION")
    print("===================")
    if "feed_info.txt" in archive.namelist():
        print(read_csv("feed_info.txt").to_string(index=False))

    stops = read_csv("stops.txt")
    routes = read_csv("routes.txt")
    trips = read_csv("trips.txt")
    stop_times = read_csv("stop_times.txt")
    calendar = read_csv("calendar.txt")

    print("\n2. DATASET COUNTS")
    print("=================")
    print("Stops:", len(stops))
    print("Routes:", len(routes))
    print("Trips:", len(trips))
    print("Stop times:", len(stop_times))

    print("\n3. COLUMN SCHEMAS")
    print("=================")
    for name, frame in [
        ("stops", stops),
        ("routes", routes),
        ("trips", trips),
        ("stop_times", stop_times)
    ]:
        print(f"\n{name}: {list(frame.columns)}")

    print("\n4. ACTIVE SERVICES ON", TEST_DATE)
    print("=================================")

    date = pd.to_datetime(TEST_DATE, format="%Y%m%d")
    weekday_column = date.day_name().lower()

    calendar["start_date"] = calendar["start_date"].astype(str)
    calendar["end_date"] = calendar["end_date"].astype(str)

    active = calendar[
        (calendar["start_date"] <= TEST_DATE)
        & (calendar["end_date"] >= TEST_DATE)
        & (calendar[weekday_column] == 1)
    ]

    active_services = active["service_id"].astype(str).tolist()

    print("Weekday:", weekday_column)
    print("Active service count:", len(active_services))
    print("Active services:", active_services[:20])

    active_trips = trips[
        trips["service_id"].astype(str).isin(active_services)
    ]

    print("\n5. ACTIVE TRIP COVERAGE")
    print("=======================")
    print("Active trips:", len(active_trips))
    print("Routes with active trips:",
          active_trips["route_id"].nunique())
    print("Trips with stop times:",
          active_trips["trip_id"].isin(stop_times["trip_id"]).sum())

    active_stop_times = stop_times[
        stop_times["trip_id"].isin(active_trips["trip_id"])
    ]

    print("Active stop-time records:", len(active_stop_times))
    print("Unique active stops:",
          active_stop_times["stop_id"].nunique())

    print("\n6. STOP TIME FORMAT")
    print("===================")
    print(active_stop_times[
        ["trip_id", "stop_id", "stop_sequence",
         "arrival_time", "departure_time"]
    ].head(10).to_string(index=False))

    print("\n7. ROUTE SAMPLE")
    print("===============")
    print(routes.head(5).to_string(index=False))

    print("\n8. STOP SAMPLE")
    print("==============")
    print(stops[
        ["stop_id", "stop_name", "stop_lat", "stop_lon"]
    ].head(5).to_string(index=False))

    print("\n9. CALENDAR EXCEPTIONS")
    print("=====================")
    if "calendar_dates.txt" in archive.namelist():
        exceptions = read_csv("calendar_dates.txt")
        print("Exception records:", len(exceptions))
        print(exceptions.head(10).to_string(index=False))
    else:
        print("No calendar_dates.txt found.")


