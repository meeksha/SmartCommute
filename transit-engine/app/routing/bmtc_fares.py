from pathlib import Path
import zipfile
import csv
import io
import sqlite3

ZIP_PATH = Path("data/raw/bmtc_latest/bmtc_latest.zip")
DB_PATH = Path("data/processed/bmtc_latest/bmtc_fares.sqlite")


def build_fare_database():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    if DB_PATH.exists():
        DB_PATH.unlink()

    connection = sqlite3.connect(DB_PATH)
    cursor = connection.cursor()

    cursor.execute("""
        CREATE TABLE fare_attributes (
            fare_id TEXT PRIMARY KEY,
            price REAL,
            currency_type TEXT,
            payment_method INTEGER,
            transfers INTEGER,
            transfer_duration INTEGER,
            agency_id TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE fare_rules (
            fare_id TEXT,
            route_id TEXT,
            origin_id TEXT,
            destination_id TEXT,
            contains_id TEXT
        )
    """)

    with zipfile.ZipFile(ZIP_PATH) as archive:
        with archive.open("fare_attributes.txt") as raw:
            reader = csv.DictReader(
                io.TextIOWrapper(raw, encoding="utf-8-sig")
            )

            rows = [
                (
                    r["fare_id"],
                    float(r["price"]),
                    r["currency_type"],
                    int(r["payment_method"]),
                    int(r["transfers"]),
                    int(r["transfer_duration"]),
                    r.get("agency_id", "")
                )
                for r in reader
            ]

            cursor.executemany(
                "INSERT INTO fare_attributes VALUES (?, ?, ?, ?, ?, ?, ?)",
                rows
            )

        print("Fare definitions imported:", len(rows))

        batch = []
        count = 0

        with archive.open("fare_rules.txt") as raw:
            reader = csv.DictReader(
                io.TextIOWrapper(raw, encoding="utf-8-sig")
            )

            for r in reader:
                batch.append((
                    r["fare_id"],
                    r.get("route_id", ""),
                    r.get("origin_id", ""),
                    r.get("destination_id", ""),
                    r.get("contains_id", "")
                ))

                if len(batch) >= 20000:
                    cursor.executemany(
                        "INSERT INTO fare_rules VALUES (?, ?, ?, ?, ?)",
                        batch
                    )
                    count += len(batch)
                    batch.clear()

                    if count % 500000 == 0:
                        print("Fare rules imported:", count)

        if batch:
            cursor.executemany(
                "INSERT INTO fare_rules VALUES (?, ?, ?, ?, ?)",
                batch
            )
            count += len(batch)

    print("Total fare rules imported:", count)

    cursor.execute("""
        CREATE INDEX idx_fare_route_stops
        ON fare_rules(route_id, origin_id, destination_id)
    """)

    cursor.execute("""
        CREATE INDEX idx_fare_id
        ON fare_rules(fare_id)
    """)

    connection.commit()
    connection.close()

    print("BMTC fare database created:", DB_PATH)


def get_bmtc_leg_fare(route_id, origin_id, destination_id):
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row

    rows = connection.execute("""
        SELECT DISTINCT
            a.fare_id,
            a.price,
            a.currency_type,
            a.payment_method,
            a.transfers,
            a.transfer_duration
        FROM fare_rules r
        JOIN fare_attributes a ON a.fare_id = r.fare_id
        WHERE r.route_id = ?
          AND r.origin_id = ?
          AND r.destination_id = ?
    """, (route_id, origin_id, destination_id)).fetchall()

    connection.close()

    if not rows:
        return {
            "status": "unavailable",
            "message": "No exact BMTC fare rule found for this leg."
        }

    if len(rows) > 1:
        return {
            "status": "ambiguous",
            "message": "Multiple fare definitions match this leg.",
            "matches": [dict(row) for row in rows]
        }

    fare = dict(rows[0])

    if fare["currency_type"] != "INR":
        return {
            "status": "unavailable",
            "message": "Fare currency is not INR."
        }

    return {
        "status": "success",
        "fare_inr": fare["price"],
        "fare_id": fare["fare_id"],
        "transfers_allowed": fare["transfers"],
        "transfer_duration_minutes": fare["transfer_duration"],
        "payment_method": fare["payment_method"],
        "fare_basis": "2026-2027 community-published BMTC GTFS",
        "is_estimate": True
    }


def calculate_bmtc_journey_fare(legs):
    results = []
    total = 0.0

    for leg in legs:
        fare = get_bmtc_leg_fare(
            leg["route_id"],
            leg["from_stop"],
            leg["to_stop"]
        )

        item = {
            "route": leg.get("route_short_name"),
            "from": leg.get("from_stop_name"),
            "to": leg.get("to_stop_name"),
            **fare
        }

        results.append(item)

        if fare["status"] != "success":
            return {
                "status": "unavailable",
                "legs": results,
                "message": "Could not verify every BMTC leg fare."
            }

        total += fare["fare_inr"]

    return {
        "status": "success",
        "total_fare_inr": round(total, 2),
        "number_of_fare_charges": len(results),
        "legs": results,
        "fare_basis": "Exact route and stop matches in community-published GTFS",
        "is_estimate": True,
        "note": "Each leg is charged separately according to its fare rule. No integrated transfer discount is assumed."
    }


if __name__ == "__main__":
    build_fare_database()

    test_legs = [
        {
            "route_id": "BMTC:2e01e1746789",
            "route_short_name": "49",
            "from_stop": "Wh3C8cd1",
            "to_stop": "Afqg410p",
            "from_stop_name": "Rama Mandira Chamarajapet",
            "to_stop_name": "KR Market"
        },
        {
            "route_id": "BMTC:982fd8b71127",
            "route_short_name": "258",
            "from_stop": "Afqg410p",
            "to_stop": "Hgy30gEx",
            "from_stop_name": "KR Market",
            "to_stop_name": "Ananda Rao Circle"
        },
        {
            "route_id": "BMTC:aa640702b176",
            "route_short_name": "82-AR",
            "from_stop": "Hgy30gEx",
            "to_stop": "G3StG9Rs",
            "from_stop_name": "Ananda Rao Circle",
            "to_stop_name": "Vivekananda College"
        }
    ]

    print("\nBMTC JOURNEY FARE TEST")
    print("======================")

    result = calculate_bmtc_journey_fare(test_legs)

    for leg in result.get("legs", []):
        print(
            leg.get("route"),
            leg.get("from"),
            "->",
            leg.get("to"),
            ":",
            leg.get("fare_inr", leg.get("message"))
        )

    print("\nTotal fare:", result.get("total_fare_inr"))
    print("Status:", result["status"])
