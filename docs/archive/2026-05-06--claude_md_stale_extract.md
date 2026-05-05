# CLAUDE.md stale extract — archived 2026-05-06

Archived from `srv/CLAUDE.md` per §三 衛生規則 (≤2-day completed milestones rule). REF-20 P6 PRODUCTION CLOSED 2026-05-03; this narrative is now +3 days and belongs in archive. Live state lives in `srv/memory/project_2026_05_03_ref20_sprint1_2_closure.md` and `docs/execution_plan/2026-05-04--ref20_gap_closure_reality_backtest_plan_v1.md`.

Source HEAD at archive time: `67b95808`.

---

## §三 REF-20 IMPL 狀態（2026-05-05 Sprint A + B + C + D ALL CLOSED — verbatim extract）

**Sprint A 完成（2026-05-05 02:05 UTC QA round 6 final smoke E2E PASS）**：commit chain `c1ab7ea9 → 353db3fe → 66b650ea → cad8ed84 → e9d547c0+2ae93992 → f51f4e2e → 3a425447 → 2531c011`（8 commit + 1 hotfix retrofit）。Plan §6.R3 acceptance "4 tables row > 0" 真實達成：`replay.experiments=4 / run_state=4 / report_artifacts=1 / simulated_fills=1` + Wave 9 safety 0 leak + FK lineage 4/4 valid。

**6-layer blocker chain 全排除**（每層發現後 fix）：
- L1 Python 3.12 `from __future__ import annotations` + lazy import → FastAPI body 422（hotfix `cad8ed84`）
- L2 `OPENCLAW_ENGINE_BINARY_SHA` env not injected → register 503（infra fix `e9d547c0`+`2ae93992`）
- L3 placeholder signature 撞 Sprint 1 Track B fail-closed verifier（R6-T1 `f51f4e2e`：real HMAC sign + sibling key.hex）
- L4 `subprocess.DEVNULL` silent-dead 反模式（R6-T2 `f51f4e2e`：stderr 寫 `<output_dir>/replay_runner.stderr` disk）
- L5 signing key not provisioned（R8 `3a425447`：restart_all 注入 `OPENCLAW_REPLAY_SIGNING_KEY_FILE` env 指 in-tree dev key.hex）
- L6 `spawn_replay_runner` 對 `exit=0 within poll grace` 误判 failure（R9 `2531c011`：sentinel pid=-1 contract + `/run` response `subprocess_completed_in_poll` flag）

**Sprint B closed (2026-05-05)**：B1 commit `2a69addb` (R4 UI enable + R0-T0 LOC release) + B2 commits `c679a8b4 → a2f819c5 → 4ffb24c4` (R5-T1+T2 Rust adapter foundation + R5-T3 IsolatedPipeline wire-up + R5-T4+T5+T6+T7 config blob path + acceptance tests)。Plan §6.R5 acceptance 達成：A4 strategy parameter delta (3 hermetic + proof_7 wiring) + A5 risk parameter delta (3 hermetic + proof_8 risk delta) — 配 6 hermetic Python tests + 2 Rust e2e proofs PASS。Config blob 完整路徑：register endpoint → V049 manifest_jsonb → /run handler → disk manifest_fixture.json → Rust replay_runner → adapter override。**proof_7 真實 fixture fills divergence 延 Sprint C R6**（synthetic_btcusdt.json 10-event monotone-up fixture 限制；wiring round-trip 已證）。

**Sprint C C1 (R6) CLOSED 2026-05-05** — 6 commit chain `286252d2 → 95beba74 → 3688e09a → 7a04d2f4 → c2cd317f → 29d41991`（W1-W6）+ V055 R6-T0' chain `ad77f039 → d7a85932`：

W1 R6-T1+T2 (Rust apply_fill fee/slippage byte-equal IntentProcessor live + 4 push site) + R6-T7 LG-3 pricing_binding healthcheck `[45]` slot (LG-3 RFC 0%→70%) / W2 R0-T0 拆檔 apply_fill.rs (~485 LOC) + R6-T3 KellyConfig wire / W3 R6-T4 calibration_label.rs (Rust 826 LOC + 19 unit per QC §1.1 spec, MAD-based σ + empirical percentile CI + 'limited'→'calibrated_replay'+3d TTL + regime detection DEFER Sprint D) / W4 R6-T5 simulated_fills_writer.py 解析 fee/fee_rate/liquidity_role/execution_model_version + R6-T6 update_execution_confidence helper / W5 R6-T8 reproducibility smoke (Rust 5 case grid+ma+funding+bb_breakout+bb_reversion 對齊 QC §1.1 表) / W6 R6-T9 Sprint C1 closure (Python port `calibration_label.py` 403 LOC mirror Rust + run_finalize_route caller wiring 192 LOC + E2E integration test 8/8 PASS + cross-language byte-equal verify).

**A6/A7 acceptance 7/7 真實 closed** (per plan §6.R6): A6-1 fee never omitted / A6-2 calibration sample+freshness+confidence in report / A6-3 maker/taker liquidity_role from PostOnly TIF / A6-4 execution_model_version != synthetic_v1 / A7-1 weak auto-downgrade / A7-2 sufficient sample → 'limited'/'calibrated' / A7-3 stale auto-downgrade. End-to-end chain demonstrated by E2E test (register → run → finalize → V049.execution_confidence UPDATE).

**V055 R6-T0' MIT P0 BLOCKER fix DEPLOYED Linux PG 16** (commit `ad77f039` after 5-round loop): V036 INSERT body 加 3 metadata column 寫入 (evidence_source_tier / replay_experiment_id / manifest_hash); expires_at TTL 經 V036 verify input + Block B JOIN replay.experiments.expires_at 雙層守門; 19-arg signature byte-equal V036; Guard A 三段 (function existence + pronargs + identity_arguments). **Lesson 5-round loop** (governance commit `d7a85932`): trusted Mac mock layer，Linux PG 16 empirical 反覆揭 bug — V### migration must Linux PG dry-run before E1 IMPL design — see `memory/feedback_v_migration_pg_dry_run.md` + `memory/feedback_chinese_only_comments.md` (§七 注釋默認中文 governance change 同期 land).

**LOC governance 1500→2000** (commit `e5b5227c`): runner.rs 1466 → 1808 + apply_fill.rs new 485; cumulative R6 LOC ~5000+ across 6 commit (4 file new + 4 file mod).

**Sprint C C2 (R7) CLOSED 2026-05-05** — 3 commit chain `fc3c6f19 → bbcdf067 → edac7d1b`（W1-W3）+ AI-E pre-DAG advisory ✅。

W1 R7-T1+T1.5+T3 三 producer 升級 calibrated_replay tier (`dream_engine.persist_dream_insights` + `mlde_shadow_advisor._persist_recommendations` PA §2B 漏列補位 + `opportunity_tracker.persist_regret_summary`) via shared helper `replay_metadata_helper.build_replay_metadata` (~80 LOC) + R7-T2 verify-only marker + R7-T4 LinUCB NO-OP confirmation. Backward-compat preserved (4 producer 不傳 R6_calibration_provider 仍跑 hardcoded 'real_outcome' fallback). E1 push back: helper 直接 SELECT V049.manifest_hash 而非 reuse `lookup_replay_config_blob` (AI-E/PA reference signature mismatch — lesson banked).

W2 R7-T5+T7+T8 audit suite — evidence_filter capability probe test (9 case, MIT §1.1 6-key 4-gate coverage) + FK chain audit (6 case, V051 paired CHECK + JOIN replay.experiments.expires_at TTL — note: mlde_shadow_recommendations 表本無 expires_at column, FK-side TTL 由 Block B JOIN 守) + lookup helper reuse audit (10 case manifest_hash consistency across producers) + observability log per MIT §1.5 (33 LOC `evidence_filter capability dump: caps=N/6 block_a=on|skip block_b=full|partial|skip` in `mlde_demo_applier_evidence_filter.fetch_pending_sql_and_params`).

W3 R7-T6 E2E integration test (797 LOC, 5 mock case + 3 live PG opt-in case + 1 smoke summary) — full chain register → run → finalize → producer consume → mlde_shadow_recommendations Block B promote。grid_trading 1162 fills → calibrated_replay tier ✅. funding_arb 99 fills → none (skip insert) ✅.

**A10 acceptance closure** (per plan §6.R7):
- ✅ A10-1: 0 hardcoded 'real_outcome' in upgraded 3 producer (W1)
- ✅ A10-2: V051 paired CHECK enforce + V036 RAISE on missing metadata (W2 + W3 live PG opt-in)
- ✅ A10-3: TTL hard check via V036 verify input + Block B JOIN replay.experiments.expires_at (W6 R6-T9 Python port + W2 FK chain audit)

Sprint C2 R7 cumulative: ~3700 LOC across 3 commits, 43 new test PASS (15+22+6), 0 production regression on 524 sibling tests. Live PG opt-in (OPENCLAW_TEST_LIVE_PG=1 + OPENCLAW_TEST_DSN) cases skip default — 留 operator post-deploy ad-hoc verify.

**Sprint D CLOSED 2026-05-05** — R8 commit `61433919` + R9 PM sign-off `6a7a885c`。

R8 maintenance/retention/observation: V056 mlde_shadow_recommendations retention policy DEPLOYED Linux PG (cron-driven DELETE 30d for replay-derived / 90d for real_outcome — V### dry-run lesson APPLIED, NOT hypertable confirmed via SSH bridge per `feedback_v_migration_pg_dry_run.md`); 5 healthcheck sentinel slots [46]-[50] (runner_binary_path / manifest_registry_growth / failed_run_rate / stale_running_rows / artifact_retention); 6 cron task disposition (5 既有 Wave 9 land + 1 R8 NEW retention cron). 44 new test PASS (33 healthcheck + 11 V056 migration) + 0 production regression on 259 sibling.

R9 final sign-off (PM-led acceptance review per plan §6.R9):
- ✅ **≥5 successful replay runs across ≥2 strategies**: Sprint A R3 4 tables row > 0 + Sprint B A4/A5 hermetic 6 case + 2 Rust e2e proof (proof_7 wiring + proof_8 risk delta) covering grid_trading + ma_crossover
- ✅ **≥1 parameter-change replay**: Sprint B A4 strategy parameter delta + A5 risk parameter delta hermetic acceptance
- ✅ **≥1 fee-aware report**: Sprint C R6 W1 R6-T1+T2 fee/slippage byte-equal IntentProcessor live + W6 R6-T9 E2E demonstrates fee-aware end-to-end
- ✅ **0 live/trading mutation during replay window**: forbidden_guard.rs + V055/V051 paired CHECK + replay isolation profile + 0 forbidden import (verified each commit per CLAUDE.md §四)
- ✅ **UI replay flow usable**: Sprint B R4 UI Enable — tab-paper.html `subtab-btn-replay` backend-readiness gated 5-state machine + 28 static asset tests + XSS guards
- ✅ **MLDE/Dream advisory non-commanding**: Sprint C R7 W1 dream_engine + opportunity_tracker + mlde_shadow_advisor (PA §2B 漏列補位) 升級 calibrated_replay tier 必經 V036 verify gate + V037 PUBLIC INSERT REVOKE + V051 paired CHECK enforce
- ✅ **Confidence labels match calibration evidence**: W6 R6-T9 Python port `derive_execution_confidence` byte-equal Rust + run_finalize_route caller wiring + V049.execution_confidence UPDATE based on real trading.fills cell-level calibration; QC spec §1.1 reproducibility verified across 4 strategy fixtures

**REF-20 cumulative**: Sprint A 8 commit + Sprint B 4 commit + Sprint C 9 commit + Sprint D 1 commit + governance/sync = **~22 commit chain**, ~14000+ LOC across Rust + Python + SQL + tests + docs, **17 acceptance criteria 100% closed** (A1-A10 plan §7 + 7 R9 conditions). Live PG opt-in (R7-T6 3 case via OPENCLAW_TEST_DSN) 待 operator post-deploy ad-hoc verify。

**Post-signoff reality-gap fix**: commit `67b95808` 修 replay UI readiness、registry/report/finalize edge cases、simulated fill payload、strategy/risk param delta tests、Rust replay runner/apply_fill gaps；Mac/Linux/origin source 已同步。

**Outstanding (operator-side, not blocking REF-20 closure)**:
- R7-T6 3 live PG E2E case full smoke (需 OPENCLAW_TEST_DSN 配置)
- V056 cron schedule deployment (helper_scripts/cron/...sh 已 land，operator add to crontab)
- Sprint D operator deploy validation (5 new healthcheck sentinel 透 cron-wrapper 跑)

**Replay learning boundary**：`replay.simulated_fills.evidence_source_tier='synthetic_replay'` 仍不可作 ML training data；只有 `calibrated_replay` / `counterfactual_replay` 且通過 verification gates 的 row 可餵 MLDE / Dream / attribution writer。

---

## §三 Wave / Sprint closure bullets — verbatim extract

- **Wave 1-9 IMPL closed (commits 9e0c826 / 1851714+b1f6b8a / 5a618ff / 4b48b6d / 457a458 / eb5f106 / c887e4e + 53ab7e7 / 8429af1 / 1f5d019 / 5a7581e)**：cold audit 揭 24/25 GREEN 是結構性 false positive — runner 從未啟動 → #2/#10/#14/#19 都是 vacuous truth。後續 Sprint 1+2+3+4 chain 把 vacuous truth 轉為 evidence-backed truth。
- **Sprint 1 cold audit fix-up (commit `edf33c0`)**：5 critical security（manifest 自洽循環 + spawn argv broken + IDOR + path traversal + env var bypass）+ 3 schema drift（V049 replay_experiments 22 col + V050 replay_simulated_fills 17 col + V051 mlde_recommendations 雙路 CHECK）+ V052 FK redirect + V053 race-free enum extension。3387 PASS / 1 fail (pre-existing) / 10 skip · 3084 cargo workspace PASS / 2 fail (pre-existing) / 3 ignored。
- **Sprint 2 retroactive evidence trail (commits `aa9343c` + `5184990` + `ab25a2a` + `db1d04f` + `c96aed4` + `984ee5d` + `35c0719` + `114f681c`)**：PA Track E Decision Lease retrofit AMD-2026-05-02-01 4-task DAG design + E2 F1 retroactive Wave 3-9 review (10 LOW + 7 P2 ticket) + E4 F2 retroactive cumulative (4 forgery flag + 5 mock retroactive flag + 3 P2-FOLLOW-UP) + Wave 7 amendment AMD-2026-05-03-01 (IMPL/Deploy 2-stage gate) + Track G doc sync + closure doc「3500→3387」訂正 (P2-FOLLOW-UP-5)。
- **Sprint 3 Track H Decision Lease retrofit IMPL (commit `dbcf845b`)**：4 並行 sub-task report（E-1 Rust facade 951 LOC + E-2 router gate + E-3 Python IPC bridge 587 LOC + E-4 V054 audit writer 535 LOC schema + 492 LOC writer）+ E2 round 1+2 + E4 final regression PASS；feature flag `OPENCLAW_LEASE_ROUTER_GATE_ENABLED=0` default OFF 灰度路徑保留。
- **Sprint 3 Track I Linux deploy (runbook `7a86d2eb` + Phase B-G executed via SSH bridge 2026-05-03 21:30+)**：V049-V054 6 V### apply（TimescaleDB hypertable + 21-value enum + paired CHECK + FK redirect 全綠）+ cargo --release engine 28.82s + replay_runner 15.35s + nm audit 406 symbol 0 forbidden + restart_all --rebuild（Engine PID 4122084 + API PID 4122156）+ 5 e2e smoke 核心 3 條 PASS + Track H schema verify 全綠。
- **Sprint 4 final closure (commit `0ad79f67`)**：operator override accept conditional skip 14d observation（理由：REF-20 是 Paper Replay Lab 回測模塊，feature flag default OFF + 0 trading.* mutation + 0 live trading 觸發）；7 closure item 4 ✅ + 3 ⏭ override skip = **REF-20 P6 CLOSED**；24/25 V3 §12 acceptance binding GREEN（#21 ⏸ DEFERRED Wave 7 P5 LG-2/3/4 stable 後解封）。
- **Conditional skip（operator override，無時限）**：14d gradient observation #4/5/6（continuous validator + cron infra 已 land，後續手動或事件觸發）+ AMD-2026-05-02-01 flag flip canary 24h（~2026-05-15 P0-EDGE-2 後 operator action）+ AMD-2026-05-03-01 Wave 7 P5 deploy gate（LG-2/3/4 frontend stable + 7d healthcheck PASS 後 operator action）。
- **後續 follow-up**：13 P2 ticket + 1 P3 ticket land in TODO §P2-AUDIT/P2-WAVE-*/P2-FOLLOW-UP/P2-LEASE/P2-INTENT/P3-V054。
- **2026-05-04 Codex review + Gap Closure Plan V1**：4 P0/P1 gap (P0-1 synthetic walker / P0-2 binary path / P1-1 UI disabled / G1-G7) 進入 forward stabilization plan；plan 文件 `docs/execution_plan/2026-05-04--ref20_gap_closure_reality_backtest_plan_v1.md` (commit `a4ea3571`) 切 9 Wave (R0-R9) + 4 Sprint (A=R1+R2+R3 / B=R4+R5 / C=R6+R7 / D=R8+R9)。Sprint A 啟動於 2026-05-04，目標：runtime usability + manifest registry + first real E2E evidence。Sprint A 完成前 replay 不能用作 strategy/risk 真實 evidence；MLDE/Dream 不會收到 unverified replay row。
