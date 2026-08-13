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

import civicdecision.release as release_contract
from civicdecision.errors import IntegrityError
from civicdecision.product.build import ProductArtifactManifest, build_product_artifacts
from civicdecision.protocols.base import sha256_file
from civicdecision.release import (
    ReleaseValidationError,
    extract_validated_sdist,
    sha256_path,
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
) -> None:
    output = tmp_path / "product"
    output.mkdir()
    (output / "stale.txt").write_text("untracked", encoding="utf-8")
    with pytest.raises(IntegrityError, match="unexpected files"):
        build_product_artifacts(ROOT, output)

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
    checksums.write_text("0" + original_checksums[1:], encoding="ascii")
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
