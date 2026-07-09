# E2 Adversarial Audit — P0 Replay Tier A 4 sub-task post-IMPL（2026-05-11）

**Date**: 2026-05-11
**Agent**: E2（Senior Backend Reviewer + Adversarial Auditor）
**Object**: 8 local commits `ffc57d7f` → `d9a52572`（main HEAD，未 push origin）
**Mode**: read-only adversarial audit
**Time budget**: ≤30 min
**Verdict**: **APPROVE to E4** · 0 BLOCKER · 0 HIGH · 1 MEDIUM（trade-off doc） · 2 LOW · 1 WATCH

---

## 1. 範圍

8 個 commits（main branch，未 push origin）：

| Commit | E1 | 範圍 | LOC |
|---|---|---|---|
| `ffc57d7f` | E1-A | runner.rs is_pinned + position_state + ReplayPosition.owner_strategy | +224 |
| `7f6182b2` | E1-B | Python manifest scanner_config + strategy_params + risk_overrides echo | +570（含 test） |
| `a17ff37a` | E1-C | per-symbol latest_price_by_symbol HashMap | +265 |
| `01b05e29` | E1-D | 6 acceptance test pack | +686 |

合計：~1660 insertions / 1 deletion。

主要檔變動：
- `rust/openclaw_engine/src/replay/{runner.rs, risk_adapter.rs, apply_fill.rs, runner_tests.rs}`
- `rust/openclaw_engine/src/bin/replay_runner.rs`
- `rust/openclaw_engine/tests/{replay_tier_a_acceptance.rs, replay_runner_e2e_param_delta.rs}`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/replay_full_chain_routes.py`

---

## 2. PA §3.5 E2 必查 5 點

### 1) forbidden_guard 0 violation — PASS

- `nm srv/rust/target/release/replay_runner | grep -E 'router|ipc_server|build_exchange_pipeline|place_order|live_authorization'` → **0 hit**
- `grep -rn 'use crate::intent_processor::router\|use crate::ipc_server\|use crate::startup::build_exchange_pipeline'` 對 `replay/` + `tests/replay_tier_a_acceptance.rs` → **0 hit**
- V3 §6.2 + §6.3 isolation invariant 不變
- `cargo test --features replay_isolated --test replay_forbidden_guard_acceptance` → **4/4 PASS**（proof_1-4 全綠）

### 2) PaperPosition import 合規驗 — PASS

- `crate::paper_state::PaperPosition` = `paper_state/mod.rs:66 pub use containers::PaperPosition`
- `containers.rs:17` 確認：`#[derive(Debug, Clone, Serialize, Deserialize)] pub struct PaperPosition`（pure data）
- 唯一 `impl PaperPosition` `refresh_max_favorable(&mut self, ...)`（line 138-168）— in-struct field update，無 DB writer / IPC sender / 全域 mutate side
- runner.rs SAFETY 注釋 line 12+63 禁的是 `PaperState` module 全 mutate side；E1-A 借用 PaperPosition data type 與 production `tick_pipeline/mod.rs:32 use crate::paper_state::PaperPosition` 對稱合理
- `build_replay_position_borrow` 構造 owned PaperPosition value（每 field `.clone()` 或拷貝），無持 self borrow；後續 process_open_intent 可正常 `self.paper_snapshot.as_mut()` 不衝突

### 3) Tier A 5 task IMPL 對齊 PA spec — PASS

| Task | PA spec | E1 IMPL | Align |
|---|---|---|---|
| T1 is_pinned wire | runner.rs build_tick_context caller 推算 `scanner_timeline.is_active_at` + fallback true | runner.rs:1015-1019 `let is_pinned = self.scanner_timeline.as_ref().map(\|tl\| tl.is_active_at(...)).unwrap_or(true)` | ✅ |
| T2 position_state | per-tick 從 paper_snapshot 取 stack-local PaperPosition | runner.rs:1027-1032 `stack_pp_opt` 構造 + `pp_ref` borrow | ✅ |
| T2.5 ReplayPosition.owner_strategy | 新欄位 + apply_fill_open 寫入 | risk_adapter.rs:101 field + apply_fill.rs:634 簽名 + 681-689 fresh open path 寫入 | ✅ |
| T3 scanner_config echo | tomllib load TOML → manifest.scanner_config | replay_full_chain_routes.py:212-241 `_load_production_scanner_config()` + manifest:1636-1639 echo | ✅ |
| T4 strategy_params + risk_overrides echo | 直接 echo manifest top-level | replay_full_chain_routes.py:1640-1649 (`if x is not None: manifest[k] = x`) | ✅ |
| T5 per-symbol price | HashMap field + fallback chain | risk_adapter.rs:117-129 + 155-170 `latest_price_for(symbol)` + apply_fill.rs:693-696 / 736-739 寫雙路 | ✅ |

T1 fallback `.unwrap_or(true)` 對齊 synthetic walker proof_1/4/5 byte-equal baseline，與 PA §3.3 T1 一致。

### 4) 6 acceptance test 真實覆蓋 — PASS（1 trade-off）

| Test | 真實覆蓋驗證 | 結論 |
|---|---|---|
| `test_replay_pinned_tier_excludes_dynamic_add_symbols` | line 280-313 `scanner_timeline_skipped_events>=1` 驗 WLD 被 skip；BTC 在 decision_trace；WLD 不在 | ✅ real assertion |
| `test_replay_cross_strategy_position_blocks_secondary_open` | line 341-378 first-tick 真 fill (qty>0)，second-tick 0 emit (`btc_opens==1`)，entry_fill `fill_status ∈ filled/partial` | ✅ real assertion |
| `test_replay_uses_production_strategy_params` | line 425-468 兩 pipeline 都 `status=Completed` — **trade-off**：Strategy trait 無 public accessor 驗 `min_persistence_ms=120000` 真實在 strategy 內部；E1-D 自承「factory accept 即等價證據」 | ⚠️ partial（trait limitation） |
| `test_per_symbol_price_anchor_independence` | line 498-527 ≥3 symbols 不同 price assert + fallback 全空 → None | ✅ real assertion |
| `test_position_state_lifecycle_tracked_in_replay` | line 607-625 ≥2 BTC fills (Open+Close)，ending_balance > starting-5.0 (fee tolerance) | ✅ real assertion |
| `test_scanner_config_parsed_into_pinned_set` | line 651-685 3 active sym + 1 not-listed + lowercase 正規化 + pre-cycle ts | ✅ real assertion |

Stub Strategy impl（ContextObserver line 170-241 + OpenThenCloseStub line 545-595）審查：
- 只 `impl Strategy`（trait method）— 無 import forbidden surface
- `declared_alpha_sources` 返 const slice `&[AlphaSourceTag::Ta1m]` — 純 data
- `on_tick` 純 logic + `StrategyAction::Open/Close` emit — 不打 IPC / Bybit / DB

### 5) 跨平台 / cross-language consistency — PASS

- `cargo test --features replay_isolated --test replay_manifest_signer_xlang_consistency` → **8/8 PASS**（含 xlang_signature_byte_equal_for_all_fixtures）
- `grep -E '/home/ncyu|/Users/[^/]*ncyu'` 對所有 Tier A 改動 → **0 hit**
- Python tomllib 雙路徑：3.11+ stdlib + py3.10 `tomli` backport（requirements.txt 已含）
- Python `_resolve_settings_root()` 用 `OPENCLAW_BASE_DIR` env + `parents[5]` fallback，對齊 paper_trading_routes.py 既有 pattern

---

## 3. E2 對抗反問 5 點

### A. T2 lifetime borrow 風險 — PASS（cargo build/test 驗）

`stack_pp_opt` = `Option<PaperPosition>` **owned by-value**（map 後 `build_replay_position_borrow` 內部 `.clone()` field 出 owned 結構）—**不**持有 `self.paper_snapshot` 的 borrow。
`pp_ref: Option<&PaperPosition>` borrow `stack_pp_opt`（local stack data），不借 self。
`ctx = build_tick_context(..., pp_ref)` 借 pp_ref，per-iteration scope 結束。
後續 `process_open_intent` 取 `self.paper_snapshot.as_mut()` 無 borrow conflict。
**設計正確** — `cargo build --features replay_isolated` PASS 證實 NLL 通過。

### B. mk_snapshot 預種 BTCUSDT/ETHUSDT default 100.0 影響 — PASS

只在 `risk_adapter.rs:482 mod tests::mk_snapshot`（test-only helper）— 3 處 callsite（line 522/548/578）全用 BTCUSDT。預種 100.0 + fallback `latest_price=Some(100.0)` 對所有 symbol 等同舊全域 100.0 → 既有 test byte-equal 不破。`cargo test --lib` 2807 PASS 證實 0 regression。

### C. `is_active_at(ts_ms<scan_ts)` clamp — PASS

`scanner_timeline.rs:250 ts_ms.max(0)` — clamp negative 至 0。Production PG timestamp 永遠 unix epoch ms > 0；**這個 clamp 是 defense-in-depth 不是 production 邏輯關鍵**。test 6 `ts_ms=500 < scan_ts=1000` 是 binary_search Err(0) → None 路徑（line 256），非 clamp 觸發。**Safe**。

### D. manifest_version 1→2 backward compat — PASS

- Rust `replay/manifest_signer.rs` 對 manifest_version 字段**無 hard match**（只在 test fixture string 內出現 `manifest_version:1`）
- Python `replay/experiment_registry.py` register handler 對 manifest_version**無 schema validation**（`grep` 0 hit on register handler module）
- 11 既有 `test_full_chain_run_routes.py` PASS（含 register success assert）— register handler accept manifest_version=2
- **forward-compat OK**；malformed `manifest_version=999` 也不會 fail（因為兩端都不 check value）

### E. T5 fallback 0.0 vs Kelly sizer reject — PASS（IMPL 比 PA spec 建議更安全）

PA spec §10 第 1 點關注 `fallback 1.0` 可能放大 qty；**IMPL 實際用 `.unwrap_or(0.0)`** 不是 1.0。
Kelly sizer `compute_kelly_qty:197` 對 `price <= 0.0` 早期 return `max_qty`（passthrough，let P1 cap decide）—**不會** 0 division panic 或失控放大。
Gate 2.6 `if price > 0.0 { ... } else { kelly_qty }` 對 price=0 fallback 至 guardian_qty。
Gate 2.7 admission 用 price=0 算 notional/leverage 會在 `check_order_allowed` 處 reject。
**Real-world**：bin/replay_runner.rs line 388-403 one-pass 預種**所有** fixture symbol 至 `initial_price_by_symbol`，replay 對 fixture-internal symbol 出 intent，per-symbol map 必 hit；fallback chain 0.0 路徑只在 fixture-external symbol 才可能觸 — production replay 不會。

---

## 4. CLAUDE.md §九 8 條 + OpenClaw 9 條

### §九 8 條（Rust 為主，多數 N/A）

| Item | Status |
|---|---|
| 改動範圍與 PA 方案一致 | ✅ T1-T6 一一對齊 |
| except:pass / 靜默吞異常 | N/A（Rust 主、Python 用 logger.warning + None return，非 silent） |
| 日誌 %s 格式（非 f-string） | ✅ Python `logger.warning("... %s ...", path)` 正確 |
| 新 API 端點有 _require_operator_role() | N/A（無新 API endpoint，純 internal helpers） |
| HTTPException raise 順序 | N/A |
| detail=str(e) 已改 Internal server error | N/A |
| asyncio 路由無 blocking threading.Lock | N/A |
| 沒有私有屬性穿透 ._xxx | ✅ 0 hit |

### OpenClaw 9 條

| Item | Status |
|---|---|
| 跨平台 grep `/home/ncyu` `/Users/*ncyu` | ✅ 0 hit |
| 雙語注釋（2026-05-05 中文默認） | ✅ 新代碼注釋中文為主，必要 SAFETY 中英對照 |
| Rust unsafe 零容忍 | ✅ 0 unsafe block |
| Rust unwrap() 限不可恢復場景 | ✅ test 內 `.expect()` 帶 panic msg；production code 用 `.unwrap_or(0.0)` / `Result<>` |
| 跨語言 IPC schema 一致 | N/A（無 IPC 改動） |
| Migration Guard A/B/C | N/A（無 SQL migration） |
| healthcheck 配對 | N/A（無新 passive-wait TODO） |
| Singleton 登記 §九 表 | N/A（無新 singleton） |
| 文件大小 800/2000 | ✅ 全 ≤ 2000：runner 1237 / risk_adapter 613 / apply_fill 761 / runner_tests 1645 / acceptance 686 / bin 643 / Python routes 1931（全 > 800 警告線但 < 2000 hard cap）|
| Bybit API 改動先查字典手冊 | N/A（無 Bybit API 改動） |

---

## 5. Findings

| 嚴重性 | 位置 | 描述 | 建議 |
|---|---|---|---|
| **MEDIUM** | test 3 `test_replay_uses_production_strategy_params` | 因 Strategy trait 無 public field accessor，只能驗 factory accept 而非 `bb_reversion.min_persistence_ms=120000` 真實 propagate 到 strategy internal field；E1-D 自承「factory accept 即等價證據」trade-off | 不阻 deploy；follow-up 評估加 trait method `fn strategy_params_snapshot() -> StrategyParamsSnapshot`（單獨 PR） |
| **LOW** | E1-B 自承 manifest size 「~17KB << 256KB」 | 實測 scanner_config 4.2KB + strategy_params 8.3KB + risk_overrides 18.3KB = **30.8KB raw**（轉 JSON dict 大致同等），仍 << 256KB（8x headroom）但 E1-B 注釋估算偏低 | 不阻 deploy；follow-up 更新 manifest size estimate doc |
| **LOW** | mk_snapshot 預種 BTCUSDT/ETHUSDT default 100.0 hardcoded | E1-C 自承「default 預種兩個常用 symbol 而非全空」trade-off；既有 risk_adapter::tests fallback 走全域 latest_price=Some(100.0) byte-equal 不破，但兩個 hardcoded symbol 名稱與 production 25-sym pinned 高耦合 | 不阻 deploy；follow-up 改 mk_snapshot 全空 default + 顯式 helper（per E1-C 建議） |
| **WATCH** | E1-D 自承 memory.md ~1MB | E1 memory.md 整檔 Read 超 256KB limit；後續 sub-agent 啟動需 selective offset/limit | watch；下個 sprint 評估 memory archive 切分 |

**0 BLOCKER · 0 HIGH** — 不需 RETURN to E1。

---

## 6. 完整 test 驗證鏈

| Suite | Result |
|---|---|
| `cargo test --lib` | **2807 passed / 0 failed**（baseline 維持） |
| `cargo test --features replay_isolated --test replay_tier_a_acceptance` | **6/6 PASS** |
| `cargo test --features replay_isolated --test replay_forbidden_guard_acceptance` | **4/4 PASS**（proof_1-4） |
| `cargo test --features replay_isolated --test replay_runner_e2e` | **6/6 PASS**（proof_1-5 + helper） |
| `cargo test --features replay_isolated --test replay_runner_e2e_param_delta` | **2/2 PASS**（R5-T7 proof_7+8 xlang） |
| `cargo test --features replay_isolated --test replay_profile_acceptance` | **5/5 PASS** |
| `cargo test --features replay_isolated --test replay_mac_policy_acceptance` | **4/4 PASS** |
| `cargo test --features replay_isolated --test replay_manifest_signer_xlang_consistency` | **8/8 PASS**（含 xlang byte-equal） |
| `nm replay_runner | grep forbidden` | **0 hit** |
| `grep -E '/home/ncyu|/Users/*ncyu'` 跨 Tier A 改動 | **0 hit** |

---

## 7. 結論

**APPROVE to E4**

4 E1 並行 IMPL（T1+T2+T2.5/T3+T4/T5/T6）完成 P0 Replay Tier A counterfactual fix：

1. PA spec §3.5 E2 必查 5 點全 PASS（forbidden_guard / PaperPosition 合規 / T1-T6 對齊 / 6 acceptance 真實覆蓋 / xlang consistency）
2. E2 對抗反問 5 點全 PASS（lifetime / mk_snapshot default / clamp / manifest_version / fallback chain）
3. CLAUDE.md §九 8 條 + OpenClaw 9 條全綠
4. 完整 test 驗證鏈：lib 2807 + replay-specific 35 (6+4+6+2+5+4+8) 全 PASS / 0 regression / 0 forbidden symbol
5. 跨平台 grep / 文件大小 / 注釋默認中文 全綠
6. 0 業務邏輯 bug / 0 race / 0 leakage / 0 shortcut / 0 spec drift

**核心對抗發現**：
- T5 fallback IMPL 用 `.unwrap_or(0.0)` 比 PA spec 建議的 1.0 **更安全**（Kelly sizer `price<=0.0` 早期 return passthrough，不會失控放大）
- T2 lifetime 設計用 owned `stack_pp_opt` + borrow `pp_ref`，**不**持 self borrow，避免 PA spec §3.5 #1 預期的 owned-by-value to TickContext 重構（更乾淨）
- `manifest_version` 1→2 兩端 0 hard match，forward-compat 自然滿足

**Trade-off accepted**：test 3 用 factory accept 作等價證據（Strategy trait limitation），單獨 MEDIUM follow-up；不阻 current deploy。

---

## 8. Follow-up（不阻 deploy）

1. **trait method 加 `strategy_params_snapshot()`**：使 test 3 能直驗 `bb_reversion.min_persistence_ms=120000` 真在 strategy 內部
2. **manifest size estimate doc 更新**：實測 30.8KB raw vs E1-B 估算 17KB
3. **mk_snapshot 全空 default**：消除 BTCUSDT/ETHUSDT hardcoded 耦合
4. **E1 memory.md archive**：下個 sprint 評估切分以解 256KB Read limit
5. **跑 Tier A acceptance**（PA §3.1）：Option 2 ON/OFF + Phase 0 ON/OFF + A-Lite 4-combo replay 量化 PnL delta

---

E2 REVIEW DONE: APPROVE to E4 · report path: `srv/docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-11--replay_tier_a_post_impl_audit.md`
