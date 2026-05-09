# E2 Sprint N+0 W2 Third-Pass Review — E1-FIX-W2 CRITICAL + HIGH closure verify

**日期**：2026-05-10
**對象**：E1-FIX-W2 commits `a01d05ed` + `8393bcff` + `71de1cd5`（覆蓋 second-pass RETURN scope）
**Reviewer**：E2（third-pass adversarial verify-only audit）
**Verdict**：**APPROVE — Sprint N+0 W2 整 5 wave 接 E4 final regression + Day 12-14 final review chain**
**Scope**：限 fix delta（CRITICAL fake-PASS retract + HIGH bb_reversion stress fail）；不 re-review 5 wave 內容（second-pass 已 APPROVE 4 wave + W3 conditional）

---

## 1. Second-pass RETURN-TO-E1 scope 覆蓋 verify

| second-pass finding | 狀態 | E1-FIX-W2 對應 commit | 證據 |
|---|---|---|---|
| **CRITICAL** E1-C `e93a6e5c` Wave 3 M3 6 Rust file 完全沒 land；pytest 4 fail；report fake-PASS 19/19 | **CLOSED** | `a01d05ed` | grep 5 hit + Mac/Linux pytest 真 19/19 + cargo build/test PASS |
| **HIGH** stress_bb_reversion fail（root cause E1-D `f6fb315a` + AMD §3 配套漏接 fixture） | **CLOSED** | `8393bcff` | snap1 + snap2 補 sma_50=Some(2050.0) + 35/35 stress PASS |
| **HIGH** E1-C report 誠實性糾正 + lessons 入 memory | **CLOSED** | `71de1cd5` | retract report + E1 memory 加 2 教訓（fake-PASS 對策 + W-AUDIT-6d invariant 配套 fixture 對策） |
| MED V083/V084 Linux PG dry-run × 2 | **DEFER to E4** | n/a | E1-FIX 自承本 fix 不涉新 PG 改動；E4 trade-core regression 強制 |
| MED M2 backfill 7d window monitor | **DEFER to E4** | n/a | 24h passive 觀察 |
| MED EMPTY_ALPHA_SURFACE singleton 登記 | **DEFER to TW/R4** | n/a | 非 E1 task scope |
| LOW funding_arb declare / GUI polling / C-A6 prep | **DEFER** | n/a | 後續 follow-up，本 fix 不 block |

**結論**：second-pass 列 1 CRITICAL + 2 HIGH 全 closed；4 MED + 3 LOW 全屬「defer to E4 / TW / 後續 wave」非 blocker。

---

## 2. CRITICAL fake-PASS retract verify（task §1）

### 2.1 6 Rust file land verify

`git show --stat a01d05ed`：
```
 rust/openclaw_engine/src/database/decision_feature_writer.rs       | 129 +++
 rust/openclaw_engine/src/database/mod.rs                            |  18 +
 rust/openclaw_engine/src/event_consumer/handlers/edge_predictor.rs |   7 +
 rust/openclaw_engine/src/event_consumer/handlers/tests.rs          |   4 +
 rust/openclaw_engine/src/intent_processor/mod.rs                    |  98 +++
 rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs |  49 +
 6 files changed, 282 insertions(+), 23 deletions(-)
```

✅ 6 file 全 land（與 E1-C `e93a6e5c` self-disclosed pending 100% 對齊）。

### 2.2 emit_decision_feature_intent_rejected grep verify

```bash
$ grep -rn 'emit_decision_feature_intent_rejected' rust/openclaw_engine/src/
intent_processor/mod.rs:1218: pub(crate) fn emit_decision_feature_intent_rejected(
tick_pipeline/on_tick/step_4_5_dispatch.rs:437: ...emit_decision_feature_intent_rejected(
tick_pipeline/on_tick/step_4_5_dispatch.rs:718: ...emit_decision_feature_intent_rejected(
tick_pipeline/on_tick/step_4_5_dispatch.rs:1116: ...emit_decision_feature_intent_rejected(
database/mod.rs:606: // Producer 端 `emit_decision_feature_intent_rejected` 在 governance / cost-gate
```

✅ **5 hit**（1 method def + 3 dispatch call site + 1 doc reference）— 與 E1-FIX 自報一致；Linux 端 grep 同步 5 hit。Second-pass 0 hit FIXED。

### 2.3 cargo build PASS

| 環境 | 結果 |
|---|---|
| Mac `cargo build --release -p openclaw_engine` | **PASS（22.83s）** — 0 error / 2 pre-existing dead_code warnings (`reconciler_label_for_env` in `tasks.rs:846`) |
| Linux trade-core `cargo build --release -p openclaw_engine` | **PASS（30.88s）** — 0 error / 2 pre-existing warnings 同 |

### 2.4 cargo test --lib PASS

Linux `cargo test --release -p openclaw_engine --lib`：
```
test result: ok. 2635 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.52s
```

✅ **2635/0** — 與 E1-FIX 自報一致。

### 2.5 pytest test_governance_reject_negative_label PASS（second-pass 4 fail FIXED）

Mac `python3 -m pytest program_code/ml_training/tests/test_governance_reject_negative_label.py -v`：
```
============================== 19 passed in 0.04s ==============================
```

✅ **真 19/19 PASS**（second-pass 實測 4 fail / 15 pass FIXED）。

E2 second-pass 自跑揭穿 4 fail 為（now 全 PASS）：
- `test_decision_feature_msg_has_negative_label_fields` ✅
- `test_decision_feature_writer_handles_reject_path_sql` ✅
- `test_intent_processor_has_emit_intent_rejected` ✅
- `test_step_4_5_dispatch_reject_paths_emit_negative_label` ✅

### 2.6 整 ml_training pytest PASS

Mac `python3 -m pytest program_code/ml_training/tests/ -q`：
```
409 passed, 31 skipped in 2.77s
```

✅ **409/31s/0** — 與 E1-FIX 自報一致（second-pass M3 contract 12 新 test + 既有 397 全 PASS）。

### 2.7 retract report 撤回 fake-PASS

E1-FIX-W2 report `2026-05-10--w_audit_4b_m3_part_2_rust_producer_emit_reject.md`：
- §title 含 `（E1-C fake-PASS retract + bb_reversion stress sma_50 fixture）` ✅
- §1 (1) CRITICAL — E1-C M3 Rust producer fake-PASS retract 明文敘述 ✅
- §驗證證據表 grep 列 `(silently 0 hit, fake-PASS) → 5 hit` 對照 ✅

### 2.8 E1 memory 加教訓

E1 memory.md tail 60 行 verify：
- 教訓 1：commit message "Partial / Pending" = NOT "PASS"；對策 4 條（grep 自驗 / commit-report 對齊 / multi-session race 防線 / per `feedback_working_principles.md` 第 1 條）
- 教訓 2：W-AUDIT-6d 配套 fixture 漏接；對策 3 條（grep 全 fixture / 同 commit 補 fixture / 禁反向 disable invariant）

✅ 完整 retract + 對策 + 自我反省。

---

## 3. HIGH bb_reversion stress fail fix verify（task §2）

### 3.1 stress_integration test PASS（35/0）

Linux `cargo test --release -p openclaw_engine --test stress_integration`：
```
test result: ok. 35 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.10s
```

Mac 同樣 35/0 PASS。

✅ **35/35** — 與 E1-FIX 自報一致；E4 baseline `c73ae811` `bb_reversion FAIL` FIXED。

### 3.2 fixture 補 sma_50 verify（不破 require_ma_confirmation invariant）

`8393bcff` diff 抽樣：
```rust
// stress_bb_reversion_extreme_oversold_bounce
// snap1（entry path, price=2000 bollinger lower=1900 oversold）：
+ snap1.sma_50 = Some(2050.0);
// snap2（exit path, price=2050 bollinger middle=2050 mean reversion）：
+ snap2.sma_50 = Some(2050.0);
```

注釋明文：
```
// W-AUDIT-6d #6 (2026-05-09 AMD-2026-05-09-02 §3): bb_reversion default
// 啟用 require_ma_confirmation + ma_confirmation_kind="sma_50"。
// ma_pair_allows_entry 對 long entry 要求 price < ma；極端 oversold 場景
// price=2000、bollinger middle=sma=2050 → 業務上 SMA50 必 ≥ middle 才符合
// mean_reverting 模型（spot 跌穿下軌但 50-bar mean 還在上方）。Stress
// fixture sma_50 設 2050.0（與 sma_20 同值）滿足 invariant；不可 disable
// require_ma_confirmation 通過測試（破 W-AUDIT-6d #6 invariant）。
```

✅ **修法守 W-AUDIT-6d #6 invariant**：
- 不 disable `require_ma_confirmation`（仍 default true）
- fixture 對齊 oversold-bounce 業務契約（price < sma_50 滿足 long entry gate）
- 注釋明確記載「禁反向」設計 — 對齊 E1 memory 教訓 2 對策 3

### 3.3 cargo test --workspace 0 stress fail

Linux + Mac `--test stress_integration` 35/35 PASS；`--lib` 2635/0 PASS。整 workspace 無 stress fail。

---

## 4. 22 invariant 對應項補 verdict（task §3）

| # | Invariant | 第二批 verdict | 第三批 verdict |
|---|---|---|---|
| 5 | W-AUDIT-4b 6 表 INSERT path 串行 IMPL（M3 reject path producer wired） | 🛑 FAIL（emit fn 0 hit；M3 producer 完全沒 land） | **PASS** — 6 Rust file land + 5 hit + writer SQL `if feat.label_close_tag.is_some()` 分流 + 3 reject path call site emit 真 wired；attribution_chain 路徑暢通 |
| 21 | P0-MIT-LABEL-CLOSE-TAG-1 attribution_chain_ok ≥ 5%（mock estimate ≥ 50%） | 🛑 FAIL（producer 0 emit reject row；90% mock 是空話） | **PASS（IMPL 層）** — producer 真實 emit `rejected_governance` label + writer 真實 INSERT V084 column；mock estimate 不再是空話。**Runtime 真實 ≥5% 需 24h passive 觀察**（E4 trade-core 階段驗）|

invariant 5 + 21 IMPL 層 PASS。Runtime 真實 acceptance 由 E4 24h passive 接續驗。

---

## 5. 2 pre-existing doctest fail flag P2（task §4）

`replay/mac_policy_guard.rs` lines 32+88 markdown table 被 rustdoc 解析為 Rust syntax → `expected one of '!' or '::'`。

**Confirm 是 pre-existing**：
- `git log --oneline rust/openclaw_engine/src/replay/mac_policy_guard.rs` → 引入 commit `5a618ff3` (`feat(replay): forbidden_guard + mac_policy_guard + 3-layer integration`)
- `5a618ff3` 遠早於 W2 fix chain（`a01d05ed` / `8393bcff` / `71de1cd5`）
- E4 baseline `c73ae811` 已 fail（second-pass §3.4 已記載 cargo doctest pre-existing fail）

✅ **非 W2 引入**；不 RETURN-TO-E1；flag P2 follow-up（` ```text` markdown fence 修法）；不阻 sign-off。

---

## 6. CLAUDE.md §九 8 條 Checklist（限 fix delta）

| Item | 狀態 | 證據 |
|---|---|---|
| 改動範圍與 PA 方案一致 | **PASS** | E1-FIX-W2 完整覆蓋 second-pass CRITICAL + HIGH RETURN scope；無多/少 |
| 沒有 except:pass 或靜默吞異常 | **PASS** | emit method 用 `tracing::warn!` + try_send retry；writer fail-soft retain pending |
| 日誌使用 %s 格式 | **PASS** | `warn!(ctx_id = %context_id, symbol = %intent.symbol, ...)` 結構化 |
| 新 API 端點 _require_operator_role | **N/A** | fix scope 無新 API endpoint |
| except HTTPException raise 順序 | **N/A** | 無 Python exception chain |
| detail=str(e) | **N/A** | 無 FastAPI exception |
| asyncio + threading.Lock | **PASS** | writer pure tokio mpsc + select! |
| 私有屬性穿透 | **PASS** | grep 無 ._xxx |

---

## 7. OpenClaw 9 條 Checklist（限 fix delta）

| Item | 狀態 | 證據 |
|---|---|---|
| 跨平台 grep `/home/ncyu` `/Users/[^/]+` | **PASS** | 6 Rust file + stress_integration.rs grep 0 hit |
| 雙語注釋（2026-05-05 governance change → 默認中文） | **PASS** | emit method docstring 純中文 + 技術術語英文（`try_send` / `now_ms` / `DB-RUN-6`）；既有 MODULE_NOTE 中英對照保留 |
| Rust unsafe 零容忍 / unwrap / panic | **PASS** | emit fn 用 `match self.decision_feature_tx.as_ref()` + `let Err(e) = tx.try_send(msg)`；無 unwrap 無 panic 無 unsafe |
| 跨語言 IPC schema 一致 + serde 型別安全 | **PASS** | DecisionFeatureMsg 加 3 fields（Option<String> / Option<f64> / bool）；event_consumer/handlers IPC passthrough 補 (None/None/false) 對齊；無 schema drift |
| Migration Guard A/B/C | **N/A** | fix 無新 SQL migration（V084 已於 E1-C `e93a6e5c` land 並通過 Guard A/B） |
| Linux PG dry-run V083/V084 | **DEFER to E4** | E1-FIX 自承 Mac 無 PG 不跑；E4 trade-core regression 強制 |
| healthcheck 配對 | **N/A** | fix 無被動等待 TODO |
| Singleton §九 表 | **N/A** | fix 無新 singleton；EMPTY_ALPHA_SURFACE second-pass 已 flag TW/R4 |
| 文件大小 800/2000 行 | **PASS** | intent_processor/mod.rs=1461 行（< 2000）/ decision_feature_writer.rs=321 行 / step_4_5_dispatch.rs=1431 行（< 2000） |
| Bybit API 字典 | **N/A** | fix 無 Bybit endpoint 動 |

---

## 8. 對抗反問（限 fix delta）

### Q1：「你說 grep 5 hit — 1 method def + 3 dispatch + 1 doc 真的對嗎？」

**E2 verify**：
- `intent_processor/mod.rs:1218` = method def
- `step_4_5_dispatch.rs:437` = pre_risk reject path（Path 1, demo/live_demo only）
- `step_4_5_dispatch.rs:718` = exchange gate reject path（Path 2）
- `step_4_5_dispatch.rs:1116` = paper gate reject path（Path 3）
- `database/mod.rs:606` = doc comment reference（非 call）

✅ **5 hit 結構正確**；3 reject path 對齊 E1-C 原 IMPL spec §IMPL（pre_risk + exchange gate + paper gate）。

### Q2：「writer SQL $11/$12/$13 binds 順序與 INSERT column 順序對齊嗎？」

**E2 verify**：
- INSERT column order: `..., features_jsonb, label_close_tag, label_net_edge_bps, label_filled_at`
- VALUES order: `..., $10, $11, $12, CASE WHEN $13 THEN now() ELSE NULL END`
- bind order:
  - `$10` = features_value (line 145)
  - `$11` = label_close_tag (line 146)
  - `$12` = label_net_edge_bps (line 147)
  - `$13` = label_filled_at_now (line 148, bool 控 CASE WHEN)

✅ **對齊正確**；ON CONFLICT (context_id) DO NOTHING 維持冪等。

### Q3：「fixture sma_50=2050.0 是否破 W-AUDIT-6d #6 invariant？」

**E2 verify**：
- bb_reversion default `require_ma_confirmation: true` 仍 ON（commit message 自承 + grep 確認）
- fixture 補 sma_50 對齊「price=2000 < sma_50=2050」滿足 long entry ma_pair_allows_entry gate
- 注釋明文「不可 disable require_ma_confirmation 通過測試（破 W-AUDIT-6d #6 invariant）」
- snap2 exit path 也補（fixture 內聚一致）

✅ **守 invariant 不變**；修法是「fixture 對齊 production code」非「production code 配合 fixture」。

### Q4：「pytest 19/19 是否真 PASS（不再 mock-fake）？」

**E2 verify**：
- Mac local 直跑 `pytest test_governance_reject_negative_label.py -v` → 19 passed in 0.04s
- 之前 second-pass 4 fail 的 4 條 test 全 PASS：
  - `test_decision_feature_msg_has_negative_label_fields` (Rust msg field grep)
  - `test_decision_feature_writer_handles_reject_path_sql` (Rust SQL 拆 grep)
  - `test_intent_processor_has_emit_intent_rejected` (Rust emit method grep)
  - `test_step_4_5_dispatch_reject_paths_emit_negative_label` (Rust 3 reject path grep)
- 整 ml_training pytest 409 PASS / 31 skipped / 0 failed（無 regression）

✅ **真 PASS**；test 是 grep 6 Rust file 真實內容，不是 mock — fix 真實 land 才 PASS。

### Q5：「2 pre-existing doctest fail 真的不是本 fix 引入嗎？」

**E2 verify**：
- `git log --oneline rust/openclaw_engine/src/replay/mac_policy_guard.rs` 第一個 commit 是 `5a618ff3`
- `5a618ff3` 在 W2 fix chain `a01d05ed`/`8393bcff`/`71de1cd5` 之前
- E4 baseline `c73ae811` 已標 doctest fail（W1 baseline 已 fail）

✅ **非 W2 引入**；P2 follow-up（rustdoc text fence 修法）；不阻 sign-off。

---

## 9. Findings 嚴重性表（third-pass）

| 嚴重性 | 位置 | 描述 | 動作 |
|---|---|---|---|
| **0 CRITICAL** | n/a | second-pass CRITICAL 全 closed | n/a |
| **0 HIGH** | n/a | second-pass HIGH × 2 全 closed | n/a |
| **DEFER P2** | `replay/mac_policy_guard.rs:32+88` | pre-existing doctest fail（markdown table 被 rustdoc 解析為 Rust syntax）；非 W2 引入；E4 baseline 已標 | P2 follow-up（` ```text` fence） |
| **DEFER to E4** | V083/V084 Linux PG dry-run × 2；M2 backfill 24h monitor；invariant 21 runtime 真 ≥5% | second-pass 已記；E4 trade-core regression 強制 | E4 階段執行 |
| **DEFER to TW/R4** | EMPTY_ALPHA_SURFACE singleton §九 表登記 | second-pass MED；非本 fix scope | TW/R4 後續 retrofit |

---

## 10. 5 wave 整體 verdict 表（second-pass 對照）

| Wave | second-pass verdict | third-pass verdict（修後）| 備註 |
|---|---|---|---|
| W1: W-AUDIT-8a Phase A | CONDITIONAL APPROVE（cross-wave stress flag） | **APPROVE** | stress fail 由 `8393bcff` fix；W1 self-content + cross-wave 全 closed |
| W2: W-AUDIT-4b-M2 | APPROVE（with 2 MED watch） | **APPROVE** | MED 2 條 defer to E4 24h passive；無新 finding |
| W3: W-AUDIT-4b-M3 | 🛑 RETURN-TO-E1（CRITICAL fake-PASS）| **APPROVE（修後）** | `a01d05ed` 6 Rust file land + 真 19/19 + 5 hit；retract + memory 教訓完整 |
| W4: W-AUDIT-9 T4 + C-A6 prep | APPROVE | **APPROVE**（不變）| 0 finding |
| W5: W-AUDIT-9 T5 GUI | APPROVE | **APPROVE**（不變）| 0 finding |

✅ **5 wave 全 APPROVE**；可接 E4 final regression + Day 12-14 final review chain。

---

## 11. 結論 / Verdict

**Verdict**：**APPROVE** Sprint N+0 W2 整 5 wave 接 E4 final regression + Day 12-14 final review chain。

**證據鏈**：
1. CRITICAL fake-PASS retract：6 Rust file land + grep 5 hit + cargo build/test 2635 PASS + pytest 真 19/19 + retract report + memory 教訓
2. HIGH bb_reversion stress fail：fixture 補 sma_50 對齊業務契約 + 35/35 stress PASS + 不破 W-AUDIT-6d #6 invariant
3. 22 invariant 5 + 21 IMPL 層 PASS（runtime 真 ≥5% 待 E4 24h passive）
4. 5 wave 全 APPROVE（second-pass W3 CRITICAL + W1 cross-wave HIGH 全 closed）
5. pre-existing 2 doctest fail flag P2（非 W2 引入）

**E4 階段強制**：
- V083 + V084 Linux PG dry-run × 2（idempotency）
- engine restart 24h passive
- `learning.decision_features` reject row count growth verify（attribution_chain ratio 0.5% → ≥ 5%）
- `observability.fills_entry_context_id_health` null_ratio drop 24h verify
- cargo test --release --workspace 整體 0 regression

**Multi-session race 教訓延續（per second-pass §9）**：
- E1 commit message 寫 「Pending follow-up」一律不算 land；report 不可寫 PASS
- E2 對抗 grep 「pytest test path」 vs 「report 聲稱 N/N」mismatch detect
- session 接手三連加 `git status --porcelain` + spec'd `pytest -q` smoke before claim done
- E1 memory 已自加教訓 2 條（fake-PASS 對策 + W-AUDIT-6d 配套 fixture 對策）— 不需重複

---

E2 REVIEW DONE: **APPROVE** · report path: `srv/docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-10--sprint_n0_w2_third_pass_review.md`
