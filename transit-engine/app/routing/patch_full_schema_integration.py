from pathlib import Path
import shutil

path = Path("app/routing/recommendation_engine.py")
source = path.read_text(encoding="utf-8")

# Verify required imports exist before changing anything.
required_imports = [
    "from app.routing.journey_schema import build_journey",
    "adapt_walking_metro",
    "adapt_bmtc_journeys",
    "adapt_bmtc_metro_journeys",
]

for item in required_imports:
    if item not in source:
        raise RuntimeError(f"Missing required import: {item}")

# 2. BMTC
start = source.index("    # 2. BMTC")
end = source.index("    # 3. BMTC + Metro", start)

bmtc_block = '''    # 2. BMTC - include best journey and alternatives
    try:
        bmtc = plan_bmtc_latest_from_gps(
            origin_lat,
            origin_lon,
            destination_lat,
            destination_lon,
            travel_date,
            departure_time
        )

        if bmtc.get("status") == "success":
            journeys = adapt_bmtc_journeys(bmtc)

            for journey in journeys:
                candidate = journey["raw_details"]
                bmtc_legs = candidate.get(
                    "bmtc_journey", {}
                ).get("legs", [])

                bmtc_fare = calculate_bmtc_journey_fare(
                    bmtc_legs
                )

                bmtc_distance = calculate_bmtc_journey_distance(
                    bmtc_legs
                )

                bmtc_emissions = (
                    calculate_bmtc_emission_scenarios(
                        bmtc_distance["distance_km"]
                    )
                    if bmtc_distance.get("status") == "success"
                    else bmtc_distance
                )

                journey["fare"] = bmtc_fare
                journey["emissions"] = bmtc_emissions

                if bmtc_distance.get("status") == "success":
                    journey["distance_km"] = bmtc_distance["distance_km"]

                recommendations.append({
                    "mode": "BMTC Bus",
                    "duration_minutes": journey["duration_minutes"],
                    "distance_walking_m": journey["walking_distance_m"],
                    "bus_distance_km": bmtc_distance.get("distance_km"),
                    "fare": bmtc_fare,
                    "emissions": bmtc_emissions,
                    "data_type": "2026-2027 BMTC scheduled timetable",
                    "journey": journey,
                    "details": candidate
                })

            if not journeys:
                errors.append({
                    "mode": "BMTC Bus",
                    "message": "Planner succeeded but produced no adapted journeys."
                })

        else:
            errors.append({
                "mode": "BMTC Bus",
                "message": bmtc.get("message", "Route unavailable")
            })

    except Exception as exc:
        errors.append({
            "mode": "BMTC Bus",
            "message": str(exc)
        })

'''

source = source[:start] + bmtc_block + source[end:]

# 3. BMTC + Metro
start = source.index("    # 3. BMTC + Metro")
end = source.index("    # 4. TomTom road routing", start)

combined_block = '''    # 3. BMTC + Metro - include all alternatives
    try:
        combined = plan_bmtc_then_metro(
            origin_lat,
            origin_lon,
            destination_lat,
            destination_lon,
            travel_date,
            departure_time
        )

        if combined.get("status") == "success":
            journeys = adapt_bmtc_metro_journeys(combined)

            for journey in journeys:
                candidate = journey["raw_details"]

                bmtc_fare = candidate.get(
                    "fare", {}
                ).get("bmtc", {})

                metro_fare = candidate.get(
                    "fare", {}
                ).get("metro", {})

                bmtc_total = bmtc_fare.get("total_fare_inr")
                metro_token = metro_fare.get("token_fare_inr")
                metro_qr = metro_fare.get("smart_card_qr_fare_inr")

                total_token = (
                    round(bmtc_total + metro_token, 2)
                    if bmtc_total is not None and metro_token is not None
                    else None
                )

                total_qr = (
                    round(bmtc_total + metro_qr, 2)
                    if bmtc_total is not None and metro_qr is not None
                    else None
                )

                combined_fare = {
                    "status": "success",
                    "bmtc": bmtc_fare,
                    "metro": metro_fare,
                    "total_token_fare_inr": total_token,
                    "total_smart_card_qr_fare_inr": total_qr,
                    "is_estimate": True
                }

                journey["fare"] = combined_fare

                recommendations.append({
                    "mode": "BMTC + Metro",
                    "duration_minutes": journey["duration_minutes"],
                    "distance_walking_m": journey["walking_distance_m"],
                    "fare": combined_fare,
                    "emissions": journey["emissions"],
                    "data_type": (
                        "2026-2027 BMTC scheduled timetable + "
                        "scheduled Metro GTFS"
                    ),
                    "journey": journey,
                    "details": candidate
                })

            if not journeys:
                errors.append({
                    "mode": "BMTC + Metro",
                    "message": "Planner succeeded but produced no adapted journeys."
                })

        else:
            errors.append({
                "mode": "BMTC + Metro",
                "message": combined.get("message", "Combined route unavailable")
            })

    except Exception as exc:
        errors.append({
            "mode": "BMTC + Metro",
            "message": str(exc)
        })

'''

source = source[:start] + combined_block + source[end:]

# 4. Road journeys
start = source.index("    # 4. TomTom road routing")
end = source.index("    # Rank by conservative emissions estimate first.", start)

road_block = '''    # 4. TomTom road routing
    for mode, label in [
        ("car", "Private Car"),
        ("taxi", "Taxi / Cab (vehicle class unverified)"),
        ("motorcycle", "Private Two-Wheeler")
    ]:
        try:
            road = calculate_road_route(
                (origin_lat, origin_lon),
                (destination_lat, destination_lon),
                travel_mode=mode
            )

            vehicle_type = {
                "car": "private_car_petrol",
                "taxi": "ride_hailing_diesel",
                "motorcycle": "private_motorcycle_petrol"
            }[mode]

            road_emissions = calculate_emissions(
                road["distance_km"],
                vehicle_type
            )

            operating_cost = None

            if mode == "motorcycle":
                operating_cost = calculate_two_wheeler_fuel_cost(
                    road["distance_km"]
                )

            fare_estimates = None

            if mode == "taxi":
                route_distance = road["distance_km"]

                fare_estimates = {
                    "distance_basis_km": route_distance,
                    "distance_source": (
                        "TomTom taxi road-route distance; "
                        "used as a proxy for Auto and Cab"
                    ),
                    "auto": estimate_auto_fare(route_distance),
                    "cab": {
                        category: estimate_cab_fare(
                            route_distance,
                            category
                        )
                        for category in [
                            "up_to_10_lakh",
                            "10_to_15_lakh",
                            "above_15_lakh"
                        ]
                    },
                    "limitations": [
                        "Estimates are distance-based, not live booking quotes.",
                        "Auto route distance is approximated using the taxi route.",
                        "Cab estimates use Karnataka notified fare categories, not verified Namma Yatri cab prices.",
                        "Waiting, pickup, toll and other applicable charges may change the final fare.",
                        "Vehicle cost category does not indicate AC or non-AC."
                    ]
                }

            data_type = (
                "TomTom Routing API v1 motorcycle route"
                if mode == "motorcycle"
                else "TomTom live-traffic routing estimate"
            )

            road_journey = build_journey(
                mode=label,
                duration_minutes=road["traffic_duration_min"],
                legs=[{
                    "type": mode,
                    "distance_km": road["distance_km"],
                    "details": road
                }],
                distance_km=road["distance_km"],
                emissions=road_emissions,
                transfers=0,
                data_sources=[data_type],
                limitations=(
                    [
                        "Motorcycle restriction data may be incomplete in some areas."
                    ]
                    if mode == "motorcycle" else []
                ),
                raw_details=road
            )

            recommendations.append({
                "mode": label,
                "duration_minutes": road["traffic_duration_min"],
                "distance_km": road["distance_km"],
                "traffic_delay_minutes": road["traffic_delay_min"],
                "emissions": road_emissions,
                "operating_cost": operating_cost,
                "fare_estimates": fare_estimates,
                "data_type": data_type,
                "journey": road_journey,
                "details": road
            })

        except Exception as exc:
            errors.append({
                "mode": label,
                "message": str(exc)
            })

'''

source = source[:start] + road_block + source[end:]

# Ensure all three road and transit sections exist before writing.
for marker in [
    "# 1. Walking + Metro",
    "# 2. BMTC - include best journey and alternatives",
    "# 3. BMTC + Metro - include all alternatives",
    "# 4. TomTom road routing",
    "# Rank by conservative emissions estimate first.",
]:
    if marker not in source:
        raise RuntimeError(f"Patch verification failed: {marker}")

backup = path.with_name(
    "recommendation_engine.py.before_full_schema_integration.bak"
)

if backup.exists():
    raise RuntimeError(
        f"Backup already exists; refusing to overwrite: {backup}"
    )

shutil.copy2(path, backup)
path.write_text(source, encoding="utf-8")

print("Full schema integration patch applied.")
print("Backup created:", backup)
