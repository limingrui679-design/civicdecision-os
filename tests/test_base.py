from __future__ import annotations

from datetime import datetime

import pytest
from pydantic import ValidationError

from civicdecision.protocols.base import (
    IdentifiedModel,
    StrictModel,
    canonical_json,
    schema_fingerprint,
    sha256_bytes,
)
from civicdecision.protocols.evidence import EvidenceItem, EvidenceStatus, EvidenceType


def test_canonical_json_is_order_independent() -> None:
    assert canonical_json({"b": 2, "a": 1}) == canonical_json({"a": 1, "b": 2})
    assert (
        canonical_json(
            {"value": 1.23456789012345, "nested": [4.263872967422037e-16, -0.0]},
            float_significant_digits=12,
        )
        == b'{"nested":[4.26387296742e-16,0.0],"value":1.23456789012}'
    )
    with pytest.raises(ValueError, match="between 1 and 17"):
        canonical_json({"value": 1.0}, float_significant_digits=0)


def test_canonical_json_rejects_nan() -> None:
    with pytest.raises(ValueError):
        canonical_json({"value": float("nan")})


class NumericContractFixture(StrictModel):
    value: float


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_every_strict_protocol_rejects_nonfinite_floats(value: float) -> None:
    with pytest.raises(ValidationError, match="finite number"):
        NumericContractFixture(value=value)


def test_sha256_is_namespaced_and_stable() -> None:
    assert sha256_bytes(b"civicdecision") == (
        "sha256:e7270047a5d8858d872931f4a4dfdee6896006cb7f6019db65cef399f9b9b08c"
    )


def test_schema_fingerprint_is_order_independent() -> None:
    left = schema_fingerprint([{"a": 1, "b": "x"}, {"a": 2}])
    right = schema_fingerprint([{"b": "x", "a": 2}, {"a": 1}])
    assert left == right


def test_identifier_rejects_uppercase_and_spaces() -> None:
    with pytest.raises(ValidationError, match="identifier must be lowercase"):
        IdentifiedModel(id="Not Valid")


def test_observed_requires_source_reference() -> None:
    with pytest.raises(ValidationError, match="source reference"):
        EvidenceItem(
            id="observed-1",
            type=EvidenceType.OBSERVED,
            status=EvidenceStatus.ESTABLISHED,
            title="Observed",
            summary="A value was observed.",
        )


def test_causal_requires_design_and_diagnostics() -> None:
    with pytest.raises(ValidationError, match="identification strategy"):
        EvidenceItem(
            id="causal-1",
            type=EvidenceType.CAUSAL,
            status=EvidenceStatus.LIMITED,
            title="Causal claim",
            summary="A causal effect is claimed.",
            source_refs=["source-1"],
        )


@pytest.mark.parametrize(
    ("evidence_type", "extra"),
    [
        (EvidenceType.OBSERVED, {"source_refs": ["source-1"]}),
        (EvidenceType.ESTIMATED, {"method": "cross-validated estimate"}),
        (
            EvidenceType.CAUSAL,
            {
                "identification_strategy": "difference-in-differences",
                "diagnostics": ["parallel-trends pre-test"],
            },
        ),
        (EvidenceType.SIMULATED, {"scenario_ref": "scenario-1"}),
        (
            EvidenceType.OPTIMIZED,
            {"objective": "minimize cost", "constraints": ["budget"]},
        ),
        (EvidenceType.PROPOSED, {"limitations": ["Not yet implemented."]}),
    ],
)
def test_all_evidence_types_validate_when_their_gate_is_met(
    evidence_type: EvidenceType, extra: dict[str, object]
) -> None:
    item = EvidenceItem(
        id=f"evidence-{evidence_type.value}",
        type=evidence_type,
        status=EvidenceStatus.ESTABLISHED,
        title="Typed evidence",
        summary="The evidence gate is satisfied.",
        **extra,
    )
    assert item.type is evidence_type


@pytest.mark.parametrize(
    ("evidence_type", "extra", "message"),
    [
        (EvidenceType.ESTIMATED, {}, "requires a method"),
        (
            EvidenceType.CAUSAL,
            {"identification_strategy": "regression discontinuity"},
            "requires diagnostics",
        ),
        (EvidenceType.SIMULATED, {}, "scenario reference"),
        (EvidenceType.OPTIMIZED, {}, "requires an objective"),
        (EvidenceType.OPTIMIZED, {"objective": "minimize risk"}, "named constraints"),
        (EvidenceType.PROPOSED, {}, "explicit limitations"),
    ],
)
def test_evidence_type_specific_missing_fields_are_rejected(
    evidence_type: EvidenceType, extra: dict[str, object], message: str
) -> None:
    with pytest.raises(ValidationError, match=message):
        EvidenceItem(
            id="missing-gate",
            type=evidence_type,
            status=EvidenceStatus.ESTABLISHED,
            title="Missing gate",
            summary="The evidence gate is intentionally incomplete.",
            **extra,
        )


def test_failed_evidence_requires_limitations() -> None:
    with pytest.raises(ValidationError, match="limitations"):
        EvidenceItem(
            id="estimate-1",
            type=EvidenceType.ESTIMATED,
            status=EvidenceStatus.FAILED,
            title="Failed estimate",
            summary="The estimate did not beat baseline.",
            method="test model",
        )


def test_protocol_rejects_timezone_naive_datetime(source_manifest: object) -> None:
    payload = source_manifest.model_dump()  # type: ignore[attr-defined]
    payload["retrieved_at"] = datetime(2026, 8, 12)
    with pytest.raises(ValidationError, match="timezone"):
        type(source_manifest).model_validate(payload)
