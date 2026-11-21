
import os
import time
import pandas as pd
import osmnx as ox

# --------------------------------------------------
# CONFIGURATION
# --------------------------------------------------

INPUT = "data/processed/walking/walking_pilot_areas.csv"
OUTPUT_DIR = "data/raw/walking/expansions"

MAX_ATTEMPTS = 4
INITIAL_WAIT_SECONDS = 30

# --------------------------------------------------
# CREATE OUTPUT DIRECTORY
# --------------------------------------------------

os.makedirs(OUTPUT_DIR, exist_ok=True)

# --------------------------------------------------
# OSMnx SETTINGS
# --------------------------------------------------

ox.settings.use_cache = True
ox.settings.log_console = True
ox.settings.requests_timeout = 180

# --------------------------------------------------
# LOAD PILOT AREAS
# --------------------------------------------------

if not os.path.exists(INPUT):
    raise FileNotFoundError(f"Input file not found: {INPUT}")

areas = pd.read_csv(INPUT)

required_columns = [
    "parent_cluster",
    "subcluster",
    "north",
    "south",
    "east",
    "west"
]

missing_columns = [
    column for column in required_columns
    if column not in areas.columns
]

if missing_columns:
    raise ValueError(
        f"Missing columns in pilot areas CSV: {missing_columns}"
    )

print("\nStarting pilot walking-network downloads...")
print("Number of pilot areas:", len(areas))

# --------------------------------------------------
# DOWNLOAD EACH PILOT AREA
# --------------------------------------------------

for _, area in areas.iterrows():

    parent = int(area["parent_cluster"])
    subcluster = int(area["subcluster"])

    filename = f"bmtc_cluster_{parent}_{subcluster}.graphml"
    filepath = os.path.join(OUTPUT_DIR, filename)

    print("\n" + "=" * 65)
    print(f"DOWNLOADING CLUSTER {parent}-{subcluster}")
    print("=" * 65)

    print(
        f"North: {area['north']:.6f}, "
        f"South: {area['south']:.6f}"
    )

    print(
        f"East: {area['east']:.6f}, "
        f"West: {area['west']:.6f}"
    )

    download_successful = False

    # --------------------------------------------------
    # RETRY LOOP WITH EXPONENTIAL BACKOFF
    # --------------------------------------------------

    for attempt in range(1, MAX_ATTEMPTS + 1):

        try:
            print(f"\nAttempt {attempt}/{MAX_ATTEMPTS}")

            # OSMnx 2.x bbox order:
            # west, south, east, north

            G = ox.graph_from_bbox(
                bbox=(
                    float(area["west"]),
                    float(area["south"]),
                    float(area["east"]),
                    float(area["north"])
                ),
                network_type="walk",
                simplify=True,
                retain_all=True
            )

            # --------------------------------------------------
            # GRAPH STATISTICS
            # --------------------------------------------------

            node_count = len(G.nodes)
            edge_count = len(G.edges)

            # --------------------------------------------------
            # SAVE GRAPH
            # --------------------------------------------------

            ox.save_graphml(
                G,
                filepath=filepath
            )

            file_size_mb = (
                os.path.getsize(filepath) / (1024 * 1024)
            )

            print("\nDOWNLOAD SUCCESSFUL")
            print("Nodes:", node_count)
            print("Edges:", edge_count)
            print(f"File size: {file_size_mb:.2f} MB")
            print("Saved:", filepath)

            download_successful = True

            del G
            break

        except Exception as error:

            print("\nDOWNLOAD FAILED")
            print("Cluster:", f"{parent}-{subcluster}")
            print("Attempt:", attempt)
            print("Error:", str(error))

            if attempt < MAX_ATTEMPTS:

                wait_time = (
                    INITIAL_WAIT_SECONDS * (2 ** (attempt - 1))
                )

                print(
                    f"Waiting {wait_time} seconds "
                    "before retrying..."
                )

                time.sleep(wait_time)

            else:
                print("Maximum retry attempts reached.")

    # --------------------------------------------------
    # FINAL STATUS FOR THIS AREA
    # --------------------------------------------------

    if not download_successful:
        print(
            f"\nCLUSTER {parent}-{subcluster} "
            "COULD NOT BE DOWNLOADED."
        )

# --------------------------------------------------
# FINAL SUMMARY
# --------------------------------------------------

print("\n" + "=" * 65)
print("PILOT DOWNLOAD PROCESS FINISHED")
print("=" * 65)

print("\nChecking downloaded files...")

for _, area in areas.iterrows():

    parent = int(area["parent_cluster"])
    subcluster = int(area["subcluster"])

    filename = f"bmtc_cluster_{parent}_{subcluster}.graphml"
    filepath = os.path.join(OUTPUT_DIR, filename)

    if os.path.exists(filepath):

        size_mb = os.path.getsize(filepath) / (1024 * 1024)

        print(
            f"SUCCESS: Cluster {parent}-{subcluster} "
            f"({size_mb:.2f} MB)"
        )

    else:

        print(
            f"MISSING: Cluster {parent}-{subcluster}"
        )

print("\nDownload script completed.")
