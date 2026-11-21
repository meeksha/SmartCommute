import inspect

from app.routing.bmtc_latest_stop_matcher import find_nearby_bmtc_stops
from app.routing.planner import (
    nearest_reachable_station,
    load_walking_data,
    plan_journey,
)
import app.routing.bmtc_latest_planner as bp
import app.routing.planner as mp

functions = [
    find_nearby_bmtc_stops,
    nearest_reachable_station,
    load_walking_data,
    plan_journey,
]

for function in functions:
    print("\n" + "=" * 75)
    print("FUNCTION:", function.__name__)
    print("=" * 75)
    print(inspect.getsource(function))

print("\n===== BMTC CONSTANTS =====")
for name in dir(bp):
    if name.isupper():
        print(name, "=", getattr(bp, name))

print("\n===== PLANNER CONSTANTS AND PATHS =====")
for name in dir(mp):
    if name.isupper():
        value = getattr(mp, name)
        print(name, "=", value)
