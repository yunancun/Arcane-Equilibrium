# E1 W1-T3 — Python strategist_history.effect adapt + GUI passthrough fills exit_reason

**Date**: 2026-04-29
**Wave**: PA strategy_name attribution cleanup W1-T3
**PA design ref**: `docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-29--strategy_name_attribution_cleanup_design.md` §1.2 + §4 W1-T3
**Pre-conditions**: W1-T1 commit `45bbe4d` landed（V033 schema + TradingMsg::Fill exit_reason scaffold + build_close_tags helper）；W1-T2 並行進行（16 emit point 改寫，本任務不依賴）；engine PID 狀態見 §三 status drift 採集時間 2026-04-29 12:38 CEST

---

## §1 任務摘要

PA W1-T3 範圍 4 子項，全部落地：

| 子項 | 範圍 | 狀態 |
|---|---|---|
| (a) `_fetch_effect_for_row()` SQL 確認 | `WHERE strategy_name = %s` 不需動 — W1-T2 後 enum match 自動命中 entry + close 兩面 | ✅ 確認 |
| (b) 釘契約 unit tests × 3 | 7d aggregate close-PnL post-T2 / pre-T2 baseline 0 / 5 enum 全覆蓋 | ✅ 加 |
| (c) `strategy_read_routes.py:606-617` SELECT + response 加 `exit_reason` | GUI passthrough 🔵 | ✅ 修 |
| (d) `live_session_account_routes.py:387-409` 同步加 `exit_reason` | live tab 平倉清單 | ✅ 修 |
| (e) `agent-tracker.js:530` shadow_fill summary 渲染 `<strategy> (<exit_reason>)` | XSS 安全經下游 ocEsc | ✅ 修 |

**邊界守住**：未動 16 emit 點動態 strategy_name（W1-T2 範圍）/ V033 schema / Rust writer / healthcheck / risk_config / strategy params / live 5 hardguard。

---

## §2 修改清單

| 檔案 | 增 / 修 / 刪 | 行數 | 一句話說明 |
|---|---|---|---|
| `program_code/exchange_connectors/bybit_connector/control_api_v1/app/strategy_read_routes.py` | 修 | +25 / -7 | `get_recent_fills_from_pg` SELECT 加 `exit_reason` 欄位（兩 branch：symbol-filter + non-filter）+ response cols extend + 雙語 docstring 引述 W1-T3 設計指針 |
| `program_code/exchange_connectors/bybit_connector/control_api_v1/app/live_session_account_routes.py` | 修 | +12 / -1 | `get_live_fills` DB-primary path SELECT 加 `exit_reason` + tuple destructure 加變數 + response dict 加 key + 雙語 inline 注釋 |
| `program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/js/agent-tracker.js` | 修 | +14 / -3 | shadow_fill summary 條件渲染 `<strategy> (<exit_reason>)`，free-text 經下游 line 580 `ocEsc(e.summary)` XSS 安全 |
| `program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_strategist_history_routes.py` | 修 | +186 | 3 新 unit tests 釘 7d edge effect 等值匹配契約（post-T2 SUM=10.5 / pre-T2 baseline=0 / 5 enum 全覆蓋）|
| `program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_strategy_read_routes_fills_exit_reason.py` | 新 | +234 | 4 新 hermetic tests：SELECT contract / response shape / symbol-filter branch / DB unavailable fail-closed |

**合計**：5 檔 / +471 / -11 = **net +460 LOC**（其中 ~210 LOC 為新 tests + 雙語 docstring；business logic ~50 LOC）。

---

## §3 關鍵 diff

### 3.1 `strategy_read_routes.py` SELECT 加 exit_reason（GUI passthrough）

```python
# Before：9 columns
"SELECT ts, fill_id, symbol, side, qty, price, fee, realized_pnl, strategy_name "
"FROM trading.fills WHERE symbol = %s ORDER BY ts DESC LIMIT %s"

# After：10 columns（+ exit_reason）
"SELECT ts, fill_id, symbol, side, qty, price, fee, realized_pnl, strategy_name, exit_reason "
"FROM trading.fills WHERE symbol = %s ORDER BY ts DESC LIMIT %s"

# response cols extend
cols = [
    "ts", "fill_id", "symbol", "side", "qty", "price",
    "fee", "realized_pnl", "strategy", "exit_reason",
]
```

雙語 docstring 引述 PA design + W1-T3 設計指針。

### 3.2 `live_session_account_routes.py` 同步加（10-tuple destructure）

```python
# Before：8 columns
"SELECT ts, symbol, side, qty, price, fee, realized_pnl, strategy_name "
"FROM trading.fills WHERE engine_mode IN (%s, %s) ORDER BY ts DESC LIMIT %s"
for ts, symbol, side, qty, price, fee, rpnl, strategy in rows:
    ...

# After：9 columns
"SELECT ts, symbol, side, qty, price, fee, realized_pnl, strategy_name, exit_reason "
"FROM trading.fills WHERE engine_mode IN (%s, %s) ORDER BY ts DESC LIMIT %s"
for ts, symbol, side, qty, price, fee, rpnl, strategy, exit_reason in rows:
    ...
    fills.append({
        ...
        "strategy": strategy or "",
        "exit_reason": exit_reason if exit_reason else None,
        "category": cat,
    })
```

### 3.3 `agent-tracker.js` shadow_fill summary 條件渲染

```javascript
// Before
rows.forEach((f) => {
  entries.push({
    type: "shadow_fill",
    ...
    summary: (f.strategy_name || f.strategy || "") + " · " + (f.side || "")
      + " · qty " + (f.qty != null ? f.qty : "--"),
  });
});

// After
rows.forEach((f) => {
  const stratLabel = (f.strategy_name || f.strategy || "");
  const exitReason = f.exit_reason || "";
  const stratAndReason = exitReason
    ? stratLabel + " (" + exitReason + ")"
    : stratLabel;
  entries.push({
    type: "shadow_fill",
    ...
    summary: stratAndReason + " · " + (f.side || "")
      + " · qty " + (f.qty != null ? f.qty : "--"),
  });
});
```

XSS 安全：`e.summary` 在 line 580 渲染時走 `ocEsc(e.summary)`（已驗證），free-text exit_reason 含 `<>` / quotes 不會 break。

### 3.4 unit tests 釘契約（修前永遠 0 / 修後正確 SUM）

```python
def test_seven_day_edge_effect_aggregates_close_pnl_after_t2() -> None:
    """[W1-T3] Post-W1-T2 close fill strategy_name is the 5-enum entry name
    → equality-match catches close legs and SUM(realized_pnl) returns the
    real 7d outcome (was 0 pre-W1-T2)."""
    aggregate_row = (2, 10.5, 0.5, None, None)  # 1 entry + 1 close
    ...
    result, err = sh_module._fetch_effect_for_row(
        engine_mode="demo",
        strategy_name="grid_trading",
        applied_at_ms=1_700_000_000_000,
    )
    assert result["fill_count"] == 2
    assert pytest.approx(result["net_pnl"], rel=1e-9) == 10.5  # 修前永遠 0；修後 = 10.5
    assert "strategy_name = %s" in captured["sql"]  # SQL 仍是等值匹配
```

---

## §4 治理對照

- **CLAUDE.md §二 #1 單一寫入口**：✅ 不變，trading_writer.rs 仍是唯一入口；本任務只動 read path
- **#3 AI 輸出 ≠ 命令**：✅ 0 影響 lease / decision path
- **#4 策略不繞風控**：✅ risk_close path 0 動
- **#5 生存 > 利潤**：✅ HARD/DYNAMIC STOP 邏輯 0 改
- **#6 失敗默認收縮**：✅ exit_reason 為 NULL 時 GUI 不顯示 reason 後綴（safe fallback）；DB unavailable test 釘 503 fail-closed
- **#8 交易可解釋**：⭐ **直接強化** — fills endpoint 回應現含 strategy_name + exit_reason，operator 可在 UI 看完整 audit trail
- **§四 5 項 live 硬邊界**：✅ 0 觸碰（authorization / mainnet env / live_reserved 全保）
- **§七 跨平台**：✅ pure Python + JS；無平台特定；grep 5 修改檔 `(/home/ncyu|/Users/[^/]+/[^/]+/TradeBot)` 0 hit
- **§七 雙語注釋**：✅ 全部新增 docstring / inline comment 中英對照（`strategy_read_routes.py` docstring + `live_session_account_routes.py` inline + agent-tracker.js inline + 兩測試檔 module + per-test docstring）
- **§七 SEC-05 XSS**：✅ free-text exit_reason 經下游 ocEsc 渲染，安全
- **§九 文件大小**：兩 Python 檔均 <1200 line（strategy_read_routes.py ~720 / live_session_account_routes.py ~520）；test 檔 234 / 619 line 均合規

---

## §5 不確定之處

### 5.1 `agent-tracker.js:530` 對 shadow_fill 是否實際生效

shadow_fills 表（`learning.decision_shadow_fills`，V021）目前**沒有** `exit_reason` column；`f.exit_reason` 永遠為 `undefined` → `exitReason = ""` → 條件分支永遠走「只顯示 strategy」分支。**結論**：line 530 改動是**前向相容 stub** — 若未來 shadow_fills 也擴 exit_reason，渲染立即生效；當前不影響行為。

PA §1.2 line 530 標 GUI passthrough 🔵，未明確排除「目前無效但未來相容」是 OK；E2 review 可問是否要拿掉條件式（簡化）或保留（防範式）。

### 5.2 PA spec 函數名 `_compute_seven_day_edge_effect` vs 實際 `_fetch_effect_for_row`

PA §1.2 引述函數名 `_compute_seven_day_edge_effect`，實際代碼為 `_fetch_effect_for_row`（line 282-365）。E1 不修 PA design typo（避擴範圍），但 test 命名直接用實際函數，docstring 引述 PA design 段落 + 時間戳留 trail。E2 可選擇是否在 PA 設計報告補注。

### 5.3 主會話統一 commit 時 deploy 順序考量

W1-T3 的 Python / JS 改動**對歷史 fills 兼容**：
- 歷史 row `exit_reason = NULL`（V033 ADD COLUMN nullable，~263k row 自動填 NULL）
- W1-T2 未 land 時 close fill `strategy_name` 仍是 dynamic format → fills endpoint 回應的 `strategy` 欄位仍為 dynamic 字串、`exit_reason = NULL`，UI 仍可顯示但 cardinality 未壓
- W1-T2 land 後 close fill `strategy_name=enum` + `exit_reason=trace` → UI 顯示 `<strategy> (<reason>)`、cardinality 自然下降

**結論**：W1-T3 可獨立部署不依賴 W1-T2，但完整效果（cardinality 壓縮 + 7d aggregate 命中 close fills）需 W1-T2 同時 land。主會話 commit + push + Linux deploy 順序：W1-T2 先 → W1-T3 後即可。或同次 commit 一起 deploy。

### 5.4 跨平台 pytest dependency

Mac dev-only 環境**沒裝** fastapi / slowapi / psycopg2-binary，本次跑 pytest 前 `pip3 install` 補齊。**Linux trade-core 環境**已裝齊（驗證：fastapi 0.135.2 / pytest 9.0.2 / pytest-asyncio 1.3.0）。E4 在 Linux 跑 regression 應該沒問題。

---

## §6 Operator 下一步

### 6.1 E2 審查重點

1. **fills endpoint contract 改動**：
   - SELECT 多 1 column（`exit_reason`）；驗 column 存在於 V033 schema（已驗 W1-T1 commit `45bbe4d` 的 V033 idempotency 通過）
   - response shape 擴 1 key（`exit_reason`）；GUI 端是否已準備好處理 null？— `agent-tracker.js:530` 用 `f.exit_reason || ""` 已防 null
2. **unit tests 契約釘 vs RCA-fix**：
   - 3 新 tests 純粹釘住「修前永遠 0 / 修後正確 SUM」+「等值匹配仍是 SQL 主路徑」契約，**SQL 0 改動**（W1-T2 後 enum match 自動生效）
   - `test_seven_day_edge_effect_misses_pre_t2_dynamic_strategy_name` 反向 baseline test 是 regression防範 — 若 close path 將來回到 dynamic format，此 test 會 catch
3. **agent-tracker.js XSS**：line 530 `f.exit_reason` free-text 經下游 `ocEsc(e.summary)`（line 580），E2 可手 trace 確認 XSS 路徑乾淨
4. **跨平台 grep**：5 修改檔 `(/home/ncyu|/Users/[^/]+/[^/]+/TradeBot)` 0 hit ✅

### 6.2 主會話下一步

1. ✅ 等 W1-T2（並行）完成 → 主會話統一 commit W1-T1 + W1-T2 + W1-T3
2. ✅ 派 E2 審查（可走 §八 標準鏈：E2 → E4 regression → PM Sign-off）
3. ✅ E4 Linux 跑：
   - `pytest program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_strategist_history_routes.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_strategy_read_routes_fills_exit_reason.py -v`
   - 期望：23 + 4 = **27 / 0 failed**
4. ✅ 部署後驗：
   - GUI Learning tab 24h fills `cardinality(strategy_name)` 開始下降（W1-T2 effect）
   - fills endpoint curl 回應含 `exit_reason` 欄位（W1-T3 effect）

### 6.3 Mac CC 透過 SSH bridge 已做的驗證

- ✅ Mac 本地 `pip3 install fastapi slowapi psycopg2-binary pytest pytest-asyncio httpx` → 跑 hermetic mock-based pytest 27 / 0 failed
- ✅ Sample fills endpoint mock response 含 `exit_reason` 欄位（close fill: `"grid_close_long"`，entry fill: `null`）
- ✅ git status 確認改動範圍 = 5 檔，無越界 healthcheck / Rust / risk_config / live hardguard

### 6.4 需 operator 親自動手的步驟

無 — 本任務全部走 sub-agent 寫碼 + Mac 本地 pytest 驗證；不需 Linux interactive、不需 high-risk 授權。等 E2 / E4 / 主會話 commit + push + Linux deploy。

---

## §7 報告路徑

`srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-04-29--w1_t3_python_adapt_gui_exit_reason.md`

E1 IMPLEMENTATION DONE: 待 E2 審查
