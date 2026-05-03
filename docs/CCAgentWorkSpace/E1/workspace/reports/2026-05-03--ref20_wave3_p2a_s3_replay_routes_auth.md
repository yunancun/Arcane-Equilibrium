# REF-20 Wave 3 P2a-S3 — replay_routes.py 8-route auth scaffold

**Date:** 2026-05-03
**Owner:** E1
**Task:** R20-P2a-S3 — 8 routes auth scaffolding (global cap=1, per-actor cap=1) in NEW `replay_routes.py`
**Spec:** REF-20 V3 §3 G3 + §6 (Replay Runner Contract) + §12 #3 (route_auth) + §12 #22 (safe_query mirror)
**Workplan:** `docs/execution_plan/2026-05-03--ref20_implementation_workplan_v1.md` §4 Wave 2 R20-P2a-S3
**Wave 3 dispatch:** `docs/execution_plan/2026-05-03--ref20_wave2_dispatch_v1.md` §3.1 (P2a security batch)

---

## 1. 任務摘要

新建 `replay_routes.py` 提供 Paper Replay Lab 的 8 條 REST endpoint，掛在 `/api/v1/replay`。本 commit 僅 land **AUTH + CONCURRENCY scaffolding**：

- 8 routes 全套 `Depends(base.current_actor)` 認證；變更類 route 額外要求 Operator + `replay:write` scope。
- 全局 active run cap = 1（V3 §5 P2/P3 不變量），per-actor active run cap = 1，cap 超出 → 409（不是 5xx）。
- `_safe_pg_select` wrapper 鏡像 `agents_routes_helpers` 的 PG-degraded-safe pattern（V3 §12 #22 acceptance binding）。
- Audit emit 為 STUB（log only），Wave 4 R20-P2b-T2 才 wire 實際 INSERT。
- 0 wiring 到 `replay_runner` Rust 二進位、0 INSERT 到 `trading.*`／live config、0 schema mutation、0 修改既有 `auth_routes_common.py` / `scout_routes.py` / `risk_routes.py`。

---

## 2. 修改清單（4 file）

| 路徑 | 變更 | 性質 | LOC |
|---|---|---|---|
| `program_code/exchange_connectors/bybit_connector/control_api_v1/app/replay_routes.py` | 新檔 | A | 902 |
| `program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_replay_routes_auth.py` | 新檔 | A | 281 |
| `program_code/exchange_connectors/bybit_connector/control_api_v1/app/main.py` | 修（+12 LOC，註冊 replay_router）| M | 665（base 653+12） |
| `docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-03--ref20_wave3_p2a_s3_replay_routes_auth.md` | 新檔（本檔） | A | — |

memory append 為第 5 個動作（不算上面 4 file）。

---

## 3. 關鍵 diff

### 3.1 8 endpoints (per dispatch §"Required reading" + V3 §6)

```python
@replay_router.post("/run")          # start replay run (Operator+replay:write)
@replay_router.get("/status")        # current run status (auth-only)
@replay_router.post("/cancel")       # cancel running replay (Operator+replay:write)
@replay_router.get("/report/{experiment_id}")  # fetch report (auth-only)
@replay_router.get("/manifests")     # list manifests for actor (auth-only)
@replay_router.post("/manifest/verify")        # verify manifest signature (Operator+replay:write)
@replay_router.get("/health/signature")        # health probe (auth-only)
@replay_router.get("/list")          # list replay experiments (auth-only)
```

### 3.2 Concurrency cap enforcement（核心 IMPL）

```python
async def _check_run_caps(actor_id: str) -> None:
    # PRECONDITION: caller must already hold _ACTIVE_RUNS_LOCK.
    global_count = len(_ACTIVE_RUNS)
    if global_count >= GLOBAL_ACTIVE_RUN_CAP:
        if actor_id in _ACTIVE_RUNS:
            raise HTTPException(409, detail={
                "reason_codes": ["replay_per_actor_cap_exceeded"], ...
            })
        raise HTTPException(409, detail={
            "reason_codes": ["replay_global_cap_exceeded"], ...
        })
    if actor_id in _ACTIVE_RUNS:
        raise HTTPException(409, detail={
            "reason_codes": ["replay_per_actor_cap_exceeded"], ...
        })

@replay_router.post("/run")
async def post_replay_run(body, actor=Depends(base.current_actor)):
    _require_replay_write(actor)
    actor_id = str(actor.actor_id)
    async with _ACTIVE_RUNS_LOCK:        # atomic check-and-set
        await _check_run_caps(actor_id)
        run_id = uuid.uuid4().hex
        _ACTIVE_RUNS[actor_id] = {...}
    _emit_audit_stub(...)
    return _replay_response({...})
```

關鍵不變量：`_check_run_caps` + 插入 `_ACTIVE_RUNS` 必在同一 `async with _ACTIVE_RUNS_LOCK:` 內，避免 TOCTOU race。

### 3.3 _safe_pg_select wrapper (V3 §12 #22 mirror)

```python
def _safe_pg_select(sql: str, params) -> tuple[list, str | None]:
    rows = []
    with get_pg_conn() as conn:
        if conn is None:
            return rows, "pg_unavailable"
        try:
            cur = conn.cursor()
            cur.execute("SET LOCAL statement_timeout = %s", (_STATEMENT_TIMEOUT_MS,))
            cur.execute(sql, tuple(params))
            return list(cur.fetchall()), None
        except Exception as exc:
            return rows, f"pg_error:{type(exc).__name__}"

async def _async_safe_pg_select(sql, params):
    return await asyncio.to_thread(_safe_pg_select, sql, params)
```

Wave 2 scaffold 階段尚無 endpoint 實際 query PG（因 V### migration 屬 Wave 3 P2a-S6 後續）；helper 已就緒供 Wave 4 wiring 直接呼叫。

### 3.4 Auth 層

- **Read-only routes**（status / report / manifests / health/signature / list）：僅 `Depends(base.current_actor)`。401 on missing token；403 自動由 `current_actor` 處理（無 scope check 因 read-only）。
- **Mutating routes**（run / cancel / manifest/verify）：`_require_replay_write(actor)` → `require_scope_and_operator(actor, "replay:write")` → 401（unauth） / 403（無 scope/role）/ 200（happy）。
- **manifest/verify**：Wave 2 scaffold 直接 raise 501（reason `replay_verify_not_wired`），因 ManifestSigner 已就緒但 SQL KeyArchive 屬 P2a-S4。

### 3.5 main.py register

L262-272 註冊 replay_router。位置：在 `agents_router` 之後、`Startup Integrity Check` 之前，與其他 22 個 router 同 pattern。

---

## 4. 治理對照（CLAUDE.md §七 + V3 §3 G3 + §12 acceptance）

### 跨平台兼容性（§七 ★★ 強制）

- ✅ 0 hardcoded `/home/ncyu` 或 `/Users/<name>` literal — `grep -nE '/home/ncyu|/Users/[^/]+'` 0 hit on both new files。
- ✅ 0 platform-specific imports（純 stdlib + fastapi + pydantic）。
- ✅ `health/signature` 使用 `os.environ.get("OPENCLAW_SECRETS_DIR")`（per CLAUDE.md §六），不 log 實際路徑（operator privacy）。

### 雙語注釋（§七 強制）

- ✅ Module-level MODULE_NOTE 中英對照（L4-L107），含 8 routes 列表 + 9 條 hard contracts + spec/workplan/dispatch 引用。
- ✅ 每個 endpoint docstring 中英對照（含 auth/scope 要求 + Wave 階段標註）。
- ✅ 每個 helper（`_check_run_caps` / `_emit_audit_stub` / `_safe_pg_select` / `_async_safe_pg_select` / `_replay_response` / `_require_replay_write`）docstring 中英對照。
- ✅ Pydantic model docstring 中英對照（`ReplayRunRequest` / `ReplayCancelRequest` / `ReplayManifestVerifyRequest`）。
- ✅ 不變量 / TODO marker 全雙語（如 L307 PRECONDITION / L391 TODO REF-20 R20-P2b-T2）。
- ✅ Test 檔 MODULE_NOTE + 每 case docstring 雙語。

### 硬邊界守則（§七）

- ✅ `max_retries / live_execution_allowed / execution_authority / system_mode`：0 hit on new file。
- ✅ Wave 4 marker（`scaffold_only_no_runner_spawned` / `TODO REF-20 R20-P2b-T2`）標記所有 deferred wiring 點。
- ✅ 0 wiring 到 `replay_runner` 二進位、Decision Lease、IPC server、build_exchange_pipeline。
- ✅ 0 INSERT/UPDATE/DELETE statement on `trading.*` / live config / advisory tables。

### LOC budget（§九）

- ⚠️ `replay_routes.py` **902** LOC > 800 警告線（< 1500 hard limit）。**E2 必須標記。**
  - 理由：MODULE_NOTE 雙語 (~100 LOC) + 8 endpoint docstring 雙語 (~250 LOC) + 9 條 hard contract 注釋 + Wave 4 TODO marker + Pydantic model 雙語 docstring。實質代碼 < 350 LOC。
  - 拆分風險：拆 helpers 到 `replay_routes_helpers.py` 增加 indirection，且本 phase 8 routes 全屬同一 logic domain（auth + cap + safe_pg + stub audit），不適合按職責拆。
  - 建議：E2 review 接受 800-1500 範圍（per `agents_routes.py` precedent — `agents_routes_helpers.py` 為避免 single file > 800 才拆）；若 Wave 4 wiring 後接近 1200-1500，再拆 `replay_routes_helpers.py`。
- ✅ `test_replay_routes_auth.py` 281 LOC < 800 警告線。
- ✅ `main.py` 665 LOC（+12）< 800 警告線。

### Singleton 登記（§九 表 — 待補入）

| Singleton | 創建位置 | 用途 |
|---|---|---|
| `_ACTIVE_RUNS: dict[str, dict[str, Any]]` | `app/replay_routes.py` L160 | In-memory active run state；Wave 4 R20-P2b-T2 切換 PG advisory lock |
| `_ACTIVE_RUNS_LOCK: asyncio.Lock` | `app/replay_routes.py` L168 | TOCTOU guard for atomic cap check + run insert |
| `replay_router: APIRouter` | `app/replay_routes.py` L121 | 8-route APIRouter mounted on `/api/v1/replay` |

**E2 review action item**：補入 CLAUDE.md §九 singleton table。本 commit 標出但未自行修改 CLAUDE.md（per CLAUDE.md §七「meta-doc 改動用 git commit --only」要求；CLAUDE.md 修改由 PM commit 統一安排）。

### V3 §3 G3 + §12 #3 acceptance binding

- ✅ #3 `replay_route_auth_contract`：4-mode test (unauth / global cap / per-actor cap / happy path) 全 PASS。
- ✅ #22 `replay_routes_use_safe_query_pattern`：`_safe_pg_select` mirror agents_routes_helpers pattern；E2 chaos drill PG kill simulation 應驗 200+degraded（本 PR 尚無 PG-touching endpoint，wrapper 就緒供 Wave 4 wiring 直接呼叫）。
- ✅ G3 8 routes auth contract：每 route 認證 dependency 注入清楚；mutating routes 有 scope+role guard；read-only routes 僅 auth。

---

## 5. 驗證

### 5.1 Pytest 4/4 PASS

```
$ cd .../control_api_v1 && python3 -m pytest tests/test_replay_routes_auth.py -v
============================= test session starts ==============================
collected 4 items

tests/test_replay_routes_auth.py::test_unauthenticated_post_run_returns_401 PASSED [ 25%]
tests/test_replay_routes_auth.py::test_authenticated_zero_active_run_post_run_accepts PASSED [ 50%]
tests/test_replay_routes_auth.py::test_authenticated_per_actor_cap_returns_409 PASSED [ 75%]
tests/test_replay_routes_auth.py::test_authenticated_global_cap_returns_409 PASSED [100%]

========================= 4 passed, 1 warning in 0.19s =========================
```

剩 1 warning：Pydantic v1 `@validator` deprecation。**與 codebase 一致（scout_routes.py 用同 pattern）**；若 PM 決定 codebase-wide migrate 到 Pydantic v2 `@field_validator`，可同步處理。本 PR 不擴張範圍。

### 5.2 py_compile + main.py 整合

```
$ python3 -m py_compile .../replay_routes.py
SYNTAX OK

$ python3 -m py_compile .../main.py
MAIN.PY SYNTAX OK

$ python3 -c "from app.main import app; ..."
main.py imports OK with replay_router
routes count: 248
replay routes: ['/api/v1/replay/cancel', '/api/v1/replay/health/signature',
                '/api/v1/replay/list', '/api/v1/replay/manifest/verify',
                '/api/v1/replay/manifests', '/api/v1/replay/report/{experiment_id}',
                '/api/v1/replay/run', '/api/v1/replay/status']
```

8/8 routes 全註冊（注意 `/manifest/verify` 路徑符合 dispatch §"Required reading" 4 — POST /api/v1/replay/manifest/verify）。

### 5.3 雙端 grep 守則

```
$ grep -nE '/home/ncyu|/Users/[^/]+' .../replay_routes.py .../test_replay_routes_auth.py
(0 hit)

$ grep -n "INSERT\|UPDATE\|DELETE" .../replay_routes.py
(only docstring/comment references describing Wave 4 deferred wiring; 0 actual SQL statement)
```

---

## 6. 不確定之處 / Ambiguity（給 E2 + E3 review）

### A. governance_audit_log event_type enum 擴展時機

V035 schema 限 `event_type` ∈ {review_live_candidate, lease_grant, lease_auto_revoke, bulk_re_evaluation, audit_write_failed}。本 PR `_emit_audit_stub` 用 `replay_run_started` / `replay_run_cancelled` / `replay_manifest_verify_attempted` 等字串標記 event type，但**僅 log，未 INSERT**。Wave 4 R20-P2b-T2 wiring 時必先 PM 決定：

- **選項 A**（schema 擴展）：新 V### migration 擴 V035 enum 加 `replay_run_started` / `replay_cancelled` / `replay_handoff` 三 enum value。
- **選項 B**（reuse audit_write_failed + alert_type）：mirror P2a-S1 cron pattern（reports `2026-05-03--ref20_p2a_s1_signing_key_rotation_cron.md` §"Audit row 用 V035 既有 enum"），用 `event_type='audit_write_failed'` + `payload->>'alert_type'='replay_run_started'` 等 discriminator。

E1 建議**選項 A**（schema-clean 較佳，replay 是 first-class governance event）；但若 PM 決定避免 schema churn，選項 B 可行。本 PR stub 兩個選項皆可後續 wire。**留給 PM Wave 4 dispatch 決定。**

### B. `_ACTIVE_RUNS` 是 process-local，多 uvicorn worker race

uvicorn 若用 `--workers 4` 跑，`_ACTIVE_RUNS` 是 process-local dict → 4 worker 各自管 1 run = 全局實際允許 4 個 active run，破 V3 §5 「global cap=1」契約。

**緩解**：
- 當前 dev runtime 用 `uvicorn --workers 1`（per `restart_all.sh` 既定設定，need to verify with E2/PM）→ 本實作正確。
- Wave 4 R20-P2b-T2 切換 PG advisory lock（`pg_try_advisory_lock(<replay_global_run>)`）即可 robust 防多 worker。
- 若 PM 確認 production 走 `--workers >1`，本 PR 必加額外 process-shared lock（如 file lock 或 redis lock）。

E1 建議：E2 review 時與 PM 確認 production worker count；若 >1，補 process-shared lock。本 PR 結構不擋此補強。

### C. `health/signature` 未 require write scope，是否會洩漏 fingerprint timing？

`health/signature` 只回 `module_importable` / `secrets_dir_env_set` / `fail_modes_count`，**不**回 fingerprint 或 secrets path。讀-only health probe 慣例對 authenticated user 全開（mirror `/api/v1/healthz`）。

E3 應 review：是否 `secrets_dir_env_set` 即「環境配置 yes/no」這種非 secret 資訊也應限 Operator？目前判斷不需要（auth 已防匿名，且不洩漏 path 內容）。

### D. Test fixture mock vs real auth chain

Test 用 `app.dependency_overrides[current_actor] = _operator_actor_alice`（`AuthenticatedActor` 直接 fabricate），bypass `current_actor` 真實 cookie / Bearer token check。**Case 1（unauth）特意不掛 override** 跑真實 chain → 確認 401 路徑工作。其他 case 用 mock 即可。

E2 reviewer 可能想看 happy path 也跑真實 token chain（HMAC compare）；本 PR 設計優先 cap test coverage，token chain 在 `test_batch_b_security_auth.py` 等既有 test 已驗。Cross-route 行為一致由 `Depends(current_actor)` 共用保證。

### E. POST /run body 接受任意 well-formed `experiment_id`，未驗 DB 存在

Wave 2 scaffold 階段未接 PG（因 V### migration 在 Wave 3 P2a-S6 後續）。`experiment_id` 只做 alphanumeric+`-_` 形狀驗證 + 長度上限，**不驗 `replay.experiments` 是否有對應 row**。

Wave 4 R20-P2b-T2 IMPL 必加：`SELECT status FROM replay.experiments WHERE experiment_id = %s` → 必為 `created` / `running`（非 `completed/failed/cancelled`）+ `signature_verified=true`，否則 422。本 PR scaffold 接受任何合法 id（合理，因 DB 尚無表）。

### F. Audit emit STUB 0 INSERT vs dispatch §"audit log"

Dispatch §(B) 寫「Audit log (governance_audit_log) 記錄每次 run/cancel/handoff with actor + ts + action + manifest_id」。本 PR 僅 log（INFO level）+ 標 TODO；無 INSERT。理由：

1. PR 紅線 §"0 INSERT 寫入 trading.* / live config" — `learning.governance_audit_log` 雖屬 learning schema，但 enum CHECK 不允許 `replay_*` event_type，硬寫會 trigger CHECK failure。
2. 等 Wave 4 PM 決策 §6.A 後（schema 擴 vs reuse），統一加 INSERT + healthcheck。
3. 本 PR stub 已留出 wiring 點（`_emit_audit_stub` 簽名穩定，Wave 4 改 body 即可，caller 0 改動）。

E2 應確認此設計符合 dispatch 意圖（scaffold 階段 audit 用 log 取代 INSERT）。若 PM 要求即刻寫，需先派 V### migration 擴 enum（不在本 PR scope）。

---

## 7. PM commit message draft

```
feat(replay): replay_routes.py 8-endpoint auth scaffold (Wave 3 P2a-S3)

REF-20 Wave 2 R20-P2a-S3. New `replay_routes.py` exposes the 8 Paper
Replay Lab endpoints under `/api/v1/replay`:
  - POST /run, /cancel, /manifest/verify   (Operator + replay:write)
  - GET  /status, /report/{id}, /manifests, /health/signature, /list
                                            (auth-only, read-only)

Auth + concurrency scaffolding only; runtime wiring to the
`replay_runner` Rust binary is deferred to Wave 4 R20-P2b-T2:
  - global active run cap = 1 (V3 §5 P2/P3 invariant)
  - per-actor active run cap = 1
  - cap exceeded → 409 (NOT 5xx) with reason_codes
    {replay_global_cap_exceeded, replay_per_actor_cap_exceeded}
  - in-memory dict + asyncio.Lock for atomic check-and-set; PR §6.B
    flags multi-worker race for PM/E2 review
  - _safe_pg_select wrapper mirrors agents_routes_helpers
    PG-degraded-safe pattern (V3 §12 #22 acceptance binding); ready
    for Wave 4 wiring once V### replay migration lands

Audit emit is STUB (log INFO only; PR §6.A flags PM decision required
on V035 enum extend vs reuse audit_write_failed + alert_type
discriminator). 0 actual INSERT on this PR.

Tests: 4/4 PASS at
  tests/test_replay_routes_auth.py
covering V3 §12 #3 route_auth_contract:
  - Case 1: unauth POST /run → 401
  - Case 2: auth + 0 active run → 200
  - Case 3: auth + per-actor cap → 409 replay_per_actor_cap_exceeded
  - Case 4: auth + global cap (cross-actor) → 409 replay_global_cap_exceeded

Files:
  + program_code/exchange_connectors/bybit_connector/control_api_v1/app/replay_routes.py (902 LOC)
  + program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_replay_routes_auth.py (281 LOC)
  M program_code/exchange_connectors/bybit_connector/control_api_v1/app/main.py (+12 LOC, register replay_router)
  + docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-03--ref20_wave3_p2a_s3_replay_routes_auth.md

Notes:
  - replay_routes.py 902 LOC > §九 800 warning line; E2 review must
    flag (mostly bilingual MODULE_NOTE + 8 endpoint docstrings + Wave 4
    TODO markers; substantive code <350 LOC).
  - Singleton table additions (_ACTIVE_RUNS / _ACTIVE_RUNS_LOCK /
    replay_router) → CLAUDE.md §九 to be patched in PM commit.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
```

---

## 8. Operator 下一步

### 強制工作鏈（CLAUDE.md §七 + §八）

1. **E2 code review**（必跑）— 焦點：
   - 902 LOC > 800 警告線：accept-and-flag vs split into helpers（建議 accept；理由見 §4 LOC budget）。
   - `_ACTIVE_RUNS` process-local dict + uvicorn worker count 確認（§6.B）。
   - `_emit_audit_stub` 0 INSERT 是否符合 dispatch §"audit log" 意圖（§6.F）— PM 決策 enum extend vs alert_type discriminator。
   - 8 routes auth dependency injection 一致性 + 401/403/409 fail-closed 路徑全覆蓋。
   - Singleton 表登記建議加入 CLAUDE.md §九。

2. **E3 security review**（必跑）— 焦點：
   - Mutating routes（run/cancel/manifest/verify）`_require_replay_write` scope+role guard 正確。
   - `health/signature` 0 secret leak（§6.C）。
   - `experiment_id` validator 防 path injection（alphanumeric + hyphen + underscore only）。
   - manifest/verify 501 stub 是否符合 V3 §5 fail-closed 紅線（簽名驗證模組就緒但 SQL KeyArchive 待 P2a-S4）。

3. **E4 regression test**（強制）— 跑 sibling tests 確認 0 break：
   - `pytest tests/test_agents_routes.py` 應 pass（agents_routes 未動）
   - `pytest tests/test_batch_b_security_auth.py` 應 pass
   - `pytest tests/test_authorization_state_machine.py` 應 pass
   - `pytest tests/replay/test_manifest_signer_xlang_consistency.py` 應 pass（P2a-S2 sibling）
   - `python3 -c "from app.main import app"` 應 import OK（已驗 §5.2）

4. **PM sign-off + commit + push**（PM 統一）— 含 CLAUDE.md §九 singleton table 補登。

### 後續 Wave 工作

- **Wave 4 R20-P2b-T2** sub-agent：wire 8 routes 到 `replay_runner` Rust 二進位 + 真實 PG SELECT/INSERT；本 PR helpers (`_safe_pg_select` / `_async_safe_pg_select`) 直接可用。
- **Wave 3 R20-P2a-S4** sub-agent：land V### migration + DB role REVOKE/GRANT；其後 `_emit_audit_stub` 改 INSERT（PM 決策 enum extend vs alert_type 後）。
- **Wave 4 R20-P2b-T1** sub-agent：isolated `replay_runner` wrapper land 後，本 PR `/run` endpoint TODO marker 處 wire IPC spawn。

---

E1 IMPLEMENTATION DONE: 待 E2 審查（report path: `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-03--ref20_wave3_p2a_s3_replay_routes_auth.md`）
