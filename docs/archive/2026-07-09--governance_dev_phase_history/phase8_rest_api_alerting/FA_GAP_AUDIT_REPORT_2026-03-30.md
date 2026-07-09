# Phase 8 FA Gap Audit Report
# 第八階段 FA 差距審計報告

**日期：** 2026-03-30
**基準：** Phase 1–7 完成後（50 tasks, 1788 tests passed）
**主題：** REST API 端點 + 告警整合

---

## 審計發現

### 現有 REST 端點覆蓋率
- Paper Trading: 22 個端點（session/order/position/market-feed）✅
- Governance: 6 個端點（status/auth/risk/reconcile/leases/health）— 基本覆蓋
- Risk Control: 8 個端點（config/status/adjust/unhalt）— 完善
- 策略: 11 個端點 ✅

### 缺失的關鍵端點
1. Recovery Gate 操作（request/approve）— 代碼完成但無 REST 綁定
2. De-escalation 操作 — 代碼完成但無 REST 綁定
3. ChangeAuditLog 查詢 — 豐富的查詢方法但無 API
4. Symbol Whitelist CRUD — 僅能透過 category config 間接操作
5. 詳細治理狀態（SM 級別）
6. Incident 事件查詢

### 告警整合缺失
- TelegramAlerter 存在但未接入 SM 回調
- GrafanaDataWriter 存在但不記錄治理事件
- CIRCUIT_BREAKER / FATAL mismatch / Daily loss halt 無即時告警

---

## Phase 8 範圍（精煉後）

| Gap | 優先級 | 類型 |
|-----|--------|------|
| G8.01 Recovery Gate REST endpoints | P1 | REST |
| G8.02 De-escalation REST endpoints | P1 | REST |
| G8.03 ChangeAuditLog query endpoint | P1 | REST |
| G8.04 Symbol whitelist CRUD endpoints | P1 | REST |
| G8.05 Detailed governance status endpoint | P2 | REST |
| G8.06 TelegramAlerter → SM critical events | P1 | Alerting |
| G8.07 Integration tests | P1 | Test |

---

*報告由 FA（via Cowork PM）於 2026-03-30 產出*
