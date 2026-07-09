# QC 數學審計 — Workflow A 22 fail-closed 1e-3 Invariant Option (c)

**Owner**: QC · **Date**: 2026-05-27 · **Verdict**: **CONDITIONAL APPROVE** — math sanity 全 PASS + C7 wording suggestion for TW

> Reconstructed from sub-agent inline return (harness constraint).

## §1 22 條 P_total Math Sanity 表

設 `P_total = Π_{i=1..22} P_i`，per AMD-09-03 §1.2 行 63 `P_i ∈ [0.5, 0.9]`。

| Scenario | P_i | log10(P_i) | sum | P_total | 量級 |
|---|---|---|---|---|---|
| 下界（全 0.5） | 0.5 | −0.30103 | −6.6227 | **2.384e-7** | 10^-7 |
| 均值（混合 0.7） | 0.7 | −0.15490 | −3.4078 | **3.908e-4** | **10^-3 ✅** |
| 上界（全 0.9） | 0.9 | −0.04576 | −1.0067 | **9.847e-2** | 10^-1 |

**QC-1 verdict**：**PASS** — AMD-09-03 §1.2 行 63 數學論證 verifiable + 字面準確。

## §2 Group B [1e-4, 1e-2] Window 合理性

逆向映射（每條 P_i 平均允許範圍）：
- P_total=1e-4 ⇒ geometric_mean(P_i)=10^(-4/22)=0.6577
- P_total=1e-2 ⇒ geometric_mean(P_i)=10^(-2/22)=0.8111

**對應 P_i window [0.658, 0.811]** — 落在 [0.5, 0.9] 正中央 50% segment、幾何中心 0.735。

**敏感度**：22 條同步漂 0.7→0.8 ⇒ Δlog10(P_total)=22×0.058=+1.28 ⇒ P_total 4e-4 → 8e-3（已超 1e-2）

**QC-4 verdict**：**PASS** — window 設計合理（既非過嚴也非過鬆，±1 order 是合理 sweet spot；±0.5 過嚴 false-positive / ±2 過鬆失意義）

## §3 22 條 Invariant 相關性 Cluster Sketch

**核心警告**：P_total=ΠP_i 假設獨立，但 22 條存在顯著相關性 cluster，乘積模型**低估**真實通過率。

| Cluster | 條目 | 相關來源 | ρ |
|---|---|---|---|
| A: IPC fail | I9 + I10 | 同 IPC 鏈路 | **0.8-0.95** HIGH |
| B: Shadow/Lease | I2 + I3 + I7 | 同 5-agent shadow chain | 0.6-0.8 MED-HIGH |
| C: Cognitive default | I4 + I12 | 同 Cognitive default | 0.5-0.7 MED |
| D: Sample-gate | I14 + I15 + I20 | 同樣本量根因 | **0.7-0.85** HIGH |
| E: 獨立 | I1, I5, I6, I8, I11, I13, I16-I22 餘 | 跨域 default | 0.1-0.3 LOW |

**有效獨立 invariant 數 N_eff ≈ 18.1**（非 22）
- corrected `P_total = 0.7^18.1 = 1.59e-3`（比獨立模型 4e-4 鬆 4×）
- **未否決 1e-3 量級結論**（corrected 1.59e-3 仍在 [1e-4, 1e-2] window）

**QC-2 verdict**：**CONDITIONAL** — Group A 個別 [0.5, 0.9] OK，但 cluster center invariant (I9/I10/I14/I15/I20) 應收緊到 **[0.55, 0.85]**（C7 給 TW）

## §4 Group C 重複計入 verify

PA §2.3 + FA §2 確認 Group C (I17-I21) 沿用既有 healthcheck spec，不繼承 1e-3。

| Healthcheck | Group C 容差 | Group A 重複？ |
|---|---|---|
| I17 [40] | avg_net + Wilson | NO（不同 abstraction） |
| I18 [33] | maker_fill_rate | NO |
| I19 [55] | chain_with_lease | NO |
| I20 [42b] | LOW_SAMPLE | NO |
| I21 [51] | n=0 binary | NO |

**Group B P_total 22 條乘積**：若改 17 條 ⇒ 0.7^17=2.34e-3 仍 1e-3 量級
- **建議妥協**：保留 22 條對齊 AMD 字面；[81] SQL 實作時 Group C 5 條用既有 healthcheck binary pass/fail（P_i=1.0 或 0），避免雙重定義容差

**QC-5 verdict**：NO 重複（前提：[81] SQL 用 binary 不重定義容差）

## §5 Healthcheck [81] SQL Prototype

Schema 選擇：`learning.failclosed_invariant_observation`（沿用 V106 `learning.health_observations` namespace + ADR-0042 6-domain convention）。Engine_mode filter 必 IN ('live','live_demo')。

### §5.1 DDL — Table + Hypertable + Indexes

```sql
-- V### (MIT 接手): learning.failclosed_invariant_observation
-- per AMD-09-03 §9 附錄 (2026-05-27) + Workflow A QC §5 prototype
-- 22 invariant (I1-I22) × per-strategy::symbol observation
-- 7d chunk + 7d compression + 90d retention (V106 pattern)

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname='timescaledb') THEN
        RAISE EXCEPTION 'V### Guard A FAIL: TimescaleDB extension missing.';
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS learning.failclosed_invariant_observation (
    observation_id        BIGSERIAL,
    observed_at           TIMESTAMPTZ NOT NULL,
    invariant_id          TEXT NOT NULL
                          CHECK (invariant_id IN (
                              'I1','I2','I3','I4','I5','I6','I7','I8',
                              'I9','I10','I11','I12','I13','I14','I15',
                              'I16','I17','I18','I19','I20','I21','I22',
                              'P_TOTAL'  -- Group B aggregate (per QC §5.2 micro-decision)
                          )),
    invariant_group       CHAR(1) NOT NULL CHECK (invariant_group IN ('A','B','C','D')),
    p_value               NUMERIC(10,8) NOT NULL CHECK (p_value >= 0 AND p_value <= 1),
    verdict               TEXT NOT NULL CHECK (verdict IN ('pass','warn','fail')),
    evidence_json         JSONB,
    engine_mode           TEXT NOT NULL
                          CHECK (engine_mode IN ('paper','demo','live_demo','live')),
    strategy_name         TEXT,
    symbol                TEXT,
    created_by            TEXT NOT NULL DEFAULT 'failclosed_invariant_monitor',
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    source_version        TEXT NOT NULL DEFAULT 'V###',
    PRIMARY KEY (observation_id, observed_at)
);

SELECT create_hypertable('learning.failclosed_invariant_observation',
    'observed_at', chunk_time_interval => INTERVAL '7 days', if_not_exists => TRUE);

ALTER TABLE learning.failclosed_invariant_observation SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'invariant_id, invariant_group',
    timescaledb.compress_orderby = 'observed_at DESC, observation_id DESC'
);
SELECT add_compression_policy('learning.failclosed_invariant_observation', INTERVAL '7 days');
SELECT add_retention_policy('learning.failclosed_invariant_observation', INTERVAL '90 days');

CREATE INDEX IF NOT EXISTS idx_failclosed_id_observed
    ON learning.failclosed_invariant_observation (invariant_id, observed_at DESC);
CREATE INDEX IF NOT EXISTS idx_failclosed_group_verdict
    ON learning.failclosed_invariant_observation (invariant_group, verdict, observed_at DESC)
    WHERE verdict IN ('warn','fail');
CREATE INDEX IF NOT EXISTS idx_failclosed_engine_mode
    ON learning.failclosed_invariant_observation (engine_mode, observed_at DESC);
```

### §5.2 INSERT 範例（per 24h cron）

4 Group 寫法各 1 範例（I1 Group A / I17 Group C / I8 + I22 Group D / P_TOTAL Group B aggregate）。完整 INSERT 模板見 sub-agent return §5.2。

### §5.3 7d Wilson Lower Bound + ADR Trigger Query

```sql
WITH per_invariant_7d AS (
    SELECT invariant_id, invariant_group, COUNT(*) AS n_obs, AVG(p_value) AS p_hat,
        ((AVG(p_value) + 1.96*1.96/(2.0*COUNT(*)))
         - 1.96 * SQRT(
             (AVG(p_value)*(1.0-AVG(p_value)) + 1.96*1.96/(4.0*COUNT(*))) / COUNT(*)
           )) / (1.0 + 1.96*1.96/COUNT(*)) AS wilson_lower
    FROM learning.failclosed_invariant_observation
    WHERE observed_at > now() - INTERVAL '7 days'
      AND engine_mode IN ('live','live_demo')
      AND invariant_group = 'A'
    GROUP BY invariant_id, invariant_group
)
SELECT 'group_a_per_invariant' AS check_type, invariant_id, n_obs, p_hat, wilson_lower,
    CASE
        WHEN wilson_lower > 0.9 THEN 'ADR_REEVAL_BYPASS'
        WHEN wilson_lower < 0.5 THEN 'FAIL_CLOSED_TOO_STRICT'
        WHEN invariant_id IN ('I9','I10','I14','I15','I20')
             AND wilson_lower > 0.85 THEN 'CLUSTER_DRIFT_WARN'
        ELSE 'OK'
    END AS verdict
FROM per_invariant_7d;
-- + UNION ALL group_b_p_total query (per_total_mean > 1e-2 OR < 1e-4 trigger)
```

**Total SQL LOC**: DDL ~70 + INSERT ~30 + Aggregation Query ~55 = ~155 行（MIT 補完 V106-style Guard 體檢 ~280 行）

## §6 Final QC Verdict: CONDITIONAL APPROVE

5 QC verify hook：
- QC-1 AMD math 重推：**PASS**
- QC-2 Group A [0.5, 0.9]：**CONDITIONAL** (C7 cluster center 收緊)
- QC-3 Group B SQL 化：**PASS** (§5 prototype)
- QC-4 ±1 order window：**PASS**
- QC-5 「≥ 50 條」/ Group C 重複：**PARTIAL** (≥50 條 unsubstantiated by FA;  Group C NO 重複前提 binary)

### C7 Wording Suggestion 給 TW（非 blocker）

TW patch §9.2 Group A footnote：「cluster center invariant (I9/I10 IPC fail cluster、I14/I15/I20 sample-gate cluster) 個別容差**收緊到 `P_i ∈ [0.55, 0.85]`** per QC §3 相關性 sketch；其餘 Group A invariant 沿用 `P_i ∈ [0.5, 0.9]`」

理由：ρ ≈ 0.8-0.95 cluster propagate 到 P_total 放大 1.2-1.6×，個別 0.9 邊界對 cluster center 太鬆。

QC AUDIT DONE: CONDITIONAL APPROVE / 1 wording suggestion (C7)
