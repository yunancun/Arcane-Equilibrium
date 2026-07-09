# E1 Sign-off — REF-20 Wave 3 R20-P2b-S8 + S9 Guard IMPL

**Date:** 2026-05-03
**Owner:** E1
**Task:** REF-20 Wave 3 Batch 3B 最後段 (R20-P2b-S8 forbidden_guard + R20-P2b-S9 mac_policy_guard merged IMPL)
**Branch:** main (uncommitted; awaiting E2 review → E4 regression → PM commit)
**Upstream contract:**
- Workplan: `docs/execution_plan/2026-05-03--ref20_implementation_workplan_v1.md` §4 Wave 3 R20-P2b-S8 + R20-P2b-S9 row + §7.4 風險 #18
- V3 spec: `docs/execution_plan/2026-05-03--ref20_paper_replay_lab_dev_plan_v3.md` §3 G7/G8 + §6.2 forbidden 清單 + §6.3 Mac fail-closed + §12 #10/#12
- Wave 2 dispatch: `docs/execution_plan/2026-05-03--ref20_wave2_dispatch_v1.md` §2 ambiguity decisions (especially #1 ENV name rename)
- Predecessor S7: report `2026-05-03--ref20_wave3_p2b_s7_replay_profile_runtime.md` + commit `07de590`
- PA boundary: `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-03--replay_runner_crate_boundary_allowlist.md`

---

## 1. 任務摘要

S7 已 land（commit `07de590`）— `ReplayProfile::Isolated` cfg gate runtime IMPL + 5 acceptance test。本 task 在其上落地 Wave 3 Batch 3B 最後段：兩個 fail-closed guard module + binary integration + 兩個 acceptance test 套件。

合併 IMPL 兩 Rust guard module（同 caller 站點 `replay_runner.rs` 避免 race）：
1. **S8 `forbidden_guard.rs`**: startup + runtime path fail-closed enforcement，覆蓋 V3 §6.2 完整 7 個 forbidden surface（lease / IPC server / WS / exchange dispatch / DB writer / live-demo config / advisory write）。Wave 3 minimal IMPL（env-var + magic-file marker 偵測）；完整 IPC/dispatch/lease 攔截留 Wave 4 R20-P2b-T1 wrapper。
2. **S9 `mac_policy_guard.rs`**: V3 §6.3 Mac fail-closed gate via env var `OPENCLAW_REPLAY_MAC_NO_PRIVATE=1`（per Wave 2 dispatch §2 #1 操作員決定改名 from `OPENCLAW_REPLAY_MAC_FORBID_REAL_DATA`）。`cfg!(target_os = "macos")` 分支：Mac fail-closed enforce / 非 Mac passthrough。

並 wire 兩 guard 進 `replay_runner::main`，與 S7 cfg gate 串成「三層 fail-closed guard chain」（依序 S7 profile → S8 forbidden → S9 mac），任一 `Err` 由 binary `.expect(...)` 觸發 panic（exit 101），run abort。

**0 runtime side-effect on existing code**：`intent_processor` / `ipc_server` / `bybit_*` / `governance_hub` / `live_authorization` 全 0 改動 / 0 import；nm symbol audit 對 366 個 symbol 全 0 forbidden hit。

---

## 2. 修改清單

| File | LOC | Change | Note |
|---|---:|---|---|
| `rust/openclaw_engine/src/replay/forbidden_guard.rs` | **534** | NEW (S8) | `ForbiddenPathError` 7-variant enum + `enforce_at_startup()` + `enforce_at_runtime(action)` + 內部 `parse_trip_value()` / `read_trip_file()` / `current_trip_value()` helpers + 3 lib unit test |
| `rust/openclaw_engine/src/replay/mac_policy_guard.rs` | **384** | NEW (S9) | `MacPolicyError` 3-variant enum + `enforce(profile)` + `host_is_macos()` / `require_env_one()` helpers + 3 lib unit test + ENV name renamed `OPENCLAW_REPLAY_MAC_NO_PRIVATE` |
| `rust/openclaw_engine/src/replay/mod.rs` | 68 → **132** | Edit | `pub mod forbidden_guard;` + `pub mod mac_policy_guard;` + 2 subsystem-level `pub use` re-exports（`ForbiddenPathError` / `MacPolicyError`）+ MODULE_NOTE 雙語更新反映 Wave 3 P2b-S8/S9 IMPL |
| `rust/openclaw_engine/src/bin/replay_runner.rs` | 179 → **246** | Edit | 加 2 個 enforce 呼叫於 main（S7 profile assert → S8 forbidden enforce → S9 mac enforce）+ 移除 S8/S9 TODO marker + 加 Wave 4 T1 wrapper TODO + V3 §6.2 forbidden 清單 reminder + stub 行更新為「P2b-S7/S8/S9 guards online」 |
| `rust/openclaw_engine/tests/replay_forbidden_guard_acceptance.rs` | NEW (**350**) | Create | 4 acceptance proof + `EnvVarRestore` RAII + `env_lock()` Mutex serialization + tempfile-based magic-file isolation |
| `rust/openclaw_engine/tests/replay_mac_policy_acceptance.rs` | NEW (**287**) | Create | 4 acceptance proof（3 macOS + 1 cross-platform；Linux CI 走非 Mac passthrough proof）+ `EnvVarRestore` RAII + `env_lock()` Mutex serialization |

LOC budget：**全 < 800 警告線**（最大 forbidden_guard 534 LOC）。

**0 改動既有檔**：`Cargo.toml` / `lib.rs` / `intent_processor/*` / `ipc_server/*` / `startup/*` / `bybit_*` / `live_authorization*` / `manifest_signer.rs` / `profile.rs` 全未動（S7 + Wave 2 P2a-S2 + Wave 1 既有契約 100% 保留）。

---

## 3. 關鍵 diff（壓縮）

### 3.1 `forbidden_guard.rs` — 7 variant enum + 兩階段 enforce

```rust
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ForbiddenPathError {
    AcquireLeaseDetected,
    IpcServerStarted,
    WsClientStarted,
    ExchangeDispatchInvoked,
    DbWriterChannelInvoked,
    LiveDemoConfigMutated,
    AdvisoryWriteAttempted { source: String },
}

pub const TRIP_ENV_VAR: &str = "OPENCLAW_REPLAY_FORBIDDEN_TRIPPED";
pub const TRIP_FILE_BASENAME: &str = "replay_forbidden.tripped";

pub fn enforce_at_startup() -> Result<(), ForbiddenPathError> {
    match current_trip_value() {
        None => Ok(()),
        Some(err) => Err(err),
    }
}

pub fn enforce_at_runtime(action: &str) -> Result<(), ForbiddenPathError> {
    let _ = action; // future-use; suppress unused warning at Wave 3 baseline.
    match current_trip_value() {
        None => Ok(()),
        Some(err) => Err(err),
    }
}
```

Detection mechanism (read-only, side-effect-free)：
- env var `$OPENCLAW_REPLAY_FORBIDDEN_TRIPPED=<variant_name>`（unit test + Wave 4 wrapper 用）
- magic file `<OPENCLAW_DATA_DIR>/replay_forbidden.tripped` 含 variant name 行
- env var 優先；皆 unset → `Ok(())`（production default）

### 3.2 `mac_policy_guard.rs` — Mac fail-closed enum + ENV rename

```rust
pub const ENV_VAR_NAME: &str = "OPENCLAW_REPLAY_MAC_NO_PRIVATE";   // 14-char (per Wave 2 dispatch §2 #1)
pub const ENV_VAR_REQUIRED_VALUE: &str = "1";

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum MacPolicyError {
    RealDataAttemptedOnMac { found_profile: ReplayProfile },
    EnvVarMissingOrZero { var_name: String, value: Option<String> },
    OsNotMacButGuardActive,
}

pub fn enforce(profile: ReplayProfile) -> Result<(), MacPolicyError> {
    if !host_is_macos() {
        return Ok(());                            // V3 §6.3 scopes policy to Mac
    }
    if !matches!(profile, ReplayProfile::Isolated) {
        return Err(MacPolicyError::RealDataAttemptedOnMac { found_profile: profile });
    }
    require_env_one()                             // ENV must equal "1" exactly
}
```

Profile mismatch reported BEFORE ENV check（audit log priority — non-Isolated profile 不論 ENV 永不可在 Mac 上跑）。

### 3.3 `replay_runner::main` — 三層 guard chain

```rust
fn main() {
    let profile = ReplayProfile::Isolated;

    profile.fail_closed_assert_isolated().expect(
        "REF-20 V3 §6.2 invariant: replay_runner MUST run as Isolated; \
         see crate::replay::profile::ReplayProfile::fail_closed_assert_isolated",
    );

    forbidden_guard::enforce_at_startup().expect(
        "REF-20 V3 §6.2 forbidden path detected at startup; \
         see crate::replay::forbidden_guard::enforce_at_startup",
    );

    mac_policy_guard::enforce(profile).expect(
        "REF-20 V3 §6.3 Mac policy violation; \
         see crate::replay::mac_policy_guard::enforce",
    );

    eprintln!("replay_runner Wave 3 P2b-S7/S8/S9 guards online; Wave 4 logic pending");
}
```

### 3.4 `mod.rs` — subsystem-level re-exports

```rust
pub mod forbidden_guard;
pub mod mac_policy_guard;
pub mod manifest_signer;
pub mod profile;

pub use profile::ReplayIsolationError;       // Wave 3 P2b-S7
pub use forbidden_guard::ForbiddenPathError;  // Wave 3 P2b-S8 (NEW)
pub use mac_policy_guard::MacPolicyError;     // Wave 3 P2b-S9 (NEW)
```

---

## 4. 驗證證明

### 4.1 cargo build (兩 variant)

```
$ cd rust/openclaw_engine && cargo check                               # default, no feature
warning: `openclaw_engine` (lib) generated 21 warnings ...
warning: `openclaw_engine` (bin "openclaw-engine") generated 3 warnings ...
    Finished `dev` profile [unoptimized + debuginfo] target(s) in 6.29s

$ cd rust/openclaw_engine && cargo check --features replay_isolated    # with feature
warning: `openclaw_engine` (lib) generated 21 warnings ...
    Finished `dev` profile [unoptimized + debuginfo] target(s) in 1.27s

$ cd rust/openclaw_engine && cargo build --bin replay_runner --features replay_isolated
warning: `openclaw_engine` (lib) generated 21 warnings ...
    Finished `dev` profile [unoptimized + debuginfo] target(s) in 6.56s
```

| Check | Result |
|---|---|
| Default build (no feature) | ✅ PASS, 0 new warning |
| Feature build (replay_isolated) | ✅ PASS, 0 new warning |
| Replay subsystem warnings 0 new | ✅ all 21 lib warnings + 3 bin warnings pre-existing baseline |
| Binary artifact built | ✅ `target/debug/replay_runner` 1.5MB |

### 4.2 cargo test — 兩 acceptance test

```
$ cargo test --features replay_isolated --test replay_forbidden_guard_acceptance
running 4 tests
test proof_4_variant_consistency_with_v3_section_6_2 ... ok
test proof_1_enforce_at_startup_clean_state_ok ... ok
test proof_2_env_var_trip_surfaces_variant ... ok
test proof_3_enforce_at_runtime_acquire_lease ... ok
test result: ok. 4 passed; 0 failed; 0 ignored

$ cargo test --features replay_isolated --test replay_mac_policy_acceptance
running 4 tests
test proof_2_mac_env_one_isolated_ok ... ok
test cross_platform_const_export_uses_renamed_env_var ... ok
test proof_1_mac_env_unset_fails_closed ... ok
test proof_3_mac_env_one_live_fails_real_data ... ok
test result: ok. 4 passed; 0 failed; 0 ignored
```

**8/8 acceptance test PASS**（含 Mac 上 3 個 macOS-only test + 1 個 cross-platform const-export check）。

### 4.3 Sibling regression — S7 + manifest_signer xlang

```
$ cargo test --features replay_isolated --test replay_profile_acceptance
running 5 tests ... test result: ok. 5 passed; 0 failed; 0 ignored

$ cargo test --features replay_isolated --test replay_manifest_signer_xlang_consistency
running 8 tests ... test result: ok. 8 passed; 0 failed; 0 ignored
```

**0 sibling regression**（S7 5/5 + manifest signer xlang 8/8）。

### 4.4 cargo test --lib (replay subsystem 內部 unit test)

```
$ cargo test --features replay_isolated --lib replay::
running 16 tests
test replay::mac_policy_guard::tests::required_value_is_string_one ... ok
test replay::mac_policy_guard::tests::env_var_name_matches_dispatch_decision_renamed_form ... ok
test replay::mac_policy_guard::tests::old_var_name_grep_self_check ... ok
test replay::forbidden_guard::tests::parse_unknown_or_empty_returns_none ... ok
test replay::forbidden_guard::tests::parse_known_variants_matches_each_arm ... ok
test replay::forbidden_guard::tests::parse_advisory_with_and_without_source ... ok
test replay::manifest_signer::tests::* (10 tests, all OK)
test result: ok. 16 passed; 0 failed; 0 ignored
```

**16 lib unit test PASS**（3 mac_policy_guard + 3 forbidden_guard + 10 manifest_signer sibling 0 regression）。

### 4.5 Binary runtime smoke

**Happy path（exit 0）**：
```
$ OPENCLAW_REPLAY_MAC_NO_PRIVATE=1 ./target/debug/replay_runner
replay_runner Wave 3 P2b-S7/S8/S9 guards online; Wave 4 logic pending
$ echo $?
0
```

**Fail-closed path 1（S9 Mac ENV 未設）**：
```
$ unset OPENCLAW_REPLAY_MAC_NO_PRIVATE; ./target/debug/replay_runner
thread 'main' panicked at openclaw_engine/src/bin/replay_runner.rs:232:40:
REF-20 V3 §6.3 Mac policy violation; see crate::replay::mac_policy_guard::enforce: \
  EnvVarMissingOrZero { var_name: "OPENCLAW_REPLAY_MAC_NO_PRIVATE", value: None }
$ echo $?
101
```

**Fail-closed path 2（S8 forbidden trip env）**：
```
$ OPENCLAW_REPLAY_MAC_NO_PRIVATE=1 OPENCLAW_REPLAY_FORBIDDEN_TRIPPED=AcquireLeaseDetected \
    ./target/debug/replay_runner
thread 'main' panicked at openclaw_engine/src/bin/replay_runner.rs:217:43:
REF-20 V3 §6.2 forbidden path detected at startup; see crate::replay::forbidden_guard::enforce_at_startup: \
  AcquireLeaseDetected
$ echo $?
101
```

V3 §12 #10 + #12 binding **滿足**：forbidden 路徑 abort run（exit 101），不 log-only。

### 4.6 nm symbol audit (S10 ci script)

```
$ SKIP_BUILD=1 REPLAY_RUNNER_BIN=target/debug/replay_runner \
      bash helper_scripts/ci/replay_runner_symbol_audit.sh

[replay_runner_symbol_audit] === replay_runner symbol audit start ===
[replay_runner_symbol_audit] platform: Darwin arm64
[replay_runner_symbol_audit] nm available: /usr/bin/nm
[replay_runner_symbol_audit] platform=Darwin → nm -gU
[replay_runner_symbol_audit] symbol count: 366
[replay_runner_symbol_audit] AUDIT PASS: 0 forbidden symbol detected (366 symbols scanned)
$ echo $?
0
```

**AUDIT PASS** — 366 symbols scanned (vs S7-only baseline 6 minimal symbols), **0 forbidden symbol class**（Decision Lease / IPC server / WS / exchange dispatch / DB writer / live auth / order placement）。新增的 360 symbols 全為 forbidden_guard / mac_policy_guard / Rust core/std / panic infra（合法）。

### 4.7 Cross-platform compliance

```
$ grep -nE '/home/ncyu|/Users/[^/]+' \
    rust/openclaw_engine/src/replay/forbidden_guard.rs \
    rust/openclaw_engine/src/replay/mac_policy_guard.rs \
    rust/openclaw_engine/src/replay/mod.rs \
    rust/openclaw_engine/src/bin/replay_runner.rs \
    rust/openclaw_engine/tests/replay_forbidden_guard_acceptance.rs \
    rust/openclaw_engine/tests/replay_mac_policy_acceptance.rs
# rc=1 (no match) — 0 hardcoded user-home path

$ grep -nE 'env::var.*FORBID_REAL_DATA|set_var.*FORBID_REAL_DATA|"OPENCLAW_REPLAY_MAC_FORBID_REAL_DATA"' \
    <same files>
# rc=1 (no match) — 0 actual code reference to old env name
# (only documentation comments referencing rename history)
```

舊長名 `OPENCLAW_REPLAY_MAC_FORBID_REAL_DATA` **僅在 doc comment 內出現**（顯式 rename history note），**0 個 code constant / env::var() argument**。Per Wave 2 dispatch §2 #1，新名 `OPENCLAW_REPLAY_MAC_NO_PRIVATE` 為唯一活躍 ENV var。

### 4.8 forbidden import audit

```
$ grep -E '^use ' \
    rust/openclaw_engine/src/replay/forbidden_guard.rs \
    rust/openclaw_engine/src/replay/mac_policy_guard.rs \
    rust/openclaw_engine/src/replay/mod.rs \
    rust/openclaw_engine/src/bin/replay_runner.rs

forbidden_guard.rs: use std::env;
forbidden_guard.rs: use std::path::PathBuf;
mac_policy_guard.rs: use std::env;
mac_policy_guard.rs: use crate::replay::profile::ReplayProfile;
replay_runner.rs:    use openclaw_engine::replay::forbidden_guard;
replay_runner.rs:    use openclaw_engine::replay::mac_policy_guard;
replay_runner.rs:    use openclaw_engine::replay::profile::ReplayProfile;
mod.rs:              (only mod declarations + pub use)
```

**0 forbidden import**：
- 0 `intent_processor` / `ipc_server` / `bybit_*` / `live_authorization` / `governance_hub` / `decision_lease` import
- 0 `tokio` import (per Wave 2 dispatch §2 #2)
- 0 `crate::config` import (per task spec：「不依賴 `crate::config`，Wave 4 R20-P2b-T2 才接 config reuse」)

### 4.9 LOC budget

| File | LOC | < 800 警告線 |
|---|---:|:-:|
| forbidden_guard.rs | 534 | ✅ |
| mac_policy_guard.rs | 384 | ✅ |
| mod.rs | 132 | ✅ |
| replay_runner.rs | 246 | ✅ |
| replay_forbidden_guard_acceptance.rs | 350 | ✅ |
| replay_mac_policy_acceptance.rs | 287 | ✅ |

---

## 5. 治理對照（V3 §12 acceptance binding + CLAUDE.md §四 hard 邊界）

| V3 §12 # | Acceptance | 本 task 提供 | 覆蓋強度 |
|---|---|---|---|
| **#10** `replay_forbidden_wiring_fail_closed` | forbidden path aborts run, NOT log-only | `ForbiddenPathError` 7-variant enum + `enforce_at_startup()` returns `Err(...)` + `replay_runner::main` `.expect(...)` panic on Err（runtime smoke 確認 exit 101） | unit test + binary runtime smoke 雙重 |
| **#12** `replay_mac_non_actionable` | Mac dry-run cannot write registry/advisory | `MacPolicyError::RealDataAttemptedOnMac` 對 non-Isolated profile + `EnvVarMissingOrZero` 對 ENV 未設 + `cfg!(target_os = "macos")` 分支 + `replay_runner::main` `.expect(...)` panic on Err | unit test + binary runtime smoke 雙重 |

CLAUDE.md §四 hard 邊界對照：
- `live_execution_allowed` — 不動（replay 永不觸碰）
- `max_retries=0` — 不動
- `decision_lease_emitted` — 不動（replay 永不取 lease）
- `live_authorization` — 不動（replay 不寫 authorization.json）

PA boundary report §4 allowed deps + §5 forbidden deps：
- ✅ allowed deps：`crate::replay::profile::ReplayProfile`（`mac_policy_guard` 用）+ `std::env` + `std::path::PathBuf`（`forbidden_guard` 用）
- ✅ forbidden deps **0 import**：`intent_processor::router` / `ipc_server::*` / `bybit_*` / `governance_hub` / `live_authorization::*` / `decision_lease::*` / `canary_writer::*` / `database::*` / `tokio::net::*` 全 0 hit

CLAUDE.md §七 跨平台合規：
- ✅ 0 hardcoded `/home/ncyu` / `/Users/<name>`
- ✅ ENV var 為 SoT（`OPENCLAW_REPLAY_MAC_NO_PRIVATE` / `OPENCLAW_REPLAY_FORBIDDEN_TRIPPED` / `OPENCLAW_DATA_DIR`），非 hardcoded path
- ✅ `cfg!(target_os = "macos")` 分支兼容 Mac + Linux + 其他 OS
- ✅ 雙語 MODULE_NOTE 完整（每 source file 雙塊 EN + 中）+ 函數 docstring 雙語 + inline 不變量雙語

---

## 6. 不確定之處（PM / E2 / E3 review checklist）

### 6.1 ENV var rename 的 history note 保留範圍

**狀態**：4 個 file 的 doc comment 內保留了「renamed from `OPENCLAW_REPLAY_MAC_FORBID_REAL_DATA`」的歷史 note（共 8 處），均在 module doc / function doc 區塊。**全 0 處** 在 code constant 或 env::var() argument。

**問題**：E2 review 是否要求把這些 history note 全部移除（避免未來 reader 把舊名誤當活躍 var 名）？

**E1 推薦**：保留。理由：
- (a) 這是 Wave 2 dispatch §2 #1 操作員決定 + Wave 3 P2b-S9 spec scaffold 的明確 rename trace；移除會讓 future audit 誤以為從未有過 rename。
- (b) 8 處 history note 全在 doc comment（`///` / `//!`），grep `env::var` / `set_var` 永不會 match，不影響 runtime 正確性。
- (c) `mac_policy_guard.rs::tests::old_var_name_grep_self_check` 已 hard guard 防止舊名作為 const 出現。

**Alternative 若 PM/E2 反對**：可在單一 commit 內全部移除，影響面 ≤ 12 LOC（4 file × 2-4 注釋行）；不影響 acceptance test。

### 6.2 `enforce_at_runtime(action)` 的 Wave 3 minimal IMPL

**狀態**：Wave 3 落地 signature + 最小 env+file detection（與 `enforce_at_startup` body 相同）。`action` 參數於 Wave 3 暫無 routing 用途；`let _ = action;` 抑制 unused warning。

**設計理由**：
- 任務 spec 明確「本 Wave 3 是 spec scaffold + minimal enforcement，完整 IPC/dispatch/lease 攔截在 Wave 4 R20-P2b-T1 wrapper 加」。
- 現在加 per-action interception 會強制 import `intent_processor::router` / `ipc_server::dispatch` 等 forbidden surface（PA boundary §5 違反）+ nm symbol audit (S10) 會 fail。
- Wave 3 鎖定 signature 以便 Wave 4 wrapper 可預先 draft 不必重鎖 API。

**問題**：E2/E3 review 是否要求把 `enforce_at_runtime` 隱藏為 `pub(crate)` 或標 `#[doc(hidden)]` 直到 Wave 4？

**E1 推薦**：留 `pub fn`（ + crate-level re-export）。理由：
- acceptance test (proof 3) 必須能呼叫 `enforce_at_runtime("acquire_lease")` 從 integration test crate；改 `pub(crate)` 無法呼叫。
- `#[doc(hidden)]` 干擾 docs.rs 顯示但不影響 public API；future Wave 4 wrapper code 可能來自 sibling crate（仍未定）。

### 6.3 Acceptance test 對 macOS 與 Linux 分支的不對稱

**狀態**：`replay_mac_policy_acceptance.rs` 4 個 test 中：
- 3 個（proof 1/2/3）`#[cfg(target_os = "macos")]` only
- 1 個（proof 4）`#[cfg(not(target_os = "macos"))]` only
- 1 個（cross_platform_const_export_uses_renamed_env_var）unconditional

**結果**：Mac dev 看到 4 PASS（3 Mac + 1 cross-platform；proof 4 invisible）。Linux CI 看到 2 PASS（1 non-Mac + 1 cross-platform；proof 1/2/3 invisible）。

**問題**：E2/E3 是否要求 mock `cfg!(target_os = "macos")` 改用 dependency injection（傳 `host_is_mac: bool` 進 `enforce()`）以同時測兩分支？

**E1 推薦**：不改。理由：
- (a) `cfg!(target_os = "macos")` 是 compile-time 常數，runtime mock 須改 `enforce()` 簽名加 ABI break；對既有 `replay_runner::main` 呼叫站點影響超過 1 行。
- (b) Wave 2 dispatch §2 #5 已決定「macOS 主 / Linux 次 CI runner platform」。CI matrix（macos-14 + ubuntu-22.04）跑兩平台必跑此 test；單一 host 看不到全部分支是 cfg 系統 by design。
- (c) sibling pattern（`replay_manifest_signer_xlang_consistency.rs`）也有 host-specific test gating。

**Alternative 若 PM/E2 要求**：可加 `host_is_mac: bool` parameter override 到 `enforce()` + 預設 `cfg!(target_os = "macos")` + 兩 host 都跑 4 test，但需 bump signature；建議延 Wave 4 R20-P2b-T1 wrapper 一併處理。

### 6.4 `OsNotMacButGuardActive` 變體目前 0 production caller

**狀態**：`MacPolicyError::OsNotMacButGuardActive` 變體已宣告但 `enforce()` 從不發此 variant（非 Mac → Ok(())）。預留供未來 strict opt-in 模式 caller。

**問題**：E2 review 可能標「dead variant」。

**E1 推薦**：保留 + Wave 3 unit test 不覆蓋此 variant（acceptance test 4 case 全跳過此分支）。Cargo `dead_code` lint 不會觸發（enum variants 預設不警告）；未來 strict opt-in 模式設 `host_is_mac: bool override = false` 時會用到。

**Alternative 若 PM/E2 要求現在移除**：移除 LOC ≤ 6 行（enum + Display branch + doc comment），若需重 land Wave 4 再加。

### 6.5 `unsafe { env::set_var(...) }` 寫法在 acceptance test 內

**狀態**：兩個 acceptance test 內都用 `unsafe { env::set_var(...) }` / `unsafe { env::remove_var(...) }`。

**設計理由**：
- Rust 1.85+（Edition 2024 default）開始將 `env::set_var` 標 unsafe（multi-thread race 隱憂）。我們用 edition 2021，`env::set_var` 仍 safe，但顯式 `unsafe { ... }` 區塊使 future migration 到 edition 2024 時不需重寫。
- 區塊內附 `// SAFETY: env mutation is single-threaded under env_lock() acquired by the test that constructed this guard.` 說明。
- `EnvVarRestore` RAII helper 在 `Drop` 內也用 `unsafe { ... }` 還原原值。

**問題**：E2 review 可能質疑「unsafe 在 safe code 上是不必要的 noise」。

**E1 推薦**：保留。理由：
- (a) Forward-compat 到 edition 2024 / Rust 2.0 軌跡。
- (b) Audit log 友善 — `unsafe` block 顯式標示 env mutation 為 race-prone，提醒 future reader。
- (c) 不影響 Rust 1.95.0 + edition 2021 的 build / runtime（cargo build / cargo test 全綠）。

---

## 7. 紅線確認（task §「紅線」對照）

| 紅線 | 狀態 | 證據 |
|---|---|---|
| 0 IPC / dispatch / live exchange import | ✅ | grep `^use ` 0 forbidden import |
| 0 GovernanceHub / decision_lease import | ✅ | 同上 |
| tokio 0 import (per dispatch §2 #2) | ✅ | `replay_runner.rs` / `forbidden_guard.rs` / `mac_policy_guard.rs` 0 `use tokio` |
| ENV name = `OPENCLAW_REPLAY_MAC_NO_PRIVATE` (per dispatch §2 #1, 14 字 → actual 30 char ASCII full name) | ✅ | `mac_policy_guard.rs::ENV_VAR_NAME` const + lib unit test 自驗 |
| 不依賴 `crate::config`（Wave 4 R20-P2b-T2 才接 config reuse） | ✅ | grep `crate::config` 0 hit |
| 雙語 comment + V035 / S7 module pattern | ✅ | MODULE_NOTE 雙塊 + function docstring 雙語 + inline 不變量雙語 |
| 不擅改 既有 S7 ProfileEnum / ReplayIsolationError 邏輯 | ✅ | `profile.rs` 0 改動（unchanged in this task） |
| 對既有 replay_runner.rs main 只加 enforce call 不 rewrite | ✅ | main 內既有 S7 assert 完整保留；新增 2 個 enforce call + 對應 doc 註釋 |
| 0 既有 Rust file 業務邏輯改動 | ✅ | 改動限於 6 個 file（4 new + 2 edit），既有 lib / strategies / intent_processor 0 改 |
| File size cap：3 source file + 2 test file 全 < 800 LOC | ✅ | 最大 forbidden_guard 534 LOC < 800 |

---

## 8. Operator 下一步

1. **E2 review**：對 6 點 binding 做最終確認：
   - PA boundary §5 forbidden import 0 hit
   - V3 §12 #10 + #12 acceptance test 對應正確
   - 兩 guard module 雙語 MODULE_NOTE + function docstring 完整
   - LOC budget 全 < 800 警告線
   - ENV var rename history note 是否保留（§6.1 unknown）
   - acceptance test 對 macOS / Linux 分支不對稱是否接受（§6.3 unknown）
2. **E4 regression**：
   - 跑全套 cargo test 確認 0 sibling regression（已驗 S7 5/5 + manifest signer 8/8 + replay lib 16/16 + 兩新 acceptance 8/8）
   - 在 trade-core Linux 跑 `cargo test --features replay_isolated --test replay_mac_policy_acceptance` 確認 proof 4 (non-Mac passthrough) PASS（Mac dev 看不到此 test）
3. **E3 review**（per workplan §3.1 安全 task review）：
   - `EnvVarRestore` RAII + `env_lock()` Mutex pattern 對 multi-thread test runner 安全性
   - `enforce_at_startup` 與 `enforce_at_runtime` Wave 3 minimal IMPL 是否符合 V3 §6.2 fail-closed 強度
   - Mac fail-closed 對「ENV 未設」誤判風險（§6.1 / §6.2 兩 unknown）
4. **PM commit + push**（在 E2 + E4 + E3 PASS 後）：見 §9。

---

## 9. PM Commit Message Draft（單行 conventional commit）

```
feat(replay): forbidden_guard + mac_policy_guard + replay_runner integration (Wave 3 P2b-S8/S9)
```

---

## 10. 修訂歷史

| 版次 | 日期 | 修訂者 | 摘要 |
|---|---|---|---|
| V1 | 2026-05-03 | E1 | Wave 3 R20-P2b-S8 + S9 IMPL — 4 source file（2 new + 2 edit）+ 2 new acceptance test file；cargo build 兩 variant PASS；cargo test 8/8 acceptance PASS + 16/16 lib unit test PASS（含 sibling 0 regression）；nm symbol audit 366 symbols 0 forbidden hit；binary smoke happy / S8 trip / S9 ENV 三 path 全驗 |
