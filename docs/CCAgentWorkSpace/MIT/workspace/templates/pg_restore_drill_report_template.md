# PG Restore Drill Report — <Scenario S#> · <YYYY-MM-DD>

**Owner template：** MIT
**Template version：** v1（2026-05-27 — OPS-4 GAP-B Round 2 baseline）
**用法：** drill 跑完複製本 template 到 `srv/docs/CCAgentWorkSpace/MIT/workspace/reports/YYYY-MM-DD--<scenario>.md`，逐欄填實際數據。空欄不可留 TBD；無 applicable 填 `N/A (reason)`。

**SOP 來源：** [`docs/runbooks/pg_restore_drill_sop.md`](../../../../runbooks/pg_restore_drill_sop.md)
**9 query 來源：** [`helper_scripts/db/post_restore_validation.sql`](../../../../../helper_scripts/db/post_restore_validation.sql)
**sqlx repair binary：** `cargo run --bin repair_migration_checksum --release -- --verify` / `--apply --i-understand-this-modifies-db`

---

## 1. Metadata

| 欄位 | 值 |
|---|---|
| **Drill date** (UTC) | `YYYY-MM-DDTHH:MMZ` |
| **Operator** | `<name / username>` |
| **Scenario** | S1 Full DB / S2 schema / S3 table / S4 V### rollback / S5 TSDB chunk / S6 Earn / S7 Mid-Sprint 4 first-day live |
| **Drill type** | Scheduled monthly / Per-event ad-hoc / **Emergency** post-incident |
| **Dump source path** | `/home/ncyu/pg_backups/tier01_YYYYMMDD.dump` |
| **Dump source ts** (UTC, from filename) | `YYYY-MM-DDTHH:MM:SSZ` |
| **Dump size** (bytes / human) | `<bytes> / <e.g. 6.8 GB>` |
| **Sandbox DB name** | `trading_ai_drill_YYYYMMDD` |
| **PG host** | `<trade-core / hostname>` |
| **PG version** | `<output of SELECT version()>` |
| **TimescaleDB version** | `<SELECT extversion FROM pg_extension WHERE extname='timescaledb'>` |
| **Drill SOP version followed** | `v1 (2026-05-27)` |
| **Drill report path** (this file) | `srv/docs/CCAgentWorkSpace/MIT/workspace/reports/YYYY-MM-DD--<scenario>.md` |

---

## 2. Pre-Drill Snapshot (PG state pre-disaster baseline)

### 2.1 Live `trading_ai` DB state（drill 起點，從 live PG 取）

```sql
-- 跑於 live trading_ai DB（drill 開始前的 baseline）
SELECT 'sqlx_max' AS metric, max(version)::TEXT AS value FROM public._sqlx_migrations
UNION ALL SELECT 'fills_count', count(*)::TEXT FROM trading.fills
UNION ALL SELECT 'fills_latest_ts', max(ts)::TEXT FROM trading.fills
UNION ALL SELECT 'fills_realized_pnl_sum', ROUND(SUM(realized_pnl)::NUMERIC, 4)::TEXT FROM trading.fills
UNION ALL SELECT 'governance_audit_24h', count(*)::TEXT FROM learning.governance_audit_log WHERE ts > NOW() - INTERVAL '24 hours'
UNION ALL SELECT 'lease_transitions_24h', count(*)::TEXT FROM learning.lease_transitions WHERE ts > NOW() - INTERVAL '24 hours'
UNION ALL SELECT 'earn_movement_total', count(*)::TEXT FROM learning.earn_movement_log;
```

| Metric | Value (live, pre-drill) |
|---|---|
| `sqlx_max` | `<填>` |
| `fills_count` | `<填>` |
| `fills_latest_ts` | `<填>` |
| `fills_realized_pnl_sum` | `<填>` |
| `governance_audit_24h` | `<填>` |
| `lease_transitions_24h` | `<填>` |
| `earn_movement_total` | `<填>` |

### 2.2 Pre-disaster snapshot timestamp（baseline 用於對比 sandbox restored DB）

`pre_disaster_ts` = `<YYYY-MM-DDTHH:MM:SSZ>`（通常 = drill 起跑時間）

---

## 3. Drill Execution Timeline

逐 phase 紀錄 start / end 時間（UTC）+ wall-clock 秒；對齊 SOP §4.2 之 7 phase。

| Phase | Action | Start (UTC) | End (UTC) | Duration | Verify result |
|---:|---|---|---|---:|---|
| 1 | **Snapshot**：baseline_snapshot.sql 跑於 live DB | | | | `/tmp/openclaw/logs/drill_baseline_<ts>.log` |
| 2 | **Side-restore**：createdb + pg_restore -j 4 | | | | exit 0 / non-0 (specify) |
| 3 | **sqlx checksum repair**：`repair_migration_checksum --verify` | | | | drift_count = 0 / drift_count > 0 (specify versions) |
| 3.5 | (if drift > 0) `--apply --i-understand-this-modifies-db` | | | | COMMIT / ROLLBACK |
| 4 | **Verify**：post_restore_validation.sql 9 query | | | | aggregate summary: <pass>/9 PASS, <warn> WARN, <fail> FAIL |
| 5 | **Swap rehearsal**（drill **skip** real swap；scenario 7 walk through） | | | | DRILL MODE - SKIPPED / WALKED THROUGH |
| 6 | **Reconcile rehearsal**（drill **skip** real reconcile；scenario 6 跑 Bybit Earn cross-check） | | | | DRILL MODE - SKIPPED / Bybit diff: `<USDT>` |
| 7 | **Operator approval rehearsal** | | | | drill verdict PASS / CONDITIONAL / FAIL |
| 8 | **Cleanup**：DROP DATABASE sandbox | | | | OK / FAIL (specify) |
| - | **Governance audit row INSERT** to live DB | | | | INSERT 0 1 / FAIL |

**Total wall-clock**: `<X hr Y min>`
**vs RTO budget**: `<within / over> by <delta>`（scenario 1/6/7 budget ≤ 4 hr；scenario 2/3/4/5 budget ≤ 30-60 min）

---

## 4. 9 Query Results Table

Source: `post_restore_validation.sql` aggregate summary 最後 9 row。

| Q# | Check name | Metric value | Verdict | Notes |
|---:|---|---|---|---|
| Q1 | autonomy_level_config singleton | `<n>` | PASS / FAIL | `<reason if FAIL>` |
| Q2 | lease_grant 24h | `<n>` | PASS / WARN | `<WARN OK if day-1 disaster>` |
| Q3 | lease_transitions distinct to_state 24h | `<n>` | PASS / WARN | `<>` |
| Q4 | trading.fills 24h | `<n>` | PASS / WARN | `<vs pre-drill baseline §2.1>` |
| Q5 | intents orphan_pct 24h | `<%>` | PASS / FAIL / WARN | `<>` |
| Q6 | earn_movement_log total | `<n>` | PASS (operator cross-check) / FAIL | `<scenario 6 必補 Bybit cross-check diff>` |
| Q7 | active strategy applied_params | `<n distinct strategy>` | PASS / FAIL | `<expect ≥ 1 of 4 strategies>` |
| Q8 | preregistration bad_hash_in_top_10 | `<n>` | PASS / FAIL | `<expect 0>` |
| Q9 | lease_lal_tiers seed count | `<n>` | PASS / FAIL | `<expect exactly 5>` |

**Aggregate**: `<P>/9 PASS · <W> WARN · <F> FAIL`

**Verdict rule**（per SOP §8.1）：
- `≥ 7/9 PASS + 0 FAIL` → drill verdict eligible PASS
- `0 FAIL + ≤ 2 WARN OK in day-1 disaster scenario`
- 任 FAIL → drill verdict FAIL + 不可進 swap

---

## 5. 4/9 Invariant Re-verify Matrix

對齊 SOP §8.2；drill mode caveat = PG 級可查證據 only（real disaster 才驗 engine/IPC/healthcheck）。

| # | Invariant | 對應 9 query | Re-verify result | Notes |
|---|---|---|---|---|
| I1 | 5-gate live boundary | Q1 | PASS / FAIL | `<Q1 1 row + id=1 + level enum>` |
| I2 | Signed authorization 路徑 | Q2 | PASS / FAIL / WARN | `<Q2 ≥ 1 row in 24h; WARN if day-1 disaster>` |
| I7 | ML/Dream/Executor/Strategist 不繞 Governance | Q3 + Q9 | PASS / FAIL | `<both PASS required>` |
| I8 | 不 fake healthcheck / fills / lineage | Q2 + Q4 (+ Bybit if scenario 6/7) | PASS / FAIL / N/A | `<Bybit cross-check for S6/S7; N/A for S2-S5 acceptable>` |

**Aggregate**: `<n>/4 PASS`

**Verdict rule**：4/4 PASS → drill verdict PASS；任 FAIL → drill verdict FAIL（即使 9 query 全 PASS）。

---

## 6. sqlx Checksum Drift Detail (per SOP §6 fail mode)

對齊 `repair_migration_checksum --verify` output table；逐 drift version 紀錄。

| Action taken | Result |
|---|---|
| `--verify` initial run | drift_count = `<n>`; drift_versions = `<[V###, ...] / empty>` |
| `--apply --i-understand-this-modifies-db` (if drift > 0) | TTY prompt typed `COMMIT` / `<other>` → applied / rolled back |
| Post-apply re-verify | drift_count = `<0 / n>` |
| pg_dump backup file path | `/tmp/openclaw/backup/_sqlx_migrations_pre_repair_<ts>.sql` |

如有 drift，逐 version 紀錄：

| version | description | file_sha384 (first 16) | db_checksum (first 16) | line_end | file_size | RCA hypothesis |
|---:|---|---|---|---|---|---|
| `<V###>` | `<desc>` | `<sha>` | `<sha>` | LF/CRLF | `<bytes>` | `<e.g. spec drift between dump time and current>` |

**注意**：drill mode 是否需 `--apply` 修 drift = 看 drill RCA；通常 drill scenario 4（V### migration rollback）會故意製造 drift 並 documenting；其他 scenario drift 出現是 unexpected → 必補 RCA。

---

## 7. Bybit Earn Cross-Check (scenario 6 / scenario 7 必填；其他 N/A)

| Source | direction | SUM(amount_usdt) | row count | Latest event ts |
|---|---|---:|---:|---|
| Local `learning.earn_movement_log` (sandbox restored) | stake | | | |
| Local `learning.earn_movement_log` (sandbox restored) | redeem | | | |
| Bybit API `GET /v5/earn/position` | (staked total) | | N/A | |
| Bybit API `GET /v5/earn/order` history (recent 30d) | (movement count) | | | |
| **Diff**: local stake SUM vs Bybit staked | | `<USDT diff>` | | |

**Cross-check pass criteria** (per BB OPS-3 C-4): diff < 0.01 USDT → PASS。

---

## 8. Verdict

### 8.1 Drill verdict

| Criterion | Required | Actual | Pass? |
|---|---|---|---|
| 9 query: ≥ 7/9 PASS + 0 FAIL | `<R>` | `<A>` | YES / NO |
| 4/9 invariant: 4/4 PASS | `<R>` | `<A>` | YES / NO |
| sqlx checksum drift handled | drift_count post-action = 0 | `<A>` | YES / NO |
| Bybit Earn cross-check (S6/S7 only) | diff < 0.01 USDT | `<A>` | YES / NO / N/A |
| Wall-clock within RTO budget | scenario budget | `<A>` | YES / NO |
| Cleanup completed | sandbox DROPped | `<A>` | YES / NO |
| Governance audit row INSERTed | event_type 對 | `<A>` | YES / NO |

**Final verdict**: **PASS / CONDITIONAL / FAIL**

- **PASS**: all criteria met; SOP ratified for next drill / real disaster
- **CONDITIONAL**: minor WARN tolerable for current drill type（e.g. day-1 disaster Q2 WARN）+ documented caveat
- **FAIL**: any FAIL → can't swap to live + must RCA before next drill

### 8.2 Operator sign-off (scenario 7 mandatory)

| Field | Value |
|---|---|
| Operator name | `<>` |
| Sign-off ts (UTC) | `<>` |
| Explicit confirm of 9/9 + 4/4 PASS + (if applicable) Bybit reconcile | YES / NO |
| Sign-off note | `<free text — e.g. "approve resume rehearsal SOP">` |

---

## 9. Carry-over Backlog（drill 發現 SOP gap / runbook revision 建議）

| # | Finding | Severity | Owner | Target action | Linked issue / PR |
|---:|---|---|---|---|---|
| 1 | `<e.g. SOP §4.3 scenario 3 procedure 缺 -t with TSDB hypertable caveat>` | Low / Med / High | MIT / E1 / Operator | `<e.g. SOP §4.3.3 amend>` | `<>` |
| 2 | | | | | |

如 carry-over 為空 → 寫 `N/A — drill clean; no SOP revision needed`。

---

## 10. Logs & Artifacts

| Artifact | Path | Size | Retention |
|---|---|---:|---|
| baseline snapshot | `/tmp/openclaw/logs/drill_baseline_<ts>.log` | | 30d |
| pg_restore output | `/tmp/openclaw/logs/drill_restore_<S#>_<ts>.log` | | 30d |
| sqlx verify output | `/tmp/openclaw/logs/drill_sqlx_verify_<S#>_<ts>.log` | | 30d |
| sqlx pg_dump backup (if --apply ran) | `/tmp/openclaw/backup/_sqlx_migrations_pre_repair_<ts>.sql` | | 90d |
| post_restore_validation.sql output | `/tmp/openclaw/logs/post_restore_validation_<ts>.log` | | 90d |
| Bybit Earn cross-check screenshot (S6/S7) | `/tmp/openclaw/logs/drill_bybit_earn_<ts>.png` | | 90d |
| This drill report | (this file) | | 永久 |

---

## 11. Next Drill Date

| 欄位 | 值 |
|---|---|
| **Next scheduled drill date** (per SOP §4.1 monthly) | `<YYYY-MM-DD (2nd Saturday of next month)>` |
| **Next scheduled scenario** | `<rotate through S1-S7; recommend S1 priority each month>` |
| **Per-event triggers active** | `<list any V### land pending, Earn stake pending, etc.>` |
| **Drill owner for next cycle** | `<name / role>` |

---

## 12. Cross-References

- SOP runbook: [`docs/runbooks/pg_restore_drill_sop.md`](../../../../runbooks/pg_restore_drill_sop.md) §<scenario chapter>
- 9 query script: [`helper_scripts/db/post_restore_validation.sql`](../../../../../helper_scripts/db/post_restore_validation.sql)
- sqlx repair binary src: [`rust/openclaw_engine/src/bin/repair_migration_checksum.rs`](../../../../../rust/openclaw_engine/src/bin/repair_migration_checksum.rs)
- PA OPS-4 spec: [`docs/execution_plan/specs/2026-05-26--p0-ops-4-first-day-live-runbook.md`](../../../../execution_plan/specs/2026-05-26--p0-ops-4-first-day-live-runbook.md) §10.A
- FA business acceptance: [`docs/CCAgentWorkSpace/FA/workspace/reports/2026-05-27--ops_4_gap_bd_business_acceptance_audit.md`](../../../FA/workspace/reports/2026-05-27--ops_4_gap_bd_business_acceptance_audit.md) §B.5
- MIT empirical research: [`docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-27--ops_4_gap_bd_pg_backup_restore_research.md`](../reports/2026-05-27--ops_4_gap_bd_pg_backup_restore_research.md) §2.3-§2.4
- BB OPS-3 C-4 Earn audit reference: TBD（link when BB report shipped）
- Sister sqlx incident memory: `memory/project_2026_05_02_p0_sqlx_hash_drift.md`
