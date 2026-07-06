# MIT Memory

> 本檔=長期教訓+近期記錄；超 300 行由 R4 巡檢標記、PM 派工壓實，舊條目原文遷 memory-archive.md（append-only）；agent 完成序列照常追加於檔尾。

## 長期教訓

- V### migration 凡涉 PG reflection / CHECK / UDF / TimescaleDB 介面，必經 Linux PG empirical dry-run double-apply；Mac mock pytest / 靜態 parse 抓不到 runtime semantics（V055/V083/V084/V104/V114/V115/V125 反覆驗證）；`timescaledb_information.*` view 欄位名版本特定，Guard 凡 SELECT 其欄位必實機跑。
- Idempotency gold standard = 第二次 apply 全 NOTICE-skip、0 RAISE；CHECK constraint / REVOKE 用 boundary INSERT 與權限實測 enforce，比靜態 SQL parse 強得多。
- TimescaleDB compressed twin（_compressed_hypertable_NN）跨 run 持久：compression + column-level GRANT 的 migration，GRANT 必包 nested `EXCEPTION WHEN undefined_column` 才可 re-apply 冪等（V114 reference pattern）；migration 內 explicit COMMIT 之後的 guard 失敗 = DDL 已落地 + sqlx 不註冊 → engine 啟動 crash-loop。
- sqlx checksum 紀律：手動 psql -f apply 不入 `_sqlx_migrations`；migration file land 後再 edit 必跑 `bin/repair_migration_checksum`；「dry-run sign-off 報告」不證明 migration 真檔存在——簽核前必驗 file on disk + `git log -S`（V104 幻覺事件教訓）。
- commit ≠ runtime live：commit message 常把 source-only（cron 未 install / flag-off / dormant writer）誤導為 IMPL；審計必區分 schema-side land 與 runtime-side active，用 PG row 增量 / crontab / process 實證。
- 對抗性證偽手法：per-symbol 重算對賬 aggregate、晚上市 symbol 跨表交叉驗（最難偽造的真實性指紋）、親跑 NULL INSERT 驗 runtime reject、親跑 dry-run 重現 EXIT 0、讀 artifact mtime/size 證進程真活——不信 pgrep 與口頭聲稱。
- 任何 blocked-signal / counterfactual edge 主張必先 side-adjusted market-beta 分解，只 demeaned residual 算 alpha；fixed-horizon close-to-close 對方向性策略必混入 beta；對稱鏡像測試（long/short 同窗翻號）是廉價有力的 beta 偵測法。
- 顯著性紀律：overlapping forward returns 用 HAC Newey-West（lag=k-1）；cross-sectional 同窗相關需 cluster-robust SE / block bootstrap（naive iid t 高估 3-5×）；多重檢定必 Bonferroni / DSR deflation；孤立單尺度顯著 + 相鄰尺度無 coherence = 雜訊非信號。
- Leakage 紀律：rolling 特徵必 shift(1)；walk-forward 必 purge + embargo 且 duration-aware（以 exit_ts 而非 entry_ts purge，embargo ≥ max holding period）；PIT survivorship 用 listed_at/delisted_at lifecycle 而非今日 survivors；name_pattern_check 不可作 leak-free 證據（必要非充分），真證據 = shift1_compliance / is_oos_gap 類 typed producer。
- PG jsonb round-trip 會把 -0.0 → 0.0（IEEE sign bit 丟失）破 canonical hash：hash 前必 normalize zeros，且 pre/post-jsonb 用同一 chokepoint 計算；此類 drift 只在真 PG round-trip 上顯形，Mac pytest 全綠不代表安全。
- ML maturity 用 Foundation/Skeleton/Shadow/Canary/Production 評級，防「表存在 = pipeline live」假象；0 row + 0 producer = dead；evidence_source_tier 必驗（synthetic_replay 不可餵 ML）。
- `/proc/PID/exe` 的 sha256 是 binary content hash 不是 git commit，勿對其跑 git ancestry；真 build commit 須另查。
- non-interactive SSH 無 DATABASE_URL：psql 須 source engine env 或 `docker exec printenv POSTGRES_PASSWORD` 建 DSN；SSH 長輸出 redirect /tmp 分次讀（憑記憶報數字危險）；psql 2>/dev/null 吞 SQL error 須交叉檢核。
- 負向 Guard test 若 mutate prod prereq 表，必包 SAVEPOINT + `\set ON_ERROR_STOP on`（BEGIN/ROLLBACK 不夠——無 ON_ERROR_STOP 時 DDL 可在 RAISE 前落地）；sandbox DB 用 `TEMPLATE template0` 避 collation mismatch。
- panel.* / market.* 共享市場數據表 by design 無 engine_mode / IPC slot（engine_mode 規範只管 learning/training 表）；klines backfill 用 `ON CONFLICT DO NOTHING` 冪等 gap-fill，但 retention policy 會 silent reap 超窗資料——backfill 前必驗 retention 視窗。
- spec ≠ runtime reality（NAS 未掛載、cron 未裝、表體積暴增）：audit 必 empirical 查 mount / crontab / pg_size，不可信 spec 描述。
- 新 migration / 被動等待必附 healthcheck（CLAUDE.md §七）；silent-dead 指紋 = 24h 0 增量但設計期望 ≥1 fire。
- LLM 永不驗 alpha：alpha 證據 math-primary；LLM screen 只做 advisory，recall-floor fail-closed（低 recall → DISABLE，全進確定性 gate，subtraction-only 不丟 alpha）。

## 近期記錄

## 2026-06-07 HIGH-1 PIT leak re-audit on f8a6cfc5 (residual hidden-OOS bridge) — leak CLOSED, PASS to E4

**Trigger**: E1 follow-up commit f8a6cfc5 (parent ae6fec2a) on /private/tmp/wt-residual-p2 branch feature/residual-hidden-oos-wiring, fixing MIT HIGH-1 (boundary-trip PIT leak at the COMPUTATION not just the label). Parent agent asked to re-run MIT's own reproduction, not trust the report.

**Verdict: leak CLOSED, PASS to E4** (with 1 test-hygiene NON-BLOCKING flake flagged + Linux/PART-3 owed items reconfirmed).

**What I reproduced (own scripts, not E1's t13)**:
1. RAW evaluate_cell probe (no filter), MIT's exact case (oos_start=100*BUCKET+5000, non-aligned; boundary trip exit in [bucket_floor(oos_start),oos_start) net_bps=123456): leak REPRODUCED — aligned_observations 10->11, eval_observations 3->4 (confirms original HIGH-1 was real).
2. Through bridge step-4b _bucket_admissible filter: leak CLOSED — boundary trip DROPPED (trips 10->10), aligned_obs 10->10, eval_obs 3->3 STABLE with-vs-without.
3. Full-bridge sealed-hash probe (real register_experiment, captured persisted manifest): sealed demo_residual_alpha_report_hash byte-identical 44316c38... with vs without boundary trip; candidate_window_end=288000 (bucket 19 end) <= oos_start 1445000.
4. Focus #2 (klines open-time-clamp 2nd-order): straddle bar (open<oos_start, close>=oos_start) passes load_btc_klines open-time clamp but bar-level _bucket_admissible(ts)=False -> dropped before bucketed_btc_factor. CLOSED.
5. Focus #3 (window fidelity): sealed candidate_window_end == max aligned bucket end residual actually fit on (288000), straddle bucket 100 end (1454400) NOT used. One-source-of-truth CLOSED.
6. Mutation M1 (remove step-4b DATA filter, KEEP step-6 backstop): t13 STILL FAILS -> proves step-6 label filter alone is insufficient; the fix MUST be at DATA layer before evaluate_cell (exactly my original HIGH-1 diagnosis). evaluate_cell line 125-126 confirmed to re-bucket INDEPENDENTLY via bucket_round_trips_by_exit + bucketed_btc_factor.

**Source-level confirmations**: bucket_floor = math.floor(ts/bs)*bs (idempotent on grid keys -> step-6 backstop byte-equiv to old MED-2 filter, as E1 claimed). Step-4b filters BOTH rts_non_oos (by exit_ts) AND btc_klines (by ts) BEFORE evaluate_cell (line 291). Only REMOVED code line = the step-6 aligned filter, replaced by byte-equivalent _bucket_admissible call. Everything else additive. Carve-out / beta-train-only / OOS-never-fit / n_trials / train-eval split UNCHANGED -> prior PASS items unaffected.

**MED-2 doc-gap**: CLOSED. sealer build_hidden_oos_state docstring + bridge step-3b comment both now state embargo_seconds = INTERNAL train->eval purge (from (eb+0.5)*bucket_sec), NOT candidate->OOS boundary embargo; OOS validity rests on strict exit<oos_start carve-out + straddle DATA filter. PART-3 promotion-time purge band [oos_start-embargo, oos_start) note added, marked OUT OF PART-2 scope.

**Tests**: bridge+sealer 28 passed (stable x5, matches E1). Full ml_training 585 passed / 31 skipped (stable x4; skip count matches E1's 31). t12b (4h-bucket eb=0 fail-closed) present + passes.

**NON-BLOCKING flake found (test hygiene, NOT a code defect)**: my hand-assembled 4-file subset (bridge+sealer+cycle+producer_db) intermittently failed t13/t11b with the LEAKED hash cd55472f... (boundary trip present) under DEFAULT (unpinned) PYTHONHASHSEED during a window of __pycache__ churn from my own mutate-then-git-restore cycles. Caught ONCE with full traceback (hash_with=cd55472f = the exact mutation-signature E1 documented). BUT: never reproduces in isolation, with any fixed PYTHONHASHSEED (scanned 0-7, 11-43, 100-160 all pass), with -X dev, with PYTHONDONTWRITEBYTECODE=1+fresh pycache (0/30), or in the natural full-suite run (585 passed x4). Root = stale-bytecode/mtime read artifact from MY file churn, not E1's committed code. Flag to E1/E2 as a recommend-add (deterministic test isolation / drop the .pyc-sensitive cross-file coupling) but it does NOT block E4 — E1's committed code is correct; the in-process evaluate_cell instrumentation showed 0 leaks reaching evaluate_cell across 12 clean runs.

**Worktree hygiene finding (NOT mine)**: residual_hidden_oos_bridge.py in the worktree had a PRE-EXISTING leftover E2-mutation (evaluate_cell(rts_all,...) + bucket_round_trips_by_exit(rts_all) "E2-MUTATION dual-site") dirty in the tree before I started. Per CLAUDE.md git rule I did not blow it away; I restored ONLY to the committed f8a6cfc5 blob (git checkout f8a6cfc5 -- <file>) to verify against committed truth. All 3 E1-touched files now match committed f8a6cfc5. E2 should clean up its leftover mutation.

**Linux / PART-3 owed (reconfirmed, out of Mac scope)**:
- Real V132 CHECK constraint empirical dry-run on Linux PG (windows_chk / embargo_seconds>0 / source+tier allowlist) — Mac mock cannot verify PG reflection semantics (CLAUDE.md V055 mandate).
- Real klines / real round_trips end-to-end on Linux (this audit used synthetic 4h bars + synthetic trips; producer load_btc_klines / load_round_trips against live PG not exercised).
- Future PART-3 promotion-time OOS-OPEN purge band [oos_start-embargo, oos_start) for post-oos_start trips (correctly deferred by E1, doc-noted).

**Report**: returned directly as final message (no .md per instruction).

## 2026-06-08 Residual PART 4 Phase 2 (Gap A orchestrator + Gap D) — methodology + Linux-empirical audit

**Commits**: `2a5df09e` + `7d2cdcba` on `feature/residual-activation` (worktree `/private/tmp/wt-residual-act`). Verdict: **RETURN-to-E1** (1 HIGH correctness bug + 1 HIGH latent prod-breaker; methodology otherwise sound).

**★ #1 PG jsonb round-trip — EMPIRICALLY RESOLVED on real PG (trading_postgres, trading_ai)**:
- Feared `1.0→1` / trailing-zero / sci-notation normalization: **DID NOT happen** on this PG. `1.0` stays `1.0`, `1e-12`→`0.000000000001`, `0.9500000000000001` byte-identical, ints/None/nested all survive. PATH A (`json.dumps(sort_keys=True)::jsonb`, the orchestrator `_STAMP_REC_SQL`) and PATH B (psycopg2 `Json`) produce the SAME read-back hash → **A_vs_B_match=TRUE** (manifest vs payload consistent).
- **BUT the ONLY drift is `-0.0 → 0.0`** (jsonb drops the IEEE-754 sign bit on negative zero). Reproduced the **asymmetric cross-check break** end-to-end: `registry_hash` is computed PRE-jsonb on the in-memory dict (bridge:355 `residual_hash=_canonical_sha256(report)`, stored as a TEXT manifest field), while source_contract recomputes `expected_hash` POST-jsonb on the payload read-back → if any field is `-0.0`, `MATCH=false → INVALID → deciding-factor breaks`.
- **Reachability is REAL not hypothetical**: `residual_alpha_gate.py:292` `residual_mean_bps=_to_bps(float(np.mean(residual_eval)))` and `:342` `beta_loadings[f]=float(beta[idx])` have NO `-0.0` normalization; `_to_bps` does `value*10000.0` (`-0.0*10000=-0.0`, sign preserved). Empirically `round(-1e-20,6)→-0.0`, `-1.0*0.0→-0.0`, `np.array([-0.0])[0]→-0.0`. Worst: correlated with the **defer/weak-alpha cohort** (degenerate near-zero residuals/betas) — exactly where the gate matters. Fix options: normalize `-0.0→0.0` (add `x+0.0` or `x if x else 0.0`) on BOTH sides before hashing, OR store report as text not jsonb, OR canonicalize-then-store. **HIGH, RETURN-to-E1.**

**#2 net_side — HIGH BUG (the false-promote vector the feature claims to close)**:
- `derive_net_side_from_fills(fills, strategy_name)` + `load_candidate_net_side(conn, strategy, ...)` filter ONLY by `name==strategy_name`; `_FILLS_QUERY` (realized_edge_stats.py:234) has **NO symbol filter**. So for candidate `family_id=grid_trading::BTCUSDT` it computes net signed-qty of grid_trading **across ALL symbols**, not the candidate (strategy,symbol). **Empirically**: grid_trading is net-short strategy-wide (−1.0M of 4.0M gross, 60d) but per-symbol RAVEUSDT/PENGUUSDT are net-LONG (+1) → a `grid_trading::RAVEUSDT` candidate gets `net_side=-1` while true exposure is `+1` → **wrong funding sign AMPLIFIES carry** = the exact MIT-hard-condition false-promote. **Fix: thread `symbol` into the fills query + derivation.** Currently masked by: triple-OFF + single-config PBO-defer (a wrong-sign defer can't false-promote since it's already rejected) — but bites the moment a multi-config candidate (which CAN pass) runs. **HIGH, RETURN-to-E1.**
- The entry-fill **double-filter** (`name==strategy_name` AND `realized_pnl==0`) IS correct: empirically 347 `realized_pnl=0` rows carry close-prefix names (excluded by name check) and 1476 `realized_pnl!=0` non-prefixed rows exist (excluded by realized check). `trading.fills` schema matches (side text Buy/Sell, qty/realized_pnl real). MED note: `sign(net qty)` for a ~25%-net grid strategy is a weak/flip-prone direction (treats 25%-net as full ±1).

**#3 multi-factor PIT/survivorship — CORRECT (real schema verified)**:
- `pit_active_symbols`: `listed_at<=entry_ts AND (delisted_at is None OR delisted_at>exit_ts)` = survivorship-correct (includes delisted-active-at-bucket, excludes today-only). `market.symbol_universe_snapshots` empirically **948 symbols, 296 with delisted_at populated** (delisted symbols present). Lifecycle query (MIN listed_at + DISTINCT ON latest delisted_at) correct.
- `market.funding_rates`: cols `ts/symbol/funding_rate` (NO `funding_time`; code comment already notes `ts` IS settlement time). BTCUSDT cadence **8.63h** (≈8h Bybit). PIT (`ts<=bucket_end`) correct.

**#4 Gap D selection-bias — CORRECT**: validator enforces V3 §8.3: K≥10 / oos≥0.20 / cv∈{walk_forward,cscv,purged_kfold} / embargo≥7d, all fail-closed. **embargo_days=7 (meta-selection provenance floor) vs sealed embargo_seconds~0.25d (intra-fit train→eval purge) are correctly DIFFERENT concepts** — E1 deviation #2 justified (using 0.25d for selection-block would trip EMBARGO_TOO_LOW; using 7d for intra-fit purge would discard training data).

**#5 deciding-factor — CORRECT (single-config INVALID-reject is right, NOT PENDING)**: post-HIGH-1-fix, source_contract first gate reads payload report → `validate_demo_residual_alpha_report(defer_report)` → `(False, passes_not_true)` → `INVALID`. PENDING_SCHEMA is reserved for schema/lineage plumbing gaps (missing tier/experiment_id/manifest_hash); a substantive math defer is NOT plumbing → INVALID is correct. Gate genuinely active on beta-masquerade (reads `passes`), correctly no-false-promote. LOW NOTE: defer_data and real block both surface as `passes_not_true`/INVALID (indistinguishable at source-contract output; but orchestrator reason + drar verdict preserve `defer_data` for triage).

**#6 leak/no-false-promote — CLEAN**: `ResidualEdgeReport` carries ONLY scalar metrics (means/betas/Sharpe/coverage/verdict/perm) — NO raw OOS return series → payload write re-introduces no data. hidden-OOS hold-out enforced upstream in bridge `partition_round_trips_by_oos`. `_intercept_bps` diagnostic-only NOT subtracted from OOS residual (correct anti-leakage). `idempotency_key=family_id+split_hash` (split definition, not data). Triple-OFF empirically real: prod state **0 stamped recs / 0 drar rows / flags unset in env** (gate genuinely inactive on deploy).

**Linux-owed for operator activation run (do NOT do — deferred decision)**: the flag-ON real-write (set `OPENCLAW_RESIDUAL_STAGE0R_PREFLIGHT=1` + `OPENCLAW_RESIDUAL_ALPHA_PRODUCER=1`, run on a real candidate) — must wait until #1 (-0.0) + #2 (per-symbol net_side) are fixed, else first real candidate with a `-0.0` metric OR a sign-divergent symbol breaks the cross-check / amplifies carry.

**Report**: returned inline to PA (no separate report file per task instruction).

## 2026-06-08 Residual PART 4 Phase 2 HIGH-1/HIGH-2 re-verify on REAL PG → PASS-to-E4

**Trigger**: E1 follow-up commit `67730b7b` (parent `7d2cdcba`, branch `feature/residual-activation`, worktree `/private/tmp/wt-residual-act`) claims fix for my 2 pre-activation HIGH blockers. Re-confirm empirically on real PG (read-mostly / temp+ROLLBACK only; orchestrator NOT activated).

**Real PG**: trade-core docker `trading_postgres` (Up 10d), PG 16.11, role `trading_admin`, db `trading_ai`. Consumer parses jsonb via psycopg2 default adapter / `json.loads` (returns Python **float**, NOT Decimal — verified no Decimal adapter anywhere in source_row read path) → my `json.loads` round-trip proxy is faithful.

**HIGH-1 (`-0.0` jsonb drift) — CONFIRMED FIXED on real PG**:
- Real PG empirically strips `-0.0`→`0.0` (`{"a":-0.0}::jsonb` reads back `{"a":0.0}`); `1.5`/`12.0`/`0.3` preserved. Confirms the bug premise.
- Built EXACT breaking case via REAL `to_dict()`: `residual_mean_bps=-0.0` + `beta_loadings.btc=-0.0`. Pre-jsonb registry hash (`_canonical_sha256`, bridge:355) == post-jsonb source-contract recompute (`:399 _canonical_sha256(dict(residual_report))`) byte-identical: `227516dc...` == `227516dc...` **YES**. Also for the real single_config_defer cohort dict (with cycle-layer `pbo_status` injection): `76ec2f41...` == `76ec2f41...` **YES**.
- Negative control (raw `-0.0`, NO `_normalize_zeros`): pre `f288d893...` ≠ post `227516dc...` → DRIFT. The unnormalized hash drifts INTO the normalized hash after PG strips `-0.0` → strongest proof fix is precisely what closes `residual_alpha_report_hash_mismatch`.
- **Other jsonb drift re-scan**: `-0.0` is the ONLY value-changing drift reachable in a real report. Edge scan on real PG: `1e-12`/`-1e-12` (PG re-renders text but psycopg2 float-parse symmetric → hash-safe), int64 max (preserved), high-prec float (preserved), trailing zeros (1.50→1.5 both sides). FOUND one *additional* PG drift class: large-magnitude float `1.23e20`→integer-numeric `123000000000000000000` (PG canonicalizes fractionless float to int form → asymmetric json.dumps). **BUT not reachable**: all report numeric fields are bps-scale / [0,1] stats / O(10) regression coeffs / small-int coverage — none reach ~1e16+. Flag as documented non-applicable edge, NOT blocker. Recursive `_normalize_zeros` covers nested dict+list (`{"a":{"b":[-0.0,...,{"c":-0.0}]}}` all →0.0 verified).
- **Single chokepoint confirmed**: `register_residual_candidate_experiment` (bridge:164, "only write entry") computes ONE `residual_hash=_canonical_sha256(report)` from ONE `to_dict()`-normalized dict; all 3 derive from it — registry hash (355), drar/durable `build_hidden_oos_state(residual_report_hash=residual_hash)` (366), payload-embed `RESIDUAL_ALPHA_REPORT_FIELD: report` (378). `report=result.report` (303) chains to producer `report_dict=report.to_dict()` (producer:167) via `evaluate_cell`→`CellResidualResult.report` (cycle:222, `dict(result.report)` shallow copy + string `pbo_status`, no float reintroduction). One normalization covers all.

**HIGH-2 (per-symbol net_side) — CONFIRMED FIXED**:
- Direct empirical `derive_net_side_from_fills`: RAVEUSDT divergence (grid_trading strategy-wide net SHORT via BTCUSDT heavy Sell; per-symbol RAVEUSDT net LONG). strategy-wide (symbol=None) → **-1** (existing caller preserved). per-symbol RAVEUSDT → **+1** (reverses strategy-wide). RAVEUSDT==+1 **YES**.
- Ambiguous fail-close: no-fills-for-symbol → `ambiguous=1.0` (orchestrator skips); net-0 → `ambiguous=1.0`. Both fail-closed (the default +1 in ambiguous return is never consumed — preflight:419 gates on `ambiguous>=1.0`).
- Caller chain: ONLY prod caller of `derive_net_side_from_fills` = `load_candidate_net_side` (893, threads symbol); ONLY caller of that = orchestrator preflight:417 `symbol=symbol` where `symbol=rec.get("symbol")` (candidate's own symbol, fail-close if empty). New `symbol=None` default → strategy-wide byte-identical for any omitting caller. `_FILLS_QUERY` already returns `f.symbol` (line 237) → Python-side filter, NO query shape change, no impact on `load_round_trips`.

**Mutation bite (both have teeth)**: bypass `_normalize_zeros` → 2 HIGH-1 tests RED; neutralize symbol filter → 3 HIGH-2 tests RED (`assert -1 == 1`). Files restored pristine (git diff empty).

**No regression / behavior-neutral**: full `ml_training + learning_engine` = **855 passed / 31 skipped** (matches commit claim, 0 regression). Triple-OFF empirical: `residual_producer_enabled()`=False default; prod PG `hidden_oos_state_registry` total=0, sealed=0, `replay.experiments` w/ residual manifest=0; engine env `OPENCLAW_RESIDUAL_ALPHA_PRODUCER` NOT SET. Orchestrator inert.

**VERDICT: PASS-to-E4** (clears P2 to E4 regression). Worktree left pristine (ahead 5/behind 2, only pre-existing E2/PA doc changes — not mine); all PG work temp+ROLLBACK, 0 leaked rows/tables.

**Linux-owed for operator's deferred activation run** (NOT my fix scope; pre-existing residual-producer remaining work): (1) `signal_spec` producer (validator/pass-through only, no constructor); (2) `hidden_oos` sealer real activation (currently 0 state='sealed'); (3) mlde hook `attach_residual_reports` 0 caller; (4) **branch ahead 5/behind 2 origin/main — needs rebase + push + Linux `--rebuild` deploy before flag-on**; (5) activation = set `OPENCLAW_RESIDUAL_ALPHA_PRODUCER=1` + restart, then verify first sealed row carries normalized `to_dict()` (no `-0.0` round-trip mismatch) + per-symbol net_side on a real multi-config candidate; (6) fills.side semantic on real Linux fills (Mac used synthetic); (7) sqlx checksum drift check per V028-V034 SOP if any new migration involved on restart.

**Lesson reinforced**: Mac pytest passed all 5 new tests, but the load-bearing proof (PG actually strips `-0.0` → unnormalized hash drifts INTO normalized hash) only materializes on real PG round-trip — exactly why this re-verify was warranted. Negative-control drifting to the same hash as the fix output is the cleanest possible bite signal.

**Report**: returned directly to PM (no separate file per task instruction).

## 2026-06-09 L2 Phase 3a ml_advisory (diagnose_leak + interpret_result) MIT named sign-off (M3 leak + M4 recall)

**Report**: `workspace/reports/2026-06-09--l2_p3a_ml_advisory_m3_m4_signoff.md`

**Scope**: E1 P3a impl audit (branch feature/l2-critic-lessons-tools @ 6a9dd0f1, P3a uncommitted) — `l2_ml_advisory_executor.py`(39KB new) + `l2_out_of_bound_guard.py`(M3/regime clauses) + `l2_prompt_contract_registry.py`(2 contracts) + orchestrator dispatch_and_execute wiring + test_l2_p3a_ml_advisory.py. **MIT-named gates: M3 (leak typing) + M4 (Ollama recall).**

**Verdict: MIT APPROVE-CONDITIONAL (M3+M4 sign-off GRANTED; 1 HIGH Linux-owed + 1 MED sink-semantic must be acknowledged before sink-write trusted)**

**M3 typing 誠實 = YES (核心問題答案)**: guard clause B 經 AST-extracted 純函數實證 12 不變式全綠：
- B.1 source_class 缺/非法 → reject；B.2 name_pattern_check 宣稱 leak_free=true OR pit_verified=true → reject（核心鐵律）；正例 npc 不宣稱 leak-free → pass；shift1_compliance/is_oos_gap leak-free → pass（producer 不存在但 typing 合法，P3b-owned）。
- `leakage_check.py` 親驗 78 行純 name-pattern/prefix（0 shift1、0 PIT temporal gap）→ M3「name_pattern_check 必要非充分」論點 grounded。
- ML_ADVISORY_LEAKFREE_SOURCE_CLASSES = frozenset{shift1_compliance, is_oos_gap}（name_pattern_check 正確排除）。
- **P3a 不假裝有 leak-free 證據**：diagnose contract template 硬約束「MUST NOT claim leak-free PIT backed only by name_pattern_check」+ guard typing 強制。誠實。

**M4 recall 機制 sound = YES (含 benchmark schema + fail-safe 方向)**: load_ollama_screen_calibration 經隔離 exec 實證 7 分支全綠：
- 無 artifact / malformed / recall 缺欄 / 非數值 recall / recall<floor → 全 DISABLED（fail-closed 方向正確：screen 不可信→全進 gate，非全放）；邊界 recall==0.85 → ENABLED（floor 是 >=）。
- recall≥0.85「loose」定義對（screen 偏向 pass，precision 由 gate 兜底，defense-in-depth）。disable-on-low-recall fail-safe 方向對（全進確定性 gate）。placeholder=DISABLED 正確保守起步。
- benchmark schema 建議（MIT-owned）：held-out good (歷史 demo-confirmed discoveries + 正確 post-hoc diagnoses) / bad (agent.lessons V133 dead-modes)；artifact {benchmark_version, recall, precision, threshold, n_good, n_bad, measured_at, classifier_version}；建議加 precision + per-class recall（good/bad 分層）+ confusion matrix counts。

**★ Sink ML-適切性 (MIT #1 決策點) — 2 findings**:
- **HIGH (Linux-owed, Mac-RCA 盲點)**: V037 REVOKE PUBLIC INSERT 已在 migration tree（V036-V040，branch V134+）。executor 做 **direct INSERT INTO mlde_shadow_recommendations**（executor:428），是唯一 direct-INSERT producer——既有 mlde_shadow_advisor:470 + opportunity_tracker:329 **全走 verify_replay_evidence_and_insert()**。若 V037 applied 且 control_api login role 無 replay_writer_role GRANT → P3a direct INSERT **runtime fail-closed（silent，因 fail-soft → ok=False/errors=[insert_failed]，advisory 靜默丟）**。Mac mocked conn 看不到。必 Linux 驗 GRANT 狀態。
- **MED (sink-semantic overload)**: sink 落 `(source='ml_shadow', recommendation_type='regret_summary')` 與兩既有 producer 碰撞。`mlde_demo_applier` 是 active demo RiskConfig mutation consumer，掃 regret_summary 建 risk_patch。protective barrier = `COALESCE(confidence,0.0) >= min_confidence`（NULL→0.0 < 0.35 default）**是 config-dependent soft barrier 非 by-design**（若 MIN_CONFIDENCE=0.0 則 P3a row 被 fetch；二道兜底 = payload 無 net_regret_direction → 空 patch no-op）。且 Block A filter `COALESCE(evidence_source_tier,'real_outcome')=ANY(allowlist)`：P3a 無 tier → 被當 real_outcome **不被濾掉**。
- **建議（給 PM/operator 拍）**: 選項 (a) 換 sink 到 agent.lessons / 專屬 diagnostic 表（最乾淨，脫離 alpha-evidence applier 命名空間）；(b) 保持但加 discriminator-aware consumer 防護（mlde_demo_applier WHERE 加 `AND created_by NOT LIKE 'ml_advisory%'` 或 `AND source <> ...`）；(c) V137 加 source='ml_diagnostic' + recommendation_type='diagnostic'/'interpretation' enum（脫離 ml_shadow/regret_summary 重載）。MIT 傾向 (a) 或 (c)——diagnostic 非 model recommendation，語義上不該與 applier-feed evidence 同表。

**cascade ML 正確性 = PASS**: LLM 永不驗 alpha（executor 0 個 dsr_gate/pbo_gate/beta_neutral import，grep 驗）；P3a 無 alpha gate（斷言無 alpha 正確）；guard 0 model call（確定性，grep 驗）；cost only on survivors（screen reject → 0 cloud，mutation-bite 測驗）；interpret 對 bull-only 強制 regime_caveat（clause C 實證）；cost 經 record_claude_cost 計入 DOC-08（screen+cloud 兩次 distinct token 非 double-count）。

**diagnose 本身無 look-ahead = PASS**: context 是 caller-supplied post-training metrics/leakage_findings/drift_signals（純事後讀，executor 不 fetch 未來資料）；diagnose 讀訓練「結果」做事後診斷，無未來資訊穿越。fact_inf_assm 正確分離（diagnose: evidence_kinds+suspected_cause；interpret: confidence+has_regime_caveat）。

**測試**: 41 test 全面（2 模式 + cascade survivors-only+mutation-bite + M4 4 分支+mutation-bite + M3 typing + regime + sink zero-exec + grep iron-rules + dispatch reachability + DoS）。**Mac 無法跑全 suite**（py3.10 缺 tomllib / py3.12 缺 pydantic+pytest；環境非 defect）→ **E4-Linux owed**。MIT 用 AST-extract 純函數隔離實證 M3(12)+M4(7) 不變式全綠補強。

**Migration**: P3 ZERO migration 正確（sink V031 / D3 V134-135 / novelty V133 / TOML registry 全 existing）——除非 sink fix 選 (c) 才需 V137。

**教訓**: PA design 的 direct-INSERT 決策（避 verify_replay_evidence_and_insert 的 replay 語義）未 reconcile V037 REVOKE——design-time grep 漏查 grant surface。再次命中「Mac 靜態看 INSERT 成功、Linux runtime permission 才見真」盲點。

## 2026-06-09 L2 P3b leak-producers + M4 benchmark spec + V127 population (MIT design/spec)

**Report**: `workspace/reports/2026-06-09--l2-p3b-leak-producers-m4-benchmark-spec.md`

**Trigger**: P3b (hypothesize→promotion, alpha-bearing) 須真 leak-free PIT 證據（非 name_pattern_check）+ down-market regime data。MIT 產 producer design + M4 benchmark schema/set + V127 population 規範（read-mostly，不寫業務碼）。

**核心 Linux runtime 發現（ssh trade-core docker exec PG live 2026-06-09，sqlx_max=133）**:
1. **V127 `research.aeg_regime_labels` = 0 row**（population 完全沒做；schema applied 但 runner `--write-db` 從沒跑）— 確認 PA owed-verify。`aeg_regime_transitions` = 0。
2. **`agent.lessons` = 0 row**（M4 bad-set + novelty dedupe 來源全空）— L2 session 從沒 persist lesson。
3. **BTC 1d klines = 730 row / span 729d（2024-06-02 → 2026-06-01）** — B1 BTC factor + down-market sub-sample 資料充足 READY。
4. **`model_registry` = 3 row**（M4 good-set 來源薄但非零）；`mlde_shadow_recommendations` = 20313 row（sink active，呼應 P3a S-2）。
5. **BTC down-market bar 實證（leak-free prior-only `ROWS BETWEEN 30 PRECEDING AND 1 PRECEDING`）**：309/730 down-bars（42%）；7d<-5%=123，30d-dd>8%=285；**last 90d 只有 23 down-bars < B1 ≥30 門檻** → B1 down-market sub-sample 必用全 2-year span（或 ≥180d），90d 窗會 DEFER。

**Producer design（reuse 重大發現）**:
- **`shift1_compliance` 不需 greenfield** — `helper_scripts/m4/feature_engineering_validator.py` 已有完整 shift(1) 機械：`is_leaky_sql`/`is_leakfree_sql`（`ROWS...CURRENT ROW`=leak vs `AND 1 PRECEDING`=leak-free）+ `is_leaky_pandas`（`.rolling(N)` 無 `.shift(1)`）+ **`validate_shift1_pattern`（empirical leak-vs-clean correlation divergence，對齊 Rust m4_miner::feature_engineering::validate_leak_free_pattern）** + pure-Python ref impl。shift1_compliance producer = 薄 wrapper 把這些 emit 成 typed `source_class=shift1_compliance` evidence row（pass/fail + leak_corr/clean_corr/diff/leak_suspected）。
- **`is_oos_gap` 須建**（leak-typing 版）— `sample_weight_sensitivity.py:329` 的 is_oos_gap 是 namesake-different（train-vs-OOS RMSE gap-ratio overfit detector，非 temporal gap）。新 producer 驗 train/test split 真有時序 embargo gap（max(train.ts) + embargo ≤ min(test.ts)）+ purge（label window 不跨界）+ 回 {has_temporal_gap, embargo_bars, purge_applied, leak_free:bool}。
- 兩 producer 餵 M3 leak-free 集合 `{shift1_compliance, is_oos_gap}`（registry `:164`），P3a guard 已 enforce typing（reject leak_free claim backed only by name_pattern_check）。

**M4 benchmark schema finalize**: `{benchmark_version, classifier_version(pin screen prompt/model), measured_at, recall, precision, n_good, n_bad, per_class_recall{good_recall,bad_reject_rate}, confusion{tp,fn,fp,tn}, recall_floor=0.85, threshold}`。存 artifact JSON（mirror FND-2 CSV-artifact pattern，避免 migration）+ log D3 gate-seam。good set = model_registry promoted（3 現有）+ 5 down-beta-masquerade NO-GO post-hoc-correct diagnoses；bad set = `agent.lessons` V133 dead-modes（**現 0 row，須先 seed**）。

**V127 population 規範**: runner classifier.py 已 leak-free PIT（`prior=close_arr[:i]` line 130 + `feature_ts=ts_arr[i-1]` line 131 = shift(1)）；data_loader.py 已 leak-free（`history_start=window_start-lookback_days` + `closed_bar_cutoff` filter，line 63/78；V127 §F 註解的 "data_loader.py:300 vol-tercile leak" 指 **ML training data_loader 非此 aeg runner**，aeg runner data_loader 乾淨）。population = operator/E1 跑 `harness.py --write-db --fnd2-run-dir <universe> --window-start 2024-06-02 --window-end 2026-06-01 --cutoff <closed>`（lookback 430d 已含）。down-market mask 從 ret_30d/ret_90d + 7d return（market.klines 直接算）derive，與 B1 def 對齊。

**殘留須 operator/QC 拍板**:
- QC: B1 down-market sub-sample window（**90d 不夠，須 ≥180d 或全 span**，實證 last-90d 僅 23 down-bars）；altcap basket construction（仍 0 producer，P3b 最大 gap）。
- operator: V127 population 跑 `--write-db`（B1 down-regime 軸 unblock）；agent.lessons seed（M4 bad-set + novelty）。
- MIT-owned build: shift1_compliance（reuse validator）+ is_oos_gap（新）producers；M4 benchmark artifact build。

**邊界**: design/spec only；不寫 producer code（E1 build）；不改 V127/leakage_check；read-only ssh probe（5 query）；不 install cron / 不 write-db / 不 restart。P3b sign-off 時 MIT 驗 leak coverage + M4 recall。

## 2026-06-09 L2 P3b leak producers + altcap PIT + M4 — M3+M4 sign-off (APPROVE)

**Report**: returned to PM inline (no separate file; per agent contract).
**Branch**: feature/l2-critic-lessons-tools @ aeae4da4 (P3b uncommitted; verdict pre-commit gate).

**Verdict: MIT M3+M4 APPROVE (sign-off).** All 4 review axes pass; 46/46 tests green Mac (pure-compute producers real, math gate real, engine mocked).

**Key determinations (each verified against actual E1 build, not spec)**:
1. **shift1_compliance reuse CORRECT** — thin adapter genuinely calls feature_engineering_validator (is_leaky_sql/is_leakfree_sql/is_leaky_pandas/validate_shift1_pattern); NO new leak algorithm, NO re-derivation. source_class="shift1_compliance"; fail-closed (any DEFER/empty-set → leak_free=False). Static-layer optional (compute_exprs may be absent) — empirical layer always runs.
2. **is_oos_gap build CORRECT** — distinct fn check_oos_gap (dodges sample_weight_sensitivity:329 RMSE-gap namesake, keeps source_class string). 4 checks per time-series-cv §2: temporal-separation + embargo + purge(label_end>=min_test) + no-shuffle (both non-monotonic AND interleaved). Tests have bite (each violation → leak_free=False). source_class="is_oos_gap".
3. **★ altcap PIT walk-forward LEAK-FREE (M3 hot-spot) — CONFIRMED no look-ahead.** _is_alive(alive_from≤bar≤alive_to) reads FND-2 builder Step F effective-lifetime clip (alive_from=max(eff_listed,ws), alive_to=min(eff_delisted,we)) — clipped from symbol's OWN listed/delisted dates (lifecycle authority), NOT today's survivors. unknown_lifetime → excluded NOT coalesced to snapshot-ts. current_survivor_only_comparison is a COLUMN not a filter (full universe includes delisted). No zombie forward-fill (two-real-close guard, c_t/c_prev both required). test_pit_walk_forward_entry_and_exit proves ARB leaves after alive_to=06-04, APT enters at alive_from=06-05. This is the alt-beta leak命門 and it holds.
4. **M3 typing integration HONEST** — _run_leak_stage requires shift1_compliance_leak_free OR is_oos_gap_leak_free True; name_pattern_check structurally NOT a gate input (cannot satisfy precondition). 3-state correct (True→pass, False→fail, None→DEFER no-producer). guard clause B.2 rejects leak-free claim backed only by name_pattern_check. Registry ML_ADVISORY_LEAKFREE_SOURCE_CLASSES={shift1,is_oos} excludes name_pattern_check. Never claims name_pattern=leak-free.
5. **M4 recall mechanism SOUND** — load_ollama_screen_calibration fail-closed to DISABLED on: missing/malformed artifact, recall<floor, recall missing, bad_reject_rate<=0 (degenerate pass-everything). disable-on-low-recall = subtraction-only (all→gate, loses no alpha, flags MIT). recall floor 0.85 (artifact-overridable). benchmark schema (n_good/n_bad/recall/precision/per_class_recall/confusion/classifier_version) matches my spec §2.1. gate-seam logs "disabled" as verdict=pass+applied_as=screen_disabled (correct: screen bypassed not killed).

**Masquerade defense (the 5-candidate killer) VERIFIED**: beta_neutral_check dual-factor forced (altcap None→DEFER, never BTC-only pseudo-neutral); β_upper=|β|+1.96·SE≥0.20→fail (SE-kill of noisy-small-β = THE dimension that killed 5 candidates); down-mask leak-free prior-only (peak[i-30:i] excludes i, close[i-7] prior, absolute scalar not full-sample percentile). HAC (Newey-West) on DW<1.5. test_hypothesize_b1_fail (cand=0.8·btc in down-market) → math gate FAIL, no sink, no cloud. PBO single-config → honest-DEFER (no fabricated peers,承 Gap-A).

**Owed (does NOT block M3+M4 sign-off; blocks live hypothesize verdict)**:
- V127 population (0 rows) — operator/E1 `--write-db`; B1 binary down-mask uses Path B klines-direct so NOT hard-blocked.
- agent.lessons seed (0 rows) — M4 bad-set + novelty source empty; seed 5-10 dead-modes via persist_lessons.
- **Producer→context assembly seam**: build_altcap_returns/compute_down_market_mask/check_shift1/check_oos_gap have NO live caller packing math_gate_inputs for a real training-completion hypothesize trigger (orchestrator passes context through but no trigger assembles it). Expected per design line 327 (hypothesize gated on QC B1 ratification + altcap + V127). Producers correct; wiring downstream of QC.
- Altcap cap-weighted basket: equal-weight shipped (operator-locked, 0 free param); full FND-2 expansion post-launch. QC-owned B1 four numbers + down-window (≥180d, runtime: last-90d=23<30) still QC sign-off.
- Linux E4 smoke (24-symbol × real market.klines altcap; PG-real) owed.

**Minor honest flag (non-blocking)**: validate_shift1_pattern empirical check correlates only the LAST window-slice (feature_values[n-window:n]) vs shift(1) slice — a single-window spot-check, not full-series rolling leak scan. Adequate as adversarial screen + paired with static SQL/pandas structural net + the by-construction leak-free klines path; deeper full-series empirical scan is a future enhancement, not a P3b blocker (the structural+empirical+test triangulation covers the realistic leak vectors).

## 2026-06-10 — P4 online-FDR M1+M2 final ratification

7 項=6 APPROVE/APPROVE-with-NOTE + 1 MODIFY（#3 debit 須含「dsr stage 渲染 pass/fail 即扣」，否則 single-config PBO honest-DEFER 下可無限免費 re-look DSR，破 E[V]≤Σα_i 前提 (c)；math gate 實作五 stage 全跑無 short-circuit、docstring :1003 誤述）。#2 拍板 **Option B**（Option A 斷帳本-水準恆等=無 FDR 保證，拒背書）。自含 bound：per-family mFDR ≤ 0.1·α_target（10x margin）、全域 ≤ α_target 需 **N_fam ≤ 1/γ=10**（cardinality healthcheck 閾值）。α_i ≤ 5e-4 恆成立 ⇒ cap=0.005 vacuous（defense-in-depth）+ threshold ≥ 0.9995 ⇒ 初期 discovery≈0 是設計後果（healthcheck 監測 conducted>0 非 discoveries>0）。NOTE：V137 CHECK 三值邏輯洞（NULL n_eff 過 CHECK）MED-HIGH、refund×debit_failed 無互斥、orphan refund wealth-inflation 向量、debit_id 決定性未規範、pre_reg_id 無 FK。E1-READY=YES+1 binding 條件。報告：workspace/reports/2026-06-10--l2-p4-m1-m2-final-ratification.md

**2026-06-10 FIX-3.1 補充裁決 ACK-with-條件**：skip 謂詞邊界=value-invariance（存在性/計數/日曆 span 可；任何 returns/price 值的函數不可）；親驗 beta_neutral_check.py:245 down-span 是 BTC value-derived 須替換「candidate history span<180d」；#3 debit 規則不變，skip=不渲染不付費，conditional-on-conducting level 經 (N,K)-cell 論證+零 discovery 面雙保險成立。詳見 ratification 報告 §5a。

## 2026-06-11 L2 記憶層（V139/manual V140/memory_distiller）ratify — RATIFY-WITH-CONDITIONS
- Schema 本體 PASS（Guard A/B/C 忠實 V133 範式、plain-table 驗算成立、supersede 單向轉移+CHECK=精確 PIT 重建可行：`created_at<=t AND (active OR updated_at>t)`，set_embedding 不 bump updated_at 是 load-bearing 不變式）。4 binding 條件：E4 scratch 須 prod 同 locale en_US.utf8；prod apply 顯式連帶 V138（sqlx head=137 親驗）+ checksum drift 預檢；backfill flag-ON 前修 F-1（OllamaEmbeddingClient 全 repo 零非測試構造點→整條 embedding 軸含 [89] 不可達，flag 名存實亡）；B3 replay 必 PIT 過濾。
- [PROD empirical] en_US.utf8 下 pg_trgm 真產 Han trigram（CJK 補位成立），但短中文 hint×長混排 content similarity=0.092<0.1 門檻=實測漏召回 → hint 式召回應改 word_similarity；'simple' FTS 對中文僅命中標點切出的整 clause token（'beta 中性化' query miss 親證）。教訓：locale 相依的檢索行為（trgm KEEPONLYALNUM 走 lc_ctype）必在 prod locale 上 empirical，scratch 建庫 locale 不對齊=驗證失真。
- 188/188 測試 Mac 親跑過；報告 `workspace/reports/2026-06-11--l2_memory_schema_ratify.md`（已複製 Operator/）。

## 2026-06-13 Probe-stage 盈利證據取數（read-only Linux runtime，trading_postgres）

**核心結論：全系統實現 edge 普遍負，cost_gate 拒單為真負非誤殺；當前窗為 DOWN regime（BTC 81052→63946，-21%/30d），任何正面結果必標 regime-bet。**

- **fills 真活**：demo 4763 + live_demo 3700（all-time）；近 7d demo 182 + live_demo 48；近 24h demo 28（latest ~20min）/ live_demo 2（latest ~21h，重度 gated）。engine 真執行決策。'live' 0 row（全 demo/live_demo）。
- **系統自評 edge（learning.edge_estimate_snapshots，109331 rows，fresh→now）每一個真實策略 cell 都負 bps**：demo bb_reversion -9.6 / grid -13.0 / ma_crossover -13.5 / funding_arb -24.4；live_demo ma_crossover -6.3 / grid -7.6 / bb_reversion -6.9。**0 個 validation_passed cell**（全系統）。僅極小樣本正 cell：grid LTCUSDT n=7 +18.3 / APTUSDT n=3 / AVAX n=4 / BCH n=5 = 全 n<10 = 噪音非 alpha。
- **cost_gate 反事實=真負非誤殺**：近 7d demo 拒 942360 / approve 233（99.97%）、live_demo 拒 12714 / approve 62。所有拒單 reason 皆 `cost_gate(JS-demo): estimated=-Xbps<0`（負 JS-shrunk 估計）；**rejected_with_positive_estimate=0**（親跑 regex 證 0 false-kill）。非 cost_gate 拒單僅 position_count/duplicate 合法風控。坐實 memory project_2026_06_01 fail-closed-gate root-cause。
- **成本牆坐實**：maker fee 0.02%（RT ~4bps）/ taker fee 0.055%+slippage 1.5bps（RT ~14bps）；cost_gate 負估計 -5~-25bps = gross edge 低於 RT 成本。
- **ML pipeline 成熟度**：exit_features 3275 rows（demo2026+live_demo1192+paper57，fresh，9 chunks）；model_registry 僅 3 row 全 grid_trading q10/q50/q90、verdict=shadow_only/canary=shadow/**0 promoted**/train_date 2026-04-23 stale 7週/sample600=**Shadow stage 永不影響 live**。decision_shadow_exits 0 chunk（Foundation）。
- **alpha 主路全空**：listing_capture_events **0**（listing fade 主路零捕捉）、pre_registered_hypotheses **0**、demo_residual_alpha_reports **0**、hidden_oos_state_registry **0**（residual producer ACHIEVED-but-INERT 不變）。aeg_regime_labels 7696（V127 population 已做，較 06-09 的 0 進展）。agent.lessons 6。
- **死管道**：market.regime_snapshots / regime_transitions = 0 chunk（呼應 TODO A1A2BA4 row：regime_snapshots 0 producer 死管道）。
- 報告：returned inline to PM（無獨立 .md per task instruction）。

## 2026-06-13 盈利研判（守+攻，read-only Linux runtime trading_postgres，~20:00Z）

**守（leak/frozen/unrealized 歸因，全 runtime 親證）**：
- **edge fresh 親算**（learning.edge_estimate_snapshots payload key=shrunk_bps/combined_ev_bps，7d，read 20:02Z）：每個真實策略 cell 全負 + **0 validation_passed**。demo bb_reversion shrunk -8.43/ev -15.18、grid -6.62/-7.72、ma_crossover -8.24/-10.25；live_demo bb_reversion -3.87/-11.83、grid -4.75/-8.05、ma_crossover -4.87/-4.89。combined_ev_bps（含成本）比 shrunk 更負 = 坐實成本牆。
- **exit-policy leak 量化**（trading.fills exit_reason 30d demo）：DYNAMIC STOP 群 systematically 大負（每筆 -2~-6.3），TRAILING STOP 群正（+1.3~+8.1）。唯一有量的正貢獻=grid_close_short n=163 avg+0.28（DOWN regime down-beta，非 alpha）。phys_lock_gate4_giveback n=42 +0.13。
- **entry 無 alpha 指紋**（trading.decision_outcomes 30d，n=940559 demo / 653441 live_demo）：MFE avg +0.044 / MAE avg -0.040（近對稱=無入場擇時）；outcome_1h≈0.0001、outcome_24h≈0.0007（forward drift≈0）。
- **side-mirror beta 測**（fills 30d）：demo Buy n=238 avg+0.21 / Sell n=78 avg-0.086（3:1 skew 偏 Buy + 正集中在 close-short/Buy 側 = down-beta 指紋）；live_demo Buy/Sell 全負平（重度 gated）。
- **live_demo 30d 實現 PnL≈ -2.01**（exit_source(none) 295 筆）。taker slippage live_demo **+5.2bps 逆向** vs demo -2.07（favorable）= live_demo 執行更差。
- **frozen ML**：model_registry=3 row 全 grid_trading shadow_only/canary=shadow/train_date 2026-04-23（停 7+週）/never promoted/sample600（<LightGBM-typical 10k）= Shadow stage 永不影響 live。exit_features 3275 fresh（demo2026/live_demo1192/paper57）但無 consumer 接 live decision。decision_shadow_exits=0（Foundation）。

**攻（dead 數據軸 + 範式天花板）**：
- **alpha 主路全 0**：listing_capture_events=0、pre_registered_hypotheses=0、demo_residual_alpha_reports=0、hidden_oos_state_registry=0（residual ACHIEVED-but-INERT）。
- **★ NEW 發現**：research.alpha_long_short_ratio_history=**0**（TODO 稱 funding/OI backfill done，但 LSR 軸實為 0 row）；alpha_funding_hist=46539 / alpha_oi_hist=348153 已填但**僅當旁證、無 alpha producer 消費**。
- **死管道**：market.regime_snapshots/transitions/funding_rates/open_interest/long_short_ratio/news_signals 全 0（market.* 是 0-producer 死表，alpha 軸全靠 research.alpha_* + aeg_regime_labels 7696）。
- 範式天花板論點：6 週 5 候選全死於 down-beta-masquerade + 成本牆（11-27bps RT）；OHLCV+技術指標在 demo 帳號 1m 級 + taker 成本下無 net edge。未碰數據軸：on-chain、Polymarket/Kalshi 事件機率、option flow、微結構（orderbook depth，現 Gate-B 僅 publicTrade prints）。

**證據紀律**：全 read-only ssh + PG SELECT，0 mutation。DOWN regime（BTC -21%/30d）→ 任何正 cell 標 regime-bet。報告 inline 回 PM（無獨立 .md，per task instruction）。

## 2026-06-14 另類數據軸離線就緒度審計（為 leak-free IC 螢幕備）— read-only Linux runtime trading_postgres + /tmp/openclaw artifact

**三軸就緒度判定（全 read-only ssh + PG SELECT + artifact stat，0 mutation；sqlx head=139）**：

- **polymarket（artifact-only，PIT-clean）= TESTABLE-but-THIN**：daily cron 活（heartbeat 06-13 04:41 fire），但 **僅 2 個 snapshot run dir**（daily-20260612T090806Z=6100 rows / daily-20260613T030115Z=8371 rows，append-only run dir）。tracked_markets.json=8405 markets（5772 tracking / 2633 resolved，全 2633 帶 resolution_outcome_prices=H4 calibration 樣本就緒）。PIT 極乾淨：每 sweep **單一 snapshot_ts_utc**（run2=2026-06-13T02:41:01Z）+ 完整欄位（outcome_prices/volume24hr/liquidity/oneDayPriceChange/end_date/closed/uma_resolution_status）+ collector_git_sha。8265/8371 rows 帶 outcome_prices，2277 btc/eth-keyword。**致命限制：只 2 天時序面板**→ 跨時序 IC（H1 lead-lag）不可測（需 hourly lane，現 commented-disabled）；H4 calibration（resolved vs odds，cross-section）可立即跑（n=2633 resolved 足）。hourly-topn 必須 operator 活化才有 horizon<1d 樣本。

- **carry_crowding（market.* live hypertable）= TESTABLE**：4 表全 live timescale hypertable + Rust market_writer.rs WS-fed + fresh to now：funding_rates 2914 rows/25 sym/8h settlement cadence（min 2026-04-05 max 06-13）；open_interest **245125 rows/25 sym/5min cadence**（fresh 00:45）；long_short_ratio 20773/25 sym/1h cadence（fresh 00:00）；liquidations 263420/84 sym/per-event tick。30d 樣本：funding 171 settlements×25、LSR 16525、OI ~密。**消費者真存在**：m4 funding_loader/liquidations_loader + residual_alpha_producer_db SELECT FROM 這些表。**★ PIT caveat（HIGH for IC）**：market.* 只有 event `ts` 欄無 fetched_at/ingest_ts → WS-ingest 落地 lag 不可從表內直接觀測，PIT 對齊須靠 WS 架構假設（funding settlement 整點已知=PIT-safe；OI/LSR 5min/1h as-of 須以 ts<=decision_t join 且不可假設 0 lag）。**research.alpha_funding_rates_history（46539）+ alpha_open_interest_history（348153）= 2-year backfill（2024-06→2026-06）但 n_runs=1 / fetched 2026-06-03 一次性 / 無增量 producer 消費=旁證庫非活軸**。

- **liq_cascade = TESTABLE（軸內最成熟）**：market.liquidations 263420 events/84 sym，事件密度 5785-10167/day（DOWN regime 放大）。30d 5min-bucket：**212 buckets≥1M USD / 41 buckets≥5M cascade threshold（W1-B spec）/ max bucket 50.3M USD**。cascade detector（event_window.detect_liquidation_cascade_events，5M threshold）**leak-free by construction**：pre window 排除 event_t、post 從 event_t+1 起、N≥30 硬 gate（對齊 Rust m4_miner）。self-fill filter（5s window 剔自家 fill cascade noise）已接。**但 41 cascade events/30d 對 per-event forward-return IC 是小樣本**（需擴窗至全 span 或降 threshold 至 1M=212 events 才過 N≥30 多分層）。

**LSR 軸更正**：research.alpha_long_short_ratio_history=**0 row**（呼應 06-13 發現，TODO 稱 backfill done 但 research LSR 軸實為 0）；但 market.long_short_ratio（live WS）有 20773 rows 可用——LSR carry 因子用 live 表而非 research backfill 表。

**證據紀律**：全窗為 DOWN regime（BTC ~64k，liquidation 密度偏多）→ 任何 cascade/carry 正結果必標 regime-bet。報告：workspace/reports/2026-06-14--altdata_axis_offline_readiness.md（複製 Operator/）。

## 2026-06-14 全倉 ML/DB cold audit（read-only Linux runtime + 靜態接線）

**Verdict: FINDINGS（無 CRITICAL；ML 決策層全系統 ≤Shadow，無 Production component）。** sqlx head=139/122 all_success；V138/V139 Guard A/B/C 完整（含 MIT N-1/N-2）。
- **★ ML 決策層整條斷線（HIGH）**：(1) `resolve_latest_production_artifact`(ml/registry.rs:190) 0 個 live caller（僅 doc 引用）；(2) live combine layer 的「ML」是 `build_ml_inference_shadow` mock（id="shadow_mock_v1"，linear clamp01((bps+10)/20)，confidence=0.5 hardcode），且只在 `emit_shadow_exit_observation`（shadow_enabled-gated，純審計「does not alter close path」）內構造；live exit call-site ml_opt 強制 None（helpers.rs:141）。訓練出的 LightGBM q10/q50/q90 永不載入 live。
- **model_registry frozen（HIGH）**：3 row 全 grid_trading shadow_only/canary=shadow/train_date 2026-04-23（7+週 stale）/sample600/**0 promoted_at**。resolver `WHERE canary_status IN ('production','promoting')` → 永回 None。
- **model_registry freshness healthcheck 盲區（MED, test-blindspot）**：check_model_registry_freshness `WHERE canary_status='production'` → shadow-only 永遠 slots=0 → PASS "Phase 1a/2 expected"，7週 stale shadow model 對監測不可見。
- **exit_features Shadow（INFO）**：3275 fresh（demo2026/live_demo1192/paper57），但消費者全是 offline research（exit_threshold_calibrator/counterfactual_exit_replay/summary/edge_p2_flip），`program_code/ml_training/` 不讀，live 引擎不讀 → 0 decision impact。
- **decision_shadow_exits Skeleton（INFO）**：writer spawn 但 3 TOML 全 shadow_enabled=false → 0 row（預期 dormant）。
- **★ fills_loader.py 未提交改動=正確的 label fix（LOW-positive）**：改 `realized_pnl - close.fee - entry.fee`（post-fee net label）。實證 trading.fills.realized_pnl 是 GROSS（pipeline_helpers.rs:513 `gross_bps=realized_pnl/notional`），fee 存正值（305/305 fee>0），entry-join 100% 命中（310/310）。舊 query 用 gross PnL 當 label 是 leakage-adjacent 污染。BUT docstring 自相矛盾（稱 Bybit closedPnl 已 net 卻又減 fee）= doc-stale，code 對 doc 錯。
- **alpha 主路全 0 不變**：listing_capture_events / pre_registered_hypotheses / demo_residual_alpha_reports / hidden_oos_state_registry / alpha_wealth_ledger(FDR) / research.alpha_long_short_ratio_history(LSR 軸) 全 0；residual triple-OFF inert。alpha_funding_rates_history 46539 / alpha_open_interest_history 348153（max ts 2026-06-03 停 11d）僅 offline research 消費。
- **L2 memory 進展**：agent.agent_memory=99（embedding=99/dims=1024 全填，06-11「embedding 軸不可達」已解）；agent_memory_embedding_meta=1；FTS-only cron active 但首 material day no-op；B3 recall flag default 0 未持久開 = Skeleton→Shadow，E2E true distillation model-call 未跑。
- 證據：read-only ssh trade-core PG + Mac 靜態 grep；0 mutation。報告 inline 回 PM。

## 2026-06-14 Polymarket lead-lag forward IC 第一階螢幕 — INSUFFICIENT-DATA（結構性）

**verdict=INSUFFICIENT-DATA（結構性非實作）；全程 read-only ssh+PG SELECT，0 mutation；DOWN regime（BTC ret30=-0.0924）。**

- **資料就緒度（FACT）**：Polymarket artifact PIT-clean（manifest point_in_time=true、單一 snapshot_ts_utc/sweep、collector_git_sha 帶簽）但**只 2 個 daily snapshot**（run1 06-12T09:07Z 6100rows / run2 06-13T02:41Z 8371rows，自 06-14 audit 後無新增）。BTC market 1172（closed 416）。BTC 1m klines 覆蓋兩 ts。
- **★ forward IC 數學上不可計算（核心裁決）**：(1) cross-section 內每個 Polymarket BTC 市場的 forward y 都對應**同一個 BTC perp** → forward 是**標量**（不隨 obs 變化）→ Spearman/Pearson IC 無定義；(2) 真 lead-lag IC 需「同一信號 × 多時間點 t」配各自 forward(t→t+h) → 需 ≥20-30 snapshot 時間點，現僅 2 個 → **n_effective(時序)=1，power=0**。殘餘 IC（扣 BTC-beta）= 不可計算（forward IC 未定義時殘餘無從定義）。
- **四螢幕實測**：A(lead-lag forward)=不可算（n_xs=394 但 forward 標量 1m=-0.000177/5m=-0.000809/60m=-0.00319）；B(in-sample 同步)=BTC realized T1→T2 +0.00317 vs Δprob 中位 -0.001（非 forward，regime-bet）；C(calibration)=daily snapshot 只抓 resolve 後 0/1（{0.0:196,1.0:219}）缺 pre-resolution odds；D(odds-momentum)=closed BTC n=95 Spearman(d1, 結算0/1)=**0.7654 p<0.0001 但 tautology**（odds 收斂自身結算≠對 perp forward alpha）。
- **解鎖條件（operator-gated）**：activate hourly-topn lane（現 commented-disabled）累積 ≥20-30 時間點 implied-prob 時序 → 方可跑真 lead-lag forward IC + BTC-beta 殘餘化 + regime slice + HAC + Bonferroni。
- scratch=trade-core:/tmp/openclaw/scratch_polymarket.py + scratch_poly_xs.py（SELECT-only，中文注釋）。報告：workspace/reports/2026-06-14--polymarket_leadlag_ic_preliminary_screen.md（複製 Operator/）。

## 2026-06-14 carry/crowding 多因子 leak-free PIT IC 螢幕（preliminary，read-only）— VERDICT: NO-SIGNAL

**軸**：funding(carry)+OI 變化+LSR(crowding) 多因子 cross-sectional，測 beta-residualize 後殘餘 IC。**read-only**：market.* live hypertable SELECT 匯出 → /tmp/openclaw 本地 PIT 分析（scratch_carry_crowding*.py），0 mutation。窗=2026-04-05→06-13（69d，DOWN-dominated 單 regime）/25 carry sym/hourly rebalance。

- **VERDICT: NO-SIGNAL**。per-symbol BTC-beta residualize（rank-changing）後，**全樣本(ALL-regime)殘餘 IC 全部 |IC|<0.02、無 |HAC-t|>1.6**；最強 MULTI(carry−crowd)4h IC=+0.019/HAC-t=+1.60/p=0.11 未過 |IC|>0.05 門檻且不顯著。residualize 正確「移除」full-sample 負傾斜（carry full −0.005→殘餘 +0.004；crowd_lsr 4h full −0.023→殘餘 −0.011）= 證明那點負相關是 beta 副產品非殘餘 alpha。
- **唯一 |殘餘IC|>0.05 命中全為 bull-only n=68**（166 bull-hours/69d down 窗）= 教科書 regime-bet，呼應 5 次 NO-GO 同根因。MULTI 4h bull +0.088(t2.59)/crowd_lsr 4h bull −0.086(t2.67)；**Bonferroni 0.05/96=0.00052，bull p=0.010-0.021 全過不了校正**；down oi_chg 4h split-half 翻號脆弱。
- **leak-free 負控 PASS**：bull crowd_lsr 4h 真實 IC−0.086 落在 shuffle 分布 0 百分位（shuffle −0.006±0.022），bull 窗分 40 block 非單一 rally → bull 下確有真橫截面結構但 regime-conditional/樣本不足/不過多重檢定/不跨 regime = 不可作 promotion 證據。
- **方法瑕疵已修**：Method A「橫截面減等權市場 return」對 Spearman 是 rank-invariant no-op（減常數不改 rank）→ 棄用；down-beta 透過 differential beta 作用，唯 per-symbol beta residual / cross-sec beta-reg residual 改 rank 才真去 beta。4h horizon overlapping return 用 NW-HAC t(lag=4)。
- **PIT caveat（HIGH）**：market.* 無 fetched_at/ingest_ts → OI/LSR ingest lag 不可表內觀測，「0 lag」是架構 ASSUMPTION（若 lag>0 殘餘 IC 只會更弱=更保守，不翻案）。survivorship=今日 25 sym 固定集未做 lifecycle（69d 內都活，影響小，標 ASSUMPTION）。
- **建議**：此軸 = NO-SIGNAL，資源轉向真換軸另類數據（on-chain/事件機率/option flow/orderbook 微結構）非精修 carry/crowding。若救則須跨 regime 擴窗（2-year research.alpha_* backfill+補 LSR 0-row 2-year），但 bull 命中過不了 Bonferroni、期望值低。報告 workspace/reports/2026-06-14--carry_crowding_leakfree_ic_screen.md（複製 Operator/）。

## 2026-06-14 — sqlx 全 runtime-checked seam 查證 (verdict=confirmed, HIGH)
- 實測：openclaw_engine src 0 compile-time `query!` 宏、93 runtime call site（61 sqlx::query( + 27 query_as + 5 query_scalar），無 .sqlx offline cache（Cargo macros feature 啟用但未用）；Python 側 163 檔 raw SQL 同樣 runtime-unchecked。column 名全為 string literal，compiler 看不見 → migration rename/drop column 對 Rust 編譯+Python 皆隱形，runtime 才破。
- 反證部分成立但不閉合 gap：(a) audit_migrations.py 有 column-level 比對但**方向僅 migration-declared→DB**（不解析 consumer query），且是 operator manual CLI、未進 cron/CI/healthcheck；(b) migrations_test.rs / persistence test 需 OPENCLAW_TEST_PG，CI（ci.yml）只跑 cargo check 全 SKIP；persistence test 自建 CREATE TABLE 非跑真 V### migration → 即使跑也測不到 drift；(c) M4 fills_loader 有 grep-based black/white-list schema test（test_source_loader_schema.py）但僅 M4 局部，且其存在本身=E2 cold review 已抓到 5 個 schema-incorrect column 的實證（drift 真發生過）。
- impact 加重：16 個 DB writer 吞 query error（warn!/error! only 不 propagate）→ column-drift INSERT 失敗=silent 不寫 row，重演 V023 silent-noop 但在 consumer 側。read 路徑 19 檔 propagate(?) 會在首次呼叫 surface 但非 boot 即時。
- fix_hint：①把 audit_migrations.py 進 CI（需 ephemeral PG service）或 cron+healthcheck check_X()；②高價值寫路徑改 query! 宏 + cargo sqlx prepare 產 .sqlx offline cache（CI sqlx prepare --check）；③至少對 consumer query 引用的 column 做反向 grep contract test（擴 M4 模式到全表）。

## 2026-06-14 Polymarket H4 Calibration Gate（retrospective CLOB lane，read-only public API）

**verdict = WELL-CALIBRATED**（限有實質流動性 resolved crypto 市場）。補上 06-14 leadlag 報告 Finding C「resolved calibration 不可算」的 gap：那是 daily snapshot lane 限制（只抓 resolve 後塌成 0/1 的 odds）；改走 CLOB `/prices-history`（resolve 前完整賠率時序，≥12h 粒度）即可算。
- 枚舉 gamma `/events?tag_slug=crypto&closed=true` 14 頁 → 1302 個 resolved binary crypto 市場；按 volume top-320 取 CLOB 賠率時序，抽 closedTime−horizon 前最後一點。
- **T-24h n=274 Brier=0.0678 / T-1h n=317 Brier=0.0518**，coinflip=0.25 → BSS +0.73/+0.79（遠優），優於 hard-favorite(0.079-0.099)。ECE 0.029-0.043，reliability curve 接近對角（質量集中兩端皆 pred≈realized）。n 均 >>30。
- **★ 降溫（必傳 PM/QC）**：(1) 校準↔流動性強相關——中低流動性桶（vol 2..234，n=14 有效）Brier 0.246≈coinflip BSS+0.018、對 base-rate BSS−0.20=崩。alpha 只能在 liquid 市場做=賠率最準的母體→錯價空間天然小。(2) 「T-1h」median gap 實際 11h（12h 粒度限制），兩 horizon 真實時間差不如標籤暗示。(3) survivorship: resolved-only + volume-top selection 雙偏樂觀。
- **H4 通過 ≠ lead-lag alpha 成立**（必要非充分）：forward IC（賠率 lead perp）仍待 hourly-topn lane ≥20-30 時間點，QC（alpha 顯著性）+MIT（IC 方法論）共審。
- 報告：`workspace/reports/2026-06-14--polymarket_calibration_gate_H4.md`（已複製 Operator/）。

## 2026-06-14 資訊論 lens 探索（transfer entropy / MI，read-only prod data，leak-free scratch）

**任務**：用 TE/MI 非線性有向資訊流找「IC≈0 但 TE/MI 顯著」的結構性 edge，禁線性範式判死。**結論：CONDITIONAL-EDGE（弱）+ 大部分 NONE-FOUND-beyond-linear**。引擎自建（quantile-symbolic 5桶 + Miller-Madow 偏差修正 + block-perm source null），合成自檢通過、負對照(shuffle target)崩到 z=0.9、leak-src 對照爆高 => 對齊正確。
- **OFI/cross-asset/large-flow → forward**：TE 全顯著(effTE 0.02-0.25, z>>3)但**線性 Spearman IC 同樣大(0.1-0.55)且與 effTE 共單調**；horizon decay (1/5/15/60m) TE 與 IC 一起衰減，**無「IC死TE存」的 lens-unique 區**。=> 這些是線性已抓的 lead-lag，非 lens 獨有，1m 級高 IC 是 microstructure 同步假象，拉長即死於 cost wall。NONE-FOUND-beyond-linear。
- **ΔOI(5m ratio) → forward 1m**：唯一 lens-unique 指紋——12/12 symbol TE 顯著(BTC effTE=0.0092 z=84)但 **|IC|<0.007**（非單調，Spearman 抵消）。條件 MI 控制坐實非洩漏：**I(ΔOI;fwd|past)=0.0036 bits, z=210, p=0.005**（條件化掉 reversion 後殘餘仍顯著）。BUT 量級=reversion 主軸 I(past;fwd)=0.119 bits 的**僅 3.0%**，且主軸本身 sub-cost。=> 真實非線性、leak-free、線性看不見，但 standalone 太小不可獨立交易。
- **liquidation pressure → forward**：TE 顯著(z 5-21)但 IC 也達 -0.05~-0.095（非 lens-unique）；樣本僅 1 個月、半數 alt n<3000 skip。
- **交互網格**：(ΔOI × past-ret) forward edge 由 past-ret 主導（past0→+12bps / past4→-10bps = 1m reversion 跨 maker-cost~4bps 但難跨 taker~14bps）；ΔOI 行幾乎不分層，synergy 僅 0.0007 bits。
- **killer_risk**：ΔOI 殘餘信息 3% 量級 + 寄生在 sub-cost reversion 軸；OI 5min cadence 對齊到 1m 有插值噪音；單一 DOWN regime(BTC 66751→64396 69.5d) 全程，非線性結構可能 regime-specific。
- 報告：`workspace/reports/2026-06-14--info-theory-te-mi-nonlinear-edge.md`（複製 Operator/）。scratch in /tmp/openclaw。

## 2026-06-14 Hawkes 自激點過程 lens — 清算叢集（read-only Linux runtime trading_postgres）

**Verdict: CONDITIONAL-EDGE (defensive/execution-quality, NOT directional alpha).** 機制=清算自激叢集真實存在，但可交易部分是「逆選擇避免」非「方向預測」。
- **分支結構真實**：market.liquidations 263566 events/28d/84 sym，ms 時戳。單變量指數核 Hawkes MLE：BTC η=0.850(half-life 0.27s)/ETH 0.816/SOL 0.749/XRP 0.705/DOGE 0.677/HYPE 0.624。LR vs Poisson null=455k(BTC) 等天文顯著。η 對去日內節律 robust(BTC 0.850→0.846 移除最忙小時)。GOF：單 exp 核 underfit(KS p≈0, resid CV≈2.25 vs 1.0)→真 η 可能更高，需 power-law/sum-of-exp 核精修(非 falsification)。
- **方向預測=NONE-FOUND（誠實）**：λ(t)→signed forward return spearman |ρ|≈0.01-0.04 且符號錯(輕微 mean-revert against liq direction)，decile spread ~0.01-0.11bps«成本牆。坐實 down-beta 偽裝，與既有 cascade-fade 死因一致。
- **活動/波動預測=STRUCTURAL（強）**：event-time λ(t_i+)→forward event count spearman ρ=0.70-0.82(p=0)，top decile 後續清算數 21-88× bot decile。clock-time(1m grid)被 0.27s half-life 嚴重稀釋(ρ 僅 0.05-0.11，decile ratio 1.02-1.04)→edge 是 sub-second。
- **逆選擇量化=機械 edge**：top-λ decile 後 10s 絕對價移 32-43bps vs bot decile 3.6-4.6bps = 8-9.5× adverse lift；median inter-event gap 8-26s(calm)→0.008s(cascade)。被動掛單/taker 進場在高 λ 窗面臨 ~28-39bps 立即逆選擇 → λ-gate(top decile suppress entry/widen quote)機械避開 = 真實 execution edge(成本牆 14bps taker/4bps maker 以上)。
- **可實作=HIGH（基建已在）**：liquidation feed live fresh(last write 59s ago,5594/24h)；panel_aggregator/liquidation_pulse.rs(615行)已消費 allLiquidation.{symbol} WS event 流 + on_liquidation 事件 hook + AlphaSurface 餵 step_4_5_dispatch。Hawkes 遞迴 λ = O(1) per-event(state=exp(-βΔt)·state+1; λ=μ+α·state)，(μ,α,β) 離線 fit 為常數，~30 行加進既有 aggregator，零新基建。
- **killer_risk**：(1)逆選擇 avoidance 是 counterfactual——需 live A/B(λ-gated vs ungated 同策略)實證真省成本，目前是 tape-implied 非 realized fill PnL；(2)gate 只減損非增 alpha，須有底層 net+ 策略才有意義(否則減損空轉)；(3)單 exp 核 underfit，live λ 估計偏低需精修核或 sum-of-exp；(4)Bybit allLiquidation feed 是 throttled/sampled(非全量 tape)→ η 可能被低估、λ 標定有偏。
- scratch: /tmp/openclaw/hawkes_{liq,gof,predict,vol,eventtime,adverse}.py（trade-core）。報告 inline to PM。

## 2026-06-14 Cash-and-carry delta-中性淨 APR 驗證（PA Wave-0 $0 spike）— VERDICT: NEGATIVE-OR-ZERO

**軸**：long spot + short perp 收 funding。資料=research.alpha_funding_rates_history 46539/20sym/2yr(2024-06→2026-06)/8h PIT walk-forward。read-only ssh+PG SELECT，scratch /tmp/openclaw/scratch_carry_{validate,quarterly,robust}.py，0 mutation。

- **核心**：gross funding（majors ~5-6%/yr）≈ spot coc（5-10%/yr）→ net APR 無 buffer，coc≥5% 多數 symbol 全負。8h rebal=fee-suicide（1095x turnover×26bps=−285~372%/yr）；30d rebal 唯一非死 horizon 但 EW net@coc0%=+0.19 / @5%=−4.81 / @8%=−7.81。
- **regime-bet 鐵證**：9 季僅 2024Q4（bull-mania funding 尖峰 gross 15.22%）net@5%+6.71 過關，其餘全負；last-90d 當前 regime EW gross=−0.06%（funding 近零至負，正在付錢持有），net@5%=−3.56。
- **conditional 不救**：positive-funding gate（majors 本就 78% 正）幾乎不加 alpha；high-premium expanding-75pct gate 犧牲 time-in-market（hit 3-9%）folded gross 塌到~1%，net 全負。
- **樂觀上限穩健**：maker 2bps+0slip+top8-best majors+30d，coc=5% 也只摸 breakeven(+0.09)、coc=8% 全負 → 非保守成本誤殺，是結構 gross≈coc 無 buffer。
- **leak-free**：PIT prior-only gate（funding[i-1]/expanding-pct），收 funding[i] 不含進場後結算窗；20sym lifecycle 全在（唯 TONUSDT 窗末 delisted）；BTC regime prior-only 30d。
- **caveat**：缺真 spot 表（klines 是 perp）→ basis MtM/spot borrow 須真 spot 數據精算（只會更差不翻案）；coc 顯式假設非實測。
- **建議**：不建 spot 子系統（Wave-0 NEGATIVE）= 用錢自動化 regime-bet 空間，違反鐵則。資源轉真換軸（on-chain/事件機率/option flow/微結構）。報告 workspace/reports/2026-06-14--cash_and_carry_net_apr_validation.md（複製 Operator/）。

## 2026-06-14 realized-PnL 回饋管線 + 在線學習 + 本地 ML 引擎角色（設計，read-only grep + Linux runtime 驗）

**核心發現（reuse 重大）**：`learning.bayesian_posteriors`（V004，272 fresh rows，weekly cron 寫）+ `thompson_sampling.py`（完整 NIG 共軛 + select_next_arm + PG persist）+ `realized_edge_stats.py`（round-trip 配對 + post-fee net bps + winsorize + price-jump guard + funding attribution + entry/exit context_id）+ `james_stein_estimates`（984 rows）**全已存在**。整條 allocator 骨架已在，缺的是接線正確性 + 消費端。
- **★ regime 軸是假的（HIGH bug）**：bayesian_posteriors.regime 實值={demo,live_demo}=engine_mode，非市場 regime（cron `_fetch_recent_fill_returns` group by engine_mode 卻命名 regime）。真 regime 源 `research.aeg_regime_labels`(7696 rows leak-free PIT BTC-anchor) 存在但 **stale（max signal_ts 2026-06-01 停 13d，runner 自 06-01 沒跑）**；`decision_context_snapshots.regime_1h` 近 7d 全 NULL（flat regime 死管道）。
- **★ 在線更新是假的**：cron 用 `empirical_bayes_init`（每次從零 re-init 全窗 fills）非 `update_posterior`（共軛序列）→ 不是 online，是 weekly batch re-fit。且 select_next_arm **0 consumer**（allocator 永不被決策消費）=Foundation/Skeleton。
- **attribution 正解**：用 realized_edge_stats round-trip（exit fill realized_pnl≠0 配對，天然避免 entry-fill double-count）+ entry_ts join aeg_regime_labels（PIT：regime signal_ts ≤ entry_ts 的最新 daily label）。fills 100% 帶 context_id（7d 217/217）→ join 可行。
- **誠實鐵則落地**：底層 arm 全負 EV（06-13 證 0 validation_passed cell）→ allocator NIG posterior mean 自然為負 → select_next_arm 選 least-negative，配合「全 arm posterior_mean<0 → 歸零配置/不開倉」門檻 = 學會歸零非硬湊正。demo 撮合 artifact（無 queue maker fill）→ round-trip 標 `fill_realism_tier`（maker-no-queue 標 non-transferable）。
- **本地 ML 引擎角色**：LightGBM/Optuna shadow（model_registry 3 row frozen 2026-04-23）轉 (1) regime 分類器 feeder（aeg_regime_labels runner 日更）+ (2) arm-performance 學習器（NIG posterior 即線上學習器，ML 只負責 regime 條件化的 feature/特徵化，不直接下單）。leak-free 在線評估=expanding-window walk-forward + purge(exit_ts)+embargo，非離線 backtest。
- **E1 spec**：新表 `learning.arm_realized_attribution`（round-trip 級 append-only，hypertable on exit_ts）+ `learning.arm_posterior_history`（posterior 快照含 asof_ts/regime/n_eff，append-only 非 UPSERT 以保 PIT 軌跡）；bayesian_posteriors 加 regime 真值 + asof（或新表取代）。全 Guard A/B/C（mirror V127）。
- 邊界：design-only，0 碼改，dirty 檔（fills_loader.py/TODO/memories）不碰。報告 inline 回 PM。

## 2026-06-14 ADPE reward 查詢效能爆炸 RCA（Linux PG 實證，免-migration 修法）

- **根因**：learning.mlde_edge_training_rows view（V084）的 `signals` LEFT JOIN LATERAL（`WHERE s.signal_id=i.signal_id ORDER BY ts DESC LIMIT 1`）在壓縮 chunk 上 bulk-decompress 全掃，每 outer row 一次。storage 級坐實：signals/intents 壓縮 `segmentby=symbol`（不含 signal_id），signals PK=(signal_id,ts) hypertable 單 signal_id 查無 ts 約束 → ChunkAppend 無法 prune → 歷史壓縮 chunk btree 不可用 → ColumnarScan+Bulk Decompression+Filter signal_id（Rows Removed≈1976/probe）。30d plan 另翻車：planner 放棄 df Memoize+PK，改全表 Seq Scan decision_features(14.1M) 建 hash。
- **量級**：7d=84 rows/1.9s cold；30d=144,526 rows/3827s(64分)。cost 620k→2.0M 但 wall-clock 2126x = cost model 嚴重低估重複 decompress。
- **修法（免-migration，已實證等價+3975x）**：直查 base 表（intents JOIN decision_features + dcs-PK lateral），**砍 signals lateral**。30d EXPLAIN ANALYZE=962ms，144,526 rows 逐字相同。signals lateral 對 reward 是 near-no-op：strategy_name 全由 intent/feature 欄提供（needs_signal=0），attribution `signal_context_id=context_id` 對 demo label-present 濾 0 行。7d view-vs-fix per-(strat,regime) 分組 diff=0 全綠。反證：correlated ts-bound lateral 仍 3m20s 未完、set-based EXISTS 120s timeout = signals 壓縮 chunk 無 signal_id segment 不可救。
- **vocab 命門保住**：fix 輸出 linucb_arm_id 維持 `<view_regime>__<strategy>`（reward_source parse_arm_id 只取 strategy 段），regime 仍 view 詞彙交 map_view_regime_to_alloc_regime；arm_id 後段 strategy 與 strategy_name 同源。不重蹈 V031 vocab bug。
- **needs_migration=false**。次要 BLOCKER：64 分查詢能跑完 = reward_source 的 statement_timeout(5000ms) guard 未實際生效，E1 須查 `_set_local_statement_timeout` 是否真套此 cur。誠實 caveat：fix 以結構性 attribution 取代 signals 再讀比對，demo 等價但語義略放寬。
- 報告：workspace/reports/2026-06-14--adpe-reward-query-perf-rca.md（已複製 Operator/）。

## 2026-06-14 Track2 新策略 arm 數據可得性 + 引擎/ML 整合審計（read-only 設計階段）

**核心：插入機制 0 阻力（Strategy trait+StrategyFactory+IntentProcessor.process 單寫入口全現成），但「成為 allocator arm」有命門——linucb arms_v1_15 硬編 5 舊策略，新策略 emit intent 但 select_arm_after_gates 解不到 arm（arm_not_found warn）→ 須擴 arm 空間（ADR）。allocator 真消費=demo ADPE runner（reward_source 砍 view lateral），非 linucb（shadow-only 0 decision impact）。**
- **整合表面（read-only grep 親證）**：(1) strategy registry=`strategies/registry.rs::StrategyFactory::create_with_params`（唯一註冊點，現 8 策略非 doc 寫的 5）；新策略=impl `Strategy` trait（on_tick→Vec<StrategyAction::Open(OrderIntent)>）+ registry push + params.rs TOML + `declared_alpha_sources()`（AlphaSourceTag SoT，**enum 改必 ADR**，alpha_surface.rs:53）。(2) 單寫入口=`IntentProcessor::process(intent,gov,state,vol,profile)`（router.rs:1043 按 GovernanceProfile 分流 cost_gate）；Guardian/cost/Kelly/P1 全在 process 內，trait 的 StrategyAction::Open 必走此路（原則1/4 不繞）。(3) **demo explore-gate=`cost_gate_moderate_with_slippage`（Validation profile，router.rs:1044）**——operator「只改 demo 分支」精確命中此函數；live=`cost_gate_live_with_slippage`（Production）+ Exploration→None 不碰。demo 已有 low-sample(n<30)/cold-start→exploration 放行 + deep-neg(<-15bps)→block 的既有探索邏輯。
- **arm 歸因鏈**：arm_id vocab=`<regime>__<strategy>`（arms_v1_15.rs:34 雙底線）；linucb v1_15=15 arm（3 regime×5 舊策略，**新策略不在內**）。realized PnL 歸因經 `learning.mlde_edge_training_rows` view（V031，linucb_arm_id=`regime_norm||'__'||strategy_name_norm`）→ ADPE reward_source 砍 signals lateral 直查 base 表（962ms）→ regime_bandit_allocator NIG。命門：reward_source 用 allocator make_arm_id 重建 arm_id（非原樣用 view 詞彙），新策略只要 strategy_name 進 fills + decision_context 即自動歸因，無需改 view。
- **數據軸即建 vs 缺採集**：**即建（資料齊）**：liquidation_cascade（market.liquidations 263k/84sym live WS，且 liquidation_cascade_fade 策略+AlphaSurface.liquidation_pulse 已是現成模板）、carry/crowding（market.funding_rates/open_interest/long_short_ratio live hypertable）——但前者 06-14 證 directional NONE-FOUND/僅 execution-edge，後者 06-14 證 NO-SIGNAL。**缺採集（schema-ready 但 0 row）**：listing-fade（research.listing_capture_events V130 schema+collector daemon.py+pg_sink+systemd installer 全在，但 systemd 未裝→0 row，上市瞬間不可 retro，須前向 seed ~Q4 才 n≥30）；orderbook 微結構深度（Gate-B 只訂 kline.1+publicTrade，無 orderbook.50 depth→OrderflowImbalance tag 永 None）。**缺源**：on-chain/Polymarket horizon<1d/option flow（外部 lane 未活化）。
- **誠實**：小帳戶優勢可證偽假設=demo $100 cap 策略（funding_harvest 範式）容量受限 symbol（thin alt listing pump、低流動 cascade）大資金無法吃→小帳戶能進的微容量錯價=真優勢；但須標「demo 撮合無 queue maker fill→round-trip 標 fill_realism_tier non-transferable」（撮合 artifact 非真 edge）。新 arm 即使數據齊，底層仍須跨成本牆（maker RT~4bps/taker~14bps）——06-14 五軸全 NO-SIGNAL/execution-only，數據齊≠有 alpha。
- 證據：read-only grep（registry/trait/gates/arms/reward_source/V130/V058）+ runtime 數據沿用 06-13/06-14 親證 row count；0 業務碼 0 schema 改 0 部署。報告 workspace/reports/2026-06-14--track2_new_arm_data_availability_integration.md（複製 Operator/）。

## 2026-06-14 cost_gate「雙重扣成本」誤拒帶 read-only replay 量化 — VERDICT: NO-MISREJECT-BAND, gate 不該修

**任務**：operator 批准 read-only replay 量化 cost_gate 誤拒帶（0<net<threshold）真實 forward PnL 期望正負。**結論：誤拒帶=空集；gate 拒的全是真負；不該開閘。go=false（守 survival-first）。**
- **gate 源確認**（gates.rs:177-214 demo / 255-320 live）：threshold reject（`edge<threshold`，threshold=fee_bps/wr*1.3，demo ~50-91bps 寬）**結構不可達**——正 cell 須 `fresh AND from_runtime_field AND validation_passed` 三真才進 threshold 比較，否則 demo→exploration(pass)/live→reject。runtime **0 validated cells**（7d 42874 cells/0 validated/364 positive）→ 正 cell 全走 exploration 放行，永不 threshold-reject。
- **risk_verdicts replay**（30d demo+live_demo，trading.risk_verdicts hypertable 37，reason/verdict/context_id）：Rejected 3,958,263 / Approved 2,377。reject 分桶：NEG_reject(est<0) demo 3.25M + live_demo 386k；**THRESHOLD_misreject_band=0**（兩 engine）；**POS_EST_KILLED=0**（max reject est=-0.36，無任何非負估計被殺，再證 06-13 rejected_with_positive_estimate=0）；其餘=qty_zero/position_count/duplicate/fee-unavail/ATR-unavail fail-closed（合法）。
- **真 forward PnL（非循環，trading.fills 實現 round-trip 30d demo）**：4 real strat 含 entry+exit 全 fee net=**-109.93 USD**（gross +39.73 - fees 149.65）。per-strat：grid_trading net-after-close-fee +1.36（但 Buy-close 349 筆+41.86 vs Sell 35 筆=down-beta 副產品非 alpha）、ma_crossover **-43.0**、bb_reversion **-17.6**。坐實成本牆=gate 負估計是對的。
- **near-zero band（-1<est<0，161524 rejects）+ rejected→decision_outcomes join**（n=107 唯一可 join，3.6M 拒單僅 107 有 forward outcome backfill）forward 1h -101.8bps/24h -500.8bps/0-of-107 24h 正 = 全負。但 n=107 微小且 close-direction 歧義 → 非主證；主證=realized fills net 全負。
- **資料 caveat（go=false 的次因）**：rejected 決策**幾乎不被 forward-backfill**（decision_outcomes 30d 僅 107 join；decision_context_snapshots 7d 6139 join 但 0 outcome_backfilled）→ 純 per-decision counterfactual forward PnL 大規模不可測；裁決靠 (a) gate 0 positive-est reject 結構鐵證 +(b) realized fills net 全負 + (c) 0 validated cells。
- **裁決**：誤拒帶真期望非正（空集 + 真負）→ gate 守得對，**不該修**，開閘=用錢自動化負期望單違反生存優先。read-only ssh+PG SELECT，0 mutation。報告 inline 回 PM（無獨立 .md per task instruction）。

## 2026-06-14 P1-SCHEMA-1 contract-test 設計 (sqlx runtime-checked gap)

**確認 drift**：engine sqlx 0 `query!` 巨集 / 0 `.sqlx` cache / 99 runtime-checked `sqlx::query()` call site；`migrations_test.rs` 查 `information_schema.tables` 3 次、`.columns` 0 次（schema-consumer contract 真缺）；CI=`cargo check` only（`OPENCLAW_TEST_PG` 永不設 → 5 個 migrations_test 全 SKIP）。column rename/drop 對 Rust 編譯+Python 全隱形至 runtime first-touch（write fail 僅 `warn!` 靜默丟）。
**決定性 image 發現**：V006 unguarded `add_compression_policy/add_retention_policy`（非 `IF EXISTS pg_extension` 包裹，不同於 V002/V003 的 conditional hypertable）→ CI PG service **必用 `timescale/timescaledb:latest-pg16`**（= prod image，TimescaleDB 2.26.1），且 migrations 不自建 timescaledb extension（runner 也不）→ CI 須 migrations 前 `CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE`（pg_trgm/btree_gist/pgcrypto 由 migration 自建）。V140 (pgvector) 是 manual out-of-band 不入 sql/migrations，不需進 CI。
**設計**：(a) 新 `schema_contract_test.rs` 跑真 `MigrationRunner::run_if_enabled`(V001-V139) 後對 ~6 熱表執行代表性 consumer INSERT/SELECT（exit_features/fills/data_quality_events/decision_outcomes/exit_features/klines）→ schema 不符即編譯後 runtime fail；(b) audit_migrations.py 進同 CI job（已有 `information_schema.columns` 反射，補 migration-declared→DB 向）。(c) CI 新 job `schema-contract` gate 在 `pull_request` only（尊重 2000min/月；push-to-main 不跑），ubuntu-latest + services PG。既有 `docker/docker-compose.test.yml` 與 `migrations_test.rs` 可直接 reuse（env var 名不一致：test compose 用 `OPENCLAW_TEST_DATABASE_URL`，test.rs 用 `OPENCLAW_TEST_PG` — 須對齊）。不改 93 call site 為 query! 宏（列未來）。
**報告**：inline 回 PM（無 .md per 指令）。

## 2026-06-14 from-zero crypto-native edge 發散探索 + cost_gate 循環論證再審（read-only Linux runtime）

**任務**：operator 鐵則=禁判「無edge」、批判 cost_gate 循環論證、擁擠度為首要假設、crypto≠股市 from-zero 想機械軸。read-only ssh+PG，scratch /tmp/openclaw/mit_*.py，0 mutation。DOWN regime（BTC ~64k）。

- **cost_gate 循環論證指控=部分成立**：(1) gate 確實用「策略自己的 edge_estimate cell」判自己（edge_estimates.get_cell(strategy,symbol)），是 single-arm per-trade EV gate，結構上無法評估組合級/market-neutral/做市/vol-harvest（這些 strategy 名下根本沒有 edge cell）→ 對「別的盈利方式」是**沉默不評估**非「擋掉」。(2) **但成本模型本身非 taker-locked**（駁回部分指控）：fee_rate_for_tif（mod.rs:1951）PostOnly→maker_fee_rate + slippage=0；cost model `2*(fee+slip)*1e4`。maker RT~4bps vs taker~14bps 真實反映。strategies 默認 taker（Market），maker 入場 gated on `use_maker_entry` TOML（default false）→ 多數 fills 走 taker 是策略選擇非 gate 強制。(3) DEFAULT_TAKER=0.00055 / MAKER=0.0002（account_manager.rs:206/208）對齊 Bybit 真實 fee，非高估。**結論：cost_gate 不誤殺（5次 replay 證 0 positive-est killed），但它只防守 single-arm directional，不是「盈利方式的裁判」——換軌/組合級 edge 不歸它管，須另建 evaluator。**

- **★ liquidation-impact reversal = REAL-but-UNCAPTURABLE（最重要發現，誠實負）**：close-to-close fade（forced-buy 後做空/forced-sell 後做多）=超強信號：partial-IC -0.51（控制本bar dp 後仍 -0.51）、magnitude 單調（small +12→top1% +46bps）、12/12 sym 正、split-half robust、close[t1]->close[t2] top5% +39bps net-of-taker +25bps。**BUT entry 改 open[t+1]（可成交價）後 edge 全消失**：5m exec open->open all -0.07bps/top5% -1.6bps；1m exec open[t+1]->open[t+2] all -0.24/top5% -0.32。**全部 edge 活在 close[t]->open[t+1] 的 sub-bar gap（理論上限 1m +11bps/top1% +27bps）**=sub-minute 反彈，5m/1m bar 粒度 + 無 maker queue 不可吃。呼應 Hawkes 0.27s half-life。**翻案路徑=真 sub-second tick 執行 + maker queue priority（demo 帳號結構不可達）。**

- **OI-positioning 四象限 reversion**（5m）：new-longs(OI+P+)→fwd -4.9bps t-19 / new-shorts(OI+P-)→+5.5 t+19 = 強 reversion 但 pooled signed-IC 僅 +0.012（dp 主導），sub-cost，呼應 info-theory ΔOI 結論。
- **反擁擠 OI-extreme cross-sectional L/S**（4h）：mean -5.8bps/4h t-0.81、non-overlap n35 t-1.39 = NO-SIGNAL-or-INSUFFICIENT（OI live 表僅 7d span，單 DOWN regime，n 太小不可結論）。
- **funding-settlement-clock 機械漂移**：equal-weight 結算前後 ±15m minute-by-minute = 純噪音；funding-extreme post-settle cross-sec L/S 4h mean -15bps t-1.54 不顯著、pooled IC +0.021 = NO-SIGNAL（n80 settle 單 regime）。

**淨判定**：本輪 from-zero 探索**未找到 demo-bar-granularity 可吃的新方向 alpha**，但**改寫了問題**：(a) 真 mechanical edge（liq overshoot reversal）確實存在且 leak-free 強，只是活在 demo 帳號達不到的 sub-second/maker-queue 層 → edge 的瓶頸是**執行基建非市場無 edge**；(b) cost_gate 不是盈利方式的裁判，換軌須建 single-arm gate 之外的 portfolio/maker/execution-quality evaluator。資源指向：sub-second 執行層（Hawkes λ-gate execution-quality，已證 8-9.5x adverse-lift 可避）+ 跨 regime 擴窗（OI/funding live 僅 7-30d 單 DOWN regime，结论力受限）。報告 inline 回 PM（無獨立 .md per task instruction）。

## 2026-06-14 D1 反crowd「對手盤定位收斂」非方向 edge 離線驗證 — NO-SIGNAL (reframe 證偽: 擁擠是動量非收斂)
- read-only ssh trade-core SELECT-only (market.long_short_ratio/open_interest/funding_rates/klines 1m, 25 carry-universe sym, 70d 2026-04-05→06-14, DOWN-dominated)。scratch /tmp/openclaw/scratch_d1_*.py。
- crowding 信號 H4 (tail-only 三條件同時, leak-free PIT shift(1)/asof≤t/entry i+1/零重疊): LSR per-symbol trailing-24h z(buy_ratio) |z|≥門檻 AND OI 1h pct-change>0 (prior-only) AND funding 同號 crowd_side。z≥2.0 funnel 2997→1401→629 final (crowd 多356/空273 平衡, 非結構性long-only)。
- **VERDICT NO-SIGNAL (reframe 證偽且方向相反)**: 對手盤(站crowd反邊)殘餘(扣BTC-beta) reward 全 horizon/門檻 **顯著負**。best=z≥2.5/8h resid mean=−32.9bps HAC-t=−4.04 n=295 DSR≈0; z≥2.0/8h −33.4bps t=−3.71 DSR=0.000。所有 cell DSR≈0。split-half 同號(H2更負)。21/25 sym 負(非單symbol主導)。leak negative-control PASS (真−33.4 落 sign-shuffle 0.0 百分位, z=−4.48 = 真實非leak)。
- **對稱鏡像精確**: 順crowd(momentum)=精確 +33.4bps t=+3.71 mirror; 證明擁擠**動量延續**非均值回歸收斂 → D1 收斂假設方向錯。momentum 順crowd 殘餘扣beta後仍 +29.9bps(ALL)/+31.7(non-bull)/+28.8(down) = 非純down-beta (但那是方向動量非D1收斂, 且 bull n=77 beta-removed=−14.3 翻號=regime-bet caveat)。
- β_down (對手盤reward~btcfwd, down regime): −0.21~−0.80 強負 = 對手盤在BTC下跌時更虧 (crowd結構性long, 反crowd=short, down regime本該贏卻虧 → 極端LSR觸發時crowd是對的, 收斂沒發生)。
- 教訓: tail-only 三條件擁擠在 demo/1m/單一down regime 下 = 動量延續訊號 (順crowd 有 beta-residual), 不是收斂訊號; 反crowd 站對手盤是顯著虧損方向。D1 reframe 與 06-14 carry_crowding NO-SIGNAL 同根但更強證偽 (此處有顯著 effect 只是方向相反)。

## 2026-06-14 D2 清算瀑布 → LP 收斂 (delta-中性 reframe) 離線驗證 — NO-SIGNAL (cost-killed)
- **非方向 reframe 統計上確實嚴格勝過 2026-06-03 方向賭版**: cascade 事件構造 (266k 清算→14614 聚類→p60 閾值 5846→5659 可用, 29 天, 195 事件/日, **n=5659 是舊 280 的 20×**)。最佳殘差 H=3: 收斂 reward mean=+8.17bps, **t(NW)=5.89 / t(day-block cluster-robust)=5.43**, β_down(殘差對 sign-folded BTC-fwd 斜率)=+0.0605 p=0.337 **<0.15 PASS** (非 down-beta 偽裝, 與 6 次前 NO-GO 不同根因), DSR(deflated 10 trials)=0.9998。收斂隨 horizon 單調衰減 (H3 t=5.4→H10 1.4→H20 ≈0) = 教科書微結構流動性回補指紋。leak-free: 事件落 bar OPEN boundary (open_ts_ms), anchor=事件 bar 前 5 bar 收盤均值 (純 prior 不含事件 bar), entry 嚴格 i+1 OPEN, forward 與聚類窗零重疊。
- **但 cost 腳判死, verdict=NO-SIGNAL (誠實不硬湊)**: gross 收斂 edge 整個活在 spread/queue 裡, 不可收割。**taker 雙邊: H3 net=−21.66bps t=−15.23** (2×5.5bps fee + 滑點全吃光)。**maker flat-p_fill 假象=+4.17bps** 但屬 measurement artifact (假設你在超調峰 OPEN 被填吃滿回吐)。**逆選擇 maker 模型 (限價掛 anchor 方向, 只在價格回穿才成交=吃掉你要捕捉的回吐) 才是真相: alt 腳 filled-net=−0.15bps t=−0.05 / E[全事件]=−0.06bps; major 腳 −15.5bps t=−21**。tier 二分: major(BTC/ETH/SOL n=3673) gross+3.27bps 但 <maker fee → maker-net −0.73bps; alt(n=1961) gross+17bps 但 overshoot median 52bps=不可規模化微價幣 + 逆選擇後歸零。
- 結論: 清算瀑布超調→收斂現象 **真實且 beta-中性**, 但 **non-harvestable** — 同一道 6 週成本牆在微結構層再次確認。資產: `/tmp/openclaw/scratch_d2_cascade_lp.py` + `d2_rewards.csv` + `d2_verdict.json`。

## 2026-06-14 P2-DIRTY-2 m4 fills_loader fee 自連 fan-out — 正確 post-fee net 聚合定義 (MIT+QC)

**對象**: `helper_scripts/m4/sources/fills_loader.py::FILLS_QUERY_SQL` 的 `LEFT JOIN trading.fills entry_fill ON entry_fill.context_id = f.entry_context_id AND entry_fill.engine_mode = f.engine_mode`。PG-empirical（trade-core trading_ai，90d，IN('live','live_demo')）。

**根因升級（比 E3 報告更嚴重）**: 不只 fan-out。join 缺 `entry_fill.entry_context_id IS NULL` 條件 → 把「context_id 等於某 close 行 entry_context_id」的 **close 行自身/其他 close 行當 entry fee 減掉**。M-query 實證：1770 個 matched entry_fill 中 **29 個是 WRONG_close_row_matched_as_entry**（close 被當 entry），只 1741 真 entry。PEPE 例：close `bybit-7d9b72fd` dirty 減 fee=0.01565（=true entry 0.0041734 + 該 close **自己的** fee 0.01147685）→ close fee 被 double-subtract（一次 f.fee、一次偽裝成 entry fee）+ 行 ×2 fan-out。

**Fan-out 數字**: close 行 A=1763 → LEFT JOIN 後 B=1796（+33, +1.9%）；C=30 close 配 >1 entry_fill；D=26 close 配 0 真 entry（COALESCE 0 靜默 gross-leak）。entry-fee 總質量 dirty=23.744 vs fixed=23.379（dirty 多減 ~0.365）。

**第二層污染**: `risk_close:`/`fast_track_reduce_half` 等 partial-reduce 行 `entry_context_id IS NULL` 但語義是 close（writer 標記不一致）→ 純 `entry_context_id IS NULL` 仍會把它們當 entry。canonical `edge_label_backfill.py` 用 `EXCLUDED_TAG_PREFIXES=(orphan_close:,adopted_close:,shadow_fill:)` + `strategy_name NOT LIKE 'unattributed:%'` + `JOIN LATERAL(... ORDER BY ts ASC LIMIT 1)` 取**單一 earliest 真 entry**（非 SUM）。

**正確 net 聚合定義（裁決）**: dirty SQL grain=per-close-fill（realized_pnl 經 R-query 證實是 per-partial-close 各自帶）。entry fee 不可在每個 partial close 全額重扣。正解 = LATERAL 子查詢取**單一代表 entry 行**（earliest entry_context_id IS NULL + 排除 close-prefix tag），net_pnl = f.realized_pnl − f.fee − entry_rep.fee。FIXED LATERAL 形式實證 rowcount=1763=A（零 fan-out）、4 真 partial-entry、26 entry-missing。entry-missing 26 行須 fail-loud（標 NULL net + entry_fee_missing flag），非 COALESCE 0。

**Report**: 直接回 PM/E1（無獨立 .md，per task instruction）。

## 2026-06-14 MIGRATION-TREE-1 forward-compat (V005+V023) scratch-DB dry-run — READY-with-1-CRITICAL-CORRECTION
**Verdict: design is FUNCTIONALLY READY (scratch GREEN all axes) BUT PA brief's核心前提錯誤 — AUTO_MIGRATE 在 prod active env 已=1 非 0**. 親驗 `settings/environment_files/basic_system_services.env`(唯一非-.bak,0600)第15行 `OPENCLAW_AUTO_MIGRATE=1`(含 opt-in 註解)。故改 V005/V023 檔=byte→SHA384 drift(親驗 prod DB checksum 逐字節=現檔:V004 2ec17f54 / V005 554d89c3 / V023 96bf3d01;openssl sha384=sqlx Sha384(sql.as_bytes()))→下次 engine restart sqlx Migrator checksum mismatch(ignore_missing:false)→`run_if_enabled` Err→main.rs:736 `std::process::exit(1)` engine 啟動中止 crash-loop。**非 latent landmine,是 active restart-breaker**。Mitigation 鐵則:E1 檔落地後、restart 前必跑 `bin/repair_migration_checksum --apply` 對齊 V005/V023 DB checksum(否則 prod 不重啟仍活,但任何 rebuild/deploy 即死)。
**Scratch GREEN(timescaledb 2.26.1, locale en_US.utf8 template0, ephemeral, prod trading_ai 全程未動 122 rows/3 model_registry 不變)**: A virgin V001→V139 corrected-patch=122 applied/0 failed,model_registry 21-col/canary_status✓;B V005 ordinal double-apply OK,virgin=0 legacy-bridge+6 non-legacy view✓;C brownfield(legacy 表在)=11 view 全建✓(DO-WRAP 不 regress);D 鐵則驗證 — legacy stub+1 row→self-heal 不 drop+Guard A FIRES RAISE✓(self-heal 不弱化 fail-closed);E prod-shape(21-col+data)re-apply=clean no-op rows/shape 不變✓。
**baseline 兩缺陷證實**: V005:414 account_snapshots_legacy missing(PART4 5 view brownfield-only,先於 V023 失敗)+ V023 Guard A RAISE(V004:135 legacy 15-col stub vs V023 新 21-col)。PA 設計(V005 5×DO-WRAP + V023 self-heal-drop-empty-legacy-before-GuardA)解兩者且不破 brownfield/idempotency/GuardA。
**實作注意(給 E1)**: V005 wrap 必逐一精準匹配 5 個 legacy view(account_snapshots/system_health/paper_pnl_snapshots/risk_events/learning_events),禁 wrap 跨越相鄰 6 個 non-legacy view(position_snapshots/order_events/trade_executions/ai_cost_events/observer_verdicts/market_tickers,讀 trading.*/market.*/agent.* 須保持 plain CREATE OR REPLACE,virgin 上即建)— 粗 regex 會把 non-legacy view 吞進 system_health_legacy 的 IF 分支致 virgin 上靜默不建(我首版 transform 即犯此,已修正後 GREEN)。E2 合審必驗 6 non-legacy view 在 virgin 上實建=6。
**checksum 紀律重申**: 改已 apply 的 migration 檔=DB checksum drift;AUTO_MIGRATE=1 下 = restart 級風險,非 future-only。

## 2026-06-14 — Fork-2 新數據軸+ML 方法可行性文獻掃描（replication-crisis 紀律）

**Trigger**: operator fork-2 任務，大量 WebSearch 找 papers/repo 評新數據軸 ingestion + ML 方法，每軸標 PROVEN-LIVE/OOS-BACKTESTED/PAPER-ONLY/OVERFIT-SUSPECT + 數據成本 + 整合工程量。報告 inline 回 PM（無 .md，依任務指令）。

**核心分軸結論（速度=可交易性的決定變數）**:
- **慢軸（小時/日級 = 我們 1m 可吃、無逆選擇）**：stablecoin exchange net-flow（Kaiko/Glassnode 證 7-14d 弱相關，daily 噪音大）/ whale 大額轉帳（6-24h contagion，但 MEV/交易所內轉/spoofed label 污染嚴重）/ options 25Δ risk-reversal skew（Deribit DVOL+chain **公開免費 API**，OOS-backtested vol-corr 非方向 alpha）/ ETF net-flow（BTC-only 單信號無截面，Farside 免費，**無嚴謹學術預測證據=PAPER-ONLY/anecdotal**）。
- **快軸（需 HFT，1m bar 決策吃不到 = 對我們是執行品質非方向 alpha）**：orderbook OFI（文獻證 <3min regime 才強、beyond-intraday 快速衰減，呼應自家 TE/MI ΔOI 與 D2 sub-5min 結論）/ cross-exchange lead-lag（ms 級，且方向有爭議：近期研究反證 Bybit leads Binance 62%，非 size 決定）。
- **arxiv 2602.00776「Explainable Patterns in Crypto Microstructure」= 最佳方法論模板**：CatBoost + GMADL direction-aware objective + 時序 CV + SHAP，**taker+maker 雙回測**（flash-crash 證 taker 逆選擇/maker 存活，直接對齊我們成本牆+執行發現）；**跨資產 SHAP 形狀穩定**（BTC→小市值可遷移）。
- **ML 方法去風險（TLOB arxiv 2502.15757）**：深度 LOB 模型（DeepLOB/transformer）**跨資產/regime 無法泛化，簡單 MLP 反勝 SOTA** → 別建脆弱深網，CatBoost/MLP + 好特徵勝。FinBERT/sentiment 論文宣稱（526% 但 Sharpe 0.407）= OVERFIT-SUSPECT/PAPER-ONLY。

**整合表面（read-only grep 親證）**: AlphaSourceTag enum（`openclaw_core/src/alpha_surface.rs:53`）已 stub 全部接點 — Tier2 Basis（mainnet spot account 前永 None）/OiDeltaPanel、Tier3 OrderflowImbalance（orderbook depth 永 None，spec levels 1/50/200/1000）/LiquidationCascade、Tier4 OnchainFlow/Macro/Sentiment/Derivatives/ExchangeEvent（全 placeholder）。**Bybit WS orderbook.50/.200 免費且不計 rate limit**（我們已訂 Bybit）→ depth 訂閱工程量低，但 OFI alpha 快/crowded。

**MIT 排序（applicability × evidence × adopt-cost）**: #1 options skew/DVOL 軸（免費數據+慢+OOS 證據+正交 funding/OI；建 Deribit collector lane）；#2 microstructure-as-execution（採 2602.00776 maker 回測法評逆選擇規避，非方向 alpha，counterfactual A/B）；#3 stablecoin/onchain 慢流（慢=我們可吃但 daily 噪音+label 污染，須嚴謹 PIT+去 beta）。**全部仍須跨成本牆 + 自家 leak-free PIT IC + 去 BTC-beta 殘餘 + 多 regime（現全 DOWN 窗）才算數**——文獻 PROVEN-LIVE 不存在（全 OOS-backtested 上限）。

## 2026-07-03 全倉 ML/DB 審計（read-only, Linux runtime 親證）— 3 HIGH
- **F-1 訓練集 label 污染**：M3 reject path 寫 label_net_edge_bps=0.0，quantile/scorer ETL（parquet_etl:459）無 close_tag 過濾 → 30d demo reject:fill ≈ 23,000:1（ma_crossover 1.88M:81），07-03 acceptance report pinball skill=0.0 / coverage 0.9988 三分位相同 = 常數 0 預測器；gate fail-closed 擋住但 lane 永久 degenerate。**F-2 drift lane no-op**：feature_tx 只接 paper pipeline（main_pipelines 493/637 demo/live=None）→ features.online_latest 凍結 2026-05-06 → drift_events 0 row ever → canary PSI gate 結構不可滿足（MARKET-KLINES-STALE-1 同款未 retrofit）。**F-3 crontab 置換**：06-27 17:xx 起 ~20 cron lane 死（passive_wait_healthcheck 90+ 檢查未倖存=監測自盲；universe snapshot/edge snapshot/L2 memory 凍結）；倖存 5 條全屬 demo soak loop。
- 次級：V142/143/144 header 聲稱 Guard A 但 body 無（模板破口）；mlde_shadow_advisor 每日 QueryCanceled（label 洪水 join 基數可信根因）；linucb 空訓練標 ok；aeg_regime_labels stale 32d 未修；embargo <50 樣本靜默跳過不入 report；V146 未 apply（prod 誤導 COMMENT 仍活）。訓練已解凍（model_registry ids 40-47 train_date=07-03 全 shadow）、CI schema_contract+audit_migrations 已接（舊 HIGH 閉環）。
- 報告：workspace/reports/2026-07-03--ml-db-full-repo-audit.md（已複製 Operator/）。

## 2026-07-06 Maker-feasibility + P0 microstructure-evidence data audit (read-only Linux PG)

**Trigger**: PM go/no-go — can current data support offline maker-edge study (A) + upgrade P0 evidence loop to microstructure-grade (B). Read-only ssh trade-core (sqlx head V150).

**Headline (推翻「只是 schema/Foundation」假設)**: microstructure recorder stack 是 **LIVE + 重度 populated**，非骨架。`OPENCLAW_RECORD_L1_EVENTS=1` 已持久化於 secrets env（rate-cap 50/s/sym）。實測 count(*)：`market.l1_events`=259M rows（recorder-v2，max_ts=now，18 distinct regime-days，min 2026-06-17）、`market.trades`=233M、`market.ob_top`=95M。ETHUSDT L1=18.6M rows、**bad-tick 0.00%**（stateful tracker 修好 crossed/locked；ob_top v1 仍 5.68%）。BTC/ETH/SOL/XRP/DOGE/ADA 全 18 regime-days 均勻覆蓋 → **超過 CP-3 ≥10-12 門檻**。fill_sim 引擎（`program_code/research/microstructure/fill_sim.py` 124KB）已建，queue-position + adverse-selection@5/15/30s + NET edge + break-even fee，read-only $0。→ **(A) 離線 maker 研究 data+tooling 已就緒且在累積**；binding constraint=單一 regime 窗（19 天，非跨 trend-stress）。

**Own-fill markout 現況**: fills total=16028；maker fills=2321，其中 maker_markout_bps 有值=221（歷史 pre-V145 誠實 NULL 無 backfill）。**近 14d maker fills=94，markout 覆蓋 94/94=100%**（V145 前向修復生效）。但 reference_source='mid_at_submit'（MM-verdict 唯一接受的乾淨 half-spread 基準）**只有 17 rows** global — 這是 own-maker-fill spread-capture 研究的真 binding constraint；其餘 maker markout 走 bbo_same_side(full-spread) 或 dispatch_last_fallback(退化，last price 非 mid)。markout 是 execution-quality @t=0（mid@submit vs fill），**非 forward-horizon**；1s/5s/30s horizon markout 只在離線 fill_sim artifact + `gate_b_ws.py`(30/60/300s) WS harness，DB 無 per-fill horizon 欄。

**「zero candidate-matched」claim — CORRECT 但需精確措辭**: grid_trading|ETHUSDT|Buy 有 124 historical fills（context_id 100%、entry_context_id 77/77 close-fills 全 join decision_features、order_id 124/124），span 2026-04-14→**2026-06-19**（之後零，符合 P0 blocked）。scorecard `candidate_matched_order_count=0` 指的是 **current-head 授權 bounded-probe shadow-placement 執行 lineage**（從沒跑），非 fill↔signal plumbing 缺陷（plumbing 完好）。歷史 grid-ETH demo fills 屬 proof-excluded（cleanup/risk-close/pre-lock）。entry_context_id health 已修：close-fills NULL entry_ctx last30d=0（V083+backfill cron 修好 38% 問題）。

**Min work to microstructure-grade (both A+B)**: 已在位只缺接線=(1) maker markout mid_at_submit 覆蓋（open-maker 也記 mid 基準，非只 close-maker）；缺=(2) per-fill forward-markout@1/5/30s enrichment job（JOIN fills×l1_events 事後回填，新欄或 sidecar 表）；(3) fill-time queue-context snapshot（best_bid/ask/size@submit 存入 fill 或 sidecar，免事後 JOIN 259M 表）；(4) candidate-matched execution-evidence 表（bounded-probe order→fill→fee→slippage→l1-context 綁 candidate_id，P0 substrate）。(A) 純離線可即跑 fill_sim（無需授權）；(B) 需 P0 unblock 授權 bounded Demo execution 才有 own-candidate outcome。

**Report**: returned inline to PM（no .md per contract）。
