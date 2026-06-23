# Bounded Probe Operator Authorization Contract

日期：2026-06-23
PM checkpoint：`545564d7`

## 結論

本輪把 bounded Demo probe 的最後一個危險淺 Interface 修掉了：`DEMO_LEARNING_PROBE_GRANTED` 不能再單獨讓 admission 放行。Rust engine 與 Python runtime adapter 現在都要求 `bounded_demo_probe_operator_authorization_v1` 子物件匹配後才會承認 future order authority。

這不是下單授權；目前 runtime plan 仍是 `order_authority=NOT_GRANTED`，writer/materializer 仍不會提交訂單。改動的價值是把未來「低風險翻越 Cost Gate」變成機器可檢查、可過期、可限量、可回放的合約。

## Source 改動

- `rust/openclaw_engine/src/demo_learning_lane.rs`
  - 新增 `BoundedProbeOperatorAuthorization`。
  - `DEMO_LEARNING_PROBE_GRANTED` 之後先驗證 authorization，再看 adapter enablement。
  - 缺失/錯誤授權返回 `OPERATOR_AUTHORIZATION_INVALID`。
- `helper_scripts/research/cost_gate_learning_lane/runtime_adapter.py`
  - 同步 Python runtime-control admission 合約。
- `rust/openclaw_engine/src/demo_learning_lane_tests.rs`
  - 覆蓋 missing / expired operator authorization。
- `helper_scripts/research/tests/test_cost_gate_learning_lane_policy.py`
  - 覆蓋 Python admission 的 missing / expired operator authorization。
  - 修正 activation preflight CLI smoke，使其不依賴 wall-clock 與開發工作樹 clean 狀態。

## Authorization Contract

future bounded Demo probe admission 必須同時滿足：

- `schema_version=bounded_demo_probe_operator_authorization_v1`
- `status=BOUNDED_DEMO_PROBE_AUTHORIZED`
- `authorization_id` / `operator_id` 非空
- `side_cell_key` 匹配本次 candidate
- `expires_at_utc` 存在、格式正確、未過期
- `authority_path_readiness_status=AUTHORITY_PATH_PATCH_READY_FOR_OPERATOR_REVIEW`
- `main_cost_gate_adjustment=NONE`
- `order_authority=DEMO_LEARNING_PROBE_GRANTED`
- `max_authorized_probe_orders` 大於 0 且覆蓋 candidate budget
- `probe_authority_granted=true`
- `order_authority_granted=true`
- `promotion_evidence=false`

## 盈利路徑

目前不應全局 lower Cost Gate。更可控的路徑是：

1. 用 blocked-signal / sealed-horizon / multi-horizon scorecard 找 side-cell/horizon alpha 候選。
2. 對單一候選發 bounded operator authorization，限制 side-cell、有效期、訂單數、notional、只允許 Demo。
3. 用 v423/v424 near-touch-or-skip placement 讓 probe 可產生 fill-backed learning data，而不是 deep passive no-touch。
4. 將 probe 的 fill/fee/slippage、order-to-fill lineage 與同 side-cell/horizon blocked controls 對齊。
5. 用 bounded result review 與 execution-realism review 判斷：
   - alpha 是否真存在；
   - 成本是否被 execution 吃掉；
   - 是擴大 edge、修入場/滑點、調整 horizon，還是封存該候選。

這條路徑的核心不是放寬主 Cost Gate，而是在 Cost Gate 外建立一個小額、可審計、能學習的真實市場標籤生成器。

## Verification

Mac:

- `PYTHONPATH=helper_scripts/research python3 -m pytest -q helper_scripts/research/tests/test_cost_gate_learning_lane_policy.py` -> 71 passed
- `python3 -m py_compile helper_scripts/research/cost_gate_learning_lane/runtime_adapter.py helper_scripts/research/tests/test_cost_gate_learning_lane_policy.py` -> passed
- `cargo test -p openclaw_engine demo_learning_lane --lib` from `srv/rust` -> 23 passed
- `cargo test -p openclaw_engine bounded_probe_near_touch --lib` from `srv/rust` -> 9 passed

Linux `trade-core` after ff-only sync to `545564d7`:

- `PYTHONPATH=helper_scripts/research python3 -m pytest -q helper_scripts/research/tests/test_cost_gate_learning_lane_policy.py` -> 71 passed
- `python3 -m py_compile helper_scripts/research/cost_gate_learning_lane/runtime_adapter.py helper_scripts/research/tests/test_cost_gate_learning_lane_policy.py` -> passed
- `/home/ncyu/.cargo/bin/cargo test -p openclaw_engine demo_learning_lane --lib` from `srv/rust` -> 23 passed

## Boundary

No CI was run. No PG query/write/schema migration, no Bybit private/signed/trading call, no deploy/rebuild/restart, no crontab/env/auth/risk/order/strategy mutation, no Cost Gate lowering, no active probe/order authority, and no promotion proof.
