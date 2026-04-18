# LIVE-GATE-BINDING-1 實作日誌（2026-04-18）

> Python Earned-Trust ↔ Rust openclaw_engine 之間的簽名授權綁定。
> 閉合「Operator 未在 T0 Entry renew/approve 情況下 Rust 也能啟動 Live」的 P0-CRITICAL 授權旁通漏洞。

---

## 一、觸發情境（RCA）

**Operator 報告**：「看一下 live 為何在 T0 Entry 我沒有 renew 和批准的情況下就開始交易了」

審查後確認：LiveDemo 路徑可在 Operator 完全沒有點擊任何 renew / approve 按鈕的情況下由 Rust 端自動拉起。

### 為何會發生

LIVE-GUARD-1（2026-04-16）已在 Rust 端補上三重 Mainnet 硬鎖（`OPENCLAW_ALLOW_MAINNET=1` env var · Mainnet env var fallback 封閉 · 憑證空時構造 `Err`），但 LiveDemo（`api-demo.bybit.com`）與 Demo / Testnet 路徑均不在此三重鎖範圍內。

**Python 側**：`EarnedTrust` 引擎 + SM-01 授權 + T0/T1/T2/T3 TTL 階梯 + Operator 角色 auth 全部實現、單測綠、GUI 運轉正常。

**Rust 側**：`build_exchange_pipeline()` 讀的是 `secret_files/bybit/<slot>/{api_key, api_secret}` 與 env var — **完全不 care Python 的授權狀態**。

也就是說：

```
┌─────────────────────────────────────────────────────────┐
│  Python 的 renew / approve / TTL expiry / revoke        │
│  對 Rust 有 0 行代碼執行性約束。                          │
│                                                          │
│  Rust 只要「slot 有 key」就會把 pipeline spawn 起來。    │
└─────────────────────────────────────────────────────────┘
```

→ 任何時候只要 slot 有憑證，重啟 engine 即進入 Live（含 LiveDemo），Operator 不在場也會。

### 設計決策：不做 Python 全 Rust 化

Operator 提出「是否全 Rust 化 Python 的門控」。評估後維持現狀分工：

- Python 繼續持有 Earned-Trust / TTL / audit trail / Operator GUI 等業務語意（這些天然屬於 FastAPI control plane）。
- **補上一張「簽名授權契約」把 Python 的業務決策可驗證地傳達給 Rust**。
- Rust 只需驗簽 + 查過期 + 查 env_allowed，不需重實作 Earned-Trust 狀態機。

這符合「Rust = 交易大腦 / Python = 業務橋接+GUI」的既有分工（見 MEMORY `project_openclaw_positioning.md`）。

### 核心原則（已存入 memory）

> **LiveDemo 雖跑在 `api-demo.bybit.com`（play-money），仍屬 Live 序列的一環；不可因 API endpoint 差異而降級任何 live-level 門控。**
> LiveDemo 存在的**唯一目的**就是讓 Live 標準在低財務風險下被完整演練；一旦降級，LiveDemo 就失去驗證價值。

檔案：`memory/feedback_live_no_degradation_by_endpoint.md`

---

## 二、合約：authorization.json

### 路徑

```
$OPENCLAW_SECRETS_DIR/live/authorization.json
fallback: $HOME/BybitOpenClaw/secrets/secret_files/bybit/live/authorization.json
```

### 格式

```json
{
  "version": 1,
  "tier": "T0_ENTRY",
  "issued_at_ms": 1745000000000,
  "expires_at_ms": 1745086400000,
  "operator_id": "ncyu",
  "env_allowed": ["live_demo"],
  "sig": "hex-encoded HMAC-SHA256"
}
```

### Canonical payload（byte-for-byte，Python↔Rust 雙端必須一致）

```
{version}|{tier}|{issued_at_ms}|{expires_at_ms}|{operator_id}|{env_sorted_csv}
```

- `env_allowed` 於簽名前 `sort() + dedup()`，避免序列差異導致簽名不一致
- `tier` 用 TrustTier enum 的 wire name（`T0_ENTRY` / `T1_PROVISIONAL` / `T2_ESTABLISHED` / `T3_TRUSTED`）
- 時間戳一律 ms epoch（Python time.time_ns() // 1_000_000，Rust SystemTime UNIX_EPOCH as_millis）

### 簽名

```
HMAC-SHA256(key=OPENCLAW_IPC_SECRET, msg=canonical_payload) → hex digest
```

IPC secret 源頭與既有 IPC server 同 env var；Rust/Python 從同一 env var 讀。

### env_allowed 值

- `live_demo` → `BybitEnvironment::LiveDemo`
- `mainnet` → `BybitEnvironment::Mainnet`

`Demo` / `Testnet` 不屬於 live 序列，Rust 遇到會回 `UnsupportedEnv`。

---

## 三、實作

### 3.1 Rust 驗簽模組（新）

`rust/openclaw_engine/src/live_authorization.rs`

- `LiveAuthorization` struct + serde
- `canonical_payload()` — 與 Python 簽名端 byte-for-byte 對齊（`sort + dedup` 同策略）
- `verify_in_memory(auth, env, now_ms, ipc_secret)` — 依序檢查：
  1. `version == 1`（不匹配 → `UnsupportedVersion`，**在驗簽前**擋掉避免 oracle 化簽名驗證器）
  2. HMAC-SHA256 hex 比對（`constant_time_eq`）→ `BadSignature`
  3. `expires_at_ms > now_ms`（**嚴格大於**，`==` 視為已過期）→ `Expired`
  4. `env` 落於 `env_allowed` → `EnvNotAllowed` / `UnsupportedEnv`
- `load_and_verify(env)` — 讀檔 + 解析 + 驗證；檔案不存在 = `FileMissing`（非軟警告）
- `auth_error_kind(&e)` — 給 telemetry 用的穩定 label（不會因內部訊息變動）

### 3.2 Rust 啟動接線

`rust/openclaw_engine/src/startup.rs::build_exchange_pipeline`

```rust
if kind == PipelineKind::Live {
    match load_and_verify(env) {
        Ok(auth) => info!(tier = %auth.tier, expires_at_ms = auth.expires_at_ms, ...),
        Err(e)  => { warn!(error_kind = auth_error_kind(&e), ...); return None; }
    }
}
```

`return None` 使 pipeline 不 spawn，Paper/Demo 不受影響。

### 3.3 Rust mid-session re-verify

`rust/openclaw_engine/src/main.rs`

引擎 started log 後、ws tick-stale watchdog 前新增 5 min interval 任務，每次 tick 重驗一次授權：

- **簽名損壞 / 過期 / env_allowed 改動 / 檔案被刪** → `cancel.cancel()` → 整個 engine 優雅停機
- 命名 `LIVE AUTHORIZATION INVALIDATED MID-SESSION` 方便告警
- 與 WS watchdog 共用 `CancellationToken`，關閉行為一致

### 3.4 Python 簽寫入 / 撤銷

`program_code/.../control_api_v1/app/live_trust_routes.py`

- `_canonical_authorization_payload()` — 與 Rust 端 `canonical_payload` 對齊
- `_sign_authorization_payload()` — `hmac.new(..., sha256).hexdigest()`
- `_atomic_write_json()` — 寫 tmpfile → `os.fchmod(0o600)` → `os.replace()`（crash-safe）
- `_write_signed_live_authorization()` — **env-var 不存在即 raise `RuntimeError`**，**絕不 silent 寫未簽檔**
- `_delete_live_authorization_file()` — 冪等（已刪 → False，不 raise）
- `_TIER_WIRE_NAME` — TrustTier enum → wire name 映射（防 `.name` 被重構）

### 3.5 Python 路由 hook

- `POST /api/v1/live/auth/renew` 成功後呼叫 `_write_signed_live_authorization()`；失敗 → `HTTPException(500)`，不向 operator 謊報「renewed」
- `POST /api/v1/live/auth/renew/review` 同上
- `_revoke_existing_live_auths()` 結尾一律呼叫 `_delete_live_authorization_file()`，讓 Rust 在下個 5 min 重驗時 fail-closed

### 3.6 env_allowed 派生

讀 `$OPENCLAW_SECRETS_DIR/live/bybit_endpoint` 檔案：

- `"demo"` → `["live_demo"]`
- `"mainnet"` / 檔案不存在 / 其他值 → `["mainnet"]`（**fail-safe 預設 mainnet，不 silently 放水到 live_demo**）

---

## 四、測試

### Rust（`cargo test -p openclaw_engine --lib live_authorization`）

15 個新單測：

- canonical payload 排序 / dedup / 空 envs
- 合法 live_demo / mainnet 通過
- 只 approved live_demo → Mainnet 拒 `EnvNotAllowed`
- 兩者 approved → 任一 env 通過
- `expires_at_ms == now_ms` 邊界拒
- 任一欄位（tier / expires / env）被竄改 → `BadSignature`
- 錯誤 IPC secret → `BadSignature`
- 錯誤 version → `UnsupportedVersion`（在驗簽前擋掉）
- `Demo` / `Testnet` → `UnsupportedEnv`
- env_allowed 入 payload 前 sort，儲存順序不影響 sig
- `load_and_verify` 讀檔 + env override 覆蓋正確
- `auth_error_kind` label 穩定（通信契約）

Engine lib 全量：**1452 passed / 0 failed**。

### Python（`pytest tests/test_live_authorization_signing.py`）

10 個新測試：

- Python canonical 格式與 Rust spec 逐字節一致
- env_allowed 先 sort + dedup 再簽
- 手算 HMAC 反推 `_sign_authorization_payload`
- End-to-end 寫檔：存在 / mode == 0o600 / 內容可驗簽
- 無 IPC secret → raise，**且檔案沒被建**（不 silent 寫未簽）
- mainnet endpoint → `env_allowed == ["mainnet"]`
- 缺 endpoint 檔 → 預設 mainnet
- delete 首次 True、第二次 False、冪等
- 模擬 `os.replace` 中途 crash → 沒有半成品 authorization.json、tmpfile 不留垃圾
- TrustTier enum 每個成員都有對應 wire name

全部 **10 / 10 pass in 0.31s**。

`tests/test_earned_trust_engine.py` 的 `ModuleNotFoundError: program_code` 為既存（本 commit 無關），git blame 為 commit 5d99875 引入，不阻本 P0。

---

## 五、新的真實 Live 門控總覽（5 項）

| # | 門控 | 由誰檢查 | 本次改動 |
|---|------|----------|----------|
| 1 | `live_reserved` global mode | Python | 既有 |
| 2 | Operator 角色 auth | Python | 既有 |
| 3 | `OPENCLAW_ALLOW_MAINNET=1` env var（僅 Mainnet） | Rust | LIVE-GUARD-1 既有 |
| 4 | secret slot 有 api_key + api_secret | Rust | LIVE-GUARD-1 既有 |
| 5 | **`authorization.json` 簽名有效 + 未過期 + env_allowed 匹配** | **Rust**（啟動 + 每 5 min） | **LIVE-GATE-BINDING-1 新增** |

**Rust 可驗證**：3 / 5 → **4 / 5**（#3 / #4 / #5 + 構造成功 = 4 項）

任何 Python 側 revoke / TTL 過期 / operator 未批准 → `authorization.json` 缺失或過期 → Rust 端 `build_exchange_pipeline` 拒 spawn / mid-session 5 min 觸發 engine shutdown。

---

## 六、已知限制（已接受）

1. **最多 5 min 響應延遲**：mid-session revoke 最壞情況 Rust 在下個 5 min tick 才感知。對 Live-Demo 階段這個延遲可接受；若 Mainnet 需求更嚴，可把 interval 降到 60s，或加 IPC push-to-invalidate。
2. **單機共享 IPC secret**：若 operator 機器完全被攻陷，攻擊者可偽造 authorization.json。此層防的是「忘記 approve」不是「系統已被 root」；後者另案（SEC-*）。
3. **LiveDemo 與 Mainnet 共用同一 secret 目錄**：目前 `live/` slot 兼做 LiveDemo / Mainnet。`bybit_endpoint` 檔 + `env_allowed` 共同決定當前 session 可否走 Mainnet。operator 若把 `bybit_endpoint` 改為 `mainnet` 而 authorization.json 只 approve `live_demo`，Rust 端會 `EnvNotAllowed` 拒 spawn，符合 fail-safe。

---

## 七、部署步驟（operator）

1. `restart_all.sh --rebuild` 重建 engine binary + PyO3 橋（LIVE-GATE-BINDING-1 是 Rust 側變更）
2. 引擎啟動後，如果 `authorization.json` 不存在，Live pipeline 直接不 spawn（log: `live authorization missing`）
3. Operator 在 GUI 點 `Renew T0 Entry` 或 `Approve renewal` → Python 寫出 signed authorization.json → 下一次 pipeline build attempt 通過
4. operator 可隨時點 `Revoke` → authorization.json 立即 unlink → Rust 下個 5 min 自動 shutdown engine；也可手動 `sudo rm authorization.json` 達同樣效果

---

## 八、下一步

- 觀察 1 週：log 內是否出現 non-noise `LIVE AUTHORIZATION INVALIDATED` 事件
- 如需把 5 min interval 降到 60s，改 `main.rs::AUTH_REVERIFY_INTERVAL_SECS` 單一常量
- Mainnet 上線前考慮把 LiveDemo 跟 Mainnet 分兩個 slot 目錄（目前共用 `live/`），各自獨立 authorization.json
- TODO.md / CLAUDE.md §四 已同步
