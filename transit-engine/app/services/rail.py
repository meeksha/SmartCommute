"""Indian Railways trains between Bengaluru and Tumakuru.

Real timetable data only (data/external/rail, see its README): daily MEMU,
passenger and express trains with the stop times published by etrain.info /
erail.in, and station coordinates with a documented source for each.

A rail journey is built as: first mile (walk, auto, or Metro inside
Bengaluru) -> train -> last mile (walk, auto, BMTC feeder bus or Metro).
Trains are boarded only at stations where the published timetable has a
time for that train.
"""
from __future__ import annotations

import csv
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path

from app.services import emissions as E
from app.services.context import haversine_km

RAIL_DIR = Path("data/external/rail")

# Route km from KSR Bengaluru (from the MEMU schedules' distance column).
STATION_KM = {"SBC": 0, "MWM": 3, "YPR": 5, "BAW": 14, "SDVL": 17, "BNKH": 33, "DBL": 38,
              "NDV": 47, "DBS": 50, "HHL": 59, "KIAT": 65, "TK": 71}
WALK_MAX_KM = 0.9            # straight-line distance treated as walkable to a station
ACCESS_MAX_KM = 15.0         # consider stations up to this far (auto / Metro / bus access)
STATIONS_PER_SIDE = 3
STATION_BUFFER_MIN = 7       # buy an unreserved ticket and reach the platform
STATION_EXIT_MIN = 4
FULL_FARE_INR = 20.0         # unreserved, SBC -> TK (71 km), etrain.info fare calculator
MIN_FARE_INR = 10.0          # Indian Railways minimum fare for short MEMU hops
KIND_LABEL = {"memu": "MEMU", "passenger": "Passenger", "express": "Express"}


@lru_cache(maxsize=1)
def stations() -> dict:
    with open(RAIL_DIR / "stations.csv", newline="", encoding="utf-8") as f:
        return {r["code"]: {"code": r["code"], "name": r["name"], "lat": float(r["lat"]), "lon": float(r["lon"]),
                            "source": r["coord_source"]} for r in csv.DictReader(f)}


def _t(s: str | None):
    return None if not s else int(s[:2]) * 60 + int(s[3:5])


@lru_cache(maxsize=1)
def trains() -> list[dict]:
    out = []
    with open(RAIL_DIR / "trains.csv", newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            stops = []
            for part in r["stops"].split("|"):
                code, times = part.strip().split(" ", 1)
                arr, dep = times.split("-")
                stops.append({"code": code, "arr": _t(arr), "dep": _t(dep)})
            out.append({"no": r["train_no"], "name": r["name"], "kind": r["kind"], "direction": r["direction"],
                        "days": r["days"], "stops": stops, "source": r["source"]})
    return out


def fare_for(km: float, kind: str) -> dict:
    if km >= 60:
        lo = hi = FULL_FARE_INR
        amount = FULL_FARE_INR
    else:
        lo, hi, amount = MIN_FARE_INR, FULL_FARE_INR, MIN_FARE_INR
    note = "Unreserved second-class fare."
    if kind == "express":
        hi = None
        note = ("Express fares vary by class and aren't published per segment; "
                "the ordinary unreserved fare is shown as a lower bound.")
    return {"amount": amount, "low": lo, "high": hi, "note": note}


def nearest_stations(lat, lon, k=STATIONS_PER_SIDE, max_km=ACCESS_MAX_KM):
    rows = sorted((haversine_km(lat, lon, s["lat"], s["lon"]), code) for code, s in stations().items())
    return [(d, code) for d, code in rows if d <= max_km][:k]


def corridor_relevant(origin, destination) -> bool:
    """Rail is worth trying when both ends have a station within reach and the trip is long enough."""
    if haversine_km(*origin, *destination) < 8:
        return False
    return bool(nearest_stations(*origin)) and bool(nearest_stations(*destination))


def find_trains(o_code: str, d_code: str, ready_min: int) -> list[dict]:
    """Daily trains stopping at o_code then d_code, departing at or after ready_min (minutes after midnight)."""
    res = []
    for tr in trains():
        codes = [s["code"] for s in tr["stops"]]
        if o_code not in codes or d_code not in codes:
            continue
        i, j = codes.index(o_code), codes.index(d_code)
        if i >= j:
            continue
        a, b = tr["stops"][i], tr["stops"][j]
        dep = a["dep"]
        arr = b["arr"] if b["arr"] is not None else b["dep"]
        if dep is None or arr is None or dep < ready_min:
            continue
        if arr < dep:
            arr += 24 * 60
        res.append({"train": tr, "board": a, "alight": b, "dep": dep, "arr": arr,
                    "stops_between": tr["stops"][i:j + 1]})
    res.sort(key=lambda x: x["arr"])
    return res


def train_leg(hit, date_str: str) -> dict:
    st = stations()
    tr = hit["train"]
    path = [[st[s["code"]]["lat"], st[s["code"]]["lon"]] for s in hit["stops_between"] if s["code"] in st]
    km = abs(STATION_KM[hit["alight"]["code"]] - STATION_KM[hit["board"]["code"]])

    def hhmm(m):
        m %= 24 * 60
        return f"{m // 60:02d}:{m % 60:02d}"

    a, b = st[hit["board"]["code"]], st[hit["alight"]["code"]]
    return {
        "type": "train",
        "label": f"{KIND_LABEL[tr['kind']]} {tr['no']}",
        "route": tr["no"],
        "route_long_name": tr["name"],
        "color": "#1864AB",
        "from": {"name": f"{a['name']} station", "lat": a["lat"], "lon": a["lon"], "stop_id": a["code"]},
        "to": {"name": f"{b['name']} station", "lat": b["lat"], "lon": b["lon"], "stop_id": b["code"]},
        "departure_time": hhmm(hit["dep"]),
        "arrival_time": hhmm(hit["arr"]),
        "duration_min": float(hit["arr"] - hit["dep"]),
        "stops_count": max(0, len(hit["stops_between"]) - 1),
        "distance_km": float(km),
        "path": path,
        "train_kind": tr["kind"],
        "timetable_source": tr["source"],
    }


def build_rail_options(origin, destination, travel_date, departure_time, market, builder_ctx):
    """Option dicts for rail journeys; empty when rail isn't relevant to the trip."""
    if not corridor_relevant(origin, destination):
        return [], []
    from app.services.metro_combos import _auto_leg, _walk_leg
    from app.routing.bmtc_latest_planner import plan_bmtc_latest_from_gps
    from app.routing.journey_adapters import adapt_bmtc_journeys
    from app.routing.bmtc_fares import calculate_bmtc_journey_fare
    from app.services.carbon import calculate_bmtc_journey_distance

    _option = builder_ctx["_option"]
    _transit_cost = builder_ctx["_transit_cost"]
    _normalise_legs = builder_ctx["_normalise_legs"]

    st = stations()
    t0 = datetime.strptime(f"{travel_date} {departure_time}", "%Y-%m-%d %H:%M")
    o_pt = {"name": "Your location", "lat": origin[0], "lon": origin[1]}
    d_pt = {"name": "Destination", "lat": destination[0], "lon": destination[1]}
    direct = haversine_km(*origin, *destination)
    out, notes = [], []
    for od, oc in nearest_stations(*origin):
        for dd, dc in nearest_stations(*destination):
            if oc == dc:
                continue
            rail_km = abs(STATION_KM[dc] - STATION_KM[oc])
            if rail_km < 0.5 * direct or od + dd > 0.6 * direct:
                continue          # the train would carry too little of the trip
            s_o = {"name": f"{st[oc]['name']} station", "lat": st[oc]["lat"], "lon": st[oc]["lon"]}
            s_d = {"name": f"{st[dc]['name']} station", "lat": st[dc]["lat"], "lon": st[dc]["lon"]}
            if od <= WALK_MAX_KM:
                a_min, a_leg = _walk_leg(o_pt, s_o, "origin_access")
                a_cost = a_em = None
            else:
                a_min, a_cost, a_em, a_leg = _auto_leg(o_pt, s_o, t0, market, "Auto to station")
            ready = t0 + timedelta(minutes=a_min + STATION_BUFFER_MIN)
            if ready.date() != t0.date():
                continue
            hits = find_trains(oc, dc, ready.hour * 60 + ready.minute)
            if not hits:
                notes.append(f"No later daily train today from {st[oc]['name']} to {st[dc]['name']}.")
                continue
            hit = hits[0]
            tleg = train_leg(hit, travel_date)
            tleg["wait_before_min"] = round(hit["dep"] - (ready.hour * 60 + ready.minute) + STATION_BUFFER_MIN, 1)
            arr_dt = datetime.combine(t0.date(), datetime.min.time()) + timedelta(minutes=hit["arr"] + STATION_EXIT_MIN)
            fare = fare_for(rail_km, hit["train"]["kind"])
            rail_em = E.transit(rail_km, "metro")
            rail_em.assumptions.append("Bengaluru-Tumakuru line is electrified; grid-electric rail factor "
                                       "(same lifecycle band as Metro).")

            variants = []
            if dd <= WALK_MAX_KM:
                e_min, e_leg = _walk_leg(s_d, d_pt, "destination_egress")
                variants.append(("walk", e_min, [e_leg], None, None, 0, 0.0))
            else:
                e_min, e_cost, e_em, e_leg = _auto_leg(s_d, d_pt, arr_dt, market, "Auto from station")
                variants.append(("auto", e_min, [e_leg], e_cost, e_em, 0, 0.0))
                try:
                    fb = plan_bmtc_latest_from_gps(s_d["lat"], s_d["lon"], destination[0], destination[1],
                                                   travel_date, arr_dt.strftime("%H:%M"))
                except Exception as exc:
                    fb = {"status": "error", "message": str(exc)}
                if fb.get("status") == "success" and arr_dt.date() == t0.date():
                    for j in adapt_bmtc_journeys(fb)[:2]:
                        raw = j["raw_details"].get("bmtc_journey", {}).get("legs", [])
                        if not raw or len(raw) > 2 or any(str(l.get("route_short_name", "")).upper()
                                                         .startswith("KIA") for l in raw):
                            continue
                        bk = calculate_bmtc_journey_distance(raw)
                        if bk.get("status") != "success":
                            continue
                        bf = calculate_bmtc_journey_fare(raw)
                        legs = _normalise_legs(j, (s_d["lat"], s_d["lon"]), destination)
                        if legs and legs[0]["type"] == "walk":
                            legs[0]["from"]["name"] = s_d["name"]
                        variants.append(("bus", j["duration_minutes"], legs,
                                         bf.get("total_fare_inr") if bf.get("status") == "success" else None,
                                         E.transit(bk["distance_km"], "bmtc_bus"), len(raw), bk["distance_km"]))
                        break

            for kind, e_min, e_legs, e_cost, e_em, bus_legs, bus_km in variants:
                total = (arr_dt - t0).total_seconds() / 60 + e_min
                parts = [rail_em]
                amount, lo = fare["amount"], fare["low"]
                hi = fare["high"]
                detail = {"train_fare_inr": fare["amount"], "train_fare_note": fare["note"]}
                sources = [f"Indian Railways timetable ({hit['train']['source']})"]
                if a_em is not None:
                    parts.append(a_em)
                    amount += a_cost["amount"]; lo += a_cost["base"]
                    hi = None if hi is None else hi + a_cost["amount"] * 1.1
                    detail["first_mile_auto_inr"] = round(a_cost["amount"], 2)
                    sources.append("Namma Yatri auto fare model")
                if kind == "auto":
                    parts.append(e_em)
                    amount += e_cost["amount"]; lo += e_cost["base"]
                    hi = None if hi is None else hi + e_cost["amount"] * 1.1
                    detail["last_mile_auto_inr"] = round(e_cost["amount"], 2)
                    if "Namma Yatri auto fare model" not in sources:
                        sources.append("Namma Yatri auto fare model")
                elif kind == "bus":
                    parts.append(e_em)
                    if e_cost is None:
                        amount = None
                    else:
                        amount += e_cost; lo += e_cost
                        hi = None if hi is None else hi + e_cost
                        detail["feeder_bus_inr"] = e_cost
                    sources.append("BMTC GTFS 2026-27 (feeder bus)")
                first = "Auto" if a_em is not None else None
                last = {"walk": None, "auto": "Auto", "bus": "Bus"}[kind]
                title = " + ".join(x for x in (first, "Train", last) if x)
                transfers = (1 if first else 0) + (1 if kind != "walk" else 0) + max(0, bus_legs - 1)
                limitations = [
                    "Train times are the published daily timetable; delays aren't modelled.",
                    fare["note"],
                    "Auto legs are modelled estimates, not booking quotes." if (first or kind == "auto") else None,
                    "Feeder bus times are scheduled (GTFS)." if kind == "bus" else None,
                    "Walks to/from stations are straight-line x 1.3 estimates.",
                ]
                if (first or kind == "auto") and (origin[1] < 77.3 or destination[1] < 77.3):
                    limitations.append("Outside Bengaluru, auto fares use the Bengaluru meter tariff "
                                       "(no Tumakuru tariff in the dataset).")
                opt = _option("train", [a_leg, tleg] + e_legs, total,
                              _transit_cost(amount, "fare", lo if amount is not None else None,
                                            hi if amount is not None else None, detail),
                              E.combine(parts),
                              rail_km + bus_km + (a_cost["km"] if a_cost else 0)
                              + (e_cost["km"] if kind == "auto" else 0),
                              transfers, sources, [x for x in limitations if x], False,
                              {"transit_km": {"rail": rail_km, "bus": round(bus_km, 2)},
                               "first_mile": "auto" if first else "walk", "last_mile": kind,
                               "train": {"no": hit["train"]["no"], "name": hit["train"]["name"],
                                         "kind": hit["train"]["kind"]}})
                opt["title"] = title
                out.append(opt)
    return out, notes
