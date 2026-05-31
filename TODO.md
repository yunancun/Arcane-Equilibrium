# 玄衡 TODO — 活躍派工佇列

**版本** v93 ｜ **日期** 2026-05-31 ｜ **source HEAD** `cd3a6d0d`（doc-only checkpoint；Linux runtime binary 仍為先前 deploy，runtime 健康詳 §0）
**當前主線**：autonomy 13 模組 active-IMPL **凍結**（保留 DESIGN/stub）→ 主攻 **alpha-edge research**（成本牆 + 資料深度兩道 binding constraint）。核心 blocker **P0-EDGE-1 見 §1**；活躍派工 **alpha-edge 4-track 見 §6.1**；模組凍結狀態見 §4。
**版本增量日誌**（各版 vN 變更敘事，新 session 不需讀、僅回顧用）→ `docs/CLAUDE_CHANGELOG.md`「TODO Version-Increment Log」｜**已歸檔 closed 明細 + v75-91 歷史** → `docs/archive/2026-05-31--todo_v92_archive.md`

---

## §-2 命名消歧義（v65 沿用）

本檔出現的「Sprint 2」一詞有 3 個含義：

| 名稱 | 真實內容 | 狀態 |
|---|---|---|
| **Sprint 1B Sub-IMPL: M3 emitter pre-readiness** | 4 並行 Track — PA D1/D2/D3 整合 + V103 land + E3-MED-2 ALTER OWNER | ✅ DONE 2026-05-22 |
| **Sprint 1B Sub-IMPL: M3 metric emitter scaffold** | 6 Track Wave 1+2 health domain emitter scaffold | ✅ PASS WITH 5 CARRY-OVER 2026-05-22 |
| **v5.8 §4 業務 Sprint 2（Alpha Tournament）** | Alpha Tournament + M4 stage 1 + M10 Tier A + M8 read-only — per v5.8 §4 + SSOT `docs/execution_plan/2026-05-26--alpha_tournament_ssot_spec.md` | 🟡 **SSOT SPEC-FINAL / PARTIAL IMPL STARTED**（M4 Stage 1 runner source+Linux PG no-writeback empirical done + GovernanceHub lease provider seam fail-closed；A2 maker-fill diagnostic PG verdict reject；A3 precheck PG verdict reject；未 deploy） |

判讀規則：「Sprint 2 pre-readiness / M3 emitter / Wave 1/2」= 支撐 sprint（DONE）；「業務 Sprint 2 / Alpha Tournament / W12-15」= v5.8 §4 業務 sprint。

---

## §0 三端同步 + Runtime 健康儀表

**三端 sync**：2026-05-31 v91 source checkpoint `ec11544a` 已在 Mac / origin/main / Linux trade-core；後續 TODO/docs checkpoint 只推進 git HEAD、不改 runtime source。Linux runtime **not rebuilt** for this Python helper-only sync, still running prior deployed binary；API/watchdog runtime state unchanged by this batch.

**Runtime snapshot（最新 deploy = v87 2026-05-31）**：
- ✅ **Engine/API/watchdog alive（2026-05-31 v87 deploy = CURRENT）** — `build_then_restart_atomic.sh` release build + engine-only restart；new engine **PID 968350**；`/proc/968350/exe` SHA == disk SHA == `30adb40cc4dfbc9649c7b338a785932b30bd6c50cc5cfe28fd700a32e5a939a1`；`GET /api/v1/healthz` 200；user `openclaw-watchdog.service` active; `engine_watchdog.py --status` reports `engine_alive=true`, demo/live fresh (<45s), and paper intentionally archived/stale (`disabled=true`, `disabled_reason=paper archived 2026-05-23; use Replay Stage 0R + Demo micro-canary`). Engine log: 0 panic/backtrace/fatal; startup warnings limited to known demo endpoint/DCP/fee-rate/dirty strategist DB param fail-closed (`ma_crossover` confluence sum 73 vs 65). `OPENCLAW_AUTO_MIGRATE=0` at boot; PG check after deploy: `_sqlx_migrations max=115 count=108 version104=true`, `learning.supervised_live_audit` exists.
- ⚠️ **system-level service caveat** — sudo password required，`openclaw-engine.service` / system watchdog unit 尚未安裝到 `/etc/systemd/system`；目前保護 = user-level `openclaw-watchdog.service` enabled + linger yes + manual engine process。system-level install 仍屬 operator hand-action。
- ⚠️ **Passive healthcheck not all green** — 殘 FAIL = `[48] replay_manifest_registry_growth`（M11 register-only cron 已裝，fire 後自癒）/ `[74] close_maker_reject_samples`（demo 流量結構性無法觸發 max_pending，等 pilot 放量）/ `[56] live_pipeline_active`（`authorization_json_missing` = Operator-only signed `/auth/renew`，agent 不動）。三條皆 OPS residual / evidence queue，不反轉 OPS-1 closure。

> 舊 deploy 快照（PID 27582/113386/191366/251791 lineage）+ Migration drift verify + Wave5 V099/Packet B physical state + pg_dump/CSRF shadow check + 2026-05-29 維護重啟窗口分析 → `docs/archive/2026-05-31--todo_v92_archive.md` §B。

**Cron schedule**：pg_dump daily `0 3 * * *` UTC installed 2026-05-28；remaining operator/runtime hand-actions = first qualifying restore drill + system-level units + live-auth renewal + replay/close-maker evidence；3 defer（passive_wait_healthcheck / ref21_market_microstructure_recorder / blocked_symbols_30d_unblock）。

---

## §1 Top-Priority Active Blockers（P0 only）

| ID | 狀態 | Owner | AC | Next Action |
|---|---|---|---|---|
| **P0-EDGE-1** | 🔴 ACTIVE（**THE 核心 blocker**；SSH empirical 2026-05-26 22:00 UTC: 0/3 AC paths satisfied；2026-05-26 cohort reframed 5→4 textbook per AMD-2026-05-26-01）| QC + PA | (i) **4 textbook** ≥3 demo 7d avg_net>5bps + Wilson lower>0 + n≥30（funding_arb retired per AMD-2026-05-26-01）；**OR** (ii) ≥3 alpha-bearing 達同標；**OR** (iii) portfolio 7d gross 正向 | 唯一可預期 closure path = (ii) Alpha-Edge 4-Track。當前 (i) **4/4 textbook** `insufficient_total_samples`；(iii) live_demo 7d net=-1.99 USDT；A1/A2/A3 舊候選未達 Stage1。**2026-05-31 NOW 三並行結果**：S1-W1-S1 MIT advisory **PASS**；S2-W0-S1 Gate-A **PROCEED**（maker-fill 59/67=88.1%，Wilson 78.2-93.8%，不是 alpha proof）；S4-W0-S1 **BLOCKED_ON_RETENTION + SCRIPT**。**Operator 2026-05-31 decision**：approve `market.klines` 365→1095d + 18mo + collection full survivorship / primary analysis core25；requires **automated breadth-ladder analysis**, not one-off manual breadth judgment；S4 downgraded from bull-data proof to cross-track regime/falsification overlay for S1-Sx, with no bull-only promotion confidence；bull data allowed only when explicitly labeled, trend/state must be local math-first from Bybit market data, and future news/X/Reddit agents are secondary corroboration only. Next executable = PA/MIT amend execution packet for alpha-history storage + breadth automation + local trend/state classifier + global regime robustness → E1 public Bybit history backfill script → MIT verify；M4 exploratory DRAFT still cannot be promotion evidence。 |
| **P0-LG-3** | 🟡 **SOURCE INTEGRATED 2026-05-31 / runtime not deployed** — T1 `feature/lg3-t1` + T4 `feature/lg3-t4` integrated on `integration/pm-1-4`; V104 Guard C fixed after real Linux rollback dry-run exposed timestamptz `time_interval` issue; re-run double-apply rollback = 0 ERROR + `V104: all guards PASS` x2 and `_sqlx_migrations` unchanged. | PM → E2 → E4 → QA → operator deploy gate | AC before deploy: E2/E4 review of integrated commits; V104 SQL checksum discipline; Linux migration dry-run or AUTO_MIGRATE plan confirms version 104 registration without modifying existing V099-V115 migrations; supervised_live tests remain green. | Next action: run full review chain on commits `deb3f3af..0802d52b` (plus integration branch context), then decide deploy/rebuild; do not use the stale 2026-05-30 MIT approve report as sole evidence because it missed the `time_interval` blocker. |
| **P0-OPS residual** | 🟢 **OPS-1 CLOSED / OPS residual OP-gated** — OPS-1 enforcing-ready gaps closed commit `22466a81`; OPS-4 pg_dump runtime freshness now PASS but passive healthcheck not all green | E1+MIT+PA → E2+A3+E4+QA 全鏈 GREEN | Migration drift clean；engine/API/watchdog alive；pg_dump cron installed + first dump PASS。 | Remaining: system-level unit install (sudo), first restore drill, OPS-2 D+14 cutover/soak, `authorization_json_missing` live-auth renewal, replay_manifest registry feed, close-maker max-pending evidence. Not current coding blocker, but blocks "OPS all green"。詳見 §6 OPS active rows。 |

> 已 CLOSED P0：`P0-ENGINE-DEAD-2026-05-27`（runtime recovered 2026-05-28）、`P0-FUNDING-ARB-DECISION-FORCE`（operator chose D 2026-05-26）、`P1-LG-3-AC-CORRECTION`（LG-3 子任務 CLOSED 2026-05-27）→ `docs/archive/2026-05-31--todo_v92_archive.md` §E。

---

## §2 Active Sprint Phase Banner

```
業務 Sprint 2 (Alpha Tournament)  🟡 SSOT SPEC-FINAL / PARTIAL IMPL STARTED (W12-15 計畫) Stream A A1 blocked by basis accumulation + A2 HOLD / maker-fill reject + A3 precheck reject；M4 Stage1 PG empirical + lease provider seam done, production writeback still schema/IPC-blocked
Layered Autonomy v2 Wave 5  🟡 FROZEN per v92 D1（active-IMPL 凍結）/ Packet A+B runtime + TOTP source + ADR sync done / Packet C core E4 green / engine integration + runtime TOTP enrollment pending
P0-EDGE alpha mainline  🔴 ACTIVE — 成本牆下 alpha 重定向（listing pump-dump fade + funding-extreme directional）；P0-EDGE-1 仍 0/3 AC
```

> 已 DONE 的歷史 phase 行（Sprint 1A-α/β/γ/δ/ε/ζ / Sub-IMPL M3 / Sprint 4+ Stage A-F / Sprint 5+ Wave 1）→ `docs/archive/2026-05-31--todo_v92_archive.md` §C。

**狀態語言**：
- DESIGN-DONE = spec/ADR/runbook/schema spec 文件 land 通過 PM signoff
- IMPL-PENDING = 對應 Rust/Python/SQL 實作未開始
- 未來 V104/Sprint2 migrations 仍須 normal Linux PG empirical dry-run + sqlx register discipline。

---

## §3 In-Flight Workflow（≤7 並行；含 sub-agent chain）

| ID | Workflow | Owner chain (T1-T5 template) | 估時 | Cluster | Blocked-on |
|---|---|---|---|---|---|
| **B** | ADR-0046 basis observation/execution split | T1: PA design → E1 Rust → MIT V117 → E2 → E4 → BB → QA | 24-30 hr | 2 (Phase 1→2→3) | PA design first |
| **Earn Wave C** | OP-1 series → first stake $100-200 Flexible-only | T1: 7 hand OP + 5 可代做 post-1..5 | OP 30min + post-flow 30min | 3 (operator-gated) | OP-1 a-f hand actions |
| **Layered Autonomy v2 Wave 5** | V099 + GUI + Rust SM-04 + 5 ADR sync + R4（🟡 active-IMPL FROZEN per v92 D1）| T1+T2 (Packet A runtime ✅; Packet B API+GUI ✅; TOTP source ✅; Packet C core E4 ✅ / engine integration pending) | 81-126 hr | partial | Pending = Packet C engine notification timeout / exchange conditional SL sync / audit emit integration + runtime TOTP enrollment（per v92 D1 凍結，不主動派 IMPL）|
| **Alpha-Edge 4-Track Program**（取代舊 Sprint 2 Alpha Tournament；PM 2 簽 PASS）| T1 低turnover多日(critical) / T2 listing fade(~Q4) / T3 ensemble(cond) / T4 funding-directional | per plan §2 work-chain（PM→QC/MIT/E1→E2/E4/A3/BB）| NOW 3 並行 completed preflight → gated follow-up | 1 (P0-EDGE closure) | **2026-05-31 S1/S2/S4 results recorded in §6.1**：S1 retention+universe PASS but OP-gated；S2 Gate-A PROCEED；S4 blocked on retention+script。 |

> 已 CLOSED workflow A（22 fail-closed invariant）/ D（AMD-25-01 cascade）/ E（AMD-25-02 cascade）/ F（funding_arb deprecation cascade）→ `docs/archive/2026-05-31--todo_v92_archive.md` §D。

**Sub-agent dispatch hygiene SOP**（per memory `feedback_fetch_before_dispatch` + 2026-05-25 cargo test-after-atomic 教訓）：
- 每次 dispatch 前強制 `git fetch` + `git branch -r | grep <topic>` + `git log --all | grep <ticket>`
- Linux cargo test 後必走 `bash helper_scripts/build_then_restart_atomic.sh` OR 標 carry-over
- Meta-doc 改動用 `git commit --only <files>` 隔絕 multi-session race

---

## §4 Module DESIGN/IMPL Matrix（M1-M13 per PA technical roadmap）

> **v92 D1 凍結**：M1/M2/M6/M8/M9 active-IMPL 凍結（保留 DESIGN/schema/stub，不派 Rust IMPL），主力轉 alpha-source 主線；解凍 gate = 首個 net-positive alpha-bearing candidate 達 stage0_ready。M7 唯一例外（V116 spec done 但 E1 IMPL 暫按住）。

| M# | 名稱 | State | LOC (R+P+SQL) | 估時 (hr) | IMPL phase |
|---|---|---|---:|---:|---|
| **M1** | Decision Lease LAL 4 Tier | DESIGN-DONE / Track A spike runtime feature-live but **`LAL_0_AUTO=0` 未證 runtime grant**（🟡 FROZEN per v92 D1）| 1800/400/350 | 130-180（80 done） | β ✅ / Sprint 4 Tier 1 / Sprint 7-8 Tier 2 / Y2 active |
| **M2** | Overlay enable SM | DESIGN-DONE / IMPL-PENDING（🟡 FROZEN per v92 D1）| 800-1100/200/250 | 90-130 | γ ✅ / Sprint 3 hook / Y2 Q1 auto-enable |
| **M3** | Health monitoring + auto-degradation | DESIGN-DONE / **Sub-IMPL emitter scaffold ✅ PASS 5 CARRY** / 6 domain × 30min × 1836 row empirical PASS | 3200/600/400 | 140-200（emitter 30-40 done） | β ✅ / 1B emitter ✅ / Sprint 5 auto-degradation / Sprint 7 recovery |
| **M4** | Self-supervised hypothesis discovery | DESIGN-DONE / **V100 base table ✅ land 663 SQL+581 spec** / Stage 1 runner **SOURCE ON MAIN + Linux PG no-writeback empirical PASS + GovernanceHub lease provider seam fail-closed**（30d BTC/ETH source counts 104520/426/92069/176；22 candidates；5 selected exploratory→PG draft；writeback_enabled=false；direct lease preflight fail-closed；production writeback blocked by UUID column vs `lease:<id>` canonical ID mismatch + active IPC lease path；no deploy） | 1500-2000/600/700 | 170-240（V100 ✅ done；Stage1 runner narrow slice source+empirical+provider seam done） | γ ✅ / **Sprint 6+ Pattern Miner active per ADR-0045** / Sprint 8 stage 2 / Y2 Q2-Q3 full loop |
| **M5** | Online learning interface | DESIGN-DONE / **trait stub ✅ 277 LOC + 100 test** | 277/0/frontmatter | 8-12 done / Y3+ 200-400 | δ stub ✅ / Y3+ AUM>$50k 啟動 |
| **M6** | Bayesian reward weight | DESIGN-DONE / IMPL-PENDING（🟡 FROZEN per v92 D1）| 900-1200/400/200 | 130-190 | β ✅ / Sprint 7 Advisory / Y2 Auto |
| **M7** | Strategy decay + auto-retirement | DESIGN-DONE / **single decay authority per CR-7** / **V116 spec done 但 E1 IMPL 暫按住 per v92 D1**（成本牆下無 alpha 可保護使其偏早；spec `docs/execution_plan/specs/2026-05-31--v116-m7-decay-detector-spec.md`）| 1200-1500/300/350 | 130-180 | β ✅ / Sprint 8 IMPL / Sprint 10 auto-demote via M1 Tier 1 |
| **M8** | Anomaly detection | DESIGN-DONE / IMPL-PENDING（🟡 FROZEN per v92 D1）| 1300-1700/500/400 | 210-310 | γ ✅ / Sprint 3 read-only / Y1 H2 alerting / Y2 ML |
| **M9** | A/B testing framework | DESIGN-DONE / IMPL-PENDING（🟡 FROZEN per v92 D1）| 1200-1600/600/500 | 200-280 | γ ✅ / Sprint 4 read-only / Sprint 7-8 manual / Y2 auto |
| **M10** | Discovery pipeline Tier A-E | DESIGN-DONE / Tier A ✅ v5.7 baseline / Tier B-E IMPL-PENDING | 800-1200/400/250 | 400-600 Y1-Y3 | γ ✅ / Sprint 2 Tier A prod / Sprint 8 Tier B / Y2 Tier C-D / Y3 Tier E |
| **M11** | Continuous counterfactual replay | DESIGN-DONE / **Track C spike SOURCE-LAND but `replay_divergence_log` rows=0 runtime-not-proven** | 1000/1100-1400/400 | 140-200（V107 ✅ schema land） | β ✅ / V107 ✅ / Sprint 3 nightly / Sprint 5+ hookups |
| **M12** | Adaptive order routing | DESIGN-DONE / **trait stub ✅ 393 LOC + 11 test** | 393+1300-1700/0/frontmatter | 20-30 done / Sprint 6 80-120 / Sprint 7-8 60-100 / Y3+ 100-160 cross-venue | δ stub ✅ / Sprint 6 maker-vs-taker / Sprint 7-8 slicing |
| **M13** | Multi-asset / multi-venue (Y3+ at earliest per ADR-0040) | DESIGN-DONE / **trait stub ✅ 151 LOC + 7 test** | 151+200-300/0/frontmatter | 30-40 done / Y3+ 250-400 IMPL | δ stub ✅ / Y1 末 spec / Y3+ Binance perp enable |

**3 missing module 處置（PM 仲裁 D1 採納）**：
- **M14** strategy hot-swap → defer v5.9（Sprint 4 後 90d）
- **M15** capacity-aware sizing → 擴 M6 acceptance 第 4 條「orderbook depth bounds」
- **M16** cross-strategy correlation re-sizing → 擴 M1/LAL acceptance「correlation-adjusted weight」

---

## §5 9 Safety Invariants Live Dashboard（per FA enforcement matrix）

| # | Invariant | Last verify | Enforcement timing | 對應 IMPL |
|---|---|---|---|---|
| I1 | 5-gate live boundary | 2026-05-25 SSH | strategy snapshot register + restart_all --rebuild 後 | Sprint 4+ §4.1 ✅ / Sprint 1A-δ Executor live |
| I2 | Signed authorization 走 Python renew/approve | 2026-05-25（OP-1 OP authorization.json missing 預期）| AMD Toggle 切換 / Cooling 7d 結束 | Workflow Earn Wave C / Layered Autonomy v2 |
| I3 | LiveDemo 不降級 authorization/TTL/risk/audit | 2026-05-25（engine_mode=live_demo 標籤 audit）| 任何 endpoint=demo 路徑 | Workflow Earn Wave C |
| I4 | Mainnet env-var fallback closed | 2026-05-25 ✅（per Action 3 closure）| 全程 | OPENCLAW_ALLOW_MAINNET=1 set via secrets file |
| I5 | Bybit API timeout / 非 0 retCode fail-closed | 2026-05-25（funding_ok=25/funding_fail=0）| 全程 | C10 funding harvest demo dormant 預期 |
| I6 | execution_authority = denylist 非真 auth | 2026-05-21 audit | 全程 | (per ADR-0034 LAL spec) |
| I7 | ML/Dream/Executor/Strategist 不繞 GovernanceHub + Decision Lease | 2026-05-21 audit + V112 LAL schema land | M4 DRAFT writeback / M1 LAL Tier / M11 replay | Workflow A + B + Sprint 2 |
| I8 | 不 fake AI calls/trading/fills/lineage/healthcheck/test | 2026-05-25 V1→V5.8 drift audit + canary rename | 全程；FA 抽查 dummy/synthetic marker | drift audit 終稿 §11 + canary rename verify |
| I9 | Paper 非 active promotion evidence (per AMD-2026-05-15-01) | 2026-05-21 audit | Stage 0R replay + Stage 1 Demo-only | Sprint 2 Alpha Tournament Stage 0R |

**高風險 violate 集中點**（per FA §1）：#3 (Lease 繞過) / #7 (學習側寫 Live) / #9 (5-gate 完整性) / #14 (state 冪等)

---

## §6 P1 Active Engineering Queue（active only；closed → archive）

> 已 CLOSED / SOURCE DONE / DEPLOYED 明細（110017 治本 / OPS-1/2/3/4 / Packet C C1-C3+HIGH1 / basis-panel / Earn source-layer / funding_arb deprecation / 2026-05-25 早期 closure 批 / reclassified NOT-A-BUG）→ `docs/archive/2026-05-31--todo_v92_archive.md` §E（commit map + 逐項 review chain）。

| ID | 優先 | 任務 | AC / Next Action |
|---|---:|---|---|
| `P2-RECONCILER-GET-POSITIONS-PAGINATION` | – | ✅ **SOURCE DONE 2026-05-31 on `integration/pm-1-4`** — full-scan `get_positions(category, None)` now uses `settleCoin=USDT`, `limit=200`, `nextPageCursor` loop, and fail-closed guards for cursor non-advance / 50-page cap; `symbol=Some` point-query path unchanged. Tests: cursor 9/0, `position_reconciler` 81/0, `cargo check -p openclaw_engine --lib` PASS. **Next: BB/E2/E4 review, then deploy with broader source batch if approved.** |
| `P3-110017-D2-AUDIT-REMOVED-SEMANTICS` | – | ✅ **SOURCE DONE 2026-05-31 with reconciler pagination batch** — ghost converge audit payload now distinguishes dispatch from handler-confirmed removal: caller passes `removed_position=true, confirmed=false`, payload writes `confirmed=false` and `removed_position_semantics="dispatched-not-confirmed"`. **Next: E2/E4 review with `P2-RECONCILER-GET-POSITIONS-PAGINATION`.** |
| `P3-110017-CONVERGE-AUDIT-OBSERVABILITY` | 4 | **NEW 2026-05-29 deploy 驗證殘留** — 部署後 loop 功能性確認停 + position 已移除，但 (1) `exchange_zero_close_converge` audit row 在 `trading.order_state_changes` 查無；(2) loop 停在 new-engine start 後 ~63s（~88 closes）非首 tick。功能無虞（position 已清、無 silent residual），純 observability/timing 核驗。Owner: E1 + MIT（audit）。 |
| `P3-110017-BB-DOC-FOLLOWUPS` | 4 | **NEW 2026-05-29 per BB 2 follow-up** — (1) retcode 字典 §4.2 110017 row 補「one-way + qty=0 form 可安全收斂」新語意；(2) 110009 doc 版本歧義（官方「110009=PositionNotFound」vs「110009=stop orders 超上限」兩版；本系統 dispatch 採 PositionNotFound→NoOp）— 順查確認。Owner: TW（字典）+ BB（110009 核實）。 |
| `P1-OPS-2-PHASE-2-CUTOVER` | 1 | **NEW 2026-05-27 per CC C-1 P0 hard gate** — D+14 (2026-06-10) Phase 2 PR：移 fallback + main.rs:402 後第二 panic block + Python reason `ipc_secret_missing` → `live_auth_signing_key_missing` + `AuthError::IpcSecretMissing` 變體刪除；Phase 2 不 land = hardcoded fallback 永久化違規；Owner: E1 + CC + BB；trigger: D+14 + 14d soak 0 WARN log；2-4 hr |
| `P1-OPS-2-14D-SOAK-OBSERVE` | 1 | **NEW 2026-05-27 per CC C-2/C-3** — 14d soak D+0 2026-05-27 → D+14 2026-06-10：(a) 每日 `ssh trade-core grep -c ops2_secret_split_phase1_fallback /tmp/openclaw/{engine,api}.log` 累計 = 0（D+1/D+2 已 PASS，~7h 維護窗口 coverage gap 非 violation）(b) 至少 1 次 `/api/v1/live/auth/renew` 重簽（仍 0 次 OP-1 operator-blocked）；任一 fail = Phase 2 BLOCK |
| `P1-OPS-2-DRY-RUN` | 1 | **NEW 2026-05-26 per E3-LOW-2** — OP-1 a-f path 45+ 天未動 = SOP 從未 end-to-end exercised；用 OP-1 當 OPS-2 SOP first dry-run 收 timing + fail-modes → runbook v1.1；Owner: Operator + PM；trigger: OP-1 unblock D+2-D+3 |
| `P0-OPS-4-GAP-B-D-OPERATOR-DEPLOY` | 1 | **PARTIAL DONE 2026-05-28** — (1) engine/watchdog runtime recovered ✅ (2) `repair_migration_checksum --verify` drift_count=0 ✅ (3) pg_dump wrapper manual run ✅ 4.6G (4) pg_dump cron apply ✅ daily 03:00 UTC (5) `[80] pg_dump_freshness` direct 7/7 PASS ✅；**remaining hand-actions**: first qualifying restore drill ~4 hr per MIT SOP scenario S1 + BB Earn cross-sign §11；passive healthcheck still fails `[48]/[74]/[56]`。**`.pgpass` 通配 ENTRY 已加 2026-05-28 per operator decision [3]**（`*:5432:trading_ai_drill_*` + `*:5432:trading_ai_restore_*` + `*:5432:*:trading_admin`，chmod 600）。**Operator timing call**：4hr 跑時段共用 PG cluster 與 live engine，agent 不自啟 → 等 Operator 排 low-trading window。 |
| `P3-OPS-4-PG-DUMP-EVENT-EXTEND` | 4 | **NEW 2026-05-27 per PA mini-patch §10.C** — `pg_dump_retention_dropped` + `pg_dump_md5_drift` 2 future event_types；triggered if dump operationally need finer audit；non-blocker first-day live |
| `P2-OPS-4-GAP-B-D-UNIT-TEST-GAP` | 3 | **NEW 2026-05-27 per E4 CARRY-OVER-2** — 743 LOC production code (3 cron + Python healthcheck + passive_wait wire) 0 unit test；governance gap；P1 backlog post first-day live |
| `P1-WAVE5-TOTP-BACKEND` | 1 | 🟦 **DEFERRED per operator decision [1] 2026-05-28 — 等系統完整正式上線再做** — `autonomy_totp.py` source + 10/10 pytest 已 land；vault dir 已 prep；runtime fail-closed by design 不阻 Conservative level 運作。**作用範圍**：只服務 Autonomy Level 2 (Standard) 切換，與 `/auth/renew` live engine 啟用無關（[2] 已確認 renew flow 無 2FA gate）。enrollment 重啟時機 = Sprint 2 Alpha Tournament + Level 2 promotion gate 開啟前。enrollment one-liner prep 保留供未來使用（authenticator app base32 seed → sha256 fingerprint → `umask 077` 寫 `autonomy_totp.json` → smoke `autonomy_totp_backend_configured()` 回 True → restart_all）。 |
| `P1-SPRINT2-STAGE0R-REPLAY-PREFLIGHT-DISPATCH` | 1 | **MAJOR CORRECTION v78 2026-05-28 — Sprint 2 大半已 DONE，不是 IMPL pending** — W2-B Rust IMPL 早於 2026-05-25 `817de10a` land（funding_short_v2 + liquidation_cascade_fade Rust struct + TOML default `active=false` + Python harness +3737 LOC）+ W2-E E2 R2/R3 APPROVE + W2-E4 regression 3483/3483 PASS + M4 W1-C-R3 draft_writer schema fix + AC-19 ALT bucket daily cron fire。**真實殘餘工作**：(1) M11 cron install ✅ DONE；(2) Packet C scope decision ✅ C1+C2+C3 done / C4+C5 Sprint 3；(3) Stage 0R 6 sanity check 跑（M11 runner 接線後）；(4) **AC-S2-A-3 ≥1 candidate evidence 累積**（14d demo via AC-19 cron 自 5/26 開跑，~D+14=2026-06-11）；(5) W3-C TW + PM sign-off Wave 3 stage0_ready 出口。**Owner**: PM → operator decisions → E1 dispatch chain。**ETA**: 真實殘餘 ~14 day（多為 evidence 累積等待）。**Ref**: PA Sprint 2 entry checklist `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-28--sprint2_alpha_tournament_entry_checklist.md`。 |
| `P1-A1A2-STAGE0R-RUNNER-IMPL` | 2 | 🟡 **IMPL DONE 2026-05-29 / A2 QC 審結 REVISE/HOLD 不推進 Stage1 Demo** — A2 functional（復用 8c liquidation cascade fade + 2 adapter）+ runner shell + 6-check time-block CSCV + `sample_sufficiency`；A1 STUB `draft_only(basis_panel_infra_missing)` 0 dead cohort code。real-PG offline：avg_net **−2.45 bps（負）** / n_eff=7 / 13d → 證據 **0/3**。**QC 2 hard-gate 裁決**：time-block CSCV = CONDITIONAL PASS（single-cell 無 model-selection 維度，A2 真 overfit 防線 = forward demo OOS）；k_prior 來源 APPROVE（runner default=None→auto-query `strategy_trial_ledger`→不存在則 fail-closed 降保守）。**PM ssh trade-core 取證 2026-05-30**：`learning.strategy_trial_ledger` 存在、33692 行全為 `edge_estimator_cycle` family、liquidation-family = 0 行 → A2 k_prior=0 為合法真實值（C-1 RESOLVED）；真 bug 在 `helper_scripts/reports/w_audit_8c/liquidation_cluster_stage0r_report.py:100-123` `_get_conn()` 讀 `POSTGRES_PASSWORD` 無 fallback；canonical secrets 路徑 = `${OPENCLAW_SECRETS_ROOT:-$HOME/BybitOpenClaw/secrets}/environment_files/basic_system_services.env`。**⚠️ 主會話誠實撤回**：先前一版宣稱「runner runtime artifact 取得 / verdict observe_more」係未經乾淨原始輸出證實（本 session 第三次幻覺），予以撤回；A2 唯一可信 edge 數據仍是 B-runner offline avg_net −2.45bps（負）。**修法 = E1 fix DONE branch `fix/a2-runner-pg-auth` @ `10aeaf54`**（+68 行 `_load_secrets_pg_password()` 讀 canonical env 缺則 fail-loud；7/7 自測 PASS）→ 待 E2→E4→PM 部署後才能 runtime 驗 runner。正確 entry = `python3 helper_scripts/reports/alpha_candidate_stage0r/candidate_stage0r_report.py`。**結論不變**：A2 = REVISE/HOLD。**剩餘鏈**：E2(A2 fix)→E4→PM 部署驗 runner runtime→A2 runner E2(C-2 call-path grep)→commit B runner。Owner: PM。ref `2026-05-30--a2_lcs_fade_stage0r_assessment.md`。 |
| `P2-A1-RUNNER-WIRE-TO-BASIS` | 3 | **NEW 2026-05-30（basis infra DEPLOYED 後的 A1 consumer wire）** — basis_panel 已 live 累積；A1 Stage 0R runner 現為 `draft_only(basis_panel_infra_missing)` stub。本 ticket = 把 A1 cohort 邏輯接上（funding>30% annualized + `basis<0.3%`（as-of LATERAL join `panel.basis_panel`）+ short-only 2-symbol cohort，per A1 spec + runner spec v2 §5）→ stub 轉 runnable。**前向累積限制**：basis_panel 歷史不可 backfill（market_tickers index 壞死）→ A1 首次有效 replay 需 land 後累積 ≥N days。**QC hard-gate**：A1 cohort 方向 + leak-free（basis as-of point-in-time）+ funding+basis 聯合 gate 統計。Owner: PA→E1→QC→E2→E4。Trigger: basis_panel 累積 ≥14d（~2026-06-13）+ A1 candidate 評估。 |
| `P3-MARKET-TICKERS-INDEX-MARK-DEAD-PERSISTENCE` | 4 | **NEW 2026-05-30 per PA basis spec flag（獨立 latent bug）** — `market.market_tickers` 的 `index_price` 87% / `mark_price` 99.6% 持久化值 = 0（column 存在但值壞死）。根因：`step_0_fast_track.rs:128` 逐 frame `index_price.unwrap_or(0.0)` + `mark_price` parser 根本不解析。**strategy live 路徑不依賴此持久化**（用 in-mem cache）；影響面僅歷史 basis/index backfill 能力（basis_panel 已用前向 writer 規避）。評估是否值得修 raw tick 表持久化。Owner: PA + E1。Trigger: 需歷史 index/mark backfill 時。 |
| `P3-BB-STRATEGIES-30D-CATCH-UP-CLOCK` | 4 | **NEW 2026-05-28 per Sprint 2 Q4 hybrid 方案 C (v77)** — bb_breakout (7d n=1) + bb_reversion (7d n=3) 結構性少樣本但**不立即 retire**；給 30 天 catch-up grace 期 (D+30 ~2026-06-27) 看是否達 M=15。**判據**：D+30 若 n_settled >= 15 → 進 Stage 0R baseline 控制組（同 grid+ma 並列）；若 < 15 → 進 M7 decay_signals RETIRED + ADR-0044 deprecation cascade。**真實語意（push-back acknowledged）**：30 天對 entry 嚴策略 = 半路線 Y retire + grace window（operator 拍板 30 天 vs 推薦 60 天）。**Owner**: PM clock watch + (D+30) QC + MIT 評估；**Trigger**: 2026-06-27 cron 或手動評估。 |
| `P2-INCIDENT-POLICY-DISPATCH-TRIGGER` | 2 | **NEW 2026-05-29 Sprint 3 — C4 全 live 的最後一塊** — C4 wire 了 fail-safe 機制但 **incident trigger 未接**：`FAILSAFE_FEED_SENDERS` OnceLock 留 `outcome_tx` seam 但 0 production producer → `outcome_rx` 永空 → timer 永不武裝 → escalate dormant。本 ticket = 接 incident policy（什麼事件/條件觸發 3-way notification dispatch）→ 餵 `observe_dispatch` → 武裝 timer → fail-safe 全 live。**✅ PA spec DONE 2026-05-30**（`docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-30--c4_incident_policy_dispatch_trigger_spec.md`，280 行）。**待 IMPL 證實項**（spec 附章誠實標）：各 producer 精確接點、`engine_dead` 是否升 arm、secret 未配時激進武裝行為。**接上後 BB mandatory re-review** + QA full incident E2E。Owner: ~~PA spec~~ ✅ → E1 → BB → E2 → E4 → QA。Trigger: Sprint 3（spec 已備，E1 IMPL 可隨時派）。 |
| `P2-PACKET-C-C5-GUI-BANNER-ACK-ROLE` | 2 | **NEW Sprint 3 defer (v79 per PC.B + MIT/E2 finding)** — C5 = GUI banner display（tab-governance 頂部）+ operator ack typed confirm（V099-style）+ `failsafe_ack_role` restricted PG role。**MIT R3 finding**：trading_admin = OWNER+SUPERUSER 隱式持全 column UPDATE，V114 column-level 限制只 bind 非-owner role；**production GUI ack 路徑必須用獨立受限 role**（`failsafe_ack_role` 只 column UPDATE acked_*）。C5 須先 provision role 再 wire GUI ack endpoint 呼 `audit_emitter::ack_failsafe_event`。**Owner**: E1a(GUI) + E1(role migration) + MIT(role verify)。**Trigger**: Sprint 3 C4 後。 |
| `COLD-AUDIT-V80-CLOSURE` | 1 | 🟢 **ALL 17 P1 + 15/17 P2 + 7/7 P3 SOURCE DONE 2026-05-29 — 詳情已歸檔** → `docs/archive/2026-05-29--cold_audit_p1_p2_p3_closure_archive.md`。**Design-complete impl-deferred（未來 ML wave）**: P2-06 model_performance evaluator-writer + P2-07 Stage-B cohort replay（無 migration，pkgE report `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-29--cold_audit_pkgE_ml_maturity_p2_05_06_07.md`）。**Runtime deploy-gate 殘留**（見 §0）：(1) PkgD Linux PG empirical (2) Linux `restart_all.sh --rebuild` 套 engine 新碼（已隨後續 deploy）(3) PkgB IPC end-to-end probe（不可 provoke live cancel）。 |
| `P1-OPS-2-HOTRELOAD` | 3 | **NEW 2026-05-26 per E3-HIGH-1 long-term** — `Arc<ArcSwap<BybitCredentials>>` + IPC reload handler = 5s rotation parity with authorization.json；消除 engine restart for Bybit key rotation；Owner: E1；ETA: Post-Sprint 4 |
| `P2-OPS-2-AUDIT-ENDPOINT` | 3 | **NEW 2026-05-26 per E3-MED-1** — `POST /api/v1/security/ipc-secret/rotate` + governance audit row；Owner: E1；ETA: Post-Sprint 4 |
| `P2-OPS-2-CRON-DRIFT` | 3 | **NEW 2026-05-26 per E3-LOW-1** — `helper_scripts/cron/long_lived_secret_drift_check.sh` report mtime + alert > 365d / > 90d；Owner: E1；ETA: Post-Sprint 4 |
| `P2-OPS-2-RUNBOOK-HEALTHCHECK-SQL` | 3 | **NEW 2026-05-28 per PA v1.0 patch out-of-scope obs (MED)** — runbook §10.3 healthcheck integration 假設 `passive_wait_healthcheck.py --check secret_rotation` 已實裝；實際 routine 不存在 → §10 4 verify 條變實質 3 條；Owner: E1 + MIT；ETA: 2-3 hr；triggered if §10.3 cited in cutover |
| `P3-OPS-2-RUNBOOK-EMERGENCY-AUDIT-CONTRACT` | 4 | **NEW 2026-05-28 per PA v1.0 patch out-of-scope obs (LOW)** — runbook §6.2.4 A-1 emergency revoke + §5.2.3 P-3 Bybit 24h soak old key revoke 均缺 audit row contract；Owner: PA + E1；ETA: 1-2 hr spec + 1 hr IMPL；non-blocker first-day live |
| `P1-EARN-WAVE-C-FIRST-STAKE-RUNTIME` | 2 | **SOURCE-LAYER FULLY CLOSED 2026-05-26 / OPERATOR-BLOCKED on OP-1** — Wave C source-layer 全 land（IntentProcessor Earn branch + OPENCLAW_ALLOW_MAINNET=1 + earn_routes.py 1221 LOC 6 endpoint 5-gate HMAC + tab-earn.html 516 + earn-tab.js 750 + replay_earn_preflight.py 799 + test 27+14 PASS）；PG `learning.earn_movement_log` still 0 rows。**仍阻 7 OP hand action**: OP-1-a Bybit web UI mainnet key Read+Trade+Earn / OP-1-b old key delete / OP-1-c new key create no IP restriction / OP-1-d Stage 0R Earn variant §8 8 OQ 拍板 / OP-1-e ssh trade-core 鍵入 + 改 bybit_endpoint demo→mainnet / OP-1-f Python /auth/renew 簽 authorization.json / OP-3 first stake $100-200 Flexible via tab-earn。**5 可代做 post-1..5**（待 OP-1-e 觸發）。 |
| `P2-EARN-WAVE-D-CONTRACT-INTEGRATION-TEST` | 2 | **NEW 2026-05-26 per E2 round 2 carry-over** — round 2 揭無 integration smoke test（frontend phrase build → POST → backend canonical → Rust IPC roundtrip 全鏈）；現 27 tests 全 FastAPI TestClient + mock IPC。**修法**: Wave D Rust IPC 接通後新增 1 integration test 跑全鏈。Owner: E1 + E1a + MIT；ETA: ~3-5 hr；阻 Wave D Rust 接通驗證 |
| `P1-EARN-WAVE-D-RUST-HMAC-CANONICAL-FORM` | 1 | **NEW 2026-05-26 per E2 round 2 HIGH risk** — Python 端 HMAC canonical 用 `json.dumps(sort_keys=True, separators=(",",":"))`；Rust 端 Wave D 若用 `serde_json::to_string` default 順序非 sort_keys → HMAC byte 不對齊 → Wave D Rust IPC 接通即 fail。**修法**: Wave D PA spec 必明定 Rust 端用 `BTreeMap`/serde 顯式排序對齊 Python `sort_keys=True`；IMPL 必 cross-language HMAC byte-identical test (fixture amount=150)。Owner: PA spec + E1 Rust IMPL + E4 cross-lang test；ETA: ~4-6 hr；阻 Wave D Rust IPC roundtrip。ref earn_routes.py:402 `_verify_stage_0r_hmac` |
| `P1-OP1-BYBIT-ENDPOINT-FILE-MISCONFIG` | 1 | secrets file 內容 `"demo"` (live slot 標 live 但 endpoint 標 demo) | OP-1 secret swap 同步改 file 為 `mainnet`；E1 SSH atomic restart；~2 min |
| `P1-EDGE-2` (funding_arb) | – | ✅ **ARCHIVE-READY 2026-05-26 per AMD-2026-05-26-01 / no-revive** — operator chose (D) 3C TOML deprecation closure；funding_arb V2 Retired closed；strategy roster 5→4 textbook。詳情已歸檔 → `docs/archive/2026-05-31--todo_v92_archive.md` §E。revive 須走 AMD amendment + ADR-0046 Accepted + 5-gate + Stage 0R replay preflight。 |
| `P3-WORKFLOW-F-D7-CARRYOVER` | 4 | **NEW 2026-05-26 per R4 Pass B 3 LOW carry-over** — D+7 (~2026-06-02) E1 `#[deprecated]` IMPL piggyback：(1) EA-3 hotfix spec 加 `> Status: Superseded per AMD-26-01` header (2) SQL V033 `fills_exit_reason.sql` 加 historical-only header (3) `docs/README.md` line 226 specs/ 目錄補 PA spec entry；Owner: E1 piggyback + R4 D+7 cycle verify；ETA: 30 min |
| `P1-LG-5` | 4 | LG-5 reviewer maturity watch | source 活躍；7d 共 66 review_live_candidate verdict=defer；90d cadence 觸發 review |
| `P1-HALT-TRIGGER-ROOT-CAUSE-INVESTIGATION-1` | 3 | v56 P0 未解 root cause；H4 healthcheck [69] LIVE | forensic `halt_audit.log` armed；passive wait + 90d review 2026-08-21 |
| `P1-LEASE-1` | 3 | 清掃 terminal `lease.rs:303` + HashMap leak | 依賴 P0-LG-3 IMPL DISPATCH；工時 ~4-6h |
| `P1-EDGE-P2-3-PH1B-DYNAMIC-BACKOFF-FOLLOWUP` | 4 | Phase 1b spec §5.4 完整 dynamic backoff state machine | Phase 2a Demo PASS 後另開 PR；PA 估 ~130 LOC |
| `P1-INTENTYPE-FIELD-VISIBILITY-DEFER` | 4 | OrderIntent struct field `pub → pub(crate)` 影響 4 integration test + IPC serde + openclaw_types re-export = builder pattern 重構 | PA builder pattern spec + E1 IMPL ~4-6 hr；defer 下個 sprint |
| `P3-SUB-AGENT-HYGIENE-SOP-CARGO-TEST-AFTER-ATOMIC` | 3 | **NEW 2026-05-25** — E4 sub-agent 跑 `ssh cargo test --release` 觸 multi-session race；SOP 寫入 prompt template | PA spec + 主會話 prompt template update；~1 hr |

**v5.8 24 H 級 ticket**（按 module 分組）→ ref `docs/archive/2026-05-21--todo_v60_archive.md` §B（24 條 carry into Sprint 1A-β/γ/δ/ε 期間並行補）

### §6.1 Alpha-Edge Research Program — Active Dispatch（v93 整合，PM 2 簽 PASS）

**SSOT**：`docs/execution_plan/2026-05-31--alpha_edge_research_execution_plan.md`（4-track work-chain + acceptance + 並行圖 + gate 全文）｜**findings**：`docs/audits/2026-05-31--p0_edge_cost_wall_investigation.md`
**主線判定**：成本牆（edge 1-3bps ≪ 成本 11-27bps）+ 資料深度（klines 56d）兩道 binding constraint；翻牆只有 ① 低 turnover 多日（**critical path**，backfill 快解）② 事件驅動 listing fade（~Q4）。

**NOW — 3 並行 session（PM 2 簽後已派，2026-05-31 結果）**：

| Session | Track | Owner chain | Acceptance（exit，可證偽）| Blocked-on |
|---|---|---|---|---|
| **S1-W1-S1** ⭐ | T1 critical | PM→MIT+operator→PA | ✅ **MIT advisory PASS + OP decision 2026-05-31**：approve `market.klines` 1095d + 18mo + full 797-symbol survivorship collection / core25 primary analysis（225 delisted/Closed overlap；純 survivor-only 排除）。Report: `docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-31--s1_w1_s1_retention_symbol_universe.md`；artifact: `...--survivorship_universe_18mo_usdt_perp.csv` | **new requirement**：automated breadth-ladder analysis must be integrated before S1-W2 verdict; S1-W1-S2 still waits for amended execution packet + E1 script |
| **S2-W0-S1** | T2 Gate-A(kill-gate) | PM→QC+MIT→joint;BB | ✅ **PROCEED**：maker-fill feasibility 59/67=88.1% at +500bps trigger / 1bp PostOnly / 60s BBO-touch；Wilson 78.2-93.8%；>30% kill line. Report: `docs/CCAgentWorkSpace/QC/workspace/reports/2026-05-31--s2_w0_s1_listing_gate_a_feasibility.md` | Gate-B requires longer BB PreLaunch phase-transition probe + capture-only collector design/review; not alpha proof |
| **S4-W0-S1** | T4 | PM→MIT+E1→MIT | ⛔ **BLOCKED_ON_RETENTION + SCRIPT / DOWNGRADED by OP 2026-05-31**：2024-11 bull data is allowed only as regime/falsification evidence, not standalone confidence or promotion proof；must expand to multi-regime S1-Sx robustness overlay. Report: `docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-31--s4_w0_s1_bull_regime_backfill_preflight.md` | PA/MIT must redesign S4 as global cross-regime gate; funding storage decision deferred until amended packet |

**gated 後續**（詳 plan §2 + OP amendment 2026-05-31）：PA/MIT amend execution packet for (a) alpha-history storage, (b) **automated breadth-ladder**, (c) **global regime robustness overlay for S1-Sx** → E1 public Bybit historical backfill writer（klines 1d/4h + funding history if approved, idempotent + coverage report）→ S1-W1-S2/S3（執行回填含 delisted + 品質 verify）→ **S1-W2-S0 breadth-ladder automation**（initial one-shot after backfill + scheduled rerun triggers: monthly when ≥30d new data, universe drift >10%, or before promotion）→ **S1-W2-S1/S2**（TSMOM + X-sec leak-free 回測，2 並行；net>2×成本 / OOS≥0.5×IS / PSR>0.95 / DSR>0；**OOS<0.3×IS=kill**）→ **S1-W3-S1**（CP-2 go/no-go + Track3 載體裁定）｜S2-W1+（Gate-A PASS；先做 BB 24h PreLaunch transition probe，再 collector IMPL → 累積 ~Q4 → Gate-B 回測）｜S3-W1-S1（ensemble，blocked-on Track1 GO；**ρ>0.5=kill**）｜S4/Sx regime overlay（no single bull/rally slice can promote; all track verdicts must report bull/range/bear/chop/high-vol slices and stale-data sensitivity）

**Checkpoints**（operator 決策點）：CP-1 ~週2（回填+品質 green / Gate-A verdict / bull 回填）｜CP-2 ~週7（Track1 GO/NO-GO/PARTIAL）｜**CP-3 ~9月（operator 三選一：放寬約束 / learning-only / 縮 universe）**

**紀律（plan §0，dispatch 必帶）**：① backfill 必含 delisted（倖存者偏差是 T1 唯一致命污染；SoT=`symbol_universe_snapshots`）② Gate-A maker-fill kill-gate 先於 collector IMPL ③ leak-free shift(1) 每回測 day-1 ④ ≤7 並行（NOW=3 / max=4）⑤ retention 365→1095d 已 operator-approved but must be implemented via safe runtime/PG gate before backfill ⑥ breadth-ladder is automated evidence, not ad hoc PM judgment ⑦ no bull-only or stale-2024-only confidence; every candidate needs cross-regime robustness/falsification before promotion.
**M7 V116 解凍**：held；觸發 = 首個 net-positive candidate 達 stage0_ready（S1-W3-S1 GO 或任一 track 過 gate）。
**並行既有 workflow**：Workflow B（ADR-0046 basis split，§3）+ Earn Wave C（operator-gated）不受 alpha-edge 影響，可並行（≤7 ceiling 內）。

---

## §7 Operator Action Checklist（D+0 ~ Sprint 4 first Live ETA）

> 已 DONE operator action（AMD-25-01/02 confirm / AMD-21-01 v2 sign-off / canary rename commit / funding_arb (D) 拍板）→ `docs/archive/2026-05-31--todo_v92_archive.md` §F。

| 日期 | Action | 預期時間 | Trigger | 卡進度後果 |
|---|---|---|---|---|
| **NOW** | ✅ **OP-ALPHA-HISTORY PARTIAL DONE 2026-05-31**：approved `market.klines` 365→1095d + window=18mo + full survivorship collection / core25 primary analysis；added breadth automation requirement；downgraded S4 to S1-Sx regime/falsification overlay | – | operator decision | Remaining: PA/MIT amend packet for breadth-ladder + regime robustness + funding-history storage path before E1 script |
| **D+2-D+3** | OP-1 a-f Bybit Web UI **mainnet** key 重發（per C-3 2026-05-26：現 2 demo key + 33d TTL，mainnet key 未發）| 5-10 min | OP-1 pre-verify done | 阻 Sprint 4 first Live + Earn Wave C production deploy |
| **D+2-D+3** | OP-2 Stage 0R Earn variant 仲裁（8 OQ）| 30-60 min | OP-1 完成 | 阻 first stake |
| **D+2-D+3** | OP-3 first stake **$100-200 USDT Flexible-only** via tab-earn（per C-5 2026-05-26 拍板 USDT only）| 5 min | OP-2 拍板 | 阻 `learning.earn_movement_log` rows>0 |
| **D+5** | P0-EDGE-1 + P0-LG-3 + P0-OPS residual OP gates closure ETA 填 §10 P0 precondition | 30 min | PM ping | P0 runtime/migration/OPS-1 已收口；仍需 pg_dump cron+restore drill、system-level unit install、LG-3 gate、EDGE-1 Alpha path |
| **W12** | **Sprint 2 業務 Alpha Tournament 派發** | – | alpha 重定向診斷 + candidate evidence | 阻 §1 P0-EDGE-1 AC-A (ii) 路徑 |
| **W18-21 (~2026-09)** | **★ Sprint 4 first Live $500（per v92 D2 走 LiveDemo 降級路徑）★** | – | P0-EDGE-1 + LG-3 + OPS residual OP gates 全 closure | – |

**Operator 手做時間 D+0~D+5 ≈ 2.5-4 hr**（OP-1 系列佔大頭）

---

## §8 Backlog by Cluster（per PM §3 parallel 分組）

> 已 CLOSED：§8.1 Cluster 1 6/6（Workflow A/D/E/F/J + OPS [78]）+ §8.5 C2（ADR-0030 4-gate verify）→ `docs/archive/2026-05-31--todo_v92_archive.md` §G。

### §8.2 Cluster 2 — Partial-Dependent（B Phase 1→2→3 / Sprint 1A-γ/δ/ε）
- **Workflow B Phase 1**（Sprint 1A-γ）：ADR-0046 basis spec execution split IMPL（PA → E1 → E2）
- **Workflow B Phase 2**（Sprint 1A-δ）：funding_arb IMPL + MIT V117 dry-run（PA → E1 → MIT → E2）
- **Workflow B Phase 3**（Sprint 1A-ε）：funding_arb live + BB approve + QA backfill（E4 → BB → QA）
- 估時 24-30 hr total；不阻 Sprint 2 主軸

### §8.3 Cluster 3 — Operator-Gated（殘留）
- OP-1 a-f Bybit Web UI key 重發（D+2-D+3）
- OP-2 Stage 0R Earn variant 仲裁（D+2-D+3）
- OP-3 first stake（D+2-D+3）
- P0-EDGE-1 + LG-3 + OPS residual OP gates closure ETA（D+5）

### §8.4 Sprint 2 業務 Alpha Tournament dispatch（W12-15）
**SSOT**：`docs/execution_plan/2026-05-26--alpha_tournament_ssot_spec.md`
**Stream A**（Sprint 2 IMPL 2 candidate + 1 DRAFT）：
- A1 funding short-only > 30% annualized（per v92 改 funding percentile rank 連續訊號）
- A2 liquidation cascade fade — 2026-05-31 maker-fill feasibility Linux PG verdict=`reject`（1bp 60s touch 49.07% < 50%）
- A3 BTC/ETH cointegration pairs DRAFT — 2026-05-31 Linux PG precheck verdict=`reject`（corr/half-life/fee gate fail）
- **v92 重定向新候選**：listing pump-dump fade（首選 ~50-65%）+ funding-extreme directional（資料可行性診斷 dispatched）
**Stream B**（V108/V109 spec + MIT）
**Stream C**（Optuna 後端 skeleton；依 V111 land）
**估時**：248-351 hr / 3w wall-clock / 7 並行 sub-agent

### §8.5 PA Condition Follow-up Deferred（殘留）
- **C3** ADR-0046 公式補位（funding_cost_bps + borrow_cost_bps）+ dual-write phase + V117 預寫 pending（PA → E1 → MIT → E2；8-12 hr）
- **C4** E4 canary [80] full sweep verify namespace="canary"（E4；2-4 hr；依 canary deploy 穩定）

---

## §9 Cascade Pending（AMD/ADR → DOC-XX per FA §3）

> 已 CLOSED cascade（AMD-25-01 / AMD-25-02 / drift audit / funding_arb (D) Workflow F）→ `docs/archive/2026-05-31--todo_v92_archive.md` §H。

| 來源 | Cascade 目標 | Owner | Status |
|---|---|---|---|
| **AMD-2026-05-21-01 v2 Wave 5** | ADR-0034 LAL 對齊矩陣加 Autonomy Level / ADR-0040 §Decision 5 / ADR-0042/0044/0045 wording sync + V099 schema + GUI sub-section + Rust SM-04 patch | PA + E1 + E1a + MIT + R4 | 🟡 **Packet A+B + TOTP source + ADR/R4 landed 2026-05-28**（V099 runtime apply/register + API/GUI posture deployed fail-closed at `a07a08c0`; TOTP source backend tests PASS but runtime enrollment missing; Packet C core E4 PASS but engine integration missing; R4 report `2026-05-28--wave5_totp_packetc_adr_ops_r4.md`）；remaining = Packet C engine integration + runtime TOTP secret enrollment（per v92 D1 active-IMPL FROZEN）。 |
| **ADR-0046 (Proposed)** | funding_arb.rs IMPL + V117 migration spec + Optuna search space update | PA + E1 + MIT | Sprint 1A-δ/ε 平行 land |
| **v92 V### reconcile (2026-05-31)** | M7 V116 / M5/M7/M12/M13 reserve V118-124 doc cascade C-1..C-6 | TW | 🟡 PENDING — 已 applied SQL 內容不動，僅 doc-side note；真實 `sql/migrations/` head=V115 |

---

## §10 V1→V5.8 Drift Audit Closure Pointer（2026-05-25）

**狀態**：✅ **FULLY DONE + 3 端同步 + PM/PA/FA 三方 sign-off APPROVED-CONDITIONAL**

**SSOT 文件指針**（4 commits at cf61d1f0）：
1. **Drift audit 終稿** — `docs/audits/2026-05-25--v1_to_v58_full_consolidation_drift.md`（499 行 / 22 plan/audit files / 8 errors corrected / 10 真實 unresolved / 72% false positive rate 自評）
2. **AMD-2026-05-25-01** Commercialization Boundary: Exchange-Native Only — `docs/governance_dev/amendments/2026-05-25--AMD-2026-05-25-01-commercialization-exchange-native-only.md`
3. **AMD-2026-05-25-02** v5.5 Bot Positioning + Capital Structure Formalization — `docs/governance_dev/amendments/2026-05-25--AMD-2026-05-25-02-v55-bot-positioning-capital-structure-formalization.md`
4. **v5.8 文檔 10 patches** — `docs/execution_plan/2026-05-20--execution-plan-v5.8.md`

**核心發現摘要**：ADR-0028/0029 編號順移 confirmed（實際 land ADR-0030/0031/0032）；W-AUDIT-8b tombstoned per AMD-15-02 v0.7；F-22 label_close_tag NULL CLOSED by AMD-11-W6-1；F-08 vs MIT-P0-2 RECONCILED；G1 v1.9 6 P1 6/6 CLOSED `07cfcb72`；SSH empirical 3 PASS。**詳細逐項發現 + Cluster 1 follow-up（全 CLOSED 2026-05-27）→ `docs/archive/2026-05-31--todo_v92_archive.md` §G/§J。**

---

## §11 Layered Autonomy v2 Wave 5 Cascade Pointer（2026-05-22）

**狀態**：🟡 **Packet A+B runtime + TOTP source + ADR/R4 + Packet C core regression landed, fail-closed by design** 2026-05-28 + ✅ **operator APPROVE 2026-05-27** + CC APPROVE A 級；**active-IMPL FROZEN per v92 D1**；full Wave 5 close still requires runtime TOTP enrollment and Packet C engine integration.

**4 個 SSOT 文件指針**：
1. **AMD-2026-05-21-01 v2** — `docs/governance_dev/amendments/2026-05-22--AMD-2026-05-21-01-autonomy-fully-with-failsafe.md`（684 行）
2. **PA spec v2** — `docs/execution_plan/2026-05-22--autonomy_level_toggle_design_spec.md`（1031 行）
3. **V099 schema spec** — `docs/execution_plan/specs/2026-05-22--v099-autonomy-level-config.md`（568 行）
4. **CC re-audit** — `docs/CCAgentWorkSpace/CC/workspace/reports/2026-05-22--layered_autonomy_v2_reaudit.md`（A 級）

**Wave 5 cascade IMPL roadmap**（updated 2026-05-28）：
1. **Packet A V099 schema land** — ✅ DONE physical apply/register + checksum drift 0.
2. **Packet B GUI/API Autonomy Posture** — ✅ DONE commit `a07a08c0`. Switch remains blocked by P0-EDGE evidence and runtime TOTP enrollment.
3. **TOTP backend wire-up** — 🟡 SOURCE DONE / RUNTIME ENROLLMENT PENDING.
4. **Packet C Rust SM-04 patch** — 🟡 SOURCE E2/E4 DONE; full integration still needs engine notification timeout scheduler, exchange conditional SL sync, audit emit.
5. **5 module ADR sync + R4 cross-ref audit** — ✅ DONE: ADR-0034/0040/0042/0044/0045；R4 report `2026-05-28--wave5_totp_packetc_adr_ops_r4.md`.

**3 並行 ceiling**（Wave-X2 per PM §5）

---

## §12 Deferred / Dormant Watch（revisit conditions explicit）

| ID | 狀態 | 觸發 / Deadline |
|---|---|---|
| **F workflow** Phase 2 三策略 A/B QC defer | DEFERRED | revisit = $5k+ account + Sprint 2 W2-A evidence + cost gate 改善 |
| `P1-OBS-PLACEMENT-BBO-V094` | DEFER | Phase 1b 14d freeze 後（~2026-06-01）|
| `P1-SWEEP-A-AXIS-PRUNE` | DEFER | 下輪 sweep（Phase 2a verdict 後）|
| `P1-WATCHDOG-NETOUTAGE-SPARSE-LOG-OQ` | DEFER | 觀察 canary NETWORK_OUTAGE event 頻率 |
| `P2-CLIPPY-CLEANUP-1` | ACTIVE | Sprint 1A 進行中並行清；E1 4-6 hr |
| `P2-FALLBACK-DEAD-ENUM-90D-AUDIT` | PASSIVE WAIT | 2026-08-21（ADR-0028 90d cadence）|
| `P2-AUDIT-DEAD-CODE` | DORMANT | D-16；Sprint N+6+ |
| `P2-WP05-CSP-UNSAFE-INLINE` | DEFER | live-gate 前升 P1 |
| `P2-CANARY-FILE-SIZE-REFACTOR` | P5 DEFER | 等 800 LOC bulk wave |
| `P3-H0GATE-FILE-SPLIT` | DEFER | 獨立 wave；h0_gate.rs 1243 行 > 800 |
| `P3-H0-LATENCY-1H-RESET-INTEGRATION-TEST` | LOW NTH | 既有 unit test 覆蓋 |
| `D-13` Cognitive Modulator | DORMANT | 3-Tier 數據源未接齊；Sprint N+8+ |
| `D-14` DreamEngine 完整自主進化 | DORMANT | Foundation Model + L4 meta-learning 未 ready；long-tail |
| `D-15` OpportunityTracker 全 Agent 注入 | DORMANT | 不影響 supervised live；Sprint N+5 可選 |
| `D-16` openclaw_core 9 模組 sunset | DORMANT | 7 已清；餘 2 待 PA；Sprint N+6+ |
| `D-17` Layer 2 自主推理循環自動觸發 | **PERMANENT DORMANT** | ADR-0020 manual+supervisor-only；**不解** |
| `D-02` Layer 2 手動 7d 試運行 SOP | DORMANT | Operator 自執行 |

---

## §13 Drift / Risk / Multi-Session Race Watch

| 風險 | 狀態 | Mitigation |
|---|---|---|
| **proc-exe drift**（cargo test multi-session 觸 incremental rebuild）| Active；3 次 reproduce 2026-05-25 | per Hygiene SOP `build_then_restart_atomic.sh` 7-phase flock；`--require-clean-build-window` flag；ref `P3-SUB-AGENT-HYGIENE-SOP-CARGO-TEST-AFTER-ATOMIC` |
| **DEPRECATED.md 引用警報** | NEW per FA §5 | 任何代碼/文件仍引舊 DOC = active blocker；FA grep 週期 |
| **5-gate / hard boundary 觸碰 record** | OPENCLAW_ALLOW_MAINNET=1 set 2026-05-25 + authorization.json missing OP-1 預期 | 14d lineage scan per FA |
| **跨平台 path 違規** | proc-exe drift 揭發 path migration | `/home/ncyu` / `/Users/` 硬編碼 weekly grep；無 `OPENCLAW_BASE_DIR` env 預設 |
| **Multi-session race** | mitigated per memory `feedback_git_commit_only_for_metadoc` + `feedback_fetch_before_dispatch` | meta-doc 用 `git commit --only`；dispatch 前 `git fetch`；sub-agent prompt hygiene 警示段落 |
| **.docx vs .md 漂移** | FA non-blocker | skill 9.2 SOP；考慮 pre-commit hook |

> 已 CLOSED watch（[78] feature_baseline_writer cron stale / Hygiene Option E FD 200 inherit）→ `docs/archive/2026-05-31--todo_v92_archive.md` §E。

---

## §14 排程 + Milestone

| 日期 / Sprint | 工作 | Gate |
|---|---|---|
| **2026-06-01** | C10 funding harvest 7d demo AC #1/#4 sample | Stage 1 Demo verdict |
| **2026-06-02** | 14d bucket-split AC verdict（ALT 25.7% / large_cap 66.7%）| QC EA-1 Phase 1b verdict |
| **2026-06-02** | `P3-WORKFLOW-F-D7-CARRYOVER` E1 `#[deprecated]` IMPL piggyback | R4 D+7 cycle verify |
| **2026-06-09** | `P1-CONDITIONAL-WATCH` TONUSDT 30d evidence freeze | QC 2026-05-11 zero-cost #4 |
| **2026-06-10** | OPS-2 Phase 2 cutover (D+14 soak end) | E1 PR move fallback + main.rs panic block + Python reason rename + AuthError variant delete |
| **2026-06-11** | AC-S2-A-3 ≥1 candidate evidence 累積（14d demo via AC-19 cron）| Sprint 2 Stage 0R baseline |
| **2026-06-13** | basis_panel 累積 ≥14d → `P2-A1-RUNNER-WIRE-TO-BASIS` + A1 candidate 評估 | A1 forward replay |
| **2026-06-27** | `P3-BB-STRATEGIES-30D-CATCH-UP-CLOCK`（bb_breakout/bb_reversion D+30）| n_settled ≥ 15 → Stage 0R baseline / < 15 → M7 retire |
| **W12-15** | **Sprint 2 業務 Alpha Tournament dispatch** | 5 stream × 7 並行 sub-agent / 248-351 hr |
| **2026-08-21** | `P2-FALLBACK-DEAD-ENUM-90D-AUDIT` + `P1-HALT-TRIGGER` review | 90d cadence |
| **W18-21 (~2026-09 初)** | **★ Sprint 4 first Live $500（per v92 D2 LiveDemo 降級）★** | P0-EDGE-1 + LG-3 + OPS-1..4 全 closure |
| **W44-55 (~2027 Q1-Q2)** | **Y1 末 — autonomy 66%** | Copy Trading evidence gate / Overlay verdict |
| **~21-24 mo** | **Y2 Q2 Auto-Allocator activation — autonomy 90%** | 6mo Advisory + >80% approval |
| **~32 mo** | **Y3 Q2 — autonomy 95%** | M10 Tier C-E / M12 / M13 Y3+ |

---

## §15 跨 Wave 衝突仲裁

> 已 WITHDRAWN/OBSOLETED：#1（LG-3 ↔ funding_arb FALSE dep）+ #5（Workflow B V117 ↔ funding_arb V2 timing）→ `docs/archive/2026-05-31--todo_v92_archive.md` §I。

| # | 衝突 | 解 |
|---|---|---|
| 2 | Phase 2a engine STOPPED ↔ verdict 視窗累積 | 每暫停 1h 失 ~0.4 rows；後續禁無預警 stop |
| 3 | W-AUDIT-9 graduated canary path ↔ ExecutorAgent shadow_mode | per AMD-2026-05-15-01：Stage 0R replay preflight + Stage 1 demo |
| 4 | Sprint 1A-β/γ/δ 順序 dispatch ↔ cross-V### dependency | per v58-CR-9 PG dry-run + cross-V### dependency graph |
| 6 | **Cluster 並行 ↔ Multi-session race** | 每次 sub-agent dispatch 前強制 `git fetch`；meta-doc `--only` commit |
| 7 | **Sprint 2 Stream B V108/V109/V111 ↔ Wave-X2 V099 cross-ADR collision** | Wave-X2 V099 與 V112 LAL 同主路徑；不可同 Sprint 1A-ε 並行 |

---

## §16 派工規則 + SSOT Pointers

### Handoff SOP（per CLAUDE.md §八 + docs/agents/todo-maintenance.md）

- **實作鏈**：`PM → PA → E1/E1a → E2 → E4 → QA → PM`
- **安全 / 部署 / runtime**：`PM → E3 → BB（若涉交易所）→ PM`
- **量化 / 資料**：`PM → QC → MIT → AI-E（若涉模型成本）→ PM`
- **Governance cascade**：`PM → CC → FA → PA → R4 → TW → PM`
- **Sign-off SOP**：`cargo test -p openclaw_engine --release` 覆蓋 tests/ integration crate
- **GUI JS 變動**：sign-off 強制 `node --check`
- **V### migration**：Linux PG empirical dry-run mandatory before IMPL sign-off
- **Meta-doc 改動**：dirty trees 用 `git commit --only <files>` 隔離 race
- **每 green checkpoint**：commit subject + body，push origin，再 ssh trade-core fast-forward；doc-only commits 加 `[skip ci]`

### Handoff 檢查指令
```bash
git -C /Users/ncyu/Projects/TradeBot/srv status --short --branch
ssh trade-core "cd ~/BybitOpenClaw/srv && git status --short --branch"
ssh trade-core "python3 helper_scripts/canary/engine_watchdog.py --data-dir /tmp/openclaw --status"
ssh trade-core "cd ~/BybitOpenClaw/srv && PGHOST=localhost PGUSER=trading_admin PGDATABASE=trading_ai bash helper_scripts/db/passive_wait_healthcheck.sh --quiet"
```

### SSOT Pointers
- **v5.7 主檔**：`docs/execution_plan/2026-05-20--execution-plan-v5.7.md`
- **v5.8 主檔**：`docs/execution_plan/2026-05-20--execution-plan-v5.8.md`（10 patches land 2026-05-25）
- **Sprint 2 Alpha Tournament SSOT**：`docs/execution_plan/2026-05-26--alpha_tournament_ssot_spec.md`
- **Sprint 2 dispatch packet**：`docs/execution_plan/2026-05-25--sprint_2_business_dispatch_packet.md`
- **M7 V116 decay detector spec**：`docs/execution_plan/specs/2026-05-31--v116-m7-decay-detector-spec.md`
- **drift audit 終稿**：`docs/audits/2026-05-25--v1_to_v58_full_consolidation_drift.md`
- **AMD-25-01**：`docs/governance_dev/amendments/2026-05-25--AMD-2026-05-25-01-commercialization-exchange-native-only.md`
- **AMD-25-02**：`docs/governance_dev/amendments/2026-05-25--AMD-2026-05-25-02-v55-bot-positioning-capital-structure-formalization.md`
- **AMD-21-01 v2**：`docs/governance_dev/amendments/2026-05-22--AMD-2026-05-21-01-autonomy-fully-with-failsafe.md`
- **PA spec v2**：`docs/execution_plan/2026-05-22--autonomy_level_toggle_design_spec.md`
- **V099 spec**：`docs/execution_plan/specs/2026-05-22--v099-autonomy-level-config.md`
- **CC re-audit Layered Autonomy v2**：`docs/CCAgentWorkSpace/CC/workspace/reports/2026-05-22--layered_autonomy_v2_reaudit.md`
- **SPECIFICATION_REGISTER**：`docs/governance_dev/SPECIFICATION_REGISTER.md`
- **Active ADR**：ADR-0006/0017/0018/0020/0022/0023/0024/0028/0029/0030/0031/0032/0033/0034/0035/0036/0037/0038/0039/0040/0041/0042/0043/0044/0045 + ADR-0046（PROPOSED 2026-05-25）
- **Active AMD**：AMD-2026-05-09-03 / -10-03 / -10-04 / -10-05 / -11-W6-1 / -15-01 / -15-02 v0.7 / -20-04 / -21-01 v2 / -25-01 / -25-02 / -26-01
- **Sub-agent hygiene SOP**：`docs/agents/sub-agent-hygiene-sop.md`
- **Bybit API reference**：`docs/references/2026-04-04--bybit_api_reference.md`
- **TODO archive**：`docs/archive/2026-05-31--todo_v92_archive.md`（v92 closed/historical 抽出）+ `docs/archive/2026-05-29--cold_audit_p1_p2_p3_closure_archive.md`（cold-audit）+ `docs/archive/2026-05-21--todo_v60_archive.md`（v60 §A-§F）

---

## §-1 歷史 closure 摘要（≤14d；舊細節 → archive）

> 2026-05-28 及更早的逐日 closure 明細 → `docs/archive/2026-05-31--todo_v92_archive.md` §J。

- **2026-05-30 7-gap 解決 + A1 前置 P2-BASIS-PANEL-INFRA DEPLOYED（operator「解 gap + 並行完成 A1 前置」）**：
  - **7 gap triage**：G3/G4 已解（doc）；G7 false-alarm；**G6 合理延後**（psycopg2-TCP env secrets drift，非 code bug，B runner offline 已驗，留 deploy-gate carry-over）；**G1/G2/G5 解決**（commit `46e0e825`：risk.rs 822→605 pure-move split + main.rs tracing var 註 + single_watcher 註解；E1→E2 APPROVE→E4 PASS）。
  - **A1 前置 P2-BASIS-PANEL-INFRA 並行完成 + DEPLOYED**（commit `e63a00e0`）：PA spec → MIT V115 Linux-PG double-apply dry-run PASS → E1(r1+r2) → E2 APPROVE → E4 PASS。**DEPLOYED**：V115 applied + basis_panel **live 25 sym / 60s flush 實寫**（A1 forward-accumulation 啟動）。
  - **deploy**：engine PID 191366→**251791**（`e9f01569`）；healthz 200 / 0 panic / 110017 仍 fixed / C4 dormant；basis_panel 真實 signed 值（e.g. ADAUSDT basis%=-0.0428）。
  - **新 follow-up**：`P2-A1-RUNNER-WIRE-TO-BASIS` / `P3-MARKET-TICKERS-INDEX-MARK-DEAD-PERSISTENCE`。
  - **git hygiene 教訓**：誤 `git stash drop` 一個 pre-existing stash → 立即 `git stash store <sha>` 復原（3 pre-existing stash 完整）。SOP：stash push 確認有存才 drop。
- **2026-05-29 全盤閉環核實 + gap audit（operator 要求）— ✅ 真實閉環成立**：
  - **B runner 收尾**：QC hard-gate 抓 k_prior over-PASS bias → E1 round 2 mirror 8c fetch_k_prior → E2 APPROVE → E4 PASS（smoke 13/13）→ commit `21db54b1`。
  - **PM git/runtime ground-truth**：三端同步 `aaeecf1d`；deployed binary `26bbc241` = 當前 main Rust（0 drift）；runtime healthz 200 / PID 191366 / 0 panic / 0 110017。
  - **FA 獨立 gap audit**：**真實閉環 ✅，0 BLOCKER / 0 安全不變量違反 / 0 overstated DONE**。對抗鏈攔下 3 真問題（BB D2 真錢誤刪 / QC B silent-stat / E1 btc_lead_lag 生產 bug）。7 gap 全 LOW/MINOR → 收進 `P3-SESSION-CLEANUP-FA-AUDIT-FOLLOWUPS`（已 DONE）。
- **2026-05-29 4-track 衝刺收尾 — operator 4-step plan 全執行 + batched deploy**：
  - Track D committed `af92e2ca`（btc_lead_lag 真生產 bug + bin-crate lock）；C4 chain 全綠 → `a8ba146c`（conditions 清）；batched deploy engine **PID 191366** SHA `26bbc241` verified（含 A+C(D2)+C4+D-hygiene）；ssh probe basis_panel 完全不存在 → A1 BLOCKED draft_only → 新 `P2-BASIS-PANEL-INFRA` + `P1-A1A2-STAGE0R-RUNNER-IMPL` ticket。三端同步 `44990d13`。
  - **這輪攔下 3 真問題**（對抗鏈見效）：BB D2 真錢誤刪 CRITICAL + QC B silent-stat/結構不匹配 + E1 btc_lead_lag 生產 bug。
- **2026-05-29 P1-110017 治本 fix 全鏈 + DEPLOYED + VERIFIED**（operator「派發→修→治本→直接 deploy」）：
  - 全鏈綠 PA RCA → E1 r1+r2 → BB APPROVE-WITH-MANDATORY-GUARD → E2 APPROVE-WITH-CONDITIONS → E4 PASS（lib 3609/0）。commit `caf008b6`（fix）+ docs；三端 `5bf8085c`。Linux atomic deploy engine **PID 113386** `/proc/exe SHA == post-build SHA`。部署驗證 loop 已修（`dispatch_structural` 110017 reject new-engine start 後 0 筆；TRXUSDT orders last 60s=0；position removed）。4 follow-up logged（§6）。
- **2026-05-29 operator-requested runtime recovery 確認 + 110017 close-loop RCA**：確認全進程/服務正確啟動（engine PID 27582 deploy intact / uvicorn ×4 healthz 200 / ollama / user watchdog active / PG reachable / 6 cron 全裝）。發現 active bug `P1-110017-POSITION-DRIFT-CLOSE-LOOP`（13:57 cold-restart drift 倉 → 110017 永不成交 → PHYS-LOCK 每 tick 重發 ~1.4/sec 自持迴圈；僅 demo，無真錢）。PM 判讀更正（誠實）：先前報「positions:{} 空 / phantom」三處判讀錯，PA RCA 更正為真 drift 倉。
- **2026-05-29 PM 接手 — #1 LG-3 dispatch ARMED + #2 P2/P3 cleanup batch（operator「先1後2」）**：#1 LG-3 dispatch 預備 ARMED（pre-dispatch freeze CLEAN / V104 still FREE / Gate 2 MIT V104 dry-run done / Gate 1 v56 Layer B +24h ON TRACK ~2026-05-30）。#2 4 ticket 全收（`P1-OPS-2-RESTART-ALL-CP-ATOMIC` / `P1-OPS-2-CI-FLAKINESS-TEST-LOCK` + 新 `P3-OPS-2-CI-FLAKINESS-BIN-CRATE-LOCK` / `P2-OPS-2-GITLEAKS` / `P3-HYGIENE-OPTION-E-FD-INHERIT-CORNER-CASE`）。carry-over：Linux 並發 cargo test --lib ≥5 輪 flake 驗證 + gitleaks operator install + shellcheck 補跑。
- **2026-05-29 PM 接手 health-freeze + runtime reconcile（v84 後）**：三端 sync `8e607415`；engine PID 27582 deploy intact；NEW 發現 trade-core 今日維護重啟窗口（graceful shutdown down ~7h，非 crash；reboot 清 `/tmp/openclaw` → cron sentinel transient，次日自癒）；PM 手動 re-fire `feature_baseline_writer_cron.sh` → [78] 回 PASS。殘留結構性（非本輪可動）：`[74]` FAIL（demo 流量結構無法觸發 max_pending）；edge/alpha WARN 群（P0-EDGE-1 領域）；`[20]` h_state_gateway stub regression（pre-existing）。

**詳細歷史 archive**：
- `docs/archive/2026-05-31--todo_v92_archive.md`（v92 closed/historical 抽出 — version 增量 v75-91 / 舊 runtime snapshot / DONE phase / 已關閉 workflow/queue/cascade/衝突 / 2026-05-28 及更早逐日 closure）
- `docs/archive/2026-05-29--cold_audit_p1_p2_p3_closure_archive.md`（cold audit 17 P1 + 15/17 P2 + 7/7 P3）
- `docs/archive/2026-05-23--sprint_4plus_5plus_wave1_closure.md`（Sprint 4+ §4.1 + Stage A→F + Sprint 5+ Wave 1）
- `docs/archive/2026-05-21--todo_v60_archive.md`（v60 §A-§F + v5.7 12 prefix + W-AUDIT-4b + H+I 批 closure）
- `docs/archive/2026-05-21--sprint_1a_alpha_repair_closure.md`（Sprint 1A α/β/γ/δ/ε）

---

**Maintenance contract**：依 `docs/agents/todo-maintenance.md` 將本檔保持為活躍派工佇列。穩定專案脈絡走 `README.md`；agent 操作規則走 `CLAUDE.md`；歷史 closure 走 `docs/archive/`。三方 sign-off (PM CONDITIONAL APPROVED / PA APPROVE-CONDITIONAL / FA Conditional Approve) 之 BLOCKER 候選 (governance_hub spec / HIST-02 frozen amend / DOC-08 §12 對應 AMD-25-02 cooling) 進 §13 Drift Watch 追蹤。
