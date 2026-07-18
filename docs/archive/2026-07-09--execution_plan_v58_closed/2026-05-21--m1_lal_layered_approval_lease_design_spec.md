---
spec: M1 — Layered Approval Lease (LAL) Module DESIGN Spec
date: 2026-05-21
author: PA Sprint 1A-β CRITICAL module DESIGN (dispatched per v5.8 §2 M1 + ADR-0034 + PA consolidation 2026-05-21)
phase: v5.8 Sprint 1A-β module DESIGN (一階段 deliverable；不寫 IMPL code、不寫 DDL)
status: SPEC-DRAFT-V0（PA 起草；待 V112 final DDL land + M3/M7/M11 module spec 並行對齊後 SPEC-FINAL）
parent specs:
  - srv/docs/execution_plan/2026-05-20--execution-plan-v5.8.md §2 M1
  - srv/docs/adr/0034-decision-lease-layered-approval-lal.md
  - srv/docs/adr/0008-decision-lease-state-machine.md
  - srv/docs/governance_dev/amendments/2026-05-15--AMD-2026-05-15-01-canary-rebase-replay-preflight-demo-micro-canary.md
  - srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-21--v58_dispatch_consolidation.md §Sprint 1A-β + §6
companion specs:
  - srv/docs/execution_plan/2026-05-21--v112_m1_decision_lease_lal_tiers_schema_spec.md (V112 schema — MIT 同時段 placeholder，full DDL Sprint 1A-β land)
  - M3 health-aware degradation module spec (PA 同時段並行 — placeholder cross-ref)
  - M7 decay enforcement module spec (QC + MIT 同時段並行 — placeholder cross-ref)
  - M11 nightly replay divergence module spec (PA + QC 同時段並行 — placeholder cross-ref)
mirror precedent:
  - srv/docs/execution_plan/2026-05-21--v103_v104_earn_hypotheses_schema_spec.md (format reference — TL;DR + Background + Outline + Acceptance + Open Q)
scope: module DESIGN only — 不寫 V112 DDL（per V112 spec doc 范圍）/ 不寫 IMPL code（E1 Sprint 4 起 IMPL）/ 不假設 V112 schema 細節（placeholder ref）/ 不擴張 M3/M7/M11 module 內部（cross-ref 即可）
---
> ⚠️ 归档历史文档 — 非当前权威。active 状态见 repo 根 `TODO.md`；本文件仅供历史/审计参考。（2026-07-18 审计批量补入）


> **REFERENCE / FROZEN AUTONOMY MODULE SPEC**
>
> 本 spec 保留 v5.8 Sprint 1A module design lineage。当前 active-IMPL 以
> `TODO.md` 和最新 PM/role reports 为准；不得仅凭本 spec 派发实现或授权 live 影响动作。

# M1 Layered Approval Lease (LAL) Module DESIGN Spec

## §0 TL;DR

- **M1 LAL 是 ADR-0008 Decision Lease state machine 的擴展，不取代** — Lease emit/sign/settle/replay/Guardian gate/5-gate kill 全保留；新增 LAL gate 在 emit 後分流（auto-approve LAL 1/2 或 operator-approve LAL 3/4）。
- **5 級 LAL 0-4，**數字越大越嚴**（**對齊 ADR-0034 Decision 1+5**；不是 V112 placeholder 中的 "0=manual / 4=bypass" 反向語義，本 spec §3.1 開列正確語義表 + §Open Questions Q1 flag V112 spec 反向需 MIT 修正）。
- **6 條 hard gate 對 LAL 1+2 auto-approve 生效**（per ADR-0034 Decision 5）：≥30 prior advisory approvals + rolling 30d operator yes-rate >80% + no incident last 90d + risk envelope in Stage 4 historical + Console toggle = ON + post-hoc transparency emit。
- **LAL ≠ Stage**：LAL 是 approval depth，Stage 是 promotion progress；兩維度正交，但 LAL 1+2 eligibility 要求對象在 Stage 4 stable 30d。LAL ↔ Stage 對齊矩陣是 §3.3 核心 artifact。
- **24h undo scope = config + risk envelope only，NOT fills**（成交不可逆，per ADR-0008 + ADR-0034 Decision 5）。
- **per-decision lease emit 永遠強制**（per ADR-0034 Decision 1）：auto-approve 不繞 lease；Guardian replay + audit chain 不斷裂。
- **Cross-V### 依賴**：V112 (own table) → V113 (M7 decay reference 「no incident 90d」query) → V109 (M8 anomaly reference for 部分 incident 類型；Sprint 1A-γ)。
- **IMPL 分階段**：Sprint 4 LAL 1 (40-60 hr) / Sprint 7-8 LAL 2 advisory (50-70 hr) / Y2 LAL 2 auto-enable (30-50 hr) / LAL 3/4 永遠 operator approve (no IMPL)。
- **AMD-2026-05-21-01 (autonomy-vs-human-final-review) 對齊**：LAL 3/4 final review 永遠 operator authority；LAL 1/2 evidence-gated autonomy 受 6 條 hard gate 約束。
- **反向 attack 6 條 mitigation 對齊 AMD-2026-05-21-01 H-11**：本 spec §6 逐條對應。

---

## §1 Context + 為什麼擴展 ADR-0008 baseline

### 1.1 v5.7 baseline 痛點

ADR-0008 (Decision Lease state machine) baseline：所有 Allocator / Strategist proposal lease 都走「emit → operator approve via Console → settle」單一路徑。Operator 度假 / 遺忘 / 高密度其他事務 = Advisory proposal queue 累積、無 SLA 自動降級路徑 → bot 癱瘓。

v5.8 §2 M1 因此引入 LAL 5 層分層治理，讓 evidence-proven proposal 在 6 條 hard gate 通過後可 auto-approve，operator 只在 LAL 3/4 + 異常路徑介入。

### 1.2 為什麼 4-Tier 治理分層 motivation

不是「全 manual」也不是「全 auto」，而是按 **decision blast radius** 分層：

| LAL | Blast radius | 為什麼這層需要這種 approval depth |
|---|---|---|
| **LAL 0** (per-fill) | 單筆 fill；既有 Guardian gate 已覆蓋 | 永遠 autonomous — 拒此層 auto = engine 無法下任何 order；違反 SLA |
| **LAL 1** (intra-strategy reparam) | 單策略參數調整；風險被 strategy-level risk envelope 框住 | Stage 4 + 30d stable 後 autonomous — 「同策略內已穩定 30d」是 evidence-gated |
| **LAL 2** (cross-strategy reweight) | Allocator 調整策略間 capital 分配；風險在 portfolio level | Y1 advisory / Y2 auto-with-gate — cross-strategy interaction 更複雜，需更多 evidence |
| **LAL 3** (new strategy promotion) | 新策略推進 Stage 0R+ live 路徑；可能引入未知 alpha 源 / 未知失敗模式 | 永遠 operator approve — 新 alpha 源風險不可預測，必 human-in-loop |
| **LAL 4** (capital structure / venue change) | AUM 重新分配 / 新 venue (ADR-0040) / Earn 大移動 | 永遠 operator approve — 結構性決策，需 operator 戰略判斷 |

**5 級設計 motivation**：每加一級就有一個明確的 blast radius + evidence 門檻；4 級或 6 級都無法乾淨 map 到上述決策範疇。

### 1.3 與既有治理元素關係（不取代）

| 既有元素 | M1 LAL 與其關係 |
|---|---|
| ADR-0008 Decision Lease state machine | **本 module 是 ADR-0008 擴展**；9 狀態 lifecycle (DRAFT/REGISTERED/ACTIVE/BRIDGED/FROZEN/REVOKED/EXPIRED/REJECTED/CONSUMED) 全保留 |
| ADR-0016 Decision Lease Router evidence mode | **不變**；Router 對所有 LAL level 都生效；auto-approve 不繞 Router |
| ADR-0024-lite Cowork operator-assistant | **協作**；assistant 在 auto-approve 後 emit notification + 提供 undo 入口；assistant 不做 auto-approve 判斷 |
| AMD-2026-05-15-01 Stage 0R-4 (Canary Rebase Replay Preflight) | **正交但對齊**；LAL ↔ Stage 對齊矩陣是兩維度橋樑 |
| AMD-2026-05-21-01 autonomy-vs-human-final-review | **本 module 為該 amendment 的 module 級落地**；6 hard gate 對應 evidence-gated autonomy directive |
| M3 health-aware degradation | **協作**；HEALTH_DEGRADED 收 LAL stat → 觸發 LAL 1 reparam halt（per v5.8 §2 M3 line 140） |
| M7 decay enforcement | **依賴**；LAL eligibility check 之 「no incident last 90d」走 M7 decay_signals query（V113 placeholder） |
| M11 nightly replay divergence | **協作**；replay divergence event → 可觸發 LAL 降階（per §3.2 auto-降階 rule） |
| M8 anomaly detection (Sprint 1A-γ) | **協作**；anomaly event 是 90d incident-free 計算的 input 之一（V109 placeholder） |
| ADR-0006 Bybit-only exchange | **不變**；LAL 4 venue change 永遠 operator approve，不繞 ADR-0006 venue lock |

---

## §2 Module scope + boundary

### 2.1 In scope (本 module DESIGN 範圍)

- LAL 0-4 5 級語義 + state machine 圖（升降 transition / auto-升降 rule / manual override path）
- Eligibility 計算（per LAL level 准入條件）
- Escalation flow（異常 → 哪個 Tier 處置 → operator 升級 trigger 條件）
- Auto-approve toggle（per ADR-0034 Decision 4 Console toggle auth）
- Cross-module integration touchpoint（M3 / M7 / M11 / M8）
- 5-gate compliance check（LAL 不繞 5-gate）
- 反向 attack 6 條 mitigation（per AMD-2026-05-21-01 H-11）
- Acceptance criteria（DESIGN 級 5-7 條 AC）
- IMPL phase split（Sprint 4 / Sprint 7-8 / Y2）
- Cross-V### dependency graph
- Open questions（≥3 條供 Sprint 1A-γ/δ 補答）

### 2.2 Out of scope（明示）

- V112 DDL spec（per V112 spec doc — MIT owner Sprint 1A-β land）
- M3 / M7 / M11 / M8 module 內部設計（各自 spec owner）
- IMPL code（E1 Sprint 4 起 IMPL）
- GUI Console toggle UI implementation（A3 sub-agent Sprint 4 + GUI 工時 per CR-11）
- Rust IPC schema 增量細節（per H-13 — QA + E4 Sprint 1A-β/γ DESIGN 補）
- Per-strategy threshold 量化值（per H-10 — FA Sprint 1A-β 補）
- M9 A/B variant LAL 路徑（per ADR-0037 — QA + QC Sprint 1A-γ）

### 2.3 假設前提（assumptions）

| # | 假設 | 來源 |
|---|---|---|
| A1 | ADR-0034 已 PROPOSED-pending-commit；本 spec 假設 ADR Decision 1-5 不再變動 | ADR-0034 status line |
| A2 | V112 schema final DDL 由 MIT Sprint 1A-β land；本 spec 用 placeholder 引用 V112 column 名 | V112 spec doc + CR-8 |
| A3 | LAL 0-4 數字方向 = 「越大越嚴」（per ADR-0034 LAL ↔ Stage 對齊表）；**V112 placeholder 反向需修正** | Open Q1 |
| A4 | M7 decay event ledger (V113) 是 「no incident 90d」query 唯一 source | ADR-0034 Decision 5 gate #2 + V113 placeholder |
| A5 | Auto-approve Console toggle default OFF（per ADR-0034 Decision 4） | ADR-0034 |
| A6 | 24h undo 永不涵蓋 fills（per ADR-0034 Decision 5 + ADR-0008 「成交不可逆」） | ADR-0034 |
| A7 | LAL gate 處在 Decision Lease emit 之後、sign 之前；不創造旁路寫入口（§二 原則 1） | §5 5-gate compliance |

---

## §3 LAL 0-4 State machine + transition rules

### 3.1 5 級語義表（authoritative — 對齊 ADR-0034）

| LAL | Approval depth | Blast radius | Eligibility 升級條件 | 自動降階 trigger | Manual override path |
|---|---|---|---|---|---|
| **0** (per-fill) | 既有 Guardian auto | 單筆 fill | n/a (always) | n/a | n/a (Guardian 內建) |
| **1** (intra-strategy reparam) | Auto after eligibility | 單策略參數 | 對象 Stage 4 + 30d stable + 6 hard gate PASS + Console toggle ON | (a) Strategy 觸 5-gate kill (b) M7 decay DECAY_ENFORCED (c) M3 HEALTH_DEGRADED (d) M11 replay divergence >threshold (e) Operator 24h undo | Console「manual approve only」per-strategy toggle |
| **2** (cross-strategy reweight) | Y1 advisory / Y2 auto-with-gate | Portfolio capital 重分配 | Y2 only + 6 hard gate PASS + Console toggle ON + Allocator approval rate >80% 6mo | (a) Portfolio cum_loss > $3,000 (b) M3 HEALTH_CRITICAL (c) M9 A/B fail Y2 enable gate (d) 任一 LAL 1 觸自動降階 cascade | Y1: 永遠 advisory; Y2: Console toggle OFF 降回 Y1 advisory |
| **3** (new strategy promotion) | 永遠 operator approve | 新策略 Stage 0R+ promote | **never auto** | n/a (永遠 manual) | n/a |
| **4** (capital structure / venue change) | 永遠 operator approve | AUM 重分配 / 新 venue / Earn 大移動 | **never auto** | n/a (永遠 manual) | n/a |

**關鍵語義方向**（與 V112 spec placeholder 反向 — 見 §Open Q1）：

- **數字越大 = approval depth 越嚴**（LAL 4 = 永遠 operator approve；LAL 0 = 既有 Guardian auto）
- **不是「LAL 0 = full manual / LAL 4 = bypass」**（V112 placeholder 反向錯誤；需 MIT 修正）
- 對齊 ADR-0034 LAL ↔ Stage 對齊表（「Compatible Stages」+「Auto-approve gate eligibility」直欄）

### 3.2 State machine 完整圖

```
                            ┌─────────────────────────────────────┐
                            │           LAL 0 (per-fill)          │
                            │   既有 Guardian auto / always on    │
                            └─────────────────────────────────────┘
                                          │
                                  (Strategy proposal)
                                          ▼
                            ┌─────────────────────────────────────┐
                            │        LAL 1 候選 (manual only)     │
                            │     新策略 default; Stage 4 stable  │
                            │     未滿 30d 或 6 hard gate 任一 fail│
                            └─────────────────────────────────────┘
                                          │
                       (Stage 4 stable 30d + 6 hard gate PASS
                        + Console toggle ON for this strategy)
                                          ▼
                            ┌─────────────────────────────────────┐
                            │       LAL 1 active (auto-approve)   │
                            │   intra-strategy reparam autonomous │
                            └─────────────────────────────────────┘
                                          │
                       ┌──────────────────┼────────────────────┐
                       │                  │                    │
                (5-gate kill)        (M7 DECAY)         (M3 HEALTH_DEGRADED)
                       │                  │                    │
                       └──────────────────┼────────────────────┘
                                          ▼
                            ┌─────────────────────────────────────┐
                            │  LAL 1 demoted (auto → manual)     │
                            │   降回 LAL 1 候選；重新走 eligibility│
                            └─────────────────────────────────────┘

  ─── Y1 邊界（LAL 2 = advisory only）───

                            ┌─────────────────────────────────────┐
                            │      LAL 2 候選 (Y1 advisory)       │
                            │   Allocator 提案；operator approve  │
                            │   每筆都 manual                     │
                            └─────────────────────────────────────┘
                                          │
                       (Y2 + Allocator approval rate >80% 6mo
                        + 6 hard gate PASS + Console toggle ON)
                                          ▼
                            ┌─────────────────────────────────────┐
                            │       LAL 2 active (Y2 auto)        │
                            │   cross-strategy reweight autonomous│
                            └─────────────────────────────────────┘
                                          │
                       ┌──────────────────┼────────────────────┐
                       │                  │                    │
              (Portfolio cum_loss)  (M3 HEALTH_CRITICAL)  (M9 A/B fail Y2 gate)
                       │                  │                    │
                       └──────────────────┼────────────────────┘
                                          ▼
                            ┌─────────────────────────────────────┐
                            │     LAL 2 demoted → Y1 advisory     │
                            └─────────────────────────────────────┘

  ─── 永遠 manual edge（無 auto path）───

  ┌─────────────────────────────────────┐    ┌─────────────────────────────────────┐
  │       LAL 3 (new strategy)          │    │   LAL 4 (capital / venue change)    │
  │     永遠 operator approve            │    │      永遠 operator approve           │
  │   Strategist propose;                │    │   Allocator propose / Operator init  │
  │   Sprint 4 Live precondition gate    │    │   ADR-0040 multi-venue gate         │
  └─────────────────────────────────────┘    └─────────────────────────────────────┘
```

### 3.3 LAL ↔ Stage 對齊矩陣（核心治理 artifact）

| LAL | Compatible Stages | Per-decision lease emit | Auto-approve gate eligibility |
|---|---|---|---|
| **LAL 0** | Stage 0 / 0R / 1 / 2 / 3 / 4 | yes（既有 Guardian） | always |
| **LAL 1** | **Stage 4 only**（30d stable） | yes | yes after 6 hard gate PASS |
| **LAL 2** | **Stage 4 only**（Y2 gate） | yes | Y2 only + Console opt-in |
| **LAL 3** | n/a（gate to Stage 0R+） | yes | **never auto** |
| **LAL 4** | n/a（gate to ADR-debt） | yes | **never auto** |

**矩陣讀法**：
- **「Compatible Stages」**：對應 decision 對象 strategy/config 必須處於該 Stage（LAL 3/4 是 gate 自身不適用）
- **「Per-decision lease emit」**：永遠 yes（per ADR-0034 Decision 1）
- **「Auto-approve gate eligibility」**：對應 §4.1 6 條 hard gate；LAL 3/4 永遠不過 gate

### 3.4 Auto-升降 rule

#### Auto-升降階（LAL 1 候選 → LAL 1 active）

**Trigger frequency**：每筆 Advisory approval / rejection 後重算（per ADR-0034 Decision 3 rolling 窗口滑動規則）。

**全 6 條 hard gate 必 PASS**（per §4.1）。

**升階產生 lease**：升階本身 emit 一筆 lease record (lease_type = `lal_upgrade`, payload includes pre-upgrade snapshot + 6-gate evidence)；該 lease 仍經 Guardian gate + 5-gate fail-closed（per §5）。

#### Auto-降階（LAL 1 active → LAL 1 候選）

**Auto-降階 trigger**（任一即降）：

| # | Trigger | 對應 cross-module |
|---|---|---|
| 1 | Strategy 觸發 5-gate kill | 既有 ADR-0008 + Guardian |
| 2 | M7 decay event `DECAY_ENFORCED` | V113 query (`decay_signals` table) |
| 3 | M3 HEALTH_DEGRADED + 該策略屬 affected scope | M3 module spec (cross-ref) |
| 4 | M11 replay divergence > threshold (per CR-7 — 5d empirical noise floor + 2.5-3σ) | M11 module spec (cross-ref) |
| 5 | M8 anomaly event `ANOMALY_CRITICAL` 且 affect 該策略 | M8 module spec (Sprint 1A-γ; cross-ref) |
| 6 | Operator 24h undo button click | per ADR-0034 Decision 5 |

**降階產生 lease**：降階本身 emit 一筆 lease record (lease_type = `lal_downgrade`, payload includes trigger reason + affected scope)；走 Guardian gate（即便降階，audit chain 仍完整）。

#### Manual override path

| 操作 | Auth 要求 | Console 路徑 |
|---|---|---|
| Per-strategy LAL 1 toggle OFF（強制走 manual） | Operator role + 2FA | Console → Strategy Detail → Auto-Approve toggle |
| Per-strategy LAL 2 Y2 toggle OFF | Operator role + 2FA | Console → Allocator → LAL 2 toggle |
| Emergency demote all strategies to LAL 1 候選 | Operator role + 2FA + confirmation modal | Console → Risk Override → Emergency Demote |
| LAL 1 active 強制升 LAL 2（跨 Y1 邊界） | Operator role + 2FA + AMD-2026-05-21-01 cross-ref + Sprint 7 Y2 gate evidence | **不允許**（only Y2 + Console toggle path）|

---

## §4 Eligibility 計算

### 4.1 6 條 hard gate（per ADR-0034 Decision 5；LAL 1+2 only）

**全 6 條必 PASS** 才升 active；任一 fail → fallback 到 LAL 1/2 候選（manual approve）。

| # | Gate | 邏輯 | Data source | Placeholder ref |
|---|---|---|---|---|
| 1 | **Prior approval threshold** | rolling 30d 內 ≥ 30 prior advisory approvals **且** operator_yes_rate > 80% | V112 `lal_eligibility_log` rolling query | V112 placeholder column `yes_rate_observed` + `advisory_sample_observed` |
| 2 | **Incident-free window** | proposal scope 內 last 90d 無 incident (M7 decay / Guardian block / 5-gate kill / operator manual halt / M8 anomaly any) | V113 `decay_signals` JOIN + V109 anomaly + 既有 governance audit log | per V113 + V109 placeholder |
| 3 | **Risk envelope check** | 所有 proposed parameter 在歷史 Stage 4 envelope 內 (per AMD-2026-05-09-03 RuntimeMaxEnvelope) | Rust `risk_envelope` snapshot | per AMD-2026-05-09-03 |
| 4 | **Operator opt-in** | Console toggle = Auto-Approve ON (per ADR-0034 Decision 4) | V112 `decision_lease_lal_tiers` 當前 active row | V112 placeholder column `lal_level` 當前狀態 |
| 5 | **24h undo path 可用** | Pre-proposal snapshot 已 capture + undo handler 健康 | V112 `lal_pre_proposal_config_snapshot jsonb NOT NULL` | per V112 placeholder column |
| 6 | **Post-hoc transparency** | Slack + email + Console notification 三路通知 emit 成功（dry-run pre-check）| 既有 notification pipeline + healthcheck | n/a |

### 4.2 Rolling 30-day yes-rate 計算（per ADR-0034 Decision 3）

```
operator_yes_rate = approvals_yes / (approvals_yes + approvals_no)
        within window: [now() - INTERVAL '30 days', now()]
        WHERE strategy_name = $1
          AND lal_level IN (1, 2)  -- LAL 0/3/4 不計
          AND decision_type IN ('advisory_approved', 'advisory_rejected')
```

**為什麼 rolling 不 lifetime**（per ADR-0034 Decision 3 棄因）：
- Regime change 後 lifetime 失真；早期 high-approval dominate
- Min sample N ≥ 30 protect 早期 N=3 全 yes 噪音誤觸發

**Min sample 不夠時的 behavior**：直接 gate fail → fallback advisory（不是「等湊夠 30 個再升」短路）。

### 4.3 Eligibility evaluation 觸發點

| 事件 | Evaluation 是否觸發 |
|---|---|
| 新 Advisory approval / rejection emit | yes (per §4.2 rolling 窗口滑動規則) |
| M7 decay event emit | yes (incident 90d window 滑動) |
| M3 health status 變化 | yes (gate #3 risk envelope check 不變但 gate #6 transparency check 可能受 health 影響) |
| Console toggle ON/OFF | yes (immediate; gate #4 變動) |
| 每筆 strategy proposal arrival | yes (per-decision evaluation；不依賴 cron) |
| Cron 巡檢 | optional — every 6h backup audit (catch missed event)；不必依賴 |

**反模式禁止**：(a) Eligibility 用 cron 每日 1 次評估 → 漂移 24h；(b) 用 in-memory cache 不查 DB → state 不一致；(c) 用 lifetime 累計（per ADR-0034 Decision 3 棄因）。

---

## §5 Escalation flow + Operator 升級 trigger

### 5.1 異常事件 → LAL 處置 map

| 異常事件 | 初始 LAL 處置 | 升級 trigger（→ operator） |
|---|---|---|
| 單筆 fill 觸 P0 stop | LAL 0 既有 Guardian halt | 不升級（local） |
| Strategy 觸 5-gate kill | LAL 1 active → LAL 1 候選 auto-降階 + emit notification | 連續 3 次降階 7d 內 → 升 operator alert (Slack + Console banner) |
| M7 decay `DECAY_ENFORCED` | LAL 1 降階 + Strategy demote 50% capital 14d review (per CR-7) | 14d review window 結束時必 operator decide (continue demote / restore / retire) |
| M3 `HEALTH_DEGRADED` | LAL 1 reparam halt (per v5.8 §2 M3 line 140) + advisory mode 接管 | HEALTH 持續 DEGRADED > 4h → 升 operator |
| M3 `HEALTH_CRITICAL` | LAL 1+2 全 halt + drain existing positions | 即時 operator alert (highest priority) |
| M11 replay divergence > threshold | LAL 1 affected strategy 降階 + emit divergence log | 連續 3 nights divergence → 升 operator review |
| M8 anomaly `ANOMALY_CRITICAL` (Sprint 1A-γ) | LAL 1+2 affected scope halt + advisory takeover | 持續 anomaly > 6h → 升 operator |
| Operator 24h undo button click | undo 完成 + LAL 1 降階 + audit log | 不升級（operator initiated） |
| LAL 1 連續 7d 內 5 次降階 (任意 trigger) | 自動轉 LAL 1 candidate「冷靜期」（min 14d 無新 advisory 可重新 eligible） | 升 operator review (策略基本面可能變了) |

### 5.2 Operator 升級 SLA + cascade

```
INFO    : 24h 內 operator 認知（Console banner / Slack 1 次通知）— LAL 1 auto-approve event
WARNING : 4h 內 operator 認知（Slack + email；Console persistent banner）— LAL 1 降階 / M7 decay
CRITICAL: 30min 內 operator 認知（Slack + email + push + Console modal）— LAL 2 降階 / M3 HEALTH_CRITICAL
URGENT  : 立即 operator 認知（all channel + 第 2 contact escalation）— 5-gate kill / portfolio cum_loss
```

**Operator inactivity > 60d failsafe**：所有 LAL 1 active 自動降回 LAL 1 候選；LAL 2 active 自動降回 Y1 advisory（per v5.8 §2 M2 OAuto-disable 同模式 — operator 無 ack 60d = 認定 unattended）。

### 5.3 Decision Lease state machine 在 escalation 中的角色

ADR-0008 既有 9 狀態（DRAFT/REGISTERED/ACTIVE/BRIDGED/FROZEN/REVOKED/EXPIRED/REJECTED/CONSUMED）在 LAL escalation 路徑下行為：

| Escalation 事件 | Lease 狀態變化 |
|---|---|
| Auto-approve LAL 1 trigger | Lease emit (DRAFT → REGISTERED → ACTIVE 自動) → Guardian gate → BRIDGED → CONSUMED |
| Auto-降階 trigger | 既有 active lease 不受影響（如已 BRIDGED 不可逆）；新 proposal 走 manual approval |
| Operator 24h undo trigger | 對應 lease 標記 `lal_undone=true`；config snapshot 回滾；fills 已成交不可逆 |
| LAL 2/3/4 manual approve | Lease 走既有 v5.7 路徑（REGISTERED → operator approve → ACTIVE） |
| 5-gate kill trigger | 所有 affected lease REVOKED；新 lease emit 拒絕 |

---

## §6 Reverse attack mitigation（6 條，對齊 AMD-2026-05-21-01 + H-11）

per AMD-2026-05-21-01 + PA consolidation H-11，§11 operator forgetfulness mitigation 6 條反向 attack 必有對應 LAL mitigation：

| # | 反向 attack | LAL mitigation | 落地點 |
|---|---|---|---|
| 1 | **M1 24h undo 已 fill 不可逆** — Operator 以為 undo 可 rollback 已 fill order，但只能 rollback config + risk envelope | per ADR-0034 Decision 5 明示 scope = config + risk envelope only；Console undo button hover tooltip + Slack notification 明示「fills already executed cannot be undone」；undo 完成 page 顯示「N fills retained / config rolled back」明細 | §3.4 Manual override path + §5.1 |
| 2 | **M2 false anomaly trigger** — M8 anomaly false-positive 導致 LAL 1 不必要的降階 cascade | LAL 1 連續降階 cascade 限 cap (7d 內 5 次)；超 cap 自動轉「冷靜期」14d 無新 advisory ineligible (per §5.1)；M8 alert 不直接降階，先 emit alert + 24h grace period | §5.1 §5.2 cascade cap |
| 3 | **M3 healthy market burst FP** — 健康市場高頻 LAL 1 auto-approve 撞 M3 短暫 latency spike → 誤判 HEALTH_DEGRADED → LAL 1 reparam halt → 錯失 alpha | M3 HEALTH_DEGRADED 必持續 ≥ 4 min 才觸發 LAL 1 halt（per CR-7 noise floor 5d empirical 同 spirit）；HEALTH_WARN 不觸發 halt 只 emit alert（per v5.8 §2 M3 line 139） | §3.4 + §5.1 trigger threshold |
| 4 | **M7 14d × 50% 持續虧** — DECAY_ENFORCED 後 50% capital 14d review 期間策略持續虧但未達 retire threshold → operator 漏看 → 累積虧損 | 14d review window 結束時**必** operator decide（per CR-7 escalation）；review window 內每 5d emit Slack + Console banner 摘要；超 14d 無 decision → 自動 retire（fail-safe degradation） | §5.1 升級 trigger |
| 5 | **M8 alpha source vs halt 混淆** — 異常 detection 是 alpha 信號 (e.g., funding rate shock = trade trigger) 還是 halt 信號 (e.g., engine bug)？混淆 → 將 alpha 當 bug halt | M8 anomaly 必標 `anomaly_category` (`market_event` / `engine_bug` / `data_quality`)；只有 `engine_bug` + `data_quality` 觸發 LAL halt；`market_event` 走既有 strategy alpha path（per M8 spec Sprint 1A-γ open Q） | §3.4 trigger #5 + M8 cross-ref |
| 6 | **M11 passive Slack 報告 5d 不被 ack 自動升 M3 HEALTH_WARN** — operator inactivity protection；nightly replay divergence Slack 報告連續 5d 無 ack → 升 M3 HEALTH_WARN → emit cross-channel | M11 nightly divergence emit Slack 每日；5d 內 0 ack → 自動 emit Console banner + email；7d 內 0 ack → 升 M3 HEALTH_WARN trigger（per CR-7 + H-11 第 6 條） | §5.2 cascade 對齊 M11 + M3 cross-ref |

**完整性檢查**：6 條 reverse attack 對應 6 個獨立 mitigation；無遺漏；無 over-claim「all-resistant」。

---

## §7 Cross-module integration

### 7.1 M3 Health-aware degradation integration

| 方向 | 內容 | Touchpoint |
|---|---|---|
| M3 → LAL | HEALTH_DEGRADED → LAL 1 reparam halt；HEALTH_CRITICAL → LAL 1+2 全 halt | per v5.8 §2 M3 line 140 + §5.1 |
| LAL → M3 | LAL 1 連續 7d 內 5 次降階 → 升 M3 HEALTH_WARN（per H-11 mitigation #6） | §5.1 升級 trigger + §6 mitigation #6 |
| Shared schema | M3 health domain stat 從 LAL eligibility evaluation 取 yes_rate / advisory_sample (V112 placeholder column) | V112 `lal_eligibility_log` query |
| Dependency direction | LAL 依賴 M3 (M3 status 是 LAL halt trigger)；M3 不嚴格依賴 LAL（M3 可 standalone）| §10 IMPL phase split |

### 7.2 M7 decay enforcement integration

| 方向 | 內容 | Touchpoint |
|---|---|---|
| M7 → LAL | DECAY_ENFORCED event → LAL 1 affected strategy 降階 (per §3.4 trigger #2) | M7 module spec |
| LAL → M7 | LAL 1 降階事件不反向觸發 M7 decay (避免 amplification loop per E3 medium #4) | n/a |
| Shared schema | LAL eligibility gate #2 「no incident 90d」query M7 `decay_signals` table | V113 placeholder ref |
| Dependency direction | LAL 依賴 M7 (V113 是 gate #2 唯一 data source)；M7 不依賴 LAL | §10 IMPL phase split |

### 7.3 M11 nightly replay divergence integration

| 方向 | 內容 | Touchpoint |
|---|---|---|
| M11 → LAL | Replay divergence > threshold → LAL 1 affected strategy 降階 (per §3.4 trigger #4) | M11 module spec |
| LAL → M11 | LAL 1 active 的 strategy 必入 nightly replay scope；LAL 1 候選 / LAL 2/3/4 也入 scope（M11 不分 LAL level） | M11 module spec |
| Shared schema | M11 `replay_divergence_log` (V107 placeholder) 由 LAL 降階 trigger 讀；M11 不寫 LAL 表 | V107 placeholder ref |
| Dependency direction | LAL 依賴 M11 (M11 是 trigger #4 唯一 source)；M11 不依賴 LAL | §10 IMPL phase split |

### 7.4 M8 anomaly integration（Sprint 1A-γ）

| 方向 | 內容 | Touchpoint |
|---|---|---|
| M8 → LAL | ANOMALY_CRITICAL + `engine_bug` / `data_quality` category → LAL 1+2 halt (per §3.4 trigger #5 + §6 mitigation #5) | M8 module spec Sprint 1A-γ |
| LAL → M8 | n/a (M8 不消費 LAL stat) | n/a |
| Shared schema | LAL eligibility gate #2 incident-free check JOIN V109 `anomaly_events` table | V109 placeholder ref |
| Dependency direction | LAL 依賴 M8 (gate #2 + trigger #5)；M8 不依賴 LAL | §10 IMPL phase split |

### 7.5 M9 A/B framework integration（Sprint 1A-γ）

| 方向 | 內容 | Touchpoint |
|---|---|---|
| M9 → LAL | M9 variant promotion to Stage 4 走 LAL 3 operator approval path (per ADR-0037)；M9 Y2 enable gate fail → LAL 2 降階 (per §3.4 trigger #4 for LAL 2) | M9 module spec Sprint 1A-γ |
| LAL → M9 | n/a (M9 不消費 LAL stat) | n/a |
| Dependency direction | LAL 依賴 M9 (LAL 3 promotion 路徑)；M9 依賴 LAL (variant promote 必經 LAL gate) | bidirectional — 須 Sprint 1A-γ 對齊 |

---

## §8 5-gate compliance（LAL 不繞 5-gate）

**核心斷言**：LAL gate 在 Decision Lease emit 後分流，**不繞 5-gate fail-closed**（per CLAUDE.md §四 + ADR-0034 Consequences）。

### 8.1 5-gate vs LAL gate 層次圖

```
┌────────────────────────────────────────────────────┐
│   Strategy / Allocator AI 產出 proposal            │
└────────────────────────────────────────────────────┘
                       │
                       ▼
┌────────────────────────────────────────────────────┐
│   Decision Lease emit (DRAFT → REGISTERED)         │
│   (ADR-0008 既有 schema; lease_id / payload_hash)  │
└────────────────────────────────────────────────────┘
                       │
                       ▼
┌────────────────────────────────────────────────────┐
│   ★ LAL gate 分流（本 module 新增）★               │
│   - LAL 0: 既有 Guardian auto                      │
│   - LAL 1+2: 6 hard gate (per §4.1) →              │
│       PASS: auto-sign by gate                      │
│       FAIL: fallback advisory (operator approve)   │
│   - LAL 3+4: operator approve only                 │
└────────────────────────────────────────────────────┘
                       │
                       ▼
┌────────────────────────────────────────────────────┐
│   ADR-0008 Guardian gate (risk envelope + 5-gate)  │
│   (LAL 不繞 — LAL approve = lease signed，         │
│    但 lease 仍經 Guardian + 5-gate fail-closed)    │
└────────────────────────────────────────────────────┘
                       │
                       ▼
┌────────────────────────────────────────────────────┐
│   Live 5-gate（CLAUDE.md §四）：                   │
│   1. Python live_reserved=True                     │
│   2. Operator role auth                            │
│   3. OPENCLAW_ALLOW_MAINNET=1                      │
│   4. Valid secret slot                             │
│   5. Signed unexpired authorization.json           │
│      環境 matched                                  │
│   (任一 fail → fail-closed; LAL auto-approve 不繞)  │
└────────────────────────────────────────────────────┘
                       │
                       ▼
┌────────────────────────────────────────────────────┐
│   Bybit submit (mainnet)                           │
└────────────────────────────────────────────────────┘
```

### 8.2 LAL auto-approve path 與 5-gate 關係

| 5-gate # | LAL auto-approve 是否繞 | 理由 |
|---|---|---|
| 1. `live_reserved=True` | **不繞** | LAL 是 Lease 層；live_reserved 是 Python execution authority 層；正交 |
| 2. Operator role auth | **不繞** | LAL 1/2 auto-approve 不要求 per-decision operator role，但 5-gate 仍要求 Python live_reserved + role；LAL 在更上游 |
| 3. `OPENCLAW_ALLOW_MAINNET=1` | **不繞** | env var 是 spawn 時 check；LAL 不能改 env |
| 4. Valid secret slot | **不繞** | LAL 不接觸 secret store |
| 5. Signed authorization.json | **不繞** | LAL 不能 sign authorization.json（per ADR-0034 Decision 4 toggle auth 與 authorization.json 不同層） |

**結論**：LAL 是 lease 層的 approval gate；5-gate 是 execution 層的 fail-closed；正交且 LAL 永不能繞 5-gate。

### 8.3 Mainnet 通道 fail-closed 保證

| 場景 | 行為 |
|---|---|
| LAL 1 auto-approve 但 Python `live_reserved=False` | Lease signed 但 execution fail-closed（既有 ADR-0008 + 5-gate） |
| LAL 2 auto-approve 但 `OPENCLAW_ALLOW_MAINNET=0` | Lease signed 但 engine spawn 拒絕 mainnet → fail-closed |
| LAL 3 operator approve 但 authorization.json expired | 5-gate fail；execution 拒絕；LAL approve 不能 override |
| LAL gate 全 PASS + 5-gate 全 PASS | Execution proceed |

---

## §9 Acceptance criteria（DESIGN 級 7 條）

| # | AC | 驗收方式 | Sign-off |
|---|---|---|---|
| **AC-1** | **5 LAL state machine proptest 覆蓋** — 升降 transition + invalid transition rejected + dead-state scan + Eligibility gate proptest（6 條 hard gate 任一 fail → fallback advisory）| `cargo test --workspace -- --include-ignored` 含 LAL proptest module；coverage > 95% on lal_state_machine.rs | E4 Sprint 4 |
| **AC-2** | **單元測試覆蓋率** — LAL eligibility evaluation / rolling 30d yes-rate / 6 hard gate / auto-降階 trigger 全覆蓋；測試 mock V112 / V113 / V109 schema query | `cargo tarpaulin` 或 `pytest-cov` > 90% on LAL business logic 模組 | E4 Sprint 4 |
| **AC-3** | **IPC schema 對齊** — Rust LAL event emit 對應 Python consumer schema bit-exact; cross-language fixture harness 1e-4 容差驗 LAL event payload；含 `lal_upgrade` / `lal_downgrade` / `lal_eligibility_evaluated` 三 message type | E4 cross-language fixture harness（per H-18） | E4 + QA Sprint 4 |
| **AC-4** | **LAL Tier 3+4 manual approval audit log** — 每筆 LAL 3 + LAL 4 approval 含 operator_id / 2FA verification result / pre-approve snapshot / approve_ts；audit log query 可重建 100% LAL 3/4 history | E2 audit + QA acceptance；query 範例：「last 30d 所有 LAL 3 approval by operator_id」必返回完整列表 | QA Sprint 4 |
| **AC-5** | **反向 attack 6 條測試** — 6 條 reverse attack 每條對應 1 條 acceptance test (M1 undo 範圍 / M2 cascade cap / M3 4-min threshold / M7 14d auto-retire / M8 category 區分 / M11 5d ack escalation)；測試 inject mock event + 觀察 LAL state + alert emit | `pytest tests/acceptance/test_lal_reverse_attack.py` 6 test PASS | E4 + QA Sprint 4 |
| **AC-6** | **5-gate non-bypass test** — LAL auto-approve + Python `live_reserved=False` 場景必 fail-closed；3 個 mainnet bypass attempt (env unset / authorization expired / role missing) × 3 LAL level (0/1/2) = 9 test PASS | `pytest tests/integration/test_lal_5gate_compliance.py` 9 test PASS | E3 + QA Sprint 4 |
| **AC-7** | **Console toggle auth + 24h undo end-to-end test** — Console toggle ON 要求 Operator role + 2FA + post-hoc notification；24h undo button click → snapshot restore + audit log emit；驗 toggle audit table `lal_toggle_audit` 有 record；驗 fills 不被 undo（顯示「N fills retained」訊息） | A3 E2E test + E1a GUI test；E2E 用 selenium / playwright（per A3 工時 §CR-11） | A3 + QA Sprint 4 |

---

## §10 IMPL phase split + 估時

| Sprint | LAL level IMPL | 工作內容 | 估時 | Owner |
|---|---|---|---|---|
| **Sprint 1A-β** | DESIGN only | 本 spec doc + V112 schema + ADR-0034 land | 60-80 hr (本 spec ~12-18 hr; V112 ~ 20-30 hr; ADR ~ 12-18 hr 已 ADR-0034 draft；E2/QA review) | PA + MIT + CC + QA |
| **Sprint 4** | **LAL 0 (既有) + LAL 1 IMPL** | (a) Rust LAL state machine + eligibility evaluator (b) V112 table writer (c) Console toggle GUI (d) 24h undo handler (e) Slack/email/Console notification emit (f) §9 AC-1-AC-7 test (g) Sprint 4 Live precondition gate（受 P0-EDGE-1 + P0-LG-3 + P0-OPS-1..4 阻塞 — per CR-10）| 40-60 hr engineering + ~20-30 hr GUI (per CR-11 261-374 GUI 工時) | E1 + E1a + A3 + E3 + E4 + QA |
| **Sprint 7-8** | **LAL 2 IMPL Advisory only (Y1)** | (a) Allocator advisory mode（既有 v5.7 §7 sustain）(b) LAL 2 eligibility tracking (rolling 6mo Allocator approval rate) (c) Console LAL 2 toggle UI（default OFF 灰）(d) Audit log extend；**Y1 不 enable auto** | 50-70 hr engineering + ~15-20 hr GUI | E1 + E1a + A3 + E3 + E4 + QA |
| **Y2 Q1-Q2** | **LAL 2 auto-execution enable** | (a) Y2 enable gate evaluation (Allocator approval rate > 80% 6mo + 6 hard gate)（b) Console LAL 2 toggle UI activate（operator opt-in path 開啟） (c) M9 A/B Y2 enable gate cross-check (d) Sprint 10 Y1 Review evidence land | 30-50 hr engineering + ~10 hr GUI | E1 + A3 + E3 + E4 + QA + PM (Y2 gate sign-off) |
| **n/a** | **LAL 3 + LAL 4 永遠 operator approve** | **no auto IMPL ever**；既有 v5.7 manual approve path 適用；LAL 3/4 audit log extend (AC-4)；Console manual approve UI 含 LAL level 顯示 | 既有 v5.7 path + ~5-10 hr LAL label extend | E1a + A3 (Sprint 4) |

**Sprint 4 IMPL precondition**（per CR-10）：
- P0-EDGE-1 closure（structural alpha-deficient cluster 完成 phase B/C/D；A 群 placeholder）
- P0-LG-3 closure（live gate ops 完成）
- P0-OPS-1..4 closure（4 條 ops blocker）
- 5-gate live readiness（per CLAUDE.md §四）

任一未 land → LAL 1 IMPL fallback 為「Demo + LiveDemo only」auto-approve；Mainnet path 自動延後（per CR-10 §12 operator decision 第 5 條）。

---

## §11 Cross-V### dependency graph + sequencing

```
        ┌──────────────────┐
        │ V112 (M1 LAL)    │  ← own table; Sprint 1A-β
        │ - decision_lease │
        │   _lal_tiers     │
        │ - lal_eligibility│
        │   _log           │
        │ - lal_toggle     │
        │   _audit         │
        └─────────┬────────┘
                  │ JOIN gate #2
                  ▼
        ┌──────────────────┐
        │ V113 (M7 decay)  │  ← Sprint 1A-β (parallel)
        │ - decay_signals  │
        └──────────────────┘

        ┌──────────────────┐
        │ V109 (M8 anomaly)│  ← Sprint 1A-γ
        │ - anomaly_events │
        └─────────┬────────┘
                  │ JOIN gate #2 (incident scope expand)
                  ▼
        ┌──────────────────┐
        │ V112 (re-query)  │  ← LAL eligibility 重評時
        └──────────────────┘

        ┌──────────────────┐
        │ V107 (M11 replay │  ← Sprint 1A-β (parallel)
        │   divergence)    │
        └─────────┬────────┘
                  │ Read by LAL auto-降階 trigger #4
                  ▼
        ┌──────────────────┐
        │ V112 (write LAL  │
        │   downgrade)     │
        └──────────────────┘
```

**Sequencing constraint**：

1. V112 land 必先於 LAL 1 IMPL (Sprint 4) — LAL 業務邏輯依賴 V112 schema
2. V113 land 必先於或與 V112 並行（Sprint 1A-β）— 否則 gate #2 incident-free check 無 data source
3. V107 land 必先於 LAL 1 IMPL (Sprint 4) — 否則 auto-降階 trigger #4 無 source
4. V109 land 可後於 V112 (Sprint 1A-γ) — gate #2 incident scope 可 phased expand
5. **Sprint 1A-β/γ 不可無條件並行**（per CR-9 + E5）：V112 → V113 / V107 必先；V109 後跟

**Placeholder column 引用**（本 spec 不假設 final DDL；以 V112 spec doc 為準）：
- `learning.decision_lease_lal_tiers.lal_level` ← per V112 placeholder（修正方向 per §Open Q1）
- `learning.decision_lease_lal_tiers.lal_pre_proposal_config_snapshot` ← per V112 placeholder
- `learning.lal_eligibility_log.yes_rate_observed` ← per V112 placeholder
- `learning.lal_eligibility_log.advisory_sample_observed` ← per V112 placeholder
- `learning.lal_eligibility_log.incident_free_check_pass` ← per V112 placeholder
- `learning.lal_toggle_audit.from_lal_level` / `to_lal_level` ← per V112 placeholder

---

## §12 Open Questions（≥3 條供 Sprint 1A-γ/δ 補答）

### Q1 [CRITICAL] V112 placeholder LAL 0-4 語義方向錯誤 — 必 MIT 修正

**問題**：V112 spec doc (`2026-05-21--v112_m1_decision_lease_lal_tiers_schema_spec.md` §1.1) 描述 LAL 為：

> 「LAL 0 = full manual approval / LAL 1 = governance auto-approve / LAL 2 = governance bypass-with-audit / LAL 3 = full auto / LAL 4 = bypass even audit (emergency only)」

**這與 ADR-0034 LAL ↔ Stage 對齊表反向**：

- ADR-0034: LAL 0 = per-fill autonomous (always) / LAL 4 = capital structure change (永遠 operator approve)
- V112 placeholder: LAL 0 = full manual / LAL 4 = bypass even audit

**影響**：CHECK constraint `lal_level ∈ {0,1,2,3,4}` 不出錯，但「LAL 3+ 是 full auto」的 partial index 完全與 ADR-0034 語義反向。

**Owner**：MIT (V112 spec doc owner) Sprint 1A-β 必修正。

**Resolution path**：以 ADR-0034 為準（authoritative per CLAUDE.md §五）；V112 spec doc §1.1 + 所有 placeholder column comments 重寫；本 spec doc 不需重寫（本 spec 已對齊 ADR-0034）。

### Q2 [HIGH] LAL 1 auto-升階是否 emit lease？

**問題**：本 spec §3.4 主張「升階產生 lease (lease_type = `lal_upgrade`)」，但 ADR-0034 Decision 1 主要描述 per-decision lease（i.e., strategy proposal）必 emit。升階事件本身是否算 decision？

**選項**：
- **(a) 升階 emit lease** — audit trail 完整；可 replay；但會增加 lease count
- **(b) 升階只寫 toggle_audit + eligibility_log，不 emit lease** — schema 簡潔；但升階決策無法走 Guardian / Router

**PA 推薦**：**(a)**（一致性；升階是治理決策，應走 lease 路徑）

**Owner**：CC + QA Sprint 1A-β confirm；如選 (b) 需更新本 spec §3.4 + V112 schema。

### Q3 [HIGH] M8 anomaly category 區分（mitigation #5）是否在 Sprint 1A-γ M8 spec land？

**問題**：§6 mitigation #5「M8 anomaly 必標 `anomaly_category` (`market_event` / `engine_bug` / `data_quality`)」需 M8 module spec 落地此 column；目前 M8 spec 仍 Sprint 1A-γ pending（per PA consolidation §2.4）。

**Owner**：M8 spec owner (PA + MIT Sprint 1A-γ) confirm `anomaly_category` 在 V109 schema 中；若 M8 spec 不 land 此設計 → 本 spec §6 mitigation #5 + §3.4 trigger #5 + §7.4 cross-ref 需重設計。

**Fallback**：M8 spec 若決定不分 category，本 spec §3.4 trigger #5 改為「M8 ANOMALY_CRITICAL 一律 24h grace period 然後 operator decide」（更保守）。

### Q4 [MEDIUM] LAL 2 Y2 enable gate 與 M9 A/B Y2 enable gate 並聯 / 串聯？

**問題**：LAL 2 Y2 auto-enable 與 M9 A/B Y2 enable 同時段（Y2 Q1-Q2）；二者 gate 條件部分重合（M9 variant promotion + LAL 2 cross-strategy reweight）。

**選項**：
- **(a) 並聯**：LAL 2 enable 與 M9 enable 各自獨立 evaluate；任一 enable 後直接 active
- **(b) 串聯**：LAL 2 enable 要求 M9 Y2 enable 已 active；M9 fail → LAL 2 不能 enable

**PA 推薦**：**(b) 串聯**（更保守；M9 是 variant promotion 紀律 base，LAL 2 是上層 autonomy）

**Owner**：QA + QC Sprint 1A-γ + Y2 Q1 PM 仲裁；如選 (a) 需更新本 spec §3.4 LAL 2 升階條件 + §7.5。

### Q5 [MEDIUM] Cron 巡檢 backup eligibility 是否必要？

**問題**：§4.3 列「Cron 巡檢 every 6h backup audit」為 optional；是否 mandatory？

**Trade-off**：
- mandatory → 多一層 safety；但增加 PG query cost
- optional → 業務邏輯為主；event-driven 已覆蓋 99%

**PA 推薦**：**Sprint 4 IMPL 階段先 optional**；Y2 LAL 2 enable 時改 mandatory（cross-strategy reweight 風險高，需 backup audit）

**Owner**：E5 Sprint 4 IMPL phase confirm；可 toggle via feature flag。

### Q6 [LOW] LAL 1 候選 → LAL 1 active toggle UI 顆粒度

**問題**：Console「Auto-Approve On」toggle 是 per-strategy 還是 per-strategy × per-LAL-level？

**選項**：
- **(a) per-strategy single toggle**：簡單；strategy 一旦 toggle ON 適用所有 LAL level (1+2)
- **(b) per-strategy × per-LAL-level**：精細；strategy 可只 toggle LAL 1，LAL 2 仍 advisory

**PA 推薦**：**(b)**（per ADR-0034 Decision 4 「per strategy / per LAL level 顆粒度」明示）

**Owner**：A3 Sprint 4 IMPL phase confirm UI mockup；對齊 v5.8 §2 M1 line 76 「per strategy / per LAL level 顆粒度」。

---

## §13 Sign-off

| Role | 範圍 | Status |
|---|---|---|
| Operator | LAL 改名已批 (D2 2026-05-21) | ✅ 既有 ADR-0034 cover |
| PA | 本 spec 起草 (Sprint 1A-β CRITICAL module DESIGN) | ✅ 2026-05-21 |
| MIT | V112 schema final DDL land + V112 spec doc §1.1 修正反向語義 (per Open Q1) | 🟡 PENDING Sprint 1A-β |
| CC | 5-gate auto path inheritance 對齊 (per CR-15) + Open Q2 confirm | 🟡 PENDING Sprint 1A-β |
| QA | LAL ↔ Stage 對齊矩陣對齊驗 + §9 AC-1-AC-7 sign-off | 🟡 PENDING Sprint 1A-β + Sprint 4 |
| E4 | §9 AC-1 + AC-2 + AC-3 + AC-5 + AC-6 test land | 🟡 PENDING Sprint 4 |
| E3 | §8 5-gate non-bypass test land + Console toggle auth integration | 🟡 PENDING Sprint 4 |
| A3 | §9 AC-7 E2E test + Console toggle UI mockup + 24h undo hover tooltip | 🟡 PENDING Sprint 4 |
| FA | LAL eligibility gate #2 incident-free window 定義 review (per ADR-0034 sign-off) + §5.1 升級 trigger threshold 量化 | 🟡 PENDING Sprint 1A-β |
| E1 | Sprint 4 LAL 1 IMPL owner | 🟡 PENDING Sprint 4 |
| PM | LAL 1 → LAL 2 Y2 enable gate 仲裁 (Y2 Q1) + Open Q4 仲裁 | 🟡 PENDING Y2 Q1 |

---

**END M1 LAL Layered Approval Lease Module DESIGN Spec**

**Cross-References**：
- ADR-0034 (M1 LAL) — Decision 1-5 + LAL ↔ Stage 對齊表
- ADR-0008 (Decision Lease state machine baseline) — 9 狀態 lifecycle
- ADR-0016 (Decision Lease Router evidence mode) — Router 不繞
- AMD-2026-05-15-01 (Canary Rebase Replay Preflight Stage 0R-4) — Stage 命名來源
- AMD-2026-05-21-01 (autonomy-vs-human-final-review) — 6 hard gate motivation
- AMD-2026-05-09-03 (Strategist Wide-Adjustment Skill) — gate #3 RuntimeMaxEnvelope
- V112 spec doc (`docs/execution_plan/2026-05-21--v112_m1_decision_lease_lal_tiers_schema_spec.md`) — own table; PLACEHOLDER 反向修正 per Open Q1
- V113 spec doc (M7 decay) — gate #2 source
- V107 spec doc (M11 replay divergence) — trigger #4 source
- V109 spec doc (M8 anomaly) — gate #2 expand + trigger #5 source (Sprint 1A-γ)
- M3 module spec — HEALTH_DEGRADED trigger
- M7 module spec — DECAY_ENFORCED trigger
- M11 module spec — divergence threshold (per CR-7 5d noise floor)
- M8 module spec — anomaly_category column (per Open Q3; Sprint 1A-γ)
- M9 module spec — Y2 enable gate (per Open Q4; Sprint 1A-γ)
- CLAUDE.md §四 Hard Boundaries — 5-gate fail-closed
- CLAUDE.md §二 Root Principles — 16 條對齊（per ADR-0034 §16 walkthrough）
- feedback_no_dead_params — LAL eligibility 必真實 evaluate 不可 stub
- feedback_minimal_confirmation — Operator 不要反復確認；6 hard gate 通過即 auto
- PA consolidation report (`docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-21--v58_dispatch_consolidation.md`) §Sprint 1A-β + §6 cross-V### dependency
- PM final verdict (`docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-21--v58_pm_final_verdict.md`)
