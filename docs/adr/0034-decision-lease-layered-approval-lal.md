# ADR 0034: Decision Lease Layered Approval (LAL) — M1 Autonomous Proposal-to-Execution Loop

Date: 2026-05-21
Status: **Proposed-pending-commit**（per operator D2 2026-05-21 已批 LAL 改名；v5.8 §2 M1 module ADR 級落地；本 ADR 為 ADR-0008 Decision Lease 的擴展，不取代）
Operator Sign-off: 2026-05-21（主會話 PM dispatch via v5.8 §2 M1「Lease Tier 0-4 重命名為 Layered Approval Lease (LAL) 0-4 以避 AMD-2026-05-15-01 Stage 0R-4 字面碰撞」D2 已批）
Related: ADR-0008 (Decision Lease state machine, baseline) / ADR-0016 (Decision Lease Router evidence mode) / ADR-0024-lite (Cowork operator-assistant) / ADR-0035 (M5 online learning interface reservation; Y3+ activation 走 LAL Tier 4) / ADR-0037 (M9 A/B framework; variant promotion to Stage 4 走 LAL Tier 3 operator approval；cluster 對齊矩陣引用 LAL Tier 1/2/3) / AMD-2026-05-15-01 (Canary Rebase Replay Preflight Demo-Micro-Canary — Stage 0R-4) / AMD-2026-05-21-01 (autonomy-vs-human-final-review) / v5.8 §2 M1 / V112 schema spec (placeholder pending CR-8) / PA dispatch consolidation report `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-21--v58_dispatch_consolidation.md` / PM final verdict `docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-21--v58_pm_final_verdict.md`

## Context

### 起源

v5.7 baseline：每次 Allocator monthly proposal 都需要 operator 透過 Console 點擊批准。Operator 度假 / 遺忘 / 高密度其他事務 = bot 癱瘓（Advisory proposal queue 累積、無 SLA 自動降級路徑）。

v5.8 §2 M1 因此引入「Layered Approval Lease」（LAL）5 層分層治理：

1. **LAL 0**（per-fill）— 永遠 autonomous，沿用既有 Guardian 路徑
2. **LAL 1**（intra-strategy reparam）— Stage 4 + 30d stable 後 autonomous
3. **LAL 2**（cross-strategy reweight）— Y1 Advisory / Y2 Auto with gate
4. **LAL 3**（new strategy promotion）— 永遠 operator approval
5. **LAL 4**（capital structure / venue change）— 永遠 operator approval

### 為什麼從「Lease Tier 0-4」改名為「LAL 0-4」（D2 已批）

v5.8 §2 M1 初稿使用「Lease Tier 0-4」命名。QA 5.21 audit catch 到字面碰撞風險：

- **AMD-2026-05-15-01**（Canary Rebase Replay Preflight）已用「**Stage 0R-4**」命名 (Stage 0R / Stage 1 / Stage 2 / Stage 3 / Stage 4) 表示策略 promotion progress / live readiness
- 同時用「**Tier**」表示 lease approval depth → reviewer / sub-agent 容易誤把「Tier 4」對到「Stage 4」（兩個正交維度被讀者強行對齊）
- v5.7 / v5.8 dispatch pipeline 已有 multi-agent 並行 review；任何字面碰撞會在 sub-agent prompt parse 時放大為實質誤判

Operator 2026-05-21 D2 已批 → 改名為「Layered Approval Lease」（LAL），對應數字保持 0-4，但用 LAL 0 / LAL 1 / LAL 2 / LAL 3 / LAL 4 名稱。

### 為什麼 LAL 不取代 Stage（兩個正交維度）

**這是本 ADR 必須明示的核心區隔**：

| 維度 | 名稱 | 表示什麼 | 來源 / 落地 |
|---|---|---|---|
| Approval depth / autonomy level | **LAL 0-4** | 一個 decision 需要多深的人類審批；數字越大越嚴 | 本 ADR-0034（v5.8 §2 M1 新增） |
| Promotion progress / live readiness | **Stage 0R-4** | 一個 strategy / parameter / overlay 走到了多遠的 live promotion；數字越大越成熟 | AMD-2026-05-15-01（Canary Rebase Replay Preflight） |

兩者**邏輯上正交但治理上有對齊關係**：策略要達到「LAL 1 autonomy」首先需要在「Stage 4」站穩 30d；LAL 2 autonomy 在 Y2 才考慮，且策略仍須在 Stage 4。**沒有「LAL 5 = Stage 5」的對應關係**；不能讀作「LAL 數字就是 Stage 數字」。

對齊矩陣詳見 §Decision LAL ↔ Stage 對齊表。

### v5.7 ADR-0008 baseline 與本 ADR 關係

ADR-0008（Decision Lease state machine）已 accepted 並 live：

- Lease emit / sign / settle / replay / Guardian gate / Audit 路徑都已 IMPL
- ADR-0016 加 Router evidence mode（Cluster + Tag 路由）
- v5.7 baseline 所有 lease 都走「emit → operator approve via Console → settle」單一路徑

本 ADR-0034 是 ADR-0008 的**擴展**（不取代）：

- ADR-0008 state machine 保留
- 在 emit 後新增「**LAL gate**」分流：根據 LAL level 走 auto-approve（LAL 0/1/2）或 operator-approve（LAL 3/4）
- Lease record 結構不變（lease_id / payload_hash / signed_at 等 schema 保留），新增 `lal_level` column + auto-approve metadata
- ADR-0008 5-gate kill criteria + Guardian gate 對所有 LAL level 都生效（fail-closed 不變）

### v5.8 §2 M1 真實工作觸發 ADR 必要性

v5.8 §2 M1 列「Sprint 1A: Lease Tier schema + ADR-0034 (60-80 hr)」並指定 ADR-0034 為本 module 治理 ADR。在沒有本 ADR 的情況下啟動 Sprint 1A schema design 違反治理紀律（PA dispatch 時 sub-agent 缺少 ADR 級邊界），需先把 LAL 治理 baseline 鎖入 ADR 才能合規 dispatch。

### AMD-2026-05-21-01（autonomy-vs-human-final-review）與本 ADR 關係

AMD-2026-05-21-01 是 operator D5 提出的 autonomy directive，將以 amendment 形式 land（pending CR-3）。本 ADR Decision 5（auto-approval gate criteria）必須與該 amendment 對齊：

- AMD-2026-05-21-01 主張在「evidence-gated autonomy expansion」前提下擴大 agent 自主權，但仍保留 operator 在 LAL 3/4 的 final review 權威
- 本 ADR 對應方式：LAL 3/4 永遠 operator-approve；LAL 1/2 auto-approve 受 6 條 hard gate（§Decision 5）約束；Console toggle 預設 OFF + 24h undo

## Decision

**Proposed**：以下 5 個治理立場 + LAL ↔ Stage 對齊矩陣 + auto-approval gate criteria + 工程 scope 落地為 ADR 級規範：

### Decision 1 — Per-Decision Lease Emit Policy（LAL 1+2 auto-approve 仍 emit lease）

| 元素 | 設計 |
|---|---|
| 規則 | LAL 1 / LAL 2 auto-approve 路徑下，**每一筆 decision 仍必 emit 完整 lease record**（含 `lease_id` / `payload_hash` / `signed_at` / `lal_level` / `auto_approval_metadata`） |
| 為什麼 | Guardian replay 必須能重放每一筆 decision；如果 auto-approve = 不留 lease，audit chain 斷裂，違反 §二 原則 8「交易必可重構並解釋」 |
| 與 ADR-0008 關係 | ADR-0008 emit / sign / settle / replay 路徑全部保留；只是在 sign 階段新增「auto-sign by LAL gate」分支，不繞過 emit |
| 與 ADR-0016 關係 | Router evidence mode 對所有 LAL level 都生效；auto-approve 不繞過 Router 路徑 |
| 反模式（明示禁止） | (a) 「LAL 1+2 auto = 跳過 lease emit」 (b) 「auto-approve 只記 aggregate counter 不留 per-decision record」 (c) 「auto-approve metadata 只存 in-memory 不寫 DB」 |
| 落地 | V112 schema 必含 `lal_level smallint NOT NULL` + `auto_approval_metadata jsonb NULL`（CR-8 schema spec 派工 owner） |

### Decision 2 — lease_id Uniqueness Contract（idempotent semantics）

| 元素 | 設計 |
|---|---|
| Uniqueness 三元組 | `(strategy_name, proposal_hash, lease_window_start)` 必 unique |
| `proposal_hash` 定義 | 對 proposal payload 做 stable canonical JSON serialization 後 SHA-256；同一 proposal 重發應產出相同 hash |
| `lease_window_start` 定義 | Lease 生命週期視窗的起始 timestamp（UTC, ms 精度）；窗口長度由 LAL level 決定（LAL 0 = single fill / LAL 1 = 24h proposal validity / LAL 2 = 7d proposal validity 等） |
| Idempotent 行為 | 同 `(strategy, hash, window_start)` 三元組重發 = 返回既有 lease（不 duplicate emit）；client 端 retry 安全 |
| Conflict resolution | 若同三元組但 payload_hash 不同 → 視為 payload 漂移 fail-closed + alert Operator（提示「同 proposal 同窗口被改動」） |
| 反模式（明示禁止） | (a) 用 `(strategy, proposal_hash)` 二元組 → 跨窗口 collision (b) 用 `(strategy, lease_window_start)` 二元組 → 同窗口多 proposal 撞 (c) 用 client-supplied UUID → audit chain 無法去重 |
| 落地 | V112 schema 必含 `UNIQUE (strategy_name, proposal_hash, lease_window_start)` constraint |

### Decision 3 — 80% Yes-Rate Window（rolling 30-day, not lifetime）

| 元素 | 設計 |
|---|---|
| 統計窗口 | **Rolling 30-day**（不是全期累計） |
| 統計指標 | `operator_yes_rate = approvals_yes / (approvals_yes + approvals_no)` 在窗口內 |
| Min sample | N ≥ 30 prior Advisory approvals（窗口內） |
| Threshold | `operator_yes_rate > 80%`（嚴格大於，不含等於） |
| 為什麼 rolling 不 lifetime | (a) Operator 對策略的判斷會隨 regime 變化；半年前 80% yes 不代表現在還 80% (b) Lifetime 累計會被早期 high-approval 期 dominate → 後期 operator 已開始 push back 但 lifetime ratio 仍過 80% gate → 誤觸發 auto |
| 窗口滑動規則 | 每筆 Advisory approval / rejection 觸發窗口重算；窗口起點 = `now() - INTERVAL '30 days'` |
| 反模式（明示禁止） | (a) Lifetime 累計（per (b) 上述）(b) 窗口 < 30d（樣本不夠穩定）(c) 不要求 min sample（早期 N=3 全 yes 就 100% 過 gate 屬於誤觸發）|
| 落地 | V112 schema 必含 `lal_yes_rate_window_days smallint NOT NULL DEFAULT 30` + `lal_min_advisory_sample smallint NOT NULL DEFAULT 30` |

### Decision 4 — Console Toggle Auth（Auto-Approve On 切換需 Operator role + 2FA）

| 元素 | 設計 |
|---|---|
| 切換主體 | Console 上「Auto-Approve On」toggle（per strategy / per LAL level 顆粒度） |
| Auth 需求 | (a) Operator role（不接受 Viewer / Analyst role） + (b) 2FA confirm（TOTP 或 hardware key） + (c) post-hoc notification（Slack + email + Console banner） |
| 預設值 | **默認 OFF**（per v5.8 §2 M1 Operator forgetfulness mitigation：default-OFF 確保「operator 忘了開」= 系統 fallback 到 v5.7 Advisory 模式 = safe degradation） |
| Toggle 變更紀錄 | 每次切換進 `learning.lal_toggle_audit` table（含 actor / before / after / 2FA 驗證 result / timestamp） |
| 反模式（明示禁止） | (a) 不要求 2FA（Operator session hijack 風險）(b) Viewer / Analyst role 可切換（authorization 降級）(c) 切換不通知 / 不留 audit |
| 落地 | V112 schema 必含 `lal_toggle_audit` table + 對應 GUI handler 對齊 §authorization 路徑 |

### Decision 5 — 24h Undo Scope（scope = config + risk envelope only, NOT fills）

| 元素 | 設計 |
|---|---|
| Undo 觸發 | Operator 在 24h 內透過 Console 點擊 「Undo last auto-approval」 |
| Undo 邊界（**核心**） | **Scope = config + risk envelope only**；**fills 已成交不可逆** |
| Undo 內容 | (a) 回滾 strategy parameter 到 pre-proposal snapshot (b) 回滾 risk envelope 到 pre-proposal state (c) 標記該 lease 為 `lal_undone=true` (d) Emit alert + slack notification |
| 不在 undo 範圍 | (a) 已成交 fills（per CR-7 與 E2 §11 反向 attack 第 1 條「成交不可逆」原則）(b) 已寫入 audit log 的歷史 record（保留歷史完整性） (c) 已影響的下游 derived data（如已聚合的 PnL panel） |
| Pre-proposal snapshot 來源 | V112 schema 新增 `lal_pre_proposal_config_snapshot jsonb NOT NULL`（每筆 auto-approve lease emit 時 capture） |
| 24h 邊界後 | 24h 後 undo button disabled；如需 rollback 走 Operator manual amendment 路徑（非 LAL undo） |
| 反模式（明示禁止） | (a) Undo 涵蓋 fills（與 ADR-0008 「成交不可逆」原則衝突）(b) Undo 涵蓋 audit log（歷史完整性破壞）(c) Undo 邊界模糊 / 文件未明示（reviewer 推測「應該」可以 undo fills）|
| 落地 | V112 schema 必含 `lal_pre_proposal_config_snapshot jsonb NOT NULL` + Console undo handler 對齊 §authorization 路徑 |

### LAL ↔ Stage 對齊矩陣（核心治理 artifact）

| LAL | Approval depth | Compatible Stages | Per-decision lease emit | Auto-approve gate eligibility |
|---|---|---|---|---|
| **LAL 0** | per-fill | Stage 0 / 0R / 1 / 2 / 3 / 4 | yes（既有 Guardian 路徑） | always（既有 Guardian auto） |
| **LAL 1** | intra-strategy reparam | **Stage 4 only**（30d stable） | yes | yes after eligibility（per §Decision 5 gate criteria） |
| **LAL 2** | cross-strategy reweight | **Stage 4 only**（Y2 gate） | yes | Y2 only + Console opt-in（per §Decision 4 toggle）|
| **LAL 3** | new strategy promotion | n/a（gate to Stage 0R+） | yes | **never auto**（always operator approve） |
| **LAL 4** | capital structure / venue change | n/a（gate to ADR-debt） | yes | **never auto**（always operator approve） |

**矩陣讀法**：

- **「Compatible Stages」直欄**：表示該 LAL level 對應的決策對象 strategy / config 必須處於該 Stage（或 LAL 3/4 是 gate 不適用）
- **「Per-decision lease emit」直欄**：永遠 yes（per §Decision 1）
- **「Auto-approve gate eligibility」直欄**：對應 §Decision 5 6 條 hard gate；LAL 3/4 永遠不過 gate

### Auto-Approval Gate Criteria（LAL 1 + LAL 2 only，6 條 hard gate）

對應 v5.8 §2 M1 既有列法 + 本 ADR formalize：

1. **Prior approval threshold**：≥ 30 prior Advisory approvals with > 80% rolling 30d operator yes-rate（per §Decision 3）
2. **Incident-free window**：No incident in proposal scope last 90d（incident 定義 = 該 strategy 觸發 Guardian block / 5-gate kill / Operator manual halt 任一）
3. **Risk envelope check**：所有 proposed parameter 在歷史 Stage 4 envelope 內（per AMD-2026-05-09-03 RuntimeMaxEnvelope）
4. **Operator opt-in**：Console toggle = Auto-Approve On（per §Decision 4，default OFF）
5. **24h undo path**：Pre-proposal snapshot 已 capture + undo handler 可用（per §Decision 5）
6. **Post-hoc transparency**：Slack + email + Console notification 三路通知 emit 成功

**6 條全部必須 PASS** 才觸發 auto-approve；任一 fail → fallback 到 v5.7 Advisory 路徑（Operator manual approve）。

### Engineering Scope（refer v5.8 §2 M1）

| Phase | 工作 | 估時 | 對應 v5.8 行 |
|---|---|---|---|
| Sprint 1A-β | LAL schema + V112 + ADR-0034 | 60-80 hr | v5.8 §2 M1 line 81 + 本 ADR + CR-8 spec |
| Sprint 4 | LAL 1 IMPL（per-strategy reparam after stable） | 40-60 hr | v5.8 §2 M1 line 82 + line 549 Sprint 4 |
| Sprint 7-8 | LAL 2 IMPL（Advisory + auto-eligibility tracking） | 50-70 hr | v5.8 §2 M1 line 83 + line 552 Sprint 7 |
| Y2 | LAL 2 auto-execution enable（gate + monitoring） | 30-50 hr | v5.8 §2 M1 line 84 + line 572 Y2 Q1-Q2 |

## Alternatives Considered

| Alternative | 棄因 |
|---|---|
| **保留「Tier 0-4」命名 + 加 LAL ↔ Stage 對齊矩陣**（QA 替代提案） | 字面碰撞風險長期累積；多 agent dispatch pipeline 任何 prompt 提到「Tier 4」+「Stage 4」並列都會引入 reviewer 誤讀；命名級隔離 cost 一次性、收益長期 |
| **完全分離 LAL 與 Stage**（無對齊矩陣） | Spec dispatch 時 sub-agent 難判斷「哪個 LAL 對哪個 Stage」；缺對齊矩陣 = 每次 dispatch 都要重新推導 = treason 風險（reviewer 誤判 LAL 2 可在 Stage 2 用） |
| **全 operator-approve（不引入 auto）** | 違反 operator D5 AMD-2026-05-21-01 autonomy directive；v5.7 痛點 Operator forgetfulness 沒解；M1 module 失去意義 |
| **Auto-approve 不 emit lease**（aggregate counter only） | 違反 §二 原則 8「交易必可重構並解釋」；Guardian replay 斷裂；audit chain 不完整 |
| **80% yes-rate 用 lifetime 累計**（不 rolling） | Regime change 後失真（per §Decision 3 棄因）；早期 high-approval 期 dominate → 後期 push back 信號被淹沒 |
| **Console toggle 不要求 2FA** | Operator session hijack 風險；2FA 是 minimal authorization 紀律，與 §authorization mainnet gate 對齊 |
| **24h undo 涵蓋 fills**（rollback 已成交） | 與 ADR-0008 「成交不可逆」原則衝突；exchange 端已執行 fill 無法 client-side rollback；undo 邊界必須明示 |
| **LAL 1/2 auto-approve 也需 2FA per decision** | Auto-approve 的目的是 remove operator click；要求 2FA per decision = degrade 到 manual approve；2FA 只用在 toggle 切換，不在 per-decision 路徑 |

### Decision 6 — LAL Tier 0 Active Blocker on M7 RETIRED Strategy (per R4 NEW-M-3 patch 2026-05-21)

| 元素 | 設計 |
|---|---|
| Contract | strategy lifecycle 進入 `RETIRED` state (per M7 DECAY_ENFORCED → RETIRED transition in V113 `decay_signals.lifecycle_state`) → 該 strategy 全部後續 LAL Tier 0 fill query path **MUST fail-closed** |
| 為什麼 | M7 RETIRED = strategy alpha-deficient 永久退役 (per ADR-0044 Decision 1 M7 single decay authority)；若 LAL Tier 0 仍允許 fill = 等同 retire 形同虛設；違反 §二 原則 5「生存 > 利潤」 + §二 原則 6「Uncertainty defaults to conservative」 |
| Query path | LAL Tier 0 fill judgment 必 query：`SELECT lifecycle_state FROM learning.mv_latest_decay_state_per_strategy WHERE strategy_id=$1` → IF `RETIRED` → reject fill + audit log + alert operator |
| 已開倉位 | RETIRED 觸發 = 新 fill block；已開倉位走既有 SL/TP path（不強制 immediate close）|
| Operator override | LAL 4 manual override 也禁用（per AMD-2026-05-21-01 protected scope）；僅 operator manual re-promotion through Stage 0R 路徑可從 RETIRED 拉回 NORMAL_LIVE（30d cooling + per ADR-0044 §3.2 transition table）|
| 反模式（明示禁止） | (a)「RETIRED 但 LAL Tier 0 仍 fill」= retire 形同虛設 (b)「LAL Tier 4 operator override RETIRED → NORMAL_LIVE 即時」= 違反 14d × 50% mitigation 硬基石 (c)「Tier 0 query 不 check decay_signals」= cross-module contract 斷裂 |
| 落地 | V112 schema LAL Tier 0 fill query path 必 join `learning.mv_latest_decay_state_per_strategy`（per V113 §8 materialized view land）；Sprint 1A-ζ spike Track A4 是首次 empirical verify 此 contract |
| Cross-ref | ADR-0044 Decision 1+6 (M7 single decay authority + RETIRED → LAL Tier 0 blocker) / V113 `decay_signals.lifecycle_state` ENUM 'RETIRED' / AMD-2026-05-21-01 protected scope §4 反向 attack #4 14d × 50% mitigation / Sprint 1A-ζ spike spec §2.1 A4 |

## Consequences

### Positive

- **命名零字面碰撞** — LAL 0-4 與 Stage 0R-4 不再 ambiguous，multi-agent dispatch reviewer 不會誤對齊
- **M1 auto path 治理紀律完整** — 6 條 hard gate + Console opt-in + 24h undo + per-decision lease + audit trail 五層保護
- **ADR-0008 baseline 不變** — 既有 Decision Lease state machine 全保留，本 ADR 是擴展不是取代
- **與 AMD-2026-05-21-01 autonomy directive 對齊** — 在 evidence-gated 前提下擴大 agent 自主，仍保 Operator 在 LAL 3/4 final review
- **v5.7 痛點 Operator forgetfulness 收口** — Default OFF 確保「忘了開」= safe degradation 到 v5.7 Advisory；不會默認 auto 造成 unintended autonomy
- **LAL ↔ Stage 對齊矩陣可被 sub-agent 直接讀** — Sprint 1A 起 PA dispatch 不再需要 ad-hoc 推導「哪個 LAL 對哪個 Stage」
- **V112 schema lock 為 single source of truth** — `lal_level` + `lal_pre_proposal_config_snapshot` + `lal_toggle_audit` 三表構成 audit 完整性

### Negative / Risk

- **搜尋取代 cost 30-60 min** — v5.8 §2 / §3 / §7 / §9 / §11 / §12 內所有「Tier」需替換為「LAL」+ V112 schema column 名稱從 `decision_lease_tiers` 改為 `decision_lease_lal_tiers`；mitigation = CR-2 prefix prerequisite 已列入 D+3 prerequisite checklist，由 PA dispatch 統一處理
- **LAL 1 Sprint 4 IMPL 在 Stage 4 stable 紀律未明示前可能誤觸發** — 30d stable 定義需嚴格（per ADR-0008 既有「30d window 內無 5-gate kill / Guardian block」紀律）；mitigation = Sprint 4 dispatch 時要求 E1 cite ADR-0034 Decision 5 gate criteria
- **rolling 30-day window 對新策略不公**（min N=30 在 Y1 早期可能很久才達到）— Y1 早期策略可能要 60-90d 才累積 30 approvals → LAL 1 eligibility 延遲；mitigation = 這是 by design，autonomy 升級必須有足夠樣本，不應為「快」放寬 min N
- **Console toggle 2FA 對 ops UX 增加摩擦** — 每次切換都要 TOTP；mitigation = 切換頻率本身應該很低（per strategy 一次性 opt-in），摩擦成本可接受
- **24h undo 邊界（fills 不可逆）需 Operator 認知到位** — 若 Operator 誤以為 undo = full rollback 會造成預期落差；mitigation = Console undo button hover tooltip + Slack notification 明示「fills already executed cannot be undone」
- **V112 schema migration 與 V### dry-run mandatory 規則對齊** — per feedback `feedback_v_migration_pg_dry_run.md`，V112 必須先 Linux PG empirical dry-run 再 IMPL sign-off；mitigation = CR-8 spec doc 派工時 explicit list dry-run requirement

### 與既存設計協作

| 既存元素 | 與本 ADR 關係 |
|---|---|
| ADR-0008 Decision Lease state machine | **本 ADR 為 ADR-0008 擴展**；emit / sign / settle / replay / Guardian gate / 5-gate kill 全保留；新增 LAL gate 分流 |
| ADR-0016 Decision Lease Router evidence mode | **不變**；Router 對所有 LAL level 都生效；auto-approve 不繞 Router |
| ADR-0024-lite Cowork operator-assistant | **協作**；Cowork operator assistant 在 LAL 1/2 auto-approve 後 emit notification + 提供 undo button 入口；assistant 不做 auto-approve 判斷 |
| AMD-2026-05-15-01 Stage 0R-4（Canary Rebase Replay Preflight） | **正交但對齊**；LAL ↔ Stage 對齊矩陣是兩維度橋樑；Stage 命名不變 |
| AMD-2026-05-21-01 autonomy-vs-human-final-review | **本 ADR 為該 amendment 的 ADR 級落地**；6 條 hard gate 對應 evidence-gated autonomy directive |
| AMD-2026-05-09-03 Strategist Wide-Adjustment Skill | **互補**；RuntimeMaxEnvelope 是 §Decision 5 gate #3 risk envelope check 的具體實現 |
| v5.8 §2 M1 Engineering scope | **本 ADR 為 ADR-0034 占位的落地**；Sprint 1A-β 60-80 hr 包含本 ADR + V112 schema + LAL schema design |
| V112 schema spec (CR-8 pending) | **本 ADR 為 V112 設計的 ADR 級邊界**；CR-8 spec doc 必 cite ADR-0034 |
| ADR-0006 Bybit-only exchange | **不變**；LAL 4 capital structure / venue change 永遠 operator approve，不繞 ADR-0006 venue lock |
| v5.8 §2 M3 Health-Aware Degradation | **協作**；HEALTH_DEGRADED 觸發時 LAL 1 reparam halt（per v5.8 §2 M3 line 140） |
| feedback_v_migration_pg_dry_run.md | **V112 必走 dry-run** before IMPL sign-off |

## §二 16 根原則合規確認

對齊 ADR-0033 範式逐條 walkthrough：

| # | 原則 | 是否相容 | 說明 |
|---|---|---|---|
| 1 | 單一寫入口 | ✅ | LAL gate 在 Decision Lease emit 後分流；單一寫入口仍透過 lease → exchange 路徑；auto-approve 不創造旁路寫入口 |
| 2 | 讀寫分離 | N/A | LAL 是治理層，讀寫分離原則 (research/GUI/learning read-only) 不被本 ADR 觸及 |
| 3 | AI 輸出 ≠ 命令 | ✅ | Strategist / Allocator AI 輸出仍是 proposal，必經 LAL gate（含 auto-approve 路徑）才成為 lease；LAL 不繞 Decision Lease |
| 4 | 策略不繞風控 | ✅ | Guardian gate / 5-gate kill / risk envelope check 對所有 LAL level 生效；LAL 1/2 auto-approve 路徑下 risk envelope check 是 hard gate #3 |
| 5 | 生存 > 利潤 | ✅ | Default OFF + 24h undo + 6 條 hard gate = 預設保守；fail open 路徑不存在；safe degradation 到 v5.7 Advisory |
| 6 | 失敗默認收縮 | ✅ | 任一 gate fail → fallback 到 Operator manual approve；Console toggle 預設 OFF |
| 7 | 學習 ≠ Live | ✅ | LAL 1/2 evidence accumulation（30 approvals + 80% yes-rate）是學習觸發 autonomy 升級，但每筆 decision 仍走 lease 路徑，學習不直接寫 live state |
| 8 | 交易可解釋 | ✅ | §Decision 1 強制 per-decision lease emit；Guardian replay 完整；§Decision 5 pre-proposal snapshot 保 undo audit |
| 9 | 雙重防線 | ✅ | LAL gate + Guardian + Local stop 三層；Auto-approve 路徑下 6 條 hard gate 是額外防線 |
| 10 | 分離事實 / 推論 / 假設 | N/A | LAL 是治理機制不涉及 reasoning 紀錄；reasoning lineage 由 ADR-0017 / 既有 lineage 系統處理 |
| 11 | Agent 在 P0/P1 內自主 | ✅ | LAL 1/2 auto-approve 是 agent 自主提升路徑（在 evidence-gated 前提下），對齊原則 11 + AMD-2026-05-21-01 |
| 12 | Evidence-based evolution | N/A | LAL 治理層；evolution 是 v5.8 §2 M4 Self-Supervised Hypothesis Discovery 範圍 |
| 13 | cost 感知 | ✅ | LAL gate IMPL Sprint 1A-β 60-80 hr 在 v5.8 §2 M1 預算內；rolling window query cost 用 V112 index 控制 |
| 14 | 零外部成本 | N/A | LAL gate 全在 Local + DB 路徑，不涉及外部付費服務 |
| 15 | Multi-agent 是 formal | ✅ | LAL 治理本身是 multi-agent collaboration 紀律（Strategist propose → LAL gate → optionally Operator approve / auto-approve）；Conductor 不變 |
| 16 | Portfolio > 孤立 trade | ✅ | LAL 2 cross-strategy reweight 本身就是 portfolio-level 治理；LAL 1 intra-strategy 在 risk envelope（含 portfolio risk）內運作 |

**4 條標 N/A 的原則**：原則 2 / 10 / 12 / 14 屬於本 ADR 範圍外的維度（讀寫分離 / lineage 紀錄 / hypothesis discovery / 零外部成本），不直接衝突。

## Cross-References

- **ADR-0008**：`docs/adr/0008-decision-lease-state-machine.md`（本 ADR baseline；emit / sign / settle / replay 不變）
- **ADR-0016**：`docs/adr/0016-decision-lease-router-evidence-mode.md`（Router evidence mode 對所有 LAL level 生效）
- **ADR-0024-lite**：`docs/adr/0024-cowork-subscription-operator-assistant.md`（assistant 在 auto-approve 後 emit notification + 提供 undo 入口）
- **AMD-2026-05-15-01**：`docs/governance_dev/amendments/2026-05-15--AMD-2026-05-15-01-canary-rebase-replay-preflight-demo-micro-canary.md`（Stage 0R-4 命名來源；對齊矩陣的 Stage 維度）
- **AMD-2026-05-21-01**：autonomy-vs-human-final-review（CR-3 待 land；本 ADR 為其 ADR 級落地）
- **AMD-2026-05-09-03**：`docs/governance_dev/amendments/2026-05-09--strategist_wide_adjustment_skill.md`（RuntimeMaxEnvelope 是 §Decision 5 gate #3 risk envelope check 的具體實現）
- **v5.8 §2 M1**：`docs/execution_plan/2026-05-20--execution-plan-v5.8.md:59-87`（本 ADR module 來源）
- **v5.8 §2 M3 Health-Aware Degradation**：`docs/execution_plan/2026-05-20--execution-plan-v5.8.md:123-151`（HEALTH_DEGRADED → LAL 1 halt 對應）
- **V112 schema spec**（CR-8 placeholder land 後路徑）：`docs/execution_plan/specs/2026-05-21--v112-decision-lease-lal.md`（待 CR-8 sub-agent 落地；本 ADR 為其設計邊界）
- **PA dispatch consolidation report**：`docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-21--v58_dispatch_consolidation.md`
- **PM final verdict**：`docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-21--v58_pm_final_verdict.md`
- **feedback_v_migration_pg_dry_run.md**：V112 必走 Linux PG empirical dry-run before IMPL sign-off
- **ADR-0006**：`docs/adr/0006-bybit-only-exchange.md`（LAL 4 venue change 永遠 operator approve）

## Sign-off

| Role | Source | Date | Status |
|---|---|---|---|
| Operator | 主會話 PM dispatch via D2 2026-05-21「LAL 改名已批」 | 2026-05-21 | ✅ PROPOSED-pending-commit |
| TW | 本文件起草（v5.8 §2 M1 module ADR 級落地） | 2026-05-21 | ✅ Drafted |
| CC | 5-gate auto path 對齊（CR-15 待 land） | TBD（Sprint 1A-β） | 🟡 PENDING |
| PA | V112 schema land 後一致性驗 | TBD（CR-8 spec doc land 後） | 🟡 PENDING |
| QA | LAL ↔ Stage 對齊矩陣對齊驗（避免 AMD-2026-05-15-01 字面回流） | TBD（Sprint 1A-β） | 🟡 PENDING |
| E1 | V112 schema IMPL owner（Sprint 1A-β） | TBD（Sprint 1A-β） | 🟡 PENDING |
| FA | LAL gate criteria #2 incident-free window 定義 review | TBD（Sprint 1A-β） | 🟡 PENDING |
| BB | LAL 4 venue change 與 ADR-0006 Bybit-only lock 對齊 review | TBD（Sprint 1A-β） | 🟡 PENDING |
| PM | LAL 1 → LAL 2 Y2 enable gate 仲裁（Y2 Q1） | TBD（Y2 Q1） | 🟡 PENDING |

---

*OpenClaw / Arcane Equilibrium ADR-0034 — Decision Lease Layered Approval (LAL) — M1 Autonomous Proposal-to-Execution Loop (Proposed, ADR-0008 extension — original Decision Lease state machine reference: `docs/adr/0008-decision-lease-state-machine.md` baseline thesis unchanged)*
