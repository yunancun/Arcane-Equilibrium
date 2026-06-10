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
