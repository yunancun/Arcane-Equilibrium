# QA E2E Acceptance — REF-20 Sprint A R3 Smoke E2E · 2026-05-04

**Verdict: BLOCK — R3 deploy 含 P0 FastAPI signature bug，R3 smoke 無法跑通；4 個 acceptance SQL counts 全 = 0；無 trading.fills leak（因為 register 立即 422 reject）但這非 fail-closed 設計成功，是 deploy 整體不可達**

**HEAD**: `66b650ea feat(replay): REF-20 Sprint A R3 — first real E2E evidence (writer + finalize)`

---

## §1 Phase 1-9 結果

### Phase 0 — Pre-flight check

| 項目 | 結果 | 證據 |
|---|---|---|
| API process alive (PID 700717) | PASS | `.venv/bin/python3 .venv/bin/uvicorn app.main:app --workers 4` |
| Engine alive (PID 700645) | PASS | `rust/target/release/openclaw-engine` running |
| `replay_runner` binary exists | PASS | `1758344 bytes 5月 3 21:31`（ctime/mtime 與 R3 commit 一致） |
| `openclaw-engine` binary exists | PASS | `25600800 bytes` |
| **`OPENCLAW_ENGINE_BINARY_SHA` env 在 API process** | **MISSING** | `/proc/700717/environ` 只有 `OPENCLAW_BASE_DIR / OPENCLAW_IPC_SECRET_FILE / OPENCLAW_DATABASE_URL_FILE / OPENCLAW_DATA_DIR`；無 `OPENCLAW_ENGINE_BINARY_SHA` |
| `/tmp/openclaw/replay_fixtures/` | MISSING | 不存在 |
| `/tmp/openclaw/replay_artifacts/` | MISSING | 不存在 |

### Phase 1 — 認證

| 步驟 | HTTP code | 結果 |
|---|---|---|
| `POST /auth/login` | 200 | `{"status":"ok","username":"398903348"}` |
| Cookie 建立（`oc_auth_token=knNHDvwYY...`） | OK | HttpOnly + 至 `2026-05-04+15d` |
| `GET /auth/check` | 200 | `{"authenticated":true}` |

**Phase 1 PASS**

### Phase 2 — Build register payload + 真實呼叫

Payload 完整對齊 `ReplayExperimentRegisterRequest` schema（透過 `cat`-write JSON file，避免 SSH heredoc quoting 問題）。

| 嘗試 | 方法 | 結果 |
|---|---|---|
| #1 curl `--data-binary @/tmp/r3smoke_register.json` | HTTP 422 | `{"detail":[{"type":"missing","loc":["query","body"],"msg":"Field required","input":null}]}` |
| #2 Python `urllib.request.Request` with explicit `Content-Type: application/json` + cookie | HTTP 422 | 同上 |
| #3 Python `requests` lib | HTTP 422 | 同上 |

**所有路徑都 422**。

### Phase 2.5 — Root cause diagnosis

**注意 422 detail**：`loc=["query","body"]` — FastAPI 把 body parameter 當作 Query string parameter，而 query string 沒提供 → 422 missing。

#### Trigger 1：`/openapi.json` HTTP 500 並暴露 PydanticUserError

```text
File "fastapi/_compat.py", line 231, in get_definitions
    field_mapping, definitions = schema_generator.generate_definitions(...)
File "pydantic/json_schema.py", line 363, in generate_definitions
File "pydantic/_internal/_mock_val_ser.py", line 41, in __getitem__
    return self._get_built().__getitem__(key)
File "pydantic/_internal/_mock_val_ser.py", line 58, in _get_built
    raise PydanticUserError(self._error_message, code=self._code)
pydantic.errors.PydanticUserError:
    `TypeAdapter[typing.Annotated[ForwardRef('ReplayExperimentRegisterRequest'),
    Query(PydanticUndefined)]]` is not fully defined; you should define
    `typing.Annotated[ForwardRef('ReplayExperimentRegisterRequest'),
    Query(PydanticUndefined)]` and all referenced types, then call
    `.rebuild()` on the instance.
```

#### Trigger 2：FastAPI dependant inspection

```python
# /api/v1/replay/experiments/register dependant:
body_params:  []
query_params: ['body']

# /api/v1/replay/run dependant:
body_params:  []
query_params: ['body']
```

**Body 真的被 misclassified 成 Query parameter。**

#### Trigger 3：Hermetic test 也 FAIL

```text
$ pytest tests/test_replay_experiments_register.py::test_register_minimal_payload_creates_row
FAILED — AssertionError: {"detail":[{"type":"missing","loc":["query","body"],"msg":"Field required","input":null}]}
assert 422 == 200
```

**Root cause**：

`srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/replay_routes.py`：

```python
1   from __future__ import annotations             # 全 file annotations 變 string forward refs
...
65      from replay import route_helpers as _rh    # try/except lazy import inside guard
71      from replay import experiment_registry as _er
...
188 ReplayExperimentRegisterRequest = _er.ReplayExperimentRegisterRequest  # module-level re-bind
...
337     body: ReplayExperimentRegisterRequest,     # FastAPI signature inspect 時 forward ref 無 typing context 可 resolve
```

`from __future__ import annotations` 把 `body: ReplayExperimentRegisterRequest` 變成 string `"ReplayExperimentRegisterRequest"`。FastAPI 在 route registration time 試圖 resolve 該 ForwardRef，但因為 `_er` 是 lazy import inside `try/except`，typing module 的 globals lookup context 看不到 `ReplayExperimentRegisterRequest` 的真定義。Pydantic ForwardRef 留 `_mock_val_ser` 占位 → FastAPI fallback 為「無法識別 BaseModel」→ 把 parameter 當 Query 處理。

**Verified**：在同 process 內 `from app.replay_routes import ReplayExperimentRegisterRequest` 後 `is BaseModel subclass: True` + `model_fields` 完整 — class 本身正確，只是 FastAPI signature inspection 沒能 resolve。

### Phase 3 — Fixture 確認（未執行）

`/tmp/openclaw/replay_fixtures/` 不存在。但因 Phase 2 已死，未必須建。

**根據 plan 指引「fixture 不存在時先停下來告訴 PM」+ 我發現的 P0 不在 fixture，是 routes signature**，**先 push back，不自行建 fixture**。

### Phase 4 — POST /run（未執行）

預期同 Phase 2 結果：422 body missing。已驗 dependant 將 body 誤判為 query。

### Phase 5 — replay_report.json 確認（未執行）

無 `RUN_ID` 可拿。

### Phase 6 — POST /finalize（未執行）

`/run/{run_id}/finalize` route dependant 顯示 `body_params: [], query_params: []` — finalize 沒 body 不受影響，但拿不到 `run_id`，仍走不完。

### Phase 7 — Sprint A R3 acceptance SQL

```sql
-- BASELINE (pre-test)
experiments=0
run_state=0
report_artifacts=0
simulated_fills=0
```

**4 個 count 全 = 0**，**未變化**。**Plan §6.R3 acceptance criteria 全 FAIL**。

### Phase 8 — Wave 9 safety SQL（執行）

```sql
trading_fills_15m=6  -- demo/paper 既有 6 row（pre-test baseline）
critical_replay_audit=NOT_QUERIED -- replay tables 全 0，無 audit log 可生成
```

**No live mutation leak**（此次「成功」是因為 register 在 fail-closed 之前已被 FastAPI 422 reject，**不是因為 governance 真的拒絕了 mutation**）。

### Phase 9 — FK lineage（未執行）

`replay.experiments` = 0 row，無 FK 可驗。

---

## §2 Plan §6.R3 acceptance verdict

| 標準 | 結果 |
|---|---|
| `replay.experiments > 0` | **FAIL** (= 0) |
| `replay.run_state > 0` | **FAIL** (= 0) |
| `replay.report_artifacts > 0` | **FAIL** (= 0) |
| `replay.simulated_fills > 0` | **FAIL** (= 0) |
| Wave 9 no live mutation | TRIVIALLY PASS（API 沒進到 mutation 點） |
| FK lineage | N/A |

**整體 R3 smoke E2E：FAIL — Sprint A R3 deploy 不滿足 plan §6.R3 acceptance**

---

## §3 故障排除過程

1. 環境 pre-flight：發現 `OPENCLAW_ENGINE_BINARY_SHA` env 缺、`/tmp/openclaw/replay_fixtures/` 不存在 → 預期 register 會 503 fail-closed
2. **實測卻 422 body missing**（不是 503）→ 顯示 register handler 根本沒執行到 `engine_binary_sha` check
3. SSH curl heredoc quoting 排除（用 `--data-binary @file`、Python `requests` 都同樣 422）
4. `/openapi.json` HTTP 500 暴露 `PydanticUserError: TypeAdapter[ForwardRef('ReplayExperimentRegisterRequest'), Query(PydanticUndefined)]` — **暴露 FastAPI 把 body 視為 Query**
5. FastAPI route dependant inspection 確認 `query_params: ['body']` + `body_params: []`（兩 routes register + run）
6. Hermetic test `test_register_minimal_payload_creates_row` 也回 422 missing body — **bug 不是 deploy-only，連 testclient 都掛**
7. 確認 root cause：`from __future__ import annotations` + `_er = ...` lazy import + module-level re-bind 三者組合，FastAPI signature inspection 無法 resolve forward ref

---

## §4 Sprint A 整體 verdict

**Plan §7 Sprint A**：

| Sprint A 目標 | 狀態 |
|---|---|
| A1 R0 hot fix | DONE（pre-R3 commit） |
| A2 R1 / R2 / R3 deploy & smoke | **R3 smoke FAIL — register/run body bug** |
| A3 V049 + V045 + report_artifacts row 寫入 | **FAIL — 4 表全 0** |
| A4-A10 | 留 Sprint B-D（per plan §11，不在本 verify 範圍） |

**Sprint A 結論**：**BLOCKED**。R3 commit `66b650ea` 通過 ssh deploy 進 Linux runtime，但 FastAPI signature inspection bug 導致 register/run endpoint 100% 422，**沒有任何 path** 能從 API 寫入 replay tables。Sprint A 不可結案。

---

## §5 PM 接手 commit 建議 + 後續 follow-up

### 立即修法（P0 BLOCKER）

**Option A（推薦最小改動）**：移除 `srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/replay_routes.py` 第 1 行 `from __future__ import annotations`。

理由：
- 該 file 充滿 `Optional / Tuple / Path / Any` 等需 typing 才合法的 annotations
- 但 file 也用 try/except lazy module import + module-level re-bind（line 188），FastAPI signature inspection 撞上 ForwardRef 無法 resolve
- 移除 `from __future__ import annotations` 會讓 annotation 成為 runtime-evaluated → FastAPI signature inspection 直接拿到 class 不是 ForwardRef
- 副作用：所有 typing forward refs 必為 runtime-resolvable（已可確認因為相關 import 都在 module top）

**Option B**：保留 `from __future__ import annotations`，改用 `BaseModel.model_rebuild()` 在 module load 末尾顯式 rebuild，並移除 line 188 indirect re-bind，改成 direct import：

```python
from replay.experiment_registry import ReplayExperimentRegisterRequest
```

**Option C**：改用 `typing.Annotated[ReplayExperimentRegisterRequest, ...]` 同時 `__future__.annotations` 不影響（更工程化）。

### 立即驗證

修完後跑：
```bash
cd /home/ncyu/BybitOpenClaw/srv/program_code/exchange_connectors/bybit_connector/control_api_v1
.venv/bin/python -m pytest tests/test_replay_experiments_register.py -v
```

預期所有 9 case PASS（per `_DUMMY_ENGINE_SHA = "0" * 64` autouse fixture 已 mock env）。

### 部署後重跑 R3 smoke

修完 + restart_all 後，重做這份 sign-off：
1. **必先 export `OPENCLAW_ENGINE_BINARY_SHA`** 給 API process（restart_all 之前）
2. **必先建 `/tmp/openclaw/replay_fixtures/btc_1m_smoke.json`**（schema 確認 per fixture_loader.rs：`{"schema_version": 1, "source": "s3_synthetic", "events":[...]}`）
3. 重跑 Phase 1-9

### Sprint A round-2 sign-off SOP

R3 deploy commit 必須 enforce「`tests/test_replay_*` 全 PASS」作 commit pre-merge 條件。本次 `66b650ea` 跳過了測試 baseline 驗證直接 ship。

---

## §6 Linux runtime state

| 項目 | 狀態 |
|---|---|
| API process PID 700717 | alive (4 workers) |
| Engine PID 700645 | alive |
| `replay.experiments` count | 0（pre-test = 0，post-test = 0） |
| `replay.run_state` count | 0 |
| `replay.report_artifacts` count | 0 |
| `replay.simulated_fills` count | 0 |
| `trading.fills last 15min` | 6（demo/paper 既有，與 replay 無關） |
| `learning.governance_audit_log replay_*` last 15min | 未產生（API 在 audit emit 之前 422）|
| `paper_trading_pipeline` | alive |
| `live_demo_trading_pipeline` | alive |

---

## §QA Acceptance Output

| 階段 | 證據 | 狀態 |
|---|---|---|
| 5 階段業務鏈 — 市場數據 | bybit_listener alive | N/A（不在本驗收範圍） |
| 5 階段 — H0/H1-H5/5-Agent/Decision Lease | (Sprint A 範圍 = replay lab，不影響 live 鏈) | N/A |
| 雙進程 E2E（API + replay subprocess） | API alive，subprocess **未能 spawn**（卡在 register 422） | **FAIL** |
| 5 hard gate（Phase 6 Live） | (本驗收非 Live 升級 gate) | N/A |
| 7d 灰度（Sprint A 結束 7d） | (Sprint A 才開頭，未進 7d 觀察) | N/A |

---

# QA E2E ACCEPTANCE DONE: BLOCK · report path: /Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/QA/workspace/reports/2026-05-04--ref20_sprint_a_r3_smoke_e2e.md

## BLOCKER 清單

1. **P0 — `replay_routes.py` body parameter 被 FastAPI 視為 Query (register + run, 2 routes)**
   - 修法：見 §5 Option A/B/C（推薦 A — 移除 line 1 `from __future__ import annotations`）
   - 驗證：`pytest tests/test_replay_experiments_register.py` 全 PASS + 重跑 R3 smoke 後 4 表 count > 0
   - Owner：E1（implement）+ E4（test PASS）+ QA（重跑本 sign-off）
   - Block 範圍：所有 R3 smoke E2E 必先此 fix 才有意義

2. **P1 — Sprint A R3 deploy commit 跳過了 hermetic test PASS gate**
   - `pytest tests/test_replay_experiments_register.py` 在 commit `66b650ea` 上 fail，但仍 ship
   - 修法：CI / pre-commit hook enforce
   - Owner：PM（policy）+ E4（CI）

3. **P2 — `OPENCLAW_ENGINE_BINARY_SHA` env 未注入 API process**
   - 影響：即使 P0 fix 後，register 還會 503 `engine_binary_sha_not_provisioned`
   - 修法：`restart_all.sh` / systemd unit / env file 加 `OPENCLAW_ENGINE_BINARY_SHA=$(sha256sum .../openclaw-engine | cut -d' ' -f1)`
   - Owner：E1 + E4

4. **P2 — `/tmp/openclaw/replay_fixtures/` 不存在 + 無 sample fixture**
   - 影響：即使 P0/P2 fix 後，/run 會 `FixtureNotFound`
   - 修法：建 `btc_1m_smoke.json`（schema per `fixture_loader.rs`），存 `srv/research_notes/replay_fixtures/`，restart 時 cp 到 `/tmp/openclaw/replay_fixtures/`
   - Owner：PA（fixture 內容）+ E1（路徑 mount）

---

## QA push back

我**沒有自行修 P0**（FastAPI signature bug 屬業務代碼），**沒有自行建 fixture**（policy: PA 撰寫）。先 push back PM 取得：

(a) 確認上面 Option A/B/C 哪一個是 PM 接受的 fix path
(b) 是否合並 P2 fixture + ENGINE_BINARY_SHA env 修整成同一次 R3 redeploy
(c) 是否需要把「register hermetic test 全 PASS」加進 future commit gate（PM policy）

**Sprint A R3 不可結案；R3 smoke E2E BLOCKED 直至 P0 修復 + 重跑此驗收**
