# 玄衡 TODO — 活躍派工佇列

**版本**：v62（v61 + 2026-05-24 Sprint 1A→1B 真實完成度核實 / runtime gap dispatch）
**日期**：2026-05-24
**Session**：v5.7 + v5.8 13-module autonomy expansion (44-55w Y1 + 21-32mo 達 95% autonomy)
**v60 完整歷史 archive**：`docs/archive/2026-05-21--todo_v60_archive.md`

---

## §0 摘要

- **Current Sprint Phase**：Sprint 1A-α + Wave 2 + Wave 2.5 + Sprint 1A-β + **Sprint 1A-γ DESIGN-DONE / IMPL-PENDING / RUNTIME-NOT-APPLIED** (PM-signed 2026-05-21；15/15 deliverable 全 land；M8 + V109 sequential final)；Sprint 1A-δ READY-TO-DISPATCH
  - 註：DESIGN-DONE = spec/ADR/runbook 文件 land；IMPL-PENDING = 無對應 IMPL 代碼；RUNTIME-NOT-APPLIED = sql/migrations/ 本地 max=V098 / Linux PG `_sqlx_migrations` max=96 / 10 target table (health_observations / degradation_state / replay_divergence_log / reward_weight_history / decision_lease_lal_tiers / lal_eligibility_log / decay_signals / strategy_lifecycle / earn_movement_log / hypotheses) pg_class 0 hits（per 2026-05-21 acceptance audit）
- **Current Wave**：**Sprint 4+ §4.1 + Stage A→F + Sprint 5+ Wave 1 ✅ ALL CLOSED (2026-05-23 PM-signed)** — 詳情已歸檔至 `docs/archive/2026-05-23--sprint_4plus_5plus_wave1_closure.md`；11 carry-over 已 routing (8 Sprint 4+ §4.1 + 3 Sprint 5+ Wave 2)；3 governance NEW (PA-DRIFT-6/7/8) 已 land；runtime later corrected 2026-05-24: API PID 3989463 / engine PID 4105805；6 active domain × 30 min × 1836 row PG empirical PASS
- **Sprint 1B 剩 3 章節 dispatch ✅ Wave A+B+Earn-Wave-2 DONE (2026-05-23 single session)** — v5.7 baseline ✅ closed (PA Track 4 DOWNGRADE-TO-NON-WORK)；**Pending 3.1 C10 funding harvest Stage 1 Demo** Wave A+B IMPL DONE (E1 Rust funding_harvest 5 file 2028 LOC + 4 strategies 接線 + 6 TOML 接線 / E1 Python Stage 0R replay harness 1089 LOC / MIT V108 spec APPROVED；HEAD 255a83f6；cargo workspace 4079/0/5)；**Pending 3.2 Earn first stake ✅ SPEC-FINAL (2026-05-23 operator OP-4 ✅ APPROVE, HEAD 5e95edfe)** — 4 OPs 拍板 (OP-1 Bybit Web UI key 重發 < 2026-04-09 / OP-2 first stake $100-200 / OP-3 Flexible-only / OP-4 SPEC-FINAL + commit + push + Wave C ready) + Wave B 5 並行 IMPL DONE (LeaseScope +EarnStake/EarnRedeem / IntentType +PositionAdjust+EarnStake+EarnRedeem / bybit_earn_client.rs 601 LOC 5 V5 unified endpoint / earn_movement_writer.rs 679 LOC / earn_reconciliation.rs 742 LOC UTC 02:00 + 3 cascade threshold) + 5/5 cross-ref ✅ APPROVE (MIT/E3/FA/QA/BB) + 0 BLOCKER + 7 carry-over (Wave C B6 IntentProcessor Earn branch / Stage 0R Earn variant 仲裁 / E3 4 Wave E integration / MIT 4 SHOULD Sprint 5+) + PM landed 9 spec patches；cargo workspace 4128/0/5；**Next**：Sprint 1B Pending 3.1 C10 closure 鏈 (E2 + V108 → E1 → E4 + QA Stage 0R Acceptance + PM Phase 3e) + Earn Wave C (B6 IntentProcessor Earn branch + Stage 0R Earn variant + OP-1 Bybit Web UI key 重發後 production deploy) defer 下 session
- **PM 2026-05-24 Sprint 1A→1B 真實完成度核實**：**NOT FULLY COMPLETE**。Design/spec 層大多完成；Mac/source 層 C10 + Earn Wave B targeted tests PASS；production PG 已有 V100/V103/V106/V107/V112 等核心表與 V106 health rows；但 trade-core running binary mtime 2026-05-23 17:56+0200 早於 C10/Earn commits，`strings` `funding_harvest`/`EarnStake`/`LAL_0_AUTO`/`replay_divergence_log` = 0；Earn 無 IntentProcessor branch / 無 first stake / `learning.earn_movement_log` 0 rows；C10 Stage 1 Demo 尚欠 E2+V108/E4/QA closure 與 synthetic spot close PnL 設計決議。Report: `docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-24--sprint_1a_1b_completion_audit.md`
- **GUI Bybit-first Demo PnL ✅ CLOSED / VERIFIED / ARCHIVED (2026-05-23, operator 1A2A3A)** — 詳情見 `docs/archive/2026-05-23--gui_bybit_first_pnl_refactor.md`；Mac 60/4199 passed + Linux 60/4201 passed；E2 + BB + E4 全 PASS
- **Layered Autonomy with Hard-Coded Fail-Safe 設計 ✅ DONE 2026-05-22**（AMD-2026-05-21-01 v2 + PA spec + V099 schema + CC re-audit **APPROVE A 級**）— ref **§1.7**；Wave 5 cascade IMPL PENDING operator final sign-off
- **Active P0**：`P0-EDGE-1`（5 strategy alpha-deficient）+ `P0-LG-3`（Wave 2.4 IMPL DISPATCH PENDING SPEC-READY 10d）+ `P0-OPS-1..4`（HTTPS / cred / legal / runbook）— Sprint 4 first Live W18-21 前必 closure
- **Next operator action**：(1) **OP-1 Bybit Web UI key 重發**（< 2026-04-09 key 已過期 ≥45 天，遠超 Bybit Earn API 14 天 scope refresh 政策；阻 Earn Wave C production deploy）(2) Sprint 1B Pending 3.1 C10 closure 鏈 dispatch (3) Earn Wave C dispatch (4) Layered Autonomy v2 Wave 5 cascade IMPL dispatch (ref §1.7)
- **Runtime**：2026-05-24 trade-core read-only verify：engine PID 4105805 alive + `/tmp/openclaw/engine.sock` owned by `openclaw-engine`；API PID 3989463 owns port 8000；watchdog `engine_alive=true`；PG `_sqlx_migrations` max=112 / count=102；6 active health domain × 30m PASS；C10/Earn/LAL symbols absent from running binary per audit above.
- **Pending operator decision**：(1) `P0-FUNDING-ARB-DECISION-FORCE` 升等 (2) Watchdog daemon R2 deploy 時機 (3) v5.8 16 CRITICAL 派發後 D+5 Sprint 1A-β readiness sign-off (4) **Layered Autonomy v2 Wave 5 cascade IMPL dispatch** (ref §1.7)

---

## §1 Session / Wave / Sprint 路線圖

### §1.1 Current Sprint Banner

```
Sprint 1A-α   DESIGN-DONE / IMPL-PENDING / RUNTIME-NOT-APPLIED (W0-1.5, 2026-05-21 PM-signed)  v5.7 12 prefix + PM signoff
Sprint 1A-修補 DESIGN-DONE / IMPL-PENDING / RUNTIME-NOT-APPLIED (D+0~D+5, 2026-05-21)           v5.8 16 CR + Wave 2.5 paperwork
Sprint 1A-β   DESIGN-DONE / IMPL-PENDING / RUNTIME-NOT-APPLIED (2026-05-21 PM-signed)          M1 LAL/M3/M6/M7/M11 DESIGN spec + 5 V### schema spec + 6 runbook (16 artifact / ~12,900+ 行；無 IMPL；V099+ migration 本地不存在；Linux PG max=96)
Sprint 1A-γ   DESIGN-DONE / IMPL-PENDING / RUNTIME-NOT-APPLIED (2026-05-21 PM-signed)          M2/M4/M8/M9/M10 DESIGN spec + V105/V108/V109/V111 schema spec + V103 EXTEND outline + 2 runbook + 3 ADR (M3/M6/M7) (15 artifact / ~12,400+ 行；無 IMPL；V###未 apply)
Sprint 1A-δ   DESIGN-DONE / **MAC-SOURCE-DONE (Rust trait stubs)** / **2026-05-24 LINUX-BINARY-PARTIAL** (2026-05-21 PM-signed + IMPL closure；2026-05-22 真實核驗修正；2026-05-24 隔壁 audit update)  M5/M12/M13 spec + V114/V115/V116 reserve (10 file design) + **6 Rust file land** (model_client 277 / order_router 393 / asset_venue 151 + 3 test 100+243+152) + 2 lib.rs edit + **+25 cargo test PASS** (M5 7 / M12 11 / M13 7) + 3 dup file mv→archive 完成 + 0 new warning / 0 mock / 0 flaky / Mac aarch64-apple-darwin cross-compile PASS；⚠️ **2026-05-24 update**: Linux engine 已 restart (PID 4105805 啟動 2026-05-24 00:11 / binary mtime 2026-05-23 17:56)；binary 含 Sprint 1A-δ trait stub symbol (M5/M12/M13) + Sprint 1A-ζ health/M3 emitter；**但仍缺** C10 funding_harvest / Earn / LAL_0_AUTO / replay_divergence_log symbol (因 binary build 早於 2026-05-23 19:36+ 後續 commit)；待 `P1-ENGINE-BINARY-SPRINT-1A-IMPL-DEPLOY` second rebuild
Sprint 1A-ε   DESIGN-DONE / IMPL-PENDING (2026-05-21 PM-signed)                                  R4 cross-ADR audit (5 CRITICAL + 4 HIGH patches applied) + TW CHANGELOG/CONTEXT + MIT V099-V116 ordering (1223) + E5 Mac CI (598) + A3 Wizard+Lv3-4 (520+) + 5 dup dedup applied (3 archived) + README index 22 entries
Sprint 1A-ζ   **✅ MAC-SOURCE-DONE + 2026-05-24 PRODUCTION-PG-LIVE + LAL/REPLAY-RUNTIME-NOT-PROVEN (2026-05-22 PM-signed + 真實核驗修正；2026-05-24 隔壁 audit update)** — IMPL Prototype Spike Track A/B/C Mac source layer 全 PASS（V106/V107/V112 .sql + Rust governance/lal mod.rs 25584 / health mod.rs 50802 + Python m11_spike 3 file）；**2026-05-24 update**: V106/V107/V112 已 land trading_ai 主 PG (sqlx apply 2026-05-23 12:38；7 row sha256 對齊 file empirical verify)；V106 health 6 active domain 30m rows PASS (api_latency 240 / database_pool 150 / engine_runtime 360 / pipeline_throughput 300 / risk_envelope 30 / strategy_quality 756)；**但 LAL Tier 0 runtime + M11 replay divergence runtime 仍 0 binary symbol**（待 `P1-ENGINE-BINARY-SPRINT-1A-IMPL-DEPLOY` second rebuild）；sandbox sqlx Round 1+2 已對齊 sha256 (per `P1-SANDBOX-SQLX-METADATA-ALIGNMENT` FULLY CLOSED 2026-05-24)；9 commit chain ad002617 → 7392d3d7；3 carry-over (PA-DRIFT-1/2 + E3-MED-2 已 closed Sprint 2 pre-readiness)
Sprint 1A-ε P1 **✅ DONE (2026-05-22)** — E3 sandbox_admin role + GRANT 13 schema + secret_file 0600；PA 5 spec patch (NEW-QA-1/2/3 + AC-7 path + V107 §4.2)；TW README +13 lines / 9 entry 新增；commit 454f26f3 + b579700e
Sprint 1A-ε P2 **✅ DONE (2026-05-22)** — N1 PA spec literal sqlx_migrate → MigrationRunner real path + V112 typo fix；N2 TW §8 path drift × 6 + ADR-0042 monitoring typo；N3 E3-MED-1 CLOSED via pg_hba.conf reject row (sandbox_admin → trading_ai REJECT；7/7 verify PASS；production engine 不誤殺)；commit 6cd3d631 + 8d744b95 + ddb7a57e
Sprint 1B early IMPL **✅ MAC-SOURCE-DONE + 2026-05-24 RUNTIME-PRE-CLOSURE (2026-05-22 + 2026-05-24 隔壁 audit update)** — 5 並行 Track Mac source layer 全 PASS：A PA M3 metric emitter Sprint 2 設計 848 LOC + B E4 28 pytest fail triage (0 drift / 0 Sprint 4 阻塞) + C V107 sandbox Round 1+2 PASS + dedup full 6/6 PASS (AC-6 caveat REMOVED) + D AC-7 Rust binding FULL PASS (bit-perfect 0.00e+00 diff Mac local；Linux x86_64 待 Sprint 4 deploy 補) + E cascade reject 2 unit test (guard 1+3 覆蓋) + 3 NEW carry-over (PA-DRIFT-1/PA-DRIFT-2/E3-MED-2)；commit 9cf0fe82；⚠️ **2026-05-24 update**: C10 funding_harvest + Earn Wave B source IMPL 已 land 但 binary 0 symbol (per 隔壁 audit `funding_harvest=0 / EarnStake=0`)；C10 Stage 1 Demo closure 缺 E2+V108+E4+QA+PM；Earn first stake 缺 OP-1 key refresh + IntentProcessor Earn branch + Stage 0R Earn variant + deploy + 實際 stake；**2 NEW P1 entry surfaced** `P1-C10-SYNTHETIC-SPOT-CLOSE-PNL-FALLBACK` + `P1-INTENTTYPE-DIRECTION-MISMATCH` (PA review 進行中)
Sprint 2 pre-readiness **✅ DONE (2026-05-22)** — 4 並行 Track 全 PASS + Sprint 2 readiness gate **FULLY OPEN**：Track 1 PA D1/D2/D3 整合 spec +113 LOC (848→961) + dispatch packet 563 LOC + readiness signoff 228 LOC；Track 2 E1 V103 file land 365 LOC + Sandbox Round 1+2 PASS + CHECK reject 3 PASS = **PA-DRIFT-2 HARD BLOCKER CLOSED**；Track 3 PA V107 spec 0 patch (Phase 3a aligned) = **PA-DRIFT-1 spec scope CLOSED** (V107 SQL drift carry-over E1 ~40 min P1)；Track 4 E3 17 table ALTER OWNER atomic + 4 DDL empirical PASS + production 不誤殺 = **E3-MED-2 CLOSED**；commit 81a2caeb + ca73798d
Sprint 4+ first Live **✅ §4.1 4 items DONE-VERDICT-PASS WITH 8 CARRY-OVER (2026-05-23 PM-signed, HEAD a9ae88fe)** — Wave A (PA-DRIFT-4 bybit + PA-DRIFT-5 risk envelope) + Wave B (main.rs scheduler) + E2 × 3 round 1+2 APPROVE + E4 regression PASS (cargo 3961 + pytest 6042 + nm 0 hit) + Production V106 deploy (psql -f raw apply, V103 Guard A FAIL trigger AUTO_MIGRATE=0 fallback) + AC-1b 5 active domain × 30 min × 20-264 row 遠超 ≥5 要求 + M-1 Singleton Registry SSOT 建立 (21 天 governance gap closure) + TW Acceptance 760 LOC + PM Phase 3e DONE；8 carry-over → Sprint 1B late §4.1.1 (V99-V102) / Sprint 5+ §4.2 (BybitPrivateWs 等 4) / §4.3 (M3 strategy_quality 等 6) / §4.4 (production 監測 4)
Stage A PA design × 4 並行 **✅ DONE (2026-05-23, HEAD 011fd5f9)** — Track 1 Sprint 1B late §4.1.1 V99-V102 audit + V099→V100 push back transcribe (PA inline 18504 chars → 327 LOC SSOT) / Track 2 Sprint 5+ §4.2.1 BybitPrivateWs supervisor Option A external Arc 注入 (293 LOC report + 738 LOC spec) / Track 3 Sprint 5+ §4.3.1 StrategyQualityEmitter wire-up Path A 1 CTE join (270 LOC report + 1200+ LOC spec) / Track 4 Sprint 1B 剩 3 章節 audit (622 LOC：C10 READY-TO-DISPATCH / Earn NEEDS-OPERATOR + §4.1.1 chain / v5.7 baseline DOWNGRADE-TO-NON-WORK)；7 file commit 3773 LOC；Stage B E1 IMPL dispatch readiness gate OPEN
Stage B E1 IMPL × 3 並行 **✅ DONE (2026-05-23, HEAD e5fb4895)** — B-1 V100 M4 base table (663 SQL + 581 spec; 3 table 30 col / 4 index / 2 FK / 25 COMMENT) + B-2 BybitPrivateWs supervisor Option A (5 caller updates + ctor +2 Arc + SharedClientsBundle +2 Option Arc + spawn_metric_emitter_scheduler signature +2 ref Option Arc; E1 2 push back 採信) + B-3 StrategyQualityEmitter Phase A (656 LOC probe_impl + Track E section 571 LOC + 5 CTE big query 2030 chars + main.rs caller +34 LOC + 3+7 inline test)；13 file commit 3728 insertions / 79 deletions；cargo test --workspace --release 3974 PASS
Stage C E2 round 1 × 3 並行 **✅ DONE (2026-05-23)** — B-1 V100 SQL ✅ APPROVE (0 CRIT/HIGH/MED；3 LOW non-blocking) / B-2 WS supervisor ✅ APPROVE (0 CRIT/HIGH/MED；2 LOW pre-existing) / B-3 StrategyQuality ❌ RETURN-TO-E1 (1 MEDIUM log literal + 1 LOW context_id NULL filter doc) → **C round 2 PM 直接 Edit fix HEAD 0d4a4aeb** (2 file +10/-1 LOC)
Stage D E4 combined regression **✅ APPROVE (2026-05-23, HEAD 0d4a4aeb)** — cargo 3974/0 + pytest 6088/28 + V100 sqlx parser 15/15 + binary symbol verify 全 PASS (Track E new literal ✅ + 'Track E skip' 0 hit + 0 spike + StrategyQuality module path + F-2 NaN sanitize + Scheduler spawning literal 全 land)；Linux deploy gate FULLY OPEN
Stage E Linux deploy chain **✅ FULL CLOSURE (2026-05-23, HEAD e377a94e)** — **PA-DRIFT-6 catch + fix** (V100 governance_approval_id FK 衝突 TimescaleDB composite PK；PM 直接 Edit drop FK 改 BIGINT soft reference + Guard C 改 column existence check)；psql -f raw apply V100/V103/V107/V112 (V106 pre-existing Sprint 4+)；7/7 target table 物理 land；_sqlx_migrations 9 row register；B-2 WS supervisor production WS metric verified (ws_rtt_p50=162ms / dropout=0 非全 0 placeholder)；B-3 Track E V106 strategy_quality **126 row 5 min** (解 Sprint 4+ §4.1 carry-over item 4)
Stage F TW Acceptance + PM Phase 3e **✅ DONE-VERDICT-PASS WITH 8 CARRY-OVER (2026-05-23)** — TW Stage A→E Overall Acceptance 663 LOC + AC-1b 30 min PG empirical FULL PASS (V106 strategy_quality 630 row 5×5×6×~4.2 ticks + api_latency ws_rtt avg 128.72-129.24ms / ws_dropout 0 × 29 sample + 5 active domain total 1653 row)；PM Phase 3e sign-off chain 9 階段全 land；8 carry-over routing 含 2 NEW (PA-DRIFT-6 audit P2 / sandbox V100 stub cleanup P2)；Sprint 1B late + Sprint 5+ + Sprint 4+ §4.1 item 4 全鏈 closure
```

> **狀態語言**（per 2026-05-21 acceptance audit）：
> - **DESIGN-DONE**：spec / ADR / runbook / schema spec 文件 land 在 docs/ 並通過 PM signoff
> - **IMPL-PENDING**：對應 Rust / Python / SQL 實作未開始（grep `nightly_replay|cf_quality|replay_divergence|earn_reconcile|lal_audit|decay_signal` in helper_scripts/api/python → 0 hits）
> - **RUNTIME-NOT-APPLIED**：sql/migrations/ 本地 max=V098；Linux runtime DB `_sqlx_migrations` MAX(version)=96 / COUNT=93；10 個 target table pg_class 0 hits

### §1.2 Sprint Progression Table（Sprint 1A → Y3）

| Sprint | Calendar | 主要工作 | 工時 (hr) | Status |
|---|---|---|---|---|
| 1A-α | 2026-05-21 done | v5.7 baseline + 4 follow-up | 75-105 | DESIGN-DONE / IMPL-PENDING |
| 1A-修補 | 2026-05-21 done | 16 CRITICAL + Wave 2.5 paperwork | 1,007-1,453 並行 | DESIGN-DONE / IMPL-PENDING |
| 1A-β | 2026-05-21 done | M1 LAL/M3/M6/M7/M11 DESIGN + V106/V107/V110/V112/V113 schema spec (本地無 .sql 檔；Linux PG 未 apply) + 6 runbook | 310-460 並行 (10 sub-agent + 3 recovery) | DESIGN-DONE / IMPL-PENDING / RUNTIME-NOT-APPLIED |
| 1A-γ | 2026-05-21 done | M2/M4/M8/M9/M10 DESIGN + V105/V108/V109/V111 schema spec + V103 EXTEND outline + 2 runbook + 3 ADR (M3/M6/M7) | 240-360 並行 (6 + 7 recovery + 2 sequential) | DESIGN-DONE / IMPL-PENDING / RUNTIME-NOT-APPLIED |
| 1A-δ | 2026-05-21 done | M5/M12/M13 spec (10 file) + **Rust trait stub IMPL** (model_client 277 / order_router 393 / asset_venue 151 + 3 test 495 行) + 2 lib.rs edit + +25 cargo test | 75-110 + IMPL 18-28 並行 (3 PA sub-agent + 3 E1 sub-agent + 1 E1 refactor + E2/E4) | DESIGN-DONE / **IMPL-DONE (trait stubs)** / RUNTIME-NOT-APPLIED |
| 1A-ε | 2026-05-21 done | R4 cross-ADR audit (5C+4H patches) + TW CHANGELOG/CONTEXT + MIT V099-V116 + E5 Mac CI + A3 Wizard+Lv3-4 + dup dedup + README index | 86-126 並行 (5 sub-agent + PM patch) | DESIGN-DONE / IMPL-PENDING |
| **1A-ζ** | **2026-05-21 — 2026-05-22 done** | **IMPL Prototype Spike DONE — Track A (M1 LAL+V112) PASS / Track B (M3 health+V106) PASS / Track C (M11 replay+V107) PASS WITH CAVEAT；E4 cargo 3769✅+pytest 6037✅+AC-7 7/7✅；QA AC-1..7 driver PASS WITH 3 CARRY-OVER；TW Acceptance Report 330 LOC；PM Phase 3e sign-off DONE** | **~30-40 actual (wall-clock 2 day high-density)** | **DONE-VERDICT-PASS WITH 3 CARRY-OVER (Sprint 1B gate OPEN)** |
| **1A-ε P1** | **2026-05-22 done** | **7 carry-over closure — E3 sandbox_admin role + PA 5 spec patch + TW docs index sweep** | **~2-3 hr 3 並行** | **✅ DONE** |
| **1A-ε P2** | **2026-05-22 done** | **3 follow-up closure — N1 PA sqlx_migrate path real + N2 TW §8 path drift × 6 + N3 E3-MED-1 pg_hba.conf reject row CLOSED** | **~1-1.5 hr 3 並行** | **✅ DONE** |
| **1B early IMPL** | **2026-05-22 done** | **5 並行 early Track — A PA M3 設計 848 LOC + B E4 pytest triage (5-11hr fix Sprint 2 carry) + C V107 sandbox + dedup full 6/6 (AC-6 caveat REMOVED) + D AC-7 Rust binding FULL + E cascade reject 2 unit test** | **~4-6 hr 5 並行** | **✅ DONE (Sprint 2 gate FULLY OPEN ✅)** |
| **2 pre-readiness** | **2026-05-22 done** | **4 並行 Track — PA D1/D2/D3 spec + dispatch packet 6 Track Wave 1+2 + E1 V103 land sandbox PASS + PA V107 align + E3 17 table ALTER OWNER × 4 DDL PASS** | **~2-3 hr 4 並行** | **✅ DONE (Sprint 2 dispatch gate FULLY OPEN ✅)** |
| 1B (full) | W9-12 | C10 Stage 1 Demo + Earn first stake + M3 partial（v5.7 baseline ✅ 移除：misnamed misnomer per PA Track 4 audit 2026-05-23；12 prefix 12/12 全 DONE via Sprint 1A-α + Wave 2/2.5 + Sprint 1A-β/γ/δ/ε/ζ + Sprint 4+/5+ chain；剩餘真實工作已被 C10/Earn/§4.1.1/operator action 吸收）| 165-220 | ⏳ (early IMPL ✅ + Wave 1 Sprint 5+ ✅) |
| 2 | W12-15 | Alpha Tournament + M4 stage 1 + M10 Tier A + M8 read-only | 280-400 | ⏳ |
| 3 | W15-18 | Top-1 Unlock SHORT build + Stage 0 shadow + M11 nightly + M3 detectors | 280-380 | ⏳ |
| **4** | **W18-21 (~2026-09 初)** | **★ Top-1 LIVE $500 first time ★** + Top-2 + Options Stack 1 + M1 LAL Tier 1 + M9 read-only | 360-490 | ⏳ |
| 5 | W21-24 | Top-2 LIVE + Top-3 + Options Stack 2 + M3 auto-degradation | 305-440 | ⏳ |
| 6 | W24-27 | Top-4 + C13-VRP + Funding short + M12 maker-vs-taker | 305-440 | ⏳ |
| 7 | W27-30 | Top-5 + Advisory Allocator + M1 Tier 2 + M6 Advisory + M9 manual A/B | 280-410 | ⏳ |
| 8 | W30-33 | Decay (M7) IMPL + M4 stage 2 + M3 recovery + M8 alerting | 360-490 | ⏳ |
| 9 | W33-36 | Continue Advisory + Copy Infra build + M12 slicing | 255-360 | ⏳ |
| 10 | W36-44 末 | Y1 Review + Copy Trading Evidence Gate + Overlay verdict + M13 spec | 190-260 | ⏳ |
| **Y1 末** | **W44-55 (~2027 Q1-Q2)** | **autonomy 66%** | – | – |
| Y2 Q1-Q2 | ~21-24 mo | 6mo Advisory + 80% approval → Auto-Allocator activation → autonomy 90% | – | – |
| Y3 Q2 | ~32 mo | M10 Tier C-E / M12 cross-venue / M13 Y3+ / M5 streaming → autonomy 95% | – | – |
| **Y1 Total** | **44-55w** | – | **3,500-5,200 hr** | – |

### §1.3 5 Strategy × Current Stage Roster

| Strategy | Current Stage | Next Stage | Sprint ETA | Notes |
|---|---|---|---|---|
| C10 funding harvest | Stage 1 Demo（Sprint 1B） | Stage 4 LIVE | Sprint 4 | Stage 0R replay-backed spot-leg accounting; no paper engine enablement |
| Unlock SHORT | Stage 0 DRAFT | Stage 0R Replay Preflight | Sprint 3 W15-18 | Tokenomist signal dep |
| Pairs trading | Stage 0 DRAFT | Stage 0 (Alpha Tournament) | Sprint 2 W12-15 | BTC/ETH cointegration |
| C13 defined-risk | Stage 0 DRAFT | Stage 0 (Alpha Tournament) | Sprint 2-6 | Bybit options demo 待驗 |
| Funding short-only | Stage 0 DRAFT | Stage 0 (Alpha Tournament) | Sprint 2-6 | high-threshold > 30% annualized |

**詳細 Strategy × Stage gate matrix**：`docs/CCAgentWorkSpace/FA/workspace/reports/2026-05-21--v57_business_consolidation.md` §6

### §1.4 Operator Action Checklist（D+0~D+6 + Sprint 4 first Live ETA）

| 日期 | Action | 預期時間 | 提醒 trigger | 卡進度後果 |
|---|---|---|---|---|
| **D+0 (2026-05-21)** | ✅ **簽 D1-D5 已完成**（v5.8 16 CRITICAL / M1→LAL / 工時上修 / M13 Y3+ / AMD-2026-05-21-01）| 30 min | done | – |
| **D+1 (2026-05-23)** | ✅ **operator OP-1 拍板 2026-05-23**：OpenClaw API key 發行日 < 2026-04-09（>45 天遠超 Bybit Earn API 14 天 scope refresh 政策）→ **必須 Bybit Web UI 手動重發 key with ≥ `asset:earn` scope**（5 min operator action）| 5 min | operator | 阻 Sprint 1B Earn Wave C production deploy |
| **D+1-D+2** | **Phase 2a 14d verdict 三選一決議**（calibration r2 / accept 35% / Phase 2b LiveDemo）— clock @ 2026-05-22~23 UTC | 30-60 min | clock 觸發 | 阻 P0-EDGE-1 closure → Sprint 4 first Live |
| **D+2-D+3** | review AMD-2026-05-21-01 草案（CC + PM draft 後；protected vs opt-in scope） | 15-30 min | CC + PM ping | 阻 CR-3 + 7 auto-apply module |
| **D+3** | 提供 P0-EDGE-1 / P0-LG-3 / P0-OPS-1..4 closure ETA（填 §10 P0 precondition table） | 30 min | PM ping | 阻 Sprint 4 first Live + CR-10 |
| **D+4** | batch review 4 ADR draft（ADR-0034 LAL / 0036 M8 anomaly / 0037 M9 A/B / 0038 M11 replay） | 30-60 min | TW + PM ping | 阻 CR-2/5/7 + V### spec |
| **D+5** | **batch sign-off 12 ADR + 1 AMD**（2026-05-22 partial: ADR-0033 3-drift patch land + ADR-0034 對齊確認 + ADR-0040 venue gate + **AMD-2026-05-21-01 → v2 Layered Autonomy with Hard-Coded Fail-Safe** + V099 schema spec + CC re-audit APPROVE A 級 → ref **§1.7**；剩 9 ADR (0030/0031/0032/0035/0036/0037/0038/0039/0041) + v2 final batch sign） | ~30 min (was 60-90 min) | PM ping | 阻 Sprint 1A-β 派發 |
| **D+5** | Console tab 歸屬決策（4 tab × 2-4 sub-section；不擴張 16 tab） | 15-30 min | A3 + PM ping | 阻 CR-11 + Sprint 4 M1 IMPL |
| **D+5** | Bybit Tokenomist trial expiry 確認（M4 dependency）+ 續訂 / fallback vendor | 5-10 min | BB ping | 阻 Sprint 6-7 M4 active |
| **D+5-D+6** | Sprint 1A-β 派發 readiness 12 check + final sign-off | 30 min | PM ping | – |

**Operator 親手時間 D+0~D+6 ≈ 3.5-5 hr**（分散 6 天，平均 30-50 min/day）；PM 每次 operator 進 session 主動 check 當天 action

### §1.5 Sprint 1A-α + Wave 2 + Wave 2.5 closure pointer

**狀態**（per 2026-05-21 acceptance audit）：
- Sprint 1A-α **DESIGN-DONE / IMPL-PENDING**（PM-signed `26ee2f06`；v5.7 12 prefix 為文件級 patch）
- Wave 2 v5.8 16 CR **DESIGN-DONE / IMPL-PENDING / RUNTIME-NOT-APPLIED**（`77d5c54e`；spec/ADR land，無 IMPL，9 V### 為 placeholder spec 非 SQL 檔）
- Wave 2.5 paperwork **DESIGN-DONE**（`957491ee`；ADR-0035/0037 補位 + 反向 ref + README 索引漂移修）
- Sprint 1A-β D+5~D+6 dispatch readiness 12-check **10/12 ✅**（剩 #8 #9 operator-bound）

**重要 caveat**（acceptance audit 揭露 + 2026-05-22 audit 更新）：sql/migrations/ 本地 max=V112（V103/V106/V107/V112 已 land per Sprint 1A-ζ Phase 2 commit `2f6d1761` + Sprint 1A-ε P1 `454f26f3`）；Linux PG **sandbox** `_sqlx_migrations` 已有 V103/V106/V107/V112；**trading_ai 主 PG `_sqlx_migrations` MAX(version)=96** — Sprint 1A V### **零 production apply**；V099/V105/V108/V109/V110/V111/V113/V114/V115/V116 共 10 條為 **spec markdown only 無 .sql**（per MIT audit 2026-05-22 紅線 1）。

**真實 IMPL 落地表（2026-05-22 audit verify）**：

| Phase | DESIGN-DONE | .sql land | sandbox apply | trading_ai apply |
|---|---|---|---|---|
| Sprint 1A-α/修補 | ✅ 12 prefix + 16 CR + 6 ADR + 1 AMD | n/a | n/a | n/a |
| Sprint 1A-β/γ | ✅ 10 module + 12 V### spec + 10 ADR/runbook | V103 only | V103 | ❌ |
| Sprint 1A-δ-IMPL | ✅ M5/M12/M13 trait stub + ADR-0035/0039/0040 | n/a (Rust only) | n/a | n/a |
| Sprint 1A-ζ | ✅ Track A/B/C 3 IMPL | **V106/V107/V112** | ✅ Round 1+2 PASS | ❌ |
| Sprint 1A-ε P1+P2 | E3 sandbox infra | n/a (PG role) | ✅ pg_hba reject 7/7 | ❌ |
| Sprint 1B early IMPL | 5 並行 Track | n/a | n/a | n/a |
| Sprint 2 pre-readiness | 4 並行 Track + E3-MED-2 | n/a | n/a (ALTER OWNER) | ALTER OWNER × 17 atomic |

所有「Sprint 1A-β/γ DONE」措辭 = **DESIGN 文件 land 級別**（V### markdown spec），**不代表** runtime ready 或 .sql 已寫。決定 2 C 路線（trading_ai PG checksum 對齊）SOP 見 `docs/execution_plan/2026-05-22--decision_2_pg_checksum_alignment_runbook.md`（待 land）。

**完整 12-check 表 + closure narrative + 反向 attack mitigation + commit chain + reference**：`docs/archive/2026-05-21--sprint_1a_alpha_repair_closure.md` §A-§F；Sprint 1A-β PM signoff narrative 在同檔 §G（無獨立 1A-β PM signoff file）

### §1.6 v5.8 Wave 2 16 CRITICAL must-fix closure pointer

**狀態**：16/16 **DESIGN-DONE** 2026-05-21（commit `77d5c54e`，spec/ADR/runbook 文件級 land；無 IMPL 代碼）+ Wave 2.5 paperwork（commit `957491ee`）；CRITICAL 合計 ~1,007-1,453 hr（est. 含未來 IMPL）/ D+0~D+5 並行 5-10 sub-agent（per 2026-05-21 acceptance audit）。

**完整 16 CR 表（Owner / 工時 / ETA）+ 統計**：`docs/archive/2026-05-21--sprint_1a_alpha_repair_closure.md` §B

### §1.7 Layered Autonomy with Hard-Coded Fail-Safe 設計 closure pointer (2026-05-22)

**狀態**：✅ **DESIGN-DONE + CC APPROVE A 級** 2026-05-22；Wave 5 cascade IMPL **PENDING operator final sign-off**

**4 個 SSOT 文件指針**（cascade IMPL 必 reference）：
1. **AMD-2026-05-21-01 v2**（684 行 / 取代 v1 protected 6 / opt-in 8 二分版）— `docs/governance_dev/amendments/2026-05-22--AMD-2026-05-21-01-autonomy-fully-with-failsafe.md`
2. **PA spec v2**（1031 行 / Autonomy Level Toggle design + 5 fail-safe hard req + readiness + AC + anti-pattern）— `docs/execution_plan/2026-05-22--autonomy_level_toggle_design_spec.md`
3. **V099 schema spec**（568 行 / `system.autonomy_level_config` + `_switch_audit` + PG ENUM `autonomy_level_enum`）— `docs/execution_plan/specs/2026-05-22--v099-autonomy-level-config.md`
4. **CC re-audit report**（A 級 / 7/7 HC PASS + 6/6 反模式 PASS + 2 BLOCKER 候選解除）— `docs/CCAgentWorkSpace/CC/workspace/reports/2026-05-22--layered_autonomy_v2_reaudit.md`

**設計核心拍板**（per operator 2026-05-22 + PA + CC verdict）：
- **命名**：Layered Autonomy with Hard-Coded Fail-Safe（解 CC 反模式 F「fully autonomy 命名誤讀」）
- **Autonomy Level Toggle**：Level 1 Conservative (預設 / protected 6 條 manual + opt-in 8 條 auto) ↔ Level 2 Standard (venue change manual + 13 條 auto)；切換需 5-gate + 2FA + 24h cooldown
- **CLAUDE.md baseline**：字面不動，amendment 並存（不 cascade re-read 14 agent profile）
- **三路通知 fail escalation**：freeze + 1h wait → 自動進入 SM-04 `Defensive`（保住盈利 + 停止損失 + close-only + active 鎖利 hook + 縮 SL 至 entry）；reuse `Defensive` 不新增 enum（per PA 拍）
- **Emergency override 月度**：rolling 30d + machine local time + 雙時間戳（local + UTC）；30% 達標 → active freeze 24h + monthly review 混合
- **Cache invalidation**：PG LISTEN/NOTIFY 主路徑 + polling 5s fallback（per PA 拍）
- **Level 2 啟用 gate**：GUI toggle disabled until 21d demo 穩定期 + 5 textbook 策略 N≥30 + Wilson CI 95% lower bound 正向（per FA U-FA-1；當前 4/5 達標，funding_arb dormant；Wilson CI 正向待 P0-EDGE-1 Phase B/C/D + A 群 alpha source）
- **Fail-safe 復原 cooling**：7d（per operator 拍；非 ADR-0044 demote pattern 30d 對齊，fail-safe escalation 性質不同）
- **新增 Rust variant**：`RiskEvent::NotificationFailsafeTimeout`（per AMD §9.8 cascade；需 PA + E1 + E4 三方 review 避免 35+ pair transition rules unhandled match arm panic）

**Wave 5 cascade IMPL roadmap**（PENDING operator final sign-off 後派發）：
1. **V099 schema land** — E1 + MIT Linux PG empirical dry-run 13 條（~ 8-12 hr）
2. **GUI Autonomy Posture sub-section** — E1a (tab-governance.html / Vanilla JS / 'CONFIRM SWITCH' typed-confirm / 14 path × 2 level panel / 5-gate flow / BroadcastChannel cross-tab) ~ 21-28 hr（per A3 估時，含 i18n + a11y + 防誤觸 8 anti-pattern）
3. **Rust SM-04 patch** — `RiskEvent::NotificationFailsafeTimeout` 新 variant + active 鎖利 hook 擴充 + 35+ pair transition rules verify（~ 52-86 hr per AMD §9.8）
4. **5 module ADR sync** — ADR-0034 (LAL 對齊矩陣加 Autonomy Level 維度) + ADR-0040 (§Decision 5 venue manual 對齊 + 3 drift patch 已 land 2026-05-22) + ADR-0042/0044/0045 wording 對齊
5. **R4 cross-ref audit** — Wave 5 完成後

**Wave 1-4 沿途完成的副產品**：
- ADR-0040 3 drift patch land 2026-05-22（liquidation hunting / BinanceSpotMarketData / sign-off chain note）— 257→259 行
- m13 asset_class spec wording sync land 2026-05-22（line 32 + 358）
- Phase 2a 三選一 → ✅ 拍 (a) Calibration r2 — QC report `docs/CCAgentWorkSpace/QC/workspace/reports/2026-05-21--phase2a_verdict_3option_data.md`

**Wave 流程紀錄**（completed sub-agent）：
- Wave 1 TW drift patch ✅ / QC Phase 2a 摘要 ✅
- Wave 2 TW v2 patch ✅ / CC preview 7 HC + 6 反模式 ✅ / PM v2 draft 580 行 ✅
- Wave 2 round 2 A3 + MIT + FA + E2 並行 ✅（E2 BLOCK 5 大類補丁送回 PA）
- Wave 3a PA 補丁 648→1031 (+383 / +59%) ✅（SM-04 reuse Defensive + LISTEN/NOTIFY 拍）
- Wave 3b TW sync v2 + V099 spec 兩 file ✅（10 條 wording sync TODO 全綠）
- Wave 4 CC re-audit ✅ **APPROVE A 級**

---

## §2 架構邊界 + 硬不變式（cross-ref CLAUDE.md）

- **產品**：玄衡 · Arcane Equilibrium；交易所目標僅 Bybit（per ADR-0033 amendment：Binance market data only / DEX 不允）
- **權威分工**：Rust `openclaw_engine` = 交易/風控/策略 config/執行；Python = control plane/GUI/bridge/replay/5-Agent host
- **GUI**：FastAPI console `trade-core:8000/console`（Vanilla JS）；外部 OpenClaw Gateway 僅通訊/mobile/supervisor
- **5-Agent runtime**：Scout / Strategist / Guardian / Analyst / Executor；Cloud L2 走 supervisor escalation + budget/model config + `agent.ai_invocations` ledger
- **權威 agent lineage**：StrategySignal → StrategistDecision → GuardianVerdict → ExecutionPlan → Decision Lease/idempotency → ExecutionReport
- **Graduated Canary**（AMD-2026-05-15-01）：Stage 0 shadow → Stage 0R Replay Preflight → Stage 1 Demo micro-canary 7d → Stage 2 demo 14d → Stage 3 demo 21d → Stage 4 LIVE_PENDING
- **5-gate live**：Python `live_reserved` + Operator role auth + `OPENCLAW_ALLOW_MAINNET=1` + secret slot + signed unexpired `authorization.json`
- **DOC-08 §12 9 條安全不變量** + **SM-04 ladder** + **CLAUDE.md §二 16 原則** 強制 binary fail-closed，不被 graduated canary 觸碰
- **新增（v5.8）**：M1 LAL（Layered Approval Lease 0-4 Tier）/ M4 self-supervised DRAFT writeback / M2 overlay state machine — 全部走 5-gate 不繞 governance

---

## §3 Runtime Evidence

- **Phase 2a 14d obs verdict 視窗**：2026-05-22~23 UTC；QA D1 T+72h projection AC-1/2/4 FAIL → operator 三選一決議
- **LG-1 P0 DONE 2026-05-21 PASS WITH 1 KNOWN GAP**：H0 wired 18M+ ticks；fail-closed never fired 5h；衍生 `P2-LG1-DEMO-SLO-CARVEOUT`（已 closure 2026-05-21 commit `aa0780a3`）
- **LG-2 P0 DONE 2026-05-21 PASS WITH 1 CAVEAT**：startup assertion fire；production tick path 0 caller for `fee_source()` BY-DESIGN per spec §2.4
- **v56 P0 HALT cycle CLOSED 2026-05-20**：root cause UNRESOLVED → `P1-HALT-TRIGGER-ROOT-CAUSE-INVESTIGATION-1`（passive wait + H4 healthcheck [69] LIVE 2026-05-21）
- **D2 watchdog classifier R2 SOURCE LAND 2026-05-21**：4-gate + AMBIGUOUS_SOURCE_PATTERNS guard；207/207 PASS；deploy 等 operator 決定 daemon 重啟
- **stale signal**：`learning.edge_estimate_snapshots` 14d 內 0 rows（max=2026-05-07）→ 併入 P0-EDGE-1

---

## §4 P0 — True-Live Blockers（active only）

| ID | 狀態 | Owner | Acceptance Criteria | Next Action |
|---|---|---|---|---|
| `P0-EDGE-1` | 🔴 ACTIVE | QC + PA | **AC-A**: 5 textbook 策略 ≥ 3 個 demo 7d avg_net > 5bps（Wilson CI lower > 0），n ≥ 30 per-strategy<br>**AC-B**: portfolio gross daily PnL 7d MA > 0 USDT<br>**AC-C**: 若全策略 7d EV < 0，supervised path = 凍結至 alpha 修補有 demo 證據 | Sprint 2 Alpha Tournament（W12-15）+ 併入 `learning.edge_estimate_snapshots` stale follow-up |
| `P0-LG-3` | ⚠️ SPEC READY 10d, IMPL DISPATCH PENDING | PA spec → E1×7 | **AC-A**: spec v2 §2.4A 加 fee_source tick-time consumer scope<br>**AC-B**: DISPATCH 拍板條件 = operator 路線決議 OR 90d stale-detect 強制 IMPL<br>**AC-C**: V099/V100 migration Linux PG empirical dry-run mandatory | PA refresh dispatch plan；待 operator 拍板 |
| `P0-OPS-1..4` | 🔴 ACTIVE | PA + BB + E3 | **OPS-1**: HTTPS certbot + 4 service binding<br>**OPS-2**: credential rotation TTL + script<br>**OPS-3**: legal+ToS spec（Bybit ToS / KYC / 地理）<br>**OPS-4**: 第一天 30min runbook | 4 子項各自 owner；OPS-1 → OPS-2 序列 |

**Sprint 4 first Live W18-21 必前置條件**：P0-EDGE-1 + P0-LG-3 + P0-OPS-1..4 全 closure（per FA v5.8 §1.4 + PM verdict §六 風險點 #6）

---

## §5 P1 / P2 / P3 — Engineering Queue + Backlog

### §5.1 P1 Active Engineering Queue（v5.7 baseline + v5.8 新增）

| ID | 優先 | 任務 | AC / Next Action |
|---|---:|---|---|
| `P1-V107-SQL-GUARD-A-LOGIC-DRIFT` | – | ✅ **CLOSED 2026-05-22** by 隔壁 commit `c706c49c` (`fix(v107-guard-a): P1 runtime logic drift CLOSED — governance.audit_log → learning.governance_audit_log`) — sandbox empirical Round 1+2 PASS per Sprint 1B early IMPL Track C ✅ |
| `P1-PG-CHECKSUM-ALIGNMENT-DECISION-2-C` | 1 | ✅ **CLOSED-VERIFY 2026-05-24 for current landed SQL set** — trade-core `trading_ai` 主 PG `_sqlx_migrations` max=112 / count=102；V100/V101/V102/V103/V106/V107/V112 success=true；7/7 target tables present；V106 6 active domain 30m empirical PASS。Remaining V099/V104/V105/V108-V116 are design/spec or later migration work, not current checksum drift. Evidence: `docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-24--sprint_1a_1b_completion_audit.md` |
| `P1-SANDBOX-SQLX-METADATA-ALIGNMENT` | – | ✅ **FULLY CLOSED 2026-05-24** — Round 1 (2026-05-22) sandbox INSERT 4 row 用錯 sha384 algorithm（sqlx V100+ 切換 sha256，V083-V098 仍 sha384，切換點 V099/V100；本 session verify trading_ai V083-V098 length=48 bytes / V100-V112 length=32 bytes）；Round 2 (2026-05-24 by PM session) UPDATE V106/V107/V112 checksum 從 sha384→sha256 對齊 trading_ai 主 DB 真實 sha256（V103 sha256 已被隔壁正常 sqlx 流程覆蓋）；4 row length 全 32 bytes / sha256 100% 對齊 file content；ref decision_2_pg_checksum_alignment_runbook.md Step 3 alt 路徑 |
| `P1-ENGINE-BINARY-SPRINT-1A-IMPL-DEPLOY` | 2 | **ACTIVE / narrowed 2026-05-24** — Linux source HEAD `c2fc1d8b` and PG V100/V103/V106/V107/V112 are landed, but running engine PID 4105805 uses binary mtime 2026-05-23 17:56+0200, before C10/Earn commits `255a83f6`/`875de212`/`5e95edfe`; `strings` hits `funding_harvest`=0, `EarnStake`=0, `LAL_0_AUTO`=0, `replay_divergence_log`=0, `health_observations`=1. Acceptance: after E2/E4/QA closures, rebuild+restart on trade-core, verify binary strings/symbols + watchdog + targeted C10/Earn health. Blocks C10 Stage 1 Demo runtime and Earn Wave C production deploy; do not promote live/first stake on current binary. |
| `P1-C10-SYNTHETIC-SPOT-CLOSE-PNL-FALLBACK` | – | ✅ **SOURCE-LAYER CLOSED 2026-05-25 (IMPL)** — Round 1 (E1 sub-agent `a83b8b53` inline return): Strategy trait `on_close_confirmed(symbol, close_price, close_ts_ms)` + `on_external_close(...)` 簽名升級 / 5 既有 strategy override migrate / funding_harvest 真實 PnL / 2 callsite 傳 close fill price / 4 new test (entry baseline / +5% / -5% / drift gate sanity 反證 PnL=0 觸發 100% drift). Round 2 (E1 sub-agent `a21934cf` inline return, 修 E2 4-5 finding): fallback chain `latest_price → entry_price → entry_price_snap` step_4_5_dispatch.rs:1662 / step_6_risk_checks.rs:603-605 對稱. E2 round 2 verify (sub-agent `a015830b` inline return — 未寫盤): APPROVE 全 9 finding closed. E4 round 2 verify (sub-agent `a314d88a` inline return — 未寫盤): PASS 4135/1/5 三遍 non-flaky. Source land commit `015b9735`. **⚠️ 注意**: sub-agent ID 非 git commit SHA；E2/E4 round 2 inline return 未寫 .md 報告（workspace 無 file 痕跡）。**Stage 0R drift gate 不再結構性永真**；待 PA spec amend (round 3 sub-agent IMPL 中) + QA Stage 0R replay + PM Phase 3e + Linux engine binary deploy. ref `docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-24--sprint_1b_audit_bug1_bug2_combined_impl.md` + `2026-05-24--sprint_1b_audit_round2_impl.md` |
| `P1-INTENTTYPE-DIRECTION-MISMATCH` | – | ✅ **SOURCE-LAYER CLOSED 2026-05-25** — Round 1: `OrderIntent::new_trade(symbol, is_long, qty, strategy)` helper land + 8 strategy emit site 改 (funding_arb / funding_harvest / bb_breakout / bb_reversion / ma_crossover / grid_trading × 2) + `validate()` debug_assert. Round 2 (修 E2 finding 1/2/3 + 6/7/8): helper 真為唯一 trade-path 建構器 (grep 0 production inline literal 殘留) / `tick_pipeline/commands.rs:202-214` submit_external_order 改 new_trade 派生 / `on_tick_helpers.rs:190-194` build_intent if is_long 派生 / `mod.rs:329-341` release path warn telemetry fail-soft / 3 fixture 注釋對齊 + funding_arb.rs:1164 test fixture 改 new_trade(false, ...). E2 round 2 inline verify APPROVE / E4 round 2 inline verify PASS 4135/1/5. **Sprint 2 Wave 1 router.rs:100 wire-up unblock**; **non-blocking follow-up DEFER 下個 sprint** (per 2026-05-25 cross-crate verify): OrderIntent struct field `pub` → `pub(crate)` 影響 4 integration test struct literal + openclaw_types crate re-export + IPC serde；屬重構非 cosmetic visibility 修；需 PA builder pattern spec + E1 IMPL ~4-6 hr. ref `2026-05-24--sprint_1b_audit_round2_impl.md` |
| `W-S4-AC1B-HEALTHCHECK` | 2 | ✅ **CLOSED-VERIFY 2026-05-24** — trade-core SQL 30m: `api_latency` 240 / `database_pool` 150 / `engine_runtime` 360 / `pipeline_throughput` 300 / `risk_envelope` 30 / `strategy_quality` 756; watchdog `engine_alive=true`. Evidence: `docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-24--sprint_1a_1b_completion_audit.md` |
| `P1-SPRINT-1B-C10-CLOSURE-GAPS` | 2 | **ACTIVE** — C10 source + replay harness tests pass, but Stage 1 Demo is not PM-closeable until E2+V108/E4/QA acceptance resolves (a) synthetic spot close PnL currently uses `entry_price` fallback because Strategy trait has no close price, and (b) runtime binary lacks `funding_harvest`. Next: E2 decide trait extension vs explicit replay-only accounting scope; E1 patch/test if needed; E4 regression; QA Stage 0R acceptance. |
| `P1-INTENTTYPE-DIRECTION-MISMATCH` | 2 | **ACTIVE** — short-capable strategies can emit `OrderIntent { is_long: false, intent_type: OpenLong }`; current execution direction still follows `is_long`, but future LeaseScope/IntentProcessor routing will consume `intent_type`. Next: central helper or per-strategy patch deriving `OpenShort` when `is_long=false`, with targeted tests before Earn B6 branch. |
| `P1-EARN-WAVE-C-FIRST-STAKE-RUNTIME` | 2 | **ACTIVE / OPERATOR-BLOCKED** — Earn SPEC-FINAL + Wave B source tests pass, but no IntentProcessor Earn branch, no OP-1 refreshed Bybit key with `asset:earn`, running binary lacks `EarnStake`, and `learning.earn_movement_log` rows=0. Next: operator OP-1 key refresh → B6 branch + Stage 0R Earn variant → rebuild/deploy → first stake $100-200 Flexible-only. |
| `P1-EDGE-2` (funding_arb) | 3 | ⚠️ PA D3 建議升 P0-FUNDING-ARB-DECISION-FORCE 待 operator 拍板 | operator 選項 (A) 砍策略 / (B) 增樣本 / (C) 接受 INSUFFICIENT；缺 deadline |
| `P1-LG-5` | 4 | LG-5 reviewer maturity watch — STILL_ACTIVE | source 活躍；7d 共 66 review_live_candidate 全 verdict=defer；建議 90d cadence + 3 not-defer 或 180d 都 defer 觸發 review |
| `P1-HALT-TRIGGER-ROOT-CAUSE-INVESTIGATION-1` | 3 | v56 P0 未解 root cause；H4 healthcheck [69] LIVE → passive-wait 合規 | forensic `halt_audit.log` armed；passive wait + 90d review 2026-08-21 |
| `P1-LEASE-1` | 3 | 升 P1 from P2：清掃 terminal `lease.rs:303` + HashMap leak | 依賴 P0-LG-3 IMPL DISPATCH；工時 ~4-6h |
| `P1-EDGE-P2-3-PH1B-DYNAMIC-BACKOFF-FOLLOWUP` | 4 | Phase 1b spec §5.4 完整 dynamic backoff state machine | Phase 2a Demo PASS 後另開 PR；PA 估 ~130 LOC |

### §5.1.1 v5.8 24 H 級 ticket（按 module 分組；派發後 Sprint 1A-β-ε 期間並行補）

- **M2 Stage gate**：H-1 對齊 AMD-2026-05-15-01 / H-2 M6 Bayesian spec / H-3 M7 baseline calibration
- **M4-M8-M11**：H-4 M8 autoencoder Y2 spec / H-5 M9 variant Stage 路徑 / H-17 M9 framework validation + M4 leakage scan
- **M10-M12-M13**：H-6 M10 AUM trigger 數據源 / H-7 M5/M12/M13 trait slot
- **mutex**：H-8 M3/M8/M11 trigger mutual exclusion contract
- **missing module**：H-9 M14/M15/M16 處置（已決議 §5.2）
- **threshold**：H-10 M1/M3/M11 量化 threshold
- **forgetfulness attack**：H-11 §11 反向 attack 6 條
- **灰度事件**：H-12 嚴重度對照表
- **IPC + state machine test**：H-13 Rust IPC message type / H-14 state machine 4 SM proptest
- **migration + SLA**：H-15 V### dry-run / H-16 SLA stress 5 hot path
- **cross-language + sibling file**：H-18 1e-4 fixture harness / H-19 13 module sibling file structure
- **CI + secret slot**：H-20 Apple Silicon CI 13 module / H-21 external secret slot policy
- **docs + tokenomist**：H-22 docs/README.md index 補 / H-23 TODO §0.5 refactor 已 done v61 / H-24 M4 Tokenomist trial expiry

### §5.2 3 missing module 處置（PM 仲裁，operator D1 採納）

| ID | 描述 | 處置 |
|---|---|---|
| **M14** | strategy hot-swap（不重啟 engine） | **defer v5.9**（Sprint 4 後 90d 才需）|
| **M15** | capacity-aware sizing（depth/liquidity 感知） | **擴 M6 acceptance 第 4 條**「orderbook depth bounds」，不新建 module |
| **M16** | cross-strategy correlation re-sizing | **擴 M1/LAL acceptance**「correlation-adjusted weight」，不新建 module |

### §5.3 W-AUDIT-4b retained invariant 19 — observe only

5 項 observe-only retained INSERT/VIEW/DROP；詳見 archive §B：`docs/archive/2026-05-21--todo_v60_archive.md`

### §5.4 P2/P3 Deferred / Passive Wait

| ID | 狀態 | 觸發 / Deadline |
|---|---|---|
| `P1-OBS-PLACEMENT-BBO-V094` | DEFER | Phase 1b 14d freeze 後（~2026-06-01）|
| `P1-SWEEP-A-AXIS-PRUNE` | DEFER | 下輪 sweep（Phase 2a verdict 後）|
| `P1-WATCHDOG-NETOUTAGE-SPARSE-LOG-OQ` | DEFER | 觀察 canary NETWORK_OUTAGE event 頻率 |
| `P2-CLIPPY-CLEANUP-1` | ACTIVE | Sprint 1A 進行中並行清；E1 4-6 hr |
| `P2-FALLBACK-DEAD-ENUM-90D-AUDIT` | PASSIVE WAIT | 2026-08-21（ADR-0028 90d cadence）|
| `P2-AUDIT-DEAD-CODE` | DORMANT | D-16；Sprint N+6+ |
| `P2-WP05-CSP-UNSAFE-INLINE` | DEFER | live-gate 前升 P1 |
| `P2-CANARY-FILE-SIZE-REFACTOR` | P5 DEFER | 等 800 LOC bulk wave |
| `P3-H0GATE-FILE-SPLIT` | DEFER | 獨立 wave；h0_gate.rs 1243 行 > 800 |
| `P3-H0-LATENCY-1H-RESET-INTEGRATION-TEST` | LOW NTH | 既有 unit test 覆蓋 reset；缺 1h cadence integration |

---

## §6 Dormant + Passive Wait

| ID | 描述 | 原因 | 最早重啟 |
|---|---|---|---|
| `D-13` | Cognitive Modulator | 3-Tier 數據源未接齊 + alpha 無依賴 | Sprint N+8+ |
| `D-14` | DreamEngine 完整自主進化 | Foundation Model + L4 跨策略 meta-learning 未 ready | long-tail |
| `D-15` | OpportunityTracker 全 Agent 注入 | 不影響 supervised live | Sprint N+5 可選 |
| `D-16` | openclaw_core 9 模組 sunset cleanup | 7 已清；餘 2 待 PA | Sprint N+6+ |
| `D-17` | Layer 2 自主推理循環自動觸發 | **PERMANENT DORMANT** by ADR-0020 manual+supervisor-only | **不解** |
| `D-02` | Layer 2 手動 7d 試運行 SOP | Operator 自執行 | operator 觸發 |

**FA constraint**：靜默漏寫 = 6 個月後 lobby 重新 review；explicit 標 dormant + reason + earliest reactivate

---

## §7 排程 + Milestone

| 日期 / Sprint | 工作 | Gate |
|---|---|---|
| **D+0 ~ D+5 (2026-05-21~26)** | v5.8 16 CRITICAL 並行修補 | Sprint 1A-β readiness 12-check |
| **D+5~D+6 (2026-05-26~27)** | Sprint 1A-β 派發 PA + 5-7 並行 sub-agent | 12-check ✓ |
| **2026-05-22~23 UTC** | Phase 2a 14d verdict 視窗 | operator 三選一 |
| 2026-06-01 | `P1-OBS-PLACEMENT-BBO-V094` + `P1-SWEEP-A-AXIS-PRUNE` 可啟動 | Phase 2a freeze |
| 2026-06-09 | `P1-CONDITIONAL-WATCH` TONUSDT 30d evidence freeze | QC 2026-05-11 zero-cost action #4 |
| **W18-21 (~2026-09 初)** | **Sprint 4 first Live $500** | P0-EDGE-1 + LG-3 + OPS-1..4 全 closure |
| 2026-08-21 | `P2-FALLBACK-DEAD-ENUM-90D-AUDIT` + `P1-HALT-TRIGGER` review | 90d cadence |
| **W44-55 (~2027 Q1-Q2)** | **Y1 末 — autonomy 66%** | Copy Trading evidence gate / Overlay verdict |
| **~21-24 mo** | **Y2 Q2 Auto-Allocator activation — autonomy 90%** | 6mo Advisory + >80% approval |
| **~32 mo** | **Y3 Q2 — autonomy 95%** | M10 Tier C-E / M12 / M13 Y3+ |

---

## §8 跨 Wave 衝突仲裁

| # | 衝突 | 解 |
|---|---|---|
| 1 | LG-3 IMPL DISPATCH ↔ P0-FUNDING-ARB-DECISION-FORCE | 若 operator 選 (A) 砍 funding_arb，LG-3 cohort 4；**operator 拍板前 LG-3 IMPL DISPATCH 不可派** |
| 2 | Phase 2a engine STOPPED ↔ verdict 視窗 累積 | 每暫停 1h 失 ~0.4 rows；後續禁無預警 stop |
| 3 | W-AUDIT-9 graduated canary path ↔ ExecutorAgent shadow_mode | per AMD-2026-05-15-01：Stage 0R replay preflight + Stage 1 demo；ExecutorAgent shadow=true 至 Stage 0R PASS |
| 4 | A 群策略候選 ↔ Stage 1 Demo cohort | RESOLVED 2026-05-16：Stage 1 為 Demo-only；A4-C tombstoned 不可作 cohort 來源 |
| 5 | v5.8 Sprint 1A-β/γ/δ 順序 dispatch ↔ cross-V### dependency | per `v58-CR-9` PG dry-run + cross-V### dependency graph；β/γ 不能無條件並行 |

---

## §9 派工規則 + Handoff SOP

詳見 `docs/agents/todo-maintenance.md` + `CLAUDE.md` §八。簡明條款：

- **實作鏈**：`PM → PA → E1/E1a → E2 → E4 → QA → PM`
- **安全 / 部署 / runtime**：`PM → E3 → BB（若涉交易所）→ PM`
- **量化 / 資料**：`PM → QC → MIT → AI-E（若涉模型成本）→ PM`
- **Sign-off SOP**：`cargo test -p openclaw_engine --release`（覆蓋 tests/ integration crate）
- **GUI JS 變動**：sign-off 強制 `node --check`
- **V### migration**：Linux PG empirical dry-run mandatory before IMPL sign-off
- **Meta-doc 改動**：dirty trees 用 `git commit --only <files>` 隔離 race
- **每 green checkpoint**：commit subject + body，push origin，再 ssh trade-core fast-forward；doc-only commits 加 `[skip ci]`

```bash
# Handoff 檢查
git -C /Users/ncyu/Projects/TradeBot/srv status --short --branch
ssh trade-core "cd ~/BybitOpenClaw/srv && git status --short --branch"
ssh trade-core "python3 helper_scripts/canary/engine_watchdog.py --data-dir /tmp/openclaw --status"
ssh trade-core "cd ~/BybitOpenClaw/srv && bash helper_scripts/db/passive_wait_healthcheck.sh --quiet"
```

---

## §10 References（active only）

### v5.7 + v5.8 主檔 + dispatch
- v5.7 主檔：`docs/execution_plan/2026-05-20--execution-plan-v5.7.md`
- v5.8 主檔：`docs/execution_plan/2026-05-20--execution-plan-v5.8.md`
- v5.7 Sprint 1A dispatch packet：`docs/execution_plan/2026-05-21--sprint_1a_dispatch_packet.md`
- V103/V104 schema spec：`docs/execution_plan/2026-05-21--v103_v104_earn_hypotheses_schema_spec.md`
- V103/V104 PG dry-run：`docs/execution_plan/2026-05-21--v103_v104_linux_pg_dry_run.md`
- Earn governance spec：`docs/execution_plan/2026-05-21--earn_governance_spec.md`

### v5.7 + v5.8 整合 + verdict
- PM 最終 verdict v5.8 主入口：`docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-21--v58_pm_final_verdict.md`
- PM autonomy verdict v5.7：`docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-21--v57_autonomy_verdict.md`
- PM v5.7 12-prefix signoff：`docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-21--v57_12_prefix_pm_signoff.md`
- PA v5.7+v5.8 dispatch consolidation：`docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-21--v58_dispatch_consolidation.md`（562 行）
- PA v5.7 dispatch consolidation：`docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-21--v57_dispatch_consolidation.md`
- PA v5.7 12-prefix tech verify：`docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-21--v57_12_prefix_tech_verify.md`
- FA v5.7 business consolidation（含 5 strategy×Stage matrix §6 + 資金路徑流圖 §7）：`docs/CCAgentWorkSpace/FA/workspace/reports/2026-05-21--v57_business_consolidation.md`
- FA v5.8 executability audit（含 13-module business acceptance §0.6）：`docs/CCAgentWorkSpace/FA/workspace/reports/2026-05-21--v58_executability_audit.md`
- FA v5.7 12-prefix business verify：`docs/CCAgentWorkSpace/FA/workspace/reports/2026-05-21--v57_12_prefix_business_verify.md`

### v5.8 14 multi-agent audit
- A3 / AI-E / BB / CC / E2 / E3 / E4 / E5 / FA / MIT / QA / QC / R4 / TW：`docs/CCAgentWorkSpace/{ROLE}/workspace/reports/2026-05-21--v58_executability_audit.md`

### Active ADR / AMD
- ADR-0006 (Bybit-only) + ADR-0033 (Binance amendment)
- ADR-0015 openclaw_core sunset
- ADR-0017 scanner authority retirement / ADR-0018 funding_arb retire
- ADR-0020 Layer 2 manual+supervisor-only
- ADR-0022 strategist cap / ADR-0023 SourceAvailability schema / ADR-0024 Cowork operator-assistant
- ADR-0028 close-maker-fallback dead enum reservation（90d audit 2026-08-21）
- ADR-0029 market.public_trades + orderbook_l2_snapshot storage policy（Proposed）
- ADR-0030 Copy Trading evidence-gated（已 LAND；非 Earn）/ ADR-0031 Macro counterfactual / ADR-0032 Bybit Earn governance（Earn governance spec 為其執行細則；2026-05-23 SPEC-FINAL）
- ADR-0034 M1 LAL（Layered Approval Lease，v5.8 NEW）✅ DONE 2026-05-21
- ADR-0035 M5 online learning interface reserved (Y3+) ✅ DONE 2026-05-21
- ADR-0036 M8 anomaly detection + M10 Tier D blacklist ✅ DONE 2026-05-21
- ADR-0037 M9 A/B framework + statistical methodology ✅ DONE 2026-05-21
- ADR-0038 M11 continuous counterfactual replay ✅ DONE 2026-05-21
- ADR-0039 M12 order router trait + maker fill rate ✅ DONE 2026-05-21
- ADR-0040 multi-venue gate spec ✅ DONE 2026-05-21
- ADR-0041 ContextDistiller v4 + AI cost cap amendment ✅ DONE 2026-05-21
- AMD-2026-05-15-01（Canary Rebase Replay Preflight + Demo Micro-Canary）
- AMD-2026-05-15-02 v0.7（EDGE-P2-3 Phase 1b + Runtime Activation Layer）
- **AMD-2026-05-21-01-autonomy-vs-human-final-review — CC+PM draft pending D+2**

### Active spec
- LG-3 spec v2 final：`docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-11--lg_3_spec_v2_final.md`
- EDGE-P2-3 Phase 1b spec v1.4：`docs/execution_plan/2026-05-15--edge_p2_3_phase_1b_close_maker_first_spec.md`
- V094 hybrid schema migration spec：`docs/execution_plan/2026-05-15--v094_close_maker_first_audit_schema_spec.md`

### Bybit / API
- `docs/references/2026-04-04--bybit_api_reference.md`
- `docs/audits/2026-04-04--bybit_api_infra_audit.md`
- BB v57 C4/C5/C6 verdict：`docs/CCAgentWorkSpace/BB/workspace/reports/2026-05-21--v57_c4_c5_c6_bybit_verdict.md`

### Recent 2026-05-21 audit reports (active)
- QA D1: `docs/CCAgentWorkSpace/QA/workspace/reports/2026-05-21--lg1_lg2_7d_closure_phase2a_t72h_verify.md`
- PA D3: `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-21--p1_data_lg5_edge_status_reverify.md`
- E5 F1: `docs/CCAgentWorkSpace/E5/workspace/reports/2026-05-21--p1_lg1_demo_sla_violation_hotpath_audit.md`
- FA G2: `docs/CCAgentWorkSpace/FA/workspace/reports/2026-05-21--todo_business_chain_audit.md`
- PA v61 restructure proposal：`docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-21--todo_v61_restructure_proposal.md`
- FA v61 restructure proposal：`docs/CCAgentWorkSpace/FA/workspace/reports/2026-05-21--todo_v61_restructure_proposal.md`

### Archive index
- v55 翻譯歸檔：`docs/archive/2026-05-19--todo_v55_translation_archive.md`
- v57.3 closure cleanup：`docs/archive/2026-05-20--todo_v57_3_closure_cleanup_archive.md`
- v57.5 route change purge：`docs/archive/2026-05-21--todo_v57_5_route_change_purge.md`
- v58 layout refactor：`docs/archive/2026-05-21--todo_v58_layout_refactor_archive.md`
- **v60 重構歸檔（v5.7 12 prefix DONE + W-AUDIT-4b + H+I 批 closure + 9 批 narrative）**：`docs/archive/2026-05-21--todo_v60_archive.md`

### Operator commit
- v5.8 主檔 + 14 audit + PA consolidation + PM verdict + TODO §0.6：commit `f37cb62b` (2026-05-21)

---

## §-1 歷史 closure 摘要（≤ 14d）

- **2026-05-24 PM audit**：Sprint 1A→1B **not full runtime complete**；trade-core PG current landed SQL set PASS and 6 health domain live, but running engine binary predates C10/Earn and lacks `funding_harvest`/`EarnStake`/`LAL_0_AUTO`; C10/Earn remain closure/deploy/operator-blocked. Report: `docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-24--sprint_1a_1b_completion_audit.md`
- **2026-05-23 closure summary**：Sprint 4+ first Live carry-over §4.1（4 items）+ Stage A→F + Sprint 5+ Wave 1 全鏈 **ALL CLOSED**（19 commit chain `011fd5f9 → 22a07294`）；3 governance NEW (PA-DRIFT-6/7/8) land；Sprint 1B Earn first stake **SPEC-FINAL** (operator OP-4 ✅ APPROVE, HEAD `5e95edfe`)；C10 funding harvest Wave A+B IMPL DONE；runtime later corrected by 2026-05-24 audit: API PID 3989463 / engine PID 4105805；6 active domain × 30 min × 1836 row PG empirical PASS — 詳情：`docs/archive/2026-05-23--sprint_4plus_5plus_wave1_closure.md`
- **2026-05-21 closure summary**：v5.7 12 prefix **DESIGN-DONE / IMPL-PENDING** PM SIGN-OFF（archive §A）/ v5.8 13-module audit 14 agent + PA + PM verdict（DESIGN-only）/ Sprint 1A-β 16 artifact **DESIGN-DONE / IMPL-PENDING / RUNTIME-NOT-APPLIED**（archive §G）/ TODO v60 → v61 重構（本檔）+ H+I 批 P2/P3 closure（archive §C）/ 過去 14d 9 批 closure narrative（archive §D）— per 2026-05-21 acceptance audit (Linux PG max_version=96, 10 target tables pg_class 0 hits, V099+ migration .sql 本地不存在)
- **Incident marker 2026-05-21**：09:58 UTC engine + watchdog SIGTERM graceful stop；13:31 UTC PM restart_all.sh --keep-auth 恢復；Phase 2a sample velocity gap ~3.5h；verdict 視窗影響 low

**詳細歷史**：`docs/archive/2026-05-23--sprint_4plus_5plus_wave1_closure.md`（Sprint 4+ §4.1 + Stage A→F + Sprint 5+ Wave 1 完整 narrative）+ `docs/archive/2026-05-21--todo_v60_archive.md`（§A-§F 完整 narrative）

---

**Maintenance contract**：依 `docs/agents/todo-maintenance.md` 將本檔保持為活躍派工佇列。穩定專案脈絡走 `README.md`；agent 操作規則走 `CLAUDE.md`；歷史 closure 走 `docs/archive/`。
