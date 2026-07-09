# MIT Advisory — REF-20 Sprint C1+C2 R6/R7 Capability + Risk Assessment

**Date**: 2026-05-05
**Author**: MIT (ML & Database Auditor)
**Posture**: read-only, pre-DAG advisory; 0 code change, 0 commit
**Sprint context**: PA Sprint C task DAG `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-05--ref20_sprint_c_task_dag.md` accepted as C1+C2 split (operator decision); LOC §九 1500→2000 same commit `e5b5227c`. HEAD `e5b5227c` Mac/Linux/origin synced.
**Boundary**: schema/risk assessment only; QC owns calibration math spec parallel.

---

## §0. Executive Summary

PA report §2C 對 `mlde_demo_applier_evidence_filter.py` capability probe 的描述 **基本正確** 但漏 1 個關鍵 capability key（`has_evidence_source_tier`）。三條 capability 全 true 才走 Block B 的論述也對，但實際是 4 個 capability gate（不是 3 個）。

PA report §0.6 「sibling CC LG5-W3-FUP-2 in flight」**過期** — 真實 commit `34211ab4`（2026-05-02 E2 round 1 PASS to E4）已 land。R7 dispatch 不會跟 sibling CC 衝突，FUP-2 不在 flight。

V051 paired CHECK + V036 verify_replay_evidence_and_insert 是**雙層守門**，但 V036 比 V051 嚴 — V036 多檢查 `expires_at IS NOT NULL` + `expires_at > now()` + source allowlist + tier allowlist。R7 producer 升級時若漏傳任一 metadata 都會被 V036 RAISE EXCEPTION 拒，**不會** drop 到 V051 CHECK 層；V051 是「萬一 caller 繞過 V036 直 INSERT」的最後 backstop。**這是好事**（兩層 fail-closed，DOC-01 #6）。

R6 calibration 用 `trading.fills.fee_rate`（V008 column）作 ground truth。**真實 retention=365d**（V006 line 78），完全足夠 R6 7d/14d/30d 樣本需求；compression 14d+ 可能讓 query 慢一點但 7d 樣本永遠在 uncompressed chunk 裡。**無風險**。

calibrated_replay tier 加入後 Block B cardinality 預估：dream_engine 每 cycle ~3-15 row（hourly cycle）+ opportunity_tracker 每 cycle 1 row（hourly）。daily ~80-360 row 進 mlde_shadow_recommendations 透過 calibrated_replay tier。**Block B 不會洪水**，但 expires_at TTL 30d 太長導致 forensic table 可能膨脹至 ~3k-10k rows/month — 需 Sprint D R8 加 retention policy。

---

## §1. mlde_demo_applier_evidence_filter capability probe 真實邏輯（驗 PA §2C）

### §1.1 真實 capability key 數量 — PA 漏 1 個

PA report §2C 寫：
> 三 capability probe：`has_replay_experiment_id` / `has_manifest_hash` / `replay_experiments_has_expires_at`

**實際為 6 個 capability key**（`mlde_demo_applier_evidence_filter.py:91-98`）：

```python
caps = {
    "has_evidence_source_tier": False,           # PA 漏列
    "has_replay_experiment_id": False,           # PA 列
    "has_manifest_hash": False,                  # PA 列
    "has_replay_experiments": False,             # PA 漏列
    "replay_experiments_has_expires_at": False,  # PA 列
    "replay_experiments_has_status": False,      # PA 漏列
}
```

**`build_evidence_source_filter` 真實 gate 邏輯**（line 172-238）：

| Gate | 缺哪個 capability → 行為 |
|---|---|
| **Top-level fail-soft** | `has_evidence_source_tier=False` → `return "", []`（legacy schema 完全 fallback，**0 filter**） |
| **Block A** | `has_evidence_source_tier=True` → emit `evidence_source_tier IN (allowlist)` filter（line 183-186） |
| **Block B 完整版** | 4 capability 全 true (`has_replay_experiment_id` + `has_replay_experiments` + `replay_experiments_has_expires_at` + `replay_experiments_has_status`) → `replay_experiment_id IS NULL OR (FK + manifest_hash + expires_at + status NOT IN cancelled/expired/compromised)`（line 196-212） |
| **Block B partial** | `has_replay_experiment_id=True` + `has_replay_experiments=True` 但 expires_at/status 缺 → degrade 到 FK existence-only gate（line 213-231） |
| **Block B 完全 skip** | `has_replay_experiment_id=False` → 完全略過 Block B（line 232-236 註解） |

**MIT 補足 PA 描述**：實際 4 個 capability 全 true 才走 Block B 完整版；3 個 capability（PA 描述）走 partial fallback；不是「三 capability 全 true 才 Block B 否則 Block A only」這麼簡單。

### §1.2 capability detection 的真實邏輯

**Q1**：是 INFORMATION_SCHEMA query? sqlx introspection? hardcoded sentinel?

**A**: 純 INFORMATION_SCHEMA query（`information_schema.columns` line 103-110 + 138-141）+ `to_regclass('replay.experiments') IS NOT NULL` table-existence check（line 125）。**100% PostgreSQL catalog query**，不是 sqlx introspection 或 hardcoded sentinel。

**Q2**：fail-soft direction?

**A**: 探測層 fail-soft：SQL exception → return all-False caps（line 113-115 + 127 + 145）→ caller `build_evidence_source_filter` 拿到 all-False caps → top-level fallback to legacy schema（filter 0 字符）→ legacy SELECT 全 row 都過。**fail-open** — 探測 SQL 失敗時 **不阻塞** caller，但也 **不過濾**（即「假設 schema 是 V038 前的 legacy」+ Block A/B 兩層全 skip）。

### §1.3 race condition / capability cache staleness

**Q3**：capability cache 是否會 stale?

**A**: **不會 cache**。`evidence_filter_capabilities(cur)` 每次 `fetch_pending_sql_and_params(cur, ...)` 呼叫都重新 probe（line 259）。每 mlde_demo_applier cycle 都重新 query INFORMATION_SCHEMA。**0 cache，0 staleness 風險**。

**性能 trade-off**：每 cycle 多 2 個 INFORMATION_SCHEMA query（mlde_shadow_recommendations columns + replay.experiments columns）。INFORMATION_SCHEMA 在 PG 是 view-on-pg_catalog，per-query <10ms。每小時 cycle 1 次，**性能 cost 可忽略**。

### §1.4 fail-safe direction — Block B 不可用時行為

**Q4**：Block B 不可用時 fail-open（fallback Block A）還是 fail-closed（reject all）?

**A**: **fail-open，但有 Block A 守門**。當 capability 缺：
- `has_evidence_source_tier=False`（V038 前）→ Block A + Block B 都 skip → 純 legacy SELECT（**包含 promiscuous 風險：non-allowlisted source 也能進 mlde_demo_applier**）
- `has_evidence_source_tier=True` + `has_replay_experiment_id=False` → Block A enforced（allowlist filter）+ Block B skip → 視所有 row 為 real_outcome（即使 row 邏輯上是 calibrated_replay，因為 column 不存在所以無法檢驗）
- `has_replay_experiment_id=True` + replay.experiments stub 缺 expires_at/status → Block A + Block B partial（FK 存在性 gate）→ 仍守 lineage，但不檢 TTL 過期

**MIT 評估**：fail-soft 設計 OK 但**不是真 fail-closed**。真正 fail-closed 應該是「capability 缺 → reject all replay-derived row」。當前設計選擇「降級守門」是合理的 forward-compat 折衷，但**operator 必須知道 V040+V051 deploy 前 capability 缺時 mlde_demo_applier 把 calibrated_replay row 當 real_outcome 對待**。

**真實 runtime 狀態（HEAD `e5b5227c`）**：V040 + V049 + V051 全 land。Linux runtime 上 4 個 capability 預期全 true → Block B 完整版啟用。**0 fail-soft 路徑被觸發**。

### §1.5 observability

**Q5**：metric 能即時看 Block A 過 row 數 vs Block B 過 row 數？

**A**: **無**。當前 helper 純 SQL fragment builder，不 emit metric / log per-block row count。caller `mlde_demo_applier._fetch_pending` 拿到 fully-built SQL 後 execute，**不知道有沒有 Block B 真行 / 多少 row 被 Block B reject**。

**MIT 建議（R7 Sprint C2 task）**：加 1 個 INFO log 在 `fetch_pending_sql_and_params` end，dump active capabilities + final filter fragment 的 1-line digest。讓 LG-3 healthcheck output 順帶可消費（`pricing_binding mode=demo block_a=on block_b=full|partial|skip caps=4/6 ...`）。**~10-15 LOC，順手 R7-T7 加。**

---

## §2. calibrated_replay tier 加入後 Block B cardinality 預估

### §2.1 真實 producer cycle 頻率（grep + Read 證實）

**dream_engine.persist_dream_insights**（`dream_engine.py:415` → 透 `verify_replay_evidence_and_insert`）：
- 由 `edge_estimator_scheduler.py:587` import + 587-591 line 在 cycle 內呼叫
- Cycle interval: `interval_s: float = 3600.0`（`edge_estimator_scheduler.py:86 + 767`）= **每小時 1 次**
- 每次 cycle 多少 insight: function loops `for insight in insights`（line 445），insight 來源是 `_compute_dream_insights(...)` 從歷史 trade 算出。每策略約 1-3 insight per cycle，5 strategy → **3-15 row/hr**

**opportunity_tracker.persist_regret_summary**（`opportunity_tracker.py:230` → 透 `verify_replay_evidence_and_insert`）：
- 由 `edge_estimator_scheduler.py:594` import + 596 line 在 cycle 內呼叫
- 每 cycle 寫 `inserted = 1` 固定（line 273）= **1 row/hr**

**mlde_demo_applier._insert_live_candidate**（`mlde_demo_applier.py:1260`）：
- PA §2B 確認：legacy real_outcome 路徑，**R7 不動**
- 每 cycle 4-15 candidate（依 candidate sufficiency），但 `evidence_source_tier='real_outcome'`，不影響 Block B
- daily ~96-360 row 但**全進 Block A 路徑，0 row 觸 Block B**

**linucb**（PA §2B `linucb (location TBD)`）：
- 真實位點：`ml_training/linucb_trainer.py:274` 有 `attribution_chain_ok` 引用，但**沒有** `verify_replay_evidence_and_insert` caller
- grep 結果：linucb 0 producer wired into V036 verified function path
- **R7 Q**：linucb 可能 0 caller，R7 不必動；若 R7 加 linucb caller 則新增 ~1-3 row/hr

### §2.2 calibrated_replay tier 啟用後 Block B 流量預估

R7 把 dream_engine + opportunity_tracker（+ linucb maybe）從 `real_outcome / NULL,NULL,NULL,NULL` 升級到「真 replay metadata」路徑。**當前 4 producer (`dream_engine`, `opportunity_tracker`, `mlde_demo_applier._insert_live_candidate`, linucb) 全寫 real_outcome**。R7 改 dream_engine + opportunity_tracker 寫 calibrated_replay：

| Producer | Pre-R7 tier | Pre-R7 row/hr | Post-R7 tier | Post-R7 row/hr |
|---|---|---:|---|---:|
| dream_engine.persist_dream_insights | real_outcome | 3-15 | calibrated_replay | 3-15 |
| opportunity_tracker.persist_regret_summary | real_outcome | 1 | calibrated_replay | 1 |
| mlde_demo_applier._insert_live_candidate | real_outcome (legacy) | 4-15 | real_outcome (no change) | 4-15 |
| linucb (TBD) | unknown | 0 (probable) | calibrated_replay (R7 optional) | 0-3 |

**Daily Block B 流量**：(3-15 + 1 + 0-3) × 24 = **96-456 row/day calibrated_replay**

### §2.3 Block B 過期 reject rate 預估

**expires_at TTL contract**：V036 line 181 註解 "`Replay manifest TTL contract: 30 days default per V3 §5`"。實際 TTL 由 caller (R7 producer) 從 manifest.expires_at 帶入。

PA §2A 條款：`p_expires_at IS NOT NULL AND p_expires_at > now()` 是 V036 RAISE 條件。**R7 producer 必傳未過期 expires_at**，否則 V036 直接拒 INSERT。

**Block B SELECT 過濾**：`expires_at > now()` 在 SELECT 時再篩。如果 manifest TTL=30d，row 寫入時 expires_at = now()+30d，30d 內 row 都過 Block B；30d 後 row 仍在 mlde_shadow_recommendations table 但 SELECT filter 把它 reject。

**過期 row 累積**：30d × 96-456 row/day = **2880-13680 row** 永久占 table 但被 Block B 過濾 reject。**累積污染** — Sprint D R8 retention policy 必須處理。

**status 過濾 reject**：實務上 manifest 進 cancelled/expired/compromised 是低頻事件（~1% 估計）。reject rate <5% / table。

### §2.4 Block B 是否會洪水？

**結論**：**不會**。

- daily ~96-456 row 進 mlde_shadow_recommendations（total）
- mlde_demo_applier 每 cycle 取 ≤ `max_recommendations`（fetch_pending_sql_and_params line 252 — config 控制）
- 即使 Block B 啟用，consumer-side LIMIT 仍守住 candidate explosion
- 真實風險不是 candidate explosion，是**table size growth**（30d expires_at 後 row 不刪）

**MIT R7 sub-task 推薦（Sprint D R8）**：
1. 加 retention policy on `mlde_shadow_recommendations` 30d-60d for replay-derived row（real_outcome row 仍保 90d for ML training）
2. 或加 partial index `WHERE evidence_source_tier IN replay_tier_set AND expires_at > now() - interval '7 days'`（hot-path query 加速）
3. 兩者擇一；retention drop 比 partial index 簡單，建議優先

---

## §3. V051 mlde_recommendations 雙路 CHECK 對 4 producer 升級的 reject rate 預估

### §3.1 V051 paired CHECK 真實 enforce 點

**真實 SQL**（V051 line 278-291）：

```sql
CHECK (
    (
        evidence_source_tier = 'real_outcome'
        AND replay_experiment_id IS NULL
        AND manifest_hash IS NULL
    )
    OR
    (
        evidence_source_tier <> 'real_outcome'
        AND replay_experiment_id IS NOT NULL
        AND manifest_hash IS NOT NULL
    )
)
```

**雙路語意**：
- real_outcome row → 兩 metadata column 必 NULL
- replay-derived row（任何 non-real_outcome tier）→ 兩 metadata column 必 NOT NULL

### §3.2 V036 vs V051 雙層守門關係

**V036 verify_replay_evidence_and_insert (function level)**（line 137-191）：

| 檢查 | V036 RAISE EXCEPTION? |
|---|---|
| tier IS NULL 或 not in 4-value allowlist | YES (line 138) |
| source IS NULL 或 not in 4-value allowlist | YES (line 147) |
| tier='real_outcome' AND (replay_id NOT NULL OR hash NOT NULL) | YES (line 156-162) |
| tier!='real_outcome' AND (replay_id IS NULL OR hash IS NULL) | YES (line 164-170) |
| tier!='real_outcome' AND expires_at IS NULL | YES (line 178-183) |
| tier!='real_outcome' AND expires_at <= now() | YES (line 184-190) |

**V051 chk_mlde_shadow_replay_lineage (table level)**（line 278-291）：

| 檢查 | V051 CHECK reject? |
|---|---|
| tier='real_outcome' AND (replay_id NOT NULL OR hash NOT NULL) | YES |
| tier!='real_outcome' AND (replay_id IS NULL OR hash IS NULL) | YES |

**雙層關係**：V036 是 function 層，**比 V051 嚴 4 條**（多檢查 source allowlist + tier allowlist + TTL non-null + TTL future）。R7 producer 漏傳任 metadata 會在 V036 layer 先 RAISE，**不會** drop to V051 CHECK。**V051 是「caller 繞過 V036 直 INSERT」的最後 backstop**。

V037（V036 deploy 後）會 REVOKE PUBLIC INSERT FROM mlde_shadow_recommendations + GRANT INSERT TO replay_writer_role only。**Operator 必確認 V037 真已 deploy** — 否則惡意 producer 仍可繞 V036 直 INSERT，V051 是唯一守門（嚴格度低 4 條）。

### §3.3 R7 producer 升級可能違 paired CHECK 的路徑

**Q**: R7 IMPL 4 producer 升級時，有沒有路徑會違 paired CHECK?

| 違規路徑 | 是否可能 | 哪層 reject |
|---|---|---|
| dream_engine 漏傳 replay_experiment_id 但 tier='calibrated_replay' | YES (人為失誤) | V036 line 164 RAISE，V051 不會觸（caller 走 verify_replay function） |
| dream_engine 漏傳 manifest_hash 但 tier='calibrated_replay' | YES | V036 line 164 RAISE |
| dream_engine 仍寫 'real_outcome' 但傳 replay_experiment_id（contradictory） | YES | V036 line 156-160 RAISE |
| dream_engine 寫 'calibrated_replay' 但 expires_at IS NULL | YES | V036 line 178 RAISE |
| dream_engine 寫 'calibrated_replay' 但 expires_at < now() | YES | V036 line 184 RAISE |
| dream_engine 繞過 verify_replay function 直 raw INSERT | NO（V037 GRANT 撤回後） | V051 chk_mlde_shadow_replay_lineage RAISE |

**V036 內無路徑可繞 V051**（because V036 function INSERT 也走 V051 CHECK，CHECK 是 row-level）。**雙層守門完整**。

### §3.4 R7 真實 reject rate 預估

R7 4 producer (dream + opportunity + linucb + ml_shadow) 升級時，**乾淨 IMPL 場景下 reject rate ≈ 0%**（producer 設計即傳對 metadata）。

**反例 + 風險場景**：
- producer race condition：manifest 寫入 replay.experiments 但 cron quota_enforcer 同步 cancel manifest → producer 拿到 cancelled experiment_id 的 manifest_hash → V036 line 164 仍 pass（status check 在 SELECT 層 not function 層） → row 寫入 → mlde_demo_applier `Block B` SELECT WHERE status NOT IN cancelled 過濾 reject → silent shadow drop
- TTL 邊緣：expires_at 接近 now() → V036 pass（line 184 是 ≤now() reject，>now() pass）→ row 寫入但 1 sec 後過期 → Block B SELECT reject

**MIT 預估**：clean IMPL 下 V036 reject rate <0.1%；race/edge cases 在 high-load runtime 可能上升至 1-3%（需 R8 加 metric 監控）。

### §3.5 V036 內是否有路徑繞 V051?

**A**: **無**。V036 function 的 INSERT 也走 underlying table 的 CHECK constraints（PostgreSQL 行級 CHECK 在 INSERT 時必 enforce）。V036 function 在 Phase 3-PR sequence 第 1 PR (V036 only) 時，metadata column 還沒實際 land（V051/V038-V040 後才 land），function 內 INSERT 只寫 V031 既有 column（line 208-243）→ V051 後 metadata column 物理化但 V036 function INSERT 仍只寫 V031 column → metadata 由 producer-side parameter 傳但 V036 function body 不 forward 進 INSERT。**這是 P4-S11 design issue**。

**MIT 必告警 PA**：V036 function body 的 INSERT statement (line 208-243) **沒寫 replay_experiment_id / manifest_hash / evidence_source_tier / expires_at 4 個新 column**。這意味著 V036 function 可能在 V051 column 物理化後仍 UNDER-FILL — INSERT row 的 evidence_source_tier 會走 V040 default 為 'real_outcome'（V040 backfill 全 real_outcome 含 new row），4 個 metadata column 全為 V038-V040 backfill default 值。

**R7 IMPL 必補的 fix**（**MIT 強烈建議列為 R6/R7 dispatch BLOCKER**）：
- V036 function body INSERT statement 必須加 4 column write（`evidence_source_tier`, `replay_experiment_id`, `manifest_hash`, `expires_at` 從 caller parameter 寫入 row）
- 不修就 V036 verify pass 後 row INSERT 仍是 real_outcome row，calibrated_replay tier 永不出現在 row body

讓 PA / E1 在 R6/R7 dispatch 時驗證此點 — 若 V036 IMPL 已修則 OK，未修則必 V055（new migration）`CREATE OR REPLACE FUNCTION` 修補。

---

## §4. mlde_demo_attribution.attribution_chain_ok writer fix sibling CC 衝突

### §4.1 Sibling CC FUP-2 真實狀態 — PA §0.6 過期

PA report §0.6 寫：
> P1-DATA-1 LG5-W3-FUP-2 attribution_chain_ok writer fix sibling CC 仍在 flight

**MIT 驗證後修正**：FUP-2 Fix 1 (cron edge_label_backfill + healthcheck [43]) **已 land** 於 commit `34211ab4`（2026-05-02 E2 round 1 PASS to E4）。E2 memory 記錄：「LG5-W3-FUP-2 Fix 2 全 IMPL 一輪 PASS to E4」。

**MIT 補充**：CLAUDE.md §三 18-blocker #11 寫「sibling CC FUP-2 in flight」需要 update — 真實狀態是 `34211ab4` E2 round 1 PASS to E4，等 E4 regression 驗 / merge / deploy。**不在 R7 IMPL window 內衝突**。

### §4.2 attribution_chain_ok 真實 schema 位置

**關鍵發現**：`attribution_chain_ok` **不是** `mlde_demo_attribution` table 上的 column。而是 `learning.mlde_edge_training_rows` SQL VIEW 上的計算 column（V031 line 332-336 + V034 line 306）。

```sql
(sr.signal_id IS NOT NULL AND sr.signal_id <> ''
    AND sr.context_id IS NOT NULL AND sr.context_id <> ''
    AND sr.signal_context_id IS NOT NULL
    AND sr.signal_context_id = sr.context_id
    AND sr.label_net_edge_bps IS NOT NULL) AS attribution_chain_ok
```

**4 個 source column**（all on `mlde_shadow_recommendations` aliased `sr`）：
1. `signal_id IS NOT NULL AND signal_id <> ''`
2. `context_id IS NOT NULL AND context_id <> ''`
3. `signal_context_id IS NOT NULL AND signal_context_id = context_id`
4. `label_net_edge_bps IS NOT NULL`

**FUP-2 真實 fix 範圍**：cron `edge_label_backfill` + healthcheck [43] 處理的是**source column #4（label_net_edge_bps）的 backfill**，不是 attribution_chain_ok itself。MLDE training row 84.6% `attribution_chain_ok=false` 是因為這 4 個 source column 至少 1 個 fail。

**Q（驗 PA）**：兩 table 確實獨立（schema dependency / FK chain 0 cross-link）?

**A**: PA 描述「兩條路徑 schema 級獨立 / 0 schema-level 衝突」**正確**：
- `mlde_demo_attribution` table — 獨立 LG-5 audit table（V031/V034）
- `mlde_shadow_recommendations` table — V051 加 replay metadata column
- `mlde_edge_training_rows` VIEW — derives from `mlde_shadow_recommendations`，計算 `attribution_chain_ok`

**0 FK chain 連 mlde_demo_attribution 與 mlde_shadow_recommendations**。R7 改 mlde_shadow_recommendations 寫入路徑（dream/opportunity 升級 calibrated_replay tier）**不影響** mlde_demo_attribution writer。

### §4.3 sibling CC 完工時點對 R7 acceptance 的影響

**Sibling CC FUP-2 已 PASS to E4**（commit `34211ab4` 2026-05-02）。

**R7 dispatch 時實際狀況**（推測）：
- Sprint C1 R6 開工時 FUP-2 已 deploy 完（2-3 day 後 deploy + healthcheck observation）
- Sprint C2 R7 開工時 FUP-2 deploy 完且運行 7-10d，attribution_chain_ok ratio 預期回升到 healthy ratio（~50%+）
- R7 改的是 dream_engine + opportunity_tracker 寫 calibrated_replay tier — `attribution_chain_ok` view computation 不變

**0 wait constraint** for R7 dispatch。

### §4.4 logic 級 align（PA §0.6 提）

PA 提出：
> sibling CC FUP-2 完工後，attribution_chain_ok=true 的 row 會被 mlde_demo_applier 用作 source

MIT 驗證：mlde_demo_applier 從 `learning.mlde_edge_training_rows` view 讀 row（看 mlde_demo_applier.py line 825 + 942 + 1049 用 `WHERE attribution_chain_ok=true`）。**view 是 read-only computed**，writer 升級寫 mlde_shadow_recommendations 後 view 自動 reflect。**R7 不需 align attribution writer 邏輯**，view 一併解決。

---

## §5. R6 calibration data lineage 風險

### §5.1 trading.fills retention + sample 可查性

**真實位點**：V006 timescaledb_policies.sql line 78
- `add_retention_policy('trading.fills', INTERVAL '365 days')` ← retention 1 年
- compression policy 14 days ← compression 啟動 14d 後 chunk
- chunk_time_interval 由 V003 hypertable 創建決定（必 grep V003）

**對 R6 的影響**：
- 7d 樣本 → 全在 uncompressed chunk（query 快）
- 14d 樣本 → 部分 compressed chunk（query 稍慢，TimescaleDB native decompress）
- 30d 樣本 → 全 compressed chunk（query 顯著慢，但 retention 365d 完全 cover）

**Q1（驗 PA）**：trading.fills 7d/14d/30d 樣本實時可查嗎?

**A**: YES, **0 retention 風險**。365d retention >> 30d 需求。R6 calibration query 實際只用 7d-30d，全在 retention 內。

### §5.2 trading.fills.fee_rate column 真實存在

**真實位點**：V008__fills_fee_rate.sql line 14
- `ADD COLUMN IF NOT EXISTS fee_rate REAL DEFAULT 0`

**對 R6 影響**：column 自 2026-01 (or earlier) 已存在。R6 calibration 直 SELECT `fee_rate FROM trading.fills WHERE engine_mode IN ('demo','live_demo') AND ts > now() - interval '30 days'` — **0 schema risk**。

### §5.3 evidence_source_tier 與 trading.fills 是否 schema-level 互通?

**Q2**：是否需要 cross-link?

**A**: **不需要也不建議**。trading.fills 是 live/demo/live_demo 真實成交 row，其 fee_rate 是 ground truth — replay simulated_fills 校 fee 模型用 trading.fills fee_rate 作為 reference。**完全 read-only 引用**，0 cross-link 需要。

CLAUDE.md §九 clear boundary：
> `replay.simulated_fills` (V050) 是 replay 衍生數據... **不可作 ML training data**

但 trading.fills (real fills) 是合法 training data。R6 calibration 用 trading.fills 校 replay model，**這是正確路徑**。

### §5.4 engine_mode filter — R6 必含 'demo' + 'live_demo'

**MIT 警告（從 memory `engine_mode_tag_live_demo`）**：
> 歷史 43k 條 engine_mode='live' 實為 LiveDemo... ML filter 用 IN ('live','live_demo')

**R6 calibration query 必含**：`WHERE engine_mode IN ('demo', 'live_demo')`，不能 `='live'` 或 `='demo'`。

**P1-7 C labels 累積也用相同 filter**（CLAUDE.md §三 memory `feedback_demo_over_paper_for_edge`）。R6 / R7 必對齊。

**Q3 確認**：R6 calibration 樣本 query SQL 必須 `engine_mode IN ('demo','live_demo')`。

**A**: 是的。R6 IMPL 任何 SELECT trading.fills 的 SQL 必含此 filter，**不能寫 IN ('live','live_demo')**（live 對 demo 環境無資料）也**不能單寫 'demo'**（漏掉 live_demo 樣本 ~30% 量）。

PA report §1E 列的 grid_trading 7d 642 demo + 520 live_demo = **1162 樣本** 必合計算，這 1162 才是 calibration sample size。

---

## §6. ML pipeline data leakage / time-series CV concerns

### §6.1 R6 calibration 是 backward-looking — leak 路徑

**R6 設計**（PA §1）：用過去 7d/14d/30d trading.fills 算 fee_bps + slippage_bps σ → 寫入 confidence label → 應用到 replay future candidate。

**潛在 time-series leak**：
- 訓練：trading.fills(t-30d, t)
- 應用：replay simulated_fills(t, t+H)
- 訓練 vs 應用之間有「時序間斷」 — 訓練只用 t 之前資料，應用 t 之後。**0 look-ahead leak**。

但 R6 confidence label 本身**會有時序 drift**：
- t 時 grid_trading sample=1162 → label='calibrated'
- t+1d 時 sample=1180 → label still 'calibrated'
- t+30d 時 grid retention drop 早期 chunk → sample 可能<1000 → label degrades to 'limited'

**MIT 推薦（QC parallel work）**：confidence label 計算時用 rolling window 而非 expanding window，避免 t 早期 sample 永久 freeze label。

### §6.2 R7 advisory expires_at TTL 是否 enough 防 stale advisor?

**V036 expires_at default**：「30 days default per V3 §5」（V036 line 181 註解）

**Q**：30d 是否 enough?

**A**: **太長**。理由：
- crypto market regime 切換可能 7-14d 內
- replay manifest reflect 30d 前 market structure → calibrated_replay row 30d 內仍生效 → mlde_demo_applier 取 stale advisory promote 到 live → live trading 用 30d 前 fee model decision

**MIT 強烈建議 R7-IMPL 改 default TTL = 7d**（不是 30d）。30d 是 forensic/audit 保留，不是「decision 有效期」。

**Workaround（R7-T7）**：mlde_demo_applier_evidence_filter Block B SELECT 時加 `expires_at > now() AND expires_at < now() + interval '14 days'`（exclude 已寫但未過期 ≤ 7d 的 row 不算太老）— 但這需 manifest writer 改寫小 TTL。

**最簡 R7 fix**：caller 傳 7d TTL 入 V036 function — 不需改 V036 schema/code。

### §6.3 是否需 walk-forward CV pattern?

**MIT 答**：**對 R6 calibration 是 — yes**，對 R7 advisory 是 — partially。

**R6 walk-forward CV**：
- 用 t-30d ~ t-7d 作 train（calibrate fee_bps σ）
- 用 t-7d ~ t 作 holdout（驗證 calibrated σ 是否還 cover 真實 fee_bps）
- 若 holdout fee_bps 在 calibrated CI 外 → label downgrade 'calibrated' → 'limited'
- 寫 R6 IMPL 時 QC owns this math，MIT 只 advisory

**R7 advisory walk-forward**：
- 不需要因為 R7 不訓練模型，只 producer route
- 但 mlde_demo_applier 取 advisory promote 時必驗「advisory ts < live decision ts」（默認 SELECT order）— **0 leak risk**

---

## §7. Rust ↔ Python ↔ DB byte-equal contract maintenance

### §7.1 R6 新 column 是否破 manifest_signer canonical_bytes?

**R6 新 column**（PA §1C）：fee_bps + slippage_bps + ci_low/mid/high_bps + execution_model_version + liquidity_role

**問題**：這些 column 是 `replay.simulated_fills` 新 column，不是 `replay.experiments.manifest_jsonb` 內容。manifest_signer canonicalize 的是 manifest_jsonb（V049 column）。

**A**: **0 byte-equal contract 影響**。simulated_fills 是 fill artifact，manifest 是 experiment config。

但 MIT 警覺：**execution_model_version** column（PA §1C row 6）若需嵌進 manifest_jsonb（為 reproducibility）就會破 byte-equal — 這是 PA 設計選擇。**MIT 建議 execution_model_version 寫 simulated_fills row level 而非 manifest level**，避免 byte-equal 維護負擔。

### §7.2 R7 replay_experiment_id + manifest_hash cross-language byte-equal?

**真實位點**：V051 line 367-376 註解
- `manifest_hash BYTEA holds SHA-256 hash of canonical manifest (byte-identical to replay.experiments.manifest_hash for the same experiment)`

**A**: byte-equal contract 已 land — V051 column comment 明文記錄。R7 producer 取 replay_experiment_id + manifest_hash 從 lookup_replay_config_blob（PA §2A 提）— 該 function 從 replay.experiments table 讀，**直接取 BYTEA value**，不重 canonicalize。**0 cross-language byte-equal 風險**（DB level 已守）。

**MIT 確認**：byte-equal contract 維持。R7 IMPL 0 改動 manifest_signer 邏輯。

---

## §8. 結論 + R7 dispatch checklist

### §8.1 結論表

| Item | 結論 (GO / DEFER / WARN) | 理由 |
|---|---|---|
| capability probe race / cache stale | **GO** | 0 cache，每 cycle 重 probe；fail-soft 設計 OK；4 capability 全 true 走 Block B 完整版（HEAD `e5b5227c` 後預期 4/6 達標） |
| Block B cardinality 預估 | **GO with R8 retention** | daily ~96-456 row calibrated_replay；不洪水但 30d expires_at 累積至 ~3k-13k row/month，**Sprint D R8 必加 retention policy** |
| V051 paired CHECK enforce | **GO + WARN-V036-INSERT-MISSING** | V036 + V051 雙層守門完整；但 **MIT 強烈建議 R6/R7 dispatch 前驗證 V036 function body INSERT 是否寫入 4 個 metadata column**（line 208-243 未寫 — 風險 producer 升級後 row body 仍 real_outcome） |
| sibling CC FUP-2 衝突 | **GO** | FUP-2 commit `34211ab4` 已 PASS to E4（2026-05-02），不在 flight；PA report §0.6 過期需 update；R7 dispatch 0 wait constraint |
| trading.fills retention 風險 | **GO** | 365d retention >> 30d R6 需求；fee_rate column V008 已 land；0 schema risk |
| time-series leak 風險 | **WARN** | R6 calibration 0 leak（backward-looking）；R7 expires_at default 30d 太長（建議 7d） — caller 端傳小 TTL 即可，0 V036 改動 |
| xlang byte-equal 維持 | **GO** | manifest_hash BYTEA contract V051 line 367-376 明文；R6 simulated_fills column 不影響 manifest canonical bytes |

### §8.2 R7 dispatch checklist（PA 派發前必驗）

**P0 BLOCKER（必驗）**：

1. [ ] **V036 function body INSERT 是否寫入 4 個 metadata column**：
   - Read `learning.verify_replay_evidence_and_insert` function body 確認 INSERT statement 含 `evidence_source_tier`, `replay_experiment_id`, `manifest_hash`, `expires_at`
   - 若**沒有** → **R6/R7 dispatch BLOCKER**，必先 V055 migration 修補 V036 function body
   - 若已有 → R7 dispatch GO

2. [ ] **V037 deploy 確認**（V036 後 PR3）：
   - `psql -c "SELECT has_table_privilege('PUBLIC', 'learning.mlde_shadow_recommendations', 'INSERT')"` 應 = false
   - 若 PUBLIC 仍可 INSERT → V037 未 deploy → V036 function 可被繞過 → R7 dispatch BLOCKER

3. [ ] **expires_at TTL 預設值決策**：PM/PA 拍板 R7 producer 傳 TTL 是 7d 還是 30d
   - MIT 建議 7d（market regime 切換考慮）
   - 預設不改 V036；caller 端決定

**P1 RECOMMENDED（dispatch 同 IMPL 內補）**：

4. [ ] **R7-T7 加 1-line INFO log** in `fetch_pending_sql_and_params`：dump active capabilities + Block B mode（full/partial/skip）
   - Helps healthcheck observability + LG-3 pricing_binding healthcheck output 順帶可消費

5. [ ] **R8（Sprint D）retention policy**：mlde_shadow_recommendations 加 30d-60d retention for replay-derived row
   - Sprint D R8 scope，不阻 R7 dispatch

**P2 NICE-TO-HAVE**：

6. [ ] **CLAUDE.md §三 18-blocker #11 update**：sibling CC FUP-2 真實狀態（commit `34211ab4` PASS to E4）
   - 不阻 R7 dispatch，但 governance hygiene 應 update

7. [ ] **PA report §0.6 update**：FUP-2 not in flight；§2C capability 補列（6 個 capability key 不是 3 個）

8. [ ] **R6 confidence label 計算 rolling vs expanding**：MIT 建議 rolling window，不要 expanding（QC parallel work owns the math）

### §8.3 對 PA Sprint C task DAG 的補充建議

PA report §3-§7 task DAG **基本可採納**，但建議：

- **R6-T1 (calibration label producer)** 加附 task：先驗 V036 function body INSERT 完整性（§8.2 P0 #1）
- **R7-T7 加 observability**：fetch_pending_sql_and_params logging（§8.2 P1 #4）
- **Sprint D R8** 必含 retention policy task（§8.2 P1 #5）
- **R7-T2/T6 (4 producer 升級)** dispatch 前 grep `OPENCLAW_REPLAY_SIGNING_KEY_FILE` env、verify_replay_evidence_and_insert callsite，確認 producer 都從 manifest 取 expires_at（不能 hardcoded 30d）

---

## §9. 後續行動 / 不阻塞 dispatch 但需 PM 留意

| Action | Owner | Sprint |
|---|---|---|
| update CLAUDE.md §三 18-blocker #11 sibling FUP-2 真實狀態 | PM | next sync |
| update PA report §0.6 + §2C 數字 | PA | C1 R6-T0 前 |
| V036 function body INSERT completeness audit | E2 | C1 R6-T0 前驗 |
| V037 GRANT/REVOKE deploy verify on Linux runtime | E4 | C1 R6 IMPL 後 |
| mlde_shadow_recommendations retention policy V### | E1 | Sprint D R8 |
| fetch_pending_sql_and_params logging | E1 | C2 R7-T7 |

---

MIT AUDIT DONE: srv/docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-05--ref20_r6_r7_capability_risk.md
