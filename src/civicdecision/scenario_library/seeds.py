"""Typed authoring seeds for the 30-by-8 scenario design matrix."""

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


@dataclass(frozen=True, slots=True)
class DesignSeed:
    """Explicit substantive content for one scenario design."""

    decision_type: DecisionType
    slug: str
    title: str
    question: str
    decision_object: str
    intervention_mechanism: str
    primary_outcome: str
    outcome_sense: Literal["minimize", "maximize"]
    outcome_unit: str
    binding_constraint_kind: DesignConstraintKind
    binding_constraint: str
    gate_type: EvidenceGateType
    evidence_gate: str
    horizon: DecisionHorizon
    spatial_unit: SpatialUnit
    analysis_modes: tuple[AnalysisMode, ...]
    additional_source_roles: tuple[LibrarySourceRole, ...]
    baseline: str
    alternatives: tuple[str, ...]
    prohibited_claim: str
    existing_template_ref: str | None = None


@dataclass(frozen=True, slots=True)
class FamilySeed:
    """Shared domain context plus eight independently authored decisions."""

    family_id: str
    suite: ApplicationSuite
    title: str
    description: str
    affected_system: str
    decision_owner: str
    common_source_roles: tuple[LibrarySourceRole, ...]
    common_assumptions: tuple[str, ...]
    transportability_risks: tuple[str, ...]
    claim_boundary: tuple[str, ...]
    designs: tuple[DesignSeed, ...]


def seed(
    decision_type: DecisionType,
    slug: str,
    title: str,
    question: str,
    decision_object: str,
    mechanism: str,
    outcome: str,
    unit: str,
    constraint_kind: DesignConstraintKind,
    constraint: str,
    gate_type: EvidenceGateType,
    gate: str,
    horizon: DecisionHorizon,
    spatial: SpatialUnit,
    modes: tuple[AnalysisMode, ...],
    roles: tuple[LibrarySourceRole, ...],
    baseline: str,
    alternatives: tuple[str, ...],
    prohibited_claim: str,
    *,
    sense: Literal["minimize", "maximize"] = "minimize",
    existing_template_ref: str | None = None,
) -> DesignSeed:
    """Keep suite definition modules compact without hiding substantive fields."""

    return DesignSeed(
        decision_type=decision_type,
        slug=slug,
        title=title,
        question=question,
        decision_object=decision_object,
        intervention_mechanism=mechanism,
        primary_outcome=outcome,
        outcome_sense=sense,
        outcome_unit=unit,
        binding_constraint_kind=constraint_kind,
        binding_constraint=constraint,
        gate_type=gate_type,
        evidence_gate=gate,
        horizon=horizon,
        spatial_unit=spatial,
        analysis_modes=modes,
        additional_source_roles=roles,
        baseline=baseline,
        alternatives=alternatives,
        prohibited_claim=prohibited_claim,
        existing_template_ref=existing_template_ref,
    )


D = DecisionType
H = DecisionHorizon
C = DesignConstraintKind
G = EvidenceGateType
R = LibrarySourceRole
S = SpatialUnit
M = AnalysisMode


__all__ = ["C", "D", "DesignSeed", "FamilySeed", "G", "H", "M", "R", "S", "seed"]
