---
spec: M13 Multi-Asset Class / Multi-Venue Capacity — Module DESIGN Specification (Interface Stub Level)
date: 2026-05-21
author: PA architecture draft for Sprint 1A-δ interface-stub deliverable
phase: v5.8 Sprint 1A-δ（W5.5-6.5 PM 整合 calendar；ADR-0040 + V116 placeholder 同 Sprint 派發）
status: SPEC-DRAFT-V0（interface stub level only；不寫 IMPL code；不寫 V116 full DDL；Y3+ first quarter activation 走新 amendment ADR）
parent specs:
  - srv/docs/adr/0040-multi-venue-gate-spec.md（治理邊界 — 不可違背；Y3+ at earliest defer + 6 trade gate criteria + venue enum hardcode + DEX/Hyperliquid 拒絕）
  - srv/docs/adr/0033-adr-0006-bybit-binance-amendment.md（Binance market-data Y1 + Y2 不變；本 spec interface 預留涵蓋 market-data + Y3+ trade slot）
  - srv/docs/adr/0006-bybit-only-exchange.md（baseline 不變；本 spec interface 不違反 Bybit-only Y1+Y2 current state）
  - srv/docs/adr/0035-m5-online-learning-interface-reserved.md（同 Sprint 1A-δ deliverable + 同 interface-reservation pattern；trait stub default panic + V### reserved migration + retirement criteria）
  - srv/docs/adr/0039-m12-order-router-trait-and-maker-fill-rate-metric.md（同 Sprint 1A-δ deliverable + 同 interface-reservation pattern；M12 venue routing 與本 spec AssetClass+Venue enum 共享 SymbolKey）
  - srv/docs/adr/0034-m1-decision-lease-lal.md（venue change 永遠走 LAL 4 always operator approve；本 spec Decision 5 對齊）
  - srv/docs/execution_plan/2026-05-20--execution-plan-v5.8.md §2 M13 (lines 460-487) + §5 capital-tier ladder (lines 644-665) + §9 V116 reserved (line 799) + §10 Risk #2 retirement criteria
  - srv/docs/execution_plan/2026-05-21--v103_v104_earn_hypotheses_schema_spec.md（範式參考 — frontmatter 結構 + Schema Outline + Hypertable 判斷 + Linux PG dry-run checklist）
  - srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-21--v58_dispatch_consolidation.md §Sprint 1A-δ 行 163
mirror precedent:
  - srv/docs/adr/0035-m5-online-learning-interface-reserved.md（M5 trait stub + V114 placeholder 治理紀律完全對等；本 spec 為 M13 對應 module DESIGN spec）
  - srv/docs/execution_plan/2026-05-21--m11_continuous_counterfactual_replay_design_spec.md（module DESIGN spec 範式）
scope: module 行為設計 + 整合接口 + AssetClass + Venue enum + 6 trade gate criteria + IMPL phasing；不寫 IMPL code；不寫 V116 full DDL；不違背 ADR-0040 Y3+ defer；不違背 ADR-0006 Bybit-only baseline
---
> ⚠️ 归档历史文档 — 非当前权威。active 状态见 repo 根 `TODO.md`；本文件仅供历史/审计参考。（2026-07-18 审计批量补入）


# M13 Multi-Asset Class / Multi-Venue Capacity — Module DESIGN Specification

## §0 TL;DR

本 spec 鎖定 M13 module 的 **interface stub 級行為設計** — AssetClass enum + Venue enum + cross-module integration placeholder + Y3+ trade enable 6 gate criteria + retirement criteria + IMPL phase split，作為 Sprint 1A-δ 三 interface-stub deliverable（M5/M12/M13）之一。

**治理邊界** 由 ADR-0040 鎖定（Y3+ at earliest defer / 6 trade gate criteria / per-venue 5-gate schema / venue enum hardcode + DEX/Hyperliquid 拒絕 / per-venue authorization 三元組綁定），本 spec 不重述只 cross-ref。**Schema DDL** 由 V116 placeholder spec doc 處理（V116 是 reserved frontmatter only，Sprint 1A-δ 不寫 full DDL）。

3 件關鍵設計選擇：

1. **AssetClass + Venue enum hardcode**（compile-time fail-closed）— DEX / Hyperliquid 不在 enum slot，編譯期即拒絕；string literal venue ID 編譯期拒絕；Y1+Y2 only `BybitPerp` / `BybitSpot` / `BybitOption` / `BinancePerpMarketData` 4 variant 真實 active；`BinancePerpTrade` slot 預留但 panic Y1-Y2
2. **6 trade gate criteria**（per ADR-0040 §Decision 3）— Y3+ first quarter (W105-W117) evaluation 走 6 條 AND gate；任一 FAIL → 繼續 defer；3 cycle FAIL → 開新 ADR 永久關閉 Binance trading optionality
3. **Cross-module integration 預留**（M1 LAL Tier 4 / M12 OrderRouter / M11 replay）— venue change 永遠走 LAL 4 (per ADR-0034) operator approve mandatory；M12 OrderRouter 路徑跨 venue 走同一 trait（venue 維度 routing）；M11 replay 對 multi-venue divergence 預留 venue field 但 Y1+Y2 single venue 不啟用

---

## §1 Context — 為什麼 M13 Multi-Asset Class / Multi-Venue Capacity

### §1.1 13 module 圖中 M13 定位

v5.8 §2 M13（lines 460-487）將 M13 列為 13 module 之一，且 operator 2026-05-21 D1 directive 「even if delayed should do; capital may scale」明示 M13 必加入 Sprint 1A interface reservation roadmap，雖 IMPL deferred Y2-Y3 phased。

per ADR-0040 + operator D4 2026-05-21，Y2 Binance trade enable 已 defer 至 **Y3+ first quarter (~Y2 末 W104+) evaluation**；Y1+Y2 期間 Binance 維持 **market-data only**（per ADR-0033 §Decision 1 不變）。本 spec interface stub 涵蓋：
- Y1 baseline (Bybit perp + Bybit spot Earn + Bybit options C13)
- Y1+Y2 market-data extension (Binance market data primary)
- Y3+ trade slot reservation (Binance perp trade)
- 永久拒絕 (DEX / Hyperliquid hardcode rejection)

### §1.2 為什麼 trait + enum 必須 Sprint 1A-δ DESIGN land

per PA dispatch packet（行 163）+ ADR-0035/0039/0040 同 Sprint 派發紀律：

- M5 ModelClient trait stub（per ADR-0035）
- M12 OrderRouter trait stub + maker_fill_rate_30d metric（per ADR-0039）
- **M13 AssetClass + Venue enum + cross-module integration interface（本 spec）**

三者共享同一個治理 pattern：**interface 預留 + V### reserved migration placeholder + 6-condition gate + retirement criteria 明示**。三者同 Sprint 派發、同 dispatch 紀律。

Sprint 1A-δ 不寫 IMPL，但 enum + trait skeleton 必 land；後續 Sprint 2+ 任何 venue-related 寫入路徑（M12 OrderRouter / market-data ingest path / Earn governance / replay engine）皆需引用本 spec 的 AssetClass + Venue enum 為唯一 authoritative type；無此 spec → sub-agent dispatch 時可能誤用 string literal venue ID（ADR-0040 §Decision 4 反模式）。

### §1.3 為什麼 M13 屬 Sprint 1A-δ（不在 Sprint 1A-β / γ）

Sprint 1A-β 五個 CRITICAL module 共同特徵：Sprint 3-5 早期 IMPL 階段的接線依賴。M13 不屬此類——Y1+Y2 期間實質運作的只有 Bybit-only baseline + Binance market-data ingest（Sprint 4+），Y3+ 才可能 trade enable；故 M13 interface stub 屬 Sprint 1A-δ delayed-IMPL module 集合，與 M5 / M12 同期 reservation。

---

## §2 AssetClass Enum 設計

### §2.1 Hardcode 4 variant

```rust
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum AssetClass {
    Perpetual,    // Sprint 4 first Live 範圍；唯一 Y1 active trading 對象
    Spot,         // Earn 用（per ADR-0030 + ADR-0032）；Sprint 1B Earn governance land
    Option,       // C13 VRP 策略；Sprint 6+ 啟用（per v5.8 §2 M2 line + Sprint roster）
    Future,       // 預留 Y3+；目前無 active 規劃；retirement R1 評估
}
```

| Variant | Y1 行為 | Y2 行為 | Y3+ 行為 | 引用 |
|---|---|---|---|---|
| `Perpetual` | Sprint 4 first Live 唯一 active | continued primary | continued primary + Binance perp slot Y3+ activation | per ADR-0006 baseline + v5.8 §2 M13 line 467 |
| `Spot` | Sprint 1B Earn 用 (per ADR-0032 Earn asset movement Guardian) | Earn scaling per AUM | Earn scaling per AUM | per v5.8 §2 line 467 "Bybit spot (Earn)" |
| `Option` | not active | not active (defer per v5.8 §2 line 468 "Y2-Y3: + structured products") | C13 VRP Sprint 6+ active；Bybit options first；Binance options 待 Y3+ AUM > $150k (per v5.8 §5 line 656 "Full M13 multi-asset") | per v5.8 §2 line 467 "Bybit options (C13 VRP)" |
| `Future` | not active | not active | not active；retirement R1 audit 評估是否 dead code | 預留 slot；無 active 規劃 |

### §2.2 設計理由

| Aspect | 設計 | 理由 |
|---|---|---|
| Enum 而非 String literal | hardcode 4 variant | per ADR-0040 §Decision 4 strict 立場；string literal 易繞編譯期 check；enum 強制 caller 明示 AssetClass |
| `Future` 預留 slot | enum variant + retirement R1 evaluation | 對等 M5 / M12 dead-code retirement audit cadence；Y3 末未 active → 開新 ADR 移除 variant |
| 不分 `BybitPerp` / `BinancePerp` AssetClass | venue 維度走 `Venue` enum，AssetClass 與 venue 正交 | AssetClass 描述「資產類型」（perp/spot/option/future）；Venue 描述「交易場所」（Bybit/Binance）；正交設計利於 cross-venue position aggregator（per v5.8 §2 line 476-477）|
| 不含 `Earn` 為獨立 AssetClass | Earn 走 `Spot` AssetClass + Earn-specific governance (per ADR-0030 / 0032) | Earn 本質是 Spot 倉位 + lending overlay；獨立 AssetClass 會引發 Earn vs Spot 雙寫風險；per Earn governance spec design land |
| 不含 `Structured` 為獨立 AssetClass | v5.8 §2 line 469 "structured products" 走 `Spot` + governance overlay | 同 Earn 理由 |

### §2.3 Y1+Y2 active scope

Y1+Y2 期間 active trading 只 `Perpetual` + `Spot`（後者 Earn 用）；`Option` Sprint 6+ enable，`Future` 永遠 not active 直 retirement R1 evaluation。

Sprint 1A-δ 不寫 `Option` / `Future` 任何 IMPL；trait method 對 `Option` / `Future` AssetClass 預設 `unimplemented!()` panic（fail-loud；對等 M5 trait 紀律）。

---

## §3 Venue Enum 設計

### §3.1 Hardcode 4 variant + DEX/Hyperliquid 拒絕

```rust
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum Venue {
    Bybit,                     // 唯一 trade venue baseline；Earn 走 Bybit Earn
    BinanceMarketDataOnly,     // Y1+Y2 active；per ADR-0033 §Decision 1
    BinanceTrade,              // DEFERRED Y3+ at earliest；per ADR-0040 §Decision 1
    // DEX / Hyperliquid hardcode rejection (compile-time error;
    // no enum slot reserved; per ADR-0040 §Decision 4 + ADR-0033 §Decision 3)
}
```

| Variant | Y1 行為 | Y2 行為 | Y3+ 行為 | 引用 |
|---|---|---|---|---|
| `Bybit` | active trading (perp + spot Earn) | active trading + options C13 (Sprint 6+) | active trading + Binance Y3+ activation 後 cross-venue | per ADR-0006 baseline + v5.8 §2 M13 |
| `BinanceMarketDataOnly` | Sprint 4+ market-data ingest active；trading 全禁 | continued market-data ingest；trading 全禁 | continued market-data；Y3+ activation 路徑通過 6-gate 後切換為 `BinanceTrade` | per ADR-0033 §Decision 1 + ADR-0040 §Decision 1 |
| `BinanceTrade` | **panic on use**（trait method `default unimplemented!()`）| **panic on use** | Y3+ first quarter (W105-W117) evaluation 走 6 gate；PASS → 開新 ADR + 移除 `unimplemented!()`；FAIL → continue defer | per ADR-0040 §Decision 1 + §Decision 3 |

### §3.2 DEX / Hyperliquid Hardcode Rejection 機制

per ADR-0040 §Decision 4：DEX / Hyperliquid **不在 enum 中保留 slot**，編譯期即拒絕。

實現方式 3 層：

**Layer 1 — Enum 不存在 variant**
```rust
// CORRECT (compile-time error on bad input):
let v = Venue::DEX;          // compile error: no variant named `DEX`
let v = Venue::Hyperliquid;  // compile error: no variant named `Hyperliquid`
```

**Layer 2 — `FromStr` / `Deserialize` 不接受 DEX / Hyperliquid string**
```rust
impl FromStr for Venue {
    type Err = VenueParseError;
    fn from_str(s: &str) -> Result<Self, Self::Err> {
        match s {
            "bybit" => Ok(Venue::Bybit),
            "binance_market_data_only" => Ok(Venue::BinanceMarketDataOnly),
            "binance_trade" => Ok(Venue::BinanceTrade),  // 仍可 parse 但 Y1+Y2 trait method panic
            "dex" | "hyperliquid" | "uniswap" | "gmx" | "dydx" | _ => {
                Err(VenueParseError::RejectedVenue(s.to_string()))
            }
        }
    }
}
```

**Layer 3 — sibling test 驗 DEX / Hyperliquid parse 必 RAISE**
```rust
#[test]
fn test_venue_hardcode_rejects_dex_hyperliquid() {
    for rejected in ["dex", "hyperliquid", "uniswap", "gmx", "dydx", "DEX",
                     "Hyperliquid", "DYDX", "perp-dex", "evm-perp"] {
        assert!(matches!(
            Venue::from_str(rejected),
            Err(VenueParseError::RejectedVenue(_))
        ), "Venue::from_str must reject {} per ADR-0040 §Decision 4", rejected);
    }
}

#[test]
fn test_venue_binance_trade_panics_y1_y2() {
    // Y1+Y2 任何 trait method 對 BinanceTrade variant 必 panic（fail-loud）
    let v = Venue::BinanceTrade;
    assert!(std::panic::catch_unwind(|| v.submit_order_via_trait(...)).is_err(),
            "Y1+Y2 BinanceTrade trait method must panic per ADR-0040 §Decision 1 stub-only 紀律");
}
```

### §3.3 反模式（明示禁止）

per ADR-0040 §Decision 4 紀律 + 對等 ADR-0035 trait stub 反模式：

- (a) Y1+Y2 任何 module 真實呼叫 `BinanceTrade` trait method（submit order / cancel / query position）：違反 stub-only 紀律，trait fail-loud 設計就是要 panic
- (b) Sprint 1A-δ 把 `BinanceTrade` 任一 trait method 改為 default no-op 或 mocked Bybit fallback：違反 fail-closed 紀律，後續 caller 誤以為 stub 已 IMPL
- (c) 任何 IMPL **不可繞 enum 走 string literal venue ID**（per ADR-0040 §Decision 4）；應用層必 `match venue: Venue` exhaustive check，編譯期強制
- (d) `FromStr` impl 接受 DEX / Hyperliquid string variant：違反 ADR-0033 §Decision 3 proactive lock-down 紀律 + ADR-0040 §Decision 4 hardcode rejection
- (e) 未來引入 OKX / Coinbase 不開新 ADR 直接加 enum variant：違反 ADR-0040 §Decision 4 「未來開放新 venue 必須開新 ADR」紀律

---

## §4 6 Trade Gate Criteria（per ADR-0040 §Decision 3）

per ADR-0040 §Decision 3，Y3+ first quarter (W105-W117) Binance trade enable evaluation 走 6 條 AND gate；任一 FAIL → 繼續 defer。本 spec 不重述條件細節（ADR-0040 已 land），只 enumerate 並對齊 evaluation 落地路徑。

| # | Criterion | ADR-0040 §Decision 3 對應 | 評估 owner | 證據來源 |
|---|---|---|---|---|
| (a) | Y1 + Y2 Bybit self-trading alpha 已驗證（Sharpe ≥ X for 12-18 months sustained） | 行 95 | MIT + QC | live PnL + Sharpe rolling window；per ADR-0030 Gate 1 Alpha 延伸 |
| (b) | Y1 + Y2 Binance market data analysis 顯示 cross-venue arbitrage 真有 +1%+ alpha vs Bybit-only baseline | 行 96 | MIT | counterfactual replay using Binance market data 兩年累積樣本 |
| (c) | Operator 仲裁（new 5-gate review session） | 行 97 | Operator + PA | per Decision 5 venue-aware authorization.json 簽署需 Operator session |
| (d) | BB confirmed Binance ToS / KYC 持續可行 | 行 98 | BB | Bybit + Binance KYC + ToS cross-venue 持續性 audit 報告 |
| (e) | Y2 末 Copy Trading evidence land | 行 99（本 ADR 新增）| MIT + FA | per ADR-0030 Copy Trading evidence-gated；Y2 末 Copy Trading 必 4-Gate evaluation PASS 並 land 為 active income stream |
| (f) | AUM ≥ $50k sustained 30d | 行 100（本 ADR 新增）| FA + Operator | per v5.8 §5 capital-tier ladder Y3 Q2 estimate $75-150k；$50k 是 Binance trade enable capital efficiency 門檻 |

**6 條 AND 邏輯**：6 條全 PASS → 開新 ADR amend ADR-0040 §Decision 1 + V116 full DDL Sprint land；任一 FAIL → 維持 `BinanceTrade` panic stub 狀態，繼續 defer 至下一 evaluation cycle。

**永久放棄條件**：連續 3 個 evaluation cycle (~12-18 months) fail → 開新 ADR 永久關閉 Binance trading optionality + `BinanceTrade` enum variant retirement R1 走 dead-code removal（per ADR-0033 §Decision 2 永久放棄路徑 + 對等 ADR-0035 retirement R1 紀律）。

---

## §5 Cross-Module Integration Placeholder

### §5.1 M1 LAL（Layered Approval Lease）整合

per ADR-0034 LAL 4 capital structure + ADR-0040 §Decision 5：**venue change 永遠走 LAL 4**（always operator approve mandatory）；Agent 無法自主提案 venue enable / disable。

對應 trait method placeholder：

```rust
pub trait VenueGovernance {
    /// Y1+Y2 BinanceTrade 走此 method 必 panic（venue change 屬 LAL 4）
    /// Y3+ activation 後此 method 必檢查 LAL 4 operator approval
    fn propose_venue_enable(
        venue: Venue,
        operator_approval: LAL4Approval,
    ) -> Result<VenueEnableLease, VenueGovernanceError>;

    /// 6 gate criteria evaluation entry point；Y3+ first quarter 啟動
    fn evaluate_venue_trade_enable_gate(
        venue: Venue,
        gate_evidence: SixGateEvidence,
    ) -> GateEvaluationResult;
}
```

Sprint 1A-δ trait skeleton only；method body `unimplemented!()` panic；Sprint Y3+ first quarter activation 走 6 gate evaluation 真實 IMPL。

### §5.2 M12 OrderRouter（per ADR-0039）整合

per ADR-0039 M12 OrderRouter trait 含 `route_order(symbol, venue)` 路徑；本 spec AssetClass + Venue enum 為其 venue 維度 input type 的 authoritative source。

```rust
pub trait OrderRouter {
    /// 跨 venue 路徑；Y1+Y2 venue 參數只能是 Bybit；Y3+ activation 後可含 BinanceTrade
    fn route_order(
        order: Order,
        symbol_key: SymbolKey,  // 含 AssetClass + Venue
        target_venue: Venue,
    ) -> Result<RoutedOrder, RouterError>;
}

// SymbolKey 是跨 venue position aggregator 的 join key
pub struct SymbolKey {
    pub asset_class: AssetClass,
    pub venue: Venue,
    pub symbol: String,  // e.g. "BTCUSDT" Bybit perp vs "BTCUSDT" Binance perp 是不同 SymbolKey
}
```

Sprint 1A-δ M12 OrderRouter trait stub + 本 spec AssetClass+Venue enum 同 Sprint land；M12 trait method 對 `BinanceTrade` venue 必 panic（與 §3.3 反模式 (a) 對齊）。

### §5.3 M11 Continuous Counterfactual Replay 整合

per ADR-0038 + M11 design spec §2，M11 replay engine 比對 live execution vs replay decision；multi-venue Y3+ activation 後須引入 venue 維度 divergence。

V107 schema（M11 replay_divergence_log）column 預留：

```sql
-- V107 既有 column（per M11 design spec）
divergence_id BIGSERIAL PRIMARY KEY,
trace_id TEXT NOT NULL,
strategy_name TEXT NOT NULL,
divergence_type TEXT NOT NULL,  -- fill_chain / position / pnl / fee / liquidation / regime / risk
divergence_severity TEXT NOT NULL,  -- NOISE / WARN / CRITICAL

-- M13 integration（Y3+ activation 時 V107 ALTER ADD COLUMN，本 spec 不寫 DDL）
venue TEXT NOT NULL DEFAULT 'bybit',  -- Y1+Y2 全 'bybit'；Y3+ 後可含 binance_trade
cross_venue_divergence_flag BOOLEAN NOT NULL DEFAULT FALSE,  -- 跨 venue 套利 divergence 標記
```

Sprint 1A-δ M13 spec land 時 V107 column 不變（V107 column DEFAULT 'bybit' 已 backward-compat）；Y3+ activation 時走新 V### ALTER 加 venue field（per ADR-0040 §Decision 2 venue-aware authorization 對齊）。

---

## §6 Acceptance Criteria

Sprint 1A-δ M13 interface stub deliverable 結案標準 6 條（含 sibling test）：

1. **AssetClass enum 4 variant hardcode**（`Perpetual` / `Spot` / `Option` / `Future`）+ sibling test 驗 string literal AssetClass parse 必 RAISE（compile-time error 不可 build）
2. **Venue enum 4 variant hardcode**（`Bybit` / `BinanceMarketDataOnly` / `BinanceTrade` + DEX/Hyperliquid 不在 slot）+ sibling test 驗 DEX/Hyperliquid `FromStr` 必 RAISE 10 種 string variant（per §3.2 Layer 3 test）
3. **`BinanceTrade` trait method Y1+Y2 全 panic**：sibling test 驗 5 種 trait method（submit_order / cancel_order / query_position / query_balance / propose_venue_enable）對 `BinanceTrade` venue 必 panic `unimplemented!()`（per ADR-0035 反模式 (a) 對等紀律）
4. **6 trade gate criteria documented**：ADR-0040 §Decision 3 6 條 cross-ref + 本 spec §4 enumerate + evaluation owner + 證據來源；Y3+ first quarter activation 時 PA 可直接 dispatch evaluation 不再現場補設計
5. **Cross-module integration trait skeleton land**：M1 LAL `propose_venue_enable` / `evaluate_venue_trade_enable_gate` + M12 OrderRouter `route_order(target_venue)` + M11 V107 venue field 預留路徑（V107 column DEFAULT 'bybit' backward-compat；不寫 V### ALTER）
6. **Retirement criteria 明示**（per ADR-0040 §Consequences negative #2 + ADR-0035 R1-R4 對等）：Y3 末 evaluation 失敗 3 cycle → 開新 ADR 永久關閉 + `BinanceTrade` enum variant + V116 placeholder + cross-module placeholder code 全 dead-code removal；retirement audit cadence Sprint 10 + Y2 Q4 + Y3 Q2 三輪（per ADR-0035 audit cadence 對齊）

**反 acceptance（明示禁止）**：

- (a) Sprint 1A-δ 真寫 `BinanceTrade` 任一 trait method 的 IMPL body（即使是 Bybit fallback）：違反 §3.3 反模式 (b)
- (b) Sprint 1A-δ 真寫 V116 full DDL：違反 §0 TL;DR + 對等 ADR-0035 V114 placeholder 紀律 + sqlx checksum drift 風險（per memory `project_2026_05_02_p0_sqlx_hash_drift`）
- (c) AssetClass / Venue enum 任一 variant 缺 sibling panic test：違反 trait stub fail-loud 紀律

---

## §7 IMPL Phase Split

per ADR-0040 §Decision 1 + v5.8 §2 M13 line 479-483 IMPL engineering scope 對齊。

**§7.1 Sprint 1A-δ — Interface Enum + Trait Stub Only**（~30-40 hr per v5.8 §3 line 511）：AssetClass + Venue enum land (3-5 + 5-7 hr) + sibling panic test × 10 case (5-8 hr) + M1 LAL trait skeleton (3-5 hr) + M12 OrderRouter `route_order(target_venue)` integration (3-5 hr) + M11 V107 venue field 預留路徑文件化（不寫 DDL；2-3 hr）+ V116 reserved frontmatter only spec doc（同 Sprint 派發；3-5 hr）+ ADR-0040 cross-ref + 本 spec PM sign-off review (3-5 hr)。

**§7.2 Y1 末 — Multi-Venue Spec（when do we add Binance trade authority）**（per v5.8 §2 M13 line 481；50-70 hr）：Y1 末 (~Sprint 10 W36-39) prep window；MIT + FA + PA 三方評估 Y1 evidence + Binance trade authority 接入路徑（per ADR-0040 §Decision 5）+ Stage 0R replay using Binance market data 範本準備。Y1 末 spec 不啟動 Y2 trade enable（per ADR-0040 §Decision 1 amend Y2 → Y3+）；是 Y3+ evaluation prep document。

**§7.3 Y3+ First Quarter — Venue Activation Evaluation + IMPL**（per ADR-0040 §Decision 1 + §Decision 3）：

- **Phase 1 (~W104-W117, Y3 Q1)** — 6 gate evaluation：(a)(b) MIT Bybit alpha + counterfactual replay；(c) Operator 5-gate review；(d) BB ToS/KYC；(e) Copy Trading 4-Gate；(f) FA AUM ≥ $50k sustained 30d。6 條全 PASS → Phase 2；任一 FAIL → continue defer
- **Phase 2 (~Y3 Q2-Q3 if Phase 1 PASS)** — Binance trade enable IMPL：開新 ADR amend ADR-0040 §Decision 1 + V116 full DDL Sprint land + `BinanceTrade` trait method IMPL replace `unimplemented!()` + Stage 0R replay using Binance market data → Stage 1 Demo micro-canary on Binance（per AMD-2026-05-15-01）；200-300 hr per v5.8 §2 M13 line 482
- **Phase 3 (Y3+ Q4+ if Phase 2 stable)** — Additional asset classes per AUM：Bybit options C13 VRP（Sprint 6+ roster）；250-400 hr cumulative per v5.8 §2 M13 line 486；per v5.8 §5 line 656「> $150k (Y4+): Full M13 multi-asset」

**§7.4 Retirement Phase**（per ADR-0035 R1-R4 對等 + ADR-0040 §Consequences negative #2）：

- **R1**：Y3 末 6 gate evaluation 連續 3 cycle FAIL (~W156) → 開新 ADR Supersede ADR-0040 + 永久關閉 Binance trading optionality + `BinanceTrade` enum variant + cross-module placeholder 全 dead-code removal PR
- **R2**：M13 範疇被其他 module 吸收（不太可能；M13 是 venue/AssetClass 治理基礎）→ 開新 ADR Supersede
- **R3**：Operator 永久放棄 multi-venue 路徑（Live 12 month 顯示 Bybit-only 足夠）→ 開新 ADR Supersede + ADR-debt closure
- **R4**：替代技術出現（Bybit cross-venue ledger 整合 / Binance ToS 禁止 algorithmic from third-party API）→ 開新 ADR amend

**Audit cadence**（per ADR-0035 對齊）：Sprint 10 Y1 Review + Y2 Q4 + Y3 Q2 三輪。Audit 結果寫 `learning.adr_retirement_audit` table（per ADR-0034 audit pattern + ADR-0035 §Decision 4 對等延伸）。

---

## §8 Cross-V### Dependency Placeholder + Open Questions

### §8.1 Cross-V### dependency

| V### | 涉及 | 本 spec 引用 | Sprint |
|---|---|---|---|
| V107 (M11 replay_divergence_log) | venue field 預留路徑 | §5.3；Sprint 1A-δ M13 不寫 V107 ALTER；Y3+ activation 時走新 V### |
| V112 (M1 decision_lease_lal_tiers) | LAL 4 venue change tier alignment | §5.1；Sprint 1A-β 已 land V112 spec；本 spec 引用 LAL 4 tier 為 venue change 治理層 |
| V116 (M13 reserved frontmatter) | 本 spec 對應 reserved migration placeholder | §0 + §7.1；Sprint 1A-δ V116 reserve frontmatter only；不寫 full DDL |
| V### Y3+ activation 後 ALTER | per ADR-0040 §Decision 2 per-venue 5-gate schema 落地 | §7.3 Phase 2；不在本 spec 範圍；Y3+ activation 時開新 V### |

### §8.2 Open Questions（≥3 條，待 Y1 末 spec 補 / Y3+ activation 仲裁）

1. **Y3+ first venue 是否確定 Binance（vs OKX / Coinbase 等）？**
   - 本 spec + ADR-0040 §Decision 1 假設 Y3+ first quarter evaluation 對象是 Binance（per v5.8 §2 M13 line 468 「Binance perp」+ ADR-0033 §Decision 2 既有路徑）
   - 但 Y2 末 evidence base 可能顯示 Binance 不是最佳 second venue（如 OKX KYC 友好 / Coinbase US 對 stablecoin spot 流動性更高）
   - **仲裁 owner**：Y3 Q1 evaluation 啟動前 PM + FA + BB 三方審視 second venue 選擇；若 Y2 末 evidence 強烈建議 OKX → 開新 ADR amend ADR-0040 §Decision 1 venue 對象
   - **Sprint 1A-δ 本 spec 不鎖定**：enum 4 variant 已預留 `BinanceMarketDataOnly` + `BinanceTrade`；若 Y3+ second venue 改 OKX，需開新 ADR 加 enum variant（per §3.3 反模式 (e)）+ 走 6 gate 重評；不可在沒有新 ADR 的情況下 hot-patch

2. **6 gate criteria 細化 (a) Sharpe X 數值與 (b) +1% alpha threshold 數值？**
   - ADR-0040 §Decision 3 (a) 「Sharpe ≥ X for 12-18 months sustained」未鎖定 X 數值
   - ADR-0040 §Decision 3 (b) 「cross-venue arbitrage 真有 +1%+ alpha」未鎖定 alpha attribution methodology
   - **仲裁 owner**：Y3 Q1 evaluation 啟動前 MIT + QC + PA 三方仲裁 X 數值 + alpha attribution methodology；evidence-based amendment 路徑符合 §二 原則 12（per ADR-0035 §Decision 3 (f) Sharpe threshold 未鎖定的對等紀律）
   - **Sprint 1A-δ 本 spec 不鎖定**：本 spec §4 表 enumerate 6 條 criterion 但不鎖數值；Y3+ activation 真接近時 PM 仲裁

3. **AssetClass `Option` 啟用時點是 Sprint 6（per v5.8 §2 C13 roster）vs Y2 末（per v5.8 §2 line 469「structured products」延後）？**
   - v5.8 §2 line 467 列「Bybit options (C13 VRP)」為 Y1 baseline 一部分；但 v5.8 §2 line 469 「Y2-Y3: + structured products」暗示 options 真實啟用可能延後
   - C13 VRP 策略 Sprint 6+ roster vs Y2 末 structured products 啟用窗口存在 ~6 month gap
   - **仲裁 owner**：Sprint 5-6 啟動前 PM + PA + MIT 三方審視 Bybit options + C13 VRP readiness；若 C13 alpha hypothesis Y1 末 evidence 不足 → defer Option AssetClass 啟用至 Y2 末
   - **Sprint 1A-δ 本 spec 不鎖定**：enum 4 variant `Option` 已預留；trait method 對 `Option` AssetClass 預設 `unimplemented!()`（per §2.3）；具體啟用走 Sprint 5-6 prep；不需開新 ADR（因 enum 已預留 + 啟用屬 IMPL 路徑非治理路徑）

### §8.3 額外 caveat（已知非阻塞）

1. **`Future` AssetClass 永遠 not active 風險**：Y3 末 retirement R1 audit 評估若 `Future` 仍無 active 規劃 → 開新 ADR 移除 variant；mitigation = audit cadence Sprint 10 + Y2 Q4 + Y3 Q2 三輪
2. **DEX / Hyperliquid hardcode rejection 維護負擔**：未來若 Bybit 收購 DEX / 推出原生 DEX product → 「DEX」名詞語義改變；mitigation = ADR-0040 §Decision 4 「未來開放新 venue 必須開新 ADR」紀律不受名詞影響，新 venue 走 enum variant 加入路徑
3. **跨 venue position aggregator 在 Sprint 1A-δ 不寫**：per v5.8 §2 M13 line 476「Cross-venue position aggregator (existing PositionAggregator extends)」；Y3+ activation 時 PositionAggregator 才真實接 venue 維度；Sprint 1A-δ 只預留 SymbolKey (AssetClass + Venue + symbol) 為 join key type
4. **per-venue secret slot 額外管理負擔 Y3+**：per ADR-0040 §Consequences negative；H-21 external secret slot policy 已設計分層；運維負擔在 Y3+ 才出現
5. **venue-aware authorization.json `venue` field schema 變更 Y3+**：per ADR-0040 §Decision 2 Gate 5 venue-aware；Y1+Y2 authorization.json 維持 backward-compat（無 venue field → 默認 'bybit'）；Y3+ activation 真寫 venue field schema patch 不在本 spec 範圍

---

## §9 風險評估 + 16 原則 / DOC-08 §12 / §四 觸碰

**§9.1 改動風險評級 = 低**（interface stub level only）：5 主要 Risk + Mitigation：(a) AssetClass/Venue enum 漂移為 dead code → retirement R1 audit cadence；(b) string literal venue ID 繞編譯期 check → §3.3 反模式 (c) + §3.2 Layer 3 sibling test；(c) `BinanceTrade` trait method 誤呼導致 Y1+Y2 panic → fail-loud by design + sibling panic test；(d) Y3+ activation 後 V107 schema 變更 risk → Y3+ 走新 V### ALTER + 本 spec 預留 backward-compat（V107 column DEFAULT 'bybit'）；(e) Sprint 1A-δ 真寫 V116 full DDL 觸 sqlx checksum drift → §0 + §6 反 acceptance (b) 明示 + V116 placeholder spec doc 限定 frontmatter 結構。

**§9.2 16 根原則合規（16/16）** — per ADR-0040 §16 對等繼承（已逐條 PASS）：原則 1 單一寫入口 per venue / 2 讀寫分離 / 3 AI→Lease→複核 / 4 策略不繞風控 / 5 生存 > 利潤（Y3+ at earliest = 更保守時點）/ 6 失敗默認收縮（6 條件 AND + 3 cycle fail 永久關閉 + trait default panic）/ 7 學習 ≠ Live / 8 交易可解釋（per-venue authorization 三元組綁定強化 lineage）/ 9 雙重防線（per-venue 5-gate + 6 條 evaluation gate + LAL 4）/ 10 分離事實 / 推論（§8.2 三 open Q 明示）/ 11 P0/P1 內自主（venue change 走 LAL 4）/ 12 持續進化（6 條 evidence-based）/ 13 AI cost 感知（interface stub level 不涉）/ 14 零外部成本（Binance market data free tier）/ 15 多 Agent 協作 formal（PA/MIT/FA/BB/E3/Operator 多 role）/ 16 Portfolio > 孤立 trade（D12 cap 跨 venue 合計）。

**§9.3 DOC-08 §12 9 條安全不變量觸碰 = 0/9**：本 spec interface stub level only；無 IMPL；不觸任一條。Y3+ activation 真寫 IMPL 階段才需逐條複核（per ADR-0040 §Decision 2 per-venue 5-gate schema 對齊）。

**§9.4 §四 5 硬邊界觸碰 = 0/5**：`execution_state` / `execution_authority` / `live_execution_allowed` / `decision_lease_emitted` / `max_retries=0` 全 0 觸碰。Y1+Y2 期間 `BinanceTrade` 全 panic stub；無任何 trading effect。Y3+ activation 走 ADR-0040 §Decision 2 venue-aware 擴展 5 gate；硬邊界紀律 venue-aware 後仍保留。

---

## §10 後續行動（給 PM 派發）

| Action | Owner | Track | Priority |
|---|---|---|---|
| Sign-off 本 M13 design spec + V116 placeholder spec | PM | Sprint 1A-δ closure | P0 |
| IMPL kickoff Sprint 1A-δ：派 E1 寫 AssetClass + Venue enum + sibling panic test + M1 LAL trait skeleton + M12 OrderRouter integration + M11 V107 venue field 預留文件化 | PM → E1 | Sprint 1A-δ | P0 |
| E2 review 重點：(a) sibling panic test 覆蓋 10 DEX/Hyperliquid string variant + 5 `BinanceTrade` trait method；(b) M1/M12/M11 integration trait skeleton 不寫 IMPL body；(c) V116 spec doc 不寫 full DDL | PM → E2 | Sprint 1A-δ | P0 |
| Cross-ADR consistency audit：本 spec + V116 + ADR-0040 三檔交叉引用無懸空 | PA → Sprint 1A-ε | Sprint 1A-ε | P1 |
| Sprint 10 Y1 Review：M13 retirement R1 first audit cycle | PA + MIT | Sprint 10 | P2 |
| Y3 Q1 (W105-W117) Binance trade enable 6 gate evaluation 啟動 | PM + MIT + FA + BB + Operator | Y3 Q1 | P3（Y3+ activation 時 priority 升 P0）|

---

## §11 關鍵文件指針（後續 IMPL agent / PM / E2 / E4 必讀）

- 本 M13 design spec：本檔
- V116 placeholder：`srv/docs/execution_plan/2026-05-21--v116_m13_multi_venue_reserved_schema_spec.md`（同 Sprint 1A-δ 同期 draft）
- ADR-0040 multi-venue gate spec：`srv/docs/adr/0040-multi-venue-gate-spec.md`（治理邊界 SoT）
- ADR-0033 ADR-0006 Bybit-Binance amendment：`srv/docs/adr/0033-adr-0006-bybit-binance-amendment.md`（Binance market-data Y1+Y2 不變 SoT）
- ADR-0006 Bybit-only exchange baseline：`srv/docs/adr/0006-bybit-only-exchange.md`（baseline 不變 SoT）
- ADR-0035 M5 online learning interface reserved：`srv/docs/adr/0035-m5-online-learning-interface-reserved.md`（同 pattern 範式 mirror）
- ADR-0039 M12 OrderRouter trait：`srv/docs/adr/0039-m12-order-router-trait-and-maker-fill-rate-metric.md`（共享 SymbolKey）
- ADR-0034 M1 LAL：`srv/docs/adr/0034-m1-decision-lease-lal.md`（venue change 走 LAL 4 SoT）
- v5.8 主檔 §2 M13 + §5 capital-tier ladder + §9 V116 reserved：`srv/docs/execution_plan/2026-05-20--execution-plan-v5.8.md:460-487 / 644-665 / 799`
- M11 design spec（V107 venue field 預留路徑來源）：`srv/docs/execution_plan/2026-05-21--m11_continuous_counterfactual_replay_design_spec.md`
- PA dispatch consolidation：`srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-21--v58_dispatch_consolidation.md` §Sprint 1A-δ
- AMD-2026-05-15-01 / AMD-2026-05-21-01 / CLAUDE.md §一 + §四 Hard Boundaries（venue-aware 5-gate per ADR-0040 §Decision 2）

---

## §12 審計記錄

| Source | Pattern coverage |
|---|---|
| PA Sprint 1A-δ M13 起草者 | Sprint 1A-δ deliverable + ADR-0040 cross-ref + enum hardcode + 6 gate enumerate + IMPL phase split |
| ADR-0035 M5 interface reserved | 範式 mirror — trait stub default panic + V### reserved placeholder + retirement R1-R4 + audit cadence + 16 原則合規格式 |
| ADR-0039 M12 OrderRouter | 共享 SymbolKey 設計 — M12 venue-aware route_order + SymbolKey(AssetClass + Venue + symbol) join key |
| M11 design spec | V107 venue field 預留路徑來源 — replay_divergence_log venue column DEFAULT 'bybit' backward-compat |
| V103/V104 spec | 範式 reference — frontmatter + §0 TL;DR + §開放問題 + §文件指針 + §審計記錄 結構 |

**§12.1 待 PM sign-off 前確認**：(1) PM sign-off 本 spec interface enum + trait skeleton scope（Sprint 1A-δ 30-40 hr）(2) PM sign-off 6 trade gate criteria 表 (§4) 對齊 ADR-0040 §Decision 3 無漂移 (3) PM 確認 §8.2 三 open Q 為 Y3+ activation 仲裁 deferred (4) PA cross-ADR consistency audit Sprint 1A-ε land（本 spec + V116 + ADR-0040 三檔交叉引用無懸空）

---

**END M13 Multi-Asset Class / Multi-Venue Capacity Module DESIGN spec draft v0**
