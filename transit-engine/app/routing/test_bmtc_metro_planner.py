from pprint import pprint

from app.routing.bmtc_metro_planner import plan_bmtc_then_metro

result = plan_bmtc_then_metro(
    origin_lat=12.9585,
    origin_lon=77.5635,
    destination_lat=13.0105,
    destination_lon=77.5540,
    travel_date="2026-11-18",
    departure_time="08:00",
)

print("\n===== BMTC -> METRO TEST =====")
print("Status:", result.get("status"))
print("Message:", result.get("message", ""))
print("Top-level keys:", list(result.keys()))

# Find journey records without assuming a particular wrapper structure.
journeys = result.get("journeys", [])

if not journeys:
    for value in result.values():
        if isinstance(value, list) and value and isinstance(value[0], dict):
            if "total_estimated_duration_minutes" in value[0]:
                journeys = value
                break

if not journeys:
    print("\nNo combined journey was returned.")
    pprint(result)
    raise SystemExit(0)

print("Combined journeys found:", len(journeys))

for index, journey in enumerate(journeys[:3], start=1):
    print(f"\n===== JOURNEY {index} =====")
    print("Total duration:", journey.get("total_estimated_duration_minutes"), "minutes")
    print("Total walking:", journey.get("total_estimated_walking_metres"), "metres")

    interchange = journey.get("interchange", {})
    print("\nInterchange:")
    pprint(interchange)

    bmtc = journey.get("bmtc_journey", {})
    print("\nBMTC fare:")
    pprint(bmtc.get("fare"))

    print("\nBMTC legs:")
    for leg in bmtc.get("legs", []):
        print(
            leg.get("route_short_name", leg.get("route_id")),
            "|", leg.get("origin_stop_name"),
            "->", leg.get("destination_stop_name"),
            "|", leg.get("departure_time"),
            "->", leg.get("arrival_time"),
        )

    metro = journey.get("metro_journey", {})
    print("\nMetro status:", metro.get("status"))
    print("Metro duration:", metro.get("duration_minutes"), "minutes")
    print("Metro legs:")
    pprint(metro.get("legs"))

    print("\nMetro fare:")
    pprint(journey.get("metro_fare"))

    print("\nCombined emissions:")
    pprint(journey.get("emissions", {}).get("combined_scenarios"))

    print("\nWarnings:")
    print(journey.get("data_warning"))
