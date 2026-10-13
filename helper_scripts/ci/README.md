# CI Audit Scripts

CI-time audit scripts that enforce REF-20 / REF-21 contract boundaries on
compiled artifacts. These run as defense-in-depth on top of compile-time
feature gates and runtime profile guards.

## Components

| File | Purpose |
|---|---|
| `check_stable_id_duplication.sh` | W-D MAG-083 P1-1 follow-up — fast grep guard that fails CI if Rust source outside the canonical Agent Spine helper/caller files reintroduces literal `stable_id` seed formatting (`format!("{}:{}:{}:{}"...`) with stable-id-like variable names. |
| `replay_runner_symbol_audit.sh` | REF-20 Wave 3 R20-P2b-S10 — 以 `nm --demangle` 掃描未剝除的 `replay_runner` debug 產物的完整符號表，確認沒有任何一類禁用符號（Decision Lease / IPC server / exchange pipeline / Bybit connector / live auth write / order placement / DB writer）。Darwin 與 Linux 用同一組旗標。 |
| `test_replay_runner_symbol_audit.sh` | 稽核腳本的模擬測試（28 項）。以替換 PATH 上的 `nm`、`uname`、`cargo` 來測，不做真正的建置。 |

## Three-Layer Defense

REF-20 V3 §3 G7/G8 mandates three independent isolation layers for the
`replay_runner` binary; this directory hosts L3:

| Layer | Mechanism | Owner | Land point |
|---|---|---|---|
| L1 compile-time | Cargo `replay_isolated` feature gate + `[[bin]] required-features` | `Cargo.toml` | Wave 1 R20-P0-T2 |
| L2 runtime | `ReplayProfile::Isolated` enum guard + `enforce_isolated_or_panic()` | `rust/.../replay/profile.rs` | Wave 3 R20-P2b-S7 |
| **L3 binary symbol** | **`nm` symbol scan of the unstripped debug artifact（release 產物已剝除符號，掃它沒有偵測力）** | **`replay_runner_symbol_audit.sh`** | **Wave 3 R20-P2b-S10 (this dir)** |

Any single layer breach shall be rejected; **all three** must pass.

## `check_stable_id_duplication.sh` Usage

```bash
bash helper_scripts/ci/check_stable_id_duplication.sh
```

Exit code `0` means no duplicated literal seed pattern was found. Exit code
`1` means at least one non-canonical Rust file contains the guarded
`format!("{}:{}:{}:{}"...` signature together with stable-id-like identifiers;
the output lists offending files and line numbers.

This check is wired into `.github/workflows/ci.yml` as
`stable_id duplication guard`.

## `replay_runner_symbol_audit.sh` Usage

```bash
# 預設：建置 replay_runner 的 debug 產物（--features replay_isolated，不剝除符號）後稽核
bash helper_scripts/ci/replay_runner_symbol_audit.sh

# 離線建置（cargo 原生支援的環境變數）
CARGO_NET_OFFLINE=true bash helper_scripts/ci/replay_runner_symbol_audit.sh

# 正向控制：逐類確認禁用樣式能命中樣本；不建置，也不讀執行檔
bash helper_scripts/ci/replay_runner_symbol_audit.sh --self-test

# 不建置，稽核既有的執行檔（受審檔是否對應目前源碼由呼叫端負責）
SKIP_BUILD=1 bash helper_scripts/ci/replay_runner_symbol_audit.sh

# 指定受審檔
REPLAY_RUNNER_BIN=/path/to/replay_runner \
    bash helper_scripts/ci/replay_runner_symbol_audit.sh
```

### Exit codes

| Code | Meaning |
|---|---|
| 0 | AUDIT PASS — 沒有禁用符號；`--self-test` 時代表正向控制成立 |
| 1 | AUDIT FAIL — 至少一類禁用符號命中 |
| 2 | BUILD FAIL — `cargo build` 失敗 |
| 3 | NM NOT FOUND — `$PATH` 上沒有 `nm` |
| 4 | BINARY NOT FOUND — 找不到 `target/debug/replay_runner`（或指定的受審檔） |
| 5 | INCONCLUSIVE — 無法判定：空符號表、已剝除、未解碼、缺定位符號、樣式無法評估、樣式清單為空、不支援的作業系統，或設了會改變建置輸出位置的環境變數；`--self-test` 時代表正向控制不成立 |
| 64 | USAGE — 不認得的參數 |

5 不是通過。空的或已剝除的符號表沒有任何證明力，所以不得回報 0。

### 掃描方式

Darwin 與 Linux 都用 `nm --demangle` 傾印完整符號表（含非對外與未定義符號）；其他作業系統回 5。

- **定位符號**：符號表裡必須同時有 `openclaw_engine::` 與 `replay_runner::`，以原始輸出比對。未解碼的函式名稱不含 `::`，所以這也確認了解碼有生效。
- **正規化**：`nm` 對泛型參數與 trait 實作裡的路徑輸出 `a..b..c`。樣式比對前先把 `..` 統一成 `::`，帶 `::` 的禁用樣式才不會漏掉只以這種形式出現的路徑。
- **受審檔**：稽核訊息會印出受審檔的 SHA-256。設了 `CARGO_TARGET_DIR`、`CARGO_BUILD_TARGET_DIR` 或 `CARGO_BUILD_TARGET` 而沒有指定 `REPLAY_RUNNER_BIN` 時，
  建置產物不在預設路徑，腳本在建置前回 5，不會去稽核預設路徑上的舊檔。cargo 設定檔裡的 target-dir 偵測不到。

### Forbidden symbol classes

Source: PA boundary report §6.1 + V3 §6.2 + 16 root principles §4.

```text
acquire_lease | release_lease            # Decision Lease (16#3)
GovernanceHub                            # Python lease bridge
ipc_server::* | ipc_dispatch | ipc_handler   # JSON-RPC pipeline (16#1, 16#2)
build_exchange_pipeline                   # exchange bootstrap (16#1)
decision_lease | DecisionLease            # lease.rs API
exchange_dispatch                         # live order routing
bybit_(rest|ws|api)                       # exchange connectors
live_authorization | _write_signed_live_authorization  # CLAUDE §4 hard
place_order | cancel_order | amend_order  # single write entry §1
canary_writer::write | database::writer   # DB writer channels
```

任何一類命中即回 1，並列出該類全部命中的符號。

這份清單是這層防線的政策；`--self-test` 為每一類各帶一筆樣本，新增或調整樣式時要同步更新樣本。

## CI Integration

這支稽核**目前沒有接進** `.github/workflows/ci.yml`（接進去的只有另一條產品線的 `ibkr_g4_symbol_audit.sh`）。它與它的模擬測試只在本機執行過，Linux 分支只有模擬。
接進 CI 時要注意：

- 正向控制（`--self-test`）與實跑要在同一個工作裡都執行；實跑本身不要求先跑過正向控制。
- 不要用 `SKIP_BUILD` 或 `REPLAY_RUNNER_BIN`，兩者都不驗證受審檔與目前源碼的關係。
- 稽核的是 debug 產物、`replay_isolated` 這一組 feature；建置指令沒有 `--locked`。

### Cron / scheduled

```bash
# Daily 03:00 audit on Linux trade-core (cron)
0 3 * * * cd $OPENCLAW_BASE_DIR && \
    bash helper_scripts/ci/replay_runner_symbol_audit.sh \
        >> $OPENCLAW_DATA_DIR/logs/replay_runner_audit.log 2>&1
```

### Pre-commit hook (optional, dev only)

```bash
# .git/hooks/pre-commit (after Rust changes)
if git diff --cached --name-only | grep -qE 'rust/openclaw_engine/'; then
    SKIP_BUILD=0 bash helper_scripts/ci/replay_runner_symbol_audit.sh \
        || { echo 'replay_runner symbol audit FAIL — fix before commit'; exit 1; }
fi
```

## Test Harness Usage

```bash
bash helper_scripts/ci/test_replay_runner_symbol_audit.sh
```

每個案例印一行 `T<N> … PASS` 或 `FAIL`，最後是：

```
PASS: 28 / FAIL: 0 / total: 28
ALL TESTS PASS
```

測試以暫存目錄裡的替身取代 `nm`、`uname` 與 `cargo`，不做真正的建置。它只證明稽核邏輯對已知的符號輸入是對的；
對真實執行檔的驗證要另外實跑稽核。Linux 案例是在 macOS 上假造 `uname`，不是真的 GNU `nm`。

## Spec References

- V3 contract: `docs/execution_plan/2026-05-03--ref20_paper_replay_lab_dev_plan_v3.md`
  §3 G7/G8 + §6.1/§6.2 + §12 #8
- Workplan: `docs/execution_plan/2026-05-03--ref20_implementation_workplan_v1.md`
  §4 Wave 3 R20-P2b-S10
- PA boundary report: `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-03--replay_runner_crate_boundary_allowlist.md`
  §6 (symbol allowlist)
- Wave 2 dispatch decisions: `docs/execution_plan/2026-05-03--ref20_wave2_dispatch_v1.md`
  §2 #5 (macOS primary / Linux secondary)
