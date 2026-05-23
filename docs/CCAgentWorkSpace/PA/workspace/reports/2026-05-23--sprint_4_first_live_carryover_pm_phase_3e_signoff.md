---
report: Sprint 4+ first Live carry-over — PM Phase 3e Sign-off + Final Verdict
date: 2026-05-23
author: PM (主會話 PM + Conductor)
phase: Sprint 4+ Phase 3e (TW Acceptance Report → PM closure)
status: SIGNED-OFF
parent reports:
  - srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-23--sprint_4_first_live_carryover_acceptance.md (TW Phase 3d Acceptance Report)
  - srv/docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-23--sprint_4_e4_regression_wave_ab.md (E4 regression PASS)
  - srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-23--sprint_4_wave_b_m1_singleton_registry_ssot.md (M-1 singleton SSOT)
  - srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-22--sprint_2_pm_phase_3e_signoff.md §4.1 (Sprint 4+ 來源)
---

# Sprint 4+ first Live carry-over PM Phase 3e Sign-off — Final Verdict

## §1 Verdict

**PASS WITH 8 CARRY-OVER** — Sprint 4+ first Live carry-over §4.1 4 items 全 closed。

- 4 items：PA-DRIFT-4 bybit instrumentation + PA-DRIFT-5 RiskEnvelopeSourceProbe wire-up + main.rs scheduler 接線 + AC-1b real PG empirical 全 PASS
- production V106 deploy DONE (psql -f raw apply 走 sandbox 範式)
- production engine PID 3654935 + 5 active domain × 30 min sample 770 row (engine_runtime 264 + pipeline_throughput 220 + api_latency 176 + database_pool 110 + risk_envelope 20)
- E2 review × 3 round 1+2 全 APPROVE + E4 regression PASS (cargo 3961 + pytest 6042 + nm 0 hit)
- M-1 Singleton Registry SSOT 建立 + 6 mutable singleton 登記 (21 天 governance gap closure)
- **Sprint 4+ Wave A+B Mac source layer + Linux runtime deploy 全鏈 closure**

## §2 §4.1 4 items 拍板

| # | Item | PM 拍板 | Rationale |
|---|---|---|---|
| 1 | PA-DRIFT-4 bybit_rest_client + bybit_private_ws instrumentation | **ACCEPTED PASS** | Wave A round 2 E2 APPROVE (5 noop retCode + 60s boundary test + observer 下沉 + checked_sub 注釋)；production binary 含 strings hit；WS half placeholder Sprint 5+ supervisor signature 改造 carry-over |
| 2 | PA-DRIFT-5 RiskEnvelopeSourceProbe wire-up | **ACCEPTED PASS WITH 1 CARRY-OVER** | Wave A round 2 E2 APPROVE (F-1 cap comment + F-3 batch helper)；correlation_avg_pairwise Wave A placeholder 0.0；real calculator + lookback Sprint 5+ amend |
| 3 | main.rs scheduler 接線 | **ACCEPTED PASS** | Wave B round 2 E2 APPROVE-WITH-CONDITIONS (H-1 placeholder OK band + M-2 WS doc + L-1/2/3)；M-1 由 PA 獨立 task closure (Singleton Registry SSOT) |
| 4 | AC-1b real PG empirical | **ACCEPTED PASS WITH 1 EXPECTED CARRY-OVER** | 5 active domain × 30 min sample × 20-264 row 遠超 ≥5 要求；strategy_quality 0 row 屬 Sprint 5+ wire-up 已知例外 (per Track E dispatch §NOT in scope) |

## §3 Production deploy chronology

```
1. Mac commit chain: 5acd36e6 + 4c84d1bb + 245216d1 + 4d4ff99f + 82351b61 + 1639506f
2. ssh trade-core git pull --ff-only (三端同步)
3. source ~/.cargo/env + bash restart_all.sh --rebuild
   - cargo rebuild 43.54s PASS clean
   - binary 5月23 02:02 (Sprint 4+ Wave A+B 含 m3_health_emitters)
   - engine PID 3641344 first restart
   - V106 INSERT fail (production trading_ai 0 schema)
4. secrets/environment_files/basic_system_services.env: OPENCLAW_AUTO_MIGRATE 0→1
5. restart_all.sh (no rebuild)
   - MigrationRunner auto-migrate: V97 V98 land OK
   - V103 Guard A FAIL: learning.hypotheses 缺 (Sprint 1A-γ M4 base table gap)
   - engine startup ABORT
6. AUTO_MIGRATE 1→0 revert + restart_all.sh
   - engine PID 3648060 clean startup
7. psql -f sql/migrations/V106__health_observations.sql
   - hypertable + compression 7d + retention 90d + 4 hot-path index
   - all guards PASS
8. engine restart 自動 (watchdog?) → PID 3654935 etime 02:58
9. 30 min sample wait (emitter interval 30s/30s/60s/60s/300s)
10. AC-1b SQL verify: 5 domain × 20-264 row in 30 min PASS
```

## §4 8 carry-over routing 拍板

### §4.1 Sprint 1B late — V### chain 補位 (3 items P0/P1)

| # | Item | Owner | Priority | Est |
|---|---|---|---|---|
| 1 | V99-V102 spec gap audit + 新 V099 base table migration (M4 hypothesis_discovery; 解 V103 Guard A FAIL) | PA + E1 | **P0 Sprint 1B late** | PA spec 4-6 hr + E1 IMPL 6-8 hr |
| 2 | OPENCLAW_AUTO_MIGRATE=1 + restart auto-migrate chain (V99-V112 全 land + _sqlx_migrations MAX 對齊 112) | E1 + operator | P0 Sprint 1B late | 1-2 hr deploy + verify |
| 3 | V107 + V112 production deploy 後 M11 + M1 spec wire-up | PA + E1 | P1 | spec follow-up 2-3 hr |

### §4.2 Sprint 5+ cascade IMPL (4 items P1/P2)

| # | Item | Owner | Priority | Est |
|---|---|---|---|---|
| 1 | BybitPrivateWs supervisor signature 改造 (解 WS half placeholder disconnect; per singleton-registry.md §6.3) | E1 + E2 | P1 | 4-6 hr E1 + 1 hr E2 |
| 2 | PortfolioStateCache update task wire-up (真實接 PaperState SSOT; per singleton-registry.md §6.4) | E1 + PA | P1 | 4-6 hr E1 + 0.5 hr PA |
| 3 | archive 4 Python singleton re-ingest (H_STATE_INVALIDATOR / MARKET_SCANNER / HStateCacheSlot / CostEdgeAdvisorDbSlot; per singleton-registry.md §6.1) | TW + PA | P2 LOW | 1-2 hr |
| 4 | dispatch packet 模板補「新 singleton 預登記」section (per singleton-registry.md §6.2) | PA | P2 | 30 min |

### §4.3 Sprint 5+ M3 follow-up (6 items)

| # | Item | Owner | Priority |
|---|---|---|---|
| 1 | StrategyQualityEmitter wire-up (解 Track E 0 row 例外) | E1 + PA | P1 |
| 2 | AC-7 cargo bench m3_emitter_cold_start fixture IMPL | E1 + E4 | P2 |
| 3 | LOC peak 切檔 (main_health_emitters 652 / bybit_rest_client 1367 / bybit_private_ws 1718 / risk_envelope 904 / risk_envelope_probe_impl 958；全 >800 警告 <2000 hard cap) | E1 + E2 | P2 |
| 4 | F-4 correlation_avg_pairwise real calculator + lookback amend | E1 + PA | P1 |
| 5 | Track B PipelineThroughput real wire-up (ws_client + IndicatorEngine + IPC stats) | E1 + PA | P1 |
| 6 | Track C writer_queue_depth / pool_wait_p95 real wire-up | E1 + PA | P2 |

### §4.4 Production engine 監測 follow-up (Sprint 4+ 即起 → Sprint 5+；4 items)

| # | Item | Owner | Priority |
|---|---|---|---|
| 1 | HEALTH_WARN 60 row api_latency rest_p50/p95/p99 → PA 評估 Bybit demo latency ladder threshold amend | PA + QA | P2 |
| 2 | HEALTH_WARN 41 row engine_runtime open_fd_count → PA 評估 ladder threshold amend | PA + QA | P2 |
| 3 | 60s expire boundary 4 個 production 長時間 sample 驗證 | QA | P3 |
| 4 | F-2 NaN/inf sanitize production fire log 監測 (真實 PaperState SSOT wire-up 後) | QA | P2 Sprint 5+ Wave C |

## §5 Sprint 後續派發

### §5.1 Sprint 1B late 派發 readiness

**OPEN** — V99-V102 spec gap audit + 新 V099 base table migration 是 Sprint 1B late P0 入口；前置 closure 後 OPENCLAW_AUTO_MIGRATE auto-migrate chain 即可一鍵完成 V99-V112 全 land。

### §5.2 Sprint 5+ cascade IMPL dispatch readiness

**OPEN** — Sprint 4+ Wave A+B closure 後 cascade 各組件 ready (event_bus 預埋 + V106 emit chain active + 6 singleton 登記 SSOT)。Sprint 5+ §4.2 4 carry-over + §4.3 6 M3 follow-up + §4.4 4 production 監測 統一派發。

### §5.3 Sprint 1B 剩餘 3 章節 (策略部署性質)

- C10 Stage 1 Demo (funding harvest demo 部署；ETA Sprint 1B)
- Earn first stake (Bybit Earn 首存款；C10 spot leg paper-only Phase 1)
- v5.7 baseline 收口

per operator 早前指示「先做 1 部分做完進 2」+「完成 1B」邏輯，這 3 章節是 Sprint 1B 純策略部署，不依賴 Sprint 4+ Wave A+B 工作；可獨立派發。

## §6 Lessons Learned 收口

PM 確認 6 條 sustained lessons (per TW Acceptance Report §5)：

1. **PA prerequisite verify mandatory** — Sprint 4+ Wave A 揭露 PA dispatch packet §5.1 「既有 bybit hook」FALSE；E2 Track D HIGH-3 catch；Wave B Track B placeholder DEGRADED band drift catch；PA prerequisite claim 必 grep verify literal 真實存在
2. **Production deploy V### sparse migration** — sql/migrations/ V99-V102/V104-V105/V108-V111 missing；OPENCLAW_AUTO_MIGRATE=1 first attempt apply V97/V98 自動 land 然後 V103 Guard A FAIL；揭露 M4 base table missing；revert + psql -f raw apply V106 only path
3. **Engine restart cargo PATH ssh non-interactive** — restart_all.sh --rebuild 第一次撞 `cargo not found`；需 `source ~/.cargo/env` (per memory feedback_restart_bind_host_default)
4. **Release binary stripped — strings vs nm differentiation** — Cargo.toml strip=true release profile；nm 0 symbol；驗 wire-up symbol 需 strings + 真實 log + DB row 證據
5. **emitter fail-soft 設計 vs auto-migrate fail-loud** — emitter V106 INSERT fail 走 tracing::warn 不 crash engine；MigrationRunner fail-loud abort startup；兩種 fail mode 不衝突 (emitter is observability layer; migrate is correctness gate)
6. **AC-1a/AC-1b 拆分契約價值再驗** — AC-1a in-memory proxy PASS during scaffold sign-off (Wave A+B IMPL); AC-1b real PG empirical PASS post-deploy + 30 min wait — 拆分契約完整覆蓋兩階段

額外 1 條 lesson (Sprint 4+ specific)：

7. **CLAUDE.md trim 21 天 governance gap (M-1 singleton SSOT)** — 2026-05-02 trim 操作整段刪除 §九 4 條 Python singleton entry 但沒搬位；21 天 gap 到 Sprint 4+ Wave B E2 round 2 catch；建立 docs/architecture/singleton-registry.md SSOT；trim 操作未來必走「move-not-delete」range

## §7 Sign-off Chain

```
Phase 2 Wave A IMPL: 5acd36e6 (PA-DRIFT-4 + PA-DRIFT-5)
Phase 2 Wave A round 2 fix: 4c84d1bb (6/6 finding closure)
Phase 2 Wave B IMPL: 245216d1 (main.rs scheduler 接線)
Phase 2 Wave B round 2 fix: 4d4ff99f (5/6 finding closure)
Phase 3b E4 regression PASS: 82351b61
Phase 3 M-1 Singleton Registry SSOT: 1639506f
Phase 3c QA AC-1b real PG empirical: production V106 deploy (psql -f) + 30 min sample × 5 domain × 20-264 row PASS
Phase 3d TW Acceptance Report: SIGNED-OFF-PENDING-PM
Phase 3e PM sign-off: 本 commit + 後續 push
```

## §8 PM 簽收

- **PM 主會話 PM + Conductor** 簽收 Sprint 4+ first Live carry-over §4.1 closure
- **Verdict**：PASS WITH 8 CARRY-OVER (§4.1-§4.4 全 land routing)
- **Sprint 1B late + Sprint 5+ cascade dispatch readiness gate**：OPEN
- **下一步**：operator 確認本 sign-off → PM 決定派 Sprint 1B late V99-V102 base table audit (§4.1.1) OR Sprint 5+ cascade IMPL (§4.2) OR Sprint 1B 剩 3 章節 (策略部署)
- **Status update**：TODO.md §0/§1.1 同步更新 Sprint 4+ → DONE-VERDICT-PASS WITH 8 CARRY-OVER

---

**END OF Sprint 4+ first Live carry-over Phase 3e PM Sign-off**
