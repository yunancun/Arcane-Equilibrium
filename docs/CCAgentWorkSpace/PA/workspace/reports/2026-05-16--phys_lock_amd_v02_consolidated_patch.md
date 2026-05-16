# PA Verdict — phys_lock Live Enable AMD v0.2 Consolidated Patch

**Date**: 2026-05-16
**Author**: PA (Project Architect)
**Subject**: AMD DRAFT v0.1 → v0.2 consolidated patch — integrate 4-agent (QC + FA + MIT + BB) short re-review 2026-05-16 verdicts
**AMD path**: `/Users/ncyu/Projects/TradeBot/srv/docs/governance_dev/amendments/2026-05-XX-XX-phys-lock-live-enable-draft.md`
**4-agent verdict commit ref**: `a26c1ed9` (2026-05-16)
**v0.2 status**: **DRAFT — NOT LANDED**（per task constraint；pending operator sign-off + Phase 2b PASS + QC counterfactual + Phase 2c LiveDemo Counterfactual Verification）

---

## §1 Verdict 概述

### **CONSOLIDATED — v0.2 DRAFT 完成**

**23 items 100% integrated** (11 must + 12 should + 3 NTH/cosmetic)，無新增 BLOCKER；4-agent 結構性反饋全部 reflected at AMD §1-§10 對應段落。v0.2 vs v0.1 差異：

| 維度 | v0.1 | v0.2 |
|---|---|---|
| §3 gate stack | 6 條 | **7 條**（新 Gate 3.7 Linux empirical + Mainnet 7 prereq cross-ref + 子表） |
| §5 evidence packet | 5 條（5.1.1-5.1.5） | **7 條**（新 5.1.6 regime stability + 5.1.7 MDE/power） |
| §5.2 PASS criteria | 4 條（a-d）+ point estimate | **6 條 + Wilson CI lower bound + MDE/power + BH-FDR + per-symbol gate (conditional)** |
| §5.3 LiveDemo Counterfactual | （無） | **新增 BLOCKER-level Phase 2c 7d observation period（≥30 fires after live enable）** |
| §6 rollback | 6.1 / 6.2 / 6.3 | **+ §6.4 in-flight close-maker-first 互動 + §6.5 forensics row retention** |
| Schema 命名 | `exit_features.physical_decision_logs`（**不存在表**） | **`learning.exit_features WHERE exit_trigger_rule LIKE 'phys_lock_%' OR exit_source='Physical'`** |
| §1 framing | α_holding truncation policy | **+ Sharpe 改善數學條件 σ_reduction × Sharpe_baseline > μ_reduction** |
| §4.4 demo/live regime | MEDIUM 單一 | **Split：觸發層 LOW + close dispatch 層 MEDIUM (already covered)** |
| §4 risk items | 4.1-4.5 | **+ §4.6 future funding alpha 交互 hook** |
| §6.2 trigger threshold | 2σ daily | **rolling 7d 偏離 vs demo baseline 7d** |

**結論**：v0.2 DRAFT 是 4-agent 對抗審核完整收口版本；下次接續工作 = Phase 2b LiveDemo PASS 後啟動 QC counterfactual analysis 走 §5 7 條 evidence packet。

---

## §2 Item-to-Section Mapping Table（23 items）

### 11 MUST-FIX（block AMD land）

| Item | AMD section diff | 變更詳述 |
|---|---|---|
| **QC-MF-1** § 5.2 (c) sensitivity sweep + (d) per-symbol 70% | **§5.1.4** + **§5.1.5** + **§5.2 PASS criteria** | (c) `min_hold_secs ± 50%` / `giveback_floor ± 0.1` / `peak_atr_norm ± 0.2` 從 27 cells full Cartesian → **6 sub-test one-at-a-time**（每個 n=86 維持 power）；(d) per-symbol 70% → **fires ≥ 10 symbols only + Wilson-CI lower bound ≥ 50% directional positive + ≥10-fires symbols < 5 時跳過 criterion** |
| **QC-MF-2** Gate 3.4 P0-EDGE-1 sub-criterion 升 hard | **§3 Gate 3.4** | 補 (a) **demo 14d rolling [40] 不再惡化** + (b) **AlphaSurface C1 或 W-AUDIT-8b funding skew 至少 1 候選 Stage 0R `eligible_for_demo_canary=true`** 雙條件 |
| **FA-MF-1** Gate 3.4 三方聲明 mandatory wording 升 + P0-EDGE-1 active 引 §5 counterfactual evidence | **§3 Gate 3.4 (c)** | 補「**若 P0-EDGE-1 在 enable 時點仍 active，PA + QC + FA 三方明文聲明必須引 §5 counterfactual evidence 證 net-positive 在 alpha-deficient regime 下仍成立**」mandatory wording |
| **MIT-MUST-A** §5.2 加 MDE + power calculation | **§5.1.7** + **§5.2 PASS criterion 3** | 新增 §5.1.7 evidence packet 條目 — 寫死「PASS 要求 with-lock 平均優勢至少 X bps，n=86 power ≥ 0.8」MDE = 5 bps；§5.2 PASS criterion 3 引此 gate |
| **MIT-MUST-B** §5.1.4 sensitivity sweep BH-FDR q=0.10 family-wise correction | **§5.1.4** + **§5.2 PASS criterion 4** | sensitivity sweep one-at-a-time 6 比較全部 BH-FDR adjusted q-value < 0.10；FAIL 條件對應更新 |
| **MIT-MUST-C** §5.2 per-symbol Wilson-CI sample-size gate (n<5 NEUTRAL) | **§5.1.5** | per-symbol 加 Wilson-CI sample-size gate；fires < 10 symbols 不計入；≥10 fires symbols < 5 時跳過此 criterion |
| **MIT-MUST-D** §5.2 PASS/FAIL 用 Wilson 95% CI lower bound | **§5.1.3** + **§5.2 PASS criterion 1** | §5.1.3 evidence packet 寫死 + Wilson 95% CI lower bound 計算；§5.2 PASS criterion 1 用 Wilson lower bound 比 threshold (不用 point estimate) |
| **MIT-MUST-E (CRITICAL schema bug)** schema 命名修正 | **全 AMD**（§5.1.1 / §6.1 / §6.5 / §7 #8 / §8 #1） | AMD 全篇 `exit_features.physical_decision_logs` → **`learning.exit_features WHERE exit_trigger_rule LIKE 'phys_lock_%' OR exit_source='Physical'`**（V029 hypertable + V086 enum allowed value 已驗證；writer at `database/exit_feature_writer.rs:123`） |
| **MIT-MUST-F** non-training surface invariant + E3 grep guard | **§7 #7** + **Approval Chain MIT row** | §7 #7 加「phys_lock fire metadata 禁餵 ML training feature；`realized_net_bps` (ex-post 真實 label) 仍合法 label source」；MIT approval row 加「non-training surface invariant E3 grep guard rule verify」 |
| **MIT-MUST-G** §5.1.2 replay framework ExitConfig override at replay session level (IMPL 前置) | **§5.1.2** + **Approval Chain MIT row** | §5.1.2 evidence packet 明寫 **prerequisite**：replay framework 必先支援 ExitConfig override at replay session level（counterfactual A 場景 pass `missing_edge_fallback_bps=-10.0` 強制 Gate 1 fail-safe Hold）；MIT approval row 加 "replay framework ExitConfig override IMPL accept" gate |
| **BB-PL-1** §3 Gate 3.7 Mainnet 7 prereq cross-ref | **§3 Gate 3.7** + **§3 Gate 3.7 子表** | 新增 Gate 3.7（合併 QC-SF-2 Linux empirical + BB-PL-1 Mainnet 7 prereq）；7 prereq 子表 inline 列 (a) 真實 fee rate verify / (b) rate_limit_remaining baseline / (c) IP whitelist / (d) EarnedTrust T0→T1 / (e) MAG-083/084 ✅ closed / (f) 24h mainnet smoke / (g) kill-switch 物理測試；3.7.5 已 closed，其餘 6 條標 "pending Phase 3 carve-out AMD"（若 LiveDemo-only enable 可推遲；若 Mainnet enable 必 inline 補完） |

### 12 SHOULD-FIX

| Item | AMD section diff | 變更詳述 |
|---|---|---|
| **QC-SF-1** §1 補 Sharpe 改善數學機制 | **§1 framing** | 補「σ_reduction × Sharpe_baseline > μ_reduction」Sharpe 上升條件數學表達式 |
| **QC-SF-2** Gate 3.7 Linux empirical verification | **§3 Gate 3.7 (a-1)** + **§4.5** | 合併入 Gate 3.7 (a-1)（與 BB-PL-1 Mainnet 7 prereq cross-ref 共同新 gate）；§4.5 ArcSwap mode 改動 + Linux runtime empirical 驗 1 tick visibility 要求明文 |
| **QC-SF-3 (BLOCKER level)** Phase 2c LiveDemo Counterfactual Verification | **§5.3** | 新增 §5.3 整段 — enable 後 7d post-enable continuous observation；per-fire 即時 counterfactual replay against same-instant **live order book snapshot**；累積 ≥ 30 fires after live enable 再判定 net positive；< 30 fires 延長至 14d 上限；PASS = 重跑 §5.2 6-criterion 全 PASS；FAIL = rollback per §6.1 + AMD 永久 REJECT |
| **QC-SF-4** §5.1.6 Regime stability check | **§5.1.6** | 新增 evidence packet 條目 — demo 86 fires 按時序 split 前 43 / 後 43，分別計算 median(A−B)，directional consistency；若 sub-period directional 不一致 → REJECT |
| **QC-SF-5** §6.1 rollback verification timestamp fix | **§6.1** | 「rollback 後 1h `phys_lock_fires=true` 計數應為 0」→ **「rollback timestamp 後 fire_ts 累積應為 0」**（不是「1h 內計數」） |
| **FA-SF-1** §4.2 + §6.2 14d cost_edge_ratio empirical vs demo baseline diff 表 | **§6.2 trigger 表新行** + **§7 #13** | §6.2 加 trigger 條目 — 14d observation 窗每日生成 `cost_edge_ratio_live_demo - cost_edge_ratio_demo_baseline_7d` diff；連續 3d 為正且絕對值 > 0.1 → review trigger；#13 加同樣文字 |
| **FA-SF-2** §5.1 QC counterfactual per-strategy minimum-fire-count | **§5.1.5** | 加 per-strategy minimum-fire-count gate — **≥ 8 fires/strategy 才納入聲明** |
| **FA-SF-3** §6.1 rollback 後既有 `learning.exit_features` row 保留作 forensics | **§6.1** + **§6.5** | §6.1 補「Pre-rollback in-flight rows preservation」明文；§6.5 新增 整段 "Forensics Audit Completeness" 明文 row preservation 規則 |
| **FA-SF-4** §6.4 close-maker-first AMD 互動處理 | **§6.4** | 新增 §6.4 整段 — rollback phys_lock 時 pending close maker orders **不應被取消**；走 timeout fallback 邏輯；引 AMD-2026-05-15-02 Race E |
| **MIT-SH-H** §5.1.2 evidence_source_tier writer mandate + E3 grep guard | **§5.1.2** | §5.1.2 加「evidence_source_tier writer mandate：tag 必為 `'counterfactual_replay'`，禁誤 tag `'synthetic_replay'`；E3 grep guard rule: `grep -nE "evidence_source_tier='synthetic_replay'" <counterfactual_writer>` 必 0 hit」 |
| **MIT-SH-I** §5.1.2 / §5.3 Linux PG dry-run snapshot + sqlx checksum + replay session evidence_id tracked | **§5.1.2** + **§5.3.2** | §5.1.2 加「Linux PG dry-run mandate：dump from Linux PG empirical + sqlx checksum verify + replay session evidence_id tracked + INSERT 走 Linux PG path」；§5.3.2 同樣 Linux PG empirical path |
| **BB-PL-2** §4.4 Demo/Live regime split | **§4.4** | §4.4 拆 4.4.1（phys_lock 觸發層 LOW，Gate 1-4 全 internal state 不依 endpoint）+ 4.4.2（close dispatch 層 MEDIUM (already covered by AMD-2026-05-15-02 AC-15/19 + healthcheck [65]，不重複歸入本 AMD scope)） |
| **BB-PL-3** §5.1.1 demo endpoint vs mainnet endpoint mapping 註腳 | **§5.1.1** | §5.1.1 加註腳：「demo 樣本走 api-demo.bybit.com，mainnet 對應 api.bybit.com — fee tier/slippage/order book depth 差異視 §4.4.2 close dispatch 層由 AMD-2026-05-15-02 AC-15/19 覆蓋」 |

### 3 NTH / Cosmetic

| Item | AMD section diff | 變更詳述 |
|---|---|---|
| **QC-NTH-1** §4 risk item 4.6 Future funding alpha (W-AUDIT-8b) 上線 phys_lock + funding settlement proximity 交互 hook | **§4.6** | 新增 §4.6 整段 — W-AUDIT-8b funding skew alpha 候選若 future Stage 0R PASS + 上線後，與 phys_lock fire timing 可能交互（funding settlement 前 30s 內 phys_lock fire + close maker pending → 跨 settlement instant；funding skew alpha 與 phys_lock 同 strategy / symbol 觸發 → 兩個 close decision 路徑競爭）；advisory non-blocking 本 AMD；W-AUDIT-8b 上線時點 reopen evaluate |
| **QC-NTH-2** §6.2 trigger threshold rolling 7d 偏離 vs demo baseline 7d | **§6.2** + **§5.3.5** | §6.2 trigger 「`phys_lock_live_fire_rate` 與 demo baseline 7d 偏離 > 2σ」→ **「rolling 7d 偏離 vs demo baseline 7d > 2σ」**（避日級 noise）；§5.3.5 Rollback gate (b) 同樣修正 |
| **FA-Cosmetic** AMD slot 編號實裝順序明文 | **§3 Gate 3.6** + **§9 強制工作鏈** | §3 Gate 3.6 補「實裝順序：**先 Phase 2b PASS → QC counterfactual PASS → Phase 2c PASS → operator sign-off → 同 commit 補 slot + register + AMD-2026-05-15-02 v0.5 patch**」；§9 強制工作鏈完整描述工作流 |

---

## §3 副作用識別 + 風險

### 3.1 副作用清單

對 v0.2 整合做副作用分析（per PA 副作用識別清單）：

1. **有沒有其他模塊 import 了相關 schema 名稱**？
   - **YES**：`database/exit_feature_writer.rs:123` INSERT INTO `learning.exit_features`；`tick_pipeline/pipeline_helpers.rs:498` parse exit_tag → `exit_source` / `exit_trigger_rule`；`tick_pipeline/mod.rs:1148` `parse_exit_tag(close_tag)` 解析 `phys_lock_*` prefix
   - **影響**：v0.2 schema 命名修正 **僅是 AMD 文檔文字修正**，**不改 Rust writer 代碼**；writer 已正確寫 `learning.exit_features` + `exit_trigger_rule LIKE 'phys_lock_%'`。Schema bug 是 AMD v0.1 文檔錯字，不是代碼 bug。
   - **0 副作用至 IMPL**

2. **改動的函數在哪些測試中被 mock**？
   - **v0.2 AMD 純文檔更新，不觸代碼**
   - 後續 IMPL（Phase 2b PASS 後）的 replay framework ExitConfig override（MIT-MUST-G 前置）是 future work，**不在本 PA verdict scope**

3. **是否涉及 asyncio/threading 混用邊界**？NO — 純 AMD 文檔。

4. **是否改動 API response schema**？NO。

5. **是否觸 RustEngine ↔ Python IPC schema**？NO。

### 3.2 v0.2 reframed risk inventory

| 風險 | v0.1 評估 | v0.2 評估 | 緩解機制 |
|---|---|---|---|
| One-flag-per-phase 違反 | MEDIUM | MEDIUM (unchanged) | Gate 3.1 + 14d phys_lock-only observation 窗（per §5.3 7d post-enable continuous observation） |
| P0-EDGE-1 alpha-deficient regime | HIGH | **HIGH (緩解強化)** | Gate 3.2 + Gate 3.4 三方聲明 mandatory wording + §5.3 Phase 2c LiveDemo Counterfactual Verification ≥30 fires after live enable |
| Demo-loose-live-strict policy | LOW | LOW (unchanged) | Operator carve-out + counterfactual + Phase 2c |
| Demo/Live regime asymmetry | MEDIUM | **LOW (觸發層) + MEDIUM (close dispatch，但 already covered)** | §4.4 split per BB-PL-2；不重複歸入本 AMD scope |
| ArcSwap mode 變化 | LOW | LOW (unchanged) | Gate 3.7 (a-1) Linux runtime empirical 1 tick visibility 驗 |
| Future funding alpha 交互 | (未評估) | **FUTURE** | §4.6 advisory；W-AUDIT-8b 上線時點 reopen |
| Replay framework ExitConfig override 0 native support | (未評估) | **HIGH (IMPL 前置)** | MIT-MUST-G 明寫 prerequisite；§5.1.2 IMPL accept gate；MIT approval chain row |
| Schema 命名 bug (IMPL 撈不到資料) | (未識別) | **MITIGATED v0.2** | 全 AMD 修正 `learning.exit_features WHERE ...` |
| In-flight close-maker-first 互動 | (未評估) | **LOW** | §6.4 明文 rollback phys_lock 時 pending close maker order 不被取消 |
| Forensics audit completeness | (未評估) | **LOW** | §6.5 明文 row preservation 規則 |

---

## §4 E1 Dispatch 影響評估（後續 IMPL）

**本 AMD v0.2 = 純文檔更新，0 E1 dispatch needed**。

未來 IMPL 派工（Phase 2b PASS 後啟動）：

1. **MIT-MUST-G prerequisite**：replay framework ExitConfig override at replay session level
   - **派工對象**: E1 (Rust replay engine) — 設計 `ReplaySession::override_exit_config(missing_edge_fallback_bps)` API
   - **預估工時**: 6-8h（含 unit test）
   - **副作用**: 影響 `rust/openclaw_engine/src/replay/*.rs` apply_fill / pipeline 模組
   - **E2 重點審查**: ExitConfig snapshot life-cycle in replay session；replay 結果不污染 production ExitConfig

2. **QC counterfactual analysis run**: 5.1.1-5.1.7 7 條 evidence packet
   - **派工對象**: QC + PA dump fires + Linux PG empirical
   - **預估工時**: 12-16h（含 86 fires dump + replay 86 次 + paired bootstrap + Wilson CI + BH-FDR + per-symbol + regime stability + MDE/power）
   - **副作用**: 寫入 `replay.simulated_fills` with `evidence_source_tier='counterfactual_replay'` 86 row

3. **Phase 2c LiveDemo Counterfactual Verification 7d observation**
   - **派工對象**: PA monitoring + QC 結束報告
   - **預估工時**: 7d wall-clock + 4h final report

---

## §5 E2 重點審查 3 點（未來 IMPL）

**本 AMD v0.2 = 純文檔，無 E2 IMPL 審查 needed**；下列為未來 replay framework ExitConfig override IMPL（MIT-MUST-G 前置）E2 必查項：

1. **ExitConfig snapshot 隔離**：replay session 設置的 `missing_edge_fallback_bps=-10.0` override **不能洩漏到 production ArcSwap snapshot**；replay session 結束 ExitConfig snapshot 必 drop；E2 必驗 `cargo test` 覆蓋 replay session 並發 production 路徑無 cross-contamination

2. **evidence_source_tier writer mandate**：replay simulated_fills INSERT 必 tag `'counterfactual_replay'`；E3 grep guard `grep -nE "evidence_source_tier='synthetic_replay'" <counterfactual_writer>` 必 0 hit

3. **Linux PG dry-run mandate**：counterfactual analysis 跑 Linux PG empirical path（不 Mac mock）；E2 必驗 schema reflection（V029 `learning.exit_features` + V050 `replay.simulated_fills` + V086 close_reason_code enum）

---

## §6 16 條根原則 v0.2 合規重評

| 原則 | v0.1 | v0.2 | 變化說明 |
|---|---|---|---|
| #1 單一寫入口 | PASS | PASS | 無變化 |
| #2 讀寫分離 | PASS | PASS | 無變化 |
| #3 AI 輸出 ≠ 命令 | PASS | PASS | 無變化 |
| #4 策略不繞風控 | PASS | PASS | 無變化 |
| **#5 生存 > 利潤** | CONDITIONAL | CONDITIONAL **(緩解強化)** | + §5.3 Phase 2c LiveDemo Counterfactual Verification + §5.2 6-criterion FAIL → REJECT |
| **#6 失敗默認收縮** | CONDITIONAL | CONDITIONAL **(緩解強化)** | + Gate 3.4 三方聲明 mandatory wording + Gate 3.7 Linux empirical |
| #7 學習 ≠ 改寫 Live | PASS | PASS **(強化)** | + non-training surface invariant 明文 (MIT-MUST-F) |
| **#8 交易可解釋** | PASS | PASS **(強化)** | + schema 命名修正（MIT-MUST-E）+ forensics row retention（FA-SF-3） |
| #9 災難保護 | PASS | PASS | 無變化 |
| #10 認知誠實 | PASS | PASS **(強化)** | + §4.4 split (BB-PL-2) + §4.6 future funding alpha + §5.1.6 regime stability check |
| #11 P0/P1 自主 | PASS | PASS | 無變化 |
| #12 持續進化 | PASS | PASS | non-training surface invariant 保 learning vs live 平面隔離 |
| #13 AI cost 感知 | CONDITIONAL | CONDITIONAL **(緩解強化)** | + 14d cost_edge_ratio empirical diff 表（FA-SF-1） |
| #14 零外部成本 | PASS | PASS | 無變化 |
| #15 多 Agent 協作 | PASS | PASS | 無變化 |
| #16 組合風險 | PASS | PASS | 無變化 |

**結論**：v0.2 16/16 PASS or PASS-with-strengthened-mitigation；3 CONDITIONAL 全強化；**0 新增 BLOCKER**。

---

## §7 PA Final Verdict

### **v0.2 DRAFT CONSOLIDATED — APPROVED for STAGING**

**結論**：
- 23 items 全收口（11 must + 12 should + 3 NTH/cosmetic）
- AMD 全篇 schema 命名修正（MIT-MUST-E critical bug）
- 新 §5.3 Phase 2c LiveDemo Counterfactual Verification BLOCKER-level gate（QC-SF-3）
- §3 gate stack 6→7 + Gate 3.7 Mainnet 7 prereq 子表
- §5 evidence packet 5→7 條
- §6 加 §6.4 + §6.5
- §1 framing 補 Sharpe 數學條件
- §4.4 split + §4.6 future funding alpha hook
- §6.2 rolling 7d 偏離取代 2σ daily

**保留**：DRAFT 狀態（per task constraint）— 等待 (a) Phase 2b LiveDemo PASS empirical evidence；(b) QC counterfactual analysis demo 86 fires PASS；(c) Phase 2c LiveDemo Counterfactual Verification 7d observation ≥30 fires PASS；(d) operator 顯式 sign-off；(e) AMD slot 編號補實。

**Risk Rating**: 高（極高風險改動：放寬 live fail-safe，但 7 條 hard gate stack + 7 條 evidence packet + Phase 2c BLOCKER 三層 mitigation）。

**Confidence**: HIGH — 4-agent 對抗審核 100% reflected；無 unresolved item。

---

## §8 下一步 Action Items

| # | Action | Owner | Trigger |
|---|---|---|---|
| 1 | Commit v0.2 patch + 本 PA verdict report | Main session | 本 PA verdict 結束後 |
| 2 | Linear/GitHub Issue 加 v0.2 status note | Main session (optional) | post-commit |
| 3 | Phase 2b LiveDemo 7d PASS empirical evidence collection | AMD-2026-05-15-02 §3 path | Phase 2a PASS + IMPL Prereq 6 全解後 |
| 4 | MIT 派 E1 IMPL replay framework ExitConfig override (MIT-MUST-G 前置) | MIT + E1 | 可 pre-Phase 2b 啟動（不阻 Phase 2b path） |
| 5 | QC 準備 §5 evidence packet skeleton (5.1.1-5.1.7) | QC + PA | 可 pre-Phase 2b 啟動 |
| 6 | Phase 2b PASS 後啟動 QC counterfactual analysis on demo 86 fires | QC | Phase 2b PASS 後 |
| 7 | Gate 3.4 三方聲明 (PA + QC + FA 引 §5 counterfactual evidence) | PA + QC + FA | QC counterfactual PASS 後 |
| 8 | Phase 2c LiveDemo Counterfactual Verification 7d observation | PA monitoring | Operator sign-off + AMD enable 後 |
| 9 | Phase 2c PASS → AMD slot 補實 + land + register + AMD-2026-05-15-02 v0.5 patch | PM + Main session | Phase 2c PASS 後 |

---

## §9 References

- AMD DRAFT v0.2: `/Users/ncyu/Projects/TradeBot/srv/docs/governance_dev/amendments/2026-05-XX-XX-phys-lock-live-enable-draft.md`
- 4-agent verdict reports (commit `a26c1ed9`):
  - QC: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/QC/workspace/reports/2026-05-16--phys_lock_live_enable_amd_qc_review.md`
  - FA: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/FA/workspace/reports/2026-05-16--phys_lock_live_enable_amd_fa_review.md`
  - MIT: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-16--phys_lock_live_enable_amd_mit_review.md`
  - BB: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/BB/workspace/reports/2026-05-16--phys_lock_live_enable_amd_bb_review.md`
- AMD-2026-05-15-02 v0.4 (close-maker-first Phase 1b baseline): `/Users/ncyu/Projects/TradeBot/srv/docs/governance_dev/amendments/2026-05-15--AMD-2026-05-15-02-edge-p2-3-phase-1b-close-maker-first.md`
- spec v1.3 (BB dict): commit `28c571c7`
- Schema verification:
  - V029 `learning.exit_features`: `/Users/ncyu/Projects/TradeBot/srv/sql/migrations/V029__exit_features.sql`
  - V050 `replay.simulated_fills` (evidence_source_tier enum: calibrated_replay / synthetic_replay / counterfactual_replay): `/Users/ncyu/Projects/TradeBot/srv/sql/migrations/V050__replay_simulated_fills.sql`
  - V086 close_reason_code enum: `/Users/ncyu/Projects/TradeBot/srv/sql/migrations/V086__governance_reject_close_reason_code.sql`
- Rust writer empirical: `rust/openclaw_engine/src/database/exit_feature_writer.rs:123` (INSERT INTO learning.exit_features) + `tick_pipeline/mod.rs:1148` (parse_exit_tag → phys_lock_* prefix)
