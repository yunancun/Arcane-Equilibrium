# Amendment AMD-2026-05-15-02 — EDGE-P2-3 Phase 1b: Close-Maker-First Refactor

**對應 spec**: EDGE-P2-3 · DOC-01 §5.1/§5.4/§5.5/§5.6/§5.8/§5.9/§5.16 · DOC-08 §12 · `docs/references/2026-04-24--postonly_design_intent.md`
**修訂對象**: EDGE-P2-3 Phase 1a entry-only scope-limiting 設計（`commands.rs:792-797` hard-coded `order_type:"market"` with comment「Close path stays Market (EDGE-P2-3 Phase 1a entry-only scope)」）
**Supersedes**:
- EDGE-P2-3 Phase 1a 的 close-path-entry-only scope boundary（自然延伸到 close path）
- 過去任何「close path 永遠 market」字面語義（仍對真風控止損成立，對策略級 close 解除）

**日期**: 2026-05-15
**作者**: PM applying main-session PM+PA+FA convergent verdict
**狀態**: **DRAFT** — pending QC + FA + BB + MIT 4-agent adversarial review
**索引**: `docs/governance_dev/SPECIFICATION_REGISTER.md` Amendments section
**TODO 連結**: P0-EDGE-1（fee bleed 影響 edge measurement）/ EDGE-P2-3 Phase 1b / W-AUDIT-8b（後續 funding alpha 不被執行成本掩蓋）

---

## 1. Executive Decision

**Close path is now an alpha-bearing pathway.**

EDGE-P2-3 Phase 1a 的「entry-only PostOnly」scope 在 close path 延伸為按 `exit_reason` 白名單分流的 maker-first 機制。安全止損 / 賬戶風控 / 對賬 / operator override 強制保 market 不變。

決策邏輯：
1. 經 3 輪對抗審核 + DB / 代碼核驗，5 textbook 策略 30d demo `-110.43` / live_demo `-27.31` USDT structural alpha-deficient；其中 `live_demo grid 7d 100% active taker close 全是策略級`（grid_close_short 74% / bb_mean_revert 18% / grid_close_long 7% / ma_reverse_cross <1%），**0% 真風控**。
2. 現有「Close path stays Market」comment 是 **governance scope-limiting decision，不是技術限制**（PA 驗 dispatch.rs:504-538 IPC chain 已完整支援 Limit + PostOnly + maker_timeout）。
3. `phys_lock_gate4_giveback` / `phys_lock_gate4_stale_roc_neg` 是 **profit-protection 4-gate 鏈**（edge floor → hold age → peak ATR → giveback / stale ROC），非 §5.9 hard-stop（FA verified；exit_features/v2.rs:286-288 PhysicalDecision::Lock 證據）。
4. Phase 1B-4.2 resting_orders.rs 是 paper-only path，與 exchange close 正交，**0 依賴**（PA verified）。

---

## 2. Scope Change

### 2.1 Newly Permitted Path

`OrderDispatchRequest` 在 `commands.rs:778-816` / `commands.rs:940` (ipc_close_all) / `commands.rs:1123` (ipc_close_symbol) 三個 close dispatcher 可按 `trigger_tag` / `exit_reason` 白名單構造 PostOnly Limit + maker_timeout_ms，timeout 後 fallback to market。

### 2.2 Positive Whitelist（8 maker-first reasons）

| exit_reason | 來源 |
|---|---|
| `grid_close_short` | grid_trading/signal.rs:316 |
| `grid_close_long` | grid_trading/signal.rs:348 |
| `bb_mean_revert` | bb_reversion/mod.rs:629（**same-strategy exit; not cross-strategy**） |
| `phys_lock_gate4_giveback` | exit_features/v2.rs Lock decision |
| `phys_lock_gate4_stale_roc_neg` | exit_features/v2.rs Lock decision |
| `ma_reverse_cross` | ma_crossover/strategy_impl.rs |
| `bw_squeeze` | bb_breakout/mod.rs（CONDITIONAL with healthcheck `min_samples_gate=30`） |
| `pctb_revert` | bb_breakout/mod.rs:524-550（同上） |

### 2.3 Negative Whitelist（強制保 market）

| 類別 | 顯式 reason |
|---|---|
| 真風控 | `risk_close:HARD STOP` / `risk_close:TRAILING STOP` / `risk_close:TIME STOP` / `risk_close:DYNAMIC STOP` |
| 帳戶級風控 | `DAILY LOSS` / `DRAWDOWN` / `CONSECUTIVE LOSS` |
| 利潤達標 | `TAKE PROFIT: pnl X% >= Y%` |
| AI cost gate | `COST EDGE: ratio X >= 0.80` |
| 對賬 | `bybit_sync` / `orphan_*` / `dust_frozen` |
| Operator override | IPC `/operator/close_position` 強制平倉 |
| 災難保護 | Engine shutdown / cancel_token / circuit breaker / authorization 失效 |
| 策略內部歧義 keyword | bb_breakout 內部 `trailing_stop`（chandelier exit；與 `risk_close:TRAILING STOP` 同 keyword，必 source 識別） |
| 未識別 reason | fail-closed 走 market（§5.6） |

---

## 3. Rollout Posture

**Mirror EDGE-P2-3 Phase 1a entry-only 模式**：

| Phase | 期間 | 環境 | TOML | 啟動條件 |
|---|---|---|---|---|
| **Phase 2a Demo** | 7d | demo | `use_maker_close = true` per-策略 | IMPL 完成 + 三閘全過 + AMD 4-agent review PASS |
| **Phase 2b LiveDemo** | 7d | live_demo | `use_maker_close = true` per-策略 | Phase 2a PASS（AC-1..AC-7） |
| **Phase 3 Live (Mainnet)** | indefinite | live | `use_maker_close = true` per-策略 per-exit_reason | Phase 2b PASS + operator 顯式 sign-off + 本 AMD 補件（live carve-out section） |

**Rust struct cold-boot default**: `use_maker_close = false`（§5.6 fail-safe）。

**Kill-switch（任一觸發自動回 market）**：
- TOML hot-reload `use_maker_close=false` → ArcSwap 1 tick 內生效
- `close_maker_fail_rate > 50% over 5min` → IPC 自動 disable
- engine shutdown / authorization 失效 → cancel_token 觸發 best-effort cancel pending + 後續 close 走 market

---

## 4. phys_lock Live 分軌（不在本 AMD scope 內，DEFER）

**現狀**：
- demo: `risk_config_demo.toml:199` override `missing_edge_fallback_bps = 10.0`（EDGE-DIAG-1 對照實驗）→ Gate 1 pass → demo 7d 86 fires
- live (含 live_demo): 無 override → Rust default `-10.0`（exit_features/v2.rs:174-180）→ Gate 1 永遠 Hold → 7d 0 fires（**by design fail-safe**）

**本 AMD 不啟用 live phys_lock**。理由：
1. 啟用 = 跨 §5.6 fail-safe（同 sprint 引入 2 個 surface 行為改變，違反 one-flag-per-phase 模式）
2. close-maker-first 白名單包含 `phys_lock_gate4_*` 是「未來啟用後同步走 maker」的前置面，不需要當前 fire 樣本
3. `feedback_demo_loose_live_strict_policy` 政策：demo 放寬不要連帶放寬 live，反向亦真

**啟用時點**：close-maker-first Phase 2b PASS 後另開 PR，與 P0-EDGE-1 alpha-source 決策合併評估（QC math 佐證 + operator sign-off）。

---

## 5. Stage 0R Replay Preflight 對齊

**本 AMD 不啟動 Stage 0R 流程**（close-maker-first 是 fee optimization 不是 alpha promotion）。但需 mirror AMD-2026-05-15-01 的 evidence discipline：

| Stage | 對應 close-maker-first 階段 | Promotion authority |
|---|---|---|
| Stage 0 | 本 AMD draft 期 + IMPL 開發期（shadow） | none |
| Stage 0R | （N/A — replay 無法驗執行成本與 fill 行為） | （N/A） |
| Phase 2a | demo 7d 觀察（mirror Stage 1 demo micro-canary） | empirical demo evidence only |
| Phase 2b | live_demo 7d（mirror Stage 2） | empirical live_demo evidence only |
| Phase 3 | live (Mainnet)（mirror Stage 4 LIVE_PENDING） | operator + AMD 補件 |

---

## 6. compute_close_limit_price() Spec

**位置**：`srv/rust/openclaw_engine/src/strategies/common/maker_price.rs`（與 entry side `compute_post_only_price()` 同檔）。

**設計（PA Option C）**：
- 內部複用 `compute_post_only_price(is_long=close_direction_inverted, MakerPriceInputs, offset, buffer_ticks, ...)` strict-skip 模式
- per-exit_reason 變體通過 `buffer_ticks` + `offset_bps` + `timeout_ms` 三參數微調，不寫多套 algorithm
- strict-skip：BBO 不存在 / tick_size 不存在 / inverted price ≤ 0 → return None → 回退 market（§5.6 fail-safe）

**Per-exit_reason 參數**：

| exit_reason | buffer_ticks | offset_bps | timeout_ms |
|---|---|---|---|
| grid_close_short / grid_close_long | 1 | 0.5 | 30000 |
| bb_mean_revert | 1 | 0.5 | 30000 |
| ma_reverse_cross | 1 | 0.5 | 30000 |
| phys_lock_gate4_giveback | 2 | 1.0 | 30000 |
| phys_lock_gate4_stale_roc_neg | 1 | 0.5 | **10000** |
| bw_squeeze / pctb_revert | 1 | 0.5 | 30000 |

---

## 7. 16 條根原則合規

| 原則 | 判定 | 機制 |
|---|---|---|
| #1 單一寫入口 | PASS | close path 仍走 `execute_position_close → OrderDispatchRequest → order_dispatch_tx` 單通道 |
| #4 策略不繞風控 | PASS | DYNAMIC/TRAILING/TIME/HARD STOP/TAKE PROFIT/COST EDGE 強制保 market；§2.3 negative whitelist 明文 |
| #5 生存 > 利潤 | CONDITIONAL | `phys_lock_gate4_stale_roc_neg` timeout 10s；AC-2 fallback ≤30%；新 AC: close_timeout_pre_stopout_rate ≤ 5% |
| #6 失敗默認收縮 | CONDITIONAL | cold-boot=false / live 預設不啟用 / 三段灰度 / kill-switch |
| #8 交易可解釋 | CONDITIONAL | `trading.fills.details` 新 4 audit 欄位 100% non-null（V### migration） |
| #9 災難保護 | CONDITIONAL | cancel_token 觸發 cancel_resting_maker_order best-effort；authorization 失效 → 清 pending |
| #16 組合風險 | CONDITIONAL | maker pending 期 portfolio_var 用 request_qty 不用 filled_qty（F-FA-2 verify pre-IMPL） |
| 其他 | PASS / 不觸 | — |

9 條安全不變量：9/9 PASS or PASS-with-stated-mitigation（FA verified；無 BLOCKER）。

---

## 8. IMPL Prerequisites（4-gate AUTH）

**所有條件必滿足才能進 IMPL**：

1. ✅ PA spec finalize（`docs/execution_plan/2026-05-15--edge_p2_3_phase_1b_close_maker_first_spec.md`）
2. ⏳ 本 AMD 經 **QC + FA + BB + MIT 4-agent 並行 adversarial review** PASS
3. ⏳ 三閘全過：
   - P0-EDGE-1 closed（[40] negative realized edge resolved）
   - W-AUDIT-8b Stage 0R passed（funding skew empirical evidence）
   - W-AUDIT-8a C1 BB/MIT sign-off（24h liquidation proof passed）
4. ⏳ 強制工作鏈：PA spec → E1 並行（A/B/C/D/E 5 worktree）→ E2 review → E4 regression → QA → PM sign-off。**不走 P0 快速通道**

---

## 9. Removed Path（顯式禁止）

- ❌ Close path 不走 W-AUDIT-9 Stage 0R replay preflight（不適用：執行成本與 fill 行為 replay 無法驗）
- ❌ 不在 W3 active scope 內 implement（PM 拒 W3 scope-in；queue Sprint N+2 P1 backlog）
- ❌ 不走 P0 快速通道（FA / E5 / E3 / CC 不可省）
- ❌ 不在本 AMD 內啟用 live phys_lock（DEFER 至 Phase 2b 後另 PR）
- ❌ 不修改 stop_manager / reconciliation engine / paper_state/resting_orders 任何代碼
- ❌ 不依賴 Phase 1B-4.2 完整實裝（PA verified 0 dependency）

---

## 10. Rollback Path

| 時機 | 動作 |
|---|---|
| Phase 2a demo 觀察 FAIL | TOML hot-reload `use_maker_close=false` → 1 tick 內回 market；FA / QC root cause review；spec 修訂或 reject |
| Phase 2b live_demo FAIL | 同上 + DOC-08 §12 incident response |
| Phase 3 live regression | operator-triggered kill-switch + AMD 補件回溯 |

回滾路徑 100% 走原 hard-coded market 路徑（已存在，零改動），**無 schema migration 回滾需求**。

---

## 11. Verdict from Source Audits

- **PM**: APPROVED-CONDITIONAL（Sprint N+2 P1，非 P0；4 IMPL 條件；6 governance gates；MA KAMA fix scope-in W3-6 by-the-way）
- **PA**: READY-FOR-SPEC（1 NEEDS-PROBE on rate-limit；0 BLOCKED-BY-1B-4.2；估 ~985 LOC, 7-9 E1-day, 3-5 worktree 並行）
- **FA**: APPROVED-CONDITIONAL（5 conditions：negative whitelist 顯式 / cold-boot=false / audit 欄位 V### migration / cancel pending on shutdown / request_qty exposure 確認）

---

## 12. 變更歷史

| 日期 | 版本 | 變更 | 作者 |
|---|---|---|---|
| 2026-05-15 | v0.1 DRAFT | 初版 — pending QC+FA+BB+MIT 4-agent adversarial review | Main session |

**下一步**：派 QC + FA + BB + MIT 4-agent 並行 adversarial review 本 AMD draft。
