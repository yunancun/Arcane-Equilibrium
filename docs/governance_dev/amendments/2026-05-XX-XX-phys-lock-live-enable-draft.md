# Amendment AMD-2026-05-XX-XX — phys_lock Live Enable (DRAFT v0.2)

**對應 spec**: EDGE-P2-3 Phase 1b 後續 · DOC-01 §5.4/§5.5/§5.6/§5.8/§5.16 · DOC-08 §12 · `risk_config_live.toml [exit]` carve-out · `exit_features/v2.rs:125-203` ExitConfig schema · `learning.exit_features` (V029 hypertable) audit SoT
**修訂對象**: AMD-2026-05-15-02 v0.4 §4「phys_lock Live 分軌（不在本 AMD scope 內，DEFER）」立場
**Supersedes**: (none — 本 AMD 是 follow-up，**不直接 supersede** AMD-2026-05-15-02 §4 DEFER 立場；待本 AMD 完整 sign-off + Phase 2b LiveDemo PASS + QC counterfactual gate + Phase 2c LiveDemo Counterfactual Verification 四條件齊備後才生效)
**日期**: 2026-05-16
**作者**: PA per main session 派 Wave C-3 dispatch（pre-Phase 2b future enable AMD draft prep）+ v0.2 consolidation per 4-agent (QC+FA+MIT+BB) short re-review 2026-05-16 verdicts
**狀態**: **DRAFT v0.2 — NOT LANDED** — pending (a) Phase 2b LiveDemo 7d PASS empirical evidence; (b) QC counterfactual analysis demo 86 fires PASS; (c) Phase 2c LiveDemo Counterfactual Verification 7d ≥30 fires PASS; (d) operator 顯式 sign-off; (e) AMD slot 編號補實（per `SPECIFICATION_REGISTER.md` 下一 free slot）
**索引**: 暫不入 `SPECIFICATION_REGISTER.md`（draft only；slot 補實後再 register）
**TODO 連結**: P0-EDGE-1（alpha-deficient regime 下 phys_lock 啟用 trade-off 評估）/ EDGE-P2-3 Phase 1b（close-maker-first Phase 2b 是前置 gate）

**v0.2 變更摘要**：整合 2026-05-16 4-agent (QC+FA+MIT+BB) short re-review 23 items —
- 11 must-fix（QC-MF-1/2 / FA-MF-1 / MIT-MUST-A/B/C/D/E/F/G / BB-PL-1）：全收口
- 12 should-fix（QC-SF-1..4 / FA-SF-1..4 / MIT-SH-H/I / BB-PL-2/3）：全收口
- 3 NTH / cosmetic（QC-NTH-1/2 / FA-Cosmetic）：全收口
- 關鍵 schema 修正：AMD 全篇 `exit_features.physical_decision_logs` → `learning.exit_features WHERE exit_trigger_rule LIKE 'phys_lock_%' OR exit_source='Physical'`（per MIT-MUST-E；schema 命名 bug，IMPL 撈不到資料）
- 新增 Phase 2c LiveDemo Counterfactual Verification（per QC-SF-3，BLOCKER-level）：enable 後 7d observation period，累積 ≥30 fires after live enable 再判定 net positive
- §3 gate stack 7→8（新 Gate 3.7 Mainnet 7 prereq cross-ref + Linux empirical verification merge）
- §5 evidence packet 5→7 條（新 5.1.6 regime stability + 5.1.7 per-strategy minimum fire count）
- §6 加 §6.4 close-maker-first AMD 互動 + §6.5 forensics row retention

---

## 1. Executive Decision

**phys_lock Live 啟用 = 解除 `risk_config_live.toml` 對 `[exit].missing_edge_fallback_bps` 的隱式 fail-safe 後備**（從 Rust default `-10.0` 改為 TOML override `+10.0`，與 demo 對稱）。

**範圍嚴格限定**：本 AMD 僅啟一個 surface 行為改變 — 在 `risk_config_live.toml [exit]` 段加 `missing_edge_fallback_bps = 10.0` override，使 live + LiveDemo 環境的 `exit_features/v2.rs::PhysicalDecision` Gate 1 從「missing edge → effective_edge = -10 < min_net_floor=5 → 永久 Hold」改為「missing edge → effective_edge = +10 ≥ floor → 進 Gate 2+」。其餘 phys_lock 8-gate 鏈條（min_hold_secs / min_peak_atr_norm / stale_peak_ms / giveback_*）參數保持 Rust default 與 demo 一致，**不引入新調參面**。

**啟用語義**：把 demo 7d 觀察到的 86 fires 對應 profit-protection 行為（gate4_giveback / gate4_stale_roc_neg）擴展到 live + LiveDemo，使 phys_lock 從 demo-only 對照實驗轉為三環境一致的 profit-protection 機制。

**Framing 嚴謹性 (per QC §1 transaction cost economics)**：phys_lock = profit-protection（peak ATR giveback / stale ROC neg lock-in），**不是 risk-bypass 也不是新 alpha source**；分類為 `α_holding truncation policy`（per QC round-2 §6 + short re-review §1 transaction cost decomposition）：
```
NetPnL = α_entry + α_holding + α_exit − (fee + slippage + impact + funding)
α_holding = ∫[t_entry, t_exit] dP_favourable(s) ds
phys_lock 干預 = truncate t_exit at peak ATR giveback condition
              = policy on α_holding upper bound + tail-loss truncation
```

phys_lock **不**改變 informational alpha（α_entry/α_exit）；只在 holding window 內以 path-dependent rule 截斷 α_holding 上下尾。經濟效果 = Sharpe-style risk-adjusted return 改善（持倉期望時間縮短 + opportunity cost 降低 + max-DD-per-trade 截斷）。

**Sharpe 改善的數學條件 (per QC-SF-1)**：
```
ΔSharpe > 0  ⇔  σ_reduction × Sharpe_baseline > μ_reduction
```
即 phys_lock 對 NetPnL 分布的影響 = E[NetPnL] 略降 + Var(NetPnL) 顯著降 + tail-loss truncation。Sharpe 上升 = variance reduction term 必須大於 mean shift term；此為本 AMD 經濟假設 hot path 的明文條件，counterfactual analysis（§5）所驗即為此條件在 demo 86 fires + Phase 2c LiveDemo ≥30 fires 上是否成立。

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

**注意**：此估算建立在「live regime 與 demo regime 行為對稱」假設上 — per §4.4 split 評估：phys_lock 觸發層 LOW（per BB-PL-2，Gate 1-4 全 internal state 不依 endpoint）+ close dispatch 層 drift 已由 close-maker-first AMD AC-15/19 + [65] healthcheck 覆蓋。

---

## 3. Pre-enable Conditions（gate stack v0.2 = 7 條 hard + 1 條 Mainnet 子表）

**所有條件必滿足才能將本 DRAFT 轉 Accepted + land 至 active amendments folder + 補 slot 編號**：

| Gate | 證據要求 | 狀態 |
|---|---|---|
| **3.1 Phase 2b LiveDemo PASS** | AMD-2026-05-15-02 §3 Phase 2b 7d 完整觀察 + AC-1..AC-19 (Wilson CI + reject sample + NULL ladder + fallback rate ≥ 95% + 14d close_maker_fill_rate ≥ 30%) + FDR 0.10 BH adjustment 全 PASS | ⏳ Pending（Phase 2b 尚未啟動，等 Phase 2a Demo 14d PASS + IMPL Prereq 6 全解） |
| **3.2 QC Counterfactual Analysis (demo 86 fires)** | QC 跑 demo 86 fires 對應倉位「**不啟用 phys_lock 反事實 PnL**」對比「**啟用 phys_lock 實際 PnL**」 — must show net positive：`counterfactual_PnL_no_lock < actual_PnL_with_lock`。樣本量 n=86 需做 block-bootstrap CI + Wilson CI lower bound + MDE/power calculation；q-value < 0.10 顯著 | ⏳ Pending（§5 evidence packet 強制要求；power+MDE+FDR 三必修 per MIT-MUST-A/B/D） |
| **3.3 Operator 顯式 Sign-off** | Operator 在 commit message + governance trail 明文 approve；不接受 implicit 推導 | ⏳ Pending |
| **3.4 P0-EDGE-1 狀態評估 + 三方聲明（hard sub-criterion per QC-MF-2 + FA-MF-1）** | (a) **demo 14d rolling [40] 不再惡化**（[40] avg_net_bps 不再變更負 vs 14d ago baseline）；(b) **AlphaSurface C1 或 W-AUDIT-8b funding skew 至少 1 候選 Stage 0R `eligible_for_demo_canary=true`**；(c) **若 P0-EDGE-1 在 enable 時點仍 active，PA + QC + FA 三方明文聲明必須引 §5 counterfactual evidence 證 net-positive 在 alpha-deficient regime 下仍成立**（mandatory wording） | ⏳ Pending |
| **3.5 AMD-2026-05-15-02 v0.4 §4 立場修訂** | 本 AMD Accepted 同時提交 AMD-2026-05-15-02 v0.5 補丁，把 §4「DEFER」改為「DEFER until AMD-2026-05-XX-XX SATISFIED → SUPERSEDED on land date」 | ⏳ Pending（提交 v0.5 patch 工作量 ~0.2h cosmetic） |
| **3.6 AMD slot 編號實裝** | per `SPECIFICATION_REGISTER.md` 下一 free slot（land 時 2026-05-XX 對應日）；目前 placeholder `XX-XX`。實裝順序（per FA-Cosmetic）：**先 Phase 2b PASS → QC counterfactual PASS → Phase 2c PASS → operator sign-off → 同 commit 補 slot + register + AMD-2026-05-15-02 v0.5 patch** | ⏳ Pending |
| **3.7 Linux Empirical Verification + Mainnet 7 prereq cross-ref（per QC-SF-2 + BB-PL-1）** | （a-1）ExitConfig ArcSwap hot-reload + RuntimeRiskConfig 路徑必跑 Linux runtime live empirical 驗 1 tick visibility（Mac unit test PASS 不足）；（a-2）Mainnet 7 prereq cross-ref：真實 fee rate verify / rate_limit_remaining baseline / IP whitelist / EarnedTrust T0→T1 / MAG-083/084 ✅ closed / 24h mainnet smoke / kill-switch 物理測試 — 若 LiveDemo-only enable 可保留「pending Phase 3 carve-out AMD」標註；若 Mainnet enable 必 inline 補完 | ⏳ Pending |

**Gate 3.7 子表 — Mainnet 啟用 7 prereq（per BB-PL-1）**：

| # | 條件 | 必檢時點 | 狀態 |
|---|---|---|---|
| 3.7.1 | 真實 fee rate verify（不依賴 demo 推導） | Mainnet enable 前 | ⏳ |
| 3.7.2 | rate_limit_remaining baseline 採集 30d | Mainnet enable 前 | ⏳ |
| 3.7.3 | IP whitelist | Mainnet enable 前 | ⏳ |
| 3.7.4 | EarnedTrust T0→T1 promote | Mainnet enable 前 | ⏳ |
| 3.7.5 | MAG-083 / MAG-084 evidence chain | ✅ Closed 2026-05-11 | ✅ |
| 3.7.6 | 24h mainnet smoke | Mainnet enable 前 | ⏳ |
| 3.7.7 | kill-switch 物理測試（mainnet endpoint 驗 rollback ArcSwap 1 tick 內生效） | Mainnet enable 前 | ⏳ |

**3.7.5 已 closed** per CLAUDE.md §三 + `docs/governance_dev/2026-05-11--w_d_mag084_signoff.md`；其餘 6 條須 inline 補完或標記 "pending Phase 3 carve-out AMD" 接續。若本 AMD 範圍限 LiveDemo enable，3.7.2-3.7.7 可推遲；若延伸 Mainnet enable，必 inline 補完。

**不要求**：W-AUDIT-8a C1 BB/MIT sign-off / W-AUDIT-8b Stage 0R PASS / 任何 alpha-bearing 三閘（本 AMD 是 profit-protection execution-quality optimization 性質，per §1 framing，與 alpha promotion 三閘正交）。但 Gate 3.4 (b) AlphaSurface C1 或 W-AUDIT-8b funding skew Stage 0R `eligible_for_demo_canary=true` 是 P0-EDGE-1 alpha pipeline empty 防禦條件，非 alpha promotion gate。

---

## 4. Risk Assessment

### 4.1 One-flag-per-phase 違反風險（核心）

**現狀**：close-maker-first Phase 1b 是 live 端**已在進行**的 surface 行為改變（Phase 2b live_demo 段，AMD-2026-05-15-02 §3 active）。本 AMD 同 sprint 引入第二個 live surface 改變 → **直接違反 EDGE-P2-3 one-flag-per-phase 模式**（per AMD-2026-05-15-02 §4 DEFER 第 1 條原文）。

**緩解 1**：強制 Gate 3.1 — 本 AMD enable timing 必須在 Phase 2b PASS 之後（即 AMD-2026-05-15-02 §3 Phase 2b 14d 觀察窗結束 + AC 全 PASS + close-maker-first 已 production-stable），保證兩個 live surface 改變不重疊。

**緩解 2**：本 AMD 啟用後立即進入 phys_lock-only 14d observation 窗（Phase 2c LiveDemo Counterfactual Verification，per §5.3），期間禁止其他 live surface flag 翻轉。

**殘留風險**：MEDIUM — 若 Phase 2b 仍在 production 早期（< 4w post-stabilize），observability 干擾依然存在；診斷新事件時可能誤把 close-maker-first 副作用歸因 phys_lock 或反之。

### 4.2 P0-EDGE-1 Alpha-deficient Regime 風險（QC §6 核心反問）

**事實**：5 textbook 策略 30d demo `-110.43` USDT structural alpha-deficient（per CLAUDE.md §三 P0-EDGE-1 active）。

**QC §6 反問**：在 alpha-deficient regime 下，phys_lock 鎖的可能是 **noise 不是真 alpha**：
- 若信號是 noise，peak ATR + giveback 信號本質上是 mean-reversion 後的 random retracement，鎖利相當於 stop-loss-on-favourable-noise；
- 在 random walk regime 下，per-trade Sharpe 改善可能來自 path-dependent timing luck，非 systematic skill；
- **counterfactual_PnL_no_lock** 可能 ≥ actual_PnL_with_lock（即不鎖更好）。

**緩解**：強制 Gate 3.2 + Gate 3.4 — Counterfactual analysis pre-enable + P0-EDGE-1 三方明文聲明引 §5 evidence。具體計算（per §5 evidence packet）：
- 取 demo 86 fires 對應倉位 entry timestamp + qty + side（per MIT-MUST-E schema 命名修正：`learning.exit_features WHERE exit_trigger_rule LIKE 'phys_lock_%' OR exit_source='Physical'`）
- 計算反事實場景 A：fire 時刻不 lock，後續 `min_hold_secs + giveback_window` 結束時 market close → 收 actual close fill price
- 對比實際場景 B：fire 時刻 phys_lock lock → 收 actual lock close fill price
- 計算 86 paired diff（A - B）→ paired block-bootstrap CI 95%（n_bootstrap=1000，block size ≈ √n ≈ 9）
- PASS 條件（per MIT-MUST-A/B/C/D + QC-MF-1 修正）：見 §5.2

**殘留風險**：HIGH — 即使 counterfactual PASS demo regime，live regime 可能行為不對稱（per BB-PL-2 split：phys_lock 觸發層 LOW + close dispatch 層 drift 已由 close-maker-first AMD AC-15/19 覆蓋）。本殘留 HIGH 由 Phase 2c LiveDemo Counterfactual Verification（per §5.3）緩解 — enable 後 7d observation 累積 ≥30 fires after live enable 再判定。

### 4.3 Demo-loose-live-strict 政策違反風險

**事實**：`feedback_demo_loose_live_strict_policy.md` 明示「demo 是學習資料源可放寬；Live 永遠 fail-closed；核心是平衡虧損與盈利，非一味保守」。

**判定**：本 AMD 啟用 = 放寬 live fail-safe → **政策上是 negotiable**（不是禁止），但需 operator carve-out + counterfactual evidence 雙重門控。本 AMD §3 Gate 3.3 operator sign-off + Gate 3.2 counterfactual + Gate 3.4 三方聲明 + §5.3 Phase 2c LiveDemo Counterfactual Verification 即為政策履行。

**殘留風險**：LOW — 政策本身允許 net-positive trade-off；本 AMD 結構正確。

### 4.4 Demo/Live Regime 行為對稱性風險（split per BB-PL-2）

**§2.3 估算「370 fires/月」依賴 demo regime 行為可外推到 live**。Split 評估：

**4.4.1 phys_lock 觸發層（Gate 1-4） — LOW**：
- Gate 1 (`missing_edge_fallback_bps`): 取自 internal edge_estimates state，**與 endpoint 無關** ✅
- Gate 2 (`min_hold_secs ≥ 30`): 取自本地 position 時鐘，**與 endpoint 無關** ✅
- Gate 3 (`min_peak_atr_norm ≥ 0.5`): 取自本地 ATR + peak tracking，**與 endpoint 無關** ✅
- Gate 4 (`giveback_*` / `stale_roc_neg`): 取自本地 peak + ROC 計算，**與 endpoint 無關** ✅

=> phys_lock fire 觸發機制本身對 demo vs mainnet endpoint 完全不敏感。

**4.4.2 close dispatch 層（fire 觸發後的 close maker order） — MEDIUM (already covered)**：
- demo 0 reject sample 可能是 demo silent degradation
- 啟用 live phys_lock 後 live_demo (走 api-demo.bybit.com) 觀察的 close maker fill rate ≠ live mainnet
- **已由 close-maker-first AMD-2026-05-15-02 AC-15/AC-19 + healthcheck [65] 覆蓋**（不重複歸入本 AMD scope）

**緩解**：本 AMD enable 後強制 Phase 2c LiveDemo Counterfactual Verification 14d observation 窗（per §5.3），per-fire 比對 demo baseline；偏差 > rolling 7d 偏離 vs demo baseline 7d（per QC-NTH-2 修正，避日級 noise）觸發 review。

**殘留風險**：LOW（觸發層）+ MEDIUM (close dispatch，但 already covered by AMD-2026-05-15-02 AC-15/19；不在本 AMD scope)。

### 4.5 Mode 變化下 Rust ArcSwap 熱重載行為

**事實**：`ExitConfig` 透過 RuntimeRiskConfig 走 ArcSwap 熱重載（per ARCH-RC1 unified config contract）。

**驗證要點**：TOML hot-reload 觸發後，正在 active 的 `compute_physical_decision()` invocation 是否使用 new config snapshot？per Rust ArcSwap semantic：每次調用 `config.load()` 取當前 snapshot，下一筆 fire 才使用 new value，**不破現有 in-flight decision**。

**Gate 3.7 (a-1) Linux empirical verification required（per QC-SF-2）**：Mac unit test PASS 不足；必跑 Linux runtime live empirical 驗 1 tick visibility（next `compute_physical_decision()` invocation 必取 new snapshot）。

**殘留風險**：LOW — ArcSwap 設計即為此場景，已驗於 close-maker-first Phase 1a entry-side rollout；Linux runtime empirical verify 為最終 gate。

### 4.6 Future Funding Alpha 交互風險 (per QC-NTH-1)

**事實**：W-AUDIT-8b funding skew directional alpha 候選若 future Stage 0R PASS + 上線（W3 + Stage 1 Demo + 後續 LiveDemo），與 phys_lock fire timing 可能交互。

**潛在 hook scenarios**：
- funding settlement 前 30s 內 phys_lock fire + close maker pending → 跨 settlement instant，maker order 在 settlement 時點仍 pending → funding charge 與 close fill 時序耦合
- funding skew alpha 與 phys_lock 同 strategy / symbol 觸發 → 兩個 close decision 路徑競爭

**緩解（advisory，non-blocking 本 AMD）**：W-AUDIT-8b alpha 若 future 上線，需新 AMD 明文 evaluate phys_lock + funding settlement proximity 互動；目前本 AMD enable 時點 W-AUDIT-8b 處於 Stage 0R 設計階段，無互動風險。

**殘留風險**：FUTURE — 不阻塞本 AMD；W-AUDIT-8b 上線時點 reopen evaluate。

---

## 5. Counterfactual Analysis 要求（QC §6 mandate + MIT MUST-A..G + 7 條 evidence packet）

### 5.1 Evidence Packet 強制條目（7 條 per v0.2 patch）

Pre-enable Gate 3.2 必交付 PA → QC → PM sign-off 路徑的 evidence packet：

| 項 | 內容 | Owner |
|---|---|---|
| 5.1.1 | Demo 86 fires 完整列表 (fire_ts / strategy / symbol / qty / entry_price / actual_lock_price / actual_lock_pnl_bps) — **schema source** = `learning.exit_features WHERE exit_trigger_rule LIKE 'phys_lock_%' OR exit_source='Physical'`（per MIT-MUST-E；V029 hypertable 7d chunk，PK=(context_id,ts)）；**demo endpoint vs mainnet endpoint mapping 註腳**（per BB-PL-3）：demo 樣本走 api-demo.bybit.com，mainnet 對應 api.bybit.com — fee tier/slippage/order book depth 差異視 §4.4.2 close dispatch 層由 AMD-2026-05-15-02 AC-15/19 覆蓋 | PA 派 E1 dump from `trading.fills` + `learning.exit_features` JOIN on `context_id` |
| 5.1.2 | 每 fire 反事實場景 A 模擬：不 lock 後 `min_hold_secs + giveback_window` 結束 market close 對應 PnL — **prerequisite**：replay framework 必先支援 **ExitConfig override at replay session level**（counterfactual A 場景 pass `missing_edge_fallback_bps=-10.0` 強制 Gate 1 fail-safe Hold；replay engine 當前 0 native support，須前置 IMPL per MIT-MUST-G）；**evidence_source_tier writer mandate**（per MIT-SH-H）：tag 必為 `'counterfactual_replay'`（V050 enum allowed value），禁誤 tag `'synthetic_replay'`；E3 grep guard rule: `grep -nE "evidence_source_tier='synthetic_replay'" <counterfactual_writer>` 必 0 hit | QC 跑 historical replay；**Linux PG dry-run mandate**（per MIT-SH-I）：dump from Linux PG empirical + sqlx checksum verify + replay session evidence_id tracked + INSERT 走 Linux PG path |
| 5.1.3 | Paired block-bootstrap CI 95% (n=86, n_bootstrap=1000, block size ≈ √n ≈ 9, AR(1) coefficient 1/(1−ρ) 自適應估) + **Wilson 95% CI lower bound 計算**（per MIT-MUST-D；PASS/FAIL 用 Wilson lower bound 比 threshold，不用 point estimate） | QC 跑 + 出報告 `docs/CCAgentWorkSpace/QC/workspace/reports/2026-05-XX--phys_lock_counterfactual_analysis.md` |
| 5.1.4 | **Sensitivity sweep — one-at-a-time（per QC-MF-1 修正）**：3 個 param 各自獨立 sweep，不做 full Cartesian 27 cells。`min_hold_secs ± 50%` / `giveback_floor ± 0.1` / `peak_atr_norm ± 0.2` 各兩端 2 點 → 6 sub-test，每個 n=86 維持 power。**+ BH-FDR q=0.10 family-wise correction**（per MIT-MUST-B；即使 one-at-a-time 6 比較仍須 family-wise control） | QC + PA review |
| 5.1.5 | **Per-symbol breakdown**（per MIT-MUST-C + QC-MF-1 修正）：(i) 只對 fires ≥ 10 symbols 做 per-symbol t-test；(ii) directional threshold = **Wilson-CI lower bound ≥ 50%** as directional positive（不用 70% point estimate）；(iii) ≥10 fires symbols 數量 < 5 時 **跳過此 criterion，僅依賴 (a)(b)(c)(d)**；+ per-strategy breakdown — **minimum-fire-count gate**（per FA-SF-2）：≥ 8 fires/strategy 才納入聲明 | QC |
| 5.1.6 | **Regime stability check（per QC-SF-4）**：取 demo 86 fires 按時序 split 前 43 / 後 43，分別計算 median(A−B)，directional consistency；若兩個 sub-period directional 不一致 → 樣本期 regime mix 不穩，counterfactual 結論 fragile → REJECT 反事實結論 | QC |
| 5.1.7 | **MDE + Power Calculation（per MIT-MUST-A）**：寫死「PASS 要求 with-lock 平均優勢至少 X bps，n=86 power ≥ 0.8」MDE 計算 — for effect size 5 bps 典型 phys_lock 鎖利幅度 n=86 paired bootstrap 約 80% power；effect size 2-5 bps power 降至 30-50% → 明文 MDE = 5 bps 為 PASS 門檻底線 | MIT + QC review |

### 5.2 PASS / FAIL Criteria（per MIT-MUST-A/B/C/D + QC-MF-1）

**PASS** (all 5 必滿足):

1. **median(A − B) < -2 bps**（with-lock 顯著優於 without-lock，至少 2 bps net advantage）+ **Wilson 95% CI lower bound** 在 `median(A-B) < 0` 一致（per MIT-MUST-D）
2. **95% one-sided CI 上限 < 0**（per QC §2 (b)，one-sided directional H1: with-lock better）
3. **MDE-power gate**: n=86 對 effect size ≥ MDE_threshold = 5 bps 的 power ≥ 0.8（per MIT-MUST-A + 5.1.7）
4. **Sensitivity sweep（one-at-a-time 6 sub-test）+ BH-FDR q=0.10**：6 比較全部 q-value < 0.10 + 各偏移下 median(A-B) 仍 < 0（per QC-MF-1 + MIT-MUST-B）
5. **Per-symbol（conditional on ≥10-fires symbols ≥ 5）**：Wilson-CI lower bound ≥ 50% directional positive；≥10 fires symbols 數量 < 5 時跳過此 criterion，僅依賴 1-4
6. **Regime stability check（5.1.6）**：前 43 / 後 43 sub-period directional consistency

**FAIL**（任一觸發 → 本 AMD 永久 REJECT，重啟需新 AMD）:
- median(A - B) ≥ 0 OR Wilson 95% CI lower bound 不顯著
- 95% CI 跨 0
- MDE-power gate FAIL（effect size 太小無法 detect）
- Sensitivity sweep BH-FDR adjusted q-value 任一 ≥ 0.10 OR 任一偏移翻為 median(A-B) ≥ 0
- Per-symbol（適用時）Wilson-CI lower bound < 50%
- Regime stability split sub-period directional 不一致

### 5.3 Phase 2c LiveDemo Counterfactual Verification（BLOCKER-level，per QC-SF-3）

**Pre-enable Gate 3.2 demo 86 fires counterfactual PASS 後**，enable live + LiveDemo phys_lock，**進入 7d observation period**：

| 項 | 內容 |
|---|---|
| 5.3.1 觀察窗 | 7d post-enable continuous observation |
| 5.3.2 Per-fire 即時 counterfactual | 每筆 phys_lock fire（live + live_demo）即時跑 counterfactual replay against same-instant **live order book snapshot**（不是 demo replay）— 即時 dump fire ts 的 best-bid/best-ask + depth + funding rate snapshot，計算 A 場景 PnL；Linux PG empirical path，evidence_source_tier='counterfactual_replay' |
| 5.3.3 累積樣本 gate | **累積 ≥ 30 fires after live enable 再判定 net positive**；< 30 fires → CONDITIONAL (繼續 observation 延長 7d 上限至 14d) |
| 5.3.4 PASS 條件 | live + live_demo 累積 ≥ 30 fires 後重跑 §5.2 全 PASS criteria（含 MDE/Wilson/sensitivity/regime）— PASS → Phase 2c 認定 net-positive；FAIL → rollback per §6.1 |
| 5.3.5 Rollback gate | 觀察窗內 (a) cost_edge_ratio > 0.85 持續 1h+ OR (b) rolling 7d fire rate 偏離 demo baseline 7d > 2σ (per QC-NTH-2 修正，避日級 noise) OR (c) operator override → 立即 rollback |

**Phase 2c 不是 pre-commit gate，但是 BLOCKER-level live observation period**；rollback 雖然 1 tick 內可回，但 14d observation 期間累積虧損可能已物質。Gate 3.2 demo counterfactual PASS = 進 Phase 2c 通行證；Phase 2c PASS = AMD enable 認定為 net-positive 並 land；Phase 2c FAIL = rollback + 本 AMD 永久 REJECT，重啟需新 AMD。

### 5.4 Audit Trail

Evidence packet land 至 git tracked 路徑；QC report + PA verdict + Operator sign-off commit 訊息明文引用 evidence ref + Phase 2c LiveDemo Counterfactual Verification 結束報告 ref。

### 5.5 Advisory（per MIT advisory）

若 Phase 2b 7d 後 demo 樣本擴展至 demo 累積 ~150-200 fires/2w，§5.2 PASS gate 自動升級：MDE_threshold 從 5 bps 降至 3 bps，per-symbol carve-out threshold 從 n≥5 改 n≥7。

---

## 6. Rollback Path

### 6.1 Hot Rollback（< 1 tick）

`risk_config_live.toml [exit]` hot-reload `missing_edge_fallback_bps = -10.0`（或直接 remove override → fall back to Rust default `-10.0`）→ ArcSwap snapshot 1 tick 內生效 → next `compute_physical_decision()` invocation Gate 1 即回 fail-safe Hold → phys_lock 即刻 silent。

**驗證**（per QC-SF-5 修正）：rollback timestamp 後 **fire_ts 累積應為 0**（不是「1h 內 `phys_lock_fires=true` 計數」） — rollback 後新增 row `learning.exit_features WHERE (exit_trigger_rule LIKE 'phys_lock_%' OR exit_source='Physical') AND ts > rollback_ts AND engine_mode IN ('live', 'live_demo')` 計數應為 0；2h+ confirm 無新增 fire。

**Pre-rollback in-flight rows preservation（per FA-SF-3）**：rollback 後既有 `learning.exit_features` 中 rollback 前已 fire 的 row **保留作 forensics**（schema 不刪 row；audit completeness 強制）。

### 6.2 Triggering Conditions

| Trigger | 動作 |
|---|---|
| `phys_lock_live_fire_rate` 與 demo baseline **rolling 7d 偏離 vs demo baseline 7d > 2σ**（per QC-NTH-2 修正，避日級 noise） | 自動 ArcSwap rollback + alert |
| **觀察窗內每日 cost_edge_ratio empirical vs demo baseline diff 表**（per FA-SF-1）：14d observation 窗每日生成 `cost_edge_ratio_live_demo - cost_edge_ratio_demo_baseline_7d` diff；連續 3d 為正且絕對值 > 0.1 → review trigger | PA monitor + 14d empirical diff 表寫至 `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-XX--phys_lock_cost_edge_diff_table.md` |
| Phase 2b LiveDemo close-maker-first regression | 同上（先 rollback phys_lock 隔離變因，再判 close-maker-first 是否獨立 regression） |
| `cost_edge_ratio > 0.85` 持續 1h | rollback（per CLAUDE.md §二 #13 AI cost gate；phys_lock 啟用增加 hold time 可能拉高 cost_edge_ratio） |
| Operator override IPC | rollback |
| Engine cancel_token shutdown | 無需 rollback（authorization 失效 → engine shutdown，pending phys_lock 倉位走 reconciler 路徑） |

### 6.3 Schema Migration 回滾

**無 schema migration**：本 AMD 純 TOML hot-flag 改動，不涉 V### migration / 表結構變更 / fills audit 欄位新增。回滾 = TOML revert，0 schema rollback cost。

### 6.4 In-flight Close-Maker-First Order 互動（per FA-SF-4）

**Rollback phys_lock 時 pending close maker orders 處理**（與 AMD-2026-05-15-02 close-maker-first 互動）：

- ArcSwap rollback **只關 future phys_lock fire**，**不直接 cancel pending close maker orders**
- 已 dispatch 的 pending PostOnly Limit close maker order 走既有 close-maker-first state machine：timeout (15s / 10s per QC-MF-2) → AMD-2026-05-15-02 Race E mandatory fallback to taker market → 成交
- **明文約束**：rollback phys_lock 時，pending close maker order **不應被取消**，繼續走 timeout fallback 邏輯
- 對 Bybit-side：pending order 自然 timeout 後 cancel + market re-dispatch；對 Bybit Order group rate budget = 額外 ~50 req 一次性 burst（per BB §7 量級評估）

### 6.5 Forensics Audit Completeness（per FA-SF-3）

Rollback 後 `learning.exit_features` 中 rollback 前已 fire 的 row 全保留：
- Schema 不刪 row
- `exit_trigger_rule LIKE 'phys_lock_%'` + `exit_source='Physical'` 識別 phys_lock fire
- ts < rollback_ts 的 row 為 pre-rollback fire (preserve)
- ts > rollback_ts 的 row 為 post-rollback bug（應為 0；非 0 → 升 BLOCKER）
- Forensics 用途：rollback 後 post-mortem RCA、AMD failure 評估、未來 reopen AMD 時參考歷史

---

## 7. 16 條根原則合規

| 原則 | 判定 | 機制 / 評估 |
|---|---|---|
| #1 單一寫入口 | PASS | 不觸 IntentProcessor / OrderDispatchRequest 通道；phys_lock 是 close-decision policy，非新寫入口 |
| #2 讀寫分離 | PASS | TOML 寫入仍走 `risk_config_live.toml` SoT；GUI/learning 只讀 |
| #3 AI 輸出 ≠ 即時命令 | PASS | phys_lock 是 Rust 確定性決策（L0 路徑），非 AI 輸出；不繞 Decision Lease（close path 已不寫 lease lineage per W-C Caveat 2） |
| **#4 策略不能繞過風控** | **PASS** | phys_lock = profit-protection（per §1 framing），**非 risk-bypass**；HARD/TRAILING/TIME STOP 等真風控不在 phys_lock 控制路徑（per AMD-2026-05-15-02 §2.3 negative whitelist 強制保 market）；Guardian / SM-04 邊界不受 phys_lock 啟用影響 |
| **#5 生存 > 利潤** | **CONDITIONAL** | profit-protection 鎖利 trade-off：**鎖利減少 max-profit per trade（subordinate to 生存）但同步降低 opportunity cost + max-DD per trade（contribute to 生存）**。Net 評估必走 Gate 3.2 counterfactual + Gate 3.4 P0-EDGE-1 三方聲明 + §5.3 Phase 2c LiveDemo Counterfactual Verification。緩解：§5 evidence packet 7 條 + §5.2 6-criterion FAIL 則拒啟 |
| **#6 失敗默認收縮** | **CONDITIONAL** | 本啟用 = **放寬 live fail-safe**（從 missing_edge=-10 fail-safe Hold → +10 進 Gate 2+ 允許 lock）。需 operator carve-out（per Gate 3.3）+ counterfactual evidence（per Gate 3.2）+ Phase 2c live observation（per §5.3）。緩解：Gate 3.1 Phase 2b PASS 為前置 + Gate 3.4 P0-EDGE-1 status 三方聲明（mandatory wording） + Gate 3.7 Linux empirical + Mainnet 7 prereq cross-ref |
| #7 學習 ≠ 改寫 Live | PASS | TOML override 是 operator 手動配置，**非** ML / DreamEngine / ExecutorAgent 自動寫；走 git tracked governance 路徑；**phys_lock fire metadata 禁餵 ML training feature**（per MIT-MUST-F；non-training surface invariant） |
| **#8 交易可解釋** | **PASS** | phys_lock fire 在 `learning.exit_features` 有完整 audit row（per MIT-MUST-E schema 命名修正；V029 hypertable + `exit_source='Physical'` + `exit_trigger_rule` 帶 `phys_lock_*` prefix）；本 AMD 啟用後 audit 行為不變，只是 row 量從 demo-only 擴展至 live + LiveDemo |
| #9 災難保護 | PASS | engine shutdown / cancel_token / authorization 失效 → reconciler 接手 pending close；phys_lock 不在 disaster-recovery 路徑 critical chain |
| #10 認知誠實 | PASS | 本 AMD §4 明文「事實 / 推斷 / 假設」分類；§5.1.4 sensitivity sweep + §5.1.6 regime stability check 對抗 假設不穩風險；§4.4 split per BB-PL-2 對抗 demo/live regime 假設過於樂觀 |
| #11 Agent 最大自主權 | PASS | P0/P1 硬邊界（HARD STOP / TRAILING / TIME STOP / DAILY LOSS）不變；phys_lock 是 close-decision policy，Agent 自主決定 timing / symbol / 策略不受影響 |
| #12 持續進化 | PASS | 不變動學習平面；不影響 outcome_backfill / evolution_*；phys_lock metadata non-training surface invariant 保 learning vs live 平面隔離 |
| #13 AI 資源成本感知 | CONDITIONAL | phys_lock 啟用可能拉長平均 hold time → 提升 attention_tax → 可能拉高 cost_edge_ratio。緩解：§6.2 rollback trigger `cost_edge_ratio > 0.85 1h+ → rollback` + **14d observation 窗內每日 cost_edge_ratio empirical vs demo baseline diff 表**（per FA-SF-1）；觀察期內 PA monitor cost_edge_ratio drift |
| #14 零外部成本可運行 | PASS | L0 確定性路徑（Rust phys_lock）不依賴 L1 Ollama / L2 Claude |
| #15 多 Agent 協作 | PASS | 不變動 5-Agent 架構 / Conductor 編排 / agent topic |
| #16 組合級風險意識 | PASS | phys_lock 影響 per-trade hold time + max-DD，不影響 portfolio_var / correlation gate 計算 SoT；不引入新 portfolio risk vector |

**結論**：16/16 PASS or PASS-with-stated-mitigation；**3 條 CONDITIONAL** (#5 / #6 / #13) 全部由 §3 pre-enable conditions（7 條 hard + Mainnet 7 prereq 子表）+ §5 counterfactual evidence packet (7 條) + §5.3 Phase 2c LiveDemo Counterfactual Verification + §6 rollback path mitigate；**0 BLOCKER**。

---

## 8. 9 條安全不變量逐條評估（CLAUDE.md §四 + DOC-08 §12）

| # | 不變量 | 判定 | 機制 |
|---|---|---|---|
| 1 | Pre-trade audit/replay 必開 | PASS | phys_lock decision 已有 `learning.exit_features` audit row（per MIT-MUST-E schema 修正：`exit_trigger_rule LIKE 'phys_lock_%' OR exit_source='Physical'`）；本 AMD 不改 audit pathway |
| 2 | Lease 必在執行前已 acquired | PASS | close path 不依賴 lease（per W-C Caveat 2）；phys_lock fire 走 close path 同樣不觸 lease |
| 3 | 執行回報必落 fills 表 | PASS | phys_lock-triggered close 走 OrderDispatchRequest → `trading.fills` INSERT，與其他 close path 同 |
| 4 | 風控降級 → engine 自動止血 | PASS | HARD/TRAILING/TIME STOP 不在 phys_lock 控制路徑；SM-04 escalate L3+ 觸發 emergency exit 與本 AMD 正交 |
| 5 | Authorization 過期/失效 → engine cancel_token shutdown | PASS | engine shutdown 走既有路徑；phys_lock pending decision 在 shutdown 後由 reconciler 接手，與 close path 一致 |
| 6 | Mainnet 無 OPENCLAW_ALLOW_MAINNET → spawn 拒絕 | PASS | 不觸（不改 spawn 邏輯）；Mainnet enable 走 Gate 3.7 7 prereq 子表（per BB-PL-1） |
| 7 | Bybit retCode != 0 → fail-closed 不重試 | PASS | 不觸（不改 dispatch error handling） |
| 8 | Reconciler 對賬差異 → 自動降級 paper | PASS | 不觸（不改 reconciler） |
| 9 | Operator 角色與 live_reserved 缺一即拒 | PASS | 不觸（不改 auth 邏輯）；本 AMD enable timing 與 live session start 正交 |

**結論**：9/9 PASS；**0 BLOCKER**；本 AMD 不削弱任何 fail-closed 邊界。

---

## 9. Approval Chain

| Role | Required Action | Status |
|---|---|---|
| **PA** | (a) 本 DRAFT 撰寫 + Gate 3.1-3.7 設計 + §4 風險評估 + §5 counterfactual analysis 要求；(b) v0.2 consolidation per 4-agent (QC+FA+MIT+BB) 23 items | ✅ DRAFT v0.1 完成 2026-05-16；✅ v0.2 consolidation 完成 2026-05-16 |
| **QC** | (a) §5 counterfactual analysis 跑 demo 86 fires; (b) sensitivity sweep one-at-a-time + BH-FDR; (c) Wilson CI lower bound; (d) regime stability check; (e) Phase 2c LiveDemo Counterfactual Verification 7d observation 結束報告; (f) verdict APPROVE or REJECT with bootstrap CI 證據 | ⏳ Pending（Phase 2b PASS 後啟動） |
| **FA** | 16 原則合規 + business chain impact 評估 + DEFER 立場修訂同意 + Gate 3.4 三方聲明 mandatory wording confirm + cost_edge_ratio empirical diff 表 review | ⏳ Pending（QC counterfactual 後同步） |
| **MIT** | counterfactual replay tier verify（'counterfactual_replay' tier 非 ML training surface，per CLAUDE.md §九 non-training surfaces invariant）+ non-training surface invariant E3 grep guard rule verify + Linux PG dry-run snapshot + sqlx checksum verify + replay session evidence_id tracked + replay framework ExitConfig override IMPL accept | ⏳ Pending |
| **BB** | Bybit-side 行為對稱性（demo vs live mainnet fee/slippage/funding regime）evaluate + Mainnet 7 prereq 子表 status verify | ⏳ Pending |
| **PM** | 4-agent verdict 收口 + AMD-2026-05-15-02 v0.5 patch 提交（§4 DEFER → SUPERSEDED on land date）+ slot 編號實裝順序執行 | ⏳ Pending |
| **Operator** | 顯式 sign-off in commit message + governance trail | ⏳ Pending（Gate 3.3） |

**強制工作鏈**：PA DRAFT v0.1（本檔 v0.1）→ 4-agent (QC+FA+MIT+BB) short re-review（2026-05-16 完成）→ PA v0.2 consolidation（本檔 v0.2，2026-05-16 完成）→ Phase 2b LiveDemo PASS 等待 → QC counterfactual analysis (demo 86 fires) → FA + MIT + BB 並行 review → PM 收口 → operator sign-off → Phase 2c LiveDemo Counterfactual Verification 7d observation → 最終 land at active amendments folder + 補 slot 編號 + `SPECIFICATION_REGISTER.md` register + AMD-2026-05-15-02 v0.5 patch。

**不接受快速通道**：本 AMD 是 live fail-safe 解除性質，FA / QC / MIT / BB 任一不可省。

---

## 10. 變更歷史

| 日期 | 版本 | 變更 | 作者 |
|---|---|---|---|
| 2026-05-16 | v0.1 DRAFT | 初版 — PA per main session 派 Wave C-3 dispatch；放於 `2026-05-XX-XX-phys-lock-live-enable-draft.md` placeholder filename；**未** land 至 active amendments folder（draft only）；**未** register `SPECIFICATION_REGISTER.md`；pending Phase 2b LiveDemo PASS + QC counterfactual + operator sign-off | PA |
| 2026-05-16 | v0.2 DRAFT | **v0.2 consolidation** per 4-agent (QC+FA+MIT+BB) short re-review 23 items 整合 — 11 must-fix（QC-MF-1/2 / FA-MF-1 / MIT-MUST-A/B/C/D/E/F/G / BB-PL-1）全收口；12 should-fix（QC-SF-1..4 / FA-SF-1..4 / MIT-SH-H/I / BB-PL-2/3）全收口；3 NTH/cosmetic（QC-NTH-1/2 / FA-Cosmetic）全收口；**關鍵 schema 修正**：AMD 全篇 `exit_features.physical_decision_logs` → `learning.exit_features WHERE exit_trigger_rule LIKE 'phys_lock_%' OR exit_source='Physical'`（MIT-MUST-E；schema 命名 bug，IMPL 撈不到資料）；**新增 §5.3 Phase 2c LiveDemo Counterfactual Verification**（QC-SF-3，BLOCKER-level，enable 後 7d observation 累積 ≥ 30 fires 再判定）；§3 gate stack 6→7 + Gate 3.7 Mainnet 7 prereq 子表；§5 evidence packet 5→7 條（新 5.1.6 regime stability + 5.1.7 MDE/power calculation）；§6 加 §6.4 close-maker-first AMD 互動 + §6.5 forensics row retention；§1 補 Sharpe 改善數學條件（QC-SF-1）；§4.4 split per BB-PL-2 phys_lock 觸發層 LOW + close dispatch 層 MEDIUM (already covered)；§4.6 future funding alpha 交互 hook（QC-NTH-1）；§6.2 rolling 7d 偏離（QC-NTH-2 取代 2σ daily） | PA |

**下一步**：本 DRAFT v0.2 commit 後等待 (a) Phase 2b LiveDemo PASS empirical evidence (預估 earliest ~2026-06-05 mirror AMD-2026-05-15-02 §3 timeline)；(b) QC 派 counterfactual analysis worker（pre-Phase 2b 可先準備 evidence packet skeleton；7 條 5.1.1-5.1.7 全條目）；(c) MIT 派 replay framework ExitConfig override IMPL（MIT-MUST-G 前置）；(d) AMD-2026-05-15-02 v0.5 §4 DEFER 立場修訂 patch ready（cosmetic ~0.2h）。**禁止**自動 land；必走 operator 顯式 sign-off + Phase 2c LiveDemo Counterfactual Verification 7d observation PASS。

---

**Report path**: `/Users/ncyu/Projects/TradeBot/srv/docs/governance_dev/amendments/2026-05-XX-XX-phys-lock-live-enable-draft.md`
