# PM Memory — 工作記憶

> 本檔=長期教訓+近期記錄；超 300 行由 R4 巡檢標記、PM 派工壓實，舊條目原文遷 memory-archive.md（append-only）；agent 完成序列照常追加於檔尾。

## 長期教訓（2026-06-10 壓實蒸餾，源自 2026-03-31~2026-06-04 條目）

1. 部署驗證必查 `/proc/$pid/exe` 與 binary hash/strings 對齊：PID 存活可能跑著已刪除的舊 executable，source grep+watchdog 不能證明 runtime 已載入新碼。
2. Linux rebuild 經非登入 SSH 必帶 `PATH=$HOME/.cargo/bin:$PATH`；標準部署指令 `bash helper_scripts/restart_all.sh --rebuild --keep-auth`。
3. `--keep-auth` 只保留現存簽名 auth、不會恢復已缺失者（restart sentinel 可能已消耗 auth）；live auth 只能走簽名 renew 路徑，禁手寫 authorization.json。
4. Bind/health 用實際地址：`OPENCLAW_BIND_HOST=auto` 解析 Tailscale IPv4 否則 loopback，禁 0.0.0.0/::；健康探測打實際 bind 地址而非假設 127.0.0.1。
5. 派發前 PM 必做 ground-truth audit（fetch+查 remote branch+實測現狀），TODO banner 與 prompt hint 會 stale；sub-agent 應 read source 驗證 prompt 前提，偏離時 pivot 並記錄動機。
6. Sub-agent prompt 必明示：直接 commit+push 不留 staging dir；push 被 sandbox 擋時 inline 回報由 PM 補推、禁 dangerouslyDisableSandbox；鼓勵 push back 非盲從執行。
7. 多 session 並行安全模式：meta-doc 用 `git commit --only`、絕不動隔壁 WIP；branch chaos 下 `git push origin <hash>:main` 與 git plumbing pattern 安全（不含 checkout/merge/rebase）。
8. 大工程先派 PA design（含 ready-to-deploy E1 prompt template）再派實作；同檔 overlap 任務強制串行派發或 first-commit absorb pattern，避免 rebase conflict。
9. Cross-agent audit 前提可能部分錯（MIT/PA/QC 均有先例），push back+SSOT trace 驗證是責任；判級先分清「by-design 未實作」vs「真壞掉」，避免 P0/CRITICAL false elevation。
10. Source/test green ≠ runtime/product closure；conditional-pass review 不是 closure；contract/FND PASS 只開下一層 design scope 非 implementation clearance；舊 spec 的 stale ready-to-implement 標頭要打 gate override 註記。
11. Healthcheck 校準：FAIL 須區分真 wedge 與合法狀態（rejected-only、Working maker、rolling-window shrink → WARN）；分母選錯會長期 false-red（[55] 改 fully-filled plan invariant 先例）。
12. Replay-first 驗證默認：sign-off 前先判 replay/counterfactual 能否驗 claim，能且安全就跑；不能則明說並改用 runtime probe / DB inventory / WS probe / healthcheck / static guard。
13. Alpha promotion 治理：math-primary、bull-heavy 證據必標註；Stage 0R GATE-RED 不啟 Stage 1（Demo-only 證據鏈）；gate 必 machine-checkable fail-closed——producer 不檢查的 manifest/JSON 等於沒有 gate。
14. V### migration 必 Linux PG empirical dry-run + double-apply 驗 idempotency；V 槽位尊重已文檔化 reserved slots；整合/合併後的 SQL 要重跑 dry-run（曾抓 Timescale `time_interval` 整合 bug）。
15. Schema 註釋與「表存在」都不是事實：retention 以 migration+PG 反射為準，0-row 表 ≠ pipeline live；先 runtime/DB 查證再寫結論。
16. 審計報告合併必按根因去重（同一問題 E3/E4/PA 各報一遍）；估時保留 E2+E4 佔總工時 30-40% 的 buffer。
17. 新 healthcheck slot 派發前 grep `passive_wait_healthcheck/runner.py` 確認編號避免衝突；被動等待項必綁 healthcheck/復查日期；fresh-restart grace 內的 PASS 不算 post-grace 閉合。
18. 長 multi-agent run 後不 bulk-commit raw WIP：只 promote 單一 canonical closure report，stale/衝突 role notes 留待 reconcile；Operator mirror 要嘛 pointer/stub 要嘛 `cmp` byte-identical。

## 近期記錄

## 2026-06-20 MM Verdict Cost-Wall Bridge

- `recorder_mm_verdict_cron.sh` now carries the break-even lens into daily live MM status: per-symbol edge-before-fees, break-even maker fee, fee shortfall, required spread capture, required maker rebate, and top-level `cost_wall_summary`.
- `runtime_runner.py` preserves this summary in alpha discovery `arms_raw` detail without changing the stable `discovery_plan` schema or positive-edge gates.
- Focused checks passed: MM cron bash/static tests 11, alpha discovery runtime tests 10, runtime runner py_compile.
- Boundary: source/test/docs only at checkpoint; no engine/API restart, no PG write, no Bybit private/signed/trading call, no runtime/auth/risk/order mutation.

## 2026-06-20 FillSim Cost-Wall Instrumentation

- `fill_sim.py` now reports break-even maker fee, fee shortfall, required half-spread, and required maker rebate per side for every horizon/net block.
- Focused test `program_code/research/tests/test_fill_sim_cost_wall.py` covers normal cost wall, negative break-even fee/rebate-needed, and empty-sample output.
- trade-core temp smoke on fresh L1 (`fillsim_cost_wall_smoke_20260620T003611Z.json`) showed the current MM failure is structural: back fill_only net@15 `-5.365bp` and front fill_only net@15 `-4.796bp`; both still require maker rebate to break even.
- Boundary: no production report overwrite, no engine/API restart, no PG write, no Bybit private/signed/trading call; this is a single-regime diagnostic, not CP-3 go/no-go or promotion proof.

## 2026-06-20 MM Verdict Stale Guard + Cron Restore

- Fixed alpha discovery killboard so stale `recorder_mm_verdict` status older than 36h becomes `SOURCE_FAILURE/stale_artifact` instead of active MM capture; focused alpha discovery tests are now 10 passed.
- Restored Linux daily `recorder_mm_verdict_cron.sh` at `41 6 * * *`; manual read-only run updated MM samples from 3 to 16, all current net-edge symbols remain negative and below sample gate.
- Caveat: fill_sim report was ~57h old; after 72h adverse_selection becomes unavailable unless a separate heavy refresh schedule is approved/designed.

## 2026-06-19 Alpha Discovery Runtime Killboard

- 1-6 alpha discovery throughput 從 source/test scaffold 接成 artifact-only runtime killboard：讀 Gate-B / FlashDip / vol-event / MM verdict / AEG matrix artifacts，寫 `<DATA>/alpha_discovery_throughput/alpha_discovery_latest.json`。
- 新 cron wrapper 可每 15 分鐘更新 killboard；`is_fast_discovery_active` 需至少 3 個真實 artifact source present，避免空跑假陽性。
- 邊界：不連 DB、不連 Bybit、不啟 probe、不下單、不改 auth/risk/runtime state；目前是 discovery-orchestration active，不是可晉升 alpha proof。

## 2026-06-19 TODO v227 Passive-Watch Refresh

- Refreshed passive watch surfaces without closing any active gate.
- Source sync: Mac/origin/Linux aligned at v226 checkpoint `880b82ba`; watchdog `engine_alive=true` with demo snapshot age `7.4s`.
- Gate-B latest `2026-06-19T01:42:01Z` remained `WATCH_ONLY` with 21 total candidates, 0 alertable/start/schedule, and 1 watch_only; no preflight/probe was run.
- flash_dip remained zero-sample; L2 cursor remained `2026-06-17` with B3 shadow rows=0; D2 `reconcile_ghost_converge` total/semantics rows remained 0.
- Passive health at `2026-06-19T01:45:02Z` still failed `[74]` (`attempts=201`, `postonly=26`, `max_pending=0`) and `[56]` (`authorization_json_missing`). Boundary: docs/TODO/report + read-only Linux file/PG/healthcheck only; no CI/cargo/Linux build/deploy/rebuild/restart/DB write/Bybit private call/credential/runtime/auth/risk/order/trading mutation/probe/archive/promotion.

## 2026-06-19 TODO v226 Source-Sync Correction

- Corrected source-sync metadata after v225 passive-watch refresh.
- Mac `HEAD=origin/main=e8ade59a` and Linux `trade-core` `HEAD=origin/main=e8ade59a` after ff-only sync.
- Linux watchdog read-only status: `engine_alive=true`, demo snapshot age `30.0s`.
- Boundary: docs/TODO metadata only; no CI/cargo/Linux build/deploy/rebuild/restart/DB write/Bybit private call/credential/runtime/auth/risk/order/trading mutation; no active gate closed.

## 2026-06-19 TODO v225 Passive-Watch Refresh

- Refreshed passive watch surfaces without closing any active gate.
- Source sync: Mac/origin/Linux aligned at v224 checkpoint `f622574a`; watchdog `engine_alive=true` with demo snapshot age `28.6s`.
- Gate-B latest `2026-06-19T01:12:01Z` remained `WATCH_ONLY` with 21 total candidates, 0 alertable/start/schedule, and 1 watch_only; top BPUSDT candidates were stale/old ContinuousTrading, so no preflight/probe was run.
- flash_dip entry remained `{}` and read-only PG found 0 flash_dip rows; L2 cursor remained `2026-06-17` with 2026-06-12..17 no-op material days and B3 shadow rows=0; D2 `reconcile_ghost_converge` total/semantics rows remained 0.
- Passive health at `2026-06-19T01:23:30Z` still failed `[74]` (`attempts=200`, `postonly=26`, `max_pending=0`) and `[56]` (`authorization_json_missing`). Boundary: docs/TODO/report + read-only Linux file/PG/healthcheck only; no CI/cargo/Linux build/deploy/rebuild/restart/DB write/Bybit private call/credential/runtime/auth/risk/order/trading mutation/probe/archive/promotion.

## 2026-06-19 TODO v224 Stage0R Current-Head Wrapper True-PG Rerun

- Refreshed `P1-A1A2-STAGE0R-RUNNER-IMPL` with current-head Linux true-PG read-only wrapper evidence, superseding the stale "no new true-PG rerun beyond v217 artifact" caveat without closing the row.
- Linux canonical `trade-core` was `HEAD=origin/main=e69d5fd3`; run dir `/tmp/openclaw/stage0r_current_head_verify_20260619T011508Z`; `PGOPTIONS="-c default_transaction_read_only=on"` with DB URL/password env deliberately unset.
- Evidence: 8b row_count=8034 / eligible=false / `no primary-horizon signals`; alpha_candidate `observe_more` / `stage0_ready=false` / A1 `draft_only` / A2 `observe_more`; standalone 8c `RED` / `review_ready=true` / total_rows=291 / total_bucket_count=2924 / long=164 / short=121 / missing-denominator scan=0.
- Boundary: no full CI/cargo/Linux build/deploy/rebuild/restart/DB write, no repo artifact write beyond docs, no Bybit private call, no credential mutation/auth/risk/order/trading mutation; trusted promotion packet, full E4 review, QC/MIT/QA sign-off, Stage0R promotion, P0-EDGE, and operator gates remain open.

## 2026-06-19 TODO v223 Source-Sync Correction

- Corrected source-sync metadata after v222 Earn first-stake routing review.
- Mac `HEAD=origin/main=712d3a03` and Linux `trade-core` `HEAD=origin/main=712d3a03`; Linux tracked checkout was clean except existing unrelated untracked `vol-event-robust-ruling.md` and `variance_risk_premium/`.
- Watchdog read-only status: `engine_alive=true`, demo snapshot age `9.6s`.
- Boundary: docs/TODO metadata only; no CI/cargo/Linux build/deploy/rebuild/restart/DB write/Bybit private call/credential mutation/auth/risk/order/trading mutation; no active gate closed.

## 2026-06-19 TODO v222 Earn First-Stake Capability Routing Focused Review

- Refreshed PM-local evidence for `P1-EARN-WAVE-C-FIRST-STAKE-RUNTIME` without closing the runtime/first-stake row.
- Source review confirms bootstrap injects `BybitEarnClient` and `EarnMovementWriter` from existing runtime handles only, missing deps still fail closed as `earn_dispatch_unwired`, Rust IPC routes `process_earn_intent` into the event-consumer owner task, and Python `/api/v1/earn/stake` sends `engine="live"`.
- Focused checks passed: `process_earn_intent_command` 2, `process_earn_intent` 4, `earn_router_fail_closed_when_unwired` 1, Python Earn route suite 28 with one existing Pydantic warning, and `cargo clippy -p openclaw_engine --lib -- -D warnings`.
- Boundary: no full CI/Linux cargo/deploy/rebuild/restart, no real Bybit call, no credential/key/secret mutation, no runtime DB write, no auth/risk/order/trading mutation, and no first-stake evidence. OP-1/2/3 plus review/deploy/restart remain open.

## 2026-06-19 TODO v221 D2 Audit Semantics Focused Review

- Refreshed PM-local evidence for `P3-110017-D2-AUDIT-REMOVED-SEMANTICS` without closing the row.
- Source review confirms D2 dispatch uses `PipelineCommand::ConvergeExchangeZero` rather than `CloseSymbol`, dispatch-site audit rows use `confirmed=false` / `dispatched-not-confirmed`, handler-confirmed wording is reserved for handler-side fact, and `converge_exchange_zero_close` removes local drift plus clears pending close without synthetic PnL/Kelly pollution.
- Focused checks from `srv/rust` passed: payload semantics tests 2, orphan_handler suite 19, loop-break regression 1, ghost suite 11, and `cargo clippy -p openclaw_engine --lib -- -D warnings`.
- Linux read-only DB count still showed `reconcile_ghost_converge` total=0 / semantics_rows=0, so production event proof remains open. Boundary: no full CI/Linux cargo/deploy/rebuild/restart/DB write/Bybit private call/auth/risk/order/trading mutation.

## 2026-06-19 TODO v220 Reconciler Pagination Focused Review

- Refreshed PM-local evidence for `P2-RECONCILER-GET-POSITIONS-PAGINATION` without closing the row.
- Source review confirms full-scan `get_positions(None)` uses `settleCoin=USDT` + `limit=200` pagination, normalizes empty/missing cursor to None, fails closed on same-cursor response, maps the client-side invariant as Structural / sync-untrusted, and keeps the ghost point-query gate load-bearing against pagination-truncated false ghosts.
- Focused checks from `srv/rust` passed: `position_manager::tests` 19, dispatch invariant mapping 1, exchange-stop invariant mapping 1, false-ghost regression 1, `position_reconciler::tests::ghost` 11, and `cargo clippy -p openclaw_engine --lib -- -D warnings`.
- Boundary: initial wrong-root cargo invocation failed before tests and was rerun correctly; no full CI/Linux cargo/deploy/rebuild/restart/DB write/Bybit private call/auth/risk/order/trading mutation. Formal BB/E2/E4/QA review and production event proof remain open.

## 2026-06-19 TODO v219 Stage0R 8c E4 Focused Regression

- Reduced the open `P1-A1A2-STAGE0R-RUNNER-IMPL` E4 denominator-fix review risk with a focused local regression report, without closing promotion/trusted-runner authority.
- Evidence: py_compile PASS; 8c smoke_cli 11/11 twice; 8c metrics smoke twice; alpha_candidate smoke twice; 8b funding_skew smoke twice; `helper_scripts/lib/tests/test_stats_common.py` 33 passed.
- Source inspection confirms the 8c wrapper now passes raw 5m `total_bucket_count` to single/sweep metrics, metrics still fail-close when omitted, and smoke coverage checks both paths.
- Boundary: no full CI, no Linux full E4 suite, no new true-PG rerun beyond v217 PM artifact, no deploy/rebuild/restart/model call/DB write/auth/risk/order/trading mutation.

## 2026-06-19 TODO v218 Source-Sync Passive Watch Refresh

- Corrected TODO source HEAD from stale v216 `61e1a6d2` to v217 `737356a5`; Mac/origin/Linux are aligned at `737356a5`.
- Read-only passive recheck found no actionable event: Gate-B remains `WATCH_ONLY`, flash_dip entry is still `{}` with no death-rate success file, L2 cursor remains `2026-06-17` with zero material/stored days, and passive health still fails `[74]`/`[56]`.
- Boundary: docs/TODO + read-only Linux file/healthcheck only; no CI/deploy/rebuild/restart, no model call, no DB write, no auth/risk/order/trading mutation.

## 2026-06-18 Earn First-Stake Capability Routing

- Reduced `P1-EARN-WAVE-C-FIRST-STAKE-RUNTIME` source blocker without closing the runtime row.
- Rust event-consumer bootstrap now injects `BybitEarnClient` from `shared_client` and `EarnMovementWriter` from `audit_pool`; construction is handle-only and does not call Bybit/PG.
- Python `/api/v1/earn/stake` now sends `engine="live"` to `process_earn_intent`, so the operator/live_reserved asset-movement lane does not rely on primary fallback.
- Focused checks passed: Rust owner-task unwired/wired-gate regression, Rust IPC `process_earn_intent` selector, Earn router unwired selector, Python Earn route suite, rustfmt check, and `git diff --check`.
- Boundary: no real Bybit call, no key/secret mutation, no deploy/rebuild/restart, no runtime DB/auth/risk/order/trading mutation. Remaining: OP-1/2/3, review/deploy/restart, first real stake evidence.

## 2026-05-15 A4-C PM/PA/FA Unblock Engineering Card

- Operator asked PM/PA/FA to formalize the A4-C unblock path and start in
  order.
- PA proposed a bounded diagnostic revive path: read-only Stage 0R RCA,
  preregistered revision only if evidence supports it, then Stage 0R rerun.
- FA pushed back: A4-C does not currently justify 7d Demo micro-canary budget;
  it remains archived from active promotion because Step 5b has weak edge,
  failed PSR/DSR, CI lower < 0, and near-zero R2.
- PM decision: add `P1-A4C-RCA-1` as the single allowed read-only RCA path.
  No paper promotion, no demo launch, no gate relaxation, no runtime/auth/risk
  mutation. If RCA finds no new preregistered hypothesis, move alpha effort to
  W-AUDIT-8b / W-AUDIT-8a C1.
- RCA start result: current 7d dry-run fetched 6,713 rows and remained worse
  than Step 5b (`avg_net_bps=-1.0013`, `PSR(0)=0.1904`, `DSR=0`,
  R2(120)=0). Finite threshold probe X=5/Y=0.20 improved sample size and
  weakly positive average (`+1.4739 bps`) but remains far below +15 and below
  per-symbol +5 defer band. This strengthens the archive/default-switch read.

## 2026-05-15 TODO v30 Three-Side Source Sync

- Operator asked to update TODO and perform three-side sync.
- PM verified Mac `HEAD`, local `origin/main`, and Linux `trade-core` were
  clean/aligned at pre-v30 base `9a72d054` before the v30 docs update.
- Active docs still had stale sync wording: `CLAUDE.md` referenced
  `TODO.md v28`, while `CLAUDE.md` / `active-plan.md` referenced source sync
  `81bc0862`.
- Updated TODO to v30 and aligned `CLAUDE.md`, `active-plan.md`,
  `.codex/MEMORY.md`, `.codex/WORKLOG.md`, PM report index, and docs index.
- Boundary: source/docs sync only. No runtime rebuild/restart, DB write, auth
  renewal, production WS topic revival, paper enablement, demo canary, risk /
  sizing / config mutation, or live action.

## 2026-05-15 A4-C RCA Final + C1 Proof Start

- QC(default) and MIT(default) both rejected opening `P1-A4C-REV-1`.
- Final `P1-A4C-RCA-1` result: current A4-C feature shape stays archived from
  promotion. The 7d RCA was negative/weak (`avg_net_bps=-1.0013`,
  `PSR(0)=0.1904`, `DSR=0`, R2(120)=0), and the best finite X=5/Y=0.20
  probe was only `+1.4739 bps`, below revive/promotion bands.
- PM closed `P1-A4C-RCA-1` as no revive hypothesis found; do not run same-shape
  A4-C Stage 0R again unless a materially new predictive variable is
  preregistered in the future.
- C1 isolated smoke returned `SMOKE_PASS_NOT_C1_PROOF`. PM started the 24h
  standalone `allLiquidation.BTCUSDT` proof on `trade-core` at
  `2026-05-15T19:53:09Z`, PID `4100789`, log
  `/tmp/openclaw/audit/liquidation_topic_probe/nohup_20260515T195309Z.log`.
- C1 remains blocked until the 24h report passes and BB/MIT sign off; no
  production subscription, parser/writer revival, DB write, rebuild/restart,
  auth renewal, paper/demo launch, risk/sizing/config mutation, or live action.

## 2026-05-15 W-AUDIT-8b Review + Stage 0R Design

- QC(default), MIT(default), and BB(default) reviewed Funding Skew v0.1 and
  conditionally approved Stage 0R replay design only.
- No strategy implementation, demo launch, runtime config change, risk/sizing
  edit, production mutation, or funding-payment edge credit is authorized.
- Spec v0.2 locks: 30m primary horizon, 15m/60m sensitivity counted in K,
  crowded-long fade and crowded-short squeeze as separate branches,
  `K_total >= K_prior+4050`, `DSR>=0.95`, PBO fail-closed, raw
  `panel.funding_rates_panel` / `panel.oi_delta_panel` as-of joins,
  funding attribution `excluded`, and Bybit funding interval/source-mode fields.
- Runtime panel freshness probe at 2026-05-15 22:13 CEST passed:
  `funding=PASS(20929ms)`, `oi=PASS(20969ms)`.
- Next work is PA/E1 packet for a read-only `funding_skew_directional.v0_2`
  Stage 0R query/report only.

## 2026-05-15 close-maker-first Refactor PM Verdict

- 對主會話 3 輪對抗審 + DB/代碼核驗 + 5 gap 清單做 PM 治理驗證。
- Verdict: APPROVED-CONDITIONAL（純 spec/設計授權；IMPL 排 Sprint N+2，不 scope-in W3）。
- W3 scope-in 拒絕：W3-1/W3-2 ncyu-blocked、Stage 0R GATE-RED 雙鎖死、alpha-bearing pathway
  必走 AMD-2026-05-09-03 5-stage canary，當前在 Stage 0R 失敗下啟 IMPL 違反 §二 原則 #6。
- 例外授權：MA KAMA fallback warn! + skip entry（30 分鐘獨立修復）scope-in W3-6 by-the-way。
- Phase 命名 = EDGE-P2-3 Phase 1b（entry 1a 自然延伸到 close path 同 alpha 軸；
  Phase 1c 留給 resting orders microstructure 軸；EDGE-P2-4 留給 alpha source promotion gate）。
- AMD 要求：是。跨 §二 原則 #6 但不違反（whitelist 8 策略降 fee + 2 Market keep 保真風控）。
  AMD 必含 close path 為 alpha-bearing pathway 明文 + whitelist/keep 邊界 + phys_lock live

  決策分軌 + Stage 0R 先 replay preflight + compute_close_limit_price spec。
- 優先序: P1（非 P0）。理由：fee/cost 優化救不了 -110.43 USDT structural alpha deficit；
  排 Sprint N+2 backlog 在 N2-AUDIT-7c/8c/PhaseC/PhaseD 之後、P0 全 closed 前不啟 IMPL。
- phys_lock live 啟用決策歸 operator（PM 提案 + FA 規格 + QC 數學佐證），建議先 demo
  Stage 1 micro-canary 7d 證 Gate 4 phys_lock 真實 PnL 改善才提 live AMD。
- 補 governance gates: §二 原則 #4 Guardian veto 必過、DOC-08 §12.4 hard_stop 觸發
  cancel+Market re-submit replay 必驗、maker fill rate empirical baseline 必先採、
  compute_close_limit_price() spec PA 必出。
- 條件 4 條：PA spec 先出、AMD 經 QC+FA+BB+MIT 4-agent adversarial review、
  P0-EDGE-1+W-AUDIT-8b Stage 0R+W-AUDIT-8a C1 BB/MIT sign-off 三閘前不啟 IMPL、
  IMPL 走強制工作鏈不走 P0 快速通道。
- Report: docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-15--close_maker_first_pm_verdict.md

## 2026-05-16 v35 Current Progress Sync + Rebuild Decision

- Operator asked to verify progress, update TODO/CLAUDE/Codex memory, perform three-side sync, and rebuild if required.
- PM verified Mac had uncommitted WP-13 leftover P1 Rust changes from the Round 4 E2 RETURN. The fix is now committed as `a7cb517f`.
- Verification for `a7cb517f`: `cargo check --release -p openclaw_engine` PASS; `tune_cmd_snapshot` 2/2 PASS; `edge_reload_tests` 16/16 PASS; full lib PASS 2908/0/1 after escalated rerun for sandbox socket tests; bin PASS 62/0.
- C1 standalone liquidation proof ended early with `FAIL_CONNECTION` at `2026-05-16T00:37:25Z` after `17055.2s/86400s`; it saw 15 `allLiquidation.BTCUSDT` candidate messages but is not proof-eligible. C1 remains blocked until a full-duration BB/MIT-signed proof.
- Before sync, Linux `trade-core` was clean but behind origin; runtime engine/API were alive and binary still reflected the prior `7b33ab2e` rebuild. Because v35 contains Rust runtime changes, rebuild was required after sync.
- Deployment completed: runtime/code-bearing v35 head `5f6f3edf` synced across Mac/origin/Linux before rebuild; post-rebuild docs-only sync may advance repository HEAD without another rebuild. `trade-core` ran `PATH=$HOME/.cargo/bin:$PATH bash helper_scripts/restart_all.sh --rebuild --keep-auth` successfully; post-rebuild engine PID `69581`, API PID `69674`, watchdog `engine_alive=true`, demo fresh.
- Runtime caveats after rebuild: signed live auth is absent and was not renewed by `--keep-auth`, so live remains inactive/blocked. `OPENCLAW_ENABLE_PAPER=0`; engine log says paper pipeline disabled and `paper_state.disabled=true`, so the fresh paper marker is disabled-state output, not active Paper trading.
- Report: `workspace/reports/2026-05-16--v35_three_side_sync_rebuild.md`.

## 2026-05-16 TODO v36 Completion Cleanup

- Active TODO was promoted to v36 after v35 rebuild. Completed v35 / 2026-05-15..16 detail was cross-checked against commits and PM/E2/E4/BB reports, then moved to `docs/archive/2026-05-16--todo_v36_completion_cleanup_archive.md`.
- Active TODO now keeps blockers, dependent gates, deferred work, and runnable backlog only. Runtime/code-bearing rebuild head remains `5f6f3edf`; this cleanup is documentation-only and does not require another rebuild.
- E2/BB `BB-MF-3` review found `arm_close_cooldown` plumbing and tests landed, but no production caller yet; keep `P1-BBMF3-WIRE-1` active for Phase 1b rather than archiving it as completed.
- Current blockers remain: W-AUDIT-8a C1 is not proof-eligible after `FAIL_CONNECTION`; true-live remains blocked by `P0-EDGE-1`, `P0-LG-1/2/3`, and `P0-OPS-1..4`.

## 12-Agent Full System Audit Sign-off (2026-05-16)

- PA consolidated 12 parallel audit agents (FA/AI-E/QC/E5/A3/E3/MIT/R4/BB/CC/E4/TW) into
  13 WPs across 4 waves. PM APPROVED-CONDITIONAL.
- 5 PM reprioritizations applied:
  1. WP-02 Donchian P0->P1: runtime already calls `donchian_prior()` since `75741eff`; the base
     `donchian()` retaining current-bar is hygiene, not live P0.
  2. WP-08 MIT-P0-2 "6/12 cron not installed" conflicts with TODO P0-V3-CRON-NOT-INSTALLED DONE;
     PA must reconcile before dispatch.
  3. AI-E-F-01 daily_usd_max $100->$2 requires operator decision, not auto-fix.
  4. R4 "CRITICAL" doc drift (14 ADR -> 22, 13 tab -> 16) downgraded to P2.
  5. WP-06 recommended split into WP-06a/b/c (Rust/Python/orjson) for parallel dispatch.
- True P0 items: WP-01 GUI Safety (A3-BLOCKER-1/2 emergency stop one-click) + P0-EDGE-1 (structural).
- Effort estimate: 12-15 sessions (optimistic 10 / pessimistic 18).
- Conflict guard: Wave 2 WP-03 (grid_helpers.rs) must land BEFORE EDGE-P2-3 Phase 1b IMPL;
  WP-06 performance must wait until Phase 1b stabilizes.
- Key lesson: 4 of 14 original P0/CRITICAL findings were false elevations (by-design pre-live state
  or deprecated strategies). PA's verification layer correctly caught all 4. Reinforces the principle
  that audit agents should distinguish "not yet implemented" from "broken/missing".
- TODO updated to v33 with new section 11.6 (13 WPs + wave assignments).
- Approved report: `srv/2026-05-16--full-system-audit-fix-plan.md` (PM sign-off appended).
- Report: docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-16--12-agent-audit-pm-signoff.md

## 2026-05-16 Stage 1 Demo + A4-C Tombstone Cleanup

- Operator confirmed paper should not be promotion evidence; promotion must rely
  on Demo. PM cleaned active docs accordingly.
- Active docs now keep Stage 1 as Demo-only after future green Stage 0R. There
  is no active W3 paper cohort marker.
- A4-C is tombstoned in active docs: keep `panel.btc_lead_lag_panel` and `[57]`
  for diagnostics only; do not use A4-C as Stage 0R promotion candidate or
  Stage 1 Demo cohort source.
- Detailed A4-C Step 5b/RCA evidence remains archived; active TODO keeps only
  the guard to prevent accidental revival from old specs.
- No runtime, DB, auth, risk, strategy, paper, demo, LiveDemo, or live mutation.
- Report: docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-16--stage1_demo_a4c_tombstone_cleanup.md

## 2026-05-16 Option A Phase 1b + W-AUDIT-8b IMPL Closure

- Operator selected Option A: dispatch Phase 1b Worktree B and W-AUDIT-8b Round 2 Phase A in parallel.
- W-AUDIT-8b v0.3 4-cell sweep tooling landed at `a6e17d5d` after E1 -> A3/E2 -> E4 PASS.
- Phase 1b close-maker-first source/test bundle landed at `ea4ceca6` after E1 rounds 1-3 -> A3/E2 -> E4 PASS.
- No deploy, production SQL migration, runtime restart, auth mutation, paper enablement, live/mainnet enablement, or production `allLiquidation` subscription.
- Report: docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-16--option_a_phase1b_w_audit8b_impl_closure.md

## 2026-05-17 W-AUDIT-8c Correction Source/Test Closure

- C1 v2 proof passed technically, but production liquidation writer revival remained blocked by MIT's lossy `(symbol, ts, side)` idempotency condition.
- W-AUDIT-8c correction source/test is now done: V095 source migration uses `(symbol, ts, side, qty, price)`, parser/writer fail closed for invalid `allLiquidation` rows, and corrected Bybit side mapping is tested (`Buy` long liquidation / `Sell` short liquidation).
- BB approved the correction patch; E2 approved conditionally on excluding unrelated GUI dirty files; MIT still requires Linux PG dry-run x2, V095 apply authorization, and re-sign before production writer/topic revival.
- No deploy, Linux DB apply, runtime restart, auth mutation, paper/live/mainnet enablement, strategy/risk mutation, or production `allLiquidation*` subscription happened.
- Report: docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-17--w_audit_8c_correction_source_test_closure.md

## 2026-06-04 Alpha-Edge P1 EvidenceManifest Gate

- EvidenceManifest 的 PM 原則：不能只落成 JSON / lineage 文檔；若 producer 不檢查、LG-5 不重驗，對 alpha promotion 幾乎等於沒有 gate。
- 本批完成 source/test/docs-only fail-closed 接入：MLDE live-candidate producer 與 LG-5 reviewer 都要求 canonical `candidate_evidence_manifest` + valid `demo_residual_alpha_report`，missing / alias / invalid / research_only / pending_schema 都不可 create/approve live candidate。
- 保留現實邊界：這不代表 hidden OOS registry 或真實 manifest producer 已完成；缺 manifest 的真實 upstream row 會被阻斷，而不是被自動修補。
- Report: docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-04--alpha_edge_p1_candidate_evidence_manifest_gate.md

## 2026-06-11 派工四態契約生效

- subagent 回報首行 STATUS 四態；處置表=DONE 驗收 / DONE_WITH_CONCERNS 讀 concerns 補驗 / NEEDS_CONTEXT 補 context 重派（可同模型）/ BLOCKED 換強模型、拆任務或升級 operator，禁無變更同模型裸重試；餵全文 + 共享 contextPath SOP 入 PM.md「派工四態契約與升級階梯」，agent-wave 自動 append 契約 footer 並回傳 statuses 索引。

## 2026-06-11 AEG-S3 + Claude Tooling 三端同步

- Operator 要求「三端同步」。本批同步範圍：Claude hooks/rtk/four-state contract/skill trigger rewrite + AEG-S3 candidate direct rows、listing_fade、oi_delta artifact-only evidence producers。
- AEG-S3 驗證：focused regression（listing fade + oi_delta + candidate rows + candidate metrics + robustness + Gate-B probe）= 70 passed；compileall OK；static forbidden-route search 新模組無 runtime/DB/Bybit route。
- Claude tooling 驗證：`bash -n` hooks、`node --check .claude/workflows/agent-wave.js`、`.claude/settings.json` JSON parse OK；secret-pattern 搜尋只命中文檔/技能中的安全詞與路徑說明。
- 邊界：docs/tooling/research artifact sync only；不重啟 runtime、不 rebuild、不改 DB/auth/risk/trading。P5-SM soak 繼續跑；AEG-S3 尚未產真候選 promotion proof，下一步仍是 Gate-B true transition artifact、V125 OI/price/regime export、candidate-grid PBO、funding_revive producer、E2/MIT/QC 審。

## 2026-06-12 AEG-S3 event breadth funding matrix

- `8fed7073` 新增 AEG-S3 event breadth adapter：funding/listing 單 symbol event evidence 可用 FND-2 PIT tiers 產真 `breadth_ladder`；`oi_delta` basket evidence 明確 fail-closed。
- Linux funding_revive event breadth `aeg_s3_funding_revive_event_breadth_v125_20260611T200033Z_oos20260301_pbo18` healthcheck PASS，full_survivorship breadth=829/delisted=255/n_independent=261；formal matrix 24 rows，coverage PASS、survivorship `pit_fnd2_delisted_proof`，但 DSR=0/PBO=0.54583333/execution unverified → 仍 non-promotable。

## 2026-06-12 P2 batch activation partial

- owed #3 Bybit 公告哨兵與 owed #4 Polymarket daily artifact cron 已在 `trade-core` 安裝並手動驗證；Bybit formal data-dir run 50 items/0 alerts，Polymarket `daily-20260612T090806Z` 6100 rows/0 errors。
- owed #2 V138/V139 與 owed #5/#6 L2 activation 未跑：checksum drift=0、prod head=137，但 P5-SM `[82]` soak 仍 accumulating（31.2h<48h，934 probes），migration 唯一路徑需 engine restart，故依 survival/system-health 邊界停在 A/B 前。

## 2026-06-12 AEG-S3 empirical execution realism + Gate-B watch

- `c35f8425` 新增 artifact-only AEG-S3 event execution realism adapter：`listing_fade` / `funding_revive` candidate evidence 可用 matched execution-observations JSONL 產 canonical `execution_realism.json`；`oi_delta` basket 明確 fail-closed。
- Gate-B 等待口徑改為事件觸發：現官方 new listing 最新批為 2026-06-09 已 open perpetual，live PreLaunch 只有老 `BPUSDT`（ContinuousTrading since 2026-03-16）；下一步盯 BPUSDT conversion 或下一個 fresh Pre-Market/PreLaunch 公告，再開 isolated 24h probe。

## 2026-06-12 AEG-S3 sidecar matrix wiring

- `66a9e511` 讓 `aeg_s3_matrix_inputs` 可直接引用既有 `breadth_ladder` / `execution_realism` sidecar artifact；缺 sidecar 時原 fail-closed placeholder 不變，candidate/parameter mismatch 直接 fail-closed。
- Mac/Linux focused regression 各 `24 passed`；Linux true funding_revive sidecar matrix smoke row_count=24、coverage PASS、survivorship `pit_fnd2_delisted_proof`、execution 仍 `unverified_missing_missing`，所以仍 non-promotable。

## 2026-06-12 AEG-S3 execution observations producer

- `9eaad929` 新增 artifact-only `aeg_s3_execution_observations`：把 `listing_fade` candidate evidence + Gate-B run 轉為 matched `execution_observations.jsonl`，供 `aeg_s3_event_execution_realism` 使用。
- 邊界：只支援 Gate-B listing_fade；funding_revive/oi_delta 不冒充；source 是 publicTrade prints only，不宣稱 orderbook-depth fill realism。
- Mac/Linux focused regression 各 `31 passed`；Linux old Gate-B smoke `listing_24h_20260602_1847` 只產 2 matched observations，execution realism 10 USDT FAIL=樣本不足+participation，1 USDT FAIL=樣本不足。producer 已接通；promotion 仍需 fresh Gate-B `>=30` matched samples 後重跑 formal matrix。

## 2026-06-12 AEG-S3 Gate-B evidence chain wrapper

- `75ed19c8` 新增 artifact-only `aeg_s3_gate_b_chain`：fresh Gate-B run 後一鍵編排 listing evidence、candidate rows、candidate metrics、execution observations、event execution realism；若提供 FND2+regime，再接 event breadth + formal matrix。
- Mac/Linux focused regression 各 `52 passed`；Linux true smoke `aeg_s3_gate_b_chain_listing_smoke_20260612` 用舊 run 產 2 listing samples / 2 execution observations，chain_status=`COMPLETE_EXECUTION_REALISM_FAIL`，reject=`sample_count_below_30`。
- 邊界：wrapper 只編排既有 artifact harness，不收集資料、不呼叫 Bybit、不寫 DB、不碰 runtime；wrapper 完成不是 promotion proof，fresh Gate-B 仍需 `>=30` matched samples + E2/MIT/QC 審。

## 2026-06-12 AEG-S3 listing_fade PBO grid wiring

- `3d03698c` 讓 `listing_fade` PBO candidate grid 變成明確 opt-in：`--include-default-pbo-grid` / `--pbo-grid-json`，默認不偽造 PBO，grid 不足 10 cells 時 fail-closed。
- Gate-B chain 已 pass-through PBO knobs 並輸出 `listing_pbo_status`；Linux old-run smoke 產 `produced_candidate_grid`，但仍因 sample_count=2 fail `sample_count_below_30`。
- Mac/Linux focused regression 各 `54 passed`；compileall/static scan OK；本批無 CI、無 deploy/rebuild/restart、無 DB/auth/risk/trading mutation。

## 2026-06-12 AEG-S3 Gate-B full matrix PBO readiness

- `235858f4` 固化 Gate-B chain full formal matrix 分支也必須攜帶 listing_fade PBO：test 斷言 `listing_pbo_status=produced_candidate_grid`、candidate rows `pbo_status=measured`。
- Linux final smoke 用 old Gate-B + 真 FND2/regime 跑完整 chain：formal matrix row_count=12、coverage PASS、survivorship `pit_fnd2_delisted_proof`、final labels 7 insufficient / 5 kill，chain_status non-promotable 只因舊 run sample_count=2。
- 結論：fresh Gate-B 到來後的 execution + event breadth + formal matrix + PBO 全鏈已可執行；promotion 仍需 fresh `>=30` matched observations + E2/MIT/QC。

## 2026-06-19 Vol-Event Robust Ruling Evidence

- Linux vol-event cron 自動產出 high-vol robust ruling：4 independent high_vol events（3 downside / 1 upside_squeeze），0/4 survives fee wall，robust ruling `NO_EDGE_SURVIVES`。
- PM 收錄為 dated repo report `docs/CCAgentWorkSpace/E1/workspace/reports/2026-06-18--vol-event-robust-ruling.md` 並更新 TODO v216；這是 evidence trace，不是 QC final promotion verdict。
- 邊界：docs/report only；無 runtime/DB/auth/risk/order/trading mutation，P0-EDGE/Gate-B/flash/L2/operator gates 不因此關閉。

## 2026-06-19 Stage0R 8c Denominator + PM Runtime Verification

- PM runtime verification of Stage0R report wrappers found standalone 8c no-sweep emitted `missing_bucket_count_denominator`; alpha_candidate A2 adapter already passed the denominator.
- Source fix: `w_audit_8c/liquidation_cluster_stage0r_report.py` now queries raw 5m liquidation `total_bucket_count` and passes it into single/sweep metrics; smoke_cli pins the no-missing-denominator invariant.
- Linux `/tmp` temp clone true-PG post-fix run `stage0r_8c_denominator_fix_20260619T001027Z` produced `RED`/`review_ready=true`, total_rows=291, total_bucket_count=2931, long=164, short=121, missing_denominator=false.
- TODO advanced to v217. PM formal runtime verification is done; E4 review remains open before trusting Stage0R runner outputs. No deploy/rebuild/restart/runtime/DB/auth/risk/order/trading mutation.

## 2026-06-12 AEG-S3 Gate-B preflight locator

- `44a30afa`/`f4a58b3c` 新增 artifact-only `aeg_s3_gate_b_preflight`：定位 Gate-B/FND2/regime，preview listing sample/PBO，輸出 full-chain command；auto locator 要求 FND2/regime summary 語義驗證。
- Mac/Linux focused regression 各 `58 passed`；Linux explicit/auto smoke 均回 `READY_BUT_SAMPLE_BELOW_GATE`、sample_count=2、pbo_status=`produced_candidate_grid`、recommended command generated。
- fresh Gate-B 後先跑 preflight，再按 generated command 跑 full matrix；preflight ready 不等於 promotion proof。

## 2026-06-12 AEG-S3 Gate-B watch preflight bridge

- `2b880f5d` 讓 `aeg_s3_gate_b_preflight` 讀 local `gate_b_watch_latest.json`，輸出 `gate_watch.operator_action` 與 `probe_command_hints`；`WATCH_ONLY` wait-only，`ACTIONABLE_*` 才給 isolated probe hint，stale/malformed/source failure fail-closed。
- Mac/Linux focused regression 各 `62 passed`；Linux smoke 讀 live watch artifact 得 `WATCH_ONLY`、23 candidates、0 alertable/start/schedule、operator_action=`WAIT_FOR_ACTIONABLE_WATCH`、old Gate-B sample_count=2。

## 2026-06-12 AEG-S3 Gate-B preflight command guard

- `289fcbe8` 將 Gate-B preflight 升 v0.3：`recommended_command` 增加 operator guard，wait-only + sample<30 時輸出 `operator_recommended=false` / `HOLD_WAIT_FOR_ACTIONABLE_WATCH`，防止舊 full-chain shell 被誤當當前 action。
- Linux 同步後 focused preflight 8 passed；live smoke 仍 `WATCH_ONLY`、23 candidates、0 alertable、sample_count=2；P5-SM `[82]` 2026-06-12T21:00Z 為 `43.0h<48h`、probes=1290，約 2026-06-13 03:59:37+02 到期。

## 2026-06-12 P5-SM [81]/[82] selector fix

- `bf673cdc` 修好 `passive_wait_healthcheck.runner --check 81 --check 82` narrow routing；只改 CLI selector dispatch，不改 `[81]/[82]` 判定邏輯。
- Mac/Linux `test_lease_ipc_soak_healthcheck.py` 各 `47 passed, 1 skipped`；Linux true DB smoke 現正常輸出 `[81] PASS`、`[82] 38.7h<48h` accumulating。

## 2026-06-12 P2 incident-policy dispatch trigger source-state checkpoint

- TODO 原 row「PA 規格完成 / 待實作」已 stale。Source 已有 `notification_failsafe/incident_policy.rs` CORE ledger、auth invalid producer、Bybit fail-closed producer、C4 incident-policy E2E；本輪 PM 修正 TODO 狀態為 partial source-live。
- Focused Rust verification on Mac and Linux: incident_policy `15 passed`; C4 failsafe wire `4 passed`; ret_code_counter `6 passed`.
- Remaining honest gaps: `sm_halt_stuck`、`position_drift`、external `engine_dead` watchdog notify-only producer coverage still pending; BB/E2/E4/QA full review still needed before declaring fail-safe runtime-complete. No CI/deploy/rebuild/restart/DB/auth/risk/trading mutation.

## 2026-06-12 P2 incident-policy BB/E2 review checkpoint

- BB `APPROVE-WITH-CONDITIONS` + E2 `PASS-WITH-CONDITIONS` for existing CORE+auth+Bybit source-live path; 0 blocker/high/medium.
- Boundaries preserved: `incident_policy` does not add Bybit requests or direct risk/system/auth mutation; C4 owner handler remains the only `set_trading_stop` side-effect path; `bybit_fail_closed` wording must stay business-retCode fail-closed, not full exchange-outage coverage.
- TODO v141 marks the ticket as BB+E2 reviewed partial. Next recommended slice: remaining producer coverage, starting with `sm_halt_stuck` arm-class, then `position_drift` / `engine_dead` notify-only.

## 2026-06-12 P2 incident-policy sm_halt_stuck producer slice

- `sm_halt_stuck` is now source-live via `event_consumer/sm_halt_incident.rs`; producer reads `TickPipeline.halt_kind` + `halt_set_ts_ms` as runtime source-of-truth, not stale passive healthcheck `[69]`.
- Hook points: after each `pipeline.on_tick()` and after the 60s lease/auth sweep; active HaltSession feeds `IncidentClass::SmHaltStuck` at 5s cadence and clears with `report_resolved` once `halt_kind` clears. Operator IPC pause remains excluded because it has `halt_kind=None`.
- Mac focused Rust: `sm_halt_incident` 5 passed; incident_policy 15 passed; C4 wire 4 passed; halt_ttl 20 passed; ret_code_counter 6 passed.
- TODO v142 keeps ticket partial: prior BB/E2 review covers CORE+auth+Bybit only; the new `sm_halt` producer still needs BB/E2/E4/QA/full-chain review, and remaining producers are `position_drift` notify-only plus external `engine_dead` watchdog notify-only. No CI/deploy/rebuild/restart/DB/auth/risk/trading mutation.

## 2026-06-12 P2 incident-policy position_drift producer slice

- `position_drift` is now source-live via `position_reconciler/incident.rs`; producer observes post-classification/post-orphan-ghost unresolved drifts before baseline update.
- Semantics: actionable = MajorDrift/SideFlip/Orphan/Ghost, MinorDrift ignored; startup grace does not accumulate; persistent threshold is existing `PERSISTENT_DRIFT_CYCLES=3`; clear path calls class-scoped `report_resolved`.
- Boundary: `IncidentClass::PositionDrift` remains policy-level `NotifyOnly`, so no C4 AllFail feed or watcher timer arm; no `PipelineCommand`, RiskGovernor, auth, DB, order, or exchange write path changed.
- Mac+Linux focused Rust: `position_reconciler::incident` 6 passed; `position_reconciler` 94 passed; incident_policy 15 passed; touched-file rustfmt and `git diff --check` passed. TODO v143 remains partial: new `sm_halt` + `position_drift` slices need BB/E2/E4/QA/full-chain review; external `engine_dead` watchdog notify-only remains unwired.

## 2026-06-12 L2 root TODO tail triage

- Root `L2_TODO.md` is not completed-archive eligible: V138/V139 activation, E2E-1, P2p sentinel operator gates, and P5 remain open. PM mirrored the uncovered tails into TODO v149 `P1-L2-ADVISORY-MESH-TAILS`; no runtime mutation/model call/deploy occurred.

## 2026-06-13 A1 basis / P2 OPS / P3 forward recorder

- A1 basis formal gate matured: `panel.basis_panel` span=14.001d, Stage0R functional path verified with `infra_gap=false`, but A1 remains `draft_only` because `no_a1_signals_after_entry_gate` and `n_eff=0`; next A1 check is event-triggered, not a passive date wait.
- P2 OPS pg_dump/passive health tests closed; P3 ticker forward recorder source landed for nullable mark/index/funding/OI, deploy-gated and forward-only.

## 2026-06-12 Documentation governance first batch

- PM -> R4/CC/FA -> PA -> PM 审阅确认：Markdown 历史证据不做删除；第一批只做 active/history 边界降权、routing banner、initiative index、audit folder semantics 和未跟踪 `.DS_Store` 清理。
- 修正高风险 stale 指针：`L2_TODO.md` 不再是 active queue；funding_short 永久 DOA 与 Linear-only active 仅保留为历史，当前 authority 指向 TODO / `.codex/MEMORY.md` / `docs/agents/issue-tracker.md`。

## 2026-06-12 Documentation governance second batch

- 第二批确认策略：入口瘦身、目录 README、摘要库存和点名旧文档降权；继续不删除 Markdown、不批量移动 role reports。
- `docs/README.md` 只做 router，长索引归 `docs/_indexes/document_index.md`；`document_inventory.json` 只作规模/导航摘要，不作删除判据。
- 旧 Linear-only、L2 active stub、Paper promotion、3E-ARCH/v5.8 frozen module 语义必须在正文层明确 historical/reference，不能只依赖顶部 banner。

## 2026-06-13 P5-SM [82] clean closure

- `[82]` step-ii 48h soak gate 在 Linux 真 DB healthcheck 2026-06-13T02:05:59Z 關閉：window=48.1h、probes=1442、success_rate=1.0000、0 flag-OFF/regression/fail-streak；watchdog read-only `engine_alive=true`。
- Closure 只解除 `[82]` blocker；未 deploy/rebuild/restart、未套 V138/V139、未啟 L2 activation。step-iii cutover 與 P2 activation 仍需 operator-gated 低風險窗口。

## 2026-06-13 L2 activation preflight selector fix

- `[82]` 到時後 read-only preflight confirmed live DB head=V137, V138/V139 objects absent, activation flags off, Gate-B latest still WATCH_ONLY. Fixed passive healthcheck narrow selector gap so `[83]-[89]` can be run directly before V138/V139 activation.
- Post-sync Linux run of `--check 83..89` returned `SUMMARY: ALL PASS`: V138 checks PASS-skip, V132 sealed regression 0, L2 memory flags OFF PASS-skip.

## 2026-06-13 L2 V138/V139 activation-window packet

- V138/V139 activation is ready for an operator-approved window but not executed. Linux read-only baseline 2026-06-13T07:44Z: head=V137/all_success=true, checksum drift=0, V138/V139 objects absent, `OPENCLAW_AUTO_MIGRATE=0`, L2 memory/alpha wealth flags OFF, `[83]-[89]` true DB preflight `SUMMARY: ALL PASS`.
- Accepted path is engine auto-migrate only: temporarily persist `OPENCLAW_AUTO_MIGRATE=1`, run `restart_all.sh --engine-only --keep-auth`, restore flag to 0, then verify head=139/checksum/objects/healthcheck/watchdog. Raw `psql -f` for V138/V139 is forbidden because it bypasses `_sqlx_migrations`; V140/seed/pipeline/model/Gate-B remain separate approvals.

## 2026-06-13 L2 V138/V139 runtime activation

- Operator approved and PM executed V138/V139 engine-only auto-migrate: run `l2_v138_v139_activation_20260613T153352Z`, new engine PID 3607315, auto_migrate `Applied(2)`, `_sqlx_migrations` head=139/all_success=true/count=122, checksum drift=0, V138/V139 objects exist, new rows 0, `[83]-[89]` post-check `SUMMARY: ALL PASS`.
- Persistent `OPENCLAW_AUTO_MIGRATE=0` restored and maintenance flag absent. Current process env still has `OPENCLAW_AUTO_MIGRATE=1` because that process was started for the migration; no further migration runs until restart, and future restart reads persistent 0. Remaining L2 gates after seed: manual V140, memory pipeline/cron/embed flags, E2E model call, P2p/P5.

## 2026-06-13 L2 memory B1 seed dry-run

- Ran `seed_agent_memory.py --dry-run` on Linux after V139: B source parsed 93 `memory/MEMORY.md` candidate rows, skipped 6 by sensitive/allowlist rules, A source `agent.lessons dead_mode` deferred by dry-run contract; read-only SQL confirmed dead_mode count=6 and `agent.agent_memory` stayed 0 rows.
- Dry-run artifact `/tmp/openclaw/l2_memory_b1_seed_dry_run_20260613T161740Z.log` sha256 `f06a301a97f012dbe8a9a5030e266cc0652e35b61e55aaf3b134493667023950`; focused verification `test_seed_agent_memory.py` 39 passed. The separate `--apply` approval was later granted and closed by B2 below.

## 2026-06-13 L2 memory B2 seed apply

- Operator approved bounded DB write; PM ran `seed_agent_memory.py --apply` on Linux: run `l2_memory_b2_seed_apply_20260613T163835Z`, log `/tmp/openclaw/l2_memory_b2_seed_apply_20260613T163835Z.log`, sha256 `4b050252c803b193862d3758cf01d1ebb17fd907371369201e05f6764393a02c`.
- Result: A=6, B=93, inserted=99, already_present=0, recall verify en/zh hits=5/5. Post DB: `agent.agent_memory` total=99, duplicate_record_ids=0, active=99, embedding_pending=99; L2 memory pipeline/cron/embed/recall flags remained unset at B2 time; `[83]-[89]` PASS and engine PID 3607315 stayed alive. Manual V140 and FTS-only pipeline were later closed below; embed backfill/model-call/P2p/P5 remain separate gates.

## 2026-06-13 L2 V140 + FTS-only pipeline activation

- Operator instructed "V140 first, then L2"; PM applied manual V140 via `apply_manual_V140_agent_memory_vector.sh`: run `l2_manual_v140_apply_20260613T164628Z`, sha256 `3ccc6dc3ebcc69e0ee80027536a6d7d3325e6adc4a00d66279a45155bab07beb`; result `vector` extension 0.8.1 installed, `agent.agent_memory.embedding=vector(1024)`, HNSW index exists, sqlx head remains 139 by design.
- Activated L2 FTS-only daily cron: smoke run `l2_pipeline_ftsonly_smoke_20260613T164831Z` processed 2026-06-12 as no-op (`l2_calls=0`, DRAR=0, stored=0) and advanced cursor to 2026-06-12; cron install run `l2_memory_cron_install_20260613T164901Z` installed daily 05:23 UTC with `OPENCLAW_L2_MEMORY_PIPELINE=1`; active `[83]-[89]` PASS, `[88] rows=99 last_success=2026-06-12 lag_days=1`, `[89]` embed backfill OFF PASS-skip. `bge-m3` is absent in Ollama, so embedding backfill remains gated/off; engine PID 3607315 stayed alive.

## 2026-06-13 L2 embedding backfill activation

- Pulled `bge-m3` on Linux Ollama and ran bounded embedding backfill for seeded memory rows: `l2_embedding_backfill_20260613T170015Z`, sha256 `109aa15dcb540ce7428713b36628034ca9b53652c2caaf5ead88737c83aa8833`, result `embedded=99/status=ok`, probe dims=1024.
- Updated the existing L2 daily memory cron to include `OPENCLAW_L2_MEMORY_EMBED_BACKFILL=1`: `l2_memory_cron_embed_flag_20260613T170044Z`, sha256 `75de04eaf9e0434d984a99651b325e868ea3ece732f51246941708324303a33d`.
- Post DB: `agent.agent_memory` total=99, embedding_pending=0, embedding_not_null=99, dims=1024, meta=`ollama|bge-m3|1024`; Linux `[83]-[89]` PASS and focused source regression `94 passed`. No CI/deploy/rebuild/restart/B3/Gate-B/auth/risk/order/trading mutation; engine PID remained 3607315.

## 2026-06-13 L2 B3 recall source wiring

- Completed B3 recall source wiring for both mainline `layer2_engine` and guest-line `l2_ml_advisory_executor` via new `l2_memory_recall_context.py`. Flag contract is `OPENCLAW_L2_MEMORY_RECALL=0|shadow|1`: default `0` does no import/DB read, `shadow` computes bundle but only writes `memory_recall_shadow` metadata into existing D3 `input_context`, and `1` injects stable/recent blocks into prompt.
- Focused regression `92 passed` covering memory recall helper, `memory_distiller.recall`, D3 engine wiring, P3a ml_advisory, and P3b hypothesize. No CI/deploy/rebuild/restart/runtime flag enablement/DB/cron/Gate-B/auth/risk/order/trading mutation; engine PID remained 3607315 until a future deploy/restart.

## 2026-06-13 V5.8 pause readiness + alpha/edge handoff

- Added artifact-only `helper_scripts/research/v58_pause_readiness/` checker for V5.8 pause/resume: validates design/governance anchors, M1-M13 scaffold, freeze/unfreeze gate, V### numbering reality, LAL/M5/M12 fail-loud posture, and optional Gate-B watch context.
- True repo + Linux Gate-B latest run `v58_pause_local_20260613_r3` returned `PASS_PAUSE_READY` with 47 pass / 0 warn / 0 fail; Gate-B remained `WATCH_ONLY` with 0 alertable/start/schedule candidates and unfreeze gate `met=false`.
- Boundary: no CI/deploy/rebuild/restart/DB/auth/risk/order/trading mutation and no Gate-B probe. Future V5.8 active-IMPL remains frozen until AEG `stage0_ready`; rerun checker before pause/resume.

## 2026-06-18 TODO v164 hygiene

- TODO masthead restored to compact shape; v161-v163 long increment narrative moved to `docs/CLAUDE_CHANGELOG.md`, preserving active state in structured TODO sections.
- §5 stale cold-audit rows corrected: duplicate SCHEMA-1 removed, AUTH-1/PROFIT-1/DIRTY-FIX statuses aligned to deployed/healthcheck/true-table evidence. Boundary: docs-only, no runtime/code/DB/auth/risk/order mutation.

## 2026-06-18 AC19 expired cron cleanup

- Removed the expired `ac19_alt_bucket_daily_cron.sh` user-crontab line on Linux `trade-core` after read-only single-line match; backup saved at `/tmp/openclaw/backup/crontab_pre_ac19_cleanup_20260618T175129Z.txt`.
- Post-check confirmed 0 remaining crontab matches. Boundary: no code/deploy/rebuild/restart/DB/auth/risk/order/trading mutation.

## 2026-06-18 Phase2 verdict-casing reconcile

- Reconciled the §6 Phase2 promotion casing warning as stale: shared contract now canonicalizes `eligible` via `is_eligible()`, route uses that helper, Rust emits lowercase `verdict.tag()`, and the focused casing contract test passed.
- Full phase2 pytest under `/usr/local/bin/python3` was 21/23 with two `tomllib` false-reds from Python 3.10; local 3.12 has `tomllib` but no pytest. Boundary: read-only verification, no source/runtime mutation.

## 2026-06-18 runtime stale TODO reconcile

- Closed the stale `daily_cost_snapshot.sh` cron action: current Linux crontab has no `daily_cost_snapshot` line and repo/Linux still have no script, so there is no remaining cron deletion/rebuild action.
- Refreshed Gate-B watcher state: latest artifact generated `2026-06-18T17:42:01Z` is `WATCH_ONLY` with 21 total candidates, 0 alertable/start/schedule, and gate-watch-only preflight says `WAIT_FOR_ACTIONABLE_WATCH`. No probe/autostart/trading mutation.

## 2026-06-18 TODO closed-row archive pass

- Archived 8 no-action completed rows out of TODO §5: funding tilt NO-GO/no-reopen + 3LOW debt, orderLinkId #6/#6 follow-up, postmortem #7, OPS-2 D+14 soak observe, OPS-4 unit-test gap, and A1 basis wire.
- Kept rows that still have active deploy/operator/future-date/event-trigger gates. Boundary: docs hygiene only, no source/runtime mutation.

## 2026-06-18 TODO closed-row archive pass #2 + source sync

- TODO v169 archives five more no-action completed rows from §5: PERF-123, DIRTY-FIX, V5.8 pause readiness, P0-EDGE post-deploy QA A1/A2/B/A4, and CODE-SIMPLIFY-D no-reopen.
- Masthead/§0 now records prior docs checkpoint `e4e1b7a3` as Mac→GitHub→Linux `trade-core` fast-forward verified; no CI/deploy/rebuild/restart/source/runtime/DB/auth/risk/order/trading mutation.

## 2026-06-18 TODO operator archive pass

- TODO v170 compresses §6 operator actions by archiving six completed historical rows: V127 apply, AC19 cron cleanup, P5-SM step-i, P2 #6/#7, P2 #8 AST decision, and residual producer baseline done.
- Kept rows with real remaining gates: front levers, P2/L2 tails, Gate-B capture, OP-1/2/3, restore/systemd window, OPS-2 leftover auth/rotation, and residual PART4 activation decision. Boundary: docs hygiene only; no runtime mutation.

## 2026-06-18 TODO active queue archive pass #3

- TODO v171 archives `AUDIT-2026-06-14-MIGRATION-TREE-1` and `AEG-S2-EVIDENCE-AUTOMATION` from §5 because both are completed and their remaining relevance is carried by V###/PG discipline plus `AEG-S3-CANDIDATE-DIRECT-ROWS`.
- Kept DONE-ish rows that still carry policy, deploy, operator, future-date, event-trigger, or source-vs-runtime gates. Boundary: docs hygiene only; no runtime mutation.

## 2026-06-18 TODO OPS-2 cutover stale row reconcile

- TODO v172 removes stale §5 row `P1-OPS-2-PHASE-2-CUTOVER`: cutover commit `3018c7a3` is ancestor of runtime source HEAD `83b7632d` and current docs HEAD, Linux checkout contains it, and 2026-06-11 runtime note records operator-commanded `restart_all --rebuild` with OPS-2 cutover new binary active, 0 fallback string, and V137 applied.
- Remaining OPS-2 operator obligations are not closed: C-B manual `/auth/renew` evidence and 2026-09-08 rotation timing remain in TODO §6. Boundary: docs hygiene only; no CI/deploy/rebuild/restart/runtime mutation.

## 2026-06-18 TODO BB reversion regime observability SQL closure

- TODO v173 archives `P1-BB-REVERSION-REGIME-OBSERVABILITY` from §5 after post-deploy runtime evidence passed: source merge `6628b4cf` is ancestor of runtime source HEAD `83b7632d` and Linux checkout, production `trading.intents.details` is JSONB, and Linux read-only SQL for `bb_reversion` intents since `2026-06-11 02:00:00+00` returned n=10 with `hurst_label` 10/10 and `hurst_value` 10/10.
- This closes only the observability/key-presence acceptance. The 2026-06-27 bb_strategy sample-size/retire decision remains active under `P3-BB-STRATEGIES-30D-CATCH-UP-CLOCK`; n<100 extension logic is unchanged. Boundary: read-only DB/source verification + docs hygiene only; no CI/deploy/rebuild/restart/runtime/DB/auth/risk/order/trading mutation.

## 2026-06-18 TODO market_tickers forward-column SQL closure

- TODO v174 archives `P3-MARKET-TICKERS-INDEX-MARK-DEAD-PERSISTENCE` from §5 after post-engine-start SQL evidence passed. Current Linux engine PID 3134818 started `2026-06-18 14:11:50+02`; source checkpoint `5733eb06` is deployed through runtime source HEAD `83b7632d`; production `market.market_tickers` has nullable real `mark_price/index_price/open_interest/funding_rate`.
- Linux read-only SQL for `ts >= 2026-06-18 14:11:50+02` returned n=587319, mark_n=40912, index_n=84919, oi_n=5913, funding_n=719; mark/index/OI zero counts are 0, and funding_zero=8 is legitimate zero funding. This closes forward persistence/fake-zero evidence only; it does not backfill history or change 90d retention. Boundary: read-only DB/source verification + docs hygiene only; no CI/deploy/rebuild/restart/runtime/DB/auth/risk/order/trading mutation.

## 2026-06-18 TODO funding/OI backfill completed-row archive

- TODO v175 archives `P0-EDGE-1-CAND-FUNDING-OI-BACKFILL` from §5. The completed state remains in TODO §2; active queue no longer needs a row whose only content was caveat/usage guidance.
- Linux read-only recheck confirmed `research.alpha_funding_rates_history` rows=46539 and `research.alpha_open_interest_history` rows=348153, single run_id `18b3c2f8-6125-42a8-a42c-cfcc8aec9406`, 0 NULL values. Caveat preserved: run-versioned schema is not idempotent on re-apply; future cron/refresh requires a new active row for clear-old-run/wrapper/rate-limit design. Boundary: docs hygiene + read-only SQL only; no CI/deploy/rebuild/restart/runtime/DB/auth/risk/order/trading mutation.

## 2026-06-18 TODO 110017 convergence observability closure

- TODO v176 archives `P3-110017-CONVERGE-AUDIT-OBSERVABILITY` from §5 after Linux read-only DB evidence closed both deployment residual checks: 4 `trading.order_state_changes.reason LIKE 'exchange_zero_close_converge:%'` rows exist, and each had 0 follow-up orders for the same symbol+strategy within 63s and 5m after convergence.
- The row closed only D1 convergence observability/stop-timing. `P3-110017-D2-AUDIT-REMOVED-SEMANTICS` and `P3-110017-BB-DOC-FOLLOWUPS` remain active separately. Boundary: read-only DB/source verification + docs hygiene only; no CI/deploy/rebuild/restart/runtime/DB/auth/risk/order/trading mutation.

## 2026-06-18 TODO incident-policy runtime deployment closure

- TODO v177 archives `P2-INCIDENT-POLICY-DISPATCH-TRIGGER` from §5. Source chain was already closed at `26a72990`; this pass only closed the stale runtime activation gate by verifying `26a72990` is ancestor of runtime source marker `83b7632d`, running engine PID 3134818 contains the incident class/C4 dispatch strings, and watchdog PID 765009 started after current watchdog source mtime.
- Caveat preserved: no synthetic incident/drill, no real incident occurrence, and no alert-delivery proof is claimed. Future incident-class drills or alert-delivery checks need a new active row. Boundary: read-only runtime/source/DB/log introspection + docs hygiene only; no CI/deploy/rebuild/restart/runtime/DB/auth/risk/order/trading mutation.

## 2026-06-18 Reconciler runtime-status correction

- TODO v178 corrects stale `未部署` wording for `P2-RECONCILER-GET-POSITIONS-PAGINATION` / `P3-110017-D2-AUDIT-REMOVED-SEMANTICS`: `bb7e9efc`/`baf46a69` are in Mac/Linux HEAD and running engine PID 3134818 binary strings include `removed_position_semantics` / `dispatched-not-confirmed` / `reconcile_ghost_converge`.
- Rows stay active: PM 1-4 integration report still requires E2/E4/QA review, and production DB currently has 0 `observability.engine_events.event_type='reconcile_ghost_converge'` rows. Boundary: read-only source/runtime/DB verification + docs hygiene only; no CI/deploy/rebuild/restart/runtime/DB/auth/risk/order/trading mutation.

## 2026-06-18 RetCode dictionary correction

- TODO v179 archives `P3-110017-BB-DOC-FOLLOWUPS`: Bybit reference now says 110017 D2 is source-land/runtime-loaded, not pending IMPL, and official Bybit V5 error table verifies 110009 as stop-orders-count limit rather than PositionNotFound.
- The remaining Rust drift is not hidden: `P2-110009-RETCODE-SEMANTICS-FIX` now tracks enum/test/comment rename plus removal/guarding of 110009 from the close-equivalent-success NoOp arm. Boundary: docs/TODO hygiene + official-doc verification only; no code/runtime mutation.

## 2026-06-18 TODO cold-audit completed-row archive

- TODO v180 archives `AUDIT-2026-06-14-AUTH-1` and `AUDIT-2026-06-14-PROFIT-1` from §5. AUTH-1 remains closed by cold-audit fix-wave/deploy; PROFIT-1 remains NO-FIX with passive_wait `[90]` sentinel.
- The future tails are preserved in §7, not hidden: Rust live-authz/direct-socket closure is a future operator architecture decision, and cost-gate double-deduct fix only reopens if explore-gate/Stage0R produces validated-positive cells or forward PnL proves released cells positive. Boundary: docs hygiene only; no source/runtime mutation.

## 2026-06-18 TODO schedule-only duplicate cleanup

- TODO v181 removes `P3-BB-STRATEGIES-30D-CATCH-UP-CLOCK` and `P1-HALT-TRIGGER-ROOT-CAUSE-INVESTIGATION-1` from §5 because both are passive scheduled reviews already carried by §7.
- §7 now contains the missing details: 2026-06-27 bb strategy baseline/retire/extend decision, and 2026-08-21 fallback dead-enum + halt root-cause review with `halt_audit.log` ready. Boundary: docs hygiene only; no source/runtime mutation.

## 2026-06-18 TODO SCHEMA-1 completed-row archive

- TODO v182 archives `AUDIT-2026-06-14-SCHEMA-1` from §5. The schema contract test and PR-only PG CI path remain in repo, while `audit_migrations.py` is explicitly informational-only.
- The derivative `MIGRATION-TREE-1` blocker is already closed/archived by v171 and future migration safety is carried by V### / Linux PG dry-run discipline. Boundary: docs hygiene only; no source/runtime mutation.

## 2026-06-18 TODO Stage0R replay preflight event-trigger relocation

- TODO v183 moves `P1-SPRINT2-STAGE0R-REPLAY-PREFLIGHT-DISPATCH` from §5 active queue to §7 passive schedule because the row has no current engineering action; it is now event-triggered.
- This is not a completion claim: 06-10 FA evidence still says 0 candidates satisfy AC-S2-A-3, A1/A2 demo are inactive with 0 fills, A1 basis wire is functional but candidate remains dormant (`n_eff=0` / `no_a1_signals_after_entry_gate`), and A2 remains NO-GO/observe_more.
- Reopen triggers preserved in §7: green Stage 0R preflight + operator demo-canary approval, first real AEG-S3 `candidate_regime_metrics` rows, residual Stage0R preflight flag-ON first run, or funding >30% APR + A1 entry-gate regime reappears; backstop remains 2026-06-27 with `P3-BB-STRATEGIES-30D-CATCH-UP-CLOCK`. Boundary: docs hygiene only; no source/runtime mutation.

## 2026-06-18 TODO SignalSpec conformance stale-defer relocation

- TODO v184 moves `P2-AST-SIGNALSPEC-CONFORMANCE` from §5 active queue to §7 conditional wait. The old defer reason was stale: `candidate_signal_spec_producer.py` and residual/hidden-OOS/manifest source now exist on main, and residual-producer baseline/operator history was archived in v170.
- This is not a checker completion claim and not a GO to implement. The remaining unblock condition is formal SignalSpec schema freeze plus PA/PM GO.
- Future thaw must preserve the corrected scope: build a `SignalSpec schema/lineage conformance checker`, not an expression-tree AST checker; true schema is a flat metadata manifest. Boundary: docs/status correction only; no source/runtime mutation.

## 2026-06-18 TODO tail deferred-debt relocation

- TODO v185 moves seven tail deferred/condition/cadence debt rows from §5 to §7: Packet C5 GUI ack, OPS-2 Sprint4 runbook bundle, LG-5 90d maturity review, LEASE-1 post-LG3 cleanup, Phase1B dynamic backoff, IntentType visibility refactor, and OPS-4 pg_dump/SOP cargo-test debt.
- This is not a DONE claim. §7 now carries the explicit wait conditions: Packet C4/failsafe role freeze, Sprint4 bandwidth/OPS-2 operator context, 90d reviewer maturity cadence, `P0-LG-3` closure, Phase 2a Demo PASS, PA builder-pattern spec, and SOP/on-demand bandwidth.
- §5 still keeps active/operator/action rows such as OP-1 dry-run, OPS-4 deploy, TOTP backend, A1/A2 runner, Earn Wave C/D, 110009 semantics, and other rows with current engineering/review gates. Boundary: docs hygiene only; no source/runtime mutation.

## 2026-06-18 TODO 110009 retCode semantics source fix

- TODO v186 archives `P2-110009-RETCODE-SEMANTICS-FIX` from §5 after source/test correction: `BybitRetCode::PositionNotFound` was renamed to `StopOrderLimitExceeded`, `from_code(110009)` maps to the new enum, and dispatch no longer classifies 110009 as close-equivalent NoOp.
- Official Bybit V5 meaning remains: 110009 = stop-order count exceeds maximum allowable limit. The fix makes 110009 Structural/fail-closed; 110001 stays NoOp and 110017 guarded convergence behavior is unchanged.
- Focused Rust tests passed: retCode tests (2), changed classifier/helper tests, and full `event_consumer::dispatch::tests` (56). Boundary: source/tests/reference/TODO/changelog/report only; no deploy/rebuild/restart, and running engine binary is not claimed to include the fix.

## 2026-06-18 TODO AC19 final-verdict active-row archive

- TODO v187 archives `P2-AC19-ALT-BUCKET-FINAL-VERDICT` from §5. The evidence/verdict work was already done: QA final verdict says alt FAIL (42 attempts, 23.8% fill, Wilson lower 13.5%, 28 timeout->taker), large_cap INCONCLUSIVE-LOW-N, and BB audit says demo public data mirrors mainnet while fills are pessimistic because demo orders have no queue position.
- Future α/β/C choice is now `P2-AC19-ALT-BUCKET-FINAL-VERDICT-FOLLOWUP` in §7: reopen only if PA/QC/operator chooses alt taker-direct, shortened timeout, or explicit keep-current-policy acceptance. Boundary: docs hygiene only; no code/runtime/DB/auth/risk/order/trading mutation.

## 2026-06-18 TODO P2/L2 activation owed operator-row archive

- TODO v188 removes the completed §6 operator row `P2 batch activation owed #2-#6`: V138/V139, B1/B2 seed, manual V140, L2 cron, bge-m3 embedding backfill, and B3 source wiring all have closure reports/evidence.
- This is not an L2 all-clear. Remaining L2 work stays visible in `P1-L2-ADVISORY-MESH-TAILS`, §8, and `L2_TODO.md`: first non-empty material day/E2E model-call evidence, B3 shadow runtime evidence, P2p sentinel operator gates, and P5 feedback/quality/GUI. Boundary: docs hygiene only; no source/runtime mutation.

## 2026-06-18 TODO cold-audit P2/P3 batch active-row archive

- TODO v189 removes `AUDIT-2026-06-14-P2P3-BATCH` from §5. The Batch 4/5 fix-wave body is already completed/deployed by the cold-audit checkpoint, and its stale tails have since been split or closed: `daily_cost_snapshot.sh` v167, DIRTY-FIX v169, MIGRATION-TREE-1 v171, and 110009 semantics v186.
- Remaining policy/doc/perf tails are preserved in §7 as `P2-COLD-AUDIT-P2P3-BATCH-FOLLOWUP`: cost-edge re-gate decision, AI-PRICING option1 SSOT + `last_verified`, BB rate-limit dictionary doc hygiene, and PERF-1 1m minor follow-up. Boundary: docs hygiene only; no source/runtime mutation.

## 2026-06-18 Earn Wave D HMAC canonical-form checkpoint

- TODO v190 removes `P1-EARN-WAVE-D-RUST-HMAC-CANONICAL-FORM` from §5 after adding shared Rust/Python golden-vector coverage for Bybit REST V5 signing. The tests lock Earn GET sorted query bytes and Earn POST compact JSON body bytes to identical HMAC outputs in Rust `common::bybit_signer` and Python `BybitClient._sign`.
- Focused verification passed: Rust signer 2 tests and Python parity 2 tests. Remaining Wave D frontend -> backend -> Rust IPC integration test stays active as `P2-EARN-WAVE-D-CONTRACT-INTEGRATION-TEST`. Boundary: source/tests/docs only; no real Bybit call, credential mutation, deploy, runtime, DB, auth, risk, order, or trading mutation.

## 2026-06-18 TODO P5-SM completed-row relocation

- TODO v191 removes `P5-SM-OPTION2-CONVERGENCE` from §5. The active row was stale: `[82]` step-ii 48h soak had already passed on 2026-06-13T02:05:59Z, and later V138/V139, seed, V140, L2 cron, embedding backfill, and B3 source wiring superseded its old "not applied/not activated" caveats.
- This is not a P5-SM step-iii completion claim. Remaining `P5-SM step-iii CUTOVER sign-off` is preserved in §6 as an operator-gated action requiring operator sign-off plus CC/E2/BB/E4 review chain; docs hygiene only, no source/runtime mutation.

## 2026-06-18 Earn Wave D IPC contract checkpoint

- TODO v192 removes `P2-EARN-WAVE-D-CONTRACT-INTEGRATION-TEST` from §5 after source/test integration landed: Rust IPC dispatch registers `process_earn_intent`, sends `PipelineCommand::ProcessEarnIntent`, and the event-consumer owner task calls `IntentProcessor::process_earn_intent`; Python `/api/v1/earn/stake` now has a contract test locking method, timeout, and 8 params sent to Rust.
- Verification passed: `cargo test -p openclaw_engine process_earn_intent --lib` (3), `cargo test -p openclaw_engine earn_router_fail_closed_when_unwired --lib` (1), and full `test_earn_routes.py` (28, existing Pydantic warning only).
- Boundary preserved: no real Bybit call, no credential/secret mutation, no deploy/rebuild/restart, no runtime/DB/auth/risk/order/trading mutation. Current real Rust path intentionally returns `submitted=false` with `earn_dispatch_unwired...` until `BybitEarnClient` and `EarnMovementWriter` are injected; `P1-EARN-WAVE-C-FIRST-STAKE-RUNTIME` stays active for OP-1/2/3 plus capability injection.

## 2026-06-18 P2 clippy cleanup gate

- TODO v194 closes `P2-CLIPPY-CLEANUP-1`: Apple Silicon `cargo clippy --target aarch64-apple-darwin -- -D warnings` now passes.
- Low-risk core/type lint errors were fixed directly; engine/bin historical lint debt is explicit at crate/bin boundaries so new unlisted lint classes still fail. Verification passed: clippy gate, core lib 412 passed, engine lib 4092 passed / 1 ignored.
- Boundary: source/tests/docs only; no CI full suite, deploy/rebuild/restart, runtime DB/auth/risk/order/trading mutation, credential mutation, or real Bybit call.

## 2026-06-18 H0Gate file split

- TODO v195 closes `P3-H0GATE-FILE-SPLIT`: `h0_gate.rs` moved its test module to `h0_gate/tests.rs`, reducing the production file from 1243 to 630 lines.
- Verification passed: H0 tests 33 passed, core lib 412 passed, Apple clippy gate, and engine `h0_latency_metrics` 5 passed.
- Boundary: source/tests/docs only; no CI full suite, deploy/rebuild/restart, runtime DB/auth/risk/order/trading mutation, credential mutation, or real Bybit call.

## 2026-06-18 Codex sub-agent hygiene dispatch rules

- TODO v196 closes `P3-SUB-AGENT-HYGIENE-SOP-CARGO-TEST-AFTER-ATOMIC`: Codex dispatch rules now require `docs/agents/sub-agent-hygiene-sop.md` for delegated Rust/Cargo/Linux-runtime/PG/deploy/runtime-verification work.
- Dispatch records must name `hygiene_sop`, `verification_surface`, and Linux write policy. E1/E2/E4 Rust tasks must report focused Mac cargo/source verification or an explicit skip reason; sub-agents remain barred from Linux cargo and unsupervised restart.
- Boundary: docs/governance only; no source code, CI, deploy/rebuild/restart, runtime DB/auth/risk/order/trading mutation, credential mutation, or real Bybit call.

## 2026-06-20 MLDE LinUCB / shadow timeout fix

- Production logs showed daily LinUCB and API scheduler MLDE reads timing out on the slow `learning.mlde_edge_training_rows` view path. LinUCB and shadow advisor now preserve the MLDE training-row contract while reading base tables directly, avoiding the `trading.signals` lateral bulk-decompress path.
- Routine LinUCB windows default to 30d with 5s timeout; remote read-only smoke of patched modules showed 30d all-arm LinUCB max arm 1.69s and shadow aggregate ~0.5s. Boundary: source/tests/docs only in this checkpoint; remote smoke was read-only and not an alpha promotion proof.

## 2026-06-20 fill_sim refresh guard + L1 stale diagnosis

- Added bounded `fill_sim_refresh_cron.sh` and installed Linux cron at 06:05 UTC. It writes candidate reports first and only replaces production fill_sim report when candidate has no abort, non-empty L1, non-empty symbols, and L1 data age <=72h. It prevents the failure observed this run: `HOURS=2` refresh produced empty L1 and initially overwrote production before the guard fix.
- `fill_sim.py` now records `l1_min_ts/l1_max_ts/l1_max_age_hours`; `recorder_mm_verdict_cron.sh` rejects empty/stale L1 data even when `generated_at` is fresh.
- Runtime recovery: explicit 90m post-fix window restored `/tmp/openclaw/research/fillsim/fillsim_report.json` with `l1_rows_post_filter=1,750,468`, fill_only `n=15,208`, adverse@15=1.477bp, net_maker@15=-4.701bp, `l1_max_age_hours=58.114`. Manual MM verdict then had `adverse_selection_usable=true`, sample=16, all symbol net edges still negative.
- Root blocker found: `market.l1_events` stopped at `2026-06-17 21:55:45+02` while trades/ob_top are fresh. `recorder_health_cron.sh` installed at 06:23 UTC and manual run appended `[RECORDER-HEALTH] recorder stalled` critical alert. Next PM target is L1 event recorder repair; without it, fill_sim data-age gate will disable adverse selection again around 72h from L1 max.

## 2026-06-20 L1 recorder persistence repair

- Root cause was restart env persistence: active engine had `OPENCLAW_RECORD_L1_EVENTS=` while `OPENCLAW_RECORD_TICKS=1`, so `market.trades` and `market.ob_top` stayed fresh but the L1 producer was OFF after restart.
- Fixed `helper_scripts/restart_all.sh` to read `OPENCLAW_RECORD_L1_EVENTS` and `OPENCLAW_L1_MAX_EVENTS_PER_SEC_PER_SYMBOL` from `basic_system_services.env` when parent env is absent; static regression covers the parent-only bug.
- Runtime repair on trade-core: set non-secret env-file keys `OPENCLAW_RECORD_L1_EVENTS=1`, `OPENCLAW_L1_MAX_EVENTS_PER_SEC_PER_SYMBOL=50`; engine-only `--keep-auth` restart, no rebuild/API restart/schema migration.
- Verification: new PID `4155643` env contains L1 flags; read-only PG showed `l1_max_ts=2026-06-20T02:19:20.531+02`, `l1_rows_5m=2635`, stale 0.027min. Formal `recorder_health_cron.sh` status: `l1_events.rows_24h=4566`, `stale_min=0.03`, crossed/locked 0.00.
- Boundary: source/test/docs + Linux non-secret env flag + engine-only restart and `/tmp/openclaw` logs/heartbeats only; no Bybit private/signed/trading call, no credential/auth/risk/order/trading mutation, no promotion proof.
