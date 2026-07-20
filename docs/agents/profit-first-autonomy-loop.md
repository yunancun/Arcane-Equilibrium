# Profit-First Autonomy Loop

目標：構建本地化、可審計、可重建、可持續自我進化的 multi-agent auto trading bot。TradeBot 必須在 operator 定義的 survival、loss-control、authorization、Rust authority、Decision Lease、auditability、reconstructability 邊界內，自主發現機會、自主判斷、自主設計實驗、自主執行 Demo bounded probes、自主復盤 after-cost outcome、自主學習、自主調整策略參數，並草擬新策略或策略變體。最高優化目標是真實 risk-adjusted net PnL after fees/slippage；任何不能遷移到未來 live 審查的 Demo 經驗都不算有效進展。

本文件只定義長期工作流。當前 blocker、候選、證據路徑、命令入口讀 `TODO.md` 和其引用；不要把易過期任務塞回本文件。

本文件不是自動 continuation authority。普通任務一律
`continuation_mode=finite`，完成使用者要求後停止。只有 exact Operator request 明示要跑
本 loop 時才建立 `operator_loop` task；每輪排下一 turn 前必須通過 Task Execution
Control。相同 semantic progress digest 立即 `BLOCKED_NO_DELTA`，不得靠新 timestamp、
TODO pointer、全面重審或虛構 next_action 維持 loop。

加速 candidate 進 Demo 驗證時，使用 `docs/agents/profit-first-fast-demo-promotion-loop.md`。該子循環允許部分達標 candidate 在機器檢查通過後進 bounded Demo probe，用真實 Demo order/fill/fee/slippage 補證據，再回到 learning 和 promotion chain；它不放寬本文件的 survival、loss-control、authorization、Rust authority、Decision Lease、auditability、reconstructability 邊界。

## 0. Load

每輪先讀 `AGENTS.md`，再用 `.codex/agent_registry_v1.json` 與 Context
Interface 按 task facts 載入最小充分 pack。Active loop 必讀 `TODO.md`；只讀它直接
引用的 current evidence、相關 code/schema、normative boundary 與 timestamped runtime
artifact。`.codex/MEMORY.md`、完整 README、所有角色 memory/report 不做 universal
preload。

事實衝突使用 typed authority matrix：同 class 比 freshness/strength；跨 class 保留
DRIFT/CONFLICT。Runtime/source observation 不得覆蓋 normative policy，也不靠重跑空審核
製造假新鮮度。

## 1. Agent Role

Codex/agent 的工作是開發、測試、部署、診斷 TradeBot，讓 TradeBot 自主找機會、驗證、交易、復盤、學習。agent 不手工替系統長期找 alpha。

agent 只在需要定位本地程序錯誤、資料斷點、證據污染、風控誤判、學習薄弱點時做獨立數據分析；分析結果必須落成 code、test、schema、runtime check 或 TODO，不作為人工交易決策。

## 2. Demo Authority

operator 已授權 Demo 內推進、開發、部署、runtime sync、bounded probe。不得再用 generic operator authorization defer。

order-capable action 前必須有 machine-checkable Demo envelope：

- `scope`: Demo only, no live/mainnet
- `actions`: research, source, deploy/sync, runtime health, private-read, loss cleanup, bounded probe
- `loss_limits`: max order/open notional, daily loss, probe count, concurrent symbols, kill switch
- `evidence`: order/fill lineage, fees, slippage, controls, hashes, reconstruction inputs
- `expiry`: expiry/renewal
- `denials`: no global Cost Gate lowering, no live promotion

若不能執行，狀態只能是：`FAIL_LOSS_LIMIT`、`FAIL_EVIDENCE`、`FAIL_AUTH_SCHEMA`、`FAIL_RUNTIME`、`LIVE_BLOCKED`、`READY`。

## 3. Cycle

| Phase | 必做 | 禁止 |
| --- | --- | --- |
| Baseline | 實作/修復 open orders, positions, runtime health, fee/slippage/BBO, evidence collectors | 把 cleanup fill 當 profit proof |
| Discover | 實作 TradeBot 的 false-negative, symbol/horizon, MM, regime, entry/exit, allocation, fee-route discovery | agent 手工長期挑候選替代程序 |
| Admit | 實作 candidate envelope compiler: id, sizing, BBO, cost plan, loss cap, Decision Lease, Rust path, kill, review contract | 降 global Cost Gate 或繞過 Rust/Lease |
| Execute | 實作 Demo bounded runner: one candidate/portfolio packet, full lineage, kill/rollback | live, untracked mutation, non-Rust order path |
| Review | 實作 candidate-matched PnL, actual cost, controls, realism, OOS/repeat evaluator | count unattributed or unrelated fills |
| Learn | 實作 observation -> lesson -> hypothesis -> experiment -> verdict -> proposal pipeline | learning output 直接 grant order/live/risk authority |
| Deploy | source fix, tests, runtime sync, health check, rollback | secrets in argv/artifacts, silent runtime mutation |

每輪必須產生狀態轉移：`DONE`、`DONE_WITH_CONCERNS`、`BLOCKED_BY_LOSS_CONTROL`、`BLOCKED_BY_RUNTIME`、`BLOCKED_NO_DELTA`、`ROTATED`。只有 ACTIVE lane 可進入下一輪；WAITING/DEFERRED/CLOSED 不可被自動 selector 重開。

## 4. Learning I/O

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

## 5. L2 Handoff

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

## 6. Proof

Profit proof 必須同時具備：

- candidate-matched orders/fills
- actual fees and slippage
- reconstructed entry/exit/markout
- matched controls
- proof-exclusion pass
- execution realism review
- repeat or OOS path

永遠不是 proof：artifact count、Paper archive、source smoke、replay-only positive、single-window MM positive、`flash_dip_buy` cleanup fill、unattributed fill、residual cleanup fill、stale local `Working` row。

## 7. Anti-Repeat

不得把 next action 寫成：全面重審、確認 demo 是否下單、確認 learning 是否在跑、繼續觀察。

同一 non-actionable semantic state 第二次出現時必須
`BLOCKED_NO_DELTA + next_action=null + schedule_wakeup=false`。只有真實 delta 後的新
ACTIVE admission 才可選擇：

- implement/deploy missing plumbing
- rotate candidate
- shrink envelope
- mark loss-control/runtime blocked
- update stale pointer

profit hypotheses 應由 TradeBot discovery/learning pipeline 產出。agent 只在工程診斷需要時補 developer hypotheses，字段固定：`program_gap`、`why_it_blocks_autonomy`、`fastest_safe_test`、`required_data`、`failure_condition`、`max_safe_next_action`。

## 8. Hosted CI Cost Gate

GitHub Actions 是 stable-head integration proof，不是 ALR 的 edit-debug loop。

- 每個 PR 只設一個 PM-owned publication lane；其他 sub-agent 只回傳 fragment/patch，
  不 push、不重跑、不輪詢相同 GitHub 狀態。
- PR head 更新前必須先跑可行的 focused、adjacent 與 wider local regression，並把
  同一 blocker 的已知修復合併成一次更新。
- workflow 先按 changed paths 決定是否需要 Rust、macOS 10x、ephemeral PG 與
  specialized guard；新 head 必須取消舊 head 的 in-flight run。
- 同一 `workflow/job/step/failure fingerprint` 第二次出現即停止發布；下一步只能是
  本地重現、改變驗證策略、縮小/修正 scope，或明確標記 external-only blocker。
- unchanged head 不 rerun；stable current head 最多請求一次 automated review；舊 SHA
  review 不得充當 current-head approval。
- CI quota/預算耗盡是 hosted-validation blocker，不是提高預算、刪除 gate、降低 proof
  標準或繼續 push 的理由。

ALR strict-default 變更若使 legacy/offline fixture 失敗，先判斷 fixture 是否需要顯式
選擇相容模式。只有被失敗集合精確點名的 fixture 可加入 checkpoint scope；production
source scope 不因測試相容性而無界擴張。擴 scope 後仍須本地 wider regression 全綠，
才可形成下一個 PR head。

明示的 long loop 之 Git 狀態同樣是 gate：每輪必須由 clean、帶 exclusive writer
lease 的 linked feature-worktree checkpoint 開始，
dirty scope 經 `git_loop_guard.py --phase checkpoint` 驗證後才可 stage；綠燈即由
PM 做窄 commit，再以 exact new HEAD 的 `--phase start` clean PASS 進下一輪。不得把
多輪改動留成一大包 dirty tree，也不得為了避免 dirty 而每輪 push 觸發 hosted CI。

最終發布只做一次 stable feature-head push，並以 `post-push` 證明 remote branch SHA；
merge 必須 `--match-head-commit`。之後按 `.codex/SYNC.md` 將 clean Mac main 與 clean
Linux main ff-only 到同一 true `origin/main` SHA，再跑 four-head reconcile。三個 git
head 未一致不得 `DONE`；engine 落後則誠實標記 `SOURCE_SYNCED_RUNTIME_PENDING`，不得
把 source sync 冒充 runtime deploy。
