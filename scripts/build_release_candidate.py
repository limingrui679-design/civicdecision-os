#!/usr/bin/env python3
"""Build and independently verify a fail-closed CivicDecision release candidate."""

from __future__ import annotations

import argparse
import datetime as dt
import importlib.metadata
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

from civicdecision import __version__
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

ROOT = Path(__file__).resolve().parents[1]
DISTRIBUTION = "civicdecision"
RELEASE_TOOL_DISTRIBUTIONS = {
    "bandit": "bandit",
    "build": "build",
    "check-wheel-contents": "check-wheel-contents",
    "cyclonedx-bom": "cyclonedx-bom",
    "detect-secrets": "detect-secrets",  # pragma: allowlist secret
    "hatchling": "hatchling",
    "pip-audit": "pip-audit",
    "pip-licenses": "pip-licenses",
    "pip-tools": "pip-tools",
    "twine": "twine",
}


class ReleaseBuildError(RuntimeError):
    """A release gate failed before publication."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ReleaseBuildError(message)


def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _tool(name: str) -> Path:
    beside_python = Path(sys.executable).parent / name
    if beside_python.is_file():
        return beside_python
    discovered = shutil.which(name)
    if discovered:
        return Path(discovered).resolve()
    raise ReleaseBuildError(f"required release tool is unavailable: {name}")


def _clean_environment(epoch: int) -> dict[str, str]:
    environment = os.environ.copy()
    environment.pop("PYTHONHOME", None)
    environment.pop("PYTHONPATH", None)
    environment.update(
        {
            "LC_ALL": "C",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONHASHSEED": "0",
            "PYTHONNOUSERSITE": "1",
            "SOURCE_DATE_EPOCH": str(epoch),
            "TZ": "UTC",
        }
    )
    return environment


def _run(
    label: str,
    command: list[str | Path],
    *,
    cwd: Path,
    environment: dict[str, str],
    log: list[dict[str, Any]],
    timeout: int = 1_800,
    output_path: Path | None = None,
) -> str:
    rendered = [str(item) for item in command]
    result = subprocess.run(
        rendered,
        cwd=cwd,
        env=environment,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    combined = result.stdout + result.stderr
    if output_path is not None:
        output_path.write_text(combined, encoding="utf-8")
    log.append(
        {
            "label": label,
            "return_code": result.returncode,
            "status": "passed" if result.returncode == 0 else "failed",
        }
    )
    if result.returncode != 0:
        tail = "\n".join(combined.splitlines()[-30:])
        raise ReleaseBuildError(f"{label} failed with exit {result.returncode}:\n{tail}")
    return combined


def _git_identity(environment: dict[str, str], *, allow_dirty: bool) -> dict[str, Any]:
    status = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=True,
    ).stdout.splitlines()
    if status and not allow_dirty:
        raise ReleaseBuildError(
            "release builds require a clean Git tree; commit or intentionally pass --allow-dirty"
        )
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=True,
    ).stdout.strip()
    branch = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=True,
    ).stdout.strip()
    return {
        "branch": branch,
        "commit": commit,
        "dirty": bool(status),
        "dirty_entry_count": len(status),
    }


def _default_epoch() -> int:
    result = subprocess.run(
        ["git", "show", "-s", "--format=%ct", "HEAD"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    return int(result.stdout.strip())


def _locate_builds(directory: Path) -> tuple[Path, Path]:
    wheels = sorted(directory.glob(f"{DISTRIBUTION}-{__version__}-*.whl"))
    sdists = sorted(directory.glob(f"{DISTRIBUTION}-{__version__}.tar.gz"))
    require(len(wheels) == len(sdists) == 1, "build output must contain one wheel and one sdist")
    return wheels[0], sdists[0]


def _build_twice(
    temporary: Path,
    *,
    environment: dict[str, str],
    command_log: list[dict[str, Any]],
) -> tuple[Path, Path, dict[str, Any]]:
    outputs: list[tuple[Path, Path]] = []
    for iteration in (1, 2):
        output = temporary / f"build-{iteration}"
        output.mkdir()
        _run(
            f"deterministic distribution build {iteration}",
            [
                sys.executable,
                "-m",
                "build",
                "--no-isolation",
                "--wheel",
                "--sdist",
                "-o",
                output,
                ROOT,
            ],
            cwd=ROOT,
            environment=environment,
            log=command_log,
            timeout=1_800,
            output_path=temporary / f"build-{iteration}.log",
        )
        outputs.append(_locate_builds(output))
    first_wheel, first_sdist = outputs[0]
    second_wheel, second_sdist = outputs[1]
    require(first_wheel.read_bytes() == second_wheel.read_bytes(), "repeated wheel builds differ")
    require(first_sdist.read_bytes() == second_sdist.read_bytes(), "repeated sdist builds differ")
    return (
        first_wheel,
        first_sdist,
        {
            "iterations": 2,
            "same_wheel_bytes": True,
            "same_sdist_bytes": True,
            "wheel_sha256": sha256_path(first_wheel),
            "sdist_sha256": sha256_path(first_sdist),
        },
    )


def _verify_source_zip(
    first: Path,
    second: Path,
    *,
    expected_source_root: str,
) -> dict[str, Any]:
    require(first.read_bytes() == second.read_bytes(), "repeated source ZIP builds differ")
    with zipfile.ZipFile(first) as archive:
        members = archive.infolist()
        require(bool(members), "source ZIP is empty")
        require(
            len({item.filename for item in members}) == len(members),
            "source ZIP duplicates paths",
        )
        require(
            all(
                not PurePosixPath(item.filename).is_absolute()
                and ".." not in PurePosixPath(item.filename).parts
                and PurePosixPath(item.filename).parts[0] == expected_source_root
                for item in members
            ),
            "source ZIP has an unsafe path or unexpected root",
        )
        timestamps = {item.date_time for item in members}
        permissions = {item.external_attr >> 16 for item in members}
    return {
        "archive": first.name,
        "file_count": len(members),
        "normalized_permissions": sorted(permissions) == [0o100644],
        "one_normalized_timestamp": len(timestamps) == 1,
        "safe_paths": True,
        "same_bytes_across_two_writes": True,
        "sha256": sha256_path(first),
    }


def _runtime_site_packages(runtime_python: Path, environment: dict[str, str]) -> Path:
    result = subprocess.run(
        [str(runtime_python), "-I", "-c", "import sysconfig; print(sysconfig.get_path('purelib'))"],
        env=environment,
        text=True,
        capture_output=True,
        check=True,
    )
    return Path(result.stdout.strip())


def _scan_candidates(source_root: Path) -> list[str]:
    candidates: list[Path] = []
    for directory in ("src", "scripts", "tests", "docs", "governance", ".github/workflows"):
        base = source_root / directory
        candidates.extend(path for path in base.rglob("*") if path.is_file())
    for name in (
        ".env.example",
        "CHANGELOG.md",
        "CONTRIBUTING.md",
        "Makefile",
        "README.md",
        "SECURITY.md",
        "pyproject.toml",
    ):
        path = source_root / name
        if path.is_file():
            candidates.append(path)
    allowed_suffixes = {
        "",
        ".css",
        ".html",
        ".js",
        ".json",
        ".md",
        ".py",
        ".svg",
        ".toml",
        ".txt",
        ".yaml",
        ".yml",
    }
    return sorted(
        {
            path.relative_to(source_root).as_posix()
            for path in candidates
            if path.suffix.lower() in allowed_suffixes
            and path.name != ".secrets.baseline"
            and path.stat().st_size <= 2 * 1024 * 1024
        }
    )


def _normalize_scan_timestamp(path: Path, epoch: int) -> None:
    payload = _json(path)
    payload["generated_at"] = dt.datetime.fromtimestamp(epoch, tz=dt.UTC).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    _write_json(path, payload)


def _verify_release_bundle(bundle: Path, assets: Path) -> dict[str, Any]:
    expected = {
        f"{assets.name}/{path.name}": path.read_bytes()
        for path in assets.iterdir()
        if path.is_file()
    }
    with zipfile.ZipFile(bundle) as archive:
        names = archive.namelist()
        require(len(names) == len(set(names)), "release bundle contains duplicate paths")
        require(set(names) == set(expected), "release bundle inventory differs from staged assets")
        for name, payload in expected.items():
            require(archive.read(name) == payload, f"release bundle payload differs: {name}")
    return {
        "asset_count": len(expected),
        "byte_exact_against_staging": True,
        "safe_paths": True,
        "sha256": sha256_path(bundle),
    }


def _tool_versions() -> dict[str, str]:
    versions: dict[str, str] = {}
    for label, distribution in RELEASE_TOOL_DISTRIBUTIONS.items():
        try:
            versions[label] = importlib.metadata.version(distribution)
        except importlib.metadata.PackageNotFoundError as exc:
            raise ReleaseBuildError(f"release dependency is missing: {distribution}") from exc
    return versions


def _package_count_from_lock(lock_path: Path) -> int:
    return sum(
        bool(line) and not line.startswith((" ", "#", "-")) and "==" in line
        for line in lock_path.read_text(encoding="utf-8").splitlines()
    )


def build_release(
    output_directory: Path,
    *,
    epoch: int,
    allow_dirty: bool,
) -> dict[str, Any]:
    if output_directory.exists():
        raise ReleaseBuildError(
            f"refusing to overwrite existing release output: {output_directory}"
        )
    environment = _clean_environment(epoch)
    git = _git_identity(environment, allow_dirty=allow_dirty)
    command_log: list[dict[str, Any]] = []
    tool_versions = _tool_versions()
    performance = _json(ROOT / "verification/milestone-8-performance.json")
    require(performance["all_budgets_passed"] is True, "performance budget report is not passing")
    require(performance["software_version"] == __version__, "performance report version drift")

    with tempfile.TemporaryDirectory(prefix="civicdecision-release-") as temporary_name:
        temporary = Path(temporary_name)
        first_wheel, first_sdist, reproducibility = _build_twice(
            temporary,
            environment=environment,
            command_log=command_log,
        )
        wheel_validation = validate_wheel(first_wheel, version=__version__)
        sdist_validation = validate_sdist(first_sdist, version=__version__)

        _run(
            "strict package metadata check",
            [_tool("twine"), "check", "--strict", first_wheel, first_sdist],
            cwd=ROOT,
            environment=environment,
            log=command_log,
            output_path=temporary / "twine-check.log",
        )
        _run(
            "wheel contents convention check",
            [_tool("check-wheel-contents"), "--no-config", first_wheel],
            cwd=ROOT,
            environment=environment,
            log=command_log,
            output_path=temporary / "wheel-contents.log",
        )

        extracted_parent = temporary / "extracted"
        source_root = extract_validated_sdist(
            first_sdist,
            extracted_parent,
            version=__version__,
        )
        require(not (source_root / ".git").exists(), "sdist unexpectedly contains Git metadata")
        source_zip_1 = temporary / f"{DISTRIBUTION}-{__version__}-source.zip"
        source_zip_2 = temporary / f"{DISTRIBUTION}-{__version__}-source-repeat.zip"
        write_deterministic_zip(source_root, source_zip_1, epoch=epoch)
        write_deterministic_zip(source_root, source_zip_2, epoch=epoch)
        source_zip_validation = _verify_source_zip(
            source_zip_1,
            source_zip_2,
            expected_source_root=source_root.name,
        )

        runtime = temporary / "runtime"
        _run(
            "create isolated runtime environment",
            [sys.executable, "-m", "venv", runtime],
            cwd=temporary,
            environment=environment,
            log=command_log,
        )
        runtime_python = runtime / "bin/python"
        runtime_pip = runtime / "bin/pip"
        lock_path = source_root / "requirements/runtime-api.lock"
        _run(
            "install fully hashed runtime lock",
            [runtime_pip, "install", "--require-hashes", "--no-cache-dir", "-r", lock_path],
            cwd=source_root,
            environment=environment,
            log=command_log,
            timeout=1_800,
            output_path=temporary / "runtime-lock-install.log",
        )
        _run(
            "install release wheel without dependency resolution",
            [runtime_pip, "install", "--no-deps", "--no-index", first_wheel],
            cwd=source_root,
            environment=environment,
            log=command_log,
            output_path=temporary / "wheel-install.log",
        )
        _run(
            "runtime dependency consistency check",
            [runtime_pip, "check"],
            cwd=source_root,
            environment=environment,
            log=command_log,
            output_path=temporary / "pip-check.log",
        )

        smoke_report = temporary / "installed-wheel-smoke.json"
        _run(
            "installed wheel product smoke",
            [
                runtime_python,
                "-I",
                source_root / "scripts/release_smoke.py",
                "--repository-root",
                source_root,
                "--report",
                smoke_report,
            ],
            cwd=source_root,
            environment=environment,
            log=command_log,
            timeout=900,
            output_path=temporary / "installed-wheel-smoke.log",
        )
        smoke = _json(smoke_report)
        require(smoke["wheel_import_isolated_from_source"] is True, "wheel import was not isolated")

        no_git_report = temporary / "no-git-verification.json"
        _run(
            "full no-Git repository verifier",
            [
                runtime_python,
                "-I",
                source_root / "scripts/verify_repository.py",
                "--report",
                no_git_report,
            ],
            cwd=source_root,
            environment=environment,
            log=command_log,
            timeout=3_600,
            output_path=temporary / "no-git-verification.log",
        )
        no_git_verification = _json(no_git_report)
        for key in (
            "benchmark_exactly_rebuilt",
            "global_city_catalog_exactly_rebuilt",
            "product_exactly_rebuilt",
            "scenario_library_exactly_rebuilt",
            "tier_d_exactly_rebuilt",
            "tier_s_exactly_rebuilt",
        ):
            require(no_git_verification.get(key) is True, f"no-Git verifier gate failed: {key}")

        bandit_report = temporary / "bandit.json"
        _run(
            "medium-confidence medium-severity source security scan",
            [
                _tool("bandit"),
                "-r",
                "src/civicdecision",
                "--severity-level",
                "medium",
                "--confidence-level",
                "medium",
                "--format",
                "json",
                "--output",
                bandit_report,
                "--quiet",
            ],
            cwd=source_root,
            environment=environment,
            log=command_log,
        )
        bandit = _json(bandit_report)
        require(bandit.get("results") == [], "Bandit found medium-or-higher source issues")
        if "generated_at" in bandit:
            bandit["generated_at"] = dt.datetime.fromtimestamp(epoch, tz=dt.UTC).isoformat()
            _write_json(bandit_report, bandit)

        secret_report = temporary / "detect-secrets.json"
        scan_candidates = _scan_candidates(source_root)
        shutil.copyfile(source_root / ".secrets.baseline", secret_report)
        _run(
            "fresh offline secret scan",
            [
                _tool("detect-secrets"),
                "scan",
                "--baseline",
                secret_report,
                "--force-use-all-plugins",
                "--no-verify",
                *scan_candidates,
            ],
            cwd=source_root,
            environment=environment,
            log=command_log,
            timeout=900,
        )
        _normalize_scan_timestamp(secret_report, epoch)
        secret_scan = _json(secret_report)
        require(secret_scan.get("results") == {}, "secret scan produced unresolved findings")

        dependency_audit_path = temporary / "dependency-audit.json"
        _run(
            "hashed-lock known-vulnerability audit",
            [
                _tool("pip-audit"),
                "-r",
                lock_path,
                "--require-hashes",
                "--no-deps",
                "--progress-spinner",
                "off",
                "--format",
                "json",
                "--output",
                dependency_audit_path,
            ],
            cwd=source_root,
            environment=environment,
            log=command_log,
            timeout=1_800,
        )
        dependency_audit = _json(dependency_audit_path)
        audited_dependencies = dependency_audit.get("dependencies", [])
        vulnerabilities = sum(len(item.get("vulns", [])) for item in audited_dependencies)
        require(vulnerabilities == 0, "dependency audit found known vulnerabilities")

        license_path = temporary / "third-party-licenses.json"
        _run(
            "installed runtime license inventory",
            [
                _tool("pip-licenses"),
                "--python",
                runtime_python,
                "--format",
                "json",
                "--with-urls",
                "--output-file",
                license_path,
            ],
            cwd=source_root,
            environment=environment,
            log=command_log,
        )
        licenses = _json(license_path)
        require(bool(licenses), "license inventory is empty")
        require(
            all(
                item.get("Name") and item.get("Version") and item.get("License")
                for item in licenses
            ),
            "license inventory contains an empty identity or license field",
        )

        sbom_path = temporary / "sbom.cdx.json"
        _run(
            "reproducible CycloneDX runtime SBOM",
            [
                _tool("cyclonedx-py"),
                "environment",
                runtime_python,
                "--pyproject",
                source_root / "pyproject.toml",
                "--mc-type",
                "application",
                "--output-reproducible",
                "--spec-version",
                "1.6",
                "--output-format",
                "JSON",
                "--output-file",
                sbom_path,
                "--validate",
            ],
            cwd=source_root,
            environment=environment,
            log=command_log,
            timeout=900,
        )
        sbom = _json(sbom_path)
        components = sbom.get("components", [])
        root_component = sbom.get("metadata", {}).get("component", {})
        require(root_component.get("name") == DISTRIBUTION, "SBOM omits root application")
        require(root_component.get("type") == "application", "SBOM root type drift")

        site_packages = _runtime_site_packages(runtime_python, environment)
        release_time = (
            dt.datetime.fromtimestamp(epoch, tz=dt.UTC).isoformat().replace("+00:00", "Z")
        )
        runtime_packages = _package_count_from_lock(lock_path)
        gates = [
            "clean-or-explicitly-overridden-source-state",
            "two-byte-identical-wheel-builds",
            "two-byte-identical-sdist-builds",
            "two-byte-identical-source-zips",
            "two-byte-identical-release-bundles",
            "safe-wheel-paths-and-inventory",
            "complete-wheel-record-hashes-and-sizes",
            "safe-sdist-paths-and-inventory",
            "pep-639-license-metadata",
            "strict-twine-metadata-check",
            "wheel-contents-convention-check",
            "fully-hashed-runtime-lock-install",
            "isolated-wheel-install-without-dependency-resolution",
            "pip-dependency-consistency-check",
            "installed-cli-sdk-api-web-plugin-smoke",
            "full-no-git-golden-rebuild",
            "medium-or-higher-bandit-clean",
            "fresh-offline-secret-scan-clean",
            "known-vulnerability-audit-clean-at-check-time",
            "third-party-license-inventory-present",
            "cyclonedx-1.6-sbom-valid",
            "all-nine-local-performance-budgets-passed",
        ]
        report: dict[str, Any] = {
            "schema_version": "1.0.0",
            "release_identity": {
                "distribution": DISTRIBUTION,
                "version": __version__,
                "release_stage": "local-reproducible-candidate",
                "source_date_epoch": epoch,
                "normalized_verified_at": release_time,
                "git": git,
            },
            "artifacts": {
                "wheel": wheel_validation,
                "sdist": sdist_validation,
                "source_zip": source_zip_validation,
                "repeated_builds": reproducibility,
            },
            "clean_install": {
                "fresh_virtual_environment": True,
                "hashed_lock": True,
                "locked_runtime_packages": runtime_packages,
                "pip_check": "passed",
                "site_packages_layout": site_packages.resolve()
                .relative_to(runtime.resolve())
                .as_posix(),
                "wheel_installed_no_deps_no_index": True,
            },
            "installed_product_smoke": smoke,
            "no_git_verification": {
                "archive_has_git_metadata": False,
                "full_verifier_passed": True,
                "product_artifacts": no_git_verification["product_artifacts"],
                "product_exactly_rebuilt": no_git_verification["product_exactly_rebuilt"],
                "scenario_library_files": no_git_verification["scenario_library_files"],
                "scenario_library_exactly_rebuilt": no_git_verification[
                    "scenario_library_exactly_rebuilt"
                ],
                "tier_d_exactly_rebuilt": no_git_verification["tier_d_exactly_rebuilt"],
                "tier_s_exactly_rebuilt": no_git_verification["tier_s_exactly_rebuilt"],
            },
            "supply_chain": {
                "bandit_medium_or_higher_findings": len(bandit["results"]),
                "cyclonedx_spec_version": sbom.get("specVersion"),
                "locked_dependency_audit_count": len(audited_dependencies),
                "known_vulnerabilities_at_check_time": vulnerabilities,
                "license_inventory_entries": len(licenses),
                "runtime_lock_sha256": sha256_path(lock_path),
                "sbom_components_including_root": len(components) + 1,
                "sbom_root_application": root_component["name"],
                "secret_scan_files": len(scan_candidates),
                "secret_scan_findings": sum(
                    len(items) for items in secret_scan["results"].values()
                ),
            },
            "performance": {
                "all_nine_budgets_passed": performance["all_budgets_passed"],
                "budget_count": len(performance["budget_checks"]),
                "boundary": performance["boundary"],
                "environment": performance["environment"],
            },
            "release_gates": {
                "passed": len(gates),
                "failed": 0,
                "items": [{"gate": gate, "status": "passed"} for gate in gates],
            },
            "tool_versions": tool_versions,
            "command_log": command_log,
            "claim_boundary": [
                "This report verifies a local release candidate; it is not a public deployment "
                "or GitHub Release.",
                "A clean vulnerability audit means no finding in the queried advisory service "
                "at check time; it is not a guarantee of absence.",
                "The SBOM and license inventory describe the isolated Python runtime, not "
                "operating-system or hosting dependencies.",
                "Local performance budgets are single-process development-machine evidence, "
                "not load, scale, availability, or SLA evidence.",
                "Internal exact rebuilds do not constitute external domain review, penetration "
                "testing, adoption, or real-world impact.",
            ],
            "external_gates_not_claimed": [
                "cryptographic artifact signature or trusted timestamp",
                "published Git tag and GitHub Release",
                "remote CI, CodeQL, or branch-protection result for this commit",
                "public hosted demo availability",
                "independent security, accessibility, or domain review",
                "real user adoption or municipal impact",
            ],
        }

        publish_root = temporary / "publish"
        asset_directory = publish_root / f"{DISTRIBUTION}-{__version__}-release"
        asset_directory.mkdir(parents=True)
        copy_map = {
            first_wheel: asset_directory / first_wheel.name,
            first_sdist: asset_directory / first_sdist.name,
            source_zip_1: asset_directory / source_zip_1.name,
            smoke_report: asset_directory / smoke_report.name,
            no_git_report: asset_directory / no_git_report.name,
            bandit_report: asset_directory / bandit_report.name,
            secret_report: asset_directory / secret_report.name,
            dependency_audit_path: asset_directory / dependency_audit_path.name,
            license_path: asset_directory / license_path.name,
            sbom_path: asset_directory / sbom_path.name,
            lock_path: asset_directory / lock_path.name,
            ROOT / "verification/milestone-8-performance.json": (
                asset_directory / "performance.json"
            ),
            ROOT / "docs/RELEASE_NOTES_0.8.0.md": asset_directory / "RELEASE_NOTES.md",
        }
        for source, target in copy_map.items():
            shutil.copyfile(source, target)
        release_report_path = asset_directory / "release-report.json"
        _write_json(release_report_path, report)
        checksum_path = asset_directory / "SHA256SUMS"
        write_checksum_inventory(
            [path for path in asset_directory.iterdir() if path.is_file()],
            checksum_path,
        )
        checksum_validation = verify_checksum_inventory(asset_directory, checksum_path)
        report["release_asset_checksums"] = checksum_validation
        report["release_bundle_contract"] = {
            "format": "deterministic ZIP",
            "contains_asset_directory": asset_directory.name,
            "detached_sha256_sidecar": True,
            "two_byte_identical_writes_required": True,
            "self_referential_bundle_hash_excluded_from_embedded_report": True,
        }
        _write_json(release_report_path, report)
        write_checksum_inventory(
            [
                path
                for path in asset_directory.iterdir()
                if path.is_file() and path != checksum_path
            ],
            checksum_path,
        )
        verify_checksum_inventory(asset_directory, checksum_path)

        bundle = publish_root / f"{DISTRIBUTION}-{__version__}-release-bundle.zip"
        repeated_bundle = publish_root / f"{DISTRIBUTION}-{__version__}-release-bundle-repeat.zip"
        write_deterministic_zip(asset_directory, bundle, epoch=epoch)
        write_deterministic_zip(asset_directory, repeated_bundle, epoch=epoch)
        require(
            bundle.read_bytes() == repeated_bundle.read_bytes(),
            "repeated release bundles differ",
        )
        repeated_bundle.unlink()
        bundle_validation = _verify_release_bundle(bundle, asset_directory)
        sidecar = bundle.with_suffix(bundle.suffix + ".sha256")
        sidecar.write_text(f"{bundle_validation['sha256']}  {bundle.name}\n", encoding="ascii")

        output_directory.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(publish_root, output_directory)
        final_report = _json(output_directory / asset_directory.name / "release-report.json")
    return final_report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--source-date-epoch", type=int)
    parser.add_argument(
        "--allow-dirty",
        action="store_true",
        help="development-only override; the report will preserve dirty=true",
    )
    args = parser.parse_args()
    epoch = args.source_date_epoch or _default_epoch()
    output = args.output_dir or ROOT / "dist" / f"release-{__version__}"
    report = build_release(output.resolve(), epoch=epoch, allow_dirty=args.allow_dirty)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ReleaseValidationError, ReleaseBuildError, subprocess.SubprocessError) as exc:
        raise SystemExit(f"release candidate failed closed: {exc}") from exc
