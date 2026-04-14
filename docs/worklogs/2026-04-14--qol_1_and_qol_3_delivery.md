# 2026-04-14 · QoL-1 + QoL-3 Delivery Worklog

**Scope**: 兩項 Quality-of-Life 改善 — paper_state 重啟還原（QoL-1）與 PyO3 .so 統一部署（QoL-3）。
**Role chain**: PM+FA → PA → E1(×2 平行 worktree) → E2/QA 驗證 → merge → rebuild + restart + log 驗證。
**Outcome**: 兩項均上線，engine lib 測試 1136 → **1144**（+8），總 Rust **1543 pass / 0 fail**。

---

## 一、立項背景

TODO.md §「2026-04-12 GUI/Metrics 修復時發現（非阻塞）」列 4 項 QoL：
- **QoL-1** 引擎重啟後 `paper_state.total_realized_pnl / total_fees / trade_count` 歸零 — 記憶體變量無持久化，GUI 累計 PnL 卡片每次重啟顯示 0。Python 側靠 metrics 端點 DB 降級繞過，但 Rust snapshot 本身仍為 0，治理/cost_gate 等內部消費方拿不到正確累計。
- **QoL-3** PyO3 `.so` 部署不統一 — `maturin develop` 默認裝到 `~/.venv`，但 API server 跑在 `control_api_v1/.venv`。Rust struct 改動後需手動 `maturin develop` 兩次，漏裝一次就是 GUI 和引擎看到不同 schema 的 bug。
- QoL-2（Demo AI cost 追蹤）依賴 G-1 AI 治理層，暫不處理。
- QoL-4 已由 PNL-FIX-1 commit `2a422fa` 處理掉。

User 指令：「先做1和2，FA PA分析下，然後平行派發後台處理」。

---

## 二、FA / PA 分析要點

### QoL-1 — PaperState 還原
- 數據源：`trading.fills` 已存在 `engine_mode TEXT NOT NULL` 欄 + `idx_fills_engine_mode_ts`，可按引擎隔離聚合。
- Schema 對齊：欄位是 `fee REAL` / `realized_pnl REAL`（非 `_usd` 後綴），無 `close_tag` 欄。
- 聚合公式：
  ```sql
  SELECT COALESCE(SUM(fee),0)::float8,
         COALESCE(SUM(realized_pnl),0)::float8,
         COALESCE(COUNT(*) FILTER (WHERE realized_pnl <> 0),0)::bigint
  FROM trading.fills WHERE engine_mode = $1
  ```
  `trade_count` 只數 close leg（`realized_pnl <> 0`）避免 open/close 雙記。
- Fail-soft 合約（憲法 §5.5 「生存 > 利潤」）：
  - `audit_pool = None` → info log + 保持零（冷啟動 / PG 停用）。
  - SQL 錯誤 → warn log + 保持零。**引擎必須一定能啟動**。
  - 成功 → info log 帶還原值，讓 operator 比對 GUI。
- 檔案大小紀律：SQL + 觸發邏輯獨立成 `event_consumer/paper_state_restore.rs`（沿用 `governor_cooldown.rs` 樣式），避免 `event_consumer/mod.rs` 持續膨脹。

### QoL-3 — 統一 PyO3 部署
- 現狀痛點：`maturin develop` 一次裝一個 venv，容易漏；且每個 venv 都會觸發一次完整編譯。
- 策略：改用 `maturin build` 生成 wheel 一次，然後 `pip install --force-reinstall --no-deps` 到每個目標 venv。
- 預設雙寫目標：
  1. `~/.venv`
  2. `<project>/program_code/exchange_connectors/bybit_connector/control_api_v1/.venv`
- 可選 `--venv <path>` 單目標、`--debug`、`-n/--dry-run`、`--help`。
- 跨平台考量（CLAUDE.md §七）：
  - `stat -c` (Linux) + `stat -f` (BSD/macOS) 雙 fallback。
  - bash 4+ guard（macOS 預設 bash 3.2，需 `brew install bash`）。
  - `mktemp -d -t` 可攜寫法 + `trap 'rm -rf' EXIT` 清理。
- 集成至 `restart_all.sh`：新增 `--rebuild` 旗標；parse 階段接受任意位置；build 失敗 → exit 2 不啟動服務。
- **Scope 邊界（重要，避免誤解）**：`--rebuild` 只重建 **PyO3 .so**（`openclaw_pyo3` crate → `openclaw_core` Python module）。**不重建 `openclaw-engine` binary**。引擎本體改動仍需 `cargo build --release --bin openclaw-engine`。

### Merge 策略
- 兩任務完全獨立：QoL-1 改 Rust 引擎內部、QoL-3 只動 helper scripts。
- 用 git worktree 隔離平行執行，避免共享工作樹衝突。
- Merge 順序：QoL-3 先（純腳本，零運行風險）→ QoL-1（需配合 rebuild + restart）。

---

## 三、實施細節

### QoL-1 檔案變更

**新增** `rust/openclaw_engine/src/event_consumer/paper_state_restore.rs`（81 行）：
- `restore_paper_counters(pipeline, pipeline_kind, audit_pool)` — fail-soft glue。
- 三分支：`None pool` → info；`SQL Err` → warn；`Ok(())` → info with `total_realized_pnl / total_fees / trade_count`。
- 全部 log 雙語（CLAUDE.md §七強制）。

**擴充** `rust/openclaw_engine/src/paper_state.rs`（866 → 1107 行，+241）：
- `async fn restore_from_db(&mut self, pool: &PgPool, engine_mode: &str) -> Result<(), sqlx::Error>`
- `fn apply_restored_counters(&mut self, fees_sum, pnl_sum, trade_count_i64)` — 純函數 helper，方便 unit test。
- 公開 accessors：`total_realized_pnl()`、`trade_count()`。
- `balance` / `peak_balance` 重建公式：`initial_balance + realized_pnl_sum - fees_sum`（與 accumulating path 一致）。
- +8 unit tests（純函數 + 邊界 + fail-soft 契約）。

**接線** `rust/openclaw_engine/src/event_consumer/mod.rs`（+6 行）：
```rust
mod paper_state_restore;
// ... 在 TickPipeline::with_kind() 之後、import_positions 之前：
paper_state_restore::restore_paper_counters(&mut pipeline, kind, audit_pool.as_ref()).await;
```

**關鍵設計決策**：
- 按 `engine_mode` 隔離是 3E-ARCH 後的必然 — 三引擎共寫 `trading.fills`，若不過濾 paper 會吃 demo 的 PnL。
- `apply_restored_counters` 抽成 helper 讓 SQL 邏輯和賦值邏輯分開測試（SQL 測試要 PG 真連線，helper 測試純記憶體 < 1ms）。

### QoL-3 檔案變更

**新增** `helper_scripts/build_pyo3.sh`（285 行，`chmod +x`）：
- `set -euo pipefail` + bash 4 guard + cross-platform stat。
- Maturin 搜尋鏈：`control_api_v1/.venv/bin/maturin` → `~/.venv/bin/maturin` → `~/.cargo/bin/maturin` → `$PATH`。
- 流程：validate venvs → `mktemp -d` wheel dir → `maturin build` → 找 wheel → loop `pip install --force-reinstall --no-deps` → verify `.so` 存在 → cross-venv size 比對。
- Exit codes：0 ok / 1 args / 2 build / 3 install / 4 verify。
- `--dry-run` 打印計劃但不執行。

**修改** `helper_scripts/restart_all.sh`（+56 / -5）：
- 重寫 arg parser 接受 `--rebuild` 出現在任意位置 + `--engine-only|--api-only|all`。
- 新增 `rebuild_pyo3()` 函數包裹 `build_pyo3.sh` 呼叫；失敗 → `exit 2` 在啟動服務前中止。
- 向後相容：無旗標行為不變。

**更新** `helper_scripts/SCRIPT_INDEX.md`（+1 entry）。

---

## 四、Merge + 部署驗證

### 平行派發（worktree isolation）
```
.claude/worktrees/agent-ab1b2599 → QoL-1（feature/qol-1-paper-state-restore）
.claude/worktrees/agent-a09ae0ab → QoL-3（feature/qol-3-unified-pyo3-build）
```
兩 E1 平行成功完成，無 code-writing refusal（關鍵：`isolation: "worktree"` + 顯式「PM approved coding task」framing）。

### Merge commits
```
dc2eec3  Merge QoL-3: unify PyO3 build deployment across venvs
ea25844  Merge QoL-1: restore paper_state counters from trading.fills on startup
22a0b36  feat(qol-1): restore paper_state counters from trading.fills on startup
c510388  feat(qol-3): unify PyO3 build deployment across venvs
```
用 `--no-ff` 保留分支歷史便於回溯。

### 關鍵插曲 — 17:55 SIGTERM
Merge 完成後檢查 `engine_watchdog.py --status` 發現三引擎全掛，snapshot 757s stale。查 `/tmp/openclaw/engine.log` 看到 15:55:54 UTC（17:55 CEST）「SIGTERM received — shutting down」+ 「final state saved」乾淨關機。時間點**早於** merge（18:07 CEST）→ **與 merge 無因果**（git 不動已編譯 binary）。無 systemd 單元（`journalctl -u openclaw-engine` 無紀錄），SIGTERM 來源未確認（疑似外部 cron / 手動 kill）。**Action item**：下次 session 追查 SIGTERM 來源。

### User 選擇 Option B → rebuild + restart
糾正了 `restart_all.sh --rebuild` 只重建 PyO3 不重建引擎 binary 的誤解：
```
1. cargo build --release --bin openclaw-engine        # 19.76s 成功（2 dead_code warn 與本任務無關）
2. bash helper_scripts/restart_all.sh --engine-only --rebuild
   → build_pyo3.sh 雙寫 .so（兩邊 6915056B 一致）
   → pkill openclaw-engine → nohup 新 binary PID 178613
3. tail log 驗證 QoL-1 還原訊息
```

### 還原驗證（engine.log L115 / L117 / L159）
```
demo  → total_realized_pnl=-3.4911563396453857  total_fees=29.10846519470215  trade_count=254
paper → total_realized_pnl=-14.399180412292480  total_fees=58.20874786376953  trade_count=333
live  → total_realized_pnl= 0.0                 total_fees= 0.0               trade_count=  0
```
三引擎分別用各自 `engine_mode` 查詢 + fail-soft 合約守住 live（無歷史也要正常啟動）。

### 收尾
- `git worktree remove` 兩個 agent worktree + `git branch -D` 兩支 feature 分支。
- Doc commit `179822d`：TODO.md QoL-1/3 打勾 + CLAUDE.md §三 新增段落 + §十一 baseline 1535 → 1543。

---

## 五、測試基準線變動

| 層級             | 前        | 後        | Δ   |
|------------------|-----------|-----------|-----|
| engine lib       | 1136      | **1144**  | +8  |
| core             | 366       | 366       | 0   |
| e2e              | 33        | 33        | 0   |
| **Rust 總計**    | **1535**  | **1543**  | +8  |
| Python           | 2852      | 2852      | 0   |

+8 來自 QoL-1 的 `apply_restored_counters` helper + fail-soft glue unit tests。

---

## 六、後續 / 留尾

1. **SIGTERM 來源** — 追查 17:55 誰 kill 了引擎（外部 cron？pkill 殘留？）。非阻塞但詭異。
2. **QoL-2** 仍等 G-1 AI 治理層（per-engine AI cost 歸因無基礎）。
3. **G-2 污染窗口** — 重啟後 funding_arb demo 端 AAVEUSDT 已見新成交，驗證窗口繼續累積信號。`memory/project_g2_validation_contamination.md` 仍有效。
4. **文檔同步**：本 worklog 已寫入 `docs/worklogs/2026-04-14--qol_1_and_qol_3_delivery.md`；CLAUDE_CHANGELOG.md 尚未追加對應條目（可下次 commit 時補）。

---

## 七、一句話總結

> QoL-1 讓 GUI 累計 PnL 不再每次重啟歸零；QoL-3 讓 Rust struct 改動一條指令同步到所有 venv。兩項非阻塞改善但大幅降低日常摩擦，4 個 commit 合併 + engine 熱升級完成，測試基準線 1535 → 1543 pass。
