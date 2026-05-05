# E2 Adversarial Review — REF-20 Sprint B2 R5-T1 + R5-T2 Foundation

**Date**: 2026-05-05 · **Reviewer**: E2 · **HEAD**: main `2a69addb` (E1 IMPL files unstaged)
**E1 sign-off**: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-05--ref20_sprint_b2_r5t1t2_impl.md`
**PA design**: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-05--ref20_sprint_b_task_dag.md` §4.1 + §4.2
**Persistence**: PM persisted per E2 closure protocol.

## §1 Executive Verdict

**PASS to E4** — R5-T1 + R5-T2 architectural foundation 通過對抗審查。**0 退回 E1 修復條目**。**5 LOW finding 全為 scope-out 或 R5-T3 caller 端注意項**，不阻 B2 dispatch。

## §2 strategy_adapter.rs 對抗結論

| Probe | 結論 |
|---|---|
| `compute_intent_signature` canonical bytes (6 field) byte-equal PA spec line 339 | PASS |
| Strategy trait reuse (0 trait change) byte-equal forward `actions = self.strategy.on_tick(ctx)` | PASS (line 146 + 181 確認) |
| StrategyAction 2 variant (Open / Close) 全 trace record；trait 真實只 emit 這 2 variant | PASS |
| `ReplayProfile::Isolated` constructor reject Live/LiveDemo/PaperLegacy | PASS (test `non_isolated_profile_rejected` 覆蓋全 3 variant) |
| `into_trace` consume self reproducibility (grep `rand`/`Instant::now` 在 grid + ma 0 hit) | PASS |
| `parameter_delta_flips_signature` test 真覆蓋 qty 1.0→2.0 | PASS (signature 64-char hex 確認；同 input deterministic) |

## §3 risk_adapter.rs 對抗結論

| Probe | 結論 |
|---|---|
| 6 Gate 順序 vs router.rs:184-455 byte-equal (1.5 → 1.6 → pre_guardian_qty → 2.0 → 2.5 → 2.6 → 2.7) | PASS (line-by-line 對照) |
| Gate 1.0 + 1.4 SKIP 是設計意圖 (V3 §6.2 + AMD-2026-05-02-01 flag OFF for replay) | PASS (docstring line 14-23 + 50-55 明寫) |
| `evaluate(&self, &snapshot)` pure (grep `RefCell|Mutex|UnsafeCell` 0 hit；`&self` not `&mut self`) | PASS |
| `pre_guardian_qty` mirror (router.rs:267-271) + reducing-path zero-leverage (router.rs:286-294) | PASS (risk_adapter.rs:264-288 byte-equal) |
| Guardian + check_order_allowed reuse pure (grep `paper_state|canary_writer|ipc_server|database` 在 risk_checks.rs / kelly_sizer.rs / guardian.rs 0 hit) | PASS |
| 6/8 Gate scope-out — `per_strategy_symbol_rejection` / `apply_governor_order_constraints` / BLOCKER-3 D15 都不在 risk_adapter | scope-out accepted (PA spec line 432「復刻 router.rs:359-455」明確不含；F-1 LOW finding) |

## §4 forbidden import audit confirm

```
$ grep -nE 'use crate::(paper_state|canary_writer|database|ipc_server|governance_hub|live_authorization|decision_lease|bybit_rest_client|bybit_private_ws|intent_processor::router)' \
    rust/openclaw_engine/src/replay/strategy_adapter.rs \
    rust/openclaw_engine/src/replay/risk_adapter.rs
(0 hits)
```

V3 §6.2 forbidden import audit GREEN ✓

完整 use list (13 import 全部 V3 §6.2 allowlist 內):
- strategy_adapter.rs: `sha2::*`, `crate::intent_processor::OrderIntent`, `crate::replay::profile::*`, `crate::strategies::{Strategy, StrategyAction}`, `crate::tick_pipeline::TickContext`
- risk_adapter.rs: `crate::config::RiskConfig`, `crate::intent_processor::OrderIntent`, `crate::ml::kelly_sizer::*`, `crate::replay::profile::*`, `crate::risk_checks::check_order_allowed`, `openclaw_core::guardian::*`

## §5 cargo test + symbol audit re-verify

```
cargo test --release --features replay_isolated -p openclaw_engine --lib: 2474 passed / 0 failed
cargo test ... 'replay::': 54 passed / 0 failed
cargo test ... --test replay_runner_e2e: 6 passed / 0 failed
bash helper_scripts/ci/replay_runner_symbol_audit.sh: 414 symbols / 0 forbidden
pytest .../tests/replay/test_manifest_signer_xlang_consistency.py: 13 passed
```

**0 regression**: 2474 lib unit + 6 e2e proof + 13 xlang + 414 binary symbol 全綠。

## §6 跨平台 + bilingual + LOC compliance

```
grep '/home/ncyu|/Users/[a-z]+' on adapter sources: 0 hit
wc -l: strategy_adapter 398 / risk_adapter 546 / mod 185 / runner 676 / profile 322 / forbidden_guard 534 — all <800
```

| 項 | 結論 |
|---|---|
| 跨平台 grep | 0 hit ✓ |
| Bilingual MODULE_NOTE | strategy_adapter line 4-37 + risk_adapter line 4-69 中英對照 ✓ |
| docstring 雙語 (公開 type + method) | 100% ✓ |
| SAFETY 不變量 注釋雙語 | strategy line 115-119 + risk line 100-104 雙語 ✓ |
| LOC 800 警告線 / 1500 hard cap | 兩 adapter 全 < 800 ✓ |

## §7 R5-T3 wire-up 預備風險

派 R5-T3 時 PM 須在 dispatch brief 標記：

1. **owned mut adapter，不可 Arc<Mutex>**：`Strategy::on_tick(&mut self, ctx)` 使 `ReplayStrategyAdapter::on_tick(&mut self)`，IsolatedPipeline 必持 owned `mut` field (E1 §8.3 已 push back PM accept)
2. **snapshot 構造端 fail-loud**：R5-T3 從 fixture 構造 `ReplayPaperSnapshot`，必對 NaN balance / None latest_price fail-loud (router.rs 真實由 paper_state 提供，自身 NaN-safe；R5-T3 不對齊則 silent bypass — F-3 LOW)
3. **synthetic walker line 478-503 將 replace**：runner.rs `IsolatedPipeline::execute` body 重寫，但 Proof 4 forbidden trip + Proof 5 baseline-vs-candidate (`tests/replay_runner_e2e.rs`) 必保留邏輯
4. **fixture_loader 端 IndicatorSnapshot**：PA design §13 line 691 已決議「fixture builder 端跑 IndicatorEngine 一次」；R5-T3 + fixture_loader 配合餵 `TickContext.indicators`
5. **apply_fill 歸 R5-T3**：`ReplayPaperSnapshot` rename + apply_fill 不在 R5-T2 (PA design line 437-450 named ReplayPaperState；E1 §8 沒明列 — F-4 LOW)，R5-T3 必自實作 mutation 邏輯
6. **import path 不可動**：R5-T2 的 `crate::ml::kelly_sizer` + `crate::risk_checks` + `openclaw_core::guardian` import path 是 V3 §6.2 audit GREEN 證據，R5-T3 wire 不可改寫成 indirect path

## §8 Findings (5 LOW，0 退回 E1)

| # | Severity | Location | Issue | Disposition |
|---|---|---|---|---|
| F-1 | LOW | `risk_adapter.rs` whole | 6/8 Gate scope-out (per_strategy / governor / D15)；A5 risk delta 範圍受限 | 不阻 B2；PA scope-out 已知。R5-T7/T8 acceptance fixture 走 `position_size_max_pct` (Gate 2.7) 路徑 OK。Sprint C 後續補 |
| F-2 | LOW | `strategy_adapter.rs:214-234` | canonical bytes 6 field (不含 limit_price/confluence_score/persistence/time_in_force/maker_timeout)；某 strategy parameter 改動不 flip signature | 不阻 B2；A4 acceptance fixture 必走 `grid_count` (qty path) |
| F-3 | LOW | `risk_adapter.rs:255` + `:340-344` | NaN balance 不 trigger Gate 1.6 (NaN<=0.0 is false)；None latest_price 使 Gate 2.6 P1 cap 無效 | 不阻 B2；行為 mirror router.rs (同 silent)。R5-T3 IsolatedPipeline::execute 構造 snapshot 必 fail-loud |
| F-4 | LOW | E1 sign-off §2 | `ReplayPaperState` rename → `ReplayPaperSnapshot` + apply_fill 不在 R5-T2 — design refinement 沒明列 push back | 不阻 B2；R5-T3 sign-off 報告需明列此 rename + apply_fill ownership boundary |
| F-5 | LOW | `strategy_adapter.rs:149` | empty-tick 不 record；A4 fixture 0-fill scenario 兩 candidate 看似 same outcome | 不阻 B2；A4 fixture 端必保證 fill ≥1 (PA §5.1 example `grid_count=10 vs 20` 兩邊 ≥2 fill 符合此預設) |

## §9 E4 接手條件

E4 可接手回歸 (R5-T3 → T4 wire 前必須 R5-T1+T2 sign-off PASS):
- ✓ 2474 lib unit test PASS
- ✓ 6 e2e proof PASS (含 Proof 4 forbidden trip + Proof 5 baseline-vs-candidate)
- ✓ 13 xlang_consistency 不破
- ✓ 414 binary symbol 0 forbidden
- ✓ 0 forbidden import / 0 跨平台 / Bilingual + LOC compliance

E4 範圍：full lib regression + e2e regression + symbol audit re-run + cross-platform grep。E4 PASS 後 R5-T3 dispatch unblock。

PM note: E2 已 ran E4-equivalent 全套 (2474 lib + 6 e2e + 13 xlang + 414 symbol + cross-platform)，PM 直接 commit + dispatch R5-T3 是 acceptable shortcut (Sprint A precedent)。

---

**E2 邊界遵守**：read-only audit · 0 直修 · 0 業務代碼.

E2 REVIEW DONE: PASS · 0 RETURN finding · 5 LOW notes · R5-T3 dispatch unblocked
