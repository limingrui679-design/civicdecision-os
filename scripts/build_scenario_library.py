#!/usr/bin/env python3
"""Build the committed CivicDecision 240-design scenario library."""

from __future__ import annotations

import argparse
from pathlib import Path

from civicdecision.scenario_library.build import build_scenario_library

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, default=ROOT / "catalog/scenario-library")
    args = parser.parse_args()
    result = build_scenario_library(args.root, args.output)
    print(
        f"created {len(result.artifact_paths)} scenario-library files: "
        f"{len(result.design_paths)} designs and {len(result.family_paths)} families"
    )


if __name__ == "__main__":
    main()
