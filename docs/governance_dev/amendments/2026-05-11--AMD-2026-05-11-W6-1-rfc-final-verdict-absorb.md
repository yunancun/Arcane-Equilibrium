# Amendment AMD-2026-05-11-W6-1 — W6-1 RFC Final Verdict 14 Push Back Absorb

**對應 spec**: W6-1 RFC final verdict draft (2026-05-10) · W6 sub-task chain W6-1~W6-10
**Refines**: W6-1 RFC final verdict draft 4 verdict + 三角 sign-off 14 push back items 統合為正式 governance amendment
**Cross-references**:
- AMD-2026-05-09-03 (graduated canary default)
- AMD-2026-05-10-03 (invariant 5 wording N+0 scope)
- AMD-2026-05-10-04 (TOML drift fix SOP)
- AMD-2026-05-10-05 (graduated canary stage criteria spec)
- AMD-2026-05-02-01 (SM-02 R-04 Decision Lease retrofit Path A)
- ADR-0011 (V### migration Linux PG dry-run mandatory)
- ADR-0017 (Scanner is evidence not authority)
- ADR-0018 (funding_arb retire)
- ADR-0022 (Strategist wide adjustment)
- DOC-08 §12 (9 條安全不變量)
- CLAUDE.md §二 (16 根原則) / §四 (硬邊界) / §七 (SQL migration 規範 + idempotency)

**日期**: 2026-05-11 (D+1 land timing)
**作者**: PA（W6-1 RFC final verdict draft author + 14 push back absorb author）
**狀態**: ⏳ DRAFT — 待 PA + QC + MIT verify push back absorb fidelity + PM 統合 sign-off + Operator 拍板
**索引**: `docs/README.md` Amendments index
**TODO 連結**: Sprint N+1 D+1+ W6 sub-task chain dispatch v3.7 §6.2 / §6.7 / §6.8 acceptance

---

## §0 Predecessors（按時間排序）

| Artifact | Date / Time UTC | Path |
|---|---|---|
| W6-1 RFC final verdict draft (PA author) | 2026-05-10 20:00 | `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-10--w6_1_rfc_final_verdict_draft.md` |
| PA sign-off verdict (APPROVE-CONDITIONAL 3 push back) | 2026-05-10 20:35 | `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-10--w6_1_rfc_pa_signoff_verdict.md` |
| MIT sign-off verdict (APPROVE-CONDITIONAL 5 MUST + 2 SHOULD) | 2026-05-10 20:38 | `srv/docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-10--w6_1_rfc_mit_signoff_verdict.md` |
| QC sign-off verdict (APPROVE-CONDITIONAL 4 push back) | 2026-05-10 21:15 | `srv/docs/CCAgentWorkSpace/QC/workspace/reports/2026-05-10--w6_1_rfc_qc_signoff_verdict.md` |
| Three-way sign-off COMPLETE marker | 2026-05-10 commit `3b5afb2d` | `git log -1 3b5afb2d` |
| W6 V086 producer-side IMPL DONE | 2026-05-10 commit `05e44ede` + `91a7b1c9` | E1 IMPL writer code + IMPL DONE report |
| chain integrity HC `[65]` IMPL DONE | 2026-05-10 commit `db17e205` | `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-10--check_65_chain_integrity_post_m3_impl.md` |
| memory chain integrity era-split (post-M3 100% / pre-M3 39%) | 2026-05-10 commit `332a2f9c` + `9159362c` | `srv/memory/project_2026_05_10_sprint_n0_closure.md` |
| V091 schema-level mutex CHECK NOT VALID skeleton | 2026-05-10 commit `50e75bff` | `sql/migrations/V091__decision_features_reject_close_mutex.sql` (skeleton land, IMPL in flight) |

---

## §1 4 Final Verdicts（LAND）

> 三角共識；經 PA + QC + MIT 各自 RFC 立場交叉引用後 PA 整合定稿，三角 sign-off 確認 capture 正確；任一條未來想撤回必經 D+N 重 RFC，不能在 dispatch 偷改。

### Verdict 1 — cost_gate hard rule 維持，不引 advisory mode

- **16 root principles compliance**：原則 #4（策略不能繞風控）+ 原則 #5（生存 > 利潤）+ 原則 #6（失敗默認收縮）共同支撐。
- **Rust source confirm**：`gates.rs:108-184` 三層設計（paper exploration / demo moderate / live fail-closed）已正確 surface「n_trades < min_n exploration mode 過 / n ≥ min_n 負 JS shrunk hard reject」。
- **數學否決鏈**：QC 提供 Kelly fractional f* < 0（mean=-14.23, σ估 ~30 bps → 數學上不交易）+ DSR / PSR(0) ≈ 0.001 + VaR 95% ≈ -2500 bps cumulative drag。
- **反指**：降為 advisory + 讓 LinUCB 自學 = 用真錢餵 ML，違反原則 #5；同時與 4-agent loss audit「5 textbook 策略結構性 alpha-deficient」結論衝突（不是 governance 太緊，是策略本身 alpha 為負）。
- **N+2 重提防線**：本條 verdict 入 W6-1 RFC report + 本 AMD，N+2 任一 wave 想動 cost_gate 必先撤回此 verdict。

**三角 sign-off 結果**：PA APPROVE / QC APPROVE FULL / MIT APPROVE — 全 fidelity HIGH。

### Verdict 2 — JS shrinkage 強收縮到 grand_mean 是設計預期

- **JS 公式**：`shrunk = grand_mean + (1 - B)(raw - grand_mean)`，`B = (p-2) · pooled_var / sq_sum`
- **數學語言**：當 79 active cells 全 negative + 離散度低（cells 之間真 edge 接近）→ `sq_sum = Σ(raw_i - grand_mean)²` 必然小 → **B 必然接近 1** → shrunk → grand_mean
- **直接觀測**：4 cost_gate cells（grid ETH/BTC/ZEC + ma ETHUSDT）shrunk_bps 標準差只有 1.04 bps（mean=-14.23, range -15.99~-13.28）= high B-factor JS shrinkage signature 的 **教科書 signature**（Lehmann & Casella, Theory of Point Estimation, Ch. 5）— 不是 estimator bug。
- **解讀邊界**：cost_gate 拒擋 shrunk negative 即拒擋 cell-level alpha 在當前 grand_mean negative 環境下；意味著「失去 cell-level idiosyncratic alpha 給 grand mean 換 estimation variance 降低」是設計交易 trade-off 不是 bug。
- **Unwind shrinkage 的唯一途徑**：grand_mean 本身翻正（拉動 shrunk target）；增加 n_trades **不能** unwind（B 公式分母 sq_sum 與 n 無關）；改變單一 cell raw 也**不能** unwind（B 接近 1 時 raw 影響極小）。
- **N+2 重新評估觸發點**：grand_mean 結構性翻正後（即 W2 A4-C BTC→Alt Lead-Lag fast-track 或 W-AUDIT-8a Phase B/C/D 真正補入 alpha source 後），不是現在。

**三角 sign-off 結果**：PA APPROVE / QC APPROVE FULL / MIT APPROVE — 全 fidelity HIGH。

### Verdict 3 — cost_gate 放行 expected new fills net edge ≈ -14 bps，不需要也不應做 counterfactual backtest

- **數學論據**：JS shrunk_bps 是 model 給予的 expected net edge；任何 unbiased estimator 預期下次 sample 也 ~-14 bps（mathematical identity）
- **counterfactual backtest 4 項 bias 修正成本**：(i) leak-free shift / (ii) fee+slippage 模型重 fit / (iii) funding settlement drag / (iv) JS self-fulfilling bias — 4 項任一漏修都會給出 misleading 結果；ROI 不值得（已知 expected -14 bps）
- **Kelly / DSR 雙重否決**：fractional Kelly f* < 0 即「數學上不交易」；DSR PASS 機率 ≈ 0；放行違反原則 #5
- **例外觸發點**：未來 grand_mean 翻正且 raw - grand_mean 大幅正方向偏離（≥ +30 bps）才有重評必要，仍不需 counterfactual backtest，直接由 JS estimator 自然驅動。

**三角 sign-off 結果**：PA APPROVE / QC APPROVE FULL / MIT APPROVE — 全 fidelity HIGH。

### Verdict 4 — scorer_trainer LightGBM regression confirm + W6-5 撤回

- **MIT W6-5 揭露 category error**：`scorer_trainer.py:90-104` `_lgb_params` `objective='regression', metric='rmse'`，**不是 binary/multi-class classification**；`is_unbalance` / `scale_pos_weight` / focal loss 是 classification 專用，對 regression `lgb.train` silently ignore。
- **W6-5 撤回原 LightGBM imbalance flag 試行**；改為 **sample_weight ratio sensitivity 試行**（探索 1/100 / 1/170 / 1/300 / 1/500 對 **scorer RMSE + scorer prediction IC + simulated LinUCB reward signal quality** 影響）。

  > **Wording fix per QC PB#1**: 移除原 draft 的「cost_gate decision distribution」誤導表述（cost_gate 用 JS shrunk_bps，不用 scorer 預測；scorer 是 LinUCB reward signal 來源）

- **V084 sample_weight 走 `lgb.Dataset(weight=...)` 路徑**對 regression 是「L2 loss 加權」（reject row 貢獻量降權至 ~0.47%，fill 仍 dominate ~20%）—  contribution weighting 非 class balancing；imbalance 的 categorical 概念 **在 regression 場景不適用**。
- **重新適用 imbalance handling 的條件** = 未來 W6-3 multi-class label 落地 + trainer task type 升 classification（multi-task learning 或 hierarchical model），預估 N+2/N+3 spec phase。

**三角 sign-off 結果**：PA APPROVE / QC APPROVE FULL / MIT APPROVE FULLY — 全 fidelity HIGH（HIGHEST per MIT confidence）。

---

## §2 14 Push Back Absorb

> 14 條 push back 按 (a) Doc / Wording fix (b) Quant / Acceptance gate (c) IMPL 已 land (d) IMPL 待 D+1+ 四類分組；逐項標 owner + commit refs + acceptance criteria。

### §2.1 Doc / Wording fix（5 條，立即 land）

#### PA PB#1 (低 severity) — V086 SQL §2 spec 註解 wording 修正

**Issue**: V086 SQL §2 idempotency 註解原文「第二次跑時兩 column 已 NOT NULL → WHERE filter 0 row no-op」與 PG runtime 行為不一致（實際是 lossless deterministic re-UPDATE，row count ≠ 0）；D+1 evening engine restart 觸發 auto-migrate 重跑 V086 後 SQL 註解與 PG 行為將出現 inconsistency window，operator/CC 從 SQL 註解推不到「為何第 2 次 UPDATE 不是 0」。

**Action**:
1. W6-3c E2 review 同次 commit 修正 V086 SQL §2 註解 wording 為「第二次跑時 deterministic CASE WHEN 對既有 row 寫同值（lossless idempotent），對新 producer dual-write 寫的 row 補 backfill；UPDATE row count 非 0 是預期，不破不變式」
2. 同次新增 §2.X subsection「Idempotency 性質定義」明文「等價 lossless idempotent，非 hard idempotent (UPDATE=0)；hard idempotent 在 producer dual-write race window 期間結構上不可能達成」
3. E2 review 報告必明文「§2 註解修正 reviewed PASS（lossless idempotent semantic 與 PG runtime 行為一致）」

**Owner**: E1 (V086 SQL edit) + E2 (review confirm)
**Acceptance**: D+1 evening engine restart 前完成；不阻 D+1 evening deploy
**Severity**: 低（governance hygiene）

---

#### QC PB#1 (minor wording) — Verdict 4 sample_weight 試行表述修正

**Issue**: Draft Verdict 4「sample_weight 試行」段落原文寫「探索 1/100 / 1/170 / 1/300 / 1/500 對 RMSE + Sharpe + cost_gate decision distribution 影響」誤導 — cost_gate 用 JS shrunk_bps **不用** scorer 預測，scorer 預測是 LinUCB routing reward signal 來源。

**Action**: §1 Verdict 4 已採 QC PB#1 wording — 表述改為「探索 1/100 / 1/170 / 1/300 / 1/500 對 **scorer RMSE + scorer prediction IC + simulated LinUCB reward signal quality** 影響」。同步更新 W6-5 dispatch acceptance metric。

**Owner**: PM (本 AMD §1 Verdict 4 已修) + dispatch v3.7 §6.7 文字同步
**Acceptance**: 本 AMD §1 Verdict 4 wording 已修；dispatch v3.7 §6.7 同 commit 對齊
**Severity**: 低（minor wording）

---

#### MIT MUST 1 — V086 SQL §2 spec 註解 wording 修正（與 PA PB#1 同源）

**Issue**: 與 PA PB#1 同事項；MIT 從 ML pipeline 立場確認方案 A (accept current behaviour + spec annotation fix)，並要求 D+2 14:30 UTC ALTER TABLE VALIDATE CONSTRAINT 之前完成。

**Action**: 與 PA PB#1 合併處理（單一 SQL edit + commit），PA PB#1 acceptance 滿足即 MIT MUST 1 滿足。

**Owner**: E1 (V086 SQL edit) + E2 (review confirm) + Operator (D+2 14:30 UTC ALTER VALIDATE)
**Acceptance**: D+2 14:30 UTC ALTER VALIDATE 之前 V086 SQL §2 註解 wording 修正完成；否則撤回方案 A 走方案 D（idempotent NOOP via `df.reject_reason_code IS DISTINCT FROM <expected_enum>` 條件）
**Severity**: MUST

---

#### PA PB#3 (informational) — AMD cross-ref 4-agent loss audit evidence path

**Issue**: Draft §1 Verdict 1 引用「4-agent loss audit『5 textbook 策略結構性 alpha-deficient』結論」但沒附 evidence path。對 N+2 audit 重提時 evidence chain 應 traceable 到 source report。

**Action**: 本 AMD §6 cross-references 加 4-agent loss audit 4 報告路徑（per Sprint N+0 closure memory `2026-05-10--sprint_n0_closure.md`）：
- PA: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-09--full_loss_architectural_root_cause_redesign.md`
- FA: `srv/docs/CCAgentWorkSpace/FA/workspace/reports/2026-05-09--audit_fix_verification.md` (+ v2/v3)
- QC: `srv/docs/CCAgentWorkSpace/QC/workspace/reports/2026-05-09--strategy_verification.md` (+ v2/v3)
- MIT: `srv/docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-09--db_ml_verification.md` (+ v2/v3)

**Owner**: PA (本 AMD §6)
**Acceptance**: 本 AMD §6 evidence path 完整列出
**Severity**: informational（不阻 sign-off）

---

#### MIT MUST 4 — CLAUDE.md §七 idempotency wording 修正

**Issue**: CLAUDE.md §七 SQL migration 規範對 idempotency 的字面表述（「每個 migration 必須能 run 兩次不出錯」）容易讓未來 migration 誤判「row count 必須 0 才合格」。V086 OR-filter 缺陷揭露 hard idempotent (UPDATE=0) 在 producer dual-write race window 期間結構上不可能達成。

**Action**: CLAUDE.md §七 idempotency wording 修正為「**idempotency = no schema corruption + no incorrect data state on repeated apply**（不要求 0 row UPDATE，但要求 lossless）」+ commit reference V086 governance exception accept（per AMD-2026-05-11-W6-1 §2.1 PA PB#1 + MIT MUST 1）。

**Owner**: Operator（**動 CLAUDE.md 屬 operator 拍板權**）
**Acceptance**: D+1 evening 同 commit 或 D+2 morning 修；本 AMD land 後 PM 通知 operator
**Severity**: MUST（防未來 migration 誤判）

---

### §2.2 Quant / Acceptance gate（5 條，AMD update）

#### QC PB#2 (quant requirement) — Track B 4-gate (b) per-class N 修正

**Issue**: Draft §3 Track B 4-gate (b) 條「multi-class label 18+ enum 各 class sample ≥ 200 row」過度寬鬆。QC 數學分析揭露：
- detect class 之間 Sharpe Δ=0.5 顯著需 per-class N ≥ 60
- detect class 之間 Sharpe Δ=0.2 顯著需 per-class N ≥ 200
- multi-class classification Bonferroni 修正：18 class 兩兩比較 = 153 比較 → α 從 0.05 降到 3.27e-4 → 對應 N 至少 × 4 倍 → **per-class N ≥ 240（Bonferroni 修正後 detect Δ=0.5 power ≈ 0.65）** 或 **per-class N ≥ 800（detect Δ=0.2）**

**Action**（與 MIT SHOULD 6 整合，以 MIT SHOULD 6 wording 為主）：Track B 4-gate (b) 條改為：

> **(b) per-class sample 累積 gate**（**MIT SHOULD 6 wording 主**）：核心 5 策略中 **≥3 策略**各 class sample ≥ 200 row（funding_arb 排除清單 hard-code per ADR-0018 dormant by design）。
>
> **量化最低標準**（**QC PB#2 wording 補強**）：對選定 ≥3 策略內，per-class N ≥ 60 for 至少 80% enum（detect Δ=0.5 with α=0.05 Bonferroni 修正後 power ≈ 0.65）；OR per-class N ≥ 240 全 enum（更嚴格）。
>
> 兩條件擇一滿足即 (b) gate PASS；funding_arb 永不過 (b) per ADR-0018，spec 必明文「funding_arb sample 不計入 (b) gate」。

**Owner**: PA (本 AMD §3 Track B spec 修訂) + MIT (Track B IMPL 階段 verify)
**Acceptance**: 本 AMD §3 Track B (b) gate wording 更新；N+2 spec phase 啟動時依此判 (b) PASS / PENDING
**Severity**: MUST

---

#### QC PB#3 (acceptance gate gap) — Track A pre-M3 era data quality filter

**Issue**: V086 backfill 9757 row 含 pre-W-AUDIT-4b M3 producer 接通（pre-2026-05-09 09:22 UTC）的歷史 reject sample 與 post-M3 sample 混雜；statistical purity 警示 — backfill 不修補 producer era confound（pre-V082 vs post-V082 reject rate 0% → 99.55%）。Track A 訓練若不過濾會 contaminate baseline。

**Action**: W6-2 + Track A acceptance 補「pre-M3 era data quality filter」要求：

> **Track A trainer pipeline 訓練時必加 filter**：`WHERE ts > '2026-05-09 09:22 UTC'`（W-AUDIT-4b M3 producer 切上線時間）以排除 pre-M3 era 的 data quality drift。
>
> **W6-5 sample_weight ratio sensitivity 試行報告必含**：(a) full pool training + (b) post-M3 era only training 兩 variant 對比；若 RMSE 差異 > 10% 則正式 production scorer training 必加 `ts > '2026-05-09 09:22 UTC'` filter（accept post-M3 era only training 為 baseline）。

**Owner**: MIT (W6-5 IMPL) + PA (本 AMD §3 Track A spec 修訂)
**Acceptance**: W6-5 試行報告 land 時含 (a)+(b) 兩 variant 對比；正式 production scorer training filter 條件入 W6-5 acceptance §6.7
**Severity**: MUST

---

#### QC PB#4 (acceptance gate clarification) — [40] LOW_SAMPLE 標記

**Issue**: §7 healthcheck [40] enhancement「fills/day rate snapshot baseline」缺 LOW_SAMPLE 標記要求；n_total < 30 時 [40] avg_net_bps 不當 strategy edge proxy（small sample noise）。

**Action**: §7 healthcheck [40] enhancement 補入：

> **[40] healthcheck enhancement 必加 `LOW_SAMPLE` 標記邏輯**：n_total < 30 時 [40] avg_net_bps 不當 strategy edge proxy，必加 WARN flag `LOW_SAMPLE(n=<count>, threshold=30)`；console GUI surface 顯示時 LOW_SAMPLE 行禁止用顏色 highlight 為「綠 / 紅 strategy edge」。

**Owner**: E1 (W6-10 [40] enhancement IMPL)
**Acceptance**: W6-10 IMPL 含 LOW_SAMPLE flag；24h dry-run 0 spurious "strategy edge" claim from n<30 cell
**Severity**: MUST

---

#### PA PB#2 (中 severity) — Track B 4-gate (e) gate weekly sample healthcheck

**Issue**: Draft §3 Track B 4-gate (a)/(b)/(c)/(d) 全是 future N+2/N+3 spec phase 條件，缺少「N+1 期間 reject_reason_code 樣本累積進度週報」的 observability 入口；N+2 spec phase 啟動時無法判斷「sample 已累到何時可進 (b) gate」。

**Action**: 補 (e) gate：

> **(e) N+1 期間 weekly sample 累積進度 healthcheck `[63]`**：W6 N+1 期間每週日 00:00 UTC 自動跑 healthcheck `check_reason_code_sample_accumulation()`，輸出 reject + close 各 enum 樣本量 vs (b) gate threshold（per QC PB#2 / MIT SHOULD 6 wording）的進度，發 console + 寫 weekly report。
>
> (e) gate **不阻 N+1 acceptance**（即 N+1 acceptance 仍只看 (a) gate V086 land + dual-write 24h drift 0 NULL），但 (e) gate 為 N+2 spec phase 啟動條件提供 evidence stream；healthcheck slot 用 `[63]` 編號（per §三 §九 編號續 [58]-[62]）。

**Owner**: E1 (W6-9 wave 加 [63] healthcheck IMPL，0.25 day)
**Acceptance**: W6-9 dispatch 加 [63] sub-task；N+1 D+2 ALTER VALIDATE 後即啟用 weekly cron
**Severity**: 中（observability gap）

---

#### MIT SHOULD 6 — Track B (b) 核心 5 策略中 ≥3 策略 wording

**Issue**: 與 QC PB#2 同源不同 wording；MIT SHOULD 6 提出「核心 5 策略中 ≥3 策略各 class sample ≥ 200」+ funding_arb 排除（per ADR-0018 dormant），避免 funding_arb 永遠 blocking。

**Action**: 與 QC PB#2 整合處理（per §2.2 QC PB#2 action）；本 AMD 統一以 MIT SHOULD 6 wording 為主（**核心 5 策略中 ≥3 策略**），QC PB#2 wording 為補強（per-class N quant 最低標準）；二者擇一滿足即 (b) gate PASS。

**Owner**: 與 QC PB#2 同
**Acceptance**: 與 QC PB#2 同
**Severity**: MUST（升 MIT SHOULD 為 MUST 因為與 QC PB#2 同源；統一處理）

---

### §2.3 IMPL 已 land（3 條）

#### MIT MUST 5 — memory chain integrity 100% 結論補註 — ✅ DONE

**Issue**: MIT 全表 chain integrity 實測 (n=5939) chain ratio 從窄窗 100% (n=331) 降至 40%（3570 orphan fills）；5/10 chain integrity replay memory 「真實 100%」結論需附註樣本範圍。

**Action**: ✅ DONE — Sprint N+0 closure memory 已 era-split 精細化：
- `srv/memory/project_2026_05_10_sprint_n0_closure.md` updated commit `332a2f9c`（補正 chain integrity 100% → 真實 40%）
- 二次 era-split 精細化 commit `9159362c`（post-M3 100% / pre-M3 39%）
- 結論：post-W-AUDIT-4b M3 producer 接通（5/10 11:00+）chain 真實 100%；pre-M3 era artifact 接受 orphan，不阻 W6-1 sign-off。
- NEW orphan 3570 RCA work item 入 N+2 dispatch（confirm H1/H2/H3 主因 — pre-M3 producer 老 path 只寫 trading.fills + risk_verdicts 不寫 decision_features）

**Owner**: PA + Operator (memory 寫入)
**Status**: ✅ DONE per commits `332a2f9c` + `9159362c`
**Severity**: MUST (已收口)

---

#### MIT SHOULD 7 — chain integrity HC `[65]` post-M3 enforcement — ✅ DONE

**Issue**: 新 healthcheck `check_chain_integrity_post_audit_4b_m3()` 入 W-AUDIT-4b M3 producer deploy 後 24h passive observation 範圍 — post-5/10 11:00 fills 對應 decision_features 必 100%；pre-5/10 fills 接受 orphan。

**Action**: ✅ DONE — chain integrity HC `[65]` IMPL DONE per commit `db17e205`：
- `helper_scripts/db/passive_wait_healthcheck/checks_chain_integrity_post_m3.py` IMPL
- 與 `[55]` agent_decision_spine_lineage 同 family，pre-M3 vs post-M3 era 分群評估
- post-M3 era 100% chain 強制；pre-M3 era WARN-on-orphan（不 hard FAIL，避免阻塞 silent-dead 偵測）

**Owner**: E1 (HC IMPL) + Operator (cron 啟用)
**Status**: ✅ DONE per commit `db17e205`
**Severity**: SHOULD (已收口)

---

#### MIT MUST 2 — V091 schema-level 互斥不變式 CHECK NOT VALID — 🟢 IN FLIGHT

**Issue**: V086 SQL 沒在 schema-level 強制 reject_reason_code XOR close_reason_code 互斥不變式，純靠 producer code discipline；當前 PG 實測 `overlap_both = 0` PASS 但不代表 future producer 不會違反。MIT db-schema-design-financial-time-series Guard B 範例對 type 敏感場景強制 CHECK constraint，互斥不變式應同等對待。

**Action**: V091 補 schema-level CHECK constraint (NOT VALID)：

```sql
ALTER TABLE learning.decision_features_evaluations
  ADD CONSTRAINT decision_features_evaluations_reject_close_mutex_chk
    CHECK ((reject_reason_code IS NULL OR close_reason_code IS NULL))
    NOT VALID;
```

**Status**: 🟢 IN FLIGHT — V091 SQL skeleton 已 land per commit `50e75bff`（V091 sub-agent a254b07d 跑中）；E1 IMPL 階段含 5 Guard + Linux PG dry-run mandatory + ALTER TABLE VALIDATE CONSTRAINT 走 D+2 14:30 UTC.
**Owner**: E1 (V091 IMPL) + E2 (review) + Operator (D+2 14:30 UTC ALTER VALIDATE)
**Acceptance**: V091 commit + push（E1 sub-agent 跑完）；D+1 engine restart NOT_RUN by design (`OPENCLAW_AUTO_MIGRATE=0`)；D+2 14:30 UTC ALTER VALIDATE CONSTRAINT 走 lock window <30 sec
**Severity**: MUST（IMPL 階段，不阻 W6-1 sign-off）

---

### §2.4 IMPL 待 D+1+（1 條）

#### MIT MUST 3 — W6-5 試行 acceptance 補 5 ML pipeline metrics

**Issue**: 試行報告 metric 缺 out-of-sample purged k-fold evaluation；只看 RMSE 訓練集會過擬合 sample_weight。

**Action**: W6-5 試行 acceptance gate 補入 5 ML pipeline metrics（per MIT C1.b time-series-cv-protocol § Per-fold metrics）：

1. **Per-fold RMSE + 95% CI**（5 fold walk-forward rolling, train_window=10d, test_window=2d, embargo=1d, purge label_end_ts < test_start）
2. **IS vs OOS gap**（gap > 50% → 撤回試行 baseline）
3. **Cross-fold consistency**（std/mean > 0.5 → 不上線 even shadow）
4. **PSI + KS p-value**（per-fold prediction distribution drift；走 `data-drift-detection` skill）
5. **cost_gate decision distribution shift**（per ratio: # cells PASS 變化 + JS shrinkage B factor 變化）

**注意**: cost_gate decision distribution shift 是「**間接觀測 sample_weight 對 cost_gate 上游邏輯的二階影響**」（cost_gate 直接讀 JS shrunk_bps，不讀 scorer 預測；但 scorer 餵 LinUCB reward 改變 → routing 改變 → fill 樣本改變 → JS estimator 重 fit → cost_gate decision distribution 改變），保留為 ML pipeline metric 而非「cost_gate 直接信號」。

**Acceptance**: 試行報告缺以上 ≥3 項 → 後續 sign-off REJECT
**Owner**: MIT (W6-5 IMPL)
**Acceptance**: D+3~D+4 W6-5 IMPL 完成；試行報告 land 時 5 metric 全含
**Severity**: MUST

---

## §3 ML Retrain Track A / Track B 拆分（修訂版含 push back absorb）

> 三角分歧 closing：PA W6 Q3 hold A「V086 立刻做 + ML retrain enable 等 4-gate」+ MIT Q2 hold B「不必等 V086；當前 regression task reject row label=0 已正確」之間的 trade-off，由 Track A / Track B 拆分 close。本節 absorb QC PB#2/3 + MIT MUST 3 + MIT SHOULD 6 + PA PB#2.

### Track A — Regression Scorer 微調（immediate, N+1）

- **Trainer task type**：regression（已 confirm Verdict 4），sample_weight contribution weighting。
- **不需** V086 reject_reason_code（regression 看 `label_net_edge_bps` 不看 reason code）。
- **不需** multi-class label split（regression task 對 categorical reason 是 redundant signal）。
- **可立即跑** W6-5 sample_weight ratio sensitivity 試行；達 W6-5 試行報告 PASS 即 Track A acceptance 滿足。
- **W6 N+1 acceptance 只需 Track A PASS**。

**新增 acceptance gate（per QC PB#3）**：
- W6-5 試行報告必含 (a) full pool training + (b) post-M3 era only training (`WHERE ts > '2026-05-09 09:22 UTC'`) 兩 variant 對比
- 若 RMSE 差異 > 10% 則正式 production scorer training 必加 `ts > '2026-05-09 09:22 UTC'` filter（accept post-M3 era only training 為 baseline）

**新增 acceptance gate（per MIT MUST 3）**：
- W6-5 試行報告必含 5 ML pipeline metrics（per §2.4 MIT MUST 3）：per-fold RMSE + 95% CI / IS vs OOS gap / cross-fold std/mean / PSI+KS / cost_gate decision distribution shift
- 缺 ≥3 項 → 後續 sign-off REJECT

### Track B — Multi-class / Classification Future（N+2/N+3）

5-gate 全達才 enable production multi-class retrain（**修訂版 5-gate**，原 4-gate + (e) gate per PA PB#2）：

- **(a) V086 兩 column land + 24h dual-write 0 NULL drift**（W-AUDIT-4b M3 producer 接通後）
- **(b) per-class sample 累積 gate**（**MIT SHOULD 6 wording 主**）：核心 5 策略中 **≥3 策略**各 class sample ≥ 200 row（funding_arb 排除清單 hard-code per ADR-0018 dormant by design）。
  **量化最低標準**（**QC PB#2 wording 補強**）：對選定 ≥3 策略內，per-class N ≥ 60 for 至少 80% enum（detect Δ=0.5 with α=0.05 Bonferroni 修正後 power ≈ 0.65）；OR per-class N ≥ 240 全 enum（更嚴格）。兩條件擇一滿足即 (b) gate PASS。
- **(c) classification trainer task 升級設計 spec**（multi-task learning 或 hierarchical model 架構選擇；MIT 推薦 hierarchical model — 先預測 routing class binary, 再預測 conditional PnL given routing — 減少 sparse class 問題）
- **(d) imbalance handling 試行報告 PASS**（此時 LightGBM `is_unbalance=True` / `scale_pos_weight` / focal loss / class_weight='balanced' 才適用）
- **(e) N+1 期間 weekly sample 累積進度 healthcheck `[63]`**（per PA PB#2）— W6 N+1 期間每週日 00:00 UTC 自動跑 `check_reason_code_sample_accumulation()`，輸出 reject + close 各 enum 樣本量 vs (b) gate threshold 進度；不阻 N+1 acceptance，為 N+2 spec phase 啟動條件提供 evidence stream

**Track B 直接 N+1 fast-track REJECT 理由**（per MIT 立場）：
1. (a) V086 dual-write 0 NULL drift 需 producer code deploy + 24h passive 觀察
2. (b) per-class N 4/5 策略不過；ma_crossover 6d / bb_breakout 7w+；fast-track 等於 grid_trading-only model（過擬合單策略風險高）
3. (c) classification trainer architecture spec 從未寫過；hierarchical / multi-task learning 設計 ≥1 sprint 工程 + R6 ML system architect adversarial review
4. Track A immediate value 滿足 W6 N+1 acceptance ML pipeline 進步要求
5. N+2 重新評估觸發點明確：producer dual-write 24h 0 NULL drift PASS + per-class sample maturity ≥3/5 策略

---

## §4 D+1 Critical Path

### D+1 morning（08:00-12:00 UTC）

| 時點 | 動作 | Owner | Acceptance |
|---|---|---|---|
| 08:00 | 本 AMD draft commit + push | PA + sub-agent | git commit `AMD-2026-05-11-W6-1...` + push origin main |
| 08:30 | E2 self-review V086 SQL §2 註解 wording 修正 | E2 | E2 review report PASS（per §2.1 PA PB#1 + MIT MUST 1）|
| 09:00 | V091 sub-agent (a254b07d) IMPL 完成 + commit + push | E1 sub-agent | V091 SQL + Guard A/B/C + Linux PG dry-run report + commit |
| 10:00 | dispatch v3.7 §6 acceptance gate 條目 cross-ref 本 AMD | PM | dispatch §6.2 + §6.7 + §6.8 注釋更新 |
| 11:00 | CLAUDE.md §三 W6 wave 一行總結 land | TW + PA | §三 加「W6-1 RFC verdict 三角 sign-off COMPLETE; AMD-2026-05-11-W6-1 absorb 14 push back」|
| 12:00 | PA + QC + MIT verify 本 AMD push back absorb fidelity | PA + QC + MIT | 三方各回 APPROVE / APPROVE-CONDITIONAL |

### D+1 evening（20:00-22:00 UTC）

| 時點 | 動作 | Owner | Acceptance |
|---|---|---|---|
| 20:00 | engine restart_all --rebuild --keep-auth deploy V086 producer code | Operator | Pre-check: V089 fix in main (operator 已 push) / V091 commit + push (sub-agent ready) / Restart with `OPENCLAW_AUTO_MIGRATE=0` (V091 NOT_RUN by design) |
| 20:30 | post-restart 30min validation | Operator + watchdog | reject_NULL_code count drop（producer dual-write 工作）/ engine_alive=true / live snapshot fresh |
| 21:00 | PM 統合 sign-off chain | PM | PA + QC + MIT verify report + Operator approval |
| 21:30 | CLAUDE.md §三 W6-1 final 一行更新 + 本 AMD 升 ✅ Accepted | PM + TW | CLAUDE.md §三 W6 wave row land；本 AMD 狀態升 Accepted |
| 22:00 | dispatch v3.8 公告 W6-1 closed → Track A immediate path 立即 dispatch MIT W6-5 IMPL | PM | dispatch v3.8 §3.0 W6-5 wave 啟動 |

### D+2（next day）

| 時點 | 動作 | Owner | Acceptance |
|---|---|---|---|
| 14:00 | 24h drift healthcheck verify post-V086 producer deploy | Operator + watchdog | reject_reason_code IS NULL count = 0 for new fills（24h post-deploy）|
| 14:30 | ALTER TABLE learning.decision_features_evaluations VALIDATE CONSTRAINT decision_features_evaluations_reject_close_mutex_chk (V091 ENFORCE) | Operator | lock window <30 sec on 9757+ rows; PASS = 0 violation row |

### D+3~D+4

| 時點 | 動作 | Owner | Acceptance |
|---|---|---|---|
| D+3 | MIT W6-5 sample_weight ratio sensitivity 試行（含 5 ML pipeline metrics + post-M3 era filter variant）| MIT | 試行報告 land；5 metric 全含；(a)+(b) variant 對比 |
| D+3 | E1 W6-9 [63] healthcheck IMPL（`check_reason_code_sample_accumulation()`）| E1 | weekly cron 啟用 |
| D+4 | Track A W6-5 試行報告三角 review（PA + QC + MIT）| PA + QC + MIT | report-only land 不需 deploy approval |

---

## §5 後續 sequence — N+2 / N+3 Track B 啟動條件 + dependency

### Track B 5-gate 細化 + dependency map

| Gate | 條件 | Dependency | 預估 timing | Owner |
|---|---|---|---|---|
| (a) | V086 兩 column land + 24h dual-write 0 NULL drift | W6-3c IMPL deploy + W-AUDIT-4b M3 producer 接通 + V091 ALTER VALIDATE | N+1 D+2 14:30 UTC ALTER VALIDATE 後 | E1 |
| (b) | 核心 5 策略中 ≥3 策略各 class sample ≥ 200 row（OR per-class N ≥ 60 for ≥80% enum 量化最低標準）+ funding_arb 排除 | (a) PASS + N+1~N+2 期間 producer 持續累 evidence | N+2 mid-Sprint 預估 | MIT 報告 |
| (c) | classification trainer task 升級設計 spec | (b) PASS + 三角 RFC verdict「multi-task vs hierarchical」 | N+2 spec phase + N+3 IMPL phase | PA + MIT spec |
| (d) | imbalance handling 試行報告 PASS | (c) classification task type confirmed + LightGBM is_unbalance/scale_pos_weight/focal loss apply | N+3 IMPL phase | MIT IMPL |
| (e) | W6 N+1 期間每週 sample 累積進度 weekly report (healthcheck `[63]`) | (a) PASS + healthcheck `[63]` IMPL | N+1 起 weekly continuous | E1 healthcheck + cron |

### Sequence dependency 注意

1. **(b) 啟動條件** = (a) PASS 後等 sample；不可省略 (a) 24h drift 0 NULL 驗證直接進 (b)
2. **(c)/(d) 啟動條件** = N+2 mid-Sprint 操作；等 (b) 4 close enum + 4 reject enum 樣本累 ≥ 200，預估 N+2 mid-Sprint（funding_arb 永不過 per ADR-0018，spec 必明文「funding_arb sample 不計入 (b) gate」）
3. **(e) 啟動條件** = N+1 D+2；V086 land + producer dual-write deploy 後即可開 weekly cron；不阻 N+1 acceptance
4. **N+1 acceptance gate 不變**：仍是 §三 §10 Sprint N+0 closure 22 sign-off invariant + W6 §8 9 條 N+1 acceptance；不加 Track B (b)/(c)/(d) 為 N+1 阻塞點（per Verdict 4 Track A/B 拆分）
5. **N+2 dispatch 預備**：PM 在 N+2 D+0 dispatch 啟動前必 read 本 AMD + (e) gate weekly report；任何 wave 想動 trainer task type 必先撤回 Verdict 4 + 走新 RFC

### 潛在 risk + 緩解

| Risk | 影響 | 緩解 |
|---|---|---|
| (b) 4 close enum < 200 永不過 | Track B 永不 enable | (e) weekly report 早期揭露，N+2 spec phase 評估「降 sample threshold」或「合 enum」alternative |
| funding_arb dormant 加之其他策略 silence | (b) gate 永不過 | dispatch §3.0 W6-7 [61] strategy fire silence healthcheck 已 capture，N+1 期間早期揭露 silence root cause |
| N+1 期間 W-AUDIT-8a Phase B/C/D land 改變 grand_mean signature | Verdict 2 N+2 重評觸發點實現 | dispatch v3.7 W2 A4-C BTC→Alt Lead-Lag fast-track 是首選 alpha source |
| Track A W6-5 sensitivity 報告 5 ratio variant 全 RMSE 退化 | N+1 acceptance §6.7 fail | PM 重 dispatch MIT 走 Track A round 2（試 1/50 / 1/200 / 1/250 ratio），N+1 acceptance window 順延 2 day |
| Track A W6-5 (a) full pool vs (b) post-M3 era variant RMSE 差異 > 10% | 確認 pre-M3 era data quality drift 顯著 | Track A acceptance 強制 production scorer training 加 `ts > '2026-05-09 09:22 UTC'` filter（per QC PB#3）；不阻塞 N+1 acceptance |

---

## §6 Cross-references（含 PA PB#3 4-agent loss audit evidence path）

### W6-1 verdict + push back 來源

- W6-1 RFC final verdict draft (PA, 2026-05-10 20:00 UTC): `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-10--w6_1_rfc_final_verdict_draft.md`
- PA sign-off verdict (APPROVE-CONDITIONAL 3 push back): `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-10--w6_1_rfc_pa_signoff_verdict.md`
- QC sign-off verdict (APPROVE-CONDITIONAL 4 push back): `srv/docs/CCAgentWorkSpace/QC/workspace/reports/2026-05-10--w6_1_rfc_qc_signoff_verdict.md`
- MIT sign-off verdict (APPROVE-CONDITIONAL 5 MUST + 2 SHOULD): `srv/docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-10--w6_1_rfc_mit_signoff_verdict.md`

### 4-agent loss audit evidence chain (per PA PB#3)

- PA: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-09--full_loss_architectural_root_cause_redesign.md` + `2026-05-08--full_audit_pa_fix_plan.md` + `2026-05-09--full_audit_pa_fix_plan_v2.md`
- FA: `srv/docs/CCAgentWorkSpace/FA/workspace/reports/2026-05-09--audit_fix_verification.md` + v2 + v3
- QC: `srv/docs/CCAgentWorkSpace/QC/workspace/reports/2026-05-09--strategy_verification.md` + v2 + v3 + `2026-05-08--strategy_risk_math_audit.md`
- MIT: `srv/docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-09--db_ml_verification.md` + v2 + v3 + `2026-05-08--db_ml_foundation_audit.md`

### IMPL artifact

- W6 V086 producer-side IMPL: `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-10--w6_3c_v086_impl_dry_run_writer_code.md` (commit `05e44ede` + IMPL DONE report `91a7b1c9`)
- V091 schema mutex CHECK NOT VALID: `srv/sql/migrations/V091__decision_features_reject_close_mutex.sql` (commit `50e75bff` skeleton; sub-agent a254b07d IMPL in flight)
- chain integrity HC `[65]`: `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-10--check_65_chain_integrity_post_m3_impl.md` (commit `db17e205`)
- memory chain era-split: `srv/memory/project_2026_05_10_sprint_n0_closure.md` (commits `332a2f9c` + `9159362c`)
- Sprint N+0 closure: `srv/docs/CCAgentWorkSpace/Operator/2026-05-10--sprint_n0_closure_pm_signoff.md`
- Sprint N+1 dispatch v3.7: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-10--sprint_n1_dispatch_draft.md`

### Source code reference

- `srv/rust/openclaw_engine/src/intent_processor/gates.rs:108-184` (cost_gate 三層設計)
- `srv/program_code/ml_training/james_stein_estimator.py:146-190` (JS shrinkage)
- `srv/program_code/ml_training/scorer_trainer.py:90-104` (LightGBM regression task type)
- `srv/rust/openclaw_engine/src/intent_processor/reject_reason_code.rs` (V086 producer-side mapping helper)

---

## §7 16 Root Principles + DOC-08 §12 + 硬邊界 Compliance

### 16 root principles 對照

| # | 原則 | 本 AMD 處理 | 狀態 |
|---|---|---|---|
| 1 | 單一寫入口 | 不動（本 AMD 純 governance metadata + acceptance gate refinement）| ✅ |
| 2 | 讀寫分離 | V086 + V091 是 schema add，read 不變 | ✅ |
| 3 | AI 輸出 ≠ 即時命令 | regression scorer 仍 advisory；W6-5 試行不 deploy production cron | ✅ |
| 4 | 策略不能繞風控 | cost_gate hard rule 強化（Verdict 1 直接支撐）| ✅ |
| 5 | 生存 > 利潤 | cost_gate 拒擋 -14 bps 是核心執行（Verdict 1+3）| ✅ |
| 6 | 失敗默認收縮 | sample_weight 試行不 deploy production；W6-5 fail-closed | ✅ |
| 7 | 學習 ≠ 改寫 Live | regression sample_weight 試行 paper-only baseline 對比 | ✅ |
| 8 | 交易可解釋 | V086 reason_code + V091 schema CHECK 強化（每筆交易可重建為何被拒/為何 close）| ✅ |
| 9 | 交易所災難保護 | 不動 | ✅ |
| 10 | 認知誠實 | 三角 RFC 立場全保留（§3 + §6）；MIT chain integrity 100% → 40% era-split 補正是認知誠實 land 範例 | ✅ |
| 11 | Agent 最大自主權 | cost_gate hard rule 不擴邊界 | ✅ |
| 12 | 持續進化 | Track A immediate retrain + Track B future spec | ✅ |
| 13 | AI 資源成本感知 | sample_weight 試行 + 5 ML pipeline metrics（per MIT MUST 3）| ✅ |
| 14 | 零外部成本可運行 | LightGBM 本地 train，無外部依賴 | ✅ |
| 15 | 多 Agent 協作 | 三角 RFC 共識 + 14 push back absorb | ✅ |
| 16 | 組合級風險意識 | reject reason mix monitor [59] + per-strategy sample gate [62] + chain integrity [65] + reason_code 累積 [63] 強化 | ✅ |

**16/16 合規。**

### DOC-08 §12 9 條安全不變量

- 9 條全 untouched；本 AMD 全屬 read-only schema add + sample_weight 試行 + healthcheck add；無動 pre-trade audit / lease 流程 / fills 寫入 / 風控降級 / authorization / mainnet / Bybit retCode / reconciler / operator 角色。
- **不變量觸碰 = 0**

### §四 硬邊界 5 項

- live_execution_allowed / max_retries=0 / system_mode / live_reserved / authorization.json — **0 觸碰**。
- 本 AMD 全屬 metadata + ML pipeline + healthcheck + acceptance gate refinement，與硬邊界正交。

---

## §8 Risk Acceptance

### 8.1 為何 14 push back 全 absorb 為 MUST/SHOULD

PA 評估三角 sign-off 的 14 push back items 質量分布：

- **5 條 MUST**（MIT MUST 1-5）+ **4 條等同 MUST**（QC PB#1-4 全 minor wording / quant requirement / acceptance gate gap，三方共識需 absorb）+ **3 條 PA push back**（PB#1 低/PB#2 中/PB#3 informational）+ **2 條 MIT SHOULD**（與 QC PB#2 重疊整合 + chain integrity HC 已 IMPL DONE）

→ 14 push back 中 **3 條已 IMPL DONE / land**（MIT MUST 5 memory era-split / MIT SHOULD 7 chain integrity HC `[65]` / MIT MUST 2 V091 IN FLIGHT）；**5 條 doc/wording fix 立即 land**（PA PB#1 + QC PB#1 + MIT MUST 1 + PA PB#3 + MIT MUST 4）；**5 條 quant/acceptance gate update**（QC PB#2/3/4 + PA PB#2 + MIT SHOULD 6 整合 QC PB#2）；**1 條 IMPL 待 D+1+**（MIT MUST 3 W6-5 試行 5 ML pipeline metrics）

→ 全 land 路徑明確；無「reject 重 RFC」性質 push back；本 AMD 升 Accepted 後 N+1 W6 wave 無 reblock。

### 8.2 為何不引 advisory mode（Verdict 1 hold）

per CLAUDE.md §二原則 #5「生存 > 利潤」+ 4-agent loss audit consensus「5 textbook 策略結構性 alpha-deficient」+ Kelly fractional / DSR / PSR 雙重否決：當前 cost_gate 拒擋 negative shrunk_bps 是設計正確；advisory 化將用真錢餵 ML，違反原則 #5。

N+2 重提防線：本 AMD §1 Verdict 1 入 RFC report + AMD，未來想動 cost_gate 必先撤回此 verdict 走新 RFC。

### 8.3 為何 Track A 不需 V086（與 PA Q3 hold A 立場 reconcile）

per Verdict 4 + §3 Track A spec：regression scorer 看 `label_net_edge_bps` 不看 reject_reason_code；Track A 完全不需 V086 落地即可立即跑 W6-5 sample_weight ratio sensitivity；PA Q3 hold A「V086 立刻做」邏輯保留入 Track B prerequisite (a) gate（V086 為 future N+2/N+3 multi-class trainer 提供 schema foundation）；MIT Q2 hold B「不必等 V086」邏輯保留入 Track A immediate path。三方立場全保留。

---

## §9 Non-Goals

This amendment does not:

- 改 W6 N+1 acceptance gate 9 條（per W6-1 RFC draft §8 + dispatch v3.7 §6）
- approve true live, MAG-083, or MAG-084
- change live (LiveDemo + Mainnet) `shadow_mode = true` 預設（per AMD-2026-05-09-03 §2.3 unchanged）
- change paper / demo TOML（per AMD-2026-05-10-04 unchanged）
- 改 ARCH-04 graduated canary 5-stage 哲學（per AMD-2026-05-10-05 unchanged）
- 改 funding_arb retire 立場（per ADR-0018 dormant by design unchanged；本 AMD §3 Track B (b) gate 明文 funding_arb 排除清單 hard-code）
- 改 ADR-0017 scanner is evidence not authority（unchanged）
- 改 invariant 5 wording N+0 scope（per AMD-2026-05-10-03 unchanged）
- 改 cost_gate hard rule（per Verdict 1 hold; advisory mode 撤銷拒）
- introduce new live boundary gate（保留 5-gate per CLAUDE.md §四）
- change scorer task type to classification（保留 regression per Verdict 4; Track B classification 留 N+2/N+3 spec phase）

---

## §10 後續動作（D+1 必跟進）

| # | 動作 | Owner | 時點 | Acceptance |
|---|---|---|---|---|
| 1 | 本 AMD draft commit + push | PA + sub-agent | D+1 08:00 UTC | git commit + push |
| 2 | docs/README.md Amendments index 加 AMD-2026-05-11-W6-1 entry | PA + TW | D+1 W6-1 sign-off 同 commit | TW IMPL |
| 3 | dispatch v3.7 §3.0 + §6 條目 cross-ref AMD-2026-05-11-W6-1 | PM | D+1 10:00 UTC | dispatch §6.2 + §6.7 + §6.8 注釋更新 |
| 4 | CLAUDE.md §三 W6 wave 一行總結 land | TW + PA | D+1 11:00 UTC | §三「W6-1 RFC verdict 三角 sign-off COMPLETE; AMD-2026-05-11-W6-1 absorb 14 push back」|
| 5 | PA + QC + MIT verify 本 AMD push back absorb fidelity | PA + QC + MIT | D+1 12:00 UTC | 三方 verify report |
| 6 | V086 SQL §2 註解 wording 修正 commit (per PA PB#1 + MIT MUST 1) | E1 + E2 | D+1 evening 前 | E2 review report PASS |
| 7 | V091 schema mutex CHECK NOT VALID commit + push (per MIT MUST 2) | E1 sub-agent | D+1 09:00 UTC | V091 SQL + Guard A/B/C + Linux PG dry-run report |
| 8 | engine restart_all --rebuild --keep-auth deploy V086 producer code | Operator | D+1 20:00 UTC | post-restart 30min validation：reject_NULL_code count drop |
| 9 | CLAUDE.md §七 idempotency wording 修正 (per MIT MUST 4) | Operator | D+1 evening 同 commit / D+2 morning | wording 修正：「lossless on repeated apply, no schema corruption + no incorrect data state」|
| 10 | W6-9 wave 加 [63] healthcheck IMPL (per PA PB#2) | E1 | D+3 | weekly cron 啟用 |
| 11 | W6-10 [40] healthcheck enhancement 加 LOW_SAMPLE flag (per QC PB#4) | E1 | D+3 | 24h dry-run 0 spurious "strategy edge" claim from n<30 cell |
| 12 | W6-5 sample_weight 試行 acceptance 補 5 ML pipeline metrics + (a)+(b) variant (per MIT MUST 3 + QC PB#3) | MIT | D+3~D+4 | 試行報告 land；5 metric 全含；(a)+(b) variant 對比 |
| 13 | D+2 14:30 UTC ALTER TABLE VALIDATE CONSTRAINT V091 ENFORCE | Operator | D+2 14:30 UTC | lock window <30 sec on 9757+ rows; PASS = 0 violation row |
| 14 | PA memory.md 追加 W6-1 verdict + 14 push back absorb 摘要 | PA | D+1 21:30 UTC sign-off 後 | memory entry land |

**E2 重點審查 3 點**（V086 SQL §2 註解修正 + V091 IMPL + W6-9 [63] healthcheck IMPL）：
1. **V086 SQL §2 註解 wording fidelity**: 修正後 wording 必明文「lossless idempotent」+「UPDATE row count 非 0 是預期」+「不破不變式」三 phrase；E2 必走 PG empirical query 比對註解描述與真實 PG runtime 行為一致
2. **V091 Guard A/B/C 完整性**: V091 SQL 必含 3 Guard，缺一 = E2 拒簽（per memory `feedback_v_migration_pg_dry_run`）；Linux PG dry-run 必驗 ALTER TABLE NOT VALID + ADD CONSTRAINT 行為與 spec 一致
3. **W6-9 [63] healthcheck SQL design**: `check_reason_code_sample_accumulation()` SQL query 必排除 funding_arb（per ADR-0018 dormant）+ 必含 weekly aggregation pattern（避免 cron miss）+ 必含 LOW_SAMPLE flag for n<30 enum（避免誤判 progression）

---

## §11 Sign-off Chain Required

| Role | Source | Date | Status |
|---|---|---|---|
| PA | 本 AMD draft author + W6-1 RFC final verdict draft author | 2026-05-11 | ⏳ DRAFT (本 AMD) |
| QC | verify quant accuracy of PB absorb (QC PB#1/2/3/4 + Verdict 2/3 數學)| TBD | ⏳ PENDING |
| MIT | verify ML pipeline + DB schema accuracy (MIT MUST 1-5 + SHOULD 6/7 + Verdict 4)| TBD | ⏳ PENDING |
| PM | consolidate sign-off + dispatch v3.8 + CLAUDE.md §三 land | TBD | ⏳ PENDING |
| Operator | final approval + CLAUDE.md §七 wording fix (per MIT MUST 4) + D+1 evening engine restart deploy + D+2 14:30 UTC ALTER VALIDATE | TBD | ⏳ PENDING |

---

## §12 Confidence

**HIGH**

**理由**：
1. 14 push back 全 capture 完整（§2.1-§2.4 逐項 absorb）— 0 漏接
2. 4 verdict fidelity HIGH（§1）— 三角 sign-off 確認 fidelity；本 AMD §1 在 draft §1 基礎上 absorb QC PB#1（Verdict 4 wording 修正）
3. IMPL 狀態 transparent（§2.3）— 3 條 已 land/IN FLIGHT 明文標 commit hash
4. Quant / acceptance gate update 邏輯一致（§2.2）— QC PB#2 + MIT SHOULD 6 整合避免 wording conflict；QC PB#3 + MIT MUST 3 互補（per-fold metrics + post-M3 era filter 兩者對 W6-5 acceptance 並列）
5. 16 root principles 全 16/16 合規 + DOC-08 §12 9 不變量 0 觸碰 + §四 5 硬邊界 0 觸碰
6. D+1 critical path timing 明確（§4）— 與 dispatch v3.7 D+0 sign-off 對齊
7. Track B 5-gate dependency map 清晰（§5）— N+2/N+3 啟動條件 + risk 緩解 全 capture

**唯一不確定**：
1. CLAUDE.md §七 idempotency wording 修正屬 operator 動作（per MIT MUST 4），時點不在 PA 控制；mitigation = 本 AMD §10 step 9 明文 D+1 evening 同 commit / D+2 morning 兩 window，operator 拍板選窗
2. V091 sub-agent IMPL 完成 timing 取決於 sub-agent runtime；mitigation = 本 AMD §10 step 7 標 D+1 09:00 UTC 預期 + sub-agent ID a254b07d 可追蹤；如 D+1 09:00 UTC 未 commit，PM 重 dispatch
3. QC + MIT verify 本 AMD push back absorb fidelity 結果未知；mitigation = 三角 sign-off 14 push back 已全保留，本 AMD 純 absorb 不變更立場，預期 0 push back

**Open items**:
- D+2 14:30 UTC ALTER VALIDATE CONSTRAINT 取決於 V086 SQL §2 註解 wording fix + V091 IMPL 兩 dependency；如任一未完成 D+2 14:30 UTC 前，operator 必延後 ALTER VALIDATE 或撤回方案 A 走方案 D
- W6-5 試行報告 5 ML pipeline metrics 中 cost_gate decision distribution shift 是「間接觀測 sample_weight 對 cost_gate 上游邏輯的二階影響」（per §2.4 MIT MUST 3 注釋）；MIT IMPL 階段如發現此 metric 無法可觀測，需單獨提撤回此 metric 並走 N+2 重 spec
- (b) gate 4 close enum < 200 永不過 risk（per §5 risk table）— 如 N+2 揭露 funding_arb 排除後仍只有 1-2 策略過 (b) gate，PA + MIT 需重評「降 sample threshold」或「合 enum」alternative；屬 N+2 spec phase work item，本 AMD 不解

---

*OpenClaw / Arcane Equilibrium Governance Amendment AMD-2026-05-11-W6-1 — W6-1 RFC Final Verdict 14 Push Back Absorb*
