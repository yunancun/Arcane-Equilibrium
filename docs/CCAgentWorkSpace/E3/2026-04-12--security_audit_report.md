# E3 全面安全審計報告 / Full-Program Security Audit Report

**日期 / Date**: 2026-04-12
**審計員 / Auditor**: E3 Security Engineer
**範圍 / Scope**: Rust openclaw_engine/core/types/pyo3 + Python control_api_v1 + GUI 靜態文件
**基線 / Baseline**: commit `1961847` (main branch)

---

## 審計摘要 / Audit Summary

| 嚴重等級 | 數量 | 狀態 |
|---------|------|------|
| CRITICAL | 1 | 需立即處理 |
| HIGH | 4 | 建議本周內修復 |
| MEDIUM | 5 | 計劃中修復 |
| LOW | 4 | 可排入迭代 |

**總體評估**：系統安全基礎紮實。Rust 端所有 DB 查詢均使用參數化綁定（sqlx `$N` + `push_bind`），消除 SQL 注入風險。IPC HMAC-SHA256 認證、GUI HttpOnly cookie、CORS 白名單、CSP 頭、rate limiting、constant-time 密碼比對等關鍵安全控制均已到位。下列發現主要集中在 **配置完善度**（IPC 認證非強制）和 **前端 XSS 殘留場景**。

---

## 1. Gate 繞過分析 / Gate Bypass Analysis

### SEC-A01 [LOW] fast_track 閃崩/保證金危機分支為死碼

**文件**: `rust/openclaw_engine/src/tick_pipeline/on_tick.rs:156-160`

```rust
let ft_action = crate::fast_track::evaluate_fast_track(
    self.governance.risk.level,
    0.0, // PNL-4 dead input
    0.0, // PNL-4 dead input
);
```

**描述**: `price_drop_pct` 和 `margin_utilization_pct` 硬編碼為 `0.0`，導致 `fast_track.rs:35-43` 的閃崩偵測（>=5% 跌幅）和保證金危機（>=90% 使用率）兩條 CloseAll 路徑永遠不觸發。唯一可觸發的 CloseAll 是 `risk_level >= CircuitBreaker`。

**風險**: 真實閃崩或保證金危機時，這兩條安全防線無法啟動。已記錄為 PNL-4 待修。

**OWASP**: A04:2021 Insecure Design

**評級**: LOW（已有文檔追蹤，且 CircuitBreaker 路徑仍有效；Live 未上線）

---

### SEC-A02 [INFO] StrategyAction::Close 輕量路徑 — 設計正確

**文件**: `rust/openclaw_engine/src/tick_pipeline/on_tick.rs:841-940`

**結論**: Close 路徑正確跳過 Guardian / cost_gate / Kelly / P1 — 這是 **設計意圖**（平倉降低風險，不增加風險）。保留了：
- 費用計算（fee_rate 正確乘入）
- PG 持久化（emit_close_fill → TradingMsg::Fill）
- 影子訂單（exchange mode 的 dispatch_close_order）
- Kelly 統計更新
- 審計追蹤（recent_intents + recent_fills 環形緩衝）

**安全**: 無繞過問題。Close 不能被策略用於 _開倉_（因為它調用 `close_position_at_symbol_market` 而非 execute_market_fill）。

---

### SEC-A03 [INFO] P1 硬上限 — 實施正確

**文件**: `rust/openclaw_engine/src/intent_processor/router.rs:140-148` (paper) + `:382-388` (exchange)

```rust
let p1_max_qty = if price > 0.0 {
    balance * self.p1_risk_pct / price
} else {
    kelly_qty  // price=0 fallback: no cap — but qty=0 will be caught by PNL-1 below
};
let final_qty = kelly_qty.min(p1_max_qty);
```

**結論**: P1 上限在 paper 和 exchange 兩條路徑中均強制執行，且 `p1_risk_pct` 通過 `set_p1_risk_pct()` 有 clamp(0.001, 0.20) 範圍限制。`price <= 0` 時 PNL-1 的 `!(final_qty > 0.0)` 會攔截。

---

### SEC-A04 [INFO] Guardian 4-check — 完整且不可繞過

**文件**: `rust/openclaw_engine/src/intent_processor/router.rs:17-26` (Gate 1) + `:45-107` (Gate 2)

**結論**: `process()` 和 `process_gates_only()` 兩條路徑均強制通過：
1. Gate 1: governance authorization check (`is_authorized()`)
2. Gate 1.5: 同方向重複倉位阻擋
3. Gate 2: Guardian 4-check（drawdown、持倉數、方向）
4. Gate 2.5: Kelly sizing
5. Gate 2.6: P1 硬上限
6. Gate 2.7: RRC-1 訂單准入（日損/槓桿/曝險）
7. Gate 3: Cost gate（模式感知）

所有 gate 均 fail-closed（返回拒絕，不繼續執行）。

---

## 2. 注入漏洞 / Injection Vulnerabilities

### SEC-B01 [INFO] Rust SQL — 全部參數化（無注入風險）

**文件**: `rust/openclaw_engine/src/database/` 全部 writer + detector 文件

**結論**: 所有 Rust 端 SQL 查詢均使用 sqlx 的 `QueryBuilder::push_bind()` 或 `sqlx::query().bind()` 參數化綁定，包括：
- `trading_writer.rs`: 7 個 flush 函數全部用 `push_values + push_bind`
- `experiment_ledger_pg.rs`: `$1..$15` 參數化 INSERT/UPDATE/SELECT
- `drift_detector.rs`: 純常量 SQL，無用戶輸入
- `context_writer.rs`, `feature_writer.rs`, `quality_writer.rs`: 全部 `push_bind`

**安全**: 無 SQL 注入風險。

---

### SEC-B02 [MEDIUM] Python parquet_etl.py — f-string 格式化 SQL

**文件**: `program_code/ml_training/parquet_etl.py:56,65-72,77-84,93`

```python
conn.execute(f"ATTACH '{db_url}' AS pg (TYPE postgres, READ_ONLY);")
ctx_query = f"""
    COPY (
        SELECT * FROM pg.trading.decision_context_snapshots
        WHERE ts >= '{start_str}' AND ts < '{end_str}'
        ...
```

**描述**: 使用 f-string 格式化 SQL 查詢，db_url 和日期字符串直接插入。

**緩解因素**:
1. 此腳本為離線 ETL 工具（不是 API endpoint）
2. 輸入來源是 `datetime.utcnow()` 計算的日期（非用戶輸入）
3. `db_url` 來自內部配置
4. DuckDB 的 `ATTACH` 是獨立連接，與主 PG 隔離

**風險**: 低（無外部攻擊面），但違反了防禦性編碼原則。

**建議**: 使用 DuckDB 的參數化查詢或至少 validate/sanitize 日期格式。

**OWASP**: A03:2021 Injection

---

### SEC-B03 [MEDIUM] GUI tab-live.html — onclick 中的 symbol 注入點

**文件**: `app/static/tab-live.html:736`

```javascript
<td><button ... onclick="closeLivePosition('${sym}')">平倉</button></td>
```

其中 `sym = ocEsc(p.symbol || '')`。

**描述**: `ocEsc()` 轉義了 `<`, `>`, `&`, `"` 但 **未轉義單引號 `'`**。如果 Bybit 返回的 symbol 中包含單引號（如 `BTCUSDT'); alert('XSS`），可以逃出 onclick 的字符串字面量。

**ocEsc 實現** (`common.js:369-372`):
```javascript
function ocEsc(s) {
  if (s == null) return '';
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  // 缺少: .replace(/'/g, '&#x27;')
}
```

**緩解因素**:
1. Bybit API 的 symbol 格式為 `BTCUSDT`（純字母數字），實際上不可能包含單引號
2. `closeLivePosition()` 使用 `encodeURIComponent(symbol)` 構建 URL，但注入發生在 onclick 屬性中
3. CSP 有 `'unsafe-inline'`，無法阻止 inline event handler 中的腳本

**建議**: `ocEsc()` 追加 `.replace(/'/g, '&#x27;')` 以防禦性完整覆蓋。或改用 `addEventListener` 綁定事件。

**OWASP**: A03:2021 Injection (XSS)

**評級**: MEDIUM（實際可利用性極低，但屬 defense-in-depth 缺口）

---

### SEC-B04 [LOW] IPC 方法路由 — 無注入風險

**文件**: `rust/openclaw_engine/src/ipc_server/mod.rs:656`

**結論**: IPC dispatch 使用 Rust `match method {}` 靜態字符串匹配，只處理白名單方法。未知方法返回 `ERR_METHOD_NOT_FOUND`。`req.params` 透過 `serde_json::Value` 反序列化，類型安全。symbol 等字符串參數用 `as_str()` 提取後直接傳入業務邏輯（不拼接 SQL 或 shell 命令）。無命令注入風險。

---

## 3. 密鑰洩漏 / Secret Management

### SEC-C01 [INFO] API 密鑰日誌 — 未發現洩漏

**結論**: `grep` 掃描 Rust 全部 `tracing::` 調用，未發現任何對 `api_key`、`api_secret`、`secret`、`credential`、`password` 的日誌記錄。REST client 的 credentials 只在 HMAC 簽名時使用，簽名結果也未記錄。

---

### SEC-C02 [INFO] Secret 文件權限 — 實施正確

**文件**: `app/settings_routes.py:157-178`

```python
def _write_key_file(slot, filename, content):
    slot_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(slot_dir, stat.S_IRWXU)      # 700
    path.write_text(content.strip())
    os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)  # 600
```

**結論**: 目錄 chmod 700，文件 chmod 600，符合安全最佳實踐。`.gitignore` 已排除 `secrets/`、`**/secret_files/`、`*.env`。

---

### SEC-C03 [INFO] Rust secret 文件讀取 — 無路徑遍歷

**文件**: `rust/openclaw_engine/src/bybit_rest_client.rs:735-755`

**結論**: `read_secret_file(slot, name)` 的 slot 來源是硬編碼的 `BybitEnvironment::secret_slot()`（"demo" 或 "live"），name 來源是硬編碼字符串（"api_key", "api_secret", "bybit_endpoint"）。無用戶可控的路徑分量。

---

### SEC-C04 [INFO] Python settings_routes slot 驗證 — 已防護

**文件**: `app/settings_routes.py:384`

```python
if slot not in ALLOWED_SLOTS:
    raise HTTPException(status_code=400, ...)
```

ALLOWED_SLOTS 為硬編碼白名單 `{"demo", "live_demo", "live"}`，path traversal 不可能。

---

## 4. 認證與授權 / Authentication & Authorization

### SEC-D01 [CRITICAL] IPC HMAC 認證為可選（非強制）

**文件**: `rust/openclaw_engine/src/ipc_server/mod.rs:497`

```rust
if let Ok(secret) = std::env::var("OPENCLAW_IPC_SECRET") {
    // ... HMAC auth required
}
// If env var is absent → auth is SKIPPED (backward compatible)
```

**描述**: IPC HMAC-SHA256 認證僅在 `OPENCLAW_IPC_SECRET` 環境變量設置時啟用。如果未設置，任何能連接 Unix domain socket 的進程均可直接發送 IPC 命令，包括：
- `close_all_positions`（全倉平倉）
- `reset_paper_state`（重置餘額）
- `update_risk_config`（修改風控參數）
- `force_governor_tier_tighter` / `_looser`（覆蓋風控等級）
- `set_system_mode`（切換系統模式）

**緩解因素**:
1. Unix domain socket 受文件系統權限保護（通常只有同用戶進程可連接）
2. 代碼註釋明確標記為 "backward-compatible: dev/test mode"
3. G-3 任務已完成 IPC 認證實現

**風險**: 生產部署時如果忘記設置 `OPENCLAW_IPC_SECRET`，所有 IPC 命令均無需認證。Live 模式下這是嚴重風險 — 本機任何同用戶進程可操控交易引擎。

**建議**: 
1. Live 模式下強制要求 `OPENCLAW_IPC_SECRET`（啟動時檢查，缺失則 panic 或拒絕啟動 Live pipeline）
2. 文檔明確標記為 Live 前置條件

**OWASP**: A07:2021 Identification and Authentication Failures

---

### SEC-D02 [HIGH] Auth cookie 的 Secure 標誌為 False

**文件**: `app/legacy_routes.py:322`

```python
resp.set_cookie(
    key="oc_auth_token",
    value=settings.api_token,
    httponly=True,
    samesite="strict",
    secure=False,  # TODO: Set True when HTTPS is enabled
)
```

**描述**: `secure=False` 意味著 cookie 會在 HTTP 明文連接中傳輸。如果系統通過非 HTTPS 的網絡訪問（包括 Tailscale 內的 HTTP），auth token 可能被中間人截取。

**緩解因素**:
1. 系統目前通過 Tailscale（WireGuard 加密隧道）訪問
2. SameSite=Strict 防止 CSRF
3. 代碼有 TODO 標記

**建議**: 當 HTTPS 啟用後立即改為 `secure=True`。或改為根據環境變量動態設置。

**OWASP**: A02:2021 Cryptographic Failures

---

### SEC-D03 [HIGH] GUI 靜態文件無認證保護

**文件**: `app/main_legacy.py` (StaticFiles mount 區域)

**描述**: `/static/` 路徑下的 HTML/JS 文件作為靜態資源掛載，不受 auth middleware 保護。雖然 `common.js` 中的 `ocAuthCheck()` 在頁面加載時做了 async auth 檢查（fetch `/api/v1/auth/check`），但：
1. 靜態 HTML/JS 本身可被未認證用戶下載和閱讀
2. Auth check 是客戶端 JavaScript 實施的，可被繞過
3. 所有 API 端點均需 auth，所以數據本身是安全的

**緩解因素**:
1. 靜態文件不含敏感數據（密鑰、餘額等需通過 API 獲取）
2. 所有寫操作端點有 `Depends(_get_auth_actor)` / `Depends(_require_operator_auth)` 保護
3. Tailscale 限制了網絡可達性

**風險**: 攻擊者可查看 GUI 結構和 JavaScript 邏輯（信息洩露），但無法獲取或修改數據。

**OWASP**: A01:2021 Broken Access Control

**評級**: HIGH（信息洩露 + 攻擊面暴露）

---

### SEC-D04 [INFO] 登錄 brute-force 防護 — 已實施

**文件**: `app/legacy_routes.py:221-303`

**結論**: 
- Rate limit: 5/minute per IP（`@limiter.limit("5/minute")`）
- IP lockout: 5 次失敗 / 15 分鐘窗口 → 429 lockout
- Constant-time comparison: `hmac.compare_digest()` 用於用戶名和密碼
- OOM 防護: `_LOGIN_FAIL_MAX_IPS` 容量上限 + FIFO 淘汰

---

### SEC-D05 [INFO] Execution authority 生命週期 — 設計正確

**結論**: Live session start 時自動授予 execution_authority，stop 時撤銷。SM-1 治理授權完整生命週期（DRAFT→PENDING→ACTIVE→REVOKED）。Live 縮倉監控（5 分鐘輪詢，回撤 ≥15% 自動撤銷）。`_EXECUTION_AUTHORITY_OVERRIDE` 為 in-memory gate，重啟清空（fail-closed）。

---

## 5. XSS 分析 / Cross-Site Scripting Analysis

### SEC-E01 [HIGH] ocEsc() 缺少單引號轉義

**文件**: `app/static/common.js:369-372`

```javascript
function ocEsc(s) {
  if (s == null) return '';
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
```

**描述**: 缺少 `'` → `&#x27;` 的轉義。當 ocEsc 結果用於單引號包裹的 HTML 屬性時（如 `onclick="fn('${ocEsc(val)}')"` — 見 SEC-B03），攻擊者可注入 JavaScript。

**影響範圍**: 搜索所有 `ocEsc` 用於單引號上下文的位置：
- `tab-live.html:736`: `onclick="closeLivePosition('${sym}')"` -- sym 來自 Bybit API
- 其他位置主要用在 `${}` 模板字面量中的 innerHTML，用雙引號包裹或作為文本內容，風險較低

**建議**: 
```javascript
function ocEsc(s) {
  if (s == null) return '';
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#x27;');
}
```

**OWASP**: A03:2021 Injection (XSS)

---

### SEC-E02 [MEDIUM] tab-system.html 確認對話框使用 innerHTML 填充硬編碼 HTML

**文件**: `app/static/tab-system.html:392-393,442-443`

```javascript
$('confirm-title').innerHTML = msg.title;
$('confirm-body').innerHTML = msg.body;
```

**描述**: `CONFIRM_MSGS` 和 `MODE_CONFIRM` 的 title/body 來自 JavaScript 常量對象（硬編碼的 HTML 片段）。目前無用戶輸入注入點。

**風險**: LOW（當前安全，但如果未來重構將用戶數據加入確認消息，可能引入 XSS）

---

### SEC-E03 [MEDIUM] tab-phase4.html 卡片加載模式 — 自源 HTML 注入

**文件**: `app/static/tab-phase4.html:174-203`

```javascript
fetch('/static/cards/teacher_card.html', { credentials: 'same-origin' })
  .then(r => r.ok ? r.text() : '')
  .then(html => {
    tmp.innerHTML = html;
    // ... execute inline scripts
    var ns = document.createElement('script');
    ns.textContent = s.textContent;
    document.body.appendChild(ns);
  });
```

**描述**: 從同源 `/static/cards/` 加載 HTML 片段，設置 innerHTML 並執行內嵌 script。

**緩解因素**:
1. Same-origin fetch（CORS 限制）
2. 加載的 card HTML 是開發者控制的靜態文件
3. CSP `script-src 'self' 'unsafe-inline'` 允許此模式

**風險**: LOW（self-origin 模式本身安全，但 `'unsafe-inline'` CSP 降低了整體防禦深度）

---

### SEC-E04 [INFO] 其他 innerHTML 使用 — 已正確轉義

**文件**: 多個 tab HTML 文件

**結論**: 掃描所有 innerHTML 賦值點：
- `tab-live.html`: 所有 Bybit 數據欄位均通過 `ocEsc()` 轉義（symbol, side, qty, price, orderId 等）
- `tab-ai.html`: strategy 名稱使用 `ocEsc(k)`, Kelly tier 使用 `ocEsc(s.kelly_tier)`
- `linucb_card.html`: regime 使用 `ocEsc(reg)`
- `news_card.html`: 明確聲明 "never innerHTML" 用於用戶內容，使用 `textContent`
- `teacher_card.html`: 使用 `textContent` 用於 directive 欄位（XSS 防護註釋）
- `dl3_card.html`: 使用 `textContent` 用於 model/symbol
- `tab-settings.html`: key_hint 使用 `ocEsc(hint)`，錯誤消息使用 `ocEsc(errMsg)`

**例外**: `ocExplain()` 函數輸出硬編碼的 HTML 解釋文本（非用戶數據），用於 `innerHTML` 是安全的。

---

## 6. 其他 OWASP Top 10 發現 / Other OWASP Findings

### SEC-F01 [HIGH] CSP 使用 'unsafe-inline' 削弱防護

**文件**: `app/main_legacy.py:335-343`

```python
"script-src 'self' 'unsafe-inline' https://unpkg.com; "
"style-src 'self' 'unsafe-inline'; "
```

**描述**: `'unsafe-inline'` 允許所有 inline script/style 執行，使 CSP 對 XSS 的防護大幅削弱。這是因為 GUI 大量使用 inline `<script>` 和 `<style>` 標籤。

**緩解因素**: CSP 仍然阻止了來自未白名單域的腳本加載，`connect-src 'self'` 限制了數據外洩管道。

**建議**: 長期遷移到 nonce-based CSP（`script-src 'nonce-xxx'`），逐步消除 inline scripts。

**OWASP**: A05:2021 Security Misconfiguration

---

### SEC-F02 [MEDIUM] CORS allow_methods 允許 POST 到所有端點

**文件**: `app/main_legacy.py:290-296`

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)
```

**描述**: 當 `OPENCLAW_CORS_ORIGINS` 配置了外部域時，該域的 JavaScript 可以向所有 POST 端點發送帶 cookie 的跨域請求。

**緩解因素**:
1. 默認 `_cors_origin_list` 為空（同源訪問）
2. SameSite=Strict cookie 阻止跨站 cookie 附加
3. 通配符 `*` 已被啟動時強制移除

**風險**: 低（需要 operator 主動配置外部 origins，且 SameSite=Strict 提供額外防線）

---

### SEC-F03 [MEDIUM] 缺少 API 端點級別的 CSRF 保護

**描述**: 除了 SameSite=Strict cookie（瀏覽器層面防護）外，API 端點沒有獨立的 CSRF token 驗證。某些老式瀏覽器或特定攻擊向量可能繞過 SameSite。

**緩解因素**:
1. SameSite=Strict 是現代瀏覽器的有效 CSRF 防護
2. 系統通過 Tailscale 訪問，攻擊面極小
3. 所有寫操作需 auth（`Depends(_get_auth_actor)`）

**建議**: 考慮為高危操作（live session start、全倉平倉、execution authority grant/revoke）加入 CSRF token 或二次確認機制。

**OWASP**: A01:2021 Broken Access Control

---

### SEC-F04 [LOW] Python logger 可能記錄敏感上下文

**文件**: `app/settings_routes.py:419,429`

```python
logger.warning("API key conflict: slot '%s' key matches '%s' slot (actor: %s)", ...)
logger.info("Validating Bybit API key for slot '%s' (actor: %s)", ...)
```

**描述**: 日誌記錄了 slot 名稱和 actor ID，但 **未記錄明文 key/secret**。`_mask_key()` 僅顯示最後 4 字符。驗證結果的錯誤消息 `err_msg` 來自 Bybit API 回應（可能包含部分 key hint）。

**結論**: 當前安全，但建議對 `err_msg` 做截斷/過濾以防未來 Bybit API 回應格式變更洩漏敏感信息。

---

### SEC-F05 [LOW] Unix socket 文件權限未設置

**文件**: `rust/openclaw_engine/src/ipc_server/mod.rs:400-440`（`start_server` 函數）

**描述**: `UnixListener::bind(socket_path)` 創建的 socket 文件繼承 umask 權限，未顯式設置為 0700。同用戶的其他進程可連接。

**緩解因素**: Unix domain socket 已受文件系統所有者保護；結合 HMAC auth（若啟用）可充分防護。

**建議**: 啟動後立即 `chmod(socket_path, 0o600)` 限制 socket 訪問。

---

## 7. 安全控制檢查清單 / Security Controls Checklist

| 控制項 | 狀態 | 備註 |
|--------|------|------|
| SQL 注入防護（Rust） | ✅ 完備 | 全部 sqlx 參數化綁定 |
| SQL 注入防護（Python） | ⚠️ parquet_etl | 離線工具，風險低 |
| XSS 防護 — ocEsc() | ⚠️ 缺單引號 | SEC-E01 |
| XSS 防護 — innerHTML 覆蓋 | ✅ 大部分完備 | news_card/teacher/dl3 使用 textContent |
| IPC HMAC 認證 | ⚠️ 非強制 | SEC-D01 |
| GUI 登錄認證 | ✅ 完備 | HttpOnly cookie + brute-force 防護 |
| API 認證中間件 | ✅ 完備 | Depends() 注入 |
| CORS 配置 | ✅ 安全 | 禁止 * + credentials |
| CSP | ⚠️ unsafe-inline | SEC-F01 |
| Rate limiting | ✅ 完備 | 全局 120/min + 登錄 5/min |
| Secret 文件保護 | ✅ 完備 | chmod 600 + .gitignore |
| 密鑰日誌洩漏 | ✅ 未發現 | 無 credential 記錄 |
| Cookie 安全標誌 | ⚠️ secure=False | SEC-D02 |
| CSRF 防護 | ✅ SameSite=Strict | 可加強 |
| 安全響應頭 | ✅ 完備 | X-Frame, X-XSS, nosniff, CSP |
| 常數時間比較 | ✅ 完備 | HMAC verify_slice / compare_digest |

---

## 8. 建議優先修復順序 / Recommended Fix Priority

1. **SEC-D01** [CRITICAL] — Live 模式強制 IPC secret（啟動時 guard）
2. **SEC-E01** [HIGH] — ocEsc() 追加單引號轉義（1 行修改）
3. **SEC-D02** [HIGH] — Cookie secure 標誌動態化（根據 HTTPS 環境）
4. **SEC-D03** [HIGH] — 靜態文件目錄加 auth middleware（或評估接受風險）
5. **SEC-F01** [HIGH] — CSP nonce 遷移規劃（長期）
6. **SEC-B03** [MEDIUM] — tab-live.html onclick 改用 addEventListener
7. **SEC-B02** [MEDIUM] — parquet_etl 參數化
8. **SEC-F03** [MEDIUM] — 高危操作 CSRF token
9. **SEC-A01** [LOW] — fast_track 死碼修復（PNL-4）
10. **SEC-F05** [LOW] — Unix socket chmod

---

*審計完成 / Audit complete. E3 Security Engineer, 2026-04-12.*
