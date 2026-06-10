"""SM Option 2 收斂 soak 可觀測性 healthcheck `[81]`（P5-SM-OPTION2 B-3，rework (b)+(b-i)）。

模塊用途：cron-side（SQL-cursor）判 SM Option 2 step-(i) soak 是否健康。

**rework 背景（operator 拍板 (b)+(b-i)，2026-06-03）**：E2 HIGH-2 + PA reconciliation
（`2026-06-03--p5_sm_soak_equiv_sampler_reconciliation.md`）證實——Option 2 下「歷史
replay 驅動 contemporaneous comparator」語意不可達：sampler 拿歷史 Rust-GRANTED row
對撞 Python hub「當前」auth state，steady-state Python hub 結構上未授權 → 每筆歷史
GRANTED → Python 影子 DENIED → comparator divergence 永遠卡死。故 comparator 從「硬
gate」**降為觀測性信號（非 gate）**。

**cutover gate 新定義 = 4a CI 綠 AND P-LIVE soak 健康**（不含 comparator counter）：
  - **4a 離線全分支 parity**（`sm_contract.rs` + `test_sm_contract_parity.py`，190-vector
    兩獨立實作）是 P-EQUIV 的 authoritative proof，**CI 物（非本 soak healthcheck）**。
  - **P-LIVE 信號**（本 healthcheck 唯一 gate）：讀 `learning.lease_transitions` row
    count + freshness，證 Rust 權威路徑（真實 engine + serde + IPC + PG writer +
    profile/engine_mode 解析）熱路徑在跑且健康。**這徹底解原 fake-pass**：gate 改讀
    真實熱路徑 `lease_transitions`（Rust 真寫），非空轉的 comparator counter（Option 2
    steady-state organic≈0、sampler 語意不可達）。

主要函數：``check_81_lease_ipc_soak``（``(cur) -> (status, msg)``，與既有 checks_*.py
同契約）。

依賴：
  - ``learning.lease_transitions``（V054，Rust writer 寫，read-only）—— **gate 唯一資料源**。
  - ``learning.lease_ipc_divergence_snapshot``（V129，flusher 寫）—— **僅觀測**：comparator
    counter（total / matches / divergences / snapshot freshness / flag_enabled）在 message
    報數值供 operator triage，**不再是 FAIL 條件**。讀取失敗 / 缺表 / stale 一律降級為
    觀測欄缺值（不致 FAIL）。

硬邊界（fail-closed — G-1，僅對 P-LIVE 適用）：
  - **P-LIVE 任一不滿足 → FAIL（exit 1）非 WARN**：lease_transitions 表缺（V054 未 apply）
    / 窗內 0 row / 最新 row stale（age >= threshold）。Rust 權威路徑死 → soak 不健康，
    必 fail-closed（不可當綠燈）。
  - freshness threshold 容忍低交易期短暫安靜（預設 3600s，O-3 ops param，operator 可調），
    但「表缺 / 0 row / 長期 stale」= 引擎或 Rust 權威路徑死 → FAIL。
  - comparator 觀測欄**不 fail-closed**：它已非 gate（Option 2 下語意不可達），讀不到只是
    觀測缺值；把它當 gate 正是原 fake-pass 根因，rework 已移除。
  - 純觀測 sentinel；不碰 live 決策 / 訂單 / 任一 5 live-auth gate。step-(iv) cleanup
    連同 comparator 退役後本 check 可移除。
"""
from __future__ import annotations

from typing import Any

# ── soak gate 閾值（per PA §5 R5 + operator O-3：freshness threshold operator 可調）──

# P-LIVE：lease_transitions 新鮮度上限（秒）。Rust 權威路徑 steady-state 應持續 emit；
# 此處取 3600s（1h）——soak 期間 lease emit 率受市場活躍度影響，低交易期可能 row 少，
# 1h 容忍短暫安靜；但 1h 內無任何 Rust lease transition 視為權威路徑可能 silent-dead
# （P-LIVE FAIL）。**operator 可依市場活躍度調整此預設（O-3 ops param）。**
LIVE_TRANSITION_FRESHNESS_MAX_SECONDS: int = 3600


def check_81_lease_ipc_soak(cur: Any) -> tuple[str, str]:
    """[81] lease_ipc_soak — SM Option 2 step-(i) soak gate（P-LIVE only；comparator 觀測）。

    **rework (b)+(b-i)**：gate 唯一條件 = P-LIVE（lease_transitions Rust 權威路徑健康）。
    comparator counter 降為觀測欄（在 msg 報數值，不再 FAIL）。

    Verdict（G-1 fail-closed，僅對 P-LIVE；任一不滿足即 FAIL，無 WARN 軟化）：
      * P-LIVE：lease_transitions 表缺（V054 未 apply）→ FAIL（Rust 權威路徑不可確認）。
      * P-LIVE：窗內 0 row → FAIL（Rust 權威路徑未 emit 任何 lease transition）。
      * P-LIVE：最新 row stale（age >= LIVE_TRANSITION_FRESHNESS_MAX_SECONDS）→ FAIL
        （Rust 權威路徑可能 silent-dead）。
      * P-LIVE 全滿足 → PASS（Rust 真跑且 fresh）。msg 附 comparator 觀測欄供 triage。

    comparator 觀測欄（**非 gate**，best-effort 讀 V129 snapshot；讀不到報缺值不致 FAIL）：
      total / matches / divergences / snapshot_age / flag_enabled —— 供 operator 觀測
      comparator 在 organic 控制面流量下是否偵測到分歧；Option 2 steady-state 多半為
      organic≈0（counter 不累積），這是預期，非 soak 失敗。

    Returns:
        ``(status, msg)``。msg 含 P-LIVE lease_transitions count/age（gate）+ comparator
        觀測欄（observed:...）；FAIL 標明 P-LIVE 哪個條件未過。
    """
    # 防禦性 rollback（鏡 checks_governance 既有 pattern）。
    try:
        cur.connection.rollback()
    except Exception:  # noqa: BLE001 — 防禦性，rollback 失敗非致命
        pass

    # ── P-LIVE 信號（gate 唯一條件）：lease_transitions Rust 權威路徑真跑（read-only）──
    try:
        cur.execute("SELECT to_regclass('learning.lease_transitions') IS NOT NULL")
        lt_exists = cur.fetchone()
    except Exception as exc:  # noqa: BLE001
        return ("FAIL", f"[81] lease_transitions existence check failed: {exc}")
    if not lt_exists or not lt_exists[0]:
        return (
            "FAIL",
            "[81] P-LIVE FAIL: learning.lease_transitions missing (V054 not applied) — "
            "cannot confirm Rust authoritative path is running",
        )

    # 最新 lease_transition 的 freshness（ts_ms 是 facade emit epoch ms）。空表 / stale
    # → FAIL（Rust 權威路徑未跑 / silent-dead；P-LIVE 是 soak gate 唯一信號）。
    try:
        cur.execute(
            "SELECT COUNT(*), "
            "       (EXTRACT(EPOCH FROM now()) * 1000)::BIGINT - COALESCE(MAX(ts_ms), 0) "
            "FROM learning.lease_transitions"
        )
        lt_row = cur.fetchone()
    except Exception as exc:  # noqa: BLE001
        return ("FAIL", f"[81] lease_transitions freshness query failed: {exc}")

    lt_count = int(lt_row[0] or 0) if lt_row else 0
    lt_age_ms = int(lt_row[1] or 0) if lt_row else 0
    if lt_count == 0:
        return (
            "FAIL",
            "[81] P-LIVE FAIL: 0 lease_transitions rows — Rust authoritative path "
            "has emitted no lease transition (path not running)",
        )
    lt_age_s = lt_age_ms // 1000
    if lt_age_s >= LIVE_TRANSITION_FRESHNESS_MAX_SECONDS:
        return (
            "FAIL",
            f"[81] P-LIVE FAIL: newest lease_transition age={lt_age_s}s "
            f">= {LIVE_TRANSITION_FRESHNESS_MAX_SECONDS}s — Rust authoritative path "
            f"may be silent-dead",
        )

    # ── comparator 觀測欄（非 gate）：best-effort 讀 V129 snapshot 報數值供 triage ──
    # rework (b)+(b-i)：comparator 已降為觀測性信號（Option 2 下語意不可達，不作 gate）。
    # 讀取失敗 / 缺表 / 缺 row / stale 一律降級為觀測欄缺值（report-only），**不致 FAIL**。
    observed = _read_comparator_observed(cur)

    # ── P-LIVE 通過 → PASS（gate 滿足）；msg 附 comparator 觀測欄 ──
    return (
        "PASS",
        f"[81] soak healthy (P-LIVE gate): lease_transitions count={lt_count} "
        f"newest_age={lt_age_s}s; observed[comparator non-gate]: {observed}",
    )


def _read_comparator_observed(cur: Any) -> str:
    """best-effort 讀 V129 snapshot comparator counter，回 observability 字串（**非 gate**）。

    為什麼 best-effort 而非 fail-closed：rework (b)+(b-i) 後 comparator 是觀測性信號，
    非 cutover gate 條件。Option 2 steady-state comparator organic≈0（sampler 語意不可達，
    見 module docstring），counter 不累積是預期，不該致 soak FAIL。任何讀取失敗（V129
    缺 / row 缺 / stale / 查詢例外）→ 回缺值描述字串，caller 照常 PASS（gate 由 P-LIVE 定）。

    回字串範例：
      ``total=12 matches=12 divergences=0 snapshot_age=8s flag=ON``
      ``unavailable: V129 snapshot table absent``
      ``unavailable: no snapshot row (flusher not yet written)``
    """
    # 防禦性 rollback（前一 P-LIVE query 後重置 tx 狀態，避免污染本觀測查詢）。
    try:
        cur.connection.rollback()
    except Exception:  # noqa: BLE001 — 防禦性
        pass

    try:
        cur.execute(
            "SELECT to_regclass('learning.lease_ipc_divergence_snapshot') IS NOT NULL"
        )
        exists_row = cur.fetchone()
    except Exception as exc:  # noqa: BLE001 — 觀測讀取失敗不致 FAIL
        return f"unavailable: snapshot existence check error ({exc})"
    if not exists_row or not exists_row[0]:
        return "unavailable: V129 snapshot table absent"

    try:
        cur.execute(
            "SELECT total, matches, divergences, flag_enabled, "
            "       EXTRACT(EPOCH FROM (now() - updated_at))::BIGINT AS age_s "
            "FROM learning.lease_ipc_divergence_snapshot "
            "WHERE snapshot_key = 'singleton'"
        )
        snap = cur.fetchone()
    except Exception as exc:  # noqa: BLE001 — 觀測讀取失敗不致 FAIL
        return f"unavailable: snapshot row query error ({exc})"

    if snap is None:
        return "unavailable: no snapshot row (flusher not yet written)"

    total = int(snap[0] or 0)
    matches = int(snap[1] or 0)
    divergences = int(snap[2] or 0)
    flag_enabled = bool(snap[3])
    snap_age_s = int(snap[4] or 0)
    flag_str = "ON" if flag_enabled else "OFF"
    return (
        f"total={total} matches={matches} divergences={divergences} "
        f"snapshot_age={snap_age_s}s flag={flag_str}"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# `[82]` lease_ipc_soak_window — P5-SM soak 第二輪（E1-D，2026-06-10）
# ═══════════════════════════════════════════════════════════════════════════════

# ── S3/S4 gate 閾值（PA 設計 §4 + PM cadence 定案 2026-06-10）──

# S3：連續有效窗下限（小時）。48h 覆蓋兩輪 daily cron + 跨 epoch，是 step-iii
# 單向 cutover 的證據底線（生存 > 速度，PM 拍板不縮）。
SOAK_WINDOW_MIN_HOURS: float = 48.0

# S3：跨 epoch 累計 canary probe 下限。120s cadence 下 48h ≈ 1440 拍，500 floor
# trivially-met（PM：binding 條件是 48h + 99% + 連段 + S4，本 floor 保留作底線）。
SOAK_MIN_PROBES: int = 500

# S3：結構成功率下限（cum_ok / cum_attempts）。
SOAK_MIN_SUCCESS_RATE: float = 0.99

# S4：epoch 間隙上限（秒）。30min 足夠 rebuild（~42s）+ restart 數次；超過 =
# 觀測黑洞 → 窗中斷、錨點重置（fail-closed）。
SOAK_EPOCH_GAP_MAX_SECONDS: int = 1800

# soak-active 推定的事件回看窗（小時）：近 72h 有任何 soak 事件即視為 active
# （即使 flag 已被誤關——這正是要抓的 soak invalid 情形）。
SOAK_ACTIVE_EVENT_LOOKBACK_HOURS: int = 72

# 事件掃描窗（天）：窗計算的最大回看（soak 兩週量級；14d 外不主張連續性）。
SOAK_EVENT_SCAN_DAYS: int = 14

# flusher 死判定：V129 'canary' row updated_at 距今超過此秒數 = flusher 停擺
# （flusher 30s cadence，1800s = 60 個週期靜默，與 epoch 間隙容忍一致）。
SOAK_CANARY_SNAPSHOT_STALE_SECONDS: int = 1800

# canary 停擺判定：窗內累計 attempts 必須 ≥ (窗秒數 / 退頻上限 300s) × 0.5。
# 用退頻 cadence（最慢合法拍距）+ 50% 安全係數做超保守下限——低於它代表 canary
# 在窗內大段時間根本沒在拍（probe 數不增長），非單純失敗率問題。
SOAK_CANARY_STALL_FLOOR_INTERVAL_SECONDS: int = 300
SOAK_CANARY_STALL_SAFETY_FACTOR: float = 0.5

# 窗太短時跳過停擺判定（秒）：窗 <30min 時期望拍數 <3，整數噪音會誤殺剛啟動
# 的 soak（此時窗條件本來就 FAIL，停擺軸不需要搶答）。
SOAK_STALL_CHECK_MIN_WINDOW_SECONDS: int = 1800

# ── canary 連續性 heartbeat 斷言（E2 HIGH-2 修復，2026-06-10）──
# flusher 端每 1800s（governance_divergence_flush._HEARTBEAT_INTERVAL_S，與 30min
# epoch 間隙容忍對齊；cron-side 不 import API app 模組，兩端鏡像常數 + 注釋互指）
# 寫一條 canary_heartbeat 事件攜 attempts 快照。本組常數定義 `[82]` 對它的斷言。

# 窗達此長度即要求至少一條 heartbeat（秒）。算術 = 2× heartbeat 週期：錨點重置後
# 下一條 heartbeat 最遲 1800s 到 + 一輪 insert 失敗重試裕度；窗更短時 heartbeat
# 可能合法尚未出現（不誤殺剛重置的窗）。
SOAK_HEARTBEAT_REQUIRED_MIN_WINDOW_SECONDS: int = 3600

# 最近一條 heartbeat 距今上限（秒）。算術 = heartbeat 週期 1800s + 最大可容忍
# epoch 間隙 1800s（restart 期間 flusher 不在跑）。超過 = heartbeat 證據鏈本身
# 中途停擺（事件寫入路徑死），之後的 canary 死亡將再度不可見 → fail-closed FAIL。
SOAK_HEARTBEAT_STALE_MAX_SECONDS: int = 3600

# heartbeat → 當前 V129 快照的增長寬限（秒）。算術 = 2× 退頻 cadence 上限
# （SOAK_CANARY_STALL_FLOOR_INTERVAL_SECONDS=300）：600s 內必有 ≥1 拍；最後一條
# heartbeat 距今超過此值才斷言當前 attempts 嚴格大於該 heartbeat 快照（低於寬限
# 不斷言，避免「heartbeat 剛寫完就跑 check」的合法零增長被誤殺）。
SOAK_HEARTBEAT_SNAPSHOT_GROWTH_GRACE_SECONDS: int = 600


def _parse_event_detail(raw: Any) -> dict:
    """事件 detail 欄容錯解析：psycopg2 jsonb 自動回 dict；mock/text 回 str。"""
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw:
        try:
            import json  # noqa: PLC0415

            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:  # noqa: BLE001 — detail 畸形不致命（fail-closed 由 caller 軸處理）
            return {}
    return {}


def _heartbeat_continuity_failure(
    in_window: list,
    canary_attempts_now: int,
    last_rollover_ts: int,
    now_epoch: int,
    window_seconds: int,
) -> str | None:
    """canary 連續性 heartbeat 斷言（E2 HIGH-2 修復）；違反回 FAIL 訊息，滿足回 None。

    為什麼需要本支路：累計停擺下限（步驟 10）在 canary 攢夠 floor 後死亡時不咬
    （E2 Probe D：17h 攢 510 拍後 31h 全黑——flusher 照常保 V129 fresh、停擺不產生
    失敗、窗照走 → 全軸不咬假 PASS）。flusher 每 30min 寫一條 canary_heartbeat
    （攜 attempts 快照），本函數對它斷言四件事（任一不滿足 = canary 在窗內某段
    死亡/停擺，或連續性證據不可證 → fail-closed FAIL）：
      (i)   窗 ≥1h 必須有 heartbeat（證據鏈存在；缺 = 事件路徑死或部署不含本機制）。
      (ii)  最近一條 heartbeat 距今 ≤1h（證據鏈沒有中途停擺——否則停擺後的 canary
            死亡又會不可見，HIGH-2 換個位置復發）。
      (iii) 同 epoch 相鄰 heartbeat 之間 attempts 嚴格增長（30min ≥6 拍裕度；
            epoch_rollover 重置比較基線——計數器跨 restart 歸零是合法回落）。
      (iv)  最後一條 heartbeat（屬本 epoch、距今超過 600s 寬限）→ 當前 V129
            attempts 嚴格增長（抓「最後一條 heartbeat 之後才死」的尾段）。
    """
    hb_events = [ev for ev in in_window if ev["type"] == "canary_heartbeat"]
    if not hb_events:
        if window_seconds >= SOAK_HEARTBEAT_REQUIRED_MIN_WINDOW_SECONDS:
            return (
                f"[82] canary continuity unprovable: 0 canary_heartbeat events in "
                f"window={window_seconds / 3600.0:.1f}h（≥"
                f"{SOAK_HEARTBEAT_REQUIRED_MIN_WINDOW_SECONDS}s 即應有）— heartbeat "
                f"證據鏈缺失，canary 中段死亡將不可見"
            )
        return None  # 窗太短，heartbeat 合法尚未出現（其他軸照常把關）

    # (ii) 新鮮度：in_window 為 ASC，尾元素即最新一條。
    newest = hb_events[-1]
    newest_age = now_epoch - newest["ts"]
    if newest_age > SOAK_HEARTBEAT_STALE_MAX_SECONDS:
        return (
            f"[82] canary continuity broken: newest canary_heartbeat age={newest_age}s "
            f"> {SOAK_HEARTBEAT_STALE_MAX_SECONDS}s — heartbeat 證據鏈中途停擺，"
            f"之後的 canary 死亡不可見（fail-closed）"
        )

    # (iii) 同 epoch 相鄰 heartbeat 嚴格增長（epoch_rollover 重置基線）。
    baseline: int | None = None
    for ev in in_window:
        if ev["type"] == "epoch_rollover":
            baseline = None  # 跨 epoch 計數器歸零，合法回落，不比較
            continue
        if ev["type"] != "canary_heartbeat":
            continue
        hb_attempts = ev["canary_attempts"]
        if hb_attempts is None:
            return (
                f"[82] canary continuity unprovable: canary_heartbeat at "
                f"epoch_s={ev['ts']} carries no attempts snapshot — 增長不可證"
                f"（fail-closed）"
            )
        if baseline is not None and int(hb_attempts) <= int(baseline):
            return (
                f"[82] canary dead/stalled mid-window: attempts did not grow between "
                f"adjacent heartbeats（{baseline} -> {hb_attempts} at "
                f"epoch_s={ev['ts']}）— probe 在窗內某段未累積"
            )
        baseline = int(hb_attempts)

    # (iv) 最後一條 heartbeat → 當前快照（僅當 heartbeat 屬本 epoch 且超過寬限）。
    if (
        newest["ts"] > last_rollover_ts
        and newest["canary_attempts"] is not None
        and newest_age >= SOAK_HEARTBEAT_SNAPSHOT_GROWTH_GRACE_SECONDS
        and canary_attempts_now <= int(newest["canary_attempts"])
    ):
        return (
            f"[82] canary dead/stalled at window tail: current attempts="
            f"{canary_attempts_now} <= last heartbeat snapshot="
            f"{newest['canary_attempts']}（{newest_age}s 前，寬限 "
            f"{SOAK_HEARTBEAT_SNAPSHOT_GROWTH_GRACE_SECONDS}s 已過）— probe 未再累積"
        )
    return None


def check_82_lease_ipc_soak_window(cur: Any) -> tuple[str, str]:
    """[82] lease_ipc_soak_window — S3/S4 soak 連續有效窗評估（fail-closed）。

    讀 V129 兩 row（'singleton' + 'canary'）+ V137 soak 事件帳本，重建「連續有效
    soak 窗」並按 PA §4 S3/S4 判 PASS/FAIL：

      - **soak-active 推定**：V129 任一 row flag_enabled=true，OR 近 72h 有 soak
        事件。非 active → PASS-skip（"soak not active"，不污染非 soak 期 cron）。
      - **錨點（anchor）**：窗起點 = 下列最晚者——14d 掃描窗下限 / 帳本首事件
        （無法主張更早連續性）/ 任何 flag-OFF 觀測 / OFF→ON 轉變（同 epoch
        flag_change 或跨 restart rollover 的 prev_flag_enabled=false）/ epoch 間隙
        >30min 或間隙不可知的 rollover（fail-closed 重置）。
      - **S4 FAIL 軸**：flag 當前 OFF / counter_regression 事件在窗內 /
        「當前 canary total < 窗內事件快照 max」的無狀態倒退交叉偵測。
      - **S3 FAIL 軸**：窗 <48h / 累計 probe <500 / 成功率 <99% / 窗內有
        canary_fail_streak（≥15min 連段）事件。
      - **基建死 FAIL 軸**：active 但 V137 缺 / canary row 缺 / canary snapshot
        stale（flusher 死）/ 累計 attempts 低於停擺下限（canary 死，粗粒度）/
        heartbeat 連續性違反（canary 中段死亡/停擺或證據鏈斷，細粒度，E2 HIGH-2）/
        帳本空。

    計數歸屬誠實聲明：counter 是 epoch 粒度——錨點若切在 epoch 中段，該 epoch 的
    全量計數仍計入（對成功率是保守方向：舊失敗仍拉低比率；對 probe floor 是輕微
    寬鬆方向，但 binding 條件是 48h 窗 + 99% 率，500 floor 在 120s cadence 下
    trivially-met，PM 定案已明示）。跨 epoch 求和對 epoch_rollover 以底層 V129
    快照識別去重（E2 HIGH-1：crash-loop 的重複 rollover 攜同一未刷新終值，只計
    一次，防成功率稀釋假綠）。

    Returns:
        ``(status, msg)``；FAIL 標明第一個未過的條件 + 數字；PASS 附全量數字。
    """
    # 防禦性 rollback（鏡 check_81 pattern）。
    try:
        cur.connection.rollback()
    except Exception:  # noqa: BLE001 — 防禦性，rollback 失敗非致命
        pass

    # ── 1. V129 存在性：缺 = 觀測棧未部署 → soak 不可能 active → PASS-skip ──
    try:
        cur.execute("SELECT to_regclass('learning.lease_ipc_divergence_snapshot') IS NOT NULL")
        v129_row = cur.fetchone()
    except Exception as exc:  # noqa: BLE001
        return ("FAIL", f"[82] V129 existence check failed: {exc}")
    if not v129_row or not v129_row[0]:
        return ("PASS", "[82] soak not active (V129 snapshot table absent) — skip")

    # ── 2. V129 兩 row（flag + canary 計數 + freshness）──
    try:
        cur.execute(
            "SELECT snapshot_key, total, matches, divergences, flag_enabled, "
            "       EXTRACT(EPOCH FROM (now() - updated_at))::BIGINT AS age_s "
            "FROM learning.lease_ipc_divergence_snapshot "
            "WHERE snapshot_key IN ('singleton', 'canary')"
        )
        snap_rows = cur.fetchall() or []
    except Exception as exc:  # noqa: BLE001
        return ("FAIL", f"[82] V129 snapshot query failed: {exc}")
    snaps: dict[str, tuple[int, int, int, bool, int]] = {}
    for r in snap_rows:
        snaps[str(r[0])] = (
            int(r[1] or 0), int(r[2] or 0), int(r[3] or 0), bool(r[4]), int(r[5] or 0),
        )
    flag_now = any(s[3] for s in snaps.values())

    # ── 3. V137 存在性 + 近 72h 事件數（active 推定第二軸）──
    try:
        cur.execute("SELECT to_regclass('learning.lease_ipc_soak_events') IS NOT NULL")
        v137_row = cur.fetchone()
        v137_exists = bool(v137_row and v137_row[0])
    except Exception as exc:  # noqa: BLE001
        return ("FAIL", f"[82] V137 existence check failed: {exc}")

    recent_events = 0
    if v137_exists:
        try:
            cur.execute(
                "SELECT COUNT(*) FROM learning.lease_ipc_soak_events "
                f"WHERE created_at > now() - interval '{SOAK_ACTIVE_EVENT_LOOKBACK_HOURS} hours'"
            )
            cnt_row = cur.fetchone()
            recent_events = int(cnt_row[0] or 0) if cnt_row else 0
        except Exception as exc:  # noqa: BLE001
            return ("FAIL", f"[82] soak_events recent-count query failed: {exc}")

    # ── 4. soak-active 推定；非 active → PASS-skip ──
    active = flag_now or recent_events > 0
    if not active:
        return (
            "PASS",
            "[82] soak not active (flag OFF on all snapshots; no soak events in "
            f"last {SOAK_ACTIVE_EVENT_LOOKBACK_HOURS}h) — skip",
        )

    # ── 5. active 下的基建完整性（fail-closed）──
    if not v137_exists:
        return (
            "FAIL",
            "[82] soak active but learning.lease_ipc_soak_events missing "
            "(V137 not applied) — continuity ledger unavailable, window 不可重建",
        )
    if not flag_now:
        # active 由近 72h 事件推定但 flag 當前 OFF = soak 被中斷（S4 invalid）。
        return (
            "FAIL",
            "[82] soak invalid: flag currently OFF while soak events exist in "
            f"last {SOAK_ACTIVE_EVENT_LOOKBACK_HOURS}h — anchor reset "
            "(S4: 0 flag-OFF 觀測未滿足)",
        )
    canary_snap = snaps.get("canary")
    if canary_snap is None:
        return (
            "FAIL",
            "[82] soak active but no 'canary' snapshot row in V129 — canary/flusher "
            "投影未運行（檢查 OPENCLAW_SM_IPC_CANARY_ENABLED 與 flusher leader）",
        )
    if canary_snap[4] >= SOAK_CANARY_SNAPSHOT_STALE_SECONDS:
        return (
            "FAIL",
            f"[82] flusher dead: 'canary' snapshot age={canary_snap[4]}s >= "
            f"{SOAK_CANARY_SNAPSHOT_STALE_SECONDS}s — V129 投影停擺，窗證據凍結",
        )

    # ── 6. now epoch + 事件掃描（14d，ASC）──
    try:
        cur.execute("SELECT EXTRACT(EPOCH FROM now())::BIGINT")
        now_row = cur.fetchone()
        now_epoch = int(now_row[0]) if now_row else 0
    except Exception as exc:  # noqa: BLE001
        return ("FAIL", f"[82] now() query failed: {exc}")
    try:
        cur.execute(
            "SELECT event_type, flag_enabled, prev_canary_attempts, prev_canary_ok, "
            "       detail, EXTRACT(EPOCH FROM created_at)::BIGINT "
            "FROM learning.lease_ipc_soak_events "
            f"WHERE created_at > now() - interval '{SOAK_EVENT_SCAN_DAYS} days' "
            "ORDER BY created_at ASC, id ASC"
        )
        event_rows = cur.fetchall() or []
    except Exception as exc:  # noqa: BLE001
        return ("FAIL", f"[82] soak_events scan query failed: {exc}")

    if not event_rows:
        # active + flag ON 但帳本全空 = flusher 從未寫事件（連 flusher_start 都缺）。
        return (
            "FAIL",
            "[82] soak active but 0 soak events in scan window — flusher 事件鏈"
            "未運行（V137 剛 apply 或 flusher 死），連續性不可證",
        )

    # ── 7. 錨點計算（第一遍掃描；fail-closed：不可證連續即重置）──
    events = []
    for r in event_rows:
        events.append({
            "type": str(r[0]),
            "flag": bool(r[1]),
            "canary_attempts": (int(r[2]) if r[2] is not None else None),
            "canary_ok": (int(r[3]) if r[3] is not None else None),
            "detail": _parse_event_detail(r[4]),
            "ts": int(r[5] or 0),
        })

    scan_floor = now_epoch - SOAK_EVENT_SCAN_DAYS * 86400
    anchor = max(scan_floor, events[0]["ts"])  # 帳本首事件前不主張連續性
    anchor_reason = "ledger start"
    for ev in events:
        if not ev["flag"]:
            # flag-OFF 觀測：窗不可早於此（S4 軸——之後的窗內必然 0 OFF）。
            if ev["ts"] >= anchor:
                anchor, anchor_reason = ev["ts"], "flag-OFF observation"
            continue
        if ev["type"] == "flag_change" and ev["detail"].get("from") is False:
            # 同 epoch OFF→ON 轉變 = soak 起點。
            if ev["ts"] >= anchor:
                anchor, anchor_reason = ev["ts"], "flag OFF->ON transition"
        elif ev["type"] == "epoch_rollover":
            detail = ev["detail"]
            if detail.get("prev_flag_enabled") is False:
                # 跨 restart OFF→ON：前一 epoch flag OFF → 窗從本 rollover 起算。
                if ev["ts"] >= anchor:
                    anchor, anchor_reason = ev["ts"], "cross-restart flag OFF->ON"
                continue
            prev_ts_candidates = [
                detail.get("prev_singleton_updated_at_epoch_s"),
                detail.get("prev_canary_updated_at_epoch_s"),
            ]
            prev_ts_vals = [int(v) for v in prev_ts_candidates if v is not None]
            if not prev_ts_vals:
                # 間隙不可知 → fail-closed 重置（不可證連續）。
                if ev["ts"] >= anchor:
                    anchor, anchor_reason = ev["ts"], "rollover with unknown gap"
                continue
            gap = ev["ts"] - max(prev_ts_vals)
            if gap > SOAK_EPOCH_GAP_MAX_SECONDS:
                if ev["ts"] >= anchor:
                    anchor, anchor_reason = (
                        ev["ts"], f"epoch gap {gap}s > {SOAK_EPOCH_GAP_MAX_SECONDS}s",
                    )

    window_seconds = max(0, now_epoch - anchor)
    window_hours = window_seconds / 3600.0

    # ── 8. 窗內事件 FAIL 軸（第二遍：嚴格在錨點之後）──
    # 邊界歸屬語義（E2 LOW-2，裁決=文檔化不改碼）：嚴格 `>` 讓「與錨點同 epoch 秒」
    # 的事件歸屬前一（已作廢）窗。同批 INSERT 共享 PG now()（單 transaction）時，
    # anchor-reset 事件與 FAIL-worthy 事件同秒落帳 → 後者被排除；但 prod 觸發需
    # in-process flag 翻轉（env 進程內不可變）基本不可達，且 anchor reset 本身已
    # fail-closed 作廢舊窗——被排除事件歸屬舊窗、少算窗證據，皆為保守方向。
    in_window = [ev for ev in events if ev["ts"] > anchor]
    for ev in in_window:
        if ev["type"] == "counter_regression":
            return (
                "FAIL",
                f"[82] S4 FAIL: counter_regression event at epoch_s={ev['ts']} inside "
                f"window (anchor={anchor}) — 記帳完整性破洞，soak invalid",
            )
    for ev in in_window:
        if ev["type"] == "canary_fail_streak":
            return (
                "FAIL",
                f"[82] S3 FAIL: canary_fail_streak (>=15min) event at epoch_s={ev['ts']} "
                f"inside window — 失敗連段違反 S3，soak 窗無效",
            )

    # ── 9. 跨 epoch 累計 + 無狀態倒退交叉偵測 ──
    cum_attempts = canary_snap[0]
    cum_ok = canary_snap[1]
    last_rollover_ts = anchor
    # E2 HIGH-1 修復：crash-loop（epoch 存活 <30s，死於首次 flush 前）讓連續多個
    # epoch_rollover 重讀同一份**未刷新**的 V129 快照 → 攜帶完全相同的 prev 終值。
    # 不去重會把同一底層快照疊加 k 次，稀釋失敗率成假綠（E2 Probe A：30 個 dup
    # rollover 把 94.8% 真實帳稀釋成 99.21% PASS），probe floor 同被虛增。
    # 去重 key = (detail.prev_canary_updated_at_epoch_s, prev_attempts, prev_ok)：
    # updated_at 識別底層 V129 快照版本（epoch 內有 flush 必前移），prev 計數雙重
    # 保險（同秒雙 flush 的理論邊界）。同一快照只計一次；方向保守（只會少算）。
    seen_prev_snapshots: set = set()
    for ev in in_window:
        if ev["type"] == "epoch_rollover":
            # 去重不影響 epoch 邊界本身：rollover 是真實 epoch 切換，
            # last_rollover_ts 照常前移（本 epoch 的 regression 交叉偵測以它為界）。
            last_rollover_ts = max(last_rollover_ts, ev["ts"])
            prev_key = (
                ev["detail"].get("prev_canary_updated_at_epoch_s"),
                ev["canary_attempts"],
                ev["canary_ok"],
            )
            if prev_key in seen_prev_snapshots:
                continue
            seen_prev_snapshots.add(prev_key)
            cum_attempts += ev["canary_attempts"] or 0
            cum_ok += ev["canary_ok"] or 0
    # 無狀態交叉偵測：本 epoch（最後一個 rollover 之後）任何事件快照的 attempts
    # 不得高於當前 V129 canary total（倒退而無對應 epoch_rollover = 記帳破洞）。
    epoch_snapshot_max = max(
        (
            ev["canary_attempts"] for ev in in_window
            if ev["type"] != "epoch_rollover"
            and ev["ts"] > last_rollover_ts
            and ev["canary_attempts"] is not None
        ),
        default=None,
    )
    if epoch_snapshot_max is not None and canary_snap[0] < epoch_snapshot_max:
        return (
            "FAIL",
            f"[82] S4 FAIL: canary counter regression without epoch_rollover — "
            f"current total={canary_snap[0]} < in-epoch event snapshot max="
            f"{epoch_snapshot_max}（記帳完整性破洞）",
        )

    # ── 10. canary 停擺（probe 數不增長）——粗粒度累計下限 ──
    if window_seconds >= SOAK_STALL_CHECK_MIN_WINDOW_SECONDS:
        min_expected = int(
            (window_seconds / SOAK_CANARY_STALL_FLOOR_INTERVAL_SECONDS)
            * SOAK_CANARY_STALL_SAFETY_FACTOR
        )
        if cum_attempts < min_expected:
            return (
                "FAIL",
                f"[82] canary stalled: cumulative attempts={cum_attempts} < "
                f"conservative floor={min_expected}（窗 {window_hours:.1f}h，以退頻 "
                f"{SOAK_CANARY_STALL_FLOOR_INTERVAL_SECONDS}s cadence × "
                f"{SOAK_CANARY_STALL_SAFETY_FACTOR} 計）— probe 未在累積",
            )

    # ── 10b. canary 連續性 heartbeat 斷言（E2 HIGH-2：細粒度補步驟 10 的縫隙）──
    # 步驟 10 在 canary 攢夠 floor 後死亡時不咬（Probe D：17h 攢 510 拍後 31h 全黑
    # 仍 PASS）；本支路以 flusher 低頻 heartbeat（30min 攜 attempts 快照）斷言窗內
    # probe 持續增長。四子軸見 _heartbeat_continuity_failure docstring。
    hb_failure = _heartbeat_continuity_failure(
        in_window, canary_snap[0], last_rollover_ts, now_epoch, window_seconds,
    )
    if hb_failure is not None:
        return ("FAIL", hb_failure)

    # ── 11. S3 gate 數字 ──
    if window_hours < SOAK_WINDOW_MIN_HOURS:
        return (
            "FAIL",
            f"[82] S3 not yet met: window={window_hours:.1f}h < "
            f"{SOAK_WINDOW_MIN_HOURS:.0f}h (anchor reason: {anchor_reason}) — "
            f"accumulating; probes={cum_attempts}",
        )
    if cum_attempts < SOAK_MIN_PROBES:
        return (
            "FAIL",
            f"[82] S3 FAIL: cumulative probes={cum_attempts} < {SOAK_MIN_PROBES} "
            f"over window={window_hours:.1f}h",
        )
    success_rate = (cum_ok / cum_attempts) if cum_attempts > 0 else 0.0
    if success_rate < SOAK_MIN_SUCCESS_RATE:
        return (
            "FAIL",
            f"[82] S3 FAIL: structural success rate={success_rate:.4f} < "
            f"{SOAK_MIN_SUCCESS_RATE}（cum_ok={cum_ok} / cum_attempts={cum_attempts}）",
        )

    # ── 12. 全滿足 → PASS ──
    return (
        "PASS",
        f"[82] soak window healthy: window={window_hours:.1f}h (anchor: {anchor_reason}), "
        f"probes={cum_attempts}, success_rate={success_rate:.4f}, "
        f"0 flag-OFF / 0 regression / 0 fail-streak in window, "
        f"canary snapshot age={canary_snap[4]}s",
    )


__all__ = [
    "check_81_lease_ipc_soak",
    "check_82_lease_ipc_soak_window",
    "LIVE_TRANSITION_FRESHNESS_MAX_SECONDS",
    "SOAK_WINDOW_MIN_HOURS",
    "SOAK_MIN_PROBES",
    "SOAK_MIN_SUCCESS_RATE",
    "SOAK_EPOCH_GAP_MAX_SECONDS",
    "SOAK_CANARY_SNAPSHOT_STALE_SECONDS",
    "SOAK_HEARTBEAT_REQUIRED_MIN_WINDOW_SECONDS",
    "SOAK_HEARTBEAT_STALE_MAX_SECONDS",
    "SOAK_HEARTBEAT_SNAPSHOT_GROWTH_GRACE_SECONDS",
]
