"""Company commuter population views, K-Means clusters, and carpool matching limits.

The population is the Census-derived statistical population of one office
(app.services.population / digital_twin.population): no invented individuals.
Carpool matching between people happens only between registered SmartCommute
users (app.main carpool board); K-Means here only groups the statistical
population for analysis (screening), it never matches named people.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.services.population import _hav  # noqa: F401  (re-exported for callers)

DEFAULT_MATCH_LIMITS = {
    "max_origin_km": 2.5,           # pickup within this straight-line radius
    "max_destination_km": 2.0,      # offices must be this close
    "max_departure_diff_min": 30,
    "max_detour_ratio": 0.35,
    "max_riders": 3,
}


def load_employees(office: str | None = None) -> pd.DataFrame:
    from app.services.digital_twin import population
    return population(office)


def employee(employee_id: str, office: str | None = None) -> dict | None:
    df = load_employees(office)
    hit = df[df["employee_id"] == str(employee_id)]
    if hit.empty:
        return None
    return hit.iloc[0].to_dict()


def to_minutes(hhmm: str) -> int:
    h, m = str(hhmm).split(":")[:2]
    return int(h) * 60 + int(m)


# The dataset stores each employee's morning departure. Their evening return is
# modelled as departure + a 9-hour working day (stated assumption).
WORKDAY_MINUTES = 9 * 60
EVENING_FROM_MINUTES = 14 * 60     # searches from 14:00 are treated as trips home


def trip_direction(departure_hhmm: str) -> str:
    return "return" if to_minutes(departure_hhmm) >= EVENING_FROM_MINUTES else "outbound"


def pickup_detour_km(origin, partners: list[dict]) -> float:
    """Greedy nearest-neighbour pickup tour length beyond the direct route."""
    if not partners:
        return 0.0
    pos = origin
    remaining = list(partners)
    tour = 0.0
    while remaining:
        nxt = min(remaining, key=lambda p: _hav(pos[0], pos[1], p.get("pickup_lat", p["home_lat"]),
                                                  p.get("pickup_lon", p["home_lon"])))
        tour += float(_hav(pos[0], pos[1], nxt.get("pickup_lat", nxt["home_lat"]), nxt.get("pickup_lon", nxt["home_lon"])))
        pos = (nxt.get("pickup_lat", nxt["home_lat"]), nxt.get("pickup_lon", nxt["home_lon"]))
        remaining.remove(nxt)
    return round(tour * 1.35, 2)


def cluster_summary(office: str | None = None) -> dict:
    df = load_employees(office)
    clusters = []
    for cid, part in df.groupby("cluster_id"):
        dep = int(part["departure_minutes"].mean())
        clusters.append({
            "cluster_id": int(cid),
            "employee_count": int(len(part)),
            "centroid_lat": round(float(part["home_lat"].mean()), 5),
            "centroid_lon": round(float(part["home_lon"].mean()), 5),
            "avg_departure": f"{dep // 60:02d}:{dep % 60:02d}",
            "avg_commute_km": round(float(part["commute_distance_km"].mean()), 2),
            "car_owners": int(part["owns_car"].sum()),
            "top_home_zones": part["home_zone"].value_counts().head(3).to_dict(),
            "top_office_zones": part["office_zone"].value_counts().head(3).to_dict(),
            "mode_share": part["baseline_mode"].value_counts(normalize=True).round(3).to_dict(),
        })
    return {
        "algorithm": f"K-Means (k={len(clusters)}) on home ward coordinates",
        "employee_count": int(len(df)),
        "cluster_count": len(clusters),
        "clusters": clusters,
        "office": df["office_zone"].iloc[0],
        "dataset": "Census 2011-derived statistical population (ward populations + Table B-28)",
    }


def recluster(k: int = 15, office: str | None = None, features=("home_lat", "home_lon", "departure_minutes"),
              seed: int = 42) -> dict:
    """Re-run K-Means with a different k and report silhouette/inertia."""
    from sklearn.cluster import KMeans
    from sklearn.metrics import silhouette_score
    from sklearn.preprocessing import StandardScaler
    df = load_employees(office)
    X = StandardScaler().fit_transform(df[list(features)])
    km = KMeans(n_clusters=int(k), random_state=seed, n_init=10).fit(X)
    sample = np.random.default_rng(seed).choice(len(X), size=min(2000, len(X)), replace=False)
    sil = float(silhouette_score(X[sample], km.labels_[sample]))
    sizes = np.bincount(km.labels_).tolist()
    return {"k": int(k), "inertia": round(float(km.inertia_), 2), "silhouette": round(sil, 4),
            "cluster_sizes": sizes, "features": list(features)}


def employees_page(offset=0, limit=100, office=None, cluster_id=None) -> dict:
    df = load_employees(office)
    if cluster_id is not None:
        df = df[df["cluster_id"] == int(cluster_id)]
    total = len(df)
    cols = ["employee_id", "home_zone", "office_zone", "home_lat", "home_lon", "office_lat", "office_lon",
            "departure_time", "commute_distance_km", "road_km", "distance_band", "baseline_mode", "owns_car",
            "cluster_id", "ward_location_source"]
    page = df.iloc[int(offset): int(offset) + int(limit)][cols]
    return {"total": int(total), "offset": int(offset), "limit": int(limit),
            "dataset": "Census 2011-derived statistical population (not real individuals)",
            "employees": page.to_dict("records")}
