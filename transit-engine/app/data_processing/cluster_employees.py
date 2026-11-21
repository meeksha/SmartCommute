
import pandas as pd
import numpy as np
from pathlib import Path
from itertools import combinations
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler

INPUT = Path(
    "data/processed/employees/bengaluru_synthetic_employees.csv"
)
OUTPUT_DIR = Path("data/processed/employees")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

N_CLUSTERS = 15
MAX_DESTINATION_DISTANCE_KM = 5
MAX_DEPARTURE_DIFFERENCE_MIN = 30

df = pd.read_csv(INPUT)

# Features used for clustering potential carpool origins.
features = df[[
    "home_lat",
    "home_lon",
    "departure_minutes"
]].copy()

scaler = StandardScaler()
scaled_features = scaler.fit_transform(features)

model = KMeans(
    n_clusters=N_CLUSTERS,
    random_state=42,
    n_init=10
)

df["cluster_id"] = model.fit_predict(scaled_features)

def haversine_km(lat1, lon1, lat2, lon2):
    earth_radius = 6371

    lat1, lon1, lat2, lon2 = np.radians(
        [lat1, lon1, lat2, lon2]
    )

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = (
        np.sin(dlat / 2) ** 2
        + np.cos(lat1) * np.cos(lat2)
        * np.sin(dlon / 2) ** 2
    )

    return 2 * earth_radius * np.arcsin(
        np.sqrt(a)
    )

# Find compatible employee pairs inside each cluster.
candidate_pairs = []

for cluster_id, group in df.groupby("cluster_id"):
    interested = group[
        group["carpool_interest"].astype(str).str.lower()
        == "true"
    ]

    records = interested.to_dict("records")

    for a, b in combinations(records, 2):
        departure_gap = abs(
            a["departure_minutes"] - b["departure_minutes"]
        )

        if departure_gap > MAX_DEPARTURE_DIFFERENCE_MIN:
            continue

        destination_gap = haversine_km(
            a["office_lat"],
            a["office_lon"],
            b["office_lat"],
            b["office_lon"]
        )

        if destination_gap > MAX_DESTINATION_DISTANCE_KM:
            continue

        candidate_pairs.append({
            "cluster_id": cluster_id,
            "employee_1": a["employee_id"],
            "employee_2": b["employee_id"],
            "departure_difference_min": departure_gap,
            "destination_distance_km": round(
                destination_gap, 2
            ),
            "home_1_lat": a["home_lat"],
            "home_1_lon": a["home_lon"],
            "home_2_lat": b["home_lat"],
            "home_2_lon": b["home_lon"],
        })

# Save employee cluster assignments.
cluster_file = OUTPUT_DIR / "employee_clusters.csv"
df.to_csv(cluster_file, index=False)

# Save compatible candidate pairs.
pairs_df = pd.DataFrame(candidate_pairs)

pairs_file = OUTPUT_DIR / "employee_carpool_candidates.csv"
pairs_df.to_csv(pairs_file, index=False)

# Cluster summary.
summary = (
    df.groupby("cluster_id")
    .agg(
        employee_count=("employee_id", "count"),
        average_departure_min=("departure_minutes", "mean"),
        average_commute_km=("commute_distance_km", "mean"),
    )
    .round(2)
)

summary_file = OUTPUT_DIR / "employee_cluster_summary.csv"
summary.to_csv(summary_file)

print("\nK-MEANS CLUSTERING REPORT")
print("-" * 45)
print("Employees clustered:", len(df))
print("Number of clusters:", N_CLUSTERS)
print("Potential compatible employee pairs:", len(pairs_df))

print("\nCluster summary:")
print(summary.to_string())

print("\nOutput files:")
print(cluster_file)
print(pairs_file)
print(summary_file)
