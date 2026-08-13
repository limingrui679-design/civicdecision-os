from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from civicdecision.benchmarks.build import (
    build_milestone_4_benchmarks,
    historical_replay_evidence,
    optimization_task_evidence,
)
from civicdecision.benchmarks.models import (
    BenchmarkArtifact,
    BenchmarkEvidenceSummary,
    BenchmarkRegistry,
    HistoricalReplay,
)
from civicdecision.errors import AnalysisError
from civicdecision.optimization.portfolio import PortfolioOptimizationRun
from civicdecision.protocols.base import sha256_file

ROOT = Path(__file__).parents[1]
STANDARDIZED = ROOT / "catalog/standardized-cities"
NASA = ROOT / "examples/data/tier-s/nasa-power"


def test_small_benchmark_build_is_deterministic_and_has_all_categories(
    tmp_path: Path,
) -> None:
    first = build_milestone_4_benchmarks(
        standardized_directory=STANDARDIZED,
        nasa_source_directory=NASA,
        output_directory=tmp_path / "first",
        replay_city_count=2,
        optimization_task_count=10,
    )
    build_milestone_4_benchmarks(
        standardized_directory=STANDARDIZED,
        nasa_source_directory=NASA,
        output_directory=tmp_path / "second",
        replay_city_count=2,
        optimization_task_count=10,
    )
    first_files = sorted(
        path.relative_to(tmp_path / "first")
        for path in (tmp_path / "first").rglob("*")
        if path.is_file()
    )
    second_files = sorted(
        path.relative_to(tmp_path / "second")
        for path in (tmp_path / "second").rglob("*")
        if path.is_file()
    )
    assert first_files == second_files
    assert all(
        (tmp_path / "first" / relative).read_bytes()
        == (tmp_path / "second" / relative).read_bytes()
        for relative in first_files
    )
    registry = BenchmarkRegistry.model_validate_json(first.registry_path.read_bytes())
    assert registry.historical_replays == 4
    assert registry.optimization_tasks == 10
    assert registry.engine_qualification_runs == 5
    assert len(registry.artifacts) == 19
    assert len(first.artifact_paths) == 19
    assert first.evidence_summary_path.exists()
    assert first.summary_csv_path.exists()
    assert first.replay_evidence_csv_path.exists()
    assert first.optimization_evidence_csv_path.exists()
    assert first.qualification_evidence_csv_path.exists()
    assert first.summary_markdown_path.exists()
    assert first.checksum_path.exists()
    assert all(
        sha256_file(tmp_path / "first" / artifact.relative_path) == artifact.content_hash
        for artifact in registry.artifacts
    )
    evidence = BenchmarkEvidenceSummary.model_validate_json(
        first.evidence_summary_path.read_bytes()
    )
    assert len(evidence.historical_replays) == 4
    assert len(evidence.optimization_tasks) == 10
    assert len(evidence.engine_qualification_runs) == 5
    assert evidence.baseline_comparisons == 7
    assert registry.evidence_summary_content_hash == sha256_file(first.evidence_summary_path)
    assert registry.artifact_set_hash == evidence.artifact_set_hash
    replay_artifact = next(item for item in registry.artifacts if item.kind == "historical-replay")
    replay = HistoricalReplay.model_validate_json(
        (tmp_path / "first" / replay_artifact.relative_path).read_bytes()
    )
    assert historical_replay_evidence(replay, replay_artifact.content_hash) == next(
        item for item in evidence.historical_replays if item.replay_id == replay.replay_id
    )
    optimization_artifact = next(
        item for item in registry.artifacts if item.kind == "optimization-task"
    )
    optimization = PortfolioOptimizationRun.model_validate_json(
        (tmp_path / "first" / optimization_artifact.relative_path).read_bytes()
    )
    assert optimization_task_evidence(optimization, optimization_artifact.content_hash) == next(
        item for item in evidence.optimization_tasks if item.run_id == optimization.run_id
    )


def test_replay_has_strict_cutoff_and_holdout_alignment(tmp_path: Path) -> None:
    built = build_milestone_4_benchmarks(
        standardized_directory=STANDARDIZED,
        nasa_source_directory=NASA,
        output_directory=tmp_path,
        replay_city_count=1,
        optimization_task_count=1,
    )
    registry = BenchmarkRegistry.model_validate_json(built.registry_path.read_bytes())
    replay_artifact = next(item for item in registry.artifacts if item.kind == "historical-replay")
    replay = HistoricalReplay.model_validate_json(
        (tmp_path / replay_artifact.relative_path).read_bytes()
    )
    assert replay.data_cutoff < replay.evaluation_start
    assert replay.evaluation_end > replay.evaluation_start
    assert len(replay.actual) == 30
    assert len(replay.forecast_run.forecast) == 30
    assert replay.forecast_run.data_cutoff == replay.data_cutoff


def test_optimizer_task_families_include_all_statuses(tmp_path: Path) -> None:
    built = build_milestone_4_benchmarks(
        standardized_directory=STANDARDIZED,
        nasa_source_directory=NASA,
        output_directory=tmp_path,
        replay_city_count=1,
        optimization_task_count=10,
    )
    registry = BenchmarkRegistry.model_validate_json(built.registry_path.read_bytes())
    runs = [
        PortfolioOptimizationRun.model_validate_json((tmp_path / item.relative_path).read_bytes())
        for item in registry.artifacts
        if item.kind == "optimization-task"
    ]
    assert {run.status.value for run in runs} == {"optimal", "infeasible", "search-limited"}
    assert all(run.selected_plan_id is None for run in runs if run.status.value != "optimal")


def test_benchmark_target_guards(tmp_path: Path) -> None:
    with pytest.raises(AnalysisError, match="must be positive"):
        build_milestone_4_benchmarks(
            standardized_directory=STANDARDIZED,
            nasa_source_directory=NASA,
            output_directory=tmp_path,
            replay_city_count=0,
            optimization_task_count=1,
        )
    with pytest.raises(AnalysisError, match="exceeds Tier-S coverage"):
        build_milestone_4_benchmarks(
            standardized_directory=STANDARDIZED,
            nasa_source_directory=NASA,
            output_directory=tmp_path,
            replay_city_count=31,
            optimization_task_count=1,
        )


def test_benchmark_registry_rejects_unsafe_duplicate_or_miscounted_entries(
    tmp_path: Path,
) -> None:
    built = build_milestone_4_benchmarks(
        standardized_directory=STANDARDIZED,
        nasa_source_directory=NASA,
        output_directory=tmp_path,
        replay_city_count=1,
        optimization_task_count=1,
    )
    payload = json.loads(built.registry_path.read_text())
    payload["artifacts"][0]["relative_path"] = "../escape.json"
    with pytest.raises(ValidationError, match="safe relative"):
        BenchmarkRegistry.model_validate(payload)

    payload = json.loads(built.registry_path.read_text())
    payload["artifacts"].append(payload["artifacts"][0])
    payload["engine_qualification_runs"] += 1
    with pytest.raises(ValidationError, match="ids must be unique"):
        BenchmarkRegistry.model_validate(payload)

    payload = json.loads(built.registry_path.read_text())
    payload["historical_replays"] += 1
    with pytest.raises(ValidationError, match="category counts must match"):
        BenchmarkRegistry.model_validate(payload)

    payload = json.loads(built.registry_path.read_text())
    payload["historical_replays"] -= 1
    payload["optimization_tasks"] += 1
    with pytest.raises(ValidationError, match="category counts must match"):
        BenchmarkRegistry.model_validate(payload)

    payload = json.loads(built.registry_path.read_text())
    payload["status_counts"] = {"fabricated": len(payload["artifacts"])}
    with pytest.raises(ValidationError, match="status counts must match"):
        BenchmarkRegistry.model_validate(payload)

    payload = json.loads(built.registry_path.read_text())
    payload["artifacts"][0]["kind"] = "unsupported-kind"
    with pytest.raises(ValidationError, match="unsupported artifact kinds"):
        BenchmarkRegistry.model_validate(payload)

    payload = json.loads(built.registry_path.read_text())
    payload["artifact_set_hash"] = "sha256:" + "0" * 64
    with pytest.raises(ValidationError, match="artifact-set hash"):
        BenchmarkRegistry.model_validate(payload)


def test_historical_replay_contract_rejects_cutoff_and_method_drift(
    tmp_path: Path,
) -> None:
    build_milestone_4_benchmarks(
        standardized_directory=STANDARDIZED,
        nasa_source_directory=NASA,
        output_directory=tmp_path,
        replay_city_count=1,
        optimization_task_count=1,
    )
    path = next((tmp_path / "historical-replays").glob("*.json"))
    payload = json.loads(path.read_text())
    payload["evaluation_start"] = payload["data_cutoff"]
    with pytest.raises(ValidationError, match="strictly forward"):
        HistoricalReplay.model_validate(payload)

    payload = json.loads(path.read_text())
    payload["selected_method"] = "naive"
    if payload["forecast_run"]["selected_method"] == "naive":
        payload["selected_method"] = "drift"
    with pytest.raises(ValidationError, match="must match the forecast run"):
        HistoricalReplay.model_validate(payload)

    payload = json.loads(path.read_text())
    payload["forecast_run"].update(
        status="insufficient-evidence",
        selected_method=None,
        forecast=[],
        failure_reason="Synthetic negative forecast fixture.",
    )
    with pytest.raises(ValidationError, match="completed forecast run"):
        HistoricalReplay.model_validate(payload)

    payload.update(
        status="insufficient-evidence",
        selected_method=None,
        evaluation_mae=None,
        evaluation_rmse=None,
        evaluation_wape=None,
        empirical_interval_coverage=None,
    )
    negative = HistoricalReplay.model_validate(payload)
    assert negative.status.value == "insufficient-evidence"

    payload["evaluation_mae"] = 1
    with pytest.raises(ValidationError, match="cannot emit evaluation results"):
        HistoricalReplay.model_validate(payload)


def test_benchmark_artifact_requires_safe_path() -> None:
    with pytest.raises(ValidationError, match="safe relative"):
        BenchmarkArtifact(
            artifact_id="bad",
            kind="bad",
            relative_path="/absolute.json",
            content_hash="sha256:" + "0" * 64,
            status="failed",
            source_refs=["source"],
            evidence_boundary="Invalid fixture.",
        )


def test_evidence_summary_rejects_aggregate_or_hash_drift(tmp_path: Path) -> None:
    built = build_milestone_4_benchmarks(
        standardized_directory=STANDARDIZED,
        nasa_source_directory=NASA,
        output_directory=tmp_path,
        replay_city_count=1,
        optimization_task_count=10,
    )
    payload = json.loads(built.evidence_summary_path.read_text())
    payload["method_counts"] = {"fabricated": len(payload["historical_replays"])}
    with pytest.raises(ValidationError, match="method counts must match"):
        BenchmarkEvidenceSummary.model_validate(payload)

    payload = json.loads(built.evidence_summary_path.read_text())
    payload["total_evaluated_plans"] += 1
    with pytest.raises(ValidationError, match="total evaluations must match"):
        BenchmarkEvidenceSummary.model_validate(payload)

    payload = json.loads(built.evidence_summary_path.read_text())
    payload["historical_replays"][0]["content_hash"] = "sha256:" + "0" * 64
    with pytest.raises(ValidationError, match="row hashes must match"):
        BenchmarkEvidenceSummary.model_validate(payload)
