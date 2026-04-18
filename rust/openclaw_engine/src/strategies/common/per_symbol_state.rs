//! `PerSymbolState<S>` — thin generic wrapper around `HashMap<String, S>`.
//! `PerSymbolState<S>` — 對 `HashMap<String, S>` 的輕量泛型包裝。
//!
//! MODULE_NOTE (EN): Factored out of the 4 strategy modules to give a single
//!   symbol-keyed container type. Pass-through API on purpose — strategies
//!   previously typed `HashMap<String, T>` directly, so existing call sites
//!   (and tests) migrate by renaming only. No ordering guarantees because the
//!   backing store is `HashMap` — callers MUST NOT assume iteration order.
//! MODULE_NOTE (中): 從 4 個策略模組抽離，統一以 symbol 為鍵的容器。
//!   API 刻意做成 pass-through，原本寫 `HashMap<String, T>` 的呼叫點與測試
//!   只需改名即可。底層是 `HashMap`，迭代順序不穩定，呼叫方不得依賴順序。

use std::collections::HashMap;

/// Symbol-keyed state container with a small, opinionated API.
/// 以 symbol 為鍵的狀態容器，API 刻意精簡。
///
/// Most methods have no `S: Default` bound so callers with custom structs
/// (e.g. `FundingPosition`) can use the container directly; only
/// `get_or_init` requires `S: Default` because it materializes a new entry
/// on first access — mirrors the `HashMap.entry(sym).or_insert_with(...)`
/// pattern in `bb_breakout::on_tick` where 4 HashMaps each get a "lazy
/// default" on first-tick activation.
/// 多數方法不帶 `S: Default` 約束，讓像 `FundingPosition` 這類自訂 struct 也能直接使用；
/// 只有 `get_or_init` 需要 `S: Default`（對應 `bb_breakout::on_tick` 中 4 個
/// HashMap 原本各自 lazy 初始化的寫法）。
#[derive(Debug, Clone)]
pub struct PerSymbolState<S> {
    state: HashMap<String, S>,
}

impl<S> Default for PerSymbolState<S> {
    fn default() -> Self {
        Self {
            state: HashMap::new(),
        }
    }
}

impl<S> PerSymbolState<S> {
    /// Build an empty per-symbol map. / 建立空的逐 symbol 映射。
    pub fn new() -> Self {
        Self {
            state: HashMap::new(),
        }
    }

    /// Insert a value for `symbol`; returns the previous value if one existed.
    /// 為 `symbol` 插入值，若先前已有值則回傳之。
    pub fn insert(&mut self, symbol: String, value: S) -> Option<S> {
        self.state.insert(symbol, value)
    }

    /// Immutable lookup. / 不可變查找。
    pub fn get(&self, symbol: &str) -> Option<&S> {
        self.state.get(symbol)
    }

    /// Mutable lookup. / 可變查找。
    pub fn get_mut(&mut self, symbol: &str) -> Option<&mut S> {
        self.state.get_mut(symbol)
    }

    /// `true` if this symbol has any entry. / 該 symbol 是否有條目。
    pub fn contains_key(&self, symbol: &str) -> bool {
        self.state.contains_key(symbol)
    }

    /// Remove and return any entry for `symbol`. / 移除並回傳該 symbol 的條目。
    pub fn remove(&mut self, symbol: &str) -> Option<S> {
        self.state.remove(symbol)
    }

    /// Drop every symbol. / 清空所有 symbol。
    pub fn clear(&mut self) {
        self.state.clear();
    }

    /// `true` when no symbols are tracked. / 無任何 symbol 時為 `true`。
    pub fn is_empty(&self) -> bool {
        self.state.is_empty()
    }

    /// Number of tracked symbols. / 追蹤的 symbol 數量。
    pub fn len(&self) -> usize {
        self.state.len()
    }

    /// Borrow-iterator of `(symbol, state)`. No ordering guarantee.
    /// 回傳 `(symbol, state)` 的借用迭代器，順序不保證。
    pub fn iter(&self) -> impl Iterator<Item = (&str, &S)> {
        self.state.iter().map(|(k, v)| (k.as_str(), v))
    }
}

impl<S: Default> PerSymbolState<S> {
    /// Fetch the entry, materializing `S::default()` if the symbol was unseen.
    /// Only available when `S: Default`; other strategies construct entries via
    /// `insert` instead.
    /// 取得該 symbol 的條目，若不存在則以 `S::default()` 建立後回傳可變參考。
    /// 僅當 `S: Default` 時可用；不實作 Default 的型別需用 `insert` 建立條目。
    pub fn get_or_init(&mut self, symbol: &str) -> &mut S {
        self.state.entry(symbol.to_string()).or_default()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[derive(Debug, Clone, Default, PartialEq)]
    struct Counter {
        value: u32,
    }

    #[test]
    fn test_get_or_init_materializes_default() {
        // First access creates via Default; repeated access returns existing entry.
        // 首次存取以 Default 建立；重複存取回傳既有條目。
        let mut s: PerSymbolState<Counter> = PerSymbolState::new();
        assert!(s.is_empty());
        s.get_or_init("BTC").value = 7;
        assert_eq!(s.get("BTC"), Some(&Counter { value: 7 }));
        // get_or_init does not reset / 不會重置
        assert_eq!(s.get_or_init("BTC").value, 7);
    }

    #[test]
    fn test_insert_get_remove_clear() {
        // Round-trip the four fundamental ops. / 基本 4 個操作來回驗證。
        let mut s: PerSymbolState<Counter> = PerSymbolState::new();
        assert_eq!(s.insert("ETH".into(), Counter { value: 3 }), None);
        assert_eq!(s.get("ETH"), Some(&Counter { value: 3 }));
        assert!(s.contains_key("ETH"));
        assert_eq!(s.len(), 1);
        assert_eq!(s.remove("ETH"), Some(Counter { value: 3 }));
        assert!(!s.contains_key("ETH"));
        s.insert("BTC".into(), Counter { value: 1 });
        s.insert("SOL".into(), Counter { value: 2 });
        assert_eq!(s.len(), 2);
        s.clear();
        assert!(s.is_empty());
    }

    #[test]
    fn test_iter_unordered_collects_all_entries() {
        // Iteration visits every entry; order is intentionally NOT asserted
        // (HashMap is unordered by construction).
        // iter 會訪問全部條目；刻意不驗證順序（HashMap 不保證順序）。
        let mut s: PerSymbolState<Counter> = PerSymbolState::new();
        s.insert("A".into(), Counter { value: 1 });
        s.insert("B".into(), Counter { value: 2 });
        s.insert("C".into(), Counter { value: 3 });
        let mut seen: Vec<(String, u32)> =
            s.iter().map(|(k, v)| (k.to_string(), v.value)).collect();
        seen.sort(); // compare sorted → don't depend on HashMap order
        assert_eq!(
            seen,
            vec![
                ("A".to_string(), 1),
                ("B".to_string(), 2),
                ("C".to_string(), 3),
            ]
        );
    }

    #[test]
    fn test_empty_helpers() {
        // is_empty / len / get on an unseen symbol all behave like a fresh HashMap.
        // is_empty/len/未命中查詢 行為與新 HashMap 一致。
        let s: PerSymbolState<Counter> = PerSymbolState::new();
        assert!(s.is_empty());
        assert_eq!(s.len(), 0);
        assert!(s.get("GHOST").is_none());
        assert!(!s.contains_key("GHOST"));
    }

    #[test]
    fn test_get_mut_allows_in_place_update() {
        // get_mut backs the "squeeze_detected_ms.entry(sym).or_insert(ts)" style
        // of in-place updates that bb_breakout relies on.
        // get_mut 支援 bb_breakout 依賴的 in-place 更新模式。
        let mut s: PerSymbolState<Counter> = PerSymbolState::new();
        s.insert("XRP".into(), Counter { value: 10 });
        if let Some(c) = s.get_mut("XRP") {
            c.value += 5;
        }
        assert_eq!(s.get("XRP"), Some(&Counter { value: 15 }));
    }
}
