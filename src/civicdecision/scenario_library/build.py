"""Deterministic builder and anti-duplication audit for the scenario library."""

# ruff: noqa: E501, RUF001 -- long policy statements are generated artifact content.

from __future__ import annotations

import csv
import io
import json
import re
import tempfile
from collections import Counter, defaultdict
from collections.abc import Hashable, Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TypeVar

from civicdecision.connectors.base import atomic_write
from civicdecision.deep.models import ApplicationSuite
from civicdecision.deep.templates import DEEP_SCENARIO_TEMPLATES
from civicdecision.errors import IntegrityError
from civicdecision.protocols.base import StrictModel, canonical_json, sha256_bytes, sha256_file
from civicdecision.protocols.evidence import EvidenceType
from civicdecision.protocols.scenario import AnalysisMode
from civicdecision.scenario_library.definitions import FAMILY_SEEDS
from civicdecision.scenario_library.models import (
    CurrentReadiness,
    DecisionHorizon,
    DecisionType,
    DesignConstraintKind,
    EvidenceGateType,
    ImplementationStatus,
    LibrarySourceRole,
    ScenarioDesign,
    ScenarioDesignConstraint,
    ScenarioDesignIndexEntry,
    ScenarioDesignObjective,
    ScenarioEvidenceGate,
    ScenarioFamily,
    ScenarioFamilyIndexEntry,
    ScenarioIndependenceKey,
    ScenarioLibraryArtifactEntry,
    ScenarioLibraryAudit,
    ScenarioLibraryManifest,
    ScenarioLibraryRegistry,
    ScenarioSimilarityPair,
    SpatialUnit,
)
from civicdecision.scenario_library.seeds import DesignSeed, FamilySeed

PUBLISHED_AT = datetime(2026, 8, 13, 0, 0, tzinfo=UTC)
HIGH_SIMILARITY_THRESHOLD = 0.9
EXPECTED_BASE_ARTIFACTS = 280
EXPECTED_TOTAL_FILES = 282

CURRENT_SOURCE_ROLES = frozenset(
    {
        LibrarySourceRole.MUNICIPAL_DEMAND,
        LibrarySourceRole.CLIMATE_HAZARD,
        LibrarySourceRole.GEOGRAPHIC_IDENTITY,
        LibrarySourceRole.DEMOGRAPHIC_CONTEXT,
    }
)

STOPWORDS = frozenset(
    {
        "a",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "for",
        "from",
        "in",
        "into",
        "is",
        "of",
        "on",
        "or",
        "the",
        "to",
        "under",
        "with",
    }
)

TCount = TypeVar("TCount", bound=Hashable)


@dataclass(frozen=True, slots=True)
class ScenarioLibraryBuildResult:
    output_directory: Path
    registry_path: Path
    audit_path: Path
    manifest_path: Path
    checksum_path: Path
    design_paths: tuple[Path, ...]
    family_paths: tuple[Path, ...]
    artifact_paths: tuple[Path, ...]


@dataclass(frozen=True, slots=True)
class LibraryModels:
    designs: tuple[ScenarioDesign, ...]
    families: tuple[ScenarioFamily, ...]
    audit: ScenarioLibraryAudit
    definitions_hash: str
    closest_pairs: tuple[ScenarioSimilarityPair, ...]


def _json_bytes(payload: object) -> bytes:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n"


def _model_bytes(document: StrictModel) -> bytes:
    return _json_bytes(document.model_dump(mode="json", exclude_none=True))


def _write_model(root: Path, relative: str, document: StrictModel) -> Path:
    path = root / relative
    atomic_write(path, _model_bytes(document))
    return path


def _write_bytes(root: Path, relative: str, content: bytes) -> Path:
    path = root / relative
    atomic_write(path, content)
    return path


def _required_evidence(modes: Sequence[AnalysisMode]) -> list[EvidenceType]:
    evidence = {EvidenceType.OBSERVED, EvidenceType.ESTIMATED, EvidenceType.PROPOSED}
    if AnalysisMode.CAUSAL in modes:
        evidence.add(EvidenceType.CAUSAL)
    if AnalysisMode.SIMULATION in modes:
        evidence.add(EvidenceType.SIMULATED)
    if AnalysisMode.OPTIMIZATION in modes:
        evidence.add(EvidenceType.OPTIMIZED)
    return sorted(evidence, key=lambda item: item.value)


def _gate_evidence(gate_type: EvidenceGateType) -> list[EvidenceType]:
    if gate_type is EvidenceGateType.IDENTIFICATION:
        return [EvidenceType.CAUSAL, EvidenceType.OBSERVED]
    if gate_type in {EvidenceGateType.CALIBRATION, EvidenceGateType.EXTERNAL_VALIDATION}:
        return [EvidenceType.ESTIMATED, EvidenceType.OBSERVED]
    return [EvidenceType.OBSERVED, EvidenceType.PROPOSED]


def _readiness(
    source_roles: Sequence[LibrarySourceRole],
    modes: Sequence[AnalysisMode],
    existing_template_ref: str | None,
) -> tuple[ImplementationStatus, CurrentReadiness]:
    if existing_template_ref is not None:
        return ImplementationStatus.REFERENCE_IMPLEMENTED, CurrentReadiness.REFERENCE_IMPLEMENTED
    source_gap = bool(set(source_roles) - CURRENT_SOURCE_ROLES)
    method_gap = AnalysisMode.CAUSAL in modes
    if source_gap and method_gap:
        readiness = CurrentReadiness.BLOCKED_MULTI
    elif source_gap:
        readiness = CurrentReadiness.BLOCKED_SOURCE
    elif method_gap:
        readiness = CurrentReadiness.BLOCKED_METHOD
    else:
        readiness = CurrentReadiness.UNCOMPILED_CURRENT_INPUTS
    return ImplementationStatus.DESIGN_ONLY, readiness


def _design_from_seed(
    family: FamilySeed,
    design_seed: DesignSeed,
    order: int,
) -> ScenarioDesign:
    source_roles = sorted(
        set(family.common_source_roles) | set(design_seed.additional_source_roles),
        key=lambda item: item.value,
    )
    evidence = _required_evidence(design_seed.analysis_modes)
    implementation, readiness = _readiness(
        source_roles,
        design_seed.analysis_modes,
        design_seed.existing_template_ref,
    )
    template_by_id = {item.template_id: item for item in DEEP_SCENARIO_TEMPLATES}
    reference_note = None
    if design_seed.existing_template_ref is not None:
        template = template_by_id[design_seed.existing_template_ref]
        reference_note = (
            f"Tier-D template {template.template_id} ({template.title}) supplies a bounded "
            "reference workflow for this design axis. The mapping does not establish complete "
            "city-specific inputs, external validity, deployment, adoption, or impact."
        )
    independence = ScenarioIndependenceKey(
        decision_object=design_seed.decision_object,
        intervention_mechanism=design_seed.intervention_mechanism,
        primary_outcome=design_seed.primary_outcome,
        binding_constraint=design_seed.binding_constraint,
        evidence_gate=design_seed.evidence_gate,
        horizon=design_seed.horizon,
        spatial_unit=design_seed.spatial_unit,
    )
    identifier = f"scenario.{family.family_id}.{design_seed.slug}.v1"
    role_anchor = source_roles[:1]
    objectives = [
        ScenarioDesignObjective(
            objective_id=f"{identifier}.objective.primary",
            metric=design_seed.primary_outcome,
            sense=design_seed.outcome_sense,
            unit=design_seed.outcome_unit,
            evidence_type=EvidenceType.ESTIMATED,
            primary=True,
        ),
        ScenarioDesignObjective(
            objective_id=f"{identifier}.objective.equity",
            metric=f"distributional gap in {design_seed.primary_outcome}",
            sense="minimize",
            unit=design_seed.outcome_unit,
            evidence_type=EvidenceType.ESTIMATED,
        ),
        ScenarioDesignObjective(
            objective_id=f"{identifier}.objective.traceability",
            metric="decision claims with complete evidence lineage",
            sense="maximize",
            unit="percent",
            evidence_type=EvidenceType.OBSERVED,
        ),
    ]
    constraints = [
        ScenarioDesignConstraint(
            constraint_id=f"{identifier}.constraint.binding",
            kind=design_seed.binding_constraint_kind,
            description=design_seed.binding_constraint,
            hard=True,
            binding=True,
            required_source_roles=source_roles,
        ),
        ScenarioDesignConstraint(
            constraint_id=f"{identifier}.constraint.evidence-scope",
            kind=DesignConstraintKind.TECHNICAL,
            description=(
                "Every released metric must retain evidence type, source lineage, geography, time, "
                "assumptions, and uncertainty."
            ),
            hard=True,
            required_source_roles=role_anchor,
        ),
        ScenarioDesignConstraint(
            constraint_id=f"{identifier}.constraint.decision-authority",
            kind=DesignConstraintKind.REGULATORY,
            description=(
                "No analytical output may bypass lawful authority, accountable human review, or an "
                "applicable appeal process."
            ),
            hard=True,
            required_source_roles=role_anchor,
        ),
    ]
    release_gate = ScenarioEvidenceGate(
        gate_id=f"{identifier}.gate.release",
        gate_type=design_seed.gate_type,
        pass_condition=design_seed.evidence_gate,
        failure_release=(
            "Release an explicit insufficient-evidence record naming missing sources, failed "
            "diagnostics, prohibited claims, and the next validation action."
        ),
        required_source_roles=source_roles,
        required_evidence_types=_gate_evidence(design_seed.gate_type),
    )
    prohibited = [
        design_seed.prohibited_claim,
        "Do not describe a design-only record as a city execution, deployment, adopted policy, or impact result.",
        "Do not relabel proposed, estimated, simulated, optimized, or causal evidence as observed evidence.",
        "Do not infer individual behavior, protected status, harm, or entitlement from aggregate records.",
    ]
    limitations = [
        "This library record has no city binding and therefore reports no local input, output, or recommendation.",
        "Readiness describes explicit source and method gates; it does not certify implementation feasibility.",
        "External domain, legal, community, security, and operational review remains outside this design artifact.",
    ]
    return ScenarioDesign(
        design_order=order,
        design_id=identifier,
        family_id=family.family_id,
        suite=family.suite,
        family_title=family.title,
        title=design_seed.title,
        decision_question=design_seed.question,
        decision_type=design_seed.decision_type,
        decision_owner=family.decision_owner,
        affected_system=family.affected_system,
        horizon=design_seed.horizon,
        decision_cadence=(
            "event-triggered and reviewed at the stated decision horizon"
            if design_seed.horizon in {DecisionHorizon.REAL_TIME, DecisionHorizon.DAYS}
            else "recompiled at each planning cycle and after material evidence change"
        ),
        spatial_unit=design_seed.spatial_unit,
        baseline=design_seed.baseline,
        alternatives=list(design_seed.alternatives),
        objectives=objectives,
        constraints=constraints,
        analysis_modes=list(design_seed.analysis_modes),
        evidence_requirements=evidence,
        required_source_roles=source_roles,
        release_gate=release_gate,
        independence_key=independence,
        design_signature=independence.signature(),
        implementation_status=implementation,
        current_readiness=readiness,
        existing_template_ref=design_seed.existing_template_ref,
        reference_implementation_note=reference_note,
        intended_claim=(
            f"A versioned {design_seed.decision_type.value} design for comparing declared "
            f"alternatives affecting {design_seed.decision_object}, conditional on its evidence gate."
        ),
        prohibited_claims=prohibited,
        assumptions=[
            *family.common_assumptions,
            "All alternatives, capacities, costs, effects, thresholds, and failure scenarios are proposed until bound to evidence.",
        ],
        limitations=limitations,
        transportability_risks=list(family.transportability_risks),
        tags=sorted(
            {
                "scenario-library",
                family.suite.value,
                family.family_id,
                design_seed.decision_type.value,
                implementation.value,
            }
        ),
    )


def _tokenize(design: ScenarioDesign) -> set[str]:
    content = " ".join(
        [
            design.title,
            design.decision_question,
            design.independence_key.decision_object,
            design.independence_key.intervention_mechanism,
            design.independence_key.primary_outcome,
            design.independence_key.binding_constraint,
            design.independence_key.evidence_gate,
            design.horizon.value,
            design.spatial_unit.value,
        ]
    ).lower()
    return {
        token
        for token in re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)*", content)
        if len(token) > 1 and token not in STOPWORDS
    }


def _group_duplicates(values: Iterable[tuple[str, str]]) -> list[list[str]]:
    groups: defaultdict[str, list[str]] = defaultdict(list)
    for identifier, value in values:
        normalized = " ".join(value.lower().split())
        groups[normalized].append(identifier)
    return sorted(sorted(group) for group in groups.values() if len(group) > 1)


def _similarities(
    designs: Sequence[ScenarioDesign],
) -> tuple[list[ScenarioSimilarityPair], list[ScenarioSimilarityPair], float]:
    token_sets = {design.design_id: _tokenize(design) for design in designs}
    all_pairs: list[ScenarioSimilarityPair] = []
    for left_index, left in enumerate(designs):
        left_tokens = token_sets[left.design_id]
        for right in designs[left_index + 1 :]:
            right_tokens = token_sets[right.design_id]
            union = left_tokens | right_tokens
            shared = left_tokens & right_tokens
            similarity = len(shared) / len(union) if union else 0.0
            all_pairs.append(
                ScenarioSimilarityPair(
                    design_a=left.design_id,
                    design_b=right.design_id,
                    similarity=round(similarity, 6),
                    shared_terms=sorted(shared),
                )
            )
    ranked = sorted(
        all_pairs,
        key=lambda item: (-item.similarity, item.design_a, item.design_b),
    )
    high = [item for item in ranked if item.similarity >= HIGH_SIMILARITY_THRESHOLD]
    maximum = ranked[0].similarity if ranked else 0.0
    return high, ranked[:20], maximum


def _counter(values: Iterable[TCount], members: Iterable[TCount]) -> dict[TCount, int]:
    counts = Counter(values)
    return {member: counts[member] for member in members}


def build_library_models() -> LibraryModels:
    """Validate the authored matrix and build 240 strict design contracts."""

    designs: list[ScenarioDesign] = []
    families: list[ScenarioFamily] = []
    order = 1
    for family_order, family_seed in enumerate(FAMILY_SEEDS, start=1):
        family_designs = []
        for design_seed in family_seed.designs:
            design = _design_from_seed(family_seed, design_seed, order)
            designs.append(design)
            family_designs.append(design)
            order += 1
        families.append(
            ScenarioFamily(
                family_order=family_order,
                family_id=family_seed.family_id,
                suite=family_seed.suite,
                title=family_seed.title,
                description=family_seed.description,
                affected_system=family_seed.affected_system,
                decision_owner=family_seed.decision_owner,
                design_refs=[item.design_id for item in family_designs],
                decision_types=[item.decision_type for item in family_designs],
                design_signatures=[item.design_signature for item in family_designs],
                common_source_roles=sorted(
                    family_seed.common_source_roles,
                    key=lambda item: item.value,
                ),
                claim_boundary=list(family_seed.claim_boundary),
            )
        )

    authored_refs = {
        item.existing_template_ref for item in designs if item.existing_template_ref is not None
    }
    implemented_refs = {item.template_id for item in DEEP_SCENARIO_TEMPLATES}
    if authored_refs != implemented_refs:
        raise IntegrityError(
            "scenario library reference mappings must match the 12 Tier-D templates exactly: "
            f"missing={sorted(implemented_refs - authored_refs)}, "
            f"unexpected={sorted(authored_refs - implemented_refs)}"
        )

    signature_groups: defaultdict[str, list[str]] = defaultdict(list)
    for design in designs:
        signature_groups[design.design_signature].append(design.design_id)
    collisions = sorted(sorted(group) for group in signature_groups.values() if len(group) > 1)
    duplicate_titles = _group_duplicates((item.design_id, item.title) for item in designs)
    duplicate_questions = _group_duplicates(
        (item.design_id, item.decision_question) for item in designs
    )
    high_pairs, closest_pairs, maximum_similarity = _similarities(designs)
    completeness = {
        "alternatives": sum(len(item.alternatives) >= 3 for item in designs),
        "assumption_registers": sum(len(item.assumptions) >= 3 for item in designs),
        "claim_boundaries": sum(len(item.prohibited_claims) >= 4 for item in designs),
        "decision_questions": sum(bool(item.decision_question) for item in designs),
        "evidence_gates": sum(bool(item.release_gate.pass_condition) for item in designs),
        "hard_constraints": sum(any(c.hard for c in item.constraints) for item in designs),
        "limitations": sum(len(item.limitations) >= 3 for item in designs),
        "negative_release_rules": sum(bool(item.release_gate.failure_release) for item in designs),
        "source_requirements": sum(bool(item.required_source_roles) for item in designs),
        "transportability_risks": sum(len(item.transportability_risks) >= 2 for item in designs),
    }
    audit_passed = not (
        collisions or duplicate_titles or duplicate_questions or high_pairs
    ) and all(value == 240 for value in completeness.values())
    audit = ScenarioLibraryAudit(
        audit_passed=audit_passed,
        exact_signature_collisions=collisions,
        duplicate_titles=duplicate_titles,
        duplicate_questions=duplicate_questions,
        high_similarity_threshold=HIGH_SIMILARITY_THRESHOLD,
        maximum_pairwise_similarity=maximum_similarity,
        high_similarity_pairs=high_pairs,
        suite_counts=_counter((item.suite for item in designs), ApplicationSuite),
        family_counts=_counter((item.suite for item in families), ApplicationSuite),
        decision_type_counts=_counter((item.decision_type for item in designs), DecisionType),
        horizon_counts=_counter((item.horizon for item in designs), DecisionHorizon),
        spatial_unit_counts=_counter((item.spatial_unit for item in designs), SpatialUnit),
        analysis_mode_counts=_counter(
            (mode for item in designs for mode in item.analysis_modes), AnalysisMode
        ),
        evidence_type_counts=_counter(
            (kind for item in designs for kind in item.evidence_requirements), EvidenceType
        ),
        source_role_counts=_counter(
            (role for item in designs for role in item.required_source_roles),
            LibrarySourceRole,
        ),
        gate_type_counts=_counter(
            (item.release_gate.gate_type for item in designs), EvidenceGateType
        ),
        constraint_kind_counts=_counter(
            (constraint.kind for item in designs for constraint in item.constraints),
            DesignConstraintKind,
        ),
        implementation_status_counts=_counter(
            (item.implementation_status for item in designs), ImplementationStatus
        ),
        current_readiness_counts=_counter(
            (item.current_readiness for item in designs), CurrentReadiness
        ),
        existing_template_refs=len(authored_refs),
        completeness_checks=completeness,
        invariants=[
            "Thirty domain families each contain exactly one design for every decision type.",
            "All 240 substantive independence signatures are unique.",
            "Titles and decision questions are exact-normalized unique.",
            "No pair reaches the fixed high-similarity threshold.",
            "Every design declares alternatives, objectives, and a single binding hard constraint.",
            "Every design declares source roles, evidence types, and a negative release gate.",
            "Every design preserves assumptions, limitations, prohibited claims, and transfer risks.",
            "Exactly twelve existing Tier-D templates map one-to-one to reference implementations.",
            "The other 228 records remain design-only and report source or method readiness gaps.",
            "No design counts a city binding, execution, deployment, adoption, impact, or new method.",
        ],
        limitations=[
            "Token Jaccard is a transparent duplication diagnostic, not proof of conceptual novelty.",
            "Domain experts and affected communities have not externally reviewed all 240 designs.",
            "Readiness is computed against the current repository source roles, not every possible city source.",
            "Design breadth does not substitute for future city-specific validation and implementation evidence.",
        ],
    )
    if not audit.audit_passed:
        raise IntegrityError("scenario library anti-duplication or completeness audit failed")
    definitions_hash = sha256_bytes(
        canonical_json(
            {
                "published_at": PUBLISHED_AT.isoformat(),
                "families": [asdict(item) for item in FAMILY_SEEDS],
            }
        )
    )
    return LibraryModels(
        designs=tuple(designs),
        families=tuple(families),
        audit=audit,
        definitions_hash=definitions_hash,
        closest_pairs=tuple(closest_pairs),
    )


def _coverage_csv(designs: Sequence[ScenarioDesign]) -> bytes:
    buffer = io.StringIO(newline="")
    fieldnames = [
        "design_order",
        "design_id",
        "suite",
        "family_id",
        "decision_type",
        "title",
        "decision_object",
        "intervention_mechanism",
        "primary_outcome",
        "horizon",
        "spatial_unit",
        "binding_constraint_kind",
        "evidence_gate_type",
        "analysis_modes",
        "required_source_roles",
        "implementation_status",
        "current_readiness",
        "existing_template_ref",
        "city_bindings",
        "method_claimed",
        "design_signature",
        "content_hash",
    ]
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    for design in designs:
        binding = next(item for item in design.constraints if item.binding)
        writer.writerow(
            {
                "design_order": design.design_order,
                "design_id": design.design_id,
                "suite": design.suite.value,
                "family_id": design.family_id,
                "decision_type": design.decision_type.value,
                "title": design.title,
                "decision_object": design.independence_key.decision_object,
                "intervention_mechanism": design.independence_key.intervention_mechanism,
                "primary_outcome": design.independence_key.primary_outcome,
                "horizon": design.horizon.value,
                "spatial_unit": design.spatial_unit.value,
                "binding_constraint_kind": binding.kind.value,
                "evidence_gate_type": design.release_gate.gate_type.value,
                "analysis_modes": "|".join(mode.value for mode in design.analysis_modes),
                "required_source_roles": "|".join(
                    role.value for role in design.required_source_roles
                ),
                "implementation_status": design.implementation_status.value,
                "current_readiness": design.current_readiness.value,
                "existing_template_ref": design.existing_template_ref or "",
                "city_bindings": len(design.city_bindings),
                "method_claimed": str(design.method_claimed).lower(),
                "design_signature": design.design_signature,
                "content_hash": design.content_hash(),
            }
        )
    return buffer.getvalue().encode("utf-8")


def _count_table(counts: Mapping[TCount, int]) -> str:
    rows = ["| Value | Count |", "|---|---:|"]
    rows.extend(f"| `{getattr(key, 'value', key)}` | {value} |" for key, value in counts.items())
    return "\n".join(rows)


def _summary_markdown(
    models: LibraryModels,
    registry: ScenarioLibraryRegistry,
) -> bytes:
    family_rows = [
        "| # | Suite | Family | Designs | Reference implementations |",
        "|---:|---|---|---:|---:|",
    ]
    for family in models.families:
        family_designs = [item for item in models.designs if item.family_id == family.family_id]
        implemented = sum(
            item.implementation_status is ImplementationStatus.REFERENCE_IMPLEMENTED
            for item in family_designs
        )
        family_rows.append(
            f"| {family.family_order} | `{family.suite.value}` | "
            f"`{family.family_id}` — {family.title} | 8 | {implemented} |"
        )
    text = f"""# CivicDecision 240-scenario design library

## Scope

This catalog contains **240 policy decision designs** organized as **30 domain families × 8
decision types**. It intentionally reports **0 city bindings**, **0 new methods**, and **0 claims
of deployment or impact**. Exactly **12 designs** point one-to-one to existing Tier-D reference
templates; the remaining **228 are design-only**.

The eight decision types are diagnose, forecast, prioritize, site, allocate, schedule,
stress-test, and evaluate. Repeating this decision grammar across domains is an explicit coverage
matrix; substantive independence is tested from decision object, intervention mechanism, primary
outcome, binding constraint, evidence gate, horizon, and spatial unit—not from title or city name.

## Verified inventory

- Designs: {registry.design_count}
- Families: {registry.family_count}
- Suites: {len(registry.suite_counts)}
- Reference-implemented designs: {registry.implementation_status_counts[ImplementationStatus.REFERENCE_IMPLEMENTED]}
- Design-only records: {registry.implementation_status_counts[ImplementationStatus.DESIGN_ONLY]}
- City-bound executions counted: {registry.city_bound_execution_count}
- Methods claimed: {registry.method_count_claimed}
- Exact signature collisions: {len(models.audit.exact_signature_collisions)}
- Duplicate titles: {len(models.audit.duplicate_titles)}
- Duplicate questions: {len(models.audit.duplicate_questions)}
- Similarity threshold: {models.audit.high_similarity_threshold:.2f}
- Maximum observed pairwise token Jaccard: {models.audit.maximum_pairwise_similarity:.6f}
- High-similarity pairs at or above threshold: {len(models.audit.high_similarity_pairs)}

## Designs by suite

{_count_table(registry.suite_counts)}

## Designs by decision type

{_count_table(registry.decision_type_counts)}

## Current readiness

{_count_table(registry.current_readiness_counts)}

## Family inventory

{chr(10).join(family_rows)}

## Evidence and release contract

Every design includes a baseline; at least three alternatives; three objectives; one binding hard
constraint plus evidence-scope and accountable-authority constraints; analysis modes; typed evidence
requirements; source roles; an evidence gate; an explicit insufficient-evidence release; assumptions;
limitations; prohibited claims; and transportability risks. A design cannot silently become an
execution: `city_bindings` is schema-constrained to an empty list and `method_claimed` is schema-
constrained to false.

## How to use the library

1. Select a family and decision type from `coverage.csv` or `registry.json`.
2. Bind a city only in a separate execution artifact; never edit the design's claim boundary.
3. Resolve all required source roles and pass the declared evidence gate.
4. Compile observed, estimated, causal, simulated, optimized, and proposed evidence without relabeling.
5. If a gate fails, publish the required insufficient-evidence record instead of a recommendation.
6. Treat external domain, legal, security, community, and operational review as additional gates.

## Claim boundary

- Breadth is a design asset, not evidence that 240 city projects were delivered.
- A reference implementation may be a negative release; it is not automatically a positive result.
- Internal reproducibility is not external validation, municipal adoption, or real-user impact.
- Counts, hashes, mappings, and audit results are reproducible from committed source definitions.
"""
    return text.encode("utf-8")


def _anti_duplication_markdown(models: LibraryModels) -> bytes:
    pair_rows = [
        "| Rank | Design A | Design B | Jaccard | Shared terms |",
        "|---:|---|---|---:|---|",
    ]
    for rank, pair in enumerate(models.closest_pairs, start=1):
        shared = ", ".join(pair.shared_terms[:12])
        pair_rows.append(
            f"| {rank} | `{pair.design_a}` | `{pair.design_b}` | {pair.similarity:.6f} | {shared} |"
        )
    text = f"""# Scenario-library anti-duplication audit

## Result

**PASS.** The audit covers all **28,680 unordered pairs** among 240 designs.

- Exact substantive-signature collisions: {len(models.audit.exact_signature_collisions)}
- Exact normalized-title duplicates: {len(models.audit.duplicate_titles)}
- Exact normalized-question duplicates: {len(models.audit.duplicate_questions)}
- Fixed high-similarity threshold: {models.audit.high_similarity_threshold:.2f}
- Maximum pairwise token Jaccard: {models.audit.maximum_pairwise_similarity:.6f}
- Pairs at or above the threshold: {len(models.audit.high_similarity_pairs)}

## What constitutes substantive identity

Each design hashes a seven-field independence key: decision object, intervention mechanism, primary
outcome, binding constraint, evidence gate, decision horizon, and spatial unit. Design identifier,
title, family label, suite label, and city name are excluded. A renamed or city-copied record with the
same substantive axes therefore collides.

## Similarity method

The transparent secondary diagnostic tokenizes title, question, and all seven substantive axes;
lowercases terms; removes a fixed small stopword list; and computes set Jaccard similarity. The
threshold is fixed in source at {HIGH_SIMILARITY_THRESHOLD:.2f}. This lexical test is intentionally
supplementary: it can identify suspicious copies but cannot prove conceptual novelty.

## Twenty closest pairs below the failure threshold

{chr(10).join(pair_rows)}

## Completeness checks

{_count_table(models.audit.completeness_checks)}

## Remaining review boundary

Passing this audit establishes deterministic structural uniqueness and absence of near-verbatim
design copies under the declared test. It does not establish novelty in the academic-method sense,
external domain correctness, public acceptance, legal authority, feasibility, deployment, or impact.
"""
    return text.encode("utf-8")


def _schema_documents() -> dict[str, dict[str, object]]:
    models: tuple[type[StrictModel], ...] = (
        ScenarioDesign,
        ScenarioFamily,
        ScenarioLibraryRegistry,
        ScenarioLibraryAudit,
        ScenarioLibraryManifest,
    )
    return {
        "schemas/"
        + re.sub(r"(?<!^)(?=[A-Z])", "-", model.__name__).lower()
        + ".schema.json": model.model_json_schema(mode="validation")
        for model in models
    }


def _media_type(relative: str) -> str:
    if relative.startswith("schemas/"):
        return "application/schema+json"
    if relative.endswith(".json"):
        return "application/json"
    if relative.endswith(".csv"):
        return "text/csv; charset=utf-8"
    if relative.endswith(".md"):
        return "text/markdown; charset=utf-8"
    raise IntegrityError(f"unknown scenario library artifact media type: {relative}")


def _record_count(relative: str) -> int | None:
    if relative.startswith(("designs/", "families/")):
        return 1
    if relative == "coverage.csv":
        return 240
    if relative == "registry.json":
        return 270
    if relative == "audit.json":
        return 240
    return None


def build_scenario_library(
    repository_root: Path,
    output_directory: Path,
) -> ScenarioLibraryBuildResult:
    """Build the checksum-complete 282-file scenario library projection."""

    repository_root = repository_root.resolve(strict=True)
    if not (repository_root / "pyproject.toml").is_file():
        raise IntegrityError("scenario library repository root lacks pyproject.toml")
    if output_directory.is_symlink():
        raise IntegrityError("scenario library output directory cannot be a symlink")
    models = build_library_models()
    with tempfile.TemporaryDirectory(prefix="civicdecision-scenario-library-") as temporary:
        staged = Path(temporary) / "scenario-library"
        staged.mkdir(parents=True)
        base_paths: list[Path] = []
        design_paths: list[Path] = []
        family_paths: list[Path] = []
        for design in models.designs:
            relative = f"designs/{design.design_order:03d}-{design.design_id}.json"
            path = _write_model(staged, relative, design)
            base_paths.append(path)
            design_paths.append(path)
        for family in models.families:
            relative = f"families/{family.family_order:02d}-{family.family_id}.json"
            path = _write_model(staged, relative, family)
            base_paths.append(path)
            family_paths.append(path)

        design_entries = [
            ScenarioDesignIndexEntry(
                design_order=item.design_order,
                design_id=item.design_id,
                family_id=item.family_id,
                suite=item.suite,
                title=item.title,
                decision_type=item.decision_type,
                implementation_status=item.implementation_status,
                current_readiness=item.current_readiness,
                existing_template_ref=item.existing_template_ref,
                design_signature=item.design_signature,
                artifact_path=path.relative_to(staged).as_posix(),
                content_hash=item.content_hash(),
            )
            for item, path in zip(models.designs, design_paths, strict=True)
        ]
        family_entries = [
            ScenarioFamilyIndexEntry(
                family_order=item.family_order,
                family_id=item.family_id,
                suite=item.suite,
                title=item.title,
                artifact_path=path.relative_to(staged).as_posix(),
                content_hash=item.content_hash(),
            )
            for item, path in zip(models.families, family_paths, strict=True)
        ]
        record_set_hash = sha256_bytes(
            canonical_json(
                {
                    "designs": [item.content_hash for item in design_entries],
                    "families": [item.content_hash for item in family_entries],
                }
            )
        )
        registry = ScenarioLibraryRegistry(
            published_at=PUBLISHED_AT,
            suite_counts=_counter((item.suite for item in models.designs), ApplicationSuite),
            decision_type_counts=_counter(
                (item.decision_type for item in models.designs), DecisionType
            ),
            implementation_status_counts=_counter(
                (item.implementation_status for item in models.designs), ImplementationStatus
            ),
            current_readiness_counts=_counter(
                (item.current_readiness for item in models.designs), CurrentReadiness
            ),
            definitions_hash=models.definitions_hash,
            artifact_set_hash=record_set_hash,
            designs=design_entries,
            families=family_entries,
            claim_boundary=[
                "The catalog contains 240 decision designs, not 240 city executions.",
                "Exactly twelve designs map to existing Tier-D reference templates; 228 remain design-only.",
                "A reference implementation can be an explicit negative release and does not imply impact.",
                "No record claims a city binding, new method, deployment, adoption, or real-user outcome.",
                "Future execution requires source binding, gate passage, and domain, legal, community, and operational review.",
            ],
        )
        base_paths.extend(
            [
                _write_model(staged, "registry.json", registry),
                _write_model(staged, "audit.json", models.audit),
                _write_bytes(staged, "coverage.csv", _coverage_csv(models.designs)),
                _write_bytes(staged, "SUMMARY.md", _summary_markdown(models, registry)),
                _write_bytes(
                    staged,
                    "ANTI_DUPLICATION_AUDIT.md",
                    _anti_duplication_markdown(models),
                ),
            ]
        )
        for relative, schema in sorted(_schema_documents().items()):
            base_paths.append(_write_bytes(staged, relative, _json_bytes(schema)))
        if len(base_paths) != EXPECTED_BASE_ARTIFACTS:
            raise IntegrityError(
                f"scenario library base artifact count is {len(base_paths)}, "
                f"expected {EXPECTED_BASE_ARTIFACTS}"
            )
        artifact_entries = [
            ScenarioLibraryArtifactEntry(
                path=path.relative_to(staged).as_posix(),
                media_type=_media_type(path.relative_to(staged).as_posix()),
                byte_count=path.stat().st_size,
                content_hash=sha256_file(path),
                record_count=_record_count(path.relative_to(staged).as_posix()),
            )
            for path in sorted(base_paths)
        ]
        manifest = ScenarioLibraryManifest(
            published_at=PUBLISHED_AT,
            library_content_hash=record_set_hash,
            artifact_count=len(artifact_entries),
            artifacts=artifact_entries,
            claim_boundary=registry.claim_boundary,
        )
        manifest_path = _write_model(staged, "artifact-manifest.json", manifest)
        checksum_targets = sorted([*base_paths, manifest_path])
        checksum_content = "".join(
            f"{sha256_file(path)[7:]}  {path.relative_to(staged).as_posix()}\n"
            for path in checksum_targets
        ).encode("ascii")
        _write_bytes(staged, "SHA256SUMS", checksum_content)
        staged_paths = tuple(sorted(path for path in staged.rglob("*") if path.is_file()))
        if len(staged_paths) != EXPECTED_TOTAL_FILES:
            raise IntegrityError(
                f"scenario library contains {len(staged_paths)} files, "
                f"expected {EXPECTED_TOTAL_FILES}"
            )
        expected = {path.relative_to(staged) for path in staged_paths}
        existing = (
            {
                path.relative_to(output_directory)
                for path in output_directory.rglob("*")
                if path.is_file()
            }
            if output_directory.exists()
            else set()
        )
        unexpected = existing - expected
        if unexpected:
            raise IntegrityError(
                "scenario library output contains unexpected files: "
                + ", ".join(path.as_posix() for path in sorted(unexpected))
            )
        for staged_path in staged_paths:
            copy_relative = staged_path.relative_to(staged)
            atomic_write(output_directory / copy_relative, staged_path.read_bytes())

    final_paths = tuple(sorted(path for path in output_directory.rglob("*") if path.is_file()))
    return ScenarioLibraryBuildResult(
        output_directory=output_directory,
        registry_path=output_directory / "registry.json",
        audit_path=output_directory / "audit.json",
        manifest_path=output_directory / "artifact-manifest.json",
        checksum_path=output_directory / "SHA256SUMS",
        design_paths=tuple(
            path for path in final_paths if path.relative_to(output_directory).parts[0] == "designs"
        ),
        family_paths=tuple(
            path
            for path in final_paths
            if path.relative_to(output_directory).parts[0] == "families"
        ),
        artifact_paths=final_paths,
    )


__all__ = [
    "HIGH_SIMILARITY_THRESHOLD",
    "PUBLISHED_AT",
    "LibraryModels",
    "ScenarioLibraryBuildResult",
    "build_library_models",
    "build_scenario_library",
]
