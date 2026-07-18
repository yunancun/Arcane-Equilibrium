---
spec: Monthly Operator Review Wizard + Lv3-4 Modal Helper Scope Spec
date: 2026-05-21
author: A3 inline draft (a12c302e) → PM transcribed (A3 tool boundary: 禁 Write/Edit)
phase: v5.8 Sprint 1A-ε CRITICAL DESIGN
status: SPEC-DRAFT-V0 — DESIGN APPROVE；移交 E1a IMPL Sprint 4 first Live 前 land basic shell
parent specs:
  - docs/CCAgentWorkSpace/A3/workspace/reports/2026-05-21--v58_executability_audit.md §0.6 §5 §8
  - docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-21--v58_dispatch_consolidation.md §2 Sprint 1A-ε
  - docs/governance_dev/amendments/2026-05-21--AMD-2026-05-21-01-autonomy-vs-human-final-review.md
  - docs/adr/0034-decision-lease-layered-approval-lal.md
  - docs/adr/0042-m3-health-monitoring.md (R4 audit pending C-1 collision fix；可能 renumber)
  - docs/adr/0044-m7-decay-enforced-single-authority.md
scope: design scope spec only — 不寫 IMPL HTML/JS/CSS；E1a Wave 1+2 IMPL phase
verdict: DESIGN APPROVE — A3 16-24 hr Wizard + 8-12 hr modal helper = 24-36 hr Y1 sign-off；E1a IMPL 70-95 hr Y1
---
> ⚠️ 归档历史文档 — 非当前权威。active 状态见 repo 根 `TODO.md`；本文件仅供历史/审计参考。（2026-07-18 审计批量补入）


# Monthly Operator Review Wizard + Lv 3-4 Modal Helper Scope Spec

## §1 Context + 為什麼

### 1.1 兩個 deliverable 為什麼合併

Monthly Wizard 與 Lv 3-4 Modal Helper 共用同一套 design token / audit trail / cooldown infrastructure / operator cognition target。分 spec 會產生兩套冗餘 copy + helper / 兩次 review。合併 Sprint 1A-ε 一次 land 一致設計語言。

### 1.2 為什麼此 spec 是 Sprint 1A-ε（非 Sprint 4 前 hot fix）

- Monthly Wizard 真正 data feed 在 Sprint 5-7 才 ready（M3/M6/M9/M11 active）
- Lv 3-4 modal helper 必在 Sprint 4 first Live 前 land basic shell（M1 LAL Tier 1 + 5-gate mainnet auth 需要）
- Spec Sprint 1A-ε frozen；IMPL 分 Wave 1 (Sprint 4 前) + Wave 2 (Sprint 7+)

### 1.3 三個直接觸發此 spec 的 finding

1. A3 v5.8 audit Risk 3：Sprint 7 末 ~25 attention items，遠超 ux-checklist 維度 2「單頁 ≤ 7」
2. W-AUDIT-7c lexical scope shadow（per `feedback_gui_node_check_sop`）：GUI sign-off 必 `node --check`
3. AMD-2026-05-21-01 protected scope：Lv 4 永不可繞 — 必有不可繞 modal + cooldown + 2FA

---

## §2 Monthly Operator Review Wizard scope

### 2.1 設計目標

| 目標 | 量化指標 |
|---|---|
| Operator 每月 audit dwell time | 30-60 min total（首屏 ≤ 5 min OK 燈批次 ack）|
| 認知負荷 | 首屏 attention items ≤ 7（per ux-checklist 維度 2）|
| 摺疊規則 default | 只展開 DEGRADED + CRITICAL；OK 預設摺疊（per `feedback_minimal_confirmation`）|
| 13 module × 4 metric coverage | 100% |
| Y1 末 Copy Trading Evidence Gate 數據準備 | ADR-0030 8 attribute 一鍵 export |

### 2.2 13 module × 4 metric Traffic-light Dashboard

| Metric | 顏色語義 | Data source |
|---|---|---|
| **Live PnL (30d)** | 綠 + / 紅 − / 黃 ±10% within zero / 灰 no data | `trading.fills` + `trading.attribution_chain` |
| **Decay State (M7)** | 綠 NORMAL_LIVE / 黃 DECAY_REVIEW / 紅 DECAY_ENFORCED / 黑 RETIRE | V113 |
| **A/B Variant Winner (M9)** | 綠 winner confirmed / 黃 inconclusive 7d / 紅 no-significance 14d+ / 灰 no test | V108 |
| **Health (M3)** | 綠 HEALTHY 5/5 / 黃 WARN 1+ / 橙 DEGRADED 2+ / 紅 CRITICAL ≥3 or 1 ≥24h | V106 |

**首屏壓縮**：13 × 4 = 52 cell；default collapsed 只顯示 DEGRADED + CRITICAL + 黑（≤ 5 rows / 20 cells）。

### 2.3 摺疊規則（per `feedback_minimal_confirmation`）

```
default:           only DEGRADED + CRITICAL + 黑（M7 RETIRE / M3 CRITICAL / M11 large divergence）
operator click:    「展開所有 OK」一鍵展開 52 cell 完整視圖
operator click:    per-row「展開該 module 詳情」進入 drilldown
hidden behind click (never default 展開):
  - Pending Lease List（M1 Tier 1/2/3 等待清單）
  - Reward Weight Change History（M6 30d log）
  - A/B Test Details（M9 mSPRT statistics）
  - Replay Divergence Daily Report（M11 7d trend）— 反 FOMO 絕禁首屏
```

### 2.4 Y1 末 Copy Trading Evidence Gate input data prep (per ADR-0030)

Sprint 10 W37+ 解鎖 8 attribute 一鍵 export（CSV + PDF）：30d net APR / Sharpe / Max DD / Attribution chain ≥ 95% / M11 divergence < 5 bps / M3 HEALTHY ≥ 95% / M7 0 RETIRED 30d / Operator click Lv 4 modal 確認。

### 2.5 月報 cron + delivery + ACK

| 維度 | Spec |
|---|---|
| Cron 觸發 | 每月 1 日 UTC 09:00（與 ml-training-maintenance 錯峰）|
| 預覽 link 有效期 | 7 day |
| Delivery | (a) Console badge 必 (b) email 必 (c) Slack 選（per Open Q4）|
| Dwell time telemetry | Wizard 內收集；月匯總 `agent.audit_log` |
| ACK 機制 | Operator click「本月 review 完成」→ `governance.monthly_review_ack`；未 ack 90d → M3 HEALTH_WARN（per AMD §6）|

### 2.6 中文 first copy（per `feedback_chinese_output`）

```
Wizard title    : 「月度操作員審計 / Monthly Operator Review」
Section: PnL    : 「30 天淨損益 / 30d Net PnL」
Section: Decay  : 「策略衰減狀態 / Strategy Decay State」
Section: A/B    : 「A/B 測試勝出方 / A/B Variant Winner」
Section: Health : 「健康域 / Health Domains」
Collapse btn    : 「展開全部 / Expand All」「僅顯示異常 / Show Critical Only」
ACK btn         : 「本月 review 完成 / Review Acknowledged」
```

---

## §3 Lv 3-4 Modal Helper Unified Design

### 3.1 LAL Tier ↔ Modal Lv 對齊表（per ADR-0034 + AMD-2026-05-21-01）

| LAL Tier | Modal Lv | Operator 認證 | Cooldown | 2FA | Audit signed file |
|---|---|---|---|---|---|
| LAL 0（per-fill）| Lv 0 | none | 0 | × | × |
| LAL 1（intra-strategy reparam）| Lv 2 | Operator role | 0 | × | × |
| LAL 2（cross-strategy reweight）| Lv 3 | + reason field | 12h | × | × |
| LAL 3（strategy promotion）| **Lv 3** | + reason + typed phrase | 12h | × | × |
| LAL 4（capital structure / venue / Tier 2 enable Auto / RETIRE）| **Lv 4** | + reason + typed phrase + 2FA TOTP | 24h | ✓ | ✓ HMAC-signed attestation file |

本 spec 只覆蓋 Lv 3 + Lv 4。

### 3.2 Lv 3 Modal Spec

**Base = 擴展現有 `openTypedConfirmModal`（per `common-modals.js:339`）**；不重寫 infra。

新增欄位：
- `reasonRequired: true / reasonMinChars: 20 / reasonHint: '請描述本次決策依據...'`
- `cooldownSec: 0`（Lv 3 default；同 lease_id 內 12h 由 backend enforce）
- `auditTag: 'LAL_TIER_3'`

**Reason field 驗**：mandatory non-empty + trim ≥ 20 chars；不接受純空白 / 純標點 / 純複製 lease_id；失敗 → toast「請描述本次決策依據（≥ 20 字）」。

**Backend gate (per CR-15 5-gate auto path inheritance)**：Operator role auth + Console toggle ON + 5/5 gate green + 同 lease_id 12h cooldown not violated → 任一 fail backend reject + toast `LAL_TIER_3_GATE_FAIL`。

### 3.3 Lv 4 Modal Spec

**Base = Lv 3 + 三項增強**：
1. **2FA TOTP**：Settings tab 註冊；6-digit OTP input；backend 驗（secret 不下發前端）；failed 3 次 → 15 min lock + alert
2. **Cooldown 24h**：同 surface 內 operator 不可在 24h 內再次觸發同 Lv 4 action
3. **HMAC-signed attestation file**：`$OPENCLAW_SECRETS_DIR/attestations/<surface>/<ts>--<actor>.json`；HMAC-SHA256（surface + actor + ts + reason + lease_id + nonce）；reference 寫 `governance.lal_4_attestations` + `agent.audit_log`；不刪除（Y2 audit recovery）

**Backend gate (per AMD-2026-05-21-01 protected scope)**：全 Lv 3 條件 + Operator inactivity < 60d → 任一 fail backend reject + toast `LAL_TIER_4_PROTECTED_SCOPE_FAIL`。

### 3.4 統一 helper API（E1a IMPL 階段範例）

```js
openLalModal({
  tier: 3 | 4,
  surface: 'M1_LAL_TIER_3_PROMOTE',
  title: '...',
  body: '...',
  phrase: '...',
  reasonMinChars: 20,
  actor: 'op:cloud@ncyu.me',
  impact: '...',
  rollback: 'governance.lal_undo(lease_id, undo_window=24h)',
  cooldownKey: 'M1_LAL_3:grid_v1',
  // Lv 4 only:
  otpRequired: tier === 4,
  attestationOutDir: '$OPENCLAW_SECRETS_DIR/attestations/M1_LAL_4_TIER_2_ENABLE',
}).then(result => { /* { ok, reason, otp_verified, attestation_path, lease_id } */ });
```

### 3.5 反 fake-success / 反 fail-open

- **絕禁** `confirm() / prompt()` browser-native fallback
- **絕禁** 前端「假成功 → 後端 fail-open」（per `feedback_no_dead_params`）
- **後端錯誤必直接顯示**：modal 內保留「最近 5 次 actor + ts + 結果」尾錄
- **trace_id 顯示**：confirm 成功後 toast 含 trace_id
- **Engine 斷連阻擋**：Lv 4 ALL surface engine disconnected 時禁用 + tooltip「Engine 未連接」

---

## §4 8 Lv 3-4 Surface 對應表

| # | Surface | LAL Tier | Modal Lv | 對應模組 / ADR | typed phrase | cooldown | Sprint | Console tab | hr |
|---|---|---|---|---|---|---|---|---|---|
| **S1** | M1 LAL Tier 3 strategy promotion | LAL 3 | Lv 3 | M1 / ADR-0034 | `PROMOTE <strategy_id>` | 12h | Sprint 4 + 7 | governance → Lease Tier | 4 |
| **S2** | M1 LAL Tier 4 capital structure (Tier 2 enable Auto) | LAL 4 | Lv 4 | M1 / ADR-0034 + AMD | `ENABLE AUTO LAL TIER 2 FOR <scope>` | 24h | Sprint 7 + Y2 | governance → Lease Tier | 6 |
| **S3** | M3 HEALTH_CRITICAL operator unlock | LAL 3 | Lv 3 | M3 / ADR-0042 | `UNLOCK <domain>` | 12h | Sprint 5 | system → Health Domains | 4 |
| **S4** | M7 DECAY_ENFORCED → NORMAL_LIVE | **BLOCKED per AMD protected scope** | N/A | M7 / ADR-0044 + AMD | — | — | — | UI disabled + tooltip | 2 (negative UI) |
| **S5** | M10 Tier change (capital tier activation) | LAL 4 | Lv 4 | M10 / ADR-0036 | `ACTIVATE TIER <X>` | 24h | Sprint 10 + Y2-Y3 | system → Capital Tier | 5 |
| **S6** | M13 venue change (per ADR-0040 6 gate) | LAL 4 | Lv 4 | M13 / ADR-0040 | `ENABLE VENUE <venue_name>` | 24h per venue | Y2-Y3（Binance Y3+）| settings → Venues | 6 |
| **S7** | 5-gate live mainnet authorization | LAL 4 | Lv 4 | CLAUDE.md §四 | `AUTHORIZE LIVE MAINNET` | 24h | Sprint 4 first Live | governance → Decision Lease | 4-5 |
| **S8** | Earn Asset Movement (per ADR-0032) | LAL 4 | Lv 4 | ADR-0032 | `MOVE <amount> <asset> <src→dst>` | 24h per asset+dir | Sprint 1B-3 | governance → Earn Movement | 5 |

**A3 sign-off 工時 Y1**：S1-S8 合計 36.5 hr + Monthly Wizard 7-9 hr + spec maintenance 4-7 hr = **48-53 hr** (per A3 v5.8 audit §5)

**S4 BLOCKED 設計理由**：per AMD-2026-05-21-01 §1 protected scope；M7 14d × 50% 自動 review window 是 forgetfulness 反向 attack 第 4 條 mitigation 硬基石。允許 override → DECAY_ENFORCED gating 變心理門檻而非物理。UI 必明示 disabled + tooltip + Wizard 顯 14d window 倒數。

---

## §5 Acceptance Criteria

| AC | 描述 | 驗證 | Sprint gate |
|---|---|---|---|
| **AC-1** | Monthly Wizard 6 metric pass A3 audit (4 metric + Copy Trading prep + cron + ACK + dwell time + 摺疊規則) | A3 dry-run mock + 5 維度 ux-checklist | Sprint 7 first activation；Sprint 10 末 Copy Trading prep gate |
| **AC-2** | Lv 3-4 modal helper 8 surface coverage 100% (S1-S8) | 8 surface E2E (含 backend gate fail + cooldown 違規 + 2FA fail + attestation file 寫盤) | Sprint 4 前 S1/S7 + Sprint 7 前 S2/S3 + Sprint 10 前 S5 + Y2 前 S6 + Sprint 1B-3 S8 |
| **AC-3** | Cooldown enforce Rust + Python audit log (前端不可繞；backend reject + audit log) | Rust integration test + Python pytest | Sprint 4 前 |
| **AC-4** | 摺疊規則 default DEGRADED + CRITICAL only；M11 divergence 絕禁首屏 | A3 UI snapshot + operator usability rehearsal | Sprint 7 first activation |
| **AC-5** | 2FA attestation file signed + Vault rotation (HMAC-SHA256 + rotation per Q2) | 寫盤檔存在 + HMAC 驗 pass + Vault rotation log | Sprint 7 前 |
| **AC-6** | GUI sign-off `node --check` pass (per W-AUDIT-7c) | `node --check tab-*.js common-modals.js` 0 error | E1a IMPL DONE 必 |
| **AC-7** | Vanilla JS only (per CLAUDE.md §七 — no React/Vue/Angular) | Grep `import.*react\|import.*vue` = 0 hit | E1a IMPL DONE 必 |

**Adversarial 強化（per `feedback_impl_done_adversarial_review`）**：E1a IMPL DONE 自評不接受獨立 sign-off；強制派 A3 + E2 並行核驗。

---

## §6 IMPL Phase Split

### 6.1 Sprint 1A-ε（本 spec land）

- A3 主導 spec + E1a 預讀；PM sign-off frozen baseline
- 工時：A3 24-36 hr
- 不寫 IMPL HTML/JS/CSS

### 6.2 Wave 1 — Sprint 4 first Live 前

- E1a 主 IMPL + A3 sign-off + E2 對抗 review + E4 regression
- Deliverable: openLalModal() Lv 3+4 active API / S7 5-gate mainnet (取代既有 prompt()) / S1 M1 LAL Tier 3 / Backend Rust authority enforce cooldown + 2FA + attestation file / Monthly Wizard read-only stub (mock data)
- 工時：42-59 hr
- AC pass: AC-3/AC-5/AC-6/AC-7 必；AC-2 partial (S1+S7)

### 6.3 Wave 2 — Sprint 7+ Advisory

- Deliverable: S2 M1 LAL Tier 4 / S3 M3 HEALTH_CRITICAL / S5 M10 Tier change / S8 Earn Asset Movement / Monthly Wizard 13 module × 4 metric 全 active / Traffic-light dynamic + 摺疊規則完整 + dwell time telemetry / ACK 機制 + 90d 未 ack auto-升 M3 HEALTH_WARN
- 工時：60-81 hr
- AC pass: AC-1 / AC-2 complete / AC-4

### 6.4 Y2 auto-allocator 階段

- 整合 audit log + signed attestation rotation
- S6 M13 venue change (Binance trade enable Y3+)
- Copy Trading Evidence Gate 真實 prep gate 解鎖

---

## §7 8 Sign-off Invariant for A3

| Invariant | Surface | 驗證 |
|---|---|---|
| **INV-1** | All S1-S8 | E1a IMPL DONE 自評 → 強制派 A3 + E2 並行（per `feedback_impl_done_adversarial_review`）|
| **INV-2** | All S1-S8 | `node --check` 0 error (per W-AUDIT-7c) |
| **INV-3** | All Lv 4 (S2/S5/S6/S7/S8) | 2FA TOTP backend 驗 (secret 不下發前端) + attestation file HMAC-SHA256 簽名驗 |
| **INV-4** | All S1-S8 | backend cooldown enforce (前端不可繞；Rust authority) |
| **INV-5** | S4 (M7 manual override) | UI 必 disabled + tooltip 顯 AMD-2026-05-21-01 引用 |
| **INV-6** | All Lv 4 | Operator inactivity < 60d check (per AMD §3) |
| **INV-7** | S7 (5-gate live mainnet auth) | 既有 `prompt()` 完全移除 (per memory 2026-04-24 §2) |
| **INV-8** | All S1-S8 | `governance.decisions` + `agent.audit_log` 雙寫；trace_id 必顯示 success toast |

---

## §8 Console Tab Placement（4 sub-section；不擴張 16 tab）

| Tab | 既有 sub-section | NEW sub-section |
|---|---|---|
| `governance` | Decision Lease | + 「Lease Tier」(S1/S2 modal) + 「Earn Movement」(S8) + 「Reward Weights」(M6) + 「Decay Lifecycle」(M7 viewer no override) |
| `system` | Engine + WS Health | + 「Health Domains」(M3，S3 unlock) + 「Capital Tier」(S5) + 「Monthly Wizard 入口 badge」 |
| `learning` | Strategy Learning Metrics | + 「Overlay State」(M2) + 「Anomalies」(M8) + 「A/B Tests」(M9) + 「Replay Divergence」(M11 + Wizard 連結) |
| `settings` | Risk Config | + 「Order Routing」(M12) + 「Venues」(S6) + 「TOTP Setup」(Vault 2FA 註冊) |

**Monthly Wizard 入口**：system tab 首屏 monthly badge「本月 review 未完成 / Pending」or「✓ 本月 review 已完成」→ 切換 Wizard 全屏 overlay（非新 tab）。

---

## §9 Cross-module Integration

| 鏈 | spec 對應 | 風險 / mitigation |
|---|---|---|
| M1 LAL Tier 1 IMPL → Lv 3 modal S1 | Sprint 4 同時 land | helper 必 Wave 1 land 不能晚 |
| M3 HEALTH state machine → Wizard Health + Lv 3 modal S3 | Wave 2 Sprint 5 | V106 schema 變動 → Wizard 顯示錯誤；mitigation = land 後重新驗 |
| M7 DECAY_ENFORCED → Wizard Decay State + S4 BLOCKED UI | Wave 2 Sprint 8 | operator 不知為何 S4 disabled；mitigation = tooltip + Wizard 14d 倒數 |
| M9 mSPRT result → Wizard A/B | Wave 2 Sprint 4+ | inconclusive 顯示誤導；mitigation = 顏色語義 黃 |
| M10 capital tier → S5 Lv 4 | Wave 2 Sprint 10 + Y2 trigger | 觸發 200-400 hr Y2-Y3 IMPL chain；mitigation = modal impact 欄列 |
| M11 replay divergence → Wizard 摺疊 + 反 FOMO | Wave 2 Sprint 7+ | 首屏 FOMO；mitigation = 絕禁首屏 |
| M13 venue → S6 Lv 4 | Y2 + Binance Y3+ | UI tooltip「Y3+」+ backend gate fail-closed |
| Earn (ADR-0032) → S8 Lv 4 | Sprint 1B-3 | per asset+direction cooldown（非 per surface）|
| 5-gate live mainnet → S7 Lv 4 | Sprint 4 first Live | INV-7 強制清 prompt() |

---

## §10 Risk / Mitigation

| Risk | 嚴重度 | Mitigation |
|---|---|---|
| **R1: GUI 認知爆炸** | HIGH | 摺疊規則 default DEGRADED+CRITICAL + Wizard ACK 一鍵批次 + 5 維度 ux-checklist |
| **R2: 2FA infrastructure dependency** | HIGH | Sprint 4 前必跟 E3+AI-E 議定 Vault；mock TOTP fail-closed |
| **R3: Cooldown Rust↔Python sync drift** | HIGH | INV-4 + AC-3 cross-language 1e-4 fixture (per v5.8 H-18) |
| **R4: Wizard Wave 1 stub 顯 mock data 被誤信** | MEDIUM | 必顯紅 banner「Wizard 數據未啟用（Sprint 7 開放）」+ ACK button disabled |
| **R5: S4 BLOCKED 被 operator 抱怨** | MEDIUM | tooltip + Wizard 14d 倒數 + docstring |
| **R6: 2FA OTP UX 阻力** | MEDIUM | S7+S5 不適合緊急止損；緊急止損走 Lv 2 既有 close-all |
| **R7: attestation file 滿盤 Y2-Y3** | LOW | per AC-5 Vault rotation 含 archive 90d hot / 1y cold |
| **R8: 摺疊 default 隱藏 OK rows operator 漏看微異常** | MEDIUM | dwell-time telemetry 月匯總；operator inactivity > 60d auto-展開全部 + email |

---

## §11 Open Q

### Q1: 4-tab Console layout final（operator D+5 pending）

A3 建議 **(c)**：Wizard 在 `system` tab 首屏 overlay；Lv 3-4 modal 散 4 tab（per §8）。

### Q2: Vault TOTP secret rotation cadence

A3 建議 **(b) 180d + soft-grace 14d**。需 E3 + AI-E 確認 Vault infrastructure 可支持。

### Q3: 摺疊規則 default ALL or DEGRADED+CRITICAL only

A3 建議 **(a) DEGRADED + CRITICAL only**（per `feedback_minimal_confirmation`）。AC-4 採 (a)。

### Q4: Monthly Wizard delivery channel

A3 建議 **(a) Console badge + email 必 / Slack 選**（per `feedback_external_tool_authority` Slack declined unless reopened）。

---

## §12 Sign-off

| Role | 簽核項 | 狀態 |
|---|---|---|
| **A3** (本 spec author) | §1-§11 spec complete + 12 section + INV-1~INV-8 + AC-1~AC-7 + 8 surface + Wizard 13×4 matrix | ✓ SIGNED 2026-05-21 (A3 inline draft a12c302e → PM transcribed) |
| **PM** | 仲裁 Open Q1-Q4 + scope frozen + Wave 1+2 + Y2 切片 frozen | PENDING (D+5 operator decision 後 batch sign-off) |
| **E1a** (IMPL Wave 1+2 owner) | 接收 spec frozen baseline；Wave 1 30-40 hr + Wave 2 40-55 hr；遵守 AC + INV | PENDING |

---

## 附錄 — Reference

- v5.8 §3.5 + §11.5 + §12 / PA dispatch consolidation §2 1A-ε / A3 audit §0.6 §5 §8
- ADR-0024-lite / 0030 / 0032 / 0034 / 0036 / 0038 / 0040 / 0041 / 0042 / 0044
- AMD-2026-05-15-01 / AMD-2026-05-21-01
- CLAUDE.md §一/§二/§四/§七/§八
- memory: `feedback_minimal_confirmation` / `feedback_gui_node_check_sop` / `feedback_impl_done_adversarial_review` / `feedback_chinese_output` / `feedback_no_dead_params` / `project_gui_write_paths_inventory` / 2026-04-24 GUI Top 3
- codebase: `common-modals.js` (openTypedConfirmModal base) / `console.html` (16 tab) / `governance-tab.js` (既有 reason field pattern)

---

**END Monthly Review Wizard + Lv 3-4 Modal Helper Scope Spec**

**A3 SIGNED 2026-05-21 inline (a12c302e) → PM transcribed 2026-05-21**
**A3 scoring: 8.5/10 (扣分: Q2 Vault TOTP infrastructure 待 E3+AI-E 確認 / R4 Wave 1 stub 風險靠紅 banner / Q1 待 operator D+5)**
