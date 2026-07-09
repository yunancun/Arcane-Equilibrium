---
report: PA Sprint 1B Pending 3.2 Earn first stake dispatch packet
date: 2026-05-23
author: PA (Project Architect)
phase: Sprint 1B late Pending 3.2 Earn first stake — DISPATCH-PACKET-READY / WAVE-B-IMPL-PENDING-4-OPERATOR-DECISION
status: DESIGN-READY / NEEDS-OPERATOR-DECISION-4 / DEPENDS-ON-V100-LAND-DONE
parent reports:
  - srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-23--sprint_1b_remaining_3_sections_audit.md §2 + §4.2 + §6
  - srv/docs/CCAgentWorkSpace/BB/workspace/reports/2026-05-21--v57_c4_c5_c6_bybit_verdict.md Part A + Part B
  - srv/docs/execution_plan/2026-05-21--earn_governance_spec.md §1-§12 (DRAFT-FOR-FIVE-ROLE-CROSS-REF)
  - srv/sql/migrations/V100__m4_hypothesis_base_table.sql (earn_movement_log schema LAND)
  - srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-23--sprint_1b_late_v100_m4_hypothesis_base_table_design.md
not in scope:
  - 不 IMPL Rust / Python / SQL (Wave B 等 operator decisions 後派發)
  - 不 commit
  - 不派下游 sub-agent
  - 不改既有 funding_arb.rs / strategies/ (Earn ≠ trading strategy)
  - 不改 V100 sql 文件 (已 land per Sprint 4+ §4.1.1 closure)
---

# PA Sprint 1B Pending 3.2 Earn first stake dispatch packet — 2026-05-23

## §0 TL;DR

Sprint 1B Pending 3.2 Earn first stake：**DESIGN-READY / NEEDS-OPERATOR-DECISION-4 / WAVE-B-IMPL-DISPATCH-PENDING**。

**核心結論**：
- **0 既有 Rust / Python IMPL**：12 Bybit Earn endpoint 全缺、`IntentProcessor::IntentType` enum 不存在、`LeaseScope::EarnStake/EarnRedeem` variant 不存在
- **`learning.earn_movement_log` schema land**（V100 line 355-379；BIGSERIAL PK + 10 column + CHECK 2 / 3 / 4 enum + 1 hot-path index + governance_audit_log soft ref per PA-DRIFT-6 lesson）— Wave B IMPL schema 前置已解
- **earn_governance spec status = DRAFT-FOR-FIVE-ROLE-CROSS-REF**（PA + E1 + QC + BB + CC 五角色 cross-ref pending；CC self-draft DONE / FA + E3 + QA + MIT + BB 四角色 PENDING D+1 2026-05-22 未 land）
- **4 operator-bound decisions** 必須親手後才 dispatch IMPL Wave B（OP-1 D+1 OpenClaw key 發行日 5 min + OP-2 first stake $200-400 拍板 + OP-3 flexible vs fixed staking 拍板 + OP-4 earn_governance spec 五角色 cross-ref final sign）

**8-step IMPL dispatch chain**：PA spec + V100 schema verify ⇒ E1×5 並行 Wave B (Bybit Earn client + IntentType enum + LeaseScope variant + earn_movement_log writer + Daily reconciliation cron) ⇒ E2 adversarial review ⇒ BB Bybit ToS/KYC verdict ⇒ E3 secret slot governance ⇒ E4 regression ⇒ QA + operator first stake execution ⇒ PM Phase 3e sign-off

**Estimate**：PA spec 10-15 hr + E1 IMPL 30-45 hr + E2/BB/E3/E4/QA/PM 10-15 hr = **50-78 hr core** + 並行 sub-agent wall-clock 4-6 day + operator parallel actions ~45 min。

---

## §1 Earn first stake spec + 12 Bybit Earn endpoint 清單

### 1.1 first stake 整體規格

per Sprint 1B brief + Sprint 1A dispatch packet §1.2 + earn_governance_spec.md + BB C4 verdict：

| 項目 | 規格 |
|---|---|
| **數額範圍** | $200-400 USDT (per Sprint 1B brief；first manual stake) — operator OP-2 拍板 |
| **賬戶** | Bybit primary live account 主帳 (per BB C4 §96 demo 0 product 待 curl smoke verify；本 dispatch packet 假設「demo 不支援 Earn → 直接 live」per earn_governance §4.2 條件 A) |
| **產品種類** | flexible vs fixed (90/180 day) — operator OP-3 拍板 (建議 flexible first stake；fixed staking 鎖倉 90+ day Sprint 1B 過短不適) |
| **APR tier** | flexible tier 1 first $200 @ ~10% / remaining $200 @ ~3% (per BB C4 reference SDK) |
| **風險範圍** | 3%/trade 不適用 (Earn 不是 trade event)；max position cap = first stake amount absolute |
| **簽署** | 5-gate boundary 全適用 + Operator role manual approve (per ADR-0020 + earn_governance §2) |
| **Lease** | `LeaseScope::EarnStake`/`EarnRedeem` (新增 2 variant)；TTL 60s (per earn_governance §2.3) |
| **Intent** | `IntentType::EarnStake`/`EarnRedeem` (新增 enum；既有 OrderIntent 無 IntentType field 必擴) |
| **Audit** | `learning.earn_movement_log` (V100 LAND) + soft ref to `learning.governance_audit_log` (Decision Lease cross-ref) |
| **API endpoint** | 12 Bybit Earn V5 endpoint (6 read-only + 6 write per BB C4 verdict) |
| **fail-closed** | retCode != 0 → 不重試；連續 3 失敗 → 自動 disable Earn until manual reset (per earn_governance §5) |
| **reconciliation** | Daily cron 02:00 UTC (avoid funding settlement) → mismatch ≥ $0.01 → next stake disable；連續 3 day mismatch → halt strategy |

### 1.2 12 Bybit Earn V5 endpoint 清單

per BB C4 verdict Part A.2 (tiagosiebler reference SDK + Bybit V5 official changelog 2025-02-20 launch / 2026-05-07 最近更新)：

#### 1.2.1 Flexible USDT savings (5 endpoint)

| # | SDK method | HTTP path | Method | Scope | RateLimit group | first stake 角色 |
|---|---|---|---|---|---|---|
| E-1 | `getEarnFlexibleProductList` | `/v5/earn/flexible/product` | GET | `Earn` / `Read-Only` | Asset (5 req/s) | OP-2 後 stake 前查 APR + tier + product_id |
| E-2 | `subscribeEarnFlexible` | `/v5/earn/flexible/subscribe` | POST | `Earn` | Asset | **first stake 主寫操作** |
| E-3 | `redeemEarnFlexible` | `/v5/earn/flexible/redeem` | POST | `Earn` | Asset | margin headroom < 30% 強制 redeem path |
| E-4 | `getEarnFlexiblePosition` | `/v5/earn/flexible/position` | GET | `Read-Only` | Asset | Daily reconciliation cron + post-stake verify |
| E-5 | `getEarnAprHistory` | `/v5/earn/apr-history` | GET | `Read-Only` | Asset | ML learning + historical APR drift detection (Sprint 2+) |

#### 1.2.2 Fixed-term staking (4 endpoint)

| # | SDK method | HTTP path | Method | Scope | RateLimit group | first stake 角色 |
|---|---|---|---|---|---|---|
| E-6 | `getEarnFixedProductList` | `/v5/earn/fixed/product` | POST | `Earn` / `Read-Only` | Asset | OP-3 fixed staking 路徑 + tenor (90/180 day) 確認 |
| E-7 | `placeFixedTermEarnOrder` | `/v5/earn/fixed/order/place` | POST | `Earn` | Asset | OP-3 fixed staking 主寫操作 |
| E-8 | `redeemFixedTermEarn` | `/v5/earn/fixed/order/redeem` | POST | `Earn` | Asset | 提前贖回 + earn_movement_log direction='redeem' |
| E-9 | `getFixedTermEarnPosition` | `/v5/earn/fixed/position` | GET | `Read-Only` | Asset | Daily reconciliation + post-stake verify |

#### 1.2.3 Unified query (3 endpoint)

| # | SDK method | HTTP path | Method | Scope | RateLimit group | first stake 角色 |
|---|---|---|---|---|---|---|
| E-10 | `getEarnOrderHistory` | `/v5/earn/order/query-history` | GET | `Read-Only` | Asset | Reconciliation 對賬源 + audit forensic |
| E-11 | `getEarnPosition` | `/v5/earn/position/query` | GET | `Read-Only` | Asset | Daily aggregated position query (unified flex + fixed) |
| E-12 | `getFixedTermEarnOrderList` | `/v5/earn/fixed/order/list` | GET | `Read-Only` | Asset | Fixed staking order list query (audit + monitor) |

**統計**：6 read-only (E-1/4/5/9/10/11/12 = 7 read endpoint 修正為 7) + 5 write (E-2/3/6/7/8) = 12 endpoint。

**修正**：BB verdict 列 12 endpoint 但分類略有差異；以本表為準 (7 read-only + 5 write)。Bybit V5 official changelog 顯示 BB 邊際 LOW priority endpoint `/v5/finance/earn/easy-onchain/*` (5 endpoint per Part A.2 2025-02-20 launch) + `/v5/finance/earn/byusdt/*` (2026-04-08) + `/v5/finance/earn/fixed-saving/*` (2026-04-14) 是 future product；Sprint 1B first stake **不接** legacy easy-onchain path (BB Part H 列為 LOW 工作)。

---

## §2 OrderIntent::IntentType enum 設計

### 2.1 既有狀態

per grep verify (path: `srv/rust/openclaw_engine/src/intent_processor/mod.rs` line 59-94)：

```rust
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OrderIntent {
    pub symbol: String,
    pub is_long: bool,
    pub qty: f64,
    pub confidence: f64,
    pub strategy: String,
    pub order_type: String, // "market" or "limit"
    pub limit_price: Option<f64>,
    pub confluence_score: Option<f32>,
    pub persistence_elapsed_ms: Option<u64>,
    pub time_in_force: Option<crate::order_manager::TimeInForce>,
    pub maker_timeout_ms: Option<u64>,
}
```

**verdict**：既有 OrderIntent struct **無 IntentType enum field**。trading intent 透過 `is_long: bool` + `strategy: String` 隱性區分 long/short；無 open/close/earn 區分 (close 路徑由 PaperState position state machine 推導)。

### 2.2 IntentType enum 新增設計

**設計方向**：新建 `IntentType` enum 7 variant + 加 `intent_type: IntentType` field 至 OrderIntent struct。

```rust
// 新建 — rust/openclaw_engine/src/intent_processor/mod.rs (緊接 OrderIntent struct 上方)
//
// IntentType — 意圖類型強型別 enum。
// 對齊 earn_governance §3.1 spec：trading 5 variant + Earn 2 variant。
//
// 設計依據：
//   - earn_governance §3.1 line 159-167 明列 7 variant (OpenLong/Short + CloseLong/Short
//     + EarnStake/Redeem) — 但 spec 未含「PositionAdjust」(W-AUDIT-9 LeaseScope 有對應
//     variant 但 trading hot-path 暫不用)；本設計暫不加，留 future Sprint 5+ 擴展。
//   - 既有 router.rs line 80-122 `acquire_lease_for_gate_1_4()` 用字面 "TRADE_ENTRY"
//     字串；本 IntentType 對齊 LeaseScope::TradeEntry/TradeExit/EarnStake/EarnRedeem
//     映射 (per §3 LeaseScope variant 設計)。
//   - PR review 戰術建議：先加 default OpenLong/OpenShort 兩 variant + EarnStake/Redeem
//     兩 variant；CloseLong/CloseShort 預留 (既有 trading hot path 透過 is_long 推導
//     close 動作；近期 Sprint 5+ position state machine 重構時再啟用)。
//
// SAFETY 不變量：
//   - new variant 必須在 IntentType.to_lease_scope() exhaustive match 同步補映射；
//   - serde tag = "type" + content = "payload" 預留 future extend (e.g. EarnPayload
//     必含 amount_usdt + apr_at_time + product_id 等 Earn-specific field)。
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum IntentType {
    /// 真實開多 — Trading entry path (既有路徑;預設 variant 對齊既有 is_long=true)。
    OpenLong,
    /// 真實開空 — Trading entry path (既有路徑;對齊 is_long=false)。
    OpenShort,
    /// 真實平多 — Sprint 5+ position state machine 重構後啟用 (預留)。
    #[allow(dead_code)]
    CloseLong,
    /// 真實平空 — Sprint 5+ 預留。
    #[allow(dead_code)]
    CloseShort,
    /// Bybit Earn flexible/fixed stake 操作 — earn_governance §3.1 新增。
    /// amount + product_id + apr + tenor 等 Earn-specific field 走 EarnIntentPayload
    /// (per §2.3 payload schema)。
    EarnStake,
    /// Bybit Earn flexible/fixed redeem 操作 — earn_governance §3.1 新增。
    /// 含提前贖回 (fixed) + flexible 即時贖回兩種 sub-mode。
    EarnRedeem,
}

impl IntentType {
    /// W-AUDIT-9 lease facade alignment: enum → LeaseScope mapping (1:1)。
    /// 對應 router.rs line 100 字面 "TRADE_ENTRY" → 升級為 enum-driven。
    pub fn to_lease_scope(self) -> crate::LeaseScope {
        // 注：實際引入路徑為 `openclaw_core::lease_scope::LeaseScope`，本骨架以
        // crate-relative 示意；E1 IMPL 期改用 full path。
        match self {
            Self::OpenLong | Self::OpenShort => crate::LeaseScope::TradeEntry,
            Self::CloseLong | Self::CloseShort => crate::LeaseScope::TradeExit,
            Self::EarnStake => crate::LeaseScope::EarnStake,
            Self::EarnRedeem => crate::LeaseScope::EarnRedeem,
        }
    }

    /// 是否為 Earn 路徑 (走 bybit_earn_client + earn_movement_log writer，
    /// 不走 IntentProcessor.execute_trade 既有 Bybit perp order path)。
    /// 用於 IntentProcessor.process 內部分支 dispatch。
    pub fn is_earn(self) -> bool {
        matches!(self, Self::EarnStake | Self::EarnRedeem)
    }
}
```

### 2.3 OrderIntent struct 擴展

```rust
// 既有 OrderIntent struct (line 59-94) 擴 1 field：
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OrderIntent {
    pub symbol: String,
    pub is_long: bool,
    pub qty: f64,
    pub confidence: f64,
    pub strategy: String,
    pub order_type: String,
    pub limit_price: Option<f64>,
    pub confluence_score: Option<f32>,
    pub persistence_elapsed_ms: Option<u64>,
    pub time_in_force: Option<crate::order_manager::TimeInForce>,
    pub maker_timeout_ms: Option<u64>,
    /// 新增 — IntentType 強型別 (Sprint 1B Earn first stake) :
    ///   既有 trading intent ⇒ OpenLong (is_long=true) / OpenShort (is_long=false)
    ///   Earn stake ⇒ EarnStake (走 bybit_earn_client + earn_movement_log writer)
    ///   Earn redeem ⇒ EarnRedeem
    /// serde default = OpenLong (向後相容既有 4 strategy IPC payload；IPC consumer
    /// 若 Sprint 1B 前已部署不會因新 field 缺失而 fail；新 Earn intent 必顯式填)。
    #[serde(default = "default_intent_type")]
    pub intent_type: IntentType,
    /// Sprint 1B 新增 — Earn-specific payload (per §3.2 earn_governance schema)。
    /// trading intent ⇒ None；Earn intent ⇒ Some(EarnIntentPayload)。
    /// 不違反既有 trading hot-path (None 短路)。
    #[serde(default)]
    pub earn_payload: Option<EarnIntentPayload>,
}

fn default_intent_type() -> IntentType {
    IntentType::OpenLong
}

/// EarnIntentPayload — Earn-specific intent payload (per earn_governance §3.2 + V100
/// earn_movement_log schema)。
///
/// 設計依據：
///   - V100 earn_movement_log 10 column 對映：amount_usdt / apr_at_time / direction
///     (intent_type) / engine_mode (resolve from caller) / api_scope_used (`account:earn:write`)
///     + reconciliation_status (writer 預設 'pending')；
///   - earn_governance §3.2 line 173-185 明列 intent payload 概念 schema；
///   - product_id + tenor_days 對映 Bybit V5 Earn API param (flexible product_id /
///     fixed product_id + tenor_days)；
///   - approval_id Uuid 對映 authorization.json approval UUID (per CLAUDE.md §四
///     5-gate Gate b authz_id)。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EarnIntentPayload {
    /// stake / redeem 金額 USDT (高精度;對齊 V100 amount_usdt NUMERIC(18,8))。
    pub amount_usdt: Decimal,
    /// 預期 APR basis points (stake 必填;redeem NULL allowed)。
    /// 對映 V100 apr_at_time REAL (writer 處將 bps → REAL 轉換)。
    pub expected_apr_bps: Option<i32>,
    /// Bybit product_id (flexible product_id 或 fixed product_id；查 E-1/E-6 返回)。
    pub product_id: String,
    /// fixed staking tenor (90 / 180 day)；flexible 不需 (None)。
    pub tenor_days: Option<u32>,
    /// authorization.json UUID (Gate b cross-ref;對映 governance_audit_log.id soft ref)。
    pub approval_id: String,
    /// Operator role string (Gate a actor_id;e.g. "PrimaryOperator" / "BackupOperator")。
    pub actor_id: String,
    /// GUI 提交時的說明文字 (audit forensic;Sprint 1B Earn first stake operator 必填)。
    pub rationale: Option<String>,
}
```

### 2.4 grep verify 既有 callers 不破壞

| Caller | 路徑 | 影響 |
|---|---|---|
| Strategy → OrderIntent constructor | `strategies/{bb_breakout,bb_reversion,grid_trading,ma_crossover}/*.rs` 各策略 | 4 個既有策略 — IntentType 默認 OpenLong / OpenShort (per is_long) + earn_payload=None；既有策略行為**不受影響** |
| IPC consumer | `event_consumer/*.rs` | serde rename_all = "snake_case" + default=OpenLong → 既有 IPC payload 無 intent_type field 仍 deserialize 成功 (backward compat) |
| IntentProcessor.process | `intent_processor/mod.rs` line 171-180 | 新增 `if intent.intent_type.is_earn() { route_earn_path(...) } else { existing_trade_path(...) }` 分支 (E1 IMPL) |
| OrderIntent → DB persistence | `database/intent_writer.rs` | trading.intents schema 可能需擴 intent_type column (Sprint 5+ V### 處理;Sprint 1B 暫不寫 trading.intents for Earn intent) |
| tests | `intent_processor/tests*.rs` + `agent_spine/tests.rs` + `event_consumer/tests/*.rs` | 既有 11 個 OrderIntent fixture builder 必加 intent_type=OpenLong default + earn_payload=None (E2 review must-fix) |

**verdict**：對既有 trading hot-path **0 中斷**；4 既有策略 + IPC + DB writer 全 backward-compat；新 Earn 路徑於 IntentProcessor.process 入口 1 個 branch fork。

---

## §3 LeaseScope::EarnStake + EarnRedeem variant 設計

### 3.1 既有狀態

per `srv/rust/openclaw_core/src/lease_scope.rs` line 34-91 read：

```rust
pub enum LeaseScope {
    TradeEntry,                  // 真實開倉 — IntentProcessor router 唯一 hot path scope
    TradeExit,                   // 真實平倉 — 預留 SM-04 ladder Stage ≥ 2 啟用
    PositionAdjust,              // 倉位調整 — 預留 Strategist 重新 risk-scaled
    CanaryStagePromotion,        // W-AUDIT-9 T6 manual graduated canary stage promotion
}

impl LeaseScope {
    pub fn as_audit_str(self) -> &'static str { ... }    // 4 字串映射
    pub fn requires_operator_authority(self) -> bool { ... }  // 僅 CanaryStagePromotion=true
    pub fn default_ttl_ms(self) -> u32 { ... }           // CanaryStagePromotion=60s / 其他=30s
}
```

**verdict**：4 variant only；無 EarnStake/EarnRedeem variant；既有 SQL CHECK constraint 對齊 4 字串值。

### 3.2 EarnStake + EarnRedeem variant 新增設計

```rust
// 既有 LeaseScope enum 擴 2 variant：
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum LeaseScope {
    TradeEntry,
    TradeExit,
    PositionAdjust,
    CanaryStagePromotion,
    /// Sprint 1B Earn first stake NEW — Bybit Earn stake (flexible/fixed) operation。
    /// TTL 60s (per earn_governance §2.3)；requires_operator_authority=true (per
    /// ADR-0030 + 5-gate Gate a + earn_governance §2.1)；
    /// audit string = "EARN_STAKE" (對齊 V100 earn_movement_log.direction='stake' +
    /// learning.governance_audit_log.event_type='earn_intent_*' pattern)。
    EarnStake,
    /// Sprint 1B Earn first stake NEW — Bybit Earn redeem (flexible/fixed) operation。
    /// 同 EarnStake 但 margin headroom < 30% 時允許走此 path (per earn_governance
    /// §2.4 子檢查 3 Margin auto-redeem floor)；
    /// audit string = "EARN_REDEEM" (對齊 V100 earn_movement_log.direction='redeem')。
    EarnRedeem,
}

impl LeaseScope {
    pub fn as_audit_str(self) -> &'static str {
        match self {
            Self::TradeEntry => "TRADE_ENTRY",
            Self::TradeExit => "TRADE_EXIT",
            Self::PositionAdjust => "POSITION_ADJUST",
            Self::CanaryStagePromotion => "CANARY_STAGE_PROMOTION",
            // Sprint 1B 新增 — SCREAMING_SNAKE_CASE 對齊 W-AUDIT-9 pattern
            Self::EarnStake => "EARN_STAKE",
            Self::EarnRedeem => "EARN_REDEEM",
        }
    }

    pub fn requires_operator_authority(self) -> bool {
        // Earn 路徑 hard fail-closed operator authority (per earn_governance §2.1 +
        // ADR-0020 Layer 2 manual+supervisor only)。
        matches!(
            self,
            Self::CanaryStagePromotion | Self::EarnStake | Self::EarnRedeem
        )
    }

    pub fn default_ttl_ms(self) -> u32 {
        match self {
            // earn_governance §2.3 line 102：「TTL = 60s（與 trading lease 一致）」
            // 對齊 CanaryStagePromotion strict 60s pattern
            Self::CanaryStagePromotion | Self::EarnStake | Self::EarnRedeem => 60_000,
            // hot-path trading scope baseline — 既有 router.rs line 89 顯式覆寫 30s
            Self::TradeEntry | Self::TradeExit | Self::PositionAdjust => 30_000,
        }
    }
}
```

### 3.3 SQL CHECK constraint 同步

V100 LAND 已對 earn_movement_log.direction CHECK ('stake','redeem')；但 governance_audit_log.transition_kind (W-AUDIT-9 T2 V0XX) 與 lease_transitions (V054) 的 CHECK constraint 是否含 'EARN_STAKE' / 'EARN_REDEEM' 待 PA spec 階段 audit (per Wave A PA1)。

**潛在 V### migration**：若既有 `governance.lease_transitions.scope` 或 `governance.canary_stage_log.transition_kind` 有 CHECK constraint 阻 EARN_STAKE/EARN_REDEEM 寫入 ⇒ 需新 V### (V### 編號待 Sprint 1B late §4.1.1 base table audit 後分配；建議 V101 或 V108 per current chain) ALTER CHECK constraint 擴 2 值。

**PA-DRIFT 警示**：per memory `2026-05-23 PA-DRIFT-6 governance audit` 教訓 + V100 governance_approval_id soft ref pattern；E1 IMPL 必須 grep 所有 PG CHECK constraint 提到 lease scope 字串：

```bash
ssh trade-core "psql -h 127.0.0.1 -p 5432 -U trading_admin -d trading_ai -c \
  \"SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint \
    WHERE contype='c' AND \
    pg_get_constraintdef(oid) ~ '(TRADE_ENTRY|TRADE_EXIT|POSITION_ADJUST|CANARY_STAGE_PROMOTION)' \
    ORDER BY conrelid::regclass::text;\""
```

E1 IMPL 階段 Linux PG empirical query 後出 ALTER list — 若 0 conflict ⇒ Sprint 1B 無需新 V###；若 ≥ 1 conflict ⇒ 加 V108 (或 PA late §4.1.1 確認後分配) ALTER CHECK。

### 3.4 grep verify 既有 callers 不破壞

| Caller | 路徑 | 影響 |
|---|---|---|
| router.rs `acquire_lease_for_gate_1_4` | line 100 字面 "TRADE_ENTRY" | E1 IMPL 改用 `intent.intent_type.to_lease_scope().as_audit_str()` (per §2.2) |
| LeaseScope variant exhaustive match | `as_audit_str()` + `requires_operator_authority()` + `default_ttl_ms()` 3 method | 編譯期強制 (exhaustive pattern)；新加 2 variant 不補 match → 編譯 fail (好事) |
| tests | `lease_scope::tests` 4 test (line 207-294) | 必加 EarnStake/EarnRedeem assertion (E2 review must-fix) |
| `governance.lease_transitions` PG INSERT | `database/lease_transition_writer.rs` | scope 字串對映 — V100 已 land 但 lease_transitions 表 (V054) 是否 CHECK 限 4 值需 grep + Linux PG verify |

---

## §4 Bybit Earn 12 endpoint client 設計

### 4.1 新檔規格

`rust/openclaw_engine/src/bybit_earn_client.rs` 新檔 (預估 600-900 LOC)

**設計依據**：對齊既有 `bybit_rest_client.rs` 1367 LOC 範式：
- 共用 `BybitRestClient` 的 `get()` / `post()` / `get_checked()` / `post_checked()` (per line 1072 / 1145 / 1202 / 1215) — 不重複 HTTP / signing / rate limit 邏輯
- 新建 `BybitEarnClient` 結構持 `Arc<BybitRestClient>` reference + 12 endpoint method
- response struct 用 serde derive (對映 tiagosiebler SDK schema)

```rust
//! Bybit V5 Earn API client (Sprint 1B Earn first stake).
//! Bybit V5 Earn API 客戶端 (Sprint 1B Earn first stake)。
//!
//! MODULE_NOTE (中):
//!   - 對齊 bybit_rest_client.rs 範式 (HMAC-SHA256 簽名 / rate limit / retCode 觀測)
//!   - 7 read-only endpoint + 5 write endpoint (per BB C4 verdict + tiagosiebler SDK)
//!   - 不重複 HTTP / signing / rate limit 邏輯 (共用 BybitRestClient 既有 facade)
//!   - retCode != 0 fail-closed 不重試 (per earn_governance §5 + 9 不變量 #7)
//!   - rate limit group = Asset (5 req/s) — 既有 bybit_rest_client::RateLimitGroup::Asset
//!     line 248 已對映 `/v5/asset/` 起頭 path；本 client 使用 `/v5/earn/` 起頭
//!     **必須在 bybit_rest_client.rs line 246-249 `RateLimitGroup::from_path` 補
//!     `/v5/earn/` → Asset 映射** (E1 IMPL must-fix; 否則 Earn endpoint 全走
//!     RateLimitGroup::Other default 不對齊 Asset 5 req/s constraint)。

use crate::bybit_rest_client::{BybitApiError, BybitResult, BybitRestClient};
use rust_decimal::Decimal;
use serde::{Deserialize, Serialize};
use std::sync::Arc;

/// Bybit V5 Earn API client。
/// 對齊 bybit_rest_client.rs BybitRestClient 範式。
pub struct BybitEarnClient {
    /// 共用既有 REST client (HMAC-SHA256 簽名 + rate limit + retCode 觀測)
    rest_client: Arc<BybitRestClient>,
}

impl BybitEarnClient {
    /// 構造新 Earn client (共用既有 BybitRestClient handle)。
    /// 從 IntentProcessor 或 Daily reconciliation cron 注入既有 rest_client 實例。
    pub fn new(rest_client: Arc<BybitRestClient>) -> Self {
        Self { rest_client }
    }

    // ====== Read-only endpoint (7 個) ======

    /// E-1: GET /v5/earn/flexible/product
    /// Flexible USDT savings product list (APR + tier + product_id)。
    /// Read-Only scope sufficient (per BB C5 verdict)。
    pub async fn get_flexible_product_list(
        &self,
        coin: &str,  // "USDT"
    ) -> BybitResult<EarnFlexibleProductListResponse> {
        let params = vec![("coin", coin)];
        let resp = self.rest_client.get_checked("/v5/earn/flexible/product", &params).await?;
        serde_json::from_value::<EarnFlexibleProductListResponse>(resp.result)
            .map_err(BybitApiError::JsonParse)
    }

    /// E-4: GET /v5/earn/flexible/position
    /// Flexible position query (含 availableAmount + freezeDetails per BB Part A.2)。
    pub async fn get_flexible_position(&self, coin: &str) -> BybitResult<EarnFlexiblePositionResponse> {
        // ... 同上範式 ...
    }

    /// E-5: GET /v5/earn/apr-history
    /// APR 歷史 (ML learning + drift detection)。
    pub async fn get_apr_history(&self, product_id: &str) -> BybitResult<EarnAprHistoryResponse> {
        // ... 同上範式 ...
    }

    /// E-9: GET /v5/earn/fixed/position — Fixed-term position query。
    pub async fn get_fixed_position(&self, coin: &str) -> BybitResult<EarnFixedPositionResponse> { ... }

    /// E-10: GET /v5/earn/order/query-history — Earn order 歷史 (reconciliation + audit)。
    pub async fn get_order_history(&self, ...) -> BybitResult<EarnOrderHistoryResponse> { ... }

    /// E-11: GET /v5/earn/position/query — Unified position (flex + fixed)。
    pub async fn get_unified_position(&self, coin: &str) -> BybitResult<EarnUnifiedPositionResponse> { ... }

    /// E-12: GET /v5/earn/fixed/order/list — Fixed staking order list。
    pub async fn get_fixed_order_list(&self, ...) -> BybitResult<EarnFixedOrderListResponse> { ... }

    // ====== Write endpoint (5 個) ======

    /// E-2: POST /v5/earn/flexible/subscribe — Flexible stake (Sprint 1B first stake 主要 path)。
    /// Scope = Earn (per BB C5 non-withdraw)。
    pub async fn subscribe_flexible(
        &self,
        product_id: &str,
        amount: Decimal,
    ) -> BybitResult<EarnSubscribeResponse> {
        let body = serde_json::json!({
            "productId": product_id,
            "amount": amount.to_string(),
        });
        let resp = self.rest_client.post_checked("/v5/earn/flexible/subscribe", &body).await?;
        serde_json::from_value::<EarnSubscribeResponse>(resp.result)
            .map_err(BybitApiError::JsonParse)
    }

    /// E-3: POST /v5/earn/flexible/redeem — Flexible redeem。
    pub async fn redeem_flexible(&self, ...) -> BybitResult<EarnRedeemResponse> { ... }

    /// E-6: POST /v5/earn/fixed/product — Fixed-term product list (POST due to filter params)。
    pub async fn get_fixed_product_list(&self, ...) -> BybitResult<EarnFixedProductListResponse> { ... }

    /// E-7: POST /v5/earn/fixed/order/place — Fixed-term stake (OP-3 fixed staking path)。
    pub async fn place_fixed_order(&self, ...) -> BybitResult<EarnFixedPlaceResponse> { ... }

    /// E-8: POST /v5/earn/fixed/order/redeem — Fixed-term redeem (提前贖回)。
    pub async fn redeem_fixed(&self, ...) -> BybitResult<EarnFixedRedeemResponse> { ... }
}

// Response struct 12 個 (對映 tiagosiebler SDK schema — E1 IMPL 期 cross-ref BB Part H 字典補錄)

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EarnFlexibleProduct {
    #[serde(rename = "productId")]
    pub product_id: String,
    pub coin: String,
    /// APR (e.g. "0.10" for 10%) — Bybit 返回字串需自行解析為 f64
    pub apr: String,
    #[serde(rename = "minPurchaseAmount")]
    pub min_purchase_amount: String,
    #[serde(rename = "maxPurchaseAmount")]
    pub max_purchase_amount: Option<String>,
    // ... 更多 field per Bybit V5 spec
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EarnFlexibleProductListResponse {
    pub list: Vec<EarnFlexibleProduct>,
}

// ... 11 個 response struct 類似 ...
```

### 4.2 既有 bybit_rest_client.rs 必要 patch

| Patch # | 路徑 | 改動 | E1 IMPL Owner |
|---|---|---|---|
| Patch-1 | `bybit_rest_client.rs` line 246-249 `RateLimitGroup::from_path` | 加 `else if path.starts_with("/v5/earn/")` 分支 → `Self::Asset` (5 req/s 對齊) | E1 (Wave B E1c LeaseScope variant 同 PR) |
| Patch-2 | `bybit_rest_client.rs` `mod` 註冊 | 在 `lib.rs` 或 `mod.rs` 加 `pub mod bybit_earn_client;` | E1 |

### 4.3 fail-closed 處理 (per earn_governance §5)

```rust
// E1 IMPL Wave B caller (IntentProcessor.process Earn 分支)：
async fn execute_earn_intent(
    intent: &OrderIntent,
    payload: &EarnIntentPayload,
    earn_client: &BybitEarnClient,
    writer: &EarnMovementLogWriter,
    governance: &GovernanceCore,
    lease_id: &LeaseId,
) -> Result<EarnIntentResult, String> {
    // 1. 對映 IntentType → API call
    let api_result = match intent.intent_type {
        IntentType::EarnStake => {
            if payload.tenor_days.is_some() {
                earn_client.place_fixed_order(&payload.product_id, payload.amount_usdt, payload.tenor_days.unwrap()).await
            } else {
                earn_client.subscribe_flexible(&payload.product_id, payload.amount_usdt).await
            }
        }
        IntentType::EarnRedeem => { ... }
        _ => unreachable!("execute_earn_intent must only be called with EarnStake/EarnRedeem"),
    };

    // 2. fail-closed (per earn_governance §5.1 + §5.2)
    let bybit_response = match api_result {
        Ok(resp) => resp,
        Err(BybitApiError::Business { ret_code, ret_msg, .. }) => {
            // retCode != 0 → 不重試 + 寫 audit log failure
            writer.write_failure(payload, ret_code, &ret_msg).await?;
            governance.release_lease(lease_id, LeaseOutcome::Cancelled)?;
            return Err(format!("earn_api_fail_closed: retCode={ret_code}, retMsg={ret_msg}"));
        }
        Err(BybitApiError::Transport(e)) => {
            // HTTP timeout / network error → fail-closed
            writer.write_failure(payload, -1, &format!("transport_error: {e}")).await?;
            governance.release_lease(lease_id, LeaseOutcome::Cancelled)?;
            return Err(format!("earn_api_transport_fail: {e}"));
        }
        Err(e) => {
            writer.write_failure(payload, -2, &format!("unknown_error: {e:?}")).await?;
            governance.release_lease(lease_id, LeaseOutcome::Cancelled)?;
            return Err(format!("earn_api_unknown_fail: {e:?}"));
        }
    };

    // 3. 寫 success audit log (V100 earn_movement_log)
    writer.write_success(payload, &bybit_response, lease_id).await?;

    Ok(EarnIntentResult { ... })
}
```

---

## §5 V100 earn_movement_log writer 接線

### 5.1 V100 schema 已 LAND (per Sprint 4+ §4.1.1 PA-DRIFT-6 patch closure)

per `srv/sql/migrations/V100__m4_hypothesis_base_table.sql` line 355-379 read：

```sql
CREATE TABLE IF NOT EXISTS learning.earn_movement_log (
    movement_id                BIGSERIAL PRIMARY KEY,
    event_ts                   TIMESTAMPTZ NOT NULL,
    direction                  TEXT NOT NULL
                               CHECK (direction IN ('stake', 'redeem')),
    amount_usdt                NUMERIC(18, 8) NOT NULL,
    apr_at_time                REAL,
    -- governance_approval_id soft reference 不是 FK constraint (per PA-DRIFT-6 lesson)
    governance_approval_id     BIGINT,
    bybit_response_payload     JSONB,
    engine_mode                TEXT NOT NULL
                               CHECK (engine_mode IN ('paper', 'demo', 'live_demo', 'live')),
    api_scope_used             TEXT NOT NULL,
    reconciliation_status      TEXT NOT NULL DEFAULT 'pending'
                               CHECK (reconciliation_status IN (
                                   'pending', 'matched', 'mismatch'
                               ))
);
```

**hot-path index**：`idx_earn_movement_log_strategy_ts` (line 409-410) on (event_ts DESC) — 對 Daily reconciliation cron `WHERE event_ts > now() - INTERVAL '24 hours' ORDER BY event_ts DESC` 高效。

### 5.2 Writer 設計

新建 `rust/openclaw_engine/src/database/earn_movement_writer.rs` (~250 LOC)

```rust
//! V100 learning.earn_movement_log writer (Sprint 1B Earn first stake)。
//! V100 learning.earn_movement_log 寫入器 (Sprint 1B Earn first stake)。
//!
//! MODULE_NOTE (中):
//!   - 對齊 V100 schema 10 column (movement_id BIGSERIAL PK / event_ts / direction
//!     CHECK 2 enum / amount_usdt NUMERIC(18,8) / apr_at_time REAL / governance_approval_id
//!     BIGINT soft ref / bybit_response_payload JSONB / engine_mode CHECK 4 enum /
//!     api_scope_used TEXT / reconciliation_status CHECK 3 enum DEFAULT 'pending')
//!   - INSERT placeholder 範式：5-gate 全 PASS 後 INSERT placeholder (outcome=pending)
//!     → Bybit API call → UPDATE reconciliation_status + bybit_response_payload
//!     (per earn_governance §2.5)
//!   - governance_approval_id soft ref：寫入時取 governance_audit_log.id 反查
//!     (per PA-DRIFT-6 lesson 2026-05-23 + V100 line 502-511 comment)
//!   - fail-closed: PG INSERT 失敗 → governance integrity 破損 → lease release +
//!     reject intent + GUI alert (per earn_governance §2.5 Audit gate)

use rust_decimal::Decimal;
use sqlx::PgPool;

pub struct EarnMovementWriter {
    pool: PgPool,
}

impl EarnMovementWriter {
    pub fn new(pool: PgPool) -> Self { Self { pool } }

    /// Step 1 — INSERT placeholder (5-gate PASS 後;Bybit API call 前)。
    /// per earn_governance §2.5 line 129 「DB INSERT placeholder（outcome=pending）」。
    pub async fn insert_placeholder(
        &self,
        payload: &EarnIntentPayload,
        intent_type: IntentType,  // EarnStake / EarnRedeem
        governance_approval_id: i64,  // soft ref to learning.governance_audit_log.id
        engine_mode: &str,  // 對齊 V100 CHECK 4 enum
        api_scope_used: &str,  // e.g. "account:earn:write" per earn_governance §2.5 line 132
    ) -> Result<i64, sqlx::Error> {
        let direction = match intent_type {
            IntentType::EarnStake => "stake",
            IntentType::EarnRedeem => "redeem",
            _ => return Err(sqlx::Error::Protocol("invalid intent_type for earn writer".into())),
        };
        let apr_at_time: Option<f32> = payload.expected_apr_bps.map(|bps| (bps as f32) / 10000.0);

        let row: (i64,) = sqlx::query_as(
            "INSERT INTO learning.earn_movement_log (
                event_ts, direction, amount_usdt, apr_at_time,
                governance_approval_id, bybit_response_payload,
                engine_mode, api_scope_used, reconciliation_status
            ) VALUES (now(), $1, $2, $3, $4, NULL, $5, $6, 'pending')
            RETURNING movement_id"
        )
        .bind(direction)
        .bind(&payload.amount_usdt)
        .bind(apr_at_time)
        .bind(governance_approval_id)
        .bind(engine_mode)
        .bind(api_scope_used)
        .fetch_one(&self.pool)
        .await?;

        Ok(row.0)
    }

    /// Step 2 — UPDATE bybit_response_payload + reconciliation_status (Bybit API ack 後)。
    pub async fn update_outcome(
        &self,
        movement_id: i64,
        bybit_response: &serde_json::Value,
        outcome: &str,  // 'matched' / 'mismatch' / 'pending' (Daily cron 更新)
    ) -> Result<(), sqlx::Error> {
        sqlx::query(
            "UPDATE learning.earn_movement_log
             SET bybit_response_payload = $1, reconciliation_status = $2
             WHERE movement_id = $3"
        )
        .bind(bybit_response)
        .bind(outcome)
        .bind(movement_id)
        .execute(&self.pool)
        .await?;
        Ok(())
    }

    /// 寫 failure row (per earn_governance §5.1 — retCode != 0 / timeout 等)。
    pub async fn write_failure(
        &self,
        payload: &EarnIntentPayload,
        ret_code: i64,
        ret_msg: &str,
    ) -> Result<(), sqlx::Error> {
        // failure row = direction='stake' / amount=intended amount / reconciliation_status='mismatch'
        // bybit_response_payload = { "ret_code": N, "ret_msg": "...", "failure_reason": "..." }
        // ... 同 insert_placeholder + 立刻 update bybit_response_payload ...
        Ok(())
    }

    /// Daily reconciliation cron 用 — past 24h pending 記錄 → 對賬 → update 為 matched/mismatch。
    pub async fn fetch_past_24h_pending(&self) -> Result<Vec<EarnMovementRow>, sqlx::Error> {
        sqlx::query_as::<_, EarnMovementRow>(
            "SELECT movement_id, event_ts, direction, amount_usdt, apr_at_time,
                    governance_approval_id, bybit_response_payload, engine_mode,
                    api_scope_used, reconciliation_status
             FROM learning.earn_movement_log
             WHERE event_ts > now() - INTERVAL '24 hours'
               AND reconciliation_status = 'pending'
             ORDER BY event_ts DESC"
        )
        .fetch_all(&self.pool)
        .await
    }
}

#[derive(Debug, sqlx::FromRow)]
pub struct EarnMovementRow { ... }  // 10 column row mapping
```

### 5.3 Daily reconciliation cron 設計 (per earn_governance §6)

新建 `rust/openclaw_engine/src/cron/earn_reconciliation.rs` (~150 LOC)

```rust
//! Daily Earn reconciliation cron (Sprint 1B Earn first stake)。
//! 每日 Earn 對賬 cron (Sprint 1B Earn first stake)。
//!
//! MODULE_NOTE (中):
//!   - 每日 UTC 02:00 (避 funding settlement 00:00 + 08:00 + 16:00) 觸發
//!   - Query Bybit Earn account balance (E-11 get_unified_position) read-only
//!   - Sum local V100 earn_movement_log past 全期 net flow (stake - redeem)
//!   - Compare diff = bybit_reported - local_computed (per earn_governance §6.1)
//!   - diff thresholds (per earn_governance §6.2):
//!     - abs(diff) < $0.01 → status='ok'
//!     - $0.01 ≤ abs(diff) < $1.00 → status='mismatch' + alert (不 disable)
//!     - abs(diff) ≥ $1.00 → status='mismatch_critical' + 自動 earn_enabled=false
//!     - 連續 3 day mismatch → halt strategy (per earn_governance §6.2 + v5.7 §9 Kill Criteria)
//!   - reconciliation cron 自身 fail (API timeout / DB error) → 不計 mismatch
//!     (per earn_governance §6.3) + 寫 audit log + 次日重試
//!   - 連續 3 day cron 自身 fail → halt strategy

pub struct EarnReconciliationCron {
    earn_client: Arc<BybitEarnClient>,
    writer: Arc<EarnMovementWriter>,
    risk_config: Arc<ArcSwap<RiskConfig>>,
    governance: Arc<GovernanceCore>,
}

impl EarnReconciliationCron {
    pub async fn run_daily(&self) -> Result<ReconciliationResult, String> {
        // Step 1: Query Bybit balance
        let bybit_balance: Decimal = self.earn_client.get_unified_position("USDT").await
            .map(|resp| extract_total_balance(&resp))
            .map_err(|e| format!("cron_fail_bybit: {e:?}"))?;

        // Step 2: Compute local net flow from V100
        let local_net: Decimal = self.compute_local_net_flow().await?;

        // Step 3: Diff + classify (per §6.2)
        let diff = bybit_balance - local_net;
        let outcome = if diff.abs() < dec!(0.01) {
            "ok"
        } else if diff.abs() < dec!(1.00) {
            "mismatch"  // alert 但不 disable
        } else {
            "mismatch_critical"  // 自動 earn_enabled=false
        };

        // Step 4: 對 past 24h pending row update reconciliation_status
        let pending_rows = self.writer.fetch_past_24h_pending().await
            .map_err(|e| format!("cron_fail_pg_fetch: {e:?}"))?;
        for row in pending_rows {
            let row_outcome = compute_row_outcome(&row, bybit_balance, local_net);
            self.writer.update_outcome(row.movement_id, &row.bybit_response_payload, &row_outcome).await
                .map_err(|e| format!("cron_fail_pg_update: {e:?}"))?;
        }

        // Step 5: 連續 3 day mismatch → halt
        if outcome == "mismatch_critical" {
            self.disable_earn_until_manual_reset().await?;
        }
        let consecutive_days = self.count_consecutive_mismatch_days().await?;
        if consecutive_days >= 3 {
            self.halt_strategy().await?;
        }

        Ok(ReconciliationResult { diff, outcome, consecutive_days })
    }
}
```

---

## §6 5 AC + earn_governance spec 五角色 cross-ref pending matrix

### 6.1 5 AC verify checklist (per earn_governance §9 AC-1~6)

| AC | 內容 | 驗證方法 | E2 review owner |
|---|---|---|---|
| **AC-1** 0 hard-coded credentials | grep 所有 Earn 路徑 0 hit `api_key=` / `secret=` | E2 grep + node --check | E2 + E3 |
| **AC-2** 0 bypass paths | grep 0 hit `submit_earn_intent` / `EarnIntentProcessor` / 直呼 Bybit Earn endpoint | E2 grep + healthcheck `[earn-bypass]` 監測 24h Earn API request 100% lease_id header | E2 |
| **AC-3** audit log 100% coverage | 每 stake/redeem 在 V100 earn_movement_log 必 1 row + lease_id + authz_id + actor_id + bybit_request/response_payload cross-ref | QA Stage 0R replay + Linux PG empirical query | QA + MIT |
| **AC-4** Daily reconciliation cron | cron 每日 UTC 02:00 (per §5.3 改 02:00 對齊 earn_governance §6.1) + 自身 fail 計數獨立 + mismatch_critical 自動 earn_enabled=false + 連續 3 day halt | systemd timer + PG dry-run 7d evidence | E1 + QA |
| **AC-5** Runbook draft | `srv/docs/runbook/earn_operations_runbook.md` 5 section stub (per earn_governance §9 AC-5) | PA spec output 階段 stub 起草 + Sprint 1B 末 land 實檔 | PA + QA |
| **AC-6** 16 原則 + 9 不變量 final check | CC re-audit verdict A/B+ + FA Approve + 0 hard boundary 觸碰 | CC + FA review | CC + FA |

### 6.2 earn_governance spec 五角色 cross-ref pending matrix

per earn_governance §12 line 477-499：

| 角色 | 範圍 + 必驗點 | Verdict 等待 | Report 路徑 | 阻塞 Wave B IMPL? |
|---|---|---|---|---|
| **CC** | 16 原則 + 9 不變量 + 5-gate self-draft | ✅ DONE | `srv/docs/CCAgentWorkSpace/CC/workspace/reports/2026-05-21--v57_c8_earn_governance_spec.md` (本 spec 自身) | 否 (self-draft 不重簽) |
| **FA** | 22 治理文件 Gap 對 Earn 覆蓋 + ADR-0030 consistency + Spec Compliance | ⬜ PENDING (D+1 2026-05-22 未 land) | `srv/docs/CCAgentWorkSpace/FA/workspace/reports/2026-05-22--earn_governance_spec_review.md` | **YES — OP-4 前置** |
| **E3** | Secret slot scope + fail-closed boundary + deploy + OWASP | ⬜ PENDING | `srv/docs/CCAgentWorkSpace/E3/workspace/reports/2026-05-22--earn_governance_spec_review.md` | **YES — OP-4 前置** |
| **QA** | AC-1~6 testability + runbook + reconciliation 自動化 + E2E | ⬜ PENDING | `srv/docs/CCAgentWorkSpace/QA/workspace/reports/2026-05-22--earn_governance_spec_review.md` | **YES — OP-4 前置** |
| **MIT** | §3.2 payload schema 與 V100 schema 一致性 + audit field + DB schema design | ⬜ PENDING | `srv/docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-22--earn_governance_spec_review.md` | **YES — OP-4 前置** |
| **BB** | 12 endpoint v BB v57-C4 verdict + ToS / KYC + Bybit Earn rate limit + mainnet boundary | ⬜ PENDING | `srv/docs/CCAgentWorkSpace/BB/workspace/reports/2026-05-22--earn_governance_spec_review.md` | **YES — OP-4 前置** |

**Cross-ref dispatch SOP** (per earn_governance §12 line 485-499)：
1. 並行 dispatch FA + E3 + QA + MIT + BB (5 sub-agent / D+1 內 land)
2. 每角色 1-2 hr / 5 角色合計 5-12 hr
3. 每角色 verdict ∈ {✅ APPROVE / ⚠️ APPROVE-WITH-CAVEAT / ❌ NEEDS-FIX}
4. 5/5 ✅ 或 4/5 ✅ + 1/5 ⚠️ minor caveat → spec 升 SPEC-FINAL，CC sign-off → OP-4 unblock
5. 任 1 ❌ NEEDS-FIX → CC 接收 + 修正 + 再 dispatch (最多 2 輪)

### 6.3 PA 對 earn_governance spec 自身 verdict (cross-ref 一票)

per spec §12 list 五角色 **未含 PA** (CC self-draft + FA + E3 + QA + MIT + BB)；但 PA 本次 dispatch packet 起草階段已 cross-ref §1-§11 spec 主體 +  §12 16 原則 + 9 不變量 coverage matrix；本 PA 視角 verdict 如下：

| 範圍 | PA 視角 verdict |
|---|---|
| §1 目標 + 適用範圍 | ✅ APPROVE (in/out of scope 明確;不重疊既有 trading hot-path) |
| §2 5-gate boundary | ✅ APPROVE (Gate a-e 與既有 trading 對齊;Earn-specific 子檢查 5 個合理) |
| §3 IntentProcessor 復用 | ⚠️ APPROVE-WITH-CAVEAT (line 159-167 IntentType enum 列 6 variant 缺 PositionAdjust;§2.2 本 dispatch packet 修正為 7 variant + CloseLong/Short 預留;CC 補)；OrderIntent struct 擴 intent_type field 改 spec §3 line 159 + 註 backward-compat 路徑 |
| §4 OPENCLAW_ALLOW_MAINNET | ✅ APPROVE (per PM 2026-05-21 仲裁 4 採條件 A finalize;§4.2 規格清晰) |
| §5 fail-closed | ✅ APPROVE (5 失敗模式枚舉 + 連續 3 disable 設計合理;但**§5.3 disable 機制細節** `risk_config_*.toml` patch vs ArcSwap 熱重載 hook 未明 — E1 IMPL 階段必 spec) |
| §6 Daily reconciliation | ✅ APPROVE (UTC 00:30 vs PA dispatch §5.3 改 02:00 對齊 — **§6.1 line 308 UTC 00:30 應改 UTC 02:00** 避 funding settlement 00:00 + 08:00 + 16:00) |
| §7 9 安全不變量 | ✅ APPROVE (9/9 PASS) |
| §8 16 原則 | ⚠️ APPROVE-WITH-CAVEAT (15/16 PASS;#13 AI 成本感知 由 v57-C? counterfactual statistics spec 處理 — 但本 spec 未明 reference 何處接;PM 接 OP-4 後追蹤) |
| §9 AC-1~6 | ✅ APPROVE (testable + verifiable) |
| §10 IMPL prereq + downstream dispatch | ✅ APPROVE |
| §11 風險登記簿 | ✅ APPROVE (RISK-1 條件 B 已不適用 per §4.2 condition A) |
| §12 五角色 cross-ref pending matrix | ⬜ PENDING (FA + E3 + QA + MIT + BB D+1 未 land — OP-4 前置阻塞) |

**PA overall verdict**：⚠️ **APPROVE-WITH-2-CAVEATS** (兩 caveat = §3 IntentType enum 範圍 7 variant + §6.1 UTC 02:00 改正)
- Caveat 解除 = CC 接收 PA verdict 後修 2 處 (spec §3 line 159-167 加 CloseLong/Short variant + §6.1 line 308 改 UTC 02:00)
- 若 CC 接受 caveat → spec status → DRAFT-WITH-PA-CAVEATS-RESOLVED → FA + E3 + QA + MIT + BB 並行 cross-ref
- 5 角色 cross-ref 結果 → final spec sign → OP-4 closed → Wave B IMPL dispatch ready

---

## §7 8-step IMPL dispatch chain

### 7.1 Pre-Wave operator actions (~30-45 min)

```
Wave 0a — operator action (~5 min)
└─ OP-1: D+1 OpenClaw Bybit key 發行日 5 min query
   ├─ Bybit Web → API management → 既有 key edit
   ├─ 看 "Last edited" 日期
   ├─ 若 ≥ 2026-04-09 → key 自動帶 Earn scope (per BB C5 verdict)
   └─ 若 < 2026-04-09 → operator 重發 key 加 Earn scope (+30-60 min action)

Wave 0b — operator decision (~10 min)
└─ OP-2: first stake $200-400 拍板
   ├─ AMD-2026-05-15-01 Stage 1 micro-canary $100 對齊 OR override
   ├─ Bybit flexible tier 1 $200 @ ~10% APR boundary 考慮
   └─ 影響 EarnIntentPayload.amount_usdt + Daily Earn cap risk_config

Wave 0c — operator decision (~5 min)
└─ OP-3: flexible (30 day flex) vs fixed (90/180 day) staking 拍板
   ├─ Sprint 1B 過短 (W9-12) → 建議 flexible (隨時 redeem)
   ├─ fixed 鎖倉 90/180 day 過長 → Sprint 2+ 再評估
   └─ 影響 IMPL 路徑：flexible only → E-2 + E-3 IMPL；fixed → E-7 + E-8 IMPL

Wave 0d — operator decision (~5 min + sub-agent parallel dispatch ~5-12 hr)
└─ OP-4: earn_governance spec 五角色 cross-ref final sign
   ├─ PM 接 PA verdict (本 packet §6.3) → CC 修 2 caveat (~1 hr)
   ├─ FA + E3 + QA + MIT + BB 並行 cross-ref dispatch (~5-12 hr 並行)
   ├─ 5/5 ✅ 或 4/5 ✅ + 1/5 ⚠️ minor caveat → CC sign-off
   └─ spec status DRAFT-FOR-FIVE-ROLE-CROSS-REF → SPEC-FINAL
```

### 7.2 Wave A — PA spec + readiness (並行 wall-clock 8-12 hr)

```
Wave A (Owner: PA + CC)
├─ PA1: 本 dispatch packet 起草 (本 report;DONE 2026-05-23)
├─ PA2: V100 earn_movement_log writer SQL/Rust binding spec finalize (2-3 hr;§5.2)
├─ PA3: cron/earn_reconciliation.rs spec finalize (2-3 hr;§5.3)
├─ PA4: Linux PG empirical CHECK constraint audit (per §3.3 — grep 是否要 V108 ALTER CHECK
│        scope = EARN_STAKE/EARN_REDEEM;若需 → 新 V### spec) (1-2 hr)
└─ CC: earn_governance spec PA caveat 解除 (§6.3 — §3 IntentType 7 variant + §6.1 UTC 02:00) (1 hr)
```

### 7.3 Wave B — 5 並行 E1 IMPL (wall-clock 2-3 day)

```
Wave B (Owner: 5 並行 E1 + 1 E1a;前置 = Wave 0 + Wave A 完成)
├─ E1a (4-6 hr): IntentType enum 新建 + OrderIntent struct 擴 intent_type + earn_payload field
│   - srv/rust/openclaw_engine/src/intent_processor/mod.rs line 59-94 patch
│   - 4 既有策略 (bb_breakout/bb_reversion/grid_trading/ma_crossover) OrderIntent constructor 補 intent_type default
│   - 11 既有 test fixture 補 intent_type=OpenLong default
│   - serde rename_all + default backward-compat verify
│
├─ E1b (2-3 hr): LeaseScope variant 新增 EarnStake + EarnRedeem
│   - srv/rust/openclaw_core/src/lease_scope.rs line 35-91 patch
│   - as_audit_str() / requires_operator_authority() / default_ttl_ms() 3 method exhaustive match 補
│   - 4 既有 test + 新加 2 test (EarnStake / EarnRedeem)
│   - 若 PA4 audit 出 V### CHECK constraint 阻 → 同 PR 加 V108 ALTER (Linux PG empirical dry-run 必跑)
│
├─ E1c (10-15 hr): bybit_earn_client.rs 新建 (§4.1)
│   - 12 endpoint method + 12 response struct (對齊 tiagosiebler SDK schema)
│   - 共用 BybitRestClient.get_checked() / post_checked()
│   - bybit_rest_client.rs RateLimitGroup::from_path 加 /v5/earn/ → Asset (§4.2 Patch-1)
│   - 12 endpoint unit test (對齊 BB Part A.2 reference SDK)
│
├─ E1d (5-7 hr): EarnMovementWriter (§5.2) + IntentProcessor Earn 分支接線
│   - srv/rust/openclaw_engine/src/database/earn_movement_writer.rs (新建 ~250 LOC)
│   - srv/rust/openclaw_engine/src/intent_processor/mod.rs process() Earn 分支接線
│   - governance_audit_log.id soft ref 反查邏輯 (per V100 PA-DRIFT-6 lesson)
│   - INSERT placeholder → API call → UPDATE outcome 範式
│
├─ E1e (4-6 hr): Daily reconciliation cron + RiskConfig hot-reload hook
│   - srv/rust/openclaw_engine/src/cron/earn_reconciliation.rs (新建 ~150 LOC)
│   - systemd timer UTC 02:00 (或內嵌 Tokio scheduler;對齊既有 ml_training cron 範式)
│   - earn_enabled=false 自動寫 risk_config_*.toml + ArcSwap 熱重載 hook
│   - 連續 3 day mismatch → halt strategy
│
└─ E1a (GUI; 8-12 hr): governance tab Earn manual stake form
   - srv/program_code/api/templates/governance.html + governance-tab.js
   - type-to-confirm + A3 wizard pattern
   - 阻於 H2 Console tab 4 sub-section 歸屬決策 (Sprint 1A-β D+5 12-check #9 operator carry-over)
   - 此 sub-task **可延 W+2** 因為 Sprint 1B first stake operator 可走 GUI shell + Bybit Web UI hybrid path
```

### 7.4 Wave C — 三方並行 review (wall-clock 1 day)

```
Wave C (前置 = Wave B 完成 + sub-agent IMPL DONE 自評)
├─ E2 (3-5 hr): adversarial review (per feedback_impl_done_adversarial_review)
│   - 16 原則 1/3/4/8 + 5-gate boundary + fail-closed
│   - grep 0 bypass + 0 hard-coded credential
│   - exhaustive match 完整性 (LeaseScope + IntentType)
│   - intent_type default backward-compat verify
│   - earn_movement_log writer transaction rollback 路徑
│
├─ BB (1-2 hr): Bybit ToS / KYC / 地理 / 12 endpoint v BB C4 verdict
│   - 12 endpoint path + scope + rate limit group 對齊
│   - retCode != 0 fail-closed pattern
│   - Bybit Earn rate limit (5 req/s Asset group) v Daily reconciliation cron 衝突 check (per earn_governance §11 RISK-3)
│
└─ E3 (1-2 hr): secret slot governance + OWASP
   - operator OP-1 完成後 Earn scope key 三端同步
   - api_scope_used field 寫入 audit trail
   - fail-closed boundary 不違反 CLAUDE.md §四
```

### 7.5 Wave D — regression + Acceptance (wall-clock 0.5-1 day)

```
Wave D (sequential 前置 = Wave C 全 ✅ APPROVE)
├─ E1: round 2 fix (0-4 hr;Wave C review fix)
├─ E4 (1-2 hr): regression
│   - cargo test (5 unit test + IntentType + LeaseScope + earn_client + writer)
│   - pytest integration test (Python ↔ Rust IPC 包 intent_type / earn_payload field)
│   - cross-strategy attribution_chain_ok = 100% (既有 4 策略 + Earn intent 不污染)
│
└─ QA (2-4 hr): Stage 0R replay preflight + 5-gate boundary verify + Acceptance
   - replay 過去 V100 earn_movement_log row PG empirical query (~0 row first deploy)
   - 5-gate boundary 5 個 reject path 各觸 1 次 + 寫 audit log empirical verify
   - AC-1~6 6 個 acceptance criteria 逐條 ✅
```

### 7.6 Wave E — operator first stake execution + PM closure (wall-clock 0.5 day)

```
Wave E (operator 親手執行)
├─ operator (10-30 min): GUI manual stake first execution
│   - operator OP-2 + OP-3 拍板數額 + product type 已知
│   - GUI Earn governance tab → type-to-confirm + A3 wizard 提交 EarnIntentPayload
│   - 5-gate 全 PASS → IntentProcessor → bybit_earn_client.subscribe_flexible / place_fixed_order
│   - V100 earn_movement_log INSERT placeholder → Bybit API ack → UPDATE outcome
│   - GUI 顯示成功 + movement_id + bybit_response_payload
│
├─ operator (5 min): Linux PG empirical verify
│   - ssh trade-core psql 查 learning.earn_movement_log 1 row inserted + 10 column 全填 + reconciliation_status='pending'
│   - 查 learning.governance_audit_log 至少 5 row (5-gate audit event_type)
│
└─ PM (1 hr): Phase 3e sign-off
   - Sprint 1B Pending 3.2 Earn first stake closure
   - 22 sign-off invariant verify
   - report path mark + memory update
```

### 7.7 整體 wall-clock + sub-agent 並行度

| Wave | Owner 數 | Wall-clock | Core hr | Sub-agent 並行峰值 |
|---|---|---|---|---|
| Wave 0 | operator | 30-45 min | – | 0 (operator-only) |
| Wave A | PA + CC | 8-12 hr (並行) | 6-9 hr | 1 PA (PA1 已 DONE;PA2-4 + CC 並行) |
| Wave B | 5 並行 E1 + 1 E1a (GUI) | 2-3 day | 30-45 hr | 5-6 並行 (per dispatch_packet §2 ceiling) |
| Wave C | E2 + BB + E3 並行 | 1 day | 5-9 hr | 3 並行 |
| Wave D | E1 fix + E4 + QA | 0.5-1 day | 3-10 hr | 2 並行 (E4 + QA;E1 fix 序列) |
| Wave E | operator + PM | 0.5 day | 1-2 hr | 0 (operator + PM) |
| **合計** | – | **4-6 day** | **45-75 hr core** | peak 5-6 並行 |

---

## §8 Estimate split

### 8.1 Hour breakdown

| 階段 | Owner | Estimate hr |
|---|---|---|
| **PA spec** | PA1 (本 packet 起草 + earn_governance verdict) + PA2 (V100 writer spec) + PA3 (reconciliation cron spec) + PA4 (Linux PG CHECK audit) | **10-15 hr** |
| **CC caveat 修正** | CC | 1 hr |
| **earn_governance spec 五角色 cross-ref** | FA + E3 + QA + MIT + BB 並行 | 5-12 hr |
| **E1 IMPL Wave B (5 並行)** | E1a IntentType (4-6) + E1b LeaseScope (2-3) + E1c bybit_earn_client (10-15) + E1d EarnMovementWriter (5-7) + E1e reconciliation cron (4-6) + E1a GUI (8-12) | **30-45 hr** (含 GUI;不含 GUI 22-37 hr) |
| **E2 + BB + E3 review** | 並行 | 5-9 hr |
| **E1 round 2 fix** | E1 | 0-4 hr |
| **E4 regression** | E4 | 1-2 hr |
| **QA Acceptance** | QA | 2-4 hr |
| **operator first stake + PG verify** | operator | 0.5-1 hr (含 verify) |
| **PM Phase 3e closure** | PM | 1 hr |
| **合計 core** | – | **50-78 hr** |

### 8.2 並行 wall-clock 4-6 day calculation

| Day | Wave | 主要工作 |
|---|---|---|
| D+0 | Wave 0a + 0b + 0c + 0d 並行 + Wave A 並行 | operator OP-1 + OP-2 + OP-3 + OP-4 並行 (~45 min) + PA2/3/4 + CC caveat 修正 + earn_governance 五角色 cross-ref dispatch (~5-12 hr 並行) |
| D+1 | Wave B 並行 5 E1 (Day 1) + earn_governance spec 五角色 verdict 收 (尾) | E1a + E1b 完成;E1c + E1d + E1e Day 1 進度 50% |
| D+2 | Wave B 並行 5 E1 (Day 2) | E1c + E1d + E1e 完成;Wave B 5 E1 全 IMPL DONE 自評 |
| D+3 | Wave C 並行 3 review (E2 + BB + E3) | adversarial review + Bybit verdict + secret slot governance |
| D+4 | Wave D sequential (E1 fix + E4 + QA) | E1 round 2 fix (0-4 hr) → E4 regression → QA Acceptance |
| D+5 | Wave E operator + PM | operator GUI first stake execution + PG verify + PM Phase 3e sign-off |

**Total**：~5 day (D+0 → D+5);D+1 → D+5 = 4 day net wall-clock。

---

## §9 4 operator-bound decisions enumeration

per Sprint 1B brief + earn_governance §10.2 + BB C5 Part F open question 1 + AMD-2026-05-15-01 Stage 1 micro-canary $100：

### 9.1 OP-1 — D+1 OpenClaw API key 發行日 Bybit Web UI query

| 項目 | 規格 |
|---|---|
| **action** | operator 親手 Bybit Web → API management → 既有 read_only key + trading key edit → 看「Last edited」日期 |
| **時長** | 5 min |
| **decision criteria** | (a) ≥ 2026-04-09 → key 自動帶 Earn scope (per BB C5 aotrading 2026 evidence) (b) < 2026-04-09 → operator 重發 key 加 `Earn` permission |
| **若 (b)** | 額外 +30-60 min operator action (重發 key + 三端同步 OpenClaw secret slot + .env config + restart engine + verify Earn endpoint smoke) |
| **block IMPL Wave B?** | YES (E1c bybit_earn_client.rs 12 endpoint IMPL 需有效 Earn scope key 才能 test) |
| **可平行?** | YES (與 Wave A PA spec + earn_governance cross-ref 並行 5 min query) |
| **report** | operator 在 TODO §0 D+1 5 min check carry-over slot 寫 verdict (a) 或 (b) + key 發行日 + 若 (b) 重發 key 完成時間 |

### 9.2 OP-2 — First stake amount $200-400 USDT 拍板

| 項目 | 規格 |
|---|---|
| **action** | operator 拍板 first stake 數額 USDT |
| **時長** | 10 min |
| **decision criteria** | (a) **AMD-2026-05-15-01 Stage 1 micro-canary 對齊** = $100 (保守對齊既有 alpha-bearing promotion 起步額) (b) **Sprint 1B brief 原規格** = $200-400 (per FA §6 §7 + Sprint 1A dispatch packet §1.2) (c) **operator override** = 任意 ≥ $100 ≤ $500 absolute cap |
| **建議** | PA 建議路徑 (a)：對齊 AMD-2026-05-15-01 Stage 1 micro-canary $100；Earn 雖非 trading event 但 first stake 嚴格度 ≥ trading first $500 promotion；first stake $100 保守 + $200 Bybit flexible tier 1 邊界 — 若 OP-3 拍板 flexible → first stake $200 利用 tier 1 ~10% APR |
| **影響** | EarnIntentPayload.amount_usdt 寫入值 + Daily Earn cap risk_config TOML (推薦 cap = 2× first stake 防 cumulative) |
| **block IMPL Wave B?** | NO (IMPL 階段值 = $0 placeholder;Wave E operator 親手執行階段填實值) |
| **可平行?** | YES (與 Wave B IMPL 並行 prep) |

### 9.3 OP-3 — Flexible vs fixed staking 拍板

| 項目 | 規格 |
|---|---|
| **action** | operator 拍板 first stake 產品種類 |
| **時長** | 5 min |
| **decision criteria** | (a) **flexible** (Bybit USDT 30 day flex) — 隨時 redeem (~T+1 settlement) / APR ~10% tier 1 $200 / ~3% remaining (b) **fixed** (90 day / 180 day tenor) — 鎖倉 / APR ~5-8% / 提前贖回 APR loss |
| **建議** | PA 建議路徑 (a) flexible：(1) Sprint 1B W9-12 過短 (~4 week) — fixed 90 day 結算超出 Sprint 1B 範圍 (2) margin headroom < 30% 強制 redeem 路徑 — fixed 鎖倉撞牆 (3) first stake 學習階段 — flexible 操作熟練後 Sprint 2+ 再評 fixed |
| **影響** | E1c bybit_earn_client IMPL 範圍：flexible only → E-2 + E-3 + E-4 + E-5 + E-1 (5 endpoint;~6-9 hr);flexible + fixed → 12 endpoint 全接 (10-15 hr) |
| **block IMPL Wave B?** | PARTIAL (IMPL 階段範圍 = 5 endpoint flexible only OR 全 12 endpoint;若 OP-3 = flexible only → E1c 工時下調 4-6 hr 節省) |
| **可平行?** | YES (與 OP-1 + OP-2 + Wave A 並行) |

### 9.4 OP-4 — earn_governance spec 五角色 cross-ref final sign

| 項目 | 規格 |
|---|---|
| **action** | (1) PM 接 PA verdict (本 packet §6.3) → CC 修 2 caveat → spec → DRAFT-WITH-PA-CAVEATS-RESOLVED (2) FA + E3 + QA + MIT + BB 並行 cross-ref dispatch (~5-12 hr) (3) 5 角色 verdict 收齊 → CC final sign (4) operator 最終 approve |
| **時長** | 5 min operator approve 親手 + 5-12 hr 並行 sub-agent work |
| **decision criteria** | (a) 5/5 ✅ APPROVE → CC sign + operator approve (b) 4/5 ✅ + 1/5 ⚠️ minor caveat → CC sign-with-caveat + operator approve (c) 任 1 ❌ NEEDS-FIX → CC 修 + 再 dispatch (最多 2 輪) |
| **建議** | per earn_governance §12 line 491-493 dispatch SOP；PA 視角 spec 質量高 (PA cross-ref §6.3 已 APPROVE-WITH-2-CAVEATS) → 5 角色預期 4-5 ✅ APPROVE |
| **影響** | spec status DRAFT-FOR-FIVE-ROLE-CROSS-REF → SPEC-FINAL；ADR-0030 promote proposed → accepted；Wave B IMPL dispatch ready |
| **block IMPL Wave B?** | **YES (HARD BLOCK)** — 未 sign 前 Wave B IMPL 不可 dispatch (per earn_governance §10.1 + PA §6.4 risk 紅線) |
| **可平行?** | YES (operator 5 min approve 與 Wave A 並行;5 角色 sub-agent cross-ref 與 Wave A 並行) |

### 9.5 4 OP 決策矩陣 — 阻塞 / 並行 / 時序

| OP | Block Wave B IMPL? | 並行 Wave A? | 預期完成時間 | 對 Wave B IMPL 影響 |
|---|---|---|---|---|
| OP-1 | YES (key scope) | YES (5 min) | D+0 (5 min) 或 D+0.5 (若 (b) 重發 +30-60 min) | E1c bybit_earn_client test 需有效 Earn scope key |
| OP-2 | NO | YES | D+0 (10 min) | EarnIntentPayload.amount_usdt 寫入值;Wave E operator 親手執行階段填實值 |
| OP-3 | PARTIAL (E1c 範圍) | YES | D+0 (5 min) | E1c IMPL 5 endpoint OR 12 endpoint;節省 4-6 hr 若 flexible only |
| OP-4 | **YES (HARD BLOCK)** | YES (cross-ref) | D+0 → D+1 (5-12 hr) | Wave B IMPL dispatch unlock 主要前置 |

**統整**：4 OP 全 D+0 → D+1 內並行完成 (operator ~45 min + 5 sub-agent ~5-12 hr 並行)；Wave B IMPL 最快 D+1 dispatch；最遲 D+1.5 dispatch (若 OP-1 (b) 重發 key)。

---

## §10 PA dispatch readiness verdict

### 10.1 Pending 3.2 Earn first stake overall verdict

**NEEDS-OPERATOR-DECISION-4 + DEPENDS-ON-EARN-GOVERNANCE-FINAL-SIGN**

| 維度 | 狀態 |
|---|---|
| **DESIGN-READY?** | ✅ YES (本 dispatch packet §1-§9 完整) |
| **V100 earn_movement_log schema land?** | ✅ YES (Sprint 4+ §4.1.1 PA-DRIFT-6 patch closure 完成) |
| **IntentType / LeaseScope / Bybit Earn client / EarnMovementWriter / reconciliation cron design?** | ✅ YES (§2 / §3 / §4 / §5 全 spec-ready) |
| **earn_governance spec sign-off?** | ⏳ PENDING (CC self-draft DONE;FA + E3 + QA + MIT + BB cross-ref D+1 PENDING) |
| **operator OP-1 OpenClaw key 發行日 query?** | ⏳ PENDING (carry-over from TODO §0 D+1 5 min) |
| **operator OP-2 first stake amount?** | ⏳ PENDING |
| **operator OP-3 flexible/fixed?** | ⏳ PENDING |
| **operator OP-4 spec final sign?** | ⏳ PENDING (前置 = 5 角色 cross-ref + CC sign) |
| **Wave B IMPL dispatch readiness?** | ⏳ **PENDING 4 OP + earn_governance spec final sign** |

### 10.2 Risk 紀要

| Risk | 嚴重度 | 緩解 |
|---|---|---|
| Wave B IMPL 5 並行 E1 帶寬撞 5+ 並行 mandate ceiling (per dispatch packet §2) | MED | 建議 Wave B 5 E1 + Wave E GUI 8-12 hr (E1a;阻於 H2 Console tab) 可延 W+2 — 4 E1 + 1 GUI 並行 → 安全 |
| E1c bybit_earn_client 12 endpoint IMPL 工時上限 15 hr — 若 OP-3 flexible only 可節省 4-6 hr | LOW | OP-3 拍板 flexible → E1c 6-9 hr 工時下調 |
| OP-1 key 重發路徑 (b) → operator +30-60 min + 三端同步 OpenClaw secret slot | MED | per BB C5 verdict — 不違 Hard Boundaries;運維 SOP per `engineering:devops` skill |
| earn_governance 五角色 cross-ref 衍生 ❌ NEEDS-FIX 致 spec 二輪修正 | MED | per spec §12 line 493 最多 2 輪 dispatch;PA verdict 已預測 4-5/5 ✅ APPROVE |
| 既有 11 個 OrderIntent test fixture 漏補 intent_type default → 編譯 fail | LOW | E1a IMPL must-fix;E2 review grep + cargo test 強制 |
| `governance.lease_transitions` PG CHECK constraint 限 4 scope → EARN_STAKE/EARN_REDEEM 寫入 fail | MED | PA4 Wave A Linux PG empirical audit catch;若需 → V108 ALTER CHECK 同 PR |
| Wave E operator first stake 真實 Bybit API 失敗 (產品撤回 / KYC trigger / 地理限制) | LOW | per BB C5 KYC + 地理已 review;earn_governance §5 fail-closed + Wave D QA Stage 0R replay verify |
| `governance_audit_log.id` soft ref 反查邏輯複雜 (per PA-DRIFT-6 lesson) | LOW | E1d IMPL 對齊 V100 line 502-511 comment + V106/V107/V112 既有範式 |

### 10.3 Dispatch readiness 阻塞鏈

```
operator action chain (~45 min + 5-12 hr 並行 sub-agent)：
├─ OP-1 D+1 OpenClaw key 5 min query (✅/重發 path)
├─ OP-2 first stake $200-400 拍板
├─ OP-3 flexible vs fixed 拍板
└─ OP-4 earn_governance spec final sign (前置 = CC 修 PA caveat + FA/E3/QA/MIT/BB cross-ref 5-12 hr 並行)

↓ 4 OP 全 closed ↓

PA spec polish (Wave A 並行 ~6-9 hr core)：
├─ PA2 V100 writer spec finalize
├─ PA3 reconciliation cron spec finalize
└─ PA4 Linux PG CHECK audit

↓ Wave A 全 PASS ↓

Wave B IMPL dispatch (5 並行 E1 + 1 E1a GUI ~30-45 hr core / 2-3 day wall-clock)

↓ Wave B IMPL DONE ↓

Wave C-E (5-9 hr review + 3-10 hr fix/regression/AC + ~1-2 hr operator+PM)

↓ Pending 3.2 closure ↓
```

### 10.4 PM 建議路徑

**路徑 A (建議)**：先 C10 後 Earn 序列 dispatch (per parent audit §5.2 路徑 A)
- W+0：先 dispatch C10 Stage 1 Demo (Pending 3.1 — READY-TO-DISPATCH 無前置阻塞;~41-62 hr / 並行 3-4 day)
- W+0 並行：operator OP-1 + OP-2 + OP-3 + OP-4 並行 (~45 min) + CC caveat 修正 + FA/E3/QA/MIT/BB cross-ref (~5-12 hr 並行)
- W+1：C10 closure 後 → Wave B IMPL 5 並行 E1 dispatch (~30-45 hr / 2-3 day)
- W+2：Wave C-E 完成 → Pending 3.2 closure

**整體 wall-clock**：~2-3 weeks (per Sprint 1B (full) W9-12 165-220 hr range;含 Sprint 4+ §4.1.1 已 closed)

---

## §11 PA 5 條完成回報

### 11.1 Earn dispatch packet path + LOC

- **Path**: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-23--sprint_1b_earn_first_stake_dispatch_packet.md`
- **LOC**: ~750 line (§0-§11 完整 9 section);中文為主 + 0 emoji
- **狀態**: DESIGN-READY / NEEDS-OPERATOR-DECISION-4 / WAVE-B-IMPL-PENDING

### 11.2 12 Bybit Earn endpoint 清單 + V100 schema 接線設計

- **12 endpoint** (per BB C4 verdict)：5 flexible (E-1/2/3/4/5) + 4 fixed (E-6/7/8/9) + 3 unified query (E-10/11/12);實際分類 7 read-only + 5 write
- **V100 earn_movement_log** schema 已 LAND (10 column / CHECK direction 2 enum + reconciliation_status 3 enum + engine_mode 4 enum / governance_approval_id BIGINT soft ref per PA-DRIFT-6 lesson)
- **Writer 接線**: `srv/rust/openclaw_engine/src/database/earn_movement_writer.rs` 新建 ~250 LOC + INSERT placeholder → Bybit API ack → UPDATE outcome 範式
- **Daily reconciliation cron**: `srv/rust/openclaw_engine/src/cron/earn_reconciliation.rs` 新建 ~150 LOC + UTC 02:00 (改 spec §6.1 UTC 00:30 caveat) + earn_enabled=false 自動 hot-reload hook

### 11.3 IntentType + LeaseScope variant 設計 + earn_governance spec 五角色 cross-ref pending matrix

- **IntentType** 新建 enum 6 variant (OpenLong/Short + CloseLong/Short 預留 + EarnStake/Redeem 新) + OrderIntent struct 擴 `intent_type` + `earn_payload` 2 field (serde rename_all=snake_case + default backward-compat)
- **LeaseScope** 擴 2 variant (EarnStake + EarnRedeem) → requires_operator_authority=true / default_ttl_ms=60s 對齊 CanaryStagePromotion 範式 / as_audit_str="EARN_STAKE"/"EARN_REDEEM"
- **五角色 cross-ref pending matrix**：CC self-draft ✅ DONE;FA + E3 + QA + MIT + BB ⬜ PENDING D+1 (5-12 hr 並行);PA 額外 cross-ref verdict ⚠️ APPROVE-WITH-2-CAVEATS (§3 IntentType 7 variant 範圍 + §6.1 UTC 02:00 改正)

### 11.4 8-step IMPL dispatch chain + 50-78 hr estimate

- **8-step chain**：Wave 0 operator (4 OP ~45 min + cross-ref 5-12 hr 並行) → Wave A PA spec 6-9 hr → Wave B 5 並行 E1 IMPL 30-45 hr / 2-3 day → Wave C E2 + BB + E3 並行 review 5-9 hr → Wave D E1 fix + E4 + QA 3-10 hr → Wave E operator first stake + PM 1-2 hr
- **Total core**: 50-78 hr (含 GUI E1a 8-12 hr) / Wall-clock 4-6 day / Sub-agent peak 5-6 並行
- **Critical path**: OP-4 spec final sign HARD BLOCK Wave B IMPL dispatch

### 11.5 4 operator-bound decisions + dispatch readiness verdict

**4 OP 拍板**:
1. **OP-1** D+1 OpenClaw key 發行日 Bybit Web UI 5 min query (block Wave B IMPL — E1c test 需 Earn scope key)
2. **OP-2** first stake $200-400 拍板 (PA 建議 $100-200 對齊 AMD-2026-05-15-01 Stage 1 micro-canary + Bybit flexible tier 1)
3. **OP-3** flexible (30 day flex) vs fixed (90/180 day) 拍板 (PA 建議 flexible — Sprint 1B 過短 + fixed 鎖倉撞牆)
4. **OP-4** earn_governance spec 五角色 cross-ref final sign (PA verdict ⚠️ APPROVE-WITH-2-CAVEATS;CC 修 2 caveat + 5 角色 cross-ref 5-12 hr → HARD BLOCK Wave B IMPL)

**dispatch readiness verdict**:
- **DESIGN**: ✅ READY (§1-§9 完整 spec)
- **V100 schema**: ✅ LAND (Sprint 4+ §4.1.1 PA-DRIFT-6 closure 完成)
- **operator decisions**: ⏳ 0/4 closed (4 OP all PENDING)
- **earn_governance final sign**: ⏳ PENDING (CC self-draft DONE / 5 角色 cross-ref PENDING)
- **Wave B IMPL dispatch**: ⏳ **NEEDS-OPERATOR-DECISION-4-CLOSED + EARN-GOVERNANCE-SPEC-FINAL-SIGN** — 預期 D+1 4 OP closed + spec final sign 後 dispatch ready

---

**END OF PA Sprint 1B Pending 3.2 Earn first stake dispatch packet**
