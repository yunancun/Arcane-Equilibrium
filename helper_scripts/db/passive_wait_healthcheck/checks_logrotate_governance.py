"""logrotate 治理巡檢哨兵 [95]（OPS F4）。

MODULE_NOTE:
  模塊用途:把 2026-07-15 logrotate drift 事故（runtime 副本漂回只蓋
    /tmp/openclaw/engine.log 死路徑,canonical 已入庫仍漂,致 var 真 engine.log
    輪替自 06-27 起空轉、alpha_discovery_throughput_cron.log 裸奔到 4.5GB 才被
    人工發現;修復 commit 00c11d55b + 416b72835）的持續巡檢面 machine-check 化,
    補進 passive_wait_healthcheck（OPS 審查 finding F4:repo 全域零 logrotate
    drift 防線,本哨兵即補此缺口）:
      [95] trade-core runtime logrotate conf 整檔 sha256 vs repo canonical
      整檔 sha256 —— 不一致 > 24h（距上次合規安裝,drift 起點=最新 applied:true
      manifest 的 mtime;無合規 manifest 的 mismatch=直接視為超窗）= FAIL
      （預設 WARN）。
  主要函數:check_95_logrotate_runtime_matches_repo。
  依賴:helper_scripts/logrotate-openclaw.conf（repo canonical,檔頭載安裝契約）、
    Path.home()/"logrotate-openclaw.conf"（trade-core runtime 副本;
    $OPENCLAW_LOGROTATE_RUNTIME_CONF 可覆寫）、$OPENCLAW_BASE_DIR（repo root）、
    $OPENCLAW_DATA_DIR/logrotate_mutations/（唯一安裝入口
    helper_scripts/cron/install_logrotate_from_repo.sh 落的兩段式 manifest;
    本哨兵只認 applied:true 者為合規安裝,drift 起點=其最新 mtime）。
  硬邊界:純觀測 read-only,不寫 runtime、不 cp、不自動修復;失敗只上報
    （修復動作=operator 跑唯一安裝入口
    `bash helper_scripts/cron/install_logrotate_from_repo.sh --apply`）。任何
    OSError / 壞 JSON 都 fail-soft 成訊息或跳過,不上拋。
    為什麼整檔 sha256 而非 active 行比對（[92] 口徑）:canonical 檔頭安裝契約
    明定「先改 canonical 過 review,再經唯一安裝入口整檔落到 runtime 路徑;禁只改
    runtime 副本」,合規安裝的唯一動作=整檔安裝,故整檔位元組平價就是契約本身的
    machine-check;檔頭註釋（載事故教訓/路徑理由）同屬契約面,漂移即治理信號。
  已知限制:首版以檔案 mtime max() 為 drift proxy 的「反覆手改 runtime 副本可
    不斷刷新 24h 容忍窗」漏洞,已由 manifest proxy 收口——drift 起點改讀最新
    applied:true manifest 的 mtime（嚴格對齊 [92] 的 manifest 口徑）:dry-run 只落
    applied:false,不刷時鐘;刪光 manifest = 無合規安裝紀錄,mismatch 直接視為
    超 24h 窗（fail-closed）;手改 runtime 副本不再影響 drift 時鐘。殘餘面=偽造
    applied:true manifest 屬主動欺詐,超出治理哨兵威脅模型（與 [92] 同界）。
    未來 manifest mtime（時鐘偏移/竄改）另有保守 guard 直接視為超窗。

  ID 說明:[95] 取當前最高 [94](bybit_announcement_sentinel) 之後的自由 slot,
    沿用 codebase [58]→[68] 重定址慣例。
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path


# 環境:OPENCLAW_LOGROTATE_GOVERNANCE_REQUIRED=1 才啟 fail-closed;預設 WARN,避免
# 首日部署 / runtime 尚未首次安裝時誤 FAIL 阻擋（與 [92] crontab 治理 REQUIRED 對齊）。
_REQUIRED_ENV = "OPENCLAW_LOGROTATE_GOVERNANCE_REQUIRED"
_TRUE_VALUES = {"1", "true", "yes", "on", "required"}

# runtime conf 路徑覆寫;預設 Path.home()/"logrotate-openclaw.conf"。生產代碼禁硬編
# 機器 home 絕對路徑:Path.home() 在 trade-core 天然解析到 crontab Tier 0 整點行
# `0 * * * * /usr/sbin/logrotate -s .../logrotate-openclaw.state .../logrotate-openclaw.conf`
# 引用的同一路徑。
_RUNTIME_CONF_ENV = "OPENCLAW_LOGROTATE_RUNTIME_CONF"

# [95] drift 容忍窗:不一致 < 24h 只 WARN（合規安裝剛落地,可能 canonical 又前進 /
# 正在對齊）;> 24h 才升級（與 [92] 24h 窗語意對齊）。
_DRIFT_FAIL_SECONDS = 24 * 3600

# sha256 塊大小:固定 1 MiB 迴圈餵 hashlib,恆定記憶體（理由見 _sha256_of docstring）。
_SHA256_CHUNK_BYTES = 1024 * 1024

# 未來 mtime 容忍:manifest mtime 超出 now + 60s 即視為異常（本地 FS 不應有未來
# mtime;時鐘偏移主機寫入 / touch -t 竄改情境）,走保守超窗路徑。60s 吸收 NTP 級抖動。
_FUTURE_MTIME_TOLERANCE_SECONDS = 60.0

# 修復提示:唯一安裝入口（裸 cp/手編=治理外行為,不落 applied:true manifest,
# 本哨兵不視為合規安裝）。
_INSTALL_HINT = "bash helper_scripts/cron/install_logrotate_from_repo.sh --apply"

# manifest 尺寸上限:正常 manifest ~600B;超過 1 MiB 直接跳過不解析——env 誤指 /
# symlink 指向巨檔時 read_text() 整檔進記憶體是 MemoryError 非 OSError,會崩整條
# runner lane（與 _sha256_of 塊讀防 4.5GB log 同一事故理由）。fail-soft 契約必須真實:
# runner 呼叫點在 try/finally 之外,任何上拋=整個 runner 斷電。
_MANIFEST_MAX_BYTES = 1024 * 1024


def _required_mode() -> bool:
    return os.environ.get(_REQUIRED_ENV, "").strip().lower() in _TRUE_VALUES


def _fail_severity() -> str:
    return "FAIL" if _required_mode() else "WARN"


def _repo_root() -> Path:
    base = os.environ.get("OPENCLAW_BASE_DIR", "").strip()
    if base:
        return Path(base)
    return Path.home() / "BybitOpenClaw" / "srv"


def _data_dir() -> Path:
    return Path(os.environ.get("OPENCLAW_DATA_DIR", "/tmp/openclaw").strip())


def _runtime_conf_path() -> Path:
    raw = os.environ.get(_RUNTIME_CONF_ENV, "").strip()
    if raw:
        return Path(raw)
    return Path.home() / "logrotate-openclaw.conf"


def _sha256_of(path: Path) -> str | None:
    """整檔 sha256 hex;讀不到（缺失/權限/IO）回 None。fail-soft:任何 OSError 不上拋。

    固定 1 MiB 塊迴圈餵 hashlib 而非整檔 read_bytes():env 誤指大檔（本事故主角即
    4.5GB log）時整檔讀是 MemoryError 非 OSError,會崩整條 lane;塊讀恆定記憶體。
    不用 hashlib.file_digest（需 Python 3.11+,runtime 跑 3.10）。
    """
    digest = hashlib.sha256()
    try:
        with path.open("rb") as fh:
            while True:
                chunk = fh.read(_SHA256_CHUNK_BYTES)
                if not chunk:
                    break
                digest.update(chunk)
    except OSError:
        return None
    return digest.hexdigest()


def _newest_applied_manifest_mtime() -> float | None:
    """最新一個 applied:true 的 logrotate_mutations/<UTC>Z/manifest.json mtime;無則 None。

    為什麼只認 applied:true（兩段式 manifest 的第二段,唯一安裝入口 post-verify
    通過後才改寫）:dry-run / 中途被守衛拒絕的 manifest 停在 applied:false,不代表
    runtime 曾被合規安裝,不得刷新 drift 時鐘——否則「跑 dry-run 續命」會複刻首版
    file-mtime proxy 的手改刷新漏洞。`is True` 嚴格判定:字串 "false"/"true"、
    數字 1 等 truthy 變體一律不算合規（JSON 布林才是安裝入口的契約輸出）。
    逐檔 fail-soft:超尺寸（>1 MiB,防巨檔/symlink MemoryError）、讀不到、壞 JSON、
    深巢 JSON（RecursionError）、非 dict 頂層（null/list/字串,.get 會 AttributeError）
    一律跳過——壞檔不掩蓋其他合規紀錄,也不上拋崩 lane（runner 呼叫點無 per-check
    try 包裹,fail-soft 契約必須真實）。
    """
    mut_root = _data_dir() / "logrotate_mutations"
    if not mut_root.is_dir():
        return None
    newest = None
    for manifest in mut_root.glob("*/manifest.json"):
        try:
            st = manifest.stat()
            if st.st_size > _MANIFEST_MAX_BYTES:
                continue
            data = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, ValueError, RecursionError):
            continue
        if not isinstance(data, dict):
            continue
        if data.get("applied") is not True:
            continue
        if newest is None or st.st_mtime > newest:
            newest = st.st_mtime
    return newest


def check_95_logrotate_runtime_matches_repo(now: float | None = None) -> tuple[str, str]:
    """[95] runtime logrotate conf 整檔 sha256 == repo canonical;不一致 > 24h → 升級。

    為什麼整檔 sha256 而非 active 行比對（[92] 口徑）:canonical 檔頭安裝契約明定
    合規安裝的唯一動作=經唯一安裝入口整檔落地,位元組平價即契約的 machine-check;
    檔頭註釋（載事故教訓/路徑理由）同屬契約面,漂移即治理信號。drift 起點=最新
    applied:true manifest mtime（≈ 上次合規安裝時間,與 [92] manifest 口徑嚴格
    對齊）;無合規 manifest 的 mismatch 直接視為超 24h 窗。
    """
    now_ts = time.time() if now is None else now
    sev = _fail_severity()
    base = "[95] logrotate_runtime_matches_repo"

    canonical = _repo_root() / "helper_scripts" / "logrotate-openclaw.conf"
    canonical_sha = _sha256_of(canonical)
    if canonical_sha is None:
        return (sev, f"{base}; repo canonical 缺失或不可讀: {canonical}")

    runtime = _runtime_conf_path()
    runtime_sha = _sha256_of(runtime)
    if runtime_sha is None:
        return (
            sev,
            f"{base}; runtime conf 缺失或不可讀: {runtime} — 每小時 logrotate cron 將無 conf"
            f" 可用=整機零輪替;修復: {_INSTALL_HINT}",
        )

    if runtime_sha == canonical_sha:
        return ("PASS", f"{base}; runtime == canonical (sha256 {canonical_sha[:12]})")

    # 不一致:drift 起點=最新合規安裝 manifest（語意見 _newest_applied_manifest_mtime）。
    newest = _newest_applied_manifest_mtime()
    if newest is None:
        return (
            sev,
            f"{base}; runtime != canonical 且無合規安裝 manifest（治理入口從未 --apply）"
            f" — drift 視為超 24h 窗"
            f"（runtime {runtime_sha[:12]} / canonical {canonical_sha[:12]}）;"
            f"修復: {_INSTALL_HINT}",
        )
    # 未來 mtime 保守 guard:本地 FS 不應有未來 mtime（容忍 60s 抖動）。時鐘偏移主機
    # 寫 manifest / touch -t 竄改會讓 age=max(0, 負)=0 永久落在容忍窗、壓制升級
    # （E2 P1 反例同型）,故一律走保守超窗路徑升 sev。
    if newest > now_ts + _FUTURE_MTIME_TOLERANCE_SECONDS:
        return (
            sev,
            f"{base}; runtime != canonical 且最新合規 manifest mtime 在未來,疑時鐘偏移或"
            f"竄改——保守視為超窗"
            f"（runtime {runtime_sha[:12]} / canonical {canonical_sha[:12]}）;"
            f"修復: {_INSTALL_HINT}",
        )
    age = max(0.0, now_ts - newest)
    if age > _DRIFT_FAIL_SECONDS:
        return (
            sev,
            f"{base}; runtime != canonical 已 {age / 3600:.1f}h (> 24h,距上次合規安裝) — "
            f"runtime {runtime_sha[:12]} / canonical {canonical_sha[:12]};"
            f"修復: {_INSTALL_HINT}",
        )
    return (
        "WARN",
        f"{base}; runtime != canonical {age / 3600:.1f}h (< 24h 容忍窗,剛有合規安裝) — "
        f"可能 canonical 又前進 / 正在對齊",
    )


__all__ = [
    "check_95_logrotate_runtime_matches_repo",
]
