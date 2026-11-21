from pathlib import Path
import shutil

path = Path("app/routing/recommendation_engine.py")
source = path.read_text(encoding="utf-8")

# Add the calculator import.
import_anchor = "from app.routing.namma_yatri_fares import ("

if "from app.routing.two_wheeler_cost import" not in source:
    source = source.replace(
        import_anchor,
        "from app.routing.two_wheeler_cost import calculate_two_wheeler_fuel_cost\n"
        + import_anchor,
        1
    )

# Calculate operating cost only for private motorcycles.
anchor = '''            road_emissions = calculate_emissions(
                road["distance_km"],
                vehicle_type
            )

            fare_estimates = None
'''

replacement = '''            road_emissions = calculate_emissions(
                road["distance_km"],
                vehicle_type
            )

            operating_cost = None

            if mode == "motorcycle":
                operating_cost = calculate_two_wheeler_fuel_cost(
                    road["distance_km"]
                )

            fare_estimates = None
'''

if source.count(anchor) != 1:
    raise SystemExit("Operating-cost insertion point not found. No changes made.")

source = source.replace(anchor, replacement, 1)

# Include operating cost in the result.
anchor = '''                "emissions": road_emissions,
                "fare_estimates": fare_estimates,
'''

replacement = '''                "emissions": road_emissions,
                "operating_cost": operating_cost,
                "fare_estimates": fare_estimates,
'''

if source.count(anchor) != 1:
    raise SystemExit("Recommendation output insertion point not found.")

source = source.replace(anchor, replacement, 1)

# Display fuel information in terminal output.
anchor = '''        fare_estimates = option.get("fare_estimates")

        if fare_estimates:
'''

replacement = '''        operating_cost = option.get("operating_cost")

        if operating_cost:
            print("Estimated fuel consumed:",
                  operating_cost["fuel_consumed_litres"], "litres")
            print("Estimated petrol cost: Rs.",
                  operating_cost["fuel_cost_inr"])
            print("Assumed mileage:",
                  operating_cost["assumed_mileage_km_per_litre"], "km/L")
            print("Petrol price:",
                  operating_cost["petrol_price_inr_per_litre"], "Rs./litre")

        fare_estimates = option.get("fare_estimates")

        if fare_estimates:
'''

if source.count(anchor) != 1:
    raise SystemExit("Terminal display insertion point not found.")

source = source.replace(anchor, replacement, 1)

backup = path.with_name(
    "recommendation_engine.py.before_two_wheeler_cost.bak"
)
shutil.copy2(path, backup)

path.write_text(source, encoding="utf-8")

print("Two-wheeler fuel-cost integration applied.")
print("Backup:", backup)
