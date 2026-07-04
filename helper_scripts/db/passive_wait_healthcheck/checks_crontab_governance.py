"""crontab 治理巡檢哨兵 [92][93]（P0-2④）。

MODULE_NOTE:
  模塊用途:把 2026-06-27 crontab 屠殺（無記錄 REPLACE 清空 70 行,32 lane 至今
    仍死;FA 2026-07-04 cron_massacre_reconciliation_d2）的兩個持續巡檢面
    machine-check 化,補進 passive_wait_healthcheck:
      [92] live crontab render sha vs repo 正本 render sha —— 不一致 > 24h = FAIL；
      [93] journal 出現無對應 manifest 的 REPLACE = FAIL（治理外 mutation 偵測）。
  主要函數:check_92_crontab_matches_repo_render / check_93_crontab_replace_has_manifest。
  依賴:crontab.trade-core.template（repo 正本）、`crontab -l`（live）、
    journalctl _COMM=crontab（REPLACE 事件）、$OPENCLAW_DATA_DIR/crontab_mutations/
    （install_crontab_from_repo.sh 落的 manifest）。
  硬邊界:兩哨兵純觀測,不寫 crontab、不改 runtime;失敗只上報,不自動修復。
    為什麼 FAIL 而非 WARN:crontab 是資料保全/審計/學習 producer 的觸發面,drift
    或無 manifest 的 REPLACE 直接對應本案不可逆風險（PG 備份斷 7 天),故治理面
    採 fail-closed(operator 明示 mutation 治理升級,FA §七④「現有 WARN 升 FAIL」)。

  ID 說明:[92]/[93] 取當前最高 [91](kline_calibration) 之後的自由 slot,沿用
    codebase [58]→[68] 重定址慣例。
"""

from __future__ import annotations

import os
import re
import subprocess
import time
from pathlib import Path


# 環境:OPENCLAW_CRONTAB_GOVERNANCE_REQUIRED=1 才啟 fail-closed;預設 WARN,避免
# 首日部署 / manifest 尚未 backfill 時誤 FAIL 阻擋（與 cron_heartbeat REQUIRED 對齊）。
_REQUIRED_ENV = "OPENCLAW_CRONTAB_GOVERNANCE_REQUIRED"
_TRUE_VALUES = {"1", "true", "yes", "on", "required"}

# [92] drift 容忍窗:不一致 < 24h 只 WARN（可能正裝新表 / render 差異短暫）;
# > 24h 才升 FAIL（per FA §七④）。
_DRIFT_FAIL_SECONDS = 24 * 3600

# [93] journal 回看窗:只查最近窗口的 REPLACE,避免掃全歷史;預設 26h（涵蓋一日
# 巡檢週期 + 容差,對齊 pg_dump freshness 的 26h 語意）。
_JOURNAL_LOOKBACK = "26 hours ago"


def _required_mode() -> bool:
    return os.environ.get(_REQUIRED_ENV, "").strip().lower() in _TRUE_VALUES


def _fail_severity() -> str:
    return "FAIL" if _required_mode() else "WARN"


def _data_dir() -> Path:
    return Path(os.environ.get("OPENCLAW_DATA_DIR", "/tmp/openclaw").strip())


def _repo_root() -> Path:
    base = os.environ.get("OPENCLAW_BASE_DIR", "").strip()
    if base:
        return Path(base)
    return Path.home() / "BybitOpenClaw" / "srv"


def _active_lines(text: str) -> list[str]:
    """回傳非空、非註釋的 active cron 行(strip 後)。與 installer _count_active_lines 同口徑。"""
    out = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        out.append(line)
    return out


def _render_template(template: Path, head_sha: str) -> str | None:
    """render {{HEAD}}→head_sha 後回傳 active 行 join;讀不到回 None。"""
    try:
        body = template.read_text(encoding="utf-8")
    except OSError:
        return None
    rendered = body.replace("{{HEAD}}", head_sha)
    return "\n".join(_active_lines(rendered))


def _live_crontab() -> str | None:
    """`crontab -l` active 行 join;crontab 缺 / 空回 None。"""
    try:
        proc = subprocess.run(
            ["crontab", "-l"],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    active = _active_lines(proc.stdout)
    if not active:
        return None
    return "\n".join(active)


def _head_sha() -> str | None:
    try:
        proc = subprocess.run(
            ["git", "-C", str(_repo_root()), "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.strip() or None


def _newest_mutation_mtime() -> float | None:
    """最新一個 crontab_mutations/<UTC>Z/manifest.json 的 mtime;無則 None。

    為什麼用 manifest mtime 做「drift 已持續多久」的近似:每次治理內安裝都落新
    manifest,故最新 manifest 時間 ≈ 上次合規安裝時間;drift 若久於此即久未對齊。
    """
    mut_root = _data_dir() / "crontab_mutations"
    if not mut_root.is_dir():
        return None
    newest = None
    for manifest in mut_root.glob("*/manifest.json"):
        try:
            m = manifest.stat().st_mtime
        except OSError:
            continue
        if newest is None or m > newest:
            newest = m
    return newest


def check_92_crontab_matches_repo_render(now: float | None = None) -> tuple[str, str]:
    """[92] live crontab active 行 == repo 正本 render active 行;不一致 > 24h → FAIL。

    為什麼比 active 行而非整檔 sha:註釋 / 空行差異不影響實際排程,只比會跑的行避免
    無意義誤報。drift 持續時長以最新 manifest mtime 近似;無 manifest（治理入口從未
    用過）時 drift 直接視為超窗（本案正是無任何 manifest）。
    """
    now_ts = time.time() if now is None else now
    sev = _fail_severity()
    base = "[92] crontab_matches_repo_render"

    head = _head_sha()
    if head is None:
        return (sev, f"{base}; cannot resolve git HEAD — 無法 render 正本比對")

    template = _repo_root() / "helper_scripts" / "cron" / "crontab.trade-core.template"
    repo_render = _render_template(template, head)
    if repo_render is None:
        return (sev, f"{base}; repo template 缺失或不可讀: {template}")

    live = _live_crontab()
    if live is None:
        # live crontab 空 = 本案屠殺後狀態,直接 fail-closed（無論 required）。
        return ("FAIL", f"{base}; live crontab 空 — 疑似 crontab 屠殺後未恢復")

    if live == repo_render:
        return ("PASS", f"{base}; live == repo render (pin={head})")

    # 不一致:看已持續多久。
    newest = _newest_mutation_mtime()
    if newest is None:
        return (
            sev,
            f"{base}; live != repo render 且無任何 manifest（治理入口從未使用）"
            " — drift 視為超 24h 窗",
        )
    drift_age = max(0.0, now_ts - newest)
    if drift_age > _DRIFT_FAIL_SECONDS:
        return (
            sev,
            f"{base}; live != repo render 已 {drift_age / 3600:.1f}h (> 24h) — 需重裝或對齊正本",
        )
    return (
        "WARN",
        f"{base}; live != repo render {drift_age / 3600:.1f}h (< 24h 容忍窗) — 可能正在裝新表",
    )


def check_93_crontab_replace_has_manifest(now: float | None = None) -> tuple[str, str]:
    """[93] journal 最近窗口每個 crontab REPLACE 都應有對應 manifest;缺對應 → FAIL。

    為什麼:2026-06-27 屠殺的定義性特徵就是「journal 有 REPLACE 但無 before/after/
    manifest」。本哨兵把「REPLACE 數 > manifest 數」變成可偵測信號 —— 治理入口外的
    crontab mutation（繞過 install_crontab_from_repo.sh）會被抓。

    近似口徑:比對 lookback 窗內 journal REPLACE 事件數 vs crontab_mutations/ 內同窗
    manifest 數。REPLACE > manifest 即有無 manifest 的 mutation。journalctl 不可用
    （非 Linux / 無權限）時退 PASS-skip,不阻擋（本哨兵屬 Linux runtime 面）。
    """
    del now  # 窗口用 journalctl --since 相對時間,不需 now 注入
    sev = _fail_severity()
    base = "[93] crontab_replace_has_manifest"

    try:
        proc = subprocess.run(
            ["journalctl", "_COMM=crontab", "--since", _JOURNAL_LOOKBACK, "--no-pager"],
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (OSError, subprocess.SubprocessError):
        return ("PASS", f"{base}; journalctl 不可用（非 Linux runtime / 無權限）— skip")
    if proc.returncode != 0:
        return ("PASS", f"{base}; journalctl 查詢非 0 退出 — skip（非 Linux runtime 面）")

    replace_count = len(re.findall(r"\bREPLACE\b", proc.stdout))
    if replace_count == 0:
        return ("PASS", f"{base}; lookback 窗內無 crontab REPLACE 事件")

    mut_root = _data_dir() / "crontab_mutations"
    manifest_count = 0
    if mut_root.is_dir():
        cutoff = time.time() - 26 * 3600
        for manifest in mut_root.glob("*/manifest.json"):
            try:
                if manifest.stat().st_mtime >= cutoff:
                    manifest_count += 1
            except OSError:
                continue

    if replace_count > manifest_count:
        return (
            sev,
            f"{base}; journal REPLACE={replace_count} > manifest={manifest_count} "
            "— 有繞過治理入口的 crontab mutation（無對應 manifest）",
        )
    return (
        "PASS",
        f"{base}; journal REPLACE={replace_count} <= manifest={manifest_count}（皆有留檔）",
    )


__all__ = [
    "check_92_crontab_matches_repo_render",
    "check_93_crontab_replace_has_manifest",
]
