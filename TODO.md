# 玄衡 TODO — 活躍派工佇列

**版本**：v67（v66 + 2026-05-26 §1 4 P0 並行推進 + funding_arb (D) deprecation closure + LG-3 AC drift correction）
**日期**：2026-05-26
**HEAD**：cf61d1f0（Mac / origin / trade-core 三端同步 2026-05-25；v67 待 commit + push + ssh fast-forward）
**Session**：§1 4 P0 sub-agent fan-out — PA OPS-1+OPS-4 / E3 OPS-2 / BB OPS-3 / PA LG-3 verify + EDGE-1 SSH empirical + operator funding_arb decision
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

**三端 sync**：Mac / origin/main / Linux trade-core 全 HEAD `cf61d1f0`（2026-05-25 22:43 UTC + 23:00 ssh pull --ff-only）

**Runtime snapshot**（2026-05-25 SSH verify per V1→V5.8 closure）：
- Engine PID 374287 alive；SHA `b005bb00...` 與 disk matched；`/proc/374287/exe` 非 deleted；env count 13 含 `OPENCLAW_ALLOW_MAINNET=1` ✅
- API PID 320486 bind `100.91.109.86:8000`（Tailscale IPv4）；`/api/v1/healthz` HTTP 200
- Watchdog PID 2936560 running；`engine_alive=true` paper/demo/live；tick 27M+
- PG `_sqlx_migrations` max=112 / count=102；V100/V101/V102/V103/V106/V107/V112 success=true；7/7 target table 物理 land
- `risk_verdicts` hypertable 15 chunks / 9.35M rows；retention 30d + compression 7d（V075 active）
- `learning.earn_movement_log` rows=0（OP-1 operator-blocked）
- 6 health domain × 30min PASS（api_latency / database_pool / engine_runtime / pipeline_throughput / risk_envelope / strategy_quality）
- ⚠️ `[78] feature_baseline_writer_cron_fires` WARN heartbeat stale 4.75d（cron 停 fire；ref §13）

**Cron schedule（post-H-2 restore 2026-05-25）**：10/13 enabled（5 Day -1 MUST + 2 SHOULD + 3 Day 0）；3 defer（passive_wait_healthcheck / ref21_market_microstructure_recorder / blocked_symbols_30d_unblock）

---

## §1 Top-Priority Active Blockers（P0 only）

| ID | 狀態 | Owner | AC | Next Action |
|---|---|---|---|---|
| **P0-EDGE-1** | 🔴 ACTIVE（SSH empirical 2026-05-26 22:00 UTC: 0/3 AC paths satisfied；2026-05-26 cohort reframed 5→4 textbook per AMD-2026-05-26-01）| QC + PA | (i) **4 textbook** ≥3 demo 7d avg_net>5bps + Wilson lower>0 + n≥30（funding_arb retired per AMD-2026-05-26-01）；**OR** (ii) ≥3 alpha-bearing 達同標；**OR** (iii) portfolio 7d gross 正向 | 唯一可預期 closure path = (ii) Sprint 2 Alpha Tournament W12-15 dispatch；當前 (i) **4/4 textbook** `insufficient_total_samples`（funding_arb 樣本不再累積：deprecated；ma_crossover / bb_breakout / bb_reversion / grid_trading runtime_bps −11~−42）；(iii) live_demo 7d net=-1.99 USDT |
| **P0-LG-3** | ⚠️ SPEC DRIFT IDENTIFIED 2026-05-26（PA verify）/ AC + §15 #1 dependency CORRECTION REQUIRED / IMPL DISPATCH PENDING V### renumber | PA spec → E1×7 | **AMENDED 2026-05-26**：spec v2 §2.4A "fee_source tick-time consumer" **NOT-FOUND**；V099/V100 與 LG-3 **無關**（已被 autonomy_level_config / m4_hypothesis_base_table 占用）；正解 AC = V### renumber to V104+ + v56 P0 Layer B 7d observation gate (~2026-05-29) | PA AC correction + V### renumber + 移除 §15 #1 false dep；ref `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-11--lg_3_spec_v2_final.md` + `2026-05-19--lg_3_wave_2_4_dispatch_plan_refresh.md` |
| **P0-OPS-1..4** | 🟡 SPEC LAND 2026-05-26 / OPS-3 5/5 operator confirm ✅ CLEARED 2026-05-26 / E1 IMPL DISPATCH PENDING / W18-21 前必 closure | PA + BB + E3 | OPS-1 HTTPS Caddy+Tailscale cert spec ✅；OPS-2 1 CRITICAL secret split + 2 HIGH runbook gap；**OPS-3 5/5 cleared**（C-1 Spain ✅ / C-2 ≥L2 ✅ / C-3 demo+33d ⚠ pending OP-1 mainnet / C-4 defer first Live+30d / C-5 USDT Flexible $100-200 ✅）；OPS-4 runbook 11 章 / 4 critical gap | OPS-1 E1 dispatch (23-33hr)；OPS-2 P1-OPS-2-SECRET-SPLIT + RUNBOOK + DRY-RUN；**OPS-3 已 closure via `srv/docs/governance_dev/2026-05-26--bybit_compliance_signoff.md`**；OPS-4 4 critical gap (systemd + PG backup)；ref §6 NEW P1 entries |
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
Layered Autonomy v2 Wave 5  🟡 DESIGN-DONE CC APPROVE A / IMPL PENDING operator sign     V099 + GUI + Rust SM-04 + 5 ADR sync + R4 audit
```

**狀態語言**：
- DESIGN-DONE = spec/ADR/runbook/schema spec 文件 land 通過 PM signoff
- IMPL-PENDING = 對應 Rust/Python/SQL 實作未開始
- RUNTIME-NOT-APPLIED = sql/migrations/ 本地 max=V112；trading_ai 主 PG `_sqlx_migrations` max=112 / count=102；7/7 target table 已 physical land

---

## §3 In-Flight Workflow（≤7 並行；含 sub-agent chain）

7 active workflow 對應 PM cluster 分組（per PM §3）：

| ID | Workflow | Owner chain (T1-T5 template) | 估時 | Cluster | Blocked-on |
|---|---|---|---|---|---|
| **A** | 22 fail-closed 1e-3 invariant Option (c) AMD-09-03 附錄 | T2: PA → TW → FA + QC → R4 cascade (waterfall+parallel) | 7.5-11.5 hr | 1 (parallel) | — D+0 可啟動 |
| **B** | ADR-0046 basis observation/execution split | T1: PA design → E1 Rust → MIT V117 → E2 → E4 → BB → QA | 24-30 hr | 2 (Phase 1→2→3) | PA design first |
| **D** | AMD-2026-05-25-01 商業化邊界 cascade | T2: operator confirm → PA + FA + R4 parallel + TW docs/README cascade | 4-6 hr | 3 (operator-gated) | operator 確認 |
| **E** | AMD-2026-05-25-02 v5.5 reframe cascade | T2: operator confirm → PA + FA + R4 parallel + TW docs/README cascade | 4-6 hr | 3 (operator-gated) | operator 確認 |
| ~~**F**~~ | ~~funding_arb (D) 3C TOML deprecation cascade~~ | – | ✅ **FULLY CLOSED 2026-05-26** | – | Phase 1 PA spec ✅ + Phase 2 TW (AMD-26-01 + 5 primary + 19 secondary) ✅ + R4 Pass A APPROVE-WITH-DRIFT ✅ + R4 Pass B APPROVE ✅；3 LOW carry-over defer D+7 |
| **Earn Wave C** | OP-1 series → first stake $100-200 Flexible-only | T1: 7 hand OP + 5 可代做 post-1..5 | OP 30min + post-flow 30min | 3 (operator-gated) | OP-1 a-f hand actions |
| **Layered Autonomy v2 Wave 5** | V099 + GUI + Rust SM-04 + 5 ADR sync + R4 | T1+T2: 3 並行 (E1 V099 / E1a GUI / Rust SM-04) | 81-126 hr (8-12+21-28+52-86) | 1 partial (operator approve) | operator final sign-off |
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
| `P1-OPS-1-E1-DISPATCH` | 1 | **NEW 2026-05-26 per PA OPS-1 verdict** — Caddy + Tailscale cert (Tailnet-only HTTPS) + CSRF middleware + secure cookie env + CSP report-only 升 P1；spec at `srv/docs/execution_plan/specs/2026-05-26--p0-ops-1-https-secure-cookie.md`；3 parallel track 23-33 hr (A 10-14h / B 8-12h / C 5-7h)；3 risk + 3 open question；Owner: PA spec → E1×3 → E2 → E4 → BB → QA；阻 Sprint 4 first Live |
| `P1-OPS-1-PROXY-HEADER-SPOOF-RISK` | 1 | **NEW 2026-05-26 per PA OPS-1 §3.2** — `auth_routes_common.py:181-204` docstring 提 `OPENCLAW_TRUST_PROXY_HEADERS` env，但 `_has_https_proxy_hint` 實作沒 gate → 直連 8000 偽造 `X-Forwarded-Proto: https` 即可讓 Secure cookie 在 HTTP 用 = spoof risk；OPS-1 IMPL 一併修 |
| `P1-OPS-2-SECRET-SPLIT` | 1 | **NEW 2026-05-26 per E3-CRIT-1** — `OPENCLAW_IPC_SECRET` 同時是 IPC HMAC + authorization.json signing key 是設計級缺陷；新增 `live_auth_signing_key.txt` + `OPENCLAW_LIVE_AUTH_SIGNING_KEY` env；migration: 首次 deploy fallback `OPENCLAW_IPC_SECRET` + WARN，14d soak 後移除；touches 5-hard-gate #4+#5；Owner: E1 + CC dual review；阻 OPS-2 SOP 撰寫 + Sprint 4 first Live；ref E3 report §C-1 |
| `P1-OPS-2-RUNBOOK` | 1 | **NEW 2026-05-26 per E3-HIGH-2** — 撰寫 `docs/runbooks/credential_rotation.md` mirror `replay_signing_key_rotation.md` 9 章；涵蓋 3 secret class + 6 auxiliary；含 Schedule / Emergency / Fail Modes / Rollback / Audit Verification SQL；Owner: PA + E1 draft → E3 + CC review → PM approve → BB sign-off；ETA: 1 sprint after C-1 land |
| `P1-OPS-2-DRY-RUN` | 1 | **NEW 2026-05-26 per E3-LOW-2** — OP-1 a-f path 45+ 天未動 = SOP 從未 end-to-end exercised；用 OP-1 當 OPS-2 SOP first dry-run 收 timing + fail-modes → runbook v1.1；Owner: Operator + PM；trigger: OP-1 unblock D+2-D+3 |
| `P1-OPS-3-OPERATOR-CONFIRM-5` | – | ✅ **CLOSED 2026-05-26 sequential confirmation** — C-1 Spain (EU member, MiCA-compliant, NOT in 16 restricted) ✅ / C-2 ≥ Advanced L2 (Gov ID + face + utility bill, 2M USDT/day) ✅ / C-3 2 demo keys + 33d TTL ⚠ pending OP-1 a-f mainnet reissue (unblocks Sprint 4 + Earn) / C-4 defer Spanish tax planning to first Live + 30d (~2026-10) / C-5 accept Earn risks, first stake $100-200 USDT Flexible only ✅；signoff doc `srv/docs/governance_dev/2026-05-26--bybit_compliance_signoff.md`；ref `srv/docs/CCAgentWorkSpace/BB/workspace/reports/2026-05-26--p0-ops-3-bybit-tos-geo-kyc-audit.md` |
| `P1-OPS-4-GAP-A-WATCHDOG-SYSTEMD` | 1 | **NEW 2026-05-26 per PA OPS-4 GAP A** — watchdog systemd respawn 未實裝；engine crash → watchdog auto-restart RTO ≤5min；阻 first-day live；Owner: E1 + E3 review |
| `P1-OPS-4-GAP-F-ENGINE-SYSTEMD` | 1 | **NEW 2026-05-26 per PA OPS-4 GAP F** — engine systemd unit 未實裝；補 systemd 失效 supervisor 自動 restart；阻 first-day live；Owner: E1 + E3 review |
| `P1-OPS-4-GAP-B-PG-RESTORE-DRILL` | 1 | **NEW 2026-05-26 per PA OPS-4 GAP B** — PG restore drill 未驗 (15d retention 30d cron need verify)；阻 first-day live；Owner: MIT + E1 |
| `P1-OPS-4-GAP-D-PG-DUMP-CRON` | 1 | **NEW 2026-05-26 per PA OPS-4 GAP D** — PG dump cron 未排；阻 first-day live；Owner: MIT + E1 |
| `P1-LG-3-AC-CORRECTION` | 2 | **NEW 2026-05-26 per PA LG-3 verify** — TODO §1 行 48 AC 描述有 drift；spec v2 §2.4A "fee_source tick-time consumer" NOT-FOUND（grep 0 docs match）；V099 已被 autonomy_level_config 占用 + V100 已 land m4_hypothesis_base_table；正解 = V### renumber to V104+ + v56 P0 Layer B 7d observation gate (~2026-05-29)；§15 #1 LG-3 ↔ funding_arb 是 FALSE dependency；Owner: PA AC correction + V### query free number + dispatch refresh patch；ref `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-19--lg_3_wave_2_4_dispatch_plan_refresh.md` |
| `P1-FUNDING-ARB-DEPRECATION-CASCADE` | – | ✅ **FULLY CLOSED 2026-05-26** Phase 1+2 + R4 Pass A+B APPROVE — PA spec (551 行) + TW AMD-26-01 (372 行) + 5/5 primary + 19/19 secondary + R4 Pass A APPROVE-WITH-DRIFT + R4 Pass B APPROVE 0 dangling；commits `6a20b9ea` + `e913adbf` 三端同步；3 LOW carry-over defer D+7 (~2026-06-02 piggyback E1 `#[deprecated]` IMPL): (1) EA-3 hotfix spec SUPERSEDED header (2) SQL V033 enum header (`strategy_close_funding_arb`) (3) docs/README specs/ index 補 PA spec entry；後續 PENDING follow-up: E1 D+7 `#[deprecated]` IMPL + MIT D+30 PG retention + QC D+30 observation；ref §9 Workflow F + AMD-26-01 §11 cascade checklist + R4 Pass B report `docs/CCAgentWorkSpace/R4/workspace/reports/2026-05-26--workflow-f-cross-ref-audit-pass-b.md` |
| `P2-OPS-2-HOTRELOAD` | 3 | **NEW 2026-05-26 per E3-HIGH-1 long-term** — `Arc<ArcSwap<BybitCredentials>>` + IPC reload handler = 5s rotation parity with authorization.json；消除 engine restart for Bybit key rotation；Owner: E1；ETA: Post-Sprint 4 |
| `P2-OPS-2-AUDIT-ENDPOINT` | 3 | **NEW 2026-05-26 per E3-MED-1** — `POST /api/v1/security/ipc-secret/rotate` + governance audit row；Owner: E1；ETA: Post-Sprint 4 |
| `P2-OPS-2-CRON-DRIFT` | 3 | **NEW 2026-05-26 per E3-LOW-1** — `helper_scripts/cron/long_lived_secret_drift_check.sh` report mtime + alert > 365d / > 90d；Owner: E1；ETA: Post-Sprint 4 |
| `P2-OPS-2-GITLEAKS` | 3 | **NEW 2026-05-26 per E3 F-pattern recommend** — `gitleaks` or `detect-secrets` pre-commit hook（`ls .git/hooks/` 0 enforcement，只 `.sample`）；Owner: E1 + PA；ETA: Pre-Sprint 4 |
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
| `P1-PG-CHECKSUM-ALIGNMENT-DECISION-2-C` | – | ✅ **CLOSED-VERIFY 2026-05-24** for current landed SQL set | trading_ai sqlx_migrations max=112/count=102 |
| `P1-SANDBOX-SQLX-METADATA-ALIGNMENT` | – | ✅ **FULLY CLOSED 2026-05-24** Round 1+2 | sandbox V100+ checksum 對齊 trading_ai 主 DB sha256 |

**v5.8 24 H 級 ticket**（按 module 分組）→ ref `docs/archive/2026-05-21--todo_v60_archive.md` §B（24 條 carry into Sprint 1A-β/γ/δ/ε 期間並行補）

---

## §7 Operator Action Checklist（D+0 ~ Sprint 4 first Live ETA）

| 日期 | Action | 預期時間 | Trigger | 卡進度後果 |
|---|---|---|---|---|
| **D+0 NEW (2026-05-26)** | **confirm AMD-2026-05-25-01 商業化邊界 + AMD-2026-05-25-02 v5.5 reframe** | 15 min | PM ping | 阻 Workflow D + E cascade |
| **D+0 NEW** | commit canary [67]→[80] rename 4 files | 5 min | E1 sub-agent ready | 阻 sync (已 commit cf61d1f0 ✅) |
| **D+1-D+2** | **AMD-21-01 v2 Layered Autonomy 最終 sign-off** | 30 min | PA spec + CC re-audit A 級 done | 阻 Wave 5 cascade IMPL（V099 + GUI + Rust SM-04 + 5 ADR sync） |
| **D+2-D+3** | OP-1 a-f Bybit Web UI key 重發（< 2026-04-09 key 已過期 ≥45 天）| 5-10 min | OP-1 pre-verify done | 阻 Earn Wave C production deploy |
| **D+2-D+3** | OP-2 Stage 0R Earn variant 仲裁（8 OQ）| 30-60 min | OP-1 完成 | 阻 first stake |
| **D+2-D+3** | OP-3 first stake $100-200 Flexible-only via GUI | 5 min | OP-2 拍板 | 阻 `learning.earn_movement_log` rows>0 |
| ~~D+3~~ | ~~P0-FUNDING-ARB-DECISION-FORCE 升等拍板~~ | – | ✅ **CLOSED 2026-05-26 operator chose (D)** | cascade Workflow F NEW (4-6 hr)；§15 #1 reframed |
| **D+5** | P0-EDGE-1 + P0-LG-3 + P0-OPS-1..4 closure ETA 填 §10 P0 precondition | 30 min | PM ping | 阻 Sprint 4 first Live W18-21 |
| **W12** | **Sprint 2 業務 Alpha Tournament 派發**（5 stream × 7 sub-agent Wave 1+2+3）| – | Sprint 1A-γ V111 land | 阻 §1 P0-EDGE-1 AC-A (ii) 路徑 |
| **W18-21 (~2026-09)** | **★ Sprint 4 first Live $500 ★** | – | P0-EDGE-1 + LG-3 + OPS-1..4 全 closure | – |

**Operator 手做時間 D+0~D+5 ≈ 2.5-4 hr**（OP-1 系列佔大頭）

---

## §8 Backlog by Cluster（per PM §3 parallel 分組）

### §8.1 Cluster 1 — Independent Parallel（D+0 立即啟動）
1. **Workflow A** — 22 fail-closed 1e-3 invariant Option (c)（PM CONDITIONAL APPROVED；PA→TW→FA→QC→R4 5-agent；7.5-11.5 hr）
2. **Workflow D** — AMD-25-01 商業化邊界 cascade（operator confirm pending → docs/README + SPEC_REGISTER + TODO cleanup；4-6 hr）
3. **Workflow E** — AMD-25-02 v5.5 reframe cascade（operator confirm pending；4-6 hr）
4. **Workflow F** (NEW 2026-05-26) — funding_arb (D) 3C TOML deprecation cascade（operator-decided；PA deprecation spec → TW docs/README/AMD → R4 cross-ref；4-6 hr）
5. **Workflow J** — PA 撤回 PA workspace「liquidation_pulse.rs deleted」FALSE CLAIM（per drift audit §11.3 J；~1-2 hr）
6. **OPS [78]** — `feature_baseline_writer` cron stale 4.75d investigation（可能 v5.7 path migration `/home/ncyu/srv/` → `/home/ncyu/BybitOpenClaw/srv/` 衝突；E3 → E1 → E4；~4-8 hr）

### §8.2 Cluster 2 — Partial-Dependent（B Phase 1→2→3 / Sprint 1A-γ/δ/ε）
- **Workflow B Phase 1**（Sprint 1A-γ）：ADR-0046 basis spec execution split IMPL（PA → E1 → E2）
- **Workflow B Phase 2**（Sprint 1A-δ）：funding_arb IMPL + MIT V117 dry-run（PA → E1 → MIT → E2）
- **Workflow B Phase 3**（Sprint 1A-ε）：funding_arb live + BB approve + QA backfill（E4 → BB → QA）
- 估時 24-30 hr total；不阻 Sprint 2 主軸

### §8.3 Cluster 3 — Operator-Gated
- AMD-25-01/02 confirm（D+0 NEW）
- AMD-21-01 v2 Wave 5 final sign-off（D+1-D+2）
- OP-1 a-f Bybit Web UI key 重發（D+2-D+3）
- OP-2 Stage 0R Earn variant 仲裁（D+2-D+3）
- OP-3 first stake（D+2-D+3）
- P0-FUNDING-ARB-DECISION-FORCE 升等拍板（D+3）
- P0-EDGE-1 + LG-3 + OPS-1..4 closure ETA（D+5）

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
- **C2** ADR-0030 4-gate threshold 副帳場景 verify（E4 + FM；3-6 hr；opportunistic）
- **C3** ADR-0046 公式補位（funding_cost_bps + borrow_cost_bps）+ dual-write phase + V117 預寫 pending（PA → E1 → MIT → E2；8-12 hr）
- **C4** E4 canary [80] full sweep verify namespace="canary"（E4；2-4 hr；依 canary deploy 穩定）

---

## §9 Cascade Pending（AMD/ADR → DOC-XX per FA §3）

| 來源 | Cascade 目標 | Owner | Status |
|---|---|---|---|
| **AMD-2026-05-25-01** | docs/README AMD list / SPECIFICATION_REGISTER count / TODO §8 Stream 2 殘留 cleanup | PM + R4 + TW | Pending operator confirm |
| **AMD-2026-05-25-02** | 同上 + ADR-0030 4-gate 副帳場景 cross-ref | PM + R4 + TW | Pending operator confirm |
| **AMD-2026-05-21-01 v2 Wave 5** | ADR-0034 LAL 對齊矩陣加 Autonomy Level / ADR-0040 §Decision 5 / ADR-0042/0044/0045 wording sync + V099 schema + GUI sub-section + Rust SM-04 patch | PA + E1 + E1a + MIT + R4 | Pending operator final sign-off |
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
- BONUS finding：[78] feature_baseline_writer cron stale 4.75d → §13

**Pending follow-up (Cluster 1)**：A + D + E + J + OPS[78] 5 並行 D+0 立即啟動

---

## §11 Layered Autonomy v2 Wave 5 Cascade Pointer（2026-05-22）

**狀態**：✅ **DESIGN-DONE + CC APPROVE A 級** 2026-05-22；Wave 5 cascade IMPL **PENDING operator final sign-off**

**4 個 SSOT 文件指針**：
1. **AMD-2026-05-21-01 v2** — `docs/governance_dev/amendments/2026-05-22--AMD-2026-05-21-01-autonomy-fully-with-failsafe.md`（684 行）
2. **PA spec v2** — `docs/execution_plan/2026-05-22--autonomy_level_toggle_design_spec.md`（1031 行 / Autonomy Level Toggle + 5 fail-safe hard req）
3. **V099 schema spec** — `docs/execution_plan/specs/2026-05-22--v099-autonomy-level-config.md`（568 行）
4. **CC re-audit** — `docs/CCAgentWorkSpace/CC/workspace/reports/2026-05-22--layered_autonomy_v2_reaudit.md`（A 級 / 7 HC + 6 反模式 + 2 BLOCKER 候選解除）

**Wave 5 cascade IMPL roadmap**（PENDING operator sign-off）：
1. V099 schema land — E1 + MIT Linux PG empirical dry-run 13 條（8-12 hr）
2. GUI Autonomy Posture sub-section — E1a tab-governance.html / CONFIRM SWITCH typed-confirm / 14 path × 2 level panel（21-28 hr）
3. Rust SM-04 patch — `RiskEvent::NotificationFailsafeTimeout` 新 variant + active 鎖利 hook + 35+ transition rules verify（52-86 hr per AMD §9.8；PA + E1 + E4 三方 review）
4. 5 module ADR sync — ADR-0034 + ADR-0040 + ADR-0042/0044/0045 wording 對齊
5. R4 cross-ref audit

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
| **[78] feature_baseline_writer cron stale 4.75d** | NEW 2026-05-25 via SSH | E3 → E1 → E4 investigation；可能 v5.7 path migration `/home/ncyu/srv/` → `/home/ncyu/BybitOpenClaw/srv/` 衝突；Cluster 1 OPS[78] |
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
| **D+0 (2026-05-26)** | confirm AMD-25-01/02 + Cluster 1 五並行啟動 | 5 sub-agent dispatch |
| **D+1-D+2** | AMD-21-01 v2 final sign-off + Wave 5 cascade dispatch | operator sign + 3 並行 |
| **D+2-D+3** | OP-1 a-f + OP-2 + OP-3 Earn first stake | `learning.earn_movement_log` rows > 0 |
| **D+5** | P0-EDGE-1 / LG-3 / OPS-1..4 closure ETA | Sprint 4 first Live W18-21 unblock |
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
| 1 | ~~LG-3 IMPL DISPATCH ↔ P0-FUNDING-ARB-DECISION-FORCE~~ | ❌ **REFRAMED 2026-05-26 per PA verify + AMD-2026-05-26-01 land** — LG-3 supervised live SM 是所有策略 (**4 textbook + C10**；funding_arb retired per AMD-2026-05-26-01) supervised live activation gate；funding_arb V2 Retired closed 不影響 LG-3 IMPL 需求；真衝突 = **V### 號占用 conflict**（V099/V100 已被 autonomy_level_config + m4_hypothesis_base_table 占）+ **v56 P0 Layer B 7d observation 視窗 ~2026-05-29**；ref `P1-LG-3-AC-CORRECTION` |
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
