
import numpy as np
import pandas as pd
from pathlib import Path

# Reproducible synthetic dataset
rng = np.random.default_rng(42)
N = 5000

# Approximate Bengaluru residential and employment-area coordinates.
residential_zones = {
    "Yelahanka": (13.1007, 77.5963),
    "Hebbal": (13.0358, 77.5970),
    "Rajajinagar": (13.0100, 77.5550),
    "Vijayanagar": (12.9719, 77.5350),
    "Jayanagar": (12.9250, 77.5838),
    "JP Nagar": (12.9077, 77.5850),
    "BTM": (12.9166, 77.6101),
    "HSR Layout": (12.9116, 77.6389),
    "Sarjapur": (12.9010, 77.6870),
    "Whitefield": (12.9698, 77.7500),
    "Electronic City": (12.8452, 77.6602),
    "Kengeri": (12.9177, 77.4838),
    "Marathahalli": (12.9591, 77.6974),
    "Banashankari": (12.9255, 77.5468),
}

office_zones = {
    "CBD": (12.9750, 77.6050),
    "Manyata Tech Park": (13.0499, 77.6200),
    "Outer Ring Road": (12.9352, 77.6950),
    "Whitefield IT Zone": (12.9698, 77.7500),
    "Electronic City": (12.8452, 77.6602),
    "Peenya": (13.0285, 77.5197),
}

# Census 2011 Bengaluru Urban mode counts.
# Shares are calculated excluding "No travel".
census_modes = [
    "Walking",
    "Bicycle",
    "Private two-wheeler",
    "Car",
    "Auto/taxi",
    "Bus",
    "Train (Census category)",
    "Other",
]

census_counts = np.array([
    858551,
    161450,
    676691,
    311510,
    101944,
    844677,
    32348,
    15707,
])

mode_probabilities = census_counts / census_counts.sum()

residential_names = list(residential_zones)
office_names = list(office_zones)

def generate_coordinate(zone):
    lat, lon = zone
    # Small random offset around the selected zone.
    return (
        lat + rng.normal(0, 0.012),
        lon + rng.normal(0, 0.012),
    )

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

    return 2 * earth_radius * np.arcsin(np.sqrt(a))

records = []

for i in range(N):
    home_zone_name = rng.choice(residential_names)
    office_zone_name = rng.choice(office_names)

    home_lat, home_lon = generate_coordinate(
        residential_zones[home_zone_name]
    )

    office_lat, office_lon = generate_coordinate(
        office_zones[office_zone_name]
    )

    # Departure time: weekday morning commute window.
    departure_minutes = int(rng.integers(420, 601))
    arrival_minutes = departure_minutes + int(
        rng.integers(30, 91)
    )

    current_mode = rng.choice(
        census_modes,
        p=mode_probabilities
    )

    preferences = rng.choice(
        ["Time", "Cost", "CO2", "Balanced"],
        p=[0.30, 0.25, 0.20, 0.25]
    )

    distance = haversine_km(
        home_lat, home_lon,
        office_lat, office_lon
    )

    records.append({
        "employee_id": f"SYN{i + 1:05d}",
        "home_zone": home_zone_name,
        "office_zone": office_zone_name,
        "home_lat": home_lat,
        "home_lon": home_lon,
        "office_lat": office_lat,
        "office_lon": office_lon,
        "departure_time": (
            f"{departure_minutes // 60:02d}:"
            f"{departure_minutes % 60:02d}"
        ),
        "required_arrival_time": (
            f"{(arrival_minutes % 1440) // 60:02d}:"
            f"{arrival_minutes % 60:02d}"
        ),
        "departure_minutes": departure_minutes,
        "commute_distance_km": round(distance, 2),
        "current_mode": current_mode,
        "optimization_preference": preferences,
        "max_walking_minutes": int(rng.choice([5, 10, 15, 20])),
        "max_transfers": int(rng.choice([0, 1, 2])),
        "carpool_interest": bool(rng.choice([True, False])),
        "dataset_type": "Synthetic",
        "mode_distribution_reference": "Census 2011 B-28",
    })

df = pd.DataFrame(records)

output = Path("data/processed/employees")
output.mkdir(parents=True, exist_ok=True)

file_path = output / "bengaluru_synthetic_employees.csv"
df.to_csv(file_path, index=False)

print("EMPLOYEE DATASET CREATED")
print("-" * 40)
print("Total employee profiles:", len(df))
print("Output:", file_path)

print("\nCurrent mode distribution:")
print(
    df["current_mode"]
    .value_counts()
    .to_string()
)

print("\nOptimization preferences:")
print(
    df["optimization_preference"]
    .value_counts()
    .to_string()
)

print("\nMissing values:", df.isnull().sum().sum())
print("\nFirst 5 records:")
print(df.head().to_string(index=False))
