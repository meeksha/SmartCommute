from app.routing.bmtc_gps_planner import plan_bmtc_from_gps

result = plan_bmtc_from_gps(
    origin_lat=12.9585,
    origin_lon=77.5635,
    destination_lat=13.0105,
    destination_lon=77.5540,
    travel_date="2024-11-07",
    departure_time="08:00",
    search_radius_m=1000,
    candidates_per_side=5
)

print("\nGPS-BASED BMTC JOURNEY")
print("======================")
print("Status:", result["status"])

if result["status"] == "success":
    best = result["best_journey"]

    print("Journeys compared:", result["journeys_compared"])
    print("Estimated total duration:",
          best["total_estimated_duration_minutes"], "minutes")

    print("\nBoarding stop:", best["origin_access"]["stop_name"])
    print("Access walking distance:",
          best["origin_access"]["distance_m"], "m")

    print("\nDestination stop:",
          best["destination_egress"]["stop_name"])
    print("Egress walking distance:",
          best["destination_egress"]["distance_m"], "m")

    print("\nBMTC arrival:",
          best["bmtc_journey"]["arrival"])
    print("Bus legs:",
          best["bmtc_journey"]["number_of_bus_legs"])

    for leg in best["bmtc_journey"]["legs"]:
        print(
            leg["route_short_name"],
            "|",
            leg["from_stop_name"],
            "->",
            leg["to_stop_name"]
        )
else:
    print(result.get("message"))
    print(result.get("diagnostics"))
