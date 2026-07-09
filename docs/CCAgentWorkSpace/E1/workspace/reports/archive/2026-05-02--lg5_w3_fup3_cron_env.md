# LG5-W3-FUP-3-CRON-ENV — PG creds sourcing in edge_label_backfill cron wrapper

Date: 2026-05-02
Author: E1
Sprint: LG5-W3-FUP-3-CRON-ENV
Round: 1 (initial impl, awaiting E2 review)
Status: DONE — awaiting E2 review

---

## 1. 任務摘要

PA dispatch (LG5-W3-FUP-3-CRON-ENV)：E4 Linux regression for LG5-W3-FUP-2 Fix 1+2 reported real cron run failure with `psycopg2.OperationalError: connection to server at "127.0.0.1", port 5432 failed: fe_sendauth: no password supplied`. Root cause = `helper_scripts/cron/edge_label_backfill_cron.sh` ran in cron's barebones env without `OPENCLAW_DATABASE_URL` / `POSTGRES_*` set; consumer `program_code/ml_training/edge_label_backfill.py:_open_conn` therefore fell into the empty-password POSTGRES_* path and psycopg2 rejected.

Fix = mirror `helper_scripts/linux_bootstrap_db.sh:41-45` sibling pattern in the cron wrapper itself: source 5 POSTGRES_* keys from `$OPENCLAW_SECRETS_ROOT/environment_files/basic_system_services.env` with HOST/PORT fallback, then `export OPENCLAW_DATABASE_URL=...` before the python3 invocation.

不動：backfill 業務邏輯、W1/W2/W3/FUP-1/Fix 1/Fix 2 其他 code、crontab install。

## 2. 修改清單

| 路徑 | 變更 | LOC |
|---|---|---|
| `srv/helper_scripts/cron/edge_label_backfill_cron.sh` | 修 (+72/-6) | 134 → 196 (淨 +62) |
| `srv/helper_scripts/cron/test_edge_label_backfill_cron_env.py` | 新檔 | 211 |
| `srv/docs/healthchecks/2026-05-02--lg5_health_checks.md` | 修 (+21/-3) | 494 → 512 |

無 SQL migration / 無新 singleton / 無新 IPC / 無 risk config 改動 / 0 業務邏輯變更。

## 3. 關鍵 diff

### 3.1 Wrapper PG creds sourcing block

插入 `set -euo pipefail` 之後、overlap-lock 之前。先 `mkdir -p "$LOG_DIR"` + 提前定義 `ts()` 讓 FATAL 可以寫 log。

```bash
SECRETS_ROOT="${OPENCLAW_SECRETS_ROOT:-$HOME/BybitOpenClaw/secrets}"
ENV_FILE="$SECRETS_ROOT/environment_files/basic_system_services.env"
if [[ ! -f "$ENV_FILE" ]]; then
    echo "[$(ts)] FATAL: env file missing: $ENV_FILE" | tee -a "$LOG" >&2
    exit 2
fi
# Note: `grep | cut` exits non-zero when key absent → set -e short-circuits.
# Trail `|| true` per command so missing keys reach the explicit empty check.
PG_PASS=$(grep '^POSTGRES_PASSWORD=' "$ENV_FILE" 2>/dev/null | cut -d= -f2- || true)
PG_USER=$(grep '^POSTGRES_USER=' "$ENV_FILE" 2>/dev/null | cut -d= -f2- || true)
PG_DB=$(grep '^POSTGRES_DB=' "$ENV_FILE" 2>/dev/null | cut -d= -f2- || true)
PG_HOST=$(grep '^POSTGRES_HOST=' "$ENV_FILE" 2>/dev/null | cut -d= -f2- || true)
PG_PORT=$(grep '^POSTGRES_PORT=' "$ENV_FILE" 2>/dev/null | cut -d= -f2- || true)
PG_HOST="${PG_HOST:-127.0.0.1}"
PG_PORT="${PG_PORT:-5432}"
if [[ -z "$PG_PASS" || -z "$PG_USER" || -z "$PG_DB" ]]; then
    echo "[$(ts)] FATAL: PG creds incomplete in $ENV_FILE (require POSTGRES_PASSWORD, POSTGRES_USER, POSTGRES_DB)" | tee -a "$LOG" >&2
    exit 2
fi
export OPENCLAW_DATABASE_URL="postgresql://redacted@${PG_HOST}:${PG_PORT}/${PG_DB}"
```

雙語注釋齊備（MODULE_NOTE 沿用既有 + sourcing block 自身 14 行中英對照）。

### 3.2 PA spec deviation — 為什麼比 spec 多 4 行

PA spec 給的 fallback 是行尾 `|| echo '127.0.0.1'`：
```bash
PG_HOST=$(grep '^POSTGRES_HOST=' ... | cut -d= -f2- || echo '127.0.0.1')
```
這行只在 `grep` 命中失敗時觸發；若 grep 命中但值為空（例如 `POSTGRES_HOST=`），fallback 不會生效。
我加了二次 fallback `PG_HOST="${PG_HOST:-127.0.0.1}"` 處理 grep-hit-but-empty edge case。

並把 grep 行尾 `|| echo` 改 `|| true`：保留錯誤吸收，但讓 host/port 缺失走到統一 `${VAR:-default}` 表達式（語義一致；E2 看代碼不會困惑兩種 fallback pattern 並存）。

### 3.3 Test (helper_scripts/cron/test_edge_label_backfill_cron_env.py)

4 pytest cases，pure subprocess + tmp_path（hermetic env，不繼承 operator shell）：
- `test_wrapper_exists_and_syntax_clean` — `bash -n` 靜態檢查
- `test_env_file_missing_exits_2_with_fatal` — 鎖 exit=2 + FATAL on stderr + log
- `test_env_file_creds_incomplete_exits_2_with_fatal` — env 含 POSTGRES_DB only → exit=2
- `test_env_file_complete_exports_database_url` — mock python3 in PATH echoes DSN → wrapper log 含 `MOCK_PY3_DSN=postgresql://redacted@127.0.0.1:15432/trading_ai`，驗 DSN 真 export 到下游 + HOST fallback 127.0.0.1 + PORT 15432 from env + USER/PASS/DB 正確 sourced

### 3.4 Healthcheck doc 更新

`docs/healthchecks/2026-05-02--lg5_health_checks.md` Fix 1 cron section 兩處：
- "Pairs with" 段加 PG creds auto-source 描述（FUP-3 引用 + sibling pattern + missing/incomplete 行為 + cron mailer 路徑）
- "Operator deploy steps" 段 crontab block 加 `# PG creds (LG5-W3-FUP-3-CRON-ENV)` 注釋說明 operator **不需** inline POSTGRES_* / OPENCLAW_DATABASE_URL；只在 OPENCLAW_SECRETS_ROOT 非預設時 inline 該變量

## 4. 治理對照

- **CLAUDE.md §七 ★★ 跨平台**：`grep -nE '/home/ncyu|/Users/[^/]+'` 0 hit on 3 修改檔（doc 用 `<ABSOLUTE_REPO_ROOT>` / `<ABSOLUTE_SECRETS_ROOT>` 描述式）。
- **CLAUDE.md §七 雙語注釋**：sourcing block 14 行中英對照；test 模組 MODULE_NOTE + 函數 docstring 全雙語；healthcheck doc 加段落維持既有英文主、中文輔風格。
- **CLAUDE.md §七 SQL migration**：無 SQL 改動。
- **CLAUDE.md §七 healthcheck pairing**：本 task 不引入新「被動等待」TODO，但強化既有 `[43] label_backfill_freshness` 的工具鏈（cron 運行可靠性 → `[43]` 才能反映真實 cron 健康，不是 "wrapper 沒 source PG 就 silent fail"）。
- **CLAUDE.md §九 singleton**：未新增 singleton。
- **CLAUDE.md §四 硬邊界**：grep `live_execution_allowed|max_retries|live_reserved|OPENCLAW_ALLOW_MAINNET|authorization\.json|decision_lease_emitted|system_mode|execution_authority` on wrapper 0 hit。
- **CLAUDE.md §九 LOC**：wrapper 196 / test 211 / doc 512 全 < 800 警告線。
- **PA spec 字面 vs 實作 deviation**：PA spec `|| echo '127.0.0.1'` 行尾 fallback 不夠 robust（grep-hit-but-empty edge case），改為 `|| true` + `${VAR:-default}` 二次 fallback；PA spec 與 sibling `passive_wait_healthcheck_cron.sh:43-44` 不一致，PA 選 `linux_bootstrap_db.sh:41-45` 完整版（更 robust），sibling alignment 直接寫進雙語 inline 注釋與本報告。

## 5. Sibling pattern alignment 驗證（PA 任務 step 2）

實際 grep 兩個 sibling cron wrapper：

| Sibling | LOC | Pattern | 為什麼不/選 |
|---|---|---|---|
| `passive_wait_healthcheck_cron.sh:43-44` | 2 行 | 簡化版：grep PG_PASS only + hardcode `trading_admin` / `trading_ai` / `127.0.0.1:5432` | **不選** — 綁特定 user/db/host/port，secret rotation 不友好 |
| `linux_bootstrap_db.sh:41-45` | 5 行 | 完整版：grep 5 keys + HOST/PORT fallback | **選** — 跨 slot 兼容，與 PA spec 對齊 |

實測 secrets env file 真實 keys（Mac + Linux 兩端 grep）：
```
POSTGRES_DB=<set>
POSTGRES_USER=<set>
POSTGRES_PASSWORD=<set>
POSTGRES_PORT=<set>
# POSTGRES_HOST 缺！HOST fallback 127.0.0.1 是必要的
```

PA spec 寫的 5-key + fallback pattern 完全對齊真實環境。本實作多加的「`||true` + `${VAR:-default}` 二次 fallback」是真實環境（HOST 缺）+ bash `set -e` 互動下的 robustness 補強，**功能上**符合 PA spec 意圖。

## 6. 不確定之處

1. **`||true` + `${VAR:-default}` 雙重 fallback vs PA spec 單一 `||echo`**：行為等價（都讓 HOST/PORT 缺失時 default 127.0.0.1:5432），但 LOC 多 4 行 + 注釋 4 行。E2 若覺得 PA spec 字面更乾淨，可回退到單一 `||echo` pattern（functionality 等價，會吃掉 grep-hit-but-empty edge case 的覆蓋）。本輪選 robustness 優先。
2. **Test 用 mock python3 in PATH 而非 source wrapper**：第一次嘗試用 `bash -c 'source wrapper; echo $URL'` 驗 export，但 wrapper `set -e + exit 1` 殺 subshell，連 `echo` 都跑不到。改用 `mock_bin/python3` 在 PATH 前 + 從 wrapper log 反查 DSN echo。E2 若覺得 source-based 更直接，需把 wrapper 改成可被 source（移除 exit /替換為 return）— 但這違反 wrapper 自身的 cron-mode 設計（cron 跑時必須 exit）。本輪選 mock python3 pattern。
3. **`OPENCLAW_DATABASE_URL` 已 export 但下游 backfill.py `_open_conn` line 94 也讀 `os.environ.get("DSN")`**：本 fix 只 export `OPENCLAW_DATABASE_URL`，不 export `DSN`。實測 backfill.py 優先讀 `OPENCLAW_DATABASE_URL`，DSN 是 secondary fallback；對齊 sibling `passive_wait_healthcheck_cron.sh:44` 也只 export `OPENCLAW_DATABASE_URL`。如果 E4 Linux smoke test 顯示 DSN 也需要，再補 `export DSN=...`（一行）。本輪不補，避免擴散。

## 7. Operator 下一步

### 已驗（Mac CC，無 ssh）
- `bash -n` exit 0
- 4 new pytest PASS in 0.46s
- 25 baseline LG5 healthcheck pytest PASS (0 regression)
- 4 manual smoke test cases all green (sealed env via `env -i`):
  - TEST A (env file missing) → exit 2 + FATAL stderr/log
  - TEST B (creds incomplete) → exit 2 + FATAL stderr/log
  - TEST C (BASE bad after PG ok) → exit 1 + ERROR log (證 PG block 通過後 wrapper 正常往下走 sanity check)
  - TEST D (mock python3 echo DSN) → exit 0 + log 含 `MOCK_PY3_DSN=postgresql://redacted@127.0.0.1:15432/trading_ai`
- 跨平台 grep 0 hit / 硬邊界 grep 0 hit / LOC < 800 warn
- `git diff --check` exit 0

### 等待 / 不做
- **不 commit / 不 push** — 等 E2 review → E4 SSH Linux real cron smoke (production secrets file 真值) → QA → PM 統一 commit
- **不 install crontab** — operator 手動 + 已在 healthcheck doc Operator deploy steps 寫清楚（不需 inline POSTGRES_*）

### E2 round 1 審查重點
1. **PA spec deviation 正當性**：`||true` + `${VAR:-default}` 二次 fallback vs PA spec 字面 `||echo` 單層（覆蓋 grep-hit-but-empty edge case；E2 若覺得不需要可回退）
2. **Sibling pattern 選擇 (linux_bootstrap_db 完整版)**：不選 passive_wait sibling 的簡化版（hardcode trading_admin/trading_ai）— rationale 寫在報告 §5 + wrapper 雙語注釋
3. **Test 用 mock python3 pattern**：避開 source-wrapper 路徑被 set -e 殺的問題；E2 若覺得測試太間接可建議 wrapper 改成可被 source
4. **`OPENCLAW_DATABASE_URL` only**（不 export `DSN`）：對齊 sibling `passive_wait_healthcheck_cron.sh:44` + backfill.py 真實 fallback 順序

### E4 Linux real-cron smoke 驗收建議
1. ssh trade-core, `bash helper_scripts/cron/edge_label_backfill_cron.sh`，期待 exit=0 + log 顯示 `--engine-mode demo OK` + `--engine-mode live_demo OK`
2. `tail -50 /tmp/openclaw/logs/edge_label_backfill_cron.log`，無 `fe_sendauth: no password supplied` 或 `FATAL` 字樣
3. 接著 `python3 helper_scripts/db/passive_wait_healthcheck.py 2>&1 | grep '\[43\]'`，期待 PASS（age <2h）

---

E1 LG5-W3-FUP-3-CRON-ENV DONE: 待 E2 審查
report path: `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-02--lg5_w3_fup3_cron_env.md`
