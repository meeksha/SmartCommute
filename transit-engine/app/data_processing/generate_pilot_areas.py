
import pandas as pd

OUTPUT = "data/processed/walking/walking_pilot_areas.csv"

# Approximate group centres from the clustering analysis.
pilot_groups = [
    {
        "parent_cluster": 21,
        "subcluster": 2,
        "stop_count": 27,
        "centre_lat": 12.847728,
        "centre_lon": 77.665247
    },
    {
        "parent_cluster": 32,
        "subcluster": 2,
        "stop_count": 17,
        "centre_lat": 13.026576,
        "centre_lon": 77.760481
    }
]

# Approximately 2 km in each direction.
lat_margin = 2.0 / 111.0
lon_margin = 2.0 / (111.0 * 0.974)

results = []

for group in pilot_groups:
    lat = group["centre_lat"]
    lon = group["centre_lon"]

    results.append({
        **group,
        "north": lat + lat_margin,
        "south": lat - lat_margin,
        "east": lon + lon_margin,
        "west": lon - lon_margin
    })

df = pd.DataFrame(results)
df.to_csv(OUTPUT, index=False)

print("\nPILOT WALKING-NETWORK AREAS")
print(df.to_string(index=False))
print("\nSaved to:", OUTPUT)
