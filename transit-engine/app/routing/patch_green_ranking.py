from pathlib import Path
import shutil

path = Path("app/routing/bmtc_metro_planner.py")
source = path.read_text(encoding="utf-8")

old = '''    journeys.sort(
        key=lambda item: item["total_estimated_duration_minutes"]
    )
'''

new = '''    # Rank by conservative estimated emissions first.
    # BMTC vehicle fuel type is unknown, so use the highest available
    # emissions scenario for each journey. Duration breaks ties.
    for journey in journeys:
        scenarios = (
            journey.get("emissions", {})
            .get("combined_scenarios", {})
        )

        scenario_totals = [
            float(scenario["total_emissions_kg_co2e"])
            for scenario in scenarios.values()
            if isinstance(scenario, dict)
            and scenario.get("total_emissions_kg_co2e") is not None
        ]

        journey["emissions"]["ranking_emissions_kg_co2e"] = (
            round(max(scenario_totals), 4)
            if scenario_totals
            else None
        )

    journeys.sort(
        key=lambda item: (
            item["emissions"]["ranking_emissions_kg_co2e"]
            if item["emissions"]["ranking_emissions_kg_co2e"] is not None
            else float("inf"),
            item["total_estimated_duration_minutes"],
        )
    )
'''

if source.count(old) != 1:
    raise SystemExit("Patch stopped: expected exactly one matching sort block.")

backup = path.with_suffix(".py.before_green_ranking.bak")
shutil.copy2(path, backup)

path.write_text(source.replace(old, new, 1), encoding="utf-8")

print("Greenest-first ranking patch applied.")
print("Backup saved to:", backup)
