# Session 3 工程日誌 — P2 Rust 7 項修復（2026-04-12）

## 概要 / Summary

全程序鏈審計 P2 優先級中 7 項 Rust 修復全部完成。涵蓋策略參數可配化、費率解耦、時間戳過期機制、負 edge 拒絕、typed event enum、O(1) 去重。

All 7 Rust P2 audit fixes completed. Covers strategy param configurability, fee rate decoupling, timestamp-based expiry, negative edge rejection, typed event enum, and O(1) dedup.

---

## 完成項目 / Completed Items

### FIX-24 — bb_reversion RSI 閾值可配（commit `84f00eb`）
- **問題**：RSI 超買/超賣閾值硬編碼 30/70，Agent 無法調整
- **修復**：`rsi_oversold` / `rsi_overbought` 加入 `BbReversionParams`（雙層：strategy-internal + TOML config）
- **驗證**：serde default 向後兼容 + ParamRange agent-adjustable（step=5.0）+ validation [5,45]/[55,95]
- **文件**：`bb_reversion.rs` · `strategies/mod.rs`

### FIX-25 — grid_trading fee_rate 字段（commit `84f00eb`）
- **問題**：`const FEE_PCT = 0.00055` 硬編碼，不同交易對/等級費率不同
- **修復**：`DEFAULT_FEE_PCT` 常量 + `fee_rate: f64` struct 字段 + `set_fee_rate()` setter
- **驗證**：4 個構造函數全部初始化 `fee_rate: DEFAULT_FEE_PCT`；OU floor 計算使用 `self.fee_rate`
- **文件**：`grid_trading.rs`

### FIX-26 — bb_breakout squeeze 時間戳過期（commit `84f00eb`）
- **問題**：`was_in_squeeze: HashMap<String, bool>` 無過期機制，歷史 squeeze 狀態永久殘留
- **修復**：`squeeze_detected_ms: HashMap<String, u64>` + `squeeze_expiry_ms: u64`（default 30min）
- **設計**：`entry().or_insert()` 只記錄首次偵測時間；expansion 檢查 `ts < detected + expiry`
- **驗證**：TOML serde default 向後兼容 + rejection rollback 正確處理 `Option<u64>`
- **文件**：`bb_breakout.rs` · `strategies/mod.rs`

### FIX-27 — kelly_sizer 負 edge 拒絕（commit `84f00eb`）
- **問題**：Kelly < 0 時返回 `balance * 0.01 / price`（1% fallback），主動交易虧損 edge
- **修復**：`kelly_full <= 0.0` → `return 0.0`（拒絕開倉）
- **驗證**：`test_negative_kelly_rejects` 斷言 `qty == 0.0`
- **文件**：`kelly_sizer.rs`

### FIX-28 — intent_processor account_leverage 字段（commit `84f00eb`）
- **問題**：Guardian risk check 硬編碼 `leverage: 1.0`，exchange 模式下實際槓桿不同
- **修復**：`account_leverage: f64` 字段（default 1.0）+ `set_account_leverage()` setter（`.max(1.0)` 防禦）
- **驗證**：`router.rs` 4 處 `leverage: 1.0` 全部改為 `self.account_leverage`
- **文件**：`intent_processor/mod.rs` · `intent_processor/router.rs`

### FIX-31 — PriceEventKind typed enum（commit `84f00eb`）
- **問題**：事件類型靠 `metadata["type"]` 字串匹配，無編譯時保證
- **修復**：`PriceEventKind` enum（7 variants：Trade/Orderbook/Ticker/Liquidation/PriceLimit/AdlNotice/RestPoll）+ `event_kind: Option<PriceEventKind>` 向後兼容字段
- **設計**：雙路徑 — typed enum + legacy metadata 並存；ws_client 6 處 parse 函數全部設置 typed 字段
- **驗證**：`#[serde(default)]` 舊 JSON 反序列化不會斷；on_tick ADL 檢查 + aggregator dispatch 改用 typed match
- **文件**：`price.rs` · `lib.rs` · `ws_client.rs` · `tick_pipeline/mod.rs` · `on_tick.rs` · `on_tick_helpers.rs` · `decision_context_producer.rs`

### FIX-33 — event_consumer exec_id 去重 O(1)（commit `84f00eb`）
- **問題**：`VecDeque<String>.iter().any()` O(n) 線性掃描，500 容量上限下每 tick 最壞 500 次比較
- **修復**：`HashSet<String>` O(1) lookup + `VecDeque<String>` 維持 FIFO 淘汰順序
- **驗證**：insert 雙寫 set+deque；eviction 時 `pop_front()` → `set.remove()`；`const MAX_SEEN_EXEC_IDS = 500`
- **文件**：`event_consumer/mod.rs`

---

## 驗證結果 / Verification

| 步驟 | 結果 |
|------|------|
| `cargo build -p openclaw_engine` | clean, 0 warnings |
| `cargo test -p openclaw_engine --lib` | **965 passed** |
| `cargo test -p openclaw_core --lib` | **366 passed** |
| `cargo test -p openclaw_types --lib` | **27 passed** |
| `cargo test -p openclaw_engine --test '*'` | **29 passed** (e2e) |
| `python3 -m pytest program_code/` | **2852 passed**, 5 skipped |
| E2 Code Review (sub-agent) | **PASS** — 0 P0, 0 P1, all bilingual/compat/security checks passed |
| **Total** | **4239 passed, 0 failed** |

---

## Commits

| Hash | 描述 |
|------|------|
| `84f00eb` | fix(audit-P2): 7 Rust fixes — configurable params, typed events, O(1) dedup |
| `78210d1` | docs: update TODO + CHANGELOG for P2 Rust 7 fixes |

---

## 技術決策 / Technical Decisions

1. **雙層 params 模式**（FIX-24/26）：strategy-internal params struct 與 TOML config params struct 同名不同模組（`bb_reversion::BbReversionParams` vs `strategies::BbReversionParams`）。兩層都需更新 + factory `create_with_params()` 接線。

2. **時間戳過期 vs TTL map**（FIX-26）：選擇 `HashMap<String, u64>` + 手動 expiry check，而非引入 TTL crate。理由：squeeze 狀態與 on_tick 生命週期綁定，不需要後台清理。

3. **typed enum 向後兼容**（FIX-31）：`Option<PriceEventKind>` + `#[serde(default)]` 確保舊 JSON（無 `event_kind` 欄位）反序列化正常。legacy `metadata["type"]` 保留但消費端改用 typed match。

4. **HashSet + VecDeque 雙結構**（FIX-33）：比 `IndexSet` 更輕量（無額外 crate），insert O(1) + lookup O(1) + eviction O(1) amortized。

---

## 未完成 / Remaining P2 Items (18)

| 類別 | 數量 | 項目 |
|------|------|------|
| Rust file splits | 5 | FIX-08, FIX-21, FIX-23, FIX-36, FIX-37 |
| ML/DB | 2 | FIX-34, FIX-35 |
| GUI/UX | 6 | FIX-38, FIX-41, FIX-44, FIX-45, FIX-46, FIX-56 |
| Docs | 5 | FIX-49, FIX-51, FIX-53, FIX-54, FIX-57 |

---

## 下一步 / Next Steps

1. 餘下 P2 按類別分批完成（Rust file splits → GUI/UX → ML/DB → Docs）
2. 全部 P2 完成後統一 E4 回歸 + 更新 §十一 一句話狀態
