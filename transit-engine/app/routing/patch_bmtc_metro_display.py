from pathlib import Path
import shutil

path = Path("app/routing/recommendation_engine.py")
source = path.read_text(encoding="utf-8")

old_emissions = '''        if emissions and emissions.get("status") == "success":
            if option["mode"] == "BMTC Bus":
                print("BMTC emissions scenarios:")
                for name, scenario in emissions["scenarios"].items():
                    print(
                        " ", name, ":",
                        scenario["emissions_kg_co2e"], "kg CO2e"
                    )
            else:
                print(
                    "Estimated emissions:",
                    emissions["emissions_kg_co2e"],
                    "kg CO2e/passenger"
                )
'''

new_emissions = '''        if emissions:
            if option["mode"] == "BMTC Bus":
                print("BMTC emissions scenarios:")
                for name, scenario in emissions.get("scenarios", {}).items():
                    print(
                        " ", name, ":",
                        scenario.get("emissions_kg_co2e"),
                        "kg CO2e"
                    )

            elif emissions.get("combined_scenarios"):
                print("BMTC + Metro combined emissions scenarios:")
                for name, scenario in emissions["combined_scenarios"].items():
                    print(
                        " ", name, ":",
                        scenario.get("total_emissions_kg_co2e"),
                        "kg CO2e"
                    )

            elif emissions.get("emissions_kg_co2e") is not None:
                print(
                    "Estimated emissions:",
                    emissions["emissions_kg_co2e"],
                    "kg CO2e/passenger"
                )
'''

if source.count(old_emissions) != 1:
    raise SystemExit(
        "Could not locate the emissions display block exactly. "
        "No changes made."
    )

source = source.replace(old_emissions, new_emissions, 1)

old_fare = '''            elif option["mode"] == "BMTC Bus":
                for leg in fare["legs"]:
                    print(
                        "Route", leg.get("route"),
                        "fare: Rs.", leg.get("fare_inr")
                    )
                print("Total BMTC fare: Rs.", fare["total_fare_inr"])
'''

new_fare = '''            elif option["mode"] == "BMTC Bus":
                for leg in fare["legs"]:
                    print(
                        "Route", leg.get("route"),
                        "fare: Rs.", leg.get("fare_inr")
                    )
                print("Total BMTC fare: Rs.", fare["total_fare_inr"])

            elif option["mode"] == "BMTC + Metro":
                bmtc_fare = fare.get("bmtc", {})
                metro_fare = fare.get("metro", {})

                print(
                    "BMTC fare: Rs.",
                    bmtc_fare.get("total_fare_inr")
                )
                print(
                    "Metro token fare: Rs.",
                    metro_fare.get("token_fare_inr")
                )
                print(
                    "Metro smart card / QR fare: Rs.",
                    metro_fare.get("smart_card_qr_fare_inr")
                )
                print(
                    "Combined token fare: Rs.",
                    fare.get("total_token_fare_inr")
                )
                print(
                    "Combined smart card / QR fare: Rs.",
                    fare.get("total_smart_card_qr_fare_inr")
                )
'''

if source.count(old_fare) != 1:
    raise SystemExit(
        "Could not locate the fare display block exactly. "
        "No changes made."
    )

source = source.replace(old_fare, new_fare, 1)

backup = path.with_name(
    "recommendation_engine.py.before_bmtc_metro_display.bak"
)
shutil.copy2(path, backup)

path.write_text(source, encoding="utf-8")

print("BMTC + Metro display patch applied.")
print("Backup:", backup)
