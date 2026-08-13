#!/usr/bin/env python3
"""Measure bounded local product performance against declared review budgets."""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import platform
import statistics
import tempfile
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TypeVar

import httpx

from civicdecision import __version__
from civicdecision.api import create_app
from civicdecision.deep.models import ApplicationSuite
from civicdecision.product.build import build_product_artifacts
from civicdecision.product.store import ArtifactStore
from civicdecision.scenario_library.build import build_scenario_library
from civicdecision.scenario_library.models import DecisionType, ImplementationStatus

T = TypeVar("T")

DEFAULT_BUDGETS_MS = {
    "cold_store_initialization_p95": 5_000.0,
    "store_compound_design_query_p95": 25.0,
    "store_design_detail_p95": 25.0,
    "api_meta_p95": 100.0,
    "api_compound_design_query_p95": 150.0,
    "api_design_detail_p95": 150.0,
    "api_family_detail_p95": 150.0,
    "product_build": 30_000.0,
    "scenario_library_build": 30_000.0,
}


def _percentile(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    index = max(0, math.ceil(percentile * len(ordered)) - 1)
    return ordered[index]


def _summary(samples: list[float]) -> dict[str, float | int]:
    return {
        "samples": len(samples),
        "min_ms": round(min(samples), 3),
        "median_ms": round(statistics.median(samples), 3),
        "p95_ms": round(_percentile(samples, 0.95), 3),
        "max_ms": round(max(samples), 3),
    }


def _measure(operation: Callable[[], T], iterations: int) -> tuple[list[float], T]:
    samples: list[float] = []
    last: T | None = None
    for _ in range(iterations):
        started = time.perf_counter_ns()
        last = operation()
        samples.append((time.perf_counter_ns() - started) / 1_000_000)
    assert last is not None
    return samples, last


async def _api_measurements(
    store: ArtifactStore,
    iterations: int,
) -> tuple[dict[str, dict[str, float | int]], dict[str, Any]]:
    app = create_app(store=store)
    requests = {
        "api_meta": ("/api/v1/meta", {}),
        "api_compound_design_query": (
            "/api/v1/designs",
            {
                "suite": "climate-disaster-resilience",
                "family_id": "climate.extreme-heat",
                "decision_type": "site",
                "implementation_status": "design-only",
                "q": "cooling center",
                "limit": 20,
            },
        ),
        "api_design_detail": (
            "/api/v1/designs/scenario.climate.extreme-heat.cooling-center-network.v1",
            {},
        ),
        "api_family_detail": ("/api/v1/design-families/climate.extreme-heat", {}),
    }
    timing: dict[str, dict[str, float | int]] = {}
    observations: dict[str, Any] = {}
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://benchmark.local",
    ) as client:
        for name, (path, params) in requests.items():
            warm = await client.get(path, params=params)
            warm.raise_for_status()
            samples: list[float] = []
            response = warm
            for _ in range(iterations):
                started = time.perf_counter_ns()
                response = await client.get(path, params=params)
                samples.append((time.perf_counter_ns() - started) / 1_000_000)
                response.raise_for_status()
            timing[name] = _summary(samples)
            observations[name] = {
                "response_bytes": len(response.content),
                "status_code": response.status_code,
                "etag": response.headers.get("etag"),
            }
    return timing, observations


def benchmark_repository(
    repository_root: Path,
    *,
    iterations: int,
    cold_iterations: int,
    include_builds: bool,
) -> dict[str, Any]:
    repository_root = repository_root.resolve(strict=True)
    cold_samples, cold_store = _measure(
        lambda: ArtifactStore(repository_root, verify_sources=True),
        cold_iterations,
    )
    store = cold_store

    design_query_samples, design_page = _measure(
        lambda: store.list_scenario_designs(
            suite=ApplicationSuite.CLIMATE_DISASTER,
            family_id="climate.extreme-heat",
            decision_type=DecisionType.SITE,
            implementation_status=ImplementationStatus.DESIGN_ONLY,
            query="cooling center",
            limit=20,
        ),
        iterations,
    )
    design_detail_samples, design_detail = _measure(
        lambda: store.scenario_design_detail(
            "scenario.climate.extreme-heat.cooling-center-network.v1"
        ),
        iterations,
    )
    api_timing, api_observations = asyncio.run(_api_measurements(store, iterations))

    timing: dict[str, dict[str, float | int]] = {
        "cold_store_initialization": _summary(cold_samples),
        "store_compound_design_query": _summary(design_query_samples),
        "store_design_detail": _summary(design_detail_samples),
        **api_timing,
    }
    build_observations: dict[str, Any] = {"included": include_builds}
    if include_builds:
        with tempfile.TemporaryDirectory(prefix="civicdecision-performance-") as temporary:
            temporary_root = Path(temporary)
            started = time.perf_counter_ns()
            scenario_result = build_scenario_library(
                repository_root,
                temporary_root / "scenario-library",
            )
            scenario_ms = (time.perf_counter_ns() - started) / 1_000_000
            started = time.perf_counter_ns()
            product_result = build_product_artifacts(
                repository_root,
                temporary_root / "product",
            )
            product_ms = (time.perf_counter_ns() - started) / 1_000_000
            timing["scenario_library_build"] = _summary([scenario_ms])
            timing["product_build"] = _summary([product_ms])
            build_observations.update(
                {
                    "scenario_library_files": len(scenario_result.artifact_paths),
                    "product_files": len(product_result.artifact_paths),
                }
            )

    observed_budget_values = {
        "cold_store_initialization_p95": timing["cold_store_initialization"]["p95_ms"],
        "store_compound_design_query_p95": timing["store_compound_design_query"]["p95_ms"],
        "store_design_detail_p95": timing["store_design_detail"]["p95_ms"],
        "api_meta_p95": timing["api_meta"]["p95_ms"],
        "api_compound_design_query_p95": timing["api_compound_design_query"]["p95_ms"],
        "api_design_detail_p95": timing["api_design_detail"]["p95_ms"],
        "api_family_detail_p95": timing["api_family_detail"]["p95_ms"],
    }
    if include_builds:
        observed_budget_values.update(
            {
                "scenario_library_build": timing["scenario_library_build"]["max_ms"],
                "product_build": timing["product_build"]["max_ms"],
            }
        )
    checks = [
        {
            "metric": metric,
            "observed_ms": observed,
            "budget_ms": DEFAULT_BUDGETS_MS[metric],
            "status": "passed" if observed <= DEFAULT_BUDGETS_MS[metric] else "failed",
        }
        for metric, observed in observed_budget_values.items()
    ]

    committed_sizes = {
        "scenario_library_bytes": sum(
            path.stat().st_size
            for path in (repository_root / "catalog/scenario-library").rglob("*")
            if path.is_file()
        ),
        "product_projection_bytes": sum(
            path.stat().st_size
            for path in (repository_root / "catalog/product").rglob("*")
            if path.is_file()
        ),
        "packaged_web_asset_bytes": sum(
            path.stat().st_size
            for path in (repository_root / "src/civicdecision/web").rglob("*")
            if path.is_file()
        ),
    }
    return {
        "schema_version": "1.0.0",
        "checked_at": datetime.now(UTC).isoformat(),
        "software_version": __version__,
        "catalog_fingerprint": store.catalog_fingerprint,
        "environment": {
            "python": platform.python_version(),
            "implementation": platform.python_implementation(),
            "platform": platform.platform(),
            "processor": platform.processor() or "not-reported",
        },
        "configuration": {
            "warm_iterations_per_operation": iterations,
            "cold_store_iterations": cold_iterations,
            "source_hash_verification": True,
            "in_process_asgi_transport": True,
            "builds_included": include_builds,
        },
        "timing": timing,
        "observations": {
            "compound_design_query_total": design_page.pagination.total,
            "design_detail_id": design_detail.design.design_id,
            "api": api_observations,
            "builds": build_observations,
            "committed_sizes": committed_sizes,
        },
        "budget_checks": checks,
        "all_budgets_passed": all(item["status"] == "passed" for item in checks),
        "boundary": [
            "These are local single-process measurements, not production load-test evidence.",
            "ASGI timings exclude network, TLS, proxy, container, and multi-user contention.",
            "A passed budget does not establish public availability, scalability, or "
            "service-level guarantees.",
            "Regressions should be compared on equivalent hardware and Python versions.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path)
    parser.add_argument("--iterations", type=int, default=30)
    parser.add_argument("--cold-iterations", type=int, default=3)
    parser.add_argument("--skip-builds", action="store_true")
    args = parser.parse_args()
    if args.iterations < 5 or args.cold_iterations < 1:
        parser.error("iterations must be at least 5 and cold iterations at least 1")
    report = benchmark_repository(
        args.root,
        iterations=args.iterations,
        cold_iterations=args.cold_iterations,
        include_builds=not args.skip_builds,
    )
    serialized = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized, encoding="utf-8")
    print(serialized, end="")
    if not report["all_budgets_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
