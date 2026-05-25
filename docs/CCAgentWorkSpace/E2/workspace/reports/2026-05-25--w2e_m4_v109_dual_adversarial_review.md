---
report: W2-E E2 dual adversarial review — M4 IMPL (W1-C) + V109 schema (W1-F)
date: 2026-05-25
author: E2 (Senior Backend Reviewer + Adversarial Auditor)
phase: Sprint 2 v5.8 Stream B Wave 1 W2-E (E2 cold review)
parents:
  - W1-C M4 IMPL commit ae9a2dd8 (Rust 1511 + Python 1900 LOC)
  - W1-F V109 schema commit 16796d13 (V109__m8_anomaly_events_hypertable.sql 832 LOC)
  - W1-B M4 spec docs/execution_plan/2026-05-25--m4_pattern_miner_stage_1_algorithm_spec.md
  - W1-E V109 v2 amend docs/execution_plan/2026-05-25--v109_m8_anomaly_events_schema_spec_v2_amend.md
head_at_review: ae9a2dd8 (= origin/main)
verdict: RETURN-TO-E1 (M4) · APPROVE → E4 (V109)
---

# §1 Executive Summary

## §1.1 Verdict

**M4 IMPL (W1-C): RETURN-TO-E1** — 1 HIGH BLOCKER · 5 schema-incorrect column in 2 source loader file（runtime 必 RAISE EXCEPTION，掩蓋在 Mac mock dry-run 之下）+ 1 MEDIUM hygiene + 1 LOW production-path unwrap

**V109 schema (W1-F): APPROVE → E4 regression ready** — 23 col + 9 taxonomy + 4 severity + 5 engine_mode + Guard A/B/C 三重 ADR-0036 黑名單反向防護全到位；P0-1/P0-2/P0-3 三 BLOCKER 修對 + P1-5 metric_baseline column land。0 BLOCKER · 0 finding

兩者不耦合：V109 可獨立 E4 進度；M4 在 E1 修完 5 schema column 後重 E2。

## §1.2 Verification Empirical

| Check | 結果 |
|---|---|
| cargo test --release -p openclaw_core --lib round 1 | 416/0 PASS · m4_miner 46/0 |
| cargo test --release -p openclaw_core --lib round 2 (non-flaky) | 416/0 PASS · 一致 |
| pytest helper_scripts/m4/tests/ | 51/0 PASS in 0.03s |
| 5 invariant Rust grep (I-1/I-2/I-3/I-4/I-5) | 全 PASS · 0 violation |
| V109 grep (governance_audit_log/metric_baseline/engine_mode/severity/ADR-0036) | 全 PASS |
| Multi-session race 5a–5e | 全 PASS · HEAD = origin/main = ae9a2dd8 |
| Hard boundary 觸碰 (live_execution_allowed/authorization/system_mode) | 0 觸碰 |
| File size cap 800/2000 | 最大 m4 file 344 LOC (event_window.rs) / 677 (test) — 全在限內 |
| Cross-platform /home/ncyu / /Users/ hardcode | 0 hit |
| unsafe Rust 塊 | 0 hit |
| unwrap() in production path | 1 hit (tick_window.rs:64) — guarded by len-check 邏輯安全但仍 LOW |

# §2 M4 IMPL RETURN-TO-E1 — 5 schema-incorrect column (HIGH)

## §2.1 Finding

對抗反問「PA spec §1.2 +1.3 SQL 是否對齊 trading.fills + market.liquidations 真實 schema」 — empirical grep 5 column 不存在於目標表，runtime PG dry-run 必 100% RAISE。

### §2.1.1 helper_scripts/m4/sources/fills_loader.py (FILLS_QUERY_SQL line 28-45)

| M4 column | trading.fills 真實 | 證據 |
|---|---|---|
| `size` | **不存在** — 真實 column `qty` | V003 schema line 7: `qty REAL NOT NULL`；rust/openclaw_engine/src/database/trading_writer.rs:459 INSERT 用 `qty` |
| `close_fill` | **不存在** — production canonical pattern `WHERE entry_context_id IS NOT NULL` | program_code/ml_training/edge_label_backfill.py:417/513/624 全用 `entry_context_id IS NULL`（entry）/反義（close）。0 ADD COLUMN close_fill 在所有 V### migration |
| `realized_net_bps` | **不存在** | V061 `_jsonb_double_v061(sf.payload, 'realized_net_bps')` 是 replay payload JSONB key，非 trading.fills column；trading.fills 既有 `realized_pnl` (V003) |

### §2.1.2 helper_scripts/m4/sources/liquidations_loader.py (LIQUIDATIONS_QUERY_SQL line 23-39)

| M4 column | market.liquidations 真實 | 證據 |
|---|---|---|
| `liq.size` | **不存在** — 真實 column `qty` | V002 schema: `qty REAL NOT NULL` |
| `aggregator_type` | **完全不存在** — 0 V### migration ADD | grep `aggregator_type` in sql/migrations/ → 0 hit。SQL `WHERE aggregator_type IN ('top_liq_30s', 'cascade_5min')` 也會 RAISE |

## §2.2 為什麼測試沒抓到

51 pytest 全 PASS 是因為 **0 個 test 真正執行 `build_fills_query` / `build_liquidations_query`** —
- grep `build_fills_query|FILLS_QUERY_SQL|build_liquidations|build_funding` in test_m4_leakage_regression.py → **0 hit**
- 51 test cover：8 leak-free regression + 4 SQL/pandas regex + 4 Bonferroni + 6 cross-correlation + 9 event-window + 3 effect_size + 9 attribute enforcer + 3 source loader (但只測 engine_mode 白名單 + freshness + token_unlocks stub raise — **不測 SQL column 名**) + 7 writeback contract
- Mac `--dry-run` 路徑：`build_fills_query()` 返 SQL string 後**只 log 訊息**，不 execute；所以全程沒接觸 PG schema

**這正是 `feedback_v_migration_pg_dry_run` 2026-05-05 教訓的反例**：Mac mock pytest 不能 catch PG runtime semantic。E1 self-verify「cargo + pytest 全 PASS」**未對齊 production schema empirical 對齊**。

## §2.3 Severity 評估

**HIGH BLOCKER** 而非 CRITICAL — 因為：
- scaffold 階段 cron 默認 disabled（per W1-B spec §12）
- Mac dry-run 不 connect PG，5 column 不會立即觸發 production RAISE
- 但 **W2-D MIT 接 cron 第一次 production run 必 100% fail**，這違反 `feedback_v_migration_pg_dry_run` invariant — 修才能 W2-D 接通

**不算 LOW** — 因為 schema-incorrect column 在 SQL hard-code，非可放行 typo；違反 Sprint 2 dispatch 期 sub-agent IMPL 必驗 source query 對齊現實 PG schema 紅線（per `feedback_v_migration_pg_dry_run` SOP）。

## §2.4 退回 E1 修復清單

E1 必修並重 E2：

1. **fills_loader.py FILLS_QUERY_SQL**：
   - line 34 `size` → `qty`
   - line 38 `realized_net_bps` → 移除 column 或改用 `realized_pnl + ABS(price * qty) bps 計算` 或來自 V094 close_maker_audit hot column（依 PA W1-B §4 attribute mapping）
   - line 43 `close_fill = TRUE` → `entry_context_id IS NOT NULL`（per ML edge_label_backfill canonical pattern）

2. **liquidations_loader.py LIQUIDATIONS_QUERY_SQL**：
   - line 28 `liq.size` → `liq.qty`
   - line 30 + line 36 `aggregator_type` → 移除 column 與 WHERE filter；market.liquidations 純 raw event 表，cascade aggregation 需 caller-side 5-min ROLLUP（per W1-B spec §1.3 「5min window」原文 — 暗示在 caller 端聚合非 source 端 column）

3. **Source loader test 補強**（per `feedback_impl_done_adversarial_review` SOP）：
   - 加 test 驗 SQL string 含預期 column 名（用 grep / regex assertion）
   - 加 test 驗 SQL string 不含已知非法 column 名（黑名單）
   - 為避免重複 Linux PG empirical（Mac 跑不到），用 `SELECT 1 FROM information_schema.columns WHERE table_schema='trading' AND column_name='qty'` 模式列預期 column；schema-coupled regression

4. **W1-B M4 spec §1.2 / §1.3 self-doc 對齊**：spec 沒明確指 column 名 — E1 IMPL 自行猜 column 名是直接違反「PA spec § 編碼點」對應；E1 應請 PA / MIT amend spec § with empirical column 列表（per `feedback_v_migration_pg_dry_run` — 任何 PG-coupled spec land 前必先 empirical reflection）。

# §3 M4 IMPL 其他 finding (MEDIUM + LOW · 不阻 E4 但 follow-up)

## §3.1 MEDIUM-1: source loader test cover gap (per §2.2 同因)

51 test 對 source loader 只測 3 件：engine_mode 白名單 + freshness + token_unlocks stub raise；其他 source loader function（`build_kline_query` / `build_liquidations_query` / `build_funding_query`）完全 0 test。E1 修 §2 schema column 時必補 4 source loader 各 ≥ 1 schema-grep test。

## §3.2 LOW-1: tick_window.rs:64 `pop_front().unwrap()` production-path

```rust
if self.buffer.len() > self.capacity {
    let evicted = self.buffer.pop_front().unwrap();  // ← LOW
    ...
}
```

邏輯安全（上面 `len > capacity` 已驗 buffer 非空），但違反 E2 profile 「`unwrap()` 僅限不可恢復場景」guideline；應改：

```rust
if let Some(evicted) = self.buffer.pop_front() {
    kahan_add(&mut self.running_sum, &mut self.running_sum_c, -evicted);
    ...
}
```

非 BLOCKER；可延 §4 LOW carry-over。

# §4 V109 schema (W1-F) APPROVE 全項對齊 v2 amend spec

## §4.1 9 V109 對抗 grep 全 PASS

| Check | Verify | 結果 |
|---|---|---|
| Guard A `learning.governance_audit_log` 表名 | grep count = 6 (P0-1 修正) | ✅ |
| Guard A v_missing array 含 `metric_baseline` | grep count = 13 (P1-5 整體 land) | ✅ |
| engine_mode 5 值 (paper/demo/live_demo/live/replay) | line 423-430 + Guard C 重檢 | ✅ |
| severity 4 級 (INFO/WARN/CRITICAL/HALT) | line 370-376 + Guard C 重檢 | ✅ |
| 9 event_taxonomy | line 357-368 + Guard C 9-name 檢 | ✅ |
| 4 detection_method (atr_vol_funding_9cell/rv_percentile/block_bootstrap/manual_operator) | line 379-385 + Guard C 4-name 檢 | ✅ |
| Hypertable 7d chunk | line 449-454 + Guard C 604800 sec 驗 | ✅ |
| Compression 30d + Retention 180d + 4 partial index | line 506-573 + post Guard 完整 | ✅ |
| ADR-0036 黑名單 hmm/markov_switching/garch 反向 RAISE | Guard A x2 + Guard C 預檢 + Guard C 後驗 = 4 重；column name prefix/suffix 雙重；comment 1 處 | ✅ |
| Idempotent `CREATE TABLE IF NOT EXISTS` + `if_not_exists=>TRUE` + `CREATE INDEX IF NOT EXISTS` + 全 DO BLOCK 預檢 | line 76/353/447/509/525/561/564/568/572 | ✅ |
| 23 column post-Guard count check | line 638-642 `IF v_column_count <> 23` | ✅ |

## §4.2 V109 v2 amend 對齊度

- 3 P0 BLOCKER fix（P0-1 表名 + P0-2 4 severity + P0-3 5 engine_mode）全 land ✅
- 7 P1 reconcile（P1-1 9 taxonomy + P1-2 4 detection + P1-3 event_taxonomy 命名 + P1-4 observed_at 命名 + P1-5 metric_baseline + P1-6 不採 audit_chain_ref + P1-7 strategy_id 命名）全 land ✅
- 5 amend list（line 411-414 表名 / line 423-431 v_missing 加 metric_baseline / Guard C 不變 / §9.1 Query 3 表名 / §9.2 22→23）全 land ✅

## §4.3 7 AC（v2 amend §7）

| AC | 結果 |
|---|---|
| AC-S2-D-1 V109 schema land (Guard A/B/C + v2 amend) | ✅ in V109.sql |
| AC-S2-D-2 Idempotency 雙跑 0 RAISE | 由 Linux PG dry-run × 2 round 驗（E1 W1-F-retry 已完成 per task spec）|
| AC-S2-D-3 ADR-0036 黑名單 grep 0 hit production | grep `hmm/markov_switching/garch` 全部在 reject paths（Guard RAISE arm）— 雙重防護 ✅ |
| AC-S2-D-4 Hypertable 7d chunk + 4 partial index + 30d compression + 180d retention | ✅ DDL Step 2-5 land + post-Guard 4 索引 + 2 policy 驗 |
| AC-S2-D-5 Sprint 3 detector IMPL prerequisite ready | ✅ schema 上 column 全到位 |
| AC-S2-D-6 engine_mode 5 值 + training filter rule | ✅ 5 值齊全 + COMMENT line 606-609 標明 training filter 必 IN ('live','live_demo')  |
| AC-S2-D-7 23 column 含 metric_baseline | ✅ post-Guard line 638-642 count = 23 強制 |

## §4.4 V109 carry-over (LOW 不阻 E4)

- spec §8 hr re-estimate 「15-20 hr」與 commit body「832 LOC」對齊；無 carry-over
- 0 schema drift；0 P0/P1 residue

# §5 Hard Boundary 0 觸碰 (對抗反問)

| 紅線 | 結果 |
|---|---|
| `live_execution_allowed` / `authorization.json` / `system_mode` | grep M4 + V109 全部 0 觸碰 ✅ |
| 不創新 order 入口 / 不繞 Decision Lease | M4 `decision_lease_draft_id` 必 non-NULL 驗 line 121-127；不可空 ✅ |
| 不動 5-gate / 不寫 authorization.json | 0 觸碰 ✅ |
| GovernanceHub 走 lease_type='M4_DRAFT_WRITEBACK' + 5min TTL | line 182-183 PASS ✅ |
| `live_order_intent=FALSE`（M4 是學習 ≠ live order） | docstring line 11 + 178-179 顯式說明 ✅ |
| status_candidate 白名單 reject 'live'/'promoted'/'rejected' | Rust types.rs:194-201 + Python draft_writer.py:116-120 雙端 ✅ |
| auto-promote past 'preregistered' 被禁 | Rust + Python 雙端 reject + 6 unit test cover ✅ |

# §6 16 Root Principles compliance（per W1-B spec §11.6）

| # | 原則 | M4 對齊 |
|---|---|---|
| #1 Single controlled write entry | DRAFT writeback 走 GovernanceHub Lease + parametrized INSERT learning.hypotheses | ✅ |
| #3 AI output → Decision Lease | M4_DRAFT_WRITEBACK lease_type + decision_lease_draft_id non-NULL | ✅ |
| #6 Uncertainty → conservative | leakage_scan_pass DEFAULT FALSE fail-closed (V103 EXTEND) | ✅ |
| #7 Learning ≠ live | DRAFT 不 trigger live order；不 promote past 'preregistered'；Rust + Python 雙端 reject test | ✅ |
| #8 Trade reconstructable | Lease backref 100% non-NULL strict fail-loud | ✅ |
| #10 Fact/inference/assumption | scaffold 階段 placeholder vs production 真實 cron 明確標 | ✅ |
| #11 Agent autonomy within P0/P1 | M4 寫 DRAFT 但無 live order 寫權 | ✅ |
| #12 Evolve from evidence | 90d data 挖 alpha hypothesis evidence-driven | ✅ |

# §7 Multi-session race check (per CLAUDE 操作人格 + multi-session-race-SOP-1 Phase 2)

| Item | 結果 | 證據 |
|---|---|---|
| 5a fetch + 2h sibling window | ✅ | `git fetch --prune origin` 無新 commit；HEAD = origin/main = ae9a2dd8 |
| 5b status clean | ✅ | `git status --porcelain` 僅 1 unstaged (PA/memory.md — 隔壁 PA session WIP；非本 review scope) |
| 5c unknown WIP 禁 revert | ✅ | 0 revert / 0 checkout / 0 stash drop |
| 5d sign-off path clean | n/a | E2 不 commit |
| 5e sibling overlap | ✅ | HEAD = origin/main 同步；無新 sibling push 進 origin |

# §8 對抗反問結果

1. **Q: 「E1 self-verify 51 pytest + 416 cargo PASS — mock 了什麼？真實邏輯有跑嗎？」**
   - E2 catch: source loader SQL 完全 untested（test 0 hit `build_fills_query/build_liquidations_query`）；51 test 全在算法 / leakage / writeback contract / 邏輯 helper；source loader SQL string 是黑盒。5 schema-incorrect column 在 mock dry-run 全程不執行 SQL 因此漏抓。

2. **Q: 「PA spec §1.2/§1.3 column 對齊真實 PG schema 第幾行？」**
   - E2: W1-B spec § 對照表 line 158-163 寫「§1.2 trading.fills」「§1.3 liquidations self-fill filter 5s」但 **0 處列出 column 名**；E1 自行猜 column 名（size/close_fill/realized_net_bps/aggregator_type）違反 PA spec 編碼點唯一性。E1 應請 PA / MIT amend spec with empirical column 列表。

3. **Q: 「`unwrap()` in tick_window.rs:64 是 panic 在交易路徑？」**
   - E2: 不在交易 hot path（M4 是 learning path），但仍違反 unwrap()/expect() 僅限不可恢復場景的 profile guideline；改 `if let Some()` 是 LOW hygiene。

4. **Q: 「I-1 shift(1) 雙端是否真 leak-free？test fixture P1-11 F3 RETRACT 場景對抗 cover？」**
   - E2 verify: feature_engineering.rs:188-197 + cross_correlation.rs:213-222 雙重 verify `output[2] = mean(values[0..2])` 嚴格不含 current bar；rolling_pearson_corr line 112-113 `let xs = &x[i - window..i]` 強制 i 排除；test_m4_leakage_regression.py:test_shift1_rolling_mean_excludes_current_bar PASS ✅

5. **Q: 「Bonferroni K=2500 超過真實 hypothesis count K_hyp=500 × 5 forward = 2500 是否會過嚴致 0 promotion？」**
   - E2: spec §10 Open Q1 已 disclose；scaffold 階段 hard-code 2500 是 baseline，Sprint 3 cron 跑後收集 K_hyp empirical 後 PA + MIT + QC 三角仲裁。可接受 trade-off。

6. **Q: 「ADR-0036 黑名單 reverse grep 是否真的能 catch future ALTER 走後門？」**
   - E2 verify: V109 Guard A (line 117-157) + Guard C 預檢 (line 244-254) + Guard C 後驗 (line 695-702) 三重 RAISE arm — 任何 future migration ALTER table ADD CHECK constraint 含 hmm/markov/garch 都會被 V109 重跑時 catch；column name pattern 雙重 (Guard A line 142-157 + post line 808-822) — 結構性 enforcement，PASS ✅

7. **Q: 「engine_mode IN ('live','live_demo') 真的全程強制？V109 engine_mode 5 值含 paper — paper 不 leak 到 training？」**
   - E2 verify: V109 column comment line 606-609 顯式 「ML training filter 必 IN ('live','live_demo')」— schema-level 允許 5 值但 application-level filter 強制。對齊 CLAUDE.md §七 + `project_engine_mode_tag_live_demo`. Acceptable.

8. **Q: 「M4 / V109 兩 commit 是否 scope 互相 leak？」**
   - E2: V109 (16796d13) 純加 sql/migrations/V109__*.sql 1 file 832 LOC；M4 (ae9a2dd8) 純加 m4_miner + helper_scripts/m4/ + lib.rs register。0 overlap。可分別 E4 / RETURN E1。

# §9 結論

## §9.1 W2-E E2 dual verdict

- **M4 IMPL (W1-C) → RETURN-TO-E1**：1 HIGH BLOCKER (5 schema-incorrect column in 2 source loader) + 1 MEDIUM (source loader test cover gap) + 1 LOW (tick_window unwrap)。修完 §2.4 4 點重 E2。
- **V109 schema (W1-F) → APPROVE → E4 regression ready**：0 BLOCKER · 9/9 對抗 grep + 7/7 AC + Guard A/B/C 三重 ADR-0036 反向防護全完整。

## §9.2 Wave 2 E4 dispatch readiness

- **V109 可進 E4 regression**：W1-F retry sub-agent 已 Linux PG dry-run × 2 round 7/7 AC PASS（per task spec）。E4 regression scope = re-empirical idempotency + 4 index 存在 + 3 policy 存在 + post-Guard 預期 verdict 對齊。
- **M4 不可進 E4**：5 schema-incorrect column 未修 → W2-D MIT cron wire-up 必 production fail。E1 必先 round 2 修 → 重 E2 → E4 → 才可派 W2-D MIT 接 cron。

## §9.3 Carry-over (LOW NTH for Wave 2)

- `tick_window.rs:64 pop_front().unwrap()` 改 `if let Some(...)` 在 M4 round 2 fix 時順手清
- M4 4 source loader test 各加 ≥ 1 schema-coupled grep regression（per §3.1）
- V109 0 carry-over

---

E2 REVIEW DONE: M4 RETURN-TO-E1 (1 HIGH + 1 MEDIUM + 1 LOW) · V109 APPROVE → E4 · report path: /Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-25--w2e_m4_v109_dual_adversarial_review.md
