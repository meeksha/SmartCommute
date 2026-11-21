from app.routing.bmtc_planner import plan_bmtc

result = plan_bmtc(
    origin="Income Tax Layout Cross 1",
    destination="RMC Yard (Yashawanthapura New Railway Station)",
    travel_date="2024-11-07",
    departure_time="08:00"
)

print("\nBMTC JOURNEY TEST")
print("=================")

for key, value in result.items():
    if key != "legs":
        print(f"\n{key}: {value}")

for index, leg in enumerate(result.get("legs", []), start=1):
    print(f"\nBus Leg {index}")
    print("Route:", leg["route_short_name"])
    print("Trip:", leg["trip_id"])
    print(
        leg["from_stop_name"], leg["departure_time"],
        "->", leg["to_stop_name"], leg["arrival_time"]
    )

    if "transfer_wait_minutes" in leg:
        print("Transfer at:", leg["transfer_at"])
        print("Waiting minutes:", leg["transfer_wait_minutes"])
