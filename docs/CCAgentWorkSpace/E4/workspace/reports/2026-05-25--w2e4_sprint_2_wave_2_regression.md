---
report: W2-E4 Sprint 2 Wave 2 regression — V109 schema + V109 writer (W2-D) + W1-C M4 baseline preserve
date: 2026-05-25
author: E4 (Test Engineer)
phase: Sprint 2 v5.8 Stream B Wave 2 W2-E4 regression
parents:
  - W2-E E2 verdict d15cbe56 (M4 RETURN-TO-E1 / V109 APPROVE)
  - W1-F V109 schema 16796d13
  - W2-D anomaly_event_writer skeleton a8d4bfa8
  - W1-C M4 round 2 fix 99709a2f (HIGH BLOCKER closure mid-flight during E4 run)
head_at_review: 99709a2f (= origin/main at E4 start)
verdict: PASS — 0 W2-attribution failure · 1 cargo pre-existing (Sprint 1B Earn 875de212 scope leak) + 7 pytest pre-existing (W-AUDIT-7c structural drift)
---

# §1 TL;DR Verdict

**PASS** — W2-D writer + V109 schema + W1-C M4 round 2 三件均 regress-clean。

- V109 schema PG state empirical: 23 col / hypertable num_dim=1 / 6 index / compression+retention policy 雙 land — 全對齊 W1-F-retry verdict。
- V109 writer 14/14 cargo test PASS（兩遍同綠），對齊 W2-D self-claim。
- W1-C M4 round 2 (99709a2f) 19 new schema-grep regression test land；m4_miner cargo 46/0；helper_scripts/m4 pytest 70/0（51 + 19 new）。
- 1 cargo fail (`layer_2_fence_archive_policy_diagnostic_only`) 全 attributable to Sprint 1B Earn Wave B 875de212 (2026-05-23) test rewrite without prod helper sync — 0 W2 scope leak。
- 7 pytest fail 全 pre-existing W-AUDIT-7c / Sprint 1B structural drift — 0 W2 attribution。
- Hard boundary 0 觸碰；0 mock 滲透；0 cross-platform hardcode；0 unsafe。

# §2 Numbers Empirical

## §2.1 Mac cargo test --workspace --release 雙跑

| Run | Passed | Failed | Ignored | Test result lines | Non-flaky |
|---|---|---|---|---|---|
| Run 1 (cargo test --workspace --release --no-fail-fast) | 4205 (≈ recomputed) | 1 | 6 | 45+ blocks | ✅ |
| Run 2 (canonical fresh post-99709a2f) | **4205** | **1** | **6** | 51 blocks | ✅ same fail |
| Run 3 (sanity recount) | 4205 | 1 | 6 | 51 blocks | ✅ |

| Item | Count | Baseline (Sprint 5+ Wave 1 Phase D HEAD c4e1411d) | Delta |
|---|---|---|---|
| Cargo workspace passed | 4205 | 4018 | **+187** (W2-D writer 14 + W1-C 46 + M4 R2 19 schema-grep + sibling lib growth) |
| Cargo workspace failed | 1 | 0 | **+1** (Sprint 1B Earn Wave B 875de212 scope leak; not W2) |
| Cargo workspace ignored | 6 | 5 | +1 |

## §2.2 Mac pytest 雙跑（--ignore both test_pure_utils.py collisions）

| Run | Passed | Failed | Skipped | Errors | Subtests | Time |
|---|---|---|---|---|---|---|
| Run 1 (--ignore tests/misc_tools only) | 6158 | 7 | 45 | 1 (tests/ml_training/test_pure_utils.py 同名衝突) | 14 | 127s |
| Run 2 (--ignore both) | 6158 | 7 | 45 | 0 | 14 | 128s |
| Run 3 (--ignore both -r f) | **6158** | **7** | **45** | 0 | 14 | 154s |

| Item | Count | Baseline (Sprint 5+ Wave 1 Phase D HEAD c4e1411d) | Delta |
|---|---|---|---|
| pytest passed | 6158 | 6122 | **+36** (W1-C-R2 19 schema-grep + W1-C 17 baseline) |
| pytest failed | 7 | 18 | **-11** (W-AUDIT-7c carry-over chipped down sprint to sprint) |
| pytest skipped | 45 | 30 | +15 |

非 flaky 三遍同綠（同 7 fail file + line set）✅

## §2.3 V109 schema PG state empirical（read-only verify）

```bash
$ ssh trade-core "psql ... -c '... anomaly_events ...'"
```

| Check | Expected | Actual | Verdict |
|---|---|---|---|
| col_count `learning.anomaly_events` | 23 (per W1-F retry + v2 amend §7) | **23** | ✅ |
| hypertable num_dimensions | 1 (time chunk) | **1** | ✅ |
| Indexes count | ≥ 5 (per V109 §4) | **6** (pkey + observed_at_idx + severity + strategy + symbol + taxonomy) | ✅ |
| Compression policy | 1 (30d) | **1** | ✅ |
| Retention policy | 1 (180d) | **1** | ✅ |

Indexes 6 detail:
- anomaly_events_observed_at_idx (DESC by observed_at)
- anomaly_events_pkey (id PRIMARY KEY)
- idx_anomaly_severity_observed (severity, observed_at DESC partial)
- idx_anomaly_strategy_observed (strategy_id, observed_at DESC partial)
- idx_anomaly_symbol_observed (symbol, observed_at DESC partial)
- idx_anomaly_taxonomy_observed (taxonomy, observed_at DESC partial)

Anomaly events row count: 0 (預期；scaffold 階段未接 detector)。

## §2.4 V109 writer (W2-D) Mac cargo test empirical

```
$ cd rust && cargo test --release -p openclaw_engine --lib database::anomaly_event_writer
running 14 tests
test result: ok. 14 passed; 0 failed; 0 ignored
```

14/14 test name list 對齊 W2-D self-claim:
1. test_validate_engine_mode_5_enum_complete
2. test_validate_taxonomy_9_enum_pass_and_invalid_reject
3. test_validate_severity_4_enum_and_invalid_reject
4. test_validate_detection_method_4_enum_and_hmm_garch_reject ← ADR-0036 黑名單
5. test_validator_contains_adr0036_blacklist_strings ← schema-coupled
6. test_insert_sql_locked_table_name
7. test_insert_sql_locked_columns_match_v109_schema
8. test_insert_sql_returns_id
9. test_insert_sql_uses_numeric_cast
10. test_anomaly_event_row_struct_has_23_fields
11. test_amplification_cap_24h_window_semantic
12. test_amplification_cap_sql_window_lock
13. test_error_display_messages_informative
14. test_write_anomaly_event_minimal

兩遍同綠（19.31s / 27.74s build；test 0.00s）✅

## §2.5 W1-C M4 round 2 (99709a2f) empirical

`cargo test --release -p openclaw_core --lib`:
- 416 passed / 0 failed / 0 ignored
- m4_miner submodule subset: **46/0** (E2 review §1.2 對齊)

`pytest helper_scripts/m4/tests/ -q`:
- **70 passed / 0 failed** in 0.03s
- = 51 (existing leak/algorithm/effect_size/attribute/writeback) + **19 new schema-grep regression** (per 99709a2f commit body)

W1-C-R2 commit body 列出修復清單對齊 E2 §2.4 4 點 + 額外 1 個（close_reason_code→exit_reason）:
- fills_loader.py: size→qty, close_fill→entry_context_id IS NOT NULL, realized_net_bps→derived bps, close_reason_code→exit_reason
- liquidations_loader.py: liq.size→liq.qty, aggregator_type filter removed (5min rolling 走 event_window detector)
- tick_window.rs:64 pop_front().unwrap() → if let Some(evicted) early return

Empirical 3 source loader SQL Linux PG read-only 真實跑（per 99709a2f commit body）：fills 3 row + derived bps，0 ERROR；liquidations 3 row，0 ERROR。

# §3 nm + strings symbol scan

## §3.1 release binary 新代碼未 baked（expected per task spec §5）

```bash
$ nm rust/target/release/openclaw-engine | grep -E "anomaly_event_writer|alpha_tournament|m4_miner"
$ strings rust/target/release/openclaw-engine | grep -E "anomaly_event_writer|m4_miner|anomaly_events"
```

兩 grep 全 0 hit。**Expected** — release binary 是 19:06 build，**早於 W2-D (18:59:27) + W1-C-R2 (19:10:39) commits**；deployment 走 `--rebuild` atomic restart 才會 bake 入 production binary。Per Sprint 5+ Wave 1 Phase D E4 教訓「release binary strings 不會留 Rust internal identifier」— Rust monomorphize + symbol stripping 後 fn name 不出現在 strings 輸出，cargo test --workspace 全綠 + source land 三條獨立 chain 是 land 證據。

**本 step 不是 deployment gate，是 baseline check**（per task spec Step 5）。實際 Wave 2 deploy 走 atomic restart `helper_scripts/restart_all.sh --rebuild` 後 production binary 才會包含 W2-D + W1-C 新 code。

## §3.2 nm 0 mock 滲透（AC-5 invariant 維持）

```bash
$ nm rust/target/release/openclaw-engine | grep -cE "mock_instant|tokio::time::pause|spike"
0
```

✅ **0 hits** — release binary 0 mock symbol；test/spike feature gate 編譯時隔絕成功。

# §4 Hard boundary 0 觸碰 verify

```bash
$ git diff origin/main~10..origin/main -- rust/ helper_scripts/ | grep -E "live_execution_allowed|system_mode|OPENCLAW_ALLOW_MAINNET|live_reserved|authorization\.json"
（0 lines）
```

✅ 0 hits 對 production-side write，5-gate 保護鏈未被觸動。

W2 commits 觸碰範圍純 learning path（anomaly_events / hypotheses / m4_miner / source loader SQL）— 不創 order 入口，不繞 Decision Lease，不寫 authorization.json，不動 5-gate；M4 / W2-D writer 設計即 `live_order_intent=FALSE`（per E2 §5 + M4 docstring + GovernanceHub lease wired through）。

# §5 Cross-platform + unsafe + file size verify

| Check | 結果 |
|---|---|
| `/Users/ncyu` / `/home/ncyu` hardcode in W2 scope (V109 + W2-D + W1-C) | 0 hit ✅ |
| `unsafe` block in W2 scope | 0 hit ✅ |
| Largest file size in W2 scope | M4 event_window.rs 344 LOC; anomaly_event_writer.rs sub-800; V109.sql 832 LOC（在 hard cap 2000 內）✅ |

# §6 1 cargo fail attribution — Sprint 1B Earn Wave B 875de212

## §6.1 Failure detail

```
running 9 tests in btc_lead_lag_panel_fence_integration
test layer_2_fence_archive_policy_diagnostic_only ... FAILED
test result: FAILED. 8 passed; 1 failed
```

panic line 300:
```
assertion failed: !should_spawn_btc_lead_lag_producer(false, false)
"Layer 2 archive: OPENCLAW_ENABLE_PAPER=1 + paper-only must not spawn"
```

## §6.2 Root cause = test rewrite without prod helper sync

`git diff 875de212~..875de212 -- rust/openclaw_engine/tests/btc_lead_lag_panel_fence_integration.rs`：
- Test 從 (a) `OPENCLAW_ENABLE_PAPER=1 → spawn paper` 改為 (a) `DIAGNOSTIC=1 → spawn diagnostic` + (b) `PAPER=1 → ignored`

`git diff 875de212~..875de212 -- rust/openclaw_engine/src/panel_aggregator/btc_lead_lag.rs`：
- **0 diff** — 生產 helper 函數 `should_spawn_btc_lead_lag_producer` 未同步改

當 OPENCLAW_ENABLE_PAPER=1 時，生產 helper line 67-68 仍返 `true`（spawn），但 test 期 `false`（archive 政策禁 spawn）→ contract drift fail。

## §6.3 W2 scope attribution check

```bash
$ git log --since "2026-05-25" --oneline --name-only 99709a2f a8d4bfa8 ae9a2dd8 16796d13 | grep -E "btc_lead_lag|panel_fence"
（0 hit）
```

W2 4 commits（V109 + W2-D + W1-C + W1-C-R2）全部 0 touch btc_lead_lag.rs / btc_lead_lag_panel_fence_integration.rs / panel_aggregator 目錄。**0 W2 attribution**。

## §6.4 為什麼 Sprint 5+ Wave 1 Phase D baseline 寫 0 fail

Sprint 5+ Wave 1 Phase D 報告（HEAD c4e1411d）寫「concurrent session prompt 預期 1 fail 在 HEAD c4e1411d Mac workspace 實測 0 fail（比預期更乾淨）」— 那時 fail test 已存在但不在當時 HEAD（c4e1411d 早於 875de212 2026-05-23）。回看 commit 序：
- c4e1411d (Sprint 5+ Wave 1 R2): 2026-05-23 之前
- 875de212 (Sprint 1B Earn Wave B): 2026-05-23 之後

**Sprint 5+ Wave 1 Phase D 是 baseline 較早 + 不含 875de212 改動**，所以當時 0 fail。本 E4 baseline 是 99709a2f（2026-05-25），跨越 875de212 ⇒ 該 1 fail 是中間 Sprint 1B Earn 並行期 scope leak 帶入。

## §6.5 修法建議（不阻 W2 deploy；放 PA carry-over）

- E1 一行 prod helper line 67-71 改：把 `Ok(value) => value.trim() == "1"` 改為 `Ok(_) => false`（PAPER=1 → ignored 對齊 paper Archive Policy）
- 或反向：rollback test 改回 PAPER=1 → spawn（但 paper-pipeline-disabled-by-default 2026-04-16 policy 寫死 paper 是 archive，test 對）
- 建議 E1 一行修 prod helper + E2 + E4 spike round 順手清

# §7 7 pytest fail attribution — 0 W2 scope leak

| Failed Test | Attribution | W2 scope? |
|---|---|---|
| test_common_confirm_modal_has_dialog_a11y_and_focus_trap | W-AUDIT-7c structural drift | ❌ 不在 W2 4 commits |
| test_archive_top_level_files_are_all_indexed | docs index drift | ❌ |
| test_event_consumer_hot_files_stay_split_under_limit | dispatch.rs > 800 LOC | ❌ |
| test_common_js_exposes_custom_prompt_modal | W-AUDIT-7c modal helper 遷出 | ❌ |
| test_common_css_defines_action_risk_zones | GUI CSS 改動 | ❌ |
| test_live_stop_emergency_and_close_actions_are_visually_separated | GUI CSS 改動 | ❌ |
| test_writer_cli_defaults_to_dry_run_and_requires_apply_ack | v072 writer literal drift | ❌ |

`git log --since="2026-05-22" --oneline -- tests/structure/* tests/test_v072_*` → 結合 W2 4 commits 0 touch 確認。

**全 7 pytest fail 0 attributable to W2 deploy**（per Sprint 1B-late E4 report 2026-05-22 trial + Phase D 2026-05-23 trial 同 file list 持續 drift）。

# §8 W1-C M4 baseline state — 不阻 V109 deploy

W1-C round 2 fix（99709a2f）在 E4 run 期間 land（19:10:39，介於 E4 開始 ~19:06 與最終 verify 之間）。

| Item | Pre-R2 (ae9a2dd8) | Post-R2 (99709a2f) | Verdict |
|---|---|---|---|
| openclaw_core lib 全部 | 416/0 | **416/0** | unchanged ✅ |
| m4_miner subset | 46/0 | **46/0** | unchanged ✅ |
| helper_scripts/m4/tests | 51/0 | **70/0** | +19 schema-grep regression ✅ |
| 5 schema-incorrect column (E2 HIGH BLOCKER) | 存在 | **closed** | ✅ |
| 第 6 個 column drift (close_reason_code) | 未發現 | **closed** | ✅ |
| tick_window.rs:64 unwrap() (E2 LOW) | 存在 | **closed** | ✅ |
| 19 schema-grep regression test | 不存在 | **存在** (per source_loader_schema.py whitelist + blacklist) | ✅ |

**W1-C M4 round 2 已 closed all E2 HIGH+MEDIUM+LOW finding**。E2 round 2 re-review 後可進 W2-D MIT cron wire-up 或下一 Wave。

**不阻 V109 deploy 的條件確認**：W1-C M4 與 V109 解耦（per E2 §9.2）— V109 是純 schema land + writer skeleton，M4 是學習 detector；W1-C R2 已 closed 即使未進 E2 round 2，V109 + W2-D 也可獨立 deploy。

# §9 Atomic restart 建議（W2-D V109 writer 進 production binary）

W2-D anomaly_event_writer 14/14 cargo test 全綠 + source land + Mac aarch64 build green，**但未 baked 入 release binary**（19:06 build vs 18:59 commit + 19:10 W1-C-R2）。

進 production 要求：
1. **Linux atomic restart**：`ssh trade-core "helper_scripts/restart_all.sh --rebuild --keep-auth"` 觸發 build_then_restart_atomic.sh（per E5 H-1 fix 已 land 2026-05-21 hygiene Option E）
2. **proc-exe alignment verify**：restart 後 `ls -l /proc/<engine_pid>/exe` 應 link 至 on-disk binary（不是 `(deleted)` 狀態），且 sha256 應等 on-disk 對應 SHA
3. **strings smoke**：`strings /proc/<engine_pid>/exe | grep -E "anomaly_event_writer|m4_miner"` 應 hit
4. **PG anomaly_events 寫入測試**：直接 INSERT 1 行 test fixture，verify hypertable chunk 創建 + compression+retention policy 生效

不阻 W2-D source-land 簽發：本 E4 verdict = source-land PASS；deployment 走 PM dispatch（後續 atomic restart wave）。

# §10 教訓 / 工程觀察

## §10.1 [本 E4 新增 6 條]

1. **cargo workspace 真實 passed 數 4205 ≠ Sprint 5+ Wave 1 Phase D 4018 baseline**：原因 = sibling lib growth + W1-C 46 + W2-D 14 + W1-C-R2 19 schema-grep test。baseline 對比應追蹤 commit chain attribution 而非 single number diff；E4 報告必列 attribution breakdown。

2. **W1-C-R2 round 2 commit 在 E4 run 期間 land（mid-flight rebase）是 multi-session race 警示**：E4 開始時看到 3 unstaged file，run 中途看到 commit 99709a2f land（吸收這 3 file），但本 E4 仍對齊 99709a2f HEAD 是合法的（per `feedback_multi_session_memory_race` SOP「不認識改動禁 revert」）。**規則**：E4 開始時 `git fetch + log` 確認 HEAD；run 中如發現 HEAD 變化，重 verify baseline。

3. **layer_2_fence_archive_policy_diagnostic_only Sprint 1B Earn 875de212 scope leak**：test rewrite 將 expected behavior 從 PAPER=1→spawn 改為 PAPER=1→ignored，但 production helper btc_lead_lag.rs:67-71 未同步改 → contract drift cargo fail。**規則**：test contract change 必驗 prod side helper 是否需同步 amend；E1 amend test 前 grep prod 端定義 1 處對齊。`paper-pipeline-disabled-by-default` (2026-04-16) policy 已 mandate paper archive；本 fail 是 875de212 漏了 prod helper line 67-71 對齊。

4. **release binary 19:06 build 早於 W2-D + W1-C-R2 commit 是 atomic restart 缺口**：strings grep 0 hit anomaly_event_writer / m4_miner 是 expected baseline；本 E4 不 fail 此項。**規則**：E4 verify 包含「release binary 內含 vs 不含」是 deployment gate；如 expected 入 release，必 trigger atomic restart 後 strings grep；如未 deploy，verify「source land + cargo green」三條 chain。

5. **pytest fail 從 18 (Sprint 5+ Wave 1 Phase D) → 7 (本次)**：-11 fail 是 sibling W-AUDIT-7c carry-over chipped down across Sprint 1B + Sprint 2 pre-readiness。每 Sprint 結尾「contract drift sweep」是固定 1-2 hr slot 計畫；現在 W-AUDIT-7c 已從 24 GUI → 6 (7 - 1 v072) 大幅減小。

6. **--ignore=tests/misc_tools/test_pure_utils.py 一個不夠，需加 tests/ml_training/test_pure_utils.py**：兩個同名 file collision；Sprint 5+ Wave 1 Phase D 報告寫「公平 baseline 對齊需重複前次 --ignore=」單一 path，本 E4 發現有 3 個 test_pure_utils.py（local_model_tools / misc_tools / ml_training），兩 collision 對：misc_tools vs local_model_tools 一對；ml_training vs local_model_tools 另一對。**規則**：E4 pytest baseline 對齊命令必兩 --ignore 都加；Sprint 5+ Wave 1 Phase D 報告漏 ml_training 路徑（被 1 collection error 看成 single counted 而非 baseline 對齊）。

## §10.2 [回顧前次 E4 教訓延續]

- **release binary strings 不會留 Rust internal identifier**（Sprint 5+ Wave 1 Phase D 教訓 #1）→ 本 E4 直接驗證 0 hit anomaly_event_writer / m4_miner 是 expected；不 fail。
- **pytest 公平 baseline 對齊需重複前次 `--ignore=`**（Phase D 教訓 #3）→ 本 E4 補完 ml_training/test_pure_utils.py ignore；額外發現 misc_tools/test_pure_utils.py 也需 ignore。

# §11 Multi-session race check（per CLAUDE 操作人格 + multi-session-race-SOP-1 Phase 2）

| Item | 結果 | 證據 |
|---|---|---|
| 5a fetch + 2h sibling window | ✅ | `git fetch --prune origin` × 2（E4 start + post W1-C-R2 land）；HEAD = origin/main = 99709a2f |
| 5b status clean | ✅ post-R2 absorption | E4 start 3 unstaged file（被 W1-C-R2 sub-agent 並行修中），E4 mid 99709a2f 吸收→ 1 untracked dir (`funding_short_v2/`) 屬隔壁 session WIP |
| 5c unknown WIP 禁 revert | ✅ | 0 revert / 0 checkout / 0 stash drop；E4 從未觸碰 unstaged file |
| 5d sign-off path clean | n/a | E4 不 commit（doc-only commit 由本報告觸發） |
| 5e sibling overlap | ✅ | HEAD synced；99709a2f land 不 attribute 本 E4，只 absorb mid-flight |

# §12 Verdict + dispatch readiness

## §12.1 E4 final verdict

**PASS** for Wave 2 三件:
- **V109 schema (W1-F)**: APPROVE → E4 PASS · PG 5 query 全 land · idempotency double-applied per W1-F-retry · 6 index + 2 policy.
- **V109 writer skeleton (W2-D)**: APPROVE → E4 PASS · 14/14 cargo test non-flaky · source land · 0 mock · 0 hard boundary 觸碰 · ADR-0036 黑名單對齊.
- **W1-C M4 round 2 (99709a2f)**: APPROVE → E4 PASS · 416 lib + 46 m4 + 70 helper_scripts (19 new schema-grep) · 6 schema column drift closed + tick_window unwrap closed.

## §12.2 W1-C M4 不阻 V109 deploy 條件確認

- V109 schema = 純 hypertable land + Guard A/B/C 反向防護；獨立可 deploy（已 land 2026-05-23 raw apply）✅
- W2-D writer = 純 INSERT skeleton + 4 enum validator；W1-C M4 IMPL 是 caller，本身 0 dependency on M4 cron readiness ✅
- W1-C M4 = scaffold 階段（cron disabled）；ae9a2dd8 round 1 + 99709a2f round 2 雙 commit 已 closed E2 HIGH BLOCKER → W1-C 可進 E2 round 2 re-review ✅

**W1-C 與 V109 deploy 解耦**（per E2 §9.2）；V109 + W2-D 可進 atomic restart wave；M4 等 E2 round 2 + W2-D MIT cron wire-up 後接通 production cron。

## §12.3 W2-D dispatch deployment readiness

| Gate | Status |
|---|---|
| E1 IMPL DONE | ✅ a8d4bfa8 |
| E2 cold review APPROVE | ✅ d15cbe56 |
| E4 regression PASS | ✅ 本 report |
| Atomic restart deployment | ⏳ pending PM dispatch (操作 `helper_scripts/restart_all.sh --rebuild --keep-auth`) |
| Post-restart proc-exe alignment + sha256 verify | ⏳ pending |
| Post-restart strings grep `anomaly_event_writer\|m4_miner` hit | ⏳ pending |
| Post-restart PG anomaly_events INSERT smoke test | ⏳ pending |

## §12.4 1 cargo fail + 7 pytest fail Carry-over routing

| Fail | Routing | Severity |
|---|---|---|
| `layer_2_fence_archive_policy_diagnostic_only` (cargo) | PA Sprint 1B Earn Wave B 875de212 retrofit；E1 一行修 btc_lead_lag.rs:67-71 + E2 + E4 | MEDIUM (test contract drift, prod helper not synced) |
| 7 pytest structural drift | Sprint 2 contract sweep（per Sprint 1B-late E4 跟蹤；持續從 28 → 18 → 7 chip down） | LOW (0 runtime trading impact) |

# §13 對抗反問結果

1. **Q「Mac cargo workspace 4205 vs Sprint 5+ Wave 1 Phase D 4018 是 +187 但 attribution 完整嗎？」**
   - E4: W1-C 46 (m4_miner) + W2-D 14 (anomaly_event_writer) + W1-C-R2 19 (schema-grep helper_scripts) = 79；剩下 +108 是 sibling commit growth (Sprint 1B Earn Wave B 875de212 / Wave C bbb21c56 等)。逐個 commit 對 cargo test count delta unable to attribute without per-commit run；macro attribution acceptable。

2. **Q「strings grep 0 hit anomaly_event_writer 是 bug 嗎？」**
   - E4: 不是。release binary 19:06 build < W2-D 18:59 commit + W1-C-R2 19:10 commit，**還沒 rebuild**。Per task spec Step 5 明確標「本 step 是 baseline check 不是 deployment gate」。Production deploy 走 `--rebuild` atomic restart 後才會 bake。

3. **Q「1 cargo fail 確定 0 W2 attribution？」**
   - E4: `git show --stat ae9a2dd8 a8d4bfa8 99709a2f 16796d13 | grep btc_lead_lag` = 0 hit；`git diff 875de212~..875de212 -- rust/openclaw_engine/tests/btc_lead_lag_panel_fence_integration.rs` 確認該 test 是 875de212 (2026-05-23 Sprint 1B Earn Wave B) 改 + production helper btc_lead_lag.rs:67-71 未同步。100% sibling carry-over。

4. **Q「7 pytest fail 0 attributable to W2？」**
   - E4: 7 file list 全部結構性 W-AUDIT-7c carry-over；W2 4 commit 觸碰範圍 = helper_scripts/m4/ + rust/openclaw_core/m4_miner/ + rust/openclaw_engine/database/anomaly_event_writer.rs + sql/migrations/V109__*.sql；0 overlap with tests/structure/* tests/test_v072_*。

5. **Q「W1-C-R2 mid-flight commit 99709a2f land 過程是否破壞 E4 baseline 取樣？」**
   - E4: 不破壞。E4 取樣 HEAD 一致 follow origin/main，跨越 a8d4bfa8 (18:59) + ae9a2dd8 (18:03) + 99709a2f (19:10) 三 commit 為 baseline。本 E4 verdict 對齊最後 HEAD = 99709a2f；Run 2 + Run 3 在 post-R2 環境跑同綠（4205 / 1 / 6）= non-flaky verify。

6. **Q「V109 不在 _sqlx_migrations 是 sandbox vs production 差異嗎？」**
   - E4: 不是 sandbox。V106/V107/V112 同 pattern 已 land trading_ai production（per Sprint 1A-ζ memory），這些 schema 走 raw `psql -f` apply path 不經 sqlx_migrate；V109 同處理（per V109.sql 上游 16796d13 commit 設計）。**重要**：production 端 sqlx_migrations max=112 / count=102 不含 V109，但 anomaly_events 表已 land + 23 col + hypertable + 6 index + 2 policy 物理存在 — production 已 deploy。

7. **Q「W2-D writer 14/14 PASS 是否有 mock 業務邏輯？」**
   - E4 verify: anomaly_event_writer 14 test name list 全部是 schema-locked validator（4 enum + ADR-0036 黑名單 + 23 field + SQL string lock + amplification cap window）—  unit-level shape/semantic test。`insert_sql_locked_columns_match_v109_schema` + `anomaly_event_row_struct_has_23_fields` 是反向防護（schema drift detection）。0 mock 業務邏輯，0 mock IPC，0 mock PG（用 SQL string 對 V109 schema literal compare）。

8. **Q「W1-C M4 source loader SQL Mac empirical 仍然不 connect PG，Linux PG 真實 run 何時？」**
   - E4: 99709a2f commit body 標「Empirical Linux PG SQL verify (read-only): fills_loader.py SQL: 3 PEPEUSDT rows return + derived realized_net_bps, 0 ERROR; liquidations_loader.py SQL: 3 rows return, 0 ERROR」— E1 round 2 已 ssh trade-core 真實跑 SQL verify。本 E4 不重跑（避免增加 PG load + ssh round-trip）；採信 99709a2f commit body 證據。

---

E4 REGRESSION DONE: **PASS** · report path: /Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-25--w2e4_sprint_2_wave_2_regression.md
