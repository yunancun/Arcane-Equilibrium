#!/usr/bin/env bash
# Shared owner-bound lock and default-off cgroup guard for artifact-only research jobs.
# This file is sourced by cron wrappers. It never installs units or mutates runtime
# configuration; enabled containment requires a preinstalled, verified slice.

RESEARCH_GUARD_LIB_PATH="${BASH_SOURCE[0]}"
RESEARCH_GUARD_LIB_DIR="$(cd -P -- "$(dirname -- "$RESEARCH_GUARD_LIB_PATH")" && pwd)"
RESEARCH_GUARD_FS_HELPER="${RESEARCH_GUARD_LIB_DIR}/research_workload_guard_fs.py"

_research_guard_fs() {
    [[ -r "$RESEARCH_GUARD_FS_HELPER" ]] || return 75
    python3 "$RESEARCH_GUARD_FS_HELPER" "$@"
}

_research_guard_prepare_private_dir() {
    _research_guard_fs prepare-dir "$1"
}

_research_guard_prepare_private_file() {
    _research_guard_fs prepare-file "$1"
}

research_guard_prepare_private_dirs() {
    (( $# > 0 )) || return 64
    local path
    for path in "$@"; do
        _research_guard_prepare_private_dir "$path" || return 75
    done
}

research_guard_prepare_flock_file() {
    (( $# == 1 )) || return 64
    _research_guard_prepare_private_file "$1"
}

_research_guard_json_state() {
    local status="$1"
    local reason="${2:-}"
    local rc="${3:-0}"
    _research_guard_fs state-write \
        "$RESEARCH_GUARD_STATE_PATH" "$status" "$reason" "$rc" \
        "$RESEARCH_GUARD_LANE" "$RESEARCH_GUARD_TOKEN" \
        "$RESEARCH_GUARD_SOURCE_HEAD" "${RESEARCH_GUARD_SCOPE_UNIT:-}"
}

_research_guard_unlock_fd() {
    flock -u 218 2>/dev/null || true
    exec 218>&- 2>/dev/null || true
}

_research_guard_lock_owner_mutex() {
    local owner_path="$1"
    [[ -n "$owner_path" ]] || return 75
    command -v flock >/dev/null 2>&1 || return 75
    _research_guard_prepare_private_file "${owner_path}.mutation.flock" || return 75
    exec 219>"${owner_path}.mutation.flock" || return 75
    flock 219 || return 75
}

_research_guard_owner_snapshot_digest() {
    local owner_path="$1"
    python3 - "$owner_path" <<'PY'
import hashlib
import json
import sys

with open(sys.argv[1], encoding="utf-8") as fh:
    payload = json.load(fh)
canonical = json.dumps(
    payload,
    ensure_ascii=False,
    sort_keys=True,
    separators=(",", ":"),
    allow_nan=False,
).encode("utf-8")
print(hashlib.sha256(canonical).hexdigest())
PY
}

_research_guard_owner_field() {
    local field="$1"
    python3 - "$RESEARCH_GUARD_OWNER_PATH" "$field" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as fh:
    payload = json.load(fh)
value = payload.get(sys.argv[2])
if value is None or isinstance(value, (dict, list, bool)):
    raise SystemExit(2)
print(value)
PY
}

_research_guard_owned_control_group() {
    local expected_unit="$1"
    python3 - "$RESEARCH_GUARD_OWNER_PATH" "$RESEARCH_GUARD_TOKEN" "$expected_unit" <<'PY'
import json
import sys

path, token, expected_unit = sys.argv[1:]
with open(path, encoding="utf-8") as fh:
    payload = json.load(fh)
if payload.get("token") != token or payload.get("scope_unit") != expected_unit:
    raise SystemExit(75)
control_group = payload.get("control_group")
if not isinstance(control_group, str) or control_group == "none":
    raise SystemExit(75)
print(control_group)
PY
}

_research_guard_validate_control_group() {
    local control_group="$1"
    [[ "$control_group" =~ ^/([A-Za-z0-9_.:@-]+/)*[A-Za-z0-9_.:@-]+$ ]] || return 75
    [[ "$control_group" != *"/./"* && "$control_group" != */. ]] || return 75
    [[ "$control_group" != *"/../"* && "$control_group" != */.. ]] || return 75
    printf '%s\n' "$control_group"
}

_research_guard_control_group_matches_unit() {
    local control_group="$1" unit="$2"
    [[ "$unit" =~ ^openclaw-research-(track-)?[a-z][a-z0-9_-]{0,31}-[0-9a-f]{32}\.scope$ ]] || return 75
    control_group="$(_research_guard_validate_control_group "$control_group")" || return 75
    [[ "${control_group##*/}" == "$unit" ]] || return 75
}

_research_guard_scope_control_group() {
    local unit="$1" control_group=""
    [[ "$unit" =~ ^openclaw-research-(track-)?[a-z][a-z0-9_-]{0,31}-[0-9a-f]{32}\.scope$ ]] || return 75
    command -v systemctl >/dev/null 2>&1 || return 75
    control_group="$(systemctl --user show "$unit" -p ControlGroup --value 2>/dev/null)" || return 75
    _research_guard_control_group_matches_unit "$control_group" "$unit" || return 75
    printf '%s\n' "$control_group"
}

_research_guard_wait_cgroup_empty() {
    local control_group="$1"
    local cgroup_root="${2:-/sys/fs/cgroup}"
    local attempts="${3:-40}"
    [[ "$cgroup_root" == /* && "$attempts" =~ ^[1-9][0-9]*$ ]] || return 75
    control_group="$(_research_guard_validate_control_group "$control_group")" || return 75

    local exact_path="${cgroup_root}${control_group}"
    local parent_path="${exact_path%/*}"
    local events_path="${exact_path}/cgroup.events"
    local attempt populated="" read_rc=0
    for (( attempt = 1; attempt <= attempts; attempt++ )); do
        # Root controllers plus an accessible parent distinguish exact cgroup
        # removal from an unavailable or unmounted cgroup hierarchy.
        [[ -r "${cgroup_root}/cgroup.controllers" && -d "$parent_path" && \
            -r "$parent_path" && -x "$parent_path" ]] || return 75
        if [[ ! -e "$exact_path" ]]; then
            return 0
        fi
        [[ -d "$exact_path" && -r "$events_path" ]] || return 75
        read_rc=0
        populated="$(awk '$1 == "populated" { count += 1; value = $2 } END { if (count != 1 || value !~ /^[01]$/) exit 75; print value }' "$events_path" 2>/dev/null)" || read_rc=$?
        (( read_rc == 0 )) || return 75
        [[ "$populated" == "0" ]] && return 0
        (( attempt == attempts )) || sleep 0.05
    done
    return 75
}

_research_guard_remove_owned_owner() {
    local path="${RESEARCH_GUARD_OWNER_PATH:-}" token="${RESEARCH_GUARD_TOKEN:-}"
    [[ -n "$path" && -n "$token" ]] || return 75
    (
        _research_guard_lock_owner_mutex "$path" || exit 75
        [[ -e "$path" ]] || exit 0
        python3 - "$path" "$token" <<'PY'
import json
import os
import sys

path, token = sys.argv[1:]
with open(path, encoding="utf-8") as fh:
    payload = json.load(fh)
if payload.get("token") != token:
    raise SystemExit(75)
os.unlink(path)
PY
    )
}

_research_guard_reclaim_stale_owner() (
    local expected_lane="$1"
    local grace_sec="${OPENCLAW_RESEARCH_LOCK_RECOVERY_GRACE_SEC:-3600}"
    [[ "$expected_lane" =~ ^[a-z][a-z0-9_-]{0,31}$ ]] || return 75
    [[ "$grace_sec" =~ ^[0-9]+$ ]] || return 75
    _research_guard_lock_owner_mutex "$RESEARCH_GUARD_OWNER_PATH" || return 75

    local owner_snapshot_digest owner_lane owner_pid owner_start owner_token
    local owner_scope owner_control_group owner_heartbeat
    owner_snapshot_digest="$(_research_guard_owner_snapshot_digest \
        "$RESEARCH_GUARD_OWNER_PATH" 2>/dev/null)" || return 75
    [[ "$owner_snapshot_digest" =~ ^[0-9a-f]{64}$ ]] || return 75
    owner_lane="$(_research_guard_owner_field lane 2>/dev/null)" || return 75
    owner_pid="$(_research_guard_owner_field pid 2>/dev/null)" || return 75
    owner_start="$(_research_guard_owner_field proc_start_ticks 2>/dev/null)" || return 75
    owner_token="$(_research_guard_owner_field token 2>/dev/null)" || return 75
    owner_scope="$(_research_guard_owner_field scope_unit 2>/dev/null)" || return 75
    owner_control_group="$(_research_guard_owner_field control_group 2>/dev/null)" || return 75
    owner_heartbeat="$(_research_guard_owner_field heartbeat_epoch 2>/dev/null)" || return 75
    [[ "$owner_lane" =~ ^[a-z][a-z0-9_-]{0,31}$ ]] || return 75
    [[ "$owner_lane" == "$expected_lane" ]] || return 75
    [[ "$owner_pid" =~ ^[0-9]+$ && "$owner_start" =~ ^[0-9]+$ ]] || return 75
    [[ "$owner_heartbeat" =~ ^[0-9]+$ && "$owner_token" =~ ^[0-9a-f]{32}$ ]] || return 75

    if [[ -e "/proc/${owner_pid}/stat" ]]; then
        [[ -r "/proc/${owner_pid}/stat" ]] || return 75
        local current_start
        current_start="$(awk '{print $22}' "/proc/${owner_pid}/stat" 2>/dev/null)" || return 75
        [[ "$current_start" =~ ^[0-9]+$ ]] || return 75
        if [[ "$current_start" == "$owner_start" ]]; then
            return 75
        fi
    elif kill -0 "$owner_pid" 2>/dev/null; then
        local current_start
        current_start="$(ps -o lstart= -p "$owner_pid" 2>/dev/null | cksum | awk '{print $1}')" || return 75
        [[ "$current_start" =~ ^[0-9]+$ ]] || return 75
        if [[ "$current_start" == "$owner_start" ]]; then
            return 75
        fi
    fi

    if [[ -n "$owner_scope" && "$owner_scope" != "none" ]]; then
        case "$owner_scope" in
            "openclaw-research-track-${owner_lane}-${owner_token}.scope"|\
            "openclaw-research-${owner_lane}-${owner_token}.scope") ;;
            *) return 75 ;;
        esac
        [[ "$owner_control_group" != "none" ]] || return 75
        _research_guard_control_group_matches_unit \
            "$owner_control_group" "$owner_scope" || return 75
        _research_guard_wait_cgroup_empty "$owner_control_group" || return 75
    elif [[ "$owner_control_group" != "none" ]]; then
        return 75
    fi

    local now
    now="$(date +%s)"
    [[ "$now" =~ ^[0-9]+$ ]] || return 75
    (( now - owner_heartbeat >= grace_sec )) || return 75

    python3 - "$RESEARCH_GUARD_OWNER_PATH" "$owner_snapshot_digest" <<'PY'
import hashlib
import json
import os
import sys

path, expected_digest = sys.argv[1:]
with open(path, encoding="utf-8") as fh:
    payload = json.load(fh)
canonical = json.dumps(
    payload,
    ensure_ascii=False,
    sort_keys=True,
    separators=(",", ":"),
    allow_nan=False,
).encode("utf-8")
if hashlib.sha256(canonical).hexdigest() != expected_digest:
    raise SystemExit(75)
os.unlink(path)
PY
)

_research_guard_reclaim_legacy_lock() {
    local lane="$1"
    local lock_dir="$2"
    local grace_sec="${OPENCLAW_RESEARCH_LOCK_RECOVERY_GRACE_SEC:-3600}"
    [[ "$grace_sec" =~ ^[0-9]+$ && -d /proc && -r /proc ]] || return 75
    local mtime now pattern proc_dir cmdline current_pid parent_pid ancestor_pids=" "
    mtime="$(stat -c %Y "$lock_dir" 2>/dev/null)" || return 75
    now="$(date +%s)"
    [[ "$mtime" =~ ^[0-9]+$ && "$now" =~ ^[0-9]+$ ]] || return 75
    (( now - mtime >= grace_sec )) || return 75
    case "$lane" in
        alpha) pattern="alpha_discovery_throughput" ;;
        cost) pattern="cost_gate_learning_lane" ;;
        polymarket) pattern="polymarket_leadlag" ;;
        *) return 75 ;;
    esac
    current_pid="$$"
    while [[ "$current_pid" =~ ^[0-9]+$ && "$current_pid" != "0" ]]; do
        ancestor_pids+="${current_pid} "
        [[ "$current_pid" == "1" ]] && break
        parent_pid="$(awk '/^PPid:/{print $2}' "/proc/${current_pid}/status" 2>/dev/null)" || return 75
        [[ "$parent_pid" =~ ^[0-9]+$ ]] || return 75
        current_pid="$parent_pid"
    done
    for proc_dir in /proc/[0-9]*; do
        [[ -d "$proc_dir" ]] || continue
        case "$ancestor_pids" in
            *" ${proc_dir##*/} "*) continue ;;
        esac
        [[ "$(stat -c %u "$proc_dir" 2>/dev/null || true)" == "$(id -u)" ]] || continue
        [[ -r "$proc_dir/cmdline" ]] || return 75
        cmdline="$(tr '\0' ' ' <"$proc_dir/cmdline" 2>/dev/null)" || return 75
        if [[ "$cmdline" == *"$pattern"* ]]; then
            return 75
        fi
    done
    # The transition flock is held, the directory is old, and no same-UID lane
    # wrapper/worker exists. Non-empty or concurrently changed legacy locks fail.
    rmdir "$lock_dir" 2>/dev/null || return 75
}

research_guard_acquire() {
    local lane="" lock_dir="" source_head="" heartbeat_file=""
    while (( $# )); do
        case "$1" in
            --lane) lane="${2:-}"; shift 2 ;;
            --lock-dir) lock_dir="${2:-}"; shift 2 ;;
            --source-head) source_head="${2:-}"; shift 2 ;;
            --heartbeat-file) heartbeat_file="${2:-}"; shift 2 ;;
            *) return 64 ;;
        esac
    done
    [[ "$lane" =~ ^[a-z][a-z0-9_-]{0,31}$ ]] || return 64
    [[ -n "$lock_dir" && -n "$source_head" && -n "$heartbeat_file" ]] || return 64
    command -v flock >/dev/null 2>&1 || return 75
    command -v python3 >/dev/null 2>&1 || return 75

    _research_guard_prepare_private_dir "$(dirname "$lock_dir")" || return 75
    _research_guard_prepare_private_dir "$(dirname "$heartbeat_file")" || return 75
    RESEARCH_GUARD_LOCK_DIR="$lock_dir"
    RESEARCH_GUARD_FLOCK_PATH="${lock_dir}.flock"
    RESEARCH_GUARD_OWNER_PATH="${lock_dir}.owner.json"
    _research_guard_prepare_private_file "$RESEARCH_GUARD_FLOCK_PATH" || return 75
    _research_guard_prepare_private_file "$heartbeat_file" || return 75
    exec 218>"$RESEARCH_GUARD_FLOCK_PATH" || return 75
    if ! flock -n 218; then
        _research_guard_unlock_fd
        return 75
    fi

    # Legacy migration is allowed only with age + same-UID /proc negative proof;
    # age by itself is never sufficient.
    if [[ -d "$lock_dir" ]]; then
        if ! _research_guard_reclaim_legacy_lock "$lane" "$lock_dir"; then
            _research_guard_unlock_fd
            return 75
        fi
    fi
    if [[ -L "$RESEARCH_GUARD_OWNER_PATH" ]]; then
        _research_guard_unlock_fd
        return 75
    fi
    if [[ -e "$RESEARCH_GUARD_OWNER_PATH" ]]; then
        if ! _research_guard_reclaim_stale_owner "$lane"; then
            _research_guard_unlock_fd
            return 75
        fi
    fi

    local token proc_start now
    if [[ -r /proc/sys/kernel/random/uuid ]]; then
        token="$(tr -d '-' </proc/sys/kernel/random/uuid)"
    elif command -v openssl >/dev/null 2>&1; then
        token="$(openssl rand -hex 16)"
    else
        _research_guard_unlock_fd
        return 75
    fi
    [[ "$token" =~ ^[0-9a-f]{32}$ ]] || {
        _research_guard_unlock_fd
        return 75
    }
    if [[ -r "/proc/$$/stat" ]]; then
        proc_start="$(awk '{print $22}' "/proc/$$/stat" 2>/dev/null)" || {
            _research_guard_unlock_fd
            return 75
        }
    else
        proc_start="$(ps -o lstart= -p "$$" 2>/dev/null | cksum | awk '{print $1}')" || {
            _research_guard_unlock_fd
            return 75
        }
    fi
    [[ "$proc_start" =~ ^[0-9]+$ ]] || {
        _research_guard_unlock_fd
        return 75
    }
    now="$(date +%s)"

    RESEARCH_GUARD_LANE="$lane"
    RESEARCH_GUARD_TOKEN="$token"
    RESEARCH_GUARD_SOURCE_HEAD="$source_head"
    RESEARCH_GUARD_HEARTBEAT_FILE="$heartbeat_file"
    RESEARCH_GUARD_SCOPE_UNIT="none"
    RESEARCH_GUARD_CONTROL_GROUP="none"
    RESEARCH_GUARD_LAUNCH_STATE="idle"
    RESEARCH_GUARD_DEFERRED_SIGNAL_NAME=""
    RESEARCH_GUARD_DEFERRED_SIGNAL_RC=""
    RESEARCH_GUARD_PROGRESS_SEQ=0
    RESEARCH_GUARD_RELEASED=0
    RESEARCH_GUARD_FAILURE_LATCH=0
    RESEARCH_GUARD_OWNER_RELEASE_BLOCKED=0
    RESEARCH_GUARD_STATE_DIR="${OPENCLAW_DATA_DIR:-/tmp/openclaw}/research_workload_guard/${lane}"
    RESEARCH_GUARD_STATE_PATH="${RESEARCH_GUARD_STATE_DIR}/${token}.state.json"
    RESEARCH_GUARD_COMPLETION_PATH="${RESEARCH_GUARD_STATE_DIR}/${token}.completion.json"
    if ! _research_guard_prepare_private_dir "$RESEARCH_GUARD_STATE_DIR"; then
        _research_guard_unlock_fd
        return 75
    fi

    if ! (
        _research_guard_lock_owner_mutex "$RESEARCH_GUARD_OWNER_PATH" || exit 75
        _research_guard_fs owner-create \
            "$RESEARCH_GUARD_OWNER_PATH" "$lane" "$source_head" "$$" \
            "$proc_start" "$token" "$heartbeat_file" "$now"
    )
    then
        _research_guard_unlock_fd
        return 75
    fi
    if ! touch "$heartbeat_file" || \
        ! _research_guard_json_state "RUNNING" "acquired" 0; then
        _research_guard_remove_owned_owner || true
        _research_guard_unlock_fd
        return 75
    fi
}

research_guard_heartbeat() {
    local stage="${1:-RUNNING}"
    [[ -n "${RESEARCH_GUARD_TOKEN:-}" && -e "${RESEARCH_GUARD_OWNER_PATH:-}" ]] || return 75
    local now
    now="$(date +%s)"
    RESEARCH_GUARD_PROGRESS_SEQ=$(( ${RESEARCH_GUARD_PROGRESS_SEQ:-0} + 1 ))
    if ! (
        _research_guard_lock_owner_mutex "$RESEARCH_GUARD_OWNER_PATH" || exit 75
        _research_guard_fs owner-heartbeat \
            "$RESEARCH_GUARD_OWNER_PATH" "$RESEARCH_GUARD_TOKEN" "$now" \
            "$RESEARCH_GUARD_PROGRESS_SEQ" "$stage" \
            "${RESEARCH_GUARD_SCOPE_UNIT:-none}" \
            "${RESEARCH_GUARD_CONTROL_GROUP:-none}"
    )
    then
        return 75
    fi
    touch "$RESEARCH_GUARD_HEARTBEAT_FILE" || return 75
}

_research_guard_bind_owner_control_group() {
    local owner_path="$1" token="$2" unit="$3" control_group="$4" heartbeat_file="$5"
    _research_guard_control_group_matches_unit "$control_group" "$unit" || return 75
    local now
    now="$(date +%s)" || return 75
    [[ "$now" =~ ^[0-9]+$ ]] || return 75
    if ! (
        _research_guard_lock_owner_mutex "$owner_path" || exit 75
        _research_guard_fs owner-bind \
            "$owner_path" "$token" "$unit" "$control_group" "$now"
    )
    then
        return 75
    fi
    touch "$heartbeat_file" || return 75
}

_research_guard_scope_entry() {
    local unit="$1" memory="$2" swap="$3" tasks="$4" slice="$5"
    local owner_path="$6" token="$7" heartbeat_file="$8"
    shift 8
    (( $# > 0 )) || return 125

    local control_group="" actual_memory="" actual_swap="" actual_tasks="" actual_slice=""
    control_group="$(_research_guard_scope_control_group "$unit")" || return 125
    grep -Fxq "0::${control_group}" /proc/self/cgroup || return 125
    actual_memory="$(systemctl --user show "$unit" -p MemoryMax --value 2>/dev/null)" || return 125
    actual_swap="$(systemctl --user show "$unit" -p MemorySwapMax --value 2>/dev/null)" || return 125
    actual_tasks="$(systemctl --user show "$unit" -p TasksMax --value 2>/dev/null)" || return 125
    actual_slice="$(systemctl --user show "$unit" -p Slice --value 2>/dev/null)" || return 125
    [[ "$actual_memory" == "$memory" ]] || return 125
    [[ "$actual_swap" == "$swap" ]] || return 125
    [[ "$actual_tasks" == "$tasks" ]] || return 125
    [[ "$actual_slice" == "$slice" ]] || return 125
    _research_guard_bind_owner_control_group \
        "$owner_path" "$token" "$unit" "$control_group" "$heartbeat_file" || return 125
    exec "$@"
}

research_guard_incomplete() {
    local reason="${1:-stage_failed}"
    local rc="${2:-1}"
    local remove_rc=0
    RESEARCH_GUARD_FAILURE_LATCH=1
    research_guard_heartbeat "INCOMPLETE:${reason}" >/dev/null 2>&1 || true
    if [[ -n "${RESEARCH_GUARD_COMPLETION_PATH:-}" ]]; then
        rm -f -- "$RESEARCH_GUARD_COMPLETION_PATH" || remove_rc=75
    fi
    (( remove_rc == 0 )) || RESEARCH_GUARD_OWNER_RELEASE_BLOCKED=1
    if ! _research_guard_json_state "INCOMPLETE" "$reason" "$rc"; then
        RESEARCH_GUARD_OWNER_RELEASE_BLOCKED=1
        rm -f -- "${RESEARCH_GUARD_STATE_PATH:-}" 2>/dev/null || true
        return 75
    fi
    return "$remove_rc"
}

_research_guard_verify_slice() {
    command -v systemctl >/dev/null 2>&1 || return 125
    command -v systemd-run >/dev/null 2>&1 || return 125
    local high max swap
    high="$(systemctl --user show openclaw-research.slice -p MemoryHigh --value 2>/dev/null)" || return 125
    max="$(systemctl --user show openclaw-research.slice -p MemoryMax --value 2>/dev/null)" || return 125
    swap="$(systemctl --user show openclaw-research.slice -p MemorySwapMax --value 2>/dev/null)" || return 125
    [[ "$high" == "25769803776" && "$max" == "34359738368" && "$swap" == "0" ]] || return 125
}

_research_guard_state_status() {
    _research_guard_fs state-status "$RESEARCH_GUARD_STATE_PATH"
}

_research_guard_scrub_environment() {
    local name
    while IFS= read -r name; do
        case "$name" in
            HOME|PATH|LANG|LC_ALL|TZ|XDG_RUNTIME_DIR|DBUS_SESSION_BUS_ADDRESS|\
            OPENCLAW_BASE_DIR|OPENCLAW_DATA_DIR|\
            OPENCLAW_SEALED_HORIZON_LEARNING_EVIDENCE_JSON|\
            OPENCLAW_SEALED_HORIZON_OPERATOR_REVIEW_JSON|\
            OPENCLAW_SEALED_HORIZON_DECISION_PACKET_JSON|\
            PGHOST|PGPORT|PGDATABASE|PGUSER|PGPASSWORD|PGOPTIONS|\
            POSTGRES_HOST|POSTGRES_PORT|POSTGRES_DB|POSTGRES_USER|POSTGRES_PASSWORD|\
            PYTHONDONTWRITEBYTECODE)
                ;;
            *) unset "$name" ;;
        esac
    done < <(compgen -e)
    export PYTHONPATH="${OPENCLAW_BASE_DIR:-}:${OPENCLAW_BASE_DIR:-}/helper_scripts/research"
    export PYTHONDONTWRITEBYTECODE=1
}

research_guard_publish_json_pair() {
    local json_stage="$1" json_latest="$2" md_stage="$3" md_latest="$4"
    [[ -f "$json_stage" && -f "$md_stage" ]] || return 66
    # JSON is the authoritative consumer input, so commit it last.
    mv -f "$md_stage" "$md_latest" || return $?
    mv -f "$json_stage" "$json_latest"
}

research_guard_publish_latest() {
    local source="$1" latest="$2"
    [[ -f "$source" && -n "${RESEARCH_GUARD_TOKEN:-}" ]] || return 66
    local staged="${latest}.tmp.${RESEARCH_GUARD_TOKEN}"
    rm -f -- "$staged"
    cp "$source" "$staged" || {
        rm -f -- "$staged"
        return 74
    }
    mv -f "$staged" "$latest" || {
        rm -f -- "$staged"
        return 74
    }
}

_research_guard_stage_failure() {
    local preserve_completion="$1" reason="$2" rc="$3"
    RESEARCH_GUARD_FAILURE_LATCH=1
    research_guard_heartbeat "INCOMPLETE:${reason}" >/dev/null 2>&1 || true
    if (( preserve_completion == 1 )); then
        if ! _research_guard_json_state "INCOMPLETE" "$reason" "$rc"; then
            RESEARCH_GUARD_OWNER_RELEASE_BLOCKED=1
            rm -f -- "${RESEARCH_GUARD_STATE_PATH:-}" 2>/dev/null || true
            return 75
        fi
    else
        research_guard_incomplete "$reason" "$rc" || true
    fi
}

_research_guard_defer_signal() {
    local signal_name="$1" signal_rc="$2"
    [[ "$signal_name" == "INT" || "$signal_name" == "TERM" ]] || return 75
    [[ "$signal_rc" == "130" || "$signal_rc" == "143" ]] || return 75
    if [[ -z "${RESEARCH_GUARD_DEFERRED_SIGNAL_NAME:-}" ]]; then
        RESEARCH_GUARD_DEFERRED_SIGNAL_NAME="$signal_name"
        RESEARCH_GUARD_DEFERRED_SIGNAL_RC="$signal_rc"
    fi
}

research_guard_run_stage() {
    local lane="" memory_max="" tasks_max="" preserve_completion=0
    while (( $# )); do
        case "$1" in
            --lane) lane="${2:-}"; shift 2 ;;
            --memory-max-bytes) memory_max="${2:-}"; shift 2 ;;
            --tasks-max) tasks_max="${2:-}"; shift 2 ;;
            --preserve-completion-manifest-on-failure)
                preserve_completion=1
                shift
                ;;
            --) shift; break ;;
            *) return 64 ;;
        esac
    done
    [[ "$lane" == "${RESEARCH_GUARD_LANE:-}" && "$memory_max" =~ ^[0-9]+$ ]] || return 64
    [[ "$tasks_max" =~ ^[0-9]+$ && $# -gt 0 ]] || return 64
    local state_before=""
    if ! state_before="$(_research_guard_state_status 2>/dev/null)"; then
        _research_guard_stage_failure "$preserve_completion" "state_read_failed" 75
        return 75
    fi
    if (( preserve_completion == 1 )); then
        if [[ "$state_before" != "COMPLETE" ]]; then
            [[ "$state_before" == "INCOMPLETE" ]] && return 75
            _research_guard_stage_failure "$preserve_completion" "publisher_before_complete" 64
            return 64
        fi
    elif [[ "$state_before" != "RUNNING" ]]; then
        [[ "$state_before" == "INCOMPLETE" ]] && return 75
        _research_guard_stage_failure "$preserve_completion" "stage_invalid_state" 75
        return 75
    fi
    if ! research_guard_heartbeat "STAGE_START"; then
        _research_guard_stage_failure "$preserve_completion" "stage_start_heartbeat_failed" 75
        return 75
    fi

    local rc=0 enabled="${OPENCLAW_RESEARCH_CONTAINMENT_ENABLED:-0}"
    local scope_slice="" scope_memory="" scope_swap="" scope_tasks=""
    local scrub_environment=0
    case "$enabled" in
        0)
            # Memory containment stays default-off, but every payload still
            # needs a fork-closed membership handle. An unbounded transient
            # scope makes signal cleanup provable without applying the
            # research slice's MemoryMax/TasksMax policy.
            RESEARCH_GUARD_SCOPE_UNIT="openclaw-research-track-${lane}-${RESEARCH_GUARD_TOKEN}.scope"
            scope_slice="app.slice"
            scope_memory="infinity"
            scope_swap="infinity"
            scope_tasks="infinity"
            ;;
        1)
            if ! _research_guard_verify_slice; then
                rc=125
            else
                RESEARCH_GUARD_SCOPE_UNIT="openclaw-research-${lane}-${RESEARCH_GUARD_TOKEN}.scope"
                scope_slice="openclaw-research.slice"
                scope_memory="$memory_max"
                scope_swap="0"
                scope_tasks="$tasks_max"
                scrub_environment=1
            fi
            ;;
        *) rc=125 ;;
    esac

    if (( rc == 0 )); then
        local inner
        inner='guard_lib="$1"; shift
source "$guard_lib" || exit 125
_research_guard_scope_entry "$@"'
        RESEARCH_GUARD_LAUNCH_STATE="pending"
        RESEARCH_GUARD_DEFERRED_SIGNAL_NAME=""
        RESEARCH_GUARD_DEFERRED_SIGNAL_RC=""
        trap '_research_guard_defer_signal INT 130' INT
        trap '_research_guard_defer_signal TERM 143' TERM
        (
            (( scrub_environment == 0 )) || _research_guard_scrub_environment
            systemd-run --user --scope --wait --collect --quiet \
                --unit="$RESEARCH_GUARD_SCOPE_UNIT" \
                --slice="$scope_slice" \
                --property="MemoryMax=${scope_memory}" \
                --property="MemorySwapMax=${scope_swap}" \
                --property="TasksMax=${scope_tasks}" \
                -- bash -c "$inner" _ "$RESEARCH_GUARD_LIB_PATH" \
                "$RESEARCH_GUARD_SCOPE_UNIT" "$scope_memory" "$scope_swap" \
                "$scope_tasks" "$scope_slice" "$RESEARCH_GUARD_OWNER_PATH" \
                "$RESEARCH_GUARD_TOKEN" "$RESEARCH_GUARD_HEARTBEAT_FILE" "$@"
        ) &
        RESEARCH_GUARD_CHILD_PID=$!
        RESEARCH_GUARD_LAUNCH_STATE="bound"
        trap 'research_guard_abort_signal INT 130' INT
        trap 'research_guard_abort_signal TERM 143' TERM
        if [[ -n "$RESEARCH_GUARD_DEFERRED_SIGNAL_NAME" ]]; then
            research_guard_abort_signal "$RESEARCH_GUARD_DEFERRED_SIGNAL_NAME" \
                "$RESEARCH_GUARD_DEFERRED_SIGNAL_RC"
        fi
        wait "$RESEARCH_GUARD_CHILD_PID" || rc=$?
        RESEARCH_GUARD_CHILD_PID=""
        RESEARCH_GUARD_LAUNCH_STATE="idle"
    fi

    if (( rc != 0 )); then
        local reason="stage_nonzero"
        (( rc == 137 )) && reason="resource_exhausted_oom_or_sigkill"
        # In publisher mode the durable manifest proves all upstream bytes were
        # complete before the final atomic link. Preserve that upstream proof,
        # but never preserve COMPLETE state after any publisher failure.
        _research_guard_stage_failure "$preserve_completion" "$reason" "$rc"
        return "$rc"
    fi
    if ! research_guard_heartbeat "STAGE_COMPLETE"; then
        _research_guard_stage_failure "$preserve_completion" \
            "stage_complete_heartbeat_failed" 75
        return 75
    fi
}

research_guard_complete() {
    local -a paths=()
    while (( $# )); do
        case "$1" in
            --completion-path) paths+=("${2:-}"); shift 2 ;;
            *) return 64 ;;
        esac
    done
    (( ${#paths[@]} > 0 )) || {
        research_guard_incomplete "completion_paths_empty" 64 || true
        return 64
    }
    local state_before=""
    if ! state_before="$(_research_guard_state_status 2>/dev/null)" || \
        [[ "$state_before" != "RUNNING" ]]; then
        research_guard_incomplete "completion_invalid_state" 75 || true
        return 75
    fi
    local path
    for path in "${paths[@]}"; do
        [[ -f "$path" ]] || {
            research_guard_incomplete "completion_path_missing" 66 || true
            return 66
        }
    done
    if ! _research_guard_fs completion-write \
        "$RESEARCH_GUARD_COMPLETION_PATH" "$RESEARCH_GUARD_LANE" \
        "$RESEARCH_GUARD_TOKEN" "$RESEARCH_GUARD_SOURCE_HEAD" "${paths[@]}"
    then
        research_guard_incomplete "completion_manifest_write_failed" 75 || true
        return 75
    fi
    if ! _research_guard_json_state "COMPLETE" "completion_manifest_valid" 0; then
        research_guard_incomplete "completion_state_write_failed" 75 || true
        return 75
    fi
    if ! research_guard_heartbeat "COMPLETE"; then
        research_guard_incomplete "completion_heartbeat_failed" 75 || true
        return 75
    fi
}

research_guard_release() {
    local prior_rc=$?
    if [[ "${RESEARCH_GUARD_RELEASED:-1}" == "1" ]]; then
        return "$prior_rc"
    fi
    RESEARCH_GUARD_RELEASED=1
    local release_safe=1 state_status=""
    if [[ ! -f "${RESEARCH_GUARD_STATE_PATH:-}" ]] || \
        ! state_status="$(_research_guard_state_status 2>/dev/null)"; then
        release_safe=0
    elif [[ "$state_status" == "RUNNING" ]]; then
        if research_guard_incomplete "released_without_completion" "$prior_rc"; then
            state_status="INCOMPLETE"
        else
            release_safe=0
        fi
    elif [[ "$state_status" != "COMPLETE" && "$state_status" != "INCOMPLETE" ]]; then
        release_safe=0
    fi
    if [[ "${RESEARCH_GUARD_FAILURE_LATCH:-0}" == "1" && \
        "$state_status" != "INCOMPLETE" ]]; then
        release_safe=0
    fi
    if [[ "${RESEARCH_GUARD_OWNER_RELEASE_BLOCKED:-0}" == "1" ]]; then
        release_safe=0
    fi
    if [[ "${RESEARCH_GUARD_LAUNCH_STATE:-idle}" == "pending" ]]; then
        release_safe=0
    fi
    if (( release_safe == 1 )); then
        _research_guard_remove_owned_owner || true
    fi
    _research_guard_unlock_fd
    return "$prior_rc"
}

_research_guard_process_identity() {
    local pid="$1" identity=""
    [[ "$pid" =~ ^[0-9]+$ ]] || return 64
    if [[ -r "/proc/${pid}/stat" ]]; then
        identity="$(awk '{print $22}' "/proc/${pid}/stat" 2>/dev/null)" || return 75
    elif kill -0 "$pid" 2>/dev/null; then
        identity="$(ps -o lstart= -p "$pid" 2>/dev/null | cksum | awk '{print $1}')" || return 75
    else
        return 1
    fi
    [[ "$identity" =~ ^[0-9]+$ ]] || return 75
    printf '%s\n' "$identity"
}

_research_guard_identity_alive() {
    local pid="$1" expected="$2" current="" state="" identity_rc=0
    current="$(_research_guard_process_identity "$pid" 2>/dev/null)" || identity_rc=$?
    case "$identity_rc" in
        0) ;;
        1) return 1 ;;
        *) return 75 ;;
    esac
    [[ "$current" == "$expected" ]] || return 1
    state="$(ps -o state= -p "$pid" 2>/dev/null | tr -d '[:space:]')" || return 75
    [[ -n "$state" ]] || return 75
    [[ "$state" == Z* ]] && return 1
    return 0
}

_research_guard_signal_process_tree() {
    local pid="$1" signal_name="$2" child children="" pgrep_rc=0 tree_rc=0 identity=""
    [[ "$pid" =~ ^[0-9]+$ ]] || return 64
    if ! identity="$(_research_guard_process_identity "$pid" 2>/dev/null)"; then
        kill -"$signal_name" "$pid" 2>/dev/null || true
        return 75
    fi
    RESEARCH_GUARD_SIGNAL_IDENTITIES+="${pid}:${identity} "
    if command -v pgrep >/dev/null 2>&1; then
        children="$(pgrep -P "$pid" 2>/dev/null)" || pgrep_rc=$?
        case "$pgrep_rc" in
            0)
                while IFS= read -r child; do
                    [[ "$child" =~ ^[0-9]+$ ]] || continue
                    _research_guard_signal_process_tree "$child" "$signal_name" || tree_rc=75
                done <<< "$children"
                ;;
            1) ;;
            *) tree_rc=75 ;;
        esac
    else
        tree_rc=75
    fi
    kill -"$signal_name" "$pid" 2>/dev/null || true
    return "$tree_rc"
}

_research_guard_wait_process_tree_gone() {
    local identities="$1" entry pid identity survivors="" attempt identity_rc=0
    for attempt in {1..20}; do
        survivors=""
        for entry in $identities; do
            pid="${entry%%:*}"
            identity="${entry#*:}"
            identity_rc=0
            _research_guard_identity_alive "$pid" "$identity" || identity_rc=$?
            case "$identity_rc" in
                0) survivors+="${entry} " ;;
                1) ;;
                *) return 75 ;;
            esac
        done
        [[ -z "$survivors" ]] && return 0
        sleep 0.05
    done
    for entry in $survivors; do
        pid="${entry%%:*}"
        identity="${entry#*:}"
        identity_rc=0
        _research_guard_identity_alive "$pid" "$identity" || identity_rc=$?
        case "$identity_rc" in
            0) kill -KILL "$pid" 2>/dev/null || true ;;
            1) ;;
            *) return 75 ;;
        esac
    done
    for attempt in {1..40}; do
        survivors=""
        for entry in $identities; do
            pid="${entry%%:*}"
            identity="${entry#*:}"
            identity_rc=0
            _research_guard_identity_alive "$pid" "$identity" || identity_rc=$?
            case "$identity_rc" in
                0) survivors+="${entry} " ;;
                1) ;;
                *) return 75 ;;
            esac
        done
        [[ -z "$survivors" ]] && return 0
        sleep 0.05
    done
    return 75
}

research_guard_abort_signal() {
    local signal_name="${1:-TERM}" signal_rc="${2:-143}"
    trap - EXIT INT TERM
    local child_pid="${RESEARCH_GUARD_CHILD_PID:-}" scope_safe=1 tree_safe=1 signal_reason="signal_term"
    [[ "$signal_name" == "INT" ]] && signal_reason="signal_int"
    if [[ "${RESEARCH_GUARD_LAUNCH_STATE:-idle}" == "pending" ]]; then
        # Defensive fail-closed path. Normal signal traps defer until the async
        # child PID is bound, so reaching this branch means launch ownership is
        # ambiguous and owner metadata must survive for later adjudication.
        RESEARCH_GUARD_OWNER_RELEASE_BLOCKED=1
        research_guard_incomplete "$signal_reason" "$signal_rc" || true
        RESEARCH_GUARD_RELEASED=1
        _research_guard_unlock_fd
        exit "$signal_rc"
    fi
    if [[ -n "${RESEARCH_GUARD_SCOPE_UNIT:-}" && "${RESEARCH_GUARD_SCOPE_UNIT}" != "none" ]]; then
        scope_safe=0
        local control_group="" control_group_rc=0 control_group_bound=0
        control_group="$(_research_guard_owned_control_group \
            "$RESEARCH_GUARD_SCOPE_UNIT" 2>/dev/null)" || control_group_rc=$?
        if (( control_group_rc == 0 )) && \
            _research_guard_control_group_matches_unit \
                "$control_group" "$RESEARCH_GUARD_SCOPE_UNIT"; then
            RESEARCH_GUARD_CONTROL_GROUP="$control_group"
            control_group_bound=1
        else
            control_group=""
            control_group_rc=0
            control_group="$(_research_guard_scope_control_group \
                "$RESEARCH_GUARD_SCOPE_UNIT" 2>/dev/null)" || control_group_rc=$?
        fi
        if (( control_group_bound == 0 && control_group_rc == 0 )); then
            RESEARCH_GUARD_CONTROL_GROUP="$control_group"
            if research_guard_heartbeat "SIGNAL_SCOPE_BOUND"; then
                control_group_bound=1
            else
                RESEARCH_GUARD_OWNER_RELEASE_BLOCKED=1
            fi
        fi
        if command -v systemctl >/dev/null 2>&1; then
            systemctl --user kill --kill-whom=all --signal="$signal_name" \
                "$RESEARCH_GUARD_SCOPE_UNIT" >/dev/null 2>&1 || true
            if (( control_group_bound == 1 )) && \
                _research_guard_wait_cgroup_empty "$control_group"; then
                scope_safe=1
            fi
        fi
    fi
    if [[ -n "$child_pid" ]]; then
        # Enabled containment is killed by cgroup first. In default-off mode,
        # terminate only the owner-bound process tree, descendants first.
        tree_safe=0
        local tree_rc=0
        RESEARCH_GUARD_SIGNAL_IDENTITIES=""
        _research_guard_signal_process_tree "$child_pid" "$signal_name" || tree_rc=$?
        local tree_wait_rc=0
        _research_guard_wait_process_tree_gone \
            "$RESEARCH_GUARD_SIGNAL_IDENTITIES" || tree_wait_rc=$?
        if (( tree_wait_rc == 0 )); then
            wait "$child_pid" 2>/dev/null || true
        fi
        RESEARCH_GUARD_CHILD_PID=""
        if (( tree_rc == 0 && tree_wait_rc == 0 )); then
            tree_safe=1
        fi
        # A verified-empty exact cgroup supersedes local process-tree discovery:
        # the heavy payload cannot outlive it even if pgrep failed.
        if [[ "${RESEARCH_GUARD_SCOPE_UNIT:-none}" != "none" ]] && \
            (( scope_safe == 1 )); then
            tree_safe=1
        fi
    fi
    research_guard_incomplete "$signal_reason" "$signal_rc" || true
    if (( scope_safe == 1 && tree_safe == 1 )); then
        research_guard_release
    else
        # Preserve owner metadata when exact cgroup emptiness cannot be proven.
        # Stale-owner recovery applies the same cgroup.events proof and never
        # treats systemd unit lookup state as proof that payloads are gone.
        RESEARCH_GUARD_RELEASED=1
        _research_guard_unlock_fd
    fi
    exit "$signal_rc"
}
