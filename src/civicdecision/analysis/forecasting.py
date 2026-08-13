"""Deterministic baseline forecasting with rolling-origin and conformal diagnostics."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from enum import StrEnum
from itertools import pairwise
from math import ceil, sqrt
from statistics import fmean

from pydantic import Field, field_validator, model_validator

from civicdecision.errors import AnalysisError
from civicdecision.protocols.base import (
    IDENTIFIER_PATTERN,
    StrictModel,
    canonical_json,
    ensure_aware,
    sha256_bytes,
)
from civicdecision.protocols.evidence import EvidenceType


class ForecastMethod(StrEnum):
    NAIVE = "naive"
    DRIFT = "drift"
    MOVING_AVERAGE = "moving-average"
    SEASONAL_NAIVE = "seasonal-naive"


class ForecastStatus(StrEnum):
    COMPLETED = "completed"
    INSUFFICIENT_EVIDENCE = "insufficient-evidence"


class TimeSeriesPoint(StrictModel):
    timestamp: datetime
    value: float

    @field_validator("timestamp")
    @classmethod
    def aware(cls, value: datetime) -> datetime:
        return ensure_aware(value, "time-series timestamp")


class ForecastConfig(StrictModel):
    horizon: int = Field(default=7, ge=1, le=366)
    backtest_folds: int = Field(default=8, ge=1, le=100)
    minimum_backtest_folds: int = Field(default=3, ge=1, le=100)
    minimum_train_size: int = Field(default=14, ge=2, le=100_000)
    moving_average_window: int = Field(default=7, ge=2, le=366)
    seasonal_period: int = Field(default=7, ge=2, le=366)
    interval_level: float = Field(default=0.90, gt=0.5, lt=1)
    require_nonnegative: bool = True
    methods: list[ForecastMethod] = Field(
        default_factory=lambda: [
            ForecastMethod.NAIVE,
            ForecastMethod.DRIFT,
            ForecastMethod.MOVING_AVERAGE,
            ForecastMethod.SEASONAL_NAIVE,
        ],
        min_length=1,
    )

    @model_validator(mode="after")
    def configuration_integrity(self) -> ForecastConfig:
        if self.minimum_backtest_folds > self.backtest_folds:
            raise ValueError("minimum_backtest_folds cannot exceed backtest_folds")
        if len(self.methods) != len(set(self.methods)):
            raise ValueError("forecast methods must be unique")
        return self


class ForecastMetrics(StrictModel):
    observations: int = Field(ge=1)
    mae: float = Field(ge=0)
    rmse: float = Field(ge=0)
    wape: float | None = Field(default=None, ge=0)
    bias: float
    empirical_interval_coverage: float = Field(ge=0, le=1)
    mean_interval_width: float = Field(ge=0)


class ForecastFold(StrictModel):
    origin_timestamp: datetime
    target_timestamps: list[datetime] = Field(min_length=1)
    actual: list[float] = Field(min_length=1)
    predicted: list[float] = Field(min_length=1)
    absolute_errors: list[float] = Field(min_length=1)

    @model_validator(mode="after")
    def aligned(self) -> ForecastFold:
        lengths = {
            len(self.target_timestamps),
            len(self.actual),
            len(self.predicted),
            len(self.absolute_errors),
        }
        if len(lengths) != 1:
            raise ValueError("forecast fold vectors must align")
        return self


class ForecastCandidate(StrictModel):
    method: ForecastMethod
    eligible: bool
    exclusion_reason: str | None = None
    folds: list[ForecastFold] = Field(default_factory=list)
    metrics: ForecastMetrics | None = None
    conformal_radius: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def eligibility_integrity(self) -> ForecastCandidate:
        if self.eligible:
            if not self.folds or self.metrics is None or self.conformal_radius is None:
                raise ValueError("eligible forecast candidates require folds, metrics, and radius")
            if self.exclusion_reason is not None:
                raise ValueError("eligible forecast candidates cannot have an exclusion reason")
        elif not self.exclusion_reason:
            raise ValueError("ineligible forecast candidates require an exclusion reason")
        return self


class ForecastValue(StrictModel):
    timestamp: datetime
    point: float
    lower: float
    upper: float

    @model_validator(mode="after")
    def interval_contains_point(self) -> ForecastValue:
        if not self.lower <= self.point <= self.upper:
            raise ValueError("forecast interval must contain its point prediction")
        return self


class ForecastRun(StrictModel):
    schema_version: str = "1.0.0"
    run_id: str = Field(pattern=IDENTIFIER_PATTERN)
    series_id: str = Field(pattern=IDENTIFIER_PATTERN)
    created_at: datetime
    data_cutoff: datetime
    source_refs: list[str] = Field(min_length=1)
    status: ForecastStatus
    evidence_type: EvidenceType = EvidenceType.ESTIMATED
    config: ForecastConfig
    observation_count: int = Field(ge=0)
    interval_seconds: float | None = Field(default=None, gt=0)
    candidates: list[ForecastCandidate] = Field(min_length=1)
    selected_method: ForecastMethod | None = None
    forecast: list[ForecastValue] = Field(default_factory=list)
    diagnostics: list[str] = Field(min_length=1)
    limitations: list[str] = Field(min_length=1)
    failure_reason: str | None = None

    @field_validator("created_at", "data_cutoff")
    @classmethod
    def aware(cls, value: datetime) -> datetime:
        return ensure_aware(value, "forecast run datetime")

    @field_validator("source_refs")
    @classmethod
    def unique_sources(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("forecast source references must be unique")
        return value

    @field_validator("evidence_type")
    @classmethod
    def estimated_only(cls, value: EvidenceType) -> EvidenceType:
        if value is not EvidenceType.ESTIMATED:
            raise ValueError("forecast runs are estimated evidence")
        return value

    @model_validator(mode="after")
    def outcome_integrity(self) -> ForecastRun:
        methods = [candidate.method for candidate in self.candidates]
        if len(methods) != len(set(methods)):
            raise ValueError("forecast candidate methods must be unique")
        if methods != self.config.methods:
            raise ValueError("forecast candidates must follow the configured method order")
        if self.status is ForecastStatus.COMPLETED:
            if self.selected_method is None or len(self.forecast) != self.config.horizon:
                raise ValueError("completed forecasts require a winner and full horizon")
            winner = next(
                (item for item in self.candidates if item.method is self.selected_method), None
            )
            if winner is None or not winner.eligible:
                raise ValueError("selected forecast method must be eligible")
            if self.failure_reason is not None:
                raise ValueError("completed forecasts cannot have a failure reason")
        else:
            if self.selected_method is not None or self.forecast:
                raise ValueError("insufficient forecasts cannot select a method or emit values")
            if not self.failure_reason:
                raise ValueError("insufficient forecasts require a failure reason")
        return self

    def content_hash(self) -> str:
        return sha256_bytes(canonical_json(self))


def _required_history(method: ForecastMethod, config: ForecastConfig) -> int:
    requirements = {
        ForecastMethod.NAIVE: 1,
        ForecastMethod.DRIFT: 2,
        ForecastMethod.MOVING_AVERAGE: config.moving_average_window,
        ForecastMethod.SEASONAL_NAIVE: config.seasonal_period,
    }
    return max(config.minimum_train_size, requirements[method])


def _predict(
    method: ForecastMethod,
    history: list[float],
    horizon: int,
    config: ForecastConfig,
) -> list[float]:
    if not history:
        raise AnalysisError("forecast history cannot be empty")
    predictions: list[float] = []
    extended = list(history)
    if method is ForecastMethod.DRIFT and len(history) < 2:
        raise AnalysisError("drift forecasting requires two observations")
    for step in range(1, horizon + 1):
        if method is ForecastMethod.NAIVE:
            prediction = history[-1]
        elif method is ForecastMethod.DRIFT:
            prediction = history[-1] + step * (history[-1] - history[0]) / (len(history) - 1)
        elif method is ForecastMethod.MOVING_AVERAGE:
            if len(extended) < config.moving_average_window:
                raise AnalysisError("moving-average history is shorter than its window")
            prediction = fmean(extended[-config.moving_average_window :])
        else:
            if len(extended) < config.seasonal_period:
                raise AnalysisError("seasonal-naive history is shorter than its period")
            prediction = extended[-config.seasonal_period]
        if config.require_nonnegative:
            prediction = max(0.0, prediction)
        prediction = float(prediction)
        predictions.append(prediction)
        extended.append(prediction)
    return predictions


def _conformal_radius(errors: list[float], level: float) -> float:
    if not errors:
        raise AnalysisError("conformal calibration requires errors")
    ordered = sorted(errors)
    rank = min(len(ordered), ceil((len(ordered) + 1) * level))
    return ordered[rank - 1]


def _metrics(actual: list[float], predicted: list[float], radius: float) -> ForecastMetrics:
    if len(actual) != len(predicted) or not actual:
        raise AnalysisError("forecast metric vectors must be non-empty and aligned")
    errors = [
        prediction - observation for observation, prediction in zip(actual, predicted, strict=True)
    ]
    absolute = [abs(value) for value in errors]
    denominator = sum(abs(value) for value in actual)
    return ForecastMetrics(
        observations=len(actual),
        mae=fmean(absolute),
        rmse=sqrt(fmean(value * value for value in errors)),
        wape=sum(absolute) / denominator if denominator else None,
        bias=fmean(errors),
        empirical_interval_coverage=sum(value <= radius for value in absolute) / len(absolute),
        mean_interval_width=2 * radius,
    )


def _candidate(
    method: ForecastMethod,
    points: list[TimeSeriesPoint],
    config: ForecastConfig,
) -> ForecastCandidate:
    required = _required_history(method, config)
    last_origin = len(points) - config.horizon
    origins = list(range(required, last_origin + 1))
    origins = origins[-config.backtest_folds :]
    if len(origins) < config.minimum_backtest_folds:
        return ForecastCandidate(
            method=method,
            eligible=False,
            exclusion_reason=(
                "requires at least "
                f"{required + config.horizon + config.minimum_backtest_folds - 1} "
                "regular observations for the configured rolling-origin evidence"
            ),
        )
    folds: list[ForecastFold] = []
    all_actual: list[float] = []
    all_predicted: list[float] = []
    for origin in origins:
        actual = [item.value for item in points[origin : origin + config.horizon]]
        predicted = _predict(
            method,
            [item.value for item in points[:origin]],
            config.horizon,
            config,
        )
        absolute = [abs(a - p) for a, p in zip(actual, predicted, strict=True)]
        folds.append(
            ForecastFold(
                origin_timestamp=points[origin - 1].timestamp,
                target_timestamps=[
                    item.timestamp for item in points[origin : origin + config.horizon]
                ],
                actual=actual,
                predicted=predicted,
                absolute_errors=absolute,
            )
        )
        all_actual.extend(actual)
        all_predicted.extend(predicted)
    residuals = [abs(a - p) for a, p in zip(all_actual, all_predicted, strict=True)]
    radius = _conformal_radius(residuals, config.interval_level)
    return ForecastCandidate(
        method=method,
        eligible=True,
        folds=folds,
        metrics=_metrics(all_actual, all_predicted, radius),
        conformal_radius=radius,
    )


def run_baseline_forecast(
    *,
    run_id: str,
    series_id: str,
    points: list[TimeSeriesPoint],
    source_refs: list[str],
    config: ForecastConfig | None = None,
    created_at: datetime | None = None,
) -> ForecastRun:
    """Select a transparent baseline using rolling-origin error and emit calibrated intervals."""

    active = config or ForecastConfig()
    if not points:
        raise AnalysisError("forecasting requires at least one observation")
    ordered = sorted(points, key=lambda item: item.timestamp)
    if ordered != points:
        raise AnalysisError("forecast observations must be sorted by timestamp")
    if len({item.timestamp for item in points}) != len(points):
        raise AnalysisError("forecast timestamps must be unique")
    intervals = [
        (current.timestamp - previous.timestamp).total_seconds()
        for previous, current in pairwise(points)
    ]
    interval_seconds = intervals[0] if intervals else None
    if interval_seconds is not None and (
        interval_seconds <= 0 or any(value != interval_seconds for value in intervals)
    ):
        raise AnalysisError("forecast observations must use a positive regular interval")
    candidates = [_candidate(method, points, active) for method in active.methods]
    eligible = [item for item in candidates if item.eligible]
    timestamp = created_at or datetime.now(UTC)
    limitations = [
        "Backtest performance does not establish causal effects or future policy impact.",
        "Intervals are split-conformal-style empirical residual bands over the declared folds; "
        "they do not guarantee coverage under distribution shift.",
        "Baseline methods omit exogenous variables, structural breaks, and operational feedback.",
    ]
    if not eligible or interval_seconds is None:
        reason = (
            "No configured method has enough regular history and rolling-origin folds."
            if interval_seconds is not None
            else "At least two regularly spaced observations are required to infer a horizon."
        )
        return ForecastRun(
            run_id=run_id,
            series_id=series_id,
            created_at=timestamp,
            data_cutoff=points[-1].timestamp,
            source_refs=source_refs,
            status=ForecastStatus.INSUFFICIENT_EVIDENCE,
            config=active,
            observation_count=len(points),
            interval_seconds=interval_seconds,
            candidates=candidates,
            diagnostics=[reason],
            limitations=limitations,
            failure_reason=reason,
        )
    winner = sorted(
        eligible,
        key=lambda item: (
            item.metrics.wape if item.metrics and item.metrics.wape is not None else float("inf"),
            item.metrics.mae if item.metrics else float("inf"),
            item.method.value,
        ),
    )[0]
    assert winner.conformal_radius is not None
    point_values = _predict(
        winner.method,
        [item.value for item in points],
        active.horizon,
        active,
    )
    step = timedelta(seconds=interval_seconds)
    forecast = []
    for index, value in enumerate(point_values, start=1):
        lower = value - winner.conformal_radius
        if active.require_nonnegative:
            lower = max(0.0, lower)
        forecast.append(
            ForecastValue(
                timestamp=points[-1].timestamp + index * step,
                point=value,
                lower=lower,
                upper=value + winner.conformal_radius,
            )
        )
    return ForecastRun(
        run_id=run_id,
        series_id=series_id,
        created_at=timestamp,
        data_cutoff=points[-1].timestamp,
        source_refs=source_refs,
        status=ForecastStatus.COMPLETED,
        config=active,
        observation_count=len(points),
        interval_seconds=interval_seconds,
        candidates=candidates,
        selected_method=winner.method,
        forecast=forecast,
        diagnostics=[
            f"Selected {winner.method.value} by minimum rolling-origin WAPE, then MAE.",
            "Calibrated the interval radius from "
            f"{winner.metrics.observations if winner.metrics else 0} held-out errors.",
            "All candidate exclusions and fold-level predictions remain serialized for audit.",
        ],
        limitations=limitations,
    )


__all__ = [
    "ForecastCandidate",
    "ForecastConfig",
    "ForecastFold",
    "ForecastMethod",
    "ForecastRun",
    "ForecastStatus",
    "ForecastValue",
    "TimeSeriesPoint",
    "run_baseline_forecast",
]
