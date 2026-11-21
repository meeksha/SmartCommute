"""Safely integrate shared quality filtering and ranking into recommendation_engine.py.

Run from the transit-engine project root:
    python -m app.routing.apply_quality_integration
The script creates a .bak copy and refuses to overwrite an existing backup.
"""
from __future__ import annotations

import ast
import re
import shutil
from pathlib import Path

TARGET = Path("app/routing/recommendation_engine.py")
BACKUP = Path("app/routing/recommendation_engine.py.before_quality_integration.bak")
IMPORT = "from app.routing.recommendation_quality import process_recommendations"


def main() -> None:
    if not TARGET.is_file():
        raise SystemExit(f"Cannot find {TARGET}. Run this command from the project root.")

    source = TARGET.read_text(encoding="utf-8")
    if IMPORT in source and "quality = process_recommendations(" in source:
        print("Quality integration already appears to be installed; no changes made.")
        return

    if BACKUP.exists():
        raise SystemExit(
            f"Backup already exists: {BACKUP}. Move it aside before applying again; "
            "the script will not overwrite a backup."
        )

    if "from app.routing.three_mode_adapter import adapt_bmtc_metro_bmtc" not in source:
        raise SystemExit("Three-mode adapter import not found. Refusing to patch an unexpected engine version.")
    if "three_mode_config" not in source:
        raise SystemExit("three_mode_config not found. Install/repair the three-mode integration first.")

    updated = source

    # Add the shared quality module import after the journey schema import.
    if IMPORT not in updated:
        anchor = "from app.routing.journey_schema import build_journey"
        if anchor not in updated:
            raise SystemExit("Could not locate journey_schema import; no changes made.")
        updated = updated.replace(anchor, anchor + "\n" + IMPORT, 1)

    # Extend only get_recommendations' signature, retaining its existing parameters.
    match = re.search(r"def get_recommendations\([\s\S]*?\n\):", updated)
    if not match:
        raise SystemExit("Could not locate get_recommendations function signature; no changes made.")
    signature = match.group(0)
    additions = []
    for name, default in (
        ("quality_limits", "None"),
        ("ranking_weights", "None"),
        ("ranking_profile", '"green_first"'),
    ):
        if not re.search(rf"\b{re.escape(name)}\s*=", signature):
            additions.append(f"    {name}={default},")
    if additions:
        # Put new optional arguments immediately before the closing parenthesis.
        closing = signature.rfind("\n):")
        if closing < 0:
            raise SystemExit("Unexpected function signature layout; no changes made.")
        before_close = signature[:closing].rstrip()
        if not before_close.endswith(","):
            before_close += ","
        signature = before_close + "\n" + "\n".join(additions) + signature[closing:]
        updated = updated[:match.start()] + signature + updated[match.end():]

    # Replace the legacy emissions-only sort with the common quality pipeline.
    start_marker = "    # Rank by conservative emissions estimate first."
    start = updated.find(start_marker)
    if start < 0:
        raise SystemExit("Legacy ranking block not found; no changes made.")
    return_marker = "    return {\n        \"status\":"
    end = updated.find(return_marker, start)
    if end < 0:
        raise SystemExit("Recommendation result return block not found; no changes made.")

    replacement = '''    # Apply the same walking limits, deduplication and explainable ranking to
    # every candidate, including the optional BMTC + Metro + BMTC journey.
    raw_candidate_count = len(recommendations)
    quality = process_recommendations(
        recommendations,
        limits=quality_limits,
        weights=ranking_weights,
        ranking_profile=ranking_profile,
    )
    recommendations = quality["recommendations"]

'''
    updated = updated[:start] + replacement + updated[end:]

    # Add auditable quality metadata to the existing result object.
    result_anchor = '        "recommendations": recommendations,\n'
    if result_anchor not in updated:
        raise SystemExit("Could not locate recommendations result field; no changes made.")
    metadata = '''        "rejected_recommendations": quality["rejected_recommendations"],
        "duplicate_recommendations_removed": quality["duplicate_recommendations_removed"],
        "quality_limits": quality["quality_limits"],
        "ranking_weights": quality["ranking_weights"],
        "ranking_profile": quality["ranking_profile"],
        "raw_candidate_count": raw_candidate_count,
'''
    updated = updated.replace(result_anchor, result_anchor + metadata, 1)

    # The existing comparison_count remains the accepted count after filtering.
    ast.parse(updated)
    shutil.copy2(TARGET, BACKUP)
    TARGET.write_text(updated, encoding="utf-8")
    print("QUALITY INTEGRATION APPLIED")
    print(f"Backup created: {BACKUP}")
    print("All candidate modes now pass through walking filters, deduplication and shared ranking.")


if __name__ == "__main__":
    main()
