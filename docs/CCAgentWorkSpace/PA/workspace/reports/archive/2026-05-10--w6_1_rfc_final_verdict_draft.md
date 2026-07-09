# W6-1 RFC Final Verdict（Draft，D+1 三角 sign-off 用）

**日期**：2026-05-10
**性質**：W6 三角 RFC 預備立場已 land 後 PA 整合產出的 final verdict draft；D+1 PA + QC + MIT 三角各 1h verify 此 draft 是否如實 capture 各自立場，**不重新 RFC**。
**Sign-off 後動作**：本 draft 升 `srv/docs/governance_dev/amendments/2026-05-1X--AMD-2026-05-1X-W6-1-rfc-verdict.md` AMD 正式件，並把 §1 verdict 4 條同 commit 推進 dispatch v3.5 §6 + 16 root principles cross-ref。

**前置 evidence**：
- PA W6 RFC PA-view（4 hold A）：`srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-10--w6_rfc_pa_questions_self_answer.md`
- QC W6 RFC QC-view（4 hold A）：`srv/docs/CCAgentWorkSpace/QC/workspace/reports/2026-05-10--w6_rfc_qc_questions_self_answer.md`
- MIT W6 RFC MIT-view（4 含 hold B + W6-5 category error）：`srv/docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-10--w6_rfc_mit_questions_self_answer.md`
- PA W6-3b enum spec final（12 reject + 14 close + 5 ambiguous A1-A5 全 ACCEPT MIT）：`srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-10--w6_3b_enum_spec_final_pa_decision.md`
- PA P2 雙前綴 RCA（無新 P2 ticket）：`srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-10--p2_decision_features_double_prefix_bug_audit.md`
- MIT W6 baseline / W6-3a close_tag distribution audit：`srv/docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-10--governance_reject_baseline_w6_rfc.md` + `2026-05-10--w6_3a_close_tag_distribution_audit.md`
- Sprint N+1 dispatch v3.5：`srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-10--sprint_n1_dispatch_draft.md`

---

## §1 W6-1 Verdict（4 條明文，per dispatch v3.5 §3.0 W6-8）

> 三角共識；經 PA + QC + MIT 各自 RFC 立場交叉引用後 PA 整合定稿。任一條未來想撤回必經 D+N 重 RFC，不能在 dispatch 偷改。

**Verdict 1 — cost_gate hard rule 維持，不引 advisory mode**
- 16 root principles compliance：原則 #4（策略不能繞風控）+ 原則 #5（生存 > 利潤）+ 原則 #6（失敗默認收縮）共同支撐。
- Rust source confirm：`gates.rs:108-184` 三層設計（paper exploration / demo moderate / live fail-closed）已正確 surface「n_trades < min_n exploration mode 過 / n ≥ min_n 負 JS shrunk hard reject」。
- 反指：降為 advisory + 讓 LinUCB 自學 = 用真錢餵 ML，違反原則 #5；同時與 4-agent loss audit「5 textbook 策略結構性 alpha-deficient」結論衝突（不是 governance 太緊，是策略本身 alpha 為負）。
- N+2 重提防線：本條 verdict 入 W6-1 RFC report + AMD，N+2 任一 wave 想動 cost_gate 必先撤回此 verdict。

**Verdict 2 — JS shrinkage 強收縮到 grand_mean 是設計預期**
- QC 數學分析確認：當前 79 active cells 全 negative + 離散度低 → grand_mean ≈ -14 bps + sq_sum 小 → JS B factor ≈ 1 → shrunk 全擠到 grand_mean。
- 4 cost_gate cells（grid ETH/BTC/ZEC + ma ETHUSDT）shrunk_bps 標準差只有 1.04 bps（mean=-14.23, range -15.99~-13.28）是 high B-factor JS shrinkage signature，不是 estimator bug。
- 解讀邊界：cost_gate 拒擋 shrunk negative 即拒擋 cell-level alpha 在當前 grand_mean negative 環境下；意味著「失去 cell-level idiosyncratic alpha 給 grand mean 換 estimation variance 降低」是設計交易 trade-off 不是 bug。
- N+2 重新評估 JS estimator 的觸發點 = grand_mean 結構性翻正後（即 W2 A4-C 或 W-AUDIT-8a Phase B/C/D 真正補入 alpha source 後），不是現在。

**Verdict 3 — cost_gate 放行 expected new fills net edge ≈ -14 bps，不需要也不應做 counterfactual backtest**
- QC 數學論據：開放 cost_gate（e.g., relax 「shrunk_bps < 0」改為「shrunk_bps < -10 bps」）= 放行 grid ETH/BTC/ZEC + ma ETHUSDT 的 fill；這 4 cells 的 JS estimate 就是 model 給予的 expected net edge → 新 fill 期望值 ≈ JS shrunk_bps ≈ **-14 bps**。
- counterfactual backtest 4 項 bias 修正（leak-free shift / fee+slippage 模型重 fit / funding settlement drag / JS self-fulfilling bias）需 ≥1 sprint 工程，ROI 不值得（已知 expected -14 bps）。
- Kelly / DSR 雙重否決：fractional Kelly f* < 0 即「數學上不交易」；DSR PASS 機率 ≈ 0；放行違反原則 #5。
- 例外觸發點：未來 grand_mean 翻正且 raw - grand_mean 大幅正方向偏離（≥ +30 bps）才有重評必要，仍不需 counterfactual backtest，直接由 JS estimator 自然驅動。

**Verdict 4 — trainer task type confirm：scorer_trainer 是 LightGBM regression**
- MIT W6-5 揭露 category error：`scorer_trainer.py:90-104` `_lgb_params` `objective='regression', metric='rmse'`，**不是 binary/multi-class classification**；`is_unbalance` / `scale_pos_weight` / focal loss 是 classification 專用，對 regression `lgb.train` silently ignore。
- W6-5 撤回原 LightGBM imbalance flag 試行；改為 **sample_weight ratio sensitivity 試行**（探索 1/100 / 1/170 / 1/300 / 1/500 對 RMSE + Sharpe + cost_gate decision distribution 影響）。
- V084 sample_weight 走 `lgb.Dataset(weight=...)` 路徑對 regression 是「L2 loss 加權」（reject row 貢獻量降權至 ~0.47%，fill 仍 dominate ~20%），這是 contribution weighting 非 class balancing；imbalance 的 categorical 概念**在 regression 場景不適用**。
- 重新適用 imbalance handling 的條件 = 未來 W6-3 multi-class label 落地 + trainer task type 升 classification（multi-task learning 或 hierarchical model），預估 N+2/N+3 spec phase。

---

## §2 8 Sub-task 對齊（W6-1 ~ W6-10 final scope）

| Sub-task | Final scope | Owner | Day | Verdict 對應 |
|---|---|---|---|---|
| W6-1 | 本 verdict draft → AMD 件，cost_gate / JS / counterfactual / trainer task 4 條 | PA + QC + MIT 三角 sign-off | D+1 (1d) | §1 全 4 |
| W6-2 | V086 schema add 兩 column（reject_reason_code + close_reason_code），Guard A/B/C + NOT VALID CHECK + one-shot 30-90 sec backfill in migration（不開 cron） | E1 IMPL，PA spec ready | D+1~D+2 (1d) | enable Verdict 4 Track B |
| W6-3a | close_tag distribution audit（68 unique → 15 category）— **MIT 已完成 HEAD `da6c1f80`** | DONE | DONE | enable W6-3b |
| W6-3b | 兩 column enum spec：reject 12 enum + close 14 enum + 5 ambiguous A1-A5 全 ACCEPT MIT — **PA 已完成** | DONE | DONE | feed W6-3c |
| W6-3c | V086 兩 column add + Guard + NOT VALID CHECK + one-shot backfill；同 migration 加 trading.fills 17 row 雙前綴 normalize（per PA P2 audit） | E1 IMPL | D+1~D+2 (1d) | §4 + §6 |
| W6-3d | trainer pipeline read schema update（regression 仍 ignore reason code，future multi-task 接口 ready） | E1 IMPL | D+2 (1d) | preserve Track A backward compat |
| W6-3e | ALTER VALIDATE CONSTRAINT D+2 14:30 UTC（lock window <30 sec on 9757+ rows） | E1 ops | D+2 (0.25d) | finalize Verdict 4 Track B 的 schema lock |
| W6-4 | M4 reject reason mix monitor [59]（cost_gate ratio 24h 變化 > 20pp / duplicate_position ratio 突增 alert；**不**用 reject rate > 95% 作 alert） | E1 IMPL | D+2~D+3 (1d) | §7 healthcheck enhancement |
| W6-5 | sample_weight ratio sensitivity 試行（1/100 / 1/170 / 1/300 / 1/500）；**僅報告對比，不 deploy 入 production cron** | MIT IMPL | D+3~D+4 (1d) | §3 Track A immediate |
| W6-6 | M5 evaluations.entry_context_id healthcheck [60]（等 ML predictor 接通後 enable） | E1 IMPL stub | D+3 (1d) | §7 healthcheck enhancement |
| W6-7 | [61] strategy fire silence healthcheck（5 策略 24h 0 fire 報 WARN，funding_arb 排除清單 hard-code per ADR-0018） | E1 IMPL | D+3 (0.5d) | §3 Track A + §7 |
| W6-8 | W6-1 RFC verdict 明文化（即本 draft 升 AMD 件） | PA | D+1 (0.25d) | self-reference §1 |
| W6-9 | [62] check_per_strategy_sample_gate healthcheck（5 策略 30d sample vs MIN_SAMPLES 200，funding_arb 排除） | E1 IMPL | D+3 (0.5d) | §7 healthcheck enhancement |
| W6-10 | fills/day rate snapshot baseline 健檢項（每週 grid / ma / bb_breakout / bb_reversion 各 fills/day baseline 入 console） | E1 IMPL | D+3 (0.25d) | §7 healthcheck enhancement |

---

## §3 ML Retrain Track A / Track B 拆分（PA Q3 vs MIT Q2 分歧解決方案）

> 三角分歧 closing：PA W6 Q3 hold A「V086 立刻做 + ML retrain enable 等 4-gate」+ MIT Q2 hold B「不必等 V086；當前 regression task reject row label=0 已正確」之間的 trade-off，由 Track A / Track B 拆分 close。

### Track A — Regression Scorer 微調（immediate, N+1）
- **Trainer task type**：regression（已 confirm Verdict 4），sample_weight contribution weighting。
- **不需** V086 reject_reason_code（regression 看 `label_net_edge_bps` 不看 reason code）。
- **不需** multi-class label split（regression task 對 categorical reason 是 redundant signal）。
- **可立即跑** W6-5 sample_weight ratio sensitivity 試行；達 W6-5 試行報告 PASS 即 Track A acceptance 滿足。
- **W6 N+1 acceptance 只需 Track A PASS**。

### Track B — Multi-class / Classification Future（N+2/N+3）
- 4-gate 全達才 enable production multi-class retrain：
  - (a) V086 兩 column land + 24h dual-write 0 NULL drift（W-AUDIT-4b M3 producer 接通後）
  - (b) multi-class label 18+ enum 各 class sample ≥ 200 row（funding_arb 永不過 gate per ADR-0018）
  - (c) classification trainer task 升級設計 spec（multi-task learning 或 hierarchical model 架構選擇）
  - (d) imbalance handling 試行報告 PASS（此時 LightGBM `is_unbalance=True` / `scale_pos_weight` / focal loss / class_weight='balanced' 才適用）
- 留 N+2/N+3 spec phase；W6 N+1 不阻塞。

### 分歧解決邏輯
- PA Q3「立刻做 V086」邏輯有效：reject 6415/3.5h ≈ 1830/h 累積快，越早 schema add 越早累 reason_code metadata 給 future Track B；不能等 sample 成熟才補 schema（會污染未來 baseline）。
- MIT Q2「不必等 V086」邏輯也有效：但限定範圍 = 「當前 regression scorer Track A」；Track B 仍需 V086 + 4-gate。
- Combined：**V086 立刻做（PA hold A）+ Track A 不等 V086 即可跑（MIT hold B）+ Track B 等 4-gate（PA hold A 4-gate spec）**，三方立場全保留。

---

## §4 真實 Enum Spec（per PA W6-3b final + MIT W6-3a evidence）

### 4.1 reject_reason_code — 12 enum（11 + 1 catch-all）

| # | enum | producer source pattern | 全期 count | post-V082 |
|---|---|---|---|---|
| 1 | `cost_gate_js_demo_negative_edge` | `^cost_gate\(JS-demo\) estimated=` | ~6.19M | 5239 |
| 2 | `cost_gate_atr_unavailable` | `ATR unavailable` (within cost_gate*) | ~13 | 0 |
| 3 | `cost_gate_other` | `^cost_gate ` (legacy non-JS, exclude JS-demo, exclude ATR unavailable) | 987k | 15 |
| 4 | `duplicate_position` | `^duplicate_position` | 1.94M | 2333 |
| 5 | `direction_conflict` | `^direction_conflict` | 2.77M | 0 |
| 6 | `position_count_limit` | `^position_count` | 732k | 0 |
| 7 | `scanner_market_gate` | `^scanner_market_gate` | 401k | 0 |
| 8 | `scanner_opportunity_canary` | `^scanner_opportunity_canary` | 138k | 0 |
| 9 | `drawdown_breach` | `^drawdown_breach` | 91k | 0 |
| 10 | `symbol_blocklist` | regex `blocked by per_strategy\.\w+\.blocked_symbols` | 35.5k | 0 |
| 11 | `risk_gate_other` | `^risk_gate` | 7998 | 0 |
| 12 | `reject_other` | residual catch-all | <100 | 0 |

### 4.2 close_reason_code — 14 enum（13 + 1 catch-all）

| # | enum | producer source pattern (label_close_tag) | 全期 count |
|---|---|---|---|
| 1 | `strategy_close_grid` | `^strategy_close:grid_close` | 689 |
| 2 | `strategy_close_ma` | `^strategy_close:ma_` | 315 |
| 3 | `strategy_close_bb` | `^strategy_close:bb_` | 4 |
| 4 | `strategy_close_funding_arb` | `^strategy_close:funding_arb_exit` | 29 |
| 5 | `strategy_close_regime_shift` | exact `strategy_close:regime_shift` | 1 |
| 6 | `strategy_close_legacy_bare_name` | bare strategy name (W-AUDIT-4b M2 約定) | 615 |
| 7 | `risk_close_phys_lock_gate4_giveback` | `^(risk_close:)?risk_close:phys_lock_gate4_giveback` (含雙前綴 normalize) | 511 |
| 8 | `risk_close_phys_lock_gate4_stale` | `^risk_close:phys_lock_gate4_stale` | 20 |
| 9 | `risk_close_cost_edge` | `^risk_close:COST EDGE` | 14 |
| 10 | `risk_close_fast_track` | `^risk_close:fast_track` | 14 |
| 11 | `risk_close_trailing_stop` | `^risk_close:TRAILING STOP` | 10 |
| 12 | `risk_close_dynamic_stop` | `^risk_close:DYNAMIC STOP` | 6 |
| 13 | `ipc_close_all` | exact `ipc_close_all` | 1 |
| 14 | `close_other` | residual catch-all | <100 |

### 4.3 V086 schema migration final spec
- 兩 column TEXT（不是 jsonb）；遵 Guard A/B/C 模板（per memory `feedback_v_migration_pg_dry_run`）。
- NOT VALID CHECK constraint（new rows 即時驗，legacy 9.5M rows 不掃描）。
- One-shot 30-90 sec backfill in migration（不開 cron），CASE WHEN 評估順序 critical：ATR unavailable 先於 JS-demo 先於 cost_gate_other；雙前綴 先於 單前綴；bare-name exact 先於 prefix regex。
- ALTER VALIDATE CONSTRAINT D+2 14:30 UTC，lock window <30 sec on 9757+ rows。

---

## §5 5 Ambiguous Mapping A1-A5 拍板（per PA W6-3b 全 ACCEPT MIT）

| # | 議題 | MIT 推薦 | PA 拍板 | 理由摘要 |
|---|---|---|---|---|
| A1 | `strategy_close_legacy_bare_name` (615 row) 是否拆 5 sub-enum | 不拆，1 enum；trainer 看 `strategy` column | **ACCEPT** 不拆 | 5 策略區分由 `decision_features.strategy` SoT 承擔，避免 schema duplication |
| A2 | `risk_close:risk_close:phys_lock_gate4_giveback` (16 row 雙前綴) | backfill normalize 同 enum；開 P1 producer ticket | **ACCEPT** normalize；但**不開** P1 ticket | RUST-DOUBLE-PREFIX-1 已 2026-04-23 commit `46a9cadc` fix；16 row 是歷史污染非 active bug |
| A3 | `cost_gate_atr_unavailable` 0 row post-V082 — 保留 enum 還是合 cost_gate_other | 保留（empty-but-reserved） | **ACCEPT** 保留 | ATR unavailable 是 SEC-11 fail-closed signal，trader semantic 與 legacy cost_gate 不同 |
| A4 | funding_arb 29 unique sub-reason 全合 1 enum | 合 `strategy_close_funding_arb` | **ACCEPT** 合 1 enum | ADR-0018 退役 future 0 增量；29 unique 是 string-formatted float 對 ML 0 cardinality value |
| A5 | `strategy_close_regime_shift` 1 row 是否值得 enum | 保留（pilot enum） | **ACCEPT** 保留 | W-AUDIT-8a R-3 hypothesis pipeline + regime detection 落地後可能爆量；enum slot 成本極低 |

---

## §6 雙前綴 16+17 Row 處理（per PA P2 RCA）

> A2 拍板的 IMPL 細節，避免 W6-3c E1 漏接 trading.fills 上游清理。

- **trading.fills** 17 row 雙前綴 `risk_close:risk_close:phys_lock_gate4_giveback` （2026-04-23 02:39-11:55 +0200, PENGUUSDT 100% 單一 cluster）— 在 V086 同 migration 加：
  ```sql
  UPDATE trading.fills
  SET strategy_name = REPLACE(strategy_name, 'risk_close:risk_close:', 'risk_close:')
  WHERE strategy_name LIKE 'risk_close:risk_close:%';
  ```
  Lock window <1 sec on 17 row，安全。
- **learning.decision_features** 16 row 雙前綴在 V086 backfill SQL 內 normalize 進 `risk_close_phys_lock_gate4_giveback` enum（保留 raw `label_close_tag` 欄位歷史 bug fingerprint，未來 forensic 可追）。
- **不開** P1 producer ticket：`build_risk_close_tag()` 已是 idempotent helper（`tick_pipeline/on_tick/helpers.rs:38-45`），post-2026-04-23 fix 17 天 0 新增雙前綴 row。

---

## §7 Healthcheck 新增（4 個 [59]/[60]/[61]/[62] + [40] enhancement）

| ID | 用途 | Owner | Wave |
|---|---|---|---|
| [59] M4 reject reason mix monitor | cost_gate ratio 24h 變化 > 20pp 或 duplicate_position ratio 突增 → WARN；**不**用 reject rate > 95% 作 alert | W6-4 | E1 IMPL |
| [60] M5 evaluations.entry_context_id coverage | predictor 接通後 enable；目前 stub | W6-6 | E1 IMPL stub |
| [61] strategy fire silence healthcheck | 5 策略 24h 0 fire 報 WARN；funding_arb 排除清單 hard-code per ADR-0018；root cause 列舉：cooldown / regime / panel_unavailable / scanner_threshold / strategy↔position desync (W7 fix 後應消失) | W6-7 | E1 IMPL |
| [62] per_strategy_sample_gate | 5 策略各列 30d sample 對比 MIN_SAMPLES (200)；標 PASS/WARN/FAIL；funding_arb 排除（dormant by design ADR-0018） | W6-9 | E1 IMPL |
| [40] enhancement | fills/day rate snapshot baseline 健檢項；每週 grid / ma / bb_breakout / bb_reversion 各 fills/day baseline 入 console；避免 N+2 用 stale 70/day baseline 作決策（actual 93/day） | W6-10 | E1 IMPL |

---

## §8 W6 N+1 Acceptance Gate（與 dispatch v3.5 §6 對齊）

> 全部達標才能 N+1 sign-off 進 N+2；每條對應 dispatch §6 條目以利交叉驗證。

1. ✅ 三角 RFC verdict 4 條明文（即 §1）寫入 RFC report + 升 AMD-2026-05-1X 件 — corresponds dispatch §6.2
2. ✅ V086 在 Linux PG `_sqlx_migrations` success=t（auto-migrate 後驗）；W-AUDIT-4b M3 producer 寫 reject_reason_code + close_reason_code 100% coverage（post-V086 sample 24h drift 0 NULL）— corresponds dispatch §6.3 + §6.4
3. ✅ Multi-class label 18+ enum 在 decision_features 顯示分布（reject 12 enum + close 14 enum；catch-all 收殘餘 < 100 row each）— corresponds dispatch §6.4
4. ✅ M4 [59] healthcheck baseline + alert 設好；24h dry-run 0 spurious alert — corresponds dispatch §6.5
5. ✅ [61] strategy fire silence healthcheck baseline 入 console；funding_arb 排除清單已驗 — corresponds dispatch §6.6
6. ✅ Sample weight ratio sensitivity 試行報告 land（1/100 / 1/170 / 1/300 / 1/500 對 RMSE + Sharpe + cost_gate decision distribution）；**僅報告對比，不 deploy 入 production cron** — corresponds dispatch §6.7
7. ✅ ML retrain 拆兩 Track（§3）：Track A PASS 即 N+1 acceptance；Track B 留 N+2/N+3 — corresponds dispatch §6.8
8. ✅ 22 invariant + 新 invariant 23 全 PASS — corresponds dispatch §6.14
9. ✅ CC + QC + MIT + BB 4-agent final review 全 APPROVE / APPROVE-CONDITIONAL — corresponds dispatch §6.15

**v3 移除（v2 設計取消，本 verdict 確認不可重啟）**：
- 不寫「W6 verdict = over-fit → conditional relax AMD」（baseline 預跑揭露 governance 沒 over-fit）
- 不設「governance reject rate 進入 70-90% 合理區間」目標（99.5% 是 normal）

---

## §9 16 Root Principles + DOC-08 §12 + 硬邊界 Compliance

### 16 root principles 對照
| # | 原則 | W6 verdict 處理 |
|---|---|---|
| 1 單一寫入口 | 不動 | ✅ |
| 2 讀寫分離 | V086 是 schema add，read 不變 | ✅ |
| 3 AI 輸出 ≠ 即時命令 | regression scorer 仍 advisory | ✅ |
| 4 策略不能繞風控 | cost_gate hard rule 強化 | ✅ Verdict 1 直接支撐 |
| 5 生存 > 利潤 | cost_gate 拒擋 -14 bps 是核心執行 | ✅ Verdict 1+3 直接支撐 |
| 6 失敗默認收縮 | sample_weight 試行不 deploy production；W6-5 fail-closed | ✅ Verdict 4 |
| 7 學習 ≠ 改寫 Live | regression sample_weight 試行 paper-only baseline 對比 | ✅ |
| 8 交易可解釋 | V086 reason_code 直接強化（每筆交易可重建為何被拒/為何 close） | ✅ Verdict 4 Track B 加強 |
| 9 交易所災難保護 | 不動 | ✅ |
| 10 認知誠實 | 三角 RFC 立場全保留（§3 + §5） | ✅ |
| 11 Agent 最大自主權 | cost_gate hard rule 不擴邊界 | ✅ |
| 12 持續進化 | Track A immediate retrain + Track B future spec | ✅ |
| 13 AI 資源成本感知 | sample_weight 試行報告對比 RMSE + cost_gate decision | ✅ |
| 14 零外部成本可運行 | LightGBM 本地 train，無外部依賴 | ✅ |
| 15 多 Agent 協作 | 三角 RFC 共識 | ✅ |
| 16 組合級風險意識 | reject reason mix monitor [59] + per-strategy sample gate [62] 強化 | ✅ |

**16/16 合規。**

### DOC-08 §12 9 條安全不變量
- 9 條全 untouched；W6 全屬 read-only schema add + sample_weight 試行 + healthcheck add；無動 pre-trade audit / lease 流程 / fills 寫入 / 風控降級 / authorization / mainnet / Bybit retCode / reconciler / operator 角色。
- **不變量觸碰 = 0**

### §四 硬邊界 5 項
- live_execution_allowed / max_retries=0 / system_mode / live_reserved / authorization.json — **0 觸碰**。
- W6 全屬 metadata + ML pipeline + healthcheck，與硬邊界正交。

---

## §10 D+1 三角 Sign-off 流程預期

**Phase 1（D+1 上午，1.5h 並行）**：
- PA verify §1 Verdict 1+2+3+4 是否如實 capture PA W6 RFC PA-view 的 4 hold A 立場（特別 §3 Track A/B 拆解是否解 PA Q3 hold A vs MIT Q2 hold B 分歧）。
- QC verify §1 Verdict 1+2+3 是否如實 capture QC W6 RFC QC-view 的 hold A 4 立場（特別 Verdict 2 JS shrinkage signature 數學語言 + Verdict 3 expected -14 bps 數學否決邏輯）。
- MIT verify §1 Verdict 4 是否如實 capture MIT W6 RFC MIT-view 揭露的 W6-5 category error；確認 §3 Track B 4-gate 是 MIT Q2 hold B 完整 spec。

**Phase 2（D+1 下午，1h 三角 sync）**：
- 三方各回「APPROVE / APPROVE-CONDITIONAL / REJECT」+ 條件清單（如有）。
- 如 3 全 APPROVE → PA 把本 draft 升 `srv/docs/governance_dev/amendments/2026-05-1X--AMD-2026-05-1X-W6-1-rfc-verdict.md` 正式 AMD 件，dispatch v3.5 §6 條目對齊 commit。
- 如 ≥1 CONDITIONAL → PA 24h 內補修 draft，重 sign-off。
- 如 ≥1 REJECT → 重新 RFC（不應發生，因為三方立場已預跑且本 draft 全 capture）。

**Sign-off 後 commit chain**（D+1 evening）：
1. AMD-2026-05-1X-W6-1-rfc-verdict.md land
2. dispatch v3.5 §6 acceptance gate 條目 cross-ref AMD（§6.2 + §6.7 + §6.8 注釋）
3. CLAUDE.md §三 W6 wave 一行總結 land（cost_gate hard rule 維持 + scorer regression task 確認）
4. PA memory.md 追加 W6-1 verdict 摘要（為未來 N+2 想動 cost_gate / scorer task type 提供 audit trail）

**E2 重點審查 3 點**（W6-3c E1 IMPL + V086 land）：
1. **Backfill SQL evaluation order**：CASE WHEN 順序錯誤會誤分類（ATR unavailable 必先於 JS-demo / cost_gate_other；雙前綴必先於單前綴；bare-name exact 必先於 prefix regex）。E2 必走 PG dry-run 9757 row distribution 比對 audit table。
2. **Guard A/B/C 完整性**：V086 必含 3 Guard，缺一 = E2 拒簽（per memory `feedback_v_migration_pg_dry_run`）。
3. **Producer dual-write race**：V086 land 與 producer dual-write code deploy 不能差 >5 min；否則 V086 → dual-write deploy 期間的 new rows reject_reason_code = NULL，過 24h healthcheck 後 ALTER VALIDATE 會失敗。E2 必驗 deployment runbook 含 atomic deploy step。

---

## §11 副作用清單（W6 全 wave）

對每個改動問：(1) import 影響？(2) mock 測試影響？(3) async 邊界？(4) API schema？

| 改動 | 副作用 | 緩解 |
|---|---|---|
| V086 兩 column add | `learning.decision_features` schema 變動，所有讀此表的 query 不受影響（純 additive，read 默認 NULL） | NOT VALID CHECK new rows only，legacy 9.5M unscanned |
| trading.fills 17 row UPDATE | lock window <1 sec；不影響 pipeline writer（只改歷史污染字串） | atomic UPDATE in V086 migration |
| W-AUDIT-4b M3 producer dual-write | `intent_processor/mod.rs:1213` 解 V017 lock；新增 reject_reason_code + close_reason_code 寫入 | E2 必驗 dual-write race + atomic deploy |
| sample_weight ratio sensitivity 試行 | scorer_trainer 測試載入 4 weight ratio variant；**不 deploy production**，只 sandbox | MIT IMPL 走 `experiment_registry` shadow track |
| healthcheck [59]/[60]/[61]/[62] + [40] enhancement | passive_wait_healthcheck/checks_*.py 新檔；cron 每小時跑 | 與既有 51 check 同模板，無 cron schedule 動 |

**0 改動觸碰 16 root principles 4/5/9 + DOC-08 §12 9 不變量 + §四 5 硬邊界。**

---

PA DESIGN DONE: report path: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-10--w6_1_rfc_final_verdict_draft.md`
