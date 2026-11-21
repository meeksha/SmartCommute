"""End-to-end commute recommendation: candidate generation -> features ->
filtering -> personalised multi-objective ranking -> explanation.

Output is a single, frontend-friendly schema (see ``Option`` in app/schemas.py).
Every number shown to the user is computed here once; the UI should render it
and never recompute it.
"""
from __future__ import annotations

import hashlib
import json
import math
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

from app.services import emissions as E
from app.services import preferences as P
from app.services.context import (get_weather, weather_effects, road_route, traffic_profile,
                                  haversine_km)
from app.services.costs import fuel_cost
from app.services.demand_pricing import market_state
from app.services.employees import pickup_detour_km
from app.services.booking import booking_links
from app.services.places import stop_point, stops_path, metro_line_info

from app.routing.planner import plan_journey
from app.routing.bmtc_latest_planner import plan_bmtc_latest_from_gps
from app.routing.bmtc_metro_planner import plan_bmtc_then_metro
from app.routing.journey_adapters import (adapt_walking_metro, adapt_bmtc_journeys,
                                          adapt_bmtc_metro_journeys)
from app.routing.bmtc_fares import calculate_bmtc_journey_fare
from app.routing.namma_yatri_fares import estimate_auto_fare, estimate_cab_fare
from app.services.carbon import calculate_bmtc_journey_distance

WALK_M_PER_MIN = 80
RIDE_HAIL_DEADHEAD = 1.30
AUTO_MAX_KM = 35.0
PLANNER_LOCK = threading.Lock()
_RESULT_CACHE: dict = {}

FAMILY_LABELS = {
    "metro": "Walk + Metro", "bus": "BMTC Bus", "bus_metro": "Bus + Metro",
    "carpool": "Carpool", "walk": "Walk", "auto": "Auto-rickshaw", "cab": "Cab",
    "two_wheeler": "Two-wheeler", "car": "Drive alone", "bicycle": "Cycle",
    "metro_combo": "Metro combination", "train": "Train",
}
# Frontend "usual transport" ids -> option families.
USUAL_MODE_FAMILIES = {"driving": {"car"}, "carpool": {"carpool"},
                       "transit": {"metro", "bus", "bus_metro", "metro_combo", "train"},
                       "twoWheeler": {"two_wheeler"}, "bicycling": {"bicycle"}, "walking": {"walk"}}
FAMILY_KEEP = {"metro": 2, "bus": 2, "bus_metro": 2, "carpool": 2, "walk": 1, "auto": 1,
               "cab": 1, "two_wheeler": 1, "car": 1, "bicycle": 1,
               "metro_combo": 3, "train": 3}
UNCERTAINTY = {"train": 0.15, "bicycle": 0.05, "metro_combo": 0.25, "metro": 0.10, "bus": 0.35, "bus_metro": 0.30, "walk": 0.0, "car": 0.15,
               "two_wheeler": 0.12, "carpool": 0.25}
DEFAULT_LIMITS = {"max_total_walking_m": 2500.0, "max_origin_access_m": 1200.0,
                  "max_destination_egress_m": 1800.0, "max_transfer_walk_m": 600.0}


# ---------------------------------------------------------------------------
# Leg normalisation
# ---------------------------------------------------------------------------
def _hhmm(t):
    if not t:
        return None
    parts = str(t).split(":")
    h = int(parts[0]) % 24
    return f"{h:02d}:{int(parts[1]):02d}"


def _transit_leg(leg, kind):
    is_bus = kind == "bus"
    stop_ids = leg.get("stop_ids") or [leg.get("from_stop"), leg.get("to_stop")]
    a = stop_point(leg.get("from_stop"), kind)
    b = stop_point(leg.get("to_stop"), kind)
    dep, arr = leg.get("departure"), leg.get("arrival")
    out = {
        "type": kind,
        "from": {"name": leg.get("from_stop_name") if is_bus else leg.get("from_station"),
                 "lat": a and a["lat"], "lon": a and a["lon"], "stop_id": leg.get("from_stop")},
        "to": {"name": leg.get("to_stop_name") if is_bus else leg.get("to_station"),
               "lat": b and b["lat"], "lon": b and b["lon"], "stop_id": leg.get("to_stop")},
        "departure_time": _hhmm(leg.get("departure_time")),
        "arrival_time": _hhmm(leg.get("arrival_time")),
        "duration_min": round((arr - dep) / 60, 1) if dep is not None and arr is not None else None,
        "stops_count": max(0, len(stop_ids) - 1),
        "path": stops_path(stop_ids, kind),
        "wait_before_min": leg.get("transfer_wait_minutes"),
    }
    if is_bus:
        out["route"] = leg.get("route_short_name")
        out["route_long_name"] = leg.get("route_long_name")
        out["label"] = f"Bus {leg.get('route_short_name')}"
        out["color"] = "#D9480F"
    else:
        info = metro_line_info().get(leg.get("route_id"), {})
        out["route"] = leg.get("route_id")
        out["label"] = info.get("name", f"{leg.get('route_id')} Line")
        out["color"] = info.get("color", "#6741D9")
        out["direction"] = leg.get("headsign")
    return out


def _normalise_legs(adapted, origin, destination):
    """Adapter legs -> UI legs with coordinates; walking legs anchored to neighbours."""
    raw = adapted["legs"]
    out = []
    for leg in raw:
        if leg["type"] == "bmtc_bus":
            out.append(_transit_leg(leg, "bus"))
        elif leg["type"] == "metro":
            out.append(_transit_leg(leg, "metro"))
        elif leg["type"] == "walking":
            out.append({"type": "walk", "segment": leg.get("segment"),
                        "from": {"name": leg.get("from")}, "to": {"name": leg.get("to")},
                        "distance_m": round(float(leg.get("distance_m") or 0), 0),
                        "duration_min": round(float(leg.get("duration_minutes") or 0), 1)})
    for i, leg in enumerate(out):
        if leg["type"] != "walk":
            continue
        prev = next((x for x in reversed(out[:i]) if x["type"] != "walk"), None)
        nxt = next((x for x in out[i + 1:] if x["type"] != "walk"), None)
        start = {"name": "Your location", "lat": origin[0], "lon": origin[1]} if prev is None else dict(prev["to"])
        end = {"name": "Destination", "lat": destination[0], "lon": destination[1]} if nxt is None else dict(nxt["from"])
        if leg["from"].get("name") and prev is not None:
            start["name"] = leg["from"]["name"]
        if leg["to"].get("name") and nxt is not None:
            end["name"] = leg["to"]["name"]
        leg["from"], leg["to"] = start, end
        leg["path"] = [[start.get("lat"), start.get("lon")], [end.get("lat"), end.get("lon")]] \
            if start.get("lat") is not None and end.get("lat") is not None else []
    return out


def _walk_metrics(legs):
    total = origin = dest = transfer = 0.0
    for leg in legs:
        if leg["type"] != "walk":
            continue
        d = float(leg.get("distance_m") or 0)
        total += d
        seg = leg.get("segment")
        if seg == "origin_access":
            origin += d
        elif seg == "destination_egress":
            dest += d
        else:
            transfer += d
    return {"total_m": round(total), "origin_access_m": round(origin),
            "destination_egress_m": round(dest), "transfer_walk_m": round(transfer)}


def _chain(legs):
    names = {"bicycle": "Cycle", "walk": "Walk", "bus": "Bus", "metro": "Metro", "car": "Car", "two_wheeler": "Two-wheeler",
             "auto": "Auto", "cab": "Cab", "carpool": "Carpool"}
    out = []
    for leg in legs:
        n = names.get(leg["type"], leg["type"])
        if leg["type"] in ("bus", "metro", "train") and leg.get("route"):
            n = leg.get("label")
        if not out or out[-1] != n:
            out.append(n)
    return out


# ---------------------------------------------------------------------------
# Candidate builders
# ---------------------------------------------------------------------------
def _option(family, legs, duration, cost, emissions, distance_km, transfers, sources,
            limitations, is_live, extra=None):
    o = {
        "id": uuid.uuid4().hex[:12],
        "family": family,
        "title": FAMILY_LABELS[family],
        "chain": _chain(legs),
        "duration_min": round(float(duration), 1),
        "distance_km": round(float(distance_km), 2) if distance_km is not None else None,
        "walking": _walk_metrics(legs),
        "transfers": int(transfers),
        "cost": cost,
        "emissions": emissions.to_dict(),
        "legs": legs,
        "data_sources": sources,
        "limitations": limitations,
        "is_live": bool(is_live),
    }
    o.update(extra or {})
    return o


def _transit_cost(amount, kind, low=None, high=None, detail=None):
    return {"amount_inr": None if amount is None else round(float(amount), 2),
            "low_inr": None if low is None else round(float(low), 2),
            "high_inr": None if high is None else round(float(high), 2),
            "kind": kind, "is_estimate": True, "detail": detail or {}}


def build_metro(res, origin, destination):
    out = []
    for j in adapt_walking_metro(res):
        raw = j["raw_details"]
        fare = raw.get("metro_fare") or {}
        km = fare.get("distance_km")
        if km is None:
            continue
        legs = _normalise_legs(j, origin, destination)
        em = E.combine([E.transit(km, "metro"), E.walking(0)])
        cost = _transit_cost(fare.get("smart_card_qr_fare_inr"), "fare",
                             fare.get("smart_card_qr_fare_inr"), fare.get("token_fare_inr"),
                             {"token_inr": fare.get("token_fare_inr"),
                              "smart_card_qr_inr": fare.get("smart_card_qr_fare_inr"),
                              "basis": fare.get("fare_basis")})
        out.append(_option("metro", legs, j["duration_minutes"], cost, em, km, j["transfers"] or 0,
                           ["BMRCL Metro GTFS (scheduled)", "OSM walking network", "Namma Metro fare chart"],
                           ["Scheduled timetable; no live train positions."], False,
                           {"transit_km": {"metro": km}}))
    return out


def build_bus(res, origin, destination):
    out = []
    for j in adapt_bmtc_journeys(res):
        raw = j["raw_details"]
        legs_raw = raw.get("bmtc_journey", {}).get("legs", [])
        dist = calculate_bmtc_journey_distance(legs_raw)
        if dist.get("status") != "success":
            continue
        km = dist["distance_km"]
        fare = calculate_bmtc_journey_fare(legs_raw)
        amount = fare.get("total_fare_inr") if fare.get("status") == "success" else None
        legs = _normalise_legs(j, origin, destination)
        em = E.combine([E.transit(km, "bmtc_bus"), E.walking(0)])
        cost = _transit_cost(amount, "fare", amount, amount,
                             {"legs": fare.get("legs"), "basis": "BMTC GTFS fare_rules (2026-27 feed)"})
        out.append(_option("bus", legs, j["duration_minutes"], cost, em, km, j["transfers"] or 0,
                           ["BMTC GTFS 2026-27 (scheduled)", "BMTC GTFS fares"],
                           ["Scheduled timetable; no live bus tracking.",
                            "Access/egress walks are straight-line estimates."], False,
                           {"transit_km": {"bus": km}}))
    return out


def build_bus_metro(res, origin, destination):
    out = []
    for j in adapt_bmtc_metro_journeys(res):
        raw = j["raw_details"]
        em_raw = raw.get("emissions") or {}
        bus_km = (em_raw.get("bmtc_scenarios") or {}).get("distance_km")
        metro_km = (em_raw.get("metro") or {}).get("distance_km")
        if bus_km is None or metro_km is None:
            continue
        f = raw.get("fare") or {}
        b = (f.get("bmtc") or {}).get("total_fare_inr")
        mq = (f.get("metro") or {}).get("smart_card_qr_fare_inr")
        mt = (f.get("metro") or {}).get("token_fare_inr")
        amount = b + mq if b is not None and mq is not None else None
        high = b + mt if b is not None and mt is not None else None
        legs = _normalise_legs(j, origin, destination)
        em = E.combine([E.transit(bus_km, "bmtc_bus"), E.transit(metro_km, "metro")])
        cost = _transit_cost(amount, "fare", amount, high,
                             {"bmtc_inr": b, "metro_smart_card_qr_inr": mq, "metro_token_inr": mt})
        out.append(_option("bus_metro", legs, j["duration_minutes"], cost, em, bus_km + metro_km,
                           j["transfers"] or 1,
                           ["BMTC GTFS 2026-27", "BMRCL Metro GTFS", "Modelled bus-Metro interchanges"],
                           ["Scheduled timetables only.", "Interchange walks are modelled."], False,
                           {"transit_km": {"bus": bus_km, "metro": metro_km}}))
    return out


def _road_leg(kind, origin, destination, route, label):
    return {"type": kind, "label": label,
            "from": {"name": "Your location", "lat": origin[0], "lon": origin[1]},
            "to": {"name": "Destination", "lat": destination[0], "lon": destination[1]},
            "distance_km": route["distance_km"], "duration_min": route["traffic_duration_min"],
            "traffic_delay_min": route.get("traffic_delay_min"),
            "path": [[origin[0], origin[1]], [destination[0], destination[1]]]}


def build_road(routes, origin, destination, market, user_vehicle, when):
    out = []
    car = routes.get("car")
    if car:
        cat = "car_petrol"
        uv = user_vehicle if (user_vehicle or {}).get("type", "car") == "car" else None
        if uv and str(uv.get("fuel_type", "")).lower() in ("ev", "electric", "bev"):
            cat = "car_ev"
        em = E.road_vehicle(car["distance_km"], cat, 1, uv, car.get("congestion_ratio"))
        fc = fuel_cost(car["distance_km"], cat, uv)
        cost = _transit_cost(fc["amount_inr"], "fuel_operating", fc["amount_inr"], fc["amount_inr"], fc)
        out.append(_option("car", [_road_leg("car", origin, destination, car, "Drive")],
                           car["traffic_duration_min"] + 3, cost, em, car["distance_km"], 0,
                           [car["traffic_source"]], ["Parking, tolls and vehicle ownership costs excluded."],
                           car.get("is_live"), {"traffic": {"delay_min": car.get("traffic_delay_min"),
                                                            "congestion_ratio": car.get("congestion_ratio")},
                                                "requires_vehicle": "car"}))
    tw = routes.get("motorcycle")
    if tw:
        cat = "two_wheeler_petrol"
        uv = user_vehicle if (user_vehicle or {}).get("type") == "two_wheeler" else None
        if uv and str(uv.get("fuel_type", "")).lower() in ("ev", "electric", "bev"):
            cat = "two_wheeler_ev"
        em = E.road_vehicle(tw["distance_km"], cat, 1, uv, tw.get("congestion_ratio"))
        fc = fuel_cost(tw["distance_km"], cat, uv)
        cost = _transit_cost(fc["amount_inr"], "fuel_operating", fc["amount_inr"], fc["amount_inr"], fc)
        out.append(_option("two_wheeler", [_road_leg("two_wheeler", origin, destination, tw, "Ride")],
                           tw["traffic_duration_min"] + 2, cost, em, tw["distance_km"], 0,
                           [tw["traffic_source"]], ["Helmet/parking costs excluded."], tw.get("is_live"),
                           {"requires_vehicle": "two_wheeler"}))
    taxi = routes.get("taxi")
    if taxi:
        km = taxi["distance_km"]
        pressure = market["price_pressure_multiplier"]
        wait = market["expected_pickup_wait_min"]
        a = estimate_auto_fare(km)
        lo, hi = a["estimated_total_inr"], a["estimated_total_inr"] * max(pressure, 1.0) * 1.1
        em = E.road_vehicle(km * RIDE_HAIL_DEADHEAD, "auto_cng", 1, None, taxi.get("congestion_ratio"))
        em.assumptions.append("+30 % dead-heading (empty) km for ride-hailing")
        out.append(_option("auto", [_road_leg("auto", origin, destination, taxi, "Auto-rickshaw")],
                           taxi["traffic_duration_min"] + wait,
                           _transit_cost(lo * pressure, "ride_hailing_estimate", lo, hi,
                                         {"base_fare_inr": lo, "price_pressure_multiplier": pressure,
                                          "basis": a["source"]}),
                           em, km, 0, [taxi["traffic_source"], "Namma Yatri open data (demand/supply)"],
                           ["Distance-based estimate, not a booking quote."], taxi.get("is_live"),
                           {"availability": {"quote_probability": market["quote_probability"],
                                             "completion_probability": market.get("completion_probability"),
                                             "trip_success_probability": market.get("trip_success_probability"),
                                             "pickup_wait_min": wait, "market": market["market_condition"],
                                             "model": market["model"]["type"]}}))
        c = estimate_cab_fare(km, "up_to_10_lakh", is_night=(when.hour >= 22 or when.hour < 6))
        lo, hi = c["estimated_total_inr"], c["estimated_total_inr"] * max(pressure, 1.0) * 1.1
        em = E.road_vehicle(km * RIDE_HAIL_DEADHEAD, "cab_diesel", 1, None, taxi.get("congestion_ratio"))
        em.assumptions.append("+30 % dead-heading (empty) km for ride-hailing")
        out.append(_option("cab", [_road_leg("cab", origin, destination, taxi, "Cab")],
                           taxi["traffic_duration_min"] + wait + 1,
                           _transit_cost(lo * pressure, "ride_hailing_estimate", lo, hi,
                                         {"base_fare_inr": lo, "price_pressure_multiplier": pressure,
                                          "basis": c["source"]}),
                           em, km, 0, [taxi["traffic_source"], "Karnataka notified cab rates",
                                       "Namma Yatri open data (demand/supply)"],
                           ["Distance-based estimate, not a booking quote."], taxi.get("is_live"),
                           {"availability": {"quote_probability": market["quote_probability"],
                                             "completion_probability": market.get("completion_probability"),
                                             "trip_success_probability": market.get("trip_success_probability"),
                                             "pickup_wait_min": wait + 1, "market": market["market_condition"],
                                             "model": market["model"]["type"]}}))
    # Auto-rickshaws are city vehicles: no auto option for intercity trips (e.g. Bengaluru-Tumakuru).
    out = [o for o in out if not (o["family"] == "auto" and (o["distance_km"] or 0) > AUTO_MAX_KM)]
    if origin[1] < 77.3 or destination[1] < 77.3:     # Tumakuru side of the region
        for o in out:
            if o["family"] in ("auto", "cab"):
                o["limitations"].append("Fares use Bengaluru ride-hailing data and tariffs; Namma Yatri "
                                        "demand/supply data covers Bengaluru only.")
            o["limitations"].append("No live or modelled congestion data for Tumakuru; roads outside "
                                    "Bengaluru use free-flow speeds.")
    return out


def _carpool_option(car_route, origin, destination, group, role, user_vehicle, compatible, real, title):
    occ = 1 + len(group)
    detour = pickup_detour_km(origin, group) if (role == "driver" and not real) else \
        round(min(p["pickup_distance_km"] for p in group) * 1.35, 2)
    km = car_route["distance_km"] + detour * 0.5   # pickups lie partly along the route
    speed = car_route["distance_km"] / max(1e-6, car_route["traffic_duration_min"])
    minutes = km / speed + 2 * len(group) + 3
    uv = user_vehicle if role == "driver" else None
    cat = "car_ev" if uv and str(uv.get("fuel_type", "")).lower() in ("ev", "electric") else "car_petrol"
    em = E.road_vehicle(km, cat, occ, uv, car_route.get("congestion_ratio"))
    fc = fuel_cost(km, cat, uv)
    share = fc["amount_inr"] / occ
    cost = _transit_cost(share, "shared_fuel", share, share,
                         {"vehicle_fuel_inr": fc["amount_inr"], "occupants": occ, "split": "equal"})
    leg = _road_leg("carpool", origin, destination, car_route, "Carpool")
    # Real colleagues' homes are never sent to the browser; simulated ones are.
    leg["pickups"] = [] if real else [
        {"employee_id": p["employee_id"], "lat": p.get("pickup_lat", p["home_lat"]),
         "lon": p.get("pickup_lon", p["home_lon"]), "home_zone": p["home_zone"]} for p in group]
    leg["distance_km"] = round(km, 2)
    leg["duration_min"] = round(minutes, 1)
    sources = [car_route["traffic_source"],
               "Registered colleagues on SmartCommute" if real else
               "Employee carpool matching (synthetic employee dataset)"]
    limits = ["Needs your colleague to accept a carpool request (Carpooling page)." if real else
              "Simulated colleagues: illustrates matching; they cannot be contacted.",
              "Pickup detour estimated from straight-line distances."]
    opt = _option("carpool", [leg], minutes, cost, em, km, 0, sources, limits, car_route.get("is_live"),
                  {"carpool": {"role": role, "occupancy": occ, "real_colleagues": real,
                               "partners": [{k: v for k, v in p.items() if k not in ("home_lat", "home_lon")}
                                            for p in group] if real else group,
                               "compatible_colleagues": compatible, "pickup_detour_km": detour,
                               "direction": group[0].get("direction", "outbound")}})
    opt["title"] = title
    return opt


def build_carpool(car_route, origin, destination, departure, user, user_vehicle, app_partners=None):
    """Carpool options with registered colleagues only (real requests possible).
    Returns (options, [], reason)."""
    if not car_route:
        return [], [], "No road route available."
    from app.services.employees import trip_direction
    direction = trip_direction(departure)
    owns_car = bool((user_vehicle or {}).get("type", "") == "car" or (user or {}).get("owns_car"))
    options = []
    app_partners = app_partners or []
    if app_partners:
        if owns_car:
            group, role = app_partners[:3], "driver"
        else:
            drivers = [p for p in app_partners if p.get("role") in ("driver", "either")]
            group, role = ([drivers[0]] + [p for p in app_partners if p is not drivers[0]][:2], "rider") \
                if drivers else ([], None)
        if group:
            names = ", ".join(p["name"] for p in group[:2]) + (" +1" if len(group) > 2 else "")
            options.append(_carpool_option(car_route, origin, destination, group, role, user_vehicle,
                                           len(app_partners), True, f"Carpool with {names}"))
    partners = []
    reason = None
    if not options:
        when = "evening return trips (office to home)" if direction == "return" else "morning trips (home to office)"
        reason = (f"No registered colleague is available for {when} within 2.5 km of your start, 2 km of your "
                  f"destination and 30 min of {departure}. Colleagues appear here once they sign up, mark "
                  "themselves available on Carpooling and save a similar trip.")
    return options, partners, reason


def build_bicycle(origin, destination):
    straight = haversine_km(origin[0], origin[1], destination[0], destination[1])
    if straight > 8.0 or straight < 0.3:
        return []
    km = straight * 1.3
    minutes = km / 13.0 * 60 + 2
    leg = {"type": "bicycle", "label": "Cycle",
           "from": {"name": "Your location", "lat": origin[0], "lon": origin[1]},
           "to": {"name": "Destination", "lat": destination[0], "lon": destination[1]},
           "distance_km": round(km, 2), "duration_min": round(minutes, 1),
           "path": [[origin[0], origin[1]], [destination[0], destination[1]]]}
    return [_option("bicycle", [leg], minutes, _transit_cost(0, "free", 0, 0), E.walking(km), km, 0,
                    ["Straight-line x 1.3 cycling estimate at 13 km/h"],
                    ["Assumes a personal bicycle; Bengaluru cycle-lane coverage is limited."], False,
                    {"requires_vehicle": "bicycle"})]


def build_walk(origin, destination):
    straight = haversine_km(origin[0], origin[1], destination[0], destination[1])
    if straight > 2.5:
        return []
    m = straight * 1.3 * 1000
    leg = {"type": "walk", "segment": "direct", "from": {"name": "Your location", "lat": origin[0], "lon": origin[1]},
           "to": {"name": "Destination", "lat": destination[0], "lon": destination[1]},
           "distance_m": round(m), "duration_min": round(m / WALK_M_PER_MIN, 1),
           "path": [[origin[0], origin[1]], [destination[0], destination[1]]]}
    return [_option("walk", [leg], m / WALK_M_PER_MIN, _transit_cost(0, "free", 0, 0), E.walking(m / 1000),
                    m / 1000, 0, ["Straight-line x 1.3 walking estimate"], [], False)]


# ---------------------------------------------------------------------------
# Filtering, ranking and explanation
# ---------------------------------------------------------------------------
def _limits(prefs, wx_fx):
    lim = dict(DEFAULT_LIMITS)
    if prefs.get("max_walking_minutes"):
        lim["max_total_walking_m"] = float(prefs["max_walking_minutes"]) * WALK_M_PER_MIN
        lim["max_origin_access_m"] = min(lim["max_origin_access_m"], lim["max_total_walking_m"])
        lim["max_destination_egress_m"] = min(lim["max_destination_egress_m"], lim["max_total_walking_m"])
    f = wx_fx.get("walking_tolerance_factor", 1.0)
    return {k: v * f for k, v in lim.items()}


def _filter(options, limits, prefs):
    accepted, rejected = [], []
    max_tr = prefs.get("max_transfers")
    avoid = set(prefs.get("avoid_modes") or [])
    for o in options:
        reasons = []
        w = o["walking"]
        if o["family"] != "walk":
            for key, lim_key, label in (("total_m", "max_total_walking_m", "total walking"),
                                        ("origin_access_m", "max_origin_access_m", "walk to first stop"),
                                        ("destination_egress_m", "max_destination_egress_m", "walk from last stop"),
                                        ("transfer_walk_m", "max_transfer_walk_m", "transfer walk")):
                if w[key] > limits[lim_key]:
                    reasons.append(f"{label} {w[key]:.0f} m exceeds {limits[lim_key]:.0f} m")
        elif w["total_m"] > limits["max_total_walking_m"]:
            reasons.append(f"walking {w['total_m']:.0f} m exceeds {limits['max_total_walking_m']:.0f} m")
        if max_tr is not None and o["transfers"] > int(max_tr):
            reasons.append(f"{o['transfers']} transfers exceeds your limit of {max_tr}")
        if o["family"] in avoid:
            reasons.append("mode excluded by your preferences")
        if reasons:
            rejected.append({"family": o["family"], "title": o["title"], "duration_min": o["duration_min"],
                             "reasons": reasons})
        else:
            accepted.append(o)
    return accepted, rejected


TRANSIT_FAMILIES = {"metro", "bus", "bus_metro", "metro_combo", "train"}


def _suppress_complex_chains(accepted, rejected):
    """Drop bus-only chains of 3+ buses when a simpler public-transport option
    (fewer transfers, at most ~15 min slower) exists, and 4+ bus chains whenever
    any other public-transport option exists."""
    keep = []
    for o in accepted:
        if o["family"] == "bus" and o["transfers"] >= 2:
            simpler = sorted([x for x in accepted if x is not o and x["family"] in TRANSIT_FAMILIES
                              and x["transfers"] < o["transfers"] and x["duration_min"] <= o["duration_min"] + 15
                              and not (x["family"] == "bus" and x["transfers"] >= 2)],
                             key=lambda x: x["duration_min"])
            other_transit = sorted([x for x in accepted if x is not o and x["family"] in TRANSIT_FAMILIES
                                    and not (x["family"] == "bus" and x["transfers"] >= 2)],
                                   key=lambda x: x["duration_min"])
            if simpler or (o["transfers"] >= 3 and other_transit):
                alt = (simpler or other_transit)[0]
                rejected.append({"family": o["family"], "title": o["title"], "duration_min": o["duration_min"],
                                 "reasons": [f"{o['transfers'] + 1}-bus chain hidden: a better public-transport "
                                             f"option exists ({alt['title']}, {alt['duration_min']:.0f} min)"]})
                continue
        keep.append(o)
    return keep


def _signature(o):
    return (o["family"], o.get("title"), tuple((l["type"], l.get("route"), (l.get("from") or {}).get("stop_id"),
                                (l.get("to") or {}).get("stop_id")) for l in o["legs"] if l["type"] in ("bus", "metro")))


def _metrics(o):
    return {"emissions": o["emissions"]["estimate_kg_co2e"], "duration": o["duration_min"],
            "cost": o["cost"]["amount_inr"], "walking": o["walking"]["total_m"],
            "transfers": o["transfers"], "uncertainty": o.get("_uncertainty", 0.2)}


def _rank(options, weights):
    for o in options:
        fam = o["family"]
        if fam in ("auto", "cab"):
            o["_uncertainty"] = round(1 - o["availability"].get("trip_success_probability",
                                                                 o["availability"]["quote_probability"]), 3)
        else:
            u = UNCERTAINTY.get(fam, 0.2)
            if fam in ("car", "two_wheeler", "carpool") and not o["is_live"]:
                u += 0.10
            o["_uncertainty"] = u
        o["features"] = P.feature_vector(_metrics(o))
        o["score"] = round(P.score(o["features"], weights), 4)
    options.sort(key=lambda o: (o["score"], o["duration_min"]))
    probs = P.choice_probabilities([o["features"] for o in options], weights) if options else []
    for i, (o, p) in enumerate(zip(options, probs), 1):
        o["rank"] = i
        o["predicted_choice_probability"] = round(p, 3)
        o["score_breakdown"] = {k: round(weights[k] * o["features"][k], 4) for k in P.FEATURES}
    return options


def _collapse(options):
    seen, kept, per_family, dropped = set(), [], {}, 0
    best_in_family = {}
    seen_titles = set()
    for o in options:  # already ranked
        sig = _signature(o)
        if sig in seen:
            dropped += 1
            continue
        seen.add(sig)
        if per_family.get(o["family"], 0) >= FAMILY_KEEP.get(o["family"], 1):
            dropped += 1
            continue
        if o["family"] in ("metro_combo", "carpool"):
            # One of each kind (Metro + Feeder bus, Metro + Auto, Auto + Metro ...)
            if (o["family"], o["title"]) in seen_titles:
                dropped += 1
                continue
            seen_titles.add((o["family"], o["title"]))
        best = best_in_family.get(o["family"])
        if best is not None and o["duration_min"] > best["duration_min"] * 1.4 + 5:
            dropped += 1          # an alternative much slower than the family's best adds noise
            continue
        best_in_family.setdefault(o["family"], o)
        per_family[o["family"]] = per_family.get(o["family"], 0) + 1
        kept.append(o)
    for i, o in enumerate(kept, 1):
        o["rank"] = i
    return kept, dropped


def _pareto(options):
    for o in options:
        a = (o["duration_min"], o["cost"]["amount_inr"] if o["cost"]["amount_inr"] is not None else 1e9,
             o["emissions"]["estimate_kg_co2e"])
        o["pareto_optimal"] = not any(
            all(x <= y for x, y in zip(b, a)) and any(x < y for x, y in zip(b, a))
            for b in [(p["duration_min"], p["cost"]["amount_inr"] if p["cost"]["amount_inr"] is not None else 1e9,
                       p["emissions"]["estimate_kg_co2e"]) for p in options if p is not o])


CHEAPER_MIN_SAVING_INR = 10.0      # worth interrupting someone for
CHEAPER_MIN_SAVING_SHARE = 0.10
CHEAPER_MAX_EXTRA_MIN = 10.0       # ...unless it costs too much time: +10 min or +25 %, whichever is larger
CHEAPER_MAX_EXTRA_SHARE = 0.25
TRIPS_PER_MONTH = 2 * 230 / 12     # two trips a working day, 230 working days a year
# Never suggest a vehicle the person may not own (we don't know if they have a cycle or two-wheeler,
# and a car only if they said so).
NEEDS_OWN_VEHICLE = {"bicycle", "two_wheeler", "car"}


def _cheaper_alternative(o, options):
    """The option that saves the most money for little extra time, or None."""
    cost = o["cost"]["amount_inr"]
    if cost is None:
        return None
    best = None
    for c in options:
        cc = c["cost"]["amount_inr"]
        if c is o or cc is None or c["family"] in NEEDS_OWN_VEHICLE:
            continue
        saving = cost - cc
        extra = c["duration_min"] - o["duration_min"]
        if saving < max(CHEAPER_MIN_SAVING_INR, CHEAPER_MIN_SAVING_SHARE * cost):
            continue
        if extra > max(CHEAPER_MAX_EXTRA_MIN, CHEAPER_MAX_EXTRA_SHARE * o["duration_min"]):
            continue
        key = (saving, -extra)
        if best is None or key > best[0]:
            best = (key, c, saving, extra)
    if not best:
        return None
    _, c, saving, extra = best
    return {
        "option_id": c["id"], "title": c["title"], "family": c["family"],
        "saves_inr": round(saving, 0),
        "saves_inr_per_month": round(saving * TRIPS_PER_MONTH, -1),
        "extra_min": round(extra, 0),
        "co2e_change_kg": round(c["emissions"]["estimate_kg_co2e"] - o["emissions"]["estimate_kg_co2e"], 2),
        "rule": (f"Shown when another option saves at least Rs {CHEAPER_MIN_SAVING_INR:.0f} and "
                 f"{CHEAPER_MIN_SAVING_SHARE:.0%} of the fare, and takes at most "
                 f"{CHEAPER_MAX_EXTRA_MIN:.0f} min or {CHEAPER_MAX_EXTRA_SHARE:.0%} longer, whichever is more. "
                 "Monthly figure assumes 2 trips a day on 230 working days a year."),
    }


def _explain(options, baseline, weights, context):
    if not options:
        return
    fastest = min(options, key=lambda o: o["duration_min"])
    greenest = min(options, key=lambda o: o["emissions"]["estimate_kg_co2e"])
    priced = [o for o in options if o["cost"]["amount_inr"] is not None]
    cheapest = min(priced, key=lambda o: o["cost"]["amount_inr"]) if priced else None
    for o in options:
        badges = []
        if o["rank"] == 1:
            badges.append("Recommended")
        if o is fastest:
            badges.append("Fastest")
        if o is greenest:
            badges.append("Lowest CO2e")
        if o is cheapest:
            badges.append("Cheapest")
        o["badges"] = badges
        o["booking"] = booking_links(o)
        o["cheaper_alternative"] = _cheaper_alternative(o, options)
        reasons = []
        if baseline and o["family"] != "car":
            saved = baseline["emissions"]["estimate_kg_co2e"] - o["emissions"]["estimate_kg_co2e"]
            if saved > 0.01:
                pct = saved / baseline["emissions"]["estimate_kg_co2e"] * 100
                reasons.append(f"Saves ~{saved:.2f} kg CO2e ({pct:.0f}%) vs driving alone")
            dt = o["duration_min"] - baseline["duration_min"]
            reasons.append(f"{abs(dt):.0f} min {'slower' if dt > 0 else 'faster'} than driving")
            if o["cost"]["amount_inr"] is not None and baseline["cost"]["amount_inr"] is not None:
                dc = baseline["cost"]["amount_inr"] - o["cost"]["amount_inr"]
                if abs(dc) >= 1:
                    reasons.append(f"Rs {abs(dc):.0f} {'cheaper' if dc > 0 else 'more expensive'} than fuel for driving")
        if o["family"] == "car":
            reasons.append("Reference option: driving alone (savings on other cards are measured against this)")
            if o.get("traffic", {}).get("delay_min"):
                reasons.append(f"~{o['traffic']['delay_min']:.0f} min of traffic delay expected")
        if o["walking"]["total_m"]:
            reasons.append(f"{o['walking']['total_m']:.0f} m walking")
        if o["transfers"]:
            reasons.append(f"{o['transfers']} transfer{'s' if o['transfers'] > 1 else ''}")
        if o["family"] == "carpool":
            reasons.append(f"{o['carpool']['compatible_colleagues']} compatible colleague(s) nearby; "
                           f"{o['carpool']['occupancy']} occupants")
        if o["family"] in ("auto", "cab"):
            av = o["availability"]
            if av.get("completion_probability") is not None:
                reasons.append(f"{av['trip_success_probability']:.0%} chance the ride happens "
                               f"(driver quote {av['quote_probability']:.0%} x completion {av['completion_probability']:.0%}, ML forecast)")
            reasons.append(f"{av['quote_probability']:.0%} chance of a driver quote, ~{av['pickup_wait_min']:.0f} min pickup "
                           f"({av['market']} market)")
        o["reasons"] = reasons
        top = sorted(o["score_breakdown"].items(), key=lambda kv: kv[1])
        o["why_ranked"] = f"Weighted by your priorities ({', '.join(P.explain_weights(weights))})."
        o.pop("_uncertainty", None)
    rec = options[0]
    car_km = baseline["emissions"]["estimate_kg_co2e"] if baseline else None
    summary = f"{rec['title']}: {rec['duration_min']:.0f} min"
    if rec["cost"]["amount_inr"] is not None:
        summary += f", Rs {rec['cost']['amount_inr']:.0f}"
    summary += f", ~{rec['emissions']['estimate_kg_co2e']:.2f} kg CO2e/passenger"
    if rec["family"] == "carpool":
        summary += f", {rec['carpool']['compatible_colleagues']} compatible employees nearby"
    if car_km and rec["family"] != "car":
        summary += f" ({(1 - rec['emissions']['estimate_kg_co2e'] / car_km) * 100:.0f}% less than driving alone)"
    return summary


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------
_CANDIDATE_CACHE: dict = {}
CANDIDATE_TTL_S = 300


def _generate(origin, destination, travel_date, departure_time, when, vehicle, employee_id, owns_car,
              app_partners=None):
    """Plan every mode once. Cached so re-ranking (goal/profile changes) is instant."""
    key = hashlib.sha1(json.dumps([origin, destination, travel_date, departure_time, vehicle, employee_id,
                                   owns_car, [p.get("ref") for p in (app_partners or [])]],
                                  sort_keys=True, default=str).encode()).hexdigest()
    hit = _CANDIDATE_CACHE.get(key)
    if hit and time.time() - hit[0] < CANDIDATE_TTL_S:
        return json.loads(hit[1]), True

    weather = get_weather(origin[0], origin[1], when)
    wx_fx = weather_effects(weather)
    traffic = traffic_profile(when)
    market = market_state(when.hour, wx_fx)

    errors, timings, candidates = [], {}, []
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {m: pool.submit(road_route, origin, destination, m, when, wx_fx)
                   for m in ("car", "motorcycle", "taxi")}
        with PLANNER_LOCK:
            for fam, fn, builder in (("metro", plan_journey, build_metro),
                                     ("bus", plan_bmtc_latest_from_gps, build_bus),
                                     ("bus_metro", plan_bmtc_then_metro, build_bus_metro)):
                ts = time.time()
                try:
                    res = fn(origin[0], origin[1], destination[0], destination[1], travel_date, departure_time)
                    if res.get("status") == "success":
                        built = builder(res, origin, destination)
                        candidates.extend(built)
                        if not built:
                            errors.append({"family": fam, "reason": "No complete journey after validation."})
                    else:
                        errors.append({"family": fam, "reason": res.get("message", "Unavailable")})
                except ValueError as exc:
                    msg = str(exc)
                    if "Metro station is reachable" in msg:
                        msg = "No Metro station within walking distance (5 km) of the origin or destination."
                    errors.append({"family": fam, "reason": msg})
                except Exception as exc:
                    errors.append({"family": fam, "reason": f"{type(exc).__name__}: {exc}"})
                timings[fam] = round(time.time() - ts, 2)
            ts = time.time()
            try:
                from app.services.metro_combos import build_metro_combos
                combos, _notes = build_metro_combos(
                    origin, destination, travel_date, departure_time, market,
                    [c for c in candidates if c["family"] == "metro"],
                    {"_option": _option, "_transit_cost": _transit_cost, "_transit_leg": _transit_leg,
                     "_normalise_legs": _normalise_legs})
                candidates.extend(combos)
            except Exception as exc:
                errors.append({"family": "metro_combo", "reason": f"{type(exc).__name__}: {exc}"})
            timings["metro_combo"] = round(time.time() - ts, 2)
            ts = time.time()
            try:
                from app.services.rail import build_rail_options, corridor_relevant
                if corridor_relevant(origin, destination):
                    rail_opts, rail_notes = build_rail_options(
                        origin, destination, travel_date, departure_time, market,
                        {"_option": _option, "_transit_cost": _transit_cost, "_normalise_legs": _normalise_legs})
                    candidates.extend(rail_opts)
                    if not rail_opts:
                        errors.append({"family": "train", "reason": (rail_notes[0] if rail_notes else
                                       "No daily train fits this trip and time.")})
            except Exception as exc:
                errors.append({"family": "train", "reason": f"{type(exc).__name__}: {exc}"})
            timings["train"] = round(time.time() - ts, 2)
        routes = {}
        for m, f in futures.items():
            try:
                routes[m] = f.result(timeout=40)
            except Exception as exc:
                errors.append({"family": m, "reason": str(exc)})

    candidates.extend(build_road(routes, origin, destination, market, vehicle, when))
    carpool_opts, partners, carpool_reason = build_carpool(
        routes.get("car"), origin, destination, departure_time,
        {"employee_id": employee_id, "owns_car": owns_car}, vehicle, app_partners)
    candidates.extend(carpool_opts)
    if carpool_reason:
        errors.append({"family": "carpool", "reason": carpool_reason})
    candidates.extend(build_walk(origin, destination))
    candidates.extend(build_bicycle(origin, destination))
    data = {"candidates": candidates, "partners": partners, "errors": errors, "timings": timings,
            "context": {"weather": weather, "weather_effects": wx_fx, "traffic": traffic,
                        "ride_hailing_market": market,
                        "live_traffic": bool((routes.get("car") or {}).get("is_live"))}}
    _CANDIDATE_CACHE[key] = (time.time(), json.dumps(data, default=str))
    if len(_CANDIDATE_CACHE) > 128:
        for k in sorted(_CANDIDATE_CACHE, key=lambda k: _CANDIDATE_CACHE[k][0])[:32]:
            _CANDIDATE_CACHE.pop(k, None)
    return json.loads(_CANDIDATE_CACHE[key][1]), False


def _compare(a, b):
    """How option a compares with option b (positive = a is better/saves)."""
    if not a or not b:
        return None
    out = {"vs_option_id": b["id"], "vs_title": b["title"],
           "time_saved_min": round(b["duration_min"] - a["duration_min"], 1),
           "co2e_saved_kg": round(b["emissions"]["estimate_kg_co2e"] - a["emissions"]["estimate_kg_co2e"], 3),
           "money_saved_inr": None}
    if a["cost"]["amount_inr"] is not None and b["cost"]["amount_inr"] is not None:
        out["money_saved_inr"] = round(b["cost"]["amount_inr"] - a["cost"]["amount_inr"], 2)
    return out


def recommend(origin, destination, travel_date: str, departure_time: str, user: dict | None = None,
              profile: str | None = None, weights: dict | None = None, preferences: dict | None = None,
              vehicle: dict | None = None, use_cache: bool = True, app_partners: list | None = None) -> dict:
    t0 = time.time()
    origin = (float(origin[0]), float(origin[1]))
    destination = (float(destination[0]), float(destination[1]))
    when = datetime.strptime(f"{travel_date} {departure_time}", "%Y-%m-%d %H:%M")
    user = user or {}
    prefs = {**(user.get("preferences") or {}), **(preferences or {})}
    vehicle = vehicle or user.get("vehicle")

    if weights:
        active_weights, weight_source = P.normalise_weights(weights), "request"
    elif profile:
        if profile not in P.PROFILES:
            raise ValueError(f"Unknown profile {profile!r}; choose {sorted(P.PROFILES)}")
        active_weights, weight_source = P.normalise_weights(P.PROFILES[profile]), f"profile:{profile}"
    elif user.get("weights"):
        active_weights, weight_source = P.normalise_weights(user["weights"]), "learned"
    else:
        p = prefs.get("profile", P.DEFAULT_PROFILE)
        active_weights, weight_source = P.normalise_weights(P.PROFILES.get(p, P.PROFILES[P.DEFAULT_PROFILE])), f"profile:{p}"

    if haversine_km(*origin, *destination) < 0.15:
        raise ValueError("Origin and destination are the same place.")

    if not use_cache:
        _CANDIDATE_CACHE.clear()
    data, cached = _generate(origin, destination, travel_date, departure_time, when, vehicle,
                             user.get("employee_id"), prefs.get("owns_car"), app_partners)
    candidates, partners, errors = data["candidates"], data["partners"], data["errors"]
    ctx = data["context"]

    baseline = next((o for o in candidates if o["family"] == "car"), None)
    limits = _limits(prefs, ctx["weather_effects"])
    accepted, rejected = _filter(candidates, limits, prefs)
    accepted = _suppress_complex_chains(accepted, rejected)
    ranked = _rank(accepted, active_weights)
    final, dropped = _collapse(ranked)
    # Choice probabilities must be over the options actually shown.
    if final:
        for o, pr in zip(final, P.choice_probabilities([o["features"] for o in final], active_weights)):
            o["predicted_choice_probability"] = round(pr, 3)
    _pareto(final)
    summary = _explain(final, baseline, active_weights, {"weather": ctx["weather"]})

    usual_family = prefs.get("usual_mode")
    usual = None
    for o in final:
        o["depart_time"] = when.strftime("%H:%M")
        o["arrive_time"] = (when + timedelta(minutes=o["duration_min"])).strftime("%H:%M")
        o["is_usual_mode"] = bool(usual_family) and o["family"] in USUAL_MODE_FAMILIES.get(usual_family, {usual_family})
        if o["is_usual_mode"] and (usual is None or o["duration_min"] < usual["duration_min"]):
            usual = o
    if usual_family and usual is None:  # usual mode filtered out: compare against its raw candidate
        pool = [c for c in candidates if c["family"] in USUAL_MODE_FAMILIES.get(usual_family, {usual_family})]
        usual = min(pool, key=lambda c: c["duration_min"]) if pool else None
    rec = final[0] if final else None

    return {
        "request_id": uuid.uuid4().hex,
        "status": "success" if final else "unavailable",
        "request": {"origin": {"lat": origin[0], "lon": origin[1]},
                    "destination": {"lat": destination[0], "lon": destination[1]},
                    "travel_date": travel_date, "departure_time": departure_time},
        "summary": summary,
        "recommended_option_id": rec["id"] if rec else None,
        "options": final,
        "baseline_option_id": baseline["id"] if baseline and baseline in final else None,
        "baseline_drive_alone": None if not baseline else {
            "duration_min": baseline["duration_min"], "cost_inr": baseline["cost"]["amount_inr"],
            "co2e_kg": baseline["emissions"]["estimate_kg_co2e"], "distance_km": baseline["distance_km"]},
        "usual_option": None if not usual else {
            "id": usual["id"], "family": usual["family"], "title": usual["title"],
            "duration_min": usual["duration_min"], "shown": usual in final},
        "comparisons": {
            "recommended_vs_drive_alone": _compare(rec, baseline) if rec is not baseline else None,
            "recommended_vs_usual": _compare(rec, usual) if usual and rec is not usual else None,
        },
        "context": ctx,
        "personalisation": {"weights": active_weights, "source": weight_source,
                            "top_priorities": P.explain_weights(active_weights),
                            "constraints": limits, "preferences": prefs},
        "carpool_matches": partners[:10],
        "rejected": rejected,
        "unavailable": errors,
        "stats": {"candidates_generated": len(candidates), "passed_filters": len(accepted),
                  "duplicates_or_extra_alternatives_removed": dropped, "shown": len(final),
                  "planner_seconds": data["timings"], "total_seconds": round(time.time() - t0, 2)},
        "methodology": {"emissions": E.methodology_notes()["metric"],
                        "ranking": "Weighted normalised costs (conditional-logit utility); weights learned "
                                   "from your choices when you have a profile."},
        "notes": [
            "Transit times are from published GTFS timetables (no live vehicle positions).",
            "Ride-hailing prices are modelled estimates, not booking quotes.",
            "CO2e is per passenger; ranges reflect fuel-mix, grid and vehicle uncertainty.",
        ],
        "cached": cached,
    }
