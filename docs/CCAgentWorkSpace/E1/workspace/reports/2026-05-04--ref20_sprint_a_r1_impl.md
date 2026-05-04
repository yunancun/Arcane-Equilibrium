# REF-20 Sprint A R1 — E1 IMPLEMENTATION DONE

**日期：** 2026-05-04
**Owner：** E1
**Sprint：** REF-20 Sprint A (R1: Runtime Usability — binary path / health route / unit tests)
**派發來源：** PA partition
`/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-04--ref20_sprint_a_task_dag.md`
**接續：** 前任 E1 stream timeout 中斷後的 R1-T3 route handler + R1-T5 unit tests 補完
**狀態：** IMPLEMENTATION DONE — 待 E2 review / E4 regression / PM 統一 commit

---

## §1. R1-T3 route handler — 完成證明

### 1.1 動作

在 `app/replay_routes.py` `/health/signature` 之前加 `@replay_router.get("/health")`
handler（以 PA design doc 範本為準）：

- Auth = `Depends(base.current_actor)`（與 `/health/signature` 對齊；不要求
  `replay:write`，monitoring infra 無 write scope 亦可 probe）
- 內部 SQL 透過 `_async_safe_pg_select(...)` 跑 V045 `replay.run_state` +
  V049 `replay.experiments` 雙路存在性 probe
- 結果交 `_compute_replay_health_state(rows=..., pg_err=...)`（已 import 在
  line 80 的 module-level alias）digest 成 9-field dict
- envelope 透過 `_replay_response(data=..., degraded=..., reason=...)` 回；
  `wiring_status != "ready"` → degraded=True + reason=`wiring_status:<state>`
- 雙語 docstring：模組目的 / 4 條 pre-condition / wiring_status 優先級全 EN+中

### 1.2 grep 證明

```text
$ python3 -c "from program_code....replay_routes import replay_router; \
  print([r.path for r in replay_router.routes if 'health' in r.path])"
['/api/v1/replay/health', '/api/v1/replay/health/signature']
```

兩條 health route 同時掛載；`/health` 在 `/health/signature` 前面（與 PA plan
ordering 一致）。`replay_router.routes` 總數從 prior 8 升為 9。

### 1.3 LOC 防線

`replay_routes.py` 1492 LOC（PA plan 要求 ≤ 1500 ✓）。詳見 §3。

---

## §2. R1-T5 unit tests — 完成證明

### 2.1 動作

新增 `tests/test_replay_route_helpers_binary_resolution.py`，5 case 覆蓋
R1-T1 接好的 5-step fallback chain（`replay/route_helpers.py
::resolve_replay_runner_bin`）：

| Test | 階段 | 驗證 |
|---|---|---|
| `test_env_override_takes_precedence` | 1 | `OPENCLAW_REPLAY_RUNNER_BIN` env override 壓過所有其他佈局，連 workspace release 同時落盤也勝出 |
| `test_workspace_release_preferred` | 2 | override unset + workspace `rust/target/release` 落盤 → 回 workspace release（2026-04-15 cargo workspace 合併後真實佈局）|
| `test_workspace_debug_fallback` | 3 | workspace release 缺 + debug 存在 → 回 workspace debug；sanity 驗 release 不存在 |
| `test_legacy_release_fallback` | 4 | workspace target 缺 + legacy nested release 存在 → 回 legacy release；sanity 驗 workspace 兩路徑都不存在 |
| `test_all_paths_absent_returns_legacy_debug_path` | 5 | 全空 → 回 legacy debug 路徑（caller 透過 503 surface）；額外驗回傳 path 不存在 |

每個 test：
- `monkeypatch.delenv("OPENCLAW_REPLAY_RUNNER_BIN", raising=False)` 隔離 prior env
- 用 `tmp_path` 處理檔案系統，**不**寫死 `/home/ncyu` / `/Users/ncyu`
- 真正 assert（assertion message 含實際 vs 預期）
- 雙語 docstring（function header + inline 不變量）
- import pattern 與既有 5 個 `test_replay_routes_*.py` 對齊（`_test_dir +
  _control_api_dir + sys.path.insert + from replay.route_helpers import ...`）

### 2.2 pytest 5/5 PASS

```text
$ python3 -m pytest -xvs program_code/.../tests/test_replay_route_helpers_binary_resolution.py
============================= test session starts ==============================
platform darwin -- Python 3.10.1, pytest-9.0.3, pluggy-1.6.0
collected 5 items

...test_env_override_takes_precedence PASSED
...test_workspace_release_preferred PASSED
...test_workspace_debug_fallback PASSED
...test_legacy_release_fallback PASSED
...test_all_paths_absent_returns_legacy_debug_path PASSED

============================== 5 passed in 0.03s ===============================
```

5/5 GREEN。

---

## §3. replay_routes.py LOC（governance）

### 3.1 LOC 演進

| 步驟 | LOC | Δ |
|---|---:|---:|
| Pre-task baseline | 1495 | — |
| 加 `/health` route （草案，~70 LOC 含完整雙語 docstring）|  ~1565 | +70 |
| **+ 抽 3 model 至 `replay_models.py` + import alias** | 1492 | **-3 net vs baseline** |
| 同時刪 dead `from pydantic import BaseModel, Field, validator`（移走 model 後不再使用）| 1492 | inline |

最終 1492 ≤ 1500，governance 達標。

### 3.2 LOC 自檢

```text
$ wc -l program_code/.../app/replay_routes.py
    1492 program_code/exchange_connectors/bybit_connector/control_api_v1/app/replay_routes.py
```

---

## §4. `replay_models.py` 抽出清單與行為等同證明

### 4.1 抽出清單（3 class，行為位元等同）

| Class | 抽出來源（pre-edit） | 抽出去處 |
|---|---|---|
| `ReplayRunRequest` | `replay_routes.py:154-193`（40 LOC 含 `_validate_experiment_id` validator）| `replay/replay_models.py:42-79` |
| `ReplayCancelRequest` | `replay_routes.py:196-213`（18 LOC）| `replay/replay_models.py:82-99` |
| `ReplayManifestVerifyRequest` | `replay_routes.py:216-243`（28 LOC）| `replay/replay_models.py:102-130` |

### 4.2 行為等同保證

- **同 class 名 / 同 field shape / 同 validator / 同 docstring 字面**：直接 copy-paste
  + 重排成獨立 module；無 model semantics 改動
- **import 路徑保持不變**：`replay_routes.py` 用 try/except dual-path（relative
  package first；absolute fallback for test layout via conftest's PROJECT_ROOT
  injection），mirror 既有 `from ..replay import route_helpers as _rh` pattern
- **`__all__` 對外 API 不變**：`replay_routes.__all__` 仍含三個 model name；
  外部 caller `from .replay_routes import ReplayRunRequest` 等寫法繼續工作（**module-level
  alias 透過 import 重新 expose**）

### 4.3 driver 證據

```text
$ python3 -c "from program_code....replay_routes import \
    replay_router, ReplayRunRequest, ReplayCancelRequest, ReplayManifestVerifyRequest; \
    print(ReplayRunRequest.__name__, ReplayCancelRequest.__name__, ReplayManifestVerifyRequest.__name__)"
ReplayRunRequest ReplayCancelRequest ReplayManifestVerifyRequest
```

3 個 class 都還能從 `replay_routes` 匯入、`__name__` 對齊 → 對 GUI / OpenAPI
schema generation / 既有 5 個 `test_replay_routes_*.py` test 都 0 行為改動。

---

## §5. R1 5 sub-task 全綠 sign-off

| Sub-task | Owner | 狀態 | 證據 |
|---|---|---|---|
| **R1-T1** route_helpers.py `resolve_replay_runner_bin()` 5-step fallback chain | 前任 E1 | ✅ DONE | `route_helpers.py:120-194`（unmodified by this task） |
| **R1-T2** `restart_all.sh::restart_api` env export | 前任 E1 | ✅ DONE | `helper_scripts/restart_all.sh` git-staged |
| **R1-T3** `replay_routes.py` `/health` route + `compute_replay_health_state()` helper in `route_helpers.py` | 前任 E1 (helper) + 本 E1 (route) | ✅ DONE | helper `route_helpers.py:1003-1112`；route `replay_routes.py:1337-1407`；smoke 顯示兩條 health route 註冊 |
| **R1-T4** `replay_runner_symbol_audit.sh::BIN_PATH_DEFAULT` | 前任 E1 | ✅ DONE | audit 腳本本機跑 → exit=0 + binary path 命中 `rust/target/release/replay_runner`（workspace 真實佈局，T1 fallback chain 生效證明） |
| **R1-T5** `tests/test_replay_route_helpers_binary_resolution.py` 5 case 全綠 | 本 E1 | ✅ DONE | pytest 5/5 PASS |

R1（Runtime Usability）5/5 closed。

---

## §6. git status sign-off-clean 證明（CLAUDE.md §七 P0-GOV-3）

### 6.1 git status

```text
$ git status --porcelain
 M CLAUDE.md
 M TODO.md
 M docs/CCAgentWorkSpace/PA/memory.md
 M docs/CLAUDE_CHANGELOG.md
 M helper_scripts/ci/replay_runner_symbol_audit.sh
 M helper_scripts/restart_all.sh
 M program_code/.../app/replay_routes.py
 M program_code/.../replay/route_helpers.py
?? docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-04--ref20_sprint_a_task_dag.md
?? program_code/.../replay/replay_models.py
?? program_code/.../tests/test_replay_route_helpers_binary_resolution.py
```

`?? replay_models.py` + `?? test_replay_route_helpers_binary_resolution.py` 是
本 task 直接產出，與 sign-off 一一對應；無 sign-off 缺對應代碼/測試的孤兒檔。
其餘 modified 檔（CLAUDE.md / TODO.md / restart_all.sh / route_helpers.py / etc）
是前任 E1 + PA + sibling session 之前已修並 staged，本 task 不再改動。

### 6.2 跨平台 grep（CLAUDE.md §七 ★★）

```text
$ grep -nE '/home/ncyu|/Users/ncyu' \
    program_code/.../replay/replay_models.py \
    program_code/.../tests/test_replay_route_helpers_binary_resolution.py
program_code/.../tests/test_replay_route_helpers_binary_resolution.py:19:    ``/home/ncyu`` / ``/Users/ncyu`` paths ...
program_code/.../tests/test_replay_route_helpers_binary_resolution.py:37:    ``/home/ncyu`` / ``/Users/ncyu`` 字面值 ...
```

只有 docstring 內以政策反例引用（CLAUDE.md §七 明寫「政策反例引用不在此限」），**0
真實硬編碼路徑**。

---

## §7. 修改清單（本 task）

| 檔案 | 動作 | 行為 |
|---|---|---|
| `program_code/.../app/replay_routes.py` | Edit | 加 `/health` route 70 LOC（含完整雙語 docstring）+ 抽 3 inline model 改成 import re-export 12 LOC + 刪 dead `from pydantic import BaseModel, Field, validator` 2 LOC → net 1495 → 1492 LOC |
| `program_code/.../replay/replay_models.py` | New | 138 LOC 純 Pydantic model 抽出（`ReplayRunRequest` / `ReplayCancelRequest` / `ReplayManifestVerifyRequest`），雙語 MODULE_NOTE + 完整 `__all__` |
| `program_code/.../tests/test_replay_route_helpers_binary_resolution.py` | New | 198 LOC 5 case pytest，每 case 真 assert + 雙語 docstring + cross-platform safe（tmp_path）|

---

## §8. 治理對照

| 治理規則 | 驗證 |
|---|---|
| CLAUDE.md §七 雙語注釋（MODULE_NOTE + docstring + inline）| 新增 2 檔 + 1 route 的 module/class/func/inline 全雙語 |
| CLAUDE.md §七 跨平台兼容性（路徑不硬編碼）| `grep -E '/home/ncyu\|/Users/ncyu'` 0 真實命中 |
| CLAUDE.md §九 1500 LOC 硬上限 | replay_routes.py 1492 ≤ 1500 |
| CLAUDE.md §七 P0-GOV-3 sign-off-clean | 本 report 列入 git status `??` 對應的代碼/測試檔，無孤兒 |
| Bilingual-comment-style skill | 每 new function/class/module 中英對照 |
| 最小範圍 / 不擴大 PA 派發範圍 | 只做 R1-T3 route handler + R1-T5 unit tests + LOC 維護所需的 model 抽出；**不**碰 R2/R3 / V### migration / `main_legacy.py` |
| 不自行 commit（E1→E2→E4→QA→PM 鏈）| 本 report 寫完即停，待 E2 review |

---

## §9. 不確定之處

1. **audit script exit code**：PA plan 預期 Mac 跑 audit script `exit_code=4`
   （BIN PATH 找不到），但實際本機跑 `cargo build --release --bin replay_runner
   --features replay_isolated` 成功且把 binary 落在 R1-T1 fallback chain 認得的
   `rust/target/release/replay_runner`，於是 audit script 找到 binary 並 PASS
   (exit=0)。**這是 R1-T1 fallback chain 接好後的真實行為**，並非 R1-T4
   退化。E2 / E4 若需要在無 cargo 環境驗 exit=4 path，可手動 `rm -rf
   rust/target` 或 `OPENCLAW_REPLAY_RUNNER_BIN=/non-exist/foo` 復現。

2. **`/health` route 的 SQL probe 在 V049 absent 時的真實 wiring_status**：實機
   PG 已 deploy V045 + V049（Sprint 3 Track I `7a86d2eb` Phase B-G），但 helper
   `compute_replay_health_state()` 的 fail-closed 預期是「`v049_present=False`
   + `pg_present=True`」此時仍判 `wiring_status="ready"`（因為主要 gate 是
   `binary_exists` + `pg_present` + `data_dir_writable`）。如果 PA design 意圖
   是「V049 absent 也要降級」，需在 helper 補一條 rule，但這不在 R1-T3 修改
   範圍。**先按既有 helper 行為走，等 E2 review 是否需要追加**。

3. **Mac runtime 路徑差異**：tests 用 `tmp_path` fixture 不依賴實機 layout，
   Mac/Linux 行為一致；但實機 `/health` route 在 Mac dev shell 跑時，因 Mac
   無 PG runtime（CLAUDE.md §三 Mac=dev / Linux=runtime），`pg_err` 會回非 None
   → `wiring_status="degraded"`。這符合預期，不是 bug。

---

## §10. Operator 下一步

1. PM 派 E2 對本 task 修改範圍（route + 抽出 + tests）做 code review
2. PM 派 E4 跑相關 regression（至少 `test_replay_route_helpers_binary_resolution.py`
   + `test_replay_routes_auth.py` + `test_replay_routes_t2_*.py`，確認 model
   抽出無破既有 import）
3. E2/E4 通過後，PM 統一 commit + push（與本 report 同 sha）
4. R1 closed，PA 啟動 R2（Manifest Registry）+ R3（First Real E2E Evidence）派發

---

## §11. E2 round 1 fix log（2026-05-04 — `RETURN to E1` 1 HIGH + 4 MEDIUM + 3 LOW）

E2 review report：
`/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-04--ref20_sprint_a_r1_e2_review.md`

本輪 round-trip 嚴格收斂在 E2 點名 finding；**未觸動** R2/R3 區、`main_legacy.py`、新 V### migration、E2 已 cleared 的 sibling test。

### 11.1 HIGH-1 — `Path.exists()` 接受 directory + non-executable file

**修法**：在 `replay/route_helpers.py` 抽 `_is_executable_file(p)` helper（line ~120-138），語意 = `p.is_file() and os.access(p, os.X_OK)`。`is_file()` 自然 follow symlink、過濾 directory + dangling symlink；`os.access(..., os.X_OK)` 驗 effective UID 對該 file 具執行 bit，封堵「mode 0644 file 名為 replay_runner」誤建場景。

**4 個 candidate 全套**：`resolve_replay_runner_bin()` 內所有 `if X.exists():` 改成 `if _is_executable_file(X):`：
- L181 `workspace_release`
- L188 `workspace_debug`
- L196 `legacy_release`

**`compute_replay_health_state()` 同步收斂**：line ~1097 `binary_exists = binary_path.exists()` → `binary_exists = _is_executable_file(binary_path)`。雙語 inline comment 註明「directory or non-executable file at the resolved path is correctly classified as binary missing」。

**回歸驗證**：新增 case 9（dir 在 workspace release 路徑必 skip）+ case 10（non-exec file 必 skip），兩者 seed legacy release 為著陸點，測「skip 後仍找到正確 binary」。pytest 兩 case 全 PASS。

### 11.2 MEDIUM-1 — `OPENCLAW_BASE_DIR` 未 strip

**修法**：line ~177 `base_dir = os.environ.get("OPENCLAW_BASE_DIR", "")` → `.strip()`，與 line 173 override 同模式。雙語 inline comment 「strip 掉 OPENCLAW_BASE_DIR 的前後空白，避免空白被併進 Path() 變成 garbage 路徑」。

### 11.3 MEDIUM-2 — `/health` response leak surface 文件化

**修法**：`compute_replay_health_state` docstring 加「Leak surface note (E2 R1 review MEDIUM-2 — 2026-05-04)」段落（中英對照），明文：
- 回應 data 刻意包含 binary 絕對路徑供 monitoring 對應 binary_missing
- 姊妹 `/health/signature` 不含路徑
- 此較豐 body MUST 限縮給已登入 actor，未來若加 viewer-only / unauthenticated 角色需重審
- 擴 RBAC 時請視本 route 至少需 `replay:read`（非 `replay:read:any`）；不應看絕對路徑的 viewer 改打 `/health/signature`

**僅補注釋，schema/行為不變**。

### 11.4 MEDIUM-3 — empty / whitespace-only env override fallthrough

**修法**：新增兩個 test case（不改 production code，因 helper line 173 `.strip()` + `if override:` 已正確處理；只是缺 regression pin）：
- `test_empty_override_falls_through_to_workspace`: `setenv("OPENCLAW_REPLAY_RUNNER_BIN", "")` → fall through 到 workspace release
- `test_whitespace_only_override_falls_through`: `setenv("OPENCLAW_REPLAY_RUNNER_BIN", "   ")` → 同 fall through

兩 case 釘住「未來若有人把 `.strip()` / `if override:` 拿掉就立刻 fail」。

### 11.5 MEDIUM-4 — legacy release vs legacy debug 順序 test

**修法**：新增 `test_legacy_release_preferred_over_legacy_debug`，**同時** seed legacy release + legacy debug，assert 回 legacy release。釘住 Step 4 vs Step 5 順序。

### 11.6 LOW-1 — docstring "4-step" → "5-path"

**修法**：`resolve_replay_runner_bin()` docstring 兩處（中英）：
- 「This 4-step fallback adds the workspace target layout」→「This 5-path fallback adds the workspace target layout」
- Priority 列表展開為明確 5 項（含 Step 4 legacy release + Step 5 legacy debug 拆分）
- 加 Step 5 inline comment「Legacy nested crate-local debug (final fallback)」

PA plan 對齊：plan §1 R1-T1 acceptance 用「4-step」是 PA 心目中 step 4 = legacy release+debug 合一；本次 docstring 統一收斂為「5-path (with split legacy variant)」更精確；inline 5 步註明「Step N: ...」逐一對齊。**不**改 PA plan 措辭（PA design doc 屬 R2 dispatch 範圍，不在本 round scope）。

### 11.7 LOW-2 — V045 / V049 absent 也回 ready 應降級

**修法**：`compute_replay_health_state()` aggregate 邏輯加第 3 條 rule：
```python
elif not v045_present or not v049_present:
    wiring_status = "degraded"
```

放在 `pg_present / data_dir_writable` rule 之後、`else: ready` 之前。雙語 inline comment 「PG up but replay schema 殘缺 → /run 會在第一筆 INSERT 失敗，不能誤報 ready」。

docstring `wiring_status rules` 列表同步加第 3 條：「v045_present=False OR v049_present=False → degraded（E2 R1 review LOW-2）」。

**回歸驗證**：3 個新 unit test 釘正：
- `test_health_state_degraded_when_v045_absent`：rows=[(False, True)] + pg_err=None → wiring_status='degraded'
- `test_health_state_degraded_when_v049_absent`：rows=[(True, False)] + pg_err=None → wiring_status='degraded'
- `test_health_state_ready_when_all_present`：sanity，rows=[(True, True)] → wiring_status='ready'

每 case 同時 seed binary 落盤 + executable + `OPENCLAW_DATA_DIR` 設 tmp_path，避免 binary_missing / data_dir_writable 路徑誤觸發。

### 11.8 LOW-3 — `replay_routes.py` 8 LOC margin → R2 dispatch 警示

**本 round 不修**（嚴格收斂）。R2 dispatch 前 PM/PA 必須先決定下一抽出策略：候選 = `replay_run_route.py` 把 `post_replay_run` ~600 LOC body 抽走（同 R1-T3 之 model 抽出 pattern：行為 byte-identical / `__all__` 對外 API 不變 / sibling test 0 break）。**本輪僅在 sign-off log 留紀錄，等 R2 排程觸發**。

### 11.9 R1-T5 既有 test 對 `_is_executable_file()` 的相容性處理

HIGH-1 修補後 `Path.touch()` 預設 mode `0o644` 不再被 `_is_executable_file()` 接受 → 既有 5 case 若不 chmod 全 fail。

**修法**：抽 `_seed_executable(path)` helper（line ~110-127），統一 `mkdir(parents=True, exist_ok=True) + touch() + chmod(0o755)`，5 既有 case 全部走此 helper 取代裸 `touch()`。新加 5 case + 3 health state case 同走此 helper。集中化 + 雙語 docstring 註明「`Path.touch()` 預設 0o644 silently fail」原因。

`test_non_executable_file_at_binary_path_skipped` 是唯一**不**走 `_seed_executable()` 的 case — 它故意 `touch() + chmod(0o644)` 製造非執行檔反例。

### 11.10 跑驗結果（必全綠）

```text
$ ./venvs/mac_dev/bin/python -m pytest -xvs program_code/.../tests/test_replay_route_helpers_binary_resolution.py
============================== 13 passed in 0.06s ==============================

$ ./venvs/mac_dev/bin/python -m pytest program_code/.../tests/ -k replay --no-header -q
68 passed, 3387 deselected, 25 warnings in 1.08s

$ bash helper_scripts/ci/replay_runner_symbol_audit.sh; echo "exit=$?"
[replay_runner_symbol_audit] AUDIT PASS: 0 forbidden symbol detected (414 symbols scanned)
exit=0

$ wc -l program_code/.../app/replay_routes.py
    1492 program_code/.../app/replay_routes.py    # 8 LOC margin（未改動，scope 收斂）
```

13/13 PASS（5 既有 + 5 HIGH-1/MEDIUM-3/MEDIUM-4 + 3 LOW-2 health state）。
68 sibling replay test PASS（含 31 既有 baseline + 13 R1-T5 + 24 其他 replay-related）。
audit exit=0（414 symbols, 0 forbidden）。
replay_routes.py 1492 LOC（未動，本 round 修補集中在 route_helpers.py + test 檔）。
跨平台 grep `/home/ncyu|/Users/ncyu` 0 真實命中（2 hit 都在 test docstring 政策反例引用）。

### 11.11 修改清單（本 round）

| 檔案 | 動作 | 行為 |
|---|---|---|
| `program_code/.../replay/route_helpers.py` | Edit | 抽 `_is_executable_file()` helper + `resolve_replay_runner_bin()` 4 candidate 全套 + `OPENCLAW_BASE_DIR.strip()` + docstring 5-path 修正 + `compute_replay_health_state()` 加 leak surface note + V045/V049 absent → degraded rule + binary_exists 走 `_is_executable_file()`；route_helpers.py 1145→1224 LOC |
| `program_code/.../tests/test_replay_route_helpers_binary_resolution.py` | Edit | 抽 `_seed_executable()` helper + 5 既有 case 改用 helper + 5 新 case（empty / whitespace / legacy release vs debug / dir / non-exec file）+ 3 health state case；215→560 LOC |
| `program_code/.../app/replay_routes.py` | **未動** | route handler docstring 對齊 R1-T3 既有；本 round 修補集中於 helper 與 test |

### 11.12 治理對照（本 round）

| 治理規則 | 驗證 |
|---|---|
| CLAUDE.md §七 雙語注釋 | `_is_executable_file()` / 5 新 test case / 3 health state test 全雙語 |
| CLAUDE.md §七 跨平台兼容性 | `grep -E '/home/ncyu\|/Users/ncyu'` 0 真實命中 |
| CLAUDE.md §九 1500 LOC 硬上限 | replay_routes.py 1492 ≤ 1500（未動）/ route_helpers.py 1224 ≤ 1500 |
| CLAUDE.md §七 P0-GOV-3 sign-off-clean | 本 §11 條目對應 git status `M route_helpers.py` + `M test_replay_route_helpers_binary_resolution.py`，0 孤兒檔 |
| 最小範圍 / scope 嚴格收斂 | 0 R2/R3 區、`main_legacy.py`、新 V### 觸動；E2 已 cleared 的 sibling test 不碰 |

---

E1 IMPLEMENTATION DONE: 待 E2 round 2 審查（report path:
`/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-04--ref20_sprint_a_r1_impl.md`）
