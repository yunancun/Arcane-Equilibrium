# Profit-First Autonomy Loop

目標：本地自動閉環進化交易能力。最高優化目標是 true risk-adjusted net PnL after fees/slippage，但永遠低於 survival、Guardian/risk gates、Decision Lease、Rust authority、authorization gates、auditability、reconstructability。

本文件只定義長期工作流。當前 blocker、候選、證據路徑、命令入口讀 `TODO.md` 和其引用；不要把易過期任務塞回本文件。

## 0. Load

每輪先讀：

1. `AGENTS.md`, `CLAUDE.md`, `.codex/MEMORY.md`
2. `README.md`
3. `docs/agents/context-loading.md`
4. `TODO.md`
5. `TODO.md` 引用的最新報告與 runtime artifacts

事實衝突時：runtime/source 新證據優先；governance 以已接受 docs/ADR 優先；修 stale pointer，不重跑空審核。

## 1. Demo Authority

operator 已授權 Demo 內推進、開發、部署、runtime sync、bounded probe。不得再用 generic operator authorization defer。

order-capable action 前必須有 machine-checkable Demo envelope：

- `scope`: Demo only, no live/mainnet
- `actions`: research, source, deploy/sync, runtime health, private-read, loss cleanup, bounded probe
- `loss_limits`: max order/open notional, daily loss, probe count, concurrent symbols, kill switch
- `evidence`: order/fill lineage, fees, slippage, controls, hashes, reconstruction inputs
- `expiry`: expiry/renewal
- `denials`: no global Cost Gate lowering, no live promotion

若不能執行，狀態只能是：`FAIL_LOSS_LIMIT`、`FAIL_EVIDENCE`、`FAIL_AUTH_SCHEMA`、`FAIL_RUNTIME`、`LIVE_BLOCKED`、`READY`。

## 2. Cycle

| Phase | 必做 | 禁止 |
| --- | --- | --- |
| Baseline | open orders/positions, runtime health, latest evidence, fee/slippage/BBO | 把 cleanup fill 當 profit proof |
| Search | 找 false-negative, symbol/horizon, maker/MM, regime, entry/exit/stop, allocation, fee route | 用 artifact count/replay/single-window positive 選候選 |
| Admit | 生成 candidate envelope: id, sizing, BBO, fee/slippage plan, loss cap, Decision Lease, Rust path, kill, review contract | 降 global Cost Gate 或繞過 Rust/Lease |
| Execute | Demo bounded probe, one candidate/portfolio packet, full lineage | live, untracked mutation, non-Rust order path |
| Review | candidate-matched net PnL after actual cost, controls, realism, OOS/repeat path | count unattributed or unrelated fills |
| Learn | observation -> lesson -> hypothesis -> experiment -> verdict -> proposal | learning output 直接 grant order/live/risk authority |
| Deploy | source fix, tests, runtime sync, health check, rollback | secrets in argv/artifacts, silent runtime mutation |

每輪必須產生狀態轉移：`DONE`、`DONE_WITH_CONCERNS`、`BLOCKED_BY_LOSS_CONTROL`、`BLOCKED_BY_RUNTIME`、`NOOP_NO_DELTA`、`ROTATED`。

## 3. Learning I/O

Learning input packet 必須規範化、append-only、可重建、無 secrets：

- `schema_version`
- `run_id`
- `created_at`
- `source_refs`
- `candidate_id`
- `side_cell_key`
- `strategy_name`
- `symbol`
- `side`
- `horizon_minutes`
- `market_context`
- `order_context`
- `fills`
- `fees_slippage`
- `risk_state`
- `controls`
- `regime_labels`
- `proof_exclusions`
- `authority_envelope`
- `net_pnl_after_costs`

Learning output packet 必須只輸出可審核結論或提案：

- `schema_version`
- `learning_id`
- `input_refs`
- `stage`: `observation|lesson|hypothesis|experiment|verdict|proposal`
- `claim`
- `confidence`
- `expected_net_pnl_mechanism`
- `parameter_delta`
- `loss_controls`
- `evidence_requirements`
- `next_action`
- `mutation_allowed`
- `runtime_authority_required`
- `l2_escalation`

規則：

- output 必須引用 input hashes/source refs。
- 無 candidate-matched evidence 時只能是 `hypothesis` 或 `proposal`。
- `mutation_allowed=true` 仍只代表當前 Demo envelope 內可執行；不代表 live、risk-envelope expansion、Cost Gate lowering。
- unattributed fills、cleanup fills、replay-only results 永遠進 `proof_exclusions`。

## 4. L2 Handoff

只在 L0/L1 無法低成本判斷、或高 upside ambiguity 值得分析時交給 L2。送 compact packet，不送 raw log。

L2 request：

- `question`
- `input_refs`
- `candidate_set`
- `decision_needed`
- `loss_limits`
- `cost_budget`
- `required_output_schema`

L2 response：

- `l2_advice_id`
- `input_refs`
- `answer`
- `confidence`
- `assumptions`
- `risk_flags`
- `recommended_tests`
- `not_authority=true`

L2 只能做 pattern discovery、anomaly diagnosis、hypothesis generation、experiment design、meta-review。L2 不能下單、改 runtime、降 Cost Gate、批 live、繞 proof。

## 5. Proof

Profit proof 必須同時具備：

- candidate-matched orders/fills
- actual fees and slippage
- reconstructed entry/exit/markout
- matched controls
- proof-exclusion pass
- execution realism review
- repeat or OOS path

永遠不是 proof：artifact count、Paper archive、source smoke、replay-only positive、single-window MM positive、`flash_dip_buy` cleanup fill、unattributed fill、residual cleanup fill、stale local `Working` row。

## 6. Anti-Repeat

不得把 next action 寫成：全面重審、確認 demo 是否下單、確認 learning 是否在跑、繼續觀察。

同一 non-actionable state 第二次出現後，下一步只能：

- implement/deploy missing plumbing
- rotate candidate
- shrink envelope
- mark loss-control/runtime blocked
- update stale pointer

每輪還要產出 1-3 個 aggressive profit hypotheses，字段固定：`why_it_might_make_money`、`fastest_safe_test`、`required_data`、`failure_condition`、`authority_required`、`max_safe_next_action`、scores。
