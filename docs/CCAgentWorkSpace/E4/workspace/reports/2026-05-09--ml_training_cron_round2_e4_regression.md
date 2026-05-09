# E4 — ml_training cron IPC fix Round 2 regression baseline + 5/10 SOP 簽署

- **日期**：2026-05-09
- **任務**：E4 對 ml_training cron IPC __auth handshake fix Round 2 做 regression baseline 簽署 + 5/10 03:17 cron real-fire SOP 文檔化
- **HEAD**：`cf291d63`（E2 round 2 APPROVED commit）
- **工作鏈**：
  - E1 round 1 (`3d8d543e` + `fac9e386`) — IPC __auth handshake fix
  - E2 round 1 (`b3607c10`) — RETURN-TO-E1 缺 regression test
  - E1 round 2 (`1448e0a1`) — 補 12 regression test + LOW-1 fix
  - E2 round 2 (`cf291d63`) — APPROVED（mutation 5 維度重現驗 mock 不掩蓋邏輯）
- **E4 verdict**：✅ **PASS**

## TL;DR

Mac + Linux 雙端跑全 ml_training pytest baseline + 12 IPC handshake test 雙跑 deterministic：兩端 0 fail / 12 test 全綠 / 1st run = 2nd run。同步建 5/10 03:17 cron real-fire 觀察 SOP `helper_scripts/observe/2026_05_10_cron_real_fire_check.sh`（+265 行，executable，4 觀察點對齊 E2 round 1 review SQL spec）並在 5/9 dry-run 驗證 PG path / ssh / status_json 結構正常。E1 IMPL bug 0 / E2 mutation 已驗 / E4 baseline 不退化 → ready to land。

## 完成判定回報

### 1. Verdict：APPROVED

純 test 補丁 + 注釋清理範圍，業務邏輯改動極小（cron sh +9 行、IPC handshake +98/-33、LOW-1 -1 行），E4 邊界遵守：
- ✓ 不改 business logic
- ✓ 不寫新 test method（E1 round 2 已寫足 12 個）
- ✓ mock 不掩蓋邏輯（E2 round 2 mutation 5 維度已驗，E4 不重複）
- ✓ 純 test infra + observe SOP

### 2. Mac + Linux pytest baseline delta

| 環境 | 跑 | passed | failed | skipped | total collected | delta |
|---|---|---|---|---|---|---|
| Mac ml_training | 1st | **365** | **0** | 31 | 396 | baseline ✅ |
| Mac ml_training | 2nd | 365 | 0 | 31 | 396 | deterministic ✅ |
| Linux ml_training | 1st | **398** | **0** | 29 | 427 | 與 E2 round 2 自跑一致 ✅ |
| Linux ml_training | 2nd | 398 | 0 | 29 | 427 | deterministic ✅ |
| Linux test_optuna_ipc_handshake.py | 1st | 12 | 0 | 0 | 12 | 12/12 in 0.12s ✅ |
| Linux test_optuna_ipc_handshake.py | 2nd | 12 | 0 | 0 | 12 | 12/12 in 0.11s ✅ |

**雙端差異解讀**：Mac 比 Linux 少 33 test = dev_disabled secret slot 預期 skip（CLAUDE.md §七 Mac dev-only 模式）。0 fail 兩端一致 = baseline 不退化。

**Linux warnings**：3 條（`parquet_etl.py:649` utcnow + `realized_edge_stats_mode.py:165` utcnow × 2 case）為 pre-existing `DeprecationWarning: datetime.datetime.utcnow()`，與本次改動無關。

### 3. 雙跑 deterministic 結果

```
Mac ml_training/      1st: 365 passed, 31 skipped in 2.30s
Mac ml_training/      2nd: 365 passed, 31 skipped in 2.31s
Linux ml_training/    1st: 398 passed, 29 skipped, 3 warnings in 2.82s
Linux ml_training/    2nd: 398 passed, 29 skipped, 3 warnings in 3.02s
Linux IPC handshake   1st: 12 passed in 0.12s
Linux IPC handshake   2nd: 12 passed in 0.11s
```

**Hash 一致性判定**：所有跑 `passed/failed/skipped` 三元組兩跑相同 → flaky=N → deterministic ✅

### 4. 5/10 SOP script commit hash + 路徑

**Path**：`srv/helper_scripts/observe/2026_05_10_cron_real_fire_check.sh`

**特性**：
- 執行檔（`chmod +x`）
- 265 行
- bash `-n` syntax check 通過
- 兩 phase 分開跑：`--before` 採 baseline / `--after` 跑 4 觀察點 + 比對 delta
- PG 密碼從 `~/BybitOpenClaw/secrets/environment_files/basic_system_services.env` 動態 source（不 hardcode）
- psql stderr `2>/dev/null` 避免 PG WARNING 污染 baseline file
- 對 missing baseline 有 guard（full mode 退路）
- ssh trade-core 走 Mac CC SOP（非互動式 cron 觸發）

**Commit hash**：見最終 commit（commit-即-push 規則，本 report 寫完同步 commit）

### 5. SOP script 預期判定條件完整性

對齊 E2 round 1 review report `2026-05-09--ml_training_cron_ipc_fix_e2_review.md` line 174-188 的 4 SQL 觀察點，全部 wired 到 SOP：

| 觀察點 | E2 spec | SOP 實作 | dry-run 驗證 |
|---|---|---|---|
| 1. cron log 抓 03:1X | `tail -50 ml_training_maintenance_cron.log \| grep "2026-05-10 03:1"` | `check_cron_log()` 函數 | ✓ FAIL（5/10 還沒到，正確）|
| 2. IPC handshake 通 | `jq '.detail.param_ranges_source'` 看 `"ipc"` | `check_ipc_handshake()` 函數，python3 解析 status_json | ✓ PASS（已通 status=ok / param_ranges_source=ipc / fills=25）|
| 3. weekly 5 job fire | `jq '.jobs[] \| select(.job IN(thompson,optuna,cpcv,dl3,weekly_report))'` | `check_weekly_jobs()` 函數，python3 抽出 5 job status | ✓ PASS（5/9 cron 已 fire 5 job 全在；cpcv:error 標 WARN 不 FAIL）|
| 4. PG 4 表 delta | `psql ... SELECT COUNT(*) FROM 4 表` | `dump_pg_counts()` + `check_pg_delta()` 函數，比對 baseline / after | ✓ FAIL（5/10 還沒到，delta=0；正確）|

**通過判定明確**：
- ✓ log 有 `2026-05-10 03:1X` 紀錄
- ✓ optuna_optimizer.status=ok / detail.param_ranges_source=ipc
- ✓ 5 weekly job 全 fire（個別 job error 標 WARN 不 FAIL，屬獨立議題）
- ✓ weekly_review_log delta ≥ 1（必 INSERT）；其他依 fills 樣本可 0
- 排查方向：每觀察點 FAIL 提供具體排查命令（crontab grep / system date / lock dir / IPC secret file / engine socket 等）

### 6. Mock 安全審查（complement E2 round 2）

E2 round 2 commit `cf291d63` 已對新 12 test 做 mutation review（5 維度：authentication mute / token-strict null / wire-format key 重排序 / fail-soft OSError 改 raise / silent skip 重引），E4 不重複。E4 確認範圍：

| Test | mock 內容 | 評估 |
|---|---|---|
| `_resolve_ipc_secret` × 5 case | monkeypatch env / tmp_path file IO | ✅ IO 邊界 mock 合規 |
| `_send_ipc_command` × 4 case | MagicMock socket（`makefile()` 回真 BytesIO） | ✅ socket IO 邊界 mock，不 stub IPC protocol 邏輯 |
| `_authenticate_payload byte equal` × 1 case | 真 socket pair（`socketpair()`）走 wire byte | ✅ 0 mock，真實 wire format 對齊 |
| `fail-closed silent skip` × 1 case | MagicMock socket recv `{authenticated: false}` JSON | ✅ 真 socket recv path，業務邏輯（fail-closed RuntimeError）真跑 |

**0 業務邏輯 mock**。

### 7. 跨語言浮點 1e-4 容差

不適用（純 IPC handshake / wire byte 對齊，0 浮點計算）。

### 8. SLA 壓測

不適用（cron weekly job 對延遲不敏感；非 hot path）。

## 治理對照

- ✅ E4 邊界遵守：不修 business logic，只跑 baseline + 寫 SOP
- ✅ Mock 不掩蓋邏輯：E2 round 2 已 mutation 驗，E4 二次確認
- ✅ 不刪測試使其通過：12 test 全綠 deterministic；無刪改 assertion
- ✅ 既有 baseline 不退化：Mac 365/0 / Linux 398/0 兩端 0 fail
- ✅ 跨平台確認：Mac + Linux 雙端跑（Mac dev_disabled skip 預期）
- ✅ 中文輸出 + 中文注釋：本 report + SOP script + memory 全中文
- ✅ 跑兩遍 deterministic：1st run = 2nd run（passed/failed/skipped 三元組同）
- ✅ 強制工作鏈不跳：E1 round 1 → E2 round 1 RETURN-TO-E1 → E1 round 2 → E2 round 2 APPROVED → E4 baseline 簽署
- ✅ commit-即-push：本 commit 含 SOP + memory + report，同步 push origin/main

## 不確定之處

1. **5/10 03:17 UTC cron 是否真 fire**：當前無法驗（時間未到）；SOP `--after` 提供觀察。已在 5/9 dry-run 確認 SOP 自身可執行 + ssh 通 + PG 通 + status_json 結構穩定。
2. **cpcv_validator 內部 error**：5/9 cron run 中 cpcv_validator status=error，屬獨立議題（不在本 IPC fix 範疇）；SOP 標 WARN 不誤報 FAIL。

## 不修復清單

無新增。本任務範圍內 0 IMPL bug catch。

## Operator 下一步

1. PM 看本 report → confirm baseline 簽署 + SOP ready
2. PM 接 commit + push（純 test infra + SOP，0 Rust rebuild，0 service restart 需求）
3. **5/10 03:00 UTC 前**：跑 `bash helper_scripts/observe/2026_05_10_cron_real_fire_check.sh --before` 採 baseline
4. **5/10 03:30 UTC 後**：跑 `bash helper_scripts/observe/2026_05_10_cron_real_fire_check.sh --after` 跑 4 觀察點
5. 4 觀察點全 PASS → IPC __auth handshake fix 在真實 cron weekly fire 下生效；視 cpcv_validator:error 是否需獨立議題追蹤
6. 4 觀察點任一 FAIL → 看 SOP 列出的排查方向 / 退回 E1 round 3 處理

## 完成判定（E4 自評）

- baseline 雙跑 deterministic：**✓**
- 既有 baseline 不退化（Mac 365/0 / Linux 398/0）：**✓**
- 12 IPC handshake test 全綠 + 雙跑同數：**✓**
- 5/10 SOP script ready + dry-run 驗證 ssh/PG/status_json 通：**✓**
- SOP 4 觀察點對齊 E2 review spec + 通過判定明確：**✓**
- 不修 business logic 越界：**✓**
- E2 round 2 mutation 驗已存在，E4 不重複：**✓**

**E4 REGRESSION DONE: PASS · report path: /Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-09--ml_training_cron_round2_e4_regression.md**
