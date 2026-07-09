---
title: M11 smoke zombie design-fix — register+run → register-only minimal
date: 2026-05-29
author: E1
ticket: P2-M11-SMOKE-ZOMBIE-DESIGN-FIX (TODO v81)
status: IMPL DONE — 待 E2 審查 + E4 回歸（不自宣 sign-off）
chain: E1 → E2 → E4 → QA → PM
hard boundaries: 不觸 live_execution_allowed / OPENCLAW_ALLOW_MAINNET / authorization.json / live_reserved；不改 replay_runner binary；不改 PG schema；不 push
---

# E1 — M11 smoke register-only design-fix

## 1. 任務摘要

`m11_replay_runner_daily_cron.sh`（M11 Stage A daily 04:00 UTC cron wrapper）原版做
**register + run dispatch**：

- POST `/api/v1/replay/experiments/register` 寫 `replay.experiments` row → 滿足
  `[48] replay_manifest_registry_growth`（rows_7d/24h ≥ 1）
- POST `/api/v1/replay/run` 啟動真實 replay 子進程 → 子進程 hang/死不寫
  `completed_at`/`exit_code` → `replay.run_state` 留 `'running'` zombie row →
  4h 後 `[50] replay_run_state_health` FAIL

首例 zombie `6532fc38`（install smoke）已 operator cancel cleanup（現 run_state
status=cancelled）。設計缺陷：每日 04:00 cron fire 會持續累積 zombie。

**修法（operator + PM 拍 register-only minimal）**：smoke 改 register-only —
保留 register（寫 experiments row → keep `[48]`），移除 run dispatch（不 POST
`/replay/run`，不製造 run_state zombie）。

## 2. 修改清單

| 檔 | 改動 |
|---|---|
| `srv/helper_scripts/cron/m11_replay_runner_daily_cron.sh` | 移除 Step 2 `POST /replay/run` + run_id/status 解析 + `smoke_completed` audit；改 register-only success path（emit `m11_replay_runner_register_only_completed`）；MODULE_NOTE 加 DESIGN-FIX 段；START/END log + fail-soft 註解 + helper alert_type 註解同步改 |
| `srv/helper_scripts/cron/install_m11_replay_runner_cron.sh` | echo / 註解提到 run 的三處改為 register-only：Stage A 描述、dry-run 第 3-4 步提示（驗 register_only_completed + run_state 無新 running row）、binary preflight 註解 |

兩檔 `bash -n` 通過（Mac + trade-core remote 均驗）。

### 關鍵 diff（wrapper 核心邏輯）

移除的 run dispatch 區塊（原 Step 2，~70 行）被替換為 register-only success path：

```bash
echo "[$(ts)] OK register http=$REGISTER_HTTP experiment_id=$EXPERIMENT_ID" >> "$LOG"

# register-only heartbeat 完成（DESIGN-FIX 2026-05-29：移除 POST /replay/run）
END_EPOCH=$(date -u +%s)
DUR=$((END_EPOCH - START_EPOCH))
echo "[$(ts)] OK m11_replay_runner_daily_cron register-only experiment_id=$EXPERIMENT_ID dur=${DUR}s" >> "$LOG"
printf '{"ts":"%s","status":"ok","mode":"register_only","experiment_id":"%s","duration_sec":%s,"datestamp":"%s"}\n' \
    "$(ts)" "$EXPERIMENT_ID" "$DUR" "$DATESTAMP" >> "$JSONL"
emit_governance_audit 'm11_replay_runner_register_only_completed' ...
exit 0
```

`register` 段（curl POST /experiments/register + experiment_id 解析 + register FAIL
fail-soft exit 0）+ heartbeat sentinel + governance_audit_log helper **全部保留**。

## 3. PA spec 原意判斷（deviation flag）

**PA spec 原意 = register + run + poll**，本修法為 **deviation**：

- PA proposal `2026-05-28--m11_replay_runner_schedule_proposal.md` §4.2 contract
  item 4-6 明寫：POST register → POST run → poll status until terminal（5 min
  timeout）。
- §5.2 timeline + wrapper 原 MODULE_NOTE line 22 亦寫「走完 register → run →
  poll status」。
- 所以 register-only 是對 PA spec 的 deviation。

**deviation 理由（已在 wrapper MODULE_NOTE DESIGN-FIX 段 + 本 report 明示）**：

1. `[48]` healthcheck `check_48_replay_manifest_registry_growth`
   (`checks_replay_maintenance.py:348-428`) **只 query `replay.experiments`** row
   growth（total/rows_7d/rows_24h/created_at），完全不碰 `replay.run_state`。
   register 成功即 keep `[48]` PASS。
2. run dispatch 唯一作用是製造 run_state row；single-fixture run hang 即留
   zombie（首次 install smoke 即留 `6532fc38`），daily fire 累積，觸 `[50]`
   FAIL。run 製造 zombie 得不償失。
3. 真實 replay 執行（含完成 + exit_code 追蹤 + cohort nightly）是 M11 Track C /
   Stage B 範圍（Sprint 3 Phase A，per PA proposal §1.2 / M11 spec §10.1），
   非 daily heartbeat。

PA spec §5.4 自己提了「`[50]` zombie 'running' > 1h 偵測」作 mitigation，但低估了
single-fixture run hang 的實際頻率（install smoke 即觸發）。register-only 從源頭
消除 zombie，比依賴 `[50]` 事後偵測更 robust。

## 4. dry-run 結果（trade-core empirical 2026-05-29）

方法：`scp` 改版 wrapper 到 trade-core `/tmp/m11_register_only_dryrun.sh` 跑（不動
tracked 檔，跑完 `rm`；runtime wrapper 維持舊版 b2e06510，待 main session 部署
committed 版）。

### baseline（dry-run 前）
- `replay.run_state` running = **0**（舊 zombie `6532fc38` 已 operator cancel →
  status=cancelled）
- `replay.experiments` total=24 / 24h=1 / 7d=1

### register-only 跑（exit 0）
- log: `OK register http=200 experiment_id=be8bd4b4-...` →
  `register-only heartbeat END OK`；**無 `POST /replay/run` 行、無 `OK run` 行**
- JSONL: `{"status":"ok","mode":"register_only","experiment_id":"be8bd4b4-...","duration_sec":0}`
  （**無 run_id**）
- governance_audit_log: `m11_replay_runner_register_only_completed` 1 row 寫入

### post-run 驗證
| 檢查 | 期望 | 實測 |
|---|---|---|
| (a) register 寫 experiments row | total 增 | total=**25** / 24h=2 / 7d=2；newest=be8bd4b4 ✅ |
| (b) 不 dispatch run（無新 run_state running） | 0 新 running | run_state running=**0**；max(created_at)=05-28 18:53（無 02:37 新 row）✅ |
| (c) exit 0 | 0 | 0 ✅ |
| `[48]` healthcheck | PASS | **PASS** `total=25 rows_7d=2 rows_24h=2 last_age=0.0h — registry growth healthy` ✅ |
| run_state status breakdown | running=0 | cancelled=1 / completed=17 / failed=6 / **running=0** ✅ |

**結論**：register 寫 experiments row（`[48]` 仍綠）+ 0 新 run_state running（無新
zombie）+ exit 0，三項全達標。

## 5. 治理對照

| 邊界 | 行為 | 合規 |
|---|---|---|
| live gates（live_execution_allowed / OPENCLAW_ALLOW_MAINNET / authorization.json / live_reserved） | 全不觸（cron 只 POST register thin handler） | ✅ |
| 不改 replay_runner binary | 只改 shell wrapper + install echo | ✅ |
| 不改 PG schema | INSERT 走既有 register endpoint，無 DDL | ✅ |
| 單一寫入口 | register 走既有 thin handler，非 raw SQL | ✅ |
| 跨平台 | Linux-only gate 保留；無硬編碼路徑（env-driven） | ✅ |
| fail-closed | register fail → fail-soft exit 0 + audit；不隱藏 retry | ✅ |
| 不 commit | 等 E2 審查 + E4 回歸後 PM 統一 commit | ✅ |

## 6. 不確定之處

1. **`m11_replay_runner_register_only_completed` event_type 仍 piggyback
   `audit_write_failed`**（V035 enum 未含 m11_*；對齊 replay_key_rotation_check.sh
   pattern）。Sprint 3 Phase A 同步擴 V### enum 為既有 follow-up（OQ-2），本 fix
   不動。
2. **install script binary preflight 保留**：register-only 本身不 spawn 子進程，
   binary 非嚴格必需。保留是為 (a) `[47] replay_runner_binary` healthcheck 一致性
   (b) Stage B cohort nightly 升級就緒。若 E2 認為應移除，可討論——但移除會與
   `[47]` 期望脫鉤，傾向保留。
3. **deviation 是否需 PA 回簽**：register-only 偏離 PA spec §4.2 contract。
   operator + PM 已拍 register-only minimal，本 fix 執行該決定；若需 PA 更新
   proposal §4.2 contract 文字對齊 register-only，屬 PA follow-up（非 E1 範圍）。

## 7. Operator / PM 下一步

1. **派 E2 對抗審查** + **E4 回歸**（per 強制鏈；本 IMPL 不自宣 sign-off）。
2. E2/E4 通過後 **PM 統一 commit + push**（1 commit：wrapper register-only +
   install echo 對齊）。建議 commit message 點明 deviation（register-only vs PA
   spec register+run）+ ticket P2-M11-SMOKE-ZOMBIE-DESIGN-FIX。
3. 部署：committed wrapper 同步到 trade-core（runtime 現為舊 b2e06510 register+run
   版）。**下次 04:00 UTC cron fire 前部署**，避免再積 zombie。純 shell 改動，無需
   `--rebuild`（無 binary/PyO3 變動）。
4. **PA follow-up（可選）**：更新 proposal §4.2 contract 文字對齊 register-only +
   把 run dispatch 明確歸 Stage B / Track C。

---

**E1 IMPLEMENTATION DONE：待 E2 審查 + E4 回歸（不自宣 sign-off）**
