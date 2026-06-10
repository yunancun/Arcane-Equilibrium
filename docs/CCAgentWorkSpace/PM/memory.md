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
