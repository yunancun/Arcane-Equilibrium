# BB — Bybit API 完整 TODO 提案
## 2026-04-24 全面盤點 + 歷史報告對比

**審計員**：BB (Bybit API 兼容性審計師)  
**日期**：2026-04-24  
**資源**：memory.md + profile.md + 2 份 2026-04-24 審計 + L3 audit 2026-04-05 + 字典手冊 + 當前 TODO.md  
**方法**：靜態審計 + 歷史對比 + 現狀驗證

---

## A. 歷史 BB Findings 全盤清算

### A.1 2026-04-05 L3 Comprehensive Audit（PyO3 時代）

**背景**：PyO3 時期 39 個橋接方法審計。現已 DEDUP-PY-RUST Phase 2（2026-04-23）完成，PyO3 removed。

**結論**：（過期，記錄用）
- REST 47 endpoints ✅ 46 正確 / 1 警告
- WS 主題 7 類 ✅ 4 活躍 / 3 已移除（liquidation/price-limit/adl-notice）
- PyO3 39 方法 ✅ 全映射正確
- 認證簽名 ✅ HMAC-SHA256 正確
- Rate limit 6 分組 ✅ 完整
- retCode 12 分類 ✅ 完備

### A.2 2026-04-04 Infrastructure Audit（初次系統審計）

**修復項**：
- 5 個過期路徑修復（set-trading-stop → trading-stop、quick-repayment → repay 等）
- 3 個 UTA migration（spot-margin-trade → spot-margin-uta）
- 3 個 deprecated endpoint 移除（switch_isolated、set_tpsl_mode、set_risk_limit）
- 2 個 P0 endpoint 補充（ADL Alert、Insurance Pool）

**結論**：Core 62 REST + 5 WS private + 4 WS public 完整；rate limit 6 分組；retCode 12 分類完備

### A.3 2026-04-24 BB TODO Audit 發現（本次）

**Critical**：0 項 ✅（核心路徑無 bug）

**High**：1 項
- **H-1 字典 `confirm-mmr` 路徑過期**：字典寫 `/v5/position/confirm-mmr`，實機 `/v5/position/confirm-pending-mmr`（代碼已於 FIX-56 修）

**Medium**：3 項
- **M-1 ws_client "handler not found" 無強制重連**：parser 只 debug!，未觸發 reconnect（容錯弱）
- **M-2 bybit_public_connectivity_check.py 硬編碼 mainnet**：無法跨環驗證
- **M-3 bybit_private_ws_smoke_test.py 舊設計**：legacy `read_only` slot + 硬編碼 mainnet

**Low**：5 項
- **L-1 字典 `get_open_interest` 參數名稱**：寫 `interval`，實機 `intervalTime`
- **L-2 字典 `account-ratio` period 值域**：列 `1d`，實機僅 `5min/15min/30min/1h/4h/4d`
- **L-3 字典缺 `/v5/user/query-api`**：Python key validation 用，未記
- **L-4 字典缺 Private WS Status Writer**：Rust takeover 後合約未更新
- **L-5 字典缺 runtime WS topic 調整**：WsTopicChange 機制未記

### A.4 2026-04-24 Compatibility Audit（文檔對比）

**字典 drift 完整清單**：
| 項 | 位置 | 誤述/缺失 | 代碼 SSOT | 優先級 |
|---|---|---|---|---|
| 1 | §1.4 / §4.3 | confirm-mmr（缺 pending-） | confirm-pending-mmr | **H** |
| 2 | §1.1 | interval（應 intervalTime） | intervalTime | L |
| 3 | §1.1 | period 列 1d（無 4d） | 5min-4d（無 1d） | L |
| 4 | §全 | 缺 query-api（Python） | settings_routes.py:100 | L |
| 5 | §2 | 缺 Status Writer | bybit_private_ws_status_writer.rs | L |
| 6 | §1-2 | ticker 字段擴充未記 | +fundingRate/indexPrice/openInterest | L |
| 7 | §1.9 | Rust ensure_symbol 邏輯缺 | negative cache + singleflight + pagination | L |

---

## B. 未入當前 TODO 的 Bybit API 活躍項

### B.1 Medium 優先（代碼修改）

**M-1 ws_client "handler not found" 強制重連**
- 位置：`rust/openclaw_engine/src/ws_client.rs:362-366`
- 現狀：`debug!` only，無 reconnect
- 建議：
  ```rust
  if let Some(msg) = parsed.get("ret_msg").and_then(|v| v.as_str()) {
      if msg.contains("handler not found") || msg.contains("topic does not exist") {
          error!(topic = ?parsed.get("args"), "⚠ Bybit handler not found — reconnecting");
          return false; // break + reconnect
      }
  }
  ```
- 工時：1-2h
- 影響：預防未來新 broken topic 毒化整個 WS 連接

**M-2 bybit_public_connectivity_check.py 去硬編碼**
- 位置：`program_code/exchange_connectors/bybit_connector/io_and_persistence/bybit_public_connectivity_check.py:8`
- 現狀：`BASE_URL = "https://api.bybit.com"` 硬寫
- 建議：環境變數 `BYBIT_PUBLIC_BASE_URL` + fallback（或改呼 `bybit_rest_client.py` helper）
- 工時：1h
- 影響：跨環驗證 + 跨平台相容性（CLAUDE.md §七.★★）

**M-3 bybit_private_ws_smoke_test.py legacy slot 清理**
- 位置：`program_code/exchange_connectors/bybit_connector/io_and_persistence/bybit_private_ws_smoke_test.py:14-15` + v2
- 現狀：`read_only` slot + hardcoded `stream.bybit.com/v5/private`
- 建議：(a) 評估刪除（Rust bybit_private_ws_status_writer 已取代觀察價值），或 (b) 改用 `demo`/`live` slot + env var
- 工時：1-2h
- 影響：reduce 維護面積 + 環境感知

### B.2 Low 優先（字典 + 文檔更新）

**H-1 字典 confirm-mmr → confirm-pending-mmr（High 優先）**
- 位置：`docs/references/2026-04-04--bybit_api_reference.md` §1.4 + §4.3
- 修改：路徑 `/v5/position/confirm-mmr` → `/v5/position/confirm-pending-mmr`
- 工時：0.5h
- 影響：prevent reader rewrite from using old path

**L-1/L-2 字典參數對齊**
- `get_open_interest`：`interval` → `intervalTime`
- `get_long_short_ratio`：period 移除 `"1d"` 加 `"4d"`
- 工時：1h

**L-3/L-4/L-5 字典補錄**
- `/v5/user/query-api` 新章節（Python-only key validation）
- Private WS Status Writer 新子章（Rust takeover）
- WS runtime topic 調整（WsTopicChange）
- ticker 欄位擴充（fundingRate/indexPrice/openInterest）
- 工時：2-3h

---

## C. BB 完整 TODO 提案（20+ 條）

### 分組方案

**Tier 1（前 2 週）**：H-1 + M-1/M-2/M-3 + L-1/L-2（代碼 + 字典修改）

**Tier 2（2-4 週）**：L-3/L-4/L-5（文檔 SSOT 標記）+ 補充 healthcheck

**Tier 3（持續）**：每新增 endpoint 或 WS topic 同步更新字典

### 提案列表

#### T1. High Priority

| ID | 項目 | 位置 | 類型 | 工時 | 阻塞 | 負責 |
|---|---|---|---|---|---|---|
| **BB-H-1** | 字典 confirm-mmr → confirm-pending-mmr 修正 | docs/references/2026-04-04--bybit_api_reference.md §1.4+§4.3 | 文檔 | 0.5h | — | TW |
| **BB-M-1** | ws_client "handler not found" 強制重連邏輯 | rust/openclaw_engine/src/ws_client.rs:362-366 | Rust | 1-2h | — | E1 / E2 |
| **BB-M-2** | bybit_public_connectivity_check.py URL 環境變數化 | program_code/.../io_and_persistence/bybit_public_connectivity_check.py | Python | 1h | — | E1 / E2 |
| **BB-M-3** | bybit_private_ws_smoke_test.py 環境感知整合或刪除 | program_code/.../io_and_persistence/bybit_private_ws_smoke_test.py + v2 | Python | 1-2h | — | PM 決策 + E1 / E2 |

#### T2. Low Priority

| ID | 項目 | 位置 | 類型 | 工時 | 負責 |
|---|---|---|---|---|---|
| **BB-L-1** | 字典 get_open_interest interval → intervalTime | docs/references/2026-04-04--bybit_api_reference.md §1.1 | 文檔 | 0.5h | TW |
| **BB-L-2** | 字典 account-ratio period 值域正確 | docs/references/2026-04-04--bybit_api_reference.md §1.1 | 文檔 | 0.5h | TW |
| **BB-L-3** | 字典補錄 /v5/user/query-api（Python key validation） | docs/references/2026-04-04--bybit_api_reference.md §1（新章節） | 文檔 | 1h | TW |
| **BB-L-4** | 字典補錄 Private WS Status Writer + Rust takeover | docs/references/2026-04-04--bybit_api_reference.md §2（新 subsection） | 文檔 | 1h | TW |
| **BB-L-5** | 字典補錄 WS runtime topic 調整（WsTopicChange） | docs/references/2026-04-04--bybit_api_reference.md §2（新 subsection） | 文檔 | 0.5h | TW |
| **BB-L-6** | 字典擴充 ticker 欄位（funding/index/OI） | docs/references/2026-04-04--bybit_api_reference.md §2.1 ticker | 文檔 | 0.5h | TW |
| **BB-L-7** | 字典擴充 Python drop-in 與 Rust contract 對齊說明 | docs/references/2026-04-04--bybit_api_reference.md §新章 | 文檔 | 1h | TW |

#### T3. Observability / Healthcheck

| ID | 項目 | 位置 | 類型 | 工時 | 前置 | 負責 |
|---|---|---|---|---|---|---|
| **BB-OBS-1** | add `passive_wait_healthcheck.py [14]` Bybit API freshness check | helper_scripts/db/passive_wait_healthcheck.py | Python | 1h | — | E1 / QA |
| **BB-OBS-2** | CI 化 `bybit_rest_client.rs::RateLimitGroup::from_path` 回歸測試 | rust/openclaw_engine/src/tests/ | Rust | 1-2h | — | E4 / QA |
| **BB-OBS-3** | WS parser 對 broken topic 監控告警（logging 強化） | rust/openclaw_engine/src/ws_client.rs | Rust | 0.5h | — | E1 |

#### T4. Future / Advisory

| ID | 項目 | 位置 | 類型 | 工時 | 優先級 | 備註 |
|---|---|---|---|---|---|---|
| **BB-FUT-1** | 自動生成字典 endpoint 清單（from Rust docstring） | helper_scripts/ + docs/references/ | 工具 | 2-3d | P3 | 長期 drift 預防 |
| **BB-FUT-2** | Bybit API changelog 監控 + 版本管理 | docs/CHANGELOG.md + CI | process | 1d | P3 | 新 endpoint 自動告警 |
| **BB-FUT-3** | Rate limit per-group 儀表板（Grafana） | monitoring/ | 觀測 | 2d | P3 | 即時監控 |
| **BB-FUT-4** | retCode 分類器 CI 與官方文檔同步驗證 | rust/openclaw_engine/src/tests/bybit_error_catalog.rs | 回歸 | 1-2d | P3 | 新 retCode 自動檢出 |
| **BB-FUT-5** | settle coin fallback 優化（market endpoint） | rust/openclaw_engine/src/market_data_client/mod.rs | Rust | 2-3h | Advisory | 減少多筆查詢 |

---

## D. Bybit API 覆蓋度分段表（完整清點）

### D.1 REST Endpoints（62 個，分 8 類）

| 類別 | 數量 | 文件 | 完成度 | 上次更新 | 備註 |
|---|---|---|---|---|---|
| **Account（12）** | 12 | account_manager.rs / platform_client.rs | ✅ 100% | 2026-04-12 FIX | fee-rate / wallet / margin / collateral / dcp |
| **Order（10）** | 10 | order_manager.rs | ✅ 100% | 2026-04-20 EDGE-P2-3 | create / cancel / amend / realtime / history |
| **Execution（1）** | 1 | order_manager.rs:539 | ✅ 100% | 2026-04-05 L3 | /v5/execution/list |
| **Position（8）** | 8 | position_manager.rs | ✅ 100% | 2026-04-12 FIX-56 | confirm-pending-mmr fix |
| **Market（15）** | 15 | market_data_client/mod.rs | ✅ 100% | 2026-04-20 EDGE-P2-2 | ticker 擴充 funding/index/OI |
| **Asset（4）** | 4 | platform_client.rs | ✅ 100% | 2026-04-04 | transfer / coin-info |
| **Spot Margin UTA（6）** | 6 | spot_margin_client.rs | ✅ 100% | 2026-04-04 | 維護性保留，無活躍 caller |
| **Leverage Tokens（4）** | 4 | leverage_token_client.rs | ✅ 100% | 2026-04-04 | 同上 |
| **Others（2）** | 2 | platform_client.rs (DCP) | ✅ 100% | 2026-04-04 | disconnected-cancel-all |
| **合計** | **62** | — | ✅ **100%** | — | Rust SSOT；Python drop-in httpx |

### D.2 WebSocket Private Topics（5 個）

| 主題 | Demo | Testnet | Mainnet | LiveDemo | 狀態 | 實裝位置 |
|---|---|---|---|---|---|---|
| `order` | ✅ | ✅ | ✅ | ✅ | ✅ | bybit_private_ws.rs:parse_order_update |
| `execution` | ✅ | ✅ | ❌ | ✅ | ✅ | bybit_private_ws.rs:parse_execution_update |
| `execution.fast` | ❌ | ❌ | ✅ | ❌ | ✅ | bybit_private_ws.rs:parse_fast_execution |
| `position` | ✅ | ✅ | ✅ | ✅ | ✅ | bybit_private_ws.rs:parse_position_update |
| `wallet` | ✅ | ✅ | ✅ | ✅ | ✅ | bybit_private_ws.rs:parse_wallet_update |
| `dcp` | ❌ | ❌ | ✅ | ❌ | ✅ | bybit_private_ws.rs:parse_dcp_triggered |
| **Status Writer** | — | — | — | — | ✅ | bybit_private_ws_status_writer.rs:604 |

**環境感知**：`bybit_rest_client.rs:117-128` BybitEnvironment::private_ws_topics() ✅ 正確

### D.3 WebSocket Public Topics（4 active + 3 disabled）

| 主題 | 狀態 | 禁用原因 | 實裝位置 |
|---|---|---|---|
| `publicTrade.{symbol}` | ✅ Active | — | ws_client.rs:330-340 |
| `kline.{interval}.{symbol}` | ✅ Active | — | ws_client.rs:341-350 |
| `orderbook.50.{symbol}` | ✅ Active | — | ws_client.rs:351-360 |
| `tickers.{symbol}` | ✅ Active | — | ws_client.rs:361-370 |
| `liquidation.{symbol}` | ❌ Disabled | Handler not found（毒化） | parser 保留，subscription 移除 |
| `price-limit.{symbol}` | ❌ Disabled | 同上 | parser 保留，subscription 移除 |
| `adl-notice.{symbol}` | ❌ Disabled | 同上 | parser 保留，subscription 移除 |

**禁用原因驗證**（2026-04-05 B-2 根因）：Bybit demo 靜默接受 subscription 但回 `handler not found`，毒化整個連接

### D.4 IPC 命令（46 個，含 8 個 Bybit 相關）

| 分類 | 數量 | Bybit 相關 | 代表 | 完成度 |
|---|---|---|---|---|
| **Bybit API 相關** | 8 | 8 | get_active_orders / place_order / cancel_order / get_execution_list / get_position_list / get_wallet_balance / confirm_pending_mmr | ✅ 100% |
| Risk Config | 2 | — | get_risk_config / patch_risk_config | ✅ |
| Governance | 12 | — | approve_intent / revoke_lease / cancel_pending_intent | ✅ |
| Budget / Teacher | 8 | — | get_budget_summary / approve_teacher_update | ✅ |
| Misc | 14 | — | exit_now / check_health / get_summary | ✅ |
| Strategy Params | 2 | — | update_strategy_params / get_strategy_params | ✅ |
| 合計 | **46** | **8** | — | ✅ **100%** |

---

## E. Live Gate 5 Gate 細化清單（LIVE-GATE-BINDING-1）

### E.1 五閘完整樹

| # | 門 | 驗證方 | Rust | Python | 實裝位置 | 狀態 |
|---|---|---|---|---|---|---|
| 1 | Python `live_reserved` global mode | Python | 無 | ✅ | live_session_routes.py:160 | ✅ |
| 2 | Python Operator auth + role（live role） | Python | 無 | ✅ | auth_middleware.py + live_session_routes.py | ✅ |
| 3 | `OPENCLAW_ALLOW_MAINNET=1` env var | Rust | ✅ | ✅ | bybit_rest_client.rs:525-537 / bybit_rest_client.py:249-260 | ✅ |
| 4 | Secret slot 有 api_key + api_secret | Rust | ✅ | ✅ | bybit_rest_client.rs:574-587 / bybit_rest_client.py:262-283 | ✅ |
| 5 | `authorization.json` HMAC 簽名 + 未過期 + env_allowed 匹配 | Rust | ✅ | ❌ | startup.rs:LIVE-GATE-BINDING-1 + main.rs 5min re-verify | ✅ |

**Rust 可驗證**：3 項（#3 / #4 / #5）  
**Python 驅動**：2 項（#1 / #2）

### E.2 Authorization Flow

```
Operator 決策 live → Python live_trust_routes.py:160 _write_signed_live_authorization()
  ↓
HMAC-SHA256(api_secret, payload_json) → signature
  ↓
寫入 $OPENCLAW_SECRETS_DIR/live/authorization.json
  ↓
Rust startup.rs 讀取 + 驗簽 + 5min re-verify
  ↓
失驗 → cancel_token shutdown（優雅）
```

**檢查點**：
- signature 正確（api_secret 推導）
- exp_at_ms > now （未過期）
- env_allowed matches current env（環境匹配 live vs live_demo）

---

## F. 規範文檔同步待辦

### F.1 SSOT 標記（短期）

每個字典章節需加：
```markdown
## 章節名
**SSOT**：代碼為唯一真實來源。以下內容對應 Rust `openclaw_engine/src/<file>.rs`。
如代碼與此文檔有分歧，以代碼為準。
最後同步日期：YYYY-MM-DD · 驗証者：<agent>
```

### F.2 Version Tracking

字典版本記錄：
- v1.0 2026-04-04 初版（46 endpoints）
- v1.1 2026-04-05 L3 audit（39 PyO3 方法）
- v1.2 2026-04-12 FIX-56（confirm-pending-mmr）
- v1.3 2026-04-20 EDGE-P2（ticker 擴充）
- v1.4 2026-04-24 此次（confirm-mmr 正式修 + L-1~5 補錄）

### F.3 CI Automation（長期）

- 每新增 REST endpoint → 自動在 §1 生成 stub
- 每新增 WS topic → 自動在 §2 註冊
- 每改變 retCode 分類 → 自動驗証 bybit_rest_client.rs 對應
- Bybit V5 spec 變更偵測（monthly webhook）

---

## G. 統計 + 優先排序

### G.1 完整提案統計

| 層級 | 項數 | 工時合計 | 負責主軸 | 截止 |
|---|---|---|---|---|
| **High（代碼 + 字典必改）** | 4 項（H-1 + M-1/2/3） | **3-5h** | E1 / E2 / TW | W1 |
| **Low（字典 + 文檔）** | 7 項（L-1~7） | **2-3h** | TW | W1 或 W2 |
| **Observability** | 3 項（OBS-1/2/3） | **2-3h** | E1 / QA | W2 |
| **Future / Advisory** | 5 項（FUT-1~5） | **2-3d** | 待決 | P3 |
| **合計** | **19 項** | **8-11h + 2-3d** | — | — |

### G.2 優先排序（執行順序）

**第 1 優先**（W1 立即開工）：
1. BB-M-1 ws_client 強制重連（2h）
2. BB-H-1 字典 confirm-mmr（0.5h）
3. BB-M-2 connectivity_check URL 環境變數（1h）
4. BB-M-3 smoke_test 環境感知或刪除（1-2h）

**第 2 優先**（W1 完成後、W2 內）：
5. BB-L-1/L-2/L-3 字典參數正確 + 補錄（2h）
6. BB-L-4/L-5/L-6 字典補述 WS / ticker（2h）
7. BB-OBS-1/2/3 Healthcheck 強化（2-3h）

**第 3 優先**（P3 或持續）：
8. BB-FUT-1~5 工具化、自動化、監控化（2-3d）

---

## 結論與建議

### Summary

OpenClaw 對 Bybit V5 API 的集成質量：**優秀 → A+**

核心優勢：
1. **統一 SSOT**（Rust engine）— 無分散 API 調用
2. **環境隔離清晰**（Demo/Mainnet/LiveDemo 三分法）
3. **私有 WS 環境感知完備**（topic 分組正確）
4. **五閘認證機制穩健**（HMAC + 過期檢查 + Operator）
5. **fail-closed 保守策略**（無重試、無自動降級）

遺留項目：
- 4 個 Medium / 7 個 Low 字典 drift（均可快速修復）
- 無 Critical / High 實作 bug

### 下一步建議

**Operator 應於本週執行**：
1. 合入 BB-M-1/2/3 + BB-H-1 PR（1-2 sprint）
2. 批次更新字典 L-1~7（TW + E2 審查，1d）
3. 加入 Bybit API 字典 SSOT 標記（enforcement rule）
4. 啟用 BB-OBS-3 告警（ci-enabled）

**後續維護規律**：
- 每新增 Bybit endpoint：字典同步 + audit checklist
- 月度 drift 掃描（via BB-OBS-1）
- Bybit spec 變更監控（webhook）

---

**報告生成**：2026-04-24  
**簽署**：BB (Bybit API Compatibility Auditor)  
**版本**：v1.0（首份完整 TODO 提案）

