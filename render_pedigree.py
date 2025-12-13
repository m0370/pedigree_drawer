#!/usr/bin/env python3
import argparse
import json
from pathlib import Path

from pedigree_drawer_lib import PedigreeChart


def main() -> int:
    parser = argparse.ArgumentParser(description="Render pedigree JSON to an SVG file.")
    parser.add_argument("input_json", type=Path, help="Path to input JSON file.")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("pedigree.svg"),
        help="Path to output SVG file (default: pedigree.svg).",
    )
    args = parser.parse_args()

    data = json.loads(args.input_json.read_text(encoding="utf-8"))
    chart = PedigreeChart()
    chart.load_from_json(data)
    chart.render_and_save(str(args.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
