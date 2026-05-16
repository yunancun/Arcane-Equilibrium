# Amendment AMD-2026-05-XX-XX — phys_lock Live Enable (DRAFT)

**對應 spec**: EDGE-P2-3 Phase 1b 後續 · DOC-01 §5.4/§5.5/§5.6/§5.8/§5.16 · DOC-08 §12 · `risk_config_live.toml [exit]` carve-out · `exit_features/v2.rs:125-203` ExitConfig schema
**修訂對象**: AMD-2026-05-15-02 v0.4 §4「phys_lock Live 分軌（不在本 AMD scope 內，DEFER）」立場
**Supersedes**: (none — 本 AMD 是 follow-up，**不直接 supersede** AMD-2026-05-15-02 §4 DEFER 立場；待本 AMD 完整 sign-off + Phase 2b LiveDemo PASS + QC counterfactual gate 三條件齊備後才生效)
**日期**: 2026-05-16
**作者**: PA per main session 派 Wave C-3 dispatch（pre-Phase 2b future enable AMD draft prep）
**狀態**: **DRAFT — NOT LANDED** — pending (a) Phase 2b LiveDemo 7d PASS empirical evidence; (b) QC counterfactual analysis demo 86 fires PASS; (c) operator 顯式 sign-off; (d) AMD slot 編號補實（per `SPECIFICATION_REGISTER.md` 下一 free slot）
**索引**: 暫不入 `SPECIFICATION_REGISTER.md`（draft only；slot 補實後再 register）
**TODO 連結**: P0-EDGE-1（alpha-deficient regime 下 phys_lock 啟用 trade-off 評估）/ EDGE-P2-3 Phase 1b（close-maker-first Phase 2b 是前置 gate）

---

## 1. Executive Decision

**phys_lock Live 啟用 = 解除 `risk_config_live.toml` 對 `[exit].missing_edge_fallback_bps` 的隱式 fail-safe 後備**（從 Rust default `-10.0` 改為 TOML override `+10.0`，與 demo 對稱）。

**範圍嚴格限定**：本 AMD 僅啟一個 surface 行為改變 — 在 `risk_config_live.toml [exit]` 段加 `missing_edge_fallback_bps = 10.0` override，使 live + LiveDemo 環境的 `exit_features/v2.rs::PhysicalDecision` Gate 1 從「missing edge → effective_edge = -10 < min_net_floor=5 → 永久 Hold」改為「missing edge → effective_edge = +10 ≥ floor → 進 Gate 2+」。其餘 phys_lock 8-gate 鏈條（min_hold_secs / min_peak_atr_norm / stale_peak_ms / giveback_*）參數保持 Rust default 與 demo 一致，**不引入新調參面**。

**啟用語義**：把 demo 7d 觀察到的 86 fires 對應 profit-protection 行為（gate4_giveback / gate4_stale_roc_neg）擴展到 live + LiveDemo，使 phys_lock 從 demo-only 對照實驗轉為三環境一致的 profit-protection 機制。

**Framing 嚴謹性**：phys_lock = profit-protection（peak ATR giveback / stale ROC neg lock-in），**不是 risk-bypass 也不是新 alpha source**；其經濟效果是 Sharpe-style risk-adjusted return 改善（持倉期望時間縮短 + opportunity cost 降低 + max-DD-per-trade 截斷），不改變 informational alpha component（per QC §6 transaction cost economics 分解：本 AMD 屬 `α_holding` truncation policy，不改 `α_entry / α_exit`）。

---

## 2. Scope

### 2.1 唯一改動

`settings/risk_control_rules/risk_config_live.toml [exit]` 段加：
```toml
# AMD-2026-05-XX-XX phys_lock Live Enable — pending operator sign-off
# Live + LiveDemo: 與 demo 對稱解除 missing-edge fail-safe，啟用 phys_lock profit-protection
missing_edge_fallback_bps = 10.0
```

### 2.2 不改動清單（明文 enumerate）

| 項 | 保持現狀 |
|---|---|
| `min_net_floor_bps` | Rust default `5.0` |
| `min_hold_secs` / `min_peak_atr_norm` / `stale_peak_ms` | Rust default 不變 |
| `giveback_base` / `giveback_slope` / `giveback_floor` | Rust default 不變 |
| `shadow_enabled` | Rust default `false`（不在本 AMD 內啟 Combine Layer shadow） |
| `risk_config_demo.toml:199` | 已 override `10.0`，不動 |
| `risk_config_paper.toml` | 不動（paper disabled by design） |
| close-maker-first 白名單 | 不動（AMD-2026-05-15-02 §2.2 `phys_lock_gate4_*` 已含；本 AMD 啟後同步走 maker，不需 patch） |
| 8-gate 鏈條任何邏輯 | `exit_features/v2.rs::compute_physical_decision()` 0 代碼改動 |
| H1-H5 / Decision Lease / Guardian / StopManager | 0 觸碰 |

### 2.3 影響範圍估算

By analogy to demo 7d 86 fires / 25 symbols ≈ **0.49 fire / symbol / day**：
- live 25 symbols × 30d ≈ **~370 fires/月** profit-protection lock-in 預期觸發頻率
- LiveDemo 累積樣本同等量級（demo + live_demo IPC 共用 risk_config_live 後）
- 對應 close-maker-first 白名單：370 月度新 maker-first close opportunity（per AMD-2026-05-15-02 §2.2 `phys_lock_gate4_giveback` + `phys_lock_gate4_stale_roc_neg`）

**注意**：此估算建立在「live regime 與 demo regime 行為對稱」假設上，**未必成立**（per §4 Risk Assessment item 2）。

---

## 3. Pre-enable Conditions（gate stack）

**所有條件必滿足才能將本 DRAFT 轉 Accepted + land 至 active amendments folder + 補 slot 編號**：

| Gate | 證據要求 | 狀態 |
|---|---|---|
| **3.1 Phase 2b LiveDemo PASS** | AMD-2026-05-15-02 §3 Phase 2b 7d 完整觀察 + AC-1..AC-19 (Wilson CI + reject sample + NULL ladder + fallback rate ≥ 95% + 14d close_maker_fill_rate ≥ 30%) + FDR 0.10 BH adjustment 全 PASS | ⏳ Pending（Phase 2b 尚未啟動，等 Phase 2a Demo 14d PASS + IMPL Prereq 6 全解） |
| **3.2 QC Counterfactual Analysis** | QC 跑 demo 86 fires 對應倉位「**不啟用 phys_lock 反事實 PnL**」對比「**啟用 phys_lock 實際 PnL**」 — must show net positive：`counterfactual_PnL_no_lock < actual_PnL_with_lock`（即鎖利確實創造 risk-adjusted return 改善）。樣本量 n=86 需做 bootstrap CI；q-value < 0.10 顯著 | ⏳ Pending（QC §6 NEW MUST，本 AMD §5 補入 evidence packet 強制要求） |
| **3.3 Operator 顯式 Sign-off** | Operator 在 commit message + governance trail 明文 approve；不接受 implicit 推導 | ⏳ Pending |
| **3.4 P0-EDGE-1 狀態評估** | 不要求 P0-EDGE-1 closed（5 textbook 策略結構性 alpha-deficient 可能無限期 active），但要求 PA + QC + FA 三方明文聲明：「即使 P0-EDGE-1 active，phys_lock 啟用的 net positive 仍成立」 | ⏳ Pending（per §4 風險 item 2） |
| **3.5 AMD-2026-05-15-02 v0.4 §4 立場修訂** | 本 AMD Accepted 同時提交 AMD-2026-05-15-02 v0.5 補丁，把 §4「DEFER」改為「DEFER until AMD-2026-05-XX-XX SATISFIED → SUPERSEDED on land date」 | ⏳ Pending（提交 v0.5 patch 工作量 ~0.2h cosmetic） |
| **3.6 AMD slot 編號實裝** | per `SPECIFICATION_REGISTER.md` 下一 free slot（land 時 2026-05-XX 對應日）；目前 placeholder `XX-XX` | ⏳ Pending |

**不要求**：W-AUDIT-8a C1 BB/MIT sign-off / W-AUDIT-8b Stage 0R PASS / 任何 alpha-bearing 三閘（本 AMD 是 profit-protection execution-quality optimization 性質，per §1 framing，與 alpha promotion 三閘正交）。

---

## 4. Risk Assessment

### 4.1 One-flag-per-phase 違反風險（核心）

**現狀**：close-maker-first Phase 1b 是 live 端**已在進行**的 surface 行為改變（Phase 2b live_demo 段，AMD-2026-05-15-02 §3 active）。本 AMD 同 sprint 引入第二個 live surface 改變 → **直接違反 EDGE-P2-3 one-flag-per-phase 模式**（per AMD-2026-05-15-02 §4 DEFER 第 1 條原文）。

**緩解 1**：強制 Gate 3.1 — 本 AMD enable timing 必須在 Phase 2b PASS 之後（即 AMD-2026-05-15-02 §3 Phase 2b 14d 觀察窗結束 + AC 全 PASS + close-maker-first 已 production-stable），保證兩個 live surface 改變不重疊。

**緩解 2**：本 AMD 啟用後立即進入 phys_lock-only 14d observation 窗，期間禁止其他 live surface flag 翻轉。

**殘留風險**：MEDIUM — 若 Phase 2b 仍在 production 早期（< 4w post-stabilize），observability 干擾依然存在；診斷新事件時可能誤把 close-maker-first 副作用歸因 phys_lock 或反之。

### 4.2 P0-EDGE-1 Alpha-deficient Regime 風險（QC §6 核心反問）

**事實**：5 textbook 策略 30d demo `-110.43` USDT structural alpha-deficient（per CLAUDE.md §三 P0-EDGE-1 active）。

**QC §6 反問**：在 alpha-deficient regime 下，phys_lock 鎖的可能是 **noise 不是真 alpha**：
- 若信號是 noise，peak ATR + giveback 信號本質上是 mean-reversion 後的 random retracement，鎖利相當於 stop-loss-on-favourable-noise；
- 在 random walk regime 下，per-trade Sharpe 改善可能來自 path-dependent timing luck，非 systematic skill；
- **counterfactual_PnL_no_lock** 可能 ≥ actual_PnL_with_lock（即不鎖更好）。

**緩解**：強制 Gate 3.2 — Counterfactual analysis pre-enable。具體計算（per QC §6 §11 nice-to-have item 11）：
- 取 demo 86 fires 對應倉位 entry timestamp + qty + side
- 計算反事實場景 A：fire 時刻不 lock，後續 `min_hold_secs + giveback_window` 結束時 market close → 收 actual close fill price
- 對比實際場景 B：fire 時刻 phys_lock lock → 收 actual lock close fill price
- 計算 86 paired diff（A - B）→ paired bootstrap CI 95%（n_bootstrap=1000）
- PASS 條件：median(A - B) < 0 (i.e. with-lock 顯著優於 without-lock) AND 95% CI 上限 < 0 (one-sided)
- FAIL 條件：median(A - B) ≥ 0 OR CI 跨 0 → 反向決策，不啟用

**殘留風險**：HIGH — 即使 counterfactual PASS demo regime，live regime 可能行為不對稱（demo Bybit liquidity / slippage / funding 與 live mainnet 不一致 — Phase 2b LiveDemo 7d 驗 close-maker-first 但 phys_lock 端無真實 fire 樣本，counterfactual 仍限於 demo 樣本 extrapolate）。

### 4.3 Demo-loose-live-strict 政策違反風險

**事實**：`feedback_demo_loose_live_strict_policy.md` 明示「demo 是學習資料源可放寬；Live 永遠 fail-closed；核心是平衡虧損與盈利，非一味保守」。

**判定**：本 AMD 啟用 = 放寬 live fail-safe → **政策上是 negotiable**（不是禁止），但需 operator carve-out + counterfactual evidence 雙重門控。本 AMD §3 Gate 3.3 operator sign-off + Gate 3.2 counterfactual 即為政策履行。

**殘留風險**：LOW — 政策本身允許 net-positive trade-off；本 AMD 結構正確。

### 4.4 Demo/Live Regime 行為對稱性假設風險

**§2.3 估算「370 fires/月」依賴 demo regime 行為可外推到 live**。實際差異：
- demo Bybit API endpoint 與 live mainnet endpoint 路徑不同（fee tier / slippage / order book depth 不同）
- demo 樣本期 7d 不一定涵蓋完整 funding cycle / regime shift
- live 真 capital-at-risk 下的 trader behavior 假設與 demo 不對稱

**緩解**：本 AMD enable 後強制 14d observation 窗，per-fire 比對 demo baseline；偏差 > 2σ 觸發 review。

**殘留風險**：MEDIUM — 觀察窗短，2σ outlier 可能 false-positive。

### 4.5 Mode 變化下 Rust ArcSwap 熱重載行為

**事實**：`ExitConfig` 透過 RuntimeRiskConfig 走 ArcSwap 熱重載（per ARCH-RC1 unified config contract）。

**驗證要點**：TOML hot-reload 觸發後，正在 active 的 `compute_physical_decision()` invocation 是否使用 new config snapshot？per Rust ArcSwap semantic：每次調用 `config.load()` 取當前 snapshot，下一筆 fire 才使用 new value，**不破現有 in-flight decision**。

**殘留風險**：LOW — ArcSwap 設計即為此場景，已驗於 close-maker-first Phase 1a entry-side rollout。

---

## 5. Counterfactual Analysis 要求（QC §6 mandate）

### 5.1 Evidence Packet 強制條目

Pre-enable Gate 3.2 必交付 PA → QC → PM sign-off 路徑的 evidence packet：

| 項 | 內容 | Owner |
|---|---|---|
| 5.1.1 | Demo 86 fires 完整列表（fire_ts / strategy / symbol / qty / entry_price / actual_lock_price / actual_lock_pnl_bps） | PA 派 E1 dump from `trading.fills` + `exit_features.physical_decision_logs` |
| 5.1.2 | 每 fire 反事實場景 A 模擬：不 lock 後 `min_hold_secs + giveback_window` 結束 market close 對應 PnL | QC 跑 historical replay（用 `replay.simulated_fills` API；evidence_source_tier='counterfactual_replay'） |
| 5.1.3 | Paired bootstrap CI 95%（n=86, n_bootstrap=1000, block-bootstrap 防 path autocorrelation） | QC 跑 + 出報告 `docs/CCAgentWorkSpace/QC/workspace/reports/2026-05-XX--phys_lock_counterfactual_analysis.md` |
| 5.1.4 | Sensitivity sweep on `min_hold_secs` ± 50% / `giveback_floor` ± 0.1 / `peak_atr_norm` ± 0.2，判 PASS 是否穩健 | QC + PA review |
| 5.1.5 | Per-symbol breakdown（≥ 5 fires symbol 各自 t-test directional） + per-strategy breakdown | QC |

### 5.2 PASS / FAIL Criteria

**PASS**:
- median(A - B) < -2 bps（with-lock 顯著優於 without-lock，至少 2 bps net advantage）
- 95% one-sided CI 上限 < 0
- 5.1.4 sensitivity sweep 在所有 ± 偏移下仍維持 median(A - B) < 0
- 5.1.5 per-symbol 至少 70% directional positive（i.e. 35/49 if 5+ fires symbols ≈ 7+ pass）

**FAIL**（任一觸發 → 本 AMD 永久 REJECT，重啟需新 AMD）:
- median(A - B) ≥ 0
- 95% CI 跨 0
- sensitivity sweep 任一偏移翻為 negative
- per-symbol > 30% directional negative

### 5.3 Audit Trail

Evidence packet land 至 git tracked 路徑；QC report + PA verdict + Operator sign-off commit 訊息明文引用 evidence ref。

---

## 6. Rollback Path

### 6.1 Hot Rollback（< 1 tick）

`risk_config_live.toml [exit]` hot-reload `missing_edge_fallback_bps = -10.0`（或直接 remove override → fall back to Rust default `-10.0`）→ ArcSwap snapshot 1 tick 內生效 → next `compute_physical_decision()` invocation Gate 1 即回 fail-safe Hold → phys_lock 即刻 silent。

**驗證**：rollback 後 1h `[exit_features.physical_decision_logs WHERE phys_lock_fires=true AND engine_mode IN ('live','live_demo')]` 計數應為 0；2h+ 無新增 fire。

### 6.2 Triggering Conditions

| Trigger | 動作 |
|---|---|
| `phys_lock_live_fire_rate` 與 demo baseline 7d 偏離 > 2σ | 自動 ArcSwap rollback + alert |
| Phase 2b LiveDemo close-maker-first regression | 同上（先 rollback phys_lock 隔離變因，再判 close-maker-first 是否獨立 regression） |
| `cost_edge_ratio > 0.85` 持續 1h | rollback（per CLAUDE.md §二 #13 AI cost gate；phys_lock 啟用增加 hold time 可能拉高 cost_edge_ratio） |
| Operator override IPC | rollback |
| Engine cancel_token shutdown | 無需 rollback（authorization 失效 → engine shutdown，pending phys_lock 倉位走 reconciler 路徑） |

### 6.3 Schema Migration 回滾

**無 schema migration**：本 AMD 純 TOML hot-flag 改動，不涉 V### migration / 表結構變更 / fills audit 欄位新增。回滾 = TOML revert，0 schema rollback cost。

---

## 7. 16 條根原則合規

| 原則 | 判定 | 機制 / 評估 |
|---|---|---|
| #1 單一寫入口 | PASS | 不觸 IntentProcessor / OrderDispatchRequest 通道；phys_lock 是 close-decision policy，非新寫入口 |
| #2 讀寫分離 | PASS | TOML 寫入仍走 `risk_config_live.toml` SoT；GUI/learning 只讀 |
| #3 AI 輸出 ≠ 即時命令 | PASS | phys_lock 是 Rust 確定性決策（L0 路徑），非 AI 輸出；不繞 Decision Lease（close path 已不寫 lease lineage per W-C Caveat 2） |
| **#4 策略不能繞過風控** | **PASS** | phys_lock = profit-protection（per §1 framing），**非 risk-bypass**；HARD/TRAILING/TIME STOP 等真風控不在 phys_lock 控制路徑（per AMD-2026-05-15-02 §2.3 negative whitelist 強制保 market）；Guardian / SM-04 邊界不受 phys_lock 啟用影響 |
| **#5 生存 > 利潤** | **CONDITIONAL** | profit-protection 鎖利 trade-off：**鎖利減少 max-profit per trade（subordinate to 生存）但同步降低 opportunity cost + max-DD per trade（contribute to 生存）**。Net 評估必走 Gate 3.2 counterfactual。緩解：§5 counterfactual analysis FAIL 則拒啟 |
| **#6 失敗默認收縮** | **CONDITIONAL** | 本啟用 = **放寬 live fail-safe**（從 missing_edge=-10 fail-safe Hold → +10 進 Gate 2+ 允許 lock）。需 operator carve-out（per Gate 3.3）+ counterfactual evidence（per Gate 3.2）。緩解：Gate 3.1 Phase 2b PASS 為前置 + Gate 3.4 P0-EDGE-1 status 三方聲明 |
| #7 學習 ≠ 改寫 Live | PASS | TOML override 是 operator 手動配置，**非** ML / DreamEngine / ExecutorAgent 自動寫；走 git tracked governance 路徑 |
| **#8 交易可解釋** | **PASS** | phys_lock fire 在 `exit_features.physical_decision_logs` 已有完整 audit row（Gate 1-4 decision + edge_estimate + lock_reason）；本 AMD 啟用後 audit 行為不變，只是 row 量從 demo-only 擴展至 live + LiveDemo |
| #9 災難保護 | PASS | engine shutdown / cancel_token / authorization 失效 → reconciler 接手 pending close；phys_lock 不在 disaster-recovery 路徑 critical chain |
| #10 認知誠實 | PASS | 本 AMD §4 明文「事實 / 推斷 / 假設」分類；§5.1.4 sensitivity sweep 對抗 假設不穩風險 |
| #11 Agent 最大自主權 | PASS | P0/P1 硬邊界（HARD STOP / TRAILING / TIME STOP / DAILY LOSS）不變；phys_lock 是 close-decision policy，Agent 自主決定 timing / symbol / 策略不受影響 |
| #12 持續進化 | PASS | 不變動學習平面；不影響 outcome_backfill / evolution_*  |
| #13 AI 資源成本感知 | CONDITIONAL | phys_lock 啟用可能拉長平均 hold time → 提升 attention_tax → 可能拉高 cost_edge_ratio。緩解：§6.2 rollback trigger `cost_edge_ratio > 0.85 1h+ → rollback`；觀察期內 PA monitor cost_edge_ratio drift |
| #14 零外部成本可運行 | PASS | L0 確定性路徑（Rust phys_lock）不依賴 L1 Ollama / L2 Claude |
| #15 多 Agent 協作 | PASS | 不變動 5-Agent 架構 / Conductor 編排 / agent topic |
| #16 組合級風險意識 | PASS | phys_lock 影響 per-trade hold time + max-DD，不影響 portfolio_var / correlation gate 計算 SoT；不引入新 portfolio risk vector |

**結論**：16/16 PASS or PASS-with-stated-mitigation；**3 條 CONDITIONAL** (#5 / #6 / #13) 全部由 §3 pre-enable conditions + §5 counterfactual evidence + §6 rollback path mitigate；**0 BLOCKER**。

---

## 8. 9 條安全不變量逐條評估（CLAUDE.md §四 + DOC-08 §12）

| # | 不變量 | 判定 | 機制 |
|---|---|---|---|
| 1 | Pre-trade audit/replay 必開 | PASS | phys_lock decision 已有 `physical_decision_logs` audit；本 AMD 不改 audit pathway |
| 2 | Lease 必在執行前已 acquired | PASS | close path 不依賴 lease（per W-C Caveat 2）；phys_lock fire 走 close path 同樣不觸 lease |
| 3 | 執行回報必落 fills 表 | PASS | phys_lock-triggered close 走 OrderDispatchRequest → `trading.fills` INSERT，與其他 close path 同 |
| 4 | 風控降級 → engine 自動止血 | PASS | HARD/TRAILING/TIME STOP 不在 phys_lock 控制路徑；SM-04 escalate L3+ 觸發 emergency exit 與本 AMD 正交 |
| 5 | Authorization 過期/失效 → engine cancel_token shutdown | PASS | engine shutdown 走既有路徑；phys_lock pending decision 在 shutdown 後由 reconciler 接手，與 close path 一致 |
| 6 | Mainnet 無 OPENCLAW_ALLOW_MAINNET → spawn 拒絕 | PASS | 不觸（不改 spawn 邏輯） |
| 7 | Bybit retCode != 0 → fail-closed 不重試 | PASS | 不觸（不改 dispatch error handling） |
| 8 | Reconciler 對賬差異 → 自動降級 paper | PASS | 不觸（不改 reconciler） |
| 9 | Operator 角色與 live_reserved 缺一即拒 | PASS | 不觸（不改 auth 邏輯）；本 AMD enable timing 與 live session start 正交 |

**結論**：9/9 PASS；**0 BLOCKER**；本 AMD 不削弱任何 fail-closed 邊界。

---

## 9. Approval Chain

| Role | Required Action | Status |
|---|---|---|
| **PA** | 本 DRAFT 撰寫 + Gate 3.1-3.6 設計 + §4 風險評估 + §5 counterfactual analysis 要求 | ✅ DRAFT 完成（本檔，2026-05-16） |
| **QC** | (a) §5 counterfactual analysis 跑 demo 86 fires; (b) sensitivity sweep; (c) verdict APPROVE or REJECT with bootstrap CI 證據 | ⏳ Pending（Phase 2b PASS 後啟動） |
| **FA** | 16 原則合規 + business chain impact 評估 + DEFER 立場修訂同意 | ⏳ Pending（QC counterfactual 後同步） |
| **MIT** | counterfactual replay tier verify（'counterfactual_replay' tier 非 ML training surface，per CLAUDE.md §九 non-training surfaces invariant） | ⏳ Pending |
| **BB** | Bybit-side 行為對稱性（demo vs live mainnet fee/slippage/funding regime）evaluate | ⏳ Pending |
| **PM** | 4-agent verdict 收口 + AMD-2026-05-15-02 v0.5 patch 提交（§4 DEFER → SUPERSEDED on land date） | ⏳ Pending |
| **Operator** | 顯式 sign-off in commit message + governance trail | ⏳ Pending（Gate 3.3） |

**強制工作鏈**：PA DRAFT（本檔）→ Phase 2b LiveDemo PASS 等待 → QC counterfactual analysis → FA + MIT + BB 並行 review → PM 收口 + AMD-2026-05-15-02 v0.5 patch → Operator sign-off → land at active amendments folder + 補 slot 編號 + `SPECIFICATION_REGISTER.md` register。

**不接受快速通道**：本 AMD 是 live fail-safe 解除性質，FA / QC / MIT / BB 任一不可省。

---

## 10. 變更歷史

| 日期 | 版本 | 變更 | 作者 |
|---|---|---|---|
| 2026-05-16 | v0.1 DRAFT | 初版 — PA per main session 派 Wave C-3 dispatch；放於 `2026-05-XX-XX-phys-lock-live-enable-draft.md` placeholder filename；**未** land 至 active amendments folder（draft only）；**未** register `SPECIFICATION_REGISTER.md`；pending Phase 2b LiveDemo PASS + QC counterfactual + operator sign-off | PA |

**下一步**：本 DRAFT commit 後等待 (a) Phase 2b LiveDemo PASS empirical evidence (預估 earliest ~2026-06-05 mirror AMD-2026-05-15-02 §3 timeline)；(b) QC 派 counterfactual analysis worker（pre-Phase 2b 可先準備 evidence packet skeleton）；(c) AMD-2026-05-15-02 v0.5 §4 DEFER 立場修訂 patch ready（cosmetic ~0.2h）。**禁止**自動 land；必走 operator 顯式 sign-off。

---

**Report path**: `/Users/ncyu/Projects/TradeBot/srv/docs/governance_dev/amendments/2026-05-XX-XX-phys-lock-live-enable-draft.md`
