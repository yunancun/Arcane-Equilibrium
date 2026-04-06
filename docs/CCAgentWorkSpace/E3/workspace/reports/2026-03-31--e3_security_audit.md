# E3 安全審計報告
生成時間：2026-03-31
審計員：E3 (Security Auditor)
系統：BybitOpenClaw AI 自動交易系統
審計範圍版本：Phase 0 Round 2.5 基線（2,227 tests passed）

---

## 嚴重性說明
- **CRITICAL**：可直接導致資金損失或系統完全失控
- **HIGH**：可能被利用導致嚴重後果
- **MEDIUM**：有風險但需特定條件
- **LOW**：最佳實踐違反，低風險

---

## 執行摘要

| 等級 | 數量 |
|------|------|
| CRITICAL | 3 |
| HIGH | 5 |
| MEDIUM | 6 |
| LOW | 5 |
| **合計** | **19** |

### 最緊急修復建議（按優先級）：

1. **[CRITICAL-1]** `openclaw_proxy` 端點無認證保護，任何人可代理訪問 OpenClaw 內部服務
2. **[CRITICAL-2]** `_require_operator_role()` 邏輯永遠拒絕合法 Operator，同時造成特權端點完全無法使用（DoS）
3. **[CRITICAL-3]** `PaperTradingEngine.submit_order()` 在 `governance_hub` 為 `None` 時完全跳過治理門檢
4. **[HIGH-1]** 登入端點 `/api/v1/auth/login` 速率限制為 120次/分鐘，可暴力破解密碼
5. **[HIGH-2]** `_run_restart_in_background()` 將 `pid` 和 `python` 路徑插入 Shell 腳本，存在信息洩漏和潛在注入面

---

## 一、治理 Gate 繞過（3 項）

### [CRITICAL-3] GovernanceHub 為 None 時完全繞過治理門檢
- **文件**：`app/paper_trading_engine.py:1081`
- **代碼**：
  ```python
  if self._governance_hub:          # ← 僅當 hub 非 None 才檢查
      if not self._governance_hub.is_authorized():
          ...reject...
  # 若 self._governance_hub 為 None，直接繼續執行訂單
  ```
- **攻擊場景**：若攻擊者能在應用程序初始化序列中阻止 `ENGINE.set_governance_hub(GOV_HUB)` 被調用（例如通過注入導致早期 import 失敗），或如果測試環境不設置 hub，`submit_order()` 將在不通過任何治理審批的情況下接受訂單。在測試模式下，`governance_hub = None` 是常見狀態，意味著測試代碼路徑不強制治理。
- **修復建議**：將 `if self._governance_hub:` 改為 fail-closed：
  ```python
  if self._governance_hub is None:
      _transition_order(order, ORDER_STATE_REJECTED, oms_sm=_oms)
      order["reject_reason"] = "governance_hub_unavailable"
      ...
      return state
  if not self._governance_hub.is_authorized():
      ...
  ```

### [HIGH-3] OPENCLAW_GOVERNANCE_ENABLED 環境變量可完全禁用治理
- **文件**：`app/governance_hub.py:167`
- **代碼**：
  ```python
  env_enabled = os.environ.get("OPENCLAW_GOVERNANCE_ENABLED", "true").lower() == "true"
  self._enabled = enabled and env_enabled
  ```
- **攻擊場景**：若攻擊者能修改環境變量（如通過配置注入、容器逃逸、或部署時誤配置），設置 `OPENCLAW_GOVERNANCE_ENABLED=false` 可完全禁用 GovernanceHub，使 `is_authorized()` 永遠返回 `False`（fail-closed），但也使整個治理框架無效化。更危險的是，如果業務邏輯錯誤地以 `not is_authorized()` 作為"可以繞過"的信號，可能導致完全失控。
- **修復建議**：移除此環境變量覆蓋。治理 Hub 只應通過程序代碼明確禁用，不應允許運行時環境變量修改。如需保留測試機制，應通過構造函數參數並記錄審計日誌。

### [MEDIUM-1] 治理 Hub 授權緩存 TTL 為 100ms，存在競態窗口
- **文件**：`app/governance_hub.py:527-531`
- **代碼**：
  ```python
  self._cache_ttl_ms = 100  # TTL in milliseconds
  if self._cached_auth_state is not None:
      cached_result, cached_ts_ms = self._cached_auth_state
      if now_ms - cached_ts_ms < self._cache_ttl_ms:
          return cached_result  # 鎖外讀取
  ```
- **攻擊場景**：在高頻交易場景下，緩存是鎖外讀取（lock-free）。若授權在 100ms 窗口內被撤銷（如 FROZEN 轉換），已緩存的 `True` 結果仍可能通過門檢。在系統進入 CIRCUIT_BREAKER 狀態的臨界時刻，可能有少量訂單在緩存過期前漏過。
- **修復建議**：在授權狀態降級/撤銷時立即清除緩存（現有代碼在 grant 時已有清除邏輯，但 revoke/freeze 路徑需確認）。審核 `revoke_all_active()`、`freeze()` 等方法是否清除 `_cached_auth_state`。

---

## 二、API 認證/授權問題（3 項）

### [CRITICAL-2] `_require_operator_role()` 類型不匹配——永遠拒絕合法 Operator（DoS）
- **文件**：`app/governance_routes.py:116-130`
- **根因分析**：
  ```python
  # governance_routes.py:95-108
  def _get_auth_actor() -> Any:
      actor = base.current_actor   # ← 返回 current_actor 函數對象本身
      return actor                  # FastAPI Depends 將再次調用它

  # 結果：Depends(_get_auth_actor()) 先調用 _get_auth_actor() 得到函數
  # 再調用 current_actor(authorization=...) 得到 AuthenticatedActor dataclass

  # governance_routes.py:116-119
  def _require_operator_role(actor: Any) -> None:
      if not actor or not isinstance(actor, dict):  # ← AuthenticatedActor 不是 dict！
          raise HTTPException(status_code=401, ...)  # ← 永遠觸發
  ```
- **驗證**：`AuthenticatedActor` 是 `@dataclass(slots=True)`，不是 `dict`，`isinstance(actor, dict)` 永遠為 `False`。
- **受影響端點**：
  - `POST /governance/auth/approve` (line 502)
  - `POST /governance/risk/override` (line 618)
  - `POST /governance/risk/de-escalation/{id}/approve` (line 786)
  - `POST /governance/recovery/{id}/approve` (line 914)
- **雙重後果**：
  1. 合法 Operator 無法使用這些端點（功能性 DoS）
  2. `actor.get(...)` 呼叫在 `not isinstance(actor, dict)` 分支**之後**，因此 line 129 的 `actor.get('user', 'unknown')` 也永遠不會執行
- **修復建議**：
  ```python
  def _require_operator_role(actor: Any) -> None:
      # AuthenticatedActor is a dataclass, not dict
      from . import main_legacy as base
      if not actor or not isinstance(actor, base.AuthenticatedActor):
          raise HTTPException(status_code=401, detail="Authentication required")
      if "operator" not in actor.roles and "operator_guarded" not in actor.roles:
          raise HTTPException(status_code=403, detail="Operator role required")
  ```

### [CRITICAL-1] `/openclaw/{path}` 反向代理端點無認證保護
- **文件**：`app/main.py:186-209`
- **代碼**：
  ```python
  @app.api_route("/openclaw/{path:path}", methods=["GET", "POST", "PUT", "DELETE"], include_in_schema=False)
  async def openclaw_proxy(path: str, request: Request):
      # 無 Depends(current_actor)！
      target = f"http://{_oc_host}:18789/{path}"
      ...
  ```
- **攻擊場景**：任何未認證的請求者可向 `/openclaw/任意路徑` 發送 GET/POST/PUT/DELETE 請求，該請求將被代理到 `localhost:18789`（OpenClaw Gateway）。由於沒有認證依賴，攻擊者可：
  1. 讀取 OpenClaw 內部狀態和配置
  2. 向 OpenClaw Gateway 的任意端點發送命令
  3. 若 OpenClaw 有寫入端點，可能觸發未授權操作
- **另一問題**：`_oc_host` 通過環境變量 `OPENCLAW_GATEWAY_HOST` 設置，若此變量被污染，可實現 SSRF
- **修復建議**：
  ```python
  @app.api_route("/openclaw/{path:path}", ...)
  async def openclaw_proxy(path: str, request: Request, actor=Depends(current_actor)):
      ...
  ```

### [HIGH-1] 登入端點缺乏暴力破解防護
- **文件**：`app/main_legacy.py:4096-4134`
- **問題**：`/api/v1/auth/login` 適用全局速率限制 `120/minute`（每秒 2 次），對密碼暴力破解無有效防護。無帳號鎖定、無指數退避、無 CAPTCHA。
- **攻擊場景**：攻擊者使用常見密碼字典（如 RockYou）以每分鐘 120 次速度嘗試，可在數分鐘到數小時內破解弱密碼。成功後獲得 API Bearer Token，可完全控制交易系統。
- **修復建議**：
  - 為 `/api/v1/auth/login` 設置嚴格速率限制（如 5次/分鐘）
  - 添加失敗計數和臨時鎖定（5次失敗後鎖定15分鐘）
  - 考慮添加 IP 封鎖邏輯
  ```python
  @app.post("/api/v1/auth/login", include_in_schema=False)
  @limiter.limit("5/minute")  # 更嚴格的限制
  async def auth_login(req: _LoginRequest, request: Request):
  ```

### [MEDIUM-2] `verify_operator_identity` 有已知 TOCTOU 競態條件
- **文件**：`app/main_legacy.py:1491-1498`
- **代碼注釋（官方文檔）**：
  ```python
  # KNOWN LIMITATION: This revision check runs BEFORE STORE.mutate() acquires the lock.
  # Under concurrent requests, the revision could change between this check and the actual mutation.
  ```
- **攻擊場景**：兩個並發的狀態修改請求攜帶相同的 `expected_state_revision`，第一個通過檢查並開始修改，第二個在鎖外的 `_assert_revision` 也通過（此時狀態仍是舊版本），然後在 `STORE.mutate()` 內部再次讀取時獲得已修改的狀態。這是已知問題（代碼中有注釋），風險相對低，但在高並發環境下可能導致狀態不一致。
- **修復建議**：將 `_assert_revision` 移入 `STORE.mutate()` 的鎖內部執行。

---

## 三、注入風險（3 項）

### [HIGH-2] Shell 腳本生成包含進程信息（潛在信息洩漏）
- **文件**：`app/main_legacy.py:4338-4346`
- **代碼**：
  ```python
  script_content = f"""#!/bin/bash
  sleep {delay_seconds}
  kill {pid} 2>/dev/null
  sleep 3
  cd {work_dir}
  nohup {python} -m uvicorn app.main:app --host 0.0.0.0 --port 8000 >> /tmp/openclaw_restart.log 2>&1 &
  """
  ```
- **分析**：`delay_seconds` 由 Pydantic 驗證為整數（5/10/15/30/60 的枚舉），`pid` 是 `os.getpid()` 的整數，`work_dir` 是硬編碼路徑，`python` 是 `sys.executable`。直接注入風險較低（已有整數驗證），但：
  1. 生成的腳本寫入 `/tmp/` 目錄（世界可寫），攻擊者可能讀取腳本並獲知服務器路徑和 PID
  2. 重啟日誌寫入 `/tmp/openclaw_restart.log`，攻擊者可讀取服務器啟動信息
  3. 服務器監聽 `--host 0.0.0.0` 被硬編碼在腳本中，若需改為安全模式（localhost）需手動修改
- **修復建議**：使用 `tempfile.mkstemp` 配合更嚴格的權限，限制日誌路徑為配置目錄而非 `/tmp/`。

### [HIGH-4] `web-pilot` subprocess 接收 AI 生成的查詢字符串
- **文件**：`app/layer2_tools.py:406-408`
- **代碼**：
  ```python
  proc = subprocess.run(
      [web_pilot, "search", query, "--max", str(max_results)],
      capture_output=True, text=True, timeout=30,
  )
  ```
- **分析**：`query` 是 AI 模型生成的搜索查詢。使用列表形式的 `subprocess.run`（非 `shell=True`），避免了 Shell 命令注入。但 `query` 字符串作為命令行參數直接傳入外部工具，若 `web-pilot` 自身存在參數注入漏洞（如以 `-` 開頭的查詢被解析為選項），可能產生意外行為。
- **注意**：`max_results` 使用 `str(int(...))` 轉換確保是純數字，安全。
- **修復建議**：在傳入前對 `query` 進行基本清理（截斷長度、過濾 null bytes）。考慮添加 `--` 分隔符防止查詢被解析為選項：`[web_pilot, "search", "--", query]`。

### [MEDIUM-3] `body.reason` 在 `/reconcile` 路由未經 sanitize 直接寫入日誌
- **文件**：`app/governance_routes.py:857`
- **代碼**：
  ```python
  logger.info(f"Manual reconciliation triggered by {actor}: {body.reason}")
  ```
- **問題**：`body.reason` 未調用 `_sanitize_string()` 處理，直接插入 f-string 進行日誌記錄。日誌注入攻擊者可以在 `reason` 中插入換行符和偽造的日誌條目（如 `\n[CRITICAL] Authorization granted to attacker`），污染日誌文件並干擾審計追蹤。
- **修復建議**：
  ```python
  sanitized_reason = _sanitize_string(body.reason, max_len=500)
  logger.info("Manual reconciliation triggered by %s: %s", actor, sanitized_reason)
  ```

---

## 四、密鑰/憑証洩漏（2 項）

### [MEDIUM-4] Bearer Token 存儲在 localStorage（可被 XSS 竊取）
- **文件**：`app/static/login.html:77`、`app/static/common.js:7-21`
- **代碼**：
  ```javascript
  localStorage.setItem(TOKEN_KEY, data.token);   // login.html:77
  const OC_TOKEN_KEY = 'oc_trading_token';       // common.js:7
  function ocGetToken() {
    return localStorage.getItem(OC_TOKEN_KEY) || '';
  }
  ```
- **攻擊場景**：localStorage 可被同源 JavaScript 訪問。若系統中存在 XSS 漏洞（見七節），攻擊者可通過 `localStorage.getItem('oc_trading_token')` 竊取 Bearer Token，進而完全控制 API。Token 是長期有效的（重啟前不失效），被竊取後影響持久。
- **替代方案**：考慮使用 `httpOnly + Secure` 的 Cookie 存儲 Token，防止 JavaScript 訪問。但需要後端添加 Cookie 支持和 CSRF 保護。

### [LOW-1] 敏感路徑在錯誤消息中暴露
- **文件**：`app/main_legacy.py:4114-4115`
- **代碼**：
  ```python
  except FileNotFoundError:
      raise HTTPException(status_code=500, detail="Auth config not found")
  ```
- **問題**：500 錯誤暴露了 "Auth config not found" 信息，攻擊者可通過此響應推斷認證配置文件是否存在於 `~/BybitOpenClaw/secrets/gui_auth.env`。此路徑在代碼中是硬編碼的（line 4103）。
- **修復建議**：統一 500 響應消息為 "Internal server error"，不暴露配置細節。

---

## 五、輸入驗證缺陷（2 項）

### [MEDIUM-5] 前端 trading.html 將服務端數據未轉義插入 innerHTML
- **文件**：`app/static/trading.html:424`、`457-465`、`481-490`
- **代碼**：
  ```javascript
  // line 424 - 信號來源名稱未轉義
  return `<tr><td>${t}</td><td>${src}</td><td class="${dirClass}">${dir}</td>...`;

  // line 459 - 策略 name 未轉義
  const name = (s.name || s.strategy_name || '--').replace(/_/g, ' ');
  return `<div class="strat-name">${name}</div>`;

  // line 486 - 指標 key/value 未轉義
  return `<div>...<span>${k}</span><span>${v}</span></div>`;
  ```
- **攻擊場景**：若攻擊者能控制交易系統中的策略名稱、指標名稱或信號來源（例如通過 Scout agent 掃描到一個交易對名稱包含 HTML），這些值將被未轉義地插入 DOM。前端已有 `ocEsc()` 函數但此處沒有使用。
- **當前風險等級**：MEDIUM（需要額外的服務端數據污染前提）
- **修復建議**：在 trading.html 中統一使用 `ocEsc()` 轉義所有服務端數據：
  ```javascript
  return `<tr><td>${ocEsc(t)}</td><td>${ocEsc(src)}</td>...`;
  const name = ocEsc((s.name || s.strategy_name || '--').replace(/_/g, ' '));
  ```

### [LOW-2] `symbol` 字段在 layer2 和 phase2 路由僅限長度，無格式驗證
- **文件**：`app/layer2_routes.py:102`
- **代碼**：
  ```python
  symbol: str = Field(default="BTCUSDT", max_length=30)
  ```
- **問題**：`symbol` 只驗證最大長度，不驗證格式（如字母數字）。惡意輸入如 `../config` 或 `; DROP TABLE` 雖不會觸發 SQL 注入（無 SQL 查詢使用 symbol），但可能被記錄到日誌或被 web-pilot 工具用作搜索查詢。
- **修復建議**：添加格式驗證：
  ```python
  symbol: str = Field(default="BTCUSDT", max_length=30, pattern=r"^[A-Z0-9]{1,30}$")
  ```

---

## 六、狀態機安全問題（2 項）

### [MEDIUM-6] `expected_previous_state` 可以設為 `None` 繞過狀態檢查
- **文件**：`app/main_legacy.py:1501-1505`
- **代碼**：
  ```python
  def _assert_previous_state(snapshot, envelope, allowed=None):
      current = snapshot["control_plane"]["demo_control"]["demo_state_switch"]
      expected = envelope.expected_previous_state
      if expected is None or expected != current or ...:  # ← None 直接短路
          raise HTTPException(...)
  ```
- **問題**：當 `expected_previous_state` 為 `None` 時，函數立即拋出異常（拒絕請求），而不是接受任意狀態。這是正確的 fail-closed 行為。但設計上，每個狀態轉換操作都要求提供明確的前置狀態，如果調用方不提供，操作將被拒絕。**確認**：這部分設計是安全的。

### [LOW-3] Paper Trading 狀態文件路徑來自環境變量
- **文件**：`app/paper_trading_routes.py:47-52`
- **代碼**：
  ```python
  _paper_state_path = os.getenv(
      "OPENCLAW_PAPER_STATE_FILE",
      os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "runtime", "paper_trading_state.json"))
  )
  ```
- **問題**：若攻擊者能控制環境變量 `OPENCLAW_PAPER_STATE_FILE`，可將路徑指向任意文件（如 `/etc/passwd` 或 `/proc/1/mem`），導致：讀取任意文件作為 JSON 狀態（失敗但洩漏錯誤信息），或將 trading 狀態寫入任意位置（若有寫權限）。
- **修復建議**：添加路徑規範化和白名單驗證，確保路徑在允許目錄內：
  ```python
  from pathlib import Path
  _allowed_base = Path(__file__).resolve().parent.parent / "runtime"
  _raw_path = os.getenv("OPENCLAW_PAPER_STATE_FILE", str(_allowed_base / "paper_trading_state.json"))
  _paper_state_path = str(Path(_raw_path).resolve())
  assert Path(_paper_state_path).is_relative_to(_allowed_base), "Invalid state file path"
  ```

---

## 七、前端安全問題（2 項）

### [MEDIUM-7] 缺乏安全 HTTP 響應頭（Content-Security-Policy 等）
- **文件**：`app/main_legacy.py`（全局未設置）
- **問題**：系統未設置以下安全響應頭：
  - `Content-Security-Policy`（CSP）：缺失，無法防止 XSS
  - `X-Frame-Options`：缺失，允許 clickjacking
  - `X-Content-Type-Options: nosniff`：缺失
  - `Referrer-Policy`：缺失
  - `Strict-Transport-Security`（HSTS）：缺失（通過 Tailscale 提供 HTTPS，但應用層面無強制）
- **修復建議**：添加安全頭中間件：
  ```python
  from starlette.middleware.base import BaseHTTPMiddleware
  class SecurityHeadersMiddleware(BaseHTTPMiddleware):
      async def dispatch(self, request, call_next):
          response = await call_next(request)
          response.headers["X-Content-Type-Options"] = "nosniff"
          response.headers["X-Frame-Options"] = "DENY"
          response.headers["Referrer-Policy"] = "strict-origin"
          # CSP 需要根據實際使用的 CDN/iframe 源定制
          return response
  app.add_middleware(SecurityHeadersMiddleware)
  ```

### [HIGH-5] CORS `allow_credentials=True` 配置風險
- **文件**：`app/main_legacy.py:4021-4025`
- **代碼**：
  ```python
  app.add_middleware(
      CORSMiddleware,
      allow_origins=_cors_origins.split(",") if _cors_origins else [],
      allow_credentials=True,   # ← 危險組合
      allow_methods=["GET", "POST"],
      allow_headers=["Authorization", "Content-Type"],
  )
  ```
- **問題**：`allow_credentials=True` 配合動態 `allow_origins` 配置存在風險。如果 `OPENCLAW_CORS_ORIGINS` 被設置為包含 `*`（Python CORS 庫會拒絕 `*` 加 credentials 的組合，但若設置為 `null` 或被誤配置），可能允許任意源帶憑據請求。另外，若 `OPENCLAW_CORS_ORIGINS` 設置不當（如包含開發服務器地址），生產環境存在 CSRF 風險（即使使用 Bearer Token，某些瀏覽器在 preflight 通過後仍可發出跨域請求）。
- **修復建議**：明確記錄 `OPENCLAW_CORS_ORIGINS` 的安全要求，在啟動時驗證：
  ```python
  if "*" in _cors_origins:
      raise RuntimeError("CORS wildcard origin with credentials is forbidden")
  ```

---

## 八、依賴安全風險（1 項）

### [LOW-4] requirements.txt 版本 Pin 不完整
- **文件**：`program_code/exchange_connectors/bybit_connector/control_api_v1/requirements.txt`
- **問題**：
  - 文件只列出 5 個直接依賴（fastapi, uvicorn, pydantic, pytest, httpx），未包含間接依賴
  - 無 `pip freeze` 完整鎖定文件（如 `requirements.lock`）
  - 實際安裝的 `slowapi==0.1.9`、`psycopg2-binary==2.9.11` 等未在 requirements.txt 中聲明
  - 缺乏 `safety` 或 `pip-audit` 漏洞掃描集成
- **當前已安裝版本**：fastapi 0.115.12（requirements）vs. 系統 0.135.2，版本不一致
- **修復建議**：
  - 補全 requirements.txt 或生成 `requirements.lock`
  - 在 CI 中集成 `pip-audit` 掃描

### [LOW-5] slowapi 版本 0.1.9 是相對舊版本
- **已安裝**：slowapi 0.1.9（2022 年版本）
- **問題**：slowapi 是一個小型庫，維護頻率低。建議定期審查是否有安全更新。目前無已知 CVE，但應納入依賴審計清單。

---

## 九、安全正面評估（系統做得好的地方）

### 治理框架設計優秀
1. **真正 fail-closed 的 GovernanceHub**：`is_authorized()` 在任何異常情況下均返回 `False`（lines 536-537, 552-556, 559-562）
2. **SM 授權拒絕訂單**：`check_order_allowed` 在 risk_manager 中真實拒絕訂單，非僅日誌記錄
3. **Decision Lease 雙重門檢**：先 `is_authorized()` 再 `acquire_lease()`，兩層獨立驗證
4. **跨 SM 級聯**：Risk ≥ CIRCUIT_BREAKER 自動觸發 Auth freeze，良好的聯動設計

### 認證機制安全
5. **恆定時間比較防時序攻擊**：`hmac.compare_digest()` 用於 Token 驗證（line 4055）
6. **Token 自動生成**：`secrets.token_urlsafe(32)` 生成高熵 Token，拒絕 "change-me" 佔位符
7. **Token 文件權限**：自動設置 `chmod 600`（line 4082），`chmod 700`（line 4083）

### 數據庫查詢安全
8. **全面參數化查詢**：`bybit_demo_sync.py` 和 `grafana_data_writer.py` 的所有 SQL 查詢均使用 `%s` 佔位符（psycopg2 的安全 API），無字符串拼接 SQL

### SSRF 防護
9. **`fetch_url` 工具有 SSRF 防護**：驗證 scheme、阻止 localhost/私有 IP、禁止重定向（`follow_redirects=False`）

### 密鑰管理
10. **無硬編碼密鑰**：Bybit API Key/Secret 通過 secrets 文件讀取，不硬編碼
11. **`.gitignore` 保護**：`.secrets/`、`secrets/`、`*.env` 均在 `.gitignore` 中

### 輸入驗證
12. **Pydantic 模型廣泛使用**：所有 API 請求模型使用 Pydantic `Field` 驗證（`max_length`、`ge/le` 範圍限制）
13. **`ocEsc()` HTML 轉義函數**：前端有統一的轉義工具，`tab-governance.html` 大量正確使用

### 速率限制
14. **全局速率限制**：SlowAPIMiddleware 應用於所有端點（120次/分鐘默認），有效防止 DDoS

### 異常處理
15. **零 `except: pass`（核心代碼）**：所有異常要么 fail-closed 返回拒絕，要么帶 `logger.exception()` 記錄，符合系統要求

---

## 十、緊急修復行動項

### CRITICAL 優先級（立即修復）

#### FIX-C1：為 OpenClaw 代理端點添加認證
**文件**：`app/main.py:186-209`

```python
# 修復前
@app.api_route("/openclaw/{path:path}", methods=["GET", "POST", "PUT", "DELETE"], include_in_schema=False)
async def openclaw_proxy(path: str, request: Request):

# 修復後
@app.api_route("/openclaw/{path:path}", methods=["GET", "POST", "PUT", "DELETE"], include_in_schema=False)
async def openclaw_proxy(path: str, request: Request, actor=Depends(base.current_actor)):
    # 需要在 app/main.py 頂部導入 base
```

#### FIX-C2：修復 `_require_operator_role` 類型檢查
**文件**：`app/governance_routes.py:116-130`

```python
def _require_operator_role(actor: Any) -> None:
    """Validate that actor has Operator role."""
    from . import main_legacy as base
    if not actor or not isinstance(actor, base.AuthenticatedActor):
        raise HTTPException(status_code=401, detail="Authentication required")
    # Check roles set
    operator_roles = {"operator", "operator_guarded"}
    if not (actor.roles & operator_roles):
        actor_id = getattr(actor, 'actor_id', 'unknown')
        logger.warning("Non-operator attempted privileged operation: %s", actor_id)
        raise HTTPException(status_code=403, detail="Operator role required")
```

#### FIX-C3：GovernanceHub 為 None 時 fail-closed
**文件**：`app/paper_trading_engine.py:1081`

```python
# 修復前（條件跳過治理）
if self._governance_hub:
    ...governance check...

# 修復後（None 時 fail-closed）
if self._governance_hub is None:
    _transition_order(order, ORDER_STATE_REJECTED, oms_sm=_oms)
    order["reject_reason"] = "governance_hub_unavailable"
    state["orders"].append(order)
    result["order"] = order
    result["rejected_reason"] = "governance_hub_unavailable"
    self._audit(state, "order_rejected_no_governance",
                f"{symbol} {side} rejected: governance hub not initialized (fail-closed)")
    return state
# 然後繼續現有的 is_authorized() 檢查
try:
    if not self._governance_hub.is_authorized():
```

### HIGH 優先級（24小時內修復）

#### FIX-H1：登入端點專用速率限制
**文件**：`app/main_legacy.py:4096`

```python
@app.post("/api/v1/auth/login", include_in_schema=False)
@limiter.limit("5/minute")    # 從 120/min 降至 5/min
async def auth_login(req: _LoginRequest, request: Request):
```

#### FIX-H2：修復日誌注入（reconcile 路由）
**文件**：`app/governance_routes.py:857`

```python
# 修復前
logger.info(f"Manual reconciliation triggered by {actor}: {body.reason}")

# 修復後
sanitized_reason = _sanitize_string(body.reason, max_len=500)
actor_id = getattr(actor, 'actor_id', str(actor))
logger.info("Manual reconciliation triggered by %s: %s", actor_id, sanitized_reason)
```

#### FIX-H3：為 web-pilot 搜索查詢添加 `--` 分隔符
**文件**：`app/layer2_tools.py:406-408`

```python
proc = subprocess.run(
    [web_pilot, "search", "--", query[:500], "--max", str(max_results)],
    capture_output=True, text=True, timeout=30,
)
```

### MEDIUM 優先級（本週修復）

#### FIX-M1：trading.html 添加 ocEsc() 轉義
**文件**：`app/static/trading.html:418-490`

```javascript
// 所有服務端字符串插入均通過 ocEsc() 轉義
return `<tr><td>${ocEsc(t)}</td><td>${ocEsc(src)}</td>...`;
return `<div class="strat-name">${ocEsc(name)}</div>`;
return `<span>${ocEsc(String(k))}</span><span>${ocEsc(String(v))}</span>`;
```

#### FIX-M2：添加安全響應頭
**文件**：`app/main_legacy.py`（在 CORS 中間件後添加）

```python
from starlette.middleware.base import BaseHTTPMiddleware
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response
app.add_middleware(SecurityHeadersMiddleware)
```

#### FIX-M3：symbol 字段添加格式驗證
**文件**：`app/layer2_routes.py:102`（及其他路由中的 symbol 字段）

```python
import re
_SYMBOL_PATTERN = r"^[A-Z0-9]{1,30}$"
symbol: str = Field(default="BTCUSDT", max_length=30, pattern=_SYMBOL_PATTERN)
```

---

## 附錄：審計覆蓋的文件列表

| 文件 | 審計重點 |
|------|---------|
| `app/main.py` | 代理端點、路由注冊 |
| `app/main_legacy.py` | 認證、CORS、速率限制、Shell 腳本、狀態機 |
| `app/governance_hub.py` | GovernanceHub fail-closed、緩存、環境變量繞過 |
| `app/governance_routes.py` | 授權、角色檢查、輸入清理 |
| `app/paper_trading_engine.py` | 治理門檢、None 繞過 |
| `app/paper_trading_routes.py` | 初始化、Hub 注入 |
| `app/bybit_demo_connector.py` | 密鑰管理、簽名生成 |
| `app/bybit_demo_sync.py` | SQL 查詢安全 |
| `app/grafana_data_writer.py` | SQL 查詢安全 |
| `app/layer2_tools.py` | SSRF 防護、subprocess、URL 驗證 |
| `app/layer2_routes.py` | 輸入驗證 |
| `app/telegram_alerter.py` | 密鑰日誌 |
| `app/static/common.js` | Token 存儲、ocEsc 實現 |
| `app/static/login.html` | Token 存儲機制 |
| `app/static/trading.html` | XSS via innerHTML |
| `app/static/tab-governance.html` | innerHTML 使用 |
| `requirements.txt` | 依賴版本 |
| `.gitignore` | 密鑰保護 |
| `docker_projects/trading_services/.env` | 配置安全 |

---

*本報告於 2026-03-31 生成，基於靜態代碼分析。建議在修復後進行回歸測試，確保安全修復不影響現有 2,227 個測試用例。*
