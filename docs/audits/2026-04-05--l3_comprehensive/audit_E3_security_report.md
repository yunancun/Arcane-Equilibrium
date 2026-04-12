# E3 安全審計報告 — OpenClaw 交易系統
# E3 Security Audit Report — OpenClaw Trading System

**審計日期 / Audit Date:** 2026-04-05
**審計範圍 / Scope:** Rust 引擎 (openclaw_engine + openclaw_core) + Python Control API + IPC + GUI + 配置/密鑰管理
**審計員 / Auditor:** E3 Security Auditor (Claude)

---

## 審計摘要 / Executive Summary

| 級別 | 數量 | 說明 |
|------|------|------|
| P0 Critical | 2 | 交易所模式 Cost Gate ��失、IPC 無認證 |
| P1 Important | 5 | 風控參數無邊界驗證、Cookie secure=False、IPC socket 權限、H0Gate shadow 繞過、inline innerHTML XSS |
| P2 Minor | 5 | 硬編碼��證路徑、latency_us u32 截斷、Token 明文 JSON 返回、process_gates_only 代碼重複、OPENCLAW_ALLOW_MAINNET 環境變量保護不足 |

**整體評估：** 系統在 demo_only 模式下安全性良好。fail-closed 設計正確，GovernanceCore 預設 Frozen，SQL 使用參數化查詢，密鑰未洩漏到日誌��但若升級到 Exchange 模式，有 2 個 P0 問題必須先修復。

---

## 1. Gate Bypass — 門控繞過分析

### SEC-01 [P0 Critical] Exchange 模式 Cost Gate (Gate 3) 缺失

**文件：** `rust/openclaw_engine/src/intent_processor.rs` L396-L516

**問題：** `process_gates_only()` 函數（Exchange 模式使用）缺少 Gate 3 Cost Gate 檢查。而 `process()` 函數（Paper 模式）包含完整的 Gate 3。

**影響：** 在 Exchange 模式下，低信心（< 0.15）和低 EV（預期收益 < 往返手續���）的交易意圖可以繞過成本���控，直接提交到交易所，導致真金白銀的手續費損耗。

**對比：**
- `process()` (Paper): Gate 1 → 1.5 → 2 → 2.5 → 2.6 → **2.7** → **3** �� 4
- `process_gates_only()` (Exchange): Gate 1 → 1.5 → 2 → 2.5 → 2.6 → **2.7** → (缺失 Gate 3)

**攻擊場景：** 當 `trading_mode = Exchange` 時，任何 confidence >= 0 的策略信號都能通過門禁，即使 EV 為負。

**修復建議：** 在 `process_gates_only()` 的 Gate 2.7 ���後、返�� `approved` 之前，加入與 `process()` 完全相同的 Gate 3 邏輯。注意需要接收 `atr` 參數。

---

### SEC-02 [P1 Important] H0Gate shadow_mode 可被 IPC 遠程切換為「永放行」

**文件：** `rust/openclaw_engine/src/ipc_server.rs` L522, `rust/openclaw_core/src/h0_gate.rs` L209

**問題：** `set_shadow_mode(true)` 使 H0Gate 的 `check()` 永遠返回 `allowed=true`���L246-L248），即使所有 5 項子檢查都失敗。此功��可通過 IPC `update_risk_config` 命令遠程切換，且 IPC 無認證（見 SEC-03）。

**影響：** 攻擊者連接 IPC socket 後可設定 `h0_shadow_mode=true`，使 H0 門控完全失效。

**當前緩解：** H0Gate 預設 `shadow_mode=true`（觀察模式），這是設計意圖。但當 H0 日後切換為強制模式時，此路徑成為繞過向量。

**修復建議：** (1) IPC 加入認證（見 SEC-03）；(2) 考慮在 `set_shadow_mode` 中加入審計日誌。

---

### SEC-03 [P2 Info] 其他門控鏈完整性確認

以下門控鏈經審計確認**正確**：
- **GovernanceCore** 預設 `Frozen`（fail-closed），`is_authorized()` 在 `!enabled || Frozen` 時返回 false ✅
- **Guardian** 4 項檢查（方向衝突/同方向持倉/槓桿/回撤）邏輯正確 ✅
- **check_order_allowed** 5 項檢查（日損/槓桿/單倉/總曝險/相關曝險）邏輯正確 ✅
- **P1 Hard Cap** `kelly_qty.min(p1_max_qty)` 正確取最小值 ✅
- **Reducing orders bypass** 允許平倉繞過風控——符合「生存 > 利潤」原則 ✅
- **on_tick** 中 H0Gate 阻斷後只處理止損，不執行策略分派 ✅
- **FastTrack CloseAll** 在 CircuitBreaker 級別正確觸發全倉平倉 ✅

---

## 2. Injection Vulnerabilities — 注入漏洞

### SEC-04 [P2 Minor] SQL 注入 — 已安全

**結果：** 所有 Rust DB writer 使��� `sqlx::QueryBuilder::push_bind()` 參數化綁定，零字符串拼接 SQL。已檢查：
- `trading_writer.rs` — push_bind for all 4 tables ✅
- `market_writer.rs` — push_bind ✅
- `feature_writer.rs` — push_bind ✅
- `context_writer.rs` — push_bind ✅
- `quality_writer.rs` — push_bind ✅
- `experiment_ledger_pg.rs` — sqlx::query with $N placeholders ✅
- `drift_detector.rs` — sqlx::query with $N ✅

**無 SQL 注入風險。**

### SEC-05 [P1 Important] GUI innerHTML 使用——潛在 XSS

**文件：** `static/tab-strategy.html`, `static/tab-trading.html`, `static/tab-risk.html`

**問題：** 多處使用 `element.innerHTML = ...` 插入動態內容。若服務端返回的交易數據（如 symbol 名稱、策略名稱）包含惡意腳本，可觸發 XSS。

**攻擊場景：** 若 Bybit WS 推送的 symbol 名稱被污染（如 `<img onerror=...>`），`innerHTML` 會直接渲染。

**當前緩解：** (1) 數據來源為 Bybit API，攻擊者需先劫持交易所數據；(2) GUI 需先登入（HttpOnly cookie + SameSite=strict）。

**修復建議：** 將 `innerHTML` 替換為 `textContent`，或使用 DOM API 創建元素。對 `ocExplain()` 返回��內容做 HTML 轉義。

---

## 3. Secret/Key Leaks — 密鑰洩漏

### SEC-06 [P2 Minor] API Token 在 JSON Response 中明文返回

**文件：** `legacy_routes.py` L376

```python
resp = JSONResponse({"token": settings.api_token, "username": req.username})
```

**問題：** 登入成功後，API token 同時通過 HttpOnly cookie 和 JSON body 返回。JSON body 中的 token 可被瀏覽器擴展或調試工具讀取。

**修復建議：** 僅通過 HttpOnly cookie 設置 token，JSON body 只返回 `{"status": "ok", "username": ...}`。

### SEC-07 已確認安全的項目

- `.gitignore` 正確排除 `secrets/`, `*.env`, `secret_files/`, `environment_files/` ✅
- `settings/secret_files/bybit/` 目錄下只有 README.md，無實際密鑰文件 ✅
- API key/secret 從環境變量或文件讀取，未硬編碼到源碼 ✅
- `bybit_rest_client.rs` 簽名函數不輸出 secret 到日誌 ✅
- 搜索全 Rust 代碼，零處將 api_key/api_secret 寫入 tracing 日誌 ✅
- Token 文件權限設為 0o600，目錄設為 0o700 (`auth.py` L112-113) ✅

---

## 4. Authentication/Authorization — 認證與授權

### SEC-08 [P0 Critical] IPC Unix Socket 無認證/授權

**文件：** `rust/openclaw_engine/src/ipc_server.rs`

**問題：** IPC 服務器接受所有連接到 Unix socket 的客戶端，無任何認證機制。任何能訪問 `/tmp/openclaw/engine.sock` 的進程都可以：
1. 調用 `update_risk_config` 修改所有風控參數（止損/槓桿/回撤限制）
2. 調用 `close_all_positions` 強制平倉
3. 調用 `reset_paper_state` 重置餘額
4. 調用 `update_strategy_params` 修改策略參數
5. 調用 `set_strategy_active` 啟停策略
6. 讀���所有持倉、價��、統計數據

**攻擊場景：** 同一台機器上的任何用戶進程（包括被入侵的 Web 服務、惡意 cron job 等）都可以通��� socket 完全控制引擎。

**當前緩解：** (1) Socket 在 `/tmp/openclaw/` 下，受 Linux 默認 umask 限制；(2) 系統處於 demo_only 模式。

**修復建議：**
1. **P0（必做）：** 設置 socket 文件權限為 0o600（僅 owner 可讀寫）
2. **P1：** 加入共享 secret 認證（首次連接發送 token）
3. **P2：** 實現命令級權限（讀取 vs 寫入 vs 控制命令分級）

### SEC-09 [P2 Minor] `/api/v1/system/startup-status` 無認證

**文件：** `main.py` L411

**問題：** 此端點明確設計為無認證（"No auth required — read-only public metadata"）。

**當前緩解：** 只返回組件初始化狀態（pending/ready/failed），不含業務數據或憑證。

**風險：** 極低——信息洩漏有限，可能暴露系統架構信息。

### SEC-10 已確認安全的認證機制

- 所有 API 路由均使用 `Depends(current_actor)` 注入認證 ✅
- 登入使用 `hmac.compare_digest` 防時序攻擊 ✅
- IP 級別速率限制 5次/分鐘 + 15分鐘 lockout ✅
- lockout 字典有 2000 條上限，防 OOM ✅
- asyncio.Lock 保護 lockout 計數器，防並發竟態 ✅

---

## 5. Fail-Open vs Fail-Closed — 錯誤處理分析

### SEC-11 [P1 Important] Cost Gate ATR=0 ��� Fail-Open

**文件：** `rust/openclaw_engine/src/intent_processor.rs` L342

```rust
if atr > 0.0 {
    // ... EV check
}
// If ATR unavailable, the trade PASSES (fail-open)
```

**問題：** 當 ATR 不可用（atr=0）時，Cost Gate 跳過 EV 檢查，只保留 `MIN_CONFIDENCE` 硬地板。這是有意設計（"fail-open if ATR unavailable"），但在數據初始化階段（前 30 根 K 線）所有交易都繞過 Cost Gate。

**影響：** 啟動後約 30 分鐘內，系統可能執行 EV 為負的交易。

**當前緩解：** (1) MIN_CONFIDENCE=0.15 硬地板仍生效；(2) Guardian 和 P1 cap 仍生效。

**修復建議：** 考慮 ATR 不可用時 fail-closed（拒絕交易），或至少延長冷啟動期間的���略禁止窗口。

### SEC-12 已確認的 Fail-Closed 設計

- GovernanceCore 預設 `GovernanceMode::Frozen` ✅
- `is_authorized()` 在 disabled/frozen 時返回 false ✅
- H0Gate 硬阻斷時返回 `allowed=false`，只處理止損 ✅
- risk `check_order_allowed` 未知狀態 → reject ✅
- DB pool 不可用時靜默丟棄（不阻塞交易管線）✅
- Session halted → CircuitBreaker 級聯 ✅

---

## 6. Integer Overflow/Underflow — 數值安全

### SEC-13 [P2 Minor] latency_us u32 截斷

**文件：** `rust/openclaw_core/src/h0_gate.rs` L481

```rust
let latency_us = start.elapsed().as_micros() as u32;
```

**問題：** `as_micros()` 返回 u128，強轉 u32 在延遲超過 ~4.29 秒時靜默截斷。雖然 H0Gate SLA < 1ms 使此場��極不可能，但若系統嚴重卡頓，延遲統計會不準確。

**修復建議：** 使用 `u64` 或 `.min(u32::MAX as u128) as u32`。

### SEC-14 已確認安全的數值處理

- `saturating_sub` 用於時間差計算，防下溢 ✅
- `exchange_seq` ���用 `wrapping_add`，防溢出 ✅
- `daily_loss_pct` 對 balance <= 0 返回 0.0 ✅
- `compute_exposure_pct` 對 balance <= 0 返回 0.0 ✅
- `p1_risk_pct` 使用 `.clamp(0.001, 0.20)` 限制範圍 ✅
- `sanitize_f64` 用於所有 DB 寫入，防 NaN/Infinity ✅

---

## 7. Race Conditions — 競態條件

### SEC-15 已確��安全——單 Actor 模型

**結果：** `TickPipeline` 採用 sole-owner 單 Actor 模型（"Tick actor sole-owner: no locks [V3-PA-1]"）。所有狀態修改通過 mpsc channel 序列化到單一 tokio task。

確認的設計：
- `TickPipeline` 為 `&mut self`，無共享可變引用 ✅
- `GovernanceCore` 無內部鎖，由 tick actor 獨佔 ✅
- IPC 命令通過 `UnboundedSender<PaperSessionCommand>` 發送，在 event_consumer 中序列化處理 ✅
- ConfigManager 使用 `ArcSwap`（原子讀 ~5ns，寫時 clone）✅
- 唯一共享可變狀態 `bybit_balance` 和 `api_pnl` 使用 `Arc<RwLock>` 保護 ✅

**TOCTOU 風險：** `check_order_allowed` 和 `apply_fill` 之間無原子保證，但因單 Actor 模型保證順序執行，不存在 TOCTOU。

---

## 8. Execution Authority — 執行權限保護

### SEC-16 已確認安全——多重保護

**主網保護鏈：**
1. `OPENCLAW_ALLOW_MAINNET` 環境變量必須為 `"1"` 才允許主網連接 (`bybit_rest_client.rs` L325)
2. `TradingMode` 預設 `PaperOnly`，需修改 config 冷參數並重啟 ✅
3. `system_mode` 硬編碼 `"demo_only"` ✅
4. GovernanceCore 只有 `grant_paper_authorization`，無 `grant_live_authorization` ✅
5. Python 側 `execution_authority = "not_granted"` 硬狀態 ✅
6. Decision Lease 框架中多處 preflight check 驗證 `execution_authority == "not_granted"` ✅

### SEC-17 [P2 Minor] OPENCLAW_ALLOW_MAINNET 保護機制

**文件：** `rust/openclaw_engine/src/bybit_rest_client.rs` L325

**問題：** 主網保護依賴��一環境變量 `OPENCLAW_ALLOW_MAINNET=1`。任何能設置環境變量的進程（包括通過 IPC 被入侵後的間接修改）都能繞過此保護。

**當前緩解：** (1) 這是冷參數，需重��生效；(2) Rust 進程的環境變量在啟動後不可被外部修改。

**修復建議：** 未來增��第二因素（如簽名文件���人工確認 prompt）。

---

## 9. IPC Security — IPC 安全

### SEC-18 [P1 Important] IPC 風控參數無邊界驗證

**文件：** `rust/openclaw_engine/src/event_consumer.rs` L706-L756

**問題：** 通過 IPC `update_risk_config` 設定的參數直接透傳到 pipeline，以下 setter 無任何邊界檢查：
- `set_hard_stop_pct(v)` — 可設為 0 或 100+，禁用止損或立即觸發
- `set_trailing_stop_pct(v)` — 可設為負數
- `set_time_stop_hours(v)` — 可設為 0（立即超時平倉）
- `set_atr_multiplier(v)` — 可設為負數
- `set_take_profit_pct(v)` — 可設為 0（��即止盈）
- `gc.max_leverage = v` — 可設為 0（阻止所有交易）或 999（無限槓桿）
- `gc.max_drawdown_pct = v` — 可設為 0（立即觸發 CircuitBreaker）

**對比：** `set_p1_risk_pct` 正確使用了 `.clamp(0.001, 0.20)` 限制範圍。

**攻擊場景：** 通過 IPC socket 將 `hard_stop_pct` 設為 0.001，觸發所有持倉立即止損平倉。

**修復建議：** 在所有 setter 中加入 `.clamp()` 邊界限制：
```rust
pub fn set_hard_stop_pct(&mut self, pct: f64) {
    self.stop_config.hard_stop_pct = pct.clamp(0.5, 50.0);
}
```

### SEC-19 IPC Buffer/Parsing — 已安全

- 使用 `BufReader::lines()` 行讀取，防緩衝區溢出 ✅
- `serde_json::from_str` 對畸形 JSON 返回錯誤，不 panic ✅
- 未知方法返回 `ERR_METHOD_NOT_FOUND` ✅
- `reset_paper_state` 的 `new_balance` 使用 `as_f64()` 安全轉換 ✅

---

## 10. Dependency Vulnerabilities — 依賴安全

### SEC-20 Rust 依賴評估

| 依賴 | 版本 | 狀態 |
|------|------|------|
| tokio | 1.x | 活躍維護，無已知 CVE ✅ |
| reqwest | 0.12 | 活躍維護 ✅ |
| sqlx | 0.8 | 活躍維護 ✅ |
| tokio-tungstenite | 0.26 | 活躍維護 ✅ |
| rustls | 0.23 | 使用 ring backend ✅ |
| hmac + sha2 | 0.12 + 0.10 | RustCrypto 系列，安全 ✅ |
| chrono | 0.4 | 已知：localtime_r 線程安全問題（CVE-2020-26235），但 OpenClaw 使用 UTC ✅ |
| pyo3 | 0.24 | 活躍維護 ✅ |
| ndarray | 0.16 | 活躍維護 ✅ |

**建議：** 定期運行 `cargo audit` 檢查已知 CVE。

### SEC-21 [P1 Important] Cookie secure=False

**文件：** `legacy_routes.py` L382

```python
secure=False,  # TODO: 启用 HTTPS 后改为 True
```

**問題：** `oc_auth_token` cookie 未設置 `secure=True`，在 HTTP 連接�� token 以明文傳輸，可被中間人截獲。

**當前緩解：** (1) Tailscale mesh 內通信加密；(2) 代碼中已有 TODO 標記。

**修復建議：** 啟用 HTTPS 後立即設置 `secure=True`。���增加配置項根據環境自動切換。

---

## 附錄：修復優先級

### 必須在 Exchange 模式啟用前修復（P0）

1. **SEC-01** — `process_gates_only` 加入 Gate 3 Cost Gate
2. **SEC-08** — IPC socket 設置 0o600 權限 + 加入認證

### 應盡快修復（P1）

3. **SEC-18** — IPC 風控參數加入邊界驗證（`.clamp()`）
4. **SEC-21** — HTTPS 後啟用 secure cookie
5. **SEC-02** ��� H0Gate shadow mode 切換加入審計日誌
6. **SEC-05** — GUI innerHTML 替換為 textContent
7. **SEC-11** — 評估 Cost Gate ATR=0 改為 fail-closed

### 低優先級改善（P2）

8. **SEC-13** — latency_us 使用 u64
9. **SEC-06** — 登入 JSON body 不返回 token
10. **SEC-09** — startup-status 端點考���加入基本認證
11. **SEC-17** — 主網保護增加第二因素

---

*報告完成。E3 Security Auditor 簽署。*
