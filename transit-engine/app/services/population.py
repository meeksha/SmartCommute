"""Statistical commuter population built only from published data.

No individual is invented with made-up attributes. For a company with N
employees at a chosen office, the population is a *deterministic allocation*
of those N commuters to:

1. Home ward: the 198 BBMP wards, weighted by their Census 2011 population,
   re-weighted so the home->office distance distribution matches Census 2011
   Table B-28 (Bangalore Urban, urban 'other workers': distance to place of
   work). Within a distance band, wards keep their population shares.
2. Travel mode: Census 2011 B-28 mode shares *for that distance band*.

Counts are apportioned with the largest-remainder method, so the same inputs
always give the same population (no random sampling). Each commuter sits at
their ward's centroid (ward resolution: the data has no finer home location).

Things the data does not give, and how they are handled (all stated in the
API output):
* B-28 groups "Tempo/Autorickshaw/Taxi": split auto 70 % / cab 30 %
  (assumption, unchanged from the earlier Twin).
* B-28 "Train" in 2011 Bengaluru is suburban rail; it is mapped to Metro.
* Car ownership: only people whose Census mode is car are treated as owning
  one. Carpool interest is not assumed; carpool uptake is a scenario input.
* Departure time: everyone is due at the office at the company start time;
  departure = start time - baseline travel time.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

WARDS = Path("data/external/census/bbmp_wards_2011_population.csv")
CENSUS_B28 = Path("data/processed/employees/bangalore_urban_commuting_statistics.csv")

BANDS = [("distance_0_1_km", 0.0, 1.5), ("distance_2_5_km", 1.5, 5.5), ("distance_6_10_km", 5.5, 10.5),
         ("distance_11_20_km", 10.5, 20.5), ("distance_21_30_km", 20.5, 30.5),
         ("distance_31_50_km", 30.5, 50.5), ("distance_51_plus_km", 50.5, 1e9)]
CENSUS_MODE_MAP = {
    "On foot": "walk", "Bicycle": "bicycle", "Moped/Scooter/Motor Cycle": "two_wheeler",
    "Car/Jeep/Van": "car", "Tempo/Autorickshaw/Taxi": "auto_taxi", "Bus": "bus", "Train": "metro",
}
AUTO_SHARE_OF_AUTO_TAXI = 0.7
ROAD_CIRCUITY = 1.35
DEFAULT_HEADCOUNT = 2000
DEFAULT_START = "09:30"

SOURCES = [
    "Census of India 2011: BBMP ward populations (198 wards), via Wikipedia 'List of wards in Bangalore (2009-2023)'",
    "Census of India 2011, Table B-28 (Bangalore Urban, urban): distance to work and mode of travel",
    "Ward locations: KGIS ward boundaries (datameet), BMTC GTFS stop names; 10 wards interpolated",
]


def _hav(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371.0088 * np.arcsin(np.sqrt(a))


@lru_cache(maxsize=1)
def wards() -> pd.DataFrame:
    return pd.read_csv(WARDS)


@lru_cache(maxsize=1)
def b28() -> pd.DataFrame:
    d = pd.read_csv(CENSUS_B28)
    return d[d["mode"].isin(CENSUS_MODE_MAP)].reset_index(drop=True)


def band_of(km: float) -> str:
    for col, lo, hi in BANDS:
        if lo <= km < hi:
            return col
    return BANDS[-1][0]


def distance_shares() -> dict:
    """P(distance band) among commuters who travel (B-28, all modes, 'distance not stated' excluded)."""
    d = b28()
    tot = {c: float(d[c].sum()) for c, _, _ in BANDS}
    s = sum(tot.values())
    return {c: v / s for c, v in tot.items()}


def mode_shares(band: str) -> dict:
    """P(mode | band) from B-28; auto/taxi split by the stated assumption."""
    d = b28()
    counts = {}
    for m, v in zip(d["mode"], d[band]):
        k = CENSUS_MODE_MAP[m]
        if k == "auto_taxi":
            counts["auto"] = counts.get("auto", 0) + float(v) * AUTO_SHARE_OF_AUTO_TAXI
            counts["cab"] = counts.get("cab", 0) + float(v) * (1 - AUTO_SHARE_OF_AUTO_TAXI)
        else:
            counts[k] = counts.get(k, 0) + float(v)
    s = sum(counts.values())
    return {k: v / s for k, v in counts.items() if v > 0}


def _apportion(total: int, weights: np.ndarray) -> np.ndarray:
    """Largest-remainder apportionment of `total` items to `weights`."""
    w = np.asarray(weights, dtype=float)
    if total <= 0 or w.sum() <= 0:
        return np.zeros(len(w), dtype=int)
    exact = w / w.sum() * total
    base = np.floor(exact).astype(int)
    rem = total - base.sum()
    order = np.argsort(-(exact - base), kind="stable")
    base[order[:rem]] += 1
    return base


@lru_cache(maxsize=32)
def build(office_lat: float, office_lon: float, office_name: str, headcount: int = DEFAULT_HEADCOUNT,
          start_time: str = DEFAULT_START) -> pd.DataFrame:
    w = wards().copy()
    w["straight_km"] = _hav(w["lat"].to_numpy(), w["lon"].to_numpy(), office_lat, office_lon)
    w["road_km"] = (w["straight_km"] * ROAD_CIRCUITY).clip(lower=0.5)
    w["band"] = [band_of(k) for k in w["road_km"]]

    # Re-weight wards so the distance-band distribution follows B-28.
    target = distance_shares()
    present = {b for b in w["band"]}
    tsum = sum(v for b, v in target.items() if b in present)
    band_pop = w.groupby("band")["population_2011"].sum()
    w["weight"] = [row.population_2011 / band_pop[row.band] * target[row.band] / tsum for row in w.itertuples()]
    w["n"] = _apportion(int(headcount), w["weight"].to_numpy())
    w = w[w["n"] > 0]

    # Modes per band, apportioned over the band's commuters, then spread over its wards.
    rows = []
    for band, g in w.groupby("band", sort=False):
        shares = mode_shares(band)
        if band in ("distance_6_10_km", "distance_11_20_km", "distance_21_30_km",
                    "distance_31_50_km", "distance_51_plus_km"):
            shares.pop("walk", None)   # B-28 reports some walking at 6-10 km; excluded (stated assumption)
        modes = list(shares)
        n_band = int(g["n"].sum())
        mode_counts = _apportion(n_band, np.array([shares[m] for m in modes]))
        pool = [m for m, c in zip(modes, mode_counts) for _ in range(c)]
        # Interleave so each ward gets a proportional mix (deterministic).
        pool = [pool[i] for i in np.argsort([(i * 0.6180339887) % 1 for i in range(len(pool))], kind="stable")]
        k = 0
        for r in g.sort_values("ward_no").itertuples():
            for _ in range(int(r.n)):
                rows.append({"ward_no": int(r.ward_no), "home_zone": r.ward_name, "home_lat": r.lat,
                             "home_lon": r.lon, "road_km": round(float(r.road_km), 2),
                             "commute_distance_km": round(float(r.straight_km), 2), "distance_band": band,
                             "baseline_mode": pool[k], "ward_location_source": r.location_source})
                k += 1
    df = pd.DataFrame(rows).sort_values(["ward_no", "baseline_mode"]).reset_index(drop=True)
    df.insert(0, "employee_id", [f"P{i + 1:05d}" for i in range(len(df))])
    df["office_zone"] = office_name
    df["office_lat"], df["office_lon"] = office_lat, office_lon
    df["owns_car"] = df["baseline_mode"].eq("car")
    df["required_arrival_time"] = start_time
    df["dataset_type"] = "Census-derived statistical population"
    return df


def offices() -> list[dict]:
    from app.services.places import OFFICE_PRESETS
    return OFFICE_PRESETS


def office_by(key: str | None) -> dict:
    offs = offices()
    if not key:
        return offs[0]
    for o in offs:
        if key in (o["id"], o["name"]):
            return o
    # Legacy zone labels ("Outer Ring Road", "CBD"...)
    for o in offs:
        if o["name"].lower().startswith(str(key).lower()):
            return o
    raise ValueError(f"Unknown office {key!r}. Use one of: " + ", ".join(o["id"] for o in offs))


def population_for(office: str | None = None, headcount: int = DEFAULT_HEADCOUNT,
                   start_time: str = DEFAULT_START) -> pd.DataFrame:
    o = office_by(office)
    return build(float(o["lat"]), float(o["lon"]), o["name"], int(headcount), start_time)


def describe(df: pd.DataFrame) -> dict:
    return {
        "type": "Census-derived statistical population (no individual-level data)",
        "headcount": int(len(df)),
        "wards_used": int(df["ward_no"].nunique()),
        "office": df["office_zone"].iloc[0] if len(df) else None,
        "mode_share": {k: round(v, 4) for k, v in df["baseline_mode"].value_counts(normalize=True).items()},
        "distance_share": {k: round(v, 4) for k, v in df["distance_band"].value_counts(normalize=True).items()},
        "sources": SOURCES,
        "assumptions": [
            "Each commuter is placed at their ward's centroid (ward-level resolution).",
            "Census 'Tempo/Autorickshaw/Taxi' split 70 % auto / 30 % cab (assumption).",
            "Census 'Train' (2011 suburban rail) mapped to Metro.",
            "Only commuters whose Census mode is car are assumed to own a car.",
            "Census reports some walking in the 6-10 km band; walking more than ~5.5 km to an office is "
            "excluded and that band's other modes are scaled up.",
            "Distance bands beyond the city's extent (31+ km) have no BBMP wards; their share is redistributed.",
        ],
    }
