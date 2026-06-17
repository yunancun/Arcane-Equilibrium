# E1 POLICY-1 — reset-drawdown 5-gate + operator_override（IMPL 待 E2）

- 日期：2026-06-17
- Wave：POLICY-1（與 POLICY-2 / Phase-1 檔零重疊並行）
- 依賴：已 deployed Phase-0 `live_patch_token` + Rust dispatch chokepoint（無需改 Rust）
- 狀態：IMPL 完成，Mac 自測綠，**未 commit**（強制鏈 E1→E2→E4→PM）

## 任務摘要

把 `POST /api/v1/paper/risk/reset-drawdown-baseline {engine:live}` 從「operator-role-only
即鑄 capability token」收緊為與 live RiskConfig 寫入同級的完整 5-gate，並提供顯式
`operator_override` 路徑供 signed-auth 結構不可達場景（halt-recovery）使用。純 Python。

## 兩個 build-blocking GREP 裁決（POLICY-1 uncertainties）

1. **per-gate API 是否已存在**：`live_preflight.all_five_live_gates_ok(actor, *, require_authz)`
   在 `require_authz=False` 時恰好依序評估 Gate 1 (operator-role) / Gate 2
   (global_mode==live_reserved) / Gate 3 (OPENCLAW_ALLOW_MAINNET，僅 Mainnet) / Gate 4
   (secret slot)，**跳過** Gate 5 (signed authorization.json)。故新 helper
   `four_gates_minus_authz_ok(actor)` = 薄委派 `all_five_live_gates_ok(require_authz=False)`，
   **零新增、零放寬** gate 邏輯（單一真相，drift 結構上不可能）。

2. **halt-recovery 走 route 還是 client**：`live_halt_recovery._try_ipc_reset_live`(:194)
   **直接** `client.reset_drawdown_baseline("live")` 繞過 FastAPI route。其
   `approve_live_halt_recovery(actor_id)`(:291) operator-approved 入口即 override 授權。
   因此：(a) 新 route-level 5-gate 結構上卡不到 halt-recovery（不 deadlock）；
   (b) client 方法簽名無 `operator_override` 欄（對 engine=live 無條件鑄 token），
   halt-recovery **無需**改傳旗標——只在 :194 補中文註釋鎖死「故意繞 route，勿改走 route」。

## 修改清單

| 檔 | 改動 |
|---|---|
| `app/live_preflight.py` | +25：新 `four_gates_minus_authz_ok(actor)` 薄 helper（委派 `all_five_live_gates_ok(require_authz=False)`，docstring 說明只豁免第 5 門 signed-auth、前 4 門不放寬） |
| `app/risk_routes.py` | +101/-4：(1) `ResetDrawdownBaselineRequest` 加 `operator_override: bool=False`；(2) route engine=="live" 授權分支（not override→5-gate require_authz=True；override→four_gates_minus_authz_ok），fail→409 live_gate_failed；(3) `_record_reset_drawdown_audit` 加 `override/bypassed_gate/caller` kwargs + 分支寫 distinct/普通審計；(4) route 末尾 thread `is_live_override` 進審計 |
| `app/live_halt_recovery.py` | +10：`_try_ipc_reset_live` 補中文註釋（為何故意繞 route、勿改走 route 否則重引 deadlock） |
| `tests/test_reset_drawdown_live_gate_policy1.py` | 新檔 13 test（TP1-1..8 + override-on-demo-inert + four_gates 委派×2 + IPC-fail-500） |

## 關鍵 diff（授權分支）

route engine=="live"：not override → `all_five_live_gates_ok(require_authz=True)`，fail→409；
override → `four_gates_minus_authz_ok(actor)`，fail→409。operator-role gate 在 route :676
先於此 live 分支，故 override **永不繞 operator-role**（非 operator 拿 403）。

審計：override=True → what 標 `"...OPERATOR_OVERRIDE, authz-gate-bypassed"` +
new_value `{override:true, bypassed_gate:"signed_auth", caller:"manual_override"}`；
override=False → 普通 row（不注入 override 欄，與上線前 byte-identical）。

## 治理對照

- **硬邊界**：0 觸碰 max_retries / live_execution_allowed / execution_authority；
  不 mutate system_mode（只讀現有 snapshot/authorization 驗證碼，皆 pre-existing）。grep 自證。
- **5-gate 0 觸碰**：未改 `all_five_live_gates_ok` 任何 gate 邏輯；新 helper 純委派。
- **Demo 放寬 / Live 收緊**：demo/paper 不觸 live 分支（維持現行無 5-gate、無 token）。
- **Root #8 可審計**：override row 與普通 row 可按 `new_value.override` 分離查詢。
- **無新 flag / 無新 migration / 無新 secret / 無新 singleton**（符 PA spec §POLICY-1.6）。
- **跨平台**：0 hardcoded `/home/ncyu`、`/Users/ncyu`（grep 自證）。
- **註釋規範**：新註釋中文為主，技術識別符英文保留。

## 測試與結果（Mac, venvs/mac_dev/bin/python 3.12.13）

- 新 POLICY-1 suite：**13 passed**。
- 既有相關 suite（reset_drawdown_route + risk_routes_live_config_gate + live_patch_token_phase0
  + live_authz_caller_retrofit_phase0 + 本新檔）合計 **57 passed**，零回歸。
- preflight/halt_recovery 相關（--ignore=tests/replay）**12 passed**。
- **Mutation A/B/C 三證**：
  - A：override 路徑跳過 4-gate enforcement → TP1-5 紅（DID NOT RAISE）。
  - B：default 路徑跳過 5-gate → TP1-1 紅。
  - C：`four_gates_minus_authz_ok` 改用 `require_authz=True` → 委派測試×2 紅。
  - 三者還原後全綠。
- `tests/replay/` 4 個 collection error = pre-existing `from program_code` import-path 問題
  （memory 已記錄，非本改動引入）。

## 偏差 / 不確定之處

- **PA spec §POLICY-1.5 偏差（已採最小安全解）**：spec 文字「`_try_ipc_reset_live` 改傳
  `operator_override=True`」與 client 方法簽名衝突（`reset_drawdown_baseline(engine)` 無此欄，
  且對 engine=live 無條件鑄 token）。裁決＝把 override-flag 授權點下沉到 route-only（manual
  路徑），halt-recovery 因繞 route 故旗標對它無意義；改以 :194 註釋鎖死繞 route 的理由。
  此與 spec §5「裁決：halt-recovery 直接走 client，其 operator-approval 即 override 授權；
  manual 路徑才需 route 層雙檢」一致。
- `_record_reset_drawdown_audit` 普通路徑（override=False）的 `new_value` 刻意**不**注入
  override 欄，保 demo/paper/普通 5-gated caller 審計 byte-identical；distinct 性靠 override
  路徑單方面標記達成。
- `ChangeRecord.new_value` 以 `json.dumps` 存為字串（PG text/jsonb column）——production 邏輯
  傳 dict 正確，test 以 `json.loads` 解回斷言。

## Operator / 下一步

1. **E2 對抗審查**：重點驗 override 繞 operator-role（403）/ 繞前 4 gate（409）/
   four_gates_minus_authz_ok 只豁免 signed-auth / 審計可區分。
2. **E4 Linux 真 engine 回歸**：override 路徑 halt-recovery 端到端（reset+unhalt 不被新
   5-gate 卡死）+ 真 PG change_audit_log override row 落地實證（按 new_value.override 查詢）。
3. 不直接 commit；等 E2→E4→PM 統一 commit + push。
