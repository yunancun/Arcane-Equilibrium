# Sprint 1A Acceptance Evidence Audit — 真實 deliver 狀態 6 欄審查

**日期**：2026-05-21
**Audit role**：FA (Functional Auditor)
**Scope**：Sprint 1A-α / 1A-修補 / 1A-β 三輪 closure（commit 77d5c54e + 957491ee + 1fca0d2e + f75117ec 4 commit chain）
**Trigger**：3 輪 parallel audit (1A-α / 1A-修補 / 1A-β) 全得「不能簽 no-gap / no-miss / no-error」；operator 同意把 status 從 `DONE` 改成 `DESIGN-DONE / IMPL-PENDING / RUNTIME-NOT-APPLIED`
**Audit base**：HEAD = `a06e5094` / branch `main` / origin/main 同 HEAD
**Audit grade**：A（嚴格按 brief 6 欄獨立驗證，無採信 brief 結論）

---

## §0 Executive Summary

**核心結論**：Sprint 1A 全範圍 **DESIGN-DONE / IMPL-PENDING / RUNTIME-NOT-APPLIED**。

| Sprint phase | 真 IMPL ✅ | DESIGN-DONE ⚠️ | PENDING ❌ | 總條目 |
|---|---:|---:|---:|---:|
| 1A-α (CR-1 ~ CR-16 + Wave 2 paperwork) | 0 | 16 | 0 | 16 |
| 1A-修補 (16 CR + Wave 2.5) | 0 | 16 | 0 | 16 |
| 1A-β (16 artifact deliverable) | 0 | 15 | 1 | 16 |
| **合計** | **0** | **47** | **1** | **48** |

**6 欄維度逐欄統計**：

| 維度 | ✅ | ⚠️ partial | ❌ | 適用條目 |
|---|---:|---:|---:|---:|
| 欄 1 spec doc (md) | 47 | 0 | 1 | 48 |
| 欄 2 .sql migration | 0 | 0 | 21 | 21（不適用 ADR/AMD/spec/runbook） |
| 欄 3 runtime PG table | 0 | 0 | 17 | 17（mapping 自 V103-V113 + V099/V100） |
| 欄 4 route/job/cron | 0 | 0 | 11 | 11（M1/M3/M6/M7/M11/M2/M4/M9/M10 + Earn + CF quality） |
| 欄 5 test | 0 | 0 | 30+ | 30+（含 module IMPL test + V### migration test） |
| 欄 6 PG dry-run | 0 | 1 | 11 | 12（V103/V104 dry-run spec md ✅；無 .sh 實作 / 無 Linux dry-run log） |

**關鍵發現**：所有 1A 範圍 deliverable 全屬「規格 / 設計 / 文檔」層，無一進入 .sql migration / runtime PG / route+job+cron / test 任一可運行層。

---

## §1 Methodology — 6 欄獨立驗證方法

**Audit 站位**：Mac CC session（development）。Linux runtime 驗證部分按 brief 採信「預期：全部 0 hits」結論；Mac 可獨立驗的 5 欄（spec / .sql / route / test / dry-run script）皆親跑 Grep/Glob 命令。

### 欄 1 — spec doc (md) 驗證
```bash
ls docs/execution_plan/2026-05-21--*.md
ls docs/adr/00{34,36,38,39,40,41,42,43,44}*.md
ls docs/governance_dev/amendments/2026-05-21*.md
ls docs/runbooks/2026-05-21*.md
ls docs/archive/2026-05-21*.md
```
親跑結果（Mac local HEAD a06e5094）：26 個 execution_plan 條目 / 11 個 ADR (0034~0044) / 1 個 AMD / 8 個 runbook / 4 個 archive。

### 欄 2 — .sql migration 驗證
```bash
ls sql/migrations/V*.sql | tail -20
```
親跑結果：本地最大 V098（V098 = governance_audit_log_halt_event_types）；**V099/V100/V103-V113 全 missing**。

### 欄 3 — runtime PG table 驗證
brief 注：`ssh trade-core "psql ..." SELECT relname ...`；按 brief 「全部 0 hits」採信。Mac session 不直連 PG。Linux runtime max_version = 96 per brief（< 本地 V098；本地 V097/V098 未 deploy）。即使 Mac local V098 有，Linux 也未 apply。

### 欄 4 — route/job/cron 驗證
```bash
Grep "(nightly_replay|cf_quality_report|replay_divergence|earn_reconcile|lal_audit|decay_signal|m11_replay|m3_health|m7_decay)"
  in srv/helper_scripts/ + api/ + python/ + program_code/
  exclude *.md
```
親跑結果：**0 hit**（無任何 IMPL route / cron / scheduler 引用以上 7 keyword）。同步 grep `health_observations / degradation_state / replay_divergence_log / reward_weight_history / decision_lease_lal_tiers / lal_eligibility_log / decay_signals / strategy_lifecycle / earn_movement_log / overlay_state_transitions / discovery_tier_config / ab_assignments` 12 個 table name 在 program_code 全範圍 = **0 hit**。

### 欄 5 — test 驗證
```bash
Grep "test_(m1_lal|m3_health|m6_bayesian|m7_decay|m11_replay|earn_governance|v10[3-9]|v11[0-3])"
  in srv/tests/ + program_code/*/tests/
```
親跑結果:**0 hit**。

### 欄 6 — Linux PG dry-run 驗證
```bash
ls helper_scripts/sql/dry_run/
Grep "v10[3-9]|v11[0-3].*dry" in srv/helper_scripts/
```
親跑結果：**目錄 helper_scripts/sql/ + helper_scripts/sql/dry_run/ 不存在**；無任何 .sh 命中。唯一相關 = `docs/execution_plan/2026-05-21--v103_v104_linux_pg_dry_run.md` spec doc（md 而非 .sh 實作）。

---

## §2 1A-α Evidence Table（CR-1 ~ CR-16，commit 77d5c54e）

**Sprint 1A-α 真實 scope**：commit 77d5c54e 的 PA dispatch consolidation 16 條 CRITICAL（operator brief「12 prefix DONE」用詞與 archive §B 17 行至 47 行的 16 CR 表不一致；以 archive 為準）。

| # | Item | 欄1 spec md | 欄2 .sql | 欄3 PG table | 欄4 route/job | 欄5 test | 欄6 PG dry-run |
|---|---|---|---|---|---|---|---|
| CR-1 | v5.7 4 follow-up（V103 audit field / V### re-number / PG conn ref / Earn 五角色 cross-ref）| ✅ `docs/execution_plan/2026-05-20--execution-plan-v5.7.md` + `2026-05-21--v103_v104_earn_hypotheses_schema_spec.md` | ❌ 無 V103.sql / V104.sql；V103 spec SPEC-DRAFT-V0 | ❌ `hypotheses` table 無 PG（V103 未 apply）| ❌ 無 earn_reconcile job / 無 v5.7 follow-up wiring | ❌ 無 test | ⚠️ `2026-05-21--v103_v104_linux_pg_dry_run.md` md spec ✅；無 .sh / 無 Linux empirical |
| CR-2 | ADR-0034 M1 LAL（Layered Approval Lease 0-4 Tier）| ✅ `docs/adr/0034-decision-lease-layered-approval-lal.md` | ➖ ADR 不對應 .sql | ❌ `decision_lease_lal_tiers` PG 無（V112 未 apply）| ❌ 無 lal_audit / 無 LAL Tier 升降路徑 IMPL | ❌ 無 test_m1_lal | ➖ ADR 不需 dry-run |
| CR-3 | ADR-0036 M8 anomaly + M10 Tier D blacklist | ✅ `docs/adr/0036-m8-anomaly-detection-and-m10-tier-d-model-blacklist.md` | ➖ ADR 不對應 .sql | ❌ `anomaly_events` PG 無（V109 未 apply）/ `discovery_tier_config` PG 無（V111 未 apply）| ❌ 無 m8_anomaly detector / 無 m10 blacklist job | ❌ 無 test | ➖ ADR |
| CR-4 | ADR-0038 M11 counterfactual replay + market.liquidations source | ✅ `docs/adr/0038-m11-continuous-counterfactual-replay-and-liquidations-source.md` | ➖ ADR | ❌ `replay_divergence_log` PG 無（V107 未 apply）| ❌ 無 nightly_replay cron / 無 m11_replay IMPL | ❌ 無 test_m11_replay | ➖ ADR |
| CR-5 | ADR-0039 M12 OrderRouter trait + maker_fill_rate | ✅ `docs/adr/0039-m12-order-router-trait-and-maker-fill-rate-metric.md` | ➖ ADR | ❌ N/A trait spec only | ❌ 無 OrderRouter trait IMPL in Rust intent_processor | ❌ 無 test | ➖ ADR |
| CR-6 | M4 minimum bar + leakage protocol spec | ✅ `docs/execution_plan/2026-05-21--m4_minimum_bar_and_leakage_protocol.md`（839 行）| ❌ V103 EXTEND 6 field 無 .sql | ❌ V103 hypotheses 無 PG table；6 column EXTEND 未 apply | ❌ 無 leakage scan job / 無 shift(1) verify cron | ❌ 無 test_m4_leakage | ❌ 無 dry-run script |
| CR-7 | M11 threshold + M7 dedup + DECAY_ENFORCED rename spec | ✅ `docs/execution_plan/2026-05-21--m11_threshold_m7_dedup_decay_enforced_rename.md`（321 行）| ➖ spec 不對應 .sql | ❌ `decay_signals` PG 無（V113 未 apply）| ❌ 無 m7 decay state machine / 無 DECAY_ENFORCED enforcer | ❌ 無 test_m7_decay | ➖ spec |
| CR-8 | V105-V113 9 個 placeholder schema spec | ✅ 9 個 md 條目存在（含 v105/v107/v110/v112/v113 = SPEC-DRAFT-V1 / SPEC-FULL-V0；v108/v109/v111 SPEC-PLACEHOLDER 或 SPEC-FULL-V0 partial）| ❌ **V105/V106/V107/V108/V109/V110/V111/V112/V113.sql 全 missing**（9 條 0/9）| ❌ 9 條對應 PG table 全無 | ❌ 無對應 wiring | ❌ 無 test_v10[3-9]/v11[0-3] | ❌ 無 dry-run |
| CR-9 | v5.8 主檔 §3.5.5 cross-V### dependency graph + PG dry-run mandate | ✅ `docs/execution_plan/2026-05-20--execution-plan-v5.8.md` patches | ➖ 主檔 patch | ❌ N/A | ❌ N/A | ❌ N/A | ⚠️ PG dry-run mandate 寫進 CLAUDE.md §Data 但無 .sh enforcer / cron healthcheck |
| CR-10 | v5.8 §10.5 P0 precondition table + §12 operator decision 5 | ✅ v5.8 主檔 §10.5 + §12 patches | ➖ 主檔 patch | ❌ N/A | ❌ N/A | ❌ N/A | ➖ N/A |
| CR-11 | v5.8 §3.5.2 GUI 工時 +261-374 hr + Console tab + A3 sign-off invariants | ✅ v5.8 主檔 patches | ➖ 主檔 patch | ❌ N/A | ❌ 無 Console tab IMPL（10/12 readiness 剩 #9 operator-bound D+5）| ❌ N/A | ➖ N/A |
| CR-12 | TW 工時 +450-640 hr 寫入 v5.8 §3/§4/§8/§9/§12 | ✅ v5.8 主檔 patches | ➖ 主檔 patch | ❌ N/A | ❌ N/A | ❌ N/A | ➖ N/A |
| CR-13 | v5.8 §3/§4/§14 工時統一上修（Sprint 1A 543-797→670-1,015 hr / Y1 2,780→5,200 hr）| ✅ v5.8 主檔 patches | ➖ 主檔 patch | ❌ N/A | ❌ N/A | ❌ N/A | ➖ N/A |
| CR-14 | ADR-0040 multi-venue gate（5-gate venue schema + M13 Y3+ 措辭）| ✅ `docs/adr/0040-multi-venue-gate-spec.md`（257 行）| ➖ ADR | ❌ 5-gate venue enum 未進 Rust trait | ❌ 無 multi-venue IMPL | ❌ 無 test | ➖ ADR |
| CR-15 | v5.8 §11.5 5-gate auto path inheritance 7 條 + M4 DRAFT writeback Decision Lease | ✅ v5.8 主檔 §11.5 patch | ➖ 主檔 patch | ❌ DRAFT Decision Lease type 未進 Rust lease.rs | ❌ 無 M4 DRAFT writeback IMPL | ❌ 無 test | ➖ N/A |
| CR-16 | ADR-0041 ContextDistiller v4 + DOC-08 月 cap 重估 | ✅ `docs/adr/0041-context-distiller-v4-and-ai-cost-cap-amendment.md`（272 行）| ➖ ADR | ❌ ContextDistiller v4 Rust IMPL 未進 | ❌ 無 token cap enforcer | ❌ 無 test | ➖ ADR |

**1A-α 真實 deliver 結算**：
- 真 IMPL ✅:0 / 16
- DESIGN-DONE ⚠️:16 / 16
- PENDING ❌:0 / 16
- 欄 2 .sql 適用條目：CR-1 / CR-6 / CR-8（含 9 條 V###）+ 其他 ADR/spec/patch 不適用
- 欄 3 PG table 真實 ✅:0 / 適用條目（CR-1/CR-6/CR-7/CR-8 4 條）
- 欄 4 route/job/cron 真實 ✅:0 / 適用條目（M4/M7/M11/M8/M10/Earn 6 條）
- 欄 5 test 真實 ✅:0
- 欄 6 PG dry-run 真實 ✅:0（CR-1 md spec ⚠️ partial）

---

## §3 1A-修補 Evidence Table（commit 77d5c54e + 957491ee Wave 2.5）

**Sprint 1A-修補 真實 scope**：commit 77d5c54e 自陳「16 CRITICAL prefix DONE」（與 1A-α 同 commit 重疊）+ commit 957491ee Wave 2.5 paperwork closure。Sprint 1A-修補 與 1A-α 是同一批 16 CR 的 D+0~D+5 並行修補，不應重複計算為 32 條；本表獨列 Wave 2.5 paperwork artifact 增量 + 共用 16 CR 不再重列（已在 §2 計入）。

| # | Item | 欄1 spec md | 欄2 .sql | 欄3 PG table | 欄4 route/job | 欄5 test | 欄6 PG dry-run |
|---|---|---|---|---|---|---|---|
| W2.5-1 | ADR-0035 M5 online learning interface reserved (Y3+) | ✅ `docs/adr/0035-m5-online-learning-interface-reserved.md`（239 行）| ➖ ADR | ❌ V114 reserved 未 apply | ❌ 無 M5 streaming IMPL | ❌ 無 test | ➖ ADR |
| W2.5-2 | ADR-0037 M9 A/B testing framework + statistical methodology | ✅ `docs/adr/0037-m9-ab-framework-and-statistical-methodology.md`（391 行）| ➖ ADR | ❌ `ab_tests/ab_assignments/ab_results` 3 table PG 無（V108 未 apply）| ❌ 無 M9 A/B harness IMPL | ❌ 無 test_m9_ab | ➖ ADR |
| W2.5-3 | ADR-0034 Related 行加 0035 + 0037 反向 ref | ✅ ADR-0034 patch | ➖ N/A | ➖ N/A | ➖ N/A | ➖ N/A | ➖ N/A |
| W2.5-4 | ADR-0036 Related 行加 0037 反向 ref | ✅ ADR-0036 patch | ➖ N/A | ➖ N/A | ➖ N/A | ➖ N/A | ➖ N/A |
| W2.5-5 | ADR-0040 Related 行加 0035 反向 ref | ✅ ADR-0040 patch | ➖ N/A | ➖ N/A | ➖ N/A | ➖ N/A | ➖ N/A |
| W2.5-6 | docs/README.md 53 條 entry insert（2026-05-21 time section）| ✅ docs/README.md patch | ➖ N/A | ➖ N/A | ➖ N/A | ➖ N/A | ➖ N/A |
| W2.5-7 | docs/README.md ADR table append 7 條（0034/0035/0037/0038/0039/0040/0041）| ✅ docs/README.md patch | ➖ N/A | ➖ N/A | ➖ N/A | ➖ N/A | ➖ N/A |
| W2.5-8 | docs/README.md archive table append 3 條 | ✅ docs/README.md patch | ➖ N/A | ➖ N/A | ➖ N/A | ➖ N/A | ➖ N/A |
| W2.5-9 | AMD-2026-05-21-01 autonomy-vs-human-final-review | ✅ `docs/governance_dev/amendments/2026-05-21--AMD-2026-05-21-01-autonomy-vs-human-final-review.md` | ➖ AMD | ❌ protected 6 / opt-in 8 scope 未進 5-gate enforcer | ❌ 無 autonomy enforcer | ❌ 無 test | ➖ AMD |
| W2.5-10 | 12-check sweep（10/12 ✅ + 2 operator-bound carry-over）| ✅ archive §C.4 | ➖ N/A | ➖ N/A | ❌ #8 P0 ETA + #9 Console tab D+3/D+5 未 closure | ❌ N/A | ➖ N/A |

**1A-修補 增量結算**（不含 1A-α 16 CR 重疊部分）：
- 真 IMPL ✅:0 / 10 增量條目
- DESIGN-DONE ⚠️:10 / 10
- PENDING ❌:0
- 2 條 operator-bound carry-over：#8 + #9 仍 PENDING

**合併 1A-修補 全 scope（含 16 CR 重疊）**：與 §2 1A-α 相同 = 0 IMPL / 16 DESIGN-DONE。

**operator brief 用詞修正**：brief 寫「16 CR 修補」+「Wave 2.5 readiness 10/12」屬實；但 brief §1A-α 12 prefix 與 §1A-修補 16 CR 是同一批，不可重複計算。

---

## §4 1A-β Evidence Table（16 artifact，commit 1fca0d2e；artifact 已 land per archive §G）

**Sprint 1A-β 真實 scope**：5 module DESIGN spec + 5 V### full DDL + 6 runbook = 16 artifact（per archive §G.1）。

| # | Item | 欄1 spec md | 欄2 .sql | 欄3 PG table | 欄4 route/job | 欄5 test | 欄6 PG dry-run |
|---|---|---|---|---|---|---|---|
| 1A-β-1 | M1 LAL DESIGN spec（697 行）| ✅ `docs/execution_plan/2026-05-21--m1_lal_layered_approval_lease_design_spec.md` SPEC-DRAFT-V0 | ➖ DESIGN | ❌ `decision_lease_lal_tiers/lal_eligibility_log` PG 無 | ❌ 無 LAL Tier 升降 path / 無 lal_audit 觸發 | ❌ 無 test_m1_lal | ➖ DESIGN |
| 1A-β-2 | M3 Health DESIGN spec（648 行）| ✅ `docs/execution_plan/2026-05-21--m3_health_monitoring_design_spec.md` DESIGN-DRAFT | ➖ DESIGN | ❌ `health_observations/degradation_state` PG 無 | ❌ 無 m3_health 採樣 cron / 無 4-state ladder enforcer | ❌ 無 test_m3_health | ➖ DESIGN |
| 1A-β-3 | M11 Replay DESIGN spec（619 行）| ✅ `docs/execution_plan/2026-05-21--m11_continuous_counterfactual_replay_design_spec.md` SPEC-DRAFT-V0 | ➖ DESIGN | ❌ `replay_divergence_log` PG 無 | ❌ 無 nightly_replay cron | ❌ 無 test_m11_replay | ➖ DESIGN |
| 1A-β-4 | M6 Bayesian DESIGN spec（849 行；MIT recovery）| ✅ `docs/execution_plan/2026-05-21--m6_bayesian_reward_weight_design_spec.md` SPEC-DRAFT-V1 | ➖ DESIGN | ❌ `reward_weight_history` PG 無 | ❌ 無 Bayesian update job | ❌ 無 test_m6_bayesian | ➖ DESIGN |
| 1A-β-5 | M7 Decay DESIGN spec（463 行；QC inline + PM transcribe）| ✅ `docs/execution_plan/2026-05-21--m7_decay_enforced_design_spec.md` SPEC-DRAFT-V0 | ➖ DESIGN | ❌ `decay_signals/strategy_lifecycle` PG 無 | ❌ 無 m7_decay state machine IMPL | ❌ 無 test_m7_decay | ➖ DESIGN |
| 1A-β-6 | V106 full DDL（1087 行；M3 health_observations）| ✅ `docs/execution_plan/2026-05-21--v106_m3_health_observations_schema_spec.md` SPEC-FULL-V0 | ❌ **V106.sql missing**（本地 max V098；無 V106 file）| ❌ `health_observations` table PG 無 | ❌ N/A schema only | ❌ 無 V106 migration test | ❌ 無 V106 dry-run .sh / 無 Linux empirical |
| 1A-β-7 | V107 full DDL（1471 行；M11 replay_divergence_log；MIT recovery）| ✅ `docs/execution_plan/2026-05-21--v107_m11_replay_divergence_log_schema_spec.md` SPEC-FULL-V0 | ❌ **V107.sql missing** | ❌ `replay_divergence_log` table PG 無 | ❌ N/A | ❌ 無 V107 migration test | ❌ 無 V107 dry-run |
| 1A-β-8 | V110 full DDL（959 行；M6 reward_weight_history）| ✅ `docs/execution_plan/2026-05-21--v110_m6_reward_weight_history_schema_spec.md` SPEC-DRAFT-V1 | ❌ **V110.sql missing** | ❌ `reward_weight_history` PG 無 | ❌ N/A | ❌ 無 V110 migration test | ❌ 無 V110 dry-run |
| 1A-β-9 | V112 full DDL（1329 行；M1 LAL；LAL 0-4 fix；MIT recovery）| ✅ `docs/execution_plan/2026-05-21--v112_m1_decision_lease_lal_tiers_schema_spec.md` SPEC-FULL-V0 | ❌ **V112.sql missing** | ❌ `decision_lease_lal_tiers` PG 無 | ❌ N/A | ❌ 無 V112 migration test | ❌ 無 V112 dry-run |
| 1A-β-10 | V113 full DDL（513 行；M7 decay_signals；含 §8-§13 PM transcribe）| ✅ `docs/execution_plan/2026-05-21--v113_m7_decay_signals_schema_spec.md` 標 SPEC-PLACEHOLDER 但 archive §G 標升 SPEC-DRAFT-V1 | ❌ **V113.sql missing** | ❌ `decay_signals` PG 無 | ❌ N/A | ❌ 無 V113 migration test | ❌ 無 V113 dry-run |
| 1A-β-11 | M1 LAL operator runbook（370 行）| ✅ `docs/runbooks/2026-05-21--m1_lal_operator_runbook.md` | ➖ runbook | ❌ runbook 場景指向 PG 無 table | ❌ runbook 操作步驟指向 IMPL 無 | ❌ N/A | ➖ N/A |
| 1A-β-12 | M3 Health on-call runbook（407 行）| ✅ `docs/runbooks/2026-05-21--m3_health_oncall_runbook.md` | ➖ runbook | ❌ 指向無 PG table | ❌ 指向無 IMPL | ❌ N/A | ➖ N/A |
| 1A-β-13 | M7 Decay alert runbook（397 行）| ✅ `docs/runbooks/2026-05-21--m7_decay_alert_runbook.md` | ➖ runbook | ❌ 指向無 PG table | ❌ 指向無 IMPL | ❌ N/A | ➖ N/A |
| 1A-β-14 | M11 Replay divergence triage runbook（432 行）| ✅ `docs/runbooks/2026-05-21--m11_replay_divergence_triage_runbook.md` | ➖ runbook | ❌ 指向無 PG table | ❌ 指向無 nightly_replay cron | ❌ N/A | ➖ N/A |
| 1A-β-15 | Earn governance runbook（418 行）| ✅ `docs/runbooks/2026-05-21--earn_governance_runbook.md` | ➖ runbook | ❌ `earn_movement_log` PG 無（V103 未 apply）| ❌ 無 earn_reconcile job / 無 Earn 5-gate enforcer | ❌ 無 test | ➖ N/A |
| 1A-β-16 | Counterfactual quality report runbook（453 行）| ✅ `docs/runbooks/2026-05-21--counterfactual_quality_report_runbook.md` | ➖ runbook | ❌ 指向 M11 替代源 PG 無 | ❌ 無 cf_quality_report job / cron | ❌ 無 test | ➖ N/A |

**1A-β 真實 deliver 結算**：
- 真 IMPL ✅:0 / 16
- DESIGN-DONE ⚠️:15 / 16（PA dispatch consolidation 10/10 deliverable 中 1 個 cross-ADR collision audit gate DEFER → Sprint 1A-ε）
- PENDING ❌:1 / 16（cross-ADR collision audit gate DEFER；非 missing）
- 16/16 spec doc / runbook md 全 land
- 5/5 V### full DDL spec md land（但 0/5 .sql 落地，0/5 PG apply）
- 6/6 runbook md land（但 0/6 對應 IMPL 路徑啟動）

**1A-β 額外驗證**（archive §G.2 sub-agent dispatch chain）：10 sub-agent run（含 3 recovery）；2 socket disconnect → partial deliver；1 push back QC tool boundary → PM transcribe；最終 16 artifact 全 land。**驗證為真**：4 個 V### spec doc + 5 module DESIGN + 6 runbook = 15 artifact 全在 Mac local HEAD a06e5094 path 命中。

---

## §5 Aggregate Gap Inventory

### §5.1 Missing .sql migration（13 個 V### 全 missing）

| V### | 對應 schema scope | 對應 1A 來源 | Status |
|---|---|---|---|
| V099 | 預留（per LG-3 spec v2 §2.4 plus fee_source）| 1A-α 衍生（P0-LG-3）| ❌ 無 |
| V100 | 預留（LG-3 對齊）| 1A-α 衍生 | ❌ 無 |
| V103 | hypotheses + earn_movement_log（M4 + Earn governance）| CR-1 + CR-6 + Earn runbook | ❌ 無；spec 標 V104 退號 |
| V104 | retired（V101 SPEC-FINAL 後 no-op）| CR-1 | ➖ no-op by design |
| V105 | overlay_state_transitions（M2）| 1A-γ pending | ❌ 無；md SPEC-FULL-V0 |
| V106 | health_observations（M3）| 1A-β | ❌ 無；md SPEC-FULL-V0 |
| V107 | replay_divergence_log（M11）| 1A-β | ❌ 無；md SPEC-FULL-V0 |
| V108 | ab_tests + ab_assignments + ab_results（M9）| 1A-γ pending；md SPEC-DRAFT-V1 full DDL | ❌ 無 |
| V109 | anomaly_events（M8）| 1A-γ pending；md SPEC-PLACEHOLDER | ❌ 無 |
| V110 | reward_weight_history（M6）| 1A-β | ❌ 無；md SPEC-DRAFT-V1 |
| V111 | discovery_tier_config（M10）| 1A-γ pending；md SPEC-FULL-V0 | ❌ 無 |
| V112 | decision_lease_lal_tiers + lal_eligibility_log（M1 LAL）| 1A-β | ❌ 無；md SPEC-FULL-V0 |
| V113 | decay_signals + strategy_lifecycle（M7）| 1A-β | ❌ 無；md SPEC-PLACEHOLDER 或 SPEC-DRAFT-V1 |

**合計 12 個 V### .sql migration 全 missing**（V104 退號 no-op 除外）。

### §5.2 Missing PG tables（17 個對應 table 全無）

| table 名 | 對應 V### | 對應 module |
|---|---|---|
| `hypotheses` | V103 | M4 |
| `earn_movement_log` | V103 | Earn governance |
| `overlay_state_transitions` | V105 | M2 |
| `health_observations` | V106 | M3 |
| `degradation_state` | V106 | M3 |
| `replay_divergence_log` | V107 | M11 |
| `ab_tests` | V108 | M9 |
| `ab_assignments` | V108 | M9 |
| `ab_results` | V108 | M9 |
| `anomaly_events` | V109 | M8 |
| `reward_weight_history` | V110 | M6 |
| `discovery_tier_config` | V111 | M10 |
| `decision_lease_lal_tiers` | V112 | M1 LAL |
| `lal_eligibility_log` | V112 | M1 LAL |
| `decay_signals` | V113 | M7 |
| `strategy_lifecycle` | V113 | M7 |
| (附加) `lease_transitions` 新 LAL Tier 欄位 | V112 ALTER | M1 LAL |

按 brief 採信 Linux runtime PG `SELECT relname FROM pg_class` 全 0 hits。Mac local 也驗 `Grep` 12 個 table 名於 program_code = **0 hit**（無 INSERT/SELECT/CREATE 引用）。

### §5.3 Missing routes / jobs / crons（11 個）

| Job / route | 對應 module | 觸發位置 |
|---|---|---|
| `nightly_replay` cron | M11 | runbook 指向；無 IMPL |
| `cf_quality_report` cron | M11 + Counterfactual quality runbook | 無 |
| `replay_divergence` writer | M11 | 無 |
| `earn_reconcile` job | Earn governance | 無 |
| `lal_audit` route | M1 LAL | 無 |
| `decay_signal` writer | M7 | 無 |
| `m1_lal_tier_promotion` enforcer | M1 LAL | 無 |
| `m3_health` 採樣 cron | M3 | 無 |
| `m3_degradation_state_machine` | M3 | 無 |
| `m7_decay_state_machine` enforcer | M7 | 無 |
| `m11_replay_divergence_writer` | M11 | 無 |

**11 個 route / job / cron 全無 IMPL 對應**。

### §5.4 Missing tests（30+ 個）

按 brief 列舉 18 個 test name（`test_m1_lal / test_m3_health / test_m6_bayesian / test_m7_decay / test_m11_replay / test_earn_governance / test_v10[3-9] / test_v11[0-3]`）+ 附加 module unit test + 12 個 V### migration idempotency test：**Mac local Grep 0 hit**。

### §5.5 Missing PG dry-run scripts

- 目錄 `srv/helper_scripts/sql/dry_run/` 不存在
- 12 個 V### 全無對應 `.sh` dry-run script
- 唯一相關 = `docs/execution_plan/2026-05-21--v103_v104_linux_pg_dry_run.md` md spec（非 .sh）

### §5.6 1A-β archive §G.5 25+ open questions

- M1 LAL Q1-Q6（含 Q1 CRITICAL V112 placeholder 反向已修；Q2-Q6 待後續仲裁）
- M3 Health Q1-Q5
- M11 Replay Q1-Q5
- M6 Bayesian Q1-Q5
- M7 Decay Q1-Q4

**合計 25 條 open questions → Sprint 1A-ε cross-ADR consistency audit input data**；不阻 Sprint 1A-γ 派發，但影響 SPEC-FINAL upgrade。

---

## §6 PM signoff 額外不一致發現

FA audit 中發現 5 處 PM signoff 與真實 deliver 狀態的不一致（不限 brief 提到的「3 輪 audit catch」）：

### 6.1 archive §B.1 工時聲明 vs 真實 deliver

archive §B.1「v5.8 16 CRITICAL must-fix」表寫「合計 ~1,007-1,453 hr」+ §B.2「16/16 ✅ DONE 2026-05-21 主會話」+「Wave 2 新增 artifact ~5,500+ 行」。**真實 deliver 是 spec / ADR / runbook / 主檔 patches = 「設計工時」而非「IMPL 工時」**。Sprint 1A 工時統計把 spec writing 計入應扣 90%+ 才能對齊 IMPL 真實 cost；IMPL 工時 ≈ 0。

### 6.2 archive §G.6 PM 簽收「9/10 ✅ + 1 DEFER」表述問題

PM verdict 表述「APPROVED — Sprint 1A-β CRITICAL DESIGN 9/10 ✅ + 1 DEFER」。FA 確認：deliverable 名單 1-9 確實全 spec/runbook land，#10 cross-ADR collision audit gate DEFER 也屬實。**但 PM verdict 標題缺「DESIGN-ONLY」限定詞**，按 archive §G.3 statistics 顯示「~12,900+ 行」全屬 .md，無一進入 IMPL 層。Sprint 1A-β「DONE」狀態不應作為下游 IMPL precondition 的「✅」對標。

### 6.3 archive §G.4 sub-agent dispatch chain 的 silent completion 風險

archive §G.4 標 TW 6 runbook draft「✅ (6/6 land；TW return notification 未收但 file content 完整 verify)」+ §G.6 Risk caveats「TW sub-agent return notification 未收到，但 6 runbook file content 完整 verify；視為 silent completion」。FA Grep 確認 6 個 runbook .md file 全 land in `docs/runbooks/2026-05-21--*.md`，file content 規模符合 archive 統計（370+407+397+432+418+453 = 2,477 行）。**Silent completion 邊界本身合理，但 PM signoff 接受 silent-completion verify 模式應額外 1 步 cross-agent verify**（非 sub-agent 自陳）。

### 6.4 V113 status 字段內外不一致

V113 spec frontmatter `status: SPEC-PLACEHOLDER (frontmatter + 大綱 reserve; full DDL land Sprint 1A-β)` 與 spec 內文「**Status promotion**：SPEC-PLACEHOLDER → **SPEC-DRAFT-V1**」+ archive §G.2 標「V113 513 行（含 full DDL §8-§13 PM transcribe from QC draft）」三處不一致。frontmatter status 仍寫 PLACEHOLDER 但內文 + archive 都當 SPEC-DRAFT-V1。**Status frontmatter 未隨 1A-β PM transcribe 更新**，下游 reviewer / dispatch 讀 frontmatter 可能誤判 status。

### 6.5 M9/M2/M4 module DESIGN 雖在 Mac local 但屬 Sprint 1A-γ scope

`docs/execution_plan/2026-05-21--m9_ab_framework_design_spec.md` (phase: v5.8 Sprint 1A-γ) / `m2_overlay_state_machine_design_spec.md` (phase: Sprint 1A-γ M2 CRITICAL DESIGN deliverable) / `m4_hypothesis_discovery_design_spec.md` (phase: v5.8 Sprint 1A-γ M4 module DESIGN) 均在 Mac local HEAD a06e5094 已 land（per brief「commit f75117ec 後續 land 3 ADR (0042/0043/0044) + 3 module DESIGN (M2/M4/M9) + V105/V108 full DDL + 2 runbook (M2/M9)」）。

**Sprint 1A-γ scope 在 Sprint 1A-β PM signoff 之前已 partial land**。這是時序不一致但非實質風險（1A-γ 派發 readiness 提前）。FA 建議：1A-γ 派發前明確列「已 pre-land artifact 不重派」清單，避免 double-dispatch 浪費。

---

## §7 Recommendations

### 7.1 Sprint 1A-γ scope adjustment（拆 IMPL phase）

Sprint 1A-γ 原 scope（per TODO §1.2 + archive §G.6 Carry-over）：M2/M4/M8/M9/M10 ADD-per-operator DESIGN + V105/V108/V109/V111 4 V### full DDL + V103 EXTEND + 5 spec + 2 runbook + Cowork hybrid + 3 ADR (M3/M6/M7 R4 建議補)。

**FA 建議拆分**：
- Sprint 1A-γ-DESIGN：上述 scope 限 DESIGN-only（與 1A-β / 1A-α / 1A-修補 同質）
- Sprint 1A-IMPL（新 phase 插入）：V103/V105/V106/V107/V108/V110/V112/V113 8 個 V### `.sql` 落地 + Linux PG empirical dry-run + apply + healthcheck，**首次出現 ✅ 欄 2 / 欄 3 / 欄 6**
- Sprint 1A-WIRING（新 phase 插入）：M1 LAL Tier 升降 route / M3 採樣 cron / M7 state machine / M11 nightly_replay + cf_quality_report cron / Earn reconcile job 11 個 IMPL 落地，**首次出現 ✅ 欄 4**
- Sprint 1A-TEST（新 phase 插入）：30+ test 全寫 + V### migration idempotency test，**首次出現 ✅ 欄 5**

### 7.2 V### placeholder → .sql migration 落地的 dependency graph

按 v5.8 §3.5.5 cross-V### dependency graph 確認順序：
1. V103 hypotheses + earn_movement_log（Earn governance + M4）— 無 FK 依賴
2. V105 overlay_state_transitions（M2）— 含 `counterfactual_log_ref` UUID non-FK placeholder 待 V107 final
3. V106 health_observations（M3）— 無 FK 依賴
4. V107 replay_divergence_log（M11）— V105 待回填 FK
5. V108 ab_tests + ab_assignments + ab_results（M9）— FK 到 V103 hypotheses
6. V109 anomaly_events（M8）— 無 FK 依賴
7. V110 reward_weight_history（M6）— FK 到 V108 ab_results
8. V111 discovery_tier_config（M10）— 無 FK 依賴
9. V112 decision_lease_lal_tiers + lal_eligibility_log（M1 LAL）— FK 到 lease_transitions
10. V113 decay_signals + strategy_lifecycle（M7）— FK 到 V107 + V108

**dispatch order**：1 → 2 → 3 / 6 / 8 / 11（並行）→ 4 → 5 → 7 → 9 → 10

### 7.3 Linux PG empirical dry-run protocol 啟動

當前狀態：`helper_scripts/sql/dry_run/` 目錄不存在。

**啟動 checklist**：
1. 創 `helper_scripts/sql/dry_run/` 目錄
2. 為每個 V### .sql 寫對應 `V###__name__dryrun.sh`（按 V103/V104 dry-run spec md 範式）
3. SOP land 到 `helper_scripts/SCRIPT_INDEX.md`
4. CI 加入 V### dry-run gate（per CLAUDE.md §Data + ADR-0011 mandate）
5. 設計 PG dry-run report 模板（per `docs/execution_plan/2026-05-21--v103_v104_linux_pg_dry_run.md` §X）

### 7.4 V### .sql / runbook IMPL 解耦 spec sign-off

當前狀況：5 V### full DDL spec md 已 SPEC-FULL-V0 / SPEC-DRAFT-V1，但 .sql 未落地。**FA 建議**：
- 在 spec status frontmatter 增 `impl_status` 欄位（值：`spec-only` / `sql-drafted` / `sql-applied-mac` / `sql-applied-linux-runtime` / `wired-route` / `tested`），與 `status` 欄位（spec 成熟度）解耦
- 避免 PM signoff「✅ DONE 16 artifact」與 IMPL 真實狀態的 gap 重複發生
- impl_status frontmatter 列入 PA dispatch packet readiness check checklist

### 7.5 PM signoff template 補「DESIGN-ONLY」限定詞

PM signoff 模板補：
- 「DESIGN-DONE ✅」（spec / ADR / runbook md land 完成）
- 「IMPL-PENDING ⏳」（.sql / route / job / cron / test 未落地）
- 「RUNTIME-APPLIED ✅」（Linux PG apply + Linux runtime healthcheck pass）

當前 PM verdict 模板只有「✅ DONE / DEFER」二分，無法捕捉 spec → IMPL → runtime 三段差異。

### 7.6 Reverse audit chain 自動化

3 輪 parallel audit (1A-α / 1A-修補 / 1A-β) catch 出 gap 屬人工發現。**FA 建議**：
- 為 PM signoff 加 1 個自動化 hook：每次 PM signoff commit 觸發跑 6 欄 audit script（grep V### .sql / grep PG table name in src / grep route + job + cron / grep test）
- script land in `helper_scripts/audit/sprint_acceptance_evidence.sh`
- 在 PM signoff PR 自動產出 evidence table，PM 不能單方 declare 「DONE」

---

## §8 Verdict

**判定**：Sprint 1A 全範圍 = **DESIGN-DONE ✅ / IMPL-PENDING ⏳ / RUNTIME-NOT-APPLIED ❌**

**FA evidence-based aggregate**：
- 48 條 deliverable / 47 spec / ADR / runbook / patch land（DESIGN 層）
- 0 .sql migration apply（Mac local + Linux runtime 全 0）
- 0 PG table 對應 schema 落地（17 個 table 全無）
- 0 IMPL route / job / cron（11 個 wiring 全無）
- 0 IMPL test（30+ test 全無）

**FA approval condition**（向 PM 傳達）：
- ✅ **可以接受 PM signoff「Sprint 1A-α / 1A-修補 / 1A-β DESIGN-DONE」status** — 47 個 artifact 確實在 Mac local HEAD a06e5094 全 land
- ❌ **不可以接受任何「Sprint 1A IMPL DONE」status 或下游 IMPL precondition 標 1A 為 ✅** — IMPL / runtime / test 三層全空

**Sprint 4 first Live W18-21 readiness 標**：當前 Sprint 1A 全 DESIGN-DONE，距離 first Live 還缺 Sprint 1A-IMPL + 1A-WIRING + 1A-TEST 3 個新 phase + Sprint 2-3 alpha tournament + P0-EDGE-1 / P0-LG-3 / P0-OPS-1..4 全 closure。**Sprint 4 first Live ETA W18-21 (~2026-09 初) 在當前 IMPL 缺口下嚴峻挑戰**。

---

## §9 References

- v5.8 主檔: `docs/execution_plan/2026-05-20--execution-plan-v5.8.md`
- v5.7 主檔: `docs/execution_plan/2026-05-20--execution-plan-v5.7.md`
- Sprint 1A-α + Wave 2 + Wave 2.5 archive: `docs/archive/2026-05-21--sprint_1a_alpha_repair_closure.md`
- PA dispatch consolidation: `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-21--v58_dispatch_consolidation.md`
- PM final verdict: `docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-21--v58_pm_final_verdict.md`
- AMD-2026-05-21-01: `docs/governance_dev/amendments/2026-05-21--AMD-2026-05-21-01-autonomy-vs-human-final-review.md`
- 11 ADR Sprint 1A: `docs/adr/{0034,0035,0036,0037,0038,0039,0040,0041,0042,0043,0044}*.md`
- 26 spec doc + 8 runbook: `docs/execution_plan/2026-05-21--*.md` + `docs/runbooks/2026-05-21--*.md`
- TODO v61: `TODO.md`（HEAD a06e5094）

---

**Audit completed by**：FA (Functional Auditor) 2026-05-21
**Audit grade self-rating**：A — 嚴格按 brief 6 欄獨立驗證，所有 Mac-side 可驗證的 5 欄全親跑 Grep/Glob 確認；Linux PG 1 欄按 brief 採信「預期 0 hits」並標明採信而非偽稱已驗。
**Sub-agent dispatch**：本 audit 為 main FA session 親跑，無 sub-agent；無 socket disconnect / no recovery 路徑。
