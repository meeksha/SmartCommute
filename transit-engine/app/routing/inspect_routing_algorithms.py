import inspect

from app.routing.bmtc_latest_planner import (
    plan_bmtc_latest_from_gps,
    active_bmtc_services,
    build_legs,
)
from app.routing.metro_planner import (
    plan_metro,
    load_metro_data,
)

functions = [
    plan_bmtc_latest_from_gps,
    active_bmtc_services,
    build_legs,
    plan_metro,
]

for function in functions:
    print("\n" + "=" * 80)
    print("FUNCTION:", function.__name__)
    print("=" * 80)
    print(inspect.getsource(function))
