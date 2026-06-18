//! AssetClass + Venue enum stub — M13 multi-asset/multi-venue interface reservation per ADR-0040
//! M13 多 asset class / 多 venue 介面預留 enum 樁；per ADR-0040 Decision 4 + 5。
//!
//! MODULE_NOTE
//! 模塊用途：為 v5.8 §2 M13 multi-asset class / multi-venue capacity 預留型別介面；
//!           純 enum + Display + FromStr + serde derive，不含 venue dispatch / trade routing / method body。
//! 主要型別：`AssetClass`（5 variants）/ `Venue`（5 variants）/ `VenueParseError`。
//! 依賴：serde（已在 crate dep）；無 thiserror（保持 dependency 乾淨，per Cargo.toml LG-2 dev-deps 紀律）。
//! 硬邊界：
//!   - DEX / Hyperliquid 不在 `Venue` enum 中保留 slot（per ADR-0040 Decision 4 + ADR-0033 Decision 3 + CLAUDE.md §一 Bybit-only）；
//!     FromStr 對應 string literal 走 `VenueParseError::DeniedByADR0040` 明示拒絕路徑，不可繞 enum check。
//!   - Sprint 1A-δ 介面預留階段：禁實作 method body 含 trading / routing / venue dispatch；違反 = scope creep。
//!   - 未來開放新 venue（如 OKX / Coinbase）必先開新 ADR amend ADR-0040 + 新 enum variant + per-venue 5-gate schema。
//!
//! 對應 spec：srv/docs/execution_plan/2026-05-21--m13_asset_class_venue_design_spec.md §2 §3 §6。

use serde::{Deserialize, Serialize};

/// OpenClaw 交易引擎的 asset class 分類。
///
/// Per v5.8 §2 M13 + ADR-0040 Decision 4 venue-asset taxonomy。
/// 為什麼：Y1 期間 Perp / Spot / Option / Earn 4 條 asset 線並行（per v5.8 §2 M13 line 466-467）；
///         Structured 預留 Y3+ Tier C+ AUM $75k+ 啟用槽，避免未來再開 ADR 加 variant。
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum AssetClass {
    /// Y1 active：永續合約（Bybit USDT 永續）。對應 5 baseline strategies hot path。
    Perp,
    /// Y1 active：現貨（Bybit 現貨，主要作 Earn 抵押用）。對應 ADR-0032 Earn asset movement Guardian。
    Spot,
    /// Y1 active：選擇權（Bybit options，僅 C13 VRP 策略用）。對應 v5.8 §2 Sprint 5 C13-VRP IMPL。
    Option,
    /// Y1 active：理財收益產品（Bybit Earn 系列）。對應 ADR-0031 Framework expansion Earn lane。
    Earn,
    /// Y3+ only：結構性產品（Dual Asset / Snowball / Auto-Compound 等）。
    /// 啟用 gate：per v5.8 §5 capital-tier ladder Tier C+ AUM ≥ $75k sustained 30d + Operator 仲裁。
    /// 為什麼是 Y3+ 而非 Y2：Structured risk profile 顯著高於 Earn，保守採 Y3+ reserved 不在 Y2 自動 active。
    Structured,
}

impl std::fmt::Display for AssetClass {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        // 採用 snake_case 與 agent.rs / state.rs 既有 Display 風格對齊。
        let s = match self {
            Self::Perp => "perp",
            Self::Spot => "spot",
            Self::Option => "option",
            Self::Earn => "earn",
            Self::Structured => "structured",
        };
        write!(f, "{}", s)
    }
}

/// OpenClaw 交易引擎的 trading venue 分類。
///
/// Per ADR-0040 Decision 4 venue enum hardcode + Decision 1 Y3+ Binance trade defer。
///
/// **DEX / Hyperliquid 硬編碼拒絕**：per ADR-0033 Decision 3 + CLAUDE.md §一 Bybit-only；
/// 不在 enum 中保留 slot；未來開放新 venue 必開新 ADR amend ADR-0040 + 新增 variant。
///
/// 為什麼 enum-level rejection 比 string literal rejection 強：string literal venue 容易繞過
/// 編譯期 venue check（如 PR 中混入 `"hyperliquid"` 而未 ADR review）；enum-driven 演進 = 受控路徑
/// （per ADR-0040 Decision 4 末段）。
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum Venue {
    /// Y1 active：Bybit USDT 永續合約。對應 5 baseline strategies Live A/B hot path。
    /// 5-gate authorization 路徑：`$OPENCLAW_SECRETS_DIR/api_key`（Bybit original path）。
    BybitPerp,
    /// Y1 active：Bybit 現貨交易（Earn collateral routing）。共用 Bybit secret slot。
    BybitSpot,
    /// Y1 active：Bybit 選擇權（僅 C13 VRP 策略用）。共用 Bybit secret slot。
    BybitOption,
    /// Y2 market-data only / Y3+ trade defer per ADR-0040 Decision 1（amend ADR-0033 §Decision 2 時點）。
    /// Y2 期間禁止：order placement / authentication beyond market-data API / asset transfer。
    /// Y3+ trade 啟用必通過 6 條 evaluation criteria（per ADR-0040 Decision 3）。
    /// 5-gate authorization 路徑：`$OPENCLAW_SECRETS_DIR/external/binance/api_key`（per H-21 external secret slot policy）。
    BinancePerp,
    /// Y3+ only per v5.8 §2 M13 line 470「Y3+: + Binance options (when AUM justifies)」。
    /// 與 BinancePerp 差異：無 Y2 market-data 階段；Y3+ enable 走獨立 ADR + 獨立 5-gate review，
    /// 不繼承 BinancePerp Tier B 通過狀態。
    BinanceOption,
}

impl std::fmt::Display for Venue {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        // 採 snake_case 對齊 Bybit / Binance category API 慣例（linear / spot / option），
        // 並對齊 agent.rs MessageType / state.rs Display 既有風格。
        let s = match self {
            Self::BybitPerp => "bybit_perp",
            Self::BybitSpot => "bybit_spot",
            Self::BybitOption => "bybit_option",
            Self::BinancePerp => "binance_perp",
            Self::BinanceOption => "binance_option",
        };
        write!(f, "{}", s)
    }
}

impl std::str::FromStr for Venue {
    type Err = VenueParseError;

    fn from_str(s: &str) -> Result<Self, Self::Err> {
        // 為避免 FromStr 大小寫敏感造成 venue id 亂寫，先以 lower-case 規範化比對。
        // 同時接受 PascalCase（與 enum 名稱對齊）與 snake_case（與 Display + API category 對齊）。
        let normalized = s.trim().to_ascii_lowercase();
        match normalized.as_str() {
            "bybitperp" | "bybit_perp" => Ok(Self::BybitPerp),
            "bybitspot" | "bybit_spot" => Ok(Self::BybitSpot),
            "bybitoption" | "bybit_option" => Ok(Self::BybitOption),
            "binanceperp" | "binance_perp" => Ok(Self::BinancePerp),
            "binanceoption" | "binance_option" => Ok(Self::BinanceOption),
            // DEX / Hyperliquid hardcode 拒絕 per ADR-0040 Decision 4 + ADR-0033 Decision 3。
            // 用 DeniedByADR0040 明示拒絕路徑，便於 IMPL layer fail-closed log 區分
            // 「未知 venue（typo / 未來 venue 未開 ADR）」與「治理拒絕 venue」。
            "dex" | "uniswap" | "gmx" | "dydx" | "hyperliquid" => {
                Err(VenueParseError::DeniedByADR0040(s.to_string()))
            }
            _ => Err(VenueParseError::UnknownVenue(s.to_string())),
        }
    }
}

/// Venue parse error variant set。
///
/// 為什麼分兩 variant：應用層 fail-closed log 需區分
/// 「typo / 未來 venue 未開 ADR（UnknownVenue）」與
/// 「治理硬編碼拒絕 venue（DeniedByADR0040）」；
/// 後者必觸發 governance review，前者僅需返回 input。
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum VenueParseError {
    /// 未知 venue：未匹配任何已知 variant，也未在 ADR-0040 拒絕清單。
    /// 處理建議：應用層 log + fail-closed；若未來需開放，必走新 ADR 路徑。
    UnknownVenue(String),
    /// 治理硬編碼拒絕：DEX / Hyperliquid 等 per ADR-0040 Decision 4 + ADR-0033 Decision 3。
    /// 處理建議：應用層必觸發 governance alert；不可在沒有新 ADR amend 的情況下繞過。
    DeniedByADR0040(String),
}

impl std::fmt::Display for VenueParseError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::UnknownVenue(s) => write!(f, "unknown venue: '{}'", s),
            Self::DeniedByADR0040(s) => write!(
                f,
                "venue '{}' is hardcode-rejected per ADR-0040 Decision 4 (DEX / Hyperliquid not approved)",
                s
            ),
        }
    }
}

impl std::error::Error for VenueParseError {}
