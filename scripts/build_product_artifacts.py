#!/usr/bin/env python3
"""Build the committed CivicDecision product-surface artifacts."""

from __future__ import annotations

import argparse
from pathlib import Path

from civicdecision.product.build import build_product_artifacts

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, default=ROOT / "catalog/product")
    args = parser.parse_args()
    result = build_product_artifacts(args.root, args.output)
    print(f"created {len(result.artifact_paths)} product artifacts in {result.output_directory}")


if __name__ == "__main__":
    main()
