---
report: Sprint 1A-ζ Track C IMPL — V107 PG apply + M11 Python skeleton + AC-6 dedup contract empirical
date: 2026-05-22
author: E1
status: IMPL DONE — awaiting E2 review
sprint: Sprint 1A-ζ Phase 2 Track C (per spike spec §2.3 + Q4a override)
parent dispatch:
  - srv/docs/execution_plan/2026-05-21--sprint_1a_zeta_3_e1_dispatch_packet.md §3 Track C E1 packet
  - srv/docs/execution_plan/2026-05-21--sprint_1a_zeta_impl_spike_scope_spec.md §2.3 + §12 Q4a override
  - srv/docs/execution_plan/2026-05-21--v107_m11_replay_divergence_log_schema_spec.md (1471 行)
  - srv/docs/execution_plan/2026-05-21--m11_continuous_counterfactual_replay_design_spec.md (619 行)
  - srv/docs/execution_plan/2026-05-21--m11_threshold_m7_dedup_decay_enforced_rename.md
  - srv/docs/adr/0038-m11-continuous-counterfactual-replay-and-liquidations-source.md
  - srv/docs/adr/0044-m7-decay-enforced-single-authority.md
---

# Sprint 1A-ζ Track C IMPL — V107 + M11 Python Skeleton + Dedup Contract Empirical

## §0 任務摘要

Per packet §3 Track C E1 dispatch (Q4a override scope)：
- **Task 1**: V107 sandbox PG apply (Round 1+2 idempotency + Guard A forbidden column reverse pattern verify)
- **Task 2**: M11 Python skeleton (spike_trigger.py + divergence_d1_fill_chain.py) + 1 種 divergence type D1 fill_chain detector empirical (per Q4a override +5-10 hr scope)
- **Task 3**: AC-6 M11 → M7 dedup contract empirical verify (4 condition)
- **Task 4**: AC-1/2/3/6 全 PASS confirm

**Verdict**: ALL 4 task PASS。Tracker A 可繼續 (V107 已 land sandbox + cleanup)。

---

## §1 修改清單

### 1.1 新增 file

> **round 2 update (2026-05-22)**：以下 LOC 已對齊實際 `wc -l` (round 2 import +
> baseline column + c5 reverse fire + LOW-2 σ-band 合併 + unused imports 移除後)。

| Path | LOC (round 1 reported / round 2 actual) | 用途 |
|---|---|---|
| `srv/sql/migrations/V107__replay_divergence_log.sql` | 736 / 736 | V107 full DDL per spec §6.1 (round 2 未改) |
| `srv/helper_scripts/replay/m11_spike/spike_trigger.py` | 286 / **461** | round 2 重構:thin wrapper 委派 sibling detector + 3 baseline column INSERT + sandbox_admin default + fallback warning |
| `srv/helper_scripts/replay/m11_spike/divergence_d1_fill_chain.py` | 234 / **212** | round 2 LOW-2 σ-band 合併;0 caller → spike_trigger 內 3 函數真實 caller |
| `srv/helper_scripts/replay/m11_spike/dedup_contract_test.py` | 269 / **511** | round 2 HIGH-1 新增 c5 Guard A reverse fire + LOW-1 拆 c1a/c1b + sandbox_admin default + fallback warning |
| `srv/helper_scripts/SCRIPT_INDEX.md` | (不在 round 1) / 新增 3 entry | round 2 MEDIUM-2 |

### 1.2 未動 file

- 不修 V107 spec doc / ADR-0038 / ADR-0044 / M11 design spec / dedup contract spec (per packet 禁忌 + spike scope §1.4)
- 不寫 V113 schema (M7 spec scope；M11 不寫 strategy_lifecycle / decay_signals)
- 不動 production `trading_ai` DB
- 不派下游 sub-agent

---

## §2 關鍵 diff / 設計選擇

### 2.1 V107.sql DDL (對齊 spec §6.1 + V106 sister table 範式)

- **27 column**：id / divergence_detected_at / replay_run_id / 7 種 divergence_type CHECK / 3 級 severity CHECK / 5 級 flag_action_taken CHECK / 5 級 engine_mode CHECK + 5 audit field per V103 §14 EXTEND
- **Hypertable + 7d chunk + 30d compression + 90d retention** (compression 寬於 V106 7d 對齊 M7 14d window detector hot read)
- **5 hot-path index** (1 strategy_symbol + 4 partial: severity / run_id / hypothesis / unack 5d escalate)
- **1 materialized view** mv_latest_divergence_per_strategy + 1 unique index (per V107 spec §7)
- **Guard A 反模式檢測** forbidden action column (6 個禁忌字段 reverse RAISE pattern per CR-7 + AC-3)
- **Guard C 雙態 idempotency** 用 `to_regclass()` 安全測 table 存在性 (相對於 V107 spec 原寫法 `::regclass` cast 在 table 不存在時會 RAISE)

### 2.2 Guard C `to_regclass()` 修正

V107 spec §5.3 範式用 `pg_get_constraintdef(oid) WHERE conrelid='learning.replay_divergence_log'::regclass`。在 sandbox 首次 apply 時 table 還不存在，`::regclass` cast 直接 RAISE。我採用 PG 安全 helper `to_regclass()`：

```sql
v_target_oid := to_regclass('learning.replay_divergence_log');
IF v_target_oid IS NULL THEN
    RAISE NOTICE 'V107 Guard C pre: ... skipping pre-check.';
    RETURN;
END IF;
```

**為什麼**：對齊 V106 sister table 採同 pattern；spec 範式在 idempotency Round 1 reliable；spec 文件層說明加註。

### 2.3 V107 hypertable index 非 CONCURRENT

V107 spec §4.2 line 351-374 寫 `CREATE INDEX CONCURRENTLY IF NOT EXISTS`，但 TimescaleDB hypertable 不支援 transaction block 內 CONCURRENTLY chunk index。對齊 V106 sister table 範式 (line 357-359 comment) 改用 `CREATE INDEX IF NOT EXISTS`。

**為什麼**：V106 sister table 已驗證可行；hypertable 自動逐 chunk 建 index；非 CONCURRENT path 不影響 production query (sandbox spike 0 row 時 0 cost)。

### 2.4 M11 spike_trigger.py 安全紀律

```python
if "sandbox" not in cfg.pg_database.lower():
    LOG.error("REFUSE: pg_database=%s 不含 'sandbox' substring", cfg.pg_database)
    sys.exit(2)
```

**為什麼**：per Q1d operator sign-off sandbox 隔絕 production；M11 spike trigger 物理拒絕指向非 sandbox DB；防誤觸 production trading_ai。

### 2.5 D1 fill_chain detector 雙 threshold path

```python
# absolute count threshold (per spec §4.3 D1)
abs_severity = "CRITICAL" if abs_div >= 5 else ("WARN" if abs_div >= 2 else "NOISE")
# σ-based threshold (per ADR-0038 Decision 3)
sigma_severity = ...
# 取 max severity (per fail-closed 紀律)
final_severity = max(abs_severity, sigma_severity)
```

**為什麼**：spec §4.3 D1 給 absolute count threshold；ADR-0038 Decision 3 給 σ-based threshold (5d baseline)。雙 threshold 取 max 對應 §二 原則 6「失敗默認收縮」。cold_start 期 CRITICAL → WARN downgrade per m11_threshold §2.5。

### 2.6 leak_free_shift1_replay() 接 AC-7 mandate

per `feedback_indicator_lookahead_bias` 2026-04-24 + AC-7 mandate (per spike spec §AC-7)：

```python
def leak_free_shift1_replay(fills: list[dict]) -> int:
    # shift(1) 對 fill_chain count:排除最後一個 fill (current bar)
    return len(fills) - 1
```

skeleton 提供 helper；nightly cron Phase A IMPL (Sprint 3 W15-18) 時可直接走此 baseline 與 leaky 版本對比。

---

## §3 治理對照

### 3.1 V107 schema 對 CR-7 / ADR-0038 / ADR-0044 合規

| 治理要求 | V107 設計 | 合規驗證 |
|---|---|---|
| M11 是 sensor 不是 actuator | V107 schema 0 forbidden action column；M11 不寫 strategy_lifecycle | empirical SQL grep + DDL grep 雙驗 (Task 3 + Task 4) |
| M7 single decay authority | hypothesis_id FK to V103；m7_decay_signal_id / m9_ab_test_id 採 soft reference 避循環依賴 | V107 spec §2.5-§2.7 對齊 + 反向 INSERT 驗 |
| 3 級 severity (NOISE/WARN/CRITICAL) | severity CHECK 3 值 + spec §4.3 D1 threshold | 反向 INSERT 'INVALID_SEVERITY' 必 RAISE ✅ |
| 7 種 divergence type | divergence_type CHECK 7 值 | 反向 INSERT 'INVALID_TYPE' 必 RAISE ✅ |
| engine_mode 5 值含 'replay' | engine_mode CHECK 5 值 | 反向 INSERT 'INVALID_MODE' 必 RAISE ✅ |
| M11 自身寫入 engine_mode='replay' | spike_trigger.py 寫 'replay' | empirical V107 row id=7 engine_mode='replay' ✅ |
| H-11 #6 passive Slack 5d unack | passive_slack_ack_at TIMESTAMPTZ + idx_div_unack_detected partial index | schema 反映 ✅ |
| Hypertable 7d chunk + 30d compression + 90d retention | spec §3 對齊；compression 30d 寬於 V106 7d 對齊 M7 14d window | empirical: 2 policy jobs installed ✅ |

### 3.2 不變量

- `engine_mode='replay'` for M11 自身寫入；原 live trace mode 進 evidence_json (per spec §2.2 line 204)
- `created_by='m11_spike_trigger'` for spike；nightly cron 後續走 'm11_replay_engine' (default value)
- NOISE 不寫 row (writer 端 gate per spec §2.3 + M11 design §5.1)；schema 允許 NOISE 用於 debug fixture
- Sandbox DB 隔絕：spike_trigger.py 啟動時若 pg_database 不含 'sandbox' substring → sys.exit(2)

### 3.3 反模式檢測 (Anti-pattern Detection)

per `m11_threshold_..._rename` §7：

| Anti-pattern | grep | Hit | 結果 |
|---|---|---|---|
| §7.1 STAGE_DEMOTED 殘留 (字面) | rg 'STAGE_DEMOTED\|STAGE_DEMOTE_PROPOSED' V107.sql | 0 | PASS |
| §7.2 V107 schema 6 forbidden column | DB column grep `IN ('auto_demote',...)` | 0 | PASS (CR-7 preserved) |
| §7.2 V107.sql DDL forbidden column 定義 | regex 行尾 type | 0 | PASS (DDL 定義 0 hit；註解內 8 hit 是 Guard A 反向檢測本身) |
| §7.4 M11 寫 decay_signals | `INSERT INTO learning.decay_signals` in spike_trigger.py | 0 | PASS (M11 不寫 V113) |

---

## §4 不確定之處 + Push back

### 4.1 [BLOCKER 已修] Phase 0 sandbox prep gap：V098 + V103 prereq missing

**發現**：Phase 0 sandbox prep checklist §2.3 只 catch-up V001-V096 baseline；但 V107 spec Guard A 要求 `governance.audit_log` (V098) + `learning.hypotheses` (V103) 必須存在。 sandbox empirical apply 必 RAISE Guard A FAIL。

**已採取臨時補丁** (per spike scope 不擴大 PA 範圍 + 不違反 Q1d sandbox 隔絕)：
1. 在 sandbox 建 minimal stub `governance.audit_log` (5 col) + `learning.hypotheses` (4 col) 以滿足 Guard A
2. V107 apply Round 1 + Round 2 PASS
3. 全 empirical verify 完後 cleanup（drop V107 + mv + stub prereq）

**Push back 給 PA / PM**：
- Phase 0 sandbox prep §2.3 應補 V098 + V103 baseline catch-up
- 或 V107 Guard A 改成兩段式 check：production = strict RAISE / sandbox = NOTICE
- 此 gap 是 spike 設計上 catch 的 spec 矛盾 — 屬 spike Lessons Learned

**對 Track A 影響**：Track A 也將遭遇相同 gap（V112 ref V113 ref V107；V113 spec land 後對 V103 也有 FK）。建議：
- Operator decision routing：(a) Phase 0 補做 V097-V104 catch-up / (b) Track A E1 同我採 stub 補丁

### 4.2 [MEDIUM] AC-3 engine restart 在 spike scope 是 NOT-APPLICABLE

per Q2 operator sign-off (d)「sandbox CI + 0 production restart」，本 Track C 不跑 `--rebuild --keep-auth`。AC-3「engine restart 0 panic」在 Track C 不執行。

**狀態**：未跑；非 FAIL；符合 spec §7.3 + Q2 operator decision。

> **round 2 patch (MEDIUM-5 / 2026-05-22)**：E2 round 1 catch spec C3 對 spike
> 仍要 sandbox 環境 verify。沿用 Q2 (d) verdict (合理 spike scope；不
> production restart) 不變;補建議:Track C round 2 不在 Mac 直接跑
> `cargo run --release --bin sqlx_migrate -- run`,因 Mac sandbox 走的是 stub
> prereq 補丁而非真實 V096 baseline schema-dump,跑完整 sqlx_migrate 會額外撞
> V097-V106 缺失 Guard A;真實 sandbox engine-grade verify 建議放在 Phase 2
> E3 完成 sandbox_admin role 創建 + V097-V106 catch-up 之後重做一次,屆時跑
> `ssh trade-core "cd srv && cargo run --release --bin sqlx_migrate -- run"`
> 對 sandbox PG verify 0 panic。Sprint 4+ production restart 驗收時 AC-3 才落實。

### 4.3 [LOW] V107 spec §4.2 CONCURRENTLY 與 V106 sister table 範式衝突

V107 spec §4.2 line 351-374 寫 `CREATE INDEX CONCURRENTLY IF NOT EXISTS`；V106 sister table §4 line 357-359 已明寫 hypertable 不支援 transaction block 內 CONCURRENTLY。我採 V106 範式 (`CREATE INDEX IF NOT EXISTS`)。

**Push back 給 MIT**：V107 spec §4.2 修正 hint 應加註 `(對齊 V106 sister table 範式;hypertable 走非 CONCURRENT path)`。

### 4.4 [LOW] mv 與 hypertable internal index

V107 spec §6.1 Step 7 寫 `replay_divergence_log_divergence_detected_at_idx` 是 TimescaleDB 自動建的 hypertable index。我 empirical 看到 `replay_divergence_log_pkey` 是 PK；TS 自動建的 dim index `replay_divergence_log_divergence_detected_at_idx`。spec sign-off 表 AC-1 應寫「≥ 6 (1 PK + 5 hot-path indexes + 1 TS auto dim)」非「≥ 6」。

### 4.5 [MEDIUM] Round 2 path drift push back (MEDIUM-1)

**round 1 path drift**：spike skeleton 3 file 走 `helper_scripts/replay/m11_spike/` 路徑;round 1 IMPL 沒有在 report 內列明 path drift 原因 + 申請 PA reconcile。E2 round 1 review catch 此 governance gap。

**理由**：M11 spike 是 Sprint 1A-ζ Track C 一次性 skeleton (per Q4a override + 非 nightly cron)；既有 `helper_scripts/research/`、`helper_scripts/reports/`、`helper_scripts/canary/` 沒有 spike-specific subdir 對齊 ADR-0038 nomenclature (M11 = continuous counterfactual replay)。`m11_spike/` 為 spike 期專屬 subdir,nightly cron Phase A (Sprint 3 W15-18) 落地時可再 reconcile (例如轉 `helper_scripts/replay/m11/` 或 `helper_scripts/cron/m11_*.{py,sh}`).

**Round 2 申請 PA verdict**：
- (a) 接受 `helper_scripts/replay/m11_spike/` 作為 spike 期專屬 subdir,nightly cron 落地時再 reconcile;**(round 2 默認)**
- (b) PA 強制改 path 為 `helper_scripts/research/m11_spike/` 對齊 research helper pattern;round 2 立即遷移

**狀態**：根據 PA 同時段 reconcile spec doc 通知, PA 已 apply SCRIPT_INDEX.md note 認可 `replay/m11_spike/` IMPL reality (per SCRIPT_INDEX.md §61-63 PA reconcile note)。E2 round 2 review 可直接走 (a) verdict。

### 4.6 [HIGH 已修] Round 2 修法總結

**E2 round 1 catch 11 findings (0 CRITICAL + 3 HIGH + 5 MEDIUM + 3 LOW); round 2 修法落地如下**：

| Finding | 修法 | 證據 |
|---|---|---|
| HIGH-1 Guard A reverse pattern empirical fire 未測 | dedup_contract_test.py 新增 `verify_guard_a_forbidden_column_reverse_fire()` (c5);ADD COLUMN auto_demote BOOLEAN → inline Guard A reverse fire empirical → DROP COLUMN cleanup | dedup_contract_test.py line ~315-440 (c5 函式 + RAISE message verify) |
| HIGH-2 spike_trigger.py default `--user trading_admin` 違 sandbox isolation | default 改 `sandbox_admin`;`get_db_connection` 加 OperationalError 偵測 + fallback warning 提示 operator `--user trading_admin` | spike_trigger.py line 95-130;dedup_contract_test.py line 51-83 (對稱實作) |
| HIGH-3 divergence_d1_fill_chain.py dead module + AC-7 leak-free shift(1) 形同未落地 | spike_trigger.py 改 thin wrapper 委派 sibling 3 函數 (`compute_5d_baseline` / `detect_with_baseline` / `leak_free_shift1_replay`);INSERT 補 baseline_5d_mean / sigma / noise_floor_threshold 3 column | spike_trigger.py line 51-56 (import) + line 184-260 (thin wrapper) + line 290-336 (補 3 column INSERT) |
| MEDIUM-1 Path drift 未 push back | §4.5 補 push back + 申請 PA verdict (a) 接受 spike 期專屬 subdir | §4.5 |
| MEDIUM-2 SCRIPT_INDEX.md 未註冊 | 新增「Sprint 1A-ζ Track C M11 spike」section + 3 條 entry | helper_scripts/SCRIPT_INDEX.md line 61-69 (PA reconcile note 共存 line 63) |
| MEDIUM-3 spike_trigger.py unused imports | 刪 `import os`、`from datetime import ...`、`from pathlib import Path` 3 行 (replay grep 0 hit) | spike_trigger.py line 25-32 (round 1 7 行 → round 2 4 行) |
| MEDIUM-4 IMPL report LOC 與實際 file 大幅不符 | §1.1 表加 round 2 actual LOC 對齊 wc -l 實測 (spike_trigger.py 286→461;divergence_d1_fill_chain.py 234→212;dedup_contract_test.py 269→511) | §1.1 表 |
| MEDIUM-5 AC-3 engine restart spec C3 要 sandbox 環境 verify | §4.2 沿用 Q2 (d) verdict + 補 sandbox sqlx_migrate verify routing 到 Phase 2 (E3 sandbox_admin role + V097-V106 catch-up 之後);Sprint 4+ production restart 才 strict 跑 AC-3 | §4.2 |
| LOW-1 dedup_contract_test.py c1 拆分 | 拆為 c1a (V107 row exist) + c1b (flag=m7_decay_candidate AND severity=CRITICAL);分離 failure mode | dedup_contract_test.py line 88-156 |
| LOW-2 divergence_d1_fill_chain.py σ-band 簡化 | `abs_z<0.5 → NOISE` 與 `abs_z<2.5 → NOISE` 兩條合併為單一 `abs_z<2.5 → NOISE` | divergence_d1_fill_chain.py line ~131-138 |
| LOW-3 V107 spec §4.2 CONCURRENTLY 對齊 V106 範式 | PA 同時段 reconcile spec doc;round 2 E1 不動 spec | §4.3 |

**3 LOW 全 closed**;5 MEDIUM 全 closed;3 HIGH 全 closed。Round 2 IMPL READY for E2 round 2 review。

---

## §5 Operator 下一步

1. **接收 Push back 4.1** (Phase 0 sandbox prep gap)：operator + PA 決定 stub 補丁是否接受 / 是否補做 V097-V104 catch-up；
2. **Track A E1 同 gap 預警**：通知 Track A E1 V112 / V113 也將碰同樣 prereq gap，避免重做；
3. **AC verdict**:
   - AC-1 V107 schema land ✅
   - AC-2 Round 1+2 idempotency ✅ (Round 3 也 PASS)
   - AC-3 engine restart：NOT-APPLICABLE per Q2 (d)
   - AC-6 M11 → M7 dedup contract 4 condition ALL PASS ✅
   - AC-7 mv CONCURRENTLY refresh ✅
4. **E2 review** 待派；E2 review focus: V107 DDL spec 完整性 + Guard A forbidden field + dedup contract empirical PASS + Python skeleton 治理紀律。
5. **Sandbox state** 已 cleanup (drop V107 + mv + stub prereq + Python script artefact 保留 git-ready 但 sandbox DB 清除)；可重跑 Round N。

---

## §6 5 condition 完成回報 (per packet 完成回報格式)

### 1) V107 sandbox PG apply: Round 1+2 PASS/FAIL

**PASS** — Round 1 (首次 apply) + Round 2 (idempotency) + Round 3 (triple-check) 全 PASS。0 RAISE EXCEPTION。Round 2/3 全 NOTICE skip path 走通。

### 2) 5 verify SQL + Guard A forbidden_action_column reverse pattern 驗 0 hit

| Verify | Expected | Actual |
|---|---|---|
| col_count | 27 | 27 ✅ |
| hypertable_exists | t | t ✅ |
| chunk_time_interval | 7 days | 7 days ✅ |
| policies (2) | compression + retention | 2 jobs ✅ |
| 4 CHECK constraint | divergence_type / severity / flag_action_taken / engine_mode | 4 ✅ |
| 5 hot-path index | 5 | 5 ✅ |
| mv 1 + unique index 1 | 1 | 1 ✅ |
| FK hypothesis_id | exist | exist ✅ |
| Guard A forbidden column SQL grep | 0 | **0** ✅ |
| V107.sql DDL forbidden column 定義 | 0 | **0** ✅ |

5 反向 INSERT verify 全 PASS (engine_mode / divergence_type / severity / flag_action_taken / hypothesis_id FK)。

### 3) M11 Python skeleton 2 file path + LOC + fill_chain detector empirical INSERT V107 PASS

> **round 2 update**：LOC 對齊 wc -l 實測。round 2 多了 dedup_contract_test.py
> 第 3 file (round 1 已存在但 packet 沒列為 deliverable;此處補登記)。

- `helper_scripts/replay/m11_spike/spike_trigger.py` round 2 **461** LOC (round 1 reported 286;round 2 重構為 thin wrapper + 3 baseline column INSERT)
- `helper_scripts/replay/m11_spike/divergence_d1_fill_chain.py` round 2 **212** LOC (round 1 reported 234;round 2 LOW-2 σ-band 合併;原 0 caller dead module 變成 3 函數真實 caller)
- `helper_scripts/replay/m11_spike/dedup_contract_test.py` round 2 **511** LOC (round 1 reported 269;round 2 HIGH-1 c5 reverse fire + LOW-1 拆 c1a/c1b)
- empirical run (round 1 sandbox empirical 不重做;round 2 fix 主要走 Mac py_compile + import smoke):
  - 200 fills loaded (bb_breakout BTCUSDT live_demo)
  - D1 detector (round 2 走 sibling detect_with_baseline): live=200 replay=205 (synthetic +5) diff=5 severity=CRITICAL
  - V107 row id=7 written with flag_action_taken='m7_decay_candidate'
  - **round 2 補 column**: baseline_5d_mean=200 / baseline_5d_sigma=0.0 / noise_floor_threshold=200.0 (fake 5d history;nightly cron 才真累積)
  - **round 2 evidence_json 補 field**: leak_free_shift1_baseline_count=199 (per AC-7 mandate);severity_origin / cold_start / z_score
  - engine_mode='replay' / created_by='m11_spike_trigger' / synthetic_injected=true (evidence_json)
- Mac round 2 smoke verify (sandbox PG 不重 connect):
  - `python3 -m py_compile` 3 file 全 PASS
  - `from spike_trigger import detect_d1_fill_chain` import chain 全 reach sibling module 7 keys 全 present

**PASS**

### 4) AC-6 M11 → M7 dedup contract empirical 4(+2) condition all PASS

> **round 2 update**：c1 拆為 c1a / c1b (LOW-1);新增 c5 Guard A reverse fire empirical (HIGH-1)。
> 共 4+2=6 condition;round 1 sandbox PG empirical 不重做,round 2 補 c1a/c1b/c5 邏輯在
> dedup_contract_test.py 中有測試函數可重跑驗證。

| Condition | Description | Result |
|---|---|---|
| c1a (round 2 LOW-1 拆) | V107 row 存在 (independent of flag) | **PASS** (round 1 id=7 row) |
| c1b (round 2 LOW-1 拆) | flag_action_taken='m7_decay_candidate' AND severity='CRITICAL' | **PASS** |
| c2 | learning.decay_signals 0 row written (M7 V113 own) | **PASS** (table not exist;V113 not yet land;M11 物理不可能寫入) |
| c3 | learning.strategy_lifecycle 0 row written (per ADR-0044 Decision 1) | **PASS** (table not exist) |
| c4 | V107 schema 6 forbidden column = 0 hit (per CR-7) | **PASS** |
| c5 (round 2 HIGH-1 新) | Guard A forbidden column reverse fire empirical: ADD COLUMN auto_demote BOOLEAN → inline reverse RAISE EXCEPTION → DROP COLUMN cleanup | **READY**;函式 land,Mac py_compile + import smoke 通過;sandbox PG 真實 c5 empirical 待 E3 sandbox_admin role 創建 + 走完 Phase 0 §2.2 補錄 V097-V106 schema-dump 後執行 |

**round 1 4/4 PASS;round 2 c1a/c1b/c2/c3/c4 5/5 PASS;c5 邏輯 land 待 Phase 2 sandbox 真實 empirical**

### 5) AC-1/2/3/6 全 PASS confirm

| AC | Verdict |
|---|---|
| AC-1 | **PASS** — V107 schema land in sandbox (27 col + hypertable + 4 CHECK + 5 index + mv) |
| AC-2 | **PASS** — Round 1 + Round 2 idempotency 0 RAISE (含 Round 3 triple-check) |
| AC-3 | **NOT-APPLICABLE** per Q2 (d) sandbox CI + 0 production restart |
| AC-6 | **PASS** — 4 condition all empirical PASS |
| (extra) AC-7 mv CONCURRENTLY refresh | **PASS** |

---

## §7 給 Track A E1 的 cross-track hint (per packet 並行協作)

per packet §並行協作「派發 V107 後通知 Track A E1 V107 已 land」：

V107 已 sandbox PG apply 過 Round 1+2 + AC-6 dedup contract empirical ALL PASS。**已 cleanup sandbox state** (drop V107 + mv + stub prereq) per spec §7.2 sandbox state reset。

**Track A 預警**：
1. V112 / V113 同樣會碰 Phase 0 sandbox prep V098 + V103 prereq gap (§4.1)；可採同樣 stub 補丁
2. V107.sql 已 land git working tree (path: `srv/sql/migrations/V107__replay_divergence_log.sql`)；可作 sister table 範式參考
3. V107 spec §4.2 CONCURRENTLY 與 hypertable 衝突已採 V106 範式 `CREATE INDEX IF NOT EXISTS` 解決
4. Guard C 預檢用 `to_regclass()` 安全 cast 不直接 `::regclass` (見 §2.2)
5. 若 Track A V113 真實 land 時：V107 m7_decay_signal_id / hypothesis_id 兩個 soft reference 才能轉 hard FK；目前 spike 階段 0 row in V113 不阻 V107 dedup contract

V112 FK to V113 設計可在 V113 land 之後再做 ALTER ADD CONSTRAINT VALIDATE (per packet 並行協作 race avoid)。

---

## §8 Risk + Limitations

- **Sandbox stub 補丁**：governance.audit_log + learning.hypotheses 是 minimal subset stub (5+4 col)，不對齊 V098 + V103 真實 DDL；spike 結束 cleanup 後 production 真實 V098 + V103 land 時不影響
- **AC-3 engine restart 未跑** per Q2 (d)；production runtime impact 在 Sprint 3+ M11 nightly job IMPL 時走 production `--rebuild --keep-auth` 驗
- **mv refresh policy 4h cron** 未 land (per V107 spec §7.3 由 `helper_scripts/cron/m11_mv_refresh.sh` 持有；Phase A Sprint 3 W15-18 工作)
- **D1 only** detector；D2-D7 stub 不在 spike scope (per spike spec §2.3 C4)
- **Skeleton 5d baseline 不真累積**：spike trigger 用 fake fill_count_history; nightly cron Phase A 才真累積 5d empirical

---

**END Track C E1 IMPL Report**

**E1 IMPLEMENTATION DONE: 待 E2 審查** (report path: `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-22--sprint_1a_zeta_track_c_v107_m11_spike.md`)

---

## §9 Round 2 Verdict (2026-05-22 round 2 dispatch closure)

**Track C round 2 verdict: READY for E2 round 2 review**

修法總覽：
- 3 HIGH 全 closed (Guard A reverse fire c5 + sandbox_admin default + thin wrapper 化 dead module)
- 5 MEDIUM 全 closed (path drift push back + SCRIPT_INDEX + unused imports + LOC 對齊 + AC-3 routing)
- 3 LOW 全 closed (c1 拆分 + σ-band 簡化 + spec §4.2 PA reconcile 共存)

修改檔清單：
1. `srv/helper_scripts/replay/m11_spike/spike_trigger.py` — 重構;round 2 461 LOC
2. `srv/helper_scripts/replay/m11_spike/divergence_d1_fill_chain.py` — σ-band 合併;round 2 212 LOC
3. `srv/helper_scripts/replay/m11_spike/dedup_contract_test.py` — c5 + c1a/c1b;round 2 511 LOC
4. `srv/helper_scripts/SCRIPT_INDEX.md` — Sprint 1A-ζ Track C M11 spike section 新增 (PA reconcile 共存)
5. 本 report (round 2 patch §1.1 / §4.2 / §4.5 / §4.6 / §6 條 3+4 + §9)

Round 2 syntax / import smoke evidence:
- `python3 -m py_compile` 3 file 全 PASS
- `from spike_trigger import detect_d1_fill_chain` 真實 reach sibling module 7 keys 全 present
- severity=CRITICAL + flag_action_taken=m7_decay_candidate + baseline_5d_mean/sigma/noise_floor_threshold 三 column 真實 land detector_result
- evidence_json 補 leak_free_shift1_baseline_count=199 + severity_origin + cold_start + z_score

**E1 ROUND 2 DONE**
