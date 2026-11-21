import ast
from pathlib import Path

files = [
    "app/routing/planner.py",
    "app/routing/metro_planner.py",
    "app/routing/bmtc_latest_planner.py",
    "app/routing/recommendation_engine.py",
]

for filename in files:
    path = Path(filename)
    print("\n" + "=" * 75)
    print(f"FILE: {filename}")
    print("=" * 75)

    if not path.exists():
        print("FILE NOT FOUND")
        continue

    source = path.read_text(encoding="utf-8-sig")
    tree = ast.parse(source)

    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            print(ast.get_source_segment(source, node))

        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            args = [arg.arg for arg in node.args.args]
            print(f"\nFUNCTION: {node.name}({', '.join(args)})")
            if ast.get_docstring(node):
                print("DOCSTRING:", ast.get_docstring(node))


