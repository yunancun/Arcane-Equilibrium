# GUI Bybit-first PnL Refactor — Closure Archive

**Archived**: 2026-05-23 15:45 CEST
**Final status**: CLOSED / VERIFIED / ARCHIVED
**Operator decisions**: 1A2A3A
- Q1=A: 本 Sprint 只保留 response-field / GUI drift display; 不做 24h reconcile cron.
- Q2=A: 本 Sprint 不做 `/demo/wallet-truth`.
- Q3=A: backend 保留 4 種 `strategy_source`; GUI fold 成 operator 可讀 labels.

## Final Verification

Scope was re-audited adversarially after the initial GUI Bybit-first implementation. The final working tree closes the discovered gaps:

- Bybit cursor/signature now signs and sends the same canonical query string; `%3A/%2C` cursor values are not double-encoded.
- `/api/v1/strategy/demo/closed-pnl` enforces the requested time window, the official 7-day Bybit window limit, and cursor pagination.
- Bybit/cache/PG fallback/strategy enrichment work is no longer performed directly on the async route event loop.
- PG fallback now respects `start_time` / `end_time`, stays read-only, and returns data when the Bybit client is unavailable.
- Three Bybit failures within 60s expose `bybit_failure_count_60s` and `degraded_until_ms`; GUI shows the operator-contact degraded banner.
- `restart_all.sh` now gates engine/API on one shared `ENGINE_SOCKET`, exported consistently to engine and API.
- Legacy full connector baseline improved from `4171 passed / 21 failed / 12 skipped` to `4199 passed / 0 failed / 12 skipped`.

Verification run on Mac:

- `bash -n helper_scripts/restart_all.sh` — PASS
- `python3 -m py_compile strategy_ai_routes.py bybit_rest_client.py` — PASS
- `node --check app/static/common.js` — PASS
- Focused GUI/Bybit/restart matrix — `60 passed`
- Full connector suite — `4199 passed, 12 skipped, 440 warnings`
- Scoped `git diff --check` — PASS

Linux / origin sync verification:

- Mac source, `origin/main`, and Linux `trade-core` were aligned on the same source HEAD after push/pull.
- Linux syntax/static checks — PASS.
- Linux focused GUI/Bybit/restart matrix — `60 passed`.
- Linux full connector suite — `4201 passed, 10 skipped, 448 warnings`.
- Linux runtime restarted via `restart_all.sh --keep-auth`; `engine.sock` gate passed at `/tmp/openclaw/engine.sock`.
- Linux smoke: `GET /api/v1/system/startup-status` returned HTTP 200; unauthenticated `GET /api/v1/strategy/demo/closed-pnl?limit=1` returned expected HTTP 401; engine watchdog reported `engine_alive=true`.

Adversarial review:

- E2 re-review: PASS
- BB re-review: PASS
- E4 regression: PASS after `test_pnl_series` fixture repair; no remaining connector failures.

Remaining 12 skipped tests are environment/opt-in skips, not GUI Bybit-first PnL failures:

- Live PG replay/calibration E2E tests require `OPENCLAW_TEST_LIVE_PG=1` and DSN.
- Replay subprocess smoke requires `OPENCLAW_REPLAY_E2E_SMOKE=1`.
- Observer data tests require real observer data.
- Executor parity cap/max-pct tests depend on G3-08.
- Governance risk escalation is not available in this environment.

Accepted scope boundaries from 1A2A3A:

- No 24h drift cron in this sprint.
- No `/demo/wallet-truth` endpoint in this sprint.
- No wallet `cumRealisedPnl` 24h truth route in this sprint.
- PG `trading.fills` remains the audit/ML source and is not mutated by GUI Bybit-first reads.
- Drift is exposed through response/UI fields; persistent audit-row cron is a future carry-over, not an open blocker in this approved scope.

---

# GUI Bybit-first PnL Refactor — 臨時工程文件

**創建時間**: 2026-05-23 12:30 Berlin
**狀態**: Archived after final adversarial verification(see closure section above)
**整合來源**: PA 工程設計 + FA 功能稽核 + E5 API hung RCA + E1a GUI RCA + A3 UX audit
**Owner**: PM(整合) → E1 + E1a(實施) → E2 + A3(對抗 review) → E4(regression) → QA(部署簽收)

---

## 一、 背景與根因(已驗證,不重新調查)

### 1.1 觸發事件
operator 在 GUI demo tab 看 OPUSDT 顯示 **-18.38 + -41.03 USD 兩筆「巨額虧損」** → 數據驗證後發現是 GUI 算法 hallucination,真實 Bybit 數據只 -2.61 USD。

### 1.2 三重 root cause(已驗證)

| Layer | Root Cause | 證據 |
|---|---|---|
| **GUI PnL 計算** | `tab-demo.html:710-751 _demoBuildProfitRows()` FIFO 配對演算法跨策略 / 跨日 / qty 雙重攤分 | E1a RCA + 真實 41 條 demo fills 模擬 confirm |
| **Backend query** | `strategy_ai_routes.py:1247` 只 query `engine_mode='demo'` 漏 `live_demo`(8 條)→ GUI FIFO 缺平倉 lot 雪崩 | grep + memory `engine_mode 標籤 live_demo 升級` |
| **GUI fail-silent stale** | 5 個 load* 函數 API timeout 時靜默 return,DOM 保留 9h 舊數據;`demo-badge` 單向粘綠 | A3 audit + operator F12 console TimeoutError 9h |
| **API hung 9h(同 incident)** | `restart_all.sh --rebuild` 不 wait engine.sock ready,API workers import strategy_wiring.py 時 ExecutorConfigCache IPC race | E5 RCA + 5/19 incident snapshot 相同 pattern |

### 1.3 驗證證據

**Bybit Demo `/v5/position/closed-pnl` endpoint 可用**:
- HTTP 200 retCode 0
- 30/30 records 全有效 closedPnl(0 null)
- OPUSDT 7 條 round-trip 全 valid:`-1.85 / -0.27 / -2.61 / +1.04 / -1.50 / -1.18 / +16.17` 合計 **+9.80 USD 淨盈利**
- 字段:qty / side / avgEntryPrice / avgExitPrice / closedPnl / openFee / closeFee / closedSize / fillCount / updatedTime / orderId / orderLinkId / leverage / execType / cumEntryValue / cumExitValue
- 數據保留 2 年,max 7 天 per query

**Secrets 路徑(已驗證)**:
- `/home/ncyu/BybitOpenClaw/secrets/secret_files/bybit/demo/api_key` (18B)
- `/home/ncyu/BybitOpenClaw/secrets/secret_files/bybit/demo/api_secret` (36B)

---

## 二、 架構決策(top-level)

| # | 決策 | 理由 |
|---|---|---|
| **D1** | **Bybit `/v5/position/closed-pnl` 為 round-trip PnL ground truth source** | exchange truth,刪 GUI FIFO bug 源 |
| **D2** | **PG `trading.fills` 為 audit trail + strategy_name 來源 + Bybit 故障 fallback**(不刪寫入) | 滿足 16 原則 #8 audit traceability + ML edge_estimator SoT(memory `feedback_demo_over_paper_for_edge`) |
| **D3** | **GUI 刪重算邏輯,純 render(zero computation in GUI)** | 治本,未來任何 fill 配對 bug 在源頭消失 |
| **D4** | **Cache layer 在 backend**(in-memory TTLCache 5-8s, per-process) | 16 原則 #14「baseline 不依賴外部付費服務」+ Bybit rate limit |
| **D5** | **PG 寫入永不被 GUI side effect 污染(ML SoT 不可反向改寫)** | FA P1 風險 — Bybit-PG drift 寫 audit log,不修 PG |
| **D6** | **只 profit sub-tab 切 Bybit-first;fill detail tab 維持 PG**(否則開倉 leg closedPnl=0 整批消失) | FA P0 風險 — Bybit execution endpoint 開倉腿無 closedPnl |

---

## 三、 4 Phase Deploy(嚴格順序 + 解耦)

### Phase 1: restart_all.sh race fix(獨立,純 bash)

**Scope**: helper_scripts/restart_all.sh 加 `wait_for_engine_socket()` helper
- `restart_engine` 後 polling unix socket connect 直到成功或 30s timeout
- 30s 不就緒 → fail-loud exit 3 + abort API restart
- 跟 Phase 2-4 完全並行

**LOC**: ~12 bash
**Owner**: E1
**Acceptance**:
- 跑 `restart_all.sh --rebuild`,輸出含 `>>> engine.sock ready after Nx500ms` 行(N=1-60)
- 故意 break socket(`mv engine.sock engine.sock.bak`)→ 30s 後 abort exit 3
- API 啟動後 0 條 `ExecutorConfigCache: IPC fetch failed before first init` warning
**Rollback**: 單 commit revert
**部署方式**: commit + 下次 deploy 自動生效(本次不觸發)

---

### Phase 2: Backend 新 endpoint + cache(獨立於 Phase 3)

**Scope**:
- 新 file `app/bybit_pnl_cache.py`(in-memory TTLCache,~80 LOC)
- 編 `app/bybit_rest_client.py` 加 `get_closed_pnl()` method(~50 LOC,參考 `get_executions` pattern)
- 編 `app/strategy_ai_routes.py`:
  - 加 `@phase2_router.get("/demo/closed-pnl")` endpoint(~120 LOC)
  - 修 `/demo/fills` line 1247:`engine_mode IN ('demo','live_demo')`(2 LOC)
- **strategy_name 4-tier reconcile**(FA P0-2 必補)— 見 §4.2

**新接口 spec**:
```
GET /api/v1/strategy/demo/closed-pnl
  Query params:
    limit:        int = 50 (1-200)
    offset:       int = 0
    start_time:   int ms? (default: now - 24h)
    end_time:     int ms? (default: now)
    symbol:       str? (filter)
    force_refresh: bool = false (跳 cache)
  Response:
    {
      "source": "bybit_api" | "bybit_cached" | "pg_fallback",
      "source_ts": int ms (數據採集時間,非 query 時間),
      "cache_age_seconds": float,
      "list": [
        {
          "symbol": str,
          "side": str,                    # 開倉方向(Bybit returns open side)
          "qty": float,
          "avg_entry_price": float,
          "avg_exit_price": float,
          "closed_pnl": float,            # ⭐ 核心 — Bybit truth
          "open_fee": float,
          "close_fee": float,
          "closed_size": float,
          "fill_count": int,
          "updated_time_ms": int,
          "order_id": str,
          "order_link_id": str,
          "strategy_name": str,           # ⭐ PG reconcile 後填入
          "strategy_source": "pg_fill" | "pg_link_id" | "bybit_unknown" | "pg_missing_unknown_external"
        }
      ],
      "count": int,
      "has_more": bool,
      "next_offset": int?,
      "degraded_reason": str?            # 如 source != bybit_api,說明
    }
```

**Cache 策略**:
- Layer 1: per-process Python dict + monotonic ts + RLock,TTL **5-8s**(FA 推薦 3-5s 也可,我取 5s balance)
- key: hash((mode, limit, offset, start_time, end_time, symbol))
- in-flight dedup:相同 query 5s 內第 N 次 request 等第一次 result(不發 N 次 Bybit)
- Layer 2: PG `trading.fills` fallback when:
  - Bybit retCode != 0
  - Bybit timeout(8s)
  - Bybit rate limit 429(5 min cooldown)
- `force_refresh=true` 強制跳 cache + 加 200ms spinner UX(FA AC-13)

**LOC**: ~280 Python
**Owner**: E1
**Acceptance**:
- AC-1: backend Bybit OK 時 response source="bybit_api"
- AC-2: Bybit 故障 → source="pg_fallback" + degraded_reason 揭露
- AC-3: cache hit → source="bybit_cached" + cache_age > 0
- AC-12: 4 worker × 30s refresh 下 peak 請求 ≤ 0.5 req/s(Bybit IP 限 120 req/s)
- AC-14: live_demo engine_mode 不 fallback Bybit(只 demo)
- AC-17: 24h 累積 sum(closedPnl) vs wallet.cumRealizedPnl ± 1%
**Rollback**: 移 endpoint + revert engine_mode IN clause(2 commit revert)
**部署方式**: `restart_all.sh --keep-auth`(Python hot reload,不 --rebuild)

---

### Phase 3: Frontend PnL render(依賴 Phase 2 部署完成)

**Scope**:
- `tab-demo.html`:
  - **刪 `_demoBuildProfitRows()` L710-751(治本)**
  - **刪 `_buildDemoStratMap()` L507-520(strategy hack)**
  - 加 `_demoBuildProfitRowsFromBybit(closedPnlList)` render 函數(~40 LOC)
  - `loadDemoFills()` profit sub-tab 切 `/api/v1/strategy/demo/closed-pnl`(fills sub-tab **維持** `/demo/fills` PG path,FA P0-1)
  - per-fill PnL 顯示 PG `realized_pnl` 加 ⚙ icon(engine-calc),round-trip 顯示 Bybit `closed_pnl` 加 ✅ icon(exchange-confirmed)— FA 推薦 #3

**LOC**: -75 / +80 = 淨 +5 LOC(刪 bug 大於加新)
**Owner**: E1a
**Acceptance**:
- AC-1 bit-exact: GUI round-trip PnL == Bybit response[i].closed_pnl(無 GUI 再算)
- AC-7: per-row guard 拒 engine_mode 不對 row
- AC-8: 翻頁超 7d → 顯黃色 "Bybit 僅留 last 7d · 點此載入 PG 歷史"(FA U-FA-6)
- AC-18: hover round-trip row 顯 entry/exit orderLinkId(operator 可手動 Bybit Web UI cross-verify)
- node --check 通過
- 對 OPUSDT 5212 qty round-trip 顯 **-2.61 USD**(不是 -41.03)
**Rollback**: 單 commit revert(GUI hash bust 自動拉舊版)
**部署方式**: `restart_all.sh --keep-auth` + GUI 強制 hash cache bust(`?v=20260523.bybit-first`)

---

### Phase 4: GUI UX 防呆(可並行 Phase 3,獨立)

**Scope**:
- `tab-demo.html` + `common.js`:
  - **stale banner**(資料 > 30s 黃,> 120s 紅)+ visual decay class `.oc-stale`
  - 每 metric 加 timestamp 角標(`d-equity` / `d-net` / `d-realized` 旁顯 `12:34:56` + > 30s 變灰)
  - **`loadDemoStatus` 失敗時加 visual decay**,不靜默 return
  - **`demo-badge` 強制可降級**(刪 L407 `if (!_demoConnectedOnce)` 守門)
  - GET 失敗也彈 toast(限頻 30s dedupe,連續 3 次彈 persistent banner)
  - 消費後端 `pipeline_status`(後端已 expose 但前端未用)
  - engine-calc vs exchange-confirmed PnL 加 ⚙/✅ icon + tooltip
- `common.js`:
  - **`ocStartRefresh` 加 in-flight guard**(防 setInterval reentry)
- `tab-system.html`:
  - **`loadQuickStatus` + `loadBusiness` sequential await → `Promise.allSettled` parallel**

**LOC**: ~150 JS / HTML
**Owner**: E1a
**Acceptance**:
- AC-5: strategy reconcile fail → 灰字 "unknown · pre-restart"(永不顯紅)
- AC-9: PG-Bybit drift > 0.10 USD → ⚠ icon + "PG-Bybit 差 D USD · click for detail"
- AC-10: 累計 net PnL 公式明示 "= sum(closedPnl)(已扣費)"
- AC-13: 立即刷新 → invalidate cache + 200ms spinner
- 模擬 API hung 60s → banner 變紅,恢復後綠
- ocApi GET 失敗 → 限頻 toast 出現
**Rollback**: 三 file 各自獨立 revert
**部署方式**: `restart_all.sh --keep-auth` + GUI cache bust

---

## 四、 關鍵 spec 補充(FA 6 必補)

### 4.1 `BybitClient.get_closed_pnl()` method spec(FA #1)

```python
# In app/bybit_rest_client.py, 仿 get_executions() pattern

def get_closed_pnl(
    self,
    category: str = "linear",
    symbol: str | None = None,
    start_time: int | None = None,
    end_time: int | None = None,
    limit: int = 50,
    cursor: str | None = None,
) -> dict:
    """Get closed PnL from /v5/position/closed-pnl.

    Returns: {"list": [...], "nextPageCursor": str | None, "category": "linear"}
    Raises: BybitError on retCode != 0
            BybitCredentialsMissing if api_key/secret unset
    """
    params = {"category": category, "limit": str(min(max(limit, 1), 100))}
    if symbol: params["symbol"] = symbol
    if start_time: params["startTime"] = str(start_time)
    if end_time: params["endTime"] = str(end_time)
    if cursor: params["cursor"] = cursor
    return self._signed_get("/v5/position/closed-pnl", params)
```

- 使用 cursor pagination(Bybit 返回 `nextPageCursor`,非 offset)
- 7d 限制 enforce by params(start_time / end_time ≤ 7d)
- Test fixture mock 對齊 `tests/test_bybit_rest_client.py` 既有 pattern

### 4.2 strategy_name 4-tier reconcile(FA P0-2 必補)

```
Tier 1 (pg_fill): SELECT strategy_name FROM trading.fills
                   WHERE order_id = bybit.orderId
                     AND engine_mode IN ('demo', 'live_demo')
                   LIMIT 1
                 — 命中即返回

Tier 2 (pg_link_id): orderLinkId 解析「oc_close_mf_fb_dm_TS_N」/「oc_dm_TS_N」/「oc_risk_dm_TS_N」前綴
                      → 反推 OpenClaw 內部 owner_strategy(需 paper_state map snapshot)
                    — pg_fill 缺時嘗試

Tier 3 (bybit_unknown): orderLinkId 不是 OpenClaw 格式(operator 手動下單 / 別系統)
                        → strategy_name = "external_manual"
                      — Tier 2 失敗

Tier 4 (pg_missing_unknown_external): PG race window 內 fill 沒寫入
                                       → strategy_name = "unknown_pending"
                                     — 三 tier 全失敗
```

**Frontend 顯示**:
- Tier 1 真名 + tooltip "from PG fill match"
- Tier 2 真名 + tooltip "(從 orderLinkId 反推)" + 灰字
- Tier 3 "external_manual" + tooltip "(交易所手動下單)"
- Tier 4 "unknown" + tooltip "(PG 寫入延遲)" + 灰字
- **永不顯紅 alert(避免恐慌)**

### 4.3 PG drift detection(FA #4 + AC-9)

每 24h cron job(獨立 cron,不在 GUI tick path):
```sql
INSERT INTO learning.governance_audit_log (event_type, payload, ts)
SELECT
  'pnl_source_drift',
  jsonb_build_object(
    'symbol', f.symbol,
    'order_id', f.order_id,
    'pg_realized_pnl', f.realized_pnl,
    'bybit_closed_pnl', b.closed_pnl,
    'diff_usd', ABS(f.realized_pnl - b.closed_pnl),
    'diff_pct', ABS(f.realized_pnl - b.closed_pnl) / NULLIF(ABS(b.closed_pnl), 0)
  ),
  NOW()
FROM trading.fills f
JOIN bybit_closed_pnl_cache b ON f.order_id = b.order_id
WHERE ABS(f.realized_pnl - b.closed_pnl) > 0.10
  AND f.ts > NOW() - INTERVAL '24 hours';
```
- threshold: < 0.10 USD OK / 0.10-1.00 WARN(log only)/ > 1.00 CRITICAL(banner alert)
- **本 Sprint 不 IMPL cron**(carry-over to Sprint 5+),只 land response field `pnl_source_drift_pct` 供 GUI 顯示

### 4.4 PnL source 三欄位拆分(FA #3)

GUI 顯示精度:
- **預設**: `displayed_pnl` = Bybit closed_pnl(Phase 3 後)
- **hover tooltip**: 顯示 `pg_engine_pnl`(PG 內部 ledger)+ `bybit_closed_pnl`(Bybit 真實)+ `diff_usd`
- diff > 0.10 USD → metric 旁 ⚠ icon

### 4.5 PG 寫入 invariant(FA P1 + D5)

**明文條款**:
> GUI Bybit-first 重構**不修改 PG `trading.fills` 任何 INSERT / UPDATE / DELETE 邏輯**。 Bybit 數據顯示為 read-only proxy,PG 寫入路徑(Rust trading_writer.rs)完全獨立。 任何 Bybit-PG drift 寫 audit log,**絕不反向修 PG**(ML SoT 不可污染)。

驗證:
- E2 review 必 grep code 改動,confirm 0 個 INSERT/UPDATE/DELETE trading.fills
- E4 regression 對比 deploy 前後 PG row count ± 5% 內

### 4.6 「立即刷新」UX(FA AC-13)

- demo tab 「成交歷史」表上方加 「🔄 立即刷新」按鈕
- 點擊 → backend `force_refresh=true` 跳 cache + 重發 Bybit
- 必有 200ms spinner UX feedback(避免 operator 不確定有沒有觸發)
- debounce: 連點 5 次 in 2s 後端只 issue 1 次 Bybit request

---

## 五、 18 條 Acceptance Criteria(FA 完整列表)

```
[AC-1]  Given operator 打開 demo tab profit sub-tab,
        When backend 從 Bybit /v5/position/closed-pnl 拉成功,
        Then GUI 顯 round-trip PnL = response[i].closed_pnl bit-exact(無 GUI FIFO 再算)

[AC-2]  Given Bybit closed-pnl 返 retCode != 0 或 503,
        Then GUI 顯紅 banner「Bybit 不可用 · 顯示 PG 估值 X」,
        fallback 標 source=pg_fallback,page 不空白

[AC-3]  Given cache hit (age < 5s),
        Then GUI 顯數字旁灰字「snapshot Ns 前 · age=2s」,
        cache age > 8s 自動 invalidate

[AC-4]  Given strategy_name reconcile success(Tier 1 pg_fill 命中),
        Then 策略 column 顯真名 + tooltip「from PG fill match」

[AC-5]  Given strategy_name reconcile fail(全 4 tier 失敗),
        Then 顯灰字「unknown · pre-restart」+ tooltip,不顯紅 alert

[AC-6]  Given operator 連點 refresh 5 次 in 2s,
        Then 後端只發 1 次 Bybit request(debounce + in-flight dedup)

[AC-7]  Given engine_mode=demo tab,
        Then GUI 100% 不顯任何 engine_mode IN ('live','live_demo','paper') 的 row;
        per-row guard 即使 backend 漏 filter 也不漏

[AC-8]  Given operator 翻頁到第 N+1 頁但 Bybit cursor 7d 邊界外,
        Then 顯黃色「Bybit 僅留 last 7d · 點此載入 PG 歷史」,
        不靜默切空白

[AC-9]  Given PG trading.fills.realized_pnl 與 Bybit closedPnl 差 > 0.10 USD,
        Then 後端寫 audit row 'pnl_source_drift',
        GUI 顯 ⚠ 旁邊「PG-Bybit 差 D USD · click for detail」

[AC-10] Given Bybit closed-pnl 無 fee 欄位(per API spec),
        Then 「累計 net PnL」公式明示「= sum(closedPnl)(已扣費)」,
        GUI legend 一行字標

[AC-11] Given GUI 走 Bybit-first,
        Then PG trading.fills INSERT 不降頻不停寫(edge_estimator 60min cron 不破);
        E4 regression 驗 PG row count 與部署前 ± 5% 內

[AC-12] Given 4 GUI worker × 1 user × refresh interval = 30s,
        Then peak Bybit closed-pnl 請求率 ≤ 0.5 req/s(5s cache 後),
        遠低於 Bybit IP 120 req/s 上限

[AC-13] Given operator 點「立即刷新」按鈕,
        Then cache 強制 invalidate + 新請求 + 顯 age=0s + spinner ≥ 200ms

[AC-14] Given LiveDemo engine_mode='live_demo',
        Then GUI demo tab 顯示(與 demo 共表),不因 endpoint 降級 auth/TTL/風控

[AC-15] Given Bybit closed-pnl 連續 3 次 fail in 60s,
        Then SM-04 ladder 不升級(GUI fail ≠ trading impair),
        但 GUI 顯紅 banner「Bybit 不可用 5 min · contact operator」

[AC-16] Given GUI 重構後保持 read-only,
        Then grep '/v5/position/closed-pnl' 在 backend 必出現 GET only;
        從 GUI 任何按鈕無法觸發 POST /v5/order/* 路徑(E3 regression)

[AC-17] Given 賬戶概覽用 closedPnl 累積,
        Then 與 wallet-balance.cumRealisedPnl 24h 內 ± 1% 對賬通過

[AC-18] Given operator hover round-trip row,
        Then tooltip 顯 entry_orderLinkId / exit_orderLinkId / Bybit response.symbolId,
        operator 可手動 cross-verify Bybit Web UI
```

---

## 六、 File 改動清單(全絕對路徑 + LOC)

| File | Phase | 改動類型 | LOC | Owner |
|---|---|---|---|---|
| `srv/helper_scripts/restart_all.sh` | 1 | Edit | ~12 | E1 |
| `srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/bybit_pnl_cache.py` | 2 | **New** | ~80 | E1 |
| `srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/bybit_rest_client.py` | 2 | Edit(加 `get_closed_pnl`) | ~50 | E1 |
| `srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/strategy_ai_routes.py` | 2 | Edit(加 endpoint + 修 L1247 IN clause) | ~150 | E1 |
| `srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/tab-demo.html` | 3+4 | Edit(刪 FIFO + 加 render + UX) | -75/+200 = 淨 +125 | E1a |
| `srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/common.js` | 4 | Edit(ocStartRefresh guard + stale banner helper) | ~50 | E1a |
| `srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/tab-system.html` | 4 | Edit(loadQuickStatus parallel) | ~30 | E1a |

**總計 ~600 LOC**(7 file)
- Backend ~280 LOC(Phase 2)
- Frontend ~205 LOC(Phase 3+4)
- restart_all ~12 LOC(Phase 1)

---

## 七、 Open Questions(等 operator 拍板)

### Q1: Reconcile alert IMPL 範圍
PA 推薦:本 Sprint 只 land `pnl_source_drift_pct` response field;**reconcile cron job carry-over to Sprint 5+**
FA 推薦:本 Sprint 同 IMPL 24h cron(+4 hr 給 Backend)
**我推薦**: PA 路徑(本 Sprint 不 IMPL cron,只埋 response field;Sprint 5+ 補 cron)
**理由**: 本 Sprint scope 已大,cron 是 nice-to-have,response field 已足以前端顯示 drift

### Q2: `/demo/wallet-truth` endpoint(改 wallet equity 也走 Bybit)
PA 推薦:延後到 Phase 5(本次只動 closed-pnl)
**我推薦**: PA 路徑(本 Sprint 不做 wallet-truth)
**理由**: wallet equity 顯示 acceptable(後端 paper_state + PG aggregate),focus closed-pnl 一個 endpoint 降風險

### Q3: strategy_source 4 種 vs 2 種(FA 4-tier vs PA 簡化)
PA 提 4 種:`pg_fill / pg_link_id / bybit_unknown / pg_missing_unknown_external`
FA 也是 4 tier
**我推薦**: 4 種(GUI 顯示 fold 為 2 種:真名 vs 灰字「unknown/external」)
**理由**: backend 留 4 種精度給 audit;GUI UX 簡化 2 視覺類別

---

## 八、 跟既有 fix chain 解耦驗證 ✅

| 既有部署 / 進行中工作 | 影響 | 證據 |
|---|---|---|
| ma_crossover NEARUSDT Phase A min_n=15 fix(已 deploy)| ✅ 不破壞 | GUI display path ≠ Rust signal pipeline |
| ma_crossover NEARUSDT 1978 deny 觀察期 | ✅ 不破壞 | cost_gate 在 Rust,GUI 不寫 |
| Phase B Rust low-sample 深負 arm(已 deploy)| ✅ 不破壞 | Rust binary 不重建 |
| funding_arb 1B EDGE-DIAG-2 收樣本 | ✅ 不破壞 | fills 仍 INSERT PG,edge_estimator 仍 SELECT |
| edge_estimate_snapshots 每小時 cron | ✅ 不破壞 | cron 直查 `trading.fills`,跟 GUI 解耦 |
| AC-11 + D5 invariant | ✅ guard | PG 寫入永不被 GUI 觸發改寫 |

---

## 九、 Risk + Rollback

### 風險評級

| Risk | Severity | Mitigation |
|---|---|---|
| Bybit API rate limit 429 撞牆 | LOW | 5s cache + 4 worker × 30s = 0.5 req/s,遠低於 120 req/s |
| Bybit 故障時 GUI 完全沒數 | MEDIUM | PG fallback + stale banner |
| strategy_name reconcile 全失敗 | LOW | Tier 4 灰字 "unknown",不顯紅 |
| PG 寫入降頻破 ML edge_estimator | **HIGH** | D5 invariant + AC-11 regression test |
| 開倉 leg closedPnl=0 整批消失 | **HIGH** | D6 只 profit sub-tab 切,fill detail 維持 PG |
| 多 worker cache 不一致 | LOW | per-process cache,差異 < 5s 可接受 |
| restart_all.sh fix race 漏掉某 thread | LOW | E5 設計含 30s timeout fail-loud,跑前 5/19 incident pattern 對照 |

### Rollback 路徑

| Phase | Rollback |
|---|---|
| 1(restart_all)| 單 commit revert,純 bash |
| 2(backend)| 2 commit revert(endpoint + IN clause),restart_all --keep-auth |
| 3(frontend render)| 單 commit revert,GUI hash bust 自動拉舊版 |
| 4(UX)| 三 file 各自獨立 revert |

---

## 十、 部署順序 + 時間估算

```
T0: PA design DONE (已完成)
T0: FA audit DONE (已完成)
T0: PM 整合 GUI-TODO (本 file)
T0+0:30: operator approve 3 Open Q + sign off GUI-TODO

T0+0:30 → T0+8h:
  Phase 1 (E1, 1h) ──┐
  Phase 2 (E1, 4h)  ─┼── 並行
  Phase 3 (E1a, 2h)  ─┘  (Phase 3 等 Phase 2 部署完才能上,但 code 可並行寫)
  Phase 4 (E1a, 3h)  ─── 並行 Phase 3

T0+8h → T0+9h:
  E2 + A3 並行 review (1h)

T0+9h → T0+9.5h:
  E4 regression test (0.5h)

T0+9.5h → T0+10h:
  Deploy:
    Phase 1: commit(不部署,下次自動)
    Phase 2: restart_all --keep-auth(Python hot reload)
    Phase 3: restart_all --keep-auth + GUI hash bust
    Phase 4: 同 Phase 3 一起部署

T0+10h → T0+11h:
  operator hard refresh GUI 驗 OPUSDT 顯 -2.61(不是 -41.03)
  24h 觀察期(QA)
```

**總時長**: ~10 hr(operator + E1 + E1a + E2 + A3 + E4 + QA)

---

## 十一、 Sign-off Table

| 角色 | 任務 | 狀態 | 完成時間 |
|---|---|---|---|
| PA | 工程設計 spec | ✅ DONE | 2026-05-23 |
| FA | 功能稽核 | ✅ DONE | 2026-05-23 |
| PM | 整合 GUI-TODO + 推薦 3 Open Q | ✅ DONE | 2026-05-23 12:30 Berlin |
| **operator** | **拍板 3 Open Q + approve GUI-TODO** | ⏳ Pending | — |
| E1 | Phase 1 + 2 寫 code | ⏳ Blocked by operator | — |
| E1a | Phase 3 + 4 寫 code | ⏳ Blocked by operator | — |
| E2 | adversarial review | ⏳ Blocked by E1/E1a | — |
| A3 | UX review | ⏳ Blocked by E1a | — |
| E4 | regression test | ⏳ Blocked by E2/A3 | — |
| QA | deploy + 24h 簽收 | ⏳ Blocked by E4 | — |

---

## 十二、 相關文件

- **PA design doc**: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-23--gui_bybit_first_pnl_refactor_design.md`
- **E5 API hung RCA**: 本 file §3.1 Phase 1 直接 reference
- **E1a GUI bug RCA**: 本 file §1.2 root cause 直接 reference
- **A3 UX audit**: 本 file §3.4 Phase 4 直接 reference
- **Bybit V5 closed-pnl API doc**: https://bybit-exchange.github.io/docs/v5/position/close-pnl
- **NEARUSDT cost_gate fix(已 deploy)**: TODO.md(主)
- **CLAUDE.md 第八節**: 工作流 chain `PM → PA → E1/E1a → E2 → E4 → QA → PM`

---

**本 file 為臨時工程文件,完成 deploy + 24h 簽收後可 archive 到 `srv/docs/archive/2026-05-23--gui_bybit_first_pnl_refactor.md`,主 `TODO.md` 加一條 archive reference 即可。**
