from pathlib import Path

path = Path("app/routing/recommendation_engine.py")
source = path.read_text(encoding="utf-8")

anchor = "from app.routing.planner import plan_journey"

new_imports = """from app.routing.journey_schema import build_journey
from app.routing.journey_adapters import (
    adapt_walking_metro,
    adapt_bmtc_journeys,
    adapt_bmtc_metro_journeys,
)
"""

if "from app.routing.journey_schema import build_journey" in source:
    print("Schema imports already exist. No changes made.")
else:
    if anchor not in source:
        raise RuntimeError("Expected import anchor not found.")

    source = source.replace(anchor, new_imports + "\n" + anchor, 1)
    path.write_text(source, encoding="utf-8")
    print("Schema imports added successfully.")
