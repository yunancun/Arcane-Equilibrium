# E5 優化 / 可讀性 / 性能審計

報告日期：2026-05-30  
審計人：E5(explorer)，純讀模式  
Repo root：`/Users/ncyu/Projects/TradeBot/srv`  
基線 commit（凍結）：`187704f6`  
Campaign label：2026-05-17  
前次報告：`docs/CCAgentWorkSpace/E5/workspace/reports/2026-05-17--optimization_readability_performance_audit.md`

## 範圍與限制

FACT：本審計為純讀模式。未修改任何代碼、配置、部署、migration、auth 或交易參數。  
FACT：本次新關注點為（a）前次修復是否持久；（b）2026-05-29/30 新工作（risk.rs split, basis_panel/BasisAggregator）的性能與結構評估。

---

## 計數摘要

- P0：0
- P1：1（前次 P1 之一已修復，一個仍待修）
- P2：2（前次遺留 + 新）
- P3：3

---

## 前次修復狀態驗證

### E5-OPT-001（P1）— strategy_ai_routes.py 超 2000 行硬上限

FACT：`wc -l` 顯示當前 **2552 行**（前次 2536 行，略微增加）。  
狀態：**仍未修復，P1 延續**。無拆分跡象。

### E5-OPT-002（P1）— step_4_5_dispatch.rs 測試嵌入主檔超硬上限

FACT：`ls rust/openclaw_engine/src/tick_pipeline/on_tick/` 確認 `step_4_5_dispatch_tests.rs`（225 行）已存在，commit `dc2a15aa`。  
FACT：`step_4_5_dispatch.rs` 當前 **1803 行**（前次 2020 行），已降至硬上限以下。  
狀態：**已修復**。

### E5-OPT-004（P2）— async GUI routes 直接呼叫阻塞 Bybit HTTP client

FACT：`strategy_ai_routes.py` 中 `refresh_balance`、`get_positions`、`get_active_orders` 已加 `asyncio.to_thread` 包裹（行 765、1071、1072、1122-1123 均有 `to_thread`）。  
狀態：**已修復**。

### E5-OPT-005（P2）— 閉合 PnL PG helpers 缺少 statement_timeout

FACT：`strategy_ai_routes.py` 行 1210、1359 現已加 `SET LOCAL statement_timeout` 呼叫，與行 2201 一致。  
狀態：**已修復**。

### E5-OPT-003/006/007/008/009（P2/P3）

狀態：Stage 0R sweep（E5-OPT-003）/ 通知 failsafe 重複 helper（006）/ FailsafeWatcher 雙實現（007）/ prelive lifecycle CTE 重複（008）/ intent_processor/tests.rs 超限（009）。  
FACT：`intent_processor/tests.rs` 當前 **1838 行**（前次 2005 行），**已降至硬上限以下**，視為已修復。  
其餘 003/006/007/008 無 commit 觸及，仍為開放票。

---

## 新發現（2026-05-29/30 工作）

### E5-OPT-NEW-001 — risk.rs split 評估：真實複雜度降低，結構正確

- 標籤：FACT
- 嚴重性：P3（資訊性評估，非問題）
- 涉及路徑：`rust/openclaw_engine/src/event_consumer/handlers/risk.rs`（822 → 605 行）；新建 `handlers/notification_failsafe_escalate.rs`（231 行）
- 証據：commit `46e0e825` 的 stat 顯示 217 行從 risk.rs 刪除，231 行移入新檔；E2 byte-equivalent 已驗；cargo test 3623/0 通過。risk.rs 剩餘函數（`handle_get_risk_runtime_status`、`handle_clear_consecutive_losses`、`handle_update_risk_config` 等）均為風控業務邏輯，與 notification failsafe 委派路徑職責清晰分離。
- 結論：**拆分合理，非僅移位**。`notification_failsafe_escalate.rs`（231 行）是一個獨立域的新 handler，不只是「把代碼搬到另一個文件」。risk.rs 從 822 降至 605，去除了跨域混用。`handlers/mod.rs` 透過 re-export 維持 caller 零感知。
- 遺留注意：risk.rs 605 行包含約 12 個 `pub(super)` fn，若後續加入更多 risk 變體，接近 800 警告線時應考慮按子域（governor/reconciler/config）再拆。

### E5-OPT-NEW-002 — BasisAggregator per-ticker 呼叫路徑有小型 allocation

- 標籤：FACT
- 嚴重性：P3（在 ticker 熱路徑上，每 cohort symbol insert 有 `symbol.to_string()` 分配）
- 涉及路徑：`rust/openclaw_engine/src/panel_aggregator/basis.rs:97`、`:108`
- 証據：`on_ticker_update` 在兩個 match arm 均執行 `self.latest.insert(symbol.to_string(), ...)` — `symbol` 是 `&str` 參數，每次 cache miss 或 last-price-only update 都分配一個 `String` key。`flush` 路徑在 `entries` Vec 內有 `sym.clone()`（行 150），每 60s 一次，影響可忽略。
- 量化影響：BasisAggregator 是 panel_aggregator task 內呼叫，位於 `PriceEvent` 事件 drain loop（非 tick_pipeline on_tick 路徑）。cohort size = 25，每 ticker frame 1 次呼叫。non-cohort symbol 在 `if !self.cohort.contains(symbol) { return; }` 處快速返回，無分配。只有 cohort 的 25 sym 有 HashMap insert，且多數 frame 是「key 已存在 + 更新 value」路徑（HashMap 的 entry API 可避免重複 hash + 分配）。
- 為何是真實發現而非 FP：ticker event 頻率高（每 frame 含 25 cohort sym 的 update），`HashMap::insert` 在 key 已存在時仍需分配新 `String` key（Rust 標準語意）。entry API 可將每次 update 的分配從 `O(len(symbol))` 降至 0（key 已存在分支）。
- 建議修法：將兩個 match arm 的 `self.latest.insert(symbol.to_string(), ...)` 改為 entry API：
  ```rust
  use std::collections::hash_map::Entry;
  match self.latest.entry(symbol.to_string()) {
      Entry::Occupied(mut e) => { e.get_mut().0 = last_price; /* 只更新 last */ }
      Entry::Vacant(e) => { e.insert((last_price, ip)); }
  }
  ```
  或更精確地只在 `Vacant` 時分配 key。預估收益：cohort hit 路徑每次節省一個 String 分配（~5-15ns）；在高頻 ticker 下 25 sym × 頻率可量測，但絕對值在 panel_aggregator 任務而非 tick hot path，對 <0.3ms tick SLA 無影響。
- 修復人角色：E1(worker)
- 驗證角色：E4(worker) for cargo test

### E5-OPT-NEW-003 — panel_aggregator/mod.rs 825 行跨警告線，BasisAggregator 嵌入加速增長

- 標籤：FACT
- 嚴重性：P2（接近警告線 +3%，且本次 basis 新增 76 行後增長趨勢明確）
- 涉及路徑：`rust/openclaw_engine/src/panel_aggregator/mod.rs:825`
- 証據：`wc -l` = 825；警告線 800；本次 ec995160 commit 加入 BasisAggregator 相關代碼 +76 行進 mod.rs（basis_aggregator field、accessor、flush dispatch、log、測試）。mod.rs 已包含 PanelAggregator struct、run() 主 loop（~250 行）、funding partial cache 邏輯、oi_delta 整合、basis 整合、測試（行 590-）。
- 為何是真實發現而非 FP：825 行超過警告線，且模塊整合模式（每加一個新 panel 加 ~70-100 LOC）代表下個 panel（若有 A1 alpha surface 等擴充）會直接撞 hard cap 前的另一個警告。
- 建議修法：將測試（行 590+）遷出至 sibling `mod_tests.rs`（-100 LOC），或按 panel 種類把 basis flush dispatch、oi_delta flush dispatch 抽為 `flush_panel_aggregate()` 輔助 fn 降低視覺複雜度。不需拆 `run()` 主 loop。無功能語意改動。
- 修復人角色：E1(worker)
- 驗證角色：E4(worker)

### E5-OPT-NEW-004 — 前次遺留：tick_pipeline/commands.rs 1972 行接近硬上限

- 標籤：FACT
- 嚴重性：P2（在 800 警告線的 146%，在 2000 硬上限的 99%；目前 1972，離硬上限 28 行）
- 涉及路徑：`rust/openclaw_engine/src/tick_pipeline/commands.rs:1972`
- 証據：`wc -l` = 1972。此檔在前次報告（2026-05-17）未被列為 finding（前次掃描 cut-off 取 top-50，本次發現進入警告視野）。grep 顯示包含 `submit_external_order`、`apply_confirmed_fill`、`risk_runtime_status_json`、`grant_paper_auth`、`snapshot()` 等大量 impl fn，是 tick pipeline 的核心 impl block。
- 為何是真實發現而非 FP：離 2000 硬上限 28 行（任何日常功能加入即可突破），且此文件是 tick pipeline 核心，在 H0 gate / tick SLA 評審期間需要高可讀性。
- 建議修法：按語義域拆出 test-only helper（若有）至 sibling test file；或把 `risk_governor` 相關 fn（`parse_risk_level`、`GOVERNOR_DE_ESCALATION_COOLDOWN_MS`、`last_governor_de_escalation_ms` 等）抽到 `commands/risk_governor_helpers.rs` sibling（估 -150 LOC）。不改任何 fn 邏輯。
- 修復人角色：E1(worker)
- 驗證角色：E4(worker) cargo test + E2(explorer) zero-semantics review

### E5-OPT-NEW-005 — intent_processor/mod.rs 1968 行，再增長即觸硬上限

- 標籤：FACT
- 嚴重性：P2（同 commands.rs pattern：在 2000 硬上限的 98%）
- 涉及路徑：`rust/openclaw_engine/src/intent_processor/mod.rs:1968`
- 証據：`wc -l` = 1968。
- 建議：與 commands.rs 同等優先，按域提取 helper block。

---

## 文件大小違規完整清單

### 超過 2000 硬上限（生產碼）

| 文件 | 行數 | 異常說明 |
|------|------|---------|
| `program_code/.../app/strategy_ai_routes.py` | 2552 | **P1**，前次已標，未修復，再延一 sprint |

### 800-2000 警告帶（前 15 大，非測試）

| 文件 | 行數 | 狀態 |
|------|------|------|
| `tick_pipeline/commands.rs` | 1972 | P2，距硬上限 28 行 |
| `intent_processor/mod.rs` | 1968 | P2，距硬上限 32 行 |
| `app/governance_routes.py` | 1978 | P2，距硬上限 22 行 |
| `replay_full_chain_routes.py` | 1931 | 警告帶 |
| `config/risk_config_tests.rs` | 1917 | 測試，可接受 |
| `bybit_private_ws.rs` | 1750 | 警告帶，WS client 複雜 |
| `main.rs` | 1667 | 警告帶，歷史 pre-existing |
| `scanner/scorer.rs` | 1613 | 警告帶 |
| `health/domains/strategy_quality.rs` | 1580 | 警告帶 |
| `panel_aggregator/mod.rs` | 825 | P2，剛跨警告線，增長趨勢確認 |

### 已修復（本次確認降至限以下）

| 文件 | 前次行數 | 當前行數 |
|------|---------|---------|
| `step_4_5_dispatch.rs`（測試抽出） | 2020 | 1803 |
| `intent_processor/tests.rs` | 2005 | 1838 |

---

## 熱路徑評估

### BasisAggregator 熱路徑成本

- BasisAggregator 位於 `panel_aggregator::run()` 的 PriceEvent drain loop，**不在 tick_pipeline on_tick 路徑**。
- `on_ticker_update` 是 O(1) HashSet lookup + HashMap insert/update；無 async，無 DB I/O，無 alloc（除 key 首次插入）。
- `flush()` 是 async，每 60s 執行一次，25 sym × PG INSERT；在 flush_timer arm 內，不影響 tick budget。
- 結論：**無 hot-path 性能風險**。BasisAggregator 的 60s flush 設計與 funding_curve/oi_delta 一致，flush 三個 aggregator 串行但均在 tokio::time::interval arm，不阻塞 event drain。

### risk.rs split hot-path 影響

- FACT：risk.rs 的所有 handler 均為 event_consumer IPC command handlers，不在 tick_pipeline hot path。
- 結論：**零 hot-path 影響**。Re-export 維持 caller 零感知，無增量 indirection。

---

## 前次修復持久性總結

| Finding | 前次嚴重性 | 當前狀態 |
|---------|-----------|---------|
| E5-OPT-001 strategy_ai_routes.py 超硬上限 | P1 | 未修復（2552 行，略微增長） |
| E5-OPT-002 step_4_5_dispatch 測試抽出 | P1 | 已修復（1803 行） |
| E5-OPT-003 Stage 0R sweep 重複計算 | P2 | 未觸及，延續開放 |
| E5-OPT-004 async routes 阻塞呼叫 | P2 | 已修復（asyncio.to_thread） |
| E5-OPT-005 statement_timeout 缺失 | P2 | 已修復（行 1210/1359） |
| E5-OPT-006 dispatcher helper 重複 | P3 | 未觸及，延續開放 |
| E5-OPT-007 FailsafeWatcher 雙實現 | P3 | 未觸及，延續開放 |
| E5-OPT-008 prelive lifecycle CTE 重複 | P3 | 未觸及，延續開放 |
| E5-OPT-009 intent_processor/tests.rs | P3 | 已修復（1838 行，降至限下） |

---

## 建議優先序

1. **P1**：strategy_ai_routes.py（2552 行）拆分 — 已延兩 sprint，每次提交都在增長，下個加功能可能引入難以追蹤的回歸。
2. **P2**：commands.rs（1972）/ governance_routes.py（1978）按域提取 helper 或測試 sibling，避免碰觸 2000 硬上限觸發 merge block。
3. **P2**：panel_aggregator/mod.rs 測試抽出 sibling（低風險，純測試移動）。
4. **P3**：BasisAggregator entry API 優化（低 ROI，可選）；notification dispatcher helper 抽共用；FailsafeWatcher 單實現清理。

E5 OPTIMIZATION REPORT: report path: `docs/CCAgentWorkSpace/E5/workspace/reports/2026-05-30--E5--optimization_readability_performance_audit.md`
