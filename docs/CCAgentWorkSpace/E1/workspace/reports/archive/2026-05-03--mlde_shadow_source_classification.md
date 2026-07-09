# REF-20 R20-P0-T7 — `learning.mlde_shadow_recommendations.source` 分類 SELECT DISTINCT
# REF-20 R20-P0-T7 — `learning.mlde_shadow_recommendations.source` classification SELECT DISTINCT

**日期 / Date：** 2026-05-03
**Owner：** E1 (sub-agent, Wave 1 task; PM 主會話 final classify ambiguous)
**契約上游 / Upstream contract：**
- `docs/execution_plan/2026-05-03--ref20_implementation_workplan_v1.md` §4 Wave 1 R20-P0-T7
- `docs/execution_plan/2026-05-03--ref20_paper_replay_lab_dev_plan_v3.md` §4.2 (`evidence_source_tier` retrofit allowlist + ambiguous classification)

**Mode：** READ-ONLY ssh `psql` SELECT；0 INSERT/UPDATE/DELETE 寫入 / 0 features payload 拉取（避免敏感數據 + 大 row）.
**Mode (EN):** READ-ONLY ssh `psql` SELECT; zero writes; zero features payload pulls (avoid sensitive data + large rows).

**SSH bridge：** ✅ reachable — `ssh trade-core "echo SSH_OK"` returns OK；DB connection via `.pgpass` working.

---

## 0. TL;DR

- **DISTINCT source 值 / Distinct source values：3**（schema CHECK 允許 4 但 1 個無實際 row）
- **All-time row count：2,482**（2026-04-29 19:38 onwards；schema V031 deploy 後）
- **Allowed for replay 分類：3 / 3**（全部 已知 producer，不在 `live` real-money path）
- **Forbidden for replay：0**（無 source 屬於 live trading mutation 路徑）
- **Ambiguous for PM：0**（schema CHECK 限定，無 unknown / NULL / `test_*` / `backfill_*` source value）
- **NULL source：0**（schema 為 NOT NULL CHECK；migration V031 enforced）

⚠️ **重要 caveat / Important caveat：**
雖然所有 source 值都是 known producer name，但 27 row engine_mode='live'（實為 LG-5 promotion-candidate audit row by `mlde_demo_applier._insert_live_candidate`，applied=false）。**這 27 row 的 source='ml_shadow' 但 engine_mode='live'**，R20-P2a-S6 retrofit 時必須保留此語意（V3 §4.2 evidence_source_tier 必接受 `real_outcome` 配 engine_mode='live' 且 applied=false）。

---

## 1. SQL probe 命令 / SQL probe commands

### 1.1 SELECT DISTINCT(source) + count + ts range

```bash
ssh trade-core "psql -h 127.0.0.1 -U trading_admin -d trading_ai -c \
  \"SELECT source, COUNT(*) AS row_count, MIN(ts) AS earliest_ts, MAX(ts) AS latest_ts \
    FROM learning.mlde_shadow_recommendations \
    GROUP BY source ORDER BY row_count DESC;\""
```

### 1.2 cross-tab source × engine_mode

```bash
ssh trade-core "psql -h 127.0.0.1 -U trading_admin -d trading_ai -c \
  \"SELECT source, engine_mode, COUNT(*) AS rows \
    FROM learning.mlde_shadow_recommendations \
    GROUP BY source, engine_mode ORDER BY source, rows DESC;\""
```

### 1.3 schema CHECK introspection

```bash
ssh trade-core "psql -h 127.0.0.1 -U trading_admin -d trading_ai -c \
  '\\d learning.mlde_shadow_recommendations' | grep -A2 'source'"
```

---

## 2. SELECT DISTINCT 結果 / Results

### 2.1 source 分布（all-time, 2026-04-29 → 2026-05-03）

| source | row_count | % | earliest_ts | latest_ts |
|---|---:|---:|---|---|
| `ml_shadow` | **1,185** | 47.7% | 2026-04-29 19:38:21 | 2026-05-03 00:43:40 |
| `dream_engine` | **1,117** | 45.0% | 2026-04-29 19:38:22 | 2026-05-03 00:43:40 |
| `opportunity_tracker` | **180** | 7.3% | 2026-04-29 18:33:05 | 2026-05-02 18:20:49 |
| **TOTAL** | **2,482** | 100% | | |

**4-day window；schema V031 deploy 2026-04-29.**

### 2.2 cross-tab source × engine_mode

| source | engine_mode | rows | 備註 / Note |
|---|---|---:|---|
| `dream_engine` | `demo` | 688 | DreamEngine demo cycle hourly |
| `dream_engine` | `live_demo` | 429 | DreamEngine live_demo cycle hourly |
| `ml_shadow` | `demo` | 729 | shadow_advisor demo cycle hourly |
| `ml_shadow` | `live_demo` | 429 | shadow_advisor live_demo cycle hourly |
| `ml_shadow` | **`live`** | **27** | **`mlde_demo_applier._insert_live_candidate` LG-5 promotion candidate audit；applied=false** |
| `opportunity_tracker` | `demo` | 90 | opportunity_tracker demo cycle |
| `opportunity_tracker` | `live_demo` | 90 | opportunity_tracker live_demo cycle |

### 2.3 schema CHECK constraint

```sql
"mlde_shadow_recommendations_source_check" CHECK (
    source = ANY (ARRAY[
        'linucb'::text,
        'ml_shadow'::text,
        'dream_engine'::text,
        'opportunity_tracker'::text
    ])
)
```

**Schema 限定 4 個值，實際只 3 個 producer 寫入** — `linucb` 在 schema allow 但 0 production row（LinUCB 走自己的 `learning.linucb_*` table，非經 mlde_shadow_recommendations）

---

## 3. 每 source row metadata sample

⚠️ **Note：** 不取 `payload` JSONB 欄位（避免敏感數據 + 大 row）；只取 metadata column。

### 3.1 `ml_shadow` (latest)

| id | source | engine_mode | recommendation_type | symbol | strategy_name | applied | created_by |
|---|---|---|---|---|---|---|---|
| 2471 | ml_shadow | live_demo | veto | (NULL) | ma_crossover | f | mlde_shadow_advisor |

### 3.2 `dream_engine` (latest)

| id | source | engine_mode | recommendation_type | symbol | strategy_name | applied | created_by |
|---|---|---|---|---|---|---|---|
| 2477 | dream_engine | live_demo | parameter_proposal | (NULL) | ma_crossover | f | mlde_dream_engine |

### 3.3 `opportunity_tracker` (latest)

| id | source | engine_mode | recommendation_type | symbol | strategy_name | applied | created_by |
|---|---|---|---|---|---|---|---|
| 2210 | opportunity_tracker | live_demo | regret_summary | (NULL) | (NULL) | f | mlde_opportunity_tracker |

### 3.4 `ml_shadow` engine_mode='live' (5 latest of 27)

| id | source | engine_mode | recommendation_type | symbol | strategy_name | applied | requires_governance | decision_lease_id | created_by |
|---|---|---|---|---|---|---|---|---|---|
| 2161 | ml_shadow | live | experiment_plan | (NULL) | ma_crossover | f | t | (NULL) | mlde_demo_applier |
| 2124 | ml_shadow | live | experiment_plan | (NULL) | ma_crossover | f | t | (NULL) | mlde_demo_applier |
| 2052 | ml_shadow | live | experiment_plan | (NULL) | ma_crossover | f | t | (NULL) | mlde_demo_applier |
| 2016 | ml_shadow | live | experiment_plan | (NULL) | ma_crossover | f | t | (NULL) | mlde_demo_applier |
| 1665 | ml_shadow | live | experiment_plan | (NULL) | ma_crossover | f | t | (NULL) | mlde_demo_applier |

**全 27 row：source='ml_shadow' / engine_mode='live' / recommendation_type='experiment_plan' / strategy_name='ma_crossover' / applied=false / created_by='mlde_demo_applier' / decision_lease_id=NULL**

LG-5 §2.1 audit row（per `mlde_demo_applier._insert_live_candidate` line 1223-1240），applied=false 是預期狀態（待 LG-5 reviewer activate after FUP-1 commit `463890d` deploy）。

---

## 4. R20-P2a-S6 evidence_source_tier 分類表 / classification table

依 V3 §4.2 evidence_source_tier 接受值 `real_outcome` / `calibrated_replay` / `synthetic_replay` / `counterfactual_replay`：

### 4.1 Allowed for replay backfill (3 / 3 → all)

每個 source 必歸入 `real_outcome` tier（V3 §4.2 initial producer allowlist 已 explicit list）：

| source | row_count | 分類 / Classification | evidence_source_tier | 理由 / Reason |
|---|---:|---|---|---|
| `dream_engine` | 1,117 | **allowed_for_replay → real_outcome** | `real_outcome` | V3 §4.2 explicit allowlist；DreamEngine consume `learning.exit_features` real fills；source=cron observation |
| `ml_shadow` | 1,185 | **allowed_for_replay → real_outcome** | `real_outcome` | V3 §4.2 explicit allowlist；shadow_advisor 從 demo/live_demo trading.fills 統計，source=real outcome |
| `opportunity_tracker` | 180 | **allowed_for_replay → real_outcome** | `real_outcome` | V3 §4.2 explicit allowlist；regret summary 來自真實 rejected entry signal 觀察 |
| **TOTAL** | **2,482** | | | |

**注意：** V3 §4.2 列 allowlist 為 `[dream_engine, ml_shadow, opportunity_tracker]`（3/3 都已列入）。`linucb` schema CHECK allow 但 0 row 寫入，未列入 V3 §4.2 allowlist；**R20-P2a-S6 retrofit 時 `evidence_source_tier='real_outcome'` 預設值 + producer-side filter 即可**。

### 4.2 Forbidden for replay (0)

無 source 命中以下「real money path」識別：
- 無 source 名 `live_*` / `mainnet_*` / `production_*`
- 無 source 屬於 ExecutorAgent 真 live 下單路徑
- 27 row engine_mode='live' 是 audit row（applied=false），不是 live mutation；source='ml_shadow' 屬 §4.1 allowed

### 4.3 Ambiguous for PM (0)

無 source 命中以下 ambiguous pattern：
- 無 `test_*` 命名
- 無 `backfill_*` 命名
- 無 unknown / mismatch schema CHECK 值
- 無 NULL（schema NOT NULL）

**Schema CHECK 限定 set 是天然 guard**；ambiguous classification 不需 PM intervene。

---

## 5. 27-row engine_mode='live' 解讀 / 27-row analysis

| 字段 / Field | 觀察 / Observation |
|---|---|
| 全 27 row source | `ml_shadow`（無例外）|
| 全 27 row strategy_name | `ma_crossover`（無例外）|
| 全 27 row recommendation_type | `experiment_plan`（無例外）|
| 全 27 row applied | `false`（無例外）|
| 全 27 row decision_lease_id | NULL（無例外）|
| 全 27 row created_by | `mlde_demo_applier`（無例外）|
| 全 27 row requires_governance | `true`（無例外）|

**Producer 路徑 / Producer path：** `mlde_demo_applier._insert_live_candidate` (line 1223)，由 `_apply_one()` 在 demo apply 完成 + `should_create_live_candidate(row, cfg)` true 時觸發。

**Healthcheck 守衛 / Healthcheck guard：** `helper_scripts/db/passive_wait_healthcheck/checks_execution.py:189` `check_mlde_shadow_recommendations()` 已守 `live/live_demo + applied + decision_lease_id IS NULL → FAIL`；目前 0 hit（applied=false 全部）。

**結論 / Conclusion：** 27 rows are LG-5 audit trail，非 live trading mutation；R20-P2a-S6 retrofit 後仍標記 `evidence_source_tier='real_outcome'`（real-outcome producer 寫的 audit row）。

---

## 6. 紅線 / Red lines

- 0 寫入 / 0 source modification（本 task 純 read-only）
- ssh trade-core 跑 `psql` 限定 SELECT + `\d` schema introspection；無 GRANT/REVOKE/ALTER
- 不取 `payload` JSONB（敏感數據避讓）
- 結果 row count ≤ 7（GROUP BY 統計 + 5 metadata sample，符合「≤100 row」紅線）
- 不直接 PM 分類 ambiguous（本 task 0 ambiguous，無需 PM intervention）

---

## 7. 雙語注釋 / Bilingual comment compliance（CLAUDE.md §七）

本 report 全文中英對照（標題雙語 / 表頭雙語 / 段落必要時雙語），符合：
- `MODULE_NOTE` 中英對照（§0 TL;DR）
- 表頭中英對照（§2 source 分布表）
- SQL probe 命令的目的描述雙語（§1）
- 分類規則 / 理由 / 結論等業務描述雙語（§4-5）

---

## 8. PM 必看 / unknowns

1. **27 row engine_mode='live' R20-P2a-S6 retrofit 時 evidence_source_tier 確認**：應屬 `real_outcome`（promotion-candidate audit row），但 V3 §4.2 spec 在 `replay_experiment_id IS NULL` and `manifest_hash IS NULL` 時要求 evidence_source_tier='real_outcome'，這 27 row 滿足條件（NULL replay_experiment_id 因為新 column 還沒加） — PM 確認 retrofit migration 時這 27 row 也走 real_outcome backfill
2. **`linucb` schema CHECK allow 但 0 row**：建議 V3 §4.2 producer allowlist 不擴增（保持 3 個 producer）；R20-P2a-S6 verified-insert function 不必 accept `source='linucb'` 參數，避免 dead code path
3. **`evidence_tier_backfill_report` table 預期 row 數（per V3 §4.2 spec）**：本掃描結果 0 ambiguous → backfill report 預期 0 row 進 `classification='ambiguous'` bucket，但會有 3 row 進 `classification='real_outcome'`（dream_engine + ml_shadow + opportunity_tracker 各一條 backfill summary）— PM 確認此預期
4. **本掃描覆蓋 4-day window**（2026-04-29 → 2026-05-03，schema V031 deploy 後）：PM 排程 R20-P2a-S6 切換時建議 ≤ 14 day（避免 source 隨產品演進新 distinct 值出現未被本掃描覆蓋）；如 14d 內有新 PR 改 producer 必補 SELECT DISTINCT re-probe
5. **Producer 切換後 row count 期望**：4 producer 觸發頻率不變（每小時 cycle）；R20-P2a-S6 PR-B 部署後 7 day 預期 row count growth ≈ 4 producer × 24h × 7d × 平均 hits/cycle，PM 排程 healthcheck 可建立 baseline ratio

---

## 9. PM 主會話 final classify 結論 / final classification recommendation

**✅ ALL 3 SOURCE → allowed_for_replay → evidence_source_tier='real_outcome'**

**0 ambiguous，0 forbidden，無需 PM 個別 classify**

R20-P2a-S6 retrofit migration 可直接套 V3 §4.2 spec 預設值 `evidence_source_tier='real_outcome'`，無需 ambiguous resolution 環節。

---

## 10. ssh bridge 連通性確認 / SSH bridge healthcheck

| 項 | 結果 |
|---|---|
| `ssh trade-core "echo SSH_OK"` | ✅ SSH_OK |
| `psql -h 127.0.0.1 -U trading_admin -d trading_ai` | ✅ via `.pgpass` |
| schema introspection `\d learning.mlde_shadow_recommendations` | ✅ |
| SELECT DISTINCT + GROUP BY query | ✅ |
| Read-only enforcement | ✅（無 INSERT/UPDATE/DELETE 觸發） |

---

## 11. 修訂歷史

| 版次 | 日期 | 修訂者 | 摘要 |
|---|---|---|---|
| v1 | 2026-05-03 | E1 (sub-agent, R20-P0-T7) | Initial SELECT DISTINCT classification; 3 source / 0 ambiguous / 0 forbidden; 27 live engine_mode → audit row 認定；無需 PM ambiguous resolve |
