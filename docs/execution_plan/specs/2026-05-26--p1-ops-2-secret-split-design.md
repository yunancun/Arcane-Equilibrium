# P1-OPS-2-SECRET-SPLIT — Design Spec

| 欄位 | 值 |
|---|---|
| **Spec ID** | `P1-OPS-2-SECRET-SPLIT` |
| **作者** | PA |
| **日期** | 2026-05-26 |
| **狀態** | DESIGN — pending CC review sign-off → E1 IMPL |
| **上游缺陷** | `E3-CRIT-1`（`docs/CCAgentWorkSpace/E3/workspace/reports/2026-05-26--p0-ops-2-credential-rotation-audit.md` §C-1）|
| **阻塞下游** | `P1-OPS-2-RUNBOOK`（`docs/runbooks/credential_rotation.md` 草擬）/ Sprint 4 first Live W18-21 |
| **HEAD baseline** | `4bbd4a17` |
| **Scope guard** | 僅 split `OPENCLAW_IPC_SECRET`；**不**碰 POSTGRES_PASSWORD / OPENCLAW_API_TOKEN / Bybit api_key（E3 P2 後續，本 spec 越界即違規）|

---

## 1. 問題陳述

### 1.1 現況（dual-purpose key）

`OPENCLAW_IPC_SECRET` 在 OpenClaw runtime 同時擔當兩個語意完全不同的角色：

| 角色 | 消費者 | 信任邊界 | 失效後果 |
|---|---|---|---|
| **(a) IPC HMAC** | Rust `ipc_server::connection` `__auth` 握手；Python `optuna_optimizer` / `replay_earn_preflight` / `edge_p2_flip_dry_run` 客戶端 | 同主機 Unix socket 端到端認證 | IPC reconnect required；不影響 Live pipeline 既有狀態 |
| **(b) Live-auth signing** | Rust `live_authorization::load_and_verify` 簽 + 驗 `authorization.json`；Python `live_trust_routes._write_signed_live_authorization` / re-verify endpoint | Live 啟動 5-gate 中的 gate #5（signed authorization）的密碼學根 | 所有現存 `authorization.json` 同 atomic 失效 → Live pipeline 立即停 `AuthError::BadSignature` |

### 1.2 為什麼是 CRITICAL 而非 HIGH

**Design defect, not operational gap**：

1. **Rotation 邏輯結構性 fragile**：rotate IPC HMAC 必同時 invalidate 所有 in-flight signed authorization — 沒有「只 rotate one role」的操作路徑。
2. **Blast radius 混淆**：IPC HMAC leak ≠ live-auth signing key leak（前者僅授權同主機 IPC 客戶端；後者授權偽造 tier/TTL/operator_id）。當前兩者共享一個 32-byte secret material，operator 無法基於不同 blast radius 設不同 rotation cadence。
3. **無法寫合規 runbook**：撰寫 `docs/runbooks/credential_rotation.md`（OPS-2 deliverable）的前提是該 key 有 well-defined rotation procedure；dual-purpose 下不存在。

### 1.3 攻擊面（per E3 §C-1）

- 同 uid env-var inspection / process memory dump / launchd plist leak（SC-005 / SC-006）→ 攻擊者拿到 `OPENCLAW_IPC_SECRET`。
- 攻擊者**同時**可：(a) 簽偽 IPC commands 操作 Rust engine；(b) 寫入偽 `authorization.json` with `tier="T3_TRUSTED"` / `expires_at_ms=now+10y` / `env_allowed=["mainnet"]` 並通過 Rust `verify_in_memory`。
- Rotation 反應壓力：必須 atomic rotate → 所有現存 signed authorization 一次失效 → Live pipeline `AuthError::BadSignature` 直至 operator 走 `/auth/renew`。

---

## 2. 目標架構（target state）

### 2.1 兩 key 完全獨立

| 屬性 | `OPENCLAW_IPC_SECRET`（保留語意 a）| `OPENCLAW_LIVE_AUTH_SIGNING_KEY`（新增語意 b）|
|---|---|---|
| 用途 | IPC handshake HMAC only | `authorization.json` HMAC sign + verify only |
| Env var name | `OPENCLAW_IPC_SECRET` | `OPENCLAW_LIVE_AUTH_SIGNING_KEY` |
| File companion env | `OPENCLAW_IPC_SECRET_FILE`（已存在）| `OPENCLAW_LIVE_AUTH_SIGNING_KEY_FILE`（新增）|
| 預設 file path | `$SECRETS_ROOT/environment_files/ipc_secret.txt` | `$SECRETS_ROOT/environment_files/live_auth_signing_key.txt` |
| Read helper | `secret_env::var_or_file("OPENCLAW_IPC_SECRET")` | `secret_env::var_or_file("OPENCLAW_LIVE_AUTH_SIGNING_KEY")` |
| Material | 32-byte high-entropy（不變）| 32-byte high-entropy（不變，初始期允許等於 IPC 為 migration backward-compat — 見 §3.1）|
| Rotation cadence | 180d（per E3 §D — IPC blast radius 中等）| 90d（per E3 §D — auth signing blast radius 高）|
| Alert lead | 165d | 75d |
| Audit row action | `ipc_secret_rotation` | `live_auth_signing_key_rotation` |
| 失效 fail-mode | `IpcAuthFailed`（已存在）| `AuthError::LiveAuthSigningKeyMissing`（新）/ `AuthError::BadSignature`（已存在）|

### 2.2 設計不變量

1. **Migration safety**：Phase 1 期間（兩 env 都 set + 值相同）系統行為與當前 100% 等價（hash 結果同、watcher poll 同、IPC handshake 同），確保零 runtime regression。
2. **Fail-closed 強化**：移除 fallback 後 Live + missing `OPENCLAW_LIVE_AUTH_SIGNING_KEY` → engine startup panic（mirror 既有 `main.rs:399-407` IPC missing pattern）。
3. **Rotation 獨立**：rotate 任一 key 不影響另一 key signed artefact；rotate IPC HMAC → 既存 `authorization.json` 仍 valid（簽名 key material 未動）。
4. **Audit trail**：rotate 任一 key 寫 `learning.governance_audit_log` 一行（actor / action / old_fingerprint_first8 / new_fingerprint_first8 / ts）— 細節屬 E3-MED-1 follow-up endpoint，本 spec 留 hook，不實 endpoint。
5. **5-hard-gate impact**：gate #4 secret slot **新增一個 file**（並列存在，不破現有）；gate #5 authorization HMAC **signing key 換 material**（migration 含 re-sign 步驟，下文 §3）。

### 2.3 OPENCLAW_IPC_SECRET 保留現況（**不**遷移）

下列 5 處 call sites 屬語意 (a) IPC HMAC，**保持讀 `OPENCLAW_IPC_SECRET`**：

| 檔案 | 行 | 用途 |
|---|---|---|
| `rust/openclaw_engine/src/main.rs` | 402 | Live + missing IPC secret → panic（IPC 強制）|
| `rust/openclaw_engine/src/ipc_server/connection.rs` | 122 | IPC `__auth` 握手 HMAC verify |
| `program_code/ml_training/optuna_optimizer.py` | 297-340 | Optuna IPC client handshake |
| `helper_scripts/canary/replay_earn_preflight.py` | 480-497 | Stage 0R preflight JSON 簽名（**不**走 Live gate；獨立 HMAC 域）|
| `helper_scripts/canary/edge_p2_flip_dry_run.py` | 182-438 | Edge P2 flip dry-run IPC handshake |

> **PA 標註**：`replay_earn_preflight.py` 表面看像 Live signing，實則 Stage 0R 的 internal manifest 簽名（用於 cron-user vs operator-user 防偽），與 `authorization.json` HMAC 完全不同的信任域。E1 IMPL **不要**把它一起遷移。

### 2.4 OPENCLAW_IPC_SECRET 遷移範圍（**遷移**）

下列 3 處 call sites 屬語意 (b) live-auth signing，**改讀 `OPENCLAW_LIVE_AUTH_SIGNING_KEY`**：

| 檔案 | 行 | 用途 | 變更類型 |
|---|---|---|---|
| `rust/openclaw_engine/src/live_authorization.rs` | 360 | `load_and_verify` 讀 ipc_secret | env var rename + 加 fallback（Phase 1）|
| `program_code/exchange_connectors/.../live_trust_routes.py` | 221 | `_write_signed_live_authorization` 讀 ipc_secret | env var rename + 加 fallback |
| `program_code/exchange_connectors/.../live_trust_routes.py` | 468 | re-verify endpoint 讀 ipc_secret | env var rename + 加 fallback |

`live_authorization.rs` `AuthError::IpcSecretMissing` rename → `AuthError::LiveAuthSigningKeyMissing`（保留 `auth_error_kind` 字串為 `live_auth_signing_key_missing` — alert rule 需同步更新，列入 E1 派發 packet）。

---

## 3. Migration phase 設計

### 3.1 Phase 1 — Backward-compat fallback（land + soak）

**Timeline 大綱**：

| 階段 | 內容 | 條件 |
|---|---|---|
| D+0 | E1 IMPL land + restart_all 寫 `live_auth_signing_key.txt`（material = ipc_secret.txt 同值）| restart_all dry-run pass |
| D+0..D+14 | 14d soak — Live pipeline 持續運行；watcher 每 5s `load_and_verify` 用新 env；若 fallback 觸發必 WARN log + audit row | 0 WARN log（兩 env 都 set 應永遠走 primary path）|
| D+14 | Phase 2 PR ready — 移除 fallback | 14d soak WARN log 計數 = 0 |

**Rust `live_authorization.rs:360` Phase 1 行為**：

```
fn read_live_auth_signing_key() -> Option<String> {
    if let Some(v) = secret_env::var_or_file("OPENCLAW_LIVE_AUTH_SIGNING_KEY") {
        return Some(v);
    }
    // Phase 1 fallback：未 set 新 env 時讀舊 env + WARN（一次性 boot log + 每次 verify 失敗不重發避免 log flood）
    if let Some(v) = secret_env::var_or_file("OPENCLAW_IPC_SECRET") {
        warn!(
            target: "live_authorization",
            "MIGRATION-FALLBACK: OPENCLAW_LIVE_AUTH_SIGNING_KEY unset; falling back to OPENCLAW_IPC_SECRET. \
             Set OPENCLAW_LIVE_AUTH_SIGNING_KEY before Phase 2 cutover."
        );
        return Some(v);
    }
    None
}
```

**Python `live_trust_routes.py:221` Phase 1 行為**：mirror — `get_secret_value("OPENCLAW_LIVE_AUTH_SIGNING_KEY")` → fallback → `get_secret_value("OPENCLAW_IPC_SECRET")` → WARN log。

**restart_all.sh 改動**（D+0 同 PR）：

```
# 新增 env var export（line ~72 區）
OPENCLAW_LIVE_AUTH_SIGNING_KEY_FILE="$SECRETS_ROOT/environment_files/live_auth_signing_key.txt"

# prepare_runtime_secret_files 加：D+0 首次 boot 自動 seed
# 若 live_auth_signing_key.txt 不存在 → 複製 ipc_secret.txt 同 material
if [ ! -f "$OPENCLAW_LIVE_AUTH_SIGNING_KEY_FILE" ] && [ -f "$OPENCLAW_IPC_SECRET_FILE" ]; then
    cp "$OPENCLAW_IPC_SECRET_FILE" "$OPENCLAW_LIVE_AUTH_SIGNING_KEY_FILE"
    chmod 600 "$OPENCLAW_LIVE_AUTH_SIGNING_KEY_FILE"
    echo ">>> SECRET-SPLIT phase 1: seeded live_auth_signing_key.txt from ipc_secret.txt (same material; rotate independently per OPS-2 runbook)"
fi
if [ -f "$OPENCLAW_LIVE_AUTH_SIGNING_KEY_FILE" ]; then
    chmod 600 "$OPENCLAW_LIVE_AUTH_SIGNING_KEY_FILE" 2>/dev/null || true
fi

# spawn 時新增 env var 注入（line ~523 + 691 兩處 spawn point）
OPENCLAW_LIVE_AUTH_SIGNING_KEY_FILE="$OPENCLAW_LIVE_AUTH_SIGNING_KEY_FILE" \
  ... existing spawn cmd ...
```

**為何 Phase 1 把兩 key material 設成同值**：避免 D+0 cutover 時所有現存 `authorization.json` 立即失效（sig 重算與舊值相等）。等 D+14 後 operator 走 `/auth/renew` 自然產生新 sig，配 §4 第一次 90d cadence rotation 時把 material 改成不同值。

### 3.2 Phase 2 — 移除 fallback（fail-closed 強化）

**Timeline 大綱**：

| 階段 | 內容 | 條件 |
|---|---|---|
| D+14 | Phase 2 PR review + merge | Phase 1 14d soak 0 WARN log，restart_all 已 seed 新 file |
| D+14 IMPL | Rust：`AuthError::LiveAuthSigningKeyMissing` 新變體取代 `IpcSecretMissing`（後者降為 IPC-only 語意）；Python：去 fallback；main.rs `panic!` 改 require **兩** secret if Live | E1 撰寫 + E2 review |
| D+14 boot | restart_all：若 Live + missing `OPENCLAW_LIVE_AUTH_SIGNING_KEY` → engine startup panic（mirror 既有 IPC missing pattern）| BB sign-off (exchange-facing impact) |
| D+14+1 | 90d rotation cadence 計時開始（first rotation due D+104）| OPS-2 runbook §4 已 land |

**Rust `main.rs` Phase 2 panic check 新增**：

```rust
if live_bindings.is_some()
    && secret_env::var_or_file("OPENCLAW_LIVE_AUTH_SIGNING_KEY").is_none()
{
    panic!(
        "FATAL: Live pipeline detected but OPENCLAW_LIVE_AUTH_SIGNING_KEY is not set. \
         Live authorization signing requires its own key (split from OPENCLAW_IPC_SECRET per OPS-2). \
         Set OPENCLAW_LIVE_AUTH_SIGNING_KEY_FILE or OPENCLAW_LIVE_AUTH_SIGNING_KEY before starting with Live credentials. \
         / Live 管線偵測到但 OPENCLAW_LIVE_AUTH_SIGNING_KEY 未設置。"
    );
}
```

### 3.3 Rollback path

| 觸發 | 反應 |
|---|---|
| Phase 1 D+0..D+14 任何時候 Live pipeline 異常 + 懷疑與 split 相關 | 1. `git revert <split-commit>` → restart engine + API（fallback 路徑保證舊 `OPENCLAW_IPC_SECRET` 仍 valid for both）。2. 留 `live_auth_signing_key.txt` 在盤上不刪（無害）。 |
| Phase 2 D+14 後 panic 阻 boot | 1. operator 確認 `$SECRETS_ROOT/environment_files/live_auth_signing_key.txt` 存在 chmod 600 + 非空。2. 不存在 → `cp $SECRETS_ROOT/environment_files/ipc_secret.txt $SECRETS_ROOT/environment_files/live_auth_signing_key.txt; chmod 600 $_`。3. restart_all `--rebuild`。4. 如仍 panic → `git revert <phase2-commit>` 回 Phase 1 fallback 模式。 |
| Phase 2 後第一次 90d rotation 失敗（new material 寫盤但 watcher reject）| 1. `cp $SECRETS_ROOT/environment_files/live_auth_signing_key.txt.rotated.<UTC_TS> $SECRETS_ROOT/environment_files/live_auth_signing_key.txt`。2. operator `/api/v1/live/auth/renew`（用舊 key 重簽 authorization）。3. restart_all `--rebuild`。 |

---

## 4. Rust IPC + Python /auth/renew 接點 detail

### 4.1 Rust 接點（PA 設計，**E1 IMPL**）

#### 4.1.1 `rust/openclaw_engine/src/live_authorization.rs`

**改動點**：

| 位置 | Phase 1 | Phase 2 |
|---|---|---|
| `enum AuthError::IpcSecretMissing` (line ~110) | 保留；display 改 "OPENCLAW_LIVE_AUTH_SIGNING_KEY (with OPENCLAW_IPC_SECRET fallback) unset" | rename → `LiveAuthSigningKeyMissing`；display 純新 env name；`IpcSecretMissing` 變體刪除（call site 只剩 ipc_server/connection.rs） |
| `fn auth_error_kind` (line ~212) | "ipc_secret_missing" → "live_auth_signing_key_missing"（**break change for alert rules**）| 同 |
| `fn load_and_verify` line 360 | 新 helper `fn read_live_auth_signing_key()`（見 §3.1）取代 `secret_env::var_or_file("OPENCLAW_IPC_SECRET")` | 同 helper 但去 fallback：純讀 `OPENCLAW_LIVE_AUTH_SIGNING_KEY` |
| `fn verify_in_memory` 參數 `ipc_secret: &str` | rename → `live_auth_signing_key: &str`；call site `compute_signature` 參數同 rename | 同 |
| Test `TEST_SECRET` const | 保留 + 新增 `TEST_LIVE_AUTH_KEY` 對應 | unit test `mismatched_live_auth_key → BadSignature` 新增（per E3 verification req）|

#### 4.1.2 `rust/openclaw_engine/src/main.rs`

**改動點**：

| 位置 | Phase 1 | Phase 2 |
|---|---|---|
| line 402 panic check | 保留（IPC HMAC 強制不變）| 保留 + **新增**另一個 panic block check `OPENCLAW_LIVE_AUTH_SIGNING_KEY`（見 §3.2）|

#### 4.1.3 `rust/openclaw_engine/src/live_auth_watcher_tests.rs`

**改動點**：line 195 `set_var("OPENCLAW_IPC_SECRET", TEST_SECRET)` → 同 set `OPENCLAW_LIVE_AUTH_SIGNING_KEY`（Phase 1 兩個都 set；Phase 2 只 set live key）。對應 test teardown line 199。

#### 4.1.4 `rust/openclaw_engine/src/ipc_server/connection.rs`

**改動點**：**0**。IPC handshake 邏輯不變（語意 a 保留 `OPENCLAW_IPC_SECRET`）。

### 4.2 Python 接點（PA 設計，**E1 IMPL**）

#### 4.2.1 `program_code/exchange_connectors/bybit_connector/control_api_v1/app/live_trust_routes.py`

**改動點**：

| 位置 | Phase 1 | Phase 2 |
|---|---|---|
| line 221 `_write_signed_live_authorization` | 新 helper `_read_live_auth_signing_key()` 讀 `OPENCLAW_LIVE_AUTH_SIGNING_KEY` fallback `OPENCLAW_IPC_SECRET` + WARN log | 純讀 `OPENCLAW_LIVE_AUTH_SIGNING_KEY`；missing → raise RuntimeError with renamed message |
| line 468 re-verify endpoint | 同 helper | 同 |
| Error message bilingual block | "OPENCLAW_IPC_SECRET is not set ..." → "OPENCLAW_LIVE_AUTH_SIGNING_KEY is not set ..." | 同 |

#### 4.2.2 Python 客戶端（**不**改）

`optuna_optimizer.py` / `replay_earn_preflight.py` / `edge_p2_flip_dry_run.py` 屬語意 (a)，**保持讀 `OPENCLAW_IPC_SECRET`**。E1 IMPL 不誤動。

### 4.3 Bash 接點（PA 設計，**E1 IMPL**）

#### 4.3.1 `helper_scripts/restart_all.sh`

**改動點**（已詳列 §3.1）：

| line | Phase 1 改動 |
|---|---|
| ~72 | 新增 `OPENCLAW_LIVE_AUTH_SIGNING_KEY_FILE` 變數定義 |
| 131-146 `prepare_runtime_secret_files` | 新增 seed-from-ipc 邏輯 + chmod 600 |
| ~523, ~691 spawn cmd | 新增 `OPENCLAW_LIVE_AUTH_SIGNING_KEY_FILE` env 注入 |

#### 4.3.2 `helper_scripts/fresh_start.sh` / `helper_scripts/clean_restart.sh`

**改動點**：mirror restart_all.sh 第三項（spawn cmd env 注入）。Seed 不必做（fresh start 不應有舊 secret）— operator 須先生成新 key 才能 spawn Live。

### 4.4 Test fixture / unit test 改動

**Rust**：

| 測試 | 新增 / 改動 |
|---|---|
| `live_authorization.rs::tests::mismatched_live_auth_key_produces_bad_signature` | **新增** — `compute_signature(auth, KEY_A)` + `verify_in_memory(auth, env, now, KEY_B)` → `BadSignature` |
| `live_authorization.rs::tests::live_auth_signing_key_missing_returns_specific_variant` | **新增** Phase 2 — `unset OPENCLAW_LIVE_AUTH_SIGNING_KEY` + `load_and_verify` → `LiveAuthSigningKeyMissing` |
| `live_authorization.rs::tests::wrong_secret_produces_bad_signature` (line 528) | rename TEST_SECRET → TEST_LIVE_AUTH_KEY |
| `live_auth_watcher_tests.rs` | 兩 env 都 set fixture |

**Python**：

| 測試 | 新增 / 改動 |
|---|---|
| `tests/control_api_v1/test_live_trust_routes.py::test_sign_authorization_uses_live_auth_signing_key` | **新增** — monkeypatch `OPENCLAW_LIVE_AUTH_SIGNING_KEY="key-a"` + `OPENCLAW_IPC_SECRET="key-b"` + 簽授權 → sig must be HMAC(key-a, payload) |
| Phase 1 fallback test | **新增** — unset new env + set old → WARN log triggered + sig 用 old key 計算 |

**Integration**：

| 測試 | 條件 | 預期 |
|---|---|---|
| **Integration A** rotate IPC HMAC keep live-auth signing | Phase 2 後；改 ipc_secret.txt material 不改 live_auth_signing_key.txt；restart engine | Live pipeline 保持 running（watcher 不重 sign）；IPC 客戶端必須帶新 secret 重連（per existing IPC behavior） |
| **Integration B** rotate live-auth signing keep IPC HMAC | Phase 2 後；改 live_auth_signing_key.txt material 不改 ipc_secret.txt；不 restart | Watcher 下一輪 `load_and_verify` → `BadSignature` → live slot teardown ≤5s；operator 須 `/auth/renew` 用新 key 重簽 | 
| **Integration C** Adversarial leak ipc_secret only | Phase 2 後；attacker 拿 `OPENCLAW_IPC_SECRET` 不拿 `OPENCLAW_LIVE_AUTH_SIGNING_KEY` | 偽造 `authorization.json` HMAC(ipc_secret, payload) → watcher 用 live_auth key verify → `BadSignature` reject |

---

## 5. 5-Hard-Gate Impact Assessment

per `CLAUDE.md §四 Hard Boundaries`：

| Gate | 當前 | Split 後 | Impact verdict |
|---|---|---|---|
| #1 Python `live_reserved` | 不變 | 不變 | 無 |
| #2 Python Operator role auth | 不變 | 不變 | 無 |
| #3 `OPENCLAW_ALLOW_MAINNET=1` | 不變 | 不變 | 無 |
| **#4 Valid secret slot** | 1 file `ipc_secret.txt` is the secret-material backing for **both** IPC + auth sign | +1 file `live_auth_signing_key.txt`（並列存在）；secret slot 仍嚴 chmod 600 + restart_all 維護；無 file 刪除 / 路徑變動 | **不破現有 + 強化（多一個獨立 file 邊界）** |
| **#5 Signed unexpired `authorization.json` matching env** | Sign + verify 用 `OPENCLAW_IPC_SECRET` material | Sign + verify 改用 `OPENCLAW_LIVE_AUTH_SIGNING_KEY` material；Phase 1 同值 backward-compat；Phase 2 獨立 | **強化** — signing key 與 IPC key 分離，blast radius 隔離，cadence 獨立；migration 14d soak 確保 0 regression |

**整體 verdict**：**僅 gate #4 + #5 受影響；兩者皆強化（無弱化）**。CC review 重點 = §3 migration phase 設計 + §4.1 Rust `AuthError` enum 變更 + restart_all.sh seed 邏輯（首次 boot 自動同值 seed 是 acceptable risk because 等價於現狀）。

**Backward compat 處理**：

- Phase 1 期間 old `authorization.json`（用 ipc_secret 簽）100% 仍 valid（fallback path）。
- Phase 2 cutover 條件之一 = Phase 1 14d 期間 operator 至少走過一次 `/auth/renew`（任何例行 TTL renew 即觸發）→ 新 sig 用 new material 簽（即使 material 同值也是新 sig 因為 timestamp 變）。
- 若 14d 內 operator 從未 renew（理論上 T0 hrs TTL 已強迫 renew，T3 24h+ 也會），Phase 2 PR 前須先 manually trigger `/auth/renew` re-sign 一次，否則 Phase 2 panic 之餘 watcher 仍可 verify 舊 file（同值 material）但 audit 痕跡不清。

---

## 6. Rotation cadence（per E3 §D）

| Key | Scheduled cadence | Alert lead | Force rotation | Emergency revoke | RTO target |
|---|---|---|---|---|---|
| `OPENCLAW_IPC_SECRET` | **180d** | 165d（15d lead）| 180d | `rm $OPENCLAW_IPC_SECRET_FILE + restart_all`（拆 IPC; Live slot 不影響）| ≤15min |
| `OPENCLAW_LIVE_AUTH_SIGNING_KEY` | **90d** | 75d（15d lead）| 90d | `rm $OPENCLAW_LIVE_AUTH_SIGNING_KEY_FILE` → watcher BadSignature ≤5s teardown → operator new key + `/auth/renew` | ≤15min |

**為何 cadence 不同**：

- IPC HMAC blast radius = 同主機 IPC 客戶端可被偽造 → 攻擊者已在主機內（高 prerequisite）→ 180d acceptable。
- Live-auth signing blast radius = 攻擊者可寫偽 `authorization.json` 直接啟 Live with arbitrary tier/TTL → 90d 嚴格。

**Drift monitoring**：屬 E3-LOW-1 follow-up（P2-OPS-2-CRON-DRIFT），**不在本 spec scope**。本 spec 只記錄 cadence 數字，runbook（`P1-OPS-2-RUNBOOK`）負責寫 SQL 查詢與 cron schedule。

---

## 7. Test Plan 摘要

依 §4.4 詳列。最低 acceptance：

| 測試類型 | 數量 | 須通過條件 |
|---|---|---|
| Rust unit | 2 新增 + 1 rename | `cargo test --package openclaw_engine live_authorization` GREEN |
| Python unit | 2 新增 | `pytest program_code/.../test_live_trust_routes.py` GREEN |
| Integration A/B/C | 3 case | Linux runtime empirical run（**Mac mock pytest 不夠** per memory `feedback_v_migration_pg_dry_run`）|
| restart_all dry-run | 1 cycle | Phase 1 boot 後 `ls -la $SECRETS_ROOT/environment_files/live_auth_signing_key.txt` 存在 + chmod 600 + content == ipc_secret.txt（首次 boot）|
| Adversarial | Integration C | 偽 authorization.json HMAC(ipc_secret, payload) → engine reject `BadSignature` |

**禁略**：integration A/B/C **必跑** Linux runtime（不接受 Mac mock）。

---

## 8. E1 IMPL Dispatch Packet

### 8.1 File change scope

| 檔案 | LOC est | 變更類型 |
|---|---|---|
| `rust/openclaw_engine/src/live_authorization.rs` | ~30 lines added / 5 renamed | helper fn + error variant + tests |
| `rust/openclaw_engine/src/main.rs` | ~12 lines added (Phase 2) | 第二個 panic block |
| `rust/openclaw_engine/src/live_auth_watcher_tests.rs` | ~5 lines | test fixture env var |
| `program_code/exchange_connectors/bybit_connector/control_api_v1/app/live_trust_routes.py` | ~20 lines | helper fn + 2 call site rename + WARN log |
| `program_code/.../tests/test_live_trust_routes.py`（可能新檔案）| ~40 lines | 2 新 test |
| `helper_scripts/restart_all.sh` | ~12 lines | env var + seed + spawn injection |
| `helper_scripts/fresh_start.sh` | ~3 lines | spawn cmd env |
| `helper_scripts/clean_restart.sh` | ~3 lines | spawn cmd env |
| 總計 | ~125 LOC Rust+Python+Bash 變更 + ~40 LOC 新 test | — |

**檔案互不重疊性**：Rust 變更獨立於 Python 變更獨立於 Bash 變更 → E1 可拆 3 並行 sub-agent（per memory `feedback_subagent_first`）。

### 8.2 並行派發建議

| Sub-agent | 檔案 | 阻塞關係 |
|---|---|---|
| E1-A (Rust) | `live_authorization.rs` + `main.rs` + `live_auth_watcher_tests.rs` | 無；可獨立 cargo test pass |
| E1-B (Python) | `live_trust_routes.py` + 新 test | 無；可獨立 pytest pass |
| E1-C (Bash) | `restart_all.sh` + `fresh_start.sh` + `clean_restart.sh` | 無；可獨立 shellcheck pass |

3 sub-agent 並行 → 合 PR → E2 review → E4 regression（必含 Linux integration A/B/C）→ CC review → PM sign-off。

### 8.3 預估工時

| 階段 | 估時 |
|---|---|
| Phase 1 IMPL（3 並行 sub-agent）| 3-4 hours |
| Unit test + Phase 1 local pytest/cargo test | 1-2 hours |
| Linux integration A/B/C 跑 | 2-3 hours |
| E2 review + CC review（5-gate 必查）| 2-3 hours |
| Phase 1 land + 14d soak（watch only）| 14 days clock |
| Phase 2 IMPL（去 fallback + 第二 panic block）| 1-2 hours |
| Phase 2 land + 90d cadence 計時開始 | 1 day clock |
| **Total active work** | **~10-14 hours active + 14d soak gate** |

### 8.4 CC review trigger 條件

per `CLAUDE.md §四 Hard Boundaries` + memory `feedback_impl_done_adversarial_review`，本 spec 屬高風險（touches gate #4 + #5）→ **強制 CC review**，trigger 條件：

1. E1 IMPL DONE（3 sub-agent 合 PR 完成）
2. E4 regression GREEN（不接受 E4 取代 CC，per `feedback_impl_done_adversarial_review`）
3. CC 須親自核：
   - **16 root principles** §1 / §3 / §4 / §6（單一寫入口未破 / Lease 機制未破 / 風控 gate 未旁路 / fail-closed 強化非弱化）
   - **9 安全不變量** I2（signed authorization）+ I5（authorization 過期/失效 → cancel_token shutdown）
   - **5 hard gates** #4 + #5 binding evidence
   - **跨平台**：`$SECRETS_ROOT` 路徑無 user-home hardcode（per memory `feedback_cross_platform`）

CC verdict 模板（A/B/B-/C/F）參 skill `16-root-principles-checklist`。

### 8.5 E2 重點審查 3 點

1. **Rust `AuthError` enum 變更**：rename `IpcSecretMissing` → `LiveAuthSigningKeyMissing` 影響 alert rule 字串 `auth_error_kind`。E2 須 grep alert config / dashboard / Prometheus 規則確認 0 caller 用舊字串。
2. **restart_all.sh seed 邏輯 idempotency**：`cp ipc_secret.txt → live_auth_signing_key.txt` 條件 `[ ! -f live_auth_signing_key.txt ]` 必嚴 — 若已存在新 file 被 ipc 同值覆蓋會破壞已 rotated 的 live-auth key。E2 須測重 boot 不覆蓋。
3. **Python `_write_signed_live_authorization` Phase 1 fallback WARN 不 flood**：WARN log 一次 / boot（或一次 / 1h）即可；不能每次 sign call 噴一行（live_auth 5s watcher poll → 7200 logs/day）。E2 須驗 log rate ≤1/h。

### 8.6 安全反 pattern 守護（PA 守衛）

| 反 pattern | 守護 |
|---|---|
| Phase 1 fallback 永久化 | Phase 2 必排 D+14 land；TODO active 條目須 explicit due date |
| Seed 同值期間 audit log 不分 | 首次 boot WARN log 含 "phase 1 seeded same material" 標記；rotation runbook 須在第一次 rotation 把 material 改成獨立值並 audit row 記 |
| 把 IPC 客戶端腳本誤遷移 | §2.3 列保留清單；E1 IMPL packet 含 negative checklist「不可改下列 5 檔」|

---

## 9. Hidden risk identification（PA 補充，E3 audit 未提）

PA 在閱讀 call site 後識別下列 E3 report 未明列的 hidden risk：

### 9.1 IPC 客戶端腳本誤遷移風險（**HIGH**）

E3 report §C-1 只列 3 call sites（live_authorization.rs / live_trust_routes.py / main.rs），但 `OPENCLAW_IPC_SECRET` 實際有 **8 call sites**（grep 確認）。其中 5 個是 IPC 客戶端域（`optuna_optimizer.py` / `replay_earn_preflight.py` / `edge_p2_flip_dry_run.py` / `connection.rs` / `main.rs:402`）— 若 E1 不嚴守 §2.3/§2.4 邊界、誤把 IPC 客戶端腳本也改成讀新 env，會破 IPC 客戶端 handshake（optuna training 直接 fail）。本 spec §8.6 已加 negative checklist 防範。

### 9.2 `replay_earn_preflight.py` 同名 false-positive 風險（**MEDIUM**）

該檔案內部 HMAC 簽名一個 cron 寫的 JSON manifest，**用同 `OPENCLAW_IPC_SECRET`** 但不走 live gate（Stage 0R 與 Live 完全獨立信任域）。表面看像 live auth，實則 internal cron-vs-operator-user 防偽。E1 看 import / grep 結果可能誤遷移。本 spec §2.3 已明列保留 + §8.6 negative checklist。

### 9.3 Cross-platform user-home assumption（**LOW**）

`$SECRETS_ROOT` 預設展開含 `$HOME/BybitOpenClaw/secrets/...`。新 file `live_auth_signing_key.txt` path 必走 `$SECRETS_ROOT/environment_files/` 同舊 file pattern；E1 IMPL 不可硬編碼 `/home/ncyu` 或 `/Users/ncyu`（per memory `feedback_cross_platform` + `CLAUDE.md §六 Runtime Reality`）。Mac Apple Silicon 部署 ready 不破。

### 9.4 Phase 1 seed 與 OPS-2 runbook §3 Initial Deployment 衝突風險（**LOW**）

OPS-2 runbook §3 (per replay_signing_key_rotation.md mirror) 要求 "Generate new key from urandom"。Phase 1 restart_all seed 邏輯 copy from ipc_secret.txt **不**走 urandom — 屬 backwards-compat shortcut。Runbook 起草時須在 §3 加 note：「初次部署 split 後第一次 90d rotation 必須 from urandom (per OPS-2)；seed-from-ipc 是 migration-only 行為」。本 spec 留 hook，runbook 撰寫責 PA + E1 在 `P1-OPS-2-RUNBOOK` 處理。

### 9.5 Watcher 與 Phase 2 panic boot ordering 風險（**LOW**）

Phase 2 後 `main.rs` panic check **必須**在 `LiveAuthWatcher` spawn 之前。當前 `main.rs:399-407` IPC panic check 在 line 399（pipeline detect 後但 IPC server spawn 前）。新 panic block 必須 mirror 同位置（在現有 IPC panic 之後立即），不能晚於 watcher spawn — 否則 watcher 起來再 panic 留 dangling tokio task。E1 IMPL 須在 PR description 明列 panic block 位置 line number。

### 9.6 alert rule 字串 break change（**LOW-MEDIUM**）

`auth_error_kind` 返回字串 `ipc_secret_missing` → `live_auth_signing_key_missing` 屬 break change。grep 結果（PA 確認）：

```
rust/openclaw_engine/src/live_authorization.rs:692 — unit test 字串 assert
```

**0 個 external alert config 引用該字串**（Prometheus / Grafana / journald grep 規則）— PA 已 grep `ipc_secret_missing` 全 repo 0 hit beyond test。risk 為 LOW-MEDIUM 因為 alert rule 可能存在 repo 外（operator 個人 Grafana dashboard），E1 IMPL packet 須提醒 operator 確認。

---

## 10. Out-of-scope（**禁** 在本 spec / IMPL 動）

per task constraint：

- POSTGRES_PASSWORD rotation / hot reload
- OPENCLAW_API_TOKEN rotation
- Bybit api_key / api_secret hot reload（E3-HIGH-1，獨立 P2 ticket `P2-OPS-2-HOTRELOAD`）
- AI provider keys（Anthropic / OpenAI / DeepSeek）
- `helper_scripts/cron/long_lived_secret_drift_check.sh`（E3-LOW-1，獨立 P2 `P2-OPS-2-CRON-DRIFT`）
- `POST /api/v1/security/ipc-secret/rotate` endpoint（E3-MED-1，獨立 P2 `P2-OPS-2-AUDIT-ENDPOINT`）
- `gitleaks` pre-commit hook（E3 §F，獨立 P2 `P2-OPS-2-GITLEAKS`）

任何越界改動 = scope creep，PA 直接 reject。

---

## 11. Sign-off Block

| 角色 | 狀態 | 簽核要點 |
|---|---|---|
| **PA**（本 spec 作者）| **DESIGN DONE** 2026-05-26 | §1-§10 完成；§9 hidden risk 5 條補 E3 盲區 |
| **CC** | **PENDING** | §5 5-gate impact + §8.4 CC trigger 條件；16-root-principles-checklist 全 16 條 + 9 invariant 過 |
| **E1** | **PENDING IMPL** | §8 dispatch packet；3 並行 sub-agent；§8.6 negative checklist 守 |
| **E2** | **PENDING REVIEW** | §8.5 3 重點審查項 |
| **E3** | **PENDING VERIFY** | E3-CRIT-1 close 條件 = §4.4 integration A/B/C GREEN + Phase 2 land |
| **BB** | **PENDING SIGNOFF** | 5-gate #4 + #5 touched → exchange-facing impact 須 BB 認 ≤15min RTO 達成 |
| **PM** | **PENDING APPROVE** | 全鏈完成後 land Phase 1 → 14d soak → Phase 2 land → close E3-CRIT-1 + unblock `P1-OPS-2-RUNBOOK` + Sprint 4 W18-21 |

---

## 12. Cross-References

- **E3 audit baseline**：`docs/CCAgentWorkSpace/E3/workspace/reports/2026-05-26--p0-ops-2-credential-rotation-audit.md` §C-1 / §D / §I
- **Rust signing path**：`rust/openclaw_engine/src/live_authorization.rs:360`
- **Python signing path**：`program_code/exchange_connectors/bybit_connector/control_api_v1/app/live_trust_routes.py:221` + `:468`
- **Rust panic path**：`rust/openclaw_engine/src/main.rs:399-407`
- **Bash secret prep**：`helper_scripts/restart_all.sh:131-146`
- **CLAUDE.md hard boundaries**：`srv/CLAUDE.md §四`
- **Runbook 樣板**：`docs/runbooks/replay_signing_key_rotation.md`（9-章結構供 `P1-OPS-2-RUNBOOK` mirror）
- **Memory references**：`feedback_cross_platform` / `feedback_v_migration_pg_dry_run` / `feedback_impl_done_adversarial_review` / `feedback_chinese_only_comments`

**END OF SPEC**
