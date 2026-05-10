# W6-1 RFC final verdict — PA sign-off

**Date**: 2026-05-10 20:35 UTC
**Verdict**: APPROVE-CONDITIONAL（4 條全 capture 正確；2 條 conditional fix-forward；2 條 push back，可在 D+1 evening 同次 commit 收口）
**Reviewer**: PA
**Draft under review**: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-10--w6_1_rfc_final_verdict_draft.md`
**對照原始 PA RFC 立場**: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-10--w6_rfc_pa_questions_self_answer.md`
**對照 W6-3b enum spec final**: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-10--w6_3b_enum_spec_final_pa_decision.md`
**E1 V086 IMPL report**: `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-10--w6_3c_v086_impl_dry_run_writer_code.md`

---

## §1 4 verdict 對應 PA 立場 fidelity 驗證

### Verdict 1 — cost_gate hard rule 維持，不引 advisory mode
**PA 立場**: APPROVE — fidelity HIGH
- 對應原 RFC Q1「hold A — cost_gate 維持 hard rule，4079 reject 符合設計」全 capture 一致。
- Draft §1 引用 `gates.rs:108-184` 三層設計與 PA 原 RFC `gates.rs:108-184` 引文一致；reject paper exploration / demo n_trades<min_n exploration / demo n≥min_n hard reject / live fail-closed 四模式論點明文。
- 16 root principles 對照（#4/#5/#6 共同支撐）+ 反指（用真錢餵 ML 違反 #5）+ 4-agent loss audit cross-ref 全保留。
- N+2 重提防線「verdict 入 W6-1 RFC report + AMD，N+2 任一 wave 想動 cost_gate 必先撤回此 verdict」是原 RFC §6 建議 1 的具體 IMPL，加分。
- **PA 簽字接受**。

### Verdict 2 — JS shrinkage 強收縮到 grand_mean 是設計預期
**PA 立場**: APPROVE — fidelity HIGH（QC 視角主導，PA 不分歧）
- 此 verdict 主要出自 QC 數學分析（PA 原 RFC Q1-Q4 無直接 JS shrinkage 立場），但其結論「強收縮到 grand_mean 是設計預期非 estimator bug」與 PA Q1 立場「cost_gate 設計正確阻擋 -13.28 bps」邏輯一致 — JS estimator 給的 -14 bps grand_mean 就是 cost_gate 拒擋的依據。
- N+2 重新評估觸發點明文「grand_mean 結構性翻正後（W2 A4-C 或 W-AUDIT-8a Phase B/C/D）才重評」與 §三 §10 Sprint N+1 N+2/N+3 timing 一致。
- 4 cost_gate cells（grid ETH/BTC/ZEC + ma ETHUSDT）shrunk_bps stdev=1.04 bps 引用是 high B-factor JS shrinkage signature 是合理判據。
- **PA 簽字接受**（PA 不挑戰 QC 數學分析，只 verify 與 PA cost_gate 立場 consistent）。

### Verdict 3 — cost_gate 放行 expected new fills net edge ≈ -14 bps，不需 counterfactual backtest
**PA 立場**: APPROVE — fidelity HIGH
- 與 PA 原 RFC Q1 「降為 advisory + LinUCB 自學會違反根原則 #5」邏輯一致 — Verdict 3 是同一個結論的數學表達（放行 = expected -14 bps = 違反 #5）。
- 4 項 bias 修正成本（leak-free shift / fee+slippage 重 fit / funding settlement drag / JS self-fulfilling bias）≥1 sprint vs 已知 expected -14 bps 的 ROI 計算正確。
- Kelly / DSR 雙重否決邏輯加分；fractional Kelly f* < 0 的數學語言與 PA Q1 「策略本身 alpha 為負」結論互補。
- **PA 簽字接受**。

### Verdict 4 — trainer task type confirm: scorer_trainer 是 LightGBM regression
**PA 立場**: APPROVE — fidelity HIGH
- 完整 capture MIT W6-5 揭露 category error；PA 原 RFC Q3 「不能等樣本『成熟』才補 schema」立場保留入 Track A/B 拆分（§3）。
- `scorer_trainer.py:90-104` `_lgb_params` `objective='regression', metric='rmse'` 引文確切；regression task 對 `is_unbalance` / `scale_pos_weight` / focal loss silently ignore 的技術論點正確。
- W6-5 撤回 imbalance flag 改 sample_weight ratio sensitivity (1/100/1/170/1/300/1/500) 的試行 grid 是合理 sample variance 探索範圍。
- 「重新適用 imbalance handling 條件 = 未來 W6-3 multi-class label + trainer task type 升 classification」明文，正確 close MIT Q2 hold B 的 timing question。
- **PA 簽字接受**。

**§1 結論**: 4/4 verdict fidelity HIGH，PA 全簽字。

---

## §2 V086 production deploy 後 finding 接收

### E1 OR-filter 缺陷 + 推薦方案 A（accept + spec 註解修正）

**E1 finding 摘要**（per W6-3c IMPL report §3.2）：
- V086 line 372 idempotency filter `AND (df.reject_reason_code IS NULL OR df.close_reason_code IS NULL)` 互斥邏輯下每 row 必有一 NULL，第 2 次 apply 不是 0 row 而是 UPDATE 20057（重 UPDATE 18696 + 新 1361 producer 寫入）。
- 不是 RAISE EXCEPTION，不是 schema 損壞，Guard C PASS。等價 lossless idempotent operation（deterministic CASE WHEN 寫 deterministic 同樣值）。
- 違反 spec §2 idempotency 註解「第二次跑兩 column 已 NOT NULL → WHERE filter 0 row no-op」的字面表述；但 PG 實際行為對不變式無害。

**PA 立場**: **ACCEPT 方案 A（accept + spec 註解修正）**

**論據**：
1. **不變式守護**：Guard C 兩次都 PASS（0 unmapped reject / 0 unmapped close / 0 double-prefix），`overlap_n=0`（V086 §3 互斥不變式 PASS），E2 review 的 3 重點警告全綠。
2. **Lossless idempotent**：deterministic CASE WHEN 對同 row 寫同值，PG MVCC tuple 雖會生新版本，但邏輯上不破任何資料；下次 engine restart 觸發 auto-migrate 即使重跑同樣安全。
3. **方案 B 不可行**：E1 §3.2 已驗證「OR 改 AND」實際沒解決問題（producer 寫一 column 後另一 column 仍 NULL，AND 也 trigger UPDATE）。
4. **方案 C 成本高收益低**：加複雜 idempotency check 對應「reason_code 是否已是非預期 NULL」會引入新 edge case（什麼是「非預期 NULL」？），且為了「第二次 apply UPDATE 0」這個 cosmetic 性質改造 backfill SQL 不值得。
5. **W6-3c E2 audit point 對齊**：PA W6-3b §6 高風險警告 #1「Backfill SQL evaluation order」E2 走 PG dry-run 9757 row distribution 比對 audit table 是 idempotency 的真實 acceptance criteria（值寫對 vs 重跑 0 row），E1 已比對 PASS。

**Spec 註解修正建議**（D+1 evening 同次 commit）：
- V086 §2 註解原文「第二次跑時兩 column 已 NOT NULL → WHERE filter 0 row no-op」改為「第二次跑時 deterministic CASE WHEN 對既有 row 寫同值（lossless idempotent），對新 producer dual-write 寫的 row 補 backfill；UPDATE row count 非 0 是預期，不破不變式」。
- 同次新增 §2.X subsection「Idempotency 性質定義」明文「等價 lossless idempotent，非 hard idempotent (UPDATE=0)；hard idempotent 在 producer dual-write race window 期間結構上不可能達成」。

**PA 預期收益**：
- D+1 evening engine restart 觸發 `OPENCLAW_AUTO_MIGRATE=1` 重跑 V086 不會 RAISE EXCEPTION（已驗證）→ **deploy 可走**。
- PM `bin/repair_migration_checksum` 補 V086 row 後（per W6-3c report §7.1），下次 sqlx 不會嘗試重跑（fingerprint match）。
- E2 review V086 SQL 不需動 SQL 本身，只 review §2 註解 wording 修正。

**PA 立場**: **接受 E1 推薦，方案 A**。

---

## §3 Track A immediate path 安排

**Verdict 4 + Track A**：
- Trainer task type = LightGBM regression confirmed
- 不需 V086 reject_reason_code（regression 看 `label_net_edge_bps` 不看 reason code）
- 立即可跑 W6-5 sample_weight ratio sensitivity (1/100/1/170/1/300/1/500)
- W6 N+1 acceptance 只需 Track A PASS

### PA 對「是否需新 wave 排或現有資源吸收」的判斷

**PA 立場**: **由現有資源吸收，不需新 wave**。

**論據**：
1. **W6-5 已在 dispatch v3.7 §3.0 W6-5 排定 1 day MIT IMPL D+3~D+4**，scope 已收窄為「sample_weight ratio sensitivity 試行報告，僅報告對比，不 deploy 入 production cron」。
2. **MIT IMPL 5 個檔位 grid (1/100/1/170/1/300/1/500)** 在現 `scorer_trainer.py` LightGBM regression `lgb.Dataset(weight=...)` 路徑上是 1-line config sweep，不需新 spec phase，MIT 1 day 充裕。
3. **acceptance metric 已在 dispatch §6.7 明文**：RMSE + Sharpe + cost_gate decision distribution 三維對比，不需新 spec。
4. **不阻塞 W6 其他 sub-task**：Track A 與 W6-2/W6-3c/W6-3d/W6-4/W6-6/W6-7/W6-9/W6-10 全部正交（W6-5 sample_weight 試行 sandbox-only），可 D+3 起 MIT 並行跑，與 E1 IMPL 互不競爭。
5. **「不 deploy 入 production cron」的 govern 邊界已 capture 入 dispatch §6.7 + Verdict 4**，不需 PA 額外為 Track A immediate path 設新 governance gate。

**Track A 完成判據**：
- W6-5 sensitivity 報告 5 ratio variant 對 RMSE / Sharpe / cost_gate decision distribution 數值對比 land
- 報告附 PM/PA/QC/MIT 三角 review verdict（report-only land，不需要 deploy approval）
- N+1 acceptance §6.7 checkbox flip

**PA 簽字**: Track A 不需新 wave，現有 W6-5 dispatch 充足。

---

## §4 Push back items

### Push back #1 — V086 §2 註解 wording 修正必須與 W6-3c E2 review 同次 commit

**Issue**: E1 IMPL report §3.2 推薦方案 A「accept；spec 註解修正即可」是技術正確判斷，但 draft §1 Verdict 4 / §6 / §10 全沒提 V086 SQL 註解 wording 修正的 commit 安排。如果 D+1 evening sign-off + deploy 後才補註解，會造成 V086 SQL 與 E2 review pass evidence、E1 IMPL report、verdict draft 三者間 wording inconsistency window。

**PA 要求**:
- W6-3c E2 review wave 同次 commit V086 SQL §2 註解 wording 修正（per §2 推薦修正建議）
- E2 review 報告必明文「§2 註解修正 reviewed PASS（lossless idempotent semantic 與 PG runtime 行為一致）」
- 修正應在 D+1 evening engine restart 前完成，避免 auto-migrate 重跑 V086 時 operator/CC 從 SQL 註解推不到「為何第 2 次 UPDATE 不是 0」

**Action**: PM dispatch W6-3c 同次給 E2 加「V086 SQL §2 註解 wording 修正」sub-task，預估 5 min。

**Severity**: 低（governance hygiene，不阻 deploy）

---

### Push back #2 — Verdict 4 Track B 4-gate 應補 (e) gate「W6 N+1 期間 ML retrain 4-gate sample 累積進度報告」

**Issue**: Draft §3 Track B 4-gate (a)/(b)/(c)/(d) 全是 future N+2/N+3 spec phase 條件，但缺少**「N+1 期間 reject_reason_code 樣本累積進度週報」**的 observability 入口。如果 N+1 期間沒有定期 metric snapshot，N+2 spec phase 啟動時無法判斷「sample 已累到何時可進 (b) gate」。

**PA 要求**:
- 補 (e) gate「W6 N+1 期間每週日 00:00 UTC 自動跑 healthcheck `check_reason_code_sample_accumulation()`，輸出 reject + close 各 enum 樣本量 vs (b) gate 200 row threshold 的進度，發 console + 寫 weekly report」
- (e) gate 不阻 N+1 acceptance（即 N+1 acceptance 仍只看 (a) gate V086 land + dual-write 24h drift 0 NULL），但 (e) gate 為 N+2 spec phase 啟動條件提供 evidence stream
- healthcheck slot 用 `[63]` 編號（per §三 §九 編號續 [58]-[62]）

**Action**: PM dispatch W6-9 wave 加 `[63]` healthcheck IMPL；E1 0.25 day。

**Severity**: 中（observability gap，影響 N+2 spec phase 啟動 timing）

---

### Push back #3（informational, 不要求 fix）— Verdict 1 反指與 4-agent loss audit cross-ref 應加 evidence path

**Issue**: Draft §1 Verdict 1 引用「4-agent loss audit『5 textbook 策略結構性 alpha-deficient』結論」但沒附 evidence path。對 N+2 audit 重提時 evidence chain 應 traceable 到 source report。

**PA 觀察**:
- 4-agent loss audit 結論在 §三 §10 Sprint N+0 closure memory 有 cross-ref（"4-agent loss audit consensus"）
- 但 Verdict 1 reader 從 verdict draft 直接讀無法 trace 到 audit source

**Action**: 不阻 sign-off；但 D+1 evening AMD-2026-05-1X-W6-1 件落地時加 cross-ref `srv/docs/CCAgentWorkSpace/{FA,QA,QC,BB}/workspace/reports/2026-05-10--*loss_audit*.md` 4 報告路徑（per Sprint N+0 closure memory `2026-05-10--sprint_n0_closure.md`）。

**Severity**: 低（documentation hygiene，不影響 verdict 邏輯）

---

## §5 後續 sequence — N+2 / N+3 Track B 啟動條件 + dependency

### Track B 4-gate 細化 + dependency map

| Gate | 條件 | Dependency | 預估 timing | Owner |
|---|---|---|---|---|
| (a) | V086 兩 column land + 24h dual-write 0 NULL drift | W6-3c IMPL deploy + W-AUDIT-4b M3 producer code 接通 | N+1 D+2 14:30 UTC ALTER VALIDATE 後 | E1 |
| (b) | multi-class 18+ enum 各 class sample ≥ 200 row | (a) PASS + N+1 ~ N+2 期間 producer 持續累 evidence | N+2 mid-Sprint 預估（4 reject enum 已 ≥200, 4 close enum < 200, funding_arb 永不過 per ADR-0018） | MIT 報告 |
| (c) | classification trainer task 升級設計 spec | (b) PASS + 三角 RFC verdict 「multi-task vs hierarchical」 | N+2 spec phase + N+3 IMPL phase | PA + MIT spec |
| (d) | imbalance handling 試行報告 PASS | (c) classification task type confirmed + LightGBM is_unbalance/scale_pos_weight/focal loss apply | N+3 IMPL phase | MIT IMPL |
| (e)（**PA 新加**） | W6 N+1 期間每週 sample 累積進度週報 | (a) PASS + healthcheck `[63]` IMPL | N+1 起 weekly continuous | E1 healthcheck + cron |

### Sequence dependency 注意

1. **(b) 啟動條件 = (a) PASS 後等 sample**: N+1 D+2 14:30 UTC ALTER VALIDATE 後即進 (b) sample 累積期；不可省略 (a) 的 24h drift 0 NULL 驗證直接進 (b)。
2. **(c)/(d) 啟動條件 = N+2 mid-Sprint 操作**: 等 (b) 4 close enum + 4 reject enum 樣本累 ≥ 200，預估 N+2 mid-Sprint（funding_arb 永不過 per ADR-0018，spec phase 必明文「funding_arb sample 不計入 (b) gate」）。
3. **(e) 啟動條件 = N+1 D+2**: V086 land + producer dual-write deploy 後即可開 weekly cron；不阻 N+1 acceptance。
4. **N+1 acceptance gate（不變）**: 仍是 §三 §10 Sprint N+0 closure 22 sign-off invariant + W6 §8 9 條 N+1 acceptance；不加 Track B (b)/(c)/(d) 為 N+1 阻塞點（per Verdict 4 Track A/B 拆分）。
5. **N+2 dispatch 預備**: PM 在 N+2 D+0 dispatch 啟動前必 read W6-1 verdict draft + (e) gate weekly report；任何 wave 想動 trainer task type 必先撤回 Verdict 4 + 走新 RFC。

### 潛在 risk + 緩解

| Risk | 影響 | 緩解 |
|---|---|---|
| (b) 4 close enum < 200 永不過 | Track B 永不 enable | (e) weekly report 早期揭露，N+2 spec phase 評估「降 sample threshold」或「合 enum」alternative |
| funding_arb dormant 加之其他策略 silence | (b) gate 永不過 | dispatch §3.0 W6-7 [61] strategy fire silence healthcheck 已 capture，N+1 期間早期揭露 silence root cause |
| N+1 期間 W-AUDIT-8a Phase B/C/D land 改變 grand_mean signature | Verdict 2 N+2 重評觸發點實現 | dispatch v3.7 W2 A4-C BTC→Alt Lead-Lag fast-track 是首選 alpha source；W2 acceptance gate 對 grand_mean signature 改動的 detection 是 implicit observability |
| Track A W6-5 sensitivity 報告 5 ratio variant 全 RMSE 退化 | N+1 acceptance §6.7 fail | PM 重 dispatch MIT 走 Track A round 2（試 1/50 / 1/200 / 1/250 ratio），N+1 acceptance window 順延 2 day |

---

## §6 Confidence

**HIGH**

**理由**：
1. 4 verdict fidelity HIGH（§1）— PA 原 RFC 立場 100% capture；QC + MIT 視角的部分（Verdict 2 + 4）PA 不分歧。
2. V086 IMPL E1 report finding 推薦方案 A 技術正確（§2）— OR-filter 缺陷實際是「lossless idempotent」性質而非真 bug，spec 註解 wording 修正即可。
3. Track A immediate path 由現有 W6-5 dispatch 吸收充足（§3）— 無資源衝突。
4. 2 條 push back 都是「fix-forward 同次 commit」性質（§4 push back #1 V086 註解 + push back #2 [63] healthcheck），不是「reject 重 RFC」性質。
5. N+2/N+3 sequence (e) gate 補完後 dependency 清晰（§5）— PA 對 Track B 啟動條件有 audit trail。

**唯一不確定**：QC + MIT 視角 verify 結果未知（per task spec PA 不跨範圍 verify）；如 QC 對 Verdict 2 數學細節 push back 或 MIT 對 Verdict 4 task type 細節 push back，需重 sync。預期 D+1 下午 1h 三角 sync 解決。

---

## §7 PA Sign-off Action Items（D+1 evening 同次 commit）

1. **PM 升 draft 為 AMD-2026-05-1X-W6-1-rfc-verdict.md**（path `srv/docs/governance_dev/amendments/`）
2. **AMD 件加 §11 cross-ref evidence chain**（per §4 push back #3）
3. **W6-3c E2 review wave 加 V086 SQL §2 註解 wording 修正 sub-task**（per §4 push back #1）
4. **W6-9 wave 加 `[63]` `check_reason_code_sample_accumulation()` healthcheck IMPL**（per §4 push back #2）
5. **dispatch v3.7 §3.0 + §6 條目 cross-ref AMD-2026-05-1X-W6-1**（per draft §10 Sign-off 後 commit chain step 2）
6. **CLAUDE.md §三 W6 wave 一行總結 land**（per draft §10 step 3）
7. **PA memory.md 追加 W6-1 verdict 摘要**（per draft §10 step 4）

---

PA SIGN-OFF DONE: APPROVE-CONDITIONAL（4 verdict 全 capture HIGH fidelity；2 push back fix-forward 同次收口；Track A 由現資源吸收；Track B (e) gate 補完）

report path: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-10--w6_1_rfc_pa_signoff_verdict.md`
