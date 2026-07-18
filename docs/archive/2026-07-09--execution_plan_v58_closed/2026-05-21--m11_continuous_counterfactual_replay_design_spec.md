---
spec: M11 Continuous Counterfactual Replay — Module DESIGN Specification
date: 2026-05-21
author: PA architecture draft for Sprint 1A-β CRITICAL module DESIGN
phase: v5.8 Sprint 1A-β（W1.5-3.5 PM 整合 calendar；CR-7 / CR-14 已 land）
status: SPEC-DRAFT-V0（module behavior 設計面 only；不寫 DDL / 不寫 IMPL code）
parent specs:
  - srv/docs/adr/0038-m11-continuous-counterfactual-replay-and-liquidations-source.md（ADR 治理邊界 — 不可違背）
  - srv/docs/adr/0037-m9-ab-framework-and-statistical-methodology.md（M9 fair execution clause；本 spec §6 對接）
  - srv/docs/adr/0026-direct-exploit-bypass-cpcv.md（pre-registration / event-study；M11 nightly 復用同 pre-registration 紀律）
  - srv/docs/execution_plan/2026-05-20--execution-plan-v5.8.md §2 M11 + §10 ADR roster
  - srv/docs/execution_plan/2026-05-21--m11_threshold_m7_dedup_decay_enforced_rename.md（M11 三級 threshold + M7 dedup contract；本 spec 引用不重複）
  - srv/docs/execution_plan/2026-05-21--v107_m11_replay_divergence_log_schema_spec.md（V107 schema placeholder；本 spec 引用 column 而非定義 DDL）
  - srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-21--v58_dispatch_consolidation.md §Sprint 1A-β + cross-V### graph
mirror precedent:
  - srv/docs/execution_plan/2026-05-21--m4_minimum_bar_and_leakage_protocol.md（module 設計 spec 範式）
scope: module 行為設計 + 整合接口 + acceptance criteria + IMPL phasing；不重複 V107 schema 細節；不重複 ADR-0038 治理邊界
---
> ⚠️ 归档历史文档 — 非当前权威。active 状态见 repo 根 `TODO.md`；本文件仅供历史/审计参考。（2026-07-18 审计批量补入）


# M11 Continuous Counterfactual Replay — Module DESIGN Specification

## §0 TL;DR

本 spec 鎖定 M11 module 的**行為設計**（nightly architecture / divergence taxonomy / flag-action map / 整合接口 / acceptance criteria / IMPL phase split），作為 Sprint 1A-β 5 CRITICAL module DESIGN 之一。**治理邊界**（self-hosted PG only / 3σ 統計推導 / M7 dedup 紀律）已由 ADR-0038 + `m11_threshold_m7_dedup_decay_enforced_rename.md` 鎖定，本 spec 不重述只 cross-ref。**Schema DDL**（V107 column / hypertable / Guard A/B/C）由 V107 spec 處理，本 spec 只引用 column 行為語義。

3 件關鍵設計選擇：

1. **Nightly 24h replay budget < 4h wall-clock** — 配合 PG shared_buffers 4-8GB 限制 + 既有 ml_training cron window；超 4h → M3 HEALTH_WARN（per CR-7）
2. **5-7 種 divergence taxonomy + severity matrix** — fill_chain / position / pnl / fee / liquidation / regime / risk 七類；NOISE/WARN/CRITICAL 三級對齊 M8 anomaly_severity（per `m11_threshold_..._rename` §5）
3. **Passive Slack 5d unack 自動升 M3 HEALTH_WARN** — per H-11 反向 attack「passive 通知 operator 5d 不 ack」mitigation；7d 升 HEALTH_DEGRADED 並暫停 LAL 1+2 auto-approval

---

## §1 Context — 為什麼 Continuous Counterfactual Replay

### §1.1 從 Stage 0R one-time preflight 升級為 nightly continuous 的理由

v5.7 §6 Stage 0R preflight 是策略 promotion **一次性 gate**：策略 promote 前跑一次 replay，PASS 即 promote、不再 nightly 跑。v5.8 §2 M11 將其升級為**持續 nightly hygiene**，核心理由 3 條：

1. **Silent strategy drift detection** — strategy 在 production 期可能因 hot-reload param 錯、配置漂移、IPC schema 升級遺漏而 silently 改變行為；one-time preflight 無法 catch 後續 drift。Continuous replay 每晚比對 live 與 replay → 任何「該策略本應 trigger 但沒 trigger」「該策略本不應 trigger 但 trigger」皆能 surface。
2. **Infra-induced behavioral change** — IPC tick latency spike / Bybit WS reconnect / cancel-on-disconnect 失效 / fill ack 漏接，這類非策略本體變更會改 fills 順序與 sizing。Replay 在控制 latency 假設下重跑可分離「策略 alpha」vs「infra noise」貢獻。
3. **Strategy alpha 真實驗證** — P0-EDGE-1 Y1 持續 negative edge 之根因之一是「無法區分策略本體 edge 不足 vs production 環境 noise 污染」。Continuous replay 提供 counterfactual baseline，配合 §6 M9 A/B 對齊路徑 → variant outcome 評估有客觀 reference。

### §1.2 M11 在 13 module 圖中的定位

per ADR-0038 + v5.8 §2 M11，M11 是 **sensor（divergence detector + signal emitter）**，**不是 actuator**：

```
[live execution trace] ──┐
                          ├──→ [M11 Replay Engine] ──→ [V107 divergence log]
[market.* historical PG] ─┘                              │
                                                          ├──→ [M7 decay input] (per CR-7)
                                                          ├──→ [M8 anomaly cross-ref] (per CR-7 §5)
                                                          ├──→ [M9 A/B fair execution audit] (per ADR-0037)
                                                          └──→ [M3 health WARN routing] (per CR-7)
```

M11 自身**不**寫 live state、**不** demote strategy、**不**改 sizing、**不**修 risk envelope；所有 action 由 down-stream M7 / M3 / M9 single authority 各自處理（per CR-7 dedup contract）。

### §1.3 為什麼 M11 屬 Sprint 1A-β CRITICAL

Sprint 1A-β 五個 CRITICAL module（M1 LAL / M3 health / M6 reward / M7 decay / M11 replay）之共同特徵：**Sprint 3-5 早期 IMPL 階段的接線依賴**。M11 nightly job IMPL（Sprint 3 W15-18）需要 V107 schema land + ADR-0038 治理邊界 + M7 dedup contract + M9 fair execution clause 同時就位；任一 spec 延後 → Sprint 3 IMPL 阻塞。

---

## §2 Nightly Replay 架構

### §2.1 高階流程（per ADR-0038 Decision 1 + Decision 5）

```
[Linux cron: 02:00-06:00 UTC nightly window，避開 ml_training_maintenance 02:00-04:00]
                            │
                            ▼
[Stage 1] Pre-flight 檢查（< 5 min budget）
  ├── V107 / V103 / V109 / V113 schema 可達
  ├── PG read-only role 連線健康
  ├── self-hosted market.* 表 retention 涵蓋 last 24h
  └── 上一晚 replay run 不在 stuck-running 狀態（防 lock 殘留）
                            │
                            ▼
[Stage 2] Fixture pull（< 30 min budget）
  ├── pull last 24h market.kline_* / market.public_trades / market.orderbook_l2_snapshot
  ├── pull last 24h market.liquidations（per ADR-0038 self-hosted only）
  ├── pull last 24h market.market_tickers / market.trade_agg_1m
  ├── data source priority: PG hot path > PG TimescaleDB chunk > 拒絕 vendor backfill
  └── fixture cache 寫 /var/lib/openclaw/m11_fixtures/<replay_id>/（per-run scratch space）
                            │
                            ▼
[Stage 3] Replay 5 strategy × all live symbols（< 3h wall-clock budget）
  ├── per strategy × symbol：載入 strategy snapshot config（git SHA + config hash）
  ├── deterministic replay：相同 random seed / 相同 IPC tick order / 相同 freshness clamp
  ├── 並行：tokio task pool 限 N=8（per CPU core 1 task；保留 4 core 給 production engine）
  ├── 每 strategy × symbol → emit replay_decisions list + replay_positions list + replay_pnl
  └── 不寫 live state；不觸 GovernanceHub；不發 IPC order intent
                            │
                            ▼
[Stage 4] Divergence detection（< 20 min budget）
  ├── per strategy × symbol：fetch live counterpart（trading.fills + governance.decisions）
  ├── 計算 7 種 divergence metric（per §4 taxonomy）
  ├── 對齊 5d empirical baseline（per `m11_threshold_..._rename` §2）
  ├── 三級分類 NOISE / WARN / CRITICAL
  └── 寫 V107 learning.replay_divergence_log（WARN + CRITICAL；NOISE 不寫）
                            │
                            ▼
[Stage 5] Flag 路由（< 5 min budget）
  ├── WARN → Slack daily digest queue（per §5 flag-action map）
  ├── CRITICAL → Slack immediate alert + M7 decay input + M3 HEALTH_WARN
  ├── persistent 14d divergence → M7 decay candidate trigger（per §7 M11 ↔ M7）
  └── M9 A/B test 進行中 → 變體 outcome 對齊 replay baseline（per §6 M11 ↔ M9）
                            │
                            ▼
[Stage 6] Cleanup（< 2 min budget）
  ├── fixture cache 保留 7d（debug 用）後 cron 刪除
  ├── replay_id metadata 寫 ops_log（per H-22 R4 governance）
  └── emit completion metric → M3 health（success / partial / failure）
```

### §2.2 為什麼 4h budget < 24h replay

per ADR-0038 Decision 5 + E4 H-15：

- PG shared_buffers 4-8GB 是 hard cap（per `project_hardware_constraints`），全 cohort 24h fixture pull 需 1-2h
- replay engine CPU 限 8 task pool（保 4 core 給 production），5 strategy × 25 symbol = 125 task / 8 並行 → 約 2-3h wall-clock
- divergence detection 是 vectorized statistical compute，< 20 min
- 總計 < 4h wall-clock；nightly cron window 02:00-06:00 有 buffer
- 超 4h → 自動 emit M3 HEALTH_WARN（per CR-7）而非 trigger demote；連續 7d 超 → operator 仲裁 §Decision 5 升級條件

### §2.3 Fixture cache 設計

| 維度 | 設計 |
|---|---|
| 位置 | `/var/lib/openclaw/m11_fixtures/<replay_id>/`（per-run scratch；不入 git） |
| 結構 | `market_data.parquet` + `live_trace.json` + `replay_decisions.json` + `divergence_metrics.json` |
| 保留 | 7d（cron auto-cleanup）；CRITICAL replay 保留 30d 用於 audit drill-down |
| 大小估算 | 5 strategy × 25 symbol × 24h market data ≈ 200-500 MB / run；7d ≈ 1.5-3.5 GB；30d CRITICAL hold ≈ < 1 GB |
| 對齊 | 不放 NAS（per `project_hardware_constraints` 40TB NAS via 10GbE 非 hot path）；local SSD scratch |

### §2.4 Mac dev vs Linux runtime 分工

per ADR-0007 + ADR-0038 Decision 5：

- **Mac dev**：不跑 full nightly；可跑 sampled 1h replay（1 strategy × 5 symbol）用於 IMPL debug + unit test fixture 生成
- **Linux runtime**：唯一 nightly cron 執行位；engine restart 後第一晚 baseline 重建期 cold_start flag

---

## §3 Self-Hosted PG `market.liquidations` Source（per ADR-0038 + BB 5.21 audit）

### §3.1 為什麼 self-hosted only（不依賴 Bybit historical）

per ADR-0038 Decision 1 + BB W-AUDIT-8a C1：

- Bybit V5 historical liquidations REST API **不存在**（per `docs/references/2026-04-04--bybit_api_reference.md` line 1088-1092）
- 即使未來開放，違反 ADR-0017 scanner-is-evidence-not-authority — vendor history 不可作 production replay dependency
- 4h wall-clock budget 在 vendor REST rate limit 下不可達

### §3.2 Schema reference（V107 spec 已 placeholder land）

per V107 spec doc，本 spec 不重複 column 定義，只引用 column 行為語義：

| Column | 本 spec 使用方式 |
|---|---|
| `divergence_id` / `ts` | per-divergence event PK |
| `replay_id` | per-run UUID；用於 §2 Stage 6 metadata + §5 flag routing |
| `hypothesis_id` | per ADR-0026 pre-registration；hypothesis-grounded replay 才填，nightly hygiene 為 NULL |
| `strategy_name` / `symbol` | 對齊 §4 taxonomy per-cohort 分類 |
| `divergence_metric_name` / `divergence_value` | per §4 七類 divergence 之一 |
| `divergence_level` | per `m11_threshold_..._rename` §2.2 三級（WARN / CRITICAL；NOISE 不寫） |
| `noise_floor_threshold` | per `m11_threshold_..._rename` §2.1 5d baseline μ + Nσ |
| `evidence_json` | raw live trace ID + replay output snapshot + diff breakdown |
| `engine_mode` | per ADR-0005（live / live_demo / demo）|

**禁止欄位**（per CR-7 + `m11_threshold_..._rename` §3.3）：`auto_demote` / `target_state` / `demote_proposal_id` — M11 不寫 action，這些由 M7 V113 own。

### §3.3 Self-hosted accumulation 狀態（per BB C6 PROOF PASS）

- `market.liquidations` 已累積 31,473 rows（per memory `project_decision_outcomes_not_dead`）
- W-AUDIT-8a C1 PASS 後 production WS `allLiquidation.{symbol}` 訂閱 enabled
- ADR-0029 land 後 `market.public_trades` + `market.orderbook_l2_snapshot` 同 pattern accumulation
- M11 nightly 首次 cold start 時若 self-hosted 數據不足（< 5d baseline）→ §2 Stage 4 emit `cold_start=true` flag，threshold 暫用 cohort median proxy；不允許 vendor backfill 補洞

---

## §4 Divergence Taxonomy — 7 種 type × Severity Matrix

### §4.1 Taxonomy 設計 — 為什麼 7 種而非 v5.8 §2 M11 原文 3 種

v5.8 §2 M11 line 401-404 原文只列「PnL / decision count / slippage」三類，是 ad-hoc 占位。為對齊 §6 M9 fair execution 評估 + §7 M7 decay 多 signal source confirm 需求，本 spec 擴展為 7 類 taxonomy；每類有獨立 metric 與獨立 baseline。

### §4.2 7 種 Divergence Type

| # | Divergence Type | metric_name 範例 | 計算定義 | 為什麼需要 |
|---|---|---|---|---|
| **D1** | `fill_chain` | `fill_count_diff`, `fill_order_diff_seq` | replay 預期 fills 數 vs live 實際 fills 數；fills 順序 hash diff | 偵測 IPC tick 漏接 / Bybit ack 漏 / 策略邏輯改動導致 trigger frequency 變 |
| **D2** | `position` | `position_diff_qty`, `position_diff_avg_entry` | replay 預期 holdings vs live 實際 holdings（per symbol per timestamp）| 偵測 fill chain 累積誤差 + 部分 fill / cancel race condition |
| **D3** | `pnl` | `pnl_diff_bps`, `realized_pnl_diff_usd`, `unrealized_pnl_diff_usd` | replay PnL（gross / net / realized / unrealized）vs live PnL | 主要 strategy alpha drift 指標（per v5.8 原文）|
| **D4** | `fee` | `fee_diff_bps`, `maker_rate_diff`, `taker_rate_diff` | replay 預期 maker/taker fee tier vs live 實際 fee tier | 偵測 Bybit fee tier rebalance / VIP level 升降 / PostOnly 邏輯漂移 |
| **D5** | `liquidation` | `liq_event_count_diff`, `liq_pnl_impact_diff` | replay 預期觸發 liquidation event 數 vs live 實際；liquidation 對 PnL 衝擊 | 對 funding_arb spike detection / bb_breakout absorption 等 liquidation-sensitive strategy 必要 |
| **D6** | `regime` | `regime_label_drift`, `regime_transition_count_diff` | replay 對 regime classify（vol regime / funding regime）標記 vs live runtime classifier | 偵測 regime classifier silent drift（per ADR-0036 M8 / M10 Tier D ATR-vol regime）|
| **D7** | `risk` | `risk_envelope_breach_diff`, `position_size_ratio_diff` | replay 預期 risk envelope clamp vs live；倉位佔比 diff | 偵測 risk_config TOML hot-reload 失效 / Guardian 邏輯漂移 |

### §4.3 Severity Matrix（per `m11_threshold_..._rename` §5 + ADR-0036 對齊）

每種 divergence type 獨立 5d baseline → 各自 mean μ + std σ；severity 級別對齊 M8 anomaly_severity vocabulary。

| Divergence Type | NOISE | WARN（μ + 2.5σ）| CRITICAL（μ + 3σ）| 為什麼 |
|---|---|---|---|---|
| D1 fill_chain | < ±2 fills | ±3-5 fills | ≥ ±5 fills | fill 順序對 PnL 衝擊大，threshold 嚴 |
| D2 position | < ±2% qty | ±2-5% qty | ≥ ±5% qty | position drift 是 fill chain 累積誤差，threshold 中 |
| D3 pnl | < ±5 bps | ±5-15 bps | ≥ ±15 bps | 主 alpha 指標，per-strategy σ 校準（per `m11_threshold_..._rename` §2.3）|
| D4 fee | < ±0.5 bps | ±0.5-1.5 bps | ≥ ±1.5 bps | fee tier 短期波動小，threshold 嚴 |
| D5 liquidation | 0 event diff | 1-2 event diff | ≥ 3 event diff | liquidation 是 rare event，threshold 寬 |
| D6 regime | 0 label diff | 1-2 label diff / 24h | ≥ 3 label diff / 24h | regime classifier 應穩定，drift 不容許 |
| D7 risk | 0 envelope breach diff | 1 breach diff | ≥ 2 breach diff | risk gate 是 hard boundary，threshold 嚴；任一 ≥ 2 必走 §5 M3 HEALTH_WARN |

**對齊 M8 anomaly_severity vocabulary**：

| M11 divergence_level | M8 anomaly_severity 對齊 | M7 action | M3 action |
|---|---|---|---|
| NOISE | INFO | none | none |
| WARN | WARN | feed M7 signal as 1-of-4 source | none |
| CRITICAL | CRITICAL | feed M7 signal as 1-of-4 source（strong） | trigger M3 HEALTH_WARN |
| reserved HALT | HALT | reserved Y2+ | reserved |

### §4.4 Per-strategy σ vs cohort-uniform σ（per ADR-0038 OQ-2）

- 5 策略 vol scale 差異 5-10× → cohort-uniform σ 對 grid 低 vol 過敏、對 bb_breakout 高 vol 不敏
- 採 **per-strategy × per-symbol σ**（V107 已預留 `baseline_5d_mean` + `baseline_5d_sigma` per row）
- cold start 期樣本不足 → 用 cohort median proxy + `cold_start=true` flag（per `m11_threshold_..._rename` §2.5）

### §4.5 為什麼必並列 leak-free shift(1) 對比（per `feedback_indicator_lookahead_bias`）

replay 在計算 D3 pnl divergence 時，若用 `rolling(N).max()` 或類似 含 current bar 的 window function 作為 entry signal 重建 → 必然 mean-revert artifact。本 spec mandate：

- replay engine 內部任何 rolling-window 信號重建必並列 leak-free `shift(1)` 版本
- divergence detection 計算時，pnl_diff 是「live PnL vs leak-free replay PnL」；若用 leaky replay → divergence 永遠偏負（artifact 而非真 alpha drift）
- E4 §M4-LEAKAGE-SCAN（per Sprint 1A-β H-17）需在 M11 replay engine 上 hit；任一 hit → IMPL block

---

## §5 Flag → Action Map

### §5.1 Action 路徑分類

| Severity | V107 寫 row | Slack 路由 | M7 dispatch | M3 dispatch | M8 cross-ref | M9 fair-exec audit |
|---|---|---|---|---|---|---|
| NOISE | ❌ 不寫 | ❌ | ❌ | ❌ | ❌ | ❌ |
| WARN | ✅ `divergence_level=WARN` | daily digest queue（次晨 09:00 UTC 推送）| ✅ M7 input 1-of-4 source | ❌ | ❌ | M9 進行中 test 對齊 |
| CRITICAL | ✅ `divergence_level=CRITICAL` | immediate alert（Slack incident channel） | ✅ M7 input 1-of-4 source（strong）| ✅ M3 HEALTH_WARN | ✅ M8 anomaly cross-ref event | M9 進行中 test inconclusive flag |
| reserved HALT | reserved Y2+ | reserved | reserved | M3 HEALTH_CRITICAL | M8 anomaly HALT | reserved |

### §5.2 Persistent divergence → M7 decay candidate（per H-11 反向 attack mitigation）

per H-11「M7 反向 attack：14d × 50% 持續虧」mitigation + ADR-0038 Decision 3 CR-7 dedup：

- 單晚 CRITICAL divergence → M7 input 1-of-4 source（**不獨立 demote**）
- 連續 14d CRITICAL ≥ 7d（即 14d 窗內過半夜為 CRITICAL）→ M7 **強候選** decay；M7 進入 multi-source confirm 流程
- 多 strategy 共同 14d CRITICAL → M3 HEALTH_DEGRADED + LAL 1/2 auto-approve 暫停（per §8 passive Slack 5d unack 條款延伸）

### §5.3 Slack 5d unack auto-escalate（per H-11 反向 attack）

per `2026-05-21--v58_dispatch_consolidation.md` H-11 反向 attack #6：「M11 passive Slack 報告 5d 不被 ack 自動升 M3 HEALTH_WARN」

| 不 ack 期 | Auto action |
|---|---|
| 0-1d | passive Slack daily digest |
| 1-3d | Slack reminder × 2/day |
| 3-5d | Slack escalation + 在 GUI Banner 顯示 |
| **5d** | **自動 emit M3 HEALTH_WARN**（per CR-7 M3 single health authority；mitigation H-11） |
| 7d | M3 HEALTH_DEGRADED + 暫停 LAL 1+2 auto-approval（fail-safe to Advisory mode）|

不 ack 計時定義：Slack message 無 emoji react 或無 GUI sign-off 點擊。

### §5.4 propTest 對「flag-action map」窮舉檢測

E4 H-14 §STATE-MACHINE-TEST 紀律延伸：對 §5.1 flag-action map 的 4 級 severity × 7 種 divergence type × 4 個 down-stream（M7/M3/M8/M9）matrix 跑 proptest 窮舉 → 任一 (severity, type) 對應 action 不一致即 FAIL。

---

## §6 M11 ↔ M9 Integration（per ADR-0037 fair execution clause）

### §6.1 為什麼 M11 是 M9 變體 outcome 評估的客觀 reference

per ADR-0037 Decision 2 + Decision 5 fair execution clause：M9 A/B test 將同策略 control + variant 分流，但兩 arm 各自走 production fills，受同期 market microstructure noise 影響 → 「variant 比 control 好 / 差」可能是 microstructure luck 而非真 alpha。M11 nightly replay 同時對 control 與 variant 重跑 → counterfactual fair execution baseline → variant outcome 評估有客觀 reference。

### §6.2 Integration 流程

```
M9 A/B test running (control arm + variant arm)
        │
        ├── live execution → fills 寫 trading.fills 各帶 ab_assignment_id
        │
        └── nightly M11 replay → 同樣 control + variant config 重跑
                │
                ▼
        per (test_id, arm) compute D3 pnl_diff（replay vs live）
                │
                ▼
        若 control + variant D3 都 < WARN threshold → A/B test conclusion valid
        若 control 或 variant D3 ≥ WARN → A/B test 該 evaluation cadence flag inconclusive
        若 control 或 variant D3 ≥ CRITICAL → A/B test 暫停（操 V108 ab_tests.status = paused），等 M7 + M3 處置完再 resume
```

### §6.3 V108 ab_tests / V107 replay_divergence_log 雙向引用

- V107 寫 row 時，若該 strategy × symbol 處於 active M9 test，`evidence_json` 攜帶 `{ab_test_id, arm}`
- V108 ab_results 寫 row 時，若該 evaluation cadence 內有 V107 WARN/CRITICAL → 自動標 `inconclusive_reason='m11_divergence_flagged'`
- M9 final conclusion（efficacy / futility）必檢查 evaluation cadence 內 V107 是否 clean；不 clean → conclusion 改 `inconclusive`

### §6.4 為什麼不直接讓 M9 觸發 M7（避走捷徑）

per ADR-0037 + ADR-0038 CR-7 dedup：M9 outcome inconclusive 走 **M9 own** 重啟流程（reset trial OR 延長窗口）；不直接 trigger M7 decay。M11 與 M7 是 single decay authority 鏈，M9 是 single experimentation authority 鏈，兩 chain 在 evidence layer 對齊（V107 + V108 cross-ref）而非 action layer 互相觸發。

---

## §7 M11 ↔ M7 Integration（per CR-7 dedup + H-11 mitigation）

### §7.1 Single decay authority 紀律（per `m11_threshold_..._rename` §3）

M11 是 **sensor / signal source**；M7 是 **single decay authority / actuator**。M11 不可：

- 寫 `learning.decay_signals` table
- 改 strategy sizing / capital allocation
- 自行 emit demote proposal

M11 可：

- 寫 V107 `learning.replay_divergence_log` 含 WARN / CRITICAL row
- emit signal to M7 ingestion queue（read-only push；M7 自行 pull/poll）
- emit Slack alert / M3 HEALTH_WARN routing（per §5）

### §7.2 14d persistent divergence → M7 strong candidate

per H-11 反向 attack #4 mitigation：

```
M11 nightly CRITICAL detected
   │
   ├── single occurrence → M7 input 1-of-4 source（normal weight）
   │
   └── 14d window 內 ≥ 7d CRITICAL → M7 strong candidate
                │
                ▼
        M7 multi-source confirm（≥ 2 of [M11 CRITICAL, 30d Sharpe<thr, DD>envelope, N-loss>3σ]）
                │
                ▼
        NORMAL_LIVE → DECAY_DETECTED → DEMOTE_PROPOSED → DECAY_ENFORCED (50% size, 14d review)
```

### §7.3 Recovery path M11 stale signal handling

per `m11_threshold_..._rename` §3.4：M7 promote 回 NORMAL_LIVE 時必須 acknowledge M11 last-N signals 為「stale post-recovery」。V107 不設 `acknowledged_at` column（per V107 spec 既有 schema），而是 M7 ingestion 端標記 stale → 計算 M7 multi-source confirm 時不算入。

### §7.4 V107 ↔ V113 read-only 關係

V107（M11）write-only by M11 nightly job；V113（M7）read-only by M7 detector（pull V107 last 14d WARN+CRITICAL row 作 input source）。V107 schema **無** V113 FK constraint（避免循環依賴 + 維持 M11 nightly job 不阻 M7 detector）。

---

## §8 Passive Slack 5d unack Auto-Escalate（per H-11 反向 attack）

### §8.1 為什麼是 hard governance

per H-11 反向 attack #6：「M11 passive Slack 報告 5d 不被 ack」是 operator forgetfulness 的具體場景。若無 mitigation → M11 divergence 累積但 operator 不知 → M7 decay candidate 累積但無人 review → 14d 後策略持續虧 50% 已 enforce 但 operator 才注意。

### §8.2 Mitigation 設計（per §5.3 延伸）

ack 定義 + 計時：

| Ack 方式 | 計入 |
|---|---|
| Slack message emoji react（任一 reaction）| ✅ |
| GUI replay_divergence_log row click + sign-off | ✅ |
| operator 在 Console 觸發「ack all M11 divergence last 24h」批量 | ✅ |
| operator 在 monthly review wizard 簽 batch sign-off | ✅ |
| 純 Slack reply text（無 reaction）| ❌（避免 reply chain 噪音與 ack 混淆）|

### §8.3 GUI Banner（per A3 Sprint 1A-ε Monthly Review Wizard）

A3 Lv 3 surface：當 M11 unack 累積 ≥ 5d → GUI 在 Console 頂部顯示紅 Banner，需 operator click「review now」進入 V107 review modal；review modal 顯示 last 14d WARN/CRITICAL row + 每 row 一鍵 sign-off / dispute。

---

## §9 Acceptance Criteria（7 條）

### AC-1 Divergence type classifier 完整性測試

**Test**：對 7 種 divergence type（D1-D7）各構造合成 fixture（known divergence amount）→ M11 classifier 必正確識別 type + severity 級別。

**Pass**：100% precision + 100% recall for 7 type × 3 severity matrix；任一 misclassification = FAIL。

### AC-2 Cross-language fixture 1e-4 tolerance（per H-18）

**Test**：Rust replay engine output vs Python reference impl output；對同 fixture run、同 strategy snapshot config、同 deterministic seed。

**Pass**：per-fill quantity 差 < 1e-4 / per-strategy net PnL 差 < 1e-4 bps；超過即 FAIL。對齊 H-18 cross-language 1e-4 容差 fixture harness 一次建多次用。

### AC-3 Nightly budget < 4h wall-clock verify

**Test**：Linux runtime 連續 5 晚 nightly run wall-clock metric；emit M3 health success / partial / failure flag。

**Pass**：5 晚平均 wall-clock < 4h；任一晚 > 4h → 觸 M3 HEALTH_WARN（不算 FAIL，是 mitigation 路徑驗）；連續 7d > 4h → operator 仲裁。

### AC-4 Flag-action map proptest 窮舉

**Test**：對 §5.1 4 級 severity × 7 種 divergence type × 4 個 down-stream matrix 跑 proptest（per E4 H-14 §STATE-MACHINE-TEST 延伸）。

**Pass**：任一 (severity, type, down-stream) tuple action 不一致即 FAIL；100% matrix coverage。

### AC-5 V107 schema 禁忌 column 反模式檢測

**Test**：grep `auto_demote|target_state|demote_proposal_id|decay_stage|stage_demoted` 在 V107 spec + IMPL PR 中。

**Pass**：0 hit（per CR-7 + `m11_threshold_..._rename` §3.3 M11 不寫 action）。任一 hit → sub-agent PR 拒絕。

### AC-6 Self-hosted PG only 反模式檢測

**Test**：grep 任何 vendor REST historical API call（`bybit_historical_*` / `binance_history_*` / 第三方數據源 URL）在 M11 replay engine code path 中。

**Pass**：0 hit（per ADR-0038 Decision 1）。任一 hit → IMPL block；違反 vendor optionality 紀律。

### AC-7 Look-ahead bias leak-free shift(1) 並列檢測

**Test**：對 M11 replay engine 內任一 rolling-window 信號重建（grep `rolling(.*\.max()|rolling(.*\.min()`）→ 必並列 leak-free `shift(1)` 版本（per `feedback_indicator_lookahead_bias` mandate）。

**Pass**：任一 leak 版本無 leak-free 對應 → FAIL；IMPL block。

---

## §10 IMPL Phase Split

### §10.1 兩 phase 分工（per TODO §1.2 + v5.8 §3）

| Phase | Sprint | 工時估 | Deliverable |
|---|---|---|---|
| **Phase A** | Sprint 3 W15-18 | 60-80 hr | M11 nightly job IMPL：cron + Stage 1-6 architecture + 7 種 divergence type classifier + 5d baseline 計算 + V107 writer + Slack daily digest 路由 + M3 HEALTH_WARN escalate（passive Slack 5d unack）|
| **Phase B** | Sprint 8 W30-33 | 40-60 hr | M11 recovery integration：M11 ↔ M7 hookup（per §7）+ M11 ↔ M9 fair execution audit（per §6）+ M11 ↔ M8 anomaly cross-ref + recovery path stale signal handling + 14d persistent divergence M7 candidate trigger |

### §10.2 為什麼分兩 phase

Phase A 純 sensor + 寫 log + 基礎 Slack 路由，**不依賴** down-stream M7 / M3 / M8 / M9 IMPL ready；可獨立 land Sprint 3 並開始累積 divergence baseline。Phase B 是與 M7（Sprint 8 IMPL）+ M3 recovery（Sprint 8）+ M8 alerting（Sprint 8）對齊的 integration phase；同期 land 避免 stale signal / recovery path 模糊。

### §10.3 Phase A 內部依賴

per CR-9 cross-V### dependency graph + Sprint 1A-β V107 land：

```
V107 land (Sprint 1A-β) → V103 land (Sprint 1A-α DONE) → market.* PG 累積 5d baseline
        │
        ▼
Phase A Sprint 3 IMPL：
  - cron job script land helper_scripts/cron/m11_nightly_replay.sh
  - tokio task pool spawn 限 N=8
  - Stage 1-6 architecture wire up
  - Slack daily digest webhook
  - 不依賴 M7 V113 land
```

### §10.4 Phase B 內部依賴

per Sprint 8 IMPL：

```
M7 V113 land + M7 detector IMPL（Sprint 8 first half）
        │
        ▼
Phase B Sprint 8 後半 IMPL：
  - M11 → M7 ingestion queue push
  - M11 → M9 V108 ab_results inconclusive flag write-back
  - M11 → M8 V109 anomaly cross-ref write
  - 14d persistent CRITICAL → M7 strong candidate trigger
  - recovery path stale signal handling
```

---

## §11 Cross-V### Dependency

per `2026-05-21--v58_dispatch_consolidation.md` §5.3 + V107 spec §5：

| V### | M11 依賴方式 | 為什麼 |
|---|---|---|
| **V107** (own) | M11 write-only | divergence log primary table |
| **V103** (hypotheses ref) | read-only via `hypothesis_id` FK | hypothesis-grounded replay 用（per ADR-0026 pre-registration）；nightly hygiene 為 NULL |
| **V109** (M8 anomaly ref) | M11 CRITICAL 寫 V109 cross-ref event | per CR-7 §5 4 級 severity 對齊；M8 anomaly events 共享 severity vocabulary |
| **V113** (M7 source per CR-7 dedup) | M7 detector read-only pull V107 last 14d WARN+CRITICAL | per §7.1 single decay authority；V107 ↔ V113 無 FK 避免循環 |
| **V108** (M9 A/B) | bi-directional cross-ref via `ab_test_id` in V107.evidence_json + V108.ab_results.inconclusive_reason | per §6 fair execution clause |
| **V105** (M2 overlay) | M2 state transition 觸發後 replay 重新 baseline | per `m11_threshold_..._rename` §2.1 排除規則（Stage transition 日不入 baseline）|
| **V096 boundary** (TimescaleDB extension) | hypertable infra prereq | V107 必 hypertable |

**Sprint 1A-β dispatch ordering**：V103 → V107 → V113 → V105；V109 與 V107 可並行；V108 在 Sprint 1A-γ land 後 Phase B 接線。

---

## §12 Open Questions（≥3 條）

### OQ-1 — Replay 重建用 strategy snapshot 的 config hash 來源

**Question**：M11 replay 需要 deterministic 重建 strategy decision，必載入 「策略當時的 config snapshot」。但 config 來自三層（risk_config_*.toml + StrategyParams ArcSwap + Rust schema）；config hash 該以哪一層為準？

**候選**：
- (a) 用 git SHA + risk_config TOML mtime + ArcSwap version 三 hash 合併
- (b) 用既有 ARCH-RC1 unified config contract canonical SHA-256（per `docs/references/2026-04-15--arch_rc1_unified_config_contract.md`）
- (c) 用 V103 hypotheses 表 `config_hash` 既有 column（per ADR-0026 v3）

**建議起點**：(b) ARCH-RC1 canonical SHA-256；同 ADR-0026 pre-registration 紀律。Phase A IMPL 前 PA + MIT confirm。

### OQ-2 — Nightly run 失敗（partial completion）的 V107 row 處置

**Question**：若 nightly 跑到一半（如 12 strategy × 25 symbol 中跑了 75 個就 PG 連線斷）→ 已寫的 V107 row 是「partial」狀態還是 mark `replay_id` 為 incomplete？

**候選**：
- (a) 不寫任何 V107 row 直到全 cohort 完成（all-or-nothing transaction）
- (b) 部分 row 寫入 + V107 `flags` JSONB 加 `partial_run=true`
- (c) ops_log 紀錄 partial + V107 不寫，下晚從上次斷點 continue

**建議起點**：(b) partial row 寫入 + `partial_run=true` flag；M7 ingestion 端對 partial run 不計入 14d 計算窗。Phase A IMPL 前 E5 確認 idempotency 可行性。

### OQ-3 — 5 strategy × 25 symbol 全 cohort vs 抽樣 nightly

**Question**：4h budget 在 cohort 擴張時（Y2 Copy Trading scale → 30+ symbol / 7+ strategy）可能超；要不要從 Phase A 起就支持「抽樣 nightly 模式」（每晚跑 1/N cohort，N 晚循環）？

**候選**：
- (a) Phase A 全 cohort；Y2 超 budget 時再 retrofit 抽樣
- (b) Phase A 起就支持 sampling mode（cli flag toggle）；正常 mode = 全 cohort
- (c) Always sampling，per-strategy 5d 內保證每 strategy × symbol 至少跑 1 次

**建議起點**：(a) Phase A 全 cohort，超 budget 時 emit M3 HEALTH_WARN（per ADR-0038 Decision 5）；連續 7d 超 → operator 仲裁時再決 (b) 或 (c)。

### OQ-4 — D6 regime divergence 對齊 M10 Tier D / M8 何者？

**Question**：D6 regime label drift 涉及 regime classifier。Y1 M10 Tier D 還未 active（Y2-Y3 才接 ATR-vol + funding state per CR-5 + ADR-0036）；Y1 期間 M11 D6 比對 baseline 用什麼？

**候選**：
- (a) Y1 直接停用 D6（NULL 不寫 row）；Y2 M10 Tier D land 後 enable
- (b) Y1 用 simple ATR-vol regime（per ADR-0036 替代 GARCH）作 proxy
- (c) Y1 用 M8 anomaly_severity 作 proxy（severity HIGH 期 = regime change 候選）

**建議起點**：(b) Y1 用 simple ATR-vol regime proxy；Y2 M10 Tier D active 後升級至完整 regime classifier。Phase A IMPL 前 MIT + QC confirm。

### OQ-5 — Replay engine 內部 leak-free shift(1) 是否走獨立 binary

**Question**：per AC-7 必並列 leak-free shift(1) 版本；要不要走獨立 binary（避免 production engine 內的 leaky behavior 污染 replay）？

**候選**：
- (a) 共用 IndicatorEngine + replay 模式 flag toggle shift(1) on/off
- (b) 獨立 `m11_replay_engine` binary 強制 leak-free
- (c) 共用 + replay 強制 leak-free + production 保持原行為（per memory `feedback_indicator_lookahead_bias` mandate）

**建議起點**：(c) — production 不改（保留現行 Donchian 等含 current bar 行為，符合 production reality），M11 replay engine 強制 leak-free 並 emit log 提示 production engine 用 leaky 版本作 entry filter 的 strategy 是 latent measurement-bias source。E1 / PA 確認 IndicatorEngine 在 Sprint 3 IMPL 前 design boundary。

---

## §13 Cross-References

| 文件 | 對應段落 / 議題 |
|---|---|
| `srv/docs/adr/0038-m11-continuous-counterfactual-replay-and-liquidations-source.md` | 治理邊界 — self-hosted PG only / 3σ 統計推導 / 4h wall-clock budget / M7 dedup contract / OQ-1..5 |
| `srv/docs/adr/0037-m9-ab-framework-and-statistical-methodology.md` | M9 fair execution clause — §6 整合來源 |
| `srv/docs/adr/0026-direct-exploit-bypass-cpcv.md` | pre-registration / hypothesis_id schema — §3.2 V107 column 行為 + OQ-1 config_hash 來源 |
| `srv/docs/execution_plan/2026-05-20--execution-plan-v5.8.md` | §2 M11 (391-423) + §10 ADR roster (744-762) + §10.5 P0 precondition |
| `srv/docs/execution_plan/2026-05-21--m11_threshold_m7_dedup_decay_enforced_rename.md` | M11 三級 threshold + M7 dedup contract + DECAY_ENFORCED rename — §4.3 severity matrix + §7 M7 integration 對齊 |
| `srv/docs/execution_plan/2026-05-21--v107_m11_replay_divergence_log_schema_spec.md` | V107 schema placeholder — §3.2 column 行為引用 |
| `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-21--v58_dispatch_consolidation.md` | §Sprint 1A-β + cross-V### graph + H-11 反向 attack mitigation + H-14 STATE-MACHINE-TEST + H-17 M9/M4 validation + H-18 cross-language fixture |
| `srv/CLAUDE.md` §六 Runtime Reality | Linux runtime 為唯一 nightly cron 執行位；Mac 不跑 full replay |
| `srv/CLAUDE.md` §四 Hard Boundaries | M11 不寫 live state；不繞 Decision Lease；不破 5-gate |
| memory `feedback_indicator_lookahead_bias` | AC-7 + §4.5 leak-free shift(1) 並列 mandate；OQ-5 IndicatorEngine boundary |
| memory `project_decision_outcomes_not_dead` | BB C6 PROOF PASS `market.liquidations` 31,473 rows accumulated 證據（§3.3）|
| memory `project_hardware_constraints` | 4-8GB PG shared_buffers 強約束（§2.2）|
| memory `project_multi_session_memory_race` | 5-7 並行 sub-agent ceiling（IMPL phase split §10.1 dispatch 紀律）|
| `srv/docs/governance_dev/amendments/2026-05-15--AMD-2026-05-15-01-canary-rebase-replay-preflight-demo-micro-canary.md` | Stage 0R preflight 共用 replay engine（per ADR-0038 OQ-5）|
| `helper_scripts/cron/m11_nightly_replay.sh` | Phase A Sprint 3 IMPL 待 land；cron schedule 對齊既有 ml_training_maintenance 02:00-04:00 避讓 |
| ADR-0017 (Scanner is evidence not authority) | 基礎原則延伸 — replay 不依賴 vendor history |
| ADR-0029 (market trade tape + L2 storage policy) | self-hosted accumulation infrastructure |
| ADR-0034 (Decision Lease LAL) | M11 ↔ M7 dispatch 走 LAL 1/2 路徑（per §7.2）|
| ADR-0010 (TimescaleDB hypertable + Guard migrations) | V107 hypertable Guard 範式對齊（V107 spec 處理；本 spec 不重複）|

---

## §14 Hard Boundary Compliance Confirmation（CLAUDE.md §四 + §二 16 原則）

| # | 原則 | M11 module 行為 | 是否合規 |
|---|---|---|---|
| 1 | 單一寫入口 | M11 是 read-only replay；不創 trade 寫入口 | ✅ |
| 2 | 讀寫分離 | M11 純讀 self-hosted PG `market.*`；無寫入 live state | ✅ |
| 3 | AI 輸出 ≠ 命令 | M11 divergence 走 V107 log + M7 dispatch；不繞 Decision Lease | ✅ |
| 4 | 策略不繞風控 | M11 CRITICAL 不 auto-demote；走 M7 + LAL gate | ✅ |
| 5 | 生存 > 利潤 | 不依賴 vendor API optionality；vendor incident 不影響 nightly 運作 | ✅ |
| 6 | 失敗默認收縮 | 4h budget 超 → M3 WARN；cohort 數據不足 → degraded sample + warn | ✅ |
| 7 | 學習 ≠ Live | M11 是 evidence accumulation；不寫 live state；CRITICAL 必走 M7 + LAL | ✅ |
| 8 | 交易可解釋 | V107 `evidence_json` 提供完整 audit trail；每筆 divergence 可重構 | ✅ |
| 9 | 雙重防線 | M11 sensor + M7 actuator 雙層；CRITICAL gate 不可單一路徑跳過 | ✅ |
| 11 | Agent 最大自主 | Agent 在 P0/P1 內走 LAL 1 auto-approve；LAL 2 受 ADR-0034 約束 | ✅ |
| 12 | 系統演化由 evidence 驅動 | M11 持續累積 divergence evidence 是 evidence-based decision 基礎 | ✅ |
| 13 | cost 感知 | 4h wall-clock budget 紀律；不增加 AI call cost | ✅ |
| 14 | 零外部成本 | self-hosted PG only；不依賴外部付費 historical API | ✅ |
| 16 | Portfolio > 孤立 trade | M11 cohort-level replay 是 portfolio thinking audit infrastructure | ✅ |

**Hard boundaries（CLAUDE.md §四）**：M11 無觸碰 `live_execution_allowed` / `OPENCLAW_ALLOW_MAINNET` / `authorization.json` / `live_reserved` 任一；M11 不在 trading hot path（cron nightly job）；M11 不寫 trading state（只寫 learning.* schema）。

---

## §15 Sign-off Table

| Role | Status | Date | Note |
|---|---|---|---|
| PA | DRAFTED | 2026-05-21 | module behavior 設計面 + 整合接口 + AC + IMPL phasing；不寫 DDL；不寫 IMPL code |
| MIT | PENDING | — | V107 schema column 行為對齊 + §4 divergence type classifier 統計合理性 |
| QC | PENDING | — | §4 severity matrix + AC-1 / AC-2 / AC-7 statistical rigor + OQ-2 / OQ-4 |
| QA | PENDING | — | §5 flag-action map + AC-4 proptest + §8 ack 計時定義 |
| E4 | PENDING | — | AC-1 / AC-2 / AC-3 / AC-7 test harness 規劃；H-18 cross-language fixture 落地 |
| E5 | PENDING | — | §2 4h budget 驗 + OQ-2 partial run idempotency + V107 hypertable + IPC 通量 |
| CC | PENDING | — | §14 16 原則 + Hard Boundaries 合規確認 |
| FA | PENDING | — | §5 + §7 M11 ↔ M7 / M3 / M8 / M9 邊界 + H-11 反向 attack 6 條全 mitigation |
| PM | PENDING | — | Sprint 1A-β CRITICAL module DESIGN closure + OQ-1..5 仲裁路徑 |

---

**END M11 Continuous Counterfactual Replay — Module DESIGN Specification**
