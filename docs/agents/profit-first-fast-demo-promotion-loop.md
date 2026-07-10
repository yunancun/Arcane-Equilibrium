# Profit-First Fast Demo Promotion Loop

目的：讓 TradeBot 快速把「部分達標但缺真實執行證據」的 candidate 推進到有界 Demo 驗證，取得真實 order/fill/fee/slippage/markout 證據，再回到 learning 和 promotion chain。速度來自機器檢查與小步 Demo probe，不來自放寬 survival、loss-control、authorization、Rust authority、Decision Lease、auditability 或 reconstructability。

本文件是 `docs/agents/profit-first-autonomy-loop.md` 的加速執行子循環。當前 candidate、runtime 事實、artifact 路徑仍讀 `TODO.md`。

## 1. Candidate Classes

每個 candidate 先被分類，不直接跳成 order：

| Class | 意義 | 允許下一步 |
| --- | --- | --- |
| `RESEARCH_ONLY` | 只有 discovery/replay/shadow 證據，缺 Demo loss-control 或執行可行性 | 補資料、補 code、補 envelope |
| `DEMO_ELIGIBLE_PARTIAL` | identity、GUI 風控、loss-control、Rust path 可檢查；盈利證據不足 | 可進 Demo final-window preflight |
| `DEMO_READY_FINAL_WINDOW` | fresh BBO/instrument、Decision Lease、Guardian、Rust authority 同窗口通過 | 可送一筆 bounded Demo probe |
| `DEMO_EXECUTED_REVIEW_PENDING` | 已有 candidate-matched Demo order/fill | 必做 after-cost review |
| `PROMOTION_CANDIDATE` | Demo after-cost、controls、realism、repeat/OOS 達標 | 進 canary/promotion review |
| `PROMOTION_BLOCKED` | 證據污染、風控失敗、不可重建、或 after-cost 失敗 | 降級、縮 envelope、或 rotate |

## 2. Partial Candidate Rule

部分達標 candidate 可以進 Demo，是為了核實缺口，不是因為已證明盈利。

可以缺：

- candidate-matched live/Demo fill 歷史
- repeat/OOS 結論
- after-cost promotion proof
- 完整參數優化結論

不能缺：

- preregistered distinct-entry n_eff 檢定 pass（WP-A.6 前置，2026-07-10 R3）：
  候選統計證據必須來自 per-(side_cell, entry_minute, horizon) 去重 + 非重疊窗
  n_eff 的 lane review（`sample_eligibility_ok=true`，即 `effective_entry_count`
  / distinct-UTC-day / top-day share 全過預註冊門檻，正本
  `docs/research/2026-07-10--counterfactual_rerun_preregistration.md` §3）；
  raw `outcome_count` 不是樣本量，不得作為任何 eligibility/t/BH 的 n
- structured candidate identity
- GUI/Rust RiskConfig cap lineage
- fresh equity and order shape
- machine-checkable loss-control envelope
- Guardian/risk pass
- active Decision Lease in the final window
- Rust authority/order supplier path
- audit/reconstruction packet
- proof-exclusion rules
- Demo-only boundary

任何一項不能缺的條件缺失，狀態只能是 `BLOCKED_BY_LOSS_CONTROL`、`BLOCKED_BY_RUNTIME`、`NOOP_NO_DELTA` 或 `ROTATED`，不得靠人工口頭批准補洞。

## 3. Minimum Demo Entry Envelope

進 Demo 前，runner 必須在同一 artifact chain 中寫出：

- `candidate_id`, `side_cell_key`, `strategy_name`, `symbol`, `side`, `horizon_minutes`
- `risk_source_of_truth=GUI_RUST_RISKCONFIG`
- `accepted_demo_equity_usdt`
- `per_trade_risk_pct`, `per_trade_budget_usdt`
- `position_size_max_pct`, `single_position_budget_usdt`
- `effective_single_order_cap_usdt`
- `max_order_notional_usdt` if explicitly configured
- `daily_loss_cap_usdt`
- `max_probe_count`, `max_concurrent_candidate_count`
- `decision_lease_id`
- `guardian_state`, `position_size_multiplier`
- `fresh_bbo`, `instrument`, `qty`, `notional`
- `order_link_id`
- `audit_artifact_refs`
- `proof_exclusions`

`10 USDT` 只能出現在歷史診斷或 local test 輸入中，不得作為權威單筆風控 cap。

## 4. Final Window

前置（WP-A.6，2026-07-10 R3）：candidate 必須已通過 §2 第一項的 preregistered
distinct-entry n_eff 檢定；未通過（含 n_eff 不明、僅有 raw outcome_count 的
證據鏈）不得開啟本窗口，PM/E3 dispatch 一律 fail closed。

Demo order-capable runner 的最後窗口順序固定：

1. 讀 fresh runtime governance snapshot。
2. 讀 fresh Demo equity。
3. 解析 GUI/Rust RiskConfig。
4. 重新編譯 candidate envelope。
5. 取得 public BBO/instrument。
6. 申請短 Decision Lease。
7. 在 lease live 時重新刷新 BBO/instrument/order shape。
8. 驗 Guardian、Rust authority、loss-control、book-clean、auditability。
9. 僅當全部通過，提交一筆 bounded Demo order。
10. 釋放或 consume lease。
11. 立即收集 order/fill/fee/slippage/reconstruction inputs。

如果任何步驟失敗，必須 fail closed，並寫出 blocker artifact；不得重試成隱藏 order path。

## 5. Review And Learn

每筆 Demo probe 之後必須產生 after-cost review：

- candidate-matched order/fill
- actual fee and slippage
- entry/exit/markout reconstruction
- controls and matched non-trade baseline
- execution realism
- proof-exclusion pass
- repeat/OOS requirement status
- net PnL after costs
- risk-adjusted score
- learning packet hash

Learning output 仍只能是 proposal/advice，除非當前 Demo envelope 明確允許下一個 bounded probe。L2 不能直接授 order/live/risk authority。

## 6. Promotion Chain

Demo outcome 只進 promotion chain，不直接進 live：

1. `DEMO_EXECUTED_REVIEW_PENDING`
2. `DEMO_AFTER_COST_REVIEW_READY`
3. `LEARNING_PROPOSAL_READY`
4. `CANARY_STAGE_REVIEW_READY`
5. `PROMOTION_CANDIDATE`
6. `LIVE_REVIEW_REQUIRED`

Live/mainnet 仍需既有 5-gate live boundary。Demo positive、single-window positive、cleanup fill、unattributed fill、artifact count、replay-only positive 都不能成為 promotion proof。

## 7. Loop State Transition

每輪必須輸出一個狀態：

- `DONE`
- `DONE_WITH_CONCERNS`
- `BLOCKED_BY_LOSS_CONTROL`
- `BLOCKED_BY_RUNTIME`
- `NOOP_NO_DELTA`
- `ROTATED`

若沒有新證據，不重跑空審核；下一步只能改 code/schema/runtime check、縮 envelope、rotate candidate、或更新 stale pointer。

## 8. Operator GUI Contract

GUI 應清楚顯示三件事：

- Authorization approval：人工批准 SM-01 授權。
- Decision Lease：只讀短 TTL final-window lease，不手工批准。
- Bounded Demo admission：candidate 進 Demo 的機器檢查條件與當前 runtime 姿態。

GUI 不直接送交易所訂單，不直接建立 lease，不直接降低 Cost Gate，不直接授 live/mainnet。
