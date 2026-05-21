//! M13 AssetClass / Venue enum interface reservation acceptance tests。
//! 對應 spec：srv/docs/execution_plan/2026-05-21--m13_asset_class_venue_design_spec.md §6.2 AC-1..AC-7。
//!
//! 測試重點：
//!   - 5 個 AssetClass + 5 個 Venue variant serde JSON round-trip。
//!   - Display + FromStr round-trip 穩定。
//!   - "dex" / "Dex" / "DEX" / "hyperliquid" 等 string literal 必被 FromStr 拒絕（per ADR-0040 Decision 4）。
//!   - 未知 venue 字串走 UnknownVenue path。
//!
//! 紅線：不寫 mock 隱蔽邏輯 / 不擴 shared_types.json golden / 不寫 venue dispatch method body。

use std::str::FromStr;

use openclaw_types::{AssetClass, Venue, VenueParseError};

/// AC-1：AssetClass 5 variant serde JSON round-trip 對等。
#[test]
fn test_asset_class_serde_round_trip() {
    let variants = [
        AssetClass::Perp,
        AssetClass::Spot,
        AssetClass::Option,
        AssetClass::Earn,
        AssetClass::Structured,
    ];
    for v in variants {
        let json = serde_json::to_string(&v).expect("serialize AssetClass");
        let back: AssetClass = serde_json::from_str(&json).expect("deserialize AssetClass");
        assert_eq!(back, v, "AssetClass round-trip mismatch for {:?}", v);
    }
}

/// AC-2：Venue 5 variant serde JSON round-trip 對等（不含 Dex / Hyperliquid）。
#[test]
fn test_venue_serde_round_trip() {
    let variants = [
        Venue::BybitPerp,
        Venue::BybitSpot,
        Venue::BybitOption,
        Venue::BinancePerp,
        Venue::BinanceOption,
    ];
    for v in variants {
        let json = serde_json::to_string(&v).expect("serialize Venue");
        let back: Venue = serde_json::from_str(&json).expect("deserialize Venue");
        assert_eq!(back, v, "Venue round-trip mismatch for {:?}", v);
    }
}

/// AC-3：Venue Display 採 snake_case；輸出格式穩定（與 Bybit / Binance category 慣例對齊）。
#[test]
fn test_venue_display_format() {
    assert_eq!(format!("{}", Venue::BybitPerp), "bybit_perp");
    assert_eq!(format!("{}", Venue::BybitSpot), "bybit_spot");
    assert_eq!(format!("{}", Venue::BybitOption), "bybit_option");
    assert_eq!(format!("{}", Venue::BinancePerp), "binance_perp");
    assert_eq!(format!("{}", Venue::BinanceOption), "binance_option");

    // 2 次調用結果一致（per spec §6.2 AC-6 Display trait 穩定）。
    assert_eq!(
        format!("{}", Venue::BybitPerp),
        format!("{}", Venue::BybitPerp)
    );
}

/// AC-4：FromStr 5 variant 都通過（接受 PascalCase + snake_case 兩種 input）。
#[test]
fn test_venue_fromstr_known() {
    // snake_case input（與 Display 對齊 → round-trip 可行）
    assert_eq!(Venue::from_str("bybit_perp").unwrap(), Venue::BybitPerp);
    assert_eq!(Venue::from_str("bybit_spot").unwrap(), Venue::BybitSpot);
    assert_eq!(Venue::from_str("bybit_option").unwrap(), Venue::BybitOption);
    assert_eq!(Venue::from_str("binance_perp").unwrap(), Venue::BinancePerp);
    assert_eq!(
        Venue::from_str("binance_option").unwrap(),
        Venue::BinanceOption
    );

    // PascalCase input（與 enum 名稱對齊）
    assert_eq!(Venue::from_str("BybitPerp").unwrap(), Venue::BybitPerp);
    assert_eq!(
        Venue::from_str("BinanceOption").unwrap(),
        Venue::BinanceOption
    );

    // Display + FromStr round-trip 可行。
    for v in [
        Venue::BybitPerp,
        Venue::BybitSpot,
        Venue::BybitOption,
        Venue::BinancePerp,
        Venue::BinanceOption,
    ] {
        let s = format!("{}", v);
        let back = Venue::from_str(&s).expect("round-trip parse");
        assert_eq!(back, v, "FromStr round-trip mismatch for {:?}", v);
    }
}

/// AC-5：Dex / dex / DEX / uniswap / gmx / dydx 必被 FromStr 拒絕，走 DeniedByADR0040 明示路徑。
#[test]
fn test_venue_fromstr_dex_rejected() {
    for input in ["dex", "Dex", "DEX", "uniswap", "Uniswap", "GMX", "dydx"] {
        let err = Venue::from_str(input)
            .err()
            .unwrap_or_else(|| panic!("expected error for input {:?}", input));
        match err {
            VenueParseError::DeniedByADR0040(payload) => {
                assert_eq!(payload, input, "DeniedByADR0040 payload should echo input");
            }
            other => panic!(
                "input {:?} expected DeniedByADR0040, got {:?}",
                input, other
            ),
        }
    }
}

/// AC-6：Hyperliquid 各種大小寫必被 FromStr 拒絕，走 DeniedByADR0040 明示路徑。
#[test]
fn test_venue_fromstr_hyperliquid_rejected() {
    for input in ["hyperliquid", "Hyperliquid", "HYPERLIQUID", "HyperLiquid"] {
        let err = Venue::from_str(input)
            .err()
            .unwrap_or_else(|| panic!("expected error for input {:?}", input));
        match err {
            VenueParseError::DeniedByADR0040(payload) => {
                assert_eq!(payload, input);
            }
            other => panic!(
                "input {:?} expected DeniedByADR0040, got {:?}",
                input, other
            ),
        }
    }
}

/// AC-7：未知 venue（typo / 未開 ADR 的 venue）走 UnknownVenue 路徑，不走拒絕路徑。
#[test]
fn test_venue_fromstr_unknown() {
    for input in ["foo", "", "okx", "coinbase", "bybit_perp_v2", "binance"] {
        let err = Venue::from_str(input)
            .err()
            .unwrap_or_else(|| panic!("expected error for input {:?}", input));
        match err {
            VenueParseError::UnknownVenue(payload) => {
                assert_eq!(payload, input);
            }
            other => panic!("input {:?} expected UnknownVenue, got {:?}", input, other),
        }
    }
}
