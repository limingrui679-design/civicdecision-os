"""Deterministic uncertainty propagation, dominance, regret, and reversal diagnostics."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from math import sqrt
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


class ObjectiveSense(StrEnum):
    MAXIMIZE = "maximize"
    MINIMIZE = "minimize"


class UncertaintyStatus(StrEnum):
    ROBUST_WINNER = "robust-winner"
    REVERSAL_RISK = "reversal-risk"
    INSUFFICIENT_EVIDENCE = "insufficient-evidence"


class UncertaintyMethod(StrEnum):
    PAIRED_DRAWS = "paired-draws"
    INDEPENDENT_SUMMARIES = "independent-summaries"


class OptionDraws(StrictModel):
    option_id: str = Field(pattern=IDENTIFIER_PATTERN)
    values: list[float] = Field(min_length=2)
    source_refs: list[str] = Field(min_length=1)
    evidence_type: EvidenceType
    limitations: list[str] = Field(min_length=1)

    @field_validator("source_refs")
    @classmethod
    def unique_sources(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("option draw source references must be unique")
        return value

    @field_validator("evidence_type")
    @classmethod
    def allowed_type(cls, value: EvidenceType) -> EvidenceType:
        if value not in {EvidenceType.ESTIMATED, EvidenceType.SIMULATED}:
            raise ValueError("uncertainty options must be estimated or simulated")
        return value


class UncertaintyConfig(StrictModel):
    sense: ObjectiveSense
    confidence_level: float = Field(default=0.95, gt=0.5, lt=0.999)
    practical_equivalence_margin: float = Field(default=0, ge=0)
    robust_probability_threshold: float = Field(default=0.90, gt=0.5, le=1)
    maximum_expected_regret: float | None = Field(default=None, ge=0)
    require_paired_draws: bool = True


class OptionUncertaintySummary(StrictModel):
    option_id: str = Field(pattern=IDENTIFIER_PATTERN)
    draws: int = Field(ge=2)
    mean: float
    standard_deviation: float = Field(ge=0)
    lower: float
    upper: float
    probability_best: float = Field(ge=0, le=1)
    expected_regret: float = Field(ge=0)
    maximum_regret: float = Field(ge=0)
    dominated_probability: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def interval_integrity(self) -> OptionUncertaintySummary:
        if not self.lower <= self.mean <= self.upper:
            raise ValueError("uncertainty interval must contain the option mean")
        return self


class PairwiseDominance(StrictModel):
    option_a: str = Field(pattern=IDENTIFIER_PATTERN)
    option_b: str = Field(pattern=IDENTIFIER_PATTERN)
    probability_a_better: float = Field(ge=0, le=1)
    mean_difference_in_better_direction: float
    practical_margin: float = Field(ge=0)

    @model_validator(mode="after")
    def distinct_options(self) -> PairwiseDominance:
        if self.option_a == self.option_b:
            raise ValueError("pairwise dominance requires two distinct options")
        return self


class DecisionReversal(StrictModel):
    baseline_option_id: str = Field(pattern=IDENTIFIER_PATTERN)
    competing_option_id: str = Field(pattern=IDENTIFIER_PATTERN)
    reversal_probability: float = Field(ge=0, le=1)
    first_reversal_draw: int | None = Field(default=None, ge=0)
    condition: str = Field(min_length=1)

    @model_validator(mode="after")
    def distinct_options(self) -> DecisionReversal:
        if self.baseline_option_id == self.competing_option_id:
            raise ValueError("decision reversal requires a distinct competitor")
        return self


class UncertaintyRun(StrictModel):
    schema_version: str = "1.0.0"
    run_id: str = Field(pattern=IDENTIFIER_PATTERN)
    created_at: datetime
    status: UncertaintyStatus
    method: UncertaintyMethod
    evidence_type: EvidenceType
    config: UncertaintyConfig
    option_summaries: list[OptionUncertaintySummary]
    pairwise_dominance: list[PairwiseDominance]
    baseline_option_id: str | None = None
    selected_option_id: str | None = None
    reversals: list[DecisionReversal]
    diagnostics: list[str] = Field(min_length=1)
    limitations: list[str] = Field(min_length=1)
    failure_reason: str | None = None

    @field_validator("created_at")
    @classmethod
    def aware(cls, value: datetime) -> datetime:
        return ensure_aware(value, "uncertainty run created_at")

    @field_validator("evidence_type")
    @classmethod
    def estimated_or_simulated(cls, value: EvidenceType) -> EvidenceType:
        if value not in {EvidenceType.ESTIMATED, EvidenceType.SIMULATED}:
            raise ValueError("uncertainty output must be estimated or simulated")
        return value

    @model_validator(mode="after")
    def run_integrity(self) -> UncertaintyRun:
        ids = [item.option_id for item in self.option_summaries]
        if len(ids) != len(set(ids)):
            raise ValueError("uncertainty option ids must be unique")
        known = set(ids)
        if self.baseline_option_id is not None and self.baseline_option_id not in known:
            raise ValueError("uncertainty baseline option must exist")
        if self.selected_option_id is not None and self.selected_option_id not in known:
            raise ValueError("uncertainty selected option must exist")
        if self.status is UncertaintyStatus.INSUFFICIENT_EVIDENCE:
            if (
                self.baseline_option_id is not None
                or self.selected_option_id is not None
                or self.option_summaries
                or self.pairwise_dominance
                or self.reversals
            ):
                raise ValueError(
                    "insufficient uncertainty runs cannot emit option-comparison results"
                )
            if not self.failure_reason:
                raise ValueError("insufficient uncertainty runs require a failure reason")
        else:
            if (
                self.method is not UncertaintyMethod.PAIRED_DRAWS
                or self.baseline_option_id is None
                or self.selected_option_id is None
                or len(self.option_summaries) < 2
            ):
                raise ValueError(
                    "completed uncertainty runs require paired summaries, baseline, and selection"
                )
            if len({item.draws for item in self.option_summaries}) != 1:
                raise ValueError("completed uncertainty summaries require aligned draw counts")
            if abs(sum(item.probability_best for item in self.option_summaries) - 1) > 1e-9:
                raise ValueError("probability-best shares must sum to one")
            pairs = [frozenset((item.option_a, item.option_b)) for item in self.pairwise_dominance]
            expected_pairs = {
                frozenset((left, right))
                for index, left in enumerate(ids)
                for right in ids[index + 1 :]
            }
            if (
                any(
                    item.option_a not in known or item.option_b not in known
                    for item in self.pairwise_dominance
                )
                or len(pairs) != len(set(pairs))
                or set(pairs) != expected_pairs
            ):
                raise ValueError("pairwise dominance must exactly cover unique option pairs")
            competitors = [item.competing_option_id for item in self.reversals]
            if (
                any(
                    item.baseline_option_id != self.baseline_option_id
                    or item.competing_option_id not in known
                    for item in self.reversals
                )
                or len(competitors) != len(set(competitors))
                or set(competitors) != known - {self.baseline_option_id}
            ):
                raise ValueError("decision reversals must cover every non-baseline option once")
            expected_selection = sorted(
                self.option_summaries,
                key=lambda item: (
                    -item.probability_best,
                    item.expected_regret,
                    item.option_id,
                ),
            )[0]
            if self.selected_option_id != expected_selection.option_id:
                raise ValueError(
                    "uncertainty selection must follow the declared deterministic rule"
                )
            regret_pass = (
                self.config.maximum_expected_regret is None
                or expected_selection.expected_regret <= self.config.maximum_expected_regret
            )
            robust = (
                expected_selection.probability_best >= self.config.robust_probability_threshold
                and regret_pass
            )
            if (self.status is UncertaintyStatus.ROBUST_WINNER) != robust:
                raise ValueError("uncertainty status must match robustness thresholds")
            if self.failure_reason is not None:
                raise ValueError("completed uncertainty runs cannot have a failure reason")
        return self

    def content_hash(self) -> str:
        return sha256_bytes(canonical_json(self))


def _quantile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    if not ordered:
        raise AnalysisError("uncertainty quantiles require values")
    position = (len(ordered) - 1) * probability
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] + fraction * (ordered[upper] - ordered[lower])


def _better(left: float, right: float, sense: ObjectiveSense, margin: float = 0) -> bool:
    if sense is ObjectiveSense.MAXIMIZE:
        return left > right + margin
    return left < right - margin


def analyze_option_uncertainty(
    *,
    run_id: str,
    options: list[OptionDraws],
    config: UncertaintyConfig,
    baseline_option_id: str | None = None,
    created_at: datetime | None = None,
) -> UncertaintyRun:
    """Compare option draw streams, expected regret, dominance, and reversal risk."""

    timestamp = created_at or datetime.now(UTC)
    limitations = [
        "The analysis conditions on supplied draw streams and does not validate their structural "
        "model.",
        "Probability of being best is not probability of real-world policy success.",
        "Expected regret uses the declared objective scale and is not automatically monetized.",
    ]
    if len(options) < 2:
        reason = "At least two option draw streams are required for uncertainty comparison."
        return UncertaintyRun(
            run_id=run_id,
            created_at=timestamp,
            status=UncertaintyStatus.INSUFFICIENT_EVIDENCE,
            method=UncertaintyMethod.PAIRED_DRAWS,
            evidence_type=EvidenceType.ESTIMATED,
            config=config,
            option_summaries=[],
            pairwise_dominance=[],
            reversals=[],
            diagnostics=[reason],
            limitations=limitations,
            failure_reason=reason,
        )
    ids = [item.option_id for item in options]
    if len(ids) != len(set(ids)):
        raise AnalysisError("uncertainty option ids must be unique")
    lengths = {len(item.values) for item in options}
    if config.require_paired_draws and len(lengths) != 1:
        reason = "Paired uncertainty analysis requires aligned draw counts for every option."
        return UncertaintyRun(
            run_id=run_id,
            created_at=timestamp,
            status=UncertaintyStatus.INSUFFICIENT_EVIDENCE,
            method=UncertaintyMethod.PAIRED_DRAWS,
            evidence_type=EvidenceType.ESTIMATED,
            config=config,
            option_summaries=[],
            pairwise_dominance=[],
            reversals=[],
            diagnostics=[reason],
            limitations=limitations,
            failure_reason=reason,
        )
    if len(lengths) != 1:
        reason = (
            "Independent unequal-length summaries cannot estimate joint best-option probabilities."
        )
        return UncertaintyRun(
            run_id=run_id,
            created_at=timestamp,
            status=UncertaintyStatus.INSUFFICIENT_EVIDENCE,
            method=UncertaintyMethod.INDEPENDENT_SUMMARIES,
            evidence_type=EvidenceType.ESTIMATED,
            config=config,
            option_summaries=[],
            pairwise_dominance=[],
            reversals=[],
            diagnostics=[reason],
            limitations=limitations,
            failure_reason=reason,
        )
    count = lengths.pop()
    option_by_id = {item.option_id: item for item in options}
    best_by_draw: list[float] = []
    probability_best_shares = {item.option_id: 0.0 for item in options}
    for index in range(count):
        best = (
            max(item.values[index] for item in options)
            if config.sense is ObjectiveSense.MAXIMIZE
            else min(item.values[index] for item in options)
        )
        tied = [item.option_id for item in options if item.values[index] == best]
        share = 1 / len(tied)
        for identifier in tied:
            probability_best_shares[identifier] += share
        best_by_draw.append(best)
    summaries = []
    alpha = 1 - config.confidence_level
    for item in options:
        mean = fmean(item.values)
        standard_deviation = sqrt(
            sum((value - mean) ** 2 for value in item.values) / (len(item.values) - 1)
        )
        regrets = [
            best - value if config.sense is ObjectiveSense.MAXIMIZE else value - best
            for best, value in zip(best_by_draw, item.values, strict=True)
        ]
        dominated = [
            any(
                _better(
                    other.values[index],
                    item.values[index],
                    config.sense,
                    config.practical_equivalence_margin,
                )
                for other in options
                if other.option_id != item.option_id
            )
            for index in range(count)
        ]
        summaries.append(
            OptionUncertaintySummary(
                option_id=item.option_id,
                draws=len(item.values),
                mean=mean,
                standard_deviation=standard_deviation,
                lower=_quantile(item.values, alpha / 2),
                upper=_quantile(item.values, 1 - alpha / 2),
                probability_best=probability_best_shares[item.option_id] / count,
                expected_regret=fmean(regrets),
                maximum_regret=max(regrets),
                dominated_probability=sum(dominated) / count,
            )
        )
    pairwise = []
    for left_index, left in enumerate(options):
        for right in options[left_index + 1 :]:
            better_count = sum(
                _better(a, b, config.sense, config.practical_equivalence_margin)
                for a, b in zip(left.values, right.values, strict=True)
            )
            differences = [
                a - b if config.sense is ObjectiveSense.MAXIMIZE else b - a
                for a, b in zip(left.values, right.values, strict=True)
            ]
            pairwise.append(
                PairwiseDominance(
                    option_a=left.option_id,
                    option_b=right.option_id,
                    probability_a_better=better_count / count,
                    mean_difference_in_better_direction=fmean(differences),
                    practical_margin=config.practical_equivalence_margin,
                )
            )
    baseline = (
        baseline_option_id
        or sorted(
            summaries,
            key=lambda item: (
                -item.mean if config.sense is ObjectiveSense.MAXIMIZE else item.mean,
                item.option_id,
            ),
        )[0].option_id
    )
    if baseline not in option_by_id:
        raise AnalysisError("uncertainty baseline option does not exist")
    baseline_values = option_by_id[baseline].values
    reversals = []
    for item in options:
        if item.option_id == baseline:
            continue
        indexes = [
            index
            for index, (competitor, incumbent) in enumerate(
                zip(item.values, baseline_values, strict=True)
            )
            if _better(
                competitor,
                incumbent,
                config.sense,
                config.practical_equivalence_margin,
            )
        ]
        reversals.append(
            DecisionReversal(
                baseline_option_id=baseline,
                competing_option_id=item.option_id,
                reversal_probability=len(indexes) / count,
                first_reversal_draw=indexes[0] if indexes else None,
                condition=(
                    f"Competitor exceeds the baseline by more than "
                    f"{config.practical_equivalence_margin} objective units."
                ),
            )
        )
    selected = sorted(
        summaries,
        key=lambda item: (-item.probability_best, item.expected_regret, item.option_id),
    )[0]
    regret_pass = (
        config.maximum_expected_regret is None
        or selected.expected_regret <= config.maximum_expected_regret
    )
    robust = selected.probability_best >= config.robust_probability_threshold and regret_pass
    evidence_type = (
        EvidenceType.SIMULATED
        if any(item.evidence_type is EvidenceType.SIMULATED for item in options)
        else EvidenceType.ESTIMATED
    )
    return UncertaintyRun(
        run_id=run_id,
        created_at=timestamp,
        status=(UncertaintyStatus.ROBUST_WINNER if robust else UncertaintyStatus.REVERSAL_RISK),
        method=UncertaintyMethod.PAIRED_DRAWS,
        evidence_type=evidence_type,
        config=config,
        option_summaries=summaries,
        pairwise_dominance=pairwise,
        baseline_option_id=baseline,
        selected_option_id=selected.option_id,
        reversals=reversals,
        diagnostics=[
            f"Compared {len(options)} options over {count} aligned draws.",
            f"Selected {selected.option_id} by probability-best, expected-regret, and stable ID.",
            f"Robust-winner threshold={config.robust_probability_threshold}; observed "
            f"probability-best={selected.probability_best}.",
        ],
        limitations=[
            *limitations,
            "Probability-best shares are split equally across exact ties; final selection ties "
            "use stable option identifiers.",
            "A robust winner remains conditional on scenario, model, source, and distribution "
            "choices.",
        ],
    )


__all__ = [
    "DecisionReversal",
    "ObjectiveSense",
    "OptionDraws",
    "OptionUncertaintySummary",
    "PairwiseDominance",
    "UncertaintyConfig",
    "UncertaintyMethod",
    "UncertaintyRun",
    "UncertaintyStatus",
    "analyze_option_uncertainty",
]
