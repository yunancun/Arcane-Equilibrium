---
spec: Sprint 1A-ζ — IMPL Prototype Spike Phase Scope Specification
date: 2026-05-21
author: PA (Project Architect)；本 spec 對 PM push back of「PA 原 Sprint 1A 純 DESIGN 設計」的衍生
phase: Sprint 1A-ζ（critical-path IMPL spike；位於 1A-ε W8.5 之後 / 1B W9 之前；1-2 wall-clock week / 30-50 hr 真實工時 + buffer 後 57-86 hr）
status: SPEC-DRAFT-V0（待 operator review + PM 派 spike sub-agent；不寫 IMPL code、不修 ADR、不修 V112/V106/V107 spec doc）
parent specs:
  - srv/docs/execution_plan/2026-05-20--execution-plan-v5.8.md §2 M1 / §2 M3 / §2 M11
  - srv/docs/adr/0034-decision-lease-layered-approval-lal.md（M1 LAL authoritative source）
  - srv/docs/adr/0036-m8-anomaly-detection-and-m10-tier-d-model-blacklist.md（M3 ↔ M8 amplification cap）
  - srv/docs/adr/0038-m11-continuous-counterfactual-replay-and-liquidations-source.md（M11 治理邊界）
  - srv/docs/governance_dev/amendments/2026-05-21--AMD-2026-05-21-01-autonomy-vs-human-final-review.md（M1 LAL 3/4 manual + M7 14d 50% protected scope）
  - srv/docs/execution_plan/2026-05-21--m1_lal_layered_approval_lease_design_spec.md（M1 module 697 行）
  - srv/docs/execution_plan/2026-05-21--m3_health_monitoring_design_spec.md（M3 module 648 行）
  - srv/docs/execution_plan/2026-05-21--m11_continuous_counterfactual_replay_design_spec.md（M11 module 619 行）
  - srv/docs/execution_plan/2026-05-21--v112_m1_decision_lease_lal_tiers_schema_spec.md（V112 1329 行）
  - srv/docs/execution_plan/2026-05-21--v106_m3_health_observations_schema_spec.md（V106 1087 行）
  - srv/docs/execution_plan/2026-05-21--v107_m11_replay_divergence_log_schema_spec.md（V107 1471 行）
  - srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-21--v58_dispatch_consolidation.md §Sprint 1A-ε + §6 cross-V### dependency graph
  - srv/docs/execution_plan/2026-05-21--v103_v104_linux_pg_dry_run.md（PG empirical apply 範式）
scope: spike scope 規劃 + Acceptance Criteria + Pass/Fail verdict + dispatch plan only — 不寫 V### sql 實檔 / 不寫 Rust skeleton / 不寫 IMPL code / 不修 ADR-0034 / 不修 V112/V106/V107 spec doc / 不派下游 sub-agent / 不 commit
non-scope:
  - 完整 M1/M3/M11 IMPL（走各 module spec §IMPL phase split 在 Sprint 4-8）
  - 完整 V112/V106/V107 production wiring（spike 只 land migration 跟最小 skeleton）
  - 其他 10 module（M2/M4/M5/M6/M7/M8/M9/M10/M12/M13）— 走 Sprint 1B / 2 / 4-10 各自 IMPL phase
  - 完整 Console GUI UI（A3 Sprint 4 起 IMPL；spike 不含）
  - cross-language fixture harness 全套（H-18 H-15 → Sprint 1B+）
---

# Sprint 1A-ζ — IMPL Prototype Spike Phase Scope Specification

## §1 Context + Motivation

### 1.1 PA 原 Sprint 1A 設計（純 DESIGN 鏈）

per `2026-05-21--v58_dispatch_consolidation.md` §2 真實 Sprint 1A 五階段：

| 階段 | 範圍 | 性質 | wall-clock |
|---|---|---|---|
| 1A-α (W0-1.5) | v5.7 12 prefix DONE + 4 follow-up 收口 | DONE | D+1 closure |
| 1A-β (W1.5-3.5) | M1/M3/M6/M7/M11 5 CRITICAL module DESIGN + V106/V107/V110/V112/V113 + ADR | 純 DESIGN，0 IMPL | 2 wall-clock weeks |
| 1A-γ (W3.5-5.5) | M2/M4/M8/M9/M10 5 ADD module DESIGN + V105/V108/V109/V111 + ADR | 純 DESIGN，0 IMPL | 2 wall-clock weeks |
| 1A-δ (W5.5-6.5) | M5/M12/M13 trait stub + ADR-0035/0039/0040 + V114/115/116 reserved | trait stub only，0 IMPL | 1 wall-clock week |
| 1A-ε (W6.5-8.5) | Cross-ADR consistency audit / 12 V### dry-run SOP land / docs index | 純文檔 + integration verify | 1.5-2 wall-clock weeks |

設計 rationale（per `2026-05-21--v58_dispatch_consolidation.md` §5.2 13 module 依賴圖 + §5.3 cross-V###）：
- IMPL 之前先把全 13 module DESIGN spec + 13 V### schema spec + 7 ADR land
- Cross-V### dependency graph + cross-ADR collision audit 兩處安全網
- E1 IMPL 時 spec 不變 → 不需 mid-IMPL re-design
- Sprint 4 first Live 時 governance 全棧穩定

### 1.2 PM push back rationale（spike 必要性）

PM 主會話對 PA 原設計提 4 條 risk push back：

| Risk | 描述 | 證據 |
|---|---|---|
| **R1: 100% design / 0% runtime evidence** | 15 module DESIGN spec + 13 V### schema spec 全 paper exercise；無一條 evidence 證實 IMPL 真實可行 | V112 placeholder v0 反向錯誤已在 spec 文件層 catch（per V112 spec doc §1.1 line 53-68）但**從未在 Linux PG empirical apply 中驗證** |
| **R2: V### 未 PG empirical apply** | 9 個 V### (V105/V106/V107/V108/V109/V110/V111/V112/V113) 全是 SQL 紙稿；無一個跑過 Linux PG dry-run | 對比 V103/V104 已走完 `2026-05-21--v103_v104_linux_pg_dry_run.md` 範式；V055 5-round loop precedent 證明 Mac mock pytest 抓不到 PL/pgSQL runtime semantic |
| **R3: state machine ↔ schema ↔ ADR 三層對齊未 runtime test** | M1 LAL state machine (Rust) ↔ V112 LAL tier 數字方向 (PG CHECK) ↔ ADR-0034 LAL 0-4 對齊矩陣 三層；任何反向錯誤可能要到 Sprint 4 first Live 才暴露 | V112 spec doc 已 catch 反向錯誤但只在文檔層；PG CHECK constraint + Rust state machine code 未實寫 = 仍有 drift 可能 |
| **R4: Sprint 4 first Live 才發現 spec 有錯 → 大幅 rework** | Sprint 4 (W17.5-20.5) 是 first Live 的 hard gate；若那時才暴露 spec 錯誤 → Sprint 4 IMPL 必 freeze → first Live 推遲 → cumulative cost > spike cost 10-100x | 2026-05-02 P0 sqlx hash drift incident 教訓：audit closure SOP 漏 engine restart 實測 → 治本要 `repair_migration_checksum` binary 補 |

### 1.3 Spike 目標

驗證 critical-path 3 個 module（M1 LAL + M3 health + M11 replay）的 DESIGN spec + V### schema spec **真實可 IMPL**，而非紙上得來終覺淺：

1. **三 V### 在 Linux PG empirical apply 跑通**（success + idempotency + engine restart 0 panic）
2. **state machine ↔ schema ↔ ADR 三層對齊**（empirical state transition test + PG CHECK constraint enforce + Rust code 對齊 ADR-0034）
3. **M7 dedup contract empirical verify**（M11 寫 V107 不寫 strategy_lifecycle 真實落地）
4. **amplification cap 24h-suppression empirical fire**（M3 注 fake CPU spike → HEALTH_WARN → 24h cap 真實 suppress 第二個）
5. **cross-language fixture harness 1e-4 容差驗 1 個 metric**（M3 health metric Rust ↔ Python replay）

### 1.4 Spike 非目標（明示）

- **不**做 full IMPL — 各 module 完整 IMPL 走 Sprint 4-8 per module spec §IMPL phase split
- **不**改 V112/V106/V107 spec doc — spec 已 land（V112 1329 行 / V106 1087 行 / V107 1471 行），spike 只引用不修
- **不**改 ADR-0034 / ADR-0036 / ADR-0038 / AMD-2026-05-21-01 — 治理邊界已鎖
- **不**接 production engine 完整 wire — spike skeleton only；wiring 走 Sprint 4-8
- **不**測 LAL 2/3/4 — 只測 Tier 0/1 transition；Tier 2-4 stub
- **不**跑 nightly cron — M11 spike 手動 1 次 trigger，nightly cron 走 Sprint 3 W15-18 Phase A
- **不**測 6 health domain 全套 — 只測 `engine_runtime` 1 domain（CPU + memory + heartbeat）

### 1.5 與 Sprint 1A-ε 的差別

| 維度 | Sprint 1A-ε | Sprint 1A-ζ |
|---|---|---|
| 性質 | 文檔 + integration verify | IMPL spike |
| Owner | TW + PA + R4 + A3 | PA + E1 × 3 + E2 × 3 + E4 + QA |
| 出物 | docs/README index / Cross-ADR audit / 12 V### dry-run SOP doc / GUI helper | 3 V### 真實跑通 PG + Rust/Python skeleton + 5 row PG state transition |
| Wall-clock | 1.5-2w | 1-2w（重疊 cross-ADR 結果） |
| 是否阻 1B | 是（V### dry-run SOP land） | 是（spike pass 才 Sprint 1B M3/M11 early IMPL 開派；spike fail 走 §5 fallback verdict） |

### 1.6 與其他 module spec §IMPL phase 的關係

| Module | spec §IMPL phase | spike 涵蓋 | 後續 |
|---|---|---|---|
| M1 LAL | Sprint 4 LAL 1 IMPL 40-60 hr engineering + 20-30 hr GUI | spike Track A 取 ~10-15 hr Tier 0→1 skeleton subset；不涵蓋 GUI、不涵蓋 Slack notification、不涵蓋 24h undo handler | Sprint 4 W17.5-20.5 full IMPL |
| M3 health | Sprint 2 metric emitter 60-80 hr + SM 40-60 hr / Sprint 5 cascade 40-60 hr + amp cap 20-30 hr | spike Track B 取 ~10-15 hr engine_runtime 1 domain + amp cap fire test subset；不涵蓋 cascade、不涵蓋 alert routing | Sprint 2 / Sprint 5 full IMPL |
| M11 replay | Sprint 3 W15-18 nightly job Phase A 80-120 hr | spike Track C 取 ~10-15 hr 手動 1 次 trigger + 1 種 divergence type subset；不涵蓋 nightly cron、不涵蓋 fixture cache | Sprint 3 full IMPL Phase A |

---

## §2 Spike Scope — 3 Critical-Path Track

### 2.1 Track A: M1 LAL + V112 IMPL spike（最高優先；Sprint 4 first Live 阻塞）

**Why 最高優先**：

- M1 LAL Tier 1 IMPL 是 Sprint 4 first Live 的 hard gate（per ADR-0034 + M1 spec §10）
- V112 placeholder v0 LAL 0-4 數字方向反向錯誤 — 文件層已 catch，但 PG CHECK + Rust code 兩端從未在 runtime apply 驗
- LAL Tier 0 fill query path 接 M7 V113 `learning.decay_signals.RETIRED` blocker（per M7 spec §8）— 兩 V### 必同時 apply 才測得通
- ADR-0034 line 41「數字越大越嚴」+ line 137-143 對齊矩陣 — Rust code + PG CHECK 對齊未 runtime verify = 仍有 drift 可能

**Spike 工作清單**：

| # | Item | Owner | 估時 | 依賴 |
|---|---|---|---|---|
| A1 | V112 Linux PG empirical migration apply（轉 `sql/migrations/V112__lease_lal_tiers.sql` + `sqlx migrate add`） | E1 (rust E1) | 3-4 hr | V112 spec doc full DDL (1329 行) |
| A2 | V112 Linux PG dry-run 跑（per V103/V104 範式：reflection / Guard A / Guard C / idempotency Round 1+2 / engine restart） | E1 + QA | 2-3 hr | A1 done |
| A3 | M1 LAL state machine Rust skeleton（Tier 0/1 transition only；Tier 2-4 stub `unimplemented!()`） | E1 (rust E1) | 3-4 hr | A1 + A2 done |
| A4 | LAL Tier 0 fill query path 接 V113 `learning.decay_signals.RETIRED` blocker（per M7 spec §8） | E1 | 1-2 hr | V113 spec doc + A3 done |
| A5 | empirical state transition test：5 row 走完 Tier 0→1 cycle + clawback TTL（24h undo handler skeleton）真實 fire | E1 + QA | 2-3 hr | A3 done |
| A6 | 驗 ADR-0034 LAL 0-4 數字方向 = 「越大越嚴」PG CHECK constraint enforce + Rust code 對齊（grep + 反向 INSERT attempt 必 RAISE）| E2 + QA | 1-2 hr | A1-A5 done |

**Track A 工時**：**12-18 hr**（含 E1 IMPL + E2 review + QA empirical verify）

**Track A 工件 deliverable**：

- `sql/migrations/V112__lease_lal_tiers.sql` （per V112 spec doc full DDL；MIT 已 land 1329 行 spec；E1 轉 sql file）
- `engine/openclaw_engine/src/governance/lal_state_machine.rs`（Rust skeleton；Tier 0/1 + Tier 2-4 stub）
- `tests/spike_lal_transition.rs`（5 row PG empirical transition test）
- `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-21--sprint_1a_zeta_track_a_acceptance.md`（Acceptance report）

### 2.2 Track B: M3 Health + V106 IMPL spike（中優先；Sprint 5 active monitoring 前置）

**Why 中優先**：

- M3 active monitoring 是 Sprint 2 metric emitter + Sprint 5 cascade IMPL 的 hard gate（per M3 spec §11）
- V106 hypertable + amplification cap column 設計 — 文件層 spec OK，但 hypertable + 7d chunk + 90d retention 在 Linux PG 跑通未驗
- amplification cap 24h-suppression 是 H-11 反向 attack 6 條 mitigation 的核心（per M3 spec §6 + ADR-0036）— 從未 empirical fire test
- 不在 first Live 阻塞 path（first Live 只要 Tier 1 metric emit 就過，cascade Sprint 5 加）

**Spike 工作清單**：

| # | Item | Owner | 估時 | 依賴 |
|---|---|---|---|---|
| B1 | V106 Linux PG empirical migration apply（轉 `sql/migrations/V106__health_observations.sql` + hypertable 7d chunk + 90d retention） | E1 (rust E1) | 3-4 hr | V106 spec doc full DDL (1087 行) |
| B2 | V106 Linux PG dry-run（per V103/V104 範式 + hypertable check `_timescaledb_catalog.hypertable` + compression policy ACTIVE check） | E1 + QA | 2-3 hr | B1 done |
| B3 | M3 4-state ladder Rust skeleton（HEALTH_OK / WARN / DEGRADED / CRITICAL）— 1 domain `engine_runtime` only；其他 5 domain stub | E1 (rust E1) | 3-4 hr | B1 + B2 done |
| B4 | `engine_runtime` domain 接 engine 30s sampling（CPU% + RSS + heartbeat 三 metric；procfs Linux 平台 sysctl Mac fallback per `feedback_cross_platform`） | E1 | 2-3 hr | B3 done |
| B5 | amplification cap Rust enforce 驗（1-anomaly = 1-state-change/24h；per M3 spec §6.2 fail-open prevention） | E1 + E2 | 2-3 hr | B3 done |
| B6 | empirical fire test：inject fake CPU spike 80% × 5min → HEALTH_WARN 升起 → 24h 內 inject 第二個 spike → cap 真實 suppress（不升 HEALTH_DEGRADED） | E1 + QA | 1-2 hr | B3-B5 done |

**Track B 工時**：**13-19 hr**（含 E1 IMPL + E2 amp cap review + QA empirical fire test）

**Track B 工件 deliverable**：

- `sql/migrations/V106__health_observations.sql`（per V106 spec doc full DDL）
- `engine/openclaw_engine/src/health/state_machine.rs`（Rust skeleton；4 state + dwell time + flap suppression）
- `engine/openclaw_engine/src/health/engine_runtime_domain.rs`（1 domain；CPU + RSS + heartbeat sampling）
- `engine/openclaw_engine/src/health/amplification_cap.rs`（24h suppression Rust enforce）
- `tests/spike_health_amp_cap_fire.rs`（empirical fire test）
- `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-21--sprint_1a_zeta_track_b_acceptance.md`

### 2.3 Track C: M11 Replay + V107 IMPL spike（低優先；Sprint 3 nightly active 前置）

**Why 低優先**：

- M11 nightly cron 在 Sprint 3 W15-18 Phase A 才上線（距當前 ~14 weeks）
- M11 是 sensor（divergence detector + signal emitter），不是 actuator — first Live 不阻塞
- M7 dedup contract 是 CR-7 single decay authority 核心紀律（per V107 spec §1.2 + M11 spec §1.2）— **這條反而值得早驗**因為一旦 spec 留漏洞 → IMPL 走偏難回頭

**但仍 worthwhile 因為**：

- V107 Guard A forbidden field 是 hard contract（per V107 spec §5.1 line 449-461 grep 6 個禁忌字段）— PG empirical apply 驗 forbidden field RAISE 真實 fire
- M11 → M7 dedup contract 從未 runtime test；spec 文件層 verify 不夠
- divergence type 7 種 spec 內 1 種（fill_chain count delta）跑得通其他大概率也通

**Spike 工作清單**：

| # | Item | Owner | 估時 | 依賴 |
|---|---|---|---|---|
| C1 | V107 Linux PG empirical migration apply（轉 `sql/migrations/V107__replay_divergence_log.sql` + Guard A forbidden field check） | E1 (rust/py E1) | 3-4 hr | V107 spec doc full DDL (1471 行) |
| C2 | V107 Linux PG dry-run + Guard A forbidden action column RAISE 驗（grep 6 個禁忌字段：`auto_demote / target_state / decay_recommendation / demote_proposal_id / decay_stage / stage_demoted`） | E1 + QA + E2 | 2-3 hr | C1 done |
| C3 | M11 nightly replay Python skeleton（不真 nightly cron；手動 1 次 trigger；scope 限 1 strategy × 1 symbol × 1 day） | E1 (py E1) | 3-4 hr | C1 + C2 done |
| C4 | 1 種 divergence type（D1 fill_chain count delta）接 `trading.fills` query | E1 | 1-2 hr | C3 done |
| C5 | M7 dedup contract empirical verify：M11 寫 V107 後 driver query verify 不寫 `learning.decay_signals`（per M7 V113）— grep V107 INSERT + grep 0 `learning.decay_signals` write | E2 + QA | 1-2 hr | C3 + C4 done |
| C6 | empirical fire test：inject 1 synthetic divergence（fake fill chain count delta = 5）→ V107 row 寫入 + `flag_action_taken = 'm7_decay_candidate'` backfill + grep M7 signal source 5 觸發（per V107 spec §5.1 H-11 #2 mitigation） | E1 + QA | 1-2 hr | C3-C5 done |

**Track C 工時**：**11-17 hr**（含 E1 IMPL + E2 dedup contract review + QA empirical fire test）

**Track C 工件 deliverable**：

- `sql/migrations/V107__replay_divergence_log.sql`（per V107 spec doc full DDL）
- `python/openclaw/m11_replay/spike_trigger.py`（手動 1 次 trigger；不接 cron）
- `python/openclaw/m11_replay/divergence_d1_fill_chain.py`（1 種 divergence type）
- `tests/spike_m11_m7_dedup_contract.py`（empirical dedup verify）
- `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-21--sprint_1a_zeta_track_c_acceptance.md`

### 2.4 三 Track 共同 deliverable

- `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-21--sprint_1a_zeta_spike_overall_acceptance.md`（合併報告 + PASS/FAIL verdict + operator decision 點）
- `docs/execution_plan/2026-05-21--sprint_1a_zeta_lessons_learned.md`（如 spike 過程 catch 任何 spec gap → 列為 Sprint 1B 補位 candidate）

---

## §3 IMPL Phase Split — 3 sub-phase per track

每 track 走 3 sub-phase；3 track 各自獨立但共用 Phase 1 PA refine + Phase 3 QA/TW closure。

### 3.1 Phase 1 — PA design refine + cross-check（4-6 hr per track / 12-18 hr total）

PA 工作（single-thread；不派 sub-agent）：

| # | Item | 工時 | 依賴 |
|---|---|---|---|
| P1-1 | spike scope cross-check ADR-0034 / ADR-0036 / ADR-0038 / AMD-2026-05-21-01 — 確保 spike scope 不違背任何治理邊界 | 2 hr | 本 spec land |
| P1-2 | spike scope cross-check V112 / V106 / V107 spec doc — 確保 spike SQL 與 spec full DDL 完全對齊 | 2 hr | 本 spec land |
| P1-3 | spike scope cross-check cross-V### dependency graph（per `2026-05-21--v58_dispatch_consolidation.md` §6）— 確保 V112 / V106 / V107 sequencing 不撞 race | 1 hr | 本 spec land |
| P1-4 | 派發 packet 撰寫 3 份（E1 Track A / B / C 各一份；含 acceptance gate + cross-V### dep + Rust/Python module path 預先拆 sibling per H-19） | 3-6 hr | P1-1/2/3 done |

**Phase 1 deliverable**：3 個 E1 dispatch packet + 1 個 cross-check audit memo

### 3.2 Phase 2 — E1 IMPL × 3 track（10-15 hr per track / 30-45 hr 並行）

E1 工作（3 並行 sub-agent；wall-clock 2-3 days）：

per Track A / B / C §2.1-2.3 工作清單；3 並行 sub-agent 各自獨立 IMPL。

**Sequential constraint within track**：
- Track A：A1 → A2 → A3 + A4 + A5（並行）→ A6
- Track B：B1 → B2 → B3 + B4（並行）→ B5 → B6
- Track C：C1 → C2 → C3 → C4 + C5（並行）→ C6

**Cross-track constraint**（per `2026-05-21--v58_dispatch_consolidation.md` §6 cross-V### dependency graph）：

```
   V112 (M1 LAL)  ── independent ──  V106 (M3 health)
                                      │
                                      ▼
                                    V107 (M11 replay)  ── soft dep on V113 ──
                                      │                     (placeholder FK)
                                      └─── Guard A forbidden field check ───
```

- V112 (Track A) + V106 (Track B) 可完全並行（無 cross dep）
- V107 (Track C) 對 V113 是 placeholder soft FK（per V107 spec §2.5）— V113 spike 階段不涉，C1 不阻
- V107 對 V103 是 nullable hard FK（per V107 spec §2.6）— V103 已 Sprint 1A-α land，C1 可進

**Network race mitigation**（per `2026-04-23` multi-session memory race 教訓）：
- 3 sub-agent dispatch 走 sequential `git fetch` + `git branch -r | grep <topic>` 後派發（per `feedback_fetch_before_dispatch`）
- 派 sub-agent 時帶 `--worktree=<unique>` 隔絕 race
- 任一 sub-agent disconnect → 接手 sub-agent 必走 commit-first / 不認識改動禁 revert / memory log 三連檢查

### 3.3 Phase 3 — E2 review + E4 regression + QA empirical + TW report（4-6 hr per track / 12-18 hr total）

| # | Item | Owner | 工時 |
|---|---|---|---|
| P3-1 | E2 對抗 review × 3 track（per Track A/B/C；高風險 IMPL per `feedback_impl_done_adversarial_review` 強制） | E2 × 3（並行） | 12-18 hr |
| P3-2 | E4 regression（pytest + cargo test --workspace + cross-language 1e-4 fixture 1 個 metric） | E4（single） | 4-6 hr |
| P3-3 | QA empirical verify（5 row PG transition / amp cap fire / dedup contract） | QA（single） | 4-6 hr |
| P3-4 | TW spike acceptance report（含 Lessons Learned + Track A/B/C 各自 Acceptance + 合併 verdict）| TW（single） | 2-3 hr |
| P3-5 | PM sign-off（PASS / FAIL verdict + operator decision routing） | PM（single） | 1-2 hr |

---

## §4 Acceptance Criteria（8 條）

| # | AC | 驗收方式 | Sign-off owner |
|---|---|---|---|
| **AC-1** | **V112 / V106 / V107 三 V### 在 Linux PG `_sqlx_migrations` 顯示 success=t** | `ssh trade-core` + `psql -c "SELECT version, success, execution_time FROM _sqlx_migrations WHERE version IN (112,106,107)"` | QA |
| **AC-2** | **三 V### Round 1 + Round 2 idempotency 跑 0 RAISE** | 第二次跑 `cargo run --release --bin sqlx_migrate -- run` 必 0 RAISE；對齊 V103/V104 dry-run 範式 | QA |
| **AC-3** | **三 V### engine restart 跑 0 panic**（per 2026-05-02 sqlx hash drift incident 教訓） | `bash helper_scripts/restart_all.sh --rebuild` 後 `journalctl -u openclaw_engine --since '10 min ago' \| grep -c panic` = 0 | QA + E3 |
| **AC-4** | **M1 LAL Tier 0→1 transition cycle 真實 fire** — 5 row 走完 Tier 0 → Tier 1 升階（eligibility 模擬 PASS）→ Tier 1 active → 5-gate kill 模擬 → Tier 1 demoted；**+ ADR-0034 LAL 0-4 數字方向 PG CHECK + Rust code 對齊**（反向 INSERT `lal_level=-1` 必 RAISE；Rust `LalTier::from(5)` 必 panic）| `cargo test --release --features spike test_lal_transition_cycle` + grep RAISE message | E4 + QA |
| **AC-5** | **M3 amplification cap 24h-suppression empirical fire** — inject fake CPU spike → HEALTH_OK → HEALTH_WARN（dwell time 60s pass）；24h 內 inject 第二個 spike → cap 真實 suppress（不升 HEALTH_DEGRADED）；驗 `learning.health_observations.amplification_loop_24h_count` 寫入正確 | `cargo test --release --features spike test_amp_cap_24h_fire` | E4 + QA |
| **AC-6** | **M11 → M7 dedup contract empirical verify** — M11 manual trigger 寫 V107 row（`flag_action_taken='m7_decay_candidate'`）；driver query 驗 `learning.decay_signals` 0 row 寫入；grep V107 schema 6 個禁忌字段 = 0 hit | `python tests/spike_m11_m7_dedup_contract.py` + `grep -E '(auto_demote\|target_state\|decay_recommendation\|demote_proposal_id\|decay_stage\|stage_demoted)' sql/migrations/V107__replay_divergence_log.sql \| wc -l` = 0 | E2 + QA |
| **AC-7** | **cross-language 1e-4 fixture pass**（M3 health metric Rust ↔ Python replay） — 1 個 metric `engine_cpu_pct` 算 5 sample window mean / sigma 在 Rust 跟 Python replay 端誤差 < 1e-4 | `pytest tests/spike_cross_lang_fixture.py -k cpu_pct_window` | E4 |
| **AC-8** | **spike Acceptance Report TW write + PM sign-off** | `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-21--sprint_1a_zeta_spike_overall_acceptance.md` exists + PM sign-off section | TW + PM |

### AC-1.1 ADR-0034 LAL 0-4 數字方向 PG CHECK + Rust assert（Phase 1 PA Refine append per P-8 patch）

**對齊源頭**：ADR-0034 line 41「數字越大越嚴」+ line 137-143 對齊矩陣 + V112 spec doc §2.2 5 tier_name enum `LAL_0_AUTO / LAL_1_LIGHT_REVIEW / LAL_2_FULL_REVIEW / LAL_3_OPERATOR_APPROVAL / LAL_4_OPERATOR_ATTESTATION`。

**SQL 反向 INSERT 測試**：

```sql
-- SQL test 1: lal_level = -1 反向 INSERT 必 RAISE (CHECK tier_level BETWEEN 0 AND 4)
INSERT INTO governance.lease_lal_tiers (
  tier_level, tier_name, auto_approve, approval_quorum, clawback_ttl_sec
) VALUES (-1, 'NEGATIVE_TEST', false, 0, 60);
-- expect: ERROR "new row for relation \"lease_lal_tiers\" violates check constraint \"lease_lal_tiers_tier_level_check\""

-- SQL test 2: lal_level = 5 反向 INSERT 必 RAISE
INSERT INTO governance.lease_lal_tiers (
  tier_level, tier_name, auto_approve, approval_quorum, clawback_ttl_sec
) VALUES (5, 'TIER_5_OVERFLOW', false, 0, 60);
-- expect: 同 ERROR
```

**Rust assert 測試**（per Track A A6 + V112 spec §2.2 line 126）：

```rust
// Rust assert 1: LalTier::from_i32(-1) 必 Err / panic
#[test]
fn test_lal_tier_from_negative() {
    let result = LalTier::from_i32(-1);
    assert!(result.is_err(), "expected Err for lal_level=-1, got {:?}", result);
}

// Rust assert 2: LalTier::from_i32(5) 必 Err / panic
#[test]
fn test_lal_tier_from_overflow() {
    let result = LalTier::from_i32(5);
    assert!(result.is_err(), "expected Err for lal_level=5, got {:?}", result);
}

// Rust assert 3: 數字越大越嚴對齊 ADR-0034 line 41
#[test]
fn test_lal_tier_numeric_strictness_order() {
    assert!(LalTier::Auto.numeric_value() < LalTier::LightReview.numeric_value());
    assert!(LalTier::LightReview.numeric_value() < LalTier::FullReview.numeric_value());
    assert!(LalTier::FullReview.numeric_value() < LalTier::OperatorApproval.numeric_value());
    assert!(LalTier::OperatorApproval.numeric_value() < LalTier::OperatorAttestation.numeric_value());
    // 全鏈：0 < 1 < 2 < 3 < 4 = 數字越大越嚴
}
```

**Verify command（AC-4 sub-step）**：

```bash
# PG CHECK 反向 INSERT 驗
ssh trade-core "psql -h 127.0.0.1 -U sandbox_admin -d trading_ai_sandbox \
  -c \"INSERT INTO governance.lease_lal_tiers (tier_level, tier_name, auto_approve, approval_quorum, clawback_ttl_sec) VALUES (-1, 'NEGATIVE_TEST', false, 0, 60);\" 2>&1 | grep -c 'violates check'"
# expect: 1 (CHECK fire 一次)

ssh trade-core "psql -h 127.0.0.1 -U sandbox_admin -d trading_ai_sandbox \
  -c \"INSERT INTO governance.lease_lal_tiers (tier_level, tier_name, auto_approve, approval_quorum, clawback_ttl_sec) VALUES (5, 'TIER_5_OVERFLOW', false, 0, 60);\" 2>&1 | grep -c 'violates check'"
# expect: 1

# Rust assert 驗
cd ~/BybitOpenClaw/srv && cargo test --release --features spike test_lal_tier_from_negative test_lal_tier_from_overflow test_lal_tier_numeric_strictness_order
# expect: 3 tests pass
```

**Sign-off**：E2 review + QA empirical（AC-4 內 sub-gate；AC-4 fail = AC-1.1 fail；無單獨 verdict）

---

### AC-5.1 Mock Time Hook Design — amp cap 24h fire test harness（Phase 1 PA Refine append per P-7 patch）

**對齊源頭**：ADR-0042 Decision 4 amplification cap (1-anomaly = 1-state-change/24h) + M3 spec §3.3 dwell time + flap suppression 設計 + AC-5 24h fire empirical 需求。

**核心挑戰**：empirical test 不能等真實 24h；必須 mock time injection。

**設計選項對比**：

| 選項 | 描述 | 取捨 | PA 推薦 |
|---|---|---|---|
| (a) `mock-instant` crate | Rust ecosystem 第三方 crate；feature flag override `std::time::Instant` | 引入新 dep；ecosystem maturity 中（last update 2024）；feature flag 滲透 production code path 風險 | 不推薦 |
| (b) `tokio::time::pause()` + `tokio::time::advance()` | tokio runtime 內建；不引入新 dep；async runtime mock；feature flag 完全隔絕 production | 限 tokio runtime；M3 state machine 必走 tokio runtime；對齊 engine 主路徑 | **推薦** |
| (c) 自寫 `TestClock` trait + `Arc<Mutex<DateTime>>` | 完全自控；無第三方 dep；但全 state machine code 必加 `clock: Arc<dyn Clock>` 構造參數 | 滲透 production constructor；測試專用代碼污染 production；高風險 | 不推薦 |

**選 (b) tokio::time mock 設計（per Track B B5 + B6）**：

```rust
// engine/openclaw_engine/src/health/state_machine.rs (spike skeleton)
#[cfg(feature = "spike")]
use tokio::time::{pause, advance, Duration};

#[cfg(feature = "spike")]
#[tokio::test(start_paused = true)]
async fn test_amp_cap_24h_fire() {
    // Setup: M3 state machine engine_runtime domain
    let mut sm = HealthStateMachine::new(Domain::EngineRuntime);
    assert_eq!(sm.current_state(), HealthState::Ok);

    // Step 1: 第一個 fake CPU spike 80% × 5min → HEALTH_WARN
    for _ in 0..10 {
        sm.observe(EngineRuntimeMetric { cpu_pct: 85.0, rss_mb: 1500.0, ... });
        advance(Duration::from_secs(30)).await;  // 30s sampling × 10 = 5min
    }
    assert_eq!(sm.current_state(), HealthState::Warn);
    assert_eq!(sm.amplification_loop_24h_count(), 1);

    // Step 2: 跳 24h+1s（mock time hop）
    advance(Duration::from_secs(24 * 3600 + 1)).await;

    // Step 3: 第二個 fake CPU spike → cap 必 suppress（不升 HEALTH_DEGRADED）
    for _ in 0..10 {
        sm.observe(EngineRuntimeMetric { cpu_pct: 85.0, rss_mb: 1500.0, ... });
        advance(Duration::from_secs(30)).await;
    }

    // Assert: 24h 後 cap 重置；第二個 spike 又算「第一次」；不升 DEGRADED
    assert_eq!(sm.current_state(), HealthState::Warn);  // 仍 WARN（dwell time 第二輪 60s pass）
    assert_eq!(sm.amplification_loop_24h_count(), 1);   // cap suppressed second spike
    
    // Step 4: 反向 assert — 24h 內 inject 第二個 spike 必被 suppress
    advance(Duration::from_secs(3600)).await;  // +1h（仍在 24h cap 窗口內）
    for _ in 0..10 {
        sm.observe(EngineRuntimeMetric { cpu_pct: 85.0, rss_mb: 1500.0, ... });
        advance(Duration::from_secs(30)).await;
    }
    assert_eq!(sm.current_state(), HealthState::Warn);  // 仍 WARN 不升 DEGRADED
    assert_eq!(sm.amplification_loop_24h_count(), 1);   // cap suppressed; count stays at 1
}
```

**對齊 M3 spec §3.3 dwell time + flap suppression**：

per M3 design spec §3.3：
- OK → WARN dwell = 60s 持續 WARN-band (30s × 2 sample)
- WARN → DEGRADED dwell = 5min 持續 DEGRADED-band **+ amplification gate PASS**
- 24h 內同 domain DEGRADED ↔ WARN > 2 次 → 自動 lock 至 DEGRADED 直到 4h 全 OK + operator manual override unlock

本 AC-5.1 test：
- step 1 OK→WARN dwell time 60s 對齊 (30s × 10 = 5min > 60s threshold)
- step 2 24h hop 對齊 24h cap reset window
- step 3 cap 仍 suppress 因 `amplification_loop_24h_count = 1` 第二個 spike anomaly_id 相同 (per ADR-0042 Decision 4 `同一 anomaly_id 在 24h rolling window 內最多觸發 1 次 state transition`)
- step 4 反向驗 24h cap 窗口內 cap 真實 fire（不升 DEGRADED）

**Feature flag 隔絕**：

```toml
# engine/openclaw_engine/Cargo.toml
[features]
default = []
spike = []  # spike-only mock time + test harness；不滲透 production binary
```

production build (`cargo build --release`) 不帶 `--features spike` → mock time + test harness 完全不編譯進 binary；0 production code path 污染。

**Verify command（AC-5 sub-step）**：

```bash
ssh trade-core "cd ~/BybitOpenClaw/srv && cargo test --release --features spike test_amp_cap_24h_fire"
# expect: test test_amp_cap_24h_fire ... ok / 0 failure
```

**Sign-off**：E4 regression + QA empirical fire test verify（AC-5 內 sub-gate；AC-5 fail = AC-5.1 fail；無單獨 verdict）

---

**AC pass 規則**：
- AC-1 / AC-2 / AC-3 = 三 V### PG empirical hard gate；缺一即 FAIL
- AC-4 / AC-5 / AC-6 = 三 track 業務邏輯 empirical hard gate；缺一即 partial FAIL（仍可走 §5 FAIL verdict 選項 (b)）
- AC-7 = cross-language fixture proof-of-concept；缺即 partial FAIL（H-18 fixture harness 走 Sprint 1B 全套）
- AC-8 = 報告 + sign-off；缺即流程未完，spike 不算 closure

---

## §5 Spike Pass / Fail Verdict

### 5.1 PASS condition（operator decision needed）

**所有以下條件同時滿足**：

- AC-1 ~ AC-8 全 ✅
- 0 critical schema gap discovered（critical = 必須改 ADR / 改 V### spec doc 才能 IMPL）
- 0 ADR ↔ spec ↔ IMPL 三層不對齊發現（per R3 spike 主要 motivation）
- 0 cross-V### dependency violation（V112 / V106 / V107 之間順序 / FK 軟硬一致）
- spike 報告 + Lessons Learned land
- PM sign-off section 寫 closure verdict

**PASS verdict 後續路徑**（operator 決定）：

- Sprint 1B (W9-11.5) **照原計畫** open — M3 metric emitter early IMPL（per M3 spec §11.1 Sprint 2 60-80 hr 提前 1 個 sprint 跑）+ M11 nightly job spec early review 走 H-18 cross-language fixture harness 全套 IMPL
- Sprint 4 first Live (W17.5-20.5) M1 LAL Tier 1 IMPL 開派 — per M1 spec §10 40-60 hr engineering + 20-30 hr GUI
- **路線不變**；spike 為 Sprint 4 IMPL 提供 runtime confidence baseline

### 5.2 FAIL condition（operator decision needed）

**任一條件觸發**：

- 任一 AC fail
- critical schema gap discovered（e.g., V112 LAL 0-4 數字方向 PG CHECK 設計錯但文件層 catch 不到的 corner case；V106 hypertable 7d chunk 在 Linux PG 跑不通；V107 Guard A forbidden field RAISE 沒 fire）
- ADR ↔ spec ↔ IMPL 三層不對齊發現
- cross-V### dependency 違反（V112 / V106 / V107 sequencing 撞 race）

**FAIL verdict 選項**（operator 三選一）：

| 選項 | 描述 | trade-off |
|---|---|---|
| **(a) 退回 Sprint 1A-γ revise spec + 補完 spec 後 re-spike** | spec doc 修正後重跑 spike；wall-clock +1-2w；保 spec 完整性 | first Live 不延，但 wall-clock cost +1-2w |
| **(b) 接受 spec 有限度 + 加 patch ADR + Sprint 1B IMPL 時補** | 不重跑 spike；issue list 加進 Sprint 1B；接受 partial spec gap | wall-clock 不延，但 Sprint 1B 工時 +20-40 hr；Sprint 4 IMPL 風險仍存 |
| **(c) defer first Live 從 Sprint 4 → Sprint 5 (W21-24) 給 IMPL re-design buffer** | spec 不變，但 first Live calendar +3-4w；IMPL re-design buffer 給 Sprint 4 W17.5-20.5 補 | first Live 延 3-4w；對 P0-EDGE-1 觸發 LiveDemo 降級的可能性增加 |

**PA 推薦預設**：
- 若 fail = 1 個 AC + critical schema gap 屬 V### single fix → **(a) 退回 spec 修正**（cost 可控）
- 若 fail = 多個 AC + ADR-level gap → **(c) defer first Live**（保治理穩定性）
- **(b) 是 worst-case** 因 IMPL 時補 = Sprint 4 IMPL 仍會踩同樣坑

### 5.3 Partial PASS（PA 自決，不需 operator）

**條件**：AC-1 ~ AC-6 全 ✅，但 AC-7（cross-lang fixture）或 AC-8（report timing）partial 達標

**處理**：
- AC-7 partial = H-18 cross-language fixture harness 不卡 Sprint 1B；只把 spike 用的 1 個 metric fixture land
- AC-8 partial = spike 報告 land 但 PM sign-off 延 1-2 day；不阻 1B 派發
- 列入 Sprint 1B 補位 candidate

---

## §6 Dispatch Plan + Workload（30-50 hr 真實 / 57-86 hr 含 buffer / 1-2 wall-clock week）

### 6.1 Per-phase workload table（per Q4a override 2026-05-21 operator sign-off）

| Sub-phase | Owner | 工時 | Sequential or parallel | Wall-clock |
|---|---|---|---|---|
| Phase 0 sandbox + Vault prep（per Q1d + Q2 operator sign-off）| E3 + AI-E (single sequence) | 4-6 hr | single-thread | 0.5 day |
| Phase 1 PA spike refine + 3 dispatch packet | PA (single) | 4-6 hr | single-thread | 0.5 day |
| Phase 2 E1 IMPL × 3 track（Track A / B / C；**強制 sequential V107 → V113 → V112 ordering**）| E1 × 3（sequential per ordering）| **35-55 hr**（Track A 12-18 / Track B 13-19 / Track C **16-27** per Q4a 含 M11 Python skeleton + fill_chain detector empirical）| sequential by V### dep | 3-4 days |
| Phase 3a E2 review × 3 track（並行） | E2 × 3（並行 sub-agent） | 12-18 hr 並行（per track 4-6 hr） | 3 並行 sub-agent | 1 day |
| Phase 3b E4 regression（含 cross-language fixture） | E4 (single) | 4-6 hr | single-thread | 0.5 day |
| Phase 3c QA empirical verify（AC-1..7 driver） | QA (single) | 4-6 hr | single-thread | 0.5 day |
| Phase 3d TW spike acceptance report | TW (single) | 2-3 hr | single-thread | 0.5 day |
| Phase 3e PM sign-off + verdict | PM (single) | 1-2 hr | single-thread | 0.5 day |
| **Total** | – | **66-102 hr（含 buffer + Phase 0 sandbox + Q4a override）** | – | **1.5-2 wall-clock week** |

### 6.1.1 V### Dependency Ordering（Phase 2 強制 sequential per V### FK reference）

per V099-V116 dependency graph (V107 ← V103/V109/V113 / V108 ← V103 / V109 → V112 / V112 → V113 / V105 → V107) + spike Track 對應 V### apply：

```
Phase 2 sequential ordering（避 3 並行撞 FK race）：
  Step 1: Track C  V107 (M11 replay divergence log) PG apply 先（standalone；無 upstream FK dep）
  Step 2: Track A  V113 (M7 decay signals) PG apply 第二（M7 ref V107 m11_replay_divergence_ref UUID placeholder）
  Step 3: Track A  V112 (M1 LAL tiers) PG apply 第三（M1 LAL ref V113 no_incident_check_v113_ref BIGINT FK）
  Step 4: Track B  V106 (M3 health observations) PG apply 第四（standalone；無 upstream FK；可與 Step 2-3 並行 IMPL 但 PG apply 必 sequential）

> Note: V### apply 為 sequential；Rust skeleton IMPL 仍可 3 並行（不撞 PG）
> per Q4a override Track C 含 M11 Python skeleton + fill_chain detector empirical (+5-10 hr) 整合在 Track C 16-27 hr 範圍
```

### 6.2 真實 wall-clock 預測（per Q4a override + V### ordering）

```
D0 (派發日 -0.5)   : Phase 0 sandbox + Vault prep (4-6 hr E3 + AI-E sequential)
D0.5 (派發日)      : Phase 1 PA spike refine + 3 dispatch packet (4-6 hr)
D1-D4 (4 days)     : Phase 2 E1 IMPL — V### apply sequential (V107 → V113 → V112 → V106) + Rust skeleton 3 並行 (35-55 hr / wall-clock 3-4 days)
D5 (1 day)         : Phase 3a E2 review × 3 並行 sub-agent (12-18 hr 並行 / wall-clock 1 day)
D6 (0.5 day)       : Phase 3b E4 regression (4-6 hr)
D6 (0.5 day, 並行) : Phase 3c QA empirical (4-6 hr)
D7 (0.5 day)       : Phase 3d TW report + Phase 3e PM sign-off (3-5 hr)
─────────
合計 wall-clock    : 1.5-2 wall-clock week（D0-D7 約 1.5 week 紧型；含 buffer 達 2 week）
```

### 6.3 並行 sub-agent ceiling check

per `project_multi_session_memory_race` + `2026-04-23` multi-session memory race 教訓：

- 7 sub-agent + PM hands-on 是 hard ceiling
- 本 spike 3 並行 E1 + 3 並行 E2 = 6 sub-agent / 但**不同步**（E1 在 Phase 2、E2 在 Phase 3a）→ 不撞 ceiling
- Phase 3b/c/d/e 全 single-thread → 0 race

### 6.3.1 Multi-Session Race Mitigation SOP（Phase 1 PA Refine append per P-9 patch）

派 3 並行 E1 sub-agent 前 SOP（per `feedback_fetch_before_dispatch` 2026-04-24 memory + `project_multi_session_memory_race` 2026-04-23 教訓）：

**Pre-dispatch fetch check**（每次派 sub-agent 前 PM 必跑；Phase 2 Track A/B/C 各一次）：

```bash
# 在 Mac CC dev session（PM 主會話）跑
git fetch origin
git branch -r | grep -E "(spike|zeta|sprint_1a)"
# 確認無 cross-session 撞點 branch（如 origin/feature/sprint_1a_zeta_track_a 已存在 = 隔壁 session 已開）

# 在 Linux trade-core runtime 跑同步驗
ssh trade-core "cd ~/BybitOpenClaw/srv && git pull --ff-only && git status --short --branch"
# 確認 Mac SSOT 與 Linux runtime branch / commit 同步；無 untracked dirty
```

**Stagger 5 min dispatch 順序**（避同時 3 並行派發撞 git index race）：

```
[T+0 min]   PM 派 Track A E1 sub-agent（V107 → V113 → V112 IMPL）
[T+5 min]   PM 派 Track B E1 sub-agent（V106 standalone IMPL）
[T+10 min]  PM 派 Track C E1 sub-agent（V107 已先 land 過；接 Python skeleton + fill_chain detector）
```

每個 sub-agent dispatch packet 帶獨立 `working_branch` hint（避撞）：
- Track A: `feature/sprint_1a_zeta_track_a_m1_lal`
- Track B: `feature/sprint_1a_zeta_track_b_m3_health`
- Track C: `feature/sprint_1a_zeta_track_c_m11_replay`

**Disconnect 接手三連檢查**（任一 sub-agent disconnect mid-IMPL → 接手 sub-agent 必跑；per `project_multi_session_memory_race`）：

```bash
# 1. memory log 檢查（前任 E1 是否寫過 memory 條目？）
ls -la ~/.claude/projects/-Users-ncyu-Projects-TradeBot/memory/ | head -5
grep -l "sprint_1a_zeta" ~/.claude/projects/-Users-ncyu-Projects-TradeBot/memory/*.md

# 2. git log 檢查（前任 E1 是否 commit 過？）
git log --oneline --since="2 days ago" --all | head -10
git log --oneline feature/sprint_1a_zeta_track_<a|b|c>* 2>&1 | head -5

# 3. TODO entry 檢查（前任 E1 是否在 TODO 寫過 active blocker？）
grep -c "sprint_1a_zeta" /Users/ncyu/Projects/TradeBot/srv/TODO.md
```

**任一檢查發現前任工作 → 接手必走 commit-first / 不認識改動禁 revert**（per `project_multi_session_memory_race` 2026-04-23 教訓）。

**7 sub-agent ceiling check**（每次 dispatch 前 PM 確認）：

| 階段 | 並行 sub-agent | 主會話 | ceiling 余量 |
|---|---|---|---|
| Phase 0 | 3 (E3 + AI-E + MIT 串行 = 0 並行) | PM | 7/7 |
| Phase 1 | 1 (PA single-thread) | PM | 6/7 |
| **Phase 2** | **3 (Track A/B/C E1 並行)** | **PM** | **3/7** |
| Phase 3a | 3 (Track A/B/C E2 並行) | PM | 3/7 |
| Phase 3b-e | 1 (E4 / QA / TW / PM single 各串行) | PM | 6/7 |

Phase 2 + Phase 3a **不同步**（Phase 2 結束才 Phase 3a 起跑）→ 6 sub-agent / 2 階段 max 3 並行 → **不撞 7 ceiling**。

**反模式**（明示禁止）：
- (a) 3 並行 E1 dispatch 不 stagger → git index race；2026-04-23 memory race 教訓重蹈
- (b) 派 sub-agent 前不 fetch → 隔壁 session 已開同名 branch 撞點（G6-01 教訓）
- (c) Phase 2 結束前同步派 Phase 3a → 撞 7 ceiling + sub-agent 看不到 Phase 2 完整 commit
- (d) 接手 sub-agent 不跑三連檢查 → 前任工作被 revert（2026-04-23 教訓）

### 6.4 Dispatch packet 結構

每個 E1 packet 含：

```
1. Track spec reference (§2.X 工作清單)
2. AC reference (§4 對應 AC-1..7)
3. cross-V### dependency check (per §3.2 sequential constraint)
4. Rust/Python sibling file path 預先拆（per H-19）
5. SOP reference (per V103/V104 PG dry-run protocol)
6. Memory race mitigation (per `feedback_fetch_before_dispatch` + `git commit --only`)
7. Chinese comment mandate (per `feedback_chinese_only_comments`)
8. Acceptance gate (per §4 AC)
9. Disconnect recovery protocol（接手 sub-agent SOP）
```

---

## §7 Risk Mitigation

### 7.1 Network 不穩 sub-agent disconnect（per Sprint 1A-γ saga）

| Risk | Mitigation |
|---|---|
| sub-agent disconnect mid-IMPL | sequential dispatch for IMPL track（3 並行但 dispatch 時 5min stagger）+ checkpoint commit per AC milestone |
| 接手 sub-agent 不認識前任工作 | 接手三連檢查（memory log / git log / TODO entry）+ commit-first 後再動代碼 |
| 多 session memory race | 派 sub-agent 前 `git fetch` + `git branch -r \| grep spike`（per `feedback_fetch_before_dispatch`）|

### 7.2 PG empirical apply 真實會改 Linux DB

| Risk | Mitigation |
|---|---|
| V112 / V106 / V107 apply 污染 production schema | spike 必先在 `_dev_sandbox_dbname`（per CLAUDE.md §六 + `docs/agents/context-loading.md` PG Connection Examples）跑 sub-shell test；passing 才 production DB apply |
| sandbox DB 不存在 / 權限 | PA Phase 1 P1-1 cross-check 階段 verify sandbox DB exists + role 權限 OK；缺即升 BLOCKER E3 補 |
| sandbox sqlx_migrations table 漂移 | spike 後 `DROP TABLE _sqlx_migrations` + `DROP TABLE` 三 V### 對應 table（清 sandbox state）；production DB 不動 |

### 7.3 Engine restart 風險（per 2026-05-02 sqlx hash drift incident）

| Risk | Mitigation |
|---|---|
| `--rebuild` 觸 sqlx hash drift | spike 必先在 sandbox test；passing 才 `ssh trade-core bash helper_scripts/restart_all.sh --rebuild`；失敗即 `cargo run --release --bin repair_migration_checksum --version <N>`（per `project_2026_05_02_p0_sqlx_hash_drift` SOP）|
| engine restart panic | 走 `restart_all.sh --rebuild` 默認帶 `--keep-auth` flag（per `feedback_restart_rebuild_flag_scope`）；panic log grep + journalctl trace |
| panic 後 production trading freeze | spike 安排在 ml_training_maintenance window 外（02:00-04:00 UTC 內不跑 spike apply）+ operator 通報 |

### 7.4 三 track 並行 IMPL E1 race（cross-V### dependency graph 嚴守）

| Risk | Mitigation |
|---|---|
| V112 / V106 / V107 sequencing 撞 race | per §3.2 cross-track constraint；Track A + B 完全並行（無 cross dep）；Track C 對 V103 是 nullable hard FK（已 Sprint 1A-α land）— 可進；對 V113 是 soft FK 不阻 |
| Track A + B 同時 apply V112 + V106 | 都新 table 無 ALTER 衝突；TimescaleDB extension 已 land（V096）；無 race |
| Track C apply V107 後 V108/V113 還沒 land | V107 對 V108/V113 是 soft FK（per V107 spec §2.5）— 不阻 |

### 7.5 Spike 失敗 cascade

| Risk | Mitigation |
|---|---|
| AC-1 / AC-2 / AC-3 fail（PG empirical hard gate） | 立即停 spike；走 §5 FAIL verdict (a) — 退回 Sprint 1A-γ revise spec |
| AC-4 / AC-5 / AC-6 fail（業務邏輯 hard gate） | 走 §5 FAIL verdict (a) 或 (b)；視 fail 範圍 |
| AC-7 fail（cross-language fixture） | 走 §5.3 Partial PASS；H-18 fixture harness 延 Sprint 1B 全套 IMPL |
| AC-8 fail（spike report 遲交） | 走 §5.3 Partial PASS；PM sign-off 延 1-2 day 不阻 1B |

---

## §8 Cross-ADR / V### / Module Dependencies

### 8.1 ADR 對齊（已 land 不可動）

| ADR / AMD | spike 影響 | 對齊驗收 |
|---|---|---|
| **ADR-0034 (M1 LAL)** | spike Track A 必對齊 LAL 0-4 數字方向（line 41 + line 137-143） | AC-4 反向 INSERT `lal_level=-1` 必 RAISE + Rust `LalTier::from(5)` 必 panic |
| **ADR-0036 (M8 anomaly + M10 blacklist)** | spike Track B 必對齊 amplification cap 1-anomaly = 1-state-change/24h | AC-5 fire test |
| **ADR-0038 (M11 self-hosted PG)** | spike Track C 必對齊 self-hosted only / 3σ 統計 / M7 dedup | AC-6 dedup contract |
| **AMD-2026-05-21-01 (autonomy-vs-human-final-review)** | spike Track A 必尊重 protected scope：M1 LAL Tier 4 manual override 不可繞 / M7 14d×50% mitigation 不可繞 | AC-4 spike 不測 Tier 2/3/4（stub `unimplemented!()`）即合規 |

### 8.2 V### 對齊（已 land spec doc 不可動）

| V### | spike Track | spec doc reference |
|---|---|---|
| V112 (M1 LAL) | Track A | `v112_m1_decision_lease_lal_tiers_schema_spec.md` (1329 行) |
| V106 (M3 health) | Track B | `v106_m3_health_observations_schema_spec.md` (1087 行) |
| V107 (M11 replay) | Track C | `v107_m11_replay_divergence_log_schema_spec.md` (1471 行) |
| V113 (M7 decay) | spike soft ref（Track A A4 + Track C C5）— 不 apply | `v113_m7_decay_signals_schema_spec.md`（待讀；soft FK only）|
| V103/V104 (hypotheses) | spike Track C nullable hard FK 來源 | 已 Sprint 1A-α land |
| V096 boundary（TimescaleDB extension） | spike 三 V### 共同依賴 | 已 land |
| V098 (governance.audit_log) | spike 三 V### 共同依賴 | 已 land |

### 8.3 16 根原則對齊（per CLAUDE.md §二 + DOC-01 V2 §5.1-§5.16）

每 IMPL track 必逐條 cross-check 16 條根原則。spike 範圍 + 對齊重點：

| 原則 | spike 對齊 |
|---|---|
| 1. 單一寫入口 | spike skeleton 不創新 order 寫入口；M11 spike trigger 不發 IPC order intent（per M11 spec §2.1 Stage 3） |
| 2. 讀寫分離 | spike M3 / M11 skeleton 只讀 metric / write audit row；不寫 live trading state |
| 3. AI ≠ 命令 | spike 不涉 AI；LAL state machine 是 pure rule-based |
| 4. 策略不繞風控 | spike 不創新 lease 旁路；LAL gate 仍走 Decision Lease（per ADR-0034 Decision 1） |
| 5. 生存 > 利潤 | spike 不動 5-gate；fail-closed 不變 |
| 6. 失敗默認收縮 | AC-5 amp cap fire 是 fail-open prevention 範例 |
| 7. 學習 ≠ live | spike 不寫 live state；只 V### audit row |
| 8. 交易可解釋 | spike 寫 V### audit row + 5 audit field（created_by/created_at/...） |
| 9. 雙重防線 | spike 不影響 Bybit conditional order |
| 10. 事實 / 推斷 / 假設分離 | spike 報告寫 「empirical evidence = ...」 / 「inferred from = ...」 / 「assumed = ...」三分 |
| 11. P0/P1 內自主 | spike 不擴 P0/P1 邊界 |
| 12. evidence-based 演化 | spike 本身就是 evidence-based 演化的 first step |
| 13. cost 感知 | spike 不增 LLM cost；M11 manual trigger 無 narrative |
| 14. 零外部成本 | spike 全 self-hosted；無 vendor 依賴 |
| 15. 多 agent 形式化 | spike 3 並行 E1 + 3 並行 E2 + 1 QA + 1 TW + 1 PM = 走形式化 chain |
| 16. portfolio > 孤立 trade | spike 不涉 portfolio sizing |

### 8.4 AMD-2026-05-21-01 protected scope 對齊

per AMD-2026-05-21-01 protected scope：

- **M1 LAL Tier 4 manual override 不可繞** — spike Track A 只 IMPL Tier 0/1，Tier 2/3/4 stub `unimplemented!()` → 物理上不可能繞，**合規**
- **M7 14d×50% mitigation 不可繞** — spike Track C 只 IMPL D1 divergence type；M7 dedup contract verify 確保 M11 不寫 `learning.decay_signals` → 不繞 M7 single decay authority，**合規**

---

## §9 Open Questions（≥3 條）

### Q1 [HIGH] Spike 期間 GUI Console 是否需加 spike-mode banner？

**問題**：spike 跑期間，operator 看 Console 可能誤以為 LAL Tier 1 / HEALTH_OK 是 production 真實 state，實際上是 spike skeleton 測試 row。

**選項**：
- (a) Console 加 spike-mode banner（紅底白字「SPIKE MODE — DATA NOT PRODUCTION」） — 需 A3 派 sub-agent 寫 ~2-4 hr GUI patch
- (b) spike 跑期間 Console 暫關（passive_wait_disable Console route） — 需 E1a 改 FastAPI handler ~1-2 hr
- (c) operator 自警覺；spike 跑期間 operator 不看 Console — 0 work；風險：operator 看到誤判
- (d) spike 走 sandbox DB（per §7.2）— Console 連 sandbox DB 不顯示 spike row — 0 額外 GUI work；前提是 Console 配置 production DB only

**PA 推薦**：**(d) sandbox DB 隔絕**（per §7.2）— 0 extra GUI work + 0 operator confusion；operator 看 Console 仍是 production DB 真實 state

**Owner**：operator decide；spike Phase 1 PA refine 階段確認

### Q2 [HIGH] Spike 期間 engine restart 走 `--rebuild` 還是 `--keep-auth`？

**問題**：per `feedback_restart_rebuild_flag_scope`，2026-04-14 後 `--rebuild` 同時重建 engine binary + PyO3；spike 改 V### + Rust skeleton → 必 `--rebuild`。但 spike 是 prototype test → 不影響 authorization → `--keep-auth` 是默認帶的 flag。

**選項**：
- (a) `--rebuild --keep-auth`（默認）— 重建 engine binary + PyO3；保 authorization；建議 default
- (b) `--rebuild`（不帶 --keep-auth）— 重建 + 重簽 authorization；spike 不需 authorization 改動 → 浪費 operator 時間
- (c) 不 restart engine — spike Rust skeleton 不接 production runtime；用 `cargo test --release --features spike` 跑單元測試 → 0 restart 風險
- (d) spike 只跑 Track A/B SQL（V112 + V106 + V107）+ Rust skeleton 在 sandbox CI 跑；production engine 不 restart

**PA 推薦**：**(d) sandbox CI + 0 production restart**（per §7.2 + §7.3）— spike 物理隔絕 production；無 restart 風險；engine restart 走 Sprint 1B（V### 確定通後）

**Owner**：operator decide；spike Phase 1 PA refine 階段確認

### Q3 [HIGH] Spike fail 後是否允許 partial pass + 部分 IMPL？

**問題**：per §5.2 FAIL verdict (b) 「接受 spec 有限度 + 加 patch ADR + Sprint 1B IMPL 時補」— 但這是治理邊界問題：partial pass 等於「明知有 gap 仍進 IMPL」，違反 §二 原則 6「失敗默認收縮」。

**選項**：
- (a) 不允許 partial pass — fail = full re-spike 或 defer first Live；保治理嚴格性
- (b) 允許 partial pass 但限「non-critical gap」 — gap 必 PA + PM 共同 sign-off 「不影響 first Live」才走 1B；criteria 可量化（e.g., gap 涉及 LAL 2/3/4 + M3 cascade + M11 nightly cron → 可 partial；涉及 LAL 0/1 + M3 amp cap + M11 dedup contract → 必 full re-spike）
- (c) 允許 partial pass + 走 §5.2 (b) 補 patch — 每個 gap 開一條 Sprint 1B 子任務；驗收前必補

**PA 推薦**：**(b) 限「non-critical gap」+ PA + PM 共同 sign-off**（折衷方案）— 既不浪費 wall-clock 又不破治理紀律；criteria 必文件化（Phase 3e PM sign-off 階段定義）

**Owner**：operator + PM 共同 decide；spike Phase 1 PA refine 階段確認

### Q4 [MEDIUM] Track C M11 是否 Y2 才 spike（per current Sprint 3 IMPL 距離當前 ~14 weeks 較遠 priority 低）？

**問題**：M11 nightly cron 在 Sprint 3 W15-18 才上線，距 spike 14 weeks；spike 投入 11-17 hr 在 14 weeks 後才用，ROI 可能低於 Track A / B。

**選項**：
- (a) 本 spike 不含 Track C；M11 spec doc verify 走 Sprint 1B（W9-11.5）spec review only；M11 IMPL spike 留 Sprint 3 W14（Phase A 派工前 1 week）跑
- (b) 本 spike 含 Track C — 11-17 hr 早跑早驗 M7 dedup contract（critical 紀律）
- (c) 本 spike 含 Track C 但只跑 V107 PG empirical apply + Guard A forbidden field RAISE（C1 + C2）— 6-7 hr；Phase A skeleton (C3-C6) 延 Sprint 3 W14
- (d) Track C 改 「spec read-only review by PA + E2 對抗審」5-8 hr — 不跑 IMPL；只驗 spec 完整性

**PA 推薦**：**(c) 折衷方案** — V107 PG empirical apply + Guard A forbidden field RAISE 是 6-7 hr critical path；M11 Python skeleton (C3-C6) 延 Sprint 3 W14；spike 工時降 ~5-10 hr / wall-clock 不變

**Owner**：operator decide；spike Phase 1 PA refine 階段確認；若 operator 選 (c) → §6.1 工時表 Track C 改 6-7 hr / total 55-79 hr

### Q5 [LOW] Spike 期間其他 Sprint 1A-ε wave 是否暫停？

**問題**：Sprint 1A-ε wave（W6.5-8.5）含 cross-ADR audit + 12 V### dry-run SOP land + GUI helper；如 spike 走 1A-ε 結尾後新一週，1A-ε 已收口 → 無衝突。但若 spike 與 1A-ε 重疊 → 7 sub-agent ceiling 風險。

**選項**：
- (a) spike 在 1A-ε W8.5 結束後跑 — 0 wave 衝突；wall-clock W8.5-W10
- (b) spike 與 1A-ε 重疊跑 — 風險 7 sub-agent ceiling；wall-clock W6.5-W8

**PA 推薦**：**(a) 1A-ε 後跑** — 嚴守 7 sub-agent ceiling + 0 race；wall-clock W8.5-W10（仍在 Sprint 1B W9-11.5 開派前）

**Owner**：PM decide；Phase 1 PA refine 階段確認

---

## §10 Sign-off Path

### 10.1 Sign-off chain

```
本 spec land (PA design DONE)
        ↓
operator 親手 review + decide §9 open question 5 條 + §5 PASS/FAIL 預先 ack
        ↓
PM 派 PA Phase 1 refine + 3 dispatch packet (4-6 hr)
        ↓
PM 派 E1 × 3 IMPL sub-agent (Track A / B / C 並行)
        ↓
PM 派 E2 × 3 review sub-agent (Track A / B / C 並行)
        ↓
PM 派 E4 regression + QA empirical（single-thread）
        ↓
TW spike acceptance report
        ↓
PM closure verdict（PASS / FAIL / Partial PASS）
        ↓
operator 親手 sign-off Sprint 1B 派發 readiness（per §5.1 PASS condition）
```

### 10.2 Spike report 結構（TW 撰寫）

`docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-21--sprint_1a_zeta_spike_overall_acceptance.md` 應含：

1. **TL;DR**：PASS / FAIL / Partial PASS verdict
2. **AC-1..8 逐條結果**（每條 PASS/FAIL + evidence link）
3. **三 Track Acceptance**（合併 Track A/B/C 各自 acceptance）
4. **Critical gap discovered**（如有；附 ADR / spec doc 影響）
5. **Lessons Learned**（per `2026-05-21--sprint_1a_zeta_lessons_learned.md` 同步）
6. **operator decision routing**（§5 FAIL 三選一 / Partial PASS 自決）
7. **Sprint 1B 派發 readiness gate**（PASS = open / FAIL = block / Partial = conditional）
8. **PM sign-off section**

### 10.3 Lessons Learned 路徑

如 spike 過程 catch 任何 spec gap → 直接列入 `2026-05-21--sprint_1a_zeta_lessons_learned.md`：

- **Spec gap 類** → Sprint 1B 補位 candidate
- **ADR 影響類** → 升 PM + CC 審；可能觸發 ADR amendment
- **Cross-V### dep 漏接類** → 升 PA + E5 補位（cross-V### graph 重畫）
- **Rust ↔ Python IPC schema 不對齊類** → 升 QA + E4 補位（H-13 IPC schema 增量清單擴充）
- **Hard boundary 違反類** → 立即升 CC + operator；spike 停止
- **任何 P0/P1 級** → 自動 escalate 進 TODO §0 active blocker

---

## §11 Appendix — Spike 與其他 governance artifact 的 cross-reference

### 11.1 與 v5.8 §3 Sprint 1A 路徑對齊

per `2026-05-20--execution-plan-v5.8.md` §3 + `2026-05-21--v58_dispatch_consolidation.md` §2：

| 階段 | 狀態 | 本 spike 影響 |
|---|---|---|
| 1A-α (W0-1.5) DONE | PM-signed | 不受 spike 影響 |
| 1A-β (W1.5-3.5) | 派發中 / 部分 land | 本 spike 引用 spec；不重做 |
| 1A-γ (W3.5-5.5) | scheduled | 本 spike 不影響；spike 結果可 feed 1A-γ 加固 |
| 1A-δ (W5.5-6.5) | scheduled | 不影響 |
| 1A-ε (W6.5-8.5) | scheduled | 本 spike 在 1A-ε 後跑（per Q5 PA 推薦） |
| **1A-ζ (W8.5-W10)** | **本 spec 新增** | **新 phase；spike 後決定 1B 派發 readiness** |
| 1B (W9-11.5) | scheduled | spike PASS = open；FAIL = block 或 defer |

### 11.2 與 Sprint 1A-β 已 land artifact 對齊

per Sprint 1A-β 已 land 文件（per 本 spec frontmatter parent specs）：

- M1 LAL design spec (697 行) — 本 spike Track A 引用
- M3 health design spec (648 行) — 本 spike Track B 引用
- M11 replay design spec (619 行) — 本 spike Track C 引用
- V112 schema spec (1329 行) — 本 spike Track A apply
- V106 schema spec (1087 行) — 本 spike Track B apply
- V107 schema spec (1471 行) — 本 spike Track C apply

**所有引用為 read-only**；spike 不修任何 spec doc。

### 11.3 與 16 audit (Sprint 1A-β / γ readiness audit) 對齊

per `2026-05-21--v58_dispatch_consolidation.md` 14 audit verdict：

- 16 CRITICAL must-fix（CR-1..16）— spike 影響 = CR-2 + CR-7 + CR-8 三條的 runtime evidence；其他 13 CR 不受 spike 影響
- 24 HIGH must-fix（H-1..24）— spike 影響 = H-13 (IPC schema) + H-15 (V-MIGRATION-DRY-RUN) + H-18 (cross-lang fixture) 三條；其他 21 HIGH 不受 spike 影響

**spike 不消化 CR / HIGH 條目**；spike 是「對已 land spec 的 runtime evidence verify」性質，不是「修補 spec gap」性質。

---

## §12 Operator Sign-off — 5 Open Q Decisions（2026-05-21）

operator 在 archive §I PM commit 後 2026-05-21 親手回覆 5 Open Q：

| # | Severity | Decision | 理由 |
|---|---|---|---|
| **Q1** | HIGH | **(d) sandbox DB 隔絕**（採 PA 推薦）| 0 GUI work + Console 仍顯示 production；最小 risk |
| **Q2** | HIGH | **(d) sandbox CI + 0 production restart**（採 PA 推薦）| 物理隔絕 production；最 fail-safe |
| **Q3** | HIGH | **(b) spike fail 限「non-critical gap」+ PA+PM 共同 sign-off**（採 PA 推薦）| 折衷 governance；不全有不全無 |
| **Q4** | MEDIUM | **(a) Track C 全跑（不折衷）含 M11 Python skeleton**（operator override PA 推薦 c）| 不在 Sprint 3 才發現 M11 架構問題；Spike 多 5-10 hr 換 14w 早 detect 值得 |
| **Q5** | LOW | **(a) 1A-ε 完才跑 1A-ζ**（採 PA 推薦）| 嚴守 7 sub-agent ceiling + 0 race；wall-clock W8.5-W10 |

**Q4 (a) Override 工時影響**：
- Track C 原 11-17 hr (V107 PG apply + Guard A 驗 + dedup contract 6-7 hr) → Q4 (a) 含 M11 Python skeleton + 1 divergence type fill_chain detector empirical = +5-10 hr
- Track C 新工時：**16-27 hr**（原 11-17 + 5-10）
- Spike 總工時：57-86 → **62-96 hr** 含 buffer
- Wall-clock：1-2 week 不變（Track C E1 仍在 D1-D3 並行窗口內）

**dispatch 順序確認**（per Q5 a）：
- Sprint 1A-δ (M5/M12/M13 stubs) 先派
- Sprint 1A-ε (cross-ADR audit + docs index 補) 後派
- Sprint 1A-ζ (IMPL Spike) W8.5-10 最後派
- 不並行；嚴守 sequential phase

---

**END Sprint 1A-ζ — IMPL Prototype Spike Phase Scope Specification**

**PA DESIGN DONE**: spec path: /Users/ncyu/Projects/TradeBot/srv/docs/execution_plan/2026-05-21--sprint_1a_zeta_impl_spike_scope_spec.md
**Operator Sign-off**: 2026-05-21 — 5 Open Q decided per §12（Q4 a override）
