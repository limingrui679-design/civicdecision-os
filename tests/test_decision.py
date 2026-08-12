from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

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
from civicdecision.protocols.source import SourceManifest


def evidence() -> EvidenceItem:
    return EvidenceItem(
        id="evidence-1",
        type=EvidenceType.OBSERVED,
        status=EvidenceStatus.ESTABLISHED,
        title="Observed source row",
        summary="A source row exists.",
        source_refs=["test-source-page-1"],
        limitations=["Fixture only."],
    )


def reproducibility() -> Reproducibility:
    return Reproducibility(
        software_version="0.1.0",
        command=["civicdecision", "demo", "run"],
        random_seed=42,
        environment={"python": "3.12"},
        parameters={"fixture": True},
        source_hashes=["sha256:" + "0" * 64],
    )


def reversal_test() -> ReversalTest:
    return ReversalTest(
        id="radius-down",
        parameter="service_radius_km",
        baseline_value=1.0,
        tested_value=0.5,
        unit="km",
        baseline_option_id="option-a",
        selected_option_id_after_test="option-b",
        outcome=ReversalOutcome.REVERSED,
        evidence_type=EvidenceType.SIMULATED,
        method="Re-run the deterministic fixture at the tested radius.",
        limitations=["Fixture sensitivity only."],
    )


def value_of_information() -> ValueOfInformation:
    return ValueOfInformation(
        id="travel-time-network",
        uncertainty="The fixture uses radius instead of observed travel time.",
        decision_link="A network could change the selected option.",
        collection_action="Acquire a versioned pedestrian and transit network.",
        priority_score=0.9,
        limitations=["Priority is a planning judgment, not a measured monetary VOI."],
    )


def test_completed_pack_selects_feasible_option(source_manifest: SourceManifest) -> None:
    pack = DecisionPack(
        run_id="run-1",
        scenario_id="scenario-1",
        created_at=datetime(2026, 8, 12, tzinfo=UTC),
        status=RunStatus.COMPLETED,
        source_manifests=[source_manifest],
        evidence=[evidence()],
        options=[
            DecisionOption(
                id="option-a",
                label="Option A",
                evidence_type=EvidenceType.OPTIMIZED,
                feasible=True,
                metrics={"cost": 10},
                limitations=["Fixture only."],
            )
        ],
        recommendation=Recommendation(
            selected_option_id="option-a",
            evidence_type=EvidenceType.OPTIMIZED,
            rationale="Option A minimizes fixture cost.",
            limitations=["Fixture only."],
        ),
        reversal_tests=[reversal_test()],
        value_of_information=[value_of_information()],
        reproducibility=reproducibility(),
    )
    assert pack.content_hash().startswith("sha256:")
    assert pack.content_hash() == pack.content_hash()


def test_completed_pack_rejects_infeasible_selection(source_manifest: SourceManifest) -> None:
    with pytest.raises(ValidationError, match="must be feasible"):
        DecisionPack(
            run_id="run-2",
            scenario_id="scenario-1",
            created_at=datetime(2026, 8, 12, tzinfo=UTC),
            status=RunStatus.COMPLETED,
            source_manifests=[source_manifest],
            evidence=[evidence()],
            options=[
                DecisionOption(
                    id="option-a",
                    label="Option A",
                    evidence_type=EvidenceType.OPTIMIZED,
                    feasible=False,
                    metrics={},
                    limitations=["Infeasible."],
                )
            ],
            recommendation=Recommendation(
                selected_option_id="option-a",
                evidence_type=EvidenceType.OPTIMIZED,
                rationale="Invalid fixture.",
                limitations=["Fixture only."],
            ),
            reversal_tests=[reversal_test()],
            value_of_information=[value_of_information()],
            reproducibility=reproducibility(),
        )


@pytest.mark.parametrize(
    "status",
    [RunStatus.FAILED, RunStatus.INSUFFICIENT_EVIDENCE, RunStatus.INFEASIBLE, RunStatus.TIMED_OUT],
)
def test_negative_run_is_a_valid_release(
    status: RunStatus, source_manifest: SourceManifest
) -> None:
    pack = DecisionPack(
        run_id=f"run-{status.value}",
        scenario_id="scenario-1",
        created_at=datetime(2026, 8, 12, tzinfo=UTC),
        status=status,
        source_manifests=[source_manifest],
        evidence=[
            EvidenceItem(
                id="evidence-failed",
                type=EvidenceType.ESTIMATED,
                status=EvidenceStatus.FAILED,
                title="Baseline not exceeded",
                summary="The model did not establish useful performance.",
                method="fixture baseline comparison",
                limitations=["No recommendation can be supported."],
            )
        ],
        recommendation=Recommendation(
            evidence_type=EvidenceType.PROPOSED,
            rationale="Do not act on this run.",
            required_next_evidence=["Obtain a valid held-out result."],
            limitations=["No option is supported."],
        ),
        failure_reason=f"Run ended with {status.value}.",
        reproducibility=reproducibility(),
    )
    assert pack.recommendation.selected_option_id is None


def test_negative_run_cannot_select_option(source_manifest: SourceManifest) -> None:
    with pytest.raises(ValidationError, match="cannot select"):
        DecisionPack(
            run_id="run-failed",
            scenario_id="scenario-1",
            created_at=datetime(2026, 8, 12, tzinfo=UTC),
            status=RunStatus.FAILED,
            source_manifests=[source_manifest],
            evidence=[evidence()],
            options=[],
            recommendation=Recommendation(
                selected_option_id="option-a",
                evidence_type=EvidenceType.PROPOSED,
                rationale="Invalid selection.",
                required_next_evidence=["More evidence."],
                limitations=["Fixture only."],
            ),
            failure_reason="Failure.",
            reproducibility=reproducibility(),
        )


@pytest.mark.parametrize("evidence_type", [EvidenceType.OBSERVED, EvidenceType.CAUSAL])
def test_decision_option_rejects_nondecision_evidence(evidence_type: EvidenceType) -> None:
    with pytest.raises(ValidationError, match="decision options"):
        DecisionOption(
            id="option-a",
            label="Option A",
            evidence_type=evidence_type,
            feasible=True,
            metrics={},
            limitations=["Fixture only."],
        )


def test_recommendation_rejects_simulated_evidence() -> None:
    with pytest.raises(ValidationError, match="must be optimized or proposed"):
        Recommendation(
            evidence_type=EvidenceType.SIMULATED,
            rationale="Invalid recommendation type.",
            limitations=["Fixture only."],
        )


def test_reversal_and_voi_reject_evidence_upgrades() -> None:
    with pytest.raises(ValidationError, match="estimated or simulated"):
        ReversalTest(
            **{
                **reversal_test().model_dump(),
                "evidence_type": EvidenceType.CAUSAL,
            }
        )
    with pytest.raises(ValidationError, match="must be proposed"):
        ValueOfInformation(
            **{
                **value_of_information().model_dump(),
                "evidence_type": EvidenceType.OBSERVED,
            }
        )


def completed_pack_payload(source_manifest: SourceManifest) -> dict[str, object]:
    pack = DecisionPack(
        run_id="run-valid",
        scenario_id="scenario-1",
        created_at=datetime(2026, 8, 12, tzinfo=UTC),
        status=RunStatus.COMPLETED,
        source_manifests=[source_manifest],
        evidence=[evidence()],
        options=[
            DecisionOption(
                id="option-a",
                label="Option A",
                evidence_type=EvidenceType.OPTIMIZED,
                feasible=True,
                metrics={"cost": 10},
                limitations=["Fixture only."],
            )
        ],
        recommendation=Recommendation(
            selected_option_id="option-a",
            evidence_type=EvidenceType.OPTIMIZED,
            rationale="Fixture selection.",
            limitations=["Fixture only."],
        ),
        reversal_tests=[reversal_test()],
        value_of_information=[value_of_information()],
        reproducibility=reproducibility(),
    )
    return pack.model_dump(mode="json")


def test_completed_pack_requires_selection(source_manifest: SourceManifest) -> None:
    payload = completed_pack_payload(source_manifest)
    payload["recommendation"]["selected_option_id"] = None  # type: ignore[index]
    with pytest.raises(ValidationError, match="require a selected option"):
        DecisionPack.model_validate(payload)


def test_completed_pack_requires_existing_selection(source_manifest: SourceManifest) -> None:
    payload = completed_pack_payload(source_manifest)
    payload["recommendation"]["selected_option_id"] = "option-missing"  # type: ignore[index]
    with pytest.raises(ValidationError, match="does not exist"):
        DecisionPack.model_validate(payload)


@pytest.mark.parametrize(
    ("field", "message"),
    [
        ("reversal_tests", "reversal test"),
        ("value_of_information", "value-of-information"),
    ],
)
def test_completed_pack_requires_decision_diagnostics(
    source_manifest: SourceManifest, field: str, message: str
) -> None:
    payload = completed_pack_payload(source_manifest)
    payload[field] = []
    with pytest.raises(ValidationError, match=message):
        DecisionPack.model_validate(payload)


def test_pack_rejects_duplicate_option_ids(source_manifest: SourceManifest) -> None:
    payload = completed_pack_payload(source_manifest)
    payload["options"].append(payload["options"][0])  # type: ignore[union-attr,index]
    with pytest.raises(ValidationError, match="option ids must be unique"):
        DecisionPack.model_validate(payload)


@pytest.mark.parametrize(
    ("remove_failure", "remove_next", "message"),
    [
        (True, False, "require a failure reason"),
        (False, True, "next-evidence guidance"),
    ],
)
def test_negative_pack_requires_release_guidance(
    source_manifest: SourceManifest,
    remove_failure: bool,
    remove_next: bool,
    message: str,
) -> None:
    payload = completed_pack_payload(source_manifest)
    payload["status"] = "failed"
    payload["recommendation"]["selected_option_id"] = None  # type: ignore[index]
    payload["recommendation"]["required_next_evidence"] = (  # type: ignore[index]
        [] if remove_next else ["Collect a held-out result."]
    )
    payload["failure_reason"] = None if remove_failure else "Fixture failure."
    with pytest.raises(ValidationError, match=message):
        DecisionPack.model_validate(payload)
