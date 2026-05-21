# M9 A/B Testing — 4 Variant Cluster Setup / mSPRT 監控 / Winner Promotion SOP

**狀態：** Draft（Sprint 1A-β deliverable；CR-4 M9 spec + M11 divergence flag + Stage 0R/1/2/3/4 path land 後 verify）
**版本：** v0.1（2026-05-21）
**Runbook ID：** RUNBOOK-M9-ABTEST-001
**Module：** M9 A/B Testing Framework（4 variant cluster + mSPRT + Bonferroni + fair execution）
**Severity coverage：** SEV-1 / SEV-2 / SEV-3
**On-call role：** Operator + PM + MIT（MIT 提供統計判讀建議；Strategist / DreamEngine 提供 variant 設計建議；operator 永遠執掌 winner promotion 與 hold 決策）
**Depends on：** CR-4 M9 spec / Stage 0R/1/2/3/4 path / M11 divergence flag / ADR-0008 Decision Lease baseline / ADR-0034 LAL 5-tier（variant promotion 走 LAL 1 路徑）

> **Hands off — operator only**：A/B test winner promotion 與 premature termination 永遠由 Operator 經 Console 親手執行；本 runbook 列的 IPC patch / SQL update **僅供 emergency mitigation**，平常運維走 Console UI。

---

## 1. TL;DR / 用途

M9 A/B testing framework 為 v5.8 §2 設計的「同策略多 variant 並行對比 → 統計驗證 winner → 經 Stage path promote」迴路。設計 4 variant cluster 而非雙 variant：

| Variant | 用途 | hash bucket 範圍 |
|---|---|---|
| **A**（control / baseline） | 既有 production parameter 對照組 | bucket 0-24 (25%) |
| **B**（candidate v1） | 主要對比 variant | bucket 25-49 (25%) |
| **C**（candidate v2 / hyperparam variant） | 次要對比 variant | bucket 50-74 (25%) |
| **D**（aggressive / risk-on variant） | 邊界探索 variant；通常 size cap 0.5x | bucket 75-99 (25%) |

統計引擎：
- **mSPRT**（mixture Sequential Probability Ratio Test）—— 連續監控 p-value，可提早結束（per Robbins 1970 / Howard et al 2021）
- **Bonferroni correction**—— 4 variant 同時 test，閾值除以 3（A 為對照組不算 multiple comparison 分母）
- **Fair execution clause**—— 4 variant 共享同一 IPC submission timing + same lease window；避免一個 variant 因 latency 優勢「贏」

本 runbook 規範 7 類事件：(a) **4 variant cluster test setup**（spec → schema → hash seed → variant kickoff）/ (b) **A/B test launch + variant assignment hash seed verify**（avoid hash skew） / (c) **monitor: mSPRT p-value + Bonferroni**（log-likelihood ratio 走勢 + early stop trigger）/ (d) **winner promotion: variant 走 Stage 0R/1/2/3/4 path**（promote 路徑 + LAL 1 hook） / (e) **fair execution clause enforce**（IPC timing fairness + lease window 一致性）/ (f) **test inconclusive: M11 divergence flag → variant 暫 hold**（divergence > 閾值時 freeze test）/ (g) **test premature termination**（operator manual stop + reason record + 數據 archive）。

---

## 2. Detection / Alarm Symptoms

| Symptom | 來源 | 對應 section |
|---|---|---|
| Console "A/B Tests" tab 顯示新 test pending kickoff | `learning.ab_test_state` | §4 Triage / §5 Setup |
| mSPRT p-value 跨閾值（< 0.0167 after Bonferroni）連續 6h | `learning.ab_test_sprt_log` | §7 monitor / §8 winner promotion |
| 4 variant bucket assignment count diverge（max - min > 5%） | `learning.ab_test_assignment_log` | §6 hash seed verify |
| M11 divergence flag fire on test-active strategy | `learning.m11_divergence_log` | §10 inconclusive hold |
| Variant 之間 IPC submission latency diff > 50ms 持續 1h | `learning.ipc_latency_panel` | §9 fair execution clause |
| Operator 收到 Slack alert: "A/B test approaching auto-stop threshold" | Slack `#ops-abtest` | §8 winner promotion review |
| Test 跑超過 max_duration（spec 設 30d）但 inconclusive | `learning.ab_test_state` | §11 premature termination |

---

## 3. Severity Matrix

| Severity | Impact | Response time | Escalation path |
|---|---|---|---|
| **SEV-1** | Hash seed skew 致 variant assignment 嚴重不均（任一 variant bucket < 15% 或 > 35%）；或 fair execution clause 失效（任一 variant 有 IPC timing 系統性優勢）；或 winner promotion 被誤 auto-promoted（未經 operator click 走 Stage path） | < 30 min | Operator 立刻 §11 emergency stop test + 暫不 promote 任何 variant；PM 1h 內加入；MIT 4h 內 review；24h postmortem |
| **SEV-2** | mSPRT p-value 跨閾值但未經 operator 確認 Bonferroni adjustment；或 M11 divergence flag fire 但 test 仍 active；或 variant D（aggressive）造成 portfolio drawdown > 2% | < 2h | Operator 透過 Console hold test → 等 MIT 統計核驗；PM 4h 內加入 |
| **SEV-3** | mSPRT p-value 在閾值附近抖動（hysteresis 範圍內）；或單一 variant assignment count 暫時偏離但 < 5%；或 test duration 接近 max_duration 但仍 monitoring | < 8h | On-call PM 回應 Slack；確認自然收斂 vs 需 §11 manual stop |

> **判定 SEV-1 還是 SEV-2 的關鍵**：是否有「未經 operator 確認的自動 state mutation」。任一 variant 被自動 promote / auto-stop 而未走 Console UI = SEV-1；只是統計指標跨閾值但 state 未變 = SEV-2。

---

## 4. Initial Triage Checklist（5-10 步）

```bash
# Step 1 — 確認當前所有 active test 全景
psql -h trade-core -U openclaw -d openclaw -c "
SELECT test_id, strategy_name, test_state, started_at,
       payload->'variant_a' AS variant_a,
       payload->'variant_b' AS variant_b,
       payload->'variant_c' AS variant_c,
       payload->'variant_d' AS variant_d
FROM learning.ab_test_state
WHERE test_state IN ('running', 'paused', 'pending_winner_review')
ORDER BY started_at DESC;"
# expected: 每 test 4 variant 全配置；test_state 合法
# decision branch:
#   - test_state='pending_winner_review' → §8 winner promotion review
#   - test_state='paused' → 找 paused 原因（§10 inconclusive 或 §11 premature）
```

```bash
# Step 2 — 確認 variant assignment 是否均衡（hash skew check）
psql -h trade-core -U openclaw -d openclaw -c "
SELECT test_id, variant, COUNT(*) AS assignment_count,
       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (PARTITION BY test_id), 2) AS pct
FROM learning.ab_test_assignment_log
WHERE assigned_at > NOW() - INTERVAL '24 hours'
GROUP BY test_id, variant
ORDER BY test_id, variant;"
# expected: 每 variant pct 在 22.5%-27.5% 範圍（25% +/- 2.5%）
# decision branch:
#   - 任一 variant pct < 15% 或 > 35% → SEV-1（§6 hash seed verify）
#   - 任一 variant pct 偏 22.5-27.5 外但 < 5% 偏離 → SEV-3（等 sample size 增加自然收斂）
```

```bash
# Step 3 — 確認 mSPRT 統計引擎健康
psql -h trade-core -U openclaw -d openclaw -c "
SELECT test_id, variant_pair, current_log_likelihood_ratio,
       current_p_value, bonferroni_adjusted_threshold,
       sample_size_a, sample_size_b, last_updated_at
FROM learning.ab_test_sprt_log
WHERE last_updated_at > NOW() - INTERVAL '1 hour'
ORDER BY test_id, variant_pair;"
# expected: log_likelihood_ratio 每小時更新；p_value 與 Bonferroni 閾值對比合理
# decision branch:
#   - p_value < bonferroni_adjusted_threshold 持續 > 6h → §8 winner promotion review
#   - log_likelihood_ratio NaN / NULL → §7 mSPRT engine 炸（SEV-2）
```

```bash
# Step 4 — 確認 fair execution clause（IPC timing fairness）
psql -h trade-core -U openclaw -d openclaw -c "
SELECT test_id, variant,
       AVG(ipc_submission_latency_ms) AS avg_latency,
       STDDEV(ipc_submission_latency_ms) AS stddev_latency,
       MAX(ipc_submission_latency_ms) AS max_latency
FROM learning.ipc_latency_panel
WHERE test_id IS NOT NULL
  AND submitted_at > NOW() - INTERVAL '1 hour'
GROUP BY test_id, variant
ORDER BY test_id, variant;"
# decision branch:
#   - 任一 variant avg_latency 與 group avg diff > 50ms → §9 fair execution clause 違反（SEV-1）
#   - max_latency 偶爾偏離但 avg ok → 預期 noise，繼續監控
```

```bash
# Step 5 — 確認 M11 divergence flag 是否影響 test
psql -h trade-core -U openclaw -d openclaw -c "
SELECT d.divergence_score, d.fired_at,
       t.test_id, t.test_state
FROM learning.m11_divergence_log d
JOIN learning.ab_test_state t ON t.strategy_name = d.affected_strategy
WHERE d.fired_at > NOW() - INTERVAL '4 hours'
  AND t.test_state = 'running';"
# decision branch:
#   - divergence_score > 0.4 且 test 仍 running → §10 inconclusive hold
#   - 0 row → cascade 健康
```

```bash
# Step 6 — 確認 variant D（aggressive）對 portfolio drawdown 影響
psql -h trade-core -U openclaw -d openclaw -c "
SELECT strategy_name, variant, SUM(realized_pnl) AS variant_pnl,
       MIN(running_drawdown) AS max_drawdown
FROM trading.fills
WHERE ab_test_variant = 'D'
  AND filled_at > NOW() - INTERVAL '24 hours'
GROUP BY strategy_name, variant;"
# decision branch:
#   - 任一 variant D max_drawdown < -2% portfolio → SEV-2（§11 manual stop variant D only）
#   - 預期 drawdown 因 size cap 0.5x 有限制
```

```bash
# Step 7 — Console banner + Slack notification 健康
curl -sS http://localhost:8001/api/v1/notify/health | jq '.slack_ok, .console_banner_ok'
# 任一 false → SEV-2（test 走勢 operator 不會收到通知）
# 處置：先 §10 hold 所有 active test 直到通知路徑復原
```

```bash
# Step 8 —（only if SEV-1）emergency stop all test
curl -sS -X POST -H "Cookie: $OPERATOR_SESSION_COOKIE" \
  http://localhost:8001/api/v1/abtest/emergency_stop_all
# expected: 200 OK + body 含 stopped_test_count + 各 variant 最後 sample size
# 立刻 §12 escalate；PM 1h 內加入；MIT 4h 內統計核驗
```

---

## 5. Mitigation — 4 Variant Cluster Test Setup

### 5.1 Pre-setup 必填項（spec → schema）

```
1. CR-4 M9 spec 必含：
   (a) hypothesis 描述（A vs B vs C vs D 各自代表什麼）
   (b) 4 variant 參數定義（每 variant 對應 parameter delta vs A）
   (c) primary metric（如 net PnL bps / 7d rolling Sharpe / fill rate）
   (d) min sample size（per Bonferroni 4-arm test 統計力計算）
   (e) max test duration（default 30d）
   (f) auto-stop threshold（p < 0.0167 after Bonferroni 持續 6h）
   (g) variant D size cap（default 0.5x 避免 risk explosion）

2. learning.ab_test_state 寫入 row：
   INSERT INTO learning.ab_test_state (test_id, strategy_name, test_state='pending_kickoff',
                                         payload=jsonb_build_object(
                                           'variant_a', ...,
                                           'variant_b', ...,
                                           'variant_c', ...,
                                           'variant_d', ...,
                                           'hash_seed', <random_uuid>,
                                           'primary_metric', ...,
                                           'min_sample_size', ...,
                                           'max_duration_days', 30,
                                           'auto_stop_threshold_p', 0.0167
                                         ));
```

### 5.2 Kickoff SOP（Console UI）

```
1. Operator 開 Console → "A/B Tests" tab → "New Test" button
2. 填表單（spec 已寫入 schema 則自動帶入）
3. 確認 hash_seed（系統自動生成 random UUID）
4. 2FA confirm
5. Console 觸發：
   UPDATE learning.ab_test_state SET test_state='running', started_at=NOW()
   WHERE test_id=...;
6. Strategy executor 開始按 hash bucket 分流 fill 到 4 variant
7. Slack `#ops-abtest` notification「test_id <X> kickoff; 4 variants live」
```

### 5.3 反模式

- (a) 跳過 spec 直接 INSERT test state → 違反 audit chain
- (b) hash_seed 使用 strategy_name hash → 可預測偏差；必用 random UUID
- (c) variant D size cap > 0.5x → 違反 risk envelope（除非 spec 明示且 PM approve）

---

## 6. A/B Test Launch + Variant Assignment Hash Seed Verify

### 6.1 Hash seed 設計（避免 hash skew）

```
variant_bucket = hash(test_id || hash_seed || symbol || timestamp_minute) % 100
variant = 'A' if bucket < 25
        'B' if bucket < 50
        'C' if bucket < 75
        'D' if bucket < 100
```

**為什麼 timestamp_minute 而非單純 symbol**：避免某些 symbol 永遠分到同一 variant（如 BTCUSDT 永遠去 B）；同 symbol 不同分鐘可進不同 variant，sample size 自然均衡。

### 6.2 Skew detection thresholds

| Sample size 範圍 | 容忍 skew 範圍 | 處置 |
|---|---|---|
| < 1000 | 任一 variant 20-30% | 預期 early-stage noise，繼續監控 |
| 1000-10000 | 任一 variant 22-28% | 自然收斂 window，繼續監控 |
| > 10000 | 任一 variant 23-27% | 任何 skew > 2% = hash seed bug，§6.3 fix |

### 6.3 Hash skew fix SOP

```bash
# Step 1 — 確認 hash function 實作正確（不能有 modulo bias）
psql -h trade-core -U openclaw -d openclaw -c "
SELECT variant_bucket, COUNT(*) FROM learning.ab_test_assignment_log
WHERE test_id=<problem_test_id>
GROUP BY variant_bucket ORDER BY variant_bucket;"
# 期望：100 個 bucket 各自 ~1% sample；若某 bucket 偏 2% 以上 = hash function 炸

# Step 2 —（emergency mitigation）暫停該 test
curl -sS -X POST -H "Cookie: $OPERATOR_SESSION_COOKIE" \
  -d '{"test_id":"<id>","reason":"hash_skew"}' \
  http://localhost:8001/api/v1/abtest/pause

# Step 3 — 走 normal channel：spec follow-up + E1 fix hash function + 重啟 test（新 hash_seed）
```

---

## 7. Monitor — mSPRT P-value + Bonferroni Correction

### 7.1 mSPRT 統計引擎理論

mSPRT（mixture Sequential Probability Ratio Test）允許**連續監控** p-value 而不需 Bonferroni-style penalty for peeking。基本框架：

```
log_likelihood_ratio(LLR) = sum over each new sample of:
  log( p_alt(sample) / p_null(sample) )

stop and reject null if LLR > log(1/alpha)
stop and accept null if LLR < log(beta/(1-alpha))
continue otherwise
```

實作要點：
- mixture prior 須在 spec 階段定（per CR-4 M9 spec），避免 post-hoc tuning
- 每筆新 fill 更新 LLR，每 5 min batch 寫 `learning.ab_test_sprt_log`
- p-value 由 LLR 反推（per Howard et al 2021 anytime-valid p-value formula）

### 7.2 Bonferroni correction for 4 variant cluster

```
原始 alpha = 0.05
4 variant 對 control A → 3 個 pairwise comparison（A-B, A-C, A-D）
Bonferroni adjusted alpha = 0.05 / 3 = 0.0167

stop criteria:
  p_value < 0.0167 持續 6h → auto-stop trigger + operator review
  p_value > 0.95 持續 6h → variant 確認 inferior → operator review
```

### 7.3 Monitor cadence

- 每 5 min：mSPRT LLR update 寫 `learning.ab_test_sprt_log`
- 每 1h：Console banner refresh + Slack `#ops-abtest` daily summary
- 每 6h：如 p_value 持續跨閾值 → Slack alert 「approaching auto-stop」
- 每 24h：MIT daily review（人工核 p-value 走勢 + 確認 mSPRT 健康）

### 7.4 mSPRT engine 炸 mitigation

**症狀**：`current_log_likelihood_ratio` 為 NaN / NULL 持續 > 30 min。

**Mitigation**：
- 暫不接受該 test 的 auto-stop trigger（避免假 p-value 推 winner）
- MIT 排查 LLR 計算（可能 sample variance 為 0 / overflow）
- 修復前 test 繼續跑（不阻塞 sample collection）；修復後 LLR 從歷史 sample 重算

---

## 8. Winner Promotion — Variant 走 Stage 0R/1/2/3/4 Path

### 8.1 Promotion 必經 path

```
Winner candidate (Console "Promote Winner" button click)
        ↓
Stage 0R（replay-only preflight）
  - 對 candidate variant parameter 走 historical replay
  - 確認 no live state mutation
  - duration: 24h sample replay
        ↓
Stage 1（Demo-only forward test）
  - candidate variant 在 demo endpoint 跑 7d
  - 確認 demo PnL 與 A/B test 期間趨勢一致
        ↓
Stage 2（Live shadow）
  - candidate variant 在 live endpoint 走 shadow（不下單）
  - 確認 lease emit / sign 路徑健康
  - duration: 7d
        ↓
Stage 3（Live small-size）
  - candidate variant 在 live 用 0.3x 正常 size 跑 14d
  - 監控實際 PnL vs A/B test 預測
        ↓
Stage 4（Live full size）
  - 走 LAL 1（per ADR-0034）auto-approve 路徑
  - 完成 30d stable + per-strategy yes-rate > 80% 後 production
```

### 8.2 Winner promotion SOP（Console UI）

```
1. Operator 收到 Slack「test <X> auto-stop threshold reached; winner candidate: variant B」
2. Open Console → A/B Tests tab → 點 test_id → "Review winner"
3. Review screen 顯示：
   - 4 variant 最終 sample size + PnL + Sharpe + win rate
   - mSPRT LLR 完整時間序列圖
   - Bonferroni adjusted p-value
   - fair execution clause 違反 count（期望 0）
   - M11 divergence flag fire count
4. Operator 必填 promotion attestation：
   (a)「我確認 mSPRT 統計顯著且 Bonferroni adjusted」
   (b)「我確認 fair execution clause 未違反」
   (c)「我接受 winner 走 Stage 0R→1→2→3→4 完整 path（不可跳階）」
5. 2FA confirm
6. Console 寫入：
   UPDATE learning.ab_test_state SET test_state='winner_promoted',
                                       winner_variant='B', promoted_at=NOW();
   INSERT INTO learning.stage_progression_log (...);
7. Slack `#ops-abtest` notification「winner B entering Stage 0R」
```

### 8.3 LAL 1 auto-promote hook（Stage 4）

Per ADR-0034 LAL 1（intra-strategy reparam）：

- Stage 0R/1/2/3 永遠 operator manual click promote
- Stage 4 promotion（最終 production）可走 LAL 1 auto-approve **如果** 6 hard gate 全 pass + per-strategy yes-rate > 80% + 30d stable
- LAL 1 auto-promote 仍需走 Console banner notification + 24h undo（per M1 LAL runbook §7）

---

## 9. Fair Execution Clause Enforce

### 9.1 為什麼需要

A/B test 公平性的最大威脅不是 hash skew，而是 **execution layer latency 差異**：

- 如 variant B 因 IPC submission path 較短（如 less validation hop）→ B 系統性快 50ms → B fill rate / slippage 系統性優於 A → 統計看起來 B 贏，實則 latency artifact

### 9.2 Fair execution clause spec

per CR-4 M9 spec：

- 所有 variant 必走**同一** IPC submission stack（無 variant-specific fast path）
- 所有 variant 必使用**同一** lease window（emit / sign / submit 三步同一時序）
- 所有 variant 必經**同一** Guardian 審批路徑
- IPC submission latency stddev 跨 variant 需 < 10ms（per fairness threshold）

### 9.3 Violation detection + mitigation

**Detection**：§4 Step 4 query 顯示任一 variant avg_latency 與 group avg diff > 50ms。

**Mitigation**：
- 立刻 §11 pause test（避免繼續 collect biased sample）
- E1 排查 latency 差異來源（IPC path / validator / DB query）
- 修復後 archive 偏差 sample（不計入統計）+ 重啟 test（新 test_id）

### 9.4 反模式

- (a) 為某 variant 加 "performance optimization" 快路徑 → 違反 fairness
- (b) 不同 variant 用不同 Guardian config → 違反 fairness
- (c) Variant D（aggressive）跳過 risk check → 違反 fairness 且違反 §四 hard boundary

---

## 10. Test Inconclusive — M11 Divergence Flag → Variant 暫 Hold

### 10.1 M11 divergence 對 A/B test 的影響

A/B test 期間如 M11 portfolio rebalance signal 與 test 進行中策略**對立**（如 test 想 promote 一個 risk-on variant，但 M11 同期 risk-off rebalance），則：

- variant 之間的 PnL 對比受 portfolio context 干擾
- mSPRT LLR 不再純粹反映 variant 內在 alpha 差異
- 強行 promote 可能在不同 portfolio context 下表現相反

### 10.2 Hold SOP

**Detection**：§4 Step 5 query 顯示 `divergence_score > 0.4` 在 test-active strategy 上。

**Hold action**：
```bash
# Pause test 但保留 sample（不 reset）
curl -sS -X POST -H "Cookie: $OPERATOR_SESSION_COOKIE" \
  -d '{"test_id":"<id>","reason":"m11_divergence","hold_until":"divergence_resolved"}' \
  http://localhost:8001/api/v1/abtest/hold
```

**Resume condition**：
- M11 divergence_score 連續 24h < 0.2 → 自動 resume
- 或 operator 經 Console manual resume + 2FA + reason

### 10.3 Hold 期間的 sample 處理

- Hold 前 collect 的 sample 保留，計入最終統計
- Hold 期間發生的 fill 不分流到 variant（全走 variant A / control）
- Hold 解除後新 fill 繼續按 hash bucket 分流

---

## 11. Test Premature Termination — Operator Manual Stop

### 11.1 觸發條件（合法 premature stop reason）

| Reason | 描述 | Sample 處理 |
|---|---|---|
| `hash_skew` | §6.3 hash function bug | Archive sample；新 test_id 重啟 |
| `fairness_violation` | §9.3 IPC latency 差異 | Archive sample；fix latency 後重啟 |
| `risk_exceeded` | Variant D drawdown > 2% | 保留 sample；停 test；MIT 統計判讀 |
| `m11_persistent_divergence` | §10 hold 超 7d 仍未恢復 | 保留 sample；停 test；下次 test 避開類似 macro context |
| `max_duration_inconclusive` | Test 跑滿 30d 但 p-value 未跨閾值 | 保留 sample；停 test；視為「無顯著差異」 |
| `operator_strategic_change` | 策略重新設計 / spec 變更 | 保留 sample；停 test；下次 test 用新 spec |

### 11.2 Premature stop SOP（Console UI）

```
1. Operator 開 Console → A/B Tests tab → 點 test_id → "Stop Test"
2. 必填 reason category（dropdown）+ 自由文本詳細說明
3. 必填 sample disposition（archive / preserve）
4. 2FA confirm
5. Console 寫入：
   UPDATE learning.ab_test_state SET test_state='stopped',
                                       stopped_at=NOW(),
                                       stop_reason=<category>,
                                       stop_reason_detail=<text>;
6. 同步 archive 或 preserve sample（per disposition）：
   - archive: INSERT INTO learning.ab_test_archived_samples ... + DELETE from active
   - preserve: keep in learning.ab_test_assignment_log 標記 final=true
7. Slack `#ops-abtest` notification「test <X> stopped; reason: <category>」
```

### 11.3 反模式

- (a) 直接 DELETE FROM learning.ab_test_state → 違反 audit chain
- (b) 跳過 reason 填 → 違反 audit；future test design 失去前車之鑑
- (c) Strategist / Cowork 代執行 stop → premature stop 是 operator-only path

---

## 12. Escalation

**Trigger**：§4 任一 Step 顯示 SEV-1；或 §6 hash skew 確認；或 §9 fairness violation；或 winner promotion 被誤 auto。

**Escalation channel**：
- SEV-1：Slack `#ops-critical` + 電話 PM + email Operator + email MIT
- SEV-2：Slack `#ops-abtest` + email PM + email MIT
- SEV-3：Slack `#ops-info`

**Attach evidence**：
- `learning.ab_test_state` 完整 row
- `learning.ab_test_assignment_log` 24h sample（per variant count + pct）
- `learning.ab_test_sprt_log` 完整 LLR 時間序列
- `learning.ipc_latency_panel` 24h variant latency 對比
- `learning.m11_divergence_log` 4h 內 fire 記錄
- `trading.fills` test 期間 fills（per variant aggregate）
- Console screenshot（test detail + winner review screen）

**Post-escalation action**：
- PM 1h 內派 MIT review 統計判讀
- 24h 內補 postmortem `docs/audits/<date>--abtest_<incident>_postmortem.md`

---

## 13. Post-Incident

### Postmortem template

```markdown
# A/B Test Incident Postmortem — <YYYY-MM-DD>

## TL;DR
- Severity: SEV-?
- Test ID: <id>
- Strategy: <name>
- 4 variant final sample size: A=?, B=?, C=?, D=?
- Stop reason category: <category>
- Operator action(s) taken: <list>

## Timeline (UTC)
- T+0: <symptom detected>
- T+N: <step taken>

## Root cause
- Hash skew / fairness violation / mSPRT engine bug / spec gap?
- Bonferroni adjusted threshold 是否合理？
- M11 divergence 是否預警但被忽略？
- Variant D size cap 是否需要更嚴？

## Mitigation
- 即時 mitigation (§5/§9/§10/§11 對應)
- 永久 mitigation（CR-4 M9 spec / mSPRT engine / hash function 更新）

## Action items
- [ ] CR-4 M9 spec 補 column / constraint
- [ ] mSPRT engine fix
- [ ] hash function audit
- [ ] runbook §X 更新

## 12-week trend tracking entry
- 加入 monthly A/B test trend dashboard tracking entry（link）
```

### 12-week trend tracking entry

PM Monthly Operator Review Wizard 含 A/B test section：
- 4 週 / 12 週 test count + 各 reason category 分布
- winner promotion → Stage 0R/1/2/3/4 各階段 pass rate
- mSPRT auto-stop trigger count + operator approval rate
- M11 divergence hold count + average hold duration
- fair execution violation count + root cause 分布
- variant D drawdown > 2% 觸發 count

Dashboard：`http://localhost:8001/console#governance/abtest` → "12w trend" tab（pending Sprint 1A-ε A3 land）。

---

## 14. Cross-References

- **CR-4 M9 spec**（pending）：`docs/execution_plan/specs/2026-05-21--m9-ab-testing-spec.md`
- **mSPRT 統計理論**：Robbins 1970「Statistical methods related to the law of the iterated logarithm」+ Howard et al 2021「Time-uniform, nonparametric, nonasymptotic confidence sequences」
- **Stage 0R/1/2/3/4 path spec**：`docs/architecture/stage_progression_path.md`（pending）
- **M11 divergence flag**：`docs/execution_plan/specs/2026-05-21--m11-divergence-flag.md`（pending）
- **ADR-0008**：`docs/adr/0008-decision-lease-state-machine.md`（variant fill 仍走 Decision Lease）
- **ADR-0034**：`docs/adr/0034-decision-lease-layered-approval-lal.md`（Stage 4 promotion 走 LAL 1 hook）
- **M1 LAL runbook**：`docs/runbooks/2026-05-21--m1_lal_operator_runbook.md`（LAL 1 auto-approve + 24h undo）
- **M2 overlay runbook**：`docs/runbooks/2026-05-21--m2_overlay_state_runbook.md`（M11 divergence detection chain）
- **v5.8 §2 M9**：`docs/execution_plan/2026-05-20--execution-plan-v5.8.md`（module 來源）
- **Metric dashboard**：`http://localhost:8001/console#governance/abtest`（pending Sprint 1A-ε）
- **Healthcheck script**：`helper_scripts/db/passive_wait_healthcheck.py --check abtest_sprt_engine`（pending）
- **CLAUDE.md hard boundaries**：§四「ML / DreamEngine / ExecutorAgent / StrategistAgent 不可繞 GovernanceHub + Decision Lease」（A/B test variant 仍受 boundary 限制）+ §二 原則 12「系統行為應由 evidence 演進，不是 anecdotes」（mSPRT 統計顯著為 evidence 基準）

---

## 15. Version History

| 版次 | 日期 | 修訂者 | 摘要 |
|---|---|---|---|
| **v0.1** | 2026-05-21 | TW | Sprint 1A-β deliverable draft；4 variant cluster setup + mSPRT + Bonferroni + Stage 0R/1/2/3/4 promotion path + fair execution clause + M11 divergence hold + 6 reason category premature termination |

---

*OpenClaw / Arcane Equilibrium Runbook — M9 A/B Testing 4 Variant Cluster / mSPRT / Winner Promotion SOP (Draft — CR-4 M9 spec + M11 divergence flag + Stage 0R/1/2/3/4 path land 後 v1 promote)*
