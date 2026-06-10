#!/usr/bin/env python3
"""
MODULE_NOTE
模塊用途：L2 Mesh P2p incident_sentinel — 本地哨兵（alert-only, never remediate）。
  watchdog 之外的獨立第二觀察者：覆蓋 watchdog 自身死亡的盲區與 watchdog 不看的面
  （DB 異常寫入率、API liveness、migration drift）。設計 SSOT：
  docs/CCAgentWorkSpace/PA/workspace/reports/2026-06-10--l2-p2p-incident-sentinel-design.md。

六個監測軸（全部唯讀證據源）：
  A1 engine 心跳（snapshot mtime 全 stale/缺檔 → CRITICAL）/ A1b watchdog 活性
  （pgrep 唯讀；engine fresh 但 watchdog 死 → WARN）/ A2 canary_events.jsonl 消費
  （alertable 事件 → WARN）/ A3 api healthz（非 200/timeout/refused → CRITICAL）/
  A4 seam reject >10/h（WARN）/ A5 agent.lessons rate >6/h 或白名單外 ≥1/24h（WARN）/
  A6 _sqlx_migrations DB max ≠ repo max 或 success=false（WARN）。

主要類/函數：AxisResult、check_*（七個純函數軸）、should_emit（key-dedup +
  4h re-alert 窗）、run_once（編排）。
依賴：純 stdlib；psycopg2 僅 DB 軸延遲 import（失敗 → db_unreachable WARN，
  file/HTTP 軸照常）。告警 sibling-import engine_watchdog._send_alert_best_effort。

硬邊界（never remediate，E2 可結構性 grep 驗證）：
  - 0 修復動作：無進程操作（A1b 的 pgrep 唯讀例外，只 list 不 signal）。
  - 0 權威面寫入：DB read-only session（default_transaction_read_only=on）
    + statement_timeout，SQL 全唯讀查詢。
  - 唯二本地寫入 = incident_sentinel_state.json + incident_sentinel_events.jsonl；
    絕不寫 canary_events.jsonl / watchdog_state.json（watchdog 進程獨占）。
  - 告警 fire-and-forget 不重試不升級；通道未配置 = 靜默 no-op，本地審計照寫。
  - payload 絕不放 creds / DSN / token。

閾值全 env-overridable（OPENCLAW_SENTINEL_*）。exit code 對齊
canary/healthchecks/_common.py：0=all-pass / 1=任一軸 FAIL / 2=connect error。
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import subprocess
import sys
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger("incident_sentinel")

# ── 常數區：閾值默認 + env override 名 + 事件分類集 ──

STATE_FILE = "incident_sentinel_state.json"
AUDIT_FILE = "incident_sentinel_events.jsonl"
CANARY_EVENTS_FILE = "canary_events.jsonl"

# watchdog 同源 snapshot 清單（engine_watchdog.py:1860-1864；獨立 stat 不經 watchdog）。
SNAPSHOT_FILES = (
    "pipeline_snapshot.json",
    "pipeline_snapshot_paper.json",
    "pipeline_snapshot_demo.json",
    "pipeline_snapshot_live.json",
)

# A2 事件分類（設計 §1.2 表）：
# ALERTABLE = watchdog 只落檔無人讀的事件（MEDIUM-2 收口）；
# 排除集 = watchdog 已自行 alert 的事件 + 正向事件 —— 不重複告警。
CANARY_ALERTABLE_EVENTS = frozenset({
    "RESTART_FAILED",
    "NETWORK_OUTAGE",
    "TRADING_INERT_PROLONGED",
    "RESTART_SKIPPED",
})

# A5 合法 source 白名單（exhaustive caller grep，設計 §1.3）。
# 注意：06-10 污染事故的 rows source='ml_advisory' 是合法值 —— 白名單抓不到，
# 必須配 rate 軸（雙層設計的依據）。新增合法 writer 時同步維護此常數。
LESSONS_SOURCE_WHITELIST = ("l2_session", "ml_advisory", "dead_mode_seed")

SEVERITY_CRITICAL = "CRITICAL"
SEVERITY_WARN = "WARN"
SEVERITY_INFO = "INFO"

EXIT_PASS = 0
EXIT_FAIL = 1
EXIT_CONNECT_ERROR = 2

_MIGRATION_NAME_RE = re.compile(r"^V(\d+)__.*\.sql$")


def _env_float(name: str, default: float) -> float:
    """讀 env 浮點閾值；壞值回 default（哨兵自身配置錯不得毀整輪）。"""
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        logger.warning("env %s 非數值（%r），改用默認 %s", name, raw, default)
        return default


def _env_int(name: str, default: int) -> int:
    return int(_env_float(name, float(default)))


def _alertable_event_set() -> frozenset:
    """A2 事件集；OPENCLAW_SENTINEL_CANARY_ALERTABLE（csv）可覆蓋（設計 OQ-3：
    operator 可把 RESTART_SKIPPED 等移出事件集）。"""
    raw = os.environ.get("OPENCLAW_SENTINEL_CANARY_ALERTABLE", "").strip()
    if not raw:
        return CANARY_ALERTABLE_EVENTS
    return frozenset(e.strip() for e in raw.split(",") if e.strip())


# ── AxisResult：每軸統一輸出 ──


@dataclass
class AxisResult:
    """每軸統一輸出。alert_key=None 表示無告警需求（ok=True 或 axis-error 只審計）。"""

    axis: str
    ok: bool
    alert_key: str | None = None
    severity: str = SEVERITY_WARN
    subject: str = ""
    body: str = ""
    evidence: dict = field(default_factory=dict)


# ── 純函數軸（path / now / conn / opener / runner 全注入 → 可測零真依賴） ──


def check_engine_heartbeat(data_dir: str, now: float, threshold: float) -> AxisResult:
    """A1：4 個 pipeline_snapshot*.json 任一 fresh = alive；全 stale/缺檔 = CRITICAL。

    為什麼 900s：watchdog 閾值 45s、自愈循環 + circuit-break 通常 <10min；
    15min 仍 stale = watchdog 自愈失敗或 watchdog 已死（20h 事故形狀）。
    sentinel 是後盾不是替身，必須晚於 watchdog 反應。
    """
    ages: dict[str, object] = {}
    any_fresh = False
    for name in SNAPSHOT_FILES:
        path = Path(data_dir) / name
        try:
            age = now - path.stat().st_mtime
            ages[name] = round(age, 1)
            if age <= threshold:
                any_fresh = True
        except OSError:
            ages[name] = "missing"
    evidence = {"snapshot_ages": ages, "threshold_seconds": threshold}
    if any_fresh:
        return AxisResult(axis="a1_engine", ok=True, evidence=evidence)
    return AxisResult(
        axis="a1_engine", ok=False, alert_key="a1:engine_stale", severity=SEVERITY_CRITICAL,
        subject="OpenClaw sentinel: a1_engine — all pipeline snapshots stale/missing",
        body=(
            f"全部 pipeline_snapshot*.json 過期或缺檔（閾值 {threshold:.0f}s）。\n"
            f"ages: {json.dumps(ages)}\n"
            "action: ssh trade-core; 檢查 engine 與 watchdog 進程、watchdog.log、"
            "canary_events.jsonl 尾部。"
        ),
        evidence=evidence,
    )


def _default_watchdog_pgrep() -> bool:
    """pgrep 唯讀探測 watchdog 進程是否存在（darwin/linux 通用）。

    never-remediate 不變量：只 list 不 signal——這是全檔唯一進程面操作。
    """
    try:
        proc = subprocess.run(
            ["pgrep", "-f", "engine_watchdog.py"],
            capture_output=True, timeout=10, check=False,
        )
        return proc.returncode == 0 and bool(proc.stdout.strip())
    except Exception as exc:  # noqa: BLE001 - 探測失敗視為未知，保守回 False 由上層 WARN
        logger.warning("watchdog pgrep 探測失敗：%s", exc)
        return False


def check_watchdog_alive(engine_ok: bool, pgrep_runner=None) -> AxisResult:
    """A1b：watchdog 活性次軸。engine fresh 但 watchdog 死 = 自愈失能降級（WARN）。

    為什麼 A1 已觸發時不另發：兩軸同時告警 = 同一事故重複噪音；
    watchdog 缺席資訊由 run_once 併入 A1 payload。
    """
    runner = pgrep_runner or _default_watchdog_pgrep
    alive = bool(runner())
    evidence = {"watchdog_alive": alive, "engine_ok": engine_ok}
    if alive:
        return AxisResult(axis="a1b_watchdog", ok=True, evidence=evidence)
    if not engine_ok:
        # A1 已觸發：不獨立發，資訊併入 A1（run_once 負責），本軸只審計。
        evidence["folded_into_a1"] = True
        return AxisResult(axis="a1b_watchdog", ok=True, evidence=evidence)
    return AxisResult(
        axis="a1b_watchdog", ok=False, alert_key="a1b:watchdog_absent", severity=SEVERITY_WARN,
        subject="OpenClaw sentinel: a1b_watchdog — watchdog process absent (engine still fresh)",
        body=(
            "engine snapshot 仍 fresh，但 pgrep 找不到 engine_watchdog.py 進程：\n"
            "自愈能力失能（尚非事故）。\n"
            "action: ssh trade-core; 以標準啟動腳本重新 spawn watchdog，並查其退出原因。"
        ),
        evidence=evidence,
    )


def check_canary_events(
    data_dir: str,
    cursor_ts: float,
    now: float,
    alertable: frozenset | None = None,
) -> tuple[AxisResult, float]:
    """A2：tail canary_events.jsonl 自上輪 ts 游標，alertable 事件聚合一條 WARN。

    游標用 ts 而非 byte offset：rotate（fresh_start.sh 歸檔）後新檔事件 ts 必然
    更新，游標天然 rotate-safe。回傳 (result, 新游標)。
    """
    alertable = alertable if alertable is not None else _alertable_event_set()
    path = Path(data_dir) / CANARY_EVENTS_FILE
    counts: dict[str, int] = {}
    malformed = 0
    max_ts = cursor_ts
    max_alertable_ts = 0.0
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                    ts = float(ev["ts"])
                    name = str(ev.get("event", ""))
                except (ValueError, TypeError, KeyError):
                    malformed += 1
                    continue
                max_ts = max(max_ts, ts)
                if ts <= cursor_ts:
                    continue
                if name in alertable:
                    counts[name] = counts.get(name, 0) + 1
                    max_alertable_ts = max(max_alertable_ts, ts)
    except OSError:
        # 檔案缺失 = 無事件可消費（fresh 環境 / 剛 rotate），非異常。
        pass

    total = sum(counts.values())
    evidence = {
        "alertable_counts": counts,
        "cursor_ts": cursor_ts,
        "new_cursor_ts": max_ts,
        "malformed_lines": malformed,
    }
    if total == 0:
        return AxisResult(axis="a2_canary", ok=True, evidence=evidence), max_ts
    # key 含批次指紋（最大 alertable ts，全精度禁截秒）：游標推進後同批不重發；
    # 新批事件 ts 必嚴格大於游標 ≥ 前批最大 ts → 必為新 key。若 int() 截整數秒，
    # 同一秒內 burst 被 cron 切成兩輪時次輪同 key → should_emit 靜默吞且游標
    # 已推過不重掃（MED-2）。
    result = AxisResult(
        axis="a2_canary", ok=False, severity=SEVERITY_WARN,
        alert_key=f"a2:through_{max_alertable_ts}",
        subject=f"OpenClaw sentinel: a2_canary — {total} unconsumed alertable canary event(s)",
        body=(
            f"canary_events.jsonl 新增 alertable 事件（watchdog 只落檔未告警）：\n"
            f"{json.dumps(counts)}\n"
            "action: ssh trade-core; 讀 canary_events.jsonl 對應事件 + watchdog.log 排查。"
        ),
        evidence=evidence,
    )
    return result, max_ts


def check_api_healthz(base_url: str, opener=None, timeout: float = 5.0) -> AxisResult:
    """A3：GET /api/v1/healthz（無 auth 監控端點，system_legacy_routes.py:326）。

    非 200 / timeout / refused 皆 CRITICAL：api down = operator 全盲
    （GUI/console 同 host 同進程）。key 固定 a3:api_down——持續 down 由
    re-alert 窗控制節奏，不因錯誤型態變化而重複告警。
    """
    opener = opener or urllib.request.urlopen
    url = base_url.rstrip("/") + "/api/v1/healthz"
    status: object = None
    error: str | None = None
    try:
        with opener(url, timeout=timeout) as resp:
            status = getattr(resp, "status", None) or resp.getcode()
    except Exception as exc:  # noqa: BLE001 - 任何網路層錯誤都是同一個事實：api 不可達
        error = f"{type(exc).__name__}: {exc}"
    evidence = {"url": url, "status": status, "error": error}
    if status == 200:
        return AxisResult(axis="a3_api", ok=True, evidence=evidence)
    return AxisResult(
        axis="a3_api", ok=False, alert_key="a3:api_down", severity=SEVERITY_CRITICAL,
        subject="OpenClaw sentinel: a3_api — healthz unreachable or non-200",
        body=(
            f"GET {url} 失敗：status={status} error={error}\n"
            "action: ssh trade-core; 檢查 uvicorn 進程與 api 日誌。"
        ),
        evidence=evidence,
    )


def check_l2_seam_rejects(conn, now: float, threshold: int = 10) -> AxisResult:
    """A4：l2_gate_seam_log 近 1h reject 計數 > 閾值 → WARN。

    baseline ≈ 0（全 capability disabled）；>10/h = 有 caller 在 loop dispatch
    或 gate 異常翻 reject，絕對閾值即可、無需 baseline 學習。
    """
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT count(*) FROM learning.l2_gate_seam_log "
            "WHERE verdict = 'reject' AND ts > now() - interval '1 hour'"
        )
        count = int(cur.fetchone()[0])
    finally:
        cur.close()
    evidence = {"reject_count_1h": count, "threshold": threshold}
    if count <= threshold:
        return AxisResult(axis="a4_seam", ok=True, evidence=evidence)
    return AxisResult(
        axis="a4_seam", ok=False, alert_key="a4:reject_surge", severity=SEVERITY_WARN,
        subject=f"OpenClaw sentinel: a4_seam — l2_gate_seam_log rejects {count}/h (> {threshold})",
        body=(
            f"learning.l2_gate_seam_log 近 1h verdict='reject' 計數 {count} > {threshold}。\n"
            "action: ssh trade-core; 查 seam log 最近 rows 的 capability/reason，"
            "確認是否有 caller loop dispatch 或 gate 異常。"
        ),
        evidence=evidence,
    )


def check_lessons_anomaly(
    conn,
    now: float,
    rate_threshold: int = 6,
    whitelist: tuple = LESSONS_SOURCE_WHITELIST,
) -> AxisResult:
    """A5：agent.lessons 雙層異常寫入偵測（06-10 fixture 污染事故制度化）。

    雙層必要性：污染 rows 的 source='ml_advisory' 是合法值 → 白名單抓不到，
    rate 抓量（7 輪 × 3 = 21 rows 遠超 6/h）；白名單抓未來新出現的越權 namespace。
    """
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT count(*) FROM agent.lessons "
            "WHERE created_at > now() - interval '1 hour'"
        )
        rate_count = int(cur.fetchone()[0])
        cur.execute(
            "SELECT count(*) FROM agent.lessons "
            "WHERE source NOT IN %s AND created_at > now() - interval '24 hours'",
            (tuple(whitelist),),
        )
        offlist_count = int(cur.fetchone()[0])
    finally:
        cur.close()
    triggers = []
    if rate_count > rate_threshold:
        triggers.append("rate")
    if offlist_count >= 1:
        triggers.append("whitelist")
    evidence = {
        "rate_count_1h": rate_count,
        "rate_threshold": rate_threshold,
        "offlist_count_24h": offlist_count,
        "source_whitelist": list(whitelist),
    }
    if not triggers:
        return AxisResult(axis="a5_lessons", ok=True, evidence=evidence)
    fingerprint = "+".join(triggers)
    return AxisResult(
        axis="a5_lessons", ok=False, alert_key=f"a5:{fingerprint}", severity=SEVERITY_WARN,
        subject=f"OpenClaw sentinel: a5_lessons — agent.lessons anomalous writes ({fingerprint})",
        body=(
            f"agent.lessons 異常寫入：1h 計數 {rate_count}（閾值 {rate_threshold}），"
            f"24h 白名單外 source 計數 {offlist_count}。\n"
            "action: ssh trade-core; 查 agent.lessons 最近 rows 的 source/context_id，"
            "辨識寫入者（測試污染 / 越權 namespace / 真實高頻 advisory）。"
        ),
        evidence=evidence,
    )


def check_migrations_drift(conn, repo_migrations_dir: str) -> AxisResult:
    """A6：_sqlx_migrations 與 repo V*.sql 最大編號比對 + bool_and(success)。

    DB<repo = 部署漏 apply；DB>repo = worktree stale 或手動 apply；
    success=false = apply 中斷（05-02 sqlx hash drift 事故域）。非即時事故故 WARN。
    """
    repo_max = 0
    try:
        for name in os.listdir(repo_migrations_dir):
            m = _MIGRATION_NAME_RE.match(name)
            if m:
                repo_max = max(repo_max, int(m.group(1)))
    except OSError as exc:
        # repo 目錄不可讀 = 哨兵自身 base-dir 配置錯，只審計不告警（避免誤報風暴）。
        return AxisResult(
            axis="a6_migrations", ok=False, alert_key=None, severity=SEVERITY_WARN,
            evidence={"axis_error": f"repo migrations dir unreadable: {exc}"},
        )

    cur = conn.cursor()
    try:
        cur.execute("SELECT max(version), bool_and(success) FROM _sqlx_migrations")
        row = cur.fetchone()
    finally:
        cur.close()
    db_max = int(row[0]) if row and row[0] is not None else 0
    all_success = bool(row[1]) if row and row[1] is not None else False
    evidence = {"db_max": db_max, "repo_max": repo_max, "all_success": all_success}
    if db_max == repo_max and all_success:
        return AxisResult(axis="a6_migrations", ok=True, evidence=evidence)
    return AxisResult(
        axis="a6_migrations", ok=False, severity=SEVERITY_WARN,
        alert_key=f"a6:db{db_max}_repo{repo_max}_{'ok' if all_success else 'fail'}",
        subject=(
            f"OpenClaw sentinel: a6_migrations — drift db={db_max} repo={repo_max}"
            f" success={'true' if all_success else 'FALSE'}"
        ),
        body=(
            f"_sqlx_migrations max={db_max} vs repo V*.sql max={repo_max}，"
            f"bool_and(success)={all_success}。\n"
            "action: ssh trade-core; 對照部署記錄確認漏 apply / stale worktree / "
            "apply 中斷，按 repair SOP 處理。"
        ),
        evidence=evidence,
    )


# ── DB 連線（延遲 import；read-only session） ──


def resolve_dsn() -> str | None:
    """DSN 解析：OPENCLAW_DATABASE_URL 優先，否則 POSTGRES_* 拼裝（host 默認
    127.0.0.1，口徑對齊 lib/pg_connect.py 注釋；不 import 它——其 MODULE_NOTE
    明文只服務 offline report scripts）。缺必要件回 None（→ db_unreachable）。
    """
    url = os.environ.get("OPENCLAW_DATABASE_URL", "").strip()
    if url:
        return url
    user = os.environ.get("POSTGRES_USER", "").strip()
    password = os.environ.get("POSTGRES_PASSWORD", "").strip()
    db = os.environ.get("POSTGRES_DB", "").strip()
    host = os.environ.get("POSTGRES_HOST", "").strip() or "127.0.0.1"
    port = os.environ.get("POSTGRES_PORT", "").strip() or "5432"
    if not (user and password and db):
        return None
    return f"postgresql://{user}:{password}@{host}:{port}/{db}"


def _connect_readonly(dsn: str):
    """psycopg2 延遲 import + read-only session 連線。

    為什麼 read-only 在 session 層強制：never-remediate 不是註釋承諾，
    任何意外寫入在 PG 端直接被拒（與 statement_timeout 防掛雙保險）。
    """
    import psycopg2  # 延遲 import：無 DB 軸調用即不需要此依賴

    timeout_ms = _env_int("OPENCLAW_SENTINEL_STATEMENT_TIMEOUT_MS", 10000)
    return psycopg2.connect(
        dsn,
        options=f"-c default_transaction_read_only=on -c statement_timeout={timeout_ms}",
    )


# ── state / 審計 / dedup ──


def load_state(data_dir: str) -> dict:
    """讀 dedup state；缺檔/壞檔回空（最壞多發一條 alert，cron 下輪自癒）。"""
    try:
        with open(Path(data_dir) / STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError, OSError, ValueError):
        return {}


def save_state(data_dir: str, state: dict) -> None:
    """原子寫 state（tmp + rename，mirror watchdog save_state）；失敗只 log 不拋。"""
    path = Path(data_dir) / STATE_FILE
    tmp = path.with_suffix(".tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
        os.replace(tmp, path)
    except OSError as exc:
        logger.warning("sentinel state 保存失敗：%s", exc)


def _append_audit(data_dir: str, record: dict) -> None:
    """自身審計 jsonl append（全檔唯二本地寫入之一）；best-effort 不拋。"""
    try:
        path = Path(data_dir) / AUDIT_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=str) + "\n")
    except OSError as exc:
        logger.warning("sentinel 審計寫入失敗：%s", exc)


def should_emit(state: dict, result: AxisResult, now: float, re_alert_interval: float) -> bool:
    """key-dedup + re-alert 窗（mirror emit_engine_down_alert_if_new 語義，state 檔獨立）。

    - 新 key（無記錄或指紋變化）→ 發，記 window_seq=1。
    - 同 key 持續異常 → 每 re_alert_interval 重發一次（window_seq 遞增）。
    - ok / alert_key=None → 不發（恢復清 key 由 run_once 處理，因 CRITICAL 要發 INFO）。
    會 mutate state；caller 負責 save_state。
    """
    if result.ok or result.alert_key is None:
        return False
    entries = state.setdefault("alert_keys", {})
    entry = entries.get(result.axis)
    if not isinstance(entry, dict) or entry.get("key") != result.alert_key:
        entries[result.axis] = {
            "key": result.alert_key,
            "severity": result.severity,
            "first_alert_ts": now,
            "last_alert_ts": now,
            "window_seq": 1,
        }
        return True
    try:
        last_ts = float(entry.get("last_alert_ts", 0.0))
    except (TypeError, ValueError):
        last_ts = 0.0
    if now - last_ts >= re_alert_interval:
        entry["last_alert_ts"] = now
        entry["window_seq"] = int(entry.get("window_seq", 1)) + 1
        return True
    return False


# ── 告警發送（sibling-import watchdog 的零依賴 emitter） ──


def _resolve_alert_fn():
    """sibling-import engine_watchdog._send_alert_best_effort
    （sys.path 同目錄慣例，見 test_watchdog_alert.py:26-40）。

    import 失敗回 no-op：告警鏈故障不得毀偵測輪（審計 jsonl 仍完整可事後查）。
    """
    here = str(Path(__file__).resolve().parent)
    if here not in sys.path:
        sys.path.insert(0, here)
    try:
        import engine_watchdog  # noqa: PLC0415 - 刻意延遲 import（103KB 檔，僅發送時需要）

        return engine_watchdog._send_alert_best_effort
    except Exception as exc:  # noqa: BLE001 - fail-soft：哨兵偵測輪不得因告警鏈失敗而毀
        logger.warning("engine_watchdog emitter import 失敗，告警降級為 no-op：%s", exc)
        return lambda subject, body, severity, data_dir: None


# ── 編排層 ──


def _safe_axis(axis_id: str, fn, *args, **kwargs) -> AxisResult:
    """per-axis try/except 隔離：單軸異常絕不毀整輪。

    axis-error 不發 alert（避免代碼 bug 變告警風暴），但 ok=False 反映進
    exit code 與審計 jsonl，operator 手動跑 / 巡檢可見。
    """
    try:
        return fn(*args, **kwargs)
    except Exception as exc:  # noqa: BLE001 - 隔離邊界，必須 catch-all
        logger.warning("axis %s 異常（隔離，不毀整輪）：%s", axis_id, exc)
        return AxisResult(
            axis=axis_id, ok=False, alert_key=None, severity=SEVERITY_WARN,
            evidence={"axis_error": f"{type(exc).__name__}: {exc}"},
        )


def run_once(
    data_dir: str, base_dir: str, *,
    dsn_resolver=None, conn_factory=None, alert_fn=None, opener=None,
    pgrep_runner=None, now: float | None = None, sleep_fn=time.sleep,
    dry_run: bool = False,
) -> int:
    """單輪偵測：六軸 → dedup → 告警 → 審計 → exit code。

    所有外部依賴可注入（測試隔離鐵則）；dry_run 跑全軸 + 寫 state/審計，
    只抑制發送並印 verdict。
    """
    now = time.time() if now is None else now
    re_alert_interval = _env_float("OPENCLAW_SENTINEL_RE_ALERT_INTERVAL_SECONDS", 4 * 3600.0)
    drain_seconds = _env_float("OPENCLAW_SENTINEL_ALERT_DRAIN_SECONDS", 6.0)

    state = load_state(data_dir)
    results: list[AxisResult] = []

    # ── file 軸：A1 / A1b ────────────────────────────────────────────────
    a1 = _safe_axis(
        "a1_engine", check_engine_heartbeat, data_dir, now,
        _env_float("OPENCLAW_SENTINEL_ENGINE_STALE_SECONDS", 900.0),
    )
    a1b = _safe_axis("a1b_watchdog", check_watchdog_alive, a1.ok, pgrep_runner)
    # A1 已觸發且 watchdog 缺席：資訊併入 A1 payload（A1b 不另發，見軸 docstring）。
    if not a1.ok and a1b.evidence.get("watchdog_alive") is False:
        a1.evidence["watchdog_process_absent"] = True
        a1.body += "\nwatchdog process absent（pgrep 無命中）—— 自愈鏈同時失能。"
    results.extend([a1, a1b])

    # ── file 軸：A2（游標在 state） ──────────────────────────────────────
    raw_cursor = state.get("canary_cursor_ts")
    try:
        cursor_ts = float(raw_cursor)
    except (TypeError, ValueError):
        # 首跑（或 state 損壞）：游標 = now - 1h，不回放陳年事件。
        cursor_ts = now - 3600.0
    try:
        a2, new_cursor = check_canary_events(data_dir, cursor_ts, now)
    except Exception as exc:  # noqa: BLE001 - 與 _safe_axis 同語義（tuple 回傳故手寫）
        logger.warning("axis a2_canary 異常（隔離，不毀整輪）：%s", exc)
        a2 = AxisResult(
            axis="a2_canary", ok=False, alert_key=None, severity=SEVERITY_WARN,
            evidence={"axis_error": f"{type(exc).__name__}: {exc}"},
        )
        new_cursor = cursor_ts
    state["canary_cursor_ts"] = new_cursor
    results.append(a2)

    # ── HTTP 軸：A3 ─────────────────────────────────────────────────────
    results.append(_safe_axis(
        "a3_api", check_api_healthz,
        os.environ.get("OPENCLAW_SENTINEL_API_BASE", "http://127.0.0.1:8000"),
        opener,
        _env_float("OPENCLAW_SENTINEL_API_TIMEOUT_SECONDS", 5.0),
    ))

    # ── DB 軸：A4 / A5 / A6（不可達 → 三軸聚合一條 db_unreachable WARN） ──
    conn = None
    db_unreachable_reason: str | None = None
    try:
        if conn_factory is not None:
            conn = conn_factory()
            if conn is None:
                db_unreachable_reason = "conn_factory_returned_none"
        else:
            dsn = (dsn_resolver or resolve_dsn)()
            if dsn is None:
                db_unreachable_reason = "dsn_unresolved"
            else:
                conn = _connect_readonly(dsn)
    except Exception as exc:  # noqa: BLE001 - PG down / psycopg2 缺失皆同一事實：DB 不可達
        db_unreachable_reason = f"{type(exc).__name__}: {exc}"
        conn = None

    if conn is not None:
        try:
            results.append(_safe_axis(
                "a4_seam", check_l2_seam_rejects, conn, now,
                _env_int("OPENCLAW_SENTINEL_SEAM_REJECTS_PER_HOUR", 10),
            ))
            results.append(_safe_axis(
                "a5_lessons", check_lessons_anomaly, conn, now,
                _env_int("OPENCLAW_SENTINEL_LESSONS_RATE_PER_HOUR", 6),
            ))
            results.append(_safe_axis(
                "a6_migrations", check_migrations_drift, conn,
                str(Path(base_dir) / "sql" / "migrations"),
            ))
        finally:
            try:
                conn.close()
            except Exception:  # noqa: BLE001 - 關閉失敗無後果（read-only session）
                pass
    else:
        # PG down 也是 incident：自身作為一條 WARN，與各 DB 軸 alert 分 key。
        # payload 只放 reason 類別，絕不放 DSN/creds。
        results.append(AxisResult(
            axis="db_unreachable", ok=False, alert_key="db:unreachable", severity=SEVERITY_WARN,
            subject="OpenClaw sentinel: db_unreachable — A4/A5/A6 cannot be evaluated",
            body=(
                f"DB 不可達（{db_unreachable_reason}），seam/lessons/migrations 三軸本輪未評估。\n"
                "action: ssh trade-core; 檢查 trading_postgres 容器與連線配置。"
            ),
            evidence={"reason": db_unreachable_reason},
        ))

    # ── dedup → 發送（含 CRITICAL 恢復 INFO） ───────────────────────────
    alert_fn = alert_fn or _resolve_alert_fn()
    alerts_sent: list[dict] = []

    def _emit(subject: str, body: str, severity: str, axis: str, kind: str) -> None:
        if not dry_run:
            try:
                alert_fn(subject, body, severity, data_dir)
            except Exception as exc:  # noqa: BLE001 - fire-and-forget：發送失敗不重試不升級
                logger.warning("alert 發送失敗（不重試）：%s", exc)
        alerts_sent.append({
            "axis": axis, "kind": kind, "severity": severity,
            "subject": subject, "dry_run": dry_run,
        })

    for result in results:
        if result.ok:
            entry = state.get("alert_keys", {}).pop(result.axis, None)
            # CRITICAL 軸恢復發 INFO RECOVERED（mirror ENGINE_RECOVERED 慣例）；
            # WARN 軸靜默清 key（避免低嚴重度雙倍噪音）。
            if isinstance(entry, dict) and entry.get("severity") == SEVERITY_CRITICAL:
                _emit(
                    f"OpenClaw sentinel: {result.axis} — RECOVERED",
                    f"軸 {result.axis} 已恢復（先前 key={entry.get('key')}）。",
                    SEVERITY_INFO, result.axis, "recovered",
                )
            continue
        if should_emit(state, result, now, re_alert_interval):
            seq = state["alert_keys"][result.axis]["window_seq"]
            subject = result.subject + (f" (re-alert #{seq})" if seq > 1 else "")
            _emit(subject, result.body, result.severity, result.axis, "alert")

    # ── exit code（對齊 _common.py：0/1/2） ──────────────────────────────
    fails = [r for r in results if not r.ok]
    if not fails:
        exit_code = EXIT_PASS
    elif all(r.axis == "db_unreachable" for r in fails):
        exit_code = EXIT_CONNECT_ERROR
    else:
        exit_code = EXIT_FAIL

    # ── 審計 + state 持久化（dry-run 也寫：演練要能驗 dedup state） ──────
    _append_audit(data_dir, {
        "ts": now, "kind": "run", "dry_run": dry_run, "exit_code": exit_code,
        "axes": [
            {"axis": r.axis, "ok": r.ok, "alert_key": r.alert_key,
             "severity": (None if r.ok else r.severity), "evidence": r.evidence}
            for r in results
        ],
        "alerts_sent": alerts_sent,
    })
    save_state(data_dir, state)

    if dry_run:
        for r in results:
            print(f"{r.axis}: {'OK' if r.ok else 'FAIL'} key={r.alert_key} evidence={json.dumps(r.evidence, default=str)}")
        print(f"exit_code={exit_code} would_send={len(alerts_sent)}")

    # 短命進程 drain：daemon-thread alert 在 main 退出前排空（> 5s HTTP timeout）。
    # watchdog 是長駐進程沒這問題，sentinel 是短命進程必須兜底。
    if alerts_sent and not dry_run:
        sleep_fn(drain_seconds)

    return exit_code


def _probe_alert(data_dir: str, alert_fn=None, sleep_fn=time.sleep) -> int:
    """--probe-alert：發一條 INFO probe 驗通道（演練 §8.3-1）；通道未配置 =
    emitter 一次性 warn + 靜默 no-op，本地審計仍寫。"""
    alert_fn = alert_fn or _resolve_alert_fn()
    subject = "OpenClaw sentinel: probe — channel verification"
    body = "incident_sentinel 告警通道演練（無事故，僅驗證端到端送達）。"
    try:
        alert_fn(subject, body, SEVERITY_INFO, data_dir)
    except Exception as exc:  # noqa: BLE001 - fire-and-forget
        logger.warning("probe alert 發送失敗：%s", exc)
    _append_audit(data_dir, {
        "ts": time.time(), "kind": "probe_alert", "subject": subject,
    })
    sleep_fn(_env_float("OPENCLAW_SENTINEL_ALERT_DRAIN_SECONDS", 6.0))
    return EXIT_PASS


def main(argv=None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [INCIDENT-SENTINEL] %(levelname)s %(message)s",
    )
    parser = argparse.ArgumentParser(
        prog="incident_sentinel",
        description="L2 Mesh P2p 本地哨兵：6 軸唯讀監測，alert-only never remediate。",
    )
    parser.add_argument(
        "--data-dir", default=os.environ.get("OPENCLAW_DATA_DIR", "/tmp/openclaw"),
        help="runtime data dir（默認 $OPENCLAW_DATA_DIR else /tmp/openclaw，對齊 watchdog）")
    parser.add_argument(
        "--base-dir",
        default=os.environ.get("OPENCLAW_BASE_DIR", "") or str(Path(__file__).resolve().parents[2]),
        help="repo root（A6 解析 sql/migrations 用；默認 $OPENCLAW_BASE_DIR else 由腳本位置推算）")
    parser.add_argument("--once", action="store_true",
                        help="單輪模式（默認且唯一模式；旗標僅供 cron 行自說明）")
    parser.add_argument("--dry-run", action="store_true",
                        help="跑全軸但不發送，印 verdict（state/審計照寫，供演練驗 dedup）")
    parser.add_argument("--probe-alert", action="store_true",
                        help="發一條 INFO probe 驗告警通道（不跑監測軸）")
    args = parser.parse_args(argv)

    if args.probe_alert:
        return _probe_alert(args.data_dir)
    return run_once(args.data_dir, args.base_dir, dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
