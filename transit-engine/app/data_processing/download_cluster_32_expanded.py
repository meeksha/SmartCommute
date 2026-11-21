
import os
import time
import pandas as pd
import osmnx as ox

# --------------------------------------------------
# CONFIGURATION
# --------------------------------------------------

INPUT = "data/processed/walking/walking_pilot_areas.csv"

OUTPUT_DIR = "data/raw/walking/expansions"

OUTPUT_FILE = os.path.join(
    OUTPUT_DIR,
    "bmtc_cluster_32_2_expanded.graphml"
)

MAX_ATTEMPTS = 4
INITIAL_WAIT_SECONDS = 30

# --------------------------------------------------
# PREPARE DIRECTORY
# --------------------------------------------------

os.makedirs(OUTPUT_DIR, exist_ok=True)

# --------------------------------------------------
# OSMNX SETTINGS
# --------------------------------------------------

ox.settings.use_cache = True
ox.settings.log_console = True
ox.settings.requests_timeout = 180

# Use an alternative global Overpass server
ox.settings.overpass_url = "https://overpass.private.coffee/api"

# Identify this project in API requests
ox.settings.http_user_agent = "TransitEngineStudentProject/1.0"
# --------------------------------------------------
# LOAD ORIGINAL PILOT BOUNDARY
# --------------------------------------------------

areas = pd.read_csv(INPUT)

area = areas[
    (areas["parent_cluster"] == 32)
    & (areas["subcluster"] == 2)
]

if area.empty:
    raise ValueError("Pilot area 32-2 not found.")

area = area.iloc[0]

# --------------------------------------------------
# EXPAND BOUNDARIES
# --------------------------------------------------

# Expand south by approximately 1.1 km.
# Expand the other sides by approximately 550 m.

north = float(area["north"]) + 0.005
south = float(area["south"]) - 0.010
east = float(area["east"]) + 0.005
west = float(area["west"]) - 0.005

print("\nEXPANDED CLUSTER 32-2")
print("=" * 65)

print(f"North: {north:.6f}")
print(f"South: {south:.6f}")
print(f"East:  {east:.6f}")
print(f"West:  {west:.6f}")

print("\nTarget original-network node:")
print("Latitude: 13.0069138")
print("Longitude: 77.7574485")

# --------------------------------------------------
# RETRY DOWNLOAD
# --------------------------------------------------

download_successful = False

for attempt in range(1, MAX_ATTEMPTS + 1):

    try:
        print(f"\nDownload attempt {attempt}/{MAX_ATTEMPTS}")

        G = ox.graph_from_bbox(
            bbox=(
                west,
                south,
                east,
                north
            ),
            network_type="walk",
            simplify=True,
            retain_all=True
        )

        print("\nDOWNLOAD SUCCESSFUL")

        print("Nodes:", len(G.nodes))
        print("Edges:", len(G.edges))

        ox.save_graphml(
            G,
            filepath=OUTPUT_FILE
        )

        size_mb = (
            os.path.getsize(OUTPUT_FILE)
            / (1024 * 1024)
        )

        print(f"File size: {size_mb:.2f} MB")
        print("Saved:", OUTPUT_FILE)

        download_successful = True

        del G
        break

    except Exception as error:

        print("\nDOWNLOAD FAILED")
        print(str(error))

        if attempt < MAX_ATTEMPTS:

            wait_time = (
                INITIAL_WAIT_SECONDS
                * (2 ** (attempt - 1))
            )

            print(
                f"Waiting {wait_time} seconds..."
            )

            time.sleep(wait_time)

        else:
            print("Maximum retry attempts reached.")

# --------------------------------------------------
# FINAL STATUS
# --------------------------------------------------

print("\n" + "=" * 65)

if download_successful:
    print("EXPANDED CLUSTER DOWNLOAD COMPLETED")
else:
    print("EXPANDED CLUSTER DOWNLOAD FAILED")

print("=" * 65)
