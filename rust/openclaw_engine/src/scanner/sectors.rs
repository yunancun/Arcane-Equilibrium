//! Static sector and stablecoin classification for scanner universe filtering.
//! 掃描器篩選用的靜態板塊與穩定幣分類。
//!
//! MODULE_NOTE (EN): Pure lookup tables — no I/O, no dependencies beyond &str.
//!   Sector assignments are best-effort; new symbols default to "other".
//!   Update SECTOR_MAP entries as the crypto landscape evolves.
//! MODULE_NOTE (中): 純查詢表，無 I/O，無外部依賴。
//!   板塊分配為盡力而為；未知交易對默認歸類為 "other"。
//!   隨加密貨幣生態演進按需更新 SECTOR_MAP。

/// Stablecoin base currencies to exclude from the tradeable universe.
/// Bybit linear perps on stablecoins have near-zero volatility and provide no edge.
/// 從可交易品類中排除的穩定幣基礎貨幣。
/// 穩定幣的 Bybit linear perp 波動率接近零，無邊際優勢。
pub const STABLECOIN_BASES: &[&str] = &[
    "USDC", "BUSD", "TUSD", "FDUSD", "USDE", "USDD", "FRAX", "DAI", "USDP", "GUSD", "PYUSD",
    "USDT", // USDTUSDT edge case
];

/// Map a symbol's base currency to a market sector string.
/// Returns "other" for unknown symbols.
/// 將交易對的基礎貨幣映射到市場板塊字串。
/// 未知交易對返回 "other"。
pub fn symbol_sector(base: &str) -> &'static str {
    match base {
        // Layer 1 infrastructure / L1 基礎設施
        "BTC" | "ETH" | "SOL" | "ADA" | "AVAX" | "DOT" | "ATOM" | "NEAR" | "APT" | "SUI"
        | "SEI" | "INJ" | "TIA" | "ALGO" | "EGLD" | "FTM" | "ONE" | "CELO" | "KAVA"
        | "FLOW" | "HBAR" | "ICP" | "THETA" | "VET" | "XLM" | "XRP" => "l1_infra",

        // Meme coins / 迷因幣
        "DOGE" | "SHIB" | "PEPE" | "FLOKI" | "BONK" | "WIF" | "MEME" | "NEIRO" | "MOG"
        | "POPCAT" | "BRETT" | "TURBO" | "BOME" | "MYRO" | "SLERF" | "PNUT" | "GOAT"
        | "MOODENG" | "FWOG" => "meme",

        // Oracle / data networks / 預言機 / 數據網絡
        "LINK" | "BAND" | "DIA" | "API3" | "TRB" | "UMA" | "REN" | "PYTH" | "SUPRA" => {
            "oracle"
        }

        // DEX / DeFi AMM / 去中心化交易所
        "UNI" | "SUSHI" | "CRV" | "BAL" | "GMX" | "GNS" | "DYDX" | "PERP" | "RBN"
        | "OSMO" | "ASTRO" | "JUP" | "ORCA" | "RAY" | "DRIFT" => "defi_dex",

        // DeFi lending / yield / 借貸 / 收益
        "AAVE" | "COMP" | "MKR" | "SNX" | "YFI" | "PENDLE" | "ENA" | "ETHFI" | "RETH"
        | "FRXETH" | "LIDO" | "LDO" | "RPL" | "SFRX" => "defi_lending",

        // Gaming / NFT / Metaverse / 遊戲 / NFT / 元宇宙
        "AXS" | "SAND" | "MANA" | "ENJ" | "IMX" | "GALA" | "MAGIC" | "LOOKS" | "BLUR"
        | "BEAM" | "RON" | "YGG" | "PYR" | "ILV" | "GODS" | "MC" | "SLP" => "gaming_nft",

        // Storage / compute / 存儲 / 算力
        "FIL" | "AR" | "STORJ" | "ANKR" | "RLC" | "GLM" | "RENDER" | "AKT" | "IO" | "TAO"
        | "GRT" | "LPT" | "NMR" => "storage_compute",

        // Payments / L1 payment chains / 支付 / 支付型 L1
        "XRP" | "LTC" | "BCH" | "DASH" | "ZEC" | "XMR" | "NANO" | "RVN" | "BTT" | "TRX"
        | "XEM" | "ZIL" => "payments_l1",

        // L2 scaling / rollups / L2 擴容 / Rollup
        "MATIC" | "POL" | "ARB" | "OP" | "STRK" | "MANTA" | "METIS" | "BOBA" | "ZKS"
        | "ZKSYNC" | "SCROLL" | "LINEA" | "BLAST" | "MODE" | "BASE" => "l2_scaling",

        // Exchange tokens / CEX native / 交易所原生代幣
        "BNB" | "OKB" | "HT" | "KCS" | "FTT" | "CRO" | "GT" | "MX" | "WBT" => "exchange",

        // AI / ML infrastructure / AI / 機器學習基礎設施
        "FET" | "AGIX" | "OCEAN" | "RNDR" | "WLD" | "ARKM" | "BITTENSOR" | "GRASS"
        | "AIOZ" => "ai_infra",

        // Privacy / 隱私
        "ZEC" | "XMR" | "SCRT" | "ROSE" | "NYM" | "PHA" => "privacy",

        // Infrastructure / middleware / 基礎設施 / 中間件
        "BAND" | "AXL" | "WORMHOLE" | "W" | "PYTH" | "JITO" | "JTO" | "EIGEN" => {
            "infrastructure"
        }

        // Default / 默認
        _ => "other",
    }
}

/// Extract the base currency from a USDT-margined symbol.
/// Returns None if the symbol does not end with "USDT".
/// 從 USDT 結算交易對中提取基礎貨幣。
/// 若交易對不以 "USDT" 結尾則返回 None。
pub fn base_from_usdt_symbol(symbol: &str) -> Option<&str> {
    symbol.strip_suffix("USDT")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_sector_btc_is_l1() {
        assert_eq!(symbol_sector("BTC"), "l1_infra");
    }

    #[test]
    fn test_sector_doge_is_meme() {
        assert_eq!(symbol_sector("DOGE"), "meme");
    }

    #[test]
    fn test_sector_unknown_is_other() {
        assert_eq!(symbol_sector("UNKNWNCOIN"), "other");
    }

    #[test]
    fn test_stablecoin_bases_usdc() {
        assert!(STABLECOIN_BASES.contains(&"USDC"));
        assert!(STABLECOIN_BASES.contains(&"BUSD"));
        assert!(STABLECOIN_BASES.contains(&"TUSD"));
    }

    #[test]
    fn test_base_from_usdt_symbol_btcusdt() {
        assert_eq!(base_from_usdt_symbol("BTCUSDT"), Some("BTC"));
    }

    #[test]
    fn test_base_from_usdt_symbol_non_usdt() {
        assert_eq!(base_from_usdt_symbol("BTCETH"), None);
    }
}
