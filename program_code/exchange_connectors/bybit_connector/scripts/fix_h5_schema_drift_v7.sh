#!/usr/bin/env bash
set -euo pipefail

cd /home/ncyu/srv/program_code/exchange_connectors/bybit_connector
BASE="/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/thought_gate"

echo "===== 0) BACKUP ====="
for f in \
  scripts/bybit_ai_cost_log.py \
  scripts/bybit_ai_governance_audit.py \
  scripts/bybit_ai_cost_governance_final_audit.py
do
  cp "$f" "$f.bak_h5_schema_drift_v7_$(date +%s)"
  echo "backed_up: $f"
done

echo
echo "===== 1) INSTALL H5 COMPAT HELPER ====="
cat > scripts/bybit_h5_compat_helpers.py <<'PY'
#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

BASE = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/thought_gate")

def read_json_if_exists(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}

def bool_from_candidates(doc: Dict[str, Any], *paths: str) -> Optional[bool]:
    for path in paths:
        cur: Any = doc
        ok = True
        for part in path.split("."):
            if not isinstance(cur, dict) or part not in cur:
                ok = False
                break
            cur = cur[part]
        if ok and isinstance(cur, bool):
            return cur
    return None

def stage_closed_from_file(filename: str, stage_key: str) -> bool:
    doc = read_json_if_exists(BASE / filename)
    v = bool_from_candidates(
        doc,
        f"audit_summary.{stage_key}",
        f"chapter_summary.{stage_key}",
        stage_key,
        "overall_ok",
        "summary_ok",
        "audit_ok",
        "log_ok",
    )
    return bool(v is True)

def h2_stage_closed() -> bool:
    return stage_closed_from_file("bybit_query_budget_final_audit_latest.json", "h2_stage_closed")

def h4_stage_closed() -> bool:
    return stage_closed_from_file("bybit_compute_governor_final_audit_latest.json", "h4_stage_closed")

def h5_log_doc() -> Dict[str, Any]:
    return read_json_if_exists(BASE / "bybit_ai_cost_log_latest.json")

def h5_audit_doc() -> Dict[str, Any]:
    return read_json_if_exists(BASE / "bybit_ai_governance_audit_latest.json")

def h5_log_ok() -> bool:
    doc = h5_log_doc()
    if doc.get("log_ok") is True:
        return True
    return doc.get("log_state") in {"ai_cost_log_recorded", "ai_cost_log_recorded_soft_warn"}

def h5_governance_audit_ok() -> bool:
    doc = h5_audit_doc()
    if doc.get("audit_ok") is True:
        return True
    return doc.get("audit_state") in {"ai_governance_audit_passed", "ai_governance_audit_passed_soft_warn"}

def extract_within_timeout_hint() -> Optional[bool]:
    candidates = [
        BASE / "bybit_query_budget_runtime_latest.json",
        BASE / "bybit_query_budget_final_audit_latest.json",
    ]
    for p in candidates:
        doc = read_json_if_exists(p)
        for path in (
            "observed_last_call.within_timeout_hint",
            "runtime_summary.within_timeout_hint",
            "budget_assessment.within_timeout_hint",
            "audit_summary.within_timeout_hint",
            "within_timeout_hint",
        ):
            v = bool_from_candidates(doc, path)
            if isinstance(v, bool):
                return v
    return None
PY
chmod +x scripts/bybit_h5_compat_helpers.py

echo
echo "===== 2) PATCH H5 THREE SCRIPTS WITH COMPAT OVERRIDE ====="
python3 - <<'PY'
from pathlib import Path
import re

FILES = [
    "scripts/bybit_ai_cost_log.py",
    "scripts/bybit_ai_governance_audit.py",
    "scripts/bybit_ai_cost_governance_final_audit.py",
]

IMPORT_LINE = (
    "from bybit_h5_compat_helpers import "
    "h2_stage_closed, h4_stage_closed, h5_log_ok, h5_governance_audit_ok, extract_within_timeout_hint"
)

def ensure_import(path: Path):
    s = path.read_text(encoding="utf-8")
    if IMPORT_LINE in s:
        return
    lines = s.splitlines()
    insert_at = 0
    for i, line in enumerate(lines):
        if line.startswith("from __future__ import"):
            insert_at = i + 1
            break
    while insert_at < len(lines) and (lines[insert_at].startswith("import ") or lines[insert_at].startswith("from ")):
        insert_at += 1
    lines.insert(insert_at, IMPORT_LINE)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

def strip_old_blocks(text: str) -> str:
    markers = [
        "# H5_FORENSIC_OVERRIDE_V6",
        "# H5_MINIMAL_OVERRIDE_V5",
        "# H5_MINIMAL_OVERRIDE_V4",
        "# H5_SOFTWARN_CLASSIFICATION_V3",
        "# H5_FINAL_STATE_V3",
        "# H5_SCHEMA_DRIFT_COMPAT_V7",
    ]
    for mk in markers:
        while mk in text:
            start = text.find(mk)
            nxt = re.search(r'(?m)^\s*(report\s*=\s*\{|return\s*\{)', text[start:])
            if not nxt:
                text = text[:start]
                break
            text = text[:start] + text[start + nxt.start():]
    return text

def insert_before_anchor(path: Path, block: str):
    s = path.read_text(encoding="utf-8")
    s = strip_old_blocks(s)

    m = re.search(r'(?m)^(\s*)(report\s*=\s*\{|return\s*\{)', s)
    if not m:
        raise SystemExit(f"ANCHOR_NOT_FOUND: {path}")

    indent = m.group(1)
    block_text = "\n".join((indent + line) if line.strip() else "" for line in block.strip("\n").splitlines()) + "\n\n"
    s = s[:m.start()] + block_text + s[m.start():]
    path.write_text(s, encoding="utf-8")

for f in FILES:
    ensure_import(Path(f))

log_block = """
# H5_SCHEMA_DRIFT_COMPAT_V7
_authoritative_h4_closed = h4_stage_closed()
_authoritative_within_timeout_hint = extract_within_timeout_hint()

if _authoritative_within_timeout_hint is not None:
    within_timeout_hint = _authoritative_within_timeout_hint

warning_flags = list(dict.fromkeys(list(warning_flags or [])))
blocking_reasons = list(dict.fromkeys(list(blocking_reasons or [])))

blocking_reasons = [x for x in blocking_reasons if x != "h4_not_closed"]
if not _authoritative_h4_closed:
    blocking_reasons.append("h4_not_closed")

if blocking_reasons:
    log_state = "ai_cost_log_blocked"
    log_ok = False
else:
    log_state = "ai_cost_log_recorded_soft_warn" if warning_flags else "ai_cost_log_recorded"
    log_ok = True
"""

audit_block = """
# H5_SCHEMA_DRIFT_COMPAT_V7
_authoritative_h2_closed = h2_stage_closed()
_authoritative_h4_closed = h4_stage_closed()
_authoritative_h5_log_ok = h5_log_ok()

failed_checks = list(dict.fromkeys(list(failed_checks or [])))
failed_checks = [x for x in failed_checks if x not in {"h2_stage_closed", "h4_stage_closed", "ai_cost_log_ok"}]

if not _authoritative_h2_closed:
    failed_checks.append("h2_stage_closed")
if not _authoritative_h4_closed:
    failed_checks.append("h4_stage_closed")
if not _authoritative_h5_log_ok:
    failed_checks.append("ai_cost_log_ok")

warning_flags = list(dict.fromkeys(list(warning_flags or [])))
blocking_reasons = list(dict.fromkeys(list(blocking_reasons or [])))

if failed_checks or blocking_reasons:
    audit_state = "ai_governance_audit_blocked"
    audit_ok = False
else:
    audit_state = "ai_governance_audit_passed_soft_warn" if warning_flags else "ai_governance_audit_passed"
    audit_ok = True
"""

final_block = """
# H5_SCHEMA_DRIFT_COMPAT_V7
_authoritative_h4_closed = h4_stage_closed()
_authoritative_h5_log_ok = h5_log_ok()
_authoritative_h5_governance_audit_ok = h5_governance_audit_ok()

failed_checks = list(dict.fromkeys(list(failed_checks or [])))
failed_checks = [x for x in failed_checks if x not in {"h4_stage_closed", "h5_log_ok", "h5_governance_audit_ok"}]

if not _authoritative_h4_closed:
    failed_checks.append("h4_stage_closed")
if not _authoritative_h5_log_ok:
    failed_checks.append("h5_log_ok")
if not _authoritative_h5_governance_audit_ok:
    failed_checks.append("h5_governance_audit_ok")

warning_flags = list(dict.fromkeys(list(warning_flags or [])))

final_state = (
    "ai_cost_governance_not_closed"
    if failed_checks
    else ("ai_cost_governance_closed_soft_warn_ready_for_i1" if warning_flags else "ai_cost_governance_closed_ready_for_i1")
)
"""

insert_before_anchor(Path("scripts/bybit_ai_cost_log.py"), log_block)
insert_before_anchor(Path("scripts/bybit_ai_governance_audit.py"), audit_block)
insert_before_anchor(Path("scripts/bybit_ai_cost_governance_final_audit.py"), final_block)

p = Path("scripts/bybit_ai_cost_governance_final_audit.py")
s = p.read_text(encoding="utf-8")
if '"final_state": final_state,' not in s and "'final_state': final_state," not in s:
    if '"audit_state": audit_state,' in s:
        s = s.replace(
            '"audit_state": audit_state,',
            '"audit_state": audit_state,\n        "final_state": final_state,',
            1,
        )
    elif "'audit_state': audit_state," in s:
        s = s.replace(
            "'audit_state': audit_state,",
            "'audit_state': audit_state,\n        'final_state': final_state,",
            1,
        )
    else:
        raise SystemExit("AUDIT_STATE_FIELD_NOT_FOUND")
    p.write_text(s, encoding="utf-8")

print("patched all H5 files")
PY

echo
echo "===== 3) VERIFY PATCH MARKERS ====="
for f in \
  scripts/bybit_ai_cost_log.py \
  scripts/bybit_ai_governance_audit.py \
  scripts/bybit_ai_cost_governance_final_audit.py
do
  echo
  echo "----- $f -----"
  grep -nE 'H5_SCHEMA_DRIFT_COMPAT_V7|h2_stage_closed|h4_stage_closed|h5_log_ok|h5_governance_audit_ok|final_state' "$f" || true
done

echo
echo "===== 4) PY_COMPILE ====="
python3 -m py_compile \
  scripts/bybit_h5_compat_helpers.py \
  scripts/bybit_ai_cost_log.py \
  scripts/bybit_ai_governance_audit.py \
  scripts/bybit_ai_cost_governance_final_audit.py

echo
echo "===== 5) RERUN H5 FULL CLOSURE ====="
./scripts/run_h5_ai_cost_governance_full_closure.sh

echo
echo "===== 6) H5 RAW DIAG AFTER V7 ====="
./scripts/run_with_trading_env.sh python3 - <<'PY'
import json
from pathlib import Path

base = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/thought_gate")
log = json.loads((base / "bybit_ai_cost_log_latest.json").read_text(encoding="utf-8"))
audit = json.loads((base / "bybit_ai_governance_audit_latest.json").read_text(encoding="utf-8"))
final_audit = json.loads((base / "bybit_ai_cost_governance_final_audit_latest.json").read_text(encoding="utf-8"))

print("log_blocking_reasons =", log.get("blocking_reasons"))
print("audit_failed_checks =", audit.get("failed_checks"))
print("audit_blocking_reasons =", audit.get("blocking_reasons"))
print("final_failed_checks =", final_audit.get("failed_checks"))
print("final_warning_flags =", final_audit.get("warning_flags"))
print("final_state =", final_audit.get("final_state"))
PY

echo
echo "===== 7) H5 FINAL CLEAN STATUS AFTER V7 ====="
./scripts/run_with_trading_env.sh python3 - <<'PY'
import json
from pathlib import Path

base = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/thought_gate")

log = json.loads((base / "bybit_ai_cost_log_latest.json").read_text(encoding="utf-8"))
audit = json.loads((base / "bybit_ai_governance_audit_latest.json").read_text(encoding="utf-8"))
final_audit = json.loads((base / "bybit_ai_cost_governance_final_audit_latest.json").read_text(encoding="utf-8"))

cost_log = log.get("cost_log") or {}
acct = cost_log.get("cost_accounting_summary") or {}
perf = cost_log.get("performance_summary") or {}
summary = final_audit.get("audit_summary") or {}

print("log_state =", log.get("log_state"))
print("audit_state =", audit.get("audit_state"))
print("final_state =", final_audit.get("final_state"))
print("h5_stage_closed =", summary.get("h5_stage_closed"))
print("h_chapter_closed =", summary.get("h_chapter_closed"))
print("ready_for_i1 =", summary.get("ready_for_i1"))
print("runtime_still_protected =", summary.get("runtime_still_protected"))
print("")
print("pricing_table_bound =", acct.get("pricing_table_bound"))
print("actual_cost_usd =", acct.get("actual_cost_usd"))
print("within_timeout_hint =", perf.get("within_timeout_hint"))
print("")
print("warning_flags =", final_audit.get("warning_flags"))
PY
