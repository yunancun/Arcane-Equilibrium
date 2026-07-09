# E2 Adversarial Review — REF-20 Sprint B2 R5-T3 (wire adapter into runner.rs)

**Date**: 2026-05-05 · **Reviewer**: E2 · **HEAD**: main `c679a8b4` (R5-T1+T2 baseline) · R5-T3 unstaged on working tree
**E1 sign-off**: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-05--ref20_sprint_b2_r5t3_impl.md`
**E2 R5-T1+T2 review (PASS to E4)**: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-05--ref20_sprint_b2_r5t1t2_e2_review.md`

## §1 Executive Verdict

**PASS to E4** — R5-T3 wire-up 通過對抗審查。**0 RETURN TO E1**；**3 LOW finding**（記錄在 §7，不阻 R5-T4 dispatch；含 1 條 E1 sign-off doc-text inconsistency + 2 條 caller-side notes）。

關鍵驗證全綠：
- 2478 lib unit / 0 fail / 0 ignored
- 58 replay:: (54 baseline + 4 R5-T3 new) / 0 fail
- 6 e2e proof / 0 fail（含 proof_4 forbidden trip + proof_5 baseline-vs-candidate）
- 478 binary symbol / 0 forbidden
- 0 forbidden import on runner.rs（V3 §6.2）
- 0 cross-platform path hardcode

## §2 Optional adapter pattern vs PA Q10 wholesale replace

E1 偏離 PA Q10「wholesale replace synthetic walker」，改採 **Optional adapter pattern**：
- `strategy_adapter.is_some()` → `execute_adapter_pipeline()`（真實 strategy + 6-Gate 風控）
- `strategy_adapter.is_none()` → `execute_synthetic_walker()`（legacy；保 proof_1/4/5 byte-equal）

**E2 立場**：Optional pattern accept。理由：
1. proof_1/4/5 e2e 是 V3 §12 acceptance binding 的 evidence baseline；wholesale replace 會破 byte-equal contract
2. synthetic walker 為 `tests/replay_runner_e2e.rs` 提供 fast deterministic baseline（無需 strategy/risk impl 即跑通）
3. R5-T4 CLI 後 production 路徑強制 set adapter — synthetic walker 退化為 e2e regression baseline

**對抗反問結果**：
- Q：production 永遠 set adapter？— 是（R5-T4 CLI dispatch 必先 build strategy_adapter + risk_adapter + snapshot 三個必填參數，無 fallback 路徑）
- Q：synthetic walker 該 deprecated marker？— 否，walker 為 e2e regression test asset。但 R5-T4 dispatch brief 應明列「CLI 必走 adapter path」+ 建議加 telemetry metric `replay.path={'adapter','synthetic'}` 在生產區分用法（**LOW finding F-A**）
- Q：dual-path 維護複雜度？— 接受。execute() body 13 LOC dispatch 純枚舉判斷；adapter / walker 各自 self-contained，0 cross-call

**結論**：Optional pattern 是 safer trade-off。**accept；R5-T4 dispatch 注意 F-A**。

## §3 apply_fill_open + apply_fill_close PnL 公式 vs paper_state mirror

**對 paper_state/fill_engine.rs::apply_fill (line 276-385) byte-by-byte 對齊**：

| 路徑 | paper_state | runner.rs | 結論 |
|---|---|---|---|
| Same-direction extend (weighted avg entry) | `(old_entry * old_qty + fill_price * qty) / new_qty` (line 337) | `(pos.entry_price * pos.qty + fill_price * qty) / new_qty` (line 929) | 公式 byte-equal |
| Opposite-direction full close (qty >= pos.qty) | `close_qty = pos.qty.min(qty)` + `pnl = (fill - entry) * close_qty` (long; short signed) (line 299-304) | `realised_per_unit * pos.qty` (qty=pos.qty path) (line 941) | 公式 byte-equal；over-fill 兩端皆 silent-discard 多餘 qty |
| Opposite-direction partial close (qty < pos.qty) | `close_qty = qty` + `remaining = pos.qty - qty > 1e-12` 留剩餘 (line 310-314) | `realised_per_unit * qty` (qty < pos.qty path) + `after.qty -= qty` (line 949-951) | 公式 byte-equal；剩餘倉留 |
| Fresh open | `entry_price = fill_price` (line 372) | `entry_price = fill_price` (line 961) | byte-equal |
| Fee deduction | `self.balance -= fee` (line 291) | 0（Sprint A baseline `fee=0.0`） | **scope-out**；Sprint C R6 補 |
| `apply_fill_close` | n/a (paper_state 無對應 close-only fn — close 走 apply_fill 反向) | `if pos.is_long { fill - entry } else { entry - fill }` * pos.qty (line 988-993) | 公式邏輯一致；StrategyAction::Close 無 qty 字段 → 全平 contract 正確 |

**balance NaN 防範**：apply_fill 後 `self.balance = snap.balance`（line 964 / 995）— 若 fill_price 非 finite 會傳染 NaN；但 fail-loud 在 `with_adapter_pipeline` 邊界已截（balance 必 finite + latest_price 至少一 anchor），輸入端 contract 強制。`fill_price` 來源 = `event.close` 或 `intent.limit_price` — fixture_loader 已強型 PA design line 178 `assert event.close > 0.0`。**NaN 不會在 runtime 出現**。

**partial-close 不變量 H-2**：`StrategyAction::Close` enum schema (`strategies/mod.rs:62-66`) 只 `symbol/confidence/reason`，**無 qty 字段** → close 一律全平 → `apply_fill_close` 全 remove 是正確設計。NO BUG。

**結論**：**apply_fill PnL 公式 byte-equal mirror paper_state**。Sprint A baseline fee=0 是 PA design 既決議 scope-out（Sprint C R6 引入）。

## §4 fail-loud snapshot construction (F-3 fix)

`with_adapter_pipeline` setter (line 541-585) 兩條 fail-loud：

```rust
// Check 1: NaN/Inf balance reject
if !snapshot.balance.is_finite() {
    return Err(ReplayError::InvalidSnapshot {
        reason: format!("balance must be finite f64, got {} (NaN/Inf rejected)", ...)
    });
}
// Check 2: empty latest_price + empty positions reject
if snapshot.latest_price.is_none() && snapshot.positions.is_empty() {
    return Err(ReplayError::InvalidSnapshot {
        reason: "latest_price is None and positions is empty — caller must seed at least one ..."
    });
}
```

**驗證**：
- `ReplayError::InvalidSnapshot` variant 確存於 `runner.rs:304`，Display impl 確存於 `runner.rs:316-321`
- 4 inline R5-T3 unit test 中 2 條覆蓋（`adapter_pipeline_rejects_nan_balance_snapshot` line 1318-1341 + `adapter_pipeline_rejects_empty_anchor_snapshot` line 1343-1369）— 均 PASS
- E2 R5-T1+T2 review §8 F-3 LOW finding 已 close

**結論**：F-3 fix **complete + tested**。

## §5 forbidden_guard runtime trip + proof_4 preservation

**兩 path 都接 forbidden_guard runtime trip**：
- `execute_synthetic_walker` line 667：`forbidden_guard::enforce_at_runtime(&action)`，action=`on_event:{symbol}@{ts_ms}`
- `execute_adapter_pipeline` line 745：`forbidden_guard::enforce_at_runtime(&action)`，action=`on_tick:{symbol}@{ts_ms}`

每 tick 必呼，所有 action 失敗都 propagate 至 `?` map_err 設 `AbortedForbidden { action }` status。

**proof_4 (`tests/replay_runner_e2e.rs::proof_4_forbidden_path_trip_via_env_aborts_run`) 實測 PASS post-R5-T3**（§1 6 e2e PASS 驗證）。

**結論**：guard runtime trip **complete preserved**；proof_4 不退。

## §6 ReplayResult.decision_traces 下游影響

**Schema 擴展**：`ReplayResult` 新 field `decision_traces: Vec<DecisionTraceEntry>`（runner.rs:269）+ `#[serde(default)]`（向後兼容）。

**Python downstream 影響**：
- `grep -rln decision_traces program_code/` → **0 hit**（Python 端 0 file 引用）
- R5-T5/T6/T7 將寫 `simulated_fills_writer.py` + `experiment_registry.py` — R5-T3 預先擴 schema 為 R5-T5 預備，但 Python 暫不消費

**xlang invariant**：
- `manifest_signer.{rs,py}` canonical_bytes 公式 0 改動（runner.rs 不影響 manifest envelope）
- `ReplayResult` 是 runner 輸出，與 manifest 簽署無關
- `ReplayResult.decision_traces` 加 field 不影響 `replay.run_state` / `replay.simulated_fills` Postgres schema（V050 17 col 不動，待 R5-T5 補 jsonb payload 才升級）

**結論**：**0 break risk**；R5-T5/T6 acceptance 寫 writer 時直接消費；canonical_bytes / xlang 0 影響。

## §7 Findings (3 LOW，0 RETURN)

| # | Severity | Location | Issue | Disposition |
|---|---|---|---|---|
| F-A | LOW | E1 sign-off + R5-T4 dispatch brief pending | synthetic walker 無 deprecated marker / 無 production-path metric；CLI 後 production 永走 adapter，但運維上難用 telemetry 區分異常走 fallback | **不阻 R5-T3**。建議 R5-T4 dispatch brief 明列「CLI 必 set adapter（無 fallback path）」+ R5-T4 metric `replay.path={'adapter','synthetic'}` 上報 |
| F-B | LOW | E1 sign-off §7 line 142 | 寫「2474 與 R5-T1+T2 baseline 同數」與 §1 line 24「+250 LOC = 4 R5-T3 inline tests」自相矛盾；E2 實測 lib 為 2478（baseline 2474 + 4 R5-T3 new），E1 sign-off 文字 typo (filter mode count snapshot mismatch) | **不阻 E4**。E1 應在 commit message 訂正為「2478 = 2474 baseline + 4 R5-T3 inline new」 |
| F-C | LOW | runner.rs:1017-1019 `into_result.starting_balance` | `if self.paper_snapshot.is_some() { DEFAULT_STARTING_BALANCE } else { DEFAULT_STARTING_BALANCE }` — 兩 branch 同值（E1 §9.2 push back 為 PR proof_1/5 contract 穩定點所致），但分支冗餘可直接寫 `let starting_balance = DEFAULT_STARTING_BALANCE;`；future R5-T5 加 `adapter_starting_balance` 時再分流 | **不阻 R5-T3**。E1 R5-T5 升級時自然清理；亦可 E2 typo-fix tier 直接修，但會擾動 E1 chain — 留 R5-T5 |

**0 CRITICAL / 0 HIGH / 0 MEDIUM / 0 RETURN-TO-E1**

## §8 LOC 1466 高內聚 exception 立場

**E1 §9.1 push back**：
- 1466 LOC < 1500 hard cap（CLAUDE.md §九 governance）
- 已超 800 警告線
- E1 提 Option A (accept) vs Option B (split into runner_apply.rs)

**E2 立場：accept Option A**（high-cohesion exception，比照 commands.rs 1343 / scanner/scorer.rs 1437 先例）：

理由：
1. **單一責任**：runner.rs 全檔負責「IsolatedPipeline 生命週期 + state mutation」；7 new method（`with_adapter_pipeline` / `execute_synthetic_walker` / `execute_adapter_pipeline` / `process_open_intent` / `process_close_intent` / `apply_fill_open` / `apply_fill_close`）+ 1 helper（`build_tick_context`）皆 IsolatedPipeline 內部 state machine，拆檔反需多重 import / 暴露 visibility（`pub(super)` vs 跨檔 `pub(crate)` 上升）
2. **bilingual docstring 是 LOC 主要膨脹源**：1466 LOC 含 +250 inline test + ~150 雙語 docstring + ~100 SAFETY 注釋；實業務代碼僅 ~470 LOC
3. **R5-T4/T5 添加 LOC 風險**：R5-T4 fixture_loader 升級走 `fixture_loader.rs`（不擾 runner.rs）；R5-T5 Python writer 走 Python；R5-T6/T7 acceptance fixture 走 separate test file。runner.rs LOC 進一步增 < 100，仍 < 1500 cap

**建議**：accept Option A。**R5-T4 啟動前先評估 LOC 走勢**；若 R5-T4 mock indicators 注入觸 `build_tick_context` 多 ~200 LOC 才破 1500 → 屆時 R5-T5 階段啟動 Option B 拆 `runner_apply.rs`。

**Pre-existing baseline exception clause（CLAUDE.md §九 2026-05-02 governance）不適用此 case**（runner.rs 從未 > 1500，是 R5-T3 一次性推近 1500），**需 Option A high-cohesion 形式 accept**。

## §9 治理對照 + boundary 確認

| 治理項 | 結論 |
|---|---|
| CLAUDE.md §二 16 條原則 | ✓ 都遵守（adapter path 仍經 6-Gate；snapshot mutation 純 in-memory；0 trading.* mutation；Decision Lease unaffected） |
| CLAUDE.md §四 硬邊界 | ✓ 都遵守（max_retries=0 unaffected；live boundary unaffected；authorization.json unaffected） |
| CLAUDE.md §七 跨平台 | ✓ runner.rs 0 路徑硬編碼 |
| CLAUDE.md §七 雙語注釋 | ✓ 7 新 method + 1 helper 全中英對照 |
| CLAUDE.md §九 LOC | ⚠ 1466 < 1500 hard cap（accept high-cohesion exception per §8） |
| CLAUDE.md §九 Singleton | ✓ R5-T3 0 新 singleton |
| V3 §6.2 forbidden import | ✓ `grep -nE 'use crate::(paper_state|canary_writer|...)' runner.rs` → 0 hit |
| V3 §12 #10 forbidden runtime trip | ✓ 兩 path 皆呼 `enforce_at_runtime` per tick；proof_4 PASS |
| V3 §12 #11 execution_confidence='none' | ✓ runner.rs:1042 hardcode `"none".to_string()` |
| V3 §12 #12 fail-closed | ✓ snapshot 構造 + with_adapter_pipeline 兩處 fail-loud |
| Sprint A R3 acceptance (4 表 row > 0) | ✓ 不退（R5-T3 不動 Python writer 路徑） |
| Bybit API 字典 | n/a（R5-T3 0 改動 REST/WS） |
| §九 既登記 non-training surface (replay.simulated_fills evidence_source_tier) | ✓ R5-T3 寫入 fill row 走 `tier_label` 來自 fixture（synthetic_replay 為 S3 default）— 不破 ML training 隔離不變量 |

## §10 E4 接手條件

E4 可直接接手回歸：
- ✓ 2478 lib unit PASS（4 NEW R5-T3 inline 全綠）
- ✓ 6 e2e proof PASS（proof_4 forbidden trip + proof_5 baseline-vs-candidate）
- ✓ 478 binary symbol / 0 forbidden
- ✓ 0 forbidden import / 0 跨平台 / Bilingual / LOC compliance
- ✓ 0 RETURN-TO-E1 finding

**E4 範圍**：full lib regression + e2e regression + symbol audit re-run + cross-platform grep + Linux 端 xlang_consistency pytest（Mac 端 venv 不可跑，Linux 端通過後 R5-T3 push 至 origin）。

E4 PASS 後 R5-T4 (CLI integration) dispatch unblock；R5-T4 dispatch brief 應加 F-A note (production-path metric)。

---

**E2 邊界遵守**：read-only audit · 0 直修 · 0 業務代碼.

E2 REVIEW DONE: PASS · 0 RETURN finding · 3 LOW notes · R5-T3 → E4 unblock · R5-T4 dispatch 待 E4 + F-A acknowledgement
