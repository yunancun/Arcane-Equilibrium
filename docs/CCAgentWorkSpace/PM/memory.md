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
