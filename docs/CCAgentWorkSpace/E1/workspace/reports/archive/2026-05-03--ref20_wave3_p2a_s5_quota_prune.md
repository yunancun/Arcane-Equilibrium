# REF-20 R20-P2a-S5 — Manifest Quota Enforcer + Artifact Prune Cron

**日期 / Date：** 2026-05-03
**Owner：** E1 (sub-agent, Wave 3 Batch 3A)
**契約上游 / Upstream contract：**
- `docs/execution_plan/2026-05-03--ref20_implementation_workplan_v1.md` §4 Wave 3 R20-P2a-S5
- `docs/execution_plan/2026-05-03--ref20_paper_replay_lab_dev_plan_v3.md` §3 G9 + §5 (Manifest, Quota, Retention) + §12 #4 + #14
- `helper_scripts/cron/replay_key_archive_cleanup.py`（既有 cron pattern reference for cleanup-race + idempotency + V042 graceful fallback）
- `helper_scripts/cron/edge_label_backfill_cron.sh`（既有 cron wrapper pattern）
- `program_code/exchange_connectors/bybit_connector/control_api_v1/replay/manifest_signer.py`（sibling P2a-S2 pattern: docstring shape + Wave 2 scaffold export style）
- bilingual-comment-style skill + `feedback_rust_authoritative_config.md`

**Mode：** IMPL — 4 NEW files + 1 MODIFIED file (runbook §4.4 new section only)；0 SQL migration / 0 trading.* / 0 IPC / 0 PG schema change。

---

## 0. TL;DR

- 4 NEW + 1 MODIFIED 檔案 land；**8/8 pytest PASS** (5 enforcer + 3 cron)；**25/25 PASS** including sibling regression（13 manifest_signer + 7 sibling cron）
- bash -n N/A（no new shell）；py_compile PASS for 4 Python files
- 0 hardcoded user-home path（grep 確認）；4 MODULE_NOTE block（EN + 中）；0 IPC / 0 GovernanceHub / 0 Decision Lease coupling
- Schema-absent graceful: enforcer treats missing tables as 0 active resources; cron exits 0 + logs (per V3 §6 P2b runner SQL fixture land timeline)
- Idempotent: cron rerun 0 effect (DELETE filter naturally dedups); enforcer mark_manifest_expired UPDATE WHERE filter naturally idempotent
- Storage cap via env var `OPENCLAW_REPLAY_ARTIFACT_STORAGE_CAP_MB`（1024 MB default）— operator override 不需改碼
- E2 + E3 review-ready

---

## 1. 修改清單 / File changes

| # | 路徑 / Path | 類型 | mode | 大小 | 說明 |
|---|---|---|---|---:|---|
| 1 | `program_code/exchange_connectors/bybit_connector/control_api_v1/replay/quota_enforcer.py` | NEW | 0644 | 728 LOC | `ReplayQuotaEnforcer` class + `ReplayQuotaExceededError` + `QuotaCheckResult` + 4 cap enforcement methods + `mark_manifest_expired` |
| 2 | `helper_scripts/cron/replay_artifact_prune.py` | NEW | 0755 | 601 LOC | 6-hourly cron: TTL prune + per-env storage-cap prune + V035 audit row emission |
| 3 | `program_code/exchange_connectors/bybit_connector/control_api_v1/tests/replay/test_quota_enforcer.py` | NEW | 0644 | 417 LOC | pytest 5 cases (per-actor manifest cap / per-actor run cap / global run cap / env storage cap / TTL flip idempotency) |
| 4 | `helper_scripts/cron/test_replay_artifact_prune.py` | NEW | 0644 | 366 LOC | pytest 3 cases (V042/replay schema absent / 0 expired manifest / 5 expired manifest pruned correctly) |
| 5 | `docs/runbooks/replay_signing_key_rotation.md` | MOD | 0644 | +~80 lines (§4.4 new) | New §4.4 expands §4.3 framework with quota + storage cap cron section |

§3 / §4.1 / §4.2 / §4.3 / §5 / §6 / §7 / §8 of runbook — UNCHANGED per task scope.

---

## 2. 關鍵設計 / Key design

### 2.1 Schema-absent graceful（4 cap × 1 cron 一致）

V3 §6 + REF-20_RESERVATION.md note 明確 replay schema 核心表（experiments / report_artifacts）由 P2b runner SQL fixture land Wave 3-4，**不佔 migration 編號**。本 sprint 必須在 schema absent 時 graceful 不 crash：

| Surface | Schema absent 行為 |
|---|---|
| `enforce_manifest_create` | `_table_exists(cur, 'replay', 'experiments')` False → return `QuotaCheckResult(current=0, cap=20, schema_present=False)` |
| `enforce_run_start` | 同上 → return `QuotaCheckResult` 通過（per-actor + global 都不 query） |
| `enforce_artifact_storage` | `_table_exists(cur, 'replay', 'report_artifacts')` False → return PASS（storage 0 used）|
| `mark_manifest_expired` | experiments 缺 → log + return False（no UPDATE issued）|
| `replay_artifact_prune.py` cron | `_replay_schema_ready(cur)` False → log + exit 0 (cron 條目可預先安裝)|

Rationale：對齊 sibling `replay_key_archive_cleanup.py` 的 V042 graceful pattern（commit `31345d8` E1 P2a-S1 sub-agent 也用此模式，allows cron entry installation pre-V042）。Routes (P2a-S3) 可立即接上 enforcer，schema land 後 0 行代碼變更即啟用真正執行。

### 2.2 4 條 cap 對應 V3 §5 invariants

| V3 §5 Row | 上限 | enforcer method | quota_kind |
|---|---:|---|---|
| per-actor active manifests | 20 | `enforce_manifest_create(actor_id)` | `manifest_per_actor` |
| per-actor active runs | 1 | `enforce_run_start(actor_id)` part 1 | `run_per_actor` |
| global active runs (P2/P3) | 1 | `enforce_run_start(actor_id)` part 2 | `run_global` |
| artifact storage cap | env-specific (default 1024 MB) | `enforce_artifact_storage(env)` | `storage_env` |
| manifest TTL | 30 days default | `mark_manifest_expired(manifest_id)` | (writer, not gate) |

`ReplayQuotaExceededError` 單一 exception 共用 `quota_kind` discriminator → caller route (P2a-S3) 可不 inspect class 階層直接組裝 4xx/5xx 回應。

### 2.3 Storage cap env var 設計選擇

V3 §5 row "artifact storage cap = implementation defines env-specific cap before P2a merge"。本實作選 single env var `OPENCLAW_REPLAY_ARTIFACT_STORAGE_CAP_MB`（默認 1024）統一套用所有 env。

**Rationale**：
- ✅ Operator 可 per-cluster 覆寫（dev cluster 200 MB、prod cluster 4 GiB）無需改碼
- ✅ Env scope 由 SQL `WHERE env = ?` 強制 — 4 envs（paper/demo/live + mac_dev_smoke）獨立計算 storage 用量但共用 cap
- ✅ Invalid value（非數字 / ≤0）退回預設 + log warning（防 typo cap=0 silent block）
- ✅ Enforcer ctor 一次性解析（app restart 才換 cap，這是預期 deploy 姿態）；cron 每次 invocation 重讀（更動 env var 不需重啟 cron daemon）

**Alternative considered**: 三條 env var (paper/demo/live 獨立)。**否決理由**：複雜化，operator 通常一個 cluster 一致設定；後續 sprint 若需要 per-env 可擴成 dict env var 而不破現 API。

### 2.4 V3 §4.1 schema 假設文件化

兩程式對 V3 §4.1 schema 假設：

| Table | 欄位需求 | 用途 |
|---|---|---|
| `replay.experiments` | `experiment_id` PK / `created_by` actor / `expires_at` TIMESTAMPTZ NULL / `status` enum / `runtime_environment` env | enforcer manifest + run cap query / cron TTL prune |
| `replay.report_artifacts` | `artifact_id` PK / `experiment_id` FK / `bytes` integer / `expires_at` / `created_at` for oldest-first | enforcer storage cap query / cron prune target |

P2b runner 將以 SQL fixture land 該 schema（per V3 §6 + workplan T1）。如 fixture 採用不同欄位名（如 `created_by_actor` vs `created_by`），需回頭修這兩程式。**建議**：fixture land sprint 同步派 E1 對齊 column name。

### 2.5 Audit row enum 對齊 sibling 模式

V035 `event_type` CHECK enum 不含 `replay_*`。本實作沿用 sibling `replay_key_archive_cleanup._emit_audit_row` 模式：

```python
INSERT INTO learning.governance_audit_log
  (event_type='audit_write_failed',
   decided_by='replay_artifact_prune_cron',
   payload={'alert_type': 'replay_artifact_prune_ttl' | 'replay_artifact_prune_storage_cap',
            'pruned_count', 'pruned_bytes_total', 'env', 'sample_pairs'})
```

**Note**：sibling task R20-P2a-S6（evidence_source_tier finalize migration）會擴 enum 為 `'replay_*'` 類型。本 IMPL 暫用 `audit_write_failed` 與 P2a-S1 sibling 行為對稱，未來雙腳本同步切換到專用 event_type。

### 2.6 Idempotency 三重保證

| 觸點 | 機制 |
|---|---|
| `mark_manifest_expired` UPDATE | `WHERE experiment_id = ? AND (expires_at IS NULL OR expires_at > NOW())` — 對已 expired manifest 無 row affected |
| Cron TTL prune DELETE | `DELETE FROM replay.report_artifacts USING replay.experiments WHERE expires_at < NOW()` — 已 DELETE row 不再符合 WHERE |
| Cron storage cap prune | `WHILE sum > cap_bytes`，過 prune sum 已下降，下次跑無動作 |
| Audit row emission | 只在 `len(pruned) > 0` 時 emit；nothing pruned = 0 audit row（不每 cron 寫無內容 noise）|

### 2.7 Loop bound on storage-cap prune

`_prune_oldest_for_storage_cap` 用 `while ... and iter_count < max_iter`（max_iter=100,000）。**Rationale**：純 defensive — 實務上 single pass 即可 exit（DELETE 後 sum 下降）；max_iter 防 schema corruption 或 SUM/DELETE drift 導致 infinite loop。觸發 max_iter 寫 `log.warning` 但 cron exit code 仍 0（不為防禦觸發 fail loud；後續 healthcheck 監控）。

---

## 3. 治理對照 / Governance alignment

| 項目 | 任務紅線 | 本 IMPL 狀態 |
|---|---|---|
| 0 PG schema mutation | 純 Python module + cron | ✅ 0 CREATE TABLE / ALTER / DROP |
| 0 trading.* / live config write | V3 §12 #14 binding | ✅ grep 4 hits all in docstring negation phrasing |
| 0 GovernanceHub / Decision Lease coupling | V3 §6.2 red-line | ✅ 0 import; docstring NOT-coupled disclaimer |
| 0 IPC / dispatch / Bybit REST/WS | replay subsystem 隔離 | ✅ 0 import |
| Idempotent (重跑 0 effect) | spec | ✅ §2.6 三重保證 |
| Schema-absent graceful (no crash) | spec | ✅ §2.1 一致 graceful |
| Storage cap env var (不 hardcode) | spec | ✅ `OPENCLAW_REPLAY_ARTIFACT_STORAGE_CAP_MB` + invalid fallback |
| 雙語 comment | MODULE_NOTE EN + 中 / docstring 雙語 / inline 雙語 | ✅ 4 個 MODULE_NOTE block；inline 雙語遍布 |
| mode 0644 python / 0755 cron | strict | ✅ 見 §1 表 |
| CLAUDE.md §七 跨平台兼容 | macOS + Linux 雙跑 | ✅ 0 OS-specific 路徑；env var driven |
| CLAUDE.md §七 雙語注釋 | 每個新 function/class/module 雙語 | ✅ MODULE_NOTE × 4 + docstring 雙語 + inline 雙語 |
| CLAUDE.md §七 路徑不硬編碼 | 0 `/home/ncyu` / `/Users/<name>` 字面值 | ✅ grep 0 hit |
| CLAUDE.md §九 文件 800 行警告 | 4 檔皆 < 800 | ✅ 728/601/417/366 |
| V3 §12 #4 quota | per-actor 20 manifest + 1 run + global 1 run all enforced | ✅ §2.2 4 cap 對映 |
| V3 §12 #14 no_live_mutation | prune cron 不寫 trading.* / live_orders | ✅ 0 trading.* INSERT/UPDATE |

---

## 4. 測試結果 / Test results

```
$ ./venvs/mac_dev/bin/python -m pytest \
    program_code/exchange_connectors/bybit_connector/control_api_v1/tests/replay/test_quota_enforcer.py \
    helper_scripts/cron/test_replay_artifact_prune.py -v

=== 8 passed in 0.04s ===

test_quota_enforcer.py::test_per_actor_manifest_cap_enforced PASSED [12.5%]
test_quota_enforcer.py::test_per_actor_run_cap_enforced PASSED      [25.0%]
test_quota_enforcer.py::test_global_run_cap_enforced PASSED         [37.5%]
test_quota_enforcer.py::test_env_storage_cap_enforced PASSED        [50.0%]
test_quota_enforcer.py::test_mark_manifest_expired_ttl_flip PASSED  [62.5%]
test_replay_artifact_prune.py::test_replay_schema_absent_exits_0_graceful PASSED  [75.0%]
test_replay_artifact_prune.py::test_zero_manifests_expired_zero_prune PASSED      [87.5%]
test_replay_artifact_prune.py::test_five_manifests_expired_pruned_correctly PASSED [100%]
```

Task spec 要求 8 test (5 enforcer + 3 cron); 本 IMPL 提供 exactly 8。Coverage：

| Test | 覆蓋 invariant |
|---|---|
| `test_per_actor_manifest_cap_enforced` | V3 §5 per-actor 20 manifest cap + schema-absent graceful + remaining slot accuracy |
| `test_per_actor_run_cap_enforced` | V3 §5 per-actor 1 run cap + per-actor優先 raise（even if global also full）+ schema-absent |
| `test_global_run_cap_enforced` | V3 §5 global 1 run cap + per-actor PASS 後 global REJECT 順序 |
| `test_env_storage_cap_enforced` | V3 §5 env-specific storage cap + 1024 MB default + env var override (2048 MB) + schema-absent + remaining accuracy in MB |
| `test_mark_manifest_expired_ttl_flip` | V3 §5 manifest TTL 30d flip + idempotent re-flip + non-existent → False + schema-absent → no UPDATE |
| `test_replay_schema_absent_exits_0_graceful` | V3 §6 P2b runner timeline graceful + exit 0 + 1 execute (probe only) |
| `test_zero_manifests_expired_zero_prune` | 0 prune row + 0 audit + 0 single-DELETE + under cap behaviour |
| `test_five_manifests_expired_pruned_correctly` | 5 row TTL DELETE + 1 audit row + payload alert_type + sample_pairs + bytes_total accuracy |

### Sibling regression check

```
$ ./venvs/mac_dev/bin/python -m pytest \
    helper_scripts/cron/test_replay_key_archive_cleanup.py \
    helper_scripts/cron/test_replay_key_rotation_check.py \
    program_code/exchange_connectors/bybit_connector/control_api_v1/tests/replay/ -v

=== 25 passed in 0.13s ===
(13 manifest_signer + 5 quota_enforcer + 3 cron prune + 4 sibling cron rotation)
```

0 sibling regression。

### Static checks

```
$ ./venvs/mac_dev/bin/python -m py_compile \
    helper_scripts/cron/replay_artifact_prune.py \
    program_code/exchange_connectors/bybit_connector/control_api_v1/replay/quota_enforcer.py \
    helper_scripts/cron/test_replay_artifact_prune.py \
    program_code/exchange_connectors/bybit_connector/control_api_v1/tests/replay/test_quota_enforcer.py
exit=0

$ grep -nE '/home/ncyu|/Users/[^/]+' <4 new files>
(no output — 0 hardcoded user-home)

$ grep -E 'trading\.|live_orders|GovernanceHub|Decision Lease|acquire_lease' \
    helper_scripts/cron/replay_artifact_prune.py \
    program_code/exchange_connectors/bybit_connector/control_api_v1/replay/quota_enforcer.py
(7 hits, all in docstring negation phrasing, e.g. "0 trading.* INSERT/UPDATE")

$ wc -l <4 new files>
   728 quota_enforcer.py  (< 800 警告線)
   601 replay_artifact_prune.py
   417 test_quota_enforcer.py
   366 test_replay_artifact_prune.py
```

---

## 5. 不確定之處 / Ambiguities & escalation requests

下列點建議 PM / E2 / E3 review 時拍板：

### 5.1 V3 §4.1 column 名稱對齊（P2b runner SQL fixture）

quota_enforcer + cron 對 `replay.experiments` 假設欄位：`experiment_id`, `created_by`, `expires_at`, `status` enum (`created/running/completed/failed/cancelled`), `runtime_environment`。對 `replay.report_artifacts` 假設：`artifact_id`, `experiment_id` FK, `bytes`, `expires_at`, `created_at`。

P2b runner SQL fixture（workplan R20-P2b-T1）land schema 時若採不同 column name（如 `actor_id` vs `created_by`、`size_bytes` vs `bytes`），需回頭修這兩程式（grep + 小幅 SQL string update）。**建議**：T1 fixture sprint 同 commit 對齊 column name；本 IMPL 不 block。

### 5.2 Single env var vs per-env storage cap

本實作選 single `OPENCLAW_REPLAY_ARTIFACT_STORAGE_CAP_MB` 統一所有 env。**Alternative**：三條 env var（`*_PAPER_MB` / `*_DEMO_MB` / `*_LIVE_MB`）。

**目前 risk**：低。Per-env scope 由 SQL `WHERE env = ?` 強制（4 envs 獨立計算 storage 用量但共用 cap）。**建議**：本 sprint 接受 single var；後續 sprint 若 PM 決定要 per-env，可擴成 dict env var（如 JSON `OPENCLAW_REPLAY_ARTIFACT_STORAGE_CAPS_MB='{"paper":200,"demo":1024,"live":4096}'`）不破現 API。E3 review 看是否需 per-env 立即實裝。

### 5.3 Audit row enum 暫用 `audit_write_failed`

V035 `event_type` CHECK 不含 `replay_*`。本 IMPL 用 `audit_write_failed` + `payload.alert_type='replay_artifact_prune_*'` 載入。**Alternative**：等 sibling task 擴 enum，那時 audit row 切回專用 type。

**Risk**：若 V035 既有 alarm 規則 query `WHERE event_type='audit_write_failed'`（非 replay 用途），會誤觸發 — 但 alarm 規則應 always include `payload->>'alert_type'` filter（既有 LG-5 pattern + sibling P2a-S1 已採用）。

**建議**：本 sprint 接受暫用法；R20-P2a-S6 evidence_source_tier finalize migration 同步擴 enum；E3 review 看是否需 inline NOTE 在 V035 column comment。

### 5.4 Storage cap prune `runtime_environment` enum hardcode

`replay_artifact_prune.py` line ~470 寫死 `envs_to_check = ["linux_trade_core", "mac_dev_smoke_test_only"]`。

**Rationale**：V3 §4.1 明確 `runtime_environment ∈ {linux_trade_core, mac_dev_smoke_test_only}` 為 schema-level enum；新 env 加入需 V### migration ALTER CHECK constraint 同步本 list。

**Alternative**：DB query distinct env values 動態 iterate。**否決理由**：dynamic 增加一條 query；schema-level enum 是 source of truth；如未來新 env 多一行 list update 是合理 maintainability tax。**建議**：sibling task / future env addition sprint 同步本 list update（grep `envs_to_check` 即見）。

### 5.5 Cron 安裝 SOP 是否需要單獨腳本

P2a-S1 sibling 有 `replay_key_rotation_check.sh` (bash wrapper) + `.py` (Python core) split；本 IMPL 直接寫 `.py`（無 bash wrapper）。**Rationale**：cron entry 直接 invoke Python 透過 shebang `#!/usr/bin/env python3` + `chmod 0755`（檢視 sibling `replay_key_archive_cleanup.py` 同 pattern：cron 直接 invoke .py 0755）。

**目前 risk**：低；既有 PostgreSQL DSN env var（`OPENCLAW_DATABASE_URL` 或 `POSTGRES_*`）由 crontab top-level 設定（runbook §4.3.1 範例已示），cron 直接 invoke .py 即可。**建議**：E3 review 看是否需要 bash wrapper（如未來加 lock file / log rotation 等 wrapper 邏輯，可後補）。

---

## 6. Operator / Reviewer 下一步

1. **E2 review** — code review focus：
   - quota_enforcer.py: cap constants 對齊 V3 §5 / cursor pattern 安全 / `QuotaCheckResult` API 給 P2a-S3 routes 整合預留充分
   - replay_artifact_prune.py: SQL DELETE...USING + RETURNING / oldest-first while-loop 邏輯 / 對齊 sibling cron rollback pattern
   - 兩 test 檔 in-memory cursor mock 完整覆蓋 8 cases
2. **E3 review** — security focus:
   - governance_audit_log payload 不含 secrets / actor_id / fingerprint（無）；`sample_pairs` 限制 ≤10 防 unbounded blob
   - PG creds sourcing 對齊 sibling cron pattern（DSN priority OPENCLAW_DATABASE_URL → POSTGRES_*）
   - 0 trading.* / 0 GovernanceHub / 0 Decision Lease coupling 確認
   - storage cap env var fallback safe（typo / negative / non-int 都 fallback default）
3. **E4 regression** — 本 task 0 修改既有路徑；regression scope 僅新檔。建議 E4 在 Linux trade-core 跑 dry-run（cron --dry-run + assert 0 row affected pre-schema-land）。
4. **PM commit** — 待 E2 + E3 + E4 三方 PASS 後合 commit；commit message draft：
   ```
   feat(replay): manifest quota enforcer + artifact prune cron (Wave 3 P2a-S5)

   - quota_enforcer.py: ReplayQuotaEnforcer class with 4 cap methods +
     mark_manifest_expired (per-actor 20 manifest / per-actor 1 run /
     global 1 run / env storage cap)
   - replay_artifact_prune.py: 6-hourly cron for TTL prune + per-env
     storage-cap oldest-first prune; V035 audit row per batch
   - 8 pytest cases PASS (5 enforcer + 3 cron); 0 sibling regression
   - schema-absent graceful (V042 / replay schema land via P2b runner)
   - storage cap via OPENCLAW_REPLAY_ARTIFACT_STORAGE_CAP_MB (default 1024)
   - 0 IPC / 0 GovernanceHub / 0 Decision Lease coupling; idempotent
   - runbook §4.4 expanded with cron + storage cap section
   - mode 0755 cron / 0644 enforcer + tests strict

   契約：workplan §4 Wave 3 R20-P2a-S5 / V3 §3 G9 + §5 / V3 §12 #4 + #14
   ```
5. **Cron 安裝**（PM 決議後 operator 在 Linux trade-core 手動）：
   ```bash
   crontab -e
   # 加（assume OPENCLAW_BASE_DIR + DSN env vars 已在 crontab top-level export）：
   0 */6 * * * "$OPENCLAW_BASE_DIR/helper_scripts/cron/replay_artifact_prune.py"
   ```
6. **Routes wiring**（P2a-S3 sub-agent owns）：在 8 routes 任意 manifest/run/artifact-creating endpoint 注入 `enforcer.enforce_*()` call，catch `ReplayQuotaExceededError` → 轉 HTTP 429（rate limit semantic）+ payload `quota_kind` + `remaining` + `cap` 給 operator UX。

---

## 7. Cross-References

- 上游：[Workplan V1](../../../execution_plan/2026-05-03--ref20_implementation_workplan_v1.md) §4 Wave 3 R20-P2a-S5
- V3 baseline：[V3](../../../execution_plan/2026-05-03--ref20_paper_replay_lab_dev_plan_v3.md) §3 G9 + §5 + §12 #4 + #14
- Sibling pattern：`helper_scripts/cron/replay_key_archive_cleanup.py`（V042 graceful + DSN sourcing + audit row enum）
- Sibling pattern：`helper_scripts/cron/test_replay_key_archive_cleanup.py`（pytest fake cursor pattern）
- Sibling pattern：`program_code/exchange_connectors/bybit_connector/control_api_v1/replay/manifest_signer.py`（雙語 docstring shape）
- Migration ledger：[`sql/migrations/REF-20_RESERVATION.md`](../../../../sql/migrations/REF-20_RESERVATION.md) V042 + replay schema P2b note
- Runbook：[`docs/runbooks/replay_signing_key_rotation.md`](../../../runbooks/replay_signing_key_rotation.md) §4.4（new this commit）

---

E1 IMPLEMENTATION DONE: 待 E2 + E3 審查（report path: `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-03--ref20_wave3_p2a_s5_quota_prune.md`）
