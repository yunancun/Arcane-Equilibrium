# 工程日誌 2026-04-12
# Earned-Trust TTL Ladder + Audit Trail 時間戳修復

**Session 類型**：跨 context 延續（前半段 context 被壓縮）  
**Commit**：`5d99875`  
**測試基準線更新**：Python 2792 → **2852** passed（+53 新測試，0 fail）

---

## 一、觸發問題

用戶報告兩個獨立 bug：

1. **Audit Trail 不顯示時間** — Governance tab 審計軌跡時間欄永遠顯示 `--`
2. **Live 從未看到過授權申請** — 系統應每天要求授權，但 operator 一次都未被通知

---

## 二、問題分析

### Bug 1 — Audit Trail 時間戳

**根因**：`tab-governance.html` JS 讀 `r.timestamp`，但伺服器 `ChangeRecord.to_dict()` 實際輸出 `when`（秒）和 `when_ms`（毫秒）。兩個字段名稱不匹配，導致 `ocTime()` 收到 `undefined`，返回 `'--'`。

**修復**（1 行）：
```javascript
// Before (bug):
const timeStr = r.timestamp ? ocTime(r.timestamp) : '--';
// After (fix):
const timeStr = r.when_ms ? ocTime(r.when_ms) : (r.when ? ocTime(r.when * 1000) : '--');
```

### Bug 2 — 實盤授權靜默過期

**根因架構分析**：
- `_EXECUTION_AUTHORITY_OVERRIDE`：真正控制實盤交易的記憶體 gate，**沒有 TTL**，重啟才清空（fail-closed），但運行中永遠有效
- `SM-01 Authorization`：治理追蹤層，確實有 24h TTL，但過期後**不阻斷 `_EXECUTION_AUTHORITY_OVERRIDE`**，也不通知 operator
- 兩層完全脫鉤：SM-01 在記錄上過期，真實交易繼續不受影響，operator 從不知道

**根本設計缺陷**：系統缺少「授權需要主動續期」的強制執行機制。SM-01 TTL 是審計記錄，不是 gate。

---

## 三、設計決策記錄

### Earned-Trust TTL Ladder 設計

用戶確認的設計原則：
1. **連續乾淨天數**（不是累計）— 觀察窗口在任何違規時完全重置
2. **中途降級即時通知，session 繼續** — 本次 session 不中斷，但下次 Renew 必須從低 tier 開始
3. **T3 自動續期一次（+15天）** — 最長 30 天後強制 Operator 全面審查

**最終 Tier 設計**：

| Tier | 名稱 | TTL | 晉升門檻 | 條件 |
|------|------|-----|---------|------|
| T0 | Entry | 24h | 初始 / 任何停止後 | — |
| T1 | Provisional | 72h | T0 連續 7 乾淨天 | net_pnl>0, dd<5%, cost_ratio<50%, 零嚴重事件 |
| T2 | Established | 168h | T1 連續 14 乾淨天 | + win_rate≥35%, pf≥1.2, sharpe≥0.5 |
| T3 | Trusted | 360h | T2 連續 21 乾淨天 | + pf≥1.4, sharpe≥0.8, consec_loss<5, window_dd<10% |

**中途降級觸發閾值**：
- `consecutive_losses >= 5` → 降一級
- T2/T3 `max_daily_drawdown_pct >= 8%` → 降一級
- `reconciler_major_drift_cycles >= 3` → 降一級

**T3 續期邏輯**：
- 首次進入 T3：`renewals_at_t3 = 0`
- T3 → T3 renew：`renewals_at_t3 += 1`
- `renewals_at_t3 >= T3_MAX_AUTO_RENEWALS (=1)` → action=`block_review`，強制 `/renew-review` 端點

**Session 停止 vs 重啟**：
- **主動 stop**：tier 重置為 T0（信任清零）
- **進程重啟**：tier 從 JSON 恢復（重啟不懲罰）

### 文件大小管理

`live_session_routes.py` 原 1192 行（接近 1200 行硬上限）。新增內容（鉤子 + helper 共 ~39 行）帶到 1231 行。  
解決方案：
- 將所有新端點放入獨立 `live_trust_routes.py`（484 行）
- 壓縮 `live_session_routes.py` 中幾個冗長 docstring（`_revoke_live_governance_auth`、`get_live_session_status`、`get_live_metrics`）
- 最終：1197 行（合規）

---

## 四、實作清單

### 新建文件

**`earned_trust_engine.py`**（715 行）
- `TrustTier` IntEnum（T0-T3）
- `TrustMetrics` dataclass（13 個指標字段）
- `TierRequirements` frozen dataclass（per-tier 晉升門檻）
- `_TIER_REQUIREMENTS` dict — T1/T2/T3 各自的最低門檻
- `EarnedTrustState` dataclass（持久化 + JSON round-trip）
- `RenewalRecommendation` / `MidSessionDowngrade` 結果類
- `EarnedTrustEngine` 核心引擎（thread-safe，`threading.Lock`）：
  - `on_session_start()` / `on_auth_renewed()` / `on_session_stop()`
  - `check_mid_session_downgrade()` → Optional[MidSessionDowngrade]
  - `evaluate_renewal()` → RenewalRecommendation
  - `record_incident()` — 重置連勝 + pending_downgrade
  - `get_state_snapshot()` — API dict
  - `_compute_current_clean_days()` / `_save()` / `_load_or_init()`
- `_check_requirements()` module-level 函數
- `get_trust_engine()` 模塊級 singleton（double-checked locking）

**`live_trust_routes.py`**（484 行）
- `_collect_live_metrics()` — 從 Rust reader + paper_trading_routes + live_session_routes + GovernanceHub 收集指標（graceful degradation）
- `_create_live_auth()` — 創建並自動批准 SM-01 live 授權
- `_revoke_existing_live_auths()` — 續期前撤銷舊授權
- `RenewBody` / `FullReviewBody` Pydantic models
- `GET /api/v1/live/auth/trust-status` — 只讀，任何角色可調用
- `POST /api/v1/live/auth/renew` — Operator 必需；不允許自我提升超過建議；T3 cap 時 409
- `POST /api/v1/live/auth/renew-review` — T3 強制全面審查；重置 `renewals_at_t3`

**`test_earned_trust_engine.py`**（609 行，53 測試）
- 10 個測試類：InitialState / SessionLifecycle / AuthRenewal / EvaluateRenewal / MidSessionDowngrade / IncidentRecording / CheckRequirements / Persistence / StateSnapshot / ThreadSafety
- 覆蓋所有關鍵路徑：晉升/降級/T3上限/持久化/並發

### 修改文件

**`live_session_routes.py`**（1192 → 1197 行）
- `import time` 確認存在
- `post_live_session_start()` 尾部加 trust engine start 鉤子（非阻塞 try/except）
- `post_live_session_stop()` 加 trust engine stop 鉤子
- 文件末尾加 `_grant_execution_authority_internal()`（供 live_trust_routes renew 後重新授予 in-memory gate）
- 3 個冗長 docstring 壓縮以回到 1200 行內

**`main.py`**
- 注冊 `live_trust_router`（2 行）

**`tab-live.html`**
- CSS：`.trust-bar`（ok/warn/crit/review 變體）/ `.trust-tier-badge` / `.trust-renew-card`
- HTML：Trust Status Bar + Renewal Card + Full Review Panel（插在 Performance Metrics 前）
- JS（本 session 補完）：
  - `TRUST_TIER_LABELS` / `TRUST_TIER_COLORS` 常量
  - `loadTrustStatus()` — GET trust-status → 渲染 badge/倒計時/欄色/pending 降級 banner
  - `_renderRenewalCard()` — 填充建議摘要 + 失敗條件列表 + 預選 tier + 顯/隱 full review panel
  - `openTrustRenewCard()` / `closeTrustRenewCard()`
  - `submitRenew()` — POST renew，成功後刷新狀態
  - `submitFullReview()` — POST renew-review，最少 10 字檢查
  - `refreshPage()` 加入 `loadTrustStatus()`

**`tab-governance.html`**（前半 session，本 session 已確認 committed）
- Audit Trail JS：`r.timestamp` → `r.when_ms || r.when*1000`

---

## 五、測試結果

```
test_earned_trust_engine.py — 53/53 PASSED (0.10s)
全套 Python regression — 2852 passed · 5 skipped · 0 fail (61s)
```

---

## 六、已知限制 / 後續工作

1. **mid-session downgrade 只在 `check_mid_session_downgrade()` 被主動調用時才觸發** — 目前無背景輪詢。需要一個週期性任務（例如加入 contraction monitor loop）每 N 分鐘調用一次並在觸發時推送通知（OC-3 告警整合）。
2. **`_collect_live_metrics()` 的 `observation_days`** — 目前設為 0（未從 DB 計算實際觀察窗口天數），影響精確度但不影響功能（0 天 < 任何 `min_clean_days`，只是顯示不準確）。精確實作待 LG-1 21d 觀察期完成後補充。
3. **`update_clean_days()` 未接定時器** — 目前 `clean_days_in_tier` 在快照中從 `clean_day_streak_start_ts_ms` 實時計算，數值正確，但 `EarnedTrustState` 持久化的 `clean_days_in_tier` 字段不會自動更新。對功能無影響（evaluate_renewal 用實時計算），只是 JSON 快照中的數字是時間點值。
4. **通知 operator 的機制** — 目前 near_expiry/expired 狀態只在 UI 上顯示，沒有推送通知（email/Telegram）。整合 OC-3 告警管線後補。

---

## 七、架構影響

**授權流完整性補全**：
```
前：_EXECUTION_AUTHORITY_OVERRIDE（無 TTL）← session start 時自動 granted，永不過期
後：_EXECUTION_AUTHORITY_OVERRIDE（revoke on stop/emergency）+ EarnedTrustEngine（TTL ladder）
    ↑ 兩層耦合：session stop → trust.on_session_stop() → T0 reset
              : renew → _grant_execution_authority_internal() → in-memory gate 重新授予
```

**新文件依賴方向**（符合現有 import 規則）：
```
tab-live.html
  → GET/POST /api/v1/live/auth/*
      → live_trust_routes.py
          → earned_trust_engine.py (pure state, no FastAPI)
          → live_session_routes._grant_execution_authority_internal()
          → governance_hub.GovernanceHub (SM-01 auth creation)
```

---

*Commit `5d99875` · 2026-04-12*
