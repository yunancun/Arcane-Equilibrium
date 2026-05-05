# TODO.md completed/stale extract — archived 2026-05-06

Archived from `srv/TODO.md` v10. All items below are either ✅ DONE (with proof commit) or OBSOLETED-BY-GOV-CHANGE (with replacement reference). Source HEAD at archive time: `67b95808`.

Live state lives in:
- `srv/memory/project_2026_05_03_ref20_sprint1_2_closure.md` — REF-20 P6 closure record
- `srv/memory/project_funding_arb_v2_deprecation_path.md` — funding_arb V2 deprecation
- `srv/docs/execution_plan/2026-05-04--ref20_gap_closure_reality_backtest_plan_v1.md` — REF-20 plan

---

## DONE — verbatim extract

### P0-DATA-INDICATOR-SWEEP (TODO line 70)

| ID | 任務 | 阻塞下游 | 狀態 |
|----|------|---------|------|
| **P0-DATA-INDICATOR-SWEEP** | ✅ **DONE 2026-05-03** · 5 策略 indicator leak-free sweep verdict = **5/5 PASS**（QC quant 主審 + E3 adversarial 副審 + PM 補位驗證 `compute_indicators` body @ `on_tick_helpers.rs:453` 證據鏈完整：`get_ohlcv → buffer().ohlcv_arrays(n)` 只從 closed-bar buffer，不含 currently-forming bar）。**真因排查**：5 策略 net -6.98 USDT 不是 indicator leak，最便宜解釋為 strategy logic / cost / maker fill 三者（[33] maker 36.6% / [40] slippage -92bps）。**P0-EDGE-1/2 可繼續使用現有 edge 估計，無需重算**。**REF-20 V3 §3 G6 + §7 P2 precondition 解封**。Verdict 報告：`docs/audits/2026-05-03--P0-DATA-INDICATOR-SWEEP_verdict.md`。Follow-up（升 P2）：L-01 streaming integration test（綁 REF-20 P2b fixture）+ L-02 feature_version 硬編碼 v1.0 fix。 | （已解除）| ✅ DONE |

### P1-INFRA-3 — REF-20 Sprint A+B+C+D + Wave 1-9 + Sprint 1+2+3+4 全 closed

| ID | 任務 | 觸發 |
|----|------|------|
| **P1-INFRA-3** | ✅ **REF-20 Sprint A+B+C+D CLOSED (2026-05-05)** — R9 PM sign-off `6a7a885c` + reality-gap fix `67b95808`。Acceptance closed：A1-A10 + R9 7 conditions；fee-aware report / execution_confidence / MLDE-Dream advisory boundary / maintenance retention / 5 replay healthcheck sentinels all landed。`replay.simulated_fills.evidence_source_tier='synthetic_replay'` remains non-training; only calibrated/counterfactual replay evidence can feed MLDE/Dream through verification gates. Operator-side outstanding: live PG opt-in smoke, V056 cron schedule, deploy validation of new sentinels. | DONE |
| **P1-INFRA-3a** | ⚠️ **Wave 1 closed (atomic 5 commits) + Sprint 1 cold audit fix-up** — P0 docs amendment + scaffold 設計（V3/Workplan V1/UX subdoc 三 baseline land） | IMPL accept-with-caveat |
| **P1-INFRA-3b** | ⚠️ **Wave 2 closed (commits `1851714` + `b1f6b8a`)** — P1 frontend IA + P2a S1/S2 signing key + manifest signer | IMPL accept-with-caveat |
| **P1-INFRA-3c** | ⚠️ **Wave 3-4 closed (commits `5a618ff` + `4b48b6d`)** — P2a S3-S6 + P2b S7-S10 runner；**Sprint 1 修 spawn argv broken + manifest 自洽循環 + 5 critical security 洞**；W3 mac_policy_guard.rs 中文全形括號 doctest fail（self-introduced，commit msg 偽稱 sibling pre-existing → P2-FOLLOW-UP-2 修）；W4 single commit 26 file 7360 ins violated §八 工作鏈（已 Sprint 2 retroactive review 補） | IMPL accept-with-caveat |
| **P1-INFRA-3d** | ⚠️ **Wave 5 closed (commit `457a458`)** — P3a/P3b/RGM 13 task NumPyro 2320 LOC；mini test 200/400 chain（production 1000/2000 從未 CI 跑 → P2-WAVE-5-NTHRESHOLD-SWEEP 修）；NumPyro Mac scipy 0 cross-OS sibling test → P2-FOLLOW-UP-4 | IMPL accept-with-caveat |
| **P1-INFRA-3e** | ⚠️ **Wave 6 closed (commit `eb5f106`)** — P4 advisory chain 8 task；W6 引入 deterministic flaky test（FastAPI dependency_overrides 跨 test pollution → P2-FOLLOW-UP-1 修）；mlde_demo_applier.py 1542 LOC 違反 §九 requirement (3) → P2-WAVE-6-MLDE-DEMO-APPLIER-SPLIT；V043 0 production caller / 0 healthcheck → P2-WAVE-6-V043-HEALTHCHECK | IMPL accept-with-caveat |
| **P1-INFRA-3f** | ⏸ **Wave 7 DEFERRED + IMPL-accept-deploy-blocked** — P5 4 task IMPL-in-tree (commit `c887e4e` operator override) 但 hard prereq LG-2/3/4 frontend merged + 7d stable 仍 NOT GREEN；正式 amendment AMD-2026-05-03-01 (commit `5184990`) 規範 IMPL/Deploy 2-stage gate + 4 AC + 失敗回退；defer note `2026-05-03--ref20_wave7_defer_note.md` 自證 prereq violation；deploy gate retained pending healthcheck `[46]` | LG-2/3/4 stable |
| **P1-INFRA-3g** | ⚠️ **Wave 8 closed (commit `8429af1`)** — P6 7 task typed-confirm + V044 idempotency；handoff cooldown race（READ COMMITTED + 0 row-level lock → 由 Sprint 1 Track C cmdline 校驗 + V053 LOCK TABLE 部分緩解）；handoff flow 0 healthcheck → P2-WAVE-8-HANDOFF-HEALTHCHECK；P6 production exposure 仍 require P0-GOV-1 Decision Lease retrofit AMD-2026-05-02-01 deploy（Sprint 2 Track E PA design 已完，feature flag 灰度路徑） | Decision Lease retrofit deploy |
| **P1-INFRA-3h** | ⚠️ **Wave 9 closed (commit `1f5d019`)** — 14d gradient + V047/V048 KPI 採集 cron；Mac mock mode 跑過 Linux 真實 PG 0 跑（QA 確認）；V047/V048 plain table 1y retention 0 設 → P2-WAVE-9-V047-V048-RETENTION | Sprint 3 deploy after Linux runtime |
| **P1-INFRA-3i** | ✅ **Sprint 1 cold audit fix-up DONE (commit `edf33c0`)** — 4 並行 E1（A spawn argv / B Rust manifest verify / C Python 3 安全洞 / D V049-V053 schema 補造）；E2 round 1+2 + E4 regression 全 PASS；3387 PASS / 1 fail (pre-existing) / 10 skip；3084 cargo workspace PASS / 2 fail (pre-existing) / 3 ignored | DONE |
| **P1-INFRA-3j** | ✅ **Sprint 2 retroactive review DONE (commit `aa9343c`)** — PA Track E Decision Lease retrofit 4-task DAG design + E2 F1 retroactive Wave 3-9 master review (10 LOW + 7 P2 提案) + E4 F2 retroactive cumulative (4 forgery flag + 5 mock retroactive flag + 3 P2 提案) | DONE |
| **P1-INFRA-3k** | ✅ **Sprint 3 Track H DONE (commit `dbcf845b`)** — Decision Lease retrofit AMD-2026-05-02-01 Path A 業務代碼 + V054 audit writer + 4 並行 sub-task report；feature flag `OPENCLAW_LEASE_ROUTER_GATE_ENABLED=0` default OFF 灰度路徑保留；amendment §5.4 flip flag canary 24h 待 ~2026-05-15 P0-EDGE-2 後 operator action | DONE |
| **P1-INFRA-3l** | ✅ **Sprint 3 Track I Linux deploy DONE** (`7a86d2eb` runbook + Phase B-G executed via SSH bridge 2026-05-03 21:30+) — V049-V054 6 V### apply / cargo --release build / restart_all --rebuild / 5 e2e smoke 核心 3 條 PASS / Track H schema verify 全綠 | DONE |
| **P1-INFRA-3m** | ✅ **Sprint 4 final closure DONE (commit `0ad79f67`)** — operator override accept conditional skip 14d observation；7 closure item 4 ✅ + 3 ⏭ override skip = REF-20 P6 CLOSED；24/25 V3 §12 acceptance binding GREEN | DONE |
| **P1-INFRA-3n** | ✅ **Sprint A closed-with-real-evidence (2026-05-05)** — Gap Closure Plan V1 R1+R2+R3 全 IMPL + 6-layer blocker chain fix + final smoke E2E PASS | DONE |
| **P1-INFRA-3o** | ✅ **Sprint B closed (2026-05-05)** — R4 UI Enablement + R5 real strategy/risk replay path landed | DONE |
| **P1-INFRA-3p** | ✅ **Sprint C closed (2026-05-05)** — V055 R6-T0' Linux PG fix + fee/slippage byte-equal replay fill path + execution_confidence calibration labels + calibrated_replay MLDE/Dream advisory integration + A6/A7/A10 acceptance closed | DONE |
| **P1-INFRA-3q** | ✅ **Sprint D closed (2026-05-05)** — R8 maintenance/retention/observation + R9 final sign-off; V056 retention policy and healthcheck sentinels [46]-[50] landed | DONE |

### P2-CODEX-3 (TODO line 186)

| **P2-CODEX-3** | hygiene fix（AUDIT-2026-05-02-P3-1/2/3）→ 已併入 P2-AUDIT-1/5 + 本次 archive sweep | DONE |

---

## OBSOLETED-BY-GOV-CHANGE-2026-05-05 (governance LOC limit 1500→2000)

| ID | 描述 | 原因 |
|----|------|------|
| **P2-FOLLOW-UP-3** | ~~Wave 6 `mlde_demo_applier.py` 1542 LOC > 1500 hard cap §九 violation~~ | 1542 < 2000，governance change 後不再 violation |
| **P2-WAVE-4-W6-REFACTOR** | ~~replay_routes.py 1500 LOC governance；Wave 4 commit msg ack 但 TODO.md 0 hit~~ | 1500→2000 + Sprint B B1 R0-T0 已釋放至 1146 LOC |
| **P2-WAVE-6-MLDE-DEMO-APPLIER-SPLIT** | ~~mlde_demo_applier.py 1542 LOC > 1500 hard cap split refactor~~ | 1542 < 2000 不再硬上限 violation |
| **P2-R3-FOLLOW-UP-7** | ~~`app/replay_routes.py` 1499 LOC（1 LOC margin to 1500 cap）~~ | governance 1500→2000 + Sprint B B1 R0-T0 1499→1146 |
| **P2-STRUCT-2** | ~~LG5-CONSUMER-SPLIT P3（`governance_hub_live_candidate_review.py` 1496/1500 LOC near cap）~~ | governance 1500→2000，1496 < 2000 不再 near cap |

---

## STALE — 排程提醒已過/條目過時

| 來源 | 條目 | 原因 |
|---|---|---|
| §四 排程提醒 line 309 | "REF-20 Wave 1 派發 checkpoint（立刻）" | Wave 1-9 全 closed，checkpoint 不再 active |

---

## R4-B 後續 follow-up（未 archive，留作下次 audit 參考）

R4-B audit 還識別出 5 STALE 條目建議重組（P1-EDGE-3 + P1-TIME ~05-16 funding_arb 重複）+ 8 MISSING 條目建議新增（P0-LG-LEASE-CANARY / P0-WAVE-7-DEPLOY-GATE / P1-FUNDING-ARB-REMOVAL-PATH / P1-REF20-OPERATOR-OUTSTANDING / P2-AGENT-TODO-MULTI-AGENT-REWORK / P2-CONTEXT-MD-MAINTENANCE / P3-CLAUDE-MD-§3-DRIFT-WATCH / P2-DOC-INDEX-SYNC）+ 5 DUPLICATE 簇待 merge。本次 archive sweep 範圍僅限「verbatim 移除已 done 的條目」，未做新增/重組；留 operator 下次 TODO 維護週期決定。
