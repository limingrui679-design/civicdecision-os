"""Deterministic claim-to-evidence and public-state auditing."""

from __future__ import annotations

import datetime as dt
import hashlib
import http.client
import json
import math
import re
import subprocess
import tomllib
import urllib.parse
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any, cast

from civicdecision import __version__


class ClaimAuditError(ValueError):
    """Raised when a claim-audit policy or evidence source is malformed."""


ClaimValue = bool | int | float | str

_CHECK_ID = re.compile(r"[a-z0-9][a-z0-9-]*\Z")
_GITHUB_REPOSITORY = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z")
_JSON_ARRAY_INDEX = re.compile(r"0|[1-9][0-9]*\Z")
_PUBLIC_STATE_REQUIRED_FIELDS = {
    "github_repository",
    "github_repository_http_status",
    "local_git_remotes",
    "package_project_urls",
    "public_hosted_demo_url",
}


def _reject_nonfinite_json(token: str) -> None:
    raise ClaimAuditError(f"JSON document contains non-finite number {token!r}")


def _load_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(
            path.read_text(encoding="utf-8"),
            parse_constant=_reject_nonfinite_json,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ClaimAuditError(f"cannot load JSON object {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ClaimAuditError(f"JSON document must be an object: {path}")
    return cast(dict[str, Any], payload)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _safe_relative(root: Path, value: str) -> Path:
    relative = Path(value)
    if relative.is_absolute() or not relative.parts or ".." in relative.parts:
        raise ClaimAuditError(f"claim-audit path must be safe and relative: {value!r}")
    resolved = (root / relative).resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise ClaimAuditError(f"claim-audit path escapes repository root: {value!r}") from exc
    return resolved


def _resolve_pointer(document: object, pointer: str) -> object:
    if pointer == "":
        return document
    if not pointer.startswith("/"):
        raise ClaimAuditError(f"JSON pointer must be empty or start with '/': {pointer!r}")
    current = document
    for raw_part in pointer[1:].split("/"):
        if re.search(r"~(?:[^01]|$)", raw_part):
            raise ClaimAuditError(f"JSON pointer contains an invalid escape: {pointer!r}")
        part = raw_part.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict):
            mapping = cast(dict[str, object], current)
            if part not in mapping:
                raise ClaimAuditError(f"JSON pointer component is absent: {pointer!r}")
            current = mapping[part]
        elif isinstance(current, list):
            sequence = cast(list[object], current)
            if not _JSON_ARRAY_INDEX.fullmatch(part):
                raise ClaimAuditError(f"JSON pointer list index is invalid: {pointer!r}")
            try:
                index = int(part)
                current = sequence[index]
            except IndexError as exc:
                raise ClaimAuditError(f"JSON pointer list index is invalid: {pointer!r}") from exc
        else:
            raise ClaimAuditError(f"JSON pointer traverses a scalar: {pointer!r}")
    return current


def _scalar(value: object, *, claim_id: str) -> ClaimValue:
    if isinstance(value, (bool, int, float, str)):
        return value
    raise ClaimAuditError(f"quantitative claim {claim_id!r} resolved to a non-scalar")


def _number(value: object, *, claim_id: str) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ClaimAuditError(f"quantitative claim {claim_id!r} requires numeric evidence")
    if isinstance(value, float) and not math.isfinite(value):
        raise ClaimAuditError(f"quantitative claim {claim_id!r} requires finite numeric evidence")
    return value


def _evaluate_claim(root: Path, claim: Mapping[str, Any]) -> tuple[ClaimValue, set[Path]]:
    claim_id = str(claim.get("id", "<missing>"))
    raw_sources = claim.get("sources")
    if not isinstance(raw_sources, list) or not raw_sources:
        raise ClaimAuditError(f"quantitative claim {claim_id!r} must declare sources")
    values: list[object] = []
    evidence_paths: set[Path] = set()
    for raw_source in raw_sources:
        if not isinstance(raw_source, dict):
            raise ClaimAuditError(f"quantitative claim {claim_id!r} has a malformed source")
        source = cast(dict[str, Any], raw_source)
        source_path = _safe_relative(root, str(source.get("path", "")))
        pointer = str(source.get("pointer", ""))
        evidence_paths.add(source_path)
        values.append(_resolve_pointer(_load_object(source_path), pointer))

    operation = str(claim.get("operation", "single"))
    if operation == "single":
        if len(values) != 1:
            raise ClaimAuditError(f"single claim {claim_id!r} must resolve exactly one source")
        return _scalar(values[0], claim_id=claim_id), evidence_paths
    if operation == "count":
        if len(values) != 1 or not isinstance(values[0], (list, dict)):
            raise ClaimAuditError(f"count claim {claim_id!r} must resolve one list or object")
        return len(values[0]), evidence_paths
    numbers = [_number(value, claim_id=claim_id) for value in values]
    if operation == "sum":
        return sum(numbers), evidence_paths
    if operation == "subtract":
        if len(numbers) != 2:
            raise ClaimAuditError(f"subtract claim {claim_id!r} requires two sources")
        return numbers[0] - numbers[1], evidence_paths
    if operation == "choose-two":
        if len(numbers) != 1 or not isinstance(numbers[0], int) or numbers[0] < 0:
            raise ClaimAuditError(
                f"choose-two claim {claim_id!r} requires one non-negative integer"
            )
        return numbers[0] * (numbers[0] - 1) // 2, evidence_paths
    raise ClaimAuditError(f"quantitative claim {claim_id!r} has unknown operation {operation!r}")


def _scanned_files(root: Path, patterns: Iterable[str]) -> list[Path]:
    paths: set[Path] = set()
    for pattern in patterns:
        for path in root.glob(pattern):
            if path.is_file() and not path.is_symlink():
                paths.add(path.resolve())
    return sorted(paths)


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ClaimAuditError(f"cannot read claim surface {path}: {exc}") from exc


def _check_id(rule: Mapping[str, Any], *, kind: str, seen: set[str]) -> str:
    value = rule.get("id")
    if not isinstance(value, str) or not _CHECK_ID.fullmatch(value):
        raise ClaimAuditError(f"{kind} id must use lowercase letters, digits, and hyphens")
    if value in seen:
        raise ClaimAuditError(f"duplicate claim-audit check id: {value!r}")
    seen.add(value)
    return value


def _validate_snapshot_timestamp(value: object) -> str:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ClaimAuditError("public-state checked_at must be an RFC 3339 UTC timestamp")
    try:
        dt.datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    except ValueError as exc:
        raise ClaimAuditError("public-state checked_at must be an RFC 3339 UTC timestamp") from exc
    return value


def _fetch_http_status(url: str, *, timeout_seconds: float) -> int:
    parsed = urllib.parse.urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.netloc != "api.github.com"
        or parsed.query
        or parsed.fragment
        or not re.fullmatch(r"/repos/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", parsed.path)
    ):
        raise ClaimAuditError("live repository check requires an exact GitHub API repository URL")
    connection = http.client.HTTPSConnection("api.github.com", timeout=timeout_seconds)
    try:
        connection.request(
            "GET",
            parsed.path,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "CivicDecision-claim-audit",
            },
        )
        with connection.getresponse() as response:
            return int(response.status)
    finally:
        connection.close()


def _git_remotes(root: Path) -> list[str] | None:
    if not (root / ".git").exists():
        return None
    try:
        result = subprocess.run(
            ["git", "remote", "-v"],
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ClaimAuditError(f"git remote inspection failed: {exc}") from exc
    if result.returncode != 0:
        raise ClaimAuditError(f"git remote inspection failed: {result.stderr.strip()}")
    return sorted(line for line in result.stdout.splitlines() if line.strip())


def _validate_check_accounting(
    checks_total: int,
    checks_passed: int,
    failures: list[dict[str, Any]],
) -> None:
    if checks_total != checks_passed + len(failures):
        raise ClaimAuditError("claim-audit internal check accounting drifted")


def audit_claims(
    root: Path,
    *,
    policy_path: Path | None = None,
    refresh_public_state: bool = False,
    network_timeout_seconds: float = 20.0,
) -> dict[str, Any]:
    """Audit governed text claims against committed evidence and a public-state snapshot."""

    repository_root = root.resolve()
    selected_policy = (
        (repository_root / policy_path).resolve()
        if policy_path is not None and not policy_path.is_absolute()
        else policy_path.resolve()
        if policy_path is not None
        else repository_root / "governance/CLAIM_AUDIT_POLICY.json"
    )
    try:
        selected_policy.relative_to(repository_root)
    except ValueError as exc:
        raise ClaimAuditError("claim-audit policy must be inside the repository root") from exc
    policy = _load_object(selected_policy)
    if policy.get("schema_version") != "1.0.0":
        raise ClaimAuditError("claim-audit policy schema_version must be 1.0.0")

    failures: list[dict[str, Any]] = []
    checks_passed = 0
    checks_total = 0
    evidence_paths: set[Path] = set()

    raw_patterns = policy.get("scan_patterns")
    if not isinstance(raw_patterns, list) or not all(
        isinstance(item, str) for item in raw_patterns
    ):
        raise ClaimAuditError("claim-audit policy scan_patterns must be a string list")
    for pattern in cast(list[str], raw_patterns):
        pattern_path = Path(pattern)
        if pattern_path.is_absolute() or not pattern_path.parts or ".." in pattern_path.parts:
            raise ClaimAuditError(
                f"claim-audit scan pattern must be safe and relative: {pattern!r}"
            )
    scan_paths = _scanned_files(repository_root, cast(list[str], raw_patterns))
    if not scan_paths:
        raise ClaimAuditError("claim-audit scan resolved no files")
    texts = {path: _read_text(path) for path in scan_paths}
    governed_surface_hashes = {
        path.relative_to(repository_root).as_posix(): _sha256(path) for path in scan_paths
    }
    seen_check_ids: set[str] = set()

    raw_forbidden = policy.get("forbidden_literals", [])
    if not isinstance(raw_forbidden, list):
        raise ClaimAuditError("forbidden_literals must be a list")
    for raw_rule in raw_forbidden:
        if not isinstance(raw_rule, dict):
            raise ClaimAuditError("forbidden literal rule must be an object")
        rule = cast(dict[str, Any], raw_rule)
        rule_id = _check_id(rule, kind="forbidden literal", seen=seen_check_ids)
        literal = str(rule.get("literal", ""))
        if not literal:
            raise ClaimAuditError(f"forbidden literal {rule_id!r} is empty")
        matches = [
            path.relative_to(repository_root).as_posix()
            for path, text in texts.items()
            if literal in text
        ]
        checks_total += 1
        if matches:
            failures.append(
                {
                    "check": rule_id,
                    "category": "forbidden-literal",
                    "detail": f"forbidden literal found in {', '.join(matches)}",
                }
            )
        else:
            checks_passed += 1

    raw_boundaries = policy.get("required_boundaries", [])
    if not isinstance(raw_boundaries, list):
        raise ClaimAuditError("required_boundaries must be a list")
    for raw_rule in raw_boundaries:
        if not isinstance(raw_rule, dict):
            raise ClaimAuditError("required boundary rule must be an object")
        rule = cast(dict[str, Any], raw_rule)
        rule_id = _check_id(rule, kind="required boundary", seen=seen_check_ids)
        path = _safe_relative(repository_root, str(rule.get("path", "")))
        phrase = str(rule.get("contains", ""))
        if not phrase:
            raise ClaimAuditError(f"required boundary {rule_id!r} is empty")
        checks_total += 1
        if not path.is_file() or phrase not in _read_text(path):
            failures.append(
                {
                    "check": rule_id,
                    "category": "required-boundary",
                    "detail": f"required phrase is absent from {path.relative_to(repository_root)}",
                }
            )
        else:
            checks_passed += 1

    quantitative_values: dict[str, ClaimValue] = {}
    rendering_count = 0
    raw_claims = policy.get("quantitative_claims", [])
    if not isinstance(raw_claims, list):
        raise ClaimAuditError("quantitative_claims must be a list")
    for raw_claim in raw_claims:
        if not isinstance(raw_claim, dict):
            raise ClaimAuditError("quantitative claim must be an object")
        claim = cast(dict[str, Any], raw_claim)
        claim_id = _check_id(claim, kind="quantitative claim", seen=seen_check_ids)
        value, paths = _evaluate_claim(repository_root, claim)
        evidence_paths.update(paths)
        quantitative_values[claim_id] = value
        checks_total += 1
        expected = claim.get("expected")
        if type(expected) is not type(value) or expected != value:
            failures.append(
                {
                    "check": claim_id,
                    "category": "evidence-value",
                    "detail": f"resolved value {value!r} differs from policy value {expected!r}",
                }
            )
        else:
            checks_passed += 1

        raw_renderings = claim.get("renderings", [])
        if not isinstance(raw_renderings, list):
            raise ClaimAuditError(f"quantitative claim {claim_id!r} renderings must be a list")
        if not raw_renderings:
            raise ClaimAuditError(
                f"quantitative claim {claim_id!r} renderings must be a non-empty list"
            )
        for index, raw_rendering in enumerate(raw_renderings, start=1):
            if not isinstance(raw_rendering, dict):
                raise ClaimAuditError(f"quantitative claim {claim_id!r} rendering is malformed")
            rendering = cast(dict[str, Any], raw_rendering)
            path = _safe_relative(repository_root, str(rendering.get("path", "")))
            template = str(rendering.get("template", ""))
            if "{value" not in template:
                raise ClaimAuditError(
                    f"quantitative claim {claim_id!r} rendering must interpolate value"
                )
            try:
                rendered = template.format(value=value)
            except (KeyError, ValueError) as exc:
                raise ClaimAuditError(
                    f"quantitative claim {claim_id!r} has an invalid rendering template"
                ) from exc
            checks_total += 1
            rendering_count += 1
            if not path.is_file() or rendered not in _read_text(path):
                failures.append(
                    {
                        "check": f"{claim_id}:rendering-{index}",
                        "category": "claim-rendering",
                        "detail": (
                            f"expected rendering {rendered!r} is absent from "
                            f"{path.relative_to(repository_root)}"
                        ),
                    }
                )
            else:
                checks_passed += 1

    public_state_path = _safe_relative(
        repository_root,
        str(policy.get("public_state_snapshot", "")),
    )
    public_state = _load_object(public_state_path)
    evidence_paths.add(public_state_path)
    snapshot_checked_at = _validate_snapshot_timestamp(public_state.get("checked_at"))
    checks_total += 1
    if public_state.get("schema_version") == "1.0.0":
        checks_passed += 1
    else:
        failures.append(
            {
                "check": "public-state-schema",
                "category": "public-state",
                "detail": "public-state snapshot schema_version must be 1.0.0",
            }
        )

    raw_public_state_contract = policy.get("public_state_contract")
    if not isinstance(raw_public_state_contract, dict) or not raw_public_state_contract:
        raise ClaimAuditError("public_state_contract must be a non-empty object")
    public_state_contract = cast(dict[str, Any], raw_public_state_contract)
    missing_contract_fields = _PUBLIC_STATE_REQUIRED_FIELDS - public_state_contract.keys()
    if missing_contract_fields:
        raise ClaimAuditError(
            "public_state_contract is missing required fields: "
            + ", ".join(sorted(missing_contract_fields))
        )
    for field, expected_value in public_state_contract.items():
        checks_total += 1
        if public_state.get(field) == expected_value:
            checks_passed += 1
        else:
            failures.append(
                {
                    "check": f"public-state-contract:{field}",
                    "category": "public-state",
                    "detail": (
                        f"public-state field {field!r} is {public_state.get(field)!r}, "
                        f"expected {expected_value!r}"
                    ),
                }
            )
    contracted_repository = public_state_contract.get("github_repository")
    if not isinstance(contracted_repository, str) or not _GITHUB_REPOSITORY.fullmatch(
        contracted_repository
    ):
        raise ClaimAuditError("public_state_contract github_repository must be owner/repository")
    expected_endpoint = f"https://api.github.com/repos/{contracted_repository}"
    checks_total += 1
    if public_state.get("github_repository_api") == expected_endpoint:
        checks_passed += 1
    else:
        failures.append(
            {
                "check": "public-state-contract:github_repository_api",
                "category": "public-state",
                "detail": "GitHub API endpoint does not match the contracted repository identity",
            }
        )

    pyproject = tomllib.loads((repository_root / "pyproject.toml").read_text(encoding="utf-8"))
    project = cast(dict[str, Any], pyproject.get("project", {}))
    declared_urls = cast(dict[str, Any], project.get("urls", {}))
    expected_urls = public_state.get("package_project_urls")
    checks_total += 1
    if expected_urls == [] and declared_urls == {}:
        checks_passed += 1
    else:
        failures.append(
            {
                "check": "package-project-urls",
                "category": "public-state",
                "detail": (
                    "package project URLs differ from the no-public-repository snapshot: "
                    f"{declared_urls!r}"
                ),
            }
        )

    actual_remotes = _git_remotes(repository_root)
    expected_remotes = public_state.get("local_git_remotes")
    checks_total += 1
    if actual_remotes is None or actual_remotes == expected_remotes:
        checks_passed += 1
    else:
        failures.append(
            {
                "check": "local-git-remotes",
                "category": "public-state",
                "detail": f"local Git remotes changed: {actual_remotes!r}",
            }
        )

    endpoint = str(public_state.get("github_repository_api", ""))
    expected_status = public_state.get("github_repository_http_status")
    if (
        not isinstance(expected_status, int)
        or isinstance(expected_status, bool)
        or not 100 <= expected_status <= 599
    ):
        raise ClaimAuditError("public-state GitHub HTTP status must be an integer from 100 to 599")
    refreshed_status: int | None = None
    if refresh_public_state:
        try:
            refreshed_status = _fetch_http_status(
                expected_endpoint,
                timeout_seconds=network_timeout_seconds,
            )
        except (OSError, http.client.HTTPException) as exc:
            failures.append(
                {
                    "check": "live-public-repository-state",
                    "category": "public-state",
                    "detail": f"live public-state refresh failed: {exc}",
                }
            )
            checks_total += 1
        else:
            checks_total += 1
            if refreshed_status == expected_status:
                checks_passed += 1
            else:
                failures.append(
                    {
                        "check": "live-public-repository-state",
                        "category": "public-state",
                        "detail": (
                            f"GitHub endpoint returned {refreshed_status}, "
                            f"expected {expected_status}"
                        ),
                    }
                )

    evidence_hashes = {
        path.relative_to(repository_root).as_posix(): _sha256(path)
        for path in sorted(evidence_paths)
    }
    checks_failed = len(failures)
    _validate_check_accounting(checks_total, checks_passed, failures)
    audit_completed_at = (
        dt.datetime.now(tz=dt.UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
        if refresh_public_state
        else None
    )

    return {
        "schema_version": "1.0.0",
        "software_version": __version__,
        "status": "passed" if not failures else "failed",
        "snapshot_checked_at": snapshot_checked_at,
        "audit_completed_at": audit_completed_at,
        "refresh_mode": "live" if refresh_public_state else "snapshot-only",
        "policy": {
            "path": selected_policy.relative_to(repository_root).as_posix(),
            "sha256": _sha256(selected_policy),
        },
        "scope": {
            "scanned_files": len(scan_paths),
            "scanned_bytes": sum(path.stat().st_size for path in scan_paths),
            "forbidden_literals": len(raw_forbidden),
            "required_boundaries": len(raw_boundaries),
            "quantitative_claims": len(raw_claims),
            "claim_renderings": rendering_count,
            "public_state_contract_fields": len(public_state_contract) + 1,
        },
        "checks": {
            "total": checks_total,
            "passed": checks_passed,
            "failed": checks_failed,
        },
        "quantitative_values": quantitative_values,
        "evidence_sha256": evidence_hashes,
        "governed_surface_sha256": governed_surface_hashes,
        "public_state": {
            "github_repository": public_state.get("github_repository"),
            "github_repository_api": endpoint,
            "snapshot_http_status": expected_status,
            "refreshed_http_status": refreshed_status,
            "local_git_remotes": actual_remotes,
            "package_project_urls": declared_urls,
            "public_hosted_demo_url": public_state.get("public_hosted_demo_url"),
        },
        "failures": failures,
        "claim_boundary": [
            "This audit checks governed text, committed evidence values, and a dated public-state "
            "snapshot; it is not external validation.",
            "A passing offline audit does not prove that external state is unchanged; refresh it "
            "before publication.",
            "No public repository, hosted demo, remote CI, external review, users, adoption, or "
            "impact is inferred from local implementation evidence.",
        ],
    }


__all__ = ["ClaimAuditError", "audit_claims"]
