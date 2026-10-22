#!/usr/bin/env python3
"""Render the checked-in architecture diagrams using Graphviz and a CJK font."""
from pathlib import Path
import shutil
import subprocess
import sys


def main():
    dot = shutil.which("dot")
    if not dot:
        sys.exit("Graphviz 'dot' was not found. See docs/diagrams/README.md.")
    directory = Path(__file__).resolve().parents[1] / "docs" / "diagrams"
    for source in sorted(directory.glob("*.dot")):
        for extension in ("svg", "png"):
            target = source.with_suffix("." + extension)
            subprocess.run(
                [dot, "-T" + extension, "-Gdpi=140", str(source), "-o", str(target)],
                check=True,
            )
            print(target)


if __name__ == "__main__":
    main()
