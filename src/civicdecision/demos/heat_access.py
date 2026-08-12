"""Evidence-typed heat-access facility planning reference workflow."""

from __future__ import annotations

import json
import platform
from pathlib import Path
from typing import Literal

from pydantic import Field, TypeAdapter, ValidationError

from civicdecision import __version__
from civicdecision.connectors.base import atomic_write
from civicdecision.errors import AnalysisError
from civicdecision.io import load_document, validate_document
from civicdecision.optimization.facility import (
    DemandPoint,
    FacilityPlan,
    FacilityPlanningConfig,
    enumerate_facility_plans,
    select_best_plan,
)
from civicdecision.protocols.base import StrictModel, canonical_json, sha256_bytes, sha256_file
from civicdecision.protocols.decision import (
    DecisionOption,
    DecisionPack,
    Recommendation,
    Reproducibility,
    ReversalOutcome,
    ReversalTest,
    RunStatus,
    ValueOfInformation,
)
from civicdecision.protocols.evidence import EvidenceItem, EvidenceStatus, EvidenceType
from civicdecision.protocols.scenario import PolicyScenario
from civicdecision.protocols.source import SourceManifest


class GeoPoint(StrictModel):
    type: Literal["Point"]
    coordinates: tuple[float, float]


class CDCTractRow(StrictModel):
    stateabbr: str = Field(pattern=r"^[A-Z]{2}$")
    statedesc: str = Field(min_length=1)
    countyname: str = Field(min_length=1)
    countyfips: str = Field(pattern=r"^[0-9]{5}$")
    tractfips: str = Field(pattern=r"^[0-9]{11}$")
    totalpopulation: int = Field(ge=0)
    totalpop18plus: int = Field(ge=0)
    access2_crudeprev: float = Field(ge=0, le=100)
    casthma_crudeprev: float = Field(ge=0, le=100)
    copd_crudeprev: float = Field(ge=0, le=100)
    diabetes_crudeprev: float = Field(ge=0, le=100)
    ghlth_crudeprev: float = Field(ge=0, le=100)
    obesity_crudeprev: float = Field(ge=0, le=100)
    lacktrpt_crudeprev: float = Field(ge=0, le=100)
    geolocation: GeoPoint


class HeatAccessDemoConfig(FacilityPlanningConfig):
    sensitivity_radii_km: tuple[float, ...] = (0.5, 0.75, 1.0, 1.5, 2.0)


class DecisionArtifacts(StrictModel):
    pack_path: Path
    brief_path: Path
    checksum_path: Path
    content_hash: str


def _portable_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return path.name


def _load_inputs(
    data_path: Path, manifest_path: Path, scenario_path: Path
) -> tuple[list[CDCTractRow], SourceManifest, PolicyScenario]:
    manifest = validate_document(manifest_path, SourceManifest)
    expected_artifact = (manifest_path.parent / manifest.artifact_path).resolve()
    if data_path.resolve() != expected_artifact:
        raise AnalysisError("data path does not match the artifact declared by the manifest")
    manifest.verify_artifact(manifest_path.parent)
    try:
        rows = TypeAdapter(list[CDCTractRow]).validate_python(load_document(data_path))
    except (ValidationError, TypeError) as exc:
        raise AnalysisError(f"CDC PLACES sample failed row validation: {exc}") from exc
    if not rows:
        raise AnalysisError("CDC PLACES sample is empty")
    if len(rows) != manifest.record_count:
        raise AnalysisError(
            f"record count mismatch: manifest={manifest.record_count}, parsed={len(rows)}"
        )
    scenario = validate_document(scenario_path, PolicyScenario)
    return rows, manifest, scenario


def _demand_points(rows: list[CDCTractRow]) -> list[DemandPoint]:
    return [
        DemandPoint(
            id=row.tractfips,
            latitude=row.geolocation.coordinates[1],
            longitude=row.geolocation.coordinates[0],
            population=row.totalpopulation,
            estimated_need=round(
                row.totalpopulation * row.lacktrpt_crudeprev / 100,
                6,
            ),
            priority_rate=row.lacktrpt_crudeprev,
        )
        for row in rows
    ]


def _evidence(
    manifest: SourceManifest,
    scenario: PolicyScenario,
    points: list[DemandPoint],
    plans: list[FacilityPlan],
    config: HeatAccessDemoConfig,
) -> list[EvidenceItem]:
    estimated_need = sum(point.estimated_need for point in points)
    feasible_count = sum(plan.feasible for plan in plans)
    return [
        EvidenceItem(
            id="source-artifact-rows",
            type=EvidenceType.OBSERVED,
            status=EvidenceStatus.ESTABLISHED,
            title="Versioned public artifact rows",
            summary=f"The verified artifact contains {len(points)} parsed census-tract rows.",
            source_refs=[manifest.artifact_id],
            limitations=[
                "Observed here means artifact presence and parsed row count, "
                "not observed health outcomes."
            ],
        ),
        EvidenceItem(
            id="transport-limited-proxy",
            type=EvidenceType.ESTIMATED,
            status=EvidenceStatus.LIMITED,
            title="Estimated transport-limited population proxy",
            summary=(
                "The bounded sample contains an estimated proxy total of "
                f"{estimated_need:.3f} people."
            ),
            source_refs=[manifest.artifact_id],
            method=(
                "tract total population multiplied by CDC PLACES lack-of-transport crude prevalence"
            ),
            assumptions=["Area prevalence is applied to the corresponding tract population."],
            limitations=[
                "CDC PLACES values are model-based area estimates and are not "
                "individual observations.",
                "The multiplication is a planning proxy and does not identify "
                "actual service users.",
            ],
        ),
        EvidenceItem(
            id="radius-coverage-model",
            type=EvidenceType.SIMULATED,
            status=EvidenceStatus.LIMITED,
            title="Straight-line service-radius coverage",
            summary=(
                f"Coverage is simulated at a {config.service_radius_km:.2f} km radius "
                "around tract-centroid candidates."
            ),
            scenario_ref=scenario.scenario_id,
            assumptions=[
                "A tract is covered when its centroid lies within the declared great-circle radius."
            ],
            limitations=[
                "The simulation omits street topology, schedules, barriers, capacity, "
                "and travel time."
            ],
        ),
        EvidenceItem(
            id="bounded-enumeration",
            type=EvidenceType.OPTIMIZED,
            status=EvidenceStatus.LIMITED,
            title="Exhaustive bounded candidate enumeration",
            summary=(
                f"The engine evaluated {len(plans)} combinations and found "
                f"{feasible_count} feasible under declared constraints."
            ),
            objective="maximize estimated need coverage minus a declared normalized cost penalty",
            constraints=[
                f"cost <= {config.budget:.2f}",
                f"priority coverage >= {config.minimum_priority_coverage:.3f}",
                f"facility count <= {config.max_facilities}",
            ],
            limitations=[
                "Optimality holds only for the bounded tract-centroid candidate set "
                "and declared proxy model."
            ],
        ),
        EvidenceItem(
            id="pilot-candidate-status",
            type=EvidenceType.PROPOSED,
            status=EvidenceStatus.LIMITED,
            title="Candidate sites are planning inputs",
            summary=(
                "Every candidate location is a tract centroid used for demonstration, "
                "not a verified facility."
            ),
            limitations=[
                "Site ownership, operating feasibility, capacity, accessibility, and "
                "community acceptance are unknown."
            ],
        ),
    ]


def _options(plans: list[FacilityPlan]) -> list[DecisionOption]:
    return [
        DecisionOption(
            id=plan.option_id,
            label="Tract-centroid candidates " + ", ".join(plan.selected_ids),
            evidence_type=EvidenceType.OPTIMIZED,
            feasible=plan.feasible,
            metrics={
                "selected_sites": ",".join(plan.selected_ids),
                "estimated_need_covered": plan.estimated_need_covered,
                "overall_coverage_rate": plan.overall_coverage_rate,
                "priority_coverage_rate": plan.priority_coverage_rate,
                "cost": plan.cost,
                "objective_score": plan.objective_score,
            },
            binding_constraints=plan.binding_constraints,
            limitations=[
                "Candidate sites are tract centroids, not verified facilities.",
                "Coverage is simulated by straight-line radius.",
                "Need counts use model-based area prevalence as a planning proxy.",
            ],
        )
        for plan in plans
    ]


def _reversal_tests(
    points: list[DemandPoint],
    config: HeatAccessDemoConfig,
    baseline: FacilityPlan,
) -> list[ReversalTest]:
    tests: list[ReversalTest] = []
    for radius in config.sensitivity_radii_km:
        if abs(radius - config.service_radius_km) < 1e-12:
            continue
        payload = config.model_dump()
        payload["service_radius_km"] = radius
        tested_config = HeatAccessDemoConfig.model_validate(payload)
        tested_best = select_best_plan(enumerate_facility_plans(points, tested_config))
        if tested_best is None:
            outcome = ReversalOutcome.INCONCLUSIVE
            selected_after = None
        elif tested_best.selected_ids == baseline.selected_ids:
            outcome = ReversalOutcome.STABLE
            selected_after = tested_best.option_id
        else:
            outcome = ReversalOutcome.REVERSED
            selected_after = tested_best.option_id
        radius_id = f"{radius:.2f}".replace(".", "-")
        tests.append(
            ReversalTest(
                id=f"service-radius-{radius_id}",
                parameter="service_radius_km",
                baseline_value=config.service_radius_km,
                tested_value=radius,
                unit="km",
                baseline_option_id=baseline.option_id,
                selected_option_id_after_test=selected_after,
                outcome=outcome,
                evidence_type=EvidenceType.SIMULATED,
                method=(
                    "Re-enumerate every candidate combination while changing only service radius."
                ),
                limitations=[
                    "Sensitivity results inherit the straight-line coverage and "
                    "tract-centroid assumptions."
                ],
            )
        )
    if not tests:
        raise AnalysisError("at least one distinct sensitivity radius is required")
    return tests


def _value_of_information() -> list[ValueOfInformation]:
    return [
        ValueOfInformation(
            id="network-travel-time",
            uncertainty="Straight-line radius may misrepresent accessible travel time.",
            decision_link=(
                "A network model can change coverage, feasibility, and the selected sites."
            ),
            collection_action=(
                "Build a versioned pedestrian and transit network with timed routing."
            ),
            priority_score=1.0,
            limitations=[
                "Priority is a declared planning judgment, not a monetized EVPI estimate."
            ],
        ),
        ValueOfInformation(
            id="facility-feasibility",
            uncertainty="Tract centroids have not been verified as operable cooling facilities.",
            decision_link="Ineligible sites would invalidate or constrain the selected plan.",
            collection_action=(
                "Verify candidate facilities, hours, accessibility, capacity, and cost."
            ),
            priority_score=0.98,
            limitations=[
                "This item proposes field validation; no facility audit has been performed."
            ],
        ),
        ValueOfInformation(
            id="individual-demand",
            uncertainty="Area-level modeled prevalence does not identify actual service demand.",
            decision_link="Observed demand could alter equity weights and facility priorities.",
            collection_action="Collect privacy-preserving, consented service-demand evidence.",
            priority_score=0.92,
            limitations=["Collection must pass privacy, ethics, and representativeness review."],
        ),
    ]


def build_heat_access_pack(
    data_path: Path,
    manifest_path: Path,
    scenario_path: Path,
    config: HeatAccessDemoConfig | None = None,
    config_reference: Path | None = None,
) -> DecisionPack:
    """Compile public sample data into a deterministic evidence-typed DecisionPack."""

    config = config or HeatAccessDemoConfig()
    rows, manifest, scenario = _load_inputs(data_path, manifest_path, scenario_path)
    points = _demand_points(rows)
    plans = enumerate_facility_plans(points, config)
    best = select_best_plan(plans)
    evidence = _evidence(manifest, scenario, points, plans, config)
    options = _options(plans)
    run_key = sha256_bytes(
        canonical_json(
            {
                "scenario_id": scenario.scenario_id,
                "source_hash": manifest.content_hash,
                "config": config.model_dump(mode="json"),
            }
        )
    )[7:19]
    command = [
        "civicdecision",
        "demo",
        "heat-access",
        "--data",
        _portable_path(data_path),
        "--manifest",
        _portable_path(manifest_path),
        "--scenario",
        _portable_path(scenario_path),
    ]
    if config_reference is not None:
        command.extend(["--config", _portable_path(config_reference)])
    reproducibility = Reproducibility(
        software_version=__version__,
        command=command,
        random_seed=scenario.random_seed,
        environment={"python": platform.python_version(), "algorithm": "exhaustive-enumeration"},
        parameters=config.model_dump(mode="json"),
        source_hashes=[manifest.content_hash],
    )
    voi = _value_of_information()
    if best is None:
        return DecisionPack(
            run_id=f"run-{run_key}",
            scenario_id=scenario.scenario_id,
            created_at=scenario.as_of,
            status=RunStatus.INFEASIBLE,
            source_manifests=[manifest],
            evidence=evidence,
            options=options,
            recommendation=Recommendation(
                evidence_type=EvidenceType.PROPOSED,
                rationale="No candidate combination satisfies every declared hard constraint.",
                required_next_evidence=[
                    "Validate the constraints and collect feasible facility candidates."
                ],
                limitations=["No action is supported by this infeasible run."],
            ),
            value_of_information=voi,
            failure_reason="The bounded candidate set has no feasible plan.",
            reproducibility=reproducibility,
        )

    reversal_tests = _reversal_tests(points, config, best)
    reversed_tests = [test for test in reversal_tests if test.outcome is ReversalOutcome.REVERSED]
    inconclusive_tests = [
        test for test in reversal_tests if test.outcome is ReversalOutcome.INCONCLUSIVE
    ]
    reversal_conditions = [
        (
            f"Selection changes at service_radius_km={test.tested_value}; "
            f"the tested option is {test.selected_option_id_after_test}."
        )
        for test in reversed_tests
    ]
    reversal_conditions.extend(
        f"No feasible plan remains at service_radius_km={test.tested_value}."
        for test in inconclusive_tests
    )
    if not reversal_conditions:
        reversal_conditions.append(
            "The selected sites remain stable only across the declared sensitivity grid."
        )
    return DecisionPack(
        run_id=f"run-{run_key}",
        scenario_id=scenario.scenario_id,
        created_at=scenario.as_of,
        status=RunStatus.COMPLETED,
        source_manifests=[manifest],
        evidence=evidence,
        options=options,
        recommendation=Recommendation(
            selected_option_id=best.option_id,
            evidence_type=EvidenceType.OPTIMIZED,
            rationale=(
                "This option has the highest declared objective score among feasible "
                "bounded tract-centroid combinations. It is a methods demonstration, "
                "not an implementation recommendation."
            ),
            reversal_conditions=reversal_conditions,
            required_next_evidence=[item.collection_action for item in voi],
            limitations=[
                "The selected plan is optimized only within the declared proxy model.",
                "No facility has been verified, opened, funded, or observed in operation.",
            ],
        ),
        reversal_tests=reversal_tests,
        value_of_information=voi,
        reproducibility=reproducibility,
    )


def render_decision_brief(pack: DecisionPack) -> str:
    """Render a human-readable brief from the same validated DecisionPack."""

    selected = next(
        (option for option in pack.options if option.id == pack.recommendation.selected_option_id),
        None,
    )
    lines = [
        "# CivicDecision OS — Heat-access reference Decision Brief",
        "",
        f"- Run: `{pack.run_id}`",
        f"- Scenario: `{pack.scenario_id}`",
        f"- Status: `{pack.status.value}`",
        f"- DecisionPack content hash: `{pack.content_hash()}`",
        "",
        "## Claim boundary",
        "",
        (
            "This is a reproducible methods demonstration over a bounded public-data sample. "
            "It is not a deployed service, causal impact estimate, verified facility plan, "
            "municipal recommendation, or record of real-world adoption."
        ),
        "",
        "## Result",
        "",
        pack.recommendation.rationale,
    ]
    if selected is not None:
        lines.extend(
            [
                "",
                f"Selected bounded option: `{selected.id}`",
                "",
                "| Metric | Value |",
                "|---|---:|",
            ]
        )
        lines.extend(f"| {key} | {value} |" for key, value in selected.metrics.items())
    if pack.failure_reason:
        lines.extend(["", f"Failure reason: {pack.failure_reason}"])
    lines.extend(["", "## Evidence layers", ""])
    lines.extend(
        f"- **{item.type.value} / {item.status.value}:** {item.summary}" for item in pack.evidence
    )
    lines.extend(
        [
            "",
            "## Reversal tests",
            "",
            "| Parameter | Baseline | Tested | Outcome | Selected after test |",
            "|---|---:|---:|---|---|",
        ]
    )
    lines.extend(
        (
            f"| {test.parameter} | {test.baseline_value} | {test.tested_value} | "
            f"{test.outcome.value} | {test.selected_option_id_after_test or 'none'} |"
        )
        for test in pack.reversal_tests
    )
    lines.extend(["", "## Highest-priority evidence gaps", ""])
    lines.extend(
        f"- `{item.priority_score:.2f}` — **{item.uncertainty}** {item.collection_action}"
        for item in sorted(
            pack.value_of_information,
            key=lambda item: (-item.priority_score, item.id),
        )
    )
    lines.extend(
        ["", "## Reproduce", "", "```bash", " ".join(pack.reproducibility.command), "```", ""]
    )
    return "\n".join(lines)


def write_decision_artifacts(pack: DecisionPack, output_dir: Path) -> DecisionArtifacts:
    """Write, re-read, and checksum JSON and Markdown artifacts without absolute paths."""

    output_dir.mkdir(parents=True, exist_ok=True)
    pack_path = output_dir / "decision-pack.json"
    brief_path = output_dir / "decision-brief.md"
    checksum_path = output_dir / "SHA256SUMS"
    payload = json.dumps(
        pack.model_dump(mode="json", exclude_none=True),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ).encode("utf-8")
    atomic_write(pack_path, payload + b"\n")
    round_trip = DecisionPack.model_validate_json(pack_path.read_bytes())
    if round_trip.content_hash() != pack.content_hash():
        raise AnalysisError("serialized DecisionPack failed canonical round-trip verification")
    atomic_write(brief_path, render_decision_brief(pack).encode("utf-8"))
    file_hash = sha256_file(pack_path)
    atomic_write(checksum_path, f"{file_hash[7:]}  {pack_path.name}\n".encode("ascii"))
    return DecisionArtifacts(
        pack_path=pack_path,
        brief_path=brief_path,
        checksum_path=checksum_path,
        content_hash=pack.content_hash(),
    )
