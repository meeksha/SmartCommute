"""Company shuttle route planner.

1. Find where public transport serves the office poorly: for every home ward
   in the office's Census-derived population, check (a) Metro: home and office
   within the Metro catchment, and (b) BMTC: a *direct* bus route (from the
   2026-27 GTFS) that stops within 500 m of the ward centre and within 500 m of
   the office. Commuters who drive, ride or take autos/cabs from wards with
   neither are the shuttle's target riders.
2. Pick-up points are real BMTC stops (the stop nearest each target ward's centre),
   since they are kerbside places where a bus can stop.
3. Routes: a capacitated vehicle-routing problem solved with Google OR-Tools.
   Each vehicle starts at its first pick-up, ends at the office, carries at most
   `capacity` riders and must keep the in-vehicle ride under `max_ride_min`.
   Pick-ups that don't fit the fleet are dropped (reported).

Distances are straight-line x 1.35 (the road network isn't loaded server side);
the shuttle speed is the Twin's corridor speed. Costs use the KSRTC hire rate;
emissions use the same functions as the rest of the app.
"""
from __future__ import annotations

import math
from functools import lru_cache

import numpy as np
import pandas as pd

from app.services import emissions as E
from app.services.costs import SHUTTLE_COST_PER_VKM_INR, SHUTTLE_COST_SOURCE
from app.services.population import _hav

ROAD_CIRCUITY = 1.35
BUS_WALK_KM = 0.5
TARGET_MODES = ("car", "two_wheeler", "auto", "cab")
STOP_DWELL_MIN = 1.5
WORKING_DAYS = 230
PICKUP_VALUE_KM = 4.0      # solver trade-off: one rider is worth up to 4 km of extra route
VEHICLE_FIXED_KM = 15.0    # and each extra bus must justify ~15 km of route


@lru_cache(maxsize=1)
def _route_stop_index():
    """stop_id -> set(route_short_name), stops frame, from the BMTC GTFS connections."""
    from app.routing.bmtc_latest_planner import BASE
    con = pd.read_csv(BASE / "bmtc_connections.csv", usecols=["route_short_name", "stop_id"], dtype=str)
    con = con.drop_duplicates()
    idx: dict[str, set] = {}
    for r, sid in zip(con["route_short_name"], con["stop_id"]):
        idx.setdefault(sid, set()).add(r)
    stops = pd.read_csv(BASE / "bmtc_stops.csv", dtype={"stop_id": str})
    stops = stops[stops["stop_id"].isin(idx)].reset_index(drop=True)
    return idx, stops


def _routes_near(lat, lon, radius_km=BUS_WALK_KM):
    idx, stops = _route_stop_index()
    d = _hav(lat, lon, stops["stop_lat"].to_numpy(), stops["stop_lon"].to_numpy())
    near = stops["stop_id"].to_numpy()[d <= radius_km]
    out = set()
    for sid in near:
        out |= idx.get(sid, set())
    return {r for r in out if not str(r).upper().startswith("KIA")}


def _nearest_stop(lat, lon):
    _, stops = _route_stop_index()
    d = _hav(lat, lon, stops["stop_lat"].to_numpy(), stops["stop_lon"].to_numpy())
    i = int(np.argmin(d))
    r = stops.iloc[i]
    return {"stop_id": r["stop_id"], "name": r["stop_name"], "lat": float(r["stop_lat"]),
            "lon": float(r["stop_lon"]), "distance_km": round(float(d[i]), 2)}


def service_gaps(office: str | None = None, headcount: int = 2000, start_time: str = "09:30") -> pd.DataFrame:
    """Per home ward: target riders and whether Metro / a direct BMTC route serve the office."""
    from app.services.digital_twin import population
    pop = population(office, headcount, start_time)
    olat, olon = float(pop["office_lat"].iloc[0]), float(pop["office_lon"].iloc[0])
    office_routes = _routes_near(olat, olon)
    rows = []
    for (ward, name, lat, lon), g in pop.groupby(["ward_no", "home_zone", "home_lat", "home_lon"]):
        home_routes = _routes_near(lat, lon)
        direct = sorted(home_routes & office_routes)
        metro_ok = bool(g["metro_eligible"].iloc[0])
        target = g[g["baseline_mode"].isin(TARGET_MODES)]
        rows.append({"ward_no": int(ward), "ward": name, "lat": lat, "lon": lon,
                     "commuters": int(len(g)), "road_commuters": int(len(target)),
                     "road_km": float(g["road_km"].iloc[0]),
                     "metro_serves": metro_ok, "direct_bus_routes": len(direct),
                     "example_routes": direct[:3],
                     "underserved": (not metro_ok) and len(direct) == 0,
                     "target_ids": target["employee_id"].tolist()})
    return pd.DataFrame(rows)


def _solve_vrp(nodes, demand, dist_km, capacity, n_vehicles, max_ride_min, speed_kmh, seconds):
    from ortools.constraint_solver import pywrapcp, routing_enums_pb2
    # Node 0 = office (end), node 1 = virtual start (free to leave), 2.. = pick-ups
    n = len(nodes)
    scale = 1000
    mgr = pywrapcp.RoutingIndexManager(n, n_vehicles, [1] * n_vehicles, [0] * n_vehicles)
    routing = pywrapcp.RoutingModel(mgr)

    def dist_cb(i, j):
        a, b = mgr.IndexToNode(i), mgr.IndexToNode(j)
        if a == 1 or b == 1:
            return 0
        return int(dist_km[a][b] * scale)
    dcb = routing.RegisterTransitCallback(dist_cb)
    routing.SetArcCostEvaluatorOfAllVehicles(dcb)

    def dem_cb(i):
        return int(demand[mgr.IndexToNode(i)])
    qcb = routing.RegisterUnaryTransitCallback(dem_cb)
    routing.AddDimensionWithVehicleCapacity(qcb, 0, [capacity] * n_vehicles, True, "Load")

    def time_cb(i, j):
        a, b = mgr.IndexToNode(i), mgr.IndexToNode(j)
        if a == 1:
            return 0
        return int((dist_km[a][b] / speed_kmh * 60 + (STOP_DWELL_MIN if a >= 2 else 0)) * 10)
    tcb = routing.RegisterTransitCallback(time_cb)
    routing.AddDimension(tcb, 0, int(max_ride_min * 10), True, "Time")
    for node in range(2, n):
        # Skipping a pick-up costs as much as PICKUP_VALUE_KM of driving per rider, so the solver
        # won't send a bus on a long detour for one or two people.
        routing.AddDisjunction([mgr.NodeToIndex(node)], int(PICKUP_VALUE_KM * scale * demand[node]))
    routing.SetFixedCostOfAllVehicles(int(VEHICLE_FIXED_KM * scale))

    params = pywrapcp.DefaultRoutingSearchParameters()
    params.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    params.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    params.time_limit.FromSeconds(int(seconds))
    sol = routing.SolveWithParameters(params)
    if sol is None:
        return []
    routes = []
    for v in range(n_vehicles):
        idx = routing.Start(v)
        seq = []
        while not routing.IsEnd(idx):
            node = mgr.IndexToNode(idx)
            if node >= 2:
                seq.append(node)
            idx = sol.Value(routing.NextVar(idx))
        if seq:
            routes.append(seq)
    return routes


@lru_cache(maxsize=16)
def plan_shuttles(office: str | None = None, headcount: int = 2000, start_time: str = "09:30",
                  capacity: int = 40, max_vehicles: int = 10, max_ride_min: int = 75,
                  include_served: bool = False, seconds: int = 5) -> dict:
    from app.services.digital_twin import population, SPEED_KMH, _trip
    pop = population(office, headcount, start_time).set_index("employee_id")
    gaps = service_gaps(office, headcount, start_time)
    olat, olon = float(pop["office_lat"].iloc[0]), float(pop["office_lon"].iloc[0])
    office_name = pop["office_zone"].iloc[0]
    sel = gaps if include_served else gaps[gaps["underserved"]]
    sel = sel[sel["road_commuters"] > 0]

    # Pick-up points: nearest real BMTC stop to each target ward; merge wards sharing a stop.
    pick = {}
    for r in sel.itertuples():
        st = _nearest_stop(r.lat, r.lon)
        key = st["stop_id"]
        p = pick.setdefault(key, {**st, "wards": [], "ids": []})
        p["wards"].append(r.ward)
        p["ids"].extend(r.target_ids)
    pickups = []
    for p in pick.values():                     # split stops with more riders than one bus holds
        ids = p["ids"]
        for k in range(0, len(ids), capacity):
            pickups.append({**p, "ids": ids[k:k + capacity]})
    nodes = [{"name": office_name, "lat": olat, "lon": olon}, {"name": "start"}] + pickups
    demand = [0, 0] + [len(p["ids"]) for p in pickups]
    n = len(nodes)
    dist = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            if i != j and i != 1 and j != 1:
                dist[i][j] = float(_hav(nodes[i]["lat"], nodes[i]["lon"], nodes[j]["lat"], nodes[j]["lon"])) * ROAD_CIRCUITY
    speed = SPEED_KMH["shuttle"]
    routes = _solve_vrp(nodes, demand, dist, int(capacity), int(max_vehicles), int(max_ride_min), speed,
                        int(seconds)) if len(pickups) else []

    out_routes, served = [], set()
    total_vkm = 0.0
    base_co2 = base_cost = 0.0
    for v, seq in enumerate(routes, start=1):
        stops = []
        # Ride time from each pick-up to the office (so the first rider rides longest).
        legs = list(zip(seq, seq[1:] + [0]))
        leg_min = [dist[a][b] / speed * 60 + STOP_DWELL_MIN for a, b in legs]
        km = sum(dist[a][b] for a, b in legs)
        riders = 0
        for i, node in enumerate(seq):
            p = nodes[node]
            ride = sum(leg_min[i:])
            riders += len(p["ids"])
            served.update(p["ids"])
            stops.append({"stop": p["name"], "lat": p["lat"], "lon": p["lon"], "boardings": len(p["ids"]),
                          "wards": sorted(set(p["wards"])), "ride_to_office_min": round(ride, 1),
                          "walk_from_ward_centre_km": p["distance_km"]})
        h, m = map(int, start_time.split(":"))
        for s in stops:
            dep = int(round(h * 60 + m - 5 - s["ride_to_office_min"]))
            s["pickup_time"] = f"{dep // 60:02d}:{dep % 60:02d}"
        fleet = E.road_vehicle(km, "shuttle_diesel")
        out_routes.append({"vehicle": v, "stops": stops, "riders": riders, "route_km": round(km, 1),
                           "max_ride_min": round(sum(leg_min), 1), "load_factor": round(riders / capacity, 2),
                           "first_pickup": stops[0]["pickup_time"],
                           "fleet_co2e_kg_one_way": round(fleet.vehicle_trip_kg_co2e, 2)})
        total_vkm += km

    # Baseline of the riders who would switch, using the Twin's per-trip functions.
    for eid in served:
        row = pop.loc[eid]
        t, c, e, _ = _trip(row["baseline_mode"], float(row["road_km"]))
        base_co2 += e
        base_cost += c
    fleet_co2 = sum(r["fleet_co2e_kg_one_way"] for r in out_routes)
    # Morning run + evening run; an empty return/positioning leg is not counted (stated).
    annual_cost = total_vkm * SHUTTLE_COST_PER_VKM_INR * 2 * WORKING_DAYS
    annual_saved_t = (base_co2 - fleet_co2) * 2 * WORKING_DAYS / 1000
    targets = int(sel["road_commuters"].sum())
    return {
        "office": office_name,
        "office_point": {"lat": olat, "lon": olon},
        "service_gaps": {
            "wards_total": int(len(gaps)), "wards_underserved": int(gaps["underserved"].sum()),
            "road_commuters_in_underserved_wards": int(gaps.loc[gaps["underserved"], "road_commuters"].sum()),
            "wards": gaps.drop(columns=["target_ids"]).sort_values(["underserved", "road_commuters"],
                                                                   ascending=[False, False]).head(60)
            .to_dict("records"),
        },
        "routes": out_routes,
        "summary": {
            "vehicles": len(out_routes), "capacity": int(capacity), "riders": len(served),
            "target_riders": targets, "unserved_target_riders": max(0, targets - len(served)),
            "vehicle_km_per_day": round(total_vkm * 2, 1),
            "annual_cost_inr": round(annual_cost, 0),
            "rider_costs_avoided_annual_inr": round(base_cost * 2 * WORKING_DAYS, 0),
            "co2e_one_way_before_kg": round(base_co2, 1), "co2e_one_way_after_kg": round(fleet_co2, 1),
            "annual_co2e_saved_tonnes": round(annual_saved_t, 1),
            "cost_per_tonne_inr": round(annual_cost / annual_saved_t, 0) if annual_saved_t > 0 else None,
            "cost_per_rider_trip_inr": round(annual_cost / max(1, len(served) * 2 * WORKING_DAYS), 1),
        },
        "method": [
            "Underserved = home ward centre has no Metro within 1.5 km (or office has none) AND no BMTC "
            "route stops within 500 m of both the ward centre and the office (BMTC GTFS 2026-27).",
            "Target riders = commuters whose Census baseline mode is car, two-wheeler, auto or cab.",
            "Pick-ups = nearest BMTC stop to each ward centre. Routes: OR-Tools capacitated VRP, "
            f"{capacity} seats, ride <= {max_ride_min} min, up to {max_vehicles} vehicles.",
            f"Distances straight-line x {ROAD_CIRCUITY}; shuttle speed {speed:g} km/h; "
            f"{STOP_DWELL_MIN} min per stop; arrive 5 min before {start_time}.",
            f"The solver skips a pick-up when serving it costs more than {PICKUP_VALUE_KM:g} km of route per "
            f"rider, and adds a bus only if it saves more than {VEHICLE_FIXED_KM:g} km.",
            f"Cost: {SHUTTLE_COST_SOURCE}; morning and evening runs, positioning km excluded.",
            "Assumes every target rider on a route switches (break-even upper bound).",
        ],
    }
