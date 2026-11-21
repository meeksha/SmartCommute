from pathlib import Path
import shutil

path = Path("app/routing/recommendation_engine.py")
source = path.read_text(encoding="utf-8")

old = (
    "Two-wheeler routing is integrated, but two-wheeler operating-cost "
    "estimates, carpool and company shuttle matching are not yet integrated."
)

new = (
    "Two-wheeler routing and estimated petrol operating costs are integrated; "
    "carpool and company shuttle matching are not yet integrated."
)

if old not in source:
    raise SystemExit(
        "Expected limitation text not found. No changes made."
    )

backup = path.with_name(
    "recommendation_engine.py.before_limitation_update.bak"
)

shutil.copy2(path, backup)
path.write_text(source.replace(old, new, 1), encoding="utf-8")

print("Data limitation updated successfully.")
print("Backup:", backup)
