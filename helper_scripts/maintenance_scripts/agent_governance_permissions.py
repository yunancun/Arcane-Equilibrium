"""Read-only command policy Implementation for the Development-Agent Governance Module."""

from __future__ import annotations

import json
import re
import shlex
from pathlib import Path, PurePosixPath
from typing import Any

from agent_governance_registry import native_agent_contract


REPO_ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = REPO_ROOT / ".codex/agent_registry_v1.json"
LOCAL_READONLY_COMMAND_RE = re.compile(
    r"^(?:"
    r"git\s+(?:status|diff|log|show|rev-parse|ls-files|branch\s+--show-current)\b|"
    r"rg\b|grep\b|head\b|tail\b|wc\b|ls\b|find\b|stat\b|"
    r"python3?\s+-m\s+pytest\b|pytest\b|cargo\s+(?:test|check|clippy)\b|cargo\s+fmt\s+--check\b|"
    r"node\s+--check\b|bash\s+-n\b"
    r")",
    re.IGNORECASE,
)
REMOTE_READONLY_COMMAND_RE = re.compile(
    r"^(?:"
    r"systemctl\s+--user\s+(?:show|is-active)\b|"
    r"ps\b|pgrep\b|ls\b|stat\b|cat\b|tail\b|fuser\b|"
    r"crontab\s+-l\b|curl\b|git\s+(?:status|diff|log|show|rev-parse)\b"
    r")",
    re.IGNORECASE,
)
SAFE_SYSTEMD_PROPERTIES = {
    "ActiveEnterTimestamp", "ActiveState", "ExecMainCode", "ExecMainStartTimestamp",
    "ExecMainStatus", "FragmentPath", "LoadState", "MainPID", "NRestarts",
    "Result", "SubState", "UnitFileState",
}
SENSITIVE_PATH_RE = re.compile(
    r"(?:^|[/\\])(?:\.ssh|\.aws|\.gnupg|\.netrc)(?:[/\\]|$)|"
    r"(?:id_rsa|id_ed25519|keychain|authorization\.json|credential|private[_-]?key)",
    re.IGNORECASE,
)
ASCII_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")


def _shell_tokens(value: str) -> list[str]:
    try:
        lexer = shlex.shlex(value, posix=True, punctuation_chars=True)
        lexer.whitespace_split = True
        return list(lexer)
    except ValueError:
        return ["<parse-error>"]


def _path_scope_error(tokens: list[str], *, remote: bool) -> str | None:
    for token in tokens[1:]:
        candidates = [token]
        if token.startswith("@"):
            candidates.append(token[1:])
        if "=" in token:
            candidates.append(token.split("=", 1)[1])
        for candidate in candidates:
            candidate = candidate.split("::", 1)[0]
            if not candidate or candidate.startswith("-") or "://" in candidate:
                continue
            if SENSITIVE_PATH_RE.search(candidate):
                return f"sensitive path is outside reviewer scope: {candidate}"
            pathish = candidate.startswith(("/", "~", ".")) or "/" in candidate or "\\" in candidate
            if not pathish:
                continue
            if candidate.startswith("~") or ".." in Path(candidate).parts:
                return f"home expansion or parent traversal is forbidden: {candidate}"
            if remote:
                if not candidate.startswith("/"):
                    continue
                allowed_remote = (
                    "/home/ncyu/BybitOpenClaw/srv",
                    "/home/ncyu/BybitOpenClaw/var/openclaw",
                    "/tmp/openclaw",
                )
                remote_path = PurePosixPath(candidate)
                if any(
                    remote_path == PurePosixPath(root)
                    or PurePosixPath(root) in remote_path.parents
                    for root in allowed_remote
                ) or re.fullmatch(r"/proc/\d+/exe", candidate):
                    continue
                return f"remote path is outside declared evidence roots: {candidate}"
            probe = candidate
            for marker in ("*", "?", "["):
                probe = probe.split(marker, 1)[0]
            resolved = (
                (REPO_ROOT / probe).resolve(strict=False)
                if not Path(probe).is_absolute()
                else Path(probe).resolve(strict=False)
            )
            try:
                resolved.relative_to(REPO_ROOT.resolve())
            except ValueError:
                return f"local path is outside repository root: {candidate}"
    return None


def _health_curl_allowed(tokens: list[str]) -> bool:
    allowed_flags = {"--fail", "-f", "--silent", "-s", "--show-error", "-S"}
    timed_flags = {"--max-time", "--connect-timeout"}
    urls: list[str] = []
    index = 1
    while index < len(tokens):
        token = tokens[index]
        if token in allowed_flags:
            index += 1
        elif token in timed_flags:
            if index + 1 >= len(tokens) or not re.fullmatch(r"\d+(?:\.\d+)?", tokens[index + 1]):
                return False
            index += 2
        elif token.startswith(("http://", "https://")):
            urls.append(token)
            index += 1
        else:
            return False
    return len(urls) == 1 and bool(
        re.fullmatch(
            r"https?://(?:localhost|127\.0\.0\.1)(?::8000)?/api/v1/health(?:\?[^\s]*)?",
            urls[0],
            re.IGNORECASE,
        )
    )


def _safe_systemctl_allowed(tokens: list[str]) -> bool:
    if len(tokens) < 4 or tokens[:2] != ["systemctl", "--user"]:
        return False
    action, service = tokens[2], tokens[3]
    if not re.fullmatch(r"openclaw-[A-Za-z0-9_.@-]+\.service", service):
        return False
    if action == "is-active":
        return len(tokens) == 4
    if action != "show":
        return False
    properties: set[str] = set()
    index = 4
    while index < len(tokens):
        token = tokens[index]
        if token in {"--no-pager", "--value"}:
            index += 1
            continue
        if token == "--property" and index + 1 < len(tokens):
            properties.update(tokens[index + 1].split(","))
            index += 2
            continue
        if token.startswith("--property="):
            properties.update(token.split("=", 1)[1].split(","))
            index += 1
            continue
        return False
    return bool(properties) and properties <= SAFE_SYSTEMD_PROPERTIES


def _safe_process_probe_allowed(tokens: list[str]) -> bool:
    if tokens == ["ps", "-eo", "pid,ppid,stat,etime,comm"]:
        return True
    if len(tokens) == 5 and tokens[0:2] == ["ps", "-p"] and tokens[2].isdigit():
        return tokens[3:] == ["-o", "pid,ppid,stat,etime,comm"]
    if len(tokens) == 3 and tokens[0:2] == ["pgrep", "-x"]:
        return re.fullmatch(r"[A-Za-z0-9_.-]+", tokens[2]) is not None
    return False



def _safe_pytest_allowed(tokens: list[str]) -> bool:
    if tokens[:3] in (["python", "-m", "pytest"], ["python3", "-m", "pytest"]):
        arguments = tokens[3:]
    elif tokens and tokens[0].lower() == "pytest":
        arguments = tokens[1:]
    else:
        return False
    no_value_flags = {
        "-q", "-v", "-vv", "-s", "-x", "--exitfirst", "--collect-only",
        "--disable-warnings", "--strict-config", "--strict-markers",
        "--no-header", "--no-summary",
    }
    value_flags = {"-k", "-m", "--tb", "--capture", "--color", "--durations", "--maxfail"}
    index = 0
    while index < len(arguments):
        token = arguments[index]
        if token in no_value_flags:
            index += 1
            continue
        if token in value_flags:
            if index + 1 >= len(arguments) or arguments[index + 1].startswith("-"):
                return False
            index += 2
            continue
        if any(token.startswith(flag + "=") for flag in value_flags if flag.startswith("--")):
            index += 1
            continue
        if token.startswith("-"):
            return False
        index += 1
    return True


def authorize_command(
    role_id: str,
    command: str,
    registry: dict[str, Any] | None = None,
    *,
    node_class: str | None = None,
    effective_permission: str | None = None,
) -> dict[str, Any]:
    """Conservatively preflight Bash for a read-only role preset."""

    registry = registry or json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    if role_id not in registry["roles"]:
        return {"allowed": False, "policy_class": "invalid", "reason": f"unknown role {role_id}"}
    spec = registry["roles"][role_id]
    declared_permission = spec["permission"]
    writer_verification = node_class == "verification" and declared_permission != "read_only"
    if node_class == "verification" and effective_permission not in {None, "read_only"}:
        return {"allowed": False, "policy_class": "invalid", "reason": "verification nodes require effective_permission=read_only"}
    if node_class == "work" and (
        declared_permission == "read_only"
        or effective_permission not in {None, declared_permission}
    ):
        return {"allowed": False, "policy_class": "invalid", "reason": "work node effective_permission must equal its Registry writer permission"}
    if node_class not in {None, "work", "verification"}:
        return {"allowed": False, "policy_class": "invalid", "reason": "node_class must be work or verification"}
    local_test_executor = node_class == "work" and role_id == "E4" and declared_permission == "test_writer"
    if declared_permission != "read_only" and not local_test_executor and not writer_verification:
        return {
            "allowed": False,
            "policy_class": "scoped_write",
            "reason": "writer/orchestrator commands require task scope or a deterministic effect Adapter",
        }
    if ASCII_CONTROL_RE.search(command):
        return {
            "allowed": False,
            "policy_class": "read_only",
            "reason": "ASCII control characters are forbidden in preflighted commands",
        }
    stripped = command.strip()
    lowered = stripped.lower()
    outer_tokens = _shell_tokens(stripped)
    if "<parse-error>" in outer_tokens or any(
        token in {";", "&&", "||", "|", "&", "$", "(", ")", "`"}
        for token in outer_tokens
    ):
        return {
            "allowed": False,
            "policy_class": "read_only",
            "reason": "shell composition or command substitution is forbidden; run one preflighted command at a time",
        }
    deny_patterns = {
        "shell redirection writes are forbidden": r"(?:^|[^<])>{1,2}",
        "git mutation is forbidden": r"\bgit\s+(?:add|commit|push|pull|fetch|merge|rebase|reset|checkout|switch|clean|stash|tag)\b",
        "filesystem mutation is forbidden": r"(?:^|[;&|]\s*)(?:rm|mv|cp|mkdir|touch|chmod|chown|ln)\b|\bsed\s+-i\b|\bperl\s+-[^\s]*i",
        "runtime mutation is forbidden": r"\bsystemctl(?:\s+--user)?\s+(?:start|stop|restart|reload|enable|disable|mask|unmask)\b|\bservice\s+\S+\s+(?:start|stop|restart)\b",
        "database mutation is forbidden": r"\b(?:insert|update|delete|alter|drop|create|truncate|grant|revoke|vacuum|reindex|copy)\b",
        "raw network clients are forbidden for reviewers": r"\b(?:wget|nc|netcat|socat)\b",
        "secret-bearing path is forbidden": r"(?:\.env\b|\.ssh\b|\.aws\b|\.gnupg\b|\.netrc\b|authorization\.json|secret|credential|token_file|id_rsa|id_ed25519|private[_-]?key)",
        "Linux cargo is forbidden": r"^ssh\s+trade-core\b.*\bcargo\s+(?:build|test|check|clippy|run)\b",
        "find execution or write actions are forbidden": r"\bfind\b.*\s-(?:delete|exec|execdir|ok|okdir|fprint|fprintf|fls)\b",
        "ripgrep preprocessors are forbidden": r"\brg\b.*\s--pre(?:\s|=|-glob\b)",
        "command output files are forbidden": r"\bgit\b.*\s--output(?:\s|=)",
        "journal mutation is forbidden": r"\bjournalctl\b.*\s--(?:rotate|sync|flush|relinquish-var|vacuum-[a-z-]+)(?:\s|=|['\"]|$)",
        "fuser kill mode is forbidden": r"\bfuser\b.*(?:^|\s)-[^\s]*k",
        "sed write commands are forbidden": r"\bsed\s+-n\b.*(?:^|[^a-z])w(?:\s|$)",
    }
    for reason, pattern in deny_patterns.items():
        if re.search(pattern, lowered, re.IGNORECASE):
            return {"allowed": False, "policy_class": "read_only", "reason": reason}

    local_path_error = _path_scope_error(outer_tokens, remote=False)
    if local_path_error:
        return {"allowed": False, "policy_class": "repo_read", "reason": local_path_error}

    governance_path = "helper_scripts/maintenance_scripts/agent_governance.py"
    if len(outer_tokens) >= 3 and outer_tokens[0] in {"python", "python3"} and outer_tokens[1] == governance_path:
        action = outer_tokens[2]
        read_actions = {
            "validate", "route", "context", "closure", "project-closure",
            "closure-quality", "authority", "evidence-key", "authorize-command",
        }
        if action == "render" and outer_tokens[3:] == ["--check"]:
            return {"allowed": True, "policy_class": "governance_readonly", "reason": "generated-view drift check is read-only"}
        if action in read_actions:
            return {"allowed": True, "policy_class": "governance_readonly", "reason": "declared governance compiler/validator command"}
        return {"allowed": False, "policy_class": "governance_readonly", "reason": "governance render is mutating unless invoked exactly with --check"}

    remote = re.fullmatch(r"ssh\s+trade-core\s+(['\"])(.*)\1", stripped, re.DOTALL | re.IGNORECASE)
    if remote:
        if local_test_executor or writer_verification:
            return {
                "allowed": False,
                "policy_class": "local_test_adapter",
                "reason": "E4 test execution is local-only; runtime probes require a read-only role",
            }
        inner = remote.group(2).strip()
        inner_tokens = _shell_tokens(inner)
        if "<parse-error>" in inner_tokens or any(
            token in {";", "&&", "||", "|", "&", "$", "(", ")", "`"}
            for token in inner_tokens
        ):
            return {"allowed": False, "policy_class": "linux_readonly_probe", "reason": "remote shell composition or command substitution is forbidden"}
        path_error = _path_scope_error(inner_tokens, remote=True)
        if path_error:
            return {"allowed": False, "policy_class": "linux_readonly_probe", "reason": path_error}
        if not REMOTE_READONLY_COMMAND_RE.match(inner):
            return {"allowed": False, "policy_class": "linux_readonly_probe", "reason": "remote command is outside the read-only allowlist"}
        if inner_tokens and inner_tokens[0].lower() == "systemctl" and not _safe_systemctl_allowed(inner_tokens):
            return {"allowed": False, "policy_class": "linux_readonly_probe", "reason": "systemctl is limited to safe properties or is-active for declared OpenClaw units"}
        if inner_tokens and inner_tokens[0].lower() in {"ps", "pgrep"} and not _safe_process_probe_allowed(inner_tokens):
            return {"allowed": False, "policy_class": "linux_readonly_probe", "reason": "process probes may expose only pid/state/etime/comm, never argv or environment"}
        if inner_tokens and inner_tokens[0].lower() == "psql":
            return {
                "allowed": False,
                "policy_class": "linux_readonly_probe",
                "reason": "direct psql is disabled until a local-socket/read-only-identity Adapter removes ambient psqlrc and PG* routing",
            }
        if inner_tokens and inner_tokens[0].lower() == "curl":
            if role_id not in {"OPS", "QA"} or not _health_curl_allowed(inner_tokens):
                return {"allowed": False, "policy_class": "linux_readonly_probe", "reason": "curl is limited to one unauthenticated localhost health GET with no output/effect flags"}
        return {"allowed": True, "policy_class": "linux_readonly_probe", "reason": "declared read-only remote probe"}
    if outer_tokens and (
        outer_tokens[0].lower() == "pytest"
        or outer_tokens[:3] in (["python", "-m", "pytest"], ["python3", "-m", "pytest"])
    ) and not _safe_pytest_allowed(outer_tokens):
        return {
            "allowed": False,
            "policy_class": "repo_or_local_test_read",
            "reason": "pytest flags are limited to non-persistent selection/display controls",
        }
    if local_test_executor:
        safe_test = bool(
            outer_tokens
            and (
                outer_tokens[0].lower() == "pytest"
                or outer_tokens[:3] in (
                    ["python", "-m", "pytest"],
                    ["python3", "-m", "pytest"],
                )
                or outer_tokens[:2] in (
                    ["cargo", "test"], ["cargo", "check"],
                    ["cargo", "clippy"], ["node", "--check"],
                    ["bash", "-n"],
                )
                or outer_tokens[:3] == ["cargo", "fmt", "--check"]
            )
        )
        if safe_test and LOCAL_READONLY_COMMAND_RE.match(stripped):
            return {
                "allowed": True,
                "policy_class": "local_test_adapter",
                "reason": "E4 local test Adapter command",
            }
        return {
            "allowed": False,
            "policy_class": "local_test_adapter",
            "reason": "E4 is limited to conservative local test/check commands",
        }
    if LOCAL_READONLY_COMMAND_RE.match(stripped):
        if writer_verification:
            return {
                "allowed": True,
                "policy_class": "node_scoped_read_only",
                "reason": (
                    "Registry-bound native verification adapter is read-only"
                    if effective_permission == "read_only"
                    else "Registry verification node is read-only"
                ),
            }
        return {
            "allowed": True,
            "policy_class": "repo_or_local_test_read",
            "reason": "declared local read/test command",
        }
    return {
        "allowed": False,
        "policy_class": "read_only",
        "reason": "command is outside the conservative read-only allowlist",
    }


def authorize_native_command(
    native_agent: str,
    command: str,
    registry: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Preflight using one exact Registry-owned native identity."""

    registry = registry or json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    try:
        contract = native_agent_contract(native_agent, registry)
    except ValueError as error:
        return {
            "allowed": False,
            "policy_class": "invalid_native_identity",
            "reason": str(error),
            "native_agent": native_agent,
        }
    decision = authorize_command(
        contract["role_id"], command, registry,
        node_class=contract["node_class"],
        effective_permission=contract["permission"],
    )
    return {
        **decision,
        "native_agent": contract["native_agent"],
        "role_id": contract["role_id"],
        "node_class": contract["node_class"],
        "effective_permission": contract["permission"],
    }
