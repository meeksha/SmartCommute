from pathlib import Path
from urllib.request import Request, urlopen

BASE_DIR = Path(__file__).resolve().parents[2]
OUTPUT_DIR = BASE_DIR / "data" / "raw" / "namma_yatri"

BASE_URL = (
    "https://d11gklsvr97l1g.cloudfront.net/"
    "open/json-data/"
)

DATASETS = {
    "city_agg_cumulative_funnel.json":
        "city_agg_cumulative_funnel_new_key.json",

    "city_agg_cumulative_stats.json":
        "city_agg_cumulative_stats_new_key.json",

    "city_agg_driver_eda.json":
        "city_agg_driver_eda_new_key.json",

    "city_agg_live_funnel.json":
        "city_agg_live_funnel_new_key.json",

    "city_agg_live_trends.json":
        "city_agg_live_trends_new_key.json",

    "daily_stats.json":
        "daily_stats_v2.json",

    "driver_eda_wards.json":
        "driver_eda_wards_new_key.json",

    "driver_eda_ca.json":
        "driver_eda_ca_new_key.json",

    "funnel_cumulative_ward.json":
        "funnel_cumulative_ward_new_key.json",

    "funnel_cumulative_ca.json":
        "funnel_cumulative_ca_new_key.json",

    "funnel_live_ward.json":
        "funnel_live_ward_new_key.json",

    "funnel_live_ca.json":
        "funnel_live_ca_new_key.json",

    "trends_live_ward.json":
        "trends_live_ward_new_key.json",

    "trends_live_ca.json":
        "trends_live_ca_new_key.json",
}


def download_file(filename, remote_name):

    url = BASE_URL + remote_name

    print(f"\nDownloading {filename}")

    try:
        request = Request(
            url,
            headers={"User-Agent": "Transit-Engine-Student-Project"}
        )

        with urlopen(request, timeout=30) as response:
            content = response.read()

        output = OUTPUT_DIR / filename
        output.write_bytes(content)

        print("Saved:", output)
        print("Size:", len(content), "bytes")

    except Exception as error:
        print("Download failed:", error)


def main():

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    for filename, remote_name in DATASETS.items():
        download_file(filename, remote_name)

    print("\nNamma Yatri download process completed.")


if __name__ == "__main__":
    main()
