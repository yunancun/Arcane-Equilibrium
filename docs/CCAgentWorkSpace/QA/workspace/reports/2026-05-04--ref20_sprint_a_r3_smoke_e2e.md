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

---

## §17 RETRY LOG — Round 4 final smoke (post `f51f4e2e` R6+R7 deploy，2026-05-05 01:32+ UTC)

**Verdict: BLOCK 仍維持；R6+R7 deploy 揭露 L6 layer 5 blocker — manifest_signing_key 未 provisioning。Sprint A R3 4-table acceptance 仍 FAIL（experiments=2 / run_state=2 status='failed' / report_artifacts=0 / simulated_fills=0）；無 trading.fills leak**

### §17.1 Round 6+7 deploy verified（部分）

| 驗證項 | 結果 | 證據 |
|---|---|---|
| origin/main HEAD | `f51f4e2e73768a70cef8547b445cd864d3dafcc1` | Mac fetch verified |
| Linux 工作樹 git HEAD | **`e9d547c0`（落後 1 commit）** | `git rev-parse HEAD` |
| Linux working tree clean | **dirty — 3 M files + 2 untracked** | `git status --porcelain` 顯示 helper_scripts/restart_all.sh + replay_routes.py + replay/route_helpers.py modified；test_replay_e2e_round6_smoke.py + test_route_helpers_fixture_default_env.py untracked |
| Working tree 內容 functionally equivalent to `f51f4e2e` | YES（per uncommitted diff 比對） | 但 git tracking 未一致 → P0-INFRA round 4 也 active |
| API process restart time | 2026-05-05 01:29:30 | `ps -o lstart` |
| API PID | 805444 | `ps -ef \| grep uvicorn` |
| `OPENCLAW_ENGINE_BINARY_SHA` env | **YES** | `/proc/805444/environ` = `38c72877...` |
| Engine binary actual sha256 match env | **YES** | `sha256sum rust/target/release/openclaw-engine` = `38c72877...` (identical) |
| `OPENCLAW_REPLAY_FIXTURE_DEFAULT` env | **YES** | `/proc/805444/environ` = `/home/ncyu/BybitOpenClaw/srv/rust/openclaw_engine/tests/fixtures/replay_runner_e2e/synthetic_btcusdt.json` |
| **`OPENCLAW_SECRETS_DIR` env** | **MISSING** | `/proc/805444/environ` 0 命中 |
| **`OPENCLAW_REPLAY_SIGNING_KEY_FILE` env** | **MISSING** | `/proc/805444/environ` 0 命中 |
| **`replay_signing_key` file exists anywhere** | **NO** | `find /home/ncyu/BybitOpenClaw -name replay_signing_key` empty result |

**Round 6+7 的 3 個聲稱 fix 真實狀態**：

| 聲稱 fix | runtime 驗證 | 狀態 |
|---|---|---|
| ✅ R6-T1 真 HMAC sign + key.hex sibling | **未驗到** — `_resolve_manifest_signing_key()` 在 step 2 `load_signing_key_from_secrets_dir` 因 `OPENCLAW_SECRETS_DIR` 未設直接 fallthrough → step 3 raise `ValueError("manifest_signing_key_unavailable")` → caller 進 `manifest_fixture_write_failed:ValueError` 路徑；output_dir 0 file written | **DEPLOY 半完成** |
| ✅ R6-T2 stderr DEVNULL → `<output_dir>/replay_runner.stderr` disk file | **代碼存在但未觸發** — subprocess.Popen 從未 invoke（在 manifest_fixture_write_failed 之前已 return） | **deploy OK 但未行動** |
| ✅ R6-T3a `OPENCLAW_REPLAY_FIXTURE_DEFAULT` env 注入 | **YES** | **deploy OK** |

### §17.2 Phase 1-7 結果

| Phase | 動作 | HTTP / SQL | 結果 |
|---|---|---|---|
| 1 — login | `POST /auth/login` | HTTP 200 + cookie 有效 | **PASS** |
| 2 — register | `POST /experiments/register` with `idempotency_key=r3smoke4-1777937530`（不傳 fixture_uri）| HTTP 200 + `experiment_id=bbcdff7e-0014-4bcd-80df-9292413e734e` + `manifest_hash=95e44198...` + `idempotency_hit=false` | **PASS** |
| 3 — POST /run | `POST /run` with experiment_id+idempotency | **HTTP 503**（`reason_codes=["replay_runner_spawn_failed"]; message=replay_runner failed to spawn; check server logs (replay_runner.stderr) for diagnosis`）| **BLOCKED on signing key** |
| 4 — wait subprocess + check artifacts | `ls /tmp/openclaw/replay_artifacts/<RUN_ID>` | **空 directory**，0 file written | subprocess 從未 spawn（R6-T1 fail-closed before subprocess.Popen） |
| 4b — root cause 從 api.log | `grep load_signing_key_from_secrets_dir /tmp/openclaw/api.log` | `load_signing_key_from_secrets_dir: OPENCLAW_SECRETS_DIR not set / OPENCLAW_SECRETS_DIR 未設` | **smoking gun 鎖定 P0-NEW-2** |
| 5 — POST /finalize | (未跑：依賴 Phase 3) | N/A | N/A |
| 6 — 4-table acceptance SQL | `experiments=2 / run_state=2 (status='failed' both rows) / report_artifacts=0 / simulated_fills=0` | 2+2+0+0 | **FAIL（4/4 必 > 0，僅 2 表 > 0）** |
| 7 — Wave 9 safety + FK lineage | `trading_fills_15m=2`（TONUSDT demo ma_crossover，無 replay context_id）；`all_replay_audit_15m=0`；`all_audit_15m=48`（review_live_candidate）；run 09da3571.manifest_id == experiment bbcdff7e（FK valid） | no replay-induced live mutation | trivially PASS |

### §17.3 Sprint A acceptance verdict — 4 表 row > 0 是否達成

| Plan §6.R3 標準 | 結果 |
|---|---|
| `replay.experiments > 0` | **PASS** (= 2，含 round 5 leftover 1 + round 4 新 1) |
| `replay.run_state > 0` | **PASS** (= 2，兩 row 都 status='failed') |
| `replay.report_artifacts > 0` | **FAIL** (= 0) |
| `replay.simulated_fills > 0` | **FAIL** (= 0) |

**整體 R3 smoke E2E：仍 FAIL — Sprint A R3 acceptance 2/4 PASS, 2/4 FAIL**

進度 trajectory（4 round 累積）：
- Round 1：0/0/0/0（FastAPI 422 body bug）
- Round 2：0/0/0/0（OPENCLAW_ENGINE_BINARY_SHA env missing）
- Round 3：1/1/0/0（manifest_signer key.hex missing — placeholder vs Sprint 1 Track B fail-closed）
- **Round 4：2/2/0/0（manifest_signing_key 未 provisioning — secrets_dir + signing_key_file 雙 env 都 missing）**

**Sprint A R3 仍不可結案**，但寫入鏈半通：register 200 + run pid 寫 row（status='failed' fail-closed 設計正確）。subprocess 從未 invoke → report_artifacts + simulated_fills 寫入鏈仍 untested。

### §17.4 故障排除 — Round 4 真實 root cause

PM plan 開頭斷言「核心 fix 已 land」3 條，runtime 驗證後實況：

#### P0-NEW-2 — `OPENCLAW_SECRETS_DIR` + `replay_signing_key` 未 provisioning（**新發現，不在 plan 預期內**）

R6+R7 commit `f51f4e2e` 改 `route_helpers.py::_resolve_manifest_signing_key()`：

```python
# Step 1: env override OPENCLAW_REPLAY_SIGNING_KEY_FILE
# Step 2: load_signing_key_from_secrets_dir(env_label) —
#   look up $OPENCLAW_SECRETS_DIR/<env_label>/replay_signing_key
# Step 3: NULL → raise ValueError("manifest_signing_key_unavailable")
```

**runtime 真實狀態**：
- `OPENCLAW_REPLAY_SIGNING_KEY_FILE` env 未設 → step 1 skip
- `OPENCLAW_SECRETS_DIR` env 未設 → `load_signing_key_from_secrets_dir` 印 `OPENCLAW_SECRETS_DIR not set` 後 return None → step 2 skip
- step 3 raise ValueError → caller `replay_routes.py:516` 把 `ValueError` 包成 `manifest_fixture_write_failed:ValueError` pg_err → `replay_routes.py:660-680` 路由到 503 `replay_runner_spawn_failed`（R7 FINDING-2 改動讓 message 不再帶 stderr text）

**為何 R6+R7 commit 沒同步 ship 配套 provisioning？**：

- 已存在 `helper_scripts/operator/generate_replay_signing_key.sh`（since R2-T3，2026-05-04 commit `353db3fe`），其 docstring 明確說 *「This script generates a 256-bit random key, writes to the spec'd path with mode 0600. It does NOT auto-deploy, auto-restart engines.」*
- R6 commit message 列 "Pending: Linux deploy via restart_all.sh --rebuild" 但**未列**「先跑 generate_replay_signing_key.sh demo」
- `restart_all.sh` R6-T3a 改動只 inject `OPENCLAW_REPLAY_FIXTURE_DEFAULT`，**沒**加 `OPENCLAW_SECRETS_DIR` export
- 結果：deploy chain 完成 binary path / fixture default / FastAPI 422 fix，但 sigining key 路徑仍是 「文檔提示但未 ship」

**修法（推薦 PM Option A）**：兩步走 deploy：

```bash
# 1. 跑 operator key gen helper for demo profile：
ssh trade-core "OPENCLAW_SECRETS_DIR=/home/ncyu/BybitOpenClaw/secrets/secret_files/bybit \
  bash helper_scripts/operator/generate_replay_signing_key.sh demo"
# 預期：寫 /home/ncyu/BybitOpenClaw/secrets/secret_files/bybit/demo/replay_signing_key (mode 0600)

# 2. 改 restart_all.sh::restart_api() 加 export：
export OPENCLAW_SECRETS_DIR="$OPENCLAW_BASE_DIR/../secrets/secret_files/bybit"
# 或 已有變數 mapping CLAUDE.md §六 顯示
#   OPENCLAW_SECRETS_DIR=secrets/secret_files/bybit (slot base)
# restart_all.sh 應該 honor 既有 env layout

# 3. restart_all --keep-auth (無 Rust 改動，不需 --rebuild)
ssh trade-core "bash helper_scripts/restart_all.sh --keep-auth"
```

**修法 Option B**：繞過 secrets_dir，用 env override 直指 dev key file（dev/test profile only）：

```bash
# restart_all.sh::restart_api() 加：
export OPENCLAW_REPLAY_SIGNING_KEY_FILE="$OPENCLAW_BASE_DIR/rust/openclaw_engine/tests/fixtures/replay_runner_e2e/key.hex"
# 該 dev key 已 commit 到 git: aabbccddeeff00112233445566778899aabbccddeeff00112233445566778899
```

**不選 Option B 的理由**：R7 FINDING-1 加了 `is_live_release_profile()` block — 若日後 profile 切 live，env override 會 hard-block，但若 dev fixture key 被誤用一陣後切 live 容易留 audit-trail 殘渣。Option A 是 production-grade。

#### P0-INFRA-2 — Linux working tree 仍 dirty + 落後 origin 1 commit（round 2 P0-INFRA repeat）

| 驗證項 | 結果 |
|---|---|
| Linux HEAD | `e9d547c0`（origin/main = `f51f4e2e`）|
| 落後 commits | 1（即 `f51f4e2e`） |
| Working tree dirty 內容 | 3 M files + 2 untracked，內容 functionally equivalent to `f51f4e2e` |

PM plan 開頭聲稱「Mac=Linux=origin sync」，runtime 驗證為 **Mac=origin (`f51f4e2e`) ≠ Linux (`e9d547c0` working tree dirty)**。代碼層行為等同，但 git tracking 違反 §七 commit 即 push + Mac→Linux pull 同步規則。

修法：operator 端 `cd ~/BybitOpenClaw/srv && git stash && git pull --ff-only && git stash drop`（per CLAUDE.md §七 CC 不執行 stash/pull/reset）。

#### P0-NEW-INFRA-2 — `replay_runner.stderr` disk file 在 manifest_fixture_write_failed 路徑下不會被寫

**現象**：R6-T2 改動 `subprocess.Popen` 加 stderr redirect 到 `<output_dir>/replay_runner.stderr`，**但**該 fix 只生效於 subprocess.Popen 真實 invoke 後。R6-T1 失敗（`manifest_signing_key_unavailable`）發生在 subprocess.Popen **之前**，stderr disk file 不會被開檔，operator 唯一 root cause 證據是 `tail /tmp/openclaw/api.log` 找 `OPENCLAW_SECRETS_DIR not set` 那一行。

這算 R6-T2 fix scope 的 known limitation — fix 解決「subprocess died after Popen with silent stderr」，不解決「subprocess never spawned due to pre-spawn ValueError」。

**改善建議（非 P0，但對 round 5+ debugging 有幫助）**：`route_helpers.py::write_manifest_fixture` 在 catch ValueError 後 `log.error()` 應該 print full traceback（含 step 1/2/3 哪一步 fail），而不只是 step 2 的 print 一行。當前 caller 寫 503 但 swallow exception traceback。

#### P2-A-RESOLVED ✅ — `OPENCLAW_REPLAY_FIXTURE_DEFAULT` env injected

R6-T3a 已 deploy。`/proc/805444/environ` 確認。register call 不傳 `manifest_jsonb.fixture_uri` 且未報「fixture_uri_missing」（雖然 spawn 沒到 fixture loader 那一步）。

### §17.5 PM 接手建議 — Sprint A close commit doc + worklog

#### 建議 1：Round 5 deploy chain（連 commit + 跑 helper script）

```bash
# 1. clean Linux working tree
ssh trade-core 'cd ~/BybitOpenClaw/srv && git stash && git pull --ff-only && git stash drop'
# 預期：working tree clean + HEAD == f51f4e2e

# 2. provision dev signing key for demo profile
ssh trade-core 'OPENCLAW_SECRETS_DIR=/home/ncyu/BybitOpenClaw/secrets/secret_files/bybit \
  bash helper_scripts/operator/generate_replay_signing_key.sh demo'

# 3. PM 派 E1 in-flight：改 helper_scripts/restart_all.sh::restart_api() 加：
export OPENCLAW_SECRETS_DIR="${OPENCLAW_SECRETS_DIR:-$REPO_ROOT/../secrets/secret_files/bybit}"
# CLAUDE.md §六 已宣 OPENCLAW_SECRETS_DIR=secrets/secret_files/bybit (slot base)，restart_all 應該尊重既有 layout

# 4. restart_all --keep-auth + smoke retest
ssh trade-core 'bash helper_scripts/restart_all.sh --keep-auth'
```

#### 建議 2：governance 修補（Sprint A close gate 補強）

R6+R7 round chain 揭示一個系統 governance hole：3500+ pytest PASS（含 R6-T4 的 25 PASS）但**真實 Linux runtime smoke E2E 0 cycle**才能 catch P0-NEW-2。

新 Sprint A close gate 應包含：

```bash
# (A) 既有 hermetic pytest gate（無變動）
cd program_code/exchange_connectors/bybit_connector/control_api_v1
.venv/bin/python -m pytest tests/test_replay_*

# (B) 新增 Linux runtime smoke gate（新增）：
ssh trade-core 'cd ~/BybitOpenClaw/srv && \
  OPENCLAW_REPLAY_E2E_SMOKE=1 .venv/bin/python -m pytest \
  program_code/exchange_connectors/bybit_connector/control_api_v1/tests/replay/test_replay_e2e_round6_smoke.py'
# R6-T4 commit 提到 test_replay_e2e_round6_smoke.py 是 opt-in via OPENCLAW_REPLAY_E2E_SMOKE=1；本應每次 deploy 後跑一次

# (C) PM commit 驗 ENV 三件套（新增）：
ssh trade-core 'API_PID=$(pgrep -f "uvicorn app.main:app" | head -1); \
  for v in OPENCLAW_ENGINE_BINARY_SHA OPENCLAW_REPLAY_FIXTURE_DEFAULT OPENCLAW_SECRETS_DIR; do \
    echo -n "$v="; grep -aE "^$v=" /proc/$API_PID/environ | head -1 || echo "MISSING"; \
  done'
```

(B) + (C) 都應在 deploy 後 ssh 驗，**任一 missing 即 BLOCK Sprint A close**。

#### 建議 3：Round 5 派發路徑

| Step | Owner | Action |
|---|---|---|
| 1 | operator | `git stash drop + pull --ff-only` Linux working tree |
| 2 | operator (一次性) | 跑 `generate_replay_signing_key.sh demo` |
| 3 | E1 | 改 `restart_all.sh::restart_api()` 加 `export OPENCLAW_SECRETS_DIR` |
| 4 | E2 round | 5 review 該 1 LOC 改動 |
| 5 | E4 | hermetic pytest 全 PASS + restart_all 重啟 + ssh 驗 ENV 三件套 |
| 6 | QA | 重跑 Phase 1-7 + §17 sign-off round 5 |
| 7 | PM | Sprint A close commit + 標 P6 真正 RUN-CALIBRATED 收尾 |

預計 round 5 工作量：~0.5-1 day（小範圍 deploy infra fix + smoke 1 cycle 即可結 Sprint A）。

#### 建議 4：Sprint A 真實狀態 vs PM plan 偏差

PM plan 開頭斷言「核心 fix 已 land — 4-layer blocker fix」3 條：
- ✅ R6-T1 真 HMAC sign + key.hex sibling — **未驗** (deploy 半完成；secrets_dir 未注入)
- ✅ R6-T2 stderr → disk file — deploy OK 但未行動
- ✅ R6-T3a fixture env — DEPLOY OK

斷言「API 4 routes all 401」誤導：本 round 驗證 register 真實 200；plan 寫 401 應該是 plan 寫作時未 login。

PM 應更新 plan §17.1 狀態以匹配 runtime 證據：「3 fix 中 1 deploy halfway（manifest_signer 配套未 ship），1 deploy OK but untriggered，1 deploy fully OK」。

### §17.6 R3 smoke 完成後 follow-up — B Sprint 啟動

**保持與 round 1-3 一致**：只有 Sprint A 真正 close（4 表全 > 0 + Wave 9 0 leak + FK valid + subprocess 真實 EXIT=0 + replay_report.json 寫入 + simulated_fills 真實 row）後，Sprint B（R4=intent_processor stub + R5=full pipeline integration）才有 evidence 觸發。

當前 Sprint A 4-round trajectory：
- Round 1: P0 FastAPI 422 ✅ resolved
- Round 2: P2-A ENGINE_BINARY_SHA env ✅ resolved
- Round 3: P0-NEW manifest_signer key.hex ✅ resolved (per R6-T1 design intent)
- **Round 4: P0-NEW-2 OPENCLAW_SECRETS_DIR + replay_signing_key provisioning — not resolved**

**Round 5 的工作不應是「再多寫一個 fix commit」**，而是 **「補完 deploy infra」**：跑 `generate_replay_signing_key.sh` + 改 `restart_all.sh` 加 `OPENCLAW_SECRETS_DIR` export。R6 的 Python 代碼 fix 是正確的（fail-closed 設計合宜），缺的是 deploy chain 配套。

### §17.7 QA push back — Round 4

我**沒有自行跑 `generate_replay_signing_key.sh`**（per CLAUDE.md §六 secrets layout + §七 CC 不寫 secret），**沒有自行修 `restart_all.sh`**（per round 2 plan-instruction），**沒有自行 stash/pull Linux working tree**（per CLAUDE.md §七 CC 不執行 pull/merge/checkout/reset）。

需要 PM action：

(a) 確認 §17.4 P0-NEW-2 Option A（推薦）vs Option B（dev 專用 env override）的選擇
(b) 確認 §17.5 建議 1 的 4-step deploy chain order（先 git clean 再 key gen 再 E1 改 restart_all 再 deploy）
(c) 確認 §17.5 建議 2 新 Sprint A close gate 加 Linux runtime smoke + ENV 三件套驗（governance update）
(d) 確認 §17.5 建議 3 派發路徑 — round 5 應走 §八 強制鏈（@PA → @E1 → @E2 → @E4 → QA round 5）
(e) PM 更新 plan plan-status 標 R6+R7 為「半 deploy / signing key 未 provisioning」

### §17.8 Sprint A R3 status — Round 4 trajectory

**仍 BLOCKED**，但 progress trajectory：

| Round | trajectory | 寫入鏈 |
|---|---|---|
| 1 | 0/0/0/0 — `from __future__ annotations` FastAPI 422 | register endpoint 0% |
| 2 | 0/0/0/0 — ENGINE_BINARY_SHA env not provisioned | register 503 |
| 3 | 1/1/0/0 — placeholder signature mismatch | register 200 + run spawn fails on key.hex |
| **4** | **2/2/0/0 — secrets_dir + signing_key_file 雙 env missing** | **register 200 + run pre-spawn ValueError** |

**Round 5 必修 P0-NEW-2 + P0-INFRA-2，重跑 §17 retry log**。預計 trajectory 進到 3/3/1/1 或 3/3/0/0（取決於 subprocess 真實是否 EXIT=0）。

---

# QA E2E ACCEPTANCE DONE (Round 4): BLOCK · report path: /Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/QA/workspace/reports/2026-05-04--ref20_sprint_a_r3_smoke_e2e.md

## BLOCKER 清單（Round 4 update）

1. ~~**P0**~~ — FastAPI 422 (round 1) — RESOLVED by `cad8ed84`
2. ~~**P2-A**~~ — ENGINE_BINARY_SHA env (round 2) — RESOLVED by `e9d547c0` + `2ae93992`
3. ~~**P0-NEW** (round 3)~~ — placeholder signature collision — RESOLVED by `f51f4e2e` R6-T1（Python 代碼層）
4. ~~**P0-NEW-INFRA** (round 3)~~ — stderr DEVNULL — RESOLVED by `f51f4e2e` R6-T2（Python 代碼層；本 round 未觸發路徑驗證）
5. ~~**P2-A-NEW** (round 3)~~ — REPLAY_FIXTURE_URI env — RESOLVED by `f51f4e2e` R6-T3a（rename 為 REPLAY_FIXTURE_DEFAULT）
6. **P0-NEW-2 — `OPENCLAW_SECRETS_DIR` + `replay_signing_key` 未 provisioning**（**Round 4 新發現**）
   - 修法：見 §17.4 Option A（推薦）— 跑 `generate_replay_signing_key.sh demo` + restart_all.sh export OPENCLAW_SECRETS_DIR
   - 驗證：`/proc/$API_PID/environ` 含 `OPENCLAW_SECRETS_DIR` + `ls $OPENCLAW_SECRETS_DIR/demo/replay_signing_key` 存在
   - Owner：operator (跑 helper) + @E1 (改 restart_all.sh) + @QA (round 5 重驗)
   - Block 範圍：所有 R3 smoke E2E /run → spawn → finalize 鏈
7. **P0-INFRA-2 — Linux working tree dirty + 落後 origin 1 commit**（**Round 4 repeat round 2 issue**）
   - 修法：operator `git stash drop + pull --ff-only`
   - 驗證：`git status --porcelain` 空 + `git rev-parse HEAD` == `f51f4e2e`
   - Owner：operator
8. **P0-NEW-INFRA-2 — manifest_fixture_write_failed pre-spawn ValueError 路徑下無 stderr disk file**（**改善建議，非阻塞**）
   - 修法：`route_helpers.py::write_manifest_fixture` catch ValueError 後 `log.error()` print full traceback
   - 驗證：next ValueError event 有完整 traceback in api.log
   - Owner：@E1（小範圍 logging fix，可進 round 5 同 commit chain）
9. **P1 — Sprint A close gate 不夠強**（**round 4 governance update**）
   - 修法：見 §17.5 建議 2 — 新增 (B) Linux runtime smoke gate + (C) ENV 三件套 grep
   - Owner：@PM (policy) + @E4 (CI integration)

**Sprint A R3 仍不可結案**；R3 round 5 必修 P0-NEW-2 + P0-INFRA-2，重跑 §17 retry log。

| Phase 8 hard gate | 結果 |
|---|---|
| 5 階段業務鏈 | N/A — Sprint A scope = replay lab，不影響 live 鏈 |
| 雙進程 E2E（API + replay subprocess） | **PARTIAL**：API alive，但 subprocess 從未 spawn（pre-spawn ValueError）|
| 5 hard gate（Phase 6 Live） | N/A — Sprint A 非 Live 升級 gate |
| 7d 灰度 | N/A — Sprint A 仍開頭，未到 7d 觀察 |
| §三 drift check | passed — engine binary SHA `38c72877...` 對齊 §三「Engine binary deployed `dbcf845b`」描述（前者為 binary 內容 hash，後者為原始碼 commit hash；engine_watchdog 看的是 mtime/SHA 用於 H0 freshness） |

---

## §18 Round 5 final smoke (post-`3a425447` Round 8 hotfix; 2026-05-05 01:43-01:44)

**Verdict: STILL BLOCK — P0-NEW-2 ROOT CAUSE 已識別 — Round 8 deploy 配套 100% 正確（subprocess 真實 status=completed + report 寫盤），但 route handler 把 fast-exit-0 當 503 失敗 — 「pathological clean-exit branch」設計缺陷；4 表 acceptance 部分 PASS：experiments=3 + run_state=3 (status=failed 因路由錯誤標記) + report_artifacts=0 + simulated_fills=0**

**HEAD**: Mac=Linux=origin all `3a425447` · Engine PID 4122084 alive · API PID 816284 alive · operator 0 manual fix needed for env

---

### §18.1 Round 8 hotfix deploy verified — 3 env injected ✅

| ENV | Value | 狀態 |
|---|---|---|
| `OPENCLAW_ENGINE_BINARY_SHA` | `38c72877e526bfede74d57e6c9a90a682d323a2f80a0a9eef0e547f4d048d2f1` | ✅ injected |
| `OPENCLAW_REPLAY_FIXTURE_DEFAULT` | `/home/ncyu/BybitOpenClaw/srv/rust/openclaw_engine/tests/fixtures/replay_runner_e2e/synthetic_btcusdt.json` | ✅ injected |
| `OPENCLAW_REPLAY_SIGNING_KEY_FILE` | `/home/ncyu/BybitOpenClaw/srv/rust/openclaw_engine/tests/fixtures/replay_runner_e2e/key.hex` | ✅ injected |

git working tree clean，Mac=Linux=origin 全 sync 在 `3a425447`。Round 1-4 5-layer infra blocker chain **真實清光**。

---

### §18.2 Phase 1-7 結果

#### Phase 1 — Login（200 OK）

```bash
POST /api/v1/auth/login
→ {"status":"ok","username":"398903348"} HTTP=200
```

Cookie 寫入 `/tmp/r3smoke5_cookie.txt`。

#### Phase 2 — Register experiment（200 OK）

```bash
POST /api/v1/replay/experiments/register
{
  "idempotency_key":"r3smoke5-1777938237",
  "symbol":"BTCUSDT","strategy":"grid_trading","timeframe":"1m",
  "data_tier":"S3",
  "data_window_start":"2026-05-01T00:00:00Z",
  "data_window_end":"2026-05-02T00:00:00Z",
  "strategy_config_sha256":"<64x0>","risk_config_sha256":"<64x0>",
  "half_life_days":7.0,"embargo_days":14,
  "manifest_jsonb":{"smoke":true}
}
→ {
  "ok":true,
  "data":{
    "experiment_id":"be2c51ff-d104-4e45-bf0c-417a5cac0228",
    "manifest_hash":"95e44198d52108d7fc0c27731cf08b4e64e27ed7ebcd757d5e584404bc87bf1c",
    "status":"created",
    "idempotency_hit":false
  },
  "is_simulated":false
} HTTP=200
```

Register 路徑全綠。Manifest hash 來自 sha256(manifest_jsonb)，非 placeholder。

#### Phase 3 — POST /run（503 — UNEXPECTED）

```bash
POST /api/v1/replay/run
{"experiment_id":"be2c51ff-d104-4e45-bf0c-417a5cac0228",
 "idempotency_key":"r3smoke5-1777938237-run"}
→ {"detail":{"reason_codes":["replay_runner_spawn_failed"],
   "message":"replay_runner failed to spawn; check server logs (replay_runner.stderr) for diagnosis"}}
HTTP=503
```

503 reason `replay_runner_spawn_failed`。但下方 §18.5 揭示這是**虛假 503** — subprocess 實際成功，route handler 誤判。

#### Phase 4 — Subprocess 實際狀態（真相揭示）

`api.log` 直接 truth：

```
replay_runner exited 0 within poll grace: pid=817807 run_id=1ef3a488e72946aa80090aa745fdd59e
(report should still be on disk; stderr_path=/tmp/openclaw/replay_artifacts/.../replay_runner.stderr)
```

artifact dir 全套都在：

```bash
ls /tmp/openclaw/replay_artifacts/1ef3a488e72946aa80090aa745fdd59e/
# key.hex (65 byte)
# manifest.json (440 byte) — 含真實 HMAC signature key_ref e7f5af202753a289
# replay_report.json (866 byte)
# replay_report.summary.txt (316 byte)
# replay_runner.stderr (179 byte) ← R6-T2 stderr disk file 真實寫入
```

`replay_runner.stderr` 內容：
```
replay_runner: completed manifest_id=be2c51ff-d104-4e45-bf0c-417a5cac0228 status=completed
json=/tmp/openclaw/replay_artifacts/1ef3a488e72946aa80090aa745fdd59e/replay_report.json
```

**stderr 訊息明確說「completed」** — subprocess 完整跑完。

`replay_report.json` 內容（節錄）：

```json
{
  "schema_version": 1,
  "manifest_id": "be2c51ff-d104-4e45-bf0c-417a5cac0228",
  "execution_confidence": "none",
  "result": {
    "status": {"kind": "completed"},
    "fills": [
      {
        "ts_ms": 1714521600000,
        "symbol": "BTCUSDT", "side": "long",
        "qty": 1.0, "price": 65050.0,
        "evidence_source_tier": "synthetic_replay"
      }
    ],
    "pnl_summary": {
      "events_processed": 10,
      "fills_emitted": 1,
      "starting_balance": 10000.0,
      "ending_balance": 10630.0,
      "net_pnl": 630.0
    },
    "diagnostics": {
      "guard_enforce_runtime_calls": 10,
      "abort_reason": null
    }
  }
}
```

10 events 全部處理 + 1 fill emitted + net_pnl=+630 + 0 abort_reason + 10 guard enforce calls。**這是 Sprint A scope 100% 完成的證據** — replay_runner 真實 walk fixture，真實 HMAC verify 通過，真實寫盤。

#### Phase 5 — 嘗試 /finalize（409 — 不可結案因為 route 已標 failed）

```bash
POST /api/v1/replay/run/1ef3a488-e729-46aa-8009-0aa745fdd59e/finalize
→ {"detail":{"reason_codes":["replay_run_not_finalizable"],
   "message":"run 1ef3a488... status not in ('starting','running'); may be already finalized or never started"}}
HTTP=409
```

run_state row 已被 route 503 路徑標記 `status=failed`，finalize 拒接（finalize 要求 `IN ('starting','running')`）。

#### Phase 6 — 4 表 acceptance SQL（部分 PASS）

| 表 | count | 預期 | 結果 |
|---|---:|---|---|
| `replay.experiments` | **3** | > 0 | ✅ PASS（register 成功）|
| `replay.run_state` | **3** | > 0 | ⚠️ 寫了但 status=failed（route 誤判）|
| `replay.report_artifacts` | **0** | > 0 | ❌ FAIL（finalize 從未執行）|
| `replay.simulated_fills` | **0** | > 0 | ❌ FAIL（finalize 從未執行）|

**2/4 寫鏈通了，2/4 finalize 鏈未通 — 因為 503 path 不寫 finalize**。

#### Phase 7 — Wave 9 safety + FK lineage

| 檢查 | 結果 | 結論 |
|---|---|---|
| `trading.fills` last 15 min | **0 row** | ✅ no leak |
| `learning.governance_audit_log` replay_* event last 15 min | **0 row** | ✅ no critical |
| FK lineage（`run_state.manifest_id == experiments.experiment_id`）| **3/3 valid** | ✅ |
| run_state 最新 row | run=1ef3a488 / manifest=be2c51ff / status=failed / pid=NULL / completed=2026-05-05T01:44:01Z | failed=route 誤判，非真實死亡 |

---

### §18.3 Sprint A acceptance verdict

**4/4 PASS**: ❌ **NOT MET**
- experiments=3 ✅ PASS
- run_state=3 ⚠️ 寫了但 status=failed（程序邏輯錯誤產生 false negative）
- report_artifacts=0 ❌ FAIL
- simulated_fills=0 ❌ FAIL

**Plan §6.R3 acceptance "All four > 0 after smoke run"**：**NOT MET**

---

### §18.4 Wave 9 safety + FK lineage 結果

| 安全 invariant | 結果 |
|---|---|
| `trading.fills` 無 replay 注入 | ✅ PASS（0 row last 15 min）|
| `governance_audit_log` 無 replay critical event | ✅ PASS（0 row）|
| FK lineage `run_state.manifest_id → experiments.experiment_id` 三筆 row 全 valid | ✅ PASS |
| `evidence_source_tier='synthetic_replay'` 在 replay_report.json | ✅ PASS（不會混入 ML training，§九 `replay.simulated_fills` 規則保留）|

Wave 9 safety GREEN — replay subprocess **沒有**洩漏到 production 數據面，failure 是純 control-plane bug 不是數據面 bug。

---

### §18.5 P0-NEW-2 ROOT CAUSE — `pathological clean-exit branch` 設計缺陷

**Code path**：

```python
# program_code/.../control_api_v1/replay/route_helpers.py:639-650
if rc is not None and rc == 0:
    # Pathological: binary exited cleanly within grace window. Treat
    # as alive=False since downstream wait/UPDATE assumes a live PID.
    log.warning(
        "replay_runner exited 0 within poll grace: pid=%d run_id=%s "
        "(report should still be on disk; stderr_path=%s)",
        proc.pid, run_id, stderr_path,
    )
    return None, "spawn_died_early:exit=0"  # ← 返回失敗 reason
```

下游 route handler：

```python
# program_code/.../control_api_v1/app/replay_routes.py:657-680
if pg_err and pg_err.startswith((
    "spawn_error:",
    "spawn_died_early:",  # ← 包括 :exit=0
    "mkdir_error:",
    "pg_error:",
    "manifest_fixture_write_failed:",
)):
    raise HTTPException(
        status_code=503,
        detail={"reason_codes": ["replay_runner_spawn_failed"], ...}
    )
```

**邏輯漏洞**：
1. `replay_runner` 對 synthetic 10-event fixture 在 hot cache 下 ~0.5-1s 跑完
2. `poll_grace_seconds=1.5` (route_helpers.py default)
3. `time.sleep(1.5)` + `proc.poll()` → rc=0（已 clean exit）
4. 函數認為「downstream wait/UPDATE assumes a live PID」所以 pid=None + return failure reason
5. Route 不 distinguish `exit=0`（成功）vs `exit=N for N != 0`（真死），全部 503

**對比 R6-T4 hermetic test**（`test_replay_e2e_round6_smoke.py:206`）：
```python
# Allow exit=0 (fixture ran fully); reject any non-zero early death.
assert err == "spawn_died_early:exit=0", (...)
```

該 test 明確接受 `exit=0` 是 OK path（"fixture ran fully"），但 **route handler 沒有 mirror 該 acceptance** — 把 exit=0 與真死同等對待。

**Sprint A R3 hermetic test 不能保護 production E2E**：因為 R6-T4 只測 `spawn_replay_runner` 直接呼叫，沒測 route handler downstream 路徑。

---

### §18.6 故障排除 — Round 8 deploy 配套全綠

| Layer | Round 8 狀態 | 證據 |
|---|---|---|
| Python `from __future__ annotations` | ✅ removed (round 1 fix `cad8ed84`) | hotfix 已 land |
| `OPENCLAW_ENGINE_BINARY_SHA` env | ✅ injected | `/proc/816284/environ` 確認 |
| `OPENCLAW_REPLAY_FIXTURE_DEFAULT` env | ✅ injected | 同上 |
| `OPENCLAW_REPLAY_SIGNING_KEY_FILE` env | ✅ injected | round 8 hotfix `3a425447` |
| `key.hex` provisioning | ✅ R6 sibling key.hex written | `aabbccddeeff00112233...` |
| stderr to disk file | ✅ R6-T2 working | replay_runner.stderr 179 byte 真實寫入 |
| Manifest HMAC signing | ✅ working | manifest.json signature_key_ref `e7f5af202753a289` |
| Subprocess 真實執行 | ✅ status=completed | replay_report.json events_processed=10 fills_emitted=1 |

5-layer infra blocker chain（round 1-4）**100% 真實清光**。新 P0 是 round 5 才暴露的 **route handler design bug**，與 round 1-4 infra 無關。

---

### §18.7 Sprint A close commit + Sprint B 啟動條件 recommendations

**Sprint A R3 推進度**（5 round 累積）：
- ✅ Layer 1: Python signature handling (cad8ed84)
- ✅ Layer 2: ENGINE_BINARY_SHA env (e9d547c0/2ae93992)
- ✅ Layer 3: Manifest HMAC signing (f51f4e2e R6-T1)
- ✅ Layer 4: stderr to disk (f51f4e2e R6-T2)
- ✅ Layer 5: Signing key provisioning (3a425447)
- ❌ Layer 6（**新揭 round 5**）: Route handler exit=0 acceptance

**P0-NEW-2 修法（Round 9 必補）**：

選項 A — 區分 `spawn_died_early:exit=0`（推薦，最小改動）:

```python
# replay_routes.py:657-680 改成：
if pg_err and pg_err.startswith((
    "spawn_error:",
    "spawn_died_early:exit=0",  # ← 移除這條從 503 list
    "mkdir_error:",
    ...
)):
    raise HTTPException(503, ...)

# 加新 elif 處理 spawn_died_early:exit=0：
elif pg_err == "spawn_died_early:exit=0":
    # Subprocess completed fast (synthetic fixture < poll_grace).
    # Report on disk. Drive finalize directly from report file.
    # Read replay_report.json from output_dir, drive INSERT into
    # report_artifacts + simulated_fills + UPDATE run_state to completed.
    ... (call finalize_run_from_report() helper)
```

選項 B — 增加 poll_grace 到 5s（不推薦，繞過根因）:
- 5s 對 synthetic 10-event fixture 仍可能 < 跑完時間
- production 大 fixture 也許會跑超過 5s
- 改 grace 是 timing band-aid，不解決設計問題

選項 C — 不 sleep poll_grace 直接呼叫 proc.wait + 讀 report file（推薦但較大改動）:
- 改 spawn_replay_runner 為 synchronous wait pattern（合理因為 subprocess 是 short-lived）
- 直接讀 replay_report.json 後 driv INSERT
- finalize 變成 dispatch /run 的內聯動作

**推薦 Option A** — 最小範圍 fix，保留 spawn pattern，明確區分 exit=0 success path。

**Sprint A close gate（governance update v3）**：
- (A) hermetic pytest gate ✅ 已有
- (B) Linux runtime smoke (`OPENCLAW_REPLAY_E2E_SMOKE=1`) ✅ 部分（spawn 路徑驗了，route handler exit=0 路徑沒驗）
- (C) `/proc/$API_PID/environ` ENV 全套 grep ✅ 已有
- **(D) NEW: Route /run E2E acceptance test** — 必須測 register → /run → finalize → 4 表 row 全 > 0 整鏈，**不允許在 hermetic 直接呼叫 spawn_replay_runner 跳過 route handler**

**Sprint A 不可結案**：
- 4/4 acceptance 未達（2/4 partial PASS）
- /run → finalize → 寫盤鏈未通
- Sprint B（Wave 4-5 R4-R5）啟動條件未達

**派工建議**（push back PM）：
- @PA 派 round 9 派工 PR：選項 A 改 replay_routes.py + route_helpers.py + 新增 `finalize_run_from_report_on_disk()` helper
- @E1 改碼（小改 ~30 lines）
- @E2 review（重點：exit=0 path 不誤判 + finalize 鏈正確 trigger）
- @E4 加 hermetic test for route /run with synthetic fixture（明確驗 exit=0 → 200 OK）
- @QA round 6（將是 Sprint A R3 最終 acceptance）

---

### §18.8 教訓（追加 memory 用）

1. **5 round infra blocker chain 全清 ≠ Sprint A 達成**：round 5 揭示「route handler 邏輯」是隱藏的 6th layer。每一層 fix 都暴露下一層，這次是不同類型（不是 deploy infra，是 route control flow design）。
2. **Hermetic test 覆蓋率盲點**：R6-T4 直接測 `spawn_replay_runner`，但 production code path 是 `replay_routes.py → spawn_replay_runner → return`. 如果 hermetic 不測 route handler 完整路徑，將永遠看不到 `spawn_died_early:exit=0` 被誤映射到 503。Sprint A close gate 必加 (D) Route E2E test。
3. **API 503 不一定代表 subprocess 死**：route handler 可能在 subprocess 成功完成後仍 503。QA 必查 disk artifacts + api.log，不能只信 HTTP code。本 round 同樣的 `spawn_died_early:exit=0` 誤訊在 round 4 就已存在但因為 round 4 是 pre-spawn ValueError（沒走到 poll_grace），沒暴露。
4. **「Pathological clean-exit branch」是設計缺陷**：route_helpers.py:639-650 把「runner 跑得太快」歸類為失敗，違反「subprocess 成功完成 = 成功」的常識。需重新定義「成功路徑包含 exit=0 + report on disk」。
5. **subprocess 寫盤 + route 認為失敗 = 不一致 state**：run_state 標 failed 但 report 真實存在，造成「3 失敗 row + 3 真實成功 report on disk」分裂狀態。Operator 必跨 DB 與 disk 才能識別。
6. **/run + /finalize 應該是原子 transaction 或 idempotent retry**：當前設計下 503 → run_state.status=failed → finalize 拒絕，沒有 recovery path 從 disk report 補完 INSERT。建議 finalize 加 force-from-disk-report 模式 OR /run 把 finalize 整合為 inline call。

---

### §18.9 Round 5 verdict

**STATUS: STILL BLOCK，但 progression 真實 + root cause 已徹底定位**

5 round 累積成果：
- 5 layer infra blocker chain：100% 清光 ✅
- replay_runner subprocess：100% 真實執行 ✅
- HMAC sign + verify：100% 工作 ✅
- stderr disk diagnostic：100% 工作 ✅
- 4 表 acceptance：2/4 partial PASS（experiments + run_state 寫鏈通；report_artifacts + simulated_fills 寫鏈待 route fix）❌
- Wave 9 safety: GREEN ✅
- FK lineage: VALID ✅

**Round 6 必補單一 P0**: route_helpers.py:639-650 + replay_routes.py:657-680 區分 exit=0 成功路徑 + 加 finalize from disk report helper。預估 ~30-50 LOC + 1 hermetic route test。修完 Sprint A 才能結案進 Sprint B。

**push back PM**：不要 commit；不要走 P0 快速通道；走 §八 強制工作鏈派 round 6 PR。

---

## §19 RETRY LOG — Round 6 FINAL (post `2531c011` Layer 6 fix; 2026-05-05 02:05 UTC)

### §19.1 Layer 6 fix `2531c011` deploy verified

**Pre-flight 三角證據**：

| 項目 | 證據 |
|---|---|
| Git tree HEAD | `2531c01184dc17523db12bb53d023c1733eb1c5c`（Mac=Linux=origin/main 同步） |
| Working tree | `git status --porcelain` = empty（clean） |
| Commit chain | `2531c011`（layer 6 hotfix）→ `3a425447`（round 8 SIGNING_KEY env）→ `f51f4e2e`（round 6+7 HMAC sign + stderr）→ `e9d547c0`（round 4 verify）→ `2ae93992`（ENGINE_BINARY_SHA env） |
| API process started | 2026-05-05 02:03:46 UTC (pre-test, post-restart) |
| API_PID | 831234 |
| ENV: OPENCLAW_ENGINE_BINARY_SHA | `38c72877e526bfede74d57e6c9a90a682d323a2f80a0a9eef0e547f4d048d2f1` ✅ |
| ENV: OPENCLAW_REPLAY_FIXTURE_DEFAULT | `/home/ncyu/BybitOpenClaw/srv/rust/openclaw_engine/tests/fixtures/replay_runner_e2e/synthetic_btcusdt.json` ✅ |
| ENV: OPENCLAW_REPLAY_SIGNING_KEY_FILE | `/home/ncyu/BybitOpenClaw/srv/rust/openclaw_engine/tests/fixtures/replay_runner_e2e/key.hex` ✅ |

3 env all injected · git clean · binary deployed · API process started.

### §19.2 Phase 1-7 結果（每 step HTTP / SQL count / file existence）

#### Phase 1 — Login

```
HTTP=200
{"status":"ok","username":"398903348"}
```

✅ Login 成功；cookie 寫入 `/tmp/r3smoke6_cookie.txt`。

#### Phase 2 — Register experiment

```
EXP_KEY=r3smoke6-1777939521
HASH64=0000000000000000000000000000000000000000000000000000000000000000
HTTP=200
{"ok":true,"data":{"experiment_id":"1ba4f26c-25c1-45a2-8b5b-eafad565d1d4",
"manifest_hash":"95e44198d52108d7fc0c27731cf08b4e64e27ed7ebcd757d5e584404bc87bf1c",
"status":"created","created_at":"2026-05-05T02:05:22.009302+02:00",
"idempotency_hit":false},"degraded":false,"reason":null,"is_simulated":false,"data_category":"replay_lab"}
```

✅ Register 成功，EXPERIMENT_ID = `1ba4f26c-25c1-45a2-8b5b-eafad565d1d4`，manifest_hash 計算正常。

#### Phase 3 — POST /run

```
HTTP=200
{"ok":true,"data":{"run_id":"f7df9b917b094ac3ab8da9d15e7fa928",
"experiment_id":"1ba4f26c-25c1-45a2-8b5b-eafad565d1d4",
"started_at_ms":1777939526566,
"status":"running",
"subprocess_pid":null,
"subprocess_completed_in_poll":true,
"wiring_status":"pg_advisory_lock_path_active",
"output_dir":"/tmp/openclaw/replay_artifacts/f7df9b917b094ac3ab8da9d15e7fa928"},
"degraded":false,"reason":null,"is_simulated":false,"data_category":"replay_lab"}
```

✅ **LAYER 6 FIX VERIFIED 真實 ACTIVE**：
- HTTP 200（不再 503）
- `subprocess_completed_in_poll: true`（新 envelope flag working）
- `subprocess_pid: null`（Layer 6 sentinel `pid=-1` 在 response 序列為 null）
- `status: "running"`（route 不誤映射 exit=0 → failed）
- run_id = `f7df9b917b094ac3ab8da9d15e7fa928`

#### Phase 4 — Disk artifacts (跳過 wait，因 completed_in_poll=true)

```
/tmp/openclaw/replay_artifacts/f7df9b917b094ac3ab8da9d15e7fa928/
├── key.hex                   (65 bytes,  r------)
├── manifest.json             (440 bytes)
├── replay_report.json        (866 bytes)
├── replay_report.summary.txt (316 bytes)
└── replay_runner.stderr      (179 bytes)
```

✅ All 5 expected files written.

`replay_report.json`:
```json
{
  "schema_version": 1,
  "manifest_id": "1ba4f26c-25c1-45a2-8b5b-eafad565d1d4",
  "execution_confidence": "none",
  "result": {
    "status": {"kind": "completed"},
    "fills": [
      {"ts_ms": 1714521600000, "symbol": "BTCUSDT",
       "side": "long", "qty": 1.0, "price": 65050.0,
       "evidence_source_tier": "synthetic_replay"}
    ],
    "pnl_summary": {"events_processed": 10, "fills_emitted": 1,
                    "starting_balance": 10000.0, "ending_balance": 10630.0,
                    "net_pnl": 630.0},
    "diagnostics": {"guard_enforce_runtime_calls": 10,
                    "last_action_label": "on_event:BTCUSDT@1714522140000",
                    "abort_reason": null}
  }
}
```

`replay_runner.stderr`:
```
replay_runner: completed manifest_id=1ba4f26c-25c1-45a2-8b5b-eafad565d1d4 status=completed json=/tmp/openclaw/replay_artifacts/f7df9b917b094ac3ab8da9d15e7fa928/replay_report.json
```

✅ subprocess truly completed: 10 events / 1 fill / +630 net_pnl / 0 abort.

#### Phase 5 — POST /finalize

```
HTTP=200
{"ok":true,"data":{"run_id":"f7df9b917b094ac3ab8da9d15e7fa928",
"experiment_id":"1ba4f26c-25c1-45a2-8b5b-eafad565d1d4",
"status":"completed",
"report_artifact_id":"ce0cc720fb854f569db9015be929c944",
"report_artifact_registered":true,
"fills_inserted":1,
"fills_skipped":0,
"fills_truncated":0,
"writer_errors":["strategy_name_missing_from_v049_manifest_jsonb"]},
"degraded":false,"reason":null,"is_simulated":false,"data_category":"replay_lab"}
```

✅ **/finalize 接受 subprocess_pid=NULL 路徑（Layer 7 風險預警 NOT triggered）**：
- HTTP 200
- `fills_inserted: 1`（synthetic walker 1 fill 真實落 DB）
- `report_artifact_id`: `ce0cc720fb854f569db9015be929c944`（FIRST EVER WRITTEN）
- `report_artifact_registered: true`
- `status: "completed"`

⚠️ **小警告（NOT BLOCKER）**：`writer_errors: ["strategy_name_missing_from_v049_manifest_jsonb"]`
- 原因：smoke payload 的 `manifest_jsonb={"smoke":true}` 沒含 strategy/symbol 字段
- 影響：simulated_fills.strategy_name 預設為 `unknown_strategy`
- 風險：低 — Plan §6.R3 acceptance 不要求 strategy_name 正確，只要求 row > 0
- Sprint B 建議：register endpoint 把 strategy/symbol field 自動注入 manifest_jsonb

#### Phase 6 — 4 表 acceptance SQL（**SPRINT A R3 MOMENT OF TRUTH**）

```
experiments | run_state | report_artifacts | simulated_fills
4           | 4         | 1                | 1
```

🟢 **PASS — 4/4 全 > 0**：

| 表 | 累積 row | round 6 新增 | 狀態 |
|---|---:|---:|---|
| `replay.experiments` | 4 | +1 | ✅ Round 4 起持續累積（1→3→3→4） |
| `replay.run_state` | 4 | +1（status=completed）| ✅ Round 6 首次出現 status=completed（之前都 failed） |
| `replay.report_artifacts` | 1 | +1 | 🆕 **FIRST EVER WRITTEN** |
| `replay.simulated_fills` | 1 | +1 | 🆕 **FIRST EVER WRITTEN** |

**Sprint A R3 acceptance 全條件達成 — 不需任何 partial credit**。

#### Phase 7 — Wave 9 safety + FK lineage

**(7a) Wave 9 safety**：

| 條目 | 真實值 | 目標 | 狀態 |
|---|---:|---:|---|
| `trading.fills` last 15 min（leak detection） | 0 | = 0（必嚴格） | 🟢 PASS |
| `learning.governance_audit_log` `event_type LIKE 'replay_%'` last 15 min | 0 | < high severity | 🟢 PASS |

✅ **0 trading.fills leak**（replay 完全隔離 production trading 平面）
✅ **0 critical replay audit row**（無 governance violation triggered）

註：plan 給 SQL 用 `severity IN ('high','critical')` 但 `learning.governance_audit_log` schema **沒 severity column**（QA round 3 教訓 schema verify 後 SQL 移除 severity 條件，只用 event_type filter）。

**(7b) FK lineage 4/4 valid**：

| run_id | exp_id (run_state.manifest_id == experiments.experiment_id) | timeframe | status | exit_code | started_at |
|---|---|---|---|---|---|
| `f7df9b91-7b09-4ac3-ab8d-a9d15e7fa928` | `1ba4f26c-25c1-...-eafad565d1d4` ✅ matches | 1m | **completed** | 0 | 2026-05-05 02:05:26 |
| `1ef3a488-...` | `be2c51ff-...` ✅ matches | 1m | failed | — | 2026-05-05 01:44:01 (round 5) |
| `09da3571-...` | `bbcdff7e-...` ✅ matches | 1m | failed | — | 2026-05-05 01:32:17 (round 4) |
| `8817ed9f-...` | `94770e9e-...` ✅ matches | 1m | failed | — | 2026-05-04 23:50:08 (round 3) |

✅ FK 4/4 全有效 + status progression: 3 failed (round 3-5) → 1 completed (round 6) — 證明 progression 真實。

**(7c) report_artifacts 行內容**：

| artifact_id | run_id | artifact_type | byte_size | created_at |
|---|---|---|---:|---|
| `ce0cc720-fb85-4f56-9db9-015be929c944` | `f7df9b91-...` | `pnl_summary` | 866 | 2026-05-05 02:05:37 |

✅ FK 鏈：report_artifacts.run_id → run_state.run_id ✅；artifact_type='pnl_summary'（V050 design）；byte_size=866（與 disk replay_report.json 一致）。

**(7d) simulated_fills 行內容**：

| sim_fill_id | experiment_id | idempotency_key | ts_ms | symbol | strategy_name | side | qty | price | liquidity_role | evidence_source_tier | execution_model_version |
|---|---|---|---:|---|---|---|---:|---:|---|---|---|
| `85bbfe20-59a4-4dd8-9788-01fcb777ebd6` | `1ba4f26c-...` | `f7df9b917b094ac3ab8da9d15e7fa928:0` | 1714521600000 | BTCUSDT | unknown_strategy | long | 1 | 65050 | taker | **synthetic_replay** | synthetic_v1 |

✅ FK 鏈：simulated_fills.experiment_id → experiments.experiment_id ✅；idempotency_key=`<run_id>:<idx>` deterministic（V050 design：rerun 不雙重寫）；evidence_source_tier=`synthetic_replay` 符合 CLAUDE.md §九 non-training surface 要求。

### §19.3 Sprint A acceptance verdict — 4/4 PASS

🟢 **SPRINT A R3 ACCEPTANCE: ALL 4/4 GREEN**

| Plan §6.R3 acceptance condition | 達成 |
|---|---|
| (1) `replay.experiments` row > 0 | ✅ 4 row |
| (2) `replay.run_state` row > 0 | ✅ 4 row（含 1 completed）|
| (3) `replay.report_artifacts` row > 0 | ✅ 1 row（first ever）|
| (4) `replay.simulated_fills` row > 0 | ✅ 1 row（first ever，evidence_source_tier=synthetic_replay）|

**Sprint A R3 acceptance moment of truth — 已達**。

### §19.4 Wave 9 safety + FK lineage（GREEN）

| 安全項 | 真實值 | 狀態 |
|---|---:|---|
| `trading.fills` leak last 15m | 0 row | 🟢 GREEN |
| `learning.governance_audit_log` replay_* high/critical last 15m | 0 row | 🟢 GREEN |
| FK lineage `run_state.manifest_id` → `experiments.experiment_id` | 4/4 valid | 🟢 GREEN |
| FK lineage `report_artifacts.run_id` → `run_state.run_id` | 1/1 valid | 🟢 GREEN |
| FK lineage `simulated_fills.experiment_id` → `experiments.experiment_id` | 1/1 valid | 🟢 GREEN |
| `evidence_source_tier=synthetic_replay` 不污染 ML training | tier 嚴格 | 🟢 GREEN |
| `idempotency_key` 設計（`<run_id>:<idx>`） | rerun-safe | 🟢 GREEN |

### §19.5 Layer 7 揭示（**NONE — 無新 BLOCKER**）

Round 6 預警的 Layer 7 風險全部 **NOT triggered**：

| 預警項 | 預期風險 | 實際結果 |
|---|---|---|
| `/finalize` 對 `subprocess_pid IS NULL` 容忍度 | 可能 503 / 410 拒接 NULL pid | ✅ HTTP 200 + fills_inserted=1，完全接受 |
| synthetic walker fills array 為 0 | simulated_fills row=0 不達 acceptance | ✅ fills_emitted=1 in report，DB row=1 |
| `subprocess_completed_in_poll: true` 路徑下 status='running' 是否 confuse 後續邏輯 | 可能 race | ✅ /finalize 把 status=running → completed 平滑切換 |

**唯一邊角警告**（非 BLOCKER）：
- `writer_errors: ["strategy_name_missing_from_v049_manifest_jsonb"]` — 因 smoke payload manifest_jsonb 不含 strategy；不影響 row count，但 ML training 將看到 `strategy_name=unknown_strategy`。Sprint B 改 register endpoint 把 strategy/symbol 自動注入 manifest_jsonb。

**Sprint A 無 layer 7 揭示 → 無新 P0 BLOCKER → 可進 Sprint B**。

### §19.6 Sprint A close commit + Sprint B 啟動條件 recommendations

#### (A) PM 後續 close commit 內容建議

PM 收到本報告後可進行 Sprint A close commit（QA 不執行，QA 守 read-mostly 邊界）：

1. **更新 CLAUDE.md §三 REF-20 IMPL 狀態**：
   - 從 `closed-with-known-gap (Sprint A in flight)` → `Sprint A R3 closed (4/4 acceptance verified)`
   - 加上 round 6 final commit `2531c011` 與本 QA report path 為 evidence

2. **更新 TODO.md REF-20 entry**：
   - 標 R3 acceptance ✅ DONE（commit `2531c011` + QA round 6 PASS）
   - 啟動 Sprint B (R4-R5) 條目

3. **記錄 Sprint A close gate v3 完成（含 D 項）**：
   - (A) hermetic pytest gate ✅
   - (B) Linux runtime smoke (`OPENCLAW_REPLAY_E2E_SMOKE=1`) ✅（每次 round 都跑）
   - (C) `/proc/$API_PID/environ` 3 env grep ✅
   - (D) Route /run E2E acceptance test ✅（round 6 真實 PASS — 走完整 register → /run → finalize → 4 表 row > 0 路徑）

4. **REF-20 evidence trail**：將 round 1-6 演化壓縮成「6 layer blocker chain 漸進排除」做 future Sprint A-D 回顧樣本：
   - L1 from __future__ annotations ✓ (round 2 cad8ed84)
   - L2 ENGINE_BINARY_SHA missing ✓ (round 4 e9d547c0/2ae93992)
   - L3 placeholder signature ✓ (round 6+7 f51f4e2e)
   - L4 stderr DEVNULL ✓ (round 6+7 f51f4e2e)
   - L5 signing key not provisioned ✓ (round 8 3a425447)
   - L6 exit=0 误判 failure ✓ (round 9 2531c011)

#### (B) Sprint B (R4-R5) 啟動條件 — 全部達成

| 條件 | 狀態 |
|---|---|
| Sprint A R3 4/4 acceptance | 🟢 PASS |
| Wave 9 safety 0 trading.fills leak | 🟢 PASS |
| FK lineage 全 valid（experiments / run_state / report_artifacts / simulated_fills 4 條 FK 鏈） | 🟢 PASS |
| `evidence_source_tier='synthetic_replay'` 不污染下游 ML pipeline | 🟢 PASS（CLAUDE.md §九 non-training surface 規則已 ship） |
| Plan V1 Sprint B scope (R4-R5: real backtest engine + IntentProcessor wiring) | 待 PM 派 PA 啟動 |

**Sprint B 啟動 0 BLOCKER**。

#### (C) 後續 follow-up（非 BLOCKER but Sprint B 應處理）

1. **P3 — register endpoint 自動注入 strategy/symbol 到 manifest_jsonb**
   - 當前：smoke payload 沒填 strategy/symbol → manifest_jsonb 缺 → simulated_fills.strategy_name='unknown_strategy'
   - 修法：register endpoint accept top-level `strategy` / `symbol` field 並注入 manifest_jsonb（同時保留向後相容性）
   - 影響：替 Sprint B+C 真實策略 backtest 預備正確 strategy_name，避免 unknown_strategy 累積

2. **P3 — V050 manifest_jsonb fail-soft strategy 字段提取**
   - replay_writer.py 寫 simulated_fills 時 fall-back 到 `'unknown_strategy'` 是 fail-soft，但持續累積 unknown_strategy row 會污染 attribution analysis
   - 建議：writer 看到 manifest_jsonb 缺 strategy 時 emit `governance_audit_log` warn entry（不阻斷寫盤）

3. **P3 — Sprint A 手動 verify 完成後加 cron 化**
   - 建議：把本 round 6 acceptance pipeline（Phase 1-7）寫成 `helper_scripts/canary/replay_e2e_smoke.py`，每日 1 次跑 sanity check
   - 與 healthcheck 框架對齊（CLAUDE.md §七 被動等待 TODO 必附 healthcheck）

### §19.7 結論

🟢 **Sprint A R3 ACCEPTANCE: PASS**
🟢 **Sprint A 達成 close 條件**
🟢 **Sprint B 啟動 0 BLOCKER**

push back PM 進行 close commit + Sprint B 派工。QA round 6 是 Sprint A R3 final acceptance，後續無需 round 7。

**6-Layer blocker chain 100% 排除 evidence**：
- 4 表 acceptance: 4/4 GREEN（first-ever simulated_fills + report_artifacts row）
- subprocess truly completed (rc=0, 10 events, 1 fill, +630 PnL)
- HMAC sign + verify cycle 工作
- stderr disk diagnostic 工作
- /run + /finalize chain 工作
- Wave 9 safety GREEN
- FK lineage 4/4 valid

REF-20 進入「**closed-with-real-evidence**」label — Sprint A 完成。Sprint B (Wave 4-5 R4-R5) 由 PM 派 PA 啟動。

---


