# FA Full-Chain Functional Audit — 2026-05-08 Cold Panorama

審計員：FA · 基準 HEAD `4e2d2883` (~ TODO HEAD `503eeb33`) · 採集時間 UTC 2026-05-08 · 上次基準 2026-04-24（34 finding）。

**Tally：Critical 4 / High 11 / Medium 9 / Low 5 = 29 finding**（其中 12 個是 4-24 finding 的 status 變動，新發現 17 個）。

---

## §1 Executive Summary

14 天後相比 4-24 panorama，**最大進展**是 Decision Lease Path A retrofit（commit `dbcf845b`+`0ad79f67`）IMPL land 並在 Linux trade-core flag flip `=1`（TODO P1-AGENT-RUNTIME-1 DONE / `[55]` PASS chains_with_lease=33）+ agent_spine 模組真接線到 tick_pipeline 8 處。

**但 fake-live 仍未真活**：`risk_config_{demo,live,paper}.toml` 都把 `[executor].shadow_mode = true` 寫死，ExecutorConfigCache fail-close default 也是 `True`，意即即便 Path A flag 翻 ON，下游 Python ExecutorAgent 仍永遠 log-only — 5-Agent 鏈下單真值依然是 0。

**第二大發現**：CLAUDE.md §三 第 5 行寫「flag default OFF」、第 99 行重述同樣事實 — 與 TODO L75/L123 真實 runtime `=1` 牙線漂移，違反 CLAUDE.md §七「§三 數據 vs runtime drift 防線」。

**業務鏈完整度**從 4-24 ~52% 提升到 **~58%**（agent_spine 接線、replay foundation IMPL closed、scanner opportunity canary live），但學習進化（25%）與 fake-live 升 live（35%）兩節點仍是阻 live blocker。openclaw_core 9 模組死代碼維持原狀無變動（~4468 行 Rust dead）。

本輪 4 條對 PM push back：
1. §三 stale 修
2. shadow_mode TOML 與 retrofit IMPL 矛盾必須鎖定設計意圖
3. Layer 2 自主循環無觸發降為「本來就不打算 autonomous」明說
4. openclaw_core 死代碼 14 天 0 動作須 Sunset Decision

---

## §2 Spec → IMPL 對照矩陣

| Spec | 模組 | IMPL 狀態 | Evidence | 偏離度 |
|---|---|---|---|---|
| **SM-01** Authorization SM | `authorization_state_machine.py` | ✅ Active | 8 states / 16 transitions；test_authorization_state_machine.py 完整 | 符合 |
| **SM-02** Decision Lease SM | `decision_lease_state_machine.py` + Rust `governance_core::acquire_lease` | ⚠️ Active 但 flag-gated；CLAUDE.md drift | Python `governance_hub.py:769` + Rust `governance_core.rs:200` `OPENCLAW_LEASE_ROUTER_GATE_ENABLED`；Linux trade-core `=1`（TODO L75）；CLAUDE.md §三/§五 仍寫 default OFF | Spec ✅ / 文檔 stale |
| **SM-04** Risk Governor SM | `risk_governor_state_machine.py` | ✅ Active | 6-level，test_risk_governor_state_machine.py | 符合 |
| **EX-01** Protection & Anti-Hunt | `protective_order_manager.py` + Rust `exit_features/` | ✅ Active | hard stops + ATR 動態 | 符合 |
| **EX-02** OMS Lifecycle | `oms_state_machine.py` | ✅ Active | 11-state | 符合 |
| **EX-04** Reconciliation | `reconciliation_engine.py` | ✅ Active | test_reconciliation_engine.py | 符合 |
| **EX-05** Learning Tiers | `learning_tier_gate.py` | ⚠️ IMPL 有但無 promotion 真活路徑 | LG-2/3/4 0 行 IMPL（CLAUDE.md §三 18 blocker #2-4） | Spec → IMPL 0% real wiring |
| **EX-06** Agent Conflict Arbitration | `multi_agent_framework.py` + `market_regime.py` | ⚠️ Partial | Python 5 Agent `~4552 行` 接線；但 Executor shadow + Layer 2 unscheduled | Spec → IMPL ~70% |
| **EX-07** Agent Data Access | `governance_hub.py` | ✅ Active | TruthSourceRegistry 已注入 | 符合 |
| **DOC-01** Core Risk Doctrine | `protective_order_manager.py` | ✅ Active | hard stop §5.9 落地 | 符合 |
| **DOC-02** Scanning & Monitoring | `scanner_rate_limiter.py` + Rust `scanner/` | ⚠️ Partial | H0 hard authority 已 retire（TODO §三 W-C 註）；H0_GATE Python singleton 仍 0 production caller（FA-H2 14 天無變） | Spec → IMPL ~60%；H0 dead path |
| **DOC-03** Market Regime | `market_regime.py` | ⚠️ Spec 寫了 / IMPL 有 但 H1/H4 ThoughtGate **未** Regime-aware（FA-H9 14 天無變） | grep `MarketRegime` in `strategist_agent.py` H1 path = 0 | Spec → IMPL ~50% |
| **DOC-04** Agent Learning Evolution | `learning_tier_gate.py` + ml_training/ | ❌ 跨 14 天無 net 進度；6 表 0 INSERT、5 ML 腳本 silent-unscheduled 維持原狀 | grep `INSERT INTO learning.rl_transitions` = 0；helper_scripts/cron 無 ML scheduler | Spec → IMPL ~25% |
| **DOC-06** Change Audit | `change_audit_log.py` | ✅ Active | append-only JSONL | 符合 |
| **DOC-07** Audit Persistence | `audit_persistence.py` | ✅ Active | rotation | 符合 |
| **DOC-08** Incident Response | `incident_event_model.py` | ✅ Active | test_incident_event_model.py | 符合 |
| **REF-19** Reality-Calibrated Replay | `replay/` Rust | ✅ Active draft | `replay_runner.rs`、`forbidden_guard.rs`、`apply_fill.rs` 全部 land | 符合 |
| **REF-20** Paper Replay Lab | Sprint A-D closed | ✅ Active-with-caveat | `simulated_fills.evidence_source_tier` 帶 synthetic / calibrated / counterfactual 三 tier 區分；下游 ML 限定 IN ('calibrated_replay','counterfactual_replay')；V050-V067 全部 land | 符合 with REF-21 blocker |
| **REF-21** Full-Chain Replay | `docs/execution_plan/2026-05-06--ref21_*` | 🟠 Revise / Blocked | runner subprocess deploy / Bybit SSOT URI / negative-edge fail-closed FSM 多 R-gap 待修 | Spec 0% IMPL（plan only） |
| **AMD-2026-05-02-01** Decision Lease Path A | Rust `governance_core::acquire_lease` + `intent_processor/router.rs` Gate 1.4 + V054 audit writer | ✅ IMPL land；Linux flag `=1`；🔴 **CLAUDE.md §三/§五 stale 仍標 OFF** | RouterLeaseGuard RAII + tests +537 LOC；TODO P1-AGENT-RUNTIME-1 DONE | Spec → IMPL 100%；文檔 drift |
| **AMD-2026-05-03-01** Wave 7 IMPL/Deploy 2-stage Gate | — | ⏸ DEFERRED Wave 7 P5 LG-2/3/4 stable 後 | 24/25 V3 §12 acceptance binding GREEN | 符合（gated） |

---

## §3 Gap 分析（Spec ↔ Code 雙向漂移）

### A. Spec 寫了但 IMPL 缺漏（spec→code drift）

1. **DOC-04 Agent Learning Evolution**：spec 要求 tier advancement criteria + auto-promotion，IMPL 只有 `learning_tier_gate.py` 規則表 + 0 cron 觸發；6 張表 0 INSERT（rl_transitions / promotion_pipeline / symbol_clusters / cpcv_results / ml_parameter_suggestions / bayesian_posteriors）跨 14 天**完全無變動**。原則 12 紙上談兵。
2. **DOC-03 Market Regime → H1/H4 ThoughtGate**：spec 要 Regime-aware；H1 三閘只用 `complexity_score` 替代品（`strategist_agent.py:292-389`）。FA-H9 14 天無進度。
3. **EX-05 Learning Tiers**：spec 規定 L1-L5 tier promotion，TODO P0-LG-1/2/3 全 ACTIVE 0% IMPL（H0 production caller / pricing binding / supervised-live state machine 全 0 行）。
4. **DOC-02 Scanning & Monitoring → H0_GATE production caller**：Python singleton `paper_trading_wiring.py:290` 創建 + H0HealthWorker 每 5s 採樣，但生產代碼 `H0_GATE.check(...)` grep = 0（除 governance_extended_routes.py `:547` GUI status route）。FA-H2 14 天無變。
5. **REF-21 Full-Chain Replay**：plan 完整 V1.3，**0 行 IMPL** runner subprocess deploy / 寫confinement / negative-edge fail-closed FSM。
6. **CLAUDE.md §五 架構圖**：圖示標 `[I Decision Lease]` 是強制 gate；實際 Python `ExecutorAgent.acquire_lease()`（`executor_agent.py:492`）受 `_shadow_mode_provider() == True`（fail-close default + TOML 預設 `true`）短路，**production 不真實 acquire**。

### B. Spec 漏寫但 IMPL 已自由發揮（implicit contract / code→spec drift）

1. **`agent_spine/` 8 模組（contracts/events/store/signal_adapter/runtime_shadow/config/tests）真接線到 tick_pipeline / event_consumer / database**：W-A/W-B/W-C 結果 — 但 SM-XX/EX-XX 無對應條目；`agent_spine` 是**沒 spec 的事實 IMPL**。需補 `SM-05` 或 `EX-08` Agent Decision Spine 規格。
2. **`OPENCLAW_AGENT_SPINE_RUNTIME_MODE=shadow` env**：影響 typed Decision Spine 寫入；`config.rs:6 RUNTIME_MODE_ENV`、Linux trade-core `=shadow`。**0 規格條目**。
3. **`ExecutorConfigCache.shadow_mode_provider()` polling 機制**：G3-03 Phase B refactor，從 hardcoded `_shadow_mode = True` 改為 IPC-backed cache，fail-close default `True`。設計意圖（CLAUDE.md §九 註解）= 取代 P1-FAKE-1 hardcoded — 但**沒有 spec 條目記載 polling 失敗時的設計選擇** + 未明示 TOML `shadow_mode = true` 預設 = production 永 shadow。
4. **`Lg5ReviewConsumer` scheduler**（`lg5_review_consumer_scheduler.py:267`）：sibling CC commit `463890d` IMPL，但無 LG-5 Wave 3 spec 條目；只在 amendment 提到。
5. **`replay.simulated_fills.evidence_source_tier` 三 tier 區分**（synthetic_replay / calibrated_replay / counterfactual_replay）：V038-V040 IMPL；REF-19 spec 有提到「evidence verification」但**未明說三 tier 名稱與下游消費約束**。CLAUDE.md §九「Non-training surfaces」段落是 last line of defense — 應升級為 SM/EX 條目。

---

## §4 死代碼清單（按 severity 排序）

### Critical（運行時誤導）

1. **CLAUDE.md §三 / §五 / §四 lease retrofit drift**（severity Critical 因為下游決策依賴）— `srv/CLAUDE.md:99` + `:164` + `:204` 寫「flag default OFF / production 0 行為改動」；TODO `:75` + `:123` 寫 Linux runtime `=1`。**推測原因**：Sprint 3 Linux deploy（commit `0ad79f67`）後 §三 未 sync；違反 CLAUDE.md §七「§三 數據 vs runtime drift 防線」「7 日重驗或刪除」。

2. **`risk_config_{demo,live,paper}.toml` `[executor].shadow_mode = true` × 3**（`srv/settings/risk_control_rules/risk_config_demo.toml:246` + `live.toml:231` + `paper.toml:221`）— Decision Lease Path A retrofit IMPL land 但下游 Python ExecutorAgent 因 TOML 預設 永 shadow，**5-Agent 鏈下單仍 0 真值**（fake-success）。**推測原因**：3 個 TOML 在 G3-02 Phase A 全寫 `true` 是符合「LiveDemo 不因 endpoint 降級」原則（feedback memory），但 demo 環境也預設 shadow 意味著 demo path 也是 fake；P1-FAKE-1 修了一半（`shadow_mode_provider` 替代 hardcoded class attr），但 TOML 與 cache fail-close default 仍然 `True`。

### High

3. **openclaw_core 9 模組 0 engine 引用 ~4468 行**（`attention.rs` 424 / `attribution.rs` 267 / `backtest.rs` 490 / `cognitive.rs` 524 / `dream.rs` 936 / `message_bus.rs` 296 / `opportunity.rs` 861 / `order_match.rs` 308 / `portfolio.rs` 362）— 14 天**完全無變動**，操作層 4-24 標 P2 無人 follow up。**推測**：Rust migration master plan v2 §2.4 規劃但 Python 同義模組保留（`portfolio_risk_control.py` / `paper_state/fill_engine.rs` / etc）取代了，沒人 sunset Rust 版。
4. **`Layer2Engine.run_session()` 無 scheduler / cron / event trigger**（`layer2_routes.py:224` 唯一 production caller GUI 手動觸發）— FA-2026-04-24-C1，14 天無變。**推測**：設計意圖可能本來就是 GUI-only，但 CLAUDE.md §五 + memory 把 Layer 2 描述為「自主推理循環」誤導；應明說設計選擇。
5. **5 ML 訓練腳本 silent-unscheduled**：`thompson_sampling.py` / `optuna_optimizer.py` / `cpcv_validator.py` / `dl3_foundation.py` / `weekly_report_generator.py`；`canary_promoter.py` 也標「auto-promote cron deferred」（`ml_training/canary_promoter.py:4`）。**推測**：等 P1-7 LEARNING-PIPELINE-DORMANT-1 後一併接，但 P1-7 14 天 idle（labels 累積還在 47/200）。
6. **6 張 learning 表 0 production INSERT**（rl_transitions / promotion_pipeline / symbol_clusters / cpcv_results / ml_parameter_suggestions / bayesian_posteriors）— 14 天無變。**推測**：跟 #5 同源（ML 腳本不跑 → 表不寫）。
7. **`learning.exit_features.est_net_bps` 100% NULL write-side gap**（FA-H6）— sibling CC FUP-2 commit `34211ab4` PASS to E4 但**未 merge / deploy**（CLAUDE.md §三 18 blocker #11）。
8. **PerceptionPlane `validate_for_decision()` 0 production caller**（`perception_data_plane.py:513`，只在 tests 用）— FA-2026-04-24-H1，14 天無變。
9. **H0_GATE Python singleton + H0HealthWorker** — 創建 + 採樣但 `H0_GATE.check()` grep = 0（除 GUI status route）。**推測**：H0 hard authority 已被 Rust 側 retire（W-C 註），Python H0_GATE 是孤兒。建議刪除或 IPC 注入 Rust。
10. **HStateCache + CostEdgeAdvisor 兩 late-inject slot env-gated OFF**（CLAUDE.md §三 18 blocker #10；`OPENCLAW_H_STATE_GATEWAY` env 未設）— 碼好未啟。
11. **CONTEXT.md 11 個過時 sentence**（`srv/CONTEXT.md:404` 描「Path A retrofit IMPL landed but feature flag default OFF; production behavior unchanged」）— 與 TODO 真實狀況同樣 stale。
12. **`risk_config_paper.toml` `[executor].shadow_mode = true`**（`paper.toml:221`）— PAPER-DISABLE-1 後 paper 預設關，這個 TOML 的 shadow_mode 是死設定（paper 永不啟動就用不到）。

### Medium / Low（承襲 4-24）

13-29. M1 correlated_exposure_max_pct TOML 漂移、M2 grafana_data_writer pipeline_bridge=None、M3 Python backtest stub、M4 evolution_engine._engine 來源不明、M5 V999 migration 命名衝突、M11 LiveAuthWatcher 5s poll 無 backoff、M12 V001-V022 Guard 覆蓋度未審、M13 _SCOUT_WORKER singleton 未登 §九（部分修），L1-L8 cosmetic — **均承襲 4-24 報告無顯著變動**。

---

## §5 業務鏈完整度評分（8 節點 0-100%）

| 節點 | % | Evidence |
|---|---:|---|
| **自動掃描** | 95% | ScoutWorker 30min daemon 持續活；MarketScanner 5min cycle；W-E DONE 2026-05-07 |
| **策略選擇** | 55% | 5 策略 wired，但 `[40]` 24h n=19 net -27.93 bps 邊際整體負；Strategist `shadow=False` 真活但無 Regime-aware（H9）；DOC-04 tier promotion 0% |
| **AI 風控評估** | 78% | H1-H5 接通 + Guardian APPROVE；但 H1 cooldown 字典 + Layer 2 cron 都 GUI-only |
| **下單（demo+live_demo+true-live）** | **35%** | demo + live_demo 真 fills 流量（grid 1162 / ma 635 / funding 99 / bb_breakout 34 / bb_reversion 7）走 Rust tick_pipeline 直接路徑；5-Agent 鏈最後一步 ExecutorAgent shadow_mode=true (TOML × 3) → 0 真實下單；true-live 0 流量 by design |
| **止損** | 95% | StopManager + ATR 動態 + Bybit 條件單；Wave 5b 對賬引擎工作中 |
| **學習** | 28% | scanner snapshots active，但 6 表 0 INSERT、5 ML 腳本 silent-unscheduled、replay simulated_fills 是 synthetic_replay tier 不可 ML feed；attribution_chain_ok 過去 24h 35/277,452 真實率 0.013% (CLAUDE.md §三 [42b]) |
| **進化** | 30% | ml_training/ 腳本可手動跑 smoke 通過；canary_promoter 5/4 commit 標 auto-promote deferred；無端到端閉環 |
| **觀察** | 80% | 51 healthcheck active；但 [42] 假綠（settled per-strategy 1.000 vs row-level 0.013% 8000× drift, PA panorama 揭發） |

**加權平均業務可用度 ≈ 58%**（4-24: ~52%；agent_spine 接線 + replay 落地 +6%；fake-live 35%、學習 28%、進化 30% 三大短板未動）。

---

## §6 Capability Matrix（Operator 視角）

| 能做（spec 期望 + IMPL 可用）| 不能做（spec 期望但 IMPL 不可用 / 偏離）|
|---|---|
| Demo + LiveDemo 兩管線 5 策略真實 fills | 5-Agent 鏈端到端真活下單（Executor shadow_mode=true × 3 TOML）|
| Manual GUI 觸發 Layer 2 推理 session（`/api/v1/layer2/run_session`）| Layer 2 自主週期 / event-trigger 推理 |
| Scout 30min 情報注入 + intel produce | DOC-04 tier auto-promotion |
| Rust agent_spine shadow lineage 寫 typed objects（StrategySignal→...→ExecutionReport，Linux 已 PASS objects=290）| MAG-082 Stage 2 24h 窗 PASS（still ACTIVE collecting）|
| Decision Lease Path A IMPL flag flip ON（Linux trade-core）| ExecutorAgent 真消費 Lease（fake-live 上層短路）|
| Replay Lab synthetic_replay tier evidence（REF-20 Sprint A-D closed）| Replay calibrated_replay / counterfactual_replay 真消費（labels 不足 / pricing binding 0 IMPL）|
| Healthcheck 51 check 含 [42b] [45] [51] 三 attribution maturity | LG-5 reviewer audit row 累積（0 row, sibling CC 待 deploy）|
| Demo 7d gross +4.98 USDT (grid only) | 5 策略合計 net positive (合計 7d -6.98 USDT) |
| Live 4 Rust 硬閘門（OPENCLAW_ALLOW_MAINNET / authorization.json HMAC / secret slot / env_allowed）| true-live 流量（0 by design + 8 P0/P1 ACTIVE blocker）|

---

## §7 Top 10 Functional Blocker（按 live 阻擋優先）

1. **Edge net negative**（5 策略 7d gross -6.98）— P0-EDGE-1 ACTIVE，~05-15 P0-3 決策。
2. **5-Agent fake-live shadow=true × 3 TOML**：ExecutorAgent 永 log-only；P1-FAKE-1 W-A 已 DONE smoke 但 TOML 與 cache default 仍 fail-close shadow。
3. **LG-2 H0 production caller** 0% IMPL（P0-LG-1 ACTIVE）。
4. **LG-3 provider pricing binding** 0% IMPL（P0-LG-2 ACTIVE）。
5. **LG-4 supervised-live state machine** 0% IMPL（P0-LG-3 ACTIVE）。
6. **CLAUDE.md §三 lease default OFF stale**：與 Linux runtime `=1` 漂移；FA push back #1。
7. **MAG-082 Stage 2 24h 窗未 PASS**（W-C ACTIVE，readiness=LINEAGE_READY_NOT_WINDOW_PASS）。
8. **est_net_bps 100% NULL writer fix 未 deploy**（FUP-2 commit `34211ab4` E4 待 merge）。
9. **HTTPS deploy + Cookie secure / credential rotation / KYC / runbook**（4 條 P0-OPS-* ACTIVE）。
10. **openclaw_core 9 模組死代碼 sunset decision**（14 天 0 動作；違背 4-24 P2 提案）。

---

## §8 FA Verdict + 對 PM 的 3 條 push back

**Verdict**：**CONDITIONAL HOLD on Live**。系統治理骨架健康（SM-01/02/04 + EX-04 + DOC-01/06/07/08 全 active），但下單真實性（fake-live 35%）+ 學習進化（28%/30%）+ live LG-2/3/4（0%）三層阻 live。最早 live 實際是 2026-06-15 悲觀帶。

**PM Push Back 3 條**：

1. **§三 staleness 防線失效（CLAUDE.md §七 第二條）**：`OPENCLAW_LEASE_ROUTER_GATE_ENABLED` Linux 真值 `=1` vs CLAUDE.md `=0 default OFF` 已超 5 天無 sync（Sprint 3 deploy `0ad79f67` 是 2026-05-03，今天 5-08）。`[33]/[40]/[42b]/5 策略 PnL` 5 個數字也疑似 stale（PM panorama §三 5 個數字 stale 結論）。建議：PM 立即觸發 CLAUDE.md §三 全 sync commit；或考慮把「runtime numerical state」搬出 §三 進入 `passive_wait_healthcheck.py` 自動產生的 status table，§三 只描述「設計意圖」非「runtime 真值」。否則 §七 的 7-day rule 形同空文。

2. **shadow_mode TOML × 3 與 retrofit IMPL 設計矛盾**：Decision Lease Path A retrofit + agent_spine shadow lineage 都 IMPL 完並 flag ON，但 `risk_config_{demo,live,paper}.toml [executor].shadow_mode = true` 同時生效讓下游 Python ExecutorAgent 永遠 log-only。設計意圖必須鎖定為「(a) shadow_mode TOML 是 W-A demo 階段的 fail-close，等 P0-EDGE-1 後 demo 翻 false 啟 shadow→live promotion」**或**「(b) 5-Agent 鏈本來就是 shadow-only 觀察工具，真實下單永遠走 Rust tick_pipeline 直接路徑，蹬 ExecutorAgent 是錯的設計」。**兩者必擇一明確記入 spec**。當前模糊狀態下 (a) 與 (b) 在 git history 都能找到證據，造成 sub-agent 持續誤判。建議補一條 SM-05 或 amendment 說清楚。

3. **openclaw_core 9 模組死代碼 14 天 0 動作 + Layer 2 自主循環無觸發 14 天 0 動作**：4-24 panorama 提的 P2 sunset decision，5-08 沒有任何 progress。**推測 root cause**：P2 在 TODO.md v13 簡化後被 archive 到 `docs/archive/2026-05-07--todo_v12_*archive.md`，實際 dispatch queue 沒人擔（P2-MIG/SEC/REPLAY-* 是 maintenance backlog 而非 sunset 行動）。請 PM 決定：(i) 把 4 個 P2 死代碼 finding（C2/C3/C4/H3+H1）正式排進 dispatch queue；(ii) 或新增 ADR-0015「openclaw_core 9 模組永久 sunset」決議；(iii) 或承認「死代碼長期共存是 OpenClaw 政策」並關閉本類 finding。**模糊狀態下 FA 每輪 panorama 都要重複報告同樣的 dead code，浪費 ~30% audit context。**

---

**FA AUDIT DONE** · 2026-05-08 UTC · Critical 4 / High 11 / Medium 9 / Low 5
