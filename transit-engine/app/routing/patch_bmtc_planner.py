from pathlib import Path

path = Path("app/routing/bmtc_planner.py")
source = path.read_text(encoding="utf-8")

if "from functools import lru_cache" not in source:
    source = source.replace(
        "from datetime import datetime\n",
        "from datetime import datetime\nfrom functools import lru_cache\n",
        1
    )

if "@lru_cache(maxsize=1)\ndef load_bmtc_data():" not in source:
    source = source.replace(
        "def load_bmtc_data():",
        "@lru_cache(maxsize=1)\ndef load_bmtc_data():",
        1
    )

anchor = '''def find_bmtc_stop(stops, name):
    exact = stops[
'''

replacement = '''def find_bmtc_stop(stops, name):
    # Allow an exact stop ID, avoiding ambiguity from duplicate stop names.
    by_id = stops[
        stops["stop_id"].astype(str) == str(name).strip()
    ]

    if len(by_id) == 1:
        return by_id.iloc[0]

    exact = stops[
'''

if "Allow an exact stop ID" not in source:
    if anchor not in source:
        raise RuntimeError("Could not locate find_bmtc_stop().")
    source = source.replace(anchor, replacement, 1)

path.write_text(source, encoding="utf-8")
print("BMTC planner updated: caching and stop-ID lookup enabled.")
