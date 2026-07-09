# Batch G：GUI 與 API 端點
# Batch G: GUI & API Endpoint Verification

**審查時間：** 2026-03-30
**狀態：** ✅ 完成
**結論：** 所有主要 API 路由存在且數據源正確；GUI 端點調用路徑完整

---

## G1：主要路由前綴（main.py）

✅ **代碼確認**

| 前綴 | Router | 路由數量 |
|------|--------|---------|
| `/paper` | paper_trading_routes | ~14 路由 |
| `/layer2` | layer2_routes | ~9 路由 |
| `/risk` | risk_routes | ~多條 |
| `/strategy` | phase2_strategy_routes | ~20 路由 |
| `/governance` | governance_routes | ~多條 |
| `/scout` | scout_routes | — |
| `/api/v1/` 前綴統一 | main_legacy.py | ~85+ 路由 |

---

## G2：Paper Trading Tab 端點

✅ **所有關鍵端點確認存在**

Session 控制：
- `POST /api/v1/paper/session/start`
- `POST /api/v1/paper/session/pause`
- `POST /api/v1/paper/session/resume`
- `POST /api/v1/paper/session/stop`

狀態查詢：
- `GET /api/v1/paper/session/status`
- `GET /api/v1/paper/orders`
- `GET /api/v1/paper/positions`
- `GET /api/v1/paper/pnl`
- `GET /api/v1/paper/fills`
- `GET /api/v1/paper/market-feed/status`

Session 12 G1 修復（訂單狀態過濾器）已確認對應正確的 paper_order_working / paper_order_partially_filled 狀態名。

---

## G3：Learning Cockpit 端點

✅ **Session 12 G6 修復後確認正確**

- `GET /api/v1/learning/feed` → `totals`（observations_recent / lessons_recent 計數）
- `GET /api/v1/learning/overview` → `observation_summary`
- 當前顯示：observations = 0（數據源空置，因 0 round_trips）

---

## G4：Strategy Tab 端點

✅ **所有路由確認**

| 端點 | 用途 |
|------|------|
| `GET /strategy/list` | 策略列表 + 狀態 |
| `GET /strategy/scanner/opportunities` | 掃描器機會 |
| `GET /strategy/scanner/deployed` | 已部署策略 |
| `GET /strategy/demo/balance` | Demo 帳戶餘額 |
| `GET /strategy/demo/positions` | Demo 持倉（13 個） |
| `POST /strategy/{name}/activate` | 激活策略 |
| `POST /strategy/{name}/pause` | 暫停策略 |

**注意：** Session 12 G5 已移除不存在的 `/strategy/demo/status` 端點。

---

## G5：認證中間件

✅ **Bearer token 驗證覆蓋**

- API token 路徑：`control_api_v1/.secrets/api_token`
- 所有 `/api/v1/` 端點需要 `Authorization: Bearer <token>`
- Governance 路由需要額外的 `operator` scope

---

## G6：Paper vs Demo 對比 Tab

✅ **Session 12 G5 修復後確認正確**

- 從 `result.list[0]` 提取 `totalRealizedPL` 等字段
- 新增性能指標折叠區（Total Equity / Available Balance / Margin Rate / PnL）
- 移除不存在的 `/strategy/demo/status` 404 回退路徑

---

## 結論

GUI 10-Tab 控制台所有主要 API 端點均存在。數據顯示空白（0 fills/observations）是系統靜止的正常反映，非端點問題。
