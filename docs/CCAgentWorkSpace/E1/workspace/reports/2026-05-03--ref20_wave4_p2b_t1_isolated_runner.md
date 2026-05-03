# REF-20 Wave 4 R20-P2b-T1 — Isolated Runner Wrapper IMPL

**Date:** 2026-05-03
**Owner:** E1
**Status:** IMPL DONE — awaiting E2 review
**Refs:**
- Workplan: `docs/execution_plan/2026-05-03--ref20_implementation_workplan_v1.md` §4 Wave 4 R20-P2b-T1 row
- V3 contract: `docs/execution_plan/2026-05-03--ref20_paper_replay_lab_dev_plan_v3.md` §6.1/§6.2/§6.4 + §12 #8/#10/#11
- Wave 2 dispatch: `docs/execution_plan/2026-05-03--ref20_wave2_dispatch_v1.md` §2 ambiguity decisions #2/#3/#4
- PA boundary report: `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-03--replay_runner_crate_boundary_allowlist.md`

---

## 1. 任務摘要

Wave 3 已 land 3-layer fail-closed guard chain（S7 profile cfg / S8 forbidden_guard / S9 mac_policy_guard）;Wave 3 binary main 為 stub `eprintln!`（[5a618ff..]）。Wave 4 R20-P2b-T1 在 guard 下游接入功能性 replay logic：

```
Wave 3 guards (S7/S8/S9) → Wave 4 [CLI parse → manifest verify → fixture load → IsolatedPipeline.execute → report write]
```

實作 5 新 lib module + binary entry 改寫 + 6 e2e acceptance proofs + fixture set。

---

## 2. 修改清單

### 2.1 新增 source（5 lib + 1 bin section + 1 test + 3 fixtures）

| File | LOC | Purpose |
|---|---:|---|
| `rust/openclaw_engine/src/replay/cli.rs` | 376 | hand-rolled CLI parser（POSIX-style `--manifest --output-dir [--baseline-id]`）+ 9 unit tests |
| `rust/openclaw_engine/src/replay/fixture_loader.rs` | 448 | S2/S3 fixture JSON → `Vec<MarketEvent>` + 5 unit tests |
| `rust/openclaw_engine/src/replay/runner.rs` | 676 | `IsolatedPipeline` orchestrator + `ReplayResult` + 4 unit tests |
| `rust/openclaw_engine/src/replay/report_writer.rs` | 391 | JSON + summary writer + 4 unit tests |
| `rust/openclaw_engine/tests/replay_runner_e2e.rs` | 468 | 6 acceptance proofs（5 spec + 1 helper round-trip）|
| `rust/openclaw_engine/tests/fixtures/replay_runner_e2e/synthetic_btcusdt.json` | — | 10-tick S3 BTCUSDT fixture |
| `rust/openclaw_engine/tests/fixtures/replay_runner_e2e/key.hex` | — | 32-byte fixture HMAC key |
| `rust/openclaw_engine/tests/fixtures/replay_runner_e2e/README.md` | — | fixture provenance / V3 compliance note |

### 2.2 修改 source（2 既有檔）

| File | Diff | 說明 |
|---|---|---|
| `rust/openclaw_engine/src/replay/mod.rs` | +21 LOC | 加 `pub mod cli/fixture_loader/runner/report_writer` + 4 subsystem-level re-export |
| `rust/openclaw_engine/src/bin/replay_runner.rs` | +200 LOC（246→471） | 替換 stub `eprintln!` 為功能性 main：CLI parse → load_and_verify_manifest → fixture load → build_isolated_pipeline → execute → write_replay_report |

### 2.3 不動既有檔（0 LOC）

- Wave 3 既存 module（`profile.rs` / `forbidden_guard.rs` / `mac_policy_guard.rs` / `manifest_signer.rs`）
- Wave 3 既存 acceptance tests（`replay_profile_acceptance.rs` / `replay_forbidden_guard_acceptance.rs` / `replay_mac_policy_acceptance.rs` / `replay_manifest_signer_xlang_consistency.rs`）
- 任何 live engine 模組（`intent_processor` / `ipc_server` / `bybit_*` / `governance_hub` / `decision_lease` / `canary_writer` / `database` / `paper_state`）

---

## 3. 關鍵 diff 與設計

### 3.1 binary entry main 改寫核心

```rust
fn main() -> Result<(), Box<dyn std::error::Error>> {
    // Wave 3 三層 fail-closed guard chain (preserved verbatim)
    let profile = ReplayProfile::Isolated;
    profile.fail_closed_assert_isolated().expect(...);   // S7
    forbidden_guard::enforce_at_startup().expect(...);    // S8
    mac_policy_guard::enforce(profile).expect(...);       // S9

    // Wave 4 R20-P2b-T1 actual replay logic
    let args = cli::parse_cli_args()?;
    let manifest = load_and_verify_manifest(&args.manifest_path)?;
    let fixture_source =
        FixtureSource::from_manifest_strings(&manifest.data_tier, &manifest.fixture_uri)?;
    let tier_label = fixture_source.tier_label();
    let events = fixture_loader::load_fixtures(&fixture_source)?;

    let mut pipeline = runner::build_isolated_pipeline(
        profile, manifest.experiment_id.clone(), tier_label, events,
    )?;
    let exec_outcome = pipeline.execute();
    let result: ReplayResult = pipeline.into_result();
    let json_path = report_writer::write_replay_report(&args.output_dir, &result)?;

    eprintln!(
        "replay_runner: completed manifest_id={} status={} json={}",
        result.manifest_id, result.status.label(), json_path.display()
    );
    exec_outcome?;  // propagate forbidden trip / abort as non-zero exit
    Ok(())
}
```

### 3.2 V3 §12 #11 invariant: `execution_confidence='none'`

`runner.rs::IsolatedPipeline.into_result()` hardcodes `"none"`:
```rust
ReplayResult {
    ...
    execution_confidence: "none".to_string(),
    ...
}
```

`report_writer.rs::ReportEnvelope` propagates verbatim:
```rust
struct ReportEnvelope<'a> {
    ...
    execution_confidence: &'a str,  // = result.execution_confidence
    result: &'a ReplayResult,
}
```

### 3.3 V3 §12 #10 fail_closed acceptance binding

`runner.rs::IsolatedPipeline.execute()` 每 event 前 call `enforce_at_runtime`:
```rust
forbidden_guard::enforce_at_runtime(&action).map_err(|err| {
    self.status = ReplayStatus::AbortedForbidden { action: action.clone() };
    err
})?;
```

Proof 4（`forbidden_path_trip_via_env_aborts_run`）PASS demonstrates abort behaviour。

---

## 4. 治理對照（V3 / workplan / CLAUDE.md）

| 規範 | 對應 IMPL | 驗證手段 |
|---|---|---|
| V3 §6.1 dedicated runner | `bin/replay_runner.rs`（feature-gated `replay_isolated`） | `cargo build --bin replay_runner --features replay_isolated` PASS |
| V3 §6.2 forbidden list | `runner.rs` 不 import `intent_processor` / `ipc_server` / `bybit_*` / `governance_hub` / `decision_lease` / `canary_writer` / `database` | `nm symbol audit` AUDIT PASS（393 symbol / 0 forbidden hit） |
| V3 §6.2 fail_closed runtime | `runner.rs::execute()` 每 event 前呼 `enforce_at_runtime` | proof 4 PASS |
| V3 §6.3 Mac policy | Wave 3 S9 已實作；Wave 4 T1 main 仍呼叫 | proof 4 / mac smoke test PASS |
| V3 §6.4 baseline snapshot | T1 不建 production baseline 目錄；test fixture 在 `tests/fixtures/replay_runner_e2e/`（與 PM-curated `research_notes/replay_fixtures/` 路徑分離） | manifest 內 `fixture_uri` 為 absolute path；report 內 `evidence_source_tier` = "calibrated_replay" / "synthetic_replay" |
| V3 §11 P2b business KPI | report 含 `pnl_summary.events_processed` / `fills_emitted` 計數 | proof 1/5 PASS |
| V3 §12 #8 resource_isolation | replay_runner 0 IPC/dispatch/lease symbol | nm audit PASS |
| V3 §12 #10 fail_closed | abort run not log-only | proof 4 PASS |
| V3 §12 #11 confidence_label | execution_confidence='none' for all replay runs | proof 1 + proof 5 + smoke test 確認 |
| Wave 2 dispatch §2 #2 tokio limited | runner / report_writer / fixture_loader / cli 0 import tokio | grep `use tokio` 全 0 hit |
| Wave 2 dispatch §2 #3 config reuse | T1 未 reuse `crate::config`；canonical_config_parser 留待 Wave 5+ | TBD（不阻塞 T1） |
| Wave 2 dispatch §2 #4 requires_lease | Wave 3 已 IMPL；Wave 4 T1 不改 | profile_acceptance 5/5 PASS |
| CLAUDE.md §七 雙語注釋 | 5 new module + bin diff + e2e test 全帶 MODULE_NOTE EN/中 | grep `MODULE_NOTE` 命中 |
| CLAUDE.md §九 file size budget | 6 new file 全 < 800 LOC 警告線（max=676 runner.rs） | wc -l 確認 |

---

## 5. Verify 結果

### 5.1 cargo build

```
$ cd rust && cargo build -p openclaw_engine --bin replay_runner --features replay_isolated --release
warning: `openclaw_engine` (lib) generated 21 warnings (pre-existing baseline)
    Finished `release` profile [optimized] target(s) in 10.97s
```
PASS — 21 lib warning 全為 pre-existing baseline（與 Wave 4 T1 改動無關）;replay 模組 0 new warning。

### 5.2 cargo test --tests（21 suite）

```
running 2447 tests   test result: ok. 2447 passed; 0 failed
running 58 tests     test result: ok. 58 passed; 0 failed
... (19 more integration test files all PASS)
```

**0 sibling regression**。e2e 測試:

```
running 6 tests
test proof_3_fixture_missing_returns_typed_error ... ok
test proof_2_invalid_manifest_signature ... ok
test proof_helper_signed_manifest_round_trip ... ok
test proof_4_forbidden_path_trip_via_env_aborts_run ... ok
test proof_1_happy_path_synthetic_fixture ... ok
test proof_5_baseline_vs_candidate_two_runs ... ok
test result: ok. 6 passed; 0 failed
```

### 5.3 nm symbol audit（V3 §12 #8 binding）

```
$ REPLAY_RUNNER_BIN=rust/target/release/replay_runner SKIP_BUILD=1 \
  bash helper_scripts/ci/replay_runner_symbol_audit.sh
[replay_runner_symbol_audit] platform=Darwin → nm -gU
[replay_runner_symbol_audit] symbol count: 393
[replay_runner_symbol_audit] AUDIT PASS: 0 forbidden symbol detected (393 symbols scanned)
```

**AUDIT PASS** — 8 forbidden pattern class（acquire_lease / GovernanceHub / ipc_server / build_exchange_pipeline / decision_lease / exchange_dispatch / bybit_(rest|ws|api) / live_authorization / place_order / canary_writer::write）全 0 hit。

### 5.4 release binary smoke test

```
$ OPENCLAW_REPLAY_MAC_NO_PRIVATE=1 \
  target/release/replay_runner \
    --manifest /tmp/manifest.json \
    --output-dir /tmp/out

replay_runner: completed manifest_id=exp_smoke_cli status=completed \
  json=/tmp/out/replay_report.json
exit: 0
```

`replay_report.summary.txt`:
```
manifest_id: exp_smoke_cli
status: completed
execution_confidence: none
events_processed: 10
fills_emitted: 1
starting_balance: 10000
ending_balance: 10630
net_pnl: 630
guard_enforce_runtime_calls: 10
last_action_label: on_event:BTCUSDT@1714522140000
abort_reason: -
```

`replay_report.json` schema_version=1，envelope-level + result-level 雙重 `execution_confidence='none'`。

---

## 6. 不確定之處（向 PM push back）

### 6.1 既有 IntentProcessor / TickPipeline reuse 邊界（決策已採 minimal stub）

V3 §6.1 says replay "may share internal strategy / risk / TickPipeline / IntentProcessor modules"。**T1 沒 reuse**，理由:

- IntentProcessor 拖 `paper_state` (mutable global) + `canary_writer` (DB writer) + `database::DecisionFeatureMsg` (DB writer channel) + `bybit_rest_client::AccountManager` — 全 §6.2 forbidden list。
- 引入會使 nm symbol audit (R20-P2b-S10) AUDIT FAIL（grep `canary_writer::write` 與 `bybit_rest_client::*` 命中）。
- Task spec 明示「如 既有 module 在 Live profile 已混入 lease/ipc/dispatch wiring，T1 sub-agent 不擅修」。

**T1 採 minimal stub**：每 symbol 首見 emit 1 entry fill,後續 mark-to-market by close-to-close delta。Wave 5 P3a 若需「真實策略 replay 邏輯」應派 PA 重評 IntentProcessor 抽 `replay_compatible` feature gate（無 paper_state / canary_writer 依賴的子集）。**不阻塞 T1 acceptance**。

### 6.2 mac_policy_guard sibling pre-existing doctest fail（不順手修）

`cargo test --doc` 揭露 `replay::mac_policy_guard` line 32 + line 88 的 ASCII matrix table 被 doctest parser 誤判為 Rust code（Wave 3 commit `5a618ff` 起就有,自 Wave 3 land 後沒人跑過 `--doc`）。

我 5 個新 module 全用 ` ```text ` fence 避此問題,**不順手修 sibling** per CLAUDE.md §八「最小影響」+ E1 profile.md「不能在修復過程中順手優化未被要求的代碼」。建議 E5 / 後續 PA wave 修。

**不阻塞 T1 acceptance**：cargo test --tests 21/21 PASS;僅 cargo test --doc 看到該 2 fail。

### 6.3 manifest signing canonicalisation drift（T1 self-consistency 路徑）

T1 `load_and_verify_manifest` 對「磁碟內容自身」做簽名 / 驗證（自洽即 PASS）。Production deploy 必先確 Wave 4 T2 實作 SQL-backed `KeyArchive` + Python sibling signer 對 sorted-keys serde_json 的 byte-equal canonicalisation。

T1 self-consistency 路徑:
- 若 `<manifest_dir>/key.hex` 存在 → 用 fixture key 走完整 4-fail-mode HMAC verify
- 若不存在 → 印 stderr warning + 跳過 verify（fixture-driven smoke run 用）

**不阻塞 T1 acceptance**（fixture / smoke 用途已足）；Wave 4 T2 必處理 production wiring。

### 6.4 `research_notes/replay_fixtures/` baseline 目錄（PM curated）

V3 §6.4 baseline snapshot 屬 PM-curated sha-pin 流程;本 task 不在 PM baseline 路徑建。Test fixture 在 `tests/fixtures/replay_runner_e2e/`,與 production baseline 路徑刻意分離。

---

## 7. Operator 下一步

1. **E2 review**（強制鏈第一步）：
   - 對 PA boundary §5 forbidden import 0 hit 確認（`grep -rE 'intent_processor|ipc_server|bybit_(rest|ws|api)|governance_hub|decision_lease|canary_writer|database::writer|build_exchange_pipeline' rust/openclaw_engine/src/bin/replay_runner.rs rust/openclaw_engine/src/replay/{cli,fixture_loader,runner,report_writer}.rs` → 0 hit）
   - nm symbol audit AUDIT PASS / 393 symbol scanned / 0 forbidden hit 接受
   - V3 §12 #8/#10/#11 acceptance binding 6/6 e2e proof + 9 cli unit + 13 lib replay::* unit test PASS
   - 雙語 MODULE_NOTE 完整 / LOC < 800 警告線 / 不順手修 sibling 接受
   - **6.1 IntentProcessor 不 reuse 決策接受?** 若 PM 要求 reuse 應重派 PA 重 audit。

2. **E4 regression**（強制鏈第二步）：
   - Linux trade-core 跑 `cargo test -p openclaw_engine --features replay_isolated --tests` + release build smoke
   - 已 Mac dev 預驗 21 suite / 2447 lib + 58 integration + 19 sibling integration tests = 0 failure
   - 確認 Linux nm `--extern-only --defined-only` AUDIT PASS（macOS-primary, Linux-secondary per Wave 2 dispatch §2 #5）

3. **E3 review**（per workplan §3.1 P2a/P2b/P4/P6 安全 task 必活）：
   - CLI hand-roll vs argv injection / escape attack
   - manifest_signer T1 self-consistency 路徑切換 Wave 4 T2 SQL archive 時間表
   - 6.2 sibling doctest fail 處理建議

4. **PM 確認 4 ambiguity**（§6 上方）

5. **PM 統一 commit + push**（依 CLAUDE.md §七 強制鏈,等 E2 + E4 通過）

---

## 8. PM Commit Message Draft（單行 conventional commit）

```
feat(replay): isolated runner wrapper IMPL + e2e tests (Wave 4 P2b-T1)
```

---

## 9. 修訂歷史

| 版次 | 日期 | 修訂者 | 摘要 |
|---|---|---|---|
| V1 | 2026-05-03 | E1 | Wave 4 R20-P2b-T1 IMPL 完成；5 new lib module + bin entry rewrite + 6 e2e proof + fixture set + AUDIT PASS + 21/21 test suite 0 regression |
