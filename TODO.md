# 玄衡 TODO — 活躍派工佇列

**版本**：v82（v81 + 2026-05-29 #2 M11 register-only deployed + #3 V114 sqlx recorded + E2 MEDIUM-1/LOW-1 fixed）
**v82 增量**：operator 指示解 #2 + #3 完成。**#3 V114 sqlx record DONE**：AUTO_MIGRATE=1 → restart → migrator `Applied(1)` "all guards PASS" → `_sqlx_migrations` version=114 success=t → AUTO_MIGRATE 還原 0（唯一 pending 是 V114，無意外 apply）。**#2 M11 register-only DONE + DEPLOYED**（commit `d696b1f2` + `1f33301a`，三端 `1f33301a`）：smoke 移除 run dispatch 保留 register（[48] 只需 experiments growth）；deployed wrapper dry-run 驗 `/replay/run` 3 hits 全註釋 + 0 run_state running + experiments fresh row + [48]/[50] PASS。**E2 register-only review APPROVE-WITH-CONDITIONS deploy clearance YES**；2 follow-up 已修：MEDIUM-1（wave9_audit_incident_scan allowlist 加 `m11_replay_runner_register_only_completed` success，failure 變體保留 incident detection）+ LOW-1（install echo register_only 對齊）。下次 04:00 cron fire 不再製造 zombie。**殘 follow-up**：OQ-2 m11_* event_type enum migration（Sprint 3 Phase A，停 audit_write_failed piggyback）+ PA proposal §4.2 register+run→register-only deviation 文字回簽 + [16] strategist DB 髒參數（另案）+ Sprint 3 Packet C C4/C5/HIGH-1。
**v81 增量**：operator 指示 `restart_all --rebuild --keep-auth` 已執行（02:12 UTC，cargo release 38.84s，engine PID 2248770 + API alive，新 binary 含 Packet C dead-code 模組）。Healthcheck 變化：**`[48]` PASS（M11 cron）+ `[50]` PASS（M11 smoke zombie `6532fc38` 已 operator cancel cleanup）+ `[56]` 不再 FAIL（live_demo pipeline restart 後 alive）**；殘 FAIL = `[74]`（結構性 evidence queue 不變）+ **`[16] strategist_cycle_fresh` NEW**（pre-existing DB 髒參數 `ma_crossover` confluence weight sum 73≠65 restart 暴露 + strategist 5-min cycle 啟動後無 cycle log；strategist=advisory 非交易關鍵；**非 Packet C 造成**，Packet C dead-code 不跑）。**V114 表存在但未進 `_sqlx_migrations`**（`OPENCLAW_AUTO_MIGRATE` disabled deliberate posture，engine boot 不自動 migrate；功能正常因 dead-code 未調用；下次正式 migration deploy 記錄）。**3 follow-up**：(a) M11 wrapper smoke 製造 zombie 設計缺陷（應 register-only 或 run proper timeout/cleanup，否則每日 cron 累積 zombie 觸發 [50]）；(b) V114 sqlx record 形式化；(c) [16] strategist DB 髒參數清理 + cycle wedge 監控（另案，非 Packet C）。三端同步 `58f9519a`（cold-audit doc-only [skip ci] 在我 Packet C 6 commit 上，binary 仍 3004edb4 code 當前）。
**v79 增量**：operator 拍板 `M11.a / PC.B hybrid / 全 10 Qs PA defaults / EA email lettre / BB ATR defer C4 / Q-C 雙路徑 / Q-D 1 attempt / Q-E defer / Q-F dyn / Q-G C4 spec`。Wave 2 全鏈綠：**4 E1 IMPL（C1 dispatchers + C2 V114/audit + C3 providers + M11 cron）+ E1 email RealSmtpTransport(lettre rustls openssl=0) + 3 fix round（V114 GRANT reorder → V114 idempotency nested EXCEPTION → MED/LOW concurrency+secret）**。Review：**E2-M11 APPROVE-WITH-CONDITIONS（0 BLOCKER）+ E2 full Rust APPROVE-WITH-CONDITIONS（1 HIGH design defer Sprint3 / MED+LOW fixed）+ E4 regression PASS 3575/3575（+6，對抗 test T4.12 親驗）+ MIT V114 三輪（R1 抓 GRANT-after-compression / R2 抓 idempotency twin BLOCKER / R3 APPROVE full deploy-ready 三跑 EXIT0）**。M11 cron live + `[48]` FAIL→PASS。V114 LEAVE TABLE（sqlx 下次 engine deploy apply，checksum-safe）。HEAD pending v79 commit；previous `be529e96`(MIT R3) + `575a0a94`(MED/LOW)。
**v80 增量**：只讀 cold audit 全鏈完成；報告 `2026-05-17--cold_audit_pm_final.md` + PA validated plan `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-17--cold_audit_validated_fix_plan.md`。未把 10 個 rejected/downgraded/unproven raw findings 寫入 TODO。審計期間多次觀察到並行 source/runtime drift；PM final-final recheck 已對齊 Mac/origin/Linux `3004edb4`。任何修復派工前仍必重新 freeze。
**日期**：2026-05-29
**HEAD**：v80 cold audit TODO/report doc sync pending；pre-sync Mac/origin/Linux recheck = `3004edb4`；engine binary 未 rebuild/restart。
**Session (v75)**：parallel session — runbook v1.0 4-patch + 14d soak D+1（保留）。
**Session (v76)**：本 session 上半 — Wave 5 Packet C SOURCE LAND + 三端同步 + Linux rebuild + A 級 ssh sweep + operator menu [1]-[5]（保留）。
**Session (v77)**：本 session 下半 — Sprint 2 grill-me + PA cross-verify 5 lock decision + hybrid 方案 C ratified（保留）。
**Session (v78)**：本 session 末段 — **Sprint 2 Wave 1 dispatch 4 agent 並行完成 + drift discovery cascade**：
  - **PA A M11 schedule** ✅ — 推薦 **Daily 04:00 UTC** (Stage A single-manifest smoke heartbeat 模式)；`[48]` healthcheck cron 首次 fire ≤24h 即綠。
  - **PA B Tournament Activation Protocol** ✅ — spec land + 預估激活時點 Sprint 4-5 (~2026-08-09)；1 mid-strong push back acknowledged (N=5/M=15 無 empirical anchor → 凍結期 fallback Stage 0R direct path + Sprint 4 reassessment Q)；operator 維持 N=5/M=15 拍板不需重議。
  - **PA C Packet C dispatcher design** ✅ — 5 commit 切片 + 44-58 sub-agent hr + 10 條 operator 必答決策（Slack workspace / Email backend / Audit V114 / Banner ack / Watcher 結構…）+ PA C 自己 push back operator Q5 拍板「完整 wire」建議改 hybrid C1+C2+C3 進 Sprint 2 + C4+C5 拉 Sprint 3 (降 scope creep 22%→10%)。
  - **E1 W2-B IMPL** ✅ **NO-OP closure** — disk + git history 證明 W2-B 已於 2026-05-25 `817de10a` IMPL DONE + E2 R2/R3 APPROVE (`aeb8a84b`+`a605af57`) + E4 regression PASS (`fa466361`+`9a82c6d3`)。E1 sub-agent 對 PA report stale + TODO Phase Banner stale 做 NO-OP closure 不重做。
  - **4 層 drift discovery**：(1) v76 menu「+ 2FA」描述錯（[2] /auth/renew 既有 design 無 2FA）；(2) Q4 grid+ma vs A1/A2 → hybrid C；(3) W2-B 早於 3 天 land 但 v77 + PA report 都認 pending；(4) PM ssh sanity 用 keyword `demo|accumul|02:30` 漏 cron 名 `ac19_alt_bucket_daily_cron`（實際 5/26-5/28 已 fire 3 天）。
  - **Sprint 2 真實狀態 post-correction**：✅ W1-A spec / W2-A pre-spec / W2-B Rust IMPL / W2-E E2 R2+R3 / W2-E4 regression / M4 W1-C-R3 draft_writer fix / AC-19 ALT bucket daily cron (08:00 UTC 3 days fire) 全 land；殘留：(a) M11 cron install (Daily 04:00 UTC) (b) Packet C 10 operator Qs + scope decision (Q5 路線 2 vs PA C hybrid) (c) Stage 0R 6 sanity check 跑 (d) AC-S2-A-3 ≥1 candidate evidence (14d 累積等等 ~D+14) (e) W3-C TW + PM sign-off。
**下一步**：commit v78 + push + Linux pull 三端同步；present operator with M11 cron install + 10 Packet C Qs + scope decision menu。
**v65 archive**：`docs/archive/2026-05-26--todo_v65_archive.md`（待 archive；含 5 Strategy Stage roster / 5.1.1 H 級 ticket / W-AUDIT-4b retained / archive index 沿用）

---

## §-2 命名消歧義（v65 沿用）

本檔出現的「Sprint 2」一詞有 3 個含義：

| 名稱 | 真實內容 | 狀態 |
|---|---|---|
| **Sprint 1B Sub-IMPL: M3 emitter pre-readiness** | 4 並行 Track — PA D1/D2/D3 整合 + V103 land + E3-MED-2 ALTER OWNER | ✅ DONE 2026-05-22 |
| **Sprint 1B Sub-IMPL: M3 metric emitter scaffold** | 6 Track Wave 1+2 health domain emitter scaffold | ✅ PASS WITH 5 CARRY-OVER 2026-05-22 |
| **v5.8 §4 業務 Sprint 2（Alpha Tournament）** | Alpha Tournament + M4 stage 1 + M10 Tier A + M8 read-only — per v5.8 §4 + SSOT `docs/execution_plan/2026-05-26--alpha_tournament_ssot_spec.md` | 🟡 **SSOT SPEC-FINAL / IMPL NOT STARTED** |

判讀規則：「Sprint 2 pre-readiness / M3 emitter / Wave 1/2」= 支撐 sprint（DONE）；「業務 Sprint 2 / Alpha Tournament / W12-15」= v5.8 §4 業務 sprint。

---

## §0 三端同步 + Runtime 健康儀表

**三端 sync**：v73 code/docs target = Mac / origin/main / Linux trade-core branch tip after PM final push+pull；previous runtime HEAD `a07a08c0`。PG runtime extra: pg_dump cron installed + first dump PASS at 2026-05-28 13:15 UTC.

**Runtime snapshot**（2026-05-28 13:15 UTC SSH verify）：
- ✅ **Engine/API/watchdog alive** — API-only deploy via `bash helper_scripts/restart_all.sh --api-only --keep-auth`；uvicorn PID 2003183；`/api/v1/healthz` HTTP 200；`systemctl --user is-active openclaw-watchdog.service` = active；`engine_watchdog.py --status` demo alive (`snapshot_age_seconds≈28` at verify)。
- ⚠️ **system-level service caveat** — sudo password required，`openclaw-engine.service` / system watchdog unit 尚未安裝到 `/etc/systemd/system`；目前保護 = user-level `openclaw-watchdog.service` enabled + linger yes + manual engine process。system-level install 仍屬 operator hand-action。
- ✅ **Migration/register drift clean** — `repair_migration_checksum --verify` 2026-05-28 11:34 UTC：`parsed_files=105 / db_rows=105 / drift_count=0`；V099/V100/V109/V113 row 均存在且 checksum 對齊。
- ✅ **Wave 5 V099 physical state** — `system.autonomy_level_config` seed `CONSERVATIVE / system_default / cold_start_default_conservative`；`system.autonomy_level_switch_audit` 18 columns；ENUM values `CONSERVATIVE, STANDARD`；24h cooldown query uses `idx_autonomy_audit_switched_at_utc` Index Only Scan。
- ✅ **Wave 5 Packet B route/UI load + TOTP source backend** — `GET /api/v1/governance/autonomy-level/state` unauth HTTP 401（route registered + auth enforced）；`autonomy-posture.js` deployed behind GUI auth boundary；TOTP verifier source + tests land；runtime secret file `/home/ncyu/BybitOpenClaw/secrets/vault/autonomy_totp.json` currently missing, so switch remains fail-closed and Level 2 remains P0-EDGE evidence-gated。
- ✅ **OPS `[80]` pg_dump freshness fixed** — manual wrapper run 2026-05-28：`/home/ncyu/pg_backups/trading_ai_2026-05-28.dump` 4.6G / md5 `aaca62b0b45262038213f2357383bc97` / governance audit insert；Python freshness 7/7 PASS + `verify_pg_dump.sh` 5/5 PASS；03:00 UTC daily cron installed。
- ✅ **OPS-1 shadow cutover check** — `helper_scripts/canary/healthchecks/csrf_shadow_zero_verify.sh` on `/tmp/openclaw` 近 7d：`verdict=PASS scanned_logs=15 csrf_shadow=0`。
- ⚠️ **Passive healthcheck not green** — 2026-05-28 13:45 UTC ssh trade-core `bash srv/helper_scripts/db/passive_wait_healthcheck.sh --quiet` exit 1：FAIL `[48] replay_manifest_registry_growth`, `[74] close_maker_reject_samples`, `[56] live_pipeline_active` (`authorization_json_missing`)；`[80] pg_dump_freshness` direct checker PASS。Ssh 真因分流（2026-05-28）：
  - `[48]` = `replay.experiments` total=23 last_age=407h（last row 2026-05-11）；`replay_runner` binary 已 build 但 0 cron + 0 systemd schedule = M11 Track C runtime wire 缺，非 schema drift；autonomous spawn 越界（4hr+ 持續寫 PG）→ Operator decision + Track C wire ticket。
  - `[74]` = demo 7d `close_maker_attempt=TRUE` 17 rows fallback_reason 分布：`postonly_reject` ×3 / `timeout_taker` ×10 / NULL ×4；**0 row** matches `rate_limit_*` 或 `EC_ReachMaxPendingOrders` = `max_pending_samples=0` 結構性無法被 demo 流量觸發；gate 軟化（加 NEUTRAL_LOW_SAMPLE 流量門檻）屬治理改動 agent 不自作主張 → 入 evidence queue 等 pilot 放量。
  - `[56]` = Operator-only signed `/auth/renew` flow，不可手寫 `authorization.json`；agent 不動。
  - 三條皆不反轉 OPS-1 closure。

**Cron schedule**：pg_dump daily `0 3 * * *` UTC installed 2026-05-28；remaining operator/runtime hand-actions = first qualifying restore drill + system-level units + live-auth renewal + replay/close-maker evidence；3 defer（passive_wait_healthcheck / ref21_market_microstructure_recorder / blocked_symbols_30d_unblock）。

---

## §1 Top-Priority Active Blockers（P0 only）

| ID | 狀態 | Owner | AC | Next Action |
|---|---|---|---|---|
| **P0-ENGINE-DEAD-2026-05-27** | ✅ **CLOSED 2026-05-28 runtime recovered** — engine/API/user watchdog alive；healthz 200；watchdog enabled user-level + linger yes | operator + E1 | AC met for immediate P0 unblock：engine PID + API PID + watchdog PID present；watchdog status `engine_alive=true`；healthz 200 | Residual: system-level unit install still needs sudo/operator password；root cause RCA not complete，but no longer blocks migration/register repair or OPS-1/Wave5 handoff |
| **P0-EDGE-1** | 🔴 ACTIVE（SSH empirical 2026-05-26 22:00 UTC: 0/3 AC paths satisfied；2026-05-26 cohort reframed 5→4 textbook per AMD-2026-05-26-01）| QC + PA | (i) **4 textbook** ≥3 demo 7d avg_net>5bps + Wilson lower>0 + n≥30（funding_arb retired per AMD-2026-05-26-01）；**OR** (ii) ≥3 alpha-bearing 達同標；**OR** (iii) portfolio 7d gross 正向 | 唯一可預期 closure path = (ii) Sprint 2 Alpha Tournament W12-15 dispatch；當前 (i) **4/4 textbook** `insufficient_total_samples`（funding_arb 樣本不再累積：deprecated；ma_crossover / bb_breakout / bb_reversion / grid_trading runtime_bps −11~−42）；(iii) live_demo 7d net=-1.99 USDT |
| **P0-LG-3** | ⚠️ PA verify ✅ + MIT V104 dry-run ✅ 9/9 PASS + 2 bonus / **IMPL DISPATCH gate (2) UNBLOCKED 2026-05-27** / gate (1) v56 P0 Layer B + 24h ~2026-05-30 待 | PA ✅ → MIT V104 dry-run ✅ → E1×N IMPL (gated) | **AMENDED 2026-05-26 / MIT dry-run 2026-05-27**：spec v2 V094→V104 1:1；2026-05-27 MIT BEGIN/ROLLBACK in trading_ai PG empirical PASS：21 col / 4 CHECK / hypertable 7day / compression 30d / retention 90d / V104 hole FREE confirmed / Guard A part 3 forbidden col 0 hit / 4 boundary INSERT check_violation rejected / 2nd apply NOTICE-skip 一致 V083/V084 gold；real dispatch precondition = (1) V104 spec scaffold ship ✅ (2) v56 P0 Layer B + 24h ⏳ ~2026-05-30 (3) MIT 4-step dry-run 9/9 PASS ✅ (4) Option B race-aware dispatch；§15 #1 FALSE dep reframed | LG-3 Wave 2.4.A earliest ~2026-05-30 UTC；ref V104 spec + verify report `2026-05-27--p0_lg3_spec_verify_and_todo_patch.md` + MIT dry-run `srv/docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-27--v104_supervised_live_audit_dry_run.md` |
| **P0-OPS-1..4** | 🟢 **OPS-1 CLOSED / OPS residual OP-gated** — OPS-1 enforcing-ready gaps closed commit `22466a81`; OPS-4 pg_dump runtime freshness now PASS but passive healthcheck not all green | E1+MIT+PA → E2+A3+E4+QA 全鏈 GREEN | OPS-1 A3 R2/R3/R4 close：CSRF 403 中文 toast + auto reload；cert trust runbook + install hint；CSRF/CSP shadow 14d→7d + `csrf_shadow_zero_verify.sh` PASS 0。Migration drift clean；engine/API/watchdog alive；pg_dump cron installed + first dump PASS。 | Remaining: system-level unit install (sudo), first restore drill, OPS-2 D+14 cutover/soak, `authorization_json_missing` live-auth renewal, replay_manifest registry feed, close-maker max-pending evidence. Not current coding blocker, but blocks “OPS all green”. |
| **P0-FUNDING-ARB-DECISION-FORCE** | ✅ **CLOSED 2026-05-26**（operator decision = D） | operator + PA | operator chose (D) 3C TOML deprecation closure | **Cascade WORKFLOW F NEW**：PA deprecation spec + TW docs/README/AMD cascade + R4 cross-ref；ref §9 NEW row + §6 P1 entry |

---

## §2 Active Sprint Phase Banner

```
Sprint 1A-α     DESIGN-DONE / IMPL-PENDING (W0-1.5, 2026-05-21 PM-signed)              v5.7 12 prefix + PM signoff
Sprint 1A-修補  DESIGN-DONE / IMPL-PENDING (D+0~D+5, 2026-05-21)                       v5.8 16 CR + Wave 2.5 paperwork
Sprint 1A-β     DESIGN-DONE / IMPL-PENDING (2026-05-21 PM-signed)                      M1 LAL/M3/M6/M7/M11 + V106/V107/V110/V112/V113 spec + 6 runbook
Sprint 1A-γ     DESIGN-DONE / IMPL-PENDING (2026-05-21 PM-signed)                      M2/M4/M8/M9/M10 + V105/V108/V109/V111 + V103 EXTEND + 3 ADR
Sprint 1A-δ     DESIGN-DONE / TRAIT-STUB-IMPL ✅ FEATURE-LIVE (2026-05-21+ 25)         M5/M12/M13 trait stub (277/393/151+test 495 LOC) + 25 cargo test PASS
Sprint 1A-ε     DESIGN-DONE / IMPL-PENDING (2026-05-21 PM-signed)                      R4 cross-ADR 5C+4H + TW CHANGELOG/CONTEXT + MIT V099-V116 + E5 Mac CI + A3 Wizard
Sprint 1A-ζ     ✅ MAC-SOURCE-DONE + PG-LIVE / LAL+REPLAY-RUNTIME-NOT-PROVEN (2026-05-22)
Sprint 1A-ε P1+P2  ✅ DONE (2026-05-22)                                                  E3 sandbox_admin + PA 5 spec patch + N1/N2/N3
Sprint 1B early IMPL  ✅ SOURCE-CLOSED + FEATURE-LIVE / PARTIAL (2026-05-22+25)         C10 PnL + IntentType + Earn IntentProcessor source-land
Sub-IMPL M3 pre-readiness  ✅ DONE (2026-05-22)                                          4 並行 Track + M3 dispatch gate OPEN
Sub-IMPL M3 metric emitter scaffold  ✅ PASS WITH 5 CARRY (2026-05-22 PM Phase 3e)      6 Track + 8 AC + 51/51 integration
Sprint 4+ §4.1 + Stage A-F + Sprint 5+ Wave 1  ✅ ALL CLOSED (2026-05-23 PM-signed)      Wave A/B + V100/V101/V102 + B-2/B-3 + Stage E Linux deploy
業務 Sprint 2 (Alpha Tournament)  🟡 SSOT SPEC-FINAL / IMPL NOT STARTED (W12-15 計畫)    Stream A funding short>30% + LCS fade + DRAFT BTC/ETH pairs
Layered Autonomy v2 Wave 5  🟡 Packet A+B runtime + TOTP source + ADR sync / Packet C core E4 green        V099 physical apply+register done；API+GUI posture deployed；TOTP runtime enrollment + Packet C engine integration still pending
```

**狀態語言**：
- DESIGN-DONE = spec/ADR/runbook/schema spec 文件 land 通過 PM signoff
- IMPL-PENDING = 對應 Rust/Python/SQL 實作未開始
- RUNTIME-NOT-APPLIED = no longer true for V099/V109/V113 as of 2026-05-28；trading_ai 主 PG `_sqlx_migrations` max=113 / count=105 / drift_count=0。Future V104/Sprint2 migrations still require normal Linux PG empirical dry-run + sqlx register discipline.

---

## §3 In-Flight Workflow（≤7 並行；含 sub-agent chain）

7 active workflow 對應 PM cluster 分組（per PM §3）：

| ID | Workflow | Owner chain (T1-T5 template) | 估時 | Cluster | Blocked-on |
|---|---|---|---|---|---|
| ~~**A**~~ | ~~22 fail-closed 1e-3 invariant Option (c) AMD-09-03 附錄~~ | – | ✅ **PA + FA + TW + QC + R4 ALL DONE 2026-05-27** | – | PA design + FA CONDITIONAL APPROVE + TW §9 附錄 +143 LOC (C1-C6) + QC math PASS + [81] SQL 155 LOC + R4 APPROVE-WITH-MINOR-CASCADE-GAP (7/7 internal PASS / 2 D+1 docs/README+SPEC_REG cascade gap)；C7 cluster center + R4 2 gap defer D+1；pending = E4 regression + operator sign-off |
| **B** | ADR-0046 basis observation/execution split | T1: PA design → E1 Rust → MIT V117 → E2 → E4 → BB → QA | 24-30 hr | 2 (Phase 1→2→3) | PA design first |
| ~~**D**~~ | ~~AMD-2026-05-25-01 商業化邊界 cascade~~ | – | ✅ **CLOSED 2026-05-27** | – | PA Workflow D cascade 完成 6 files (AMD Status Active + docs/README + SPECIFICATION_REGISTER + AMD-20-04/05 superseded callout + TODO §9 closed)；report `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-27--workflow_d_amd_25_01_cascade.md` |
| ~~**E**~~ | ~~AMD-2026-05-25-02 v5.5 reframe cascade~~ | – | ✅ **CLOSED 2026-05-27** | – | PA Workflow E cascade 完成；report `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-27--workflow_e_amd_25_02_cascade.md` |
| ~~**F**~~ | ~~funding_arb (D) 3C TOML deprecation cascade~~ | – | ✅ **FULLY CLOSED 2026-05-26** | – | Phase 1 PA spec ✅ + Phase 2 TW (AMD-26-01 + 5 primary + 19 secondary) ✅ + R4 Pass A APPROVE-WITH-DRIFT ✅ + R4 Pass B APPROVE ✅；3 LOW carry-over defer D+7 |
| **Earn Wave C** | OP-1 series → first stake $100-200 Flexible-only | T1: 7 hand OP + 5 可代做 post-1..5 | OP 30min + post-flow 30min | 3 (operator-gated) | OP-1 a-f hand actions |
| **Layered Autonomy v2 Wave 5** | V099 + GUI + Rust SM-04 + 5 ADR sync + R4 | T1+T2 (Packet A runtime ✅; Packet B API+GUI ✅; TOTP source ✅; Packet C core E4 ✅ / engine integration pending) | 81-126 hr | partial | ✅ **Packet A V099 physical apply/register DONE 2026-05-28**：V99 row + checksum `7b6e...aeff7`；`current_level=CONSERVATIVE` seed；`repair_migration_checksum --verify drift_count=0`。✅ **Packet B API+GUI posture deployed** commit `a07a08c0`。✅ **TOTP source backend**：file-backed fail-closed verifier + route evidence gate guard + 10 pytest PASS；runtime secret missing → not Level2-enabled。✅ **Packet C source E2/E4**：`risk_gov` 27/27 PASS + `openclaw_engine --lib` 3468/3468 PASS (1 ignored)。✅ **5 ADR/R4 sync**：ADR-0034/0040/0042/0044/0045 + R4 report. Pending = Packet C engine notification timeout / exchange conditional SL sync / audit emit integration + runtime TOTP enrollment. |
| **Sprint 2 業務 Alpha Tournament** | A1 funding short>30% + A2 LCS fade + A3 BTC/ETH pairs DRAFT | T1+T5: PA spec → E1 Rust×3 → MIT V108/V109/V111 → E2 → E4 → QC → BB → QA | 248-351 hr / 3w wall-clock | 4 (Sprint 2 dispatch) | Sprint 1A-γ V111 land |

**Sub-agent dispatch hygiene SOP**（per memory `feedback_fetch_before_dispatch` + 2026-05-25 cargo test-after-atomic 教訓）：
- 每次 dispatch 前強制 `git fetch` + `git branch -r | grep <topic>`
- Linux cargo test 後必走 `bash helper_scripts/build_then_restart_atomic.sh` OR 標 carry-over
- Meta-doc 改動用 `git commit --only <files>` 隔絕 multi-session race

---

## §4 Module DESIGN/IMPL Matrix（M1-M13 per PA technical roadmap）

| M# | 名稱 | State | LOC (R+P+SQL) | 估時 (hr) | IMPL phase |
|---|---|---|---:|---:|---|
| **M1** | Decision Lease LAL 4 Tier | DESIGN-DONE / Track A spike runtime feature-live but **`LAL_0_AUTO=0` 未證 runtime grant** | 1800/400/350 | 130-180（80 done） | β ✅ / Sprint 4 Tier 1 / Sprint 7-8 Tier 2 / Y2 active |
| **M2** | Overlay enable SM | DESIGN-DONE / IMPL-PENDING | 800-1100/200/250 | 90-130 | γ ✅ / Sprint 3 hook / Y2 Q1 auto-enable |
| **M3** | Health monitoring + auto-degradation | DESIGN-DONE / **Sub-IMPL emitter scaffold ✅ PASS 5 CARRY** / 6 domain × 30min × 1836 row empirical PASS | 3200/600/400 | 140-200（emitter 30-40 done） | β ✅ / 1B emitter ✅ / Sprint 5 auto-degradation / Sprint 7 recovery |
| **M4** | Self-supervised hypothesis discovery | DESIGN-DONE / **V100 base table ✅ land 663 SQL+581 spec** / pattern miner IMPL-PENDING | 1500-2000/600/700 | 170-240（V100 ✅ done） | γ ✅ / **Sprint 6+ Pattern Miner active per ADR-0045** / Sprint 8 stage 2 / Y2 Q2-Q3 full loop |
| **M5** | Online learning interface | DESIGN-DONE / **trait stub ✅ 277 LOC + 100 test** | 277/0/frontmatter | 8-12 done / Y3+ 200-400 | δ stub ✅ / Y3+ AUM>$50k 啟動 |
| **M6** | Bayesian reward weight | DESIGN-DONE / IMPL-PENDING | 900-1200/400/200 | 130-190 | β ✅ / Sprint 7 Advisory / Y2 Auto |
| **M7** | Strategy decay + auto-retirement | DESIGN-DONE / IMPL-PENDING / **single decay authority per CR-7** | 1200-1500/300/350 | 130-180 | β ✅ / Sprint 8 IMPL / Sprint 10 auto-demote via M1 Tier 1 |
| **M8** | Anomaly detection | DESIGN-DONE / IMPL-PENDING | 1300-1700/500/400 | 210-310 | γ ✅ / Sprint 3 read-only / Y1 H2 alerting / Y2 ML |
| **M9** | A/B testing framework | DESIGN-DONE / IMPL-PENDING | 1200-1600/600/500 | 200-280 | γ ✅ / Sprint 4 read-only / Sprint 7-8 manual / Y2 auto |
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

## §6 P1 Active Engineering Queue（active only；closed → §-1 archive）

| ID | 優先 | 任務 | AC / Next Action |
|---|---:|---|---|
| `P1-OPS-1-E1-DISPATCH` | – | ✅ **IMPL DONE 2026-05-27 commit `65e78437`** round 1；ref `docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-27--ops_1_https_secure_cookie_impl.md` |
| `P1-OPS-1-E1-ROUND-2` | – | ✅ **CLOSED 2026-05-28 commit `22466a81` supersedes `07027493` enforcing gaps** — original round 2 8 fix + A3 R2/R3/R4 close：CSRF 403 friendly toast + auto reload, cert trust runbook + install hint, CSRF/CSP shadow 7d + `csrf_shadow_zero_verify.sh` PASS 0；target tests 34/34 PASS；Linux runtime repo pulled |
| `P1-OPS-1-PROXY-HEADER-SPOOF-RISK` | – | ✅ **CLOSED 2026-05-27 by E2 verify PASS** — `auth_routes_common.py:60-94` `_proxy_headers_trusted()` env gate fail-closed verified；偽造 X-Forwarded-Proto 無效；regression batch B 10/10 PASS |
| `P1-OPS-2-SECRET-SPLIT` | – | ✅ **IMPL DONE 2026-05-27 commit `65e78437`** Phase 1 — E1 477 LOC (Rust 371 + Python 74 + Bash 32) + 24/24 cargo + 8/8 pytest + 10/10 batch B + cross-lang HMAC `1b2b18d7...` byte-identical 三端 + 5 PA hidden risk mitigation；E2 APPROVE-CONDITIONAL 0 BLOCKER/HIGH；A3 8.0/10；CC 16/16 + 9/9 + 4/4 hard gate；Mainnet env-var fallback closed 紀律 reconcile PASS (signing-key 域 ≠ Bybit credential)；ref `docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-27--ops_2_secret_split_impl.md` + E2 + A3 + CC reports |
| `P1-OPS-2-PHASE-2-CUTOVER` | 1 | **NEW 2026-05-27 per CC C-1 P0 hard gate** — D+14 (2026-06-10) Phase 2 PR：移 fallback + main.rs:402 後第二 panic block + Python reason `ipc_secret_missing` → `live_auth_signing_key_missing` + `AuthError::IpcSecretMissing` 變體刪除；Phase 2 不 land = hardcoded fallback 永久化違規；Owner: E1 + CC + BB；trigger: D+14 + 14d soak 0 WARN log；2-4 hr |
| `P1-OPS-2-14D-SOAK-OBSERVE` | 1 | **NEW 2026-05-27 per CC C-2/C-3** — 14d soak D+0 2026-05-27 → D+14 2026-06-10：(a) 每日 `ssh trade-core grep -c ops2_secret_split_phase1_fallback /tmp/openclaw/{engine,api}.log` 累計 = 0 (b) 至少 1 次 `/api/v1/live/auth/renew` 重簽；任一 fail = Phase 2 BLOCK |
| `P1-OPS-2-RUNBOOK` | – | ✅ **CLOSED 2026-05-27 PA draft v0.9** — `docs/runbooks/credential_rotation.md` 495 行 / 12 章 / 3 primary + 6 auxiliary / Emergency RTO ≤5-7min / 4 audit SQL；ref `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-27--ops_2_runbook_draft.md` |
| `P1-OPS-2-RUNBOOK-V1.0-PATCH` | – | ✅ **CLOSED 2026-05-28** — PA delivered 4-patch v1.0：(1) §4.2.1 quote box Phase 1 backward-compat note（restart_all seed-from-ipc 不違反 urandom；首次 90d rotation 後必獨立 from urandom）(2) §10.1.1 sub-section `grep -c ops2_secret_split_phase1_fallback /tmp/openclaw/{engine,api}.log = 0` invariant + AC table (3) §10.5 cross-lang HMAC sanity check（pinned hex `1b2b18d7...8b78fc` + Python stdlib one-liner + Rust `cross_lang_hmac_fixture_is_byte_identical` test）(4) §13 6-sub Phase 2 cutover SOP（preconditions + Grafana 新字串 + PR dispatch + panic verify + rollback + D+44 sign-off）；495→687 行（+192）；§11 Revision History v1.0 row land；§12 Cross-References +6 refs；ref `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-28--ops_2_runbook_v1_0_patch.md` + 3 P2 carry-over rows below |
| `P1-OPS-2-CI-FLAKINESS-TEST-LOCK` | 3 | **NEW 2026-05-27 per E2 MEDIUM-1** — `live_authorization::tests::ENV_TEST_LOCK` vs `live_auth_watcher_tests::ENV_GUARD` 兩獨立 mutex；cargo test --lib 並行下 env-var race；24/24 PASS 實測未觸但 latent；合併至 crate-level shared mutex 或 serial_test crate；defer follow-up 非 prod risk |
| `P1-OPS-2-RESTART-ALL-CP-ATOMIC` | 3 | **NEW 2026-05-27 per E2 MEDIUM-2** — `restart_all.sh:159` `cp ipc_secret.txt live_auth_signing_key.txt` 非 atomic；SIGTERM 中斷可能 partial-written；改 `cp ... tmp && mv tmp final`；首 boot 場景概率低 fail-closed 路徑安全；defer follow-up 非 prod risk |
| `P1-OPS-2-DRY-RUN` | 1 | **NEW 2026-05-26 per E3-LOW-2** — OP-1 a-f path 45+ 天未動 = SOP 從未 end-to-end exercised；用 OP-1 當 OPS-2 SOP first dry-run 收 timing + fail-modes → runbook v1.1；Owner: Operator + PM；trigger: OP-1 unblock D+2-D+3 |
| `P1-OPS-3-OPERATOR-CONFIRM-5` | – | ✅ **CLOSED 2026-05-26 sequential confirmation** — C-1 Spain (EU member, MiCA-compliant, NOT in 16 restricted) ✅ / C-2 ≥ Advanced L2 (Gov ID + face + utility bill, 2M USDT/day) ✅ / C-3 2 demo keys + 33d TTL ⚠ pending OP-1 a-f mainnet reissue (unblocks Sprint 4 + Earn) / C-4 defer Spanish tax planning to first Live + 30d (~2026-10) / C-5 accept Earn risks, first stake $100-200 USDT Flexible only ✅；signoff doc `srv/docs/governance_dev/2026-05-26--bybit_compliance_signoff.md`；ref `srv/docs/CCAgentWorkSpace/BB/workspace/reports/2026-05-26--p0-ops-3-bybit-tos-geo-kyc-audit.md` |
| `P1-OPS-4-GAP-A-WATCHDOG-SYSTEMD` | – | ✅ **IMPL DONE 2026-05-27 commit `65e78437`** — `helper_scripts/systemd/openclaw-watchdog.service` (Restart=always + StartLimitBurst=10/600s) + install_watchdog_service.sh；E2 APPROVE-WITH-MINOR；RTO ≤5min 數學成立 |
| `P1-OPS-4-GAP-F-ENGINE-SYSTEMD` | – | ✅ **IMPL DONE 2026-05-27 commit `65e78437`** — `helper_scripts/systemd/openclaw-engine.service` (Restart=on-failure + RestartSec=10 + StartLimitBurst=5/300s) + install_engine_service.sh；E2 APPROVE-WITH-MINOR；ref `docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-27--ops_4_gap_a_f_systemd_impl.md` |
| `P1-OPS-4-GAP-A-F-MINOR-FIX` | – | ✅ **CLOSED 2026-05-27 commit `07027493`** — 4 fix in-place: Requires=空值刪除 + verify warn/error 區分 + root user guard exit 12 + README reset-failed 提示；bash -n PASS；ref `docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-27--ops_4_minor_e1_in_place_fix.md` |
| `P1-OPS-4-GAP-B-PG-RESTORE-DRILL` | – | ✅ **IMPL DONE 2026-05-27** chain round 1+2+3 — MIT 3/3 deliverable: `srv/helper_scripts/db/post_restore_validation.sql` (330 LOC / 9 query / Q3 fix `created_at` 2 處 / 8/9 PASS Linux SSH empirical) + `srv/docs/runbooks/pg_restore_drill_sop.md` (572 LOC / 10 章 mirror replay_signing_key_rotation.md / 7 scenario estimates median 14h worst 22.5h) + `srv/docs/CCAgentWorkSpace/MIT/workspace/templates/pg_restore_drill_report_template.md` (239 LOC / 12 章) + cite existing `srv/rust/openclaw_engine/src/bin/repair_migration_checksum.rs` for sqlx repair；4/9 invariant re-verify mandatory I1/I2/I7/I8 |
| `P1-OPS-4-GAP-D-PG-DUMP-CRON` | – | ✅ **IMPL DONE 2026-05-27** chain round 1+2+3 — E1 6/6 deliverable: `helper_scripts/cron/install_pg_dump_cron.sh` (132 LOC w/ MED-3 `_validate_cron_env_value` + regex `[[:space:]%[:cntrl:]\"\'\\\$\`]` + length>200 exit 6) + `trading_ai_pg_dump_cron.sh` (181 LOC EXCLUDE evaluations + governance_audit_log INSERT 2/4 event_type per PA mini-patch §10.B.1 + retention 30d) + `verify_pg_dump.sh` (129 LOC Bash sidecar) + `sql/migrations/V113__governance_audit_log_pg_dump_event_types.sql` (V053/V098 race-free + Guard A/B) + `helper_scripts/canary/healthchecks/check_pg_dump_freshness.py` (662 LOC w/ MED-1 `_platform_guard()` + MED-2 heartbeat cross-check WARN escalation) + `helper_scripts/db/passive_wait_healthcheck/{__init__.py,checks_cron_heartbeat.py,runner.py}` wire；E2 r1+r2 + E4 r1+r2 + QA E2E 全 GREEN |
| `P0-OPS-4-GAP-B-D-OPERATOR-DEPLOY` | 1 | **PARTIAL DONE 2026-05-28** — (1) engine/watchdog runtime recovered ✅ (2) `repair_migration_checksum --verify` drift_count=0 ✅ after V109/V113 register repair + V099 apply/register (3) pg_dump wrapper manual run ✅ 4.6G + md5/audit/TOC PASS (4) pg_dump cron apply ✅ daily 03:00 UTC installed (5) `[80] pg_dump_freshness` direct 7/7 PASS ✅；remaining hand-actions: first qualifying restore drill ~4 hr per MIT SOP scenario S1 + BB Earn cross-sign §11；passive healthcheck still fails `[48]/[74]/[56]` for replay/close-maker/live-auth reasons outside pg_dump freshness. **Drill prereq sweep 2026-05-28 15:53 UTC ssh**: dump `trading_ai_2026-05-28.dump 4.6G` (3h old) ✅；disk `/dev/nvme0n1p8 835G free` ≫ 60G SOP threshold ✅；PG 16.11 reachable ✅；SOP + post_restore_validation.sql + drill report template 3/3 present ✅；`repair_migration_checksum` release binary present ✅；**`.pgpass` 通配 ENTRY 已加 2026-05-28 17:33 UTC per operator decision [3]**：`*:5432:trading_ai_drill_*:trading_admin:<passwd>` + `*:5432:trading_ai_restore_*` + `*:5432:*:trading_admin:<passwd>`（chmod 600；測試 `psql -d trading_ai_drill_$(date -u +%Y%m%d)` 命中 pgpass FATAL = "database does not exist" 確認密碼已送）；**Operator timing call**：4hr 跑時段共用 PG cluster 與 live engine，agent 不自啟避免性能干擾 → 等 Operator 排 low-trading window。 |
| `P3-OPS-4-PG-DUMP-EVENT-EXTEND` | 4 | **NEW 2026-05-27 per PA mini-patch §10.C** — `pg_dump_retention_dropped` + `pg_dump_md5_drift` 2 future event_types；triggered if dump operationally need finer audit；non-blocker first-day live |
| `P2-OPS-4-GAP-B-D-UNIT-TEST-GAP` | 3 | **NEW 2026-05-27 per E4 CARRY-OVER-2** — 743 LOC production code (3 cron + Python healthcheck + passive_wait wire) 0 unit test；governance gap；P1 backlog post first-day live |
| `P1-WAVE5-TOTP-BACKEND` | 1 | 🟦 **DEFERRED per operator decision [1] 2026-05-28 — 等系統完整正式上線再做** — Operator 拍板「2FA 不是當前重點，等系統完整正式上線再 enroll」。`autonomy_totp.py` source + 10/10 pytest 已 land；vault dir 已 prep（drwx------ ncyu ncyu）；runtime fail-closed by design 不阻 Conservative level 運作。**作用範圍澄清**：TOTP backend 只服務 **Autonomy Level 2 (Standard) 切換**，與 `/auth/renew` live engine 啟用無關（[2] 已確認 renew flow 無 2FA gate）。enrollment 重啟時機 = Sprint 2 Alpha Tournament + Level 2 promotion gate 開啟前。one-liner prep（保留供未來使用）：(1) authenticator app 產 base32 seed `SEED_B32`；(2) `python3 -c "import hashlib; print(hashlib.sha256(b'${SEED_B32}').hexdigest())"` → `FINGERPRINT`；(3) `umask 077 && cat >~/BybitOpenClaw/secrets/vault/autonomy_totp.json <<EOF\\n{"totp_seed_b32":"${SEED_B32}","fingerprint":"${FINGERPRINT}","totp_algorithm":"SHA1","totp_digits":6,"totp_interval_sec":30}\\nEOF`；(4) smoke `cd .../control_api_v1 && .venv/bin/python3 -c "from app.autonomy_totp import autonomy_totp_backend_configured; print(autonomy_totp_backend_configured())"` 必回 `True`；(5) restart_all。 |
| `P1-WAVE5-PACKET-C-E2-E4-INTEGRATION` | 1 | 🟡 **ENGINE INTEGRATION SOURCE LAND + LINUX REBUILD DONE / pipeline_ctor wire PENDING 2026-05-28** — commit `920f8299` lands `openclaw_engine::notification_failsafe` module (1099 LOC inc 14 mock tests + 5 trait seam: NotificationDispatcher / PositionSnapshotProvider / ExchangeStopSync / FailsafeAuditEmitter / FailsafeClock). 整條 chain 已接：observe AllFail → 1h timer → SM-04 `transition(Defensive, NotificationFailsafeTimeout, RiskGovernor, "auto_escalated_to_sm04_defensive")` → `active_lock_profit_per_position` → `ExchangeStopSync::sync_stop` per adj → `FailsafeAuditEmitter::emit_auto_escalated`. `DEFAULT_TIMEOUT_MS=3_600_000` compile-time hard-coded（無 TOML override 路徑，per AMD §Decision 2.5 + Q3 Path A）；`cargo test -p openclaw_engine --lib` 3482/3482 PASS = 3468 baseline + 14 new；clippy 0 hit；core 27/27 unchanged。**Linux 16:18 UTC `restart_all --rebuild --keep-auth` cargo release 37.94s + engine PID 2044407 + API 4 workers up + post-rebuild healthcheck FAIL = 同 3 條 `[48]/[74]/[56]` 零 regression**。Minimal slice 不接 pipeline_ctor / 不 spawn 長運行 task / audit 走 trait emitter（沒下一 wave 真實 3-way dispatcher 接線前 wire 進 runtime 等同假 wire，per CLAUDE.md §六 + memory feedback_no_dead_params）。 |
| `P2-M11-REPLAY-RUNNER-SCHEDULE-PROPOSAL` | 3 | ✅ **PROPOSAL DONE 2026-05-28 per PA A background agent / OPERATOR CONFIRM + E1 INSTALL PENDING** — proposal land at `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-28--m11_replay_runner_schedule_proposal.md` + Operator mirror `docs/CCAgentWorkSpace/Operator/2026-05-28--m11_replay_runner_schedule_proposal.md`。**PA A 推薦 cadence**: **Daily 04:00 UTC**（Stage A single-manifest smoke heartbeat 模式）；理由：避撞既有 03:00 pg_dump / 03:17 ml_training_maintenance / 04:41 feature_baseline_writer；對齊 ADR-0044 Decision 2「daily aggregate」；PG cost ~50 kB/day, 30d ~1.5 MB；Sprint 3 Phase A 後可無痛升 Stage B nightly cohort wrapper。**`[48]` healthcheck 變 PASS 時點**：cron 首次成功 fire 後 ≤24h 內（規則 `rows_7d ≥ 1 + rows_24h ≥ 1`）→ 首次 04:00 UTC fire 完即綠。**待**：(a) operator confirm Daily 04:00 UTC（或選 hourly/6h/on-demand 替代）；(b) E1 cron install per 既有 `helper_scripts/cron/install_pg_dump_cron.sh` pattern；ETA 1-2 day。**✅ INSTALLED + LIVE 2026-05-28**（commit `b43481f7` Daily 04:00 UTC；smoke run + `[48]` FAIL→PASS）。 |
| `P2-M11-SMOKE-ZOMBIE-DESIGN-FIX` | 2 | ✅ **DONE + DEPLOYED 2026-05-29**（修法 a register-only）— commit `d696b1f2`(wrapper) + `1f33301a`(wave9 allowlist + install echo)；三端 `1f33301a`。smoke 移除 run dispatch 保留 register（[48] 只需 `replay.experiments` growth，run 是 zombie 唯一源）。deployed wrapper dry-run 驗：`/replay/run` 3 hits 全註釋 + 0 run_state running + experiments fresh row 02:37 + [48]/[50] PASS。E2 APPROVE-WITH-CONDITIONS deploy clearance YES；2 follow-up 修畢（MEDIUM-1 wave9_audit_incident_scan allowlist 加 success alert_type 防 daily false incident，failure 變體保留 incident detection；LOW-1 install echo register_only 對齊）。首例 zombie `6532fc38` operator cleanup。**殘 follow-up（Sprint 3 Phase A OQ-2）**：加 `m11_*` event_type enum migration 停 `audit_write_failed` piggyback + PA proposal §4.2 register+run→register-only deviation 文字回簽。 |
| `P1-SPRINT2-STAGE0R-REPLAY-PREFLIGHT-DISPATCH` | 1 | **MAJOR CORRECTION v78 2026-05-28 — Sprint 2 大半已 DONE，不是 IMPL pending** — 經 E1 sub-agent NO-OP closure + git history reality check 修正：W2-B Rust IMPL 早於 2026-05-25 `817de10a` 已 land（funding_short_v2 + liquidation_cascade_fade Rust struct + TOML default `active=false` + Python harness +3737 LOC）+ W2-E E2 R2/R3 APPROVE (`aeb8a84b`+`a605af57`) + W2-E4 regression 3483/3483 PASS (`fa466361`+`9a82c6d3`) + M4 W1-C-R3 draft_writer schema fix (`b2febd43`) + AC-19 ALT bucket daily cron 5/26-5/28 fire 3 天連續成功。Sprint 2 改名 `Stage 0R Replay Preflight Sprint`（保 Tournament activation spec future use per Q2）。**Q4 hybrid 方案 C 仍有效**：主軌 A1+A2 IMPL 已 done；對照軌 grid+ma 待 Stage 0R baseline；catch-up 軌 bb_breakout+bb_reversion D+30=2026-06-27 評估。**真實殘餘工作**：(1) **M11 cron install** Daily 04:00 UTC per PA A 推薦 — operator confirm 後 E1 cron 接線 1-2 day；(2) **Packet C 10 operator Qs 拍板** + **scope decision**（Q5 路線 2 完整 wire vs PA C 推薦 hybrid C1+C2+C3 進 Sprint 2 / C4+C5 拉 Sprint 3）— operator 拍板後派 E1 IMPL；(3) **Stage 0R 6 sanity check 跑**（M11 runner 接線後）；(4) **AC-S2-A-3 ≥1 candidate evidence 累積**（14d demo accumulation 已透過 AC-19 cron 自 5/26 開跑，預估 ~D+14=2026-06-11 evidence 充分）；(5) **W3-C TW + PM sign-off** Wave 3 stage0_ready 出口。**Owner**: PM → operator decisions → E1 dispatch chain。**ETA 修正**: 原估 2.5 week / 248-351 hr → 真實殘餘 ~14 day（多為 evidence 累積等待，非 IMPL hr），E1 active hr 估 25-50 hr 含 Packet C 與 M11 cron。**Ref**: PA Sprint 2 entry checklist `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-28--sprint2_alpha_tournament_entry_checklist.md`（stale 部分已修正）+ E1 NO-OP closure report `docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-28--w2b_impl_noop_closure.md` + v78 PM sign-off。 |
| `P2-ALPHA-TOURNAMENT-ACTIVATION-SPEC` | 4 | ✅ **DONE 2026-05-28 per PA B background agent** — spec land at `docs/execution_plan/specs/2026-05-28--alpha_tournament_activation_protocol.md` (22.7K) 含 §1-§14 governance ladder：activation 觸發 N=5+M=15 / 退出機制 / 排名 metric slot 預留 / 晉級+淘汰 slot 預留 / Re-entry path / per-Sprint 觸發評估 / Sprint 2 hybrid C 映射 / **預估激活時點 Sprint 4-5 (~2026-08 至 2026-09)**。**PA B 1 mid-strong push back**：N=5/M=15 無 empirical anchor（當前 0 策略滿足 C2，閾值為直覺猜測）；mitigation 充分（§11 AMD path 開放 + 6-9 月 reassessment 窗口 + 凍結期 fallback Stage 0R direct path），operator 拍板維持 N=5/M=15 不需重議。**Reassessment trigger**：PM 在 Sprint 4 dispatch packet 內 check Q「若 A4/A5 延遲導致 Sprint 5 仍 < N=5，是否走 §11 AMD 改 N=4？」。**Workspace report**: `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-28--alpha_tournament_activation_protocol_spec.md` (4.3K)。 |
| `P3-BB-STRATEGIES-30D-CATCH-UP-CLOCK` | 4 | **NEW 2026-05-28 per Sprint 2 Q4 hybrid 方案 C (v77)** — bb_breakout (7d n=1) + bb_reversion (7d n=3) 結構性少樣本但**不立即 retire**；給 30 天 catch-up grace 期 (D+30 ~2026-06-27) 在 demo 累積樣本看是否達 M=15。**判據**：D+30 評估時若 n_settled >= 15 → 進 Stage 0R baseline 控制組（同 grid+ma 並列）；若 n_settled < 15 → 進 M7 decay_signals RETIRED + ADR-0044 deprecation cascade。**真實語意（push-back acknowledged）**：30 天對 entry 嚴策略本質上 = 半路線 Y retire + grace window（per agent push back operator 拍板 30 天 vs 推薦 60 天）；operator 拍板維持 30 天 = 接受「結構性 entry 嚴 ≠ 應特例放行」立場；M7 decay_signals 路徑保 governance 不破口。**Owner**: PM clock watch + (D+30) QC + MIT 評估；**Trigger**: 2026-06-27 cron 或手動評估。 |
| `P1-PACKET-C-3WAY-DISPATCHER-WIRE-DISPATCH` | 1 | 🟢 **C1+C2+C3 IMPL DONE + 全 review chain 綠 (v79 2026-05-28) / C4+C5 defer Sprint 3** — operator 拍 PC.B hybrid + 全 10 Qs PA defaults + EA(lettre)。**C1 dispatchers**：slack(Incoming Webhook) + email(Gmail SMTP App Password + RealSmtpTransport lettre 0.11 rustls openssl=0) + console_banner(vault file 持久化直到 ack) + three_way(NotificationDispatcher impl)。**C2**：V114 `observability.notification_failsafe_events` 17-col hypertable（GRANT-before-compression + nested EXCEPTION idempotent，MIT R3 三跑 EXIT0 deploy-ready）+ PgAuditEmitter + ack stub。**C3**：wall_clock + RestPositionProvider + BybitExchangeStopSync + SharedFailsafeWatcher(single shared, claim-before-await 並發 guard)。**Review 全綠**：E2 full Rust APPROVE-WITH-CONDITIONS（0 BLOCKER）+ E4 3575/3575 PASS + MIT V114 R3 APPROVE。**Secret fail-closed**（缺檔 disable，同 TOTP pattern）：operator 後續寫 `~/BybitOpenClaw/secrets/vault/{slack_webhook,email_config}.json` 才 live。**C4+C5 defer Sprint 3**（pipeline_ctor wire + GUI banner + failsafe_ack_role）見下方 4 Sprint 3 ticket。**Ref**: PA spec `docs/execution_plan/specs/2026-05-28--packet_c_3way_dispatcher_wire_spec.md` + E1 reports pc1/pc2/pc3/email/v114_idempotency/med_low + E2 + E4 + MIT R1/R2/R3 memory。 |
| `P2-PACKET-C-C4-PIPELINE-WIRE` | 2 | **NEW Sprint 3 defer (v79 per operator Q5=PC.B)** — C4 = `tasks.rs::spawn_notification_failsafe_watcher` + pipeline_ctor wire + 注入 ThreeWayDispatcher/RestPositionProvider/BybitExchangeStopSync/PgAuditEmitter/WallClock 替 mock。**前置阻**：(1) **HIGH-1 PA ruling**（見 `P1-PACKET-C-HIGH1-BANNER-CHANNEL-WEIGHT`）— banner pull-channel 不該與 Slack+Email push 同權計 AllFail，否則 fail-safe 核心場景失效；(2) **ATR 注入**（operator Q-B=BB）— Bybit REST 不回 ATR → `active_lock_profit_per_position` 全跳過 → SL 不收緊；C4 須從 strategies ATR cache 注入 PositionSnapshot.atr；(3) C3 PC3.Q4 `dispatch_and_observe` vs mpsc outcome 路徑 C4 spec 明指；(4) paper engine_mode noop（C4 必驗 paper pipeline 不注入 exchange sync）。**Owner**: PA spec → E1 → E2 → E4 → QA。**Trigger**: Sprint 3 + HIGH-1 ruling。 |
| `P1-PACKET-C-HIGH1-BANNER-CHANNEL-WEIGHT` | 1 | **NEW Sprint 3 defer (v79 per E2 full Rust HIGH-1)** — **設計缺陷 + 可能 AMD 澄清**：`three_way.rs compute_outcome` 要 3 路全 false 才 AllFail；但 console banner = 本地檔寫（永遠成功）→ Slack+Email **雙掛**（operator 兩 push 通道全失聯，正是 fail-safe 要保護場景）時 banner 仍成功 → 判 PartialFail → 1h timer **不武裝** → 不升 Defensive。root cause：pull-based passive channel（banner 寫成功 ≠ 人被通知）不該與 push channel 同權計入冗餘。**屬 AMD-2026-05-21-01 §Decision 3.1「三路冗餘」語義層級重新詮釋** → 須 PA ruling（可能需 AMD amendment：AllFail 應 = 兩 push channel 全 fail，banner 為 last-resort visibility 不計 delivery）。**不阻 C1-C3 merge**（deferred stub 未進 runtime）；**阻 C4 wire**。**Owner**: PA → 可能 CC（AMD）→ E1 修 compute_outcome。**Trigger**: Sprint 3 C4 前。 |
| `P2-PACKET-C-C5-GUI-BANNER-ACK-ROLE` | 2 | **NEW Sprint 3 defer (v79 per PC.B + MIT/E2 finding)** — C5 = GUI banner display（tab-governance 頂部）+ operator ack typed confirm（V099-style）+ `failsafe_ack_role` restricted PG role。**MIT R3 finding**：trading_admin = OWNER+SUPERUSER 隱式持全 column UPDATE，V114 column-level 限制只 bind 非-owner role；**production GUI ack 路徑必須用獨立受限 role**（`failsafe_ack_role` 只 column UPDATE acked_*），否則 append-only 限制形同虛設。當前 DB 無此 role。C5 須先 provision role 再 wire GUI ack endpoint 呼 `audit_emitter::ack_failsafe_event`。**Owner**: E1a(GUI) + E1(role migration) + MIT(role verify)。**Trigger**: Sprint 3 C4 後（依 C4 watcher live）。 |
| `P1-COLD-AUDIT-LIVE-GATE-FAKE-SUCCESS` | 1 | **NEW 2026-05-29 per cold audit PA P1-01/P1-02/P1-04/P1-05/P1-17** — live 授權與 GUI 成功語義不可信：Executor live 授權驗證仍吃 IPC secret 域；live start/resume/grant 與全局模式切換可在未完成 signed live gate + Rust readback 時回報 `active/success`；live close-all GUI 會遮蔽 partial failure；Settings safe-recheck/demo-validate 只是蓋章，不是證據。**Owner**: PA spec → E1 → E2 → A3/E3/E4；**AC**: 驗簽改用 live-auth signing-key；live mode 僅接受精確 `live_reserved`；`active/granted/success` 前必有 IPC 成功 + Rust readback；任何 partial failure 顯示阻斷紅/警告；蓋章狀態不得滿足 readiness gate；**Ref**: PA plan `P1-01/02/04/05/17` + PM final `2026-05-17--cold_audit_pm_final.md`。 |
| `P1-COLD-AUDIT-LIVE-CANCEL-AUTHORITY-DECISION` | 1 | **NEW 2026-05-29 per cold audit PA P1-03** — Python live Stop 會直接呼叫 Bybit `cancel-all`，屬 Rust authority 外的 exchange-mutating live write。**Operator/PA/CC 必先決策**：改成 Rust-only authority，或用 ADR/audit/5-gate 正式批准極窄 emergency exception。**Owner**: operator + PA + CC → E1；**AC**: 不再存在未批准的 Python live exchange write；BB/E2 驗證。 |
| `P1-COLD-AUDIT-ORDER-RETRY-POLICY` | 1 | **NEW 2026-05-29 per cold audit PA P1-07** — mutating order-create retry 與「timeout / 非 0 `retCode` 必 fail-closed」硬邊界衝突。**Operator/PA/CC 必先決策**：採嚴格 reconcile-before-retry，或明文批准 idempotent retry exception。**Owner**: operator + PA + CC → E1；**AC**: dispatch retry 測試、CLAUDE/ADR 邊界與實作三者一致；BB + E4 驗 timeout/retCode 行為。 |
| `P1-COLD-AUDIT-BYBIT-STOP-LIVEDEMO-SEMANTICS` | 1 | **NEW 2026-05-29 per cold audit PA P1-06/P1-08 (+P2-02/03/04)** — Bybit 交易語義包：exchange-side trading-stop 未按 tick rounding；LiveDemo 的 live secret slot 可退回 process env credentials；amend、rate-limit、Bybit reference doc 也有同類語義漂移。**Owner**: PA → E1 + BB；**AC**: trading-stop/amend 一律用 instrument precision 或 fail-closed；LiveDemo 對 `live` slot 禁 env fallback；rate-limit/docs 與 source 對齊；cargo + BB regression 綠。 |
| `P1-COLD-AUDIT-EVIDENCE-PROMOTION-GATES` | 1 | **NEW 2026-05-29 per cold audit PA P1-09/P1-10/P1-11/P1-16** — 證據/晉級 gate 包：過期 edge snapshot 可通過 cost gate；paper promotion path 仍可進 demo，違反 paper lane freeze；`learning.close_maker_audit` 缺表（既有 `P1-LEARNING-CLOSE-MAKER-AUDIT-TABLE-MISSING` 為子任務）；Alpha/M11 文件與 runtime 語義漂移可能製造假 evidence。**Owner**: PA → E1 + MIT + TW；**AC**: stale/unvalidated edge 必 fail/defer；paper 不得 promote demo；close-maker audit table/writer/healthcheck 或規格修訂需 MIT dry-run 後落地；Alpha/M11 文檔明確分離 Stage A smoke 與 Stage B promotion evidence。 |
| `P1-COLD-AUDIT-AI-ML-LINEAGE` | 1 | **NEW 2026-05-29 per cold audit PA P1-12/P1-13/P1-14** — AI/ML lineage 包：AI policy enum 與 route binder 命名不一致，可能在 `should_call_ai=true` 後阻斷真調用；provider-native paid call 未進 durable invocation/cost ledger；fresh shadow model 未登記到 canary/promotion registry。**Owner**: PA → E1 + MIT + AI-E；**AC**: route enum 端到端 fixture 通過；paid call 必寫 durable invocation/cost ledger，否則不能滿足 cost gate；fresh artifact 必註冊或 fail loud。 |
| `P1-COLD-AUDIT-SOT-DOCS-DRIFT` | 2 | **NEW 2026-05-29 per cold audit PA P1-15** — active governance SoT 漂移：SPECIFICATION_REGISTER 內 ADR 路徑失效、Operator mirror 與 canonical report 漂移、docs/source route 有歧義。**Owner**: TW + PM + R4（若 ADR 命名意圖要改則 PA 介入）；**AC**: active register path-existence check 綠；重要 Operator mirror 改為 stub/pointer 或與 canonical 一致；R4 驗證無死 active authority path。 |
| `P2-COLD-AUDIT-DEFERRED-BACKLOG` | 3 | **NEW 2026-05-29 per cold audit PA confirmed P2/P3** — PA 另確認 17 個 P2 + 7 個 P3；PM 暫不拆成 24 條 TODO，避免 active queue 膨脹。**Owner**: PM scheduler；**AC**: Sprint cleanup 前，按 PA report 拆成聚焦修復包，或明確 defer/archive 並寫理由；**Ref**: PA plan Confirmed P2/P3 sections。 |
| `P1-LG-3-AC-CORRECTION` | – | ✅ **CLOSED 2026-05-26 / VERIFIED 2026-05-27** — PA delivered (1) spec v2 amendment 83 行 L1771-1851 (V094→V104 1:1 + V099/V100 移除 + §2.4A wording drift 移除) (2) V104 scaffold 378 行 `srv/docs/execution_plan/specs/2026-05-26--v104-lg3-supervised-live-audit-migration.md` (10 章 + 21 col + 4 CHECK + hypertable + Guard A/B/C + 4-step PG dry-run + V094→V104 replacement rule) (3) TODO §1 row reframe applied；**2026-05-27 PA verify pass**：3/3 drift FULLY COVERED + sql/migrations/ empirical V104 FREE；2 external gate remain = v56 P0 Layer B + 24h (~2026-05-30) + MIT V104 4-step empirical dry-run 9/9 PASS；ref close report `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-26--p0_lg3_ac_correction_and_v104_scaffold.md` + verify report `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-27--p0_lg3_spec_verify_and_todo_patch.md` |
| `P1-FUNDING-ARB-DEPRECATION-CASCADE` | – | ✅ **FULLY CLOSED 2026-05-26** Phase 1+2 + R4 Pass A+B APPROVE — PA spec (551 行) + TW AMD-26-01 (372 行) + 5/5 primary + 19/19 secondary + R4 Pass A APPROVE-WITH-DRIFT + R4 Pass B APPROVE 0 dangling；commits `6a20b9ea` + `e913adbf` 三端同步；3 LOW carry-over defer D+7 (~2026-06-02 piggyback E1 `#[deprecated]` IMPL): (1) EA-3 hotfix spec SUPERSEDED header (2) SQL V033 enum header (`strategy_close_funding_arb`) (3) docs/README specs/ index 補 PA spec entry；後續 PENDING follow-up: E1 D+7 `#[deprecated]` IMPL + MIT D+30 PG retention + QC D+30 observation；ref §9 Workflow F + AMD-26-01 §11 cascade checklist + R4 Pass B report `docs/CCAgentWorkSpace/R4/workspace/reports/2026-05-26--workflow-f-cross-ref-audit-pass-b.md` |
| `P2-OPS-2-HOTRELOAD` | 3 | **NEW 2026-05-26 per E3-HIGH-1 long-term** — `Arc<ArcSwap<BybitCredentials>>` + IPC reload handler = 5s rotation parity with authorization.json；消除 engine restart for Bybit key rotation；Owner: E1；ETA: Post-Sprint 4 |
| `P2-OPS-2-AUDIT-ENDPOINT` | 3 | **NEW 2026-05-26 per E3-MED-1** — `POST /api/v1/security/ipc-secret/rotate` + governance audit row；Owner: E1；ETA: Post-Sprint 4 |
| `P2-OPS-2-CRON-DRIFT` | 3 | **NEW 2026-05-26 per E3-LOW-1** — `helper_scripts/cron/long_lived_secret_drift_check.sh` report mtime + alert > 365d / > 90d；Owner: E1；ETA: Post-Sprint 4 |
| `P2-OPS-2-GITLEAKS` | 3 | **NEW 2026-05-26 per E3 F-pattern recommend** — `gitleaks` or `detect-secrets` pre-commit hook（`ls .git/hooks/` 0 enforcement，只 `.sample`）；Owner: E1 + PA；ETA: Pre-Sprint 4 |
| `P2-OPS-2-RUNBOOK-HEALTHCHECK-SQL` | 3 | **NEW 2026-05-28 per PA v1.0 patch out-of-scope obs (MED)** — runbook §10.3 healthcheck integration 假設 `passive_wait_healthcheck.py --check secret_rotation` 已實裝；實際 routine 不存在 → §10 4 verify 條變實質 3 條；Owner: E1 + MIT；ETA: 2-3 hr；triggered if §10.3 cited in cutover；ref `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-28--ops_2_runbook_v1_0_patch.md` §4 |
| `P3-OPS-2-RUNBOOK-EMERGENCY-AUDIT-CONTRACT` | 4 | **NEW 2026-05-28 per PA v1.0 patch out-of-scope obs (LOW)** — runbook §6.2.4 A-1 emergency revoke + §5.2.3 P-3 Bybit 24h soak old key revoke 均缺 audit row contract（無 `old_key_revoked_at` timestamp + 無明文 `/auth/revoke` audit row 規格）；Owner: PA + E1；ETA: 1-2 hr spec + 1 hr IMPL；non-blocker first-day live |
| `P1-EARN-WAVE-C-FIRST-STAKE-RUNTIME` | 2 | **SOURCE-LAYER FULLY CLOSED 2026-05-26 / OPERATOR-BLOCKED on OP-1** — Wave C source-layer 全 land: IntentProcessor Earn branch ✅ + OPENCLAW_ALLOW_MAINNET=1 ✅ + earn_routes.py 1221 LOC (6 endpoint /balance /products /preflight /stake /positions /records + 5-gate + HMAC sig verify) + tab-earn.html 516 + earn-tab.js 750 (7 sections + 5-gate UI + typed-confirm phrase 整數鎖 + V100 enum + event_ts_utc) + replay_earn_preflight.py 799 (5 sanity + 5 fail injection + HMAC sig) + test 27+14 PASS / 2 round 1+2 IMPL + E2 APPROVE 8/8 + A3 9/10 + E4 PASS 27/10/249 / `_format_phrase_amount(150)='150'` integer empirical + `_hmac_sig=64hex` tamper-PENDING verify；PG `learning.earn_movement_log` still 0 rows. **仍阻 7 OP hand action**: (OP-1-a Bybit web UI mainnet key Read+Trade+Earn) (OP-1-b old key delete) (OP-1-c new key create with no IP restriction per (b)) (OP-1-d Stage 0R Earn variant §8 8 OQ 拍板) (OP-1-e ssh trade-core 鍵入 + 改 bybit_endpoint demo→mainnet) (OP-1-f Python /auth/renew 簽 authorization.json) (OP-3 first stake $100-200 Flexible via tab-earn). **5 可代做 post-1..5** (待 OP-1-e 觸發). |
| `P2-EARN-WAVE-D-CONTRACT-INTEGRATION-TEST` | 2 | **NEW 2026-05-26 per E2 round 2 carry-over** — E1+E1a round 1 並行沒做 contract testing → 4 處 schema 脫節（field name / phrase format / outcome enum / event_ts_utc），round 2 全修；E2 round 2 verdict 揭露**無 integration smoke test**（frontend phrase build → POST → backend canonical → Rust IPC roundtrip 全鏈）；現 27 tests 全 FastAPI TestClient + dependency_overrides + mock IPC。**修法**: Wave D Rust IPC 接通後新增 1 integration test 跑全鏈。Owner: E1 + E1a + MIT；ETA: ~3-5 hr；阻 Wave D Rust 接通驗證 |
| `P1-EARN-WAVE-D-RUST-HMAC-CANONICAL-FORM` | 1 | **NEW 2026-05-26 per E2 round 2 HIGH risk** — Python 端 HMAC canonical 用 `json.dumps(sort_keys=True, separators=(",",":"))` Python stdlib；Rust 端 Wave D 若用 `serde_json::to_string` default 順序非 sort_keys → **HMAC byte 不對齊** → Wave D Rust IPC 接通即 fail。**修法**: Wave D PA spec 必明定 Rust 端用 `BTreeMap` 或 serde `#[serde(...)]` 顯式排序產生 canonical 對齊 Python `sort_keys=True`；Wave D IMPL 必 cross-language HMAC byte-identical test (fixture amount=150 → sha256 = `<known hex>`). Owner: PA spec + E1 Rust IMPL + E4 cross-lang test；ETA: ~4-6 hr (含 Wave D Rust IPC dispatch 接通)；阻 Wave D Rust IPC roundtrip + 防 Earn first stake silent fail. ref earn_routes.py:402 `_verify_stage_0r_hmac` |
| `P1-OP1-BYBIT-ENDPOINT-FILE-MISCONFIG` | 1 | secrets file 內容 `"demo"` (live slot 標 live 但 endpoint 標 demo) | OP-1 secret swap 同步改 file 為 `mainnet`；E1 SSH atomic restart；~2 min |
| `P1-EDGE-2` (funding_arb) | – | ✅ **ARCHIVE-READY 2026-05-26 per AMD-2026-05-26-01** — operator chose (D) 3C TOML deprecation closure；funding_arb V2 Retired closed；ADR-0018 status 升格；strategy roster 5→4 textbook；本條目於 D+7 E1 IMPL DONE 後可移 §-1 archive；ref `P1-FUNDING-ARB-DEPRECATION-CASCADE` + AMD-2026-05-26-01 §3+§4 |
| `P3-WORKFLOW-F-D7-CARRYOVER` | 4 | **NEW 2026-05-26 per R4 Pass B 3 LOW carry-over** — D+7 (~2026-06-02) E1 `#[deprecated]` IMPL piggyback：(1) EA-3 hotfix spec `2026-05-25--ea3_funding_arb_sl_gate_p1_hotfix_spec.md` 加 `> Status: Superseded per AMD-26-01` header (2) SQL V033 `fills_exit_reason.sql` 加 historical-only header (`strategy_close_funding_arb` enum value lineage) (3) `docs/README.md` line 226 specs/ 目錄補 PA spec `2026-05-26--funding-arb-deprecation-cascade.md` entry；Owner: E1 piggyback + R4 D+7 cycle verify；ETA: 30 min |
| `P1-LG-5` | 4 | LG-5 reviewer maturity watch | source 活躍；7d 共 66 review_live_candidate verdict=defer；90d cadence 觸發 review |
| `P1-HALT-TRIGGER-ROOT-CAUSE-INVESTIGATION-1` | 3 | v56 P0 未解 root cause；H4 healthcheck [69] LIVE | forensic `halt_audit.log` armed；passive wait + 90d review 2026-08-21 |
| `P1-LEASE-1` | 3 | 清掃 terminal `lease.rs:303` + HashMap leak | 依賴 P0-LG-3 IMPL DISPATCH；工時 ~4-6h |
| `P1-EDGE-P2-3-PH1B-DYNAMIC-BACKOFF-FOLLOWUP` | 4 | Phase 1b spec §5.4 完整 dynamic backoff state machine | Phase 2a Demo PASS 後另開 PR；PA 估 ~130 LOC |
| `P1-LEARNING-CLOSE-MAKER-AUDIT-TABLE-MISSING` | 1 | **NEW 2026-05-25** per QA EA-1 empirical — `learning.close_maker_audit` table NOT deployed PG | PA spec V### migration + writer wire-up；~4-6 hr；阻 §5 pilot adverse selection 監測 |
| `P1-INTENTYPE-FIELD-VISIBILITY-DEFER` | 4 | OrderIntent struct field `pub → pub(crate)` 影響 4 integration test + IPC serde + openclaw_types re-export = builder pattern 重構 | PA builder pattern spec + E1 IMPL ~4-6 hr；defer 下個 sprint |
| `P2-WATCHDOG-STATUS-JSON-WRITER` | 3 | `/tmp/openclaw/watchdog_status.json` 不存在；daemon running and CLI returns JSON OK | PA + E1；~2-4 hr (write status file or remove stale healthcheck)；Sprint 2 Wave 3 / pre-flight |
| `P3-HYGIENE-OPTION-E-FD-INHERIT-CORNER-CASE` | 3 | **NEW 2026-05-25** — `build_then_restart_atomic.sh` Phase 5 spawn 的 engine 繼承父 shell FD 200 (flock) | PA spec + E1 IMPL；~30 min；Sprint 2 Wave 3 |
| `P3-SUB-AGENT-HYGIENE-SOP-CARGO-TEST-AFTER-ATOMIC` | 3 | **NEW 2026-05-25** — E4 sub-agent 跑 `ssh cargo test --release` 觸 multi-session race；SOP 寫入 prompt template | PA spec + 主會話 prompt template update；~1 hr |
| `P1-OP1-IP-WHITELIST-CORRECTION` | – | ✅ **OPERATOR-DECIDED 2026-05-25** — 選項 (b) Bybit "no IP restriction" | OP-1-d 觸發；含 OP-1 |
| `P1-ENV-OPENCLAW-ALLOW-MAINNET-SET` | – | ✅ **FULLY CLOSED 2026-05-25** by `a51c1a1f` + `a775b5b9` + `a7ada6cf` + `ae7b207c` | env count 12→13 / persistence verify across restart |
| `P1-C10-SYNTHETIC-SPOT-CLOSE-PNL-FALLBACK` | – | ✅ **SOURCE-LAYER CLOSED 2026-05-25** | commit `015b9735` + E2/E4 round 2 PASS |
| `P1-INTENTTYPE-DIRECTION-MISMATCH` + `-V2` | – | ✅ **CLOSED 2026-05-25** | commit `015b9735` + `bbb21c56` |
| `P1-SPRINT-1B-C10-CLOSURE-GAPS` | – | ✅ **SOURCE/FEATURE CLOSED 2026-05-25** | full chain done；7d demo observation → 2026-06-01 |
| `P1-ENGINE-BINARY-SPRINT-1A-IMPL-DEPLOY` | – | ✅ **FULLY CLOSED 2026-05-25 01:18 UTC** by Hygiene Option E A+B 並行 | PID 350616 → ... → 374287；proc SHA match disk |
| `W-S4-AC1B-HEALTHCHECK` | 2 | ✅ **CLOSED-VERIFY 2026-05-25 recheck** | 6 health domain × 30min 全 PASS |
| `P1-V107-SQL-GUARD-A-LOGIC-DRIFT` | – | ✅ **CLOSED 2026-05-22** by `c706c49c` | sandbox Round 1+2 PASS |
| `P1-PG-CHECKSUM-ALIGNMENT-DECISION-2-C` | – | ✅ **CLOSED-VERIFY 2026-05-28** for current landed SQL set | trading_ai `_sqlx_migrations` max=113/count=105；`repair_migration_checksum --verify drift_count=0` |
| `P1-SANDBOX-SQLX-METADATA-ALIGNMENT` | – | ✅ **FULLY CLOSED 2026-05-24** Round 1+2 | sandbox V100+ checksum 對齊 trading_ai 主 DB sha256 |

**v5.8 24 H 級 ticket**（按 module 分組）→ ref `docs/archive/2026-05-21--todo_v60_archive.md` §B（24 條 carry into Sprint 1A-β/γ/δ/ε 期間並行補）

---

## §7 Operator Action Checklist（D+0 ~ Sprint 4 first Live ETA）

| 日期 | Action | 預期時間 | Trigger | 卡進度後果 |
|---|---|---|---|---|
| ~~**D+0 NEW (2026-05-26)**~~ | ~~confirm AMD-2026-05-25-01 商業化邊界 + AMD-2026-05-25-02 v5.5 reframe~~ ✅ **DONE 2026-05-27** — 兩 AMD operator APPROVE；Workflow D (25-01) + E (25-02) cascade completed | — | — | — |
| **D+0 NEW** | commit canary [67]→[80] rename 4 files | 5 min | E1 sub-agent ready | 阻 sync (已 commit cf61d1f0 ✅) |
| ~~**D+1-D+2**~~ | ~~AMD-21-01 v2 Layered Autonomy 最終 sign-off + Wave 5 Packet A/B kickoff~~ ✅ **DONE 2026-05-28** — operator APPROVE 三 AMD 同輪；Packet A V099 + Packet B API/GUI posture landed；remaining TOTP backend + Packet C/R4 | — | — | — |
| **D+2-D+3** | OP-1 a-f Bybit Web UI **mainnet** key 重發（per C-3 2026-05-26：現 2 demo key + 33d TTL，mainnet key 未發 → Sprint 4 first Live + Earn 雙線需）| 5-10 min | OP-1 pre-verify done | 阻 Sprint 4 first Live + Earn Wave C production deploy |
| **D+2-D+3** | OP-2 Stage 0R Earn variant 仲裁（8 OQ）| 30-60 min | OP-1 完成 | 阻 first stake |
| **D+2-D+3** | OP-3 first stake **$100-200 USDT Flexible-only** via tab-earn（per C-5 2026-05-26 拍板 USDT only 免幣價跌）| 5 min | OP-2 拍板 | 阻 `learning.earn_movement_log` rows>0 |
| ~~D+3~~ | ~~P0-FUNDING-ARB-DECISION-FORCE 升等拍板~~ | – | ✅ **CLOSED 2026-05-26 operator chose (D)** | cascade Workflow F NEW (4-6 hr)；§15 #1 reframed |
| **D+5** | P0-EDGE-1 + P0-LG-3 + P0-OPS residual OP gates closure ETA 填 §10 P0 precondition | 30 min | PM ping | P0 runtime/migration/OPS-1 已收口；仍需 pg_dump cron+restore drill、system-level unit install、LG-3 gate、EDGE-1 Alpha path |
| **W12** | **Sprint 2 業務 Alpha Tournament 派發**（5 stream × 7 sub-agent Wave 1+2+3）| – | Sprint 1A-γ V111 land | 阻 §1 P0-EDGE-1 AC-A (ii) 路徑 |
| **W18-21 (~2026-09)** | **★ Sprint 4 first Live $500 ★** | – | P0-EDGE-1 + LG-3 + OPS residual OP gates 全 closure | – |

**Operator 手做時間 D+0~D+5 ≈ 2.5-4 hr**（OP-1 系列佔大頭）

---

## §8 Backlog by Cluster（per PM §3 parallel 分組）

### §8.1 Cluster 1 — Independent Parallel（D+0 立即啟動）— ✅ **6/6 全 CLOSED 2026-05-27**
1. ~~**Workflow A**~~ — ✅ PA design + FA pre-verify CONDITIONAL APPROVE + TW AMD-09-03 §9 patch +143 LOC (C1-C6 全 land) + QC math sanity PASS + [81] SQL prototype；pending = E4 + R4 + operator sign-off
2. ~~**Workflow D**~~ — ✅ AMD-25-01 cascade 6 files
3. ~~**Workflow E**~~ — ✅ AMD-25-02 cascade 6 files
4. ~~**Workflow F**~~ — ✅ CLOSED 2026-05-26 funding_arb deprecation
5. ~~**Workflow J**~~ — ✅ CLOSED 2026-05-27 by PA inline CORRECTION
6. ~~**OPS [78]**~~ — ✅ CLOSED 2026-05-27 by E3 (crontab now installed)

### §8.2 Cluster 2 — Partial-Dependent（B Phase 1→2→3 / Sprint 1A-γ/δ/ε）
- **Workflow B Phase 1**（Sprint 1A-γ）：ADR-0046 basis spec execution split IMPL（PA → E1 → E2）
- **Workflow B Phase 2**（Sprint 1A-δ）：funding_arb IMPL + MIT V117 dry-run（PA → E1 → MIT → E2）
- **Workflow B Phase 3**（Sprint 1A-ε）：funding_arb live + BB approve + QA backfill（E4 → BB → QA）
- 估時 24-30 hr total；不阻 Sprint 2 主軸

### §8.3 Cluster 3 — Operator-Gated
- AMD-25-01/02 confirm（D+0 NEW）
- AMD-21-01 v2 Wave 5 final sign-off ✅ done；Packet A V099 runtime apply/register ✅ done
- OP-1 a-f Bybit Web UI key 重發（D+2-D+3）
- OP-2 Stage 0R Earn variant 仲裁（D+2-D+3）
- OP-3 first stake（D+2-D+3）
- P0-FUNDING-ARB-DECISION-FORCE 升等拍板（D+3）
- P0-EDGE-1 + LG-3 + OPS residual OP gates closure ETA（D+5）

### §8.4 Sprint 2 業務 Alpha Tournament dispatch（W12-15）
**SSOT**：`docs/execution_plan/2026-05-26--alpha_tournament_ssot_spec.md`
**Stream A**（Sprint 2 IMPL 2 candidate + 1 DRAFT）：
- A1 funding short-only > 30% annualized
- A2 liquidation cascade fade (LCS isolated cluster + book recovery + PostOnly maker)
- A3 BTC/ETH cointegration pairs DRAFT
**Stream B**（V108/V109 spec + MIT）
**Stream C**（Optuna 後端 skeleton；依 V111 land）
**Wave 1+2+3 phase chain**（per PA dispatch packet `2026-05-25--sprint_2_business_dispatch_packet.md`）
**估時**：248-351 hr / 3w wall-clock / 7 並行 sub-agent

### §8.5 PA Condition Follow-up Deferred
- ~~**C2** ADR-0030 4-gate threshold 副帳場景 verify（E4 + FM；3-6 hr；opportunistic）~~ ✅ **CLOSED 2026-05-27 by AMD-2026-05-25-02 §4.2** — 副帳 Y2+ enable 條件 = ADR-0030 4-gate + AMD-25-02 Gate 5 Moat（reverse-snipe defense + simulator >95% + anti-snipe + Master Trader API + ranking dashboard）共 5-gate 全 PASS；framework 已 lock，無 verify work
- **C3** ADR-0046 公式補位（funding_cost_bps + borrow_cost_bps）+ dual-write phase + V117 預寫 pending（PA → E1 → MIT → E2；8-12 hr）
- **C4** E4 canary [80] full sweep verify namespace="canary"（E4；2-4 hr；依 canary deploy 穩定）

---

## §9 Cascade Pending（AMD/ADR → DOC-XX per FA §3）

| 來源 | Cascade 目標 | Owner | Status |
|---|---|---|---|
| **AMD-2026-05-25-01** | docs/README AMD list / SPECIFICATION_REGISTER count / TODO §8 Stream 2 殘留 cleanup / AMD-04+05 supersede markers | PA Workflow D | ✅ **CLOSED 2026-05-27** Cascade executed — operator APPROVE 2026-05-27 via PM session AskUserQuestion；AMD-25-01 Status Active；docs/README + SPECIFICATION_REGISTER 已 land entry；AMD-04 §1 Stream 2 + AMD-05 Stream 2 retain 部分 supersede marker land；`monetization-demand-test-spec.md` superseded marker pre-existed；TODO 無 Stream 2 active task 殘留（active surface 0 / archive-only mention 11+ files）；report `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-27--workflow_d_amd_25_01_cascade.md` |
| **AMD-2026-05-25-02** | docs/README AMD list / SPECIFICATION_REGISTER count / AMD-25-01 §3.2 cross-ref / ADR-0030 cross-ref / AMD Status Active + approval log / TODO §8.5 C2 cleanup | PA Workflow E | ✅ **CLOSED 2026-05-27** Cascade 完成；report `2026-05-27--workflow_e_amd_25_02_cascade.md` |
| **AMD-2026-05-21-01 v2 Wave 5** | ADR-0034 LAL 對齊矩陣加 Autonomy Level / ADR-0040 §Decision 5 / ADR-0042/0044/0045 wording sync + V099 schema + GUI sub-section + Rust SM-04 patch | PA + E1 + E1a + MIT + R4 | 🟡 **Packet A+B + TOTP source + ADR/R4 landed 2026-05-28** — V099 runtime apply/register + API/GUI posture deployed fail-closed at `a07a08c0`; TOTP source backend tests PASS but runtime enrollment missing; Packet C core E4 PASS but engine integration missing; R4 report `docs/CCAgentWorkSpace/R4/workspace/reports/2026-05-28--wave5_totp_packetc_adr_ops_r4.md`；remaining = Packet C engine integration + runtime TOTP secret enrollment. |
| **ADR-0046 (Proposed)** | funding_arb.rs IMPL + V117 migration spec + Optuna search space update | PA + E1 + MIT | Sprint 1A-δ/ε 平行 land |
| **drift audit 2026-05-25** | TODO active state update + v5.8 文檔 patches (DONE 10 patches) | PM | Cascade 完成 ✅ |
| **operator decision 2026-05-26 (D) funding_arb deprecation** (Workflow F) | (1) PA spec (551 行) ✅ `2026-05-26--funding-arb-deprecation-cascade.md` (2) TW AMD-26-01 372 行 + 5 primary + 19 secondary ✅ `2026-05-26--AMD-2026-05-26-01-funding-arb-deprecation.md` (3) R4 Pass A APPROVE-WITH-DRIFT ✅ `2026-05-26--workflow-f-cross-ref-audit.md` (4) R4 Pass B APPROVE ✅ `2026-05-26--workflow-f-cross-ref-audit-pass-b.md` | PA → TW → R4 | ✅ **CLOSED 2026-05-26** Cascade 完成；3 LOW carry-over defer D+7 (~2026-06-02) |

---

## §10 V1→V5.8 Drift Audit Closure Pointer（2026-05-25）

**狀態**：✅ **FULLY DONE + 3 端同步 + PM/PA/FA 三方 sign-off APPROVED-CONDITIONAL**

**SSOT 文件指針**（4 commits at cf61d1f0）：
1. **Drift audit 終稿** — `docs/audits/2026-05-25--v1_to_v58_full_consolidation_drift.md`（499 行 / 22 plan/audit files / 8 errors corrected / 10 真實 unresolved / 72% false positive rate 自評）
2. **AMD-2026-05-25-01** Commercialization Boundary: Exchange-Native Only — `docs/governance_dev/amendments/2026-05-25--AMD-2026-05-25-01-commercialization-exchange-native-only.md`
3. **AMD-2026-05-25-02** v5.5 Bot Positioning + Capital Structure Formalization — `docs/governance_dev/amendments/2026-05-25--AMD-2026-05-25-02-v55-bot-positioning-capital-structure-formalization.md`
4. **v5.8 文檔 10 patches** — `docs/execution_plan/2026-05-20--execution-plan-v5.8.md`（M4/M7/M13 inconsistency + ADR-0042-0046 roster + AMD-25-01/02 cross-ref）

**核心發現**：
- ADR-0028/0029 編號順移 confirmed（v5.6/v5.7 提案實際 land 為 ADR-0030/0031/0032）
- W-AUDIT-8b tombstoned per AMD-15-02 v0.7 Round 2 RED_FINAL
- ADR-0021 + ARCH-04 + CONTEXT 5 詞條全 land
- F-22 label_close_tag NULL 98.9% CLOSED by AMD-11-W6-1（V086+V091+HC[65]）
- F-22 risk_verdicts retention CLOSED by V075（30d drop + 7d compress）
- F-08 vs MIT-P0-2 RECONCILED per 2026-05-16 PM report
- G1 v1.9 6 P1 task 6/6 CLOSED in commit `07cfcb72`
- SSH empirical verify 3 PASS：F-22 / F-08 / [55][67][27]
- BONUS finding：[78] feature_baseline_writer cron stale 4.75d → ✅ **CLOSED 2026-05-27** by E3 reconcile（crontab now installed + healthcheck today PASS；ref §13）

**Pending follow-up (Cluster 1)**：A + D + E + J **4 並行** D+0 立即啟動（OPS[78] ✅ CLOSED 2026-05-27 per E3 reconcile，無需 IMPL；J + A 已 DONE 2026-05-27；D + E cascade 啟動 post AMD-25-01/25-02 operator APPROVE 2026-05-27）

---

## §11 Layered Autonomy v2 Wave 5 Cascade Pointer（2026-05-22）

**狀態**：🟡 **Packet A+B runtime + TOTP source + ADR/R4 + Packet C core regression landed, fail-closed by design** 2026-05-28 + ✅ **operator APPROVE 2026-05-27** + CC APPROVE A 級；full Wave 5 close still requires runtime TOTP enrollment and Packet C engine integration.

**4 個 SSOT 文件指針**：
1. **AMD-2026-05-21-01 v2** — `docs/governance_dev/amendments/2026-05-22--AMD-2026-05-21-01-autonomy-fully-with-failsafe.md`（684 行）
2. **PA spec v2** — `docs/execution_plan/2026-05-22--autonomy_level_toggle_design_spec.md`（1031 行 / Autonomy Level Toggle + 5 fail-safe hard req）
3. **V099 schema spec** — `docs/execution_plan/specs/2026-05-22--v099-autonomy-level-config.md`（568 行）
4. **CC re-audit** — `docs/CCAgentWorkSpace/CC/workspace/reports/2026-05-22--layered_autonomy_v2_reaudit.md`（A 級 / 7 HC + 6 反模式 + 2 BLOCKER 候選解除）

**Wave 5 cascade IMPL roadmap**（updated 2026-05-28）：
1. **Packet A V099 schema land** — ✅ DONE physical apply/register + checksum drift 0.
2. **Packet B GUI/API Autonomy Posture** — ✅ DONE commit `a07a08c0`: state/eligibility/status/switch endpoints, GUI posture panel, typed-confirm/audit/cooldown skeleton, Linux API-only deploy. Switch remains blocked by P0-EDGE evidence and runtime TOTP enrollment.
3. **TOTP backend wire-up** — 🟡 SOURCE DONE / RUNTIME ENROLLMENT PENDING: file-backed verifier + route guard + 10 pytest PASS; operator must enroll secret file outside git and smoke `totp_backend_configured=true`.
4. **Packet C Rust SM-04 patch review** — 🟡 SOURCE E2/E4 DONE: core risk_gov 27/27 PASS + engine lib 3468/3468 PASS; full integration still needs engine notification timeout scheduler, exchange conditional SL sync, and audit emit.
5. **5 module ADR sync + R4 cross-ref audit** — ✅ DONE: ADR-0034 + ADR-0040 + ADR-0042/0044/0045 wording 對齊；R4 report `2026-05-28--wave5_totp_packetc_adr_ops_r4.md`.

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
| ~~**[78] feature_baseline_writer cron stale**~~ | ✅ **CLOSED 2026-05-27 by E3 reconcile** — root cause (c) post-restart auto-fix：2026-05-22 G1 cluster 取樣 4.75d stale 因 crontab 尚未 install；現 `41 4 * * *` installed + 兩日連續 fire；sentinel `/tmp/openclaw/cron_heartbeat/feature_baseline_writer.last_fire` mtime=2026-05-27 04:41:01 / age=8.9h<25h threshold；`check_78_feature_baseline_writer_cron_fires()` 今日返 PASS；無「信號源不一致」（sentinel mtime = wrapper start 04:41 vs PG write 04:42 同週期差 1m33s）；ref E3 inline finding 2026-05-27 + `helper_scripts/db/passive_wait_healthcheck/checks_cron_heartbeat.py:175-189` |
| **Hygiene Option E FD 200 inherit corner case** | NEW 2026-05-25 | PA spec + E1 IMPL；`restart_all.sh nohup ... 0<&- 200<&-` 或 Phase 5 前 manual `flock -u 200`；ref `P3-HYGIENE-OPTION-E-FD-INHERIT-CORNER-CASE` |
| **DEPRECATED.md 引用警報** | NEW per FA §5 | 任何代碼/文件仍引舊 DOC = active blocker；FA grep 週期 |
| **5-gate / hard boundary 觸碰 record** | OPENCLAW_ALLOW_MAINNET=1 set 2026-05-25 + authorization.json missing OP-1 預期 | 14d lineage scan per FA |
| **跨平台 path 違規** | proc-exe drift 揭發 path migration | `/home/ncyu` / `/Users/` 硬編碼 weekly grep；無 `OPENCLAW_BASE_DIR` env 預設 |
| **Multi-session race** | mitigated per memory `feedback_git_commit_only_for_metadoc` + `feedback_fetch_before_dispatch` | meta-doc 用 `git commit --only`；dispatch 前 `git fetch`；sub-agent prompt hygiene 警示段落 |
| **.docx vs .md 漂移** | FA non-blocker | skill 9.2 SOP；考慮 pre-commit hook |

---

## §14 排程 + Milestone

| 日期 / Sprint | 工作 | Gate |
|---|---|---|
| ~~**D+0 (2026-05-26)**~~ | ~~confirm AMD-25-01/02 + Cluster 1 五並行啟動~~ ✅ **DONE 2026-05-27** Cluster 1 6/6 全 CLOSED + 三 AMD operator APPROVE | — |
| ~~**D+1-D+2**~~ | ~~AMD-21-01 v2 final sign-off + Wave 5 Packet A/B runtime land~~ ✅ **operator APPROVE 2026-05-27** + **V099 physical apply/register 2026-05-28** + **Packet B API/GUI fail-closed deploy 2026-05-28** + Packet C Rust SM-04 source present | 下一步：TOTP backend + Packet C E2/E4/integration + R4 ADR sync |
| **2026-06-10** | OPS-2 Phase 2 cutover (D+14 soak end) | E1 PR move fallback + main.rs panic block + Python reason rename + AuthError variant delete |
| **D+2-D+3** | OP-1 a-f + OP-2 + OP-3 Earn first stake | `learning.earn_movement_log` rows > 0 |
| **D+5** | P0-EDGE-1 / LG-3 / OPS residual OP gates closure ETA | Sprint 4 first Live W18-21 unblock |
| **2026-06-01** | C10 funding harvest 7d demo AC #1/#4 sample | Stage 1 Demo verdict |
| **2026-06-02** | 14d bucket-split AC verdict（ALT 25.7% / large_cap 66.7%）| QC EA-1 Phase 1b verdict |
| **2026-06-09** | `P1-CONDITIONAL-WATCH` TONUSDT 30d evidence freeze | QC 2026-05-11 zero-cost #4 |
| **W12-15** | **Sprint 2 業務 Alpha Tournament dispatch** | 5 stream × 7 並行 sub-agent / 248-351 hr |
| **2026-08-21** | `P2-FALLBACK-DEAD-ENUM-90D-AUDIT` + `P1-HALT-TRIGGER` review | 90d cadence |
| **W18-21 (~2026-09 初)** | **★ Sprint 4 first Live $500 ★** | P0-EDGE-1 + LG-3 + OPS-1..4 全 closure |
| **W44-55 (~2027 Q1-Q2)** | **Y1 末 — autonomy 66%** | Copy Trading evidence gate / Overlay verdict |
| **~21-24 mo** | **Y2 Q2 Auto-Allocator activation — autonomy 90%** | 6mo Advisory + >80% approval |
| **~32 mo** | **Y3 Q2 — autonomy 95%** | M10 Tier C-E / M12 / M13 Y3+ |

---

## §15 跨 Wave 衝突仲裁

| # | 衝突 | 解 |
|---|---|---|
| 1 | ~~LG-3 IMPL DISPATCH ↔ P0-FUNDING-ARB-DECISION-FORCE~~ | ❌ **WITHDRAWN 2026-05-26 / VERIFIED 2026-05-27** — FALSE dep（LG-3 supervised live SM 為所有策略 supervised live activation gate，與 funding_arb retired/active 解耦 per AMD-2026-05-26-01）。真衝突 = V### 號占用（V099 autonomy_level_config 預留 + V100 m4_hypothesis_base 已 land → LG-3 取 V104 FREE per 2026-05-27 empirical）+ v56 P0 Layer B + 24h gate ~2026-05-30。ref `P1-LG-3-AC-CORRECTION` (§6 ✅ CLOSED) + V104 spec scaffold |
| 2 | Phase 2a engine STOPPED ↔ verdict 視窗累積 | 每暫停 1h 失 ~0.4 rows；後續禁無預警 stop |
| 3 | W-AUDIT-9 graduated canary path ↔ ExecutorAgent shadow_mode | per AMD-2026-05-15-01：Stage 0R replay preflight + Stage 1 demo |
| 4 | Sprint 1A-β/γ/δ 順序 dispatch ↔ cross-V### dependency | per v58-CR-9 PG dry-run + cross-V### dependency graph |
| 5 | ~~**Workflow B Phase 2 V117 ↔ funding_arb V2 active timing**~~ | ❌ **OBSOLETED 2026-05-26 per AMD-2026-05-26-01** — funding_arb V2 Retired closed；V117 重新 framed 為 ADR-0046 future redesign slot 的 V3 schema 預留；revive 須走 AMD amendment + ADR-0046 Accepted + 5-gate + Stage 0R replay preflight，非 single-sprint apply 路徑 |
| 6 | **Cluster 1 5 並行 ↔ Multi-session race** | 每次 sub-agent dispatch 前強制 `git fetch`；meta-doc `--only` commit |
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
- **drift audit 終稿**：`docs/audits/2026-05-25--v1_to_v58_full_consolidation_drift.md`
- **AMD-25-01**：`docs/governance_dev/amendments/2026-05-25--AMD-2026-05-25-01-commercialization-exchange-native-only.md`
- **AMD-25-02**：`docs/governance_dev/amendments/2026-05-25--AMD-2026-05-25-02-v55-bot-positioning-capital-structure-formalization.md`
- **AMD-21-01 v2**：`docs/governance_dev/amendments/2026-05-22--AMD-2026-05-21-01-autonomy-fully-with-failsafe.md`
- **PA spec v2**：`docs/execution_plan/2026-05-22--autonomy_level_toggle_design_spec.md`
- **V099 spec**：`docs/execution_plan/specs/2026-05-22--v099-autonomy-level-config.md`
- **CC re-audit Layered Autonomy v2**：`docs/CCAgentWorkSpace/CC/workspace/reports/2026-05-22--layered_autonomy_v2_reaudit.md`
- **SPECIFICATION_REGISTER**：`docs/governance_dev/SPECIFICATION_REGISTER.md`
- **Active ADR**：ADR-0006/0017/0018/0020/0022/0023/0024/0028/0029/0030/0031/0032/0033/0034/0035/0036/0037/0038/0039/0040/0041/0042/0043/0044/0045 + ADR-0046（PROPOSED 2026-05-25）
- **Active AMD**：AMD-2026-05-09-03 / -10-03 / -10-04 / -10-05 / -11-W6-1 / -15-01 / -15-02 v0.7 / -20-04 / -21-01 v2 / -25-01 / -25-02
- **Sub-agent hygiene SOP**：`docs/agents/sub-agent-hygiene-sop.md`
- **Bybit API reference**：`docs/references/2026-04-04--bybit_api_reference.md`
- **v60/v65 TODO archive**：`docs/archive/2026-05-21--todo_v60_archive.md` + 待 archive `docs/archive/2026-05-26--todo_v65_archive.md`

---

## §-1 歷史 closure 摘要（≤14d；舊細節 → archive）

- **2026-05-28 D+2 PM takeover continuation — runbook v1.0 land + 14d soak D+1 observation**：
  - `P1-OPS-2-RUNBOOK-V1.0-PATCH` CLOSED — PA delivered 4-patch v1.0 對齊 A3 條件：(1) §4.2.1 quote box Phase 1 backward-compat note（restart_all seed-from-ipc 不違反 urandom，首次 90d rotation 必獨立）(2) §10.1.1 sub-section `grep -c ops2_secret_split_phase1_fallback /tmp/openclaw/{engine,api}.log = 0` invariant + AC table (3) §10.5 cross-lang HMAC sanity check（pinned hex `1b2b18d7...8b78fc`）(4) §13 6-sub Phase 2 cutover SOP；495→687 行（+192）；§11 Revision v1.0 + §12 Cross-Refs +6 entries。
  - `P1-OPS-2-14D-SOAK-OBSERVE` D+1 ssh trade-core empirical：engine.log 0 / api.log 0 hits of `ops2_secret_split_phase1_fallback` ✅；AC (a) PASS；AC (b) `/auth/renew` 0 次（OP-1 operator-blocked，繼續累積觀察）。Phase 2 D+14 = 2026-06-10 unchanged。
  - 3 P2/P3 carry-over land from PA out-of-scope obs：`P2-OPS-2-RUNBOOK-HEALTHCHECK-SQL` (MED, §10.3 `passive_wait_healthcheck.py --check secret_rotation` 未實裝)；`P3-OPS-2-RUNBOOK-EMERGENCY-AUDIT-CONTRACT` (LOW, §6.2.4 A-1 + §5.2.3 P-3 24h soak 缺 audit row contract)；non-blocker first-day live。
  - 三端 sync target pending：Mac SSOT v75 doc-only push → origin/main → trade-core fast-forward。
- **2026-05-28 D+2 P0 收口 + Wave 5 Packet A/B runtime land（commits `0100da7c` + `22466a81` + `a07a08c0` + DB hand-action）**：
  - Engine/API/user watchdog recovered；healthz 200；system-level unit install still operator/sudo hand-action。
  - Migration/register drift closed：V109/V113 register 補登；V099 physical apply + `_sqlx_migrations` register；`repair_migration_checksum --verify drift_count=0`。
  - OPS-1 enforcing-ready gaps closed：CSRF 403 friendly toast + reload；cert trust runbook + install hint；7d shadow + `csrf_shadow_zero_verify.sh` PASS 0。
  - Wave 5 Packet B landed/deployed：autonomy state/eligibility/status/switch API + GUI Autonomy Posture；switch remains fail-closed on missing TOTP backend and P0-EDGE evidence，避免 fake autonomy success。
  - Passive healthcheck still FAIL on `[48] replay_manifest_registry_growth`, `[74] close_maker_reject_samples`, `[56] live_pipeline_active authorization_json_missing`; `[80] pg_dump_freshness` insufficient sample。這些轉 OPS residual / evidence queue，不反轉 OPS-1 closure。
  - Next true dev phase：TOTP backend + Packet C E2/E4/integration/R4；then Sprint 2 Alpha Tournament when P0-EDGE/LG/OPS residual gates are scheduled。
- **2026-05-28 D+2 follow-up Wave5/OPS reality check**：
  - TOTP source backend landed with fail-closed file verifier + route evidence gate guard; runtime secret missing, so no successful Level2 path until operator enrollment.
  - Packet C source E2/E4 is green (`risk_gov` 27/27; `openclaw_engine --lib` 3468/3468, 1 ignored) but engine integration is still genuinely absent: no notification 3-way timeout caller, no exchange conditional SL sync, no audit emit.
  - 5 ADR sync done: ADR-0034/0040/0042/0044/0045; R4 report records boundaries.
  - OPS `[80]` pg_dump fixed at runtime: 4.6G dump, md5/audit/TOC PASS, daily 03:00 UTC cron installed. Passive healthcheck now has only `[48]/[74]/[56]` FAILs, all real evidence/operator gates.
- **2026-05-27 D+1 OPS-4 GAP B+D FULLY CLOSED via 3-round IMPL chain + E2/E4 r1+r2 + QA E2E + engine dead discovery**：
  - **Round 1 commit `1392c9e1`** PA spec amend (449→695) + E1 4/6 deliverable (3 cron + V113) + MIT 1/3 (post_restore_validation.sql 330 LOC)
  - **Round 2 commit `261d3956`** E1 round 2 補 (check_pg_dump_freshness.py 616 LOC + passive_wait wire) + MIT round 2 補 (pg_restore_drill_sop.md 572 LOC + template 239 LOC)
  - **Round 3 commit `cf710dc7`** MIT Q3 P0 BUG fix (ts→created_at) + E1 3 MED fix (platform_guard call + heartbeat cross-check + ENTRY env-var validation) + PA mini-patch spec §10.B.1 4→2 event_type + §10.C P3 backlog
  - **E2 r1** APPROVE-WITH-CONDITION (3 MED) → **r2 APPROVE** (LOW-1 auto-resolved by MED-2)
  - **E4 r1** YELLOW (Q3 P0 BUG + 3 MED) → **r2 GREEN 雙重 confirm** (original + re-dispatch both verify GREEN)
  - **QA E2E APPROVE-CONDITIONAL** commit `b548c10d`: 5-gate 5/5 + 9 invariant 9/9 + FA 6/15 PASS-AUTOMATIC + 3 PARTIAL + 6 PENDING operator + 0 FAIL；7 operator hand-action ready
  - **3 hidden risks QA empirical surfaced**: (1) V099 deployment gap (Wave 5 Packet A scope, non-blocker) (2) **V113 sqlx register drift** (psql raw apply skipped sqlx register; operator 必 `cargo run --release --bin repair_migration_checksum -- --verify`) (3) **🔴 engine + watchdog PROCESS DEAD 8h33m** (ps -ef 0 hit / snapshot stale 30806s) — 升 P0 §1；**2026-05-28 三項均已在上方 D+1 bullet 收口/降為 OP residual**
  - **3 端 sync** Mac/origin/Linux HEAD `b548c10d`
- **2026-05-27 D+0 Wave 4 closure（6 sub-agent / commit `07027493`）**：
  - **E1 OPS-1 round 2** ✅ 8 fix + bonus；33→48 test PASS + 6 JS node --check + grep 0 raw POST；2026-05-28 A3 enforcing gaps R2/R3/R4 已由 `22466a81` 補齊
  - **E1 OPS-4 minor** ✅ 4/4 fix；bash -n PASS；E4 ready
  - **R4 Workflow A** ✅ APPROVE-WITH-MINOR-CASCADE-GAP；7/7 internal PASS + 2 D+1 docs/README+SPEC_REG cascade gap
  - **MIT OPS-4 GAP-B+D** ⚠️ PARTIAL：GAP-B 53d schema-only dump+NAS 未掛；GAP-D 3 drafts ready (291 行) 但未 install + disk 226GB×15d 接近 841GB ceiling；7 operator hand-action ~28hr unblock
  - **E1 Wave 5 Packet A V099** ✅ 369 行 + D1-D13 PG empirical PASS + D14-D19 對抗 11/11 PASS + idempotency PASS；⚠ V99<V100 out-of-order PM accept needed before next engine restart
  - **E1 Wave 5 Packet C Rust SM-04** ✅ +349 LOC + 3469+423+27 cargo test PASS + 25 transition pair 0 regression + clippy 0 hit + fail-closed NaN/負值 skip
- **2026-05-27 D+0 Wave 1-3 大規模並行 closure（22 sub-agent / 三波 / commits `bcf0e401` → `0459d451` → `65e78437`）**：
  - **Wave 1 (4 並行)**: PA Workflow A design 323 行 (22 invariant 4-Group framework + 5 risk + FA pre-verify recommend) / PA Workflow J L243+L259 inline CORRECTION 撤回 / E3 OPS [78] reconcile root cause (c) crontab now installed + healthcheck today PASS / PA P0-LG-3 verify 3/3 drift FULLY COVERED + V104 FREE empirical
  - **Wave 2 (9 並行)**: FA Workflow A pre-verify CONDITIONAL APPROVE 22/22 字對齊 + 6 conditions / PA Workflow D AMD-25-01 cascade 6 files / PA Workflow E AMD-25-02 cascade 6 files / PA Wave 5 dispatch packet master 410 行 / MIT V104 9/9 PASS + 2 bonus LG-3 IMPL gate (2) UNBLOCKED / PA OPS-2 runbook v0.9 495 行 / E1 OPS-1 1242 LOC + 33/33 PASS / E1 OPS-2 SECRET-SPLIT Phase 1 477 LOC + cross-lang HMAC byte-identical / E1 OPS-4 systemd 2 unit + 2 install script
  - **Wave 3 (8 並行 review chain)**: A3 OPS-1 6.0/10 CONDITIONAL (1 BLOCKER raw fetch + 2 HIGH SOP/toast) / A3 OPS-2 8.0/10 CONDITIONAL (4 Phase 2 follow-ups) / E2 OPS-1 RETURN 2 HIGH + 3 MED (E1 round 2 4-6 hr) / E2 OPS-2 APPROVE-CONDITIONAL 0 BLOCKER/HIGH + 2 MED / E2 OPS-4 APPROVE-WITH-MINOR 1 MED + 3 LOW / CC OPS-2 APPROVE-CONDITIONAL 16/16+9/9+4/4 hard gate + Mainnet env-var fallback closed 紀律 reconcile PASS (signing-key 域) / TW Workflow A AMD-09-03 §9 patch +143 LOC (C1-C6 全 land) / QC Workflow A math sanity PASS + [81] SQL prototype 155 LOC + C7 cluster center wording suggestion
  - **3 AMD operator APPROVE 2026-05-27**: AMD-25-01 Commercialization Exchange-Native + AMD-25-02 v5.5 Bot Positioning + AMD-21-01 v2 Layered Autonomy with Fail-Safe (Wave 5 packet master ready)
  - 真實 closure: 0 OPS critical block；P0-LG-3 gate (2) UNBLOCKED；OPS-1 shadow mode commit OK pending E1 round 2 enforcing cutover；OPS-2 14d soak start D+0 → D+14 2026-06-10 Phase 2 cutover；OPS-4 4 minor E1 in-place fix
- **2026-05-26 §1 P0 advance — LG-3 AC correction + OPS-2 SECRET-SPLIT design**：
  - **P0-LG-3 AC correction** ✅ PA delivered — spec v2 amendment 83 行 (line 1771-1851) + V104 migration spec scaffold 378 行 + TODO §1 reframe applied；2 external gate pending = v56 P0 Layer B + 24h (~2026-05-30) + MIT V104 4-step PG dry-run；ref `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-26--p0_lg3_ac_correction_and_v104_scaffold.md`
  - **P1-OPS-2-SECRET-SPLIT design** ✅ PA delivered — 484 行 / 12 章 spec at `srv/docs/execution_plan/specs/2026-05-26--p1-ops-2-secret-split-design.md`；Phase 1 D+0 + Phase 2 D+14；5-gate #4+#5 強化；E1 IMPL 125 LOC / 3 並行 sub-agent / 10-14 hr active + 14d soak；5 hidden risks (HIGH IPC client mis-migration); CC review trigger E1 IMPL DONE + E4 GREEN
  - 真實 closure: 0/3 ACTIVE P0 close today；EDGE-1 ETA W18 (5 mo via Sprint 2)；LG-3 ETA D+14 (post external gate);OPS-1..4 ETA W18-21 (Sprint 4 first Live)
- **2026-05-26 OPS-3 5/5 operator confirm sequential closure + Workflow F Phase 1+2 partial**：
  - **C-1~C-5 sequential signoff** ✅：Spain residence (allowed) / ≥L2 KYC / 2 demo+33d TTL (OP-1 pending mainnet) / Spain tax defer first Live+30d / USDT Flexible $100-200 first stake accepted；signoff doc `srv/docs/governance_dev/2026-05-26--bybit_compliance_signoff.md`；P1-OPS-3-OPERATOR-CONFIRM-5 CLOSED
  - **Workflow F Phase 1 PA spec** ✅ `srv/docs/execution_plan/specs/2026-05-26--funding-arb-deprecation-cascade.md` (551 行)
  - **Workflow F FULLY CLOSED** ✅ Phase 1 PA spec (551 行) + Phase 2 TW (AMD-26-01 372 行 + 5/5 primary + 19/19 secondary cascade) + R4 Pass A APPROVE-WITH-DRIFT + R4 Pass B APPROVE 0 dangling；3 LOW carry-over defer D+7 → `P3-WORKFLOW-F-D7-CARRYOVER`
  - **Linux atomic rebuild+restart** ✅ engine new PID 1228870 (23:06 起跑替舊 374287)；demo pipeline alive；live pipeline dead 71h pre-existing per OP-1 authorization.json 未簽
  - **3 端 git sync** ✅ Mac / origin / trade-core HEAD `e913adbf` (commit chain `6a20b9ea` → `e913adbf` 兩段 push + ssh ff)
- **2026-05-26 §1 4 P0 並行推進 + operator funding_arb (D) closure**：5 sub-agent fan-out — PA OPS-1 spec (Caddy+Tailscale TLS / 23-33hr E1 IMPL) / E3 OPS-2 audit (1 CRIT secret split + 2 HIGH / 0 NEW leak in 1320 commits) / BB OPS-3 audit (CONDITIONAL / 5 operator confirm / C-1 residence 最大 ship-stop) / PA OPS-4 runbook (11 章 + 8 GAP / 4 critical) / PA LG-3 verify (SCOPE-QUESTION-PENDING-OPERATOR — TODO §1 行 48 AC drift + §15 #1 FALSE dep)；EDGE-1 SSH empirical 0/3 AC paths satisfied；operator chose (D) funding_arb 3C TOML deprecation → §1 CLOSED + §9 Workflow F NEW；§6 加 16 新 P1/P2 entries；§15 #1 reframed
- **2026-05-25 V1→V5.8 drift audit closure** ✅ (8 errors corrected + 10 真實 unresolved + 2 AMD proposed + ADR-0046 proposed + canary [67]→[80] rename + SSH empirical 3 PASS + monetization-demand-test-spec.md superseded marker + 4 commit 三端 sync HEAD `cf61d1f0`；PM+PA+FA 三方 APPROVED-CONDITIONAL；ref §10 SSOT 指針)
- **2026-05-26 Alpha Tournament SSOT 補洞**：`docs/execution_plan/2026-05-26--alpha_tournament_ssot_spec.md` land；v5.8 §4 implicit Alpha slot → 可派發 SSOT；候選池 / scoring contract / minimum evidence gates / Stage output 全部固定
- **2026-05-25 v64 消歧義 + Day -1 派工 + EA-4 P0-EDGE-1 AC amend + E1 H-3 push back**：「Sprint 2」三義性 closure + EA-4 P0-EDGE-1 AC-A 三選一條件 amend 解雞蛋論
- **2026-05-25 governance lesson**：sub-agent audit report 引用 file path / line range 必驗實際 code 對齊；E5 §H-3 line range 錯誤 + path mismatch claim 誤判 → 若 E1 沒對抗核驗會白派 IMPL
- **2026-05-25 PA Day -1 3 spec land + EA-3 verdict overturn**：commit `e1993ec6` (1) H-2 cron restoration spec 修 E5 ml_training 分級 (2) sub-agent hygiene SOP 8 prompt template 警示 (3) PA overturn QC EA-3 funding_arb SL gate verdict 為 doc-only
- **2026-05-25 EA-1 Phase 1b sweep chain** (4 sub-agent round)：Round 1 揭 harness IMPL bug → Round 2 Option A 1-LOC fix → PA §4 acceptance gate 揭 Top-1 已 live since `820f0532` → QA verify ENDORSE 46/8/27 + 48-72h pilot recommend
- **2026-05-25 NEW P1**: `P1-LEARNING-CLOSE-MAKER-AUDIT-TABLE-MISSING`（per QA empirical PG SELECT 揭 table NOT deployed）→ PA spec needed
- **2026-05-25 H-1 atomic deploy verify ✅ DONE**：build_then_restart_atomic.sh 7-phase flock + restart_all.sh --require-clean-build-window land；Lock release 100% verified
- **2026-05-25 H-2 cron restore ✅ DONE + EA-2 N/A confirmed**：PM atomic apply 10/13 enabled + 3 defer；Sprint 2 Day 0 業務派發 readiness UNBLOCKED
- **2026-05-25 Sprint 2 Day 0 業務派發 readiness 確認 + PM 3 decision 拍板**：PA dispatch packet `2026-05-25--sprint_2_business_dispatch_packet.md` 5 stream × 7 並行 sub-agent
- **2026-05-25 PM recheck**：C10 PnL + IntentType + Earn Wave C source gaps progressed；running engine has C10/Earn symbols；proc-exe drift + Earn first stake 0 rows remain active
- **2026-05-23 Sprint 4+ §4.1 + Stage A→F + Sprint 5+ Wave 1 ALL CLOSED** (19 commit chain `011fd5f9 → 22a07294`)：詳情 `docs/archive/2026-05-23--sprint_4plus_5plus_wave1_closure.md`
- **2026-05-22 Sub-IMPL: M3 emitter scaffold ✅ PASS WITH 5 CARRY** + Layered Autonomy v2 設計 DONE + CC APPROVE A 級
- **2026-05-21 closure**：v5.7 12 prefix DESIGN-DONE + v5.8 16 CR + Sprint 1A-α/β/γ/δ/ε PM signoff 全 land；詳情 `docs/archive/2026-05-21--sprint_1a_alpha_repair_closure.md`
- **Incident marker 2026-05-21**：09:58 UTC engine + watchdog SIGTERM；13:31 UTC PM restart_all.sh --keep-auth 恢復；Phase 2a sample velocity gap ~3.5h

**詳細歷史 archive**：
- `docs/archive/2026-05-23--sprint_4plus_5plus_wave1_closure.md`（Sprint 4+ §4.1 + Stage A→F + Sprint 5+ Wave 1）
- `docs/archive/2026-05-21--todo_v60_archive.md`（v60 §A-§F + v5.7 12 prefix + W-AUDIT-4b + H+I 批 closure）
- `docs/archive/2026-05-21--todo_v58_layout_refactor_archive.md`（v58 layout refactor）

---

**Maintenance contract**：依 `docs/agents/todo-maintenance.md` 將本檔保持為活躍派工佇列。穩定專案脈絡走 `README.md`；agent 操作規則走 `CLAUDE.md`；歷史 closure 走 `docs/archive/`。三方 sign-off (PM CONDITIONAL APPROVED / PA APPROVE-CONDITIONAL / FA Conditional Approve) 之 BLOCKER 候選 (governance_hub spec / HIST-02 frozen amend / DOC-08 §12 對應 AMD-25-02 cooling) 進 §13 Drift Watch 追蹤。
