#!/usr/bin/env python3
"""Smoke-test an installed CivicDecision wheel against an extracted no-Git source archive."""

from __future__ import annotations

import argparse
import asyncio
import importlib.metadata
import json
import platform
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI

import civicdecision
from civicdecision import __version__
from civicdecision.api import create_app
from civicdecision.plugins import load_plugin_package, scaffold_plugin
from civicdecision.product.models import ProductTier
from civicdecision.sdk import CivicDecisionSDK


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def _run_cli(*arguments: str) -> str:
    result = subprocess.run(
        [sys.executable, "-m", "civicdecision.cli", *arguments],
        check=True,
        capture_output=True,
        text=True,
        timeout=120,
    )
    return result.stdout.strip()


async def _smoke_api(app: FastAPI) -> dict[str, Any]:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://release-smoke",
    ) as client:
        meta = await client.get(
            "/api/v1/meta",
            headers={"x-request-id": "release-smoke-1234"},
        )
        require(meta.status_code == 200, "API metadata route failed")
        require(meta.json()["scenario_library_designs"] == 240, "API catalog drift")
        require(meta.headers.get("x-request-id") == "release-smoke-1234", "request ID drift")
        etag = meta.headers.get("etag", "")
        require(etag.startswith('W/"') and etag.endswith('"'), "API weak ETag is missing")
        cached = await client.get("/api/v1/meta", headers={"if-none-match": etag})
        cross_resource = await client.get(
            "/api/v1/designs",
            params={"limit": 1},
            headers={"if-none-match": etag},
        )
        missing = await client.get("/api/v1/not-a-route", headers={"if-none-match": "*"})
        invalid = await client.get("/api/v1/designs", params={"limit": 101})
        mutation = await client.post("/api/v1/meta")
        require(cached.status_code == 304 and not cached.content, "conditional GET drift")
        require(cross_resource.status_code == 200, "ETag crossed representation boundaries")
        require(missing.status_code == 404, "unknown route was incorrectly cached")
        require(invalid.status_code == 422, "invalid query did not fail closed")
        require(mutation.status_code == 405, "read-only API accepted a mutation")
        require(
            missing.headers["content-type"].startswith("application/problem+json"),
            "problem response media type drift",
        )
        openapi = await client.get("/api/openapi.json")
        require(openapi.status_code == 200, "OpenAPI route failed")
        require(len(openapi.json()["paths"]) == 19, "OpenAPI path count drift")
        explorer = await client.get("/")
        asset = await client.get("/assets/app.js")
        require(explorer.status_code == asset.status_code == 200, "packaged explorer failed")
        require("default-src 'self'" in explorer.headers["content-security-policy"], "CSP drift")
        require(asset.headers["x-content-type-options"] == "nosniff", "security headers drift")
    return {
        "openapi_paths": 19,
        "read_only_negative_release": True,
        "representation_scoped_etag": True,
        "security_headers": True,
        "web_explorer": True,
    }


def smoke(repository_root: Path) -> dict[str, Any]:
    root = repository_root.resolve(strict=True)
    require(not (root / ".git").exists(), "smoke source must not contain Git metadata")
    module_origin = Path(civicdecision.__file__).resolve(strict=True)
    require(
        not module_origin.is_relative_to(root),
        "civicdecision import resolved to the source archive instead of the installed wheel",
    )
    distribution = importlib.metadata.distribution("civicdecision")
    distribution_files = list(distribution.files or [])
    installed_version = distribution.version
    require(installed_version == __version__ == "0.8.0", "installed version sources disagree")
    require(_run_cli("version") == __version__, "installed CLI version output disagrees")
    require(
        any(str(path) == "civicdecision/web/index.html" for path in distribution_files),
        "installed wheel is missing its web explorer",
    )

    sdk = CivicDecisionSDK.open(root)
    summary = sdk.summary()
    require(summary.software_version == __version__, "catalog and installed software disagree")
    require(summary.exposed_city_records == 258, "unexpected highest-tier city count")
    require(summary.scenario_library_designs == 240, "unexpected scenario-design count")
    require(summary.scenario_library_families == 30, "unexpected design-family count")
    require(summary.reference_implemented_designs == 12, "unexpected reference-design count")
    require(summary.design_only_scenarios == 228, "unexpected design-only count")
    require(summary.scenario_library_audit_passed, "scenario-library audit is not passing")
    require(sdk.cities(tier=ProductTier.DEEP, limit=100).pagination.total == 8, "Tier-D drift")
    require(sdk.designs(limit=1).pagination.total == 240, "SDK design pagination drift")
    families = sdk.design_families(limit=1)
    require(families.pagination.total == 30, "SDK family pagination drift")
    family = sdk.design_family(families.items[0].family_id)
    require(len(family.designs) == 8, "a scenario family does not expose exactly eight designs")
    evidence = sdk.scenario_library_evidence()
    require(evidence.design_count == 240 and evidence.audit_passed, "SDK audit evidence drift")

    app = create_app(root)
    api = asyncio.run(_smoke_api(app))

    with tempfile.TemporaryDirectory(prefix="civicdecision-plugin-smoke-") as temporary:
        plugin_root = Path(temporary) / "release-smoke-plugin"
        generated = scaffold_plugin(
            plugin_root,
            plugin_id="release-smoke",
            name="Release Smoke Plugin",
            author="CivicDecision release verifier",
        )
        package = load_plugin_package(
            plugin_root,
            allowlisted_plugin_ids={"release-smoke"},
        )
        require(len(generated) == 2, "plugin scaffold inventory drift")
        require(len(package.adapters) == 1, "plugin loader adapter count drift")

    return {
        "archive_has_git_metadata": False,
        "api": api,
        "catalog_fingerprint": summary.catalog_fingerprint,
        "cli_version": __version__,
        "distribution_file_count": len(distribution_files),
        "installed_version": installed_version,
        "module_origin_relative_to_environment": module_origin.relative_to(
            Path(sys.prefix).resolve()
        ).as_posix(),
        "plugin": {"data_only_scaffold_files": 2, "validated_adapters": 1},
        "python": platform.python_version(),
        "sdk": {
            "design_families": summary.scenario_library_families,
            "designs": summary.scenario_library_designs,
            "tier_d_cities": 8,
        },
        "source_archive_root": root.name,
        "wheel_import_isolated_from_source": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    report = smoke(args.repository_root)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
