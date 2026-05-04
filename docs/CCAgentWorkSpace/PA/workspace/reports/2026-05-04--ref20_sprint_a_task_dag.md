# REF-20 Sprint A Task DAG — R1 + R2 + R3 Design Dispatch

**Author:** PA
**Date:** 2026-05-04
**Plan source:** `docs/execution_plan/2026-05-04--ref20_gap_closure_reality_backtest_plan_v1.md` (commit `a4ea3571`)
**Pre-flight evidence:** PM 4-gap reality check confirmed before this design.
**Status:** read-only design — no code written, no commits, no file edits

---

## Executive summary

Sprint A 是把 REF-20 從「結構性 GREEN / vacuous truth」推到「最小 evidence-backed truth」的 unblock 工作。R1 修 binary path + audit script + 補 `/api/v1/replay/health`；R2 把 `/run` 對 `replay.experiments` 的 dangling 假設換成真實的 atomic registration；R3 在 Linux 跑通第一條 authenticated E2E run 並讓 4 張表落第一筆 row。

設計關鍵發現：

1. **R1 的 4 個任務檔案重疊低**（R1-T1+T3 共動 `route_helpers.py`；R1-T2 改 `restart_all.sh`；R1-T3 改 `replay_routes.py` 加 1 endpoint；R1-T4 改 `replay_runner_symbol_audit.sh`）→ 4 個 sub-task 可並行給 1-2 個 E1，**不需要 worktree isolation**。
2. **R2 是真正的高風險區**：現在的 `/run` 用 `uuid5(experiment_id)` 自衍生 `manifest_id` 然後 INSERT 到 `replay.run_state`，**從來沒 INSERT 過 `replay.experiments` 任何行**（grep 確認 routes module 0 個 `INSERT INTO replay.experiments` 出現）。Sprint 1 V052 加的 FK redirect 在 `replay.run_state.manifest_id → replay.experiments.experiment_id` 之間目前是 **vacuously true**：因為 `run_state` 也是 0 行，FK 從未被檢查。**R3 一旦真跑，FK 會在 Linux PG 直接拒 INSERT** → R2 必先於 R3 land + deploy。
3. **R3 是純串行**，依 R1 + R2 完成後才能跑；不可並行。R3 的執行步驟可在 R1+R2 並行期間先設計好 curl/SQL，等部署完馬上 dry-run。
4. **Hidden risk**：`restart_all.sh::restart_api()` 只 inherit 2 個 env var，**沒明確 export `OPENCLAW_BASE_DIR`**；雖然 `nohup` 慣常透過 shell 繼承 caller env，但這 path resolution 變脆弱（systemd / launchd / pm2 重新封裝時會丟）→ R1-T2 必補。

---

## §1 R1 task list — Runtime Usability Repair

| Task | File | Est LOC | Depends-on | Acceptance |
|---|---|---:|---|---|
| **R1-T1** | `program_code/exchange_connectors/bybit_connector/control_api_v1/replay/route_helpers.py::resolve_replay_runner_bin()` (line 120-146) | ~25 | none | Unit test覆蓋 4-step fallback；override > workspace target > debug target > legacy nested path；missing → exit 503 path 維持 |
| **R1-T2** | `helper_scripts/restart_all.sh::restart_api()` (line 357-378) | ~5 | none | API process 環境內必含 `OPENCLAW_BASE_DIR` + `OPENCLAW_DATA_DIR`（顯式 `export` 不靠 nohup inherit）|
| **R1-T3** | `program_code/exchange_connectors/bybit_connector/control_api_v1/app/replay_routes.py` 新增 `@replay_router.get("/health")` | ~50 | R1-T1 (resolve_replay_runner_bin) | curl 200 + body 含 `binary_path` / `binary_exists` / `data_dir_writable` / `pg_present` / `wiring_status`；auth 採 read-only — `Depends(base.current_actor)` 保留登入要求但**不要 require_scope_and_operator**（與 `/health/signature` 對齊）|
| **R1-T4** | `helper_scripts/ci/replay_runner_symbol_audit.sh::BIN_PATH_DEFAULT` (line 88-91) | ~3 | none | `RUST_CRATE_DIR` 改為 `$SRV_ROOT/rust`；運行時 audit 真實 workspace target |
| **R1-T5** | 新增 `tests/test_replay_route_helpers_binary_resolution.py` | ~80 | R1-T1 | 4 test case：env override / release exists / debug fallback / all absent |

### 設計要點 — R1-T1 binary resolution fallback chain

當前實作只認 `$OPENCLAW_BASE_DIR/rust/openclaw_engine/target/...`（cargo crate-local 寫法），但 cargo workspace 在 root `Cargo.toml` 配置時 emit 路徑是 `$OPENCLAW_BASE_DIR/rust/target/...`（workspace-local）。修復順序：

```python
def resolve_replay_runner_bin() -> Path:
    # 1. Operator/test override
    override = os.environ.get("OPENCLAW_REPLAY_RUNNER_BIN", "").strip()
    if override:
        return Path(override)

    base_dir = os.environ.get("OPENCLAW_BASE_DIR", "")
    if not base_dir:
        return Path("replay_runner")  # PATH-relative last resort

    # 2. Workspace target release (current real layout 2026-05-04)
    workspace_release = Path(base_dir) / "rust/target/release/replay_runner"
    if workspace_release.exists():
        return workspace_release

    # 3. Workspace target debug (dev path)
    workspace_debug = Path(base_dir) / "rust/target/debug/replay_runner"
    if workspace_debug.exists():
        return workspace_debug

    # 4. Legacy nested crate-local layout (compat fallback for partial rollouts)
    legacy_release = Path(base_dir) / "rust/openclaw_engine/target/release/replay_runner"
    if legacy_release.exists():
        return legacy_release
    legacy_debug = Path(base_dir) / "rust/openclaw_engine/target/debug/replay_runner"
    return legacy_debug  # may not exist; caller surfaces via 503
```

### 設計要點 — R1-T3 `/api/v1/replay/health` schema

| Field | 來源 | 含義 |
|---|---|---|
| `binary_path` | `resolve_replay_runner_bin()` | 報告 currently resolved path |
| `binary_exists` | `Path(binary_path).exists()` | bool |
| `binary_release_profile` | `OPENCLAW_RELEASE_PROFILE` env 值 | live / paper / 空 |
| `data_dir` | `OPENCLAW_DATA_DIR` 或 default | runtime artifact root |
| `data_dir_writable` | `os.access(data_dir, os.W_OK)` | bool |
| `pg_present` | `_async_safe_pg_select("SELECT 1", ())` 觀察 err | bool |
| `v045_present` | `_v045_table_present(cur)` | bool |
| `v049_present` | `_v049_table_present(cur)` | bool |
| `wiring_status` | aggregate | `ready` / `degraded` / `binary_missing` |

**Auth 政策（plan §6 R1 acceptance "behind the intended auth policy"）**：採 **`Depends(base.current_actor)` 已登入即可**，**不要 `require_scope_and_operator`** — 與 `/health/signature` (line 1336-1375) 對齊。理由：health probe 是 monitoring infra 用，operator 不應為了 health 拿 write scope；leak surface 已限制在「resolved binary path + writable bool」沒有敏感秘密。

### Acceptance 量化

```bash
# Linux 端 R1 部署後
curl -i http://127.0.0.1:8000/api/v1/replay/health
# expect: 200 + body.data.binary_exists=true + binary_path 含 "rust/target/release/replay_runner"

bash helper_scripts/ci/replay_runner_symbol_audit.sh
# expect: AUDIT PASS, 0 forbidden symbol detected

curl -X POST http://127.0.0.1:8000/api/v1/replay/run -H 'Content-Type: application/json' \
     --cookie "..." -d '{"experiment_id":"smoke-r1-only"}'
# expect: NOT "binary_not_found"; may still hit FK from G2 until R2 lands
```

---

## §2 R2 task list — Manifest Registry & Verification Repair

| Task | File | Est LOC | Depends-on | Acceptance |
|---|---|---:|---|---|
| **R2-T1** | `app/replay_routes.py` 新增 `@replay_router.post("/experiments/register")` | ~120 | R1-T3（共用 health 邏輯模式） | INSERT 一行到 `replay.experiments`（22 col contract）；require_scope_and_operator + replay:write；idempotency_key 命中已存在 manifest 回 200 但不重複插 |
| **R2-T2** | `app/replay_routes.py::post_replay_run()`（修改 line 401-573）| ~40 改 | R2-T1 | `/run` 開兩階段事務：(a) verify `replay.experiments` row 存在（用 body.experiment_id）；不存在 → 400 reason=`replay_experiment_not_registered`；(b) INSERT `replay.run_state` 同事務；保證 FK 不 dangle |
| **R2-T3** | `replay/manifest_signer.py` + `app/replay_routes.py::post_manifest_verify()` (line 1195-1334) | ~80 | R2-T1 | 拿掉 501 path：當 `replay.signing_keys` table（V042 reserved 但 schema 未定）尚未 ready 時，改 fallback 到 secrets 目錄掃 `$OPENCLAW_SECRETS_DIR/<env>/replay_signing_key`，找到 fingerprint matching key → verify；找不到 → 410 reason=`replay_verify_key_archive_not_provisioned`（不再用 `OPENCLAW_REPLAY_VERIFY_TEST_KEY`）|
| **R2-T4** | `tests/test_replay_routes_t2_subprocess.py` + 新增 `tests/test_replay_experiments_register.py` | ~200 | R2-T1, R2-T2 | atomic registration test：register → run → run_state.manifest_id ≠ NULL ∧ FK valid；FK reject test：跳過 register 直接 run → 400 |
| **R2-T5** | 新增 `tests/test_replay_idempotency_register.py` | ~80 | R2-T1 | 同 idempotency_key 兩次 register → 同 experiment_id 回；同 idempotency_key 兩次 run → 同 run_id 回 |

### 設計要點 — R2-T1 atomic registration vs idempotency

兩個分離資源 (experiments + run_state) 兩種冪等：

- **`/experiments/register`** 冪等 by `idempotency_key + actor_id` → INSERT 失敗（unique violation）→ SELECT 已存的 row 回 200。
- **`/run`** 冪等 by `idempotency_key + actor_id` → 同樣 unique violation → SELECT existing run。

**為什麼用兩階段而非單一 atomic 事務（一次 register + spawn）**：plan §6 R2 acceptance 明文 "Authenticated manifest registration creates one `replay.experiments` row" 與 "Authenticated `/run` creates one `replay.run_state` row" 為**獨立** acceptance line。將 register 與 run 拆開符合 manifest registry 是 "design-time intent" / run_state 是 "runtime fact" 的分層（V045 schema doc 已明文）。Operator 的 use case = 設計 manifest（一次）→ 多次 run（每次決策不同 fixture）→ 報告不同 run_id。Atomic 合一會綁死「一次 register = 一次 run」，違反設計意圖。

### 設計要點 — R2-T1 manifest payload schema

V049 22-col contract 要求 minimum：

```python
class ReplayExperimentRegisterRequest(BaseModel):
    idempotency_key: Optional[str]  # actor-scoped uniqueness
    symbol: str                     # e.g. "BTCUSDT"
    strategy: str                   # e.g. "grid_trading"
    data_window_start: datetime     # OOS window start
    data_window_end: datetime       # OOS window end
    half_life_days: float           # V041 stub field, V049 promoted
    embargo_days: float             # V041 stub field, V049 promoted
    manifest_jsonb: dict            # full V3 §4.1 manifest body (signed-or-not)
    signature_hex: Optional[str]    # 若 caller 已簽，server verify
    signature_key_ref: Optional[str]  # fingerprint
    # server-derived: experiment_id (uuid4), manifest_hash (sha256 of canonical_bytes)
```

注：本任務 **不**負責修 R5+R6 的 reality calibration；R2 只負責讓 `/run` 不 dangle。

### E3 安全審計 checklist（R2 高風險）

E3 必審：

1. **Auth bypass**：`/experiments/register` 必走 `require_scope_and_operator(actor, "replay:write")`；不可只查 `current_actor`。
2. **IDOR (cross-actor manifest theft)**：register 時 `actor_id` 必由 server-side `audit_actor_id(actor)` 寫入；不接受 client-supplied `actor_id`。Read 路徑沿用 R20 Sprint 1 Track C P0-5a 的 `replay:read:any` scope 邏輯。
3. **FK race**：`/run` 必用 `SELECT FOR UPDATE` 或 `pg_advisory_xact_lock` 鎖住 experiment row 防 register/delete race；INSERT run_state 必在同 cursor 同事務。
4. **Signature bypass via test_key**：R2-T3 拿掉 test_key 後，R2-T3 的 fallback secrets-file 路徑必檢 `is_live_release_profile()` — live 下 secrets file 必通過 `OPENCLAW_SECRETS_DIR` 結構驗證（不能讓 attacker 用 `/tmp/X` symlink 注入 key）。
5. **manifest_jsonb size**：register body 必設 size cap（建議 256 KB / row）防 PG 慢查；body 太大 → 413。
6. **canonical-bytes JSON encoding contract**：`route_helpers.write_manifest_fixture` 已用 `sort_keys=True / separators=(',', ':') / ensure_ascii=False`；register 計 manifest_hash 時必走同 canonical 寫法（reuse 同函式）防 cross-language drift（Sprint 1 F1 retrofit invariant 已嚴格定義）。

---

## §3 R3 task list — First Real Runtime E2E Evidence

| Task | Owner | Depends-on | Acceptance |
|---|---|---|---|
| **R3-T1** | E1 (Linux runtime via SSH bridge) | R1 全部 + R2 全部 deploy | 1 次完整成功 run，4 張表 row > 0 |
| **R3-T2** | QA | R3-T1 | 對 ms 級時間軸截屏 + state transition log + Wave 9 no-live-mutation watch query 確認 0 leak |

### 認證流程設計

Operator 角色 + `replay:write` scope。Token 簽發走現有 `app/auth/` cookie session：operator 透過 GUI login flow（GUI 已實裝）拿 cookie；CLI 用 `helper_scripts/auth/operator_login.sh` 或對應 script。**這 design 不重新設計 auth pipeline** — 沿用 production 路徑。

### Curl 命令序列（R3 Linux smoke run）

```bash
# Step 0 — login (operator session token)
COOKIE_JAR=$(mktemp)
curl -sS -c "$COOKIE_JAR" -X POST http://127.0.0.1:8000/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d "{\"actor_id\":\"operator_smoke\",\"role\":\"operator\",\"scopes\":[\"replay:write\"]}"
# expect: 200 + Set-Cookie header

# Step 1 — health probe (R1-T3 acceptance)
curl -sS -b "$COOKIE_JAR" http://127.0.0.1:8000/api/v1/replay/health | jq .
# expect: 200 + data.binary_exists=true + wiring_status="ready"

# Step 2 — register experiment (R2-T1 acceptance)
EXP_ID="smoke-$(date +%s)"
REGISTER_BODY=$(cat <<EOF
{
  "idempotency_key": "${EXP_ID}-key",
  "symbol": "BTCUSDT",
  "strategy": "grid_trading",
  "data_window_start": "2026-05-01T00:00:00Z",
  "data_window_end": "2026-05-02T00:00:00Z",
  "half_life_days": 7.0,
  "embargo_days": 0.5,
  "manifest_jsonb": {"data_tier":"S3","fixture_uri":"file:///tmp/openclaw/replay_artifacts/fixtures/btc_2026_05_01.json"},
  "signature_hex": null,
  "signature_key_ref": null
}
EOF
)
REGISTER_RESP=$(curl -sS -b "$COOKIE_JAR" -X POST http://127.0.0.1:8000/api/v1/replay/experiments/register \
  -H 'Content-Type: application/json' -d "$REGISTER_BODY")
echo "$REGISTER_RESP" | jq .
EXPERIMENT_ID=$(echo "$REGISTER_RESP" | jq -r '.data.experiment_id')

# Step 3 — run replay (R3 acceptance)
curl -sS -b "$COOKIE_JAR" -X POST http://127.0.0.1:8000/api/v1/replay/run \
  -H 'Content-Type: application/json' \
  -d "{\"experiment_id\":\"${EXPERIMENT_ID}\",\"idempotency_key\":\"${EXP_ID}-run-key\"}" | jq .
# expect: 200 + data.run_id non-null + data.status="running"

# Step 4 — poll status (allow 5-10s for synthetic walker)
sleep 8
curl -sS -b "$COOKIE_JAR" http://127.0.0.1:8000/api/v1/replay/status | jq .
# expect: 200 + data.status in {completed, running}

# Step 5 — fetch report
curl -sS -b "$COOKIE_JAR" http://127.0.0.1:8000/api/v1/replay/report/${EXPERIMENT_ID} | jq .
# expect: 200 + artifact_path within allowlist + report fields populated
```

### SQL 驗證查詢（plan §8 + Wave 9 safety）

```sql
-- Wave R3 acceptance: 4 tables must be > 0
SELECT 'experiments' as tbl, COUNT(*) FROM replay.experiments
UNION ALL SELECT 'run_state', COUNT(*) FROM replay.run_state
UNION ALL SELECT 'report_artifacts', COUNT(*) FROM replay.report_artifacts
UNION ALL SELECT 'simulated_fills', COUNT(*) FROM replay.simulated_fills;

-- (handoff_requests + mlde_replay_veto_log 仍可為 0；R7 才開始有資料)

-- FK lineage validity
SELECT s.run_id, s.manifest_id, e.experiment_id
  FROM replay.run_state s
  LEFT JOIN replay.experiments e ON e.experiment_id = s.manifest_id
 WHERE e.experiment_id IS NULL;
-- expect: 0 rows (no dangling FK)

-- Wave 9 no-live-mutation safety (plan §8)
SELECT COUNT(*) AS leaks_into_trading
  FROM trading.fills
 WHERE created_at >= NOW() - INTERVAL '15 minutes';
-- expect: ≈ 0 (allow normal demo / live_demo activity if any; replay alone must add 0)

SELECT COUNT(*) AS critical_replay_audit
  FROM learning.governance_audit_log
 WHERE event_type LIKE 'replay_%'
   AND severity IN ('high','critical')
   AND created_at >= NOW() - INTERVAL '15 minutes';
-- expect: 0 (no critical security audit during smoke run)
```

---

## §4 並行 / 串行決策

```
[Wave R0 truth reset]              ← 已含於 plan，不在 Sprint A scope
        │
        ├── R1-T1 binary resolution   ──┐
        ├── R1-T2 restart_all env       │
        ├── R1-T4 audit script         ├── 並行 (1 E1, 4 sub-tasks 同 file 邊界 OK)
        ├── R1-T3 /health endpoint     │   *file 重疊：T1+T3 都動 route_helpers / replay_routes，
        ├── R1-T5 unit tests          ─┘    但 T1 改 1 函式 / T3 加 1 endpoint，**不重疊**
        │
        │   E2 round 1 (R1) → E4 round 1 (R1 regression)
        │
        ├── R2-T1 /experiments/register
        ├── R2-T2 /run FK guard         ──┐ 
        ├── R2-T3 manifest verify       ├── 並行（1-2 E1）；E3 必審 R2-T1+T3
        ├── R2-T4 + R2-T5 tests        ─┘
        │
        │   E2 round 2 (R2) + E3 security audit → E4 round 2
        │
        │   restart_all --rebuild deploy（Linux）
        │
        └── R3-T1 smoke E2E (Linux)        ← 串行；依 R1+R2 deploy
            R3-T2 QA evidence capture       ← 串行；依 R3-T1
```

### Isolation 建議

- **R1 4 並行 sub-tasks** → **NO worktree isolation needed**：T1+T3 動 `route_helpers.py` + `replay_routes.py` 但是 `addtion`-only（T3 加新函式 + 加 router decorator；T1 改既有函式內部）。可派同 1 個 E1 順序處理；或派 2 E1 各做一半（T1+T3 / T2+T4+T5）。
- **R2 4 並行 sub-tasks** → **YES worktree isolation needed**：T1+T2+T3 都動 `replay_routes.py`，T1 加 50+ LOC route，T2 改 line 401-573 既有 `/run` 邏輯，T3 改 line 1195-1334 既有 `/manifest/verify` 邏輯 — 三個區段不直接重疊但都 INSERT/UPDATE 到同檔，git merge 風險高。**建議派 1 E1 順序**或**派 2 E1 + worktree**。
- **R3** → **single E1 + Linux SSH bridge**（不可 isolation；必在 Linux 真實 runtime）。

### 為什麼 R1 + R2 不可同時並行（同 commit 上線）

R1-T3 加 `/health` endpoint 會被 R2-T1 加 `/experiments/register` 在同檔再次擴張；merge 衝突管理成本 > 並行收益。**建議：R1 先 land + deploy 驗證 → R2 再 land + deploy → R3 跑**，三波分別獨立 sprint cycle。

---

## §5 Hidden risks 表

| # | Risk | 嚴重 | 緩解 |
|---|---|---|---|
| H1 | Decision Lease retrofit (Sprint 3 Track H, commit `dbcf845b`) feature flag `OPENCLAW_LEASE_ROUTER_GATE_ENABLED=0`；Sprint A 改 `/run` + `/experiments/register` 路徑會否誤觸 lease？ | 🟢 LOW | replay_routes 純 replay 子系統，**不**走 IntentProcessor → router；router gate 不在 path 內。E3 必 grep `acquire_lease` 確認 R2 沒新引用；symbol_audit.sh 第 226 行 `acquire_lease|release_lease` pattern 為 0 是回歸線。 |
| H2 | `replay_routes.py` 當前 1494 LOC，pre-existing 1500 baseline exception；R2 加 `/experiments/register` ~120 LOC + R2-T2 內部改動 ~40 LOC = 預估 +160 LOC → **~1654 LOC 越過 baseline+5 邊界 154 LOC** | 🟠 HIGH | **必拆**：R2-T1 `/experiments/register` 邏輯抽出到新 `replay/experiment_registry.py` (~150 LOC pure module，沿 `route_helpers.py` 模式)，`replay_routes.py` 只留 thin route handler delegating；R2-T3 verify SQL archive 邏輯抽出到 `replay/manifest_signer.py` 既有 module。最終 `replay_routes.py` 加淨 ≤ +50 LOC，落在 baseline+5 內。 |
| H3 | 14d observation period（plan deferred items + healthcheck cron）正進行中；Sprint A 改 binary resolution / 加 endpoint 是否影響 observation metrics？ | 🟢 LOW | observation 對象是 `replay.run_state` row 累積 + 14d 0 trading mutation；R1+R2+R3 工作目的就是讓這些 metric 從 vacuous truth 變 real evidence — observation 本身 metric 重置 OK，operator 可在 Sprint A 結束後重啟 14d 計時。**但**：Wave 9 continuous_validator.py 必持續 PASS（Sprint A 過程中沒 trading.fills leak），E4 regression 必驗 plan §8 safety SQL。 |
| H4 | V049-V054 schema 已 deploy（Sprint 3 Track I `7a86d2eb`）；R2 manifest registration 是否需新 migration？ | 🟢 LOW | **不需新 migration**：V049 22-col contract 已 land 完整 schema；R2-T1 INSERT 用既有 column。**但**：confirm manifest_jsonb / signature_key_ref / data_window_start_ms / data_window_end_ms 4 col 在 INSERT statement 全 enumerate；E3 必對 V049 col list vs INSERT col list 做 diff（缺 col 會 NOT NULL violation）。 |
| H5 | `OPENCLAW_REPLAY_VERIFY_TEST_KEY` 在 Sprint 1 Track C P0-2 boot guard 強制；R2-T3 拿掉 501 path 後若 archive 也未 ready，verify 必須降級到合理 fail-closed | 🟠 MED | R2-T3 設計：若 secrets file fallback 也找不到 key → 回 410 + `replay_verify_key_archive_not_provisioned`，**不**回 200 false positive；R2-T3 必含 unit test 證 410 行為。 |
| H6 | Linux PG 既有 `replay.experiments` 為 V041 4-col stub + V049 promoted 22-col；row 數 = 0；R2-T1 第一筆 INSERT 撞 pre-existing UNIQUE/CHECK constraint（V049 EXCLUDE GIST window-overlap）的風險 | 🟡 LOW-MED | V049 EXCLUDE 是 pairwise non-overlap protection；register 第一筆 row trivially pass。E4 regression 必含 2-row test：第二 register 用相同 (symbol, strategy, window) → expect 409 / EXCLUDE violation；錯開 window → pass。 |
| H7 | Mac dev 與 Linux runtime 路徑差異：`OPENCLAW_DATA_DIR` Mac 預設 `$HOME/.openclaw_runtime` / Linux `/tmp/openclaw`；R3 在 Linux 跑，Mac 端跑 unit test 時若直接 fixture path hardcode 會 fail | 🟢 LOW | R1-T1 的 fallback chain 已 cross-platform 處理；R1-T5 unit test 用 `os.environ.get(..., default)` patch 不寫死路徑；R3 只在 Linux 跑，無 Mac vs Linux drift 直接風險。 |
| H8 | restart_all.sh export OPENCLAW_BASE_DIR 改動會擴散到所有 API uvicorn worker | 🟢 LOW | env var addition 純加，舊 worker 行為不變；現 production 已透過 `nohup` shell 繼承這 var（grep `restart_engine` line 347 已用 `$base_dir`），R1-T2 只是讓 `restart_api` 對齊。E2 必 diff 兩 function env list 確認對稱。 |
| H9 | R2-T3 拿掉 test_key path 但 test suite 不少 hermetic test 依賴 test_key | 🟡 LOW-MED | E4 必 grep test files 找所有 `OPENCLAW_REPLAY_VERIFY_TEST_KEY` 引用，遷移到 secrets file fixture 路徑或標 deprecated。R2-T3 不可 silently regress 既有 test。 |
| H10 | Codex P0-1 (synthetic walker) **不在 Sprint A scope** — 但 R3 跑出來的 simulated_fills 仍是 synthetic | 🟢 EXPECTED | plan §6 R6 (Fee Calibration) + R5 (Real Decision Path) 才解；Sprint A 的 R3 acceptance 是「4 張表 row > 0」非「fills 真實」。R3 寫的 report 必含 `execution_confidence='none'` (Wave R6 引入的 label，可在 Sprint A 預先寫死) 防 operator 誤把 synthetic 當 calibrated。 |

---

## §6 PM 要決定的 Open Questions

1. **R1 + R2 同 sprint？分 sprint？**
   - 提案：**R1 先 land + Linux deploy 驗證 → 暫停 24h 觀察 R1 PASS → R2 再 land + deploy → R3 smoke run**。三波合計 ~2-3 個工作日。
   - 替代：合併 R1+R2 同 PR 一次 deploy；節省 1 deploy cycle 但回滾單位變大。**PA 推薦分波**。

2. **R2-T3 SQL archive vs secrets file fallback 哪條主？**
   - V042 `replay.signing_keys` table schema reserved 但 0 deploy；本 Sprint 兩種選擇：
     - **(a)** R2-T3 同次 land V042 schema + writer + reader → +1 migration + +200 LOC，risk 大但 long-term clean。
     - **(b)** R2-T3 暫走 secrets file（`$OPENCLAW_SECRETS_DIR/<env>/replay_signing_key`）+ 標 `wiring_status="secrets_file_fallback"` + 開 P2 ticket 跟蹤 V042 work → 保守，符合 plan §6 R2 的 "Wave 6 V042 archive bridge" 已預留 wiring。
   - **PA 推薦 (b)**：R2 已是高風險區，疊 V042 land 會把 sprint 變 1500 LOC migration。

3. **R3 smoke run 在 Linux 跑後，要不要立即啟動 Wave R4 UI 啟用？**
   - plan §6 R4 owner chain 是獨立 wave；R3 evidence-backed 後 UI subtab 可從 disabled 改 backend-readiness gated。
   - **PA 觀察**：UI 啟用會曝露 unauthenticated path 風險到 GUI 訪客；建議 R4 與 R3 至少間隔 1 個 sprint 確認 R3 evidence 健康再 unmask UI。

4. **Sprint A 是否需要 QC 介入？**
   - plan §6 R1-R3 owner chain 都沒列 QC（R5+R6 才有）；但 R2-T1 manifest schema 設計、R3 fee model assumption（雖 Sprint A 不做 calibration）可以拉 QC 提前 push back，避免 R5 翻案。
   - **PA 推薦**：Sprint A 派發前讓 QC 看一眼 R2-T1 manifest_jsonb 結構 + R3 confidence label 預設值，1h cost；**不**列為強制工作鏈。

5. **Decision Lease feature flag 是否在 Sprint A 期間 flip？**
   - plan deferred items 中 ~05-15 P0-EDGE-2 後 operator 動作；Sprint A 工作不依賴 lease。
   - **PA 答**：**保持 OFF**；Sprint A 不應與 lease canary 同 deploy 視窗。

---

## Acceptance test alignment (plan §7 matrix)

| Sprint A wave | plan §7 gate | 證據 |
|---|---|---|
| R1 | A1 — API can spawn runner | `/run` 不再 binary_not_found；audit script PASS |
| R2 | A3 — No dangling manifest FK | `/run` 不能 INSERT 沒對應 experiments row |
| R3 | A2 — DB lineage exists | 4 表 row > 0 |
| R3 | A9 — No live mutation | Wave 9 safety SQL 0 leak |

A4 / A5 / A6 / A7 / A8 / A10 屬 R5-R9 sprint 範圍，**不**在 Sprint A acceptance。

---

## 反爬蟲風險評級總結

- **R1-T1/T2/T4**：低。
- **R1-T3**：低-中（新 endpoint，需 E2 看 auth 對齊）。
- **R2-T1/T2**：高（FK guard + atomic registration + size cap + auth）。
- **R2-T3**：中-高（拿掉 501 path 引入 archive lookup，V042 不存在時降級邏輯設計易出錯）。
- **R3**：低（純驗證，不寫業務邏輯）。

PA 沒法替 R2-T1+T3 的安全邊界做最終決定 — 必拉 E3 同步 audit。

---

PA DESIGN DONE: report path: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-04--ref20_sprint_a_task_dag.md`
