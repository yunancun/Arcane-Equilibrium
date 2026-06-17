# 本地智能調參下單 Agent 系統 — Master Implementation Spec

- **Author:** PA · **Date:** 2026-06-17 · **Base commit:** `0cf086c1`
- **Status:** design (read-only) → pending adversarial review (E3+CC+E2) → phased build+deploy
- **Driver:** operator 要求「完整的、本地具備智能、能透過 ML/DB/學習經驗/市場信號智能調整參數的下單 Agent 系統」

## Operator 決策（已鎖定）
1. **SCOPE = 全範圍含 live RiskConfig**（最終）— 不只策略參數。
2. **LIVE 自主度 = 人工促升閘**。demo 自主學習調參；任何到 live engine 的改動經 operator 確認的 promotion，永不自動套用 live。
3. **AUTH-1 先封（Phase 0）** 才允許任何 agent 路徑碰 RiskConfig。
4. **NEWS = 嚴格 corroborating-only**（Alpha Evidence Governance）：news/X 只能作 brain 的 context 輸入，永不可單獨觸發調參；每次調參必須能由 leak-free 量化證據獨立支撐（reject-path + test，非註釋）。

## 載重安全不變量（operator 旗標，不可協商，每 phase 內建）
Agent 在 operator 設定的 band **內**調整；**永不**放寬或移除 survival floors。survival 欄位永遠 operator-only 且在 P0/P1 denylist：
絕對 hard SL/TP 上限、max_position_size、max_total_exposure、max_leverage、daily_loss_cap、drawdown_max、liquidation buffer。
Agent 可在 operator band 內移動旋鈕（鏡像 `DynamicRiskSizer` clamp-cannot-widen，dynamic_risk_sizer.rs:42-99），但永不可改 band 本身、clamp、或任何 survival hard-limit。
→「全範圍含 live RiskConfig」= agent 調 **非生存** 風控旋鈕（cost-gate k〔k 上調=放寬 edge filter，視為 survival-class〕、holding-hours、regime 乘數、dynamic-stop 乘數）在 band 內；survival hard-limit 仍是 operator 的手。

## 復用的三個既有「腦」（不建第四個）
- **StrategistScheduler**（strategist_scheduler/）：LLM-judge 策略參數 tuner，demo（tune_target 寫死 Demo evaluate.rs:310），`promote_params_to_live` mod.rs:342 是已接但不自動呼的 method；只動 `agent_adjustable:true` 參數；±50% clamp + range + weight-sum=65 validate（mod.rs:402）；persist learning.strategist_applied_params。
- **claude_teacher DirectiveApplier**（claude_teacher/applier.rs）：P0/P1 denylist :200-218 + GovernanceCore veto + session-halt/daily-loss veto :342-347/:497-504 + 審計 learning.directive_executions :276；sink（strategy_ipc_impl.rs:11-24）刻意只 update_strategy_params+set_strategy_active，**結構上不能寫 RiskConfig**；DEFAULT-OFF。
- **DynamicRiskSizer**（dynamic_risk_sizer.rs）：in-path、live-enabled，從 realized-PnL Sharpe 在 band `[min,max]`+硬 clamp `[0.001,0.20]` 內調 global per_trade_risk_pct；UP 有 LCB 顯著性 gate、DOWN 不設限。

## AUTH-1 現狀（CC 已驗）
已封：per-engine route `update_per_engine_global_config`（risk_routes.py:710-748，engine==live 走 all_five_live_gates_ok）。
**仍開**：`POST /config/global`（:245）、`POST /config/category`（:286）、**`POST /agent-adjust`（:376，agent 來源路徑，無 engine、無 5-gate）**；加上 direct-socket 繞過（g2_03_bind_helper.py → Rust patch_risk_config engine=live，Rust 只 warn! 不擋，handlers_config.rs:152-164；IPC auth 僅 connection-level HMAC）。

---

## PHASE 0 — AUTH-1 全封（BUILD-READY，最先建）

**目標**：無 agent 來源路徑、無 direct socket 能在缺 5 gate 下改 **live** RiskConfig（或任何 live-affecting 旋鈕）；demo/paper 完全不變。Phase 1-3 觸 live 的硬前置。

**威脅模型（親 grep 證實的真實攻擊面，2026-06-17 @HEAD）**：
1. **Direct-socket**：任何持 `OPENCLAW_IPC_SECRET`（connection-level HMAC）的進程可開 socket、過 `__auth` 握手後**對任何 method 全開**（dispatch.rs:127 之後無 per-method authz），送 `patch_risk_config{engine:"live"}`；Rust 今天只 `warn!`（handlers_config.rs:157-164）不擋。`g2_03_bind_helper.py --engine-mode live`(:179,:262) 與 `edge_p2_flip_dry_run.py` 都已能走此路。
2. **IPC method 面**：除 `patch_risk_config` 外，`update_risk_config`/`force_governor_tier_looser`/`set_dynamic_risk_enabled` 等十餘個 mutator 經 `extract_engine_tx` resolve `engine:"live"` 後直改 live runtime（cost_gate_k/leverage/drawdown/hard_stop/governor tier 等），同樣無 token。
3. **Python route 面（已大半關，需補欄）**：三條開放 route（`/config/global`/`/config/category`/`/agent-adjust`）今天 client 不傳 engine → `_patch()`(risk_view_client.py:306) 送 `{patch, source}` 無 engine → Rust default `paper`（engine_routing.rs:97）→ **今天根本寫不到 live**。但 request model（GlobalConfigUpdate:122 / CategoryConfigUpdate:146 / AgentAdjustRequest:161）**無 engine 欄**，一旦 Phase 1-3 想透傳 engine 就缺 gate；Phase 0 補欄+gate 把這條未來路徑也鎖死。

**設計總綱**：5-gate 決策權威**留在 Python**（單一權威，符 CLAUDE §四「Rust execution_authority 是字串面非真機制」）；Python 過門後**鑄造短 TTL、單次、綁定操作內容的 capability token**；Rust 在 **dispatch 唯一 chokepoint** 對「engine==live 的 state-mutator method」強制驗 token，fail-closed。Rust 是 **enforcer 非 authorizer**。

---

### 0.1 Token 安全機制（HIGH-1 RESOLVED — 綁操作 + 單次 nonce）

舊 `verify_ipc_token`(connection.rs:52) 只 `HMAC(secret, ts.to_string())` → 跨 method/跨 patch 可重用、TTL 內可重放。**Phase 0 不改它**（connection-level handshake 保持），而是**新增**一個獨立的 per-request `live_authz_token`。

**Secret**（與 IPC HMAC secret 分離檔）：
- env：`OPENCLAW_LIVE_PATCH_SECRET`（直接值）或 `OPENCLAW_LIVE_PATCH_SECRET_FILE`（檔路徑）。Rust 用既有 `secret_env::var_or_file("OPENCLAW_LIVE_PATCH_SECRET")` 讀（secret_env.rs:12，已支援 `*_FILE` fallback）。
- 部署：獨立檔，`chmod 600`，**絕不**等於 IPC HMAC secret 檔。Python 與 Rust 讀同一檔/同一 env。
- **secret_env.rs 無權限檢查**（LOW finding 屬實）：Rust 啟動時若讀到 file-based secret 且檔權限寬於 600 → `warn!` 一行（不硬擋，避免 boot 崩；E3 review 此取捨）。

**Canonical patch hash（決定性序列化，Python 與 Rust 必須位元一致）**：
- 對「即將送給 Rust 的 `patch` JSON 物件」做 **RFC-8785-style 決定性序列化**：遞迴排序所有物件 key、無多餘空白（`separators=(",",":")`）、UTF-8、數字用 Python `json.dumps` 預設數值表示。Rust 端用 `serde_json::Value` + 自寫遞迴 canonicalizer（sort `Map` keys、緊湊輸出）對「收到的 `params["patch"]`」做同一序列化。
- `canonical_patch_hash = hex(SHA256(canonical_patch_bytes))`。
- **為何 hash patch 而非整個 params**：token 綁的是「這次要改什麼值」；engine/method/ts/nonce 另列入 bind-string。patch 一個 byte 不同 → hash 不同 → token 失效（防「過門改一個值，重放時偷換成另一個值」）。
- **數值表示風險（E1 必驗）**：Python `json.dumps` 與 Rust `serde_json` 對浮點的字串化可能不同（如 `0.03` vs `3e-2`）。**緩解**：Python minter 不自己序列化原始 body，而是**對已 remap、即將進 IPC 的最終 patch dict**（`_build_global_patch` / `_remap_*_to_rust` 的輸出，全是 Python float）做 canonical serialize；Rust 對「反序列化後再以 serde_json 重序列化的同一 patch」做 canonical serialize。E1 必須加一個 **round-trip 一致性測試**：Python 序列化 bytes == Rust 對同 JSON 反序列化後重序列化 bytes（用一組含浮點/巢狀/中文 key 的 fixture），否則整個機制失效。若浮點字串化無法位元對齊，降級方案=canonical 對「`serde_json::Value` 解析後的結構」算 hash 由 Rust 主導、Python 送原始 patch JSON 字串讓 Rust 算 hash（見 0.6 風險）。

**Bind-string**（token 簽的內容，欄位以 `\x1f` US 分隔避免歧義）：
```
bind = canonical_patch_hash ∥ 0x1f ∥ engine ∥ 0x1f ∥ method ∥ 0x1f ∥ ts ∥ 0x1f ∥ nonce
live_authz_token = hex(HMAC_SHA256(OPENCLAW_LIVE_PATCH_SECRET, bind))
```
- `engine`：必為 `"live"`（Phase 0 token 只為 live 鑄造；demo/paper 不需 token）。
- `method`：被授權的 IPC method 名（如 `"patch_risk_config"`）。token 綁 method → 過 patch_risk_config 門的 token 不能拿去過 update_risk_config。
- `ts`：鑄造時 Unix 秒（i64）。
- `nonce`：Python 生成的 128-bit 隨機 hex（`secrets.token_hex(16)`）。

**Wire format**（無需改 JSON-RPC 框架；token 三欄就是 `params` 的額外 key）：
```json
{"jsonrpc":"2.0","method":"patch_risk_config","id":1,
 "params":{"engine":"live","patch":{...},"source":"operator",
           "live_authz_token":"<hex>","live_authz_nonce":"<hex>","live_authz_ts":<int>}}
```
`EngineIPCClient.call(method, params)` 把 params 原樣放進 request（ipc_client.py:215-216），故 Python 只需在 params dict 多塞三 key，**不改 ipc_client / 不改握手**。

**TTL + nonce ledger（Rust 側）**：
- TTL = **25 秒**（≤30s 約束，留 5s 給 ts skew + 傳輸；mint→use 同機 <1s，25s 充裕）。`|now - ts| > 25` → 拒（理由 `token_expired`）。
- **單次 nonce ledger**：`NonceLedger { seen: Mutex<HashMap<String, i64>> }`（key=nonce hex，value=ts）。verify 成功且 `(now-ts)<=TTL` 後，**先檢查 nonce 不在 ledger**（在 → 拒 `nonce_replay`）→ 插入 → 才放行。
  - **驅逐**：每次插入順帶掃描並移除 `now - ts > TTL` 的舊條目（lazy eviction，避免背景 task）；ledger size 天然上界 = TTL 窗內的 live patch 次數（極小，~個位數）。設硬上界 `MAX_NONCE_LEDGER = 10_000`，超限時拒新 token（`nonce_ledger_full`）並 `error!`（DoS 安全閥；正常永不觸及）。
  - 放 `ipc_server` 模組級 singleton（`OnceLock<NonceLedger>` 或 main boot 建 `Arc` 傳入 dispatch）。**新 mutable singleton → 必登記 singleton authority table（CLAUDE §九）**。
- **常數時間比對**：復用 `hmac::Mac::verify_slice`（connection.rs 已用此 primitive 防時序攻擊），**不**用 `==` 比 hex 字串。新函數 `verify_live_authz_token(secret, bind_bytes, token_hex) -> bool`，內部 `HmacSha256::new_from_slice → update(bind_bytes) → verify_slice(hex::decode(token))`。

---

### 0.2 Rust 強制 chokepoint（HIGH-2 RESOLVED — 單一閘 + 全 mutator allowlist）

**chokepoint 位置裁決（親 grep）**：原 spec 寫「extract_engine_tx / engine-resolution 層」，但 grep 證實**沒有單一 resolution 函數**所有 live-write 都經過 —— `extract_engine_tx`(engine_routing.rs:252) 只服務 PipelineCommand 類 mutator，而 `patch_risk_config`/`update_risk_config`/`get_risk_config` 的 engine resolve 是**各 match arm 內聯**（dispatch.rs:421-425 等），用的是 `risk_stores.select(engine)` 另一條路。**唯一覆蓋全部 method 的點 = `dispatch_request` 的 `match method` 之前**（dispatch.rs:127 前，method 已解析、params 在手）。

**裁決：在 dispatch.rs:127 `match method {` 之前插入單一 live-write authz gate**：
```
（虛擬碼，E1 實作）
1. let engine = req.params.get("engine").and_then(as_str).unwrap_or("paper");  // 與各 arm 同源讀法
2. if engine == "live" && LIVE_WRITE_METHODS.contains(method) {
3.     // 取 token 三欄；缺任一 → reject(ERR_INVALID_REQUEST, "live_authz_token_required")
4.     // 算 canonical_patch_hash（patch 類 method 取 params["patch"]；非 patch 類見下）
5.     // 重建 bind-string（hash ∥ "live" ∥ method ∥ ts ∥ nonce）
6.     // TTL 檢查 → nonce ledger 檢查 → verify_live_authz_token
7.     // 任一失敗 → 寫 V014 config_reject 審計 row（見 0.4）+ return ERR_INVALID_REQUEST（fail-closed）
8. }
9. // 通過或非 live-write → 落入既有 match method（行為不變）
```
- **非-`patch` 類 mutator 的 hash 對象**：`update_risk_config`/`set_dynamic_risk_enabled` 等的可變內容不是 `params["patch"]` 而是 params 本身的旋鈕欄。裁決：對這類 method，`canonical_patch_hash` = canonical-serialize 整個 `params` 物件**但排除 token 三欄 + engine**（即 `params \ {live_authz_token, live_authz_nonce, live_authz_ts, engine}` 排序序列化後 SHA256）。Python minter 對應地對「即將送的 params（去 token 三欄、去 engine）」算 hash。`patch` 類則 hash 僅 `params["patch"]`（更窄、更精確）。**E1 用一個 helper `canonical_hash_for(method, params)` 統一兩分支**，Python/Rust 各一份對齊。
- **engine 讀法一致性**：gate 讀 engine 的方式必須與下游 match arm 完全一致（同 `params.get("engine").as_str().unwrap_or("paper")`），否則 gate 判 paper 而 arm 走 live = 繞過。E2 對抗測試必含「engine 欄型別怪異（數字/null/大小寫 LIVE）」確認 gate 與 arm 同步 fail-safe。

**`LIVE_WRITE_METHODS` allowlist 常數（dispatch.rs 模組頂，親 grep 全 mutator 列舉）**：
```
const LIVE_WRITE_METHODS: &[&str] = &[
    // RiskConfig / ConfigStore 寫
    "patch_risk_config",
    "update_risk_config",
    // governor / dynamic-risk runtime 寫
    "force_governor_tier_looser",
    "force_governor_tier_tighter",
    "set_dynamic_risk_enabled",
    // exit / drawdown / loss-counter runtime 寫
    "restore_exit_config_defaults",
    "reset_drawdown_baseline",
    "clear_consecutive_losses",
    // strategy 寫（engine:live 時）
    "set_strategy_active",
    "update_strategy_params",
    // pipeline 控制（engine:live 時改 live runtime 狀態）
    "pause_paper", "resume_paper", "reset_paper_state",
    // 註：close_all_positions / cancel_all_orders / close_position / submit_paper_order
    //     是「平倉/下單」面，屬 lease/order authority 既有治理，非 RiskConfig 面；
    //     Phase 0 SCOPE = 「改 live param/runtime config」。平倉路徑列為 OUT-OF-SCOPE
    //     但 E3 review 須確認它們不是另一條改 live param 的偽裝（grep 證 handle_paper_cmd
    //     只送 PipelineCommand::CloseAll 等，不改 RiskConfig）。
];
```
- **分類規則（E1/E3 共識）**：method 進 allowlist 的判準 = 「engine==live 時會改變 live 引擎的風控/策略/runtime 參數或開關狀態」。**唯讀 method**（`get_*` / `query_*` / `governance.get_*` / `governance.is_authorized` / `governance.list_leases`）**一律豁免**（不進 allowlist）。`reload_config`/`reload_edge_estimates`/`record_ai_usage`/`update_ai_budget_config`/`set_teacher_loop_enabled` 不直接寫 live RiskConfig，Phase 0 **不**納入（E3 確認；teacher loop 本身 DEFAULT-OFF 且其 sink 結構上不能寫 RiskConfig，見 spec §復用三腦）。
- **allowlist 維護紀律**：未來新增任何 IPC mutator method → 同步評估是否進 `LIVE_WRITE_METHODS`。CC review checklist 加一條：「新 IPC method 是否 live-affecting？是→必進 allowlist」。

---

### 0.3 Python 控制面（封三條 route + 補 engine 欄 + token minter）

**新 token minter 模組** `app/live_patch_token.py`（新檔，與 live_preflight.py 同目錄）：
- `def mint_live_authz_token(method: str, params_for_hash: dict) -> dict` → 回 `{"live_authz_token", "live_authz_nonce", "live_authz_ts"}`。
- 讀 secret：`secret = _read_secret()`，從 `OPENCLAW_LIVE_PATCH_SECRET` 或 `OPENCLAW_LIVE_PATCH_SECRET_FILE`（鏡像 Rust secret_env 語意）；secret 缺 → raise（fail-closed，無 token 不可能鑄）。
- `nonce = secrets.token_hex(16)`；`ts = int(time.time())`。
- `canonical_patch_hash = sha256(canonical_json(params_for_hash)).hexdigest()`，`canonical_json` = `json.dumps(obj, sort_keys=True, separators=(",",":"), ensure_ascii=False).encode("utf-8")`（與 Rust canonicalizer 對齊；見 0.1 round-trip 測試）。
- `bind = b"\x1f".join([hash, b"live", method.encode(), str(ts).encode(), nonce.encode()])`；`token = hmac.new(secret, bind, sha256).hexdigest()`。
- **新 mutable singleton？** minter 無狀態（每次讀 secret + 隨機 nonce），**不是** singleton，無需登記。Rust 的 NonceLedger 才是 singleton。

**共用 helper** `_require_live_gates_if_live(actor, engine)`（risk_routes.py，緊鄰 `_require_risk_write:111`）：
- `engine == "live"` → `from . import live_preflight; ok, reasons = live_preflight.all_five_live_gates_ok(actor, require_authz=True)`；fail → `raise HTTPException(409, detail={"error":"live_gate_failed","gate_failed":reasons})`（**逐字鏡像** update_per_engine_global_config:710-727 的既有 body，零新 authz 邏輯）。
- `engine in {"paper","demo"}` → no-op（Demo 放寬/Live 收緊政策）。
- 無 flag（只收緊，永遠生效）。

**三 route 改動**：
1. **request model 加 engine 欄**（U1 RESOLVED — 三 model 今天無 engine 欄）：`GlobalConfigUpdate`(:122)、`CategoryConfigUpdate`(:146)、`AgentAdjustRequest`(:161) 各加 `engine: str = Field(default="paper")`（default=paper **保留今日行為**；validator 限 `{"paper","demo","live"}`）。
2. **`/config/global`(:245)**：`_require_risk_write(actor)` 後加 `_require_live_gates_if_live(actor, body.engine)`；engine=="live" 時改走 `_get_direct_ipc()` 路徑（鏡像 update_per_engine_global_config:728-756：`_build_global_patch` → mint token → `ipc.call("patch_risk_config", params={engine, patch, source:"operator", **token})`）；engine 非 live 維持既有 `client.update_global_config()`（不傳 engine、寫 paper、零 token）。
3. **`/config/category`(:286)**：同 2，engine=="live" 走 direct-ipc + token（patch=`{"overrides":{category:mapped}}`）；非 live 維持 `client.update_category_config()`。
4. **`/agent-adjust`(:376)**：(a) 加 `_require_live_gates_if_live`；(b) **engine=="live" → 直接 `raise HTTPException(403, detail={"error":"agent_source_live_write_forbidden"})`**（合法 agent→live 路徑要到 Phase 3，Phase 0 硬拒，且**先於 gate/mint**短路，不鑄 token）+ 寫 V014 config_reject 審計 row（見 0.4，source="agent"）；engine 非 live 維持既有 `client.agent_adjust()`（source=agent、寫 paper）。**此即 operator 必測項**。

**既有 `/config/engine/{engine}/global`(update_per_engine_global_config:688) 必須同步補 token（否則自我封死）**：此路由是**今天唯一已過 5-gate 的合法 operator live 寫入路徑**，但目前 call `patch_risk_config` 時 **不帶 token**（risk_routes.py:736-739）。一旦 Rust chokepoint 上線，此路由的 live call 會被自己的 gate 拒（`live_authz_token_required`）。**E1 必須在此路由的 `engine=="live"` 分支（5-gate 通過後、`ipc.call` 之前）插入 `mint_live_authz_token("patch_risk_config", patch)` 並把三 token 欄併入 params**。這是 Phase 0 不可遺漏的整合點（CC/E3 review checklist 必含「既有 5-gate live 路徑已補 token」）。demo/paper 分支不鑄 token。

**g2_03_bind_helper.py re-home（:179,:262）**：
- `--engine-mode live`：**不再**讓 helper 直接送 socket patch。改為先 `POST /api/v1/.../risk/config/engine/live/global`（既有 update_per_engine_global_config，已過 5-gate + Phase-0 token）— 即 helper 變成「呼 Python 控制面的薄 client」而非「繞過控制面的 direct socket」。
- **降級/最小改動方案**（若不想讓 helper 依賴 HTTP 控制面）：helper `--engine-mode live` 改為**只先呼 Python 一個新窄端點 `POST /api/v1/.../risk/live-patch-token`（Operator + all_five_live_gates_ok）取 token**，再帶 token 走既有 socket。但這等於新增一條「Python 發 token 給任意 socket client」的端點，擴大攻擊面 → **PA 不推薦**。
- **裁決：`--engine-mode live` 直接禁用**（helper print「live writes must go through POST /risk/config/engine/live/global」並 exit 2），`paper`/`demo`/`live_demo` 維持既有 socket 直連（demo/paper 無 token 需求；`live_demo` 走 demo endpoint 但 live-grade control — 確認其 engine 字串 resolve 成什麼：grep 證 g2_03 `live_demo` 是否被 Rust select 成 live；若是則同 live 處理）。**E1 必 grep**：`live_demo` 在 `PerEngineRiskStores::select`(engine_routing.rs:93) 落到哪個 store（`_ => paper`，即 live_demo→paper store）→ 確認 live_demo 不寫 live store，否則 live_demo 也要 token。

---

### 0.4 審計（V014 engine_events，每次 gate/token 失敗都落 row）

**復用既有 V014 表**（observability.engine_events，schema 見 V014__engine_events.sql；**無需新 migration**）。`event_type='config_reject'` 是表設計時已預留但**從未使用**的值（V014 註釋 line 21），Phase 0 首次啟用它。

**reject-row shape**（Rust chokepoint 與 Python 403/409 各寫一條，fail-soft fire-and-forget，鏡像 handlers_config.rs:167-198 既有 INSERT）：
```sql
INSERT INTO observability.engine_events
  (ts_ms, event_type, source, config_name, old_version, new_version, payload)
VALUES ($ts_ms, 'config_reject', $source, $config_name, NULL, NULL, $payload)
```
- `source`：`"operator"` | `"agent"` | `"direct_socket"`（reject 來源）。
- `config_name`：`"risk/live"`（或實際 target，如 `"risk/live"` / method 名）。
- `old_version`/`new_version`：NULL（reject 無版本變動）。
- `payload`（JSONB）：`{"method": <method>, "reject_reason": <code>, "engine": "live"}`，其中 `reject_reason ∈ {live_authz_token_required, token_expired, nonce_replay, nonce_ledger_full, token_invalid, live_gate_failed, agent_source_live_write_forbidden}`。
- **不記** token/nonce/secret 任何值（CLAUDE §十一：絕不外洩 secret/token）。
- **accept row 不變**：成功 live patch 仍走既有 `event_type='config_patch'` row（handlers_config.rs:167）；Phase 0 額外確認 `risk/live` 成功 patch 的 warn! 行被**移除**（見 0.5），audit 信號改由 config_patch row + chokepoint 的結構化 log 承載。
- **live audit fail-closed（CC §5）**：live RiskConfig 成功 commit 的 audit row 寫入，Phase 0 **暫維持既有 fire-and-forget**（與既有 config_patch 一致），但 QA 必在 Linux PG **實證** accept(config_patch) + 4 類 reject(config_reject) 都真落 row（audit_events/engine_events 史上稀疏，P8 風險）。**真正的「commit gate 在 audit 寫成功」是 Phase 2 促升的要求**（Phase 0 是收緊既有路徑，不改 commit↔audit 時序，避免引入 live patch 阻塞風險）。E3 確認此邊界。

---

### 0.5 移除 fail-open（MED-1 RESOLVED）

- **移除** `OPENCLAW_LIVE_PATCH_TOKEN_REQUIRED` flag 整個概念。Rust chokepoint **無條件**對 `engine==live && LIVE_WRITE_METHODS` 強制 token；**沒有** warn!-only 逃生門。
- **取代** handlers_config.rs:157-164 的 `if config_name.starts_with("risk/live") { warn!(...) }` 分支：刪除該 warn!-only block（其授權判斷已上移到 dispatch chokepoint；到達 handle_patch_config 的 live patch 必已過 token gate）。保留 line 167-198 的 V014 config_patch INSERT（accept 審計）。
- **唯一緊急姿態 = 撤 `OPENCLAW_LIVE_PATCH_SECRET` 檔/env**：secret 不存在 → Python 無法鑄 token（mint raise）+ Rust verify 必失敗（`secret.is_empty()→false`）→ **所有 live patch fail-closed**。這是 fail-closed kill-switch，非 fail-open。

---

### 0.6 測試矩陣（acceptance — E4 在 Linux PG + 真 engine 跑全綠才 sign-off）

| # | 測試 | 預期 | 層 |
|---|---|---|---|
| T1 | **operator 必測**：`POST /agent-adjust` body.engine="live" | 403 `agent_source_live_write_forbidden`，0 mutation，V014 config_reject row(source=agent) | Python |
| T2 | direct-socket `patch_risk_config{engine:live, patch}` 過 `__auth` HMAC 但**無** live_authz_token | ERR_INVALID_REQUEST `live_authz_token_required`，0 mutation，V014 reject row(source=direct_socket) | Rust |
| T3 | live token **過期**（ts = now-26s） | ERR_INVALID_REQUEST `token_expired` | Rust |
| T4 | **TTL 邊界**：ts=now-24s → 過；ts=now-26s → 拒 | 24s ok / 26s reject（25s 閾值） | Rust |
| T5 | **nonce 重放**：同 token 連送兩次 | 第一次 ok、第二次 `nonce_replay`（TTL 內也擋） | Rust |
| T6 | **跨 method 重用**：拿 `patch_risk_config` 的 token 送 `update_risk_config` | `token_invalid`（bind-string method 不符） | Rust |
| T7 | **跨 patch 重用**：拿改 cost_gate_k 的 token 送改 leverage 的 patch | `token_invalid`（canonical_patch_hash 不符） | Rust |
| T8 | **per-method 覆蓋**：對 `LIVE_WRITE_METHODS` 每個 method `engine:live` 無 token | 全部 fail-closed reject（參數化測試逐 method） | Rust |
| T9 | `POST /config/global` body.engine="live" 缺 5-gate（如 global_mode≠live_reserved） | 409 `live_gate_failed` | Python |
| T10 | `POST /config/global` body.engine="live" 過 5-gate + fresh token | 成功 + V014 config_patch row + **Linux PG 實證 live ConfigStore version 前進 + hot-reload** | E2E |
| T11 | **demo/paper 不受影響**：`engine:demo` 與 `engine:paper`（及不傳 engine）的三 route + direct socket | 全部維持既有行為、**無 token 需求**、0 回歸 | Python+Rust |
| T12 | **canonical round-trip**：Python `canonical_json(fixture)` bytes == Rust 對同 JSON 反序列化後重序列化 bytes（fixture 含浮點/巢狀/中文 key） | byte-identical（否則整機制失效） | 跨語言 |
| T13 | **secret 撤除 kill-switch**：移除 `OPENCLAW_LIVE_PATCH_SECRET` 後 live patch | Python mint raise + Rust verify fail → fail-closed | E2E |
| T14 | **nonce ledger 驅逐**：插入 TTL 外舊 nonce 後該 nonce 不阻新 token；ledger 不無界增長 | 過期 nonce 被驅逐，size 有界 | Rust |
| T15 | g2_03 `--engine-mode live` | exit≠0 + 指引走 HTTP 控制面（不送 socket）；`demo`/`paper` 維持既有 | helper |

**Linux PG 實證紀律（CLAUDE Data §）**：T10/T11/T13 必在 `ssh trade-core` 真 engine + 真 PG（trading_admin@127.0.0.1/trading_ai）跑；Mac mock pytest 不驗 hot-reload 語意。T12 跨語言 round-trip 是**整個機制的命門**，E1 first-build 必先通過 T12 才繼續。

---

### 0.7 E1 build order + 整合 seam

**順序裁決：Rust-first（chokepoint + token verifier + nonce ledger），Python 跟（minter + route）**。理由：
1. **整合 seam = canonical_patch_hash 的位元對齊（0.1/T12）**。這是 Python↔Rust 唯一硬契約；必須先在 Rust 定下 canonicalizer 的確切行為（serde_json key 排序 + 緊湊輸出 + 浮點字串化），Python 再對齊。若 Python 先寫，浮點字串化分歧（T12 fail）會逼 Python 全部重做。
2. Rust 端（verifier/ledger/chokepoint/allowlist/刪 warn!）**檔案不與 Python 重疊** → 可與 Python 端並行，但**T12 fixture 必須由 Rust 端先產出**作為 Python 對齊基準。

**E1 並行拆分（檔零重疊，可雙 E1）**：
- **E1-RUST**：`ipc_server/live_authz.rs`（新檔：`verify_live_authz_token` + `canonical_hash_for` + `NonceLedger` + `LIVE_WRITE_METHODS`）；`dispatch.rs`（chokepoint 插在 :127 前 + 接 NonceLedger singleton + 寫 V014 reject）；`handlers_config.rs:157-164`（刪 warn!-only block）；main boot（建 NonceLedger Arc 傳入 dispatch 鏈 + secret 啟動讀取告警）；singleton table 登記 NonceLedger。產出 **T12 canonical fixture**（一組 JSON + 其 Rust canonical bytes）。
- **E1-PY**（依賴 E1-RUST 的 T12 fixture）：`app/live_patch_token.py`（新 minter）；`risk_routes.py`（`_require_live_gates_if_live` helper + 三 route engine 欄 + gate + live-branch direct-ipc+token + agent-adjust 403 + reject 審計 + **既有 update_per_engine_global_config live 分支補 mint token**）；三 request model 加 engine 欄；`g2_03_bind_helper.py`（`--engine-mode live` 禁用）。

**剩餘 micro-uncertainty（E1 coding 前必 grep 確認）**：
- **U-P0-1（命門）**：T12 canonical 浮點字串化 Python↔Rust 是否位元一致。E1-RUST 先寫 5-case fixture（含 `0.03`、`1e-7`、巢狀、中文 key、整數）跑 Rust canonicalizer 印 bytes；E1-PY 對齊。若不一致 → 採 0.1 降級方案（Rust 主導 hash，Python 送原始 patch JSON 字串）。**這是 must-resolve-before-coding，非 nice-to-have。**
- **U-P0-2**：`live_demo` 在 `PerEngineRiskStores::select`(engine_routing.rs:93) 落到哪個 store。grep 證 `_ => paper`，即 `live_demo`→paper store（不寫 live store）→ g2_03 `live_demo` 不需 token。E1 確認後在 helper 註明。若未來 live_demo 改 select live store，則 live_demo 必須納入 token gate。
- **U-P0-3**：chokepoint 讀 engine 的方式（`params.get("engine").as_str().unwrap_or("paper")`）必須與**每個** LIVE_WRITE_METHODS arm 內部讀 engine 的方式逐字一致。E1 grep 每 arm 的 engine 讀取（patch_risk_config:421-425 / extract_engine_tx:256 / get_risk_config:409-413）確認無「gate 判 paper、arm 走 live」的 skew。
- **U-P0-4**：`update_risk_config` 與 `set_strategy_active`/`update_strategy_params` 的 params 形狀（非 `patch` key）→ 確認 `canonical_hash_for` 的「排除 token+engine 後序列化整 params」分支正確涵蓋。

---

### 0.8 Rollback / flags / kill-switch
- **無新 migration**（復用 V014）。**無新 master flag**（Phase 0 是無條件收緊；移除了 fail-open flag）。
- **revert**：還原三 route body + 三 model engine 欄 + 刪 `live_patch_token.py` + 還原 dispatch chokepoint（移除 gate block）+ 還原 handlers_config.rs warn!-only + 移除 NonceLedger singleton。純加法（chokepoint 是 match 前的 if block，刪了即回原行為），無 schema 副作用。
- **kill-switch（唯一緊急姿態）**：撤 `OPENCLAW_LIVE_PATCH_SECRET` 檔/env → 全 live patch fail-closed（Python mint raise + Rust verify fail）。

### 0.9 硬邊界核對（CLAUDE §四 / 16 原則）
- **不觸碰** live_execution_allowed / max_retries / system_mode / authorization.json 簽署路徑（5-gate 決策權威仍在 Python live_preflight，Phase 0 只新增 enforcer）。
- 原則 #1 單一寫入口：強化（live param 寫入新增單一 chokepoint）。#2 讀寫分離：唯讀 method 豁免，寫 method 收緊。#4 不繞風控：agent→live 硬拒（403）。#6 失敗收縮：所有失敗 fail-closed。#8 可審計：每 reject 落 V014 row。**評級預期 A（16/16，5-gate 0 觸碰，純收緊）。**

### Role chain（E3+CC+BB 強制不可跳）
`PA → CC(16-principle+硬邊界,MANDATORY) → E3(security: token 綁定/HMAC 復用/replay/nonce ledger/TTL/canonical 對齊,MANDATORY) → BB(live order-sizing 面,MANDATORY) → E1-RUST ∥ E1-PY(T12 fixture 為 seam) → E2(對抗:agent+live reject/跨method+跨patch 重用/nonce replay/engine skew) → E4(Rust+pytest+Linux 實證 hot-reload+T12 跨語言) → CC final → PM`

---

## PHASE 1 — demo 自主智能策略參數調參
**目標**：餵 StrategistScheduler 更多 leak-free 證據（additive INPUT），不改它能寫什麼（仍 demo、仍 agent_adjustable 策略參數、仍既有 clamp）。

- 擴充 LLM payload（additive）：`edge_estimates`(per-cell shrunk_bps/win_rate)、`ml_shadow`(ONNX shadow_only 純諮詢)、`regime`(本地 leak-free label)、`news_context`(corroborating-only)。
- **news 規則（code+test 非註釋）**：validate 層（mod.rs:402）要求 recommendation 帶 `quant_justification` 引至少一個量化證據源；唯一支撐是 news_context → **reject `news_solo_trigger`**（加入 REJECT_REASONS + CycleCounters + test）。news 只能在多個量化證據選項中影響偏好，永不可單獨致 delta。
- 復用 apply+persist+±delta clamp+range+weight-sum=65 不變；tunable 集 = 既有 agent_adjustable:true（mod.rs:430）；Phase 1 無新參數受控。
- flag `OPENCLAW_STRATEGIST_RICH_INPUT` default-OFF（OFF=bit-identical baseline）。
- Role chain：`PA → QC(leak-free? look-ahead? MANDATORY) → MIT(shadow ONNX 輸入正確性) → E1 → E2(證 news-solo reject+clamp 完整) → E4(flag-OFF identity+flag-ON 行為) → CC(Alpha Evidence) → PM`

---

## PHASE 2 — demo→live 促升管線（人工閘）
**目標**：把 `promote_params_to_live()`(mod.rs:342) 接在 operator 確認的 criteria 後。策略參數 only，永不 RiskConfig。

- 新 IPC `promote_strategist_params`（method_registry+dispatch）→ 呼既有 promote method。
- 新 route `POST /api/v1/strategist/promote`（Operator + all_five_live_gates_ok）→ 呼 IPC。
- criteria gate（Rust 純邏輯，鏡像 canary_promotion_eval.py:127）：demo-applied 參數連 N cycle 穩定 + soak 窗無 drawdown 越界 + demo realized 非淨負，才可促升。
- 流程：demo soak 穩 → operator GUI 審 diff → 確認 POST /promote(5 gate) → criteria gate → IPC → promote_params_to_live → Live UpdateStrategyParams → audit learning.strategist_promotions。**永不自動呼。**
- Rollback = reverse-promote（`POST /strategist/demote` 重套促升前 live snapshot，同 gate）；存 pre-promotion snapshot 以精確還原。flag `OPENCLAW_STRATEGIST_PROMOTION_ENABLED` default-OFF。
- Role chain：`PA → QC(criteria 閾值 quant-justified,MANDATORY) → E1 → E2(證無自動觸發+reverse 精確) → E3(live route auth) → E4(Linux 實證 真 Live engine bound, promote+demote 往返) → CC → PM`

---

## PHASE 3 — RiskConfig agent 調參（全範圍件）
**目標**：agent 調 **非 survival** RiskConfig 旋鈕，demo 自主 + live 經 Phase 2 促升閘。survival floors 永遠 operator-only。需 Phase 0 完成。

### 新 `RiskConfigDirectiveSink`（DirectiveApplier 第三 sink）
- 新增 `DirectiveType::AdjustRiskConfig` + 平行 sink trait（**不**擴 PipelineCommandSink——其契約 strategy_ipc_impl.rs:11-24 禁碰 RiskConfig，保此不變量）。經 Rust `ConfigStore<RiskConfig>` 直寫（in-process，source=Agent），**永不**走 Python operator route（保 agent 路徑在 Rust denylist 內）。

### 欄位級 ALLOWLIST（非 survival，agent 可在 operator band 內動）
- `regime.{trending,volatile,ranging,squeeze,unknown}.*` 乘數
- `dynamic_stop.{base_ratio,cap_ratio,trailing_min_rr,atr_stop_mult,atr_tp_mult}`（不可超 survival SL/TP 上限）
- `limits.holding_hours_max`（**僅向下/收緊**）
- `agent.{trailing_activation_pct,trailing_distance_pct,size_multiplier}`（size_multiplier 已 clamp [0.1,1.0]）

### survival DENYLIST（operator-only 永遠，agent 寫=硬 veto）
`limits.{stop_loss_max_pct,take_profit_max_pct,position_size_max_pct,total_exposure_max_pct,correlated_exposure_max_pct,leverage_max,session_drawdown_max_pct,daily_loss_max_pct,global_notional_cap_usdt,min_balance_usdt,consec_loss_cooldown_*}`、`per_trade_risk_pct`，加既有 P0_P1_DENYLIST_FIELDS。
**cost_gate.k_***：operator 旗標 survival-class → Phase 3 **預設 denylist**；若日後允許僅向下(收緊)、在緊 band 內，永不向上（另一 operator 決定）。

### clamp-cannot-widen（鏡像 DynamicRiskSizer）
每 allowlist 欄位：agent 提議值 → sink clamp 至 live RiskConfig 讀出的 `[band_min,band_max]`（band 欄位本身在 denylist，agent 不能放寬）。放寬風險的 UP 移動需 LCB 顯著性 gate（dynamic_risk_sizer.rs:42-52）；收緊 DOWN 不設限。

### 治理 gate（復用 Teacher applier）
1) 欄位 allowlist check（非 allowlist 或含 denylist→拒，inverse+extend find_denylisted_field applier.rs:306）；2) GovernanceCore veto(applier.rs:342)；3) daily-loss/drawdown veto；4)(live only) 值須經 Phase 2 促升(operator 確認+5 gate+Phase-0 token)，demo 自主無 token。每結果→learning.directive_executions row。
- flag `OPENCLAW_RISKCONFIG_AGENT_TUNING_ENABLED` default-OFF（master）。
- Role chain：`PA → CC(證 P4/P5/P7/P11,MANDATORY) → E3(sink 在 live 無 token 不可達,MANDATORY) → QC+MIT(旋鈕由 leak-free 證據支撐? regime/dynamic-stop 敏感度,MANDATORY) → BB(live sizing 影響) → E1(新 sink+DirectiveType+allowlist) → E2(對抗:survival veto/band-widen/live bypass) → E4(Linux:demo apply+audit+hot-reload; live 無促升被拒) → CC final → PM`

---

## 依賴/排序
- **獨立可部署**：Phase 0（純收緊）、Phase 1（demo-only，不需 Phase 0 因永不觸 live）。Phase 0 與 1 不同檔可並行 E1 wave。
- Phase 2 需 Phase 0+1 merged。Phase 3 需 Phase 0；demo 半可先於 Phase 2 出，live 半復用 Phase 2 機制。

## 新 flags（全 default-OFF）/ secrets / singletons / migrations
- flags 見各 phase。secret：`OPENCLAW_LIVE_PATCH_SECRET`（Phase 0，file-based，與 IPC secret 分離）。
- singleton 註冊（CLAUDE §九 merge 前）：RiskConfigDirectiveSink、live-patch token minter。
- migration（V###，Linux PG 實證 dry-run + double-apply 必跑）：`learning.strategist_promotions`(P2)；復用 learning.directive_executions(P3)+V014 engine_events(P0 rejects)。

## 觀測 / kill-switch
- 每次 auto-tune 可見：get_strategist_cycle_metrics + 新 get_risk_directive_metrics（per-param apply/reject/last value/source）；GUI Risk tab 顯示 agent 動作+量化理由（node --check 前置）。
- audit：strategist_applied_params(P1)/strategist_promotions(P2)/directive_executions(P3)/V014 rejects(P0)，**全須 QA 實證會落 row**（audit_events 歷史為空，P8 風險）。
- kill-switch 分層：per-phase master flag OFF→凍該 phase；撤 LIVE_PATCH_SECRET→全 live patch fail-closed；GovernanceCore session-halt/daily-loss/drawdown veto→stress 時擋全 agent 調參；operator 促升確認是唯一 live 觸發。

## 待解不確定（建該 phase 前先解）
- **U1(Phase 0) RESOLVED**：grep 證實 `RiskViewClient._patch()`(risk_view_client.py:306) 送 `{patch, source}` **不含 engine** → Rust default paper（engine_routing.rs:97）→ 三 route 今天寫不到 live。Phase 0 真工作=三 model 加 engine 欄 + `_require_live_gates_if_live` gate + token（折入 §0.3）。
- **U2(Phase 1)**：StrategistScheduler payload 組裝 fn 確切位置（evaluate.rs:310 附近）。
- **U3(Phase 1)**：agent_adjustable:true ParamRange 權威列舉（grid/ma 集），供 operator/QC 確認可控面。
- **U4(Phase 0,security,operator+E3) RESOLVED-PENDING-RATIFY**：capability-token 模型已具體設計（§0.1-§0.2，綁操作+單次 nonce+TTL 25s+constant-time）。operator 已鎖定方向（Operator 決策 #3）；E3 review token 綁定/replay/nonce ledger/canonical 對齊。拒絕的替代=全 5-gate-in-Rust（重複權威 + Rust 缺 session/secret-slot context）。
- **U5(Phase 3,quant,QC)**：各 allowlist 欄位的 operator band（regime 乘數、dynamic_stop ratio）。band 即安全面；無 band 則該欄位留 denylist。

---

## 對抗審核 must-fix（E3 security + CC compliance + E2 engineering，2026-06-17；build 前 PA 須折入 spec）

### 已解（E2 親驗）
- **U1 RESOLVED**：`/config/global`/`/config/category`/`/agent-adjust` 目前 Python client 不傳 engine → Rust default `paper`（dispatch.rs:421-425, engine_routing.rs:93-99）→ **三 route 今天根本寫不到 live**。Phase 0 真工作=給三個 request model（GlobalConfigUpdate:122/CategoryConfigUpdate:146/AgentAdjustRequest:161 目前無 engine 欄）**加 engine 欄 + gate**；live 威脅實為 direct-socket + IPC 方法面（見 HIGH-2）。
- **U2 RESOLVED**：payload builder = `build_strategist_eval_payload` evaluate.rs:**423**（非 :310，:310 是 tune_target=Demo fail-fast guard，E2 證 Phase 1 結構上碰不到 live）。
- 所有 spec 對既有碼的 file:line claim 經 E2 spot-check **準確**。

### HIGH（build 前必修）
1. **[PHASE-0 RESOLVED — 折入 §0.1/§0.2]** token 必須綁操作非僅 timestamp（E3 HIGH-1 + E2 HIGH-2）：新 `live_authz_token` = HMAC over `(canonical_patch_hash ∥ engine ∥ method ∥ ts ∥ nonce)` + single-use nonce ledger（§0.1）；canonical 序列化 + bind-string + wire format + TTL=25s + 常數時間 verify 全在 §0.1 釘死。**`verify_ipc_token`(connection.rs:52) 不改**（connection-level handshake 保留），Phase 0 新增獨立 per-request token。
2. **[PHASE-0 RESOLVED — 折入 §0.2]** token gate 覆蓋所有 live-write 方法（E3 HIGH-2）：chokepoint **裁定在 `dispatch_request` 的 `match method` 之前**（dispatch.rs:127 前）——grep 證實**無單一 engine-resolution 函數**所有 live-write 都經過（`extract_engine_tx` 只服務 PipelineCommand、`patch_risk_config` engine resolve 是各 arm 內聯走 `risk_stores.select`）；唯一覆蓋全 method 的點是 match 前。`LIVE_WRITE_METHODS` allowlist 完整列舉於 §0.2（含 patch/update_risk_config/force_governor_*/set_dynamic_risk_enabled/restore_exit/reset_drawdown/clear_consec/set+update_strategy/pause+resume+reset_paper），唯讀 method 豁免。
3. **Phase 2 reverse-promote 非精確**（E2 HIGH-1，**Phase 2 範疇，不在 Phase 0**）：`UpdateStrategyParams` 是 deep MERGE 非 replace（strategy_params.rs:17-42）→促升新增的 key 重放 snapshot 不會移除。修：snapshot 取完整 param set(GetStrategyParams)+demote 送完整 key set 或加 replace 路徑+version precondition（live 期間變動則拒）。加 add-key-then-demote acceptance test。

### MEDIUM（build 前折入）
- **[PHASE-0 RESOLVED — 折入 §0.5]** fail-open flag 移除（E3 MED-1）：`OPENCLAW_LIVE_PATCH_TOKEN_REQUIRED` 概念整個移除（§0.5）；handlers_config.rs:157-164 warn!-only block 刪除；唯一緊急姿態=撤 `OPENCLAW_LIVE_PATCH_SECRET`（fail-closed）。
- **[PHASE-0 PARTIAL — 折入 §0.4]** live audit fail-closed（CC §5）：Phase 0 每次 gate/token reject 落 V014 `config_reject` row（§0.4，復用既有表，無新 migration）；QA 必在 Linux PG **實證** accept(config_patch)+4 類 reject 都落 row。**「commit gate 在 audit 寫成功」的同步硬綁是 Phase 2 促升要求**（Phase 0 不改 commit↔audit 時序，避免 live patch 阻塞風險）。
- **[PHASE-0 NOTE — §0.7 U-P0-1]** canonical 序列化 Python↔Rust 位元對齊（新增 must-resolve）：浮點字串化分歧會使 token hash 失配；E1-RUST 先產 T12 fixture，E1-PY 對齊；不一致則 Rust 主導 hash。**這是 Phase 0 build 的命門。**
- **denylist 補全 + 用真 RiskConfig 欄名**（CC，**Phase 3 範疇**）：spec denylist 漏 `limits.{daily_loss_halt_ttl_ms,drawdown_halt_ttl_ms,guardian_modification_leverage_cap,guardian_modification_size_factor,open_positions_max,min/max_order_notional_usdt,ft_*}`、**整個 `cascade.*`**、`cost_gate.{min_confidence,adx_trending}`（min_confidence 下調=放寬 gate 同 k 上調）。且既有 `P0_P1_DENYLIST_FIELDS`(applier.rs:200-218) 用舊名(max_leverage)≠RiskConfig 葉名(leverage_max)→不可依賴,Phase 3 denylist 須按真 RiskConfig dotted-path 重寫。
- **nested 遞迴 matcher**（CC + E2，**Phase 3 範疇**）：`find_denylisted_field`(applier.rs:551-559) 只比 top-level key→`{"limits":{"leverage_max":50}}` 繞過。須 dotted-path 遞迴走整 patch 樹 + allowlist-default-deny + E2 nested-widen 對抗測試。
- **U5 成硬 gate**（CC，**Phase 3 範疇**）：regime/dynamic_stop 在 struct **無 band 欄**(DynamicStop/RegimeMultipliers validate 只查 >0)→clamp-to-band 是空操作。無 operator band 的 allowlist 欄位 v1 **留 denylist**（或先加 operator-set band 欄,band 本身 denylist）。
- **clamp-cannot-widen race**（E2 MED-2，**Phase 3 範疇**）：ConfigStore load→merge→replace 非原子(handlers_config.rs:119/144)。新 sink 須在單一 `apply_patch` closure(write_lock 內,store.rs:155-192) 讀 band+clamp+寫,或加 CAS version precondition。加 band-narrow-during-agent-UP race 測試。
- **in-process sink 自有 gate**（E3 MED-2，**Phase 3 範疇**）：Phase 3 sink in-process 寫 ConfigStore 不過 IPC token 層→live 寫須 sink 自驗 token/promotion-state；demo sink 只持 demo ConfigStore Arc,結構上不可持 live Arc（P1 單一 ConfigStore/engine,E3 驗）。
- **news/quant-justification 須 server-side 驗值非 LLM 自述**（E3 MED-3 + CC §4 + E2 angle-6，**Phase 1 範疇**）：`quant_justification` free-text 是新注入出口+可被 news 敘事滿足。validate 須(1)news_context 標 untrusted 結構隔離;(2)引用的 quant 證據用 **engine 端獨立查/重算**(edge_estimates cell shrunk_bps 符號/量級與 delta 方向一致),news 在 gate 算術零權重;(3)新 reject 理由 `quant_justification_unverified`。news 只能在已獨立通過量化 gate 的選項間作 post-hoc tiebreaker。
- **migration 號 build 時釘**（E2 MED-4，**Phase 2 範疇**）：最高現為 V143。P2 `learning.strategist_promotions` build 前重查 next-free(≥V144)+Guard A+double-apply,勿信本 doc 佔位。**Phase 0 無新 migration**（復用 V014）。
- **method_registry 是描述非執行**（E2 MED-3）：真 wiring 在 dispatch.rs match arm(unknown→ERR_METHOD_NOT_FOUND);registry 條目 optional。

### LOW / 注意
- DynamicRiskSizer clamp 真碼在 maybe_update :199/:216/:298-306、LCB-UP :280-290（非 spec 引的 :42-99 config docs）。
- `OPENCLAW_LIVE_PATCH_SECRET` 須 chmod 600 + 與 IPC secret 分離檔（secret_env.rs:25 無權限檢查）。
- applier.rs 1072 行(>800)；P3 加 DirectiveType+sink 恐近 cap→考慮 sibling `applier_riskconfig.rs`。
- Phase 3 demo sink 須明確 `select("demo")`（engine_routing unknown→paper fallback 會誤落 paper）。
- **dirty-tree 撞號**：本 session 另一工作刪了 `openclaw_core/src/risk/regime.rs`（RegimeMultipliers 死配置修復）；P3 allowlist 含 `regime.*` 乘數→build 時確認不撞（該修復是 engine config.regime,P3 也是同源,需對齊）。

