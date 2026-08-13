"""Strict benchmark registry and historical replay contracts."""

from __future__ import annotations

import re
from collections import Counter
from datetime import datetime
from enum import StrEnum
from pathlib import PurePosixPath

from pydantic import Field, field_validator, model_validator

from civicdecision.analysis.forecasting import ForecastMethod, ForecastRun, ForecastStatus
from civicdecision.optimization.portfolio import ObjectiveStrategy, PortfolioRunStatus
from civicdecision.protocols.base import (
    IDENTIFIER_PATTERN,
    StrictModel,
    canonical_json,
    ensure_aware,
    sha256_bytes,
)
from civicdecision.protocols.evidence import EvidenceType

SHA256_VALUE_PATTERN = r"^sha256:[0-9a-f]{64}$"


def artifact_set_hash(values: dict[str, str]) -> str:
    return sha256_bytes(canonical_json(values))


class ReplayStatus(StrEnum):
    COMPLETED = "completed"
    INSUFFICIENT_EVIDENCE = "insufficient-evidence"


class HistoricalReplay(StrictModel):
    schema_version: str = "1.0.0"
    replay_id: str = Field(pattern=IDENTIFIER_PATTERN)
    created_at: datetime
    city_id: str = Field(pattern=IDENTIFIER_PATTERN)
    city_name: str = Field(min_length=1)
    source_artifact_id: str = Field(pattern=IDENTIFIER_PATTERN)
    source_content_hash: str = Field(pattern=SHA256_VALUE_PATTERN)
    parameter: str = Field(pattern=r"^[A-Z0-9_]+$")
    train_start: datetime
    data_cutoff: datetime
    evaluation_start: datetime
    evaluation_end: datetime
    actual: list[float] = Field(min_length=1)
    forecast_run: ForecastRun
    selected_method: ForecastMethod | None = None
    evaluation_mae: float | None = Field(default=None, ge=0)
    evaluation_rmse: float | None = Field(default=None, ge=0)
    evaluation_wape: float | None = Field(default=None, ge=0)
    empirical_interval_coverage: float | None = Field(default=None, ge=0, le=1)
    status: ReplayStatus
    diagnostics: list[str] = Field(min_length=1)
    limitations: list[str] = Field(min_length=1)

    @field_validator(
        "created_at",
        "train_start",
        "data_cutoff",
        "evaluation_start",
        "evaluation_end",
    )
    @classmethod
    def aware(cls, value: datetime) -> datetime:
        return ensure_aware(value, "historical replay datetime")

    @model_validator(mode="after")
    def replay_integrity(self) -> HistoricalReplay:
        if not self.train_start <= self.data_cutoff < self.evaluation_start <= self.evaluation_end:
            raise ValueError("historical replay time windows must be strictly forward")
        if self.forecast_run.data_cutoff != self.data_cutoff:
            raise ValueError("historical replay cutoff must match the forecast run")
        if self.status is ReplayStatus.COMPLETED:
            if self.forecast_run.status is not ForecastStatus.COMPLETED:
                raise ValueError("completed replays require a completed forecast run")
            if self.forecast_run.selected_method is not self.selected_method:
                raise ValueError("historical replay selected method must match the forecast run")
            if len(self.actual) != len(self.forecast_run.forecast):
                raise ValueError("historical replay actual and forecast horizons must align")
            if not self.forecast_run.forecast:
                raise ValueError("completed replays require forecast values")
            if (
                self.evaluation_mae is None
                or self.evaluation_rmse is None
                or self.empirical_interval_coverage is None
            ):
                raise ValueError("completed replays require evaluation metrics")
        elif self.forecast_run.status is not ForecastStatus.INSUFFICIENT_EVIDENCE:
            raise ValueError(
                "insufficient-evidence replays require an insufficient-evidence forecast run"
            )
        elif (
            self.selected_method is not None
            or self.evaluation_mae is not None
            or self.evaluation_rmse is not None
            or self.evaluation_wape is not None
            or self.empirical_interval_coverage is not None
        ):
            raise ValueError("insufficient-evidence replays cannot emit evaluation results")
        return self

    def content_hash(self) -> str:
        return sha256_bytes(canonical_json(self))


class BenchmarkArtifact(StrictModel):
    artifact_id: str = Field(pattern=IDENTIFIER_PATTERN)
    kind: str = Field(pattern=IDENTIFIER_PATTERN)
    relative_path: str = Field(min_length=1)
    content_hash: str = Field(pattern=SHA256_VALUE_PATTERN)
    status: str = Field(min_length=1)
    source_refs: list[str] = Field(min_length=1)
    evidence_boundary: str = Field(min_length=1)

    @field_validator("relative_path")
    @classmethod
    def safe_path(cls, value: str) -> str:
        path = PurePosixPath(value)
        if path.is_absolute() or ".." in path.parts or "\\" in value:
            raise ValueError("benchmark artifact paths must be safe relative POSIX paths")
        return value

    @field_validator("source_refs")
    @classmethod
    def unique_sources(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("benchmark artifact source references must be unique")
        return value


class HistoricalReplayEvidence(StrictModel):
    replay_id: str = Field(pattern=IDENTIFIER_PATTERN)
    city_id: str = Field(pattern=IDENTIFIER_PATTERN)
    city_name: str = Field(min_length=1)
    parameter: str = Field(pattern=r"^[A-Z0-9_]+$")
    source_artifact_id: str = Field(pattern=IDENTIFIER_PATTERN)
    data_cutoff: datetime
    evaluation_start: datetime
    evaluation_end: datetime
    training_observations: int = Field(ge=1)
    holdout_observations: int = Field(ge=1)
    selected_method: ForecastMethod
    evaluation_mae: float = Field(ge=0)
    evaluation_rmse: float = Field(ge=0)
    evaluation_wape: float | None = Field(default=None, ge=0)
    empirical_interval_coverage: float = Field(ge=0, le=1)
    content_hash: str = Field(pattern=SHA256_VALUE_PATTERN)

    @field_validator("data_cutoff", "evaluation_start", "evaluation_end")
    @classmethod
    def aware(cls, value: datetime) -> datetime:
        return ensure_aware(value, "historical replay evidence datetime")

    @model_validator(mode="after")
    def window_integrity(self) -> HistoricalReplayEvidence:
        if not self.data_cutoff < self.evaluation_start <= self.evaluation_end:
            raise ValueError("historical replay evidence windows must be forward")
        return self


class OptimizationTaskEvidence(StrictModel):
    run_id: str = Field(pattern=IDENTIFIER_PATTERN)
    status: PortfolioRunStatus
    objective_strategy: ObjectiveStrategy
    search_space_size: int = Field(ge=1)
    evaluated_plans: int = Field(ge=1)
    feasible_plans: int = Field(ge=0)
    retained_plans: int = Field(ge=1)
    enumeration_complete: bool
    baseline_feasible: bool
    baseline_objective: float
    selected_plan_id: str | None = Field(default=None, pattern=IDENTIFIER_PATTERN)
    selected_objective: float | None = None
    selected_objective_change_from_baseline: float | None = None
    pareto_frontier_plans: int = Field(ge=0)
    violated_constraint_ids: list[str]
    content_hash: str = Field(pattern=SHA256_VALUE_PATTERN)

    @field_validator("violated_constraint_ids")
    @classmethod
    def unique_violations(cls, value: list[str]) -> list[str]:
        if value != sorted(set(value)):
            raise ValueError("optimization evidence violations must be sorted and unique")
        return value

    @model_validator(mode="after")
    def selection_integrity(self) -> OptimizationTaskEvidence:
        selected = self.selected_plan_id is not None
        if selected != (self.selected_objective is not None) or selected != (
            self.selected_objective_change_from_baseline is not None
        ):
            raise ValueError("optimization evidence selection fields must be present together")
        if selected != (self.status is PortfolioRunStatus.OPTIMAL):
            raise ValueError("only optimal optimization evidence can retain a selection")
        if self.evaluated_plans > self.search_space_size:
            raise ValueError("optimization evidence cannot evaluate beyond its search space")
        if self.feasible_plans > self.evaluated_plans:
            raise ValueError("optimization evidence feasible plans cannot exceed evaluations")
        return self


class EngineQualificationEvidence(StrictModel):
    artifact_id: str = Field(pattern=IDENTIFIER_PATTERN)
    run_id: str = Field(pattern=IDENTIFIER_PATTERN)
    status: str = Field(min_length=1)
    evidence_type: EvidenceType
    source_refs: list[str] = Field(min_length=1)
    content_hash: str = Field(pattern=SHA256_VALUE_PATTERN)

    @field_validator("source_refs")
    @classmethod
    def unique_sources(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("qualification evidence source references must be unique")
        return value


class BenchmarkEvidenceSummary(StrictModel):
    schema_version: str = "1.0.0"
    summary_id: str = Field(pattern=IDENTIFIER_PATTERN)
    created_at: datetime
    artifact_set_hash: str = Field(pattern=SHA256_VALUE_PATTERN)
    run_artifact_hashes: dict[str, str] = Field(min_length=1)
    historical_replays: list[HistoricalReplayEvidence]
    optimization_tasks: list[OptimizationTaskEvidence]
    engine_qualification_runs: list[EngineQualificationEvidence]
    method_counts: dict[str, int]
    parameter_counts: dict[str, int]
    optimization_status_counts: dict[str, int]
    optimization_strategy_counts: dict[str, int]
    total_search_space_size: int = Field(ge=0)
    total_evaluated_plans: int = Field(ge=0)
    total_feasible_plans: int = Field(ge=0)
    baseline_comparisons: int = Field(ge=0)
    limitations: list[str] = Field(min_length=1)

    @field_validator("created_at")
    @classmethod
    def aware(cls, value: datetime) -> datetime:
        return ensure_aware(value, "benchmark evidence summary created_at")

    @field_validator("run_artifact_hashes")
    @classmethod
    def valid_artifact_hashes(cls, value: dict[str, str]) -> dict[str, str]:
        if any(not re.fullmatch(SHA256_VALUE_PATTERN, item) for item in value.values()):
            raise ValueError("benchmark evidence artifact hashes must be SHA-256 values")
        return value

    @model_validator(mode="after")
    def evidence_integrity(self) -> BenchmarkEvidenceSummary:
        replay_ids = [item.replay_id for item in self.historical_replays]
        optimization_ids = [item.run_id for item in self.optimization_tasks]
        qualification_ids = [item.artifact_id for item in self.engine_qualification_runs]
        all_ids = [*replay_ids, *optimization_ids, *qualification_ids]
        if len(all_ids) != len(set(all_ids)):
            raise ValueError("benchmark evidence artifact ids must be unique")
        if set(all_ids) != set(self.run_artifact_hashes):
            raise ValueError("benchmark evidence rows must exactly cover artifact hashes")
        row_hashes = (
            {item.replay_id: item.content_hash for item in self.historical_replays}
            | {item.run_id: item.content_hash for item in self.optimization_tasks}
            | {item.artifact_id: item.content_hash for item in self.engine_qualification_runs}
        )
        if row_hashes != self.run_artifact_hashes:
            raise ValueError("benchmark evidence row hashes must match artifact hashes")
        if self.artifact_set_hash != artifact_set_hash(self.run_artifact_hashes):
            raise ValueError("benchmark evidence artifact-set hash must match its artifact map")
        expected_method_counts = dict(
            sorted(Counter(item.selected_method.value for item in self.historical_replays).items())
        )
        expected_parameter_counts = dict(
            sorted(Counter(item.parameter for item in self.historical_replays).items())
        )
        expected_status_counts = dict(
            sorted(Counter(item.status.value for item in self.optimization_tasks).items())
        )
        expected_strategy_counts = dict(
            sorted(
                Counter(item.objective_strategy.value for item in self.optimization_tasks).items()
            )
        )
        if self.method_counts != expected_method_counts:
            raise ValueError("benchmark evidence method counts must match replay rows")
        if self.parameter_counts != expected_parameter_counts:
            raise ValueError("benchmark evidence parameter counts must match replay rows")
        if self.optimization_status_counts != expected_status_counts:
            raise ValueError("benchmark evidence status counts must match optimization rows")
        if self.optimization_strategy_counts != expected_strategy_counts:
            raise ValueError("benchmark evidence strategy counts must match optimization rows")
        if self.total_search_space_size != sum(
            item.search_space_size for item in self.optimization_tasks
        ):
            raise ValueError("benchmark evidence total search space must match optimization rows")
        if self.total_evaluated_plans != sum(
            item.evaluated_plans for item in self.optimization_tasks
        ):
            raise ValueError("benchmark evidence total evaluations must match optimization rows")
        if self.total_feasible_plans != sum(
            item.feasible_plans for item in self.optimization_tasks
        ):
            raise ValueError("benchmark evidence total feasible plans must match optimization rows")
        if self.baseline_comparisons != sum(
            item.selected_objective_change_from_baseline is not None
            for item in self.optimization_tasks
        ):
            raise ValueError("benchmark evidence baseline count must match optimization rows")
        return self

    def content_hash(self) -> str:
        return sha256_bytes(canonical_json(self))


class BenchmarkRegistry(StrictModel):
    schema_version: str = "1.0.0"
    registry_id: str = Field(pattern=IDENTIFIER_PATTERN)
    created_at: datetime
    artifacts: list[BenchmarkArtifact] = Field(min_length=1)
    historical_replays: int = Field(ge=0)
    optimization_tasks: int = Field(ge=0)
    engine_qualification_runs: int = Field(ge=0)
    status_counts: dict[str, int] = Field(min_length=1)
    evidence_summary_ref: str = Field(min_length=1)
    evidence_summary_content_hash: str = Field(pattern=SHA256_VALUE_PATTERN)
    artifact_set_hash: str = Field(pattern=SHA256_VALUE_PATTERN)
    limitations: list[str] = Field(min_length=1)

    @field_validator("created_at")
    @classmethod
    def aware(cls, value: datetime) -> datetime:
        return ensure_aware(value, "benchmark registry created_at")

    @field_validator("evidence_summary_ref")
    @classmethod
    def safe_summary_path(cls, value: str) -> str:
        path = PurePosixPath(value)
        if path.is_absolute() or ".." in path.parts or "\\" in value:
            raise ValueError("benchmark evidence summary path must be safe and relative")
        return value

    @model_validator(mode="after")
    def registry_integrity(self) -> BenchmarkRegistry:
        ids = [item.artifact_id for item in self.artifacts]
        paths = [item.relative_path for item in self.artifacts]
        if len(ids) != len(set(ids)):
            raise ValueError("benchmark artifact ids must be unique")
        if len(paths) != len(set(paths)):
            raise ValueError("benchmark artifact paths must be unique")
        supported_kinds = {
            "historical-replay",
            "optimization-task",
            "engine-qualification",
        }
        actual_kinds = Counter(item.kind for item in self.artifacts)
        unknown = set(actual_kinds) - supported_kinds
        if unknown:
            raise ValueError(f"benchmark registry contains unsupported artifact kinds: {unknown}")
        declared_kinds = {
            "historical-replay": self.historical_replays,
            "optimization-task": self.optimization_tasks,
            "engine-qualification": self.engine_qualification_runs,
        }
        if dict(actual_kinds) != {key: value for key, value in declared_kinds.items() if value}:
            raise ValueError("benchmark artifact category counts must match declared categories")
        actual_statuses = dict(sorted(Counter(item.status for item in self.artifacts).items()))
        if self.status_counts != actual_statuses:
            raise ValueError("benchmark status counts must match artifact statuses")
        expected_artifact_set_hash = artifact_set_hash(
            {item.artifact_id: item.content_hash for item in self.artifacts}
        )
        if self.artifact_set_hash != expected_artifact_set_hash:
            raise ValueError("benchmark artifact-set hash must match registered artifacts")
        return self

    def content_hash(self) -> str:
        return sha256_bytes(canonical_json(self))


__all__ = [
    "BenchmarkArtifact",
    "BenchmarkEvidenceSummary",
    "BenchmarkRegistry",
    "EngineQualificationEvidence",
    "HistoricalReplay",
    "HistoricalReplayEvidence",
    "OptimizationTaskEvidence",
    "ReplayStatus",
    "artifact_set_hash",
]
