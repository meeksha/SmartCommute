from zipfile import ZipFile
from pathlib import Path

path = Path("data/raw/bmtc_latest/bmtc_latest.zip")

if not path.exists():
    raise FileNotFoundError(path)

with ZipFile(path) as archive:
    print("BMTC FEED FILES")
    print("================")

    for item in archive.infolist():
        print(f"{item.filename:30} {item.file_size:>12,} bytes")

    required = {
        "agency.txt",
        "stops.txt",
        "routes.txt",
        "trips.txt",
        "stop_times.txt",
        "calendar.txt"
    }

    available = {
        Path(name).name for name in archive.namelist()
    }

    print("\nREQUIRED FILE CHECK")
    for name in sorted(required):
        print(name, "FOUND" if name in available else "MISSING")

    if "calendar.txt" in available:
        import pandas as pd
        import io

        calendar = pd.read_csv(
            io.BytesIO(archive.read("calendar.txt"))
        )

        print("\nSERVICE CALENDAR")
        print(calendar.head())
