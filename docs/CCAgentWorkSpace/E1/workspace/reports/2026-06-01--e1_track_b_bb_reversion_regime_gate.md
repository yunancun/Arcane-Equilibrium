# E1 IMPL — Track B：bb_reversion regime 硬 gate（accumulate-only）· 2026-06-01

Role: E1。Scope: 僅 `rust/openclaw_engine/src/strategies/bb_reversion/{mod,params,tests}.rs`（3 檔），
與前一 E1 in-flight 改動（bb_breakout/strategies-mod/tick_pipeline/ipc_server/dual_rail）disjoint。
未 commit（鏈 E1→E2→E4→QA→PM）。main HEAD `2e809b96` 未動。

## 1. 任務摘要

把 bb_reversion 既有 Hurst regime 從「confidence boost」（mod.rs:442-450，**保留不動**）升級為
**entry 硬 gate**：只在 mean_reverting（`RegimeLabel::AntiPersistent`）regime 入場，其他 regime
與 Hurst 不可得（`ctx.indicators.hurst = None`）一律 fail-closed skip。新增可調參數
`require_mean_reverting_regime`（Default=true，治理層硬 gate，agent 不可自關，operator 可關回退）。
accumulate-only（只讓策略在對的 regime 累積乾淨樣本供後續 QC 驗證），非 promotion。

## 2. 修改清單

| 檔 | 改動 |
|---|---|
| `bb_reversion/params.rs` (+32) | `require_mean_reverting_regime: bool` 欄位（`#[serde(default)]`）+ default fn(true) + `Default::default()` + `param_ranges()` 一項（agent_adjustable=false / db_persisted=true）|
| `bb_reversion/mod.rs` (+53) | `BbReversion` struct field + `new()`=true + `update_params()` 賦值 + `get_params()` round-trip + **entry 硬 gate**（:535 `if let Some(is_long)=signal` 後、btc_lead_lag gate 前）|
| `bb_reversion/tests.rs` (+339) | 新 helper `ctx_bb_with_hurst`（可傳 None）+ `neutralize_confluence_gate` + 6 新測試（a/b/b'/c/e + leak-free d）+ `param_ranges_count` 18→19 + 3 既有 Phase B 測試補中文註記 |

## 3. 關鍵 diff（entry gate 本體，mod.rs:535 後）

```rust
if let Some(is_long) = signal {
    // Track B — Hurst regime 入場硬 gate。leak-free：復用 :444 的同一判斷，只讀
    // ind.hurst.regime 既有 point-in-time 值（上游 R/S trailing window +
    // HysteresisDetector trailing lag），不重算、不窺視未來。無 first-detection
    // deadlock：每 tick 重讀 snapshot，regime 切回 mean_reverting 後立即重新 fire。
    if self.require_mean_reverting_regime {
        let regime_allows = match &ind.hurst {
            Some(h) => crate::regime::RegimeLabel::from_legacy_str(&h.regime)
                == crate::regime::RegimeLabel::AntiPersistent,
            None => false, // fail-closed：Hurst 不可得 → 不交易。
        };
        if !regime_allows {
            // ...debug log...
            self.persistence.clear(ctx.symbol); // 與 btc_lead_lag gate 一致
            return intents;
        }
    }
    if !btc_lead_lag_allows_reversion_entry(...) { ... }
```

## 4. 治理對照

- **leak-free（CC #5 + QC，最高）**：regime label 由 `regime/hurst.rs::compute_hurst`（R/S trailing
  price window）+ `HysteresisDetector::push`（只吃 `history` VecDeque，trailing lag）算出，純
  point-in-time。gate **只讀** `ind.hurst.regime` 既有字串，不重算、不引入 look-ahead。test (d)
  構造「prefix 相同、僅未來 bar 不同」兩序列證 trailing-only label bit-identical + 反向健全性斷言
  （含未來窗口 H 偏離 >0.05）證序列有判別力。
- **fail-closed（根原則 6）**：Hurst=None → skip（比舊行為「None→boost=0 但仍交易」更保守）。
- **無 first-detection deadlock**：每 tick 重讀當前 snapshot，無 `is_none()` 永久 guard；regime 切回
  mean_reverting 立即重新 fire。
- **accumulate-only（非 promotion）**：未加任何晉升/放量邏輯。fills 變少是預期且正確。
- **hurst_boost 正交保留**：mod.rs:442-450 boost 0 改動；gate 決定能否進場，boost 微調 confidence。
- **hard boundary**：max_retries / live_execution_allowed / execution_authority / system_mode / mainnet
  全未碰（git diff grep 確認）。
- **真 tunable（禁假功能）**：operator 經 IPC `update_strategy_params`（dispatch.rs:286）→
  `BbReversion::update_params_json`（serde_from_str）→ `update_params`（validate+賦值）→ runtime
  field → entry gate 讀取；`get_strategy_params` 回讀；param_ranges `db_persisted: true`。與既有
  `require_ma_confirmation` 完全同接線模式。

## 5. 測試（誠實）

- `cargo check -p openclaw_engine --lib`：PASS（exit 0，Finished）。3 warning 全 pre-existing 他模塊
  （db_writer unused import / single_watcher C4 dormant fields / ma_crossover make_intent），0 引用
  bb_reversion。
- `cargo test -p openclaw_engine --lib`：**3700 passed / 0 failed / 1 ignored**（全 suite，0 filtered）。
- bb_reversion 模組：**54 passed / 0 failed**（原 48 + 新 6）。strategies:: 全套 627 passed。
- **對抗驗證（測試 bite 確認）**：
  - 注入 `None => true`（破壞 fail-closed）→ (c) FAIL ✓
  - 注入 `if false &&`（停用整個 gate）→ (b)/(b')/(c)/(e) FAIL、(a)/(d) pass ✓（證明每個行為斷言唯一由
    regime gate 決定，非 vacuous）
  - 均已還原，最終樹乾淨（`None => false` ×1，`if self.require_mean_reverting_regime {` ×1）。
- Mac advisory；E4 Linux regression authoritative。

## 6. param 接線確認（證明非假功能）

完整鏈路：operator/agent → IPC `update_strategy_params`（ipc_server/dispatch.rs:286）→
`BbReversion::update_params_json`（mod.rs:643，`serde_json::from_str::<BbReversionParams>`，欄位有
`#[serde(default)]`）→ `update_params`（validate + `self.require_mean_reverting_regime = params....`）→
runtime field → entry gate 讀取。`get_strategy_params` / `get_param_ranges` 端點回讀。param_ranges
標 `db_persisted: true` 持久化。test (e) 用真實 `update_params/get_params` 通道驗證 round-trip +
flag 改變 on_tick 行為（gate 開 trending=0 vs gate 關 trending=1，confluence 中性化隔離）。

## 7. 不確定之處 / 殘留風險

1. **兩個同名 `BbReversionParams`**：`bb_reversion/params.rs`（IPC 熱重載完整版，我加 gate）≠
   `strategy_params.rs:211`（TOML 啟動子集）。registry.rs:88 factory 只 wire TOML 子集；
   `require_ma_confirmation`/`ma_confirmation_kind`/`maker_price_buffer_ticks` 與我的
   `require_mean_reverting_regime` **都不在 TOML 層**，靠 `new()` default(true) + IPC update。
   → **gate 啟動即 true**（factory 不覆蓋），符合治理層硬 gate 預設啟用。
   → **殘留**：operator 不能在 live/demo/paper TOML 設初始值（與既有 `require_ma_confirmation` 現狀
   一致）。若 PA/operator 要 TOML 初始可覆蓋，需在 strategy_params.rs::BbReversionParams + registry.rs
   factory 補欄位（對齊既有模式，**非本任務範圍**）。建議 PM 登記 follow-up（與 require_ma_confirmation
   並列）。
2. **gate 與 confluence regime weight 同向**：bb_reversion confluence regime_score 也偏好
   mean_reverting（reversion profile weight_regime=30），且 reversion signal 在 confluence 內因
   momentum 因子與 signal 條件互斥而高度倚賴 regime。→ 在預設配置下，gate 擋住的 trending/random/None
   confluence 大多也擋。gate 的**增量價值** = (a) 硬性保證（confluence 是軟 score，理論上其他因子湊夠
   分可放行 trending；gate 一票否決）；(b) None fail-closed（confluence 用 uncertain=0.6 可能放行，
   gate 強制 skip）。test 用 `neutralize_confluence_gate` 隔離證明 gate 真實生效。**這也意味著 runtime
   fills 減少幅度可能不如「gate 完全主導」那麼大**（confluence 已先擋掉部分）—— E4/QC replay 時應留意
   增量 fills 變化主要來自硬性否決 + None fail-closed，QC 後續驗證 accumulate 樣本時可參考此特性。
3. **端到端**：IPC probe + runtime entry 行為 deploy/operator-gated（CLAUDE §六，out of scope）。

## 8. Handoff to E2

Review 重點：(1) entry gate 插入點正確（:535 signal 後、btc_lead_lag 前），復用 :444 判斷無
look-ahead；(2) fail-closed None=>false（比舊行為保守）；(3) param 接線與 require_ma_confirmation
同模式（非假功能），殘留 #1 TOML 層子集是既有設計選擇；(4) 測試 bite（confluence 中性化的必要性，
見殘留 #2 + 對抗驗證）；(5) hurst_boost :442-450 + 3 既有 Phase B 測試斷言 0 邏輯改（僅註記）。
然後 E4 Linux regression（authoritative）+ QC 驗 leak-free + accumulate 語義。

E1 IMPLEMENTATION DONE: 待 E2 審查
