from app.routing.planner import plan_journey
from app.routing.bmtc_latest_planner import plan_bmtc_latest_from_gps
from app.routing.planner import get_bmtc_interchange
import inspect

ORIGIN = (12.9585, 77.5635)
DESTINATION = (13.0105, 77.5540)
DATE = "2026-11-18"
TIME = "08:00"


def show_structure(value, depth=0, max_depth=4):
    indent = "  " * depth

    if isinstance(value, dict):
        for key, item in value.items():
            if isinstance(item, (dict, list)):
                print(f"{indent}{key}:")
                if depth < max_depth:
                    show_structure(item, depth + 1, max_depth)
                else:
                    print(f"{indent}  ...")
            else:
                print(f"{indent}{key}: {item}")

    elif isinstance(value, list):
        print(f"{indent}Number of items: {len(value)}")
        if value:
            print(f"{indent}First item:")
            if depth < max_depth:
                show_structure(value[0], depth + 1, max_depth)
            else:
                print(f"{indent}  {value[0]}")


print("\n===== WALKING + METRO RESULT =====")
metro_result = plan_journey(
    *ORIGIN, *DESTINATION, DATE, TIME
)
show_structure(metro_result)

print("\n===== BMTC RESULT =====")
bmtc_result = plan_bmtc_latest_from_gps(
    *ORIGIN, *DESTINATION, DATE, TIME
)
show_structure(bmtc_result)

print("\n===== BMTC INTERCHANGE FUNCTION =====")
print(inspect.getsource(get_bmtc_interchange))
