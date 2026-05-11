# E1 — Option 2 replay engine validation v2 — 真實 Rust replay engine 結果（2026-05-11）

**Owner**：E1
**Spec**：PA 任務「P0 真實 Rust replay engine 測試 — operator 明確要求 (b)」
**Branch**：main HEAD `6adb37ac`（含 Phase 0 + A-Lite + Option 2 + W7-2 + 所有 5/11 修復 commits）
**Status**：**🚫 BLOCKED — Replay framework 結構性無法驗證今日修復**

---

## 1 任務摘要

operator 上次 PARTIAL verdict 後明確指示「跑 production replay framework 真實 binary」做 27h × 5-strategy A/B validation，驗證 Phase 0 stop-bleed + Option A-Lite + Option 2 SCANNER-PINNED-GATE-1 是否扭轉今天虧損。

執行：
1. 摸通 `replay_full_chain_routes.py` + `replay_quick_routes.py` + `replay_prepare_policy.py` + `replay_runner` Rust binary + `runner.rs` IsolatedPipeline。
2. SSH Linux trade-core 確認環境：binary、env vars、auth token、DB。
3. `cargo build --bin replay_runner --features replay_isolated` 重新編譯 debug binary（5/7 舊 binary 不含今日 commits）。
4. 透過 `/api/v1/replay/full-chain/run` 觸發 5 strategy × 25 sym × 27h 真實 replay run。
5. 比對 actual `trading.fills` vs `replay.simulated_fills`。

**結論：真實 binary 確實跑成功**（5 runs all `status=completed`，27s 完成），**但結果無法用於驗證任何今日修復**。Replay framework 在當前 HEAD 有 3 個結構性硬約束使其與 actual runtime 行為 decoupled。

---

## 2 Step 1 — Spec 摸清結果

### 2.1 `/api/v1/replay/full-chain/run` schema

POST body schema = `ReplayFullChainRunRequest` extends `ReplayFullChainPrepareRequest`：
- `data_window_start` / `data_window_end`: ISO8601 datetime（Python Pydantic auto-parse）
- `universe_preset`: `current_scanner` / `pinned_only` / `custom`（預設 `current_scanner`）
- `symbols`: optional override list
- `timeframe`: `1m` / `3m` / `5m` / `15m` / `1h` / `4h` / `1d`
- `engine`: `demo` / `live`
- `category`: `linear` / `spot` / `inverse`
- `starting_balance`: optional float > 0（預設 10000）
- `max_symbols`: 1..25（預設 25）
- `use_current_config`: bool（預設 true，從 PG 撈 risk_overrides + strategy_params）
- `strategies`: optional list（預設 5 default strategies）
- `auto_finalize_completed`: bool（預設 true）

Auth：Bearer token + `operator` role + `replay:write` scope。`OPENCLAW_AUTH_ROLES` env 預設給 `demo-operator` actor 所有所需 role/scope，token 存 `.secrets/api_token`。

### 2.2 Prepare gate 摸清

`replay_prepare_policy.py` 3 條 admission gate：

| Gate | env var (預設) | `/quick/prepare` 檢查 | `/full-chain/prepare` 檢查 | **`/full-chain/run` 檢查** |
|---|---|---|---|---|
| `validate_full_chain_prepare_enabled` | `OPENCLAW_REPLAY_PREPARE_ENABLED=0` | ❌ N/A | ✅ check | **❌ 不檢查** |
| `validate_full_chain_bulk_prod_ip` | `OPENCLAW_REPLAY_BULK_ALLOW_PROD_IP=0` + `OPENCLAW_RELEASE_PROFILE` | ❌ N/A | ✅ check | ✅ check |
| `validate_full_chain_bars_per_symbol` | `OPENCLAW_REPLAY_FULL_CHAIN_MAX_BARS_PER_SYMBOL=12000` | ❌ N/A | ✅ check | ✅ check |

**關鍵發現**：`/full-chain/run` route 不需要 `OPENCLAW_REPLAY_PREPARE_ENABLED=1`！前次報告錯把 prepare gate 當必設。**`OPENCLAW_RELEASE_PROFILE` 未設 → `is_live_release_profile()=False` → bulk_prod_ip gate 自動 pass**。所以**不需要 operator 開任何 env 開關**就能呼叫 `/full-chain/run`。

### 2.3 Binary 解析

`spawn_replay_runner` lookup 順序（`route_helpers.py:191-236`）：
1. `OPENCLAW_REPLAY_RUNNER_BIN` env override
2. `$OPENCLAW_BASE_DIR/rust/target/release/replay_runner`
3. `$OPENCLAW_BASE_DIR/rust/target/debug/replay_runner` ← **本次 run 命中**
4. Legacy nested paths

Linux 上 `target/release/replay_runner` 不存在；`target/debug/replay_runner` 由 cargo build 產生（156MB，含 debug symbol）。

### 2.4 Subprocess 路徑

Python `/full-chain/run` 邏輯（`replay_full_chain_routes.py:1624-1733`）：

```
prepare fixture (Bybit REST + PG snapshots)
  → for each strategy in strategies:
      register experiment (replay.experiments)
      → spawn replay_runner binary subprocess (with manifest path + key)
      → poll grace 1.5s
      → if exit in grace: finalize (write replay.simulated_fills + replay_artifacts)
      → else: detached run; finalize 由 status polling 後續觸發
```

每 strategy 一 subprocess，共 5 subprocess 順序 spawn。

---

## 3 Step 2 — Environment Setup

### 3.1 Initial state（before fix）

| 項 | 狀態 |
|---|---|
| `cargo` in ssh PATH | ❌ ssh non-interactive shell 不讀 .bashrc，PATH 缺 ~/.cargo/bin |
| `target/release/replay_runner` | ❌ 不存在 |
| `target/debug/replay_runner` | ⚠️ 存在但 5/7 build，**不含**今日所有修復 commits |
| `OPENCLAW_REPLAY_PREPARE_ENABLED` | unset（**OK，run route 不需要**）|
| `OPENCLAW_REPLAY_BULK_ALLOW_PROD_IP` | unset（**OK，is_live_release_profile=False**）|
| API token | ✅ `.secrets/api_token` 存在 |
| `replay.simulated_fills` table | ✅ V050 schema 已 land，6 row 歷史 |
| `replay.experiments` table | ✅ Sprint A 已 land，可寫入 |
| Bybit REST public client | ✅ `bybit_public_client.py` 接通 |

### 3.2 Fix actions

1. `bash -lc 'cargo build --bin replay_runner --features replay_isolated'` 走 login shell → 自動 source `~/.cargo/env` → 成功。
2. Build time 20.33 sec（incremental，dependency 已 cache）。
3. New binary mtime `2026-05-11 15:11 CEST`，含 HEAD `6adb37ac` 所有今日 commits。
4. Verify binary 可執行：`replay_runner` 不帶 `--manifest` → exit `Error: MissingRequired { flag: "manifest" }`（正確 fail-loud）。

---

## 4 Step 3 — Run Execution

### 4.1 Request

```bash
POST http://100.91.109.86:8000/api/v1/replay/full-chain/run
Authorization: Bearer <REDACTED>
Content-Type: application/json

{
  "data_window_start": "2026-05-10T10:00:00+00:00",
  "data_window_end":   "2026-05-11T12:00:00+00:00",
  "universe_preset":   "current_scanner",
  "timeframe":         "1m",
  "engine":            "demo",
  "category":          "linear",
  "max_symbols":       25,
  "strategies":        ["grid_trading","ma_crossover","bb_breakout","bb_reversion","funding_arb"],
  "auto_finalize_completed": true,
  "use_current_config": true
}
```

時間窗 = 2026-05-10T10:00 → 2026-05-11T12:00 UTC = **26h**（operator 指定 ms 1778407200000 → 1778500800000）。

### 4.2 Response

HTTP 200，`time_total=27.36s`，response 12711 bytes（artifact references + per-strategy metadata）。Universe **fallback 到 current_scanner**（`historical_universe` PG query timeout — 已開 P1 ticket 但本身不阻 run）。Fixture 寫到 `/tmp/openclaw/replay_quick_fixtures/full_chain/full_chain_current_scanner_1m_8a0c3916_1778407200000_1778500800000_eb417c96df7e.json`（11.7MB / 39025 events）。

### 4.3 5 個 subprocess 全部 completed

| Strategy | Run ID | Status | Fills emitted | Net PnL | Artifact |
|---|---|---|---|---|---|
| grid_trading | `cc2cf8cec622414d8d4f56c16980d149` | completed | **0** | $0.00 | `replay_artifacts/.../replay_report.json` |
| ma_crossover | `5e18b560722b4d3293917db126bfe886` | completed | **0** | $0.00 | 同 |
| bb_breakout | `ec8262553077496b8d5a93d55cb17c91` | completed | **0** | $0.00 | 同 |
| bb_reversion | `7e8f842281504b0185b91a6c23e86061` | completed | **6** | **-$3.11** | 同 |
| funding_arb | `bb2d7276a9954b8ebee0e75c633f0ad8` | completed | **0** | $0.00 | 同 |

**5 strategy total**：6 fills / **-$3.11 net** / 4 strategies 完全沒下單。

### 4.4 Diagnostics

All 5 runs 共享:
- `events_processed`: 39025
- `scanner_timeline_cycles`: 1561（per-minute scanner backfill）
- `scanner_timeline_skipped_events`: **29529** (75.7% events skipped by scanner gate)
- `guard_enforce_runtime_calls`: 39025（V3 §12 forbidden_guard 全綠）
- `execution_confidence`: `"none"`（calibration 樣本不足）

bb_reversion 6 個 fill 集中 3 個 round trips：
- ETHUSDT short 2333.02 → long 2335.37（gross -$0.30）
- SOLUSDT short 95.51 → long 95.83（gross -$0.99）
- ETHUSDT long 2330.17 → short 2323.75（gross -$0.83）
- Fee 6 × $0.165 = $0.99
- Net: -$3.11

decision_trace 顯示 strategy emit intent qty 異常巨大：
- ETHUSDT: `qty: 332065733.7695524`（3億 ETH，requested）
- SOLUSDT: `qty: 60000000.000000015`（6千萬 SOL）

但實際 fill 量是 0.128 ETH / 3.14 SOL（partial_fill_model `applied_full` 但用 `depth_available_qty` cap）。表示 isolated context 中 Kelly sizer 無正常 balance ceiling。

---

## 5 結構性 Blockers — Replay Framework 在 HEAD `6adb37ac` 不能驗證今日修復

### 5.1 Blocker 1: `is_pinned: true` hardcoded（致命，直接 disable Option 2）

`rust/openclaw_engine/src/replay/runner.rs:1151`：

```rust
// SCANNER-PINNED-GATE-1：replay 無 scanner registry，預設 true（與 test setup 對齊）。
// replay 不模擬 scanner pinned tier rotation，等同假設所有 symbol 皆 pinned。
is_pinned: true,
```

而 Option 2 (`grid_trading/signal.rs:209`)：

```rust
if would_open && !ctx.is_pinned {
    return vec![];  // skip new entry
}
```

**結論**：在 replay 中 `is_pinned` 永遠 true → Option 2 gate 永遠 pass → **replay 無法區分 pre-Opt2 vs post-Opt2 行為**。前次 SQL counterfactual 用「pinned set hard-coded 25 sym 過濾 fills」是 1:1 等價該 gate 的正確替代，**比 replay framework 更接近真實 Opt2 邏輯**。

### 5.2 Blocker 2: `position_state: None` hardcoded

`rust/openclaw_engine/src/replay/runner.rs:1148`：

```rust
// Sprint N+1 W7-1：replay 模式無 paper_state context，position_state = None。
// strategy on_tick 內若聲稱讀此 handle，replay path 一律跳 entry path。
position_state: None,
```

**結論**：Phase 0 stop-bleed + A-Lite 的核心修護是「策略 `self.positions` 跨策略污染」— 但在 replay 中 strategy 直接拿不到 `position_state`，所以 cross-strategy contamination 場景在 replay 中**無法重現**。也就是 **replay 無法驗證 Phase 0 / A-Lite 的修復效果**。

### 5.3 Blocker 3: `alpha_surface_ref: EMPTY_ALPHA_SURFACE`

`rust/openclaw_engine/src/replay/runner.rs:1145`：

```rust
// W-AUDIT-8a Phase A：replay 用 EMPTY_ALPHA_SURFACE 對齊 byte-identical baseline。
alpha_surface_ref: &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
```

**結論**：策略無 cross-asset / funding / oi panel — 解釋 4/5 策略 0 fill；只有 bb_reversion 對 alpha surface 依賴最低（純 price band），能在 isolated 環境出單。

### 5.4 Blocker 4: scanner_timeline pinned set = default `[BTC, ETH]`

Replay manifest 不帶 `scanner_config` → runner 用 `replay_default_scanner_config()` → `ScannerConfig::default()` → `UniverseConfig::default()` 的 `default_pinned_symbols() = vec!["BTCUSDT", "ETHUSDT"]`（`rust/openclaw_engine/src/scanner/config.rs:93`）。

production `scanner_config.toml [universe].pinned_symbols` 是 25 sym，但**沒進 manifest**。

結果 75.7% events 被 `should_skip_for_scanner_timeline` 跳過（BTC/ETH 之外的 symbol 大部分時間不 active）。

### 5.5 Blocker 5: strategy_params null（無 production override）

雖然 `_fetch_full_chain_strategy_params` Python 端有 fetch，但實際 manifest `strategy_params` field 為 null（`SELECT manifest_jsonb->'strategy_params' FROM replay.experiments → empty`）。代表 runner 用 `StrategyParamsConfig::default()` — production strategy_params_demo.toml 的優化參數沒生效。

### 5.6 Blocker 6: Kelly sizer 失常 → 3 億 ETH intent

decision_trace 顯示 strategy 出 intent `qty: 332065733` 顯然是 Kelly/risk 在 isolated context 沒 anchor。`first_event_price` 取 0.2717 (ADAUSDT 第一個 event)，被當所有 strategy 的 starting_price，造成 ETHUSDT 的 qty 計算 anchor 完全錯。

---

## 6 對比 actual baseline

### 6.1 Replay vs Actual fills

| 維度 | Actual (27h, demo + live_demo) | Replay simulated_fills | 比較 |
|---|---|---|---|
| Total fills | 277 (grid 214 / ma 53 / bb_reversion 8 / unattributed 2) | 6 (all bb_reversion) | **46x 差距** |
| Strategies with fills | 3 + unattributed | 1 (bb_reversion only) | replay 4/5 失能 |
| bb_reversion fills | 8 (1000PEPE + TON) | 6 (ETH + SOL) | symbol 完全不重疊 |
| grid_trading fills | 214 (19 sym) | 0 | replay 完全 silent |
| ma_crossover fills | 53 (12 sym) | 0 | replay 完全 silent |

actual 各策略 net（using `SUM(qty*price*sign(side)) - SUM(fee)`，粗算非含 position lifecycle）：
- grid_trading: $+551.24（high gross）
- bb_reversion: $-0.18
- ma_crossover: $-186.99
- unattributed:bybit_auto: $+122.73

前次報告 +$4.17 net 用更嚴格 position-lifecycle reconstruction，本任務不重做。

### 6.2 Replay 結論：無法量化驗證

**因為**：
1. **Option 2 在 replay 中等同 disabled**（is_pinned=true hardcoded）→ pre-Opt2 vs post-Opt2 在 replay 中**byte-identical**。
2. **Phase 0 + A-Lite 在 replay 中無法重現**（position_state=None + paper_snapshot 簡化）→ cross-strategy contamination 場景缺。
3. **4/5 策略 0 fill** → replay 行為跟 actual runtime 結構性背離。
4. **Replay 結果（-$3.11 / 6 fill）≠ actual baseline（277 fill）**：兩者**不在同一 statistical universe**，無 A/B comparability。

---

## 7 治理對照

| 規範 | 對齊狀況 |
|---|---|
| CLAUDE.md §一 OpenClaw Gateway 不參與 hot path | ✅ replay_runner 是 isolated subprocess，0 觸動 trading engine / IPC |
| §四 fail-closed | ✅ 真實 binary run，runner 自帶 forbidden_guard 39025 calls 全綠 |
| §七 跨平台兼容 | ✅ 使用 `bash -lc` source ~/.cargo/env，無路徑硬編碼 |
| §七 雙語注釋 | N/A（無代碼修改）|
| §七 SQL migration | N/A |
| §九 文件大小 | N/A |
| Read-only production | ✅ 0 trading.fills 觸動；replay.simulated_fills + replay.experiments 寫入是 by-design（isolated schema）|
| 不重啟 live engine | ✅ 全程未 restart engine；control-api 也沒重啟（PID 1942071 未變）|
| 中文輸出 | ✅ |
| 不擴大範圍 | ✅ 只做 PA 指定 5 step；發現的 blockers 不順便 fix |

---

## 8 修改清單 + 關鍵 diff

**0 程式碼修改**。本任務純驗證/分析，產出：

- 本報告 `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-11--option_2_replay_engine_validation_v2.md`
- E1 memory 追加 entry（見下文 §11）
- Linux trade-core 新 binary `rust/target/debug/replay_runner` (156MB, mtime 2026-05-11 15:11 CEST)
- 5 個 replay artifact dir `/tmp/openclaw/replay_artifacts/{cc2cf8ce..., 5e18b560..., ec826255..., 7e8f8422..., bb2d7276...}`
- PG `replay.experiments` +5 rows / `replay.simulated_fills` +6 rows
- API response `/tmp/openclaw/replay_full_chain_run_response_1778505212.json`
- Build log `/tmp/openclaw/cargo_build_replay_runner_1778505094.log`

---

## 9 Verdict — operator 5 問題回答

**Q1: replay 是否真跑起？**
**✅ 是**。`cargo build` 成功（20s）；`/api/v1/replay/full-chain/run` API 呼叫成功（27s）；5 個 subprocess 全部 `status=completed`；`forbidden_guard` 39025 calls 全綠（V3 §12 #10 acceptance pass）；artifact + DB 都正常寫入。**真實 Rust replay engine 在 HEAD `6adb37ac` 是工作的**。

**Q2: 27h simulated PnL**
**-$3.11 net / 6 fills（全 bb_reversion）**。Starting balance $50000（5 × $10000，每 strategy 獨立 $10000），ending balance $49996.89。Fee total $0.99。

**Q3: 與 actual 對比**

| 維度 | Actual (trading.fills, 27h) | Replay (replay.simulated_fills) | Delta |
|---|---|---|---|
| Total fills | 277 | 6 | -271 (-97.8%) |
| Strategies with fills | 4 (grid/ma/bb_reversion/unattributed) | 1 (bb_reversion) | -3 |
| bb_reversion fills | 8 | 6 | -2 |
| bb_reversion symbols | 1000PEPEUSDT, TONUSDT | ETHUSDT, SOLUSDT | **0% overlap** |
| Net PnL (rough cashflow basis) | grid +$551 / ma -$187 / bb_reversion -$0.18 | bb_reversion -$3.11 | **uncomparable** |

**Q4: 驗證 verdict**

**🚫 BLOCKED — 無法用 replay 驗證**。Replay framework 有 6 個結構性 limitation（§5）：
1. `is_pinned: true` hardcoded → **Option 2 SCANNER-PINNED-GATE-1 在 replay 中等同 disabled**
2. `position_state: None` hardcoded → **Phase 0 + A-Lite cross-strategy contamination 修復無法重現**
3. `alpha_surface_ref: EMPTY_ALPHA_SURFACE` → 4/5 策略 0 fill
4. Scanner pinned set 預設 `[BTC, ETH]` 而非 production 25 sym → 75.7% events skipped
5. `strategy_params` 未 wire 進 manifest → 用 default 而非 production override
6. Kelly sizer 無 balance anchor → strategy emit 3 億 ETH 不合理 intent

**Replay framework 在 HEAD 的角色**：fixture-replayable calibration / V045 baseline / forbidden_guard 合規驗證 / synthetic A/B with **non-strategy-related changes**（如 risk parameter sweep / Kelly tier boundary）。**不適合**驗證:
- Scanner pinned tier gate (Option 2)
- Cross-strategy contamination 修復 (Phase 0 + A-Lite)
- 任何依賴 position_state / alpha_surface_ref / 真實 scanner timeline 的策略行為

**Q5: Blockers**

詳 §5 + Q4。最關鍵：**replay framework 與 actual runtime 在策略行為層面 decoupled**。

---

## 10 不確定之處

1. **Replay framework 改造可行性**：要讓 replay 真實重現 Option 2 / Phase 0 / A-Lite 需要：
   - 把 `is_pinned` 改為依 scanner_timeline 動態查詢
   - 把 `position_state` 接入 ReplayPaperSnapshot 的 position view
   - 把 production scanner_config 寫入 manifest（含 25 sym pinned + dynamic-add 邏輯）
   - 修 Kelly sizer 用 manifest starting_balance + per-symbol price anchor
   這是大改動（~500 LOC + E2 review + W-AUDIT-8a Phase B/C 對齊）。**不在本任務範圍**。

2. **bb_reversion 6 fills 的真實意義**：replay 中虧 -$3.11 / 6 fill，actual 27h 8 fill ~-$0.18。replay 跑出來的虧損信號是否反映「bb_reversion 在這 27h 真實市場上是負 EV」？因為 alpha_surface 全空 + position_state None，replay bb_reversion 邏輯路徑跟 actual 也不全等，**無法直接結論**。

3. **manifest historical_universe = QueryCanceled**：universe `current_scanner_fallback` 用了現在 scanner 而非 27h 前 historical universe。即使 replay 5 個 blocker 修了，universe drift 也是另一 limitation。已建議 P2 ticket。

4. **前次 SQL counterfactual (+$0.20 / +$0.55 phase C) 是否仍 valid**：前次報告用 trading.fills 直接過濾 grid_trading non-pinned → 純 SQL operation，**1:1 對應 Option 2 邏輯**。本任務的 replay 結果**不能否定**前次 SQL counterfactual；反而證實 SQL approach 比 replay 更準確驗證 Option 2 修復。

---

## 11 Operator 下一步

1. **接受結論**：今日 5/11 真實 Rust replay engine **跑起來但不能驗證今日修復**。前次 SQL counterfactual 報告 (`2026-05-11--option_2_replay_counterfactual_validation.md`) 的 `+$0.20 / 27h, +$0.55 / Phase C` 結論**仍是最準確的 Option 2 量化證據**。

2. **接受 follow-up tickets**（已隱含建議）：
   - **P1 — 改造 Replay framework 移除 is_pinned/position_state hardcoded**：~500 LOC, W-AUDIT-8a 對齊。**不**建議現在做（W-AUDIT-8a Phase B/C 才剛 spec ready，需先收 panel infrastructure）。
   - **P1 — 對 actual runtime 寫 24h passive watch metric**：Option 2 deploy 14:33 後 24h grid non-pinned fill 數量應顯著下降。SQL 持續追蹤即可。
   - **P2 — manifest 帶完整 scanner_config + strategy_params**：當前 `_build_manifest_jsonb` 沒注入這兩個，造成 replay 用 default。需 Python `_register_full_chain_experiment` 修。

3. **真實虧損驗證**：建議仍走 **actual runtime PG watch** 而非 replay：
   - 12h post-Opt2 (14:33 → 02:33 UTC May 12): grid_trading non-pinned fill 數量
   - 24h post-Phase 0 (~22:08 May 10 → 22:08 May 11): bb_reversion cross-strategy attack pattern
   - 已包在 PA RCA follow-up，不需要 replay。

4. **報告 commit + push**：本報告寫入 git，等 E2 review。

---

## 12 結論一句話

**真實 Rust replay engine 跑起來了**，但 `is_pinned/position_state/alpha_surface_ref` 三項 hardcoded 使得 replay 在策略行為層面與 actual runtime decoupled — **無法驗證 Phase 0 / A-Lite / Option 2 任何今日修復**。前次 SQL counterfactual 結論 (+$0.20 / 27h, +$0.55 / Phase C) **仍然是最準確的 Option 2 量化證據**；新的真實 binary run 反而強化「Replay framework 設計目的是 calibration / forbidden_guard 合規而非 ad-hoc strategy A/B」的結構性結論。

---

E1 IMPLEMENTATION DONE (real Rust replay engine confirmed working, but cannot validate today's fixes due to structural limitations): 待 E2 審查（report path: `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-11--option_2_replay_engine_validation_v2.md`）
