# ADR 0042: M3 Health Monitoring — Single Health Authority + 4-State Ladder + 6 Domain + Amplification / Cascade Cap

Date: 2026-05-21
Status: **Accepted**（v5.8 §2 M3 module ADR 級落地；對應 PA dispatch CR-7 single-authority 系列 + H-11 amplification mitigation）
Operator Sign-off: 2026-05-21（主會話 PM dispatch — v5.8 §2 M3 採「集中健康觀測 + 4 級狀態機 + degradation cascade」治理路徑；M3 design spec 648 行 Sprint 1A-β land 為 ADR 落地證據）
Related: v5.8 §2 M3 Health-Aware Degradation (lines 123-151) / M3 design spec `docs/execution_plan/2026-05-21--m3_health_monitoring_design_spec.md`（648 行；本 ADR 為其治理層 promotion）/ V106 schema spec `docs/execution_plan/2026-05-21--v106_m3_health_observations_schema_spec.md` / ADR-0034 LAL Decision 4 / ADR-0036 M8 anomaly amplification dedup / AMD-2026-05-21-01 autonomy-vs-human-final-review

## Context

### 起源

v5.7 baseline 健康監測散落於三處互不協調的 surface：

| 來源 | 範圍 | 觸發行為 | 問題 |
|---|---|---|---|
| `helper_scripts/canary/engine_watchdog.py` | engine 進程存活 / IPC heartbeat | systemd restart engine | 只看進程不看 pipeline；engine 跑著但 strategy 全 dormant 也不報警 |
| `helper_scripts/db/passive_wait_healthcheck.sh` | DB lock / migration 卡 / writer queue depth | 阻 TODO sign-off | 只在 passive wait 觸發；live runtime stalls 無 active alarm |
| Strategy 內嵌 self-test | per-strategy first-detection / dormant / signal rate | strategy 內 log；不外發 alert | 各策略各做各的；無 cross-strategy 互比；first-detection deadlock 反模式（per `feedback_first_detection_deadlock_pattern`） |
| Bybit retCode fail-closed | per-operation API call | 該次 operation 失敗 + log | 不累積；rolling 失敗率高也不升級為 system-level 退化 |
| Manual operator check via Console | 手動觀察 | 操作員行動 | 依賴 operator 不忘記 + 線上 + 看對 dashboard tab |

v5.8 §2 M3 設計意圖（per v5.8 lines 123-151）：把上述碎片化 healthcheck **集中**到一個 module，加 state machine + degradation cascade + alert routing，**填補「per-operation fail-closed」與「5-gate kill」之間的中間層**。

### 為什麼集中 ≠ 重複 5-gate

5-gate kill criteria（per CLAUDE §四 hard boundary）是 catastrophic-level 防線（真 live 啟動 / Operator role / mainnet 環境 / 簽署 authorization / 環境匹配 五重）。M3 是 **operational degradation** 層次，**HEALTH_CRITICAL ≠ true live kill**：

- 5-gate kill 處理「能不能下單」（authorization / authentication / venue gate）
- M3 處理「下單品質正不正常」（runtime / pipeline / business 三層異常累積）
- HEALTH_CATASTROPHIC 由現有 D2 5-gate kill 觸發（不在 M3 範圍）；M3 4-state ladder 只到 CRITICAL

### Sprint 1A-β CRITICAL 路徑必要性

per PA dispatch consolidation report §Sprint 1A-β + §跨 module dependency：M3 ↔ M1 LAL / M3 ↔ M8 / M3 ↔ M11 三組 integration contract 在 Sprint 1A-β 同時段 land，必須有 ADR 級邊界鎖入「M3 = single health authority」否則 sub-agent dispatch 階段會出現「per-domain healthcheck 各自定 state 語意」的回潮。

### H-11 amplification loop 風險

per PA H-11 反向 attack：M8 anomaly detector 可能在 false-positive burst（如 WS reconnect 觸發 burst 異常）時連續觸發 M3 state degradation → M3 cascade halt 全策略 → trading 全停。**M3 必須有 amplification cap**，否則單一 anomaly source 可在數分鐘內把 system 從 OK 降到 CRITICAL。

## Decision

**Proposed**：以下 7 條核心決策鎖入 ADR 級。

### Decision 1 — M3 為 single health authority

| 元素 | 設計 |
|---|---|
| 規則 | 全 system 健康觀測（process / pipeline / business 三層）集中由 M3 module 接收 + 評級 + 觸發 degradation cascade |
| 取代範圍 | engine_watchdog.py / passive_wait_healthcheck.sh / per-strategy self-test / Bybit retCode 累積評估 — 四 surface 升級為 M3 emitter（**保留既有 fail-closed 路徑**，但 system-level state 由 M3 統一發布） |
| 不取代範圍 | (a) per-operation fail-closed（Bybit retCode！=0 該次 op 仍立即失敗）(b) 5-gate kill（真 live 啟動防線不變）(c) Guardian gate（Decision Lease 風控不變） |
| 反模式（明示禁止） | (a) per-domain 各自定 4-state 語意（HEALTH_DEGRADED 在 A domain 跟 B domain 含義不同）(b) Strategy 自己 emit HEALTH_DEGRADED 直接 trigger system-wide cascade（必經 M3）(c) Bypass M3 直接讀 raw metric 觸發 alert |
| 落地 | M3 design spec §2 6 domain + V106 schema `health_observations` table + `health_state_transitions` table |

### Decision 2 — 4-state ladder（OK / WARN / DEGRADED / CRITICAL）

| State | 語意 | Cascade 行為 |
|---|---|---|
| **HEALTH_OK** | 全 domain 皆 OK band | 正常 trading；M1 LAL 可 auto-approve（per Tier eligibility）|
| **HEALTH_WARN** | 至少 1 domain 在 WARN band 持續 dwell time | Alert routing 升級（Slack notify）；不影響 trading / LAL gate |
| **HEALTH_DEGRADED** | 至少 1 domain 在 DEGRADED band 持續 dwell time | **Strategy Tier 1 reparam halt** + M1 LAL **auto-approve disabled** + **fallback 到 Operator manual approve** + alert escalate |
| **HEALTH_CRITICAL** | 至少 1 domain 在 CRITICAL band 持續 dwell time | **All trading halt** + 已開單位走 SL/TP 自然退出 + 全 alert 升級 + 等待 Operator 介入 |
| HEALTH_CATASTROPHIC | （不在 M3 範圍） | 由 5-gate kill / Operator manual kill 觸發；engine 強制停 |

**Wave 5 v2 sync（2026-05-28）**：HEALTH_DEGRADED / HEALTH_CRITICAL 同時是 Autonomy Level auto path freeze trigger。Freeze 期間不得切到 Level 2，也不得用 Level 2 繞過 M1 LAL、M7 decay、Guardian 或 5-gate；系統行為回到 Level 1 Conservative / operator manual posture。此同步只收緊自主，不改 M3 不繞 5-gate 的 Decision 6。

**Ladder 4 級 + 1 級分離理由**：把 5-gate kill 從 M3 拆出後，M3 ladder 是「漸進降級」治理（每升一級多收一層自主）；CATASTROPHIC 是「立即停車」工程（不在治理層次）。

### Decision 3 — 6 health domain（per V106 schema）

| Domain | 層 | 為何此 domain |
|---|---|---|
| `engine_runtime` | Process | 進程級基線；engine_watchdog 升級 |
| `pipeline_throughput` | Pipeline | WS 訂閱 + IPC 健康；典型異常 WS reconnect 漏訂閱 / IPC 死鎖 |
| `database_pool` | Pipeline | PG 寫入 backlog stall；磁盤滿風險 |
| `api_latency` | Pipeline | 交易所側健康；rate-limit / 5xx / WS 中斷的累積 |
| `strategy_quality` | Business | 策略級活性 + fill 品質；典型異常策略 dormant 不報 / slippage 持續 outlier |
| `risk_envelope` | Business | Portfolio 級風險聚合；與 §16 原則 + 5-gate 既有 kill 邊界協作 |

**3 層分離核心**：Process 層 OK 不代表 Pipeline 層 OK（典型 "engine 跑著但 strategy 全 dormant"）；Pipeline 層 OK 不代表 Business 層 OK（典型 WS 正常 + DB 正常 + strategy 全虧）。

Threshold 數值列入 V106 spec `regime_threshold_table`（per ADR-0036 Decision 4 block bootstrap 估計），M3 不寫死 magic number；本 ADR 只鎖**結構 + ladder**。

### Decision 4 — Amplification cap（per H-11，1-anomaly = 1-state-change/24h）

| 元素 | 設計 |
|---|---|
| 觸發來源 | M8 anomaly detector emit anomaly_id 到 M3 |
| Cap 規則 | **同一 anomaly_id 在 24h rolling window 內最多觸發 1 次 state transition** |
| Cap key | `(anomaly_source, anomaly_signature_hash)` — signature_hash 對 anomaly 內容做 stable hash 去重 |
| Cap 失效情境 | 24h 窗口後 reset；anomaly_signature 變更（不同 anomaly burst）獨立計數 |
| 失效時 fallback | 第 2+ 次同 anomaly_id 觸發 → 仍 log + emit metric，但**不**進 state transition；等待 24h cooling |
| 反模式 | (a) per-event 直接降級（false-positive burst → 數分鐘內 OK → CRITICAL）(b) Cap key 只取 source 不取 signature（不同異常被誤合併）(c) 不留 cooling window log（debug 無法回溯為何升級被吞）|
| 落地 | M3 design spec §6 amplification logic + V106 `health_state_transitions` 表含 `cap_suppressed_count` column；對齊 ADR-0036 M8 dedup contract |

### Decision 5 — Cascade gate cap（8 action / 1 cascade）

| 元素 | 設計 |
|---|---|
| Cascade 定義 | 一次 state transition 觸發的下游 action set（Strategy halt / LAL toggle / Alert / Logging / Audit emit 等） |
| Cap 規則 | **單一 cascade 最多執行 8 action**；超出視為 design overflow → ERROR + fail-closed |
| Cap 為何 8 | M3 design spec §4 列 6 種 cascade action category（trading halt / reparam halt / LAL toggle / alert routing / audit / logging）+ 2 餘量；超 8 = 設計擴張需先 amend |
| 反模式 | (a) Cascade 無上限（典型 single transition 觸發 N domain × M strategy 連鎖 → cascade 雪崩）(b) Cap 不留 telemetry（debug 無法判斷為何 cascade 截斷） |
| 落地 | M3 design spec §6 cascade enforcement + telemetry counter |

### Decision 6 — M3 不繞 5-gate（HEALTH_CRITICAL ≠ true live kill）

| 元素 | 規範 |
|---|---|
| 規則 | M3 4-state ladder 任一 state（含 CRITICAL）**不可繞過或弱化 5-gate kill criteria** |
| HEALTH_CRITICAL 行為 | All trading halt = **暫停 emit new lease**；已 emit 但未 settle 的 lease 走自然 settle 路徑；已開倉位走 SL/TP；**engine 不強制停止**（CATASTROPHIC 才強制停）|
| 與 5-gate 關係 | 5-gate fail = engine 自己拒下單（M3 不參與）；M3 HEALTH_CRITICAL = engine 仍能下單但 M3 cascade 要求 halt new intent — **兩個獨立 fail-safe 鏈** |
| 反模式 | (a) HEALTH_CRITICAL → 直接調 5-gate kill（治理層次混淆）(b) HEALTH_OK → 自動繞 5-gate 任一條件（fail-open）(c) M3 自己 emit `authorization.json`（authorization 不歸 M3）|
| 落地 | M3 design spec §3 integration contract + ADR §四 hard boundary 不變 |

### Decision 7 — Retirement criteria（何時 M3 自身可退役 / 結構性升級）

| 觸發條件 | Action |
|---|---|
| 6 domain 覆蓋率不足（新增 sub-system 如 Y3+ multi-venue） | Amend V106 schema + 補 domain；不退役 M3 |
| 4-state ladder 不足表達（如需 5-state） | Amend 本 ADR Decision 2；保留 backward compat |
| 集中 authority 經 12 mo 線上後評估失敗（cascade 反而成系統性 SPOF） | 開 ADR amendment 評估「分權重組」；M3 本身不單方面廢除 |
| Health authority 與外部 SRE 系統合併（Y3+ 假設） | 開新 ADR；M3 降為 sensor，evaluation/cascade 移到外部 |

## Alternatives Considered

| Alternative | 棄因 |
|---|---|
| **分散 healthcheck**（保留 v5.7 fragmented） | per §Context 5 source 各自為政 → cross-strategy 互比不可能 + alert routing 不一致 + cascade 無法定義 |
| **2-state ladder（OK / NOT_OK）** | 失去 WARN 預警 + DEGRADED 階段性降級空間；operator 失去 "有問題但還能跑" 中間訊號 |
| **5-state ladder（含 CATASTROPHIC）** | CATASTROPHIC 已由 5-gate kill / Operator manual kill 處理；M3 不應重複定義 catastrophic 邊界 |
| **No amplification cap** | per H-11 反向 attack：false-positive anomaly burst → 數分鐘內 OK → CRITICAL → 全停 |
| **per-domain 各自 cap（無 cross-domain coordination）** | M8 同 anomaly 跨 domain 觸發（pipeline + business 雙層）會繞 per-domain cap；必須在 M3 中心化 cap |
| **HEALTH_CRITICAL → 強制 engine kill** | 違反 Decision 6；5-gate kill 是 catastrophic 防線，M3 是 operational 防線；兩者不可混淆 |
| **M3 emit `authorization.json` 自動 demote authorization** | 違反 §四 hard boundary「signed live authorization 必經 approved Python renew/approve 路徑」 |
| **Cascade 無上限** | Single transition 連鎖觸發 N × M action 導致 system-wide cascade meltdown |

## Consequences

### Positive

- **單一健康真相** — 全 system state 由 M3 統一發布；operator dashboard / alert / debug 對齊
- **State ladder 漸進降級** — WARN / DEGRADED / CRITICAL 三階段給足預警 + 自動降級空間，不是「立即停車」二極化
- **與 LAL gate 完整對接** — HEALTH_DEGRADED → LAL auto-approve disabled（per ADR-0034 Decision 4 toggle 對接）；不創旁路
- **Amplification cap 救命** — False-positive anomaly burst 不再能在數分鐘內把 system 從 OK 拉到 CRITICAL
- **Cascade cap 防雪崩** — Single state transition 不再能觸發無上限 action chain
- **與 5-gate 邊界明示** — HEALTH_CRITICAL ≠ true live kill；兩條 fail-safe 鏈獨立運作不互蓋
- **6 domain 覆蓋 3 層** — Process / Pipeline / Business 三層分離設計填補「engine alive but trading dead」盲區

### Negative / Risk

- **集中 = 潛在 SPOF** — M3 module 自身故障會讓全 system 失去健康可觀測性；mitigation = M3 emit self-heartbeat 到 engine_watchdog（fallback 觀測），M3 down 時 engine_watchdog 升級 alert
- **Threshold 估計需要 90d 累積資料** — Y1 早期 strategy 樣本不足會讓 V106 `regime_threshold_table` 不準；mitigation = 預設保守 threshold + 30d re-estimate cadence（per ADR-0036 Decision 4 block bootstrap）
- **Cascade cap 8 在複雜場景可能不夠** — Future module（M9 / M10 / M11）加入可能觸發 > 8 action；mitigation = Decision 7 retirement criteria 允許 amend；超 8 fail-closed 而非 silent truncate
- **HEALTH_DEGRADED → LAL auto-approve disabled 對 Operator UX 增加摩擦** — DEGRADED 期間所有 LAL 1/2 退回 manual approve；mitigation = degradation 本就應該收緊自主，這是 by design
- **6 domain × per-symbol × 30s/60s/5min sampling = 寫入 burst** — V106 schema 必須有 partition / TTL 控制；mitigation = V106 spec 包含 `health_observations` 7d hot + 30d archive 策略
- **M3 ↔ M8 amplification cap 需 anomaly_signature_hash 穩定** — signature 演算法選錯會誤合併或誤分離 anomaly；mitigation = ADR-0036 Decision 2 替代算法已鎖 + M8 emitter signature hash spec 同 Sprint 1A-β land

### 與既存設計協作

| 既存元素 | 與本 ADR 關係 |
|---|---|
| `engine_watchdog.py` | M3 `engine_runtime` domain emitter；升級為 M3 sensor，不退役（fallback 保留）|
| `passive_wait_healthcheck.sh` | M3 `database_pool` domain emitter；passive wait 路徑保留，active sample 接 M3 |
| Strategy 內嵌 self-test | M3 `strategy_quality` domain emitter；first-detection deadlock 反模式（per `feedback_first_detection_deadlock_pattern`）必修 |
| 5-gate kill criteria | **獨立 fail-safe**；M3 不可繞，不可弱化（Decision 6）|
| Guardian gate (Decision Lease) | **獨立路徑**；M3 cascade 不繞 Guardian；HEALTH_DEGRADED 只 halt new lease emit，不繞 lease audit |
| ADR-0034 M1 LAL | HEALTH_DEGRADED → LAL auto-approve disabled（ADR-0034 Decision 4 toggle fallback）|
| ADR-0036 M8 anomaly | Amplification cap key 用 M8 anomaly_signature_hash；ADR-0036 Decision 2 替代算法為 signature source |
| AMD-2026-05-21-01 autonomy directive | DEGRADED → autonomy 收緊；CRITICAL → autonomy 全停；對齊 evidence-gated autonomy 紀律 |
| V106 schema spec | 本 ADR 為 V106 設計邊界；V106 spec cite ADR-0042 Decision 3 + Decision 4 |
| ADR-0009 ArcSwap | Threshold hot-update via ArcSwap；不需 engine restart |

## §二 16 根原則合規確認

| # | 原則 | 是否相容 | 說明 |
|---|---|---|---|
| 1 | 單一寫入口 | ✅ | M3 不創寫入口；state 變更走 V106 health_state_transitions 既有 audit 路徑 |
| 2 | 讀寫分離 | ✅ | M3 是觀測層 + 治理層；不直接寫 trading state |
| 3 | AI 輸出 ≠ 命令 | ✅ | M3 cascade 不直接執行交易；只 emit signal 給 LAL gate / Strategy / Alert routing |
| 4 | 策略不繞風控 | ✅ | HEALTH_DEGRADED 收緊不放鬆；HEALTH_OK 不繞 Guardian / 5-gate |
| 5 | 生存 > 利潤 | ✅ | 4-state ladder 預設保守；任何疑慮往收緊方向偏 |
| 6 | 失敗默認收縮 | ✅ | M3 自身故障 → engine_watchdog fallback alert；threshold 缺資料 → 預設保守 |
| 7 | 學習 ≠ live | N/A | M3 是治理層；不涉學習 |
| 8 | 交易可解釋 | ✅ | health_state_transitions 完整 audit；每次 cascade 留 action log |
| 9 | 雙重防線 | ✅ | M3 + 5-gate + Guardian + Local stop 多層；M3 不取代其他層 |
| 10 | 分離事實 / 推論 / 假設 | ✅ | Metric 是事實；threshold 是 walk-forward 估計（事實 + 推論）；cascade 是 governance（假設） |
| 11 | Agent 在 P0/P1 內自主 | ✅ | HEALTH_OK 期間 LAL 1/2 自主路徑暢通；DEGRADED 收緊但不取消 |
| 12 | Evidence-based evolution | ✅ | Threshold walk-forward + 30d re-estimate；不固定 magic number |
| 13 | cost 感知 | ✅ | M3 hot path 採 30s/60s/5min 分層 sampling；不在 trading hot path |
| 14 | 零外部成本 | ✅ | M3 全 Local + DB；不依賴外部 SRE 服務 |
| 15 | Multi-agent formal | ✅ | M3 是 health surface；Strategist / Guardian / LAL gate 各保留邊界 |
| 16 | Portfolio > 孤立 trade | ✅ | `risk_envelope` domain 是 portfolio-level 聚合；對齊原則 16 |

## Cross-References

- **M3 design spec**：`docs/execution_plan/2026-05-21--m3_health_monitoring_design_spec.md`（648 行；本 ADR 治理層 promotion）
- **V106 schema spec**：`docs/execution_plan/2026-05-21--v106_m3_health_observations_schema_spec.md`（schema DDL 主責）
- **v5.8 §2 M3**：`docs/execution_plan/2026-05-20--execution-plan-v5.8.md:123-151`
- **ADR-0034 M1 LAL**：`docs/adr/0034-decision-lease-layered-approval-lal.md`（HEALTH_DEGRADED → LAL toggle fallback）
- **ADR-0036 M8 anomaly**：`docs/adr/0036-m8-anomaly-detection-and-m10-tier-d-model-blacklist.md`（amplification cap signature source）
- **AMD-2026-05-21-01**：`docs/governance_dev/amendments/2026-05-21--AMD-2026-05-21-01-autonomy-vs-human-final-review.md`（DEGRADED → autonomy 收緊對齊）
- **PA dispatch consolidation report**：`docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-21--v58_dispatch_consolidation.md`（H-11 amplification + CR-7 single-authority）
- **engine_watchdog.py**：`helper_scripts/canary/engine_watchdog.py`（升級為 `engine_runtime` emitter）
- **passive_wait_healthcheck.sh**：`helper_scripts/db/passive_wait_healthcheck.sh`（升級為 `database_pool` emitter）
- **feedback_first_detection_deadlock_pattern**：strategy self-test 反模式必修
- **ADR-0009**：`docs/adr/0009-arcswap-config-hot-reload.md`（threshold hot-update 路徑）

## Sign-off

| Role | Source | Date | Status |
|---|---|---|---|
| Operator | 主會話 PM dispatch via v5.8 §2 M3 集中健康 + 4 級狀態 + cascade 治理路徑 | 2026-05-21 | ✅ PROPOSED-pending-commit |
| TW | 本 ADR 起草（M3 design spec 治理層 promotion） | 2026-05-21 | ✅ Drafted |
| PA | V106 schema land 後 cross-ref + amplification cap signature 對齊 ADR-0036 review | TBD（Sprint 1A-β land） | 🟡 PENDING |
| E1 | M3 module IMPL owner（Sprint 5-7） | TBD（Sprint 5） | 🟡 PENDING |
| E2 | 6 domain emitter 串接 review + cascade cap 8 邊界對抗驗 | TBD（Sprint 5-7） | 🟡 PENDING |
| FA | risk_envelope domain ↔ 5-gate envelope 對齊 review | TBD（Sprint 5） | 🟡 PENDING |
| MIT | V106 `regime_threshold_table` block bootstrap 估計對齊 ADR-0036 Decision 4 | TBD（Sprint 1A-γ） | 🟡 PENDING |
| QA | M3 ↔ M1 LAL / M3 ↔ M8 / M3 ↔ M11 integration contract 字面對齊驗 | TBD（Sprint 1A-β） | 🟡 PENDING |
| PM | Sprint 5-7 IMPL dispatch 前 ADR-0042 land 確認 | TBD（Sprint 5） | 🟡 PENDING |

---

*OpenClaw / Arcane Equilibrium ADR-0042 — M3 Health Monitoring — Single Health Authority + 4-State Ladder (OK/WARN/DEGRADED/CRITICAL) + 6 Domain (engine_runtime / pipeline_throughput / database_pool / api_latency / strategy_quality / risk_envelope) + Amplification Cap (1-anomaly = 1-state-change/24h per H-11) + Cascade Cap (8 action / 1 cascade) + M3 不繞 5-gate (Proposed-pending-commit per 2026-05-21 v5.8 §2 M3 module)*
