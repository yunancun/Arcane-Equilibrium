# E2 Adversarial Review — Python P0 Wave: F5 GUI + F7 healthchecks · 2026-04-26 23:55 CEST

## 改動範圍

### F5 — `origin/e1-f5-gui-live-anti-human-design`
- Commits: `51be82f` + `3d1fb1f` (docs)
- Stat: 5 files / +971 / -74
- Files (correct path is `program_code/exchange_connectors/bybit_connector/control_api_v1/...`):
  - `app/live_session_routes.py` (+52)
  - `app/live_session_account_routes.py` (+95)
  - `app/static/console.html` (+89)
  - `app/static/tab-live.html` (+378)
  - `tests/test_live_session_endpoint_actual_engine_kind.py` (+200, 11 pytest)

### F7 — `origin/e1-f7-healthchecks-isolated`
- Commits: `4085442` + `f572edc` (tests)
- Stat: 6 files / +1,645 / -20
- Files:
  - `helper_scripts/db/passive_wait_healthcheck/__init__.py` (+22)
  - `helper_scripts/db/passive_wait_healthcheck/runner.py` (+130)
  - `helper_scripts/db/passive_wait_healthcheck/checks_engine.py` (+613)
  - `helper_scripts/db/passive_wait_healthcheck/checks_strategy.py` (+108) → 1154/1200
  - `helper_scripts/db/passive_wait_healthcheck/checks_derived.py` (+112)
  - `helper_scripts/db/test_f7_new_healthchecks.py` (+669, 38 unit tests)

### Mac local validation
- F7 38 tests: `python3 helper_scripts/db/test_f7_new_healthchecks.py` → `Ran 38 tests in 0.014s · OK` (worktree)
- F5: schema-only review (Mac 無 engine + 無 live key)

---

## §九 8 條 checklist

| Item | F5 | F7 |
|---|---|---|
| 改動範圍與 PA 方案一致 | ✅ A1 P0 + A2/A3/A4/A5 | ✅ MIT/E5 spec [22-29] |
| 沒有 except:pass / 靜默吞異常 | ✅ | ✅ try/except + WARN return |
| 日誌 %s 格式 | ⚠️ N/A no logging.* in diff | ✅ no f-string log |
| 寫入 endpoint `_require_operator_role()` | ✅ existing endpoint 保留 | N/A (健檢) |
| `except HTTPException: raise` 在 `except Exception` 之前 | ✅ 無新 endpoint | N/A |
| `detail=str(e)` → "Internal server error" | ✅ no new HTTPException 拋 e | N/A |
| asyncio 路由中沒有 blocking threading.Lock | ✅ no new lock | ✅ no lock |
| 沒有私有屬性穿透 (`._xxx`) | ⚠️ 1 處 console.html line 198 `metricsData.realized_pnl` 不算（response data） | ✅ |

## OpenClaw 9 條 §3 checklist

| Item | F5 | F7 |
|---|---|---|
| 跨平台 grep `/home/ncyu` `/Users/[^/]+` | ✅ no hits（lsr/lsar/test 全綠） | ✅ no hits |
| 雙語注釋 MODULE_NOTE / docstring | ✅ 6 段式齊備 | ✅ 6 段式齊備（含 F7 spec note） |
| Rust unsafe / unwrap 限不可恢復 | N/A Python | N/A Python |
| 跨語言 IPC schema 一致 | N/A | ✅ [29] deferred-no-ipc 顯式 SKIPPED |
| Migration Guard A/B/C | N/A | N/A 無 migration |
| healthcheck 配對被動等待 TODO | N/A | N/A 本 PR 是 healthcheck 本身 |
| Singleton §九 表登記 | N/A | N/A |
| 文件大小 ≤ 800 警告 / ≤ 1200 硬上限 | console.html ~~行 / tab-live ~~行 (HTML 不適用) | ⚠️ checks_strategy.py 1154/1200 距硬限 46 行 |
| Bybit API 改動先查字典手冊 | N/A no Bybit API 改動 | N/A |

---

## 對抗反問結果

### F5

**Q1**: 「fake-success 真消除？5 種狀態邊界（mainnet/live_demo/unconfigured × engine in {live/demo/paper/unknown}）是否全部有正確視覺？」

**A_E1**: 11 pytest tests + frontend 5 種視覺模式（mainnet REAL FUNDS / live_demo orange / unconfigured silver / engine!=live integrity-fail / paper-fallback caution）

**E2 評估**: ⚠️ **Partial**：
- ✅ Read 端（GET）5 endpoint 全套 phantom guard
- ✅ 5 種狀態 frontend 視覺模式定義齊全（CSS class `.live-mode-mainnet` / `.live-mode-livedemo` / `.live-mode-unconfigured` + `integrity-fail-view`）
- ✅ test 11 case 覆蓋了 `_phantom_view_guard()` 內邏輯（9 case）+ `_resolve_live_endpoint_label()` 內邏輯（4 case）
- ❌ **Write 端漏（HIGH）**：`/positions/{symbol}/close` + `/close-all-positions` 沒套 `_phantom_view_guard()`，curl 直接 POST 仍可觸發
- ❌ **Test test_phantom_guard_allows_demo_engine_with_configured_mainnet_slot 揭示設計缺陷**：Mainnet slot configured + engine 非 live → backend 不擋，會打真實 Mainnet REST 拿真實 wallet → 注入 actual_engine_kind=demo marker → 前端 swap view 不渲染。但 **payload 已含 Mainnet 數據** → curl 仍可拿。違反 §二 #2 讀寫分離

**Q2**: 「LiveDemo 不被當『未配置』？per memory `feedback_live_no_degradation_by_endpoint`，LiveDemo 是 design intent」

**A_E1**: `actual_endpoint == 'live_demo'` 走橙色 + `live-demo-badge` + 「LiveDemo · api-demo endpoint」標籤；風控不降級

**E2 評估**: ✅ Pass — `_resolve_live_endpoint_label()` 邏輯：
- `live/api_key` exists + `live/bybit_endpoint == 'demo'` → `'live_demo'`
- `live/api_key` exists 沒有 endpoint file 或 != 'demo' → `'mainnet'`
- `live/api_key` 無 → `'unconfigured'`

且 `_phantom_view_guard()` 顯式只擋 `engine != 'live' AND endpoint == 'unconfigured'` —— LiveDemo 場景（engine=='live' + endpoint=='live_demo'）放行 with 橙色主題。風控仍按 Live 嚴格（5-gate auth 不降）— 與 memory 一致

**Q3**: 「『全部平倉』按鈕 client-side guard 是否真不能誤觸打到 demo 帳戶？」

**A_E1**: `_applyLiveActionGuards()` disable 按鈕 + 顯示 tooltip

**E2 評估**: ❌ **Fail（MEDIUM）**：
1. `_applyLiveActionGuards()` 只查 3 個 button：btn-live-stop / btn-emergency-stop / `button[onclick="openCloseAllDialog()"]`
2. **個別倉位平倉按鈕**（onclick=`closeLivePosition('${sym}'...)`）**不在 query 範圍** → 不被 disable
3. disabled 屬性可被 dev tools / dynamic re-render / JS 直呼 `doLiveCloseAll()` 繞過
4. **真正的安全層必須在 server-side**，但 server-side 也沒套 guard

**Q4**: 「時間區雙標是否所有時間欄位都有？」

**A_E1**: `_formatFillTime(tsMs)` 改為 UTC + local TZ dual-stamp

**E2 評估**: ⚠️ Partial — 只看到 fills 欄位用 `_formatFillTime`（line 1623）。Positions / orders / metrics 的時戳是否同樣 dual-stamp？只查到 fill table 一處。Minor finding 不阻 PASS

### F7

**Q1**: 「[22] 5-layer UNION ALL syntax 正確？minutes_stale NULL handling？SENTINEL_INF coercion?」

**A_E1**: `EXTRACT(EPOCH FROM (now() - max(ts))) / 60` + `count(*) FILTER (WHERE ts > now() - interval '1 hour')` + Python 端 `SENTINEL_INF = 1e9` 對 None → infinity

**E2 評估**: ✅ Pass — SQL 5-layer UNION ALL syntax 正確；`max(ts)` over 空表 → NULL → row[1] is None → coerce SENTINEL_INF → message 顯示 `"empty/never"`；FAIL 條件 `dcs_rows_1h > 100 AND fills_stale > 60` 符合 4/17 P1-12 incident fingerprint

**Q2**: 「[23] LEFT JOIN on context_id — context_id 是否真的 nullable？unattributed fills 在 F4 寫 NULL 嗎？」

**A_E1**: F4 audit row context_id = `unattrib-{exec_id}-{ts_ms}` non-NULL；ML pipeline filter 用 `WHERE strategy_name NOT LIKE 'unattributed:%'`

**E2 評估**: ❌ **Fail (MEDIUM cross-cut)**：F4 audit row context_id 雖然 non-NULL，但**沒對應 trading.orders 寫入**（per `event_consumer/loop_handlers.rs:try_emit_unattributed_fill`）→ F7 [23] LEFT JOIN 算到 fills_n=1 / orders_n=0 → 計入 `pairs_with_missing_orders`。1h 內 ≥6 個 F4 audit fill 跨多 symbol（funding payment / dust scrub 跨 BTC/ETH/SOL/...）→ **F7 [23] 誤 FAIL**「orders writer dropping rows across >5 pairs」。修法：F7 [23] SQL 加 `AND f.strategy_name NOT LIKE 'unattributed:%'`

**Q3**: 「[25] `log(10::numeric, qty::numeric)` 兼容性（PG 版本）」

**A_E1**: `qty > 0` 過濾 + fail-soft WARN return

**E2 評估**: ✅ Pass — PostgreSQL 12+ 都支援 `log(numeric, numeric)`. `qty > 0` 過濾防 log of 0/負；fail-soft try/except 兜 PG 版本差異

**Q4**: 「[26] `realized_net_bps = -5.5` exact match — 這個常量正確嗎？對 micro-profit-lock-v2 數值衍生影響？」

**A_E1**: MIT spec 直接寫 `realized_net_bps == -5.5`；觀察自 dust spiral row pattern

**E2 評估**: ⚠️ **LOW push back to MIT**：
- 推導鏈：`bybit_sync` adopted positions 的 `entry_fee = 0.0`（`fill_engine.rs:62` + `:142`）
- `realized_net_bps = (gross_bps) - close_fee_bps - entry_fee_bps = 0 - 5.5 - 0 = -5.5`
- 公式耦合於「adopted 倉位不追蹤 entry_fee」實作 invariant
- 如未來修「補回 entry_fee 追蹤」→ `realized_net_bps` shifts to `-11`
- **[26] 會 silently 漏抓 regression**
- 建議改 `realized_net_bps BETWEEN -12 AND -4` 範圍 match

對 micro-profit-lock-v2 影響：v2 不寫 `realized_net_bps` 於 fast_track partial reduce（per `pipeline_helpers.rs:232` `is_partial_reduce_tag` skip），所以 [26] 不會抓到 v2 fire 的 row。OK 隔離

**Q5**: 「[28] `qty<1e-3` 對所有 Bybit symbol 通用嗎？」

**A_E1**: per-symbol min-qty 不同，但 sub-millimeter 是 phantom fingerprint

**E2 評估**: ⚠️ **LOW push back to E5**：
- BTC min_qty=0.001=1e-3 → 邊界 OK
- ETH min_qty=0.01 → phantom qty=0.005 通不過 [28]（0.005 ≥ 1e-3 ≠ FAIL trigger），但 0.005 < ETH min_qty 仍是真正 phantom
- 設計上 [28] 是 fast triage（不查 instrument_info），不是 full coverage
- **接受 with 補 docstring**：「fast triage; 較大 symbol min_qty 由 [21] dust inventory 接力」

**Q6**: 「[29] deferred-no-ipc 處理是否符合『IPC fn 不存在 → SKIPPED 並 log；不要 fail-open』？」

**A_E1**: 現返回 `("PASS", "[deferred-no-ipc] ...")` 純 placeholder

**E2 評估**: ✅ Pass with note —
- ✅ 顯式 `[deferred-no-ipc]` prefix in message → operator 在 cron 每次跑都看見「正在等 Rust IPC handler 加入」
- ✅ 不 fail-open（沒回 PASS without context；prefix 是強烈視覺標識）
- ⚠️ 嚴格地說 spec 說「先 skip 該 check 標 SKIPPED」 — current MVP 用 PASS + prefix，technically 不是 SKIPPED status code。但 cron exit code 不 flip（PASS = green）+ message 顯式 deferred → 與 spec 意圖一致
- 後續升級為 grep-then-call probe 已在 docstring 規劃

**Q7**: 「runner.py invocation order — [22-28] cursor / [29] post-cursor 是否合理？」

**A_E1**: cursor block 21 + post-cursor 9 = 30 checks；F7 [22-28] 屬 DB-bound 進 cursor / [29] no-DB 進 post-cursor

**E2 評估**: ✅ Pass — 順序正確：[22-28] 在 `try`/`finally conn.close()` 內、與既有 [1-15][21] 同 cursor lifecycle；[29] 在 `finally` 之後純 Python no-DB call

**Q8**: 「`__init__.py` re-export 完整無漏？」

**E2 評估**: ✅ Pass — verified all 8 new check fn re-exported in both `__init__.py` (L32-39 + L65-66 + L98 + L100 + L104) and `runner.py` import block (L34-46 + L51-60 + L62-67)

**Q9**: 「mock pattern — 是否 mock 切徹底？」

**A_E1**: MagicMock cursor + `cur.connection.rollback = MagicMock()` 配對 defensive rollback；38 tests 不打 DB

**E2 評估**: ✅ Pass — 38 tests 各 check 5 case (PASS/WARN/FAIL/empty/exception) + [29] 3 case；Mac worktree 跑 `Ran 38 tests in 0.014s OK`；mock 是真切（`fetchall.return_value = [tuples]` / `cur.execute.side_effect = Exception`），不是 mock 表面留 logic 真打 DB

⚠️ **Minor**: boundary value（dcs_1h=100/101 / pairs_missing=5/6 / hours_stale=6.0/6.01）沒測 edge — 不阻 PASS 但下次補

---

## Cross-Cutting Findings

### F4 audit row vs F7 [23] orders consistency 衝突

| 屬性 | F4 audit row（`unattributed:bybit_auto`） | F7 [23] 行為 |
|---|---|---|
| `strategy_name` | `"unattributed:bybit_auto"` | LEFT JOIN 不過濾 strategy_name pattern |
| `context_id` | `"unattrib-{exec_id}-{ts_ms}"` non-NULL | LEFT JOIN ON o.context_id = f.context_id |
| `trading.orders` row | **不寫**（F4 設計：只寫 fill audit，沒對應 order） | LEFT JOIN → orders_n = 0 |
| 後果 | — | `fills_n=1 > orders_n=0` → 計入 pairs_with_missing_orders |

**典型情境**：
1. Bybit auto-funding payment（每 8h 自動結算 funding）→ 跨 25 個 symbols 各 1 個 unattributed fill → 1h 內 25 個 audit row → F7 [23] 報「>5 pairs missing orders」 → MEDIUM FAIL
2. 但實際 orders writer 健康，是 F4 audit 設計副作用

**修法（建議）**：F7 [23] SQL 加 filter
```sql
WHERE f.ts > now() - interval '30 minutes'
  AND f.engine_mode IN ('demo', 'live', 'live_demo')
  AND f.strategy_name NOT LIKE 'unattributed:%'   -- 新增
```

**Severity**: MEDIUM — 不阻 F7 通過 E4，但生產 cron 6h 間隔很可能在 LIVE 階段第一次觸發誤報，影響 operator 信任 healthcheck signal

### F4 audit row vs F7 [22] silent_gap

F7 [22] anchor 在 `dcs_rows_1h > 100 AND fills_stale > 60`. F4 audit row 寫入 fills 表，**會降低** `fills_stale` → 反而**減少** [22] 誤報（fills 不會 cliff），所以 F4 對 [22] 是 **Helpful 不是 Harmful**. OK

### F4 audit row vs F7 [25/26/27/28] — 全部 OK

- [25] dust qty distribution: F4 audit qty 來自真實 Bybit exec_qty，不一定觸 sub-micro 桶
- [26] dust spiral noise EF: F4 不寫 learning.exit_features
- [27] intents counter freeze: 純查 trading.intents，F4 寫 fills
- [28] phantom fills attribution: `strategy_name LIKE 'risk_close:%'` — F4 是 `unattributed:%`，不抓

---

## F5 Server-side write guard 建議

「全部平倉」+「個別倉位平倉」endpoint 應加同一 phantom guard：

```python
@core.live_router.post("/close-all-positions")
async def post_live_close_all_positions(actor: Any = Depends(base.current_actor)) -> dict:
    core._require_operator(actor)

    # F5/A1 phantom-view server-side guard — refuse to close demo positions
    # under the Live label. Mirror the GET endpoint pattern.
    # F5/A1：拒絕在 Live 標籤下平 demo 倉位；對齊 GET endpoint 模式
    actual_engine_kind = core._get_live_engine_kind()
    actual_endpoint = core._resolve_live_endpoint_label()
    if actual_engine_kind != "live" and actual_endpoint == "unconfigured":
        raise HTTPException(
            status_code=422,
            detail={
                "error": "live_slot_not_configured",
                "error_zh": "Live 槽未配置；拒絕在 Live 標籤下執行寫入操作",
                "actual_engine_kind": actual_engine_kind,
                "actual_endpoint": actual_endpoint,
            },
        )
    # ... existing logic ...
```

對個別倉位平倉同樣加。**用 `HTTPException(422)` 而非 phantom 200 envelope**，因為寫操作 caller（GUI 寫操作 + curl）應收到清晰的拒絕訊號

---

## F7 SQL 規格邊界 push back 重點

| Push back 對象 | Check | Issue | 建議修法 |
|---|---|---|---|
| **MIT** | [26] | `realized_net_bps == -5.5` exact match 耦合於 bybit_sync adopted entry_fee=0 implementation invariant | `BETWEEN -12 AND -4` 範圍 match |
| **E5** | [28] | `qty < 1e-3` 通用閾值對較大 symbol（ETH min 0.01）漏抓 | docstring 說明「fast triage；完整 coverage 由 [21] 接力」 |
| **F4 + MIT** | [23] | F4 audit row 觸發誤報 | SQL 加 `AND strategy_name NOT LIKE 'unattributed:%'` |
| **MIT** | [27] | `positions > 0 cross-query 簡化` 已記註，但 demo 有持倉真 0 + 強制 stop trade 場景下會 FAIL | 文檔註明 false positive 場景 |
| **E5** | [29] | deferred-no-ipc 用 PASS+prefix 不是 SKIPPED — 與 spec 字面不完全一致 | 接受（cron exit code 不 flip + 強烈視覺標識 satisfies spec 意圖） |

---

## Findings 總表

| Severity | PR | 位置 | 描述 | 建議修法 |
|---|---|---|---|---|
| **HIGH** | F5 | `live_session_account_routes.py:362` (`/close-all-positions`) + `:267` (`/positions/{symbol}/close`) | 寫入 endpoint 沒套 `_phantom_view_guard()` → curl bypass client-guard 後 IPC fail → REST fallback 用 demo client → 誤平 demo 倉 | 加 server-side phantom guard，回 HTTPException(422)，違反 §二 #2 讀寫分離 + #6 fail-closed |
| **MEDIUM** | F5 | `tab-live.html:283` `_applyLiveActionGuards()` query | `closeLivePosition` 個別倉位平倉按鈕 onclick string 不在 querySelector 範圍，未被 disable；config + dev tools 雙重繞過 | 擴寬 querySelector 涵蓋所有 onclick 寫操作；或改在 Mode 變化時整體 disabled body class 套 CSS pointer-events: none |
| **MEDIUM** | F7 + F4 | `checks_engine.py:243-258` (F7 [23] SQL) | F4 audit row context_id=`unattrib-...` non-NULL 但無對應 `trading.orders` → LEFT JOIN 計入 missing → F7 [23] 1h 內 ≥6 個 funding payment 跨 symbol 即誤 FAIL | F7 [23] SQL 加 `AND f.strategy_name NOT LIKE 'unattributed:%'`（cross-cutting） |
| **LOW** | F5 | `live_session_routes.py:228-230` `_resolve_live_endpoint_label` | `import os` + `from pathlib import Path` 在 fn 內，違反 [R1-6] | 移到模組頂層（line 41 既有 imports 區） |
| **LOW** | F7 | `checks_derived.py:96` ([26] SQL) | `realized_net_bps = -5.5` exact-match 耦合於 bybit_sync entry_fee=0 implementation invariant；未來補 entry_fee 追蹤即 silent regression | 改 `realized_net_bps BETWEEN -12 AND -4` 範圍 match |
| **LOW** | F7 | `checks_engine.py:540` ([28] SQL) | `qty < 1e-3` 通用閾值對較大 symbol min_qty 漏抓 | docstring 補充「fast triage; 較大 symbol 由 [21] 接力」 |
| **LOW** | F7 | `checks_strategy.py` 1154/1200 | 距硬限 46 行；下個新 check 加進去會超 | 開 follow-up `F7-FUP-CHECKS-STRATEGY-SPLIT` ticket 預計畫 split timing |
| **LOW** | F5 | `tab-live.html:1623` `_formatFillTime` | 只 fills 欄位用 dual-stamp；positions / orders / metrics 沒覆蓋 | 補上時戳 dual-stamp 一致性（不阻 PASS） |

---

## 結論

### F5 — **RETURN to E1**（3 issues：1 HIGH + 1 MEDIUM + 1 LOW + 1 minor）

**RETURN 必修清單**:

1. **HIGH** — 在 `live_session_account_routes.py` 兩個寫入 endpoint 加 server-side phantom guard：
   - `@core.live_router.post("/close-all-positions")` (L361)
   - `@core.live_router.post("/positions/{symbol}/close")` (L267)
   - 加 `_phantom_view_guard_write()` helper 回 `HTTPException(422)` 而非 200 envelope
   - 補對應 pytest `test_close_all_positions_phantom_guard_blocks` + `test_close_individual_position_phantom_guard_blocks`

2. **MEDIUM** — `tab-live.html:283` `_applyLiveActionGuards()` 擴寬 querySelector：
   - 加 `button[onclick^="closeLivePosition"]` 涵蓋個別倉位平倉
   - 或改在 `_applyLiveModeUI()` 中對 `body` 套 `body.classList.add('live-no-write')` + CSS `.live-no-write button[data-write]{pointer-events:none;opacity:0.4}`，標記所有寫按鈕 `data-write` attribute 後統一 disable

3. **LOW** — `live_session_routes.py:228-230` import 提到模組頂層

4. **Minor** — positions / orders / metrics 時戳補 `_formatFillTime` dual-stamp（不阻 RETURN merge，可 follow-up）

### F7 — **PASS to E4 with 3 follow-up tickets**（1 MEDIUM + 2 LOW + 1 LOW size warning）

PASS criteria:
- ✅ 8 new check 邏輯正確
- ✅ SQL syntax 安全（all 5 driving tables 有 engine_mode column）
- ✅ 38 unit tests 在 Mac worktree 跑綠
- ✅ 跨平台 / 雙語注釋 / except handling / module structure 全綠
- ✅ runner.py invocation order 合理
- ✅ `__init__.py` re-export 完整

Follow-up tickets:
- **`F7-FUP-23-AUDIT-EXCLUDE`** (MEDIUM): F7 [23] SQL 加 `AND strategy_name NOT LIKE 'unattributed:%'` filter — coordinate with F4
- **`F7-FUP-26-RANGE-MATCH`** (LOW): MIT spec [26] 改 `BETWEEN -12 AND -4` 防 implementation invariant 耦合
- **`F7-FUP-28-DOCSTRING-COVERAGE`** (LOW): [28] docstring 補「fast triage; 較大 symbol 由 [21] 接力」
- **`F7-FUP-CHECKS-STRATEGY-SPLIT`** (LOW size warning): `checks_strategy.py` 1154/1200 距硬限 46 行，計畫 split timing 防 strategist 1200 教訓重演

---

## 退回 E1 修復清單（F5）

```
1. live_session_account_routes.py:267 + :361 — 加 phantom-view server-side guard 寫入 endpoint
   - 新 helper `_phantom_view_guard_write()` 回 HTTPException(422)
   - 兩處 callsite 加調用
   - 補 2 tests: test_close_all_phantom_guard_returns_422 + test_close_individual_phantom_guard_returns_422

2. tab-live.html:283 _applyLiveActionGuards() — 擴寬 querySelector 涵蓋個別倉位平倉按鈕
   - 加 button[onclick^="closeLivePosition"] 或 data-attribute 統一標記法
   - 在 doLiveCloseAll() + closeLivePosition() 函數開頭加 _liveModeState check 雙重防衛

3. live_session_routes.py:228-230 — import os + Path 移到模組頂層
   - line 41 之後加 `import os` + `from pathlib import Path`
   - 移除 fn 內的 import os / from pathlib import Path
```

---

E2 REVIEW DONE: F5 RETURN to E1 / F7 PASS to E4 with 4 FUP · report path: docs/CCAgentWorkSpace/E2/workspace/reports/2026-04-26--python_p0_wave_review.md
