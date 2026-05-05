# OpenClaw TODO — 工作清單（v7 · P0/P1/P2 三層 · 2026-05-05）

**版本**：v8（2026-05-05 REF-20 Sprint A + B closed — 累計 12 commit chain：A 8 commit `c1ab7ea9 → ... → 2531c011` + B 4 commit `2a69addb (B1 R4+R0-T0) → c679a8b4 (R5-T1+T2) → a2f819c5 (R5-T3) → 4ffb24c4 (R5-T4+T5+T6+T7)`；plan §6.R3 acceptance 4 表 row > 0 + §6.R4 UI enabled + §6.R5 A4 + A5 hermetic acceptance PASS；Sprint C-D pending）
**HEAD**: `2531c011`（Mac/Linux/origin 同步）· **Engine deployed**: `dbcf845b`（Sprint 3 Track H 仍 active；R3 round 1-9 為 Python only，無 Rust rebuild）
**測試基準**：Python pytest **3431 PASS** / 1 fail (pre-existing E4-P0-1) / 10 skip · Rust cargo workspace **3132 PASS** / 2 fail (pre-existing E4-P0-2) / 3 ignored · Sprint 3 Track H Python sibling 44/44 PASS · cumulative Sprint 1+2+3 chain 三端同步
**21d demo 時鐘**：2026-04-16 22:16 → 解鎖 **2026-05-07**

**歸檔索引**：
- 4-day codex audit closure 詳細 + Wave 4 Pre-Stage 5 軸線完整表 + Top 10 派發優先序 → `docs/archive/2026-05-02--TODO-pre-trim-snapshot.md`
- 62-finding Batch A-F：`docs/archive/2026-04-29--62finding-batch-A-to-F.md`
- STRKUSDT P0 Wave：`docs/archive/2026-04-29--strkusdt-p0-wave.md`
- Wave A-H 完整敘述：`docs/archive/2026-04-29--wave-A-to-H-narrative.md`
- Wave 1-3 完成表格 + Backlog 完成項：`docs/archive/2026-05-01--completed_waves_1_2_3_and_backlog.md`

---

## 一、真實狀態（2026-05-02 panorama 整合）

5 策略 7d gross 真實 net **-6.98 USDT**（demo）+ **-0.81 USDT**（live_demo）— grid 唯一 +5.77，其它 4 個合計 -11.96。LG-5 W3 FUP-1 sibling CC commit `463890d` 已 land，待下次 deploy 後 reviewer 啟動。**Decision Lease retrofit AMD-2026-05-02-01 Track H 業務代碼 + V054 schema 已 land**（commit `dbcf845b`）+ **Track I Linux deploy Phase B-G executed**（feature flag `OPENCLAW_LEASE_ROUTER_GATE_ENABLED=0` default OFF → production runtime 0 行為改動）。**REF-20 Sprint A + B closed (2026-05-05)**（累計 12 commit chain — A 8 commit + B 4 commit：B1 `2a69addb` R4 UI enable + R0-T0 LOC release / B2 `c679a8b4` R5-T1+T2 Rust adapter foundation / `a2f819c5` R5-T3 IsolatedPipeline wire / `4ffb24c4` R5-T4+T5+T6+T7 config blob path + acceptance；plan §6.R3 4 表 row > 0 + §6.R4 UI gated + §6.R5 A4/A5 hermetic acceptance PASS；config blob 完整路徑 register → V049 → /run → disk manifest → Rust runner → adapter override；Sprint C-D pending — R6 fee calibration + R7 MLDE-Dream / R8 maintenance + R9 final sign-off）。

**最早 Live target**：~05-23 樂觀 / ~05-30 中位 / ~06-15 悲觀。**panorama 評估悲觀更可能**（5 LG IMPL + Decision Lease retrofit + 18 blocker）。

---

## 二、P0/P1/P2 三層工作流程（5 大組 × 36 條目）

### 🔴 P0 — Live Blocker（必須在真 Live 前完成或正式拒收）

#### P0-EDGE — 策略 edge 層

| ID | 任務 | 等什麼 | 觸發 |
|----|------|--------|------|
| **P0-EDGE-1** | Edge net positive 驗證（5 策略 7d gross 由 -6.98 USDT 翻正）| 21d demo 解鎖 + EDGE-P1b 累積 | 被動觀察至 ~05-10 |
| **P0-EDGE-2** | P0-3 edge decision 會（A 翻正 / B 仍負 / C 部分改善）| EDGE-P1b ≥200 rows + counterfactual_exit_replay 結果 | ~05-15 |

#### P0-LG — Live Gate 實裝（依 P0-EDGE 結果啟動）

| ID | 任務 | 狀態 | ETA |
|----|------|------|-----|
| **P0-LG-1** | LG-1 21d demo 解鎖（passive）| 進行中 | 2026-05-07 |
| **P0-LG-2** | LG-2 H0 blocking IMPL（RFC `5ce777b` → 0% IMPL；過去 24h log 0 H0 blocks，metric collector 未建）| RFC only | P0-EDGE-2 後，1 sprint |
| **P0-LG-3** | LG-3 provider pricing binding IMPL（AccountManager.refresh_fee_rates 在但無 binding contract / staleness HC / startup assertion）| RFC only | 0.5-1 sprint |
| **P0-LG-4** | LG-4 supervised live IMPL（RFC `ec8f0f4` → state machine 0 行）| RFC only | 1.5-2 sprint |
| **P0-LG-5** | LG-5 W3 FUP-1 reviewer 0 emit fix（commit `463890d` 已 land，待 deploy 後驗證 24h `governance_audit_log` 累積）| sibling CC done | 下次 deploy |

#### P0-GOV — 治理 / 可審計層紅線

| ID | 任務 | 狀態 |
|----|------|------|
| **P0-GOV-1** ⚠️ | **Decision Lease 路徑 A retrofit**（Rust `acquire_lease()` facade + router gate + Python IPC 轉呼 + bundled audit writer fix）| 2026-05-02 三方 review 完成 ✅ AMD-2026-05-02-01；retrofit pending：~2.5-3 E1 task，派發 2026-05-15 P0-EDGE-2 後並行 LG-2/3，必在 LG-4 IMPL 前完。E4 驗收 AC-1~5（SM-02 transition coverage / 6-element auth fill rate / lease_id flow / weekly audit / agent schema row count）。詳 `docs/governance_dev/amendments/2026-05-02--SM-02_R04_retrofit_path_a.md` |
| **P0-GOV-2** | agent schema all-time 0 rows（`agent.messages` / `state_changes` / `ai_invocations`）— DOC-01 #8/#15 violation；MessageBus DB sink 接線 | **bundled with P0-GOV-1**（PA push back 採納；retrofit 同 sprint，AC-5 驗收條件）|
| **P0-GOV-3** | SOP「sign-off 必檢 `git status --porcelain` clean」gate（LG-5 漏洞同類防線）| CLAUDE.md §七 已加，需新 PR review template |
| **P0-GOV-4** | Live credential rotation 7 步（PG password + Grafana admin + 6 commit history 清理）| 2 day work，Live 前必 |

#### P0-OPS — 運維紅線

| ID | 任務 | 狀態 |
|----|------|------|
| **P0-OPS-1** | HTTPS deploy + Cookie secure G-4（PRE-LIVE-2 source not landed，3d 工時）| 0% IMPL |
| **P0-OPS-2** | KYC / 地理禁區 / Bybit ToS 合規確認（0 governance entry）| Operator 法律確認 |
| **P0-OPS-3** | Disaster runbook + Live first-day SOP（dust clear SOP only，缺完整 first-day playbook）| 1d work |
| **P0-PROCESS-1** ⚠️ | E4 sign-off SOP 必加 Linux pytest 步驟（不只 Mac）— Sprint A R3 round 3 hotfix 揭 Mac Python 3.10 / Linux Python 3.12 FastAPI lazy ForwardRef 解析行為差異，Mac PASS ≠ Linux PASS。Sprint A R1+R2+R3 全部 hermetic test 在 Linux 真實 fail（100% 422 missing body）但 E4 只跑 Mac → false-positive sign-off。修法：E4 SOP 加 PM commit pre-check 階段「Linux pytest 必綠（透過 SSH bridge `ssh trade-core "cd ~/BybitOpenClaw/srv/... && .venv/bin/pytest <files>"`）」步驟；允許 Linux 已知 pre-existing fail 集 carry over，但需明文文檔化。詳：`srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-04--ref20_sprint_a_r3_impl.md` §12 | @PM @E4 |

#### P0-DATA — 資料正確性紅線（跨 wave prerequisite）

| ID | 任務 | 阻塞下游 | 狀態 |
|----|------|---------|------|
| **P0-DATA-INDICATOR-SWEEP** | ✅ **DONE 2026-05-03** · 5 策略 indicator leak-free sweep verdict = **5/5 PASS**（QC quant 主審 + E3 adversarial 副審 + PM 補位驗證 `compute_indicators` body @ `on_tick_helpers.rs:453` 證據鏈完整：`get_ohlcv → buffer().ohlcv_arrays(n)` 只從 closed-bar buffer，不含 currently-forming bar）。**真因排查**：5 策略 net -6.98 USDT 不是 indicator leak，最便宜解釋為 strategy logic / cost / maker fill 三者（[33] maker 36.6% / [40] slippage -92bps）。**P0-EDGE-1/2 可繼續使用現有 edge 估計，無需重算**。**REF-20 V3 §3 G6 + §7 P2 precondition 解封**。Verdict 報告：`docs/audits/2026-05-03--P0-DATA-INDICATOR-SWEEP_verdict.md`。Follow-up（升 P2）：L-01 streaming integration test（綁 REF-20 P2b fixture）+ L-02 feature_version 硬編碼 v1.0 fix。 | （已解除）| ✅ DONE |

---

### 🟠 P1 — Important（Live 質量 / 在 LG IMPL 前後完成）

#### P1-FAKE — Fake-live wiring 修

| ID | 任務 | 來源 |
|----|------|------|
| **P1-FAKE-1** | ExecutorAgent `shadow_mode_provider` `lambda: True` fail-close default fix（G3-03 Phase B 名為 wired 實際仍 shadow）| PA panorama |
| **P1-FAKE-2** | H0_GATE singleton 0 production caller wire（DOC-02 spec 死於 wiring，LG-2 IMPL 前提）| FA-H2 |
| **P1-FAKE-3** | HStateCache + CostEdgeAdvisor 兩 late-inject slot 啟用（env-gated `OPENCLAW_H_STATE_GATEWAY=1` / `OPENCLAW_COST_EDGE_ADVISOR_*` 未設）| PA panorama |

#### P1-EDGE — Edge 層支撐

| ID | 任務 | 觸發 |
|----|------|------|
| **P1-EDGE-1** | ma_crossover ATR-SNR 後仍 net negative 重評（demo -5.09 / live_demo -1.60）| G2-02 ~05-03 後 |
| **P1-EDGE-2** | bb_breakout live_demo 14d 0 fires diagnosis（FIX-26-DEADLOCK-1 是否漏覆其它策略）| 即時可派 |
| **P1-EDGE-3** | funding_arb V2 棄策略 14d audit | 2026-05-16 cron |
| **P1-EDGE-4** | BUSDT 110017 reject loop 治本（24h slippage live_demo -92 bps；event_consumer/dispatch 加 net pos pre-check）| ASAP |

#### P1-DATA — 數據完整性

| ID | 任務 | 狀態 |
|----|------|------|
| **P1-DATA-1** | MLDE training row 84.6% `attribution_chain_ok=false`（MIT-S2-1） | sibling CC LG5-W3-FUP-2 in flight |
| **P1-DATA-2** | `learning.exit_features.est_net_bps` 100% NULL（FA-H6） | edge_estimator P1-7 C labels 47/200 累積中 + writer 路徑修 |
| **P1-DATA-3** | maker fill rate live_demo 7d 36.6% < 40% PASS 線（healthcheck 假綠） | 重設 baseline 或修 strategist post-only |
| **P1-DATA-4** | LG5-W3-FUP-2 attribution_chain_ok writer gap diagnosis | sibling CC in flight |

#### P1-TIME — 時間驅動里程碑

| 日期 | 任務 | 觸發腳本 / 條件 |
|------|------|----------------|
| **~05-03** | G2-02 ma_crossover counterfactual replay（1w post-G7-09 demo 數據累積）| `ma_crossover_counterfactual_replay.py`；若結論支持 → 派 G2-03-FUP-CALLER-WIRE P1 |
| **~05-07/08** | G2-01 PostOnly 1-2w 驗收（[33] ≥60% fee_drop）| 自動觀察；若 <60% → P2-COND-1 G2-04 grid disable 決策會 |
| **~05-09** | 3C deploy 7d audit（5 metric vs prior 7d baseline）| `bash helper_scripts/db/audit/2026-05-09_3c_7d_audit.sh` |
| **~05-10** | EDGE-P1b 累積 ≥200 rows（grid 1030 / ma 493 READY）| 跑 `exit_threshold_calibrator.py`；manual approve flow |
| **~05-15** | P0-3 邊評決策會 | PM+FA+PA+QC：edge positive/mixed/still negative → LG-2/3/4/5 or dual-track |
| **~05-16** | funding_arb V2 1B 樣本累積 14 天彙總 | `bash helper_scripts/db/audit/2026-05-16_funding_arb_14d_audit.sh`；n≥30 且 net bps 顯著負 → 2A 觸發棄策略 |
| **~05-22+** | Wave 4 實裝 | 依 P0-3 決策路徑啟動 P0-LG-2/3/4 + P0-GOV-1 retrofit |
| **~05-30±7d** | Live target | PM W2 sign-off 目標（中位 estimate） |

#### P1-INFRA — Pre-Live 基礎設施

| ID | 任務 | 觸發 |
|----|------|------|
| **P1-INFRA-1** | Slack alert channel go/no-go（pre-live ~2 週評估） | ~2026-05-15 |
| **P1-INFRA-2** | PRE-LIVE-4 災難恢復演練（drawdown auto-revoke / liquidation buffer / auth expire 三 scenario）| LG-2 RFC 後 |
| **P1-INFRA-3** | ✅ **REF-20 Sprint A + B closed (2026-05-05)** — 12 commit chain (A: `c1ab7ea9 → ... → 2531c011` 8 commit / B: `2a69addb (B1 R4+R0-T0) → c679a8b4 (R5-T1+T2) → a2f819c5 (R5-T3) → 4ffb24c4 (R5-T4+T5+T6+T7)` 4 commit) 三端同步。Plan §6.R3 4 表 row > 0 + §6.R4 UI gated + §6.R5 A4/A5 hermetic acceptance PASS：6 hermetic Python (3 A4 + 3 A5) + 2 Rust e2e proof (proof_7 wiring + proof_8 risk delta)。Config blob 完整路徑：register endpoint → V049 manifest_jsonb → /run handler → disk manifest_fixture.json → Rust replay_runner → adapter override。**Sprint C-D pending**：C=R6 (fee calibration + execution_confidence label none/limited/calibrated) + R7 (MLDE/Dream advisory verify_replay_evidence_and_insert) / D=R8 (maintenance/cron) + R9 (reality-calibrated final sign-off)。**Push-back accepted**：proof_7 真實 fixture fills divergence 延 Sprint C R6（synthetic_btcusdt.json 10-event monotone-up fixture quality limit, 不是 architecture limit；wiring round-trip 已證）。`replay.simulated_fills.evidence_source_tier='synthetic_replay'` 仍不可作 ML training data。Plan：`docs/execution_plan/2026-05-04--ref20_gap_closure_reality_backtest_plan_v1.md`。 | Sprint C 啟動 |
| **P1-INFRA-3a** | ⚠️ **Wave 1 closed (atomic 5 commits) + Sprint 1 cold audit fix-up** — P0 docs amendment + scaffold 設計（V3/Workplan V1/UX subdoc 三 baseline land） | IMPL accept-with-caveat |
| **P1-INFRA-3b** | ⚠️ **Wave 2 closed (commits `1851714` + `b1f6b8a`)** — P1 frontend IA + P2a S1/S2 signing key + manifest signer | IMPL accept-with-caveat |
| **P1-INFRA-3c** | ⚠️ **Wave 3-4 closed (commits `5a618ff` + `4b48b6d`)** — P2a S3-S6 + P2b S7-S10 runner；**Sprint 1 修 spawn argv broken + manifest 自洽循環 + 5 critical security 洞**；W3 mac_policy_guard.rs 中文全形括號 doctest fail（self-introduced，commit msg 偽稱 sibling pre-existing → P2-FOLLOW-UP-2 修）；W4 single commit 26 file 7360 ins violated §八 工作鏈（已 Sprint 2 retroactive review 補） | IMPL accept-with-caveat |
| **P1-INFRA-3d** | ⚠️ **Wave 5 closed (commit `457a458`)** — P3a/P3b/RGM 13 task NumPyro 2320 LOC；mini test 200/400 chain（production 1000/2000 從未 CI 跑 → P2-WAVE-5-NTHRESHOLD-SWEEP 修）；NumPyro Mac scipy 0 cross-OS sibling test → P2-FOLLOW-UP-4 | IMPL accept-with-caveat |
| **P1-INFRA-3e** | ⚠️ **Wave 6 closed (commit `eb5f106`)** — P4 advisory chain 8 task；W6 引入 deterministic flaky test（FastAPI dependency_overrides 跨 test pollution → P2-FOLLOW-UP-1 修）；mlde_demo_applier.py 1542 LOC 違反 §九 requirement (3) → P2-WAVE-6-MLDE-DEMO-APPLIER-SPLIT；V043 0 production caller / 0 healthcheck → P2-WAVE-6-V043-HEALTHCHECK | IMPL accept-with-caveat |
| **P1-INFRA-3f** | ⏸ **Wave 7 DEFERRED + IMPL-accept-deploy-blocked** — P5 4 task IMPL-in-tree (commit `c887e4e` operator override) 但 hard prereq LG-2/3/4 frontend merged + 7d stable 仍 NOT GREEN；**正式 amendment AMD-2026-05-03-01 (commit `5184990`)** 規範 IMPL/Deploy 2-stage gate + 4 AC + 失敗回退；defer note `2026-05-03--ref20_wave7_defer_note.md` 自證 prereq violation；deploy gate retained pending healthcheck `[46]` | LG-2/3/4 stable |
| **P1-INFRA-3g** | ⚠️ **Wave 8 closed (commit `8429af1`)** — P6 7 task typed-confirm + V044 idempotency；handoff cooldown race（READ COMMITTED + 0 row-level lock → 由 Sprint 1 Track C cmdline 校驗 + V053 LOCK TABLE 部分緩解）；handoff flow 0 healthcheck → P2-WAVE-8-HANDOFF-HEALTHCHECK；**P6 production exposure 仍 require P0-GOV-1 Decision Lease retrofit AMD-2026-05-02-01 deploy**（Sprint 2 Track E PA design 已完，feature flag 灰度路徑） | Decision Lease retrofit deploy |
| **P1-INFRA-3h** | ⚠️ **Wave 9 closed (commit `1f5d019`)** — 14d gradient + V047/V048 KPI 採集 cron；Mac mock mode 跑過 Linux 真實 PG 0 跑（QA 確認）；V047/V048 plain table 1y retention 0 設 → P2-WAVE-9-V047-V048-RETENTION | Sprint 3 deploy after Linux runtime |
| **P1-INFRA-3i** | ✅ **Sprint 1 cold audit fix-up DONE (commit `edf33c0`)** — 4 並行 E1（A spawn argv / B Rust manifest verify / C Python 3 安全洞 / D V049-V053 schema 補造）；E2 round 1+2 + E4 regression 全 PASS；3387 PASS / 1 fail (pre-existing) / 10 skip；3084 cargo workspace PASS / 2 fail (pre-existing) / 3 ignored | DONE |
| **P1-INFRA-3j** | ✅ **Sprint 2 retroactive review DONE (commit `aa9343c`)** — PA Track E Decision Lease retrofit 4-task DAG design + E2 F1 retroactive Wave 3-9 master review (10 LOW + 7 P2 提案) + E4 F2 retroactive cumulative (4 forgery flag + 5 mock retroactive flag + 3 P2 提案) | DONE |
| **P1-INFRA-3k** | ✅ **Sprint 3 Track H DONE (commit `dbcf845b`)** — Decision Lease retrofit AMD-2026-05-02-01 Path A 業務代碼 + V054 audit writer + 4 並行 sub-task report（E-1 Rust facade / E-2 router gate / E-3 Python IPC bridge / E-4 V054 audit writer）+ E2 round 1+2 + E4 final regression；feature flag `OPENCLAW_LEASE_ROUTER_GATE_ENABLED=0` default OFF 灰度路徑保留；amendment §5.4 flip flag canary 24h 待 ~2026-05-15 P0-EDGE-2 後 operator action | DONE |
| **P1-INFRA-3l** | ✅ **Sprint 3 Track I Linux deploy DONE** (`7a86d2eb` runbook + Phase B-G executed via SSH bridge 2026-05-03 21:30+) — Phase A skip (E4 final regression 已跑) / Phase B V049-V054 6 V### apply (TimescaleDB hypertable + 21-value enum + paired CHECK + FK redirect 全綠) / Phase C cargo --release build (engine 28.82s + replay_runner 15.35s, nm audit 406 symbol 0 forbidden) / Phase D skip (feature flag OFF + 回測模塊不需 production cron) / Phase E restart_all --rebuild (Engine PID 4122084 + API PID 4122156 / paper+demo+live alive / snapshot age 8.1s) / Phase F 5 e2e smoke 核心 3 條 PASS / Phase G Track H schema verify 全綠 | DONE |
| **P1-INFRA-3m** | ✅ **Sprint 4 final closure DONE (commit `0ad79f67`)** — operator override accept conditional skip 14d observation：「直接跑掉 A-H，後續有問題再修」（理由：REF-20 是 Paper Replay Lab 回測模塊，feature flag default OFF + 0 trading.* mutation + 0 live trading 觸發）；7 closure item 4 ✅ + 3 ⏭ override skip = REF-20 P6 CLOSED；24/25 V3 §12 acceptance binding GREEN（#21 ⏸ DEFERRED Wave 7 P5）；P2-FOLLOW-UP-5 closure doc 「3500+→3387」訂正同 commit 處理 | DONE |
| **P1-INFRA-3n** | ✅ **Sprint A closed-with-real-evidence (2026-05-05)** — Gap Closure Plan V1 R1+R2+R3 全 IMPL + 6-layer blocker chain fix + final smoke E2E PASS。**R1 Runtime Usability** (`c1ab7ea9`)：binary path fallback chain + `/api/v1/replay/health` route + audit script + restart_all env export + 13 unit tests。**R2 Manifest Registry** (`353db3fe`)：970 LOC `experiment_registry.py` + `/experiments/register` endpoint + `/run` FK guard SELECT FOR SHARE + `/manifest/verify` secrets file fallback + 29 R2 tests + canonical_bytes contract docstring + CLAUDE.md §九 simulated_fills non-training surface note。**R3 First Real E2E** (`66b650ea` + 6 hotfix rounds)：simulated_fills_writer + run_finalize_route + 6 layer fix (Python 3.12 422 + ENGINE_BINARY_SHA + real HMAC sign + stderr capture + signing key provisioning + exit=0 sentinel)。**QA round 6 final smoke E2E PASS (2026-05-05 02:05 UTC)**：4 表 row > 0 真實達成。**A1+A2+A3 acceptance 全綠**。Plan: `docs/execution_plan/2026-05-04--ref20_gap_closure_reality_backtest_plan_v1.md` | DONE |
| **P1-INFRA-3o** | ⏸ **Sprint B pending (Sprint A 後啟)** — R4 UI Enablement + R5 Real Decision/Risk Replay Path。**R4 涵蓋 P1-1 + G7**：tab-paper.html `subtab-btn-replay` 從 `data-disabled="true"` 改 backend-readiness gated；execution confidence / data tier / fee model / calibration status surface；empty/running/failed/completed/degraded states。**R5 涵蓋 P0-1 (synthetic close-price walker)**：inventory live strategy/risk call graph + extract pure components + `ReplayStrategyAdapter` + `ReplayRiskAdapter` + 證明 strategy/risk parameter delta 真改變 replay decision。**Sprint B acceptance**：A4 actual strategy path + A5 actual risk path + A8 UI usable | Sprint A R1+R2+R3 acceptance |
| **P1-INFRA-3p** | ⏸ **Sprint C pending (Sprint B 後啟)** — R6 Fee/Execution Calibration + R7 MLDE/Dream Advisory Integration。**R6 涵蓋 G6 fee 部分**：maker/taker fee model + spread/slippage model + calibration against demo/live_demo fills + run-level confidence label `none`/`limited`/`calibrated`。**R7**：DreamEngine generate replay candidate + MLDE rank/veto + `learning.verify_replay_evidence_and_insert()` route。**Sprint C acceptance**：A6 fee-aware PnL + A7 confidence honesty + A10 ML/Dream advisory boundary | Sprint B R4+R5 acceptance |
| **P1-INFRA-3q** | ⏸ **Sprint D pending (Sprint C 後啟)** — R8 Maintenance/Retention/Observation + R9 Reality-Calibrated Usability Sign-off。**R8 涵蓋 G5**：install replay cron jobs (key rotation / archive cleanup / artifact prune / Wave9 no-live-mutation watch / business KPI collector / audit incident scan) 或 document manual + healthcheck probes (runner binary path / manifest registry rows / artifact retention / failed run rate / stale running rows) + artifact TTL/quota。**R9 涵蓋 G6 final**：≥5 successful runs ≥2 strategies + ≥1 parameter-change replay + ≥1 fee-aware report + 0 live mutation + UI usable without manual DB insert + MLDE/Dream advisory non-commanding + confidence labels match calibration。**Sprint D acceptance = Wave R9 final sign-off → REF-20 Reality-Calibrated Fast Replay usable for demo research** | Sprint C R6+R7 acceptance |

---

### 🟡 P2 — Maintenance / Backlog（條件觸發或下個維護週期）

#### P2-AUDIT — 4-day codex audit Step 2 follow-up（部分 in flight）

| ID | 描述 | Owner |
|----|------|-------|
| **P2-AUDIT-1** | PA-DRY-1（`is_legacy_close_tag` `commands.rs:203/576` 重複 4 行）| @E1 |
| **P2-AUDIT-2** | PA-SCRIPT-PROC-1（4 script Linux-only `/proc/<pid>/cwd` 違跨平台）| @E1 |
| **P2-AUDIT-3** | PA-TEST-WATCHER-SLOT-1（無 e2e 測試斷言 watcher respawn 寫 / teardown 清 `live_cmd_slot`）| @E1+@E4 |
| **P2-AUDIT-4** | MIT-S2-2/3/4/6（demo→live promotion contract / regret_summary ceiling / V031 view scaling / opp_tracker noise）| @E1 |
| **P2-AUDIT-5** | QC-S2-01/02/04/09（scanner posterior LCB hardcoded / promotion distribution shift / TOML triple-env 違反 / PRE-LIVE-3 thresholds RFC 缺）| @QC + @PA |
| **P2-AUDIT-6** | E3-S2-P2-1/P2-2 exception leak；E3-S2-P3-1 file mode 0600 | @E1 |
| **P2-AUDIT-7** | V044 P6-S15 enum DROP+ADD 缺 LOCK TABLE ACCESS EXCLUSIVE；補回同 V053 race-free retrofit pattern（BEGIN+LOCK TABLE ... ACCESS EXCLUSIVE+COMMIT 包裹 + probe-short-circuit-before-lock）— REF-20 Sprint 1 Track C V053 落地時 E2/E3 同 incident 反例覆蹤 | @E1 |
| **P2-FOLLOW-UP-1** | `test_case2_pg_kill_simulation_returns_200_degraded` deterministic flaky（FastAPI `app.dependency_overrides[current_actor]` 跨 test pollution；隔離跑 PASS）— Wave 6 commit `eb5f106` 引入但 closure doc 偽稱 pre-existing。修法：pytest fixture autouse 重置 `app.dependency_overrides` + 包 router instance fixture | @E1+@E4 |
| **P2-FOLLOW-UP-2** | `mac_policy_guard.rs` 2 doctest fail（中文全形括號 `（）` 觸發 Rust doctest tokenizer error）— Wave 3 commit `5a618ff` 自引入但聲稱 sibling pre-existing。修法：把 doctest 中文範例包進 ` ```text ``` ` markdown code fence 或改半形括號 | @E1 |
| **P2-FOLLOW-UP-3** | Wave 6 `mlde_demo_applier.py` 1542 LOC > 1500 hard cap §九 violation（pre-existing 1541 baseline 已破 1500 → §九 exception clause 條件 (1) 適用，但 W6 commit msg 0 doc accept / 0 P2 ticket → 條件 (2) + (3) 違反）— Sprint 2 E4 F2 retroactive 揭。修法：W6 commit accept doc retrofit + 開 split P2 ticket | @E1+@PM |
| **P2-FOLLOW-UP-4** | W5 NumPyro Mac scipy fallback 自宣「1:1 alignment」0 cross-OS sibling test。修法：加 production scale (n_warmup=1000 / n_samples=2000) Mac aarch64 vs Linux x86_64 同 seed 一致性 sibling test ledger | @E1+@MIT |
| **P2-FOLLOW-UP-5** | REF-20 final closure doc `2026-05-03--ref20_final_closure_and_deploy_guidance.md` line 99 自宣「Expected: ~3500+ Python pytest PASS (Wave 1-9 cumulative)」是虛構數字（cold reality 3387 PASS，差 113-126）。修法：訂正成「Sprint 1 後 3387 PASS / 1 fail (pre-existing) / 10 skip」+ Wave commit message 數字一致性審查 | @PM |
| **P2-WAVE-3-DOCTEST-FIX** | mac_policy_guard.rs doctest fail（與 P2-FOLLOW-UP-2 重疊，merge 處理）；E5 follow-up 0 ticket | @E1 |
| **P2-WAVE-4-W6-REFACTOR** | replay_routes.py 1500 LOC governance；Wave 4 commit msg ack 但 TODO.md 0 hit（與 Sprint 1 P2-AUDIT-7 同漂移模式，已 Sprint 1 Track C extract 修到 1494 LOC，但仍待補 W4 commit msg accept doc retrofit） | @E1 |
| **P2-WAVE-5-NTHRESHOLD-SWEEP** | shrinkage_router N_THRESHOLD 30/50 boundary sweep test 缺 + production chain 1000/2000 在 CI 0 跑（Sprint 2 E2 F1 LOW + E4 F2 mock retroactive flag）| @E1+@MIT |
| **P2-WAVE-6-MLDE-DEMO-APPLIER-SPLIT** | mlde_demo_applier.py 1542 LOC > 1500 hard cap split refactor（與 P2-FOLLOW-UP-3 重疊，merge 處理） | @E1+@E5 |
| **P2-WAVE-6-V043-HEALTHCHECK** | V043 mlde_replay_veto_log 0 healthcheck pairing（passive_wait_healthcheck.py 加 `check_47_v043_advisory_writer()`）| @E1 |
| **P2-WAVE-8-HANDOFF-HEALTHCHECK** | handoff request flow 0 healthcheck（cooldown rejected rate / V044 UNIQUE collision rate / pg_unavailable degraded rate）— Sprint 2 E2 F1 LOW；passive_wait_healthcheck.py 加 `check_48_handoff_health()` | @E1 |
| **P2-WAVE-9-V047-V048-RETENTION** | V047 / V048 plain table 1y retention 0 設（MIT cold audit + Sprint 2 E2 F1 LOW）— hypertable 升級 OR retention drop policy | @E1+@MIT |
| **P2-LEASE-VEC-CLEANUP** | `DecisionLeaseSm.objects` Vec 在 lease 終態（Consumed/Revoked）後不 swap_remove，pre-existing 設計 leak ~200 bytes/trade（1yr × 1000 trade/day = 73MB Vec heap leak）— REF-20 Sprint 3 Track H E-1 retrofit push back #3 揭。修法：terminal state 後 `swap_remove` + 同步更新 `lease_id_to_idx` HashMap reverse mapping；加 e2e leak guard test | @E1 |
| **P2-INTENT-PROCESSOR-TESTS-SPLIT** | `rust/openclaw_engine/src/intent_processor/tests.rs` 2910 LOC > 1500 hard cap（pre-existing 2375 已超，Sprint 3 Track H E-1+E-2 retrofit +535）— §九 exception clause condition (1) 適用，**condition (2) 即此 ticket** + **condition (3) PM Sign-off 明文 declare**：兩 retrofit 撞 condition (3) baseline exception accept 理由 = (a) Decision Lease retrofit 是 P0-GOV-1 critical path / (b) 28 fixture 重寫 + 7 新 router_gate test 結構性必須在原檔同 module 內 / (c) 抽 helper module 風險高（既有 fixture 互相 import）。修法：split into `tests/lease_facade_tests.rs` + `tests/router_gate_tests.rs` + `tests/golden_extreme_tests.rs` 三 file；保留 `tests.rs` &lt;1500 LOC | @E1+@PM |
| **P3-V054-PYTEST-SIBLING** | V054 lease_transitions schema 0 Python pytest sibling — 與 V049-V052 Track D 模式不一致（test_v049_v050_v051_v052_track_d.py 24 case static-parse + cross-file invariants）。E4 Track H final regression 揭。修法：仿 test_v049_v050_v051_v052_track_d.py pattern 加 test_v054_lease_transitions.py（schema parse / Guard A/B/C / hypertable / event_type enum 7 values / FK to V035 governance_audit_log + REF-21 placeholder）| @E1 |
| **P3-PYDANTIC-V2-MIGRATE-REPLAY** | replay/ 全模組 `@validator` (Pydantic V1) → `@field_validator` (V2) migration；含 `experiment_registry.py` (5 validator) / `replay_models.py` (1 validator) / 其他 replay/ 內 Pydantic V1 用法。Trigger: Pydantic V2.13+ 持續輸出 `PydanticDeprecatedSince20` warning（pytest run 每次 6+ 條 noise，Sprint A R2 round 2 review L-2 揭）。當前不阻塞 R2/R3 功能；Pydantic V3.0 釋出時會 hard-break。修法：`@validator → @field_validator` + `pre=True → mode='before'` + 必要時 retrofit signature（`(cls, v, values)` → `(cls, v, info)` 用 `info.data`）；保所有 round 1+2 validator 行為（symbol/strategy alphanumeric+_ guard / data_tier enum / timeframe enum / strategy_config_sha256 / risk_config_sha256 / manifest_jsonb 256 KB / window order）+ `_no_reserved_prefix_keys` 順序在 `_size_cap` 前 unchanged。E1 round 3 Sprint A R2 round 2 review L-2 defer | @E1 |
| **P2-R3-FOLLOW-UP-1** | V### migration 加 `'replay_report'` value 至 V046 `chk_replay_report_artifacts_type` enum + 同步 `canary_writer.py::ALLOWED_ARTIFACT_TYPES` 擴。當前 R3 用 `'pnl_summary'`（最近義 in-allowlist），語意對齊但下游 R5 query `WHERE artifact_type='fill_log'` / `artifact_type='replay_report'` 找不到 fill data。修法：V0XX migration ALTER TABLE replay.report_artifacts DROP CONSTRAINT chk_replay_report_artifacts_type + ADD CONSTRAINT 加新 6-value enum；同步 ALLOWED_ARTIFACT_TYPES 加 `ARTIFACT_TYPE_REPLAY_REPORT`；修 `run_finalize_route.py` 用新 enum value（從 `'pnl_summary'` 改為 `'replay_report'`）。Sprint A R3 round 2 fix M-3 揭（E3 §6 MEDIUM-2） | @E1 |
| **P2-R3-FOLLOW-UP-3** | `run_finalize_route.py` exception 路徑 message field generic 化（exception detail 僅 `logger.warning`），符合 §九 SEC-04 `detail=str(e)` 政策；當前 503 path 含 `f"finalize failed: {type(exc).__name__}"` 可能 leak 內部 stack 結構（exception class name 是 internal API），message 應改 `"finalize failed (internal error logged)"` 同時保 logger.warning 完整 stack。Sprint A R3 round 2 fix L-1 揭（E3 §6 LOW-1） | @E1 |
| **P3-R3-FOLLOW-UP-4** | `verify_replay_runner_pid` 加 `psutil.Process.create_time()` 校驗防 PID-reuse cmdline 巧合 false positive；schema add: V045 column `subprocess_started_at_ms BIGINT`；spawn writer 在 `route_helpers.spawn_replay_runner` 寫；`verify_replay_runner_pid` 讀+比 `psutil.Process(pid).create_time() * 1000 == subprocess_started_at_ms ± tolerance`。當前 cmdline match 在 PID-reuse + cmdline 巧合下 false positive 卡 finalize（極罕見但非零）。Sprint A R3 round 2 fix L-2 揭（E3 §6 LOW-2） | @E1 |
| **P2-R3-FOLLOW-UP-5** | V046 `byte_size CHECK BETWEEN 0 AND 67108864`（64 MB）defense-in-depth；real bound 由 upstream `simulated_fills_writer.MAX_REPORT_BYTES = 16 MB` 防（parse 階段 reject oversized file）。但 V046 schema 層無此 CHECK，未來若 upstream cap 被誤調高（or attacker 繞 parse 直 INSERT）則 V046 row 可載入超大 byte_size。修法：V0XX migration `ALTER TABLE replay.report_artifacts ADD CONSTRAINT chk_replay_report_artifacts_byte_size CHECK (byte_size >= 0 AND byte_size <= 67108864)`。Sprint A R3 round 2 fix L-3 揭（E3 §6 LOW-3） | @E1 |
| **P2-R3-FOLLOW-UP-6** | `tests/test_replay_routes_auth.py` 3 case 在 Linux 真 PG 環境下 fail：用 `experiment_id="exp-2026-05-03-test"`（不是 valid UUID），fix 後路徑通暢但 PG `replay.experiments.experiment_id` UUID column 拒收 → `InvalidTextRepresentation` → 503 spawn_failed。Mac mock fixture 假 PASS（從未打 PG）。Sprint A R3 round 3 hotfix 揭（git stash 雙向驗證確認 pre-existing fixture bug，非 hotfix regression）。修法：fixture 改用 `uuid.uuid4().hex`（V049 schema-compliant UUID）+ test setup 先 INSERT V049 experiments row 滿足 FK；3 case 名 `test_authenticated_zero_active_run_post_run_accepts` / `test_authenticated_per_actor_cap_returns_409` / `test_authenticated_global_cap_returns_409` | @E1 |
| **P2-R3-FOLLOW-UP-7** | `app/replay_routes.py` 1499 LOC（1 LOC margin to 1500 cap）— Sprint A R3 round 3 hotfix +8 LOC 後 margin 過薄。下次任何 small docstring update 就會超 cap，違 §九 governance。修法：抽 hotfix 警告塊（line ~28-37 `CRITICAL — DO NOT add from __future__ import annotations` 雙語警示 + SPEC reference）到 `replay/MAINTAINER_NOTES.md` 外部檔；docstring 內留 1-line pointer `"# See replay/MAINTAINER_NOTES.md for PEP 563 ban rationale"` 回收 ~7 LOC margin | @E1 |

詳述 → `docs/archive/2026-05-02--TODO-pre-trim-snapshot.md` § Top P2 / P3 backlog

#### P2-CODEX — 4-day codex window 殘存

| ID | 描述 | Owner |
|----|------|-------|
| **P2-CODEX-1** | 12 個 worktree merge 無人審（含 `PA/memory.md` + `cost_edge_advisor/mod.rs` conflict 解法）| @PA spot-check |
| **P2-CODEX-2** | 單 commit 13.6k LOC governance（`b46660a`）— §七 加「單 commit 上限」規則 or 接受並 flag | operator 決定 |
| **P2-CODEX-3** | hygiene fix（AUDIT-2026-05-02-P3-1/2/3）→ 已併入 P2-AUDIT-1/5 + 本次 archive sweep | DONE |

#### P2-STRUCT — 結構債

| ID | 描述 | 觸發 |
|----|------|------|
| **P2-STRUCT-1** | `decision_outcomes` outcome_* 100% NULL（timeframe 字串 bug）+ engine_mode 100% 'paper'（INSERT 漏接線）| memory `decision_outcomes_not_dead` |
| **P2-STRUCT-2** | LG5-CONSUMER-SPLIT P3（`governance_hub_live_candidate_review.py` 1496/1500 LOC near cap）| 下一輪維護 |
| **P2-STRUCT-3** | LG5-W2-FUP-PA-RFC-§4（`authorization.json.scope.lease_scopes` 加 `LIVE_CANDIDATE_APPLY:*` 條目；當前 empty-fallback=True latent rug-pull）| 下個 batch |
| **P2-STRUCT-4** | LinUCB shadow compare deferred to Rust warm-start | 條件觸發 |
| **P2-STRUCT-5** | G3-09 Phase C deferred（PA RFC ready，operator 決定「等時間長一些」）| Phase B observation 累積 |
| **P2-STRUCT-6** | G3-08-FUP-* split P2/P4（Analyst / HSQ / MAF / SINGLETON-POLLUTION）| 下一輪維護 |
| **P2-STRUCT-7** | 殭屍代碼盤點：`governance_hub.py` 部分 deprecated / `paper_trading_engine.py` retired / `pipeline_bridge` retired / `linucb_shadow_compare` 保留 / `apply_ai_consultation` deprecated stub | 下個 audit cycle |
| **P2-STRUCT-8** | Mac/Linux 6 commit gap → 下次 deploy window 一次 rebuild | 下次 deploy |

#### P2-COND — 條件觸發 backlog（保留）

| ID | 觸發條件 | Tag |
|---|---|---|
| **G2-03-FUP-CALLER-WIRE** | wire step_6_risk_checks caller chain，真實啟用 SL/TP override | G2-02 ~05-03 後 |
| **G2-04** | Grid disable 決策會 | G2-01 若 fee_drop <60% |
| **G8-03** | 灰度驗收自動化（shadow metrics）| EDGE-P2 flip 後 |
| **EDGE-P2-flip** | combine layer shadow flip | EDGE-P1b + 7d ≥95% agree |
| **EDGE-P2-3 Phase 2+** | live endpoint / funding_arb PostOnly | EDGE-P1b ~05-10+ |
| **G2-03 binding** | ma_crossover SL/TP 真實啟用 | G2-02 結論 + G2-03-FUP-CALLER-WIRE |
| **G7-03-Phase-B-FUP-grid** | grid_trading HysteresisDetector 遷移 | parallel WIP merge 後 |
| **G7-01 wiring** | Kelly router callsites | G4 labels work |
| **G3-06 Phase B** | Layer 2 autonomous Rust integration | 條件待確認 |
| **STRATEGIST-AUTO-PROMOTE** | 自動晉升規則 | P2-01 穩定後 |
| **ORPHAN-ADOPT-1 Phase 2B** | Strategist `would_take` 終仲裁 | G-1 R-02 |
| **IP-DEDUP-1** | IntentProcessor 去抖 | P0-3 後 edge 仍負 + 高重發率 |
| **G-7 ClaudeTeacher 啟用** | consumer_loop.rs enabled | 21d demo + G-3 後 ~05-07+ |
| **G9-02-FUP-COOLDOWN** | WS force reconnect cooldown 評估 | DEFAULT-ON 後 1-2w passive |
| **G8-01-FUP-REGRET-DREAM-DEFERRED** | OpportunityTracker + DreamEngine rebuild | 長期未定 |
| **G2-FUP-FUNDING-ARB-PAPER-SYNC-LOW-1** | TW memory.md 補 commit msg 一致性 | 下次 TW 接手 |
| **T6-FUP-PA-MEMORY-INDEX-SYNC** | PA Track 3 dust audit memory.md 條目補錄 | 下次 PA 接手 |
| **G5-09-FUP-TYPO** | commit `a5b6f17` commit msg test count typo | 下次 commit msg edit cycle |
| **TIER4-MIT-AUDIT-GREP-SNIPPET** | MIT EXIT-FEATURES audit H1 補 grep snippet 嚴謹度 | 下次 audit |
| **OC-1~6** | Webhook / Telegram 多通道 / MCP PostgreSQL | Phase 5+ |
| **WS-1** | FastAPI WebSocket/SSE 實時推送（替代 30s 輪詢）| 中優先 |
| **4-Conditional** | PairsTrading / Beta / Kalman / Jump detection | post-live |
| **G-6/G-7/G-8/G-10** | Edge JS retrain / ClaudeTeacher / cost_gate credibility / isotonic | P1-7B / 21d+G-3 |
| **QoL-2** | Demo AI cost 追蹤 GUI（硬編碼 N/A）| G3-08 |
| **G7-05** | cost_gate grand_mean bind | grand_mean>-50bps ∧ eligible cells>0 ∧ ≥2 strategy shrunk>0 |
| **G-2 FundingArb 重評** | 三參數重評 | R-02 Strategist 在線 |
| **EDGE-P2 Phase B** | Liquidation signal | Phase A OI 驗收 ✅ 已完，Phase B deferred |

---

## 三、Active Observation Gates

| Gate | 真實狀態（PA SQL panorama） | 目標 | 結論時間 |
|------|---------------------------|------|---------|
| `[22]` trading pipeline silent gap | WARN：fills stale；rejected-only 風險／cost gates 拒絕視為 WARN（`b283fda` 校準）| distinguish writer/order push wedge vs unfilled maker working orders | 持續觀察 |
| `[16]` strategist cycle fresh | last cycle 11.3min ago；within 30-min backoff window | <30min backoff tolerated | transient observe |
| `[33]` maker fill rate | 7d rolling **27.2%**（CLAUDE.md drift） / **36.6%** (PA SQL ground truth)；fee_drop 22.0% | ≥60% fee_drop | ~05-07/08 |
| `[38]` grid lifecycle drift | demo p50 7.9min vs live_demo 3.2min；lifetime_ratio 0.41 WARN；live re_entry_rate 0.48 | lifetime ≥0.5x | ~05-06 再看 |
| `[40]` realized edge acceptance | 24h MLDE rows=37-39，avg_net **-17~-18 bps**；slippage live_demo 24h **-92.47 bps** (BUSDT loop) | net_bps_after_fee>0 | 等累積 + edge 翻正 |
| `[41]` scanner market-gate confirmation | events=1260 / cells=69 / scoreable=0，gate 已 fire 但 label 未足 | gate blocked cells later negative | 等 label 累積 |
| `[27]` intents counter freeze | demo stale 88.3m / intents_30m=0 / verdicts_30m=1 / approved_verdicts_30m=0；risk/cost gates rejected all | approved verdicts with 0 intents 才 FAIL | 持續觀察 |
| `[11]` counterfactual clean window | n=413/200, cf_fired=46，rolling 2d window shrink expected，WARN not FAIL after `2674e14` | fresh replay + 3d WARN/PASS streak；criteria grid/ma/orphan 達標 | 本週 |
| `[42]/[42b]` LG-5 reviewer | 0 audit row 累積（sibling CC FUP-1 commit `463890d` 已 land）| >0 row/24h | 下次 deploy 後 |

**規則**：任何背景項連續 3 次 healthcheck FAIL = 中止被動等待，轉人工介入。

---

## 四、Healthcheck 清單（`passive_wait_healthcheck.py` 已實裝）

**Ground truth**：cron-wrapper output；裸 `python3 helper_scripts/db/passive_wait_healthcheck.py` 在非互動 SSH 可能缺 DB env；接手請用 wrapper。

| # | 項目 | 對應 |
|---|------|------|
| [1] | close_fills_24h | P0-2 engine 活性 |
| [2] | label_backfill | P1-7 C labels |
| [3] | exit_features_writer | EDGE-P1b 寫入面 |
| [4] | phys_lock_runtime | TRACK-P-V2 |
| [6] | trailing_stop_fire | — |
| [7] | edge_estimates_freshness | G1-01 / G4-04 |
| [8] | shadow_exits_24h | EDGE-P2-flip 前 baseline |
| [9] | model_registry_freshness | G4-03 |
| [10] | intents_writer_ratio | G2-01 |
| [11] | counterfactual_clean_window_growth | EDGE-P3 |
| [12] | bb_breakout_post_deadlock_fix | G2-06 disabled → PASS skip |
| [13] | edge_estimator_scheduler_fresh | G1-01 |
| [14] | exit_features_accumulation_rate | EDGE-P1b per-strategy |
| [15] | shadow_exit_agreement_phase2 | EDGE-P2 flip |
| [16] | strategist_cycle_fresh | G3 Strategist runtime |
| [18] | disabled_strategy_inventory | G2-06 drift 防線 |
| [19] | observer_pipeline_alive | G9-04 |
| [20] | h_state_gateway_freshness | G3-08 |
| [21] | paper_state_dust_inventory | Dust prevention |
| [22] | trading_pipeline_silent_gap | F7 |
| [23] | orders_fills_consistency | F7 |
| [24] | signals_writer_freshness | F7 |
| [25] | dust_qty_distribution | F7 |
| [26] | dust_spiral_noise_in_ef | EXIT-FEATURES fix |
| [27] | intents_counter_freeze | F7 |
| [28] | phantom_fills_attribution | F7 |
| [29] | reconciler_paper_state_divergence | deferred Rust handler |
| [30] | cost_edge_advisor_status | G3-09 Phase B |
| [31] | edge_diag_2_strategy_diversity | EDGE-DIAG-2 |
| [32] | maker_entry_intent_drift | G2-01 guard |
| [33] | maker_fill_rate | G2-01 PostOnly target ≥60% |
| [34] | intent_signal_attribution | STRATEGY-EDGE-REPAIR |
| [35] | MLDE data contract | MLDE demo autonomy |
| [36] | MLDE advisory/live lease boundary | MLDE demo autonomy |
| [37] | MLDE demo applier audit | MLDE demo autonomy |
| [38] | grid_trading_lifecycle_drift | GRID-LIFECYCLE-DRIFT |
| [39] | strategy_name_cardinality_drift | STRATEGY-NAME-ATTRIBUTION |
| [40] | realized_edge_acceptance | post-deploy edge observation |
| [41] | scanner_market_gate_confirmation | scanner market judgement 後驗 |
| [42] | lg5_review_audit_lag | LG-5 W3 IMPL-3（sibling CC FUP-1 deploy 後啟動）|
| [42b] | lg5_attribution_drift | 同上 |
| [Xa] | leader_election_health | G1-01 |
| [Xb] | pipeline_triangulation | G6-01 |

### 📅 排程提醒

| 日期 | 任務 | 觸發腳本 | Acceptance |
|---|---|---|---|
| **2026-05-09**（週六）| 3C deploy 7 天後對比 audit：5 metric vs prior 7d baseline | `bash helper_scripts/db/audit/2026-05-09_3c_7d_audit.sh` | exit 0（all metrics expected direction）→ PA review；exit 1 → operator 決策 base_ratio 是否續收緊或回退 |
| **2026-05-16**（週六）| funding_arb 1B 樣本累積 14 天彙總，判斷 2A 棄策略 trigger | `bash helper_scripts/db/audit/2026-05-16_funding_arb_14d_audit.sh` | n≥30 且 net bps 顯著負 → 2A 觸發棄策略；n<30 → 續收 |
| **REF-20 Wave 1 派發 checkpoint**（立刻）| Wave 1 P0 docs/scaffold 9 task 並行派發（PA / E1 / E1a / E3 / A3 / PM 多 owner，全 docs only 無 runtime risk）— 詳 `docs/execution_plan/2026-05-03--ref20_implementation_workplan_v1.md` §4 Wave 1 表 | 9 task 全 PM sign-off | Wave 1 exit → 啟 Wave 2 P1 IA + P2a foundation |
| **REF-20 Wave 5 prereq watch**（持續，~05-15 至 ~05-25）| 觀察 LG5-W3-FUP-2 attribution writer deploy + decision_outcomes timeframe '1' vs '1m' fix + demo 21d unlock（2026-05-07）三條件 | 三條件全 GREEN | Wave 5 P3a/P3b 才能啟（量化 calibration） |

> 為什麼不用 `/schedule` remote agent：DB 在 trade-core localhost，遠端 cloud agent 沒 SSH/Tailscale。改寫腳本進 repo + TODO 提醒，operator（或 CC session）到日期 ssh 跑一行即可。
> Refs：`memory/project_2026_05_02_p0_sqlx_hash_drift.md` / `memory/project_funding_arb_v2_deprecation_path.md`

---

## 五、接手三連檢查

```bash
git status && git log --oneline -5
ssh trade-core "python3 helper_scripts/canary/engine_watchdog.py --data-dir /tmp/openclaw --status"
ssh trade-core "cd ~/BybitOpenClaw/srv && bash helper_scripts/db/passive_wait_healthcheck.sh --quiet"
```

---

## 六、工作流程速查

```
角色鏈：E1/E1a 並行（≤5）→ E2（強制）→ E4（強制）→ PM 確認 → commit + push
P0 快速通道：PA → E1（≤5）→ E2 → E4 → PM（可省 FA / E5 / E3 / CC）
sign-off 前必檢：git status --porcelain clean（P0-GOV-3 強制）
```

部署：`ssh trade-core "bash helper_scripts/restart_all.sh --rebuild --keep-auth"`（C 改動 commit 後跑此命令一次性 promote 所有 ahead-of-deploy commit + LG-5 reviewer 啟動）

---

**簽核鏈**：PA 核實 → PM Sign-off（必檢 git status clean）→ commit/push → Linux pull
**下一決策點**：~05-09 3C deploy 7d audit · ~05-15 P0-3 edge decision + Decision Lease flag flip canary 24h · ~05-16 funding_arb V2 14d audit
