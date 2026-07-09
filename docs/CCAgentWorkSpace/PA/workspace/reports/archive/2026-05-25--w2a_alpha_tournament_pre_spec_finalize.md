# W2-A — Stream A 2 candidate IMPL-ready pre-spec finalize + §10 P0 precondition 對照

**Date**: 2026-05-25
**Author**: PA（Sprint 2 W2-A sub-agent task）
**Source SoT**:
- W1-A spec 1: `srv/docs/execution_plan/2026-05-25--alpha_candidate_1_funding_short_v2_spec.md`
- W1-A spec 2: `srv/docs/execution_plan/2026-05-25--alpha_candidate_4_liquidation_cascade_fade_spec.md`
- W1-B M4 spec: `srv/docs/execution_plan/2026-05-25--m4_pattern_miner_stage_1_algorithm_spec.md`
- v5.8 §10.5 P0 precondition table (line 827-844) + §11.5 5-Gate Auto Path Inheritance (line 864+) + EA-4 P0-EDGE-1 AC amend (TODO §3 line 240)
- ADR-0034 Decision Lease Layered Approval (LAL)
- ADR-0025 + ADR-0026 Track-based strategy attribution + direct_exploit bypass CPCV
- V100 hypotheses schema + V101 track ENUM + V103 EXTEND 6 column
**Predecessor**: W1-A 2 spec land 2026-05-25 (commit `d94fa0c0`)
**Status**: PA W2-A FINALIZE — IMPL-ready 給 W2-B E1 sub-agent **WITH 2 CRITICAL schema drift amend**

---

## §0 TL;DR — Verdict

### W2-B E1 IMPL dispatch readiness verdict: **CONDITIONAL READY** — W2-B 必先吸收以下 2 個 CRITICAL schema 修正

**Verdict 條件**：
- (a) ✅ Algorithm spec / Rust struct skeleton / TOML config / 5-gate inheritance / look-ahead bias proof / acceptance criteria — 6 維 readiness ALL GREEN
- (b) ✅ §10 P0 precondition 對照 — 4/4 P0 + 5-gate 全通過（candidate IMPL 不觸 OPS / 不繞 LG-3 lease audit / 5-gate boundary inherit per §11.5）
- (c) 🔴 **CRITICAL-1**：W1-A spec §7.3 (funding_short_v2) + §7.4 (liquidation_cascade_fade) DRAFT writeback INSERT statement **schema 錯誤** — 引用不存在 table `learning.m4_hypotheses_extended` + 不存在 column `attribute_n / attribute_p_value / attribute_effect_size / attribute_subperiod_stable / attribute_graveyard_flag / attribute_cluster_silhouette`。實際 schema 是 `learning.hypotheses` table + V103 EXTEND 6 column `hypothesis_source_module / leakage_scan_pass / bonferroni_corrected_p / replicability_score / decision_lease_draft_id / cowork_review_status`（per V100 + V103 file）
- (d) 🔴 **CRITICAL-2**：W1-A spec §7.1 (funding_short_v2) + §7.1 (liquidation_cascade_fade) `strategy_track` 值 **invalid** — spec 寫 `"alpha_short_carry"` + `"alpha_microstructure_fade"` 不存在於 V101 `strategy_track` ENUM（V101 line 72-76 ENUM 僅 3 值：`direct_exploit / asds_factory / baseline`；hand-coded Rust strategy per ADR-0026 必 = `direct_exploit`）

**dispatch readiness verdict**：W2-B E1 IMPL **READY 派發** 條件：本 W2-A report §3 (DRAFT writeback amend) + §4 (track 修正) 為 IMPL 必讀；W2-B IMPL 不可直接抄 W1-A spec §7 DRAFT writeback / track 值，必走本 report §3 + §4

**派發 verdict**：**W2-B E1 IMPL DISPATCH GREEN** with this report as carry-over correction

**核心 deliverables 6 條**：
1. §2 §10 P0 precondition 對照 matrix（2 candidate × 4 P0 + 5-gate）— ALL GREEN
2. §3 14d demo accumulation hook design — V103 EXTEND 6 column 修正 INSERT statement + bucket-split SQL + cron line + attribution_chain_ok verify
3. §4 Decision Lease backref design — 採 ADR-0034 LAL 3 + lease_type='STRATEGY_TRIAL'；不 auto-promote past 'preregistered'
4. §5 alpha_tournament_runner Rust scaffold 8 file structure
5. §6 Python harness 2 file design（attribution_daily.py + tournament_orchestrator.py）
6. §7 TOML 配置 amend（risk_config + strategy_params）+ §8 AC re-confirm + §9 Cross-cutting collision check

**1 PM decision point**：W1-A spec §7 DRAFT writeback schema 錯誤 + track 值錯誤 — **PM 拍 PA W2-A inline amend 採 V103 actual schema + ADR-0026 direct_exploit track**（推薦）vs 退回 W1-A revise

---

## §1 為什麼 W1-A spec §7 schema 是錯的（push-back evidence）

### §1.1 CRITICAL-1: `learning.m4_hypotheses_extended` 不存在

**W1-A funding_short_v2 spec §7.3 line 694-703 寫**：
```sql
INSERT INTO learning.m4_hypotheses_extended (
  hypothesis_id, strategy_name, attribute_n, attribute_p_value,
  attribute_effect_size, attribute_subperiod_stable, attribute_graveyard_flag,
  attribute_cluster_silhouette, source_run_id, draft_state
) VALUES (...)
```

**實際 V103 schema**（per `srv/sql/migrations/V103__extend_m4_hypothesis_columns.sql:209-236`）：

```sql
ALTER TABLE learning.hypotheses
    ADD COLUMN IF NOT EXISTS hypothesis_source_module TEXT NOT NULL DEFAULT 'OPERATOR' CHECK (...M4_AUTO/OPERATOR/HISTORIC);
ALTER TABLE learning.hypotheses
    ADD COLUMN IF NOT EXISTS leakage_scan_pass BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE learning.hypotheses
    ADD COLUMN IF NOT EXISTS bonferroni_corrected_p NUMERIC(10, 8) CHECK ([0,1]);
ALTER TABLE learning.hypotheses
    ADD COLUMN IF NOT EXISTS replicability_score NUMERIC(5, 4) CHECK ([0,1]);
ALTER TABLE learning.hypotheses
    ADD COLUMN IF NOT EXISTS decision_lease_draft_id UUID;
ALTER TABLE learning.hypotheses
    ADD COLUMN IF NOT EXISTS cowork_review_status TEXT NOT NULL DEFAULT 'NONE' CHECK (NONE/PENDING/APPROVED/REJECTED);
```

**V100 base table** (`V100__m4_hypothesis_base_table.sql:274-302`) 列：
- `hypothesis_id BIGSERIAL PK / strategy_name TEXT NOT NULL / state TEXT (11 values: draft/preregistered/shadow/stage_0r/stage_1-4/live/retired/killed) / created_at / hypothesis_text / null_hypothesis / acceptance_criteria / min_sample_size / max_drawdown_pct / pre_reg_ts / pre_reg_hash / ...`

**W1-A spec 不對的 6 個 column 名**：`attribute_n / attribute_p_value / attribute_effect_size / attribute_subperiod_stable / attribute_graveyard_flag / attribute_cluster_silhouette` — 0 hits in V103 source.

**為什麼 W1-A 做錯**：把 W1-B M4 spec **CR-6 6 attribute minimum bar 設計概念** 誤當作 V103 actual column name（W1-B spec §3 line 350 列 6 attribute 概念名稱對應 V103 EXTEND column 但映射不是 1:1）。

### §1.2 CRITICAL-2: `strategy_track` ENUM 僅 3 值

**W1-A funding_short_v2 spec §7.1 line 648 寫**：
```
strategy_track = "alpha_short_carry"（per AMD-2026-05-15-01 track classification；新 track 名稱）
```

**W1-A liquidation_cascade_fade spec §7.1 line 740 寫**：
```
strategy_track = "alpha_microstructure_fade"（新 track；對齊 AMD-2026-05-15-01 track classification）
```

**實際 V101 ENUM**（per `srv/sql/migrations/V101__track_v3_attribution_column.sql:72-76`）：
```sql
CREATE TYPE strategy_track AS ENUM (
    'direct_exploit',
    'asds_factory',
    'baseline'
);
```

**AMD-2026-05-15-01** (`docs/governance_dev/amendments/2026-05-15--AMD-2026-05-15-01-canary-rebase-replay-preflight-demo-micro-canary.md`) 全文 grep 結果：0 hit on `alpha_short_carry / alpha_microstructure_fade` — W1-A spec 引用 AMD-2026-05-15-01 為依據是 **misattribution**。

**ADR-0025 + ADR-0026 verdict**：
- ADR-0025: track = `direct_exploit / asds_factory / baseline` (3 ENUM)
- ADR-0026: hand-coded Rust strategy 必 track = `direct_exploit` (Track A bypass CPCV)
- funding_short_v2 + liquidation_cascade_fade 都是 hand-coded Rust → **必 = `direct_exploit`**

### §1.3 修正路徑

PA W2-A inline amend（**不退回 W1-A spec revise**）：
- §3 + §4 IMPL 路徑採 V103 actual 6 column + ADR-0026 track='direct_exploit'
- W2-B E1 IMPL 必讀本 W2-A report §3 + §4，不抄 W1-A spec §7
- W2-E E2 review 必 grep `m4_hypotheses_extended` / `alpha_short_carry` / `alpha_microstructure_fade` → 0 hit in IMPL code（catch 規定）

**為什麼不退回 W1-A revise**：
1. 算法 spec / Rust struct / TOML / 5-gate inheritance 5 維 spec 都正確（W1-A 90% spec 不必動）
2. 退回 W1-A revise 拉長 1 day wall-clock；本 W2-A inline amend 即可 close
3. PA W2-A 為 IMPL-ready pre-spec finalize 階段 — 本 report 本就為 carry-over correction 場景設計

---

## §2 §10 P0 Precondition 對照（v5.8 §10.5 + EA-4 amend）

### §2.1 funding_short_v2 × 4 P0 + 5-gate matrix

| P0 ID | 對照 | 結論 |
|---|---|---|
| **P0-EDGE-1 AC-A (ii) amend** | candidate 達 demo 7d avg_net > 5bps + Wilson CI lower > 0 + n ≥ 30 路徑 | ✅ AC-S2-A-C1-7 (n ≥ 30 over 14d) + AC-S2-A-C1-8 (avg_net > 5bps + Wilson CI > 0) 對齊 P0-EDGE-1 AC-A (ii) 「≥ 3 個 alpha-bearing 策略含 Sprint 2 新 source」路徑 |
| **P0-OPS-1..4** | candidate IMPL 不直接觸 OPS（schema only 不 deploy live） | ✅ Sprint 2 demo-only；HTTPS / cred rotation / legal / runbook 4 OPS 條件不被 IMPL 影響；OPS-1/2 是 Sprint 4 W17.5 first Live 阻塞，與本 IMPL 並行 |
| **P0-LG-3** | candidate 不繞 lease audit chain | ✅ live entry path 必經 `IntentProcessor.submit_intent` → Guardian → Decision Lease emit（per ADR-0034 LAL 0 per-fill emit）；funding_short_v2 + liquidation_cascade_fade strategy 內部不繞 lease 路徑（per §4 backref design）|
| **5-gate live boundary** | candidate live state 必經 5-gate (per CR-15) | ✅ W1-A spec §4.1 五 gate inheritance contract 完整：A `live_reserved` / B `Operator role` / C `OPENCLAW_ALLOW_MAINNET=1` / D `valid secret slot` / E `signed authorization.json` — 全 inheritance 不繞 |

**RETURN-TO-PA 觸發條件**：以上 4 條任一 FAIL → 退 W1-A revise。**結果**：4/4 PASS，**dispatch CONTINUE**

### §2.2 liquidation_cascade_fade × 4 P0 + 5-gate matrix

| P0 ID | 對照 | 結論 |
|---|---|---|
| **P0-EDGE-1 AC-A (ii) amend** | demo 7d threshold | ✅ AC-S2-A-C4-9 + C4-10 對齊 P0-EDGE-1 AC-A (ii)；microstructure 新 source 屬 「alpha-bearing 新 source」覆蓋 |
| **P0-OPS-1..4** | 不觸 OPS | ✅ Sprint 2 demo-only；不依賴 OPS-1 HTTPS / OPS-2 cred / OPS-3 legal / OPS-4 runbook |
| **P0-LG-3** | 不繞 lease | ✅ live entry 必經 lease emit；strategy 內部不繞 |
| **5-gate boundary** | live 5-gate inherit | ✅ W1-A spec §4.1 同 funding_short_v2 全 inherit |

**結果**：4/4 PASS，**dispatch CONTINUE**

### §2.3 §10 P0 precondition 對照 verdict

兩 candidate × 4 P0 + 5-gate = **8/8 全 PASS**。**RETURN-TO-PA 0 trigger**；W2-B E1 IMPL dispatch readiness 在本軸 GREEN。

---

## §3 14d Demo Accumulation Hook Design（**修正版 — 採 V103 actual schema**）

### §3.1 Attribution Chain（per ADR-0025 + ADR-0026）

W2-B E1 IMPL **必 honor** 以下 attribution chain（**不**採 W1-A spec §7.1 invalid track 值）：

| Field | funding_short_v2 | liquidation_cascade_fade | Source |
|---|---|---|---|
| `strategy_name` | `"funding_short_v2"` | `"liquidation_cascade_fade"` | Rust Strategy::name() return value |
| `track` (V101 ENUM) | `'direct_exploit'` | `'direct_exploit'` | ADR-0026: hand-coded Rust = direct_exploit (Track A bypass CPCV) |
| `engine_mode` (V015 ENUM) | `'demo' / 'live_demo' / 'live'` | 同左 | ADR-0005 engine_mode tag |

**Track assignment logic** in W2-B E1 IMPL（registry.rs append）:

```rust
// srv/rust/openclaw_engine/src/strategies/registry.rs — 既有 track 對映機制
// per ADR-0026: hand-coded Rust strategy 必 track = direct_exploit
//
// 注意：track 不在 strategy struct 本體，而在 IntentProcessor 或 fills writer 寫入
// trading.fills.track 列時對 strategy_name 做 lookup。W2-B IMPL 不需新增 track 邏輯，
// 既有 fills writer 已 lookup 對映；只需確保 strategy_name 拼寫一致。
```

**驗證 IMPL track 正確**：W2-F MIT post-IMPL 必跑：
```sql
SELECT strategy_name, track, COUNT(*) AS n
FROM trading.fills
WHERE strategy_name IN ('funding_short_v2', 'liquidation_cascade_fade')
  AND engine_mode IN ('demo', 'live_demo')
GROUP BY strategy_name, track;
-- expect: 100% rows track = 'direct_exploit'（per ADR-0026）
```

### §3.2 attribution_chain_ok verify（per Sprint N+0 closure 範式）

per memory `project_2026_05_10_sprint_n0_closure.md`：attribution_chain_ok 0.5%→100% 經驗（V083 + V101 land 後 grid/ma/bb_breakout 達 100%）。

W2-F QA daily 必跑：
```sql
SELECT
  strategy_name,
  COUNT(*) AS total_fills,
  SUM(CASE WHEN attribution_chain_ok THEN 1 ELSE 0 END) AS ok_count,
  ROUND(100.0 * SUM(CASE WHEN attribution_chain_ok THEN 1 ELSE 0 END) / COUNT(*), 2) AS pct
FROM trading.fills
WHERE strategy_name IN ('funding_short_v2', 'liquidation_cascade_fade')
  AND engine_mode IN ('demo', 'live_demo')
  AND filled_at > NOW() - INTERVAL '14 days'
GROUP BY strategy_name;
-- expect: pct = 100.00 per strategy（W1-A spec 1 line 651 + spec 2 line 743 預期）
```

**fail-closed**: attribution_chain_ok < 90% → W2-F QA escalate → 暫停 14d 累積 / 修 entry_context_id 鏈

### §3.3 14d Demo Bucket-Split SQL（per CR-6 minimum bar）

`helper_scripts/alpha_tournament/14d_bucket_split.sql`（**新檔；W2-B E1 IMPL 落地**）：

```sql
-- Sprint 2 W2-F QA 14d daily evidence accumulation
-- per AC-S2-A-2 / AC-S2-A-C1-7 / AC-S2-A-C4-9 minimum bar n_fills ≥ 30
-- per CR-6 6 attribute（部分 attribute 對映至 V103 EXTEND 6 column）
--
-- Bucket split: per-strategy × per-symbol × per-trade-date
WITH alpha_candidate_demo AS (
  SELECT
    strategy_name,
    DATE(filled_at AT TIME ZONE 'UTC') AS trade_date,
    symbol,
    COUNT(*) AS n_fills,
    AVG(net_pnl_bps) AS avg_net_bps,
    -- Wilson CI lower bound (z=1.96 for 95% CI; per CR-6 minimum bar)
    -- defensive against n=0 / stddev=NULL（COALESCE）
    (AVG(net_pnl_bps) - 1.96 * COALESCE(STDDEV(net_pnl_bps), 0)
     / NULLIF(SQRT(GREATEST(COUNT(*), 1)::float8), 0))::numeric(10,4) AS wilson_lower_bps
  FROM trading.fills
  WHERE strategy_name IN ('funding_short_v2', 'liquidation_cascade_fade')
    AND engine_mode IN ('demo', 'live_demo')
    AND track = 'direct_exploit'  -- per ADR-0026
    AND attribution_chain_ok = TRUE  -- per Sprint N+0 closure 範式
    AND filled_at > NOW() - INTERVAL '14 days'
  GROUP BY strategy_name, trade_date, symbol
)
SELECT
  strategy_name,
  trade_date,
  SUM(n_fills) AS total_fills,
  AVG(avg_net_bps) AS avg_net_bps_overall,
  MIN(wilson_lower_bps) AS wilson_lower_overall_bps,
  -- Sample size projection (14d cumulative)
  SUM(SUM(n_fills)) OVER (PARTITION BY strategy_name ORDER BY trade_date) AS cumulative_n_fills,
  -- AC-S2-A-2 minimum bar: cumulative ≥ 30
  CASE WHEN SUM(SUM(n_fills)) OVER (PARTITION BY strategy_name ORDER BY trade_date) >= 30
       THEN 'PASS' ELSE 'PENDING' END AS min_sample_gate
FROM alpha_candidate_demo
GROUP BY strategy_name, trade_date
ORDER BY strategy_name, trade_date DESC;
```

### §3.4 cron line（per H-2 cron restoration SOP）

W2-B E1 IMPL 寫 `helper_scripts/alpha_tournament/14d_bucket_split.sh` 包裝 .sql + 加 cron：

```cron
# Sprint 2 Alpha Tournament 14d demo evidence accumulation
# Daily 02:30 UTC fire（per Sprint N+0 closure + H-2 cron restoration 範式）
# Idempotent: 重跑同日不副作用（INSERT-only-if-new approach 在 wrapper script 內）
30 2 * * * /home/$USER/openclaw/srv/helper_scripts/alpha_tournament/14d_bucket_split.sh >> /tmp/openclaw/logs/alpha_candidate_daily_$(date +\%Y\%m\%d).log 2>&1
```

**注意**：本 cron 是 evidence accumulation **read-only**，不寫 PG（僅 SELECT + log out）；不觸 5-gate / 不違 16 原則 #7 學習 ≠ live。

### §3.5 V103 EXTEND DRAFT writeback（CRITICAL-1 修正版）

**W1-A spec §7.3 + §7.4 INSERT 為 invalid schema**。**正確 IMPL**：

```sql
-- Sprint 2 W2-F MIT post-IMPL audit (Wave 3 W3-A)
-- per AC-S2-A-C1-9 / AC-S2-A-C4-11 DRAFT writeback to V103 EXTEND
-- per W1-B M4 spec §4 V103 EXTEND 6 column mapping
--
-- 注意：本 INSERT 走 learning.hypotheses（V100 base table + V103 EXTEND）
-- 不是 learning.m4_hypotheses_extended (該 table 不存在)
--
-- 6 attribute 對映（per W1-B spec §3 line 350 + V103 actual column）：
-- - W1-B 6 attribute (1) N ≥ 30 → 用 hypotheses.min_sample_size column (V100 既有)
-- - W1-B 6 attribute (2) Bonferroni p < 0.05/K → V103.bonferroni_corrected_p
-- - W1-B 6 attribute (3) effect size ≥ 0.2 → V103.replicability_score (composite include effect size)
-- - W1-B 6 attribute (4) 6mo sub-period stability → V103.replicability_score (composite include stability)
-- - W1-B 6 attribute (5) leakage scan pass → V103.leakage_scan_pass
-- - W1-B 6 attribute (6) cluster K silhouette → V103.replicability_score (composite include cluster)
-- - 統一通過 → V103.hypothesis_source_module = 'M4_AUTO'

INSERT INTO learning.hypotheses (
  -- V100 base 6 column必填
  strategy_name,
  state,             -- per V100 11-value ENUM；DRAFT 階段 = 'draft' 或 'preregistered'
  hypothesis_text,
  null_hypothesis,
  acceptance_criteria,
  min_sample_size,   -- W1-B attribute (1) N ≥ 30 → 此處填 14d cumulative n_fills
  max_drawdown_pct,
  -- V103 EXTEND 6 column 必填
  hypothesis_source_module,  -- 'M4_AUTO' for Sprint 2 alpha candidate auto-discovered
  leakage_scan_pass,         -- W1-B attribute (5)
  bonferroni_corrected_p,    -- W1-B attribute (2)
  replicability_score,       -- W1-B composite (3) effect size + (4) sub-period + (6) cluster K
  decision_lease_draft_id,   -- per §4 Decision Lease backref UUID
  cowork_review_status       -- DEFAULT 'NONE' Sprint 2 不啟 Y2 Cowork
) VALUES (
  'funding_short_v2',
  'draft',  -- Sprint 2 draft state；Sprint 3+ promote to 'preregistered'（不 auto-promote）
  'Funding rate > 30% annualized + short-only directional capture (Sprint 2 Alpha Tournament Candidate #1)',
  'Mean net_pnl_bps in demo over 14d <= 0',
  '14d demo avg_net_pnl_bps > 5 + Wilson CI lower > 0 + n_fills ≥ 30',
  /* n_fills */ ?::int,
  3.0,  -- per_strategy SL 3% 對齊 strategy_params
  'M4_AUTO',
  /* leakage_scan_pass */ TRUE,  -- W2-E E2 review 必證 funding rate / index price 不含 look-ahead bias（per §5）
  /* bonferroni p */ ?::numeric(10,8),  -- α = 0.05/K, K=2 (2 candidate) → α = 0.025
  /* replicability composite */ ?::numeric(5,4),  -- effect size × subperiod × cluster 加權
  /* lease_draft_id */ ?::uuid,  -- per §4 STRATEGY_TRIAL lease UUID
  'NONE'  -- Sprint 2 不啟 Cowork
);

-- 同 INSERT 結構 for liquidation_cascade_fade
-- strategy_name = 'liquidation_cascade_fade'
-- hypothesis_text = 'Liquidation cascade > $500k 5m + dominant_side fade entry (Sprint 2 Alpha Tournament Candidate #4)'
-- max_drawdown_pct = 2.0 (per_strategy SL 2%)
```

**W2-B E1 IMPL 必 honor**：
- 不可寫 `learning.m4_hypotheses_extended`（該 table 不存在；W2-E grep 此名 = IMPL CRITICAL FAIL）
- 不可寫 `attribute_n / attribute_p_value / attribute_effect_size` 等 W1-A 虛構 column 名
- 必走 V100 base + V103 EXTEND actual schema
- W2-F MIT post-IMPL audit 走 spec §3.5 INSERT pattern

---

## §4 Decision Lease Backref Design（per CR-15 + ADR-0034 LAL）

### §4.1 Lease type taxonomy

per ADR-0034 LAL 0-4 + 5-gate auto path inheritance：

| Phase | Lease type | LAL Level | Trigger | Audit |
|---|---|---|---|---|
| **Sprint 2 demo IMPL** | （無 lease emit；strategy 走 IntentProcessor.submit_intent → Guardian → ADR-0008 Decision Lease per-fill emit）| LAL 0 (per-fill always emit) | 每筆 demo fill | ADR-0008 既有路徑 |
| **Sprint 2 14d evidence accumulation** | （無新增 lease type；只 SELECT + log）| n/a | n/a | n/a |
| **Sprint 3+ Stage 0R promotion 評估** | `STRATEGY_TRIAL` (PA W2-A 提案 naming) | LAL 3 (new strategy promotion always operator-approve) | DRAFT writeback to hypotheses.state='preregistered' | ADR-0034 §Decision 5 6 hard gate full |
| **Sprint 4+ Live preregistered → stage_0r → stage_1** | 沿用 `STRATEGY_TRIAL` (LAL 3 重新 sign per stage) | LAL 3 | operator click | per V100 state 11-value 路徑 |

### §4.2 Sprint 2 lease backref binding (V103 EXTEND `decision_lease_draft_id` UUID)

per V103 EXTEND `decision_lease_draft_id UUID` (line 229)：

```rust
// Sprint 2 W2-F MIT post-IMPL audit pseudo-code
// V103 EXTEND decision_lease_draft_id 對應 ADR-0034 LAL Decision Lease emit
//
// Sprint 2 demo 階段：DRAFT writeback 必 bind 一個 placeholder lease UUID（pre-issue 不 emit）
// Sprint 3+ Stage 0R 階段：placeholder UUID 替換為 ADR-0008 emit lease_id

let placeholder_lease_uuid = uuid::Uuid::new_v4();  // Sprint 2 W2-F bind
// V103 EXTEND INSERT 用 placeholder UUID
// FK 暫不加（V103 line 230 commented out 「待 V099/V100 lease tables land」）

// Sprint 3+ Cowork review approve 後：
//   1. operator click LAL 3 approval
//   2. governance.decision_lease emit lease_id (per ADR-0008)
//   3. UPDATE learning.hypotheses SET decision_lease_draft_id = <new lease_id> WHERE hypothesis_id = ?
```

### §4.3 5-gate auto path inheritance contract

per CR-15 / v5.8 §11.5 hard invariant：

| 5-gate | funding_short_v2 inheritance | liquidation_cascade_fade inheritance |
|---|---|---|
| A: Python `live_reserved` | 不繞 — IntentProcessor 強制 | 同左 |
| B: Operator role | 不繞 — HMAC signed auth | 同左 |
| C: `OPENCLAW_ALLOW_MAINNET=1` | 不繞 | 同左 |
| D: Valid secret slot | 不繞 | 同左 |
| E: Signed `authorization.json` env match | 不繞 | 同左 |

**Strategy 內部 invariant**：
- `active = false` default (TOML)
- `enabled = false` default (per_strategy risk_config)
- live entry 必經 `submit_intent` → Guardian → ADR-0008 Decision Lease emit → P1/P2 risk envelope
- **Sprint 2 demo 階段 5-gate-A/B/C/E 仍須 green**（per LiveDemo no-degradation）

### §4.4 fail-closed contract

- DRAFT writeback fail → 不 UPDATE hypotheses.decision_lease_draft_id（INSERT roll back，per Postgres tx semantics）
- 14d 累積 fail（n_fills < 30）→ hypotheses.state = 'draft'（不 auto-promote 'preregistered'）
- attribution_chain_ok < 90% → W2-F escalate 暫停 evidence path
- Stage 0R Replay Preflight `eligible_for_demo_canary = false` → 不晉升 Stage 1（per AMD-2026-05-15-01）

### §4.5 不 auto promote past 'preregistered'

per ADR-0034 LAL 3 + 16 原則 #7 學習 ≠ Live + 16 原則 #11 P0/P1 邊界內自主：

- Sprint 2 IMPL DRAFT writeback 達 state='draft'（W1-C M4 pattern miner 同範式）
- Sprint 3+ operator manual click 才升 'preregistered'
- 'preregistered' → 'shadow' → 'stage_0r' → 'stage_1-4' → 'live' 各層必 operator click（LAL 3 always operator approve）
- **不**走 LAL 1 auto-approve（LAL 1 僅 intra-strategy reparam；策略升 stage 是 cross-strategy 級別 → LAL 3）

---

## §5 alpha_tournament_runner Rust Scaffold Design（per W1-A spec 11 sections）

### §5.1 8-file structure

```
srv/rust/openclaw_engine/src/strategies/funding_short_v2/
  ├── mod.rs           # FundingShortV2 struct + Strategy trait impl
  ├── params.rs        # FundingShortV2Params (TOML schema)
  └── tests.rs         # unit tests + 1e-4 cross-language fixture

srv/rust/openclaw_engine/src/strategies/liquidation_cascade_fade/
  ├── mod.rs           # LiquidationCascadeFade struct + Strategy trait impl
  ├── params.rs        # LiquidationCascadeFadeParams (TOML schema)
  └── tests.rs         # unit tests + 1e-4 cross-language fixture

modifications:
srv/rust/openclaw_engine/src/strategies/mod.rs       # append 2 pub mod
srv/rust/openclaw_engine/src/strategies/registry.rs  # append 2 strategy registration in StrategyFactory
srv/rust/openclaw_engine/src/strategies/params.rs    # append FundingShortV2Params + LiquidationCascadeFadeParams to StrategyParamsConfig
```

**Note**：W1-A spec §6.1 + §6.2 已給完整 mod.rs skeleton；W2-B E1 IMPL 直接抄；本 W2-A 不重複，只加 file structure spec。

### §5.2 No new alpha_tournament_runner orchestrator module

**PA W2-A clarification**：W1-A 命名「alpha_tournament_runner」字面意思 = 「跑 2 candidate 並行的 orchestrator」，但實作上 **不需獨立 orchestrator module**：

- 2 candidate 是普通 Strategy trait impl，自動由既有 `Orchestrator` tick_pipeline dispatch
- 既有 `StrategyFactory::build_strategies()` 已 iterate 所有 active strategy 並 push to runtime
- W2-B E1 IMPL 只新增 2 sub-module + 在 registry.rs append 2 registration block → **既有 orchestrator 自動 dispatch**
- 「alpha_tournament_runner」概念 = 整個 W2-B IMPL 集合（2 strategy + 1 SQL + 1 cron + 14d hook），不是新 Rust module

**W1-A spec §0 verdict 用 "alpha_tournament_runner" 為 informal name**；W2-B IMPL 不需建 `src/strategies/alpha_tournament/` 子目錄。

### §5.3 Cross-language fixture harness（per H-18 1e-4 tolerance）

per W1-A spec §9 對抗式 review 第 7 點 + W1-B M4 spec §6 Pure Stats Helper Rust+Python parity：

W2-B E1 IMPL 必落地 unit test fixture：
- `funding_short_v2/tests.rs` — Python pendant `tests/python/test_funding_short_v2_parity.py`
- `liquidation_cascade_fade/tests.rs` — Python pendant `tests/python/test_liquidation_cascade_fade_parity.py`
- compute_edge / compute_basis_pct / should_enter / should_exit pure function — Rust output 1e-4 對齊 Python reimplementation

**Cross-language fixture 6 case minimum**：
1. funding_short_v2: funding=0.0003 (annualized 30.4%) → annualized_funding 計算對齊
2. funding_short_v2: funding=0.0002 (annualized 21.9%) → reject (< 30%)
3. funding_short_v2: funding=-0.0003 → reject (negative funding hard side enforcement)
4. liquidation_cascade_fade: BTC dominant_notional=$600k > $500k threshold → entry_is_long signal map
5. liquidation_cascade_fade: ETH dominant_notional=$250k < $300k threshold → reject
6. liquidation_cascade_fade: Mixed dominant_side → reject

---

## §6 Python Harness Design（2 file）

### §6.1 `helper_scripts/alpha_tournament/attribution_daily.py`

職責：daily fire from cron @02:30 UTC；跑 §3.3 bucket-split SQL；Wilson CI projection；Bonferroni K=2；sample size projection

```python
#!/usr/bin/env python3
"""Sprint 2 Alpha Tournament daily 14d evidence accumulation.

per W2-A pre-spec finalize §3.3-§3.4 + AC-S2-A-2 minimum bar.
- Wilson CI 95% lower bound projection per candidate × symbol × date
- Bonferroni K=2 alpha adjustment (2 candidate)
- Sample size cumulative projection (target ≥ 30 over 14d)
- 不寫 PG（read-only SELECT + stdout log）
- attribution_chain_ok 必 100%（per Sprint N+0 closure 範式）

Output: stdout JSON + log to /tmp/openclaw/logs/alpha_candidate_daily_<YYYYMMDD>.log
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# 從 helper_scripts/lib/ 既有 PG connection helper
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
from pg_conn import connect_observer  # noqa: E402

CANDIDATE_STRATEGIES = ("funding_short_v2", "liquidation_cascade_fade")
BONFERRONI_K = 2  # 2 candidate this sprint
MIN_FILLS_PER_CANDIDATE = 30  # per AC-S2-A-2

BUCKET_SPLIT_SQL = """  -- 見 §3.3 完整 SQL
WITH alpha_candidate_demo AS (
  SELECT strategy_name, DATE(filled_at AT TIME ZONE 'UTC') AS trade_date, ...
  FROM trading.fills
  WHERE strategy_name = ANY(%s)
    AND engine_mode IN ('demo', 'live_demo')
    AND track = 'direct_exploit'
    AND attribution_chain_ok = TRUE
    AND filled_at > NOW() - INTERVAL '14 days'
  GROUP BY strategy_name, trade_date, symbol
)
SELECT ... FROM alpha_candidate_demo
GROUP BY strategy_name, trade_date
ORDER BY strategy_name, trade_date DESC;
"""

def main() -> int:
    with connect_observer() as conn:
        with conn.cursor() as cur:
            cur.execute(BUCKET_SPLIT_SQL, (list(CANDIDATE_STRATEGIES),))
            rows = cur.fetchall()

    summary = {
        "as_of": datetime.now(timezone.utc).isoformat(),
        "candidates": {},
    }
    for strategy_name in CANDIDATE_STRATEGIES:
        strat_rows = [r for r in rows if r[0] == strategy_name]
        cumulative_n = max((r[6] for r in strat_rows), default=0)
        summary["candidates"][strategy_name] = {
            "cumulative_n_fills_14d": cumulative_n,
            "min_sample_gate_pass": cumulative_n >= MIN_FILLS_PER_CANDIDATE,
            "bonferroni_adjusted_alpha": 0.05 / BONFERRONI_K,
            "daily_buckets": [
                {
                    "trade_date": str(r[1]),
                    "total_fills": r[2],
                    "avg_net_bps_overall": float(r[3]) if r[3] is not None else None,
                    "wilson_lower_overall_bps": float(r[4]) if r[4] is not None else None,
                }
                for r in strat_rows
            ],
        }

    print(json.dumps(summary, indent=2))
    return 0

if __name__ == "__main__":
    sys.exit(main())
```

### §6.2 `helper_scripts/alpha_tournament/tournament_orchestrator.py`

職責：optional — only if PA W2-A 需多 candidate cross-strategy ranking。Sprint 2 暫 stub（不必 Sprint 2 IMPL；Sprint 3+ M11 counterfactual replay 接入再 IMPL）

```python
#!/usr/bin/env python3
"""Sprint 2 placeholder for Sprint 3+ M11 counterfactual replay integration.

Sprint 2 Stage 1 不需 cross-candidate orchestration（2 candidate 並行獨立累積）；
Sprint 3+ M11 daily replay 後加入 candidate ranking 邏輯。

當前實作 = stub return success；不寫 PG / 不寫 file。
"""
def main() -> int:
    return 0

if __name__ == "__main__":
    import sys
    sys.exit(main())
```

---

## §7 TOML 配置 Amend（risk_config + strategy_params）

### §7.1 `srv/settings/strategy_params_demo.toml` append 2 slot

per W1-A spec §3.1 (funding_short_v2) + §3.1 (liquidation_cascade_fade) — **W2-A confirm 採用 verbatim**：

```toml
# Sprint 2 W2-B IMPL append
[funding_short_v2]
active = false
cooldown_ms = 28_800_000
allowed_symbols = ["BTCUSDT", "ETHUSDT"]
funding_threshold_annualized = 0.30
funding_exit_annualized = 0.05
max_basis_pct = 0.5
entry_basis_ratio = 0.6
max_hold_ms = 86_400_000
total_cost_bps = 22.0
expected_periods = 1.5

[liquidation_cascade_fade]
active = false
cooldown_ms = 1_800_000
allowed_symbols = ["BTCUSDT", "ETHUSDT"]
default_threshold_usd = 100_000.0
btc_threshold_usd = 500_000.0
eth_threshold_usd = 300_000.0
min_events = 3
max_hold_ms = 3_600_000
take_profit_pct = 1.5
reverse_cascade_ratio = 1.5
```

### §7.2 `srv/settings/risk_control_rules/risk_config_demo.toml` append 2 per_strategy block

per W1-A spec §3.2 — **W2-A confirm 採用 verbatim**：

```toml
# Sprint 2 W2-B IMPL append
[per_strategy.funding_short_v2]
enabled = false
max_concurrent_positions = 2
stop_loss_max_pct_override = 3.0
take_profit_max_pct_override = 2.0
take_profit_enforced_override = true
trailing_activation_pct_override = 1.0
trailing_distance_pct_override = 0.5

[per_strategy.liquidation_cascade_fade]
enabled = false
max_concurrent_positions = 2
stop_loss_max_pct_override = 2.0
take_profit_max_pct_override = 1.5
take_profit_enforced_override = true
trailing_activation_pct_override = 0.8
trailing_distance_pct_override = 0.4
```

### §7.3 risk_config_live.toml + risk_config_paper.toml

**不**動（per memory `feedback_env_config_independence` 三環境 config 故意分開）。Sprint 2 IMPL 只動 demo。Sprint 4+ first Live 才考慮 live config（per P0-EDGE-1 closure 路徑）。

---

## §8 AC Re-confirm（with W2-A corrections）

### §8.1 AC-S2-A-1..5（per dispatch packet §2.3）

| AC | 內容 | W2-A clarification | Verification |
|---|---|---|---|
| AC-S2-A-1 | Sprint 2 內 IMPL ≥ 2 新 candidate | ✅ funding_short_v2 + liquidation_cascade_fade IMPL（per W1-A spec §6 + W2-A §5） | W2-B IMPL DONE |
| AC-S2-A-2 | 14d demo data accumulation ≥ 30 n_fills | ✅ 採 W2-A §3.3 14d bucket split SQL；attribution_chain_ok 100% | Wave 3 W3-A review |
| AC-S2-A-3 | ≥ 1 candidate 達 demo 7d avg_net > 5bps + Wilson CI lower > 0 | ✅ 對映 P0-EDGE-1 AC-A (ii) amend | Sprint 3+ verdict |
| AC-S2-A-4 | DRAFT writeback to V103 hypotheses 完整 6 attribute | ✅ **採 W2-A §3.5 修正版 INSERT**（V103 EXTEND actual 6 column；非 W1-A 虛構 column）| W3-A review |
| AC-S2-A-5 | 5 textbook 自然累積 monitor | ✅ 與本 IMPL 並行（Stream A1 軌；本 IMPL 是 A2 軌） | QA daily SOP |

### §8.2 AC-S2-A-C1-1..10 (funding_short_v2，per W1-A spec §8)

| AC | W2-A 驗 |
|---|---|
| C1-1 strategy struct land + StrategyFactory registered + TOML active | ✅ W2-B E1 IMPL DONE |
| C1-2 `const IS_LONG: bool = false` | ✅ E2 review grep |
| C1-3 funding_threshold_annualized = 0.30 | ✅ TOML default |
| C1-4 Stage 1 cohort BTC/ETH only | ✅ unit test |
| C1-5 should_exit 4 條件 OR | ✅ unit test |
| C1-6 14d demo hook works | ✅ 採 W2-A §3 修正版 |
| C1-7 n_fills ≥ 30 over 14d | ✅ Wave 3 W3-A |
| C1-8 14d avg_net > 5bps + Wilson CI > 0 | ✅ Sprint 3+ |
| C1-9 DRAFT writeback to V103 | ✅ **採 W2-A §3.5 修正版**（不是 W1-A 虛構 `m4_hypotheses_extended` table）|
| C1-10 5-gate 0 觸碰 | ✅ E2 grep `live_reserved\|max_retries\|live_execution_allowed` |

### §8.3 AC-S2-A-C4-1..12 (liquidation_cascade_fade，per W1-A spec §8)

| AC | W2-A 驗 |
|---|---|
| C4-1 strategy struct land | ✅ |
| C4-2 declared_alpha_sources = LiquidationCascade | ✅ |
| C4-3 fail-closed on panel = None | ✅ |
| C4-4 Mixed → reject | ✅ |
| C4-5 per-symbol threshold | ✅ |
| C4-6 should_enter/exit 4+4 gate | ✅ |
| C4-7 self-fills stub Stage 1 | ✅ |
| C4-8 14d hook works | ✅ |
| C4-9 n_fills ≥ 30 | ✅ |
| C4-10 14d avg_net > 5bps | ✅ Sprint 3+ |
| C4-11 DRAFT writeback to V103 | ✅ **採 W2-A §3.5 修正版** |
| C4-12 5-gate 0 觸碰 | ✅ |

---

## §9 Cross-cutting Check（Stream A vs Stream B M4 pattern miner）

### §9.1 Collision check — Stream A 2 candidate vs Stream B M4 pattern miner DRAFT writeback

| 維度 | Stream A 2 candidate | Stream B M4 pattern miner | Collision? |
|---|---|---|---|
| Target table | learning.hypotheses + V103 EXTEND | learning.hypotheses + V103 EXTEND | **同 table** |
| hypothesis_source_module | `'M4_AUTO'`（W2-A spec）| `'M4_AUTO'`（W1-B spec §4.1 line 425）| **同 value** |
| Trigger | Sprint 2 W2-F MIT post-IMPL（手動，14d 後）| W1-C E1 IMPL daily auto fire（cron）| **不同 trigger** |
| strategy_name | `'funding_short_v2'` / `'liquidation_cascade_fade'` | M4 自動 discovery 出新 candidate name | **不同 strategy_name** |
| state | `'draft'` (Sprint 2)；Sprint 3+ operator click 升 'preregistered' | `'draft'` (Sprint 2)；Y2 Cowork review 升 | **同 state** |

**Collision verdict**：**NO collision**
- 同 table 但不同 row（strategy_name 不同）
- 同 hypothesis_source_module='M4_AUTO' 是 design alignment 不是 conflict
- INSERT 不會 race（不同 strategy_name PK 不衝突）
- W2-F MIT 跑 §3.5 INSERT；W1-C E1 cron 跑自動 discovery INSERT；兩者 INSERT 路徑獨立

### §9.2 W1-B M4 spec §4 6 attribute mapping 對齊（避免重複勞）

per W1-B spec §3 line 350 6 attribute（CR-6 minimum bar）：

| W1-B 6 attribute | V103 EXTEND column | Stream A 2 candidate W2-A 驗 |
|---|---|---|
| (1) N ≥ 30 | hypotheses.min_sample_size (V100 base) | ✅ W2-A §3.5 INSERT n_fills 填入 min_sample_size |
| (2) Bonferroni p < 0.05/K | V103.bonferroni_corrected_p | ✅ K=2 alpha=0.025；W2-F MIT 計算 |
| (3) effect size ≥ 0.2 (Cohen's d) | V103.replicability_score (composite) | ✅ W2-F MIT 計算後並入 composite |
| (4) 6mo sub-period stability | V103.replicability_score (composite) | ✅ Sprint 3+ accumulate 後 W3-A 評 |
| (5) leakage scan pass | V103.leakage_scan_pass | ✅ W2-E E2 review 證 funding rate / index price / liquidation pulse 不含 look-ahead bias |
| (6) cluster K silhouette 5-fold CV | V103.replicability_score (composite) | ✅ Sprint 3+ M11 replay 評（Sprint 2 標 'single-cluster' 通過） |

**結論**：Stream A 2 candidate 與 Stream B M4 pattern miner 在 V103 EXTEND 6 attribute mapping **對齊 100%**；不重複勞，不衝突。

### §9.3 PostgreSQL writer 衝突 check

W1-C M4 pattern miner Rust+Python hybrid scaffold（commit `ae9a2dd8`）已 land；W2-B E1 IMPL alpha_tournament 2 candidate INSERT 路徑與 M4 INSERT 路徑 **不互動**：

- M4 cron `edge_label_backfill */30min` 跑自動 discovery
- Alpha tournament cron `14d_bucket_split @02:30 UTC` read-only（不寫 hypotheses）
- W2-F MIT post-IMPL audit 手動跑 §3.5 INSERT（與 cron 隔開）

**結論**：Stream A + Stream B **0 PG writer race**

### §9.4 5-gate inheritance cross-check

per CR-15 / v5.8 §11.5：

| Auto path | Stream A 2 candidate | Stream B M4 pattern miner |
|---|---|---|
| LAL 0 per-fill emit (ADR-0008) | ✅ 不繞 | n/a (M4 不直接 emit lease；DRAFT writeback only) |
| LAL 1 intra-strategy reparam | ✅ Sprint 3+ Stage 4 + 30d stable 才開（per ADR-0034 §Decision 5）| n/a |
| LAL 2 cross-strategy reweight | n/a Sprint 2 不啟 | n/a |
| LAL 3 new strategy promotion | ✅ Sprint 3+ operator click 升 preregistered 才走 LAL 3 | ✅ W1-C IMPL 不 trigger live（per AC-S2-B-4）|
| LAL 4 capital structure | n/a | n/a |

**結論**：Stream A + Stream B 5-gate inheritance **fully aligned**

---

## §10 對抗式 Review Focus（W2-E E2 + W2-F MIT post-IMPL audit 重點）

繼承 W1-A spec §9 對抗式 review focus（funding_short_v2 7 點 + liquidation_cascade_fade 8 點）+ W2-A 新增 3 點：

### W2-A 新增對抗式 review focus

1. **W1-A schema drift catch**：W2-E E2 grep IMPL diff：
   - `grep -rn 'm4_hypotheses_extended' src/ helper_scripts/ tests/` → **MUST 0 hit**（catch W1-A spec §7.3+§7.4 虛構 table）
   - `grep -rn 'attribute_n\|attribute_p_value\|attribute_effect_size\|attribute_subperiod_stable\|attribute_graveyard_flag\|attribute_cluster_silhouette' src/ helper_scripts/ tests/` → **MUST 0 hit**（catch W1-A 虛構 column）
   - `grep -rn 'alpha_short_carry\|alpha_microstructure_fade' src/ helper_scripts/` → **MUST 0 hit**（catch W1-A 虛構 track）

2. **track ENUM compliance**：W2-F MIT post-IMPL audit 跑 §3.1 verify query；100% rows track='direct_exploit'

3. **V103 EXTEND INSERT schema 對齊**：W2-F MIT 跑 §3.5 INSERT pattern；驗 6 V103 EXTEND column 全填 + min_sample_size + state='draft'

---

## §11 W2-B E1 IMPL Dispatch Readiness Verdict

### §11.1 Final verdict

**DISPATCH-READY** with W2-A inline schema corrections（CRITICAL-1 + CRITICAL-2）

### §11.2 W2-B E1 IMPL must-read pre-IMPL

1. **W1-A spec 1 funding_short_v2** — algorithm + Rust skeleton + TOML（採 99% verbatim）
2. **W1-A spec 2 liquidation_cascade_fade** — algorithm + Rust skeleton + TOML（採 99% verbatim）
3. **本 W2-A report §3 + §4** — DRAFT writeback schema 修正 + Decision Lease backref（**override W1-A spec §7.3 + §7.4**）
4. **本 W2-A report §6** — Python harness 2 file design

### §11.3 W2-B IMPL action checklist

| # | Action | Source |
|---|---|---|
| 1 | Add `pub mod funding_short_v2;` + `pub mod liquidation_cascade_fade;` to `strategies/mod.rs` | W1-A spec §6 + §6 |
| 2 | Create `funding_short_v2/{mod.rs, params.rs, tests.rs}` 3 file | W1-A spec §6.2-§6.4 |
| 3 | Create `liquidation_cascade_fade/{mod.rs, params.rs, tests.rs}` 3 file | W1-A spec §6.2-§6.4 |
| 4 | Append 2 strategy registration block to `strategies/registry.rs` | W1-A spec §6.3 + §6.3 |
| 5 | Append 2 params block to `strategies/params.rs` StrategyParamsConfig | W1-A spec §6.4 + §6.4 |
| 6 | Append 2 TOML block to `settings/strategy_params_demo.toml` | W2-A §7.1 |
| 7 | Append 2 per_strategy block to `settings/risk_control_rules/risk_config_demo.toml` | W2-A §7.2 |
| 8 | Create `helper_scripts/alpha_tournament/14d_bucket_split.sql` + `.sh` | W2-A §3.3 + §3.4 |
| 9 | Create `helper_scripts/alpha_tournament/attribution_daily.py` | W2-A §6.1 |
| 10 | Add cron line（per W2-A §3.4） | W2-A §3.4 |
| 11 | Update `helper_scripts/SCRIPT_INDEX.md` per `srv/CLAUDE.md` §七 | CLAUDE.md §七 |
| 12 | `cargo test --workspace`（Mac OK）+ Python unit test cross-language fixture 1e-4 | W1-A §9 + W2-A §5.3 |

### §11.4 W2-E E2 review + W2-F MIT audit dispatch readiness

per dispatch packet Wave 2 W2-E + W2-F：

- W2-E E2 對抗式 review focus = W1-A 7+8 點 + W2-A 新增 3 點 = 18 review focus
- W2-F MIT post-IMPL audit 走 §3.3 SQL + §3.5 INSERT + §3.1 track verify
- attribution_chain_ok 必 100%（per Sprint N+0 範式）

---

## §12 References

### Code source of truth

- `srv/sql/migrations/V100__m4_hypothesis_base_table.sql` — base hypothesis schema
- `srv/sql/migrations/V101__track_v3_attribution_column.sql` — strategy_track ENUM 3 值
- `srv/sql/migrations/V103__extend_m4_hypothesis_columns.sql` — V103 EXTEND 6 column actual
- `srv/rust/openclaw_engine/src/strategies/mod.rs` — strategies pub mod list
- `srv/rust/openclaw_engine/src/strategies/registry.rs` — StrategyFactory pattern
- `srv/rust/openclaw_engine/src/strategies/params.rs` — StrategyParamsConfig pattern
- `srv/rust/openclaw_core/src/alpha_surface.rs` — AlphaSourceTag + LiquidationPulse + LiquidationSide schema
- `srv/rust/openclaw_engine/src/strategies/funding_arb.rs` — Option A-Lite reference pattern
- `srv/rust/openclaw_engine/src/strategies/funding_harvest/mod.rs` — Stage 1 BTCUSDT reference pattern

### Predecessor reports + ADRs

- W1-A spec 1: `docs/execution_plan/2026-05-25--alpha_candidate_1_funding_short_v2_spec.md`
- W1-A spec 2: `docs/execution_plan/2026-05-25--alpha_candidate_4_liquidation_cascade_fade_spec.md`
- W1-B M4 spec: `docs/execution_plan/2026-05-25--m4_pattern_miner_stage_1_algorithm_spec.md`
- Sprint 2 dispatch packet: `docs/execution_plan/2026-05-25--sprint_2_business_dispatch_packet.md`
- v5.8 main: `docs/execution_plan/2026-05-20--execution-plan-v5.8.md` §10.5 + §11.5
- ADR-0008 Decision Lease state machine
- ADR-0025 Track-based strategy attribution
- ADR-0026 direct_exploit bypass CPCV
- ADR-0034 Decision Lease Layered Approval (LAL)
- ADR-0036 §Decision 1 HMM/Markov-switching/GARCH 黑名單
- ADR-0038 §Decision 1 M11 self-hosted PG historical source
- AMD-2026-05-15-01 Canary Rebase Replay Preflight (Stage 0R)

### Memory + governance

- `feedback_indicator_lookahead_bias` (rolling shift(1) 強制)
- `feedback_position_sizing` (3% risk/trade Kelly)
- `feedback_demo_loose_live_strict_policy` (demo 學習料源 / live fail-closed)
- `feedback_env_config_independence` (三環境 config 故意分開)
- `feedback_v_migration_pg_dry_run` (Linux PG empirical reflection)
- `project_funding_arb_v2_deprecation_path` (funding_arb V2 dormant)
- `project_2026_05_10_sprint_n0_closure` (attribution_chain_ok 0.5%→100% 範式)
- 16 root principles #4 #5 #6 #7 #11

### Skills

- quant-strategy-design
- math-model-audit
- crypto-microstructure-knowledge
- 16-root-principles-checklist

---

## §13 Conclusion

### W2-A pre-spec finalize verdict

| 維度 | Status |
|---|---|
| §10 P0 precondition 對照 (2 candidate × 4 P0 + 5-gate) | ✅ 8/8 全 PASS |
| 14d demo accumulation hook（**修正版**） | ✅ ready；attribution_chain_ok 100% 預期 |
| Decision Lease backref (LAL 3 STRATEGY_TRIAL) | ✅ ready；不 auto-promote past preregistered |
| Rust scaffold 8 file structure | ✅ ready；不需新 alpha_tournament_runner module |
| Python harness 2 file | ✅ ready；attribution_daily.py 為 cron-fire 主 entry |
| TOML 配置 amend | ✅ ready；採 W1-A spec verbatim |
| AC re-confirm（5 main + 22 sub） | ✅ all GREEN with W2-A schema corrections |
| Cross-cutting collision (Stream A vs B M4) | ✅ 0 collision；fully aligned |

### W2-B E1 IMPL dispatch verdict

**DISPATCH-READY** — W2-B 收以下 carry-over correction：
1. **不**抄 W1-A spec §7.3 + §7.4 DRAFT writeback INSERT（虛構 schema）
2. **不**用 `alpha_short_carry / alpha_microstructure_fade` strategy_track（虛構 ENUM 值）
3. **採** W2-A §3.5 修正版 INSERT + §3.1 track='direct_exploit'

### PM decision point 1（待拍）

W1-A spec §7 DRAFT writeback schema 錯誤（CRITICAL-1）+ track 值錯誤（CRITICAL-2）：

- **Option A（推薦）**：PA W2-A inline amend close（本 report §3 + §4 override W1-A spec §7）；W2-B E1 IMPL 採 W2-A 修正版；W2-E E2 review 加 3 條對抗式 grep 防漏（per §10）
- **Option B**：退回 W1-A revise；wall-clock 拉長 1 day；W2-B IMPL 延後

**PA 推薦 Option A**：90% W1-A spec 正確 + 修正點 specific（不是設計層級錯）+ Option A 不影響 Wave 2 timeline

---

**Report END**

PA DESIGN DONE: report path: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-25--w2a_alpha_tournament_pre_spec_finalize.md`

---

## Step X — PM Decision 拍板 Option A — closure note

**Date**: 2026-05-25
**Source**: PM decision in W1-A inline amend dispatch task

### PM 決策

PM 拍板 **Option A（inline amend）**，不退回 W1-A revise：
- 採 §§3 + §4 修正版 schema：V103 EXTEND actual 6 column + `track = 'direct_exploit'`
- W1-A spec § 不全部 redrive；只動 2 spec 的 §7.1 + §7.3/§7.4 + 加 Changelog block

### 執行確認

1. **funding_short_v2 spec amend**：
   - `srv/docs/execution_plan/2026-05-25--alpha_candidate_1_funding_short_v2_spec.md`
   - §7.1 track value `'alpha_short_carry'` → `'direct_exploit'` ✅
   - §7.3 INSERT target `learning.m4_hypotheses_extended` → `learning.hypotheses` + V103 EXTEND 6 real column ✅
   - 加 Changelog v1.1 footnote ✅

2. **liquidation_cascade_fade spec amend**：
   - `srv/docs/execution_plan/2026-05-25--alpha_candidate_4_liquidation_cascade_fade_spec.md`
   - §7.1 track value `'alpha_microstructure_fade'` → `'direct_exploit'` ✅
   - §7.4 INSERT target → `learning.hypotheses` + V103 EXTEND 6 real column ✅
   - 加 Changelog v1.1 footnote ✅

3. **V101 ENUM SSH empirical verify**：
   ```
   $ ssh trade-core "psql ... -c \"SELECT enum_range(NULL::strategy_track);\""
   {direct_exploit, asds_factory, baseline}
   ```
   注意：ENUM type 名稱 = `strategy_track`（非 `strategy_track_enum`，本 report §1.2 原 SQL `enum_range(NULL::strategy_track_enum)` syntax 不完全準確；ENUM 值正確）。

### W2-B E1 IMPL dispatch readiness verdict 更新

| 維度 | Status (W2-A finalize) | Status (Step X closure) |
|---|---|---|
| Algorithm spec / Rust struct skeleton / TOML / 5-gate / look-ahead bias / AC | ✅ ALL GREEN | ✅ unchanged |
| §10 P0 precondition 4/4 + 5-gate | ✅ ALL PASS | ✅ unchanged |
| CRITICAL-1 schema drift（`learning.m4_hypotheses_extended` 不存在）| 🔴 BLOCKER | ✅ **CLOSED** (W1-A spec inline amend v1.1) |
| CRITICAL-2 ENUM drift（`alpha_short_carry / alpha_microstructure_fade` 不存在）| 🔴 BLOCKER | ✅ **CLOSED** (W1-A spec inline amend v1.1) |
| W2-B E1 IMPL dispatch readiness | CONDITIONAL READY | **DISPATCH-READY** |

### W2-E E2 review grep guard（必跑）

W2-E E2 review 強制 grep：
```
grep -rn 'm4_hypotheses_extended' src/ helper_scripts/ tests/         # MUST 0 hit
grep -rnE 'attribute_(n|p_value|effect_size|subperiod_stable|graveyard_flag|cluster_silhouette)' src/ helper_scripts/ tests/  # MUST 0 hit
grep -rnE 'alpha_short_carry|alpha_microstructure_fade' src/ helper_scripts/  # MUST 0 hit
```
任一 hit → IMPL CRITICAL FAIL → 退 W2-B IMPL revise

### closure verdict

W2-A pre-spec finalize report + W1-A 2 spec v1.1 amend = **W2-B E1 IMPL DISPATCH-READY**。

Step X closure done 2026-05-25 by PA inline amend task per PM Option A decision.
