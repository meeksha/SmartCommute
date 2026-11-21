"""Stop/station coordinate lookups and offline place search."""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd

BMTC_STOPS = Path("data/processed/bmtc_latest/bmtc_stops.csv")
METRO_STOPS = Path("data/processed/metro/standard/stops.csv")
METRO_ROUTES = Path("data/processed/metro/standard/routes.csv")

# Employment zones used by the employee dataset (office presets for the UI).
OFFICE_PRESETS = [
    {"id": "cbd", "name": "CBD (MG Road)", "lat": 12.9750, "lon": 77.6050},
    {"id": "manyata", "name": "Manyata Tech Park", "lat": 13.0499, "lon": 77.6200},
    {"id": "orr", "name": "Outer Ring Road (Bellandur)", "lat": 12.9352, "lon": 77.6950},
    {"id": "whitefield", "name": "Whitefield IT Zone", "lat": 12.9698, "lon": 77.7500},
    {"id": "ecity", "name": "Electronic City", "lat": 12.8452, "lon": 77.6602},
    {"id": "peenya", "name": "Peenya", "lat": 13.0285, "lon": 77.5197},
]
OFFICE_ZONE_NAMES = {
    "CBD": "cbd", "Manyata Tech Park": "manyata", "Outer Ring Road": "orr",
    "Whitefield IT Zone": "whitefield", "Electronic City": "ecity", "Peenya": "peenya",
}


@lru_cache(maxsize=1)
def bmtc_stop_coords() -> dict:
    s = pd.read_csv(BMTC_STOPS, dtype={"stop_id": str})
    return {r.stop_id: (float(r.stop_lat), float(r.stop_lon), str(r.stop_name))
            for r in s.itertuples(index=False)}


@lru_cache(maxsize=1)
def metro_stop_coords() -> dict:
    s = pd.read_csv(METRO_STOPS, dtype=str)
    return {r.stop_id: (float(r.stop_lat), float(r.stop_lon), str(r.stop_name))
            for r in s.itertuples(index=False) if pd.notna(r.stop_lat)}


@lru_cache(maxsize=1)
def metro_stations() -> pd.DataFrame:
    s = pd.read_csv(METRO_STOPS, dtype=str)
    s["location_type"] = pd.to_numeric(s["location_type"], errors="coerce")
    st = s[s["location_type"] == 1].copy()
    st["stop_lat"] = st["stop_lat"].astype(float)
    st["stop_lon"] = st["stop_lon"].astype(float)
    return st[["stop_id", "stop_name", "stop_lat", "stop_lon"]].reset_index(drop=True)


@lru_cache(maxsize=1)
def metro_line_info() -> dict:
    r = pd.read_csv(METRO_ROUTES, dtype=str)
    return {row.route_id: {"name": f"{row.route_short_name} Line",
                           "color": "#" + str(row.route_color or "888888")}
            for row in r.itertuples(index=False)}


def stop_point(stop_id, kind: str):
    table = bmtc_stop_coords() if kind == "bus" else metro_stop_coords()
    hit = table.get(str(stop_id))
    if not hit:
        return None
    return {"lat": hit[0], "lon": hit[1], "name": hit[2]}


def stops_path(stop_ids, kind: str):
    out = []
    for sid in stop_ids or []:
        p = stop_point(sid, kind)
        if p:
            out.append([round(p["lat"], 6), round(p["lon"], 6)])
    return out


def _norm(text):
    return re.sub(r"[^a-z0-9 ]", " ", str(text).lower()).strip()


@lru_cache(maxsize=1)
def _search_index():
    rows = []
    for o in OFFICE_PRESETS:
        rows.append(("office", o["name"], o["lat"], o["lon"]))
    try:
        from app.services.rail import stations as rail_stations
        for st in rail_stations().values():
            rows.append(("rail_station", f"{st['name']} railway station", st["lat"], st["lon"]))
    except Exception:
        pass
    st = metro_stations()
    for r in st.itertuples(index=False):
        rows.append(("metro_station", f"{r.stop_name} Metro", r.stop_lat, r.stop_lon))
    seen = set()
    for _sid, (lat, lon, name) in bmtc_stop_coords().items():
        key = _norm(name)
        if key in seen:
            continue
        seen.add(key)
        rows.append(("bus_stop", name, lat, lon))
    return [(kind, name, _norm(name), lat, lon) for kind, name, lat, lon in rows]


def search_places(query: str, limit: int = 8, use_online: bool = True) -> list[dict]:
    q = _norm(query)
    if not q:
        return []
    results = []
    if use_online:
        try:
            # Bengaluru + Tumakuru (no city suffix, so Tumakuru places are found too).
            params = {"q": query, "format": "json", "limit": 5, "countrycodes": "in",
                      "viewbox": "76.95,13.45,77.90,12.70", "bounded": 1}
            req = Request("https://nominatim.openstreetmap.org/search?" + urlencode(params),
                          headers={"User-Agent": "sustainable-commute-research/1.0"})
            with urlopen(req, timeout=5) as r:
                for item in json.loads(r.read().decode("utf-8")):
                    results.append({"name": item.get("display_name", "").split(",")[0],
                                    "label": item.get("display_name"),
                                    "lat": float(item["lat"]), "lon": float(item["lon"]),
                                    "kind": "osm", "source": "OpenStreetMap Nominatim"})
        except Exception:
            pass
    terms = q.split()
    scored = []
    for kind, name, norm, lat, lon in _search_index():
        if all(t in norm for t in terms):
            score = (0 if norm.startswith(q) else 1, {"office": 0, "metro_station": 1, "rail_station": 1, "bus_stop": 2}[kind], len(norm))
            scored.append((score, kind, name, lat, lon))
    scored.sort()
    for _s, kind, name, lat, lon in scored[: max(0, limit - len(results))]:
        results.append({"name": name, "label": name, "lat": lat, "lon": lon, "kind": kind,
                        "source": "Local GTFS / office presets"})
    return results[:limit]
