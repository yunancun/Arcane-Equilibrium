# Demo Learning Evidence Killboard Ingestion

## 結論

`alpha_discovery_throughput` 現在會讀取 `demo_learning_evidence_audit_latest.json`，並把 demo-learning composite evidence 帶入 `cost_gate_demo_learning_lane` blocker row。

這把上一批新增的 heartbeat 接進總覽層：alpha killboard 不再只看 cost-gate plan / ledger / learning-loop / historical review，也能看到最新 composite runtime diagnosis：PG 是否已記錄 Cost Gate rejects、recent context 是否只是 observation-only、learning ledger 是否沒有累積。

## 變更

- `runtime_runner.py`
  - 新增 `summarize_demo_learning_evidence_audit()`。
  - 讀 `<DATA>/demo_learning_evidence/demo_learning_evidence_audit_latest.json`。
  - 將 compact `demo_learning_evidence_*` fields 附到 `cost_gate_demo_learning_lane` detail。
- `discovery_loop.py`
  - `PG_REJECTS_RECORDED_LEARNING_LANE_NOT_ACCUMULATING` + empty ledger 會分類為：
    `demo_cost_gate_rejects_recorded_but_learning_lane_not_accumulating`
  - `OBSERVATION_TELEMETRY_ACTIVE_NO_ACTIONABLE_LEDGER` 會分類為：
    `demo_observation_telemetry_active_no_actionable_reject_evidence`
  - 最新 composite runtime evidence 優先於 historical-only review，避免歷史候選蓋過當前 demo 狀態。
- `test_alpha_discovery_throughput.py`
  - 新增 PG-reject gap fixture。
  - 新增 observation-only fixture。

## 為何重要

我們現在的方向不是把 demo 只當作保守下單機，而是讓它變成會學習的資料面。

這次改動使 killboard 能區分兩個完全不同的狀態：

- 有大量 PG Cost Gate rejects，但 learning ledger 沒累積：下一步是 operator-gated bounded learning lane enablement。
- 最近只是 observation-only telemetry：下一步是等 candidate/reject 或查 candidate producer，不應誤判為可以 probe。

這直接降低「demo 很久沒下單」時的診斷噪音，並把學習閉環缺口放到 alpha-discovery 的同一張 killboard。

## 邊界

- Artifact-only ingestion。
- 不連 PG。
- 不連 Bybit。
- 不下單。
- 不 append ledger。
- 不啟 writer。
- 不安裝 cron。
- 不 deploy / rebuild / restart。
- 不改 auth / risk / strategy / runtime config。
- 不降低 main Cost Gate。
- 不授權 demo order。

## 驗證

- `python3 -m pytest helper_scripts/research/tests/test_alpha_discovery_throughput.py -q`：36 passed
- `python3 -m py_compile helper_scripts/research/alpha_discovery_throughput/runtime_runner.py helper_scripts/research/alpha_discovery_throughput/discovery_loop.py helper_scripts/research/tests/test_alpha_discovery_throughput.py`：PASS

下一步若 operator 批准 runtime 啟用，應先做 source/env/runtime 對齊，再安裝/啟用 heartbeat cron 與 bounded learning writer；本 report 不授權這些 runtime 動作。
