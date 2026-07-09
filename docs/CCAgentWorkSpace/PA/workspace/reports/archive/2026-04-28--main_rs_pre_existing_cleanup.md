# MAIN-RS-PRE-EXISTING-CLEANUP P2 — Sibling extract `main_scanner_init.rs`

- Date: 2026-04-28
- Agent: PA + E1 合一（per operator 三角合一授權）
- Base HEAD: `8a5973f`（origin/main）
- Risk rating: 低（純 location refactor，0 production behavior change）

## 背景

Wave E `cost_edge_advisor_boot` split (commit `2f88c40`) 把 main.rs 從 1230 → 1210，仍 10 LOC 超 §九 1200 hard cap（pre-existing 1208 baseline）。E2 PB1 retroactive review (`a23d6c2`) 標 MED-1：governance ambiguity。PM Decision 開新 P2 ticket 處理 pre-existing。

## Step 1 — Investigation 結論

main.rs 全檔 1210 LOC 掃描，找到 5 個 ≥10 LOC 候選：

| # | 區塊 | 行範圍 | LOC | 自包含度 |
|---|---|---|---|---|
| 1 | Scanner D4 pre-init（config + registry + edge estimates + relay channel） | 247-313 | ~67 | 高（output 4 個 Arc + 1 mpsc tx，無啟動順序耦合） |
| 2 | Phase 4 wrappers（LinUCB + News + Governance + Phase 4.1 teacher loop + A2 news pipeline） | 656-703 | ~48 | 中（依賴 governance_wrapper 順序） |
| 3 | DB pool + V024 auto-migrate | 605-651 | ~47 | 中（需在 budget/audit init 前完成） |
| 4 | IPC server 構建 | 415-528 | ~114 | 低（trigger handle pre-create 與 watcher 兩階段耦合 deep） |
| 5 | Live event slot + ready barrier 註解區 | 841-880 | ~40 | 純註解居多，extract value 低 |

**選定 #1 Scanner pre-init**：(a) 最自包含 (b) 67 LOC body → ~13 LOC call site = net -54 LOC（headroom 充足，1190 acceptable target 提供 22 LOC buffer 給未來小改）(c) 避開 cost_edge_advisor_boot 區（Wave E 已抽）(d) sibling 模式對齊 main_boot_tasks / main_pipelines / main_fanout / main_ws / main_watchdog / main_shutdown / main_instruments 既定 pattern。

## Step 2 — Design

**新 sibling**：`rust/openclaw_engine/src/main_scanner_init.rs`（170 LOC，遠低於 800 warn / 1200 hard cap）

**API 表面**：
- `pub(crate) struct ScannerInitBundle { scanner_store, symbol_registry, edge_estimates, ws_topic_change_tx, current_ws_client_tx }`
- `pub(crate) fn init_scanner() -> ScannerInitBundle` — 無參數，從 env 讀路徑；fail-soft（config 載入失敗 → defaults）；內部 `tokio::spawn` relay task

**main.rs 接線**：
```rust
let main_scanner_init::ScannerInitBundle {
    scanner_store,
    symbol_registry,
    edge_estimates: scanner_edge_estimates,
    ws_topic_change_tx: scanner_ws_tx,
    current_ws_client_tx,
} = main_scanner_init::init_scanner();
```

**保留變數名**：`scanner_store` / `symbol_registry` / `scanner_edge_estimates` / `scanner_ws_tx` / `current_ws_client_tx` — 下游 5 處使用點 (L470/572/574/575/576/599/600/721/746/747/933/934/1034/1035) 全部零變動，grep stability 維持。

**移除 imports**：`load_toml_or_default` / `SymbolRegistry` / `ScannerConfig`（僅 sibling 用，main.rs 不再引用）。

## Step 3 — Impl

| 動作 | 檔案 |
|---|---|
| 新建 sibling（含完整 MODULE_NOTE 雙語注釋 + struct/fn docstring 雙語） | `rust/openclaw_engine/src/main_scanner_init.rs` (+170) |
| `mod main_scanner_init;` 加入 mod 宣告（按字典序） | `main.rs` L16 (+1) |
| 移除 unused `use` 三項 | `main.rs` L27/30/32 (-3) |
| 替換 inline scanner 區塊為 destructure call | `main.rs` L247-313 → L246-260 (-67 +14 = -53) |

**雙語注釋**：sibling 完整遵循 `feedback_bilingual_comment_style` — module-level MODULE_NOTE EN+中、struct docstring EN+中、fn docstring EN+中、inline 註解 EN+中對照保留。

**0 production behavior change**：(a) 區塊內每行 logic 1:1 移植 (b) `tokio::spawn` 仍在 tokio runtime 內呼叫（async_main 內呼叫 `init_scanner()` → tokio::spawn relay task，runtime context 一致）(c) 沒改 env var 名 / 預設值 / 載入順序 (d) `let _: ScannerInitBundle { ... } = init_scanner();` 在原 inline 區塊原位置呼叫，downstream 5 個 sites 順序不變。

## Step 4 — Verify

| 驗收項 | 期望 | 實際 | 結果 |
|---|---|---|---|
| `wc -l main.rs` | ≤ 1190 (preferred) | **1158** | ✅ 超預期 32 LOC headroom |
| `wc -l main_scanner_init.rs` | ≤ 800 | **170** | ✅ |
| `cargo build --release -p openclaw_engine` | 編譯通過 | Finished `release` profile [optimized] target(s) in 19.97s | ✅ |
| `cargo test --release -p openclaw_engine --lib` | 無 regression | **2308 passed; 0 failed** | ✅ baseline 已 +9（base HEAD `8a5973f` 的 edge-diag-2 test rename），0 failed |
| `cargo test ... --test test_cost_edge_advisor_daemon` | 11/0 | **11 passed; 0 failed** | ✅ |
| `cargo test ... --test test_cost_edge_advisor_persistence` | 2/0 | **2 passed; 0 failed** | ✅ |
| 無新 unsafe / unwrap / panic | — | 0 引入 | ✅ |
| 變數名保留 | grep stability | 5 個下游名零改動 | ✅ |
| §九 1200 hard cap | 進入合規 | 1158 < 1200 | ✅ |
| §九 800 warn line（sibling） | 不超 warn | 170 << 800 | ✅ |

**Lib test baseline drift 說明**：prompt 寫 2299，實際 2308。差 9 個 = base HEAD `8a5973f` ("test JSON keys n_trades→n") 已加新 test。0 failed → 不影響本 P2 結論。

## Step 5 — 結論

✅ **MAIN-RS-PRE-EXISTING-CLEANUP P2 完成**

- main.rs：1210 → **1158**（淨減 52 LOC，比 1190 acceptable target 多 32 LOC headroom）
- 新 sibling main_scanner_init.rs：170 LOC（170 << 800 warn）
- 抽出 fn 列表：`init_scanner() -> ScannerInitBundle`（單 fn）
- §九 1200 hard cap 進入合規，governance ambiguity（E2 PB1 MED-1）解除
- 0 production behavior change：cargo build 綠 + lib 2308/0 + cost_edge_advisor 11/0 + 2/0
- 雙語注釋符合 `feedback_bilingual_comment_style`
- 副作用識別清單：
  1. ✅ 沒有其他模塊 import 此 inline 區塊（區塊原為 main.rs private 邏輯）
  2. ✅ 無測試直接 mock 此區塊（startup 邏輯無 mock）
  3. ✅ 仍在 tokio runtime 內（init_scanner 在 async_main 內呼叫，tokio::spawn 上下文一致）
  4. ✅ 無 API response schema 改動
  5. ✅ 無 RustEngine ↔ Python IPC schema 改動

## E1 派發計劃（已合一執行，無 follow-up）

無。本任務 PA + E1 合一完成，純 refactor 無 E1 邏輯擴增。

## E2 重點審查 3 點（建議）

1. **變數名 grep stability**：confirm 下游 5 處（L470/572/574/575/576/599/600/721/746/747/933/934/1034/1035）使用 `scanner_store` / `symbol_registry` / `scanner_edge_estimates` / `scanner_ws_tx` / `current_ws_client_tx` 五個原名零變動。
2. **Sibling 命名**：`main_scanner_init.rs` 對齊既定 sibling pattern（`main_boot_tasks` / `main_pipelines` / `main_fanout` / `main_ws` / `main_watchdog` / `main_shutdown` / `main_instruments`），未引入新命名空間。
3. **Tokio runtime context**：`init_scanner()` 內 `tokio::spawn` 必須在 tokio runtime active 時呼叫；`main.rs::async_main` 已在 multi-thread runtime 內，呼叫位置（destructure 處）位於 async fn body，runtime context 與原 inline 區塊一致。

## Worktree / Commit

- 不 commit（worktree pattern；返主會話統一 commit + push）
- 改動檔案：
  - `rust/openclaw_engine/src/main.rs`（modified, -52 LOC net）
  - `rust/openclaw_engine/src/main_scanner_init.rs`（new, +170 LOC）

PA DESIGN DONE: report path: /Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-28--main_rs_pre_existing_cleanup.md
