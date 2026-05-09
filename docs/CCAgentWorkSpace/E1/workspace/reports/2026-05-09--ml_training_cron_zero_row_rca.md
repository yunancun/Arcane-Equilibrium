# 2026-05-09 — ml_training_maintenance cron zero-row RCA + IPC __auth fix

**Agent**：E1（Backend Developer）
**Task source**：玄衡治理任務（operator dispatch via auto mode）
**Mac SSOT HEAD**：`fed11435` → fix commit `3d8d543e`（已 push origin/main，Linux fast-forward 完成）

---

## 1. 任務背景

V3 sprint closure 後 24h delta 驗證發現 4 個目標表 INSERT 全 0 row：
- `learning.bayesian_posteriors` total=0
- `learning.ml_parameter_suggestions` total=0
- `learning.foundation_model_features` total=0
- `learning.weekly_review_log` total=0

Operator 假設三層之一：
1. cron 沒實際 fire（systemd / cron daemon / env 問題）
2. cron fire 但 script 失敗（path / dependency / permission）
3. script 跑成功但 4 表 writer code path 不通

---

## 2. 三層 RCA 結論（**多重原因，但與 brief 假設不完全匹配**）

### Layer 1: cron 確實沒 fire（**24h 內**）— 但不是 daemon 問題

| 證據 | 結論 |
|---|---|
| `crontab -l` 第 36 行存在 | entry 已註冊 |
| `systemctl status cron`（read-only）= active running 3 weeks 4 days | daemon 健康 |
| `/var/log/syslog` 5/2-5/9 全期間 0 ml_training 字樣 | entry 從未 fire |
| `ls -la helper_scripts/cron/ml_training_maintenance_cron.sh` mtime = `2026-05-09 18:41` | **script 是今天 18:41 commit 的，cron entry 也是同期才裝** |

**結論**：24h delta 驗證的時間窗口本來就在 entry 安裝之前，0 row 不奇怪。下次 fire 是 5/10 03:17（今天 18:41 安裝後尚未到 03:17）。

→ **operator brief 「上次 03:17 應 fire 過」是誤判**，但因 brief 同時要求做 INSERT path 驗證，繼續往下查。

### Layer 2: 手動跑 script — INSERT 路徑 75% 通

`OPENCLAW_BASE_DIR=$HOME/BybitOpenClaw/srv OPENCLAW_DATA_DIR=/tmp/openclaw $HOME/BybitOpenClaw/srv/helper_scripts/cron/ml_training_maintenance_cron.sh` 直接跑。

但是 5 個 audit job (thompson/optuna/cpcv/dl3/weekly) 默認 `_skip_not_due()` 限制 UTC weekday=6 (Sunday)：

```python
def _weekly_audit_due(args: argparse.Namespace) -> bool:
    if args.force_audit_jobs:
        return True
    return datetime.now(timezone.utc).weekday() == args.audit_weekday  # 6 = Sunday
```

今天 5/9 = Saturday (UTC weekday=5)，**5 個 audit job 全 skip**。這是 FA D-10 設計（weekly job per design），但 brief 把 weekly cron 當 daily 期待 row。

第二次跑加 `OPENCLAW_ML_CRON_FORCE_AUDIT_JOBS=1` 強制：
- thompson_sampling: **ok**, rows_written=219（→ bayesian_posteriors）
- dl3_foundation: **ok**, 4 model run（→ foundation_model_features）
- weekly_report_generator: **ok**, persist=true（→ weekly_review_log）
- cpcv_validator: **error** = `lightgbm not installed`
- optuna_optimizer: **skipped** = `param_ranges_unavailable`（detail: `RuntimeError`）

3/4 INSERT 路徑驗證通。剩 ml_parameter_suggestions 0 row → Layer 3。

### Layer 3: optuna IPC 撞 __auth handshake 缺失

直接 `nc -U /tmp/openclaw/engine.sock` 投測 `get_param_ranges`：

```
{"jsonrpc":"2.0","error":{"code":-32600,"message":"first message must be __auth"},"id":null}
```

Engine 在 `OPENCLAW_IPC_SECRET` 設置時要求 HMAC-SHA256 first-message handshake（`rust/openclaw_engine/src/ipc_server/connection.rs:140`）。**主端 `ipc_client.py:578 _authenticate` 處理了 auth**，但 `optuna_optimizer.py:293 _send_ipc_command` 是手寫的 lightweight client，沒處理 `__auth`。

→ 撞 `RuntimeError: IPC error [-32600]: first message must be __auth` → `_resolve_optuna_param_ranges` catch 為 `unavailable:RuntimeError` → `param_ranges_unavailable` skip。

---

## 3. Fix（commit `3d8d543e`）

### 3.1 helper_scripts/cron/ml_training_maintenance_cron.sh（+9 行）

注入 `OPENCLAW_IPC_SECRET_FILE` 對齊 restart_all.sh 默認 path：

```bash
# 注入 IPC secret 路徑 — engine 在 OPENCLAW_IPC_SECRET 設置時要求 __auth 握手
# optuna_optimizer 呼叫 IPC `get_param_ranges` 需要先帶 HMAC-SHA256 token；
# 沒帶 = engine 拒收 first message must be __auth → param_ranges_unavailable
# 對齊 restart_all.sh 的 path：$SECRETS_ROOT/environment_files/ipc_secret.txt
IPC_SECRET_FILE_DEFAULT="$SECRETS_ROOT/environment_files/ipc_secret.txt"
if [[ -z "${OPENCLAW_IPC_SECRET_FILE:-}" && -f "$IPC_SECRET_FILE_DEFAULT" ]]; then
    export OPENCLAW_IPC_SECRET_FILE="$IPC_SECRET_FILE_DEFAULT"
fi
```

### 3.2 program_code/ml_training/optuna_optimizer.py（+98 行 / -33 行）

加三個函數：

| 函數 | 用途 |
|---|---|
| `_resolve_ipc_secret()` | env-first / file-fallback 對齊 `secret_runtime.get_secret_value` |
| `_read_response_line()` | 共用 newline-delimited JSON-RPC reader（auth + business call） |
| `_send_ipc_command()` 改寫 | connect 後若 secret 存在先送 `__auth`（HMAC-SHA256(secret, str(ts))），再送業務 call |

Wire format 對齊 `ipc_client._authenticate`：
- `id=0` for auth, `id=1` for business
- `ensure_ascii=False`（HMAC token 是純 ASCII hex，但與 ipc_client byte-equal 對齊 E2 round 1 LOW-2 retrofit 2026-05-03）
- `authenticated=true` 驗證

### 3.3 imports

`+ import hashlib`、`+ import hmac as _hmac_lib`、`+ import time`。

---

## 4. 驗證

### 4.1 Unit test（9/9 PASS）

`_resolve_ipc_secret`:
1. 沒設 → None ✓
2. 直接 env → 直接值 ✓
3. 只有 FILE → 從檔讀（strip） ✓
4. 直接 env 優先於 FILE ✓
5. 不存在 FILE → None（fail-soft） ✓

`_send_ipc_command`（mock socket）:
6. business result extracted ✓
7. wire 1 = `__auth` (id=0, token len=64 = SHA256 hex) ✓
8. wire 2 = business method (id=1, params preserved) ✓
9. no secret → skip auth, send business directly ✓

### 4.2 Linux force-run（after fix）

| Field | 修復前 | 修復後 |
|---|---|---|
| `optuna_optimizer.status` | skipped | **ok** |
| `optuna_optimizer.error` | param_ranges_unavailable | (空) |
| `param_ranges_source` | unavailable:RuntimeError | **ipc** |
| `result.status` | (沒進到此層) | insufficient_data (fills=25 < 80) |
| `result.study_name` | (沒進到此層) | ma_crossover_BTCUSDT_live_observed |

→ IPC 通了；ml_parameter_suggestions 0 row 是真實業務 fills 不夠 80（`ma_crossover/BTCUSDT/demo+live_demo` 30d 只 29 fills），**非 schema/writer 問題**。

---

## 5. 修復前後 4 表計數 → 修復後計數 → cron log 路徑驗證

### 5.1 4 表 count delta

| 表 | baseline 0 | manual run #1 (skip 5 jobs) | force run #1 | force run #2 (after fix) | RCA |
|---|---|---|---|---|---|
| bayesian_posteriors | 0 | 0 (skip) | 219 | 219 | thompson UPSERT idempotent |
| ml_parameter_suggestions | 0 | 0 (skip) | 0 (RuntimeError) | **0 (insufficient_data 25<80)** | 真實樣本不夠 |
| foundation_model_features | 0 | 0 (skip) | 4 | 8 (+4) | dl3 INSERT 通 |
| weekly_review_log | 0 | 0 (skip) | 1 | 2 (+1) | weekly_report INSERT 通 |

→ **3/4 表 INSERT 路徑經實證可寫**；ml_parameter_suggestions 等業務樣本累積即可寫。

### 5.2 cron log 路徑

operator brief 預期 `~/BybitOpenClaw/srv/logs/cron/`（不存在），實際 script 寫到 `$DATA/logs/`：

```
-rw-rw-r-- 1 ncyu ncyu 141741  5月  9 20:22 /tmp/openclaw/logs/ml_training_maintenance_cron.log
-rw-rw-r-- 1 ncyu ncyu  12405  5月  9 20:22 /tmp/openclaw/status/ml_training_maintenance_status.json
```

→ **腳本 log 機制工作正常**，path 在 `/tmp/openclaw/logs/`（即 `$OPENCLAW_DATA_DIR/logs/`）。Brief 的「重定向到 logs/cron/」建議**不採納**（會破壞既有 monitoring path 約定）。

### 5.3 cron 真實 fire 待驗

下次 fire = 2026-05-10 03:17 CEST（即 01:17 UTC）；本次驗證僅手動 force-run，cron 環境下 `OPENCLAW_IPC_SECRET_FILE` 是否經 cron.sh 的 `if [[ -z ... && -f ... ]]` 正確 resolve 待明天 cron 自動 fire 後驗 status_json.optuna_optimizer.status。

---

## 6. 治理對照（CLAUDE.md 強制條款）

| 條款 | 狀態 |
|---|---|
| §七 跨平台兼容性 | ✓ 用 `$SECRETS_ROOT/environment_files/ipc_secret.txt`，不硬編碼 |
| §七 注釋默認中文 | ✓ 新加 docstring/inline 全中文 |
| §七 SQL migration Guard A/B/C | n/a（無 SQL migration） |
| §七 被動等待 healthcheck | n/a（本任務非被動等待 TODO） |
| §七 Sign-off git status clean | ✓ 只 stage 本任務 2 檔，未吸 multi-session WIP |
| §八 1) 規劃優先 | ✓ 三層 RCA 後 IMPL，非平凡修改 |
| §八 6) 自主 bug 修復 | ✓ 從 cron / IPC handshake / writer 三層追根因 |
| §八 「最小影響」 | ✓ 只改 IPC auth handshake + cron secret 注入；不改 weekly schedule、不改 lightgbm install、不改 audit_weekday |
| §九 800 行警告 | ✓ optuna_optimizer.py 修改後 ~870 行，仍在 800-2000 軟區間（pre-existing baseline >800） |

---

## 7. 不確定之處

1. **明天 5/10 03:17 自動 fire 是否真通過 IPC auth**：手動 export `OPENCLAW_IPC_SECRET_FILE` 跑通了，但 cron 是否能透過 cron.sh 的 `if -f` 條件正確注入待驗。如失敗可能要在 ml_training_maintenance.py 主端額外 `os.environ.setdefault` 兜底，但本次先不做。
2. **lightgbm not installed**：cpcv_validator + quantile_trainer 仍 fail；屬 deploy 配置問題，超出 IMPL scope。
3. **dl3 4/4 model_unavailable**：chronos-t5-tiny / timesfm-1.0-200m 是否需 download；未深查 model registry config，屬 P2 follow-up。
4. **fills < 80 的根本原因**：是策略 demo 階段樣本累積太慢（demo 通常少量 fill），還是 promotion gate 阻 demo 真正 fire；需 QC 看 demo 期望 fill rate。

---

## 8. Operator 下一步

1. **觀察明天 5/10 03:17 cron 自動 fire**：`tail /tmp/openclaw/logs/ml_training_maintenance_cron.log` + `cat /tmp/openclaw/status/ml_training_maintenance_status.json | jq '.jobs[] | select(.job=="optuna_optimizer")'` 看 status==ok && param_ranges_source==ipc
2. **明天 5/10 因為是 Sunday weekday=6** → 5 個 audit job 自然 fire（不需 force flag）；可以證實 cron 真實 path 完整工作
3. **Review IPC auth fix 是否需要 E2 review**：本變動 ~130 行業務邏輯（IPC auth handshake + wire format）— **建議 E2 review**（跨 IPC wire format + 跟 ipc_client.py 對齊不變式）
4. **P2 ticket 補洞**：建議 4 個 P2 ticket（lightgbm install / dl3 model / optuna fills threshold / weekly fire healthcheck），詳 E1 memory.md 「後續 follow-up」

---

## 9. 修復 commit hash + 行數

- commit: `3d8d543e`
- 變動：
  - `helper_scripts/cron/ml_training_maintenance_cron.sh` +9 行（env injection）
  - `program_code/ml_training/optuna_optimizer.py` +98 / -33 行 = 純新增 ~98 行業務邏輯（含 docstring/中文注釋）
  - 總計：107 insertions / 33 deletions
- 本機 push: `9e265ba9..3d8d543e  main -> main`
- Linux pull: `fed11435..3d8d543e  main       -> origin/main` ✓ fast-forward

---

E1 IMPLEMENTATION DONE: 待 E2 審查（report path: `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-09--ml_training_cron_zero_row_rca.md`）
