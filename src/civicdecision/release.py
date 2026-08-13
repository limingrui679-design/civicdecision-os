"""Fail-closed validation primitives for CivicDecision release archives."""

from __future__ import annotations

import base64
import csv
import hashlib
import io
import stat
import tarfile
import zipfile
from collections.abc import Iterable
from email.parser import BytesParser
from email.policy import default
from pathlib import Path, PurePosixPath
from typing import Any, cast


class ReleaseValidationError(ValueError):
    """Raised when a release artifact does not satisfy its closed contract."""


MAX_ARCHIVE_MEMBERS = 5_000
MAX_ARCHIVE_UNCOMPRESSED_BYTES = 128 * 1024 * 1024
MAX_ARCHIVE_MEMBER_BYTES = 32 * 1024 * 1024

_FORBIDDEN_PARTS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "dist",
}
_FORBIDDEN_SUFFIXES = {".pyc", ".pyo"}


def sha256_path(path: Path) -> str:
    """Return a lowercase, unprefixed SHA-256 digest for a regular file."""

    if not path.is_file() or path.is_symlink():
        raise ReleaseValidationError(f"checksum target is not a regular file: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_member_name(name: str) -> PurePosixPath:
    if not name or "\\" in name or "\x00" in name:
        raise ReleaseValidationError(f"archive member is not a safe POSIX path: {name!r}")
    path = PurePosixPath(name)
    if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise ReleaseValidationError(f"archive member is not a safe relative path: {name!r}")
    if any(part in _FORBIDDEN_PARTS for part in path.parts):
        raise ReleaseValidationError(f"archive contains forbidden path component: {name}")
    if path.suffix.lower() in _FORBIDDEN_SUFFIXES:
        raise ReleaseValidationError(f"archive contains forbidden bytecode: {name}")
    return path


def _check_member_budget(sizes: Iterable[int]) -> tuple[int, int]:
    values = list(sizes)
    if len(values) > MAX_ARCHIVE_MEMBERS:
        raise ReleaseValidationError(
            f"archive has {len(values):,} members; limit is {MAX_ARCHIVE_MEMBERS:,}"
        )
    if any(size < 0 or size > MAX_ARCHIVE_MEMBER_BYTES for size in values):
        raise ReleaseValidationError("archive contains a negative or oversized member")
    total = sum(values)
    if total > MAX_ARCHIVE_UNCOMPRESSED_BYTES:
        raise ReleaseValidationError(
            f"archive expands to {total:,} bytes; limit is {MAX_ARCHIVE_UNCOMPRESSED_BYTES:,}"
        )
    return len(values), total


def _metadata_values(payload: bytes) -> dict[str, Any]:
    message = BytesParser(policy=default).parsebytes(payload)
    return {
        "metadata_version": message["Metadata-Version"],
        "name": message["Name"],
        "version": message["Version"],
        "requires_python": message["Requires-Python"],
        "license_expression": message["License-Expression"],
        "license_files": message.get_all("License-File", []),
    }


def _assert_metadata(metadata: dict[str, Any], *, name: str, version: str) -> None:
    expected = {
        "metadata_version": "2.4",
        "name": name,
        "version": version,
        "requires_python": ">=3.11",
        "license_expression": "MIT",
    }
    for key, expected_value in expected.items():
        if metadata.get(key) != expected_value:
            raise ReleaseValidationError(
                f"release metadata {key} is {metadata.get(key)!r}, expected {expected_value!r}"
            )
    if metadata.get("license_files") != ["LICENSE"]:
        raise ReleaseValidationError("release metadata must name exactly the top-level LICENSE")


def _wheel_record_digest(payload: bytes) -> str:
    encoded = base64.urlsafe_b64encode(hashlib.sha256(payload).digest()).rstrip(b"=")
    return f"sha256={encoded.decode('ascii')}"


def validate_wheel(
    wheel_path: Path,
    *,
    distribution: str = "civicdecision",
    version: str,
) -> dict[str, Any]:
    """Validate a wheel's paths, metadata, required assets, and every RECORD entry."""

    expected_dist_info = f"{distribution}-{version}.dist-info"
    required = {
        f"{distribution}/__init__.py",
        f"{distribution}/cli.py",
        f"{distribution}/py.typed",
        f"{distribution}/web/index.html",
        f"{distribution}/web/favicon.svg",
        f"{distribution}/web/assets/app.css",
        f"{distribution}/web/assets/app.js",
        f"{expected_dist_info}/METADATA",
        f"{expected_dist_info}/WHEEL",
        f"{expected_dist_info}/entry_points.txt",
        f"{expected_dist_info}/licenses/LICENSE",
        f"{expected_dist_info}/RECORD",
    }
    with zipfile.ZipFile(wheel_path) as archive:
        members = archive.infolist()
        _check_member_budget(member.file_size for member in members)
        names: set[str] = set()
        payloads: dict[str, bytes] = {}
        for member in members:
            path = _safe_member_name(member.filename)
            normalized = path.as_posix()
            if normalized in names:
                raise ReleaseValidationError(f"wheel contains a duplicate member: {normalized}")
            names.add(normalized)
            if member.flag_bits & 0x1:
                raise ReleaseValidationError(f"wheel contains an encrypted member: {normalized}")
            mode = member.external_attr >> 16
            if stat.S_ISLNK(mode):
                raise ReleaseValidationError(f"wheel contains a symbolic link: {normalized}")
            if not member.is_dir():
                payloads[normalized] = archive.read(member)

    missing = sorted(required - names)
    if missing:
        raise ReleaseValidationError(f"wheel is missing required members: {missing}")
    top_level = {PurePosixPath(name).parts[0] for name in names}
    if top_level != {distribution, expected_dist_info}:
        raise ReleaseValidationError(f"wheel has unexpected top-level members: {sorted(top_level)}")

    metadata = _metadata_values(payloads[f"{expected_dist_info}/METADATA"])
    _assert_metadata(metadata, name=distribution, version=version)
    entry_points = payloads[f"{expected_dist_info}/entry_points.txt"].decode("utf-8")
    if "civicdecision = civicdecision.cli:app" not in entry_points.splitlines():
        raise ReleaseValidationError("wheel console entry point is missing or incorrect")

    record_name = f"{expected_dist_info}/RECORD"
    record_rows = list(csv.reader(io.StringIO(payloads[record_name].decode("utf-8"))))
    if any(len(row) != 3 for row in record_rows):
        raise ReleaseValidationError("wheel RECORD must contain exactly three columns per row")
    recorded: dict[str, tuple[str, str]] = {}
    for row in record_rows:
        record_path = _safe_member_name(row[0]).as_posix()
        if record_path in recorded:
            raise ReleaseValidationError(f"wheel RECORD duplicates {record_path}")
        recorded[record_path] = (row[1], row[2])
    if set(recorded) != set(payloads):
        raise ReleaseValidationError("wheel RECORD paths do not exactly cover wheel files")
    for name, payload in payloads.items():
        digest, size = recorded[name]
        if name == record_name:
            if digest or size:
                raise ReleaseValidationError("wheel RECORD must leave its own hash and size empty")
            continue
        if digest != _wheel_record_digest(payload) or size != str(len(payload)):
            raise ReleaseValidationError(f"wheel RECORD digest or size mismatch: {name}")

    python_files = sum(name.endswith(".py") for name in names)
    return {
        "archive": wheel_path.name,
        "sha256": sha256_path(wheel_path),
        "member_count": len(members),
        "uncompressed_bytes": sum(member.file_size for member in members),
        "python_files": python_files,
        "record_entries": len(record_rows),
        "record_complete": True,
        "metadata": metadata,
        "required_assets_present": len(required),
        "safe_paths": True,
        "links": 0,
    }


def _validate_sdist_members(
    archive: tarfile.TarFile,
    *,
    expected_root: str,
) -> tuple[list[tarfile.TarInfo], set[str]]:
    members = archive.getmembers()
    _check_member_budget(member.size for member in members)
    names: set[str] = set()
    for member in members:
        normalized = _safe_member_name(member.name).as_posix().rstrip("/")
        if normalized in names:
            raise ReleaseValidationError(f"sdist contains a duplicate member: {normalized}")
        names.add(normalized)
        if PurePosixPath(normalized).parts[0] != expected_root:
            raise ReleaseValidationError("sdist members must share one exact top-level directory")
        if member.issym() or member.islnk() or member.isdev() or member.isfifo():
            raise ReleaseValidationError(f"sdist contains a link or special file: {normalized}")
        if not member.isfile() and not member.isdir():
            raise ReleaseValidationError(f"sdist contains an unsupported member type: {normalized}")
    return members, names


def validate_sdist(
    sdist_path: Path,
    *,
    distribution: str = "civicdecision",
    version: str,
) -> dict[str, Any]:
    """Validate a source archive's closed inventory, paths, metadata, and release inputs."""

    root = f"{distribution}-{version}"
    required_relative = {
        ".github/workflows/ci.yml",
        ".github/workflows/codeql.yml",
        ".github/workflows/release-candidate.yml",
        ".github/workflows/security.yml",
        ".secrets.baseline",
        "CHANGELOG.md",
        "CONTRIBUTING.md",
        "LICENSE",
        "Makefile",
        "PKG-INFO",
        "README.md",
        "SECURITY.md",
        "catalog/product/artifact-manifest.json",
        "catalog/product/SHA256SUMS",
        "catalog/scenario-library/artifact-manifest.json",
        "catalog/scenario-library/SHA256SUMS",
        "docs/RELEASE_PROCESS.md",
        "docs/CLAIM_AUDIT.md",
        "docs/PERFORMANCE.md",
        "docs/RELEASE_NOTES_0.8.0.md",
        "docs/SECURITY_ASSURANCE.md",
        "examples/outputs/suffolk-heat-access/SHA256SUMS",
        "governance/CLAIM_BOUNDARIES.md",
        "governance/CLAIM_AUDIT_POLICY.json",
        "pyproject.toml",
        "requirements/runtime-api.lock",
        "scripts/audit_claims.py",
        "scripts/build_release_candidate.py",
        "scripts/release_smoke.py",
        "scripts/verify_repository.py",
        "src/civicdecision/__init__.py",
        "src/civicdecision/claim_audit.py",
        "src/civicdecision/release.py",
        "tests/test_product_build.py",
        "verification/milestone-7-scenario-library-and-product.json",
        "verification/milestone-8-claim-audit.json",
        "verification/milestone-8-coverage.json",
        "verification/milestone-8-performance.json",
        "verification/milestone-8-public-state.json",
        "verification/milestone-8-quality.json",
        "verification/milestone-8-repository.json",
    }
    required = {f"{root}/{relative}" for relative in required_relative}
    with tarfile.open(sdist_path, mode="r:gz") as archive:
        members, names = _validate_sdist_members(archive, expected_root=root)
        missing = sorted(required - names)
        if missing:
            raise ReleaseValidationError(f"sdist is missing required members: {missing}")
        package_info_member = archive.getmember(f"{root}/PKG-INFO")
        package_info_handle = archive.extractfile(package_info_member)
        if package_info_handle is None:
            raise ReleaseValidationError("sdist PKG-INFO is not a regular readable file")
        metadata = _metadata_values(package_info_handle.read())
    _assert_metadata(metadata, name=distribution, version=version)
    files = sum(member.isfile() for member in members)
    directories = sum(member.isdir() for member in members)
    return {
        "archive": sdist_path.name,
        "sha256": sha256_path(sdist_path),
        "member_count": len(members),
        "file_count": files,
        "directory_count": directories,
        "uncompressed_bytes": sum(member.size for member in members),
        "metadata": metadata,
        "required_release_inputs_present": len(required_relative),
        "safe_paths": True,
        "links_or_special_files": 0,
        "top_level_directory": root,
    }


def extract_validated_sdist(
    sdist_path: Path,
    destination: Path,
    *,
    distribution: str = "civicdecision",
    version: str,
) -> Path:
    """Validate and then manually extract regular sdist members without path traversal."""

    validate_sdist(sdist_path, distribution=distribution, version=version)
    if destination.exists() and any(destination.iterdir()):
        raise ReleaseValidationError(f"extraction destination is not empty: {destination}")
    destination.mkdir(parents=True, exist_ok=True)
    root = f"{distribution}-{version}"
    with tarfile.open(sdist_path, mode="r:gz") as archive:
        members, _ = _validate_sdist_members(archive, expected_root=root)
        for member in members:
            relative = _safe_member_name(member.name)
            target = destination.joinpath(*relative.parts)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                target.chmod(0o755)
                continue
            source = archive.extractfile(member)
            if source is None:
                raise ReleaseValidationError(f"sdist member cannot be read: {member.name}")
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("wb") as handle:
                while chunk := source.read(1024 * 1024):
                    handle.write(chunk)
            target.chmod(0o755 if member.mode & 0o111 else 0o644)
    return destination / root


def write_deterministic_zip(
    source_directory: Path,
    output_path: Path,
    *,
    epoch: int,
) -> dict[str, Any]:
    """Write a byte-reproducible ZIP with normalized ordering, timestamps, and permissions."""

    import datetime as dt

    if not source_directory.is_dir() or source_directory.is_symlink():
        raise ReleaseValidationError(f"ZIP source is not a regular directory: {source_directory}")
    timestamp = dt.datetime.fromtimestamp(max(epoch, 315532800), tz=dt.UTC)
    date_time = (
        timestamp.year,
        timestamp.month,
        timestamp.day,
        timestamp.hour,
        timestamp.minute,
        0,
    )
    files = sorted(path for path in source_directory.rglob("*") if path.is_file())
    if any(path.is_symlink() for path in files):
        raise ReleaseValidationError("ZIP source contains a symbolic link")
    _check_member_budget(path.stat().st_size for path in files)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        raise ReleaseValidationError(f"refusing to overwrite ZIP: {output_path}")
    with zipfile.ZipFile(
        output_path,
        mode="x",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
        strict_timestamps=True,
    ) as archive:
        for path in files:
            relative = path.relative_to(source_directory.parent).as_posix()
            _safe_member_name(relative)
            info = zipfile.ZipInfo(relative, date_time=date_time)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            info.flag_bits |= 0x800
            archive.writestr(
                info,
                path.read_bytes(),
                compress_type=zipfile.ZIP_DEFLATED,
                compresslevel=9,
            )
    return {
        "archive": output_path.name,
        "sha256": sha256_path(output_path),
        "file_count": len(files),
        "normalized_timestamp": timestamp.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "normalized_permissions": "0644",
        "safe_paths": True,
    }


def write_checksum_inventory(paths: Iterable[Path], output_path: Path) -> int:
    """Write a sorted portable two-space SHA256SUMS inventory."""

    paths_list = sorted(paths, key=lambda item: item.name)
    names = [path.name for path in paths_list]
    if len(names) != len(set(names)):
        raise ReleaseValidationError("checksum inventory requires unique basenames")
    lines = [f"{sha256_path(path)}  {path.name}" for path in paths_list]
    output_path.write_text("\n".join(lines) + "\n", encoding="ascii")
    return len(lines)


def verify_checksum_inventory(directory: Path, checksum_path: Path) -> dict[str, Any]:
    """Verify every portable checksum line and reject omissions or extra targets."""

    seen: set[str] = set()
    for line in checksum_path.read_text(encoding="ascii").splitlines():
        try:
            digest, name = line.split("  ", 1)
        except ValueError as exc:
            raise ReleaseValidationError(f"invalid checksum line: {line!r}") from exc
        relative = _safe_member_name(name)
        if len(relative.parts) != 1:
            raise ReleaseValidationError("release checksum targets must use basenames")
        if name in seen:
            raise ReleaseValidationError(f"duplicate checksum target: {name}")
        seen.add(name)
        path = directory / name
        if len(digest) != 64 or digest != sha256_path(path):
            raise ReleaseValidationError(f"release checksum mismatch: {name}")
    expected = {
        path.name for path in directory.iterdir() if path.is_file() and path != checksum_path
    }
    if seen != expected:
        raise ReleaseValidationError(
            f"release checksum inventory differs: unlisted={sorted(expected - seen)}, "
            f"missing={sorted(seen - expected)}"
        )
    return {"entry_count": len(seen), "complete": True, "portable_paths": True}


def validate_dependency_audit(
    dependency_audit: object,
    *,
    installed_versions: dict[str, str],
    expected_count: int,
) -> tuple[list[dict[str, Any]], int]:
    """Reconcile a pip-audit report with the installed hash-locked runtime."""

    if not isinstance(dependency_audit, dict):
        raise ReleaseValidationError("dependency audit report must be an object")
    raw_dependencies = dependency_audit.get("dependencies")
    if not isinstance(raw_dependencies, list):
        raise ReleaseValidationError("dependency audit dependencies must be a list")
    if not all(isinstance(item, dict) for item in raw_dependencies):
        raise ReleaseValidationError("dependency audit contains a malformed dependency record")
    dependencies = cast(list[dict[str, Any]], raw_dependencies)
    audited_versions = {
        str(item.get("name", "")).casefold().replace("_", "-"): str(item.get("version", ""))
        for item in dependencies
    }
    if (
        len(dependencies) != len(audited_versions)
        or len(audited_versions) != expected_count
        or not all(name and version for name, version in audited_versions.items())
    ):
        raise ReleaseValidationError(
            "dependency audit inventory is incomplete, duplicated, or malformed"
        )
    if not all(isinstance(item.get("vulns"), list) for item in dependencies):
        raise ReleaseValidationError("dependency audit omitted vulnerability results")
    if audited_versions != installed_versions:
        raise ReleaseValidationError(
            "dependency audit inventory differs from the hash-locked installed runtime"
        )
    vulnerabilities = sum(len(cast(list[object], item["vulns"])) for item in dependencies)
    if vulnerabilities:
        raise ReleaseValidationError("dependency audit found known vulnerabilities")
    return dependencies, vulnerabilities
