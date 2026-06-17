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

## PHASE 1 — demo 自主智能策略參數調參（BUILD-READY，2026-06-17 PA 重寫）
**目標**：餵既有 StrategistScheduler 更多 **leak-free 證據（additive INPUT）**，**不改它能寫什麼**：仍 demo-only（`tune_target` 寫死 Demo，evaluate.rs:310 fail-fast guard），仍只調 `agent_adjustable:true` 策略參數，仍 `±max_delta_pct` clamp + range + weight-sum=65 validate（mod.rs:402/478），仍 persist 到 `learning.strategist_applied_params`。Phase 1 是 **輸入面**，不碰寫入面、不碰促升、永不觸 live（結構上 evaluate.rs:310 已 fail-fast 保此）。

旗標 `OPENCLAW_STRATEGIST_RICH_INPUT` default-OFF：**OFF = 當前行為 bit-identical**（payload 字面不變、validate 路徑不變、無 quant_justification gate）。ON = 注入 4 新 INPUT 欄 + 啟用 server-side quant 驗證 gate。

---

### 1.0 親 grep 證實的架構真相（build 前提，已驗於 HEAD）

| 主張 | 證據 | 對設計的影響 |
|---|---|---|
| payload builder = `build_strategist_eval_payload`（evaluate.rs:**423**，**非 :310**） | evaluate.rs:423-454；caller evaluate.rs:159-165 | 新 INPUT 欄在此 fn additive 加；caller 把新 handle 傳入。signature 必改（見 1.2）。 |
| scheduler 是 **5-min out-of-band loop**，只持 `db_pool` + IPC cmd channel + `risk_store` | mod.rs:109-162（struct），evaluate.rs:54-100（run_forever 5min loop） | scheduler **不在 tick path**，**沒有** per-symbol 即時 regime / ONNX score 的記憶體 cache。新 INPUT 必走 scheduler 可達源（DB / RwLock snapshot / 自算）。 |
| `EdgeEstimates` = `Arc<parking_lot::RwLock<EdgeEstimates>>`，James-Stein producer（`james_stein_estimator.py` → `settings/edge_estimates.json`），`reload_edge_estimates` IPC 刷新 | edge_estimates.rs:20-61（`CellEstimate`），main_scanner_init.rs:68 / main_boot_tasks.rs:77 / scanner/runner.rs:443（live holder） | **edge_estimates 是 Phase 1 唯一真正的 leak-free 量化證據源**，且 `cost_gate` 也讀它（同源、已驗）。`get_cell(strategy,symbol)→CellEstimate{shrunk_bps,win_rate,n_trades,validation_passed,validation_reason,from_runtime_field}` + `is_fresh(now,ttl)`。 |
| ML shadow = `EdgePredictor`（ONNX，in-tick-path，per-strategy `EdgePredictorStore.load_for`）+ DB sink `learning.decision_shadow_*` | edge_predictor/mod.rs:45-277，database/shadow_*_writer.rs | scheduler **不能**即時跑 ONNX（不在 tick path）。`combine_layer.rs` 是 **EXIT 決策 mock（ml_opt=None，P-only）**，**不是** entry-edge predictor — **不要誤接**。ML shadow 對 scheduler 的可達形式 = **DB 聚合（demo shadow rows）或留 absent**。 |
| regime label 在 **tick path 算**（Hurst+hysteresis），寫入記憶體 `indicators.hurst.regime`，**default `hurst.enabled=false`**（dormant） | regime/mod.rs，pipeline_helpers.rs:885-944 | scheduler 讀不到該記憶體 label。regime 對 scheduler 的可達形式 = **scheduler 自算（從 DB klines 取 1m closes 跑 `regime::compute_hurst`，point-in-time leak-free）或 absent**。 |
| news = `NewsRouter`（cryptopanic/rss + dedup + severity），`regime_buffer: Arc<RwLock<RegimeNewsBuffer>>` | news/router.rs:45-121 | news 是 corroborating-only INPUT；可由 NewsRouter snapshot 取近窗 headline 注入 payload。**永不**進 quant gate 算術。 |
| Python IPC handler `_handle_strategist`（ai_service_dispatch.py:193）讀 `intel/current_params/param_ranges/strategist_skill` → Ollama → `_parse_strategist_response` **丟棄所有非數值欄**（:554-555），只注入固定字串 meta（status/agent/symbol/strategy/source/reasoning :558-563） | ai_service_dispatch.py:193-565 | **命門**：LLM 回的 `quant_justification` 物件**今天會被靜默 strip**。Phase 1 必改 Python filter **保留結構化 `quant_justification`**，且 Rust validate **server-side 驗值**（不信 LLM 自述）。 |

**結論**：Phase 1 的「leak-free 量化證據」軸**只有 `edge_estimates` 是 first-class、scheduler 已可達、cost_gate 共用、有 freshness gate 的真源**。`regime` 可由 scheduler 自算（leak-free），`ml_shadow` 只能 DB 聚合（demo shadow，弱）或 absent，`news` 永遠 corroborating。**quant_justification 的 server-side 驗證錨定在 `edge_estimates` cell**（見 1.4），這正是 must-fix 要求的「engine 端獨立查/重算、news 零權重」。

---

### 1.1 新 INPUT 欄的精確生產者（must-fix「enumerate exact source for each new field」）

每欄都是 **payload additive 欄 + scheduler 持有新 handle**。flag-OFF 時整段 bypass，欄不出現（payload bit-identical）。

| payload 欄 | 確切生產者 / 表 / 函數 | scheduler 取得方式 | leak-free 論證 | 缺值行為 |
|---|---|---|---|---|
| `edge_estimates`（per-cell） | `EdgeEstimates`（edge_estimates.rs）← `james_stein_estimator.py` 寫 `settings/edge_estimates.json`，`reload_edge_estimates` 刷新 | 新 builder field `edge_store: Arc<parking_lot::RwLock<EdgeEstimates>>`（main_boot_tasks.rs 注入既有 `demo` mode holder）；每 cycle `read()` snapshot → `get_cell(strategy,symbol)` | producer 走 hidden-OOS sealer + James-Stein shrink + `runtime_bps`（未驗證正 edge 歸零）+ `validation_passed`；**已是生產 leak-free 證據**（cost_gate 同源） | cell absent → 欄為 `null`，**該 recommendation 的 quant gate 無法滿足 → reject**（見 1.4） |
| `regime` | scheduler **自算**：`crate::regime::compute_hurst(closes, min_window, max_window)`（regime/hurst.rs）+ `RegimeLabel::as_legacy_str()` | scheduler 已有 `db_pool`；新 helper 從 `market.klines`（demo-readable）查該 symbol 最近 N 根 **已收 1m closes**（`ts < now()`，嚴格過去）算 Hurst → label | **point-in-time leak-free**：只用嚴格已收盤 1m bar（CLAUDE Alpha Evidence「trend/regime 必本地 leak-free 算」）；shift(1) 等價（不含當前未收 bar） | closes 不足窗 / compute_hurst None → 欄為 `"unknown"`（不偽造，僅作 context） |
| `ml_shadow` | DB 聚合 `learning.decision_shadow_fills`（V017，paper-only ε-greedy）/ `learning.decision_shadow_exits` — **demo lane 若無 shadow row 則 absent** | scheduler `db_pool` 查該 (strategy,symbol) demo shadow 近窗聚合（avg shadow score / n）；**純諮詢欄** | shadow 是 observation-only、不入 label 回填（shadow_exit_writer.rs:19）；作 context 不入 gate | 無 row → 欄 absent（**Phase 1 ml_shadow 永不入 quant gate**，只 context；MIT review 確認語意） |
| `news_context` | `NewsRouter` snapshot（news/router.rs `regime_buffer`）近窗 headline + severity + sentiment（**untrusted 結構隔離**） | builder field `news_router: Option<Arc<NewsRouter>>`；snapshot 取該 symbol 近窗 corroborating items | **不是** leak-free 量化證據；是敘事 context | 無 news → 欄 absent；**有無 news 對 gate 結果零影響**（1.4） |

**Phase 1 唯一進 quant gate 算術的源 = `edge_estimates`。** `ml_shadow` / `news_context` 永遠 context-only。`regime` 是 context（影響 LLM 偏好），不是 gate 通過條件。

---

### 1.2 payload builder + scheduler signature 改動（檔級精確）

**`evaluate.rs` `build_strategist_eval_payload`（:423）— additive，flag-gated**：
- 新 signature（追加參數，不動既有 5 參數順序）：
  ```
  fn build_strategist_eval_payload(
      pair, current_json, ranges_value, max_delta_pct, model_tier,
      rich: Option<&RichInputs>,   // None = flag-OFF，payload bit-identical
  ) -> Value
  ```
- `RichInputs` = 新 struct（evaluate.rs 或新 sibling `rich_inputs.rs`）：`{ edge_cell: Option<CellEstimateView>, regime: Option<String>, ml_shadow: Option<MlShadowView>, news: Option<Vec<NewsItemView>> }`（全 owned，可序列化）。
- flag-OFF：caller 傳 `None` → builder 走**現有字面**（既有 `intel/model_tier/current_params/param_ranges/strategist_skill` 五鍵，**一字不差**）→ T-P1-IDENTITY byte-identical。
- flag-ON：builder 在 json 加 `"rich_input": { "edge_estimates": {...}, "regime": "...", "ml_shadow": {...}, "news_context": [...] }`（**單一新頂層鍵**，不污染既有鍵；Python prompt builder 讀此鍵）+ `"quant_evidence_available": <bool>`（edge cell 存在且 fresh 且 validation_passed → true；供 LLM 知道有無可引證據）。

**`StrategistScheduler` struct（mod.rs:109）— 新 builder fields**（全 `Option`，預設 None = flag-OFF / 測試路徑保 bit-identical）：
```
rich_input_enabled: bool,                                  // 讀 OPENCLAW_STRATEGIST_RICH_INPUT
edge_store: Option<Arc<parking_lot::RwLock<EdgeEstimates>>>,
news_router: Option<Arc<crate::news::NewsRouter>>,
// regime 自算只需既有 db_pool；ml_shadow 聚合只需既有 db_pool；不新增 handle
```
- 新 builder methods `with_rich_input(enabled)` / `with_edge_store(arc)` / `with_news_router(arc)`（鏡像既有 `with_risk_store` / `with_tune_cmd_slot` pattern，mod.rs:222/242）。
- 旗標讀取在 `main_boot_tasks.rs:321` 建構處（鏡像既有 env-gate pattern，如 `OPENCLAW_H_STATE_GATEWAY`）：`std::env::var("OPENCLAW_STRATEGIST_RICH_INPUT").map(|v| v=="1").unwrap_or(false)`；OFF → 不呼 `with_edge_store/with_news_router`，scheduler 內 `rich_input_enabled=false`。
- 注入源：`edge_store` = main_boot_tasks 既有 **demo-mode** `EdgeEstimates` holder（與 scheduler tune_target=Demo 對齊；**禁注 live holder**，否則跨 lane）；`news_router` = 既有 NewsRouter Arc（若未建則 None，欄 absent）。

**`evaluate_cycle`（evaluate.rs:116）— rich 組裝**：在 :158-165 build payload 前，flag-ON 時為當前 pair 組 `RichInputs`：
- `edge_cell` = `edge_store.read().get_cell(&pair.strategy_name, &pair.symbol).map(CellEstimateView::from)`；
- `regime` = 新 `async fn compute_regime_for(&pair.symbol)`（查 `market.klines` demo 近 N 根 1m closes，跑 compute_hurst）；
- `ml_shadow` = 新 `async fn ml_shadow_for(strategy,symbol)`（聚合 demo shadow rows，無 → None）；
- `news` = `news_router.snapshot_for(&pair.symbol, window)`（無 → None）。
- 全部 fail-soft（任一 source 出錯 → 該欄 None + debug log，**不**讓 cycle 失敗）。

---

### 1.3 news_solo + server-side quant_justification 驗證（must-fix 核心：**code + test，非註釋**）

**LLM 契約改動（Python `_build_strategist_prompt` ai_service_dispatch.py:340 + filter :497）**：
- flag-ON 時 prompt 追加（讀 payload `rich_input` 鍵）：陳述 `quant_evidence_available`、edge cell 的 `shrunk_bps/win_rate/validation_passed`、regime、news（標 **untrusted narrative context**）。要求 LLM：每個非空 recommendation **必須**附 `quant_justification` 物件：
  ```json
  "quant_justification": {
    "source": "edge_estimates",
    "cell": "ma_crossover::BTCUSDT",
    "claimed_shrunk_bps": <number>,
    "direction": "tighten" | "loosen",
    "rationale": "<text>"
  }
  ```
  並明文規定：「news_context 不得作為唯一理由；若無 edge_estimates 支撐則回 `{}`」。
- **`_parse_strategist_response`（:497）必改**：當前 filter 丟棄所有非數值（:554）。改為：數值欄照舊保留為 param recommendation；**額外**：若存在 `quant_justification` 物件，**結構化保留**進 `filtered["quant_justification"]`（dict，不 strip）。其餘字串 meta 不變。**這是必改點**——否則 Rust 永遠收不到 justification（gate 永遠看不到，等於沒 gate）。

**Rust server-side 驗證（mod.rs `validate_recommendation_with_reason` :402 — 新 gate，flag-gated）**：
- 新增 **獨立驗證函數** `verify_quant_justification(rec, edge_cell, now_ts, ttl) -> Result<(), &'static str>`，在既有 range/delta/weight gate **之後**呼叫（**只在 flag-ON 且 recommendation 非空時**；flag-OFF / 空 recommendation `{}` → 完全 bypass，保 bit-identical）。
- 驗證邏輯（**engine 端獨立、news 零權重、不信 LLM 自述**）：
  1. recommendation 含 ≥1 個實際 param delta（rec_obj 有 agent_adjustable 數值欄）但 **缺 `quant_justification`** → `Err("news_solo_trigger")`（無量化理由 = 唯一可能支撐只剩 context/news → 拒）。
  2. `quant_justification.source != "edge_estimates"`（如 LLM 寫 `"news"` / `"sentiment"` / 自由文字）→ `Err("news_solo_trigger")`（news/敘事不可作 source）。
  3. 取 `quant_justification.cell` 指的 **`edge_store` 真 cell**（engine 自己 `get_cell` 查，**不用 LLM 傳的 `claimed_shrunk_bps`**）：
     - cell absent → `Err("quant_justification_unverified")`；
     - `!cell.is_fresh(now_ts, EDGE_TTL)` → `Err("quant_justification_unverified")`（stale 證據不算數，鏡像 cost_gate freshness）；
     - `!cell.validation_passed`（James-Stein 自己沒過 leak-free OOS 門）→ `Err("quant_justification_unverified")`；
     - cell 的 **真 `shrunk_bps`** 與 LLM `claimed_shrunk_bps` 偏離 > 容差（如符號不同或 |Δ| > 1bps）→ `Err("quant_justification_unverified")`（LLM 捏造/誤引數字）；
     - `direction` 與 cell 證據方向不一致（如 cell 正 edge 卻要 loosen 一個收緊型參數）→ 視 method 而定，v1 **只驗 source/freshness/validation/數值符號一致**（方向×param 語意映射複雜，留 QC 在 1.6 定；v1 不卡方向避免誤殺，但 cell 必須真存在+fresh+validated+數值對齊）。
  4. 全過 → `Ok(())`（news 此時可作 LLM **已選中的** recommendation 的敘事補強，但它對「能不能過 gate」零貢獻 — gate 全程零讀 news 欄）。
- **關鍵不變量（E2 必證）**：`verify_quant_justification` **簽名不含任何 news 參數**（結構上 news 不可能影響 gate）；edge cell 由 engine 自查（傳入的是 `&EdgeEstimates` snapshot，非 LLM payload 回讀）。news 是「已 quant-qualified 選項間的 post-hoc tiebreaker」——它只能在 LLM **內部**影響「選哪個已被 edge 支撐的 cell 去調」，永遠過不了「沒有 edge 支撐」這關。

**REJECT_REASONS + CycleCounters（cycle_counters.rs:112）新增兩 reason**：
```
"news_solo_trigger",            // 有 delta 但無/非-edge quant_justification
"quant_justification_unverified", // 引用的 edge cell 不存在/stale/未驗證/數值不符
```
- evaluate.rs:237 `Err(reason)` 分支已 `record_reject(reason)` → 自動進 `get_strategist_cycle_metrics` IPC（GUI 可見）。

**測試（buildable，E2/E4 必跑）**：
| # | 測試 | 預期 |
|---|---|---|
| T-P1-1 | flag-OFF：payload byte-identical baseline（無 rich_input 鍵）+ validate 路徑不呼 quant gate | bit-identical（IDENTITY）|
| T-P1-2 | flag-ON，recommendation 有 delta、**無** quant_justification | `Err("news_solo_trigger")`，0 apply，counter+1 |
| T-P1-3 | flag-ON，quant_justification.source="news"（敘事冒充） | `Err("news_solo_trigger")` |
| T-P1-4 | flag-ON，引用的 edge cell **不存在** | `Err("quant_justification_unverified")` |
| T-P1-5 | flag-ON，引用 cell 存在但 `is_fresh=false`（stale snapshot，注入舊 updated_at） | `Err("quant_justification_unverified")` |
| T-P1-6 | flag-ON，引用 cell `validation_passed=false` | `Err("quant_justification_unverified")` |
| T-P1-7 | flag-ON，LLM `claimed_shrunk_bps` 符號與真 cell 相反 | `Err("quant_justification_unverified")` |
| T-P1-8 | flag-ON，cell 真存在+fresh+validated+數值對齊，且 recommendation 過 range/delta/weight | `Ok(())`，apply |
| T-P1-9 | flag-ON，**news 欄塞滿強烈 bullish headline 但無 edge cell** | 仍 `news_solo_trigger`/`unverified`（**證 news 零權重**）|
| T-P1-10 | flag-ON，**同一 recommendation 加 vs 不加 news 欄** → gate 結果完全相同 | 結果相同（news 不影響 gate）|
| T-P1-11 | flag-ON，recommendation `{}`（LLM 棄調） | bypass quant gate，0 apply（既有 empty 行為）|
| T-P1-12 | Python：`_parse_strategist_response` 保留 quant_justification dict（不被 :554 strip）| dict 進 filtered |
| T-P1-13 | regime 自算只用嚴格過去 1m closes（注入含「未收盤當前 bar」fixture，證未洩漏） | leak-free（QC look-ahead 驗）|

---

### 1.4 不變量保護（什麼**不改**）

- **tune_target=Demo fail-fast（evaluate.rs:310）不動** → Phase 1 結構上碰不到 live（E2 grep 證）。
- **±delta clamp / range / weight-sum=65（mod.rs:429-485）不動** → 既有 3 gate 全保留，quant gate 是**之後**疊加的第 4 gate（更嚴，不放寬）。
- **apply / persist / `learning.strategist_applied_params`（persist.rs）不動**。
- **`agent_adjustable:true` tunable 集不擴**（grid/ma/bb/funding 既有集，mod.rs:430 讀 `range.agent_adjustable`）；Phase 1 **無新可調參數**。
- **`validate_recommendation`（bool wrapper :387）簽名不動**（既有 direct-call 測試穩定）；quant gate 加在 `_with_reason` 變體，且只在 flag-ON 經由新 `rich` 路徑觸發（direct-call 測試傳 None edge → bypass，不破壞既有測試）。

---

### 1.5 降級 / rollback / kill-switch
- **flag default-OFF = 零行為改變**（payload/validate/Python filter 全走原路；rich struct None；quant gate bypass）。這是主 kill-switch。
- **edge_store absent / RwLock 讀爭用 / news_router None / regime 算失敗 / shadow 無 row** → 各欄 fail-soft 降級（None / "unknown" / absent），**cycle 不失敗**。
- **edge snapshot stale**（`is_fresh=false`）→ quant gate 主動拒（fail-closed），不是放行。
- **revert**：純 additive（builder fn 追加參數、struct 追加 Option fields、新 verify fn、2 新 reason、Python filter 保留分支）；git revert 單 commit，無 schema 副作用（**無新 migration** — edge/regime/shadow/news 全讀既有源）。
- **無新 mutable singleton**（edge_store/news_router 是既有 Arc 的 clone，不新建全域）→ 無 singleton table 登記。

---

### 1.6 待 E1 grep 確認 / 待 QC 定（build 前必解）
- **U2-P1 RESOLVED**：payload builder = evaluate.rs:**423**；signature 改為追加 `Option<&RichInputs>`。
- **U3-P1（E1+QC）**：`agent_adjustable:true` ParamRange 權威集 —— grep `strategies/*/params.rs` 逐策略列舉（grid/ma/bb_reversion/bb_breakout/funding_arb/liquidation_cascade_fade 已見大量 `agent_adjustable:true`）。Phase 1 不擴此集，但 QC 需確認「edge_estimates cell 的 (strategy,symbol) key 命名」與 `pair.strategy_name` 一致（`get_cell` 用 `"{strategy}::{symbol}"`，edge_estimates.rs:280；scheduler `pair.strategy_name` 來自 fills，已過 close-filter，**E1 必驗兩邊 strategy 名同字典** —— 若 fills 用 `ma_crossover` 而 edge json 用別名則 cell 永遠 absent → gate 永遠拒，等於 Phase 1 無效）。
- **U4-P1（QC，方向語意）**：quant gate 是否驗 `direction × param` 一致（如「正 edge → 該收緊還是放寬哪些參數」）。v1 **不卡方向**（只驗 cell 真實+fresh+validated+`shrunk_bps` 符號與 claimed 一致），避免 param 語意映射誤殺；方向映射表由 QC 在 Phase 1 build 前定，定了再加（additive）。
- **U5-P1（MIT）**：`ml_shadow` DB 聚合的確切 query（哪張 shadow 表、demo lane 是否有 row）—— 若 demo lane 結構上無 shadow fill（V017 是 paper-only ε-greedy），則 `ml_shadow` 欄 **Phase 1 恆 absent**，MIT 確認後可**從 payload 移除此欄**（不假裝有 ML 諮詢）。**這是誠實邊界**：ML shadow 對 demo scheduler 可能根本不可達，寧缺勿偽（CLAUDE「不偽造 AI 調用」）。
- **U6-P1（E1）**：`market.klines` demo 可讀性 + 1m closes 充足度（intraday backfill 已補，承 memory 06-15 條）；regime 自算的 N 窗 = `HurstConfig.window_size`（regime/hurst.rs），E1 確認 demo symbol 有足量 1m bar。

### Role chain（強制不可跳）
`PA → QC(leak-free? look-ahead? regime 自算 point-in-time? edge cell 命名對齊? quant gate news 零權重? MANDATORY) → MIT(ml_shadow demo lane 可達性 + shadow 語意正確性，MANDATORY) → E1(payload builder signature + struct fields + verify_quant_justification + 2 reason + Python filter 保留 + regime/shadow helper) → E2(對抗：T-P1-2/3/9/10 證 news-solo reject + news 零權重；flag-OFF IDENTITY；既有 3 gate 不破) → E4(flag-OFF byte-identical baseline + flag-ON 全 T-P1 + Linux demo engine 實證 cycle 真跑 reject/apply) → CC(Alpha Evidence Governance：news corroborating-only 證) → PM`

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

## POLICY 修正（operator 2026-06-17 裁定 — live-control 加固，**與 Phase 1 tuner 無關、可獨立 build/deploy**）

> 此兩項是 Phase 0 capability-token 機制（已 deployed）的**授權面收緊**，不碰 demo tuner。Phase 0 解決了「Rust enforcer 驗 token」；POLICY-1/2 解決「Python authorizer 在某些 live 路徑授權不足（操作員-role-only 即可鑄 token）」。親 grep 證實的當前狀態見下。

### POLICY-1 — `POST /reset-drawdown-baseline {engine:live}` 必須 5-gate + 顯式 override 路徑

**當前狀態（親 grep @HEAD）**：
- 路由 `reset_drawdown_baseline`（risk_routes.py:649-705）對 **任何 engine** 只查 `_require_risk_write(actor)` + operator-role（:671-682）+ engine 白名單（:686），**無 `all_five_live_gates_ok`**。
- `engine=="live"` 時 `client.reset_drawdown_baseline("live")`（risk_view_client.py:386）→ `_attach_live_token_if_live("reset_drawdown_baseline", {"engine":"live"})`（:415）**鑄 token**。但 minter（live_patch_token.py）**刻意不跑 5-gate**（「caller 必先過自己的 5-gate / operator gate」:246）。
- **結論**：今天 live drawdown-baseline reset = **operator-role 即可鑄 token + 過 Rust chokepoint** → 授權強度**低於**普通 5-gated live write（如 `/config/engine/live/global` 走 `all_five_live_gates_ok`）。這是 operator 點名要收緊的弱授權路徑。
- **override 場景已存在**：`live_halt_recovery.approve_live_halt_recovery`（live_halt_recovery.py:291）→ `_try_ipc_reset_live()`（:194）call 同一 `reset_drawdown_baseline("live")`。halt 時 **signed-auth 已自動撤銷**（recovery 的 `next_step="renew_signed_auth"` :331），故 `all_five_live_gates_ok(require_authz=True)` **結構上必然失敗** → 不能對此路徑硬套 5-gate，否則 halt 永遠無法恢復。這就是 operator 說的「5-gate-structurally-impossible 的 override case」。

**設計（buildable）**：
1. **`ResetDrawdownBaselineRequest` 加欄**（risk_routes.py:577）：`operator_override: bool = Field(default=False)`（default=False 保現行 caller 行為）+ 既有 `engine`/`reason` 不變。
2. **route `reset_drawdown_baseline`（:649）改授權邏輯**（`engine` 白名單檢查後、IPC call 前）：
   ```
   if body.engine == "live":
       if not body.operator_override:
           # 預設路徑：完整 5-gate（與 live RiskConfig 寫入同級）
           ok, reasons = live_preflight.all_five_live_gates_ok(actor, require_authz=True)
           if not ok:
               raise HTTPException(409, {"error":"live_gate_failed","gate_failed":reasons})
           # 過 5-gate → 既有 client.reset_drawdown_baseline 內鑄 token（不變）
       else:
           # OVERRIDE 路徑（halt-recovery 等 signed-auth 自動撤銷的結構不可達場景）：
           # 不跑 require_authz=True（會必然失敗）；但收緊到「operator-role + 顯式 override 旗標
           # + 5-gate 中 *非-authz* 子集」（live_reserved + operator-role + ALLOW_MAINNET + secret-slot；
           #   獨缺 signed-auth，因 halt 時本就撤銷）。E1 用 live_preflight 的細分 gate API（見下）。
           # 審計 DISTINCTLY（見 3）。
   ```
3. **5-gate 細分（E1 必確認 API）**：`live_preflight.all_five_live_gates_ok` 今天是 all-or-nothing（`require_authz` 只切第 5 gate）。override 路徑需「前 4 gate（live_reserved/operator/ALLOW_MAINNET/secret-slot）必過、第 5 gate（signed-auth）豁免」。**E1 必 grep `live_preflight.py`** 確認是否已有可回 per-gate 結果的函數（如 `all_five_live_gates_ok` 內部已分項算）；若無，E1 加薄 helper `four_gates_minus_authz_ok(actor)`（**只重組既有 gate 判斷，不新增 gate 邏輯，不放寬任何既有 gate**）。**禁**讓 override 路徑跳過 live_reserved/operator/ALLOW_MAINNET/secret-slot 任何一項。
4. **審計 DISTINCTLY**（`_record_reset_drawdown_audit` risk_routes.py:602）：override 路徑寫 `change_type=STATE_CHANGE` 但 `what` 標 `"Drawdown baseline reset (engine=live, OPERATOR_OVERRIDE, authz-gate-bypassed)"` + `new_value` 含 `{"override":true,"bypassed_gate":"signed_auth","caller":"halt_recovery|manual_override"}`，與普通 5-gated reset（`override:false`）在審計上**可區分查詢**。`auto_approve=True` 保留但 reason 必含 override 理由（route 強制 `operator_override=True` 時 `reason` min_length 提到 override；驗證在 route）。
5. **`live_halt_recovery._try_ipc_reset_live`（:194）改傳 `operator_override=True`**：halt-recovery 是 override 的**唯一合法自動觸發者**；它 call `reset_drawdown_baseline` 時須帶 override 旗標（否則新 5-gate 會卡死 recovery）。**E1 必確認** halt-recovery 走的是 route 還是直接 `risk_view_client`——若直接走 client（繞 route），則 override 旗標的授權檢查要下沉到 client 或 halt-recovery 自身已過 operator-approval gate（`approve_live_halt_recovery(actor_id)` :291 已是 operator-approved 入口）。**裁決**：halt-recovery 直接走 client（既有），它的 operator-approval 即是 override 授權；manual 路徑（route + `operator_override=True`）才需 route 層的 operator-role + override 旗標雙檢。
6. **無新 flag、無新 migration、無新 secret**（復用 live_preflight + Phase-0 token + change_audit_log）。

**測試矩陣**：
| # | 測試 | 預期 |
|---|---|---|
| TP1-1 | `engine=live, override=false`, 缺 5-gate（如非 live_reserved） | 409 `live_gate_failed`，0 reset |
| TP1-2 | `engine=live, override=false`, 過 5-gate | reset 成功 + token 鑄 + 普通審計 row（override:false）|
| TP1-3 | `engine=live, override=true`, operator-role, 前 4 gate 過、無 signed-auth（halt 模擬） | reset 成功 + **DISTINCT 審計 row**（override:true, bypassed_gate:signed_auth）|
| TP1-4 | `engine=live, override=true`, **非 operator-role** | 403（override 不繞 operator-role）|
| TP1-5 | `engine=live, override=true`, 前 4 gate 缺一（如非 ALLOW_MAINNET） | 409（override 只豁免 signed-auth，不豁免其餘 4 gate）|
| TP1-6 | `engine=demo`/`paper` | 維持現行（無 5-gate、無 token）|
| TP1-7 | halt-recovery `approve_live_halt_recovery` 端到端 | reset+unhalt 成功（override 路徑不被新 5-gate 卡死）|
| TP1-8 | 審計可區分查詢：override row vs 普通 row | change_audit_log 可按 `override` 欄分離（Root #8）|

### POLICY-2 — strategy toggle：demo-default 不變 + 新增 flag-gated 5-gate live mode

**當前狀態（親 grep @HEAD）**：
- `activate/pause/stop`（strategy_write_routes.py:146/176/206）→ `_sync_strategy_active(name, active)`（:48）**硬寫 `engine="demo"`**（:64）→ Rust 在 demo pipeline set_strategy_active，**永不觸 live**（且 demo 走 primary≠live 不需 token）。
- **這正是 operator 要保留的「routing to DEMO」現行行為。**
- **已有 flag-gated 5-gate live 模式的範本**：`toggle_dynamic_risk`（:72-142）對 `engine=="live"` 走 `all_five_live_gates_ok(require_authz=True)`（:99）+ `call_params_with_token("set_dynamic_risk_enabled", ...)`（:111）。POLICY-2 的 live strategy toggle **直接鏡像此 pattern**。

**設計（buildable）**：
1. **新設定/旗標 `OPENCLAW_STRATEGY_TOGGLE_LIVE_MODE` default-OFF**（env-gate，鏡像既有 pattern）：
   - OFF（預設）→ `activate/pause/stop` 行為**完全不變**（`_sync_strategy_active` 硬 demo，:64 不動）。
   - ON → 三路由接受 **可選 `engine` body 欄**（default 仍 demo）；`engine=="live"` 時走 5-gate live 模式。
2. **`activate/pause/stop` 路由改動**（:146/176/206）：保留現行 demo 路徑為預設。新增 live 分支（**僅 flag-ON 且 body.engine=="live" 時可達**）：
   - 讀 flag：flag-OFF 時即使 body 傳 `engine=live` 也**忽略**（強制 demo，保現行）+ 可選 409「live strategy toggle disabled」（避免靜默降級的歧義）。**裁決**：flag-OFF + `engine=live` → **409 `live_strategy_toggle_disabled`**（fail-loud，不靜默當 demo）；flag-OFF + 無 engine/`engine=demo` → 現行 demo（bit-identical）。
   - flag-ON + `engine=="live"`：
     ```
     ok, reasons = live_preflight.all_five_live_gates_ok(actor, require_authz=True)
     if not ok: raise HTTPException(409, {"error":"live_gate_failed","gate_failed":reasons})
     params = call_params_with_token("set_strategy_active",
                {"strategy_name": name, "active": <True|False>, "engine": "live"})
     await client.call("set_strategy_active", params=params)
     ```
   - **注意**：live 分支**不**走 `ORCHESTRATOR.activate_strategy`（那是 Python demo orchestrator 的狀態）；live toggle 是純 Rust IPC `set_strategy_active{engine:live}`（`set_strategy_active` 已在 Phase-0 `LIVE_WRITE_METHODS` allowlist → Rust chokepoint 自動驗 token）。E1 確認 live 分支只送 IPC、不動 Python orchestrator 狀態（避免雙真值）。
3. **新 helper `_sync_strategy_active_live(name, active)`**（鏡像 `_sync_strategy_active` :48 但 engine="live" + 5-gate + token）；**或**把 demo/live 分支收進一個 `_sync_strategy_active(name, active, engine, actor)`——**裁決**：新獨立 helper（demo 路徑零改動風險最小，符 surgical-change）。
4. **scope 維持 `strategy:write`**（`_require_strategy_write` :27）對 demo；live 分支**額外**疊 `all_five_live_gates_ok`（與 `toggle_dynamic_risk` 同：strategy:write scope 不足以授權 live，必補完整 5-gate）。
5. **無新 migration、無新 secret**（復用 Phase-0 `OPENCLAW_LIVE_PATCH_SECRET` + token mint）。新 flag 一個。

**測試矩陣**：
| # | 測試 | 預期 |
|---|---|---|
| TP2-1 | flag-OFF，`activate/pause/stop` 無 engine | demo（bit-identical 現行，`_sync_strategy_active` engine=demo）|
| TP2-2 | flag-OFF，body `engine=live` | 409 `live_strategy_toggle_disabled`（fail-loud，不靜默當 demo）|
| TP2-3 | flag-ON，`engine=demo`/無 engine | demo（現行）|
| TP2-4 | flag-ON，`engine=live`, 過 5-gate | live set_strategy_active + token 鑄 + Rust chokepoint 接受 |
| TP2-5 | flag-ON，`engine=live`, 缺 5-gate | 409 `live_gate_failed`，0 mutation |
| TP2-6 | flag-ON，`engine=live`, strategy:write scope 有但非 5-gate | 409（scope 不足以授權 live）|
| TP2-7 | flag-ON，`engine=live`, **無 token 直送 Rust**（繞 Python mint） | Rust chokepoint `live_authz_token_required`（Phase 0 已保證）|
| TP2-8 | live toggle **不**改 Python ORCHESTRATOR 狀態 | grep 證 live 分支只送 IPC |

### POLICY E1 派發 + Role chain
- **檔零重疊可並行**：POLICY-1（risk_routes.py + live_halt_recovery.py + live_preflight helper）∥ POLICY-2（strategy_write_routes.py + 新 flag）。兩者都依賴**已 deployed** 的 Phase-0 `live_patch_token` + Rust chokepoint（無需改 Rust）。
- **降級/rollback**：POLICY-1 `operator_override` 欄 default-False = 現行 caller 不受影響（但**注意**：上線後 `engine=live, override=false` 的現有 manual caller 會開始被 5-gate 卡——這是**預期收緊**，operator 已裁；halt-recovery 自動帶 override 不受影響）。POLICY-2 flag default-OFF = bit-identical。
- **Role chain**：`PA → E3(security：override 路徑只豁免 signed-auth 不豁免其餘 4 gate？live toggle 無 token 不可達？MANDATORY) → CC(硬邊界：5-gate 0 觸碰、override 審計可區分、Demo 放寬/Live 收緊政策，MANDATORY) → BB(live strategy toggle = exchange-facing 行為改變，MANDATORY) → E1-A(POLICY-1) ∥ E1-B(POLICY-2) → E2(對抗：override 繞 operator-role/繞前4gate；flag-OFF live=409 fail-loud) → E4(Linux 真 engine：override 路徑 halt-recovery 端到端、live toggle 過 chokepoint) → CC final → PM`

---

## 依賴/排序
- **獨立可部署**：Phase 0（純收緊，已 deployed）、Phase 1（demo-only，不需 Phase 0 因永不觸 live）、**POLICY-1/2（live-control 加固，依賴已-deployed Phase-0 token，不改 Rust）**。Phase 0 / 1 / POLICY 不同檔可並行 E1 wave。
- Phase 2 需 Phase 0+1 merged。Phase 3 需 Phase 0；demo 半可先於 Phase 2 出，live 半復用 Phase 2 機制。

## 新 flags（全 default-OFF）/ secrets / singletons / migrations
- flags：`OPENCLAW_STRATEGIST_RICH_INPUT`(P1)、`OPENCLAW_STRATEGY_TOGGLE_LIVE_MODE`(POLICY-2)、`OPENCLAW_STRATEGIST_PROMOTION_ENABLED`(P2)、`OPENCLAW_RISKCONFIG_AGENT_TUNING_ENABLED`(P3)。secret：`OPENCLAW_LIVE_PATCH_SECRET`（Phase 0，file-based，與 IPC secret 分離，已 deployed）。POLICY-1 無新 flag（`operator_override` 是 request 欄非 env-flag）。
- singleton 註冊（CLAUDE §九 merge 前）：RiskConfigDirectiveSink（P3）、live-patch token minter（P0，已 deployed）。**Phase 1 無新 singleton**（edge_store/news_router 是既有 Arc clone）。**POLICY-1/2 無新 singleton**。
- migration：`learning.strategist_promotions`(P2，V###，Linux PG 實證 dry-run + double-apply 必跑，build 時重查 next-free ≥V144)；復用 learning.directive_executions(P3)+V014 engine_events(P0 rejects)。**Phase 1 無新 migration**（edge/regime/shadow/news 全讀既有源）。**POLICY-1/2 無新 migration**（復用 live_preflight + Phase-0 token + change_audit_log）。

## 觀測 / kill-switch
- 每次 auto-tune 可見：get_strategist_cycle_metrics + 新 get_risk_directive_metrics（per-param apply/reject/last value/source）；GUI Risk tab 顯示 agent 動作+量化理由（node --check 前置）。
- audit：strategist_applied_params(P1)/strategist_promotions(P2)/directive_executions(P3)/V014 rejects(P0)，**全須 QA 實證會落 row**（audit_events 歷史為空，P8 風險）。
- kill-switch 分層：per-phase master flag OFF→凍該 phase；撤 LIVE_PATCH_SECRET→全 live patch fail-closed；GovernanceCore session-halt/daily-loss/drawdown veto→stress 時擋全 agent 調參；operator 促升確認是唯一 live 觸發。

## 待解不確定（建該 phase 前先解）
- **U1(Phase 0) RESOLVED**：grep 證實 `RiskViewClient._patch()`(risk_view_client.py:306) 送 `{patch, source}` **不含 engine** → Rust default paper（engine_routing.rs:97）→ 三 route 今天寫不到 live。Phase 0 真工作=三 model 加 engine 欄 + `_require_live_gates_if_live` gate + token（折入 §0.3）。
- **U2(Phase 1) RESOLVED**：payload builder = `build_strategist_eval_payload`（evaluate.rs:**423**，caller :159-165）；signature 改為追加 `Option<&RichInputs>`（§1.2）。:310 是 tune_target=Demo fail-fast guard（E2 已證 Phase 1 結構碰不到 live）。
- **U3(Phase 1) → 細分 §1.6**：agent_adjustable:true ParamRange 集不擴；命門是 **edge_estimates cell key（`strategy::symbol`，edge_estimates.rs:280）與 fills 的 `strategy_name` 必須同字典**（否則 cell 永遠 absent → quant gate 永遠拒 → Phase 1 無效），E1 必驗。ml_shadow demo-lane 可達性（U5-P1，MIT 確認，可能恆 absent → 誠實移欄）。regime 自算 leak-free（U6-P1，只用嚴格過去 1m closes）。quant gate 方向語意（U4-P1，QC 定，v1 不卡方向）。
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

