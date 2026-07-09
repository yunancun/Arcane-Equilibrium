# WP-03 OU Sigma Residual Fix — Post-Deploy 24h Monitoring Gate Spec

**Date**: 2026-05-16
**Author**: PA
**Scope**: WP-03 OU sigma residual fix (commit `ef6ea79f` / v35 rebuild engine PID `69581`) 部署後 24h monitoring + auto revert flag 設計
**Status**: SPEC ONLY — awaiting PM dispatch；本 spec 0 IMPL，僅 design + acceptance contract + revert decision matrix
**Restriction**：本 spec 不改 business code、不 install cron、不 deploy、不 commit / push（PM 統一）
**Ticket**: `P0-2 WP-03 Deploy-gate Monitoring`
**Trigger**: Operator option (C) Deploy-gate 24h monitoring + revert flag（per WP-03 OU sigma residual estimation 修正後對 grid_trading edge 影響待驗）

---

## 1. 背景 — WP-03 改動範圍

**Commit**：`ef6ea79f` "feat(wave2): WP-03 OU sigma residual + WP-04 AI observability + WP-07 dead code audit + WP-10 Bybit retCode"
**改動檔案**：`rust/openclaw_engine/src/strategies/grid_helpers.rs` (+170 / -1 LOC，檔案總行 809 / 800 警告線)
**修法**：`compute_ou_step_with_cost_floor()` line 140 sigma 估計
- 舊公式：`sigma = sqrt(Σdx² / n)` — 把 mean-reversion drift `θ(μ - x_{t-1})` 混入白噪 innovation sigma
- 新公式：`sigma = sqrt(Σε² / (n-2))` — OLS 殘差 + n-2 自由度

**Bias 方向**：舊公式 sigma **偏高** → grid spacing `sigma × √(2/θ)` **過寬** → 每次 grid level 觸發 fill 之間 distance 過大 → grid 策略下單頻次偏低 + miss profit opportunities.
**修正後預期方向**：sigma **降** → grid spacing **收窄** → fill 頻次升 + per-trade 收益 / 信號 SNR 提升 → `avg_net_bps` for grid_trading 應升。

**修正方向的可選反向**：spacing 過窄可能造成（a）maker fill 機率變小（更接近 mid 收 quotes 但 cross-spread）/（b）adversarial fill skew 升 / （c）cost_bps 接近 net_bps 縮小 edge。任一發生 → WP-03 改動 net-negative，必啟動 revert。

**部署狀態**：v35 rebuild 2026-05-16 01:00 UTC（engine PID `69581`），含 WP-03 + WP-04 + WP-07 + WP-10 + WP-13 leftover。`grid_helpers.rs` 21/21 tests PASS（含 5 個新 WP-03 測試）。

---

## 2. Deploy-gate scope

| 屬性 | 值 |
|---|---|
| **被監測 commit** | `ef6ea79f` (WP-03 OU sigma residual fix) |
| **被監測 deploy 事件** | v35 rebuild `2026-05-16T01:00:00Z` (engine PID `69581`) |
| **被監測 strategy** | `grid_trading` (filter `strategy_name='grid_trading'`) |
| **被監測 metric** | `[40] realized_edge_acceptance.avg_net_bps_grid` — `learning.mlde_edge_training_rows.net_bps_after_fee` AVG for `strategy_name='grid_trading'` AND `engine_mode IN ('demo','live_demo')` AND `attribution_chain_ok=true` AND `net_bps_after_fee IS NOT NULL` |
| **Window** | 24h primary / 12h fast-trigger / 7d cumulative |
| **Engine mode** | demo + live_demo 合算（per ADR-0021 fresh paper `disabled=true`，無 paper edge 入 mlde 訓練表）|
| **資料源** | `learning.mlde_edge_training_rows`（[40] 既有源）— **不開新表**，直接複用 |

**Scope 排除**：
- 非 `grid_trading` strategy 不在本 gate（如 ma_crossover / bb_reversion / bb_breakout / funding_arb 各自獨立 gate 不互動）
- WP-04 / WP-07 / WP-10 改動雖共享 commit 但有獨立驗證路徑（WP-04 由 `agent.ai_invocations` 觀測 / WP-07 純 dead-code drop 無 runtime / WP-10 由 Bybit retCode 110017 enum 直接 type-safe），不在本 gate
- 非 grid_trading symbol 不在本 gate
- Demo 階段，本 gate 不 trigger live trading revert（live 無 grid_trading fills，per CLAUDE.md §三 P0-EDGE-1 active）

---

## 3. Baseline 推算

**Baseline window**：commit `ef6ea79f` (2026-05-16 01:44 UTC) 之前 14d 的 grid_trading avg_net_bps。
**Pre-WP-03 reference commit**：commit `67a82612` 或更早 — 取 `2026-05-02T01:44:00Z` ~ `2026-05-16T01:44:00Z` window 平均（避開 WP-03 IMPL window）。

**Baseline 估算 query**（PA 預估 deploy 後 E1 跑一次）：

```sql
SELECT
  COUNT(*)::int                         AS n_14d_pre_wp03,
  AVG(net_bps_after_fee)::float8        AS baseline_avg_net_bps_grid_14d,
  STDDEV(net_bps_after_fee)::float8     AS baseline_std_14d
FROM learning.mlde_edge_training_rows
WHERE ts >= '2026-05-02T01:44:00Z'
  AND ts <  '2026-05-16T01:44:00Z'
  AND engine_mode IN ('demo','live_demo')
  AND strategy_name = 'grid_trading'
  AND attribution_chain_ok = TRUE
  AND net_bps_after_fee IS NOT NULL;
```

**Baseline 來源 ground truth**：CLAUDE.md §三 W-AUDIT-7c Round 1 Sprint N+0 closure entry — `[40] avg_net -17.82 → +8.75bps` for grid/ma/bb_breakout post-V083+V084+attribution_chain_ok fix（2026-05-10 runtime impact verified）。**但**該數字是 3 策略合算，不是 `grid_trading` 單獨。本 spec 要求 E1 deploy 後跑上述 SQL 對 grid_trading 隔離出單獨 baseline。

**Baseline 預期區間**：基於 §三 +8.75bps post-V083 mixed baseline + grid 為三策略中 sample 量最大 (374 PASS per memory 2026-05-09)，PA 估 grid baseline ≈ +5 ~ +12 bps 14d；標準差 ≈ 10-20 bps（grid fills sample 量大 → std 較窄）。

**Spec lock**：Baseline 數值 **必須 E1 在 deploy_gate 第一次 cron run 內 query 出來並 cache 至 JSON**（不允許在 spec 內 hard-code），符合既有 [40] pattern + CLAUDE.md §七 §三 runtime drift defense（採集時間 + healthcheck 反向綁定）。

---

## 4. Revert Trigger 條件（explicit + actionable）

### 4.1 三層 trigger window

| Trigger # | Window | 條件 | Severity |
|---|---|---|---|
| **T1**（fast-fail）| 12h since deploy | `avg_net_bps_grid_12h < -10.0` 且 `n_12h ≥ 30` | **CRITICAL** auto revert flag |
| **T2**（primary）| 24h since deploy | `avg_net_bps_grid_24h < -5.0` 且 `n_24h ≥ 50` | **HIGH** auto revert flag |
| **T3**（cumulative drift）| 7d since deploy | `avg_net_bps_grid_7d < (baseline_avg_net_bps_grid_14d - 3.0)` 且 `n_7d ≥ 200` | **MEDIUM** auto revert flag |

### 4.2 Sample 量 floor 邏輯

- 樣本不足（n_12h < 30 / n_24h < 50 / n_7d < 200）→ 不 trigger revert，標 `INSUFFICIENT_SAMPLE` 等待累積。
- 樣本完全為 0（grid_trading 全 0 fills 24h）→ FAIL 標 `ZERO_FILLS_POSSIBLE_STRATEGY_DORMANCY`，這是另一類嚴重問題（WP-03 改動可能導致 grid 全 dormant），同樣 trigger revert flag。

### 4.3 Trigger 優先級

任一 T1/T2/T3/ZERO_FILLS 觸發 → revert flag SET。
T1 觸發 → severity CRITICAL → operator alert path 立刻通知。
T2 觸發 → severity HIGH → operator alert path。
T3 觸發 → severity MEDIUM → operator alert path（cumulative drift 較緩，但仍 alert）。

### 4.4 Threshold 來源 / 對齊既有 [40]

- [40] `EDGE_ACCEPTANCE_BAD_CELL_MAX_AVG_BPS = -10.0` (line 1129) → T1 直接複用該語意（保守 fast-fail）
- [40] `EDGE_ACCEPTANCE_MIN_AVG_NET_BPS = 5.0` (line 1127) → T2 -5.0 是「相對 baseline 收緊一檔」的對稱負界
- T3 baseline - 3 bps drift → 對應 §三 「runtime 數值 7 日鮮度上限」+ 預期改動的雙倍標準差 buffer（baseline std ~10-20 bps，3 bps 是「實質 drift」邊界）

### 4.5 Conservative bias rationale

WP-03 改動方向是「降 sigma」→「收窄 grid spacing」→ 預期 **edge 升**。若 edge **大幅降** = 修正有副作用，**保守 revert 比保守留下** safer（每 day grid loss compound）。
Trigger 設定 -5 / -10 / baseline-3 比 [40] 全局 -10 嚴格 1 級 — 因為這是 **deploy-gate 風險窗口** 不是 long-run 監控。

---

## 5. Revert Action — Two Path

### 5.1 Path A — TOML fallback flag (preferred, requires E1 IMPL)

新增 `settings/strategy_params_demo.toml` `[strategist]` section flag：

```toml
[strategist]
use_legacy_ou_sigma = false  # default：用新 OLS 殘差 sigma
                              # true：fallback 至舊 raw second moment sqrt(Σdx²/n)
```

**Rust 側 IMPL（future E1，不在本 spec scope）**：
- `compute_ou_step_with_cost_floor()` 加 `use_legacy_sigma: bool` parameter
- TOML hot-reload 經 strategy params reload pathway（已 wired）
- `if use_legacy_sigma { /* old formula */ } else { /* WP-03 new formula */ }`
- Reload 不需 engine restart（同 ArcSwap pattern as ARC-RC1）

**Why Path A**：
- 不需 git revert + 不需 engine rebuild → revert 時間 < 30s
- 保留 WP-03 改動代碼，方便後續 debug + 重新評估
- TOML flag 是 operator 顯式 action，符合 ADR-0020 manual-only revert principle

**Risk**：需要 E1 補 IMPL（estimated 4h work + E2 review + E4 regression）；deploy 前 IMPL 必 land 否則 Path A 不可用 → 退至 Path B。

### 5.2 Path B — Git revert (fallback, no IMPL needed)

```bash
# 操作 (operator manual only)
cd /home/ncyu/BybitOpenClaw/srv
git revert ef6ea79f --no-commit
# 解 conflict（WP-03/04/07/10 同 commit；revert 必選擇性還 grid_helpers.rs L140 區域）
git checkout HEAD~1 -- rust/openclaw_engine/src/strategies/grid_helpers.rs
# 重 build engine
PATH=$HOME/.cargo/bin:$PATH bash helper_scripts/restart_all.sh --rebuild --keep-auth
```

**Why Path B**：
- Path A 未 IMPL 前 fallback；100% 工作但 cost engine downtime ~5min
- 同時還原 WP-03 5 新測試（殘差 < raw 等 5 個 assert）→ 後續若 revert + reland 需 careful 重跑

**Risk**：
- WP-03 + WP-04 + WP-07 + WP-10 共 commit，selective revert grid_helpers.rs 是 careful manual op
- engine downtime 5min 期間 grid_trading 不交易（demo + live_demo）
- 觸 §三 §四「engine rebuild → 必 watchdog 確認 + ssh trade-core verify」

### 5.3 Path 選擇 decision matrix

| 情境 | 推薦 Path | 理由 |
|---|---|---|
| Path A IMPL 已 land + tested | **A** | < 30s revert，符 ADR-0020 |
| Path A 未 IMPL，trigger 觸發 | **B** + 同 ticket P1 補 Path A IMPL | Operator 必須立刻 cleared edge loss，IMPL 補後續 |
| Trigger 邊界值（如 T2 -4.9 bps borderline）| 不 revert，加觀察 window 12h | 4.9 bps drift 可能 noise 不 root cause；waits |
| ZERO_FILLS 觸發 | **B** + emergency RCA | grid 全 dormant 影響大 → 立刻 revert + RCA 確認是 WP-03 還是其他 root cause |

---

## 6. Monitoring Healthcheck Design — `[69] check_69_wp03_ou_sigma_deploy_gate`

### 6.1 既有 [40] pattern 沿用 + 差異

| 屬性 | [40] realized_edge_acceptance | **[69] wp03_ou_sigma_deploy_gate** |
|---|---|---|
| Function | `check_realized_edge_acceptance(cur)` | `check_69_wp03_ou_sigma_deploy_gate(cur)` |
| Module | `checks_execution.py` | **新檔**：`checks_wp03_deploy_gate.py`（與 [12]/[57]/[68] 同 pattern：feature-specific 模組）|
| Window | 24h fixed | 12h + 24h + 7d **三窗合算** |
| Filter strategy | 全策略 | **`grid_trading` only** |
| Engine mode | demo + live_demo | demo + live_demo（同）|
| Output verdict | PASS / WARN / FAIL | PASS / WARN / FAIL **+ revert flag if FAIL** |
| Cron | `passive_wait_healthcheck.py --all` 既有 cycle | 同 cycle，**+ 寫 revert flag file** if any trigger met |
| Deploy proxy | 無 | `/tmp/openclaw/engine_pid` mtime（per [12] pattern）— gates pre-deploy PASS-skip |

### 6.2 Function skeleton（spec only，不 IMPL）

```python
# helper_scripts/db/passive_wait_healthcheck/checks_wp03_deploy_gate.py
# (新檔，spec only — E1 IMPL phase ticket 另開)

WP03_DEPLOY_TIMESTAMP_UTC = "2026-05-16T01:00:00Z"  # v35 rebuild
WP03_REVERT_FLAG_PATH = Path(os.environ.get("OPENCLAW_DATA_DIR", "/tmp/openclaw")) / "wp03_revert_flag"
WP03_BASELINE_CACHE_PATH = Path(os.environ.get("OPENCLAW_DATA_DIR", "/tmp/openclaw")) / "wp03_baseline_cache.json"

# Thresholds (per §4)
T1_WINDOW_HOURS = 12
T1_AVG_NET_FLOOR = -10.0
T1_MIN_SAMPLE = 30
T2_WINDOW_HOURS = 24
T2_AVG_NET_FLOOR = -5.0
T2_MIN_SAMPLE = 50
T3_WINDOW_DAYS = 7
T3_DRIFT_BPS = 3.0  # absolute drift below baseline_14d
T3_MIN_SAMPLE = 200


def check_69_wp03_ou_sigma_deploy_gate(cur) -> tuple[str, str]:
    """[69] WP-03 OU sigma residual fix post-deploy 24h+ monitoring + revert flag.

    監測 grid_trading 在 WP-03 殘差 sigma 修正部署後的 avg_net_bps 變化。
    三窗 trigger：12h fast-fail（-10bps）/ 24h primary（-5bps）/ 7d cumulative
    drift（baseline-3bps）。任一觸發即寫 revert flag + operator alert。

    Pre-deploy（engine_pid mtime ≥ WP03_DEPLOY_TIMESTAMP_UTC 未 pass）→ PASS-skip。
    Baseline 14d 推算結果 cache 到 WP03_BASELINE_CACHE_PATH，第一次跑時 compute，後續 reuse。
    """
    # Step 0: deploy proxy gate (per [12] pattern)
    pid_path = Path(os.environ.get("OPENCLAW_DATA_DIR", "/tmp/openclaw")) / "engine_pid"
    if not pid_path.exists():
        return ("PASS", "[69] engine_pid 不存在，pre-deploy or maintenance — gate skipped")
    pid_mtime_utc = datetime.fromtimestamp(pid_path.stat().st_mtime, tz=timezone.utc)
    deploy_ts = datetime.fromisoformat(WP03_DEPLOY_TIMESTAMP_UTC.replace("Z", "+00:00"))
    if pid_mtime_utc < deploy_ts:
        return ("PASS", f"[69] engine restart 在 WP-03 deploy 前（{pid_mtime_utc}），gate not active yet")
    age_h = (datetime.now(tz=timezone.utc) - max(pid_mtime_utc, deploy_ts)).total_seconds() / 3600.0
    if age_h < 1.0:
        return ("PASS", f"[69] 部署 <1h（{age_h:.2f}h），sample 累積中 — gate not yet evaluable")

    # Step 1: baseline cache load or compute
    baseline = _load_or_compute_baseline(cur)
    if baseline is None:
        return ("WARN", "[69] baseline_14d compute failed — cannot evaluate drift")

    # Step 2: 三窗 query
    t1 = _query_grid_window(cur, hours=T1_WINDOW_HOURS)
    t2 = _query_grid_window(cur, hours=T2_WINDOW_HOURS)
    t3 = _query_grid_window(cur, days=T3_WINDOW_DAYS)

    # Step 3: trigger evaluation
    triggers = []
    if t1["n"] >= T1_MIN_SAMPLE and t1["avg_net_bps"] < T1_AVG_NET_FLOOR:
        triggers.append(("T1_CRITICAL", f"12h n={t1['n']} avg={t1['avg_net_bps']:.2f}bps < {T1_AVG_NET_FLOOR}"))
    if t2["n"] >= T2_MIN_SAMPLE and t2["avg_net_bps"] < T2_AVG_NET_FLOOR:
        triggers.append(("T2_HIGH", f"24h n={t2['n']} avg={t2['avg_net_bps']:.2f}bps < {T2_AVG_NET_FLOOR}"))
    if t3["n"] >= T3_MIN_SAMPLE and t3["avg_net_bps"] < (baseline["avg_net_bps"] - T3_DRIFT_BPS):
        triggers.append(("T3_MEDIUM", f"7d n={t3['n']} avg={t3['avg_net_bps']:.2f}bps drift > {T3_DRIFT_BPS}bps below baseline {baseline['avg_net_bps']:.2f}bps"))

    # Step 4: zero-fills detection
    if age_h >= T2_WINDOW_HOURS and t2["n"] == 0:
        triggers.append(("ZERO_FILLS", "24h grid_trading n=0 — possible strategy dormancy from WP-03"))

    base_msg = (
        f"deploy_age={age_h:.1f}h, baseline_14d={baseline['avg_net_bps']:.2f}bps (n={baseline['n']}), "
        f"12h n={t1['n']} avg={t1['avg_net_bps']:.2f}bps, "
        f"24h n={t2['n']} avg={t2['avg_net_bps']:.2f}bps, "
        f"7d n={t3['n']} avg={t3['avg_net_bps']:.2f}bps"
    )

    # Step 5: verdict + revert flag
    if triggers:
        _write_revert_flag(triggers)
        return ("FAIL", f"[69] WP-03 deploy-gate FAIL — triggers: {triggers}; {base_msg}")

    # WARN: 80% threshold approach
    warnings = []
    if t1["n"] >= T1_MIN_SAMPLE and t1["avg_net_bps"] < T1_AVG_NET_FLOOR * 0.8:  # i.e. < -8 bps
        warnings.append(f"12h avg {t1['avg_net_bps']:.2f}bps approaching T1 (-10bps × 80%)")
    if t2["n"] >= T2_MIN_SAMPLE and t2["avg_net_bps"] < T2_AVG_NET_FLOOR * 0.8:  # i.e. < -4 bps
        warnings.append(f"24h avg {t2['avg_net_bps']:.2f}bps approaching T2 (-5bps × 80%)")
    if t3["n"] >= T3_MIN_SAMPLE and t3["avg_net_bps"] < (baseline["avg_net_bps"] - T3_DRIFT_BPS * 0.8):
        warnings.append(f"7d cumulative drift approaching T3 (80% of {T3_DRIFT_BPS}bps drift)")
    if warnings:
        return ("WARN", "[69] " + "; ".join(warnings) + " — " + base_msg)

    return ("PASS", f"[69] WP-03 deploy-gate within tolerance — {base_msg}")
```

### 6.3 Auxiliary helpers（E1 IMPL phase, spec only）

```python
def _query_grid_window(cur, hours: int = None, days: int = None) -> dict:
    """Query learning.mlde_edge_training_rows for grid_trading."""
    if hours:
        interval = f"interval '{hours} hours'"
    else:
        interval = f"interval '{days} days'"
    cur.execute(
        f"""
        SELECT COUNT(*)::int, AVG(net_bps_after_fee)::float8, STDDEV(net_bps_after_fee)::float8
        FROM learning.mlde_edge_training_rows
        WHERE ts > now() - {interval}
          AND engine_mode IN ('demo','live_demo')
          AND strategy_name = 'grid_trading'
          AND attribution_chain_ok = TRUE
          AND net_bps_after_fee IS NOT NULL
        """
    )
    n, avg, std = cur.fetchone()
    return {"n": int(n or 0), "avg_net_bps": float(avg or 0), "std": float(std or 0)}


def _load_or_compute_baseline(cur) -> dict | None:
    """Load WP-03 baseline 14d cache or compute & persist."""
    if WP03_BASELINE_CACHE_PATH.exists():
        return json.loads(WP03_BASELINE_CACHE_PATH.read_text())

    # 14d pre-WP-03 baseline
    cur.execute(
        """
        SELECT COUNT(*)::int, AVG(net_bps_after_fee)::float8
        FROM learning.mlde_edge_training_rows
        WHERE ts >= '2026-05-02T01:44:00Z'
          AND ts <  '2026-05-16T01:44:00Z'
          AND engine_mode IN ('demo','live_demo')
          AND strategy_name = 'grid_trading'
          AND attribution_chain_ok = TRUE
          AND net_bps_after_fee IS NOT NULL
        """
    )
    n, avg = cur.fetchone()
    if not n or n < 30:
        return None  # baseline 樣本不足，無法評估
    baseline = {
        "n": int(n), "avg_net_bps": float(avg),
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "window": "14d pre-WP-03 (2026-05-02 ~ 2026-05-16)",
    }
    WP03_BASELINE_CACHE_PATH.write_text(json.dumps(baseline))
    return baseline


def _write_revert_flag(triggers: list[tuple]) -> None:
    """Persist revert flag to OPENCLAW_DATA_DIR for operator alert path."""
    flag_data = {
        "trigger_at": datetime.now(timezone.utc).isoformat(),
        "triggers": [{"name": t[0], "detail": t[1]} for t in triggers],
        "severity": triggers[0][0],  # highest severity (T1 > T2 > T3 > ZERO)
        "wp03_commit": "ef6ea79f",
        "deploy_ts": WP03_DEPLOY_TIMESTAMP_UTC,
    }
    WP03_REVERT_FLAG_PATH.write_text(json.dumps(flag_data, indent=2))
```

### 6.4 註冊到 healthcheck runner

`helper_scripts/db/passive_wait_healthcheck/__init__.py` 新增 import：

```python
from .checks_wp03_deploy_gate import (  # noqa: F401
    # [69] WP-03 OU sigma residual fix post-deploy 24h+ monitoring + revert flag.
    # 監測 grid_trading 部署後 12h/24h/7d 三窗 avg_net_bps drift；任一 trigger 寫 revert flag。
    check_69_wp03_ou_sigma_deploy_gate,
)
```

加入 `__all__` 列表 + `runner.py` check list（per [40]/[42]/[57]/[68] pattern）。

### 6.5 取 [69] 自由 slot 理由

CLAUDE.md §三 + `__init__.py` 列出最新 check ID：
- [56] live_pipeline_active
- [57] btc_lead_lag_panel_health
- [68] portfolio_resting_exposure（per checks_portfolio_resting_exposure.py 註釋「[58] 已被 W-AUDIT-9 T4 占用 → 取 [68] 自由 slot」）

**WP-03 deploy gate 取 [69] = 下一個自由 slot**（檢查 [69] 確認未占用）。
**Name**：`wp03_ou_sigma_deploy_gate`（明確 wave + topic + 性質）。

---

## 7. Operator alert path

### 7.1 Trigger 接 alert

任一 FAIL 觸發 → `[69]` 在 cron run 內寫 `$OPENCLAW_DATA_DIR/wp03_revert_flag`。
Operator alert path：CLAUDE.md §三 + governance alert protocol 既有 pattern：
1. **被動觀察**：Operator 在 daily watchdog 看到 `[69] FAIL` line
2. **主動 ping**：CC 主 session 啟動序列 read `wp03_revert_flag` if exists → 第一條 echo 給 operator
3. **GUI 顯示**：Learning Cockpit / Demo tab 加入 banner（per `feature/agent-tracker-mvp` 既有 pattern）— 不在本 spec scope

### 7.2 ADR-0020 manual-only revert principle

**Auto revert flag SET ≠ auto revert action**。Flag 是 operator 顯式 sign + execute 才 revert（per ADR-0020）。
- Flag 寫入 `$OPENCLAW_DATA_DIR/wp03_revert_flag` 是 advisory + audit trail
- Operator 看到 flag → manual decision：(a) revert via Path A flag flip / (b) revert via Path B git revert / (c) extend observe window 12h before action / (d) dismiss flag if false positive

### 7.3 PA 推薦 operator decision matrix

| Trigger severity | Operator 建議反應時間 | 建議動作 |
|---|---|---|
| T1 CRITICAL | < 1h | Path B 立刻 revert（fast-fail 比 cost engine downtime 嚴重）|
| T2 HIGH | < 4h | Path A 若 IMPL 就緒 flip / 否 Path B；同時跑 RCA query 看是否 maker fill collapse |
| T3 MEDIUM | < 24h | Extend observe 12h；若 drift 持續或加劇 → revert；若 stable / 反彈 → dismiss |
| ZERO_FILLS | < 30min | Path B 立刻 revert + emergency RCA（symbol dormancy 是嚴重副作用）|

---

## 8. Timeline

```
2026-05-16 01:00 UTC : v35 rebuild deploy (HAPPENED)
2026-05-16 ~02:00 UTC: [69] healthcheck PASS-skip（sample <1h，pre-evaluable）
2026-05-16 ~13:00 UTC: [69] 12h window 評估 active；baseline 14d cache compute（first cron）
2026-05-17 01:00 UTC: [69] 24h primary gate 評估 active
2026-05-17 ~01:30 UTC: PM 對齊 [69] 24h result：若 PASS land + WP-03 進 long-run monitoring；若 FAIL → revert + WP-03 reopen
2026-05-23 01:00 UTC: [69] 7d cumulative gate 評估 active
2026-06-15 (T+30d) :  PM 評估 [69] 整體 effectiveness + 是否 fine-tune threshold or sunset gate
```

**Gate 何時 sunset**：
- 7d 全 PASS + 整體 grid edge ≥ baseline + 3 bps → 30d 後 sunset gate（gate 已 prove WP-03 net-positive）
- 任一 7d window FAIL → revert + WP-03 reopen，gate 保留至 reland 30d 後再評估
- 部分 PASS / 部分 WARN → 延至 60d 後 evaluate（保守保留 gate）

---

## 9. Acceptance Criteria（deploy-gate spec sign-off）

| # | Criterion | 驗證方式 |
|---|---|---|
| AC1 | Deploy-gate scope 明確（commit + strategy + metric + window）| 本 spec §2 |
| AC2 | Baseline 推算邏輯 + cache pattern | 本 spec §3 + §6.3 `_load_or_compute_baseline` |
| AC3 | Revert trigger 3 層 explicit + actionable | 本 spec §4 |
| AC4 | Revert action 雙 path（flag + git revert）+ decision matrix | 本 spec §5 |
| AC5 | [69] healthcheck 設計對齊既有 [40]/[12]/[57]/[68] pattern | 本 spec §6 |
| AC6 | Operator notification + alert path 符 ADR-0020 manual-only | 本 spec §7 |
| AC7 | Timeline 含 sample 累積 + 評估點 + sunset 條件 | 本 spec §8 |
| AC8 | Spec 不含 IMPL（純 design）+ 不 commit / push by PA | 本 spec restriction footer + PA 不動 code |

---

## 10. Out-of-scope（後續 ticket）

| Ticket（建議）| 工作 | Estimate |
|---|---|---|
| `P1-WP03-DEPLOY-GATE-IMPL` | E1 IMPL `checks_wp03_deploy_gate.py` + 註冊 runner + `wp03_revert_flag` write | ~4h E1 |
| `P1-WP03-DEPLOY-GATE-E2-E4` | E2 review + E4 regression test（mock revert flag write + 三窗 SQL 驗）| ~3h |
| `P2-WP03-PATH-A-TOML-FALLBACK` | Rust `use_legacy_ou_sigma` flag + hot-reload | ~6h E1 + 2h E2 |
| `P2-WP03-GUI-ALERT-BANNER` | Learning Cockpit revert flag banner | ~2h FE |
| `P2-WP03-PA-CC-INTEGRATION` | CC session 啟動序列 read wp03_revert_flag if exists → echo | ~1h CC config |
| `P2-WP03-LONG-RUN-MONITOR` | 30d / 60d / 90d sunset evaluation cron | ~2h |

**本 spec 不含**：E1 IMPL、TOML schema change、Rust 修改、cron install、GUI 修改、deploy 操作。

---

## 11. 16 根原則 + 9 不變量 合規

| 維度 | 評估 |
|---|---|
| 原則 1 單一寫入口 | N/A（純 monitoring，無 IntentProcessor 路徑）|
| 原則 2 讀寫分離 | ✅ healthcheck 純 SELECT，無 _authorize_write |
| 原則 3 AI 輸出 ≠ 命令 | N/A（無 AI 路徑）|
| 原則 4 策略不繞風控 | ✅ healthcheck 不下單 |
| 原則 5 生存 > 利潤 | ✅ revert flag 保守傾向（-5/-10/-3 bps trigger）保策略邊界 |
| 原則 6 失敗默認收縮 | ✅ ZERO_FILLS + 任一 trigger → 寫 flag 默認傾向 revert |
| 原則 7 學習 ≠ 改寫 Live | ✅ healthcheck 不寫 mlde 訓練表，純 SELECT |
| 原則 8 交易可解釋 | ✅ baseline cache + flag JSON 含 commit SHA + deploy_ts + 觸發明細 |
| 原則 9 災難保護 | ✅ Path A flag + Path B git revert 雙 line |
| 原則 10 認知誠實 | ✅ 三窗 evidence + WARN 80% threshold + sample floor 明寫 |
| 原則 11 Agent 最大自主 | ✅ revert flag 由 healthcheck 自主寫，operator 顯式 action |
| 原則 12 持續進化 | ✅ 30d sunset + reland 評估循環 |
| 原則 13 AI 成本感知 | N/A（純 PG SELECT 0 AI 調用）|
| 原則 14 零外部成本可運行 | ✅ healthcheck 純 PG，無外部依賴 |
| 原則 15 多 Agent 協作 | ✅ 觸發後 operator + PM + PA chain 已定義 |
| 原則 16 組合級風險 | N/A（單策略 gate，組合風險另有 [68] portfolio_resting_exposure）|

**合規評級**：**A 級（16/16 適用項，硬邊界 0 觸碰）**

### 硬邊界（CLAUDE.md §四）

| 硬邊界項 | 觸碰? |
|---|---|
| `live_execution_allowed` | ❌ 否 |
| `max_retries=0` | ❌ 否 |
| `execution_authority` | ❌ 否 |
| `decision_lease_emitted` | ❌ 否 |
| `OPENCLAW_ALLOW_MAINNET` | ❌ 否 |
| `live_reserved` | ❌ 否 |
| `authorization.json` | ❌ 否 |

### DOC-08 §12 9 條安全不變量

純 monitoring spec，不適用 lease / fills / mainnet / authorization 等執行不變量。

---

## 12. Risks / Open Questions

### R1（MEDIUM）— Baseline 14d window 含 WP-03 pre-deploy 階段，但也含 V083 attribution_chain_ok fix（2026-05-10）的 transition window

per CLAUDE.md §三 W-AUDIT-7c Round 1 entry：`[40] avg_net -17.82 → +8.75bps` post-V083+V084 fix。
2026-05-10 至 2026-05-16 是 transition window；baseline 14d 2026-05-02 ~ 2026-05-16 含 attribution_chain_ok=true rows pre-fix 階段（-17.82 bps）和 post-fix（+8.75 bps）。
**Mitigation**：E1 IMPL 時 baseline cache 取 **2026-05-11 ~ 2026-05-16**（post-V083 5 day stable window），同時 spec §3 update。
**Decision**：本 spec lock baseline window = `[2026-05-11T00:00:00Z, 2026-05-16T01:44:00Z]`，5 day stable post-V083 window，避 V083 transition contamination。

### R2（LOW）— `learning.mlde_edge_training_rows` ts 與 fills.ts 對齊問題

mlde rows ts 是 backfill 時 inserted 的 ts，不是 fill 時 ts。若 backfill 有 delay，24h window 可能 miss 真實 24h fills.
**Mitigation**：[40] 既有 query 已 cover 該假設；本 spec 沿用，per CLAUDE.md §三 attribution_chain_ok 100% 後 backfill 延遲 < 1h，可接受。
**Decision**：accept；不引入新風險。

### R3（LOW）— grid_trading 同 commit 還有 WP-13 leftover 改動（DemoCmdSenderSlot extension）

WP-13 leftover 是 `a7cb517f` commit (2026-05-16 02:53)，影響 demo reconciler / strategist scheduler / edge reload 的 `DemoCmdSenderSlot` 讀取。理論上不直接影響 grid_helpers.rs 的 OU sigma 邏輯，但可能間接影響 grid_trading 信號發送頻次。
**Mitigation**：[69] 評估若 trigger，先讀 `[55]` fill-lineage + `[12]` bb_breakout 看是否同步異常（cross-strategy infrastructure issue）；若 [55]/[12] 健康 → 確認 WP-03 sigma 改動是 root cause。
**Decision**：[69] FAIL detail 必含 cross-check hints；如 detail 包 cross-strategy infrastructure noise → operator 評估 confound。

### R4（LOW）— WP-03 5 個新測試 PASS 但 runtime 行為與測試 fixture 不一致

5 test 是 unit test on `compute_ou_step_with_cost_floor()` 純函數；runtime grid_trading 還涉及（a）KlineManager feed / （b）IndicatorEngine ATR / （c）SignalEngine grid level emission / （d）IntentProcessor write / （e）reconciler 對賬。任一中間層 noise 影響 grid edge.
**Mitigation**：本 [69] 是 end-to-end 監測 (mlde rows = post-fill backfill)；測試 5 PASS 是 unit boundary，runtime 影響是 [69] gate 本身的 monitoring 目的。
**Decision**：spec 接受 unit-runtime gap；這正是 deploy-gate 存在的理由。

---

## 13. PA Sign-off

**Spec status**：DESIGN-COMPLETE
**Verdict**：APPROVE（A 級合規，0 硬邊界觸碰，monitoring-only 路徑安全）
**Hand-off**：PM dispatch decision — 派 `P1-WP03-DEPLOY-GATE-IMPL` E1 IMPL + `P1-WP03-DEPLOY-GATE-E2-E4` 對抗審 + E4 regression。
**Sign-off path**：本 PA spec self-sign（PA DESIGN DONE）→ 主 session PM dispatch IMPL ticket → E1 → E2 → E4 → PM verify [69] cron run PASS / WARN / FAIL routing 正確。

---

PA DESIGN DONE: report path: /Users/ncyu/Projects/TradeBot/srv/docs/execution_plan/2026-05-16--wp03_ou_sigma_deploy_gate_spec.md
