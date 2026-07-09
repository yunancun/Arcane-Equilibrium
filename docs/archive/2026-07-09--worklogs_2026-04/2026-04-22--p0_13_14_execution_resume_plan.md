---
title: P0-13 + P0-14 執行計畫（resume-from-compact safe）
date: 2026-04-22
status: IN PROGRESS — operator approved Option F execution plan 2026-04-22 23:30 CEST
scope: 3 commits 同 --rebuild 部署；主 session + 2 sub-agents 並行
parent:
  - docs/worklogs/2026-04-22--p0_13_atr_scale_qc_research.md（QC 研究 + 推薦）
  - docs/worklogs/2026-04-22--p0_14_edge_estimates_miss_rca.md（P0-14 RCA）
  - docs/worklogs/2026-04-22--passive_wait_silent_fail_audit.md（原始 audit）
---

# P0-13 + P0-14 執行計畫

## 0. 接手指南（若 session compact 從此恢復）

**狀態檢查**（先跑這 3 個）：
```bash
cd /Users/ncyu/Projects/TradeBot/srv
git log --oneline -10                           # 看已 commit 多少
ssh trade-core "cd ~/BybitOpenClaw/srv && git log --oneline -3"  # 驗 Linux 同步
ls docs/worklogs/2026-04-22--p0_1*.md           # 看 worklog 狀態
```

**已完成 commits**（本計畫開工前的 baseline，prefix 已 push）：
- `7e35316` docs(QC): P0-13 Option F 推薦 + QC research worklog
- `cc8867f` docs(P0-15): 文檔更正 + P0-14 RCA worklog 歸檔
- `5c4af97` fix(healthcheck): edge_estimates.json schema 誤查修正
- `0579f41` docs(audit): P0-13 升級 ATR scale bug
- `074dcca` docs(P0 audit): 3 runtime silent fail

**本計畫目標 3 新 commits**（必同 `restart_all.sh --rebuild` 週期部署）：
- Commit #1: P0-13 Option F — atr source 切 kline-based（主 session）
- Commit #2: P0-14 Option A — Rust Gate 1 `missing_edge_fallback_bps` fallback（sub-agent）
- Commit #3: P0-14 Option B — Python JS estimator proxy cells（sub-agent）

**未完成則接力**：讀 §2-§4 找「☐」checkpoint。

---

## 1. 硬約束 / Hard constraints

1. **3 commits 必同 rebuild**：單修 P0-14 → Gate 4a mass close 災難；單修 P0-13 → Gate 1 仍擋 99% 失觀測性
2. **測試基準線**：engine lib pre-fix **1835 passed / 0 failed**；post-fix 預期 **~1850 passed / 0 failed**（P0-13 +~10 tests, P0-14 Rust +~5 tests）
3. **零 schema migration**：本計畫不動 DB schema、不動 TOML（除非 P0-14 A 需要 ExitConfig 新 default）
4. **跨平台**：Mac debug test pass 即可 commit；Linux release test 作為 deploy 前 gate
5. **部署時機**：3 commits 全 push + 測試全綠 → **operator 明確指令才 deploy**（不自動 restart_all.sh）
6. **commit 即 push**（per `project_ssh_bridge_workflow.md`）；每個 commit 後 `ssh trade-core git pull --ff-only`

---

## 2. Commit #1 · P0-13 Option F · atr source 切 kline-based

**Owner**：主 session（Mac）

### 2.1 實作範圍

#### File 1: `rust/openclaw_engine/src/tick_pipeline/on_tick/step_6_risk_checks.rs`

當前（L90-95）：
```rust
let position_rows: Vec<_> = positions_flat.iter().map(|p| {
    PositionRow {
        atr_pct: self.price_tracker.compute_atr_pct(&p.symbol),
        ...
```

改為（核心改動）：
```rust
let position_rows: Vec<_> = positions_flat.iter().map(|p| {
    let kline_atr_pct = self.kline_manager
        .get_ohlcv(&p.symbol, "1m", Some(20))
        .and_then(|o| openclaw_core::indicators::volatility::atr(
            &o.high, &o.low, &o.close, 14
        ))
        .map(|r| r.atr_percent);
    PositionRow {
        atr_pct: kline_atr_pct,   // was: self.price_tracker.compute_atr_pct(&p.symbol)
        ...
```

**必先驗**：
- `get_ohlcv` 的 API shape（`klines.rs:200-225`）— 返回 `OhlcvArrays { high: &[f32], low: &[f32], close: &[f32], ... }` 還是 owned?
- `atr()` 參數類型（`volatility.rs:75-110`）— 接受什麼 array slice?
- `self.kline_manager` 在 `TickPipeline` 是否存在？— 確認 struct field

#### File 2: `rust/openclaw_engine/src/risk_checks.rs:179-188`

當前 `compute_dynamic_stop_pct(..., atr_pct, ...)` 的 atr 來自 `PositionRow.atr_pct`（上游已改）— **可能無需改動**，自動繼承 #1 的 source change。E1 階段 trace 確認。

#### File 3: `rust/openclaw_engine/src/exit_features/builder.rs`

`build_exit_features_for_tick` 接受 `atr_pct: Option<f64>` 作參數，**語意不變**（繼續接受 percent-as-number），**只是 caller 傳進更合理尺度的值**。builder 本身無改動。

**單測更新**：builder.rs 測試（L182-346）現有 12 個使用 `atr_pct=1.0` / `1.5` 等 percent-as-number 值 — 這些繼續有效（符合 design intent）。**只需新增 1-2 個 test 確認在 kline-based ATR 尺度下行為正確**，例如 `atr_pct=0.1` (1m ATR 1%) 的 case 走 physical_micro_profit_lock_v2 end-to-end。

#### File 4: `rust/openclaw_core/src/risk/price_tracker.rs:105-135`

加 `#[deprecated]` warning：
```rust
#[deprecated(
    since = "2026-04-22",
    note = "Returns per-tick micro-volatility (scale ~0.001-0.006%), NOT \
            position-life ATR. Use `openclaw_core::indicators::volatility::atr()` \
            on `KlineManager` OHLCV for position-life ATR. This fn remains \
            suitable ONLY for fast_track spike detection (per-tick semantics \
            match)."
)]
pub fn compute_atr_pct(&self, symbol: &str) -> Option<f64> { ... }
```

**注意**：`compute_atr_pct` 仍被 `fast_track` 相關 path 可能使用（per-tick 語義合理）— 跑 `grep -rn 'compute_atr_pct' rust/` 確認。若 fast_track 確實使用，該 call site 加 `#[allow(deprecated)]` 局部抑制警告。

### 2.2 驗證步驟

☐ (1) Read `rust/openclaw_core/src/indicators/volatility.rs:75-110` 確認 `atr()` 簽名
☐ (2) Read `rust/openclaw_core/src/klines.rs:200-225` 確認 `get_ohlcv` API
☐ (3) Read `rust/openclaw_engine/src/tick_pipeline/mod.rs` 確認 `kline_manager` field 存在
☐ (4) Grep `compute_atr_pct` 全 repo 確認所有 callers
☐ (5) Write code change
☐ (6) `cd srv/rust && cargo check -p openclaw_engine` 編譯 OK
☐ (7) `cargo test -p openclaw_engine --lib` → 預期 1835 → ~1842 passed
☐ (8) commit → push → `ssh trade-core git pull --ff-only`
☐ (9) `ssh trade-core "cd ~/BybitOpenClaw/srv/rust && cargo test --release -p openclaw_engine --lib"` — 預期綠

### 2.3 Commit 訊息模板

```
fix(P0-13): ATR source kline-based (Option F) — 修 per-tick vs 持倉期尺度 bug

三 consumer atr_pct 來源從 price_tracker.compute_atr_pct
（per-tick abs return avg ~0.001-0.006%）切為 kline_manager
get_ohlcv("1m", 20) + indicators::volatility::atr(high, low,
close, 14)（持倉期 Wilder's ATR ~0.05-0.5%）。

修正：
- compute_dynamic_stop_pct: atr × 2 現在 > base_stop 可正常 dominate
- build_exit_features giveback_atr_norm: DB avg 364 → 預期 ~3
- physical_micro_profit_lock_v2 Gate 3/4a: 閾值回到設計意圖

舊 compute_atr_pct 加 #[deprecated]，保留給 fast_track 閃崩偵測
（per-tick micro-volatility 語義合理）。

必與 P0-14 A+B commits 同 restart_all.sh --rebuild 部署。

engine lib 1835 → XXXX passed / 0 failed

Files:
- rust/openclaw_engine/src/tick_pipeline/on_tick/step_6_risk_checks.rs
- rust/openclaw_core/src/risk/price_tracker.rs (deprecated)
```

---

## 3. Commit #2 · P0-14 Option A · Rust Gate 1 fallback

**Owner**：sub-agent B（並行派發）

### 3.1 實作範圍

#### File 1: `rust/openclaw_engine/src/exit_features/v2.rs`

當前 Gate 1（預期 L246-260 附近，E1 階段實 Read 確認）：
```rust
// Gate 1: edge floor
if let Some(edge) = f.est_net_bps {
    if edge <= cfg.min_net_floor_bps {
        return PhysicalDecision::Hold;
    }
} else {
    return PhysicalDecision::Hold;  // ← P0-14 要改這裡
}
```

改為：
```rust
// Gate 1: edge floor with fallback for missing edge (P0-14 Option A)
let effective_edge = f.est_net_bps
    .map(|e| e as f64)
    .unwrap_or(cfg.missing_edge_fallback_bps);
if effective_edge <= cfg.min_net_floor_bps {
    return PhysicalDecision::Hold;
}
```

#### File 2: `rust/openclaw_engine/src/exit_features/v2.rs` (or core.rs ExitConfig)

`ExitConfig` 加欄位：
```rust
pub struct ExitConfig {
    // ... existing fields ...
    
    /// P0-14 Option A: fallback bps when `est_net_bps` is None.
    /// Conservative default -10.0 means "treat missing edge as a weak
    /// negative signal, still below min_net_floor_bps=5.0 → Hold by
    /// default, preserving fail-safe". Operator may raise to allow
    /// phys_lock on sync-label positions before P0-14 Option B proxy
    /// cells populate the JSON.
    /// P0-14 Option A：est_net_bps 為 None 時的 fallback bps。預設 -10.0
    /// 保守值，仍 Hold；operator 可調高讓 sync-label 倉位在 B 方案
    /// proxy cells 生效前也能 phys_lock。
    #[serde(default = "default_missing_edge_fallback_bps")]
    pub missing_edge_fallback_bps: f64,
}

fn default_missing_edge_fallback_bps() -> f64 {
    -10.0  // conservative: still below min_net_floor_bps, preserves Hold
}
```

`ExitConfig::Default` 加此 field。`validate()` 加 check `missing_edge_fallback_bps.is_finite()`。

#### 單測

新增 2 tests：
- `test_v2_gate1_missing_edge_uses_fallback_below_floor`：`est_net_bps=None`, `fallback=-10`, `floor=5` → Hold
- `test_v2_gate1_missing_edge_fallback_above_floor_passes`：`est_net_bps=None`, `fallback=20`, `floor=5` → 進 Gate 2（如 mock peak/hold 通過則最終 Lock）

### 3.2 驗證步驟（sub-agent 做）

☐ (1) Read `rust/openclaw_engine/src/exit_features/v2.rs` 確認 Gate 1 具體行
☐ (2) Read `ExitConfig` struct 定義 + `impl Default` + `validate()`
☐ (3) 實作改動
☐ (4) `cargo test -p openclaw_engine --lib` Mac debug → 預期 +2 tests
☐ (5) 回報主 session，不 commit（主 session 統一）

### 3.3 Commit 訊息模板

```
fix(P0-14 A): ExitConfig Gate 1 missing_edge_fallback_bps

當 f.est_net_bps is None（99.1% 情況，per P0-14 RCA H3/H4）
舊 Gate 1 強制 Hold。現引入 missing_edge_fallback_bps（default
-10.0 保守）讓 operator 可 escalate sync-label positions 的
phys_lock 觸發性。

與 P0-14 Option B Python proxy cells 互補：A 是 runtime 保守
兜底，B 是 source-of-truth 填充。

engine lib XXXX → YYYY passed / 0 failed

Files:
- rust/openclaw_engine/src/exit_features/v2.rs
```

---

## 4. Commit #3 · P0-14 Option B · Python JS proxy cells

**Owner**：sub-agent C（並行派發）

### 4.1 實作範圍

#### File: Python edge estimator 模組

讀 `docs/worklogs/2026-04-22--p0_14_edge_estimates_miss_rca.md` §4.2 確認具體路徑。可能是：
- `srv/program_code/ml_training/edge_estimator_scheduler.py`
- `srv/program_code/edge_estimator/james_stein_estimator.py`
- 其他（sub-agent 需 grep `_write_json_snapshot` 或 `edge_estimates.json`）

在 JSON snapshot 寫出前插入 proxy cell 邏輯：

```python
# P0-14 Option B: synthesize proxy cells for runtime sync-label positions
# that have no training labels. Uses grand_mean_bps as a weak prior so
# Priority 6 Gate 1 can evaluate (still below min_net_floor_bps → Hold
# default; passes only if explicit edge fallback raised).
SYNC_LABEL_STRATEGIES = (
    "bybit_sync",
    "orphan_adopted",
    "orphan_frozen",
    "dust_frozen",
)

def _inject_sync_label_proxy_cells(
    cells: dict, grand_mean_bps: float, known_symbols: set[str]
) -> None:
    """Add proxy cells for sync-label owner_strategy values × all symbols
    present in the JSON. shrunk_bps = grand_mean_bps, n = 0, marked
    `_proxy_from = "grand_mean"` so downstream can identify."""
    for strat in SYNC_LABEL_STRATEGIES:
        for sym in known_symbols:
            key = f"{strat}::{sym}"
            if key not in cells:
                cells[key] = {
                    "shrunk_bps": grand_mean_bps,
                    "n": 0,
                    "_proxy_from": "grand_mean",
                }
```

呼叫點在 `_write_json_snapshot` 結尾，寫 file 之前。

#### pytest

新增 test 覆蓋：
- `test_proxy_cells_added_for_sync_strategies`
- `test_proxy_cells_use_grand_mean_bps`
- `test_proxy_cells_do_not_overwrite_existing`

### 4.2 驗證步驟（sub-agent 做）

☐ (1) Grep `_write_json_snapshot\|edge_estimates.json` 找準確 Python file
☐ (2) Read 該 file 完整 `_write_json_snapshot` fn
☐ (3) 實作改動 + pytest
☐ (4) `ssh trade-core "source \$HOME/.venv/bin/activate && cd ~/BybitOpenClaw/srv && pytest program_code/ml_training/... -q"` 驗綠
☐ (5) 回報主 session

### 4.3 Commit 訊息模板

```
fix(P0-14 B): edge_estimator sync-label proxy cells

P0-14 RCA 揭露 runtime owner_strategy 含 bybit_sync/orphan_*
/dust_frozen 十餘種但 JSON 僅 grid_trading::* + ma_crossover::*
兩種 prefix → T4 closure get_cell 99% miss → Gate 1 永遠 Hold。

_write_json_snapshot 結尾注入 proxy cells（4 sync strategies
× 已存在 symbols，shrunk_bps = grand_mean_bps, n = 0, 標
_proxy_from = "grand_mean"）。

與 P0-14 Option A Rust Gate 1 fallback 互補：B 填 source-of-
truth，A 是 runtime 保守兜底。

pytest +3 tests

Files:
- srv/program_code/ml_training/edge_estimator/...（待 sub-agent 確認）
```

---

## 5. 並行協調 / Coordination

### 5.1 Lane 分配

| Lane | Owner | Commit | 依賴 |
|---|---|---|---|
| 1 | 主 session | #1 P0-13 F | 無，先完成再 commit |
| 2 | sub-agent B | #2 P0-14 A Rust | 與 #1 同 Rust crate，需 #1 先 commit 避免 merge conflict（不同檔案但編譯單測會連動） |
| 3 | sub-agent C | #3 P0-14 B Python | 完全獨立 |

**建議執行順序**：
1. 同時派發 Lane 2 (sub-agent B) + Lane 3 (sub-agent C) — 不 commit
2. 主 session 做 Lane 1 — commit #1 + push
3. 主 session 收 Lane 2 回報 → commit #2 + push
4. 主 session 收 Lane 3 回報 → commit #3 + push
5. 最終測試：Mac debug `cargo test` + Linux release SSH + pytest
6. 回報 operator：3 commits + tests 全綠，等 deploy 指令

### 5.2 Sub-agent prompt 要點（下一節）

每個 sub-agent 必明確：
- READ 必做
- WRITE 可做（code + tests）
- **NOT**：不 commit / 不 push / 不 deploy / 不派 sub-agent
- Return shape：worklog 更新 §X 進度 + 簡短報告

---

## 6. 測試驗收 / Testing

### 6.1 Mac debug（必 pass）

```bash
cd /Users/ncyu/Projects/TradeBot/srv/rust
cargo test -p openclaw_engine --lib 2>&1 | tail -5
# 預期：1835 → ~1850 passed / 0 failed

cargo test -p openclaw_core --lib 2>&1 | tail -5
# 預期：原 baseline 不動 / 0 failed
```

### 6.2 Linux release（deploy 前 gate）

```bash
ssh trade-core "cd ~/BybitOpenClaw/srv/rust && cargo test --release -p openclaw_engine --lib" 2>&1 | tail -5
```

### 6.3 pytest（P0-14 B 驗）

```bash
ssh trade-core "cd ~/BybitOpenClaw/srv && source \$HOME/.venv/bin/activate && pytest program_code/ml_training/... -q" 2>&1 | tail -10
```

### 6.4 Smoke test（code 可 compile 載入）

```bash
ssh trade-core "cd ~/BybitOpenClaw/srv && cargo build --release -p openclaw-engine 2>&1 | tail -5"
```

---

## 7. Deploy（等 operator 指令）

**等 operator 說「deploy」才動**。不自動 restart_all.sh。

```bash
# operator approve 後執行
ssh trade-core "cd ~/BybitOpenClaw/srv && bash helper_scripts/restart_all.sh --rebuild" 2>&1 | tail -20
```

Deploy 後立即跑：
```bash
ssh trade-core "python3 helper_scripts/canary/engine_watchdog.py --data-dir /tmp/openclaw --status"
ssh trade-core "cd ~/BybitOpenClaw/srv && source \$HOME/.venv/bin/activate && pg_pass=\$(grep POSTGRES_PASSWORD settings/environment_files/basic_system_services.env | cut -d= -f2-) && OPENCLAW_DATABASE_URL=\"postgresql://redacted@127.0.0.1:5432/trading_ai\" OPENCLAW_BASE_DIR=\$HOME/BybitOpenClaw/srv python3 helper_scripts/db/passive_wait_healthcheck.py"
```

期待：healthcheck FAIL [4] → WARN 或 PASS（phys_lock 1-10 次/day 合理範圍）

---

## 8. Deploy 後 24h 監控（checklist）

☐ engine PID stable（無 crash）
☐ `learning.exit_features.atr_pct` avg 從 ~0.003 → ~0.05-0.2（1m ATR 合理）
☐ `learning.exit_features.giveback_atr_norm` avg 從 364 → ~0.3-3.0
☐ `trading.fills exit_reason LIKE 'risk_close:phys_lock_%'` 24h fire 1-10 次（非 0 非爆多）
☐ `trading.fills exit_reason LIKE 'risk_close:DYNAMIC STOP%'` 24h fire 1-5 次（原 7d 1 次，回到合理）
☐ close_fills 24h total 不爆增（mass close 警示）
☐ 所有其他策略 close（ma_reverse_cross / grid_close / bb_mean_revert）維持原節奏

若任一異常 → **revert 3 commits 一起**：
```bash
cd /Users/ncyu/Projects/TradeBot/srv
git revert --no-edit <commit3> <commit2> <commit1>
git push
ssh trade-core "cd ~/BybitOpenClaw/srv && git pull --ff-only && bash helper_scripts/restart_all.sh --rebuild"
```

---

## 9. Unsure points（E1 階段必驗）

從 QC worklog §7：

1. **Cold start KlineManager** — restart 後 ~15 min 累 1m bars 才能算 `atr(14)`。期間 `atr_pct = None`。影響程度需確認 `KlineManager::seed_bars` 是否在 engine startup bootstrap。
2. **`compute_dynamic_stop_pct` call chain** — trace 確認 `atr_pct` 入參當前來源。
3. **1m vs 5m period** — 推薦初始 1m period=14；若實測噪音大再切 5m。不是本 PR scope。
4. **`compute_atr_pct` 其他 callers** — fast_track / pipeline_helpers 是否仍使用；deprecation warning 是否需 `#[allow(deprecated)]`。
5. **`build_exit_feature_row` (close-time)** — `pipeline_helpers.rs:297` 同樣有 `atr_pct` 欄位，需同步切來源。否則 close-time row 與 live-time row 語意不一致。**E1 必檢此點**。
6. **replay spec `atr_fallback_pct=1.0`** — Python replay 若讀舊 exit_features rows 跨 fix 前後 → 需 partition time window。

---

## 10. 狀態追蹤表（每個 lane 完成勾 ☑）

### Commit #1 P0-13 Option F（主 session）
- ☐ Read `indicators::volatility::atr()` API
- ☐ Read `KlineManager::get_ohlcv()` API
- ☐ Grep `compute_atr_pct` all callers
- ☐ Trace `compute_dynamic_stop_pct` atr_pct call chain
- ☐ 實作 step_6_risk_checks.rs 切 atr source
- ☐ 實作 pipeline_helpers.rs build_exit_feature_row 切 atr source（close-time）
- ☐ 加 `#[deprecated]` to price_tracker::compute_atr_pct
- ☐ 新增 2 regression tests
- ☐ Mac `cargo test -p openclaw_engine --lib` 綠
- ☐ commit + push

### Commit #2 P0-14 Option A（sub-agent B）
- ☐ 派發 sub-agent prompt
- ☐ sub-agent 回報
- ☐ 主 session review
- ☐ commit + push

### Commit #3 P0-14 Option B（sub-agent C）
- ☐ 派發 sub-agent prompt
- ☐ sub-agent 回報
- ☐ 主 session review
- ☐ commit + push

### 最終驗收
- ☐ Mac debug cargo test 全綠
- ☐ Linux release cargo test 全綠
- ☐ pytest 綠
- ☐ 3 commits 全 push + Linux 同步
- ☐ 報告 operator 等 deploy 指令

---

**EOF — 計畫存檔完成，若 compact 從此 resume**
