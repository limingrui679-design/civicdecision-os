from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from civicdecision.cli import app
from civicdecision.deep.models import ApplicationSuite
from civicdecision.deep.templates import DEEP_SCENARIO_TEMPLATES
from civicdecision.errors import IntegrityError
from civicdecision.protocols.base import sha256_file
from civicdecision.scenario_library.build import (
    EXPECTED_BASE_ARTIFACTS,
    EXPECTED_TOTAL_FILES,
    HIGH_SIMILARITY_THRESHOLD,
    LibraryModels,
    build_library_models,
    build_scenario_library,
)
from civicdecision.scenario_library.models import (
    CurrentReadiness,
    DecisionType,
    ImplementationStatus,
    ScenarioDesign,
    ScenarioFamily,
    ScenarioLibraryAudit,
    ScenarioLibraryManifest,
    ScenarioLibraryRegistry,
)

ROOT = Path(__file__).parents[1]
COMMITTED = ROOT / "catalog/scenario-library"
runner = CliRunner()


@pytest.fixture(scope="module")
def library_models() -> LibraryModels:
    return build_library_models()


@pytest.fixture(scope="module")
def rebuilt_library(tmp_path_factory: pytest.TempPathFactory) -> Path:
    output = tmp_path_factory.mktemp("scenario-library") / "catalog"
    build_scenario_library(ROOT, output)
    return output


def test_scenario_library_authored_matrix_and_counts(library_models: LibraryModels) -> None:
    assert len(library_models.designs) == 240
    assert len(library_models.families) == 30
    assert [item.design_order for item in library_models.designs] == list(range(1, 241))
    assert [item.family_order for item in library_models.families] == list(range(1, 31))
    assert Counter(item.suite for item in library_models.designs) == {
        ApplicationSuite.CLIMATE_DISASTER: 40,
        ApplicationSuite.MOBILITY_ACCESS: 40,
        ApplicationSuite.POPULATION_HEALTH: 32,
        ApplicationSuite.HOUSING_LAND_USE: 32,
        ApplicationSuite.PUBLIC_SERVICE: 32,
        ApplicationSuite.INFRASTRUCTURE_FINANCE: 32,
        ApplicationSuite.BEHAVIORAL_EQUITY: 32,
    }
    assert Counter(item.decision_type for item in library_models.designs) == {
        kind: 30 for kind in DecisionType
    }
    assert all(set(item.decision_types) == set(DecisionType) for item in library_models.families)


def test_scenario_library_every_design_has_a_full_decision_contract(
    library_models: LibraryModels,
) -> None:
    for design in library_models.designs:
        assert len(design.alternatives) >= 3
        assert len(design.objectives) == 3
        assert sum(item.primary for item in design.objectives) == 1
        assert len(design.constraints) == 3
        assert sum(item.binding for item in design.constraints) == 1
        assert design.analysis_modes and design.evidence_requirements
        assert design.required_source_roles
        assert design.release_gate.failure_status == "insufficient-evidence"
        assert design.release_gate.failure_release
        assert len(design.prohibited_claims) >= 4
        assert len(design.assumptions) >= 3
        assert len(design.limitations) >= 3
        assert len(design.transportability_risks) >= 2
        assert design.city_bindings == [] and design.method_claimed is False
        assert design.design_signature == design.independence_key.signature()


def test_scenario_library_reference_mappings_are_exact_scoped_and_noninflated(
    library_models: LibraryModels,
) -> None:
    implemented = [
        item
        for item in library_models.designs
        if item.implementation_status is ImplementationStatus.REFERENCE_IMPLEMENTED
    ]
    design_only = [
        item
        for item in library_models.designs
        if item.implementation_status is ImplementationStatus.DESIGN_ONLY
    ]
    expected_refs = {item.template_id for item in DEEP_SCENARIO_TEMPLATES}
    assert len(implemented) == 12 and len(design_only) == 228
    assert {item.existing_template_ref for item in implemented} == expected_refs
    assert all(
        item.current_readiness is CurrentReadiness.REFERENCE_IMPLEMENTED for item in implemented
    )
    assert all(item.reference_implementation_note for item in implemented)
    assert all(
        "does not establish" in (item.reference_implementation_note or "") for item in implemented
    )
    assert all(item.existing_template_ref is None for item in design_only)
    assert all(item.reference_implementation_note is None for item in design_only)


def test_scenario_library_audit_covers_uniqueness_and_all_pairwise_comparisons(
    library_models: LibraryModels,
) -> None:
    audit = library_models.audit
    assert audit.audit_passed is True
    assert audit.exact_signature_collisions == []
    assert audit.duplicate_titles == []
    assert audit.duplicate_questions == []
    assert audit.high_similarity_pairs == []
    assert audit.high_similarity_threshold == HIGH_SIMILARITY_THRESHOLD
    assert audit.maximum_pairwise_similarity == pytest.approx(0.646154)
    assert 240 * 239 // 2 == 28_680
    assert len(library_models.closest_pairs) == 20
    assert all(value == 240 for value in audit.completeness_checks.values())


def test_scenario_library_exact_build_matches_committed_tree(rebuilt_library: Path) -> None:
    expected = sorted(
        path.relative_to(COMMITTED) for path in COMMITTED.rglob("*") if path.is_file()
    )
    actual = sorted(
        path.relative_to(rebuilt_library) for path in rebuilt_library.rglob("*") if path.is_file()
    )
    assert expected == actual
    assert len(actual) == EXPECTED_TOTAL_FILES == 282
    for relative in expected:
        assert (COMMITTED / relative).read_bytes() == (rebuilt_library / relative).read_bytes()


def test_scenario_library_manifest_and_checksums_are_complete(rebuilt_library: Path) -> None:
    manifest = ScenarioLibraryManifest.model_validate_json(
        (rebuilt_library / "artifact-manifest.json").read_bytes()
    )
    assert manifest.artifact_count == len(manifest.artifacts) == EXPECTED_BASE_ARTIFACTS
    for entry in manifest.artifacts:
        path = rebuilt_library / entry.path
        assert path.is_file() and path.stat().st_size == entry.byte_count
        assert sha256_file(path) == entry.content_hash
    checksum_lines = (rebuilt_library / "SHA256SUMS").read_text(encoding="ascii").splitlines()
    assert len(checksum_lines) == EXPECTED_TOTAL_FILES - 1
    checksum_paths = set()
    for line in checksum_lines:
        digest, relative = line.split("  ", 1)
        assert not Path(relative).is_absolute() and ".." not in Path(relative).parts
        assert sha256_file(rebuilt_library / relative) == f"sha256:{digest}"
        checksum_paths.add(relative)
    assert checksum_paths == {
        path.relative_to(rebuilt_library).as_posix()
        for path in rebuilt_library.rglob("*")
        if path.is_file() and path.name != "SHA256SUMS"
    }


def test_scenario_library_coverage_csv_reconciles_with_registry() -> None:
    registry = ScenarioLibraryRegistry.model_validate_json(
        (COMMITTED / "registry.json").read_bytes()
    )
    with (COMMITTED / "coverage.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 240
    assert [int(row["design_order"]) for row in rows] == list(range(1, 241))
    assert [row["design_id"] for row in rows] == [item.design_id for item in registry.designs]
    assert len({row["design_signature"] for row in rows}) == 240
    assert Counter(row["implementation_status"] for row in rows) == {
        "design-only": 228,
        "reference-implemented": 12,
    }
    assert {row["city_bindings"] for row in rows} == {"0"}
    assert {row["method_claimed"] for row in rows} == {"false"}


def test_scenario_library_schemas_and_documents_are_strict() -> None:
    schemas = sorted((COMMITTED / "schemas").glob("*.schema.json"))
    assert len(schemas) == 5
    assert all(
        json.loads(path.read_text(encoding="utf-8"))["additionalProperties"] is False
        for path in schemas
    )
    registry = ScenarioLibraryRegistry.model_validate_json(
        (COMMITTED / "registry.json").read_bytes()
    )
    audit = ScenarioLibraryAudit.model_validate_json((COMMITTED / "audit.json").read_bytes())
    design = ScenarioDesign.model_validate_json(
        (COMMITTED / registry.designs[0].artifact_path).read_bytes()
    )
    assert audit.audit_passed and design.design_id == registry.designs[0].design_id
    assert registry.design_count == 240 and registry.family_count == 30


def test_scenario_library_models_reject_claim_inflation_and_integrity_drift(
    library_models: LibraryModels,
) -> None:
    def clone(payload: object) -> dict[str, object]:
        return json.loads(json.dumps(payload))

    def reject(model: type[object], payload: dict[str, object], message: str) -> None:
        with pytest.raises(ValidationError, match=message):
            model.model_validate(payload)  # type: ignore[attr-defined]

    base = library_models.designs[0].model_dump(mode="json")
    mutations = []
    city_bound = clone(base)
    city_bound["city_bindings"] = ["unverified.city"]
    mutations.append(city_bound)
    method_claim = clone(base)
    method_claim["method_claimed"] = True
    mutations.append(method_claim)
    signature_drift = clone(base)
    signature_drift["design_signature"] = "sha256:" + "0" * 64
    mutations.append(signature_drift)
    missing_boundary = clone(base)
    missing_boundary["prohibited_claims"] = ["one"]
    mutations.append(missing_boundary)
    ref_note_drift = clone(base)
    ref_note_drift["reference_implementation_note"] = "invented reference scope note"
    mutations.append(ref_note_drift)
    for payload in mutations:
        with pytest.raises(ValidationError):
            ScenarioDesign.model_validate(payload)

    duplicate_cases: list[tuple[str, list[object], str]] = [
        ("alternatives", list(base["alternatives"]), "scenario design alternatives must be unique"),
        (
            "analysis_modes",
            list(base["analysis_modes"]),
            "scenario design analysis modes must be unique",
        ),
        (
            "evidence_requirements",
            list(base["evidence_requirements"]),
            "scenario design evidence requirements must be unique",
        ),
        (
            "required_source_roles",
            list(base["required_source_roles"]),
            "scenario design source roles must be unique",
        ),
        (
            "prohibited_claims",
            list(base["prohibited_claims"]),
            "scenario design prohibited claims must be unique",
        ),
        ("tags", list(base["tags"]), "scenario design tags must be unique"),
    ]
    for field, values, message in duplicate_cases:
        payload = clone(base)
        payload[field] = [*values, values[0]]
        reject(ScenarioDesign, payload, message)

    duplicate_objective = clone(base)
    duplicate_objective["objectives"][1]["objective_id"] = duplicate_objective["objectives"][0][
        "objective_id"
    ]
    reject(ScenarioDesign, duplicate_objective, "scenario design objective ids must be unique")

    duplicate_constraint = clone(base)
    duplicate_constraint["constraints"][1]["constraint_id"] = duplicate_constraint["constraints"][
        0
    ]["constraint_id"]
    reject(ScenarioDesign, duplicate_constraint, "scenario design constraint ids must be unique")

    unsorted_tags = clone(base)
    unsorted_tags["tags"] = list(reversed(unsorted_tags["tags"]))
    reject(ScenarioDesign, unsorted_tags, "scenario design tags must be sorted")

    no_primary = clone(base)
    for objective in no_primary["objectives"]:
        objective["primary"] = False
    reject(ScenarioDesign, no_primary, "requires exactly one primary objective")

    no_binding = clone(base)
    for constraint in no_binding["constraints"]:
        constraint["binding"] = False
    reject(ScenarioDesign, no_binding, "requires exactly one binding constraint")

    primary_mismatch = clone(base)
    primary_mismatch["independence_key"]["primary_outcome"] = "a different primary outcome"
    reject(ScenarioDesign, primary_mismatch, "primary objective must match")

    binding_mismatch = clone(base)
    binding_mismatch["independence_key"]["binding_constraint"] = (
        "A different binding constraint remains binding."
    )
    reject(ScenarioDesign, binding_mismatch, "binding constraint must match")

    gate_mismatch = clone(base)
    gate_mismatch["independence_key"]["evidence_gate"] = (
        "A different and sufficiently detailed evidence gate applies."
    )
    reject(ScenarioDesign, gate_mismatch, "release gate must match")

    horizon_mismatch = clone(base)
    horizon_mismatch["independence_key"]["horizon"] = "multi-year"
    reject(ScenarioDesign, horizon_mismatch, "scenario horizon must match")

    spatial_mismatch = clone(base)
    spatial_mismatch["independence_key"]["spatial_unit"] = "facility"
    reject(ScenarioDesign, spatial_mismatch, "scenario spatial unit must match")

    gate_role_undeclared = clone(base)
    gate_role_undeclared["release_gate"]["required_source_roles"].append("housing-market")
    reject(ScenarioDesign, gate_role_undeclared, "release-gate source roles must be declared")

    constraint_role_undeclared = clone(base)
    constraint_role_undeclared["constraints"][1]["required_source_roles"] = ["housing-market"]
    reject(ScenarioDesign, constraint_role_undeclared, "constraint source roles must be declared")

    gate_evidence_undeclared = clone(base)
    gate_evidence_undeclared["release_gate"]["required_evidence_types"].append("causal")
    reject(ScenarioDesign, gate_evidence_undeclared, "release-gate evidence types must be declared")

    causal_base = next(
        item.model_dump(mode="json")
        for item in library_models.designs
        if "causal" in [mode.value for mode in item.analysis_modes]
    )
    causal_without_evidence = clone(causal_base)
    causal_without_evidence["evidence_requirements"].remove("causal")
    causal_without_evidence["release_gate"]["required_evidence_types"].remove("causal")
    reject(ScenarioDesign, causal_without_evidence, "causal design mode requires causal evidence")

    causal_without_identification = clone(causal_base)
    causal_without_identification["release_gate"]["gate_type"] = "model-calibration"
    reject(
        ScenarioDesign,
        causal_without_identification,
        "causal design mode requires an identification gate",
    )

    template_mismatch = clone(base)
    template_mismatch["existing_template_ref"] = "template.unverified.v1"
    reject(ScenarioDesign, template_mismatch, "status and template reference must align")

    readiness_mismatch = clone(base)
    readiness_mismatch["current_readiness"] = "reference-implemented"
    reject(ScenarioDesign, readiness_mismatch, "reference implementation and readiness must align")

    missing_required_tag = clone(base)
    missing_required_tag["tags"].remove(base["suite"])
    reject(ScenarioDesign, missing_required_tag, "scenario design tags lack")

    duplicate_constraint_role = clone(base)
    duplicate_constraint_role["constraints"][0]["required_source_roles"].append(
        duplicate_constraint_role["constraints"][0]["required_source_roles"][0]
    )
    reject(ScenarioDesign, duplicate_constraint_role, "constraint source roles must be unique")

    duplicate_gate_role = clone(base)
    duplicate_gate_role["release_gate"]["required_source_roles"].append(
        duplicate_gate_role["release_gate"]["required_source_roles"][0]
    )
    reject(ScenarioDesign, duplicate_gate_role, "gate source roles must be unique")

    duplicate_gate_evidence = clone(base)
    duplicate_gate_evidence["release_gate"]["required_evidence_types"].append(
        duplicate_gate_evidence["release_gate"]["required_evidence_types"][0]
    )
    reject(ScenarioDesign, duplicate_gate_evidence, "gate evidence types must be unique")

    family_base = library_models.families[0].model_dump(mode="json")
    duplicate_family_refs = clone(family_base)
    duplicate_family_refs["design_refs"][1] = duplicate_family_refs["design_refs"][0]
    reject(ScenarioFamily, duplicate_family_refs, "family design references must be unique")

    incomplete_decision_matrix = clone(family_base)
    incomplete_decision_matrix["decision_types"][-1] = incomplete_decision_matrix["decision_types"][
        0
    ]
    reject(ScenarioFamily, incomplete_decision_matrix, "cover all eight decision types")

    duplicate_family_signatures = clone(family_base)
    duplicate_family_signatures["design_signatures"][1] = duplicate_family_signatures[
        "design_signatures"
    ][0]
    reject(ScenarioFamily, duplicate_family_signatures, "family signatures must be unique")

    duplicate_family_roles = clone(family_base)
    duplicate_family_roles["common_source_roles"].append(
        duplicate_family_roles["common_source_roles"][0]
    )
    reject(ScenarioFamily, duplicate_family_roles, "family source roles must be unique")

    registry_base = ScenarioLibraryRegistry.model_validate_json(
        (COMMITTED / "registry.json").read_bytes()
    ).model_dump(mode="json")

    registry_order = clone(registry_base)
    registry_order["designs"][0], registry_order["designs"][1] = (
        registry_order["designs"][1],
        registry_order["designs"][0],
    )
    reject(ScenarioLibraryRegistry, registry_order, "design order must be contiguous")

    family_order = clone(registry_base)
    family_order["families"][0], family_order["families"][1] = (
        family_order["families"][1],
        family_order["families"][0],
    )
    reject(ScenarioLibraryRegistry, family_order, "family order must be contiguous")

    duplicate_design_ids = clone(registry_base)
    duplicate_design_ids["designs"][1]["design_id"] = duplicate_design_ids["designs"][0][
        "design_id"
    ]
    reject(ScenarioLibraryRegistry, duplicate_design_ids, "design identifiers must be unique")

    duplicate_registry_signatures = clone(registry_base)
    duplicate_registry_signatures["designs"][1]["design_signature"] = duplicate_registry_signatures[
        "designs"
    ][0]["design_signature"]
    reject(
        ScenarioLibraryRegistry,
        duplicate_registry_signatures,
        "substantive signatures must be unique",
    )

    duplicate_family_ids = clone(registry_base)
    duplicate_family_ids["families"][1]["family_id"] = duplicate_family_ids["families"][0][
        "family_id"
    ]
    reject(ScenarioLibraryRegistry, duplicate_family_ids, "family identifiers must be unique")

    bad_suite_counts = clone(registry_base)
    bad_suite_counts["suite_counts"]["climate-disaster-resilience"] += 1
    reject(ScenarioLibraryRegistry, bad_suite_counts, "suite counts must cover 240 designs")

    incomplete_suite_counts = clone(registry_base)
    removed_count = incomplete_suite_counts["suite_counts"].pop("behavioral-policy-equity")
    incomplete_suite_counts["suite_counts"]["climate-disaster-resilience"] += removed_count
    reject(ScenarioLibraryRegistry, incomplete_suite_counts, "suite counts must cover 240 designs")

    bad_type_counts = clone(registry_base)
    bad_type_counts["decision_type_counts"]["diagnose"] = 29
    reject(ScenarioLibraryRegistry, bad_type_counts, "decision type must appear once")

    incomplete_type_counts = clone(registry_base)
    incomplete_type_counts["decision_type_counts"].pop("evaluate")
    reject(ScenarioLibraryRegistry, incomplete_type_counts, "decision type must appear once")

    bad_implementation_counts = clone(registry_base)
    bad_implementation_counts["implementation_status_counts"]["design-only"] = 227
    reject(ScenarioLibraryRegistry, bad_implementation_counts, "implementation status counts")

    bad_readiness_counts = clone(registry_base)
    bad_readiness_counts["current_readiness_counts"]["blocked-missing-source"] = 198
    reject(ScenarioLibraryRegistry, bad_readiness_counts, "readiness counts must reconcile")

    duplicate_template_refs = clone(registry_base)
    implemented_entries = [
        item for item in duplicate_template_refs["designs"] if item["existing_template_ref"]
    ]
    implemented_entries[1]["existing_template_ref"] = implemented_entries[0][
        "existing_template_ref"
    ]
    reject(ScenarioLibraryRegistry, duplicate_template_refs, "template references must be unique")

    audit_base = library_models.audit.model_dump(mode="json")
    bad_audit_status = clone(audit_base)
    bad_audit_status["audit_passed"] = False
    reject(ScenarioLibraryAudit, bad_audit_status, "audit status does not match")

    bad_audit_suite_count = clone(audit_base)
    bad_audit_suite_count["suite_counts"]["climate-disaster-resilience"] += 1
    reject(ScenarioLibraryAudit, bad_audit_suite_count, "audit suite counts do not reconcile")

    bad_audit_family_count = clone(audit_base)
    bad_audit_family_count["family_counts"]["climate-disaster-resilience"] += 1
    reject(ScenarioLibraryAudit, bad_audit_family_count, "audit suite counts do not reconcile")

    bad_audit_matrix = clone(audit_base)
    bad_audit_matrix["decision_type_counts"]["diagnose"] = 29
    reject(ScenarioLibraryAudit, bad_audit_matrix, "lacks the 30-by-8 design matrix")

    manifest_base = ScenarioLibraryManifest.model_validate_json(
        (COMMITTED / "artifact-manifest.json").read_bytes()
    ).model_dump(mode="json")
    bad_manifest_count = clone(manifest_base)
    bad_manifest_count["artifact_count"] += 1
    reject(ScenarioLibraryManifest, bad_manifest_count, "artifact count must match entries")

    unsorted_manifest = clone(manifest_base)
    unsorted_manifest["artifacts"][0], unsorted_manifest["artifacts"][1] = (
        unsorted_manifest["artifacts"][1],
        unsorted_manifest["artifacts"][0],
    )
    reject(ScenarioLibraryManifest, unsorted_manifest, "artifact paths must be sorted and unique")

    duplicate_manifest_path = clone(manifest_base)
    duplicate_manifest_path["artifacts"][1]["path"] = duplicate_manifest_path["artifacts"][0][
        "path"
    ]
    reject(
        ScenarioLibraryManifest,
        duplicate_manifest_path,
        "artifact paths must be sorted and unique",
    )

    for unsafe_path in ("/absolute.json", "../escape.json", "nested\\windows.json"):
        unsafe_manifest = clone(manifest_base)
        unsafe_manifest["artifacts"][0]["path"] = unsafe_path
        reject(ScenarioLibraryManifest, unsafe_manifest, "safe relative POSIX paths")


def test_scenario_library_builder_rejects_stale_and_symlink_outputs(tmp_path: Path) -> None:
    stale_output = tmp_path / "stale"
    stale_output.mkdir()
    (stale_output / "unexpected.txt").write_text("not allowlisted", encoding="utf-8")
    with pytest.raises(IntegrityError, match="unexpected files"):
        build_scenario_library(ROOT, stale_output)
    target = tmp_path / "target"
    target.mkdir()
    symlink = tmp_path / "linked-output"
    symlink.symlink_to(target, target_is_directory=True)
    with pytest.raises(IntegrityError, match="cannot be a symlink"):
        build_scenario_library(ROOT, symlink)


def test_cli_builds_the_exact_scenario_library(tmp_path: Path) -> None:
    output = tmp_path / "scenario-library"
    result = runner.invoke(
        app,
        [
            "catalog",
            "build-scenario-library",
            "--root",
            str(ROOT),
            "--output",
            str(output),
        ],
    )
    assert result.exit_code == 0
    assert "282 scenario-library files" in result.output
    assert "240 designs and 30 families" in result.output
    assert {
        path.relative_to(output): path.read_bytes() for path in output.rglob("*") if path.is_file()
    } == {
        path.relative_to(COMMITTED): path.read_bytes()
        for path in COMMITTED.rglob("*")
        if path.is_file()
    }
