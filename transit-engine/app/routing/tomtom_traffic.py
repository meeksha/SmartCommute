import json
import os
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


def load_api_key():
    env_path = Path(".env")

    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()

            if line.startswith("TOMTOM_API_KEY="):
                value = line.split("=", 1)[1].strip()
                value = value.strip('"').strip("'")
                if value and value != "your_api_key_here":
                    return value

    return os.getenv("TOMTOM_API_KEY")




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

def calculate_road_route(origin, destination, travel_mode="car"):
    """
    origin and destination must be (latitude, longitude).
    Supported modes: car, taxi.
    """

    api_key = load_api_key()

    if not api_key:
        raise RuntimeError(
            "TomTom API key not found. Configure TOMTOM_API_KEY in .env."
        )

    if travel_mode == "motorcycle":
        return calculate_motorcycle_route(origin, destination)

    if travel_mode not in ("car", "taxi"):
        raise ValueError(
            "Supported modes: car, taxi, motorcycle."
        )

    url = (
        "https://api.tomtom.com/maps/orbis/routing/routes/calculate"
        "?apiVersion=3"
    )

    payload = {
        "routePlanningLocations": {
            "origin": {
                "type": "Point",
                "coordinates": [origin[1], origin[0]]
            },
            "destination": {
                "type": "Point",
                "coordinates": [destination[1], destination[0]]
            }
        },
        "traffic": "live",
        "routeType": "fast",
        "travelMode": travel_mode
    }

    headers = {
        "Content-Type": "application/json",
        "TomTom-Api-Version": "3",
        "TomTom-Api-Key": api_key,
        "Attributes": "routes"
    }

    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST"
    )

    try:
        with urlopen(request, timeout=30) as response:
            result = json.loads(response.read().decode("utf-8"))

    except HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"TomTom HTTP error {exc.code}: {error_body}"
        ) from exc

    except URLError as exc:
        raise RuntimeError(f"Network error: {exc.reason}") from exc

    routes = result.get("routes", [])

    if not routes:
        raise RuntimeError("TomTom returned no routes.")

    summary = routes[0].get("summary", {})

    duration = summary.get("travelDurationInSeconds")
    distance = summary.get("lengthInMeters")
    delay = summary.get("trafficDelayDurationInSeconds")

    if duration is None or distance is None:
        raise RuntimeError("TomTom response is missing route summary data.")

    delay = delay or 0

    return {
        "distance_km": round(distance / 1000, 2),
        "traffic_duration_min": round(duration / 60, 1),
        "traffic_delay_min": round(delay / 60, 1),
        "estimated_no_delay_min": round(max(0, duration - delay) / 60, 1),
        "travel_mode": travel_mode,
        "traffic_source": "TomTom live traffic",
        "is_live": True
    }


if __name__ == "__main__":
    # Chamarajapet -> Orion Mall, Bengaluru
    origin = (12.9585, 77.5635)
    destination = (13.0105, 77.5540)

    try:
        result = calculate_road_route(origin, destination)

        print("\nTOMTOM TRAFFIC ROUTE")
        print("===================")

        for key, value in result.items():
            print(f"{key}: {value}")

    except Exception as exc:
        print("\nTOMTOM TEST FAILED")
        print(exc)
