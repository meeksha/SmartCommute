from app.routing.planner import plan_journey
from app.routing.bmtc_latest_planner import plan_bmtc_latest_from_gps
from app.routing.bmtc_metro_planner import plan_bmtc_then_metro

from app.routing.journey_adapters import (
    adapt_walking_metro,
    adapt_bmtc_journeys,
    adapt_bmtc_metro_journeys,
)
from app.routing.journey_schema import validate_journey, validate_itinerary


ORIGIN_LAT = 13.0107901
ORIGIN_LON = 77.5548862
DESTINATION_LAT = 13.0218597
DESTINATION_LON = 77.5671423
TRAVEL_DATE = "2026-11-18"
DEPARTURE_TIME = "09:00"


def show_journey(journey, index):
    print(f"\nJourney {index}: {journey['mode']}")
    print(
        f"Duration: {journey['duration_minutes']} min | "
        f"Walking: {journey['walking_distance_m']} m | "
        f"Transfers: {journey.get('transfers')}"
    )

    for number, leg in enumerate(journey["legs"], start=1):
        kind = leg.get("type")
        if kind == "walking":
            print(
                f"  {number}. WALK {leg.get('from')} -> {leg.get('to')} "
                f"({leg.get('distance_m')} m, {leg.get('duration_minutes')} min)"
            )
        elif kind == "bmtc_bus":
            print(
                f"  {number}. BMTC {leg.get('route_number')} | "
                f"{leg.get('boarding_stop')} "
                f"({leg.get('departure_time')}) -> "
                f"{leg.get('alighting_stop')} ({leg.get('arrival_time')})"
            )
        elif kind == "metro":
            print(
                f"  {number}. METRO {leg.get('route_name')} towards "
                f"{leg.get('direction')} | "
                f"{leg.get('boarding_station')} "
                f"({leg.get('departure_time')}) -> "
                f"{leg.get('alighting_station')} ({leg.get('arrival_time')})"
            )

    schema_check = validate_journey(journey)
    route_check = validate_itinerary(journey)
    print("Schema:", schema_check["status"], "| Route integrity:", route_check["status"])
    if route_check["errors"]:
        for error in route_check["errors"]:
            print("  ERROR:", error)


def run_test(name, planner, adapter):
    print("\n" + "=" * 75)
    print(name)
    print("=" * 75)
    result = planner(
        ORIGIN_LAT,
        ORIGIN_LON,
        DESTINATION_LAT,
        DESTINATION_LON,
        TRAVEL_DATE,
        DEPARTURE_TIME,
    )
    print("Planner status:", result.get("status"))
    if result.get("status") != "success":
        print("Unavailable:", result.get("message"))
        return []

    journeys = adapter(result)
    print("Valid adapted journeys:", len(journeys))
    for index, journey in enumerate(journeys, start=1):
        show_journey(journey, index)
    if not journeys:
        print("No valid itinerary survived route-integrity checks.")
    return journeys


if __name__ == "__main__":
    run_test("WALKING + METRO", plan_journey, adapt_walking_metro)
    run_test("BMTC BUS", plan_bmtc_latest_from_gps, adapt_bmtc_journeys)
    run_test("BMTC + METRO", plan_bmtc_then_metro, adapt_bmtc_metro_journeys)
