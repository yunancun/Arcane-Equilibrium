# REF-20 R20-P2a-S1 — Signing Key Rotation Operations (90d cron + 180d cleanup)

**日期 / Date：** 2026-05-03
**Owner：** E1 (sub-agent, Wave 2 Batch 1)
**契約上游 / Upstream contract：**
- `docs/execution_plan/2026-05-03--ref20_implementation_workplan_v1.md` §4 Wave 2 R20-P2a-S1
- `docs/execution_plan/2026-05-03--ref20_wave2_dispatch_v1.md` §3.1 + §4 (P2a security 起頭 row)
- `docs/execution_plan/2026-05-03--ref20_paper_replay_lab_dev_plan_v3.md` §3 G9 + §5
- `docs/runbooks/replay_signing_key_rotation.md` §4.3 + §6
- `helper_scripts/operator/generate_replay_signing_key.sh` (T8 commit `6d9977e` baseline)

**Mode：** IMPL — 4 NEW files + 1 MODIFIED file（runbook §4.3 only）；0 SQL migration / 0 trading.* / 0 IPC / 0 PG schema change。

---

## 0. TL;DR

- 5 NEW + 1 MODIFIED 檔案 land；7/7 pytest PASS；bash -n PASS；py_compile PASS
- 0 hardcoded user-home path；4 MODULE_NOTE block（EN + 中）；0 IPC / 0 dispatch
- V042 absent graceful fallback（rotation 用 filesystem mtime；cleanup 直接 exit 0）
- Idempotent：rotation 同日 dedup audit row；cleanup 用 `WHERE status='retired'` 過濾已 expired
- E2 + E3 review-ready

---

## 1. 修改清單 / File changes

| # | 路徑 / Path | 類型 | mode | 大小 | 說明 |
|---|---|---|---|---:|---|
| 1 | `helper_scripts/cron/replay_key_rotation_check.sh` | NEW | 0755 | 16472 B | Daily 90d rotation 7d-window probe |
| 2 | `helper_scripts/cron/replay_key_archive_cleanup.py` | NEW | 0644 | 13764 B | Daily 180d retention `retired→expired` flip |
| 3 | `helper_scripts/cron/test_replay_key_rotation_check.py` | NEW | 0644 | 8724 B | pytest 4 cases (incl. bash -n + 1 bonus) |
| 4 | `helper_scripts/cron/test_replay_key_archive_cleanup.py` | NEW | 0644 | 12002 B | pytest 3 cases (V042 absent / 0 row / 3 row) |
| 5 | `docs/runbooks/replay_signing_key_rotation.md` | MOD | 0644 | +~1.6KB | §4.3 expanded with §4.3.1/§4.3.2/§4.3.3 |

§3 / §4.1 / §4.2 / §5 / §6 / §7 / §8 / §9 / §10 of runbook — UNCHANGED per task scope.

---

## 2. 關鍵設計 / Key design

### 2.1 V042 absent graceful fallback（雙腳本一致）

V042 (`replay.replay_signing_keys`) reserved per `sql/migrations/REF-20_RESERVATION.md` 但**尚未** land。task spec 要求：「V042 absent 時 graceful fallback（不 crash）」。實作：

| Script | V042 absent 行為 |
|---|---|
| `replay_key_rotation_check.sh` | Fall back to filesystem mtime + 90d rule（mtime > NOW - 83d → ALERT；mtime ≤ NOW - 83d → OK；mtime > NOW - 90d 即必 ALERT）。Rationale：T8 已 land key file 寫入；mtime 即 `generated_at` 近似（rotation 時舊 key 進 backup `*.rotated.<ts>` 不影響 active key 的 mtime）。 |
| `replay_key_archive_cleanup.py` | `_v042_present(cur)` 返 False → log + `return 0` graceful exit。Cron 條目可在 V042 land 之前先安裝；V042 land 後本腳本自動成為 useful（無需重裝 cron）。 |

### 2.2 跨平台 stat / date

CLAUDE.md §七 ★★：「項目必須隨時可以部署在 macOS 上運行」。`replay_key_rotation_check.sh` 用 BSD/GNU 雙分支：

```bash
# stat mtime (BSD vs GNU) / mtime 提取 (BSD vs GNU)
if mtime_epoch=$(stat -f '%m' "$key_path" 2>/dev/null); then
    : # macOS / BSD
elif mtime_epoch=$(stat -c '%Y' "$key_path" 2>/dev/null); then
    : # Linux / GNU
fi

# date (BSD vs GNU) / date 格式 (BSD vs GNU)
if due_at=$(date -u -r "$due_epoch" '+%Y-%m-%dT%H:%M:%SZ' 2>/dev/null); then
    : # macOS / BSD
elif due_at=$(date -u -d "@${due_epoch}" '+%Y-%m-%dT%H:%M:%SZ' 2>/dev/null); then
    : # Linux / GNU
fi
```

Pytest 7/7 PASS 於 `darwin 25.4.0` 證明 macOS branch 工作；Linux branch 經目視 review（既有 `edge_label_backfill_cron.sh` 同模式 production-tested）。

### 2.3 Audit row 用 V035 既有 enum

V035 `event_type` CHECK enum：`'review_live_candidate' / 'lease_grant' / 'lease_auto_revoke' / 'bulk_re_evaluation' / 'audit_write_failed'`。**不擴 enum**（scope creep prevention）。改用：

```sql
-- rotation_check ALERT / cleanup expired flip
INSERT INTO learning.governance_audit_log (event_type, decided_by, payload)
VALUES ('audit_write_failed', 'replay_key_rotation_check_cron|replay_key_archive_cleanup_cron',
        '{"alert_type":"replay_key_rotation_due"|"replay_key_archive_expired", ...}'::jsonb);
```

`alert_type` 走 payload JSONB（V035 column `payload JSONB NULL` 註解：「Forward-compat replay payload」）。Sibling task（後續 sprint）可擴 enum 為專用 `'replay_key_*'` 類型。

### 2.4 Idempotency（同日重跑 0 effect 強制）

- **`replay_key_rotation_check.sh`**：`already_today` query — `payload->>'alert_type'='replay_key_rotation_due' AND payload->>'env'='${env_name}' AND ts >= date_trunc('day', NOW())`，每 env 每天最多 1 audit row（避免 cron 連續 7 天每天寫同 env alert）。
- **`replay_key_archive_cleanup.py`**：`UPDATE ... WHERE status='retired'` 自然過濾掉已 expired row（一旦翻轉，下次同 row 就不再被 RETURNING 回，所以 audit row 也不會重寫）。

### 2.5 PG creds sourcing — 對齊 sibling pattern

延續 2026-05-02 LG5-W3-FUP-3-CRON-ENV 經驗教訓（`linux_bootstrap_db.sh:41-45` 完整 pattern vs `passive_wait_healthcheck_cron.sh:43-44` 簡化 pattern）：

`replay_key_rotation_check.sh` 用完整版（5 POSTGRES_* keys + HOST/PORT fallback + PG_AVAILABLE flag）；當 PG creds 缺失或 `psql` 不在 PATH，fallback 到 filesystem mtime + skip audit row writes — 不 fail loud（cron 仍能正常檢查 mtime；audit log 為 best-effort）。

---

## 3. 治理對照 / Governance alignment

| 項目 | 任務紅線 | 本 IMPL 狀態 |
|---|---|---|
| 0 actual key 生成 | T8 已做，本 task 0 key 生成 | ✅ 兩 script 0 `openssl rand` / 0 file write at key path |
| 0 key 部署 / file move | 不做 deploy（runbook §3 說明 operator 手動）| ✅ 兩 script 不 mv / 不 chmod key file |
| 不寫 trading.* / live order | 0 trading.* INSERT/UPDATE | ✅ 0 出現 `trading.` 字串 |
| Idempotent | 重跑 0 effect | ✅ §2.4 兩個機制 |
| V042 absent graceful fallback | 不 crash | ✅ §2.1 |
| 雙語 comment | MODULE_NOTE EN + 中 / docstring 雙語 / inline 雙語 | ✅ 4 個 MODULE_NOTE block；inline 雙語遍布 |
| 不依賴 IPC / dispatch / live exchange / GovernanceHub | 純 PG + filesystem | ✅ 0 import IPC client / 0 ai_service / 0 GovernanceHub |
| 不引入新 PG schema | V042 預留不 IMPL | ✅ 0 CREATE TABLE / 0 ALTER；只 query existing tables |
| mode 0755 shell / 0644 Python | 嚴守 | ✅ 見 §1 表 |
| CLAUDE.md §七 跨平台兼容 | macOS + Linux 雙跑 | ✅ §2.2 BSD/GNU 雙分支 |
| CLAUDE.md §七 雙語注釋 | 每個新 function/class/module 雙語 | ✅ MODULE_NOTE × 4 + docstring 雙語 + inline 雙語 |
| CLAUDE.md §七 路徑不硬編碼 | 0 `/home/ncyu` / `/Users/<name>` 字面值 | ✅ grep 0 hit（runbook example 內含絕對路徑為 cron crontab 範例不在 source code，符合「歷史 worklog / dated snapshot / 政策反例引用不在此限」例外）|

---

## 4. 測試結果 / Test results

```
$ python3 -m pytest helper_scripts/cron/test_replay_key_rotation_check.py \
                    helper_scripts/cron/test_replay_key_archive_cleanup.py -v

=== 7 passed in 0.12s ===

helper_scripts/cron/test_replay_key_rotation_check.py::test_wrapper_exists_and_syntax_clean PASSED
helper_scripts/cron/test_replay_key_rotation_check.py::test_v042_absent_mtime_within_grace_exits_0_silent PASSED
helper_scripts/cron/test_replay_key_rotation_check.py::test_v042_absent_mtime_past_due_exits_1_alert PASSED
helper_scripts/cron/test_replay_key_rotation_check.py::test_secrets_dir_missing_exits_2 PASSED  ← bonus coverage
helper_scripts/cron/test_replay_key_archive_cleanup.py::test_v042_absent_exits_0_graceful PASSED
helper_scripts/cron/test_replay_key_archive_cleanup.py::test_v042_present_zero_rows_past_retention PASSED
helper_scripts/cron/test_replay_key_archive_cleanup.py::test_v042_present_three_rows_past_retention PASSED
```

Task spec 要求 6 test，本 IMPL 提供 7（rotation_check 4 + cleanup 3）— 多出的 `test_secrets_dir_missing_exits_2` 補 wrapper exit 2 路徑覆蓋。

### Static checks

```
$ bash -n helper_scripts/cron/replay_key_rotation_check.sh && echo OK
OK

$ python3 -m py_compile helper_scripts/cron/replay_key_archive_cleanup.py \
                         helper_scripts/cron/test_replay_key_rotation_check.py \
                         helper_scripts/cron/test_replay_key_archive_cleanup.py && echo OK
OK

$ grep -nE '/home/ncyu|/Users/[^/]+' helper_scripts/cron/replay_key_*.{sh,py} \
                                       helper_scripts/cron/test_replay_key_*.py
(no output — 0 hardcoded user-home in source)
```

---

## 5. 不確定之處 / Ambiguities & escalation requests

下列點建議 PM / E2 / E3 review 時拍板：

### 5.1 Audit log enum 暫用 `audit_write_failed` 是否合適？

V035 `event_type` CHECK 不含 `replay_key_*`。本 IMPL 用 `audit_write_failed` + `payload.alert_type='replay_key_*'` 載入。**alternative**：等 sibling task 擴 enum（V0XX 加 `'replay_key_rotation_alert' / 'replay_key_archive_expired'`），那時 audit row 切回專用 type。**目前 risk**：若 V035 既有 alarm 規則 query `WHERE event_type='audit_write_failed'`（非 replay 用途），會誤觸發 — 但 alarm 規則應 always include `payload->>...` filter（既有 LG-5 pattern 就是這樣）。

**建議**：本 sprint 接受暫用法；sibling task R20-P2a-S6（evidence_source_tier finalize migration） 同步擴 enum；E3 review 看是否需 inline NOTE 在 V035 column comment。

### 5.2 V042 schema 預期 — 雙腳本對欄位假設

`replay.replay_signing_keys` V042 預期欄位（per `REF-20_RESERVATION.md` V042 row + runbook §3.2 step 3）：

```sql
env TEXT,                      -- 'paper' / 'demo' / 'live'
fingerprint TEXT,              -- 16-char SHA256 prefix
generated_at TIMESTAMPTZ,
rotation_due_at TIMESTAMPTZ,   -- generated_at + 90d
retention_until TIMESTAMPTZ,   -- generated_at + 180d
status TEXT,                   -- 'active' / 'retired' / 'expired' / 'compromised'
retired_at TIMESTAMPTZ NULL    -- when status flipped to retired/expired
```

兩腳本對該 schema 假設：
- rotation_check：`SELECT rotation_due_at FROM ... WHERE env=? AND status='active'`
- cleanup：`UPDATE ... SET status='expired' WHERE status='retired' AND retention_until<NOW() RETURNING env, fingerprint, retention_until`

V042 land 時若 PA / E1 採用不同欄位名（如 `expires_at` vs `rotation_due_at`），須回頭修這兩腳本。**建議**：V042 IMPL 任務同 sprint，對齊欄位名稱前 PM 統一；本 IMPL 不 block。

### 5.3 Cron monitoring system — 任務問本任務寫了什麼，目前我採取 pragmatic 立場：

runbook §4.3.2 列了 4 種 monitoring 機制（cron mailer / journald / log file 直查 / healthcheck integration），但「Healthcheck integration」目前未 IMPL（只列 placeholder）。**建議**：sibling task R20-P2a-S6 / R20-P3a-Q6 補 `check_replay_signing_key_rotation()` 進 `helper_scripts/db/passive_wait_healthcheck.py`（既有 42 check 模式）。本 IMPL 不擅自加（scope creep）。

### 5.4 ROTATION_DAYS 與 ALERT_THRESHOLD_DAYS 為 hardcoded

`replay_key_rotation_check.sh` 內 `ROTATION_DAYS=90 / ALERT_THRESHOLD_DAYS=7` 是 hardcoded 常量。**Alternative**：env var override（如 `OPENCLAW_REPLAY_ROTATION_DAYS=90`）。**未實作 reasoning**：runbook §4 + V3 §3 G9 invariant 將 90/180/7 寫為 spec 級常量；env var 反而給 operator 改 spec 的可能。**建議**：sibling task QA discussion 結論 — 若決定為 spec invariant，本 hardcoded 即正確；若決定為 cluster-tunable，補 env var override。

---

## 6. Operator / Reviewer 下一步

1. **E2 review** — code review focus：bash strict mode + 跨平台 stat/date + Python type hints + idempotency + 0 IPC/dispatch
2. **E3 review** — security focus：governance_audit_log payload 不含 secrets / PG creds sourcing 是否複用既有 sibling pattern / fail-mode 對齊 runbook §6 4 fail-mode
3. **E4 regression** — 本 task 0 修改既有路徑；regression scope 僅新檔。建議 E4 在 Linux trade-core 跑 dry-run（產生 fake key file，cron 觀察 24h）。
4. **PM commit** — 待 E2 + E3 + E4 三方 PASS 後合 commit；commit message draft：
   ```
   feat(replay): signing key 90d rotation + 180d retention cron + tests (Wave 2 P2a-S1)
   
   - replay_key_rotation_check.sh: daily 7d-window probe (filesystem mtime fallback)
   - replay_key_archive_cleanup.py: daily 180d retention flip (V042 graceful absent)
   - 7 pytest cases PASS
   - runbook §4.3 expanded with installation/monitoring/SQL-equivalent
   - 0 IPC/dispatch/trading mutation; idempotent; mode 0755/0644 strict
   
   契約：workplan §4 Wave 2 R20-P2a-S1 / runbook §4.3 / V3 §3 G9 + §5
   ```
5. **Cron 安裝**（PM 決議後 operator 在 Linux trade-core 手動）：
   ```bash
   crontab -e
   # 加：
   0  9 * * * /home/ncyu/BybitOpenClaw/srv/helper_scripts/cron/replay_key_rotation_check.sh
   30 9 * * * /home/ncyu/BybitOpenClaw/srv/helper_scripts/cron/replay_key_archive_cleanup.py
   ```

---

## 7. Cross-References

- 上游：[Workplan V1](../../../execution_plan/2026-05-03--ref20_implementation_workplan_v1.md) §4 Wave 2 R20-P2a-S1
- 上游：[Wave 2 dispatch](../../../execution_plan/2026-05-03--ref20_wave2_dispatch_v1.md) §3.1
- V3 baseline：[V3](../../../execution_plan/2026-05-03--ref20_paper_replay_lab_dev_plan_v3.md) §3 G9 + §5
- Runbook：[`docs/runbooks/replay_signing_key_rotation.md`](../../../runbooks/replay_signing_key_rotation.md) §4.3
- Migration ledger：[`sql/migrations/REF-20_RESERVATION.md`](../../../../sql/migrations/REF-20_RESERVATION.md) V042
- Sibling pattern：`helper_scripts/cron/edge_label_backfill_cron.sh`（PG creds sourcing + lock pattern）
- Sibling pattern：`helper_scripts/cron/test_edge_label_backfill_cron_env.py`（pytest sealed env style）
- Sibling pattern：`helper_scripts/db/passive_wait_healthcheck/db.py`（DSN builder）

---

E1 IMPLEMENTATION DONE: 待 E2 + E3 審查（report path: `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-03--ref20_p2a_s1_signing_key_rotation_cron.md`）
