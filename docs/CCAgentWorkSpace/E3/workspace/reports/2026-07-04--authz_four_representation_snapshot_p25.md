# E3 — 授權四表示法一致性快照 + P2-1 憑證判準對齊 spec · 2026-07-04

> 角色：E3（攻擊者思維，read-only）。任務 P2-5（授權四表示法同刻快照 + fail-open 分析）+ 順帶 P2-1（`_resolve_credentials` `is_mainnet`→`is_live_slot` 修法 spec）。
> 凍結基準：Mac HEAD `2be58c191`（==Linux checkout，本輪錨點一致）。Linux runtime HEAD `3a050b60`（07-04 16:40 窗口後）。runtime 一律 read-only（SELECT/讀檔/proc/curl-GET）。
> 誠實聲明：fact=親測 runtime/源碼；inference=源碼推導的當前態；assumption=未能 runtime 直證處已標。

## 0. 摘要（verdict）

- 四表示法**當前態全一致**（LiveDemo 無 authorization.json → 全鏈 fail-closed，無 live 授權活躍）。**0 CRITICAL / 0 HIGH**。
- **P2-5 fail-open 窗口**：撤權方向存在 **≤5s bounded 窗口**（Rust Live pipeline teardown latency），期間「GUI 已顯示撤權但 Rust 引擎理論上仍可下單」——**by-design、bounded、IPC-trigger 緩解**，評 **INFO/LOW-1**（非缺陷，設計取捨；real money 僅 Mainnet，現 runtime=LiveDemo+ALLOW_MAINNET=0）。
- **P2-1 憑證判準漂移**：`bybit_rest_client.py` Python 端仍以 `is_mainnet` 判 env-fallback；**Rust 端已於「P1-08 cold audit pkg B」修為 `is_live_slot`**（`bybit_rest_client.rs:1058`），Python drop-in **未同批更新** → Rust↔Python 契約漂移。評 **MED（代碼級）/ 但 runtime 當前 NOT exploitable（LOW）**：engine+uvicorn 進程 env **無** `BYBIT_API_KEY/SECRET`，secrets/environment_files 與 compose_env **無**該兩 env 定義，故當前無可回退來源；latent（任何未來設此 env 的路徑即靜默覆寫 operator live slot）。給 E1 完整 spec 見 §4。

## 1. 四表示法同刻快照對表（2026-07-04 runtime）

| # | 表示法 | 當前值 | 資料來源（SSOT） | 證據等級 |
|---|---|---|---|---|
| ① | runtime authorization.json | **ABSENT**（`find ~/BybitOpenClaw/secrets -name authorization.json` 空） | `~/…/secret_files/bybit/live/authorization.json` | FACT（親測） |
| ② | Rust 引擎側視圖 | Live pipeline **未 spawn**（`load_and_verify`→`FileMissing`）；endpoint=LiveDemo（`live/bybit_endpoint`="demo"）、`OPENCLAW_ALLOW_MAINNET=0` | `live_authorization::load_and_verify` + `live_auth_watcher`（5s poll + IPC trigger） | FACT（endpoint/mainnet 親測 /proc + slot 檔）；pipeline 態=inference（源碼推導：檔缺→FileMissing→不 spawn） |
| ③ | Python gate | `verify_signed_authorization` → raise `authorization`（missing）→ `all_five_live_gates_ok(require_authz=True)`=False，live 寫入面阻擋 | `live_preflight.py:88`（每次 preflight 現讀檔） | FACT（源碼）+ inference（當前檔缺→必 raise） |
| ④ | GUI 顯示 | `signed_authorization.status`=missing / reason=`authorization_json_missing`；`execution_authority='not_granted'`；`session_state='offline'` | GUI 讀 `/api/v1/live/auth/trust-status` → `_read_signed_live_authorization_status()`（Python 現讀 authorization.json，live_trust_routes.py:415-532） | inference（endpoint auth-gated 回 `unauthenticated`，無 operator session 無法直取；由源碼+①推導） |

**結論**：四表示法在「無授權」態 **coherent**，全部 fail-closed。已知 LiveDemo 缺 authorization.json 態內部一致，非缺陷。

## 2. 授權傳播鏈架構（fail-open 分析基礎）

三個代碼表示法**各自獨立現讀同一 SSOT 檔**（`live/authorization.json`），各自 HMAC-SHA256 驗簽 + expiry 檢查，**簽名邏輯 parity**：

- **Python gate**（`live_preflight.py:141-200`）：`_hmac.new(signing_key…).hexdigest()` + `compare_digest`（:168，常數時間）+ `expires_at_ms <= now_ms` reject（:180）+ env-match（:191）。canonical payload=`ltr._canonical_authorization_payload`。**每次 live 寫入 preflight 現讀檔**（session start/resume/risk-config）。
- **GUI trust-status**（`live_trust_routes.py:415-532`）：同讀檔、同驗簽，但**回狀態 dict 不 raise**（診斷端點）。GUI 每次 poll 現讀。
- **Rust watcher**（`live_authorization::load_and_verify` + `live_auth_watcher`）：`verify_in_memory`（:312）—`compute_signature`（HMAC-SHA256）+ `constant_time_eq`（:299）+ `expires_at_ms <= now_ms` reject（:339）+ env check（:354）。canonical payload=pipe-separated `version|tier|issued_at_ms|expires_at_ms|operator_id|approved_system_mode|env_allowed_sorted_csv`（:263）。**每 5s poll + IPC `trigger_live_auth_recheck` 現讀**（≤5s TTR，happy-path 近即時）。

**關鍵不對稱（攻擊者視角）**：唯一「真正 gate 實錢下單」的表示法是 **Rust pipeline 存在性**——
- Python gate 守的是 HTTP **session start** 寫入口；一旦 Live session 已跑，on_tick 策略信號經 `dispatch.rs:436/446 om.place_order` → `order_manager.rs:354 place_order` 派單，**該路徑無 per-order Python 或 Rust 授權複驗**（grep `order_manager.rs` 0 個 `load_and_verify`/`live_reserved`/`SystemMode`/`authoriz`）。
- 即：**Live pipeline「存在」= 授權 enforcement**，撤權靠 watcher teardown pipeline，而非 place_order 逐單查授權。

## 3. Fail-open 窗口分析

### Scenario A — 撤權（revoke / 過期 / halt-auto-revoke）→ 存在 ≤5s bounded 窗口

1. Python revoke/halt 路徑刪 authorization.json（`live_trust_routes.py:812`）+ 觸發 `_trigger_live_auth_recheck_fire_and_forget()`（3 callsite：:842 / :1041 / :1143）。
2. Rust watcher 收 IPC trigger → 立即 recheck → `load_and_verify`→FileMissing → teardown Live pipeline（近即時）。
3. **fail-open 窗口**：authorization.json 刪除 → Rust teardown 完成之間。
   - happy-path（IPC trigger 送達）：亞秒級。
   - IPC trigger 失敗（fire-and-forget daemon thread + try/except，:605 只記 log）：退回 5s poll backstop → **≤5s 窗口**。
   - 窗口內若有 in-flight on_tick 觸發信號 → 仍可經存活 pipeline 派 live 單。
4. **GUI 同刻已顯示撤權**（下次 poll 現讀 authorization.json missing）→ 命中任務所指「GUI 顯示已撤權但引擎仍可下單」情境。

**判定 = INFO/LOW-1（非缺陷）**：窗口 by-design bounded（watcher 存在正是把 Phase 2 的 300s 收到 5s）+ IPC trigger 把 happy-path 壓到亞秒 + 5s poll 為保證 backstop + 實錢僅 Mainnet（現 runtime LiveDemo + ALLOW_MAINNET=0，無實錢面）。**若 operator 要求零窗口**：需在 Rust place_order 或 dispatch 加一個廉價的 authz-epoch（如 watcher 每次 verify 後 bump 一個 AtomicU64 epoch，place_order 對比 epoch≠當前有效即 fail-closed）——非本輪修，記為設計 follow-up。

### Scenario B — 授權（renew / approve）→ fail-CLOSED 方向（安全）

Python/GUI 顯示「已授權」（現讀檔通過）但 Rust pipeline 尚未 respawn（≤5s poll + exponential backoff）。此方向**無單可下**（pipeline 未起）→ fail-closed，僅 availability/UX，非安全 fail-open。

### 反向（「GUI 顯示已授權但引擎已撤」）— 不成立

三表示法同讀同一檔、同驗簽邏輯 parity，不存在「GUI 讀到有效但 Rust 讀到無效」的持久分歧（唯一差異是 Rust 5s poll 相位，且 Rust 更嚴/更快 teardown）。GUI 因與 Python 同為「現讀檔」，撤權後 GUI 立即翻 missing，不會落後於引擎。

## 4. P2-1 給 E1 的可執行修法 spec（`is_mainnet`→`is_live_slot`）

### 4.1 錨點與根因（FACT）

- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/bybit_rest_client.py:196` `is_mainnet = (env == "mainnet")`
- `:197` `slot = _SECRET_SLOTS.get(env, "demo")`（`live_demo`→"live"，`mainnet`/`live`→"live"，`demo`/`testnet`→"demo"）
- `:201` `if key is None and not is_mainnet:` → env `BYBIT_API_KEY` fallback
- `:209` `if secret is None and not is_mainnet:` → env `BYBIT_API_SECRET` fallback
- **漂移**：`live_demo` 映射 "live" slot 但 `is_mainnet==False` → env-fallback **開啟** → 任何能設進程 env 的路徑可覆寫 operator 管理的 live slot 憑證，繞過 live-slot 來源/審計。違反 CLAUDE.md §四「LiveDemo does not relax authorization」+ 破 Rust-parity（Rust `bybit_rest_client.rs:1058` 已修）。

### 4.2 修法（EXACT 鏡像 Rust `bybit_rest_client.rs:1051-1089`）

在 `_resolve_credentials` 內（:196-197 後）：
```
is_live_slot = (slot == "live")   # 涵蓋 mainnet + live_demo（== Rust rust:1058）
```
把 `:201` 與 `:209` 的 `not is_mainnet` 改為 `not is_live_slot`。`is_mainnet`（:196）改後在該函數內變 unused → 移除。
**必須保留不變**（real-money 專屬，鏡像 Rust `:1095`/gate#1）：ctor `:262/:266`（Gate#1 `OPENCLAW_ALLOW_MAINNET`）與 `:280`（Gate#3 空憑證 fail-closed）**仍鍵於 `is_mainnet`，不擴大到 live_demo**（LiveDemo 連 demo 端點，非實錢，OPENCLAW_ALLOW_MAINNET 與空憑證硬 raise 不適用；Rust 註解 :1056-1057 明示同一取捨）。

### 4.3 所有 callsite 清單（production）

| callsite | 構造 | env | 受本修影響？ |
|---|---|---|---|
| `live_session_routes.py:278`（`_get_rust_client_safe`） | `BybitClient(environment=environment)`，environment=`"live_demo"`（endpoint=="demo"）或 `"mainnet"` | **live_demo** | **是**——唯一觸發 P2-1 的 prod 路徑；修後 live_demo 不再吃 env fallback，只認 live slot 檔 |
| `strategy_ai_routes.py:154`（`_get_rust_client`） | `BybitClient()`（默認 environment="demo"） | demo | 否——demo slot（is_live_slot=False）仍允 env fallback（正確，demo 學習源可放寬） |
| `executor_config_cache.py:486` | `CanaryCohort(environment=env_val…)` | N/A | **假陽性**——非 BybitClient，是 CanaryCohort 欄位 |

`_resolve_credentials` 唯一內部 caller=ctor `:276`。

### 4.4 回歸測試點（給 E1；`tests/test_bybit_rest_client.py`）

現有覆蓋缺口：`:202 test_resolve_credentials_mainnet_prefers_param` 只證 mainnet；`:935 test_place_order_live_demo_allowed_passes_guard` 用**顯式** key/secret，**未**測 env-fallback 路徑。**無任何測試證 live_demo 忽略 env**。新增：
1. `test_resolve_credentials_live_demo_ignores_env`：`monkeypatch.setenv("BYBIT_API_KEY","envK")` + `setenv("BYBIT_API_SECRET","envS")`，`_resolve_credentials("live_demo", None, None)` → 斷言回值 **NOT** ("envK","envS")（應落 slot 檔或空），證 env 被忽略。
2. `test_resolve_credentials_live_demo_parity_with_mainnet`：同 env 下 live_demo 與 mainnet 對 env-fallback 行為一致（皆忽略）。
3. `test_resolve_credentials_demo_still_uses_env`（**行為保留守衛**）：demo env 下 env var **仍**被採用（防止過度收緊誤傷 demo）。
4. 保持 `:935` live_demo place_order 守衛測試綠（顯式憑證路徑不受影響）。
5. Rust-parity 註解引用 `bybit_rest_client.rs:1058`（is_live_slot SSOT）。

### 4.5 runtime exploitability（FACT）

- engine PID 3159871 與 uvicorn PID 3160250 的 `/proc/*/environ` **均無** `BYBIT_API_KEY`/`BYBIT_API_SECRET`。
- `~/BybitOpenClaw/secrets/environment_files` 與 `compose_env` grep **無** 該兩 env 定義。
- → **當前 NOT exploitable**（無可回退來源）。latent：任何未來 cron/wrapper/compose 引入該 env 即靜默覆寫 operator live slot（LiveDemo）。修 = 消除此 latent 面 + 恢復 Rust↔Python parity。

## 5. Findings 總表

| 嚴重性 | 位置 | 攻擊路徑 | 修法 |
|---|---|---|---|
| **MED（代碼級）/ LOW（runtime latent）** P2-1 | `bybit_rest_client.py:196/201/209` | live_demo 走 "live" slot 但 `is_mainnet==False` → env `BYBIT_API_KEY/SECRET` fallback 開啟 → 進程 env 覆寫 operator live 憑證，繞 live-slot 來源/審計；破 Rust-parity | §4：`not is_mainnet`→`not is_live_slot`（鏡像 rust:1058），Gate#1/#3 保留 is_mainnet；補 3 回歸測試 |
| **INFO / LOW-1** P2-5 fail-open | `live_auth_watcher` teardown latency × `order_manager.rs:354` 無 per-order authz | 撤權後 ≤5s 窗口內 in-flight on_tick 可經存活 Live pipeline 派單（GUI 已顯撤權）；IPC-trigger 失敗才落到 5s poll | by-design bounded，非缺陷；若要零窗口→Rust place_order 加 authz-epoch fail-closed 檢查（設計 follow-up，非本輪） |
| **INFO** 假陽性 | `executor_config_cache.py:486` | grep `environment=` 命中，實為 `CanaryCohort` 欄位非 BybitClient | 無需修（列附錄供 PM 裁決） |

## 6. 附錄：證據錨點

- authz SSOT 檔缺席：`ssh trade-core find ~/BybitOpenClaw/secrets -name authorization.json` = 空
- endpoint=LiveDemo：`live/bybit_endpoint`="demo"；`OPENCLAW_ALLOW_MAINNET=0`（/proc/3159871/environ）
- live slot 檔存在：`api_key`(18B)/`api_secret`(36B)/`bybit_endpoint`（Gate4 滿足）
- Rust 獨立驗簽：`live_authorization.rs:312 verify_in_memory`（constant_time_eq :299 / expiry :339 / env :354）；watcher `live_auth_watcher.rs`（5s poll + IPC trigger，≤5s TTR）
- Python 驗簽：`live_preflight.py:168 compare_digest` / `:180 expiry` / `:191 env`
- GUI 讀：`tab-live.js:112 /api/v1/live/auth/trust-status` → `signed_authorization`（:140）+ `execution_authority`（:237）
- IPC trigger 3 fire point：`live_trust_routes.py:842/1041/1143`
- 無 per-order authz：`order_manager.rs:354 place_order` grep 0 個 authz/live gate
- Rust 已修 P2-1：`bybit_rest_client.rs:1058 let is_live_slot = slot == "live"`（註解「P1-08 cold audit pkg B」）
- 進程/env-file 無 BYBIT_API_KEY/SECRET → P2-1 當前不可利用（latent-only）

