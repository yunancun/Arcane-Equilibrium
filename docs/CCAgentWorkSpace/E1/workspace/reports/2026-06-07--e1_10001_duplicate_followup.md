# E1 IMPLEMENTATION — P2 #6 orderLinkId follow-up：10001+duplicate 與 110072 對齊

- 日期：2026-06-07
- 角色：E1（Backend Developer）
- 分支：feature/l2-critic-lessons-tools（3 個目標檔與 origin/main byte-identical → 可乾淨 cherry-pick 到 main）
- 來源：P2 #6 的 E2/BB flag（同一 open silent-success 風險未收）
- 狀態：IMPL DONE，待 E2 審查 + BB（exchange-facing retCode 分類）

## 一、任務摘要

P2 #6 已把 Bybit `110072`（duplicate orderLinkId）做成 close-only 冪等成功、open
fail-closed。E2/BB 當時 flag：`10001 + retMsg contains "duplicate"` 也是同類
「duplicate orderLinkId」，但 classify **無條件 NoOp**（open 也被當成功）= 同一個
open silent-success 風險未收。本任務把它收斂，與 110072 完全對齊。

- Follow-up A（Rust，execution path，主要）：dispatch.rs + dispatch_tests.rs
- Follow-up B（Python，cosmetic，trivial）：closed_pnl_pagination.py

## 二、修改清單

| 檔 | 改動 | 行數 |
|---|---|---|
| `rust/openclaw_engine/src/event_consumer/dispatch.rs` | classify 10001 arm NoOp→Structural；helper close_dup 擴 10001+dup；consumption info! log 去寫死 110072 字面 + 加 ret_code/ret_msg | +98/-? 區段重整 |
| `rust/openclaw_engine/src/event_consumer/dispatch_tests.rs` | 改 2 既有測試（依賴舊 NoOp 行為）+ 新增 5 helper 測試 | +118/-65 |
| `program_code/exchange_connectors/bybit_connector/control_api_v1/app/closed_pnl_pagination.py` | `_ENGINE_BY_TAG` 提為 module-level const | +9/-? |

cherry-pick 前提：`git diff --stat origin/main` 對三檔皆空（byte-identical），先驗再動。

## 三、關鍵 diff（A，dispatch.rs 核心代碼，非註釋）

改動 1 — classify 10001 arm：
```rust
-        10001 => {
-            if ret_msg.to_ascii_lowercase().contains("duplicate") {
-                DispatchOutcome::NoOp
-            } else {
-                DispatchOutcome::Structural
-            }
-        }
+        10001 => DispatchOutcome::Structural,
```
（duplicate 與非-duplicate 的 10001 同歸 Structural；classify 層不再讀 retMsg。
retMsg 仍被 10002 arm 使用，無 unused 參數警告。duplicate 偵測下移到 consumption 層。）

改動 2 — helper close_dup_is_idempotent_success：
```rust
     req.is_close
-        && matches!(err, BybitApiError::Business { ret_code, .. } if *ret_code == 110072)
+        && match err {
+            BybitApiError::Business { ret_code, .. } if *ret_code == 110072 => true,
+            BybitApiError::Business {
+                ret_code, ret_msg, ..
+            } if *ret_code == 10001 => ret_msg.to_ascii_lowercase().contains("duplicate"),
+            _ => false,
+        }
```

改動 3 — consumption Structural 分支 info! log：去掉寫死字面 "110072"（現也可能是
10001+dup，避免誤記）+ 加 ret_code/ret_msg 提取保留可區分性（mirror NoOp/else 分支
的 log 模式）。

## 四、observable 行為對照（open/close × duplicate）

| 輸入 | classify | consumption | observable 結果 | 變化 |
|---|---|---|---|---|
| **open + 10001-dup** | NoOp→**Structural** | else 分支（is_close=false） | `DispatchFailed` terminal="Rejected" | **新 hardening**（之前 NoOp 誤當成功）|
| **close + 10001-dup** | NoOp→**Structural** | `if close_dup` upgrade | lease `Consumed`（冪等成功）| 之前 classify-NoOp success；**對 close 同一 observable 成功，無回歸** |
| 非-dup 10001（格式錯/qty 非法）| Structural | else（若 close primary）| `DispatchFailed` | **不變** |
| 110072（open/close）| Structural | 同 #6 | open=Rejected / close=Consumed | **完全不變** |

不碰：`noop_is_exchange_zero_position`（10001/110072 都不收斂倉）、`OPEN_NO_RETRY`、
retry 預算、mainnet/auth/risk/system_mode。

## 五、改了哪個既有測試（為何）

grep `test.*duplicate.*noop` by-name 只命中 1 個明顯測試，但 full lib 跑出 **2 個額外
失敗**（命中 E1 memory 13624「接手他人 IMPL 必親跑 full test，不能信 by-name grep」）：

1. **`test_classify_10001_invalid_order_link_id_format_is_structural`**（誤導性命名）
   — 名字寫 "is_structural"，但尾部夾帶一條 `"DUPLICATE order_link_id" → NoOp` 大寫
   補充斷言（驗舊 case-insensitive duplicate→NoOp）。改：大寫補充斷言 → Structural。
   首段 `"invalid order_link_id format" → Structural` 不變（非-duplicate 仍結構性）。

2. **`test_run_dispatch_retry_noop_on_second_attempt_records_attempts_2`**（測 helper
   非 classify）— 驗 `run_dispatch_retry` 的「NoOp 中斷重試迴圈」路徑，**碰巧**用
   10001+dup 作 NoOp 觸發碼。改：觸發碼換 `110001`（穩定 NoOp 碼 "order not exists"），
   保留本測試對 NoOp 路徑的覆蓋意圖不變（Structural 中斷另由
   `test_run_dispatch_retry_structural_breaks_without_retry` 覆蓋，不重複）。last_error
   斷言從比對 retMsg "duplicate" 改為比對 ret_code==110001。

兩處皆誠實改為新預期行為，不為了綠保留舊斷言。

## 六、新測試清單（5 個，dispatch_tests.rs）

| 測試 | 斷言 |
|---|---|
| `test_close_dup_is_idempotent_success_close_10001_duplicate_true` | close+10001-dup → true（含大寫變體）|
| `test_close_dup_is_idempotent_success_open_10001_duplicate_false` | **open+10001-dup → false（open fail-closed 關鍵 + 對抗驗證註記）** |
| `test_close_dup_is_idempotent_success_close_10001_non_duplicate_false` | close+10001-非dup（格式錯/qty 非法）→ false |
| `test_10001_duplicate_does_not_trigger_local_position_convergence` | noop_is_exchange_zero_position(10001-dup) → false（不收斂倉）|
| （classify uppercase）`test_classify_duplicate_order_link_id_10001_is_structural` 新增 | 10001-dup lowercase+uppercase → Structural |

既有 110072 測試群（close→true / open→false / 其他碼→false / 非-Business→false /
不收斂 / open-retry-budget 不變）全保留全綠。

## 七、真實測試結果

- `cargo build -p openclaw_engine --lib` → Finished（17.61s，3 pre-existing warning，
  皆別檔 dead_code，與本改動無關）。
- `cargo test -p openclaw_engine --lib event_consumer::dispatch` → **56 passed / 0 failed**。
- `cargo test -p openclaw_engine --lib`（full）→ **3769 passed / 0 failed / 1 ignored**
  （基線 3764 + 5 新測試）。
- crate-wide grep `10001`：`bybit_rest_client` 的 `BybitRetCode`/`is_4xx`/`is_noop` 是
  **獨立** client 層分類器（10001→4xx client fault；`is_noop` 集合 110001/110008 等
  不含 10001），與 dispatch `classify_business_retcode` 無耦合；`tasks.rs`/`startup`/
  `account_manager` 的 `10001 + 空 retMsg` 是 fee-rate seed_default 與 duplicate 無關
  → **0 個其他 caller 依賴舊 10001+dup→NoOp 行為**。
- Python：`py_compile` OK；`pytest test_closed_pnl_pagination.py` → **35 passed**
  （17 個 orderLinkId/engine 映射相關全綠）；import sanity 驗 module-level
  `_ENGINE_BY_TAG` 初始化正確 + `lv`→`live` 不誤判 demo（污染 live 訂單歸屬風險點）。

## 八、治理對照

- 硬邊界 grep：diff additions 無 `max_retries`/`live_execution_allowed`/
  `execution_authority`/`system_mode` 實際修改（僅註釋/測試提及 OPEN_NO_RETRY /
  noop_is_exchange_zero_position 字面解釋為什麼不碰 + negative assertion 鎖不收斂）。
  無 `/home/ncyu`/`/Users/` 硬編碼。
- 與 #6 / 110072 對齊：classify 預設 Structural 保護 open fail-closed；close 冪等
  upgrade 由 consumption 層 is_close guard 處理（單一 SSOT helper）。
- Root Principle 5（survival）/ 硬邊界「Bybit nonzero retCode fails closed；不加 hidden
  retry」：open path 改為 fail-closed（之前 fail-open silent success），收緊符合方向。
- 注釋：新增/修改註釋默認中文（bilingual-comment-style）；技術識別符（retCode/
  DispatchOutcome/order_link_id/duplicate）保留英文。

## 九、不確定之處 / 交 E2/BB/E4

1. **clippy 既有債（非我引入）**：`cargo clippy -p openclaw_engine` 撞
   `openclaw_core/src/risk/price_tracker.rs:132` deprecated_semver error
   （`since = "2026-04-22"` 非 semver，rust-1.95.0 clippy 變嚴 deny）。`price_tracker.rs`
   vs origin/main 空 diff = pre-existing 別 crate 債。它 deny 阻斷 openclaw_core 編譯，
   使 `cargo clippy -p openclaw_engine` 跑不到我的 dispatch.rs（engine 依賴 core）。
   build/test 不受影響（lint-only）。我的 dispatch 改動：clippy 第一輪 warning 列表
   0 條指向 dispatch.rs。**建議 E4 在 Linux 跑 full regression（authoritative）；
   clippy core 既有債需另開 follow-up（不在本任務範圍）**。
2. **E4 Linux regression owed**：Mac build/test 全綠，但 authoritative 環境在 Linux
   trade-core，按工作流需 E4 Linux cargo regression 確認 exit 0。
3. **info! log 加 ret_code/ret_msg**：consumption Structural success 分支原 log 寫死
   "110072"，follow-up 後該分支也接 10001+dup，寫死字面會誤記。去掉字面後加 ret_code/
   ret_msg 提取以保留 observability 區分性。這是 log 正確性的必要補償，非範圍外優化；
   請 E2 確認此判斷。

## 十、Operator 下一步

1. E2 審查（重點：observable 行為對照表、2 個改寫的既有測試是否誠實反映新預期、
   helper match 邏輯、log 訊息改動）。
2. BB 審查（exchange-facing：10001+dup 與 110072 對齊的 retCode 語義、open fail-closed
   正確性、不碰收斂/retry）。
3. E4 Linux cargo regression。
4. QA → PM 統一 cherry-pick 到 main + push（不直接 commit）。

E1 IMPLEMENTATION DONE: 待 E2 審查（report path:
docs/CCAgentWorkSpace/E1/workspace/reports/2026-06-07--e1_10001_duplicate_followup.md）
