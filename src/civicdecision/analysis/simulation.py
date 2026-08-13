"""Seeded Monte Carlo simulation with typed parameters and auditable sensitivity output."""

from __future__ import annotations

import hashlib
import json
import random
from datetime import UTC, datetime
from enum import StrEnum
from math import isfinite, sqrt
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


class DistributionKind(StrEnum):
    FIXED = "fixed"
    UNIFORM = "uniform"
    TRIANGULAR = "triangular"
    NORMAL = "normal"
    BERNOULLI = "bernoulli"
    EMPIRICAL = "empirical"


class SimulationStatus(StrEnum):
    COMPLETED = "completed"
    INSUFFICIENT_EVIDENCE = "insufficient-evidence"


class ThresholdDirection(StrEnum):
    AT_LEAST = "at-least"
    AT_MOST = "at-most"


class ParameterDistribution(StrictModel):
    parameter_id: str = Field(pattern=IDENTIFIER_PATTERN)
    unit: str = Field(min_length=1)
    kind: DistributionKind
    evidence_type: EvidenceType
    source_refs: list[str] = Field(default_factory=list)
    fixed_value: float | None = None
    minimum: float | None = None
    maximum: float | None = None
    mode: float | None = None
    mean: float | None = None
    standard_deviation: float | None = Field(default=None, gt=0)
    probability: float | None = Field(default=None, ge=0, le=1)
    empirical_values: list[float] = Field(default_factory=list)
    assumptions: list[str] = Field(min_length=1)
    limitations: list[str] = Field(min_length=1)

    @field_validator("source_refs")
    @classmethod
    def unique_sources(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("parameter source references must be unique")
        return value

    @model_validator(mode="after")
    def distribution_contract(self) -> ParameterDistribution:
        if self.evidence_type not in {EvidenceType.ESTIMATED, EvidenceType.PROPOSED}:
            raise ValueError("simulation parameters must be estimated or proposed")
        if self.evidence_type is EvidenceType.ESTIMATED and not self.source_refs:
            raise ValueError("estimated simulation parameters require source references")
        if self.kind is DistributionKind.FIXED and self.fixed_value is None:
            raise ValueError("fixed distributions require fixed_value")
        if self.kind is DistributionKind.UNIFORM and (
            self.minimum is None or self.maximum is None or self.minimum >= self.maximum
        ):
            raise ValueError("uniform distributions require minimum < maximum")
        if self.kind is DistributionKind.TRIANGULAR and (
            self.minimum is None
            or self.mode is None
            or self.maximum is None
            or not self.minimum <= self.mode <= self.maximum
            or self.minimum == self.maximum
        ):
            raise ValueError("triangular distributions require minimum <= mode <= maximum")
        if self.kind is DistributionKind.NORMAL:
            if self.mean is None or self.standard_deviation is None:
                raise ValueError("normal distributions require mean and standard_deviation")
            if (
                self.minimum is not None
                and self.maximum is not None
                and self.minimum > self.maximum
            ):
                raise ValueError("normal truncation minimum cannot exceed maximum")
        if self.kind is DistributionKind.BERNOULLI and self.probability is None:
            raise ValueError("Bernoulli distributions require probability")
        if self.kind is DistributionKind.EMPIRICAL and not self.empirical_values:
            raise ValueError("empirical distributions require values")
        return self


class SimulationTerm(StrictModel):
    parameter_id: str = Field(pattern=IDENTIFIER_PATTERN)
    coefficient: float


class SimulationModel(StrictModel):
    model_id: str = Field(pattern=IDENTIFIER_PATTERN)
    scenario_ref: str = Field(pattern=IDENTIFIER_PATTERN)
    outcome_id: str = Field(pattern=IDENTIFIER_PATTERN)
    outcome_unit: str = Field(min_length=1)
    intercept: float
    terms: list[SimulationTerm] = Field(min_length=1)
    floor: float | None = None
    ceiling: float | None = None
    method: str = Field(min_length=1)
    assumptions: list[str] = Field(min_length=1)
    limitations: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def model_integrity(self) -> SimulationModel:
        ids = [term.parameter_id for term in self.terms]
        if len(ids) != len(set(ids)):
            raise ValueError("simulation model parameter ids must be unique")
        if self.floor is not None and self.ceiling is not None and self.floor > self.ceiling:
            raise ValueError("simulation model floor cannot exceed ceiling")
        return self


class SimulationConfig(StrictModel):
    iterations: int = Field(default=10_000, ge=100, le=1_000_000)
    random_seed: int = Field(default=20260812, ge=0, le=2**32 - 1)
    quantiles: list[float] = Field(default_factory=lambda: [0.05, 0.25, 0.5, 0.75, 0.95])
    retained_draws: int = Field(default=25, ge=0, le=1_000)
    threshold: float | None = None
    threshold_direction: ThresholdDirection = ThresholdDirection.AT_LEAST

    @field_validator("quantiles")
    @classmethod
    def valid_quantiles(cls, value: list[float]) -> list[float]:
        if not value or any(item <= 0 or item >= 1 for item in value):
            raise ValueError("simulation quantiles must be strictly between zero and one")
        if value != sorted(set(value)):
            raise ValueError("simulation quantiles must be sorted and unique")
        return value


class QuantileEstimate(StrictModel):
    probability: float = Field(gt=0, lt=1)
    value: float


class SensitivityEstimate(StrictModel):
    parameter_id: str = Field(pattern=IDENTIFIER_PATTERN)
    pearson_correlation: float = Field(ge=-1, le=1)
    absolute_rank: int = Field(ge=1)
    method: str = Field(min_length=1)


class RetainedSimulationDraw(StrictModel):
    iteration: int = Field(ge=0)
    parameters: dict[str, float] = Field(min_length=1)
    outcome: float


class SimulationSummary(StrictModel):
    mean: float
    standard_deviation: float = Field(ge=0)
    minimum: float
    maximum: float
    quantiles: list[QuantileEstimate] = Field(min_length=1)
    threshold_probability: float | None = Field(default=None, ge=0, le=1)

    @model_validator(mode="after")
    def summary_integrity(self) -> SimulationSummary:
        if not self.minimum <= self.mean <= self.maximum:
            raise ValueError("simulation summary mean must lie within its range")
        probabilities = [item.probability for item in self.quantiles]
        if probabilities != sorted(set(probabilities)):
            raise ValueError("simulation summary quantiles must be sorted and unique")
        return self


class SimulationRun(StrictModel):
    schema_version: str = "1.0.0"
    run_id: str = Field(pattern=IDENTIFIER_PATTERN)
    created_at: datetime
    status: SimulationStatus
    evidence_type: EvidenceType = EvidenceType.SIMULATED
    model: SimulationModel
    config: SimulationConfig
    parameters: list[ParameterDistribution] = Field(min_length=1)
    summary: SimulationSummary | None = None
    sensitivity: list[SensitivityEstimate] = Field(default_factory=list)
    retained_draws: list[RetainedSimulationDraw] = Field(default_factory=list)
    draw_stream_hash: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")
    diagnostics: list[str] = Field(min_length=1)
    limitations: list[str] = Field(min_length=1)
    failure_reason: str | None = None

    @field_validator("created_at")
    @classmethod
    def aware(cls, value: datetime) -> datetime:
        return ensure_aware(value, "simulation run created_at")

    @field_validator("evidence_type")
    @classmethod
    def simulated_only(cls, value: EvidenceType) -> EvidenceType:
        if value is not EvidenceType.SIMULATED:
            raise ValueError("simulation runs must retain simulated evidence type")
        return value

    @model_validator(mode="after")
    def run_integrity(self) -> SimulationRun:
        parameter_ids = [item.parameter_id for item in self.parameters]
        if len(parameter_ids) != len(set(parameter_ids)):
            raise ValueError("simulation parameter ids must be unique")
        if self.status is SimulationStatus.COMPLETED:
            if set(parameter_ids) != {item.parameter_id for item in self.model.terms}:
                raise ValueError("simulation parameters must exactly match model terms")
            if self.summary is None or self.draw_stream_hash is None:
                raise ValueError("completed simulations require summary and draw hash")
            if len(self.sensitivity) != len(self.parameters):
                raise ValueError("completed simulations require sensitivity for every parameter")
            sensitivity_ids = [item.parameter_id for item in self.sensitivity]
            if set(sensitivity_ids) != set(parameter_ids) or len(sensitivity_ids) != len(
                set(sensitivity_ids)
            ):
                raise ValueError("simulation sensitivity must exactly cover unique parameters")
            if sorted(item.absolute_rank for item in self.sensitivity) != list(
                range(1, len(self.parameters) + 1)
            ):
                raise ValueError("simulation sensitivity ranks must be complete and unique")
            if len(self.retained_draws) != min(self.config.retained_draws, self.config.iterations):
                raise ValueError("completed simulations require the configured retained draws")
            if [item.iteration for item in self.retained_draws] != list(
                range(len(self.retained_draws))
            ):
                raise ValueError("retained simulation draws must be the ordered stream prefix")
            if any(set(item.parameters) != set(parameter_ids) for item in self.retained_draws):
                raise ValueError("retained simulation draws must exactly cover parameters")
            if [item.probability for item in self.summary.quantiles] != self.config.quantiles:
                raise ValueError("simulation summary quantiles must match configuration")
            if (self.config.threshold is None) != (self.summary.threshold_probability is None):
                raise ValueError("simulation threshold probability must match configuration")
            if self.failure_reason is not None:
                raise ValueError("completed simulations cannot have a failure reason")
        else:
            if (
                self.summary is not None
                or self.draw_stream_hash is not None
                or self.sensitivity
                or self.retained_draws
            ):
                raise ValueError("insufficient simulations cannot emit outcome summaries")
            if not self.failure_reason:
                raise ValueError("insufficient simulations require a failure reason")
        return self

    def content_hash(self) -> str:
        return sha256_bytes(canonical_json(self))


def _sample(distribution: ParameterDistribution, generator: random.Random) -> float:
    if distribution.kind is DistributionKind.FIXED:
        assert distribution.fixed_value is not None
        return distribution.fixed_value
    if distribution.kind is DistributionKind.UNIFORM:
        assert distribution.minimum is not None and distribution.maximum is not None
        return generator.uniform(distribution.minimum, distribution.maximum)
    if distribution.kind is DistributionKind.TRIANGULAR:
        assert (
            distribution.minimum is not None
            and distribution.mode is not None
            and distribution.maximum is not None
        )
        return generator.triangular(distribution.minimum, distribution.maximum, distribution.mode)
    if distribution.kind is DistributionKind.NORMAL:
        assert distribution.mean is not None and distribution.standard_deviation is not None
        value = generator.gauss(distribution.mean, distribution.standard_deviation)
        if distribution.minimum is not None:
            value = max(distribution.minimum, value)
        if distribution.maximum is not None:
            value = min(distribution.maximum, value)
        return value
    if distribution.kind is DistributionKind.BERNOULLI:
        assert distribution.probability is not None
        return float(generator.random() < distribution.probability)
    return generator.choice(distribution.empirical_values)


def _quantile(values: list[float], probability: float) -> float:
    if not values:
        raise AnalysisError("simulation quantiles require values")
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower_index = int(position)
    upper_index = min(lower_index + 1, len(ordered) - 1)
    fraction = position - lower_index
    return ordered[lower_index] + fraction * (ordered[upper_index] - ordered[lower_index])


def _correlation(left: list[float], right: list[float]) -> float:
    if len(left) != len(right) or not left:
        raise AnalysisError("sensitivity vectors must be non-empty and aligned")
    left_mean = fmean(left)
    right_mean = fmean(right)
    covariance = sum((a - left_mean) * (b - right_mean) for a, b in zip(left, right, strict=True))
    left_scale = sqrt(sum((value - left_mean) ** 2 for value in left))
    right_scale = sqrt(sum((value - right_mean) ** 2 for value in right))
    if left_scale == 0 or right_scale == 0:
        return 0.0
    return covariance / (left_scale * right_scale)


def _outcome(model: SimulationModel, values: dict[str, float]) -> float:
    output = model.intercept + sum(
        term.coefficient * values[term.parameter_id] for term in model.terms
    )
    if model.floor is not None:
        output = max(model.floor, output)
    if model.ceiling is not None:
        output = min(model.ceiling, output)
    if not isfinite(output):
        raise AnalysisError("simulation model produced a non-finite outcome")
    return output


def run_monte_carlo(
    *,
    run_id: str,
    model: SimulationModel,
    parameters: list[ParameterDistribution],
    config: SimulationConfig | None = None,
    created_at: datetime | None = None,
) -> SimulationRun:
    """Run a deterministic Monte Carlo sample stream under the declared parameter model."""

    active = config or SimulationConfig()
    parameter_ids = [item.parameter_id for item in parameters]
    if len(parameter_ids) != len(set(parameter_ids)):
        raise AnalysisError("simulation parameter ids must be unique")
    if set(parameter_ids) != {item.parameter_id for item in model.terms}:
        reason = "Simulation parameters do not exactly cover the model terms."
        return SimulationRun(
            run_id=run_id,
            created_at=created_at or datetime.now(UTC),
            status=SimulationStatus.INSUFFICIENT_EVIDENCE,
            model=model,
            config=active,
            parameters=parameters,
            diagnostics=[reason],
            limitations=[*model.limitations, reason],
            failure_reason=reason,
        )
    generator = random.Random(active.random_seed)
    parameter_draws: dict[str, list[float]] = {identifier: [] for identifier in parameter_ids}
    outcomes: list[float] = []
    retained: list[RetainedSimulationDraw] = []
    stream_digest = hashlib.sha256()
    ordered = sorted(parameters, key=lambda item: item.parameter_id)
    for iteration in range(active.iterations):
        draw = {item.parameter_id: _sample(item, generator) for item in ordered}
        output = _outcome(model, draw)
        for identifier, value in draw.items():
            parameter_draws[identifier].append(value)
        outcomes.append(output)
        stream_record = json.dumps(
            {"iteration": iteration, "parameters": draw, "outcome": output},
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        stream_digest.update(len(stream_record).to_bytes(8, "big"))
        stream_digest.update(stream_record)
        if iteration < active.retained_draws:
            retained.append(
                RetainedSimulationDraw(
                    iteration=iteration,
                    parameters=draw,
                    outcome=output,
                )
            )
    mean = fmean(outcomes)
    deviation = sqrt(sum((value - mean) ** 2 for value in outcomes) / (len(outcomes) - 1))
    threshold_probability = None
    if active.threshold is not None:
        if active.threshold_direction is ThresholdDirection.AT_LEAST:
            threshold_probability = sum(value >= active.threshold for value in outcomes) / len(
                outcomes
            )
        else:
            threshold_probability = sum(value <= active.threshold for value in outcomes) / len(
                outcomes
            )
    sensitivity_values = [
        (
            identifier,
            _correlation(parameter_draws[identifier], outcomes),
        )
        for identifier in parameter_ids
    ]
    ranked = sorted(sensitivity_values, key=lambda item: (-abs(item[1]), item[0]))
    rank_by_id = {identifier: rank for rank, (identifier, _) in enumerate(ranked, start=1)}
    sensitivity = [
        SensitivityEstimate(
            parameter_id=identifier,
            pearson_correlation=correlation,
            absolute_rank=rank_by_id[identifier],
            method="Pearson correlation across the seeded joint Monte Carlo draw stream.",
        )
        for identifier, correlation in sensitivity_values
    ]
    return SimulationRun(
        run_id=run_id,
        created_at=created_at or datetime.now(UTC),
        status=SimulationStatus.COMPLETED,
        model=model,
        config=active,
        parameters=parameters,
        summary=SimulationSummary(
            mean=mean,
            standard_deviation=deviation,
            minimum=min(outcomes),
            maximum=max(outcomes),
            quantiles=[
                QuantileEstimate(probability=probability, value=_quantile(outcomes, probability))
                for probability in active.quantiles
            ],
            threshold_probability=threshold_probability,
        ),
        sensitivity=sensitivity,
        retained_draws=retained,
        draw_stream_hash=f"sha256:{stream_digest.hexdigest()}",
        diagnostics=[
            f"Generated {active.iterations} draws with explicit seed {active.random_seed}.",
            "Serialized the complete draw-stream hash and a bounded prefix for replay inspection.",
            "Ranked input association with output; sensitivity correlations are not causal "
            "effects.",
        ],
        limitations=[
            *model.limitations,
            "Outputs are simulated consequences of declared distributions and model structure, "
            "not observed outcomes.",
            "Parameter independence is assumed unless dependence is encoded outside this model.",
            "Monte Carlo precision does not resolve structural or source uncertainty.",
        ],
    )


__all__ = [
    "DistributionKind",
    "ParameterDistribution",
    "QuantileEstimate",
    "RetainedSimulationDraw",
    "SensitivityEstimate",
    "SimulationConfig",
    "SimulationModel",
    "SimulationRun",
    "SimulationStatus",
    "SimulationSummary",
    "SimulationTerm",
    "ThresholdDirection",
    "run_monte_carlo",
]
