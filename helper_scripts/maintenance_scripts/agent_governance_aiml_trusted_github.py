"""Authenticated GitHub policy verification for S0.3 Program adoption."""

from __future__ import annotations

import re
import ssl
import stat
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Protocol

from agent_governance_aiml_trusted_common import (
    HEAD_RE,
    canonical_digest,
    instant as _instant,
    strict_json_loads,
    utc_now as _utc_now,
)
from agent_governance_aiml_trusted_github_pr import (
    associated_pulls_path,
    associated_pulls_projection,
    check_runs_path,
    check_runs_projection,
    pull_path,
    pull_projection,
    select_merged_pull,
    verify_merged_pull_gate_outcomes,
)


GITHUB_API_ORIGIN = "https://api.github.com"
GITHUB_API_VERSION = "2022-11-28"
TRUSTED_CA_BUNDLE_PATHS = (
    Path("/etc/ssl/certs/ca-certificates.crt"),
    Path("/etc/ssl/cert.pem"),
)
EXPECTED_REPOSITORY_ID = 1188963759
EXPECTED_REPOSITORY_FULL_NAME = "yunancun/Arcane-Equilibrium"
EXPECTED_DEFAULT_BRANCH = "main"
EXPECTED_RULESET_ID = 19071223
EXPECTED_RULESET_NAME = "Protect main after public hardening"
GITHUB_CAPTURE_PROJECTION_VERSION = "github_capture_projection_v2"
EXPECTED_REQUIRED_CHECKS = (
    {"context": "Analyze (actions)", "integration_id": 15368},
    {"context": "Analyze (javascript-typescript)", "integration_id": 15368},
    {"context": "Analyze (python)", "integration_id": 15368},
    {
        "context": "Git workflow policy (unconditional cheap gate)",
        "integration_id": 15368,
    },
    {"context": "applied migration immutability guard", "integration_id": 15368},
    {"context": "classify changed paths (linux)", "integration_id": 15368},
    {"context": "public repository hygiene gate", "integration_id": 15368},
    {"context": "stable_id duplication guard", "integration_id": 15368},
)
EXPECTED_PULL_REQUEST_PARAMETERS = {
    "allowed_merge_methods": ["merge", "rebase", "squash"],
    "dismiss_stale_reviews_on_push": False,
    "require_code_owner_review": False,
    "require_last_push_approval": False,
    "required_approving_review_count": 0,
    "required_review_thread_resolution": True,
    "required_reviewers": [],
}
EXPECTED_REQUIRED_STATUS_CHECK_PARAMETERS = {
    "do_not_enforce_on_create": True,
    "required_status_checks": list(EXPECTED_REQUIRED_CHECKS),
    "strict_required_status_checks_policy": True,
}
MAX_GITHUB_BYTES = 4 * 1024 * 1024
MAX_GITHUB_PAGES = 10
GITHUB_PAGE_SIZE = 100
MAX_GITHUB_OBSERVATION_AGE = timedelta(minutes=5)
MAX_GITHUB_VALIDITY = timedelta(minutes=15)
MAX_CLOCK_SKEW = timedelta(seconds=60)


class GitHubTransport(Protocol):
    def get_json(self, path: str, token: bytes) -> Any: ...


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> None:
        return None


class StdlibGitHubTransport:
    """GET-only, fixed-origin GitHub API transport with no proxy inheritance."""

    def __init__(self) -> None:
        ca_bundle: Path | None = None
        for candidate in TRUSTED_CA_BUNDLE_PATHS:
            if not candidate.exists():
                continue
            resolved = candidate.resolve(strict=True)
            info = resolved.stat()
            if (
                stat.S_ISREG(info.st_mode)
                and info.st_uid == 0
                and not (info.st_mode & (stat.S_IWGRP | stat.S_IWOTH))
            ):
                ca_bundle = resolved
                break
        if ca_bundle is None:
            raise ValueError("trusted system CA bundle is unavailable")
        context = ssl.create_default_context(cafile=str(ca_bundle))
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        self._opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}),
            _NoRedirect(),
            urllib.request.HTTPSHandler(context=context),
        )

    def get_json(self, path: str, token: bytes) -> Any:
        if (
            re.fullmatch(
                r"/[A-Za-z0-9._~%/+\-]+(?:\?[A-Za-z0-9._~%=&,+\-]+)?",
                path,
            )
            is None
            or "#" in path
            or "//" in path
        ):
            raise ValueError("GitHub endpoint path is invalid")
        url = GITHUB_API_ORIGIN + path
        request = urllib.request.Request(
            url,
            method="GET",
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": "Bearer " + token.decode("ascii"),
                "User-Agent": "arcane-equilibrium-aiml-trusted-finalizer/1",
                "X-GitHub-Api-Version": GITHUB_API_VERSION,
                "Cache-Control": "no-cache",
            },
        )
        try:
            with self._opener.open(request, timeout=15) as response:
                if response.status != 200 or response.geturl() != url:
                    raise ValueError("GitHub response status/origin is invalid")
                raw = response.read(MAX_GITHUB_BYTES + 1)
                if len(raw) > MAX_GITHUB_BYTES:
                    raise ValueError("GitHub response exceeds size limit")
        except (UnicodeError, urllib.error.URLError) as error:
            raise ValueError("authenticated GitHub observation failed") from error
        return strict_json_loads(raw)


def _github_static_paths() -> dict[str, str]:
    base = f"/repos/{EXPECTED_REPOSITORY_FULL_NAME}"
    return {
        "repository": base,
        "ruleset_detail": (
            f"{base}/rulesets/{EXPECTED_RULESET_ID}?includes_parents=true"
        ),
        "default_branch_ref": f"{base}/git/ref/heads/{EXPECTED_DEFAULT_BRANCH}",
    }


def _github_inventory_path(page: int) -> str:
    base = f"/repos/{EXPECTED_REPOSITORY_FULL_NAME}/rulesets"
    return (
        f"{base}?includes_parents=true&targets=branch"
        f"&per_page={GITHUB_PAGE_SIZE}&page={page}"
    )


def _github_effective_rules_path(page: int) -> str:
    base = (
        f"/repos/{EXPECTED_REPOSITORY_FULL_NAME}/rules/branches/"
        f"{EXPECTED_DEFAULT_BRANCH}"
    )
    return f"{base}?per_page={GITHUB_PAGE_SIZE}&page={page}"


def _github_commit_path(head: str) -> str:
    if HEAD_RE.fullmatch(head) is None:
        raise ValueError("GitHub commit head is invalid")
    return f"/repos/{EXPECTED_REPOSITORY_FULL_NAME}/commits/{head}"


def _github_compare_path(reviewed_head: str, merge_head: str) -> str:
    if HEAD_RE.fullmatch(reviewed_head) is None or HEAD_RE.fullmatch(merge_head) is None:
        raise ValueError("GitHub comparison heads are invalid")
    base = f"/repos/{EXPECTED_REPOSITORY_FULL_NAME}/compare"
    return f"{base}/{reviewed_head}...{merge_head}?per_page=1&page=1"


def _github_associated_pulls_path(head: str, *, page: int) -> str:
    return associated_pulls_path(
        EXPECTED_REPOSITORY_FULL_NAME,
        head,
        page=page,
        page_size=GITHUB_PAGE_SIZE,
    )


def _github_pull_path(number: int) -> str:
    return pull_path(EXPECTED_REPOSITORY_FULL_NAME, number)


def _github_check_runs_path(head: str, *, page: int) -> str:
    return check_runs_path(
        EXPECTED_REPOSITORY_FULL_NAME,
        head,
        page=page,
        page_size=GITHUB_PAGE_SIZE,
    )


def _associated_pulls_projection(payload: Any, *, page: int) -> dict[str, Any]:
    return associated_pulls_projection(
        payload, page=page, projection_version=GITHUB_CAPTURE_PROJECTION_VERSION
    )


def _pull_projection(payload: Any) -> dict[str, Any]:
    return pull_projection(
        payload, projection_version=GITHUB_CAPTURE_PROJECTION_VERSION
    )


def _check_runs_projection(payload: Any, *, page: int) -> dict[str, Any]:
    return check_runs_projection(
        payload, page=page, projection_version=GITHUB_CAPTURE_PROJECTION_VERSION
    )


def _repo_projection(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("GitHub repository response is invalid")
    return {
        "projection_version": GITHUB_CAPTURE_PROJECTION_VERSION,
        "kind": "repository",
        "id": payload.get("id"),
        "full_name": payload.get("full_name"),
        "default_branch": payload.get("default_branch"),
        "archived": payload.get("archived"),
        "disabled": payload.get("disabled"),
    }


def _ruleset_inventory_projection(payload: Any, *, page: int) -> dict[str, Any]:
    if not isinstance(payload, list):
        raise ValueError("GitHub ruleset inventory response is invalid")
    items: list[dict[str, Any]] = []
    ids: set[int] = set()
    for item in payload:
        if not isinstance(item, dict) or not isinstance(item.get("id"), int):
            raise ValueError("GitHub ruleset inventory item is malformed")
        if item["id"] in ids:
            raise ValueError("GitHub ruleset inventory contains duplicate ids")
        ids.add(item["id"])
        items.append({
            "id": item.get("id"),
            "name": item.get("name"),
            "target": item.get("target"),
            "source_type": item.get("source_type"),
            "source": item.get("source"),
            "enforcement": item.get("enforcement"),
        })
    return {
        "projection_version": GITHUB_CAPTURE_PROJECTION_VERSION,
        "kind": "ruleset_inventory_page",
        "page": page,
        "items": sorted(items, key=lambda item: item["id"]),
    }


def _ref_projection(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict) or not isinstance(payload.get("object"), dict):
        raise ValueError("GitHub default-branch ref response is invalid")
    return {
        "projection_version": GITHUB_CAPTURE_PROJECTION_VERSION,
        "kind": "default_branch_ref",
        "ref": payload.get("ref"),
        "object_type": payload["object"].get("type"),
        "object_sha": payload["object"].get("sha"),
    }


def _normalize_required_checks(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ValueError("GitHub required checks are missing")
    checks: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict) or set(item) != {"context", "integration_id"}:
            raise ValueError("GitHub required checks are malformed")
        checks.append({
            "context": item.get("context"),
            "integration_id": item.get("integration_id"),
        })
    normalized = sorted(
        checks,
        key=lambda item: (str(item["context"]), int(item["integration_id"] or -1)),
    )
    if len({(item["context"], item["integration_id"]) for item in normalized}) != len(
        normalized
    ):
        raise ValueError("GitHub required checks contain duplicates")
    return normalized


def _normalize_rule_parameters(rule_type: str, parameters: Any) -> Any:
    if rule_type in {"deletion", "non_fast_forward"}:
        if parameters is not None:
            raise ValueError("GitHub denial rule unexpectedly has parameters")
        return None
    if not isinstance(parameters, dict):
        raise ValueError("GitHub ruleset parameters are missing")
    if rule_type == "pull_request":
        if set(parameters) != set(EXPECTED_PULL_REQUEST_PARAMETERS):
            raise ValueError("GitHub pull-request parameter surface drifted")
        normalized = dict(parameters)
        methods = normalized.get("allowed_merge_methods")
        if not isinstance(methods, list):
            raise ValueError("GitHub merge methods are malformed")
        normalized["allowed_merge_methods"] = sorted(methods)
        if not isinstance(normalized.get("required_reviewers"), list):
            raise ValueError("GitHub required reviewers are malformed")
        return normalized
    if rule_type == "required_status_checks":
        if set(parameters) != set(EXPECTED_REQUIRED_STATUS_CHECK_PARAMETERS):
            raise ValueError("GitHub status-check parameter surface drifted")
        normalized = dict(parameters)
        normalized["required_status_checks"] = _normalize_required_checks(
            parameters.get("required_status_checks")
        )
        return normalized
    raise ValueError("GitHub ruleset contains an unknown rule type")


def _normalize_rules(rules: Any) -> list[dict[str, Any]]:
    if not isinstance(rules, list):
        raise ValueError("GitHub ruleset rules are missing")
    allowed = {"deletion", "non_fast_forward", "pull_request", "required_status_checks"}
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for rule in rules:
        if not isinstance(rule, dict) or set(rule) - {"type", "parameters"}:
            raise ValueError("GitHub ruleset rule is malformed")
        rule_type = rule.get("type")
        if rule_type not in allowed or rule_type in seen:
            raise ValueError("GitHub ruleset contains unknown or duplicate rule types")
        seen.add(str(rule_type))
        parameters = _normalize_rule_parameters(
            str(rule_type), rule.get("parameters")
        )
        item: dict[str, Any] = {"type": rule_type}
        if parameters is not None:
            item["parameters"] = parameters
        normalized.append(item)
    if seen != allowed:
        raise ValueError("GitHub ruleset lacks required rule types")
    return sorted(normalized, key=lambda item: str(item["type"]))


def _expected_normalized_rules() -> list[dict[str, Any]]:
    return sorted(
        [
            {"type": "deletion"},
            {"type": "non_fast_forward"},
            {"type": "pull_request", "parameters": EXPECTED_PULL_REQUEST_PARAMETERS},
            {
                "type": "required_status_checks",
                "parameters": EXPECTED_REQUIRED_STATUS_CHECK_PARAMETERS,
            },
        ],
        key=lambda item: str(item["type"]),
    )


def _ruleset_projection(payload: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    if not isinstance(payload, dict):
        raise ValueError("GitHub ruleset response is invalid")
    normalized_rules = _normalize_rules(payload.get("rules"))
    by_type = {str(rule["type"]): rule for rule in normalized_rules}
    conditions = payload.get("conditions")
    ref_name = conditions.get("ref_name") if isinstance(conditions, dict) else None
    if not isinstance(ref_name, dict):
        raise ValueError("GitHub ruleset ref conditions are missing")
    pull = by_type["pull_request"]["parameters"]
    checks = by_type["required_status_checks"]["parameters"]
    attested_ruleset = {
        "ruleset_id": payload.get("id"),
        "name": payload.get("name"),
        "target": payload.get("target"),
        "enforcement": payload.get("enforcement"),
        "ref_includes": sorted(ref_name.get("include", [])),
        "ref_excludes": sorted(ref_name.get("exclude", [])),
        "pull_request_required": True,
        "required_approving_review_count": pull.get("required_approving_review_count"),
        "required_checks": checks["required_status_checks"],
        "strict_required_status_checks_policy": checks.get(
            "strict_required_status_checks_policy"
        ),
        "bypass_actors": payload.get("bypass_actors"),
        "current_user_can_bypass": payload.get("current_user_can_bypass"),
        "deletion_allowed": False,
        "non_fast_forward_allowed": False,
    }
    projection = {
        "projection_version": GITHUB_CAPTURE_PROJECTION_VERSION,
        "kind": "ruleset",
        "source_type": payload.get("source_type"),
        "source": payload.get("source"),
        "normalized_rules": normalized_rules,
        **attested_ruleset,
    }
    return projection, attested_ruleset


def _effective_rules_projection(payload: Any, *, page: int) -> dict[str, Any]:
    if not isinstance(payload, list):
        raise ValueError("GitHub effective-rules response is invalid")
    items: list[dict[str, Any]] = []
    seen: set[tuple[int, str]] = set()
    for rule in payload:
        if not isinstance(rule, dict) or set(rule) - {
            "type", "parameters", "ruleset_id", "ruleset_source_type",
            "ruleset_source",
        }:
            raise ValueError("GitHub effective rule is malformed")
        rule_type = str(rule.get("type", ""))
        ruleset_id = rule.get("ruleset_id")
        if not isinstance(ruleset_id, int) or (ruleset_id, rule_type) in seen:
            raise ValueError("GitHub effective rules contain duplicate identities")
        seen.add((ruleset_id, rule_type))
        parameters = _normalize_rule_parameters(rule_type, rule.get("parameters"))
        item = {
            "type": rule_type,
            "ruleset_id": ruleset_id,
            "ruleset_source_type": rule.get("ruleset_source_type"),
            "ruleset_source": rule.get("ruleset_source"),
        }
        if parameters is not None:
            item["parameters"] = parameters
        items.append(item)
    return {
        "projection_version": GITHUB_CAPTURE_PROJECTION_VERSION,
        "kind": "effective_rules_page",
        "page": page,
        "items": sorted(
            items, key=lambda item: (int(item["ruleset_id"]), str(item["type"]))
        ),
    }


def _commit_projection(payload: Any, *, requested_head: str) -> dict[str, Any]:
    if not isinstance(payload, dict) or not isinstance(payload.get("parents"), list):
        raise ValueError("GitHub commit response is invalid")
    parent_shas = [
        item.get("sha") for item in payload["parents"] if isinstance(item, dict)
    ]
    if len(parent_shas) != len(payload["parents"]) or any(
        HEAD_RE.fullmatch(str(value or "")) is None for value in parent_shas
    ):
        raise ValueError("GitHub commit parents are invalid")
    return {
        "projection_version": GITHUB_CAPTURE_PROJECTION_VERSION,
        "kind": "commit",
        "requested_head": requested_head,
        "sha": payload.get("sha"),
        "parent_shas": parent_shas,
    }


def _compare_projection(payload: Any) -> dict[str, Any]:
    if (
        not isinstance(payload, dict)
        or not isinstance(payload.get("base_commit"), dict)
        or not isinstance(payload.get("merge_base_commit"), dict)
    ):
        raise ValueError("GitHub comparison response is invalid")
    return {
        "projection_version": GITHUB_CAPTURE_PROJECTION_VERSION,
        "kind": "commit_comparison",
        "status": payload.get("status"),
        "ahead_by": payload.get("ahead_by"),
        "behind_by": payload.get("behind_by"),
        "total_commits": payload.get("total_commits"),
        "base_sha": payload["base_commit"].get("sha"),
        "merge_base_sha": payload["merge_base_commit"].get("sha"),
    }


class GitHubRulesetVerifier:
    """Compare packet attestation with current authenticated GitHub policy."""

    def __init__(
        self,
        token: bytes,
        *,
        now: datetime | None = None,
        transport: GitHubTransport | None = None,
    ) -> None:
        if len(token) < 8 or any(byte < 33 or byte > 126 for byte in token):
            raise ValueError("GitHub credential is invalid")
        self._token = token
        self._now = (now or _utc_now()).astimezone(timezone.utc)
        self._transport = transport or StdlibGitHubTransport()

    def _fetch_pages(
        self,
        path_builder: Callable[[int], str],
        projector: Callable[..., dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
        items: list[dict[str, Any]] = []
        projections: dict[str, dict[str, Any]] = {}
        for page in range(1, MAX_GITHUB_PAGES + 1):
            path = path_builder(page)
            payload = self._transport.get_json(path, self._token)
            if not isinstance(payload, list):
                raise ValueError("GitHub paginated response is invalid")
            projection = projector(payload, page=page)
            projections[GITHUB_API_ORIGIN + path] = projection
            items.extend(projection["items"])
            if len(payload) < GITHUB_PAGE_SIZE:
                return items, projections
        raise ValueError("GitHub pagination exceeds trusted-host page limit")

    def _fetch_check_pages(
        self, reviewed_head: str,
    ) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
        items: list[dict[str, Any]] = []
        projections: dict[str, dict[str, Any]] = {}
        expected_total: int | None = None
        for page in range(1, MAX_GITHUB_PAGES + 1):
            path = _github_check_runs_path(reviewed_head, page=page)
            payload = self._transport.get_json(path, self._token)
            projection = _check_runs_projection(payload, page=page)
            if expected_total is None:
                expected_total = projection["total_count"]
            elif projection["total_count"] != expected_total:
                raise ValueError("GitHub check-runs total_count drifted across pages")
            page_items = projection["items"]
            items.extend(page_items)
            projections[GITHUB_API_ORIGIN + path] = projection
            if len(page_items) < GITHUB_PAGE_SIZE:
                if len(items) != expected_total:
                    raise ValueError("GitHub check-runs pagination is incomplete")
                ids = [item["id"] for item in items]
                if len(ids) != len(set(ids)):
                    raise ValueError("GitHub check-runs pages contain duplicate ids")
                return items, projections
        raise ValueError("GitHub check-runs pagination exceeds trusted-host limit")

    def _verify(self, attestation: dict[str, Any]) -> None:
        if not isinstance(attestation, dict):
            raise ValueError("GitHub attestation is absent")
        observed = _instant(attestation.get("observed_at"))
        expires = _instant(attestation.get("expires_at"))
        if observed > self._now + MAX_CLOCK_SKEW:
            raise ValueError("GitHub attestation is future-dated")
        if self._now - observed > MAX_GITHUB_OBSERVATION_AGE or self._now >= expires:
            raise ValueError("GitHub attestation is stale")
        if expires - observed > MAX_GITHUB_VALIDITY:
            raise ValueError("GitHub attestation validity window is too broad")

        reviewed_head = str(attestation.get("reviewed_head", ""))
        merge_head = str(attestation.get("merge_head", ""))
        if HEAD_RE.fullmatch(reviewed_head) is None or HEAD_RE.fullmatch(merge_head) is None:
            raise ValueError("GitHub attestation heads are invalid")

        static_paths = _github_static_paths()
        repo_payload = self._transport.get_json(
            static_paths["repository"], self._token
        )
        inventory, inventory_projections = self._fetch_pages(
            _github_inventory_path, _ruleset_inventory_projection
        )
        ruleset_payload = self._transport.get_json(
            static_paths["ruleset_detail"], self._token
        )
        effective_rules, effective_projections = self._fetch_pages(
            _github_effective_rules_path, _effective_rules_projection
        )
        ref_payload = self._transport.get_json(
            static_paths["default_branch_ref"], self._token
        )
        repo = _repo_projection(repo_payload)
        ruleset_projection, ruleset = _ruleset_projection(ruleset_payload)
        ref = _ref_projection(ref_payload)

        commit_projections: dict[str, dict[str, Any]] = {}
        for head in dict.fromkeys((reviewed_head, merge_head)):
            path = _github_commit_path(head)
            payload = self._transport.get_json(path, self._token)
            commit_projections[GITHUB_API_ORIGIN + path] = _commit_projection(
                payload, requested_head=head
            )
        compare_path = _github_compare_path(reviewed_head, merge_head)
        comparison = _compare_projection(
            self._transport.get_json(compare_path, self._token)
        )
        associated_pulls, pull_inventory_projections = self._fetch_pages(
            lambda page: _github_associated_pulls_path(reviewed_head, page=page),
            _associated_pulls_projection,
        )
        inventory_pull = select_merged_pull(
            associated_pulls,
            reviewed_head=reviewed_head,
            merge_head=merge_head,
            repository_id=EXPECTED_REPOSITORY_ID,
            repository_name=EXPECTED_REPOSITORY_FULL_NAME,
            default_branch=EXPECTED_DEFAULT_BRANCH,
        )
        pull_path_value = _github_pull_path(inventory_pull["number"])
        pull = _pull_projection(
            self._transport.get_json(pull_path_value, self._token)
        )
        check_runs, check_projections = self._fetch_check_pages(reviewed_head)

        expected_repo = {
            "repository_id": EXPECTED_REPOSITORY_ID,
            "full_name": EXPECTED_REPOSITORY_FULL_NAME,
            "default_branch": EXPECTED_DEFAULT_BRANCH,
        }
        if attestation.get("repository") != expected_repo:
            raise ValueError("GitHub attestation repository identity mismatch")
        if repo != {
            "projection_version": GITHUB_CAPTURE_PROJECTION_VERSION,
            "kind": "repository",
            "id": EXPECTED_REPOSITORY_ID,
            "full_name": EXPECTED_REPOSITORY_FULL_NAME,
            "default_branch": EXPECTED_DEFAULT_BRANCH,
            "archived": False,
            "disabled": False,
        }:
            raise ValueError("live GitHub repository state is ineligible")
        expected_inventory = [{
            "id": EXPECTED_RULESET_ID,
            "name": EXPECTED_RULESET_NAME,
            "target": "branch",
            "source_type": "Repository",
            "source": EXPECTED_REPOSITORY_FULL_NAME,
            "enforcement": "active",
        }]
        if inventory != expected_inventory:
            raise ValueError("live GitHub ruleset inventory drifted")
        expected_ruleset = {
            "ruleset_id": EXPECTED_RULESET_ID,
            "name": EXPECTED_RULESET_NAME,
            "target": "branch",
            "enforcement": "active",
            "ref_includes": ["~DEFAULT_BRANCH"],
            "ref_excludes": [],
            "pull_request_required": True,
            "required_approving_review_count": 0,
            "required_checks": list(EXPECTED_REQUIRED_CHECKS),
            "strict_required_status_checks_policy": True,
            "bypass_actors": [],
            "current_user_can_bypass": "never",
            "deletion_allowed": False,
            "non_fast_forward_allowed": False,
        }
        if ruleset != expected_ruleset or attestation.get("ruleset") != expected_ruleset:
            raise ValueError("live GitHub ruleset policy mismatch")
        if ruleset_projection.get("source_type") != "Repository" or (
            ruleset_projection.get("source") != EXPECTED_REPOSITORY_FULL_NAME
        ):
            raise ValueError("live GitHub ruleset source is invalid")
        if ruleset_projection.get("normalized_rules") != _expected_normalized_rules():
            raise ValueError("live GitHub ruleset parameter policy drifted")
        expected_effective_rules = []
        for rule in _expected_normalized_rules():
            item = {
                "type": rule["type"],
                "ruleset_id": EXPECTED_RULESET_ID,
                "ruleset_source_type": "Repository",
                "ruleset_source": EXPECTED_REPOSITORY_FULL_NAME,
            }
            if "parameters" in rule:
                item["parameters"] = rule["parameters"]
            expected_effective_rules.append(item)
        expected_effective_rules.sort(
            key=lambda item: (int(item["ruleset_id"]), str(item["type"]))
        )
        if effective_rules != expected_effective_rules:
            raise ValueError("live GitHub effective branch rules drifted")
        expected_ref = f"refs/heads/{EXPECTED_DEFAULT_BRANCH}"
        if ref.get("ref") != expected_ref or ref.get("object_type") != "commit":
            raise ValueError("live GitHub default-branch ref is invalid")
        if ref.get("object_sha") != merge_head:
            raise ValueError("live GitHub default branch differs from merge_head")
        if any(
            projection.get("sha") != projection.get("requested_head")
            for projection in commit_projections.values()
        ):
            raise ValueError("live GitHub commit identity mismatch")
        expected_status = "identical" if reviewed_head == merge_head else "ahead"
        if (
            comparison.get("status") != expected_status
            or comparison.get("base_sha") != reviewed_head
            or comparison.get("merge_base_sha") != reviewed_head
            or comparison.get("behind_by") != 0
            or not isinstance(comparison.get("ahead_by"), int)
            or not isinstance(comparison.get("total_commits"), int)
            or comparison["ahead_by"] != comparison["total_commits"]
            or (reviewed_head == merge_head and comparison["ahead_by"] != 0)
            or (reviewed_head != merge_head and comparison["ahead_by"] < 1)
        ):
            raise ValueError("live GitHub reviewed/merge ancestry is invalid")
        merge_projection = commit_projections[
            GITHUB_API_ORIGIN + _github_commit_path(merge_head)
        ]
        verify_merged_pull_gate_outcomes(
            inventory_pull=inventory_pull,
            pull=pull,
            check_runs=check_runs,
            reviewed_head=reviewed_head,
            merge_head=merge_head,
            merge_parent_shas=merge_projection["parent_shas"],
            required_checks=EXPECTED_REQUIRED_CHECKS,
            observed_at=observed,
            now=self._now,
        )

        projections = {
            GITHUB_API_ORIGIN + static_paths["repository"]: repo,
            **inventory_projections,
            GITHUB_API_ORIGIN + static_paths["ruleset_detail"]: ruleset_projection,
            **effective_projections,
            GITHUB_API_ORIGIN + static_paths["default_branch_ref"]: ref,
            **commit_projections,
            GITHUB_API_ORIGIN + compare_path: comparison,
            **pull_inventory_projections,
            GITHUB_API_ORIGIN + pull_path_value: pull,
            **check_projections,
        }
        captures = attestation.get("evidence_captures")
        if not isinstance(captures, list) or len(captures) != len(projections):
            raise ValueError("GitHub evidence capture inventory mismatch")
        seen: set[str] = set()
        for capture in captures:
            if not isinstance(capture, dict) or set(capture) != {
                "url", "response_digest", "captured_at"
            }:
                raise ValueError("GitHub evidence capture is malformed")
            url = capture.get("url")
            if url in seen or url not in projections:
                raise ValueError("GitHub evidence capture URL inventory mismatch")
            seen.add(str(url))
            if capture.get("response_digest") != canonical_digest(projections[str(url)]):
                raise ValueError("GitHub evidence capture projection digest mismatch")
            captured = _instant(capture.get("captured_at"))
            if captured > observed or observed - captured > MAX_CLOCK_SKEW:
                raise ValueError("GitHub evidence capture time mismatch")
        if seen != set(projections):
            raise ValueError("GitHub evidence capture inventory is incomplete")

    def __call__(self, attestation: dict[str, Any]) -> bool:
        try:
            self._verify(attestation)
            return True
        except (KeyError, TypeError, UnicodeError, ValueError):
            return False
