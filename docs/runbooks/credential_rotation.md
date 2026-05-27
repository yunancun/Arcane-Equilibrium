# Credential Rotation Runbook

**狀態：** DRAFT v0.9（2026-05-27，P1-OPS-2-RUNBOOK draft；待 OP-1 first dry-run 收 timing 後 v1.0 patch）
**版本：** v0.9（draft pre-dry-run）
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
| Phase 2 land 後 Live + missing `OPENCLAW_LIVE_AUTH_SIGNING_KEY` → engine startup panic | OPS-2 spec §3.2 | gate #5 弱化 |

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
| engine startup panic | P-1 / P-2 | Live + missing key file | 復原 file from `.rotated.<UTC_TS>` 或 quarantine 回退 |
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

---

## 11. 修訂歷史 / Revision History

| 版次 | 日期 | 修訂者 | 摘要 |
|---|---|---|---|
| **v0.9 (draft)** | 2026-05-27 | PA (P1-OPS-2-RUNBOOK draft) | mirror replay_signing_key_rotation.md 9-章；涵蓋 3 primary + 6 auxiliary；含 Initial deploy / Scheduled / Emergency / Fail+Rollback / Audit SQL / Operator SOP / Cross-system verify；待 OP-1 first dry-run timing 後 v1.0 patch |

---

## 12. Cross-References

- 上游 spec：[`docs/execution_plan/specs/2026-05-26--p1-ops-2-secret-split-design.md`](../execution_plan/specs/2026-05-26--p1-ops-2-secret-split-design.md) §1-§12
- 上游 audit：[`docs/CCAgentWorkSpace/E3/workspace/reports/2026-05-26--p0-ops-2-credential-rotation-audit.md`](../CCAgentWorkSpace/E3/workspace/reports/2026-05-26--p0-ops-2-credential-rotation-audit.md) §C-1 / §D / §E
- Sibling runbook（A-5）：[`docs/runbooks/replay_signing_key_rotation.md`](replay_signing_key_rotation.md)
- Hard boundaries：`srv/CLAUDE.md §四`（5-hard-gate）+ `srv/CLAUDE.md §六`（Runtime Reality）
- Root principles：`srv/CLAUDE.md §二`（#1 / #4 / #6 / #8 / #9）
- Cross-platform：memory `feedback_cross_platform`（`$SECRETS_ROOT` 無 user-home hardcode）
- Migration safety：memory `feedback_v_migration_pg_dry_run`（Mac mock 不夠，Linux runtime empirical）
- Adversarial review：memory `feedback_impl_done_adversarial_review`（rotation IMPL 走 CC + E2 dual review）
- Helper scripts：`helper_scripts/restart_all.sh`（secret prep + spawn env 注入）

**END OF RUNBOOK v0.9 DRAFT**
