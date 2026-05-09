# 玄衡 · Arcane Equilibrium — QCTODO（Post 4-Agent Loss Audit Dispatch Queue）

> **PM Sign-off Banner（2026-05-09 UTC）**
>
> - **整合輸入**：PA full dispatch plan (`d3bf7be2`) + FA business-chain validation (`5a2dee98`) + 4-agent loss audit (QC/MIT/PA/FA, 2026-05-09)
> - **派遣依據**：Operator 拍板 5 群（A 新策略 / B ML 三斷層 / C Promotion+Dormant / D Architectural Wave / E G3-08+治理 decision）
> - **PM Sign-off Verdict**：**ACCEPTED with 1 PENDING-OPERATOR**（Sprint N+0 5/5 HOT capacity risk acknowledgement, 見 §5）
> - **與 srv/TODO.md 隔離**：QCTODO 是新檔，**不動 TODO.md**（隔壁 session 修 P0 dirty file）；Sprint N+0 結束後 PM 將 QCTODO 內容 merge 進 TODO.md（隔壁 session 完成後）
> - **規模**：6 sprint × ~12 weeks → first per-alpha-source supervised live；~140 person-day across E1×5
> - **A2-followup 已 DONE**：G3-08 `OPENCLAW_H_STATE_GATEWAY=1` enable + cost_edge_advisor daemon spawned (2026-05-09 17:27 UTC)

---

## §1 6-Sprint Dispatch Roadmap（PA + FA 整合）

| Sprint | Week | 主題 | E1 capacity | Critical path | Business chain milestone (FA) |
|---|---|---|:---:|---|---|
| **N+0** | W1-W2 | **FOUNDATION HEAVY**: W-AUDIT-9 + 8a Phase A + B 群 + C-A6 + 6 mid-ground | **5/5 HOT** ⚠️ | W-AUDIT-9 + 8a Phase A 序列化（共 file 衝突）| 63→65% |
| **N+1** | W3-W4 | ALPHA SURFACE PANEL WIRING: 8a Phase B+C 並行 + A4-C spec + Stage 1 cohort 7d 觀察 | 4/5 | 8a Phase B+C 並行 | 65→70% (Stage 1 standalone +5-7%) |
| **N+2** | W5-W6 | A4-C IMPL + 8a Phase D + Stage 2 demo cohort 14d | **5/5 HOT** ⚠️ | A4-C IMPL | 70→76% |
| **N+3** | W7-W8 | A4-B IMPL + R-2 spec + Stage 3 demo full | 4/5 | A4-B IMPL | 76→80% |
| **N+4** | W9-W10 | R-3 spec + A4-A IMPL + 8e IMPL + Track W 收尾 | 4/5 | 8e IMPL | 80-83% |
| **N+5** | W11-W12 | R-3 IMPL + R-4 spec + **first per-alpha-source supervised live** | **5/5 HOT** ⚠️ | first per-alpha-source live | **85-89%** |

詳：`srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-09--full_dispatch_engineering_plan.md` §1 / FA report §1

**最早 supervised live 規劃帶**（FA 業務鏈視角概率）：
- 6/15 樂觀（業務鏈 75%+）：~30%
- 6/30 中位（業務鏈 80%+）：~40%
- 7/15 悲觀（業務鏈 85%+）：~25%
- 8/15 極悲觀：~5%

---

## §2 Confirmed Dispatch List（Operator 拍板，不容變更）

### A 群 — Alpha 升級 3 候選（PA spec phase 並行 → IMPL 順序 C/B/A）

| ID | 主題 | Sprint | Person-day | Owner |
|---|---|---|---:|---|
| A4-C | BTC→Alt Lead-Lag (W-AUDIT-8d) | N+1 spec → N+2 IMPL | 7 | E1 + QC review |
| A4-B | Liquidation Cluster Reaction (W-AUDIT-8c) | N+2 spec → N+3 IMPL | 1.5 sprint | E1 (Rust hot-path) + QC + BB review WS |
| A4-A | Funding Skew Directional (W-AUDIT-8b) | N+3 spec → N+4 IMPL | 1 sprint | E1 + QC + MIT review |

**FA Stage-2 abort gate（必明文記入 Sprint sign-off）**：A4-C 若 Stage 2 demo 14d gross < 0，整個 A 群 8b/c 必須重評，**不可連續 IMPL B/A**。

### B 群 — ML Pipeline 三道斷層（Sprint N+0 並行 dispatch）

| ID | 主題 | Person-day | Owner |
|---|---|---:|---|
| B-M1 | `decision_features` producer 改 intent-only emit + `decision_features_evaluations` 拆表 V0XX migration | 5 | E1 + MIT review V### |
| B-M2 | Fill writer `entry_context_id` INSERT trigger | 0.5 sprint | E1 |
| B-M3 | Governance reject 寫 negative label + class weight handling | 1 sprint | E1 + MIT spec |

**FA Push back（critical）**：6 表 INSERT path **必串行 IMPL**（feature_baselines first → mlde_edge_training_rows → scorer_predictions → 3 advisor 並行）；不可 E1×4 全並行（schema relationship dependency）。

### C 群 — Promotion Gate + Dormant Unlock

| ID | 主題 | Sprint | Person-day | Owner |
|---|---|---|---:|---|
| C-A6 | DSR/PBO/CPCV evidence pipeline 自動化 + `trial_sharpes` 持久化（V079 已 land） | N+0 | 2 | E1 |
| C-D-05-wire | `set_promotion_pipeline()` singleton init | N+0 | 0.5 | E1 (依附 C-A6) |
| C-D-02 | Layer 2 manual 7d 試運行 | operator 自決 | 7d 觀察 | operator + FA SOP §6 |

### D 群 — Architectural Wave

| ID | 主題 | Sprint | Person-day | Owner |
|---|---|---|---:|---|
| W-AUDIT-8a | Alpha Surface Foundation (Phase A → D) | N+0 → N+2 | ~40 (4 phase × 10) | E1 + MIT/QC/CC/BB review |
| W-AUDIT-9 | Graduated Canary Foundation (T1-T7) | N+0 IMPL | 1.5-2 sprint | E1 (5 並行) |
| W-AUDIT-8e (R-2) | Strategist Alpha Source Orchestrator | N+4 spec → N+5 IMPL | 2-3 sprint | E1 + PA spec |
| W-AUDIT-8f (R-3) | Hypothesis Pipeline + W-AUDIT-4 ML 6 dead schema 併入 | N+5 IMPL | 2-3 sprint | E1 + MIT spec |
| W-AUDIT-8g (R-4) | Per-alpha-source Live Promotion Gate | N+7+ defer | 2 sprint | E1 + PA spec |
| W-AUDIT-10 (R-5) | Spec-as-Code + Module Lifecycle SM | defer 中期 | 1-2 sprint | E1 |

**FA Push back（D-08e promote）**：W-AUDIT-8e Strategist→Analyst propose 通道 promote 至 Sprint N+4（與 Track W 收尾並行），不需等 8a Phase A 全 land。

### W-AUDIT-6 Mid-Ground（Sprint N+0 並行，operator 拍板）

**保 6 子項**（Sprint N+0, 5 person-day, QC review）：
1. DSR/PBO 自動化 evidence push（V079 + `promotion_evidence.py`）
2. Kelly RiskConfig SSOT（`per_trade_risk_pct` + Kelly tier）
3. funding_arb retire（4 TOML clean, ADR-0018, ✅ done）
4. portfolio VaR/CVaR/EVT promotion gate（W-AUDIT-6c, ✅ done）
5. `portfolio_var min_observations=200` review + sampling unit 校正
6. bb_reversion verdict（pair MA per AMD-2026-05-09-02 §3）

**砍 6 子項**（**E2 grep blacklist, 命中即 reject merge**）：
1. ❌ ma_crossover 5m 反向觀察重做
2. ❌ bb_breakout Donchian 5m optimization sweep
3. ❌ grid_trading symbol expansion ORDIUSDT → 5
4. ❌ funding_arb v3 MA pair retry
5. ❌ strategy_params 4×5 hardcoded → 動態 Sharpe-by-regime（W-AUDIT-8e 後做更合適）
6. ❌ 5 策略 cost_gate threshold 個別 tune

**DSR multiple testing penalty 量化結論**（必記入 sign-off report）：保 6 K +3 trial / 砍 6 K -15 trial / **Net K -12 trial**；`mu_0 = sqrt(2 × ln(K))` 從 ~2.83 降至 ~2.27 → DSR PASS threshold 對 5 策略 sharpe ~0.5 真實要求降低（FA report §3）。

### E 群 — Operator-decide-only（已拍板）

| Decision | 狀態 | 證據 |
|---|---|---|
| A2-followup G3-08 `OPENCLAW_H_STATE_GATEWAY=1` enable | ✅ DONE | `dddc5dc1` restart_all.sh wire + env file 加 line + 2026-05-09 17:27 UTC restart 確認 daemon spawn (`cost_edge_advisor spawned env=1 phase=B_shadow`) |
| Decision-2 W-AUDIT-6 mid-ground | ✅ confirmed | 保 6 / 砍 6（如上）|
| Decision-3 W-AUDIT-4 併入 R-3 | ✅ confirmed | W-AUDIT-8f 同 wave 做 schema + state machine + 接線 |

---

## §3 Cross-Wave Conflict Resolution（PA §3.3）

| 衝突 | Files | 解 |
|---|---|---|
| **#1** 8a Phase A migration ↔ W-AUDIT-6 mid-ground 5 策略改動 | `bb_breakout/mod.rs` / `ma_crossover/strategy_impl.rs` / `bb_reversion/mod.rs` | **序列化**：先 6 mid-ground，再 8a Phase A |
| **#2** W-AUDIT-9 T3 `shadow_mode_provider` stage-aware ↔ ExecutorAgent shadow_mode 接線 | `executor_config_cache.py` / `executor_agent.py` | T3 結束前 ExecutorAgent shadow=true 不動，T3 land 後 stage-aware reload |
| **#3** W-AUDIT-8a Phase B+C ↔ W-AUDIT-5 性能 wave | `tick_pipeline/mod.rs` | Phase B+C 並行於 N+1，W-AUDIT-5 性能 catch-up 在 N+1 reserved slot |
| **#4** A 群 3 新策略 ↔ W-AUDIT-9 Stage 1 cohort 選擇 | governance/canary | A4-C 用 W-AUDIT-9 Stage 1 paper cohort 入場驗 stage 機制；非 W-AUDIT-9 7 sub-task 完整 land 不啟動 A4-C IMPL |

---

## §4 Sprint N+0 Day-by-Day Dispatch（PA §8）

### Day 0-3 Dispatch（PM 從 QCTODO sign-off 後立即派發）

並行 5 個 E1 + ops：
- `@E1` W-AUDIT-9 T1 Rust schema 升級（並行 `@QC` enum review）
- `@E1` W-AUDIT-9 T2 V### migration（並行 `@MIT` review）
- `@E1` W-AUDIT-9 T3 `shadow_mode_provider` stage-aware
- `@E1` W-AUDIT-9 T6 manual promote Decision Lease
- `@E1` W-AUDIT-6 mid-ground 6 保子項（並行 `@QC` 數學審計）
- `@E1` B-M1 decision_features intent-only emit（並行 `@MIT` review V###）
- `@ops` A2-followup G3-08 ✅ **已 DONE**

### Day 3-5 E2 first-pass

- `@E2` review T1+T2+W-AUDIT-6 mid-G+B-M1
- `@E4` regression schema test

### Day 5-7 Dispatch（W-AUDIT-6 mid-G done 後 8a Phase A 序列化開始）

- `@E1` W-AUDIT-8a Phase A trait 升級 + 5 策略 declare
- `@E1` B-M2 `entry_context_id` INSERT trigger
- `@E1` B-M3 negative label + class weight
- `@E1` C-A6 DSR/PBO evidence pipeline
- `@E1` W-AUDIT-9 T4 healthcheck `[58]`
- `@E1` W-AUDIT-9 T5 GUI surface

### Day 12-14 Full review chain

- `@E2` second-pass review T3+T4+T5+T6+8a Phase A+B-M2+B-M3+C-A6
- `@E4` regression 5-stage transition + byte-diff E2E + B 群 schema + C-A6 DSR/PBO query
- `@QC` 5 策略數學審計 + `AlphaSourceTag` enum 完整性
- `@MIT` V### migration row-rate 估算 + cron install
- `@CC` Scout IPC schema preview（為 Phase D N+2）
- `@BB` Bybit V5 levels 對齊 review（為 Phase C N+1）

### Day 14-15 PM Sign-off Sprint N+0 milestone（跑 §5 16 invariant）

---

## §5 PM Sign-off Pre-flight Checklist（PA 11 + FA 9 整合 deduplicate = 16 unique invariant）

> 任一 FAIL = BLOCKER；不可帶 known-deviation 進 Sprint N+1

### 結構 invariant（5 條）

| # | Invariant | 驗證 | 來源 |
|---|---|---|---|
| 1 | Sprint N+0 W-AUDIT-9 7 sub-task 全 land + `[58]` PASS + `governance.canary_stage_log` active | `git log --grep=W-AUDIT-9` 7 commit + healthcheck PASS | PA-1 |
| 2 | Sprint N+0 W-AUDIT-8a Phase A trait 升級 land + 5 策略 byte-identical replay PASS + `cargo build --release` 綠 | E2E byte-diff test PASS | PA-2 |
| 3 | W-AUDIT-6 mid-ground 6 保子項 land + 砍 6 子項 grep blacklist 0 命中 | grep audit + 6 commit 存在 | PA-3 |
| 4 | W-AUDIT-9 Stage 1 cohort active + 7d wall-clock 觀察期未提前升級（**standalone milestone**，FA 估 +5-7%）| `governance.canary_stage_log` Stage 1 entered_at_ms + auto-promote 條件未提前觸 | PA-4 + FA-Critique-2 |
| 5 | W-AUDIT-4b 6 表 INSERT path 已**串行** IMPL（feature_baselines first → mlde_edge_training_rows → scorer_predictions → 3 advisor 並行）| commit ordering 驗 + schema relationship test PASS | FA-2 |

### 安全 invariant（5 條）

| # | Invariant | 驗證 | 來源 |
|---|---|---|---|
| 6 | DOC-08 §12 9 條安全不變量未違反 | 逐條 grep + healthcheck pass | PA-5 |
| 7 | live boundary 5-gate 所有 stage active 期間未繞過 | LiveDemo authorization.json 簽名+TTL+env_allowed 全 pass | PA-6 |
| 8 | §二 16 根原則合規（especially 1/4/5/6/9）| 逐條 grep + AMD-2026-05-09-03 §6.3 校核 | PA-7 |
| 9 | `shadow_mode_provider` exception path fail-closed Stage 0（**不是** Stage 1）| E2 review T3 + unit test PASS | PA-8 |
| 10 | W-AUDIT-9 Stage 0 binary fail-closed 不變式保留（Live boundary 5-gate / SM-04 ladder / DOC-08 §12 / §二 16 原則 4 範圍均不被 graduated canary 觸碰）| 4 範圍逐條 invariant test | FA-4 |

### 治理 invariant（6 條）

| # | Invariant | 驗證 | 來源 |
|---|---|---|---|
| 11 | `canary_stage_log.decision_lease_id` for `manual_promote` PG NOT NULL 強制 | V0XX migration 含 `CHECK (transition_kind != 'manual_promote' OR decision_lease_id IS NOT NULL)` | PA-9 |
| 12 | healthcheck `[58]` 對 SM-04 ≥ L3 escalate 必 hard FAIL → 觸 stage = 0 rollback | `[58]` IMPL 對 SM-04 L3 邏輯 explicit + unit test PASS | PA-10 |
| 13 | A 群 3 新策略 IMPL 後 `declared_alpha_sources()` 與真實邏輯對齊 | grep 3 新策略 ctor + QC review report sign-off | PA-11 |
| 14 | W-AUDIT-8b/c/d sequence 必含 **Stage 2 abort gate**（C IMPL 後 Stage 2 demo 14d gross < 0 → A 群 8b/c 重評，**不**連續 IMPL）| Sprint sign-off report 明文記入 | FA-5 |
| 15 | D-02 Layer 2 manual SOP 不違反 ADR-0020（manual probe 不可自動化為 cron / event-trigger）| code grep audit | FA-6 |
| 16 | W-AUDIT-6 mid-ground 砍 6 polishing 的 **K -12 trial DSR penalty 量化結論記入 sign-off report**（避免後續 polishing backlog 重新 lobby 時被當「省工時妥協」回擊）| sign-off report 明文 | FA-7 |

### 監督 / record（追蹤項，3 條）

| # | Invariant | 驗證 | 來源 |
|---|---|---|---|
| 17 | F-08 5 ML cron `crontab -e` install + 24h 真 fire 驗 | `[Xc] ml_training_cron_active` healthcheck PASS（A1 cron已 install，等 24h 真 fire）| FA-3（A1 已 partial done）|
| 18 | v2-NEW-1 strategist cap 30%→50% 補 ADR-0021（freedom-not-gate rationale + SM-05 張力 + 50% 偏離監測指標）| ADR-0021 land + commit | FA-8 |
| 19 | 6 表 0 INSERT 18 天無變動 gap 必有 **owner + ETA**（W-AUDIT-4b P1 escalation，非 wave-level ACTIVE/PARTIAL 模糊）| TODO entry P1 標記 | FA-9 |
| 20 | W-AUDIT-3b runtime smoke 已從 Linux 驗（`pytest -k test_executor_fail_closed` + engine restart 後 `[55] chains_with_lease > 0`） | ssh trade-core run + log evidence | FA-1 |

### git status clean 強制（CLAUDE.md §七 P0-GOV-3）

PM Sign-off 前必跑 `git status --porcelain`，對應檔案必 clean。違反 = PM 拒絕 sign-off。

---

## §6 D-02 Layer 2 Manual 7d 試運行 SOP（Operator 自執行，FA 寫）

完整 6 step 見 FA report §2。摘要：

1. **API key 取得**：Anthropic Console → Create Key（命名 `openclaw-layer2-manual-7d-trial`，monthly budget $5）
2. **寫入**：`echo "sk-ant-xxx..." > $OPENCLAW_SECRETS_ROOT/secret_files/anthropic/api_key && chmod 600`
3. **Manual trigger 7d daily**（每天 1 次任意時間）：
   ```bash
   curl -X POST http://localhost:8000/api/v1/layer2/run_session \
     -H "Authorization: Bearer $OPERATOR_TOKEN" \
     -d '{"trigger_kind":"manual_daily_probe","scope":"L1_triage","max_cost_usd":0.50}'
   ```
4. **4 metric 7d 觀察**：cost_today / decisions_assisted / avoided_loss / false_positive_rate
5. **Pass**: alpha > 2× cost + false_positive < 40% + 0 critical incident；**Fail**: alpha < cost OR false_positive > 60% OR ≥1 layer2 建議致 > 5 USDT 虧損
6. **Fail rollback**: `rm api_key && restart_all.sh --keep-auth`

預期 +2-5 USDT/week alpha contribution（保守）。

---

## §7 Push Back / Risk

### PA Push Back（PENDING-OPERATOR）

**Sprint N+0 5/5 HOT capacity = 任一 E1 故障 = 阻塞 critical path**。

**選項**：
- **(a)** Operator 提供 1 stand-by E1（6 並行: 5 active + 1 stand-by）
- **(b)** Operator **顯式 sign-off 接受** 5/5 HOT 風險（任一 E1 故障即 Sprint N+0 延誤 ~1 sprint）

**等 operator 拍板**才能進入 Day 0-3 dispatch。

### FA Push Back（已採納，記入治理）

- **Track W vs Track A 預算**：Track W 92h 是 supervised live 前置門檻，**不能被 Track A lobby 取代**（合規/安全/可觀測 baseline 不可繞）
- **D-02 SOP 預期上限**：+2-5 USDT/week 是保守上限；若 7d < 1 USDT/week 不值人工 fixed cost，建議 abort
- **A/B/C 候選預期**：+3-7% 業務鏈是中位估，新 alpha source **0% PASS 率歷史不支持「三都 PASS」樂觀情境**
- **W-AUDIT-6 砍 6 polishing**：是 DSR 數學意義 right move（K -12），**不是省工時妥協**

### Risk Mitigation 表（PA §3.4 摘要）

| Risk | 觸發 | 對應 |
|---|---|---|
| W-AUDIT-9 T3 stage-aware exception path 翻車 | E2 unit test 不過 | T3 重 IMPL（lose 1-2 day）|
| W-AUDIT-8a Phase A byte-diff fail | E4 E2E 比對失敗 | 5 策略 migration revert + Phase A 重做 |
| W-AUDIT-6 mid-ground 與 8a Phase A 撞牆 | 同 file overlap merge conflict | 序列化（已 §3 衝突 #1） |
| MIT V### Linux PG dry-run fail | PG empirical query 與設計不符 | E1 IMPL 重設計，CLAUDE.md §七 V055 5-round loop 教訓 |
| Stage 1/2 觀察期未到 14d 強行 promote | operator manual_promote 繞 7d wall-clock | invariant #4 + healthcheck `[58]` PG NOT NULL constraint 阻擋 |

---

## §8 References（引用文件絕對路徑）

| Type | Path | Commit |
|---|---|---|
| **PA full dispatch plan** | `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-09--full_dispatch_engineering_plan.md` | `d3bf7be2` |
| **FA business chain validation** | `srv/docs/CCAgentWorkSpace/FA/workspace/reports/2026-05-09--full_dispatch_business_chain_validation.md` | `5a2dee98` |
| PA architectural redesign | `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-09--full_loss_architectural_root_cause_redesign.md` | `ad59765b` |
| QC alpha root cause | (inline in PM session 2026-05-09) | n/a |
| MIT ML data root cause | (inline in PM session 2026-05-09) | n/a |
| FA dormant alpha inventory | `srv/docs/CCAgentWorkSpace/FA/workspace/reports/2026-05-09--full_loss_dormant_alpha_features_inventory.md` | included |
| 4-agent loss audit worklog | `srv/docs/worklogs/2026-05-09--4_agent_loss_audit_and_5_actions.md` | `ad59765b` |
| W-AUDIT-8a spec | `srv/docs/execution_plan/2026-05-09--w_audit_8a_alpha_surface_foundation_spec.md` | `c13c811e` |
| AMD-2026-05-09-03 graduated canary | `srv/docs/governance_dev/amendments/2026-05-09--AMD-2026-05-09-03-graduated-canary-default.md` | `b1891023` |
| AMD-2026-05-09-02 W-AUDIT-6 5 策略 verdict | `srv/docs/governance_dev/amendments/2026-05-09--AMD-2026-05-09-02-...md` | (existing) |
| restart_all.sh G3-08 wire | `srv/helper_scripts/restart_all.sh` engine + API blocks | `dddc5dc1` |

---

## §9 PM Sign-off

**Verdict**: **ACCEPTED with 1 PENDING-OPERATOR**

**Pending decision**:
- Sprint N+0 5/5 HOT capacity risk: operator 必拍板 **(a)** 提供 stand-by E1（6 並行: 5 active + 1 stand-by）OR **(b)** 顯式 sign-off 接受 5/5 HOT 風險（任一 E1 故障 = Sprint N+0 延誤 ~1 sprint）

**Operator 回應後 PM 動作**：
- 拍 (a): 修 §1 capacity row 為 6 並行；§4 Day 0-3 加 stand-by E1 slot
- 拍 (b): 在此 §9 加 operator sign-off line + 接受風險聲明

**PM 簽名**：Claude Opus 4.7（Conductor，主會話 PM）
**日期**：2026-05-09 UTC
**對偶輸入確認**：
- ✅ PA dispatch plan reviewed (commit `d3bf7be2`, 689 lines, §1-§9)
- ✅ FA business chain validation reviewed (commit `5a2dee98`, 8 sections)
- ✅ 16 sign-off invariant deduplicate from PA 11 + FA 9
- ✅ Operator 5 group dispatch list 拍板已記
- ✅ A2-followup G3-08 enable 已驗證 (engine.log `cost_edge_advisor spawned env=1 phase=B_shadow`)

**Operator sign-off line**（待 operator 填）：
- [ ] 接受 (a) 預備 stand-by E1
- [ ] 接受 (b) 5/5 HOT 風險顯式 sign-off
- 簽名：____________
- 日期：____________

---

**QCTODO 維護規則**：
- Sprint N+0 結束後 PM 把 QCTODO §1-§5 內容（含 Sprint N+0 closure milestone）merge 進 `srv/TODO.md`（隔壁 session 修 P0 完後）
- Sprint N+1+ 進度更新追加 §10 Sprint Status Updates section
- Sign-off invariant FAIL 觸發 = 在此檔加 §11 BLOCKER section 即時記入 + push back PA/FA
- 此檔 W-AUDIT-9 + W-AUDIT-8a 完成後 archive 至 `srv/docs/archive/2026-05-XX--qctodo_sprint_n0_n5_archive.md`
