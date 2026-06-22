# Sealed Horizon Operator Review Artifact

## 結論

v393 新增 `sealed_horizon_operator_review_v1` builder，補上 sealed-horizon bounded demo-probe preflight 的 operator-review 記錄缺口。

這不是下單授權，也不是 probe approval。它只把 operator 對某個 sealed candidate 的 preflight review decision 寫成可重跑 artifact，供 `sealed_horizon_bounded_demo_probe_preflight_v1` 嚴格消費。

## Source Changes

- `helper_scripts/research/cost_gate_learning_lane/sealed_horizon_operator_review.py`
  - 新增 artifact-only operator-review builder。
  - 輸入：`sealed_horizon_learning_evidence_v1`、optional `sealed_horizon_bounded_demo_probe_preflight_v1`。
  - 輸出：`sealed_horizon_operator_review_v1`。
  - `--decision defer` 預設只輸出 `PENDING_OPERATOR_REVIEW`。
  - `--decision reject` 輸出 `REJECTED_FOR_BOUNDED_DEMO_PROBE_PREFLIGHT`。
  - `--decision approve-preflight` 只有在 fresh aligned preflight、non-empty `--operator-id`、exact typed confirmation 全部成立時才輸出 `APPROVED_FOR_BOUNDED_DEMO_PROBE_PREFLIGHT`。
  - 即使 approved，也固定 `main_cost_gate_adjustment=NONE`、`probe_authority_granted=false`、`order_authority_granted=false`、`promotion_evidence=false`。

- `helper_scripts/research/tests/test_cost_gate_sealed_horizon_operator_review.py`
  - 覆蓋 defer artifact 不會讓 preflight 通過 operator gate。
  - 覆蓋 exact approval 只關閉 operator-review gate；production learning lane 仍可單獨 block。
  - 覆蓋 wrong typed confirm、mismatched preflight、authority-granting input fail closed。

- `helper_scripts/SCRIPT_INDEX.md`
  - 登記新 script、CLI、硬邊界。

## Profitability Relevance

這一步不是「再算一次」，而是把盈利路徑的下一個人工 gate 變成可審核資料面。

當前 leading path 仍是 `ma_crossover|BTCUSDT|Sell@240m`。它已有 sealed blocked-outcome evidence，但不能靠文字敘述翻越 Cost Gate；必須經過：

1. operator review artifact；
2. production learning lane 真的累積 ledger/outcome rows；
3. separate Rust-authority bounded demo-probe authorization。

v393 只完成第 1 項的 artifact 機制，不替 operator approve。

## Verification

- Mac py_compile passed.
- Mac focused operator-review/preflight pytest：`9 passed`.
- Mac related Cost Gate/profitability/alpha/worklist suite：`79 passed`.
- Mac `git diff --check` passed.
- Linux `trade-core` fast-forwarded source to `5622aba7`.
- Linux py_compile passed.
- Linux same related suite：`79 passed`.

Linux artifact smoke:

- pending review JSON：`/tmp/openclaw/profitability_refresh/20260622T031320Z/operator_review_v393/sealed_horizon_operator_review_latest.json`
- pending review sha256：`06ab3827c5e663f91de35592cbf770af70f591ae3ee3015e6bad3a43af5fa0b1`
- pending review status：`PENDING_OPERATOR_REVIEW`
- typed confirm expected：`approve_sealed_horizon_preflight:ma_crossover|BTCUSDT|Sell:240`
- preflight recheck JSON：`/tmp/openclaw/profitability_refresh/20260622T031320Z/operator_review_v393/sealed_horizon_probe_preflight_with_pending_review_aligned_decision.json`
- preflight recheck sha256：`6441cada5a55e73e5132c5f9cf9f1fee4a3690fcf48698824d9b6e19e6fd8773`
- preflight recheck status：`OPERATOR_REVIEW_AND_PRODUCTION_LEARNING_LANE_REQUIRED`
- remaining blocking gates：`operator_sealed_horizon_review_recorded`, `production_learning_lane_accumulating`

## Boundary

- No PG write/schema migration.
- No Bybit private/signed/trading call.
- No deploy/rebuild/restart.
- No env/auth/risk/order/strategy/runtime mutation.
- No Cost Gate lowering.
- No probe/order authority.
- No promotion proof.

## Remaining Work

Operator can choose whether to approve this preflight by generating an approved review artifact with the exact typed confirmation. Even after that, the system still needs production learning-lane ledger/outcome accumulation before any separate bounded demo-probe authorization should be considered.
