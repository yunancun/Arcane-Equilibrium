---
report: P1-OPS-2-SECRET-SPLIT — E1 Phase 1 IMPL DONE
date: 2026-05-27
author: E1 (Backend Developer, Rust + Python + Bash)
phase: Phase 1 IMPL DONE — 待 E2 review + A3 對抗式核驗 + E4 regression
status: cargo test 24/24 PASS (含 5 新 OPS-2 test) / pytest 18/18 PASS (8 新 + 10 batch B) / bash -n 三腳本 OK / cross-lang HMAC fixture byte-identical 雙端 PASS
parent spec: docs/execution_plan/specs/2026-05-26--p1-ops-2-secret-split-design.md (484 行)
production engine: 未碰
---

# §0. TL;DR

Phase 1 完整 IMPL：新 `OPENCLAW_LIVE_AUTH_SIGNING_KEY` env var path 在 Rust + Python + Bash 三 track 同時接線；Phase 1 fallback to `OPENCLAW_IPC_SECRET` 帶 rate-limit WARN（≤1/h，雙端對齊）；restart_all `prepare_runtime_secret_files` 自動 seed `live_auth_signing_key.txt` 自 `ipc_secret.txt`（`[ ! -f ]` 條件嚴 = E2 重點 #2 守住）；新 `AuthError::LiveAuthSigningKeyMissing` + `auth_error_kind` "live_auth_signing_key_missing" 變體（IpcSecretMissing 變體 + ipc_secret_missing 字串 Phase 1 保留 backward-compat）；cross-lang HMAC byte-identical fixture pin = `1b2b18d7e212d0d1e8f943c25f6f070b2ba75013b8fd5c3a021800d11b8b78fc`，Rust + Python 同 fixture 算出同 hex；4 個 PA negative-checklist 檔案（optuna_optimizer / replay_earn_preflight / edge_p2_flip_dry_run / ipc_server::connection）0 改動。

# §1. 3 Track LOC 變動矩陣

| Track | 檔案 | 性質 | 行數變動 |
|---|---|---|---|
| **A · Rust** | `rust/openclaw_engine/src/live_authorization.rs` | helper fn + 1 新 enum 變體 + 5 新 unit test + 1 舊 test ENV lock 補強 | +371 (邏輯約 +100；對抗式 unit tests 約 +271) |
| **A · Rust** | `rust/openclaw_engine/src/live_auth_watcher_tests.rs` | test env helper 加 `OPENCLAW_LIVE_AUTH_SIGNING_KEY` set/clear | +5 |
| **B · Python** | `program_code/exchange_connectors/bybit_connector/control_api_v1/app/live_trust_routes.py` | 新 `_read_live_auth_signing_key` helper + 2 call site rename + WARN rate-limit state | +74 |
| **B · Python** | `program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_live_trust_routes_secret_split.py` | **新建** 8 test：primary wins / fallback emit / rate-limit 1/h / reemit after interval / both unset / sign uses LIVE_AUTH / cross-lang HMAC byte-identical / sign raises on missing | +244 |
| **C · Bash** | `helper_scripts/restart_all.sh` | env var 定義 + `prepare_runtime_secret_files` seed 邏輯 + 2 spawn point inject | +21 |
| **C · Bash** | `helper_scripts/fresh_start.sh` | env var 定義 + 2 spawn point inject (engine + API) | +6 |
| **C · Bash** | `helper_scripts/clean_restart.sh` | env var 定義 + 2 spawn point inject | +5 |
| **C · Doc** | `helper_scripts/SCRIPT_INDEX.md` | restart_all entry 補 OPS-2 SECRET-SPLIT 說明 | +1 (擴句) |
| **Total** | — | — | 邏輯改動 ≈ 212 LOC + 對抗式 test 515 LOC（spec §8.1 估 125 LOC 邏輯 + 40 LOC test；超估主因是 Rust 5 新 unit test 寫詳實對應 spec §4.4 + §8.5 雙視角驗證）|

# §2. Cross-lang HMAC byte-identical fixture verify 結果

**Pinned hex**：`1b2b18d7e212d0d1e8f943c25f6f070b2ba75013b8fd5c3a021800d11b8b78fc`

**Canonical payload byte-identical invariant**：`"2|T0_ENTRY|1700000000000|1700086400000|ncyu|live_reserved|live_demo"`

**Key**：`"test-live-auth-signing-key-do-not-use-in-prod"`

**Rust 端**：`live_authorization::tests::cross_lang_hmac_fixture_is_byte_identical` — `assert_eq!(sig, "1b2b18d7e2...")` PASS。

**Python 端**：`test_live_trust_routes_secret_split.py::test_cross_lang_hmac_fixture_matches_rust_compute_signature` — 同 fixture 計 sig，三段 assert（algorithm 對齊 stdlib hmac / pinned hex 對齊 / 64 hex chars 對齊）全 PASS。

**獨立 stdlib 重算驗證**：`python3 -c "import hmac,hashlib; print(hmac.new(b'test-live-auth-signing-key-do-not-use-in-prod', b'2|T0_ENTRY|1700000000000|1700086400000|ncyu|live_reserved|live_demo', hashlib.sha256).hexdigest())"` → `1b2b18d7e212d0d1e8f943c25f6f070b2ba75013b8fd5c3a021800d11b8b78fc` 與雙端 unit test pinned 完全一致。

**意義**：未來任何一端改 canonical_payload 格式（pipe sep / env_allowed dedup / version 順序）或 HMAC 算法 / hex encoding 立刻在此 fixture 雙端 fail。對應 spec §8.5 E2 重點 #1 + §1.2 防 Earn first stake silent fail。

# §3. Phase 1 fallback WARN rate-limit IMPL evidence

**Rust（`live_authorization.rs`）**：
- `static LAST_FALLBACK_WARN_TS: AtomicU64` process-wide 時戳
- `const FALLBACK_WARN_INTERVAL_SECS: u64 = 3600`
- `compare_exchange(last, now_secs, AcqRel, Relaxed)` 保證多 caller 並發只一個贏得 emit 權
- 觸發點：`read_live_auth_signing_key()` fallback 分支內單一 emit

**Python（`live_trust_routes.py`）**：
- module-level `_fallback_warn_state = {"last_ts": 0.0, "lock": threading.Lock()}`
- `_FALLBACK_WARN_INTERVAL_SECS = 3600`（與 Rust 同窗口）
- `with _fallback_warn_state["lock"]: ... time.time() - last_ts >= interval ... logger.warning(...)`
- 同 process 內 sign + verify 兩路徑共享同一 rate-limit state（每 1h 雙路徑合計最多 1 條 WARN）

**Empirical 驗證**：`test_phase1_fallback_warn_rate_limit_one_per_hour` 連續 100 次 `_read_live_auth_signing_key()` call 後 `caplog` 過濾 `ops2_secret_split_phase1_fallback` 事件 → 僅 1 條 WARN。第二測試 `test_phase1_fallback_warn_reemits_after_interval` 把 `last_ts` 倒回 1h+1s 前 → 第二次 emit 觸發，PASS。

**watcher 5s poll 場景換算**：未限速 = 86400/5 = 17,280 logs/day（雙路徑 ~34k/day）→ rate-limit 後 24 logs/day max（每 1h 雙路徑合計 1 條）。

# §4. 5 hidden risk PA caught 對應 mitigation verify

| Spec §9 風險 | 等級 | E1 mitigation | Verify |
|---|---|---|---|
| §9.1 IPC 客戶端腳本誤遷移 | **HIGH** | `grep -l OPENCLAW_LIVE_AUTH_SIGNING_KEY` 對 4 個 negative-checklist 檔案（optuna_optimizer.py / replay_earn_preflight.py / edge_p2_flip_dry_run.py / ipc_server::connection.rs）| **0 hit ✅** — 4 個 IPC 客戶端域檔案完全未動 |
| §9.2 `replay_earn_preflight.py` false-positive | MEDIUM | 同 §9.1 negative checklist | **0 hit ✅** — Stage 0R internal manifest 簽名路徑 0 改動 |
| §9.3 Cross-platform user-home 硬編碼 | LOW | 三 bash script 變數均走 `$SECRETS_ROOT/environment_files/live_auth_signing_key.txt`（`$SECRETS_ROOT` 由 `OPENCLAW_SECRETS_ROOT` env var 控制，default `$HOME/BybitOpenClaw/secrets`）| `grep -n '/home/ncyu\|/Users/ncyu' helper_scripts/restart_all.sh helper_scripts/fresh_start.sh helper_scripts/clean_restart.sh` → **0 hit ✅** |
| §9.4 Phase 1 seed vs OPS-2 runbook urandom 衝突 | LOW | restart_all seed 邏輯加 `echo` 訊息標註 "same material; rotate independently per OPS-2 runbook"；運行時提示 operator 第一次 rotation 必須 from urandom | **見 restart_all.sh seed 邏輯 echo line ✅** — runbook 撰寫責 PA + E1 在 P1-OPS-2-RUNBOOK 處理 |
| §9.5 Watcher 與 Phase 2 panic ordering | LOW | Phase 2 panic block 預留 TODO（未實 Phase 2）；本 IMPL 階段 Phase 1 fallback 不引入 boot ordering 改變 | Phase 1 fallback path 在 `load_and_verify` 內 inline，不新 spawn task → 不引入 ordering 問題 ✅ |
| §9.6 alert rule 字串 break change | LOW-MEDIUM | Phase 1 保留 `IpcSecretMissing` 變體 + `ipc_secret_missing` 字串；新增 `LiveAuthSigningKeyMissing` + `live_auth_signing_key_missing` 並列（不替換）| **`auth_error_kind` test asserts both labels stable ✅** — operator 個人 Grafana dashboard 不破；Phase 2 cutover 時 alert rule 同步加新字串 |

# §5. Deploy SOP（給 operator 手動 deploy 用 + 14d soak 觀察點）

## 5.1 Deploy 前置（main session push 後）

1. SSH trade-core：`cd ~/BybitOpenClaw/srv && git fetch && git pull --ff-only`
2. 驗 working tree clean + 確認 commit SHA 對齊 E2/E4/QA sign-off。
3. 確認 `$SECRETS_ROOT/environment_files/ipc_secret.txt` 存在 + chmod 600 + 非空（不存在 = 既有 deploy 已有 bug，須先 OPS-2 runbook 處理）。

## 5.2 Deploy（推薦 atomic 路徑）

```
bash helper_scripts/build_then_restart_atomic.sh
```

該腳本會：
1. flock build_window → cargo build --release （重建 engine binary 含 OPS-2 Rust 變更）
2. SHA snapshot
3. restart_all.sh（自動觸發 `prepare_runtime_secret_files`）：
   - 若 `live_auth_signing_key.txt` 不存在 → 自動 seed from `ipc_secret.txt`（首次 boot）+ echo `>>> OPS-2 SECRET-SPLIT phase 1: seeded ...`
   - 已存在則保留現值（重 boot idempotent）
   - chmod 600 確保
4. spawn engine + API（兩 process 同時收 `OPENCLAW_LIVE_AUTH_SIGNING_KEY_FILE` env）
5. verify `/proc/$PID/exe` SHA == on-disk SHA

## 5.3 Deploy 後立即驗證（D+0）

```
# 1. 驗 secret file 存在
ssh trade-core 'ls -la $HOME/BybitOpenClaw/secrets/environment_files/live_auth_signing_key.txt'
# 期望：mode -rw------- + 非零 byte + mtime ~ deploy 時點

# 2. 驗 file 與 ipc 同值（Phase 1 seed 行為）
ssh trade-core 'sha256sum $HOME/BybitOpenClaw/secrets/environment_files/live_auth_signing_key.txt $HOME/BybitOpenClaw/secrets/environment_files/ipc_secret.txt'
# 期望：兩 hash 完全相同（首次 seed 後）

# 3. 驗 engine + API 進程 env 注入
ssh trade-core 'cat /proc/$(pgrep -x openclaw-engine | head -1)/environ | tr "\0" "\n" | grep LIVE_AUTH_SIGNING_KEY_FILE'
# 期望：OPENCLAW_LIVE_AUTH_SIGNING_KEY_FILE=/home/ncyu/BybitOpenClaw/secrets/environment_files/live_auth_signing_key.txt

# 4. 驗 engine log 無 WARN（兩 env 都 set → 不應 fallback）
ssh trade-core 'grep -c "ops2_secret_split_phase1_fallback" /tmp/openclaw/engine.log'
# 期望：0

# 5. 驗 live pipeline 正常（若 Live slot active）
ssh trade-core 'curl -s http://localhost:8000/api/v1/live/auth/trust-status | python3 -m json.tool | head -20'
# 期望：tier / expires_at_ms 正常；不出 "ipc_secret_missing" / "live_auth_signing_key_missing" reason
```

## 5.4 14d Soak 觀察點（D+0..D+14）

| 觀察項 | 工具 | 期望值 | 異常處理 |
|---|---|---|---|
| **fallback WARN 計數** | `grep -c "ops2_secret_split_phase1_fallback" /tmp/openclaw/engine.log /tmp/openclaw/api.log` | 累積 = 0 | 若 > 0 表示新 env 未生效，檢查 restart_all 是否走到 spawn point；不可直接 Phase 2 cutover |
| **engine PID 穩定** | `pgrep -x openclaw-engine` + restart 計數 | 與 deploy 前 baseline 一致 | 不穩定 → 不可 Phase 2 |
| **live_auth_signing_key.txt 完整性** | `ls -la` + `sha256sum` | mode 600 + sha 與 ipc_secret.txt 同 | mode 不對 → operator 手動 chmod 600；sha 不同 → operator 已 rotate（可接受，記入 Phase 2 readiness check）|
| **trust-status verify path** | `/api/v1/live/auth/trust-status` reason 字段 | 非 `ipc_secret_missing` / `live_auth_signing_key_missing` | 若出現 → engine 找不到 key file，檢查 env injection |
| **Operator 走過 /auth/renew ≥1 次** | API access log + `learning.live_auth_renewals` (若有) | 至少 1 次 | 0 次 → Phase 2 前必須 manually trigger 一次 renew 重簽（spec §5 backward compat 處理段）|

## 5.5 14d soak start date proposal

**proposed start date**：deploy 當天 = soak D+0；spec §3.1 描述 14d 連續 0 WARN log → D+14 Phase 2 PR ready。

**Proposed schedule**（pending operator approval）：
- **D+0 = 2026-05-27** (today UTC)：deploy（atomic restart）
- **D+0..D+14 = 2026-05-27..2026-06-10**：soak（每日 §5.4 check）
- **D+14 = 2026-06-10**：Phase 2 IMPL（移 fallback + 加 `main.rs` 第二 panic block + `IpcSecretMissing` 變體刪除）
- **D+14+1 = 2026-06-11**：90d cadence 計時開始（first rotation due 2026-09-09）

**Phase 2 IMPL 預留位置**（本 IMPL 階段 TODO，不寫 patch）：
- `live_authorization.rs::read_live_auth_signing_key` fallback 分支整段刪除（spec §3.2）
- `live_authorization.rs::AuthError::IpcSecretMissing` 變體刪除 + display 移除 + `auth_error_kind` arm 刪除
- `live_trust_routes.py::_read_live_auth_signing_key` fallback 分支整段刪除 + return type 改 `str | None` → 純 raise on missing
- `live_trust_routes.py::line 473` reason 字串 `ipc_secret_missing` → `live_auth_signing_key_missing`
- `main.rs:399-407` 之後新增第二 panic block：`if live_bindings.is_some() && secret_env::var_or_file("OPENCLAW_LIVE_AUTH_SIGNING_KEY").is_none() { panic!("..."); }`（spec §3.2）

# §6. 對抗式測試覆蓋摘要

| 測試 | 端 | 驗什麼 | 結果 |
|---|---|---|---|
| `cross_lang_hmac_fixture_is_byte_identical` | Rust | canonical_payload format + HMAC algo + 64 hex chars + pinned hex | PASS |
| `mismatched_live_auth_key_produces_bad_signature` | Rust | 用 key-A 簽 + key-B 驗 → BadSignature（防 IPC leak 仍能偽造 live auth） | PASS |
| `phase1_fallback_reads_ipc_secret_when_live_auth_unset` | Rust | 新 env 未設 → 讀舊 env（backward-compat 路徑） | PASS |
| `live_auth_signing_key_primary_wins_over_ipc_fallback` | Rust | 兩 env 都設且值不同 → primary | PASS |
| `live_auth_signing_key_missing_returns_specific_variant` | Rust | 兩 env 都未設 → 新變體（非舊 IpcSecretMissing）| PASS |
| `load_and_verify_uses_live_auth_signing_key_when_set` | Rust | 端到端 load_and_verify 走 primary path（IPC=different 不污染）| PASS |
| `auth_error_kind_labels_are_stable` | Rust | 兩 alert kind 字串 stable | PASS |
| `test_primary_live_auth_key_wins_over_ipc_fallback` | Python | 同 Rust primary wins | PASS |
| `test_phase1_fallback_emits_warn_when_only_ipc_set` | Python | fallback 觸發 WARN 1 條 | PASS |
| `test_phase1_fallback_warn_rate_limit_one_per_hour` | Python | 100 calls / ms 級內 → 1 WARN | PASS |
| `test_phase1_fallback_warn_reemits_after_interval` | Python | 倒回 1h+1s → 再 emit | PASS |
| `test_returns_empty_when_both_envs_unset` | Python | fail-closed 空字串 | PASS |
| `test_sign_authorization_uses_live_auth_signing_key` | Python | primary key-a 簽 ≠ fallback key-b 簽 | PASS |
| `test_cross_lang_hmac_fixture_matches_rust_compute_signature` | Python | Rust pinned hex 對齊 | PASS |
| `test_write_signed_live_authorization_raises_when_both_envs_unset` | Python | missing 必 raise + 訊息含新 env name | PASS |
| 既有 `test_batch_b_security_auth.py::test_static_proxy_and_secret_surfaces_are_locked_down` | Python | 3 restart 腳本仍無 `OPENCLAW_IPC_SECRET="${...}` 直接 env 注入 | PASS（split 後不破 invariant）|

# §7. 不確定 / 須 E2 / A3 review 確認

1. **AuthError enum rename 時機**：本 IMPL 階段保留 `IpcSecretMissing` + 並列加 `LiveAuthSigningKeyMissing`（避免 Phase 1 14d 期間 alert rule break）。spec §4.1.1 Phase 2 才 rename。E2 須確認此 staged migration 策略可接受。
2. **alert config grep 已 0 hit but external dashboards**：本 repo grep `ipc_secret_missing` 0 hit beyond unit test；operator 個人 Grafana / journald 規則無法 audit。Deploy SOP §5.3 step 4 grep engine.log 是 runtime invariant，但 Phase 2 cutover 前 PM 須 operator 確認外部 alert rule 已加 `live_auth_signing_key_missing` 對齊。
3. **Phase 1 兩 env 同值 audit log 不分**：spec §8.6 安全反 pattern PA 守衛之一 — restart_all seed 時 echo line 含 "phase 1 seeded same material" 標記；audit row 寫入屬 E3-MED-1 follow-up endpoint（本 spec 留 hook 不實）。本 IMPL 守住 echo 標記，audit row 留 follow-up TODO。
4. **`_fallback_warn_state` thread safety**：Python 用 `threading.Lock`；FastAPI uvicorn 多 worker 場景下 4 worker 各自獨立 process，每 worker 1h 1 條 = 4 條/h theoretical max。可接受（≤4 logs/h <<< 7200 logs/day）。Rust 端 atomic 是 process-wide，engine 單 process 故 1 條/h。

# §8. 主要建議

1. E2 review 4 重點：
   - §1 LOC 矩陣 vs spec §8.1 預估
   - §4 5 hidden risk mitigation
   - cross-lang HMAC fixture pinning 是否需 freeze 為共享 fixture file（vs 兩 test file 各自 pin 同 hex）
   - Phase 2 TODO 標記是否需轉 GitHub Issue / TODO active 條目
2. A3 / E2 對抗式核驗（per `feedback_impl_done_adversarial_review`）：
   - 重點驗 Phase 1 seed 邏輯 idempotency（restart_all 重 boot 不覆蓋 rotated key — spec §8.5 E2 重點 #2）
   - 重點驗 WARN log rate ≤1/h 真的不洪流
3. E4 regression 必跑：
   - 對 `restart_all.sh` mock prepare_runtime_secret_files 環境跑 dry-run（Mac mock；Linux ssh trade-core 真實 PG + secrets 跑一次 verify §5.3 step 1-4）
   - Linux PG empirical：spec §4.4 integration A/B/C **未在本 IMPL 跑**（屬 E4 regression 範圍，本 IMPL 只跑 unit test）
4. PM 後續：approve 14d soak start date proposal 2026-05-27 → 2026-06-10

# §9. 出證 commands（operator empirical 重跑）

```
# Rust 24/24
cargo test -p openclaw_engine --lib --manifest-path rust/Cargo.toml live_authorization 2>&1 | tail -3
# expected: "test result: ok. 24 passed; 0 failed; 0 ignored"

# Python new 8 + batch B 10
python3 -m pytest \
  program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_live_trust_routes_secret_split.py \
  program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_batch_b_security_auth.py 2>&1 | tail -3
# expected: "18 passed in 0.21s"

# Bash syntax
bash -n helper_scripts/restart_all.sh && bash -n helper_scripts/fresh_start.sh && bash -n helper_scripts/clean_restart.sh && echo "三腳本 OK"

# Cross-lang HMAC pinned hex 獨立驗證
python3 -c "import hmac,hashlib; print(hmac.new(b'test-live-auth-signing-key-do-not-use-in-prod', b'2|T0_ENTRY|1700000000000|1700086400000|ncyu|live_reserved|live_demo', hashlib.sha256).hexdigest())"
# expected: 1b2b18d7e212d0d1e8f943c25f6f070b2ba75013b8fd5c3a021800d11b8b78fc

# PA negative-checklist 守住（4 個 IPC client 域檔案 0 動）
grep -l "OPENCLAW_LIVE_AUTH_SIGNING_KEY" program_code/ml_training/optuna_optimizer.py helper_scripts/canary/replay_earn_preflight.py helper_scripts/canary/edge_p2_flip_dry_run.py rust/openclaw_engine/src/ipc_server/connection.rs 2>/dev/null
# expected: 空輸出（0 hit）
```

**END OF E1 IMPL REPORT**
