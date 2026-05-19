# TODO v55 翻譯與歸檔快照 — 2026-05-19

**來源**: `srv/TODO.md` v55（翻譯前快照）
**目的**: 保存被精簡掉的 ✅ DONE / carry-forward 細節，活躍佇列改寫為精簡中文版。所有原 commit hash / file path / 函式名 / 治理决议均原樣保留。

本檔不取代既有的：
- `docs/archive/2026-05-15--todo_v21_completion_cleanup_archive.md`
- `docs/archive/2026-05-15--todo_v24_stale_rows_archive.md`
- `docs/archive/2026-05-16--todo_v36_completion_cleanup_archive.md`
- `docs/archive/2026-05-16--close_maker_first_phase_1b_round1_archive.md`
- `docs/archive/2026-05-16--stage1_demo_a4c_tombstone_cleanup.md`

只補錄 v36 之後（v37-v55）累積在 TODO banner 與正文中的 carry-forward 細節。

---

## 一、v55 Banner 全文（原文保留）

> 原 TODO.md L1-L67 banner 段落、carry-forward 鏈、報告檔指引列表。內容極長（單行近 5000 字），純歷史記錄性質。

### v55 — 4-track parallel closure（2026-05-19）

operator-authorized 4 surfaces all done（#5 watchdog RCA / #6 entry-path RCA / #7 tab-live extract / #9 stress fails RCA + #12 E1 R2 fix）。

Commit chain：
- `9bf4fd62`：tab-live.html 2171→543 LOC + 新 tab-live.js 1645 LOC（純 cut-paste，`?v=20260519.tab-live-extract`）
- `c1f47722`：stress_integration.rs +65 LOC 2 helper fix；`070ff0a3` INNOCENT，真正肇事者 `6cdfe0dc`（bb_reversion）+ `7a07348b`（bb_breakout）；35/35 PASS
- `d927bf7f`：QA watchdog RCA report

**QC P2-ENTRY-PATH critical reframe**：昨日 QA「entry-close vs risk-exit by ID prefix」拆法是結構性人為造成的；兩者都走同一條 `execute_position_close()` 路径；`oc_close_mf_fb_*` = maker timeout fallback / `oc_risk_*` = maker success；**真實是 6 maker attempts / 3 fills = 50% Wilson CI [18.8%, 81.2%]，sim 70.8% 落在 CI 內**，所以是 21pp 偏差而非 70pp gap。H5 sample noise HIGH + H3 BBO-cross-proxy 樂觀 MEDIUM-HIGH，H4 path 不對稱 REJECTED。**Sample velocity ~0.44 grid_close/hr → T+72h n≈24 不夠 30，首個 defensible verdict 推到 T+96h~T+120h（2026-05-22~23 UTC）**。

**6 new backlog tickets**：
- P1-WATCHDOG-EXIT-CODE-CLARIFY（sys.exit(2)→20）
- FA-WATCHDOG-3STRIKE-ESCALATION-POLICY
- P2-QA-TEMPLATE-CLOSE-MAKER-SPLIT-FIX（按 attempt×fallback 切非 ID prefix）
- P2-SIM-QUEUE-AWARE-ADJUSTMENT（replay 10-15pp bias 修正）
- P2-STRESS-BB-BREAKOUT-FALSE-SQUEEZE-COINCIDENTAL-PASS（3rd 測試因錯誤原因 PASS）

**Governance flags**：cargo test --lib 不覆蓋 tests/ integration crate；建議 sign-off SOP 加 `cargo test -p openclaw_engine --release`（no --lib）。stress_integration suite 35/35 PASS / cargo lib 2999/0/1 unchanged / node --check + HTML parse 全 GREEN。

### v54 carry-forward — runtime/admin closure

operator-authorized V096 Linux PG apply/register DONE，P1 cron install wave DONE on trade-core；`[75]` first-fire PASS；`[76]-[79]` expected WARN until natural first schedules。

`P1-WATCHDOG-STATUS2-RCA` CLOSED as DNS/HTTP transport outage misclassified as `ENGINE_CRASH`（no OOM/panic，current engine/watchdog alive）。`P2-ENTRY-PATH-0PCT-MAKER-FILL-RCA` CLOSED with entry_close 6/6 attempts 0/6 maker vs risk_exit 3/3 maker，path-specific not global PostOnly failure。Calibration output classified generated and ignored，reports tracked。No V095，engine restart，allLiquidation revival，risk_config，或 runtime env mutation。

### v53 carry-forward — sprint closure

operator-authorized 4 parallel tracks all CLOSED。

Commit chain：
- `4e045c2f`：P2-ORDERS-INTENT-ID-WRITER-GAP-1 Rust intent_id end-to-end plumb +5 regression tests
- `ae71575e`：P2-COMMON-JS-LOC common.js 2198→4 files split + 19-file cache-bust uniform `?v=20260519.split-p2`（E2 HIGH catch 後修）
- `3584fb17`：P3 hygiene 4-item + QA Phase 1b 24h AC-A INSUFFICIENT_SAMPLE verdict

**QA Phase 1b**：n=8 attempt_pct Wilson CI [40.9%, 92.9%] passes 25% AC-A floor + 3 real maker fills @ fee 0.0002 vs taker 0.00055；0 rollback trigger；**Phase 2a 14d clock STAYS @ 2026-05-18 13:50 UTC**（5 evidence: binary mtime / TOML / no --rebuild / spec silent on process restart / fill velocity consistent）；engine 01:57:19 UTC autonomous watchdog respawn（9th occurrence in 7d → 新 `P1-WATCHDOG-STATUS2-RCA` ticket）。

**Re-verify AC-A T+72h = 2026-05-21 13:50 UTC**（~32 fills first n≥30 verdict window）。

**2 new follow-up tickets**：`P1-WATCHDOG-STATUS2-RCA` + `P2-ENTRY-PATH-0PCT-MAKER-FILL-RCA`（sim 70.8% vs real entry 0% = 70pp gap）。

**P2-TAB-LIVE-LOC DEFERRED**（no Jinja2；ticket `P2-TAB-LIVE-JS-EXTRACT` tracks future inline-script extract）。

E2 verdict：PASS-after-fix（1 HIGH cache-bust drift caught + fixed inline by PM；1 MEDIUM weak test + 2 LOW paper-shadow alloc + common.js 815 attention-threshold 全 advisory non-blocking）。E4：cargo engine 2998/0/1（+5 new regression）/ pytest targeted 76/0 / wider 421/3 = v51 baseline identical 0 regression。

### v52 carry-forward — P2-WP05-FUP-1 final 9/9 closure

PM-as-Conductor APPROVE Option A（E1 memo §4 推薦）→ E1 round 2 `risk_routes.py` `_ipc_failure(reason_code, *, log_detail=None)` 簽名升級 + 9 caller rewrite（`ipc_<op>_failed` / `ipc_patch_risk_config_not_ok`）+ 中文 docstring + `logger.warning("ipc failure: %s | %s", ...)` → E2 APPROVE 0 finding（6 視角 + §3.10 caller proof 0 external + GUI strict-match 0 hit + `result!r` PII risk verified IPC payload `{ok, config, version, source}` 0 sensitive field）→ E4 421/3 wider batch identical to v51 baseline（3 pre-existing test-ordering pollution，0 regression）。

**P2-WP05-FUP-1 final state：32/32 sites all closed**。

### v51 carry-forward — cleanup sprint closure

operator-authorized 2 P1 + 11 P2 maintenance batch CLOSED via PM+Conductor 4-batch dispatch + E2 PASS + E4 PASS + 5 commits（`c3524da2` / `449f628b` / `428f1505` / `7bb994c3` / `eda460e8`）。

**Done（12/13）**：
- `P1-EDGE-P2-3-PH1B-ML-INVARIANT`（pr-adversarial-review §3.11）
- `P2-PORTFOLIO-RESTING-{TEST-COVERAGE / ROUTER-CACHE / DOCSTRING-CLEANUP / E5-BENCH / REPLAY-PARALLEL}`
- `P2-PERCEPTION-DEPRECATE-1`（DeprecationWarning + 3 test files filterwarnings）
- `P2-STOCHASTIC-LEAK`（`stochastic_prior` variant + 5-indicator audit）
- `P2-DEAD-RUST-CLEANUP-1`（−3616 LOC across 7 openclaw_core modules per ADR-0015）
- `P2-DEAD-SCHEMA-DROP-1`（V096 RESTRICT + Guard A/B source/test，Linux apply gated）
- `P2-WP05-CSP-UNSAFE-INLINE`（SRI sha384 on unpkg lightweight-charts@4.1.0）
- `P1-CRON-INSTALL-WAVE-1`（5 wrapper touch-at-start + 5 healthchecks [75..79] source/test，crontab install gated）

**Partial（1/13）**：`P2-WP05-FUP-1` 23/32 sites cleaned across 8 files；9 risk_routes.py sites HIT signature blocker → memo `docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-18--p2_wp05_fup1_signature_blocker.md` Option A/B/C for PA Round 2。

**Net LOC**：−3554。**Regression**：cargo engine 2993/0/1 / core 357/0 / pytest 22+42+107 PASS（V096 + cron heartbeat + 3 perception）+ 8-file batch 421/3（3 pre-existing identical）；2 cargo engine integration stress fails（bb_breakout/bb_reversion）confirmed pre-existing on clean main `8d2b2866` NOT PR-introduced。

**Operator gates remain**：V096 Linux PG apply + crontab install on trade-core（separate deploy step）。

### v50 carry-forward — W-AUDIT-8c Stage 0R replay tooling

3 worktree（S0R-1 SQL / S0R-2 metrics / S0R-3 CLI）MERGED to main HEAD `a182e155` after 12 sub-agent multi-round adversarial chain。

Chain：PA Stage 0R packet design v1.0 → BB STRUCTURAL verdict（long-liq skew = mainnet microstructure，not demo bias，0 day delay）→ PA HIGH-2 boundary leak arbitration（verdict D open-only not mid）→ E1 × 3 round 1（S0R-1 `bd1b2443` + S0R-2 `c041097c` + S0R-3 `b3e68870`）→ E2 × 3 round 1 RETURN（S0R-1 2 CRIT + S0R-2 3 CRIT + S0R-3 6 CRIT runtime + silent-RED killer）+ MIT round 1 APPROVE-CONDITIONAL → E1 × 3 round 2（S0R-1 `381d89a0` + S0R-2 `6cc2b7fb` + S0R-3 `1888ecee`）→ E2 × 3 round 2（S0R-1 + S0R-2 APPROVE，S0R-3 RETURN 4 NEW + smoke misreport governance event）+ MIT round 2 APPROVE Linux PG dry-run x2 byte-equivalent + n_eff cluster-aware retrofit verified → E1 round 3（S0R-3 `a2dc1be8` + `6638d678` honesty disclosure section + 11/11 actual smoke PASS）→ E2 round 3 APPROVE（independent smoke 11/11 verified，honesty disclosure genuine）→ E4 regression 5 phases 0 W-AUDIT-8c regression（helper_scripts 654 PASS + S0R-2 34/34 + S0R-3 post-merge 11/11 + program_code baseline + cargo 2992）→ QA + PM merge integration `w-audit-8c-stage0r-int` → main `f8cb076f` → governance trail commits（`00358320` 12 sub-agent reports + `0e2d1fa0` feedback_pnl_priority_over_governance memory + `a182e155` QA Phase 1b T+24h Phase 1 prep）→ 三端同步（Mac local / origin/main / Linux trade-core all on `a182e155`）。

### v49 dispatch-state sync — Phase 1b parameter calibration closure

v48 `P0-PHASE-1B-PARAM-CALIBRATION-1` 全 6 step chain CLOSED including deploy。

Chain：PA spec v0.1（`75e29265`）→ E1 harness IMPL 12 files / 2781 LOC（`93069c29`）→ E2 APPROVE-CONDITIONAL 0 MUST / 3 SHOULD → E4 PASS 7/7 → Merge（`8d8a0123`）→ PA SHOULD-FIX memo（`5df39d13`，3 accept-with-caveat 0 IMPL fix）→ Spec v0.2 patch（`34af2d2e`）→ SQL fix（`d2286c05`）→ Sweep 81 cells（1.4 sec wall）→ PA cell selection report（`2b65d3f1`，78 unique cells / 35 INDETERMINATE / 43 TRUE FAIL / top `G-AB-01-C90` fill 70.8% / +3.37 bps）→ E1 Rust 14 LOC `timeout 30s → 90s`（`820f0532`）→ E2 light APPROVE-CONDITIONAL → E4 PASS 7/7（`4cc32ff6`）→ Merge（`67f1a047`）→ operator-authorized rebuild + restart（engine PID 1253085 → **1506208**，binary mtime 2026-05-18 13:50 UTC）。

**Phase 2a 14d observation clock reset @ 13:50 UTC**；24h AC-A SQL verification target ~2026-05-19 13:50 UTC。

### v48 carry-forward — 第三方評估 + PG verify

2026-05-18 ~10:30 UTC：third-party assessment + own PG verify revealed Phase 1b 12H post-restart sample = **4 close fills，100% `close_maker_attempt=TRUE` BUT 100% `close_maker_fallback_reason=timeout_taker`** → real fee saving = 0% so far（maker offset_bps=0.5 + buffer_ticks=1 + timeout 30s/15s too tight for sparse alt-coin spreads）。

Operator scheduled **P0 Phase 1b parameter calibration sweep + replay counterfactual** for AFTER 12H test window closes（~2026-05-18 11:54 UTC）。Pre-calibration code path is verified correct（TOML activator + maker_attempt instrumentation working）；root cause is parameter tuning，NOT IMPL bug。

### v47 carry-forward — W-AUDIT-8a Wave 1 merge state

W-AUDIT-8a Wave 1（B-REM-1 `49975eeb` / B-REM-5 `5997dd43` + ADR-0023 `1b614daf` / C1-LIQ-WRITER `7ab6c22d` + healthcheck `[67]` `d8938a78`）merged via `ef0dfc6e` / `5aeae75c` / `25413e96`。

EDGE-P2-3 Phase 1b runtime activator deploy chain remains CLOSED 2026-05-17 23:54（engine PID 1143103，`runtime.use_maker_close=true`）。W-AUDIT-8b Round 2 RED_FINAL tombstoned via spec v0.4（`ef7ea6c2`）+ AMD v0.7（`71f2283b`）。Wave 2（`C2-ORDERFLOW` 5pd HIGH + `C3-SPREAD` + `D-CONTRACT-LOCK` 2pd PA-only）deferred to Sprint N+4。Previous v46 production `allLiquidation*` writer revival（`0e8a8ae8` / `bedc40c3`）remains CLOSED。

### v46 production liquidation revival（2026-05-17）

✅ SOURCE/TEST + RUNTIME DEPLOY DONE 2026-05-17；`0e8a8ae8` revives only C1-approved `allLiquidation.{symbol}` in startup and scanner dynamic production builders while legacy `liquidation.` / `price-limit.` / `adl-notice.` remain excluded；`bedc40c3` fixes runtime log observability（`topics_per_symbol=8`，`all_liquidation_enabled=true`）；local + Linux release lib both green `2969/0/1`；trade-core engine-only rebuild/restart completed with PID `1066422`；post-healthcheck: `OPENCLAW_AUTO_MIGRATE=0`，`OPENCLAW_ENABLE_PAPER=0`，V094/V095 still registered，`market.liquidations` PK `(symbol, ts, side, qty, price)`，public WS subscribed `200` topics / `20` batches，no handler/rate-limit/topic-poison errors，and 3 real liquidation rows landed。Paper remains disabled via `pipeline_snapshot_paper.json disabled=true`（`OPENCLAW_ENABLE_PAPER != 1`）。PM 整合報告：`docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-17--deploy_readiness_consolidated_audit.md`。

### v45 deploy-readiness runtime closure（2026-05-17）

✅ V094/V095 + Phase 1b engine restart DONE 2026-05-17；`b867e452` restored Linux cargo baseline to `2969/0/1`；V094 registered with checksum `d7db4e674cc0505da787861b6777717059d69902137057350a3b4b0a5e527a41a1e7b7e3cb559ba2fb8a4dd3fead2512`；V095 registered with checksum `e25f110594587cddafd1e08f7699da593fe63c64af6d26415356c00b4534d8f60f0e67d7640ab8a6b18ba6ba742ca15b`；`market.liquidations` PK is now `(symbol, ts, side, qty, price)`；Phase 1b engine-only rebuild/restart completed at commit `74f88269` before V095 docs sync；`OPENCLAW_AUTO_MIGRATE=0` and `OPENCLAW_ENABLE_PAPER=0` remained unchanged。

### v44 W-AUDIT-8c correction closure（2026-05-17）

✅ SOURCE/TEST + V095 LINUX APPLY + PRODUCTION WRITER REVIVAL DONE 2026-05-17；V095 source migration preserves liquidation item identity with `(symbol, ts, side, qty, price)`；parser/writer fail closed for invalid `allLiquidation` rows；corrected Bybit side mapping（`Buy` long liquidation / `Sell` short liquidation）is tested；V095 Linux PG transaction dry-run x2 PASS + MIT idempotency re-sign APPROVE-CONDITIONAL；V095 manual apply/register DONE in v45；production `allLiquidation.{symbol}` subscription/writer revival DONE in v46 after explicit authorization。PM report：`docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-17--w_audit_8c_correction_source_test_closure.md`；dry-run evidence：`docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-17--v095_linux_pg_dry_run_result.md`；MIT re-sign：`docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-17--w_audit_8c_v095_mit_resign.md`。

### v43 Option A source/test closure（2026-05-16）

✅ DONE 2026-05-16；`a6e17d5d` adds W-AUDIT-8b v0.3 4-cell sweep tooling with A3/E2/E4 approval；`ea4ceca6` lands Phase 1b close-maker-first source/test bundle with Worktree B dispatch，V094 audit writer，fallback terminalization，and healthchecks。No deploy / production SQL migration / runtime restart / auth mutation / paper/live/mainnet enablement。PM report：`docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-16--option_a_phase1b_w_audit8b_impl_closure.md`。

### v42 role profile/memory hygiene（2026-05-16）

✅ DONE 2026-05-16；新增 `docs/agents/role-profile-memory-standard.md`，所有 `docs/CCAgentWorkSpace/*/profile.md` 接入共同角色契約，所有 `memory.md` 頂部加 historical-memory 解讀契約；A3/E3/E4/E5/QA/PM 等 profile 去除「當前狀態即真相」歧義，改為 historical baseline + `TODO.md`/latest report/runtime evidence 為準。歷史 memory 正文未刪除。

### v41 agent-settings refresh（2026-05-16）

✅ DONE 2026-05-16；all Claude/Codex agent role files now preload operating memory + `README.md` + `docs/agents/context-loading.md`，route active state to `TODO.md`，and no longer depend on stale numbered-memory sections，11-tab，bilingual-comment，or 1200-line assumptions。Codex role index and agent-facing skills/profiles were aligned。

### v35 rebuild + restart（2026-05-16）

trade-core engine PID 69581 / API PID 69674；Wave 2-4 Rust source IMPL all deployed；runtime env at 2026-05-16 01:00 UTC had `OPENCLAW_AGENT_SPINE_RUNTIME_MODE=shadow`，`OPENCLAW_LEASE_ROUTER_GATE_ENABLED=1`，`OPENCLAW_ENABLE_PAPER=0`，`OPENCLAW_BASE_DIR=/home/ncyu/BybitOpenClaw/srv`。

### Round 4 三角 cross-validation（PA + FA + CC，2026-05-16）

一致 verdict A/C/A for 3 P0 → operator 確認同意。

### Wave 1-4 全 closed

- WP-01/02/05/09（Wave 1）+ WP-03/04/07/10/BB-MF-3（Wave 2）+ WP-06/08/13/WP-13-leftover（Wave 3）+ WP-11 Phase 1（Wave 4）；WP-12 DEFERRED by design。

### 2026-05-16 完成的 P0 items

- **P0-1 WP-04 $2 RATIFY**：✅ DONE 2026-05-16 commit `e24c1d8f`；operator ack at `docs/CCAgentWorkSpace/Operator/2026-05-16--wp04_budget_ratification.md`；governance debt cleared。
- **P0-2 WP-03 OU sigma deploy-gate**：✅ Option C selected；PA spec `docs/execution_plan/2026-05-16--wp03_ou_sigma_deploy_gate_spec.md`（~600 LOC）+ `[69]` healthcheck design land；revert flag 三層 trigger logic（12h/24h/7d）；Operator notification ADR-0020 manual-only。`P1-WP03-DEPLOY-GATE-IMPL` ✅ DONE 2026-05-16 commit `d6ff77f7`：`checks_wp03_deploy_gate.py` 587 LOC + test 528→592 LOC（18/18 PASS）+ runner.py wire `[69]` + `__init__.py` re-export；完整工作鏈 E1→E2 RETURN→E1 round 2→E2 APPROVE（MEDIUM-1 ZERO_FILLS false-positive secondary guard 修 + LOW-1 REQUIRED escalation msg 加 `revert_recommended=false` hint + new test `test_zero_fills_env_override_age_mismatch`）；E4 386/0 sibling regression PASS；2 P2 follow-up：`P2-WP03-MSG-STRUCT` + `P2-WP03-ALERT-FLAG-INDEPENDENCE`；Linux-flagged 6 items（deploy 後 cron 第一次 fire empirical verify）。
- **P0-3 Race protocol SOP Phase 2 rollout**：✅ APPROVE + enforce 立即生效 2026-05-16 18:00+；`.claude/agents/E2.md` §5 race check 5 條 + `docs/CCAgentWorkSpace/PM/race_dispatch_template.md` PM §6 模板 + `docs/lessons.md` Phase 2 entry；2026-05-30 PM 2-week review。

### 2026-05-16 完成的 P1 items

- **P1 #5 F-09 model_tier TOML extraction**：✅ DONE commit `3b055c98`；ArcSwap snapshot path；3 TOML 加 `model_tier="l1_9b"`；E2 APPROVE / E4 PASS 2917/0/1。
- **P1 #7 [68] portfolio_resting_exposure healthcheck**：✅ DONE commit `3b055c98`；ID conflict [58]→[68] resolved；562+408 LOC new；E2 APPROVE-CONDITIONAL / E4 PASS 368/0。
- **P1-WAVE-3-5-LINUX-MIGRATION-BACKLOG**：✅ DONE 2026-05-16 on `trade-core`；V092 physical continuous aggregates applied online；V091/V092/V093 `_sqlx_migrations` metadata repaired to max_applied=93 / rows=90；checksum verify drift_count=0。PM closure report：`docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-16--wave_3_5_linux_migration_backlog_closure.md`。
- **P1 #4 C1 v2 24h proof**：✅ TECHNICAL PASS / APPROVE-CONDITIONAL + PRODUCTION WRITER REVIVAL DONE 2026-05-17；`trade-core:/tmp/openclaw/audit/liquidation_topic_probe/liquidation_topic_probe_v2_latest.md` verdict `PASS_C1_PROOF_CANDIDATE`，`c1_proof_eligible=true`，uptime ratio `0.999991`，failures `0`；BB APPROVE after corrected side mapping（`Buy` long liquidation / `Sell` short liquidation）；W-AUDIT-8c/V095 source-test idempotency correction is DONE，V095 Linux PG dry-run x2 PASS，MIT re-sign cleared the schema/idempotency blocker，V095 is applied on Linux，and v46 source/runtime revival now subscribes C1-approved `allLiquidation.{symbol}` with 3 real rows landed。PM result：`docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-17--c1_final_signoff_result.md`。
- **P1 #6 BB-MF-3 production wiring**：✅ SOURCE/TEST + RUNTIME DEPLOY DONE 2026-05-17；Phase 1b checkpoint `ea4ceca6` is deployed after V094 apply + engine-only rebuild/restart；close-maker audit fields can populate on subsequent fills。

### 2026-05-16 P2 maintenance hygiene batch

✅ DONE 2026-05-16 local source/test closure for `P2-H0-DISPLAY-LABEL-1`，`P2-START-LOCAL-HELPER`，`P2-PA-CALLPATH-GREP-RULE`，and `P2-CROSSTAB-I18N`。H0 GUI endpoint now returns `display_only=true`；local Control API launchers use `resolve_openclaw_api_bind_host()`；PA/E2 audit skill requires P0/P1 leak/bias production caller grep；listed cross-tab static GUI files have `实盘/平仓/请检查` grep=0。PM closure report：`docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-16--p2_maintenance_hygiene_closure.md`。

### Banner 報告檔指引列表（v26-v39）

- v26 alpha-path dispatch report：`docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-15--alpha_path_phase_c_dispatch.md`
- v27 intent-freeze post-grace closure report：`docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-15--p1_intent_freeze_27_post_grace_closure.md`
- v28 Phase C0 liquidation inventory report：`docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-15--w_audit_8a_phase_c0_liquidation_inventory.md`
- v29 P0-MICRO-PROFIT alpha prework：`docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-15--micro_profit_alpha_prework.md`
- v29 A4-C PM/PA/FA unblock/archive engineering card：`docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-15--a4c_unblock_engineering_card.md`
- v29 A4-C RCA start：`docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-15--a4c_stage0r_rca_start.md`
- v30 TODO/source three-side sync：`docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-15--todo_v30_three_side_sync.md`
- v31 A4-C RCA final + C1 proof start：`docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-15--a4c_rca_final_and_c1_proof_start.md`
- v32 W-AUDIT-8b review + Stage 0R design：`docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-15--w_audit_8b_review_stage0r_design.md`
- v35 current-progress sync + rebuild decision：`docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-16--v35_three_side_sync_rebuild.md`
- v36 completion cleanup archive：`docs/archive/2026-05-16--todo_v36_completion_cleanup_archive.md`
- v37 Stage 1 / A4-C active-marker cleanup：`docs/archive/2026-05-16--stage1_demo_a4c_tombstone_cleanup.md`
- W-AUDIT-8b adversarial hardening commit `1499778b`：`docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-16--w_audit_8b_adversarial_hardening.md`
- v39 Wave 3.5 Linux PG migration backlog closure：`docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-16--wave_3_5_linux_migration_backlog_closure.md`

---

## 二、§3 Latest State 已 DONE 條目（原文保留）

### EDGE-P2-3 Phase 1b 整套部署鏈

`Round 1 Design/Governance CLOSED + Worktree B DEPLOY DONE 2026-05-17`：
- round 1 歷史 + spec v1.3 / AMD v0.4 / V094 spec archived at `docs/archive/2026-05-16--close_maker_first_phase_1b_round1_archive.md`
- Option A Worktree B source/test landed at `ea4ceca6` with A3/E2/E4 approval
- `b867e452` fixed the test-only phys-lock literal guard regression
- V094 Linux apply + engine-only rebuild/restart 已 DONE
- phys_lock live enablement remains deferred to Phase 2b
- 認知：本 refactor 是 execution-quality optimization（fee saving ~$50-$200/year per E3 empirical），不解 trading losses root cause（5 textbook 策略 structural alpha deficit）；真實治癒走 W-AUDIT-8a/8b/8c alpha source 軸。

### Trading losses Round 2 — Alpha Source Push Option A

`SOURCE/TEST DONE 2026-05-16 + W-AUDIT-8c correction/V095 APPLY DONE 2026-05-17`：
- operator trigger 後同步派發 2 路：（P0）Phase 1b Worktree B source/test done `ea4ceca6` and runtime deploy done after V094；（P1）W-AUDIT-8b Round 2 Phase A sweep tooling done `a6e17d5d`
- C1 transport proof passed 2026-05-17
- W-AUDIT-8c correction source/test includes V095 idempotency source
- V095 Linux PG dry-run x2 PASS + MIT re-sign APPROVE-CONDITIONAL + Linux apply/register DONE
- Production writer revival still waits for separate AMD/source/config dispatch；no production `allLiquidation*` enablement / auth mutation / paper/live/mainnet enablement yet（注：此後 v46 已完成）

### 2026-05-18 EDGE-P2-3 Phase 1b RUNTIME ACTIVATOR BLOCKER — RESOLVED

原 RCA preserved for governance audit：
- post-deploy 4h `trading.fills` sample showed 0% maker_attempt rate（18 grid_close_short + 2 ma_reverse_cross all `close_maker_attempt=FALSE` + `fallback_reason=NULL`）
- E2 adversarial RCA `docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-18--phase_1b_0_attempt_rca.md` identified cold-default `use_maker_close=false` + ZERO production callers for `set_use_maker_close_runtime`
- Resolution：PA design `2026-05-18--phase_1b_use_maker_close_runtime_activator_design.md` Option A TOML activator → E1 second-dispatch IMPL `18081551`（~40 LOC `pipeline_ctor.rs` + `pipeline_config.rs` + `risk_config_demo.toml`）→ E2 re-review APPROVE 0 new MUST-FIX（`a94825cb`）→ E4 PASS 12/12（`af3b3010`）→ QA APPROVE 0 BLOCKER（`a1b3ca908`）→ merge `c737a1e4` → restart 2026-05-17 23:54 UTC engine PID 1143103
- AMD-2026-05-15-02 v0.5（`23e6b6b2`）added Runtime Activation Layer wording
- AC-A 24h window verification still pending statistical significance per QA template

### 2026-05-18 W-AUDIT round 2 milestones

**（a）W-AUDIT-8b Round 2 Phase B preliminary sweep**：on panel 6.92d（operator-auth override pending 7.0d natural confirm ≈2026-05-18 01:30 CEST）returned 8/8 cells RED HIGH conf with DSR=0 / PBO 0.64-0.75 / z=1.2 INJUSDT dilution -9.64 bps / crowded_long_fade dead trigger all z（`docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-17--w_audit_8b_round2_phase_b_preliminary_sweep.md`）；7.0d confirm rerun + 4-agent QC/MIT/BB/FA review packet template（`docs/CCAgentWorkSpace/PM/workspace/templates/2026-05-18--w_audit_8b_round2_red_4agent_review_packet_template.md`）ready。

**（b）W-AUDIT-8a Phase B/C/D 11-worktree decomposition**：done（`docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-18--w_audit_8a_phase_b_c_d_worktree_decomposition.md`）：36.1 pd / 8.5 wallclock weeks @ 4 active E1。Wave 1 ✅ MERGED 2026-05-18 via single-sequential E1+E2 chain post race-incident recovery：B-REM-1 dispatch snapshot contract tests `49975eeb`（merge `5aeae75c`），B-REM-5 SourceAvailability schema `5997dd43` + ADR-0023 `1b614daf`（merge `ef0dfc6e`，E2 APPROVE per `docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-18--w_audit_8a_b_rem_5_e2_review.md`），C1-LIQ-WRITER LiquidationPulse provider `7ab6c22d` + healthcheck `[67]` `d8938a78` + W-AUDIT-8c spec v0.3（`06897175`）（merge `25413e96`，E2 APPROVE-CONDITIONAL + QA APPROVE WITH RESERVATIONS per `docs/CCAgentWorkSpace/QA/workspace/reports/2026-05-18--w_audit_8a_c1_liq_writer_qa_deploy_readiness.md`）。Wave 2（`C2-ORDERFLOW` 5pd HIGH + `C3-SPREAD` + `D-CONTRACT-LOCK` 2pd PA-only）deferred to Sprint N+4（W9-W10，2026-06-07..13）。

### 2026-05-18 AMD-2026-05-15-02 v0.5 + multi-agent dispatch race incident

AMD v0.4 → v0.5 wording patch（`23e6b6b2`）adds explicit Runtime Activation Layer + three-env TOML table + Phase 2b live_demo Demo-only guard conflict defer to AMD §3 line 84（closes E2-identified spec/IMPL gap）。

**4-E1 + 1-PA parallel dispatch on 2026-05-18 SUSPENDED** 因：
- （a）`isolation=worktree` 機制不可靠（hook 未設 + agents 用絕對路徑 write main tree）
- （b）agents cross-wrote main tree（Phase 1b activator agent + B-REM-1 agent 都動 `rust/openclaw_engine/src/tick_pipeline/`，導致 `step_4_5_dispatch.rs +246 LOC`（B-REM-1 dispatch snapshot contract tests）leaked into `feature/phase-1b-runtime-activator` branch alongside Phase 1b activator IMPL）
- （c）AMD v0.5 patch 在 main tree 被某 agent 過程 silent revert（已 re-apply）

**Recovery state ✅ CLOSED 2026-05-18 via single-sequential dispatch**：Phase 1b activator IMPL second-dispatch `18081551`（post-strip 245 LOC B-REM-1 leak + honest cargo test 2972/0/1）→ merge `c737a1e4`。B-REM-5 SourceAvailability `5997dd43` E2 APPROVE → merge `ef0dfc6e` + ADR-0023 `1b614daf`。B-REM-1 dispatch snapshot contract tests re-dispatched as `49975eeb` → merge `5aeae75c`。C1-LIQ-WRITER LiquidationPulse provider re-dispatched as `7ab6c22d` + healthcheck `[67]` `d8938a78` → merge `25413e96`。

**Lesson learned**：不再多 E1 同時並行；single-agent sequential + E2 chain 完才下個 — 本批 recovery 是這條規則的首次實證；後續所有 W-AUDIT-8a Wave 2+ 工作必繼承。

### 2026-05-18 Phase 1b runtime activator deploy chain CLOSED + W-AUDIT-8b Round 2 RED_FINAL tombstoned

**Phase 1b deploy chain APPROVED**：
- E1 second-dispatch（`18081551`，post-strip 245 LOC B-REM-1 leak + honest cargo test 2972/0/1）→ E2 re-review APPROVE 0 new MUST-FIX（`a94825cb`）→ E4 PASS 12/12 runs Mac+Linux release cross-arch（`af3b3010`）→ QA APPROVE 0 BLOCKER（`a1b3ca908`）→ merge to main（`c737a1e4`）→ operator-代跑 restart_all.sh --rebuild on trade-core UTC 2026-05-17 23:54 → engine PID 1066422 → 1143103 with new binary containing `runtime.use_maker_close` activator
- `risk_config_demo.toml [runtime] use_maker_close=true` confirmed via grep + engine boot log shows `risk_demo_version=2` loaded
- Post-restart 90min sample：1 whitelist close，0 maker_attempts（n=1 too small）；AC-A/B/C verification requires ~24h window for statistical significance per QA template
- Phase 2a 14d observation clock t=0 = first AC-A SQL PASS UTC timestamp（NOT restart timestamp）
- Cross-wave consistency check pending（QA recommendation #3 — restart triggered W6/W7/W1 main-landed-but-not-deployed sources too；PM 24h audit packet §3.9）

**W-AUDIT-8b Round 2 RED_FINAL tombstoned**：
- PA 7.0d sweep rerun（panel 7.0049d natural gate，+7min margin，4/4 empirical assertion gates PASS）returned 8/8 cells RED HIGH conf 100% aligned with preliminary 6.92d（`docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-18--w_audit_8b_round2_phase_b_final_sweep.md`）
- 4-agent independent review **4/4 APPROVE concur RED_FINAL**（BB 0/2/3，QC 0/4/2，FA 3/2/3，MIT 0/4/3 MUST/SHOULD/NTH）；MIT report `docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-18--w_audit_8b_round2_red_final_mit_review.md`（`d3fe4063`）；BB/QC/FA inline per profile rule；consolidated verdict `docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-18--w_audit_8b_round2_red_final_4agent_consolidated.md`（`ffdbc2d0`）
- **Cross-agent consensus root causes**：（a）z 39x asymmetry（MIT empirical：z≥+1.5 0.27% vs z≤-1.5 10.5%）+ Bybit USDT-perp 25-sym 結構性 funding tail bimodal（BB structural）→ crowded_long_fade dead **data-structural，NOT demo silent degradation NOT strategy design bug**；（b）INJUSDT 87% concentration in 2026-05-13 single-day event（MIT）→ effective independent obs ≈ 2-3 days；（c）`_n_eff` formula deterministic horizon-overlap（not cluster-aware）— RED robust but W-AUDIT-8c+ must retrofit
- **AMD-2026-05-15-02 v0.6 → v0.7 wording patch**（`71f2283b`）§8 condition 3 funding-related general + tombstone clause
- **W-AUDIT-8b spec v0.3 → v0.4 tombstone amendment**（`ef7ea6c2`）+ NEW `Branch-Level Dormancy Retire Path` governance hardening（FA-MUST-FIX-2 forward-applicable to W-AUDIT-8c/8a/8e/8f specs）
- **REJECTED**：Round 3 zoom-in（MIT ROI≈0）/ 28d panel expansion / dual-AMD
- **Redirect path**：W-AUDIT-8c Liquidation Cluster + W-AUDIT-8a Phase B/C/D per fix-plan v1.1 §9.4 critical path（11-worktree decomposition，Wave 1 = B-REM-1/5 + C1-LIQ-WRITER ready）

### 2026-05-18 ~10:30 UTC EDGE-P2-3 Phase 1b 12H sample BLOCKER → P0 calibration

Operator surfaced third-party assessment + main session PG verify converged on same finding。**PG data（post-restart UTC 2026-05-17 23:54 + ~10.5h）**：
```
engine_mode | close_maker_attempt | close_maker_fallback_reason | count
demo        | f                   |                             | 23
live_demo   | f                   |                             | 13
demo        | t                   | timeout_taker               | 4
```
4 attempted close fills（all on whitelist exit_reasons：3 `grid_close_short` + 1 `phys_lock_gate4_giveback`）were maker_attempt=TRUE BUT 100% fell back to taker via timeout → real fee saving = 0% currently。

**Pre-calibration code path is verified correct**（TOML activator firing + maker_attempt instrumentation populating audit fields）；root cause is parameter tuning（offset_bps=0.5 + buffer_ticks=1 + timeout 30s grid / 15s phys_lock too tight for sparse alt-coin spreads），NOT an IMPL bug。

**Schedule**：12H test window ends ~2026-05-18 11:54 UTC；after window closes → P0 dispatch sequence。Pre-window remaining ~1.5h is observation-only（no parameter changes during 12H window per AC-A integrity）。Operator instruction：「12H 後做 calibration，然後三端同步」。

---

## 三、§11 P1 / §12 P2 已 DONE 條目（原文保留）

### P1-EDGE-P2-3-PH1B-ML-INVARIANT
✅ **DONE 2026-05-18 commit `c3524da2`**：`.claude/skills/pr-adversarial-review/SKILL.md` §3.11 ML training pipeline 非輸入不變量 — `close_maker_*` audit 欄位禁餵 LinUCB/scorer/quantile/MLDE/DL3；含 3 條 grep pattern + 白名單（audit/replay/healthcheck/governance/tests）；違反輸出格式沿用 §3.10 caller proof。E3 PR pre-merge gate 立即生效。

### P1-BBMF3-WIRE-1
✅ SOURCE/TEST + RUNTIME DEPLOY DONE 2026-05-17。Phase 1b source/test bundle wires close-maker reject/backoff/cooldown plumbing and integration regression。Runtime evidence：V094 Linux apply + engine-only rebuild/restart completed；close-maker audit fields can populate on subsequent fills。

### P1-WAVE-3-5-LINUX-MIGRATION-BACKLOG
✅ **DONE 2026-05-16**：`trade-core` online PG closure complete。V092 physical continuous aggregates created（6 views + 6 refresh policies）；V091/V092/V093 `_sqlx_migrations` metadata inserted with source SHA-384 checksums；max_applied=93 / rows=90 / checksum drift_count=0。V081 remains legal dead slot。V094 deploy is no longer blocked by this backlog。

### P1-PORTFOLIO-RESTING-EXPOSURE-1
✅ **DONE 2026-05-16 commit `9980448a`**（Round 2 alpha push P1）：337 LOC source（intent_processor/mod.rs +118 / tests.rs +208 / paper_state/resting_orders.rs +11）+ 7 unit test；Mac+Linux cargo test --release 2915/0/1（= baseline 2908 + new 7）；hot_path bench p99=42μs << 300μs SLA；aarch64-apple-darwin PASS。A3 對抗審 APPROVE 9/10（2 WARN advisory 不阻 commit）；E2 PASS to E4（0 CRITICAL / 1 MEDIUM / 4 LOW）；E4 regression PASS。16-root + 9 invariant + 硬邊界全 GREEN；live/auth/lease 全未動；注釋全中文。

### P2-PORTFOLIO-RESTING-58-HEALTHCHECK
✅ **DONE 2026-05-16 as `[68] portfolio_resting_exposure_lineage`**：原 spec/TODO 標 `[58]`，但 `[58]` 已被 W-AUDIT-9 T4 `check_58_graduated_canary_stage_invariant` 占用；實作取下一個 free slot `[68]`，保留 lineage name。`check_68_portfolio_resting_exposure` 已在 `runner.py` wire + `__init__.py` re-export；targeted pytest `helper_scripts/db/test_portfolio_resting_exposure_healthcheck.py -q` = 10 passed。Residual LOW：engine-specific fallback cap / live+live_demo snapshot double-count future hardening，不阻 Stage 1 demo 啟動前監控目的。

### P2-PORTFOLIO-RESTING-TEST-COVERAGE
✅ **DONE 2026-05-18 commit `c3524da2`**：新測 `test_p2_portfolio_resting_multi_close_summed_capped_at_filled` 釘住「同 symbol 多筆 close-side resting 累積 > filled qty 時 cap 在 filled qty」A3 WARN-2 invariant；intent_processor/tests.rs +45 LOC（含中文 rationale 與三層 assert）。cargo test 2993/0/1 PASS。

### P2-PORTFOLIO-RESTING-ROUTER-CACHE
✅ **DONE 2026-05-18 commit `c3524da2`**：新增 `compute_{exposure_pct,correlated_exposure_pct,leverage}_from_netting(eff_long, eff_short, balance)` 三 helper 變體 + `compute_effective_long_short_notional` 升 `#[doc(hidden)] pub fn`（precedent `TickPipeline::new`）；router.rs 438-450 caller cache (eff_long, eff_short, balance) 一次共用，3 HashMap allocs → 1。語意保留。E5-bench 實測 p50 ~7.88µs single netting vs ~6.29µs cached three pcts（25-sym × 3-resting 場景節省 ~20%）。

### P2-PORTFOLIO-RESTING-DOCSTRING-CLEANUP
✅ **DONE 2026-05-18 commit `c3524da2`**：intent_processor/mod.rs:887-923 三段 docstring（RRC-1-B3 / RG-2 / FIX-05）移除英文僅保留中文；P1-PORTFOLIO-RESTING-EXPOSURE-1 引入註解保留。E2 LOW-2 closed。

### P2-PORTFOLIO-RESTING-E5-BENCH
✅ **DONE 2026-05-18 commit `c3524da2`**：新 `benches/intent_processor_exposure.rs`（178 LOC，Criterion harness）覆蓋 25-sym × 3-resting 場景；Cargo.toml `[[bench]]` 註冊；Mac aarch64 + Linux x86_64 release `--no-run` 編譯 PASS；實跑 single netting p50/p99 = 7.88/11.71µs vs cached three-pct p50/p99 = 6.29/9.46µs。

### P2-PORTFOLIO-RESTING-REPLAY-PARALLEL
✅ **DONE 2026-05-18 commit `c3524da2` (design-only)**：design memo `docs/execution_plan/2026-05-18--p2_portfolio_resting_replay_parallel_design.md` 闡明本 IMPL 故意不感染 replay（R5-T2 並行 surface SAFETY 不變量）；後續啟動條件 3 條觸發 / 短期 hygiene 1 條 backlog 子卡。0 代碼動。

### P1-CRON-INSTALL-WAVE-1
✅ **SOURCE/TEST + LINUX CRONTAB INSTALL DONE 2026-05-19**：source/test commit `7bb994c3`；operator-authorized trade-core crontab install completed with backup `/tmp/openclaw/crontab_backups/before_p1_cron_install_wave_1_20260519T103745Z.cron`。5 wrapper installed；direct heartbeat recheck：`[75]` PASS fresh after first 5-min fire；`[76]-[79]` expected WARN until first natural hourly/daily/weekly fire。Report：`docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-19--v096_cron_watchdog_entry_rca_closure.md`。

### P1-WATCHDOG-STATUS2-RCA
✅ **RCA DONE 2026-05-19**：2026-05-19 01:52-01:57 UTC cluster = DNS/HTTP transport outage + stale snapshot misclassified as `ENGINE_CRASH`；no OOM/segfault/panic evidence；engine/watchdog currently alive。Follow-up implementation ticket：`P1-WATCHDOG-NETOUTAGE-CLASSIFIER-FIX`。

### P1-C1-PROBE-RECONNECT-SPEC
✅ **DONE 2026-05-16 commits `25396b0b` + `8d2eef58`**：v2 resilient harness IMPL `liquidation_topic_probe_v2.py`（942→1045 LOC）+ 49/49 unit test + wrapper script `run_c1_v2_proof.sh`；5 reviewer 全綠（A3 7.5/10 APPROVE-COND + E2 PASS to merge + E4 Linux 49/49 + 60s smoke PASS + BB COND 0 Critical/High/Med + MIT FULL V09X 不需）+ E1 consolidated 6-fix + E2 re-review PASS + E4 quick recheck PASS。

### P2-DEAD-SCHEMA-DROP-1
✅ **SOURCE/TEST + LINUX V096 APPLY/REGISTER DONE 2026-05-19**：source commit `428f1505`；operator-authorized trade-core apply/register only V096（no V095 / no engine restart）。Checksum `dd4613c384f053b6ff7cff8cea48529790e7e77458e97e3e2d89ca31142c58cfe5a691c367df5a0209812fd36e91b982`；backup `/tmp/openclaw/migration_backups/v096_20260519T103714Z`；precheck rows/dependents 0；postcheck both target tables `to_regclass=NULL`；`_sqlx_migrations` version 96 success=true。

### P2-DEAD-RUST-CLEANUP-1
✅ **DONE 2026-05-18 commit `449f628b`**：刪 7 openclaw_core modules（attention 424 / attribution 267 / cognitive 524 / dream 936 / message_bus 296 / order_match 308 / opportunity 861 = 3616 LOC，dispatch 估 3186 LOC 偏差 +430 LOC 已記入 ADR-0015 follow-up）；rg 0 production caller 驗證；lib.rs 移 7 `pub mod` + retirement marker。cargo openclaw_core 357/0 PASS（baseline 446 − 90 dead module tests + 1 new stochastic_prior test = 357，每個移除可歸因，**非 silent deletion**）。ADR-0015 提「九」模組但 PA TODO 列 7，餘 2 待 PA 下 sprint 確認。

### P2-PERCEPTION-DEPRECATE-1
✅ **DONE 2026-05-18 commit `428f1505`**：`perception_data_plane.py:513 validate_for_decision` 加 `warnings.warn(DeprecationWarning, stacklevel=2)`；中文 docstring 標明 0 production caller + 建議走 Agent Spine typed lineage。3 test 檔（test_perception_data_plane / test_integration_phase2 / test_batch9_perception_analyst_integration）加 pytestmark filterwarnings + unittest setUpModule（runner-agnostic）。107 perception 測試全 PASS（DeprecationWarning suppressed）。

### P2-H0-DISPLAY-LABEL-1
✅ **DONE 2026-05-16**：Python H0Gate GUI endpoint 回傳 `display_only=true`，明確標示此 FastAPI/GUI surface 僅展示 H0 狀態，不是 Rust H0 execution authority；targeted pytest `TestGetH0GateStatusFreshnessFields` = 3 passed。

### P2-ORDERS-INTENT-ID-WRITER-GAP-1
✅ **DONE 2026-05-19 commit `4e045c2f`**：ORDER_COLS 12→13 + PendingOrder/OrderDispatchRequest/TradingMsg::Order 加 `intent_id: Option<String>`；entry path Some(make_intent_id(em, symbol, event.ts_ms)) byte-equal trading.intents writer；close path 4 commands + 1 synthetic + pending_sweep 全 explicit None（fail-loud no fake synthesis）；5 新 regression test（pending_registration_order_type_tests.rs）；PG bind 5041×13=65533 < 65535 cap PASS；backfill design memo（DO NOT EXECUTE）at `docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-19--p2_orders_intent_id_backfill_design_memo.md`。Guardian-pass-rate join 自此恢復可算。

### P2-WP05-FUP-1
✅ **DONE 32/32 2026-05-19** — round 1（commit `428f1505`）：23 sites 跨 8 py file `str(exc)` → 穩定 reason_code + logger.warning；round 2（commit pending today）：9 risk_routes.py sites — PM-as-Conductor APPROVE Option A → `_ipc_failure(reason_code, *, log_detail=None)` 簽名升級保留 `rust_engine_unavailable:` 前綴維持 test:266 substring 斷言相容 + 9 caller 改 `ipc_<op>_failed` / `ipc_patch_risk_config_not_ok`；`logger.warning("ipc failure: %s | %s", reason_code, log_detail)` 不外洩。1 site live_session_routes:591 marker compare 保留（dispatch 明確分類為非 leak）。E2 APPROVE 0 finding；E4 421/3 = v51 baseline identical 0 regression。

### P2-COMMON-JS-LOC
✅ **DONE 2026-05-19 commit `ae71575e`**：common.js 2198→4 files（common.js 815 + common-formatters.js 548 + common-mode-badge.js 357 + common-modals.js 482 = 2202 +4 module headers），每檔 ≤ 2000 cap；19 HTML 文件 3 new `<script>` tag 順序在 common.js 之前；E2 HIGH catch cache-bust drift → 全 19 文件 `?v=20260519.split-p2` uniform 修正；node --check 4/4 PASS / HTML parse 19/19 PASS；window.* global pattern 保留無 framework 注入。

### P2-ENTRY-PATH-0PCT-MAKER-FILL-RCA
✅ **RCA DONE 2026-05-19**：Phase 1b deploy clock後 demo whitelist close，entry-close `oc_close_mf_fb_*` = 6 total / 6 attempts / 0 maker / 6 timeout_taker；risk-exit `oc_risk_*` 同窗 = 5 total / 3 attempts / 3 maker。結論：非全局 PostOnly 壞，為 entry-close path-specific 真實 fill gap；sweep BBO-cross proxy 70.8% 對此 path 過度樂觀。

### P2-TAB-LIVE-LOC
✅ **DONE 2026-05-19 commit `9bf4fd62`** via P2-TAB-LIVE-JS-EXTRACT：tab-live.html 內聯 `<script>` block 抽到 sibling `tab-live.js` 1645 LOC（pattern 同 app-paper.js / risk-tab.js / governance-tab.js / canary-tab.js）；HTML 2171→**543** LOC 大幅低於 §九 2000 cap；純 cut-paste 零邏輯改；self-reference scan clean / DOM timing 保留 verbatim。node --check + HTML parse 全 PASS。

### P2-CROSSTAB-I18N
✅ **DONE 2026-05-16**：tab-system / tab-paper / console / tab-settings / governance-tab.js / tab-risk / app.js / risk-tab.js 進行 static UI 繁體化 cleanup；指定殘留 `实盘/平仓/请检查` grep=0；JS syntax `node --check app.js risk-tab.js governance-tab.js` passed。

### P2-STOCHASTIC-LEAK
✅ **DONE 2026-05-18 commit `449f628b`**：indicators/momentum.rs:80-86 確認 `high[start..=i]` 含 current bar 同類 look-ahead leak；新增 `stochastic_prior(high, low, close, k_period, d_period)` strip current bar（mirror `donchian_prior`），原 `stochastic()` 保留（live caller 仍在 IndicatorEngine + golden_dataset.rs），加中文 warning doc。新測 `test_stochastic_prior_excludes_current_bar` 釘 divergence。5 textbook + 5 strategy indicator 完整 leak audit table：**僅 stochastic LEAKY**，RSI/ADX/ATR/EWMA/SMA/EMA/MACD/KAMA/Bollinger/Hurst/volume_ratio 全 LEAK-FREE 或 BENIGN（summary-style 非 forecast）。後續 production 切換到 `stochastic_prior` 由下一 P1 處理。

### P2-START-LOCAL-HELPER
✅ **DONE 2026-05-16**：`start_local.sh` + `beta_quickstart.sh` source `helper_scripts/lib/api_bind_host.sh` 並使用 `resolve_openclaw_api_bind_host()`；safe default 保持 auto→Tailscale IPv4/loopback，`OPENCLAW_BIND_HOST` 可 override，`0.0.0.0` / `::` 仍 fail-closed；static pytest + `bash -n` passed。

### P2-PA-CALLPATH-GREP-RULE
✅ **DONE 2026-05-16**：repo 內無 literal `code-quality-audit` skill，落地到實際審核入口 `.claude/skills/pr-adversarial-review/SKILL.md` §3.10，並同步 `.claude/agents/PA.md`；P0/P1 leak / look-ahead / selection-bias / stale finding 必附 IndicatorEngine / production caller call-path grep，未附 grep 不得作 P0/P1 blocker。

### P2-WP05-CSP-UNSAFE-INLINE
🟡 **SRI DONE 2026-05-18 commit `7bb994c3`** / ⏳ **full CSP nonce-based refactor 待 live-gate 前 P1**：`trading.html` 唯一外部 CDN tag（unpkg lightweight-charts@4.1.0）加 `integrity="sha384-rcCMiCptH4kTlEbg0euOTUKWe72TESbrjElatnG+9BfbmUIV268UK/Pro5biJdGm" crossorigin="anonymous"`；helper `helper_scripts/security/compute_sri_hashes.sh` 提供版本升级時重算 + version-pin 檢查。`unsafe-inline` 移除 + 25 處 innerHTML 改寫 + nonce-based CSP 為 live-gate 前獨立 P1 refactor。

---

## 四、§11.6 12-Agent Full System Audit WPs（2026-05-16）

**Source**：`srv/2026-05-16--full-system-audit-fix-plan.md`（PA consolidated + PM sign-off）
**PM Sign-off**：APPROVED-CONDITIONAL 2026-05-16
**Status**：Wave 1-4 source/test work is closed and archived in `docs/archive/2026-05-16--todo_v36_completion_cleanup_archive.md`。

**Retained follow-ups（已 fold 進 active TODO）**：
- WP-11 Phase 2 residuals → §12 P2 backlog
- WP-12 ONNX remains deferred；rule-based fallback is current behavior
- PA audit drift hardening → `P2-PA-CALLPATH-GREP-RULE`
- LOC follow-ups from Wave 1 → `P2-COMMON-JS-LOC` 與 `P2-TAB-LIVE-LOC`

---

## 五、§4 Wave Roster 已關閉細節

### EDGE-P2-3 Phase 1b（Wave 12，原 §4.1）

✅ **DEPLOY DONE 2026-05-18，AC-A VERIFICATION PENDING 24h**：Full chain APPROVED：E1 second-dispatch `18081551`（post-strip 245 LOC B-REM-1 leak + honest cargo test 2972/0/1）→ E2 re-review APPROVE 0 new MUST-FIX → E4 PASS 12/12 cross-arch → QA APPROVE 0 BLOCKER → merge to main `c737a1e4` → operator-authorized restart UTC 2026-05-17 23:54（PID 1066422 → 1143103）。AMD v0.6 → v0.7（`71f2283b`）wording patch §8 condition 3 land。`runtime.use_maker_close=true` confirmed in demo TOML。Phase 2a 14d clock t=0 trigger = first AC-A SQL PASS。

### W-AUDIT-8a（Wave 4）
✅ **C1 TRANSPORT PASS + WRITER REVIVAL DONE 2026-05-17 + WAVE 1 MERGED 2026-05-18**：Phase A/B/C0 complete；v1 C1 proof FAIL_CONNECTION 5h/24h → v2 resilient harness IMPL `25396b0b` + consolidated 6-fix `8d2eef58` 全鏈 GREEN；C1 24h artifact on `trade-core` is `PASS_C1_PROOF_CANDIDATE`；BB approved corrected side mapping；MIT schema/writer idempotency condition is cleared by V095 apply；production `allLiquidation.{symbol}` writer revival landed in `0e8a8ae8`/`bedc40c3` with Linux rows observed。Phase B/C/D 11-worktree Wave 1（B-REM-1 `49975eeb` + B-REM-5 `5997dd43` + ADR-0023 `1b614daf` + C1-LIQ-WRITER `7ab6c22d` + healthcheck `[67]` `d8938a78`）MERGED 2026-05-18 via `ef0dfc6e` / `5aeae75c` / `25413e96`。Wave 2 deferred to Sprint N+4。

### W-AUDIT-8b（Wave 5）
⛔ **TOMBSTONED 2026-05-18 Round 2 RED_FINAL**：Spec v0.3 → **v0.4 tombstone**（`ef7ea6c2`）per Round 2 7.0d sweep 8/8 cells RED HIGH conf + 4-agent（BB/QC/FA/MIT）4/4 APPROVE concur（`ffdbc2d0` consolidated verdict）。AMD v0.6 → v0.7（`71f2283b`）§8 condition 3 funding-related general + tombstone clause。No-revive on same feature shape per A4-C precedent。NEW `Branch-Level Dormancy Retire Path` governance hardening forward-applicable to W-AUDIT-8c/8a/8e/8f。**Redirect**：W-AUDIT-8c + W-AUDIT-8a Phase B/C/D per fix-plan v1.1 §9.4 critical path。

### W-AUDIT-8c（Wave 6）
✅ **SOURCE/TEST + V095 LINUX APPLY + WRITER REVIVAL DONE 2026-05-17**：V095 source/test preserves one `data[]` item per row via `(symbol, ts, side, qty, price)`；parser/writer fail closed；corrected side mapping tested；V095 Linux PG dry-run x2 PASS + MIT re-sign + Linux apply/register DONE；production `allLiquidation.{symbol}` writer revival DONE；strategy launch remains separate。

---

## 六、§10 P0 已關閉條目

### P0-PHASE-1B-PARAM-CALIBRATION-1
✅ **DONE 2026-05-18 13:50 UTC（deploy chain CLOSED）**：Option C path（simulation = evidence，no live pilot）：PA spec v0.1/v0.2 → E1 harness IMPL（`93069c29`）+ Rust constant change（`820f0532`）→ E2 + E4 review chain → Merge（`8d8a0123` + `67f1a047`）→ Sweep 81 cells（1.4 sec wall，top `G-AB-01-C90` fill 70.8% / +3.37 bps simulated）→ operator rebuild + restart（engine PID 1506208 binary mtime 13:50 UTC）。Grid family `timeout_ms 30s → 90s` deployed；phys_lock family timeout unchanged。**Acceptance result**：simulation `maker_fill_rate=70.8% ≥ 25%` AND `expected_fee_saving_bps=+3.37 ≥ 0.5`（top cell）。**Outstanding**：24h post-deploy AC-A SQL verify real fill rate vs 70.8% simulation prediction ~2026-05-19 13:50 UTC。Rollback trigger：real fill < 15% Wilson lower at n≥30 OR adverse_real > 5.55 bps baseline。PnL unlock projection $32-162/year × ~65% PASS prior。Phase 2a 14d observation clock reset from 13:50 UTC。

---

## 七、附：CLAUDE.md 引用的 archive 連結（v55 banner 內列出）

- `docs/archive/2026-05-07--todo_v12_agent_openclaw_replan_archive.md`
- `docs/archive/2026-05-09--w_audit_verified_closed_archive_v3.md`
- `docs/archive/2026-05-15--todo_v21_completion_cleanup_archive.md`
- `docs/archive/2026-05-15--todo_v24_stale_rows_archive.md`
- `docs/archive/2026-05-16--todo_v36_completion_cleanup_archive.md`
- `docs/archive/2026-05-16--close_maker_first_phase_1b_round1_archive.md`
- `docs/archive/2026-05-16--stage1_demo_a4c_tombstone_cleanup.md`

---

**歸檔者**：主會話 PM
**翻譯歸檔時間**：2026-05-19
**對應 TODO 版本**：v55 → 翻譯後簡稱 v56-zh（精簡中文版）
