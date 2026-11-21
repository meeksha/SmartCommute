from pathlib import Path
import json

BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / "data" / "raw" / "namma_yatri"


def inspect_json(filepath):
    print("\n" + "=" * 60)
    print(filepath.name)
    print("=" * 60)

    try:
        with open(filepath, "r", encoding="utf-8") as file:
            data = json.load(file)

        print("Data type:", type(data).__name__)

        if isinstance(data, dict):
            print("Top-level keys:", list(data.keys())[:30])
            print("\nSample:")
            print(json.dumps(data, indent=2)[:2000])

        elif isinstance(data, list):
            print("Number of records:", len(data))

            if data:
                print("\nFirst record:")
                print(json.dumps(data[0], indent=2)[:2000])

        else:
            print("Value:", str(data)[:1000])

    except Exception as error:
        print("Inspection failed:", error)


def main():
    files = sorted(DATA_DIR.glob("*.json"))

    if not files:
        print("No JSON files found in:", DATA_DIR)
        return

    print("JSON files found:", len(files))

    for filepath in files:
        inspect_json(filepath)


if __name__ == "__main__":
    main()
