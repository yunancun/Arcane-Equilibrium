# False-Negative Candidate Friction Scorecard

Date: 2026-06-24

## 結論

我沒有重跑 `P0-BOUNDED-PROBE-AUTHORIZATION` 的同一個 exact-confirm blocker。因為沒有新的 typed-confirm evidence，重跑會違反 anti-repeat。

本輪改推進一個安全的 source-only aggressive alpha checkpoint：新增 false-negative candidate friction scorecard。

## 新增內容

新增：

`helper_scripts/research/cost_gate_learning_lane/false_negative_candidate_friction_scorecard.py`

用途：

- 讀現有 false-negative candidates；
- 合併 bounded touchability / placement / authorization friction；
- 排序哪些 candidate 最值得下一步 review；
- 幫我們避免只盯著 AVAX，如果 AVAX exact-confirm 長期卡住，可以找到其他高 upside、低 friction 的路徑。

## 重要邊界

這個 scorecard 不會：

- 授權 probe/order；
- 產生 bounded authorization object；
- 降低 Cost Gate；
- 開 live；
- 呼叫 Bybit；
- 寫 PG；
- 改 runtime / crontab / service；
- 作 promotion proof。

`TYPED_CONFIRM_REQUIRED` 只會被標成 blocker，不會被當成已授權。

## Review 結果

PA/E2/E4 都做了 no-edit review。

E2/E4 一開始抓到兩個問題：

- `bybit_call_performed=true` 沒有被 fail-closed；
- placement artifact 裡 top-level candidate 與 nested candidate 若不一致，可能誤套 friction。

這兩個都已修，並補 regression tests。

本地驗證：

- scorecard focused tests：`9 passed`
- adjacent bounded helper suite：`60 passed`
- broader bounded helper suite：`67 passed`
- alpha/profitability/worklist suite：`108 passed`
- `py_compile` passed
- `git diff --check` passed
- Mac 沒有 runtime artifacts 的 smoke 正確 fail-closed，所有 authority flags 都是 false。
- Linux source 已同步到 `68aaa896`，Linux canonical `/tmp/openclaw` artifact-only smoke 成功：
  - status: `FALSE_NEGATIVE_CANDIDATE_FRICTION_SCORECARD_READY`
  - top: `grid_trading|AVAXUSDT|Sell`
  - next action: `exact_bounded_demo_typed_confirm_required_or_select_next_candidate`
  - ranked candidates: `11`
  - all authority / proof flags: false

## 目前狀態

`P0-BOUNDED-PROBE-AUTHORIZATION` 仍然卡在 exact typed-confirm，沒有被繞過。

這輪狀態是 `DONE_WITH_CONCERNS`：source-only scorecard 完成、已 push、已 Linux sync、已 canonical artifact-only smoke；concern 是它必須維持在 triage/review 層，不能接入 runtime admission 或當成 promotion proof。
