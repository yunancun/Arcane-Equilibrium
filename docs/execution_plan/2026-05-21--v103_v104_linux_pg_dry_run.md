# V103/V104 Linux PG Empirical Dry-Run（v57-C9）

**日期**：2026-05-21
**Source**：`ssh trade-core`
**Connection**：`psql -h 127.0.0.1 -p 5432 -U trading_admin -d trading_ai`（從 `~/.pgpass` `*:5432:trading_ai:trading_admin:****` 取得；非派工 prompt 假設的 `openclaw/openclaw`）
**狀態**：**PASS** — empirical query 全跑通；但結果**重構 v5.7 §7.5 派工假設**

**One-line verdict**：v5.7 §7.5 假設「V101/V102 已 land、V103/V104 = Earn schema」**全錯**；real state 是 `_sqlx_migrations head = V096`、V101/V102 spec 自己保留「順延 V103/V104」option、Earn schema 重編 V099-V102 是更乾淨路徑。Sprint 1A 派發前需 operator + PA 拍板 4 條 race-aware 排程。

---

## §1 PG 連線方式

| 項 | 值 |
|---|---|
| Host | `127.0.0.1` |
| Port | `5432`（`pg_isready` accepting；`/var/run/postgresql:5432` socket no response — TCP-only） |
| User | `trading_admin` |
| Database | `trading_ai` |
| Auth | `~/.pgpass`（`chmod 600`，permission 已正確）|
| 連線一行 | `psql -h 127.0.0.1 -p 5432 -U trading_admin -d trading_ai -c '<SQL>'` |

**重要 caveat**：DB 名稱 `trading_ai` 而**非** `openclaw`；user `trading_admin` 而**非** `openclaw`。派工 prompt 假設 `psql -d openclaw -U openclaw` 全部會 fail。

**WARNING noise**：每次連線 `WARNING: database "trading_ai" has no actual collation version, but a version was recorded` — 無害（OS locale upgrade 之後沒重建 collation refresh；非 V103/V104 blocker）。

---

## §2 Q1 `_sqlx_migrations` head

```
 head |            recent_10            
------+---------------------------------
   96 | {96,95,94,93,92,91,90,89,88,87}
```

**Head**：V096（`drop dead learning tables`，2026-05-19 apply）

**最近 15 個 applied（含時間軸）**：

| version | description | installed_on | success |
|---|---|---|---|
| 96 | drop dead learning tables | 2026-05-19 | t |
| 95 | market liquidations identity | 2026-05-17 | t |
| 94 | fills close maker audit | 2026-05-17 | t |
| 93 | decision features evaluations panel fail closed | 2026-05-16 | t |
| 92 | panel continuous aggregates | 2026-05-16 | t |
| 91 | decision features reject close mutex check | 2026-05-16 | t |
| 90 | governance unblock candidates | 2026-05-10 | t |
| 89 | governance canary stage metric seed | 2026-05-10 | t |
| 88 | panel btc lead lag panel | 2026-05-10 | t |
| 87 | panel oi delta panel | 2026-05-10 | t |
| 86 | governance reject close reason code | 2026-05-10 | t |
| 85 | panel funding curve | 2026-05-10 | t |
| 84 | decision features reject negative label | 2026-05-10 | t |
| 83 | fills entry context id close check | 2026-05-10 | t |
| 82 | decision features evaluations split | 2026-05-10 | t |

**結論**：
- DB head = V096
- repo 已有 V097/V098 file（`V097__lg5_attribution_healthcheck_indexes.sql` + `V098__governance_audit_log_halt_event_types.sql`）但**未 apply**
- V099 起的所有編號（含 V101/V102 spec 提案 + v5.7 §7.5 想用的 V103/V104）**全部 unreserved**
- V101/V102 spec v3（`docs/execution_plan/2026-05-20--v101_v102_track_attribution_migration_spec.md` line 24-25）**自己寫**「real V### PA dispatch 時 final 鎖定，預期 V101/V102 但若 LG-3 與 W-AUDIT-8a 殘留 reserve V099/V100，可能順延 V103/V104」 — 即 V101/V102 spec **是浮動編號**，跟 v5.7 §7.5 Earn schema 直接撞號

---

## §3 Q2 既有 `hypothes*` + `track` 狀態

```
 table_schema | table_name | column_name | data_type 
--------------+------------+-------------+-----------
(0 rows)
```

**0 rows**：

- `learning.*hypothes*` 表**不存在**（v5.7 §7.5 想新建 `learning.hypotheses` / `learning.hypothesis_preregistration` — clean greenfield，無 collision）
- `trading.fills.track` column **不存在**（v5.7 §7.5 假設「V101 spec v3 §1 已 ALTER 12 表加 track column」**全錯** — V101 spec 還在 docs/execution_plan/ 沒 land，沒 ENUM 也沒 ALTER）

**追加驗證**：

```sql
-- trading.fills 完整 column list（27 cols）
ts / fill_id / order_id / symbol / side / qty / price / fee / fee_currency / realized_pnl /
is_paper / strategy_name / context_id / details / fee_rate / engine_mode / entry_context_id /
exit_source / reference_price / reference_ts_ms / reference_source / slippage_bps /
liquidity_role / fill_latency_ms / exit_reason / close_maker_attempt / close_maker_fallback_reason
-- 無 track；無 strategy_track ENUM type
```

```sql
SELECT EXISTS(SELECT 1 FROM pg_type WHERE typname='strategy_track');
-- f（false — ENUM 未創建）

SELECT table_schema, table_name FROM information_schema.tables
WHERE table_schema='governance' AND table_name LIKE '%track%';
-- 0 rows（governance.track_kill_events 不存在）
```

---

## §4 Q3 PG size baseline

```
  mb   | schemaname |               tablename               
-------+------------+---------------------------------------
 86408 | learning   | decision_features_evaluations
 16073 | trading    | decision_context_snapshots
 11660 | learning   | decision_features
   902 | trading    | risk_verdicts_damaged_20260414_130607
   391 | trading    | decision_outcomes
    29 | learning   | mlde_shadow_recommendations
    22 | learning   | strategist_applied_params
    11 | learning   | mlde_param_applications
     8 | learning   | strategy_trial_ledger
     4 | trading    | fills_damaged_20260414_130607
     1 | trading    | intents_damaged_20260414_130607
     0 | learning   | weekly_review_log
     0 | learning   | linucb_migrations
     0 | learning   | cpcv_results
     0 | learning   | teacher_directives
     0 | learning   | linucb_state
     0 | learning   | linucb_state_archive
     0 | learning   | pattern_insights
     0 | learning   | bayesian_posteriors
     0 | learning   | decision_shadow_fills
```

**總 DB size**：`121 GB`

**Top 3 storage hot**：
- `learning.decision_features_evaluations` = **86 GB**（V082 split，後續 V092 continuous aggregates 沒明顯壓縮 — 後續 retention check follow-up）
- `trading.decision_context_snapshots` = 16 GB
- `learning.decision_features` = 11 GB

**對 V103/V104（Earn schema）size 預測**（per v5.7 §7.5 schema）：
- `learning.hypotheses`：< 10 MB（per spec 預期 row count 數十）
- `learning.hypothesis_preregistration`：< 50 MB（JSONB payload + signature）
- `learning.earn_movement_log`：< 1 MB/yr（spec 預期 stake/redeem < 10/yr）
- `trading.fills.track` ALTER：**寫放大 ≈ 0**（current trading.fills 不大；fills_damaged_20260414 < 4MB 不算）
- **Net**：< 100 MB 6mo growth；可忽略

**governance schema baseline**：top 20 無 governance 表（≤ 1MB）— Earn schema 之 `learning.earn_movement_log` FK → `governance.audit_log` 不會被 governance 既有 size 壓垮。

---

## §5 Q4 V101/V102 spec 落地狀態

**`_sqlx_migrations`** WHERE `version >= 95 AND version <= 110`：

```
 version |         description          |         installed_on          | success 
---------+------------------------------+-------------------------------+---------
      95 | market liquidations identity | 2026-05-17                    | t
      96 | drop dead learning tables    | 2026-05-19                    | t
(2 rows)
```

**V099-V110 全空**。

**Spec land 狀態**（`docs/execution_plan/`）：
- `2026-05-20--v101_v102_track_attribution_migration_spec.md` **EXISTS**（23,452 bytes, modified 2026-05-21 11:56）
- spec 自身 header：「**Status**: SPEC READY v3 — Phase 0 catch-up V097/V098 必先完成 + v56 P0 完整 cycle 收口」
- spec §1 last paragraph：「若 LG-3 與 W-AUDIT-8a 殘留 reserve V099/V100，可能順延 V103/V104」 — 即 **V101/V102 與 V103/V104 是同一份 spec 的浮動編號**，v5.7 §7.5 把 V103/V104 派給 Earn 是**unaware 衝突**

**Phase 0 V097/V098 catch-up 狀態**：
- 兩 file 已在 `srv/sql/migrations/`（V097 = LG-5 attribution healthcheck indexes / V098 = governance audit_log halt event types ALTER constraint）
- **未 apply**（DB head = V096）
- V098 spec note：「含 governance.audit_log ALTER constraint，須低寫入窗口」 — 即 V098 = potentially 鎖表 migration，需要 operator 安排 maintenance window

---

## §6 Sprint 1A IMPL 派發前 finalize 判斷

### 6.1 V103/V104 必派否

**Verdict**：**V103/V104 命名與 v5.7 §7.5 假設衝突；不可直接派 IMPL，必須先 race-aware re-number**。

**根據**：
- v5.7 §7.5 假設 V101/V102 已 land → V103/V104 是 Earn schema
- empirical 事實：V101/V102 spec 還在 docs/execution_plan/ 沒 land；spec v3 自己保留「順延 V103/V104」option
- 直接派 V103/V104 = Earn schema 會與 V101/V102 spec 撞號

### 6.2 V104 退號 / 重編 / no-op 結論

**選項**（依優先排序）：

| 選項 | 編號排程 | 風險 | PA 建議度 |
|---|---|---|---|
| **A**：V097/V098 catch-up → V099/V100 = Track v3 (原 V101/V102) → V101/V102 = Earn schema (原 V103/V104) | 連續 99-102 | Low；只是把所有 spec 順延 2 | **A 最乾淨** |
| **B**：V097/V098 catch-up → V099/V100 reserved (LG-3 / W-AUDIT-8a) → V101/V102 = Track v3 → V103/V104 = Earn schema | 99 預留 100 預留 101-104 | Med；V099/V100 是否真要 reserve 還沒 closure | B 維持 v5.7 §7.5 命名 |
| **C**：跳號（V097/V098 catch-up → V200 = Track v3 → V210 = Earn schema） | sparse | High；違反 migration sequential convention | NOT RECOMMENDED |
| **D**：V101/V102 spec 改編號變 V103/V104（與 Earn 共用 v5.7 §7.5 編號）+ Earn 改 V105/V106 | 衝突 | Med；命名 churn 高 | NOT RECOMMENDED |

**PA 強烈建議 A**：
- V097/V098 catch-up 先排（Phase 0 prerequisite，spec 已寫死）
- V099/V100 = Track attribution v3 final（原 V101/V102）
- V101/V102 = Earn schema final（原 v5.7 §7.5 V103/V104）
- 4 個 ADR/spec 文件全部 search/replace 編號 — 30 min churn 可接受
- V099/V100 「LG-3 / W-AUDIT-8a 殘留 reserve」claim 須 PA 親自驗：grep `srv/docs/CCAgentWorkSpace/{PA,QA}/workspace/reports/` 找 LG-3 或 W-AUDIT-8a 是否仍要 V099/V100 編號 — 若無實質佔用，V099/V100 直接給 Track v3

**選項 B 留作 backup**：若 V099/V100 確有不可移動的 reserve（如 LG-3 IMPL DISPATCH 已預告 V099），則退化 B。

### 6.3 Race-aware sequencing SOP（V103 → V102 inflight？）

當前無 V102 inflight（DB head = V096 < V101/V102 / V103/V104 全部）。但 spec 自身已標 race：

**Spec-defined race conditions（per V101/V102 spec v3 §2）**：
1. **V097/V098 catch-up 必先 apply**（V098 含 governance.audit_log ALTER constraint，須低寫入窗口）
2. **V096 (drop_dead_learning_tables) 已 apply 且不可逆** — 任何 rollback spec **不得依賴 V096 reversal**
3. **v56 P0-ENGINE-HALTSESSION-STUCK-FIX 完整 cycle 收口** — TODO §3 列「v56 P0 closed but root cause UNRESOLVED」 → PA + QA 須 verdict 此 hard precondition 是否仍 bound

**SOP for V099-V102 (per option A) sequential apply**：

```
Day -2 (D-2): operator 簽 V097/V098 maintenance window（V098 ALTER 須 < 1 min 低寫入）
Day -1 (D-1): ssh trade-core apply V097/V098 → verify head=V098 → 24h baseline observe
Day 0 (D+0): operator 簽 V099/V100 Track v3 dispatch（含 PA finalize spec rename V101/V102 → V099/V100）
Day 0+0.5: E1 dispatch V099 (CREATE TYPE + ADD COLUMN nullable + CREATE 2 new tables + backfill baseline)
Day 1: V099 idempotency 雙跑 + 24h observe
Day 1+0.5: E1 dispatch V100 (ALTER NOT NULL + DEFAULT + per-table-tailored indexes + 4 P&L views)
Day 2: V100 idempotency 雙跑 + 24h observe → head=V100
Day 3: operator 簽 V101/V102 Earn schema dispatch
Day 3+0.5: E1 dispatch V101 (Earn schema CREATE 4 tables; Guard A/B/C)
Day 4: V101 idempotency 雙跑 + 24h observe
Day 4+0.5: E1 dispatch V102 (Earn schema ALTER NOT NULL + indexes if any)
Day 5: V102 idempotency 雙跑 + head=V102 → V099-V102 全 closure
```

**Race-aware guards**（每 V### apply 前必驗）：
1. `psql -c 'SELECT max(version) FROM _sqlx_migrations'` = previous expected head
2. `psql -c "SELECT pg_try_advisory_lock(0x1234)"` — engine 沒在跑同 migration
3. `cargo test -p openclaw_engine --test migrations_test` PASS（Mac）
4. apply 後 `psql -c "SELECT max(version) FROM _sqlx_migrations"` = current expected head
5. apply 後 idempotency 雙跑 = ZERO row mutation on 2nd run

---

## §7 開放 question / 須 operator 拍板

### Q1：V###  re-number 拍板

選項 A vs B（per §6.2）：A 是「全順延 2 號」最乾淨；B 是維持 v5.7 §7.5 命名但 V099/V100 需 reserve 來源。
- **PA verdict**：A 最乾淨；除非 operator 明示 V099/V100 確有不可移動 reserve（LG-3 或 W-AUDIT-8a），否則用 A
- **影響範圍**：4 個 ADR draft（C2，TW × 3 並行 sub-agent draft）必須以 final V### 寫；v5.7 §7.5 spec 必須 search/replace 編號；§ ADR-0033 也須引用 final V###
- **rec timing**：D+0 簽核（Sprint 1A 派發 D-5 前），不等 spec land

### Q2：V097/V098 Phase 0 catch-up maintenance window

- V097 = LG-5 attribution healthcheck indexes（CREATE INDEX CONCURRENTLY 不鎖表）
- V098 = governance.audit_log ALTER constraint（須低寫入窗口，spec v3 line 27 標）
- **operator action**：簽 V098 apply 之 maintenance window（建議低交易時段，Phase 2a 14d observation verdict 視窗 2026-05-22~23 UTC 之前或之後）
- **race with Phase 2a**：V097/V098 apply 期間 engine 不寫 governance.audit_log → 影響 Phase 2a sample 累積 ≈ V098 apply 持續時間（預期 30 sec-2 min；可接受）

### Q3：V101/V102 spec v3 hard precondition「v56 P0 完整 cycle 收口」是否仍 bound

- TODO §3 v56 P0 HALT cycle **CLOSED** 2026-05-20，但 root cause **UNRESOLVED**（`P1-HALT-TRIGGER-ROOT-CAUSE-INVESTIGATION-1` passive wait）
- spec v3 寫「v56 P0 完整 cycle 收口」是否 = closure + root cause resolved，抑或 closure 即可
- **PA verdict 建議**：closure 即可（passive wait 90d review 不 block V099/V100 Track v3 派發）
- **operator action**：確認 PA verdict

### Q4：Earn schema spec C3（v5.7-C3）finalize 編號

- v5.7-C3 draft 預期 land：`docs/execution_plan/2026-05-21--v103_v104_earn_hypotheses_schema_spec.md`
- 若 option A 採用，**改名**：`docs/execution_plan/2026-05-21--v101_v102_earn_hypotheses_schema_spec.md`
- **operator action**：簽 final V### 後 PA 立即派 MIT + CC + FA + TW draft（C3，8-12 hr）

### Q5：v5.7 §7.5 「V104 與 V101 spec 重複」consolidation 判斷無效

- v5.7 §7.5 line 18-19：「V101 spec v3 §1 已 ALTER trading.fills.track，**V104 退號**（per R4 + MIT 建議）」 — 此判斷基於 **錯誤前提**（V101 spec **未** land；trading.fills **無** track column）
- **更正後判斷**：V104 (option A 後重編為 V102) **不退號** — Earn schema 有獨立 `trading.fills.track` ADD COLUMN 需要嗎？檢查 v5.7 §7.5 Table 3 spec...
- v5.7 §7.5 Table 3 寫 `trading.fills.track` ADD COLUMN — 但這跟 V099/V100 Track v3 spec §1 「ADD COLUMN nullable on 12 existing tables」**重疊**
- **真正應退號者**：v5.7 §7.5 Table 3（`trading.fills.track`）— 因 V099/V100 Track v3 已涵蓋 trading.fills.track，Earn schema 不需自己再加
- **operator action**：MIT + FA 確認 v5.7 §7.5 Table 3 是否與 V099/V100 spec 重複；若是，Earn schema V101/V102（option A）只剩 3 表（hypotheses + hypothesis_preregistration + earn_movement_log）

### Q6：strategy_track ENUM 是否包含 Earn 路徑 track

- V099/V100 Track v3 spec：strategy_track ENUM `baseline / experimental / ...`
- Earn movement 是否需要在 strategy_track ENUM 加 `earn` value？
- **operator + MIT action**：spec v3 §2.3 找 ENUM value list；earn_movement_log.api_scope_used 是否 vs strategy_track ENUM 重疊

### Q7：派工 prompt 假設 `psql -d openclaw -U openclaw` 在所有 future audit script 全錯

- 派工 prompt §-1 fallback：「grep `helper_scripts/db/audit/*.py` 找連線範例」 — 已驗證所有現有 audit script 用 `trading_admin / trading_ai`
- **TW action**：CLAUDE.md / docs/agents/context-loading.md 加 PG connection 範例段，明示 `trading_admin / trading_ai`，未來 PA / E1 / E4 派工 prompt 不再誤導

---

## §8 Sign-off

| 項 | 狀態 |
|---|---|
| Q1-Q4 query 全 PASS | ✓ |
| Read-only 約束 | ✓ |
| 中文標題 + SQL 保留英文 | ✓ |
| `srv/` 永久檔範圍：本 spec | ✓ |
| Side-effect 0（無 DDL/CREATE/ALTER/DROP）| ✓ |

**Operator next action**：
1. 拍板 §7 Q1 V### re-number 選項 A 或 B
2. 簽 §7 Q2 V097/V098 maintenance window 時間
3. 拍板 §7 Q3 v56 P0 hard precondition 是否仍 bound
4. Q4-Q7 PA + MIT + TW 後續 follow-up

**PA dispatch readiness**：v57-C3（V### schema spec draft）派發前須先收 Q1 verdict。其他 11 個 v57-C1..C12 不被本 dry-run 阻塞。
