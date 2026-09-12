#!/usr/bin/env python3
"""Architecture fitness test — the dependency arrows must point inward.

Layering violations are cheap to introduce and expensive to unwind, so this
runs in CI rather than living in a document nobody re-reads.

    engine   -> stdlib only
    domain   -> stdlib only
    ports    -> domain, engine
    adapters -> ports, domain, engine, drivers
    tools/analysis are not imported by anything

A layer may never import from one below it in that list.
"""

import ast
import pathlib
import sys

ALLOWED: dict[str, set[str]] = {
    "engine": set(),
    "domain": set(),
    "ports": {"domain", "engine"},
    "adapters": {"ports", "domain", "engine"},
}

LOCAL = set(ALLOWED) | {"tests", "tools", "analysis", "api", "workers"}


def imported_roots(path: pathlib.Path) -> set[str]:
    roots: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(), str(path))):
        if isinstance(node, ast.Import):
            roots |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            roots.add(node.module.split(".")[0])
    return roots


def main() -> int:
    root = pathlib.Path(__file__).resolve().parent.parent
    violations: list[str] = []
    third_party: list[str] = []

    for layer, allowed in ALLOWED.items():
        for file in sorted((root / layer).rglob("*.py")):
            rel = file.relative_to(root)
            for mod in sorted(imported_roots(file)):
                if mod == layer:
                    continue
                if mod in LOCAL:
                    if mod not in allowed:
                        violations.append(f"  {rel}: imports '{mod}' (not allowed in {layer}/)")
                # engine and domain must stay dependency-free
                elif mod not in sys.stdlib_module_names and layer in ("engine", "domain"):
                    third_party.append(f"  {rel}: third-party import '{mod}'")

    if violations:
        print("LAYERING VIOLATIONS — dependency arrows must point inward:")
        print("\n".join(violations))
    if third_party:
        print("PURITY VIOLATIONS — engine/ and domain/ must be dependency-free:")
        print("\n".join(third_party))
    if violations or third_party:
        return 1

    print("architecture OK")
    for layer, allowed in ALLOWED.items():
        print(f"  {layer + '/':<10} may import: {', '.join(sorted(allowed)) or 'stdlib only'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
