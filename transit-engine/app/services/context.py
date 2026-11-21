"""Live context: weather, time-of-day traffic, and road routing with fallback.

Live sources are used when reachable (Open-Meteo for weather, TomTom for
traffic-aware road routes). When a live source is unavailable the module falls
back to documented models and labels the result ``is_live = False`` so the UI
can show where every number came from.
"""
from __future__ import annotations

import json
import math
import threading
import time
from datetime import datetime
from urllib.parse import urlencode
from urllib.request import Request, urlopen

_CACHE: dict = {}
_LOCK = threading.Lock()


def _cached(key, ttl_s, fn):
    now = time.time()
    with _LOCK:
        hit = _CACHE.get(key)
        if hit and now - hit[0] < ttl_s:
            return hit[1]
    value = fn()
    with _LOCK:
        _CACHE[key] = (now, value)
    return value


def haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0088
    p1, p2 = math.radians(float(lat1)), math.radians(float(lat2))
    dp = p2 - p1
    dl = math.radians(float(lon2) - float(lon1))
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


# --------------------------------------------------------------------------
# Weather
# --------------------------------------------------------------------------
# Bengaluru climatology (approximate IMD normals): rainy days per month and
# mean daily temperature. Used only when live weather is unreachable.
_RAINY_DAYS = [0.2, 0.5, 0.6, 3.0, 7.0, 6.5, 9.0, 11.0, 10.0, 9.0, 4.5, 1.5]
_MEAN_TEMP_C = [21.5, 23.5, 26.0, 27.5, 27.0, 24.5, 23.5, 23.5, 23.5, 23.5, 22.0, 21.0]
_DAYS_IN_MONTH = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]

_WMO_RAIN_CODES = set(range(51, 68)) | set(range(80, 83)) | {95, 96, 99}


def _weather_fallback(when: datetime) -> dict:
    m = when.month - 1
    p = _RAINY_DAYS[m] / _DAYS_IN_MONTH[m]
    return {
        "is_live": False,
        "source": "Bengaluru monthly climatology (approx. IMD normals) - live weather unavailable",
        "temperature_c": _MEAN_TEMP_C[m],
        "precipitation_mm": None,
        "precipitation_probability": round(p, 2),
        "is_raining": False,
        "rain_expected": p >= 0.3,
        "condition": "climatology",
    }


def get_weather(lat: float, lon: float, when: datetime) -> dict:
    """Weather at the departure hour. Live via Open-Meteo (no key needed)."""
    key = ("wx", round(lat, 2), round(lon, 2), when.strftime("%Y-%m-%d %H"))

    def fetch():
        params = {
            "latitude": round(lat, 3), "longitude": round(lon, 3),
            "current": "temperature_2m,precipitation,weather_code",
            "hourly": "precipitation_probability,precipitation,temperature_2m,weather_code",
            "timezone": "Asia/Kolkata", "forecast_days": 3,
        }
        url = "https://api.open-meteo.com/v1/forecast?" + urlencode(params)
        try:
            with urlopen(Request(url, headers={"Accept": "application/json"}), timeout=6) as r:
                data = json.loads(r.read().decode("utf-8"))
        except Exception as exc:  # network blocked, timeout, etc.
            fb = _weather_fallback(when)
            fb["live_error"] = str(exc)[:160]
            return fb
        hourly = data.get("hourly", {})
        target = when.strftime("%Y-%m-%dT%H:00")
        times = hourly.get("time", [])
        if target in times:
            i = times.index(target)
            prob = (hourly.get("precipitation_probability") or [None])[i]
            mm = (hourly.get("precipitation") or [None])[i]
            temp = (hourly.get("temperature_2m") or [None])[i]
            code = (hourly.get("weather_code") or [None])[i]
        else:  # departure outside forecast window -> use current
            cur = data.get("current", {})
            prob, mm = None, cur.get("precipitation")
            temp, code = cur.get("temperature_2m"), cur.get("weather_code")
        raining = bool((mm or 0) >= 0.3 or (code in _WMO_RAIN_CODES))
        probability = (prob / 100.0) if prob is not None else (1.0 if raining else 0.0)
        return {
            "is_live": True,
            "source": "Open-Meteo forecast API",
            "temperature_c": temp,
            "precipitation_mm": mm,
            "precipitation_probability": round(probability, 2),
            "is_raining": raining,
            "rain_expected": raining or probability >= 0.5,
            "condition": "rain" if raining else ("rain likely" if probability >= 0.5 else "dry"),
            "weather_code": code,
        }

    return _cached(key, 900, fetch)


def weather_effects(weather: dict) -> dict:
    """How weather changes commuter behaviour and ride-hailing supply/demand.

    Rain lowers walking tolerance, slows road traffic and raises ride-hailing
    demand. Coefficients are transparent modelling assumptions.
    """
    wet = weather.get("rain_expected")
    hot = (weather.get("temperature_c") or 25) >= 34
    return {
        "walking_tolerance_factor": 0.6 if wet else (0.8 if hot else 1.0),
        "road_delay_factor": 1.15 if wet else 1.0,
        "ride_hailing_demand_factor": 1.25 if wet else 1.0,
        "ride_hailing_supply_factor": 0.85 if wet else 1.0,
        "note": ("Rain: walking tolerance -40 %, road time +15 %, ride-hailing demand +25 %, "
                 "driver supply -15 % (modelling assumptions)") if wet else
                ("Heat: walking tolerance -20 %" if hot else "No weather adjustment"),
    }


# --------------------------------------------------------------------------
# Time-of-day traffic model (fallback when live traffic is unavailable)
# --------------------------------------------------------------------------
# Travel-time multiplier over free flow for Bengaluru weekdays, by hour.
_WEEKDAY_CONGESTION = [
    1.05, 1.03, 1.02, 1.02, 1.05, 1.15, 1.35, 1.65, 1.90, 1.85, 1.60, 1.45,
    1.40, 1.40, 1.40, 1.50, 1.70, 1.90, 2.00, 1.90, 1.65, 1.40, 1.20, 1.10,
]
_WEEKEND_FACTOR = 0.80          # weekend excess congestion is ~20 % lower
FREE_FLOW_KMH = {"car": 32.0, "taxi": 32.0, "motorcycle": 36.0}
ROAD_CIRCUITY = 1.35            # road distance / straight-line, Indian metro cities


def traffic_profile(when: datetime) -> dict:
    base = _WEEKDAY_CONGESTION[when.hour]
    weekend = when.weekday() >= 5
    if weekend:
        base = 1 + (base - 1) * _WEEKEND_FACTOR
    if base >= 1.75:
        level = "heavy"
    elif base >= 1.4:
        level = "moderate"
    else:
        level = "light"
    return {
        "congestion_multiplier": round(base, 2),
        "level": level,
        "is_peak": base >= 1.6,
        "is_weekend": weekend,
        "source": "Modelled Bengaluru weekday time-of-day profile (used when live traffic is unavailable)",
    }


BENGALURU_CENTRE = (12.9716, 77.5946)
URBAN_RADIUS_KM = 18.0          # beyond this, roads are treated as intercity highway
HIGHWAY_FREE_FLOW_KMH = {"car": 60.0, "taxi": 60.0, "motorcycle": 55.0}   # model assumption (NH48/NH75)


def _urban_share(origin, destination, samples=21) -> float:
    """Share of the straight line that lies inside urban Bengaluru (congestion applies there)."""
    inside = 0
    for i in range(samples):
        f = i / (samples - 1)
        lat = origin[0] + (destination[0] - origin[0]) * f
        lon = origin[1] + (destination[1] - origin[1]) * f
        inside += haversine_km(lat, lon, *BENGALURU_CENTRE) <= URBAN_RADIUS_KM
    return inside / samples


def _osrm_route(origin, destination, mode):
    """Road distance and free-flow time from the public OSRM server (OpenStreetMap road network)."""
    import os
    if os.environ.get("OSRM_DISABLED") == "1":
        raise RuntimeError("OSRM disabled")
    profile = "driving"
    url = (f"https://router.project-osrm.org/route/v1/{profile}/"
           f"{origin[1]},{origin[0]};{destination[1]},{destination[0]}?overview=false")
    req = Request(url, headers={"User-Agent": "sustainable-commute-research/1.0"})
    with urlopen(req, timeout=4) as r:
        data = json.loads(r.read().decode("utf-8"))
    route = data["routes"][0]
    return route["distance"] / 1000.0, route["duration"] / 60.0


def _fallback_road_route(origin, destination, mode, when: datetime, weather_fx: dict) -> dict:
    straight = haversine_km(origin[0], origin[1], destination[0], destination[1])
    share = _urban_share(origin, destination)
    prof = traffic_profile(when)
    mult = prof["congestion_multiplier"]
    if mode == "motorcycle":            # two-wheelers filter through traffic
        mult = 1 + (mult - 1) * 0.7
    mult *= weather_fx.get("road_delay_factor", 1.0)
    source = None
    try:
        distance, osrm_min = _osrm_route(origin, destination, mode)
        # OSRM speeds come from OSM road classes (free flow); city streets in Bengaluru are far
        # slower than that, so inside the city we keep the calibrated urban free-flow speed.
        urban_km = distance * share
        free_min = urban_km / FREE_FLOW_KMH[mode] * 60 + osrm_min * (1 - share)
        source = "OpenStreetMap road network (OSRM) + time-of-day congestion profile"
    except Exception:
        urban_km = straight * share * ROAD_CIRCUITY
        rural_km = straight * (1 - share) * 1.2
        distance = max(0.5, urban_km + rural_km)
        free_min = urban_km / FREE_FLOW_KMH[mode] * 60 + rural_km / HIGHWAY_FREE_FLOW_KMH[mode] * 60
        source = ("Modelled: straight-line x 1.35 circuity in the city (x 1.2 on highways), "
                  "time-of-day congestion profile")
    urban_free = (distance * share) / FREE_FLOW_KMH[mode] * 60
    total = free_min + urban_free * (mult - 1)
    return {
        "distance_km": round(max(0.5, distance), 2),
        "traffic_duration_min": round(total, 1),
        "traffic_delay_min": round(total - free_min, 1),
        "estimated_no_delay_min": round(free_min, 1),
        "travel_mode": mode,
        "traffic_source": source,
        "is_live": False,
        "congestion_ratio": round(total / free_min, 2) if free_min else 1.0,
        "urban_share": round(share, 2),
    }


def road_route(origin, destination, mode: str, when: datetime, weather_fx: dict | None = None) -> dict:
    """TomTom live route when reachable, otherwise the modelled fallback."""
    weather_fx = weather_fx or {}
    bucket = int(time.time() // 600)  # 10-minute cache for live traffic
    key = ("road", mode, round(origin[0], 4), round(origin[1], 4),
           round(destination[0], 4), round(destination[1], 4), when.strftime("%Y-%m-%d %H"), bucket)

    def fetch():
        live_error = None
        # Live traffic describes *now*; only trust it for near-term departures.
        minutes_ahead = (when - datetime.now()).total_seconds() / 60
        if -30 <= minutes_ahead <= 90:
            try:
                from app.routing.tomtom_traffic import calculate_road_route
                r = calculate_road_route(tuple(origin), tuple(destination), travel_mode=mode)
                free = r.get("estimated_no_delay_min") or r["traffic_duration_min"]
                r["congestion_ratio"] = round(r["traffic_duration_min"] / free, 2) if free else 1.0
                if weather_fx.get("road_delay_factor", 1.0) > 1.0:
                    r["weather_note"] = "Live traffic already reflects current weather."
                return r
            except Exception as exc:
                live_error = str(exc)[:160]
        else:
            live_error = "Departure is outside the live-traffic window; using time-of-day model."
        fb = _fallback_road_route(origin, destination, mode, when, weather_fx)
        fb["live_error"] = live_error
        return fb

    return _cached(key, 600, fetch)
