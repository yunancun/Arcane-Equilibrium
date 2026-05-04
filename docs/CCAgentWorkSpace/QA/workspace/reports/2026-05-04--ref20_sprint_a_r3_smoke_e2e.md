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

---

## §15 RETRY LOG — Round 2 (post-hotfix `cad8ed84`，2026-05-04 23:30+ UTC)

**Verdict: BLOCK 仍維持，但 BLOCKER 從 P0 (FastAPI 422) 降級到 P2 (env + fixture)；hotfix 確認有效，是真實的 deploy 半完成狀態**

### §15.1 Hotfix `cad8ed84` deploy verified

| 驗證項 | 結果 | 證據 |
|---|---|---|
| Linux 工作樹 git HEAD | `66b650ea`（落後 1 commit，origin/main `cad8ed84`） | `git rev-parse HEAD` |
| Linux 工作樹 uncommitted file | `replay_routes.py` 已移除 `from __future__ import annotations`（line 1） | `git diff` 顯示 `-from __future__ import annotations` |
| **uncommitted 內容是否等於 `cad8ed84`** | **YES（functionally equivalent）** | diff hunks 完全是 hotfix 相同 — line 1 移除 + module docstring 加 CRITICAL warning + Hotfix line 替換 Dispatch line |
| Linux origin/main has `cad8ed84` | YES | `git log --all` shows commit on origin |
| API process restart time | `2026-05-04 23:29:24` | `ps -o lstart` |
| API process picks up hotfix code | YES | `/openapi.json` HTTP 200（前次 PydanticUserError 500 已消失） |
| Hermetic pytest 5 file 集合（45 cases） | **45 passed** | `pytest tests/test_replay_*` 0 fail |

**重要 deploy 不一致**：Linux 是「working tree dirty pull-not-yet」狀態（工作樹有 hotfix uncommitted；origin/main 已有 `cad8ed84` 的 commit）。**這違反 git §七 commit 即 push + Mac→Linux pull 同步**規則。代碼層面行為等同 `cad8ed84`，但 git tracking 層面 Linux 沒進到 PM 宣稱的「HEAD `cad8ed84`」。

**功能層面結論：hotfix 有效，FastAPI 422 body misclassification 已解。**

### §15.2 Phase 1-9 結果（hotfix 後）

| Phase | 動作 | HTTP / SQL | 結果 |
|---|---|---|---|
| 1 — login | `POST /auth/login` | HTTP 200 + cookie | **PASS** |
| 2 — register | `POST /experiments/register` | **HTTP 503**（reason: `replay_engine_binary_sha_not_provisioned`） | **BLOCKED on env**（不再是 422 body 422 Query bug） |
| 3 — fixture probe | `/tmp/openclaw/replay_fixtures/` ls | 不存在；但有 `rust/openclaw_engine/tests/fixtures/replay_runner_e2e/synthetic_btcusdt.json`（10 events） | **fixture 待 PM 決策 reuse / 新建** |
| 4 — `/run` | (未跑：依賴 Phase 2) | N/A | N/A |
| 5 — `replay_report.json` 確認 | (未跑) | N/A | N/A |
| 6 — `/finalize` | (未跑) | N/A | N/A |
| 7 — 4-table acceptance SQL | `experiments=0 / run_state=0 / report_artifacts=0 / simulated_fills=0` | 全 = 0 | **FAIL（vs target > 0）** |
| 8 — Wave 9 safety SQL | `trading_fills_15m=2`（pre-existing demo activity）；`all_replay_audit_15m=0`；`all_audit_15m=48` | no replay leak; no critical replay audit | trivially PASS（沒進到 mutation 點） |
| 9 — FK lineage | (跳過：4 表全 0 沒 FK) | N/A | N/A |

### §15.3 Sprint A acceptance verdict

| Plan §6.R3 標準 | 結果 |
|---|---|
| `replay.experiments > 0` | **FAIL** (= 0) |
| `replay.run_state > 0` | **FAIL** (= 0) |
| `replay.report_artifacts > 0` | **FAIL** (= 0) |
| `replay.simulated_fills > 0` | **FAIL** (= 0) |

**整體 R3 smoke E2E：仍 FAIL — Sprint A R3 acceptance 4/4 全 0**

但 root cause 已從 P0（routes signature bug）降級到 P2（env + fixture infrastructure），這是真實進展。

### §15.4 Wave 9 safety + FK lineage

| Item | 結果 | 評估 |
|---|---|---|
| `trading.fills` 15m | 2 row（demo/paper 既有，與 replay 無關） | **PASS — no replay-induced live mutation** |
| `learning.governance_audit_log` 15m replay_* + critical | 0 | trivially PASS（API 在 audit emit 點之前 fail-close） |
| `learning.governance_audit_log` 15m total | 48 row | engine 治理鏈仍活躍（與 replay 無關） |
| FK lineage（experiments → run_state → report_artifacts/fills） | N/A（4 表全 0 沒可驗 FK）| 等 R3 smoke 跑通 redo |

### §15.5 故障排除（hotfix 後仍存在的 P2 BLOCKER）

#### P2-A — `OPENCLAW_ENGINE_BINARY_SHA` env 未注入 API process（已知 R2 round 2 M-3 fix）

- **驗證**：`/proc/726858/environ` 含 `OPENCLAW_BASE_DIR / OPENCLAW_DATA_DIR / OPENCLAW_DATABASE_URL_FILE / OPENCLAW_IPC_SECRET_FILE`，**無** `OPENCLAW_ENGINE_BINARY_SHA`
- **代碼面確認**：`replay/experiment_registry.py:748-755` (`os.environ.get("OPENCLAW_ENGINE_BINARY_SHA", "").strip() or None`) + `:956-965` (`linux_trade_core REQUIRES`) — 唯一注入路徑是 process env var
- **修法**：`helper_scripts/restart_all.sh::restart_api()` 加 `export OPENCLAW_ENGINE_BINARY_SHA=$(sha256sum rust/target/release/openclaw-engine | cut -d" " -f1)`，再 `bash helper_scripts/restart_all.sh --keep-auth`
- **engine binary SHA**：`38c72877e526bfede74d57e6c9a90a682d323a2f80a0a9eef0e547f4d048d2f1`（已驗）
- **per plan instruction** `這個 fix 上去前先 push back 給 PM，不要自己 patch restart_all.sh`：**未自行 patch，push back 給 PM**

#### P2-B — `/tmp/openclaw/replay_fixtures/btc_1m_smoke.json` 不存在

- **驗證**：`/tmp/openclaw/replay_fixtures/` 整個 directory 不存在
- **可重用 fixture**：`rust/openclaw_engine/tests/fixtures/replay_runner_e2e/synthetic_btcusdt.json`（10 OHLC events，schema_version=1，source=`s3_synthetic`，符合 `fixture_loader.rs::FixtureEnvelope`）
- **必要性檢查**：`route_helpers.py::build_default_manifest_payload` 顯示 `fixture_uri` default 是 `<output_dir>/fixture.json`，可由 `OPENCLAW_REPLAY_FIXTURE_URI` env 覆寫；**`manifest_jsonb.fixture_uri` 是 hint 不直接驅動 runner**。所以兩條路：
  - **Option F1**（推薦）：set env `OPENCLAW_REPLAY_FIXTURE_URI=/home/ncyu/BybitOpenClaw/srv/rust/openclaw_engine/tests/fixtures/replay_runner_e2e/synthetic_btcusdt.json`（同 P2-A 修 restart_all 加 export）
  - **Option F2**：cp test fixture 到 `/tmp/openclaw/replay_fixtures/btc_1m_smoke.json`（需 `mkdir -p` + restart 時補 cp）
- **per plan instruction** `如 fixture 真需要 + 不存在，停下來告 PM`：**未自行建 fixture，push back 給 PM**

### §15.6 PM 接手 commit + deploy 建議

#### 建議 1：清 git working tree（uncommitted change）

Linux working tree 有 hotfix 的 uncommitted edit，但 origin/main 已 commit `cad8ed84`。應該：
```bash
ssh trade-core 'cd ~/BybitOpenClaw/srv && git stash && git pull --ff-only && git stash drop'
```
（注：CC 不執行 stash/pull/reset，由 operator 或 PM 手動 issue）

或先讓 operator commit + push 該 hotfix 完成 git tracking 一致性（如果 Linux 那份是另一份獨立 patch；但 §15.1 比對顯示功能等同 → safe 用 stash drop）。

#### 建議 2：合併 R3 deploy infrastructure 為單次 PR/commit chain

```bash
# 修 helper_scripts/restart_all.sh::restart_api():
#   export OPENCLAW_ENGINE_BINARY_SHA=$(sha256sum "$REPO_ROOT/rust/target/release/openclaw-engine" | cut -d' ' -f1)
#   export OPENCLAW_REPLAY_FIXTURE_URI="$REPO_ROOT/rust/openclaw_engine/tests/fixtures/replay_runner_e2e/synthetic_btcusdt.json"
#   ⋯⋯ 原 uvicorn 啟動

# 啟動前 mkdir -p：
#   mkdir -p /tmp/openclaw/replay_artifacts /tmp/openclaw/replay_fixtures

# 完整 deploy chain：
ssh trade-core 'cd ~/BybitOpenClaw/srv && git pull --ff-only && bash helper_scripts/restart_all.sh --keep-auth'
```

#### 建議 3：CI/pre-commit gate enforcement

P1 commit `66b650ea` 跳過 hermetic pytest gate ship 已是 incident。R3 round 2/3 應加 commit gate：
```bash
# pre-commit hook (server-side or CI):
cd program_code/exchange_connectors/bybit_connector/control_api_v1
.venv/bin/python -m pytest tests/test_replay_*.py
```
任何 fail = block commit（CI）/ block merge（GitHub）。

#### 建議 4：Sprint A R3 round 3 retry plan

R3 round 3 = 上面 1+2+3 同 commit 一次 ship + redeploy + 重跑 §15.2 Phase 1-9，全綠後 Sprint A close。預計 1 task 1 sprint。

### §15.7 R3 smoke 完成後的 follow-up（B Sprint 啟動條件）

只在 Sprint A 真正 close（4 表全 > 0）後，Sprint B（R4=intent_processor stub + R5=full pipeline integration）才有 evidence 觸發。當前 Sprint A 仍 BLOCKED 不可啟 Sprint B。

### §15.8 QA push back（round 2，補強）

我**沒有自行 patch `restart_all.sh`**（per plan §15.1 plan-instruction），**沒有自行建 fixture**（per plan §3 plan-instruction），**沒有自行 stash/pull Linux working tree**（per CLAUDE.md §七「CC 絕不執行 pull/merge/checkout/reset/rebase」）。

需要 PM action：

(d) 接受上面 §15.6 建議 1（清 working tree dirty 狀態） + 建議 2（合併 ENGINE_BINARY_SHA env + REPLAY_FIXTURE_URI env + mkdir runtime dirs 進 `restart_all.sh`），**或**指派 E1 sub-agent 派 task
(e) 確認 fixture re-use `synthetic_btcusdt.json` 是 acceptable Sprint A R3 smoke evidence（per V3 §11 data tier classification — `s3_synthetic` 是 `replay.simulated_fills.evidence_source_tier` 允許值；**注意**：CLAUDE.md §九 已標 `'synthetic_replay' 不可作 ML training data`，下游必 filter）；或 PM 要求 PA 撰寫真實 BTCUSDT 1m fixture（Sprint B+ scope）
(f) 是否要 R3 round 3 hotfix commit chain（restart_all 改 + retest）此次必走 §八 強制工作鏈（@PA → @E1 → @E2 → @E4 → QA）正常派發，**不**走 P0 快速通道（不是 incident，是計劃中的 deploy infra fix）

### §15.9 Sprint A R3 status

**仍 BLOCKED**，但 progression：
- ~~P0: FastAPI signature 422 bug~~ → **RESOLVED** (cad8ed84 hotfix verified at runtime + 45 hermetic test pass)
- P2-A: `OPENCLAW_ENGINE_BINARY_SHA` env not provisioned → **REMAINS BLOCKER**（503 on register）
- P2-B: `/tmp/openclaw/replay_fixtures/btc_1m_smoke.json` not exist → **REMAINS BLOCKER**（will hit FixtureNotFound on /run）
- 4-table acceptance: 0/0/0/0 → **REMAINS FAIL**

**R3 round 3 必修兩個 P2，並 commit Linux working tree 一致性，再重跑這份 §15 retry log。**

---

# QA E2E ACCEPTANCE DONE (Round 2): BLOCK · report path: /Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/QA/workspace/reports/2026-05-04--ref20_sprint_a_r3_smoke_e2e.md

## BLOCKER 清單（Round 2 update）

1. ~~**P0** — `replay_routes.py` body parameter FastAPI 422 (round 1)~~ — **RESOLVED** by hotfix `cad8ed84` (verified at runtime + 45 hermetic test pass)
2. **P2-A — `OPENCLAW_ENGINE_BINARY_SHA` env 未注入 API process**（仍 active）
   - 修法：`helper_scripts/restart_all.sh::restart_api()` 加 export + restart
   - 驗證：`grep ENGINE_BINARY_SHA /proc/$API_PID/environ` ≠ empty + register 200
   - Owner：E1（implement）+ E4（restart_all.sh test）
3. **P2-B — `/tmp/openclaw/replay_fixtures/btc_1m_smoke.json` 不存在**（仍 active）
   - 修法：env `OPENCLAW_REPLAY_FIXTURE_URI` 指向 `synthetic_btcusdt.json`，或 cp + restart
   - 驗證：/run subprocess 不報 `FixtureNotFound`
   - Owner：E1 + PA（fixture 是否需新建）
4. **P0-INFRA — Linux working tree dirty + behind origin/main**（新發現）
   - 修法：operator 端 stash drop + pull --ff-only（CC 不執行）
   - 驗證：`git status` clean + `git rev-parse HEAD` = `cad8ed84`
   - Owner：operator / PM
5. **P1 — Sprint A R3 deploy commit (`66b650ea`) 跳過 hermetic test gate**（仍 active per round 1）
   - 修法：CI / pre-commit hook enforce `pytest tests/test_replay_*.py`
   - Owner：PM（policy）+ E4（CI）

**Sprint A R3 仍不可結案**；R3 smoke E2E BLOCKED 直至 P2-A + P2-B 修復 + 重跑 §15 retry log。

---

## §16 RETRY LOG — Round 3 final smoke (post `e9d547c0`，2026-05-04 23:50+ UTC)

**Verdict: BLOCK 仍維持，但 root cause 從 P2 (env infra) 進到 P0-NEW (manifest signing key.hex provisioning gap — Sprint 1 Track A vs Track B integration drift)；Sprint A R3 4-table acceptance 仍 FAIL（experiments=1 / run_state=1 status='failed' / report_artifacts=0 / simulated_fills=0）；無 trading.fills leak**

### §16.1 Round 4 infra fix (commit `e9d547c0` + `2ae93992`) deploy verified

| 驗證項 | 結果 | 證據 |
|---|---|---|
| Linux 工作樹 git HEAD | `e9d547c0` | `git rev-parse HEAD` |
| Linux working tree clean | clean | `git status --porcelain` 空輸出 |
| origin/main HEAD | `e9d547c0` | `git rev-parse origin/main` |
| API process restart with new env | API PID 739152 alive 23:44 | `ps -ef | grep uvicorn` |
| `OPENCLAW_ENGINE_BINARY_SHA` env injected to API | **YES** | `cat /proc/739152/environ \| tr '\0' '\n' \| grep ENGINE_BINARY_SHA` = `38c72877e526bfede74d57e6c9a90a682d323a2f80a0a9eef0e547f4d048d2f1` |
| Engine binary sha256 actual match | **YES** | `sha256sum rust/target/release/openclaw-engine` = `38c72877...` (identical) |
| `OPENCLAW_REPLAY_FIXTURE_URI` env injected to API | **NO** | API process env 無此 key（plan 提及但未 ship）|
| `_REGISTER_IDEM_CACHE` H-1 fix runtime | YES | `grep _REGISTER_IDEM_CACHE experiment_registry.py` line 151+152 確認 |
| E1 round 4 probe row in replay.experiments | YES | `experiment_id=94770e9e... status=created data_tier=S3 timeframe=1m` |

**Round 4 infra fix 真實落地**：`OPENCLAW_ENGINE_BINARY_SHA` 已 inject 到 API process，restart_all.sh `2ae93992` commit 行為驗證。register endpoint 503 → 200 transition 不再被 P2-A blocking。

### §16.2 Phase 4-9 結果

| Phase | 動作 | HTTP / SQL | 結果 |
|---|---|---|---|
| 1 — login | `POST /auth/login` | HTTP 200 + cookie 有效 | **PASS** |
| 4 — POST /run | `POST /api/v1/replay/run` with `experiment_id=94770e9e... idempotency_key=r3smoke3-1777931408` | **HTTP 503**（reason: `replay_runner_spawn_failed: spawn_died_early:exit=1`） | **PARTIAL**：subprocess 真的 spawn + run_state row 寫入（status='failed'），但 subprocess 立刻 exit=1 |
| 5 — subprocess artifact 確認 | `ls /tmp/openclaw/replay_artifacts/8817ed9fb1f14f8bbb1e553bd31ada20/` | 只有 `manifest.json`（361 bytes），無 stderr/stdout/replay_report.json | subprocess 寫了 manifest 但讀回 manifest 立刻死，stderr 被 `subprocess.DEVNULL` 吞 |
| 5b — manual replay_runner with same manifest | 重跑 `replay_runner --manifest <path> --output-dir <path>` | EXIT=1 with `Error: "manifest_signer_key_missing: sibling key.hex absent at /tmp/openclaw/replay_artifacts/8817ed9fb1f14f8bbb1e553bd31ada20/key.hex; production path requires either (a) operator-deployed sibling key.hex per V042 archive deploy runbook (Wave 6+) or (b) V042 SQL-backed KeyArchive (not yet landed) — fail-closed"` | **Root cause exposed** |
| 6 — POST /finalize | `POST /api/v1/replay/run/8817ed9f.../finalize` | HTTP 409 `replay_run_not_finalizable: status not in (starting,running)` | **設計正確 fail-closed**（status='failed' 不允許 finalize） |
| 7 — 4-table acceptance SQL | `experiments=1 / run_state=1 (status=failed) / report_artifacts=0 / simulated_fills=0` | 1+1+0+0 | **FAIL（4/4 必 > 0，僅 2 表 > 0）** |
| 8 — Wave 9 safety SQL | `trading_fills_15m=3`（demo 既有）；`replay_audit_15m=0`（subprocess 死太早未發 audit） | no replay-induced live mutation | trivially PASS |
| 9 — FK lineage | `run_state.manifest_id (94770e9e...) == experiments.experiment_id (94770e9e...)` | match | **valid** |

### §16.3 4-tables acceptance verdict

| 標準 | 結果 |
|---|---|
| `replay.experiments > 0` | **PASS** (= 1, E1 round 4 已 insert) |
| `replay.run_state > 0` | **PASS** (= 1, R3 round 5 spawn 寫入 status='failed') |
| `replay.report_artifacts > 0` | **FAIL** (= 0) |
| `replay.simulated_fills > 0` | **FAIL** (= 0) |

**Plan §6.R3 acceptance: 2/4 PASS, 2/4 FAIL**

新進展：experiments + run_state 兩表現在都 > 0 — 從 round 2 的 0/0/0/0 → 現在 1/1/0/0，**寫入路徑半通**。R3 deploy 證明 register + spawn 路徑無 P0 bug。但 subprocess 死於 `manifest_signer_key_missing`，**無法產出 report_artifacts / simulated_fills**。

### §16.4 Wave 9 safety + FK lineage

| Item | 結果 | 評估 |
|---|---|---|
| `trading.fills` 15m | 3 row（demo/paper 既有，與 replay 無關，ts column 確認非 replay context_id） | **PASS — no replay-induced live mutation** |
| `learning.governance_audit_log` 15m `replay_*` | 0 row | trivially PASS（subprocess 在 audit emit 前 exit=1） |
| `learning.governance_audit_log` 15m total | (略；本驗證未拉) | engine 治理鏈仍活躍（與 replay 無關） |
| FK lineage（experiments → run_state） | **valid**（manifest_id PK match） | run_state row 寫入時 FK constraint 通過，schema integrity OK |
| `replay.report_artifacts.run_id` FK | N/A（artifacts 0 row） | 等 R3 真跑通 redo |

### §16.5 故障排除（Round 5 真實 root cause — Sprint 1 Track A vs Track B integration drift）

#### P0-NEW — `route_helpers.build_default_manifest_payload` 寫 placeholder signature 但 `replay_runner` Sprint 1 Track B 已 fail-closed 拒絕無 sibling key.hex

**完整 stack trace**：

1. `replay_routes.py POST /run` → `spawn_replay_runner(manifest_id, run_id, output_dir, manifest_fixture_path)` (route_helpers.py:442)
2. `build_default_manifest_payload` 寫 manifest with：
   ```json
   {
     "experiment_id": "94770e9e...",
     "data_tier": "S3",
     "fixture_uri": "/tmp/openclaw/replay_artifacts/<RUN_ID>/fixture.json",  // env override missing
     "signature": "placeholder_signature_wave6_v042_pending",
     "manifest_hash": "placeholder_hash_wave6_v042_pending",
     "signature_key_ref": "placeholder_key_ref"
   }
   ```
   （注意：experiment row 在 register 時填的 `fixture_uri=/home/ncyu/.../synthetic_btcusdt.json` **未被 manifest 使用**；route_helpers 預設用 output_dir/fixture.json）
3. `subprocess.Popen([replay_runner, --manifest <path>, --output-dir <dir>])` → `stderr=subprocess.DEVNULL`（line 549）→ stderr 永久消失
4. `replay_runner` (replay_runner.rs:522 `load_and_verify_manifest`) → 找 sibling `<output_dir>/key.hex`（line 544-547）
5. **REF-20 Sprint 1 Track B (commit `edf33c0`)** 已將 key.hex 缺 fail-open 改為 **fail-closed**（line 548-557）→ exit=1 with `manifest_signer_key_missing`
6. Python `spawn_replay_runner` poll-grace 1.5s 後發現 subprocess 已死 → return `(None, "spawn_died_early:exit=1")`
7. caller wrap into HTTP 503 `replay_runner_spawn_failed`，run_state row 寫 status='failed'

**為何 Sprint A R3 (`66b650ea`) 沒 ship 配套 key.hex provisioning？**：

- Sprint 1 Track A (commit chain pre-`edf33c0`) 預期 manifest_signer fall-through with stderr warning when key.hex 缺
- Sprint 1 Track B (commit `edf33c0`) 修 E3-P0-1 fail-open vulnerability **同時**改 fail-closed
- Sprint A R3 (commit `66b650ea`) 寫 finalize/writer/spawn flow 但未補 `route_helpers.build_default_manifest_payload` 寫 sibling key.hex（or env-pointed path）
- 結果：placeholder signature 配 fail-closed verifier 必死

**修法（推薦 PM Option A）**：`route_helpers.write_manifest_fixture` 同時寫 sibling `key.hex`，內容為 dev 用 fixture key（`aabbccddeeff00112233445566778899aabbccddeeff00112233445566778899` 已在 `rust/openclaw_engine/tests/fixtures/replay_runner_e2e/key.hex` line 1）。配套 `route_helpers.build_default_manifest_payload` 用真實 HMAC-signed manifest，不再 placeholder。

**修法 Option B**：env-gated `OPENCLAW_REPLAY_PROVISION_FIXTURE_KEY=1` 在 dev/test 啟用 sibling key.hex 寫入；live 走 V042 SQL-backed KeyArchive。

**修法 Option C**：保留 placeholder 但 `replay_runner` Track B 加 dev-only env-gate `OPENCLAW_REPLAY_ALLOW_PLACEHOLDER_KEY=1` 允許 fall-through with stderr warning（短期 — 風險：fail-open 復活）。

#### P0-NEW-INFRA — `subprocess.Popen` stderr DEVNULL 吞所有 root cause

**問題**：`route_helpers.py:549 stderr=subprocess.DEVNULL` 是 fail-closed 設計但 root cause 永久看不到。R3 round 5 必 ssh 到 Linux 手動跑同 manifest 才看到 stderr — 任何後續 subprocess fail 都需 manual reproduce。

**修法**：`stderr=subprocess.PIPE`（spawn-then-poll 內讀 stderr buffer 並 log）或 redirect 到 `<output_dir>/replay_runner.stderr` log file（poll grace 後讀 + log）。

#### P2-A — `OPENCLAW_REPLAY_FIXTURE_URI` env 仍未 inject API process（plan §15.6 建議 2 半完成）

- 驗證：API PID 739152 environ 無此 key
- 影響：即使修了 P0-NEW（key.hex provisioning），manifest fixture_uri 仍會走 default `output_dir/fixture.json` 而 fixture file 不存在 → replay_runner 在 fixture loader 層死（next blocker）
- 修法：`restart_all.sh::restart_api()` 加 `export OPENCLAW_REPLAY_FIXTURE_URI=/home/ncyu/BybitOpenClaw/srv/rust/openclaw_engine/tests/fixtures/replay_runner_e2e/synthetic_btcusdt.json`，或同樣 P0-NEW Option A — 直接在 `route_helpers.write_manifest_fixture` 一併 cp/mv fixture file 進 output_dir

### §16.6 PM 接手建議

#### 建議 1：Sprint A R3 commit chain 整合 commit

R3 round 6 必須在 single commit 一次補完：

```python
# route_helpers.py modifications:
# 1. write_manifest_fixture(): write sibling key.hex (dev key for now)
# 2. build_default_manifest_payload(): produce real HMAC signature using dev key
# 3. spawn_replay_runner(): change stderr=subprocess.DEVNULL → stderr=subprocess.PIPE + log on early-death
```

或 Option B (cleaner separation)：

```python
# replay_routes.py POST /run handler:
#   - copy/symlink fixture file from experiment.fixture_uri to output_dir/fixture.json
#   - call ManifestSigner.sign() to produce real signature
#   - call write_manifest_fixture() with signed manifest
#   - call spawn_replay_runner() with PIPE stderr
```

**關鍵 governance**：派 §八 強制工作鏈 PA → E1 → E2 → E4 → QA（**不**走 P0 快速通道；這是計劃中 deploy infra fix）。

#### 建議 2：刪除 P1 commit gate enforcement defer

R3 round 5 證明：問題不在「跑 hermetic test」（45 test PASS 但仍 deploy fail），而在「hermetic test scope 不包含 spawn → execute → finalize 真實鏈」。

**新的 Sprint A close gate**：
- (a) hermetic pytest 全 PASS（既有）
- (b) **R3 smoke E2E 1 cycle 全綠**：register → run → finalize → 4 表 row > 0 → trading.fills 0 leak（新增）
- (c) Phase 8 Wave 9 safety + FK lineage valid（新增）

(b) + (c) 須在 deploy 後 ssh trade-core 驗 — 不依賴 hermetic test environment。

#### 建議 3：QA 接手三連 + 反 silent-dead 三角檢更新

R3 round 5 結論：**「register 200 OK」≠「整條 replay flow 跑通」**。Sprint A R3 round 4 報告（E1 sign-off）只驗 register 沒驗 /run，誤導 PM 以為 R3 已 unblock。

**QA SOP 強化**：任何 endpoint 「200 OK」必驗 downstream effect — 對 /run = subprocess truly executed + report_artifact written + simulated_fills written；不只看 200 OK return。

#### 建議 4：5-commit chain 整體成 Sprint A reality-calibrated foundation 評估

| Commit | 解決問題 | Round 5 驗證 |
|---|---|---|
| `c1ab7ea9` (R0+R1) | runtime usability repair | 仍待 R3 完整 smoke 驗證 |
| `353db3fe` (R2) | manifest registry + verification | E1 round 4 register PASS — verified |
| `66b650ea` (R3) | first real E2E evidence | **R3 round 5 仍 BLOCK — manifest_signer_key_missing** |
| `cad8ed84` (hotfix) | FastAPI 422 body bug | round 2 + round 5 確認 register 200 OK |
| `e9d547c0` + `2ae93992` (R3 round 4) | OPENCLAW_ENGINE_BINARY_SHA inject | round 5 verified env present |

**Round 5 verdict**：5-commit chain 在「runtime + register + signature env」3 層解決問題，但 R3 round 5 揭示**第 4 層 (manifest signing key.hex provisioning)** 是 Sprint 1 Track A vs Track B integration drift — Sprint A R3 未 cover。Sprint A close 必須 ship round 6 補完。

### §16.7 R3 smoke 完成後的 follow-up（B Sprint 啟動條件）

**保持與 round 2 一致**：只有 Sprint A 真正 close（4 表全 > 0 + Wave 9 0 leak + FK valid）後，Sprint B（R4=intent_processor stub + R5=full pipeline integration）才有 evidence 觸發。

當前 Sprint A 進度：
- experiments + run_state 寫入鏈 PASS
- report_artifacts + simulated_fills 寫入鏈 BLOCKED on manifest_signer_key_missing

Round 6 預計 1 task 1 sprint（@PA → @E1 (route_helpers.py + dev key.hex provision) → @E2 → @E4 → @QA round 6 驗）。

---

# QA E2E ACCEPTANCE DONE (Round 3): BLOCK · report path: /Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/QA/workspace/reports/2026-05-04--ref20_sprint_a_r3_smoke_e2e.md

## BLOCKER 清單（Round 3 update）

1. ~~**P0** — `replay_routes.py` body parameter FastAPI 422 (round 1)~~ — **RESOLVED** by `cad8ed84`
2. ~~**P2-A** — `OPENCLAW_ENGINE_BINARY_SHA` env not provisioned (round 2)~~ — **RESOLVED** by `e9d547c0` + `2ae93992`
3. ~~**P0-INFRA** — Linux working tree dirty (round 2)~~ — **RESOLVED**（git status clean，HEAD == origin/main `e9d547c0`）
4. **P0-NEW — `route_helpers.build_default_manifest_payload` placeholder signature + `replay_runner` Sprint 1 Track B fail-closed `manifest_signer_key_missing` integration drift**（round 5 揭示）
   - 修法：見 §16.5 Option A/B/C（推薦 A — `route_helpers.write_manifest_fixture` 同時寫 sibling key.hex + 用真實 HMAC sign manifest）
   - 驗證：手動 `replay_runner --manifest <path> --output-dir <dir>` 應 EXIT=0 + 寫 replay_report.json
   - Owner：@PA (design fixture provision strategy) + @E1 (implement) + @E2 (review) + @E4 (test)
   - Block 範圍：所有 R3 smoke E2E /run → finalize 鏈
5. **P0-NEW-INFRA — `subprocess.Popen stderr=subprocess.DEVNULL` 吞所有 subprocess root cause**
   - 修法：改 `stderr=subprocess.PIPE` + spawn-then-poll 讀 stderr buffer 並 log 到 file
   - 驗證：subprocess fail 後 `<output_dir>/replay_runner.stderr` 存在且非空
   - Owner：@E1 (with @PA review)
6. **P2-A-NEW — `OPENCLAW_REPLAY_FIXTURE_URI` env 仍未 inject API process**（plan §15.6 建議 2 半完成）
   - 修法：restart_all.sh 加 export，或同 P0-NEW Option A 整合（route_helpers 自動 cp fixture）
   - 驗證：`grep REPLAY_FIXTURE_URI /proc/$API_PID/environ` 非空 OR manifest fixture_uri 自動指向真實 fixture
   - Owner：@E1
7. **P1 — Sprint A R3 deploy commit gate** — **REVISED**（round 5 揭示 hermetic test 不夠）：新 close gate 必 (a) hermetic test PASS + (b) R3 smoke E2E full cycle PASS + (c) Wave 9 safety + FK lineage valid
   - Owner：@PM（policy）+ @E4（CI scope expansion）

**Sprint A R3 仍不可結案**；R3 round 6 必修 P0-NEW + P0-NEW-INFRA + P2-A-NEW，重跑 §16 retry log。

## §16.8 QA push back（round 3，補強）

我**沒有自行修 `route_helpers.py`**（業務代碼，per §八 強制鏈），**沒有自行重簽 manifest**（簽章邏輯屬於 manifest_signer.py，PA/E1 scope），**沒有自行寫 sibling key.hex**（dev key 是 PA 設計決策），**沒有自行修 stderr DEVNULL**（business code change），**沒有自行 patch restart_all.sh 加 REPLAY_FIXTURE_URI**（per plan §15.6 plan-instruction）。

Round 5 verify 範圍只到「真實 ssh 觸發 R3 smoke + 觀察 4 表 acceptance + manual reproduce subprocess fail 取 stderr」— 屬 read-only QA scope。

需要 PM action：

(a) 確認 §16.5 P0-NEW Option A/B/C 哪一個是 PM 接受的 fix path，派 §八 強制鏈派 R3 round 6
(b) 確認 §16.5 P0-NEW-INFRA stderr 改 PIPE 進 round 6 同次 commit
(c) 確認 §16.6 建議 2 新 Sprint A close gate (b)+(c) 進入治理規則
(d) Sibling-CC 是否要在 sprint A R3 round 6 之前 review LG-5 W3 FUP-1 (commit `463890d`) 是否影響 manifest_signer 路徑（R3 round 5 沒看到 audit emit 是因為 subprocess 死太早，但 LG-5 reviewer scheduler 待 deploy 後才能驗）

**Sprint A 真實狀態 Round 5**：
- ✅ R3 deploy infra (binary path / signature env / git tracking) 完成
- ✅ register + spawn 半鏈通（experiments=1 / run_state=1）
- ❌ subprocess execute (manifest_signer fail-closed) BLOCKED
- ❌ report_artifacts + simulated_fills 寫入鏈 untested

預估 round 6 工作量：~1.5-2 day E1 task（route_helpers.py refactor + manifest_signer integration + stderr PIPE + 配套 hermetic test for sign+verify cycle）。

| Phase 8 hard gate | 結果 |
|---|---|
| 5 階段業務鏈（市場數據 / H0 / H1-H5 / 5-Agent / Decision Lease + Engine + 學習）| N/A — Sprint A scope = replay lab，不影響 live 鏈 |
| 雙進程 E2E（Python API + replay_runner subprocess）| **PARTIAL** — subprocess truly spawn 但 exit=1 fail-closed |
| 5 hard gate（Phase 6 Live）| N/A — Sprint A 非 Live 升級 gate |
| 7d 灰度 | N/A — Sprint A 仍開頭，未到 7d 觀察 |
| §三 drift check | passed — `e9d547c0` HEAD + `dbcf845b` engine binary deployed 對齊 §三 描述 |

