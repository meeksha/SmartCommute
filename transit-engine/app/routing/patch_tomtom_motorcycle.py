from pathlib import Path
import shutil

path = Path("app/routing/tomtom_traffic.py")
source = path.read_text(encoding="utf-8")

helper = '''

def calculate_motorcycle_route(origin, destination):
    """Motorcycle routing using TomTom Routing API v1."""

    api_key = load_api_key()

    if not api_key:
        raise RuntimeError("TomTom API key not found.")

    locations = (
        f"{origin[0]},{origin[1]}:"
        f"{destination[0]},{destination[1]}"
    )

    from urllib.parse import urlencode

    params = {
        "key": api_key,
        "travelMode": "motorcycle",
        "traffic": "true",
        "routeType": "fastest",
        "computeTravelTimeFor": "all"
    }

    url = (
        "https://api.tomtom.com/routing/1/calculateRoute/"
        f"{locations}/json?{urlencode(params)}"
    )

    request = Request(
        url,
        headers={"Accept": "application/json"},
        method="GET"
    )

    try:
        with urlopen(request, timeout=30) as response:
            result = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"TomTom HTTP error {exc.code}: {body}"
        ) from exc
    except URLError as exc:
        raise RuntimeError(
            f"Network error: {exc.reason}"
        ) from exc

    routes = result.get("routes", [])

    if not routes:
        raise RuntimeError("No motorcycle route returned.")

    summary = routes[0].get("summary", {})

    duration = summary.get("travelTimeInSeconds")
    distance = summary.get("lengthInMeters")
    delay = summary.get("trafficDelayInSeconds", 0) or 0

    if duration is None or distance is None:
        raise RuntimeError("Missing motorcycle route summary.")

    return {
        "distance_km": round(distance / 1000, 2),
        "traffic_duration_min": round(duration / 60, 1),
        "traffic_delay_min": round(delay / 60, 1),
        "estimated_no_delay_min": round(
            max(0, duration - delay) / 60, 1
        ),
        "travel_mode": "motorcycle",
        "traffic_source": "TomTom Routing API v1",
        "routing_api_version": "v1",
        "is_live": True,
        "restriction_data_note": (
            "Motorcycle routing is beta; restriction data "
            "may be incomplete in some areas."
        )
    }

'''

anchor = 'def calculate_road_route(origin, destination, travel_mode="car"):\n'

if "def calculate_motorcycle_route(" not in source:
    if source.count(anchor) != 1:
        raise SystemExit("Could not find routing function. No changes made.")
    source = source.replace(anchor, helper + anchor, 1)

old = '''    if travel_mode not in ("car", "taxi"):
        raise ValueError("TomTom Orbis supports car or taxi in this module.")
'''

new = '''    if travel_mode == "motorcycle":
        return calculate_motorcycle_route(origin, destination)

    if travel_mode not in ("car", "taxi"):
        raise ValueError(
            "Supported modes: car, taxi, motorcycle."
        )
'''

if old in source:
    source = source.replace(old, new, 1)
elif "return calculate_motorcycle_route(origin, destination)" not in source:
    raise SystemExit("Could not find travel-mode validation. No changes made.")

backup = path.with_name("tomtom_traffic.py.before_motorcycle.bak")
if not backup.exists():
    shutil.copy2(path, backup)

path.write_text(source, encoding="utf-8")

print("Motorcycle routing patch applied.")
print("Backup:", backup)
