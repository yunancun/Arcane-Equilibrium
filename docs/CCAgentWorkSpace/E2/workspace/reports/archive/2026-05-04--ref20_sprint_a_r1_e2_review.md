# REF-20 Sprint A R1 — E2 Adversarial Code Review

**Date:** 2026-05-04
**Reviewer:** E2
**E1 sign-off:** `docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-04--ref20_sprint_a_r1_impl.md`
**PA design:** `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-04--ref20_sprint_a_task_dag.md`
**Files reviewed:** 6 (1 new model file, 1 new test file, 2 modified Python, 2 modified shell scripts)
**Sibling test regression:** 31/31 PASS (test_replay_routes_t2_subprocess + auth + track_c_security + safe_query_audit)
**New unit test:** 5/5 PASS

---

## §1 Executive verdict

**RETURN to E1 — PASS-WITH-FIX-REQUIRED · 1 HIGH + 4 MEDIUM + 3 LOW finding · 0 CRITICAL**

R1 整體方向正確：5-step fallback chain 正確修了 cargo workspace 路徑漂移 / `/health` 端點 schema 對齊 PA design / 雙語注釋完整 / sibling 31 test 不破 / pytest 5/5 PASS / 跨平台合規。**沒有 CRITICAL 阻塞**（無 SQL injection / 無硬邊界繞過 / 無 secret leak）。

但 fallback chain 有 **HIGH-1 file-vs-directory 確認漏洞**（`Path.exists()` 對 directory 也回 True，攻擊者或誤操作可在 workspace target 路徑放 dir 騙過 helper），加上 4 個 MEDIUM（empty-string env corner case 缺測 / response 比 `/health/signature` 多 4 keys 的 leak 對齊未驗 / `binary_release_profile` 沒走既有 `RELEASE_PROFILE_ENV_VAR` 常量 / `OPENCLAW_BASE_DIR=" "` whitespace 不 strip 變 garbage path），及 3 LOW（test 缺 legacy release vs legacy debug 順序覆蓋 / docstring 寫「4-step」實際 5-step / 未驗 V049 absent 的 reason 仍 ready）。

E2 不直修 1500-cap 內的業務行為改動；HIGH-1 的 `is_file()` 收斂屬語意改動（`exists()` → `is_file()`）退 E1。MEDIUM 全退 E1。LOW 1 個 docstring/comment（5 vs 4 step）E2 直修可接受、其餘 LOW 退 E1。

---

## §2 R1-T1 fallback chain finding（含 corner case）

### 2.1 HIGH-1 — `Path.exists()` 接受 directory 與 non-executable file（攻擊面 + 誤操作面）

**位置：** `replay/route_helpers.py:174 / 180 / 190`

```python
if workspace_release.exists():
    return workspace_release
```

**對抗驗證**（E2 Mac 本機跑）：

| 場景 | `.exists()` | `.is_file()` | helper 回傳 | caller 後果 |
|---|---|---|---|---|
| 正常 file | True | True | workspace_release | OK |
| dangling symlink | False | False | 跳下一階 | OK |
| symlink → existing target | True | True | workspace_release | OK |
| **mode 0644 (non-executable file)** | **True** | **True** | **回該檔** | **subprocess.Popen → PermissionError** |
| **directory at workspace target path** | **True** | **False** | **回該目錄** | **subprocess.Popen → PermissionError / IsADirectoryError** |

兩種情境（誤建 dir / 誤改 mode）helper 都會欺騙 caller → /run 看到 200 但 spawn 立即崩。也是攻擊面：若操作員可寫 `$OPENCLAW_BASE_DIR/rust/target/release/`（CI / NFS / Docker bind-mount），可放 dir 名為 `replay_runner` 讓 health 回 `binary_exists=true` 但 /run 永遠 fail，DOS 模式。

**修法（退 E1）：**
- `if workspace_release.is_file():`（同樣套 workspace_debug / legacy_release / legacy_debug）；或
- 兩段檢查 `workspace_release.is_file() and os.access(workspace_release, os.X_OK)`，後者貼 V045 後續 spawn 真實前置條件。

PA design §1 R1-T1 acceptance line 提的「missing → exit 503 path 維持」未涵蓋「exists 但不可執行」——這是 E1/PA 共同盲點。

### 2.2 MEDIUM-1 — `OPENCLAW_BASE_DIR="   "`（whitespace-only）→ garbage path

**位置：** `replay/route_helpers.py:163`

```python
base_dir = os.environ.get("OPENCLAW_BASE_DIR", "")
if not base_dir:
    return Path("replay_runner")
```

無 `.strip()`：whitespace-only 值通過 `if not base_dir:` 檢查，後續 `Path(base_dir) / "rust/target/release/replay_runner"` 結果是 `   /rust/target/release/replay_runner`（leading whitespace）→ 不 match disk → fall 到 step 4 → 最終 fallback `   /rust/openclaw_engine/target/debug/replay_runner`，路徑本身錯但 helper 不告知。

E2 復現：
```
OPENCLAW_BASE_DIR='   ' → 回   /rust/openclaw_engine/target/debug/replay_runner
```

**修法（退 E1）：** override 用 `.strip()`，base_dir 應同樣。一行：

```python
base_dir = os.environ.get("OPENCLAW_BASE_DIR", "").strip()
```

### 2.3 docstring 自稱 4-step 實際 5-step（LOW-1，可 E2 直修）

route_helpers.py:130 + 138（中英）docstring 寫「4-step fallback」並列 4 項 Priority；實際 code 5 條 path（含 Step 1 override + Step 2 workspace_release + Step 3 workspace_debug + Step 4 legacy_release + 隱含 Step 5 legacy_debug 作 final fallback）。內 inline comment（line 157+171+177+183）也是 4 step，但實質 5 path。

但 PA plan §1 R1-T1 acceptance 同樣寫「4-step fallback」，PA 心目中 step 4 = legacy release+debug 合一。語義不算錯但行為描述不精準。E2 直修為「4-step (with split legacy variant)」或「5-step」。**E2 視為 LOW，不阻塞**。

### 2.4 PA design 與 E1 IMPL 對齊查

PA plan §1 R1-T1 sample code (line 38-65) vs E1 IMPL (line 156-195)：完全對齊（path order / fallback semantics / strip override）。**0 spec drift**。

---

## §3 R1-T3 /health endpoint finding（adversarial）

### 3.1 Auth bypass — 不可用未登入訪問（PASS）

`Depends(base.current_actor)` 在 `main_legacy.py:392` 確認：cookie OR Bearer header；token 缺即 raise `HTTPException(401)`。E2 對抗反問「能否未登入訪問 /health」答**否**。pattern 與 `/health/signature` 對齊。**PASS**。

### 3.2 PG injection（PASS）— hardcoded literal SQL

`/health` SQL 是 hardcoded `information_schema.tables` 雙 EXISTS probe，無 user input parameter，`_async_safe_pg_select(sql, ())` 第二參數是空 tuple；走 `safe_pg_select` 內部 `cur.execute(sql, tuple(params))` 是 psycopg parameterized binding。**0 SQL injection 面**。

### 3.3 Statement timeout（PASS — 透過 helper）

`safe_pg_select` 在每次 query 前 `SET LOCAL statement_timeout = 2000ms` (DEFAULT_PG_STATEMENT_TIMEOUT_MS)；PG 慢查 / 死鎖 → 2s 超時 → raise `pg_error:OperationalError` → `pg_present=False` → degraded。`/health` 不會被 PG 掛住。**PASS**。

### 3.4 MEDIUM-2 — Response data shape 比 `/health/signature` 多 4 keys，可能對外洩 repo layout

`/health` data：9 keys 含 `binary_path`（resolved 完整絕對路徑，例 `/home/ncyu/srv/rust/target/release/replay_runner`） + `data_dir`（runtime 目錄絕對路徑）。`/health/signature` data：4 keys，無路徑洩漏。

對未授權 actor leak surface 比 `/health/signature` 大：
- 若 cookie / Bearer auth 被 misconfigured（例如 viewer role 也能拿 cookie），viewer 看得到 repo absolute path
- repo path = OS pivot point（`/home/ncyu/...` vs `/Users/ncyu/...` vs Linux container path）
- attacker 知 binary 確切位置即可規劃 `/run` 注入 payload（雖然 spawn 走 helper whitelist 抗注入，但路徑 enumeration 是 recon advantage）

**E2 評估**：plan §1 R1-T3 acceptance 明文要 `binary_path` 在 body（leak 是 PA 設計選擇），且 leak 限給 logged-in actor。**MEDIUM 而非 HIGH，但需 E1 加 docstring 註明「binary_path 完整絕對路徑刻意 expose 給 logged-in actor，未來若 viewer/operator 分權 leak surface review 時要降級」**。退 E1 補注釋即可，**不需改 schema**。

### 3.5 data_dir_writable 跨平台行為對齊（PASS）

`os.access(data_dir_str, os.W_OK)` Mac vs Linux 都查 effective UID 對該 path 的寫權限；Mac ACL（POSIX + extended）vs Linux POSIX + ACL 行為對齊 —— 真實寫入測試用 Linux 跑（E4 regression），單元測試 mock filesystem 即可。**PASS**。

### 3.6 envelope 對齊 PA spec（PASS）

`_replay_response(data=health, degraded=..., reason=...)` 走 `replay_response_envelope`（`route_helpers.py:802`）回 `{"ok":True, "data":..., "degraded":..., "reason":..., "is_simulated":False, "data_category":"replay_lab"}`。PA plan §1 R1-T3 schema 描述為「body.data.binary_exists」格式 — 實際 implementation envelope 有 `data` field 包 9-key dict — **schema 對齊**。

### 3.7 LOW-2 — V049 absent 但仍 wiring_status="ready"

`compute_replay_health_state` line 1093-1098：

```python
if not binary_exists: → "binary_missing"
elif not pg_present or not data_dir_writable: → "degraded"
else: → "ready"
```

當 PG up + binary OK + data_dir OK + V045/V049 都 absent → `wiring_status="ready"`，但 `/run` 會在 INSERT V045 時失敗（`v045_absent`）。E1 §9 不確定之處 #2 已自承此問題，問是否要追加。

**E2 評估**：依 PA plan §1.R1-T3 schema 表，`v045_present` / `v049_present` 是 inform 不是 gate；wiring_status 的 gate 用 `pg_present`。但語意仍歪：若 PG 有但 V### schema 缺，downstream `/run` fail，monitoring 卻見 ready。**LOW，退 E1 加 rule**：

```python
elif not v045_present:
    wiring_status = "degraded"  # PG up but schema not deployed
```

或保留 ready 但補 reason `schema_pending` warning。E1 §9 已 flag 等 E2 review，回答**追加**。

---

## §4 R1-T2 / R1-T4 shell scripts finding

### 4.1 R1-T2 restart_all.sh — env export 對齊（PASS）

L390-395 顯式 export `OPENCLAW_BASE_DIR + OPENCLAW_DATA_DIR + OPENCLAW_DATABASE_URL_FILE + OPENCLAW_IPC_SECRET_FILE`，5 個 var；對齊 `restart_engine` 在 L347-352 的 export（base_dir + DATA_DIR + DATABASE_URL_FILE + IPC_SECRET_FILE + AUTO_MIGRATE）。

`base_dir="${OPENCLAW_BASE_DIR:-$REPO_ROOT}"` 雙保險：env 不設則 fallback `REPO_ROOT`（line 33 由 `cd "$(dirname "$0")/.."` + `pwd -P`）。restart_engine 用 `$(pwd)`，restart_api 用 `$REPO_ROOT`，兩者實質等價（restart_engine 跑時 cwd 已是 REPO_ROOT 因 line 32 cd 過）。

systemd / launchd 包裹時 env 重新打包，本 export 確保 API process 一定拿到 var。**PASS**。

**LOW-3 / minor**：restart_engine 用 `$(pwd)` vs restart_api 用 `$REPO_ROOT` — 兩者語義一致但形式不齊。**E2 直修可接受但非必要**；不影響運作。

### 4.2 R1-T4 audit script — `RUST_CRATE_DIR` 仍用於 cargo build（PASS）

`RUST_CRATE_DIR` 在 line 88 保留（`$SRV_ROOT/rust/openclaw_engine`），在 line 141 `cd "$RUST_CRATE_DIR" && cargo build` — cargo 對 cwd 敏感，crate-local Cargo.toml 解析依賴 cwd。**保留正確**，新增 `RUST_TARGET_DIR` (line 106) + `BIN_PATH_DEFAULT="$RUST_TARGET_DIR/$BIN_NAME"` (line 110) workspace 真實佈局。

E2 Mac 跑 audit script：`exit=0`（414 symbols, 0 forbidden），binary 真在 `rust/target/release/replay_runner`。**PASS**。

`REPLAY_RUNNER_BIN` env override (line 113) 仍 `${REPLAY_RUNNER_BIN:-$BIN_PATH_DEFAULT}` 行為正確。4 個 audit step（symbol scan / nm / forbidden list / report）都用 `$BIN_PATH` 變數，自動跟新 path。**0 dangling**。

---

## §5 R1-T5 unit tests finding

### 5.1 5 case 全綠（PASS）

5/5 PASS in 0.03s。每 case `monkeypatch.delenv("OPENCLAW_REPLAY_RUNNER_BIN", raising=False)` 清 env，避免 leaked env 遮蔽。**對齊 R1-T1 5-step chain 的 5 主要分支**。

### 5.2 MEDIUM-3 — empty-string env override 的 fallthrough corner case 未測

R1-T1 line 159：`os.environ.get("OPENCLAW_REPLAY_RUNNER_BIN", "").strip()` + `if override:` — 設 `OPENCLAW_REPLAY_RUNNER_BIN=""` 應 fallthrough 到 step 2/3/4/5；E2 復現確實 fallthrough。**但 5 case 沒一個測 `monkeypatch.setenv("OPENCLAW_REPLAY_RUNNER_BIN", "")`**——任何 future regression 把 `.strip()` 拿掉就 silently 破。

**修法（退 E1）：** 加 case 6：

```python
def test_empty_string_env_override_falls_through(tmp_path, monkeypatch):
    """Step 1 corner case: explicit empty-string env var should fallthrough."""
    monkeypatch.setenv("OPENCLAW_REPLAY_RUNNER_BIN", "   ")
    monkeypatch.setenv("OPENCLAW_BASE_DIR", str(tmp_path))
    workspace_release = tmp_path / "rust" / "target" / "release" / "replay_runner"
    workspace_release.parent.mkdir(parents=True)
    workspace_release.touch()
    assert resolve_replay_runner_bin() == workspace_release
```

### 5.3 MEDIUM-4 — legacy release vs legacy debug 順序未覆蓋

`test_legacy_release_fallback` 只 seed legacy release；如果 future regression 把 step 4/5 順序顛倒（先檢 legacy_debug 再 legacy_release），test 不會抓。建議補一 case：seed **兩**個 legacy（release + debug），驗 release 勝。

```python
def test_legacy_release_beats_legacy_debug(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENCLAW_REPLAY_RUNNER_BIN", raising=False)
    monkeypatch.setenv("OPENCLAW_BASE_DIR", str(tmp_path))
    legacy_release = tmp_path / "rust/openclaw_engine/target/release/replay_runner"
    legacy_debug = tmp_path / "rust/openclaw_engine/target/debug/replay_runner"
    legacy_release.parent.mkdir(parents=True)
    legacy_debug.parent.mkdir(parents=True)
    legacy_release.touch()
    legacy_debug.touch()
    assert resolve_replay_runner_bin() == legacy_release
```

### 5.4 macOS `/private/tmp` symlink 行為（PASS）

`tmp_path` fixture 在 macOS 給 `/var/folders/.../T/tmp...` 而非 `/tmp/...` symlink；`workspace_release == result` 比較直接走 PosixPath equality，無 follow-symlink 問題。E2 跑 5/5 PASS 在 darwin 確認。**PASS**。

### 5.5 path 不寫死 `/home/ncyu` `/Users/ncyu`（PASS）

只在 docstring（line 19, 37）以政策反例引用 — CLAUDE.md §七 ★★ 明文「政策反例引用不在此限」。**PASS**。

---

## §6 跨平台 + 雙語 + LOC + Singleton + 回歸 compliance 結論

### 6.1 跨平台（CLAUDE.md §七 ★★）— PASS

`grep -nE '/home/ncyu|/Users/ncyu' <6 files>` → 唯 2 hit 都在 `test_replay_route_helpers_binary_resolution.py:19/37` 的 docstring 政策反例引用。**0 真實硬編碼路徑**。`tmp_path` fixture 跨平台、`OPENCLAW_BASE_DIR` env 跨平台。**PASS**。

### 6.2 雙語注釋（CLAUDE.md §七 強制）— PASS

| 元素 | 中英對照 | 完整度 |
|---|---|---|
| `replay_models.py` MODULE_NOTE | ✅ EN+中 | 完整 |
| `ReplayRunRequest` / `ReplayCancelRequest` / `ReplayManifestVerifyRequest` docstring | ✅ EN+中 | 完整 |
| `_validate_experiment_id` validator inline | ✅ EN+中 | 完整 |
| `compute_replay_health_state` docstring | ✅ EN+中 | 大幅完整含 Args/Returns/wiring_status rules |
| `/health` route handler docstring | ✅ EN+中 | 完整 + plan §6.R1 連結 |
| `resolve_replay_runner_bin` docstring REF-20 Sprint A R1-T1 | ✅ EN+中 | 完整 + commit context |
| inline 不變量（step 1-5 中英） | ✅ EN+中 | 完整 |
| `test_*.py` MODULE_NOTE + 5 case docstring + inline | ✅ EN+中 | 完整 |
| restart_all.sh restart_api comment block | ✅ EN+中 | 完整 |
| replay_runner_symbol_audit.sh BIN_PATH_DEFAULT comment block | ✅ EN+中 | 完整 |

**PASS**。

### 6.3 LOC governance（CLAUDE.md §九 1500 hard cap）— PASS

| 檔 | LOC | cap | 狀態 |
|---|---:|---:|---|
| `replay_routes.py` | 1492 | 1500 | ✅ 8 LOC margin |
| `route_helpers.py` | 1145 | 1500 | ✅ |
| `replay_models.py` | 138 | 1500 | ✅（新檔） |
| `test_replay_route_helpers_binary_resolution.py` | 215 | n/a (test) | ✅ |

**LOW-3**：`replay_routes.py` 只剩 8 LOC margin；R2-T1 (PA plan ~120 LOC) + R2-T2 (~40 LOC modify) + R2-T3 (~80 LOC) 任一 land 必再抽出 — E1 / PA / PM 在 R2 dispatch 前必先決定下一抽出策略（candidate: `replay_run_route.py` 把 `post_replay_run` 600 LOC body 抽走）。**E2 view = 不阻塞 R1，但需 PM dispatch R2 前明文交代**。

### 6.4 Singleton（CLAUDE.md §九）— PASS

`replay_models.py` 0 mutable module-level singleton（純 Pydantic class def + `__all__`）。
`route_helpers.py` 新增 `compute_replay_health_state` 是 pure function，0 module state。
**PASS**，無需登記 §九 表。

### 6.5 回歸風險 — PASS

- `replay_routes.__all__` 仍 export 3 model name → `from app.replay_routes import ReplayRunRequest` 等 caller 不破
- `app/main.py:272`: `from .replay_routes import replay_router` 不變
- 5 sibling test 檔（`test_replay_routes_t2_subprocess.py:51` / `test_replay_routes_auth.py:56` / `test_replay_routes_track_c_security.py:89` / `test_replay_routes_safe_query_audit.py`）的 `from app.replay_routes import ...` 走 module-level alias 仍 work
- 31/31 PASS 跑通驗證
- E2 額外 smoke：`replay_routes.ReplayRunRequest is replay_models.ReplayRunRequest` → True（同一 class object）

**PASS**。

### 6.6 OpenClaw 9 條 §3 checklist 對齊

| 條目 | 狀態 |
|---|---|
| 跨平台 grep `/home/ncyu` `/Users/ncyu` | ✅ 0 真實硬編碼 |
| 雙語注釋 | ✅ |
| Rust unsafe / unwrap / panic | ✅ N/A（純 Python + shell） |
| 跨語言 IPC schema | ✅ N/A |
| Migration Guard A/B/C | ✅ N/A（本 R1 無新 V###） |
| healthcheck 配對 | ⚠️ MEDIUM-5：`/api/v1/replay/health` 端點是 GUI/monitoring probe，CLAUDE.md §七「被動等待 TODO 必附 healthcheck」是指 `passive_wait_healthcheck.py` 的 cron probe；`/health` 端點本身是 healthcheck 但 cron 端點還沒掛 → 待 R3 deploy 階段或 R4 補（**不阻塞 R1**） |
| Singleton 登記 | ✅ 0 新 singleton |
| 文件大小 800/1500 | ✅ |
| Bybit API | ✅ N/A |

---

## §7 退回 E1 修的條目（E2 不代寫）

| # | Severity | 位置 | 描述 | 修法 |
|---|---|---|---|---|
| 1 | **HIGH-1** | `replay/route_helpers.py:174 / 180 / 190` | `Path.exists()` 對 directory + non-executable file 都回 True，spawn 失敗時 health 仍報 binary_exists=true | 改 `is_file()`（最低）；或 `is_file() and os.access(path, os.X_OK)`（更穩）。同時 helper 的 `binary_exists` field 也要走同 predicate。**對 4 個 path candidate 都套**。 |
| 2 | **MEDIUM-1** | `replay/route_helpers.py:163` | `OPENCLAW_BASE_DIR="   "` whitespace 不 strip → 後續 path 帶 leading space 變 garbage | `base_dir = os.environ.get("OPENCLAW_BASE_DIR", "").strip()`（與 override 同模式） |
| 3 | **MEDIUM-2** | `app/replay_routes.py:1311-1331` `/health` route | response body 含 `binary_path` 完整絕對路徑 — leak surface 比 `/health/signature` 大 | docstring 加段「binary_path 完整絕對路徑為 logged-in actor only；未來若 viewer/operator 分權需 review leak surface」；schema 不變。**只補注釋** |
| 4 | **MEDIUM-3** | `tests/test_replay_route_helpers_binary_resolution.py` | 缺 `OPENCLAW_REPLAY_RUNNER_BIN=""` / `"   "` empty/whitespace fallthrough 測試 | 加 case 6：`monkeypatch.setenv("OPENCLAW_REPLAY_RUNNER_BIN", "")` + workspace release 落盤 → assert 回 workspace release（驗 `.strip()` 仍守 fallthrough） |
| 5 | **MEDIUM-4** | `tests/test_replay_route_helpers_binary_resolution.py` | 缺 legacy release vs legacy debug 順序 case | 加 case 7：legacy release + legacy debug 同時落盤 → assert 回 legacy release |
| 6 | **MEDIUM-5** (defer) | `helper_scripts/db/passive_wait_healthcheck.py` | `/api/v1/replay/health` 還沒接到 passive_wait_healthcheck cron probe | R3 deploy 後或 R4 派發階段補；**R1 不阻塞** |
| 7 | **LOW-2** | `replay/route_helpers.py:1093-1098` `compute_replay_health_state` | V049/V045 absent 但仍 wiring_status="ready"（E1 §9 #2 自 flag） | 補 rule：`elif not v045_present: wiring_status="degraded" + reason="schema_pending"`；或保留 ready 但 reason 加 warning |
| 8 | **LOW-3** | `app/replay_routes.py:1492` LOC margin 只 8 行 | R2-T1 任一 land 必觸 1500 cap | PM dispatch R2 前先決定下一抽出策略，建議 `replay_run_route.py` |

---

## §8 obvious typo / lint / dead import 直修記錄（E2 可直接修）

**E2 本 round 不直修**。理由：

1. **LOW-1 docstring 5-step vs 4-step 不一致**——E2 邊界內可直修，但與 PA plan §1 同樣表述對齊（PA 也寫「4-step」），統一口徑後再修以免 spec drift；建議 R2 啟動前 PM/PA round confirm「4-step (with split legacy)」or「5-step」措辭，由 E1 一次同步 PA plan + helper docstring + inline comment。
2. **LOW-3 minor restart_engine 用 `$(pwd)` vs restart_api 用 `$REPO_ROOT`**——形式不齊但語義等價，且 R1-T2 已固定該寫法；改一致是 cosmetic，不直修以免侵入 R1-T2 commit boundary。

**0 dead import / 0 typo / 0 trailing whitespace**。E1 R1 整體 hygiene 良好。

---

## §9 Verdict & follow-up

**RETURN to E1 — 1 HIGH (#1) + 4 MEDIUM (#2/#3/#4/#5) 必修才能進 E4。**
**LOW-2 (#7) + LOW-3 (#8 governance) 由 PM 決定是否 R1 內修或 R2 dispatch 前處理。**

**Sub-task verdict matrix：**

| Task | Severity | Action |
|---|---|---|
| R1-T1 fallback chain | HIGH | RETURN E1（is_file 收斂 + base_dir strip） |
| R1-T2 restart_api env | PASS | — |
| R1-T3 /health route | MEDIUM | RETURN E1（補 leak-surface docstring + V049 absent rule 由 PM 裁奪） |
| R1-T4 audit BIN_PATH | PASS | — |
| R1-T5 unit tests | MEDIUM | RETURN E1（加 2 case：empty-string fallthrough + legacy release vs debug 順序） |

**對抗反問結果：**

1. Q: 「`Path.exists()` 對 directory 是否回 True？」 → A: **是**，HIGH-1 attack surface
2. Q: 「`OPENCLAW_REPLAY_RUNNER_BIN=""` 真 fallthrough?」 → A: 行為對（`.strip()` 守住），但**未測**
3. Q: 「未登入能訪問 /health?」 → A: 否，`current_actor` 401
4. Q: 「PG injection 風險?」 → A: 0（hardcoded literal SQL + parameterized binding）
5. Q: 「PG 死鎖能掛 health 嗎?」 → A: 否（`SET LOCAL statement_timeout = 2000ms`）
6. Q: 「response leak repo layout?」 → A: 是，但限給 logged-in actor（PA design 選擇），需 docstring 註明
7. Q: 「model 抽出後既有 caller 是否破?」 → A: 否，31/31 sibling test PASS + `__all__` 對齊

**修完後 E2 重審範圍：**
- HIGH-1 + MEDIUM-1 改 1 個 helper function
- MEDIUM-2 改 1 個 docstring
- MEDIUM-3 + MEDIUM-4 加 2 test case

預估 E1 修完 < 30 min；E2 round 2 重跑 5/5 + 31/31 sibling + 對 HIGH-1 補 dir/non-exec 反例 case 即可放行。

---

E2 REVIEW DONE: RETURN to E1 (1 HIGH + 4 MEDIUM finding) · report path: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-04--ref20_sprint_a_r1_e2_review.md`

---

## §11 Round 2 Verification — 2026-05-04 · focused fix audit

**Scope reminder**：嚴格收斂在 round 1 finding 的 fix verdict，**不**重審已 cleared 的部分。

### §11.1 HIGH-1 fix verdict — ✅ PASS

`_is_executable_file(p) = p.is_file() and os.access(p, os.X_OK)` 在 `route_helpers.py:120-137` 落地。對抗驗證：

| Use site (line) | 套用 helper | 驗證結果 |
|---|---|---|
| 209 `workspace_release` | `_is_executable_file` | ✅ |
| 215 `workspace_debug` | `_is_executable_file` | ✅ |
| 225 `legacy_release` | `_is_executable_file` | ✅ |
| 233 `legacy_debug` | 直 return（final fallback，不 check 對 — caller 經 503 surface） | ✅ R1 finding 「4 candidate」是「3 check + 1 final return」設計 |
| 1138 `compute_replay_health_state.binary_exists` | `_is_executable_file` | ✅ HIGH-1 fix 真接到 health state（round 1 漏點） |

**HIGH-1 + non-exec 兩 case 真綠**：
```
test_directory_at_binary_path_skipped PASSED
test_non_executable_file_at_binary_path_skipped PASSED
2 passed, 11 deselected in 0.02s
```

對抗 probe（live Mac）：workspace_release 是 dir 時 → helper 正確 fall through 到 final legacy_debug path，caller 透過 503 surface `binary_missing`，**不**回 dir、**不**錯誤回報 `binary_exists=true`。

### §11.2 MEDIUM-1/2/3/4 fix verdict — ✅ ALL PASS

**MEDIUM-1**（line 198）：`base_dir = os.environ.get("OPENCLAW_BASE_DIR", "").strip()` ✅，與 line 189 `OPENCLAW_REPLAY_RUNNER_BIN` 同 `.strip()` 模式對齊。test 6 `test_empty_override_falls_through_to_workspace`（empty）+ test 7 `test_whitespace_only_override_falls_through`（"   "）兩 case PASS ✅。

**MEDIUM-2**（line 1065-1076 EN + line 1091-1098 中）：`compute_replay_health_state` docstring 加 leak surface note 完整中英對照，明確「binary_path 為已登入 actor only / 未來 viewer-only / 未登入 role 加入時必重審 / 擴 RBAC 視為至少 `replay:read`，不應暴露給 `replay:read:any`」✅。schema 不變對 R1 review 邏輯。

**MEDIUM-3**：test 6 + test 7 兩 fallthrough corner case 已加，PASS。

**MEDIUM-4**：test 8 `test_legacy_release_preferred_over_legacy_debug` 同時 seed 兩 legacy 並驗 release 勝出，PASS ✅。

### §11.3 LOW-1/2 fix verdict — ✅ ALL PASS

**LOW-1**（5-step / 4-step 自洽）：route_helpers.py 唯一殘存「path」字眼（line 150 EN「5-path fallback」+ line 159 中「5 path fallback」），無 4-step 表述 ✅。

**LOW-2**（line 1166-1175）：`compute_replay_health_state` step 4 wiring_status 邏輯加 `elif not v045_present or not v049_present: wiring_status = "degraded"` rule，三 unit test mock：
- `test_health_state_degraded_when_v045_absent` (rows=[(False, True)]) → degraded ✅
- `test_health_state_degraded_when_v049_absent` (rows=[(True, False)]) → degraded ✅
- `test_health_state_ready_when_all_present` (rows=[(True, True)]) → ready ✅

**LOW-3** 留 R2 dispatch margin 警示，未動 LOC ✅（governance 通報未越界）。

### §11.4 LOC + sibling 數字驗證

```
1492 program_code/.../app/replay_routes.py            # 8 LOC margin，未動 ✅
1224 program_code/.../replay/route_helpers.py         # baseline 1145 → +79 LOC（_is_executable_file + LOW-2 rule + bilingual）
 560 program_code/.../tests/test_replay_route_helpers_binary_resolution.py
                                                       # baseline 215 → +345 LOC（8 new test case + bilingual MODULE_NOTE 大擴展）
```

`replay_routes.py` 1492 ≤ 1500 ✅；`route_helpers.py` 1224 ≤ 1500 ✅；test file 不受 1500 cap 約束（CLAUDE.md §九 governance 對 test 寬鬆）。

R1-T5 13/13 PASS（5 既有 + 5 HIGH-1/MEDIUM-3/MEDIUM-4 regression + 3 LOW-2 health state）✅。`def test_` 計數 13，對齊 E1 claim。

```
13 passed in 0.03s
```

Sibling regression `-k replay`：**68 PASS, 3387 deselected, 25 warnings**（Pydantic V1 validator deprecation 是 pre-existing，非本 round 引入）。round 1 baseline 31 是 4 file 子集；round 2 全 `-k replay` 跑 68 不退 ✅。

audit script `helper_scripts/ci/replay_runner_symbol_audit.sh` exit=0，414 symbols / 0 forbidden ✅。

跨平台：`/home/ncyu` `/Users/ncyu` grep 唯 hit 是 test docstring 的政策反例引用（line 36 / 71，CLAUDE.md §七 ★★ 明文允許）✅。

### §11.5 `_is_executable_file` 對抗反問結論

| Probe | 結果 | E2 評估 |
|---|---|---|
| dangling symlink | `is_file()=False`、`exists()=False` | helper 正確 skip ✅ |
| symlink → existing exec target | `is_file()=True`、`X_OK=True` | helper 正確 accept ✅ |
| 0o755 real exe | `is_file()=True`、`X_OK=True` | accept ✅ |
| 0o644 plain file | `is_file()=True`、`X_OK=False` | helper 因 `and` 正確 skip ✅ |
| **directory** | **`is_file()=False`、`X_OK=True`** | **helper 因 `and` short-circuit 正確 skip** ✅ — **本案 attack-surface critical insight**：directory 對 traverse 而言 `os.access(X_OK)=True`！若 helper 只檢 `os.access` 不檢 `is_file()` 會被欺騙。E1 雙條件設計對 |
| 跨平台（macOS APFS / Linux ext4） | `is_file()` + `os.access(X_OK)` 行為對齊 POSIX | 0 跨平台 regression ✅ |
| **POSIX root 行為** | mode 0644 / 0444 / 0000 對 root 的 `os.access(X_OK)=False`（POSIX `access(2)` 規範：root 仍需至少一 user/group/other 有 x bit） | root 場景下「攻擊者 0644 假 binary 騙 root helper」**仍**被守 ✅ |

**對抗反問結論：no new finding**。E1 的 `is_file() and os.access(X_OK)` 雙保險設計是**唯一**正確 — `is_file()` 守 directory + symlink，`os.access(X_OK)` 守 mode 不對。少一個都漏。

### §11.6 Final verdict — Round 2 PASS to E4

**Pass criteria 全綠**：
- HIGH-1 fix 真改完（4 candidate + binary_exists 全套，2/2 regression test PASS）
- MEDIUM-1 真加 `.strip()`（line 198）
- MEDIUM-2 leak surface note 完整中英
- MEDIUM-3 / MEDIUM-4 兩 corner case test 真加（13/13 PASS）
- LOW-1 docstring 5-path 一致
- LOW-2 wiring_status='degraded' rule + 3 unit test
- LOC 收斂（replay_routes 未動 + route_helpers +79 在 1500 內 + test file 不受 cap）
- sibling 68 PASS 不退
- audit script exit=0
- 跨平台 grep 0 hit
- 對抗反問 0 新 finding

**E2 不寫業務代碼，不直修；本 round 0 行 E2 直修**（與 round 1 自陳一致）。

**Sub-task verdict matrix（round 2）：**

| Task | Round 1 | Round 2 |
|---|---|---|
| R1-T1 fallback chain (HIGH-1) | RETURN | ✅ PASS |
| R1-T1 base_dir strip (MEDIUM-1) | RETURN | ✅ PASS |
| R1-T2 restart_api env | PASS | (untouched) |
| R1-T3 /health route (MEDIUM-2 leak note) | RETURN | ✅ PASS |
| R1-T3 /health LOW-2 V045/V049 absent rule | RETURN | ✅ PASS |
| R1-T4 audit BIN_PATH | PASS | (untouched) ✅ exit=0 |
| R1-T5 unit tests (MEDIUM-3 + MEDIUM-4) | RETURN | ✅ PASS（5+5+3=13 PASS） |
| R1 LOC governance (LOW-3 R2 dispatch warning) | LOW | ✅ noted, R2 dispatch 前處理 |

**Outstanding (defer 至 R3 不阻塞)：**
- MEDIUM-5：`/api/v1/replay/health` 接到 `passive_wait_healthcheck.py` cron probe — round 1 已標 R3/R4 deploy 階段補，不在 R1 scope
- LOW-3：1492/1500 8 LOC margin → R2-T1/T2/T3 dispatch 前 PM 必先決定下一抽出策略（candidate `replay_run_route.py`）

---

E2 REVIEW DONE: PASS to E4 · round 2 cleared all round 1 findings · 0 new finding · report path: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-04--ref20_sprint_a_r1_e2_review.md`
