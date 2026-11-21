from pathlib import Path

path = Path("app/routing/bmtc_metro_planner.py")
source = path.read_text(encoding="utf-8")

replacements = [
    (
        "    INTERCHANGES,\n",
        "",
    ),
    (
        "def plan_bmtc_then_metro(\n",
        'CURRENT_INTERCHANGES = Path(\n'
        '    "data/processed/bmtc_latest/metro_bmtc_current_interchanges.csv"\n'
        ')\n\n\n'
        "def plan_bmtc_then_metro(\n",
    ),
    (
        "    if not INTERCHANGES.exists():",
        "    if not CURRENT_INTERCHANGES.exists():",
    ),
    (
        "    interchange_df = pd.read_csv(INTERCHANGES)",
        "    interchange_df = pd.read_csv(CURRENT_INTERCHANGES)",
    ),
    (
        '(interchange_df["interchange_status"] == "OSM_MODELLED_CONNECTION")',
        '(interchange_df["interchange_status"] == "CURRENT_FEED_APPROXIMATE_WALK")',
    ),
]

for old, new in replacements:
    count = source.count(old)
    if count != 1:
        raise SystemExit(
            f"Patch stopped: expected exactly 1 occurrence, found {count} for:\n{old}"
        )
    source = source.replace(old, new, 1)

path.write_text(source, encoding="utf-8")
print("Patched successfully:", path)
