# E3 Memory — 工作記憶

## 項目上下文（2026-04-24）

- 當前 Phase：Live_Ready ⚠️ (demo 階段，0 真實 live 流量)
- engine PID 884467, binary 2026-04-24 02:06, lib 1980/0 failed
- Python pytest ~2996 passed
- 系統模式：demo + live_demo（歷史 43k engine_mode="live" 實為 LiveDemo）
- 安全評級：**A-（0 CRITICAL / 0 HIGH / 5 MEDIUM / 4 LOW / 5 INFO）**

## 工作記憶

### 2026-04-24 全程序安全審計關鍵發現

1. **所有 2026-04-01 findings 大部分已修復**：CORS wildcard + 安全響應頭 + HttpOnly cookie + 登入 IP 鎖定全綠
2. **LIVE-GATE-BINDING-1（2026-04-18）落地** — 5 項 Live 門控全部經 Rust 簽名契約綁定
3. **LIVE-GUARD-1（2026-04-16）落地** — OPENCLAW_ALLOW_MAINNET + env-var 憑證封閉
4. **FIX-10 雙保險** — Live 啟動若 OPENCLAW_IPC_SECRET 未設 → Rust panic
5. **殘留 5 MEDIUM + 4 LOW**：
   - MEDIUM-A：11 處 `detail=f"...{e}"` 錯誤洩漏（ml/paper/strategy_write routes）
   - MEDIUM-B：claude_teacher `find_denylisted_field` 單層掃描（nested bypass 理論上可能）
   - MEDIUM-C：`app.js:530-608` renderProductFamilyEditor innerHTML 無 ocEsc
   - MEDIUM-D：Layer 2 `context` 無 prompt injection 清洗
   - MEDIUM-E：IPC 認證在 paper/demo 未設 OPENCLAW_IPC_SECRET 時 fail-open
   - LOW-A~D：CSP unsafe-inline / 503 auth msg / x-forwarded-* 未 strip / EA-PERSIST 無 HMAC
6. **五項 Live 門控繞過測試**：全部 **通過** —
   - Python live_reserved ✅
   - Operator 角色 auth ✅
   - OPENCLAW_ALLOW_MAINNET=1 ✅（5 Rust tests）
   - secret slot api_key+secret ✅（asyncio.Lock + compare_digest + chmod 600）
   - authorization.json HMAC+TTL+env_allowed ✅（13 Rust tests + 5min re-verify）

### 架構安全觀察（保留自 2026-04-01，增量）

- GovernanceHub fail-closed 設計一流，經多輪驗證
- H0 Gate <1ms SLA 確定性門控
- 所有新路由遵循統一認證模式
- 原則 7 隔離嚴格執行
- **新增：Python↔Rust HMAC 簽名契約（LIVE-GATE-BINDING-1）= 跨進程信任邊界最佳實踐**
- **新增：claude_teacher 硬邊界 denylist + pause_all veto + unknown scope reject 三重防護**

## 報告索引

| 日期 | 任務 | 文件位置 |
|------|------|---------|
| 2026-04-01 | 全程序安全審計（對比 March 31） | `docs/CCAgentWorkSpace/E3/workspace/reports/2026-04-01--security_audit.md` |
| 2026-04-24 | 全程序安全審計（對比 April 01；5 gates 逐一驗證） | `docs/CCAgentWorkSpace/E3/workspace/reports/2026-04-24--full_chain_security_audit.md` |

### 2026-05-02 P0-DATA-INDICATOR-SWEEP（5 strategy adversarial leak audit, E3 副審）

- **Verdict**：5/5 PASS（無 leak），與 QC 主審獨立 cross-check 預期收斂
- **核心發現**：strategy → IndicatorSnapshot 單向依賴；strategy 0 處直接讀 KlineManager
- KlineBuffer 只存 `is_closed=true` bar，`current_bar` 物理隔離；`donchian_prior` 額外退一格 → 雙保險
- bb_breakout FIX-26-DEADLOCK-1 修復 (mod.rs:417-423) 確認落地，semantic 正確
- 所有 strategy 用 `ctx.timestamp_ms`，0 處 `Utc::now()` / 牆鐘洩漏
- 5 策略 net negative 主因 **非 leak**（最便宜的解釋不成立），edge 缺陷在策略邏輯/cost/maker fill rate
- **2 LOW finding**：
  1. test fixtures 用 `Box::leak(IndicatorSnapshot)` 跳過 KlineManager streaming → 策略邏輯有 coverage、streaming 整合無 coverage
  2. `feature_version` hardcoded "v1.0"（pipeline_ctor.rs:67）→ indicator code 改不會自動 bump → MLDE training 數據版本污染風險
- Mac vs Linux byte-equality：default rustc (no rustflags) → IEEE-754 reproducible likely OK
