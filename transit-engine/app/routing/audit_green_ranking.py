from app.routing.bmtc_metro_planner import plan_bmtc_then_metro

result = plan_bmtc_then_metro(
    origin_lat=12.9585,
    origin_lon=77.5635,
    destination_lat=13.0105,
    destination_lon=77.5540,
    travel_date="2026-11-18",
    departure_time="08:00",
)

print("\n===== GREEN-FIRST RANKING AUDIT =====")

if result.get("status") != "success":
    print(result)
    raise SystemExit()

journeys = [result["best_journey"]] + result["alternative_journeys"]

for rank, journey in enumerate(journeys, start=1):
    emissions = journey.get("emissions", {})
    print(
        f"\nRank {rank}",
        "| Conservative emissions:",
        emissions.get("ranking_emissions_kg_co2e"),
        "| Duration:",
        journey.get("total_estimated_duration_minutes"),
    )

    print("Fare:", journey.get("fare"))
    print("BMTC first leg:")
    legs = journey.get("bmtc_journey", {}).get("legs", [])
    if legs:
        print(legs[0])

print("\nLimitations:")
print(result.get("limitations"))
