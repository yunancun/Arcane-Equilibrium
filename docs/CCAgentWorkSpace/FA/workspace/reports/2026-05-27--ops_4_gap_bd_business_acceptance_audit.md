# FA Business Acceptance Audit — OPS-4 GAP B (PG restore drill) + GAP D (PG dump cron)

**Auditor**: FA (Functional Auditor — read-only)
**Date**: 2026-05-27
**Status**: research only — acceptance criteria + business gap analysis for MIT + E1 IMPL sign-off
**Verdict**: **NEEDS-AMENDMENT**（GAP B+D 概念對；但 RPO 漏 2 L0 表 + retention 矛盾 + audit trail meta-gap + 估時 3-5h 過低）

**Sources**:
- PA OPS-4 runbook `srv/docs/execution_plan/specs/2026-05-26--p0-ops-4-first-day-live-runbook.md` §2.2-§2.3 / §7.2 / §10 GAP B+D / §8 sign-off MIT row
- MIT empirical `srv/docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-27--ops_4_gap_b_d_pg_backup_drill.md`
- BB OPS-3 C-4 `srv/docs/CCAgentWorkSpace/BB/workspace/reports/2026-05-26--p0-ops-3-bybit-tos-geo-kyc-audit.md`
- TODO §5 9 Safety Invariants + §6 P1 entries
- CLAUDE.md §四 5-gate / §二 16 root principles
- V003 / V035 / V075 / V098 / V099 / V100 / V112 schema empirical

---

## §A — 4 Schema 業務保留優先級分層

**統計**: 84 active tables 跨 8 schema（含 V001 legacy public）

| Schema | L0 Critical | L1 Important | L2 Replayable | L3 Ephemeral | Total |
|---|---:|---:|---:|---:|---:|
| **governance** | 3 | 2 | 0 | 0 | 5 |
| **trading** | 5 | 4 | 2 | 1 | 12 |
| **learning** | 6 | 11 | 8 | 3 | 28 |
| **observability** | 0 | 1 | 0 | 4 | 5 |
| **system** | 2 | 0 | 0 | 0 | 2 |
| **replay** | 0 | 2 | 5 | 0 | 7 |
| **market** | 0 | 0 | 11 | 0 | 11 |
| **public (V001 legacy)** | 0 | 0 | 0 | 14 | 14 |
| **合計** | **16** | **20** | **26** | **22** | **84** |

### A.1 L0 Critical（16 表 — 任何情境必 restore；丟即破 root principle #8）

**governance**:
1. `governance.lease_lal_tiers` (V112) — 5-tier seed config；LAL framework 唯一 SoT
2. `governance.lease_lal_assignments` (V112) — append-only per-lease tier history；root principle #3
3. `governance.strategy_freeze_log` (V058) — strategy halt 永久 audit

**trading**:
4. `trading.fills` (V003 hypertable 永久 retention) — 唯一 real-fill audit；Bybit reconcile
5. `trading.intents` (V003 hypertable 90d retention V075) — pre-risk-review 意圖
6. `trading.orders` (V003 hypertable 永久) — submitted order event
7. `trading.order_state_changes` (V003 hypertable 60d retention V075) — lifecycle event source
8. `trading.decision_context_snapshots` (V003) — 決策上下文；AI 可解釋性

**learning**:
9. `learning.governance_audit_log` (V035 永久) — 9 invariant audit 唯一 SoT
10. `learning.earn_movement_log` (V100, per BB OPS-3 C-4) — Bybit Earn 唯一 audit source
11. `learning.hypotheses` (V100) — M4 hypothesis discovery preregistration
12. `learning.hypothesis_preregistration` (V100, signed append-only)
13. `learning.lease_transitions` (V054) — Decision Lease state transition history
14. `learning.strategist_applied_params` (V019) — 已套用策略參數 SoT

**system**:
15. `system.autonomy_level_config` (V099 singleton CHECK id=1) — Autonomy Level Toggle 唯一 SoT
16. `system.autonomy_level_switch_audit` (V099) — switch reason ≥30 char enforce

### A.2 L1 Important（20 表 — first 24h restore；資訊損失但可重建）

`governance.unblock_candidates` (V090) / `canary_stage_log` (V080) / `trading.risk_verdicts` (V003 30d V075) / `position_snapshots` 90d / `signals` 90d / `decision_outcomes` / `learning.decision_features` 90d / `decision_features_evaluations` (V082) / `experiment_ledger` (V007) / `model_registry` (V023) / `cost_edge_advisor_log` (V026) / `funding_settlements` (V027) / `exit_features` (V029) / `strategy_trial_ledger` (V079) / `replay_divergence_log` (V107) / `mlde_param_applications` (V032) / `health_observations` (V106) / `observability.engine_events` (V014) / `replay.tier_promotion_approval` (V057) / `handoff_requests` (V044)

### A.3 L2 Replayable（26 表 — 可從 raw event/market 重算）

`trading.scanner_snapshots` (V030) / `scanner_opportunity_decays` (V062) + 8 learning + 5 replay + 11 market

### A.4 L3 Ephemeral（22 表 — runtime cache / 不影響業務）

4 observability metrics + 1 paper_state_checkpoint + 3 learning (rl_transitions / promotion_pipeline / symbol_clusters) + 14 public V001 legacy

---

## §B — Restore Drill 業務驗證 Acceptance Criteria

### B.1 9 Post-Restore L0 Validation Queries（必跑）

| # | 業務目的 | SQL pattern | Pass criteria |
|---|---|---|---|
| 1 | **5-gate state 完整 (I1)** | `SELECT current_level, last_switched_at FROM system.autonomy_level_config WHERE id=1` | 1 row + level IN (CONSERVATIVE/STANDARD) |
| 2 | **Signed authorization 路徑 (I2)** | `SELECT event_type, COUNT(*) FROM learning.governance_audit_log WHERE event_type='lease_grant' AND ts > pre_disaster_ts GROUP BY event_type` | rows > 0 |
| 3 | **Decision Lease state (I7)** | `SELECT lease_id, status_to, COUNT(*) FROM learning.lease_transitions WHERE ts > pre_disaster_ts GROUP BY lease_id, status_to` | rows match pre-disaster snapshot |
| 4 | **trading.fills 完整性 (#8)** | `SELECT COUNT(*), MAX(ts), MIN(ts), SUM(realized_pnl) FROM trading.fills WHERE ts > pre_disaster_ts AND is_paper=false` | count + sum = pre-disaster + Bybit balance match |
| 5 | **intents → orders FK lineage** | `SELECT COUNT(*) FROM trading.intents i LEFT JOIN trading.orders o ON i.intent_id=o.intent_id WHERE o.intent_id IS NULL` | 0 orphaned post-restore |
| 6 | **earn_movement_log (BB OPS-3 C-4)** | `SELECT direction, COUNT(*), SUM(amount_usdt), MAX(ts) FROM learning.earn_movement_log GROUP BY direction` | 全 stake/redeem rows preserved |
| 7 | **strategist_applied_params (#11)** | `SELECT strategy_name, MAX(applied_at) FROM learning.strategist_applied_params GROUP BY strategy_name` | rows for 4 active strategies |
| 8 | **hypothesis preregistration signed integrity** | `SELECT hypothesis_id, payload_hash, signed_at FROM learning.hypothesis_preregistration ORDER BY signed_at DESC LIMIT 10` | payload_hash NOT NULL + signature valid |
| 9 | **LAL tier integrity (ADR-0034)** | `SELECT tier_level, COUNT(*) FROM governance.lease_lal_assignments WHERE assigned_at > pre_disaster_ts GROUP BY tier_level` | rows match + 5 tier seed intact |

### B.2 9 Safety Invariant Re-verify Matrix（post-restore）

| # | Invariant | Re-verify? | Path |
|---|---|---|---|
| I1 | 5-gate live boundary | **YES** | authorization.json signature + autonomy_level_config + live_reserved + OPENCLAW_ALLOW_MAINNET |
| I2 | Signed authorization 走 Python renew/approve | **YES** | engine 不能 bypass renew；query 2 |
| I3 | LiveDemo 不降級 | NO | runtime endpoint；不在 PG |
| I4 | Mainnet env-var fallback closed | NO | env-var only |
| I5 | Bybit API timeout fail-closed | NO | runtime IPC |
| I6 | execution_authority = denylist | NO | Rust constant |
| I7 | ML/Dream/Executor/Strategist 不繞 Governance | **YES** | lease_transitions + lease_lal_assignments + post-restore first lease；query 3, 9 |
| I8 | 不 fake healthcheck / fills / lineage | **YES** | governance_audit_log 0 row loss + trading.fills Bybit reconcile；query 2, 4 |
| I9 | Paper 非 active promotion | NO | restored paper_state 不影響 live |

**Re-verify count**: **4/9 mandatory** (I1, I2, I7, I8)

### B.3 RTO Acceptance

| Scenario | PA target | FA acceptance |
|---|---|---|
| Engine crash | < 5 min | ≤ 5 min (PA align) |
| Engine SIGTERM | < 10 min | ≤ 10 min |
| PG out-of-disk | < 30 min | ≤ 30 min |
| **PG full restore (NEW GAP B)** | **未列** | **≤ 2 hr** (FA propose) |
| **PG single L0 schema restore** | **未列** | **≤ 30 min** (FA propose) |

### B.4 RPO Acceptance

| Data class | PA RPO | FA acceptance | Gap |
|---|---|---|---|
| trading.fills/intents/orders | 0 fsync | ≤ 24h post-GAP-D | 24h fill loss = 重大；建議 hourly dump for L0 |
| risk_verdicts (30d V075) | ≤ 1 row | ≤ 24h post-dump | 30d 前 drop；GAP B 無法解 |
| governance_audit_log (永久) | ≤ 5s flush | ≤ 24h post-dump | 24h gap = 9 invariant 24h 空白 |
| halt_audit.log fsync | 0 | **GAP C 另解** | 不在 GAP B+D scope |
| decision_lease | ≤ 60s | ≤ 24h post-dump | audit chain 24h 黑窗 |
| Bybit account state | 0 | N/A | 外部 SoT |
| **earn_movement_log (BB C-4)** | **PA 未列** | **≤ 24h (FA mandate)** | Earn 唯一本地 audit；丟 = 稅務 + monetary loss |

**RPO gap**: PA §2.2 漏 `earn_movement_log` + `system.autonomy_level_config`

### B.5 Drill Scenarios（必驗 business scenarios）

1. **Full DB corruption recovery** — drop trading_ai → restore latest → 9 query PASS + Bybit balance reconcile
2. **Single L0 schema restore (governance only)** — 驗 selective restore 不破其他 schema
3. **Single L0 table truncate accident** — `pg_restore -t trading.fills`；驗 FK lineage 不破
4. **V### migration rollback** — V112 LAL retract 後 restore；驗 5 tier seed
5. **TimescaleDB hypertable chunk loss** — 單 chunk corrupt → restore；retention policy 不重 fire
6. **Disaster after Earn first stake** — operator 首 stake 後 24h disaster；Bybit Earn API cross-check
7. **Mid-Sprint 4 first-day live disaster** — 模擬 first 24h disaster；RTO ≤ 2hr + 9 invariant re-verify + operator approval resume

---

## §C — PG Dump Cron 業務功能 Gap

### C.1 Audit Trail Completeness（root principle #8）

**Gap**: MIT draft `trading_ai_pg_dump_cron.sh` 寫 JSONL log + sentinel，但**不寫 `learning.governance_audit_log`** governance audit row。

**Impact**: dump 失敗 / md5 drift / retention violation 不入 9 invariant audit dashboard；I8 無 PG 級可查證據。

**FA acceptance**: dump wrapper 補 INSERT `learning.governance_audit_log` (event_type='pg_dump_completed' / 'pg_dump_failed')。

### C.2 5-gate 影響

**Gap**: PA spec 未列 dump 期間 live trading 影響。`pg_dump -Fc` 加 ACCESS SHARE lock；15-30 min for 226GB 可能：
- 阻 `VACUUM FULL` (低)
- 與 retention `drop_chunks` 競爭 (中)
- 不阻 INSERT/SELECT (低)

**FA acceptance**: dump 期間若 6 health domain 任一 WARN → 提前 abort。

### C.3 DR Scenario Coverage

| DR scenario | Coverage | Gap |
|---|---|---|
| Tailscale outage | ✅ | — |
| Bybit API outage | ✅ | — |
| PG out-of-disk | ❌ | **D-1**: dump 前 `df -h > 5GB` precheck；不足 skip + alert |
| PG container crash | partial | OK (exit≠0 alert) |
| NAS unmount | ❌ (NAS 未掛) | **D-2**: 短期 local-only；長期 operator 必補 NAS mount + rsync |
| concurrent dump race | ✅ (lock dir) | — |

### C.4 Compliance（30d audit per CLAUDE.md §四 + V075）

**Gap**: V075 risk_verdicts 30d retention；MIT draft 15d dump。**15d dump < 30d audit window → D+16 risk_verdicts 已 drop + dump 也只剩 15d → 真 audit window 15d，非 30d。**

**FA acceptance**:
- 接受 15d 窗 OK
- 必滿足 9 invariant 30d → dump retention 延 **31d (30d + 1d grace)**
- MIT §3 警告 "15d × 50GB = 750GB > 841G free"；operator 三選：(a) Mount NAS / (b) 縮 7d / (c) 接受 15d；**FA verdict: 7d 太短 (< 30d window)；NAS 是唯一可接受長期解**

### C.5 Earn V100 audit trail（per BB OPS-3 C-4）

**Gap**: MIT draft 已含 `--schema=learning` 涵蓋 `earn_movement_log` ✅。

**FA acceptance**: post-install 第一 dump 跑 `pg_restore --list | grep earn_movement_log` 必返 ≥1 entry。MIT `verify_pg_dump.sh` 缺此 check；建議補 6th check「L0 schema coverage smoke test」。

---

## §D — PA OPS-4 Runbook Gap Audit

### D.1 5 大 business requirement 漏

1. **RPO 表漏 V099+V100 兩 L0 表** — PA §2.2 只列 7 class；2026-05 新增 V099 Autonomy + V100 Earn 未追加
2. **9 query post-restore validation 未列** — PA §2.1 只列 RTO；無「restore 成功 ≠ 業務可重用」SQL acceptance gate；§B.1 補
3. **9 Safety Invariant re-verify 矩陣未列** — PA §8 sign-off MIT row 只說 quarterly drill；不指明 re-verify 哪幾個；§B.2 補
4. **L0/L1/L2/L3 業務分層未做** — PA §2.3 提 schema list 未分層；§A 補
5. **Dump 流程不寫 governance_audit_log** — PA §10 GAP D 未提；MIT draft 也未實作；違反 #8

### D.2 16 root principles 未覆蓋面

- #3 AI→Lease→複核: post-restore lease state 未強制 re-verify；§B.1 query 3 補
- #7 學習不重寫 Live: strategist_applied_params integrity 未驗；§A L0 #14 + §B.1 query 7 補
- #8 every trade reconstructable: PA §2.2 列 trading.fills 永久；dump cadence (15d) ≪ 永久 — NAS 異地必補
- #10 separate fact/inference/assumption: PA §7.2 用 "should"；§B.5 7 scenario 必驗
- #15 multi-agent collaboration: PA §8 MIT 一人 row；建議 FA + BB cross-sign（FA business + BB Bybit Earn cross-reconcile）

### D.3 OPS-1/2/3 pattern 對照 OPS-4 類似 gap

| Pattern | OPS-1/2/3 揭露 | OPS-4 GAP B+D 類似面 |
|---|---|---|
| 配置漂移 | OPS-2 endpoint 標 "demo" vs slot 標 "live" | dump 7-schema 寫死 wrapper；新增 schema (如 audit) 會漏 — **加 weekly drift check: `\dn` vs script 列表** |
| 首次 SOP 退化 | OPS-2 OP-1 路徑 45+ 天未 exercise | restore drill 也首次；建議 **monthly restore drill cron** 取代 quarterly |
| End-to-end smoke missing | OPS-1 7 raw fetch 未走 ocApi → 403 | MIT 只跑 schema-only；**未跑 fresh 226GB → restore → 9 query 全鏈** |
| Healthcheck 與業務真值斷層 | OPS-3 C-4 Account Statement excludes Earn | dump JSONL log + sentinel 不入 9 invariant dashboard — **加 check_pg_dump_freshness 進 passive_wait** (MIT §3.4 已 propose) |
| Multi-session race | OPS-2 五週 governance drift | retention prune `find -mtime` multi-session 改 retention TOML 可能 race；**加 lock + JSONL audit retention 變更** |

---

## §E — E1 IMPL Sign-off Acceptance Criteria（15 項）

| # | 驗證項 | Evidence | Pass |
|---|---|---|---|
| 1 | L0 schema 100% covered | `pg_restore --list \| grep -E 'governance\\.\|learning\\.\|trading\\.\|system\\.'` | 16 L0 表全在 TOC + comment + index |
| 2 | earn_movement_log dumped + restored | `pg_restore --list \| grep earn_movement_log` | ≥ 3 entries |
| 3 | 9 invariant re-verify 4/4 PASS | post-restore sandbox 跑 §B.1 query 1-9 | I1/I2/I7/I8 對應 query 全綠 |
| 4 | Full data restore drill ≤ 2 hr | E4 timer | drill report 含 start/end ts |
| 5 | End-to-end drill 7 scenario | §B.5 各 1 次 | drill report 紀錄 verdict |
| 6 | dump 寫 governance_audit_log | post-dump `SELECT * FROM learning.governance_audit_log WHERE event_type LIKE 'pg_dump_%'` | row 存在 + ts < 1h |
| 7 | verify_pg_dump.sh 進 passive_wait | `passive_wait_healthcheck.sh --quiet` 7+ check | 7 check (原 6 + pg_dump_freshness) |
| 8 | dump 期間 6 health domain 0 WARN | dump run 中 + 後 30 min healthcheck | 0 WARN / 0 FAIL |
| 9 | NAS 異地或 retention 30d+ | `df -h` + `ls -la \| wc -l` | 30+ dump files OR NAS verify |
| 10 | Cron audit trail in TODO §0 | `crontab -l \| grep pg_dump` | entry exists + last run < 26h |
| 11 | ≥ 1 drill report in MIT workspace | `ls docs/CCAgentWorkSpace/MIT/.../2026-05-*--*pg*drill*.md` | 1+ report ts post-D+1 |
| 12 | MIT push back §3 三選一拍板 | operator D+0 sign-off 紀錄 | (a) NAS / (b) 縮 7d / (c) accept 15d |
| 13 | PA spec §2.2 RPO 表補 2 row | PA spec patch commit | spec diff 顯示 2 新 row |
| 14 | Drill 含 V### migration rollback | drill report §5 含 V112 retract 驗證 | LAL 5 tier seed 重 PASS |
| 15 | BB cross-sign (Earn variant) | PA spec §8 加 BB row | BB sign-off + Bybit Earn API cross-check |

**Sign-off count**: 15 項；E1 IMPL DONE 後需全 15/15 PASS

---

## §F — Verdict

### F.1 PA Runbook GAP B/D 判定

**Status**: **NEEDS-AMENDMENT**

理由：
1. PA §2.2 RPO 漏 V099 autonomy + V100 earn 兩 L0 表
2. PA §10 估時 (3-5 hr) 過低；MIT empirical 6-8 hr / sub-agent + NAS work
3. PA §2.3「30d×7 rotation」與 §10「15d minimum」自相矛盾；operator 需拍板
4. PA §10 GAP D 未列 dump 自身 audit trail (#8)
5. PA §8 sign-off MIT 單方面；缺 FA + BB cross-sign

### F.2 Sub-verdict

| Sub-area | Verdict |
|---|---|
| GAP B 範圍 | **PARTIAL-SUFFICIENT** — 概念對，缺 9 query + 7 scenario + 2 hr RTO 明文 |
| GAP D 範圍 | **PARTIAL-SUFFICIENT** — MIT 3 draft 對齊 spec §2.3，缺 audit row + NAS 異地 + 30d retention drift solve |
| 業務鏈完整度 | **PARTIAL** — 5/9 invariant restore-后 verify；L0 16 表 100% 對齊；dump cadence 與 audit window 矛盾 |

### F.3 阻 first-day live 結論

- GAP B 業務 acceptance：§E 15 criteria 全 PASS
- GAP D 業務 acceptance：§C 5 gap 全 mitigation
- **最早 unblock = T+28-36 hr from operator first action**（含 NAS mount decision + D+1 full drill）

### F.4 業務功能完整度（4 維度）

| 維度 | GAP B | GAP D |
|---|---|---|
| 1. 代碼存在 | 0/1 | 1/1 |
| 2. 功能可調用 | 0/1 | 0/1 (未 install) |
| 3. 端到端可用 | 0/1 | 0/1 (未 fire) |
| 4. 邊界覆蓋 | 0/1 | 0/1 |
| **Total** | **0/4 (0%)** | **1/4 (25%)** |

---

## §G — Cross-Reference

- PA: `srv/docs/execution_plan/specs/2026-05-26--p0-ops-4-first-day-live-runbook.md`
- MIT: `srv/docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-27--ops_4_gap_b_d_pg_backup_drill.md`
- MIT drafts: `srv/docs/CCAgentWorkSpace/MIT/workspace/drafts/ops4_gap_b_d/{install_pg_dump_cron.sh, trading_ai_pg_dump_cron.sh, verify_pg_dump.sh}` (291 LOC)
- BB OPS-3 C-4: `srv/docs/CCAgentWorkSpace/BB/workspace/reports/2026-05-26--p0-ops-3-bybit-tos-geo-kyc-audit.md`
- TODO §5 + §6: `srv/TODO.md:125-139` + 164-165
- CLAUDE.md §四 + §二

---

**FA AUDIT DONE**: 4 schema 分層 L0=16/L1=20/L2=26/L3=22；4/9 invariant 必 re-verify；5 critical business gaps；15 sign-off criteria；Verdict **NEEDS-AMENDMENT**。
