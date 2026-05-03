# E1 Sign-off — REF-20 Wave 3 R20-P2b-S7 `ReplayProfile::Isolated` cfg gate runtime IMPL

**Date:** 2026-05-03
**Owner:** E1
**Task:** REF-20 Wave 3 Batch 3B / R20-P2b-S7（`ReplayProfile` 5 method body + binary fail-closed entry + 5 acceptance proofs unit-tested）
**Branch:** main（uncommitted；待 E2 review → E4 regression → PM 統一 commit + push）
**Upstream contract:**
- Workplan: `docs/execution_plan/2026-05-03--ref20_implementation_workplan_v1.md` §4 Wave 3 R20-P2b-S7 row + §7.1 #1/#2
- V3 spec: `docs/execution_plan/2026-05-03--ref20_paper_replay_lab_dev_plan_v3.md` §3 G7/G8 + §6.1/§6.2 + §12 #8/#9/#10/#11
- Wave 2 dispatch §2 ambiguity decisions (PM final): #2 tokio subset / #3 canonical_config_parser reuse / #4 `requires_lease()` 語意
- PA boundary allowlist: `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-03--replay_runner_crate_boundary_allowlist.md`

---

## 1. 任務摘要

Wave 1 P0-T2/T3 已 land 純 enum spec scaffold（commit `06d360a`）。本 task（R20-P2b-S7）在其上：
1. 補 5 method body 到 `ReplayProfile` 上（per Wave 2 dispatch §2 #4 PM 決議：`Isolated => false / 其餘 => true`）；
2. 加 `ReplayIsolationError::WrongProfile { found }` 窄範圍 error type；
3. 替換 `replay_runner::main` 的 Wave 1 panic stub 為 fail-closed runtime gate（`fail_closed_assert_isolated().expect(...)` + stub line + exit 0）；
4. 落地 5 個 acceptance proof unit test（V3 §12 #8/#9/#10/#11 binding）；
5. nm symbol audit 7 forbidden classes 全 0 hit。

**0 runtime side-effect**：binary 跑只印 stub 行 + exit 0，**沒**接 `intent_processor::router`、**沒**接 `manifest_signer` verify flow（per task spec「對 既有 `intent_processor::router` 不切換」— 那是 Wave 4 R20-P2b-T2 的範圍）。

---

## 2. 修改清單

| File | LOC before → after | Change kind | Note |
|---|---:|---|---|
| `rust/openclaw_engine/src/replay/profile.rs` | 116 → **322** | Edit | 加 5 method body + `ReplayIsolationError` enum + `Display` + `std::error::Error` impl；移除 `#[allow(dead_code)]`；雙語 doc 每 method |
| `rust/openclaw_engine/src/replay/mod.rs` | 41 → **68** | Edit | 更新 MODULE_NOTE 反映 Wave 3 IMPL；新增 `pub use profile::ReplayIsolationError;` subsystem-level re-export |
| `rust/openclaw_engine/src/bin/replay_runner.rs` | 132 → **179** | Edit | 替換 Wave 1 panic stub 為 `fail_closed_assert_isolated().expect()` + stub line + exit 0；保留 forbidden list comment + 4 條 Wave 3/4 TODO marker |
| `rust/openclaw_engine/tests/replay_profile_acceptance.rs` | NEW (**232**) | Create | 5 個 `#[test]` proof + 雙語 MODULE_NOTE；對 4 variant 全顯式列舉，禁 default-arm |

LOC budget：322 / 68 / 179 / 232，**全 < 800 警告線**。

**0 改動既有檔**：`Cargo.toml` / `lib.rs` / `intent_processor/*` / `ipc_server/*` / `startup/*` / `bybit_*` / `live_authorization*` / `manifest_signer.rs` 全未動（Wave 1 + Wave 2 P2a-S2 既有契約 100% 保留）。

---

## 3. 關鍵 diff（壓縮）

### 3.1 `replay/profile.rs` — 5 method bodies

```rust
impl ReplayProfile {
    pub fn requires_lease(&self) -> bool {
        !matches!(self, ReplayProfile::Isolated)
    }
    pub fn allow_ipc_server(&self) -> bool {
        !matches!(self, ReplayProfile::Isolated)
    }
    pub fn allow_exchange_dispatch(&self) -> bool {
        !matches!(self, ReplayProfile::Isolated)
    }
    pub fn allow_db_writer_channels(&self) -> bool {
        !matches!(self, ReplayProfile::Isolated)
    }
    pub fn fail_closed_assert_isolated(&self) -> Result<(), ReplayIsolationError> {
        if !matches!(self, ReplayProfile::Isolated) {
            return Err(ReplayIsolationError::WrongProfile { found: *self });
        }
        Ok(())
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ReplayIsolationError {
    WrongProfile { found: ReplayProfile },
}
// + Display + std::error::Error impl
```

### 3.2 `replay/mod.rs` — subsystem-level re-export

```rust
pub mod manifest_signer;
pub mod profile;

pub use profile::ReplayIsolationError;  // <-- NEW
```

### 3.3 `bin/replay_runner.rs` — runtime gate entry

```rust
use openclaw_engine::replay::profile::ReplayProfile;

fn main() {
    let profile = ReplayProfile::Isolated;
    profile.fail_closed_assert_isolated().expect(
        "REF-20 V3 §6.2 invariant: replay_runner MUST run as Isolated; \
         see crate::replay::profile::ReplayProfile::fail_closed_assert_isolated",
    );
    eprintln!("replay_runner Wave 3 P2b-S7 cfg gate online; Wave 4 logic pending");
}
```

### 3.4 `tests/replay_profile_acceptance.rs` — 5 proofs（題核）

```rust
#[test] fn proof_1_isolated_requires_lease_false() { ... }
#[test] fn proof_2_non_isolated_variants_require_lease_true() { ... }   // Live + LiveDemo + PaperLegacy 各 1 assert
#[test] fn proof_3_allow_ipc_server_matrix() { ... }                    // Isolated false + 3 variant true
#[test] fn proof_4_fail_closed_assert_matrix() { ... }                  // Isolated Ok + 3 variant Err(WrongProfile{found:variant})
#[test] fn proof_5_cross_method_consistency() { ... }                   // 跨 4 method × 4 variant 一致性
```

---

## 4. 驗證證明

### 4.1 cargo build

```
$ cd rust/openclaw_engine && cargo build --bin replay_runner --features replay_isolated
warning: `openclaw_engine` (lib) generated 21 warnings (run `cargo fix --lib -p openclaw_engine` to apply 13 suggestions)
    Finished `dev` profile [unoptimized + debuginfo] target(s) in 8.87s

$ cd rust/openclaw_engine && cargo build -p openclaw_engine    # default, no feature
warning: `openclaw_engine` (lib) generated 21 warnings ...
warning: `openclaw_engine` (bin "openclaw-engine") generated 3 warnings ...
    Finished `dev` profile [unoptimized + debuginfo] target(s) in 17.32s
```

| Check | Result |
|---|---|
| Replay-new warnings | **0** (21 lib + 3 bin all pre-existing baseline; replay 三檔 0 new) |
| Default build excludes replay_runner | ✅ `cargo metadata` confirms `required-features=['replay_isolated']` |
| Feature build produces artifact | ✅ `target/debug/replay_runner` 1.27MB |

### 4.2 cargo test — 5 acceptance proofs

```
$ cargo test --test replay_profile_acceptance --features replay_isolated
running 5 tests
test proof_1_isolated_requires_lease_false ... ok
test proof_2_non_isolated_variants_require_lease_true ... ok
test proof_5_cross_method_consistency ... ok
test proof_3_allow_ipc_server_matrix ... ok
test proof_4_fail_closed_assert_matrix ... ok

test result: ok. 5 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.00s
```

### 4.3 Sibling regression — Wave 2 P2a-S2 manifest_signer

```
$ cargo test --test replay_manifest_signer_xlang_consistency --features replay_isolated
test result: ok. 8 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out
```

**0 sibling regression。**

### 4.4 Binary runtime smoke

```
$ /Users/ncyu/Projects/TradeBot/srv/rust/target/debug/replay_runner
replay_runner Wave 3 P2b-S7 cfg gate online; Wave 4 logic pending
$ echo $?
0
```

### 4.5 nm symbol audit（per PA boundary §6 + task (F) #3 binding）

```
$ nm target/debug/replay_runner | wc -l
1148

$ nm target/debug/replay_runner | grep -E 'acquire_lease|release_lease|GovernanceHub'    | wc -l   # 0
$ nm target/debug/replay_runner | grep -E 'build_exchange_pipeline'                        | wc -l   # 0
$ nm target/debug/replay_runner | grep -E 'ipc_server|ipc_dispatch|ipc_handler'           | wc -l   # 0
$ nm target/debug/replay_runner | grep -E 'place_order|cancel_order|amend_order'          | wc -l   # 0
$ nm target/debug/replay_runner | grep -E 'write_signed_live_authorization'                | wc -l   # 0
$ nm target/debug/replay_runner | grep -E 'bybit_private_ws|ws_client::Client'             | wc -l   # 0
$ nm target/debug/replay_runner | grep -E 'canary_writer::write|database::writer'          | wc -l   # 0
```

**7/7 forbidden symbol classes → 0 hit on 1148 total symbols。**

剩餘 1148 symbols 為 Rust core/std + `ReplayProfile` 自身的 `Debug`/`Clone`/`Eq` derive helpers + panic / format infra，全 100% 合法。

### 4.6 grep `use` import audit（task (F) binding #1）

```
$ grep -nE '/home/ncyu|/Users/[^/]+' \
    rust/openclaw_engine/src/replay/profile.rs \
    rust/openclaw_engine/src/replay/mod.rs \
    rust/openclaw_engine/src/bin/replay_runner.rs \
    rust/openclaw_engine/tests/replay_profile_acceptance.rs
# rc=1 (no match) — 0 hardcoded path

$ grep -E 'use .*acquire_lease|use .*ipc_server|use .*build_exchange_pipeline|use .*GovernanceHub|use .*exchange_dispatch|use .*trading_tx|use .*market_data_tx|use .*order_dispatch_tx' \
    rust/openclaw_engine/src/bin/replay_runner.rs \
    rust/openclaw_engine/src/replay/profile.rs \
    rust/openclaw_engine/src/replay/mod.rs
# rc=1 (no match) — 0 forbidden use import
```

**注意**：寬範圍 grep `acquire_lease|ipc_server|...` 在 `profile.rs` 命中 method declaration name `pub fn allow_ipc_server` / `pub fn allow_exchange_dispatch`。這是設計上必要的 — method declaration name 表達 forbidden surface 的 gate 語意，不是 use import。E2 review 必加 `grep "use .*<pattern>"` narrow filter 區分。

---

## 5. 治理對照（V3 §12 acceptance binding）

| V3 §12 # | Acceptance | 本 task 提供 | 覆蓋強度 |
|---|---|---|---|
| **#8** `replay_resource_isolation` | no IPC/WS/exchange/DB writer channels | Method `allow_ipc_server`/`allow_exchange_dispatch`/`allow_db_writer_channels` 全 false on Isolated；nm 對應 7 symbol classes 0 hit | unit + symbol audit 雙重 |
| **#9** `replay_no_decision_lease_acquire` | smoke replay does not call `acquire_lease` | `requires_lease() == false` on Isolated；binary 0 import lease；nm 0 hit | unit + symbol audit |
| **#10** `replay_forbidden_wiring_fail_closed` | forbidden path aborts run, NOT log-only | `fail_closed_assert_isolated()` 回 `Err(WrongProfile)`；binary `.expect()` panic on Err | unit + binary entry |
| **#11** `replay_execution_confidence_label` | S2/S3 smoke reports `execution_confidence='none'` | **本 task 標記 caller policy**；profile method 不直接 enforce `execution_confidence`；Wave 4 R20-P2b-T2 binary IMPL 寫 manifest 時必綁 `Isolated => execution_confidence='none'` | doc-only here, runtime in Wave 4 |
| **#12** `replay_mac_non_actionable` | Mac dry-run cannot write registry/advisory | **不在本 task scope** — Wave 3 R20-P2b-S9 (`mac_policy_guard`) 範圍 | Wave 3 sibling |

CLAUDE.md §四 hard 邊界對照：
- `live_execution_allowed` — 不動（replay 永不觸碰）
- `max_retries=0` — 不動
- Decision Lease 路徑 — 不動（本 task 確認 Isolated profile **不**取 lease，但 lease 接線本身是 Python `governance_hub.acquire_lease` 的 retrofit pending range，本 task 0 影響）

---

## 6. 不確定之處（PM / E2 / E3 review checklist）

1. **`ReplayIsolationError` variant 命名**：選 `WrongProfile { found: ReplayProfile }`，預期 E2/E3 可接受。Alternatives 評估：
   - `NotIsolated`（更精簡，但 caller pattern-match 不夠 self-documenting）
   - `ProfileMismatch { expected: ReplayProfile, found: ReplayProfile }`（更完整，但 expected 永遠 = `Isolated`，redundancy）
   - **採用 `WrongProfile { found }`**：精準 + payload 攜帶 audit log 所需信息（哪個 non-Isolated profile 洩漏）。
   - **PM/E3 if reject**：可單獨改 enum variant + test，影響面 ≤ 5 LOC。

2. **`ReplayIsolationError` 是否該對 `thiserror::Error` 做 derive**：`replay/manifest_signer.rs` 用 plain `Debug + Display + std::error::Error` 手寫 impl。本 task 對齊 sibling pattern（手寫 impl + 不 import `thiserror`）。理由：
   - 維持 replay subsystem 0 額外依賴（per PA allowlist §4 表）
   - `ReplayIsolationError` 只一 variant，手寫 impl LOC = 8 行（用 thiserror 也 8 行）
   - 若未來加 variant 多到 ≥ 5 個，再考慮升級用 thiserror。

3. **acceptance test 為何不用 `#[should_panic]` 標籤對 binary 跑 fail-closed scenario**：採 typed Result + match 而非 should_panic 因：
   - test 跑 binary entry 不容易（會雙進程）；改成單元測試 method 本身語意
   - typed error 可在 `match` 內驗 `WrongProfile.found == profile`，比 panic message 字串 match 更可靠
   - 對應 V3 §12 #10 binding：spec 要求「forbidden path aborts run, NOT log-only」，本 task method 回 Err + caller `.expect()` panic 的兩階段語意比直接 panic 更清晰（caller 可選擇 panic 或別的 error handling，雖然 V3 規定 panic）

4. **是否需要在本 task 加 `cargo clippy` lint rule 防止未來 `intent_processor` import**：PA boundary §3 §6 已說 nm/objdump CI step 是 R20-P2b-S10 範圍。本 task 不加 lint rule（避免擴大 scope）。

5. **`profile.rs` 從 116 → 322 LOC（+206）**：擴張主要來自 5 method 的雙語 doc comment（每 method 約 40 行 doc）+ `ReplayIsolationError` enum + `Display` + `std::error::Error` impl。雖大但全在「new method body 範圍」內，未動 enum body 既有 4 variant。E2 review 看是否要拆 doc 到 module-level；本作者認為對齊 sibling `manifest_signer.rs`（260 LOC + 內部結構複雜度更高）pattern，本檔 LOC 仍合理。

---

## 7. Operator 下一步

1. **E2 review**：`@E2` 對 5 點 binding 做最終確認：
   - (F) #1 grep clean（method declaration name 不算）
   - (F) #2 nm symbol audit clean
   - 5 acceptance test 對 V3 §12 #8/#9/#10/#11 binding 完整
   - LOC budget OK（profile.rs 322 < 800）
   - 雙語注釋覆蓋 5 method docstring + MODULE_NOTE 雙塊
2. **E4 regression**：跑 `cargo test -p openclaw_engine --features replay_isolated` 全測試套件確認 0 sibling regression
3. **E3 review**（可選，per workplan §3.1 安全 task review）：對 `ReplayIsolationError` variant 命名 + `fail_closed_assert_isolated` 語意做 cross-check
4. **PM commit + push**（在 E2 + E4 PASS 後）：

```
feat(replay): ReplayProfile cfg gate runtime IMPL + 5 acceptance tests (Wave 3 P2b-S7)
```

---

## 8. PM Commit Message Draft

```
feat(replay): ReplayProfile cfg gate runtime IMPL + 5 acceptance tests (Wave 3 P2b-S7)
```

---

## 修訂歷史

| 版次 | 日期 | 修訂者 | 摘要 |
|---|---|---|---|
| V1 | 2026-05-03 | E1 | Wave 3 R20-P2b-S7 IMPL deliverable — 4 file edit + 1 new test file + 5/5 acceptance PASS + nm 7 forbidden classes 0 hit + 8 sibling test 0 regression |
