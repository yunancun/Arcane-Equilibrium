# E1 IMPL — LG-1 T4 H0 Block Summary Operator Verification Route

Date: 2026-05-11
Owner: E1
Sprint: N+1 Wave 2.2
PA Plan: `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-11--lg_2_3_4_design_plan.md` §1.4 表 T4
Status: IMPL DONE — 待 E2 審查 + E4 回歸

---

## 1. 任務摘要

實作 PA tech plan §1.4 表 T4 給 operator 的 read-only 驗證端點 `GET /api/v1/paper/risk/h0_block_summary`。

提供：
- 跨 engine（paper / demo / live / live_demo）的 H0 hard-block 累計事件數
- 按 5 個 sub-check reason 分類（freshness / health / eligibility / envelope / cooldown）
- 窗口期 trading.fills 計數做 sanity check
- 頂層裁決 PASS / WARN / FAIL（規則內嵌 Pydantic Field description）

並行性：與 LG1-T1 (Rust e2e test) / LG1-T2 (healthcheck `[59]`) / LG1-T3 (SOP + ctor) 無檔案重疊，已並行 IMPL（per PA §1.4）。

---

## 2. 修改清單

| 檔 | 改動 | LOC |
|---|---|---|
| `program_code/exchange_connectors/bybit_connector/control_api_v1/app/risk_routes.py` | 末尾新增 — 2 Pydantic model + 5 helper + 1 route + module docstring 區段 | +410 (708→1118) |
| `program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_h0_block_summary_route.py` | **新檔** — 21 unit + route tests，PG/Snapshot 全 mock | +468 |
| `docs/CCAgentWorkSpace/E1/memory.md` | 末尾追加 LG-1 T4 工作紀錄 | +35 |

**未動**：H0 production code（h0_gate.rs / step_0_5_h0_gate.rs）、ipc_state_reader.py、db_pool.py、main.py（既有 `app.include_router(risk_router)` 自動覆蓋）、TOML/RiskConfig、TODO.md、CLAUDE.md。

---

## 3. 改動位置 + Pydantic Model

### 路由註冊

```python
@risk_router.get("/h0_block_summary", response_model=H0BlockSummaryResponse)
async def get_h0_block_summary(
    window_hours: int = 24,
    engine_mode: str | None = None,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
) -> H0BlockSummaryResponse:
    ...
```

`risk_router.prefix = "/api/v1/paper/risk"` → 實際路徑 `GET /api/v1/paper/risk/h0_block_summary`。

注：PA spec 寫 `/api/v1/risk/h0_block_summary`，但既有 `risk_router` prefix 是 `/api/v1/paper/risk`。**選擇遵從既有 router prefix 不另開新 router**（per PA T4 表「extend risk_routes.py」）。cross-engine 字段在 response body（engine_mode/engines[]）對 operator 透明，路徑 prefix 不影響語意。

### Pydantic Models

```python
class H0BlockSummaryEngineDetail(BaseModel):
    engine_mode: str                                  # paper/demo/live/live_demo
    h0_shadow_mode: bool | None                       # 該 engine 當前 shadow flag
    engine_available: bool                            # snapshot 是否新鮮 (<60s)
    h0_block_events_total: int                        # since engine boot
    h0_block_events_by_reason: dict[str, int]         # 5 sub-check counter
    h0_total_checks: int
    h0_allow_rate_pct: float
    fills_in_window: int                              # trading.fills count, windowed
    last_check_at_utc: str | None                     # snapshot.written_at_ms 近似
    health_status: str                                # PASS/WARN/FAIL per engine
    notes: list[str]                                  # 補充說明


class H0BlockSummaryResponse(BaseModel):
    window_hours: int
    engine_modes: list[str]
    engines: list[H0BlockSummaryEngineDetail]
    h0_block_events_total: int                        # 跨 engine 聚合
    h0_block_events_by_reason: dict[str, int]
    fills_during_block: int                           # by-design 恆為 0
    last_block_event_at_utc: str | None               # 最新 snapshot ts
    block_acceptance_pct: float                       # 100% = 理想
    health_status: str                                # 頂層 PASS/WARN/FAIL
    notes: list[str]
```

### 5 Helper（純函數，無副作用）

1. `_h0_reason_breakdown(gate_stats)` — 從 Rust GateStats dict 抽 5 sub-check counter + totals。
2. `_count_fills_in_window(engine_modes, window_hours)` — PG SELECT 計數窗口期 fills（參數化 SQL）。
3. `_per_engine_h0_summary(engine, fills_count, window_hours)` — 從 RustSnapshotReader 拉 snapshot + 合成 EngineDetail。
4. `_aggregate_h0_summary(engine_details)` — 跨 engine 聚合 total/by_reason/latest_ts。
5. `_top_level_verdict(engine_details)` — 頂層 PASS/WARN/FAIL 規則。

---

## 4. PA Spec 設計取捨（必告知 PM / E2）

### 4.1 `h0_block_events_by_strategy` 改名 `h0_block_events_by_reason`

**Why**：H0 gate 是 **pre-strategy** gate（per-symbol gate，跑在 `step_0_5_h0_gate.rs`，**早於** step_3_signals / step_4_5_dispatch），沒有 strategy 維度。`GateStats` 只記錄 5 sub-check counter（`blocked_freshness/health/eligibility/envelope/cooldown`），這 5 個對 operator 更有實用價值（哪類問題在阻擋 — data freshness？risk envelope？cooldown？）。

PA spec 寫 `by_strategy` 是語意誤判，已用 `by_reason` 覆蓋。

### 4.2 `fills_during_block` 改語意為「設計不變式恆為 0」

**Why**：H0 hard-block 在 `step_0_5_h0_gate.rs:43-94` 路徑早退（only `stops` processed, never `emit_fill`），所以「block 期間的 fill」by-design 不存在。原始 spec 字段恆為 0 是「invariant proof」，**非觀察量**。窗口期 fills 計數放在 `engines[].fills_in_window`。

### 4.3 `last_block_event_at_utc` 用 snapshot.written_at_ms 近似

**Why**：Rust `GateStats` 是 cumulative monotonic counter，**沒有 per-event timestamp**（看 `rust/openclaw_core/src/h0_gate.rs:60-71`）。無法精確還原「最近一次 block 何時」。退而求其次取 `pipeline_snapshot.written_at_ms` 作 `last_check_at_utc` 近似，並在字段 description 明文標示「近似」。None = engine 不可達。

### 4.4 路徑 prefix 用 `/api/v1/paper/risk/` 不另開 router

**Why**：既有 `risk_router.prefix = "/api/v1/paper/risk"`；PA spec 寫 `/api/v1/risk/` 但表 T4 明文「extend risk_view_client.py or risk_routes.py」。新開 router 增加 main.py wiring + 切割既有 risk 命名空間，得不償失。Operator GUI / curl 用 response body engine_mode/engines[] cross-engine 已涵蓋語意。

---

## 5. SQL 範本 + Linux PG 跑時間

### SQL

```sql
SELECT engine_mode, COUNT(*) AS n
  FROM trading.fills
 WHERE ts >= NOW() - (%s || ' hours')::interval
   AND engine_mode = ANY(%s)
 GROUP BY engine_mode
```

**參數化**：`(window_hours_str, [engine1, engine2, ...])` 透過 psycopg2 `%s` placeholder + tuple 防注入。

### Linux PG empirical dry-run (2026-05-11)

```
EXPLAIN (ANALYZE, TIMING) SELECT engine_mode, COUNT(*) AS n FROM trading.fills
 WHERE ts >= NOW() - ('24' || ' hours')::interval
   AND engine_mode = ANY(ARRAY['paper','demo','live','live_demo'])
 GROUP BY engine_mode;
```

QueryPlan：
- `Custom Scan (ChunkAppend) on fills` — TimescaleDB chunk-aware
- `Index Scan using _hyper_35_422_chunk_fills_ts_idx` — `fills_ts_idx`
- 6 chunks excluded during startup（TimescaleDB chunk pruning 工作）
- **Planning Time: 10.115 ms / Execution Time: 0.461 ms**

實測返結果：
```
 engine_mode |  n
-------------+-----
 demo        | 253
 live_demo   | 200
(2 rows)
```

24h window 顯示 demo + live_demo 都有 active trading，paper/live 0 fills（與 §三「paper 預設關閉 / live 真 mainnet 0 流量」一致）。SQL 跑時間遠 <1s warm（**符合 acceptance criterion 6**）。

---

## 6. pytest 結果

```bash
$ source venvs/mac_dev/bin/activate && python -m pytest \
  program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_h0_block_summary_route.py -v
```

**21 tests PASS in 0.40s**：

| Test | 驗證 |
|---|---|
| `test_h0_reason_breakdown_with_full_stats` | 完整 GateStats → 5 sub-check counter 對 |
| `test_h0_reason_breakdown_handles_missing_keys` | None / 空 dict 安全降級 |
| `test_aggregate_h0_summary_picks_latest_ts` | 跨 engine 聚合 last_check 取最新 |
| `test_top_level_verdict_all_pass` | 全 PASS → 頂層 PASS 100% |
| `test_top_level_verdict_any_fail_short_circuits` | 任一 FAIL → 頂層 FAIL 0% |
| `test_top_level_verdict_partial_warn` | 部分 WARN → 頂層 WARN 50% |
| `test_top_level_verdict_empty_input` | 無 engine → WARN 0% |
| `test_per_engine_summary_pass_hard_block` | shadow_mode=false + active checks → PASS |
| `test_per_engine_summary_warn_shadow_mode` | shadow_mode=true → WARN |
| `test_per_engine_summary_warn_unavailable` | snapshot 不可達 → WARN + engine_available=false |
| `test_per_engine_summary_live_demo_maps_to_live_snapshot` | live_demo → live snapshot mapping 正確 |
| `test_route_default_window_all_engines_pass` | 預設 24h + 全 engine PASS |
| `test_route_engine_filter_demo_only` | engine_mode=demo 篩選只回單 engine |
| `test_route_shadow_mode_warn` | 整 deployment shadow_mode → WARN |
| `test_route_engine_unavailable_warn` | snapshot None → WARN |
| `test_route_invalid_engine_mode_400` | mainnet → 400 |
| `test_route_invalid_window_hours_400` | 10000h / 0h → 400 |
| `test_route_response_schema_complete` | 所有 Pydantic 字段都在 JSON 出 |
| `test_route_unauthenticated_401` | 無 token → 401（auth gate 真實生效）|
| `test_route_pg_unavailable_graceful_degrade` | PG 不可用 → fills=0 + 200 不 5xx |
| `test_response_model_directly_constructible` | Pydantic schema 獨立 |

---

## 7. curl 範例 + Linux 實測

### 規格 example（待 commit + deploy 後實測）

```bash
curl -s -H "Authorization: Bearer $OPENCLAW_API_TOKEN" \
  "http://trade-core:8000/api/v1/paper/risk/h0_block_summary?window_hours=24&engine_mode=demo" | jq
```

**Expected response shape**（依 mock test schema 預估）：

```json
{
  "window_hours": 24,
  "engine_modes": ["demo"],
  "engines": [
    {
      "engine_mode": "demo",
      "h0_shadow_mode": false,
      "engine_available": true,
      "h0_block_events_total": 12,
      "h0_block_events_by_reason": {
        "freshness": 8,
        "health": 0,
        "eligibility": 2,
        "envelope": 1,
        "cooldown": 1
      },
      "h0_total_checks": 234567,
      "h0_allow_rate_pct": 99.99488,
      "fills_in_window": 253,
      "last_check_at_utc": "2026-05-11T08:42:13+00:00",
      "health_status": "PASS",
      "notes": []
    }
  ],
  "h0_block_events_total": 12,
  "h0_block_events_by_reason": {
    "freshness": 8, "health": 0, "eligibility": 2, "envelope": 1, "cooldown": 1
  },
  "fills_during_block": 0,
  "last_block_event_at_utc": "2026-05-11T08:42:13+00:00",
  "block_acceptance_pct": 100.0,
  "health_status": "PASS",
  "notes": [
    "GateStats 為累計 counter (since engine boot)，不帶 per-event ts；last_check_at_utc 取 snapshot.written_at_ms 作近似",
    "fills_during_block 是設計不變式 (恆為 0)；窗口期 fills 計數見 engines[].fills_in_window"
  ]
}
```

### 為何沒實際 Linux curl 結果

E1 規則：完成後等 E2 審查 + E4 回歸通過後 PM 統一 commit + push。**目前改動未 commit**，Linux trade-core 仍跑舊 risk_routes.py（無此路由）。實際 curl 必須等以下完成：

1. E2 代碼審查 PASS
2. E4 回歸測試 PASS（會驗 21/21 + 既有 risk_routes regress）
3. PM 統一 commit + push
4. `bash helper_scripts/restart_all.sh --keep-auth`（純 Python 改動，不需 `--rebuild`）
5. curl `/api/v1/paper/risk/h0_block_summary` 驗證 200 + JSON shape

**Linux PG SQL dry-run 已驗證**（§5）— SELECT 在 Linux PG 跑通且 0.461ms < 1s。pytest 21/21 PASS — 業務邏輯封閉驗證完。剩餘 = wire-up + auth + curl integration。

---

## 8. Self-check: 8 Acceptance Criteria

| # | Acceptance | 結果 |
|---|---|---|
| 1 | `python -m py_compile risk_routes.py / risk_view_client.py` 綠 | ✅ `py_compile PASS`（risk_routes.py 動，risk_view_client.py 未動）|
| 2 | `pytest tests/test_h0_block_summary_route.py -v` 3-5 test PASS | ✅ **21 tests PASS in 0.40s**（超過 3-5 target）|
| 3 | curl Linux runtime endpoint 返 JSON 正確 | ⚠️ **DEFERRED** — E1 不 commit；待 E2/E4/PM commit + deploy 後執行（Linux PG SQL 已驗 §5）|
| 4 | 注釋中文 | ✅ MODULE_NOTE + 所有新 helper docstring + inline 注釋全中文（per 2026-05-05 governance change）|
| 5 | read-only 純 SELECT | ✅ 唯一 PG 寫操作 = `SELECT engine_mode, COUNT(*) ... FROM trading.fills`；無 INSERT/UPDATE/DELETE/IPC patch |
| 6 | Response time < 1s warm | ✅ PG SQL 0.461ms（§5）+ snapshot file read ~few ms + serialize <10ms → **<100ms warm 估計**；mock pytest 21 test 全套 0.40s |
| 7 | 無 hardcoded path | ✅ 不引入新路徑常量；既有 `OPENCLAW_DATA_DIR` 透過 `RustSnapshotReader` 自處理；`_count_fills_in_window` 用 `get_pg_conn()` 共用 pool |
| 8 | Pydantic model schema 正確 | ✅ 21 test 其中 `test_route_response_schema_complete` + `test_response_model_directly_constructible` 雙重驗證；FastAPI `response_model=H0BlockSummaryResponse` 自動驗 |

---

## 9. 不確定之處

1. **`risk_routes.py` 1118 LOC > 800 警告線**（< 2000 hard cap）。CLAUDE.md §九 容許 pre-existing baseline exception，但此次新增不是 pre-existing。**建議 E2 評估是否要求 P3 拆檔** `h0_block_summary_routes.py` 為 sibling，或接受 warning。
2. **`h0_block_events_by_reason` 字段命名**：PA spec 寫 `by_strategy`。我覆寫為 `by_reason` 因 H0 是 pre-strategy gate（§4.1 解釋）。E2 / PA review 是否認同此覆寫，若不同意需回退並另開 ticket 為 H0 加 strategy 維度（要動 Rust h0_gate.rs）。
3. **`live_demo → live` snapshot mapping**：3E-ARCH live_demo 走 live pipeline + demo endpoint，pipeline_snapshot 仍寫 `pipeline_snapshot_live.json`。我在 `_per_engine_h0_summary` 加 `snapshot_engine = "live" if engine == "live_demo" else engine`。**若有 dedicated `pipeline_snapshot_live_demo.json` future commit**，此 mapping 需更新（建議 E2 確認當前無此分離）。
4. **`block_acceptance_pct` 計算規則保守**：當前 PASS=100% / partial WARN=50% / FAIL=0%。Operator 可能想要更細粒度的「per-engine PASS 比例」（如 3 engine 2 PASS 1 WARN → 66.7%）。當前 spec 沒明確要求；若 E2 / A3 想升級，需修 `_top_level_verdict` 邏輯（影響 acceptance test）。
5. **`window_hours` 上限 30 天**：用 `_H0_SUMMARY_MAX_WINDOW_H = 24 * 30 = 720` 防 unbounded SELECT。Trading.fills hypertable 有 chunk pruning，但 30d 仍可能 >10k rows；若 operator 真需 30d view，0.46ms PG 應可吃；若 E2 想更激進限制（如 7d），改常數即可。

---

## 10. Operator 下一步

1. **E2 review**：
   - 看 `risk_routes.py` 末尾 +410 LOC 設計取捨（§4.1-4.4 4 條 push back）
   - 認領 `_count_fills_in_window` SQL 參數化 + injection safety
   - 認領 `_per_engine_h0_summary` live_demo→live mapping 正確性
   - 評估是否要求 P3 拆檔 sibling `h0_block_summary_routes.py`

2. **E4 regression**：
   - 跑 `pytest program_code/exchange_connectors/bybit_connector/control_api_v1/tests/` 確 既有 risk_routes 測試（`test_risk_view_client.py` / `test_risk_governor_state_machine.py` 等）不破
   - 跑 `pytest program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_h0_block_summary_route.py -v` 確 21 tests
   - 跑 main.py import smoke `python -c "from app import main"` 確 `app.include_router(risk_router)` 不破

3. **PM commit + deploy**：
   - E2 / E4 通過後統一 commit + push
   - `ssh trade-core "cd ~/BybitOpenClaw/srv && git pull --ff-only origin main"`
   - `ssh trade-core "bash helper_scripts/restart_all.sh --keep-auth"`（純 Python，不需 --rebuild）
   - `curl -s -H "Authorization: Bearer $TOKEN" http://trade-core:8000/api/v1/paper/risk/h0_block_summary?engine_mode=demo | jq` 驗 200 + JSON
   - 若 health_status="PASS" 即 LG1-T4 sign-off

4. **與其他 LG-1 sibling 整合**：
   - LG1-T2 healthcheck `[59]` IMPL 完後，可在 `check_h0_block_acceptance()` 內 import 本 route 的 helper `_count_fills_in_window` + `_per_engine_h0_summary` 共用邏輯（避免雙寫）。建議 E2 通知 LG1-T2 owner。
   - LG1-T3 runbook 完後，可在 SOP 文檔加上 curl 範例（§7）作為 operator quick check。

---

## 11. 治理對照

| 治理 | 落地證據 |
|---|---|
| CLAUDE.md §二 16 原則 #2 讀寫分離 | ✅ 純 read-only / SELECT |
| CLAUDE.md §四 硬邊界 | ✅ 0 觸碰 max_retries / live_execution_allowed / execution_authority / system_mode |
| CLAUDE.md §五 架構 | ✅ 不改 H0 production code / 不改 IPC / Rust unchanged |
| CLAUDE.md §七 跨平台 | ✅ 0 硬編碼路徑（grep `/home/ncyu` / `/Users/ncyu` 在 risk_routes.py / test 文件 = 0 hit）|
| CLAUDE.md §七 中文注釋 default (2026-05-05) | ✅ 全中文 / MODULE_NOTE 段落 / docstring / inline |
| CLAUDE.md §七 SQL Linux PG dry-run mandatory | ✅ §5 Linux PG EXPLAIN ANALYZE 已驗 |
| CLAUDE.md §九 file size warn 800 / hard 2000 | ⚠️ risk_routes.py 1118 > 800 warn（E2 評估是否拆）|
| CLAUDE.md §九 singleton 表 | ✅ 0 新 singleton |
| 16 原則 #6 失敗默認收縮 | ✅ PG 不可用 → fills=0 fail-safe / engine snapshot 不可達 → engine_available=false WARN |
| 16 原則 #8 可解釋 | ✅ Response notes 字段內嵌「為何裁決如此」+「資料源限制」 |

---

E1 IMPLEMENTATION DONE: 待 E2 審查（report path: `docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-11--lg1_t4_h0_block_summary_route.md`）
