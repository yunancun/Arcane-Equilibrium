# Credential Rotation Runbook

**狀態：** v1.0（2026-05-28，P1-OPS-2-RUNBOOK-V1.0-PATCH；A3 4 conditional items closed；Phase 2 cutover 待 D+14 = 2026-06-10）
**版本：** v1.0（A3-aligned，Phase 2 SOP land）
**Owner：** PA + E1（draft） → E3 + CC（review）→ PM（approve）→ BB（sign-off for exchange-facing impact）
**上游契約：**
- 設計：[`docs/execution_plan/specs/2026-05-26--p1-ops-2-secret-split-design.md`](../execution_plan/specs/2026-05-26--p1-ops-2-secret-split-design.md)
- 上游 audit：[`docs/CCAgentWorkSpace/E3/workspace/reports/2026-05-26--p0-ops-2-credential-rotation-audit.md`](../CCAgentWorkSpace/E3/workspace/reports/2026-05-26--p0-ops-2-credential-rotation-audit.md)
- 結構樣板：[`docs/runbooks/replay_signing_key_rotation.md`](replay_signing_key_rotation.md)（9 章 mirror）
**輔助腳本：** `helper_scripts/restart_all.sh`（secret prep + spawn env 注入）

---

## 1. 用途 / Why this runbook exists

OpenClaw runtime 倚賴一組 long-lived secret material 維持 Live trading 5-hard-gate（per `CLAUDE.md §四`）。E3-HIGH-2 audit 確認除 `replay_signing_key` 外其餘 secret class 0 rotation runbook，operator 緊急 / 例行 rotation 必須 ad-hoc derive，失敗模式高（漏 `--rebuild` / 漏 `/auth/renew` / 漏 audit row）。

涵蓋 **3 primary secret class**（split per OPS-2-SECRET-SPLIT）+ **6 auxiliary secret class** = 9 secret 維度；4 大事件路徑：Initial deployment / Scheduled rotation / Emergency rotation / Fail+Rollback。Mirror `replay_signing_key_rotation.md` 9 章結構。

---

## 2. Secret class inventory

### 2.1 三類 primary secret（5-gate 直接依賴）

| Class | Env var | File path（default） | 5-gate 角色 | Cadence | Owner |
|---|---|---|---|---|---|
| **P-1 IPC HMAC** | `OPENCLAW_IPC_SECRET` | `$SECRETS_ROOT/environment_files/ipc_secret.txt` | gate #4 secret slot（同主機 IPC handshake） | **180d** | Operator + PA |
| **P-2 Live-auth signing** | `OPENCLAW_LIVE_AUTH_SIGNING_KEY` | `$SECRETS_ROOT/environment_files/live_auth_signing_key.txt` | gate #5 signed authorization HMAC | **90d** | Operator + PA |
| **P-3 Bybit API key/secret** | `OPENCLAW_BYBIT_API_KEY` / `OPENCLAW_BYBIT_API_SECRET` | `$SECRETS_ROOT/bybit/api_key.txt` + `api_secret.txt` | gate #4 secret slot（exchange auth） | **90d**（align Bybit policy）| Operator + BB |

> P-1 + P-2 split 為 OPS-2-SECRET-SPLIT spec scope；split land 後本 runbook 才取代 dual-purpose 假設。Phase 1 backward-compat 期間 P-1 + P-2 material 可同值（per spec §3.1）；第一次 90d rotation 後必獨立 material（per §9.4 OPS-2 spec hidden risk）。

### 2.2 六類 auxiliary secret

| ID | Class | Env var / Location | 用途 | Cadence | Emergency revoke 路徑 |
|---|---|---|---|---|---|
| **A-1** | `authorization.json` signed artefact | `$SECRETS_ROOT/authorization.json` | gate #5 active signed token | **TTL auto-renew**（T0 hrs / T3 24h+） | `POST /api/v1/live/auth/revoke` ≤5s |
| **A-2** | `POSTGRES_PASSWORD` | `$SECRETS_ROOT/environment_files/postgres_password.txt` | learning/PG DB auth | **365d** | PG `ALTER USER` + coordinated restart |
| **A-3** | `OPENCLAW_API_TOKEN` | `$SECRETS_ROOT/environment_files/api_token.txt` | Control API operator auth | **365d**（fail-closed on `change-me` per SC-001） | regenerate + invalidate old |
| **A-4** | Provider AI keys（Anthropic / OpenAI / DeepSeek） | `$SECRETS_ROOT/environment_files/provider_<name>.txt` | L2 LLM provider auth | **90d default per provider** | Provider Web UI revoke + local file 替換 |
| **A-5** | `replay_signing_key` | `$SECRETS_ROOT/<env>/replay_signing_key` | REF-20 P2b runner manifest HMAC | **90d** | 見 `replay_signing_key_rotation.md`（independent runbook） |
| **A-6** | `replay_earn_preflight` HMAC（reuse `OPENCLAW_IPC_SECRET`） | — | Stage 0R cron-vs-operator-user 防偽 | follows P-1 cadence | follows P-1 |

> A-5 已有 dedicated runbook `replay_signing_key_rotation.md`；本 runbook 只在 §10 cross-ref。A-6 屬語意 (a) IPC HMAC，rotation 跟隨 P-1。

---

## 3. 治理約束 / Governance Invariants

| Invariant | 來源 | 違反後果 |
|---|---|---|
| 算法 = HMAC-SHA256（256-bit key） | OPS-2 spec §2.1 | sig 格式 mismatch → `BadSignature` fail-closed |
| P-1 + P-2 split 後 material 須獨立（first rotation 後） | OPS-2 spec §9.4 | blast radius 重疊 → 違反 fail-closed 強化目標 |
| File mode = 0600 owner-only read | OWASP A02:2021 + CLAUDE.md §六 | mode drift → security finding |
| File path 走 `$SECRETS_ROOT/...`（**禁** hardcode `/home/ncyu` / `/Users/ncyu`） | CLAUDE.md §六 + memory `feedback_cross_platform` | Mac 部署破 |
| Rotation 寫 `learning.governance_audit_log` 一行（action / actor / fingerprint_first8） | root principle 8 | forensic review 不能 |
| Rotation 期間 LiveDemo 同 Mainnet 同等嚴格 | feedback `live_no_degradation_by_endpoint` | endpoint 降級 = root principle 4 違反 |
| `restart_all --rebuild` 必跑 rotation 後（engine reload） | OPS-2 spec §3.1 + restart_all.sh | engine 仍用 old key |
| operator 必簽 audit row（每次 rotation）| root principle 8 + §9 | rotation 來源不可追溯 |
| Phase 2 land 後 Live + missing `OPENCLAW_LIVE_AUTH_SIGNING_KEY` → live 拒 spawn + log kind `live_auth_signing_key_missing`（panic gate 在但被 LIVE-GATE-BINDING-1 post-dominate，僅窄路徑觸發；CC-MED-1 校準 2026-06-10） | OPS-2 spec §3.2 | gate #5 弱化 |

---

## 4. Initial Deployment（每 secret class 首次寫盤）

### 4.1 前置 / Preconditions

- [ ] `$OPENCLAW_SECRETS_DIR` + `$OPENCLAW_SECRETS_ROOT` env 已 set；目錄存在 mode 0700
- [ ] 對應子目錄 `environment_files/` / `bybit/` / `<env>/` 已存在
- [ ] 1Password vault entry per class 已準備（待寫 fingerprint）
- [ ] V### audit table（如 `learning.governance_audit_log`）已 land
- [ ] operator 已 ssh trade-core（per CLAUDE.md §六 — Mac 不能跑 runtime secret prep）

### 4.2 Steps per class

#### 4.2.1 P-1 / P-2（IPC HMAC + Live-auth signing）

> ⚠️ **Phase 1 backward-compat exception（2026-05-27 ~ Phase 2 cutover D+14 = 2026-06-10）**
>
> 本 §4.2.1 描述的 urandom 獨立 material 屬 **Phase 2 cutover 後** 的正規 initial deploy 路徑。Phase 1 期間 `helper_scripts/restart_all.sh` 的 `prepare_runtime_secret_files` 在 `live_auth_signing_key.txt` 不存在時會自動 seed from `ipc_secret.txt`（`[ ! -f ]` guard，**首次** boot 才觸發），並 echo `>>> OPS-2 SECRET-SPLIT phase 1: seeded live_auth_signing_key.txt from ipc_secret.txt (backward compat; rotate to fresh urandom on next scheduled rotation per §5.2.2)`。
>
> - 此 seed 行為**不視為違反**本節 urandom 要求；屬 OPS-2 spec §3.1 Phase 1 設計 contract。
> - **第一次 scheduled rotation（90d）必須 from urandom**，不可再次 seed-from-ipc（per OPS-2 spec §9.4 hidden risk + §5.2.2 cadence）。
> - **Phase 2 cutover 後（≥2026-06-10；CC-MED-1 校準 2026-06-10，PM 拍板=保留 seed）**：`restart_all` **保留** auto-seed 作 §13.5 rollback 安全墊（僅 `[ ! -f ]` 首次 provisioning，不讀 legacy env、非 runtime fallback——引擎/Python 只讀 `OPENCLAW_LIVE_AUTH_SIGNING_KEY`/file）。**注意**：seed 複製 `ipc_secret.txt` 同 material，首次 90d urandom rotation（due **2026-09-08**）前任何 missing-file 重啟會靜默重耦合兩 secret 域——operator 見 seed echo 應視為異常信號並排查 file 為何消失。缺 key 的**實際症狀**＝engine 照常啟動、live pipeline 拒 spawn、log kind `live_auth_signing_key_missing` deny-loop（panic gate 存在但被 LIVE-GATE-BINDING-1 post-dominate，僅 `live_bindings` 已成立的窄路徑觸發；per E2 A1 + CC-MED-1）。
> - cross-ref：§13 Phase 2 Cutover SOP / §10.1.1 Phase 1 fallback WARN invariant。

```bash
# 1. 生成 32-byte high-entropy material（urandom）
sudo -u openclaw openssl rand -hex 32 \
  > $OPENCLAW_SECRETS_DIR/environment_files/ipc_secret.txt
sudo -u openclaw openssl rand -hex 32 \
  > $OPENCLAW_SECRETS_DIR/environment_files/live_auth_signing_key.txt

# 2. chmod 600
sudo chmod 600 $OPENCLAW_SECRETS_DIR/environment_files/{ipc_secret,live_auth_signing_key}.txt

# 3. fingerprint 記到 1Password（first 8 hex char）
sha256sum $OPENCLAW_SECRETS_DIR/environment_files/ipc_secret.txt | cut -c1-8
sha256sum $OPENCLAW_SECRETS_DIR/environment_files/live_auth_signing_key.txt | cut -c1-8

# 4. restart engine（拾新 key）
bash helper_scripts/restart_all.sh --rebuild

# 5. healthcheck verify
curl -s http://localhost:8001/api/v1/health | jq '.engine_status'
curl -s http://localhost:8001/api/v1/live/auth/trust-status \
  | jq '.signed_authorization.present'
# expected: engine_status=running + present=true（或 absent if 還沒 renew）
```

#### 4.2.2 P-3（Bybit API key / secret）

```bash
# 1. Bybit Web UI 生成 key（trader role + IP allowlist）
# 2. 寫盤
sudo -u openclaw bash -c \
  'echo "$NEW_KEY" > $OPENCLAW_SECRETS_DIR/bybit/api_key.txt'
sudo -u openclaw bash -c \
  'echo "$NEW_SECRET" > $OPENCLAW_SECRETS_DIR/bybit/api_secret.txt'
sudo chmod 600 $OPENCLAW_SECRETS_DIR/bybit/api_{key,secret}.txt

# 3. validate via API
curl -s -X POST http://localhost:8001/api/v1/settings/api-key/live/validate \
  -H "X-Operator-Token: $OPERATOR_TOKEN"
# expected: {"valid":true,"endpoint":"<demo|live>"}

# 4. restart + auth/renew + healthcheck
bash helper_scripts/restart_all.sh --rebuild
curl -s -X POST http://localhost:8001/api/v1/live/auth/renew \
  -H "X-Operator-Token: $OPERATOR_TOKEN"
curl -s http://localhost:8001/api/v1/live/session/status | jq
```

#### 4.2.3 A-1..A-6 Initial deploy

A-1：由 `/api/v1/live/auth/renew` 自動產生，無 manual initial step。
A-2..A-4：write file → chmod 600 → `restart_all.sh --rebuild` →（如 PG）pre-restart 跑 `ALTER USER` 同步。
A-5：見 `replay_signing_key_rotation.md §3`。
A-6：跟 P-1 同 file。

---

## 5. Scheduled Rotation（per-class cadence）

### 5.1 Cadence + Alert lead

| Class | Cadence | Alert lead | Force rotation due |
|---|---|---|---|
| P-1 IPC HMAC | 180d | 165d | 180d |
| P-2 Live-auth signing | 90d | 75d | 90d |
| P-3 Bybit API key | 90d | 75d | 90d |
| A-1 authorization.json | TTL auto | — | TTL expiry |
| A-2 POSTGRES_PASSWORD | 365d | 350d | 365d |
| A-3 OPENCLAW_API_TOKEN | 365d | 350d | 365d |
| A-4 Provider AI keys | 90d | 75d | per provider |
| A-5 replay_signing_key | 90d | 7d | 90d（per replay runbook §4）|
| A-6 (= P-1) | 180d | follows P-1 | follows P-1 |

### 5.2 Steps（per primary class）

#### 5.2.1 P-1 IPC HMAC（180d）

```bash
# 1. Notify operator + PM 排程（GovernanceHub event 或 Linear）
# 2. Backup old + write new material
UTC_TS=$(date -u +%Y%m%dT%H%M%SZ)
sudo cp $OPENCLAW_SECRETS_DIR/environment_files/ipc_secret.txt \
        $OPENCLAW_SECRETS_DIR/environment_files/ipc_secret.txt.rotated.$UTC_TS
sudo chmod 0000 $OPENCLAW_SECRETS_DIR/environment_files/ipc_secret.txt.rotated.$UTC_TS
sudo -u openclaw openssl rand -hex 32 \
  > $OPENCLAW_SECRETS_DIR/environment_files/ipc_secret.txt
sudo chmod 600 $OPENCLAW_SECRETS_DIR/environment_files/ipc_secret.txt

# 3. restart engine（IPC handshake 用新 key）
bash helper_scripts/restart_all.sh --rebuild

# 4. IPC 客戶端腳本（optuna_optimizer / replay_earn_preflight / edge_p2_flip_dry_run）
#    必須帶新 secret 重連 — verify via 跑一次 trivial IPC call
curl -s http://localhost:8001/api/v1/health/ipc | jq '.handshake'
# expected: "ok"

# 5. Audit row（operator 須親寫；本 step 屬 §9 SOP）
psql -h trade-core -d learning -c "INSERT INTO learning.governance_audit_log
  (actor, action, payload, ts) VALUES
  ('$OPERATOR_ID', 'ipc_secret_rotation',
   jsonb_build_object('old_fp', '<OLD_FP_8>', 'new_fp', '<NEW_FP_8>',
                      'rotated_at', NOW(), 'class', 'P-1'),
   NOW());"
```

#### 5.2.2 P-2 Live-auth signing（90d）

```bash
# 1-2 同 5.2.1 但 file = live_auth_signing_key.txt
# 3. restart engine
bash helper_scripts/restart_all.sh --rebuild

# 4. 立即 /auth/renew（因新 key 簽的 authorization.json 才 valid）
curl -s -X POST http://localhost:8001/api/v1/live/auth/renew \
  -H "X-Operator-Token: $OPERATOR_TOKEN"

# 5. healthcheck — watcher 5s respawn
sleep 6
curl -s http://localhost:8001/api/v1/live/auth/trust-status \
  | jq '.signed_authorization.present'
# expected: true

# 6. Audit row（action='live_auth_signing_key_rotation'）
```

#### 5.2.3 P-3 Bybit API key（90d）

per `replay_signing_key_rotation.md §4` mirror + Bybit-specific：

```bash
# 1. Bybit Web UI: 生成 new key（不 revoke old yet）
# 2. /api/v1/settings/api-key/live/validate 用 new key
# 3. 寫盤（同 4.2.2 step 2）+ chmod 600 + audit
# 4. restart_all --rebuild
# 5. /auth/renew + healthcheck
# 6. **24h soak**：觀察 Bybit retCode error rate，OK 後再 Web UI revoke old
# 7. Audit row（action='bybit_api_key_rotation'）
```

### 5.3 Auxiliary class rotation 簡要

A-2 POSTGRES_PASSWORD：`ALTER USER` 在 maintenance window；coordinate restart。
A-3 OPENCLAW_API_TOKEN：write file + restart API（engine 不受影響）。
A-4 Provider AI keys：write file + restart API 或 LLM client hot-reload（如有）。
A-5 replay_signing_key：見 `replay_signing_key_rotation.md §4`。
A-6 = P-1。

---

## 6. Emergency Rotation（5min 應急路徑）

### 6.1 Trigger

- secret fingerprint 出現在非授權場合（git diff / log / Slack / email / pastebin）
- operator 離職且持有過 `$SECRETS_ROOT` 讀權
- Bybit account 異常活動 / Web UI 告警
- vault / 1Password 完整性事件

### 6.2 Steps（per class，⚠️ 標差異）

#### 6.2.1 P-3 Bybit API key compromise（最高優先）

```bash
# ⚠️ Step 1 — Bybit Web UI revoke key（5 min；最重要 cut off attacker）
# ⚠️ Step 2 — 本地拆 Live（≤5s）
curl -s -X POST http://localhost:8001/api/v1/live/auth/revoke \
  -H "X-Operator-Token: $OPERATOR_TOKEN"
curl -s http://localhost:8001/api/v1/live/session/status
# expected: live_active=false

# Step 3 — Quarantine 舊 key file
UTC_TS=$(date -u +%Y%m%dT%H%M%SZ)
sudo mv $OPENCLAW_SECRETS_DIR/bybit/api_key.txt \
        $OPENCLAW_SECRETS_DIR/bybit/api_key.QUARANTINED.$UTC_TS
sudo chmod 0000 $OPENCLAW_SECRETS_DIR/bybit/api_key.QUARANTINED.$UTC_TS

# Step 4 — 走 §4.2.2 initial deploy（new Bybit key）
# Step 5 — /auth/renew + healthcheck（per §4.2.2 step 4）
# ⚠️ Step 6 — Audit row action='bybit_api_key_emergency_rotation' + reason
# ⚠️ Step 7 — 24h 內 PM 補 post-mortem `docs/audits/<date>--bybit_key_compromise_postmortem.md`
```

RTO target: **≤7 min**（per E3 audit §E 6-step SOP）。

#### 6.2.2 P-1 IPC HMAC compromise

```bash
# ⚠️ Quarantine + 走 §5.2.1 但跳 schedule 通知
# Live pipeline 不受影響（P-2 split 後）
# IPC 客戶端 optuna / preflight 短暫不可用 acceptable
```

RTO target: **≤5 min**。

#### 6.2.3 P-2 Live-auth signing compromise

```bash
# ⚠️ Step 1 — /api/v1/live/auth/revoke（拆 Live ≤5s）
# Step 2 — quarantine 舊 key file（同 P-3 step 3 但 file=live_auth_signing_key.txt）
# Step 3 — 走 §5.2.2 但跳 schedule 通知
# ⚠️ Step 4 — 立即 /auth/renew 用新 key 重簽
# ⚠️ Step 5 — Audit row action='live_auth_signing_key_emergency_rotation'
# ⚠️ Step 6 — Reject all authorization.json signed by compromised key — Phase 2 land 後 watcher 自動 reject
```

RTO target: **≤5 min**（per OPS-2 spec §6）。

#### 6.2.4 Auxiliary

A-1 authorization.json：`POST /api/v1/live/auth/revoke` ≤5s。
A-2 POSTGRES_PASSWORD：immediate `ALTER USER` + coordinated restart（≤30 min RTO）。
A-3 OPENCLAW_API_TOKEN：regenerate + invalidate（≤5 min）。
A-4 Provider AI keys：Provider Web UI revoke + local file 替換（≤5 min）。
A-5 replay_signing_key：見 `replay_signing_key_rotation.md §5`。

---

## 7. Fail Modes + Rollback

### 7.1 Fail modes 對照表

| Fail-mode | Class | 觸發條件 | Operator 處置 |
|---|---|---|---|
| `LiveAuthSigningKeyMissing` | P-2 | engine 啟動時新 env 未 set（Phase 2 後） | 復原 `live_auth_signing_key.txt` 或 `git revert` Phase 2 commit |
| `BadSignature` | P-2 / A-1 | watcher verify 用 new key 但 authorization.json 用 old key 簽 | `/api/v1/live/auth/renew` 用新 key 重簽 |
| `IpcAuthFailed` | P-1 | IPC handshake HMAC mismatch | 確認所有 IPC 客戶端帶新 secret reconnect |
| Bybit `retCode != 0` 連續 | P-3 | API key invalid / IP 不在 allowlist | 回 `4.2.2` validate 流程；不重試 (fail-closed) |
| `LiveAuth role mismatch` | A-1 | authorization tier 不對 | revoke + renew with correct role |
| live 拒 spawn + log kind `live_auth_signing_key_missing`（panic 僅窄路徑；CC-MED-1 校準） | P-1 / P-2 | Live + missing key file | 復原 file from `.rotated.<UTC_TS>` 或 quarantine 回退 |
| restart_all `--rebuild` fail | any | binary build fail / disk full | inspect log + revert commit + restart engine 不 rebuild |
| `/auth/renew` fail | A-1 | operator token expired / role drift | 重新登入 operator + retry |

### 7.2 Rollback procedure

```bash
# 1. Stop engines
bash helper_scripts/stop_all.sh 2>/dev/null \
  || sudo systemctl stop openclaw_engine openclaw_api

# 2. Restore previous secret（rotation backup file 命名規約 .rotated.<UTC_TS>）
TARGET=$OPENCLAW_SECRETS_DIR/environment_files/live_auth_signing_key.txt
LATEST_BACKUP=$(ls -t ${TARGET}.rotated.* 2>/dev/null | head -1)
sudo cp "$LATEST_BACKUP" "$TARGET"
sudo chmod 600 "$TARGET"
sudo chown openclaw:openclaw "$TARGET"

# 3. （如 Phase 2 commit cause panic）
git revert <phase2-commit>
bash helper_scripts/restart_all.sh --rebuild

# 4. Re-verify
curl -s http://localhost:8001/api/v1/live/auth/trust-status

# 5. Audit row action='secret_rollback' + 原因 + commit SHA
# 6. PM 24h root-cause analysis（per OPS-2 spec §3.3）
```

---

## 8. Audit Verification SQL

### 8.1 Rotation event 查詢

```sql
-- Query 1: 過去 90d 所有 rotation event
SELECT actor, action, payload->>'class' AS class,
       payload->>'old_fp' AS old_fp,
       payload->>'new_fp' AS new_fp,
       ts
  FROM learning.governance_audit_log
 WHERE action LIKE '%_rotation'
    OR action LIKE '%_emergency_rotation'
   AND ts > NOW() - INTERVAL '90 days'
 ORDER BY ts DESC;
-- expected：P-2 + P-3 每 ≤90d ≥1 row；P-1 每 ≤180d ≥1 row
```

### 8.2 Rotation 漏排檢測

```sql
-- Query 2: 找超 cadence 仍未 rotate 的 class
WITH latest AS (
  SELECT payload->>'class' AS class, MAX(ts) AS last_rotate
    FROM learning.governance_audit_log
   WHERE action LIKE '%_rotation' OR action LIKE '%_emergency_rotation'
   GROUP BY 1
)
SELECT class, last_rotate,
       EXTRACT(EPOCH FROM (NOW() - last_rotate)) / 86400 AS days_since
  FROM latest
 WHERE (class IN ('P-2','P-3','A-4','A-5') AND last_rotate < NOW() - INTERVAL '90 days')
    OR (class IN ('P-1','A-6')              AND last_rotate < NOW() - INTERVAL '180 days')
    OR (class IN ('A-2','A-3')              AND last_rotate < NOW() - INTERVAL '365 days');
-- expected：0 row（任何 row = rotation 漏排 P0）
```

### 8.3 File mode + ownership audit

```sql
-- Query 3: rotation-adjacent governance event 查 file mode drift
SELECT actor, action, payload, ts
  FROM learning.governance_audit_log
 WHERE action IN ('file_mode_drift_alert', 'secret_ownership_drift')
   AND ts > NOW() - INTERVAL '30 days'
 ORDER BY ts DESC;
-- expected：0 row（healthy）；> 0 → 立即排查 cron `replay_key_archive_cleanup` 同類 drift check
```

### 8.4 Cross-class fingerprint collision check（P-1 vs P-2 split 完整性）

```sql
-- Query 4: P-1 + P-2 split 後 fingerprint must NOT be equal（Phase 2 land 90d 後）
WITH latest_per_class AS (
  SELECT payload->>'class' AS class,
         payload->>'new_fp' AS fp,
         MAX(ts) AS last_ts
    FROM learning.governance_audit_log
   WHERE action LIKE '%_rotation'
     AND payload->>'class' IN ('P-1','P-2')
   GROUP BY 1, 2
)
SELECT 'fingerprint_collision' AS issue, p1.fp
  FROM latest_per_class p1
  JOIN latest_per_class p2 ON p1.fp = p2.fp
 WHERE p1.class = 'P-1' AND p2.class = 'P-2';
-- expected：0 row（Phase 2 land 90d 後）；> 0 → P-1 + P-2 split 退化為 dual-purpose（critical）
```

---

## 9. Operator Acknowledge SOP

每次 rotation **必須**走以下 acknowledge cycle，否則 audit chain 殘缺：

1. **Pre-rotation announcement**（≥1h before scheduled）
   - GovernanceHub event 或 Linear ticket
   - Notify PM + on-call operator
2. **Rotation execution**
   - operator 親手跑 §4 / §5 / §6 步驟
   - **每** shell session 開 `script -a $OPENCLAW_DATA_DIR/logs/rotation-$UTC_TS.log` 記 stdout/stderr
3. **Audit row 寫入**（per §5.2.x step 6）
   - actor = operator's 1Password identity（非 system user）
   - payload 必含 `class` / `old_fp` / `new_fp` / `rotated_at` / `runbook_section`
4. **Cross-system verify**（per §10）
   - engine status + API status + healthcheck + Bybit endpoint trust-status
   - **4 條 verify 全綠**才視 rotation completed
5. **Post-rotation sign-off**
   - operator 在 Linear ticket / Governance event 留 commit「Rotation completed: class=<X> fp=<NEW_FP_8>」
   - 24h 後 PM review audit row + log + verify result → close ticket

> 任何 step 漏跑 = rotation **未完成**；不論 secret 是否已寫盤、engine 是否已 restart。

---

## 10. Cross-System Verification

Rotation completion **必須**通過以下 4 verify：

### 10.1 Engine status

```bash
curl -s http://localhost:8001/api/v1/health \
  | jq '{engine: .engine_status, ipc: .ipc_status, watcher: .watcher_status}'
# expected: engine=running, ipc=connected, watcher=active
```

#### 10.1.1 Phase 1 fallback WARN invariant（D+0 → Phase 2 cutover D+14 前每日跑）

Phase 1 期間 `OPENCLAW_LIVE_AUTH_SIGNING_KEY` 已正確注入 spawn env，理論上 Rust `live_authorization.rs::read_live_auth_signing_key` fallback 分支**不應觸發**。任一觸發 = 新 env 未生效 / Rust live_authorization 走錯路徑 / 2 key 未正確分離 = Phase 2 BLOCK。屬 fail-closed observation invariant。

```bash
ssh trade-core "grep -c ops2_secret_split_phase1_fallback /tmp/openclaw/engine.log /tmp/openclaw/api.log"
```

| AC | 期望值 | 違反處理 |
|---|---|---|
| engine.log + api.log 累積計數 | 兩 file 各 = 0 | 任一 ≥ 1 → Phase 2 cutover **BLOCK**；檢查 `restart_all` 是否走到 spawn point + env 注入是否生效；ref §13.1 cutover preconditions |

> Cross-ref：E1 IMPL 報告 §5.4 14d Soak Observable 表（同 invariant）+ §13 Phase 2 Cutover SOP。

### 10.2 API status

```bash
curl -s http://localhost:8001/api/v1/live/session/status \
  | jq '{live: .live_active, endpoint: .bybit_endpoint, trust: .trust_state}'
# expected: trust=signed_present + endpoint match expected env
```

### 10.3 Healthcheck integration

```bash
python3 $OPENCLAW_BASE_DIR/helper_scripts/db/passive_wait_healthcheck.py \
  --check secret_rotation
# expected: all 9 secret class pass + 0 file_mode_drift + 0 fingerprint_collision
```

> Healthcheck SQL routine **建議**新增（P2-OPS-2-AUDIT-ENDPOINT follow-up）；目前未實裝以 §8 SQL 替代。

### 10.4 Bybit endpoint trust-status

```bash
curl -s http://localhost:8001/api/v1/live/auth/trust-status \
  | jq '{present: .signed_authorization.present,
         tier: .signed_authorization.tier,
         expires_in: .signed_authorization.expires_in_seconds,
         env: .signed_authorization.env_allowed}'
# expected: present=true + env match (mainnet|testnet|demo) + expires_in > 60
```

### 10.5 Cross-language HMAC sanity check

#### 動機

OPS-2 P-2 live-auth signing 同 Wave D Earn HMAC flow 都倚賴雙端（Python signing path / Rust verify path）對 canonical_payload 完全 byte-identical 計算同一 HMAC-SHA256。Python 端用 `json.dumps(sort_keys=True, separators=(",",":"))` 標準化；Rust 端必用 `BTreeMap` 或顯式 sort 同序生成 canonical bytes。**任何 canonical 順序漂移 / separator drift / encoding drift = HMAC byte 不對齊 = 雙端 sig 失配 = Earn / live-auth flow silent fail**，且失敗 mode 是 fail-closed 拒授權（不會降級重試），operator 看到的會是 `BadSignature` 而非具體 cause。

#### canonical_payload format 規格（pinned）

| 屬性 | 值 |
|---|---|
| serialize | JSON |
| key 順序 | `sort_keys=True`（lexicographic） |
| separators | `(",",":")` (無 space) |
| 字符 encoding | UTF-8 |
| HMAC 算法 | HMAC-SHA256 |
| 輸出格式 | lowercase hex（64 char） |

> Wave D Earn 採 **pipe-delimited string** canonical (不是 JSON) 格式，見 `earn_routes.py:402 _verify_stage_0r_hmac`；TODO §6 `P1-EARN-WAVE-D-RUST-HMAC-CANONICAL-FORM` 條目要求 Wave D Rust IMPL 對齊。本 §10.5 主要 cover OPS-2 P-2 live-auth；Wave D Earn 走獨立 fixture，cross-ref Wave D spec。

#### Pinned fixture（OPS-2 P-2 Phase 1 IMPL）

- **fixture key**: `b'test-live-auth-signing-key-do-not-use-in-prod'`
- **fixture canonical_payload**: `2|T0_ENTRY|1700000000000|1700086400000|ncyu|live_reserved|live_demo`
- **pinned hex**: `1b2b18d7e212d0d1e8f943c25f6f070b2ba75013b8fd5c3a021800d11b8b78fc`

該 fixture per E1 IMPL §報告 line 13 + 31 + 41，Rust + Python 同 fixture 算出同 hex；OPS-2 land 同時 pin 在雙端 unit test (`cross_lang_hmac_fixture_is_byte_identical` Rust + Python 對應 case)。

#### Operator sanity one-liner

```bash
# Python (operator 或 CI 一鍵 paste；單行 stdlib 無依賴)
python3 -c "import hmac,hashlib; print(hmac.new(b'test-live-auth-signing-key-do-not-use-in-prod', b'2|T0_ENTRY|1700000000000|1700086400000|ncyu|live_reserved|live_demo', hashlib.sha256).hexdigest())"
# expected: 1b2b18d7e212d0d1e8f943c25f6f070b2ba75013b8fd5c3a021800d11b8b78fc
```

```bash
# Rust（透過已 pin 的 cargo test 雙端對齊；ssh trade-core 跑）
ssh trade-core "cd $OPENCLAW_BASE_DIR/rust/openclaw_engine && cargo test --release --quiet cross_lang_hmac_fixture_is_byte_identical -- --nocapture"
# expected: test cross_lang_hmac_fixture_is_byte_identical ... ok（assert pinned hex 命中）
```

#### AC + 違反處理

| AC | 期望值 | 違反處理 |
|---|---|---|
| Python one-liner output | `1b2b18d7e212d0d1e8f943c25f6f070b2ba75013b8fd5c3a021800d11b8b78fc` | 不等 → Python stdlib drift / 環境異常；**不可** rotation；先排查 |
| Rust `cargo test` output | `... ok` （pinned hex 命中） | fail → Rust canonical_payload format 漂移 / HMAC algo 換 / hex encoding 換；**secret split 完整性破壞** → rollback per §7.2 + forensic |
| Rust hex == Python hex == pinned hex（三向）| 三方完全相等 | 任一不等 = 上游 Earn first stake silent fail risk + live-auth verify silent fail risk → BLOCK rotation + raise forensic ticket |

#### Cross-ref

- Wave D Earn HMAC canonical form follow-up：TODO §6 `P1-EARN-WAVE-D-RUST-HMAC-CANONICAL-FORM`
- E1 IMPL pinned hex 出處：`docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-27--ops_2_secret_split_impl.md` line 13 / 31 / 41 / 153 / 210
- OPS-2 spec §8.5 E2 重點 #1（防 canonical drift）+ §1.2（防 Earn first stake silent fail）

---

## 11. 修訂歷史 / Revision History

| 版次 | 日期 | 修訂者 | 摘要 |
|---|---|---|---|
| **v0.9 (draft)** | 2026-05-27 | PA (P1-OPS-2-RUNBOOK draft) | mirror replay_signing_key_rotation.md 9-章；涵蓋 3 primary + 6 auxiliary；含 Initial deploy / Scheduled / Emergency / Fail+Rollback / Audit SQL / Operator SOP / Cross-system verify；待 OP-1 first dry-run timing 後 v1.0 patch |
| **v1.0** | 2026-05-28 | PA (P1-OPS-2-RUNBOOK-V1.0-PATCH) | 4-patch land 對齊 A3 對抗性核驗 4 conditional items：(1) §4.2.1 Phase 1 backward-compat note（restart_all seed-from-ipc 不違反 urandom 要求，首次 90d rotation 後必獨立）；(2) §10.1.1 Phase 1 fallback WARN invariant（D+0 → D+14 每日 `grep -c ops2_secret_split_phase1_fallback /tmp/openclaw/{engine,api}.log = 0`）；(3) §10.5 Cross-language HMAC sanity check（pinned hex `1b2b...78fc` + Python stdlib one-liner + Rust `cross_lang_hmac_fixture_is_byte_identical` test）；(4) §13 Phase 2 Cutover SOP（D+14 = 2026-06-10 preconditions / Grafana 新字串 / PR dispatch / panic verify / rollback / post-cutover verify）。ref A3 SSOT [`docs/CCAgentWorkSpace/A3/workspace/reports/2026-05-27--ops_2_secret_split_adversarial_review.md`](../CCAgentWorkSpace/A3/workspace/reports/2026-05-27--ops_2_secret_split_adversarial_review.md) |

---

## 12. Cross-References

- 上游 spec：[`docs/execution_plan/specs/2026-05-26--p1-ops-2-secret-split-design.md`](../execution_plan/specs/2026-05-26--p1-ops-2-secret-split-design.md) §1-§12
- 上游 audit：[`docs/CCAgentWorkSpace/E3/workspace/reports/2026-05-26--p0-ops-2-credential-rotation-audit.md`](../CCAgentWorkSpace/E3/workspace/reports/2026-05-26--p0-ops-2-credential-rotation-audit.md) §C-1 / §D / §E
- A3 對抗性核驗 SSOT（v1.0 patch 對齊源）：[`docs/CCAgentWorkSpace/A3/workspace/reports/2026-05-27--ops_2_secret_split_adversarial_review.md`](../CCAgentWorkSpace/A3/workspace/reports/2026-05-27--ops_2_secret_split_adversarial_review.md)
- E1 Phase 1 IMPL SSOT（pinned hex / fallback WARN invariant 出處）：[`docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-27--ops_2_secret_split_impl.md`](../CCAgentWorkSpace/E1/workspace/reports/2026-05-27--ops_2_secret_split_impl.md)
- Sibling runbook（A-5）：[`docs/runbooks/replay_signing_key_rotation.md`](replay_signing_key_rotation.md)
- Phase 2 cutover SOP：本 runbook §13（D+14 = 2026-06-10）
- Phase 1 backward-compat note：本 runbook §4.2.1（box block）+ §10.1.1（WARN invariant）+ §10.5（cross-lang HMAC sanity）
- Hard boundaries：`srv/CLAUDE.md §四`（5-hard-gate）+ `srv/CLAUDE.md §六`（Runtime Reality）
- Root principles：`srv/CLAUDE.md §二`（#1 / #4 / #6 / #8 / #9）
- Cross-platform：memory `feedback_cross_platform`（`$SECRETS_ROOT` 無 user-home hardcode）
- Migration safety：memory `feedback_v_migration_pg_dry_run`（Mac mock 不夠，Linux runtime empirical）
- Adversarial review：memory `feedback_impl_done_adversarial_review`（rotation IMPL 走 CC + E2 dual review）
- Shell paste safety：memory `feedback_shell_paste_safety`（單行 one-liner，禁 heredoc）
- Helper scripts：`helper_scripts/restart_all.sh`（secret prep + spawn env 注入）
- TODO 上游條目：`P1-OPS-2-PHASE-2-CUTOVER`（D+14 PR）+ `P1-EARN-WAVE-D-RUST-HMAC-CANONICAL-FORM`（Wave D Rust canonical 對齊）

---

## 13. Phase 2 Cutover SOP

> **適用時機**：Phase 1 land + 14d soak 0 WARN log 完成後（D+14 = **2026-06-10**），切到 fail-closed 強化模式（移 Rust fallback / 加第二 panic block / 刪舊 `AuthError::IpcSecretMissing` 變體 / Python reason rename）。
>
> **owner**：E1（IMPL）+ CC（review）+ BB（exchange-facing sign-off）+ PM（approve）。Operator 親手執行 §13.2 + §13.6 verify。
>
> **non-negotiable**：本節指令一律單行 one-liner（per memory `feedback_shell_paste_safety`）。

### 13.1 前置 / Preconditions（D+14 readiness gate）

| Gate | Check | 違反 |
|---|---|---|
| **14d soak fallback WARN = 0** | per §10.1.1：`ssh trade-core "grep -c ops2_secret_split_phase1_fallback /tmp/openclaw/engine.log /tmp/openclaw/api.log"` 累積 = 0 | 任一 ≥ 1 → cutover **BLOCK**；E1 排查 + soak 重起算 |
| **≥1 次 /auth/renew 重簽記錄** | per E1 IMPL §5.4 Observable 表：API access log 或 `learning.live_auth_renewals` ≥ 1 row（soak 期間 operator 走過至少 1 次 renew） | 0 次 → operator 手動 trigger 一次 renew + 等 watcher 5s respawn 再驗 trust-status |
| **`live_auth_signing_key.txt` 完整性** | `ssh trade-core "ls -la \$HOME/BybitOpenClaw/secrets/environment_files/live_auth_signing_key.txt"` mode 600 + 非零 byte + mtime 在 soak 區間 | mode drift → `sudo chmod 600`；missing → §7.2 rollback path |
| **engine PID 穩定** | soak 期間 restart 計數無異常飆升 | 不穩 → cutover **BLOCK** |
| **PM 確認 Sprint 4 first Live ≥ 2026-06-10**（A3 conditional #4） | TODO § / Linear ticket commit | 早於 D+14 安排 Live → 推遲或 cutover 前完成 |

### 13.2 Operator 外部監控同步（Grafana / journald / log rules）

> A3 §7 提示外部 alert rule 是 first-time GUI / operator 個人 monitoring stack 的盲區，本 repo grep 不可 audit。Phase 2 cutover 前 **operator 親手確認**外部系統能 catch 新字串。

**新 alert pattern**（cutover 前加入外部 monitoring）：

- log substring：`live_auth_signing_key_missing`
- Rust error variant 名（trace / journald）：`AuthError::LiveAuthSigningKeyMissing`
- preflight gate token（live_preflight.py 既有雙 taxonomy，CC-LOW-2）：`live_auth_key_missing`

**parallel 保留（不立即移除）**：

- 舊 substring：`ipc_secret_missing`（Phase 1 IMPL 保留並列；Phase 2 cutover commit 才刪 Rust 變體 + Python reason rename）
- 舊 Rust 變體名：`AuthError::IpcSecretMissing`（Phase 2 PR 同次刪除；外部 alert rule 可留 14d soak buffer 再清）

**Operator 確認 checklist**：

- [ ] Grafana / journald alert rule 已加新字串 `live_auth_signing_key_missing` + `AuthError::LiveAuthSigningKeyMissing`
- [ ] 舊字串 alert rule 保留 14d cutover buffer（cutover 後 D+14 才清）
- [ ] alert routing 仍 page on-call（test fire 一次驗 channel）
- [ ] operator 親簽 audit row：actor / action='ops2_phase2_external_alert_aligned' / ts

### 13.3 PR dispatch（E1 IMPL）

per OPS-2 spec §3.2 + spec §4.1.1-§4.1.4 + §4.2.1，Phase 2 PR 改動範圍：

| 文件 | 改動 |
|---|---|
| `rust/openclaw_engine/src/live_authorization.rs` | fallback 分支整段刪除（spec §3.2）；`AuthError::IpcSecretMissing` 變體 + Display impl + `auth_error_kind` arm 刪除 |
| `rust/openclaw_engine/src/main.rs:402` 後 | 加第二 panic block：Live + missing `OPENCLAW_LIVE_AUTH_SIGNING_KEY` → engine startup panic（fail-closed）|
| `rust/openclaw_engine/src/live_auth_watcher_tests.rs` | line 195 / 199 teardown 只 set `OPENCLAW_LIVE_AUTH_SIGNING_KEY`（不再雙 set） |
| `program_code/exchange_connectors/bybit_connector/control_api_v1/app/live_trust_routes.py:473` | reason 字串 `ipc_secret_missing` → `live_auth_signing_key_missing` |

TODO 上游條目：§6 `P1-OPS-2-PHASE-2-CUTOVER`（D+14 PR）。PR dispatch chain：E1 IMPL → CC review → BB sign-off → PM approve → merge.

### 13.4 Panic verify（sandbox / dry-run，禁 production 直觸）

> **Production engine 直接 trigger panic 會 SIGABRT，蕩 live pipeline**。本步驟強制在 sandbox env / dry-run pattern 跑。

**推薦 pattern**：

```bash
ssh trade-core "cd $OPENCLAW_BASE_DIR/rust/openclaw_engine && cargo test --release --quiet live_auth_signing_key_missing_panics_when_live -- --nocapture"
```

| AC | 期望值 | 違反 |
|---|---|---|
| Rust test 命中第二 panic block | `... ok`（panic message 含 `OPENCLAW_LIVE_AUTH_SIGNING_KEY` 字眼） | fail → spec §3.2 panic block 未生效 → PR **REJECT** |
| `cargo test` 全 suite | 全 PASS（含舊 `live_auth_signing_key_missing_returns_specific_variant` Rust test 仍綠） | 任一 fail → PR **REJECT** |

> sandbox env / Phase 2 PR CI 跑 cargo test 即等價 panic verify；不必 production engine 觸發。

### 13.5 Rollback（D+14 cutover 失敗）

per OPS-2 spec §3.3 Rollback table + 本 runbook §7.2 Rollback procedure：

```bash
# 1. stop engines
ssh trade-core "bash $OPENCLAW_BASE_DIR/helper_scripts/stop_all.sh"

# 2. 確認 live_auth_signing_key.txt 存在 chmod 600 + 非空（spec §3.3 Phase 2 D+14 後缺 key row；實際症狀=live 拒 spawn 非 panic 阻 boot，CC-MED-1 校準）
ssh trade-core "ls -la \$HOME/BybitOpenClaw/secrets/environment_files/live_auth_signing_key.txt"

# 3. 若不存在 → seed from ipc_secret.txt 暫救（緊急 fallback）
ssh trade-core "sudo -u openclaw cp \$HOME/BybitOpenClaw/secrets/environment_files/ipc_secret.txt \$HOME/BybitOpenClaw/secrets/environment_files/live_auth_signing_key.txt && sudo chmod 600 \$HOME/BybitOpenClaw/secrets/environment_files/live_auth_signing_key.txt"

# 4. 仍 panic → git revert Phase 2 commit 回 Phase 1 fallback 模式
ssh trade-core "cd $OPENCLAW_BASE_DIR && git revert <phase2-commit-sha> && bash helper_scripts/restart_all.sh --rebuild"

# 5. Audit row + 24h PM root-cause analysis（per §7.2 step 5-6）
```

**Rollback timeline target**：≤30 min from cutover failure detect → live pipeline 恢復 Phase 1 模式。

### 13.6 Verify SOP（cutover 後 D+15 ~ D+44）

| 觀察項 | 工具 | 期望值 |
|---|---|---|
| **engine PID 穩定 24h** | `ssh trade-core "pgrep -x openclaw-engine"` | PID 穩定，無 panic 觸發 |
| **無 fallback WARN（永久）** | per §10.1.1 grep | 累積仍 = 0（fallback 路徑已刪不可能觸發；任何 grep > 0 = 有殘留代碼 P0） |
| **trust-status reason 字串無 `ipc_secret_missing`** | `ssh trade-core "curl -s http://localhost:8001/api/v1/live/auth/trust-status \| grep -c ipc_secret_missing"` | = 0 |
| **cross-lang HMAC sanity check 仍 PASS** | per §10.5 Python + Rust one-liner | 三向命中 pinned hex |
| **fresh urandom rotate cadence 90d 從 cutover 日重啟計** | TODO 排程 + §5.1 cadence table | first scheduled rotation due = cutover + 90d = **2026-09-08**（per spec §3.1）；第一次必走 §5.2.2 urandom（**禁** seed-from-ipc，per §4.2.1 backward-compat note）|

**Cutover sign-off**：D+44（cutover + 30d）PM review 上述 5 invariant 全綠 → `P1-OPS-2-PHASE-2-CUTOVER` closure → archive Phase 1 + Phase 2 lineage 到 `docs/audits/2026-06-10--ops2_phase2_cutover_signoff.md`。

---

**END OF RUNBOOK v1.0**
