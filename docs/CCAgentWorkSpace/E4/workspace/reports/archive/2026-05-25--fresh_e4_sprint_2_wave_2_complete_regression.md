---
report: Fresh E4 Sprint 2 Wave 2 complete chain regression — W2-B + W2-F + W2-E-R2 + W1-C-R3 + PA velocity RCA
date: 2026-05-25
author: E4 (Test Engineer)
phase: Sprint 2 v5.8 Stream B Wave 2 closure — fresh full chain post W2-E4 fa466361
parents:
  - W2-E4 fa466361 baseline 2026-05-25 (cargo 4205/1/6 / pytest 6158/7/45)
  - W2-B 817de10a (funding_short_v2 + liquidation_cascade_fade Rust scaffold + Python harness)
  - W2-F fbfbd184 + b2febd43 (QA + FA audit + AC-19 cron + W1-C-R3 fix + PA velocity RCA)
  - W2-E-R2 aeb8a84b (E2 dual re-review M4 R2 + W2-B APPROVE)
  - PA velocity RCA d8311cf2
head_at_review: b2febd43 (= origin/main at E4 start; 3 post-commits a605af57/a120106f/e0c90ee3 are doc-only memory/report — 0 source diff in rust/ helper_scripts/ program_code/ — regression scope unaffected)
verdict: PASS — 0 W2-attribution new failure · 1 pre-existing layer_2_fence (Sprint 1B carry) · 7 pre-existing W-AUDIT-7c structural
---

# §1 TL;DR Verdict

**PASS** — 5 件 commit chain (W2-B 817de10a + W2-F fbfbd184/b2febd43 + W2-E-R2 aeb8a84b + PA velocity RCA d8311cf2) regress-clean。

- Mac cargo workspace 4300/1/6 雙跑同綠 vs fa466361 baseline 4205/1/6 = **+95 passed**（W2-B funding_short_v2 47 + liquidation_cascade_fade 48 完美對齊）。
- Mac pytest 6221/7/45 雙跑同綠 vs fa466361 baseline 6158/7/45 = **+63 passed**（W1-C-R3 M4 +19 schema-grep + AC-19 cron +44 ac19_alt_bucket_daily 完美對齊）。
- 1 cargo fail `layer_2_fence_archive_policy_diagnostic_only` 仍是 Sprint 1B Earn Wave B 875de212 (2026-05-23) scope leak（fa466361 baseline 已有；非 Wave 2 attribution）。
- 7 pytest fail 全 pre-existing W-AUDIT-7c / structural drift（fa466361 baseline 完全一致 fail set；非 Wave 2 attribution）。
- V109 PG state: 23 col / hypertable / 0 row（writer skeleton 未 wire detector，預期）。
- AC-19 crontab: 1 line installed 5/26 08:00 UTC + 7d alt/large_cap empirical 35/9/25.7% 與 6/4/66.7%。
- Hard boundary 0 觸碰；0 mock 滲透；0 cross-platform hardcode；0 unsafe block。

**Wave 3 sign-off readiness gate FULLY OPEN**：W3-A PA + MIT / W3-B QA 6/2 ALT verdict / W3-C TW + PM 可派發。

**Atomic deploy 建議**：W2 結構性改動（W2-B scaffold + V109 writer + AC-19 cron）**不阻 Wave 3 dispatch**；deploy 可 defer 至 Sprint 3 detector IMPL 接線後 (per W2-E-R2 verdict + PA velocity RCA confirming engine boot 12:37 UTC + close_maker_attempt 5/25 14:30 UTC post-deploy fire)。

---

# §2 Numbers Empirical

## §2.1 Mac cargo test --workspace --release 雙跑

| Run | Passed | Failed | Ignored | Non-flaky |
|---|---|---|---|---|
| Run 1 (no-fail-fast) | **4300** | **1** | **6** | ✅ |
| Run 2 (no-fail-fast) | **4300** | **1** | **6** | ✅ same |

Run 1 + Run 2 identical → **non-flaky** ✅

| Item | Current | Baseline (fa466361) | Delta | 解釋 |
|---|---|---|---|---|
| Cargo workspace passed | **4300** | 4205 | **+95** | W2-B funding_short_v2 47 + liquidation_cascade_fade 48 = 95 ✅ |
| Cargo workspace failed | **1** | 1 | 0 | layer_2_fence_archive_policy_diagnostic_only Sprint 1B carry |
| Cargo workspace ignored | **6** | 6 | 0 | 一致 |

Sole failure (pre-existing Sprint 1B carry):
```
test layer_2_fence_archive_policy_diagnostic_only ... FAILED
Layer 2 archive: OPENCLAW_ENABLE_PAPER=1 + paper-only must not spawn
```
attributed to Sprint 1B Earn Wave B 875de212 (2026-05-23) test rewrite without prod helper sync。fa466361 baseline 已含。0 W2 attribution。

## §2.2 Mac pytest 雙跑（--ignore tests/ml_training/test_pure_utils.py + tests/misc_tools/test_pure_utils.py）

| Run | Passed | Failed | Skipped | Subtests | Time | Non-flaky |
|---|---|---|---|---|---|---|
| Run 1 (--ignore both) | **6221** | **7** | **45** | 14 | 129.97s | ✅ |
| Run 2 (--ignore both) | **6221** | **7** | **45** | 14 | 129.36s | ✅ same fail set |

Run 1 + Run 2 fail set 完全一致 → **non-flaky** ✅ (diff /tmp/r1_fails.txt /tmp/r2_fails.txt = empty)

| Item | Current | Baseline (fa466361) | Delta | 解釋 |
|---|---|---|---|---|
| pytest passed | **6221** | 6158 | **+63** | M4 +19 schema-grep + AC-19 +44 = 63 ✅ |
| pytest failed | **7** | 7 | 0 | 7 pre-existing W-AUDIT-7c / structural; fa466361 同 set |
| pytest skipped | **45** | 45 | 0 | 一致 |

7 fail 完整 set（fa466361 baseline 完全一致；0 new attribution）:
1. tests/structure/test_confirm_modal_a11y_static.py::test_common_confirm_modal_has_dialog_a11y_and_focus_trap
2. tests/structure/test_docs_readme_index_static.py::test_archive_top_level_files_are_all_indexed
3. tests/structure/test_event_consumer_split_static.py::test_event_consumer_hot_files_stay_split_under_limit
4. tests/structure/test_prompt_modal_static.py::test_common_js_exposes_custom_prompt_modal
5. tests/structure/test_strategy_action_visual_isolation_static.py::test_common_css_defines_action_risk_zones
6. tests/structure/test_strategy_action_visual_isolation_static.py::test_live_stop_emergency_and_close_actions_are_visually_separated
7. tests/test_v072_feature_baseline_writer_static.py::test_writer_cli_defaults_to_dry_run_and_requires_apply_ack

---

# §3 Module Test Isolation Verify

## §3.1 V109 + V109 writer (W1-F + W2-D)

```
$ cargo test --release -p openclaw_engine --lib database::anomaly_event_writer
test result: ok. 14 passed; 0 failed; 0 ignored
```

14 test name 對齊 W2-D self-claim:
- test_validate_engine_mode_5_enum_complete
- test_validate_taxonomy_9_enum_pass_and_invalid_reject
- test_validate_severity_4_enum_and_invalid_reject
- test_validate_detection_method_4_enum_and_hmm_garch_reject (ADR-0036 黑名單)
- test_validator_contains_adr0036_blacklist_strings (schema-coupled)
- test_insert_sql_locked_table_name
- test_insert_sql_locked_columns_match_v109_schema (23 col lock)
- test_insert_sql_returns_id
- test_insert_sql_uses_numeric_cast
- test_anomaly_event_row_struct_has_23_fields
- test_error_display_messages_informative
- test_write_anomaly_event_minimal
- (+2 enum tests)

## §3.2 W2-B Rust strategies

```
$ cargo test --release -p openclaw_engine --lib strategies::funding_short_v2
test result: ok. 47 passed; 0 failed; 0 ignored

$ cargo test --release -p openclaw_engine --lib strategies::liquidation_cascade_fade
test result: ok. 48 passed; 0 failed; 0 ignored
```

47 funding_short_v2 + 48 liquidation_cascade_fade = **95 new W2-B tests** ✅ 完美對齊 cargo workspace +95 delta。

funding_short_v2 representative coverage:
- should_enter_reject_basis_at_entry_gate_boundary (邊界 gate)
- should_enter_reject_basis_too_wide
- should_enter_reject_funding_below_threshold
- should_enter_reject_negative_funding_hard_side_enforcement (硬方向)
- should_exit_basis_blowout
- should_exit_funding_collapse_below_exit_gate
- should_exit_funding_flip_to_negative
- should_exit_time_stop
- update_params_accepts_default_30pct
- update_params_rejects_funding_threshold_below_floor

liquidation_cascade_fade representative coverage:
- threshold_for_btc_is_500k (cohort BTC)
- threshold_for_eth_is_300k (cohort ETH)
- threshold_for_non_cohort_fallback_100k
- should_exit_reverse_cascade_long_to_short
- should_exit_take_profit_long / short
- should_exit_time_stop
- should_exit_zero_entry_price_fails_closed (fail-closed)
- update_params_rejects_non_cohort_symbol

## §3.3 W1-C-R3 M4 draft_writer schema-grep regression

```
$ python3 -m pytest helper_scripts/m4/tests/ -q
89 passed in 0.09s
```

89 = 70 base + 19 new schema-grep regression (W1-C-R3)。

## §3.4 AC-19 cron alt_bucket pytest

```
$ python3 -m pytest helper_scripts/cron/tests/test_ac19_alt_bucket_daily.py -q
44 passed in 0.05s
```

44 完美對齊預期 AC-19 cron suite。

---

# §4 Linux PG Empirical (Read-Only)

## §4.1 V109 hypertable state

```
SELECT COUNT(*) AS col FROM information_schema.columns
WHERE table_schema='learning' AND table_name='anomaly_events';
SELECT COUNT(*) AS row_count FROM learning.anomaly_events;
```

| Check | Expected | Actual | Verdict |
|---|---|---|---|
| col_count `learning.anomaly_events` | 23 | **23** | ✅ |
| row_count | 0 (scaffold; detector 未 wire) | **0** | ✅ |

## §4.2 AC-19 crontab installed

```
$ ssh trade-core "crontab -l | grep ac19_alt_bucket"
0 8 * * * OPENCLAW_BASE_DIR=$HOME/BybitOpenClaw/srv OPENCLAW_DATA_DIR=/tmp/openclaw $HOME/BybitOpenClaw/srv/helper_scripts/cron/ac19_alt_bucket_daily_cron.sh >>/tmp/openclaw/logs/ac19_alt_bucket_daily_cron.cron.log 2>&1
```

✅ 1 line installed 5/26 08:00 UTC。OPENCLAW_BASE_DIR + OPENCLAW_DATA_DIR env 注入 cross-platform safe (per H-2 / W1-C SOP)。

## §4.3 AC-19 cron empirical smoke (7d post-deploy alt vs large_cap)

```sql
WITH post_deploy AS (
  SELECT symbol, close_maker_attempt, close_maker_fallback_reason FROM trading.fills
  WHERE engine_mode='demo' AND ts > '2026-05-19 00:00:00' AND close_maker_attempt=true
)
SELECT 
  CASE WHEN symbol IN ('BTCUSDT','ETHUSDT') THEN 'large_cap' ELSE 'alt' END AS bucket,
  count(*) AS attempts, count(*) FILTER (WHERE close_maker_fallback_reason IS NULL) AS fills,
  ROUND(... * 100, 1) AS fill_rate_pct
FROM post_deploy GROUP BY 1 ORDER BY 1;
```

| Bucket | Attempts | Fills | Fill rate |
|---|---|---|---|
| alt | 35 | 9 | **25.7%** |
| large_cap | 6 | 4 | **66.7%** |

✅ 兩 bucket 數據實際存在；AC-19 query 邏輯 production-validated。alt fill_rate 偏低（25.7%）是 Stream E AC-19 stall RCA 焦點，由 cron 每日記錄趨勢監控。

## §4.4 _sqlx_migrations sanity

```
max_ver=112 / migration_count=102
```

對齊 TODO §0 2026-05-25 baseline。Sprint 1B Wave 2 land 後未新 migration apply（V109 已是 W1-F land Sprint 1A-ζ 系列）。

---

# §5 Binary Symbol Scan

## §5.1 Mac openclaw-engine binary (mtime 2026-05-25 21:45)

```
$ strings rust/target/release/openclaw-engine | grep -ciE "funding_short_v2"          → 5
$ strings rust/target/release/openclaw-engine | grep -ciE "liquidation_cascade_fade"  → 5
$ strings rust/target/release/openclaw-engine | grep -ciE "anomaly_event_writer"      → 0
$ strings rust/target/release/openclaw-engine | grep -ciE "m4_miner"                  → 0
$ strings rust/target/release/openclaw-engine | grep -ciE "alpha_tournament"          → 0
```

Mac dev binary 含 W2-B 兩 strategy Rust scaffold strings。

V109 writer / M4 / alpha_tournament 0 因：
- V109 writer 是 scaffold（未 wire production；W2-D self-claim 一致）
- M4 在 `openclaw_core` lib 但未 wire main binary 接線
- alpha_tournament 是 Python orchestrator (helper_scripts/alpha_tournament/) 不在 Rust binary

## §5.2 Linux openclaw-engine binary (mtime 2026-05-25 00:27)

```
$ ssh trade-core "strings .../openclaw-engine | grep -ciE 'funding_short_v2|liquidation_cascade_fade|anomaly_event_writer|m4_miner'"
0
```

Linux binary **pre-Wave 2** (built 2026-05-25 00:27 < W2-B 817de10a / W1-C-R3 99709a2f / W2-F b2febd43 all later 5/25)。0 W2-B/V109/M4 symbol — 一致。

**deploy timing decision**: per PA velocity RCA + W2-E-R2 verdict，**不阻當前 Wave 2 closure / Wave 3 dispatch**。Atomic restart 可 defer 至 Sprint 3 detector IMPL（M8 anomaly detector + W2-B detector wiring + M4 detector pipeline）合一接線後一次部署 — 避免 binary churn / per "atomic deploy" 政策。

## §5.3 Mock 滲透掃描

```
$ nm rust/target/release/openclaw-engine | grep -ciE "mock_instant|tokio::time::pause|spike"
0
```

✅ 0 mock symbol 滲透 release binary。

---

# §6 Hard Boundary + Cross-Platform + Unsafe Scan

## §6.1 Hard boundary (live_execution_allowed/system_mode/OPENCLAW_ALLOW_MAINNET/live_reserved/authorization.json)

```
$ git diff fa466361..b2febd43 -- rust/ helper_scripts/ | grep -cE "live_execution_allowed|system_mode|OPENCLAW_ALLOW_MAINNET|live_reserved|authorization\.json"
0
```

✅ Wave 2 diff 0 hard boundary 觸碰。

## §6.2 Cross-platform hardcode (/Users/ncyu | /home/ncyu)

```
$ grep -rE "/Users/ncyu|/home/ncyu" \
  rust/openclaw_engine/src/strategies/funding_short_v2 \
  rust/openclaw_engine/src/strategies/liquidation_cascade_fade \
  helper_scripts/m4 helper_scripts/m8 helper_scripts/alpha_tournament \
  helper_scripts/cron/ac19_alt_bucket_*
(no output)
```

✅ 0 hardcoded path 全 Wave 2 IMPL 範圍。AC-19 cron 使用 `OPENCLAW_BASE_DIR` + `OPENCLAW_DATA_DIR` env var 注入（per W1-C SOP）。

## §6.3 Unsafe block

```
$ grep -rn "unsafe\s*\{" \
  rust/openclaw_engine/src/strategies/funding_short_v2 \
  rust/openclaw_engine/src/strategies/liquidation_cascade_fade \
  rust/openclaw_core/src/m4_miner
(no output)
```

✅ 0 unsafe block in W2-B + M4 source。

---

# §7 Mock Audit (per Mock 安全規則)

Wave 2 改動 mock 範圍 review:

| 改動 | Mock 範圍 | OK? |
|---|---|---|
| W2-B funding_short_v2 tests.rs (649 LOC) | 純 unit test，computed_basis_proxy + time_in_position 真函數 | ✅ |
| W2-B liquidation_cascade_fade tests.rs | cohort threshold + state transition 真函數 | ✅ |
| V109 writer tests | schema validator 真函數，0 IPC mock | ✅ |
| AC-19 cron pytest (44) | 模擬 PG fills row 純 dict input → query function | ✅ stub IO only |
| M4 schema-grep regression (19) | grep source code 純 static check | ✅ no business mock |

✅ 0 業務邏輯 mock；mock 都只在 IO/static check 邊界。

---

# §8 Wave 3 Sign-off Readiness Verdict

| Wave 3 sub-component | Gate readiness | 阻塞? |
|---|---|---|
| W3-A PA + MIT (strategy_quality cross-tournament KPI) | ✅ FULL OPEN | W2-B Rust scaffold 完成；MIT spec readiness gate 開 |
| W3-B QA 6/2 ALT verdict (alt_bucket data RCA closure) | ✅ FULL OPEN | AC-19 cron deployed + 7d empirical 35/9/25.7% 數據 land |
| W3-C TW + PM (Wave 2 → Wave 3 transition docs) | ✅ FULL OPEN | 5 commit chain 全 doc-trace；Wave 2 sign-off chain 完整 |

**Wave 3 dispatch gate: FULL OPEN** ✅

---

# §9 Atomic Deploy 建議

**結論**：Wave 2 IMPL **不需立即** atomic deploy。

理由（per W2-E-R2 verdict + PA velocity RCA）:

1. **W2-B funding_short_v2 + liquidation_cascade_fade 是 Rust scaffold** — strategy registry 註冊 + params runtime config support，但 strategy_dispatcher 還未 wire upstream signal 接線。Live deploy 前需 Sprint 3 detector pipeline IMPL 才有效路徑。
2. **V109 writer (W2-D) 是 schema lock skeleton** — 14 cargo test 鎖住 23 col + SQL pattern，但 detector caller wiring 留 Sprint 3 M8 anomaly detector IMPL。Linux PG `learning.anomaly_events` 0 row 確認 (per §4.1)。
3. **AC-19 cron 已 production deploy** (per §4.2 crontab installed + §4.3 7d empirical 35/9 alt + 6/4 large_cap)。**已 production-live；不需 deploy 動作。**
4. **W1-C-R3 M4 draft_writer fix 是 schema-grep regression 加強** — 89 pytest PASS (70 base + 19 new) 鎖死 6 col schema drift。M4 runtime wiring 同 Sprint 3 待。
5. **PA velocity RCA confirmed**: engine boot 12:37 UTC + close_maker_attempt fire 14:30 UTC post-deploy = 之前的 deploy chain 已生效。Wave 2 增量不影響 runtime。

**建議**: atomic restart defer 至 Sprint 3 W3-A detector/wire-up IMPL + W3-B Wave 3 readiness sign-off 後合一部署。降低 binary churn 風險。

---

# §10 結論

**E4 REGRESSION DONE: PASS**

- 5 commit chain (817de10a / fbfbd184 / b2febd43 / aeb8a84b / d8311cf2) 全 W2 attribution 0 new failure
- Mac cargo workspace 4300/1/6 雙跑 non-flaky (+95 vs baseline = W2-B 47+48)
- Mac pytest 6221/7/45 雙跑 non-flaky (+63 vs baseline = M4 19 + AC-19 44)
- 5 module isolation verify 全 PASS (V109 writer 14 / W2-B funding 47 / W2-B liquidation 48 / M4 89 / AC-19 44)
- V109 PG state 23col/0row + AC-19 crontab installed + 7d alt 25.7% / large_cap 66.7% empirical confirmed
- 0 mock 滲透 / 0 hard boundary / 0 cross-platform / 0 unsafe
- Wave 3 dispatch gate FULLY OPEN
- Atomic deploy defer 至 Sprint 3 detector wire-up（per W2-E-R2 + PA velocity RCA）

**No retreat to E1 needed.**
