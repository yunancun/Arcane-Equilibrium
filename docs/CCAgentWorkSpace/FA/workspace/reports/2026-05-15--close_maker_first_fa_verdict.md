# FA 功能 + 16 條根原則合規驗證 — close-maker-first refactor

**Auditor**：FA (Functional Auditor)
**Date**：2026-05-15
**Scope**：將平倉路徑（`tick_pipeline/commands.rs:792` hard-coded `"market"`）按 exit_reason 白名單改為 maker-first；mirror EDGE-P2-3 Phase 1a entry-only 部署模式
**SSOT 對照**：`CLAUDE.md` §二（16 根原則）+ §四（硬邊界）+ `SPECIFICATION_REGISTER.md` v2026-05-15 + `docs/references/2026-04-24--postonly_design_intent.md`

> 註：FA agent 因 system-reminder 未直接 Write，本檔由主會話按 FA agent 返回原文存檔，內容為 FA 視角輸出。

---

## 1. Whitelist 業務分類認可 / 反對（per exit_reason）

| exit_reason | FA 分類 | 來源 | 認可 / 反對 / Conditional | 理由 |
|---|---|---|---|---|
| `grid_close_short` | strategic_close（grid 翻轉信號）| `grid_trading/signal.rs:316` (idx<prev_idx 且 cur_inventory<0) | **APPROVED** | 與 entry signal 同源同步 (`StrategyAction::Close`)；非風控、非緊急；與 entry 用同一 `use_maker_entry` + `maker_price_offset_bps` + `maker_timeout_ms` 構造合理 |
| `grid_close_long` | strategic_close（grid 翻轉信號）| `grid_trading/signal.rs:348` | **APPROVED** | 同上 |
| `bb_mean_revert` | **same-strategy close（非跨策略）** | `bb_reversion/mod.rs:629` `Some(_is_long)` exit branch | **APPROVED**（更正背景假設）| **背景假設「bb_mean_revert 是跨策略信號 → 平 grid/ma 倉」不準確**。Post Option A-Lite (commit 2026-05-11) 已加 `ctx.position_state.owner_strategy == self.name()` filter（`cross_strategy_attribution_integrity.rs:13`），cross-strategy 倉位 skip exit 全路徑；此 reason 100% 是 bb_reversion 在自己倉位 (`percent_b ∈ [0.2,0.8]`) 觸發的 mean-reversion exit。屬策略級可延遲，maker-first 合理 |
| `phys_lock_gate4_giveback` | **strategic_close (profit-protection)，非 risk_close** | `position_risk_evaluator.rs:341` 註釋 `risk_close:phys_lock_gate4_*` | **APPROVED with named carve-out** | 雖然 tag 帶 `risk_close:` 前綴（`RUST-DOUBLE-PREFIX-1` 為 healthcheck `LIKE 'risk_close:phys_lock_%'` 設計），語義上是「peak ATR 後 giveback 達閾值 → 鎖利」，屬 §5.16 portfolio-level profit lock，**非 §5.9 hard-stop**。原則 #4 不被觸碰（見 §4 條目）|
| `phys_lock_gate4_stale_roc_neg` | strategic_close (profit-protection) | 同上 | **APPROVED** | 同 giveback；ROC<0 + peak 停滯 = 利潤蒸發護盤，非生存風控 |
| `ma_reverse_cross` | strategic_close（MA 反向交叉信號）| `ma_crossover/strategy_impl.rs` (`Close` reason) | **APPROVED** | 同 grid 翻轉性質；趨勢信號逆轉，非緊急 |
| `bw_squeeze` | strategic_close（bb_breakout 帶寬塌陷）| `bb_breakout/mod.rs` + tests:556 | **CONDITIONAL** | 樣本量極低（demo 7d=1）。**單條 carve-out**：bb_breakout 5 close 樣本月度低於 30 之前，先入 whitelist 但 healthcheck 上 `bb_breakout_close_maker_fill_rate` 設 `min_samples_gate=30`（樣本不足 → NEUTRAL 而非 WARN），避免單筆 outlier 干擾 |
| `pctb_revert` | strategic_close（bb_breakout %B 回中）| `bb_breakout/mod.rs:524-550` | **CONDITIONAL** | 同 bw_squeeze；samples=1，併入相同 carve-out |

---

## 2. 遺漏的 exit_reason（應加 whitelist 或保 market）

**保 market（fail-safe）— 已涵蓋**：
- `HARD STOP: pnl X% <= Y%` — §5.9 P0/P1 硬止損
- `TRAILING STOP: peak A% - current B% = C%` — drawdown 真風控
- `TIME STOP: held Xh >= limit Yh` — 風控時間限制
- `DAILY LOSS / DRAWDOWN / CONSECUTIVE LOSS` — 帳戶級風控（per `step_6_risk_checks.rs:265`）

**遺漏項（FA 識別）— 提議追加保 market**：

| exit_reason | 來源 | FA 判定 |
|---|---|---|
| `TAKE PROFIT: pnl X% >= Y%` | `phys_lock_wrapper_tests.rs:157` | **保 market**。Take profit 雖然非生存風控，但語義是「達標即收」；轉 maker 後若未成交 → 利潤回吐，違反設計初衷。背景白名單**未包含**，但提案中未明示處理 — **FA 強烈建議明文寫保 market** |
| `COST EDGE: ratio X >= 0.80` | 同上 (line 161) | **保 market**。原則 #13 cost_edge_ratio ≥ 0.8 = 建議關倉；此時 ai-cost 已超經濟性，等 maker 不成交反而再扣 hosting cost |
| `bybit_sync` / `orphan_*` / `dust_frozen` close | `exit_features/v2.rs:308` 提及 sync-label | **保 market**（reconciliation engine 觸發）。EX-04 對賬路徑驅動，需與交易所 SOT 立即同步 |
| IPC `/operator/close_position` 強制平倉 | `commands.rs` close_position_at_symbol_market 調用面 | **保 market**。Operator override 必須立即執行 |
| Engine shutdown / cancel_token / circuit breaker 觸發 close | `bybit_rest_client.rs` env-allowed 失效 → shutdown | **保 market**。原則 #9 災難保護 |

**請主會話派 PA 補一輪 grep**：`risk_close:` 前綴 emit 點 + `close_position_at_symbol_market` 直接呼叫面 + reconciliation engine forced-close path。FA 認為這 5 條若不顯式 carve-out，新代碼可能誤把「OPERATOR_FORCE_CLOSE」「TAKE PROFIT」誤導入 maker-first。

---

## 3. Acceptance Criteria 草案（mirror EDGE-P2-3 Phase 1a 模式）

EDGE-P2-3 Phase 1a entry-only 的 rollout 模式：(a) `strategy_params_*.toml` per-strategy `use_maker_entry` 旗 + maker_price_offset_bps + maker_limit_timeout_ms；(b) Rust struct cold-boot default = `false`（原則 #6）；(c) demo/paper=true、live=false；(d) 驗收 = `passive_wait_healthcheck` check `[3] maker_fill_rate ≥ 60%`；(e) live 翻轉條件 = 1-2w demo 驗證正 net edge。

### Phase 2a Demo PASS（最早 2026-05-29，7d 觀察）
- **AC-1**：`trading.fills WHERE engine_mode='demo' AND is_close=true AND exit_reason IN (whitelist 8) AND order_type='limit'` 比例 ≥ 60%
- **AC-2**：fallback transition (maker_timeout → taker market) 比例 ≤ 30%（與 entry side 對標）
- **AC-3**：close_dispatch_failed counter 不增（`commands.rs:826` log 命中數）
- **AC-4**：per-strategy 5 close exit_reason 各自 close fill ≥ 10 條（樣本量門檻；`bw_squeeze`/`pctb_revert` 各 ≥ 1，套 §1 carve-out gate）
- **AC-5**：close 平均 net_bps（fee net）改善 ≥ taker baseline 的 +3 bps（mirror entry maker 5.5→2 bps fee 節省的 50%）
- **AC-6**（新增）：原則 #8 audit — `trading.fills.details` 新欄位 `close_maker_attempt / close_maker_fallback_reason` 100% non-null
- **新增 healthcheck**：`passive_wait_healthcheck.py check_close_maker_fill_rate()`（複用 [3] 結構）

### Phase 2b LiveDemo PASS（最早 2026-06-05，再 7d）
- **AC-7**：LiveDemo demo Phase 2a 同等指標滿足
- **AC-8**：authorization.json HMAC re-verify 期間 0 stray pending maker close orders（與原則 #9 對齊；cancel_token 觸發必清空 pending close）
- **AC-9**：MAG-082/083/084 全 ✅ 維持，無 regression（W-C lease lineage 寫入正常）

### Phase 3 Live（純 Mainnet）— 翻 flag 必須 operator 簽署
- **AC-10**：phase 2b 14d 內 0 P0 regression + close net_bps Δ vs Phase 1a baseline ≥ +5 bps
- **AC-11**：operator 顯式 sign-off（mirror `EDGE-P2-3 Phase 1b` 翻轉模式 — `use_maker_close=false→true` per-策略 + per-exit_reason 旗）

### 失敗回滾 / kill switch
- **KS-1**：TOML hot-reload `use_maker_close=false`（ArcSwap，無重啟）→ 1 tick 內回 market
- **KS-2**：`close_maker_fail_rate > 50% over 5min` → IPC `/operator/risk/exit_patch` 自動 disable + alert
- **KS-3**：所有 strategic close 失敗 fallback 必走原 hard-coded market 路徑（已存在，零改動）

---

## 4. 16 條根原則 conflict 評估

| 原則 | 判定 | 證據 / 理由 |
|---|---|---|
| **#1 單一寫入口** | **PASS** | close path 仍 100% 走 `execute_position_close` → `OrderDispatchRequest` → `order_dispatch_tx`（單通道）；改的是 request 的 `order_type` / `maker_timeout_ms` 欄位，非分流多入口。下游 `event_consumer/loop_handlers.rs` 同一 sweep 邏輯 |
| **#3 AI→Lease→複核→執行** | **PASS** | close path 已在 W-C Caveat 2 修復後不寫 entry lineage（`commands.rs:809-815`），lease 由 entry 持有；改 order_type 不破此契約 |
| **#4 策略不能繞過風控** | **PASS**（critical clarification）| `phys_lock_gate4_*` 雖帶 `risk_close:` 前綴，**但語義是 profit-protection 非 §5.9 hard-stop**（見 `position_risk_evaluator.rs:341` 設計註）。`HARD STOP / TRAILING / TIME / DAILY LOSS` 才是真風控，**強制保 market** = 風控通道完整。FA 確認該邊界 carve-out 正確 |
| **#5 生存 > 利潤** | **CONDITIONAL** | maker timeout 期 (45s default) 倉位仍 expose；若 spot-vol spike，45s ≈ 1-3 個 ATR 移動。**緩解**：(a) `maker_limit_timeout_ms` close 路徑可降到 15-30s（demo first），(b) `phys_lock_gate4_*` 的 timeout 必須 ≤ atr_pct_15m 對應的等價 risk window，(c) **AC 必含 close_timeout_pre_stopout_rate ≤ 5%**（在 maker timeout 內被 hard stop 搶先觸發的比例） |
| **#6 失敗默認收縮** | **CONDITIONAL — 必須 cold-boot=false** | maker-first close 是「放寬」（增加未成交風險窗）。**強制 carve-out**：(a) Rust struct cold-boot default `use_maker_close: false` per `use_maker_entry` 同 pattern（`bb_breakout/mod.rs:221` 註），(b) `risk_config_live.toml` 預設不啟用，(c) demo 7d → LiveDemo 7d → Mainnet (operator sign-off only) 三段必 mirror entry 已建立模式 |
| **#7 學習 ≠ 改寫 Live** | **PASS** | 翻 flag 是 governance 動作非學習面動作；ML/DreamEngine 無法寫此 flag |
| **#8 交易可解釋** | **CONDITIONAL — 新欄位 mandatory** | `trading.fills.details` 必補 `close_maker_attempt: bool`、`close_maker_fallback_reason: enum{timeout_taker, postonly_reject, cancel_grace_expired, ack_lost}`、`close_initial_limit_price: f64`、`close_final_fill_price: f64`。`OrderDispatchRequest` 已有 `reference_price` / `reference_ts_ms` / `reference_source` 結構，新欄位可複用 telemetry 通道（`commands.rs:798-808`）。AC-6 已列 |
| **#9 交易所災難保護** | **CONDITIONAL** | 引擎/網絡崩 + pending maker close → tracker row 在重啟後丟失（`state.pending_orders` 是 in-memory）；交易所端 maker order resting 風險 = 倉位仍 open。**強制 carve-out**：(a) `cancel_resting_maker_order` 在 cancel_token shutdown 路徑必須 best-effort fire-and-forget（已有，line 647 `tokio::spawn`），(b) authorization.json 失效 → engine shutdown 前必清空所有 pending close maker orders（**FA 新增要求**），(c) recovery 後優先 reconcile 而非新 entry |
| **#11 Agent P0/P1 自主** | **PASS** | P0/P1 硬邊界（HARD STOP / TRAILING / TIME / DAILY LOSS）仍走 market 不改 |
| **#13 AI cost 感知** | **PASS** | maker-first 不增 AI 調用 |
| **#15 多 Agent 協作** | **PASS** | 不觸 Conductor / Scout / Strategist / Guardian / Analyst / Executor 通信契約 |
| **#16 組合級風險意識** | **CONDITIONAL** | maker close 未成交時組合 net exposure 未減 → portfolio_var/correlation gates 必須以 **request_qty 而非 filled_qty** 計算 effective exposure（否則 risk view 短暫 underestimate）。**FA 建議 verify** `intent_processor` portfolio 計算 SoT |

**未觸及**：#2 / #10 / #12 / #14（讀寫分離、認知誠實、進化、零成本）

---

## 5. 9 條安全不變量（CLAUDE.md §四 fail-closed 邊界）觸碰評估

| 不變量 | 觸碰？ | 評估 |
|---|---|---|
| `execution_state` | NO | close path 不改 execution state 字段 |
| `execution_authority` | NO | Rust execution_authority 是 P0/P1 denylist 字串常量，不被觸 |
| `live_execution_allowed` | NO | flag 不在此 gate 範圍 |
| `decision_lease_emitted` | NO | close path 已不寫 lease lineage（W-C Caveat 2 修） |
| `max_retries` | NO | maker timeout cancel 是 sweep loop 不是 retry |
| `OPENCLAW_ALLOW_MAINNET` | NO | 環境變數不變 |
| `authorization.json HMAC` | **INDIRECT touched** — AC-8 已含；HMAC 失效 → shutdown 必先 cancel pending maker close（FA 新增護欄）|
| `live_reserved` global mode | NO | Python live_reserved 不接 |
| `Bybit API timeout / retCode != 0 → fail-closed` | **PASS** | `cancel_resting_maker_order` 失敗 → log error + tracker 不阻塞下次 sweep；保留 fail-closed 語義 |

**結論**：9/9 PASS or PASS-with-stated-mitigation。**無 BLOCKER**。

---

## 6. phys_lock live 啟用 vs fail-safe — `missing_edge_fallback_bps` 決策

**核實事實**：
- `risk_config_demo.toml:199` `missing_edge_fallback_bps = 10.0`（EDGE-DIAG-1 對照實驗 override）
- `risk_config_live.toml` 無 `[exit]` override → 用 Rust default `-10.0`（`exit_features/v2.rs:174`）
- Gate 1 邏輯：`effective_edge = est_net_bps.unwrap_or(missing_edge_fallback_bps)`；若 ≤ `min_net_floor_bps=5.0` → Hold
- live: `-10 < 5` → 100% Gate 1 Hold → phys_lock 7d 0 fires by design

**FA 建議**：**DEFER**（不在本提案內動）

**理由**：
1. close-maker-first 本身**不需要 phys_lock 啟用**——白名單裡 phys_lock_gate4_* 已含，是「**若**未來 phys_lock 啟動則同步走 maker」的前置面，當前無實際 fire 樣本
2. live 啟用 `missing_edge_fallback_bps=10` 是 **edge data 政策決策**（feedback_demo_loose_live_strict_policy.md 明示「operator 決定不放寬 demo，因為動了會連 live 一起放寬」反向亦真）— 跨 demo/live 對稱性、edge 估計樣本量（P1-7 C labels 47/200 unconfirmed）、Phase 5 promotion ladder 均未閉環
3. 與原則 #6（失敗默認收縮）reconcile：當前 live -10 是「保守 hold」= fail-safe；強行打開 = 在 close path 改動的同 sprint 引入第二個 surface 行為改變，違反 EDGE-P2-3 模式 (one-flag-per-phase)
4. 真正合適時機：close-maker-first Phase 2b LiveDemo PASS 後另開 PR，與 P0-EDGE-1 alpha-source decision 合併評估

---

## 7. 業務 / 規範遺漏（FA findings）

1. **F-FA-1 (P1)**：原則 #8 audit 欄位 `close_maker_*` 在 `trading.fills.details` schema **未存在**；需 V### migration 補入。E1 IMPL 前必確認，否則 AC-6 無從驗
2. **F-FA-2 (P1)**：`portfolio_var` / correlation gate 是否用 request_qty vs filled_qty 計 exposure — FA 在 `intent_processor/mod.rs` 未 grep 到明確結論，建議派 PA 補核（原則 #16 conditional 依此而定）
3. **F-FA-3 (P1)**：`commands.rs:809-815` W-C Caveat 2 fix 假設 close path 不寫 lineage — close maker 改 order_type 不改此契約，**但**新增的 `close_maker_attempt` audit 欄位必須**不**經 spine lineage 通道，否則破不變式
4. **F-FA-4 (P2)**：DOC-08 §12 incident response 對「maker timeout 期間 partial fill」沒明確 SOP — 提案外但建議補 EX-04 reconciliation 對 partial maker close 的處理章節
5. **F-FA-5 (P2)**：背景假設「`bb_mean_revert` 是跨策略信號」不準確（已在 §1 更正）；提案 spec 文檔需修正措辭，否則下游 PA/E1 沿用會誤設計

---

## 8. FA Verdict

**判定**：**APPROVED-CONDITIONAL**

**Condition 1（mandatory，blocking IMPL）**：採納 §2 5 條遺漏 exit_reason 保 market 明示化（TAKE PROFIT / COST EDGE / bybit_sync / OPERATOR_FORCE_CLOSE / shutdown-triggered）；spec 寫死 negative whitelist + positive whitelist 雙清單。

**Condition 2（mandatory）**：採納 §4 原則 #5/#6/#8/#9/#16 5 條 CONDITIONAL carve-out（cold-boot=false / 新增 audit 欄位 V### migration / cancel pending on shutdown / request_qty exposure 確認）。

**Condition 3（mandatory）**：mirror EDGE-P2-3 Phase 1a 部署模式 — demo 7d PASS → LiveDemo 7d PASS → Mainnet 翻 flag 必 operator sign-off；每段 AC-1~11 完整。

**Condition 4（recommended）**：`phys_lock` live 啟用 DEFER 至 close-maker-first Phase 2b 後另開 PR。

**Condition 5（recommended）**：F-FA-1~5 5 條 finding 派 PA/E1 在 IMPL 前處理 F-FA-1 / F-FA-2 / F-FA-3（P1），F-FA-4 / F-FA-5（P2 可後跟）。

---

## 業務鏈完整度評分（提案落地後預期）

| 環節 | 當前 | Phase 2a demo PASS | Phase 2b LiveDemo PASS | Phase 3 Live |
|---|---|---|---|---|
| 下單（含 close 路徑） | 88% | 91% (+3) | 93% (+2) | 95% (+2) |
| 止損（真風控保 market 完整性） | 95% | 95% (no regression) | 95% | 95% |
| 觀察（fee audit completeness） | 88% | 90% | 91% | 92% |

**整體業務鏈**：63% → 預期 Phase 2a +1% / Phase 2b +1% / Phase 3 +1%（規模有限因為主要影響 fee-drag 邊際，非新建業務鏈環節）

---

**關鍵文件指針**（IMPL agent 必讀）：
- `srv/rust/openclaw_engine/src/tick_pipeline/commands.rs:778-815` 改點
- `srv/rust/openclaw_engine/src/event_consumer/loop_handlers.rs:573-678` sweep 邏輯（複用）
- `srv/rust/openclaw_engine/src/tick_pipeline/on_tick/step_6_risk_checks.rs:374-393` risk_close emit 點（不動，但對應 negative whitelist）
- `srv/rust/openclaw_engine/src/exit_features/v2.rs:125-199` `missing_edge_fallback_bps` 不動（DEFER）
- `srv/docs/references/2026-04-24--postonly_design_intent.md` 部署模式 SoT
- `srv/settings/risk_control_rules/strategy_params_{demo,live,paper}.toml` per-strategy flag 結構 SoT
- `srv/helper_scripts/db/passive_wait_healthcheck/` 新增 `check_close_maker_fill_rate()` 強制
