"""Metro journeys with a motorised first or last mile.

The walk + Metro planner rejects trips where a station is too far to walk to,
e.g. JP Nagar -> Whitefield IT Zone, where the nearest Purple Line station
is 2.5-3 km from the offices. Real commuters bridge that gap with an auto or
a Metro feeder bus. This module builds those journeys from real data:

* Metro legs: the BMRCL GTFS timetable (metro_planner.plan_metro), boarded at
  the time the commuter actually reaches the station.
* Feeder bus: a real BMTC GTFS search from the exit station, starting when the
  train arrives (airport express routes excluded).
* Auto: Namma Yatri distance fare x hourly price pressure, pickup wait from
  the demand/supply model, road time from the time-of-day traffic profile.

Every combination goes through the same filters and ranking as other options.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta

from app.services import emissions as E
from app.services.context import haversine_km, traffic_profile, ROAD_CIRCUITY, FREE_FLOW_KMH
from app.services.places import metro_stations, stop_point, stops_path, metro_line_info

WALK_M_PER_MIN = 80
WALK_MAX_STRAIGHT_KM = 0.9        # walk to/from a station when it is this close
MOTORISED_MAX_KM = 7.0            # do not consider stations further than this
STATIONS_PER_SIDE = 2
STATION_ENTRY_MIN = 3             # security check + platform
STATION_EXIT_MIN = 2
RIDE_HAIL_DEADHEAD = 1.30
MAX_FEEDER_BUS_LEGS = 2


def _nearest_stations(lat, lon, k=STATIONS_PER_SIDE, max_km=MOTORISED_MAX_KM):
    st = metro_stations()
    rows = []
    for r in st.itertuples(index=False):
        d = haversine_km(lat, lon, r.stop_lat, r.stop_lon)
        if d <= max_km:
            rows.append((d, r.stop_id, r.stop_name, r.stop_lat, r.stop_lon))
    rows.sort()
    return rows[:k]


def _hhmm(dt: datetime) -> str:
    if dt.second or dt.microsecond:
        dt = dt.replace(second=0, microsecond=0) + timedelta(minutes=1)
    return dt.strftime("%H:%M")


def _auto_leg(a, b, when, market, label):
    """(minutes incl. pickup wait, fare dict, emissions, leg dict) for an auto ride."""
    from app.routing.namma_yatri_fares import estimate_auto_fare
    km = max(0.8, haversine_km(a["lat"], a["lon"], b["lat"], b["lon"]) * ROAD_CIRCUITY)
    congestion = traffic_profile(when)["congestion_multiplier"]
    ride = km / FREE_FLOW_KMH["taxi"] * 60 * congestion
    wait = market["expected_pickup_wait_min"]
    fare = estimate_auto_fare(km)
    pressure = market["price_pressure_multiplier"]
    em = E.road_vehicle(km * RIDE_HAIL_DEADHEAD, "auto_cng", 1, None, congestion)
    leg = {"type": "auto", "label": label, "from": a, "to": b, "distance_km": round(km, 2),
           "duration_min": round(ride + wait, 1), "wait_before_min": round(wait, 1),
           "path": [[a["lat"], a["lon"]], [b["lat"], b["lon"]]]}
    return ride + wait, {"base": fare["estimated_total_inr"], "amount": fare["estimated_total_inr"] * pressure,
                         "pressure": pressure, "km": km}, em, leg


def _walk_leg(a, b, segment):
    m = haversine_km(a["lat"], a["lon"], b["lat"], b["lon"]) * 1000 * 1.3
    return m / WALK_M_PER_MIN, {"type": "walk", "segment": segment, "from": a, "to": b,
                                "distance_m": round(m), "duration_min": round(m / WALK_M_PER_MIN, 1),
                                "path": [[a["lat"], a["lon"]], [b["lat"], b["lon"]]]}


def _metro_km(legs):
    km = 0.0
    for leg in legs:
        pts = stops_path(leg.get("stop_ids") or [], "metro")
        for (a, b) in zip(pts, pts[1:]):
            km += haversine_km(a[0], a[1], b[0], b[1])
    return km * 1.05


def build_metro_combos(origin, destination, travel_date, departure_time, market, existing_metro, builder_ctx):
    """Return Option dicts for Auto+Metro, Metro+Auto and Metro+Feeder bus journeys.

    builder_ctx supplies recommender helpers (to avoid an import cycle):
    _option, _transit_cost, _transit_leg, _normalise_legs.
    """
    from app.routing.metro_planner import plan_metro
    from app.routing.metro_fares import estimate_metro_fare
    from app.routing.bmtc_latest_planner import plan_bmtc_latest_from_gps
    from app.routing.journey_adapters import adapt_bmtc_journeys
    from app.routing.bmtc_fares import calculate_bmtc_journey_fare
    from app.services.carbon import calculate_bmtc_journey_distance

    _option = builder_ctx["_option"]
    _transit_cost = builder_ctx["_transit_cost"]
    _transit_leg = builder_ctx["_transit_leg"]
    _normalise_legs = builder_ctx["_normalise_legs"]

    t0 = datetime.strptime(f"{travel_date} {departure_time}", "%Y-%m-%d %H:%M")
    o_pt = {"name": "Your location", "lat": origin[0], "lon": origin[1]}
    d_pt = {"name": "Destination", "lat": destination[0], "lon": destination[1]}
    direct_km = haversine_km(*origin, *destination)
    if direct_km < 4:
        return [], []

    o_st = _nearest_stations(*origin)
    d_st = _nearest_stations(*destination)
    out, notes = [], []
    tried = set()
    for (od, oid, oname, olat, olon) in o_st:
        for (dd, did, dname, dlat, dlon) in d_st:
            if oid == did or (oid, did) in tried:
                continue
            tried.add((oid, did))
            access_walk, egress_walk = od <= WALK_MAX_STRAIGHT_KM, dd <= WALK_MAX_STRAIGHT_KM
            if access_walk and egress_walk:
                continue                      # plain walk + Metro: handled by the main planner
            if od + dd > 0.6 * direct_km:
                continue                      # the Metro would carry too little of the trip
            s_o = {"name": f"{oname} Metro", "lat": olat, "lon": olon}
            s_d = {"name": f"{dname} Metro", "lat": dlat, "lon": dlon}

            # First mile
            if access_walk:
                a_min, a_leg = _walk_leg(o_pt, s_o, "origin_access")
                a_cost, a_em, a_label = None, None, "Walk"
            else:
                a_min, a_cost, a_em, a_leg = _auto_leg(o_pt, s_o, t0, market, "Auto to Metro")
                a_label = "Auto"
            board_at = t0 + timedelta(minutes=a_min + STATION_ENTRY_MIN)
            if board_at.date() != t0.date():
                continue
            try:
                m = plan_metro(oname, dname, travel_date, _hhmm(board_at))
            except Exception as exc:
                notes.append(f"{oname}->{dname}: {exc}")
                continue
            if m.get("status") != "success" or not m.get("legs"):
                continue
            arr = datetime.strptime(f"{travel_date} {m['arrival'][:5]}", "%Y-%m-%d %H:%M")
            at_exit = arr + timedelta(minutes=STATION_EXIT_MIN)
            metro_legs = []
            for leg in m["legs"]:
                tl = _transit_leg(leg, "metro")
                metro_legs.append(tl)
            metro_km = _metro_km(m["legs"])
            fare = estimate_metro_fare(metro_km)
            metro_transfers = len(m["legs"]) - 1

            # Last-mile variants
            variants = []
            if egress_walk:
                e_min, e_leg = _walk_leg(s_d, d_pt, "destination_egress")
                variants.append(("walk", e_min, [e_leg], None, None, 0, 0.0))
            else:
                e_min, e_cost, e_em, e_leg = _auto_leg(s_d, d_pt, at_exit, market, "Auto from Metro")
                variants.append(("auto", e_min, [e_leg], e_cost, e_em, 0, 0.0))
                try:
                    fb = plan_bmtc_latest_from_gps(dlat, dlon, destination[0], destination[1],
                                                   travel_date, _hhmm(at_exit))
                except Exception as exc:
                    fb = {"status": "error", "message": str(exc)}
                if fb.get("status") == "success":
                    for j in adapt_bmtc_journeys(fb)[:2]:
                        raw_legs = j["raw_details"].get("bmtc_journey", {}).get("legs", [])
                        if not raw_legs or len(raw_legs) > MAX_FEEDER_BUS_LEGS:
                            continue
                        if any(str(l.get("route_short_name", "")).upper().startswith("KIA") for l in raw_legs):
                            continue
                        bus_km = calculate_bmtc_journey_distance(raw_legs)
                        if bus_km.get("status") != "success":
                            continue
                        bfare = calculate_bmtc_journey_fare(raw_legs)
                        legs = _normalise_legs(j, (dlat, dlon), destination)
                        if legs and legs[0]["type"] == "walk":
                            legs[0]["from"]["name"] = s_d["name"]
                        variants.append(("bus", j["duration_minutes"], legs,
                                         bfare.get("total_fare_inr") if bfare.get("status") == "success" else None,
                                         E.transit(bus_km["distance_km"], "bmtc_bus"), len(raw_legs),
                                         bus_km["distance_km"]))
                        break

            for kind, e_min, e_legs, e_cost, e_em, bus_legs, bus_km in variants:
                total = (at_exit - t0).total_seconds() / 60 + e_min
                legs = [a_leg] + metro_legs + e_legs
                parts = [E.transit(metro_km, "metro")]
                cost_amount, cost_lo, cost_hi = fare["smart_card_qr_fare_inr"], fare["smart_card_qr_fare_inr"], fare["token_fare_inr"]
                detail = {"metro_smart_card_qr_inr": fare["smart_card_qr_fare_inr"], "metro_token_inr": fare["token_fare_inr"]}
                sources = ["BMRCL Metro GTFS (scheduled)"]
                if a_em is not None:
                    parts.append(a_em)
                    cost_amount += a_cost["amount"]; cost_lo += a_cost["base"]; cost_hi += a_cost["amount"] * 1.1
                    detail["first_mile_auto_inr"] = round(a_cost["amount"], 2)
                    sources.append("Namma Yatri auto fare model")
                if kind == "auto":
                    parts.append(e_em)
                    cost_amount += e_cost["amount"]; cost_lo += e_cost["base"]; cost_hi += e_cost["amount"] * 1.1
                    detail["last_mile_auto_inr"] = round(e_cost["amount"], 2)
                    if "Namma Yatri auto fare model" not in sources:
                        sources.append("Namma Yatri auto fare model")
                elif kind == "bus":
                    parts.append(e_em)
                    if e_cost is None:
                        cost_amount = None
                    else:
                        cost_amount += e_cost; cost_lo += e_cost; cost_hi += e_cost
                        detail["feeder_bus_inr"] = e_cost
                    sources.append("BMTC GTFS 2026-27 (feeder bus)")
                first = "Auto" if a_em is not None else "Walk"
                last = {"walk": "Walk", "auto": "Auto", "bus": "Feeder bus"}[kind]
                title = " + ".join(x for x in ([("Auto" if first == "Auto" else None), "Metro",
                                                 (last if last != "Walk" else None)]) if x)
                transfers = metro_transfers + (1 if kind == "bus" else 0) + max(0, bus_legs - 1) \
                    + (1 if first == "Auto" else 0) + (1 if kind == "auto" else 0)
                limitations = ["Metro times are scheduled (GTFS).",
                               "Auto legs are modelled estimates, not booking quotes." if (first == "Auto" or kind == "auto") else None,
                               "Feeder bus times are scheduled (GTFS)." if kind == "bus" else None,
                               "Walks to/from stations are straight-line x 1.3 estimates."]
                opt = _option("metro_combo", legs, total,
                              _transit_cost(cost_amount, "fare", cost_lo if cost_amount is not None else None,
                                            cost_hi if cost_amount is not None else None, detail),
                              E.combine(parts), metro_km + bus_km + (a_cost["km"] if a_cost else 0)
                              + (e_cost["km"] if kind == "auto" else 0),
                              transfers, sources, [l for l in limitations if l], False,
                              {"transit_km": {"metro": round(metro_km, 2), "bus": round(bus_km, 2)},
                               "first_mile": first.lower(), "last_mile": kind,
                               "availability": None})
                opt["title"] = title
                opt.pop("availability")
                out.append(opt)
    return out, notes
