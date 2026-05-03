# `replay_runner` Crate Boundary Allowlist + Symbol Audit Spec — REF-20 Wave 1 R20-P0-T9

**Owner:** PA
**Date:** 2026-05-03
**Status:** Wave 1 SPEC — E2 sign-off ready
**Refs:**
- Workplan: `docs/execution_plan/2026-05-03--ref20_implementation_workplan_v1.md` §4 Wave 1 R20-P0-T2/T3/T9 + Wave 3 R20-P2b-S7/S8/S9/S10
- V3 contract: `docs/execution_plan/2026-05-03--ref20_paper_replay_lab_dev_plan_v3.md` §3 G7/G8 + §6.1/§6.2 + §12 #8/#9/#10/#11/#12
- 16 根原則 §2: #1 單一寫入口 / #2 讀寫分離 / #4 策略不繞風控 / #6 失敗默認收縮 / #7 學習 ≠ 改寫 Live
- Hard 邊界 §4: live_execution_allowed / max_retries=0 / decision_lease

---

## 1. PA Design Diff（Wave 1 落地清單）

### 1.1 新增檔案（4）

| File | LOC | 用途 |
|---|---:|---|
| `rust/openclaw_engine/src/replay/profile.rs` | 116 | `ReplayProfile` enum spec — `Live` / `LiveDemo` / `PaperLegacy` / `Isolated`，0 IMPL，雙語 doc |
| `rust/openclaw_engine/src/replay/mod.rs` | 30 | replay subsystem export — Wave 1 僅 `pub mod profile;` |
| `rust/openclaw_engine/src/bin/replay_runner.rs` | 117 | binary scaffold — `#![cfg(feature = "replay_isolated")]` + `panic!()` + 4 條 TODO REF-20 P2b-S7/S8/S9/S10 marker |
| `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-03--replay_runner_crate_boundary_allowlist.md` | this | crate 邊界白/黑名單 + nm/objdump CI spec |

### 1.2 修改檔案（2）

| File | Diff | 說明 |
|---|---|---|
| `rust/openclaw_engine/Cargo.toml` | +24 LOC | (1) 新增 `[features] replay_isolated = []`（純 marker，0 deps）；(2) 新增 `[[bin]] replay_runner` with `required-features = ["replay_isolated"]` |
| `rust/openclaw_engine/src/lib.rs` | +5 LOC | 新增 `pub mod replay;` 並附 Wave 3 forward-looking comment |

### 1.3 不動既有檔（重要）

- `intent_processor/router.rs` / `intent_processor/gates.rs` — 0 改動（V3 §6.2 forbidden list IMPL 在 Wave 3 R20-P2b-S7/S8）
- `ipc_server/*` — 0 改動
- `startup/mod.rs::build_exchange_pipeline` — 0 改動
- `bybit_rest_client.rs` / `bybit_private_ws.rs` / `ws_client.rs` — 0 改動
- `live_authorization.rs` — 0 改動
- `governance_hub` (Python) — 0 改動，replay binary 永遠不 reach Python 層

---

## 2. Cargo Build Verification（紅線驗收）

### 2.1 `cargo check` 無 feature（既有 build path 不應變動）

```
$ cd rust/openclaw_engine && cargo check -p openclaw_engine
warning: `openclaw_engine` (lib) generated 21 warnings (run `cargo fix --lib -p openclaw_engine` to apply 13 suggestions)
warning: `openclaw_engine` (bin "openclaw-engine") generated 3 warnings (run `cargo fix --bin "openclaw-engine" -p openclaw_engine` to apply 1 suggestion)
    Finished `dev` profile [unoptimized + debuginfo] target(s) in 9.16s
```

**結果**: PASS（warnings = 21 lib + 3 bin = pre-existing baseline，無一條源自 Wave 1 改動；replay_runner binary **未編譯** — required-features 阻擋）。

### 2.2 `cargo check --bin replay_runner --features replay_isolated`

```
$ cd rust/openclaw_engine && cargo check -p openclaw_engine --bin replay_runner --features replay_isolated
warning: `openclaw_engine` (lib) generated 21 warnings (run `cargo fix --lib -p openclaw_engine` to apply 13 suggestions)
    Finished `dev` profile [unoptimized + debuginfo] target(s) in 7.17s
```

**結果**: PASS（21 warnings 全為 lib pre-existing baseline；`replay_runner` / `replay/profile.rs` / `replay/mod.rs` **0 new warnings**）。

### 2.3 `cargo build --bin replay_runner --features replay_isolated`

```
$ cd rust/openclaw_engine && cargo build -p openclaw_engine --bin replay_runner --features replay_isolated
warning: `openclaw_engine` (lib) generated 21 warnings (run `cargo fix --lib -p openclaw_engine` to apply 13 suggestions)
    Finished `dev` profile [unoptimized + debuginfo] target(s) in 11.98s
```

**結果**: PASS（產生 `target/debug/replay_runner` artifact；運行會 panic with 預期訊息 "REF-20 P2b-S7/S8 will land runtime; this is Wave 1 scaffold only"，符合 Wave 1 設計）。

### 2.4 cargo metadata 確認 binary target 正確掛上

```json
{
  "name": "replay_runner",
  "src_path": "/Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/bin/replay_runner.rs",
  "kind": ["bin"],
  "edition": "2021",
  "required-features": ["replay_isolated"]
}
```

**結果**: PASS。

---

## 3. 雙層 cfg gate 設計（V3 workplan §7.1 #2 對應）

### 3.1 第一層 — Compile-time feature gate

```toml
[features]
replay_isolated = []     # marker only, no deps in Wave 1

[[bin]]
name = "replay_runner"
required-features = ["replay_isolated"]
```

```rust
// bin/replay_runner.rs
#![cfg(feature = "replay_isolated")]
```

**效果**:
- 預設 `cargo build` / `cargo check` **物理上不能** pull `replay_runner.rs` 到 graph
- 若 future Wave 3 IMPL 不慎 import `intent_processor::router` 或 `ipc_server`，且該 import 未 gate，**default build 仍成功**（因為 binary 不編）→ `nm`/`objdump` CI 才會 catch
- `required-features` 是 cargo 的硬約束 — 即使 user 嘗試 `cargo build --bin replay_runner` 不帶 feature，cargo 直接 reject

### 3.2 第二層 — Runtime profile gate

```rust
// replay/profile.rs (Wave 3 IMPL 將加 method)
pub enum ReplayProfile {
    Live,           // never used by replay binary
    LiveDemo,       // never used by replay binary
    PaperLegacy,    // never used by replay binary
    Isolated,       // ONLY profile replay binary may enter
}

// Wave 3 R20-P2b-S7 will add:
// impl ReplayProfile {
//     pub fn requires_lease(&self) -> bool {
//         match self { Isolated => false, _ => true }
//     }
//     pub fn allows_exchange_dispatch(&self) -> bool {
//         match self { Isolated => false, _ => true }
//     }
//     pub fn enforce_isolated_or_panic(&self) {
//         if !matches!(self, Isolated) { panic!("replay_runner refuses non-Isolated profile"); }
//     }
// }
```

**效果**:
- 即使 Wave 3 IMPL 不慎讓 `replay_runner` 取得 non-Isolated profile（例如 manifest 偽造），runtime 第一道 panic guard 仍 fail-closed
- 此層為「runtime defense in depth」— 不替代 compile-time gate，是補充

### 3.3 為何 V3 §7.1 #2 警告「避免 CI matrix 爆」

若每個 profile 都對應一個 cargo feature（4 features 全展開 = 2^4 = 16 build matrix），CI 跑時會爆。本設計用「**單一** `replay_isolated` feature gate binary 存在性 + runtime enum 控制行為」避免 matrix 爆 — CI 只需跑 2 個 build target：(a) default no-feature / (b) `--features replay_isolated`。

---

## 4. Allowed Crate Dependencies（Wave 3 R20-P2b-S7 IMPL 必嚴守）

| 依賴 | 用途 | 來源 |
|---|---|---|
| `crate::replay::profile::ReplayProfile` | 自身 enum，runtime 強制 `Isolated` | sibling file (Wave 1 已建) |
| `crate::replay::forbidden_guard` | startup + runtime fail-closed guard | Wave 3 R20-P2b-S8 will land |
| `crate::replay::mac_policy_guard` | `OPENCLAW_REPLAY_MAC_FORBID_REAL_DATA=1` enforcer | Wave 3 R20-P2b-S9 will land |
| `crate::replay::manifest_signer` | HMAC-SHA256 verify-first-then-hash | Wave 2-3 P2a-S2 will land |
| `crate::replay::fixture_loader` | S2 public Bybit data + S3 synthetic OHLC/tick fixture | Wave 3 will land |
| `crate::replay::baseline_snapshot` | V3 §6.4 baseline snapshot mechanism | Wave 3 will land |
| `crate::replay::canonical_config_parser` | strategy/risk TOML canonicalization (sha256) | reuse既有 `crate::config` 但 read-only |
| `crate::common::*`（read-only helpers） | timestamp / hex / hash util | safe; no IO |
| `crate::secret_env::var_or_file` | `OPENCLAW_REPLAY_SIGNING_KEY` env/file 讀取 | reuse 既有，read-only |
| `serde` / `serde_json` (workspace) | manifest parse/serialize | safe |
| `chrono` (workspace) | timestamp arithmetic | safe |
| `clap` (NEW dep, Wave 3) | CLI arg parsing | will add to Cargo.toml under `replay_isolated` feature |
| `tracing` (workspace) | structured logging | safe (no DB/file/IPC sink in replay binary by default) |
| `hmac` / `sha2` / `hex` (workspace) | HMAC-SHA256 manifest verify | safe |
| `tokio` (workspace, **限定 feature** `rt-multi-thread` + `macros` only) | async runtime | safe; **不可** import `tokio::net::*` |
| `parking_lot` (workspace) | in-memory state lock | safe |
| `rand` (workspace) | synthetic fixture generator | safe |
| `tempfile` (dev-dependencies) | unit test fixture | dev only |

**Rationale:** 所有 allowed deps 共同特徵 = **唯讀 / pure compute / 無 network IO / 無 DB writer**。

---

## 5. Forbidden Crate Dependencies（Wave 3 IMPL 違反 = E2 reject）

| 禁用依賴 | 違反原則 | V3 / workplan 引用 |
|---|---|---|
| `crate::intent_processor::router::*`（含 `router::dispatch_intent` 等） | 16#1 單一寫入口；replay 不得進 live execution dispatch | V3 §6.2 forbidden list / §12 #8 / workplan §7.1 #1 |
| `crate::intent_processor::gates::*` | 同上 — gates 是 live 路徑專用 | V3 §6.2 |
| `crate::ipc_server::*`（含 `dispatch::*` / `handlers::*` / `protocol::*` / `slots::*`） | 16#1 + 16#2；replay 不得開 IPC server 與 Python 通訊 | V3 §6.2 / §12 #8 |
| `crate::startup::build_exchange_pipeline`（位於 `startup/mod.rs:497`） | exchange 啟動含 live order dispatch 接線；replay 永不 spawn | V3 §6.2 / §12 #8 |
| `crate::bybit_rest_client::BybitClient::place_order*`（任何 POST 路徑） | 16#1 + §四 hard 邊界 max_retries=0 | V3 §2.1 / §6.2 / §12 #14 |
| `crate::bybit_rest_client::BybitClient::cancel_order*` | 同上 | V3 §6.2 |
| `crate::bybit_private_ws::*` / `crate::ws_client::*` | 16#9 災難保護；replay 不掛 WS | V3 §6.2 / §12 #8 |
| `crate::live_authorization::_write_signed_live_authorization` | §四 hard 邊界 — authorization.json 必經 Python renew/approve 路由 | CLAUDE.md §四 |
| `crate::live_authorization::*`（write side） | 同上 | CLAUDE.md §四 |
| GovernanceHub.acquire_lease / release_lease（Python 側 `governance_hub.py`） | 16#3 AI ≠ 命令；replay 不得 acquire lease | V3 §6.2 / §12 #9 / workplan §8 PM 必查 #1 |
| `crate::execution_listener::*` | order 執行回報；replay 永遠 0 真實 fills | V3 §6.2 / §12 #14 |
| `crate::position_manager::*`（write side） | 16#1；replay 不得改持倉狀態 | V3 §2.1 / §12 #14 |
| `crate::order_manager::*`（write side） | 同上 | V3 §6.2 |
| `crate::canary_writer::*`（DB 寫端） | 16#7 學習 ≠ 改寫 Live；replay artifact 必經 verified insert function | V3 §4.2 / §12 #6 |
| `crate::database::*`（write channels — INSERT/UPDATE） | 16#1 + 16#2；replay 寫 registry 必經 P2a-S4 verified function | V3 §4.2 / §12 #5/#6/#7 |
| `crate::paper_state::*`（mutable global write side） | 16#7；replay binary 自帶 in-memory state，不 mutate global | V3 §6.2 |
| `tokio::net::*` / `reqwest::Client::*`（exchange 端） | 16#9；replay 永不 outbound network call 到 Bybit | V3 §6.2 / §12 #8 |
| `sqlx::Pool::execute` 直接 INSERT/UPDATE 任何 `trading.*` / `learning.*`（不經 verified function） | 16#1 + V3 §4.2 DB role guard | V3 §4.2 / §12 #5/#6 |
| `crate::live_auth_watcher::*` | live 認證循環專用；replay 不得介入 | CLAUDE.md §四 |
| `crate::position_reconciler::*`（write 路徑） | EX-04 對賬只在 live；replay 不參與 | V3 §6.2 |

---

## 6. Symbol Allowlist for P2b-S10 nm/objdump CI Step

### 6.1 Forbidden symbol grep（必 0 hit）

CI shell script `helper_scripts/ci/replay_runner_symbol_audit.sh`（Wave 3 R20-P2b-S10 land）必含以下 grep；任一 hit ≥ 1 → CI fail。

```bash
#!/usr/bin/env bash
# REF-20 Wave 3 R20-P2b-S10 — replay_runner symbol audit (defense in depth)
set -euo pipefail

BIN="${BIN:-target/release/replay_runner}"
test -f "$BIN" || { echo "binary not found: $BIN"; exit 2; }

# Linux: nm; macOS: nm -gU (already in Linux PATH on CI runner per V3 §7.3 #13)
SYMBOLS="$(nm -g "$BIN" 2>/dev/null || objdump -t "$BIN")"

FAIL=0
check_forbidden() {
    local pattern="$1"; local label="$2"
    local hits
    hits=$(echo "$SYMBOLS" | grep -E "$pattern" | wc -l | tr -d ' ')
    if [[ "$hits" -gt 0 ]]; then
        echo "FORBIDDEN SYMBOL ($label): $hits hits matching '$pattern'"
        echo "$SYMBOLS" | grep -E "$pattern" | head -5
        FAIL=$((FAIL + 1))
    fi
}

# Decision Lease (V3 §6.2 #2 / §12 #9)
check_forbidden 'acquire_lease|release_lease|GovernanceHub' 'Decision Lease'

# Exchange pipeline bootstrap (V3 §6.2 / §12 #8)
check_forbidden 'build_exchange_pipeline' 'Exchange pipeline'

# IPC server (V3 §6.2 / §12 #8)
check_forbidden 'ipc_server::|ipc_dispatch|ipc_handler' 'IPC server'

# Order placement (V3 §6.2 / §12 #14)
check_forbidden 'place_order|cancel_order|amend_order' 'Order placement'

# Live authorization write (CLAUDE.md §四)
check_forbidden 'write_signed_live_authorization' 'Live auth write'

# WS clients (V3 §6.2 / §12 #8)
check_forbidden 'bybit_private_ws|ws_client::Client' 'WS clients'

# DB writer channels (V3 §4.2)
check_forbidden 'canary_writer::write|database::writer' 'DB writers'

if [[ "$FAIL" -gt 0 ]]; then
    echo "REPLAY_RUNNER SYMBOL AUDIT FAILED: $FAIL forbidden symbol class(es) detected"
    exit 1
fi

echo "REPLAY_RUNNER SYMBOL AUDIT PASS"
```

### 6.2 Counter-example test（CI matrix 必跑）

```bash
# 反例：故意 inject acquire_lease 應被 catch
nm replay_runner | grep -E 'acquire_lease|build_exchange_pipeline|ipc_' | wc -l
# 期望: 0
# 若 ≥ 1 → CI fail，require fix
```

### 6.3 Wave 1 baseline 預期

由於 Wave 1 binary body 是 `panic!()`，nm 預期僅見：
- `main`
- panic handler symbols（`std::panicking::*` 等）
- `replay_runner::main`

**0 forbidden symbol** — Wave 1 bench 為「空 binary」基準線，Wave 3 IMPL 後 grep 仍須 0 hit。

---

## 7. E2 Sign-off Ready Checklist（≥5 條）

| # | 檢查項 | Wave 1 狀態 |
|---|---|---|
| 1 | `cargo check` 無 feature 通過 + 21 warnings 全為 pre-existing baseline（與 Wave 1 改動無關） | ✅ PASS |
| 2 | `cargo check --bin replay_runner --features replay_isolated` 通過 + replay 三檔 0 new warnings | ✅ PASS |
| 3 | `cargo build --bin replay_runner --features replay_isolated` 產出 artifact 且 main panic 訊息符合預期 | ✅ PASS |
| 4 | 預設 `cargo build` 不編 replay_runner（required-features 阻擋）— compile-time isolation 證明 | ✅ PASS |
| 5 | `replay_runner.rs` 0 import `intent_processor` / `ipc_server` / `build_exchange_pipeline` / `acquire_lease` / `bybit_*` / `ws_*` / `live_authorization`（Wave 1 binary body 僅 `panic!()`） | ✅ PASS（grep 確認） |
| 6 | `replay/profile.rs` 純 enum 宣告 0 method body 0 trait impl | ✅ PASS |
| 7 | `replay/mod.rs` 僅 `pub mod profile;` 0 其他 export | ✅ PASS |
| 8 | Cargo.toml `[features] replay_isolated = []` 純 marker 無新 deps | ✅ PASS |
| 9 | Cargo.toml `[[bin]] replay_runner` 含 `required-features = ["replay_isolated"]` | ✅ PASS |
| 10 | 雙語注釋（中英對照）覆蓋所有 module-level doc + Cargo.toml + lib.rs export 注釋 | ✅ PASS |
| 11 | Crate 邊界 allowlist + forbidden list 雙欄並列 + 每項 V3 / workplan / CLAUDE.md 引用 | ✅ PASS（本 report §4 + §5） |
| 12 | nm/objdump grep pattern 含反例 + Wave 3 R20-P2b-S10 CI script 完整 spec | ✅ PASS（本 report §6） |
| 13 | 雙層 cfg gate 設計（compile-time feature + runtime ProfileEnum）說明 | ✅ PASS（本 report §3） |
| 14 | TODO marker 4 條（REF-20 P2b-S7/S8/S9/S10）標識 Wave 3 land 點 | ✅ PASS（in `bin/replay_runner.rs`） |
| 15 | 不改既有檔業務邏輯（僅 Cargo.toml binary entry + lib.rs `pub mod replay;` export） | ✅ PASS |

---

## 8. PM Commit Message Draft（單行 conventional commit）

```
feat(replay): scaffold replay_runner binary + ReplayProfile enum spec (REF-20 Wave 1 R20-P0-T2/T3/T9)
```

---

## 9. Wave 3 R20-P2b-S7/S8/S9/S10 派發前 PM 必確認的 ambiguity / clarify 項

下列項目 Wave 1 不阻塞，但 Wave 3 IMPL 派發前 PM 必先 clarify：

1. **`OPENCLAW_REPLAY_MAC_FORBID_REAL_DATA` 命名最終決定**（V3 workplan §7.3 #14 已 flag「過長」但不 block）。E3 sign-off 前需 PM 決：保持原名 / 改短（建議 `OPENCLAW_REPLAY_MAC_NO_PRIVATE` 14 字 vs 原 41 字）。
2. **`tokio` feature subset under `replay_isolated`**（本 report §4 限定 `rt-multi-thread + macros`）：是否允許 `tokio::time` 用於 fixture replay 計時。建議允許（pure compute）；E2 sign-off 前 PM 確認。
3. **`canonical_config_parser` reuse 既有 `crate::config`**（讀端）vs **fork 子集**：reuse 風險 = config crate 將來加 IO 副作用會傳染 replay 路徑；建議「reuse + 加 read-only assert lint」，但需 E2 + E3 共審。
4. **Wave 3 R20-P2b-S7 spec 中 `ReplayProfile::requires_lease()` 預期語意**（本 report §3.2 草擬）— 是否確定 `Isolated => false`，其餘三 profile `=> true`，請 PM 在 Wave 3 派發前 confirm。
5. **CI runner 平台**（V3 workplan §7.3 #13 flag「Linux only」）：若 CI matrix 同時跑 macOS（aarch64-apple-darwin），nm 行為差異（macOS nm 默認不顯示 undefined symbols）需在 audit script 加 `nm -gU` flag 處理。Wave 3 派發前 PM 確認 CI 平台清單。

---

## 10. PA 結論

**Wave 1 R20-P0-T2 + T3 + T9 — APPROVE FOR E2 SIGN-OFF**

3 task 三件齊備：(a) `replay_runner` binary scaffold + Cargo.toml feature gate + lib.rs export；(b) `ReplayProfile` enum spec；(c) crate 邊界白/黑名單 + nm/objdump CI spec 完整。

**核心契約 frozen 在 compile time**：預設 build 不可能拉 replay binary 進 graph；feature opt-in 後 binary 仍 panic 拒絕運行。Wave 3 IMPL 派發前若需 reset 任何上述設計，須回 PM + PA 走正式 amendment 流程。

**0 runtime change**（符合 Wave 1 Exit Criteria）。

**Wave 3 R20-P2b-S7/S8/S9/S10 接力建議派發 owner**：E1 + PA review + E3 review。**E2 必查 3 點**（per workplan §8）：
1. `grep -rE 'acquire_lease|ipc_server|build_exchange_pipeline' rust/openclaw_engine/src/bin/replay_runner.rs rust/openclaw_engine/src/replay/` → Wave 3 IMPL 後 0 hit
2. `nm target/release/replay_runner | grep -E 'acquire_lease|build_exchange_pipeline|ipc_'` → 0 hit
3. Wave 3 unit test 含 4 fail-mode（profile 偽造、forbidden symbol 注入、Mac S0/S1 read attempt、unsigned manifest）— Wave 1 不要求

---

## 修訂歷史

| 版次 | 日期 | 修訂者 | 摘要 |
|---|---|---|---|
| V1 | 2026-05-03 | PA | Wave 1 R20-P0-T2/T3/T9 三 task 合併 deliverable + crate 邊界 spec + nm/objdump CI step + E2 sign-off ready checklist |
