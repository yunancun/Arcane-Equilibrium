# ADR 0044: M7 Decay Detection + Single Decay Authority + DECAY_ENFORCED Lifecycle

Date: 2026-05-21
Status: **Accepted**（v5.8 §2 M7 module ADR 級落地；對應 PA dispatch CR-7 single decay authority + H-11 14d × 50% mitigation + AMD-2026-05-21-01 protected scope）
Operator Sign-off: 2026-05-21（主會話 PM dispatch — v5.8 §2 M7 採 single decay authority + 6 lifecycle FSM；DECAY_ENFORCED 改名為 CR-7 字面跨域碰撞 mitigation）
Related: v5.8 §2 M7 Decay Detection (lines 253-277) / M7 design spec `docs/archive/2026-07-09--execution_plan_v58_closed/2026-05-21--m7_decay_enforced_design_spec.md`（463 行；本 ADR 為其治理層 promotion）/ V113 schema spec `docs/archive/2026-07-09--execution_plan_v58_closed/2026-05-21--v113_m7_decay_signals_schema_spec.md` / M11 threshold M7 dedup decay enforced rename spec `docs/archive/2026-07-09--execution_plan_v58_closed/2026-05-21--m11_threshold_m7_dedup_decay_enforced_rename.md` / ADR-0034 LAL Tier 0 active blocker / ADR-0036 model blacklist (decay signal Sharpe 估計適用) / ADR-0038 M11 replay (字面命名空間分離參考——M11 module 名稱不與 M7 decay 重疊) / AMD-2026-05-21-01 protected scope

## Context

### 起源

v5.8 §2 M7（lines 253-277）列 4 種 decay signal + 6 state lifecycle。Reviewer round-16 + CR-7 共識 catch 三個結構性問題：

1. **M7 / M8 / M11 三 module 各自獨立 decay decision** — 同事件 alert × 2 / alert fatigue / recovery path 模糊
2. **ad-hoc per-strategy decay 評估**（各 strategy 自評 30d Sharpe + drawdown + N consecutive loss）缺統一 governance + audit trail
3. **`STAGE_DEMOTED` 字面跨域碰撞** — 「STAGE」字眼與 AMD-2026-05-15-01 Stage 0R-4 / ADR-0034 LAL 0-4 跨域重疊；SQL `WHERE state = 'STAGE_DEMOTED'` 易與 `stage_history.stage = 'Stage 1'` 邏輯混淆

本 ADR 為 M7 design spec 治理層 promotion + CR-7 single authority 鎖入 + 字面 mitigation。

### 為什麼 single decay authority

| 理由 | 說明 |
|---|---|
| **Traceability** | 任一 demote / retire decision 都能追溯到唯一 `strategy_lifecycle.lifecycle_id`（CR-7 contract）|
| **Dedup** | M11 daily nightly replay divergence event 與 M7 30d Sharpe degradation 在 empirical study 信號重疊 60-70%（QC 5.21 v58 audit Risk 3）→ 各自獨立 demote 等於同事件 alert × 2 |
| **Recovery path clarity** | Single state machine 才能定義「何時 promote 回 NORMAL_LIVE」；多 authority 各自 demote 各自 recovery 邏輯衝突 |
| **Operator 心智負擔** | 5 strategy × 4 signal type × 6 lifecycle state = 120 combinatorial event source；single authority 收斂為 5 × 6 = 30 active state visibility |

### DECAY_ENFORCED rename rationale（per CR-7）

原 v5.8 `STAGE_DEMOTED` 字面含「STAGE」三字，與：

- **AMD-2026-05-15-01 Stage 0 / 0R / 1 / 2 / 3 / 4**（canary promotion gate；策略 promotion 成熟度維度）
- **ADR-0034 LAL 0 / 1 / 2 / 3 / 4**（Decision Lease Layered Approval；批准深度維度）

跨領域字面碰撞風險：

- SQL query `WHERE state = 'STAGE_DEMOTED'` 在 ETL / dashboard 易與 `stage_history.stage = 'Stage 1'` 邏輯混淆
- Multi-agent dispatch reviewer 容易誤把 STAGE_DEMOTED 理解為「降到 Stage X」（兩個正交維度被誤對齊）
- AMD-2026-05-15-01 Stage 0R-4 + ADR-0034 LAL 0-4 已歸範 stage / lease tier 兩個命名空間；M7 必須避開此命名空間（per R4 NEW-H-1 修：ADR-0038 實為 M11 replay，非 stage lifecycle naming 權威）

`DECAY_ENFORCED` 直接對應 M7 decay action 域，無跨域字面重疊，命名級隔離一次到位。

### H-11 amplification + AMD-2026-05-21-01 protected scope

per PA H-11 反向 attack：M7 decay signal 對 alpha-bearing strategy 觸發 DEMOTE_PROPOSED 後直接降級可能造成 over-react；per AMD-2026-05-21-01 autonomy directive，**14d × 50% mitigation** 是 protected scope：

- 任何 demote 必有 14d × 50% 的漸進降級窗口（不可一次性全停）
- Protected scope strategy 必經 LAL Tier 3 operator approve 才能跨 DEMOTE_PROPOSED → DECAY_ENFORCED
- 14d 窗口期間若 signal recovery（rolling Sharpe 回升） → 自動回 NORMAL_LIVE

## Decision

**Proposed**：以下 7 條核心決策鎖入 ADR 級。

### Decision 1 — M7 為 sole decay authority（per CR-7）

| 元素 | 設計 |
|---|---|
| 規則 | 全 system decay decision 集中由 M7 module 主責；M11 / M8 / M2 / M9 **只 emit signal，不寫 `strategy_lifecycle` 表** |
| Signal 來源 | M7 主責 4 signal（Sharpe / Drawdown / OOS / Hit-rate）+ M11 ingest as 5th decay-relevant signal（divergence aggregated） |
| `strategy_lifecycle` 寫入權 | **M7 唯一**；其他 module emit signal 寫到 V113 `decay_signals` 表，由 M7 polling + aggregate 後決定是否寫 lifecycle |
| 反模式 | (a) M11 直接寫 `strategy_lifecycle.state = 'DECAY_DETECTED'`（繞 M7）(b) M8 anomaly burst 直接觸發 demote（無 dedup）(c) per-strategy self-detect 自行 demote（無 audit）|
| 落地 | M7 design spec §2-4 + V113 schema `decay_signals` table + `strategy_lifecycle` table M7 exclusive write |

### Decision 2 — 4 decay signal + M11 ingest as 5th

| Signal | 公式 | Window | Threshold |
|---|---|---|---|
| **A: Sharpe Decay** | `sharpe_30d(t) < baseline_mean - 1.5σ` + 連續 5 trading day confirmation | 30d rolling | per-strategy baseline = expanding mean + 1.5σ |
| **B: Drawdown Widening** | `dd_max_7d(t) > envelope_max_dd × 0.8` (WARNING) / `× 1.0` (CRITICAL) | 7d rolling | Stage 4 envelope max DD（per AMD-2026-05-15-01） |
| **C: OOS Degradation** | `oos_deg = (live_30d_Sharpe - backtest_OOS_Sharpe) / backtest_OOS_Sharpe < -0.6` | 30d live vs 90d backtest | live < 40% × backtest OOS |
| **D: Hit-rate Decline** | `hit_rate_30d(t) < baseline_hit_rate - 1.5σ` | 30d rolling | per-strategy baseline |
| **E: M11 Replay Divergence** (ingest as 5th) | `daily_divergence_aggregate_30d > divergence_threshold` | 30d | M11 source |

**多重檢驗校正**：5 strategy × 90d × 4 signal = 1,800 evaluation；Bonferroni α=0.05/1800=2.8e-5 → 1.5σ trigger 必加 second confirmation（連續 5 trading day 都觸發才 escalate）。

**Signal Sharpe 估計禁用 HMM / GARCH**（per ADR-0036 Decision 1）；採 realized return + bootstrap。

### Decision 3 — 6 lifecycle FSM

| State | 進入條件 | 行為 |
|---|---|---|
| **NORMAL_LIVE** | Default；strategy 正常運作 | 全 LAL Tier autonomy 開放（per ADR-0034）|
| **DECAY_DETECTED** | 任一 signal A-E first confirmation（單 trigger 不需 5-day） | M3 alert WARN；不影響 trading；繼續觀察是否升 DEMOTE_PROPOSED |
| **DEMOTE_PROPOSED** | Signal 連續 5 trading day confirmation OR 多 signal 同時 trigger | M3 alert escalate；LAL Tier 1/2 auto-approve 自動 disable；emit demote proposal 等 operator approve OR 14d × 50% mitigation 自動執行 |
| **DECAY_ENFORCED** | Operator approve OR 14d 自動執行 | Strategy capital allocation × 50%；continue trading at reduced size；14d 觀察是否 RECOVERY |
| **RECOVERY** | 14d × 50% 期間 signal 反向（Sharpe 回升 + drawdown 收斂） | 漸進回升 allocation 至 100%；通過 21d OOS 驗證後回 NORMAL_LIVE |
| **RETIRED** | DECAY_ENFORCED 30d 持續無 RECOVERY OR Operator manual retire | Strategy capital = 0；走 LAL Tier 0 active blocker（per Decision 6）|

**FSM transition matrix**：詳見 M7 design spec §3；本 ADR 只鎖**狀態 + transition 條件**。

### Decision 4 — DECAY_ENFORCED rename rationale（per CR-7）

| 元素 | 規範 |
|---|---|
| 原命名 | `STAGE_DEMOTED`（v5.8 §2 M7 line 264）|
| 新命名 | `DECAY_ENFORCED` |
| Rename 理由 | 字面 mitigation；避 AMD-2026-05-15-01 Stage 0R-4 + ADR-0034 LAL 0-4 字面碰撞；SQL query / dashboard / multi-agent dispatch reviewer 不再誤對齊 |
| Backward compat | V113 schema 新 column 直接用 `DECAY_ENFORCED`；無歷史資料遷移風險（M7 是新 module） |
| 與 stage lifecycle naming 關係 | AMD-2026-05-15-01 Stage 0R-4 規範 stage promotion progress；ADR-0034 LAL 0-4 規範 lease approval tier；本 ADR Decision 4 規範 decay 領域命名；三個正交不衝突（per R4 NEW-H-1 修：原誤 ref ADR-0038；ADR-0038 為 M11 replay 非 stage naming 權威）|
| 反模式 | (a) 保留 `STAGE_DEMOTED` 命名（CR-7 catch 字面碰撞）(b) 改名為 `DOWNGRADED` / `DEPRECATED`（仍含跨域語意）(c) 改名為 M7-specific code（如 `M7_S4`，喪失語義）|
| 落地 | M7 design spec §1.3 + V113 schema column `state ENUM(...)` 不含 STAGE 字眼 |

### Decision 5 — 14d × 50% mitigation（per H-11 + AMD-2026-05-21-01 protected scope）

| 元素 | 設計 |
|---|---|
| 規則 | DEMOTE_PROPOSED → DECAY_ENFORCED 不可一次性全停；必 14d × 50% 漸進降級 |
| 14d 用途 | 觀察期；signal 若反向（Sharpe 回升 + drawdown 收斂）→ 自動回 NORMAL_LIVE；不需 operator 介入 |
| 50% allocation | DECAY_ENFORCED 期間 strategy capital × 50%；continue trading at reduced size；不全停 |
| Protected scope strategy | per AMD-2026-05-21-01 — alpha-bearing strategy 在 protected scope 內必 LAL Tier 3 operator approve 才能跨 DEMOTE_PROPOSED → DECAY_ENFORCED |
| Non-protected strategy | 14d 自動執行；不需 operator approve |
| 14d 為何 14d | (a) 短於 14d → 不夠 signal 反向觀察窗 (b) 長於 14d → 持續虧損 risk 累積過大 (c) 對齊 V113 schema decay_signals 30d window 的 ~半週期 |
| 50% 為何 50% | (a) 全停（0%）= 失去 RECOVERY 觀察可能 (b) 100%（不降）= 違反 H-11 protected scope 紀律 (c) 50% 是 balance |
| 反模式 | (a) 一次性全停（無 RECOVERY 機制）(b) 14d 窗口期間 operator approve 強制 enforce（繞 mitigation；違反 AMD-2026-05-21-01）(c) Protected scope strategy 走自動 14d 不經 operator（違反 protected 紀律）|
| 落地 | M7 design spec §3-4 + V113 schema mitigation_state column + LAL Tier 3 對接 |

**Wave 5 v2 sync（2026-05-28）**：M7 `DECAY_ENFORCED` / `RETIRED` 是 Autonomy Level auto path freeze trigger。Level 2 Standard 不允許繞過 14d × 50% mitigation、RETIRE finality、或 M1 LAL Tier 0 blocker；只在 owning gate 明確允許且 M7 state 非 freeze 狀態時，才可把特定 demote path 交給 fail-safe auto。

### Decision 6 — M7 ↔ M1 LAL：RETIRED → Tier 0 active blocker

| 元素 | 設計 |
|---|---|
| 規則 | `strategy_lifecycle.state = 'RETIRED'` → M1 LAL **Tier 0 active blocker**（per ADR-0034）|
| Tier 0 blocker 行為 | 該 strategy 任何 LAL Tier 任何 lease 全部 reject；包含 per-fill LAL 0；engine 拒絕該 strategy 任何 new intent |
| 為何 LAL 0 也 block | RETIRED 是 final state；per-fill 自主路徑也不應 emit 新 lease；只允許已開倉位走 SL/TP 自然 settle |
| 已開倉位處理 | RETIRED 前已開倉位 → 走 SL/TP 自然退出；不強制平倉（per CLAUDE §四 fail-closed not catastrophic）|
| 反 RETIRE 路徑 | RETIRED → 不自動 revive；必經 LAL Tier 3 operator approve + 30d shadow validation + 新 promotion gate（per AMD-2026-05-15-01 Stage 0R）|
| 反模式 | (a) RETIRED 仍允許 LAL 0 per-fill（破 final state 語意）(b) RETIRED 自動 revive（無 evidence-gated）(c) RETIRED 強制平倉（違反 SL/TP 自然退出 + §四 boundary）|
| 落地 | M7 design spec §5 + ADR-0034 Tier 0 blocker contract |

### Decision 7 — Retirement criteria（M7 module 自身）

| 觸發條件 | Action |
|---|---|
| 4 signal + M11 ingest 5 signal 仍漏抓 alpha-decay 模式（per Y2 末 review） | Amend V113 schema + M7 spec §2；不退役 M7 |
| Single authority 設計反成 SPOF（M7 down → 全 system 失去 decay observability） | 開 ADR amendment 評估 dual-authority hot-standby；M7 本身不退役 |
| 14d × 50% mitigation 在實證下 over-conservative（real edge-loss 在 14d 已 -10%+） | Amend Decision 5 mitigation window / allocation；不退役 M7 |
| Y3+ multi-venue 後 decay 域擴大 | 開新 ADR；M7 升級含 venue-level decay signal |

## Alternatives Considered

| Alternative | 棄因 |
|---|---|
| **保留 M7/M8/M11 各自獨立 decay decision**（v5.7 baseline） | per CR-7 三痛點；alert × 2 + recovery path 模糊 + operator 心智負擔 120 combinatorial |
| **保留 `STAGE_DEMOTED` 命名** | per CR-7 字面跨域碰撞；SQL / dashboard / multi-agent dispatch 風險長期累積 |
| **改名為 `DOWNGRADED` / `DEPRECATED`** | 仍含跨域語意（stage downgrade / module deprecated）；不夠 specific 到 decay 域 |
| **5-state FSM**（合併 DECAY_DETECTED + DEMOTE_PROPOSED） | 失去 「first confirmation 觀察期 vs 5-day confirmation 升級」分離；過早降級風險 |
| **7-state FSM**（加細粒度） | 過度複雜；6 state + protected scope LAL Tier 3 已涵蓋核心場景 |
| **一次性全停**（無 14d × 50% mitigation） | 違反 H-11 protected scope；失去 RECOVERY 觀察可能 |
| **14d 全停（不 50% allocation）** | 同上；continue trading at reduced size 是 evidence accumulation 必要 |
| **RETIRED 仍允許 LAL 0 per-fill** | 破 final state 語意；RETIRED 應為 hard stop |
| **RETIRED 自動 revive after 30d 無新事件** | 違反 evidence-gated；無 new promotion gate 不應自動 revive |
| **Sharpe / Drawdown signal 採 HMM / GARCH 估計** | 違反 ADR-0036 Decision 1 black-list |
| **Decay signal threshold 寫死 magic number** | per `feedback_indicator_lookahead_bias` + walk-forward 紀律；threshold 必 per-strategy baseline + bootstrap |

## Consequences

### Positive

- **單一 decay authority** — 取代 M7/M8/M11 各自 demote 反模式；alert × 2 + recovery path 模糊問題收斂
- **6 lifecycle FSM 完整覆蓋** — NORMAL_LIVE → DECAY_DETECTED → DEMOTE_PROPOSED → DECAY_ENFORCED → RECOVERY / RETIRED 五條轉換路徑全 enumerable
- **字面跨域碰撞零** — DECAY_ENFORCED 命名一次到位；avoid Stage / LAL 字面衝突
- **14d × 50% mitigation 平衡 H-11 protected scope** — 不一次性全停 + 不繼續全速虧損 + 留 RECOVERY 觀察窗
- **與 ADR-0034 LAL Tier 0 完整對接** — RETIRED → Tier 0 active blocker；不繞 LAL gate
- **Protected scope strategy 必 LAL Tier 3 operator approve** — 對齊 AMD-2026-05-21-01 evidence-gated autonomy + operator final review
- **與 M3 Health alert routing 對接** — DECAY_DETECTED → M3 WARN / DEMOTE_PROPOSED → M3 DEGRADED；alert 統一

### Negative / Risk

- **Single authority = 潛在 SPOF** — M7 down → 全 system 失去 decay observability；mitigation = M7 emit heartbeat 到 M3；M7 down M3 升 DEGRADED + alert
- **14d × 50% mitigation 在快速 regime shift 下可能反應慢** — Crypto regime 切換 5-10d；14d 觀察期可能錯過早期止血；mitigation = Decision 7 retirement criteria 允許 amend；多 signal 同時 trigger 可加速跳過 DECAY_DETECTED 直入 DEMOTE_PROPOSED
- **M11 ingest as 5th signal 增加 cross-module dependency** — M11 down 會少 1 signal；mitigation = M11 是 decay-relevant 不是 decay-essential；4 主 signal 仍可獨立 trigger
- **5 strategy × Bonferroni α=0.05/1800=2.8e-5 = z=4.0** — 1.5σ trigger + 5-day confirmation 多重檢驗校正後實際 false positive rate 仍需 Y2 empirical 驗；mitigation = M11 nightly replay 互驗 + M7 design spec §2 多重檢驗章節
- **RETIRED → Tier 0 active blocker = 已開倉位走 SL/TP** — 若 SL/TP 距離過寬，RETIRED 後仍可能繼續累積虧損；mitigation = RETIRED 觸發時 emit alert + operator 可手動 close
- **DECAY_ENFORCED 期間 50% allocation = 50% capacity utilization** — Risk 是 strategy 在 50% 配額下 evidence 收集不夠統計力決定 RECOVERY；mitigation = 14d × 50% 是 baseline；可 amend Decision 5

### 與既存設計協作

| 既存元素 | 與本 ADR 關係 |
|---|---|
| v5.7 baseline per-strategy self-detect | **本 ADR 取代**；per-strategy 不再自行 demote；emit signal 到 V113 由 M7 polling |
| ADR-0034 M1 LAL | **Decision 6 對接**；RETIRED → Tier 0 active blocker；DEMOTE_PROPOSED → Tier 1/2 auto-approve disabled |
| ADR-0036 model black-list | **Decision 2 對齊**；Sharpe / Drawdown 估計不可用 HMM / GARCH |
| AMD-2026-05-15-01 Stage 0R-4 + ADR-0034 LAL 0-4 | **Decision 4 對齊**；stage / lease tier / decay 三領域命名空間分離（per R4 NEW-H-1 修：原誤 ref ADR-0038 stage lifecycle naming）|
| AMD-2026-05-15-01 Stage 0R-4 | **Decision 5 RECOVERY 路徑對接**；RETIRED revive 必經新 promotion gate |
| AMD-2026-05-21-01 protected scope | **Decision 5 對接**；protected scope strategy 必 LAL Tier 3 operator approve |
| M3 Health (ADR-0042) | **DECAY_DETECTED → M3 WARN / DEMOTE_PROPOSED → M3 DEGRADED** alert 統一 |
| M6 Bayesian reward weight (ADR-0043) | **Decision 1 對接**；M7 SUSPENDED → M6 weight=0；M7 NORMAL_LIVE 後 M6 重啟 tuning |
| M9 A/B framework (ADR-0037) | **M7 ↔ M9 dedup**；M9 variant promotion 不繞 M7 lifecycle 評估 |
| M11 continuous counterfactual replay | **Decision 2 對接**；M11 divergence aggregate as 5th signal；M11 不寫 strategy_lifecycle |
| V113 schema spec | 本 ADR 為 V113 設計邊界；V113 spec cite ADR-0044 Decision 1-6 |
| walk-forward-validation-protocol skill | M7 design spec §2 對齊；purge + embargo + DSR + PSR |

## §二 16 根原則合規確認

| # | 原則 | 是否相容 | 說明 |
|---|---|---|---|
| 1 | 單一寫入口 | ✅ | `strategy_lifecycle` 寫入權 M7 唯一；其他 module emit signal 到 V113 |
| 2 | 讀寫分離 | ✅ | M7 是 evaluation 層；不直接寫 trading state |
| 3 | AI 輸出 ≠ 命令 | ✅ | M7 demote 走 lease + LAL gate；不直接執行 |
| 4 | 策略不繞風控 | ✅ | DECAY_ENFORCED 50% allocation 走 Allocator + 5-gate 既有路徑 |
| 5 | 生存 > 利潤 | ✅ | 4 signal 早期偵測 + 14d × 50% mitigation + RETIRED Tier 0 blocker 多層保守 |
| 6 | 失敗默認收縮 | ✅ | Signal 觸發默認往降級方向；RECOVERY 必經 21d OOS 驗證 |
| 7 | 學習 ≠ live | ✅ | Decay signal 是學習；demote action 必經 LAL gate |
| 8 | 交易可解釋 | ✅ | V113 decay_signals + strategy_lifecycle 完整 audit；每次 transition 留 log |
| 9 | 雙重防線 | ✅ | M7 + LAL + Guardian + Local SL/TP 多層 |
| 10 | 分離事實 / 推論 / 假設 | ✅ | Signal metric = 事實；threshold baseline = 推論；FSM transition = governance（假設）|
| 11 | Agent 在 P0/P1 內自主 | ✅ | NORMAL_LIVE 期間 LAL 全 Tier 自主；DECAY_DETECTED+ 階段性收緊 |
| 12 | Evidence-based evolution | ✅ | 4 signal + M11 ingest 從 evidence 演化 lifecycle；不依賴 anecdote |
| 13 | cost 感知 | ✅ | M7 signal 評估 nightly cron；不在 trading hot path |
| 14 | 零外部成本 | ✅ | M7 全 Local + DB；不依賴外部 SRE |
| 15 | Multi-agent formal | ✅ | M7 ↔ M3 ↔ M6 ↔ M11 ↔ LAL 多 contract 明文化 |
| 16 | Portfolio > 孤立 trade | ✅ | Strategy-level lifecycle 影響 portfolio allocation；對齊原則 16 |

## Cross-References

- **M7 design spec**：`docs/archive/2026-07-09--execution_plan_v58_closed/2026-05-21--m7_decay_enforced_design_spec.md`（463 行）
- **V113 schema spec**：`docs/archive/2026-07-09--execution_plan_v58_closed/2026-05-21--v113_m7_decay_signals_schema_spec.md`
- **M11 threshold M7 dedup rename spec**：`docs/archive/2026-07-09--execution_plan_v58_closed/2026-05-21--m11_threshold_m7_dedup_decay_enforced_rename.md`
- **v5.8 §2 M7**：`docs/execution_plan/2026-05-20--execution-plan-v5.8.md:253-277`
- **ADR-0034 M1 LAL**：`docs/adr/0034-decision-lease-layered-approval-lal.md`（Tier 0 active blocker + Tier 3 operator approve）
- **ADR-0036 M8 black-list**：`docs/adr/0036-m8-anomaly-detection-and-m10-tier-d-model-blacklist.md`（Signal 估計禁用 HMM / GARCH）
- **ADR-0038**：`docs/adr/0038-m11-continuous-counterfactual-replay-and-liquidations-source.md`（M11 replay；M7 dedup 對齊參考 — M11 不寫 strategy_lifecycle 走 ingest signal route）
- **AMD-2026-05-21-01**：`docs/governance_dev/amendments/2026-05-21--AMD-2026-05-21-01-autonomy-vs-human-final-review.md`（protected scope + 14d × 50% mitigation）
- **AMD-2026-05-15-01**：`docs/governance_dev/amendments/2026-05-15--AMD-2026-05-15-01-canary-rebase-replay-preflight-demo-micro-canary.md`（Stage envelope + revive 路徑）
- **PA dispatch consolidation report**：`docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-21--v58_dispatch_consolidation.md` §CR-7 + §H-11
- **walk-forward-validation-protocol skill**：`srv/.claude/skills/walk-forward-validation-protocol/SKILL.md`
- **feedback_indicator_lookahead_bias**：`.shift(1)` leak-free 紀律

## Sign-off

| Role | Source | Date | Status |
|---|---|---|---|
| Operator | 主會話 PM dispatch via v5.8 §2 M7 single authority + DECAY_ENFORCED rename + 14d × 50% mitigation | 2026-05-21 | ✅ PROPOSED-pending-commit |
| TW | 本 ADR 起草（M7 design spec 治理層 promotion） | 2026-05-21 | ✅ Drafted |
| QC | 4 signal Sharpe / Drawdown 估計禁用 HMM/GARCH 對齊 + Bonferroni 校正驗 | TBD（Sprint 1A-β） | 🟡 PENDING |
| MIT | V113 schema decay_signals + strategy_lifecycle DDL 對齊 | TBD（Sprint 1A-β） | 🟡 PENDING |
| E1 | M7 module IMPL owner（Sprint 6-8） | TBD（Sprint 6） | 🟡 PENDING |
| E2 | M7 ↔ M1 LAL Tier 0 blocker 對接 + 14d × 50% mitigation 對抗驗 | TBD（Sprint 6-8） | 🟡 PENDING |
| FA | RETIRED → SL/TP 自然退出 vs 強制平倉邊界 review | TBD（Sprint 6） | 🟡 PENDING |
| QA | M7 ↔ M3 ↔ M6 ↔ M11 ↔ LAL 多 contract 字面對齊驗 + DECAY_ENFORCED 字面碰撞 grep 驗 | TBD（Sprint 1A-β） | 🟡 PENDING |
| PM | 14d × 50% mitigation 在 Y1 末 empirical 是否需 amend 仲裁 | TBD（Y1 末） | 🟡 PENDING |

---

*OpenClaw / Arcane Equilibrium ADR-0044 — M7 Decay Detection + Single Decay Authority (per CR-7) + 4 Decay Signal (Sharpe / Drawdown / OOS / Hit-rate) + M11 Ingest as 5th + 6 Lifecycle FSM (NORMAL_LIVE / DECAY_DETECTED / DEMOTE_PROPOSED / DECAY_ENFORCED / RECOVERY / RETIRED) + DECAY_ENFORCED Rename (avoid Stage / LAL 字面跨域碰撞) + 14d × 50% Mitigation (per H-11 + AMD-2026-05-21-01 protected scope) + M7 ↔ M1 LAL Tier 0 Active Blocker on RETIRED (Proposed-pending-commit per 2026-05-21 v5.8 §2 M7 + CR-7)*
