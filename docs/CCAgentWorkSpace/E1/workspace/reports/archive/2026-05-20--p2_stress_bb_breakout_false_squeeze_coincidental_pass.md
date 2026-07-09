# E1 — P2-STRESS-BB-BREAKOUT-FALSE-SQUEEZE-COINCIDENTAL-PASS · 2026-05-20

## 任務摘要

v55 audit 點出 `stress_bb_breakout_false_squeeze_no_volume` 因錯誤原因 PASS。前
份 E1 報告 `2026-05-19--stress_test_invariant_drift_fix.md §不確定之處 #2`
已預警同類 coincidental pass — 本任務就是該 follow-up。

**Coincidental PASS 真因**：fixture 用 `EMPTY_ALPHA_SURFACE.oi_delta_panel =
None`，整個 `on_tick` 在 commit `7a07348b`（2026-05-14, Phase 8a）新增的 OI
fail-closed gate（`bb_breakout/mod.rs:479`）就直接 `return vec![]`。

| 階段 | 舊行為 | 結果 |
|---|---|---|
| ctx1（squeeze 登記） | OI gate fail-closed → `return vec![]` | squeeze 從未登記（has_squeeze=false） |
| ctx2（false expansion） | OI gate fail-closed → `return vec![]` | 從未進 entry path，volume gate 從未被執行 |
| assert `intents.is_empty()` | trivially 滿足 | 「不是因為 volume gate 攔下」而是「OI gate 一律 return 空」 |

**修法**：
1. 補 `fresh_oi_surface("BTCUSDT")` 讓 OI gate 通過（沿用前 commit 已存在的 helper）。
2. 強化 assert 覆蓋 7 個切片，**真實踩 volume gate 拒絕路徑**。
3. 加 control case — 同 fixture 僅 `vol_ratio` 升到 ≥ threshold 必須觸發
   entry — 證 (3) 的 0 intents 唯一原因是 volume gate。
4. RED→GREEN 演練先驗證「fixture 修好後若移除 volume gate 防線會 RED」（已執行）。

**邊界遵守**：純測試端改動，不動 `bb_breakout/` 任何 production 邏輯。

## 修改清單

| 檔 | 變動 |
|---|---|
| `rust/openclaw_engine/tests/stress_integration.rs` | +92/-6 LOC（中文 rationale + 7 切片 assert + control case） |

僅一個 test function `stress_bb_breakout_false_squeeze_no_volume`
（line 545-…）被改；其餘 34 個 stress test、production 代碼全 0 改動。

無新檔案、無新 helper、無新 import。沿用前 PR 已建立的 `fresh_oi_surface`
helper（line 154-168）+ `has_squeeze` / `entry_price_of` / `trailing_stop_of`
public accessor（mod.rs:309-326）。

## 關鍵 diff

### 修前（line 545-571，舊版）
```rust
#[test]
fn stress_bb_breakout_false_squeeze_no_volume() {
    let mut strat = BbBreakout::new();
    strat.min_persistence_ms = 0;
    let ctx1 = make_ctx("BTCUSDT", 67000.0, 0,
        Some(bb_snapshot(0.5, 0.015, 50.0, 67000.0, 67000.0, 25.0, 0.8)));
    strat.on_tick(&ctx1, &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE);
    let ctx2 = make_ctx("BTCUSDT", 67500.0, 700_000,
        Some(bb_snapshot(1.1, 0.05, 60.0, 67000.0, 67100.0, 25.0, 1.0)));
    let intents = strat.on_tick(&ctx2, &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE);
    assert!(intents.is_empty(), "should not enter without volume confirmation");
}
```
唯一 assert `intents.is_empty()` 被 OI fail-closed 永遠滿足；fixture 完全沒
觸發 volume gate。

### 修後（核心切片）
```rust
let surface = fresh_oi_surface("BTCUSDT");

// (1) Squeeze 登記
strat.on_tick(&ctx1, surface);
assert!(strat.has_squeeze("BTCUSDT"),
    "ctx1 應在 bandwidth(0.015) < squeeze_bw(0.03) 時登記 squeeze；…");

// (2)(3) Expansion + direction OK 但 volume 不過 → 0 intents
let intents = strat.on_tick(&ctx2, surface);
assert_eq!(intents.len(), 0,
    "vol_ratio(1.0) < volume_threshold(1.2) 時 false breakout 必須 0 intents");

// (4) 顯式禁 Open/Close — 防 future regression 用其他理由產生意外 action
for action in &intents {
    match action {
        StrategyAction::Open(i) => panic!("false_squeeze 不應產生 Open intent，但拿到 {:?}", i),
        StrategyAction::Close { reason, .. } => panic!("false_squeeze 無持倉，不應產生 Close (reason={})", reason),
    }
}

// (5) PnL 邊界 — 無入場 → no entry_price / no trailing_stop
assert_eq!(strat.entry_price_of("BTCUSDT"), None, "false breakout 未入場，entry_price 必為 None");
assert_eq!(strat.trailing_stop_of("BTCUSDT"), None, "false breakout 未入場，trailing_stop 必為 None");

// (6) Squeeze 窗口保留（FIX-26 語義）
assert!(strat.has_squeeze("BTCUSDT"),
    "false breakout 不消耗 squeeze 窗口（FIX-26 語義），squeeze_detected_ms 應保留");

// (7) Control case — 同 fixture vol_ratio→1.5 必須 fire long entry
let mut strat_ctrl = BbBreakout::new();
strat_ctrl.min_persistence_ms = 0;
strat_ctrl.on_tick(&ctx1, surface);
let ctx2_ctrl = make_ctx("BTCUSDT", 67500.0, 700_000,
    Some(bb_snapshot(1.1, 0.05, 60.0, 67000.0, 67100.0, 25.0, 1.5)));
let intents_ctrl = strat_ctrl.on_tick(&ctx2_ctrl, surface);
assert_eq!(intents_ctrl.len(), 1,
    "control：vol_ratio 升到 >= threshold 後同 fixture 必須產生 entry");
match &intents_ctrl[0] {
    StrategyAction::Open(i) => assert!(i.is_long, "control：%B(1.1)>1.0 → 必為 long entry，但拿到 short"),
    other => panic!("control：期待 Open(long)，實際 {:?}", other),
}
```

### 7 個切片 vs PA 任務 4 三條對應

| PA 要求 | 切片 |
|---|---|
| 驗 indicator 路徑（squeeze→expansion→direction） | (1) has_squeeze + (2) bandwidth>expansion_bw + %B>1 判 long |
| 驗 entry/exit 行為（false_squeeze NO ENTRY 或 minimal entry） | (3) intents=0 + (4) 禁 Open/Close |
| 驗 PnL 邊界（false_squeeze 不應觸發大 loss） | (5) entry_price=None + trailing_stop=None（無入場 → 無 PnL） |
| 額外 — 防 future regression 真實衡量 volume gate 而非其他 fail-closed | (6) squeeze 保留 + (7) control case fire long |

## RED → GREEN 演練（任務 5）

| 步驟 | fixture | 預期 | 實際 |
|---|---|---|---|
| Baseline（修前） | `EMPTY_ALPHA_SURFACE` + vol_ratio=1.0 | GREEN（但 coincidental） | GREEN |
| RED probe | `fresh_oi_surface` + vol_ratio=1.5（升到 ≥ threshold） | FAIL（產生 long entry → assert is_empty 必失敗） | FAILED at line 568 panicked "should not enter without volume confirmation" |
| Final（修後） | `fresh_oi_surface` + vol_ratio=1.0 + 7 切片 + control | GREEN（每個 assert 都有意義） | GREEN |

RED probe **真的會 FAIL**（已執行 `cargo test stress_bb_breakout_false_squeeze_no_volume` 拿到 panic）→
證明：(a) fixture 修好後 entry path 真的可達；(b) volume gate 是唯一防線；
(c) assert 改進後若任一切片崩壞（OI gate 移除、squeeze 登記改變、entry path
新增其他 fail-closed、volume gate 邏輯反向、PnL state 寫入點偏移）都會 RED，
不再 coincidentally GREEN。

## 治理對照

| 治理項 | 對照 |
|---|---|
| 不擴大 PA 範圍 | 僅一個 test function 改；不碰 production 代碼、不動 helper、不動 import |
| 不改 runtime business logic（PA 邊界#6） | `bb_breakout/mod.rs` / `params.rs` / `runtime_params.rs` / `tests*.rs` 0 改動；Python 0 改動 |
| 跨平台兼容 | 純 Rust 測試，沿用 `Box::leak` 既有模式；無新硬編碼路徑 |
| 注釋規範 | 全中文 rationale（標 v55 audit + commit + 7 個切片 + RED probe 結果）；無中英對照重複 |
| 硬邊界 | 不碰 max_retries / live_execution / authorization；test fixture only |
| 工作目錄鎖定 | `/Users/ncyu/Projects/TradeBot/srv` |
| 不 git add/commit/push | 確認 |
| 文件大小 | stress_integration.rs 1315 → 1401 LOC；既已過 800 警告線但本次 +92/-6 ≪ 2000 上限，且僅修 1 個函數，不擴大範圍 |

## 驗證證據

### 目標 test（修後 GREEN）
```
cd /Users/ncyu/Projects/TradeBot/srv/rust
cargo test -p openclaw_engine --release --test stress_integration \
  stress_bb_breakout_false_squeeze_no_volume
# → test stress_bb_breakout_false_squeeze_no_volume ... ok
# → 1 passed; 0 failed
```

### RED probe（中間步驟，演練「fixture 修好 + 不修 assert」會 fail）
```
running 1 test
test stress_bb_breakout_false_squeeze_no_volume ... FAILED
panicked at stress_integration.rs:568:5:
should not enter without volume confirmation
```

### 相鄰 bb_breakout stress test
```
cargo test -p openclaw_engine --release --test stress_integration stress_bb_breakout
# → stress_bb_breakout_valid_squeeze_with_volume ... ok
# → stress_bb_breakout_false_squeeze_no_volume ... ok
# → 2 passed; 0 failed
```

### Full stress_integration suite
```
cargo test -p openclaw_engine --release --test stress_integration
# → 35 passed; 0 failed; 0 ignored
```

### Full openclaw_engine cargo test surface
```
cargo test -p openclaw_engine --release --tests
# → lib 3042 passed + 全 integration suites 0 failed
# → 0 regression
```

## 不確定之處

1. **檔案 LOC 突破 800 警告線**：stress_integration.rs 已自 ~1315 增至 1401。
   前一份 E1 報告（2026-05-19）已記錄該檔越線；本次 +92 LOC 全在單一函數內，
   不擴大範圍。是否需開 FIX-PLAN follow-up 拆檔交 E2 判斷；E1 本任務不主動
   執行拆檔以遵守「不擴大範圍」原則。

2. **squeeze_detected_ms 在「OI fail-closed → 未登記」與「OI 通過 → 已登記」
   兩條路徑語義不同**：本修法揭露當前 OI gate 在 squeeze 登記**之前**執行
   （mod.rs:479 在 line 538 的 squeeze 登記之上），意味 OI 不可用時整個策略
   完全 dormant — 包含 squeeze 登記、OI buffer 維護（line 567-）、cooldown
   等。這是 commit `7a07348b` 的設計選擇；前一份 E1 報告也已 surface 過。
   不在本任務範圍內處理。

3. **control case 是「同函數內第二個策略實例」非單獨 `#[test]`**：選此做法
   是因為 v55 PA 任務 5 要求「相鄰 1-2 個 bb_breakout stress test 確認
   RED→GREEN 轉換有意義」，且 control 是同函數內的對照組（test cohesion 強，
   單一 fixture 唯一變動 = vol_ratio，更直接驗 volume gate 唯一性）。
   若 E2 偏好拆成獨立 `#[test] stress_bb_breakout_false_squeeze_control_volume_threshold`
   單獨檔案 follow-up 可行；本 PR 暫不拆以最小改動。

## Operator 下一步

1. **E2 review**：確認 7 個切片 + control case 覆蓋充分，確認對照組與
   `valid_squeeze_with_volume` test 無語義重疊（valid_squeeze 用 vol_ratio=2.0
   且 fixture 不同 — bandwidth/RSI/percent_b 皆異）。
2. **E4 regression**：跑完整 cargo test 包含 lib + integration（本 E1 已驗
   全綠，0 regression）；建議 E4 在 Linux release 環境再驗一次。
3. **QA**：純 test fixture 改，無 production / live / authorization side
   effect，可走 fast lane。
4. **PM**：E1→E2→E4 通過後統一 commit + push（**E1 不直接 commit**）。

## 報告

報告路徑：`docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-20--p2_stress_bb_breakout_false_squeeze_coincidental_pass.md`
