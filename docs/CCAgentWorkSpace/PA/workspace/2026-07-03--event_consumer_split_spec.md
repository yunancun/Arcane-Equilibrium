# event_consumer 熱檔拆分 spec（純機械搬移，零邏輯改動）

- 日期：2026-07-03　角色：PA　狀態：E1-READY
- 基準：HEAD `2bc69697c`（event_consumer/ 目錄 worktree==HEAD，已驗 `git status` 乾淨）
- 目標：`tests/structure/test_event_consumer_split_static.py` 轉綠——dispatch.rs 1108 / dispatch_tests.rs 1008 / loop_handlers.rs 1541 全部降至 ≤800 且**每檔留 ≥30 行餘量**；新檔同樣 ≤800。
- 承接：E1 triage 報告 `docs/CCAgentWorkSpace/E1/workspace/reports/2026-07-03--static_test_red_seven_triage_fix.md` #5 節。
  **PA 修正 E1 初診斷兩處**：①dispatch.rs 只抽 ~315 行 → 793 行太貼線，擴大為 424 行全簇；
  ②loop_handlers 兩刀（E1 的 ~634 行估算誤把 inline tests 算進 handle_tick_event）→ 實際需三刀（Arm D/E/F 各自成檔），否則留檔 842 行仍紅。

---

## 0. 鐵則（E1 逐字遵守）

1. **除 visibility / use / mod / re-export 佈線外，一行邏輯都不許動**。搬移的每個 block 函數體/註釋/常量值逐位元組不變（含 `OPEN_NO_RETRY`、`classify_business_retcode` 的 `_ => Structural` fail-closed default、BB MANDATORY guard 全文——這些是硬邊界相鄰代碼，E2 將以 `git diff --color-moved=dimmed-zebra` 驗純移動）。
2. 唯一允許的新增文本：新檔 module doc header、use 區塊、re-export 行、mod.rs 的 mod 行、`#[cfg(test)] #[path]` mount、以及 dispatch_retcode_tests.rs 內 `biz()` fixture 的一份複製（見 §3.2，唯一許可的重複）。
3. 不碰：`lib.rs`、`tick_pipeline/`、`demo_learning_lane*`（IMPL-A 在製髒檔）、`event_consumer/tests/` 目錄任何檔、`loop_exchange.rs`、`bootstrap.rs`。
4. 行號以 HEAD `2bc69697c` 為準；動手前先 `git rev-parse HEAD` 比對，若 HEAD 已前移，以各 block 的「起訖內容錨」重新定位（每個 block 均附錨文字）。

## 1. 命名（定論）

| 新檔 | 來源 | 內容 |
|---|---|---|
| `dispatch_retcode.rs` | dispatch.rs | retcode 分類 + 重試機械（純決策，無 channel 副作用） |
| `dispatch_retcode_tests.rs` | dispatch_tests.rs | 分類/重試簇測試，經 `#[path]` mount 於 dispatch_retcode.rs |
| `loop_pending_registration.rs` | loop_handlers.rs | Arm D `handle_pending_registration` + 其私有 decision helper |
| `loop_pipeline_command.rs` | loop_handlers.rs | Arm E `handle_pipeline_command` |
| `loop_tick.rs` | loop_handlers.rs | Arm F `handle_tick_event` |

理由：dispatch_* 沿 E1 建議；loop_* 三檔沿既有 arm-per-file 慣例（先例 loop_exchange.rs = Arm C）。

## 2. dispatch.rs → dispatch_retcode.rs（搬 424 行）

### 2.1 搬移 block（源行號 @HEAD，全部 cut 到新檔，順序保持）

| Block | 行 | 行數 | 內容 | 起錨 / 訖錨 |
|---|---|---|---|---|
| M1 | 24-60 | 37 | banner「Retry policy (DISPATCH-RETRY-1…)」+ `OPEN_NO_RETRY` + `CLOSE_RETRY_DELAY_MS` + `CLOSE_ATTEMPT_TIMEOUT_MS` + `dispatch_retry_delays_for_intent` | `// ------…`（L24）/ `}`（L60，delays helper 收尾） |
| M2 | 143-196 | 54 | `DispatchOutcome` enum + `DispatchRetryResult<T>` enum | `/// Classification of a dispatch error…`（L143）/ `}`（L196） |
| M3 | 198-420 | 223 | `classify_dispatch_error` + `classify_business_retcode` + `noop_is_exchange_zero_position` + `noop_is_reduce_only_close` + `close_dup_is_idempotent_success` | `/// Classify a Bybit API error…`（L198）/ `}`（L420） |
| M4 | 489-598 | 110 | `close_dispatch_timeout_error` + `run_dispatch_retry` | `fn close_dispatch_timeout_error(`（L489）/ `}`（L598） |

**留在 dispatch.rs**（不動）：L1-23 header/uses、L62-141（`send_decision_lease_release` / `close_maker_audit_for_dispatch_req` / `send_close_maker_dispatch_failed`）、L422-487（`send_exchange_zero_close`）、L600-1100（`spawn_order_dispatch`）、L1102-1108（test banner + `#[cfg(test)] #[path = "dispatch_tests.rs"] mod tests;` ← 靜態測試要求此字串留在 dispatch.rs）。

### 2.2 新檔 dispatch_retcode.rs 骨架

```rust
//! Bybit dispatch retcode 分類 + 重試策略機械 — 自 dispatch.rs 拆出
//! （EVENT-CONSUMER-SPLIT-2，2026-07-03；§九 800 行治理）。
//! 純決策邏輯，無 channel 副作用；事件發送 helper（send_*）仍在 dispatch.rs。

use crate::bybit_rest_client::BybitApiError;
use crate::tick_pipeline::OrderDispatchRequest;
use std::time::Duration;
use tracing::{debug, warn};

<M1><M2><M3><M4 原文>

// ---------------------------------------------------------------------------
// Tests / 測試
// ---------------------------------------------------------------------------

#[cfg(test)]
#[path = "dispatch_retcode_tests.rs"]
mod tests;
```

依賴自足性已親驗：M1-M4 僅引用 `BybitApiError` / `OrderDispatchRequest` / `Duration` / `tracing::{debug,warn}` / 全限定 `serde_json::json!`・`tokio::time::sleep`；不引用 dispatch.rs 任何留守項。

### 2.3 visibility 最小調整（唯一清單，逐項）

| 項目 | 原 | 新 | 原因 |
|---|---|---|---|
| `noop_is_exchange_zero_position` | `fn` | `pub(super) fn` | dispatch.rs `send_exchange_zero_close` 跨 sibling 呼叫 + dispatch_tests 留守測試（L380/L441）引用 |
| `noop_is_reduce_only_close` | `fn` | `pub(super) fn` | dispatch.rs `send_exchange_zero_close` 呼叫 |
| `close_dup_is_idempotent_success` | `fn` | `pub(super) fn` | dispatch.rs `spawn_order_dispatch` Structural 分支 + 留守測試 |
| `close_dispatch_timeout_error` | `fn` | `pub(super) fn` | dispatch.rs spawn closure 呼叫 |
| `classify_business_retcode` | `fn` | `fn`（不變） | 唯一 caller `classify_dispatch_error` 同檔；child test mod 可及私有項 |
| 其餘（consts / enums / classify_dispatch_error / run_dispatch_retry / delays helper） | `pub(super)` | `pub(super)`（不變） | sibling 深度相同，`pub(super)` = `pub(in event_consumer)` 語意等價 |

### 2.4 dispatch.rs 佈線（re-export，鏡像 loop_exchange 先例）

在既有 use 區塊後（原 L22 之後）插入：

```rust
// EVENT-CONSUMER-SPLIT-2（2026-07-03）：retcode 分類 + 重試機械拆至 sibling
// dispatch_retcode.rs（§九 800 行治理）。pub(super) re-export 保持本檔函數體
// 與 dispatch_tests.rs 的引用路徑逐字不變（鏡像 loop_exchange.rs 先例）。
pub(super) use super::dispatch_retcode::{
    close_dispatch_timeout_error, close_dup_is_idempotent_success,
    dispatch_retry_delays_for_intent, noop_is_exchange_zero_position, noop_is_reduce_only_close,
    run_dispatch_retry, DispatchRetryResult, CLOSE_ATTEMPT_TIMEOUT_MS,
};
// OPEN_NO_RETRY 僅 dispatch_tests.rs（留守測試 L453）引用 → test-only re-export，
// 避免非 test build unused-import 警告（鏡像 loop_handlers.rs 對 unattributed_emit
// 的 #[cfg(test)] pub(super) use 先例）。
#[cfg(test)]
pub(super) use super::dispatch_retcode::OPEN_NO_RETRY;
```

re-export 集 = dispatch.rs 本體 + dispatch_tests.rs 留守測試實際消費的 9 項（已逐一 grep）；`classify_dispatch_error` / `DispatchOutcome` / `CLOSE_RETRY_DELAY_MS` **不** re-export（其消費者全數搬到 dispatch_retcode 側，多餘 re-export 會觸發 unused-import 警告）。

佈線後 dispatch.rs 函數體零改動：`send_exchange_zero_close` / `spawn_order_dispatch` 內對搬移項的非限定引用經 re-export 原樣解析。

另一處必要修整：`use tracing::{debug, error, info, warn};` → `use tracing::{error, info, warn};`（`debug!` 唯一使用點 `run_dispatch_retry` 已搬走）。其餘 import 全部保留（逐一驗過仍被留守代碼使用）。

### 2.5 行數預算

- dispatch.rs：1108 − 424 + ~11（re-export 塊）≈ **695**（餘量 ~105）
- dispatch_retcode.rs：424 + ~17（header/uses/mount）≈ **441**

## 3. dispatch_tests.rs → dispatch_retcode_tests.rs（搬 578 行）

### 3.1 搬移 block（cut 到新檔，順序保持）

| Block | 行 | 行數 | 內容 | 起錨 / 訖錨 |
|---|---|---|---|---|
| T1 | 122-300 | 179 | `test_retry_delay_constants`、`test_dispatch_retry_delays_helper_*`、classify 系列（transport/json/no_credentials/signing/client_side/10006/10001-duplicate/10001-param/10003/110001/110009/110017/110001+110009 回歸/110072） | `#[test]`（L122）/ `}`（L300） |
| T2 | 457-571 | 115 | classify 系列（110012/110043/170124/10016 族/99999/170210/10004/10010）+ banner + 10001-format/10002 三測 | `#[test]`（L457）/ `}`（L571） |
| T3 | 573-856 | 284 | loop-level banner + `test_run_dispatch_retry_*` 六測 + open 單次嘗試兩測 + `test_close_retry_delay_constants` + `test_close_attempt_timeout_constant_is_500ms` + `test_close_dispatch_timeout_error_is_transient` | `// Loop-level tests…`（L573）/ `}`（L856） |

**留在 dispatch_tests.rs**：L1-120（uses + `biz()` + `close_maker_dispatch_req` fixture + 2 個 close-maker preflight 測試）、L302-455（`close_dup_is_idempotent_success` 系列 + `noop_is_exchange_zero_position` 收斂抑制兩測 + `test_open_retry_budget_unchanged_after_110072_change`）、L858-1008（`close_dispatch_req_for_zero` fixture + `send_exchange_zero_close` guard 六測）。

**為什麼 close_dup/noop 測試留守而不隨函數搬**（定論）：(a) 它們與 send_exchange_zero_close 測試共用 `close_dispatch_req_for_zero` fixture（38 行），留守使 fixture 保持單副本；(b) 它們驗的是 spawn_order_dispatch（留守）的 consumption 層契約；(c) 經 §2.4 re-export + 既有 `use super::*` 零改動可及。

### 3.2 新檔 dispatch_retcode_tests.rs 骨架

```rust
//! Dispatch retcode 分類 + 重試迴圈測試（自 dispatch_tests.rs 拆出，
//! EVENT-CONSUMER-SPLIT-2，2026-07-03）。mount 於 dispatch_retcode.rs。

use super::*;
use crate::bybit_rest_client::BybitApiError;
use serde_json::json;

/// Build a Business error helper for tests.
/// 測試輔助：構造 Business 錯誤。（與 dispatch_tests.rs 的 biz() 同文複製 —
/// 兩測試模組樹各自私有，跨模組共享 test fixture 的 visibility 成本高於 9 行複製。）
fn biz(ret_code: i64, ret_msg: &str) -> BybitApiError { …同文… }

<T1><T2><T3 原文>
```

已親驗 T1-T3 依賴閉包：僅需 `biz` + `classify_dispatch_error` / `DispatchOutcome` / `DispatchRetryResult` / `run_dispatch_retry` / 三 consts / `dispatch_retry_delays_for_intent` / `close_dispatch_timeout_error`（全在 super=dispatch_retcode 本模組）+ `Duration`（經 `use super::*` 取得 dispatch_retcode 的私有 import，機制與今日 dispatch_tests 取 `mpsc` 相同）+ 全限定 `reqwest::` / `tokio::` / `serde_json::from_str` / `std::cell::RefCell`。**不**需要 `OrderDispatchRequest` / `mpsc` / 兩個 request fixture。

### 3.3 行數預算

- dispatch_tests.rs：1008 − 578 = **430**
- dispatch_retcode_tests.rs：578 + ~18 ≈ **596**（餘量 ~200）

## 4. loop_handlers.rs → 三新檔（搬 995 行）

### 4.1 搬移 block

| Block | 行 | 行數 | 去向 | 起錨 / 訖錨 |
|---|---|---|---|---|
| M5a | 173-189 | 17 | loop_pending_registration.rs | `fn dispatch_failed_close_maker_fallback_decision(`（L173）/ `}`（L189）；唯一 caller 在 Arm D（L499，已 grep 全 crate 證實）→ 隨遷且**保持私有 fn** |
| M5b | 277-635 | 359 | loop_pending_registration.rs | Arm D banner `// ────…`（L277）/ `}`（L635，`handle_pending_registration` 收尾） |
| M6 | 637-885 | 249 | loop_pipeline_command.rs | Arm E banner（L637）/ `}`（L885，`handle_pipeline_command` 收尾） |
| M7 | 889-1258 | 370 | loop_tick.rs | Arm F banner（L889）/ `ControlFlow::Continue(())` + `}`（L1257-1258） |

**留在 loop_handlers.rs**：L1-31 header/uses（修整見 §4.4）、L33-95（`LoopState` + `pending_order_accepts_fill`）、L97-171（`dispatch_close_maker_fallback_from_pending`）、L191-197（`#[cfg(test)] pub(super) use super::unattributed_emit::{…}`）、L199-275（Arm A + Arm B）、**L887 `pub(super) use super::loop_exchange::handle_exchange_event;`（靜態測試逐字要求）**、L1260-1541（inline `mod tests` 全部——含 wall-clock 測試；該測試自足不引用 handle_tick_event，其 banner 內 `loop_handlers.rs:823-828` 行號引用在 HEAD 即已 stale（實際 L947-953），**不修**，遵守 surgical-change 原則）。

三個 arm handler fn 簽名 visibility 均維持 `pub(super)` 不變。

### 4.2 新檔骨架（import 區塊逐字給定）

`loop_pending_registration.rs`（≈385 行）：

```rust
//! Arm D handler — dispatch task 的 pending order 註冊/終態事件，自
//! loop_handlers.rs 拆出（EVENT-CONSUMER-SPLIT-2，2026-07-03；§九 800 行治理）。

use super::loop_handlers::{dispatch_close_maker_fallback_from_pending, LoopState};
use super::types::{PendingOrder, PendingOrderEvent};
use crate::order_manager::TimeInForce;
use crate::strategies::maker_rejection::{CloseMakerFallbackReason, CloseMakerRateLimitScope};
use crate::tick_pipeline::TickPipeline;

<M5a><M5b 原文>
```

`loop_pipeline_command.rs`（≈258 行）：

```rust
//! Arm E handler — IPC PipelineCommand 派遣，自 loop_handlers.rs 拆出
//! （EVENT-CONSUMER-SPLIT-2，2026-07-03；§九 800 行治理）。

use std::sync::Arc;

use super::handlers;
use super::loop_handlers::LoopState;
use crate::persistence::DualStateWriter;
use crate::tick_pipeline::{EngineEvent, PipelineCommand, PipelineKind, TickPipeline};

<M6 原文>
```

`loop_tick.rs`（≈384 行）：

```rust
//! Arm F handler — 主 tick 事件熱路徑，自 loop_handlers.rs 拆出
//! （EVENT-CONSUMER-SPLIT-2，2026-07-03；§九 800 行治理）。

use std::collections::HashMap;
use std::ops::ControlFlow;
use std::sync::Arc;
use std::time::{Duration, Instant};

use super::loop_handlers::{dispatch_close_maker_fallback_from_pending, LoopState};
use super::pending_sweep::{self, classify_pending_sweep, PendingSweepAction};
use crate::order_manager::TimeInForce;
use crate::persistence::{AuditWriter, DualStateWriter, StateWriter};
use crate::strategies::maker_rejection::CloseMakerFallbackReason;
use crate::tick_pipeline::TickPipeline;

<M7 原文>
```

關鍵便利事實：三個 arm body 內的 `super::sm_halt_incident::…`、`super::status_report::…`、`pending_sweep::…` 等引用**逐字仍有效**——新檔與 loop_handlers.rs 同為 event_consumer 直接子模組，`super::` 解析目標不變。搬移跨的是同父 sibling 邊界，除 loop_handlers/dispatch 自身私有項（已在 §2.3/§4.1 枚舉）外，所有 `crate::` / `super::` 可見性關係自動保持。

### 4.3 loop_handlers.rs 佈線（相容 re-export）

在原 L887 的 loop_exchange re-export 旁追加（既有行不動）：

```rust
// EVENT-CONSUMER-SPLIT-2（2026-07-03）：Arm D/E/F 拆至 sibling 檔（§九 800 行
// 治理）。pub(super) re-export 保持 mod.rs 與 event_consumer/tests/* 的
// `loop_handlers::handle_*` 呼叫路徑不變（鏡像 loop_exchange.rs 先例）。
pub(super) use super::loop_pending_registration::handle_pending_registration;
pub(super) use super::loop_pipeline_command::handle_pipeline_command;
pub(super) use super::loop_tick::handle_tick_event;
```

**這三行不可 `#[cfg(test)]` gate**：mod.rs（非 test 代碼）經 `loop_handlers::handle_pipeline_command` / `handle_tick_event` / `handle_pending_registration` 呼叫（mod.rs L170/L183/L196）。同時 event_consumer/tests/ 的 earn_ipc_tests.rs（L17/L83）與 pending_registration_order_type_tests.rs（L31 起 20+ 呼叫點）也經此路徑消費——re-export 缺一即編譯斷（fail-loud）。

### 4.4 loop_handlers.rs use 區塊修整（搬移後 unused 清理，逐行給定）

- 刪：`use std::ops::ControlFlow;`（L21，僅 Arm F）
- 刪：`use std::sync::Arc;`（L22，僅 Arm E/F）
- 刪：`use super::handlers;`（L25，僅 Arm E）
- 刪：`use super::pending_sweep::{self, classify_pending_sweep, PendingSweepAction};`（L26，僅 Arm F）
- 刪：`use crate::persistence::{AuditWriter, DualStateWriter, StateWriter};`（L29，僅 Arm E/F）
- 改：L23 → `use std::time::Instant;`（Duration 僅 Arm F 具名使用）
- 改：L27 → `use super::types::PendingOrder;`（PendingOrderEvent 僅 Arm D）
- 改：L31 → `use crate::tick_pipeline::{EngineEvent, PipelineKind, TickPipeline};`（PipelineCommand 僅 Arm E）
- 留：L20（HashMap/HashSet ← LoopState）、L28（TimeInForce ← fallback helper）、L30（maker_rejection 雙型 ← fallback helper 簽名）

以 cargo 實測為終審：若仍有 unused-import 警告，按警告修 import 行（僅 import 行，不動其他）。

### 4.5 行數預算

- loop_handlers.rs：1541 − 995 + ~6 − ~4 ≈ **548**（餘量 ~250）
- 三新檔見 §4.2（最大 ~385，餘量 >400）

## 5. mod.rs diff（僅加 mod 行，字母序插入）

`mod dispatch;` 之後插：

```rust
// EVENT-CONSUMER-SPLIT-2（2026-07-03）：dispatch.rs retcode 分類簇拆出（§九 800 行治理）。
mod dispatch_retcode;
```

`mod loop_handlers;` 之後插：

```rust
// EVENT-CONSUMER-SPLIT-2（2026-07-03）：Arm D/E/F 自 loop_handlers.rs 拆出（§九 800 行治理）。
mod loop_pending_registration;
mod loop_pipeline_command;
mod loop_tick;
```

`mod loop_exchange;` 一行**不動**（靜態測試逐字斷言）。mod.rs 的 select! 呼叫點全部零改動（經 §4.3 re-export）。

## 6. 靜態測試同步（tests/structure/test_event_consumer_split_static.py）

### 6.1 cap 測試（治理面擴大，不縮小；閾值 800 不動）

```python
def test_event_consumer_hot_files_stay_split_under_limit() -> None:
    governed = {
        "dispatch.rs",
        "dispatch_retcode.rs",
        "dispatch_retcode_tests.rs",
        "dispatch_tests.rs",
        "loop_exchange.rs",
        "loop_handlers.rs",
        "loop_pending_registration.rs",
        "loop_pipeline_command.rs",
        "loop_tick.rs",
    }
    modules = {name: _loc(EVENT_CONSUMER / name) for name in governed}
    for name in sorted(modules):
        assert modules[name] <= 800, f"{name} = {modules[name]} LOC > 800"
```

（原 4 檔全保留 + 新 5 檔加入；由逐條 assert 改 loop 帶檔名訊息，斷言語意不變且更可診斷。）

### 6.2 compatibility exports 測試（原 4 斷言逐字保留，追加以下）

```python
    retcode_text = (EVENT_CONSUMER / "dispatch_retcode.rs").read_text(encoding="utf-8")
    pending_reg_text = (EVENT_CONSUMER / "loop_pending_registration.rs").read_text(encoding="utf-8")
    pipeline_cmd_text = (EVENT_CONSUMER / "loop_pipeline_command.rs").read_text(encoding="utf-8")
    tick_text = (EVENT_CONSUMER / "loop_tick.rs").read_text(encoding="utf-8")

    # mod 佈線
    assert "mod dispatch_retcode;" in mod_text
    assert "mod loop_pending_registration;" in mod_text
    assert "mod loop_pipeline_command;" in mod_text
    assert "mod loop_tick;" in mod_text

    # dispatch façade：re-export + 測試 mount 雙軌
    assert "pub(super) use super::dispatch_retcode::" in dispatch_text
    assert '#[path = "dispatch_retcode_tests.rs"]' in retcode_text

    # loop_handlers façade：三 arm re-export + 新檔實體
    assert "pub(super) use super::loop_pending_registration::handle_pending_registration;" in loop_text
    assert "pub(super) use super::loop_pipeline_command::handle_pipeline_command;" in loop_text
    assert "pub(super) use super::loop_tick::handle_tick_event;" in loop_text
    assert "pub(super) fn handle_pending_registration(" in pending_reg_text
    assert "pub(super) async fn handle_pipeline_command(" in pipeline_cmd_text
    assert "pub(super) fn handle_tick_event(" in tick_text
```

## 7. 驗證計劃

Mac（隔離 worktree，因主樹有 IMPL-A 髒 rust 檔，基線必須在隔離樹取）：

1. `git worktree add <scratch>/ec-split 2bc69697c`（或當時 origin/main tip）→ 於該樹先取**基線**：`cargo test -p openclaw_engine --lib` 記錄 `N passed / 0 failed` 與警告數。
2. 套用拆分 → `cargo build -p openclaw_engine` 零錯誤、無新警告（與基線比對）→ `cargo test -p openclaw_engine --lib` 斷言 **同 N passed / 0 failed**（測試只搬不增刪，總數必須逐一相等；判準看 `0 failed` 非籠統 test count 漂移）。
3. `cargo fmt -p openclaw_engine -- --check`（搬移塊原本 fmt-clean，位移不破壞；新 use 區塊按 rustfmt 慣例書寫）。
4. `python3 -m pytest tests/structure/ -q --import-mode=importlib` → 全綠（含本測試 2 passed，且不碰其他 structure 測試）。
5. `git diff --check`；`git diff --color-moved=dimmed-zebra` 目視全部搬移塊呈 moved 色（純移動證明，供 E2 復用）。
6. 提交：單一 commit，`git commit --only` 恰 10 檔（§9 清單），multi-session 紀律。

Linux trade-core（QA gate，PM 排程）：

7. origin/main 乾淨基礎上 `cargo build --release` + `cargo test -p openclaw_engine` 全量，與該機基線比對；因零行為改動，binary 可隨下次常規 `restart_all --rebuild` 週期部署，不需緊急重啟。

## 8. 風險清單（E1/E2 對照）

1. **`#[path]` mount 唯一性**：dispatch_retcode_tests.rs 只能由 dispatch_retcode.rs 的 `#[cfg(test)] #[path]` mount 一次；**嚴禁**放進 `event_consumer/tests/` 目錄或在 mod.rs 另掛（雙 mount = 符號重複編譯錯）。tests/ 目錄的 mod.rs 是顯式列舉制，本次不動它。
2. **cfg(test) gate 方向**：dispatch 的 `OPEN_NO_RETRY` re-export 必須 `#[cfg(test)]`（否則非 test build unused 警告）；loop_handlers 三 arm re-export 必須**不**帶 cfg（mod.rs 非 test 消費）。方向弄反其一即紅。
3. **glob-import 隱性依賴**：兩個測試檔靠 `use super::*` 取得宿主模組的私有 import（現況 `mpsc`/`Duration` 即如此）。dispatch_retcode.rs 的 use 區塊須含 `std::time::Duration`（§2.2 已釘死），E1 不得「順手精簡」任何宿主 import。
4. **跨模組私有依賴已全枚舉**：§2.3 四個 fn 升 `pub(super)`；`dispatch_failed_close_maker_fallback_decision` 隨遷保私有（全 crate grep 證唯一 caller 在 Arm D）。除此之外若 cargo 報 private-item 錯誤 = 定位錯 block 邊界，回頭對錨，不得擅自加 `pub`。
5. **event_consumer/tests/ 消費路徑**：earn_ipc_tests / pending_registration_order_type_tests / phantom_fill_ordering_tests / funding_settlement_tests / unattributed_fill_tests 全走 `super::super::loop_handlers::` — 由 §4.3 re-export 承接，這些檔零改動；若動了它們 = 越界。
6. **同名異物**：`crate::notification_failsafe::DispatchOutcome` 是不同型別（已 grep 證實與本簇無關），E1 全域搜尋替換是禁手——本 spec 不需要任何搜尋替換。
7. **stale 註釋不修**：wall-clock 測試 banner 的 `loop_handlers.rs:823-828`、dispatch 各處 `dispatch.rs create_req` 等自引用文字在 HEAD 即已 stale/泛指，一律保留原文（surgical change；修註釋=擴 diff 面）。
8. **macro 使用處**：搬移塊內 `tracing::info!/warn!/error!` 全限定或經新檔 use 覆蓋；`serde_json::json!` 全限定；無自定義 macro。已逐塊驗證。
9. **行數計法**：靜態測試用 `splitlines()`（≈ `wc -l`），新檔務必以 pytest 實跑為準，不心算。

## 9. 改動閉包（恰 10 檔）

| # | 檔 | 動作 | 預估 LOC |
|---|---|---|---|
| 1 | rust/openclaw_engine/src/event_consumer/mod.rs | +6 行（mod×4+註釋） | ~302 |
| 2 | …/dispatch.rs | −424 +11 | ~695 |
| 3 | …/dispatch_retcode.rs | 新檔 | ~441 |
| 4 | …/dispatch_tests.rs | −578 | ~430 |
| 5 | …/dispatch_retcode_tests.rs | 新檔 | ~596 |
| 6 | …/loop_handlers.rs | −995 +6 −4 | ~548 |
| 7 | …/loop_pending_registration.rs | 新檔 | ~385 |
| 8 | …/loop_pipeline_command.rs | 新檔 | ~258 |
| 9 | …/loop_tick.rs | 新檔 | ~384 |
| 10 | tests/structure/test_event_consumer_split_static.py | §6 diff | ~75 |

## 10. 降級 / rollback 路徑

- **Rollback = 單 commit `git revert`**。純 crate 內模組重排：0 schema / 0 config / 0 IPC contract / 0 API surface / 0 部署腳本耦合；revert 後回到當前紅測狀態（僅 #5 紅），無運行時後果。
- 零行為改動 ⇒ 不需伴隨緊急 engine 重啟；Linux 若全量測試出意外（理論上只可能是編譯/測試計數差異），在 main 上 revert 即止血，Mac worktree 留診斷現場。
- 不存在「半套用」中間態風險：單 commit 原子落地，落地前 worktree 內全綠 gate（§7 步驟 1-5）不可跳。

## 11. E1 派發計劃

- **單一 E1，單一 commit**。不拆兩個 E1 並行：mod.rs 與靜態測試檔是共同交點，且 dispatch 側/loop 側均 ~1-2h 純機械量，並行收益 < 交點衝突成本。
- 建議 commit subject：`refactor(event_consumer): split dispatch retcode cluster + loop arms D/E/F to sibling files (EVENT-CONSUMER-SPLIT-2) — zero logic change`。
- **時序（PM 決策點）**：event_consumer/ 當前乾淨，PA 建議**儘速落地**（拆分 diff 大，拖延風險 = IMPL-A 或他線長進這三檔後需重對行號）；落地前 PM 與 IMPL-A owner 確認其在製計劃不含 event_consumer/——若含，改為其 merge 後執行（E1 triage 報告原建議），並由 E1 對新 HEAD 以內容錨重定位行號。
- NO-OP exit：若接手時發現三熱檔已 ≤800（他線已拆），驗靜態測試綠後 NO-OP 退出並回報。

## 12. E2 重點審查（3 點）

1. **純移動證明**：`git diff --color-moved=dimmed-zebra` 全部搬移塊呈 moved；重點逐字比對硬邊界相鄰體——`OPEN_NO_RETRY` 值與註釋、`classify_business_retcode` 的 `_ => Structural` fail-closed default、110017/110072 BB MANDATORY guard 註釋與條件、`CLOSE_RETRY_DELAY_MS = [100, 400]`。任何非 use/mod/visibility 的字元差異 = RETURN。
2. **visibility 收口**：升級恰好 §2.3 列出的 4 個 fn 且只升到 `pub(super)`；無任何 `pub`（crate 級）或 `pub(crate)` 蔓延；`OPEN_NO_RETRY` re-export 帶 `#[cfg(test)]` 而三 arm re-export 不帶。
3. **治理方向**：靜態測試 cap 集合 = 9 檔（只增不減）、閾值仍 800；compatibility 測試原 4 斷言逐字仍在；`cargo test --lib` passed 數與基線嚴格相等（測試只遷不刪——特別驗 dispatch_retcode_tests 內測試數 + dispatch_tests 留守數 = 原 dispatch_tests 總數）。

— PA，2026-07-03（HEAD 2bc69697c；grep 證據見本檔各節內嵌 file:line）
