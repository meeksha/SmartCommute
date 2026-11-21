"""Safely wire optional fare data from three_mode_config into the adapter."""
from pathlib import Path
import shutil

path = Path("app/routing/recommendation_engine.py")
if not path.exists():
    raise SystemExit("Run this script from the transit-engine project root; recommendation_engine.py not found.")
text = path.read_text(encoding="utf-8")
old = "adapted = adapt_bmtc_metro_bmtc(three_mode)"
new = "adapted = adapt_bmtc_metro_bmtc(three_mode, fare_data=three_mode_config.get(\"fare_data\"))"
if new in text:
    print("Fare data is already passed to the three-mode adapter; no changes made.")
elif old in text:
    backup = path.with_suffix(".py.before_fare_ranking.bak")
    if not backup.exists():
        shutil.copy2(path, backup)
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    print(f"Updated three-mode fare-data handoff. Backup: {backup}")
else:
    raise SystemExit(
        "Could not find the expected adapter call. No file was changed. "
        "Search recommendation_engine.py for adapt_bmtc_metro_bmtc and update that call manually."
    )
