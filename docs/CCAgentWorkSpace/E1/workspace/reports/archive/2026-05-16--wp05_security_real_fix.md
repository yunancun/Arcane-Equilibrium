# WP-05 Security Hardening Real Fix — E1 Sign-off

Date: 2026-05-16
Task: WP-05 Real Fix (E2 + E3 RETURN to E1 from偽修復 `6b8be386`)
Status: IMPL DONE, awaiting E2 + A3 review
Branch: feature branch (uncommitted; PM 統一 commit + push per CLAUDE.md §七)

## 1. 任務摘要

Wave 1 WP-05 偽修復 (commit `6b8be386`) 用 global `@app.exception_handler(Exception)`
試圖統一消毒 500 leak，但 FastAPI 順位下此 handler **不** 攔截 `HTTPException` /
`RequestValidationError`，因此 25+ route 仍 `raise HTTPException(detail=f"...{exc}")`
路徑直接 leak `str(exc)` / `type(exc).__name__` / 文件路徑到 client。

本 Real Fix 三層防線：
1. 新建 `error_sanitize.py` helper（`sanitize_exc_for_detail` / `sanitize_exc_str`）
2. main_legacy.py 補 `StarletteHTTPException` + `RequestValidationError` handler 順位 + leak regex 偵測
3. 逐 route migrate 25+ 列名 callsite（per PA SoT）

OPENCLAW_DEBUG=1 startup warn 已加（不 fail-closed 以保 dev workflow）。

## 2. 修改清單

| File | Line(s) | 變更類型 |
|---|---|---|
| `app/error_sanitize.py` | new (~82 LOC) | 新檔 helper（中文 docstring） |
| `app/main_legacy.py` | imports L30-44 / handler block L380-440 | 加 `StarletteHTTPException` + `RequestValidationError` handler + DEBUG warn |
| `app/ipc_error_handler.py` | L100-125 / L162-184 | `raise_http_for_ipc_error` + `classify_ipc_exception` migrate |
| `app/live_session_routes.py` | L209 | `_ipc_command_route` IPC fallback |
| `app/live_trust_routes.py` | L972 / L995 / L1060 / L1090 | auth create + auth write × 2 路徑 |
| `app/strategy_ai_routes.py` | L156 / L437 / L487 / L574 / L921 / L944 / L1154 | Bybit balance/positions/orders/fills + IPC close/pause/resume |
| `app/executor_routes.py` | L632 | shadow-toggle IPC unavailable |
| `app/strategist_promote_routes.py` | L717 | promote apply IPC unavailable |
| `app/paper_trading_routes.py` | L223 / L281 / L303 / L708 / L728 | session start/pause/resume + close_all/close_position |
| `app/strategy_write_routes.py` | L107 | toggle_dynamic_risk IPC error |
| `app/strategy_read_routes.py` | L667 / L709 / L746 | PG fills/signals/features JSONResponse leak |
| `app/ml_routes.py` | L415 | model_registry import error |
| `app/live_session_endpoints.py` | L399 / L447 | live pause/resume IPC |
| `app/ai_budget_routes.py` | L205 | ipc client unavailable |
| `app/openclaw_routes.py` | L1218 / L1223 / L1292 / L1297 | proposal create + decide validation + store_unavailable × 2 |
| `app/layer2_routes.py` | L548 / L555 / L639 | provider_keys save validation/io + delete io |
| `app/layer2_tools.py` | L737 / L797 / L825 / L857 / L951 | call_tool / paper engine / decisions read / experience read / fetch_url |
| `app/governance_hub.py` | L356 / L1218 | trust state read + reconciliation error |
| `app/edge_estimator_scheduler.py` | L654 | promotion evidence push fail-open |

**Migrate 統計**：18 檔 / 38 callsite（含 ipc_error_handler 共 helper 解 1 處 → all 上游
caller，及 4 處 `reason_codes=[str(exc)]` 結構轉成標準 reason_code）。

## 3. Reason Code 對照表

| Scenario | reason_code | safe message (production) |
|---|---|---|
| IPC unreachable / disconnected | `ipc_unreachable` | `Engine unreachable` |
| IPC timeout | `ipc_timeout` | `Engine timeout` |
| IPC generic error | `ipc_error` | `Engine error` |
| Rust engine unavailable | `rust_engine_unavailable` | `Rust engine unavailable` |
| Auth create | `auth_failure` | `Authentication failed` |
| Auth write (authorization.json) | `auth_write_failure` | `Authorization write failed` |
| Bybit balance/positions/orders/fills | `bybit_api_failure` | `Exchange API call failed` |
| PG database error | `db_error` (via str fallback) | `Database error` |
| Pydantic 422 | `validation_failed` | `Validation failed` |
| ImportError / unmapped | `internal_error` | `Internal server error` |

## 4. 關鍵 diff snippets

### error_sanitize.py（新檔）
```python
def sanitize_exc_for_detail(exc, reason_code="internal_error") -> dict:
    safe_msg = _REASON_CODE_MESSAGES.get(reason_code, ...["internal_error"])
    if _DEBUG:
        exc_repr = f"{type(exc).__name__}: {str(exc)[:200]}"
        return {"reason_codes": [reason_code], "detail": f"{safe_msg} ({exc_repr})"}
    return {"reason_codes": [reason_code], "detail": safe_msg}
```

### main_legacy.py（HTTPException leak detection regex）
```python
_LEAK_PATTERN = re.compile(r":\s+\w*Error|:\s+\d+|Traceback|<class '")

@app.exception_handler(StarletteHTTPException)
async def _http_exception_handler(request, exc):
    detail = exc.detail
    if isinstance(detail, str) and not _OPENCLAW_DEBUG:
        if _LEAK_PATTERN.search(detail):
            detail = "Internal error"
    return JSONResponse(status_code=exc.status_code, content={"detail": detail})
```

Regex 9/9 自測 PASS（leak 5 種 pattern 命中、safe 4 種放行）。

### 典型 callsite migrate before/after
Before:
```python
except Exception as exc:
    raise HTTPException(status_code=502, detail=f"Bybit balance fetch failed: {exc}")
```
After:
```python
except Exception as exc:
    logger.exception("Bybit balance fetch failed")
    from .error_sanitize import sanitize_exc_for_detail
    raise HTTPException(
        status_code=502,
        detail=sanitize_exc_for_detail(exc, "bybit_api_failure"),
    )
```

## 5. 治理對照

| Rule | Status | Note |
|---|---|---|
| 不改硬邊界 (max_retries=0 等) | PASS | 未碰 |
| 注釋默認中文 (CLAUDE.md §七 2026-05-05) | PASS | helper docstring + inline 全中文 |
| 不改 business logic | PASS | 只動 exception → response detail 路徑 |
| 不改 secrets / config | PASS | 無 |
| 不 rebuild engine / restart | PASS | 純 Python |
| 不動 `helper_scripts/` | PASS | 無 |
| 不動既有 `_general_exception_handler` | PASS | 保留原 L365-379 邏輯 |
| 新檔 ≤ 80 LOC | NEAR | error_sanitize.py 82 LOC（spec 給 ~80 估算，內含 docstring 注釋；超 2 行屬 governance 邊界內可接受） |
| main_legacy.py 行數 | PASS | 494 → 556（800 warning 線 -244） |
| 不擴大 PA 範圍 | PASS | 只動 PA 證據列名 25+ callsite；其他 `str(exc)` 殘留留 sign-off 段落說明 |
| 跨平台合規 (CLAUDE.md §七 ★★) | PASS | 無 user-home 硬編碼；無 platform-specific 依賴 |

## 6. 殘留說明

PA 證據 list 標記 25+ callsite **全已 migrate**。

**未動 (per scope 限制)**：grep 結果發現 22 個 `str(exc)` / `str(e)` 殘留**不在** PA SoT 25+
列名內，但仍可能洩漏 — 屬「per-route design choices」（per WP-05 sign-off 範圍限制）：

| File:Line | 性質 | 風險評估 |
|---|---|---|
| `live_session_routes:591` | marker 字串 in-equality 比對（不 response） | 無洩漏 |
| `live_session_routes:634` / `strategy_ai_routes:711, 785` / `paper_trading_routes:481, 520` | `{"skipped": True, "reason": str(exc)}` IPC 子步驟 dict（混合返 client） | 中等 — 在 ipc_command result 子欄；GUI 可能讀到 |
| `strategy_ai_routes:635` | `_attach_owner_strategy` 內部 result dict | 低（內部處理鏈） |
| `live_trust_routes:346, 436, 883` | trust state / recommendation 分析 dict | 中等 — GUI tab-live 可見 |
| `paper_trading_routes:193` | `get_demo_summary` 內部 dict（**GUI summary endpoint**） | **中等 — GUI 直接讀** |
| `layer2_tools:472/535/581/630` | SearchResponse dataclass `error` 欄位 | 中等（LLM tool context） |
| `layer2_routes:506` | model_list_error 內部 dict | 低（admin 路徑） |
| `edge_estimator_scheduler:332/699/712/719/726/740` | scheduler 子任務 error dict（持久化日誌 + GUI 狀態端） | 中等 |

**建議**：下一個 WP / wave 加 P2 ticket：`P2-WP05-FUP-1` 涵蓋以上 22 處消毒，及 `ai_budget_routes:226`（`str(result["error"])` Rust IPC structured error — 不算 Python exc leak 但需評估）。

## 7. 自我驗證

```
py_compile (18 files) PASS
error_sanitize round-trip (prod + DEBUG): PASS
main_legacy import + 5 handlers registered:
  StarletteHTTPException: _http_exception_handler  ← NEW
  RequestValidationError: _validation_error_handler  ← NEW
  WebSocketRequestValidationError: (FastAPI default)
  RateLimitExceeded: _rate_limit_exceeded_handler
  Exception: _unhandled_exception_handler (kept)
_LEAK_PATTERN regex test: 9/9 PASS (5 leak detected + 4 safe放行)
tests/structure/: 36 passed in 0.12s
```

## 8. 不確定之處

1. **新檔 LOC 82 (spec 給 ~80)**：超 2 行屬必要（docstring 描述 WP-05 緣由 + reason_code
   字典清單）。若 E2 要求壓 ≤80，可移 docstring 第一段到 sign-off report，新檔可降至 79。
2. **`_LEAK_PATTERN` regex**：刻意保守（4 種 distinct pattern）；非常少數合法業務文案若
   含「`: 某錯誤`」可能誤命中（如 `Strategy 'foo' not found: timeout`）→ 會被替換成
   "Internal error"。production 影響：GUI 看到「Internal error」非精準文案，但比 leak 安全；
   DEBUG=1 模式下原樣放行不受影響。
3. **未動 22 處殘留**：scope 嚴格限制，已記第 6 節並建議 P2-WP05-FUP-1。
4. **layer2_tools internal dict 的 error key**：消毒後仍會進 LLM context，但 sanitize 後是
   safe message，無實質風險。

## 9. Operator 下一步

1. 派 @E2 對抗審查（重點驗 5 handler 順位 + leak regex + reason_code 表完整）
2. 派 @A3 安全審查（重點驗 25+ callsite 真實消毒 + 殘留 22 處風險評估）
3. 派 @E4 回歸測試（重點：tests/structure/ 已 PASS；可選加 unit test for sanitize helpers）
4. E2 + A3 + E4 都 PASS → PM 統一 commit + push

## 10. 影響總結

- **18 檔修改**（其中 main_legacy.py + error_sanitize.py + ipc_error_handler.py 是核心；
  16 檔 route 是 callsite migrate）
- **38 callsite migrate**（25+ PA SoT 全覆蓋 + 13 helper / 結構 callsite 連帶處理）
- **0 business logic 改動**
- **0 config / secrets / runtime 動作**
- **3 層防線**：helper + handler 順位 + per-callsite 消毒 = 不是 single point patch
- **DEBUG 路徑保留** for dev workflow（OPENCLAW_DEBUG=1 仍可 inspect 真實 exc）
- **5/5 handler 順位** 全部正確註冊
