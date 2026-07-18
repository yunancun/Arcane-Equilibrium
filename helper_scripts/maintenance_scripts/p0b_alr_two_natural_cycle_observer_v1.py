#!/usr/bin/python3
"""Fail-closed proof of two natural post-recovery ALR cycles.

Production has no configurable trust root.  The only approved invocation is
``/usr/bin/python3 -I -B`` followed by this exact Linux path.  The observer
performs fixed-file, OS-process, and one PostgreSQL read-only transaction
attestations.  It has no mutation, broker, order, lease, serving, or promotion
surface.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import importlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shlex
import stat
import sys
import types
from typing import Any, Callable, Mapping, Sequence


SCHEMA = "p0b_alr_two_natural_cycle_observer_v1"
TARGET_HEAD = "275901baa09656e842f14b11e94c00f9bfe0c380"
DECISION_CODE = "NO_QUALIFIED_CANDIDATE_ROTATE_RESEARCH_DIRECTION"
UNIT_NAME = "openclaw-alr-shadow.service"
EXPECTED_UID = 1000
EXPECTED_GID = 1000

OBSERVER_PATH = Path(
    "/home/ncyu/BybitOpenClaw/srv/target/codex-context/"
    "p0b_alr_two_natural_cycle_observer_v1.py"
)
APPLY_RECEIPT_PATH = Path(
    "/home/ncyu/BybitOpenClaw/srv/target/codex-context/"
    "p0b-alr-recovery-apply-receipt.json"
)
APPLY_RECEIPT_SHA256 = (
    "59188a5c8325917fcd1fa62f44e9884f716a7c5a2a8bb42ef253fa4f9dc4c97f"
)
RECOVERY_V2_PATH = Path(
    "/home/ncyu/BybitOpenClaw/srv/target/codex-context/"
    "p0b_alr_recovery_transaction_v2.py"
)
RECOVERY_V2_SHA256 = (
    "e78186edfd2c7b9c21d6c8a3f54ebc5b712da34dbe8c0f29d3c0e9a48f96c385"
)
RECOVERY_REPO_PATH = Path("/home/ncyu/BybitOpenClaw/srv")
RECOVERY_GIT_DIR_PATH = RECOVERY_REPO_PATH / ".git"
RECOVERY_GIT_INFO_EXCLUDE_PATH = RECOVERY_GIT_DIR_PATH / "info/exclude"
RECOVERY_GIT_INFO_EXCLUDE_SHA256 = (
    "6671fe83b7a07c8932ee89164d1f2793b2318058eb8b98dc5c06ee0a5a3b0ec1"
)
RECOVERY_GIT_INFO_EXCLUDE_SIZE = 240
RECOVERY_GIT_INDEX_PATH = RECOVERY_GIT_DIR_PATH / "index"
RECOVERY_GIT_INDEX_SHA256 = (
    "aebb5d0ec5d7cf733b79d92159a13a5d45eadc0f77cc039e8068307ca9d5eb2e"
)
RECOVERY_GIT_INDEX_SIZE = 1_322_183
RECOVERY_GIT_INDEX_RECORD_COUNT = 8_764
RECOVERY_GIT_INFO_ATTRIBUTES_PATH = RECOVERY_GIT_DIR_PATH / "info/attributes"
RECOVERY_REPO_DIRECTORY_EXPECTED = {
    "dev": 66_312,
    "ino": 60_430_267,
    "uid": 1000,
    "gid": 1000,
    "mode": 0o775,
    "nlink": 21,
}
RECOVERY_GIT_DIRECTORY_EXPECTED = {
    "dev": 66_312,
    "ino": 60_430_269,
    "uid": 1000,
    "gid": 1000,
    "mode": 0o775,
    "nlink": 8,
}
RECOVERY_PASSWD_PATH = Path("/etc/passwd")
RECOVERY_PASSWD_SHA256 = (
    "81779fc70b66265217a7d7460986f0798ec55de9ba579e77aaf5c681050fed99"
)
RECOVERY_PASSWD_EXPECTED = {
    "dev": 66_312,
    "ino": 19_139_851,
    "uid": 0,
    "gid": 0,
    "mode": 0o644,
    "nlink": 1,
    "size": 3_100,
}
RECOVERY_GROUP_PATH = Path("/etc/group")
RECOVERY_GROUP_SHA256 = (
    "65c2c9f3dabf8e0889beac4091bf9b655abc01a2da26f78890c1b83fe49bef4e"
)
RECOVERY_GROUP_EXPECTED = {
    "dev": 66_312,
    "ino": 19_139_973,
    "uid": 0,
    "gid": 0,
    "mode": 0o644,
    "nlink": 1,
    "size": 1_183,
}
RECOVERY_BASE_SYSTEM_ENV = {
    "HOME": "/home/ncyu",
    "PATH": "/usr/local/bin:/usr/bin:/bin",
    "USER": "ncyu",
    "LOGNAME": "ncyu",
    "LANG": "C.UTF-8",
    "LC_ALL": "C.UTF-8",
    "XDG_RUNTIME_DIR": "/run/user/1000",
    "DBUS_SESSION_BUS_ADDRESS": "unix:path=/run/user/1000/bus",
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_TERMINAL_PROMPT": "0",
}
RECOVERY_HARDENED_GIT_ENV = {
    **RECOVERY_BASE_SYSTEM_ENV,
    "GIT_COMMON_DIR": str(RECOVERY_GIT_DIR_PATH),
    "GIT_OPTIONAL_LOCKS": "0",
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_CONFIG_SYSTEM": "/dev/null",
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_TRACE2": "0",
    "GIT_TRACE2_PERF": "0",
    "GIT_TRACE2_EVENT": "0",
    "GIT_ATTR_NOSYSTEM": "1",
    "GIT_NO_LAZY_FETCH": "1",
    "GIT_NO_REPLACE_OBJECTS": "1",
}
RECOVERY_GIT_COMMAND_PREFIX = (
    "/usr/bin/git",
    "--no-optional-locks",
    "-c",
    "core.fsmonitor=false",
    "-c",
    "core.untrackedCache=false",
    "-c",
    "trace2.normalTarget=0",
    "-c",
    "trace2.perfTarget=0",
    "-c",
    "trace2.eventTarget=0",
    "-c",
    "core.ignoreStat=false",
    "-c",
    "core.fileMode=true",
    "-c",
    "core.checkStat=default",
    "-c",
    "core.symlinks=true",
    "-c",
    "core.trustctime=true",
    "-c",
    "core.ignoreCase=false",
    "-c",
    "core.attributesFile=/dev/null",
    "-c",
    "core.excludesFile=/dev/null",
    f"--git-dir={RECOVERY_GIT_DIR_PATH}",
    f"--work-tree={RECOVERY_REPO_PATH}",
    "-C",
    str(RECOVERY_REPO_PATH),
)
RECOVERY_GIT_CONFIG_INVENTORY_ARGS = (
    "config",
    "--local",
    "--includes",
    "--null",
    "--name-only",
    "--list",
)
MAX_GIT_CONFIG_INVENTORY_BYTES = 128 * 1024
MAX_GIT_CONFIG_KEYS = 4096
MAX_GIT_CONFIG_KEY_BYTES = 1024
MAX_GIT_INDEX_INVENTORY_BYTES = 2 * 1024 * 1024
MAX_GIT_INDEX_PATH_BYTES = 4096
RECOVERY_GIT_STAGE_INVENTORY_SIZE = 1_166_201
BOARD_PATH = Path(
    "/home/ncyu/BybitOpenClaw/var/openclaw/cost_gate_learning_lane/"
    "blocked_outcome_review_20260717T122701Z.json"
)
BOARD_SOURCE_CONTENT_SHA256 = (
    "a6332c735378991f78ca573bc63134e7813cac98653dc6baefbb16f2d13ede50"
)
BOARD_HASH = "c1449c8d175061daa85f7d7c33a4e3de0ecd8c34752d01dd0ee49b6e81aa2d58"
BOARD_AUDIT_HASH = (
    "b4db289cad151216faf17d49f3c6010c634225c26ee007071312f7376002adba"
)
SELECTION_HASH = "fe9d97921a877a047d3ad275613f486e0fa246101616eca5e182517eb287a5bb"
CANDIDATE_SET_HASH = (
    "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945"
)
UNIT_PATH = Path("/home/ncyu/.config/systemd/user/openclaw-alr-shadow.service")
UNIT_SHA256 = "526fbcd67ca109668ec7ac7586b99e6b6393e6630bb741df71f4a935a1cc7518"
PIN_PATH = Path(
    "/home/ncyu/BybitOpenClaw/var/openclaw/runtime_generation/"
    "expected_source_head.json"
)
PIN_SHA256 = "74d3b05bc45402d762dfbdfb55844ca3fcf052850ea02d4803cee84ae5aff311"
PIN_DERIVED_AT_UTC = "2026-07-17T13:41:01Z"
POSTCHECK_PATH = Path(
    "/home/ncyu/BybitOpenClaw/srv/target/codex-context/"
    "p0b-independent-readonly-postapply-v1.json"
)
POSTCHECK_SHA256 = (
    "eef3abf5c478999eda4f5ca24806c50b500c64a984cfc64232d26f6e02864f12"
)
POSTCHECK_EVIDENCE_SHA256 = (
    "83b96a4c537826a41cfaa543ef4aaa89a585a70eb2f8c15ca24a4dece5e0ff20"
)
PROTECTED_SHA256 = (
    "a593931856dda06ff365e4e80d463d53491029cb3d226e7f0c615ab3c110e626"
)
DSN_PATH = Path("/home/ncyu/.config/openclaw/alr-shadow.dsn")
SINGLETON_LOCK_PATH = Path("/run/user/1000/alr-shadow/consumer.lock")
PROC_LOCKS_PATH = Path("/proc/locks")
PROC_ROOT = Path("/proc")

PRIVATE_DEPS_ROOT = Path(
    "/home/ncyu/BybitOpenClaw/var/openclaw/p0b-observer-deps"
)
PRIVATE_SITE_PACKAGES = PRIVATE_DEPS_ROOT / "site-packages"
PSYCOPG_PACKAGE_PATH = PRIVATE_SITE_PACKAGES / "psycopg2"
PSYCOPG_LIBS_PATH = PRIVATE_SITE_PACKAGES / "psycopg2_binary.libs"
PSYCOPG_PACKAGE_MANIFEST = {
    "__init__.py": "f66a3941dd2e587884071d82768806a2cda436ab6534d1b36ed625182d21592f",
    "_ipaddress.py": "8e4bb284b82a50644170b3560ccf10272b15eaad4da5cfd1607e3f904ec964f5",
    "_json.py": "5cf9f83e7cdb4e0d4372acfb9f524cbf974a841e55155ebcdf8184b7149ac2dd",
    "_psycopg.cpython-312-x86_64-linux-gnu.so": "df93d0caf76c1c457f400b1e3c73e46c3e444432c89a68f223b19bbd90562187",
    "_range.py": "b1779e9c6ada244130d88de673c46598d8afcb68cc83bcd6a1a9c37acd98c29f",
    "errorcodes.py": "f0113f6403fb6e1b0848ac8b3f4824ad683f34d8f5ba3dfb751df9e840deeb2a",
    "errors.py": "6804b8749c938356ec0f3243091400301fecef3bfe438c81e98be2876e88fb43",
    "extensions.py": "086d241b9bcbf0eb79d375069435d724915d1562e0e07136fdcd7e94b38b73c3",
    "extras.py": "a017eb76fb569fc213c5cdf1fa1da1e88c0752c59d56a09d7f81a985bd09a98f",
    "pool.py": "50612df0874fdf135cd8f1983651b8b10be0f2785fe1a7829f3dfd8534741fc2",
    "sql.py": "39c144026a5ed9a31faf1d0c124e0bc74d17bd75c90a6be595a3956c963eca81",
    "tz.py": "afde642bb7864a9398aff96e0b262cce71ccce3979dac2e3b2748f5e45cbcd12",
}
PSYCOPG_LIB_MANIFEST = {
    "libcom_err-2abe824b.so.2.1": "5426dcb54dd01c9eedda05e2179f0e47114e8b48a534ffe9e94916e79471b257",
    "libcrypt-13f4f5d0.so.1": "a74d1e8438d224e0fff14da0001f5e50129b0d666a103bf981b976770158d106",
    "libcrypto-88208852.so.3": "2fd37154b19333c0bee46ff24aaafab5c38f0b9aff4bedc107753b67f3161c80",
    "libgssapi_krb5-497db0c6.so.2.2": "2a74b0330ee973281b26f8ebe4acef0ebf9ee99c6b68497cf9151fff6c4c34e1",
    "libk5crypto-b1f99d5c.so.3.1": "9844e5009e70a6ad2fb22b587306810fe2a7b1b9f6b9922daa1c78ba3466de27",
    "libkeyutils-dfe70bd6.so.1.5": "c29e41b03cf4b2dffbfb4960946e2b42f82c0ca5d53d231d3f0fc597ba274488",
    "libkrb5-fcafa220.so.3.3": "b2aab528ff4cab2144e5ce01b246ac09f574a072a53ff63ea81d6bb29b26b8f1",
    "libkrb5support-d0bcff84.so.0.1": "6a71f57d748fef79b4e736d5348875545d0a224fa8928b5d62a3cf2647fc109f",
    "liblber-314cbfbf.so.2.0.200": "fdba45538f1d793a9902797c5f888b39e7a5e8b7bf5fe0447e01ab7f487c1bc7",
    "libldap-331dad9d.so.2.0.200": "c56191deb6b726bf408634f46522ea4e829087b85bba619ae250718d6ed9ffc6",
    "libpcre-9513aab5.so.1.2.0": "02eda850e04931656d8af81f5171bff74d8bec1553d3d85c3d32d7fc5efe8864",
    "libpq-f521cc7d.so.5.17": "c2870f74ba59a43550b515eb7044ec35e66d77674f65c7d784c2247966e1893f",
    "libsasl2-84219a89.so.3.0.0": "ae3f8967d5fa191dac7c6ae5f9130f659cf2f5cb66b2f7e5c5a1a5a47369fe5a",
    "libselinux-0922c95c.so.1": "d4fa8e7fb3add960a68325a59c9694244aea3213fd739a50815cb067c4965654",
    "libssl-fe1b61af.so.3": "2db83e4f393066674c90ebfdec7367ce707020931754a4bab2995d2ada377c43",
}
PSYCOPG_EXTENSION_NAME = "_psycopg.cpython-312-x86_64-linux-gnu.so"
PSYCOPG_VERSION_TOKEN = "2.9.12"
PG_APPLICATION_NAME = "p0b-alr-two-natural-cycle-observer-v1"
PG_OPTIONS = (
    "-csearch_path=pg_catalog -cstatement_timeout=15000 -clock_timeout=1000 "
    "-cidle_in_transaction_session_timeout=30000 "
    "-cdefault_transaction_read_only=on"
)

MAX_RECEIPT_BYTES = 64 * 1024
MAX_BOARD_BYTES = 64 * 1024
MAX_POSTCHECK_BYTES = 2 * 1024 * 1024
MAX_UNIT_BYTES = 16 * 1024
MAX_PIN_BYTES = 1024
MAX_DSN_BYTES = 16 * 1024
MAX_PROC_BYTES = 4 * 1024 * 1024
MAX_SOURCE_PAYLOAD_BYTES = 1024 * 1024
MAX_DECISION_PAYLOAD_BYTES = 256 * 1024
MAX_HEALTH_PAYLOAD_BYTES = 256 * 1024
MAX_DETAILS_BYTES = 16 * 1024
MAX_OUTPUT_BYTES = 256 * 1024
MAX_CYCLES = 256
MAX_EDGES = 4096
MAX_SOURCE_KEY_BYTES = 1024
MAX_SCAN_ID_BYTES = 256
MAX_TEXT_BYTES = 4096

HEX40_RE = re.compile(r"^[0-9a-f]{40}$")
HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
UTC_Z_RE = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?Z$"
)

FALSE_AUTHORITY = {
    "exchange_authority": False,
    "trading_authority": False,
    "order_or_probe_authority": False,
    "decision_lease_authority": False,
    "cost_gate_authority": False,
    "proof_authority": False,
    "serving_authority": False,
    "promotion_authority": False,
    "latest_authority": False,
}
ZERO_COUNTERS = {
    "exchange_contact_count": 0,
    "trading_action_count": 0,
    "order_or_probe_count": 0,
    "decision_lease_count": 0,
    "cost_gate_change_count": 0,
    "proof_claim_count": 0,
    "serving_or_promotion_count": 0,
}
HEALTH_ZERO_COUNTERS = {
    "run_authority_mismatch_count": 0,
    "feedback_authority_mismatch_count": 0,
    "exchange_contact_count": 0,
    "trading_action_count": 0,
    "order_or_probe_count": 0,
    "decision_lease_count": 0,
    "cost_gate_change_count": 0,
    "proof_claim_count": 0,
    "serving_promotion_count": 0,
    "latest_pointer_update_count": 0,
}
FALSE_CLAIMS = (
    "training_run_created",
    "model_training_performed",
    "serving_ready",
    "promotion_ready",
    "order_or_probe_created",
)
BOARD_AUDIT_FIELDS = (
    "lineage_partition_complete",
    "raw_blocked_outcome_row_count",
    "qualified_lineage_outcome_row_count",
    "unqualified_lineage_outcome_row_count",
    "invalid_lineage_outcome_row_count",
    "invalid_exact_cohort_row_count",
    "invalid_identity_family_row_count",
    "unassigned_invalid_lineage_outcome_row_count",
    "unqualified_raw_valid_evaluation_missing_row_count",
    "unqualified_event_outside_evaluation_window_row_count",
    "consistent_duplicate_event_hash_extra_row_count",
    "conflicting_duplicate_event_hash_row_count",
    "conflicting_duplicate_event_hash_attribution_row_count",
    "lineage_exclusion_reason_counts",
)


class ObserverIssue(RuntimeError):
    outcome = "UNVERIFIED"

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class ObserverUnverified(ObserverIssue):
    outcome = "UNVERIFIED"


class ObserverFail(ObserverIssue):
    outcome = "FAIL"


def canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ObserverFail("canonical_json_invalid") from exc


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _strict_json(raw: bytes, *, label: str) -> dict[str, Any]:
    def object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate_key")
            result[key] = value
        return result

    def reject_constant(value: str) -> None:
        raise ValueError(value)

    try:
        parsed = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=object_pairs,
            parse_constant=reject_constant,
        )
    except (UnicodeError, ValueError, json.JSONDecodeError) as exc:
        raise ObserverUnverified(f"{label}_json_invalid") from exc
    if not isinstance(parsed, dict):
        raise ObserverUnverified(f"{label}_not_mapping")
    return parsed


def _identity(stat_result: os.stat_result, digest: str | None = None) -> dict[str, Any]:
    result = {
        "dev": stat_result.st_dev,
        "ino": stat_result.st_ino,
        "uid": stat_result.st_uid,
        "gid": stat_result.st_gid,
        "mode": stat.S_IMODE(stat_result.st_mode),
        "nlink": stat_result.st_nlink,
        "size": stat_result.st_size,
        "mtime_ns": stat_result.st_mtime_ns,
        "ctime_ns": stat_result.st_ctime_ns,
    }
    if digest is not None:
        result["sha256"] = digest
    return result


def _read_bound_file(
    path: Path,
    expected_sha256: str,
    *,
    label: str,
    max_bytes: int,
    mode: int | None = None,
    uid: int | None = EXPECTED_UID,
    gid: int | None = EXPECTED_GID,
    require_nonempty: bool = False,
) -> tuple[bytes, dict[str, Any]]:
    if not HEX64_RE.fullmatch(expected_sha256):
        raise ObserverUnverified(f"{label}_expected_sha256_invalid")
    if getattr(os, "O_NOFOLLOW", None) is None:
        raise ObserverUnverified(f"{label}_secure_open_unavailable")
    try:
        before = path.lstat()
    except OSError as exc:
        raise ObserverUnverified(f"{label}_unavailable") from exc
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
        raise ObserverUnverified(f"{label}_not_regular")
    if (
        before.st_nlink != 1
        or before.st_size > max_bytes
        or (require_nonempty and before.st_size == 0)
        or (uid is not None and before.st_uid != uid)
        or (gid is not None and before.st_gid != gid)
        or (mode is not None and stat.S_IMODE(before.st_mode) != mode)
    ):
        raise ObserverUnverified(f"{label}_identity_invalid")
    flags = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise ObserverUnverified(f"{label}_open_failed") from exc
    try:
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_nlink != 1
            or (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino)
            or opened.st_size > max_bytes
            or (require_nonempty and opened.st_size == 0)
            or (uid is not None and opened.st_uid != uid)
            or (gid is not None and opened.st_gid != gid)
            or (mode is not None and stat.S_IMODE(opened.st_mode) != mode)
        ):
            raise ObserverUnverified(f"{label}_identity_changed")
        remaining = opened.st_size
        chunks: list[bytes] = []
        while remaining:
            chunk = os.read(descriptor, min(remaining, 1024 * 1024))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        final = os.fstat(descriptor)
        if _identity(final) != _identity(opened):
            raise ObserverUnverified(f"{label}_changed_during_read")
    finally:
        os.close(descriptor)
    raw = b"".join(chunks)
    digest = hashlib.sha256(raw).hexdigest()
    if len(raw) != opened.st_size or digest != expected_sha256:
        raise ObserverUnverified(f"{label}_sha256_mismatch")
    return raw, _identity(opened, digest)


def _read_proc_file(path: Path, *, label: str, max_bytes: int) -> bytes:
    if getattr(os, "O_NOFOLLOW", None) is None:
        raise ObserverUnverified(f"{label}_secure_open_unavailable")
    try:
        descriptor = os.open(
            path,
            os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0),
        )
    except OSError as exc:
        raise ObserverUnverified(f"{label}_unavailable") from exc
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode):
            raise ObserverUnverified(f"{label}_not_regular")
        result = bytearray()
        while True:
            chunk = os.read(descriptor, min(65536, max_bytes + 1 - len(result)))
            if not chunk:
                break
            result.extend(chunk)
            if len(result) > max_bytes:
                raise ObserverUnverified(f"{label}_too_large")
    finally:
        os.close(descriptor)
    return bytes(result)


def _mapping(value: Any, reason: str, *, unverified: bool = False) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        error = ObserverUnverified if unverified else ObserverFail
        raise error(reason)
    return value


def _exact_fields(value: Mapping[str, Any], expected: set[str], reason: str) -> None:
    if set(value) != expected:
        raise ObserverFail(reason)


def _parse_utc(value: Any, reason: str, *, unverified: bool = False) -> datetime:
    error = ObserverUnverified if unverified else ObserverFail
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise error(reason) from exc
    else:
        raise error(reason)
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise error(reason)
    return parsed.astimezone(timezone.utc)


def _utc_z(value: Any, reason: str) -> str:
    return _parse_utc(value, reason).isoformat().replace("+00:00", "Z")


def _utc_z_seconds(value: Any, reason: str) -> str:
    return _parse_utc(value, reason).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _hash(value: Any, reason: str, *, length: int = 64) -> str:
    matcher = HEX40_RE if length == 40 else HEX64_RE
    if not isinstance(value, str) or matcher.fullmatch(value) is None:
        raise ObserverFail(reason)
    return value


def _nonnegative(value: Any, reason: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ObserverFail(reason)
    return value


def _positive(value: Any, reason: str) -> int:
    result = _nonnegative(value, reason)
    if result == 0:
        raise ObserverFail(reason)
    return result


def _bounded_text(value: Any, max_bytes: int, reason: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value.encode("utf-8")) > max_bytes
    ):
        raise ObserverFail(reason)
    return value


def _require_no_authority(value: Any, reason: str) -> None:
    if value != FALSE_AUTHORITY:
        raise ObserverFail(reason)


def _require_zero_counters(value: Any, expected: Mapping[str, int], reason: str) -> None:
    if value != expected:
        raise ObserverFail(reason)


TX_START_SQL = (
    "SELECT pg_catalog.current_setting('transaction_read_only') AS transaction_read_only, "
    "pg_catalog.current_setting('transaction_isolation') AS transaction_isolation, "
    "pg_catalog.current_setting('search_path') AS search_path, "
    "pg_catalog.current_setting('statement_timeout') AS statement_timeout, "
    "pg_catalog.current_setting('lock_timeout') AS lock_timeout, "
    "pg_catalog.current_setting('idle_in_transaction_session_timeout') AS idle_timeout, "
    "CURRENT_USER AS current_user, pg_catalog.current_database() AS current_database, "
    "pg_catalog.inet_server_addr()::text AS server_addr, "
    "pg_catalog.inet_server_port() AS server_port, "
    "pg_catalog.pg_current_xact_id_if_assigned()::text AS txid_current_if_assigned"
)

OPEN_SESSION_SQL = (
    "WITH open_sessions AS ("
    "SELECT s.session_id, s.event_id AS start_event_id, s.recorded_at AS started_at "
    "FROM learning.alr_consumer_events AS s "
    "WHERE s.event_kind = 'SESSION_STARTED' AND NOT EXISTS ("
    "SELECT 1 FROM learning.alr_consumer_events AS terminal "
    "WHERE terminal.session_id = s.session_id AND terminal.event_kind IN ("
    "'SESSION_STOPPED','SESSION_FAILED','UNCLEAN_RECOVERY')) "
    "ORDER BY s.recorded_at DESC, s.event_id DESC LIMIT 2) "
    "SELECT session_id,start_event_id,started_at FROM open_sessions"
)

CYCLES_SQL = (
    "SELECT lane.event_id AS lane_success_event_id,lane.session_id,"
    "lane.recorded_at AS lane_success_recorded_at,lane.source_ts,"
    "CASE WHEN pg_catalog.octet_length(lane.source_scan_id) <= 256 "
    "THEN lane.source_scan_id END AS lane_source_scan_id,"
    "pg_catalog.octet_length(lane.source_scan_id) AS lane_source_scan_id_bytes,"
    "lane.source_hash,pg_catalog.pg_column_size(lane.details) AS details_bytes,"
    "CASE WHEN pg_catalog.pg_column_size(lane.details) <= 16384 "
    "THEN lane.details END AS details,"
    "pg_catalog.jsonb_typeof(lane.details->'rows_seen') AS rows_seen_kind,"
    "pg_catalog.octet_length(lane.details->>'rows_seen') AS rows_seen_text_bytes,"
    "CASE WHEN pg_catalog.jsonb_typeof(lane.details->'rows_seen')='number' "
    "AND pg_catalog.octet_length(lane.details->>'rows_seen') BETWEEN 1 AND 18 "
    "AND (lane.details->>'rows_seen') ~ '^[0-9]+$' "
    "THEN (lane.details->>'rows_seen')::bigint END AS rows_seen_value,"
    "source.source_table,CASE WHEN pg_catalog.octet_length(source.source_key) <= 1024 "
    "THEN source.source_key END AS source_key,"
    "pg_catalog.octet_length(source.source_key) AS source_key_bytes,"
    "CASE WHEN pg_catalog.octet_length(source.source_scan_id) <= 256 "
    "THEN source.source_scan_id END AS source_scan_id,"
    "pg_catalog.octet_length(source.source_scan_id) AS source_scan_id_bytes,"
    "source.source_ts AS typed_source_ts,source.source_hash AS typed_source_hash,"
    "source.cycle_schema_version,source_artifact.artifact_kind AS source_artifact_kind,"
    "pg_catalog.pg_column_size(source_artifact.canonical_payload) AS source_payload_bytes,"
    "CASE WHEN pg_catalog.pg_column_size(source_artifact.canonical_payload) <= 1048576 "
    "THEN source_artifact.canonical_payload END AS source_canonical_payload,"
    "notification.event_id AS notification_event_id,"
    "notification.recorded_at AS notification_recorded_at,"
    "notification.notification_ts_ms "
    "FROM learning.alr_consumer_events AS lane "
    "LEFT JOIN learning.alr_source_events AS source ON "
    "source.source_table='trading.scanner_snapshots' "
    "AND source.source_ts=lane.source_ts "
    "AND source.source_scan_id=lane.source_scan_id "
    "AND source.source_hash=lane.source_hash "
    "LEFT JOIN learning.alr_artifact_nodes AS source_artifact ON "
    "source_artifact.artifact_hash=source.source_hash "
    "AND source_artifact.artifact_kind='scanner_cycle' "
    "JOIN LATERAL (SELECT consumed.event_id,consumed.recorded_at,"
    "consumed.notification_ts_ms FROM learning.alr_consumer_events AS consumed "
    "WHERE consumed.session_id=lane.session_id "
    "AND consumed.event_kind='NOTIFICATION_CONSUMED' "
    "AND consumed.recorded_at <= lane.recorded_at "
    "AND consumed.source_ts=lane.source_ts "
    "AND consumed.source_scan_id=lane.source_scan_id "
    "AND consumed.source_hash=lane.source_hash "
    "ORDER BY consumed.recorded_at DESC,consumed.event_id DESC LIMIT 1) "
    "AS notification ON TRUE "
    "WHERE lane.session_id=%s::uuid AND lane.event_kind='LANE_SUCCESS' "
    "AND lane.lane='FRESH' AND lane.recorded_at >= %s "
    "ORDER BY lane.source_ts DESC,lane.source_scan_id DESC,"
    "lane.event_id DESC LIMIT 257"
)

DECISION_SQL = (
    "SELECT artifact.artifact_hash,artifact.artifact_kind,artifact.created_at,"
    "pg_catalog.pg_column_size(artifact.canonical_payload) AS payload_bytes,"
    "CASE WHEN pg_catalog.pg_column_size(artifact.canonical_payload) <= 262144 "
    "THEN artifact.canonical_payload END AS canonical_payload "
    "FROM learning.alr_artifact_nodes AS artifact "
    "WHERE artifact.artifact_kind='target_rotation' "
    "AND artifact.canonical_payload->>'schema_version'="
    "'alr_candidate_learning_projection_artifact_v2' "
    "AND artifact.canonical_payload#>>'{decision,source_head}'=%s "
    "AND artifact.canonical_payload#>>'{decision,decision_code}'=%s "
    "AND artifact.canonical_payload#>>'{decision,evaluated_at}'=%s "
    "AND artifact.canonical_payload#>>'{source_refs,handoff,evidence,source_content_sha256}'=%s "
    "AND artifact.canonical_payload#>>'{source_refs,handoff,evidence,board_hash}'=%s "
    "AND artifact.canonical_payload#>>'{source_refs,handoff,evidence,audit_hash}'=%s "
    "AND artifact.canonical_payload#>>'{source_refs,handoff,evidence,selection_hash}'=%s "
    "AND artifact.canonical_payload#>>'{source_refs,handoff,evidence,candidate_set_hash}'=%s "
    "AND artifact.canonical_payload#>>'{source_refs,handoff,source_cursor,source_hash}'=%s "
    "AND artifact.canonical_payload#>>'{source_refs,handoff,source_cursor,source_key}'=%s "
    "AND artifact.canonical_payload#>>'{source_refs,handoff,source_cursor,source_ts}'=%s "
    "ORDER BY artifact.created_at,artifact.artifact_hash LIMIT 2"
)

EDGES_SQL = (
    "SELECT edge.edge_hash,edge.from_artifact_hash,edge.to_artifact_hash,"
    "edge.edge_role,source.source_hash,"
    "CASE WHEN pg_catalog.octet_length(source.source_key)<=1024 "
    "THEN source.source_key END AS source_key,"
    "pg_catalog.octet_length(source.source_key) AS source_key_bytes,"
    "source.source_ts,CASE WHEN pg_catalog.octet_length(source.source_scan_id)<=256 "
    "THEN source.source_scan_id END AS source_scan_id,"
    "pg_catalog.octet_length(source.source_scan_id) AS source_scan_id_bytes,"
    "source.source_table,source.cycle_schema_version "
    "FROM learning.alr_provenance_edges AS edge "
    "LEFT JOIN learning.alr_source_events AS source ON "
    "source.source_hash=edge.from_artifact_hash "
    "AND source.source_table='trading.scanner_snapshots' "
    "WHERE edge.to_artifact_hash=%s "
    "ORDER BY source.source_ts NULLS LAST,source.source_key NULLS LAST,"
    "source.source_hash NULLS LAST,edge.edge_hash LIMIT 4097"
)

HEALTH_SQL = (
    "SELECT health.snapshot_hash,health.source_head,health.recorded_at,"
    "health.fresh_cursor_ts,health.fresh_cursor_scan_id,"
    "pg_catalog.pg_column_size(health.canonical_payload) AS payload_bytes,"
    "CASE WHEN pg_catalog.pg_column_size(health.canonical_payload)<=262144 "
    "THEN health.canonical_payload END AS canonical_payload "
    "FROM learning.alr_health_events AS health "
    "WHERE health.source_head=%s AND health.recorded_at >= %s "
    "AND health.fresh_cursor_ts=%s AND health.fresh_cursor_scan_id=%s "
    "AND health.canonical_payload#>>'{watermark,source_hash}'=%s "
    "AND health.snapshot_hash<>%s "
    "ORDER BY health.recorded_at,health.snapshot_hash LIMIT 1"
)

STANDING_DEFER_SQL = (
    "WITH latest_run AS (SELECT run_hash,candidate_artifact_hash,run_status,"
    "no_authority,authority_counters,created_at "
    "FROM learning.alr_training_runs ORDER BY created_at DESC,run_hash DESC LIMIT 1),"
    "latest_feedback AS (SELECT feedback_status,proof_packet_present,"
    "reward_record_count,rotate_next_target,global_stop,no_authority,"
    "authority_counters FROM learning.alr_outcome_feedback_events "
    "WHERE run_hash=(SELECT run_hash FROM latest_run) "
    "ORDER BY recorded_at DESC,feedback_artifact_hash DESC LIMIT 1) "
    "SELECT run.run_hash,run.candidate_artifact_hash,run.run_status,"
    "CASE WHEN pg_catalog.pg_column_size(run.no_authority)<=8192 "
    "THEN run.no_authority END AS run_no_authority,"
    "CASE WHEN pg_catalog.pg_column_size(run.authority_counters)<=8192 "
    "THEN run.authority_counters END AS run_authority_counters,"
    "feedback.feedback_status,feedback.proof_packet_present,"
    "feedback.reward_record_count,feedback.rotate_next_target,feedback.global_stop,"
    "CASE WHEN pg_catalog.pg_column_size(feedback.no_authority)<=8192 "
    "THEN feedback.no_authority END AS feedback_no_authority,"
    "CASE WHEN pg_catalog.pg_column_size(feedback.authority_counters)<=8192 "
    "THEN feedback.authority_counters END AS feedback_authority_counters,"
    "(run.run_hash=%s AND run.candidate_artifact_hash=%s AND run.run_status=%s "
    "AND run.run_hash=%s AND run.candidate_artifact_hash=%s AND run.run_status=%s) "
    "AS bound_to_both_health_targets "
    "FROM latest_run AS run LEFT JOIN latest_feedback AS feedback ON TRUE"
)

TX_FINAL_SQL = (
    "SELECT pg_catalog.coalesce(pg_catalog.sum(stats.n_tup_ins),0)::bigint "
    "AS tuples_inserted,"
    "pg_catalog.coalesce(pg_catalog.sum(stats.n_tup_upd),0)::bigint "
    "AS tuples_updated,"
    "pg_catalog.coalesce(pg_catalog.sum(stats.n_tup_del),0)::bigint "
    "AS tuples_deleted,"
    "pg_catalog.pg_current_xact_id_if_assigned()::text AS txid_current_if_assigned "
    "FROM pg_catalog.pg_stat_xact_user_tables AS stats"
)


def _active_identity(active: Mapping[str, Any], *, unverified: bool = False) -> dict[str, str]:
    error = ObserverUnverified if unverified else ObserverFail
    expected_fixed = {
        "LoadState": "loaded",
        "ActiveState": "active",
        "SubState": "running",
        "NRestarts": "0",
    }
    if any(active.get(key) != value for key, value in expected_fixed.items()):
        raise error("alr_active_identity_invalid")
    values = {
        "MainPID": active.get("MainPID"),
        "ProcessStartTicks": active.get("ProcessStartTicks"),
        "InvocationID": active.get("InvocationID"),
        "ExecMainStartTimestampMonotonic": active.get(
            "ExecMainStartTimestampMonotonic"
        ),
    }
    if (
        not isinstance(values["MainPID"], str)
        or not values["MainPID"].isdigit()
        or int(values["MainPID"]) <= 0
        or not isinstance(values["ProcessStartTicks"], str)
        or not values["ProcessStartTicks"].isdigit()
        or not isinstance(values["ExecMainStartTimestampMonotonic"], str)
        or not values["ExecMainStartTimestampMonotonic"].isdigit()
        or not isinstance(values["InvocationID"], str)
        or re.fullmatch(r"[0-9a-f]{32}", values["InvocationID"]) is None
    ):
        raise error("alr_active_identity_invalid")
    return values  # type: ignore[return-value]


def _manager_identity(
    manager: Mapping[str, Any],
    *,
    unverified: bool = False,
) -> dict[str, str]:
    error = ObserverUnverified if unverified else ObserverFail
    if (
        manager.get("head") != TARGET_HEAD
        or manager.get("active_required") is not True
        or manager.get("conflicting_generation_environment") != []
        or manager.get("need_daemon_reload") != "no"
        or manager.get("fragment_path", str(UNIT_PATH)) != str(UNIT_PATH)
        or manager.get("drop_in_paths", "") != ""
    ):
        raise error("alr_manager_identity_invalid")
    result = {
        "MainPID": manager.get("main_pid"),
        "ProcessStartTicks": manager.get("process_start_ticks"),
        "InvocationID": manager.get("invocation_id"),
    }
    if any(not isinstance(value, str) or not value for value in result.values()):
        raise error("alr_manager_identity_invalid")
    return result  # type: ignore[return-value]


def _validate_apply_receipt(receipt: Mapping[str, Any]) -> dict[str, Any]:
    expected_fields = {
        "schema_version",
        "status",
        "returncode",
        "source_head",
        "transaction_adapter",
        "pm_approval",
        "pin_helper",
        "alr_after",
        "manager_loaded_after_restart",
        "unit_after",
        "generation_pin_after",
        "systemctl_effect_receipts",
        "atomic_effect_barrier",
        "boundaries",
        "claims",
    }
    if set(receipt) != expected_fields:
        raise ObserverUnverified("apply_receipt_fields_invalid")
    if (
        receipt.get("schema_version") != "p0b_alr_recovery_apply_receipt_v1"
        or receipt.get("status") != "APPLIED_POSTCHECK_PASS"
        or receipt.get("returncode") != 0
        or receipt.get("source_head") != TARGET_HEAD
    ):
        raise ObserverUnverified("apply_receipt_status_invalid")
    adapter = _mapping(
        receipt.get("transaction_adapter"),
        "apply_transaction_adapter_missing",
        unverified=True,
    )
    if adapter != {
        "path": str(RECOVERY_V2_PATH),
        "sha256": RECOVERY_V2_SHA256,
        "apply_count": 1,
        "retry_count": 0,
    }:
        raise ObserverUnverified("apply_transaction_adapter_invalid")
    approval = _mapping(
        receipt.get("pm_approval"),
        "apply_pm_approval_missing",
        unverified=True,
    )
    approved = _parse_utc(
        approval.get("approved_at_utc"),
        "apply_pm_approval_time_invalid",
        unverified=True,
    )
    expires = _parse_utc(
        approval.get("expires_at_utc"),
        "apply_pm_approval_time_invalid",
        unverified=True,
    )
    if (
        approval.get("path")
        != "/home/ncyu/BybitOpenClaw/srv/target/codex-context/"
        "p0b-recovery-pm-approval.json"
        or approval.get("sha256")
        != "b82b8d4a3058a32b9bb1d85c8c906b222285a66d4f54aaedd117f4615ea87e98"
        or approval.get("nonretryable") is not True
        or approved >= expires
    ):
        raise ObserverUnverified("apply_pm_approval_invalid")
    pin = _mapping(
        receipt.get("pin_helper"),
        "apply_pin_helper_missing",
        unverified=True,
    )
    started = _parse_utc(
        pin.get("started_at"), "apply_pin_time_invalid", unverified=True
    )
    completed = _parse_utc(
        pin.get("completed_at"), "apply_pin_time_invalid", unverified=True
    )
    if (
        pin.get("status") != "APPLIED_POSTCHECK_PASS"
        or pin.get("completed_at_semantics")
        != "apply_admission_lower_bound_utc_only"
        or not approved <= started <= completed <= expires
    ):
        raise ObserverUnverified("apply_pin_helper_invalid")
    active = _mapping(
        receipt.get("alr_after"),
        "apply_alr_identity_missing",
        unverified=True,
    )
    manager = _mapping(
        receipt.get("manager_loaded_after_restart"),
        "apply_manager_identity_missing",
        unverified=True,
    )
    active_identity = _active_identity(active, unverified=True)
    manager_identity = _manager_identity(manager, unverified=True)
    if (
        {key: active_identity[key] for key in manager_identity} != manager_identity
        or active.get("ControlGroup")
        != "/user.slice/user-1000.slice/user@1000.service/app.slice/"
        "openclaw-alr-shadow.service"
    ):
        raise ObserverUnverified("apply_identity_crosscheck_failed")
    unit = _mapping(
        receipt.get("unit_after"),
        "apply_unit_missing",
        unverified=True,
    )
    if (
        unit.get("path") != str(UNIT_PATH)
        or unit.get("sha256") != UNIT_SHA256
        or unit.get("mode") != "0600"
        or unit.get("size") != 2152
        or isinstance(unit.get("inode"), bool)
        or not isinstance(unit.get("inode"), int)
        or unit["inode"] <= 0
    ):
        raise ObserverUnverified("apply_unit_invalid")
    generation = _mapping(
        receipt.get("generation_pin_after"),
        "apply_generation_pin_missing",
        unverified=True,
    )
    if (
        generation.get("path") != str(PIN_PATH)
        or generation.get("sha256") != PIN_SHA256
        or generation.get("mode") != "0600"
        or generation.get("size") != 193
        or generation.get("head") != TARGET_HEAD
        or generation.get("derived_at_utc") != PIN_DERIVED_AT_UTC
        or isinstance(generation.get("inode"), bool)
        or not isinstance(generation.get("inode"), int)
        or generation["inode"] <= 0
    ):
        raise ObserverUnverified("apply_generation_pin_invalid")
    effects = _mapping(
        receipt.get("systemctl_effect_receipts"),
        "apply_systemctl_effects_missing",
        unverified=True,
    )
    if (
        effects.get("completed_total") != 3
        or effects.get("daemon_reload")
        != {"request_count": 1, "effect_count": 1}
        or effects.get("restart")
        != {
            "request_count": 1,
            "effect_count": 1,
            "stable_postcheck_seconds": 10,
        }
    ):
        raise ObserverUnverified("apply_systemctl_effects_invalid")
    reset = _mapping(
        effects.get("reset_failed"),
        "apply_reset_failed_missing",
        unverified=True,
    )
    if (
        reset.get("request_count") != 1
        or reset.get("effect_count") != 1
        or reset.get("disposition") != "RESTART_COUNTER_CLEARED"
        or reset.get("nrestarts_before") != 5417
        or reset.get("nrestarts_after") != 0
    ):
        raise ObserverUnverified("apply_reset_failed_invalid")
    if receipt.get("atomic_effect_barrier") != {
        "unit_committed_before_pin": True,
        "unit_and_pin_under_same_locks": True,
        "only_alr_unit_file_changed": True,
        "manager_wide_daemon_reload_count": 1,
    }:
        raise ObserverUnverified("apply_atomic_barrier_invalid")
    if receipt.get("boundaries") != {
        "api_service_mutation": False,
        "authorization_mutation": False,
        "broker_or_exchange_contact": False,
        "cron_mutation": False,
        "engine_service_mutation": False,
        "order_or_probe_action": False,
        "postgres_mutation": False,
        "watchdog_service_mutation": False,
    }:
        raise ObserverUnverified("apply_boundaries_invalid")
    if receipt.get("claims") != {
        "full_apply_completion_time_claimed": False,
        "serving_or_promotion_claimed": False,
        "trading_or_order_authority_claimed": False,
        "training_or_model_fit_claimed": False,
        "two_natural_cycles_observed": False,
    }:
        raise ObserverUnverified("apply_claims_invalid")
    return {
        "lower_bound": completed,
        "lower_bound_text": pin["completed_at"],
        "service_identity": active_identity,
    }


def _validate_board(board_outer: Mapping[str, Any]) -> dict[str, Any]:
    if (
        board_outer.get("schema_version")
        != "cost_gate_demo_learning_lane_blocked_outcome_review_v6"
        or board_outer.get("candidate_board_generation_state") != "COMPLETE"
        or board_outer.get("ledger_scan_status") != "COMPLETE"
        or board_outer.get("latest_alias_used", False) is not False
    ):
        raise ObserverUnverified("board_outer_semantics_invalid")
    board = _mapping(
        board_outer.get("learning_candidate_board"),
        "board_payload_missing",
        unverified=True,
    )
    expected_fields = {
        "schema_version",
        "as_of_utc_date",
        "candidate_universe_complete",
        *BOARD_AUDIT_FIELDS,
        "candidate_rows",
        "selection_hash",
        "audit_hash",
        "board_hash",
    }
    if set(board) != expected_fields:
        raise ObserverUnverified("board_fields_invalid")
    if (
        board.get("schema_version") != "cost_gate_learning_candidate_board_v2"
        or board.get("candidate_universe_complete") is not True
        or board.get("candidate_rows") != []
        or board.get("selection_hash") != SELECTION_HASH
        or board.get("audit_hash") != BOARD_AUDIT_HASH
        or board.get("board_hash") != BOARD_HASH
    ):
        raise ObserverUnverified("board_semantics_invalid")
    count_fields = BOARD_AUDIT_FIELDS[1:-1]
    counts = [board.get(field) for field in count_fields]
    if (
        board.get("lineage_partition_complete") is not True
        or any(
            isinstance(value, bool) or not isinstance(value, int) or value < 0
            for value in counts
        )
    ):
        raise ObserverUnverified("board_count_contract_invalid")
    raw, qualified, unqualified, invalid, exact, family, unassigned, *_ = counts
    if (
        raw != qualified + unqualified + invalid
        or invalid != exact + family + unassigned
        or qualified != 0
    ):
        raise ObserverUnverified("board_count_invariants_invalid")
    reasons = board.get("lineage_exclusion_reason_counts")
    if (
        not isinstance(reasons, Mapping)
        or any(
            not isinstance(key, str)
            or not key
            or isinstance(value, bool)
            or not isinstance(value, int)
            or value <= 0
            for key, value in reasons.items()
        )
        or sum(reasons.values()) != unqualified + invalid
    ):
        raise ObserverUnverified("board_reason_counts_invalid")
    if canonical_sha256([]) != CANDIDATE_SET_HASH:
        raise ObserverUnverified("board_candidate_set_hash_mismatch")
    if canonical_sha256(
        {
            "schema_version": "cost_gate_learning_candidate_selection_v2",
            "candidate_rows": [],
        }
    ) != SELECTION_HASH:
        raise ObserverUnverified("board_selection_hash_mismatch")
    audit_payload = {
        "schema_version": "cost_gate_learning_candidate_audit_v2",
        **{field: board[field] for field in BOARD_AUDIT_FIELDS},
        "candidate_audit_rows": [],
    }
    if canonical_sha256(audit_payload) != BOARD_AUDIT_HASH:
        raise ObserverUnverified("board_audit_hash_mismatch")
    without_hash = {key: value for key, value in board.items() if key != "board_hash"}
    if canonical_sha256(without_hash) != BOARD_HASH:
        raise ObserverUnverified("board_hash_mismatch")
    authority_flags: list[tuple[str, Any]] = []

    def visit(value: Any, path: str = "board") -> None:
        if isinstance(value, Mapping):
            for key, nested in value.items():
                lowered = str(key).lower()
                if "authority" in lowered and any(
                    token in lowered
                    for token in ("order", "probe", "promotion", "runtime")
                ):
                    authority_flags.append((f"{path}.{key}", nested))
                visit(nested, f"{path}.{key}")
        elif isinstance(value, list):
            for index, nested in enumerate(value):
                visit(nested, f"{path}[{index}]")

    visit(board_outer)
    if any(value not in (False, "NOT_GRANTED", 0, None, []) for _, value in authority_flags):
        raise ObserverUnverified("board_authority_grant_present")
    return {
        "candidate_count": 0,
        "candidate_universe_complete": True,
        "board_hash": BOARD_HASH,
        "audit_hash": BOARD_AUDIT_HASH,
        "selection_hash": SELECTION_HASH,
        "candidate_set_hash": CANDIDATE_SET_HASH,
    }


def _postcheck_sample(sample: Mapping[str, Any], expected_identity: Mapping[str, str]) -> None:
    active = _mapping(sample.get("alr"), "postcheck_alr_missing", unverified=True)
    if _active_identity(active, unverified=True) != expected_identity:
        raise ObserverUnverified("postcheck_alr_identity_invalid")
    manager = _mapping(
        sample.get("manager"), "postcheck_manager_missing", unverified=True
    )
    manager_identity = _manager_identity(manager, unverified=True)
    if {key: expected_identity[key] for key in manager_identity} != manager_identity:
        raise ObserverUnverified("postcheck_manager_identity_invalid")
    source = _mapping(sample.get("source"), "postcheck_source_missing", unverified=True)
    if (
        source.get("uid") != EXPECTED_UID
        or source.get("gid") != EXPECTED_GID
        or source.get("branch") != "main"
        or source.get("head") != TARGET_HEAD
        or source.get("clean") is not True
    ):
        raise ObserverUnverified("postcheck_source_invalid")
    if sample.get("job") != {"status": "NO_QUEUED_JOB", "unit": UNIT_NAME}:
        raise ObserverUnverified("postcheck_job_invalid")
    if sample.get("lane") != {"owner": False, "processes": [], "scopes": []}:
        raise ObserverUnverified("postcheck_lane_invalid")
    if sample.get("protected_sha256") != PROTECTED_SHA256:
        raise ObserverUnverified("postcheck_protected_invalid")
    unit = _mapping(sample.get("unit"), "postcheck_unit_missing", unverified=True)
    pin = _mapping(sample.get("pin"), "postcheck_pin_missing", unverified=True)
    if unit.get("sha256") != UNIT_SHA256 or pin.get("sha256") != PIN_SHA256:
        raise ObserverUnverified("postcheck_unit_pin_invalid")
    if pin.get("head") != TARGET_HEAD:
        raise ObserverUnverified("postcheck_pin_head_invalid")
    board = _mapping(
        sample.get("current_board"),
        "postcheck_board_missing",
        unverified=True,
    )
    if (
        board.get("candidate_count") != 0
        or board.get("candidate_universe_complete") is not True
        or board.get("generation_state") != "COMPLETE"
        or board.get("ledger_scan_status") != "COMPLETE"
        or board.get("bytes_equal") is not True
        or board.get("authority")
        != {"order": False, "probe": False, "promotion": False, "runtime": False}
        or _mapping(board.get("source"), "postcheck_board_source_missing", unverified=True).get(
            "sha256"
        )
        != BOARD_SOURCE_CONTENT_SHA256
        or _mapping(
            board.get("published"),
            "postcheck_board_published_missing",
            unverified=True,
        ).get("sha256")
        != BOARD_SOURCE_CONTENT_SHA256
    ):
        raise ObserverUnverified("postcheck_board_invalid")
    completion = _mapping(
        board.get("completion"),
        "postcheck_board_completion_missing",
        unverified=True,
    )
    if completion.get("status") != "COMPLETE" or completion.get("source_head") != TARGET_HEAD:
        raise ObserverUnverified("postcheck_board_completion_invalid")


def _validate_postcheck(
    postcheck: Mapping[str, Any],
    expected_identity: Mapping[str, str],
) -> None:
    if (
        postcheck.get("schema") != "p0b_independent_readonly_postapply_v1"
        or postcheck.get("status") != "PASS"
        or postcheck.get("evidence_sha256") != POSTCHECK_EVIDENCE_SHA256
        or canonical_sha256(
            {key: value for key, value in postcheck.items() if key != "evidence_sha256"}
        )
        != POSTCHECK_EVIDENCE_SHA256
    ):
        raise ObserverUnverified("postcheck_digest_or_status_invalid")
    if postcheck.get("expected") != {
        "pin_sha256": PIN_SHA256,
        "protected_sha256": PROTECTED_SHA256,
        "source_head": TARGET_HEAD,
        "unit_sha256": UNIT_SHA256,
        "v2_sha256": RECOVERY_V2_SHA256,
    }:
        raise ObserverUnverified("postcheck_expected_invalid")
    if postcheck.get("stability") != {
        "alr": True,
        "current_board": True,
        "job": True,
        "lane": True,
        "manager": True,
        "manager_environment_sha256": True,
        "pin": True,
        "protected_components": True,
        "protected_sha256": True,
        "source": True,
        "unit": True,
    }:
        raise ObserverUnverified("postcheck_stability_invalid")
    if postcheck.get("boundaries") != {
        "broker_contact": False,
        "credential_content_read": False,
        "mutation_performed": False,
        "pg_access": False,
        "systemctl_mutation": False,
    }:
        raise ObserverUnverified("postcheck_boundaries_invalid")
    first = _mapping(postcheck.get("first"), "postcheck_first_missing", unverified=True)
    second = _mapping(postcheck.get("second"), "postcheck_second_missing", unverified=True)
    _postcheck_sample(first, expected_identity)
    _postcheck_sample(second, expected_identity)
    for key in postcheck["stability"]:
        if first.get(key) != second.get(key):
            raise ObserverUnverified(f"postcheck_{key}_drift")


def load_fixed_trust(
    file_reader: Callable[..., tuple[bytes, dict[str, Any]]] = _read_bound_file,
) -> dict[str, Any]:
    receipt_raw, receipt_identity = file_reader(
        APPLY_RECEIPT_PATH,
        APPLY_RECEIPT_SHA256,
        label="apply_receipt",
        max_bytes=MAX_RECEIPT_BYTES,
        mode=0o600,
    )
    receipt = _strict_json(receipt_raw, label="apply_receipt")
    apply = _validate_apply_receipt(receipt)
    board_raw, board_identity = file_reader(
        BOARD_PATH,
        BOARD_SOURCE_CONTENT_SHA256,
        label="board",
        max_bytes=MAX_BOARD_BYTES,
        mode=None,
    )
    board = _validate_board(_strict_json(board_raw, label="board"))
    postcheck_raw, postcheck_identity = file_reader(
        POSTCHECK_PATH,
        POSTCHECK_SHA256,
        label="postcheck",
        max_bytes=MAX_POSTCHECK_BYTES,
        mode=0o600,
    )
    _validate_postcheck(
        _strict_json(postcheck_raw, label="postcheck"),
        apply["service_identity"],
    )
    return {
        **apply,
        "board": board,
        "receipt_identity": receipt_identity,
        "board_identity": board_identity,
        "postcheck_identity": postcheck_identity,
    }


def _read_runtime_files(
    file_reader: Callable[..., tuple[bytes, dict[str, Any]]] = _read_bound_file,
) -> dict[str, Any]:
    unit_raw, unit_identity = file_reader(
        UNIT_PATH,
        UNIT_SHA256,
        label="unit",
        max_bytes=MAX_UNIT_BYTES,
        mode=0o600,
    )
    try:
        unit_text = unit_raw.decode("utf-8")
    except UnicodeError as exc:
        raise ObserverUnverified("unit_not_utf8") from exc
    if unit_text.count(TARGET_HEAD) != 1:
        raise ObserverUnverified("unit_target_head_binding_invalid")
    pin_raw, pin_identity = file_reader(
        PIN_PATH,
        PIN_SHA256,
        label="pin",
        max_bytes=MAX_PIN_BYTES,
        mode=0o600,
    )
    pin = _strict_json(pin_raw, label="pin")
    if pin != {
        "head": TARGET_HEAD,
        "derived_at_utc": PIN_DERIVED_AT_UTC,
        "writer": "derive_expected_source_head.sh",
        "base_dir": "/home/ncyu/BybitOpenClaw/srv",
    }:
        raise ObserverUnverified("pin_payload_invalid")
    return {"unit": unit_identity, "pin": pin_identity, "pin_payload": pin}


def _validate_owned_parent_chain(path: Path, *, label: str) -> None:
    home = Path("/home/ncyu")
    try:
        relative = path.absolute().relative_to(home)
    except ValueError as exc:
        raise ObserverUnverified(f"{label}_outside_home") from exc
    current = home
    for part in relative.parts:
        current = current / part
        if current == path:
            break
        try:
            observed = current.lstat()
        except OSError as exc:
            raise ObserverUnverified(f"{label}_parent_unavailable") from exc
        if (
            stat.S_ISLNK(observed.st_mode)
            or not stat.S_ISDIR(observed.st_mode)
            or observed.st_uid != EXPECTED_UID
            or observed.st_gid != EXPECTED_GID
            or stat.S_IMODE(observed.st_mode) & 0o022
        ):
            raise ObserverUnverified(f"{label}_parent_identity_invalid")


def parse_exact_dsn_text(text: str) -> dict[str, str]:
    try:
        parts = shlex.split(text)
    except ValueError as exc:
        raise ObserverUnverified("dsn_invalid") from exc
    allowed = {"host", "port", "dbname", "user", "password"}
    parsed: dict[str, str] = {}
    for part in parts:
        if "=" not in part:
            raise ObserverUnverified("dsn_invalid")
        key, value = part.split("=", 1)
        if key not in allowed or key in parsed or not value:
            raise ObserverUnverified("dsn_invalid")
        parsed[key] = value
    if set(parsed) != allowed:
        raise ObserverUnverified("dsn_fields_invalid")
    if (
        parsed["host"] != "127.0.0.1"
        or parsed["port"] != "5432"
        or parsed["dbname"] != "trading_ai"
        or parsed["user"] != "alr_shadow"
        or not parsed["password"]
    ):
        raise ObserverUnverified("dsn_location_invalid")
    return parsed


def read_exact_dsn() -> dict[str, str]:
    _validate_owned_parent_chain(DSN_PATH, label="dsn")
    # The DSN is deliberately not hash-bound because the password is rotatable;
    # its path, file identity, exact key set, and local-only location are fixed.
    if getattr(os, "O_NOFOLLOW", None) is None:
        raise ObserverUnverified("dsn_secure_open_unavailable")
    try:
        before = DSN_PATH.lstat()
    except OSError as exc:
        raise ObserverUnverified("dsn_unavailable") from exc
    if (
        stat.S_ISLNK(before.st_mode)
        or not stat.S_ISREG(before.st_mode)
        or before.st_uid != EXPECTED_UID
        or before.st_gid != EXPECTED_GID
        or stat.S_IMODE(before.st_mode) != 0o600
        or before.st_nlink != 1
        or not 0 < before.st_size <= MAX_DSN_BYTES
    ):
        raise ObserverUnverified("dsn_identity_invalid")
    try:
        descriptor = os.open(
            DSN_PATH,
            os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0),
        )
    except OSError as exc:
        raise ObserverUnverified("dsn_open_failed") from exc
    try:
        opened = os.fstat(descriptor)
        if _identity(opened) != _identity(before):
            raise ObserverUnverified("dsn_identity_changed")
        raw = os.read(descriptor, MAX_DSN_BYTES + 1)
        if len(raw) != opened.st_size or len(raw) > MAX_DSN_BYTES:
            raise ObserverUnverified("dsn_read_size_invalid")
        final = os.fstat(descriptor)
        if _identity(final) != _identity(opened):
            raise ObserverUnverified("dsn_changed_during_read")
    finally:
        os.close(descriptor)
    try:
        text = raw.decode("utf-8").strip()
    except UnicodeError as exc:
        raise ObserverUnverified("dsn_not_utf8") from exc
    return parse_exact_dsn_text(text)


def reject_ambient_pg_environment(environment: Mapping[str, str]) -> None:
    if any(str(key).upper().startswith("PG") for key in environment):
        raise ObserverUnverified("ambient_pg_environment_present")


def _directory_identity(path: Path, *, label: str, mode: int) -> dict[str, Any]:
    if getattr(os, "O_NOFOLLOW", None) is None:
        raise ObserverUnverified(f"{label}_secure_open_unavailable")
    try:
        before = path.lstat()
    except OSError as exc:
        raise ObserverUnverified(f"{label}_unavailable") from exc
    if (
        stat.S_ISLNK(before.st_mode)
        or not stat.S_ISDIR(before.st_mode)
        or before.st_uid != EXPECTED_UID
        or before.st_gid != EXPECTED_GID
        or stat.S_IMODE(before.st_mode) != mode
    ):
        raise ObserverUnverified(f"{label}_identity_invalid")
    try:
        descriptor = os.open(
            path,
            os.O_RDONLY
            | os.O_NOFOLLOW
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_DIRECTORY", 0),
        )
    except OSError as exc:
        raise ObserverUnverified(f"{label}_open_failed") from exc
    try:
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISDIR(opened.st_mode)
            or (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino)
            or opened.st_uid != EXPECTED_UID
            or opened.st_gid != EXPECTED_GID
            or stat.S_IMODE(opened.st_mode) != mode
        ):
            raise ObserverUnverified(f"{label}_identity_changed")
    finally:
        os.close(descriptor)
    return _identity(opened)


def _exact_directory_entries(path: Path, expected: set[str], *, label: str) -> None:
    try:
        names = {entry.name for entry in os.scandir(path)}
    except OSError as exc:
        raise ObserverUnverified(f"{label}_enumeration_failed") from exc
    if names != expected:
        raise ObserverUnverified(f"{label}_entry_set_invalid")
    for name in names:
        try:
            observed = (path / name).lstat()
        except OSError as exc:
            raise ObserverUnverified(f"{label}_entry_unavailable") from exc
        if stat.S_ISLNK(observed.st_mode):
            raise ObserverUnverified(f"{label}_symlink_present")


def verify_private_psycopg_bundle() -> dict[str, Any]:
    package_manifest = PSYCOPG_PACKAGE_MANIFEST
    lib_manifest = PSYCOPG_LIB_MANIFEST
    root = PRIVATE_DEPS_ROOT
    if len(package_manifest) != 12 or len(lib_manifest) != 15:
        raise ObserverUnverified("psycopg_bundle_manifest_unsealed")
    site = root / "site-packages"
    package = site / "psycopg2"
    libraries = site / "psycopg2_binary.libs"
    _validate_owned_parent_chain(root, label="psycopg_bundle")
    directory_identities = {
        "root": _directory_identity(root, label="psycopg_root", mode=0o700),
        "site": _directory_identity(site, label="psycopg_site", mode=0o700),
        "package": _directory_identity(
            package, label="psycopg_package", mode=0o700
        ),
        "libraries": _directory_identity(
            libraries, label="psycopg_libraries", mode=0o700
        ),
    }
    _exact_directory_entries(root, {"site-packages"}, label="psycopg_root")
    _exact_directory_entries(
        site, {"psycopg2", "psycopg2_binary.libs"}, label="psycopg_site"
    )
    _exact_directory_entries(package, set(package_manifest), label="psycopg_package")
    _exact_directory_entries(libraries, set(lib_manifest), label="psycopg_libraries")
    files: dict[str, dict[str, Any]] = {}
    for name, digest in sorted(package_manifest.items()):
        expected_mode = 0o700 if name == PSYCOPG_EXTENSION_NAME else 0o600
        _raw, identity = _read_bound_file(
            package / name,
            digest,
            label="psycopg_package_file",
            max_bytes=16 * 1024 * 1024,
            mode=expected_mode,
            uid=EXPECTED_UID,
            gid=EXPECTED_GID,
            require_nonempty=True,
        )
        files[f"psycopg2/{name}"] = identity
    for name, digest in sorted(lib_manifest.items()):
        _raw, identity = _read_bound_file(
            libraries / name,
            digest,
            label="psycopg_library_file",
            max_bytes=32 * 1024 * 1024,
            mode=0o700,
            uid=EXPECTED_UID,
            gid=EXPECTED_GID,
            require_nonempty=True,
        )
        files[f"psycopg2_binary.libs/{name}"] = identity
    return {
        "directories": directory_identities,
        "files": files,
        "manifest_sha256": canonical_sha256(
            {"package": dict(package_manifest), "libraries": dict(lib_manifest)}
        ),
    }


def _mapped_paths() -> set[Path]:
    raw = _read_proc_file(Path("/proc/self/maps"), label="proc_self_maps", max_bytes=MAX_PROC_BYTES)
    try:
        lines = raw.decode("utf-8").splitlines()
    except UnicodeError as exc:
        raise ObserverUnverified("proc_self_maps_invalid") from exc
    paths: set[Path] = set()
    for line in lines:
        fields = line.split(None, 5)
        if len(fields) != 6 or not fields[5].startswith("/"):
            continue
        text = fields[5]
        if text.endswith(" (deleted)"):
            raise ObserverUnverified("mapped_dependency_deleted")
        paths.add(Path(text))
    return paths


def _verify_root_owned_system_path(path: Path) -> None:
    real = Path(os.path.realpath(path))
    if not (str(real).startswith("/usr/lib/") or str(real).startswith("/lib/")):
        raise ObserverUnverified("mapped_system_dependency_outside_lib")
    current = Path("/")
    for part in real.parts[1:]:
        current = current / part
        try:
            observed = current.lstat()
        except OSError as exc:
            raise ObserverUnverified("mapped_system_dependency_unavailable") from exc
        if (
            stat.S_ISLNK(observed.st_mode)
            or observed.st_uid != 0
            or observed.st_gid != 0
            or stat.S_IMODE(observed.st_mode) & 0o022
        ):
            raise ObserverUnverified("mapped_system_dependency_identity_invalid")


def _validate_mapped_dependencies(before: set[Path], after: set[Path]) -> dict[str, Any]:
    extension = PSYCOPG_PACKAGE_PATH / PSYCOPG_EXTENSION_NAME
    if extension not in after:
        raise ObserverUnverified("psycopg_extension_not_mapped")
    allowed_private = {
        extension,
        *(PSYCOPG_LIBS_PATH / name for name in PSYCOPG_LIB_MANIFEST),
    }
    mapped_private = {path for path in after if str(path).startswith(str(PRIVATE_DEPS_ROOT) + "/")}
    if not mapped_private.issubset(allowed_private):
        raise ObserverUnverified("unsealed_private_dependency_mapped")
    for path in sorted((after - before) - mapped_private, key=str):
        if ".so" in path.name:
            _verify_root_owned_system_path(path)
    return {
        "extension_mapped": True,
        "mapped_private_file_count": len(mapped_private),
        "mapped_private_manifest_subset": True,
        "new_system_libraries_root_owned_nonwritable": True,
    }


def load_verified_psycopg2() -> tuple[Any, Any, dict[str, Any]]:
    if any(name == "psycopg2" or name.startswith("psycopg2.") for name in sys.modules):
        raise ObserverUnverified("psycopg2_preimported")
    before_bundle = verify_private_psycopg_bundle()
    before_maps = _mapped_paths()
    site_text = str(PRIVATE_SITE_PACKAGES)
    if site_text in sys.path:
        raise ObserverUnverified("psycopg_private_site_preexisting")
    sys.path.append(site_text)
    importlib.invalidate_caches()
    spec = importlib.util.find_spec("psycopg2")
    expected_init = PSYCOPG_PACKAGE_PATH / "__init__.py"
    if spec is None or spec.origin != str(expected_init):
        raise ObserverUnverified("psycopg2_import_origin_untrusted")
    try:
        psycopg2 = importlib.import_module("psycopg2")
        extras = importlib.import_module("psycopg2.extras")
        extension = importlib.import_module("psycopg2._psycopg")
    except Exception as exc:
        raise ObserverUnverified("psycopg2_import_failed") from exc
    if (
        getattr(psycopg2, "__file__", None) != str(expected_init)
        or getattr(extras, "__file__", None)
        != str(PSYCOPG_PACKAGE_PATH / "extras.py")
        or getattr(extension, "__file__", None)
        != str(PSYCOPG_PACKAGE_PATH / PSYCOPG_EXTENSION_NAME)
        or str(getattr(psycopg2, "__version__", "")).split(maxsplit=1)[0]
        != PSYCOPG_VERSION_TOKEN
    ):
        raise ObserverUnverified("psycopg2_import_attestation_failed")
    mapped = _validate_mapped_dependencies(before_maps, _mapped_paths())
    after_bundle = verify_private_psycopg_bundle()
    if after_bundle != before_bundle:
        raise ObserverUnverified("psycopg_bundle_changed_during_import")
    cursor_factory = getattr(extras, "RealDictCursor", None)
    if cursor_factory is None:
        raise ObserverUnverified("psycopg_real_dict_cursor_missing")
    return psycopg2, cursor_factory, mapped


def connect_readonly(parameters: Mapping[str, str]) -> Any:
    if set(parameters) != {"host", "port", "dbname", "user", "password"}:
        raise ObserverUnverified("dsn_fields_invalid")
    psycopg2, cursor_factory, _mapped = load_verified_psycopg2()
    try:
        return psycopg2.connect(
            host=parameters["host"],
            port=int(parameters["port"]),
            dbname=parameters["dbname"],
            user=parameters["user"],
            password=parameters["password"],
            sslmode="disable",
            application_name=PG_APPLICATION_NAME,
            connect_timeout=5,
            options=PG_OPTIONS,
            cursor_factory=cursor_factory,
        )
    except Exception as exc:
        raise ObserverUnverified("pg_connection_failed") from exc


def load_exact_recovery_module() -> Any:
    raw, _identity_value = _read_bound_file(
        RECOVERY_V2_PATH,
        RECOVERY_V2_SHA256,
        label="recovery_v2",
        max_bytes=2 * 1024 * 1024,
        mode=None,
    )
    module = types.ModuleType("p0b_observer_reviewed_recovery_v2")
    module.__file__ = str(RECOVERY_V2_PATH)
    module.__package__ = ""
    try:
        exec(
            compile(raw, str(RECOVERY_V2_PATH), "exec", dont_inherit=True),
            module.__dict__,
        )
    except Exception as exc:
        raise ObserverUnverified("recovery_v2_load_failed") from exc
    if not hasattr(module, "Runtime"):
        raise ObserverUnverified("recovery_v2_runtime_missing")
    return module


def _read_recovery_git_metadata(
    file_reader: Callable[..., tuple[bytes, dict[str, Any]]],
) -> dict[str, dict[str, Any]]:
    exclude_raw, exclude_identity = file_reader(
        RECOVERY_GIT_INFO_EXCLUDE_PATH,
        RECOVERY_GIT_INFO_EXCLUDE_SHA256,
        label="recovery_git_info_exclude",
        max_bytes=4096,
        mode=0o664,
        uid=EXPECTED_UID,
        gid=EXPECTED_GID,
        require_nonempty=True,
    )
    index_raw, index_identity = file_reader(
        RECOVERY_GIT_INDEX_PATH,
        RECOVERY_GIT_INDEX_SHA256,
        label="recovery_git_index",
        max_bytes=2 * 1024 * 1024,
        mode=0o664,
        uid=EXPECTED_UID,
        gid=EXPECTED_GID,
        require_nonempty=True,
    )
    passwd_raw, passwd_identity = file_reader(
        RECOVERY_PASSWD_PATH,
        RECOVERY_PASSWD_SHA256,
        label="recovery_passwd",
        max_bytes=64 * 1024,
        mode=0o644,
        uid=0,
        gid=0,
        require_nonempty=True,
    )
    group_raw, group_identity = file_reader(
        RECOVERY_GROUP_PATH,
        RECOVERY_GROUP_SHA256,
        label="recovery_group",
        max_bytes=64 * 1024,
        mode=0o644,
        uid=0,
        gid=0,
        require_nonempty=True,
    )
    if (
        len(exclude_raw) != RECOVERY_GIT_INFO_EXCLUDE_SIZE
        or exclude_identity.get("size") != RECOVERY_GIT_INFO_EXCLUDE_SIZE
        or len(index_raw) != RECOVERY_GIT_INDEX_SIZE
        or index_identity.get("size") != RECOVERY_GIT_INDEX_SIZE
        or {
            key: passwd_identity.get(key) for key in RECOVERY_PASSWD_EXPECTED
        }
        != RECOVERY_PASSWD_EXPECTED
        or {
            key: group_identity.get(key) for key in RECOVERY_GROUP_EXPECTED
        }
        != RECOVERY_GROUP_EXPECTED
    ):
        raise ObserverUnverified("recovery_git_metadata_size_invalid")
    try:
        passwd_lines = passwd_raw.decode("utf-8").splitlines()
        group_lines = group_raw.decode("utf-8").splitlines()
    except UnicodeError as exc:
        raise ObserverUnverified("recovery_private_group_database_invalid") from exc
    primary_gid_users = [
        fields
        for line in passwd_lines
        if not line.startswith("#")
        and len(fields := line.split(":")) == 7
        and fields[3] == "1000"
    ]
    private_groups = [
        fields
        for line in group_lines
        if not line.startswith("#")
        and len(fields := line.split(":")) == 4
        and fields[2] == "1000"
    ]
    if primary_gid_users != [
        ["ncyu", "x", "1000", "1000", "NCYu", "/home/ncyu", "/bin/bash"]
    ] or private_groups != [["ncyu", "x", "1000", ""]]:
        raise ObserverUnverified("recovery_private_group_database_invalid")
    return {
        "info_exclude": dict(exclude_identity),
        "index": dict(index_identity),
        "passwd": dict(passwd_identity),
        "group": dict(group_identity),
    }


def _observe_recovery_git_paths() -> dict[str, Any]:
    repo_identity = _directory_identity(
        RECOVERY_REPO_PATH,
        label="recovery_repo_directory",
        mode=0o775,
    )
    git_identity = _directory_identity(
        RECOVERY_GIT_DIR_PATH,
        label="recovery_git_directory",
        mode=0o775,
    )
    for observed, expected in (
        (repo_identity, RECOVERY_REPO_DIRECTORY_EXPECTED),
        (git_identity, RECOVERY_GIT_DIRECTORY_EXPECTED),
    ):
        if {key: observed.get(key) for key in expected} != expected:
            raise ObserverUnverified("recovery_git_directory_identity_invalid")
    try:
        RECOVERY_GIT_INFO_ATTRIBUTES_PATH.lstat()
    except FileNotFoundError:
        attributes_absent = True
    except OSError as exc:
        raise ObserverUnverified(
            "recovery_git_info_attributes_unavailable"
        ) from exc
    else:
        raise ObserverUnverified("recovery_git_info_attributes_present")
    return {
        "repo": repo_identity,
        "git": git_identity,
        "info_attributes_absent": attributes_absent,
        "private_group_boundary": (
            "uid_gid_1000_same_principal_private_primary_group"
        ),
    }


def harden_loaded_recovery_git(
    recovery_module: Any,
    *,
    file_reader: Callable[..., tuple[bytes, dict[str, Any]]] = _read_bound_file,
    git_path_observer: Callable[[], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Seal the exact recovery module's read-only Git observation surface."""

    base = getattr(recovery_module, "base", None)
    runtime_class = getattr(recovery_module, "Runtime", None)
    base_runtime_class = getattr(base, "RecoveryRuntime", None)
    base_environment = getattr(base, "SYSTEM_ENV", None)
    if (
        not isinstance(base_environment, dict)
        or base_environment != RECOVERY_BASE_SYSTEM_ENV
        or not isinstance(runtime_class, type)
        or not isinstance(base_runtime_class, type)
        or not issubclass(runtime_class, base_runtime_class)
        or Path(getattr(base, "REPO", "")) != RECOVERY_REPO_PATH
        or not callable(getattr(base_runtime_class, "run", None))
        or not callable(base_runtime_class.__dict__.get("git"))
        or "git" in runtime_class.__dict__
    ):
        raise ObserverUnverified("recovery_git_hardening_seam_invalid")

    allowed_calls = {
        ("symbolic-ref", "--short", "HEAD"),
        ("rev-parse", "HEAD"),
        ("status", "--porcelain=v1", "--untracked-files=all"),
    }
    hardened_environment = dict(RECOVERY_HARDENED_GIT_ENV)

    base.SYSTEM_ENV = dict(hardened_environment)
    path_observer = git_path_observer or getattr(
        file_reader, "observe_git_paths", _observe_recovery_git_paths
    )
    metadata_identity = _read_recovery_git_metadata(file_reader)
    path_identity = path_observer()

    def assert_git_metadata_stable() -> None:
        if (
            _read_recovery_git_metadata(file_reader) != metadata_identity
            or path_observer() != path_identity
        ):
            raise ObserverUnverified("recovery_git_metadata_changed")

    assert_git_metadata_stable()
    try:
        inventory_completed = base_runtime_class.run(
            [*RECOVERY_GIT_COMMAND_PREFIX, *RECOVERY_GIT_CONFIG_INVENTORY_ARGS],
            env=dict(hardened_environment),
        )
    except Exception as exc:
        raise ObserverUnverified("recovery_git_config_inventory_failed") from exc
    assert_git_metadata_stable()
    inventory_stdout = getattr(inventory_completed, "stdout", None)
    if not isinstance(inventory_stdout, str):
        raise ObserverUnverified("recovery_git_config_inventory_invalid")
    try:
        inventory_bytes = inventory_stdout.encode("utf-8")
    except UnicodeError as exc:
        raise ObserverUnverified("recovery_git_config_inventory_invalid") from exc
    if (
        len(inventory_bytes) > MAX_GIT_CONFIG_INVENTORY_BYTES
        or (inventory_stdout and not inventory_stdout.endswith("\x00"))
    ):
        raise ObserverUnverified("recovery_git_config_inventory_invalid")
    config_keys = (
        inventory_stdout[:-1].split("\x00") if inventory_stdout else []
    )
    if len(config_keys) > MAX_GIT_CONFIG_KEYS:
        raise ObserverUnverified("recovery_git_config_inventory_invalid")
    forbidden_exact = {
        "core.attributesfile",
        "core.excludesfile",
        "core.sparsecheckout",
        "core.sparsecheckoutcone",
        "core.worktree",
        "extensions.relativeworktrees",
        "extensions.worktreeconfig",
        "index.sparse",
        "trace2.normaltarget",
        "trace2.perftarget",
        "trace2.eventtarget",
    }
    for key in config_keys:
        try:
            key_bytes = key.encode("utf-8")
        except UnicodeError as exc:
            raise ObserverUnverified(
                "recovery_git_config_key_invalid"
            ) from exc
        lowered = key.lower()
        if (
            not key
            or len(key_bytes) > MAX_GIT_CONFIG_KEY_BYTES
            or key != key.strip()
            or any(character in key for character in ("\n", "\r"))
        ):
            raise ObserverUnverified("recovery_git_config_key_invalid")
        if (
            lowered.startswith("filter.")
            or lowered.startswith("include.")
            or lowered.startswith("includeif.")
            or lowered in forbidden_exact
        ):
            raise ObserverUnverified("recovery_git_effectful_config_present")

    assert_git_metadata_stable()
    try:
        shared_index_completed = base_runtime_class.run(
            [*RECOVERY_GIT_COMMAND_PREFIX, "rev-parse", "--shared-index-path"],
            env=dict(hardened_environment),
        )
    except Exception as exc:
        raise ObserverUnverified("recovery_git_shared_index_probe_failed") from exc
    assert_git_metadata_stable()
    shared_index_stdout = getattr(shared_index_completed, "stdout", None)
    if shared_index_stdout != "":
        raise ObserverUnverified("recovery_git_shared_index_present")

    assert_git_metadata_stable()
    try:
        index_completed = base_runtime_class.run(
            [*RECOVERY_GIT_COMMAND_PREFIX, "ls-files", "-v", "-z"],
            env=dict(hardened_environment),
        )
    except Exception as exc:
        raise ObserverUnverified("recovery_git_index_inventory_failed") from exc
    assert_git_metadata_stable()
    index_stdout = getattr(index_completed, "stdout", None)
    if not isinstance(index_stdout, str):
        raise ObserverUnverified("recovery_git_index_inventory_invalid")
    try:
        index_inventory_bytes = index_stdout.encode("utf-8")
    except UnicodeError as exc:
        raise ObserverUnverified("recovery_git_index_inventory_invalid") from exc
    if (
        not index_stdout.endswith("\x00")
        or len(index_inventory_bytes) > MAX_GIT_INDEX_INVENTORY_BYTES
    ):
        raise ObserverUnverified("recovery_git_index_inventory_invalid")
    index_records = index_stdout[:-1].split("\x00")
    if len(index_records) != RECOVERY_GIT_INDEX_RECORD_COUNT:
        raise ObserverUnverified("recovery_git_index_inventory_invalid")
    for record in index_records:
        if (
            not record.startswith("H ")
            or not record[2:]
            or len(record[2:].encode("utf-8")) > MAX_GIT_INDEX_PATH_BYTES
        ):
            raise ObserverUnverified("recovery_git_index_flag_or_path_invalid")

    assert_git_metadata_stable()
    try:
        stage_completed = base_runtime_class.run(
            [*RECOVERY_GIT_COMMAND_PREFIX, "ls-files", "--stage", "-z"],
            env=dict(hardened_environment),
        )
    except Exception as exc:
        raise ObserverUnverified("recovery_git_stage_inventory_failed") from exc
    assert_git_metadata_stable()
    stage_stdout = getattr(stage_completed, "stdout", None)
    if not isinstance(stage_stdout, str):
        raise ObserverUnverified("recovery_git_stage_inventory_invalid")
    try:
        stage_inventory_bytes = stage_stdout.encode("utf-8")
    except UnicodeError as exc:
        raise ObserverUnverified("recovery_git_stage_inventory_invalid") from exc
    if (
        len(stage_inventory_bytes) != RECOVERY_GIT_STAGE_INVENTORY_SIZE
        or not stage_stdout.endswith("\x00")
    ):
        raise ObserverUnverified("recovery_git_stage_inventory_invalid")
    stage_records = stage_stdout[:-1].split("\x00")
    if len(stage_records) != RECOVERY_GIT_INDEX_RECORD_COUNT:
        raise ObserverUnverified("recovery_git_stage_inventory_invalid")
    for record in stage_records:
        metadata, separator, path = record.partition("\t")
        fields = metadata.split(" ")
        if (
            separator != "\t"
            or len(fields) != 3
            or re.fullmatch(r"[0-7]{6}", fields[0]) is None
            or HEX40_RE.fullmatch(fields[1]) is None
            or fields[2] != "0"
            or fields[0] == "160000"
            or not path
            or path == ".gitmodules"
            or len(path.encode("utf-8")) > MAX_GIT_INDEX_PATH_BYTES
        ):
            raise ObserverUnverified("recovery_git_stage_or_submodule_invalid")

    def hardened_git(instance: Any, *args: str) -> str:
        if (
            getattr(base, "SYSTEM_ENV", None) != hardened_environment
            or args not in allowed_calls
            or any(not isinstance(value, str) or "\x00" in value for value in args)
        ):
            raise ObserverUnverified("recovery_git_command_scope_drift")
        effective_args = (
            (*args, "--ignore-submodules=all")
            if args and args[0] == "status"
            else args
        )
        assert_git_metadata_stable()
        completed = instance.run(
            [*RECOVERY_GIT_COMMAND_PREFIX, *effective_args],
            env=dict(hardened_environment),
        )
        assert_git_metadata_stable()
        stdout = getattr(completed, "stdout", None)
        if not isinstance(stdout, str):
            raise ObserverUnverified("recovery_git_stdout_invalid")
        return stdout.strip()

    base_runtime_class.git = hardened_git
    if getattr(runtime_class, "git", None) is not hardened_git:
        raise ObserverUnverified("recovery_git_hardening_install_failed")
    return {
        "git_optional_locks": False,
        "global_config_disabled": True,
        "system_config_disabled": True,
        "fsmonitor_disabled_per_command": True,
        "untracked_cache_disabled_per_command": True,
        "trace2_disabled": True,
        "system_attributes_disabled": True,
        "lazy_fetch_disabled": True,
        "replace_objects_disabled": True,
        "submodule_recursion_disabled_for_status": True,
        "exact_git_dir_and_work_tree": True,
        "stat_semantics_fixed_per_command": True,
        "trust_ctime_enabled_per_command": True,
        "ignore_case_disabled_per_command": True,
        "common_git_directory_fixed": True,
        "local_included_config_names_only_inventory": True,
        "local_config_key_count": len(config_keys),
        "index_inventory_names_only": True,
        "index_record_count": len(index_records),
        "index_inventory_sha256": hashlib.sha256(
            index_inventory_bytes
        ).hexdigest(),
        "shared_index_path_empty": True,
        "stage_inventory_bounded": True,
        "stage_record_count": len(stage_records),
        "stage_inventory_sha256": hashlib.sha256(
            stage_inventory_bytes
        ).hexdigest(),
        "stage0_only": True,
        "gitlink_count": 0,
        "tracked_gitmodules_present": False,
        "submodule_ignore_evidence_safe": True,
        "git_info_exclude_sha256": RECOVERY_GIT_INFO_EXCLUDE_SHA256,
        "git_index_sha256": RECOVERY_GIT_INDEX_SHA256,
        "exact_repo_and_git_directory_identity": True,
        "git_info_attributes_absent": True,
        "source_clean_scope": (
            "tracked_changes_and_nonignored_untracked_files_under_exact_worktree"
        ),
        "ignored_artifacts_absence_claimed": False,
        "private_group_threat_boundary": (
            "uid_gid_1000_same_principal_private_primary_group"
        ),
        "private_group_identity_files_sealed": True,
    }


def observe_singleton_lock(pid: int) -> dict[str, Any]:
    if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
        raise ObserverFail("singleton_pid_invalid")
    try:
        before = SINGLETON_LOCK_PATH.lstat()
    except OSError as exc:
        raise ObserverFail("singleton_lock_unavailable") from exc
    if (
        stat.S_ISLNK(before.st_mode)
        or not stat.S_ISREG(before.st_mode)
        or before.st_uid != EXPECTED_UID
        or before.st_gid != EXPECTED_GID
        or stat.S_IMODE(before.st_mode) != 0o600
        or before.st_nlink != 1
        or before.st_size != 0
    ):
        raise ObserverFail("singleton_lock_identity_invalid")
    fd_root = PROC_ROOT / str(pid) / "fd"
    matching_fds: list[int] = []
    try:
        entries = list(os.scandir(fd_root))
    except OSError as exc:
        raise ObserverFail("singleton_process_fd_unavailable") from exc
    if len(entries) > 65536:
        raise ObserverUnverified("singleton_process_fd_limit_exceeded")
    for entry in entries:
        if not entry.name.isdigit():
            continue
        fd_path = fd_root / entry.name
        try:
            target = os.readlink(fd_path)
            opened = os.stat(fd_path)
        except OSError:
            continue
        if (
            target == str(SINGLETON_LOCK_PATH)
            and stat.S_ISREG(opened.st_mode)
            and (opened.st_dev, opened.st_ino) == (before.st_dev, before.st_ino)
        ):
            matching_fds.append(int(entry.name))
    if len(matching_fds) != 1:
        raise ObserverFail("singleton_lock_fd_binding_invalid")
    raw_locks = _read_proc_file(PROC_LOCKS_PATH, label="proc_locks", max_bytes=MAX_PROC_BYTES)
    try:
        lines = raw_locks.decode("ascii").splitlines()
    except UnicodeError as exc:
        raise ObserverUnverified("proc_locks_invalid") from exc
    device_inode = (
        f"{os.major(before.st_dev):02x}:{os.minor(before.st_dev):02x}:"
        f"{before.st_ino}"
    )
    same_inode: list[list[str]] = []
    for line in lines:
        fields = line.split()
        if device_inode in fields:
            same_inode.append(fields)
    valid = [
        fields
        for fields in same_inode
        if len(fields) == 8
        and fields[1:5] == ["FLOCK", "ADVISORY", "WRITE", str(pid)]
        and fields[5:] == [device_inode, "0", "EOF"]
    ]
    if len(valid) != 1 or len(same_inode) != 1:
        raise ObserverFail("singleton_proc_lock_binding_invalid")
    try:
        after = SINGLETON_LOCK_PATH.lstat()
    except OSError as exc:
        raise ObserverFail("singleton_lock_unavailable") from exc
    if _identity(after) != _identity(before):
        raise ObserverFail("singleton_lock_changed_during_observation")
    return {
        "pid": pid,
        "fd": matching_fds[0],
        "dev": before.st_dev,
        "ino": before.st_ino,
        "mode": "0600",
        "owner": {"uid": EXPECTED_UID, "gid": EXPECTED_GID},
        "granted_write_flock_count": 1,
    }


def _runtime_snapshot(runtime: Any) -> dict[str, Any]:
    try:
        source = _mapping(runtime.source_snapshot(), "runtime_source_invalid")
        active = _mapping(runtime.alr_active_snapshot(), "runtime_active_invalid")
        manager = _mapping(
            runtime.manager_loaded_alr_head(
                expected_head=TARGET_HEAD,
                require_active=True,
            ),
            "runtime_manager_invalid",
        )
        job = runtime.assert_no_queued_systemd_job()
        lane = runtime.assert_lane_quiescent()
        active_confirm = _mapping(
            runtime.alr_active_snapshot(), "runtime_active_invalid"
        )
    except ObserverIssue:
        raise
    except Exception as exc:
        raise ObserverUnverified("runtime_readonly_observation_failed") from exc
    if (
        source.get("uid") != EXPECTED_UID
        or source.get("gid") != EXPECTED_GID
        or source.get("branch") != "main"
        or source.get("head") != TARGET_HEAD
        or source.get("clean") is not True
    ):
        raise ObserverFail("runtime_source_generation_drift")
    identity = _active_identity(active)
    if _active_identity(active_confirm) != identity:
        raise ObserverFail("runtime_identity_changed_during_snapshot")
    manager_identity = _manager_identity(manager)
    if {key: identity[key] for key in manager_identity} != manager_identity:
        raise ObserverFail("runtime_manager_identity_mismatch")
    if job != {"status": "NO_QUEUED_JOB", "unit": UNIT_NAME}:
        raise ObserverFail("runtime_systemd_job_not_quiescent")
    if lane != {"owner": False, "processes": [], "scopes": []}:
        raise ObserverFail("runtime_lane_not_quiescent")
    return {
        "source_head": TARGET_HEAD,
        "service": UNIT_NAME,
        "identity": identity,
        "nrestarts": 0,
        "job": dict(job),
        "lane": dict(lane),
    }


def _fetch_all(
    cursor: Any,
    sql: str,
    params: Sequence[Any] = (),
    *,
    maximum: int,
    overflow_reason: str,
) -> list[Mapping[str, Any]]:
    cursor.execute(sql, tuple(params))
    rows = cursor.fetchall()
    if not isinstance(rows, list) or not all(isinstance(row, Mapping) for row in rows):
        raise ObserverFail("database_rows_invalid")
    if len(rows) > maximum:
        raise ObserverUnverified(overflow_reason)
    return list(rows)


def _fetch_one(
    cursor: Any,
    sql: str,
    params: Sequence[Any] = (),
) -> Mapping[str, Any] | None:
    cursor.execute(sql, tuple(params))
    row = cursor.fetchone()
    if row is None:
        return None
    return _mapping(row, "database_row_invalid")


def _validate_tx_start(row: Mapping[str, Any] | None) -> dict[str, Any]:
    if row is None:
        raise ObserverUnverified("readonly_transaction_guard_missing")
    if (
        row.get("transaction_read_only") != "on"
        or row.get("transaction_isolation") != "repeatable read"
        or row.get("search_path") != "pg_catalog"
        or row.get("statement_timeout") != "15s"
        or row.get("lock_timeout") != "1s"
        or row.get("idle_timeout") != "30s"
        or row.get("current_user") != "alr_shadow"
        or row.get("current_database") != "trading_ai"
        or row.get("server_addr") != "127.0.0.1"
        or row.get("server_port") != 5432
        or row.get("txid_current_if_assigned") is not None
    ):
        raise ObserverFail("readonly_transaction_start_guard_failed")
    return {
        "transaction_read_only": "on",
        "transaction_isolation": "repeatable read",
        "search_path": "pg_catalog",
        "statement_timeout": "15s",
        "lock_timeout": "1s",
        "idle_timeout": "30s",
        "current_user": "alr_shadow",
        "current_database": "trading_ai",
        "server_addr": "127.0.0.1",
        "server_port": 5432,
        "xid_assigned": False,
    }


def _validate_tx_final(row: Mapping[str, Any] | None) -> dict[str, Any]:
    if row is None:
        raise ObserverUnverified("readonly_transaction_effect_guard_missing")
    if (
        row.get("tuples_inserted") != 0
        or row.get("tuples_updated") != 0
        or row.get("tuples_deleted") != 0
        or row.get("txid_current_if_assigned") is not None
    ):
        raise ObserverFail("readonly_transaction_effect_guard_failed")
    return {
        "tuples_inserted": 0,
        "tuples_updated": 0,
        "tuples_deleted": 0,
        "xid_assigned": False,
    }


def _validate_session(
    rows: list[Mapping[str, Any]],
    *,
    lower_bound: datetime,
) -> dict[str, Any]:
    if not rows:
        raise ObserverFail("current_open_session_missing")
    if len(rows) != 1:
        raise ObserverFail("current_open_session_ambiguous")
    row = rows[0]
    session_id = str(row.get("session_id") or "")
    start_event_id = str(row.get("start_event_id") or "")
    started_at = _parse_utc(row.get("started_at"), "current_session_started_at_invalid")
    if (
        UUID_RE.fullmatch(session_id) is None
        or UUID_RE.fullmatch(start_event_id) is None
        or started_at < lower_bound
    ):
        raise ObserverFail("current_open_session_invalid")
    return {
        "session_id": session_id,
        "start_event_id": start_event_id,
        "started_at": started_at,
    }


SCANNER_PAYLOAD_FIELDS = {
    "ts",
    "scan_id",
    "active_symbols",
    "added",
    "removed",
    "rejected_count",
    "scan_duration_ms",
    "candidates",
    "config",
}


def _validate_symbol_list(value: Any, reason: str) -> list[str]:
    if not isinstance(value, list) or len(value) > 10000:
        raise ObserverFail(reason)
    result: list[str] = []
    for item in value:
        result.append(_bounded_text(item, 256, reason))
    if len(result) != len(set(result)):
        raise ObserverFail(reason)
    return result


def _validate_scanner_payload(
    payload: Mapping[str, Any],
    *,
    source_ts: datetime,
    scan_id: str,
    source_hash: str,
) -> None:
    if set(payload) != SCANNER_PAYLOAD_FIELDS:
        raise ObserverFail("cycle_source_payload_fields_invalid")
    expected_ts = source_ts.isoformat().replace("+00:00", "Z")
    if payload.get("ts") != expected_ts or payload.get("scan_id") != scan_id:
        raise ObserverFail("cycle_source_payload_identity_invalid")
    active = _validate_symbol_list(
        payload.get("active_symbols"), "cycle_source_active_symbols_invalid"
    )
    added = _validate_symbol_list(payload.get("added"), "cycle_source_added_invalid")
    removed = _validate_symbol_list(
        payload.get("removed"), "cycle_source_removed_invalid"
    )
    if not set(added).issubset(active) or set(added) & set(removed) or set(removed) & set(active):
        raise ObserverFail("cycle_source_symbol_semantics_invalid")
    _nonnegative(payload.get("rejected_count"), "cycle_source_rejected_count_invalid")
    _nonnegative(payload.get("scan_duration_ms"), "cycle_source_duration_invalid")
    candidates = payload.get("candidates")
    if not isinstance(candidates, list) or len(candidates) > 10000:
        raise ObserverFail("cycle_source_candidates_invalid")
    for candidate in candidates:
        candidate_map = _mapping(candidate, "cycle_source_candidate_invalid")
        _bounded_text(candidate_map.get("symbol"), 256, "cycle_source_candidate_invalid")
    if not isinstance(payload.get("config"), Mapping):
        raise ObserverFail("cycle_source_config_invalid")
    if canonical_sha256(payload) != source_hash:
        raise ObserverFail("cycle_source_payload_hash_mismatch")


def _validate_cycle(
    row: Mapping[str, Any],
    session: Mapping[str, Any],
) -> dict[str, Any] | None:
    details_bytes = row.get("details_bytes")
    rows_seen_text_bytes = row.get("rows_seen_text_bytes")
    if (
        isinstance(details_bytes, bool)
        or not isinstance(details_bytes, int)
        or details_bytes < 0
        or details_bytes > MAX_DETAILS_BYTES
        or row.get("details") is None
    ):
        raise ObserverUnverified("cycle_details_oversize_or_unavailable")
    if (
        isinstance(rows_seen_text_bytes, bool)
        or not isinstance(rows_seen_text_bytes, int)
        or rows_seen_text_bytes < 1
        or rows_seen_text_bytes > 18
    ):
        raise ObserverUnverified("cycle_rows_seen_text_bound_invalid")
    if row.get("rows_seen_kind") != "number":
        raise ObserverFail("cycle_rows_seen_type_invalid")
    rows_seen = row.get("rows_seen_value")
    if isinstance(rows_seen, bool) or not isinstance(rows_seen, int) or rows_seen < 0:
        raise ObserverFail("cycle_rows_seen_invalid")
    if rows_seen == 0:
        return None
    details = _mapping(row.get("details"), "cycle_details_invalid")
    if details.get("rows_seen") != rows_seen:
        raise ObserverFail("cycle_rows_seen_projection_mismatch")
    for field in ("persisted", "duplicates"):
        if field in details:
            _nonnegative(details[field], f"cycle_{field}_invalid")
    if str(row.get("session_id") or "") != session["session_id"]:
        raise ObserverFail("cycle_session_mismatch")
    notification_values = (
        row.get("notification_event_id"),
        row.get("notification_recorded_at"),
        row.get("notification_ts_ms"),
    )
    if notification_values == (None, None, None):
        # Startup drain/catch-up can persist a positive LANE_SUCCESS without a
        # NOTIFICATION_CONSUMED event.  It is not an acceptance cycle.
        return None
    if any(value is None for value in notification_values):
        raise ObserverFail("cycle_notification_binding_invalid")
    event_id = str(row.get("lane_success_event_id") or "")
    notification_id = str(row.get("notification_event_id") or "")
    if UUID_RE.fullmatch(event_id) is None or UUID_RE.fullmatch(notification_id) is None:
        raise ObserverFail("cycle_notification_binding_invalid")
    lane_at = _parse_utc(row.get("lane_success_recorded_at"), "cycle_recorded_at_invalid")
    source_at = _parse_utc(row.get("source_ts"), "cycle_source_ts_invalid")
    notification_at = _parse_utc(
        row.get("notification_recorded_at"),
        "cycle_notification_recorded_at_invalid",
    )
    if not session["started_at"] <= notification_at <= lane_at or source_at > notification_at:
        raise ObserverFail("cycle_time_causality_invalid")
    lane_scan_id = _bounded_text(
        row.get("lane_source_scan_id"), MAX_SCAN_ID_BYTES, "cycle_lane_scan_id_invalid"
    )
    if row.get("lane_source_scan_id_bytes") != len(lane_scan_id.encode()):
        raise ObserverUnverified("cycle_lane_scan_id_size_invalid")
    source_hash = _hash(row.get("source_hash"), "cycle_source_hash_invalid")
    source_key = _bounded_text(
        row.get("source_key"), MAX_SOURCE_KEY_BYTES, "cycle_source_key_invalid"
    )
    scan_id = _bounded_text(
        row.get("source_scan_id"), MAX_SCAN_ID_BYTES, "cycle_source_scan_id_invalid"
    )
    if (
        row.get("source_key_bytes") != len(source_key.encode())
        or row.get("source_scan_id_bytes") != len(scan_id.encode())
    ):
        raise ObserverUnverified("cycle_source_string_size_invalid")
    if (
        row.get("source_table") != "trading.scanner_snapshots"
        or row.get("cycle_schema_version") != "alr_scanner_cycle_v1"
        or row.get("source_artifact_kind") != "scanner_cycle"
        or _parse_utc(row.get("typed_source_ts"), "cycle_typed_source_ts_invalid")
        != source_at
        or row.get("typed_source_hash") != source_hash
        or scan_id != lane_scan_id
        or source_key != f"{scan_id}|{source_at.isoformat().replace('+00:00', 'Z')}"
    ):
        raise ObserverFail("cycle_typed_source_identity_invalid")
    payload_bytes = row.get("source_payload_bytes")
    if (
        isinstance(payload_bytes, bool)
        or not isinstance(payload_bytes, int)
        or payload_bytes < 0
        or payload_bytes > MAX_SOURCE_PAYLOAD_BYTES
        or row.get("source_canonical_payload") is None
    ):
        raise ObserverUnverified("cycle_source_payload_oversize_or_unavailable")
    payload = _mapping(row.get("source_canonical_payload"), "cycle_source_payload_invalid")
    if len(canonical_bytes(payload)) > MAX_SOURCE_PAYLOAD_BYTES:
        raise ObserverUnverified("cycle_source_payload_canonical_oversize")
    _validate_scanner_payload(
        payload,
        source_ts=source_at,
        scan_id=scan_id,
        source_hash=source_hash,
    )
    notification_ts_ms = row.get("notification_ts_ms")
    notification_ts_ms = _nonnegative(
        notification_ts_ms, "cycle_notification_ts_invalid"
    )
    expected_notification_ts_ms = int(source_at.timestamp() * 1000)
    if notification_ts_ms != expected_notification_ts_ms:
        raise ObserverFail("cycle_notification_source_timestamp_mismatch")
    return {
        "event_id": event_id,
        "recorded_at": lane_at,
        "source_ts": source_at,
        "source_scan_id": scan_id,
        "source_hash": source_hash,
        "source_key": source_key,
        "cursor_key": (source_at, scan_id),
        "details": {
            "rows_seen": rows_seen,
            "persisted": details.get("persisted"),
            "duplicates": details.get("duplicates"),
        },
        "notification": {
            "event_id": notification_id,
            "recorded_at": notification_at,
            "notification_ts_ms": notification_ts_ms,
        },
    }


CANDIDATE_DECISION_FIELDS = {
    "schema_version",
    "decision_code",
    "evaluated_at",
    "source_head",
    "source_set_hash",
    "evidence_source_status",
    "evidence_selection_hash",
    "candidate_set_hash",
    "policy_hash",
    "selected_candidate",
    "selected_collection_target",
    "candidate_count",
    "eligible_candidate_count",
    "evaluated_candidates",
    *FALSE_CLAIMS,
    "no_authority",
    "authority_counters",
    "decision_hash",
}
CANDIDATE_ARTIFACT_FIELDS = {
    "schema_version",
    "decision_code",
    "decision_hash",
    "selected_candidate",
    "selected_collection_target",
    "decision",
    "source_refs",
    *FALSE_CLAIMS,
    "next_stage",
    "no_authority",
    "authority_counters",
}
CANDIDATE_SOURCE_REF_FIELDS = {
    "evidence_source_status",
    "evidence_selection_hash",
    "candidate_set_hash",
    "handoff",
}
CANDIDATE_HANDOFF_FIELDS = {
    "schema_version",
    "evidence",
    "source_head",
    "source_set_hash",
    "source_cursor",
    "decision_time",
    "policy_input_hash",
    "policy_config_hash",
    "prior_decisions_hash",
    "handoff_hash",
}
CANDIDATE_EVIDENCE_FIELDS = {
    "schema_version",
    "source_status",
    "source_content_sha256",
    "board_hash",
    "selection_hash",
    "audit_hash",
    "candidate_set_hash",
    "generated_at",
    "evaluated_at",
    "cost_source_payload_sha256",
    "cost_normalized_projection_sha256",
    "cost_source_asof_utc",
}


def _validate_edges(
    edges: list[Mapping[str, Any]],
    *,
    artifact_hash: str,
    cycle: Mapping[str, Any],
) -> tuple[list[str], list[tuple[datetime, str, str, str]]]:
    if not edges:
        raise ObserverFail("decision_training_input_edges_missing")
    hashes: list[str] = []
    identities: list[tuple[datetime, str, str, str]] = []
    seen: set[str] = set()
    for edge in edges:
        from_hash = _hash(
            edge.get("from_artifact_hash"), "decision_edge_source_hash_invalid"
        )
        source_key = _bounded_text(
            edge.get("source_key"), MAX_SOURCE_KEY_BYTES, "decision_edge_source_key_invalid"
        )
        scan_id = _bounded_text(
            edge.get("source_scan_id"), MAX_SCAN_ID_BYTES, "decision_edge_scan_id_invalid"
        )
        if (
            edge.get("source_key_bytes") != len(source_key.encode())
            or edge.get("source_scan_id_bytes") != len(scan_id.encode())
        ):
            raise ObserverUnverified("decision_edge_string_size_invalid")
        source_at = _parse_utc(edge.get("source_ts"), "decision_edge_source_ts_invalid")
        if (
            edge.get("to_artifact_hash") != artifact_hash
            or edge.get("edge_role") != "training_input"
            or edge.get("source_hash") != from_hash
            or edge.get("source_table") != "trading.scanner_snapshots"
            or edge.get("cycle_schema_version") != "alr_scanner_cycle_v1"
            or source_key != f"{scan_id}|{source_at.isoformat().replace('+00:00', 'Z')}"
            or from_hash in seen
        ):
            raise ObserverFail("decision_training_input_edge_invalid")
        edge_body = {
            "from_artifact_hash": from_hash,
            "to_artifact_hash": artifact_hash,
            "edge_role": "training_input",
        }
        if edge.get("edge_hash") != canonical_sha256(edge_body):
            raise ObserverFail("decision_training_input_edge_hash_mismatch")
        if source_at > cycle["source_ts"]:
            raise ObserverFail("decision_edge_after_cursor")
        hashes.append(from_hash)
        identities.append((source_at, source_key, from_hash, scan_id))
        seen.add(from_hash)
    if identities != sorted(identities):
        raise ObserverFail("decision_source_identity_order_invalid")
    if identities[-1] != (
        cycle["source_ts"],
        cycle["source_key"],
        cycle["source_hash"],
        cycle["source_scan_id"],
    ):
        raise ObserverFail("decision_source_set_cursor_mismatch")
    return hashes, identities


def _validate_decision(
    row: Mapping[str, Any],
    edges: list[Mapping[str, Any]],
    cycle: Mapping[str, Any],
) -> dict[str, Any]:
    payload_bytes = row.get("payload_bytes")
    if (
        isinstance(payload_bytes, bool)
        or not isinstance(payload_bytes, int)
        or payload_bytes < 0
        or payload_bytes > MAX_DECISION_PAYLOAD_BYTES
        or row.get("canonical_payload") is None
    ):
        raise ObserverUnverified("decision_payload_oversize_or_unavailable")
    payload = _mapping(row.get("canonical_payload"), "decision_payload_invalid")
    if len(canonical_bytes(payload)) > MAX_DECISION_PAYLOAD_BYTES:
        raise ObserverUnverified("decision_payload_canonical_oversize")
    artifact_hash = _hash(row.get("artifact_hash"), "decision_artifact_hash_invalid")
    created_at = _parse_utc(row.get("created_at"), "decision_created_at_invalid")
    if row.get("artifact_kind") != "target_rotation" or created_at < cycle["recorded_at"]:
        raise ObserverFail("decision_artifact_identity_or_time_invalid")
    _exact_fields(payload, CANDIDATE_ARTIFACT_FIELDS, "decision_artifact_fields_invalid")
    if (
        payload.get("schema_version")
        != "alr_candidate_learning_projection_artifact_v2"
        or artifact_hash != canonical_sha256(payload)
    ):
        raise ObserverFail("decision_artifact_hash_or_schema_invalid")
    for field in FALSE_CLAIMS:
        if payload.get(field) is not False:
            raise ObserverFail("decision_outer_false_claim_invalid")
    _require_no_authority(payload.get("no_authority"), "decision_outer_authority_invalid")
    _require_zero_counters(
        payload.get("authority_counters"),
        ZERO_COUNTERS,
        "decision_outer_authority_counters_invalid",
    )
    decision = _mapping(payload.get("decision"), "decision_nested_missing")
    _exact_fields(decision, CANDIDATE_DECISION_FIELDS, "decision_nested_fields_invalid")
    expected_evaluated = _utc_z_seconds(
        cycle["source_ts"], "decision_cycle_source_ts_invalid"
    )
    if (
        decision.get("schema_version") != "alr_candidate_learning_decision_v2"
        or decision.get("decision_code") != DECISION_CODE
        or decision.get("evaluated_at") != expected_evaluated
        or decision.get("source_head") != TARGET_HEAD
        or decision.get("evidence_source_status") != "READY"
        or decision.get("evidence_selection_hash") != SELECTION_HASH
        or decision.get("candidate_set_hash") != CANDIDATE_SET_HASH
        or decision.get("candidate_count") != 0
        or decision.get("eligible_candidate_count") != 0
        or decision.get("evaluated_candidates") != []
        or decision.get("selected_candidate") is not None
        or decision.get("selected_collection_target") is not None
    ):
        raise ObserverFail("decision_semantics_invalid")
    policy_hash = _hash(decision.get("policy_hash"), "decision_policy_hash_invalid")
    for field in FALSE_CLAIMS:
        if decision.get(field) is not False:
            raise ObserverFail("decision_nested_false_claim_invalid")
    _require_no_authority(decision.get("no_authority"), "decision_no_authority_invalid")
    _require_zero_counters(
        decision.get("authority_counters"),
        ZERO_COUNTERS,
        "decision_authority_counters_invalid",
    )
    decision_hash = _hash(decision.get("decision_hash"), "decision_hash_invalid")
    if decision_hash != canonical_sha256(
        {key: value for key, value in decision.items() if key != "decision_hash"}
    ):
        raise ObserverFail("decision_hash_mismatch")
    if (
        payload.get("decision_code") != DECISION_CODE
        or payload.get("decision_hash") != decision_hash
        or payload.get("selected_candidate") is not None
        or payload.get("selected_collection_target") is not None
        or payload.get("next_stage") != "WP4_VERSIONED_TRAINING_SCHEMA_REQUIRED"
    ):
        raise ObserverFail("decision_payload_binding_invalid")
    refs = _mapping(payload.get("source_refs"), "decision_source_refs_missing")
    _exact_fields(refs, CANDIDATE_SOURCE_REF_FIELDS, "decision_source_refs_fields_invalid")
    if (
        refs.get("evidence_source_status") != "READY"
        or refs.get("evidence_selection_hash") != SELECTION_HASH
        or refs.get("candidate_set_hash") != CANDIDATE_SET_HASH
    ):
        raise ObserverFail("decision_source_refs_invalid")
    handoff = _mapping(refs.get("handoff"), "decision_handoff_missing")
    _exact_fields(handoff, CANDIDATE_HANDOFF_FIELDS, "decision_handoff_fields_invalid")
    if (
        handoff.get("schema_version") != "alr_candidate_board_handoff_v1"
        or handoff.get("source_head") != TARGET_HEAD
        or handoff.get("decision_time") != expected_evaluated
        or handoff.get("policy_config_hash") != policy_hash
    ):
        raise ObserverFail("decision_handoff_binding_invalid")
    for field in ("policy_input_hash", "prior_decisions_hash"):
        _hash(handoff.get(field), f"decision_handoff_{field}_invalid")
    handoff_hash = _hash(handoff.get("handoff_hash"), "decision_handoff_hash_invalid")
    if handoff_hash != canonical_sha256(
        {key: value for key, value in handoff.items() if key != "handoff_hash"}
    ):
        raise ObserverFail("decision_handoff_hash_mismatch")
    expected_cursor = {
        "source_hash": cycle["source_hash"],
        "source_key": cycle["source_key"],
        "source_ts": expected_evaluated,
    }
    if handoff.get("source_cursor") != expected_cursor:
        raise ObserverFail("decision_handoff_cursor_mismatch")
    evidence = _mapping(handoff.get("evidence"), "decision_handoff_evidence_missing")
    _exact_fields(evidence, CANDIDATE_EVIDENCE_FIELDS, "decision_evidence_fields_invalid")
    if (
        evidence.get("schema_version") != "alr_candidate_evidence_snapshot_v2"
        or evidence.get("source_status") != "READY"
        or evidence.get("source_content_sha256") != BOARD_SOURCE_CONTENT_SHA256
        or evidence.get("board_hash") != BOARD_HASH
        or evidence.get("audit_hash") != BOARD_AUDIT_HASH
        or evidence.get("selection_hash") != SELECTION_HASH
        or evidence.get("candidate_set_hash") != CANDIDATE_SET_HASH
        or evidence.get("evaluated_at") != expected_evaluated
    ):
        raise ObserverFail("decision_handoff_evidence_invalid")
    generated_at = _parse_utc(
        evidence.get("generated_at"), "decision_evidence_generated_at_invalid"
    )
    evaluated_at = _parse_utc(expected_evaluated, "decision_evaluated_at_invalid")
    if generated_at > evaluated_at or evaluated_at > created_at:
        raise ObserverFail("decision_time_causality_invalid")
    for field in ("cost_source_payload_sha256", "cost_normalized_projection_sha256"):
        if evidence.get(field) is not None:
            _hash(evidence[field], f"decision_{field}_invalid")
    if evidence.get("cost_source_asof_utc") is not None:
        if _parse_utc(evidence["cost_source_asof_utc"], "decision_cost_time_invalid") > generated_at:
            raise ObserverFail("decision_cost_time_causality_invalid")
    source_hashes, _source_identities = _validate_edges(
        edges, artifact_hash=artifact_hash, cycle=cycle
    )
    source_set_hash = canonical_sha256(source_hashes)
    if (
        decision.get("source_set_hash") != source_set_hash
        or handoff.get("source_set_hash") != source_set_hash
    ):
        raise ObserverFail("decision_source_set_hash_mismatch")
    return {
        "artifact_hash": artifact_hash,
        "created_at": created_at,
        "decision_hash": decision_hash,
        "handoff_hash": handoff_hash,
        "source_set_hash": source_set_hash,
        "source_count": len(source_hashes),
        "policy_hash": policy_hash,
        "decision_code": DECISION_CODE,
    }


WRITE_METRIC_GROUP_FIELDS = {
    "health": {
        "attempts",
        "emitted",
        "state_delta_writes",
        "heartbeat_writes",
        "writes_suppressed",
        "rows_written",
        "payload_bytes_written",
        "suppression_ratio",
    },
    "decision": {
        "attempts",
        "writes_suppressed",
        "duplicate_retries",
        "artifact_rows_written",
        "provenance_rows_written",
        "run_rows_written",
        "feedback_rows_written",
        "defer_artifact_rows_written",
        "payload_bytes_written",
        "source_rows_consumed",
        "suppression_ratio",
    },
    "feedback": {
        "attempts",
        "persisted",
        "duplicate_retries",
        "persisted_ratio",
        "duplicate_retry_ratio",
        "artifact_rows_written",
        "provenance_rows_written",
        "event_rows_written",
        "total_rows_written",
        "payload_bytes_written",
    },
}


def _validate_metric_group(group: Mapping[str, Any], fields: set[str], reason: str) -> None:
    if set(group) != fields:
        raise ObserverFail(reason)
    for key, value in group.items():
        if key.endswith("ratio"):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1:
                raise ObserverFail(reason)
        else:
            _nonnegative(value, reason)


def _validate_health(
    row: Mapping[str, Any],
    cycle: Mapping[str, Any],
    decision: Mapping[str, Any],
    session_id: str,
) -> dict[str, Any]:
    payload_bytes = row.get("payload_bytes")
    if (
        isinstance(payload_bytes, bool)
        or not isinstance(payload_bytes, int)
        or payload_bytes < 0
        or payload_bytes > MAX_HEALTH_PAYLOAD_BYTES
        or row.get("canonical_payload") is None
    ):
        raise ObserverUnverified("health_payload_oversize_or_unavailable")
    payload = _mapping(row.get("canonical_payload"), "health_payload_invalid")
    if len(canonical_bytes(payload)) > MAX_HEALTH_PAYLOAD_BYTES:
        raise ObserverUnverified("health_payload_canonical_oversize")
    snapshot_hash = _hash(row.get("snapshot_hash"), "health_snapshot_hash_invalid")
    if payload.get("snapshot_hash") != snapshot_hash or snapshot_hash != canonical_sha256(
        {key: value for key, value in payload.items() if key != "snapshot_hash"}
    ):
        raise ObserverFail("health_snapshot_hash_mismatch")
    recorded_at = _parse_utc(row.get("recorded_at"), "health_recorded_at_invalid")
    observed_at = _parse_utc(payload.get("observed_at"), "health_observed_at_invalid")
    if (
        payload.get("schema_version") != "alr_health_snapshot_v2"
        or payload.get("source_head") != TARGET_HEAD
        or row.get("source_head") != TARGET_HEAD
        or not decision["created_at"] <= observed_at <= recorded_at
    ):
        raise ObserverFail("health_payload_binding_invalid")
    if (
        _parse_utc(row.get("fresh_cursor_ts"), "health_cursor_ts_invalid")
        != cycle["source_ts"]
        or row.get("fresh_cursor_scan_id") != cycle["source_scan_id"]
    ):
        raise ObserverFail("health_typed_cursor_mismatch")
    watermark = _mapping(payload.get("watermark"), "health_watermark_missing")
    if (
        set(watermark) != {"source_ts", "source_scan_id", "source_hash"}
        or _parse_utc(
            watermark.get("source_ts"), "health_watermark_source_ts_invalid"
        )
        != cycle["source_ts"]
        or watermark.get("source_scan_id") != cycle["source_scan_id"]
        or watermark.get("source_hash") != cycle["source_hash"]
    ):
        raise ObserverFail("health_watermark_mismatch")
    ingestion = _mapping(payload.get("ingestion"), "health_ingestion_missing")
    if (
        _parse_utc(
            ingestion.get("fresh_cursor_ts"),
            "health_ingestion_cursor_ts_invalid",
        )
        != cycle["source_ts"]
        or ingestion.get("fresh_cursor_scan_id") != cycle["source_scan_id"]
    ):
        raise ObserverFail("health_ingestion_cursor_mismatch")
    target = _mapping(payload.get("target"), "health_target_missing")
    if set(target) != {"run_hash", "candidate_artifact_hash", "run_status"}:
        raise ObserverFail("health_target_fields_invalid")
    run_hash = _hash(target.get("run_hash"), "health_target_run_hash_invalid")
    candidate_hash = _hash(
        target.get("candidate_artifact_hash"), "health_target_candidate_hash_invalid"
    )
    run_status = _bounded_text(target.get("run_status"), 64, "health_target_status_invalid")
    if run_status != "DEFER_EVIDENCE":
        raise ObserverFail("health_target_not_defer")
    _require_no_authority(payload.get("no_authority"), "health_no_authority_invalid")
    _require_zero_counters(
        payload.get("authority_counters"),
        HEALTH_ZERO_COUNTERS,
        "health_authority_counters_invalid",
    )
    failure = _mapping(payload.get("failure"), "health_failure_missing")
    recovery = _mapping(payload.get("restart_recovery"), "health_restart_recovery_missing")
    failure_count = _nonnegative(failure.get("count"), "health_failure_count_invalid")
    restart_count = _nonnegative(
        recovery.get("restart_count"), "health_restart_count_invalid"
    )
    unclean_count = _nonnegative(
        recovery.get("unclean_recovery_count"), "health_unclean_count_invalid"
    )
    duplicate_count = _nonnegative(
        recovery.get("source_duplicate_key_count"), "health_duplicate_count_invalid"
    )
    if recovery.get("watermark_present") is not True:
        raise ObserverFail("health_watermark_not_present")
    last_success_at = _parse_utc(
        recovery.get("last_success_at"), "health_last_success_at_invalid"
    )
    if not cycle["recorded_at"] <= last_success_at <= observed_at:
        raise ObserverFail("health_last_success_time_invalid")
    notifications = payload.get("notifications")
    notification_duplicate_count = 0
    if notifications is not None:
        notification_map = _mapping(notifications, "health_notifications_invalid")
        for field in ("received", "consumed", "duplicate", "invalid"):
            _nonnegative(notification_map.get(field), "health_notifications_invalid")
        notification_duplicate_count = notification_map["duplicate"]
    metrics = _mapping(payload.get("write_metrics"), "health_write_metrics_missing")
    if set(metrics) != {"schema_version", "scope", "health", "decision", "feedback"}:
        raise ObserverFail("health_write_metrics_fields_invalid")
    if metrics.get("schema_version") != "alr_write_metrics_v1":
        raise ObserverFail("health_write_metrics_schema_invalid")
    scope = _mapping(metrics.get("scope"), "health_write_metrics_scope_missing")
    if scope.get("kind") != "consumer_session_cumulative" or scope.get("session_id") != session_id:
        raise ObserverFail("health_write_metrics_scope_invalid")
    validated_groups: dict[str, Mapping[str, Any]] = {}
    for name, fields in WRITE_METRIC_GROUP_FIELDS.items():
        group = _mapping(metrics.get(name), f"health_write_metrics_{name}_missing")
        _validate_metric_group(group, fields, f"health_write_metrics_{name}_invalid")
        validated_groups[name] = group
    health_attempts = _positive(
        validated_groups["health"].get("attempts"), "health_attempts_invalid"
    )
    decision_attempts = _positive(
        validated_groups["decision"].get("attempts"),
        "health_decision_attempts_invalid",
    )
    if scope.get("through_completed_health_attempt") != health_attempts:
        raise ObserverFail("health_completed_attempt_scope_mismatch")
    return {
        "snapshot_hash": snapshot_hash,
        "recorded_at": recorded_at,
        "observed_at": observed_at,
        "health_attempts": health_attempts,
        "decision_attempts": decision_attempts,
        "failure_count": failure_count,
        "restart_count": restart_count,
        "unclean_recovery_count": unclean_count,
        "source_duplicate_key_count": duplicate_count,
        "notification_duplicate_count": notification_duplicate_count,
        "target": {
            "run_hash": run_hash,
            "candidate_artifact_hash": candidate_hash,
            "run_status": run_status,
        },
    }


def _validate_bundle_pair(first: Mapping[str, Any], second: Mapping[str, Any]) -> None:
    if first["cycle"]["event_id"] == second["cycle"]["event_id"]:
        raise ObserverFail("lane_success_events_not_distinct")
    if first["cycle"]["notification"]["event_id"] == second["cycle"]["notification"]["event_id"]:
        raise ObserverFail("consumed_notifications_not_distinct")
    if second["cycle"]["cursor_key"] <= first["cycle"]["cursor_key"]:
        raise ObserverFail("natural_cycle_cursor_not_monotonic")
    first_health = first["health"]
    second_health = second["health"]
    if first_health["snapshot_hash"] == second_health["snapshot_hash"]:
        raise ObserverFail("health_snapshots_not_distinct")
    if second_health["health_attempts"] <= first_health["health_attempts"]:
        raise ObserverFail("health_attempts_not_increasing")
    if second_health["decision_attempts"] <= first_health["decision_attempts"]:
        raise ObserverFail("health_decision_attempts_not_increasing")
    for field, reason in (
        ("failure_count", "health_failure_count_increased"),
        ("restart_count", "health_restart_count_increased"),
        ("unclean_recovery_count", "health_unclean_count_increased"),
        ("source_duplicate_key_count", "health_source_duplicate_count_increased"),
        ("notification_duplicate_count", "health_notification_duplicate_count_increased"),
    ):
        if second_health[field] > first_health[field]:
            raise ObserverFail(reason)
    if first_health["target"] != second_health["target"]:
        raise ObserverFail("health_targets_not_identical")


def _validate_standing(
    row: Mapping[str, Any] | None,
    target: Mapping[str, Any],
) -> tuple[str, dict[str, Any] | None, str | None]:
    if row is None:
        return "PENDING", None, "latest_global_run_not_observed"
    run_hash = _hash(row.get("run_hash"), "standing_run_hash_invalid")
    candidate_hash = _hash(
        row.get("candidate_artifact_hash"), "standing_candidate_hash_invalid"
    )
    run_status = row.get("run_status")
    if (
        row.get("bound_to_both_health_targets") is not True
        or run_hash != target["run_hash"]
        or candidate_hash != target["candidate_artifact_hash"]
        or run_status != target["run_status"]
    ):
        raise ObserverFail("standing_latest_run_health_target_mismatch")
    _require_no_authority(row.get("run_no_authority"), "standing_run_authority_invalid")
    _require_zero_counters(
        row.get("run_authority_counters"),
        ZERO_COUNTERS,
        "standing_run_authority_counters_invalid",
    )
    if row.get("feedback_status") is None:
        return (
            "PENDING",
            {
                "run_hash": run_hash,
                "candidate_artifact_hash": candidate_hash,
                "run_status": run_status,
                "feedback_status": None,
            },
            "latest_global_run_feedback_pending",
        )
    if (
        run_status != "DEFER_EVIDENCE"
        or row.get("feedback_status") != "DEFER_EVIDENCE"
        or row.get("proof_packet_present") is not False
        or row.get("reward_record_count") != 0
        or row.get("rotate_next_target") is not True
        or row.get("global_stop") is not False
    ):
        raise ObserverFail("standing_defer_invalid")
    _require_no_authority(
        row.get("feedback_no_authority"), "standing_feedback_authority_invalid"
    )
    _require_zero_counters(
        row.get("feedback_authority_counters"),
        ZERO_COUNTERS,
        "standing_feedback_authority_counters_invalid",
    )
    return (
        "PASS",
        {
            "scope": "latest_global_run_bound_to_both_post_restart_health_snapshots",
            "run_hash": run_hash,
            "candidate_artifact_hash": candidate_hash,
            "run_status": run_status,
            "feedback_status": "DEFER_EVIDENCE",
            "proof_packet_present": False,
            "reward_record_count": 0,
            "rotate_next_target": True,
            "global_stop": False,
            "current_source_head_or_fit_claimed": False,
        },
        None,
    )


def _observe_database(
    connection: Any,
    *,
    lower_bound: datetime,
) -> dict[str, Any]:
    transaction_started = False
    pending_issue: ObserverIssue | None = None
    transaction_start: dict[str, Any] | None = None
    transaction_final: dict[str, Any] | None = None
    evidence: dict[str, Any] = {}
    try:
        connection.set_session(
            readonly=True,
            isolation_level="REPEATABLE READ",
            autocommit=False,
        )
        transaction_started = True
        with connection.cursor() as cursor:
            transaction_start = _validate_tx_start(_fetch_one(cursor, TX_START_SQL))
            try:
                session = _validate_session(
                    _fetch_all(
                        cursor,
                        OPEN_SESSION_SQL,
                        maximum=2,
                        overflow_reason="open_session_row_limit_exceeded",
                    ),
                    lower_bound=lower_bound,
                )
                cycle_probe = _fetch_all(
                    cursor,
                    CYCLES_SQL,
                    (session["session_id"], session["started_at"]),
                    maximum=MAX_CYCLES + 1,
                    overflow_reason="cycle_query_probe_limit_exceeded",
                )
                window_truncated = len(cycle_probe) == MAX_CYCLES + 1
                raw_cycles = list(reversed(cycle_probe[:MAX_CYCLES]))
                cycle_window = {
                    "scope": (
                        "latest_notification_backed_lane_success_rows_"
                        "in_current_post_pin_session"
                    ),
                    "query_order": (
                        "source_ts_desc_scan_id_desc_event_id_desc"
                    ),
                    "probe_limit": MAX_CYCLES + 1,
                    "evaluated_limit": MAX_CYCLES,
                    "observed_rows": len(cycle_probe),
                    "evaluated_rows": len(raw_cycles),
                    "truncated": window_truncated,
                    "full_history_scan_claimed": False,
                }
                validated_cycles: list[dict[str, Any]] = []
                last_cursor: tuple[datetime, str] | None = None
                last_source_hash: str | None = None
                last_source_key: str | None = None
                for raw_cycle in raw_cycles:
                    cycle = _validate_cycle(raw_cycle, session)
                    if cycle is None:
                        continue
                    if last_cursor is not None:
                        if cycle["cursor_key"] < last_cursor:
                            raise ObserverFail("natural_cycle_cursor_not_monotonic")
                        if cycle["cursor_key"] == last_cursor:
                            if (
                                cycle["source_hash"] != last_source_hash
                                or cycle["source_key"] != last_source_key
                            ):
                                raise ObserverFail(
                                    "natural_cycle_cursor_identity_conflict"
                                )
                            # A legal notification retry can persist another
                            # positive LANE_SUCCESS for the same scanner cursor.
                            # It is validated but cannot become another cycle.
                            continue
                    last_cursor = cycle["cursor_key"]
                    last_source_hash = cycle["source_hash"]
                    last_source_key = cycle["source_key"]
                    validated_cycles.append(cycle)

                # Validate ordering and same-cursor identity across the whole
                # bounded window before selecting the first two complete
                # cycle/decision/health bundles from that scope.
                bundles: list[dict[str, Any]] = []
                excluded_health_hash = "0" * 64
                for cycle in validated_cycles:
                    cycle_time = _utc_z_seconds(
                        cycle["source_ts"], "decision_cycle_source_ts_invalid"
                    )
                    decision_rows = _fetch_all(
                        cursor,
                        DECISION_SQL,
                        (
                            TARGET_HEAD,
                            DECISION_CODE,
                            cycle_time,
                            BOARD_SOURCE_CONTENT_SHA256,
                            BOARD_HASH,
                            BOARD_AUDIT_HASH,
                            SELECTION_HASH,
                            CANDIDATE_SET_HASH,
                            cycle["source_hash"],
                            cycle["source_key"],
                            cycle_time,
                        ),
                        maximum=2,
                        overflow_reason="decision_row_limit_exceeded",
                    )
                    if not decision_rows:
                        continue
                    if len(decision_rows) != 1:
                        raise ObserverFail("decision_same_cursor_ambiguous")
                    decision_row = decision_rows[0]
                    edge_rows = _fetch_all(
                        cursor,
                        EDGES_SQL,
                        (decision_row.get("artifact_hash"),),
                        maximum=MAX_EDGES,
                        overflow_reason="decision_edge_row_limit_exceeded",
                    )
                    decision = _validate_decision(decision_row, edge_rows, cycle)
                    health = _fetch_one(
                        cursor,
                        HEALTH_SQL,
                        (
                            TARGET_HEAD,
                            decision["created_at"],
                            cycle["source_ts"],
                            cycle["source_scan_id"],
                            cycle["source_hash"],
                            excluded_health_hash,
                        ),
                    )
                    if health is None:
                        continue
                    validated_health = _validate_health(
                        health,
                        cycle,
                        decision,
                        session["session_id"],
                    )
                    excluded_health_hash = validated_health["snapshot_hash"]
                    bundles.append(
                        {
                            "cycle": cycle,
                            "decision": decision,
                            "health": validated_health,
                        }
                    )
                    if len(bundles) > 2:
                        bundles = bundles[-2:]
                standing_status = "PENDING"
                standing: dict[str, Any] | None = None
                standing_reason: str | None = "two_natural_cycles_not_yet_observed"
                if len(bundles) == 2:
                    _validate_bundle_pair(bundles[0], bundles[1])
                    target = bundles[0]["health"]["target"]
                    standing_row = _fetch_one(
                        cursor,
                        STANDING_DEFER_SQL,
                        (
                            target["run_hash"],
                            target["candidate_artifact_hash"],
                            target["run_status"],
                            bundles[1]["health"]["target"]["run_hash"],
                            bundles[1]["health"]["target"]["candidate_artifact_hash"],
                            bundles[1]["health"]["target"]["run_status"],
                        ),
                    )
                    standing_status, standing, standing_reason = _validate_standing(
                        standing_row, target
                    )
                repeated_session = _validate_session(
                    _fetch_all(
                        cursor,
                        OPEN_SESSION_SQL,
                        maximum=2,
                        overflow_reason="open_session_row_limit_exceeded",
                    ),
                    lower_bound=lower_bound,
                )
                if repeated_session != session:
                    raise ObserverFail("current_open_session_changed_during_observation")
                evidence = {
                    "session": session,
                    "cycle_window": cycle_window,
                    "bundles": bundles,
                    "standing_status": standing_status,
                    "standing": standing,
                    "standing_reason": standing_reason,
                }
            except ObserverIssue as exc:
                pending_issue = exc
            except Exception as exc:
                pending_issue = ObserverUnverified(
                    "database_observation_failed:" + type(exc).__name__
                )
            try:
                transaction_final = _validate_tx_final(_fetch_one(cursor, TX_FINAL_SQL))
            except ObserverIssue as exc:
                if pending_issue is None or isinstance(exc, ObserverFail):
                    pending_issue = exc
            except Exception as exc:
                pending_issue = ObserverUnverified(
                    "readonly_transaction_effect_guard_unavailable:"
                    + type(exc).__name__
                )
    except ObserverIssue:
        raise
    except Exception as exc:
        raise ObserverUnverified("readonly_transaction_unavailable") from exc
    finally:
        if transaction_started:
            try:
                connection.rollback()
            except Exception:
                if pending_issue is None:
                    pending_issue = ObserverUnverified(
                        "readonly_transaction_rollback_unverified"
                    )
        try:
            connection.close()
        except Exception:
            if pending_issue is None:
                pending_issue = ObserverUnverified(
                    "readonly_connection_close_unverified"
                )
    if pending_issue is not None:
        raise pending_issue
    evidence["transaction"] = {
        "start": transaction_start,
        "final": transaction_final,
        "rolled_back": True,
    }
    return evidence


def _public_cycle(bundle: Mapping[str, Any]) -> dict[str, Any]:
    cycle = bundle["cycle"]
    decision = bundle["decision"]
    health = bundle["health"]
    return {
        "lane_success_event_id": cycle["event_id"],
        "lane_success_recorded_at": cycle["recorded_at"].isoformat().replace(
            "+00:00", "Z"
        ),
        "cursor": {
            "source_ts": cycle["source_ts"].isoformat().replace("+00:00", "Z"),
            "source_scan_id": cycle["source_scan_id"],
            "source_hash": cycle["source_hash"],
            "source_key": cycle["source_key"],
        },
        "notification": {
            "event_id": cycle["notification"]["event_id"],
            "recorded_at": cycle["notification"]["recorded_at"].isoformat().replace(
                "+00:00", "Z"
            ),
            "notification_ts_ms": cycle["notification"]["notification_ts_ms"],
        },
        "source_artifact": {
            "artifact_kind": "scanner_cycle",
            "canonical_payload_hash_verified": True,
        },
        "decision": {
            key: decision[key]
            for key in (
                "artifact_hash",
                "decision_hash",
                "handoff_hash",
                "source_set_hash",
                "source_count",
                "policy_hash",
                "decision_code",
            )
        },
        "health": {
            "snapshot_hash": health["snapshot_hash"],
            "observed_at": health["observed_at"].isoformat().replace("+00:00", "Z"),
            "health_attempts": health["health_attempts"],
            "decision_attempts": health["decision_attempts"],
            "failure_count": health["failure_count"],
            "restart_count": health["restart_count"],
            "unclean_recovery_count": health["unclean_recovery_count"],
            "source_duplicate_key_count": health["source_duplicate_key_count"],
            "target": dict(health["target"]),
        },
    }


def _base_result(now: Callable[[], datetime]) -> dict[str, Any]:
    observed_at = now()
    if observed_at.tzinfo is None or observed_at.utcoffset() is None:
        observed_at = observed_at.replace(tzinfo=timezone.utc)
    return {
        "schema_version": SCHEMA,
        "observed_at_utc": observed_at.astimezone(timezone.utc).isoformat().replace(
            "+00:00", "Z"
        ),
        "status": "UNVERIFIED",
        "reason_codes": [],
        "target_head": TARGET_HEAD,
        "trust_root": {
            "apply_receipt_sha256": APPLY_RECEIPT_SHA256,
            "recovery_v2_sha256": RECOVERY_V2_SHA256,
            "board_source_content_sha256": BOARD_SOURCE_CONTENT_SHA256,
            "board_hash": BOARD_HASH,
            "board_audit_hash": BOARD_AUDIT_HASH,
            "selection_hash": SELECTION_HASH,
            "candidate_set_hash": CANDIDATE_SET_HASH,
            "unit_sha256": UNIT_SHA256,
            "pin_sha256": PIN_SHA256,
            "postcheck_sha256": POSTCHECK_SHA256,
        },
        "cycle_count": 0,
        "cycles": [],
        "claims": {
            "two_natural_cycles_observed": False,
            "idle_heartbeat_counted_as_cycle": False,
            "current_os_process_singleton_observed": False,
            "cryptographic_process_session_binding_claimed": False,
            "current_fit_claimed": False,
            "training_or_model_fit_claimed": False,
            "serving_or_promotion_claimed": False,
            "trading_or_order_authority_claimed": False,
        },
        "boundaries": {
            "pg_mutation_statement_present": False,
            "pg_readonly_effect_guard_passed": None,
            "pg_tuple_write_observed": None,
            "broker_contact_performed": False,
            "service_mutation_performed": False,
            "source_mutation_performed": False,
            "credential_content_output": False,
        },
    }


def run_observation(
    *,
    trust_loader: Callable[[Callable[..., tuple[bytes, dict[str, Any]]]], dict[str, Any]] = load_fixed_trust,
    file_reader: Callable[..., tuple[bytes, dict[str, Any]]] = _read_bound_file,
    recovery_module_loader: Callable[[], Any] = load_exact_recovery_module,
    dsn_loader: Callable[[], Mapping[str, str]] = read_exact_dsn,
    connect: Callable[[Mapping[str, str]], Any] = connect_readonly,
    lock_observer: Callable[[int], dict[str, Any]] = observe_singleton_lock,
    environment: Mapping[str, str] | None = None,
    now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> dict[str, Any]:
    result = _base_result(now)
    try:
        reject_ambient_pg_environment(os.environ if environment is None else environment)
        trust = trust_loader(file_reader)
        runtime_files_before = _read_runtime_files(file_reader)
        recovery_module = recovery_module_loader()
        git_hardening = harden_loaded_recovery_git(
            recovery_module,
            file_reader=file_reader,
        )
        try:
            runtime = recovery_module.Runtime()
        except Exception as exc:
            raise ObserverUnverified("recovery_runtime_initialization_failed") from exc
        runtime_before = _runtime_snapshot(runtime)
        if runtime_before["identity"] != trust["service_identity"]:
            raise ObserverFail("runtime_identity_not_apply_identity")
        singleton_before = lock_observer(int(runtime_before["identity"]["MainPID"]))
        parameters = dsn_loader()
        if not isinstance(parameters, Mapping):
            raise ObserverUnverified("dsn_admission_failed")
        connection = connect(parameters)
        database: dict[str, Any] | None = None
        database_issue: ObserverIssue | None = None
        try:
            database = _observe_database(
                connection,
                lower_bound=trust["lower_bound"],
            )
        except ObserverIssue as exc:
            database_issue = exc
        runtime_after = _runtime_snapshot(runtime)
        singleton_after = lock_observer(int(runtime_after["identity"]["MainPID"]))
        runtime_files_after = _read_runtime_files(file_reader)
        if runtime_after != runtime_before:
            raise ObserverFail("runtime_identity_changed_during_database_observation")
        if singleton_after != singleton_before:
            raise ObserverFail("singleton_lock_changed_during_database_observation")
        if runtime_files_after != runtime_files_before:
            raise ObserverFail("unit_or_pin_changed_during_database_observation")
        if database_issue is not None:
            raise database_issue
        if database is None:
            raise ObserverUnverified("database_observation_result_missing")
        public_cycles = [_public_cycle(bundle) for bundle in database["bundles"]]
        result.update(
            {
                "apply_admission_lower_bound_utc": trust["lower_bound_text"],
                "runtime": runtime_before,
                "recovery_git_hardening": git_hardening,
                "runtime_files": runtime_files_before,
                "singleton_lock": singleton_before,
                "session": {
                    "session_id": database["session"]["session_id"],
                    "start_event_id": database["session"]["start_event_id"],
                    "started_at_utc": database["session"]["started_at"].isoformat().replace(
                        "+00:00", "Z"
                    ),
                    "post_pin_unique_open_session": True,
                },
                "cycle_window": database["cycle_window"],
                "transaction": database["transaction"],
                "standing_defer": database["standing"],
                "cycle_count": len(public_cycles),
                "cycles": public_cycles,
            }
        )
        result["claims"]["current_os_process_singleton_observed"] = True
        result["boundaries"]["pg_readonly_effect_guard_passed"] = True
        result["boundaries"]["pg_tuple_write_observed"] = False
        if len(public_cycles) == 2 and database["standing_status"] == "PASS":
            result["status"] = "PASS"
            result["reason_codes"] = []
            result["claims"]["two_natural_cycles_observed"] = True
        else:
            result["status"] = "PENDING"
            reasons: list[str] = []
            if len(public_cycles) < 2:
                reasons.append("two_natural_cycles_not_yet_observed")
            if database["standing_reason"] is not None and database["standing_reason"] not in reasons:
                reasons.append(database["standing_reason"])
            result["reason_codes"] = reasons
    except ObserverIssue as exc:
        result["status"] = exc.outcome
        result["reason_codes"] = [exc.reason]
        if exc.reason.startswith("readonly_transaction_"):
            result["boundaries"]["pg_readonly_effect_guard_passed"] = False
    except Exception as exc:
        result["status"] = "UNVERIFIED"
        result["reason_codes"] = ["observer_internal_unverified:" + type(exc).__name__]
    return result


def _serialize_result(result: Mapping[str, Any]) -> str:
    encoded = canonical_bytes(result)
    if len(encoded) > MAX_OUTPUT_BYTES:
        fallback = _base_result(lambda: datetime.now(timezone.utc))
        fallback["reason_codes"] = ["observer_output_limit_exceeded"]
        encoded = canonical_bytes(fallback)
    return encoded.decode("utf-8")


def _early_result(reason: str) -> dict[str, Any]:
    result = _base_result(lambda: datetime.now(timezone.utc))
    result["reason_codes"] = [reason]
    return result


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments:
        result = _early_result("cli_arguments_forbidden")
    elif sys.flags.isolated != 1:
        result = _early_result("isolated_mode_required")
    elif sys.dont_write_bytecode is not True:
        result = _early_result("dont_write_bytecode_required")
    elif Path(__file__) != OBSERVER_PATH:
        result = _early_result("observer_path_not_fixed_linux_path")
    elif sys.executable != "/usr/bin/python3":
        result = _early_result("python_executable_not_approved")
    else:
        result = run_observation()
    print(_serialize_result(result), flush=True)
    return {"PASS": 0, "PENDING": 3, "FAIL": 4, "UNVERIFIED": 5}[result["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
