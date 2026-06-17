# PHASE 0 AUTH-1 全封（live-write capability token）— E1 IMPL

- 日期：2026-06-17 · 角色：E1 · 狀態：IMPL DONE（待 E2）
- spec：`docs/execution_plan/2026-06-17--intelligent-param-adjusting-agent-master-spec.md` §0.1–§0.9
- SCOPE：PHASE 0 ONLY（未建 Phase 1-3）

## 任務摘要
無 agent 來源路徑、無 direct socket 能在缺 5-gate 下改 live RiskConfig（或任何 live-affecting
旋鈕）。5-gate 決策權威留 Python；Python 過門後鑄短 TTL、單次 nonce、綁操作的 capability
token；Rust 在 dispatch 唯一 chokepoint 對「engine==live 的 state-mutator」強制驗 token，
fail-closed。Rust 是 enforcer 非 authorizer。demo/paper 完全不變。

## 修改清單
**RUST**（5 檔）
- 新 `rust/openclaw_engine/src/ipc_server/live_authz.rs`（662 行）：`verify_live_authz_token`
  （常數時間 `Mac::verify_slice`，非 `==`）／`canonical_hash_for`（patch 類只 hash patch；
  非 patch 類 hash「params \ {token三欄,engine}」）／`canonicalize`+`canonical_bytes`（決定性序列化）／
  `NonceLedger`（`std::sync::Mutex<HashMap<nonce,ts>>`，lazy TTL 驅逐，`MAX_NONCE_LEDGER=10_000`）／
  `nonce_ledger()`（`OnceLock` singleton）／`LIVE_WRITE_METHODS`（13 method allowlist）／
  `requires_live_authz` / `check_live_authz`（chokepoint 核心）／`LiveAuthzReject`（5 reason code）。
  含 15 個 inline test（T12 fixture / 跨 method+跨 patch 重用 / nonce replay / TTL 邊界 / ledger 驅逐+滿）。
- `dispatch.rs`：`match method` 前插 chokepoint（engine resolve 鏡像下游 arm；fail-closed +
  V014 config_reject row source=direct_socket + `ERR_INVALID_REQUEST`）。
- `handlers_config.rs`：刪 :152-164 risk/live warn!-only block（MED-1 fail-open 移除）；保留 V014 config_patch INSERT。
- `mod.rs`：`mod live_authz;`。
- `tests/config.rs`：collateral 修 `test_p2_patch_risk_config_engine_routing`（原送無 token live
  patch → 現鑄 byte-equal token；env set+remove）。

**PYTHON**（3 source + 2 test）
- 新 `app/live_patch_token.py`（207 行）：`mint_live_authz_token` / `canonical_json` /
  `canonical_patch_hash` / `_rust_serde_float_str`（ryu mirror）/ `_read_secret`（fail-closed raise）。
- `app/risk_routes.py`：3 model 加 `engine` 欄+validator{paper,demo,live}；`_require_live_gates_if_live`
  helper（鏡像既有 5-gate body）；`_write_config_reject_audit`（V014 fire-and-forget）；
  `_patch_live_with_token`（共用 mint+attach+IPC helper）；`/config/global`+`/config/category` live 分支
  走 direct-ipc+token；`/agent-adjust` engine=live → 403 + audit（先於 gate/mint 短路）；
  **`update_per_engine_global_config` live 分支補 mint token**（防 chokepoint self-deadlock 唯一合法路徑）。
- `helper_scripts/canary/g2_03_bind_helper.py`：`cmd_apply --engine-mode live` → exit 2 + 指引走 HTTP 控制面。
- 新 `tests/test_live_patch_token_phase0.py`（14 test）+ 改 `tests/test_risk_routes_live_config_gate.py`（補 token env）。

**DOC**：`docs/architecture/singleton-registry.md` §2.7 登記 NonceLedger。

## T12 跨語言 interop 結果：byte-identical（未用 Rust-led fallback）
naive `json.dumps` 對 |x|<1e-4 與 Rust `serde_json`(ryu) 分歧（Python `1e-07`/`1e-05`/`2e-05` vs
Rust `1e-7`/十進位 `0.00001`/`0.00002`；科學記號門檻 + 指數零填充雙重差異）。解 = Python
`_rust_serde_float_str` 鏡像 ryu shortest（取 repr shortest 數字 + 套 ryu 格式：e10∈[-5,16) 定點、
否則科學記號無零填充、保 -0.0）。對 **225,000+ 個 f64**（隨機 bit pattern / subnormal / 指數門檻 /
十進位刻度）sweep 驗 **0 mismatch**。Rust fixture sha256 常數嵌入 Python test 逐一斷言相符。
mutation bite：把 mirror 換 naive repr → T12 紅（`1e-07` vs `1e-7`）→ 還原綠。**故 minter 必用
此 mirror 非 json.dumps**（已在 canonical_json 落實）。

## LIVE_WRITE_METHODS allowlist（13 method，grep dispatch.rs 親證）
`patch_risk_config, update_risk_config, force_governor_tier_looser, force_governor_tier_tighter,
set_dynamic_risk_enabled, restore_exit_config_defaults, reset_drawdown_baseline,
clear_consecutive_losses, set_strategy_active, update_strategy_params, pause_paper, resume_paper,
reset_paper_state`。唯讀 method（get_* / query_* / governance.get_*/is_authorized/list_leases）豁免。
平倉/下單面（close_all_positions/cancel_all_orders/close_position/submit_paper_order）OUT-OF-SCOPE
（lease/order authority 既有治理，handle_paper_cmd 只送 PipelineCommand 不改 RiskConfig）。

## 治理對照（spec §0.9）
- 硬邊界 0 觸碰（live_execution_allowed/max_retries/system_mode/authorization.json）— grep 自證。
- 5-gate 權威留 Python；Rust 只新增 enforcer。原則 #1 強化（單一 chokepoint）／#4 agent→live 硬拒
  403／#6 全失敗 fail-closed／#8 每 reject 落 V014 row。
- 無新 migration（復用 V014，config_reject 是表設計預留值，V014:21）。無新 flag（移除 fail-open）。
- kill-switch：撤 OPENCLAW_LIVE_PATCH_SECRET → Python mint raise + Rust verify fail = 全 live patch fail-closed。
- 跨平台：新碼 0 hardcoded user path（grep 自證）。NonceLedger singleton 已登記 §2.7。

## 驗證（誠實）
- Rust：`cargo build -p openclaw_engine` OK（僅 3 pre-existing warning，非我碼）。
  `cargo test -p openclaw_engine --lib` = **3932 passed / 0 failed / 1 ignored**（含 15 新 live_authz）。
- Python（mac_dev venv 3.12）：5 檔 60 test 全綠（14 新 Phase0 + 8 live-config-gate 含補 token +
  38 鄰近 risk 零回歸）。
- demo/paper byte-unchanged：chokepoint 只 engine=="live" 為真；既有 demo strategy/patch test 全綠。
- g2_03：live apply exit 2、demo apply 過 live 守衛續走既有 qc-report 檢查。

## 不確定之處 / 偏差（E2/E3 review 重點）
- **U-P0-3 engine-skew（偏差於 spec，已釘死）**：spec §0.2 說 gate 一律 `unwrap_or("paper")`「與
  arm 同源」，但 grep 證下游 arm 有兩條路：patch_risk_config 走 `select(unwrap_or("paper"))`；
  其餘 11 個 LIVE_WRITE_METHODS 走 `extract_engine_tx`（缺 engine → `primary()` = live>demo>paper）。
  production Python 實證 pause_paper/resume_paper/reset_paper_state/clear_consecutive_losses 都
  **不傳 engine**。若 gate 一律 unwrap_or paper，這些 method 在 live-running 引擎被 arm 路由到
  LIVE 而 gate 判 paper = 繞過。最小安全解 = chokepoint 對非-patch_risk_config method 缺 engine 時
  用 `cmd_channels.primary_label()` 解 effective engine（與 arm 鏡像）。**E2 請對抗測試「缺 engine
  參數的 extract_engine_tx LIVE_WRITE_METHOD 在 live-running 引擎」確認 gate 與 arm 同步**。
- **過度收緊副作用**：上述修法使「live-running 引擎上、缺 engine 參數、走 extract_engine_tx 的
  LIVE_WRITE_METHOD」需 token。今天 Python 這些呼叫都無 token → 在 live-running 引擎會被拒。但
  這些是 paper-control 語意呼叫（pause_paper 等），在 live-running 引擎走 primary()=live 本就語意
  可疑。**E3 確認此非破合法 operator paper-control 流程**（建議 caller 顯式傳 engine="paper"/"demo"）。
- **audit fail-soft（spec §0.4 PARTIAL）**：Phase 0 維持 config_reject/config_patch fire-and-forget；
  commit↔audit 同步硬綁是 Phase 2 要求。
- **dispatch.rs 853 行**（>800 review 線，未破 2000 cap）：chokepoint 加在已龐大中央 router；拆分
  out-of-scope。

## Operator 下一步
- E2 對抗審查（agent+live reject / 跨 method+跨 patch 重用 / nonce replay / engine skew / U-P0-3）。
- E4 Linux 實證（OWED）：真 engine hot-reload + 真 PG config_reject/config_patch 落 row + T12 跨語言
  在 Linux build 再證 + T10/T11/T13 真 engine 跑。
- 部署需設 `OPENCLAW_LIVE_PATCH_SECRET`（獨立檔 chmod 600，**絕不**等於 IPC HMAC secret 檔）；
  Python 與 Rust 讀同一 env/檔。未設則全 live patch fail-closed（kill-switch）。
- 不直接 commit（PM 統一）。
