"""Structured authoring helpers for domain-specific eight-decision matrices."""

# ruff: noqa: E501 -- policy phrases are preserved as authored catalog content.

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from civicdecision.deep.models import ApplicationSuite
from civicdecision.protocols.scenario import AnalysisMode
from civicdecision.scenario_library.models import (
    DecisionHorizon,
    DecisionType,
    DesignConstraintKind,
    EvidenceGateType,
    LibrarySourceRole,
    SpatialUnit,
)
from civicdecision.scenario_library.seeds import FamilySeed, seed


@dataclass(frozen=True, slots=True)
class DecisionAxis:
    """Domain-authored axis; shared policy logic is supplied by decision type."""

    decision_type: DecisionType
    slug: str
    title: str
    question: str
    decision_object: str
    mechanism: str
    outcome: str
    unit: str
    spatial: SpatialUnit
    roles: tuple[LibrarySourceRole, ...]
    boundary: str
    existing_template_ref: str | None = None
    sense: Literal["minimize", "maximize"] = "minimize"


@dataclass(frozen=True, slots=True)
class TypeSetting:
    constraint_kind: DesignConstraintKind
    constraint_noun: str
    gate_type: EvidenceGateType
    gate_checks: str
    horizon: DecisionHorizon
    modes: tuple[AnalysisMode, ...]
    baseline_action: str
    targeted_action: str
    portfolio_action: str


TYPE_SETTINGS = {
    DecisionType.DIAGNOSE: TypeSetting(
        DesignConstraintKind.TECHNICAL,
        "measurement resolution and classification uncertainty",
        EvidenceGateType.GEOGRAPHIC_ALIGNMENT,
        "coverage, semantics, geography, timestamps, and uncertainty",
        DecisionHorizon.ANNUAL,
        (AnalysisMode.DESCRIPTIVE,),
        "continue current inspection and reporting practice for",
        "verify the highest-consequence signals before acting on",
        "combine targeted inspection, monitoring, and data-quality repair for",
    ),
    DecisionType.FORECAST: TypeSetting(
        DesignConstraintKind.CAPACITY,
        "validated operational capacity and forecast uncertainty",
        EvidenceGateType.CALIBRATION,
        "held-out error, interval coverage, event detection, drift, and baseline comparison",
        DecisionHorizon.WEEKS,
        (AnalysisMode.FORECAST,),
        "continue ordinary capacity planning for",
        "activate a bounded reserve from forecast risk bands for",
        "use rolling forecasts and conservative capacity triggers for",
    ),
    DecisionType.PRIORITIZE: TypeSetting(
        DesignConstraintKind.BUDGET,
        "capital, operating, maintenance, and delivery budgets",
        EvidenceGateType.COST_CAPACITY,
        "cost, benefit, service life, dependencies, deliverability, and maintenance burden",
        DecisionHorizon.MULTI_YEAR,
        (AnalysisMode.DESCRIPTIVE, AnalysisMode.OPTIMIZATION),
        "fund only already-committed work for",
        "rank verified high-consequence candidates for",
        "select a risk-, equity-, and lifecycle-balanced portfolio for",
    ),
    DecisionType.SITE: TypeSetting(
        DesignConstraintKind.REGULATORY,
        "land control, accessibility, permitting, safety, and operating feasibility",
        EvidenceGateType.LEGAL_AUTHORITY,
        "parcel control, legal authority, environmental review, access, capacity, and operator responsibility",
        DecisionHorizon.MULTI_YEAR,
        (AnalysisMode.SIMULATION, AnalysisMode.OPTIMIZATION),
        "retain only existing approved locations for",
        "screen feasible locations against the largest access gaps for",
        "co-optimize distributed and high-capacity locations for",
    ),
    DecisionType.ALLOCATE: TypeSetting(
        DesignConstraintKind.EQUITY,
        "minimum service, eligibility, capacity, and distributional safeguards",
        EvidenceGateType.EQUITY_MEASUREMENT,
        "eligible denominators, group attributes, inventory, minimum-service rules, and allocation records",
        DecisionHorizon.WEEKS,
        (AnalysisMode.SIMULATION, AnalysisMode.OPTIMIZATION),
        "retain the current distribution rule for",
        "protect minimum coverage before needs-based allocation of",
        "adapt allocations using observed demand, uptake, and capacity for",
    ),
    DecisionType.SCHEDULE: TypeSetting(
        DesignConstraintKind.TIME,
        "labor, access, sequencing, notice, and completion windows",
        EvidenceGateType.TEMPORAL_ALIGNMENT,
        "effective dates, time zones, calendars, lead times, completion semantics, and update cadence",
        DecisionHorizon.WEEKS,
        (AnalysisMode.FORECAST, AnalysisMode.OPTIMIZATION),
        "continue the fixed operating calendar for",
        "advance high-risk work within verified feasible windows for",
        "use rolling risk and capacity updates to reschedule",
    ),
    DecisionType.STRESS_TEST: TypeSetting(
        DesignConstraintKind.RISK,
        "minimum continuity and safety thresholds across severe scenarios",
        EvidenceGateType.EXTERNAL_VALIDATION,
        "scenario ranges, dependence, failure rates, recovery, intervention performance, and sensitivity",
        DecisionHorizon.SEASONAL,
        (AnalysisMode.FORECAST, AnalysisMode.SIMULATION, AnalysisMode.OPTIMIZATION),
        "apply current continuity provisions to",
        "add targeted redundancy around the largest failure modes in",
        "select an adaptive robust portfolio across severe scenarios for",
    ),
    DecisionType.EVALUATE: TypeSetting(
        DesignConstraintKind.EQUITY,
        "pre-specified assignment, comparison, outcome, spillover, and subgroup rules",
        EvidenceGateType.IDENTIFICATION,
        "dated assignment, comparison validity, pre-trends, outcome panels, attrition, spillovers, and falsification tests",
        DecisionHorizon.MULTI_YEAR,
        (AnalysisMode.DESCRIPTIVE, AnalysisMode.CAUSAL),
        "retain pre-intervention conditions for",
        "compare eligible treated and credible untreated units for",
        "estimate pre-specified overall and distributional effects of",
    ),
}


def axis(
    decision_type: DecisionType,
    slug: str,
    title: str,
    question: str,
    decision_object: str,
    mechanism: str,
    outcome: str,
    unit: str,
    spatial: SpatialUnit,
    roles: tuple[LibrarySourceRole, ...],
    boundary: str,
    *,
    existing_template_ref: str | None = None,
    sense: Literal["minimize", "maximize"] = "minimize",
) -> DecisionAxis:
    return DecisionAxis(
        decision_type=decision_type,
        slug=slug,
        title=title,
        question=question,
        decision_object=decision_object,
        mechanism=mechanism,
        outcome=outcome,
        unit=unit,
        spatial=spatial,
        roles=roles,
        boundary=boundary,
        existing_template_ref=existing_template_ref,
        sense=sense,
    )


def matrix_family(
    *,
    family_id: str,
    suite: ApplicationSuite,
    title: str,
    description: str,
    affected_system: str,
    decision_owner: str,
    common_source_roles: tuple[LibrarySourceRole, ...],
    common_assumptions: tuple[str, ...],
    transportability_risks: tuple[str, ...],
    claim_boundary: tuple[str, ...],
    axes: tuple[DecisionAxis, ...],
) -> FamilySeed:
    """Expand eight domain-authored axes into complete and explicit decision seeds."""

    designs = []
    for item in axes:
        setting = TYPE_SETTINGS[item.decision_type]
        decision_label = item.decision_type.value.replace("-", " ")
        constraint = (
            f"The {title.lower()} {decision_label} must respect declared {setting.constraint_noun}."
        )
        gate = (
            f"Evidence for {item.decision_object} passes documented checks for "
            f"{setting.gate_checks}."
        )
        alternatives = (
            f"{setting.targeted_action} {item.decision_object}",
            f"{setting.portfolio_action} {item.decision_object}",
            f"pair {item.mechanism} with an explicit stop, review, and escalation rule",
        )
        extra_roles = list(item.roles)
        if item.decision_type is DecisionType.EVALUATE:
            extra_roles.extend(
                [LibrarySourceRole.INTERVENTION_ASSIGNMENT, LibrarySourceRole.OUTCOME_PANEL]
            )
        designs.append(
            seed(
                item.decision_type,
                item.slug,
                item.title,
                item.question,
                item.decision_object,
                item.mechanism,
                item.outcome,
                item.unit,
                setting.constraint_kind,
                constraint,
                setting.gate_type,
                gate,
                setting.horizon,
                item.spatial,
                setting.modes,
                tuple(dict.fromkeys(extra_roles)),
                f"{setting.baseline_action} {item.decision_object}.",
                alternatives,
                item.boundary,
                sense=item.sense,
                existing_template_ref=item.existing_template_ref,
            )
        )
    return FamilySeed(
        family_id=family_id,
        suite=suite,
        title=title,
        description=description,
        affected_system=affected_system,
        decision_owner=decision_owner,
        common_source_roles=common_source_roles,
        common_assumptions=common_assumptions,
        transportability_risks=transportability_risks,
        claim_boundary=claim_boundary,
        designs=tuple(designs),
    )


__all__ = ["DecisionAxis", "axis", "matrix_family"]
