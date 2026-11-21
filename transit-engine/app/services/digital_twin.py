"""Organisation-level commute Digital Twin (scenario simulator), v2.

Simulates the whole employee population for one working day and compares a
baseline with a what-if scenario:

* metro_shift_pct          - share of eligible car/2W/auto commuters living
                             and working near Metro who switch to Metro
* carpool_pct              - share of feasible carpool groups that form
* shuttle_count/capacity   - company shuttles assigned to the densest
                             home-cluster x office-zone corridors
* ride_hailing_price_change_pct - price change for auto/cab; mode shift via a
                             price elasticity (default -0.4)
* transit_fare_change_pct  - BMTC/Metro fare change; elasticity -0.3
* rain                     - wet-day behaviour (walk/cycle -> auto/bus,
                             slower roads)

Per-trip emissions and costs use exactly the same functions as the journey
recommender (app.services.emissions / costs), so organisation totals are
consistent with what an individual sees. Travel times here are corridor-level
models (documented below), not per-employee GTFS searches.
"""
from __future__ import annotations

import json
import math
from copy import deepcopy
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from app.services import emissions as E
from app.services.costs import fuel_cost, SHUTTLE_COST_PER_VKM_INR
from app.services.population import population_for, describe as describe_population, _hav, DEFAULT_HEADCOUNT, DEFAULT_START
from app.services.places import metro_stations
from app.routing.metro_fares import estimate_metro_fare
from app.routing.namma_yatri_fares import estimate_auto_fare, estimate_cab_fare

CENSUS = Path("data/processed/employees/bangalore_urban_commuting_statistics.csv")
FARE_DB = Path("data/processed/bmtc_latest/bmtc_fares.sqlite")
FARE_CURVE_CACHE = Path("data/processed/bmtc_latest/bmtc_fare_curve.json")

WORKING_DAYS_PER_YEAR = 230
ROAD_CIRCUITY = 1.35
MODES = ["walk", "bicycle", "two_wheeler", "car", "carpool", "auto", "cab", "bus", "metro", "shuttle"]
MODE_LABELS = {"walk": "Walk", "bicycle": "Bicycle", "two_wheeler": "Two-wheeler", "car": "Car (solo)",
               "carpool": "Carpool", "auto": "Auto-rickshaw", "cab": "Cab", "bus": "BMTC bus",
               "metro": "Metro", "shuttle": "Company shuttle"}

# Corridor speed models (km/h, in-vehicle, peak-weighted average) - assumptions.
SPEED_KMH = {"car": 18.0, "two_wheeler": 22.0, "auto": 18.0, "cab": 18.0, "bus": 14.0,
             "metro": 32.0, "shuttle": 17.0, "walk": 4.8, "bicycle": 13.0}
OVERHEAD_MIN = {"car": 5, "two_wheeler": 3, "auto": 6, "cab": 7, "bus": 14, "metro": 8,
                "shuttle": 12, "walk": 0, "bicycle": 2, "carpool": 10}
RIDE_HAIL_DEADHEAD = 1.30     # empty km per paid km (ITF-style uplift), assumption
METRO_CATCHMENT_KM = 1.5
AUTO_SHARE_OF_AUTO_TAXI = 0.7

# Transit: Namma Metro fare rise of ~46 % (9 Feb 2025) cut weekday ridership ~10 % (Deccan Herald,
# 11 Feb 2025) -> short-run elasticity ~ -0.22. Ride-hailing: literature-range assumption.
ELASTICITY = {"ride_hailing_price": -0.4, "transit_fare": -0.22}

CENSUS_MODE_MAP = {
    "On foot": "walk", "Bicycle": "bicycle", "Moped/Scooter/Motor Cycle": "two_wheeler",
    "Car/Jeep/Van": "car", "Tempo/Autorickshaw/Taxi": "auto_taxi", "Bus": "bus", "Train": "metro",
}
BANDS = [("distance_0_1_km", 0, 1.5), ("distance_2_5_km", 1.5, 5.5), ("distance_6_10_km", 5.5, 10.5),
         ("distance_11_20_km", 10.5, 20.5), ("distance_21_30_km", 20.5, 30.5),
         ("distance_31_50_km", 30.5, 1e9)]


# ---------------------------------------------------------------------------
# Calibration helpers
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def census_mode_given_distance() -> dict:
    """P(mode | distance band) from Census 2011 Table B-28 (Bangalore Urban).

    Walking beyond 5 km is treated as implausible for a daily office commute
    and its share is redistributed proportionally to the other modes.
    """
    d = pd.read_csv(CENSUS)
    d = d[d["mode"].isin(CENSUS_MODE_MAP)]
    table = {}
    for col, lo, hi in BANDS:
        counts = {CENSUS_MODE_MAP[m]: float(v) for m, v in zip(d["mode"], d[col])}
        if lo >= 5.5:
            counts["walk"] = 0.0
        if lo >= 20.5:
            counts["bicycle"] = counts.get("bicycle", 0) * 0.3
        total = sum(counts.values())
        table[col] = {k: v / total for k, v in counts.items() if v > 0}
    return table


def _band(distance_km):
    for col, lo, hi in BANDS:
        if lo <= distance_km < hi:
            return col
    return BANDS[-1][0]


@lru_cache(maxsize=1)
def bmtc_fare_curve() -> list:
    """Median BMTC fare by distance bin, calibrated from the GTFS fare rules."""
    if FARE_CURVE_CACHE.exists():
        return json.loads(FARE_CURVE_CACHE.read_text())
    import sqlite3
    from app.services.places import bmtc_stop_coords
    coords = bmtc_stop_coords()
    con = sqlite3.connect(FARE_DB)
    rows = con.execute(
        "SELECT r.origin_id, r.destination_id, a.price FROM fare_rules r "
        "JOIN fare_attributes a ON a.fare_id = r.fare_id "
        "WHERE r.rowid % 397 = 0 LIMIT 40000").fetchall()
    con.close()
    pts = []
    for o, dst, price in rows:
        a, b = coords.get(str(o)), coords.get(str(dst))
        if a and b:
            pts.append((float(_hav(a[0], a[1], b[0], b[1])) * 1.25, float(price)))
    df = pd.DataFrame(pts, columns=["km", "fare"])
    edges = [0, 2, 4, 6, 8, 10, 12, 15, 18, 21, 25, 30, 40, 80]
    df["bin"] = pd.cut(df["km"], edges)
    curve = [{"max_km": float(iv.right), "fare_inr": float(g["fare"].median())}
             for iv, g in df.groupby("bin", observed=True) if len(g) >= 20]
    # enforce monotone non-decreasing
    for i in range(1, len(curve)):
        curve[i]["fare_inr"] = max(curve[i]["fare_inr"], curve[i - 1]["fare_inr"])
    try:
        FARE_CURVE_CACHE.write_text(json.dumps(curve))
    except OSError:
        pass
    return curve


def bmtc_fare_for(km: float) -> float:
    curve = bmtc_fare_curve()
    for c in curve:
        if km <= c["max_km"]:
            return c["fare_inr"]
    return curve[-1]["fare_inr"] if curve else 30.0


# ---------------------------------------------------------------------------
# Population model
# ---------------------------------------------------------------------------
@lru_cache(maxsize=32)
def population(office: str | None = None, headcount: int = DEFAULT_HEADCOUNT,
               start_time: str = DEFAULT_START) -> pd.DataFrame:
    """Census-derived commuters of one company office, with corridor attributes.

    Baseline modes come straight from Census 2011 B-28 (see app.services.population);
    departure = office start time - baseline travel time.
    """
    from sklearn.cluster import KMeans
    df = population_for(office, headcount, start_time).copy()

    st = metro_stations()
    hl, ho = df["home_lat"].to_numpy()[:, None], df["home_lon"].to_numpy()[:, None]
    ol, oo = df["office_lat"].to_numpy()[:, None], df["office_lon"].to_numpy()[:, None]
    sl, so = st["stop_lat"].to_numpy()[None, :], st["stop_lon"].to_numpy()[None, :]
    dh = _hav(hl, ho, sl, so)
    dw = _hav(ol, oo, sl, so)
    ih, iw = dh.argmin(axis=1), dw.argmin(axis=1)
    df["home_metro_km"] = dh.min(axis=1)
    df["office_metro_km"] = dw.min(axis=1)
    df["home_metro"] = st["stop_name"].to_numpy()[ih]
    df["office_metro"] = st["stop_name"].to_numpy()[iw]
    df["metro_ride_km"] = _hav(st["stop_lat"].to_numpy()[ih], st["stop_lon"].to_numpy()[ih],
                               st["stop_lat"].to_numpy()[iw], st["stop_lon"].to_numpy()[iw]) * 1.2
    df["metro_eligible"] = (df["home_metro_km"] <= METRO_CATCHMENT_KM) & \
                           (df["office_metro_km"] <= METRO_CATCHMENT_KM) & (df["metro_ride_km"] >= 2)

    times = []
    for row in df.itertuples(index=False):
        if row.baseline_mode == "metro":
            times.append(_metro_trip(row, False, 1.0)[0])
        else:
            times.append(_trip(row.baseline_mode, row.road_km)[0])
    h, m = map(int, start_time.split(":"))
    df["baseline_min"] = np.round(times, 1)
    df["departure_minutes"] = (h * 60 + m - np.round(times)).astype(int)
    df["departure_time"] = [f"{x // 60:02d}:{x % 60:02d}" for x in df["departure_minutes"]]
    k = int(min(15, max(2, df["ward_no"].nunique() // 3)))
    km = KMeans(n_clusters=k, n_init=10, random_state=42).fit(df[["home_lat", "home_lon"]].to_numpy())
    df["cluster_id"] = km.labels_
    return df


@lru_cache(maxsize=4096)
def _trip(mode: str, km: float, extra: float = 0.0, occupancy: float = 1.0,
          rain: bool = False, transit_fare_mult: float = 1.0, ride_mult: float = 1.0) -> tuple:
    """(minutes, cost_inr per person, co2e_kg per person, vehicles) for one one-way trip."""
    km = round(float(km), 1)
    road_slow = 1.15 if rain else 1.0
    if mode == "walk":
        return km / SPEED_KMH["walk"] * 60, 0.0, 0.0, 0.0
    if mode == "bicycle":
        return km / SPEED_KMH["bicycle"] * 60 + OVERHEAD_MIN["bicycle"], 0.0, 0.0, 0.0
    if mode in ("car", "two_wheeler"):
        cat = "car_petrol" if mode == "car" else "two_wheeler_petrol"
        t = km / SPEED_KMH[mode] * 60 * road_slow + OVERHEAD_MIN[mode]
        return t, fuel_cost(km, cat)["amount_inr"], E.road_vehicle(km, cat).estimate_kg_co2e, 1.0
    if mode == "carpool":
        dist = km + extra
        t = dist / SPEED_KMH["car"] * 60 * road_slow + OVERHEAD_MIN["carpool"]
        cost = fuel_cost(dist, "car_petrol")["amount_inr"] / occupancy
        co2 = E.road_vehicle(dist, "car_petrol", occupancy=occupancy).estimate_kg_co2e
        return t, cost, co2, 1.0 / occupancy
    if mode == "auto":
        t = km / SPEED_KMH["auto"] * 60 * road_slow + OVERHEAD_MIN["auto"]
        fare = estimate_auto_fare(km)["estimated_total_inr"] * ride_mult
        co2 = E.road_vehicle(km * RIDE_HAIL_DEADHEAD, "auto_cng").estimate_kg_co2e
        return t, fare, co2, 1.0
    if mode == "cab":
        t = km / SPEED_KMH["cab"] * 60 * road_slow + OVERHEAD_MIN["cab"]
        fare = estimate_cab_fare(km, "up_to_10_lakh")["estimated_total_inr"] * ride_mult
        co2 = E.road_vehicle(km * RIDE_HAIL_DEADHEAD, "cab_diesel").estimate_kg_co2e
        return t, fare, co2, 1.0
    if mode == "bus":
        t = km / SPEED_KMH["bus"] * 60 * road_slow + OVERHEAD_MIN["bus"]
        return t, bmtc_fare_for(km) * transit_fare_mult, E.transit(km, "bmtc_bus").estimate_kg_co2e, 0.0
    if mode == "shuttle":
        t = km / SPEED_KMH["shuttle"] * 60 * road_slow + OVERHEAD_MIN["shuttle"]
        return t, 0.0, 0.0, 0.0   # shuttle cost/CO2e are accounted per vehicle, not per rider
    raise ValueError(mode)


def _metro_trip(row, rain, fare_mult):
    access = row.home_metro_km * 1.3
    egress = row.office_metro_km * 1.3
    walk_min = (access + egress) / SPEED_KMH["walk"] * 60 / (0.8 if rain else 1.0)
    ride_km = max(1.0, row.metro_ride_km)
    t = walk_min + ride_km / SPEED_KMH["metro"] * 60 + OVERHEAD_MIN["metro"]
    fare = estimate_metro_fare(ride_km)["smart_card_qr_fare_inr"] * fare_mult
    co2 = E.transit(ride_km, "metro").estimate_kg_co2e
    return t, fare, co2, 0.0


# ---------------------------------------------------------------------------
# Scenario assignment
# ---------------------------------------------------------------------------
DEFAULT_SCENARIO = {
    "metro_shift_pct": 0.0,
    "carpool_pct": 0.0,
    "shuttle_count": 0,
    "shuttle_capacity": 40,
    "ride_hailing_price_change_pct": 0.0,
    "transit_fare_change_pct": 0.0,
    "rain": False,
    "office_zone": None,          # office preset id or name (default: first preset)
    "headcount": DEFAULT_HEADCOUNT,
    "start_time": DEFAULT_START,
    "max_carpool_occupancy": 4,
}


def _form_carpools(df: pd.DataFrame, candidates: np.ndarray, max_occ: int):
    """Greedy disjoint carpool groups: a car-owning driver + up to max_occ-1 riders
    with nearby homes (<=2.5 km), same office zone (<=2 km) and departures within
    30 minutes. Returns list of (driver_idx, [rider_idx...], extra_km)."""
    cand = df.loc[candidates]
    groups = []
    used = set()
    drivers = cand[cand["owns_car"]].sort_values("departure_minutes")
    for di, d in drivers.iterrows():
        if di in used:
            continue
        pool = cand[(~cand.index.isin(used)) & (cand.index != di) &
                    (cand["office_zone"] == d["office_zone"])]
        if pool.empty:
            continue
        og = _hav(d["home_lat"], d["home_lon"], pool["home_lat"].to_numpy(), pool["home_lon"].to_numpy())
        dg = _hav(d["office_lat"], d["office_lon"], pool["office_lat"].to_numpy(), pool["office_lon"].to_numpy())
        tg = np.abs(pool["departure_minutes"].to_numpy() - d["departure_minutes"])
        ok = (og <= 2.5) & (dg <= 2.0) & (tg <= 30)
        if not ok.any():
            continue
        sel = pool.index.to_numpy()[ok][np.argsort(og[ok])][: max_occ - 1]
        extra = float(np.sort(og[ok])[: max_occ - 1].sum()) * ROAD_CIRCUITY
        groups.append((di, list(sel), extra))
        used.add(di)
        used.update(sel.tolist())
    return groups


def simulate(scenario: dict | None = None, include_employees: bool = False) -> dict:
    sc = {**DEFAULT_SCENARIO, **(scenario or {})}
    for k in ("metro_shift_pct", "carpool_pct"):
        if not 0 <= float(sc[k]) <= 100:
            raise ValueError(f"{k} must be between 0 and 100")
    if int(sc["shuttle_count"]) < 0 or int(sc["shuttle_capacity"]) < 1:
        raise ValueError("shuttle_count must be >= 0 and shuttle_capacity >= 1")

    base = population(sc["office_zone"] or None, int(sc["headcount"]), str(sc["start_time"]))
    rng = np.random.default_rng(7)
    df = base.copy()
    df["mode"] = df["baseline_mode"]
    df["occupancy"] = 1.0
    df["extra_km"] = 0.0
    log = []

    rain = bool(sc["rain"])
    if rain:
        wet = df.index[df["mode"].isin(["walk", "bicycle"]) & (df["commute_distance_km"] > 1.5)]
        move = rng.random(len(wet)) < 0.35
        df.loc[wet[move], "mode"] = np.where(rng.random(move.sum()) < 0.5, "auto", "bus")
        log.append(f"Rain: {int(move.sum())} walk/cycle commuters switched to auto or bus")

    # Ride-hailing price elasticity
    rh = float(sc["ride_hailing_price_change_pct"])
    if rh:
        idx = df.index[df["mode"].isin(["auto", "cab"])]
        if rh > 0:
            p_leave = min(0.9, -ELASTICITY["ride_hailing_price"] * rh / 100)
            leave = idx[rng.random(len(idx)) < p_leave]
            alt = np.where(df.loc[leave, "metro_eligible"], "metro", "bus")
            df.loc[leave, "mode"] = alt
            log.append(f"Ride-hailing +{rh:g}%: {len(leave)} auto/cab users moved to bus/Metro (elasticity -0.4)")
        else:
            src = df.index[df["mode"].isin(["bus", "metro"])]
            p_join = min(0.5, -ELASTICITY["ride_hailing_price"] * (-rh) / 100 * 0.3)
            join = src[rng.random(len(src)) < p_join]
            df.loc[join, "mode"] = "auto"
            log.append(f"Ride-hailing {rh:g}%: {len(join)} transit users moved to auto")

    # Transit fare elasticity (applied to existing transit riders)
    tf = float(sc["transit_fare_change_pct"])
    if tf:
        idx = df.index[df["mode"].isin(["bus", "metro"])]
        p = min(0.9, abs(ELASTICITY["transit_fare"] * tf / 100))
        moved = idx[rng.random(len(idx)) < p]
        if tf > 0:
            df.loc[moved, "mode"] = "two_wheeler"
            log.append(f"Transit fare +{tf:g}%: {len(moved)} riders moved to two-wheeler (elasticity -0.22, Namma Metro Feb 2025 fare hike)")
        else:
            cars = df.index[df["mode"].isin(["car", "two_wheeler"]) & df["metro_eligible"]]
            gain = cars[rng.random(len(cars)) < p]
            df.loc[gain, "mode"] = "metro"
            log.append(f"Transit fare {tf:g}%: {len(gain)} drivers near Metro moved to Metro")

    # Metro shift
    ms = float(sc["metro_shift_pct"]) / 100
    if ms > 0:
        elig = df.index[df["mode"].isin(["car", "two_wheeler", "auto", "cab"]) & df["metro_eligible"]]
        n = int(round(len(elig) * ms))
        chosen = rng.choice(elig, size=n, replace=False) if n else []
        df.loc[chosen, "mode"] = "metro"
        log.append(f"Metro shift {ms:.0%}: {n} of {len(elig)} eligible road commuters (home & office within "
                   f"{METRO_CATCHMENT_KM} km of a station) moved to Metro")

    # Shuttles: densest home-cluster x office-zone corridors first
    shuttle_stats = []
    sh_n, cap = int(sc["shuttle_count"]), int(sc["shuttle_capacity"])
    if sh_n > 0:
        pool = df[df["mode"].isin(["car", "two_wheeler", "auto", "cab", "bus"])]
        corridors = pool.groupby(["cluster_id", "office_zone"]).size().sort_values(ascending=False)
        remaining = sh_n
        for (cid, oz), size in corridors.items():
            if remaining <= 0:
                break
            members = pool[(pool["cluster_id"] == cid) & (pool["office_zone"] == oz)]
            members = members.sort_values("departure_minutes")
            # One shuttle per `cap` riders on this corridor, within remaining fleet.
            n_sh = min(remaining, max(1, int(math.ceil(len(members) * 0.6 / cap))))
            take = members.index[: n_sh * cap]
            # Adoption: 60 % of corridor commuters are willing to use a shuttle.
            willing = take[rng.random(len(take)) < 0.6][: n_sh * cap]
            if len(willing) == 0:
                continue
            df.loc[willing, "mode"] = "shuttle"
            route_km = float(members["road_km"].median()) + 6.0     # + pickup loop
            shuttle_stats.append({"cluster_id": int(cid), "office_zone": oz, "shuttles": n_sh,
                                  "riders": int(len(willing)), "route_km": round(route_km, 1),
                                  "utilisation": round(len(willing) / (n_sh * cap), 3)})
            remaining -= n_sh
        log.append(f"Shuttles: {sh_n - remaining} deployed on {len(shuttle_stats)} corridors")

    # Carpools
    cp = float(sc["carpool_pct"]) / 100
    groups = []
    if cp > 0:
        cand = df.index[df["mode"].isin(["car", "two_wheeler", "auto", "cab"])]
        all_groups = _form_carpools(df, cand.to_numpy(), int(sc["max_carpool_occupancy"]))
        k = int(round(len(all_groups) * cp))
        groups = all_groups[:k]
        for driver, riders, extra in groups:
            occ = 1 + len(riders)
            members = [driver] + riders
            df.loc[members, "mode"] = "carpool"
            df.loc[members, "occupancy"] = occ
            df.loc[driver, "extra_km"] = extra
            df.loc[riders, "extra_km"] = extra
        log.append(f"Carpool {cp:.0%}: {k} of {len(all_groups)} feasible groups formed "
                   f"({sum(1 + len(r) for _, r, _ in groups)} employees)")

    ride_mult = 1 + rh / 100
    fare_mult = 1 + tf / 100

    def evaluate(frame, mode_col, occ_col=None, extra_col=None, r=False, fm=1.0, rm=1.0):
        t = np.zeros(len(frame)); c = np.zeros(len(frame)); e = np.zeros(len(frame)); v = np.zeros(len(frame))
        for i, row in enumerate(frame.itertuples(index=False)):
            m = getattr(row, mode_col)
            if m == "metro":
                res = _metro_trip(row, r, fm)
            else:
                res = _trip(m, row.road_km, getattr(row, extra_col) if extra_col else 0.0,
                            getattr(row, occ_col) if occ_col else 1.0, r, fm, rm)
            t[i], c[i], e[i], v[i] = res
        return t, c, e, v

    bt, bc, be, bv = evaluate(base, "baseline_mode")
    st_, sc_, se, sv = evaluate(df, "mode", "occupancy", "extra_km", rain, fare_mult, ride_mult)

    # Shuttle fleet emissions/cost (operator side), per vehicle.
    shuttle_vkm = sum(s["shuttles"] * s["route_km"] for s in shuttle_stats)
    shuttle_co2 = E.road_vehicle(shuttle_vkm, "shuttle_diesel").vehicle_trip_kg_co2e if shuttle_vkm else 0.0
    shuttle_cost = shuttle_vkm * SHUTTLE_COST_PER_VKM_INR
    shuttle_vehicles = sum(s["shuttles"] for s in shuttle_stats)

    def summary(t, c, e, v, modes, extra_co2=0.0, extra_cost=0.0, extra_veh=0.0, occupancy=None):
        n = len(modes)
        share = pd.Series(modes).value_counts()
        car_like = pd.Series(modes).isin(["car", "carpool"])
        occ = float(np.mean(occupancy[car_like.to_numpy()])) if occupancy is not None and car_like.any() else 1.0
        one_way_co2 = float(e.sum()) + extra_co2
        one_way_cost = float(c.sum()) + extra_cost
        return {
            "employees": n,
            "one_way": {"co2e_kg": round(one_way_co2, 1), "commuter_cost_inr": round(float(c.sum()), 0),
                        "operator_cost_inr": round(extra_cost, 0), "total_cost_inr": round(one_way_cost, 0)},
            "daily_round_trip": {"co2e_kg": round(one_way_co2 * 2, 1), "total_cost_inr": round(one_way_cost * 2, 0)},
            "annual": {"co2e_tonnes": round(one_way_co2 * 2 * WORKING_DAYS_PER_YEAR / 1000, 1),
                       "total_cost_inr_lakh": round(one_way_cost * 2 * WORKING_DAYS_PER_YEAR / 1e5, 1)},
            "vehicles_on_road": int(round(float(v.sum()) + extra_veh)),
            "avg_commute_min": round(float(t.mean()), 1),
            "avg_co2e_per_employee_kg": round(one_way_co2 / max(1, n), 3),
            "avg_car_occupancy": round(occ, 2),
            "mode_share": {MODE_LABELS[m]: {"count": int(share.get(m, 0)),
                                            "share": round(float(share.get(m, 0)) / max(1, n), 4)}
                           for m in MODES if share.get(m, 0)},
        }

    baseline = summary(bt, bc, be, bv, base["baseline_mode"].tolist())
    scenario_res = summary(st_, sc_, se, sv, df["mode"].tolist(), shuttle_co2, shuttle_cost,
                           shuttle_vehicles, df["occupancy"].to_numpy())

    def delta(a, b):
        return {"abs": round(b - a, 2), "pct": round((b - a) / a * 100, 2) if a else None}

    comparison = {
        "co2e_kg_one_way": delta(baseline["one_way"]["co2e_kg"], scenario_res["one_way"]["co2e_kg"]),
        "annual_co2e_tonnes": delta(baseline["annual"]["co2e_tonnes"], scenario_res["annual"]["co2e_tonnes"]),
        "total_cost_inr_one_way": delta(baseline["one_way"]["total_cost_inr"], scenario_res["one_way"]["total_cost_inr"]),
        "vehicles_on_road": delta(baseline["vehicles_on_road"], scenario_res["vehicles_on_road"]),
        "avg_commute_min": delta(baseline["avg_commute_min"], scenario_res["avg_commute_min"]),
    }

    switched = int((df["mode"] != base["baseline_mode"]).sum())
    carpool_members = sum(1 + len(r) for _, r, _ in groups)
    result = {
        "simulation_type": "organisation_commute_digital_twin_v2",
        "scenario": sc,
        "baseline": baseline,
        "scenario_result": scenario_res,
        "comparison": comparison,
        "employees_switched": switched,
        "carpool": {"groups": len(groups), "employees": carpool_members,
                    "avg_occupancy": round(carpool_members / len(groups), 2) if groups else None,
                    "seat_utilisation": round(carpool_members / (len(groups) * int(sc["max_carpool_occupancy"])), 3)
                    if groups else None},
        "shuttle": {"deployed": shuttle_vehicles, "capacity": cap, "corridors": shuttle_stats,
                    "riders": int(sum(s["riders"] for s in shuttle_stats)),
                    "utilisation": round(sum(s["riders"] for s in shuttle_stats) / (shuttle_vehicles * cap), 3)
                    if shuttle_vehicles else None,
                    "fleet_co2e_kg_one_way": round(shuttle_co2, 1), "operator_cost_inr_one_way": round(shuttle_cost, 0)},
        "metro": {"eligible_employees": int(base["metro_eligible"].sum()),
                  "catchment_km": METRO_CATCHMENT_KM},
        "events": log,
        "assumptions": [
            "Population: Census 2011 ward populations re-weighted to the B-28 distance-to-work distribution; "
            "baseline modes are B-28 mode-by-distance shares, apportioned deterministically (no random sampling).",
            "Carpool candidates are all road commuters with compatible homes, office and timing; the carpool "
            "percentage sets how many of the feasible groups form.",
            "Road distance = straight-line x 1.35. Corridor speeds (km/h): " +
            ", ".join(f"{k} {v:g}" for k, v in SPEED_KMH.items()) + ".",
            "Ride-hailing emissions include a 30 % dead-heading (empty km) uplift.",
            "Price elasticities: transit fare -0.22 (Namma Metro fare hike of Feb 2025: ~46 % rise, ~10 % fewer riders); ride-hailing -0.4 (literature-range assumption).",
            "Shuttle adoption 60 % of corridor commuters (assumption); shuttle cost Rs 62/vehicle-km (KSRTC ordinary bus hire rate, Nov 2026).",
            "Per-trip CO2e and costs use the same functions as the journey recommender.",
            f"Annual figures assume {WORKING_DAYS_PER_YEAR} working days, round trip.",
        ],
        "population": describe_population(base),
    }
    if include_employees:
        cols = ["employee_id", "home_zone", "office_zone", "commute_distance_km", "baseline_mode"]
        out = base[cols].copy()
        out["scenario_mode"] = df["mode"].values
        out["baseline_min"], out["scenario_min"] = np.round(bt, 1), np.round(st_, 1)
        out["baseline_co2e_kg"], out["scenario_co2e_kg"] = np.round(be, 3), np.round(se, 3)
        result["employees"] = out[out["baseline_mode"] != out["scenario_mode"]].head(500).to_dict("records")
    return result


def preset_scenarios() -> list[dict]:
    return [
        {"id": "metro20", "name": "20 % of eligible drivers to Metro", "scenario": {"metro_shift_pct": 20}},
        {"id": "carpool30", "name": "30 % carpool adoption", "scenario": {"carpool_pct": 30}},
        {"id": "shuttle10", "name": "10 company shuttles", "scenario": {"shuttle_count": 10}},
        {"id": "ridehail+25", "name": "Ride-hailing price +25 %", "scenario": {"ride_hailing_price_change_pct": 25}},
        {"id": "rainy", "name": "Rainy day", "scenario": {"rain": True}},
        {"id": "combined", "name": "Combined policy", "scenario": {"metro_shift_pct": 20, "carpool_pct": 30,
                                                                     "shuttle_count": 10}},
    ]
