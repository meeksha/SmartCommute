from pathlib import Path
import shutil

path = Path("app/routing/recommendation_engine.py")
source = path.read_text(encoding="utf-8")

# 1. Add the combined planner import.
import_line = "from app.routing.bmtc_latest_planner import plan_bmtc_latest_from_gps\n"
new_import = import_line + (
    "from app.routing.bmtc_metro_planner import plan_bmtc_then_metro\n"
)

if source.count(import_line) != 1:
    raise SystemExit("Could not safely locate BMTC planner import.")

source = source.replace(import_line, new_import, 1)

# 2. Add BMTC + Metro recommendation before road routing.
marker = "    # 3. TomTom road routing\n"

combined_block = '''    # 3. BMTC + Metro
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
            best = combined["best_journey"]
            bmtc_fare = best.get("fare", {}).get("bmtc", {})
            metro_fare = best.get("fare", {}).get("metro", {})

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

            recommendations.append({
                "mode": "BMTC + Metro",
                "duration_minutes": best[
                    "total_estimated_duration_minutes"
                ],
                "distance_walking_m": best[
                    "total_estimated_walking_metres"
                ],
                "fare": combined_fare,
                "emissions": best.get("emissions", {}),
                "data_type": (
                    "2026-2027 BMTC scheduled timetable + "
                    "scheduled Metro GTFS"
                ),
                "details": combined
            })
        else:
            errors.append({
                "mode": "BMTC + Metro",
                "message": combined.get(
                    "message", "Combined route unavailable"
                )
            })

    except Exception as exc:
        errors.append({
            "mode": "BMTC + Metro",
            "message": str(exc)
        })

    # 4. TomTom road routing
'''

if source.count(marker) != 1:
    raise SystemExit("Could not safely locate road-routing section.")

source = source.replace(marker, combined_block, 1)

# 3. Make the taxi label explicit about its limitations.
source = source.replace(
    '("taxi", "Taxi / Auto-like road estimate")',
    '("taxi", "Taxi / Cab (vehicle class unverified)")',
    1
)

# 4. Replace duration-first ranking with conservative emissions-first ranking.
old_sort = '''    recommendations.sort(
        key=lambda item: item["duration_minutes"]
    )
'''

new_sort = '''    # Rank by conservative emissions estimate first.
    # For BMTC options, fuel type is unknown, so use the highest
    # available fuel-scenario estimate.
    def get_conservative_emissions(item):
        emissions = item.get("emissions") or {}

        # BMTC-only scenarios.
        scenarios = emissions.get("scenarios", {})
        if scenarios:
            values = []
            for scenario in scenarios.values():
                if isinstance(scenario, dict):
                    value = scenario.get("emissions_kg_co2e")
                else:
                    value = scenario

                if value is not None:
                    values.append(float(value))

            if values:
                return max(values)

        # BMTC + Metro combined scenarios.
        combined_scenarios = emissions.get(
            "combined_scenarios", {}
        )
        if combined_scenarios:
            values = [
                float(scenario["total_emissions_kg_co2e"])
                for scenario in combined_scenarios.values()
                if isinstance(scenario, dict)
                and scenario.get("total_emissions_kg_co2e") is not None
            ]

            if values:
                return max(values)

        # Single-mode emissions, such as Metro or private car.
        value = emissions.get("emissions_kg_co2e")
        if value is not None:
            return float(value)

        return None

    for item in recommendations:
        item["ranking_emissions_kg_co2e"] = (
            get_conservative_emissions(item)
        )

    recommendations.sort(
        key=lambda item: (
            item["ranking_emissions_kg_co2e"]
            if item["ranking_emissions_kg_co2e"] is not None
            else float("inf"),
            item["duration_minutes"]
        )
    )
'''

if source.count(old_sort) != 1:
    raise SystemExit("Could not safely locate existing ranking block.")

source = source.replace(old_sort, new_sort, 1)

# 5. Update the limitation notes.
source = source.replace(
    '"Taxi routing is not a verified auto-rickshaw fare or route.",',
    '"Taxi road routing does not verify the vehicle class or provide a live fare.",',
    1
)

source = source.replace(
    '"Carpool and company shuttle matching are not integrated yet."',
    '"Auto-specific fares, two-wheeler routing, carpool and company shuttle matching are not integrated yet."',
    1
)

# Save backup and write patched file.
backup = path.with_suffix(".py.before_unified_ranking.bak")
shutil.copy2(path, backup)

path.write_text(source, encoding="utf-8")

print("Recommendation engine updated successfully.")
print("Backup saved to:", backup)
print("Added: BMTC + Metro")
print("Changed: emissions-first ranking")
print("Clarified: taxi vehicle-class limitation")
