from __future__ import annotations

import io
import json
import shutil
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

import pytest

import civicdecision.claim_audit as claim_contract
import civicdecision.release as release_contract
from civicdecision.claim_audit import ClaimAuditError, audit_claims
from civicdecision.errors import IntegrityError
from civicdecision.product.build import ProductArtifactManifest, build_product_artifacts
from civicdecision.protocols.base import sha256_file
from civicdecision.release import (
    ReleaseValidationError,
    extract_validated_sdist,
    sha256_path,
    validate_dependency_audit,
    validate_sdist,
    validate_wheel,
    verify_checksum_inventory,
    write_checksum_inventory,
    write_deterministic_zip,
)

ROOT = Path(__file__).parents[1]


@pytest.fixture(scope="module")
def rebuilt_product(tmp_path_factory: pytest.TempPathFactory) -> Path:
    output = tmp_path_factory.mktemp("product-artifacts") / "product"
    build_product_artifacts(ROOT, output)
    return output


def test_product_build_exactly_matches_committed_projection(rebuilt_product: Path) -> None:
    committed = ROOT / "catalog/product"
    expected = sorted(
        path.relative_to(committed) for path in committed.rglob("*") if path.is_file()
    )
    actual = sorted(
        path.relative_to(rebuilt_product) for path in rebuilt_product.rglob("*") if path.is_file()
    )
    assert expected == actual
    assert len(actual) == 338
    for relative in expected:
        assert (committed / relative).read_bytes() == (rebuilt_product / relative).read_bytes()


def test_product_manifest_covers_every_projected_artifact(rebuilt_product: Path) -> None:
    manifest = ProductArtifactManifest.model_validate_json(
        (rebuilt_product / "artifact-manifest.json").read_bytes()
    )
    assert manifest.artifact_count == 336
    assert len(manifest.artifacts) == 336
    assert manifest.catalog_fingerprint.startswith("sha256:")
    for entry in manifest.artifacts:
        path = rebuilt_product / entry.path
        assert path.stat().st_size == entry.byte_count
        assert sha256_file(path) == entry.content_hash


def test_product_checksum_inventory_is_relative_complete_and_valid(rebuilt_product: Path) -> None:
    lines = (rebuilt_product / "SHA256SUMS").read_text(encoding="ascii").splitlines()
    assert len(lines) == 337
    observed = set()
    for line in lines:
        digest, relative = line.split("  ", 1)
        assert not relative.startswith("/") and ".." not in Path(relative).parts
        assert sha256_file(rebuilt_product / relative) == f"sha256:{digest}"
        observed.add(relative)
    assert observed == {
        path.relative_to(rebuilt_product).as_posix()
        for path in rebuilt_product.rglob("*")
        if path.is_file() and path.name != "SHA256SUMS"
    }


def test_product_collections_publish_exact_record_counts(rebuilt_product: Path) -> None:
    expected = {
        "cities/highest-available.json": 258,
        "cities/tier-g.json": 250,
        "cities/tier-s.json": 30,
        "cities/tier-d.json": 8,
        "scenarios/all.json": 188,
        "scenarios/standard-screen.json": 90,
        "scenarios/deep-pack.json": 96,
        "scenarios/reference-pack.json": 2,
        "scenarios/decision-pack.json": 98,
        "sources/index.json": 90,
        "suites/index.json": 7,
        "designs/index.json": 240,
        "designs/reference-implemented.json": 12,
        "designs/design-only.json": 228,
        "designs/suite/climate-disaster-resilience.json": 40,
        "designs/decision-type/evaluate.json": 30,
        "design-families/index.json": 30,
    }
    for relative, count in expected.items():
        document = json.loads((rebuilt_product / relative).read_text(encoding="utf-8"))
        assert document["record_count"] == len(document["items"]) == count
        assert document["claim_boundary"]
    design_details = sorted((rebuilt_product / "designs/detail").glob("*.json"))
    family_details = sorted((rebuilt_product / "design-families/detail").glob("*.json"))
    assert len(design_details) == 240
    assert len(family_details) == 30
    assert all(
        json.loads(path.read_text())["design"]["city_bindings"] == [] for path in design_details
    )
    evidence = json.loads((rebuilt_product / "evidence/scenario-library-summary.json").read_text())
    assert (evidence["design_count"], evidence["family_count"]) == (240, 30)
    assert evidence["city_bound_executions_counted"] == evidence["methods_claimed"] == 0


def test_product_schemas_and_openapi_are_substantive(rebuilt_product: Path) -> None:
    schemas = sorted((rebuilt_product / "schemas").glob("*.schema.json"))
    openapi = json.loads((rebuilt_product / "openapi-v1.json").read_text(encoding="utf-8"))
    web = json.loads((rebuilt_product / "web-assets.json").read_text(encoding="utf-8"))
    assert len(schemas) == 28
    assert all(
        "$defs" in json.loads(path.read_text(encoding="utf-8"))
        or "properties" in json.loads(path.read_text(encoding="utf-8"))
        for path in schemas
    )
    assert len(openapi["paths"]) == 19
    assert len(web["assets"]) == web["asset_count"] == 4
    assert all(item["content_hash"].startswith("sha256:") for item in web["assets"])


def test_product_builder_allows_exact_regeneration_in_place(rebuilt_product: Path) -> None:
    before = {
        path.relative_to(rebuilt_product): path.read_bytes()
        for path in rebuilt_product.rglob("*")
        if path.is_file()
    }
    result = build_product_artifacts(ROOT, rebuilt_product)
    after = {
        path.relative_to(rebuilt_product): path.read_bytes()
        for path in rebuilt_product.rglob("*")
        if path.is_file()
    }
    assert before == after
    assert len(result.artifact_paths) == 338


def test_product_builder_rejects_stale_files_and_release_archives_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "product"
    output.mkdir()
    (output / "stale.txt").write_text("untracked", encoding="utf-8")
    with pytest.raises(IntegrityError, match="unexpected files"):
        build_product_artifacts(ROOT, output)

    installed_runtime = {"alpha": "1.0", "beta-core": "2.0"}
    clean_audit = {
        "dependencies": [
            {"name": "alpha", "version": "1.0", "vulns": []},
            {"name": "beta_core", "version": "2.0", "vulns": []},
        ]
    }
    assert validate_dependency_audit(
        clean_audit, installed_versions=installed_runtime, expected_count=2
    ) == (clean_audit["dependencies"], 0)
    audit_failures = (
        ([], "report must be an object"),
        ({}, "dependencies must be a list"),
        ({"dependencies": ["invalid", {}]}, "malformed dependency record"),
        (
            {
                "dependencies": [
                    {"name": "alpha", "version": "1.0", "vulns": []},
                    {"name": "alpha", "version": "1.0", "vulns": []},
                ]
            },
            "incomplete, duplicated, or malformed",
        ),
        (
            {"dependencies": [{"name": "alpha", "version": "1.0"}]},
            "omitted vulnerability results",
        ),
        (
            {"dependencies": [{"name": "alpha", "version": "1.1", "vulns": []}]},
            "differs from the hash-locked installed runtime",
        ),
        (
            {"dependencies": [{"name": "alpha", "version": "1.0", "vulns": [{"id": "CVE-test"}]}]},
            "found known vulnerabilities",
        ),
    )
    for audit_report, message in audit_failures:
        expected_versions = {"alpha": "1.0"}
        with pytest.raises(ReleaseValidationError, match=message):
            validate_dependency_audit(
                audit_report,
                installed_versions=expected_versions,
                expected_count=1 if audit_report else 0,
            )

    release_dist = tmp_path / "release-dist"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "hatchling",
            "build",
            "--target",
            "wheel",
            "--target",
            "sdist",
            "--directory",
            str(release_dist),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=180,
    )
    wheel = next(release_dist.glob("*.whl"))
    sdist = next(release_dist.glob("*.tar.gz"))
    wheel_report = validate_wheel(wheel, version="0.8.0")
    sdist_report = validate_sdist(sdist, version="0.8.0")
    assert wheel_report["record_complete"] is True
    assert wheel_report["safe_paths"] is True
    assert sdist_report["safe_paths"] is True
    assert sdist_report["links_or_special_files"] == 0

    extracted = extract_validated_sdist(
        sdist,
        tmp_path / "extracted",
        version="0.8.0",
    )
    assert extracted.name == "civicdecision-0.8.0"
    assert not (extracted / ".git").exists()
    first_zip = tmp_path / "source-one.zip"
    second_zip = tmp_path / "source-two.zip"
    first_zip_report = write_deterministic_zip(extracted, first_zip, epoch=1_786_579_200)
    second_zip_report = write_deterministic_zip(extracted, second_zip, epoch=1_786_579_200)
    assert first_zip.read_bytes() == second_zip.read_bytes()
    assert first_zip_report["sha256"] == second_zip_report["sha256"]

    inventory = tmp_path / "inventory"
    inventory.mkdir()
    inventory_wheel = inventory / wheel.name
    inventory_zip = inventory / first_zip.name
    shutil.copyfile(wheel, inventory_wheel)
    shutil.copyfile(first_zip, inventory_zip)
    checksums = inventory / "SHA256SUMS"
    assert write_checksum_inventory([inventory_wheel, inventory_zip], checksums) == 2
    assert verify_checksum_inventory(inventory, checksums) == {
        "entry_count": 2,
        "complete": True,
        "portable_paths": True,
    }

    unsafe_wheel = tmp_path / "unsafe.whl"
    shutil.copyfile(wheel, unsafe_wheel)
    with zipfile.ZipFile(unsafe_wheel, mode="a") as archive:
        archive.writestr("../escape", b"unsafe")
    with pytest.raises(ReleaseValidationError, match="safe relative path"):
        validate_wheel(unsafe_wheel, version="0.8.0")

    unsafe_sdist = tmp_path / "unsafe.tar.gz"
    with tarfile.open(unsafe_sdist, mode="w:gz") as archive:
        member = tarfile.TarInfo("civicdecision-0.8.0/../escape")
        member.size = 1
        archive.addfile(member, io.BytesIO(b"x"))
    with pytest.raises(ReleaseValidationError, match="safe relative path"):
        validate_sdist(unsafe_sdist, version="0.8.0")

    original_checksums = checksums.read_text(encoding="ascii")
    replacement = "1" if original_checksums[0] == "0" else "0"
    checksums.write_text(replacement + original_checksums[1:], encoding="ascii")
    with pytest.raises(ReleaseValidationError, match="checksum mismatch"):
        verify_checksum_inventory(inventory, checksums)
    with pytest.raises(ReleaseValidationError, match="regular file"):
        sha256_path(inventory)
    with pytest.raises(ReleaseValidationError, match="overwrite ZIP"):
        write_deterministic_zip(extracted, first_zip, epoch=1_786_579_200)
    nonempty = tmp_path / "nonempty-extraction"
    nonempty.mkdir()
    (nonempty / "keep.txt").write_text("keep", encoding="utf-8")
    with pytest.raises(ReleaseValidationError, match="not empty"):
        extract_validated_sdist(sdist, nonempty, version="0.8.0")

    for unsafe_name in ("", "unsafe\\path", "unsafe\x00path"):
        with pytest.raises(ReleaseValidationError, match="safe POSIX path"):
            release_contract._safe_member_name(unsafe_name)
    for unsafe_name in ("/absolute", "root/../escape"):
        with pytest.raises(ReleaseValidationError, match="safe relative path"):
            release_contract._safe_member_name(unsafe_name)
    with pytest.raises(ReleaseValidationError, match="forbidden path component"):
        release_contract._safe_member_name("root/.git/config")
    with pytest.raises(ReleaseValidationError, match="forbidden bytecode"):
        release_contract._safe_member_name("root/module.pyc")
    with pytest.raises(ReleaseValidationError, match="5,001 members"):
        release_contract._check_member_budget([0] * 5_001)
    with pytest.raises(ReleaseValidationError, match="negative or oversized"):
        release_contract._check_member_budget([-1])
    with pytest.raises(ReleaseValidationError, match="negative or oversized"):
        release_contract._check_member_budget([release_contract.MAX_ARCHIVE_MEMBER_BYTES + 1])
    with pytest.raises(ReleaseValidationError, match="expands to"):
        release_contract._check_member_budget([release_contract.MAX_ARCHIVE_MEMBER_BYTES] * 5)
    with pytest.raises(ReleaseValidationError, match="metadata_version"):
        release_contract._assert_metadata(
            {
                "metadata_version": "2.3",
                "name": "civicdecision",
                "version": "0.8.0",
                "requires_python": ">=3.11",
                "license_expression": "MIT",
                "license_files": ["LICENSE"],
            },
            name="civicdecision",
            version="0.8.0",
        )
    with pytest.raises(ReleaseValidationError, match="exactly the top-level LICENSE"):
        release_contract._assert_metadata(
            {
                "metadata_version": "2.4",
                "name": "civicdecision",
                "version": "0.8.0",
                "requires_python": ">=3.11",
                "license_expression": "MIT",
                "license_files": [],
            },
            name="civicdecision",
            version="0.8.0",
        )

    missing_wheel = tmp_path / "missing.whl"
    with zipfile.ZipFile(missing_wheel, mode="w") as archive:
        archive.writestr("civicdecision/placeholder.txt", b"placeholder")
    with pytest.raises(ReleaseValidationError, match="missing required members"):
        validate_wheel(missing_wheel, version="0.8.0")

    symlink_wheel = tmp_path / "symlink.whl"
    shutil.copyfile(wheel, symlink_wheel)
    link = zipfile.ZipInfo("civicdecision/release-link")
    link.create_system = 3
    link.external_attr = (0o120777 << 16) | 0xA0000000
    with zipfile.ZipFile(symlink_wheel, mode="a") as archive:
        archive.writestr(link, b"target")
    with pytest.raises(ReleaseValidationError, match="symbolic link"):
        validate_wheel(symlink_wheel, version="0.8.0")

    extra_root_wheel = tmp_path / "extra-root.whl"
    shutil.copyfile(wheel, extra_root_wheel)
    with zipfile.ZipFile(extra_root_wheel, mode="a") as archive:
        archive.writestr("unexpected/file.txt", b"unexpected")
    with pytest.raises(ReleaseValidationError, match="unexpected top-level"):
        validate_wheel(extra_root_wheel, version="0.8.0")

    def write_small_sdist(
        path: Path,
        entries: list[tuple[str, bytes | None, bytes | None]],
    ) -> None:
        with tarfile.open(path, mode="w:gz") as archive:
            for name, payload, member_type in entries:
                member = tarfile.TarInfo(name)
                if member_type is not None:
                    member.type = member_type
                    member.linkname = "target"
                if payload is not None:
                    member.size = len(payload)
                    archive.addfile(member, io.BytesIO(payload))
                else:
                    archive.addfile(member)

    wrong_root = tmp_path / "wrong-root.tar.gz"
    write_small_sdist(wrong_root, [("other/file.txt", b"x", None)])
    with pytest.raises(ReleaseValidationError, match="one exact top-level"):
        validate_sdist(wrong_root, version="0.8.0")
    linked_sdist = tmp_path / "linked.tar.gz"
    write_small_sdist(
        linked_sdist,
        [("civicdecision-0.8.0/link", None, tarfile.SYMTYPE)],
    )
    with pytest.raises(ReleaseValidationError, match="link or special file"):
        validate_sdist(linked_sdist, version="0.8.0")
    incomplete_sdist = tmp_path / "incomplete.tar.gz"
    write_small_sdist(
        incomplete_sdist,
        [("civicdecision-0.8.0/placeholder.txt", b"x", None)],
    )
    with pytest.raises(ReleaseValidationError, match="missing required members"):
        validate_sdist(incomplete_sdist, version="0.8.0")

    with pytest.raises(ReleaseValidationError, match="regular directory"):
        write_deterministic_zip(inventory_wheel, tmp_path / "not-a-directory.zip", epoch=0)
    symlink_source = tmp_path / "symlink-source"
    symlink_source.mkdir()
    (symlink_source / "target.txt").write_text("target", encoding="utf-8")
    (symlink_source / "link.txt").symlink_to(symlink_source / "target.txt")
    with pytest.raises(ReleaseValidationError, match="symbolic link"):
        write_deterministic_zip(symlink_source, tmp_path / "symlink-source.zip", epoch=0)

    duplicate_left = tmp_path / "duplicate-left"
    duplicate_right = tmp_path / "duplicate-right"
    duplicate_left.mkdir()
    duplicate_right.mkdir()
    (duplicate_left / "same.txt").write_text("left", encoding="utf-8")
    (duplicate_right / "same.txt").write_text("right", encoding="utf-8")
    with pytest.raises(ReleaseValidationError, match="unique basenames"):
        write_checksum_inventory(
            [duplicate_left / "same.txt", duplicate_right / "same.txt"],
            tmp_path / "duplicate-SHA256SUMS",
        )

    checksums.write_text("invalid-line\n", encoding="ascii")
    with pytest.raises(ReleaseValidationError, match="invalid checksum line"):
        verify_checksum_inventory(inventory, checksums)
    checksums.write_text(f"{'0' * 64}  nested/file.txt\n", encoding="ascii")
    with pytest.raises(ReleaseValidationError, match="use basenames"):
        verify_checksum_inventory(inventory, checksums)
    digest = sha256_path(inventory_wheel)
    checksums.write_text(
        f"{digest}  {inventory_wheel.name}\n{digest}  {inventory_wheel.name}\n",
        encoding="ascii",
    )
    with pytest.raises(ReleaseValidationError, match="duplicate checksum target"):
        verify_checksum_inventory(inventory, checksums)
    checksums.write_text(f"{digest}  {inventory_wheel.name}\n", encoding="ascii")
    with pytest.raises(ReleaseValidationError, match="inventory differs"):
        verify_checksum_inventory(inventory, checksums)

    with zipfile.ZipFile(wheel) as archive:
        original_wheel_payloads = {
            info.filename: archive.read(info) for info in archive.infolist() if not info.is_dir()
        }

    def rewrite_wheel(
        output_path: Path,
        *,
        transform: object,
    ) -> None:
        with zipfile.ZipFile(output_path, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, payload in original_wheel_payloads.items():
                candidate_name, candidate_payload = transform(name, payload)  # type: ignore[operator]
                if candidate_name is not None:
                    archive.writestr(candidate_name, candidate_payload)

    missing_entry_point = tmp_path / "missing-entry-point.whl"
    rewrite_wheel(
        missing_entry_point,
        transform=lambda name, payload: (
            (name, b"[console_scripts]\n")
            if name.endswith("/entry_points.txt")
            else (name, payload)
        ),
    )
    with pytest.raises(ReleaseValidationError, match="console entry point"):
        validate_wheel(missing_entry_point, version="0.8.0")

    malformed_record = tmp_path / "malformed-record.whl"
    rewrite_wheel(
        malformed_record,
        transform=lambda name, payload: (
            (name, b"only-one-column\n") if name.endswith("/RECORD") else (name, payload)
        ),
    )
    with pytest.raises(ReleaseValidationError, match="three columns"):
        validate_wheel(malformed_record, version="0.8.0")

    incomplete_record = tmp_path / "incomplete-record.whl"
    rewrite_wheel(
        incomplete_record,
        transform=lambda name, payload: (
            (name, b"civicdecision/__init__.py,,\n")
            if name.endswith("/RECORD")
            else (name, payload)
        ),
    )
    with pytest.raises(ReleaseValidationError, match="exactly cover"):
        validate_wheel(incomplete_record, version="0.8.0")

    self_hashed_record = tmp_path / "self-hashed-record.whl"
    rewrite_wheel(
        self_hashed_record,
        transform=lambda name, payload: (
            (
                name,
                payload.replace(
                    b"civicdecision-0.8.0.dist-info/RECORD,,\n",
                    b"civicdecision-0.8.0.dist-info/RECORD,sha256=invalid,1\n",
                ),
            )
            if name.endswith("/RECORD")
            else (name, payload)
        ),
    )
    with pytest.raises(ReleaseValidationError, match="leave its own hash"):
        validate_wheel(self_hashed_record, version="0.8.0")

    digest_mismatch_wheel = tmp_path / "digest-mismatch.whl"
    rewrite_wheel(
        digest_mismatch_wheel,
        transform=lambda name, payload: (
            (name, payload + b"tamper") if name == "civicdecision/__init__.py" else (name, payload)
        ),
    )
    with pytest.raises(ReleaseValidationError, match="digest or size mismatch"):
        validate_wheel(digest_mismatch_wheel, version="0.8.0")

    duplicate_wheel = tmp_path / "duplicate.whl"
    shutil.copyfile(wheel, duplicate_wheel)
    with (
        pytest.warns(UserWarning, match="Duplicate name"),
        zipfile.ZipFile(duplicate_wheel, mode="a") as archive,
    ):
        archive.writestr("civicdecision/__init__.py", b"duplicate")
    with pytest.raises(ReleaseValidationError, match="duplicate member"):
        validate_wheel(duplicate_wheel, version="0.8.0")

    encrypted_wheel = tmp_path / "encrypted.whl"
    with zipfile.ZipFile(wheel) as original, zipfile.ZipFile(encrypted_wheel, mode="w") as archive:
        for info in original.infolist():
            clone = zipfile.ZipInfo(info.filename, info.date_time)
            clone.flag_bits = info.flag_bits | (
                0x1 if info.filename == "civicdecision/__init__.py" else 0
            )
            clone.external_attr = info.external_attr
            archive.writestr(clone, original.read(info))

    # Python's zip writer clears the encryption bit, so exercise the decoded member contract
    # with a minimal in-memory archive facade.
    class EncryptedInfo:
        filename = "civicdecision/__init__.py"
        file_size = 1
        flag_bits = 0x1
        external_attr = 0

        @staticmethod
        def is_dir() -> bool:
            return False

    class EncryptedArchive:
        @staticmethod
        def __enter__() -> EncryptedArchive:
            return EncryptedArchive()

        @staticmethod
        def __exit__(*args: object) -> None:
            return None

        @staticmethod
        def infolist() -> list[EncryptedInfo]:
            return [EncryptedInfo()]

        @staticmethod
        def read(member: object) -> bytes:
            return b"x"

    original_zipfile = release_contract.zipfile.ZipFile
    release_contract.zipfile.ZipFile = lambda *args, **kwargs: EncryptedArchive()  # type: ignore[assignment]
    try:
        with pytest.raises(ReleaseValidationError, match="encrypted member"):
            validate_wheel(encrypted_wheel, version="0.8.0")
    finally:
        release_contract.zipfile.ZipFile = original_zipfile

    duplicate_sdist = tmp_path / "duplicate-sdist.tar.gz"
    write_small_sdist(
        duplicate_sdist,
        [
            ("civicdecision-0.8.0/same.txt", b"a", None),
            ("civicdecision-0.8.0/same.txt", b"b", None),
        ],
    )
    with pytest.raises(ReleaseValidationError, match="duplicate member"):
        validate_sdist(duplicate_sdist, version="0.8.0")

    audit_root = tmp_path / "claim-audit"
    (audit_root / "governance").mkdir(parents=True)
    (audit_root / "verification").mkdir()
    (audit_root / "doc.md").write_text("Count 3. Local-only boundary.\n", encoding="utf-8")
    (audit_root / "evidence.json").write_text('{"value": 3}\n', encoding="utf-8")
    (audit_root / "pyproject.toml").write_text(
        '[project]\nname = "claim-audit-fixture"\n', encoding="utf-8"
    )
    public_state = {
        "schema_version": "1.0.0",
        "checked_at": "2026-08-13T00:00:00Z",
        "github_repository": "example/missing",
        "github_repository_api": "https://api.github.com/repos/example/missing",
        "github_repository_http_status": 404,
        "local_git_remotes": [],
        "package_project_urls": [],
        "public_hosted_demo_url": None,
    }
    (audit_root / "verification/public-state.json").write_text(
        json.dumps(public_state) + "\n", encoding="utf-8"
    )
    policy = {
        "schema_version": "1.0.0",
        "scan_patterns": ["doc.md", "pyproject.toml"],
        "forbidden_literals": [{"id": "false-claim", "literal": "FALSE CLAIM"}],
        "required_boundaries": [
            {
                "id": "local-boundary",
                "path": "doc.md",
                "contains": "Local-only boundary.",
            }
        ],
        "public_state_contract": {
            "github_repository": "example/missing",
            "github_repository_http_status": 404,
            "local_git_remotes": [],
            "package_project_urls": [],
            "public_hosted_demo_url": None,
        },
        "quantitative_claims": [
            {
                "id": "fixture-count",
                "expected": 3,
                "sources": [{"path": "evidence.json", "pointer": "/value"}],
                "renderings": [{"path": "doc.md", "template": "Count {value}."}],
            }
        ],
        "public_state_snapshot": "verification/public-state.json",
    }
    policy_path = audit_root / "governance/CLAIM_AUDIT_POLICY.json"
    policy_path.write_text(json.dumps(policy) + "\n", encoding="utf-8")

    passing_audit = audit_claims(audit_root)
    assert passing_audit["status"] == "passed"
    assert passing_audit["checks"] == {"total": 13, "passed": 13, "failed": 0}
    assert passing_audit["quantitative_values"] == {"fixture-count": 3}
    assert passing_audit["public_state"]["local_git_remotes"] is None
    assert passing_audit["audit_completed_at"] is None
    assert set(passing_audit["governed_surface_sha256"]) == {"doc.md", "pyproject.toml"}
    assert (
        audit_claims(
            audit_root,
            policy_path=Path("governance/CLAIM_AUDIT_POLICY.json"),
        )["status"]
        == "passed"
    )

    (audit_root / "doc.md").write_text(
        "Count 3. Local-only boundary. FALSE CLAIM\n", encoding="utf-8"
    )
    failed_literal_audit = audit_claims(audit_root)
    assert failed_literal_audit["status"] == "failed"
    assert failed_literal_audit["failures"][0]["category"] == "forbidden-literal"

    (audit_root / "doc.md").write_text("Count 3. Local-only boundary.\n", encoding="utf-8")
    invalid_template = json.loads(json.dumps(policy))
    invalid_template["quantitative_claims"][0]["renderings"][0]["template"] = "Count 3."
    policy_path.write_text(json.dumps(invalid_template) + "\n", encoding="utf-8")
    with pytest.raises(ClaimAuditError, match="must interpolate value"):
        audit_claims(audit_root)

    invalid_operation = json.loads(json.dumps(policy))
    invalid_operation["quantitative_claims"][0]["operation"] = "invented"
    policy_path.write_text(json.dumps(invalid_operation) + "\n", encoding="utf-8")
    with pytest.raises(ClaimAuditError, match="unknown operation"):
        audit_claims(audit_root)

    unsafe_source = json.loads(json.dumps(policy))
    unsafe_source["quantitative_claims"][0]["sources"][0]["path"] = "../escape.json"
    policy_path.write_text(json.dumps(unsafe_source) + "\n", encoding="utf-8")
    with pytest.raises(ClaimAuditError, match="safe and relative"):
        audit_claims(audit_root)

    policy_path.write_text(json.dumps(policy) + "\n", encoding="utf-8")
    real_fetch_http_status = claim_contract._fetch_http_status
    monkeypatch.setattr(claim_contract, "_fetch_http_status", lambda *args, **kwargs: 404)
    refreshed_audit = audit_claims(audit_root, refresh_public_state=True)
    assert refreshed_audit["status"] == "passed"
    assert refreshed_audit["checks"] == {"total": 14, "passed": 14, "failed": 0}
    assert refreshed_audit["public_state"]["refreshed_http_status"] == 404
    assert refreshed_audit["audit_completed_at"].endswith("Z")

    monkeypatch.setattr(claim_contract, "_fetch_http_status", lambda *args, **kwargs: 200)
    changed_public_state = audit_claims(audit_root, refresh_public_state=True)
    assert changed_public_state["status"] == "failed"
    assert changed_public_state["failures"][0]["check"] == "live-public-repository-state"
    monkeypatch.setattr(claim_contract, "_fetch_http_status", real_fetch_http_status)

    missing_json = audit_root / "missing.json"
    with pytest.raises(ClaimAuditError, match="cannot load JSON object"):
        claim_contract._load_object(missing_json)
    array_json = audit_root / "array.json"
    array_json.write_text("[]\n", encoding="utf-8")
    with pytest.raises(ClaimAuditError, match="must be an object"):
        claim_contract._load_object(array_json)
    malformed_json = audit_root / "malformed.json"
    malformed_json.write_text("{\n", encoding="utf-8")
    with pytest.raises(ClaimAuditError, match="cannot load JSON object"):
        claim_contract._load_object(malformed_json)
    nonfinite_json = audit_root / "nonfinite.json"
    nonfinite_json.write_text('{"value": NaN}\n', encoding="utf-8")
    with pytest.raises(ClaimAuditError, match="non-finite number"):
        claim_contract._load_object(nonfinite_json)

    outside = tmp_path / "outside.json"
    outside.write_text("{}\n", encoding="utf-8")
    escape_link = audit_root / "escape-link.json"
    escape_link.symlink_to(outside)
    with pytest.raises(ClaimAuditError, match="escapes repository root"):
        claim_contract._safe_relative(audit_root, "escape-link.json")

    pointer_document = {"a/b": {"~key": [3]}}
    assert claim_contract._resolve_pointer(pointer_document, "") == pointer_document
    assert claim_contract._resolve_pointer(pointer_document, "/a~1b/~0key/0") == 3
    for pointer, message in (
        ("not-a-pointer", "must be empty or start"),
        ("/missing", "component is absent"),
        ("/a~1b/~0key/not-an-index", "list index is invalid"),
        ("/a~1b/~0key/-1", "list index is invalid"),
        ("/a~1b/~0key/01", "list index is invalid"),
        ("/a~1b/~0key/1", "list index is invalid"),
        ("/a~2b", "invalid escape"),
        ("/a~1b/~0key/0/child", "traverses a scalar"),
    ):
        with pytest.raises(ClaimAuditError, match=message):
            claim_contract._resolve_pointer(pointer_document, pointer)

    with pytest.raises(ClaimAuditError, match="non-scalar"):
        claim_contract._scalar([], claim_id="fixture")
    with pytest.raises(ClaimAuditError, match="numeric evidence"):
        claim_contract._number(True, claim_id="fixture")
    with pytest.raises(ClaimAuditError, match="finite numeric evidence"):
        claim_contract._number(float("inf"), claim_id="fixture")

    compound_evidence = audit_root / "compound-evidence.json"
    compound_evidence.write_text(
        json.dumps({"first": 5, "second": 2, "items": [1, 2, 3], "float": 3.5, "negative": -1})
        + "\n",
        encoding="utf-8",
    )

    def source(pointer: str) -> dict[str, str]:
        return {"path": "compound-evidence.json", "pointer": pointer}

    assert (
        claim_contract._evaluate_claim(
            audit_root,
            {"id": "sum", "operation": "sum", "sources": [source("/first"), source("/second")]},
        )[0]
        == 7
    )
    assert (
        claim_contract._evaluate_claim(
            audit_root,
            {"id": "count", "operation": "count", "sources": [source("/items")]},
        )[0]
        == 3
    )
    assert (
        claim_contract._evaluate_claim(
            audit_root,
            {
                "id": "subtract",
                "operation": "subtract",
                "sources": [source("/first"), source("/second")],
            },
        )[0]
        == 3
    )
    assert (
        claim_contract._evaluate_claim(
            audit_root,
            {"id": "choose", "operation": "choose-two", "sources": [source("/first")]},
        )[0]
        == 10
    )
    for candidate, message in (
        ({"id": "none", "sources": []}, "must declare sources"),
        ({"id": "bad-source", "sources": [1]}, "malformed source"),
        (
            {"id": "single", "sources": [source("/first"), source("/second")]},
            "exactly one source",
        ),
        (
            {"id": "count", "operation": "count", "sources": [source("/first")]},
            "one list or object",
        ),
        (
            {"id": "subtract", "operation": "subtract", "sources": [source("/first")]},
            "requires two sources",
        ),
        (
            {"id": "choose", "operation": "choose-two", "sources": [source("/float")]},
            "requires one non-negative integer",
        ),
        (
            {"id": "choose", "operation": "choose-two", "sources": [source("/negative")]},
            "requires one non-negative integer",
        ),
        (
            {"id": "nonscalar", "sources": [source("/items")]},
            "non-scalar",
        ),
    ):
        with pytest.raises(ClaimAuditError, match=message):
            claim_contract._evaluate_claim(audit_root, candidate)

    invalid_utf8 = audit_root / "invalid-utf8.md"
    invalid_utf8.write_bytes(b"\xff")
    with pytest.raises(ClaimAuditError, match="cannot read claim surface"):
        claim_contract._read_text(invalid_utf8)
    scan_link = audit_root / "linked-doc.md"
    scan_link.symlink_to(audit_root / "doc.md")
    assert len(claim_contract._scanned_files(audit_root, ["*.md"])) == 2

    class GitHubResponse:
        def __init__(self, status: int) -> None:
            self.status = status

        def __enter__(self) -> GitHubResponse:
            return self

        def __exit__(self, *args: object) -> None:
            return None

    class GitHubConnection:
        response_status = 204

        def __init__(self, host: str, *, timeout: float) -> None:
            assert host == "api.github.com"
            assert timeout == 1
            self.closed = False
            self.request_arguments: tuple[str, str, dict[str, str]] | None = None
            github_connections.append(self)

        def request(self, method: str, path: str, *, headers: dict[str, str]) -> None:
            self.request_arguments = (method, path, headers)

        def getresponse(self) -> GitHubResponse:
            return GitHubResponse(self.response_status)

        def close(self) -> None:
            self.closed = True

    github_connections: list[GitHubConnection] = []

    with monkeypatch.context() as scoped_patch:
        scoped_patch.setattr(
            claim_contract.http.client,
            "HTTPSConnection",
            GitHubConnection,
        )
        assert (
            claim_contract._fetch_http_status(
                "https://api.github.com/repos/example/missing", timeout_seconds=1
            )
            == 204
        )
        assert github_connections[-1].request_arguments == (
            "GET",
            "/repos/example/missing",
            {
                "Accept": "application/vnd.github+json",
                "User-Agent": "CivicDecision-claim-audit",
            },
        )
        assert github_connections[-1].closed is True

        GitHubConnection.response_status = 404
        assert (
            claim_contract._fetch_http_status(
                "https://api.github.com/repos/example/missing", timeout_seconds=1
            )
            == 404
        )
        assert github_connections[-1].closed is True

    for unsafe_url in (
        "http://api.github.com/repos/example/missing",
        "https://example.invalid/repos/example/missing",
        "https://api.github.com/repos/example/missing?redirect=1",
        "https://api.github.com/users/example",
    ):
        with pytest.raises(ClaimAuditError, match="exact GitHub API repository URL"):
            claim_contract._fetch_http_status(unsafe_url, timeout_seconds=1)

    git_marker = audit_root / ".git"
    git_marker.mkdir()
    failed_git = subprocess.CompletedProcess(
        args=["git", "remote", "-v"], returncode=1, stdout="", stderr="not a repository"
    )
    with monkeypatch.context() as scoped_patch:
        scoped_patch.setattr(claim_contract.subprocess, "run", lambda *args, **kwargs: failed_git)
        with pytest.raises(ClaimAuditError, match="git remote inspection failed"):
            claim_contract._git_remotes(audit_root)
    with monkeypatch.context() as scoped_patch:
        scoped_patch.setattr(
            claim_contract.subprocess,
            "run",
            lambda *args, **kwargs: (_ for _ in ()).throw(subprocess.TimeoutExpired("git", 30)),
        )
        with pytest.raises(ClaimAuditError, match="git remote inspection failed"):
            claim_contract._git_remotes(audit_root)
    successful_git = subprocess.CompletedProcess(
        args=["git", "remote", "-v"],
        returncode=0,
        stdout=(
            "upstream\thttps://example.com/upstream.git (fetch)\n"
            "origin\thttps://example.com/repo.git (fetch)\n"
        ),
        stderr="",
    )
    with monkeypatch.context() as scoped_patch:
        scoped_patch.setattr(
            claim_contract.subprocess, "run", lambda *args, **kwargs: successful_git
        )
        assert claim_contract._git_remotes(audit_root) == [
            "origin\thttps://example.com/repo.git (fetch)",
            "upstream\thttps://example.com/upstream.git (fetch)",
        ]
    git_marker.rmdir()

    claim_contract._validate_check_accounting(2, 2, [])
    with pytest.raises(ClaimAuditError, match="internal check accounting drifted"):
        claim_contract._validate_check_accounting(2, 1, [])

    def write_policy(candidate: object) -> None:
        policy_path.write_text(json.dumps(candidate) + "\n", encoding="utf-8")

    malformed_policy_cases: list[tuple[object, str]] = []
    bad_schema = json.loads(json.dumps(policy))
    bad_schema["schema_version"] = "2.0.0"
    malformed_policy_cases.append((bad_schema, "schema_version"))
    bad_patterns = json.loads(json.dumps(policy))
    bad_patterns["scan_patterns"] = "doc.md"
    malformed_policy_cases.append((bad_patterns, "scan_patterns"))
    unsafe_pattern = json.loads(json.dumps(policy))
    unsafe_pattern["scan_patterns"] = ["../*.md"]
    malformed_policy_cases.append((unsafe_pattern, "scan pattern must be safe and relative"))
    bad_public_contract = json.loads(json.dumps(policy))
    bad_public_contract["public_state_contract"] = {}
    malformed_policy_cases.append((bad_public_contract, "public_state_contract"))
    empty_patterns = json.loads(json.dumps(policy))
    empty_patterns["scan_patterns"] = ["absent/**/*.md"]
    malformed_policy_cases.append((empty_patterns, "resolved no files"))
    bad_forbidden_list = json.loads(json.dumps(policy))
    bad_forbidden_list["forbidden_literals"] = "bad"
    malformed_policy_cases.append((bad_forbidden_list, "forbidden_literals"))
    bad_forbidden_rule = json.loads(json.dumps(policy))
    bad_forbidden_rule["forbidden_literals"] = ["bad"]
    malformed_policy_cases.append((bad_forbidden_rule, "must be an object"))
    bad_rule_id = json.loads(json.dumps(policy))
    bad_rule_id["forbidden_literals"][0]["id"] = "Bad_ID"
    malformed_policy_cases.append((bad_rule_id, "id must use lowercase"))
    duplicate_rule_id = json.loads(json.dumps(policy))
    duplicate_rule_id["required_boundaries"][0]["id"] = "false-claim"
    malformed_policy_cases.append((duplicate_rule_id, "duplicate claim-audit check id"))
    empty_forbidden_rule = json.loads(json.dumps(policy))
    empty_forbidden_rule["forbidden_literals"] = [{"id": "empty", "literal": ""}]
    malformed_policy_cases.append((empty_forbidden_rule, "is empty"))
    bad_boundaries = json.loads(json.dumps(policy))
    bad_boundaries["required_boundaries"] = "bad"
    malformed_policy_cases.append((bad_boundaries, "required_boundaries"))
    bad_boundary_rule = json.loads(json.dumps(policy))
    bad_boundary_rule["required_boundaries"] = ["bad"]
    malformed_policy_cases.append((bad_boundary_rule, "boundary rule must be an object"))
    empty_boundary = json.loads(json.dumps(policy))
    empty_boundary["required_boundaries"][0]["contains"] = ""
    malformed_policy_cases.append((empty_boundary, "required boundary .* is empty"))
    bad_claims = json.loads(json.dumps(policy))
    bad_claims["quantitative_claims"] = "bad"
    malformed_policy_cases.append((bad_claims, "quantitative_claims"))
    bad_claim_rule = json.loads(json.dumps(policy))
    bad_claim_rule["quantitative_claims"] = ["bad"]
    malformed_policy_cases.append((bad_claim_rule, "claim must be an object"))
    bad_renderings = json.loads(json.dumps(policy))
    bad_renderings["quantitative_claims"][0]["renderings"] = "bad"
    malformed_policy_cases.append((bad_renderings, "renderings must be a list"))
    empty_renderings = json.loads(json.dumps(policy))
    empty_renderings["quantitative_claims"][0]["renderings"] = []
    malformed_policy_cases.append((empty_renderings, "renderings must be a non-empty list"))
    bad_rendering_rule = json.loads(json.dumps(policy))
    bad_rendering_rule["quantitative_claims"][0]["renderings"] = [1]
    malformed_policy_cases.append((bad_rendering_rule, "rendering is malformed"))
    bad_rendering_format = json.loads(json.dumps(policy))
    bad_rendering_format["quantitative_claims"][0]["renderings"][0]["template"] = (
        "Count {value:invalid}."
    )
    malformed_policy_cases.append((bad_rendering_format, "invalid rendering template"))
    for candidate, message in malformed_policy_cases:
        write_policy(candidate)
        with pytest.raises(ClaimAuditError, match=message):
            audit_claims(audit_root)

    outside_policy = tmp_path / "outside-policy.json"
    outside_policy.write_text(json.dumps(policy) + "\n", encoding="utf-8")
    with pytest.raises(ClaimAuditError, match="policy must be inside"):
        audit_claims(audit_root, policy_path=outside_policy)

    missing_boundary = json.loads(json.dumps(policy))
    missing_boundary["required_boundaries"][0]["contains"] = "missing boundary"
    write_policy(missing_boundary)
    assert audit_claims(audit_root)["failures"][0]["category"] == "required-boundary"

    wrong_value = json.loads(json.dumps(policy))
    wrong_value["quantitative_claims"][0]["expected"] = 4
    write_policy(wrong_value)
    assert audit_claims(audit_root)["failures"][0]["category"] == "evidence-value"
    wrong_value_type = json.loads(json.dumps(policy))
    wrong_value_type["quantitative_claims"][0]["expected"] = 3.0
    write_policy(wrong_value_type)
    assert audit_claims(audit_root)["failures"][0]["category"] == "evidence-value"

    missing_rendering = json.loads(json.dumps(policy))
    missing_rendering["quantitative_claims"][0]["renderings"][0]["template"] = "Absent {value}."
    write_policy(missing_rendering)
    assert audit_claims(audit_root)["failures"][0]["category"] == "claim-rendering"

    invalid_public_state = dict(public_state)
    invalid_public_state["schema_version"] = "2.0.0"
    (audit_root / "verification/public-state.json").write_text(
        json.dumps(invalid_public_state) + "\n", encoding="utf-8"
    )
    write_policy(policy)
    assert audit_claims(audit_root)["failures"][0]["check"] == "public-state-schema"
    (audit_root / "verification/public-state.json").write_text(
        json.dumps(public_state) + "\n", encoding="utf-8"
    )

    for invalid_timestamp in ("2026-08-13", "not-a-dateZ"):
        bad_timestamp_state = dict(public_state)
        bad_timestamp_state["checked_at"] = invalid_timestamp
        (audit_root / "verification/public-state.json").write_text(
            json.dumps(bad_timestamp_state) + "\n", encoding="utf-8"
        )
        with pytest.raises(ClaimAuditError, match="RFC 3339 UTC timestamp"):
            audit_claims(audit_root)
    (audit_root / "verification/public-state.json").write_text(
        json.dumps(public_state) + "\n", encoding="utf-8"
    )

    mismatched_public_state = dict(public_state)
    mismatched_public_state["github_repository_http_status"] = 200
    (audit_root / "verification/public-state.json").write_text(
        json.dumps(mismatched_public_state) + "\n", encoding="utf-8"
    )
    assert audit_claims(audit_root)["failures"][0]["check"].startswith("public-state-contract:")
    (audit_root / "verification/public-state.json").write_text(
        json.dumps(public_state) + "\n", encoding="utf-8"
    )

    mismatched_endpoint = dict(public_state)
    mismatched_endpoint["github_repository_api"] = "https://api.github.com/repos/example/other"
    (audit_root / "verification/public-state.json").write_text(
        json.dumps(mismatched_endpoint) + "\n", encoding="utf-8"
    )
    assert (
        audit_claims(audit_root)["failures"][0]["check"]
        == "public-state-contract:github_repository_api"
    )
    fetched_urls: list[str] = []
    with monkeypatch.context() as scoped_patch:
        scoped_patch.setattr(
            claim_contract,
            "_fetch_http_status",
            lambda url, **kwargs: fetched_urls.append(url) or 404,
        )
        assert audit_claims(audit_root, refresh_public_state=True)["status"] == "failed"
    assert fetched_urls == ["https://api.github.com/repos/example/missing"]
    (audit_root / "verification/public-state.json").write_text(
        json.dumps(public_state) + "\n", encoding="utf-8"
    )

    missing_contract_field = json.loads(json.dumps(policy))
    missing_contract_field["public_state_contract"].pop("package_project_urls")
    invalid_repository_contract = json.loads(json.dumps(policy))
    invalid_repository_contract["public_state_contract"]["github_repository"] = "not-a-repository"
    for invalid_contract, message in (
        (missing_contract_field, "missing required fields"),
        (invalid_repository_contract, "must be owner/repository"),
    ):
        write_policy(invalid_contract)
        with pytest.raises(ClaimAuditError, match=message):
            audit_claims(audit_root)
    write_policy(policy)

    for invalid_status in (True, 99, 600):
        bad_status_state = dict(public_state)
        bad_status_state["github_repository_http_status"] = invalid_status
        (audit_root / "verification/public-state.json").write_text(
            json.dumps(bad_status_state) + "\n", encoding="utf-8"
        )
        with pytest.raises(ClaimAuditError, match="HTTP status must be an integer"):
            audit_claims(audit_root)
    (audit_root / "verification/public-state.json").write_text(
        json.dumps(public_state) + "\n", encoding="utf-8"
    )

    (audit_root / "pyproject.toml").write_text(
        '[project]\nname = "claim-audit-fixture"\n[project.urls]\nRepository = "https://example.com"\n',
        encoding="utf-8",
    )
    assert audit_claims(audit_root)["failures"][0]["check"] == "package-project-urls"
    published_urls = {"Repository": "https://example.com"}
    published_state = dict(public_state)
    published_state["package_project_urls"] = published_urls
    published_policy = json.loads(json.dumps(policy))
    published_policy["public_state_contract"]["package_project_urls"] = published_urls
    (audit_root / "verification/public-state.json").write_text(
        json.dumps(published_state) + "\n", encoding="utf-8"
    )
    write_policy(published_policy)
    assert audit_claims(audit_root)["status"] == "passed"

    (audit_root / "pyproject.toml").write_text(
        '[project]\nname = "claim-audit-fixture"\nurls = ["not-a-mapping"]\n',
        encoding="utf-8",
    )
    with pytest.raises(ClaimAuditError, match="package project URLs must be a string mapping"):
        audit_claims(audit_root)

    malformed_url_state = dict(public_state)
    malformed_url_state["package_project_urls"] = ["not-a-mapping"]
    (audit_root / "verification/public-state.json").write_text(
        json.dumps(malformed_url_state) + "\n", encoding="utf-8"
    )
    (audit_root / "pyproject.toml").write_text(
        '[project]\nname = "claim-audit-fixture"\n', encoding="utf-8"
    )
    write_policy(policy)
    with pytest.raises(ClaimAuditError, match="public-state package project URLs"):
        audit_claims(audit_root)

    (audit_root / "verification/public-state.json").write_text(
        json.dumps(public_state) + "\n", encoding="utf-8"
    )
    (audit_root / "pyproject.toml").write_text(
        '[project]\nname = "claim-audit-fixture"\n', encoding="utf-8"
    )

    with monkeypatch.context() as scoped_patch:
        scoped_patch.setattr(
            claim_contract,
            "_git_remotes",
            lambda root: ["origin\thttps://example.com/repo.git (fetch)"],
        )
        assert audit_claims(audit_root)["failures"][0]["check"] == "local-git-remotes"

    with monkeypatch.context() as scoped_patch:
        scoped_patch.setattr(
            claim_contract,
            "_fetch_http_status",
            lambda *args, **kwargs: (_ for _ in ()).throw(OSError("offline")),
        )
        failed_refresh = audit_claims(audit_root, refresh_public_state=True)
        assert failed_refresh["failures"][0]["check"] == "live-public-repository-state"

    write_policy(policy)
