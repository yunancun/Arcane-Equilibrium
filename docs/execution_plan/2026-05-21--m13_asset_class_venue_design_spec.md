---
spec: M13 AssetClass / Venue Enum Interface Reservation DESIGN
date: 2026-05-21
author: PA Sprint 1A-δ (single sub-agent dispatch)
phase: v5.8 Sprint 1A-δ interface reservation
status: SPEC-PARTIAL-V0（partial spec — enum reservation only；不含 multi-asset / multi-venue full IMPL；Y2-Y3+ phased per AUM；待 E1 stub IMPL + PA Sprint 1A-ε cross-ADR audit 後升 SPEC-DRAFT-V1）
parent specs:
  - srv/docs/adr/0040-multi-venue-gate-spec.md (ADR-0040 ADR 權威 257 行 — 5 Decisions；本 spec 100% 對齊不違背)
  - srv/docs/adr/0033-adr-0006-bybit-binance-amendment.md (ADR-0033 Binance market-data Y1 approved + Y3+ trade defer baseline；§Decision 2 已被 ADR-0040 amend Y2 → Y3+)
  - srv/docs/adr/0006-bybit-only-exchange.md (ADR-0006 Bybit-only baseline 2026-04-03；thesis 不變)
  - srv/docs/execution_plan/2026-05-20--execution-plan-v5.8.md §2 M13 (line 460-487)
  - srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-21--v58_dispatch_consolidation.md §Sprint 1A-δ (line 159-167)
sibling specs:
  - srv/docs/execution_plan/2026-05-21--v116_m13_asset_venue_dim_schema_spec.md (V116 placeholder schema spec — 同 Sprint 1A-δ deliverable；本 DESIGN spec land 後 V116 full DDL upgrade Y2+ phase)
mirror precedent:
  - srv/docs/execution_plan/2026-05-21--m9_ab_framework_design_spec.md (M9 DESIGN spec 結構範式 — frontmatter / §0-§14)
  - srv/docs/adr/0035-m5-online-learning-interface-reserved.md (ADR-0035 interface reservation pattern — Y3+ retirement criteria 預設)
amendments:
  - AMD-2026-05-21-01 autonomy-vs-human-final-review (venue change always operator approval；本 spec §3 Venue 變更不可 Agent 自主)
scope: M13 AssetClass + Venue enum interface reservation only — 不寫 IMPL Rust/Python code (E1 後續工作); 不假設 PositionAggregator 既有 Rust path 存在 (per §6 caveat); 不違背 ADR-0040 5 Decisions; 不創造 DEX / Hyperliquid enum slot (per ADR-0040 Decision 4 hardcode reject); 不寫 V116 SQL DDL (sibling V116 placeholder land); 不在 Mac 跑 PG
---

# M13 AssetClass / Venue Enum Interface Reservation — DESIGN Specification (Sprint 1A-δ)

## §0 TL;DR

- **M13 為 multi-asset class / multi-venue interface reservation**：Sprint 1A-δ 階段僅落 type definition + ADR-0040 對齊；不寫 multi-asset / multi-venue full IMPL；後續 Y2-Y3+ phased per AUM ladder（per v5.8 §5 capital-tier ladder）
- **AssetClass enum 5 variants**：`Perp` (Y1 active) / `Spot` (Y1 active for Earn) / `Option` (Y1 active for C13 VRP) / `Earn` (Y1 active) / `Structured` (Y3+ activation; reserved)
- **Venue enum 5 variants**（per ADR-0040 Decision 4 + Decision 1 Y3+ amendment）：`BybitPerp` (Y1 active) / `BybitSpot` (Y1 active) / `BybitOption` (Y1 active) / `BinancePerp` (Y2 market-data only / Y3+ trade defer per ADR-0040 Decision 1) / `BinanceOption` (Y3+ reserved per v5.8 §2 M13 line 470 「Y3+: + Binance options」)
- **DEX / Hyperliquid hardcode 拒絕**（per ADR-0040 Decision 4 + ADR-0033 Decision 3 + CLAUDE.md §一 Bybit-only）：**不在 Venue enum 中保留 slot**；IMPL layer 任何 trying-to-use Dex / Hyperliquid 應 compile-error（找不到 enum variant）or return `Err`（per §3.4 反模式 (a)(b)）
- **Per-venue 5-gate trade enable**（per ADR-0040 Decision 2 venue-aware 5-gate schema）：新 venue trade enable 必通過 venue stage 0R-4 graduated canary + 5-gate live boundary（Python `live_reserved` / Operator role / `OPENCLAW_ALLOW_MAINNET=1` / per-venue valid secret slot / per-venue signed `authorization.json` with venue field）
- **Y3+ Binance trade activation 6 criteria**（per ADR-0040 Decision 3 — 合併 ADR-0033 4 條 + ADR-0040 新增 2 條）：(a) Y1+Y2 Bybit alpha sustained Sharpe ≥ X for 12-18 months / (b) Y1+Y2 Binance market data 顯示 cross-venue arbitrage / liquidation hunting 等 strategy +1%+ alpha vs Bybit-only baseline / (c) Operator 仲裁 new 5-gate review session / (d) BB confirmed cross-venue ToS/KYC / (e) Y2 末 Copy Trading evidence land per ADR-0030 4-Gate / (f) AUM ≥ $50k sustained 30d per v5.8 §5
- **既有 PositionAggregator extends caveat**（per v5.8 §2 M13 line 476 「existing PositionAggregator extends」）：grep 結果 = **Rust + Python 兩端皆未實作 PositionAggregator**（v5.8 文本是 PA 假設前提，實際 greenfield）；本 spec §6 §7 將其列為 Open Q + Sprint 8+ IMPL 工作，不在 1A-δ scope
- **§6 IMPL dispatch brief for E1**：Rust crate path `srv/rust/openclaw_types/src/asset_venue.rs` (新 module；對齊既有 7 module pattern) + enum + Display + FromStr + serde derive + 中文 doc comment 標 Y1/Y2/Y3+ availability + ADR-0040 + V116 placeholder ref；預估 **4-6 hr Rust IMPL**（純 enum + 基礎 trait derive；無 method body）；acceptance: `cargo build` OK + `cargo test` (enum round-trip 1-2 test + Dex/Hyperliquid compile-reject 驗 — 用 `trybuild` 或 `compile_fail` doctest)
- **AC（5-7 條）**：enum round-trip / Dex/Hyperliquid compile-reject / Display trait stable / FromStr 反向 parse / serde JSON 對齊 / per-venue authorization venue field 對齊 / cargo build 跨 Mac + Linux

---

## §1 Context + 為什麼

### 1.1 v5.8 §2 M13 module source

v5.8 §2 M13 line 460-487 將 Multi-asset class / multi-venue 列為 13 module 之一：

```
Asset class expansion roadmap:
  Y1: Bybit perp + Bybit spot (Earn) + Bybit options (C13 VRP)
  Y2: + Binance perp (price-equivalent symbols only; per ADR-0006 amendment)
  Y2-Y3: + structured products (Bybit Earn variants, options strategies beyond VRP)
  Y3+: + Binance options (when AUM justifies)
  Always declined: DEX / Hyperliquid (D1a per operator)
```

operator 2026-05-21 指示「design at initial stage even if IMPL delayed — 對後續接入更 friendly」（per PA report 行 22）。

### 1.2 為什麼 M13 必須在 Sprint 1A-δ DESIGN 階段 land

per PA dispatch consolidation 行 159-167（Sprint 1A-δ deliverable）：M13 30-40 hr DESIGN 包含 AssetClass + Venue enum + ADR-0040 + V116 reserved 四件耦合。本 DESIGN spec 是 ADR-0040 在工程層的對應 enum reservation；E1 後續 IMPL 期可直接讀此 spec 對齊 ADR-0040 5 Decisions：

- 4 cluster taxonomy 邊界 → ADR-0040 Decision 4 Venue enum hardcode + DEX/Hyperliquid 拒絕 → §3.4 反模式
- per-venue 5-gate schema → ADR-0040 Decision 2 → §4 multi-venue gate inheritance
- per-venue 6 條 Y3+ Binance trade enable gate criteria → ADR-0040 Decision 3 → §5.2 Y3+ activation criteria
- per-venue authorization 三元組綁定 → ADR-0040 Decision 5 → §4.5 authorization venue field

### 1.3 v5.8 文本 vs ADR-0040 字面衝突（已被 ADR-0040 解決）

v5.8 §2 M13 line 467-468 寫「Y2: + Binance perp (price-equivalent symbols only; per ADR-0006 amendment Binance market-data primary, trade secondary)」— 此 **trade secondary** 字面與 ADR-0033 §Decision 2「Y1 末 evaluation」立場 + ADR-0040 §Decision 1「Y2 → Y3+ at earliest」amendment **已產生字面衝突**。

per BB 5.21 v5.8 audit push back + PM final verdict §四 D4 + operator D4 已批：**本 DESIGN spec 對齊 ADR-0040 不對齊 v5.8 文本**。即 Y2 期間 Binance perp **僅 market-data**，trade enable 至少 defer 到 Y3+ first quarter (~Y2 末 W104+) evaluation。

### 1.4 為什麼 Sprint 1A-δ 只做 interface reservation 不寫 IMPL

per ADR-0040 Decision 4 末段 + ADR-0035 interface reservation pattern：

- Sprint 1A-δ 階段 = **enum + Display + FromStr + serde derive only**；無 method body；無 venue dispatch logic
- Multi-venue trading logic IMPL 走 Y2+ phase；對 Binance trade enable 走 Y3+ first quarter（per ADR-0040 Decision 1）
- Sprint 1A-δ 純為「將 DEX/Hyperliquid 從 enum 根源拒絕」+「為 Y3+ Binance enable 預留 schema」+「為 §4 per-venue 5-gate 提供 type-level 對齊」
- 任何嘗試在 Sprint 1A-δ 加 venue method body / venue dispatch / venue routing logic = 違反本 spec scope；應由 E1 dispatch packet 列為 BLOCKER 拒絕

### 1.5 為什麼 Bybit + Binance only，DEX / Hyperliquid 永久拒絕

per ADR-0033 §Decision 3 + ADR-0040 §Decision 4 + CLAUDE.md §一 Bybit-only baseline：

- **DEX (Uniswap / GMX / dYdX 等)**：D1a operator hardcode reject；MEV / gas / smart contract attack surface / KYC dispute mitigation 對 $50k+ AUM 帳不經濟
- **Hyperliquid**：D1a operator hardcode reject；centralized perp DEX 仍有 smart contract attack surface + 流動性集中風險 + 法規不確定性
- **enum-level rejection 比 string literal rejection 更強**：string literal venue ID 容易繞過編譯期 venue check（如 PR 中混入 `"hyperliquid"` 而未 ADR review）；enum-driven 演進 = 受控路徑（per ADR-0040 Decision 4 末段）

### 1.6 為什麼 BinanceOption 是 Y3+ reserved variant

per v5.8 §2 M13 line 470「Y3+: + Binance options (when AUM justifies)」：

- BinanceOption 為 Y3+ enable variant；不在 Y1/Y2 active set
- enum slot 預留是為避免 Y3+ enable 時需另開 ADR 加 enum variant（per ADR-0040 Decision 4 末段「未來開放新 venue 路徑必須開新 ADR」原則）
- 與 BinancePerp 的差異：BinancePerp Y2 market-data only / Y3+ trade defer；BinanceOption Y3+ 才 reserve（無 Y2 market-data 階段）
- 邊界：若 Y3+ Binance trade enable 6 criteria 通過後，BinanceOption Y3+ enable 仍走獨立 ADR + 獨立 5-gate review（不繼承 BinancePerp 的 5-gate 通過狀態）

### 1.7 不在本 spec 範圍

- ❌ IMPL Rust code（E1 Sprint 1A-δ 後續工作；本 spec 為 DESIGN）
- ❌ V116 SQL DDL 寫作（sibling V116 placeholder spec land；full DDL 在 M13 Y2+ phase）
- ❌ Mac 跑 PG SQL（必 Linux PG empirical；走 V116 spec dry-run 規範）
- ❌ Rust/Python writer 對應 venue dispatch / venue routing logic（Y2+ IMPL 工作）
- ❌ Cross-venue PositionAggregator IMPL（Sprint 8+ phase；per §6 §7 Open Q）
- ❌ Multi-venue Decision Lease + Guardian extend（Y3+ Binance trade enable 通過後 IMPL）
- ❌ ContextDistiller v4 token cap 對齊（per ADR-0041；M13 enum reservation 不在 hot path L1 SLA）

---

## §2 AssetClass Enum 詳細規範

per ADR-0040 + v5.8 §2 M13 line 474「AssetClass enum (Perp / Spot / Option / Earn / Structured)」。

### 2.1 Variant 列表 + Y1/Y2/Y3+ availability

| Variant | 對應 asset 類型 | Availability | Doc comment Y 標記 | 依賴 |
|---|---|---|---|---|
| **Perp** | Perpetual futures | **Y1 active** | `/// Y1 active: Perpetual futures (Bybit USDT perp)` | 5 baseline strategies (grid / ma / bb_breakout / bb_reversion / funding_arb) |
| **Spot** | Spot trading | **Y1 active** | `/// Y1 active: Spot trading (Bybit spot for Earn collateral)` | Bybit Earn integration（per ADR-0032 Earn asset movement Guardian） |
| **Option** | Options | **Y1 active** | `/// Y1 active: Options trading (Bybit options for C13 VRP only)` | C13-VRP strategy land（per v5.8 §2 Sprint 5 C13-VRP IMPL） |
| **Earn** | Yield-bearing products | **Y1 active** | `/// Y1 active: Earn yield products (Bybit Earn variants)` | per v5.8 §2 Sprint 4+ Earn revenue lane + ADR-0031 Framework expansion |
| **Structured** | Structured products | **Y3+ reserved** | `/// Y3+ reserved: Structured products (per v5.8 §5 Tier C+ @ AUM $75k+)` | M13 Tier C+ AUM $75k+ activation gate（per v5.8 §5 capital-tier ladder） |

### 2.2 為什麼 Perp / Spot / Option / Earn 4 個 Y1 active 而非僅 Perp

per v5.8 §2 M13 line 466-467「Y1: Bybit perp + Bybit spot (Earn) + Bybit options (C13 VRP)」：

- **Perp**：5 baseline strategies hot path；Sprint 4 first Live A/B 啟用核心
- **Spot**：Earn 整合需 spot 持倉 + collateral routing；Y1 Sprint 4+ revenue lane 必需
- **Option**：C13-VRP strategy land 後啟用（per ADR-0031 Framework expansion C13 option strategy）；Y1 Sprint 5+ Live A/B
- **Earn**：Earn 整合屬於獨立 asset class（不是 Spot 的子集 — Earn 有 lockup period + APR + redemption mechanics），per ADR-0031 + ADR-0032 應有獨立 enum variant

### 2.3 為什麼 Structured 是 Y3+ reserved 而非 Y2

per v5.8 §2 M13 line 469「Y2-Y3: + structured products (Bybit Earn variants, options strategies beyond VRP)」+ v5.8 §5 capital-tier ladder Y3 Q2 estimate $25-50k：

- Structured products = 比 Earn 更複雜的 yield variant（如 Dual Asset / Snowball / Auto-Compound）；Risk profile 更高
- Y2-Y3 文本 range 暗示「Y2 late 或 Y3 early」；保守採 Y3+ reserved（不在 Y2 自動 active）
- M13 Tier C+ activation criteria per v5.8 §5：AUM ≥ $75k sustained 30d + Operator approval（per ADR-0034 LAL 4 venue change always operator）
- 與 BinanceOption 的差異：Structured 是 asset class 維度擴展；BinanceOption 是 venue 維度擴展；兩者獨立 evaluation gate

### 2.4 Doc comment 範本（per E1 IMPL 對齊）

```rust
/// Asset class taxonomy for OpenClaw trading engine.
/// OpenClaw 交易引擎的 asset class 分類。
///
/// Per v5.8 §2 M13 + ADR-0040 Decision 4 venue-asset taxonomy.
/// 對應 v5.8 §2 M13 + ADR-0040 Decision 4 venue-asset 分類。
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum AssetClass {
    /// Y1 active: Perpetual futures (Bybit USDT perp)
    /// Y1 起用：永續合約（Bybit USDT 永續）
    Perp,
    /// Y1 active: Spot trading (Bybit spot for Earn collateral)
    /// Y1 起用：現貨（Bybit 現貨，作 Earn 抵押用）
    Spot,
    /// Y1 active: Options trading (Bybit options for C13 VRP only)
    /// Y1 起用：選擇權（Bybit options，僅 C13 VRP 策略用）
    Option,
    /// Y1 active: Earn yield products (Bybit Earn variants)
    /// Y1 起用：理財收益產品（Bybit Earn 系列）
    Earn,
    /// Y3+ reserved: Structured products (per v5.8 §5 Tier C+ @ AUM $75k+)
    /// Y3+ 預留：結構性產品（per v5.8 §5 Tier C+ AUM $75k+ 啟用）
    Structured,
}
```

### 2.5 反模式（明示禁止）

- (a) 在 Sprint 1A-δ enum 中加 method body（如 `fn min_position_size()` / `fn supported_strategies()`）— 違反 §1.4 interface reservation scope
- (b) 用 string literal `"perp"` / `"spot"` 替代 enum variant — 違反 ADR-0040 Decision 4「string literal venue 容易繞過編譯期 venue check」原則
- (c) 在 Sprint 1A-δ 加 Y1 active variant 以外的 IMPL（如 Structured asset 邏輯）— 違反 §1.4 phased per AUM 原則
- (d) 加 `Unknown` / `Other` catch-all variant — 違反 fail-closed 紀律（catch-all variant 容易繞過 enum exhaustiveness check）

---

## §3 Venue Enum 詳細規範

per ADR-0040 Decision 4 venue enum hardcode + Decision 1 Y3+ Binance trade defer。

### 3.1 Variant 列表 + Y1/Y2/Y3+ availability

| Variant | 對應 venue | Availability | Trade enabled | Market-data enabled | 5-gate authorization 路徑 |
|---|---|---|---|---|---|
| **BybitPerp** | Bybit USDT perp | **Y1 active** | ✅ | ✅ | `$OPENCLAW_SECRETS_DIR/api_key` (Bybit original path) |
| **BybitSpot** | Bybit spot | **Y1 active** | ✅ | ✅ | same Bybit path |
| **BybitOption** | Bybit options | **Y1 active (C13 VRP only)** | ✅ | ✅ | same Bybit path |
| **BinancePerp** | Binance USDT perp | **Y2 market-data only / Y3+ trade defer** | ❌ Y2 / Y3+ gated | ✅ Y2 onwards | `$OPENCLAW_SECRETS_DIR/external/binance/api_key` (per H-21 external secret slot policy + ADR-0040 Decision 2) |
| **BinanceOption** | Binance options | **Y3+ reserved** | ❌ Y3+ gated | ❌ Y3+ gated | same Binance path（Y3+ activation 時建立） |

### 3.2 為什麼 BinancePerp Y2 market-data only / Y3+ trade defer

per ADR-0040 §Decision 1（amend ADR-0033 §Decision 2 Y2 → Y3+ at earliest）+ §Context Y1 末 evidence 不足分析：

- **Y2 期間**：Binance maintain market-data only（per ADR-0033 §Decision 1 不變）；用於 cross-venue arbitrage counterfactual replay analysis（per ADR-0038 M11 continuous counterfactual replay）
- **Y2 期間禁止**：(a) 任何 Binance order placement (b) 任何 Binance authentication beyond market-data API key (c) 任何 Binance asset transfer / wallet operation
- **Y3+ first quarter (~Y2 末 W104+) evaluation**：6 criteria 全 PASS 才開新 ADR enable Binance trade
- **Y3+ evaluation 失敗 → defer**：任一 6 條件 fail → 維持 Bybit-only trading，繼續 Y3+ cycle 重評

### 3.3 為什麼 DEX / Hyperliquid hardcode 不放入 enum

per ADR-0040 Decision 4 + ADR-0033 Decision 3 + CLAUDE.md §一 + §1.5：

- **enum-level rejection 比 string literal rejection 強**：DEX/Hyperliquid 不在 enum 中保留 slot → IMPL layer compile-error（找不到 enum variant）
- **未來開放路徑**：若未來需開放新 venue（如 OKX / Coinbase），**必須開新 ADR 顯式 amend ADR-0040 + 新增 enum variant + 對應 per-venue 5-gate schema**；不可在沒有新 ADR 的情況下 hot-patch 加 string venue
- **Read-only on-chain query 例外**：per ADR-0033 §Decision 3 例外 + ADR-0031 Framework 3 on-chain counterfactual-only Y1 立場；**不創造 venue enum slot**（read-only RPC query 不屬於 trading venue；走 ADR-0031 framework 不走 M13 venue enum）

### 3.4 反模式（明示禁止 per ADR-0040 Decision 4）

- (a) **IMPL layer 嘗試使用 `Venue::Hyperliquid` / `Venue::Uniswap` / `Venue::DyDx`**：compile-error（enum variant 不存在）→ 編譯期 fail-closed
- (b) **string literal venue routing**：如 `dispatch_to_venue("hyperliquid")` / `Venue::from_str("uniswap")` → §3.5 FromStr 必 reject DEX/Hyperliquid string literal → runtime `Err(VenueParseError::UnknownVenue)`
- (c) **catch-all variant `Venue::Other(String)`**：違反 enum hardcode rejection 紀律；不允許
- (d) **在 Sprint 1A-δ 加 DEX/Hyperliquid 為 reserved variant**：違反 ADR-0040 Decision 4「不在 enum 中保留 slot」立場 — reserved ≠ inactive；保留 slot 等同於開放未來 enable 路徑
- (e) **string literal venue ID 經 unsafe path 繞 enum check**（如 `unsafe { transmute }`）→ E2 review 必 reject

### 3.5 Doc comment + FromStr 範本（per E1 IMPL 對齊）

```rust
/// Trading venue taxonomy for OpenClaw trading engine.
/// OpenClaw 交易引擎的 trading venue 分類。
///
/// Per ADR-0040 Decision 4 venue enum hardcode + Decision 1 Y3+ Binance trade defer.
/// 對應 ADR-0040 Decision 4 venue enum hardcode + Decision 1 Y3+ Binance trade 延後。
///
/// **DEX / Hyperliquid hardcode 拒絕**：per ADR-0033 Decision 3 + CLAUDE.md §一；
/// 不在 enum 中保留 slot；未來開放新 venue 必開新 ADR amend ADR-0040。
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum Venue {
    /// Y1 active: Bybit USDT perpetual futures
    /// Y1 起用：Bybit USDT 永續合約
    BybitPerp,
    /// Y1 active: Bybit spot trading
    /// Y1 起用：Bybit 現貨交易
    BybitSpot,
    /// Y1 active: Bybit options (C13 VRP only)
    /// Y1 起用：Bybit 選擇權（僅 C13 VRP 策略用）
    BybitOption,
    /// Y2 market-data only / Y3+ trade defer per ADR-0040 Decision 1
    /// Y2 僅市場資料 / Y3+ 才考慮 trade 啟用 per ADR-0040 Decision 1
    BinancePerp,
    /// Y3+ reserved per v5.8 §2 M13 line 470 (when AUM justifies)
    /// Y3+ 預留 per v5.8 §2 M13 line 470 (AUM 充足時啟用)
    BinanceOption,
}

impl std::str::FromStr for Venue {
    type Err = VenueParseError;
    fn from_str(s: &str) -> Result<Self, Self::Err> {
        match s {
            "BybitPerp" | "bybit_perp" => Ok(Self::BybitPerp),
            "BybitSpot" | "bybit_spot" => Ok(Self::BybitSpot),
            "BybitOption" | "bybit_option" => Ok(Self::BybitOption),
            "BinancePerp" | "binance_perp" => Ok(Self::BinancePerp),
            "BinanceOption" | "binance_option" => Ok(Self::BinanceOption),
            // DEX / Hyperliquid hardcode reject per ADR-0040 Decision 4
            // DEX / Hyperliquid 硬編碼拒絕 per ADR-0040 Decision 4
            _ => Err(VenueParseError::UnknownVenue(s.to_string())),
        }
    }
}
```

注意 `VenueParseError` 為新 error enum（E1 IMPL 期 land；用 `thiserror` derive）；具體 IMPL 細節留 E1 dispatch packet。

---

## §4 Multi-Venue Gate Inheritance（per ADR-0040 Decision 2 venue-aware 5-gate）

### 4.1 既有 5-gate live boundary（per CLAUDE.md §四）

CLAUDE.md §四 既有 5-gate live boundary（current Bybit-only）：

1. Python `live_reserved`
2. Operator role 授權
3. `OPENCLAW_ALLOW_MAINNET=1`
4. Valid secret slot
5. Signed `authorization.json` with matching environment

### 4.2 ADR-0040 Decision 2 venue-aware 擴展

per ADR-0040 Decision 2，5 gate 擴展為 venue-aware：

| Gate | 既有設計 | Venue-aware 擴展 |
|---|---|---|
| 1. Python `live_reserved` | Bybit-only | **Venue-agnostic** — 任一 venue trading 啟用都需通過 |
| 2. Operator role 授權 | Bybit-only | **Venue-agnostic** — 任一 venue trading 啟用都需通過 |
| 3. `OPENCLAW_ALLOW_MAINNET=1` | Bybit-only | **Venue-agnostic** — 任一 venue trading 啟用都需通過 |
| 4. Valid secret slot | `$OPENCLAW_SECRETS_DIR/api_key`（Bybit only） | **Per-venue** — Bybit 走原 path；Binance 走 `external/binance/api_key`（per H-21 external secret slot policy） |
| 5. Signed `authorization.json` | environment-bound（demo / live） | **Venue-aware** — `authorization.json` 必含 `venue` field（默認 = `'bybit'`）；non-bybit venue 必經 Y3+ Binance enable gate（per ADR-0040 Decision 3） |

### 4.3 Fail-closed 邊界（per ADR-0040 Decision 2 末段）

5-gate 任一 fail → fail-closed **該 venue 全部 outbound order**（不影響其他 venue）：

- 例 1：Bybit secret slot expired → Bybit trading freeze，**不影響** Binance market-data read（per ADR-0033 §Decision 1 Binance market-data 持續）
- 例 2：Binance authorization.json venue field 校驗 fail → Binance trading freeze（Y3+ enable 後），**不影響** Bybit trading
- 例 3：Operator role 撤銷 → 所有 venue trading 同時 freeze（venue-agnostic gate fail）

### 4.4 IMPL caveat — Sprint 1A-δ 不寫 fail-closed dispatch logic

per §1.4 interface reservation scope：

- Sprint 1A-δ 只 land enum + per-venue secret slot path constant + authorization.json venue field schema 設計
- Fail-closed dispatch logic（如「BybitPerp secret expired → BybitPerp trading freeze, Binance market-data 不影響」）= Y3+ Binance trade enable IMPL 期工作
- 本 spec §4.2 venue-aware 擴展為 schema 級設計；具體 fail-closed dispatch 在應用層 IMPL（per ADR-0040 Decision 2 末段「fail-closed scope = venue-aware」）

### 4.5 Authorization.json venue field schema

per ADR-0040 Decision 5 + AMD-2026-05-15-01 + ADR-0008 Decision Lease：

- **venue + environment + secret slot 三元組綁定**（per AMD-2026-05-15-01 + ADR-0008 Decision Lease）
- 三元組任一 mismatch 即 fail-closed
- `authorization.json` schema 強制 `venue` field（默認 = `'bybit'` 維持既有 backward compatibility）
- non-bybit venue 必須顯式寫 `venue` field

Authorization.json schema 範例（不在 Sprint 1A-δ IMPL；Y3+ Binance enable IMPL 期 land）：

```json
{
  "schema_version": "2.0",
  "venue": "binance_perp",
  "environment": "live",
  "secret_slot_path": "/path/to/external/binance/api_key",
  "expires_at": "2027-01-01T00:00:00Z",
  "operator_signature": "..."
}
```

### 4.6 反模式（per ADR-0040 Decision 2 + Decision 5）

- (a) **single secret slot expired 誤殺所有 venue**：違反 venue-aware fail-closed scope；schema-level 必 per-venue isolation
- (b) **string literal venue 繞 authorization.json venue field 校驗**：如 hardcode `"binance"` 而未走 enum；schema-level 校驗 fail
- (c) **Agent 自主提案 venue enable / disable**：per ADR-0034 LAL 4 + AMD-2026-05-21-01 venue change always operator；Agent 提案 = invariant violation

---

## §5 5-Gate Inheritance + Y3+ Activation Criteria（per ADR-0040 Decision 3）

### 5.1 既有 venue stage 0R-4 graduated canary（per AMD-2026-05-15-01）

每新 venue trade enable 必通過：

1. **Stage 0R replay preflight**：venue-specific replay preflight；驗 venue data feed + venue order semantics
2. **Stage 0 shadow**：venue shadow trading（無實際 outbound order）
3. **Stage 1 demo small**：venue demo small order；累積 fills evidence
4. **Stage 2 demo full**：venue demo full;
5. **Stage 3 live canary**：venue live small canary
6. **Stage 4 live full**：venue live full（per ADR-0034 LAL 4 operator approval mandatory）

### 5.2 Y3+ Binance trade enable 6 criteria（per ADR-0040 Decision 3）

合併 ADR-0033 §Decision 2 4 條 + ADR-0040 新增 2 條（Y2 末額外 evidence）：

| # | Criterion | 來源 | 評估方法 |
|---|---|---|---|
| (a) | Y1 + Y2 Bybit self-trading alpha 已驗證 | ADR-0033 §Decision 2 (a) 延伸 | Sharpe ≥ X for **12-18 months sustained**（per ADR-0030 Gate 1 Alpha 延伸；Y1+Y2 累積 ~22 months 樣本足夠） |
| (b) | Y1 + Y2 Binance market data analysis 顯示 cross-venue arbitrage / liquidation hunting 等 strategy 真有 +1%+ alpha vs Bybit-only baseline | ADR-0033 §Decision 2 (b) 延伸 | Counterfactual replay using Binance market data Y1+Y2 兩年累積；vs Bybit-only baseline alpha attribution |
| (c) | Operator 仲裁 | ADR-0033 §Decision 2 (c) 不變 | **New 5-gate review session**（per ADR-0040 Decision 2 venue-aware authorization.json 簽署需 Operator session） |
| (d) | BB confirmed Binance ToS / KYC 持續可行 | ADR-0033 §Decision 2 (d) 不變 | BB 提供 Bybit + Binance KYC + ToS cross-venue 持續性 audit 報告 |
| (e) | **Y2 末 Copy Trading evidence land** | **ADR-0040 新增** | per ADR-0030 Copy Trading evidence-gated；Y2 末 Copy Trading 必須通過 4-Gate evaluation 並 land 為 active income stream |
| (f) | **AUM ≥ $50k sustained 30d** | **ADR-0040 新增** | per v5.8 §5 capital-tier ladder Y3+ AUM 估計；$50k 是 Binance trade enable 的 capital efficiency 門檻 |

**6 條 AND 邏輯**：6 條全 PASS → Y3+ evaluation PASS → 開新 ADR 落地 Binance trade enable；任一 FAIL → continue defer。

### 5.3 M13 Tier B / Tier C+ activation criteria（per ADR-0040 + v5.8 §5 capital-tier ladder）

| Tier | 對應 venue / asset | AUM threshold | 啟用 criteria | 評估時點 |
|---|---|---|---|---|
| **Tier A (Y1 baseline)** | BybitPerp + BybitSpot + BybitOption + Earn | $0+ baseline | Sprint 4 first Live 啟用 + P0 precondition 通過 | Y1 Sprint 4 W17.5+ |
| **Tier B (Y3+ Binance perp trade enable)** | BinancePerp trade enable | **AUM ≥ $50k sustained 30d** + Operator 仲裁 + Y3+ 5-gate review | per §5.2 6 條 AND | Y3+ first quarter (~Y2 末 W104+) |
| **Tier C+ (Y3+ Structured + BinanceOption)** | Structured + BinanceOption + Binance options expanded | **AUM ≥ $75k sustained 30d** + Operator 仲裁 + Tier C+ 獨立 5-gate review | per ADR-0040 + 獨立 ADR | Y3+ later quarter |

### 5.4 永久放棄條件（per ADR-0040 + ADR-0033 §Decision 2 邏輯延伸）

- 連續 3 個 evaluation cycle (~12-18 months) fail → 開新 ADR 永久關閉 Binance trading optionality
- BinanceOption Tier C+ 失敗 → 不退回 BinancePerp（Tier B 維持）
- Structured Tier C+ 失敗 → 不影響 Earn Y1 active（per ADR-0031 Framework expansion 獨立 path）

### 5.5 反模式（per ADR-0040 Decision 3 + AMD-2026-05-21-01）

- (a) **6 criteria 任一 evidence 模糊 → 強行 PASS**：違反「6 條 AND 邏輯」；任一 inconclusive 應 defer 不應 PASS
- (b) **跨 Tier 升級**（如 Y2 末直接從 Tier A 升 Tier C+）：違反 stage 路徑紀律；必 Tier A → Tier B → Tier C+ phased
- (c) **Agent 自主提案 Tier 升級**：per AMD-2026-05-21-01 venue change always operator；Agent 提案 = invariant violation
- (d) **5-gate review session 走 auto path 繞 Operator**：per ADR-0034 LAL 4 + ADR-0040 Decision 5 三元組綁定；不允許

---

## §6 IMPL Dispatch Brief for E1（核心交付物）

### 6.1 Rust crate path 建議

per §1.4 + 既有 `openclaw_types` crate 結構（grep 確認 7 個 module: agent / cognitive / intent / price / risk / state + lib.rs；新增 1 module = 8 個 module）：

| 項目 | 設計 |
|---|---|
| **Crate** | `srv/rust/openclaw_types`（既有 crate；對齊 7 module pattern） |
| **新增 module file** | `srv/rust/openclaw_types/src/asset_venue.rs` |
| **lib.rs 對應 export 新增** | `pub mod asset_venue;` + `pub use asset_venue::{AssetClass, Venue, VenueParseError};` |
| **依賴 crates** | `serde` (已在 dependency) + `thiserror`（如未在依賴需加；E1 dispatch packet 確認） |
| **預估工時** | **4-6 hr Rust IMPL**（純 enum + 基礎 trait derive + FromStr + Display + serde derive；無 method body；無 venue dispatch logic） |

### 6.2 E1 IMPL acceptance criteria

| AC | 驗證方法 | 預期結果 |
|---|---|---|
| **AC-1** Cargo build OK | `cargo build -p openclaw_types` (Mac + Linux) | 0 error / 0 warning |
| **AC-2** Cargo test 通過 enum round-trip | `cargo test -p openclaw_types asset_venue` | 1-2 test pass：(a) `AssetClass::Perp.to_string() == "Perp"` round-trip via FromStr；(b) `Venue::BybitPerp.to_string() == "BybitPerp"` round-trip via FromStr |
| **AC-3** Dex / Hyperliquid compile-reject 驗 | `trybuild` 或 `compile_fail` doctest | 嘗試 `Venue::Hyperliquid` 或 `Venue::Uniswap` → compile error: "no variant named X" |
| **AC-4** FromStr 反向 parse | `cargo test` | `Venue::from_str("hyperliquid")` → `Err(VenueParseError::UnknownVenue("hyperliquid"))` |
| **AC-5** Serde JSON 對齊 | `cargo test` | `serde_json::to_string(&Venue::BybitPerp)` == `"BybitPerp"`（或 snake_case `"bybit_perp"`，per E1 selection） |
| **AC-6** Display trait 穩定 | `cargo test` | `format!("{}", Venue::BybitPerp)` == `"BybitPerp"`；2 次調用結果一致 |
| **AC-7** Golden schema validation pass | `cargo test schema_golden_tests` | per `openclaw_types/src/lib.rs` 既有 golden schema 規範；新增 `AssetClass` + `Venue` entry 至 `rust/schemas/shared_types.json`（**Open Q：Sprint 1A-δ 是否擴展 golden schema** — 見 §7） |

### 6.3 E1 IMPL phase steps

E1 Sprint 1A-δ IMPL 步驟（per 4-6 hr scope）：

1. **Step 1 (~30min)**：讀 `srv/docs/adr/0040-multi-venue-gate-spec.md` (257 行) + 本 spec §2 + §3 + §6
2. **Step 2 (~60min)**：建立 `srv/rust/openclaw_types/src/asset_venue.rs`；定義 `AssetClass` + `Venue` + `VenueParseError` enum + 中文 doc comment（per §2.4 + §3.5 範本）
3. **Step 3 (~60min)**：impl `Display` + `FromStr` + `Serialize` + `Deserialize`（serde derive）
4. **Step 4 (~30min)**：lib.rs 加 `pub mod asset_venue;` + `pub use ...;`
5. **Step 5 (~60min)**：寫 enum round-trip test + Dex/Hyperliquid compile-reject test（用 `trybuild` 或 inline `compile_fail` doctest）
6. **Step 6 (~30min)**：跑 `cargo build` + `cargo test` Mac local；commit + push
7. **Step 7 (Linux verify ~30min)**：`ssh trade-core` + `git pull --ff-only` + `cargo build` Linux verify；無 IPC 影響（純 type definition）；無 engine restart 需求

### 6.4 E1 IMPL phase exclusions

E1 IMPL **不做**以下工作：

- ❌ Venue dispatch logic（如 `match venue { ... }` 路由實際 trade）
- ❌ AssetClass method body（如 `fn min_position_size()`）
- ❌ V116 SQL DDL（sibling V116 placeholder spec land；full DDL Y2+ phase）
- ❌ PositionAggregator extends（per v5.8 §2 M13 line 476；既有 PositionAggregator 不存在 — §7 Open Q 1；Sprint 8+ IMPL）
- ❌ Multi-venue Decision Lease + Guardian extend（Y3+ Binance trade enable 通過後 IMPL）
- ❌ Authorization.json venue field schema IMPL（Y3+ Binance enable IMPL 期 land；本 spec §4.5 為 schema 設計）
- ❌ Cross-venue position netting logic（Sprint 8+ phase）

### 6.5 E2 review focus（3 重點）

E2 sub-agent review 時必查 3 點：

1. **DEX / Hyperliquid hardcode rejection 驗**：grep 結果應顯示 0 個 `Hyperliquid` / `Uniswap` / `DyDx` / `GMX` enum variant；trybuild compile_fail test 必 PASS
2. **enum variant naming 對齊 ADR-0040 Decision 4**：5 個 variant 必齊：`BybitPerp` / `BybitSpot` / `BybitOption` / `BinancePerp` / `BinanceOption`；無 catch-all `Other` / `Unknown`
3. **Y1/Y2/Y3+ doc comment availability 標記齊全**：每個 variant doc comment 必含 `Y1 active` / `Y2 market-data only` / `Y3+ reserved` 一致；ADR-0040 + v5.8 §2 M13 cross-ref

---

## §7 Open Q + Risk Caveats

### 7.1 Open Q 1: PositionAggregator 既有 Rust path 不存在（spec → IMPL gap）

**背景**：v5.8 §2 M13 line 476 寫「Cross-venue position aggregator (existing PositionAggregator extends)」。
**Grep 結果**：`srv/rust/` + `srv/python/` 兩端皆 **0 個** `PositionAggregator` / `position_aggregator` 結果。

**結論**：v5.8 文本「existing PositionAggregator extends」是 PA 假設前提；實際代碼層 = greenfield。

**影響**：
- Sprint 1A-δ scope 不 IMPL PositionAggregator（per §6.4 exclusion）
- Sprint 8+ phase IMPL 必先做：(a) Decide if 新建 Rust struct `PositionAggregator` 或 extend Python；(b) Decide cross-venue position netting algorithm；(c) Decide schema （V116 dim table 是否含 position_aggregator state field）
- Sprint 1A-δ 文檔層 caveat：本 spec §1.7 已列「Cross-venue PositionAggregator IMPL = Sprint 8+ phase」
- 建議：Sprint 1A-ε cross-ADR consistency audit 時，verify v5.8 §2 M13 文本「existing PositionAggregator extends」是否需 patch 為「new PositionAggregator (Sprint 8+ IMPL)」

**Owner**：PA Sprint 1A-ε cross-ADR consistency audit 期 confirm + 主會話 v5.8 主檔 patch 決定

### 7.2 Open Q 2: ADR-0033 編號確認（spec → IMPL gap）

**背景**：任務指示需 grep verify ADR-0033 編號。

**Grep 結果**：`srv/docs/adr/0033-adr-0006-bybit-binance-amendment.md` 存在；確認為 ADR-0033 對應實體 file path。

**結論**：ADR-0033 編號正確；本 spec parent specs 引用路徑為 `srv/docs/adr/0033-adr-0006-bybit-binance-amendment.md`。

**影響**：無 gap；本 spec 引用路徑已正確。

### 7.3 Open Q 3: Golden schema validation 擴展與否

**背景**：per `srv/rust/openclaw_types/src/lib.rs` line 28-162 既有 golden schema validation test pattern；新增 `AssetClass` + `Venue` enum 是否同步 update `rust/schemas/shared_types.json`?

**Considerations**：
- (a) **擴展 golden schema**：cross-language contract 完整性高；Python side（如有）可同步驗 enum；但增加 Sprint 1A-δ IMPL 工時 1-2 hr
- (b) **不擴展 golden schema**：純 Rust internal type；Sprint 1A-δ scope 不含 Python binding；後續 Y2+ IMPL 期再擴展

**建議**：(b) 不擴展，由 E1 Sprint 1A-δ IMPL 確認 — 純 Rust type definition；Python binding 走 Y2+ IMPL 期；golden schema 擴展應在 PyO3 binding land 時同步。

**Owner**：E1 Sprint 1A-δ IMPL 期決定 + E2 review 期確認

### 7.4 Open Q 4: VenueParseError variant 範圍

**背景**：本 spec §3.5 FromStr IMPL 範本含 `VenueParseError::UnknownVenue(String)`；是否需 enrich variant？

**Considerations**：
- (a) **最小 variant 集合**：僅 `UnknownVenue(String)` — 4-6 hr IMPL scope 內可達
- (b) **enrich variant**：加 `DeniedByADR0040(String)` / `RequiresOperatorApproval(String)` 等 — 更明示 fail-closed reason；但增 IMPL 工時 1-2 hr

**建議**：(a) 最小 variant 集合；fail-closed reason 走應用層 log；後續 Y3+ Binance enable IMPL 期可 enrich。

**Owner**：E1 Sprint 1A-δ IMPL 期決定

### 7.5 Risk Caveat 1: Sprint 1A-δ scope creep risk

**Risk**：E1 IMPL 期可能誤入 venue dispatch logic / AssetClass method body / cross-venue aggregator design — 違反 §1.4 interface reservation scope。

**Mitigation**：
- E1 dispatch packet 強制引用本 spec §1.4 + §6.4 exclusion list
- E2 review 必查 §6.5 3 重點
- 4-6 hr 工時 cap 嚴格執行；超時即停 + 升 PA Sprint 1A-δ extension review

### 7.6 Risk Caveat 2: ADR-0040 Y3+ amendment 文本同步風險

**Risk**：v5.8 §2 M13 line 467-468 文本仍寫「Y2: + Binance perp ... trade secondary」與 ADR-0040 Y3+ amendment 字面衝突；本 spec 對齊 ADR-0040 不對齊 v5.8。

**Mitigation**：
- 本 spec §1.3 已明示 v5.8 文本 vs ADR-0040 字面衝突 + ADR-0040 為 authoritative
- 主會話 v5.8 主檔 update 走 Sprint 1A-ε integration verify phase；屆時同步 patch v5.8 M13 文本對齊 ADR-0040
- 本 spec 不在 1A-δ 期間 patch v5.8 主檔（per scope）

### 7.7 Risk Caveat 3: enum variant 增刪 backward compat 風險

**Risk**：未來 Y3+ Binance trade enable 後可能需新增 enum variant（如 `BinanceSpot` / `OKXPerp` 等）；現有 serde + database stored enum 是否 backward compat?

**Mitigation**：
- 本 spec §3.5 FromStr IMPL 含明確 error handling（UnknownVenue）；database stored 不認識的 venue → fail-closed
- 未來 enum 擴展走「開新 ADR + 加 variant + 對應 5-gate schema」紀律（per ADR-0040 Decision 4 末段）
- E1 IMPL 期建議 serde derive 走 `#[serde(deny_unknown_fields)]` + `#[serde(rename_all = "snake_case")]`（per E1 dispatch packet 確認）

---

## §8 References

### 8.1 Parent specs (authoritative)

- **ADR-0040**：`srv/docs/adr/0040-multi-venue-gate-spec.md`（257 行；5 Decisions ADR 權威；本 spec 100% 對齊不違背）
- **ADR-0033**：`srv/docs/adr/0033-adr-0006-bybit-binance-amendment.md`（Binance market-data Y1 approved + Y3+ trade defer baseline；§Decision 2 已被 ADR-0040 amend Y2 → Y3+；§Decision 1/3/4 不變）
- **ADR-0006**：`srv/docs/adr/0006-bybit-only-exchange.md`（Bybit-only baseline 2026-04-03；thesis 不變）
- **v5.8 execution plan**：`srv/docs/execution_plan/2026-05-20--execution-plan-v5.8.md` §2 M13 line 460-487
- **PA dispatch consolidation**：`srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-21--v58_dispatch_consolidation.md` §Sprint 1A-δ line 159-167

### 8.2 Sibling specs

- **V116 placeholder spec**：`srv/docs/execution_plan/2026-05-21--v116_m13_asset_venue_dim_schema_spec.md`（同 Sprint 1A-δ deliverable；本 DESIGN spec land 後 V116 full DDL upgrade Y2+ phase）
- **M5 / M12 interface reservation specs**：（Sprint 1A-δ 同期 deliverable；隔壁 PA agent 負責）

### 8.3 Amendments

- **AMD-2026-05-21-01 autonomy-vs-human-final-review**：venue change always operator approval；本 spec §3.4 (c) + §5.5 (c) 對齊
- **AMD-2026-05-15-01 Stage 0R-4 graduated canary framework**：本 spec §5.1 venue stage 0R-4 引用

### 8.4 ADR cross-ref

- **ADR-0008 Decision Lease state machine**：`srv/docs/adr/0008-decision-lease-state-machine.md`（per-venue authorization 三元組為其 venue 維度延伸）
- **ADR-0030 Copy Trading evidence-gated**：本 spec §5.2 (e) Y2 末 Copy Trading evidence land 引用 4-Gate evaluation
- **ADR-0031 Framework expansion (Earn / Macro / On-chain)**：本 spec §1.5 on-chain read-only RPC query 例外不在 venue enum
- **ADR-0032 Earn asset movement Guardian**：本 spec §2.1 Spot Y1 active for Earn collateral 對齊
- **ADR-0034 M1 Decision Lease LAL**：本 spec §3.4 (c) + §5.5 (c) Agent 自主提案 venue change = invariant violation 對齊 LAL 4
- **ADR-0035 M5 online learning interface reservation**：interface reservation pattern 對齊 mirror precedent
- **ADR-0036 M8 anomaly detection**：無直接交集；M13 venue gate 與 M8 anomaly 在 IMPL 期 cross-validate（Sprint 8+ phase）
- **ADR-0037 M9 A/B framework**：M9 cluster 2 signal source swap 可能跨 venue alpha source；Y3+ Binance enable 後 M9 evaluation 必對齊 per-venue 5-gate
- **ADR-0038 M11 continuous counterfactual replay**：Binance market data Y2 onwards 為 M11 replay source（per ADR-0040 §Decision 3 (b)）；本 spec §3.2 對齊
- **ADR-0039 M12 OrderRouter trait**：M12 maker-vs-taker dispatch 在 Y3+ Binance enable 後必對齊 per-venue routing；Sprint 6+ IMPL phase

### 8.5 CLAUDE.md cross-ref

- **CLAUDE.md §一 Bybit-only**：字面立場保留；本 spec §1.5 + §3.3 DEX/Hyperliquid hardcode reject 對齊
- **CLAUDE.md §四 mainnet boundary**：本 spec §4 multi-venue gate inheritance 為其 venue 維度擴展
- **CLAUDE.md §二 16 根原則**：本 spec §9 16 根原則合規確認

### 8.6 Memory cross-ref

- **memory `feedback_chinese_only_comments`**：本 spec doc comment 範本 §2.4 + §3.5 對齊中文注釋
- **memory `project_openclaw_positioning`**：本 spec §1.5 對齊 OpenClaw 定位「Bybit-only baseline」立場
- **memory `feedback_v_migration_pg_dry_run`**：V116 placeholder full DDL Y2+ phase 必走 Linux PG empirical dry-run

### 8.7 Skill cross-ref

- **`srv/.claude/skills/16-root-principles-checklist`**：本 spec §9 16 根原則合規確認對齊

---

## §9 §二 16 根原則合規確認

per ADR-0040 §二 16 根原則合規確認，本 DESIGN spec 100% 對齊：

| # | 原則 | 是否相容 | 說明 |
|---|---|---|---|
| 1 | 單一寫入口 per venue | ✅ | Bybit 仍為唯一 active trading venue；Binance Y3+ enable 後 per-venue 5-gate 確保各 venue 單一寫入口；DEX/Hyperliquid enum-level 拒絕 |
| 2 | 讀寫分離 | ✅ | Binance Y2 仍 market-data only（純讀）；trading 走 Decision Lease + 5-gate（per venue） |
| 3 | AI 輸出 ≠ 命令 | ✅ | venue change 走 LAL 4（per ADR-0034）= Operator approval mandatory；Agent 無法自主提案 venue enable |
| 4 | 策略不繞風控 | ✅ | per-venue 5-gate 任一 fail → 該 venue 全部 outbound order freeze；策略無法繞 venue gate |
| 5 | **生存 > 利潤** | ✅ | Y3+ at earliest = 更保守時點，給 Y1+Y2 evidence 累積時間；defer 而非 push 是生存優先 |
| 6 | 失敗默認收縮 | ✅ | Y3+ evaluation 6 條件任一 fail → 繼續 defer；連續 3 cycle fail → 永久關閉 |
| 7 | 學習 ≠ Live | ✅ | Y2 期間 Binance market data 為 evidence accumulation；Y3+ enable 走 Decision Lease + 5-gate |
| 8 | 交易可解釋 | ✅ | per-venue authorization 三元組綁定（venue + environment + secret slot）+ Decision Lease 確保 venue 維度可追溯 |
| 9 | 雙重防線 | ✅ | per-venue 5-gate + 6 條 evaluation gate + LAL 4 operator approval = 多層 |
| 10 | 分離事實 / 推論 / 假設 | ✅ | Y3+ at earliest 反映「Y1 末 evidence 可能不足」是推論 + Operator D4 是事實；本 spec §1.3 明示兩者 |
| 11 | **Agent 自主在 P0/P1 內 / venue change 屬 LAL 3-4 protected** | ✅ | venue enable / disable 走 LAL 4（per ADR-0034）；Agent 在 venue 啟用後可在 P0/P1 內自主使用該 venue trading |
| 12 | 系統行為從證據演進 | ✅ | 6 條 evaluation criteria 全部 evidence-based（alpha sustained / counterfactual / Copy Trading land / AUM） |
| 13 | AI 調用 cost 感知 | ✅ | venue change 不涉及 LLM 調用 cost；governance cost 在 Operator 5-gate review session |
| 14 | 零外部成本 baseline | ✅ | Binance API 接入 free tier；secret slot 管理屬於本地運維；Sprint 1A-δ Rust enum IMPL 0 外部 cost |
| 15 | 多 agent 協作 formal | ✅ | venue gate 涉及 PM / BB / FA / E3 / Operator 多 role；per ADR-0040 Sign-off table |
| 16 | Portfolio > 孤立 trade | ✅ | Y3+ enable 後 D12 cap 80% 跨 venue 合計（per ADR-0033 §Decision 4 extend）；portfolio-level diversification |

---

## §10 Sign-off

| Role | Source | Date | Status |
|---|---|---|---|
| Operator | 主會話 PM dispatch via PM final verdict §四 D4（M13 Y2 Binance trade enable → Y3+ at earliest 已批；per ADR-0040 sign-off） | 2026-05-21 | ✅ APPROVED-pending-spec-land |
| PA | 本 DESIGN spec 起草（對齊 ADR-0040 5 Decisions + AssetClass enum 5 variants + Venue enum 5 variants + DEX/Hyperliquid hardcode reject + per-venue 5-gate inheritance + Y3+ 6 criteria + IMPL dispatch brief for E1 + 7 Open Q / Risk Caveats） | 2026-05-21 | ✅ Drafted v0 |
| E1 | `srv/rust/openclaw_types/src/asset_venue.rs` IMPL (4-6 hr scope per §6) + 7 AC verify | TBD（Sprint 1A-δ Day 2-3） | 🟡 PENDING |
| E2 | E2 review 3 重點（per §6.5）+ trybuild compile_fail test 驗 | TBD（Sprint 1A-δ Day 3-4） | 🟡 PENDING |
| E4 | Cargo build + cargo test Mac + Linux 跨平台 regression（per AC-1） | TBD（Sprint 1A-δ Day 4） | 🟡 PENDING |
| PA Sprint 1A-ε | Cross-ADR consistency audit（11 ADR 跨引用 + v5.8 §2 M13 文本 patch + Open Q 1 PositionAggregator 既有 Rust path 決定） | TBD（Sprint 1A-ε） | 🟡 PENDING |
| PM Sprint 1A-δ closure | Sprint 1A-δ deliverable sign-off | TBD（Sprint 1A-δ end） | 🟡 PENDING |

---

**END M13 AssetClass / Venue Enum Interface Reservation DESIGN spec v0（Sprint 1A-δ；對齊 ADR-0040 5 Decisions；待 E1 stub IMPL + PA Sprint 1A-ε cross-ADR audit 後可升 SPEC-DRAFT-V1）**

---

Sub-agent dispatch: PA Sprint 1A-δ M13 track
Completion: 2026-05-21
