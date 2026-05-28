# 2026-04-01 工程日誌 — Governance Authorization 重啟丟失修復 & 訂單解封

**日期**：2026-04-01（下午，CEST）
**觸發**：用戶回報 Paper + Demo 運行數小時但零下單
**結果**：根因診斷完成，訂單解封，commit `d065453`
**測試基準**：3341 passed（未變動，本次修復不含新測試，E4 通過）

---

## 一、問題現象

用戶反映：Paper Trading session 活躍、Demo 同步運行，但幾小時內完全沒有任何訂單成交。

---

## 二、診斷過程

### 2.1 第一層：查 paper_trading_state.json

```
Total orders: 13（全部 paper_order_rejected）
reject_reason: symbol_CYSUSDT_not_in_category_whitelist
              symbol_XPLUSDT_not_in_category_whitelist
              ... （共 8 種幣種，每種 1-2 筆）
```

所有 13 個訂單被 `symbol_XXX_not_in_category_whitelist` 拒絕。此 reject 格式已在
commit `f4663d3`（05:58 今日）移除（T5.04 whitelist check removal）。

**結論**：這 13 個拒單是 **舊問題的歷史遺留**，發生在 05:58 修復之前。

### 2.2 第二層：查 Audit Log

```jsonl
{"overall_result": "MISMATCH_MINOR", "discrepancy_count": 13,
 "actions_triggered": ["FREEZE_TRADING"]}
```

對賬引擎每 ~60 秒觸發一次，報告 13 個 discrepancies（Paper 有 13 個 REJECTED 訂單，Demo 無對應記錄）→ 超過 `max_discrepancies_before_freeze=5` 門限，建議 `FREEZE_TRADING`。

但 GovernanceHub 收到 MISMATCH_MINOR 只記錄 warning 並 return，**不實際凍結**。

**結論**：對賬警報是誤導性噪音，不是真實的訂單阻塞原因。

### 2.3 第三層：查 Pipeline Bridge 統計

```json
{
  "active": true,
  "ticks_received": 6734,
  "intents_submitted": 0,
  "intents_accepted": 0,
  "intents_rejected": 231,
  "intents_h0_blocked": 8
}
```

- Bridge 是活躍的（active: true），ticks 在正常流入
- 231 個 intents 被拒絕，0 個成功提交
- Intents 確實在生成（`/strategy/intents` 顯示 50 個 pending intents）

### 2.4 第四層：查 GovernanceHub 狀態

```json
{
  "authorization": {
    "state": "NONE",
    "is_effective": false
  }
}
```

**根本原因找到**：`authorization.state = "NONE"` — 沒有任何有效授權！

`pipeline_bridge._process_pending_intents()` 在每個 intent 上調用 `self._governance_hub.is_authorized()`，無有效授權時返回 False，intent 被靜默拒絕並 `intents_rejected += 1`。

---

## 三、根本原因分析

### 直接根因：grant_paper_authorization() 未在重啟後被調用

**正常流程（首次啟動 session）：**
```
POST /paper/session/start
  → ENGINE.start_session()
  → GOV_HUB.grant_paper_authorization()  ← 授權在此被自動授予
  → Authorization state: ACTIVE
```

**問題流程（服務器重啟，已有 active session）：**
```
服務器重啟
  → PaperStateStore.load()  ← 從 paper_trading_state.json 載入已有 session
  → session_state = "active"（已有活躍 session）
  → grant_paper_authorization() 從未被調用！
  → Authorization state: NONE  ← 問題所在
```

Paper Trading session 的狀態（orders/positions/balance）持久化到文件，
但 GovernanceHub 的授權是**純記憶體狀態**，重啟後歸零。
當服務器載入持久化的 session 時，不重新執行 `start_session()`，
因此 `grant_paper_authorization()` 沒有機會被調用。

### 複合問題：get_status() 未填充 auth_pending_approval

`approve_authorization` 端點依賴 `status.auth_pending_approval` 判斷是否有待審批授權，
但 `get_status()` 從不設置此欄位（始終為 `False`），導致：
- 手動發起 `POST /governance/auth/request` 後，auth 進入 PENDING_APPROVAL 狀態
- 嘗試 `POST /governance/auth/approve` → 返回 "No pending authorization approval"
- approve 端點完全失效

---

## 四、修復方案

### 即時修復（無需重啟服務器）

```bash
# Step 1: Stop current session（balance 未有實際交易，安全重置）
POST /api/v1/paper/session/stop

# Step 2: Start new session（觸發 grant_paper_authorization()）
POST /api/v1/paper/session/start
  {"initial_balance": 1000.0}

# Verify:
GET /api/v1/governance/auth/status
# → {"state": "ACTIVE", "is_effective": true}
```

授權生效後，pipeline bridge 立即開始提交 intents：
```
intents_submitted: 1, intents_accepted: 1, demo_synced: 1
第一筆訂單: FARTCOINUSDT Sell 860 qty @ 0.1743 → filled ✅
```

### 永久修復（commit d065453）

**修復 1：`governance_hub.get_status()` 補填 `auth_pending_approval`**

```python
# 在 _authorization_sm.get_effective() 返回空時，額外檢查 PENDING_APPROVAL 狀態
auth_pending_approval_flag = False
if effective_auths:
    ...
else:
    auth_state = "NONE"
    try:
        all_auths = self._authorization_sm.list_all()
        auth_pending_approval_flag = any(
            a.state.value == "PENDING_APPROVAL" for a in all_auths
        )
    except Exception:
        pass
```

修復後 `approve` 端點可正常工作。

**修復 2：`POST /paper/session/reauth` 新端點**

無需重置 session，直接重新授予 paper authorization：

```bash
POST /api/v1/paper/session/reauth
# → {"granted": true, "is_authorized": true}
```

**修復 3：服務器啟動時自動補授權（`main.py _startup_integrity_check`）**

```python
# 啟動時若 active session 存在但無授權，自動補授
if _is_active and GOV_HUB is not None:
    if not GOV_HUB.is_authorized():
        _granted = GOV_HUB.grant_paper_authorization()
```

（此修復已在 commit `1237744` APR01 批次中包含）

---

## 五、其他一併提交的改動（APR01 批次殘留）

| 文件 | 改動 | 原因 |
|------|------|------|
| `backtest_routes.py` | 從 KLINE_MANAGER + Bybit REST API 獲取 OHLCV 數據 | 回測可使用歷史 K 線 |
| `experiment_routes.py` | Pydantic Field max_length 約束 | DoS/存儲保護 |
| `main_legacy.py` | CORS wildcard `*` 安全修復（APR01-HIGH-1） | 允許 `allow_credentials=True` + `*` 違反 CORS 規範 |

---

## 六、診斷中的關鍵觀察

### 對賬 FREEZE_TRADING 是假警報

```
reconciliation_engine._determine_actions():
  elif len(report.discrepancies) >= self._config.max_discrepancies_before_freeze:
      actions.append(IncidentAction.FREEZE_TRADING.value)  # 觸發

governance_hub._on_reconciliation_mismatch():
  if severity == "MISMATCH_MINOR":
      logger.warning(...)
      return  # 不實際凍結
```

`max_discrepancies_before_freeze=5`，13 個舊拒單觸發了 FREEZE_TRADING 建議，
但 GovernanceHub 對 MISMATCH_MINOR 只記錄 warning，並不真正凍結。
Audit log 中的 `"actions_triggered": ["FREEZE_TRADING"]` 是**對賬引擎的建議**，
不是 GovernanceHub 的實際動作。

### 對賬誤差的處理方向

13 個舊拒單造成持續對賬 discrepancy，每分鐘一次警報。
長期應考慮：在對賬引擎中排除 REJECTED 狀態的訂單（它們在 Demo 端本來就不存在，
不應被視為不一致）。暫記為 P3 技術債。

---

## 七、Commits

| Hash | 描述 |
|------|------|
| `d065453` | fix(governance): 修復服務器重啟後 Paper Authorization 丟失 |
| `1237744` | fix(learning): APR01 Batch 1（含 startup_integrity_check 自動補授權） |

---

## 八、後續注意事項

1. **服務器每次重啟後**：如果 paper session 已有 active 狀態，現在的 startup 代碼
   會自動調用 `grant_paper_authorization()`，不再需要手動 stop/start。
2. **對賬 MISMATCH_MINOR 噪音**：暫時忽略，13 個舊拒單持續觸發，不影響正常交易。
3. **Demo 同步**：訂單解封後，pipeline bridge 正確同步 paper/demo（`demo_synced: 1`）。
