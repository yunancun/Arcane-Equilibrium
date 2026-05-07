# 玄衡 TODO — 工作清單（v12 · P0/P1/P2 三層 · 2026-05-06）

**版本**：v12（2026-05-06 soft rename：正式項目名改為「玄衡 · Arcane Equilibrium」；OpenClaw 保留為控制平面 / Gateway / Console / 通信服務族；Bybit 保留為唯一交易所 adapter / connector）
**v11 摘要保留**：2026-05-06 R4 audit sweep：archive 25 done + 5 obsoleted-by-gov-change items；P1-INFRA-3 整塊 REF-20 Sprint A-D + Wave 1-9 + Sprint 1-4 closure 移歸檔
**v10 摘要保留**：2026-05-06 active-doc sync REF-20 A-D closed + post-signoff reality-gap fix `67b95808` + AgentTodo MAG-000 confirmed
**v9 摘要保留**：2026-05-05 §九 LOC governance change：硬上限 1500→2000（operator 決定，REF-20 Sprint C 拍板）；警告線維持 800。
**REF-20 closure 摘要**：Sprint A+B+C+D 已 closed；R9 PM sign-off commit `6a7a885c` + reality-gap fix `67b95808`。詳 → `srv/memory/project_2026_05_03_ref20_sprint1_2_closure.md` + `docs/archive/2026-05-06--todo_completed_extract.md`。Operator-side outstanding 僅剩 live PG opt-in smoke、V056 cron schedule、5 healthcheck sentinel deploy validation，不阻塞 REF-20 closure。
**玄衡 2026-05-06 命名定位**：正式項目名為「玄衡 · Arcane Equilibrium」；外部 OpenClaw Gateway 改為通信 / mobile / supervisor / proposal relay；本地 5-Agent 保持獨立；唯一 GUI 是 `trade-core:8000/console` OpenClaw Control Console。詳 `docs/architecture/2026-05-06--openclaw_control_plane_repositioning.md` + `docs/adr/0014-arcane-equilibrium-soft-rename.md`。
**REF-21 實證審查（2026-05-07）**：V1.3 final 8-agent real-code audit 接受；P0 replay availability blockers 已關。已修正 §10 replay baseline namespace collision、補 `OPENCLAW_REPLAY_BULK_ALLOW_PROD_IP` guard、落 V057-V061 migration targets、回填 GUI 13-tab 與 LOC governance；V057-V060 Guard A/B/C + Linux PG transaction dry-run 已綠且 rollback 後 0 persisted table；V061 `replay.calculate_promotion_metrics` 非 stub SECURITY DEFINER body 已落地並以 Linux replay data transaction dry-run 驗證 eligible=true/rollback。`/full-chain/run` 已走 dedicated Rust `replay_runner` subprocess，scanner timeline / V058 / V059 / local BBO/orderbook overlay / fee-aware report analytics / one-click GUI / read-only ML-Dream advisory ranking 已上線。2026-05-07 S1 calibration lift 已補 deterministic depth partial-fill、latency q50/q90、baseline-vs-candidate comparison、balance curve + stationary block bootstrap run bands、recorder retention/maturity policy。剩餘不是「能不能用」而是 empirical calibration maturity：更長本地 recorder 歷史、per-cell maker/fill calibration、operator baseline library、Bybit ToS/fair-use review；recorder 啟動前的舊窗口仍不得 fabricated microstructure。
**Source checkpoint before soft rename**: `61634f3a`（Mac/Linux/origin source 同步；2026-05-06 SSH 驗證 Linux clean；本次玄衡 soft rename 為 docs-only，不 rebuild / restart / DB write）· **Engine runtime**: watchdog demo/live alive，paper inactive by design；last verified full rebuild remains Sprint 3 Track I (`dbcf845b`)。
**測試基準**：Python pytest **3431 PASS** / 1 fail (pre-existing E4-P0-1) / 10 skip · Rust cargo workspace **3132 PASS** / 2 fail (pre-existing E4-P0-2) / 3 ignored · Sprint 3 Track H Python sibling 44/44 PASS
**21d demo 時鐘**：2026-04-16 22:16 → 解鎖 **2026-05-07**

**歸檔索引**：
- **2026-05-06 R4 sweep**：`docs/archive/2026-05-06--todo_completed_extract.md`（P1-INFRA-3 整塊 + P0-DATA-INDICATOR-SWEEP + P2-CODEX-3 + 5 OBSOLETED-BY-GOV-CHANGE）
- 4-day codex audit closure 詳細 + Wave 4 Pre-Stage 5 軸線完整表 + Top 10 派發優先序 → `docs/archive/2026-05-02--TODO-pre-trim-snapshot.md`
- 62-finding Batch A-F：`docs/archive/2026-04-29--62finding-batch-A-to-F.md`
- STRKUSDT P0 Wave：`docs/archive/2026-04-29--strkusdt-p0-wave.md`
- Wave A-H 完整敘述：`docs/archive/2026-04-29--wave-A-to-H-narrative.md`
- Wave 1-3 完成表格 + Backlog 完成項：`docs/archive/2026-05-01--completed_waves_1_2_3_and_backlog.md`

---

## 一、真實狀態（2026-05-02 panorama 整合）

5 策略 7d gross 真實 net **-6.98 USDT**（demo）+ **-0.81 USDT**（live_demo）— grid 唯一 +5.77，其它 4 個合計 -11.96。LG-5 W3 FUP-1 sibling CC commit `463890d` 已 land，待下次 deploy 後 reviewer 啟動。**Decision Lease retrofit AMD-2026-05-02-01 Track H 業務代碼 + V054 schema 已 land**（commit `dbcf845b`）+ **Track I Linux deploy Phase B-G executed**（feature flag `OPENCLAW_LEASE_ROUTER_GATE_ENABLED=0` default OFF → production runtime 0 行為改動）。**REF-20 Sprint A+B+C+D closed (2026-05-05)**，R9 PM sign-off `6a7a885c` + post-signoff reality-gap fix `67b95808` 後，Paper Replay Lab is usable for demo research；replay-derived rows remain advisory / non-commanding and do not authorize live trading。

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
| **P0-GOV-1** ✅ | **Decision Lease 路徑 A retrofit**（Rust `acquire_lease()` facade + router gate + Python IPC 轉呼 + bundled audit writer fix）| LAND 2026-05-03：`dbcf845b` IMPL + `0ad79f67` deploy；feature flag `OPENCLAW_LEASE_ROUTER_GATE_ENABLED=0` default OFF → production 0 行為改動；§5.4 canary flip 待 ~2026-05-15 P0-EDGE-2 後 operator action。詳 `docs/governance_dev/amendments/2026-05-02--SM-02_R04_retrofit_path_a.md` |
| **P0-GOV-2** | ✅ **source + Linux smoke row proof closed**：`agent.messages` / `state_changes` / `ai_invocations` 不再是 all-time 0；`MessageBus` 僅作 legacy/advisory trace，不得升為 Agent Decision Spine 權威。2026-05-06 `[52]` strict 先 FAIL `0/0/0`，受控 smoke 後 PASS `messages=2 state_changes=11 ai_invocations=2`。Production continuous event-store flag / real supervisor cloud rows 仍需未來 runtime enablement；MAG-019 已只落 default-disabled ledger policy | AgentTodo M1 durable event-store wave；local row proof closed；OpenClaw supervisor cloud ledger policy closed，real cloud call remains disabled |
| **P0-GOV-3** | SOP「sign-off 必檢 `git status --porcelain` clean」gate（LG-5 漏洞同類防線）| CLAUDE.md §七 已加，需新 PR review template |
| **P0-GOV-4** | Live credential rotation 7 步（PG password + Grafana admin + 6 commit history 清理）| 2 day work，Live 前必 |

#### P0-OPS — 運維紅線

| ID | 任務 | 狀態 |
|----|------|------|
| **P0-OPS-1** | HTTPS deploy + Cookie secure G-4（PRE-LIVE-2 source not landed，3d 工時）| 0% IMPL |
| **P0-OPS-2** | KYC / 地理禁區 / Bybit ToS 合規確認（0 governance entry）| Operator 法律確認 |
| **P0-OPS-3** | Disaster runbook + Live first-day SOP（dust clear SOP only，缺完整 first-day playbook）| 1d work |
| **P0-PROCESS-1** ⚠️ | E4 sign-off SOP 必加 Linux pytest 步驟（不只 Mac）— Sprint A R3 round 3 hotfix 揭 Mac Python 3.10 / Linux Python 3.12 FastAPI lazy ForwardRef 解析行為差異，Mac PASS ≠ Linux PASS。Sprint A R1+R2+R3 全部 hermetic test 在 Linux 真實 fail（100% 422 missing body）但 E4 只跑 Mac → false-positive sign-off。修法：E4 SOP 加 PM commit pre-check 階段「Linux pytest 必綠（透過 SSH bridge `ssh trade-core "cd ~/BybitOpenClaw/srv/... && .venv/bin/pytest <files>"`）」步驟；允許 Linux 已知 pre-existing fail 集 carry over，但需明文文檔化。詳：`srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-04--ref20_sprint_a_r3_impl.md` §12 | @PM @E4 |

#### P0-REF21 — Full-Chain Replay R2/R3 解阻

| ID | 任務 | 狀態 |
|----|------|------|
| **P0-REF21-1** ✅ | §10 baseline SLA namespace collision 修正：replay fixture row/decision count 改為 `254062 ±1%` / `10080 ±5%` scan cycles / `500-1500` intents；pytest baseline 獨立 | DONE in V1.3 empirical correction |
| **P0-REF21-2** ✅ | `OPENCLAW_REPLAY_BULK_ALLOW_PROD_IP` guard：live release profile 下 full-chain prepare 無 override 即 403，不 fetch Bybit | DONE source/test |
| **P0-REF21-3** ✅ | V057-V060 至少有真 migration targets：tier approval / symbol+freeze / edge snapshots / emergency audit log | DONE source/test |
| **P0-REF21-4** ✅ | MIT Linux PG dry-run V057-V060（apply transaction + rollback/disposable DB proof + Guard A/B/C + GRANT/REVOKE diff） | DONE 2026-05-06：pre-existing f/f/f/f/f → inside_tx t/t/t/t/t → after_rollback f/f/f/f/f；all Guard A/B/C notices emitted |
| **P0-REF21-5** ✅ | SECURITY DEFINER `replay.calculate_promotion_metrics` 真 body，對齊 `learning_engine/dsr_gate.py` + `pbo_gate.py` + `quantile_bootstrap.py`；禁止 stub deploy | DONE 2026-05-06：`V061__replay_promotion_metrics_calculator.sql` + static tests；Linux transaction dry-run with replay.experiments/simulated_fills/edge snapshots returned `eligible=true`, `fail_reasons=[]`, `PBO=0`, `q50.n_iter=1000`, then rollback |
| **P0-REF21-6a** ✅ | `POST /api/v1/replay/full-chain/run` API orchestration：同一份多幣種 S2 fixture，按策略逐一註冊 V049 manifest，並走既有 REF-20 `_do_pg_path_for_run_sync` spawn dedicated Rust `replay_runner` subprocess；不在 uvicorn 內跑策略/風控。Replay tab 預設 One-Click 入口已接此端點，Advanced 保留 manifest 工具。Mac/Linux targeted tests 16/16 PASS；Mac static replay asset tests 43/43 PASS。 | DONE source/test/gui |
| **P0-REF21-6b** ✅ | 真歷史 scanner timeline：replay-safe Rust scanner timeline module 已落，`replay_runner` 在 `mode=full_chain` manifest 下會從 fixture OHLCV 重建 60s scan cycles，並在 adapter path 只對歷史 scanner active symbol 餵 strategy tick；已開倉 symbol 仍吃 tick 以允許 exit。V049 manifest payload 已保留 `mode`/`scanner_config`/`edge_estimates`。Control API `POST /api/v1/replay/full-chain/run` 現在對 `current_scanner` 預設先讀 V058 `market.symbol_universe_snapshots`，並把 V059 `learning.edge_estimate_snapshots` 轉成 Rust `EdgeEstimates` JSON cells 嵌進 manifest；V058/V059 不存在或無資料時顯式 warning 降級。2026-05-07 補 `ref21_backfill_v058_v059.py` dry-run/apply helper，可從 Bybit public instruments-info 回填 V058 symbol universe / freeze log，預設抓 `Trading,PreLaunch,Delivering,Closed`、跳過 dated futures 等不符合 V058 symbol contract 的合約，並支持 `--asof` / `--freeze-asof` 分離；可從 `settings/edge_estimates*.json` 回填 V059 edge snapshots；replay fixture 現保留 Bybit kline `turnover`，Rust scanner timeline 優先使用 fixture turnover 重建 24h turnover，舊 fixture fallback 至 `close * volume`；`/full-chain/run` register 已修 `half_life_days=7` / `embargo_days=14` 以滿足 V041 `chk_embargo_days` 真 PG 約束。Linux `trade-core` 已 apply V060/V061、backfill V058 905 rows + V059 457 cells、build release `replay_runner`、API reload；current-config Linux smoke（2 symbols / 30m / grid）完成並 finalize。質量提升已補：recurring V058 recorder wrapper、dedicated public microstructure recorder、`market.market_tickers` BBO overlay、Rust fixture/tick BBO consumption、healthcheck `[53]`、C2 `/full-chain/coverage` preflight、C3 fee-net report analytics、C4 read-only ML/Dream advisory ranking。2026-05-07 S1 calibration lift 補齊 orderbook-depth partial fills、latency q50/q90、baseline comparison、balance curve + stationary block bootstrap run bands、recorder retention/maturity policy。剩餘真實邊界：Bybit public REST 不提供可回放的歷史 ticker/orderbook；recorder 啟動前沒有本地 microstructure row 的舊窗口仍只能標記為 S2/S2+ public kline replay，不做 fabricated L2。 | DONE runtime usable; S1 calibration lift implemented; empirical confidence now depends on recorder-history maturity and future per-cell calibration |
| **P0-REF21-7** ✅ | Rate/IP 50 req/s 真 enforce + replay dedicated public Bybit client；避免共用 production rate window。`ReplayBybitPublicClient` endpoint allowlist + per-endpoint lower budget + 429/5xx bounded retry 已落，Mac/Linux targeted tests 12/12 PASS。 | DONE source/test |

#### P0-DATA — 資料正確性紅線（跨 wave prerequisite）

| ID | 任務 | 阻塞下游 | 狀態 |
|----|------|---------|------|
| **P0-DATA-INDICATOR-SWEEP** | ✅ **DONE 2026-05-03** — 5/5 PASS verdict, indicator leak-free sweep；details → `docs/archive/2026-05-06--todo_completed_extract.md` + verdict `docs/audits/2026-05-03--P0-DATA-INDICATOR-SWEEP_verdict.md` | （已解除）| ✅ DONE |

---

### 🟠 P1 — Important（Live 質量 / 在 LG IMPL 前後完成）

#### P1-FAKE — Fake-live wiring 修

| ID | 任務 | 來源 |
|----|------|------|
| **P1-FAKE-1** | ExecutorAgent `shadow_mode_provider` `lambda: True` fail-close default fix（G3-03 Phase B 名為 wired 實際仍 shadow）| PA panorama |
| **P1-FAKE-2** | H0_GATE singleton 0 production caller wire（DOC-02 spec 死於 wiring，LG-2 IMPL 前提）| FA-H2 |
| **P1-FAKE-3** | HStateCache + CostEdgeAdvisor 兩 late-inject slot 啟用（env-gated `OPENCLAW_H_STATE_GATEWAY=1` / `OPENCLAW_COST_EDGE_ADVISOR_*` 未設）| PA panorama |

#### P1-OPENCLAW — Gateway / Agent Control Console

**執行順序**：以 `docs/architecture/multi_agent_rework_2026-05-05/AgentTodo.md` 為接手入口。AgentTodo Sprint A（MAG-015 -> MAG-010..014 -> MAG-016/017 -> MAG-018/019）已完成；M2 MAG-020..026 Scanner Advisory Conversion 已完成；M3 Agent Decision Spine Shadow（MAG-030..035）已完成；M4 Strategist V2（MAG-040..045）已完成；M5 Guardian V2（MAG-050..054）已完成；M6 Executor Planner 已完成 MAG-060 ExecutionPlan interface/order-style contract。下一步若繼續 AgentTodo，進 MAG-061 implement ExecutionPlan generation。Telegram/WebChat、proposal approval relay、第二 GUI 仍不在下一步。

| ID | 任務 | 來源 |
|----|------|------|
| **P1-OPENCLAW-0** | ✅ AgentTodo Sprint A closed：MAG-015 contract addendum frozen；MAG-010..014 durable event-store source + Linux controlled `[52]` row proof closed；MAG-016/017 read-only authority lockdown + `/status` + `/self-state` closed at `cbb225b7`；MAG-018 Agent Control GUI foundation closed at `12d3f3ff`；MAG-019 supervisor cloud ledger policy closed at `65a4279f`；OpenClaw 工作不得繞過 read-only foundation | AgentTodo 2026-05-06 PM handoff |
| **P1-OPENCLAW-1** | ✅ MAG-016 closed：OpenClaw Gateway authority lockdown tests prove allowlist `/api/v1/openclaw/*` is exactly two GET endpoints and no direct order / live TOML / Bybit key / secret / deploy path is exposed; OpenClaw request context缺失會降級 degraded/anonymous posture | 2026-05-06 control-plane repositioning |
| **P1-OPENCLAW-2** | ✅ MAG-017 closed：read-only `/api/v1/openclaw/status` + `/api/v1/openclaw/self-state` 聚合 API 已新增；返回 backend-authored degraded envelopes，不啟用 write/proposal endpoint | OpenClaw Gateway development plan + AgentTodo MAG-017 |
| **P1-OPENCLAW-3** | 再新增 `/brief/latest` / `/diagnostics` / `/escalations` 聚合 API；必須由 durable event store + `agent.ai_invocations` 支撐，不讓前端拼 raw table | OpenClaw Gateway development plan |
| **P1-OPENCLAW-4** | ✅ MAG-018 closed：`tab-agents.html` 已升級為 read-only OpenClaw / Agent Control foundation；topology、self-state、gateway/channel posture、degraded/error states 由 backend view model 驅動，無手動交易控制、無 raw table join | GUI OpenClaw Control Console plan + AgentTodo MAG-018 |
| **P1-OPENCLAW-5** | ✅ MAG-019 closed：Supervisor cloud escalation policy 已落地；cloud 預設 disabled，需顯式 budget/model config；本地 5-Agent 不獨立叫 cloud，未來 cloud call 必先建立 supervisor packet 並預留 `agent.ai_invocations` ledger row | Operator 2026-05-06 architecture decision + AgentTodo MAG-019 |
| **P1-OPENCLAW-6** | Proposal / approval queue：OpenClaw 只能 create proposal 和 relay approve/reject；交易影響仍走 canonical GUI approval queue + GovernanceHub + Decision Lease + Rust | OpenClaw Gateway + GUI plans |
| **P1-OPENCLAW-7** | Telegram/WebChat mobile lane：最後接入 alert / read-only query / approval relay；Gateway outage 不影響 Rust trading runtime | OpenClaw Gateway development plan |

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
| **P1-INFRA-3** | ✅ **REF-20 Sprint A+B+C+D + Wave 1-9 + Sprint 1-4 ALL CLOSED (2026-05-05)** — R9 PM sign-off `6a7a885c` + reality-gap fix `67b95808`. Detail (Wave 1-9 closure / Sprint 1-4 evidence trail / Sprint A-D commit chain / A1-A10 + R9 7 conditions): `docs/archive/2026-05-06--todo_completed_extract.md` + `srv/memory/project_2026_05_03_ref20_sprint1_2_closure.md`. **Wave 7 仍 DEFERRED**（P1-INFRA-3f）— LG-2/3/4 frontend stable + 7d healthcheck PASS 後 operator action，per AMD-2026-05-03-01。Operator-side outstanding（不阻塞 closure）：live PG opt-in smoke / V056 cron schedule / 5 healthcheck sentinel deploy validation。 | DONE |
| **P1-INFRA-3f** | ⏸ **Wave 7 DEFERRED + IMPL-accept-deploy-blocked** — P5 4 task IMPL-in-tree (commit `c887e4e` operator override) 但 hard prereq LG-2/3/4 frontend merged + 7d stable 仍 NOT GREEN；正式 amendment AMD-2026-05-03-01 (commit `5184990`) 規範 IMPL/Deploy 2-stage gate + 4 AC + 失敗回退；deploy gate retained pending healthcheck `[46]` | LG-2/3/4 stable |

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
| **P2-FOLLOW-UP-3** | ✅ **OBSOLETED-BY-GOV-CHANGE-2026-05-05**（governance 1500→2000 後 1542 < 2000 不再 violation。但 W6 commit msg 0 doc accept 的歷史 governance drift issue 仍可 archive 為治理教訓）— ~~Wave 6 `mlde_demo_applier.py` 1542 LOC > 1500 hard cap §九 violation~~ | OBSOLETED |
| **P2-FOLLOW-UP-4** | W5 NumPyro Mac scipy fallback 自宣「1:1 alignment」0 cross-OS sibling test。修法：加 production scale (n_warmup=1000 / n_samples=2000) Mac aarch64 vs Linux x86_64 同 seed 一致性 sibling test ledger | @E1+@MIT |
| **P2-FOLLOW-UP-5** | REF-20 final closure doc `2026-05-03--ref20_final_closure_and_deploy_guidance.md` line 99 自宣「Expected: ~3500+ Python pytest PASS (Wave 1-9 cumulative)」是虛構數字（cold reality 3387 PASS，差 113-126）。修法：訂正成「Sprint 1 後 3387 PASS / 1 fail (pre-existing) / 10 skip」+ Wave commit message 數字一致性審查 | @PM |
| **P2-WAVE-3-DOCTEST-FIX** | mac_policy_guard.rs doctest fail（與 P2-FOLLOW-UP-2 重疊，merge 處理）；E5 follow-up 0 ticket | @E1 |
| **P2-WAVE-4-W6-REFACTOR** | ✅ **OBSOLETED-BY-GOV-CHANGE-2026-05-05**（governance 1500→2000 + Sprint B B1 R0-T0 已釋放 replay_routes.py 至 1146 LOC）— ~~replay_routes.py 1500 LOC governance；Wave 4 commit msg ack 但 TODO.md 0 hit~~ | OBSOLETED |
| **P2-WAVE-5-NTHRESHOLD-SWEEP** | shrinkage_router N_THRESHOLD 30/50 boundary sweep test 缺 + production chain 1000/2000 在 CI 0 跑（Sprint 2 E2 F1 LOW + E4 F2 mock retroactive flag）| @E1+@MIT |
| **P2-WAVE-6-MLDE-DEMO-APPLIER-SPLIT** | ✅ **OBSOLETED-BY-GOV-CHANGE-2026-05-05**（governance 1500→2000 後 1542 < 2000 不再硬上限 violation；split refactor 仍可作 high-cohesion review，但非 governance 必須）— ~~mlde_demo_applier.py 1542 LOC > 1500 hard cap split refactor~~ | OBSOLETED |
| **P2-WAVE-6-V043-HEALTHCHECK** | V043 mlde_replay_veto_log 0 healthcheck pairing（passive_wait_healthcheck.py 加 `check_47_v043_advisory_writer()`）| @E1 |
| **P2-WAVE-8-HANDOFF-HEALTHCHECK** | handoff request flow 0 healthcheck（cooldown rejected rate / V044 UNIQUE collision rate / pg_unavailable degraded rate）— Sprint 2 E2 F1 LOW；passive_wait_healthcheck.py 加 `check_48_handoff_health()` | @E1 |
| **P2-WAVE-9-V047-V048-RETENTION** | V047 / V048 plain table 1y retention 0 設（MIT cold audit + Sprint 2 E2 F1 LOW）— hypertable 升級 OR retention drop policy | @E1+@MIT |
| **P2-LEASE-VEC-CLEANUP** | `DecisionLeaseSm.objects` Vec 在 lease 終態（Consumed/Revoked）後不 swap_remove，pre-existing 設計 leak ~200 bytes/trade（1yr × 1000 trade/day = 73MB Vec heap leak）— REF-20 Sprint 3 Track H E-1 retrofit push back #3 揭。修法：terminal state 後 `swap_remove` + 同步更新 `lease_id_to_idx` HashMap reverse mapping；加 e2e leak guard test | @E1 |
| **P2-INTENT-PROCESSOR-TESTS-SPLIT** | `rust/openclaw_engine/src/intent_processor/tests.rs` 2910 LOC > 2000 hard cap (governance 2026-05-05 提至 2000 後仍超 910)（pre-existing 2375 已超舊 1500，Sprint 3 Track H E-1+E-2 retrofit +535）— §九 exception clause condition (1) 適用，**condition (2) 即此 ticket** + **condition (3) PM Sign-off 明文 declare**：兩 retrofit 撞 condition (3) baseline exception accept 理由 = (a) Decision Lease retrofit 是 P0-GOV-1 critical path / (b) 28 fixture 重寫 + 7 新 router_gate test 結構性必須在原檔同 module 內 / (c) 抽 helper module 風險高（既有 fixture 互相 import）。修法：split into `tests/lease_facade_tests.rs` + `tests/router_gate_tests.rs` + `tests/golden_extreme_tests.rs` 三 file；保留 `tests.rs` &lt;2000 LOC | @E1+@PM |
| **P3-V054-PYTEST-SIBLING** | V054 lease_transitions schema 0 Python pytest sibling — 與 V049-V052 Track D 模式不一致（test_v049_v050_v051_v052_track_d.py 24 case static-parse + cross-file invariants）。E4 Track H final regression 揭。修法：仿 test_v049_v050_v051_v052_track_d.py pattern 加 test_v054_lease_transitions.py（schema parse / Guard A/B/C / hypertable / event_type enum 7 values / FK to V035 governance_audit_log + REF-21 placeholder）| @E1 |
| **P3-PYDANTIC-V2-MIGRATE-REPLAY** | replay/ 全模組 `@validator` (Pydantic V1) → `@field_validator` (V2) migration；含 `experiment_registry.py` (5 validator) / `replay_models.py` (1 validator) / 其他 replay/ 內 Pydantic V1 用法。Trigger: Pydantic V2.13+ 持續輸出 `PydanticDeprecatedSince20` warning（pytest run 每次 6+ 條 noise，Sprint A R2 round 2 review L-2 揭）。當前不阻塞 R2/R3 功能；Pydantic V3.0 釋出時會 hard-break。修法：`@validator → @field_validator` + `pre=True → mode='before'` + 必要時 retrofit signature（`(cls, v, values)` → `(cls, v, info)` 用 `info.data`）；保所有 round 1+2 validator 行為（symbol/strategy alphanumeric+_ guard / data_tier enum / timeframe enum / strategy_config_sha256 / risk_config_sha256 / manifest_jsonb 256 KB / window order）+ `_no_reserved_prefix_keys` 順序在 `_size_cap` 前 unchanged。E1 round 3 Sprint A R2 round 2 review L-2 defer | @E1 |
| **P2-R3-FOLLOW-UP-1** | V### migration 加 `'replay_report'` value 至 V046 `chk_replay_report_artifacts_type` enum + 同步 `canary_writer.py::ALLOWED_ARTIFACT_TYPES` 擴。當前 R3 用 `'pnl_summary'`（最近義 in-allowlist），語意對齊但下游 R5 query `WHERE artifact_type='fill_log'` / `artifact_type='replay_report'` 找不到 fill data。修法：V0XX migration ALTER TABLE replay.report_artifacts DROP CONSTRAINT chk_replay_report_artifacts_type + ADD CONSTRAINT 加新 6-value enum；同步 ALLOWED_ARTIFACT_TYPES 加 `ARTIFACT_TYPE_REPLAY_REPORT`；修 `run_finalize_route.py` 用新 enum value（從 `'pnl_summary'` 改為 `'replay_report'`）。Sprint A R3 round 2 fix M-3 揭（E3 §6 MEDIUM-2） | @E1 |
| **P2-R3-FOLLOW-UP-3** | `run_finalize_route.py` exception 路徑 message field generic 化（exception detail 僅 `logger.warning`），符合 §九 SEC-04 `detail=str(e)` 政策；當前 503 path 含 `f"finalize failed: {type(exc).__name__}"` 可能 leak 內部 stack 結構（exception class name 是 internal API），message 應改 `"finalize failed (internal error logged)"` 同時保 logger.warning 完整 stack。Sprint A R3 round 2 fix L-1 揭（E3 §6 LOW-1） | @E1 |
| **P3-R3-FOLLOW-UP-4** | `verify_replay_runner_pid` 加 `psutil.Process.create_time()` 校驗防 PID-reuse cmdline 巧合 false positive；schema add: V045 column `subprocess_started_at_ms BIGINT`；spawn writer 在 `route_helpers.spawn_replay_runner` 寫；`verify_replay_runner_pid` 讀+比 `psutil.Process(pid).create_time() * 1000 == subprocess_started_at_ms ± tolerance`。當前 cmdline match 在 PID-reuse + cmdline 巧合下 false positive 卡 finalize（極罕見但非零）。Sprint A R3 round 2 fix L-2 揭（E3 §6 LOW-2） | @E1 |
| **P2-R3-FOLLOW-UP-5** | V046 `byte_size CHECK BETWEEN 0 AND 67108864`（64 MB）defense-in-depth；real bound 由 upstream `simulated_fills_writer.MAX_REPORT_BYTES = 16 MB` 防（parse 階段 reject oversized file）。但 V046 schema 層無此 CHECK，未來若 upstream cap 被誤調高（or attacker 繞 parse 直 INSERT）則 V046 row 可載入超大 byte_size。修法：V0XX migration `ALTER TABLE replay.report_artifacts ADD CONSTRAINT chk_replay_report_artifacts_byte_size CHECK (byte_size >= 0 AND byte_size <= 67108864)`。Sprint A R3 round 2 fix L-3 揭（E3 §6 LOW-3） | @E1 |
| **P2-R3-FOLLOW-UP-6** | `tests/test_replay_routes_auth.py` 3 case 在 Linux 真 PG 環境下 fail：用 `experiment_id="exp-2026-05-03-test"`（不是 valid UUID），fix 後路徑通暢但 PG `replay.experiments.experiment_id` UUID column 拒收 → `InvalidTextRepresentation` → 503 spawn_failed。Mac mock fixture 假 PASS（從未打 PG）。Sprint A R3 round 3 hotfix 揭（git stash 雙向驗證確認 pre-existing fixture bug，非 hotfix regression）。修法：fixture 改用 `uuid.uuid4().hex`（V049 schema-compliant UUID）+ test setup 先 INSERT V049 experiments row 滿足 FK；3 case 名 `test_authenticated_zero_active_run_post_run_accepts` / `test_authenticated_per_actor_cap_returns_409` / `test_authenticated_global_cap_returns_409` | @E1 |
| **P2-R3-FOLLOW-UP-7** | ✅ **OBSOLETED-BY-GOV-CHANGE-2026-05-05** + Sprint B B1 R0-T0（replay_routes.py 1499→1146 + cap 1500→2000，~854 LOC margin） — ~~`app/replay_routes.py` 1499 LOC（1 LOC margin to 1500 cap）~~ | OBSOLETED |

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
| **P2-STRUCT-2** | ✅ **OBSOLETED-BY-GOV-CHANGE-2026-05-05**（governance 1500→2000，1496 < 2000 不再 near cap）— ~~LG5-CONSUMER-SPLIT P3（`governance_hub_live_candidate_review.py` 1496/1500 LOC near cap）~~ | OBSOLETED |
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
| **OC-1~6** | Superseded by P1-OPENCLAW-1..5：OpenClaw Gateway 作通信 / mobile / supervisor / proposal relay，不作第二 GUI 或交易 conductor | 2026-05-06 architecture overlay |
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
| `[40]` realized edge acceptance | 24h MLDE rows=19，avg_net **-27.93 bps**；slippage live_demo 24h **-92.47 bps** (BUSDT loop) | net_bps_after_fee>0 | 等累積 + edge 翻正 |
| `[41]` scanner market-gate confirmation | events=1260 / cells=69 / scoreable=0，gate 已 fire 但 label 未足 | gate blocked cells later negative | 等 label 累積 |
| `[51]` scanner opportunity shadow/canary acceptance | 3h snapshot routes=485/485、scanner intents=50/50；24h labels=9，positive_avg=27.93bps / nonpositive_avg=-47.85bps / corr=0.21；post-`98ce3d00` latest scanner snapshot 85/85 cost_source=`account_manager_taker_fee`，30m rejected scanner intents 78/78 carry opportunity（2 canary） | labels≥10 後評估 calibration；rejected counterfactual labels需等 decision_outcomes backfill | row proof 完整但 label 未足；canary live for demo/live_demo new-open only |
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
| [42c] | lg5_attribution_drift_3d | R-meta gate 對齊 3d 鏡像 |
| [43] | label_backfill_freshness | edge label backfill cron 活性 |
| [44] | replay_manifest_key_presence | replay manifest key.hex deploy contract |
| [45] | pricing_binding | LG-3 provider pricing binding |
| [46] | mlde_shadow_retention_status | V056 retention cron + candidate cap |
| [47] | replay_runner_binary | Linux replay_runner binary presence |
| [48] | replay_manifest_registry_growth | replay.experiments row growth |
| [49] | replay_artifact_retention | V046 artifact TTL/cap |
| [50] | replay_run_state_health | V045 failed rate + zombie running |
| [51] | scanner_opportunity_shadow_acceptance | scanner opportunity row proof + calibration |
| [52] | agent_event_store_rows | AgentTodo MAG-010..012 `agent.messages` / `agent.state_changes` / `agent.ai_invocations` row proof |
| [53] | ref21_v058_symbol_universe_recorder | REF-21 recurring V058 universe snapshot liveness |
| [Xa] | leader_election_health | G1-01 |
| [Xb] | pipeline_triangulation | G6-01 |

### 📅 排程提醒

| 日期 | 任務 | 觸發腳本 | Acceptance |
|---|---|---|---|
| **2026-05-09**（週六）| 3C deploy 7 天後對比 audit：5 metric vs prior 7d baseline | `bash helper_scripts/db/audit/2026-05-09_3c_7d_audit.sh` | exit 0（all metrics expected direction）→ PA review；exit 1 → operator 決策 base_ratio 是否續收緊或回退 |
| **2026-05-16**（週六）| funding_arb 1B 樣本累積 14 天彙總，判斷 2A 棄策略 trigger | `bash helper_scripts/db/audit/2026-05-16_funding_arb_14d_audit.sh` | n≥30 且 net bps 顯著負 → 2A 觸發棄策略；n<30 → 續收 |
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
