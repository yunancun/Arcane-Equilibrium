# Replay Signing Key — Deployment + Rotation Runbook

**狀態：** Active（REF-20 P0 baseline）
**版本：** v1（2026-05-03，Wave 1 R20-P0-T8 land）
**Owner：** Operator + PM
**契約上游：** [`docs/execution_plan/2026-05-03--ref20_paper_replay_lab_dev_plan_v3.md`](../execution_plan/2026-05-03--ref20_paper_replay_lab_dev_plan_v3.md) §3 G9 + §5
**輔助腳本：** [`helper_scripts/operator/generate_replay_signing_key.sh`](../../helper_scripts/operator/generate_replay_signing_key.sh)
**Migration archive：** V042 `replay_signing_keys` (reserved per `sql/migrations/REF-20_RESERVATION.md`)

---

## 1. 用途 / Why this runbook exists

REF-20 Paper Replay Lab 對所有 replay manifest 做 server-side HMAC-SHA256 簽名（V3 §5），防止 client tampering。Manifest verification 是 P2b runner 啟動前的 fail-closed gate（V3 §3 G2 + §6.2），key 不對等於整個 replay subsystem 拒絕啟動。

本 runbook 規範三類事件:
- **Initial deployment**（每環境首次部署）
- **Scheduled rotation**（90d 例行輪替）
- **Emergency rotation**（key 洩漏 / 離職員工）

REF-20 V3 §5 specifies HMAC-SHA256 server-side signing for all replay manifests as a fail-closed gate before P2b runner startup. This runbook governs initial key deployment, scheduled 90d rotations, and emergency key rotation events.

---

## 2. 治理約束 / Governance Invariants

| Invariant | 來源 | 違反後果 |
|---|---|---|
| 算法 = HMAC-SHA256（256-bit key） | V3 §5 | manifest 簽名格式 mismatch → `signature_mismatch` 4-fail-mode 之一 |
| Key 與 live `auth_signing_key` 必隔離 | V3 §5 | live key 被 replay 路徑誤用 → live 偽簽風險 |
| Key path = `$OPENCLAW_SECRETS_DIR/<env>/replay_signing_key` | V3 §5 | path 不對 → engine `key_missing` fail-mode |
| File mode = 0600 owner-only read | OWASP A02:2021 | mode drift → security finding |
| Rotation target = **90 days** | V3 §3 G9 | rotation 過期 → `key_expired` fail-mode |
| Old key retention = **180 days max** | V3 §5 | 過 180d 任何用舊 key 簽的 manifest 永久不可驗證 |
| Server-side only signing；client-supplied signature **rejected** | V3 §5 | 接受 client 簽名 = manifest tamper bypass |
| Verification order: signature first → manifest hash | V3 §5 | 順序錯 → 部分 fail-mode 漏報 |
| Audit 必區分 4 種 fail-mode（`signature_mismatch` / `manifest_hash_mismatch` / `key_missing` / `key_expired`） | V3 §5 | 攻擊歸因不能 |

---

## 3. Initial Deployment（每環境首次部署）

### 3.1 前置 / Preconditions

- [ ] `$OPENCLAW_SECRETS_DIR` 已設置且目錄存在 mode 0700（owned by openclaw runtime user）
- [ ] `$OPENCLAW_SECRETS_DIR/<env>/` 子目錄已存在（per env）
- [ ] V042 `replay_signing_keys` migration 已 land（initial deploy 在 P2a 之後 OR 標記 archive 待補）
- [ ] 1Password vault entry `OpenClaw / replay_signing_key / <env>` 已創建（待寫 fingerprint）
- [ ] 同 env 之 `auth_signing_key` 已存在且 fingerprint 已記（separation 比對基準）

### 3.2 Steps

1. **Generate key** （on Linux trade-core host）:
   ```bash
   sudo -u openclaw bash helper_scripts/operator/generate_replay_signing_key.sh <env>
   ```
2. **Record fingerprint to 1Password**（script 印出的 16-char fingerprint + generated_at + rotation_due_at + retention_until）
3. **Insert key version archive row**（V042 land 後）:
   ```sql
   INSERT INTO replay.replay_signing_keys
     (env, fingerprint, generated_at, rotation_due_at, retention_until, status)
   VALUES
     ('<env>', '<fingerprint>', '<generated_at>', '<rotation_due_at>', '<retention_until>', 'active');
   ```
4. **Restart engines** 帶新 key:
   ```bash
   bash helper_scripts/restart_all.sh
   ```
5. **Post-deploy verify**:
   ```bash
   curl -s http://localhost:8001/api/v1/replay/health/signature
   # expected: {"signature_check":"PASS","fingerprint":"<NEW_FP>","status":"active"}
   ```
6. **Fingerprint match check**（防止舊 ENV 沒重載）:
   ```bash
   curl -s http://localhost:8001/api/v1/replay/health/signature | jq -r '.fingerprint'
   # must equal fingerprint printed by step 1
   ```

---

## 4. Scheduled Rotation（90d 例行）

### 4.1 觸發條件 / Trigger

- `rotation_due_at` 距今 ≤7d → PM 排程
- `rotation_due_at` 已過期 → engine 進入 `key_expired` fail-closed（manifest 全 reject）
- 14d 內必須完成 rotation（防止超 90d 後 manifest backlog 累積）

### 4.2 Steps

1. **Notify operator** PM 簽 schedule（GovernanceHub event 或 Slack）
2. **Generate new key** with force flag:
   ```bash
   OPENCLAW_REPLAY_KEY_FORCE=1 sudo -u openclaw \
     bash helper_scripts/operator/generate_replay_signing_key.sh <env>
   ```
   (script 自動把舊 key 備份到 `${TARGET_KEY}.rotated.<UTC_TS>`)
3. **Mark old key as `retired`**（archive 仍保留 180d 用於驗證舊 manifest）:
   ```sql
   UPDATE replay.replay_signing_keys
   SET status = 'retired', retired_at = NOW()
   WHERE env = '<env>' AND status = 'active' AND fingerprint = '<old_fingerprint>';
   ```
4. **Insert new key row** 同 §3.2 step 3。
5. **Restart engines** 同 §3.2 step 4。
6. **Verify dual key support**（server 保留舊 key 解 archive manifest 用）:
   ```bash
   # 對舊 manifest 用 archived key 驗證
   curl -s http://localhost:8001/api/v1/replay/manifest/verify \
     -H "Content-Type: application/json" \
     -d '{"manifest_id":"<archived_id>","key_fingerprint":"<old_fp>"}'
   # expected: {"signature_check":"PASS"}
   ```
7. **Audit row 寫入** `learning.governance_audit_log`（actor, action='replay_key_rotation', old_fp, new_fp, ts）。

### 4.3 180d Retention Cleanup

舊 key 滿 180d 自動進入 `expired` 狀態，由 cron job（`helper_scripts/cron/replay_key_archive_cleanup.py`，P2a-S2 一併 land）每日跑:
```sql
UPDATE replay.replay_signing_keys
SET status = 'expired'
WHERE retention_until < NOW() AND status = 'retired';
```
進入 `expired` 後，該 key 簽的歷史 manifest 永久不可再驗證 → 任何 `verify` 請求回 `key_expired` fail-mode。

---

## 5. Emergency Rotation（key 洩漏 / 員工離職）

### 5.1 Trigger

- 任何 fingerprint 出現在非授權場合（git diff / log / Slack / email）
- 操作員離職且持有過 secrets dir 讀權
- HSM / vault 完整性事件

### 5.2 Steps（與 §4 差異標 ⚠️）

1. ⚠️ **Quarantine** existing key file 立即:
   ```bash
   sudo mv $OPENCLAW_SECRETS_DIR/<env>/replay_signing_key \
           $OPENCLAW_SECRETS_DIR/<env>/replay_signing_key.QUARANTINED.<UTC_TS>
   sudo chmod 0000 $OPENCLAW_SECRETS_DIR/<env>/replay_signing_key.QUARANTINED.*
   ```
2. ⚠️ **Engine 此時進 `key_missing` fail-closed**（短暫不可用 acceptable）
3. **Generate new key** 同 §4.2 step 2
4. ⚠️ **Mark old key 直接 `compromised`**（不留 180d 寬限）:
   ```sql
   UPDATE replay.replay_signing_keys
   SET status = 'compromised', retired_at = NOW(), retention_until = NOW()
   WHERE env = '<env>' AND fingerprint = '<old_fingerprint>';
   ```
5. ⚠️ **Reject all manifests signed by compromised key**（改 verify endpoint 對 `compromised` 直接回 `key_expired` 即使 retention_until > now()）
6. **Restart engines + Verify** 同 §4.2 step 5/6
7. ⚠️ **Audit row** 寫 `governance_audit_log` action='replay_key_emergency_rotation' + reason
8. ⚠️ **Post-mortem** 24h 內 PM 主導，補 `docs/audits/<date>--replay_key_compromise_postmortem.md`

---

## 6. 4 Fail-Mode 故障處理

| Fail-mode | 觸發條件 | 操作員處置 |
|---|---|---|
| **`key_missing`** | engine 啟動時 `$OPENCLAW_SECRETS_DIR/<env>/replay_signing_key` 不存在 | 跑 §3.2 initial deploy；如過期視同 §4 rotation |
| **`key_expired`** | manifest 用的 fingerprint 在 archive 中 status ∈ {expired, compromised} | 拒絕該 manifest；不要 retro-active 重簽（V3 §5 invariant） |
| **`signature_mismatch`** | manifest body 與 signature 對不上 | 視為 tamper attempt；alert PM；查 client log；不要直接重簽 |
| **`manifest_hash_mismatch`** | manifest body 內聲明的 hash 與 server 重算的 hash 不符（signature 對） | manifest 在簽後被改寫；alert + 拒絕；查 producer code |

每個 fail-mode 必寫 `learning.governance_audit_log` row + dashboard 顯示（V3 §3 G2 audit invariant）。

---

## 7. Rollback Procedure

如新 key 部署後 engine 啟動失敗:

1. **Stop engines**:
   ```bash
   bash helper_scripts/stop_all.sh
   ```
2. **Restore previous key**（rotation backup）:
   ```bash
   sudo cp $OPENCLAW_SECRETS_DIR/<env>/replay_signing_key.rotated.<UTC_TS> \
           $OPENCLAW_SECRETS_DIR/<env>/replay_signing_key
   sudo chmod 0600 $OPENCLAW_SECRETS_DIR/<env>/replay_signing_key
   sudo chown openclaw:openclaw $OPENCLAW_SECRETS_DIR/<env>/replay_signing_key
   ```
3. **Revert archive row** (如已寫):
   ```sql
   UPDATE replay.replay_signing_keys
   SET status = 'active', retired_at = NULL
   WHERE env = '<env>' AND fingerprint = '<old_fingerprint>';
   DELETE FROM replay.replay_signing_keys
   WHERE env = '<env>' AND fingerprint = '<new_fingerprint>'
     AND generated_at > NOW() - INTERVAL '1 hour';
   ```
4. **Restart + verify** 同 §3.2 step 4-6
5. **PM root-cause analysis** 24h 內：為何新 key 部署失敗（permission / path / engine version drift）；補 audit row + 修腳本後再 retry

---

## 8. Audit / 稽核驗證

| 檢查項 | SQL / 命令 | 預期 |
|---|---|---|
| Active key only one per env | `SELECT env, COUNT(*) FROM replay.replay_signing_keys WHERE status='active' GROUP BY env;` | 每 env 恰 1 row |
| 過 90d 仍 active | `SELECT * FROM replay.replay_signing_keys WHERE status='active' AND rotation_due_at < NOW();` | 0 row（如有 = rotation 漏排） |
| 過 180d 還 retired | `SELECT * FROM replay.replay_signing_keys WHERE status='retired' AND retention_until < NOW();` | 0 row（cron 失效告警） |
| Live auth key 與 replay key fingerprint 不重 | (compare two files via openssl dgst) | fingerprint 相異 |
| File mode 嚴 | `stat -c '%a' $OPENCLAW_SECRETS_DIR/<env>/replay_signing_key` | `600` |

每月 PM 跑一次 audit；如有違反 → 升 P0。

---

## 9. 修訂歷史 / Revision History

| 版次 | 日期 | 修訂者 | 摘要 |
|---|---|---|---|
| **v1** | 2026-05-03 | PM (R20-P0-T8) | Wave 1 P0 baseline runbook：initial deploy + 90d rotation + emergency rotation + 4 fail-mode + rollback + audit |

---

## 10. Cross-References

- 上游契約：[V3 baseline](../execution_plan/2026-05-03--ref20_paper_replay_lab_dev_plan_v3.md) §3 G2 + §3 G9 + §5
- Workplan：[Implementation Workplan V1](../execution_plan/2026-05-03--ref20_implementation_workplan_v1.md) §4 Wave 1 R20-P0-T8 + Wave 3 R20-P2a-S1/S2
- Migration ledger：[`sql/migrations/REF-20_RESERVATION.md`](../../sql/migrations/REF-20_RESERVATION.md) V042
- Helper script：[`helper_scripts/operator/generate_replay_signing_key.sh`](../../helper_scripts/operator/generate_replay_signing_key.sh)
- Sibling runbook 風格參考：（暫無；本檔為 `docs/runbooks/` 首檔）
