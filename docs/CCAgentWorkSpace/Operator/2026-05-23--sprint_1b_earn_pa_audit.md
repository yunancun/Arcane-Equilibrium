---
report: PA Sprint 1B Pending 3.2 Earn first stake — audit summary + readiness verdict
date: 2026-05-23
author: PA (Project Architect)
phase: Sprint 1B late Pending 3.2 Earn first stake — AUDIT-DONE / NEEDS-OPERATOR-DECISION-4 / WAVE-B-IMPL-PENDING
status: PA-AUDIT-DONE / DISPATCH-PACKET-READY / OPERATOR-RETURN-PENDING
parent reports:
  - srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-23--sprint_1b_earn_first_stake_dispatch_packet.md (主 packet 750+ line / §0-§11)
  - srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-23--sprint_1b_remaining_3_sections_audit.md §2 + §4.2 + §6
  - srv/docs/CCAgentWorkSpace/BB/workspace/reports/2026-05-21--v57_c4_c5_c6_bybit_verdict.md Part A + B
  - srv/docs/execution_plan/2026-05-21--earn_governance_spec.md DRAFT-FOR-FIVE-ROLE-CROSS-REF
  - srv/sql/migrations/V100__m4_hypothesis_base_table.sql earn_movement_log schema LAND
not in scope:
  - 不 IMPL Rust / Python / SQL
  - 不改 V100 (已 land)
  - 不 commit
  - 不派下游 sub-agent
---

# PA Sprint 1B Pending 3.2 Earn first stake — audit summary + readiness verdict

## §0 TL;DR

**Verdict**：**NEEDS-OPERATOR-DECISION-4 / WAVE-B-IMPL-DISPATCH-PENDING**

- ✅ DESIGN-READY (dispatch packet 750+ line §0-§11 完整 + 12 endpoint 清單 + V100 schema 接線 + IntentType/LeaseScope variant spec + 8-step chain + 50-78 hr estimate)
- ✅ V100 earn_movement_log schema LAND (Sprint 4+ §4.1.1 PA-DRIFT-6 patch closure)
- ⏳ earn_governance spec status DRAFT-FOR-FIVE-ROLE-CROSS-REF (CC self-draft DONE / FA + E3 + QA + MIT + BB cross-ref D+1 PENDING)
- ⏳ **4 operator-bound decisions all PENDING** (OP-1 OpenClaw key 發行日 / OP-2 first stake amount / OP-3 flexible vs fixed / OP-4 earn_governance final sign)
- ⏳ Wave B IMPL dispatch PENDING 4 OP closed + spec final sign

**Wall-clock**：~4-6 day Wave B IMPL + Wave C-E review/regression/closure (per Sprint 1B (full) W9-12 165-220 hr range);**operator return action ~45 min 親手 + 5-12 hr 並行 sub-agent cross-ref**;Wave B IMPL 最快 D+1 dispatch (若 OP-1 (a) path + 5 角色 5/5 ✅ APPROVE);最遲 D+2 dispatch (若 OP-1 (b) key 重發 +30-60 min + 5 角色 2 輪)。

---

## §1 既有狀態 audit

### §1.1 Bybit Earn API client (Rust)

| Component | 既有 IMPL | Gap |
|---|---|---|
| `rust/openclaw_engine/src/bybit_rest_client.rs` | 1367 LOC / HMAC-SHA256 簽名 / `RateLimitGroup` 6 enum / `get()` / `post()` / `get_checked()` / `post_checked()` 4 method | **無 Earn endpoint** — 既有 `RateLimitGroup::from_path` line 246-249 僅含 `/v5/order/` `/v5/position/` `/v5/account/` `/v5/market/` `/v5/asset/` `/v5/spot-lever-token/` `/v5/spot-margin/`;**0 hit `/v5/earn/`** |
| Bybit Earn 12 endpoint client | **0/12** | E1c IMPL Wave B 新建 `rust/openclaw_engine/src/bybit_earn_client.rs` ~600-900 LOC |

### §1.2 IntentProcessor + OrderIntent struct

| Component | 既有 IMPL | Gap |
|---|---|---|
| `rust/openclaw_engine/src/intent_processor/mod.rs` line 59-94 `OrderIntent` struct | 11 field (symbol/is_long/qty/confidence/strategy/order_type/limit_price/confluence_score/persistence_elapsed_ms/time_in_force/maker_timeout_ms) | **無 `IntentType` enum field**;trading intent 透過 is_long+strategy 隱性區分 |
| `IntentType` enum (per earn_governance §3.1 line 159-167) | **0 hit** (enum 不存在) | E1a IMPL Wave B 新建 6 variant (OpenLong/Short + CloseLong/Short 預留 + EarnStake/Redeem 新) + OrderIntent struct 擴 `intent_type` + `earn_payload` 2 field |
| `EarnIntentPayload` struct (per earn_governance §3.2 + V100 schema 對映) | **0 hit** | E1a IMPL Wave B 新建 (amount_usdt Decimal / expected_apr_bps i32 / product_id / tenor_days / approval_id / actor_id / rationale 7 field) |

### §1.3 LeaseScope (rust/openclaw_core)

| Component | 既有 IMPL | Gap |
|---|---|---|
| `rust/openclaw_core/src/lease_scope.rs` line 34-91 `LeaseScope` enum | 4 variant (TradeEntry/TradeExit/PositionAdjust/CanaryStagePromotion) + `as_audit_str()` + `requires_operator_authority()` + `default_ttl_ms()` 3 method exhaustive match | **無 `EarnStake` + `EarnRedeem` variant** |
| Variant 擴展設計 | – | E1b IMPL Wave B 新加 2 variant → as_audit_str = `"EARN_STAKE"` + `"EARN_REDEEM"` / requires_operator_authority=true / default_ttl_ms=60s (對齊 CanaryStagePromotion strict 60s + earn_governance §2.3) |
| PG CHECK constraint sync | – | PA4 Wave A Linux PG empirical audit;若既有 `governance.lease_transitions` 或 `canary_stage_log.transition_kind` CHECK 限 4 scope → 需 V108 ALTER 擴 2 值 |

### §1.4 V100 earn_movement_log

| Component | 狀態 |
|---|---|
| `srv/sql/migrations/V100__m4_hypothesis_base_table.sql` line 355-379 `learning.earn_movement_log` | ✅ **LAND** (Sprint 4+ §4.1.1 PA-DRIFT-6 patch closure 完成) |
| 10 column | movement_id BIGSERIAL PK / event_ts TIMESTAMPTZ / direction CHECK ('stake','redeem') / amount_usdt NUMERIC(18,8) / apr_at_time REAL NULL / governance_approval_id BIGINT soft ref / bybit_response_payload JSONB / engine_mode CHECK 4 enum / api_scope_used TEXT / reconciliation_status CHECK 3 enum DEFAULT 'pending' |
| Hot-path index | `idx_earn_movement_log_strategy_ts` on (event_ts DESC) |
| FK | governance_approval_id soft ref (不是 SQL FK;per PA-DRIFT-6 lesson 2026-05-23 — governance_audit_log 是 TimescaleDB hypertable composite PK (id, ts);application-level 反查) |
| Writer | **0 既有** — E1d IMPL Wave B 新建 `database/earn_movement_writer.rs` ~250 LOC |

### §1.5 earn_governance spec

| 項目 | 狀態 |
|---|---|
| `srv/docs/execution_plan/2026-05-21--earn_governance_spec.md` | 539 line / 34659 byte / status DRAFT-FOR-FIVE-ROLE-CROSS-REF |
| §1-§11 主體 | ✅ COMPLETE (5-gate / IntentProcessor 復用 / Earn-specific risk envelope / fail-closed / Daily reconciliation / 9 不變量 / 16 原則 / AC-1~6 全 spec) |
| §12 五角色 cross-ref | ⬜ PENDING (CC self-draft ✅ DONE;FA + E3 + QA + MIT + BB 5 角色 ⬜ PENDING D+1 2026-05-22 未 land) |
| PM 2026-05-21 仲裁 4 | §4.2 condition A finalize (BB v57-C4 verdict = API EXISTS;demo OPENCLAW_ALLOW_MAINNET 不適用 / live mainnet=1 強制) |
| PA cross-ref (本 audit 補) | ⚠️ **APPROVE-WITH-2-CAVEATS** (§3 IntentType enum 範圍 7 variant + §6.1 UTC 02:00 改正) |

---

## §2 12 Bybit Earn endpoint + V100 schema 接線

per dispatch packet §1.2 + §5：

### §2.1 12 endpoint 分類

| 類別 | 數量 | endpoint |
|---|---|---|
| **Flexible USDT savings** | 5 | E-1 `/v5/earn/flexible/product` (R) / E-2 `/v5/earn/flexible/subscribe` (W) / E-3 `/v5/earn/flexible/redeem` (W) / E-4 `/v5/earn/flexible/position` (R) / E-5 `/v5/earn/apr-history` (R) |
| **Fixed-term staking** | 4 | E-6 `/v5/earn/fixed/product` (W due to filter params) / E-7 `/v5/earn/fixed/order/place` (W) / E-8 `/v5/earn/fixed/order/redeem` (W) / E-9 `/v5/earn/fixed/position` (R) |
| **Unified query** | 3 | E-10 `/v5/earn/order/query-history` (R) / E-11 `/v5/earn/position/query` (R) / E-12 `/v5/earn/fixed/order/list` (R) |
| **總計** | 12 | 7 read-only + 5 write |

**Scope** (per BB C5 verdict)：read-only endpoint = `Read-Only` scope (key 自動帶);write endpoint = `Earn` scope (key < 2026-04-09 需 operator 重發)。**`Withdraw` scope 不需要** — Earn 屬內部 asset transfer 非外部出金 (per Hard Boundaries D1d)。

**Rate limit group**：全 12 endpoint → `RateLimitGroup::Asset` (5 req/s)。E1c IMPL must-fix = `bybit_rest_client.rs` line 246-249 加 `else if path.starts_with("/v5/earn/")` 分支 → `Self::Asset` 映射。

### §2.2 V100 schema 接線

per dispatch packet §5.2 + §5.3：

```
EarnIntentPayload (intent submit 階段)
  ├─ amount_usdt Decimal → V100 amount_usdt NUMERIC(18,8) 直映 (高精度;不丟 satoshi-scale)
  ├─ expected_apr_bps Option<i32> → V100 apr_at_time REAL (bps / 10000 = APR 4-decimal float)
  ├─ approval_id String → V100 governance_approval_id BIGINT soft ref (反查 learning.governance_audit_log.id)
  ├─ product_id String → V100 bybit_response_payload JSONB embed
  ├─ tenor_days Option<u32> → V100 bybit_response_payload JSONB embed
  └─ actor_id + rationale → V100 bybit_response_payload JSONB embed

寫入時序：
  1. 5-gate Gate a-d PASS
  2. Gate e: EarnMovementWriter.insert_placeholder() → V100 row (reconciliation_status='pending' / bybit_response_payload=NULL)
  3. bybit_earn_client.subscribe_flexible() / place_fixed_order() / redeem_*() Bybit API call
  4. API ack → EarnMovementWriter.update_outcome(movement_id, bybit_response, 'pending')  -- 等 cron 對賬
  5. lease release (LeaseOutcome::Consumed)

Daily reconciliation cron (UTC 02:00):
  1. earn_client.get_unified_position("USDT") → bybit_reported_balance
  2. SELECT SUM(amount_usdt) FROM V100 WHERE direction='stake' - SUM(amount_usdt) WHERE direction='redeem' → local_net
  3. diff = bybit - local
     - abs(diff) < $0.01 → outcome='ok'
     - $0.01 ≤ abs(diff) < $1.00 → outcome='mismatch' + alert
     - abs(diff) ≥ $1.00 → outcome='mismatch_critical' + 自動 earn_enabled=false hot-reload
  4. UPDATE V100 row reconciliation_status = ('matched' | 'mismatch')
  5. 連續 3 day mismatch → halt strategy (per v5.7 §9 Kill Criteria)
```

**新建檔案**：
- `srv/rust/openclaw_engine/src/bybit_earn_client.rs` (E1c ~600-900 LOC)
- `srv/rust/openclaw_engine/src/database/earn_movement_writer.rs` (E1d ~250 LOC)
- `srv/rust/openclaw_engine/src/cron/earn_reconciliation.rs` (E1e ~150 LOC)

---

## §3 IntentType + LeaseScope variant 設計 + earn_governance spec 五角色 cross-ref pending matrix

per dispatch packet §2 + §3 + §6.2：

### §3.1 IntentType enum (新建)

```rust
// rust/openclaw_engine/src/intent_processor/mod.rs (緊接 OrderIntent 上方)
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum IntentType {
    OpenLong,                    // trading entry (既有 is_long=true 對映)
    OpenShort,                   // trading entry (既有 is_long=false 對映)
    #[allow(dead_code)] CloseLong,   // Sprint 5+ 預留
    #[allow(dead_code)] CloseShort,  // Sprint 5+ 預留
    EarnStake,                   // Sprint 1B 新 — Bybit Earn flexible/fixed stake
    EarnRedeem,                  // Sprint 1B 新 — Bybit Earn flexible/fixed redeem
}

impl IntentType {
    pub fn to_lease_scope(self) -> LeaseScope { /* 1:1 mapping */ }
    pub fn is_earn(self) -> bool { matches!(self, EarnStake | EarnRedeem) }
}
```

OrderIntent struct 擴 2 field (intent_type + earn_payload;serde default backward-compat)。

### §3.2 LeaseScope variant 擴 (新建 2)

```rust
// rust/openclaw_core/src/lease_scope.rs
pub enum LeaseScope {
    TradeEntry, TradeExit, PositionAdjust, CanaryStagePromotion,
    EarnStake,    // NEW — as_audit_str="EARN_STAKE" / req_operator_auth=true / default_ttl=60s
    EarnRedeem,   // NEW — as_audit_str="EARN_REDEEM" / req_operator_auth=true / default_ttl=60s
}
```

對齊 CanaryStagePromotion strict 60s + operator authority 範式;exhaustive match 3 method (as_audit_str / requires_operator_authority / default_ttl_ms) 編譯期強制。

### §3.3 earn_governance spec 五角色 cross-ref pending matrix

| 角色 | Verdict | Report path |
|---|---|---|
| **CC** (self-draft) | ✅ DONE | `srv/docs/CCAgentWorkSpace/CC/workspace/reports/2026-05-21--v57_c8_earn_governance_spec.md` (spec 自身) |
| **PA** (本 audit 補) | ⚠️ APPROVE-WITH-2-CAVEATS (§3 IntentType 7 variant + §6.1 UTC 02:00) | `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-23--sprint_1b_earn_first_stake_dispatch_packet.md` §6.3 |
| **FA** | ⬜ PENDING (D+1 2026-05-22 未 land) | `srv/docs/CCAgentWorkSpace/FA/workspace/reports/2026-05-22--earn_governance_spec_review.md` |
| **E3** | ⬜ PENDING | `srv/docs/CCAgentWorkSpace/E3/workspace/reports/2026-05-22--earn_governance_spec_review.md` |
| **QA** | ⬜ PENDING | `srv/docs/CCAgentWorkSpace/QA/workspace/reports/2026-05-22--earn_governance_spec_review.md` |
| **MIT** | ⬜ PENDING | `srv/docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-22--earn_governance_spec_review.md` |
| **BB** | ⬜ PENDING | `srv/docs/CCAgentWorkSpace/BB/workspace/reports/2026-05-22--earn_governance_spec_review.md` |

**dispatch SOP**：CC 修 2 PA caveat → spec status → DRAFT-WITH-PA-CAVEATS-RESOLVED → 5 角色並行 dispatch (5-12 hr) → 5/5 ✅ 或 4/5 ✅ + 1/5 ⚠️ minor → CC final sign → operator OP-4 approve → SPEC-FINAL → Wave B IMPL dispatch ready。

---

## §4 8-step IMPL chain + 50-78 hr estimate

per dispatch packet §7 + §8：

### §4.1 8-step dispatch chain

```
Wave 0 (operator ~45 min + sub-agent cross-ref 5-12 hr 並行)
  ├─ OP-1: D+1 OpenClaw key 發行日 5 min query (key 自動帶 Earn / 重發 +30-60 min)
  ├─ OP-2: first stake $200-400 拍板
  ├─ OP-3: flexible (30 day flex) vs fixed (90/180 day) 拍板
  └─ OP-4: earn_governance spec 五角色 cross-ref final sign (HARD BLOCK Wave B IMPL)

Wave A (PA spec 6-9 hr + CC 1 hr 並行)
  ├─ PA1: 本 dispatch packet 起草 (DONE 2026-05-23)
  ├─ PA2: V100 writer SQL/Rust binding spec finalize (2-3 hr)
  ├─ PA3: reconciliation cron spec finalize (2-3 hr)
  ├─ PA4: Linux PG CHECK constraint audit (1-2 hr) → 若需 V108 ALTER scope CHECK
  └─ CC: PA caveat 修正 (§3 IntentType 7 variant + §6.1 UTC 02:00) (1 hr)

Wave B (5 並行 E1 + 1 E1a GUI ~30-45 hr core / 2-3 day wall-clock)
  ├─ E1a: IntentType + OrderIntent struct + EarnIntentPayload (4-6 hr)
  ├─ E1b: LeaseScope EarnStake/Redeem variant + 3 method exhaustive match (2-3 hr)
  ├─ E1c: bybit_earn_client.rs 12 endpoint + 12 response struct + RateLimitGroup patch (10-15 hr)
  ├─ E1d: EarnMovementWriter + IntentProcessor Earn 分支接線 (5-7 hr)
  ├─ E1e: Daily reconciliation cron + ArcSwap hot-reload hook (4-6 hr)
  └─ E1a (GUI 阻於 H2 Console tab; 可延 W+2): governance tab Earn manual stake form (8-12 hr)

Wave C (E2 + BB + E3 並行 review ~5-9 hr / 1 day wall-clock)
  ├─ E2: adversarial review 16 原則 1/3/4/8 + 5-gate + fail-closed (3-5 hr)
  ├─ BB: 12 endpoint v BB C4 verdict + ToS / KYC / rate limit (1-2 hr)
  └─ E3: secret slot governance + OWASP + Earn scope key 三端同步 (1-2 hr)

Wave D (sequential ~3-10 hr / 0.5-1 day wall-clock)
  ├─ E1: round 2 fix (Wave C review fix) (0-4 hr)
  ├─ E4: cargo + pytest + integration regression (1-2 hr)
  └─ QA: Stage 0R replay + 5-gate verify + AC-1~6 (2-4 hr)

Wave E (operator + PM ~1-2 hr / 0.5 day wall-clock)
  ├─ operator: GUI manual stake first execution + Linux PG verify (10-30 min + 5 min)
  └─ PM: Phase 3e sign-off + Sprint 1B Pending 3.2 closure (1 hr)
```

### §4.2 50-78 hr estimate breakdown

| 階段 | Estimate |
|---|---|
| PA spec | 10-15 hr |
| CC caveat 修正 | 1 hr |
| earn_governance 五角色 cross-ref | 5-12 hr (並行) |
| E1 IMPL Wave B (5 並行 + GUI) | 30-45 hr (含 GUI 8-12;不含 22-37) |
| E2 + BB + E3 review | 5-9 hr (並行) |
| E1 round 2 fix | 0-4 hr |
| E4 regression | 1-2 hr |
| QA Acceptance | 2-4 hr |
| operator first stake + PG verify | 0.5-1 hr |
| PM Phase 3e closure | 1 hr |
| **合計 core** | **50-78 hr** |

**Wall-clock**：4-6 day (D+0 4 OP + Wave A → D+1-3 Wave B → D+4 Wave C → D+4.5 Wave D → D+5 Wave E)。

**Sub-agent peak**：5-6 並行 (Wave B 5 並行 E1 + Wave 0d 5 角色 cross-ref 並行;不撞 dispatch_packet §2 50-60% workload mandate ceiling)。

---

## §5 4 operator-bound decisions + dispatch readiness verdict

### §5.1 4 OP enumeration

per dispatch packet §9：

| OP | 規格 | 時長 | Block Wave B IMPL? | PA 建議 |
|---|---|---|---|---|
| **OP-1** | D+1 OpenClaw key 發行日 Bybit Web UI 5 min query → (a) ≥ 2026-04-09 key 自動帶 Earn / (b) < 2026-04-09 operator 重發 key (+30-60 min) | 5 min + 0-60 min | YES (E1c test 需 Earn scope key) | – (operator carry-over from TODO §0) |
| **OP-2** | first stake amount $100-500 USDT 拍板 | 10 min | NO (IMPL placeholder=$0;Wave E 實值) | **路徑 (a) $100-200** — 對齊 AMD-2026-05-15-01 Stage 1 micro-canary + Bybit flexible tier 1 $200 @ ~10% APR boundary |
| **OP-3** | flexible (30 day flex) vs fixed (90/180 day) staking 拍板 | 5 min | PARTIAL (E1c 範圍縮 4-6 hr if flexible only) | **路徑 (a) flexible** — Sprint 1B W9-12 過短 + fixed 鎖倉撞 margin auto-redeem 路徑 |
| **OP-4** | earn_governance spec 五角色 cross-ref final sign (CC + FA + E3 + QA + MIT + BB) | 5 min approve + 5-12 hr 並行 sub-agent | **YES (HARD BLOCK)** | PA verdict ⚠️ APPROVE-WITH-2-CAVEATS — 預期 4-5/5 ✅ APPROVE post-caveat 修正 |

### §5.2 dispatch readiness verdict matrix

| 維度 | 狀態 |
|---|---|
| DESIGN-READY | ✅ YES (dispatch packet 750+ line §0-§11) |
| V100 earn_movement_log schema | ✅ LAND (Sprint 4+ §4.1.1 PA-DRIFT-6 closure) |
| IntentType / LeaseScope / bybit_earn_client / writer / cron design | ✅ READY (§2 / §3 / §4 / §5 全 spec) |
| earn_governance spec sign-off | ⏳ PENDING (CC self-draft ✅ / 5 角色 cross-ref ⬜) |
| OP-1 OpenClaw key 發行日 query | ⏳ PENDING (TODO §0 D+1 5 min carry-over) |
| OP-2 first stake amount | ⏳ PENDING |
| OP-3 flexible/fixed | ⏳ PENDING |
| OP-4 spec final sign | ⏳ PENDING (前置 = 5 角色 cross-ref + CC sign) |
| Wave B IMPL dispatch readiness | ⏳ **NEEDS-OPERATOR-DECISION-4-CLOSED + EARN-GOVERNANCE-SPEC-FINAL-SIGN** |

### §5.3 PM 建議路徑

**路徑 A (PA 建議)**：先 C10 後 Earn 序列 dispatch (per parent audit §5.2 路徑 A)
- **W+0**：dispatch C10 Stage 1 Demo (Pending 3.1 — READY-TO-DISPATCH 無前置阻塞) + operator 4 OP 並行 (~45 min) + earn_governance 5 角色 cross-ref 並行 (5-12 hr)
- **W+1**：C10 closure 後 → Wave B IMPL 5 並行 E1 dispatch (~30-45 hr / 2-3 day)
- **W+2**：Wave C-E 完成 → Pending 3.2 closure

**整體 wall-clock**：~2-3 weeks (含 Sprint 4+ §4.1.1 已 closed + C10 並行 4 day + Earn 4-6 day)。

### §5.4 risk 紀要

| Risk | 嚴重度 | 緩解 |
|---|---|---|
| Wave B IMPL 5 並行 E1 撞 mandate ceiling | MED | E1a GUI 可延 W+2;4 E1 + 1 GUI 並行安全 |
| OP-1 key 重發路徑 (b) +30-60 min | MED | per BB C5 不違 Hard Boundaries;運維 SOP `engineering:devops` |
| 五角色 cross-ref 衍生 ❌ NEEDS-FIX 致 spec 二輪 | MED | per spec §12 最多 2 輪 dispatch |
| `governance.lease_transitions` PG CHECK 限 4 scope 阻 EARN_STAKE/REDEEM 寫入 | MED | PA4 Wave A Linux PG empirical audit catch;若需 V108 ALTER 同 PR |
| Wave E operator first stake 真實 Bybit API 失敗 (產品撤回 / KYC / 地理) | LOW | per BB C5 KYC + 地理已 review;earn_governance §5 fail-closed + Wave D QA Stage 0R replay verify |
| 11 個既有 OrderIntent test fixture 漏補 intent_type default | LOW | E1a IMPL must-fix;E2 review grep + cargo test 強制 |
| `governance_audit_log.id` soft ref 反查邏輯複雜 (per PA-DRIFT-6 lesson) | LOW | E1d IMPL 對齊 V100 line 502-511 comment + V106/V107/V112 既有範式 |

---

## §6 PA 對 PM 的 next-action 建議

### §6.1 立即 (Wave 0 並行 ~D+0)

1. **operator OP-1**: D+1 Bybit Web UI 5 min query OpenClaw key 發行日 (TODO §0 carry-over)
2. **operator OP-2**: first stake $100-500 拍板 (PA 建議 $100-200 對齊 AMD-2026-05-15-01)
3. **operator OP-3**: flexible vs fixed 拍板 (PA 建議 flexible)
4. **operator OP-4**: earn_governance spec 五角色 cross-ref final sign approve (CC 修 2 caveat → 5 sub-agent 並行 cross-ref dispatch ~5-12 hr → CC final sign → operator approve)

### §6.2 Wave 0 完成後

1. dispatch Wave A: PA2 + PA3 + PA4 並行 (~6-9 hr core) → V100 writer spec finalize + reconciliation cron spec finalize + Linux PG CHECK audit
2. **與 Pending 3.1 C10 並行** (per parent audit §5.2 路徑 A建議)

### §6.3 Wave A 完成後

1. dispatch Wave B 5 並行 E1: E1a IntentType + E1b LeaseScope + E1c bybit_earn_client + E1d EarnMovementWriter + E1e reconciliation cron (~30-45 hr / 2-3 day)
2. E1a GUI manual stake form 阻於 H2 Console tab 決策;可延 W+2

### §6.4 Wave B 完成後

1. Wave C (E2 + BB + E3 並行 review ~5-9 hr) → Wave D (E1 fix + E4 + QA ~3-10 hr) → Wave E (operator first stake + PM ~1-2 hr)
2. Sprint 1B Pending 3.2 Earn first stake 全 closure (per parent audit §5.4 收口時序 W+2-2.5)

### §6.5 risk 紅線

- ❌ **不可** 在 4 OP 全 closed 前 dispatch Wave B IMPL (OP-4 spec final sign 是 HARD BLOCK)
- ❌ **不可** 跳過 earn_governance spec 五角色 cross-ref 直接 IMPL (per dispatch packet §6.4 risk 紅線)
- ❌ **不可** 將 OP-2 first stake $200-400 拍 < $100 absolute (per AMD-2026-05-15-01 Stage 1 micro-canary 邊界) 或 > $500 (Sprint 1B 過保守邊界)
- ❌ **不可** Wave B IMPL 期跳過 4 既有策略 (bb_breakout/bb_reversion/grid_trading/ma_crossover) OrderIntent constructor + 11 test fixture intent_type default 補 (per dispatch packet §2.4 backward-compat)
- ❌ **不可** OP-3 拍板 fixed 同時 Sprint 1B W9-12 範圍 (per PA 建議 fixed 鎖倉撞 margin auto-redeem;Sprint 2+ 評估)

---

## §7 PA 5 條完成回報 (對齊主 packet §11)

### 7.1 Earn dispatch packet path + LOC

- **path**: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-23--sprint_1b_earn_first_stake_dispatch_packet.md`
- **LOC**: 750+ line / §0-§11 完整
- **狀態**: DESIGN-READY / NEEDS-OPERATOR-DECISION-4

### 7.2 12 Bybit Earn endpoint + V100 schema 接線

- **12 endpoint**: 5 flexible + 4 fixed + 3 unified query (7 read-only + 5 write per BB C4 verdict);全走 `RateLimitGroup::Asset` (5 req/s)
- **V100 earn_movement_log**: LAND (10 column + CHECK enum + soft ref governance_audit_log per PA-DRIFT-6)
- **Writer 接線**: 3 新檔 (bybit_earn_client.rs ~600-900 + earn_movement_writer.rs ~250 + earn_reconciliation.rs ~150);INSERT placeholder → API ack → UPDATE outcome 範式;Daily cron UTC 02:00 + earn_enabled=false 自動 hot-reload

### 7.3 IntentType + LeaseScope variant + 五角色 cross-ref pending

- **IntentType** 6 variant + OrderIntent 擴 2 field (intent_type + earn_payload;serde default backward-compat 11 既有 callers 不破壞)
- **LeaseScope** 擴 2 variant (EarnStake + EarnRedeem) → 60s TTL + requires_operator_authority=true 對齊 CanaryStagePromotion 範式
- **五角色 cross-ref**: CC self-draft ✅ / FA + E3 + QA + MIT + BB ⬜ PENDING D+1;PA cross-ref ⚠️ APPROVE-WITH-2-CAVEATS (§3 IntentType 7 variant + §6.1 UTC 02:00)

### 7.4 8-step IMPL chain + 50-78 hr estimate

- **8-step**: Wave 0 operator (45 min + 5-12 hr 並行) → Wave A PA spec (6-9 hr) → Wave B 5 並行 E1 IMPL (30-45 hr / 2-3 day) → Wave C E2 + BB + E3 並行 (5-9 hr) → Wave D fix + regression + QA (3-10 hr) → Wave E operator + PM (1-2 hr)
- **Total core**: 50-78 hr / Wall-clock 4-6 day / Sub-agent peak 5-6 並行
- **Critical path**: OP-4 spec final sign HARD BLOCK Wave B IMPL dispatch

### 7.5 4 OP enumeration + dispatch readiness verdict

**4 OP**:
1. **OP-1** D+1 OpenClaw key 發行日 Bybit Web UI 5 min query (block: E1c test;PA 建議 (a) ≥ 2026-04-09 path)
2. **OP-2** first stake $100-500 拍板 (NO block IMPL;PA 建議 $100-200 對齊 AMD-2026-05-15-01)
3. **OP-3** flexible vs fixed 拍板 (PARTIAL block: E1c 範圍縮 4-6 hr;PA 建議 flexible)
4. **OP-4** earn_governance spec final sign (HARD BLOCK Wave B;5-12 hr 並行 cross-ref)

**Dispatch readiness verdict**: **NEEDS-OPERATOR-DECISION-4 / WAVE-B-IMPL-PENDING**
- DESIGN ✅ / V100 schema ✅ / variant + writer + cron spec ✅
- earn_governance final sign ⏳ / OP-1/2/3/4 ⏳
- Wave B IMPL 最快 D+1 dispatch (4 OP closed + 5 角色 ≥ 4/5 ✅)
- 最遲 D+2 dispatch (OP-1 (b) +30-60 min + 5 角色 2 輪)

---

**END OF PA Sprint 1B Pending 3.2 Earn first stake — audit summary + readiness verdict**

PA DESIGN DONE: report path: /Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-23--sprint_1b_earn_pa_audit.md
