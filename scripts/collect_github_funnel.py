"""Collect a bounded GitHub discovery-and-trial snapshot without persisting credentials."""

from __future__ import annotations

import argparse
import http.client
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

API_ROOT = "https://api.github.com"


def request_json(path: str, token: str) -> Any:
    request = urllib.request.Request(
        f"{API_ROOT}{path}",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "User-Agent": "civicdecision-funnel-audit",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            if exc.code < 500 or attempt == 2:
                detail = exc.read().decode("utf-8", errors="replace")[:500]
                raise RuntimeError(f"GitHub API {exc.code} for {path}: {detail}") from exc
        except (
            ConnectionError,
            http.client.IncompleteRead,
            http.client.RemoteDisconnected,
            TimeoutError,
            urllib.error.URLError,
        ) as exc:
            if attempt == 2:
                raise RuntimeError(f"GitHub API transport failure for {path}: {exc}") from exc
        time.sleep(0.5 * (attempt + 1))
    raise AssertionError("unreachable GitHub API retry state")


def collect(repo: str, token: str) -> dict[str, Any]:
    repository = request_json(f"/repos/{repo}", token)
    views = request_json(f"/repos/{repo}/traffic/views", token)
    clones = request_json(f"/repos/{repo}/traffic/clones", token)
    referrers = request_json(f"/repos/{repo}/traffic/popular/referrers", token)
    paths = request_json(f"/repos/{repo}/traffic/popular/paths", token)
    releases = request_json(f"/repos/{repo}/releases?per_page=20", token)

    release_assets = [
        {
            "tag": release["tag_name"],
            "name": asset["name"],
            "downloads": asset["download_count"],
            "size_bytes": asset["size"],
        }
        for release in releases
        for asset in release.get("assets", [])
    ]

    return {
        "schema_version": "1.0.0",
        "collected_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "repository": repo,
        "signals": {
            "stars": repository["stargazers_count"],
            "forks": repository["forks_count"],
            "subscribers": repository["subscribers_count"],
            "open_issues": repository["open_issues_count"],
            "views_14_days": views,
            "clones_14_days": clones,
            "popular_referrers": referrers,
            "popular_paths": paths,
            "release_assets": release_assets,
        },
        "claim_boundary": [
            "Traffic values can update with delay and cover GitHub's bounded retention window.",
            "Views, clones, downloads, forks, and stars do not establish deployment, adoption, "
            "or impact.",
            "External reproduction and domain review require separate public records.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default="limingrui679-design/civicdecision-os")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        parser.error("GITHUB_TOKEN is required and must not be committed or printed")
    report = collect(args.repo, token)
    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(payload, encoding="utf-8")
        print(f"wrote {args.output}")
    else:
        sys.stdout.write(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
