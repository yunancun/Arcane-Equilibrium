---
title: P0-14 EDGE-ESTIMATES-MISS-1 — est_net_bps 99% NULL RCA
date: 2026-04-22
status: READ-ONLY RCA（不動 code / config / DB / log）
trigger: 被動等待 audit 揭露 `learning.exit_features` 7d 110 rows 中 109 row `est_net_bps IS NULL`（99.1% miss）
related:
  - `memory/project_track_p_runtime_live.md`（T4 `e95c779` / V2-SWAP `306993e`）
  - `docs/worklogs/2026-04-22--passive_wait_silent_fail_audit.md`（P0-14 母單）
  - TODO §P0-13（builder unit bug，與本項共依賴）/ §P0-14（本項）
scope: 單檔本 worklog 寫入；不改任何 `.rs` / `.py` / `.json` / DB
---

# P0-14 EDGE-ESTIMATES-MISS-1 — RCA

## 0. TL;DR

**最可能命中假設**：**H4（owner_strategy label 與 JSON key 策略維度不匹配）** 為首要，
**H3（JSON cells 覆蓋範圍不足）** 為次要，兩者疊加成因：

1. **H4 為 dominant 因**（高信心）：Rust runtime 的 `owner_strategy` 可取 `"bybit_sync"` / `"orphan_adopted"` / `"orphan_frozen"` / `"dust_frozen"` / `"ma_crossover"` / `"grid_trading"` / `"bb_breakout"` 等十餘種值；JSON（demo + live_demo 兩檔）**僅** 含 `grid_trading::*` + `ma_crossover::*` 兩種前綴（43 + 31 cells，0 bybit_sync / 0 orphan_* / 0 bb_breakout / 0 funding_arb）。
2. **H3 為附加因**（中信心）：即便倉位是 `ma_crossover` 或 `grid_trading`，仍需 (strategy, symbol) cell 存在 — JSON 目前僅 23 symbols 有 cells（`_meta.n_cells=43` 分佈 grid 22 + ma 21）；runtime universe 可大於此（pinned + scanner live）。
3. **H1 / H2 / H5 均 FAIL**（讀 code 即可確認）：key 格式一致為 `"{strategy}::{symbol}"`、load 為 flat map、Reader / Writer 對齊。

**healthcheck cells 0/0 為假陽性**：`passive_wait_healthcheck.py:187` 查 `.get("cells", [])`，但 JSON schema 是 **flat map**（no `cells` wrapper），所以永遠回 `[]` → `populated=0, total=0` → `cov=0 → WARN`。**此訊號與 est_net_bps miss 無關**，是 healthcheck code 本身的 schema 誤解。

**修復入口建議**（詳 §6）：
- 短期（data fix + fallback, 1-2d）：新增 `DUST_FROZEN_STRATEGY` / `"bybit_sync"` / `"orphan_*"` 到 JS estimator 的 strategy label 映射（或 `retriage_synthetic_owner` 之前查詢），或於 Gate 1 加 `edge=None → 走 `grand_mean_bps` fallback 但不 Lock` 分支；
- 中期（P0-13 修好後才能安全 uncover）：當前 builder unit bug 掩蓋 Gate 4a — 任何 §3.2 fix 需與 P0-13 同 rebuild 部署，否則 Gate 4a mass close winners。

---

## 1. JSON 實際結構（ssh trade-core 讀，未 dump 敏感內容）

**來源路徑**：`~/srv/settings/edge_estimates.json` · mtime `2026-04-22 21:56`（當日 scheduler 正常刷新）· 11 767 bytes · `_meta.updated_at = 2026-04-22T19:56:23.113573+00:00` · `_meta.n_cells=43` · `_meta.grand_mean_bps=-4.298`

**Top-level schema**：**flat map**（非 `{"cells": [...]}` 包裹）：

```json
{
  "_meta": { "updated_at": "...", "n_cells": 43, "grand_mean_bps": -4.298 },
  "grid_trading::1000PEPEUSDT": { "shrunk_bps": -4.2984, "raw_bps": -8.56, "n": 13, ... },
  "grid_trading::AAVEUSDT":     { "shrunk_bps": -4.2984, "raw_bps": -11.97, "n": 6, ... },
  ...
  "ma_crossover::SOLUSDT":      { "shrunk_bps": -4.2984, "raw_bps": 8.23, "n": 4, ... }
}
```

**Key 分佈**（`jq 'keys | map(split("::") | .[0]) | group_by(.)'`）：

| 策略前綴 | cell 數 |
|---|---:|
| `grid_trading` | 22 |
| `ma_crossover` | 21 |
| `bybit_sync` | **0** |
| `orphan_adopted` / `orphan_frozen` / `dust_frozen` | **0** |
| `bb_breakout` / `bb_reversion` / `funding_arb` | **0** |
| 其他 | 0 |

**唯一 symbol 數**（兩策略合併去重）：**23** symbols（1000PEPEUSDT / AAVEUSDT / ADAUSDT / BASEDUSDT / BLURUSDT / BTCUSDT / CHIPUSDT / CLUSDT / DOGEUSDT / ENAUSDT / ENJUSDT / ETHUSDT / FARTCOINUSDT / GENIUSUSDT / GUNUSDT / HIGHUSDT / HYPEUSDT / METUSDT / MNTUSDT / ORDIUSDT / PIEVERSEUSDT / RAVEUSDT / SOLUSDT）。

**live_demo 變體**：`~/srv/settings/edge_estimates_live_demo.json` 同 schema · `_meta.n_cells=31` · `_meta.grand_mean_bps=-7.737` · 同樣僅 `grid_trading::*` + `ma_crossover::*`。

---

## 2. Writer 路徑（Python → JSON）

### 2.1 主 estimator — [`srv/program_code/ml_training/james_stein_estimator.py:357`](../../program_code/ml_training/james_stein_estimator.py:357) `_write_json_snapshot()`

```python
# srv/program_code/ml_training/james_stein_estimator.py:366-397
now_iso = datetime.now(tz=timezone.utc).isoformat()
snapshot: dict = {
    "_meta": {
        "updated_at": now_iso,
        "n_cells": len(results),
        "grand_mean_bps": results[next(iter(results))]["grand_mean_bps"] if results else 0.0,
    }
}
for (strategy, symbol), r in results.items():
    key = f"{strategy}::{symbol}"           # ← key format
    snapshot[key] = { "shrunk_bps": ..., "raw_bps": ..., "n": ..., ... }
```

- **Key 格式**：`f"{strategy}::{symbol}"`（雙冒號，2 段）。**無 engine_mode prefix**。
- **strategy 來源**：`results` 的 `(strategy, symbol)` tuple key 來自上游 [`compute_edge_stats()`](../../program_code/ml_training/realized_edge_stats.py:1) via `james_stein_estimator.py:156`。
- **snapshot path**：根據 `engine_mode` 參數決定檔名（`james_stein_estimator.py:249-263`）：
  - `demo` → `settings/edge_estimates.json`（**Rust runtime demo/live 讀這檔**）
  - `paper` → `settings/edge_estimates_paper.json`（隔離）
  - `live` → `settings/edge_estimates_live.json`
  - `live_demo` → `settings/edge_estimates_live_demo.json`

### 2.2 Strategy label 上游來源（壓縮鏈）

[`realized_edge_stats.compute_edge_stats`](../../program_code/ml_training/realized_edge_stats.py:1) 以 `(strategy_name, symbol)` group by SQL。`strategy_name` 欄位來自 `trading.fills` — 此欄位由 Rust `intent_processor` / `fill_engine` 寫入，**取倉位 `owner_strategy` 欄位原值**。

**關鍵映射缺口**：JS estimator 對上游 fills 表 `strategy_name` 僅會保留**實際有 round-trip 成交**的策略（grid / ma）；`bybit_sync` / `orphan_adopted` 等 sync-only / adoption label 的倉位若從未 close 或 close 歸因到 entry strategy 而非 sync label，**不會**產生對應 JS cell。

### 2.3 Scheduler — [`srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/edge_estimator_scheduler.py:244`](../../program_code/exchange_connectors/bybit_connector/control_api_v1/app/edge_estimator_scheduler.py:244)

每小時 daemon 呼 `run_james_stein(days_back=7, engine_mode=mode)` 對 `("demo", "live_demo")` 兩模式各跑一次，寫出對應 JSON。**days_back=7** → rolling 7 天視窗（與 P1-15 cleanup horizon 對齊）。

**語意確認**：
- Writer key = `"{strategy}::{symbol}"` → 與 Rust `EdgeEstimates::get_cell(strategy, symbol).format!("{}::{}")`（`edge_estimates.rs:220`）**完全一致**。
- → **H1 / H2 FAIL**（key 格式對齊，非 mismatch 也非 engine_mode 3-segment）。

---

## 3. Reader 路徑（Rust → EdgeEstimates）

### 3.1 Load — [`srv/rust/openclaw_engine/src/edge_estimates.rs:62`](../../rust/openclaw_engine/src/edge_estimates.rs:62) `load_from_file()`

```rust
// edge_estimates.rs:65-101（摘錄）
let parsed: serde_json::Value = serde_json::from_str(&content).ok()?;
let obj = parsed.as_object()?;
...
for (key, val) in obj {
    if key.starts_with('_') { continue; }     // skip _meta
    if let Some(bps) = val.get("shrunk_bps").and_then(|v| v.as_f64()) {
        // ... parse win_rate / n / std_bps ...
        data.insert(key.clone(), CellEstimate { shrunk_bps: bps, ... });
    }
}
```

- Top-level iter；skip `_`-prefixed；保留所有其他 key 原樣作 HashMap key。
- **與 writer 完全對稱**：`"{strategy}::{symbol}"` 進 HashMap。

### 3.2 Mode-aware load — [`srv/rust/openclaw_engine/src/edge_estimates.rs:193`](../../rust/openclaw_engine/src/edge_estimates.rs:193) `load_for_mode()`

```rust
pub fn load_for_mode(base_dir: impl AsRef<Path>, mode: &str) -> Self {
    let filename = match mode {
        "paper" => "edge_estimates_paper.json",
        _ => "edge_estimates.json",     // demo + live 共用 production JSON
    };
    ...
}
```

**注意**：`live_demo` mode **不走** `edge_estimates_live_demo.json`（僅 2 分支 `paper` / 其他）。Live / LiveDemo runtime 讀的是 `edge_estimates.json`（demo + live 共用）。`edge_estimates_live_demo.json` 目前只是 Python 側 side-write，Rust reader **未讀**。

→ **敏感**：目前 production runtime 是 demo（authorization.json 未簽，live pipeline 拒啟），所以讀的就是 `edge_estimates.json`（43 cells）。

### 3.3 Wiring — [`srv/rust/openclaw_engine/src/event_consumer/mod.rs:459`](../../rust/openclaw_engine/src/event_consumer/mod.rs:459)

```rust
let mode = pipeline_kind.db_mode();                                  // "demo" / "live" / ...
let estimates = crate::edge_estimates::EdgeEstimates::load_for_mode(&base, mode);
pipeline.set_edge_estimates(estimates);
```

- 啟動時一次性 load + `set_edge_estimates()`；
- 每小時 Python scheduler 只刷新**檔案**；Rust runtime **不**熱重載 — 需 `restart_all.sh --rebuild` 或 engine restart 才吃到新檔（comment 記於 `edge_estimator_scheduler.py:13-20`）。
- 當前 engine PID 158918 於 2026-04-22 20:55 CEST `--rebuild` 啟動，load 當時 `edge_estimates.json` 快照。

### 3.4 get_cell — [`srv/rust/openclaw_engine/src/edge_estimates.rs:219`](../../rust/openclaw_engine/src/edge_estimates.rs:219)

```rust
pub fn get_cell(&self, strategy: &str, symbol: &str) -> Option<&CellEstimate> {
    let key = format!("{}::{}", strategy, symbol);
    self.data.get(&key)
}
```

- 精確 key lookup，無 normalization / fallback / prefix 嘗試。
- 任何 strategy 字串與 JSON key 不匹配 → `None` → downstream `est_net_bps = None`。

---

## 4. T4 closure — [`srv/rust/openclaw_engine/src/tick_pipeline/on_tick/step_6_risk_checks.rs:144-165`](../../rust/openclaw_engine/src/tick_pipeline/on_tick/step_6_risk_checks.rs:144)

```rust
// step_6_risk_checks.rs:140-165（T4 核心片段）
let paper_state_ref = &self.paper_state;
let price_tracker_ref = &self.price_tracker;
let edge_estimates_ref = self.intent_processor.edge_estimates();
let tick_ts_ms = event.ts_ms;
let exit_features_fn = |row: &PositionRow| -> Option<ExitFeatures> {
    let snap = paper_state_ref.position_exit_snapshot(&row.symbol)?;
    let price_roc_short = price_tracker_ref.compute_roc(&row.symbol, 300);
    let est_net_bps = edge_estimates_ref
        .get_cell(&snap.owner_strategy, &row.symbol)       // ← 關鍵 2-arg call
        .map(|c| c.shrunk_bps as f32);
    Some(build_exit_features_for_tick(
        &snap, row.current_price, row.atr_pct, price_roc_short, est_net_bps, tick_ts_ms,
    ))
};
```

- `.get_cell(&snap.owner_strategy, &row.symbol)` — **只 2 個參數 `(strategy, symbol)`**，無 engine_mode。
- `snap.owner_strategy` 從 `PaperState::position_exit_snapshot()` 取，即 `PaperPosition.owner_strategy` 原值（`paper_state/containers.rs:47`）。

---

## 5. 5 假設逐條驗證

### H1 — JSON cells key 與 T4 closure 查詢 key 不匹配 — **FAIL**

**證據**：
- Writer key = `f"{strategy}::{symbol}"`（`james_stein_estimator.py:375`）
- Reader load 直接 HashMap `key.clone()`（`edge_estimates.rs:91`）
- T4 closure `format!("{}::{}", strategy, symbol)`（`edge_estimates.rs:220`）
- → 三處完全對稱，格式零 mismatch。

### H2 — JSON key 三段式 `engine_mode:strategy:symbol` vs T4 傳 2 段 — **FAIL**

**證據**：
- JSON 實測 keys（§1）形如 `grid_trading::1000PEPEUSDT`，**只有雙冒號 2 段**，無 engine_mode prefix。
- Writer code（`james_stein_estimator.py:375`）明確 `f"{strategy}::{symbol}"`，未注入 engine_mode。
- Engine mode 隔離是**檔名**層級（`edge_estimates.json` vs `edge_estimates_live_demo.json`），非 key 內部。

### H3 — Scheduler 實際寫入 cells 遠少於預期（資料不足）— **PASS（附加因）**

**證據**：
- `_meta.n_cells=43`（demo）= 22 grid + 21 ma = 雙策略 × ~23 symbols 的稀疏覆蓋。
- P1-15/17 JS estimator 要求每 cell `n_observations ≥ min_samples=3`（CLI default）；很多 (strategy, symbol) combo 不達標自動 drop。
- Runtime universe（pinned + scanner）可達 25+ symbols × 5 策略 = ~125 理論 cells；實測 43 = 34% 覆蓋。
- **但**：此條單獨**不足以解釋 99.1% miss** — 若倉位全落在 grid/ma × 已覆蓋 symbols，命中率應 ≥50%。需疊加 H4 才能解釋 99%。

**量化推斷**（無直接 psql，但可從 CLAUDE.md §三 得知）：
- `P1-6 DEMO-BYBIT-SYNC-ORPHAN-1`：6 個 `bybit_sync` 倉位策略動不了；`P1-8 FUP retriage_synthetic_owner` tick-level 自主接管中。
- 換言之：runtime 長期持倉**多為 `owner_strategy = "bybit_sync"`**（交易所 WS upsert 直入，見 `fill_engine.rs:66, 146`），**沒有對應 JSON cell**。

### H4 — `owner_strategy` 欄位值與 JSON key 策略字串不匹配 — **PASS（首要因）**

**證據 A — 實際寫入 owner_strategy 的 code 點**：

| code 點 | 寫入值 | file:line |
|---|---|---|
| Bybit WS PositionUpdate adopt（first insert） | `"bybit_sync"` | [`fill_engine.rs:66`](../../rust/openclaw_engine/src/paper_state/fill_engine.rs:66) |
| Bybit WS upsert（None branch，首見 symbol） | `"bybit_sync"` | [`fill_engine.rs:146`](../../rust/openclaw_engine/src/paper_state/fill_engine.rs:146) |
| ORPHAN-ADOPT-1 adopt | `"orphan_adopted"` | [`orphan_handler.rs:75-84`](../../rust/openclaw_engine/src/position_reconciler/orphan_handler.rs:75) |
| orphan detect + freeze | `"orphan_frozen"` | [`paper_state/tests.rs:677`](../../rust/openclaw_engine/src/paper_state/tests.rs:677) （邏輯在 orphan_handler） |
| DUST-EVICTION-GAP-1 freeze | `DUST_FROZEN_STRATEGY`（= `"dust_frozen"`） | [`dust_gate.rs:112`](../../rust/openclaw_engine/src/paper_state/dust_gate.rs:112) |
| retriage_synthetic_owner 升級 | operator-provided（`"ma_crossover"` / `"grid_trading"` 等） | [`dust_gate.rs:93`](../../rust/openclaw_engine/src/paper_state/dust_gate.rs:93) |
| strategy 自 emit entry | `strategy.name()`（`"ma_crossover"` / `"grid_trading"` / `"bb_breakout"` / `"bb_reversion"` / `"funding_arb"` 等） | [`fill_engine.rs:257, 330`](../../rust/openclaw_engine/src/paper_state/fill_engine.rs:257) |

**證據 B — JSON 零 bybit_sync/orphan cells**：

| strategy 前綴 | JSON cell 數 | 對應 runtime owner_strategy 來源 |
|---|---:|---|
| `grid_trading` | 22 | 僅 `grid_trading` strategy emit 的 entry |
| `ma_crossover` | 21 | 僅 `ma_crossover` strategy emit 的 entry |
| `bybit_sync` | **0** | `fill_engine.rs:66,146` WS adopt — 無 cell |
| `orphan_adopted` / `orphan_frozen` | **0** | `orphan_handler.rs` adopt/freeze — 無 cell |
| `dust_frozen` | **0** | `dust_gate.rs:112` dust freeze — 無 cell |
| `bb_breakout` / `bb_reversion` / `funding_arb` | **0** | 這些策略當前無活躍 fills 產 JS label |

**因果鏈**：
1. Demo runtime 的長期持倉大量落在 `owner_strategy = "bybit_sync"`（exchange sync adopt，見 CLAUDE.md §三 P1-6 DEMO-BYBIT-SYNC-ORPHAN-1「6 個 bybit_sync 倉位策略動不了」）。
2. JS estimator 7 天窗口內即便有 retriage 升級成 `ma_crossover`/`grid_trading` 的倉位，**close fill 的 strategy_name 仍可能寫原 bybit_sync 或升級後 label**（需查 fill_engine close path 確認 — 未查，但 7d est_net_bps NULL 率 99.1% 強烈暗示此方向）。
3. T4 closure `get_cell("bybit_sync", "SYMBOL")` → JSON 無此 key → `None` → downstream Gate 1 Hold。

**疑點**：worklog §3.2 提到「7d 1/110 有 est_net_bps」。該 1 row 可能是單一 strategy-owned symbol（grid 或 ma）剛好 match JSON cell 的幸運倉位。

### H5 — JSON schema 變過（健康時有 `cells` array，現在是 map）— **FAIL**

**證據**：
- `james_stein_estimator.py:366-397` 寫法一直是 flat map（自 PH5-WIRE-1 commit 以來）。
- `edge_estimates.rs:62` load 實作也是 flat map iter，從無 `cells` 欄位支持。
- JSON mtime 2026-04-22 21:56 當天 scheduler 已正常寫入（§1），schema 是 flat map。
- Healthcheck 誤查 `.get("cells", [])` 是 **Python 側實作 bug**（`passive_wait_healthcheck.py:187`），JSON 從未有 `cells` 欄位。

→ 所謂「cells 0/0」是 healthcheck 誤解 schema，非 JSON 損壞/變更。

---

## 6. 命中假設的修復路徑（3 options）

三選項可**單獨或疊加**實施；option A + B 為首推組合。

### Option A — Rust 側 fallback Gate 1 分支（code fix，~0.5-1d）

**位置**：`exit_features/v2.rs physical_micro_profit_lock_v2` Gate 1（edge floor gate）

**現況邏輯**（推定 — 基於 `v2.rs` 命名 `min_net_floor_bps=5.0`）：
```rust
if features.est_net_bps.unwrap_or(-f32::INFINITY) <= config.min_net_floor_bps {
    return PhysicalDecision::Hold;   // ← None 直接 Hold（當前行為）
}
```

**新增分支**：
```rust
let edge = match features.est_net_bps {
    Some(e) => e,
    None => grand_mean_bps_fallback,    // 例如讀 JSON _meta 的 grand_mean_bps
                                         // 或 config.missing_edge_fallback_bps = -5.0
};
if edge <= config.min_net_floor_bps { return Hold; }
```

**優點**：
- 不碰 data 管線；
- 保守 fallback（`grand_mean_bps ≈ -4.3` < `min_net_floor_bps=5.0` → 仍 Hold）→ 行為等效目前，但 log 中可明確區分「miss vs explicit negative」。

**風險**：
- 若 fallback 設太樂觀（e.g. 0 bps）→ Gate 1 放過 → 接觸 §3.1 Gate 4a unit bug mass close。**必須與 P0-13 同 rebuild**。
- 建議值：`fallback_bps = min(grand_mean_bps, -10.0)` 保守 floor。

### Option B — Python 側補齊 strategy label cells（data fix，~1-3d）

**位置**：`james_stein_estimator.py` + 上游 `realized_edge_stats.py`

**思路 1（推）**：JS estimator 跑完後，對 `("bybit_sync", "orphan_adopted", "dust_frozen")` 這些 sync/adopt label，**用該 symbol 下任一可用 strategy 的 shrunk_bps 作為 proxy cell** 寫入 JSON（或直接用 `grand_mean_bps`）。例如：

```python
# james_stein_estimator.py:_write_json_snapshot 下游 hook
SYNC_LIKE = ("bybit_sync", "orphan_adopted", "orphan_frozen", "dust_frozen")
for sym in symbols_in_snapshot:
    for sync_label in SYNC_LIKE:
        key = f"{sync_label}::{sym}"
        if key not in snapshot:
            snapshot[key] = { "shrunk_bps": grand_mean_bps, "n": 0, "B": 1.0,
                              "_proxy_from": "grand_mean", ... }
```

**優點**：徹底消除 99% miss；Rust 側零改。

**風險**：
- 「用 grand_mean 當 proxy」引入 bias — 所有 sync 倉位 edge 看起來一致。與真實策略 performance 脫節。
- 可改為「用該 symbol 下 grid/ma 兩策略的加權平均」為更精準 proxy。

**思路 2**：不改 estimator，改 Rust 側 retriage 時機 — 保證倉位在進入 Priority 6 前 `owner_strategy` 已 promote 出 sync 標籤。**但** 這是 P1-6 / P1-8 長期項目，跨 P0-14 scope。

### Option C — 等 P1-6/P1-8 retriage 自然解決 + 擴大 JS cell 覆蓋（passive, 週級）

**路徑**：
1. P1-8 FUP `retriage_synthetic_owner` tick-level 自主接管（CLAUDE.md §三）— 目前觀察一週起算 2026-04-17，預計 ~2026-04-24 判定是否生效；
2. 若有效，bybit_sync 倉位會逐步 promote 成 grid/ma 擁有，close 後寫對應 strategy fill；
3. JS estimator 7 天窗口後 cell 自然新增；
4. est_net_bps NULL 率自然下降。

**風險**：
- 與被動等待 audit 初衷（§passive_wait_silent_fail_audit.md）**直接衝突** — operator 明確反饋「被動等待但 silent fail 不能接受」；
- 時間成本 ~週級；
- 無法解釋「近期 fills.strategy_name 實際分佈」，純假設。

**建議**：**不採用 Option C**。

### 首推組合 — **A + B**

- A 修 Gate 1 fallback（Rust 側，immediate observability，保守語意）；
- B 補 JS 側 sync-label proxy cells（Python 側，從根源消除 miss）；
- 兩者同 PR + **必須與 P0-13 同 rebuild 部署**（否則 Gate 4a unit bug 疊加過度 Lock）。
- 預期效果：est_net_bps NULL 率 99% → <10%；Priority 6 首次有機會真實 fire；healthcheck 同時修 schema 誤查。

---

## 7. 與 P0-13 的互動（critical coupling）

**依賴關係**：**P0-14 fix 必須在 P0-13 fix 同 rebuild 或之後，絕不可單獨部署**。

### 7.1 當前等效 dead 狀態

| Gate | 當前行為 | 原因 |
|---|---|---|
| Gate 1 `edge ≤ 5.0 → Hold` | **永遠 Hold** | `est_net_bps = None` ∀ 99% 倉位（P0-14） |
| Gate 2 `entry_age_secs ≥ min_hold` | 多數通過 | 倉位持續時間自然 |
| Gate 3 `peak_atr_norm ≥ 0.5` | **永遠通過** | `peak_pnl_pct(%) / atr_pct(fraction) × 100x` 放大（P0-13） |
| Gate 4a `giveback ≥ threshold` | 無法到達 | Gate 1 攔死 |

→ 當前 Priority 6 runtime dead，`phys_lock_*` fire 7d = 0。

### 7.2 單獨修 P0-14（危險）

若修 P0-14（Gate 1 放過多數倉位）但**不修 P0-13**：
- Gate 3 永遠過（100x 放大）；
- Gate 4a `giveback_atr_norm ≈ 364` >> threshold（typically 0.3-1.0）→ **立刻 Lock 所有 winner 倉位**；
- 後果：mass close，可能 close 掉尚未達到真 peak / giveback 的所有 +profit 倉位；
- 2026-04-22 worklog §3.1 明確警告：「若有人修了 §3.2（P0-14），Gate 4a 會立刻引發 mass close 災難」。

### 7.3 單獨修 P0-13（無效）

若修 P0-13（unit 修正）但**不修 P0-14**：
- Gate 3 / Gate 4a 算法正確化；
- 但 Gate 1 仍 99% Hold → Priority 6 仍 0 fire；
- 無 runtime observable effect（除了 `learning.exit_features.giveback_atr_norm` 列的 DB avg 從 365 降到 ~3）。

### 7.4 部署契約

**必要條件**（鐵律）：
1. P0-13 commit + P0-14 commit 必須**同一 PR 或連續 2 commit 同 `restart_all.sh --rebuild` 週期部署**；
2. 部署前必跑新 healthcheck 確認兩項 fix 存在於 binary；
3. 部署後第一 1h 密切監控 `phys_lock_*` fire 率 — 合理區間 0.5-5 fire/day（若 >20 fire/day = Gate 4a over-fire，回滾）；
4. P0-15（文檔對齊）可獨立部署。

### 7.5 次要互動 — Gate 4a 新觸發對 MICRO-PROFIT-FIX-1 的補位

- §passive_wait_silent_fail_audit.md §3.4 揭露：MICRO-PROFIT-FIX-1 「narrow-band gate 正常運作」敘述錯誤，實際 2026-04-20 起 0 fire（被 T3 deprecation 註解掉的 COST EDGE gate 替代）。
- P0-13 + P0-14 修好後，Priority 6 v2 Gate 4a 是設計上**接替 MICRO-PROFIT narrow-band 的物理層防線**。首次有機會真實 fire。
- 若 fire 率健康 → Phase 5 edge 重評 baseline（P0-3）可納入 Priority 6 作為正 edge 安全網的 candidate；
- 若 fire 率失控 → 需要 `min_net_floor_bps` 調高（如 0 → 5 → 10 漸進）。

---

## 8. operator 可選執行的新 psql 查詢（RCA 後補強）

本 RCA 已從 code + JSON schema 結論 dominant 因為 H4；但若需量化驗證，以下查詢可進一步收斂（session 未授權跑 psql，列此供 operator）：

```sql
-- (A) 近 7 天 exit_features 的 owner_strategy 分佈（確認 H4 量級）
SELECT owner_strategy, COUNT(*) AS n,
       SUM(CASE WHEN est_net_bps IS NULL THEN 1 ELSE 0 END) AS null_count,
       ROUND(100.0 * SUM(CASE WHEN est_net_bps IS NULL THEN 1 ELSE 0 END) / COUNT(*), 2) AS pct_null
  FROM learning.exit_features
 WHERE ts > now() - interval '7 days'
   AND engine_mode = 'demo'
 GROUP BY owner_strategy
 ORDER BY n DESC;
-- 預期：bybit_sync 佔 60-90%, 對應 pct_null ≈ 100%
--       ma_crossover / grid_trading 少數 rows，pct_null 可能 <100%（若 symbol 在 JSON 內）

-- (B) 近 7 天 ma/grid 倉位的 symbol 分佈對照 JSON universe
SELECT owner_strategy, symbol, COUNT(*) AS n
  FROM learning.exit_features
 WHERE ts > now() - interval '7 days'
   AND engine_mode = 'demo'
   AND owner_strategy IN ('ma_crossover','grid_trading')
 GROUP BY 1,2
 ORDER BY 3 DESC;
-- 對照 JSON 的 23 symbols 清單，看有幾個不在 JSON → 即 H3 覆蓋 gap

-- (C) close fills 近 7 天的 strategy_name 分佈（驗證 fill writer 是否保留 bybit_sync label）
SELECT strategy_name, COUNT(*) AS n
  FROM trading.fills
 WHERE ts > now() - interval '7 days'
   AND engine_mode = 'demo'
   AND realized_pnl <> 0
 GROUP BY 1
 ORDER BY 2 DESC LIMIT 20;
-- 若多數是 strategy_close:* / risk_close:* → close 時 strategy_name 已脫 bybit_sync
-- 若多數是 bybit_sync → JS estimator 永遠無 cell，驗證 H4
```

預期 **(A) 結果**：`bybit_sync` rows 佔大多數，null rate ~100%；`ma_crossover` / `grid_trading` rows 少數，null rate 視 symbol 命中而定。

---

## 9. 結論摘要

| 維度 | 結論 |
|---|---|
| **首要命中假設** | H4 — `owner_strategy = "bybit_sync"` / `"orphan_*"` 等 label 無對應 JSON cell，T4 closure `get_cell` 永遠 miss |
| **次要命中假設** | H3 — 即便策略已 promote 到 grid/ma，symbol 未落在 JS 7d 窗口 ≥3 samples 閾值 |
| **FAIL 假設** | H1（key 格式匹配）/ H2（無 engine_mode 3-段式）/ H5（schema 未變） |
| **healthcheck 0/0 來源** | `passive_wait_healthcheck.py:187` 誤查 `.get("cells", [])` — schema bug，非 runtime 問題 |
| **修復路徑推薦** | Option A（Gate 1 fallback）+ Option B（JS 側補 sync-label proxy cells），**必與 P0-13 同 rebuild**；不採 C（被動等待） |
| **不可破壞契約** | P0-14 fix **絕不可單獨部署**，否則 P0-13 unit bug 引發 Gate 4a mass close；兩者必須同 rebuild |

**P0-14 fix entry 建議**（~200 字）：

採 Option A + B 雙管齊下。Python 側 [`james_stein_estimator.py:_write_json_snapshot`](../../program_code/ml_training/james_stein_estimator.py:357) 結尾新增 sync-label proxy cells 寫入（為 `("bybit_sync", "orphan_adopted", "orphan_frozen", "dust_frozen")` × JSON 內 23 symbols 各生 proxy cell，`shrunk_bps = grand_mean_bps`、`n = 0`、標 `_proxy_from: grand_mean`）——徹底消除 H4 下的 99% miss。Rust 側 [`exit_features/v2.rs`](../../rust/openclaw_engine/src/exit_features/v2.rs:1) `physical_micro_profit_lock_v2` Gate 1 新增 `None → min(grand_mean_bps, -10.0)` 保守 fallback 分支作二道防線（應對 Python proxy 還沒寫入的 corner case）。同步修 [`passive_wait_healthcheck.py:187`](../../helper_scripts/db/passive_wait_healthcheck.py:187) 改查 flat map（`len([k for k in data if not k.startswith('_')])`）。**必與 P0-13 giveback unit fix 同 `restart_all.sh --rebuild` 部署**，否則 Gate 4a 放開會觸發 mass close。E1/E2/E4 全鏈走，部署後 1h 監控 `phys_lock_*` fire 率，合理區間 0.5-5 fire/day。

— END —
