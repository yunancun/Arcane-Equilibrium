# 2026-06-21 -- Cost-Gate Runtime Activation Blocker Audit

## 結論

這次是 runtime read-only audit，不是 source 改動。結論很清楚：

- PG reject data 正在大量積累。
- cost-gate learning ledger / materializer / outcome review 沒有在 runtime 積累。
- blocker 是 runtime source reconcile/sync + writer/cron/append activation 尚未做，不是 source 缺功能，也不是缺 PG 數據。

因此下一步不應再做 source-only wrapper；需要 operator 明確授權 runtime activation。

## Runtime Evidence

只讀命令面：`ssh trade-core` 下的 `git status`、`ls`、`crontab -l`、`pgrep`、`/proc/<pid>/environ`、PG `SELECT count(*)`。沒有 pull、沒有寫 crontab、沒有改 env、沒有 restart、沒有 PG write。

Observed:

- runtime repo：`/home/ncyu/BybitOpenClaw/srv`
- runtime HEAD：`917be4cc9a3d3549328155f1863d42400c70267f`
- branch：`main`
- status：behind `origin/main` by 5 commits
- dirty：大量 modified/untracked source/doc files
- current `main` on Mac/origin：`2c4f524f99a537c2c728e75e42affb3688862dbe`

Required source files missing on runtime checkout:

- `helper_scripts/research/cost_gate_learning_lane/status.py`
- `helper_scripts/research/cost_gate_learning_lane/reject_materializer.py`
- `helper_scripts/cron/cost_gate_learning_lane_cron.sh`
- `helper_scripts/cron/install_cost_gate_learning_lane_cron.sh`

Runtime artifacts:

- present：`/tmp/openclaw/cost_gate_learning_lane/demo_learning_lane_plan_latest.json`
- absent：`probe_ledger.jsonl`
- absent：`reject_materializer_latest.json`
- absent：`outcome_refresh_latest.json`
- absent：`blocked_outcome_review_latest.json`
- no `cost_gate_learning_lane.log`
- no matching cost-gate learning lane crontab entry

Running engine:

- PID：`35187`
- `OPENCLAW_DATA_DIR=/tmp/openclaw`
- `OPENCLAW_DEMO_LEARNING_LANE_WRITER` unset
- `OPENCLAW_DEMO_LEARNING_LANE_PLAN` unset
- `OPENCLAW_DEMO_LEARNING_LANE_LEDGER` unset

PG reject source:

- last 4h demo/live_demo Cost Gate rejects：`27071`
- total demo/live_demo Cost Gate rejects：`4423477`
- latest reject timestamp：`2026-06-21 20:47:59.988+02`

## Interpretation

這直接回答兩個問題：

- 新信號是否 silent 丟失？
  - 在 PG 層不是 silent：`learning.decision_features` 正在記錄大量 Cost Gate rejects。
  - 在 learning ledger 層仍然是未積累：runtime 沒有 materializer / writer / cron / ledger artifacts。
- 是否應該 lower Cost Gate？
  - 不能盲目 lower。上一個 read-only smoke 已顯示目前 BTCUSDT 樣本 review 為 `KEEP_COST_GATE_BLOCKED`。
  - 正確做法是啟用 bounded learning lane，把 rejects 持續 materialize -> markout -> review，只對正向 side-cell 進入 demo probe authority review。

## Required Operator Authorization

下一步需要一次明確授權的 runtime activation wave：

1. Reconcile dirty runtime source tree，不覆蓋未確認 WIP。
2. Sync `trade-core` to current `origin/main` containing `2c4f524f...`.
3. Run activation preflight from synced source.
4. Install/enable `cost_gate_learning_lane_cron.sh`.
5. Enable materializer append path after reviewing ledger path and disk boundary.
6. If engine hot-path writer is also desired, set runtime env and restart through approved restart path.
7. Observe `reject_materializer_latest.json`, `probe_ledger.jsonl`, `outcome_refresh_latest.json`, and `blocked_outcome_review_latest.json` over 24-72h.

## Boundary

No runtime source sync, no crontab edit, no env edit, no deploy/rebuild/restart, no ledger append, no PG write/schema migration, no Bybit private/signed/trading call, no writer enablement, no order authority, and no main Cost Gate lowering were performed.
