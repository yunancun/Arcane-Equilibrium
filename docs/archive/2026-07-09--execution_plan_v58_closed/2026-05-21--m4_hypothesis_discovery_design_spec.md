---
spec: M4 Hypothesis Discovery — Self-Supervised Pattern Mining DESIGN Spec
date: 2026-05-21
author: PA recovery sub-agent (M4 DESIGN spec — Hypothesis Discovery 主體設計)
phase: v5.8 Sprint 1A-γ M4 module DESIGN
status: SPEC-DRAFT-V0
parent specs:
  - srv/docs/execution_plan/2026-05-20--execution-plan-v5.8.md §2 M4
  - srv/docs/execution_plan/2026-05-21--m4_minimum_bar_and_leakage_protocol.md（§2 6 attribute + §3 leak-free + §4 anti-mock；本 spec §3 §4 直引）
  - srv/docs/adr/0024-cowork-subscription-operator-assistant.md（Cowork DRAFT-only 邊界）
  - srv/docs/governance_dev/amendments/2026-05-21--AMD-2026-05-21-01-autonomy-vs-human-final-review.md（M4 DRAFT writeback 在 protected scope 邊界）
related memory:
  - memory/feedback_indicator_lookahead_bias.md（2026-04-24 P1-11 F3 RETRACT 教訓 — rolling shift(1) 強制）
  - memory/feedback_working_principles.md（對抗性驗證 + 誠實報告原則）
scope: DESIGN spec only — 不寫 IMPL code，不修 V103 本檔（V103 EXTEND outline 寫 §10），下游 sub-agent 補完整 ALTER DDL
---

# M4 Hypothesis Discovery — Self-Supervised Pattern Mining DESIGN Spec

## §0 TL;DR

M4 是 OpenClaw v5.8 的 **自監督 hypothesis discovery 模組**：從 live trading data + market data 自動挖掘 alpha candidate pattern，產出 DRAFT-state hypothesis 寫入 `learning.hypotheses` 表。

**核心定位**：
- M4 **不** 替代 StrategistAgent；StrategistAgent 仍是 H1 strategy authority
- M4 是 Strategist 的 **資料供應者**：把 live data 中可能的 alpha pattern 變成可審查 candidate
- M4 寫 DRAFT 經 **Decision Lease（無 live 寫入語意）** 落表；後續 LAL Tier 1-2 audit / Cowork hybrid review / operator manual promote 才能 transition past DRAFT
- 任何 M4 DRAFT 都不 auto-promote past Stage 0R；遵循 ADR-0024-lite + AMD-2026-05-21-01 protected scope (a) Stage transition

**6 attribute minimum bar** 全部直引 `2026-05-21--m4_minimum_bar_and_leakage_protocol.md` §2，本 spec §3 不重複定義數學細節，只描述 enforcement flow。

**Cross-language hypothesis fixture**：M4 Pattern miner 跨 Rust（fast pattern detector）+ Python（statistical engine）+ SQL（feature aggregation），三套必對齊 1e-4 fixture（numerical equivalence test）；shift(1) leak 偵測在三語言同時驗。

**M4 出口路徑**：
1. DRAFT 寫入 `learning.hypotheses` + V103 EXTEND 6 字段（含 leakage_scan_pass / decision_lease_draft_id / cowork_review_status）
2. M9 A/B test integration：DRAFT 進 M9 cluster 4 exit logic variant 之一做 paper-stage backtest
3. M6 reward integration：M4 DRAFT 的 reward weight 從 M6 5λ baseline 起算（不 auto-tune）
4. M11 dedup：M11 replay divergence trigger 不算 M4 hypothesis source（兩條獨立 pipeline）

---

## §1 Context — 為什麼需要 M4

### §1.1 v5.8 主檔 §2 M4 原樣設計面

v5.8 主檔 line 153-186 列「Self-Supervised Hypothesis Discovery」三 stage：

```
Pattern miner:
  - Statistical: rolling cross-correlation between asset features and forward returns
  - Temporal: event-window analysis (unlock / FOMC / liquidation cascade / large funding flip)
  - Cross-sectional: residual-return clustering, volatility regime clustering
```

但 v5.8 主檔 **未規範**：
- (a) hypothesis 從 raw data 到 DRAFT writeback 的 **end-to-end flow**（feature scan → pattern detection → leakage check → DRAFT 寫入）
- (b) DRAFT 寫入後的 **governance path**（誰能 promote past DRAFT？依何 evidence？）
- (c) M4 與 M9 / M6 / M11 的 **integration boundary**（哪些路徑是 M4 寫的，哪些不是）
- (d) **Cowork operator-assistant hybrid path**（ADR-0024-lite 給的 DRAFT-only 邊界如何與 M4 自動 discovery 串接）

本 spec land 上述 4 個 design gap。

### §1.2 M4 vs StrategistAgent 邊界

| 角色 | 職責 | 寫權 | Live order 路徑 |
|---|---|---|---|
| **StrategistAgent** | 主策略選型、參數權威、Lease 申請者 | 跨 strategy reweight（H1）| 透過 Guardian + Decision Lease → IntentProcessor |
| **M4** | hypothesis candidate 供應者；不替代 Strategist | DRAFT-only 寫 `learning.hypotheses` | **不直接走 live**；候選經 M9 A/B paper-stage backtest → operator promote → 再進 Strategist 視野 |

**核心區別**：StrategistAgent 是「在已知 strategy 集合內做選擇」；M4 是「擴張 hypothesis 候選池供未來 strategy 設計」。

### §1.3 與 ADR-0024-lite + AMD-2026-05-21-01 的關係

- **ADR-0024-lite**：Cowork（Claude Max / GPT Plus 訂閱）是 operator-assistant；可寫 DRAFT hypothesis 但不能 promote past DRAFT。**M4 自動 discovery 與 Cowork 共用同一個 `learning.hypotheses` DRAFT 表面**，但 source 不同（M4 寫 `hypothesis_source_module='M4_AUTO'`，Cowork 寫 `'OPERATOR'`）。
- **AMD-2026-05-21-01**：human final review 拆 protected vs opt-in scope。M4 DRAFT writeback **不在 opt-in scope (g)-(n) 任一條**，亦不在 protected scope (a)-(f) 任一條 → M4 是 **第三類「discovery-only」**：寫 DRAFT 不算 trade-affecting decision，不需要 Console toggle，但 promotion past DRAFT 屬 protected scope (a) Stage transition 範疇（operator click 必）。

### §1.4 為什麼自監督 hypothesis discovery 有價值

- **手動 hypothesis bandwidth bottleneck**：operator + Cowork 一週能寫 5-10 個 hypothesis；market 每日產生數百 micro-pattern；單靠人工挖掘必漏 alpha 機會
- **規則化 alpha decay**：已知 strategy（grid / MA / BB / funding_arb）alpha 5 textbook 全部 structurally alpha-deficient（per Sprint N+0 closure memory）；需新 hypothesis source 才能脫困
- **Y1 active loop bootstrap**：v5.8 Y2 active loop 需 ≥10 operator-validated hypothesis 才能啟動全 discovery loop（per ADR-0024-lite §future）；M4 + Cowork hybrid 共同 bootstrap 此 ledger

---

## §2 Hypothesis Generation Flow

### §2.1 End-to-end pipeline（4-stage）

```
[Stage 1] Feature scan
  └─ scan market data + live trading data + Bybit funding / OI / liquidation feed
  └─ output: candidate feature set（rolling stats / event windows / cross-sectional residuals）
  └─ leak-free 強制：所有 rolling stat 必 shift(1)（per §4）

[Stage 2] Pattern detection
  └─ Statistical: rolling cross-correlation between features × forward returns
  └─ Temporal: event-window analysis（unlock / FOMC / liquidation cascade / funding flip）
  └─ Cross-sectional: residual-return clustering / volatility regime clustering（Sprint 8 only）
  └─ output: hypothesis candidate（含 effect_size + p_value + N + sub-period stats）

[Stage 3] Leakage check + 6 attribute minimum bar
  └─ 自動 leakage scan SQL（per §4）
  └─ 6 attribute pass/fail 計算（per §3）
  └─ output: hypothesis 標籤 status='preregistered' candidate 或 'exploratory'

[Stage 4] DRAFT writeback Decision Lease
  └─ emit Decision Lease（lease_type='M4_DRAFT_WRITEBACK'，無 live order 語意）
  └─ INSERT INTO learning.hypotheses + V103 EXTEND 6 字段
  └─ post-hoc transparency：Slack + email + Console notification（per AMD-2026-05-21-01 §4.4 模式）
  └─ output: DRAFT row + audit trail
```

### §2.2 Stage 1 — Feature scan

**Input**：
- `market.kline` 1m/5m/15m/1h/4h timeframe × 25 symbols
- `trading.fills` past 90d（自家交易行為作 self-reference feature）
- `bybit.funding_rate` / `bybit.open_interest` / `bybit.liquidation` 30d
- `market.regime_label`（per M3 health snapshot；regime metadata）

**Output candidate feature set**（範例）：
- `rolling_corr_btc_eth_60m_shift1`（leak-free 60-min rolling correlation）
- `funding_flip_event_window_pm_4h`（funding rate flip 前後 ±4h window）
- `liquidation_cascade_count_30m_shift1`（30-min rolling liquidation cascade count）
- `cross_sectional_residual_return_btc_minus_alts`（橫截面 residual return）

**硬約束**：
- 所有 rolling stat **必 shift(1)**（per §4 §3 leak-free 強制；Rust / Python / SQL 三語言全套）
- Feature 計算結果落 `learning.feature_scan_cache`（PK: feature_id + as_of_ts）供 Stage 2 重用，避免重算

### §2.3 Stage 2 — Pattern detection

#### §2.3.1 Statistical pattern

- 跨 feature × forward return 算 Pearson / Spearman 相關
- forward return windows：1m / 5m / 15m / 1h / 4h（共 5 window）
- 每 batch 並行 hypothesis 數估計 K：500 hypothesis × 5 window = K = 2,500 → Bonferroni α_corrected = 0.05 / 2500 = 2e-5（per leakage spec §2.2）

#### §2.3.2 Temporal pattern（event-window）

- Event sources：FOMC announcement / token unlock schedule / liquidation cascade trigger / funding rate flip
- Event window analysis：t-30min ... t+30min 觀察 forward return distribution shift
- Edge case：event-based hypothesis N 可能 < 30（如 FOMC 每年 8 次）→ 強制 `status='exploratory'`，標記「event-rate constrained」（per leakage spec §2.1.3）

#### §2.3.3 Cross-sectional pattern（Sprint 8 only）

- Residual-return clustering（K-means / HDBSCAN / GMM）
- Volatility regime clustering
- 必算 5-fold purged time-series CV silhouette ≥ 0.5（per leakage spec §2.6）
- Sprint 2-3 **不啟用** clustering（Sprint 8 才開）

### §2.4 Stage 3 — Leakage check + 6 attribute minimum bar enforcement

逐個 candidate 計算 6 attribute（per leakage spec §2）：

| Attribute | 計算 | 通過條件 |
|---|---|---|
| N | event/observation count | ≥ 30 |
| Bonferroni p | raw p × K | < 0.05 / K |
| Cohen's d | (mean_t - mean_c) / pooled_std | ≥ 0.2 |
| Sub-period stability | 50/50 split + Mann-Whitney U | 同方向 + \|Δeffect\| < 0.5σ |
| Graveyard flag | Harvey-Liu-Zhu fuzzy match | 不阻 DRAFT，但 review prompt |
| Silhouette（clustering only）| 5-fold purged CV avg | ≥ 0.5（or skip + spec_no_clustering=true）|

**Leakage scan** 同時跑（per §4）：
- SQL grep：`ROWS BETWEEN ... AND CURRENT ROW` 出現即 reject
- pandas grep：`.rolling(N).mean()` 後無 `.shift(1)` 即 reject
- Rust grep：`rolling_mean(...)` 後無 `.shift(lit(1))` 即 reject
- 對 DRAFT 跑 §3.5 verification SQL（leak vs shift1 effect_diff > 0.1 → leak suspected）

### §2.5 Stage 4 — DRAFT writeback Decision Lease

#### §2.5.1 為什麼 M4 DRAFT 走 Decision Lease

M4 DRAFT 寫 `learning.hypotheses` **不是 trade-affecting decision**（DRAFT 不會引發 live order），但仍 emit Decision Lease 理由：
1. **audit traceability**（16 root principle #8）：每個 DRAFT 寫入 lease_id 落表，可重建寫入時 toggle_state / feature scan input / leakage scan result
2. **與 ADR-0024-lite Cowork DRAFT 對齊**：Cowork 寫 DRAFT 也經 lease（per ADR-0024-lite + AMD-2026-05-21-01 §4.4）；M4 自動 DRAFT 對等
3. **不繞 5-gate**：M4 DRAFT lease 仍經 GovernanceHub.acquire_lease()，雖然 lease_type='M4_DRAFT_WRITEBACK' 不帶 live order intent，但 lease lifecycle + RBAC + audit 全套不繞

#### §2.5.2 Lease 屬性

| 屬性 | 值 |
|---|---|
| `lease_type` | `'M4_DRAFT_WRITEBACK'` |
| `actor` | `'m4_pattern_miner'` |
| `target_state` | `'learning.hypotheses INSERT (status=draft)'` |
| `live_order_intent` | `false`（M4 DRAFT 不 trigger live order） |
| `expires_at` | `now() + INTERVAL '5 minutes'` |
| `decision_lease_draft_id` | INSERT 後 backref 寫回 `learning.hypotheses.decision_lease_draft_id` 欄位 |

#### §2.5.3 寫入交易

```
BEGIN;
  -- 1. Acquire lease
  SELECT GovernanceHub.acquire_lease(
    lease_type := 'M4_DRAFT_WRITEBACK',
    actor := 'm4_pattern_miner',
    expires_at := now() + INTERVAL '5 minutes'
  ) INTO v_lease_id;

  -- 2. INSERT hypothesis DRAFT
  INSERT INTO learning.hypotheses (
    hypothesis_id, strategy_name, status,
    -- M4 minimum bar 6 attribute 字段（V103 EXTEND）
    m4_attribute_n, m4_attribute_p_bonferroni, m4_attribute_effect_size,
    m4_attribute_subperiod_pass, m4_attribute_graveyard_flag, m4_attribute_silhouette,
    -- M4 自動 discovery 額外字段（V103 EXTEND 本 spec §10）
    hypothesis_source_module, leakage_scan_pass, bonferroni_corrected_p,
    replicability_score, decision_lease_draft_id, cowork_review_status,
    created_at
  ) VALUES (
    gen_random_uuid(), $strategy, $status,
    $n, $p_bonf, $cohens_d, $subperiod_pass, $graveyard_flag, $silhouette,
    'M4_AUTO', $leak_pass, $p_bonf, $repl_score, v_lease_id, 'NONE',
    now()
  );

  -- 3. Release lease（DRAFT writeback 完成）
  SELECT GovernanceHub.release_lease(v_lease_id, outcome := 'SUCCESS');
COMMIT;
```

#### §2.5.4 Post-hoc transparency

每筆 M4 DRAFT writeback emit：
- Slack notification（topic：`#m4-draft-writeback`）：strategy / N / p_bonf / d / leak_pass / lease_id
- Email digest（每 24h 一封；列當日全部 DRAFT）
- Console notification（Learning Cockpit 卡片新增 row）

對應 AMD-2026-05-21-01 §4.4 多通道通知模式。

### §2.6 反例：M4 不允許做的事

- **不允許**直接寫 `trading.fills` / `trading.signals`（屬 IntentProcessor 寫權，違反 16 root principle #1 單一寫入口）
- **不允許** auto-promote DRAFT past `status='preregistered'`（promotion 屬 protected scope (a) Stage transition）
- **不允許**直接觸發 live order（即使 hypothesis 通過 6 attribute；live order 路徑 = StrategistAgent + Guardian + Decision Lease 完整鏈）
- **不允許**修改 `risk_config_*.toml` 或 strategy parameter（違反 ADR-0024-lite forbidden uses #2 對等規則）
- **不允許** L2 Claude API call 做 hypothesis generation（per ADR-0020 + ADR-0024-lite；M4 自動 discovery 是 L0 rule-based + L1 Ollama only）

---

## §3 Minimum Bar 6 Attribute Enforcement

本節描述 enforcement flow；數學定義 + p-value correction 細節**全部直引** `2026-05-21--m4_minimum_bar_and_leakage_protocol.md` §2 不重複。

### §3.1 6 attribute pass/fail decision table

| Attribute | Pass condition | Fail → status | 參考 |
|---|---|---|---|
| **N ≥ 30** | event/observation count ≥ 30 | `'exploratory'`（非 event-based）或 `'exploratory' + event-rate constrained` flag（event-based） | leakage spec §2.1 |
| **Bonferroni p < 0.05 / K** | raw_p × K < 0.05 | `'exploratory'` | leakage spec §2.2 |
| **Cohen's d ≥ 0.2** | \|d\| ≥ 0.2 + \|d\| < 3.0 outlier check | `'exploratory'`（< 0.2）或 `'exploratory' + effect_size_outlier=true`（> 3.0）| leakage spec §2.3 |
| **Sub-period stability** | 同方向 AND \|Δeffect\| < 0.5σ | `'exploratory'` | leakage spec §2.4 |
| **Graveyard flag** | fuzzy similarity ≤ 0.6 | 不阻；只 `graveyard_flag=true` warning | leakage spec §2.5 |
| **Silhouette ≥ 0.5**（clustering only）| 5-fold purged CV avg ≥ 0.5 | clustering hypothesis fail → `'exploratory'`；non-clustering → NULL + `spec_no_clustering=true` skip | leakage spec §2.6 |

### §3.2 整體 pass criterion

```
6_attribute_all_pass = (
    m4_attribute_n >= 30
    AND m4_attribute_p_bonferroni < (0.05 / K)
    AND ABS(m4_attribute_effect_size) >= 0.2
    AND m4_attribute_subperiod_pass = TRUE
    AND COALESCE(m4_attribute_silhouette >= 0.5, TRUE)  -- non-clustering skip
    -- graveyard_flag 不參與 pass criterion，只作 warning
)
```

- **全 pass** → status='preregistered' 候選（仍需 operator click 才能 transition past `preregistered`）
- **任一 fail** → status='exploratory'（DRAFT 保留，標 fail 原因）

### §3.3 Enforcement 階段

Stage 3 自動跑 6 attribute 計算 → 寫 V103 EXTEND 字段 → 決定 status；不依賴外部 review。

### §3.4 Anti-pattern alert

PA / E1 IMPL 階段 grep（per leakage spec §2.2.4）：
- `WHERE p_value < 0.05` 無 Bonferroni / FDR 邊界註解 → reject sign-off
- `silhouette_score(...)` 後無 5-fold purged CV wrapper → reject sign-off
- `effect_size` 計算後無 outlier range check（|d| > 3.0）→ warning + 要求補

---

## §4 Leakage Protocol Enforcement

### §4.1 三語言 shift(1) leak-free 強制

直引 leakage spec §3.2-§3.5 三語言範例 + §3.5 verification SQL，不重複內容。

| 語言 | Leak-free pattern | Anti-pattern |
|---|---|---|
| **SQL** | `ROWS BETWEEN N PRECEDING AND 1 PRECEDING` | `ROWS BETWEEN N-1 PRECEDING AND CURRENT ROW`（leak）|
| **pandas** | `df.rolling(N).mean().shift(1)` | `df.rolling(N).mean()`（含 current bar = leak）|
| **Rust polars** | `col(...).rolling_mean(...).shift(lit(1))` | `col(...).rolling_mean(...)`（缺 shift = leak）|

### §4.2 V103 EXTEND 6 字段 leak audit

DRAFT 寫入後，自動跑 `§3.5 verification SQL`（leakage spec）：
- `effect_value_with_current_bar` vs `effect_value_shift1` 兩版並列計算
- `|mean_effect_leak - mean_effect_clean| > 0.1` → `leak_suspected=true` → DRAFT 拒絕 + RCA log

### §4.3 leakage scan SQL（自動化）

```sql
-- Stage 3 自動跑（每個 DRAFT 寫入前）：
WITH leak_audit AS (
    SELECT
        h.hypothesis_id,
        h.m4_attribute_effect_size,
        la.effect_value_with_current_bar AS leak_effect,
        la.effect_value_shift1 AS clean_effect,
        ABS(la.effect_value_with_current_bar - la.effect_value_shift1) AS effect_diff
    FROM learning.hypotheses h
    JOIN learning.hypothesis_observation_leak_audit la USING (hypothesis_id)
    WHERE h.hypothesis_source_module = 'M4_AUTO'
      AND h.status = 'draft'
)
SELECT
    hypothesis_id,
    effect_diff,
    effect_diff > 0.1 AS leak_suspected,
    -- leak_suspected=true → trigger DRAFT reject pathway
    CASE WHEN effect_diff > 0.1 THEN 'REJECT_LEAK_SUSPECTED'
         ELSE 'PASS' END AS leakage_scan_action
FROM leak_audit;
```

leakage scan 結果寫 `leakage_scan_pass` 欄位（V103 EXTEND）：
- `true` → DRAFT 可繼續流程
- `false` → DRAFT 拒絕寫入 + RCA log emit Slack alert

### §4.4 Cross-language fixture 對齊

M4 Pattern miner 跨 Rust（fast detector）+ Python（statistical engine）+ SQL（aggregation），三套必對齊 **1e-4 numerical equivalence**：

```python
# srv/tests/test_m4_cross_language_fixture.py
def test_rolling_corr_shift1_equivalence():
    """
    M4 Pattern miner 跨語言 fixture 對齊測試。
    Rust polars / Python pandas / SQL window function 三套對同一 input 算 rolling_corr.shift(1)。
    要求：max(|rust - python|, |rust - sql|, |python - sql|) < 1e-4。

    為什麼：numerical 不一致 → DRAFT writeback 由哪個語言 trigger 結果不同 = 不可重現 audit failure。
    """
    fixture_input = load_fixture("rolling_corr_shift1_input.parquet")
    result_rust = call_rust_polars_rolling_corr_shift1(fixture_input)
    result_python = call_python_pandas_rolling_corr_shift1(fixture_input)
    result_sql = call_pg_window_rolling_corr_shift1(fixture_input)
    assert abs(result_rust - result_python).max() < 1e-4
    assert abs(result_rust - result_sql).max() < 1e-4
    assert abs(result_python - result_sql).max() < 1e-4
```

### §4.5 Anti-mock 防護

直引 leakage spec §4.4：mock 不可掩蓋 leak。
- `unittest.mock.MagicMock` 在 M4 Pattern miner test 中**僅用於 isolation**（mock 外部 API / DB / 第三方 lib）
- **不可**用 mock 偽造 rolling stat 回傳值讓 leak 通過 test
- Code review checklist 必驗：每個 mock 回傳 series **時序語意符合 shift(1)**

### §4.6 IMPL DONE 強制 grep

任何 M4 Pattern miner code PR IMPL DONE 前，PA 派 sub-agent 跑（per leakage spec §4.1-§4.2）：
```bash
grep -rn 'rolling.*mean\(\)\|rolling.*std\(\)\|rolling.*corr\(\)\|rolling.*max\(\)\|rolling.*min\(\)' \
    --include='*.py' --include='*.rs' \
    srv/python/research srv/rust/openclaw_engine/src/strategies
grep -rn 'ROWS BETWEEN' --include='*.sql' --include='*.py' srv/sql srv/python
```

任何 rolling 沒 `.shift(1)` 且無 inline 反證註解 → FAIL → sub-agent reject sign-off。

---

## §5 M4 DRAFT Writeback Decision Lease（不繞 5-gate）

### §5.1 為什麼 M4 DRAFT 需要 lease

per §2.5.1：audit traceability + 對齊 Cowork DRAFT pattern + 不繞 5-gate。

### §5.2 Lease lifecycle

```
[acquire] GovernanceHub.acquire_lease(
    lease_type='M4_DRAFT_WRITEBACK',
    actor='m4_pattern_miner',
    expires_at=now() + 5min,
    live_order_intent=false
)
  → lease_id (UUID)

[execute] INSERT INTO learning.hypotheses (..., decision_lease_draft_id=lease_id, ...)

[release] GovernanceHub.release_lease(lease_id, outcome='SUCCESS')

[audit] agent.ai_invocations + learning.lease_audit_log 同步寫
```

### §5.3 不繞 5-gate 證明

| Gate | M4 DRAFT 是否經過 | 說明 |
|---|---|---|
| **live_reserved** | N/A | M4 DRAFT 不 trigger live order，live_reserved 不需 check |
| **Operator role auth** | ✅ 經過 | lease acquire 仍經 RBAC（service-role `m4_pattern_miner`）|
| **OPENCLAW_ALLOW_MAINNET=1** | N/A | M4 DRAFT 不涉 Mainnet，env var 不需 check |
| **secret slot** | ✅ 經過（讀 DB credential） | DB connection 仍走 secret slot |
| **authorization.json** | N/A | DRAFT 寫入不需 trade authorization |

**結論**：M4 DRAFT 不走 5-gate 中的 trade-specific gate（live_reserved / Mainnet / authorization.json），但 lease + RBAC + audit 全套不繞。

### §5.4 LAL Tier 1-2 audit path

M4 DRAFT 寫入後進入 LAL（Learning Audit Ledger）audit 流程：
- **LAL Tier 1**（automated audit）：
  - Bonferroni p / effect size / leakage_scan_pass 標 PASS/FAIL
  - graveyard_flag warning 升 operator review prompt
  - Tier 1 audit 落 `learning.lal_tier1_audit` 表
- **LAL Tier 2**（cowork hybrid auto-suggest）：
  - Y2 啟用（per ADR-0024-lite 'Track B Hypothesis Ledger ≥10 operator-validated' precondition）
  - Cowork scheduled task 讀 LAL Tier 1 PASS hypothesis → 寫 Cowork analysis markdown → operator review
  - Tier 2 **不 auto-promote**（per ADR-0024-lite forbidden uses #1）

### §5.5 Promotion path（M4 DRAFT past `'preregistered'`）

M4 DRAFT 從 `'preregistered'` past（→ `'experimenting'` → `'promoted'`）**必經 operator manual Console action**：
- 屬 protected scope (a) Stage transition（per AMD-2026-05-21-01 §2）
- 每 transition emit `operator_click_evidence`（per AMD §2 protected scope rationale）
- 不允許 batch confirm（per AMD §2 禁止 helper 路徑）

### §5.6 Stage 0R 邊界

M4 DRAFT 通過 6 attribute 後是 `'preregistered'`，**不等於** Stage 0R 通過。Stage 0R 是 replay preflight，與 M4 hypothesis discovery 是兩條獨立 pipeline：
- Stage 0R = 「策略現有版本是否能在 replay 中重現 historical alpha」
- M4 = 「是否有新 hypothesis pattern 值得 backtest」

M4 DRAFT promote past `'preregistered'` 後，**才**進入 M9 A/B 並 trigger Stage 0R-pattern replay。

---

## §6 M4 ↔ M9 A/B Integration

### §6.1 為什麼 M4 → M9

M4 產出 DRAFT hypothesis（6 attribute pass）→ 需要 **paper-stage backtest** 驗證在 out-of-sample data 下 effect 是否 persist → 對應 v5.8 §2 M9 A/B test cluster 4 exit logic variant。

### §6.2 Integration boundary

| 階段 | M4 責任 | M9 責任 | 邊界 |
|---|---|---|---|
| DRAFT 生成 | ✅ | ✗ | M4 寫 DRAFT；M9 不接觸 raw feature scan |
| backtest 設計 | ✗ | ✅ | M9 拿 DRAFT spec → 設計 A/B test variant |
| paper-stage execution | ✗ | ✅ | M9 走 paper-engine backtest |
| outcome attribution | ✗ | ✅ | M9 寫 outcome 回 `learning.ab_test_outcomes` |
| DRAFT status transition | ✗ | △ | M9 提 outcome；transition 仍走 operator click（protected scope a）|

### §6.3 Handoff schema

M4 DRAFT promote 至 `'preregistered'` 後（operator click 觸發），自動 INSERT `learning.m9_ab_test_queue`：
```
INSERT INTO learning.m9_ab_test_queue (
    hypothesis_id,
    cluster_assignment,  -- 1-4，M9 4 cluster exit logic variant 之一
    queued_at,
    status  -- 'pending' / 'running' / 'completed' / 'failed'
);
```

M9 worker 拉 queue → 跑 backtest → 寫 `learning.ab_test_outcomes`（不 promote DRAFT，只報告 outcome）。

### §6.4 不允許的路徑

- **不允許** M4 自己跑 backtest（職責屬 M9）
- **不允許** M9 修改 M4 DRAFT 的 6 attribute 字段（attribute 是 discovery-time 快照，不可事後改）
- **不允許** M4 DRAFT 跳過 M9 A/B 直接進 Strategist 視野（必經 paper-stage backtest）

---

## §7 M4 ↔ M6 Reward Integration

### §7.1 為什麼 M4 → M6

M4 產出 hypothesis 後，若 promote past `'experimenting'`（Stage 0R replay PASS + Stage 1 Demo micro-canary active），M6 Auto-Allocator 需 reward weight baseline 才能 size allocation。Paper engine output is Archive/diagnostic only and cannot promote a hypothesis.

### §7.2 Reward weight baseline

M4 DRAFT 的初始 reward weight **從 M6 5λ baseline 起算**（不 auto-tune）：

| λ | 預設值 | 適用 |
|---|---|---|
| **λ_dd**（drawdown penalty） | 0.20 | 全策略 |
| **λ_tail**（tail risk penalty） | 0.15 | 全策略 |
| **λ_turnover**（turnover cost） | 0.25 | 全策略 |
| **λ_slippage**（slippage cost） | 0.20 | 全策略 |
| **λ_decay**（alpha decay penalty） | 0.20 | 全策略 |

M4 DRAFT initial weight = (Sharpe ratio target) × Π(1 - λ_i) baseline，per M6 spec。

### §7.3 不 auto-tune 規則

- M4 DRAFT promote 至 paper-active 後，M6 Auto-Allocator **不**對該 hypothesis auto-tune reward weight
- Reward weight tune 需 6+ months Advisory + > 80% approval（per AMD-2026-05-21-01 opt-in scope (k) M6 reward weight ≤ 30% auto-apply）
- 在達到此 precondition 前，weight 永遠 = baseline

### §7.4 Integration constraint

- **不允許** M4 直接寫 M6 reward weight 表（屬 M6 寫權）
- **不允許** M6 修改 M4 DRAFT 的 6 attribute 字段
- M4 → M6 handoff 透過 M9 outcome：M9 paper-stage backtest 完成後寫 `learning.ab_test_outcomes` → M6 讀 outcome 計算 reward weight

---

## §8 M4 ↔ M11 Dedup

### §8.1 為什麼需要 dedup

M11 是 replay divergence detector（per v5.8 §2 M11）：當 replay 結果與 live 結果偏離 > threshold 時，trigger investigation。

潛在混淆：M11 replay divergence trigger 可能被誤認為 M4 hypothesis source。

### §8.2 兩條獨立 pipeline

| Module | 觸發來源 | 輸出 | DRAFT writeback 路徑 |
|---|---|---|---|
| **M4** | feature scan + pattern detection | hypothesis candidate | ✅ 寫 `learning.hypotheses` `'M4_AUTO'` |
| **M11** | replay vs live divergence | investigation alert | ❌ **不寫** `learning.hypotheses`；寫 `learning.replay_divergence_alert` |

### §8.3 規則

- **M11 replay divergence trigger 不算 M4 hypothesis source**
- M11 發出 alert 後，operator 可手動依 alert 內容寫 hypothesis（透過 Cowork operator-assistant → `'OPERATOR'` source）
- M4 自動 discovery **不**讀 M11 alert 作 feature input（避免循環依賴）

### §8.4 Dedup enforcement

DRAFT 寫入時，`hypothesis_source_module` 欄位 CHECK constraint：
```sql
CHECK (hypothesis_source_module IN ('M4_AUTO', 'OPERATOR', 'HISTORIC'))
```

`'HISTORIC'` 對應 ADR-0024-lite 未來 'Track B Hypothesis Ledger ≥10 operator-validated' 累積的歷史條目。M11 source 不在此 enum 內 → schema-level dedup。

---

## §9 Cowork Hybrid Path（ADR-0024 Operator-Assistant Y1+Y2）

### §9.1 為什麼這節必含

per ADR-0024-lite + AMD-2026-05-21-01，Cowork（Claude Max / GPT Plus 訂閱）作為 operator-assistant 與 M4 自動 discovery **共用同一 DRAFT 表面**。需明示 hybrid boundary。

### §9.2 Cowork operator-assistant 邊界（直引 ADR-0024-lite）

**允許**：
- Operator-initiated interactive analysis（讀 logs / market state / 寫 markdown）
- Scheduled Cowork tasks（max 4/day）：讀 trading.fills / signals / ai_invocations / cost_edge_advisor_log past 24h
- Cowork session 寫 `learning.hypotheses` DRAFT only（source='OPERATOR'）

**禁止**：
- 不可 transition DRAFT past `'preregistered'` automatically
- 不可 modify runtime config / risk_config / strategy parameter / live authorization / live_reserved / Decision Lease / order submission
- 不可繞 Guardian / H0 Gate / Decision Lease
- 不可 24/7 autonomous loop
- 不可替代 L1 Ollama runtime-touching analysis

### §9.3 Y1 read-only review pattern

**Y1 Sprint 1-5（含 1A-γ 之後）**：
- Cowork **僅 read-only review** M4 自動 discovery 寫的 DRAFT
- Cowork scheduled task 4/day cap：讀 past 24h M4 DRAFT 寫 markdown analysis → operator working directory
- `cowork_review_status` 寫 `'NONE'`（無 active review）或 `'PENDING'`（review markdown 已寫，等 operator 看）
- **不啟用** Cowork 寫 hypothesis（避免 Y1 早期混淆 source attribution）

### §9.4 Y2 LAL Tier 2 auto-suggest

**Y2（per ADR-0024-lite 'Track B Hypothesis Ledger ≥10 operator-validated' 達標後）**：
- Cowork scheduled task 升級：讀 LAL Tier 1 PASS hypothesis → 寫 review suggestion markdown + Cowork 寫 hypothesis（source='OPERATOR'）
- LAL Tier 2 auto-suggest **僅 informational**；不 auto-promote
- `cowork_review_status` 更新流程：
  - `'NONE'` → `'PENDING'`（Cowork 寫 review markdown 完成）
  - `'PENDING'` → `'APPROVED'`（operator 在 Console click approve）
  - `'PENDING'` → `'REJECTED'`（operator 在 Console click reject）
- `'APPROVED'` 後**仍**走 operator manual Console click 才能 transition DRAFT past `'preregistered'`（雙確認；protected scope (a) 不縮短）

### §9.5 Cowork hybrid 不 auto-promote 證明

| 路徑 | Cowork 可做 | Cowork 不可做 |
|---|---|---|
| 讀 M4 DRAFT | ✅（read-only review）| — |
| 寫 review markdown 到 operator workspace | ✅ | — |
| 寫 hypothesis（source='OPERATOR'） | ✅ Y2 only | Y1 不允許 |
| 更新 `cowork_review_status` 'NONE'→'PENDING' | ✅ Y2 only | Y1 不允許 |
| 更新 `cowork_review_status` 'PENDING'→'APPROVED' | ✅ Y2 only | Y1 不允許 |
| transition DRAFT past `'preregistered'` | ❌ 永不允許 | — |
| 修 6 attribute 字段 | ❌ 永不允許 | — |
| trigger M9 A/B queue | ❌ 永不允許（屬 operator click 後 trigger）| — |

### §9.6 Cowork audit 屬性（per ADR-0024-lite Cost & Audit）

- `agent.ai_invocations` 記錄 `invocation_type='cowork_operator_assist'` 或 `'cowork_scheduled_task'`
- `track='baseline'`
- Cost = $0（subscription sunk cost）
- token count + invocation count 仍記錄

### §9.7 M4 vs Cowork hybrid coexist

| Source | 寫 DRAFT 觸發 | 寫 6 attribute 字段 | promote past `'preregistered'` |
|---|---|---|---|
| **M4 auto** | Stage 4 自動 | 自動填（Stage 3）| operator click protected (a) |
| **Cowork operator-assistant** | scheduled task / operator interactive | 由 Cowork 自行算填 + leakage scan 跑 | operator click protected (a) |
| **OPERATOR direct（manual Console）** | operator 手動 input | operator 自填或不填（exploratory）| operator click protected (a) |

---

## §10 V103 EXTEND for M4 Column（Outline Only — Not Implementation）

### §10.1 範圍與責任

**本 spec 不寫實 ALTER SQL**；只列 6 column outline + Guard B 模式 + ALTER 範式 + migration up/down 結構。完整 DDL 由後續 sub-agent 補（per CR-1 v5.7 follow-up 主會話收口 + 對齊 leakage spec §5.1）。

### §10.2 6 new column outline

| Column | Type | NOT NULL | DEFAULT | CHECK | 用途 |
|---|---|---|---|---|---|
| `hypothesis_source_module` | TEXT | YES | `'M4_AUTO'` | `IN ('M4_AUTO', 'OPERATOR', 'HISTORIC')` | DRAFT 來源 module；M4 vs Cowork operator vs 歷史 |
| `leakage_scan_pass` | BOOLEAN | YES | `TRUE` | — | Stage 3 leakage scan（§4）結果；false → DRAFT reject pathway |
| `bonferroni_corrected_p` | NUMERIC(10,8) | NO（exploratory 可 NULL） | — | `>= 0 AND <= 1` | Bonferroni-corrected p-value（per leakage spec §2.2）|
| `replicability_score` | NUMERIC(5,4) | NO | — | `>= 0 AND <= 1` | 跨 sub-period stability + cross-asset / cross-timeframe robustness score |
| `decision_lease_draft_id` | UUID | YES | — | — | M4 DRAFT writeback lease_id backref（per §2.5）|
| `cowork_review_status` | TEXT | YES | `'NONE'` | `IN ('NONE', 'PENDING', 'APPROVED', 'REJECTED')` | Cowork hybrid review state（per §9.4）|

### §10.3 ALTER TABLE 範式（outline only — 不實做）

```sql
-- V103 EXTEND M4 6 column —— 詳細 DDL 由下游 sub-agent 補
-- 必含 Guard B（type-sensitive ADD COLUMN）per CLAUDE.md §Data, Migrations, And Validation

-- Guard B 範式：每個 ADD COLUMN 必 IF NOT EXISTS
ALTER TABLE learning.hypotheses
    ADD COLUMN IF NOT EXISTS hypothesis_source_module TEXT
        NOT NULL DEFAULT 'M4_AUTO'
        CHECK (hypothesis_source_module IN ('M4_AUTO', 'OPERATOR', 'HISTORIC'));

ALTER TABLE learning.hypotheses
    ADD COLUMN IF NOT EXISTS leakage_scan_pass BOOLEAN
        NOT NULL DEFAULT TRUE;

ALTER TABLE learning.hypotheses
    ADD COLUMN IF NOT EXISTS bonferroni_corrected_p NUMERIC(10, 8)
        CHECK (bonferroni_corrected_p IS NULL OR (bonferroni_corrected_p >= 0 AND bonferroni_corrected_p <= 1));

ALTER TABLE learning.hypotheses
    ADD COLUMN IF NOT EXISTS replicability_score NUMERIC(5, 4)
        CHECK (replicability_score IS NULL OR (replicability_score >= 0 AND replicability_score <= 1));

ALTER TABLE learning.hypotheses
    ADD COLUMN IF NOT EXISTS decision_lease_draft_id UUID;
    -- FK constraint 暫不加；由下游 sub-agent 決定是否 backref governance.decision_lease_audit

ALTER TABLE learning.hypotheses
    ADD COLUMN IF NOT EXISTS cowork_review_status TEXT
        NOT NULL DEFAULT 'NONE'
        CHECK (cowork_review_status IN ('NONE', 'PENDING', 'APPROVED', 'REJECTED'));

-- Index outline（hot-path Guard C 模式；下游 sub-agent 補）：
-- CREATE INDEX IF NOT EXISTS idx_hypotheses_source_status
--     ON learning.hypotheses (hypothesis_source_module, status, created_at DESC);
-- CREATE INDEX IF NOT EXISTS idx_hypotheses_leakage_scan
--     ON learning.hypotheses (leakage_scan_pass, created_at DESC) WHERE status = 'draft';
-- CREATE INDEX IF NOT EXISTS idx_hypotheses_cowork_review
--     ON learning.hypotheses (cowork_review_status, created_at DESC) WHERE cowork_review_status IN ('PENDING', 'APPROVED');
```

### §10.4 Migration up outline

```
V### up:
1. ALTER TABLE learning.hypotheses ADD COLUMN ...（6 條，每條 Guard B IF NOT EXISTS）
2. UPDATE 既有 row：
   - hypothesis_source_module = 'OPERATOR'（既有 row 都是 operator manual / Cowork 寫的，預設）
   - leakage_scan_pass = TRUE（既有 row 假設 pass；歷史檢查由後續 backfill task）
   - cowork_review_status = 'NONE'（預設）
   - 其他 column 保 NULL（既有 row 無相應 metadata）
3. CREATE INDEX IF NOT EXISTS ...（per Guard C，hot-path indexes）
4. INSERT V103_EXTEND_M4 marker into learning.migration_marker
```

### §10.5 Migration down outline

```
V### down（rollback；應為冪等）：
1. DROP INDEX IF EXISTS idx_hypotheses_source_status
2. DROP INDEX IF EXISTS idx_hypotheses_leakage_scan
3. DROP INDEX IF EXISTS idx_hypotheses_cowork_review
4. ALTER TABLE learning.hypotheses DROP COLUMN IF EXISTS hypothesis_source_module
5. ALTER TABLE learning.hypotheses DROP COLUMN IF EXISTS leakage_scan_pass
6. ALTER TABLE learning.hypotheses DROP COLUMN IF EXISTS bonferroni_corrected_p
7. ALTER TABLE learning.hypotheses DROP COLUMN IF EXISTS replicability_score
8. ALTER TABLE learning.hypotheses DROP COLUMN IF EXISTS decision_lease_draft_id
9. ALTER TABLE learning.hypotheses DROP COLUMN IF EXISTS cowork_review_status
10. DELETE FROM learning.migration_marker WHERE marker = 'V103_EXTEND_M4'
```

**注意**：down 路徑會失去 M4 DRAFT 寫入的 source attribution + leakage scan + lease backref；rollback 後新 M4 DRAFT 無法寫入（缺欄位）。down 適用於 schema 緊急回退場景，不適用於正常營運。

### §10.6 V103 本檔不修

**本 spec 不修** `2026-05-21--v103_v104_earn_hypotheses_schema_spec.md` 本檔；V103 spec 本檔的 ALTER 由後續 sub-agent 在 CR-1 v5.7 follow-up 主會話收口統一 land。本 §10 是 outline only。

### §10.7 Linux PG dry-run mandate

per CLAUDE.md §七 + V055 mandate + feedback `feedback_v_migration_pg_dry_run`：
- V### IMPL **必經** Linux PG empirical dry-run（mock pytest + static review 抓不到 PL/pgSQL 語意）
- 下游 sub-agent 補 ALTER DDL 完成後，**強制** `ssh trade-core` 跑 dry-run + reflection query 驗 column type / constraint / default 完整落盤

---

## §11 Acceptance Criteria

### §11.1 5 條 acceptance（DESIGN spec 不寫 IMPL test，列驗收門檻）

| # | Acceptance | 驗收方式 |
|---|---|---|
| **AC-1** | M4 Pattern miner code 全路徑 leakage scan PASS | grep `rolling.*mean\(\)` / `ROWS BETWEEN ... CURRENT ROW` 0 hit；leakage_scan_pass=TRUE on 100% DRAFT |
| **AC-2** | 6 attribute minimum bar 全自動計算 + 寫入 V103 EXTEND 字段 | `SELECT COUNT(*) FROM learning.hypotheses WHERE hypothesis_source_module='M4_AUTO' AND m4_attribute_n IS NULL` = 0 |
| **AC-3** | M4 DRAFT writeback Decision Lease 不繞 5-gate | `SELECT COUNT(*) FROM learning.hypotheses WHERE hypothesis_source_module='M4_AUTO' AND decision_lease_draft_id IS NULL` = 0；audit log 100% match |
| **AC-4** | Cowork hybrid Y1 read-only 不寫 DRAFT | Y1 期間 `SELECT COUNT(*) FROM learning.hypotheses WHERE hypothesis_source_module='OPERATOR' AND created_via='cowork_scheduled_task'` = 0；Y2 啟用後才允許 |
| **AC-5** | Cross-language hypothesis fixture 1e-4 對齊 | `test_m4_cross_language_fixture.py` 全 PASS（Rust polars / Python pandas / SQL window function 三套對 fixture input 結果 max diff < 1e-4） |

### §11.2 額外 2 條 acceptance（governance / process）

| # | Acceptance | 驗收方式 |
|---|---|---|
| **AC-6** | DRAFT promote past `'preregistered'` 100% 經 operator click | `SELECT COUNT(*) FROM learning.hypotheses_status_transition WHERE from_status='preregistered' AND to_status IN ('experimenting','promoted') AND operator_click_evidence IS NULL` = 0 |
| **AC-7** | M11 replay divergence 不寫 M4 DRAFT 表 | `SELECT COUNT(*) FROM learning.hypotheses WHERE created_via='m11_replay_divergence_alert'` = 0；M11 alert 落 `learning.replay_divergence_alert` 不落 `learning.hypotheses` |

---

## §12 IMPL Phase + Open Questions

### §12.1 Sprint 階段對應

| Sprint | 內容 | 估時 | M4 stage |
|---|---|---|---|
| **Sprint 1A-γ DESIGN（本 spec）** | M4 Hypothesis Discovery design + V103 EXTEND 6 column outline + Cowork hybrid section | 12-16 hr | DESIGN only |
| **Sprint 1A-γ 補完** | V103 EXTEND 完整 ALTER DDL（下游 sub-agent）+ ADR-0045（per leakage spec §6.2 建議）+ Linux PG dry-run | 8-12 hr | DDL + governance |
| **Sprint 2-3 Pattern miner stage 1** | Statistical + Temporal pattern；Stage 1-4 end-to-end；不含 clustering | 60-90 hr | IMPL |
| **Sprint 6-7 M9 A/B integration** | M9 worker 拉 m9_ab_test_queue + 跑 paper-stage backtest + 寫 ab_test_outcomes | 30-40 hr | IMPL |
| **Sprint 8 Pattern miner stage 2** | Cross-sectional clustering + regime separation（§2.3.3）+ silhouette 5-fold purged CV | 60-90 hr | IMPL |
| **Y2 Cowork hybrid auto** | LAL Tier 2 Cowork scheduled task 寫 hypothesis（source='OPERATOR'）+ cowork_review_status flow | 20-30 hr | IMPL |

### §12.2 Open Questions（≥3 條，未在 spec 內 finalize）

#### **Open Q1**：Sub-period stability 50/50 split 對於 newer data scarce 場景如何處理？

**問題**：v5.8 §2 M4 適用 25 symbol × 5 timeframe；新 symbol（如新上幣 BUSDT）historical data 可能 < 6 month，無法做 50/50 split。  
**選項**：
- (a) 強制 6-month history minimum：< 6mo data 的 symbol 不允許 hypothesis discovery（保守）
- (b) split ratio 動態：< 6mo 用 30/70 split，6-12mo 用 50/50（彈性）
- (c) symbol-specific override：operator 在 Console 對 newer symbol 設 minimum-history exception（per-symbol gate）

**待決**：Sprint 2-3 IMPL 階段選定；本 spec 不 finalize。

#### **Open Q2**：M4 Pattern miner 跑頻率（cron 模式 vs continuous monitoring）？

**問題**：M4 Stage 1 feature scan 計算成本高（25 symbol × 5 timeframe × multi-feature）；continuous monitoring vs daily/weekly cron 各有 tradeoff。  
**選項**：
- (a) Daily cron（每日 UTC 00:00 跑一次）：成本可控，但 hypothesis discovery 延遲 24h
- (b) Continuous monitoring（每 1h trigger 一次新 batch）：discovery latency 1h，但 LLM/CPU cost 高
- (c) Event-driven（funding rate flip / liquidation cascade trigger 即時跑 event-window pattern）：對 event-based hypothesis 最佳，對 statistical pattern 不適用

**待決**：Sprint 2-3 IMPL 階段定 cron schedule；本 spec 不 finalize。可能採混合（statistical = daily / event-based = event-driven）。

#### **Open Q3**：Y2 Cowork hybrid auto-suggest 升 `'PENDING'` 後 SLA 多長？

**問題**：Cowork 寫 review markdown 至 `cowork_review_status='PENDING'` 後，operator 多久內必須 review？逾時是否自動 'REJECTED'？  
**選項**：
- (a) 無 SLA：operator 自由 review，永久 'PENDING'（簡單但失去推進力）
- (b) 30d SLA：'PENDING' 30d 內 operator 必 review；逾時 auto-'REJECTED'（強制節奏，但可能誤殺 deferred hypothesis）
- (c) 60d SLA + Slack 升級：30d Slack reminder / 60d auto-'REJECTED'（per AMD-2026-05-21-01 §4.5 operator inactivity 60d 邏輯對齊）

**待決**：Y2 啟用前定；本 spec 不 finalize。建議採 (c) 對齊 60d inactivity 模式。

#### **Open Q4**：M4 DRAFT 寫入 leakage_scan_pass=FALSE 時，是否 INSERT 拒絕 vs INSERT with reject flag？

**問題**：Stage 4 寫入時若 §4.3 leakage scan SQL 報 leak_suspected=true，兩種處理方式。  
**選項**：
- (a) INSERT 拒絕：完全不寫表，emit RCA log；DRAFT pool 純淨但失去 leak history
- (b) INSERT with leakage_scan_pass=FALSE：寫表但 status='exploratory'+leak flag；可追蹤 leak history
- (c) Two-path：reject + 同時寫 `learning.hypothesis_leak_rejected_log`（rejection audit ledger）

**待決**：Sprint 2-3 IMPL 階段定；本 spec 不 finalize。建議 (c)：DRAFT 表純淨 + 獨立 leak rejection ledger。

#### **Open Q5**：cross-language fixture 1e-4 對齊在三語言 implementation 差異時如何 reconcile？

**問題**：Rust polars vs Python pandas vs SQL window function 對於 NaN handling / floating point precision / window boundary 邊界可能有微小差異（如 ddof=0 vs ddof=1 std deviation）。  
**選項**：
- (a) 強制三語言 implementation 100% 等價：選定一語言為 reference（如 Python pandas），其他兩語言 implementation 必對齊
- (b) 弱對齊（1e-4 tolerance）：允許微差，但對 DRAFT writeback **指定 single language 為 source of truth**（如全部 M4 DRAFT 由 Python 寫）
- (c) Tolerance 分等級：feature scan / pattern detection 用 1e-4；DRAFT writeback final value 用 1e-6 嚴格對齊

**待決**：Sprint 2-3 IMPL 階段定；本 spec 不 finalize。建議 (b)：Python pandas 為 source of truth，Rust + SQL 是 performance optimization path，不直接寫 DRAFT。

### §12.3 ADR-0045 建議（per leakage spec §6.2）

本 spec 對應 governance authority = ADR-0045（per leakage spec §6.2 建議）。M4 Hypothesis Discovery 全 scope（含 6 attribute minimum bar + leakage protocol + Decision Lease writeback + Cowork hybrid path）由 ADR-0045 統一落 governance。本 spec 不寫 ADR 本檔；待 PA Sprint 1A-γ dispatch 統一收口。

---

## §13 Cross-References

### §13.1 spec 內部

- M4 leakage protocol baseline：`docs/execution_plan/2026-05-21--m4_minimum_bar_and_leakage_protocol.md`（839 行 / Wave 2 land）
- V103 schema spec：`docs/execution_plan/2026-05-21--v103_v104_earn_hypotheses_schema_spec.md`（CR-1 v5.7 follow-up SoT）
- v5.8 主檔 §2 M4：`docs/execution_plan/2026-05-20--execution-plan-v5.8.md` line 153-186

### §13.2 ADR + governance

- ADR-0024-lite：`docs/adr/0024-cowork-subscription-operator-assistant.md`（Cowork operator-assistant 邊界 — §9 hybrid path 引用源）
- AMD-2026-05-21-01：`docs/governance_dev/amendments/2026-05-21--AMD-2026-05-21-01-autonomy-vs-human-final-review.md`（protected scope (a) Stage transition + opt-in scope mapping 引用源）
- ADR-0020：Layer 2 cloud LLM manual-only（M4 不用 L2 Claude API 對應）
- ADR-0034：M1 Decision Lease Tier（M4 DRAFT lease lifecycle 模式參考）
- ADR-0045（待建立）：M4 Hypothesis Discovery 統一 governance authority

### §13.3 skills + memory

- Feature engineering protocol：`srv/.claude/skills/feature-engineering-protocol/SKILL.md`
- Walk-forward validation protocol：`srv/.claude/skills/walk-forward-validation-protocol/SKILL.md`
- Time-series CV protocol：`srv/.claude/skills/time-series-cv-protocol/SKILL.md`
- 16 root principles checklist：`srv/.claude/skills/16-root-principles-checklist/SKILL.md`
- `memory/feedback_indicator_lookahead_bias.md`（2026-04-24 P1-11 F3 RETRACT — rolling shift(1) 強制證據）
- `memory/feedback_v_migration_pg_dry_run.md`（V### Linux PG dry-run mandate）

### §13.4 學術參考

- Harvey, Liu, Zhu (2016) "...and the Cross-Section of Expected Returns"（graveyard 主來源）
- Hou, Xue, Zhang (2020) "Replicating Anomalies"（HLZ 後續 replication 失敗證據）
- Cohen (1988) Statistical Power Analysis（effect size convention）
- Benjamini, Hochberg (1995) FDR baseline
- López de Prado (2018) "Advances in Financial Machine Learning"（purged k-fold + embargo 範式來源）

---

## §14 Sign-off Status

| Agent | Status | 範圍 | Note |
|---|---|---|---|
| **PA recovery sub-agent** | **Drafted** | Spec 全文（§0-§13）| 包含 12 必 section + Cowork hybrid section + V103 EXTEND outline + open Q ≥3 |
| **PA 主會話** | **PENDING** | V103 EXTEND 完整 ALTER DDL（下游 sub-agent 補）+ ADR-0045 起草 + Sprint 1A-γ dispatch | 待主會話收口 |
| **MIT** | **PENDING** | 6 attribute 數學定義對齊（已 leakage spec drafted；本 spec §3 引用未重複）+ Stage 2 pattern detection 演算法選型 | Sprint 2-3 IMPL 前確認 |
| **QC** | **PENDING** | Bonferroni vs FDR 仲裁（per leakage spec §2.2.3）+ effect size threshold 校驗 + replicability_score formula | Sprint 1A-γ dispatch 前 |
| **E4** | **PENDING** | Cross-language 1e-4 fixture test harness（§4.4 `test_m4_cross_language_fixture.py`）+ leakage scan grep 自動化 | E4 regression 階段補 |
| **AI-E** | **PENDING** | M4 Pattern miner stage 1 + stage 2 IMPL 引用本 spec | Sprint 2-3 + Sprint 8 |
| **E3** | **PENDING** | Decision Lease lifecycle integration（GovernanceHub.acquire_lease 對 M4 DRAFT 支援）+ Cowork hybrid Y2 console toggle | Sprint 6-7 + Y2 啟用前 |

---

## §15 Out of Scope（本 spec 不寫）

- IMPL code（M4 Pattern miner Stage 1-4 Python / Rust 實檔；Sprint 2-3 / Sprint 8）
- V103 EXTEND 完整 ALTER DDL 實檔（下游 sub-agent 補；本 §10 outline only）
- V103 本檔修改（V103 spec 本檔不動；CR-1 v5.7 follow-up 主會話統一）
- ADR-0045 實檔（PA Sprint 1A-γ dispatch 統一）
- 6 attribute 數學細節（直引 leakage spec §2；本 spec §3 不重複）
- Rolling shift(1) 三語言 code 範例（直引 leakage spec §3.2-§3.4；本 spec §4 不重複）
- Mac PG empirical dry-run（必 Linux PG，per CLAUDE.md §七 + V055 mandate）
- M9 A/B test 4 cluster exit logic variant 細節（屬 M9 spec scope）
- M6 5λ baseline 數值優化（屬 M6 spec scope）
- M11 replay divergence threshold 細節（屬 M11 spec scope）
- Cowork scheduled task `mcp__scheduled-tasks__*` framework wiring（屬 E3 IMPL scope）

---

**END OF SPEC**
