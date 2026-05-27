---
report: P1-OPS-2-SECRET-SPLIT — E2 Adversarial Review
date: 2026-05-27
author: E2 (Senior Backend Code Reviewer + Adversarial Auditor)
phase: E1 IMPL DONE — adversarial review per workflow chain
status: APPROVE-CONDITIONAL — 0 BLOCKER / 0 HIGH / 2 MEDIUM (test race + bash atomicity, both LOW prod impact) / 3 LOW (note / defer)
parent spec: docs/execution_plan/specs/2026-05-26--p1-ops-2-secret-split-design.md
parent E1 IMPL: docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-27--ops_2_secret_split_impl.md
---

# §0. TL;DR

477 LOC (rust 371 + python 74 + bash 32) 全 read。對抗 6 視角 (root cause / edge / race / leakage / shortcut / spec-drift) + E2 8 條 checklist + OpenClaw 9 條 §3 全跑。
verdict = **APPROVE-CONDITIONAL** — 0 BLOCKER / 0 HIGH。改動範圍與 PA spec §4.1-§4.3 完全對齊，5 hidden risk mitigation 全 verify，cross-lang HMAC pinned hex 三端 (Rust pin / Python pin / 獨立 stdlib 重算) byte-identical。

2 MEDIUM = (a) live_authorization::tests::ENV_TEST_LOCK vs live_auth_watcher_tests::ENV_GUARD 兩獨立 mutex 可在 cargo test 並行下殘留 env var race (CI flakiness 風險，非 prod)；(b) restart_all seed `cp ipc_secret.txt live_auth_signing_key.txt` 非 atomic (中斷可能 partial-written；首 boot 場景，無 race target，accept)。

3 LOW = (c) Phase 2 panic block 預期 line position 已實 verify (現 line 397-411，spec §9.5 "在 watcher spawn 前" 對齊)；(d) `compare_exchange(AcqRel, Relaxed)` 對單 atomic 略 over-engineered（Relaxed 即可）非 bug；(e) fresh_start.sh 不 seed 但無 explicit FAIL 提示 operator——defer 到 P1-OPS-2-RUNBOOK。

允許 PASS to E4 regression + CC review，無強制退回 E1。

# §1. Track ABC Issue 矩陣

## §1.1 Track A · Rust `live_authorization.rs` + `live_auth_watcher_tests.rs`

| 檢查項 | 結論 |
|---|---|
| `OPENCLAW_LIVE_AUTH_SIGNING_KEY` env load path thread-safe | ✅ `secret_env::var_or_file` (line 12-32) 同 path 唯一 helper；env read 是 Rust std 內部 single-shot；空字串自動 filter (line 14-16 + 27-30) → 空 env / 空 file return `None`，fallback 必觸 |
| `AuthError::LiveAuthSigningKeyMissing` 新變體 match exhaustiveness | ✅ grep `AuthError::` 外部 0 個 match arm (drawdown_revoke.rs 只有 doc comment 引用 `FileMissing`)；`auth_error_kind()` (line 237) 已 exhaustive 加新 arm "live_auth_signing_key_missing"；`IpcSecretMissing` 變體保留 Phase 1 backward-compat 不破 alert string |
| Phase 1 fallback fail-closed 條件 | ✅ `read_live_auth_signing_key` (line 392-419) — primary None + fallback None → return None；`load_and_verify` (line 423) `.ok_or(AuthError::LiveAuthSigningKeyMissing)?` 必走新變體 fail-closed |
| AtomicU64 + compare_exchange WARN rate-limit ≤1/h | ✅ 雙重 guard：`now_secs.saturating_sub(last) >= 3600` (時間窗口) + `compare_exchange(last, now_secs, AcqRel, Relaxed).is_ok()` (multi-caller 並發 CAS) 保證僅一個 emit；無 race emit-multiple；saturating_sub 處理 clock rewind (NTP slew) |
| 5 new unit test 覆蓋邊界 | ✅ `phase1_fallback_reads_ipc_secret_when_live_auth_unset` (新 unset) / `primary_wins_over_ipc_fallback` (both present) / `missing_returns_specific_variant` (both unset → 新變體) / `mismatched_live_auth_key_produces_bad_signature` (key-A 簽 key-B 驗 → BadSignature 防 leak attack) / `cross_lang_hmac_fixture_is_byte_identical` (pinned hex)；既有 `load_and_verify_reads_file_via_env_override` 補強 ENV_TEST_LOCK 串行 |
| `compare_exchange(AcqRel, Relaxed)` orderings | LOW · 單 atomic 無 cross-memory dep；Relaxed 即可；AcqRel 略 over-engineered；非 bug |

**race issue (MEDIUM-LOW)**：`live_authorization::tests::ENV_TEST_LOCK` 與 `live_auth_watcher_tests::ENV_GUARD` 是兩個獨立 static mutex；cargo test --lib 同 test binary 並行下若兩文件 test 同跑可能 race process-global env (`OPENCLAW_LIVE_AUTH_SIGNING_KEY` / `OPENCLAW_IPC_SECRET`)。E1 IMPL report 已 PASS 24/24 表示實測未 trigger，但屬 latent flakiness。Mitigation = 合併到 crate-level 共用 lock 或 `#[serial]` macro；可選 fix。**非 prod 風險**，不阻 Phase 1 land。

## §1.2 Track B · Python `live_trust_routes.py` + test_live_trust_routes_secret_split.py

| 檢查項 | 結論 |
|---|---|
| `_read_live_auth_signing_key` 處理 file missing / permission denied | ✅ 走 `get_secret_value` (`secret_runtime.py:21-41`) — `Path(file_path).read_text` 捕 `OSError` 包含 `PermissionError`/`FileNotFoundError`→ return None；本 helper `(get_secret_value(...) or "").strip()` 空字串 fallthrough；fail-closed |
| 2 callsite (line 272 sign + line 523 verify) 完整替換 | ✅ grep `OPENCLAW_IPC_SECRET` in live_trust_routes.py 只剩 (a) docstring (line 60 / 264) / WARN log text (line 88) / (b) error message (line 276) — 都是 Phase 1 兼容字串；無 leftover direct read |
| threading.Lock 在 sync route 中安全 | ✅ FastAPI route `def get_trust_status` / `def post_live_renew` / `def post_live_renew_review` 都是 sync def — uvicorn 用 threadpool 跑；`threading.Lock` 正確；非 asyncio 阻塞 |
| `_read_live_auth_signing_key` 返回類型一致 | ✅ helper 簽名 `-> str`（空字串 = fail）；caller `if not ipc_secret: raise / return unverifiable`；契約 clear |
| 8 new unit test 覆蓋 | ✅ primary wins / fallback emit 1 WARN / 100 calls 1 WARN / 1h+ 重 emit / both unset 回 "" / sign uses LIVE_AUTH / cross-lang HMAC pin / raise on missing — 完整 |
| replay_earn_preflight false-positive mitigation | ✅ `helper_scripts/canary/replay_earn_preflight.py:480` 仍讀 `OPENCLAW_IPC_SECRET` 未動；Stage 0R internal HMAC manifest 信任域與 live-auth 完全分離 (per PA spec §2.3 + §9.2) |

## §1.3 Track C · Bash `restart_all.sh` / `fresh_start.sh` / `clean_restart.sh`

| 檢查項 | 結論 |
|---|---|
| seed `[ ! -f live_auth_signing_key.txt ]` 條件嚴 | ✅ `[ ! -f "$OPENCLAW_LIVE_AUTH_SIGNING_KEY_FILE" ] && [ -f "$OPENCLAW_IPC_SECRET_FILE" ]` (restart_all.sh:157-162) — 已 rotate 之 key 不被覆蓋；重 boot idempotent；fresh_start + clean_restart 不 seed |
| seed atomicity | MEDIUM-LOW · `cp` 非 atomic；中斷可能 partial-written。首 boot 場景無 race target；spec 未要求；accept |
| 2 spawn point (engine + API) env inject | ✅ restart_all.sh:543 engine spawn + line 712 API spawn 均加 `OPENCLAW_LIVE_AUTH_SIGNING_KEY_FILE="$OPENCLAW_LIVE_AUTH_SIGNING_KEY_FILE"` 環境注入；fresh_start.sh:351 + 360 / clean_restart.sh:388 + 397 mirror |
| 跨平台 user-home 0 hardcode | ✅ grep `/home/ncyu|/Users/[^/]+` 三 script + 兩 rust + 一 python + 一 test = 0 hit；路徑走 `$SECRETS_ROOT/environment_files/...` 由 `OPENCLAW_SECRETS_ROOT` env 解 |
| bash -n 三 script 語法 OK | ✅ restart_all / fresh_start / clean_restart 全 PASS |

# §2. PA 5 hidden risk mitigation 完整 verify

| Spec §9 風險 | 等級 | E1 mitigation | E2 verify |
|---|---|---|---|
| §9.1 IPC 客戶端腳本誤遷移 | **HIGH** | 4 negative-checklist 檔不動 | ✅ `grep -l "OPENCLAW_LIVE_AUTH_SIGNING_KEY" optuna_optimizer.py replay_earn_preflight.py edge_p2_flip_dry_run.py ipc_server/connection.rs` = **0 hit**；ipc_client.py / earn_routes.py / ipc_client_sync.py / executor_routes.py 也保留 `OPENCLAW_IPC_SECRET` 不誤動 |
| §9.2 `replay_earn_preflight.py` false-positive | MEDIUM | 同 §9.1 negative checklist | ✅ replay_earn_preflight.py:480 仍 `os.environ.get("OPENCLAW_IPC_SECRET")` — Stage 0R internal manifest 信任域保留；無誤遷移 |
| §9.3 Cross-platform user-home 硬編碼 | LOW | 三 bash 走 `$SECRETS_ROOT` 變數 | ✅ 全 patch 0 hit `/home/ncyu` / `/Users/ncyu` (跨 rust + python + bash + test) |
| §9.4 Phase 1 seed vs OPS-2 runbook urandom 衝突 | LOW | restart_all seed 含 echo "phase 1 seeded same material; rotate independently per OPS-2 runbook" | ✅ restart_all.sh:161 echo line 落地；runbook 撰寫責 PA + P1-OPS-2-RUNBOOK 處理 |
| §9.5 Watcher 與 Phase 2 panic ordering | LOW | Phase 1 fallback inline 在 `read_live_auth_signing_key`，不新 spawn task | ✅ Phase 1 不引入 boot ordering 改變；Phase 2 panic block 位置 main.rs:402 (IPC FIX-10 panic) 之後立即 mirror，TODO marker 在 `read_live_auth_signing_key` 註明 (rust line 397-398) |
| §9.6 alert rule 字串 break change | LOW-MEDIUM | Phase 1 保留 `IpcSecretMissing` + `ipc_secret_missing` 並列加新 `LiveAuthSigningKeyMissing` + `live_auth_signing_key_missing`；不替換 | ✅ `auth_error_kind_labels_are_stable` test 雙 label assert；Python 端 `_read_signed_live_authorization_status` line 528-531 保留 `reason="ipc_secret_missing"` + Phase 2 cutover TODO 明確 |

# §3. Cross-lang HMAC fixture 真實一致 verify

**Pinned hex**：`1b2b18d7e212d0d1e8f943c25f6f070b2ba75013b8fd5c3a021800d11b8b78fc`

**Canonical payload byte**：`"2|T0_ENTRY|1700000000000|1700086400000|ncyu|live_reserved|live_demo"`

**Key**：`"test-live-auth-signing-key-do-not-use-in-prod"`

| 端 | Test | 驗證 | 結果 |
|---|---|---|---|
| Rust | `live_authorization::tests::cross_lang_hmac_fixture_is_byte_identical` (line 745) | `assert_eq!(sig, "1b2b18d7e212d0...")` + 64-char hex + self-consistency | ✅ pinned (per E1 IMPL report) |
| Python | `test_cross_lang_hmac_fixture_matches_rust_compute_signature` (line 184-223) | `_sign_authorization_payload` vs stdlib `hmac.new(...).hexdigest()` + pinned hex | ✅ pinned (per E1 IMPL report) |
| 獨立 stdlib | E2 本次重算：`python3 -c "import hmac,hashlib; print(hmac.new(b'test-live-auth-signing-key-do-not-use-in-prod', b'2|T0_ENTRY|1700000000000|1700086400000|ncyu|live_reserved|live_demo', hashlib.sha256).hexdigest())"` | 三端對齊 | ✅ 輸出 = `1b2b18d7e212d0d1e8f943c25f6f070b2ba75013b8fd5c3a021800d11b8b78fc` 完全一致 |

**驗證意義**：未來任一端改 canonical_payload 格式 / HMAC 算法 / hex encoding / pipe separator → 此 fixture 雙端 fail。對應 spec §1.2 防 Earn first stake silent fail。

**WARN rate-limit 100 calls/ms empirical**：Python `test_phase1_fallback_warn_rate_limit_one_per_hour` 連續 100 次 `_read_live_auth_signing_key()` 後 `caplog` 過濾 → 1 WARN（per E1 IMPL report）。Rust 端 `LAST_FALLBACK_WARN_TS` AtomicU64 CAS 邏輯保證並發下 deterministic 1 emit / 1h（spec §8.5 對齊）。

# §4. Issues 退回 E1 list

**0 BLOCKER / 0 HIGH**。

**2 MEDIUM**（CI flakiness / 部署 robustness — 非 prod risk）：

1. **MEDIUM-CI · Test-only env var race**：`live_authorization::tests::ENV_TEST_LOCK`（mod-local）與 `live_auth_watcher_tests::ENV_GUARD`（檔案-local）是兩個獨立 mutex，cargo test --lib 同 test binary 並行下可能殘留 env-var 競爭。
   - **位置**：rust/openclaw_engine/src/live_authorization.rs:728 + rust/openclaw_engine/src/live_auth_watcher_tests.rs:210
   - **修法建議**：可選 (a) 提升至 crate-level 共用 lock (`pub(crate) static ENV_LOCK: Mutex<()>...`) 在新 mod `test_env_lock`；(b) 引入 `serial_test` crate `#[serial]` macro；(c) Accept（24/24 PASS 表示實測未觸）。
   - **嚴重性決定**：不退回 E1，標記為 Phase 1 land 後可選 follow-up；E1 IMPL report 已 24/24 PASS。

2. **MEDIUM-OPS · restart_all seed cp 非 atomic**：`cp "$OPENCLAW_IPC_SECRET_FILE" "$OPENCLAW_LIVE_AUTH_SIGNING_KEY_FILE"` (restart_all.sh:159) 若被 SIGTERM 中斷可能 partial-written；engine startup 讀到部分文件 → empty/garbage key → fallback to ipc_secret (Phase 1) or BadSignature (Phase 2)。
   - **位置**：helper_scripts/restart_all.sh:159
   - **修法建議**：`cp ipc tmp && mv tmp final` atomic rename。
   - **嚴重性決定**：首 boot 路徑（[ ! -f ] guard 確保僅一次）；中斷概率極低；fail-closed 路徑安全。defer，不阻 Phase 1 land。

**3 LOW**（observations / defer）：

3. LOW · `compare_exchange(AcqRel, Relaxed)` 對單 atomic 略 over-engineered（Relaxed/Relaxed 即可）。非 bug。
4. LOW · Phase 2 main.rs panic block 預期位置 (spec §9.5 標 399-407) 實際在 397-411；line offset 微差但 PA `live_bindings.is_some() && secret_env::var_or_file("OPENCLAW_IPC_SECRET").is_none()` block 結構正確。E1 IMPL TODO 註記在 read_live_auth_signing_key 內 + Phase 2 移除 fallback 時同步加 panic block，路徑 clear。
5. LOW · fresh_start.sh 不 seed + 不 FAIL if file missing；engine boot 走 Phase 1 fallback；defer 到 P1-OPS-2-RUNBOOK 處理 urandom 生成步驟。

# §5. E2 Checklist Run

## E2 8 條 reviewer checklist

| Item | 結果 |
|---|---|
| 改動範圍與 PA 方案一致 | ✅ 3 track 完全對齊 spec §4.1-§4.3；no scope creep |
| 沒有 `except:pass` 或靜默吞異常 | ✅ Python helper 用 `(get_secret_value(...) or "")` 顯式 fallthrough；Rust `.ok_or(AuthError::...)` |
| 日誌使用 %s 格式 | ✅ live_trust_routes.py:88 用 `"event=%s", "ops2_secret_split_phase1_fallback"`；非 f-string |
| 新 API 端點 `_require_operator_role()` | N/A · 本 IMPL 無新 endpoint |
| `except HTTPException: raise` 在 `except Exception` 前 | N/A · 本 IMPL 無新 try/except |
| `detail=str(e)` 已改 `"Internal server error"` | N/A · 本 IMPL 無新 HTTPException |
| asyncio 路由無 blocking threading.Lock | ✅ live_trust_routes 全部 sync `def`；FastAPI threadpool；threading.Lock 正確 |
| 沒有私有屬性穿透 `._xxx` | ✅ test 文件用 `live_trust_routes._fallback_warn_state` / `._FALLBACK_WARN_INTERVAL_SECS` 是 test fixture 必要的 internal hook，acceptable for unit test scope |

## OpenClaw 9 條 §3 checklist

| Item | 結果 |
|---|---|
| 跨平台合規 | ✅ 0 hit `/home/ncyu` / `/Users/ncyu` |
| 注釋規範（中文為主） | ✅ 新 patch 中文 rationale 為主；少量 English 留技術 identifier (env var name / HMAC / SHA256 / canonical payload) |
| Rust unsafe 零容忍 / unwrap 限不可恢復 | ✅ 0 unsafe；unwrap 僅在 test (`tempfile::tempdir().expect("tempdir")` / `Mutex.lock().unwrap_or_else(into_inner)`) 屬不可恢復 test 路徑 |
| 跨語言 IPC schema 一致 + serde 型別安全 | ✅ cross-lang HMAC pinned hex 三端 byte-identical verify；canonical_payload format pipe-sep 對齊 |
| Migration Guard A/B/C | N/A · 本 IMPL 無 SQL migration |
| healthcheck 配對 | N/A · 14d soak D+14 在 E1 IMPL report §5.4 列觀察點（fallback WARN 計數 / engine PID / file integrity / trust-status reason / operator renew ≥1）；不屬被動等待 TODO |
| Singleton 登記 | ✅ `LAST_FALLBACK_WARN_TS` static AtomicU64 + Python `_fallback_warn_state` module-level dict — 內部 rate-limit 狀態屬於 implementation detail；scope 限於文件內；無 cross-module shared mutable singleton |
| 文件大小 800/2000 行 | ⚠️ live_authorization.rs 從 ~711 行漲到 1082 行（+371）；test 區佔多數；prod code 約 +30 行；可接受但靠近 800 行警戒 |
| Bybit API 改動先查字典手冊 | N/A · 本 IMPL 無 Bybit endpoint |

# §6. 對抗反問

| Q | E2 自證 |
|---|---|
| 「測試通過 mock 了什麼？真實邏輯有跑嗎？」 | Python 8 test 用 `monkeypatch.setenv` 真實設 env var 跑 `_read_live_auth_signing_key`；Rust 5 test 用 `std::env::set_var` 真實設 + tempfile 真實寫 authorization.json 跑 `load_and_verify`；非 mock IPC server。 |
| 「沒影響其他模塊？grep 結果？」 | `grep -rn "OPENCLAW_IPC_SECRET" rust/openclaw_engine/src` 命中只在 live_authorization.rs (簽名路徑保留兼容 docstring) + ipc_server/connection.rs (IPC handshake 保留) + main.rs (FIX-10 panic 保留) — 4 個 client-domain Python/Rust 完全未動。 |
| 「race 不可能？怎證明？」 | Rust `AtomicU64::compare_exchange(last, now_secs, AcqRel, Relaxed)` 多 caller 並發只一個贏 CAS；Python `threading.Lock` 在 sync route + uvicorn threadpool 序列化。empirical 100 calls/ms → 1 emit (E1 IMPL §3 列數據)。 |
| 「edge case 已處理？」 | empty env: `secret_env::var_or_file` line 14-16 + 27-30 filter；empty file: line 27-30 trim_end_matches + is_empty check；permission denied: Python `try ... except OSError` 包含 `PermissionError`；NTP clock rewind: `saturating_sub` 防溢出；missing file: `read_text` OSError caught。 |
| 「規格一致？PA 文件第幾行對應哪行 code？」 | spec §4.1.1 line 200 (AuthError variant) → rust line 119-130；spec §4.1.1 line 202 (`load_and_verify` 改 helper) → rust line 423；spec §4.2.1 line 230 (`_write_signed_live_authorization` helper) → python line 272；spec §4.3.1 line 246 (restart_all seed) → restart_all.sh:157-167；spec §4.3.1 line 248 (spawn env) → restart_all.sh:543 + 712。 |

# §7. 結論

**verdict = APPROVE-CONDITIONAL → PASS to E4 regression + CC review**

理由：
- 0 BLOCKER + 0 HIGH。
- 5 PA hidden risk mitigation 全 verify（含 4 negative-checklist 檔 0 hit）。
- cross-lang HMAC pinned hex 三端 byte-identical（E2 獨立 stdlib 重算對齊）。
- E2 8 條 + OpenClaw 9 條 checklist 全跑；改動範圍與 spec 100% 對齊；無 scope creep。
- 2 MEDIUM 屬 CI flakiness + bash atomicity 提升空間，非 prod risk；E1 IMPL report 24/24 + 18/18 + bash -n 三端 GREEN 為實測背書。
- 3 LOW 屬 over-engineered ordering / line offset 微差 / fresh_start runbook follow-up；defer 不阻 Phase 1 land。

**Conditional (建議 E4 + CC + 部署期觀察)**：
1. E4 regression 必跑 Linux integration A/B/C（spec §4.4）— Mac mock pytest 不足驗證 restart_all seed `cp` 真實 SECRETS_ROOT 路徑展開。
2. CC review 必查 §5 5-hard-gate impact (gate #4 + #5 強化非弱化)；16-root-principles §1 (signal write entry) + §3 (lease) + §4 (risk bypass) + §6 (fail-closed) 對齊。
3. Deploy 後 D+0..D+14 soak 觀察 fallback WARN log 累計 = 0；若 > 0 表示 restart_all 未正確 inject env，CUT Phase 2。
4. 可選 follow-up：MEDIUM-1 (test env lock unification) + MEDIUM-2 (cp atomic mv) 列入 hygiene backlog，非 Phase 1 land 阻塞。

**退回 E1 修復清單**：無強制項。可選 follow-up（不阻 Phase 1）：
- (1) Rust test ENV_TEST_LOCK + ENV_GUARD 合併至 crate-level shared mutex
- (2) restart_all.sh:159 `cp` 改 `cp ... tmp && mv tmp final` atomic

**E2 sign-off ready** — 等 PM dispatch E4 regression + CC review。

# §8. Cross-References

- E1 IMPL report: `docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-27--ops_2_secret_split_impl.md`
- PA spec: `docs/execution_plan/specs/2026-05-26--p1-ops-2-secret-split-design.md`
- Rust live_authorization: `rust/openclaw_engine/src/live_authorization.rs:1-1082`
- Python live_trust_routes: `program_code/exchange_connectors/bybit_connector/control_api_v1/app/live_trust_routes.py`
- Python test: `program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_live_trust_routes_secret_split.py`
- Bash scripts: `helper_scripts/restart_all.sh` / `fresh_start.sh` / `clean_restart.sh`
- Main.rs panic block context: `rust/openclaw_engine/src/main.rs:397-411`
- Skill applied: pr-adversarial-review + bilingual-comment-style

**END OF E2 REVIEW**
