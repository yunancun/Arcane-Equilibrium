# 微利死循環 RCA + 修復計畫（等 E1 開工）

**日期**：2026-04-17
**發起**：Operator 觀察「全部交易都是微利」
**狀態**：設計凍結 + 核實完成（compact 後 PM 驗證），等 E1 開工
**引擎 PID**：1771173（20:55 local 起算，watchdog healthy）
**核實記錄**：compact 後重新對照代碼與數學，全部一致；發現 2 項實作細節 worklog 原版未覆蓋，已於 §4.6 / §4.1 補上（見紅框「PM 核實補強」）。

---

## 1. 問題觀察

48h demo fills（PID=1364222 + 1771173 合計）：3210 fills / 924 勝 / 875 負 / **1411 零盈虧** / net +$17.15。

**PnL 分布桶統計**：
- 87.5% 落在 ±$0.20（bucket 10+11 合計 2810）
- 負向長尾：-$7.18 ~ -$2（6 fills）
- 正向長尾：+$2 ~ +$11.28（14 fills）
- 單筆最大虧損：`risk_close:DYNAMIC STOP pnl -10.44%` -$7.18

**兩大微利來源**：
- `risk_close:fast_track_reduce_half` × **989 fills**（31%），avg |PnL| $0.068，小計 -$10.33
- `risk_close:COST EDGE ratio ≥100x ...suggest close while profitable` × 162 fills（~160 unique ratio 變體），avg |PnL| $0.01–0.1，小計 ≈0

---

## 2. 根因驗證（兩者獨立）

### 2.1 COST EDGE 冷啟動 gate（我原先誤判已澄清）

**公式**（`rust/openclaw_engine/src/position_risk_evaluator.rs:76-82`）：
```rust
fn compute_cost_ratio(pnl_pct: f64, fee_rate: f64) -> f64 {
    if pnl_pct > 0.0 { (2.0 * fee_rate * 100.0) / pnl_pct } else { 0.0 }
}
```

**觸發**（`rust/openclaw_engine/src/risk_checks.rs:207-213`）：
```rust
if cost_ratio >= cost_edge_max_ratio && pnl_pct > 0.0 {
    return RiskAction::ClosePosition(format!(
        "COST EDGE: ratio {:.2} >= {:.2}, pnl {:.2}% (suggest close while profitable)",
        cost_ratio, cost_edge_max_ratio, pnl_pct
    ));
}
```

**重要澄清**：
- 分母是**當前實時浮盈 %**，**跟 `settings/edge_estimates.json` 完全無關**
- 我原假設「edge_estimates.json = {} 造成分母 0」**是錯的**
- edge_estimates.json 為空屬另一問題（LEARNING-PIPELINE-DORMANT-1 / P1-7），兩者不同

**配置**（`settings/risk_control_rules/budget_config.toml:25` + 根目錄 `budget_config.toml:7`）：
```toml
cost_edge_max_ratio = 100.0   # default 是 0.8，被人改到 100 意圖「放寬」
```

**數學驗證**（Bybit taker fee_rate ≈ 0.00055，round-trip 0.11%）：
- `0.11 / pnl_pct ≥ 100` → **pnl_pct ≤ 0.0011%** 就觸發
- 實測日誌：`ratio 128.69 pnl 0.00%` → pnl_pct = 0.11/128.69 = 0.000854%
- 極端例子：`ratio 5619309260446` → pnl_pct ≈ 2×10⁻¹⁴%（dust）
- 19:09 剛觸發：`symbol=RAVEUSDT reason=COST EDGE: ratio 110.19 pnl 0.00%`

**設計意圖 vs 實際行為**：
- 設計意圖：「利潤太小相對於費用 → lock in before fees eat it」
- 實際行為：threshold 100 = 只在 pnl_pct ≤ 0.0011% 觸發 = **breakeven 區**
- 出場時的 exit fee ≈ 0.055%（單邊）→ 鎖定的 $0.001% 浮盈必被 exit fee 吃光
- 把 threshold 從 0.8 拉到 100 是「想放寬但方向沒搞對」—— 仍在 breakeven 觸發

### 2.2 fast_track_reduce_half — 重複半倉同一倉位

**觸發條件**（`rust/openclaw_engine/src/fast_track.rs:89-98`）：
1. 5%+3σ 持倉跌幅 + risk < Defensive → `ReduceToHalf`（scoped 單 symbol）
2. risk_level ≥ Defensive → `ReduceToHalf`（portfolio-wide 全倉減半）

**冷卻**（`rust/openclaw_engine/src/tick_pipeline/on_tick.rs:160-168` + `on_tick_helpers.rs`）：
- per-symbol 60s，sigma 縮放至 [60s, 600s]
- 清空整個 HashMap 只在 `risk_level == Normal`（P0-5 fix 2026-04-16）

**非觸發源確認**：
- 90% margin_utilization 閾值（`fast_track.rs:64`）在 leverage_max=100 + total_exposure_max_pct=200% 下，max margin_util = 2% ≪ 90%，**永遠不觸發**。是 intentional 的 cash-mode fail-safe，不要動（fast_track.rs:57-62 註解引用 `docs/references/2026-04-14--fa_phantom_fup7_margin_threshold_decision.md`）
- FA-PHANTOM-1 bug 已修，margin_utilization 分子已除以 leverage

**實測小時分布揭露「重複半倉 dust 化」**（過去 24h demo）：
```
hr      halve_fills  avg_notional  total_pnl
15:00   96           $5.29         +$0.10      ← 重複半倉至 $5（從 $70 halve 4 次）
11:00   20           $1.90         +$1.80      ← halve 5-6 次（$70 → $2）
02:00   86           $8.69         -$2.73
```
- 正常入場 notional ≈ $70；avg $1.90–16 = 同一倉位被反復 halve 4-6 次的殘尸
- 60s 冷卻 + risk_level 長時間卡在 Cautious/Defensive（Normal 才清空）→ 每 60s 一批倉位再半倉 → dust 化

**989 fills × avg |PnL| $0.068 = 「全部微利」的另一半來源**。

---

## 3. 修復設計（已凍結）

### 3.1 Scheme A（相對 notional，採用）

**為什麼 A 勝 B**：
- B（halve_count）只數 fast_track 自己的半倉次數；`grid_trading` / `strategy_close:*` / 手動 IPC 平倉另外削倉位時 B 看不到，仍會再 halve 已小的倉
- A 用「當前 notional / entry_notional」作比，**無論哪條路徑削倉都一視同仁**

**參數**：`ft_min_notional_ratio_of_entry = 0.25`
- 語義：`current_qty × price < 0.25 × entry_notional` 時不再 halve
- 2 次 halve 後剩 25% 剛好卡住；3 次會到 12.5% 被擋下

**實作**：
- `PaperPosition` 新增欄位 `entry_notional: f64`（開倉時 `initial_qty × entry_price` 記錄一次）
- fast_track filter 加一行：
```rust
.filter(|p| {
    let ratio = (p.qty * p.latest_price) / p.entry_notional.max(1e-9);
    ratio >= cfg.limits.ft_min_notional_ratio_of_entry
})
```
- 遷移：fix 部署時在籍的既存倉位，`entry_notional` 初始化為 `qty × entry_price`（等同「從現在開始算」），無回填 DB 需求

### 3.2 Config 方案 ② — 窄帶激活（採用）

**新語義**（`risk_checks.rs` 第 6 步改寫）：
```rust
if cost_ratio >= cost_edge_max_ratio
    && pnl_pct >= min_profit_to_close_pct
    && pnl_pct > 0.0 {
    return RiskAction::ClosePosition(...);
}
```

**冷啟動 default**（Bybit taker 0.055% 單邊）：
- `cost_edge_max_ratio = 0.2` → 觸發上界 `pnl_pct ≤ 0.55%`
- `min_profit_to_close_pct = 0.3%` → 觸發下界 `pnl_pct ≥ 0.3%`
- **激活帶：`0.3% ≤ pnl_pct ≤ 0.55%`**（taker），`0.3% ≤ pnl_pct ≤ 3.0%`（maker）
- 語義：「利潤在縮、但還抓得住」窗口內 lock-in；帶有寬度，不靠學習

**Agent 後續可調**：
- 收窄成 [0.2%, 0.4%]（更保守 lock）
- 打開到 [0.3%, 1%]（讓更多倉位跑）
- hot-reload 30s 內生效

### 3.3 定案參數表 v2

| 參數 | default | 範圍校驗 | 位置 |
|---|---|---|---|
| `cost_edge_max_ratio` | **0.2** | `[0.0, 10.0]` | `BudgetConfig.attention_tax`（existing 欄位改 default） |
| `min_profit_to_close_pct` | **0.3** | `[0.0, 5.0]` | `BudgetConfig.attention_tax`（NEW，單位 %） |
| `ft_min_notional_ratio_of_entry` | **0.25** | `[0.0, 1.0]` | `RiskConfig.limits`（NEW） |

**絕不寫死**：三個都走 ConfigStore（ArcSwap），tick-level hot-reload，4 IPC 寫入面全部支援，不可 restart-to-apply（CLAUDE.md §三 根原則）。toml 值只作冷啟動 default，運行權威在 ConfigStore。

---

## 4. 實作切片（E1 工單）

### 4.1 `rust/openclaw_engine/src/config/budget_config.rs`
- 欄位改 default：`default_cost_edge_max_ratio() -> f64 { 0.2 }`（原 0.8）
- 新增欄位 `min_profit_to_close_pct: f64`（`default_min_profit_to_close_pct = 0.3`）
- validate：`min_profit_to_close_pct` 範圍 `[0.0, 5.0]`
- 單測：
  - `test_min_profit_to_close_pct_default_0_3()`
  - `test_min_profit_to_close_pct_out_of_range_rejected()`
  - `test_min_profit_to_close_pct_serialization_roundtrip()`

**🔶 PM 核實補強（2026-04-17 compact 後）—— validator 範圍相容性**：
- 現行 `budget_config.rs:343-344` 驗證 `cost_edge_max_ratio ∈ [0.0, 100.0]`，已接受過 100.0 的歷史值
- 若 §3.3 把範圍縮到 `[0.0, 10.0]`，**不改動 ConfigStore 的 persisted snapshot 或 IPC 曾 patch 過的 100.0 → 下次重啟反序列化 validate 失敗 → fail-closed 起不來**
- **處理方案**（擇一）：
  1. 寬鬆改法：保留 `[0.0, 100.0]`，只改 default 0.2（最小侵入）
  2. 嚴格改法：縮到 `[0.0, 10.0]` **同時**在 `config/legacy_migration.rs` 加一次性 rewrite — 反序列後檢測 `> 10.0` 則 clamp 到新 default 0.2 + warn
- **推薦方案 2**（嚴格 + 遷移），避免 `[0, 100]` 範圍繼續允許無意義高值
- 新增單測：`test_legacy_high_cost_edge_max_ratio_migrated_to_default()`

### 4.2 `rust/openclaw_engine/src/config/risk_config.rs`（+ `Limits` struct）
- 新增欄位 `ft_min_notional_ratio_of_entry: f64`（default `0.25`）
- validate：範圍 `[0.0, 1.0]`
- 單測：default/range/serialization 三件套

### 4.3 `rust/openclaw_engine/src/risk_checks.rs:207-213`
- 簽名：`check_position_on_tick` 多傳 `min_profit_to_close_pct` 參數（從 BudgetConfig.attention_tax 讀）
- 邏輯加 `pnl_pct >= min_profit_to_close_pct` AND 子句
- 訊息加 `min_profit=...%` 以便線上診斷

### 4.4 `rust/openclaw_engine/src/position_risk_evaluator.rs:86-122`
- `evaluate_position` 簽名加 `min_profit_to_close_pct: f64`
- 傳下到 `check_position_on_tick`

### 4.5 `rust/openclaw_engine/src/tick_pipeline/mod.rs`
- 類似 `current_cost_edge_max_ratio()` 加 `current_min_profit_to_close_pct()` helper
- 在 tick 頂部快照

### 4.6 `rust/openclaw_engine/src/paper_state.rs`（或 PaperPosition 定義處）
- `PaperPosition` 加欄位 `entry_notional: f64`（`#[serde(default)]` 以兼容舊 snapshot）
- 開倉 path（entry fill，`apply_fill` 開新倉分支 ~line 815）：`entry_notional = qty × entry_price`
- **同方向加倉路徑（`apply_fill:798-810`）：`entry_notional += fill_qty × fill_price`**
- reduce_position 不改 entry_notional（保留 halve 基準）
- 啟動遷移：既存 positions 掃一次，若 `entry_notional == 0.0` 則補 `qty × entry_price`

**🔶 PM 核實補強（2026-04-17 compact 後）—— accumulate 路徑語義**：
- 原 worklog 只寫「開倉時記錄一次」，未覆蓋 `apply_fill` 同方向加倉分支（line 798-810 會更新 `qty` 與 weighted-avg `entry_price`）
- 三種選擇結果不同：
  1. **首次凍結**：entry_notional 永遠 = first-open notional — 加倉後 halve 基準偏小，容易被 0.25 擋下（早停）
  2. **累加**（採用）：`entry_notional += fill_qty × fill_price` — 反映累計入場總 notional，符合「halve 到 25% 殘餘」直觀語義
  3. **重設** `= new_qty × new_entry_price`：退化為即時值 — **filter 恆 = 1.0 失效，禁用**
- **實作結論**：採用選項 2（累加）。代數上等價於 `peak_notional`，且與 `entry_price` 的 weighted-avg 更新天然對齊（`old_entry × old_qty + fill_price × fill_qty = new_qty × avg_entry`）
- 新增單測：
  - `test_entry_notional_set_on_open()`
  - `test_entry_notional_accumulates_on_same_direction_fill()`
  - `test_entry_notional_unchanged_on_reduce()`
  - `test_entry_notional_migration_fills_zero_with_qty_times_price()`

### 4.7 `rust/openclaw_engine/src/tick_pipeline/on_tick.rs:208-220`
- fast_track ReduceToHalf 的 filter 加 `ft_min_notional_ratio_of_entry` 檢查
- ft_action filter 從 `.filter(cooldown_expired)` 擴成雙條件

### 4.8 `settings/risk_control_rules/budget_config.toml`
- `cost_edge_max_ratio = 0.2`（從 100 改回）
- 新增 `min_profit_to_close_pct = 0.3`

### 4.9 新增 e2e 整合單測
- `test_cost_edge_band_active_only_in_03_to_055_pct()`
- `test_cost_edge_does_not_fire_below_min_profit()`
- `test_cost_edge_does_not_fire_above_ratio_threshold()`
- `test_fast_track_blocks_halve_below_entry_ratio()`
- `test_fast_track_halves_until_25pct_then_stops()`
- `test_fast_track_halves_after_accumulate_uses_cumulative_notional()`（PM 核實補強，驗 §4.6 選項 2 的累加語義）
- `test_legacy_high_cost_edge_max_ratio_migrated_to_default()`（PM 核實補強，驗 §4.1 的 legacy snapshot 遷移）

### 4.10 GUI 寫入面（P1，可延後）
- Budget / Risk Config patch endpoint 暴露新欄位
- 先確認 existing `patch_budget_config` / `patch_risk_config` 泛型路徑自動 pick up 新欄位即可

---

## 5. 部署與驗收鏈

1. **E1 實作**（兩 fix 同 commit，不拆）—— Operator 已授權
2. **E2 audit**（對抗性審查）—— 檢查：
   - 公式對不對、邊界值、overflow
   - 冷啟動 default 冰凍正確
   - Rust 跨平台（CLAUDE.md §七 #1）
   - 雙語註解（§七）
3. **E4 測試回歸**
   - 基準線：engine lib **1351 passed**（default）、1348（ort feature）、core 380、e2e 35、reconciler_e2e 19
   - 新增 ≥5 單測（見 4.9）
   - Python 基準線 2898 passed / 5 skipped（應不受影響）
4. **PM 驗收** + `docs/CLAUDE_CHANGELOG.md` 頂部追加條目
5. **部署**：`bash helper_scripts/restart_all.sh --rebuild`（MEMORY.md 記：--rebuild 同時重建 engine binary + PyO3）
6. **觀察期 24-48h**：SQL 對比
   - `risk_close:fast_track_reduce_half` fills 應從 989/48h → 預期 < 200（被 ratio 0.25 擋下大部分重複 halve）
   - `risk_close:COST EDGE` fills 應從 162/48h → 預期 < 50（限定 0.3%-0.55% 窄帶）
   - avg |PnL| 應從 $0.068 → 上升到 ≥$0.15（dust 減少）
   - net PnL 48h 從 +$17 → 應有顯著變化（正或負皆可接受，關鍵是信號清晰）

---

## 6. 風險與 rollback

**風險**：
- Config 方案 ② 窄帶太窄 → 該 gate 幾乎不觸發，等同失效但比「空集」稍寬。可接受，hot-reload 調整即可。
- `entry_notional` 遷移若漏位 → 個別既存倉位 halve 無限 → 啟動時掃描補齊即可
- `entry_notional` accumulate 語義若誤用「首次凍結」→ 加倉後基準偏小、早停（見 §4.6 PM 核實補強，已凍結為「累加」語義）
- validator 縮窄範圍若未配 legacy migration → 舊 persisted snapshot 反序列失敗、fail-closed 起不來（見 §4.1 PM 核實補強，已選「嚴格改法 + migration」）
- Phase 5 edge 仍為負：fix 後微利減少 ≠ 整體策略賺錢，只是噪音清理

**Rollback 路徑**（hot-reload，無需重啟）：
1. 把 `cost_edge_max_ratio` 拉回 0.8（default）+ `min_profit_to_close_pct` 改回 0.0
2. `ft_min_notional_ratio_of_entry` 改 0.0（filter 恆 true，還原 pre-fix 行為）
3. 30s 內生效，不動代碼

**硬 rollback**（code revert）：若發現邏輯 bug，`git revert` 兩 commit + `restart_all.sh --rebuild`。

---

## 7. 下一步承接（compact 後）

1. `git status && git log --oneline -5` 確認 CLAUDE.md 啟動檢查
2. 灰度驗證：`python3 helper_scripts/canary/engine_watchdog.py --data-dir /tmp/openclaw --stale-threshold 45 --grace-period 120 --status`
3. Read 本 worklog
4. 按 §4 清單跑 E1 實作（E1 + E1a 並行：budget_config.rs / risk_config.rs + paper_state.rs / risk_checks.rs）
5. E2 audit → E4 回歸 → PM

**CLAUDE.md §三 接手後更新**：
- 本次 fix 命名暫定 `MICRO-PROFIT-FIX-1`
- 完成後 §三「已完成里程碑索引」追 2026-04-17 一行
- TODO.md §P0-X 追新條目（當前 P0-10 已 ✅，P0-11 可用）

---

## 8. 關鍵事實速查（後續避免重跑 query）

- 引擎 PID：1771173（2026-04-17 20:55 local 啟動）
- 48h demo fills：3210 / 924 勝 / 875 負 / 1411 零
- COST EDGE 訊息觸發閾值公式：pnl_pct ≤ (2 × fee_rate × 100) / threshold
  - 當前配 threshold=100, taker fee 0.055% → pnl_pct ≤ 0.0011%（breakeven）
  - 修復後 threshold=0.2, floor=0.3% → band `[0.3%, 0.55%]`
- fast_track 觸發數據：989 fills / 48h，avg notional $7.43（dust 化證據）
- fast_track 90% margin gate：intentional fail-safe，不可動
- Paper pipeline：disabled by default（`OPENCLAW_ENABLE_PAPER=1` 才 spawn）
- 相關 memory：
  - `memory/project_fa_phantom_bug.md` — FA-PHANTOM-1 全策略系統性全平背景
  - `memory/project_p06_rca_and_fix_plan.md` — P0-6 RCA（不同問題，本修復不觸及）
  - `memory/feedback_rust_authoritative_config.md` — Rust 為唯一交易參數權威
  - `memory/feedback_no_dead_params.md` — 可調參數禁止假功能

---

**簽收**：Operator 2026-04-17，選 A + 方案 ②，compact 後開工。
