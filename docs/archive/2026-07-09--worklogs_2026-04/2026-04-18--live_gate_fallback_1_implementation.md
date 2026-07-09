# LIVE-GATE-FALLBACK-1 — REST-only reduce_only close path

**Date:** 2026-04-18
**Status:** ✅ Implemented, awaiting deployment (API restart only, no Rust rebuild)
**Severity:** P0 (operator cannot close live positions via GUI)
**Parent:** LIVE-GATE-BINDING-1 (2026-04-18, commit `1239312`)

---

## RCA — LIVE-GATE-BINDING-1 副作用引發的 GUI 平倉失敗

### 觸發場景
Operator 今天透過 GUI 嘗試：
1. `Stop Live Session` 按鈕 → 返回 200 OK 但 `errors` 陣列含多筆錯誤
2. `Close All Positions` 按鈕 → 同上

### 實際錯誤訊息（引擎 log + API log）
```
503: IPC command 'close_all_positions' failed: Engine RPC error [-32603]:
paper command channel not configured / 引擎 RPC 錯誤 [-32603]:
paper command channel not configured

Live orphan sweep: close_position ADAUSDT failed: 503: ... paper command channel not configured
Live orphan sweep: close_position ENAUSDT failed: 503: ... paper command channel not configured
Live orphan sweep: close_position FARTCOINUSDT failed: 503: ... paper command channel not configured
Live orphan sweep: close_position MOVRUSDT failed: 503: ... paper command channel not configured
Live orphan sweep: close_position ETHUSDT failed: 503: ... paper command channel not configured
Live orphan sweep: close_position IPUSDT failed: 503: ... paper command channel not configured
```

### 根因鏈
1. `authorization.json` 不存在（operator 從未走過 `/api/v1/live/auth/renew` 流程）
2. 今日 20:13 local restart → Rust `build_exchange_pipeline(Live, LiveDemo)` 被 LIVE-GATE-BINDING-1 拒絕 → `live_bindings = None`
3. `main.rs:359` `live_cmd_tx = None` → `EngineCommandChannels::live = None` 從未註冊
4. Python GUI 發 IPC `close_all_positions(engine=live)` → `ipc_server/mod.rs:750` → `extract_engine_tx("live") → None` → `handle_paper_cmd` 返回 `-32603: paper command channel not configured`
5. Python `_sweep_live_orphan_positions` 用 live API key 查 Bybit 交易所，發現 7 個 live 倉位（前次 Live 運行遺留）→ 逐一 `close_position` IPC → 同樣 `None` channel → 7 筆 error

### 設計缺陷
LIVE-GATE-BINDING-1 把「啟動新下單管線」與「平既有持倉」兩件事**綁在同一個門控上**。
違反根原則 #6 **「失敗默認收縮」**：授權失效時應該

- ❌ 拒絕**開新倉**
- ✅ **仍然允許平倉**（縮倉、清理 orphan）

當前狀態：交易所有 7 個 live 倉位，operator 無法從 GUI 平掉。

---

## 修復契約

**拆分門控：**
- **開倉路徑**（spawn pipeline / intent→order）維持嚴格門控（LIVE-GATE-BINDING-1 不變）
- **平倉路徑**（close_all / close_position / orphan sweep）新增 REST 降級 fallback

### 降級觸發條件（嚴格）
僅當 IPC 錯誤訊息 **完全包含** `"paper command channel not configured"` 時才降級。任何其他錯誤（網路 timeout、Bybit retCode=10001、stepSize violation 等）原樣記錄到 `errors` 陣列，**不降級** — 避免遮蔽真實問題。

### 降級行為
1. 用 live slot API key（同既有 `_get_rust_client_safe()`）取得 `BybitClient`
2. 發 `place_order(symbol, side, "Market", qty, reduce_only=True)`
   - `side = "Sell" if is_long else "Buy"`
   - `qty = rc.round_qty(symbol, qty)`（對齊 step size，`round_qty` 失敗時 raw qty）
3. Response 標記 `rest_fallback=True`, `reason="live_pipeline_not_authorized"`, `source="rust_engine_with_rest_fallback"`

---

## 實作變更

### `app/live_session_routes.py`

新增：
- `_CHANNEL_NOT_CONFIGURED_MARKER` 常量
- `_is_live_channel_unavailable_error(exc)` — 錯誤分類器
- `_rest_close_position_reduce_only(rc, symbol, qty, is_long)` — REST 平倉 helper

改造：
- `_sweep_live_orphan_positions()` — IPC 失敗時判別並降級；新增 `rest_fallback / swept_via_ipc / swept_via_rest` response 欄位
- `post_live_close_all_positions()` — IPC `close_all_positions` channel-not-configured 時不記 error；response 新增 `rest_fallback / reason`
- `post_live_session_stop()` — 同上
- `post_live_close_position(symbol)` — 單 symbol 路徑也降級（需 hints 俱全：qty + is_long）

### `tests/test_live_gate_fallback.py`（新）

11 單測：
1. `test_detects_channel_unavailable_error` — 錯誤分類器正確識別
2. `test_does_not_flag_generic_errors` — timeout / retCode / connection refused 不誤判
3. `test_rest_close_long_uses_sell_side_reduce_only` — 多頭 → Sell + reduce_only
4. `test_rest_close_short_uses_buy_side_reduce_only` — 空頭 → Buy + reduce_only
5. `test_rest_close_aligns_qty_via_round_qty` — qty 經 round_qty 對齊
6. `test_rest_close_survives_round_qty_failure` — round_qty 失敗 fallback raw qty
7. `test_orphan_sweep_fallback_on_channel_unavailable` — 所有位置都走 REST
8. `test_orphan_sweep_does_not_fallback_on_generic_error` — retCode=10001 不降級
9. `test_orphan_sweep_records_rest_failure` — REST 也失敗時正確記 error
10. `test_orphan_sweep_no_positions_returns_zero_swept` — 空持倉零 IPC 調用
11. `test_orphan_sweep_mixed_ipc_and_rest` — IPC 和 REST 混合路徑計數正確

結果：**11/11 passed**（加上既有 `test_live_authorization_signing` 的 10/10 合計 **21/21 passed**）

---

## 部署

**純 Python 修改，不需 `--rebuild`：**

```bash
cd /home/ncyu/BybitOpenClaw/srv
bash helper_scripts/restart_all.sh         # 不需 --rebuild
```

Rust binary 不變（`openclaw_engine` 保持上次 build）。只 restart uvicorn。

### 部署後立即驗證

1. GUI 按 `Close All Positions` 應返回 `rest_fallback=true, errors=null`
2. 引擎 log 出現：
   ```
   LIVE-GATE-FALLBACK-1: IPC close_all_positions channel unavailable ...
   Live orphan sweep: close_position XXXUSDT qty=... (REST fallback — live pipeline not authorized)
   ```
3. Bybit 交易所 7 個 orphan 持倉（ADAUSDT / ENAUSDT / FARTCOINUSDT / MOVRUSDT / ETHUSDT / IPUSDT 等）被清空
4. 確認：`python3 -c "from openclaw_core import BybitClient; print([(p['symbol'], p.get('size')) for p in BybitClient(environment='live_demo').get_positions('linear') if float(p.get('size') or 0) > 0])"`

---

## 已知限制與 follow-up

1. **降級後仍無 ConfigStore 治理**
   REST 降級繞過 Rust risk gates (P0/P1/P2)。**設計上可接受** — `reduce_only=True` 的 Market 平倉本質是縮倉，P0 denylist/BIL/max_qty 等在平倉方向永遠不觸發。但失去了 Rust 側的 audit（不寫 `trading.fills` 的 live 路徑）。未來可補一個 Python-side `live_rest_fallback_events` 表或 log-only audit。

2. **Single close_position fallback 依賴 hints**
   `post_live_close_position(symbol)` 必須先用 REST 查到 `qty + is_long` 才能降級。若 `get_positions` 失敗、或持倉在兩次查詢之間被手動關閉（race），fallback 不會觸發（返回 502）。這是設計上的 fail-closed，不是 bug。

3. **寄望 operator 走正常 renew 流程**
   長期：LIVE-GATE-FALLBACK-1 只是為了讓 authorization 缺失狀態下仍能平倉自保。正確運維流程仍是 operator 經 `/api/v1/live/auth/renew` 簽發 `authorization.json` → restart → live pipeline 正常啟動。

---

## 不變量（未破壞）

- ✅ LIVE-GATE-BINDING-1 的啟動門控不變（pipeline spawn 仍需有效 authorization.json）
- ✅ LIVE-GUARD-1 的 Mainnet 三重硬鎖不變
- ✅ 沒有新增 Rust 代碼，沒有新增 PyO3 接口
- ✅ 降級觸發條件**嚴格** — 只看一個字串 marker，其他錯誤原樣暴露
- ✅ LiveDemo 不因 api-demo endpoint 而放寬任何檢查（該 marker 對 Mainnet / LiveDemo 通用）
- ✅ 根原則 #6「失敗默認收縮」得到滿足：授權失效時可平倉、不能開倉
