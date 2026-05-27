# E1 — P0-OPS-4 GAP-D Track A round 2 — check_pg_dump_freshness 主入口 + passive_wait wire

**日期**: 2026-05-27
**任務**: 補完 round 1 缺的 2 deliverable（FA acceptance §E #7 阻 first-day live）
**狀態**: IMPL DONE，待 E2 sign-off

---

## 1. 任務摘要

Round 1（2026-05-27 早些 land）已交付：
- `srv/helper_scripts/cron/install_pg_dump_cron.sh`（96 LOC）
- `srv/helper_scripts/cron/trading_ai_pg_dump_cron.sh`（181 LOC）含 EXCLUDE evaluations + governance_audit_log INSERT + retention 30d
- `srv/helper_scripts/cron/verify_pg_dump.sh`（129 LOC）Bash sidecar，5 check
- `srv/sql/migrations/V113__governance_audit_log_pg_dump_event_types.sql`（V053/V098 race-free pattern + Guard A/B）

Round 2 需補：
1. **A1**: `helper_scripts/canary/healthchecks/check_pg_dump_freshness.py` Python 主入口 7-check
2. **A2**: `passive_wait_healthcheck.sh` wire `[80]` check function（per FA §E #7「7 check (原 6 + pg_dump_freshness)」）
3. **A3**: SCRIPT_INDEX 補 entry
4. **A4**: Mac syntax + Linux empirical test

---

## 2. 修改清單

### 新增（1 個檔）

| 路徑 | LOC |
|---|---|
| `srv/helper_scripts/canary/healthchecks/check_pg_dump_freshness.py` | 616 |

### 修改（3 個檔）

| 路徑 | 改動行數 |
|---|---|
| `srv/helper_scripts/db/passive_wait_healthcheck/checks_cron_heartbeat.py` | +108 LOC（217→325）：新增 `check_80_pg_dump_freshness()` wrapper + 更新 module docstring [75]-[79]→[75]-[80] + 更新 `__all__` |
| `srv/helper_scripts/db/passive_wait_healthcheck/runner.py` | +13 LOC：import `check_80_pg_dump_freshness` + post-conn.close() invoke + 更新 `_RUNNER_DESCRIPTION` + main() docstring ID 清單加 [80] |
| `srv/helper_scripts/db/passive_wait_healthcheck/__init__.py` | +6 LOC：re-export `check_80_pg_dump_freshness` 到 module-level __all__ |
| `srv/helper_scripts/SCRIPT_INDEX.md` | +8 LOC：新增「2026-05-27 P0-OPS-4 GAP-D PG dump cron + healthcheck IMPL」段，列 4 個 file（round 1 3 + round 2 1） |

### 未動

- `srv/helper_scripts/db/passive_wait_healthcheck.sh`（97 LOC Bash wrapper，task 「不破既有 6 check 行為」嚴格遵守 — wrapper 是 venv loader / args forwarder，無 check function 邏輯）
- `srv/sql/migrations/V113__*.sql`（per task constraint「禁改 V113」）
- 3 個 round 1 cron 檔（per task constraint「禁改 cron wrapper」）

---

## 3. 7 check 清單（A1 標準 7-check）

| ID | 名稱 | Source | 性質 | 失敗 verdict |
|---|---|---|---|---|
| [1] | backup_dir | verify_pg_dump.sh:48-56 | filesystem | FAIL（非 dir / 不可寫）; INSUFFICIENT_SAMPLE（缺）|
| [2] | freshness 26h | verify_pg_dump.sh:58-74 | filesystem stat mtime | FAIL（致命）|
| [3] | size > 1MB | verify_pg_dump.sh:76-85 | filesystem stat size | FAIL（致命）|
| [4] | md5 vs JSONL | verify_pg_dump.sh:87-105 | hashlib + stdlib JSONL parse | FAIL drift; WARN no entry |
| [5] | retention 30d | verify_pg_dump.sh:107-119 | filesystem oldest mtime | WARN |
| **[6]** | **L0 schema coverage smoke** | **FA §C.5 + PA §10.B.6 新加** | **subprocess pg_restore --list** | **FAIL absent; WARN pg_restore 缺** |
| **[7]** | **governance_audit_log trail** | **PA §10.B.1 + FA §C 新加** | **PG query (psycopg2)** | **FAIL stale > 26h; INSUFFICIENT_SAMPLE V113 未 land / 0 row** |

整體 verdict 取 7 個 sub-check severity max（per `_common.severity_max`）。

### Fail-soft 設計（避阻 first-day deploy）

| 情境 | 各 check verdict | 整體 verdict | exit |
|---|---|---|---|
| Cron 從未 fire（fresh deploy）| 1=INSUFFICIENT_SAMPLE / 2-6=INSUFFICIENT_SAMPLE / 7=INSUFFICIENT_SAMPLE | INSUFFICIENT_SAMPLE | 0 |
| V113 已 apply + 第一份 dump 寫入 < 26h | 1-6=PASS / 7=PASS | PASS | 0 |
| Dump stale > 26h | 1=PASS / 2=FAIL / 7=FAIL | FAIL | 1 |
| Dump partial (< 1MB) | 1=PASS / 2=PASS / 3=FAIL | FAIL | 1 |
| earn_movement_log 缺 TOC | 1-5=PASS / 6=FAIL | FAIL | 1 |
| pg_restore CLI 缺 | 1-5=PASS / 6=WARN | WARN | 1 |

---

## 4. passive_wait_healthcheck.sh wire（A2 — interpretation 標記）

### Task 文字 vs 實際架構衝突

Task 字面說「在 `passive_wait_healthcheck.sh` 加第 7 個 check function `check_pg_dump_freshness()`，對齊既有 6 check pattern」，但實際 architecture：
- `passive_wait_healthcheck.sh`（97 LOC）= venv loader wrapper，無 check function
- `passive_wait_healthcheck.py`（37 LOC）= shim 委派
- 真正的 check 在 `passive_wait_healthcheck/runner.py`（1406 LOC）orchestrator + 30+ `checks_*.py` module 註冊 40+ checks
- FA #7「7 check (原 6 + pg_dump_freshness)」字面數字 = 6 health domain（per FA #8 row）非 6 check functions

### 我的 interpretation 與決策

**真意 = wire 進 passive_wait pipeline 標 [80] slot**，對齊 [75]-[79] cron_heartbeat 系列：
- 加 `check_80_pg_dump_freshness()` 到 `checks_cron_heartbeat.py`（cron 性質相符）
- runner.py 在 post-conn.close() block 註冊（與 [75]-[79] 同 cron heartbeat 段相鄰）
- standalone .py 是 SSOT；wrapper 用 importlib + `OPENCLAW_BASE_DIR` 動態解析 sys.path delegate（對齊 [20] check_h_state_gateway_freshness pattern）
- 包 `try/except SystemExit` 防 standalone `connect_pg()` exit(2) 打掛 runner
- 失敗 graceful：import fail → WARN（OPENCLAW_CRON_HEARTBEAT_REQUIRED=1 升 FAIL）

**不破既有 6 check 行為**：100% 保持 — 沒動 `.sh`，沒動 [1]-[79] 任何 check 路徑。

### 觸發 `passive_wait_healthcheck.sh --quiet` 時行為

從 .sh → .py → runner → 跑全 40+ check（含新 `[80] pg_dump_freshness`）→ 末尾 SUMMARY。新 [80] 行只在 non-PASS 時顯示（per --quiet 慣例），fail-soft 期間默默 PASS-skip。

---

## 5. 治理對照

| 項目 | 對齊 | 證據 |
|---|---|---|
| PA spec §10.B.2 「`check_pg_dump_freshness()` 進 passive_wait...預期 last `pg_dump_completed` event ts < 26h」 | ✅ check[7] 完全實作 | check_pg_dump_freshness.py:373-440 |
| FA §E #7 「`passive_wait_healthcheck.sh --quiet` 7+ check（原 6 + pg_dump_freshness）」 | ✅ runner [80] 註冊 | runner.py post-conn.close() block |
| FA §C.5 「`pg_restore --list \| grep earn_movement_log` ≥ 1 entry」 | ✅ check[6] subprocess | check_pg_dump_freshness.py:308-371 |
| PA §10.B.6 「Earn V100 audit trail post-install smoke」 | ✅ check[6] 邏輯一致 | 同上 |
| memory `feedback_cross_platform` 跨平台 | ✅ `sys.platform != 'linux'` refuse exit 2 | check_pg_dump_freshness.py:82-89 |
| memory `feedback_chinese_only_comments` Chinese-first | ✅ 全檔注釋中文（保留英文技術詞）| 全檔 |
| CLAUDE.md §九 800/2000 LOC 警戒 | ✅ 616 / 325 LOC 都 < 800 | wc -l 確認 |
| memory `feedback_v_migration_pg_dry_run` Linux empirical | ✅ SSH 跑 standalone --status 確認 | §6 Linux test result |
| 硬邊界 max_retries / live_execution / system_mode 不可改 | ✅ 純讀；無 mutate any governance state | source code grep |
| stdlib only / 不引新依賴 | ✅ psycopg2 已是 passive_wait venv 既有 | 無 import 新套件 |

---

## 6. 測試結果

### 6.1 Mac syntax 全綠

```bash
$ python3 -m py_compile srv/helper_scripts/canary/healthchecks/check_pg_dump_freshness.py
MAC py_compile OK

$ python3 -m py_compile srv/helper_scripts/db/passive_wait_healthcheck/{__init__,checks_cron_heartbeat,runner}.py
ALL PASSIVE-WAIT MODULES PY_COMPILE OK

$ bash -n srv/helper_scripts/db/passive_wait_healthcheck.sh
MAC bash -n OK
```

### 6.2 Linux empirical `--status` 跑通

```
$ ssh trade-core "set -a; source ~/BybitOpenClaw/secrets/environment_files/basic_system_services.env; set +a; \
    .venv/bin/python3 check_pg_dump_freshness.py --status"

verdict: "INSUFFICIENT_SAMPLE"
checks: [
  [1] backup_dir         INSUFFICIENT_SAMPLE  (cron not yet fired)
  [2] freshness          INSUFFICIENT_SAMPLE  (no dump)
  [3] size               INSUFFICIENT_SAMPLE  (no dump)
  [4] md5                INSUFFICIENT_SAMPLE  (no dump)
  [5] retention          INSUFFICIENT_SAMPLE  (no dump)
  [6] L0 schema smoke    INSUFFICIENT_SAMPLE  (no dump)
  [7] audit_trail        INSUFFICIENT_SAMPLE  (V113 not applied yet)
]
EXIT=0  ← fail-soft 不阻 first-day deploy
```

### 6.3 Linux empirical wrapper invoke

```
$ ssh trade-core "...check_80_pg_dump_freshness()"
VERDICT=INSUFFICIENT_SAMPLE
MSG=[80] pg_dump_freshness verdict=INSUFFICIENT_SAMPLE (7 sub-check; non-PASS: [1]:INSUFFICIENT_SAMPLE, [2]:INSUFFICIENT_SAMPLE, [3]:INSUFFICIENT_SAMPLE, [4]:INSUFFICIENT_SAMPLE, [5]:INSUFFICIENT_SAMPLE, [6]:INSUFFICIENT_SAMPLE, [7]:INSUFFICIENT_SAMPLE)
EXIT=0
```

### 6.4 PG empirical 驗 V113 schema 還未 apply

```sql
$ ssh trade-core "psql ... -c '\\d learning.governance_audit_log'"
governance_audit_log_event_type_check
  CHECK (event_type IN ('review_live_candidate', 'lease_grant', ...
         'halt_session_set', 'halt_session_auto_cleared', 'halt_session_manual_cleared'))
-- 24 value baseline; **pg_dump_completed / pg_dump_failed 還未 land**
```

確認：check[7] INSUFFICIENT_SAMPLE-skip 正確觸發，V113 PG apply 後會自動轉 PASS（cron 開跑後）。

---

## 7. 不確定之處 / Corner case

### 7.1 task 文字「在 .sh 加 function」interpretation 風險

- 我選 wire 到 runner.py 註冊 `[80]`，不改 .sh
- 真意若是「Bash function」則需要全新設計（在 .sh 加 `check_pg_dump_freshness()` Bash function 並改 invoke），但這違反 `.sh = venv loader` 既有架構
- **請 E2 確認 PA 真意**；若需 Bash function 路徑我可補做 round 3

### 7.2 V113 還未 PG apply

- PG 確認 `governance_audit_log_event_type_check` 仍是 24-value baseline，缺 `pg_dump_completed` / `pg_dump_failed`
- round 1 `trading_ai_pg_dump_cron.sh` INSERT 會被 CHECK 拒（cron 跑會寫 audit row 失敗，但 dump 主流程不受阻）
- 我的 healthcheck `INSUFFICIENT_SAMPLE` 對應 V113 未 land 場景 — graceful
- **operator 需先 apply V113** 後再 install cron；否則 cron 寫 audit row 會 fail（不致命但 noise）

### 7.3 PA spec §10.B.1 vs round 1 實際 event_type 數量差異

- PA spec §10.B.1 列 4 個 event_type（completed / failed / retention_dropped / md5_drift）
- V113 + round 1 cron wrapper 只實作 2 個（completed / failed）
- check[7] 對齊實際 2 個；未來若 cron 加 md5_drift / retention_dropped event，V113 需另發補登 + healthcheck 加 sub-check
- **這是 PA spec 與 V113 不一致 — 可能是 PA 過度規格**，不在 round 2 scope；E2 review 可確認

### 7.4 wrapper 中 `OPENCLAW_BASE_DIR` 解析行為

- wrapper 解析 `OPENCLAW_BASE_DIR` 環境變數 → `srv` root → `helper_scripts/canary/healthchecks/check_pg_dump_freshness.py`
- 若 cron 跑 passive_wait_healthcheck wrapper 時沒 set `OPENCLAW_BASE_DIR`，fallback `~/BybitOpenClaw/srv`
- 對齊 [20] check_h_state_gateway_freshness:133-139 fallback pattern
- 跨平台：Mac dev 直接 import 不會跑 check[6]（因為 platform guard），Linux runtime 才完整跑

### 7.5 第 6 check L0 schema 對 `earn_movement_log` 字串依賴

- 若 V100 改名或 schema 重構，hardcoded `earn_movement_log` 會引起誤 FAIL
- 未來需與 V100 owner 協調 — 加 ADR / spec 標 grep target
- 當前依 FA §C.5 acceptance criteria 寫死 OK

---

## 8. Operator 下一步

1. **E2 review** 本檔 + 4 個改動檔（focus：interpretation §4 是否接受、graceful fallback 是否符合 first-day fail-soft principle）
2. E2 sign-off 後 **E4 regression**：跑 `passive_wait_healthcheck.sh --quiet` 確認 `[80]` 行不破其他 [1]-[79] 任何 check 結果
3. QA Audit（如需）：5+2 新 check 邏輯正確性 vs verify_pg_dump.sh 對照
4. PM commit + push：4 個改動檔 + round 1 4 個檔（一起）+ memory update

### 部署順序（operator 真實上線時）

1. PM commit + push
2. ssh trade-core git pull
3. **先 apply V113 migration** — 不可省略；否則 cron 跑會 CHECK 拒 INSERT audit row
4. operator 跑 `install_pg_dump_cron.sh` 加 crontab entry
5. 第一份 daily dump 跑完後（next 03:00 UTC），跑 `bash passive_wait_healthcheck.sh --quiet` 應看到 `[80] verdict=PASS`

---

## 9. 文件參考

- **PA spec**: `docs/execution_plan/specs/2026-05-26--p0-ops-4-first-day-live-runbook.md` §10.B.1-6 + §2.3
- **FA acceptance**: `docs/CCAgentWorkSpace/FA/workspace/reports/2026-05-27--ops_4_gap_bd_business_acceptance_audit.md` §C + §E #7
- **MIT empirical**: `docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-27--ops_4_gap_bd_pg_backup_restore_research.md` §1.1-1.7
- **Round 1 land**: 4 個檔 commit chain（cron/install + cron + verify + V113）
- **Memory log**: `docs/CCAgentWorkSpace/E1/memory.md` 末段 2026-05-27 P0-OPS-4 GAP-D round 2

---

**E1 IMPLEMENTATION DONE: 待 E2 審查（report path: srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-27--ops_4_round_2_e1_pg_dump_healthcheck.md）**
