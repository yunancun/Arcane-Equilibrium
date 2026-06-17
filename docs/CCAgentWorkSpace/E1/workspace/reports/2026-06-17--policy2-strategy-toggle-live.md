# POLICY-2 — flag-gated 5-gate live strategy toggle（E1 IMPL，待 E2）

- 日期：2026-06-17 · 角色：E1 · 鏈：E1→E2→E4→PM（未 commit）
- 設計來源：`docs/execution_plan/2026-06-17--intelligent-param-adjusting-agent-master-spec.md`
  + design JSON `design.policy_fix_strategy_toggle`（wcqhti681.output）
- 依賴：已部署的 Phase-0 `live_patch_token`（`call_params_with_token` minter）+ Rust dispatch
  chokepoint（`live_authz.rs` 對 13 個 `LIVE_WRITE_METHODS`@engine==live 強制驗 token）。
  **POLICY-2 純 Python，0 Rust 改。**

## 任務摘要
為策略 activate/pause/stop 路由新增「旗標控管 + 完整 5-gate」的 live 啟停分支，
demo 路徑保持 bit-identical。live 啟停走純 Rust IPC（`set_strategy_active{engine:live}`），
不碰 Python ORCHESTRATOR 狀態；`set_strategy_active` 已在 Phase-0 allowlist，Rust chokepoint
自驗 token。

## 修改清單
- `app/strategy_write_routes.py`（+~110 行）：
  1. 新 `_strategy_toggle_live_enabled()` — 讀 flag `OPENCLAW_STRATEGY_TOGGLE_LIVE_MODE`，
     只認字面 `"1"`（鏡像既有 `OPENCLAW_EDGE_RELOAD` env-gate 慣例），default-OFF。
  2. 新 `_sync_strategy_active_live(actor, name, active)` — 鏡像 `toggle_dynamic_risk`(:72-142)：
     `all_five_live_gates_ok(actor, require_authz=True)` → fail 拋 409 `live_gate_failed`；pass
     `call_params_with_token("set_strategy_active", {strategy_name, active, engine:"live"})` + IPC。
     **不**呼 `ORCHESTRATOR`（live 啟停 = 純 Rust 權威）。
  3. 新 `_resolve_toggle_engine(request)` — 從 optional body 解析 engine（default `"demo"`）：
     demo/無 engine→`"demo"`；engine=live + flag-OFF→**409 `live_strategy_toggle_disabled`
     fail-loud**（絕不靜默降級 demo）；engine=live + flag-ON→`"live"`；其他值→400。
  4. `activate_strategy` / `pause_strategy` / `stop_strategy` 各加 `request: Request = None`，
     在 `_require_strategy_write` + name-validate 後呼 `_resolve_toggle_engine`；engine=="live"
     走 `_sync_strategy_active_live`（跳過 ORCHESTRATOR），否則維持既有 demo 行為。
  - **demo helper `_sync_strategy_active`（engine="demo" 寫死）完全未動**（surgical）。
- `tests/test_strategy_toggle_live_policy2.py`（新檔，11 test）— TP2-1..8 全覆蓋。

## 關鍵設計決策
- **`request: Request = None`（非無 default）**：FastAPI 對型別為 `Request` 的參數恆注入真實
  Request（已實測），default 值不影響 HTTP routing；None 只出現在直呼 handler 的單元測試
  路徑（`test_phase2_strategy_routes_coverage.py` 以 `(name, actor=...)` 直呼），`_resolve_toggle_engine(None)`
  → demo → 既有 coverage 測試 byte-identical 不破。此選擇避免改動 wave 外的測試檔（最小影響）。
- **engine 集合限 demo|live**：原 demo helper 寫死 demo，POLICY-2 只加 live；paper 啟停不屬此面
  （避免擴大 scope），其他值 400。
- **live 分支 fail-loud 而非 fire-and-forget**：與 demo helper（fire-and-forget warn）不同，
  live 5-gate 失敗 / mint raise 必上拋（409 / 500），杜絕「以為改 live 實則沒改 / 改了 demo」。

## 治理對照
- 硬約束：未碰 `max_retries` / `live_execution_allowed` / `execution_authority` / `system_mode`
  / authorization.json 簽署路徑（5-gate 權威仍在 Python `live_preflight`）。grep 自證 0 命中。
- CLAUDE §四：live 須完整 5-gate（strategy:write scope 單獨不足，與 toggle_dynamic_risk 同級）；
  LiveDemo/Live 不降級。原則 #1 單一寫入口（live 啟停集中走 Rust chokepoint）/ #2 讀寫分離
  / #4 不繞風控（live 須 5-gate）/ #6 失敗收縮（全 fail-closed / fail-loud）。
- 無新 migration、無新 secret、1 新 flag（default-OFF）。flag-OFF = bit-identical（已測）。
- 新 singleton：無（minter 無狀態；唯一 mutable singleton NonceLedger 屬 Phase-0 Rust 已登記）。
- 跨平台：0 hardcoded user path（grep 自證）。注釋中文為主（bilingual-comment-style）。
- 檔案 409 行（< 800 review 門檻）。

## 測試與結果（Mac, venvs/mac_dev py3.12, fastapi 0.136）
- 新 `test_strategy_toggle_live_policy2.py`：**11 passed**。覆蓋 TP2-1（flag-OFF demo
  bit-identical）/ 1b（無 engine→demo, direct-call+空 body）/ 2（flag-OFF live→409 fail-loud,
  0 mutation）/ 2b（三路由皆 fail-loud 不降級）/ 3（flag-ON demo 仍 demo, 不走 5-gate）/
  4（flag-ON live 5-gate pass→鑄 token + IPC engine=live）/ 5（flag-ON live 缺 5-gate→409
  live_gate_failed, 永不 mint/IPC）/ 6（strategy:write scope 單獨不足以授權 live）/
  7（live 分支恆鑄 token, =TP2-7 Phase-0 chokepoint 前提）/ 7b（撤 secret kill-switch→500
  fail-closed, 不發無 token live IPC）/ 8（live toggle 不變動 ORCHESTRATOR）。
- 回歸：`test_live_authz_caller_retrofit_phase0` + `test_phase2_strategy_routes_coverage` +
  `test_phase2_routes` 合計 **74 passed, 0 failed**（demo 路徑 byte-identical）。
- **mutation A/B 雙證**：(A) flag-OFF live 改成靜默 `return "demo"` → fail-loud 測試紅(2)；
  (B) live 分支加 `ORCHESTRATOR.activate_strategy` → isolation 測試紅(1)；還原皆綠。
- grep 證 Phase-0 前提：`set_strategy_active` ∈ `rust/.../live_authz.rs:63` LIVE_WRITE_METHODS
  → 部署中的 Rust chokepoint 自驗 token，POLICY-2 確不需 Rust 改。

## 不確定之處 / 偏差
- 無設計偏差。design 對 activate/pause/stop 取 engine 的 wire 方式未明指（這些是 path-param
  路由，原本無 body）；我選「optional JSON body 的 engine 欄 + request:Request=None」以同時滿足
  HTTP 與既有直呼測試，已實測兩路徑皆正確（小決策，已註明理由）。
- Mac mock pytest 不驗 Rust chokepoint 真實 enforcement 與 demo hot-path 語意；TP2-7 的真實
  end-to-end（無 token live IPC 被 Rust 拒）由 Phase-0 Rust live_authz unit test 已釘死，
  本檔以「Python live 分支恆鑄 token」結構斷言佐證。

## Operator 下一步 / OWED
- E2 對抗審（flag-OFF+live 409 fail-loud / flag-ON+live 缺 5-gate / 跨 active 值 token /
  ORCHESTRATOR 隔離 / demo bit-identical）。
- E4 Linux 真 engine 實證：flag-ON live toggle 經 Rust chokepoint 真驗 token；demo 路徑
  hot-path 不變；flag-OFF default = 既有行為。
- 激活（operator-gated）：`OPENCLAW_STRATEGY_TOGGLE_LIVE_MODE=1` 才開放 live 策略啟停面。
