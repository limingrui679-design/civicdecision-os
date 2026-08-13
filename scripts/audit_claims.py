#!/usr/bin/env python3
"""Audit governed project claims against committed evidence and current public state."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from civicdecision.claim_audit import ClaimAuditError, audit_claims  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--policy", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument(
        "--refresh-public-state",
        action="store_true",
        help="check the dated GitHub repository-state assertion against the official API",
    )
    args = parser.parse_args()
    report = audit_claims(
        args.root,
        policy_path=args.policy,
        refresh_public_state=args.refresh_public_state,
    )
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.report is not None:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    if report["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ClaimAuditError) as exc:
        raise SystemExit(f"claim audit failed closed: {exc}") from exc
