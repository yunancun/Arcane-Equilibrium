# Sprint 4+ first Live §4.1 + Sprint 5+ Wave 1 — Closure Archive

**Archived**: 2026-05-23（從 TODO.md §0 摘要遷出，保留 brief pointer）
**Scope**: Sprint 4+ first Live carry-over §4.1（4 items）+ Stage A→F closure + Sprint 5+ Wave 1（Phase A→F closure）
**Final status**: DONE-VERDICT-PASS WITH 8 CARRY-OVER（Sprint 4+ §4.1）+ DONE-VERDICT-PASS WITH 3 GOVERNANCE NEW + 4 OBSERVATION（Sprint 5+ Wave 1）
**Commit chain**: `011fd5f9 → 6ceb5814`（Sprint 4+ §4.1 + Stage A→F）+ `011fd5f9 → 22a07294`（Sprint 5+ Wave 1 12 commit）

---

## §1 Sprint 4+ first Live carry-over §4.1（2026-05-23 PM-signed）

**4 items 全 closed**：
- PA-DRIFT-4 bybit instrumentation
- PA-DRIFT-5 RiskEnvelopeSourceProbe wire-up
- main.rs scheduler 接線
- AC-1b real PG empirical

**Mac source + Linux runtime deploy 全鏈 closure**：
- production V106 deploy（psql -f raw apply）
- engine PID 3654935 emitter active
- AC-1b SQL 5 active domain × 30 min sample × 20-264 row（遠超 ≥5 要求）
- M-1 Singleton Registry SSOT 建立 + 6 mutable singleton 登記（21 天 governance gap closure）
- E2 round 1+2 × 3 全 APPROVE + E4 regression PASS（cargo 3961 + pytest 6042 + nm 0 hit）
- TW Acceptance Report 760 LOC / 28-30k 字
- PM Phase 3e sign-off DONE

**8 carry-over routing**：
- §4.1 Sprint 1B late V99-V102 3 條
- §4.2 Sprint 5+ cascade 4 條
- §4.3 Sprint 5+ M3 6 條
- §4.4 production 監測 4 條

---

## §2 Stage A→F closure（Sprint 5+ Wave 1 預備期 + 主體）

### Stage A 4 並行 PA design ✅ DONE（commit `011fd5f9`）

- Track 1 Sprint 1B late §4.1.1 V99-V102 audit + V099→V100 push back（PA inline 18504 chars → 327 LOC SSOT）
- Track 2 Sprint 5+ §4.2.1 BybitPrivateWs supervisor Option A external Arc 注入（293 LOC report + 738 LOC spec）
- Track 3 Sprint 5+ §4.3.1 StrategyQualityEmitter wire-up Path A 1 CTE join（270 LOC report + 1200+ LOC spec）
- Track 4 Sprint 1B 剩 3 章節 audit（622 LOC：C10 READY-TO-DISPATCH / Earn NEEDS-OPERATOR + §4.1.1 chain / v5.7 baseline DOWNGRADE-TO-NON-WORK）

7 file commit 3773 LOC；Stage B E1 IMPL dispatch readiness gate OPEN

### Stage B 3 並行 E1 IMPL ✅ DONE（commit `e5fb4895`）

- B-1 V100 M4 base table：663 SQL + 581 spec；3 table 30 col / 4 index / 2 FK / 25 COMMENT
- B-2 BybitPrivateWs supervisor Option A：5 caller updates + ctor +2 Arc + SharedClientsBundle +2 Option Arc + spawn_metric_emitter_scheduler signature +2 ref Option Arc；E1 2 push back 採信
- B-3 StrategyQualityEmitter Phase A：656 LOC probe_impl + Track E section 571 LOC + 5 CTE big query 2030 chars + main.rs caller +34 LOC + 3+7 inline test

13 file commit 3728 insertions / 79 deletions；cargo test --workspace --release 3974 PASS

### Stage C 3 並行 E2 review ✅ DONE

- B-1 + B-2 APPROVE / B-3 RETURN-TO-E1（1 MEDIUM + 1 LOW）
- C round 2 PM 直接 Edit fix（commit `0d4a4aeb`）：Track E log literal 對齊 spec §4.3 + E1 report §7.6 補 context_id NULL filter rationale

### Stage D E4 combined regression ✅ APPROVE（HEAD `0d4a4aeb`）

- cargo 3974/0 + pytest 6088/28 + V100 sqlx parser 15/15 + binary symbol verify 全 PASS

### Stage E Linux deploy chain ✅ FULL CLOSURE（HEAD `e377a94e`）

- **PA-DRIFT-6 catch + fix**：V100 governance_approval_id FK 衝突 TimescaleDB composite PK；PM 直接 Edit drop FK 改 BIGINT soft reference + Guard C 改 column existence check
- psql -f raw apply V100+V103+V107+V112 + V106 既有
- 7/7 target table 物理 land + 9 row _sqlx_migrations register
- B-2 WS metric verified + B-3 Track E strategy_quality 5 min 126 row

### Stage F TW Acceptance + AC-1b 30 min sample ✅ FULL PASS

- TW Stage A→E Overall Acceptance Report 663 LOC（`docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-23--stage_a_to_e_overall_acceptance.md`）
- 10 section + PA-DRIFT-6 完整 RCA + 8 carry-over routing + 2 NEW（PA-DRIFT-6 audit P2 + sandbox stub cleanup P2）
- AC-1b 30 min PG empirical：V106 strategy_quality **630 row**（5 strategy × 5 symbol × 6 metric × ~4.2 ticks）
- V106 api_latency ws_rtt_p50 avg 128.72ms / ws_rtt_p99 avg 129.24ms / ws_dropout 0（29 sample each）
- 5 active domain row total 1653（engine_runtime 336 + database_pool 145 + api_latency 232 + pipeline_throughput 280 + risk_envelope 30 + strategy_quality 630）

### PM Phase 3e sign-off ✅ DONE-VERDICT-PASS WITH 8 CARRY-OVER

- Stage A→E 全鏈 closure
- 7 commit `011fd5f9 → 6ceb5814`
- 3 closure + 1 governance NEW（PA-DRIFT-6）
- 8 carry-over routing

---

## §3 Sprint 5+ Wave 1 全鏈（2026-05-23 PM Phase 3e formal sign-off）

operator 拍板 8 carry-over 6 actionable 全頃 dispatch（per「逐個拍板」2026-05-23）。

**Phase A→F 全鏈**：
- Phase A：5 並行 PA design + sandbox cleanup
- Phase B Wave 1：5 並行 E1 IMPL combined
- Phase C round 1：5 並行 E2 review（2 APPROVE / 3 RETURN）
- Phase C round 2：3 E1 fix + 3 E2 mini verify（3/3 APPROVE）
- Phase D：E4 combined regression（cargo 4018/0/5 + pytest 6122/18/30）
- Phase E：Linux deploy（PA-DRIFT-8 V083 53 violator catch + MIT Strategy B sentinel populate + V101 amend 40 LOC + production 53 sentinel + 14326 backfill + V102 trigger+index+DEFAULT + restart_all --rebuild engine PID 3989463 alive + R2-3 Track B+C real metric + §4.4 ladder amend land）
- Phase F：TW Acceptance Report 712 LOC

**12 commit chain**：`011fd5f9 → 22a07294`

**6 active domain × 30 min × 1836 row**：
- strategy_quality 756
- engine_runtime 360
- pipeline_throughput 300
- api_latency 240
- database_pool 150
- risk_envelope 30

**Track B+C real metric verified**：
- strategy_signal_rate 1-418k/min
- ws_tick_rate 611-1355/sec
- pg_pool_active_conn 0-2
- ratio 0-10%
- vs Stage E baseline placeholder 1.0/2.0

**3 governance NEW**：
- **PA-DRIFT-7** V107 idempotency FK CASCADE 漂移 re-apply 不 restore
- **PA-DRIFT-8** V083 NOT VALID UPDATE re-validation + Strategy B sentinel populate `legacy_pre_v083_unknown_<fill_id>`
- **signal_rate volatility** 1-418k 2.5x range + ws_subscription_drift avg 28.85 persistent positive

**3 Sprint 5+ Wave 2 routing**：
- ADR-0010 Guard D amend pre-UPDATE forward-only constraint violator scan
- signal_rate calculator investigation
- Track v3 EXTEND 11 表完整版
- Earn schema V104 + P&L view
- governance.track_kill_events
- W-AUDIT-4b M2 4 set_entry_context_id call site cargo test guard
- check_fills_entry_context_id_sentinel_count healthcheck

---

## §4 Reference

- 完整 Stage A→F 全鏈 TW Acceptance：`docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-23--stage_a_to_e_overall_acceptance.md`
- Sprint 5+ Wave 1 Phase F TW Acceptance：（per commit `22a07294`）
- Sprint 4+ §4.1 4 items closure：見 Sprint 4+ Phase 3e PM sign-off report
- 8 carry-over routing：見當期 TODO.md §0 + §1.7 + §5

---

**Maintenance contract**：本檔為 closure archive；活躍派工請見 `TODO.md`。
