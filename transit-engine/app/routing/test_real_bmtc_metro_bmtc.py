"""Real GTFS integration test for Electronic City -> Yelahanka.

Uses the project's actual BMTC 2026-2027 and Namma Metro standard GTFS data.
Run from the project root:
    python -m app.routing.test_real_bmtc_metro_bmtc
"""
from app.routing.bmtc_metro_bmtc_planner import plan_bmtc_metro_bmtc


def main():
    print("REAL-DATA BMTC + METRO + BMTC INTEGRATION TEST")
    print("Origin: Electronic City representative workplace point")
    print("Destination: Yelahanka representative workplace point")
    print("Date: 2026-11-19 | Departure: 09:00")
    print("Metro: Electronic City -> Goraguntepalya")
    print("Loading actual project GTFS data; this may take a minute...")

    result = plan_bmtc_metro_bmtc(
        origin_lat=12.84684,
        origin_lon=77.67042,
        destination_lat=13.10073,
        destination_lon=77.59632,
        travel_date="2026-11-19",
        departure_time="09:00",
        metro_origin_station="Electronic City",
        # Metro GTFS Entrance A coordinates
        metro_origin_lat=12.856402,
        metro_origin_lon=77.663420,
        metro_destination_station="Goraguntepalya",
        # Metro GTFS Entrance C coordinates
        metro_destination_lat=13.028390,
        metro_destination_lon=77.540306,
    )

    print("\nRESULT")
    print("Status:", result.get("status"))
    if result.get("status") != "success":
        print("Failed stage:", result.get("stage"))
        print("Reason:", result.get("message"))
        details = result.get("details") or {}
        if details:
            print("Planner details:", details.get("message", details))
        raise AssertionError("Real three-mode journey was not generated")

    assert result["journey_type"] == "BMTC + Metro + BMTC"
    assert len(result["legs"]) == 3
    assert [leg["mode"] for leg in result["legs"]] == [
        "BMTC feeder", "Metro", "BMTC feeder"
    ]

    first, metro, last = result["legs"]
    first_bus = first["journey"]["bmtc_journey"]
    metro_journey = metro["journey"]
    last_bus = last["journey"]["bmtc_journey"]

    # Validate that the feeder legs and Metro legs have actual scheduled data.
    assert first_bus["number_of_bus_legs"] >= 1
    assert len(metro_journey["legs"]) >= 1
    assert last_bus["number_of_bus_legs"] >= 1
    assert first_bus["arrival"] <= metro_journey["departure"]
    assert metro_journey["arrival"] <= last_bus["departure"]
    assert result["walking_m"] <= 4800  # Sum of configured leg walking caps.

    print("\nITINERARY")
    print(
        "1. BMTC origin feeder:", first_bus["departure"], "->",
        first_bus["arrival"], "| bus legs:", first_bus["number_of_bus_legs"],
    )
    print(
        "   Origin access:", first["journey"]["origin_access"]["distance_m"],
        "m | Metro egress:", first["journey"]["destination_egress"]["distance_m"], "m",
    )
    print(
        "2. Metro:", metro_journey["departure"], "->",
        metro_journey["arrival"], "| train legs:", len(metro_journey["legs"]),
    )
    print(
        "3. BMTC destination feeder:", last_bus["departure"], "->",
        last_bus["arrival"], "| bus legs:", last_bus["number_of_bus_legs"],
    )
    print(
        "   Metro access:", last["journey"]["origin_access"]["distance_m"],
        "m | Final egress:", last["journey"]["destination_egress"]["distance_m"], "m",
    )
    print("\nTotal duration:", result["total_duration_minutes"], "minutes")
    print("Final arrival (including final walk):", result["arrival"])
    print("Total walking:", result["walking_m"], "m")
    print("Transfer buffer:", result["transfer_buffer_minutes"], "minutes")
    print("\nData limitations:")
    for warning in result.get("data_warnings", []):
        print("-", warning)

    print("\nREAL-DATA THREE-MODE INTEGRATION TEST PASSED")


if __name__ == "__main__":
    main()
