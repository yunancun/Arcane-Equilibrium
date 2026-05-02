# REF-19 — Reality-Calibrated Fast Replay 治理契約（中文版）

**日期：** 2026-05-02
**狀態：** Draft 治理契約；PM / operator 接受此邊界前，不得開始實作。
**Owner：** PM
**英文版：** `docs/references/2026-05-02--reality_calibrated_fast_replay_governance.md`
**關聯：** DOC-01 §5.3 / §5.7 / §5.8 / §5.10、REF-03、REF-04、REF-05、V031、V032、V034

---

## 1. 目的

Reality-Calibrated Fast Replay 是 OpenClaw 新增的研究與開發平面。
它的任務是把歷史行情實驗壓縮到分鐘級，同時誠實標出「歷史回放」與「真實交易所執行」之間的差距。

Reality-Calibrated Fast Replay 不替代 demo、LiveDemo、GovernanceHub、Decision Lease 或 live gates。
它是一個實驗環境，用來幫 operator 和 agents 快速淘汰壞參數，並挑出少量值得進入 bounded demo 驗證的候選。

Reality-Calibrated Fast Replay 可以調用 MLDE、DreamEngine、OpportunityTracker、LinUCB / ML shadow components。
但它不得把這些 component 重新定義成 replay-only 工具。
ML / Dream 的主要使命仍然是：Agent 自我學習、策略修復、以及受邊界約束的策略 / 風控參數演進。

---

## 2. 不可談判邊界

1. Replay 是研究平面，永遠不得提交 live 訂單。
2. Replay 輸出默認是 advisory，除非經現有治理流程明確提升。
3. ML / Dream 輸出不是執行命令。
4. synthetic 或 calibrated replay rows 不得在缺少明確 source tag 的情況下混入 real fill labels。
5. `learning.mlde_edge_training_rows` 保持 real-outcome training view，除非未來 migration 新增明確分離的 replay-labeled view。
6. 由 replay-derived recommendation 觸發的 demo 參數變更，必須經現有 MLDE demo applier contract 保持 bounded、audited、reversible。
7. live / live_demo 參數變更必須經 GovernanceHub review、Decision Lease 和現有 live authorization gates。
8. Replay 不得削弱 H0、Guardian、risk config、exchange disaster protection 或 account survival rules。
9. Replay 必須報告不確定性；單一點估計不足以作為決策依據。
10. 每一次 replay 結果都必須可由 manifest 重建。

---

## 3. 系統角色邊界

| Component | 職責 | 禁止事項 |
|---|---|---|
| Reality-Calibrated Replay Orchestrator | 建立 experiment manifest、載入歷史市場資料、運行 Rust 同源 replay、調用 execution calibration 和 advisory producers、寫報告 | 直接修改 live / demo 參數；變成策略權威 |
| Rust `TickPipeline` | 從歷史事件重新計算 indicators、signals、scanner context、intents、risk / verdict 行為 | 未經版本化就加入 replay-only 策略特殊行為 |
| Execution Simulator | 估計 maker fills、taker slippage、fees、latency、timeout、reject probability | 宣稱 simulated fills 是 real fills |
| MLDE / ML Shadow | 對候選做 rank / veto，估計 expected post-fee edge 和不確定性 | 變成 replay-only；繞過 advisory / governance tables |
| DreamEngine | 在 replay windows 上探索參數假設並產生 parameter proposals | 直接套用參數；變成一般 backtest engine |
| OpportunityTracker | 從 skipped / rejected opportunities 估計 regret / dodged-loss | 沒有 outcome evidence 時，把 gate rejection count 當成 regret |
| Demo Applier | 透過 Rust IPC 套用 bounded demo-only changes，並寫 audit rows | 套用 live / live_demo changes |
| GovernanceHub | Review live candidates，執行 lease / governance 邊界 | 把 replay metrics 視為足夠 live approval |
| Operator | 接受治理變更並批准 live-boundary changes | 只用 replay report 作為 live release evidence |

---

## 4. 資料來源分層

Replay 的可信度取決於市場資料等級。每份報告都必須標明使用了哪個 tier。

| Tier | Source | 預期用途 | 可信度 |
|---|---|---|---|
| S0 | 真實 demo / live_demo fills、orders、verdicts、snapshots | Calibration 和 validation labels | 對已觀察行為最高 |
| S1 | 本地錄製 L1 / L50 orderbook + trades + ticker / funding / OI | 未來高擬真 maker simulation | recorder 穩定後高 |
| S2 | Bybit public klines、trades、funding、OI | 低成本歷史 replay 和 signal sweeps | 中 |
| S3 | OHLC-derived synthetic ticks | 僅策略 signal smoke tests | 對 execution 低 |
| S4 | 經批准的付費 historical L2 data | 深度 maker queue / backfill calibration | 高，但受成本 gate 約束 |

默認成本策略：先用 S0 + S2，立刻開始累積 S1；S4 需要 operator 批准具體 paid-data scope 後才可使用。

---

## 5. 必需 Experiment Manifest

每一次 replay run 都必須有 manifest。Manifest 是可重建性契約。

必需欄位：

```yaml
schema_version: replay_manifest_v1
experiment_id: <stable id>
created_at: <UTC timestamp>
operator_or_agent: <actor>
git_sha: <repo sha>
engine_binary_sha: <if available>
strategy_config_sha256: <hash>
risk_config_sha256: <hash>
market_data:
  tier: S0|S1|S2|S3|S4
  source: bybit_public|local_recorded|paid_l2|synthetic
  symbols: [...]
  start_ts: <UTC>
  end_ts: <UTC>
  timeframe_or_tick: <details>
execution_model:
  version: <model version>
  calibrated_from_start_ts: <UTC>
  calibrated_from_end_ts: <UTC>
  source_modes: [demo, live_demo]
candidate_params:
  strategy_params: <hash or inline patch>
  risk_params: <hash or inline patch>
output_policy:
  write_shadow_recommendations: true|false
  allow_demo_candidate: true|false
  allow_live_candidate: false
```

沒有 manifest 的 replay 結果，不得用於 MLDE recommendation、demo patching 或 governance review。

---

## 6. Source Tagging Contract

Replay 產生的所有 rows 和 reports 都必須帶 source tags。

必需 source tags：

| Tag | 含義 |
|---|---|
| `real_fill` | 來自交易所或 runtime DB 的真實 demo / live_demo / live fill |
| `calibrated_replay` | 由「從 real fills 校準過的 execution model」產生的 simulated fill |
| `synthetic_replay` | 從 OHLC 或其他 synthetic reconstruction 產生的 simulated fill / tick |
| `counterfactual_replay` | 以真實觀測 trade 為 anchor 重新計算的 outcome |
| `dream_parameter_proposal` | DreamEngine advisory parameter hypothesis |
| `ml_shadow_rank` | MLDE rank recommendation |
| `ml_shadow_veto` | MLDE veto recommendation |

Reports 必須包含 source mix table。任何混合不同 source 的 aggregate，都必須顯式暴露混合比例。

---

## 7. Execution Calibration Contract

Execution model 與 strategy replay 是分離的。Execution model 的任務是估計交易所現實，而不是假設 paper 立即成交。

最少模型輸出：

1. `maker_fill_probability`
2. `maker_timeout_probability`
3. `maker_expected_latency_ms`
4. `maker_adverse_selection_bps`
5. `taker_slippage_q10_bps`
6. `taker_slippage_q50_bps`
7. `taker_slippage_q90_bps`
8. `reject_probability`
9. `fee_rate_maker`
10. `fee_rate_taker`

Calibration features 在可用時應包含：

- symbol
- strategy
- side
- order type
- liquidity role
- maker offset bps
- maker timeout ms
- spread bps
- turnover / volume
- volatility / ATR
- funding rate
- open interest
- scanner regime / route mode
- time of day
- recent reject / timeout state

Calibration acceptance：

- 模型必須發布 sample count 和 calibration window。
- low-sample cells 必須 shrink 或標記 insufficient。
- Reports 必須顯示 calibrated / pessimistic / optimistic outcomes。
- calibration stale 時，replay 可以跑，但不得產生 actionable recommendations。

---

## 8. MLDE 和 DreamEngine 使用邊界

Reality-Calibrated Fast Replay 可以用三種方式調用 MLDE 和 DreamEngine。

### 8.1 ML Execution Calibration

ML 可以從 S0 real fills / orders 訓練或更新 execution-reality estimators。
這些 estimators 用於 replay simulation 和 uncertainty report。

這不改變 MLDE 的主要角色。同一批 calibration outputs 也可以服務 live agent self-awareness、cost-edge analysis，以及未來策略 / 風控調參。

### 8.2 Dream Parameter Exploration

DreamEngine 可以在 replay windows 上做 parameter exploration。它應該產生 parameter proposals，而不是 approvals。

DreamEngine outputs 必須保持與 general advisory contract 兼容：

- `source = dream_engine`
- `recommendation_type = parameter_proposal`
- `expected_net_bps`
- `confidence`
- `sample_count`
- `payload.policy = read_only_parameter_proposal`
- 若來源是 replay，必須帶 `payload.replay_experiment_id`

DreamEngine 必須保持 Agent general self-learning component 的身份。Replay 只是其中一種 experiment environment，不是它的唯一用途。

### 8.3 MLDE Rank / Veto

MLDE 可以對 replay-generated candidates 做 rank 或 veto。必須包含：

- expected post-fee edge
- q10 或 pessimistic downside
- confidence
- sample count
- data source tier
- attribution quality
- calibration freshness

MLDE recommendations 仍為 advisory，除非被現有 demo applier 或 GovernanceHub review flow 消費。

---

## 9. Report Acceptance Metrics

Replay report 至少必須包含：

| Metric | Required |
|---|---|
| gross PnL / bps | Yes |
| net bps after fee | Yes |
| q10 / q50 / q90 net bps | Yes |
| max drawdown | Yes |
| maker fill rate | maker strategies 必須 |
| maker timeout rate | maker strategies 必須 |
| taker slippage distribution | market close paths 必須 |
| reject rate | Yes |
| trade count / sample count | Yes |
| source mix | Yes |
| calibration model version | Yes |
| calibration freshness | Yes |
| attribution-chain quality | Yes |
| regime breakdown | Yes |
| symbol breakdown | Yes |
| pass / defer / reject verdict | Yes |

任何 promotion-oriented report 都必須列出每個 verdict 的理由。

---

## 10. Candidate Verdict Rules

Replay 只能產生以下 verdict：

| Verdict | 含義 |
|---|---|
| `reject` | candidate 比 baseline 更差，或未通過 safety / data gates |
| `defer_data` | sample 不足、calibration stale、或 attribution 弱 |
| `defer_reality` | signal 看起來可以，但 execution model uncertainty 太高 |
| `demo_candidate` | candidate 可進 bounded demo A/B |
| `live_candidate_research_only` | candidate 可寫入 GovernanceHub review，但不可 auto-apply |

Replay 永遠不得產生 `live_approved`。

最小 `demo_candidate` gates：

1. calibrated q50 net bps after fee > 0
2. pessimistic q10 未突破配置的 downside threshold
3. maker timeout / reject rates 未超閾值惡化
4. source tier 是 S0 / S1 / S2，不是 S3-only
5. calibration 足夠新鮮
6. attribution-chain quality 高於配置下限
7. parameter delta 在 demo applier bounds 內

---

## 11. Storage and Table Separation

初始實作應盡量避免 schema churn，但任何持久化 replay result 都必須與 real outcomes 可分離。

允許 sinks：

- `docs/CCAgentWorkSpace/PM/workspace/reports/` 下的 local JSON / Markdown report
- 帶明確 replay tags 的 `learning.mlde_shadow_recommendations`
- 未來 `replay.*` schema，用於 experiment manifests、replay fills 和 reports

禁止 sinks：

- 把 replay fills 當作真實資料寫入 `trading.fills`
- 在沒有新增明確 replay source column / view 的情況下，把 replay rows 寫入 `learning.mlde_edge_training_rows`
- 由 replay output 直接修改 live / live_demo configs

建議未來 schema：

- `replay.experiments`
- `replay.market_data_manifests`
- `replay.execution_model_versions`
- `replay.simulated_fills`
- `replay.candidate_results`
- `replay.report_artifacts`

---

## 12. Healthcheck Requirements

Replay output 能夠餵給 demo candidates 之前，必須增加 healthchecks：

1. `replay_manifest_contract` — 每次 run 都有有效 manifest。
2. `replay_source_mix` — report 暴露 real / calibrated / synthetic 比例。
3. `execution_calibration_freshness` — calibration window 和 samples 足夠新鮮。
4. `execution_calibration_power` — low-sample cells 不會被當成 high confidence。
5. `replay_no_live_mutation` — replay path 不能寫 live / live_demo params。
6. `replay_shadow_sink_boundary` — replay-derived MLDE rows 是 advisory 且有 tag。
7. `replay_report_reproducibility` — report 引用 git SHA、config hashes 和 model version。

任一 healthcheck FAIL 都阻塞 promotion to demo candidate。

---

## 13. Implementation Sequence

### Phase R0 — Governance First

- land 本文件。
- 將它註冊為 REF-19 companion 中文版。
- 不改 runtime behavior。

### Phase R1 — Read-Only Replay MVP

- 新增 standalone replay runner。
- 載入 Bybit 歷史資料並生成 `PriceEvent` stream。
- 用選定 strategy / risk configs 跑 Rust `TickPipeline` replay mode。
- 輸出 manifest 和 report。
- 不寫 recommendations。

### Phase R2 — Execution Calibration

- 從真實 demo / live_demo data 訓練 / 校準 maker fill、slippage、reject、timeout models。
- 加入 calibrated / pessimistic / optimistic result bands。
- 補 healthchecks。

### Phase R3 — MLDE / Dream Advisory Integration

- 允許 replay 調用 DreamEngine 產生 parameter proposals。
- 允許 MLDE 對 replay candidates 做 rank / veto。
- 只寫帶明確 replay source tags 的 advisory rows。

### Phase R4 — Bounded Demo A/B Candidate Flow

- 允許 `demo_candidate` output 被 MLDE demo applier 消費。
- 強制 existing bounded delta、dedupe、rollback 和 audit rules。

### Phase R5 — GovernanceHub Live Candidate Review

- 允許高信心、且經 demo 驗證的 candidates 變成 live research candidates。
- GovernanceHub review 仍為 mandatory。
- Decision Lease 和 live gates 仍為 mandatory。

---

## 14. Cost Policy

默認路線：

1. 使用現有 runtime DB 和真實 demo / live_demo fills。
2. 使用 Bybit public historical data。
3. 開始收集 local orderbook data，供未來 replay 使用。
4. 在免費路徑證明瓶頸確實是缺失 L2 history 前，不使用付費資料。

付費 historical L2 data 需要 operator decision，並明確：

- vendor
- symbol list
- time range
- expected cost
- acceptance question
- dataset 使用期限

---

## 15. Review Chain

基於本文的 implementation work 同時屬於 feature / quant / data hybrid，必須使用：

- PM triage
- PA design check
- QC strategy / math review
- MIT data / schema review
- E1 implementation
- E2 adversarial code review
- E4 regression and targeted replay tests
- 若新增 GUI / operator workflow，加入 QA acceptance
- PM sign-off

可以跳過角色，但 PM 必須明確寫出理由；E2 和 E4 不可跳過。

---

## 16. Operator-Facing Summary

Reality-Calibrated Fast Replay 是高速度實驗環境。它調用 MLDE 和 DreamEngine，
但不重新定義它們。MLDE 和 DreamEngine 仍然是 general agent-learning components，
服務策略修復、風控調整與自我改進。

Replay 可以說：

- 這組參數不值得浪費 demo 時間
- 這組參數值得 bounded demo A/B
- 這個 candidate 應該寫入 future governance review

Replay 不能說：

- 這已經 live-approved
- synthetic PnL 是 real PnL
- ML / Dream output 是 order
- paper fill assumptions 是 exchange truth
