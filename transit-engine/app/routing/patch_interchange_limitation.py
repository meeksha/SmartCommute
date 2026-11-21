from pathlib import Path
import shutil

path = Path("app/routing/bmtc_metro_planner.py")
source = path.read_text(encoding="utf-8")

old = "Only modelled OSM interchange connections are considered."
new = (
    "Current-feed BMTC stops are matched to Metro entrances using "
    "approximate walking distances (straight-line distance multiplied "
    "by 1.3); these are not pedestrian-network routes."
)

if source.count(old) != 1:
    raise SystemExit("Expected limitation text not found exactly once.")

backup = path.with_suffix(".py.before_limitations_fix.bak")
shutil.copy2(path, backup)

source = source.replace(old, new, 1)
path.write_text(source, encoding="utf-8")

print("Updated interchange limitation.")
print("Backup:", backup)
