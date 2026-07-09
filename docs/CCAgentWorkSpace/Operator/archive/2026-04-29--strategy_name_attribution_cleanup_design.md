# PA Design — `trading.fills.strategy_name` Attribution Cleanup

**Date**: 2026-04-29
**Trigger**: Operator 觀測 GUI Learning tab 24h fills 顯示 demo bucket 25 個 distinct `strategy_name`、live_demo 9 個。實測 PG 確認 cardinality 來自 Rust dispatch path 把動態 trace（funding rate / basis / peak / current PnL / dynamic stop pct / regime）拼進 `strategy_name`，而非寫到 `details` JSONB 或新欄位。
**Author**: PA (read-only design, no business code written)
**Pre-conditions**: HEAD 已含 V032 + ML/Dream local implementation（commit 53bff07）；engine PID 620724；engine binary 含 R2/R3 實作；Live 5 hardguard 永不觸碰。

---

## §1 Scope Audit — Rust Writer + Python SELECT

### §1.1 Rust dispatch path — 動態 strategy_name 寫入面

**核心結論**：Rust 唯一寫 `trading.fills.strategy_name` 的入口是 `database/trading_writer.rs:347-348/375` 的 `b.push_bind(strategy_name.as_str())`，consumer 是 `TradingMsg::Fill { strategy_name, .. }`（`database/mod.rs:340`）。`strategy_name` 在 `Fill` enum 變體裡是 `String`，沒有獨立 enum 化。所有 close path 都把「prefix:reason」**字面字串**塞進此欄位。

| Call site | 檔案 : 行 | 寫入字串模板 | 動態 / Static | 進入 fills.strategy_name 後形式 |
|---|---|---|---|---|
| **Entry path（5 個策略）** | | | | |
| ma_crossover open | `strategies/ma_crossover/strategy_impl.rs` (via OrderIntent.strategy) | `self.name()` = `"ma_crossover"` | static enum-like | `ma_crossover` |
| bb_reversion open | `strategies/bb_reversion/mod.rs` | `"bb_reversion"` | static | `bb_reversion` |
| bb_breakout open | `strategies/bb_breakout/mod.rs` | `"bb_breakout"` | static | `bb_breakout` |
| grid_trading open | `strategies/grid_trading/signal.rs:213-216` | `self.name()` = `"grid_trading"` | static | `grid_trading` |
| funding_arb open | `strategies/funding_arb.rs` | `"funding_arb"` | static | `funding_arb` |
| **Strategy-driven exit path（4 個策略發 Close action）** | | | | |
| funding_arb exit | `strategies/funding_arb.rs:402-405` | `format!("funding_arb_exit: rate={:.6} basis={:.3}%", funding_rate, basis_pct)` | **DYNAMIC**（10000+ 排列） | `strategy_close:funding_arb_exit: rate=-0.001352 basis=0.503%` |
| ma_crossover exit | `strategies/ma_crossover/strategy_impl.rs:257` | `"ma_reverse_cross"` | static | `strategy_close:ma_reverse_cross` |
| bb_reversion exit | `strategies/bb_reversion/mod.rs:458` | `"bb_mean_revert"` | static | `strategy_close:bb_mean_revert` |
| grid_trading exit | `strategies/grid_trading/signal.rs:206/238` | `"grid_close_short"` / `"grid_close_long"` | static | `strategy_close:grid_close_short`（含 prefix） |
| `step_4_5_dispatch` 套 prefix | `tick_pipeline/on_tick/step_4_5_dispatch.rs:1011, 1031, 1072, 1095` | `format!("strategy_close:{reason}")` | wrapper | — |
| **Risk-driven exit path（risk_checks.rs 6 條 + step_0_fast_track 4 條 + commands 2 條）** | | | | |
| HARD STOP | `risk_checks.rs:306-309` | `format!("HARD STOP: pnl {:.2}% <= -{:.2}%", pnl_pct, effective_sl)` | **DYNAMIC** | `risk_close:HARD STOP: pnl -6.00% <= -5.00%` |
| DYNAMIC STOP | `risk_checks.rs:327-330` | `format!("DYNAMIC STOP: pnl {:.2}% <= -{:.2}% (regime={}, atr={:?})", pnl_pct, dyn_stop, regime, atr_pct)` | **DYNAMIC** | `risk_close:DYNAMIC STOP: pnl -8.5% <= -7.2% (regime=trending, atr=Some(0.012))` |
| TAKE PROFIT | `risk_checks.rs:338-341` | `format!("TAKE PROFIT: pnl {:.2}% >= {:.2}% (regime={})", pnl_pct, tp_target, regime)` | **DYNAMIC** | `risk_close:TAKE PROFIT: pnl 5.20% >= 4.50% (regime=trending)` |
| TRAILING STOP | `risk_checks.rs:351-355` | `format!("TRAILING STOP: peak {:.2}% - current {:.2}% = ... locked {:.2}% >= floor {:.2}%", ...)` | **DYNAMIC**（6 浮點欄位） | `risk_close:TRAILING STOP: peak 8.46% - current 6.46% = 2.00% >= distance 2.00% (locked 6.46% >= floor 5.78%)` |
| TIME STOP | `risk_checks.rs:362-365` | `format!("TIME STOP: held {:.1}h >= limit {:.1}h (regime={})", ...)` | **DYNAMIC** | `risk_close:TIME STOP: held 24.0h >= limit 24.0h (regime=trending)` |
| PHYS-LOCK | `risk_checks.rs:386` + emit by `physical_micro_profit_lock_v2` | `format!("risk_close:{}", reason)` (reason ∈ static enum-like `phys_lock_gate4_giveback` / `phys_lock_gate4_stale_roc_neg`) | static | `risk_close:phys_lock_gate4_giveback` |
| HALT SESSION | `risk_checks.rs:407, 421` (HaltSession action) | `format!(...)` | DYNAMIC（halt 同樣動態） | `risk_close:halt_session_*` 系列 |
| `risk_close:` wrapping | `tick_pipeline/on_tick/helpers.rs:38-42` `build_risk_close_tag` 強制單前綴（防 RUST-DOUBLE-PREFIX-1 regression） | constant `"risk_close:"` | wrapper | — |
| FAST TRACK reduce-half | `tick_pipeline/on_tick/step_0_fast_track.rs:453, 467` | `"risk_close:fast_track_reduce_half"` | static | `risk_close:fast_track_reduce_half` |
| FAST TRACK close-all | `tick_pipeline/on_tick/step_0_fast_track.rs:570, 583` | `"risk_close:fast_track"` | static | `risk_close:fast_track` |
| IPC close symbol | `tick_pipeline/commands.rs:1039` | `"risk_close:ipc_close_symbol"` | static | `risk_close:ipc_close_symbol` |
| IPC close symbol (dispatch tag) | `tick_pipeline/commands.rs:1125` | `"risk_close:ipc_close_symbol"` | static | 同上 |
| **Audit / unattributed path** | | | | |
| Unattributed (F4 fix) | `event_consumer/unattributed_emit.rs:168` | `"unattributed:bybit_auto"` | static | `unattributed:bybit_auto` |

**寫入面總結**：
- Open path：5 個 enum-like 字串（`ma_crossover` / `bb_reversion` / `bb_breakout` / `grid_trading` / `funding_arb`）— 已 clean。
- Close path（共 16 個 emit 點）：
  - **9 個 static**（含 `risk_close:` prefix wrapper）— 也算 enum-like
  - **7 個 dynamic format!()** — 是 cardinality inflation 的根源：
    1. `funding_arb_exit: rate={:.6} basis={:.3}%`
    2. `HARD STOP: pnl X <= -Y`
    3. `DYNAMIC STOP: pnl X <= -Y (regime=R, atr=Z)`
    4. `TAKE PROFIT: pnl X >= Y (regime=R)`
    5. `TRAILING STOP: peak X - current Y = Δ >= dist (locked L >= floor F)`
    6. `TIME STOP: held Hh >= limit Lh (regime=R)`
    7. `halt_session_*` 系列（DYNAMIC）

---

### §1.2 Python / SQL SELECT scope — `trading.fills.strategy_name` 消費者

**分類原則**：分四級風險
- 🔴 **直接破壞**：依賴等值 match 或 enum 規範、被 dynamic format 完全漏掉
- 🟡 **prefix LIKE 受影響**：用 `LIKE 'risk_close:phys_lock_%'` 等 pattern；prefix 部分穩定但動態 suffix 影響統計
- 🟢 **Already-immune**：用 entry path strategy_name + dynamic suffix 不進結果（FIFO pair）
- 🔵 **passthrough**：純 raw return 給 GUI，不解析語意

| 類別 | Call site | 檔案 : 行 | SELECT 形式 | 風險 | 備註 |
|---|---|---|---|---|---|
| **DB writer in Rust** | trading_writer.rs（FILL INSERT） | `database/trading_writer.rs:327, 347, 375` | INSERT 寫入面 | 寫入根源 | 不算 SELECT，標出方便 cross-ref |
| **GUI passthrough** | strategy_read_routes.fills | `strategy_read_routes.py:606-617` | `SELECT ts, fill_id, symbol, side, qty, price, fee, realized_pnl, strategy_name FROM trading.fills` | 🔵 | 直接 return，GUI 顯示完整字串。Operator 看到 25 個 distinct 就在這 |
| **GUI passthrough** | live_session_account_routes 平倉歷史 | `live_session_account_routes.py:387-409` | 同上 + WHERE engine_mode IN ('live', 'live_demo') | 🔵 | live tab 平倉清單；同樣顯示完整字串 |
| **GUI summary** | agents_routes_helpers `_fetch_shadow_vs_live_summary` | `agents_routes_helpers.py:367-379` | GROUP BY engine_mode bucket（demo / live_demo），**不**讀 strategy_name | 🟢 | 不依賴 strategy_name shape |
| **GUI today intents** | agents_routes_helpers `_fetch_today_intent_counts_by_strategy` | `agents_routes_helpers.py:256-261` | `SELECT strategy_name, COUNT(*) FROM trading.intents` GROUP BY strategy_name | 🟢 | trading.intents 寫入只 5 個 enum 值（entry only），不受 close path 動態 reason 影響 |
| **History / 7d edge** | strategist_history_routes._compute_seven_day_edge_effect | `strategist_history_routes.py:312-326` | `WHERE strategy_name = %s`（whitelisted `_ALLOWED_STRATEGIES`：5 個 strategy 名） | 🔴 **完全 miss close** | 等值 match 永遠不命中 `strategy_close:*` / `risk_close:*` 行 → fill_count / net_pnl / win_rate **永遠只算 entry**（entry 通常 realized_pnl=0）→ 數據從一開始就不對 |
| **Shadow fills view** | shadow_fills_routes（讀 `learning.decision_shadow_fills`） | `shadow_fills_routes.py:200-216` | GROUP BY strategy_name | 🟢 | 不是 trading.fills，是 shadow 表 |
| **ML training（V031 view）** | sql/migrations/V031__ml_dream_edge_unblock.sql | view `learning.mlde_edge_training_rows` 讀 `trading.intents` (不讀 fills) + 用 CASE WHEN normalize 為 5 個 enum | view 已自帶 normalize | 🟢 | 已 immune，但 **base table 是 intents 不是 fills** |
| **Realized edge stats** | realized_edge_stats._pair_round_trips | `realized_edge_stats.py:241, 268-418` | FIFO pair entry/exit；exit prefix detect → entry strategy_name 進 RoundTripRecord | 🟢 | 已 immune（entry path 永遠 5 enum 之一） |
| **realized_edge_stats** | exclude unattributed | `realized_edge_stats.py:241` | `f.strategy_name NOT LIKE 'unattributed:%%'` | 🟡 | 用 prefix 過濾 audit row，**OK** |
| **canary_promoter** | check_disagreement_count | `canary_promoter.py:160` | `WHERE strategy_name = %s` | 🟢 | 讀 `learning.decision_shadow_exits`（V021 表，不是 fills；那邊 strategy_name 是 entry 5 enum） |
| **healthcheck [4]** phys_lock_runtime | `passive_wait_healthcheck/checks_ipc_edge.py:60, 66` | `LIKE 'risk_close:phys_lock_%'` | 🟡 | prefix 對 — wrap 後是 `risk_close:phys_lock_*`，**仍會 match**；count rate 不受影響但 raw text reason suffix 不解析 |
| **healthcheck [5]** RETIRED | `checks_ipc_edge.py:106, 112` | `LIKE 'risk_close:COST EDGE%'` | 🟡 | 已死 endpoint（COST EDGE 已退役，永遠 0）。retain check id 穩定，建議保 |
| **healthcheck [6]** TRAILING STOP fire | `checks_ipc_edge.py:125` | `LIKE 'risk_close:TRAILING STOP%'` | 🟡 | match 完整 dynamic format（`TRAILING STOP: peak ...`）prefix 部分；count rate 對 |
| **healthcheck [11]** counterfactual clean window | `checks_strategy.py:685-689` | `SELECT strategy_name, COUNT(*) FROM learning.exit_features GROUP BY strategy_name` | 🟢 | 不讀 fills，讀 exit_features（entry strategy_name）|
| **healthcheck [12]** bb_breakout entries | `checks_strategy.py:236` | `WHERE strategy_name = 'bb_breakout'` | 🟢 | entry path，等值匹配安全 |
| **healthcheck [16]** unattributed ratio | `checks_engine.py:601, 670` | `LIKE 'unattributed:%'` | 🟡 | 同上，audit row 過濾 |
| **healthcheck [Xa] dust spiral** | `checks_engine.py:283, 383` | `LIKE 'risk_close:fast_track%'` AND `realized_pnl=0` | 🟢 | static prefix 完整 |
| **healthcheck [21]** order/fill drift | `checks_engine.py:670, 762, 1101-1103` | `LIKE 'risk_close:%'` | 🟢 | 大 prefix 不受 dynamic suffix 影響 |
| **healthcheck [27, 30, 31, 33...]** | `checks_*.py` 各 | 多種 LIKE / GROUP BY | 🟡 | 多處 prefix-based filter，與當前格式相容 |
| **research scripts** | `helper_scripts/research/shadow_disagreement_breakdown.py:106, 122` | `GROUP BY strategy_name, engine_mode` / `reason` | 🟡 | 偏 ad-hoc audit，cardinality 影響可讀性但結果不錯 |
| **research scripts** | `helper_scripts/research/exit_features_summary.py:132` | GROUP BY strategy_name | 🟢 | exit_features 表 |
| **research scripts** | `helper_scripts/research/exit_threshold_calibrator.py:167` | comment 提及 strategy_name stratification | 🟢 | exit_features |
| **counterfactual replay** | `helper_scripts/db/counterfactual_exit_replay.py:719` | GROUP BY strategy_name | 🟢 | exit_features |
| **GUI agent-tracker** | `static/js/agent-tracker.js:530, 583, 591` | 直接顯示 fill.strategy_name | 🔵 | 影響 UX 顯示而非計算 |
| **dream_engine** | `local_model_tools/dream_engine.py:190-195` | `FROM learning.mlde_edge_training_rows GROUP BY strategy_name, ...` | 🟢 | view 已 normalize |
| **mlde_shadow_advisor** | `program_code/ml_training/mlde_shadow_advisor.py` | 讀 V031 view 的 `strategy_name` | 🟢 | view 已 normalize |
| **linucb_trainer** | `program_code/ml_training/linucb_trainer.py:59-88` | 讀 V031 view | 🟢 | view 已 normalize |

**Python SELECT scope 總結**：
- **唯一真正破壞點 = `strategist_history_routes._compute_seven_day_edge_effect()` 等值 match**（🔴）→ 7d edge effect endpoint 對 close fills 完全失效（結算永遠拿 entry 的 0 元 realized_pnl，**不是**真實 7d 成果）。
- 其他 18+ 個 call site 全部已 prefix-aware 或讀 normalized view 或讀 entry path 的 strategy_name → **🟡 / 🟢 / 🔵 屬於可接受**
- GUI passthrough（🔵）= 視覺髒，但「顯示 25 個 row 各帶 reason」對 operator 反而是有用的 debug 訊號

---

## §2 三方案比較表

### §2.1 方案 A — schema migration 加新欄位 `exit_reason`

**核心**：strategy_name 強制只寫 enum-like prefix；動態 trace 寫到新增 TEXT 欄位 `trading.fills.exit_reason`（nullable）。

| 維度 | A 方案 |
|---|---|
| **Schema 變更** | ✅ V033 ADD COLUMN exit_reason TEXT NULL（小 chunk-friendly migration）+ Guard A/B per CLAUDE.md §七 強制規則 |
| **Rust writer 改動行數估計** | ~80–120 LOC：(a) `database/mod.rs::TradingMsg::Fill` 加 `exit_reason: Option<String>` 欄位（5 處 destructure pattern 需更新）(b) `trading_writer.rs::INSERT` 新增 column bind（22→23 col）(c) `tick_pipeline/on_tick/helpers.rs::build_risk_close_tag` 改成 `build_close_tags() -> (canonical_name, exit_reason)` 拆兩值 (d) 16 個 emit 點各改 1-2 行（funding_arb / risk_checks / step_4_5_dispatch / step_0_fast_track / commands / unattributed_emit）|
| **Python call site 改動估計** | 0–4 行：strategist_history_routes._compute_seven_day_edge_effect 仍可繼續用 `WHERE strategy_name = %s` 但**現在會命中**（因 strategy_name 規範化後值就是 `funding_arb`）；no-op 不需動。`exit_reason` 新欄位是 opt-in 讓未來消費 |
| **GUI 影響** | passthrough 變短：strategy_name 顯示 `funding_arb` + 旁邊 cell 顯示 reason `funding_arb_exit: rate=...`；operator 仍能看 reason 但更整齊 |
| **Backward compat**（既有 ~263k 歷史 fills 含 dynamic format） | 歷史 row：strategy_name 保留 `risk_close:TRAILING STOP: peak X...`；exit_reason=NULL。新 row：strategy_name=`ma_crossover`、exit_reason=`TRAILING STOP: peak X...`。下游 prefix LIKE 對歷史 row 仍 match；新 row 不再 match 但因為新格式統計值已歸到 normalized strategy_name → 不靠 LIKE 也能算 |
| **healthcheck 影響** | 4–8 個 LIKE-based check 需升級寫**雙語法**支持新舊資料（`strategy_name LIKE 'risk_close:phys_lock_%' OR exit_reason LIKE 'phys_lock_%'`）。已寫入歷史的 row 永遠靠 LIKE；新 row 靠 exit_reason → 共存 7d 後完全切到新邏輯 |
| **ML pipeline 影響** | V031 mlde_edge_training_rows 讀 `trading.intents`（非 fills）→ **0 改動**。realized_edge_stats `_pair_round_trips` 不依賴 fills.strategy_name 為 enum（用 prefix detect exit），維持兼容 |
| **E4 新測試 case 數** | ~25 個：(a) Rust：每個 emit 點 1 個（16 個）+ TradingMsg::Fill exit_reason None default（4 個）(b) Python：strategist_history.effect 7d window 對 normalized strategy_name 命中（3 個）(c) Migration idempotency（2 個 per CLAUDE.md §七 強制） |
| **rollback complexity** | 簡單：`ALTER TABLE trading.fills DROP COLUMN exit_reason`；Rust 端新格式 commit revert；歷史 row 永不變動 |
| **risk** | 中等：TradingMsg::Fill enum 變動會影響 5+ 個 destructure callsite（`paper_state` / `event_consumer` / `tests`），漏一處 = 編譯失敗 (compile-time enforce 反而是優點) |

### §2.2 方案 B — 動態 trace 寫到既有 `details` JSONB

**核心**：strategy_name 同 A 規範化；動態 trace 寫到既有 `trading.fills.details` JSONB（V003 line 284 已建欄位但 trading_writer 從不寫）。

| 維度 | B 方案 |
|---|---|
| **Schema 變更** | 0：`details` JSONB 已存在於 V003。但需新增 GIN index 才能高效查詢（V033 新增 index 不算 schema change） |
| **Rust writer 改動行數估計** | ~100–150 LOC（比 A 多 ~30 LOC）：(a) `database/mod.rs::TradingMsg::Fill` 加 `details: Option<serde_json::Value>` (b) `trading_writer.rs::INSERT` 把 22 col 改 23 col（含 details JSONB） (c) helper `build_close_tags` 改成 (canonical_name, details: serde_json::json!({"exit_reason": "...", "regime": "...", "rate": ...}))；JSON 結構需設計 +1 spec 文件 |
| **Python call site 改動估計** | 同 A，~0 行改動（healthcheck 仍可用 LIKE 對歷史 row）|
| **GUI 影響** | passthrough 行為同 A；額外好處：JSONB 可 selectively render 多個字段（exit_reason / regime / rate），UX 更彈性 |
| **Backward compat** | 同 A：歷史 row `details=NULL`、strategy_name 仍是長字串；新 row 拆兩處。LIKE-based healthcheck 仍工作 |
| **healthcheck 影響** | 比 A 略複雜：需教 healthcheck 怎麼讀 JSONB（`details->>'exit_reason' LIKE 'TRAILING STOP%'`）— GIN index 速度足夠但語法繁瑣 |
| **ML pipeline 影響** | V031 0 改動；下游若想 mining details 字段需 JSONB extract（`details->>'regime'`），但這算未來進步 |
| **E4 新測試 case 數** | ~30 個（比 A +5）：JSON schema validation 額外驗 |
| **rollback complexity** | 簡單：Rust revert；details=NULL 歷史 row 永不變動 |
| **risk** | 中等：JSONB schema 隨意比 column 容易 drift；需要強制 spec（`docs/references/...exit_details_schema.md`）|

### §2.3 方案 C — 純 view 層解決（不動 writer）

**核心**：加 view `trading.fills_normalized_strategy` 用 SQL `regexp_replace` / CASE WHEN 把 prefix extract 成 5 個 enum。Rust writer 不動、歷史不動、未來 row 仍累積亂。

| 維度 | C 方案 |
|---|---|
| **Schema 變更** | 0：純 view |
| **Rust writer 改動行數估計** | 0 |
| **Python call site 改動估計** | ~10–20 行：所有破壞點（特別 strategist_history.effect）改 `FROM trading.fills` → `FROM trading.fills_normalized_strategy`，可能 8+ 處 |
| **GUI 影響** | 無改動（GUI 仍從 raw fills 讀 raw strategy_name）→ 25 個 distinct 仍存在；operator 視覺髒 unchanged |
| **Backward compat** | 歷史完美兼容（view 對所有 row 工作） |
| **healthcheck 影響** | 雙寫雙讀困境：healthcheck 要選讀 view（normalized）還是讀 raw fills（含 cardinality）？需逐個 check 決定 |
| **ML pipeline 影響** | 0 |
| **E4 新測試 case 數** | ~15 個：view 規範化 5 strategy → 每個 prefix path 1 case |
| **rollback complexity** | 最簡單：`DROP VIEW`，無資料變動 |
| **risk** | **長期高**：未來資料污染繼續累積；命名 drift 可能性最大；`docs/references` 易過期；下游必須選對表名才不踩雷 |

---

## §3 推薦方案

**推 A（schema migration + new column `exit_reason`）**。

理由：

1. **Single Source of Truth**：strategy_name 永遠只是 5 個 enum value（`ma_crossover` / `bb_reversion` / `bb_breakout` / `grid_trading` / `funding_arb`）+ 系統路徑（`unattributed:bybit_auto`），exit_reason 是 trace。語意清楚分離。
2. **修真實破壞**：strategist_history.effect 端點 7d edge effect **立即正確**（無需改 SQL）— 純粹靠 strategy_name 規範化 → enum match 自動命中。
3. **column-level type safety**：vs B JSONB 結構鬆散；vs C view-only 容易被 bypass。Rust enum + Python 預期型 vs string-pattern 容易做。
4. **Forward-compat**：未來若需要拆更細（exit_reason structured fields like `regime`, `pnl_pct`, `peak_pct`），可逐步加新 column / 拆 sub-fields；JSONB 路徑反而需要 JSON schema migration 麻煩。
5. **healthcheck rollover 7d 自然**：歷史 row 走 LIKE `strategy_name LIKE 'risk_close:phys_lock_%'`、新 row 走 `exit_reason LIKE 'phys_lock_%'`；雙語法 7d 後 phase out 老語法。
6. **CLAUDE.md §二 治理對照**：原則 #8（交易可解釋）— normalized 的 strategy_name + 結構化 exit_reason 比 dynamic format 字串更容易做歸因 / 重建決策路徑。
7. **§七 SQL guard 強制無壓力**：V033 是 ADD COLUMN，Guard A/B template 已存在（V021 / V023 範例 in-tree）。

**反方案 B 的關鍵 reason**：JSONB schema 沒 enforce、未來會 drift；GIN index 維護成本；測試代碼複雜。為了避免單一新 column，付出設計開銷不值得。

**反方案 C 的關鍵 reason**：根源 cardinality inflation 持續發生；將來再 audit 仍會踩同樣陷阱；未來自動化 / Linear 工單規模化時必踩 30+ distinct strategy_name 的雷區。

---

## §4 工作分解 — E1 Implementation Checklist

**前置**：派發 E1 前必跑 `git fetch && git branch -r | grep 'strategy_name'`（per memory `feedback_fetch_before_dispatch`）以避撞已開 branch。

### W1（並行可派 4 個 sub-task，PA Worktree pattern）

#### W1-T1 — Rust schema + TradingMsg::Fill enum extension
**範圍**：
- (a) 寫 `sql/migrations/V033__fills_exit_reason.sql`：ADD COLUMN exit_reason TEXT NULL + Guard A 對 trading.fills + Guard B 對 column type + COMMENT + Index `idx_fills_exit_reason_prefix(exit_reason text_pattern_ops) WHERE exit_reason IS NOT NULL`（~80 LOC SQL）
- (b) 改 `rust/openclaw_engine/src/database/mod.rs::TradingMsg::Fill` 加 `exit_reason: Option<String>` 欄位（~3 LOC）
- (c) 改 `rust/openclaw_engine/src/database/trading_writer.rs::FILL_COLS = 23` + INSERT 22→23 col bind（~10 LOC）
- (d) 在 `tick_pipeline/on_tick/helpers.rs` 新 helper `pub(crate) fn build_close_tags(reason: &str) -> (String, Option<String>)` 把 raw reason 拆成 (canonical_strategy_name, opt_exit_reason)；canonical 的 5 個 enum 從上下文 strategy_name 進去（**Caller 必須知道 entry strategy 是哪 5 個之一**）
- (e) 5 個 destructure callsite 全更新（paper_state / event_consumer / unattributed_emit / 2 tests）
- (f) cargo build 綠 + lib test 從 2361 變 2361+ ~10 個

**LOC 估**：~120 LOC Rust + 80 LOC SQL = **~200 LOC**
**E1 instance**：worktree 隔離（Rust 跨檔 + 5 destructure callsite）
**ETA**：~8h（包括建 V033 migration test）

#### W1-T2 — Caller 16 個 emit 點改寫
**範圍**：每個 close emit 點都從「拼 dynamic format 進 strategy_name」改成「strategy_name = 5 enum 之一 + exit_reason = 動態 trace」
- 1 個 funding_arb_exit（funding_arb.rs）
- 6 個 risk_checks.rs（HARD/DYNAMIC/TRAILING/TIME/TAKE PROFIT/halt session）
- 4 個 step_0_fast_track.rs（fast_track_reduce_half × 2 + fast_track × 2）
- 2 個 commands.rs（ipc_close_symbol × 2）
- 2 個 step_4_5_dispatch.rs（strategy_close prefix 套法 → 改成 strategy_name=entry_name + exit_reason=reason）

**LOC 估**：~150 LOC（每 emit ~5–10 LOC 含上下文 entry strategy 注入）
**E1 instance**：建議 isolation worktree（多檔同改、avoid 撞 W1-T1 的 destructure 點）
**ETA**：~10h

#### W1-T3 — Python strategist_history.effect 適配 + GUI passthrough 微調
**範圍**：
- 確認 strategist_history.effect 的 SQL `WHERE strategy_name = %s` 仍可工作（值 = `funding_arb` 等 enum 名），新增 unit test 釘死 7d window 對 close row 命中（修前永遠 0 / 修後正確 SUM realized_pnl）
- GUI passthrough 兩處（strategy_read_routes / live_session_account_routes）順便加 exit_reason 欄位 return（可選，UX 改進）
- 改 tab-live.html / tab-demo.html 渲染 fill row：`f.strategy_name + (f.exit_reason ? ' (' + f.exit_reason + ')' : '')` 給 operator 仍能看到 reason

**LOC 估**：~50 LOC Python + ~20 LOC JS
**E1 instance**：主樹（檔案不重疊 W1-T1/T2）
**ETA**：~3h

#### W1-T4 — healthcheck 雙語法升級
**範圍**：
- `passive_wait_healthcheck/checks_ipc_edge.py` line 60, 66, 106, 112, 125 — 5 個 LIKE 改寫成 `WHERE (strategy_name LIKE '...' OR exit_reason LIKE '...')`
- `checks_engine.py` line 283, 383, 670, 762, 1101-1103 — 6 個同上
- 確保 7d window 後（歷史 row 全部 expire）只走新 path
- 新增 [38] 健檢：`strategy_name_cardinality_drift` — `SELECT COUNT(DISTINCT strategy_name) FROM trading.fills WHERE ts > now() - interval '24 hours'`，**>10 = WARN, >20 = FAIL**（防 regression 後再次出現 cardinality 爆炸）

**LOC 估**：~80 LOC
**E1 instance**：主樹
**ETA**：~3h

### W2（W1 全綠後）

#### W2-T1 — E2 review + E4 regression
- E2：~2h（cargo build / pytest / SQL guard idempotency double-run）
- E4：~3h（lib + integration + new healthcheck cron 跑一次）

### 全鏈派發架構建議

| 子任務 | E1 instance | isolation | 依賴 | ETA |
|---|---|---|---|---|
| W1-T1 Rust schema + TradingMsg::Fill | E1-Alpha | **YES**（Rust 跨檔 destructure）| 無 | 8h |
| W1-T2 16 emit point 改寫 | E1-Beta | **YES**（多檔同改）| W1-T1 結束 schema 後可同步開（subset 編譯）| 10h（可與 T1 後段重疊 ~6h） |
| W1-T3 Python adaptation | E1-Gamma | NO 主樹 | W1-T1 + W1-T2 後 | 3h |
| W1-T4 healthcheck upgrade | E1-Delta | NO 主樹 | 同 W1-T3 | 3h |

**Wall-clock**：~16h sequential / **~10h parallel**（T1 + T2 重疊大半，T3/T4 並行）+ E2/E4 5h = **~15h 全鏈**

---

## §5 風險清單

### §5.1 歷史資料 backfill 路徑

**選項 1（推薦）**：歷史不 backfill。新 row 走新格式、舊 row 維持原格式，靠 healthcheck 雙語法 7d phase out。LIKE pattern 對歷史可繼續運作。實際成本最低、rollback 完美無痕。

**選項 2**：寫 backfill SQL `regexp_replace` 把 strategy_name 拆成 (canonical, exit_reason) 2 column。但 ~263k row 寫操作對 hypertable 有成本；若需要 audit / mining 歷史 ML 訓練資料推薦做。**注意**：backfill SQL 需要在獨立 V034 migration 寫成 idempotent + Guard pattern（`WHERE exit_reason IS NULL`）。**P3 backlog item**，非 W1 必做。

### §5.2 Rollback 路徑

- **L1 Rust commit revert**：直接 git revert W1-T2 的 commit，編譯 + lib test 仍綠（因為 schema 仍多 1 column nullable，`exit_reason` 寫 None 兼容）
- **L2 Schema rollback**：跑 `ALTER TABLE trading.fills DROP COLUMN exit_reason; DROP INDEX idx_fills_exit_reason_prefix;`（5 sec 執行）
- **L3 完整 rollback**：L1 + L2 + 跑 `git revert` 全 W1 wave

### §5.3 灰度部署

- **不需要灰度**：本 wave 對 trading hot path 0 邏輯改動（純資料拆欄）。close emit 對下游 fill 投遞語意不變。
- **Live 端未啟動**：當前 live 5 hardguard 全保（authorization.json schema v1→v2 仍阻擋）— 任何 wave 部署均純 demo / live_demo / paper 影響。
- **Demo restart**：W1 完成後一次 `restart_all.sh --rebuild` 即生效；engine PID rollover 不重置 21d demo 穩定時鐘（per §三 規則）。

### §5.4 設計風險

- **R-A1**：W1-T2 16 個 emit 點若漏 1 個 emit 點 → 該 close path 仍進 dynamic strategy_name（pre-fix 行為）→ healthcheck [38] cardinality drift 會 WARN catch；E2 必逐一 grep verify
- **R-A2**：TradingMsg::Fill enum 加欄位 → destructure callsite 編譯 enforced；漏一處 = compile fail，**安全**
- **R-A3**：`build_close_tags` 需要 caller 傳 entry strategy name；若 caller path 不知道 entry strategy（例如 fast_track close all 時 close 的 position 由不同 strategy 開）→ 需從 `paper_state.get_position(symbol).strategy` 取；確保 5 close path 都能找到 entry strategy
- **R-A4**：`unattributed:bybit_auto` 是 audit row 不歸入 5 enum，保持原 strategy_name 不規範化 → 加白名單跳過 cardinality healthcheck
- **R-A5**：halt_session_* 系列 reason 是 dynamic（`risk_close:halt_session_*` 後接 trace）；caller 路徑不一定知道 entry strategy（halt 是全帳戶 close）→ strategy_name 寫 `risk_close:halt_session`（fallback prefix），exit_reason 寫完整 trace。**特殊 case**，此 path 不規範到 5 enum

---

## §6 healthcheck 建議

### §6.1 必加 — `[38] strategy_name_cardinality_drift`

```python
def check_strategy_name_cardinality_drift(cur) -> tuple[str, str]:
    """[38] cardinality regression detector for trading.fills.strategy_name.

    Background / 背景:
      Pre-2026-04-29 close path emitted dynamic format!() into strategy_name
      (`risk_close:TRAILING STOP: peak X - current Y = ...`) creating 25+
      distinct values per 24h. Post-fix should normalize to ≤7 enum values:
      ma_crossover / bb_reversion / bb_breakout / grid_trading / funding_arb /
      unattributed:bybit_auto / risk_close:halt_session.

      若新 emit 點漏改、cardinality 重新爆炸 → cron 自動 catch。
    """
    sql = """
        SELECT COUNT(DISTINCT strategy_name)
        FROM trading.fills
        WHERE ts > now() - interval '24 hours'
          AND engine_mode IN ('demo', 'live_demo', 'live')
    """
    n_distinct = _scalar(cur, sql)
    if n_distinct > 20:
        return ("FAIL", f"24h distinct strategy_name = {n_distinct} > 20 — emit point regression!")
    if n_distinct > 10:
        return ("WARN", f"24h distinct strategy_name = {n_distinct} > 10 — possible regression / new strategy")
    return ("PASS", f"24h distinct strategy_name = {n_distinct} (≤10 expected)")
```

放 `passive_wait_healthcheck/checks_strategy.py`（與 [11], [12] 共族）。cron 每 6h 跑一次（已在 cron schedule 內，無需新加）。

### §6.2 已有 healthcheck 升級

- `[4]` `phys_lock_runtime` — 目前 `LIKE 'risk_close:phys_lock_%'`；fix 後新 row 是 `strategy_name = 'risk_close:phys_lock_gateN_*'` 仍存（phys_lock 屬 risk_close 路徑保 prefix），不需改。
- `[5]` `RETIRED COST EDGE` — 目前 `LIKE 'risk_close:COST EDGE%'`；fix 後 COST EDGE 已退役且不會 emit 任何新 row，**不需改**（只是名字 historical reference）。
- `[6]` `TRAILING STOP fire` — 目前 `LIKE 'risk_close:TRAILING STOP%'`；fix 後 TRAILING STOP 進 exit_reason、strategy_name 是 5 enum 之一 → 需升級雙語法
- `[Xa] dust spiral` — 目前 `LIKE 'risk_close:fast_track%'`；fast_track 是 static prefix，**不需改**

### §6.3 可選 — `[39] exit_reason_coverage`

驗 close fills 必有 exit_reason 寫入：`SELECT COUNT(*) FROM trading.fills WHERE realized_pnl != 0 AND ts > now() - interval '24 hours' AND exit_reason IS NULL AND strategy_name NOT LIKE 'unattributed:%'` — 應該 = 0；不為 0 = emit 點漏接 exit_reason。

---

## §7 治理對照

- **CLAUDE.md §二 #1 單一寫入口**：✅ 不變，trading_writer.rs 仍是唯一入口
- **#3 AI 輸出 ≠ 命令**：✅ 不影響 lease / decision path
- **#4 策略不繞風控**：✅ risk_close path 不變，只是 trace 拆欄
- **#5 生存 > 利潤**：✅ HARD/DYNAMIC STOP 邏輯零改動
- **#6 失敗默認收縮**：✅ exit_reason=None default 安全 fallback
- **#8 交易可解釋**：⭐ **直接強化** — strategy_name=enum + exit_reason=structured trace 比 dynamic format 字串更容易 audit / replay
- **§四 5 項 live 硬邊界**：✅ 0 觸碰（authorization / mainnet env / live_reserved 全保）
- **§七 跨平台**：✅ pure SQL + Rust + Python；無平台特定
- **§七 雙語注釋**：W1 必含 — `TradingMsg::Fill.exit_reason` doc comment + V033 migration 中英對照
- **§七 SQL guard A/B**：W1-T1 Mandatory（V033 模板從 V021 複製即可）
- **§七 「被動等待 TODO 必附 healthcheck」**：W1-T4 [38] cardinality drift 自動 catch regression，免後續自查

---

## §8 沒做的事（E1/E2 領域）

- 沒寫任何 Rust / Python 業務代碼（純 PA design）
- 沒建立 V033 migration（W1-T1 由 E1 寫）
- 沒派 sub-agent（純 PA 主 agent 串行讀+寫）
- 沒跑 cargo test / pytest
- 沒擴範圍到 V032 mlde_param_applications schema / live authorization v2 / G2-01 fee monitoring

---

## §9 教訓備忘

- **「動態 trace 拼進 enum 欄位」是反模式**：strategy_name 設計上就是 enum 維度（aggregation key），funding_arb_exit / TRAILING STOP 動態 reason 屬 trace 維度（free-text payload）。混在一起破壞下游 GROUP BY / equality match / cardinality 衛生 — 是「`feedback_no_dead_params`」的反模式變體。
- **Cardinality healthcheck 應該成為標配**：對任何「列 enum 的 column」（如 strategy_name / risk_verdict / exit_source / engine_mode），cron 6h 跑一次 distinct count 檢查 = 1 SQL 即可釘死「字面值規範」這條看不見的 contract，比逐個 emit 點 grep 強。
- **V031 view-layer normalize 是好但不夠**：V031 為 ML pipeline 補了 view 層 CASE WHEN normalize（線上 7 enum）但只蓋 trading.intents 不蓋 fills；fills.strategy_name 仍 raw → operator 視角有 25 個 distinct。**Lesson**：view-layer fix 適合「不能改 writer」場景；本 audit 顯示有條件改 writer 時應從根 normalize，view 是次選。
- **historical row backfill 應該是 P3 不是 P0**：歷史 ~263k row 含舊格式不影響新邏輯運作（healthcheck 雙語法 7d phase out + raw row 仍 LIKE-able 對 audit）；backfill 工作量不對應收益。

---

## §10 Summary（給 PM）

| 項目 | 答案 |
|---|---|
| **推薦方案** | **A**（schema migration + new column `exit_reason`） |
| **理由** | strategist_history.effect 真實破壞 + 16 emit 點規範 + ML pipeline 已 immune + healthcheck 雙語法 7d 自然 phase out + CLAUDE.md §二 #8 強化 |
| **N 個檔案** | 12（Rust 6 + Python 4 + SQL 1 + JS 1） |
| **估計總 LOC** | ~430（Rust 270 + Python 90 + SQL 80）|
| **估計總時間** | ~15h（並行 4 sub-task ~10h + E2/E4 ~5h） |
| **派發**：4 sub-task（W1-T1/T2/T3/T4），W1-T1+T2 必 worktree isolation；W1-T3/T4 主樹並行 |
| **新增 healthcheck** | [38] strategy_name_cardinality_drift（必加）+ [39] exit_reason_coverage（可選） |
| **歷史 backfill** | 不做（P3 backlog） |
| **報告路徑** | `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-29--strategy_name_attribution_cleanup_design.md` |
