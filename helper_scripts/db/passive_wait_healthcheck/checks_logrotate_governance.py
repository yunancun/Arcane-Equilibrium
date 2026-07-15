"""logrotate 治理巡檢哨兵 [95]（OPS F4）。

MODULE_NOTE:
  模塊用途:把 2026-07-15 logrotate drift 事故（runtime 副本漂回只蓋
    /tmp/openclaw/engine.log 死路徑,canonical 已入庫仍漂,致 var 真 engine.log
    輪替自 06-27 起空轉、alpha_discovery_throughput_cron.log 裸奔到 4.5GB 才被
    人工發現;修復 commit 00c11d55b + 416b72835）的持續巡檢面 machine-check 化,
    補進 passive_wait_healthcheck（OPS 審查 finding F4:repo 全域零 logrotate
    drift 防線,本哨兵即補此缺口）:
      [95] trade-core runtime logrotate conf 整檔 sha256 vs repo canonical
      整檔 sha256 —— 不一致 > 24h = FAIL（預設 WARN）。
  主要函數:check_95_logrotate_runtime_matches_repo。
  依賴:helper_scripts/logrotate-openclaw.conf（repo canonical,檔頭載安裝契約）、
    Path.home()/"logrotate-openclaw.conf"（trade-core runtime 副本;
    $OPENCLAW_LOGROTATE_RUNTIME_CONF 可覆寫）、$OPENCLAW_BASE_DIR（repo root）。
  硬邊界:純觀測 read-only,不寫 runtime、不 cp、不自動修復;失敗只上報
    （修復動作=operator 依 canonical 檔頭安裝契約手動 cp）。任何 OSError 都
    fail-soft 成訊息,不上拋。
    為什麼整檔 sha256 而非 active 行比對（[92] 口徑）:canonical 檔頭安裝契約
    明定「先改 canonical 過 review,再整檔 cp 到 runtime 路徑;禁只改 runtime
    副本」,合規安裝的唯一動作=整檔 cp,故整檔位元組平價就是契約本身的
    machine-check;檔頭註釋（載事故教訓/路徑理由）同屬契約面,漂移即治理信號。
  已知限制:drift 時長以檔案 mtime 為 proxy 的內生限制——反覆手改 runtime 副本
    會不斷刷新 24h 容忍窗,REQUIRED=1 的升級承諾對「持續竄改者」不成立;一次性
    漂移後擱置 > 24h(本事故形態)則正確升級。偵測面不受影響:mismatch 每輪都
    上報 WARN 且訊息含兩側短 hash,永不靜默。未來 mtime(時鐘偏移/竄改)另有
    保守 guard 直接視為超窗,不受此限制影響。根治方向=仿 [92] 落安裝
    receipt/manifest 供 drift 起點查證(follow-up,非本檔範圍)。

  ID 說明:[95] 取當前最高 [94](bybit_announcement_sentinel) 之後的自由 slot,
    沿用 codebase [58]→[68] 重定址慣例。
"""

from __future__ import annotations

import hashlib
import os
import time
from pathlib import Path


# 環境:OPENCLAW_LOGROTATE_GOVERNANCE_REQUIRED=1 才啟 fail-closed;預設 WARN,避免
# 首日部署 / runtime 尚未首次 cp 安裝時誤 FAIL 阻擋（與 [92] crontab 治理 REQUIRED 對齊）。
_REQUIRED_ENV = "OPENCLAW_LOGROTATE_GOVERNANCE_REQUIRED"
_TRUE_VALUES = {"1", "true", "yes", "on", "required"}

# runtime conf 路徑覆寫;預設 Path.home()/"logrotate-openclaw.conf"。生產代碼禁硬編
# /home/ncyu:Path.home() 在 trade-core 天然解析到 crontab Tier 0 整點行
# `0 * * * * /usr/sbin/logrotate -s .../logrotate-openclaw.state .../logrotate-openclaw.conf`
# 引用的同一路徑。
_RUNTIME_CONF_ENV = "OPENCLAW_LOGROTATE_RUNTIME_CONF"

# [95] drift 容忍窗:不一致 < 24h 只 WARN（可能正在對齊 / canonical 剛過 review 更新,
# cp 尚未跟上）;> 24h 才升級（與 [92] 24h 窗語意對齊）。
_DRIFT_FAIL_SECONDS = 24 * 3600

# sha256 塊大小:固定 1 MiB 迴圈餵 hashlib,恆定記憶體（理由見 _sha256_of docstring）。
_SHA256_CHUNK_BYTES = 1024 * 1024

# 未來 mtime 容忍:proxy 超出 now + 60s 即視為異常（本地 FS 不應有未來 mtime;時鐘
# 偏移主機 cp / touch -t 竄改情境）,走保守超窗路徑。60s 吸收 NTP 級抖動。
_FUTURE_MTIME_TOLERANCE_SECONDS = 60.0


def _required_mode() -> bool:
    return os.environ.get(_REQUIRED_ENV, "").strip().lower() in _TRUE_VALUES


def _fail_severity() -> str:
    return "FAIL" if _required_mode() else "WARN"


def _repo_root() -> Path:
    base = os.environ.get("OPENCLAW_BASE_DIR", "").strip()
    if base:
        return Path(base)
    return Path.home() / "BybitOpenClaw" / "srv"


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


def _drift_proxy_mtime(runtime: Path, canonical: Path) -> float | None:
    """drift 起點 proxy = max(mtime(runtime), mtime(canonical));任一 stat 失敗回 None。

    為什麼用兩檔 mtime 取 max 近似「drift 已持續多久」:兩側任一近期被動過都代表
    對齊流程可能正在進行 —— runtime 剛被 cp（operator 正在安裝）或 canonical 剛過
    review 更新（cp 尚未跟上,屬安裝契約預期中的短暫窗）;取 max 即「最後一次任一側
    變動」距今的時長,久於 24h 才視為漂移固化。logrotate 安裝契約=人工整檔 cp、無
    治理入口 manifest 可查（對照 [92] 以 manifest mtime 近似上次合規安裝時間）,
    檔案 mtime 是唯一可得 proxy。stat 失敗（sha 讀後檔案被移走等 race）→ None,
    呼叫端保守視為超窗。
    """
    try:
        return max(runtime.stat().st_mtime, canonical.stat().st_mtime)
    except OSError:
        return None


def check_95_logrotate_runtime_matches_repo(now: float | None = None) -> tuple[str, str]:
    """[95] runtime logrotate conf 整檔 sha256 == repo canonical;不一致 > 24h → 升級。

    為什麼整檔 sha256 而非 active 行比對（[92] 口徑）:canonical 檔頭安裝契約明定
    合規安裝的唯一動作=整檔 cp,位元組平價即契約的 machine-check;檔頭註釋（載
    事故教訓/路徑理由）同屬契約面,漂移即治理信號。
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
            f" 可用=整機零輪替;修復: cp {canonical} {runtime}",
        )

    if runtime_sha == canonical_sha:
        return ("PASS", f"{base}; runtime == canonical (sha256 {canonical_sha[:12]})")

    # 不一致:看已持續多久（proxy 語意見 _drift_proxy_mtime docstring）。
    proxy = _drift_proxy_mtime(runtime, canonical)
    if proxy is None:
        return (
            sev,
            f"{base}; runtime != canonical 且 mtime 不可讀 — drift 保守視為超 24h 窗"
            f"（runtime {runtime_sha[:12]} / canonical {canonical_sha[:12]}）;"
            f"修復: cp {canonical} {runtime}",
        )
    # 未來 mtime 保守 guard:本地 FS 不應有未來 mtime（容忍 60s 抖動）。時鐘偏移主機
    # cp / touch -t 竄改會讓 age=max(0, 負)=0 永久落在容忍窗、壓制升級（E2 P1 反例）,
    # 故一律走保守超窗路徑升 sev。
    if proxy > now_ts + _FUTURE_MTIME_TOLERANCE_SECONDS:
        return (
            sev,
            f"{base}; runtime != canonical 且 mtime 在未來,疑時鐘偏移或竄改——保守視為超窗"
            f"（runtime {runtime_sha[:12]} / canonical {canonical_sha[:12]}）;"
            f"修復: cp {canonical} {runtime}",
        )
    age = max(0.0, now_ts - proxy)
    if age > _DRIFT_FAIL_SECONDS:
        return (
            sev,
            f"{base}; runtime != canonical 已 {age / 3600:.1f}h (> 24h) — "
            f"runtime {runtime_sha[:12]} / canonical {canonical_sha[:12]};"
            f"修復: cp {canonical} {runtime}",
        )
    return (
        "WARN",
        f"{base}; runtime != canonical {age / 3600:.1f}h (< 24h 容忍窗) — 可能正在對齊"
        f"（runtime 剛 cp / canonical 剛更新）",
    )


__all__ = [
    "check_95_logrotate_runtime_matches_repo",
]
