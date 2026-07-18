# 本地智能調參下單 Agent 系統 — Master Implementation Spec

- **Author:** PA · **Date:** 2026-06-17 · **Base commit:** `0cf086c1`
- **Status:** ⚠️ DORMANT（记于 2026-07-18 文档审计）— 原文 "design (read-only) → pending adversarial review (E3+CC+E2) → phased build+deploy"；本 spec 不在当前 `TODO.md` active queue 或任何 `initiative_index`，非 pending-build。当前 autonomy 方向 = profit-first 自主 loop（2026-07-08+）。恢复须 PM 确认 + `TODO.md` gate。（注：本 spec 已将 live RiskConfig 变更设为「人工促升闸、永不自動套用 live」，见下 §决策 2；此非 live 安全隐患，仅 dormancy 标注。）
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

## PHASE 2 — demo→live 促升管線（人工閘）— BUILD-READY（2026-06-17 PA in-place rewrite）

**目標**：把 demo-tuned 策略參數，經 **operator 確認 + 5-gate + criteria gate + Phase-0 token**，促升到 LIVE 引擎。**策略參數 only，永不 RiskConfig。永不自動呼。** flag `OPENCLAW_STRATEGIST_PROMOTION_ENABLED` default-OFF。

> **★★★ 親 grep 翻案：Phase 2 不是 greenfield，是 ENHANCEMENT。** 已存在的 `strategist_promote_routes.py`（`strategist_promote_router`，已 wired 進 `main.py:280-281`，`strategy_write_routes.py:74` 已把它認作唯一合法 live-promote lane）**已實作絕大部分骨架**：兩步 confirm preview/apply、live 5-gate（`_apply_target_gate`→`executor_routes._verify_live_gate`）、**Phase-0 token 已鑄**（`call_params_with_token("update_strategy_params", ipc_params)` 行 700-701）、IPC dispatch（`update_strategy_params` 經既有 chokepoint+handler）、change_audit_log。**Phase 2 的工作 = 在此既有路徑上補三個結構性缺口**：(A) 加 flag gate（現無）、(B) 加 Rust 純邏輯 **EDGE-ANCHORED** criteria gate（現完全沒有 — 任何穩定 demo row 都可促升；§2.4 已採 QC NEEDS_CHANGES 重寫成 beta-neutral edge-anchored 閘，**不靠 demo PnL**）、(C) 把 audit 從 fire-and-forget 升級成 **fail-closed 同步寫 `learning.strategist_promotions`**，並 (D) 新建 **EXACT reverse-promote（demote）**（現完全不存在）。**E1 必先讀全 `strategist_promote_routes.py` 確認當前行為，不得盲信本 spec 把它當空白。**

---

### §2.0 既有路徑的親 grep 事實（E1 必先核對）

| 事實 | 證據 | 對 Phase 2 的含義 |
|---|---|---|
| promote route 已 live + 已過 5-gate + 已鑄 token | `strategist_promote_routes.py` 全檔；token mint 在 :699-701（live target 才鑄） | **不重建 route。token+5-gate 已 done，只疊 flag/criteria/audit。** |
| `update_strategy_params` 已在 `LIVE_WRITE_METHODS` | `live_authz.rs:64`；chokepoint `dispatch.rs:127-211` | **Rust 端 token 強制已部署**；route live 分支不鑄 token 即被自己的 chokepoint 拒（自封）。token 必鑄（已鑄）。 |
| `promote_params_to_live()`(mod.rs:417-440) 是 unwired STUB | `mod.rs:403` 「Not invoked internally」 | **它走 `promote_cmd_snapshot()`（Live cmd slot），不經 dispatch chokepoint**（in-process Rust→Live channel）。**現有 Python route 不呼它**，而是走 Python IPC `update_strategy_params{engine:live}` 經 chokepoint。兩條路皆達 Live `UpdateStrategyParams`。**裁決見 §2.3。** |
| IPC merge 是 **deep MERGE 非 replace** | `merge_strategy_params_json`(strategy_params.rs:17-42)：`for (k,v) in incoming { current_map.insert(k,v) }` — **只插入/覆寫，永不刪 key** | reverse-promote 必須 EXACT（§2.5）。 |
| `get_strategy_params` 回 **完整 typed param set** | `handle_get_strategy_params`(strategy_params.rs:124-134)→`strategy.get_params_json()`（完整序列化，非 partial） | demote 用它捕捉「促升前完整 live param set」可行（§2.5）。 |
| 現有 audit = fire-and-forget change_audit_log，**非 fail-closed，無專表** | `_record_promote_audit`(:364-445) try/except 吞錯「audit must never break the request」(:444) | **違反 must-fix C**（live param 改 + 無耐久 audit row = P8）。Phase 2 改成同步 fail-closed + 專表（§2.6）。 |
| 現無 flag gate | grep `STRATEGIST_PROMOTION_ENABLED` = 0 hit（全 repo） | **任何穩定 demo row 今天即可促升 live（只要 operator 過 5-gate）**。Phase 2 加 flag default-OFF + criteria gate。 |
| 現無 demote/reverse-promote 任何路徑 | grep demote/reverse_promote = 0 命中（除 canary stage demote 無關） | **demote 是 net-new**（§2.5）。 |
| criteria gate 完全不存在 | promote route 不查任何 edge/drawdown/soak | **criteria gate 是 net-new Rust 純邏輯，EDGE-ANCHORED**（§2.4 — reuse `edge_estimates.validation_passed` OOS 鏈 + `cost_gate_live_with_slippage` cost wall + canary soak metric + LIVE drawdown SSOT；**不靠 demo PnL**，避 down-beta 假陽性）。 |

---

### §2.1 flag wiring（必先做，最低風險）

- 新 env flag `OPENCLAW_STRATEGIST_PROMOTION_ENABLED`，default-OFF（讀法鏡像 Phase-0 `secret_env` / 既有 bool flag helper；E1 grep 既有 `os.environ.get(...)=="1"` 慣例對齊）。
- **gate 位置 = `strategist_promote_routes.py` 的 `confirm=true` + `target_engine=="live"` 分支入口**（Step 5 `_apply_target_gate` 之前）。flag-OFF + 此分支 → **409 `promotion_disabled`**（fail-loud，不靜默降級成 demo，鏡像 POLICY-2 的 409 姿態）。
- **flag 不擋**：`confirm=false`（preview）、`target_engine=="paper"`、demote 的 preview。**flag-OFF 時 live promote 完全不可達 = bit-identical 行為**（除新增的 409 拒絕碼）。
- demote（§2.5）共用同一 flag（live demote 也須 flag-ON）。

---

### §2.2 5-gate + Phase-0 token（已 done，E1 只驗不改）

- live promote 的 5-gate = `_apply_target_gate(actor,"live")`→`executor_routes._verify_live_gate(actor)`（內部走 `all_five_live_gates_ok(actor, require_authz=True)`，live_preflight.py:247）。**E1 驗 `_verify_live_gate` 確走 `require_authz=True`**（live 必須含 signed-auth gate；與 POLICY-1 override 場景相反，promote 無 halt-recovery 例外，永遠全 5 gate）。
- token mint = `call_params_with_token("update_strategy_params", ipc_params)`（live_patch_token.py:235）**已在 route :699-701**。non-patch 類 hash 對象 = params 去 token 三欄 + engine（`hash_target_for` 自動處理）。**E1 不改 token 邏輯**；只確認 **criteria gate 與 audit 寫在 token mint＋IPC dispatch 之間/之後的正確時序**（§2.6）。
- **順序（route confirm=true live 分支）**：① flag gate（§2.1）→ ② operator-role（既有 Step 2，always）→ ③ 取 source row（既有 Step 3）→ ④ **criteria gate（§2.4 新，EDGE-ANCHORED：route 算 soak/fills/boundary metric + 解析 active-symbol → 唯讀 IPC `evaluate_promotion_criteria`，engine 自查 live edge cells + cost wall + 跑判定）**→ ⑤ 5-gate `_apply_target_gate`（既有 Step 5）→ ⑥ **捕捉 pre-promotion 完整 live snapshot（§2.5 新，供 demote）**→ ⑦ token mint（既有 :699-701）→ ⑧ IPC `update_strategy_params`（既有 Step 6）→ ⑨ **同步 fail-closed audit 寫 `learning.strategist_promotions`（§2.6 新）**。**criteria gate 在 5-gate 前或後皆可（兩者皆 deny-on-fail），裁決放 5-gate 前**（criteria 是業務前提，先廉價拒不合格者，再跑較重的 signed-auth 驗證）。criteria gate 的 edge cell 取得是**唯讀 IPC**（不入 `LIVE_WRITE_METHODS`，token 豁免），不改任何 state。

---

### §2.3 promote 落地路徑裁決（不呼 stub，沿用既有 chokepoint 路徑）

- **裁決：Phase 2 不接 `promote_params_to_live()` stub（mod.rs:417），沿用既有 Python route 的 `update_strategy_params{engine:live}` IPC 路徑。** 理由：(1) stub 走 `promote_cmd_snapshot()` 的 in-process Rust→Live channel，**繞過 dispatch chokepoint**=繞過 Phase-0 token 強制（U-P0-3 類繞過風險）；(2) 既有 route 路徑已過 chokepoint+token+handler，**安全面已驗證**；(3) master-spec 目標文字「接 promote_params_to_live」的**實質意圖是「把 demo-tuned 參數促升到 live」**，既有 route 已達成此語意，stub 是早期未完成的替代實作。
- **stub 處置**：`promote_params_to_live()` 維持 **not-auto-called STUB**（不刪，保 additive headroom；master-spec/CLAUDE「learning 不可自動改寫 live」= P7，stub 永不被任何自動 caller 觸發）。E2 必 grep 證 `promote_params_to_live` 仍 0 caller（除 test）。**不新增 IPC method `promote_strategist_params`**（原 spec §2 的提議作廢——既有 `update_strategy_params` 已足，新 method 只增表面積且要再過一輪 chokepoint allowlist 維護）。
- **U1（E1 必 grep）**：確認 `update_strategy_params` 經 chokepoint 後 dispatch 到 `handle_update_strategy_params`(strategy_params.rs:51)，其 merge 行為（deep merge）正是 §2.5 demote-exactness 的根因。

---

### §2.4 criteria gate — EDGE-ANCHORED / beta-neutral（net-new，REUSE in-tree 機制，鏡像 canary Stage 3→4）

> **★★★ QC NEEDS_CHANGES 重寫（2026-06-17）。** 原 §2.4 提議的「`realized_pnl_net >= 0` + `drawdown_breach==0` + `stable_cycles>=N`」criteria 在量化上**錯誤**：demo realized PnL 在多頭/趨勢 regime 下會被 **down-beta 污染**而出現假陽性正值（承 [[project_2026_06_15_demo_loss_rootcause_grid_trend]] + profit-diagnosis 教訓：同一靜態 config 06-12 開多賺、06-15 開空虧，方向全由市場 regime 定非 alpha）。「demo 賺錢」**不是 edge 存在的證明**，只是 regime bet 的副產品（CLAUDE Alpha Evidence Governance：bull-only positive = `regime-bet / learning-only` 非 promotion proof）。**criteria 必須換成 edge-anchored、beta-neutral、引用既有 battle-tested gate 的量化可辯護閘。** 本節不再自定義新的盈利/穩定性度量，而是**復用樹內既有的 walk-forward OOS 顯著性鏈 + live cost wall + canary 風控 metric**。

---

#### §2.4.A 設計總則（為何 edge-anchored）

促升 live 的唯一可辯護證據 = **leak-free 的 OOS alpha 顯著性**，不是 demo PnL。樹內已有兩條 battle-tested 顯著性防線，criteria gate **REUSE 它們，不重新推導**：

1. **`edge_estimates` cell 的 `validation_passed` 鏈**（James-Stein producer，cost_gate 同源）= 每 `(strategy, symbol)` cell 的 **walk-forward OOS 顯著性 verdict**。由 `edge_estimate_validation.py` 計算：`PSR ≥ 0.95`（runtime mode 0.975）、`DSR ≥ 0.90`（runtime 0.95，**已 Bonferroni-deflated for multiple testing** — `p_value_bonferroni` over `m_tests`）、`oos_n ≥ 30`（runtime 60）、`wf_windows ≥ 2`（runtime 3）。`validation_reason` 在 PASS 時為 `"passed"`，FAIL 時為 `"insufficient_total_samples"` / `"psr_below_threshold"` / `"dsr_below_threshold"` 等穩定 token。**這就是 per-cell 的 deflated-Sharpe + PSR + OOS-n 顯著性閘——它本身已是 QC 要的「DSR/PBO/OOS significance bar」，且是 per (strategy, symbol) 而非 per canary-stage。**

2. **`cost_gate_live_with_slippage`**（gates.rs:288-353）= **live cost wall**。它對正 edge cell 要求 `fresh && from_runtime_field && validation_passed` 三者全真，然後 `shrunk_bps ≥ fee_bps/win_rate × safety_multiplier`（`fee_bps = 2×(fee_rate + slippage)×10000` round-trip taker+slippage cost wall，win-rate 加權）。**這就是 QC 要的「demo→live degradation haircut：shrunk_bps 須清 live cost wall（taker fee + slippage + 保守滑點），不僅 > 0」。** criteria gate **直接以同一 cost model 為 bar**（同 `risk_config_live.toml` 的 `slippage.*` / `cost_gate_*` 參數），不另造成本模型。

criteria gate = 把這兩條 **per-cell** 的 live-grade 防線，**aggregate 成 per-strategy 的 majority/weighted coverage 判定**（因 strategist param 按 `(engine_mode, strategy_name)` apply 跨該策略所有 active symbol — `strategist_promote_routes.py:47-48` 親證 schema 僅 `(engine_mode, strategy_name)`），再疊上 canary Stage 3→4 的 soak / wall-clock / drawdown / boundary 風控 metric（凡 per-strategy 可得者）。

---

#### §2.4.B BINDING GATE — edge-anchored hard requirement（per active-symbol cell）

對被促升的 `strategy`，解析其 **active-symbol 集合**，逐 cell 套 live-grade 檢查，再 majority/weighted coverage 判定。

**active-symbol 集合解析（E1）**：`strategy` 的 active symbol = `strategy_params_live.toml` 該策略段的 `allowed_symbols`（staging gate）∩ **pinned 交易 universe**（`scanner_config.toml` `pinned_symbols`，25-sym；非 `max_symbols` 觀測 tier — 承 [[bundle-recorderv2]] `is_pinned` 是硬交易 gate 的教訓，只有 pinned symbol 真開倉）。**理由**：promote 的 live blast radius = 該策略在 live 真會交易的 symbol 集，不是它名義 allowed 的全集，也不是觀測 tier。若 `allowed_symbols` 為空/未設 → 該策略 live 不交易任何 symbol → criteria `Reject("no_active_symbols")`（無 blast radius 即無促升意義，fail-closed）。

**per-cell PASS 條件（全真才算該 cell qualified）**：對每個 active symbol，從 **live `edge_estimates` snapshot**（注意：必查 **live engine** 的 edge cell，不是 demo edge — promote 的是 live 行為，QC 要 demo→live degradation haircut 用 live cost wall；demo edge 只在 §2.4.D soak metric 用）取 `get_cell(strategy, symbol)`：
1. `cell` 存在（None → 該 symbol unqualified）。
2. `cell.validation_passed == true`。
3. `cell.validation_reason == "passed"` —— **REAL OOS-PASS，拒 explore-grace-only**。**rationale**：`validation_passed` 由 `edge_estimate_validation.py` 的 walk-forward OOS 鏈寫；explore-gate（`explore_eligible`/`explore_remaining`）是 `explore_quota_sink.py` 的**獨立 overlay writer**，只新增 explore 兩欄、**不觸碰 `validation_passed`**（親 grep 證 explore_quota_sink.py:23-29「只新增 explore_eligible / explore_remaining 兩欄，原樣保留所有既有欄位」）。且 live gate `cost_gate_live_with_slippage` 結構上**完全不讀** `explore_eligible`/`explore_remaining`（gates.rs comment「此欄只被 demo gate 讀；live gate 不引用，是 demo↔live 隔離的單一守門點」）。→ criteria gate **同樣不讀 explore 欄**，且額外要求 `validation_reason=="passed"`（不是任何 `insufficient_*`/`*_below_threshold`），確保「explore-gate 放行的 demo-only 探索 cell」**結構上無法**冒充 live-qualified。
4. `cell.is_fresh(now, edge_ttl) == true`（`edge_ttl = slippage_cfg.edge_estimate_ttl_secs`，與 live cost_gate 同源 TTL）。
5. `cell.from_runtime_field == true`（runtime-derived bps，非 legacy `shrunk_bps` 回退 — P1-09）。
6. `cell.shrunk_bps > 0.0`。
7. `cell.n_trades >= 30`（OOS 樣本下界，對齊 `edge_estimate_validation.min_oos_n=30`；QC 可上調至 runtime `min_oos_n=60`）。
8. **live cost wall（degradation haircut）**：`cell.shrunk_bps >= fee_bps/clamp(win_rate) × safety_multiplier`，其中 `fee_bps`/`win_rate`/`safety_multiplier` **完全 reuse `cost_gate_live_with_slippage` 的同一算式與同一 `risk_config_live.toml` slippage 參數**（不另造成本模型）。即「該 cell 的 shrunk edge 在扣 live round-trip taker+保守滑點+win-rate 加權後仍為正」。

**coverage 判定（majority / weighted，NOT single cherry-picked cell）**：
- `qualified_cells` = active symbol 中 per-cell 8 條全過者。
- **weighted-coverage**：以各 cell `n_trades` 為權重（樣本多的 cell 權重高），`coverage = Σ n_trades(qualified) / Σ n_trades(all active)`。要求 `coverage >= COVERAGE_FLOOR`（QC 釘，建議 ≥0.6 majority）**AND** `qualified_count >= MIN_QUALIFIED_CELLS`（QC 釘，建議 ≥ ceil(active_count/2)，至少絕對下界如 2，防單 cell 高 n_trades 撐起整個 coverage）。
- 任一不足 → `Pending("edge_coverage_below_floor: qualified=X/Y coverage=Z")`（not Reject — 等更多 cell validated）。
- **單 cell cherry-pick 結構上被擋**：coverage 是「跨 active symbol 的 weighted 比例」，一個 validated cell 無法讓 25-sym 策略過 majority。

> **★ 為何 binding gate 用 live edge（不是 demo edge）**：QC 要的核心 = 「demo→live degradation haircut，shrunk_bps 須清 LIVE cost wall」。live `edge_estimates` 的 cell 已是 producer 對 live engine_mode 算的 runtime-mode 顯著性（更嚴的 `min_oos_n=60`/`psr_min=0.975`/`dsr_min=0.95`）+ live cost wall。**這是把「促升前 demo 看起來好」這個假陽性源頭直接繞過**——不問 demo PnL，只問「live engine 對該策略×該 symbol 是否已有 OOS-validated、清 live 成本牆的正 edge」。若 live edge 從未 validated（今天 0 validated cell 的真實狀態），coverage=0 → 永遠 `Pending`，**這正是 desired fail-closed 行為**（§2.9 誠實標）。

---

#### §2.4.C MIRROR canary Stage 3→4 — soak / wall-clock / boundary（可得者）

QC 要求鏡像 `canary_promotion.rs` 的 Stage 3→4 gate（PA 已親讀 evaluate_stage3_promote, canary_promotion.rs:329-419）：`wall_clock ≥ 21d` + `≥ 72h since last param change` + `≥ 30 attributable demo fills` + `DSR > 0`（deflated for sweep K）+ `PBO ≤ 0.5` + `attribution_chain_ok ≥ 0.7` + `boundary_violation_count = 0`。

**FEASIBILITY 裁決（PA 親查，MANDATORY — 不發明不存在的 metric）**：

| canary Stage 3→4 metric | 對 strategist-tuned param 是否可得？ | 裁決 |
|---|---|---|
| `wall_clock ≥ 21d` | **可得** — `learning.strategist_applied_params` 有 `applied_at`，可算「該策略當前 param-version 的 demo soak wall-clock」 | **採用**：`demo_soak_wall_clock_ms >= 21d`（`SOAK_WALL_CLOCK_MS`，鏡像 `STAGE3_WALL_CLOCK_MS`）。 |
| `≥ 72h since last param change` | **可得** — 同表時序，「自上次 `params_json` 變動以來的 wall-clock」 | **採用**：`ms_since_last_param_change >= 72h`（`STABLE_SINCE_CHANGE_MS`，鏡像 canary sample_floor 72h）。**取代原 §2.4 的 `consecutive_stable_cycles`**（72h wall-clock 比「N 輪 loop」更穩健——loop 頻率變動不影響）。 |
| `≥ 30 attributable demo fills` | **可得** — `trading.fills WHERE engine_mode='demo'` 該策略 soak 窗內 fills（鏡像 evaluate.rs:417 同源） | **採用**：`attributable_demo_fills >= 30`（`MIN_ATTRIBUTABLE_FILLS`，鏡像 `STAGE2_ENTRY_FILLS_MIN`=30）。**樣本充足性閘。** |
| `DSR > 0`（deflated for sweep K） | **NOT 可得 per (strategy, param-version)** — canary 的 DSR 來自 W-AUDIT-6 pipeline，對 **canary executor config stage** 計算，**不存在 per strategist-tuned param 的 DSR row**（無 learning 表存它）。 | **NOT 重新發明。** 以 §2.4.B 的 `validation_passed` 鏈作 **canonical 顯著性 bar**——它本身就是 per-cell 的 **deflated-Sharpe（DSR≥0.90 Bonferroni over m_tests）+ PSR≥0.95 + OOS-n** verdict（`edge_estimate_validation.py:33-34,196-209`）。即「sweep K 的 multiple-testing deflation」已由 `edge_estimate_validation` 的 Bonferroni `p_value_bonferroni`/`m_tests` 編碼。**criteria 的顯著性權威 = validation_passed 鏈，不是 canary DSR。** |
| `PBO ≤ 0.5` | **NOT 可得 per strategist-param**（同 DSR，PBO 是 W-AUDIT-6 對 canary stage 算，無 per-param row） | **NOT 重新發明。** 同上以 validation_passed 鏈代替（PBO 的 overfit 防護由 walk-forward OOS + Bonferroni deflation 在 `validation_passed` 內承擔）。 |
| `attribution_chain_ok ≥ 0.7` | **可得（additional，非 binding）** — `[55]` attribution_chain_ok healthcheck 是 per-strategy 可查 metric（既有 healthcheck，不是 per-param） | **採用為 additional gate（where available）**：若該 healthcheck 對該策略可查且 `< 0.7` → `Pending("attribution_chain_below_floor")`（鏡像 `STAGE3_ATTRIBUTION_RATIO_FLOOR=0.7`）；查不到（None）→ **Pending**（不 fail，鏡像 canary None→Pending 語意，等下次），**但不作為唯一 binding bar**（binding 是 §2.4.B edge coverage）。 |
| `boundary_violation_count = 0` | **可得** — demo soak 窗內 risk-envelope/drawdown 越界次數（同 canary boundary 語意，per-engine demo 可查） | **採用**：`demo_boundary_violation_count == 0` → 否則 `Reject("demo_boundary_breach")`（root #5 硬拒）。 |

**結論（metric-sourcing decision，明確記錄）**：
- **顯著性 canonical bar = `validation_passed` OOS 鏈（§2.4.B）**，不是 canary DSR/PBO（後者對 strategist-tuned param **不存在** per-param row，PA 親查確認，**不發明**）。validation 鏈已內含 DSR≥0.90(Bonferroni-deflated)/PSR≥0.95/OOS-n≥30。
- **canary 可移植 metric = wall-clock(21d) + since-change(72h) + attributable-fills(30) + boundary(0)**，全部從 `learning.strategist_applied_params` + `trading.fills` + demo risk metric query 可得（與既有 route `_fetch_latest_applied_row` 同源 DB lane）。
- **attribution_chain_ok = additional where-available**（None→Pending，非 binding）。

---

#### §2.4.D DRAWDOWN bound = LIVE risk_config SSOT（非 demo envelope）

QC 要求：drawdown bound 用 **LIVE** `risk_config_live.toml` 的 `session_drawdown_max_pct=12` / `daily_loss_max_pct=7`（PA 親查確認），**不是** demo envelope（`risk_config_demo.toml` `session_drawdown_max_pct=25` / `daily_loss_max_pct=15`）。

**設計**：`demo_boundary_violation_count`（§2.4.C）的「越界」定義 = demo soak 期間 **demo 引擎的 realized drawdown / daily-loss 是否曾突破 LIVE（較緊）envelope**——即用 `12% session DD / 7% daily loss` 作上界量測 demo 軌跡，**不是用 demo 自己的 25%/15%**。理由：促升的是 live 行為；demo 在寬鬆 envelope 下「沒爆」不代表它在 live 緊 envelope 下安全。E1：metric query 比對 demo soak 窗 max session-drawdown / max daily-loss vs LIVE SSOT 值（`risk_config_live.toml`，**SSOT 讀取，不硬編碼 12/7**）；任一曾突破 → `demo_boundary_violation_count > 0` → `Reject("demo_breached_live_drawdown_envelope")`。

---

#### §2.4.E 模塊位置 + 輸入 struct + 輸出 enum + 判定邏輯（Rust 純函數）

**模塊位置**：新 `strategist_scheduler/promotion_criteria.rs`（sibling extract，鏡像 `cycle_counters.rs`/`rich_inputs.rs` 範本；mod.rs 加 `mod promotion_criteria;`）。**純函數，零 IO**——所有 metric（含 per-cell edge 數據）由 caller 預先 query/snapshot 後以 struct 傳入，鏡像 canary `is_promote_eligible(stage, metrics)` 簽名。

**輸入 struct `PromotionCriteriaInput`**：
```
PromotionCriteriaInput {
    // §2.4.B edge coverage（per active-symbol cell，caller 從 live EdgeEstimates snapshot + active-symbol 解析後填）
    active_cells: Vec<ActiveCellEdge>,   // 每 active symbol 一筆
    // §2.4.C/D canary 可移植 soak/風控 metric
    demo_soak_wall_clock_ms: i64,
    ms_since_last_param_change: i64,
    attributable_demo_fills: i64,
    demo_boundary_violation_count: i64,  // §2.4.D：以 LIVE envelope 量測
    attribution_chain_ok_ratio: Option<f64>,  // additional where-available；None→Pending
    // live cost model 參數（reuse risk_config_live.toml slippage.*，caller 傳入或 Rust 直讀 risk_config）
    fee_bps_round_trip: f64,
    cost_gate_safety_multiplier: f64,
    cost_gate_win_rate_floor: f64,
    edge_estimates_fresh: bool,          // snapshot 級 is_fresh(now, edge_ttl)
    // §2.4.F direction bound
    tuned_param_names: Vec<String>,      // 本次 promote 實際改動的 param key
}

ActiveCellEdge {
    symbol: String,
    present: bool,                // get_cell 是否存在
    validation_passed: bool,
    validation_reason: String,    // 必須 == "passed"
    from_runtime_field: bool,
    shrunk_bps: f64,
    win_rate: f64,
    n_trades: u64,
}
```
> **注意**：`is_fresh` 是 snapshot-level（單一 `_meta.updated_at` 對全 snapshot，edge_estimates.rs:317-339），故 freshness 以 `edge_estimates_fresh` 一個 bool 傳入（caller 對 live snapshot 算一次），per-cell 不重複帶 ts。

**輸出 enum `PromotionVerdict`**（鏡像 canary `PromoteVerdict`）：`Eligible` / `Pending(reason)` / `Reject(reason)`，reason 為穩定短 token（GUI surface + audit row 用）。

**判定邏輯（fail-closed，順序短路）**：
1. **direction bound（§2.4.F）**：`tuned_param_names` 含任一不在 v1 allowlist 的 param → `Reject("param_direction_ambiguous: <name>")`。
2. **active-symbol 空**：`active_cells` 為空 → `Reject("no_active_symbols")`。
3. **boundary**：`demo_boundary_violation_count > 0` → `Reject("demo_breached_live_drawdown_envelope")`（root #5）。
4. **snapshot freshness**：`!edge_estimates_fresh` → `Pending("edge_snapshot_stale")`。
5. **attributable fills**：`attributable_demo_fills < MIN_ATTRIBUTABLE_FILLS(30)` → `Pending("insufficient_attributable_fills")`。
6. **wall-clock soak**：`demo_soak_wall_clock_ms < SOAK_WALL_CLOCK_MS(21d)` → `Pending("soak_below_21d")`。
7. **since-change**：`ms_since_last_param_change < STABLE_SINCE_CHANGE_MS(72h)` → `Pending("param_changed_within_72h")`。
8. **edge coverage（binding，§2.4.B）**：對每 cell 套 8 條 per-cell 檢查（含 live cost wall haircut），算 weighted `coverage` + `qualified_count`；`coverage < COVERAGE_FLOOR` 或 `qualified_count < MIN_QUALIFIED_CELLS` → `Pending("edge_coverage_below_floor: q=X/Y cov=Z")`。
9. **attribution（additional）**：`attribution_chain_ok_ratio` == None → `Pending("attribution_not_computed")`；`< 0.7` → `Pending("attribution_chain_below_floor")`。
10. 全過 → `Eligible`。

> **fail-closed 順序註**：direction bound 與 boundary breach 是 **Reject**（硬拒，永不因等待而 Eligible）；其餘樣本/soak/coverage 不足是 **Pending**（等更多證據）。**edge coverage 是 binding gate**——即使 soak/fills/wall-clock 全過，coverage 不足仍 Pending（沒有 OOS-validated 清 live 成本牆的正 edge = 沒有可促升的 alpha，root #5/#6/#12）。

---

#### §2.4.F v1 DIRECTION BOUND（限定 unambiguous-direction param）

QC 要求：v1 只允許促升**方向語意明確**的 param（如 cooldown / threshold 收緊），denylist 方向模糊者，直到 QC 的 direction×param consistency map 建立（25-sym live blast radius 使方向倒置的促升高風險）。

**v1 ALLOWLIST（unambiguous「tighten = 更保守 = 交易更少」單調語意）**（PA 親查 param_ranges 後初擬，**QC MANDATORY 復核並釘死最終 allowlist**）：
- `cooldown_ms`（↑ = 進場間隔更長 = 交易更少，結構性保守）。
- `min_events` / `min_*` 樣本/事件下界（↑ = 要求更多證據才進場）。
- entry threshold 類「值越高越難進場」者：`funding_threshold`、`adx_threshold`、`*_threshold_usd`（`default_threshold_usd`/`btc_threshold_usd`/`eth_threshold_usd`）（↑ = 要求更強信號）。

**v1 DENYLIST（方向模糊，promote-blocked 直到 consistency map）**：
- 所有 `weight_*`（`weight_adx`/`weight_regime`/`weight_volume`/`weight_momentum` 等）——權重重分配可**反轉有效信號方向**，非單調。
- `take_profit_pct`、`max_hold_ms`、`expected_periods`（持倉時長/止盈，方向取決於 regime，非單調安全）。
- `entry_basis_ratio`、`max_basis_pct`、`reverse_cascade_ratio`、`total_cost_bps`（basis/反轉/成本旋鈕，方向語意需 map）。
- sizing/notional 類（已 `agent_adjustable:false`，本就不在面，但顯式列入 denylist 防回歸）。

**機制**：direction bound 在 `promotion_criteria.rs` 判定邏輯 step 1（`tuned_param_names` 任一 ∉ allowlist → `Reject`）。**allowlist 是 const `&[&str]`，與 param_ranges `name` 對齊**。E1：`tuned_param_names` = 本次 promote payload 相對 pre-promotion 真正改動的 key（route 算 diff 傳入）。**QC 釘死 allowlist 前，E1 用 PA 初擬 allowlist 並標 PROVISIONAL。**

---

#### §2.4.G 資料來源裁決（async/sync 邊界 — 不變，重申）

criteria gate 的**純邏輯**在 Rust（`promotion_criteria.rs`），**資料 query 放 Python route**（route 已 async + 有 `get_pg_conn()`/IPC；`_fetch_latest_applied_row` 已 query `strategist_applied_params`）。route 算齊所有 metric（含經唯讀 IPC `get_edge_estimates_snapshot`-類取 live edge cells，或 route 直讀 producer 寫的 live `edge_estimates.json` 快照 — E1 二選一，**偏好經 IPC 取 engine 記憶體中 live snapshot 以保 freshness 一致**）→ 填 `PromotionCriteriaInput` → 經**新唯讀 IPC `evaluate_promotion_criteria`**（不在 `LIVE_WRITE_METHODS`，唯讀豁免 token；回 `verdict + reason`）。route 拿到 `Reject`/`Pending` → **409 `criteria_not_met` + reason**，0 IPC promote、0 audit-as-applied（但寫 denied audit row §2.6）。
- **為何 Rust 判定**：deterministic 風控邏輯，Rust-first（`feedback_new_code_rust_first`）+ 與 Phase 3 RiskConfig promote 共用同一 criteria 模塊（headroom）。
- **edge cell 取得**：promote 路徑需 live `edge_estimates` 的 per-cell 數據。**裁決：經唯讀 IPC 由 engine 回傳 live `EdgeEstimates` snapshot 的 per-cell（strategy 的 active symbol 子集）**——保證與 live cost_gate 看到的是同一份記憶體 snapshot（freshness/runtime_field 一致），避免 route 自讀檔產生「route 看到的 edge ≠ engine 看到的 edge」漂移。若 E1 評估「在 `evaluate_promotion_criteria` IPC handler 內 engine 直接自查 `Arc<RwLock<EdgeEstimates>>` + 解析 active-symbol + 跑判定」更乾淨（engine 本就持有 edge snapshot + risk_config slippage 參數）→ **此為首選**：route 只傳 `strategy` + soak/fills/boundary metric + `tuned_param_names`，engine 自查 edge + cost model + 跑 `promotion_criteria.rs`，回 verdict。**E1 二選一並在報告釘死；QC 驗閾值不受實作語言/取得路徑影響。**
- **fallback（若新 IPC 過重）**：criteria 純邏輯可在 Python route 內聯——但 edge cell 仍須經唯讀 IPC 取 live snapshot（不可 route 自讀檔當權威），且閾值常數須與 Rust const 對齊。**PA 偏好 Rust-first + engine 自查 edge**。

---

**待 QC 釘死（MANDATORY，PA 不自定閾值）**：
1. **`COVERAGE_FLOOR`**（weighted-coverage 下界，PA 建議 ≥0.6 majority）。
2. **`MIN_QUALIFIED_CELLS`**（絕對下界，PA 建議 ≥ max(2, ceil(active/2))）。
3. **per-cell `n_trades` 下界**（PA 建議 30 對齊 `min_oos_n`；QC 判是否上調至 runtime 60）。
4. **`SOAK_WALL_CLOCK_MS`**（PA 建議 21d 鏡像 canary Stage3）/ **`STABLE_SINCE_CHANGE_MS`**（72h）/ **`MIN_ATTRIBUTABLE_FILLS`**（30）—— QC 確認對 strategist-param soak 是否沿用 canary 值或調整。
5. **v1 direction ALLOWLIST 最終名單**（§2.4.F，PA 初擬 PROVISIONAL，QC 釘死）。
6. **是否啟用 attribution_chain_ok additional gate**（若 [55] healthcheck 對該策略不可查則整條移除，避免假 Pending 卡死）。

**QC 不需釘的（已由既有機制決定，criteria 直接 reuse，不重新推導）**：OOS 顯著性 bar（PSR/DSR/oos_n/Bonferroni — `edge_estimate_validation.py` 已釘）；live cost wall 算式與滑點參數（`cost_gate_live_with_slippage` + `risk_config_live.toml` 已釘）；LIVE drawdown envelope（`risk_config_live.toml` 12/7 SSOT 已釘）。

---

### §2.5 reverse-promote（demote）EXACT — net-new（must-fix「REVERSE-PROMOTE EXACTNESS」）

**問題根因（親 grep 鐵證）**：`merge_strategy_params_json`(strategy_params.rs:17-42) 是 deep MERGE（`current_map.insert(k,v)`）——**只覆寫/新增 key，永不刪 key**。若一次 promote ADD 了新 key（如某策略加了一個 demo-only 調出來的參數），naive「重放促升前 snapshot」demote **不會移除該新增 key**（snapshot 沒那 key，merge 不刪）→ demote 不精確。

**EXACT demote 設計**：
1. **promote 時捕捉「完整 pre-promotion live param set」**：§2.2 順序步驟 ⑥ — 在 IPC promote 寫入**之前**，先 IPC `get_strategy_params{engine:live, strategy_name}`（唯讀，無 token）取 **live 當前完整 param set**（`handle_get_strategy_params` 回完整 typed serialization，§2.0 已證）。把此完整 set 連同 promote 後的 set 一起存進 `learning.strategist_promotions`（`pre_promotion_params_json` 完整欄 + `promoted_params_json` 完整欄）。
2. **demote = 用完整 pre-promotion set 做 EXACT 還原**，**不靠 merge 語意**：
   - **裁決 A（首選，零 Rust 改動）**：demote 送 **完整 key union** 給 `update_strategy_params{engine:live}`。具體：demote payload = `pre_promotion_params_json`（完整 set）；因 demote 前的 live set = promote 後的 set（其 key 是 pre-set ∪ promote-added-keys），把 **pre-set 的所有 key 都送**會覆寫回原值，但 **promote 新增、而 pre-set 沒有的 key 不會被刪**（merge 不刪）→ **裁決 A 對「promote 只改值不加 key」精確，對「promote 加了 pre-set 沒有的 key」仍不精確。**
   - **裁決 B（EXACT，必選）**：demote payload = **pre-set ∪「promote 相對 pre-set 新增的 key 各自設回其 typed default / 或顯式 null-clear」**。但 typed param struct **無「刪 key」語意**（`update_params_json` 是 typed struct deserialize，未提供的 key 保留 struct 既有值）→ **真 EXACT 還原唯一可靠路徑 = 送回 pre-promotion 的完整 typed param set，且依賴「typed struct 全欄序列化」特性**：因 `get_strategy_params` 回的是**完整 typed 序列化（所有欄位都在）**，pre-promotion snapshot 本身就是 full set；把它整份送回，`merge` 後 typed `update_params_json` 重新 deserialize 整個 struct → **promote 期間任何「typed 欄位的值變動」都被還原**。**唯一仍不還原的 = promote 透過 IPC 加進去、但不在 typed struct schema 內的「額外 JSON key」**——而 `handle_update_strategy_params` 走 `strategy.update_params_json(&merged_json)`（**typed deserialize**），**typed deserialize 會丟棄非 schema key**（serde 預設 ignore unknown 或 deny；E1 必驗該 struct 是否 `#[serde(deny_unknown_fields)]`）。
   - **★ E1 必驗的決定性事實（U2）**：`update_params_json` 的 typed struct 是否 `deny_unknown_fields`？若**是**→ promote 根本無法加入 schema 外的 key（merge 後 deserialize 會報錯），則「promote 加新 key」場景不存在，**裁決 A 即已 EXACT**（所有可促升的 key 都是 typed schema 內欄位，全在完整 snapshot）。若**否（ignore unknown）**→ 非 schema key 可被 merge 進 JSON 但 deserialize 時被忽略，**不影響 live 策略行為**（策略只讀 typed struct），demote 還原 typed set 即還原行為，殘留的 inert JSON key 無害（但 audit 上 `get_strategy_params` 回的是 typed 序列化，不含 inert key，故無殘留）。**兩種情況下，「送回 pre-promotion 的完整 get_strategy_params 序列化」都達成行為級 EXACT 還原。** E1 grep 確認 struct serde 屬性，在報告釘死哪種情況，并加對應 acceptance test。
3. **version / precondition guard（must-fix「refusing demote if live params changed since the snapshot」）**：demote 前再 IPC `get_strategy_params{engine:live}` 取**當前** live set，與 `learning.strategist_promotions.promoted_params_json`（促升當下寫入 live 的 set）比對：
   - 相等 → live 自促升後未被改 → demote 安全，放行。
   - 不等 → live 在促升後被其他路徑改過（另一次 promote / operator 手改 / scheduler）→ **409 `live_changed_since_promotion`**，拒絕 demote（避免盲目覆寫掉中間的合法改動）。operator 須先查清再決定。
   - **比對用 canonical 比較**（鏡像 Phase-0 `canonical_json`/`canonicalize` byte-equal 邏輯，避免 key 序/float 格式假性不等）。E1 復用既有 canonicalizer。
4. **demote route**：新 `POST /api/v1/strategist/demote`（同 `strategist_promote_router`，同 5-gate + flag + token mint，target=live）。body = `{strategy, symbol, promotion_id}`（指向要回滾的 `strategist_promotions` row）。**demote 也是 operator-confirmed（confirm=true）+ 5-gate + criteria gate 豁免**（demote 是安全方向，root #5/#6——回滾到已知 live-safe 的 pre-promotion 狀態永遠允許，不需 criteria）。demote 成功寫 `strategist_promotions` 一條 `action='demote'` row（指回原 `promotion_id`）。
5. **acceptance test（must-fix「add-key-then-demote」）**：E2/E4 必跑「promote 改值 → demote → live set byte-equal 還原 pre-promotion set」+ 「(若 deny_unknown_fields=false) promote 試圖加 schema 外 key → 行為不變 → demote 還原」+ 「demote 遇 live 被中途改 → 409 拒」。

---

### §2.5.1 post-promotion realized-vs-expected auto-demote trigger（DESIGN-ONLY，標 **Phase 2.1，NOT v1**）

> **★ QC follow-up #8（design 但 defer）。** 唯一能防「促升前不可觀測的分布漂移」（pre-promotion demo edge 真實，但 live 上線後 regime/microstructure 變化使實際 edge 蒸發）的真正防線 = **促升後在 live 上量測 realized edge，若顯著低於 demo-claimed edge 則自動 demote**。但此 trigger **只在「有東西被促升」之後才有意義**——而 §2.9 誠實標已證：0 validated cell → Phase 2 v1 上線不會促升任何東西。**故設計但延後**：在第一個真促升發生（= 真有 validated edge）之前，auto-demote trigger 無對象可監控，建它是 premature。

**設計（Phase 2.1 build）**：
- **trigger**：對每個 active 的 `strategist_promotions`（`action='promote'` 且尚未被 demote）row，在促升後的監控窗（如 7-14d，QC 釘）內，量測該 `(strategy, active-symbol)` 的 **live realized edge**（同 `edge_estimates` producer 對 live engine_mode 算的 runtime `shrunk_bps`，或 `trading.fills WHERE engine_mode='live'` 該策略的 realized round-trip edge，beta-neutral 去 down-beta）。
- **auto-demote 條件**：`live_realized_edge < REALIZED_DEMOTE_RATIO × demo_claimed_edge`（QC 建議 `REALIZED_DEMOTE_RATIO ≈ 0.3`——live 實現 edge 跌破 demo 宣稱 edge 的 ~30% 即視為分布漂移/促升失效）→ **自動觸發 §2.5 的 demote machinery**（回滾到 pre-promotion live set，EXACT）。auto-demote 同樣寫 `strategist_promotions` 一條 `action='demote'` + `reason='auto_demote_realized_edge_decay'` row。
- **wire 點**：復用 §2.5 已建的 demote 路徑（同 5-gate + token + 同步 audit）。trigger 可掛 out-of-band scheduler（鏡像既有 5-min loop）或 canary comparator 類週期 job。**auto-demote 是「learning 自動收縮 live」= root #5/#6 允許的安全方向**（與「learning 自動 promote/擴張 live」相反，後者 P7 禁止）——故 auto-demote 可自動觸發，promote 永遠 operator-confirmed。
- **defer 理由（明確）**：(1) 無促升對象前無監控目標；(2) live realized edge 量測需促升後累積足夠 live fills（本身需時）；(3) v1 先把「安全促升 + 安全手動 demote」機器建穩，auto-demote 是其上的自動化層，依賴 v1 的 demote machinery 已驗證可靠。**Phase 2.1 在第一個真促升發生後啟動建設。**
- **副作用 / 風險**：auto-demote 必有 hysteresis / min-fills 防抖（live fills 不足時不觸發，避免低樣本噪音誤 demote）；REALIZED_DEMOTE_RATIO 與監控窗由 QC quant-justify。

---

### §2.6 audit fail-closed + `learning.strategist_promotions` 表（must-fix「AUDIT FAIL-CLOSED FOR LIVE」）

**現狀缺口**：既有 `_record_promote_audit`(:364-445) 是 **fire-and-forget change_audit_log**（try/except 吞錯，:444「audit must never break the request」）。**Phase 2 的 live promote/demote 必須改成「commit gate 在 audit row 寫成功」**——live param 改動 + 無耐久 audit row = P8 違反（root #8；`audit_events` 歷史為空，QA 必實證 row 真落）。

**設計**：
- **新表 `learning.strategist_promotions`**（V### 見 §2.7）。schema（鏡像 `strategist_applied_params` V019 + 加促升專屬欄）：
  - `id BIGSERIAL PK`
  - `action TEXT NOT NULL`（`'promote'` / `'demote'`）
  - `strategy_name TEXT NOT NULL`
  - `symbol TEXT`（audit scope hint，不參與語意，鏡像既有 route 的 symbol-as-hint 設計）
  - `source_engine TEXT NOT NULL`（promote 來源，'demo'/'paper'）
  - `target_engine TEXT NOT NULL DEFAULT 'live'`
  - `pre_promotion_params_json JSONB NOT NULL`（**完整** live set，促升前 / demote 還原目標）
  - `promoted_params_json JSONB NOT NULL`（**完整** 促升後寫入 live 的 set；demote 的 precondition 比對基準）
  - `criteria_verdict TEXT NOT NULL`（`Eligible`/`Pending:reason`/`Reject:reason`/`demote_exempt`）
  - `criteria_input_json JSONB`（promote 當下的 EDGE-ANCHORED metric 快照，root #8 可重建：per active-symbol cell 的 `{symbol, validation_passed, validation_reason, from_runtime_field, shrunk_bps, win_rate, n_trades, cleared_live_cost_wall}` 陣列 + `weighted_coverage` + `qualified_count` + `demo_soak_wall_clock_ms` + `ms_since_last_param_change` + `attributable_demo_fills` + `demo_boundary_violation_count`（以 LIVE envelope 量測）+ `attribution_chain_ok_ratio` + `tuned_param_names` + `live_cost_model{fee_bps_round_trip, safety_multiplier, win_rate_floor}`。**完整保留促升當下的 edge 證據，供事後 QC 重審「這次促升的量化依據」**。）
  - `actor_id TEXT NOT NULL`
  - `gate_passed BOOLEAN NOT NULL`（5-gate 結果）
  - `applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()` + `applied_at_ms BIGINT NOT NULL`
  - `reverts_promotion_id BIGINT`（demote 指回被回滾的 promote row id；FK-soft）
  - `reason TEXT`
  - index：`(strategy_name, target_engine, applied_at_ms DESC)`、`(action, applied_at_ms DESC)`
- **fail-closed 寫入時序（live promote 成功路徑）**：IPC `update_strategy_params{engine:live}` 回 OK 後，**同步**（非 fire-and-forget）`INSERT INTO learning.strategist_promotions(...)` with `action='promote'`。**INSERT 失敗 → route 回 500 `audit_write_failed` + 結構化告警**（live 已改但 audit 沒落 = 必須 loud；operator 須立即知曉並考慮 demote）。**裁決：audit 寫在 IPC 成功之後**（不能在之前，否則 IPC 失敗會留假 audit row）；**這意味著「IPC 成功 + audit 失敗」是一個真實窗口**——此窗口的處置 = route 回 500 + 告警 + log 完整 params（讓 operator 能手動重建 audit / 決定 demote）。**不可吞錯靜默成功。**
  - **與既有 change_audit_log 的關係**：保留既有 `_record_promote_audit`（change_audit_log，給 governance hub 統一審計流）為**補充**，但 **`learning.strategist_promotions` 的同步 INSERT 才是 commit gate 的權威耐久 row**。两者不互斥（change_audit_log fail 仍 fire-and-forget warn；strategist_promotions fail = hard 500）。
- **denied 路徑**（criteria reject / 5-gate fail / flag-off）：寫 `strategist_promotions` 一條 `gate_passed=false` + `criteria_verdict=<reason>` row（fail-soft 此處可接受 best-effort，因無 live 改動；但 PA 偏好同樣同步寫以保 audit 完整 — E1 裁量，QA 驗 denied row 是否落）。
- **QA 實證（MANDATORY）**：Linux PG 真連線，跑 promote-success / criteria-reject / 5-gate-fail / demote / demote-precondition-fail 五場景，**親查 `learning.strategist_promotions` 真有對應 row**（`audit_events`/`engine_events` 歷史稀疏甚至為空，P8 風險，不可只信 code path）。

---

### §2.7 migration `learning.strategist_promotions`（V###，build 時釘）

- **next-free V### = build 時親查，勿信本 doc。** 親 grep `sql/migrations/` 當前最高 = **V143**（`V143__l1_book_event_recorder.sql`），但 **V140 缺號、V143 file 可能尚未 apply 至 prod**（PA memory 06-16 條：prod `_sqlx_migrations` max 曾為 139）。**E1 必 `ssh trade-core` 查 prod `_sqlx_migrations` 實際最高 ordinal**，取**檔案鏈最高 + 1**（避免撞並行 session 的號）。**建議 V144**，但以 build 時 grep + prod 查為準（migration 號是 git 看不見的全局命名空間 — PA memory 鐵則）。
- **Guard A**：`CREATE SCHEMA IF NOT EXISTS learning;` + `CREATE TABLE IF NOT EXISTS learning.strategist_promotions (...)`（schema 已由 V019 建，重複 IF NOT EXISTS 安全）。index 用 `CREATE INDEX IF NOT EXISTS`。
- **idempotent double-apply**：Linux PG 連跑兩次 migration，第二次必 no-op 無錯（CLAUDE Data §）。
- **Linux PG empirical dry-run（MANDATORY）**：`ssh trade-core` 連 `trading_admin@127.0.0.1/trading_ai`（via ~/.pgpass），scratch DB 跑 migration → 驗表/欄/index/型別 → double-apply → 驗 `_sqlx_migrations` row。**不手 psql 打 prod**（避 checksum 漂移；prod apply 走 sqlx auto-migrate at engine boot 或 operator-gated migrate 命令）。
- **非 hypertable**（促升是稀疏事件，非時序高頻；無 compress/retention，永久保留 audit lineage — root #8）。

---

### §2.8 副作用清單

1. **`strategist_promote_routes.py` 行為改變**：flag-OFF 時 live promote 從「5-gate 過即可」變「409 promotion_disabled」。**現無 caller 在 prod 自動呼 live promote**（operator GUI 手動），故 default-OFF 不破任何自動流程。GUI promote 按鈕在 flag-OFF 下會收 409 — **GUI 需顯示 promotion_disabled 提示**（E1 加，或 GUI 既有錯誤處理 surface）。
2. **新唯讀 IPC `evaluate_promotion_criteria`（首選 Rust 路徑）**：加進 dispatch match arm。**不在 `LIVE_WRITE_METHODS`**（唯讀，token 豁免）。handler 自查 `Arc<RwLock<EdgeEstimates>>`（**只 read lock**，不寫）+ 讀 `risk_config_live.toml` slippage 參數（只讀）+ 跑 `promotion_criteria.rs` 純函數。E2 驗它確唯讀（不改任何 ConfigStore / 不改 EdgeEstimates / 不送 cmd）。**注意 async/sync 邊界**：edge snapshot 取 read lock 是同步快操作（非阻塞 await），handler 內不引入 await-on-lock。
3. **`promote_params_to_live()` stub 仍 0 自動 caller**：E2 grep 證 P7（learning 不自動改寫 live）不破。
4. **change_audit_log 不變**（既有 fire-and-forget 保留為補充）。
5. **無 RiskConfig 觸碰**：全程只 `update_strategy_params`（strategy param sink），永不 `patch_risk_config`/`update_risk_config`。E2/CC 驗。
6. **mock 脆弱點**：`_verify_live_gate` / `all_five_live_gates_ok` 在大量測試被 mock；criteria gate + demote 新測試不可 mock 掉 5-gate（否則 live 授權繞過誤過）。E2 驗測試真跑 gate。

---

### §2.9 降級 / rollback 路徑

- **flag default-OFF** = Phase 2 完全 inert，live promote 不可達（bit-identical 除 409 拒絕碼）。緊急關閉 = unset flag。
- **demote（§2.5）= 業務級 rollback**：任何促升後可一鍵回滾到 pre-promotion live 完整 set（EXACT）。**Phase 2.1 的 auto-demote trigger（§2.5.1，DEFER）** 將在此 demote machinery 上加自動收縮層（live realized edge < 0.3× demo-claimed → 自動回滾），防促升後分布漂移——但 defer 到第一個真促升發生後。
- **Phase-0 secret 撤除 = 終極 kill-switch**：撤 `OPENCLAW_LIVE_PATCH_SECRET` → 所有 live-write（含 promote/demote IPC）token 驗證必失敗 → fail-closed 拒（既有 Phase-0 機制）。
- **migration 純 additive**（新表，無改既有表）→ git revert 安全；表留存無害（無 writer 時就是空表）。
- **★ 誠實標（核心，flag-ON 絕不可誤讀為「促升啟動」）**：今天 live `edge_estimates` = **129 cells / 0 validated**。EDGE-ANCHORED criteria gate（§2.4）的 binding gate = 「該策略 active symbol 的 edge cell 須 `validation_passed && validation_reason=="passed" && fresh && from_runtime_field && shrunk_bps>0 && n_trades>=30 && 清 live cost wall`，且 weighted-coverage ≥ floor」。**0 validated cell → 任何策略的 `weighted_coverage == 0` → criteria gate 對所有促升一律回 `Pending("edge_coverage_below_floor")`（或 `Reject`）**。即 **Phase 2 上線當天，正確 criteria gate REJECTS/PENDS 所有促升 —— 這是 DESIRED 行為**：機器安全就緒，但在「真正 OOS-validated、清 live 成本牆的正 edge」出現之前**不促升任何東西**。Phase 2 是「為將來有 validated edge 時準備好的安全機器」，**flag-ON ≠ 促升 active**。任何把 flag-ON 讀成「現在開始促升」的理解都是錯的——edge coverage 是 binding gate，沒有 validated edge 就沒有 Eligible。

---

### §2.10 E1 派發計劃（最大並行）

- **E1-A（Rust，EDGE-ANCHORED criteria gate）**：新 `strategist_scheduler/promotion_criteria.rs`（`PromotionCriteriaInput` + `ActiveCellEdge` struct + `PromotionVerdict` enum + 純函數 `evaluate_promotion_criteria`，10-step fail-closed 判定 §2.4.E；per-cell 8 條 + weighted coverage §2.4.B；v1 direction allowlist const §2.4.F）；mod.rs 加 `mod`。新唯讀 IPC `evaluate_promotion_criteria`（dispatch.rs 加唯讀 arm + handler wrapper，**不入 LIVE_WRITE_METHODS**）——**首選實作**：handler 內 engine 自查 `Arc<RwLock<EdgeEstimates>>` 的 live snapshot + 解析該策略 active-symbol（`strategy_params_live.toml allowed_symbols` ∩ `scanner_config.toml pinned_symbols`）+ reuse `risk_config_live.toml` slippage 參數算 live cost wall（鏡像 `cost_gate_live_with_slippage` 算式）+ 跑判定，回 verdict（route 只傳 strategy + soak/fills/boundary metric + tuned_param_names，§2.4.G）。**REUSE 既有：`edge_estimate_validation` 的 `validation_passed`/`validation_reason` 語意（不重算 PSR/DSR）、`cost_gate_live_with_slippage` 的 cost wall 算式（不另造成本模型）、`risk_config_live.toml` SSOT（drawdown 12/7 §2.4.D、slippage 參數）。** **不重驗 U2（U2 屬 §2.5 demote，E1-A 不碰）。**
- **E1-B（SQL，migration）**：`V###__strategist_promotions.sql`（§2.7，build 時 ssh 查號）+ Linux PG double-apply dry-run。`criteria_input_json` 欄須容納 §2.6 的 edge-anchored 快照（JSONB 已足）。**先定表名/欄/PK/index**，E1-C 跟。
- **E1-C（Python，route enhancement，依賴 E1-A IPC 簽名 + E1-B 表 schema）**：`strategist_promote_routes.py` 加 flag gate（§2.1）+ criteria metric query（soak wall-clock / since-change / attributable demo fills / demo boundary-vs-LIVE-envelope，§2.4.C/D，與 `_fetch_latest_applied_row` 同 DB lane）+ active-symbol 解析傳入（或由 engine 自解，§2.4.G 首選）+ criteria 唯讀 IPC call（§2.4.G）+ tuned_param_names diff（§2.4.F）+ pre-promotion snapshot 捕捉（§2.5 步驟 1）+ 同步 fail-closed `strategist_promotions` INSERT（含 edge-anchored `criteria_input_json`，§2.6）；新 `POST /demote` route（§2.5 步驟 4，precondition guard 步驟 3）。
- **阻塞關係**：E1-A∥E1-B 可並行；E1-C 依賴二者的契約（IPC verdict 形狀 + 表 schema）——E1-A/B 先交契約 stub，E1-C 跟。**單 E1 串行亦可**（工作量中等，route 已大半存在；edge-anchored 判定的複雜度集中在 E1-A 的 active-symbol 解析 + per-cell coverage）。

---

### §2.11 E2 重點審查 4 點

1. **無自動觸發 + P7 不破**：grep 證 `promote_params_to_live` stub 0 自動 caller；promote/demote 唯一觸發 = operator-confirmed route（confirm=true）；criteria IPC 唯讀不改 state（不送 cmd / 不改 ConfigStore / 不改 EdgeEstimates）。
2. **★ EDGE-ANCHORED criteria 不可被繞 + 不靠 demo PnL（QC 重寫核心）**：(a) criteria 的 binding gate 是 live `edge_estimates` 的 `validation_passed && validation_reason=="passed"` 鏈，**不讀** demo realized PnL 當促升證據（驗 `PromotionCriteriaInput` 無 `realized_pnl` 欄、判定無 PnL 分支 — down-beta 假陽性源頭已移除）；(b) criteria gate **結構上不讀 `explore_eligible`/`explore_remaining`**（explore-grace-only cell 無法冒充 live-qualified — 鏡像 live cost_gate 的 demo↔live 隔離守門點）；(c) drawdown bound 用 **LIVE** `risk_config_live.toml`（12/7）非 demo envelope（25/15）；(d) per-cell 須清 **live cost wall**（reuse `cost_gate_live_with_slippage` 算式，非僅 shrunk_bps>0）；(e) coverage 是 **weighted/majority**（單 cell cherry-pick 無法過 25-sym 策略）；(f) v1 direction allowlist 生效（denylist param → Reject）。
3. **reverse-promote EXACT**：依 U2 裁決（§2.5），acceptance test 證「promote→demote→live set byte-equal 還原 pre-promotion」+「live 中途被改→demote 409」+ canonical 比對正確（不假性不等）。
4. **audit fail-closed 真生效**：live promote IPC 成功後 `strategist_promotions` INSERT 失敗 → route 真回 500（非吞錯）；`criteria_input_json` 完整保留 edge-anchored 證據（per-cell + coverage）；5-gate/criteria/token 三閘任一失敗 → 0 live 改 + 不靜默；E4 Linux PG 親查 row 真落（P8）。

> **★ E2 GREP 要求（criteria 繞過防線 — 不可省）**：E2 必 grep 證 **無第二個 `update_strategy_params{engine:live}` caller 繞過 criteria gate**。具體：(1) grep 全 repo `call_params_with_token("update_strategy_params"` + `update_strategy_params` IPC method 的所有 Python caller，證**唯一**達 live 的路徑是 `strategist_promote_routes.py` 的 confirm=true live 分支（已過 §2.2 順序的 criteria gate ④）；(2) grep Rust 端 `UpdateStrategyParams` / `promote_cmd_snapshot` / `promote_params_to_live` 的 caller，證 stub 仍 0 自動 caller、in-process Rust→Live channel（繞 chokepoint+criteria）無任何 production 觸發；(3) `strategy_write_routes.py:74` 認 promote router 為唯一合法 live-promote lane 仍成立。**任一旁路 caller = criteria gate 可被繞 = BLOCKER。**

### §2.12 Role chain（修正 — EDGE-ANCHORED criteria 重寫後）
`PA(本設計，§2.4 已採 QC NEEDS_CHANGES 的 edge-anchored 重寫) → QC(ratify edge-anchored criteria 設計 + 釘死 §2.4「待 QC 釘死」6 項：COVERAGE_FLOOR / MIN_QUALIFIED_CELLS / per-cell n_trades 下界 / soak·since-change·fills 值 / v1 direction allowlist 最終名單 / attribution_chain_ok 是否啟用，MANDATORY) → E1-A/B/C → E2(對抗：無自動觸發 + EDGE-ANCHORED 不可繞·不靠 demo PnL·拒 explore-grace·LIVE drawdown·清 live cost wall·weighted coverage·direction allowlist + reverse 精確 + audit fail-closed + 無 RiskConfig 觸碰 + 無第二 live caller 繞過 grep) → E3(live route auth：_verify_live_gate require_authz=True，token mint 時序，demote 同 5-gate) → E4(Linux 真 Live engine bound：criteria reject/pending 在 0-validated-cell 真回 Pending（誠實標）、promote+demote 往返 byte-equal、precondition-fail 409、strategist_promotions row 親查 edge-anchored criteria_input_json 真落、double-apply) → CC(P4/P5/P7/#8 audit + Alpha Evidence Governance：promotion 證據 math-primary·demo-only lane·bull-only=regime-bet 非 proof) → PM`

---

## PHASE 3 — RiskConfig agent 調參 — BUILD-READY（2026-06-17 PA in-place rewrite）
**目標**：agent 調 **非 survival** RiskConfig 旋鈕，demo 自主 + live **僅**經 Phase-2 人工促升閘。survival floors 永遠 operator-only。需 Phase 0 完成（live 半另需 Phase 2）。

> **★★★ v1 誠實邊界（先講結論，全節據此設計）**：親 grep 證 `DynamicStop`/`RegimeMultipliers` 等候選 allowlist 欄位**在 struct 中沒有任何 operator-set band 欄**（`DynamicStop::validate` risk_config_advanced.rs:165-178 只查 `base_ratio>0 / cap_ratio>0 / base<=cap / atr_*>0`；`RegimeMultipliers::validate` risk_config.rs:1263-1276 只查 `stop/tp/time > 0`）。**沒有 band = clamp-cannot-widen 對它們是空操作（VACUOUS）**。因此 v1 的**硬規則 U5**（見下）把所有「無 operator band」的欄位**留在 denylist**。淨效果：**v1 很可能以 allowlist 實質為空出貨 → flag-ON 也 tune NOTHING**。這是**正確的 inert 行為**（與 Phase 1/2「機器先就位、edge 證據/band 未備齊就持續 fail-closed」一致），不是缺陷。agent 真正能動任何 RiskConfig 旋鈕的**啟動路徑 = operator+QC 先加 band 欄（band 欄自身 denylist）+ 填值**（§3.5）。

### §3.0 in-process 寫入面 + demo-only-Arc 結構閘（must-fix「IN-PROCESS SELF-GATE」/ E3 MED-2）
- **新 `RiskConfigDirectiveSink`（DirectiveApplier 的平行 sink，不是 PipelineCommandSink 的第 N 個方法）**。**不**擴 `StrategyIpcSink` trait（strategy_ipc_impl.rs:11-24，ARCH-RC1 契約禁碰 RiskConfig — 保此不變量）。新 sink 是獨立 struct，持有 `Arc<ConfigStore<RiskConfig>>` 並經 `ConfigStore::apply_patch(PatchSource::Agent, …)`（store.rs:155）**in-process 直寫**，**永不**走 Python operator route（`POST /config/global` 等），故 agent 路徑的 denylist/clamp 永遠在 Rust 內、不可繞。
- **★ 命門：此 in-process 寫入不經過 IPC `dispatch_request` chokepoint（dispatch.rs:127 前）→ 結構上拿不到 Phase-0 `live_authz_token` 強制**。因此 sink 自身必須結構性保證「live 寫只在 promotion-state 在 frame 內時可達」。設計用**型別/所有權閘**（非 runtime 字串判斷）：
  - **demo sink = `RiskConfigDirectiveSink::demo(Arc::clone(&risk_stores.demo))`**：建構時**只**接 `risk_stores.demo` 的 Arc，**結構上不持有 `risk_stores.live` 的 Arc**。鏡像兩個已部署的 in-process daemon 先例：`EngineCommandSink::demo(...)`（tasks.rs:286，Teacher 既有 sink）+ `spawn_cost_edge_advisor_if_enabled` 取 `Arc::clone(&risk_stores.demo)`（cost_edge_advisor_boot.rs:167，RFC §8 cross-env 獨立）。**禁用 `PerEngineRiskStores::select(engine_str)`**（engine_routing.rs:93 unknown→paper fail-safe，會用 runtime 字串把 live Arc 取出 = 破壞結構閘）。demo sink 連 live Arc 的 handle 都沒有 → 無論 directive 怎麼寫都**不可能** mutate live ConfigStore（E3 編譯期可證：demo sink struct 欄位型別不含 live store）。
  - **live 寫 = 不存在獨立的「live RiskConfigDirectiveSink」**。agent 對 RiskConfig 的 live 變更**唯一路徑 = Phase-2 promotion**：把 demo 上已驗證的 RiskConfig 子集，經 §2 既有 `strategist_promote_routes` 同級機制（operator confirm + `all_five_live_gates_ok` + Phase-0 token + 同步 fail-closed audit）促升。**裁決：Phase 3 不新增任何把 RiskConfig 寫 live 的 in-process Rust 路徑**；live RiskConfig 的促升走 Python route → IPC `patch_risk_config{engine:live}`（已過 dispatch chokepoint + Phase-0 token，handlers_config.rs）。這與 Phase 2 「不接 `promote_params_to_live()` in-process stub、沿用過 chokepoint 的 route」裁決同構。**RiskConfig 促升的 criteria 模塊 reuse Phase 2 的 `promotion_criteria.rs`**（§2.4 edge-anchored，spec :610 已預留 headroom）。

### §3.1 完整 survival DENYLIST（按 REAL RiskConfig dotted-path 欄名重寫；must-fix「SURVIVAL FLOOR INVARIANT」/ CC）
> **★ 為何不可複用既有 `P0_P1_DENYLIST_FIELDS`**：那組（applier.rs:200-218）是 strategy-param 命名空間的舊名（`max_leverage` / `max_position_size_usd` / `hard_stop_pct` / `daily_loss_pct` / `max_drawdown_pct` …），**與 RiskConfig 真實葉名不同**（RiskConfig 是 `limits.leverage_max` / `limits.position_size_max_pct` / `limits.daily_loss_max_pct` / `limits.session_drawdown_max_pct`）。若直接套用，denylist **永遠 match 不到任何 RiskConfig patch key = 靜默全放行**。Phase 3 必須用下方按 risk_config.rs / risk_config_advanced.rs 親 grep 出的**真 dotted-path**重新 author 一份 `RISKCONFIG_SURVIVAL_DENYLIST`。既有 `P0_P1_DENYLIST_FIELDS` 為 strategy-param sink 保留不動（仍對 AdjustParam 有效）。

**RISKCONFIG_SURVIVAL_DENYLIST（dotted-path，全部 operator-only forever；agent 觸碰=硬 veto）**：

- **絕對 SL/TP 上限 + 倉位/曝險上限（GlobalLimits，risk_config.rs:365-498）**：
  `limits.stop_loss_max_pct`、`limits.take_profit_max_pct`、`limits.take_profit_enforced`、`limits.position_size_max_pct`、`limits.total_exposure_max_pct`、`limits.correlated_exposure_max_pct`、`limits.leverage_max`、`limits.session_drawdown_max_pct`、`limits.daily_loss_max_pct`、`limits.consec_loss_cooldown_count`、`limits.consec_loss_cooldown_min`、`limits.open_positions_max`、`limits.min_order_notional_usdt`、`limits.max_order_notional_usdt`、`limits.min_balance_usdt`、`limits.global_notional_cap_usdt`、`limits.per_trade_risk_pct`、`limits.margin_mode`、`limits.position_mode`、`limits.allowed_categories`。
- **halt TTL（生存恢復語意，risk_config.rs:484/496）**：`limits.daily_loss_halt_ttl_ms`、`limits.drawdown_halt_ttl_ms`（後者 validate 強制=0；任何 agent 改都違 root#5/#6）。
- **guardian 修正 caps（risk_config.rs:427-430）**：`limits.guardian_modification_size_factor`、`limits.guardian_modification_leverage_cap`。
- **fast_track dust floors（survival 平倉語意，risk_config.rs:448/468）**：`limits.ft_min_notional_ratio_of_entry`、`limits.ft_dust_qty_floor_usd`。
- **liquidation buffer（risk_config_advanced.rs:200 MarketGate）**：`market_gate.liquidation_buffer_pct`（連帶整個 `market_gate.*` 微結構 gate 不在 allowlist，default-deny 自動擋；但 liquidation_buffer 顯式列入以便 audit 可讀）。
- **整個 cascade.* struct（CascadeThresholds，risk_config.rs:1039-1070；must-fix 點名「the ENTIRE cascade.* struct」）**：`cascade.drawdown_cautious_pct`、`cascade.drawdown_reduced_pct`、`cascade.drawdown_defensive_pct`、`cascade.drawdown_circuit_pct`、`cascade.daily_loss_cautious_pct`、`cascade.daily_loss_reduced_pct`、`cascade.daily_loss_circuit_pct`、`cascade.consec_loss_cautious`、`cascade.consec_loss_reduced`、`cascade.consec_loss_circuit`、`cascade.pressure_cautious`、`cascade.pressure_reduced`、`cascade.pressure_defensive`、`cascade.pressure_circuit`、`cascade.min_hold_ms`。**E1 實作層面更穩的做法：denylist 一條 `cascade`（整個 struct 前綴）即可，遞迴 matcher 對 `cascade.` 下任何葉直接拒**（見 §3.3）。
- **cost_gate 全部 5 欄（CostGate，risk_config.rs:1283-1295；must-fix：k-up + min_confidence-down 都放寬 edge filter = survival-class）**：`cost_gate.k_base`、`cost_gate.k_medium`、`cost_gate.k_small`、`cost_gate.min_confidence`、`cost_gate.adx_trending`。**整個 `cost_gate.*` 預設 denylist**；k 上調 / min_confidence 下調 / adx_trending 下調都是「放寬 edge 過濾 = 開更多倉」，屬 survival-class。日後若要允許僅向下收緊（k 下調 / min_confidence 上調）須另一 operator 決定 + 加 band（同 §3.5），v1 不開。
- **既有 P0_P1_DENYLIST_FIELDS 的硬邊界字面 token 一併納入（防 agent 用舊名/別名注入）**：`execution_state`、`execution_authority`、`system_mode`、`live_execution_allowed`、`max_retries`（連帶 §四 三硬邊界字面）。這些雖非 RiskConfig 葉，但作為 free-text key 出現即 veto（defense-in-depth）。

### §3.2 候選 ALLOWLIST（v1 實質為空 — 每欄須有 operator band 才解禁）
> 下列是「**若**未來 operator+QC 加了 band 欄、且 QC 確認該欄由 leak-free 證據支撐」才可能進 allowlist 的候選。**v1 因無 band 欄，全部按 §3.3 U5 規則留在 default-deny（=denylist）**。列出是為了把 §3.5 啟動路徑釘清楚，不是 v1 即可調。

- `regime.{trending,volatile,ranging,squeeze,unknown}.{stop,tp,time}` 乘數（RegimeMultipliers，risk_config.rs:1182-1200）— 無 band 欄 → v1 deny。
- `dynamic_stop.{base_ratio,cap_ratio,trailing_min_rr,atr_stop_mult,atr_tp_mult}`（DynamicStop，risk_config_advanced.rs:124-135）— 無 band 欄 → v1 deny。
- `agent.{trailing_activation_pct,trailing_distance_pct,size_multiplier}`（AgentParams，risk_config.rs:782-820）— `size_multiplier` 已有結構性 clamp `[0.1,1.0]`（validate :854）算「半個 band」，但 trailing_* 只有 `>0`；**v1 仍 deny**（要 explicit `[band_min,band_max]` 才一致，避免「有些半 band 有些無」的不一致防線）。
- **注意**：`agent.stop_loss_pct`/`agent.take_profit_pct`（P2 有效止損止盈）**不入候選 allowlist** — 它們是直接 SL/TP 數值，與 survival SL/TP 上限耦合（validate cross-field :311-326），歸 survival 語意，留 deny。

### §3.3 遞迴 dotted-path matcher + allowlist-default-deny（must-fix「RECURSIVE/DOTTED-PATH」/ CC+E2）
> **★ 為何必須重寫 matcher**：既有 `find_denylisted_field`（applier.rs:551-559）**只比頂層 object key**（`for key in obj.keys()`，不遞迴）。RiskConfig patch 是**巢狀** `{"limits":{"leverage_max":50}}` → 頂層 key 只有 `"limits"`，舊 matcher 看不到 `leverage_max` → **整條 survival 邊界被繞過**。

- **新 `riskconfig_patch_leaves(patch: &serde_json::Value) -> Vec<String>`（純函數，sibling）**：遞迴走整個 patch JSON 樹，對每個**葉節點**（非 object 的 value，或 object 內的純量）產出其完整 dotted-path（如 `limits.leverage_max`、`regime.trending.stop`、`cascade.min_hold_ms`）。陣列葉用 `key[]` 或整 key 視為單葉（保守：`allowed_categories` 整體視為一葉，落 denylist）。
- **判定順序（fail-closed，default-deny）**：對每個葉 path：
  1. 若 path（或其任一前綴，如 `cascade`、`cost_gate`、`market_gate`）∈ `RISKCONFIG_SURVIVAL_DENYLIST` → **VetoedByHardBoundary**（reason 帶確切 dotted-path）。
  2. 否則若 path ∉ `RISKCONFIG_ALLOWLIST`（v1 為空集）→ **VetoedByDefaultDeny**（reason `riskconfig_field_not_allowlisted`）。
  3. 僅當 path ∈ allowlist 且 path 有對應 operator band → 進 §3.4 clamp。
- **任一葉被拒 → 整個 patch 拒（all-or-nothing，對齊 ConfigStore apply_patch 語意）**。E2 對抗測試必含：`{"limits":{"leverage_max":50}}`（nested survival）、`{"cascade":{"min_hold_ms":0}}`（nested struct-prefix）、`{"cost_gate":{"k_base":99}}`、`{"regime":{"trending":{"stop":99}}}`（v1 無 band → default-deny）、`{"unknown_top":{"x":1}}`（未知頂層 → default-deny）。
- **大小寫/別名**：保留既有 `eq_ignore_ascii_case` 比對；denylist token 全小寫存。

### §3.4 clamp-cannot-widen + LCB-UP gate（must-fix「clamp-cannot-widen」+ E2 MED-2 race；鏡像 DynamicRiskSizer）
- **band 從何讀**：sink 從**自己持有的 demo `ConfigStore<RiskConfig>` 當前快照**讀該欄的 `[band_min, band_max]`（band 欄自身在 denylist → agent 不能放寬 band → clamp 永遠對 operator 真值生效）。
- **★ 原子性（E2 MED-2：load→merge→replace 非原子，handlers_config.rs:119/144 是舊路徑的問題）**：新 sink **不**用 load-then-replace，而是**在單一 `ConfigStore::apply_patch(PatchSource::Agent, mutate, validate)` closure 內**（store.rs:155-192，write_lock 持有期間）讀 band + clamp + 寫。`apply_patch` 在 write_lock 內快照 current（store.rs:173）→ 同一 critical section 內讀 band 與寫值 = 無 band-narrow-during-agent-UP race。validate 仍跑完整 `RiskConfig::validate()`（all-or-nothing 回滾）。
- **clamp 規則**：agent 提議 `v_raw` → `v = clamp(v_raw, band_min, band_max)`。clamp 後值永遠 ⊆ operator band。
- **方向 gate（鏡像 DynamicRiskSizer DYNAMIC-RISK-SIG-1，dynamic_risk_sizer.rs:275-290 真碼，非 spec 舊引的 :42-52 config doc）**：
  - **DOWN（朝「更保守/交易更少」方向）= ungated**（survival-first，root#5/#6）。每欄須標 monotonic direction（哪邊是 tighten）——**這正是 Phase 2 §2.4 已釘的 v1 direction-bound 問題**（ParamRange 無方向語意）；RiskConfig 欄的 tighten 方向由 QC 在加 band 時一併釘（如 `atr_stop_mult` 下調=停損更近=更保守?需 QC 確認，因更近停損也可能增 whipsaw — 這正是為何 v1 不靠猜）。
  - **UP（朝「放寬/交易更多」方向）= 需 LCB 顯著性 gate**：reuse DynamicRiskSizer 的 `lcb = metric − sig_z·se; lcb >= threshold` + 樣本硬 floor `max(min_trades, sig_min_trades)` 形態。**但 metric 來源必須是 leak-free per-(strategy,symbol) edge 證據**（reuse Phase 1 `edge_estimates` cell / Phase 2 `validation_passed` 鏈），不是 RiskConfig 旋鈕自己的歷史。**v1 因無 band、無 allowlist 欄、無「哪個 edge metric 支撐哪個 risk 旋鈕」的 QC 映射 → UP gate 無對象 = 進一步坐實 v1 inert**。
- **誠實標**：clamp-cannot-widen 對「無 band」欄是 vacuous（U5），所以**安全來自 §3.3 default-deny 把無 band 欄擋在 clamp 之前**，clamp 只是「已有 band 欄解禁後」的第二層。

### §3.5 U5 硬規則 + band-field 加法設計（must-fix「U5 no-operator-band→stays-denylisted」）
- **U5 硬規則（v1 不可違反）**：**任何 allowlist 候選欄，若 RiskConfig struct 中沒有對應的 operator-defined `[band_min, band_max]` 欄，則該欄留在 denylist（default-deny），agent 不可調。**
- **啟動路徑（agent 將來能調某 risk 旋鈕的唯一方式）**：
  1. **operator + QC** 決定某欄值得交給 agent，且能指出**leak-free 證據源**（哪個 edge metric / 哪個方向是 tighten）。
  2. 在 RiskConfig struct **新增該欄的 band 子欄**（如 `dynamic_stop.atr_stop_mult_band: Option<(f64,f64)>` 或獨立 `DynamicStopBands` sub-struct）。**band 欄自身列入 `RISKCONFIG_SURVIVAL_DENYLIST`**（agent 永不能改自己的 band — 這是 clamp-cannot-widen 的根基）。band 欄 `Option`/default=None → 未設時該欄**仍 deny**（None ≠ 解禁）。
  3. operator 經正常 operator route 填 band 值（operator-only 寫，過既有 5-gate / `_require_risk_write`）。
  4. 該欄才進 `RISKCONFIG_ALLOWLIST`（編譯期常數或由「band 欄非 None」動態推導 — **裁決：動態推導**，即 allowlist 成員資格 = 「在候選集 ∧ band 欄 Some」，避免「allowlist 常數列了但 band 沒填」的不一致）。
  5. v1 ship 時所有 band 欄 None → allowlist 動態為空 → flag-ON 也 tune nothing。
- band 欄的 schema/validate（band_min < band_max、band ⊆ 該欄物理合法域、不得放寬到 survival 邊界外）由加 band 的那次 operator+QC 工作定義，**不在 Phase 3 v1 範疇**（v1 只建機器 + default-deny）。

### §3.6 治理 gate 全鏈（demo sink，flag-ON 時每個 directive 順序）
1. **flag check**：`OPENCLAW_RISKCONFIG_AGENT_TUNING_ENABLED` ≠ "1" → directive 不被 route 到此 sink（DirectiveType::AdjustRiskConfig 在 flag-OFF 時於 `apply_inner` match arm 直接回 `InvalidDirective{disabled}`，不靜默吞）。
2. **§3.3 遞迴 matcher**：任一葉 ∈ denylist → VetoedByHardBoundary；任一葉 ∉ allowlist → VetoedByDefaultDeny。（v1：所有 RiskConfig 葉都會在此被擋。）
3. **GovernanceCore veto**（reuse `GovernanceCheck::session_halted()` applier.rs:141）：session halted / daily-loss / drawdown 觸發 → 拒（stress 時擋全 agent 調參）。
4. **§3.4 clamp + 方向 gate**（僅 allowlist 欄到此）：clamp 到 band；UP 需 LCB；在 `apply_patch` closure 內原子寫。
5. **audit（§3.7）**：每個 outcome（Applied / VetoedByHardBoundary / VetoedByDefaultDeny / VetoedByGovernance / IpcError-equiv / Clamped）→ `learning.directive_executions` row（reuse 既有表，**無新 migration**；source=agent）。reuse `super::writer::record_execution`（applier.rs:276）；audit 失敗不吞 outcome（既有語意），但 Phase 3 **QA 必實證 5 類 outcome 都落 row**（audit_events 歷史稀疏，P8 風險）。

### §3.7 audit（reuse learning.directive_executions，無新 migration）
- 每次 auto-tune（含被拒）→ row：`directive_id / directive_type=adjust_risk_config / scope(欄 dotted-path 或 "riskconfig") / params(原始 patch) / outcome / clamped_from→clamped_to(若 clamp) / band_used / source=agent`。
- 新 IPC 觀測 `get_risk_directive_metrics`（per-field apply/reject/clamp count + last value + last reject reason），GUI Risk tab surface（node --check 前置）。
- v1 預期 row 形態：清一色 `VetoedByDefaultDeny`（因 allowlist 空）→ **這正是「機器活著、安全 inert」的可觀測證據**。

### §3.8 flag / singleton / migration / 降級
- flag `OPENCLAW_RISKCONFIG_AGENT_TUNING_ENABLED` **default-OFF（master）**。flag-OFF = sink 不被 route（bit-identical：DirectiveType::AdjustRiskConfig 不存在於現行 directive 流，flag-OFF 下新 arm 立即回 disabled）。
- singleton：`RiskConfigDirectiveSink`（demo Arc holder）須登記 CLAUDE §九 singleton 表（merge 前）。
- migration：**無**（reuse learning.directive_executions）。
- **降級 / rollback**：(a) flag-OFF = 凍結整個 Phase 3，sink no-op；(b) demo sink 結構上不持 live Arc = live RiskConfig 永遠不被此路徑碰（編譯期不變量，非 runtime 開關）；(c) GovernanceCore session-halt / daily-loss / drawdown veto = stress 時擋全 agent 調參；(d) v1 allowlist 空 = 即使誤開 flag 也 tune nothing；(e) live RiskConfig 促升唯一觸發 = operator Phase-2 confirm（撤 `OPENCLAW_LIVE_PATCH_SECRET` → 全 live patch fail-closed）。

### §3.9 E1 派發計劃（檔案邊界 + 並行度）
- **E1-RUST-A（denylist + 遞迴 matcher，純函數，無 IO，可先行）**：新 sibling `applier_riskconfig.rs`（applier.rs 已 1072 行 >800，§九；新 DirectiveType+sink 加上去恐近 2000 cap → 拆 sibling，LOW 注意項已記）。含 `RISKCONFIG_SURVIVAL_DENYLIST` 常數（§3.1 真 dotted-path）+ `riskconfig_patch_leaves` 遞迴 + 判定函數 + 全 §3.3 對抗單測。
- **E1-RUST-B（DirectiveType + sink + clamp + wiring）**：parser.rs 加 `DirectiveType::AdjustRiskConfig`（enum + snake_case + ALLOWED_FIELDS 不變，params 仍 free-form）；apply_inner match arm（applier.rs:291）加 `apply_adjust_risk_config`；新 `RiskConfigDirectiveSink::demo(...)` struct（持 demo Arc）；clamp 在 `apply_patch` closure 內（§3.4）；tasks.rs spawn 處 wire（demo Arc，鏡像 :286）+ flag gate。
- **依賴**：B 依賴 A（matcher 函數）。A 可與 Phase-2 `promotion_criteria.rs`（live 促升 criteria reuse）並行（不同檔）。
- **E2 重點審查 3 點**：(1) **遞迴 matcher nested-widen**：`{"limits":{"leverage_max":50}}` 與 `{"cascade":{...}}` 必被拒（舊 top-level matcher 會放行 = 命門）；(2) **demo-only-Arc 結構閘**：grep + 型別證 RiskConfigDirectiveSink 欄位不含 `risk_stores.live`，且不調用 `select(engine_str)`（編譯期不可達 live）；(3) **allowlist-default-deny + U5**：未列舉葉 + 無 band 欄一律 default-deny；v1 對任何 RiskConfig patch 回 VetoedByDefaultDeny（證 inert）。
- Role chain：`PA → CC(證 P4 策略不繞風控 / P5 生存>利潤 / P7 學習不改 live / P11 自主在 P0/P1 內,MANDATORY) → E3(sink 在 live 結構不可達 + in-process 不繞 token 的補償閘,MANDATORY) → QC+MIT(哪個 leak-free edge metric 支撐哪個 risk 旋鈕 + tighten 方向 + 是否值得加 band,MANDATORY；v1 預期結論「暫不加任何 band」) → BB(live sizing 影響：v1 無 live 寫故 N/A，記為 Phase-2-promotion 時才復審) → E1-RUST-A ∥ (promotion_criteria) → E1-RUST-B → E2(對抗 3 點) → E4(Linux 真 engine：demo flag-ON 仍 default-deny 不動值 + audit row 落 + 確認 live ConfigStore 版本號不變) → CC final → PM`

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
- **U5(Phase 3,quant,QC) RESOLVED-AS-HARD-RULE**：親驗 DynamicStop/RegimeMultipliers struct **無 band 欄**（validate 只查 >0）→ §3.5 釘成硬規則「無 operator band → 留 denylist」，v1 allowlist 空 = inert（正確）。**剩餘 QC 工作（非 v1 阻塞）**：日後若要解禁某欄，QC 須回答「哪個 leak-free edge metric 支撐該風險旋鈕 + 哪個方向是 tighten」才加 band（§3.5 啟動路徑）。v1 預期 QC 結論=「暫不加任何 band」。

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
- **[PHASE-3 RESOLVED — 折入 §3.1]** denylist 補全 + 用真 RiskConfig 欄名（CC）：§3.1 已按親 grep 的真 dotted-path author 完整 `RISKCONFIG_SURVIVAL_DENYLIST`（含 halt_ttl/guardian/open_positions/notional/ft_*/**整個 cascade.***/**整個 cost_gate.* 5 欄含 min_confidence+adx_trending**/liquidation_buffer），並明示既有 `P0_P1_DENYLIST_FIELDS`(applier.rs:200-218) 舊名不可複用（max_leverage≠leverage_max 會靜默不 match）。
- **[PHASE-3 RESOLVED — 折入 §3.3]** nested 遞迴 matcher（CC + E2）：§3.3 新 `riskconfig_patch_leaves` 遞迴走整 patch 樹（取代只比 top-level 的 `find_denylisted_field` applier.rs:551-559）+ 前綴匹配(cascade/cost_gate/market_gate)+ allowlist-default-deny + E2 nested-widen 對抗測試清單。
- **[PHASE-3 RESOLVED — 折入 §3.2/§3.5]** U5 成硬 gate（CC）：§3.5 釘死「無 operator band → 留 denylist」硬規則；§3.2 列候選但全標 v1 deny（DynamicStop/RegimeMultipliers validate 只查 >0，親驗無 band 欄）；§3.5 設計 band-field 加法為唯一啟動路徑（band 欄自身 denylist + Option default None + 動態 allowlist 推導）。**v1 ship inert（allowlist 空）= 正確**已釘為節首結論。
- **[PHASE-3 RESOLVED — 折入 §3.4]** clamp-cannot-widen race（E2 MED-2）：§3.4 規定 clamp 在單一 `ConfigStore::apply_patch` closure（write_lock 內，store.rs:155-192）讀 band+clamp+寫，同 critical section 消除 band-narrow-during-UP race（不用 load→replace）。LCB-UP gate 真碼引 dynamic_risk_sizer.rs:275-290。
- **[PHASE-3 RESOLVED — 折入 §3.0]** in-process sink 自有 gate（E3 MED-2）：§3.0 demo sink 結構上**只**持 `Arc::clone(&risk_stores.demo)`（鏡像 EngineCommandSink::demo tasks.rs:286 + cost_edge_advisor_boot.rs:167 先例），編譯期不持 live Arc、禁用 `select(engine_str)`；**Phase 3 不新增任何 RiskConfig→live in-process 路徑**，live 促升唯一走 Phase-2 route+chokepoint+token。
- **news/quant-justification 須 server-side 驗值非 LLM 自述**（E3 MED-3 + CC §4 + E2 angle-6，**Phase 1 範疇**）：`quant_justification` free-text 是新注入出口+可被 news 敘事滿足。validate 須(1)news_context 標 untrusted 結構隔離;(2)引用的 quant 證據用 **engine 端獨立查/重算**(edge_estimates cell shrunk_bps 符號/量級與 delta 方向一致),news 在 gate 算術零權重;(3)新 reject 理由 `quant_justification_unverified`。news 只能在已獨立通過量化 gate 的選項間作 post-hoc tiebreaker。
- **migration 號 build 時釘**（E2 MED-4，**Phase 2 範疇**）：最高現為 V143。P2 `learning.strategist_promotions` build 前重查 next-free(≥V144)+Guard A+double-apply,勿信本 doc 佔位。**Phase 0 無新 migration**（復用 V014）。
- **method_registry 是描述非執行**（E2 MED-3）：真 wiring 在 dispatch.rs match arm(unknown→ERR_METHOD_NOT_FOUND);registry 條目 optional。

### LOW / 注意
- DynamicRiskSizer clamp 真碼在 maybe_update :199/:216/:298-306、LCB-UP :280-290（非 spec 引的 :42-99 config docs）。
- `OPENCLAW_LIVE_PATCH_SECRET` 須 chmod 600 + 與 IPC secret 分離檔（secret_env.rs:25 無權限檢查）。
- applier.rs 1072 行(>800)；P3 加 DirectiveType+sink 恐近 cap→考慮 sibling `applier_riskconfig.rs`。
- Phase 3 demo sink 須明確 `select("demo")`（engine_routing unknown→paper fallback 會誤落 paper）。
- **dirty-tree 撞號**：本 session 另一工作刪了 `openclaw_core/src/risk/regime.rs`（RegimeMultipliers 死配置修復）；P3 allowlist 含 `regime.*` 乘數→build 時確認不撞（該修復是 engine config.regime,P3 也是同源,需對齊）。

