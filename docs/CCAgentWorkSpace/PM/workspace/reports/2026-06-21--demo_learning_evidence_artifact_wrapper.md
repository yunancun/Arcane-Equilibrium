# Demo Learning Evidence Artifact Wrapper

## 結論

新增 `helper_scripts/cron/demo_learning_evidence_audit_cron.sh`，把 `demo_learning_evidence_audit.py` 從手動診斷升級成可排程的只讀 evidence heartbeat。

這不是下單權、不是 learning writer activation、不是 Cost Gate 放寬。它的用途是讓 demo 是否真正「在學」變成持續可查的 artifact：PG 是否仍有 Cost Gate rejects、最近 context 是否只是 observation-only、learning ledger 是否有 rows、blocked outcome review 是否出現 operator-review candidate。

## 變更

- 新 wrapper 寫入：
  - `$OPENCLAW_DATA_DIR/demo_learning_evidence/demo_learning_evidence_audit_<stamp>.{md,json}`
  - `$OPENCLAW_DATA_DIR/demo_learning_evidence/demo_learning_evidence_audit_latest.{md,json}`
  - `$OPENCLAW_DATA_DIR/logs/demo_learning_evidence_audit.log`
  - `$OPENCLAW_DATA_DIR/logs/demo_learning_evidence_audit_cron.log`
  - `$OPENCLAW_DATA_DIR/cron_heartbeat/demo_learning_evidence_audit.last_fire`
- 支援 operator knobs：
  - `OPENCLAW_DEMO_LEARNING_EVIDENCE_ENGINE_MODES`
  - `OPENCLAW_DEMO_LEARNING_EVIDENCE_LOOKBACK_HOURS`
  - `OPENCLAW_DEMO_LEARNING_EVIDENCE_TOP_LIMIT`
  - `OPENCLAW_DEMO_LEARNING_EVIDENCE_EXPECTED_HEAD`
  - runtime env / PID / `/proc/<pid>/environ` / auto-detect / writer-required preflight knobs
- 新增靜態測試 `helper_scripts/cron/tests/test_demo_learning_evidence_audit_cron_static.py`，鎖住只讀 PG、artifact-only、無交易/重啟/ledger append 邊界。

## 判斷

這一步對齊 operator 的方向：demo 的價值不只是受控下單，而是持續累積「被擋信號 -> 後續市場走勢 -> 是否該小額探索」的學習證據。

如果 demo 又很久不下單，下一次不必先猜測策略是否死掉；先看 `demo_learning_evidence_audit_latest.json` 和 status log，就能區分：

- 只有 observation telemetry，尚無 actionable candidate/reject；
- PG 已記錄 Cost Gate rejects，但 learning lane ledger 沒累積；
- admission rows 已有，但 outcome refresh 沒跑；
- blocked outcomes 正在累積，但尚未達 review threshold；
- 已出現需要 operator review 的 bounded demo-probe candidate。

## 邊界

- Read-only PG SELECT only。
- 只寫本地 artifact/status/heartbeat/lock/log。
- 不安裝 cron。
- 不 append `probe_ledger.jsonl`。
- 不啟用 `OPENCLAW_DEMO_LEARNING_LANE_WRITER`。
- 不 deploy / rebuild / restart。
- 不連 Bybit private/signed/trading API。
- 不改 auth / risk / strategy / runtime config。
- 不降低 main Cost Gate。
- 不授權 demo order。

## 驗證

- `bash -n helper_scripts/cron/demo_learning_evidence_audit_cron.sh`：PASS
- `python3 -m pytest helper_scripts/cron/tests/test_demo_learning_evidence_audit_cron_static.py -q`：6 passed
- `python3 -m pytest --import-mode=importlib helper_scripts/cron/tests/test_demo_learning_evidence_audit_cron_static.py helper_scripts/db/audit/test_demo_learning_evidence_audit.py helper_scripts/db/audit/test_demo_order_stall_audit.py helper_scripts/research/tests/test_cost_gate_learning_lane_policy.py -q`：75 passed
- `python3 -m pytest helper_scripts/db/audit/test_demo_learning_evidence_audit.py helper_scripts/db/audit/test_demo_order_stall_audit.py -q`：16 passed
- `python3 -m pytest helper_scripts/research/tests/test_cost_gate_learning_lane_policy.py -q`：53 passed

普通 pytest 混跑 `helper_scripts/cron/tests` 和 `helper_scripts/research/tests` 會遇到既有 package collision：兩邊都有 `tests/__init__.py`，pytest 以頂層 `tests.*` 收集時會找錯 package。這不是本 wrapper 行為失敗；`--import-mode=importlib` 合併 smoke 已通過。
