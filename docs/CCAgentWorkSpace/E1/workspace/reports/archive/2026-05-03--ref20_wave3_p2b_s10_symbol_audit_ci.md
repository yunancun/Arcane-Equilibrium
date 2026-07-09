# E1 報告 — REF-20 Wave 3 R20-P2b-S10 replay_runner symbol audit CI script

**日期：** 2026-05-03
**Owner：** E1
**Wave / Batch：** Wave 3 Batch 3B（與 P2b-S7 並行）
**契約上游：**
- `docs/execution_plan/2026-05-03--ref20_implementation_workplan_v1.md` §4 Wave 3 R20-P2b-S10 row
- `docs/execution_plan/2026-05-03--ref20_paper_replay_lab_dev_plan_v3.md` §3 G7/G8 + §6.1/§6.2 + §12 #8
- `docs/execution_plan/2026-05-03--ref20_wave2_dispatch_v1.md` §2 #5（macOS 主 / Linux 次 CI runner platform）
- `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-03--replay_runner_crate_boundary_allowlist.md` §6（symbol allowlist）

---

## 0. 任務摘要 / Summary

R20-P2b-S10 — 實作 `replay_runner` Rust binary 的 `nm` / `objdump` symbol 稽核 CI step（縱深防禦 / defense in depth）。

驗證 `replay_runner` release binary 不含任何禁用 symbol（Decision Lease / IPC server / exchange pipeline / Bybit connector / live authorization write / order placement / DB writer），違反任一 = REF-20 V3 §6.2 forbidden-path 契約破壞或 §3 G7/G8 crate 邊界 breach。

三層縱深防禦的 L3：
- L1 編譯期：Cargo `replay_isolated` feature gate + `[[bin]] required-features`（Wave 1 R20-P0-T2 已 land）
- L2 runtime：`ReplayProfile::Isolated` enum guard（Wave 3 R20-P2b-S7 sibling sub-agent 進行中）
- **L3 binary symbol：本 task — `nm` symbol grep on stripped release artifact**

---

## 1. 修改清單 / Changes

| 檔案 | 動作 | LOC | mode | 用途 |
|---|---|---:|---|---|
| `helper_scripts/ci/replay_runner_symbol_audit.sh` | NEW | 337 | 0755 | 主 audit script — cross-platform `uname -s` 分支（Darwin BSD nm + Linux GNU nm）+ 10 forbidden patterns + exit codes 0/1/2/3/4 |
| `helper_scripts/ci/test_replay_runner_symbol_audit.sh` | NEW | 324 | 0755 | mock-based bash 測試套 5 cases（T1 clean / T2 forbidden hit / T3 nm absent / T4 binary missing / T5 multi-class hit） |
| `helper_scripts/ci/README.md` | NEW | 158 | 0644 | 三層縱深防禦說明 + GitHub Actions matrix + cron + pre-commit hook 整合範例 |
| `helper_scripts/SCRIPT_INDEX.md` | UPDATE | +6 | 0644 | 新增 `## ci/` section + last-updated timestamp |

**4 個交付，0 改動既有業務邏輯（純新增 audit infrastructure）。**

---

## 2. 關鍵實作 diff（精簡）

### 2.1 Cross-platform branch（V3 wave2 §2 #5 對齊）

```bash
case "$os" in
    Darwin)
        # macOS / aarch64-apple-darwin (primary CI target)
        # -g: external symbols only / -U: defined only
        log "platform=Darwin → nm -gU"
        nm -gU "$BIN_PATH"
        ;;
    Linux)
        # Linux / GNU binutils (secondary CI target)
        log "platform=Linux → nm --extern-only --defined-only"
        nm --extern-only --defined-only "$BIN_PATH"
        ;;
    *)
        # Unsupported OS does not false-PASS; fail-closed exit 3
        log "UNSUPPORTED OS: $os (only Darwin / Linux supported)"
        exit 3
        ;;
esac
```

### 2.2 Forbidden symbol patterns（10 class，全引自 PA boundary report §6.1）

```bash
declare -a FORBIDDEN_PATTERNS=(
    'acquire_lease|release_lease'                               # Decision Lease
    'GovernanceHub'                                             # Python lease bridge
    'ipc_server::|ipc_dispatch|ipc_handler'                     # JSON-RPC pipeline
    'build_exchange_pipeline'                                   # exchange bootstrap
    'decision_lease|DecisionLease'                              # lease.rs API
    'exchange_dispatch'                                         # live order routing
    'bybit_(rest|ws|api)'                                       # exchange connectors
    'live_authorization|_write_signed_live_authorization'       # live auth write
    'place_order|cancel_order|amend_order'                      # single write entry §1
    'canary_writer::write|database::writer'                     # DB writer channels
)
```

### 2.3 Exit code matrix

| Code | 觸發 | 行動 |
|---|---|---|
| 0 | 0 forbidden symbol | AUDIT PASS — CI green |
| 1 | ≥1 forbidden class hit | AUDIT FAIL — block PR / 警示 |
| 2 | cargo build 失敗 | BUILD FAIL — 看 cargo error |
| 3 | nm 不在 PATH 或 OS 不支援 | TOOLING — 裝 binutils / Xcode CLI |
| 4 | 期望 binary 不存在 | BINARY MISSING — rebuild 或調 REPLAY_RUNNER_BIN |

### 2.4 Three-layer defense overview

```
┌──────────────────────────────────────────────────────────────┐
│  L1 — Compile-time feature gate (Wave 1 R20-P0-T2 ✅ land)   │
│       Cargo.toml [features] replay_isolated = []             │
│       [[bin]] required-features = ["replay_isolated"]        │
│       → default cargo build does NOT compile replay_runner   │
└──────────────────────────────────────────────────────────────┘
              ↓ (caller opts in via --features replay_isolated)
┌──────────────────────────────────────────────────────────────┐
│  L2 — Runtime ProfileEnum guard (Wave 3 R20-P2b-S7 in flight)│
│       ReplayProfile::Isolated enum +                         │
│       enforce_isolated_or_panic() at startup                 │
│       → even if L1 bypassed, runtime panic before tick       │
└──────────────────────────────────────────────────────────────┘
              ↓ (release binary actually written to disk)
┌──────────────────────────────────────────────────────────────┐
│  L3 — Binary symbol audit (THIS TASK ✅)                     │
│       nm -gU (Darwin) / nm --extern-only (Linux) +           │
│       grep 10 forbidden classes → exit 1 on hit              │
│       → catches build graph drift L1 + L2 missed             │
└──────────────────────────────────────────────────────────────┘
```

---

## 3. 治理對照（CLAUDE.md / V3 / 16 根原則）

| 治理條文 | 對應 | 達成方式 |
|---|---|---|
| CLAUDE.md §七 跨平台兼容性 | 路徑不硬編碼 / 服務可遷移 | 0 hit `/home/ncyu` `/Users/[^/]+`；用 `BASH_SOURCE[0]` 推 srv root；`uname -s` 分支兼容 macOS + Linux |
| CLAUDE.md §七 雙語注釋 | MODULE_NOTE / docstring / inline | 兩 shell + README 全雙語；section header / forbidden pattern label / function docstring 中英對照 |
| CLAUDE.md §七 被動等待 healthcheck | 不適用（本 task 為 active CI step） | N/A |
| 16 根原則 §1 單一寫入口 | replay 不得 place_order/cancel_order/amend_order | forbidden pattern: `place_order\|cancel_order\|amend_order` |
| 16 根原則 §2 讀寫分離 | replay 不得直 INSERT learning.* / trading.* | forbidden pattern: `canary_writer::write\|database::writer` |
| 16 根原則 §3 AI ≠ 命令 | replay 不得 acquire_lease | forbidden pattern: `acquire_lease\|release_lease` + `decision_lease\|DecisionLease` + `GovernanceHub` |
| 16 根原則 §4 策略不繞風控 | replay 不得進 IntentProcessor live path | forbidden pattern: `build_exchange_pipeline` + `exchange_dispatch` |
| 16 根原則 §7 學習 ≠ 改寫 Live | replay binary 不直接寫 DB | forbidden pattern: `database::writer` + verified function 必走 P2a-S4 |
| 16 根原則 §9 災難保護 | replay 不掛 exchange WS/REST | forbidden pattern: `bybit_(rest\|ws\|api)` |
| §四 hard 邊界 live_authorization | replay 不得寫 authorization.json | forbidden pattern: `live_authorization\|_write_signed_live_authorization` |
| V3 §3 G7 runner decision | dedicated Rust binary 抽出 | 本 audit 驗 binary symbol-level 隔離 |
| V3 §3 G8 fail-closed isolation | forbidden P2 wiring abort | exit 1 on hit + log file:line evidence |
| V3 §6.1/§6.2 canonical impl + forbidden list | replay binary 必在 ReplayProfile::Isolated 下跑 | 10 forbidden patterns 對齊 §6.2 完整列表 |
| V3 §12 #8 resource_isolation acceptance | 必有 nm/objdump grep step | 本 task 落地此 acceptance check |
| Wave 2 dispatch §2 #5 | macOS 主 / Linux 次 CI platform | `uname -s` 分支 Darwin BSD `nm -gU` / Linux GNU `nm --extern-only --defined-only` |
| PA boundary report §6.1 | symbol allowlist + reverse list | 10 forbidden patterns 100% 對齊 PA spec |

---

## 4. 驗證 / Verification

### 4.1 bash -n syntax check

```
$ bash -n helper_scripts/ci/replay_runner_symbol_audit.sh && echo "PASS"
PASS
$ bash -n helper_scripts/ci/test_replay_runner_symbol_audit.sh && echo "PASS"
PASS
```

### 4.2 Mock test harness 5/5 PASS

```
=== replay_runner_symbol_audit.sh test harness ===
T1 clean_symbols → exit 0     PASS
T2 acquire_lease hit → exit 1 PASS
T3 nm absent → exit 3         PASS
T4 binary missing → exit 4    PASS
T5 multi-class hit → exit 1   PASS

PASS: 5 / FAIL: 0 / total: 5
ALL TESTS PASS
```

### 4.3 macOS smoke test（real binary + real nm）

```
$ tmpdir=$(mktemp -d); cp /bin/ls "$tmpdir/replay_runner"
$ SKIP_BUILD=1 REPLAY_RUNNER_BIN="$tmpdir/replay_runner" \
      bash helper_scripts/ci/replay_runner_symbol_audit.sh

[replay_runner_symbol_audit] === replay_runner symbol audit start ===
[replay_runner_symbol_audit] srv root: /Users/ncyu/Projects/TradeBot/srv
[replay_runner_symbol_audit] platform: Darwin arm64
[replay_runner_symbol_audit] nm available: /usr/bin/nm
[replay_runner_symbol_audit] SKIP_BUILD=1 + binary exists → skip cargo build
[replay_runner_symbol_audit] binary path: /var/folders/.../replay_runner
[replay_runner_symbol_audit] platform=Darwin → nm -gU
[replay_runner_symbol_audit] symbol count: 6
[replay_runner_symbol_audit] AUDIT PASS: 0 forbidden symbol detected (6 symbols scanned)

# exit=0
```

驗證點：
- Mac ARM64 (aarch64-apple-darwin) → 走 Darwin 分支 `nm -gU` ✅
- 真 nm 工具被找到 (`/usr/bin/nm`) ✅
- SKIP_BUILD=1 + binary exists 跳過 cargo build ✅
- AUDIT PASS exit 0 ✅
- macOS strip-by-default 後 system binary 通常 6 個 symbol，全合法 ✅

### 4.4 Compliance probe

```
--- A) hardcoded user-home check (must be 0 hit) ---
0 hit

--- B) trading.* / IPC / GovernanceHub side-effect calls ---
0 actual call (2 hits 都在 forbidden pattern 註釋裡描述「replay must not write trading.*」)

--- C) bilingual comment coverage ---
audit script: 2 MODULE_NOTE
test harness: 12 MODULE_NOTE / inline 雙語

--- D) line count vs 800 warn / 1500 hard ---
audit:    337 ✅
test:     324 ✅
README:   158 ✅

--- E) shell mode ---
audit:    -rwxr-xr-x ✅ (0755)
test:     -rwxr-xr-x ✅ (0755)
```

### 4.5 Cargo build 真實驗（未跑，留 CI matrix）

本 task **不跑** real `cargo build --release --features replay_isolated`，原因：
- Wave 1 binary scaffold body 是 `panic!()`，nm 預期僅 6 symbol（`main` + panic handlers）
- Wave 3 R20-P2b-S7 sibling sub-agent 並行落 runtime IMPL，未 land 前真 cargo build 不會帶入 forbidden deps
- 真 cargo build 慢（~30-60s on Mac M-series），CI matrix 才該跑
- mock test harness 已驗 audit 邏輯 5/5 PASS
- macOS smoke 用真實 binary 驗 nm + 流程 OK

P2b-S7 IMPL land 後，PR CI matrix（macos-14 + ubuntu-22.04）跑 `bash helper_scripts/ci/replay_runner_symbol_audit.sh` 會 force rebuild + 真 audit。

---

## 5. 不確定之處 / Open Questions

1. **P2b-S7 IMPL 完成後是否需移除 SKIP_BUILD 預設行為？**
   目前 audit script 預設**會** force rebuild（除非 caller 顯式 `SKIP_BUILD=1`）。若 P2b-S7 land 後 CI 變慢，operator 可能要求 PR diff smart-skip（檔案未動 rust/openclaw_engine/ 不重 build）。本 task 暫保留 force rebuild，待 P2b-S7 land 後 review。

2. **Linux GNU nm 的真實驗證**
   本 task 在 Mac 上 dev，Linux 分支邏輯只 mock test 過（bash 邏輯 PASS）。trade-core Linux binary 真實跑時行為 nm 輸出格式可能與 mock 略異，需 P2b-S7 land 後在 trade-core 跑一次 smoke 確認。**Mitigation**：CI matrix 加 ubuntu-22.04 runner 強制 PR 級驗證；本地 dev 不驗 Linux 分支不 block merge（mock 已覆蓋邏輯）。

3. **`nm` symbol stripping 的 release vs debug 差異**
   `cargo build --release` 預設會 strip 大部分 symbol（特別是 inline / generic），但 public API + non-mangled extern "C" 仍保留。本 audit 偵測 mangled Rust symbols（`crate::module::function` pattern）即可，但 future 若 P2b-S7 用了 `#[no_mangle]` extern "C" wrapper，pattern 可能要擴。**Mitigation**：P2b-S7 unit test 強制驗 4 fail-mode（profile 偽造 / forbidden symbol 注入 / Mac S0/S1 read attempt / unsigned manifest），與本 audit 互補；本 audit 偏向 binary-level 防漂移而非 unit-test 等級確定性。

4. **PR 級 audit 應該 force rebuild 還是 cache？**
   GitHub Actions 範例（README §CI Integration）目前未配 cache。若 future CI 慢，可加 `actions/cache@v4` 對 `~/.cargo` + `target/` 做 cache。本 task 不預設 cache（保持簡單），由 operator 在 CI 配置階段決定。

5. **是否需 `objdump` fallback？**
   PA boundary report §6.1 spec 寫「nm 或 objdump」但本 IMPL 只用 nm。原因：(a) macOS 預裝 objdump 但 BSD-style flag 不同 / (b) Linux GNU objdump 與 nm 重疊 95%+；只需 nm 即可滿足 V3 §12 #8 acceptance。若 future 有 nm 不 work 的情境（e.g. cross-compiled binary），可加 objdump fallback。

---

## 6. Operator 下一步 / Next Steps

### 立即（本 task 完成後）
1. **E2 review**：對 audit script 的 forbidden pattern 對齊度（vs PA §6.1）+ shell strict mode + cross-platform 邏輯做 sign-off。
2. **E3 review**：對 fail-closed exit code 設計 + nm absent / unsupported OS branch 安全性 sign-off。
3. **E4 regression**：跑 mock test harness 確認 5/5 PASS（本機已驗）+ 在 trade-core Linux 跑一次 smoke（用 `cp /bin/ls` 替代 binary）。

### 等 P2b-S7 land 後
4. **真 cargo build + 真 audit**：在 macos-14 + ubuntu-22.04 PR CI matrix 加 step `bash helper_scripts/ci/replay_runner_symbol_audit.sh`，force rebuild + 真 audit；驗證 P2b-S7 IMPL 不破 forbidden boundary。
5. **PR 級保護**：在 GitHub Actions repo settings → branch protection 加 required check `replay_runner_symbol_audit / macos-14` + `replay_runner_symbol_audit / ubuntu-22.04`，PR 必綠才 merge。

### 中期（Wave 4-5）
6. **trade-core daily cron**：操作員選擇是否加 daily cron `0 3 * * * bash helper_scripts/ci/replay_runner_symbol_audit.sh`，log 寫 `$OPENCLAW_DATA_DIR/logs/replay_runner_audit.log`，被動偵測 future 部署 drift。
7. **Pre-commit hook 可選**：dev 端是否加 `.git/hooks/pre-commit` 對 Rust 改動觸發 audit（範例已寫進 README）。

---

## 7. PM commit message 草案

```
feat(ci): replay_runner symbol audit CI script (cross-platform) (Wave 3 P2b-S10)

Add helper_scripts/ci/replay_runner_symbol_audit.sh + test harness +
README, the L3 binary-symbol layer of REF-20 Paper Replay Lab three-layer
defense (L1 Cargo feature gate + L2 ReplayProfile::Isolated runtime
guard + L3 nm symbol grep). Cross-platform per Wave 2 dispatch §2 #5
operator decision (macOS primary aarch64-apple-darwin BSD `nm -gU` +
Linux secondary x86_64-unknown-linux-gnu GNU `nm --extern-only
--defined-only`). 10 forbidden symbol classes match PA boundary report
§6.1 allowlist (Decision Lease / IPC server / exchange pipeline / Bybit
connector / live auth write / order placement / DB writer). Exit codes
0/1/2/3/4 per spec. mock test harness 5/5 PASS. macOS smoke verified
real binary (cp /bin/ls) + real nm /usr/bin/nm. Bilingual MODULE_NOTE.
SCRIPT_INDEX.md updated.

V3 §3 G7/G8 + §6.1/§6.2 + §12 #8 acceptance.
```

---

## 8. 修訂歷史

| 版次 | 日期 | 修訂者 | 摘要 |
|---|---|---|---|
| V1 | 2026-05-03 | E1 | Wave 3 R20-P2b-S10 IMPL — replay_runner symbol audit script + test harness + README + SCRIPT_INDEX.md update；mock 5/5 PASS + macOS smoke PASS；待 E2 + E3 review |

---

**E2 / E3 review-ready flag：✅**
- 邏輯：cross-platform `uname -s` 分支 + 10 forbidden patterns 對齊 PA §6.1 + exit codes 0/1/2/3/4 per spec
- 驗證：bash -n PASS / mock 5/5 PASS / macOS smoke real-binary PASS / 0 hardcoded path / 0 actual side-effect call / 雙語注釋齊備 / mode 0755
- 紅線：0 binary mutation / 0 PG / 0 trading.* / 0 IPC / 0 GovernanceHub coupling
