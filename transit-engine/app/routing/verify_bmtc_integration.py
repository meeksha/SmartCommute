from app.routing.bmtc_planner import plan_bmtc

result = plan_bmtc(
    origin="Income Tax Layout Cross 1",
    destination="RMC Yard (Yashawanthapura New Railway Station)",
    travel_date="2024-11-07",
    departure_time="08:00"
)

print("\nHYBRID BMTC PREDICTION TEST")
print("===========================")
print("Status:", result["status"])
print("Scheduled arrival:", result.get("arrival"))
print("Scheduled duration:", result.get("duration_minutes"), "minutes")

for i, leg in enumerate(result.get("legs", []), 1):
    print(f"\nBus Leg {i}: {leg['route_short_name']}")
    print("From:", leg["from_stop_name"])
    print("To:", leg["to_stop_name"])
    print("Scheduled segment duration:",
          leg.get("scheduled_segment_duration_min"))
    print("Predicted segment duration:",
          leg.get("duration_estimate_min"))
    print("Prediction method:",
          leg.get("duration_estimate_method"))
    print("Prediction status:",
          leg.get("duration_estimate_status"))

print("\nOriginal timetable duration remains authoritative.")
