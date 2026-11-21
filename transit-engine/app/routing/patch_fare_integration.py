from pathlib import Path
import shutil

path = Path("app/routing/recommendation_engine.py")
source = path.read_text(encoding="utf-8")

import_anchor = "from app.routing.tomtom_traffic import calculate_road_route\n"

import_replacement = import_anchor + '''from app.routing.namma_yatri_fares import (
    estimate_auto_fare,
    estimate_cab_fare
)
'''

if "from app.routing.namma_yatri_fares import" not in source:
    if source.count(import_anchor) != 1:
        raise SystemExit("Import insertion point not found. No changes made.")
    source = source.replace(import_anchor, import_replacement, 1)

anchor = '''            recommendations.append({
                "mode": label,
                "duration_minutes": road["traffic_duration_min"],
'''

replacement = '''            fare_estimates = None

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

            recommendations.append({
                "mode": label,
                "duration_minutes": road["traffic_duration_min"],
'''

if source.count(anchor) != 1:
    raise SystemExit("Road recommendation insertion point not found. No changes made.")

source = source.replace(anchor, replacement, 1)

anchor2 = '''                "emissions": road_emissions,
                "data_type": "TomTom live-traffic routing estimate",
'''

replacement2 = '''                "emissions": road_emissions,
                "fare_estimates": fare_estimates,
                "data_type": "TomTom live-traffic routing estimate",
'''

if source.count(anchor2) != 1:
    raise SystemExit("Fare field insertion point not found. No changes made.")

source = source.replace(anchor2, replacement2, 1)

backup = path.with_name(
    "recommendation_engine.py.before_fare_integration.bak"
)
shutil.copy2(path, backup)
path.write_text(source, encoding="utf-8")

print("Fare integration patch applied.")
print("Backup:", backup)
