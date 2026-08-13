"""Identification-gated difference-in-differences with auditable diagnostics."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from math import sqrt
from statistics import NormalDist, fmean

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


class CausalRunStatus(StrEnum):
    IDENTIFICATION_PASSED = "identification-passed"
    INSUFFICIENT_EVIDENCE = "insufficient-evidence"


class DiagnosticStatus(StrEnum):
    PASS = "pass"
    FAIL = "fail"


class PanelObservation(StrictModel):
    unit_id: str = Field(pattern=IDENTIFIER_PATTERN)
    period: int
    outcome: float
    treated_group: bool


class DifferenceInDifferencesDesign(StrictModel):
    study_id: str = Field(pattern=IDENTIFIER_PATTERN)
    estimand: str = Field(min_length=1)
    treatment_definition: str = Field(min_length=1)
    comparison_definition: str = Field(min_length=1)
    assignment_mechanism: str = Field(min_length=1)
    no_anticipation_rationale: str = Field(min_length=1)
    parallel_trends_rationale: str = Field(min_length=1)
    no_interference_rationale: str = Field(min_length=1)
    source_refs: list[str] = Field(min_length=1)
    limitations: list[str] = Field(min_length=1)

    @field_validator("source_refs")
    @classmethod
    def unique_sources(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("causal design source references must be unique")
        return value


class DifferenceInDifferencesConfig(StrictModel):
    intervention_period: int
    minimum_units_per_group: int = Field(default=5, ge=2, le=1_000_000)
    minimum_pre_periods: int = Field(default=4, ge=3, le=10_000)
    minimum_post_periods: int = Field(default=2, ge=1, le=10_000)
    confidence_level: float = Field(default=0.95, gt=0.5, lt=0.999)
    pretrend_slope_equivalence_margin: float = Field(gt=0)
    placebo_effect_equivalence_margin: float = Field(gt=0)
    require_balanced_panel: bool = True

    @field_validator("require_balanced_panel")
    @classmethod
    def current_estimator_requires_balance(cls, value: bool) -> bool:
        if not value:
            raise ValueError("the current DID estimator requires a balanced panel")
        return value


class CausalDiagnostic(StrictModel):
    id: str = Field(pattern=IDENTIFIER_PATTERN)
    status: DiagnosticStatus
    measured: float | int | str | bool
    threshold: float | int | str | bool
    method: str = Field(min_length=1)
    details: str = Field(min_length=1)


class EffectEstimate(StrictModel):
    label: str = Field(min_length=1)
    estimate: float
    standard_error: float = Field(ge=0)
    confidence_level: float = Field(gt=0.5, lt=0.999)
    lower: float
    upper: float
    p_value: float = Field(ge=0, le=1)
    treated_units: int = Field(ge=2)
    comparison_units: int = Field(ge=2)

    @model_validator(mode="after")
    def interval_integrity(self) -> EffectEstimate:
        if not self.lower <= self.estimate <= self.upper:
            raise ValueError("effect interval must contain the estimate")
        return self


class EventTimeEffect(StrictModel):
    relative_period: int
    calendar_period: int
    estimate: EffectEstimate


class DifferenceInDifferencesRun(StrictModel):
    schema_version: str = "1.0.0"
    run_id: str = Field(pattern=IDENTIFIER_PATTERN)
    created_at: datetime
    data_cutoff_period: int
    status: CausalRunStatus
    evidence_type: EvidenceType
    causal_claim_issued: bool
    design: DifferenceInDifferencesDesign
    config: DifferenceInDifferencesConfig
    observation_count: int = Field(ge=0)
    unit_count: int = Field(ge=0)
    pre_periods: list[int]
    post_periods: list[int]
    diagnostics: list[CausalDiagnostic] = Field(min_length=1)
    primary_effect: EffectEstimate | None = None
    event_time_effects: list[EventTimeEffect] = Field(default_factory=list)
    placebo_effects: list[EventTimeEffect] = Field(default_factory=list)
    interpretation: str = Field(min_length=1)
    limitations: list[str] = Field(min_length=1)
    failure_reason: str | None = None

    @field_validator("created_at")
    @classmethod
    def aware(cls, value: datetime) -> datetime:
        return ensure_aware(value, "causal run created_at")

    @model_validator(mode="after")
    def claim_gate(self) -> DifferenceInDifferencesRun:
        diagnostic_ids = [item.id for item in self.diagnostics]
        if len(diagnostic_ids) != len(set(diagnostic_ids)):
            raise ValueError("causal diagnostic ids must be unique")
        all_pass = all(item.status is DiagnosticStatus.PASS for item in self.diagnostics)
        if self.status is CausalRunStatus.IDENTIFICATION_PASSED:
            if self.evidence_type is not EvidenceType.CAUSAL or not self.causal_claim_issued:
                raise ValueError("passed identification requires an explicit causal evidence type")
            if self.primary_effect is None or not self.event_time_effects:
                raise ValueError("passed identification requires effect estimates")
            if not all_pass:
                raise ValueError("passed identification cannot contain failed diagnostics")
            if self.failure_reason is not None:
                raise ValueError("passed identification cannot have a failure reason")
        else:
            if self.evidence_type is not EvidenceType.ESTIMATED or self.causal_claim_issued:
                raise ValueError("insufficient designs must remain estimated associations")
            if not self.failure_reason:
                raise ValueError("insufficient designs require a failure reason")
        return self

    def content_hash(self) -> str:
        return sha256_bytes(canonical_json(self))


def _sample_variance(values: list[float]) -> float:
    if len(values) < 2:
        raise AnalysisError("effect estimation requires at least two units per group")
    mean = fmean(values)
    return sum((value - mean) ** 2 for value in values) / (len(values) - 1)


def _estimate(
    label: str,
    treated_changes: list[float],
    comparison_changes: list[float],
    confidence_level: float,
) -> EffectEstimate:
    if len(treated_changes) < 2 or len(comparison_changes) < 2:
        raise AnalysisError("difference-in-differences requires two units per group")
    effect = fmean(treated_changes) - fmean(comparison_changes)
    standard_error = sqrt(
        _sample_variance(treated_changes) / len(treated_changes)
        + _sample_variance(comparison_changes) / len(comparison_changes)
    )
    critical = NormalDist().inv_cdf(0.5 + confidence_level / 2)
    if standard_error == 0:
        p_value = 1.0 if effect == 0 else 0.0
    else:
        p_value = 2 * (1 - NormalDist().cdf(abs(effect / standard_error)))
    return EffectEstimate(
        label=label,
        estimate=effect,
        standard_error=standard_error,
        confidence_level=confidence_level,
        lower=effect - critical * standard_error,
        upper=effect + critical * standard_error,
        p_value=p_value,
        treated_units=len(treated_changes),
        comparison_units=len(comparison_changes),
    )


def _slope(periods: list[int], values: list[float]) -> float:
    if len(periods) != len(values) or len(periods) < 2:
        raise AnalysisError("pretrend slopes require aligned multi-period values")
    mean_period = fmean(periods)
    mean_value = fmean(values)
    denominator = sum((period - mean_period) ** 2 for period in periods)
    if denominator == 0:
        raise AnalysisError("pretrend periods must vary")
    return (
        sum(
            (period - mean_period) * (value - mean_value)
            for period, value in zip(periods, values, strict=True)
        )
        / denominator
    )


def _diagnostic(
    identifier: str,
    passed: bool,
    measured: float | int | str | bool,
    threshold: float | int | str | bool,
    method: str,
    details: str,
) -> CausalDiagnostic:
    return CausalDiagnostic(
        id=identifier,
        status=DiagnosticStatus.PASS if passed else DiagnosticStatus.FAIL,
        measured=measured,
        threshold=threshold,
        method=method,
        details=details,
    )


def _run(
    *,
    run_id: str,
    created_at: datetime,
    data_cutoff_period: int,
    status: CausalRunStatus,
    evidence_type: EvidenceType,
    causal_claim_issued: bool,
    design: DifferenceInDifferencesDesign,
    config: DifferenceInDifferencesConfig,
    observation_count: int,
    unit_count: int,
    pre_periods: list[int],
    post_periods: list[int],
    diagnostics: list[CausalDiagnostic],
    interpretation: str,
    limitations: list[str],
    primary_effect: EffectEstimate | None = None,
    event_time_effects: list[EventTimeEffect] | None = None,
    placebo_effects: list[EventTimeEffect] | None = None,
    failure_reason: str | None = None,
) -> DifferenceInDifferencesRun:
    return DifferenceInDifferencesRun(
        run_id=run_id,
        created_at=created_at,
        data_cutoff_period=data_cutoff_period,
        status=status,
        evidence_type=evidence_type,
        causal_claim_issued=causal_claim_issued,
        design=design,
        config=config,
        observation_count=observation_count,
        unit_count=unit_count,
        pre_periods=pre_periods,
        post_periods=post_periods,
        diagnostics=diagnostics,
        primary_effect=primary_effect,
        event_time_effects=event_time_effects or [],
        placebo_effects=placebo_effects or [],
        interpretation=interpretation,
        limitations=limitations,
        failure_reason=failure_reason,
    )


def run_difference_in_differences(
    *,
    run_id: str,
    design: DifferenceInDifferencesDesign,
    observations: list[PanelObservation],
    config: DifferenceInDifferencesConfig,
    created_at: datetime | None = None,
) -> DifferenceInDifferencesRun:
    """Estimate a two-group panel DID and issue a causal type only after strict gates pass."""

    if not observations:
        raise AnalysisError("difference-in-differences requires panel observations")
    keys = [(item.unit_id, item.period) for item in observations]
    if len(keys) != len(set(keys)):
        raise AnalysisError("panel unit-period keys must be unique")
    unit_rows: dict[str, dict[int, PanelObservation]] = {}
    assignments: dict[str, bool] = {}
    for item in observations:
        unit_rows.setdefault(item.unit_id, {})[item.period] = item
        previous = assignments.setdefault(item.unit_id, item.treated_group)
        if previous is not item.treated_group:
            raise AnalysisError("treatment-group assignment must be constant within unit")
    periods = sorted({item.period for item in observations})
    pre_periods = [period for period in periods if period < config.intervention_period]
    post_periods = [period for period in periods if period >= config.intervention_period]
    treated_units = sorted(unit for unit, treated in assignments.items() if treated)
    comparison_units = sorted(unit for unit, treated in assignments.items() if not treated)
    expected_periods = set(periods)
    balanced = all(set(rows) == expected_periods for rows in unit_rows.values())
    diagnostics = [
        _diagnostic(
            "treated-unit-count",
            len(treated_units) >= config.minimum_units_per_group,
            len(treated_units),
            f">={config.minimum_units_per_group}",
            "Count unique units assigned to the treated group.",
            "Small groups make unit-level uncertainty unstable.",
        ),
        _diagnostic(
            "comparison-unit-count",
            len(comparison_units) >= config.minimum_units_per_group,
            len(comparison_units),
            f">={config.minimum_units_per_group}",
            "Count unique units assigned to the never-treated comparison group.",
            "The design requires a contemporaneous comparison group.",
        ),
        _diagnostic(
            "pre-period-count",
            len(pre_periods) >= config.minimum_pre_periods,
            len(pre_periods),
            f">={config.minimum_pre_periods}",
            "Count distinct periods strictly before intervention.",
            "Multiple pre-periods are required for observable trend diagnostics.",
        ),
        _diagnostic(
            "post-period-count",
            len(post_periods) >= config.minimum_post_periods,
            len(post_periods),
            f">={config.minimum_post_periods}",
            "Count distinct periods at or after intervention.",
            "The declared post window must meet the configured evidence floor.",
        ),
        _diagnostic(
            "balanced-panel",
            balanced,
            balanced,
            config.require_balanced_panel,
            "Compare each unit's period keys with the complete panel period set.",
            "The current estimator does not weight or impute unbalanced observations.",
        ),
    ]
    basic_pass = all(item.status is DiagnosticStatus.PASS for item in diagnostics)
    timestamp = created_at or datetime.now(UTC)
    limitations = [
        *design.limitations,
        "Passing observable diagnostics cannot prove parallel counterfactual trends, no "
        "anticipation, or no interference.",
        "The estimator is an unadjusted two-group panel contrast with unit-level change variance.",
        "The causal label applies only to the declared estimand, units, periods, and design.",
    ]
    if not basic_pass:
        failed = [item.id for item in diagnostics if item.status is DiagnosticStatus.FAIL]
        reason = f"Required design diagnostics failed: {', '.join(failed)}."
        return _run(
            run_id=run_id,
            created_at=timestamp,
            data_cutoff_period=max(periods),
            design=design,
            config=config,
            observation_count=len(observations),
            unit_count=len(unit_rows),
            pre_periods=pre_periods,
            post_periods=post_periods,
            limitations=limitations,
            status=CausalRunStatus.INSUFFICIENT_EVIDENCE,
            evidence_type=EvidenceType.ESTIMATED,
            causal_claim_issued=False,
            diagnostics=diagnostics,
            interpretation=(
                "The panel can be retained as a descriptive association input, but the current "
                "design does not clear the causal identification gate."
            ),
            failure_reason=reason,
        )

    def values(unit: str, selected_periods: list[int]) -> list[float]:
        return [unit_rows[unit][period].outcome for period in selected_periods]

    treated_slopes = [_slope(pre_periods, values(unit, pre_periods)) for unit in treated_units]
    comparison_slopes = [
        _slope(pre_periods, values(unit, pre_periods)) for unit in comparison_units
    ]
    slope_estimate = _estimate(
        "treated-minus-comparison pre-period slope",
        treated_slopes,
        comparison_slopes,
        config.confidence_level,
    )
    slope_pass = (
        slope_estimate.lower > -config.pretrend_slope_equivalence_margin
        and slope_estimate.upper < config.pretrend_slope_equivalence_margin
    )
    diagnostics.append(
        _diagnostic(
            "pretrend-slope-equivalence",
            slope_pass,
            abs(slope_estimate.estimate)
            + NormalDist().inv_cdf(0.5 + config.confidence_level / 2)
            * slope_estimate.standard_error,
            f"<{config.pretrend_slope_equivalence_margin}",
            "Unit-level pre-period OLS slopes; require the full two-sided confidence interval "
            "inside the declared practical-equivalence margin.",
            "This is an observable pretrend diagnostic, not proof of counterfactual trends.",
        )
    )
    baseline_period = pre_periods[0]
    placebo_effects: list[EventTimeEffect] = []
    critical = NormalDist().inv_cdf(0.5 + config.confidence_level / 2)
    placebo_pass = True
    for period in pre_periods[1:]:
        effect = _estimate(
            f"placebo DID at pre-period {period}",
            [
                unit_rows[unit][period].outcome - unit_rows[unit][baseline_period].outcome
                for unit in treated_units
            ],
            [
                unit_rows[unit][period].outcome - unit_rows[unit][baseline_period].outcome
                for unit in comparison_units
            ],
            config.confidence_level,
        )
        placebo_effects.append(
            EventTimeEffect(
                relative_period=period - config.intervention_period,
                calendar_period=period,
                estimate=effect,
            )
        )
        placebo_pass = placebo_pass and (
            abs(effect.estimate) + critical * effect.standard_error
            < config.placebo_effect_equivalence_margin
        )
    diagnostics.append(
        _diagnostic(
            "placebo-effect-equivalence",
            placebo_pass,
            max(
                abs(item.estimate.estimate) + critical * item.estimate.standard_error
                for item in placebo_effects
            ),
            f"<{config.placebo_effect_equivalence_margin}",
            "Contrast each later pre-period with the first pre-period and require every full "
            "confidence interval inside the declared practical-equivalence margin.",
            "Placebo equivalence can reject obvious differential pre-movements but not latent "
            "bias.",
        )
    )
    pre_means = {
        unit: fmean(values(unit, pre_periods)) for unit in [*treated_units, *comparison_units]
    }
    event_effects = []
    for period in post_periods:
        effect = _estimate(
            f"DID effect at post-period {period}",
            [unit_rows[unit][period].outcome - pre_means[unit] for unit in treated_units],
            [unit_rows[unit][period].outcome - pre_means[unit] for unit in comparison_units],
            config.confidence_level,
        )
        event_effects.append(
            EventTimeEffect(
                relative_period=period - config.intervention_period,
                calendar_period=period,
                estimate=effect,
            )
        )
    primary = _estimate(
        "average post-period DID effect",
        [fmean(values(unit, post_periods)) - pre_means[unit] for unit in treated_units],
        [fmean(values(unit, post_periods)) - pre_means[unit] for unit in comparison_units],
        config.confidence_level,
    )
    all_pass = all(item.status is DiagnosticStatus.PASS for item in diagnostics)
    if all_pass:
        return _run(
            run_id=run_id,
            created_at=timestamp,
            data_cutoff_period=max(periods),
            design=design,
            config=config,
            observation_count=len(observations),
            unit_count=len(unit_rows),
            pre_periods=pre_periods,
            post_periods=post_periods,
            limitations=limitations,
            status=CausalRunStatus.IDENTIFICATION_PASSED,
            evidence_type=EvidenceType.CAUSAL,
            causal_claim_issued=True,
            diagnostics=diagnostics,
            primary_effect=primary,
            event_time_effects=event_effects,
            placebo_effects=placebo_effects,
            interpretation=(
                "The declared difference-in-differences design passes the implemented balance, "
                "sample-size, pretrend-equivalence, and placebo-equivalence gates. The estimate "
                "is causal only conditional on the documented untestable assumptions."
            ),
        )
    failed = [item.id for item in diagnostics if item.status is DiagnosticStatus.FAIL]
    reason = f"Identification diagnostics failed: {', '.join(failed)}."
    return _run(
        run_id=run_id,
        created_at=timestamp,
        data_cutoff_period=max(periods),
        design=design,
        config=config,
        observation_count=len(observations),
        unit_count=len(unit_rows),
        pre_periods=pre_periods,
        post_periods=post_periods,
        limitations=limitations,
        status=CausalRunStatus.INSUFFICIENT_EVIDENCE,
        evidence_type=EvidenceType.ESTIMATED,
        causal_claim_issued=False,
        diagnostics=diagnostics,
        primary_effect=primary,
        event_time_effects=event_effects,
        placebo_effects=placebo_effects,
        interpretation=(
            "A treated-versus-comparison association was estimated, but it is not released as "
            "causal because at least one identification diagnostic failed."
        ),
        failure_reason=reason,
    )


__all__ = [
    "CausalDiagnostic",
    "CausalRunStatus",
    "DiagnosticStatus",
    "DifferenceInDifferencesConfig",
    "DifferenceInDifferencesDesign",
    "DifferenceInDifferencesRun",
    "EffectEstimate",
    "EventTimeEffect",
    "PanelObservation",
    "run_difference_in_differences",
]
