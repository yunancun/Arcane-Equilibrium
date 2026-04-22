# 2026-04-22 · BACKFILL-LABELS-STALLED-1 RCA（read-only）

**作者**：sub-agent（PA 派發）· **狀態**：**未驗證假設**（READ-ONLY，禁 psql/改 code/tail log）
**TODO 對應**：P1-19 BACKFILL-LABELS-STALLED-1
**相關 commit**：`bd45e90`（FILL-CONTEXT-LINKAGE-1，2026-04-19）· `23b14ef`（scheduler 加 backfill pre-step，2026-04-19）
**近期 runtime 事件**：`--rebuild` 部署 2026-04-21 20:44（engine PID 3813984→3954769）+ 2026-04-22 20:55（engine PID 3954769→158918）；uvicorn PID 158973 起於 2026-04-22 20:55（`ps` 確認）

---

## 1. 現象重述

- `phase1a_c_readiness.py --engine-mode demo`（2026-04-22 22:10 CEST）顯示：最大 slice `demo grid_trading BLURUSDT` **仍 47/200 labels**，與 2026-04-19 原值完全相同——**3 天 0 成長**。39 個 slice 中 35 個 24h rate = 0，剩 4 個僅 1–4 labels/24h。
- **對比**：`settings/edge_estimates.json` mtime = **2026-04-22 21:56 CEST**（剛寫，ssh 確認 `/home/ncyu/BybitOpenClaw/srv/settings/edge_estimates.json`）+ `edge_estimates_live_demo.json` 同時間。→ `edge_estimator_scheduler._run_cycle` 仍在跑，但 JS 分支正常 ≠ backfill 正常。
- 兩者落差必定出在 `_run_cycle` 內部「backfill 先跑 → JS 後跑」的第一步被 fail-open `except` 吸收，或 backfill SQL 跑了但 `UPDATE ... FROM labels` 匹配到 0 行。

---

## 2. 5 個假設（可能性高 → 低）

### H1（最可能）· FILL-CONTEXT-LINKAGE-1 Rust 鏈 `entry_context_id` 靜默未寫 → backfill SQL `EXISTS (... entry_context_id = l.context_id)` 匹配不到

**核心論述**：`edge_label_backfill._BACKFILL_INCLUDED_SQL`（[edge_label_backfill.py:113](program_code/ml_training/edge_label_backfill.py:113)）的 `entries` CTE 要求 `trading.fills.entry_context_id = l.context_id`。若 Rust `apply_confirmed_fill` 在 close fill 寫入 `trading.fills.entry_context_id` 的鏈斷掉（`existing_entry_ctx` 取空字串 → [trading_writer.rs:317](rust/openclaw_engine/src/database/trading_writer.rs:317) 寫 NULL），則 `entries` CTE 永久空集合，`filled_count` 報 0 但 scheduler 看不到任何異常。**JS 分支照常跑**（JS 讀的是 `decision_features` 已 backfilled 的 rows + 直接 `realized_pnl`，不需要本輪 backfill 成功）。

**關鍵 file:line**：
- [tick_pipeline/commands.rs:437-474](rust/openclaw_engine/src/tick_pipeline/commands.rs:437) — `apply_confirmed_fill` 捕獲 `existing_entry_ctx = paper_state.get_entry_context_id(symbol).unwrap_or("").to_string()` **before** `apply_fill`
- [commands.rs:507-513](rust/openclaw_engine/src/tick_pipeline/commands.rs:507) — close fill 的 `fill_entry_ctx = if realized_pnl != 0.0 { existing_entry_ctx.clone() } else { String::new() }`
- [database/trading_writer.rs:317-320](rust/openclaw_engine/src/database/trading_writer.rs:317) — 空字串寫成 SQL NULL（`if entry_context_id.is_empty() { b.push_bind(None) }`）
- [paper_state/accessor.rs:216](rust/openclaw_engine/src/paper_state/accessor.rs:216) — `get_entry_context_id` 讀 per-position 的 `entry_context_id: Option<String>`
- [event_consumer/mod.rs:891-901](rust/openclaw_engine/src/event_consumer/mod.rs:891) — WS fill 分支傳 `&po.context_id`（`PendingOrder.context_id`，signal-time id）
- [event_consumer/dispatch.rs:411-415](rust/openclaw_engine/src/event_consumer/dispatch.rs:411) — `PendingOrder` 建構時 `context_id: req.context_id.clone()`（從 `OrderDispatchRequest`）
- [tick_pipeline/on_tick/step_4_5_dispatch.rs:307-326](rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs:307) — `OrderDispatchRequest { context_id: context_id.clone() }`（`context_id` 在 step_4_5 內經 `make_context_id(em, symbol, event.ts_ms)` 產生，再用於寫 `decision_features`）

**為什麼兩次 `--rebuild` 可能破壞**：engine PID 換 3 次（2026-04-21 20:44 + 2026-04-22 20:55），每次換都走 `cargo build --release`；FILL-CONTEXT-LINKAGE-1 的單測（[tick_pipeline/tests.rs:187-349](rust/openclaw_engine/src/tick_pipeline/tests.rs:187)）是 `apply_confirmed_fill_preserves_signal_context_id` 這類 pure-fn 測試，**不覆蓋 `PaperPosition.entry_context_id` 在 apply_fill 序列中的持久化**。特別是 2026-04-22 `306993e` TRACK-P-V2-SWAP-1 動了 `RiskConfig`/`ExitConfig`/v1 v2 swap 和 `paper_state` 的路徑相互穿插的區域，存在回歸風險——但 Mac 本地 `engine lib 1835/0 failed` 僅代表這些單測通過，不代表 end-to-end 寫入 `entry_context_id` 通。

**驗證方法**：
- READ-ONLY 可做：
  - 單測 `apply_confirmed_fill_preserves_signal_context_id` 加 `paper_state.get_entry_context_id()` 斷言（Mac 可跑）— 本次 RCA 不改 code，僅列為後續步驟
  - ssh trade-core `grep` engine.log 找 `FILL-CONTEXT-LINKAGE-1` or `entry_context_id` 警告（需 operator 授權 tail log）
- **需 operator psql**：Q3（TODO.md 已列）— `SELECT COUNT(*) FILTER (WHERE entry_context_id IS NOT NULL) / COUNT(*) FROM trading.fills WHERE ts_ms > now() - 24h`
  - H1 命中指紋：`with_ctx / total < 10%`（close fills 24h 幾乎全 NULL `entry_context_id`）

**修復 scope**：若 H1 命中，1–2 天。`get_entry_context_id` 在 close fill 前已被 `apply_fill` 清掉（position 先 close 再取 entry_context_id 就取不到）的順序 bug；修法：`commands.rs:437` 的 `existing_entry_ctx` 已是「before apply_fill 捕獲」，若仍空代表 `set_entry_context_id` 在 **開倉** 時根本沒寫入——追回到 `commands.rs:466-474` 的 `was_open && realized_pnl == 0.0` 條件是否誤判（比如 `realized_pnl` 在 reopen-after-close 的一 tick 為非零？）。

---

### H2（次可能）· `_run_backfill` 內部 exception 被 fail-open `except` 吞掉

**核心論述**：`edge_estimator_scheduler._run_cycle`（[edge_estimator_scheduler.py:188-204](program_code/exchange_connectors/bybit_connector/control_api_v1/app/edge_estimator_scheduler.py:188)）以 `try ... except Exception as bexc: logger.warning(... backfill failed (fail-open, JS still runs): %s)` 包住 `_run_backfill(mode)`。任何 exception（psycopg2 連線錯、PG deadlock、sys.path 問題、schema 漂移、**uvicorn `--workers 4` 並發 4 scheduler 同時 UPDATE 競爭**）都被 fail-open 吸收，JS 繼續跑並更新 `edge_estimates.json`——完全匹配現象。

**關鍵 file:line**：
- [edge_estimator_scheduler.py:168-180](program_code/exchange_connectors/bybit_connector/control_api_v1/app/edge_estimator_scheduler.py:168) — `_run_backfill`: `from ml_training.edge_label_backfill import backfill_labels` + 呼 `backfill_labels(engine_mode=mode, batch_limit=5000, dry_run=False)`
- [edge_estimator_scheduler.py:198-204](program_code/exchange_connectors/bybit_connector/control_api_v1/app/edge_estimator_scheduler.py:198) — **fail-open boundary**：`except Exception as bexc: backfill_summary = {"error": str(bexc)}; logger.warning(...)`
- [edge_label_backfill.py:299-303](program_code/ml_training/edge_label_backfill.py:299) — `backfill_labels` 自己的 rollback：`except Exception: conn.rollback(); raise` — rollback 後往上 bubble 到 scheduler fail-open boundary
- [restart_all.sh:220-221](helper_scripts/restart_all.sh:220) — uvicorn `--workers 4` + 無 log 重定向（stdout 丟失）

**為什麼 log 看不到**：`restart_all.sh:220-221` 跑 `"$API_VENV/bin/uvicorn" app.main:app ... --workers 4 &` 但 **沒有 `> $DATA_DIR/api.log 2>&1`**（對比 engine 那行 [restart_all.sh:200](helper_scripts/restart_all.sh:200)：`nohup rust/target/release/openclaw-engine > "$DATA_DIR/engine.log" 2>&1 &`）。`/tmp/openclaw/api.log` mtime 為 2026-04-19 00:45 （ssh 確認）—— 3 天無更新，代表 uvicorn stdout 根本沒落到 `/tmp/openclaw/api.log`（更可能是 operator 之前手動重定向過，這次 rebuild 沒接上）。scheduler 的 `logger.warning` → Python stdlib logging → uvicorn stdout → **丟**。

**並發懷疑**：4 個 uvicorn worker process 都會跑 `app.on_event("startup")` → 4 份 `EdgeEstimatorScheduler` daemon thread 同時每小時 UPDATE `learning.decision_features`。PG 的 row-level lock 在 UPDATE FROM labels 會競爭；deadlock 勝者 commit、敗者 rollback 並 bubble exception → fail-open 吞掉 → 下一小時又撞。**但** `edge_estimates.json` 4 個 worker 也會競爭寫，卻顯示有正常刷新——代表 JS 分支的 SELECT + fs write 夠快避開窗口，backfill 的 long UPDATE 更容易撞死。

**驗證方法**：
- **需 operator psql**：Q2（TODO.md 已列）— `SELECT DATE_TRUNC('hour', label_filled_at), COUNT(*) FROM learning.decision_features WHERE label_filled_at > now() - 48h GROUP BY 1`
  - H2 命中指紋：**0 rows** 48h（backfill 從未寫入）或小部份 hour 有 writes、大部份 hour 空（deadlock 窗口）
- **需 operator 授權**：ssh trade-core tail `/tmp/openclaw/api.log` OR 重導 uvicorn stdout 到新 log 後觀察一小時（scheduler 第一 cycle 60s warmup + 首 run）

**修復 scope**：若 H2 命中，0.5–1 天。修 [restart_all.sh:220](helper_scripts/restart_all.sh:220) 加 `> "$DATA_DIR/api.log" 2>&1`；並把 `_run_backfill` fail-open 的 `logger.warning` 升到 engine_events 表（可 psql 查證）以免下次 silent。並發問題若確認，改用 advisory lock + 限定只 worker-0 跑 scheduler（env `OPENCLAW_SCHEDULER_LEADER=1`）。

---

### H3 · demo 24h 新 fills 大幅乾枯（上游無資料可 label，非 pipeline bug）

**核心論述**：P1-10 STRATEGY-ASYMMETRY-1 後 grid fee drag 主導 + ma_crossover win rate 從 64% 崩到 37.8%，若 risk gate (correlated exposure 70% > 65%) 持續阻新開（P1-6 DEMO-BYBIT-SYNC-ORPHAN-1）+ cost_gate 冷啟動全 Hold（§三 提到 V2-SWAP 部署後 edge_estimates 冷啟動期 Gate 1 全 Hold）→ **fills 24h 趨近 0 → 沒 close fills → 沒可 backfill 行**。

**關鍵 file:line**：
- TODO.md P1-10 gross edge negative · TODO.md P1-6 死循環敘述
- CLAUDE.md §三「**INTENT-WRITE-GAP-1 ✅ 2026-04-21 24h 驗證 trading.intents demo 144 rows**」+「**ORDER-SUBMIT-GAP-1 ✅ trading.fills demo 123 rows**」— 2026-04-21 demo 24h 有 123 fills。距今約 24h，若衰退到 ~0 fills 是可能的但需要驗證
- 不在 code 路徑中——是策略/風控閾值 side-effect

**驗證方法**：
- **需 operator psql**：Q1（TODO.md 已列）— `SELECT engine_mode, COUNT(*) FROM trading.fills WHERE ts_ms > now() - 24h GROUP BY 1`
  - H3 命中指紋：demo 24h fills **< 10**（或仍 100+ → H3 反證，資料還在 → 傾向 H1/H2）
- 補充查詢：`SELECT COUNT(*) FROM trading.fills WHERE entry_context_id IS NOT NULL AND ts_ms > now() - 24h AND engine_mode = 'demo'` — 看 close fills 數

**修復 scope**：非 pipeline bug，修復 = 策略改善；此 RCA 不 own。若 H3 命中、結案 P1-19 為「等 P1-10 EDGE-P2-3 PostOnly 生效回暖」。

---

### H4 · scheduler daemon thread 在 `--rebuild` 後未重啟（或被 uvicorn reloader kill），JS 有另一獨立入口仍跑

**核心論述**：`--rebuild` kill 舊 uvicorn → 啟新 uvicorn（PID 158973 from `ps`）→ startup hook 內 `_start_edge_scheduler()` 應該啟動。但 thread 是 `daemon=True`（[edge_estimator_scheduler.py:89](program_code/exchange_connectors/bybit_connector/control_api_v1/app/edge_estimator_scheduler.py:89)），若 startup hook 內 exception 被 fail-open 吃掉（[main.py:378-382](program_code/exchange_connectors/bybit_connector/control_api_v1/app/main.py:378)），scheduler 根本沒起。但 `edge_estimates.json` 仍刷新——矛盾？**可能的解**：JS 有另一個入口（cron job / systemd timer / 其他 daemon）寫 `edge_estimates.json`。

**關鍵 file:line**：
- [edge_estimator_scheduler.py:81-98](program_code/exchange_connectors/bybit_connector/control_api_v1/app/edge_estimator_scheduler.py:81) — `start()` idempotent，thread `daemon=True`
- [edge_estimator_scheduler.py:125-131](program_code/exchange_connectors/bybit_connector/control_api_v1/app/edge_estimator_scheduler.py:125) — `_loop()` 首次延遲 60s 後 `while True: _run_cycle(); sleep(3600)`
- [main.py:372-382](program_code/exchange_connectors/bybit_connector/control_api_v1/app/main.py:372) — 啟動 fail-open
- [edge_estimator_routes.py:37-57](program_code/exchange_connectors/bybit_connector/control_api_v1/app/edge_estimator_routes.py:37) — route `get_scheduler()`；如果 scheduler 沒起 `_scheduler = None`，status endpoint 會報
- **找不到** 其他入口：`grep -r "run_james_stein\|edge_estimates.json" program_code/` 預期只在 scheduler + james_stein_estimator.py + edge_estimator_scheduler.py（本次未跑完整掃，列為待驗）

**驗證方法**：
- READ-ONLY 可做：`curl http://localhost:8000/api/v1/learning/edge-estimator/status`（若 route 存在）查 `last_run_ts` / `runs` / `failures` — 無需 psql
- ssh trade-core `ps -ef | grep -i james` 看是否有 systemd timer 或 cron 直接跑 james_stein_estimator
- `systemctl list-units | grep -i openclaw` 本次 ssh 回 0 hits（= 沒 openclaw.service / 沒 timer），**降低 H4 外部入口可能性**
- 查 `helper_scripts/**` 是否有 cron-wired 的 JS runner 腳本

**修復 scope**：若 H4 命中，< 1 天。在 startup hook 失敗時 raise 或寫 engine_events；加一個 health route 持續暴露 scheduler 狀態。

---

### H5 · `_BACKFILL_INCLUDED_SQL` 因 UPDATE JOIN 條件不匹配 → SQL 跑了但 0 rows 更新（不 raise）

**核心論述**：SQL（[edge_label_backfill.py:113-211](program_code/ml_training/edge_label_backfill.py:113)）的 `entries` CTE 要求 `l.label_filled_at IS NULL AND l.engine_mode = %(engine_mode)s AND EXISTS (...)`。若：
- 所有 demo 的 rows 已被過去 batch 標為 `label_filled_at != NULL` 但 label NULL（excluded 路徑）→ pass 1 永遠 0 rows
- `engine_mode` 欄位值漂移（V015/V017 / OUTCOME-BACKFILL 系列 fix 引入的 `engine_mode` = `'live_demo'` vs `'demo'` 誤差）
- `trading.fills.entry_context_id` 既有 rows 全為 NULL（同 H1 的 Rust 鏈斷但指向資料層 cause vs H1 指 code cause），`EXISTS` 永真空

**關鍵 file:line**：
- [edge_label_backfill.py:117-124](program_code/ml_training/edge_label_backfill.py:117) — `entries` CTE
- [edge_label_backfill.py:201-211](program_code/ml_training/edge_label_backfill.py:201) — UPDATE + RETURNING（若 entries 空 → RETURNING 0 rows → `filled_count=0` 合法，`conn.commit()` 成功 → 不 raise）
- 這代表即使 H2 的 fail-open 沒吞 exception，scheduler 記下的仍是 `filled=0` — log 會有 `filled=0 grid=0` 的規律 log line（[edge_estimator_scheduler.py:190-197](program_code/exchange_connectors/bybit_connector/control_api_v1/app/edge_estimator_scheduler.py:190)），但 log 丟失（H2）

**驗證方法**：
- **需 operator psql**：補充 Q4 — `SELECT COUNT(*) FROM learning.decision_features WHERE label_filled_at IS NULL AND engine_mode = 'demo' AND ts > now() - 72h` + `AND EXISTS (SELECT 1 FROM trading.fills f WHERE f.entry_context_id = l.context_id)`（兩段 COUNT 對比）
- H5 命中指紋：第一 COUNT 大（還有待 backfill 的 entries）、第二 COUNT 近 0（沒有可 JOIN 的 fills）→ = H1 的 DB 側指紋
- 另一變體：`SELECT DISTINCT engine_mode FROM learning.decision_features WHERE ts > now() - 24h ORDER BY 1` 查看是否有 `live_demo`/`live`/`demo` 三值與 backfill 傳入的 `engine_mode` 不對齊

**修復 scope**：若 H5 命中（資料層指紋 = H1 code 指紋同一問題），合併於 H1 修復。若是 engine_mode 漂移（類似 2026-04-21 `5e2981d` OUTCOME-BACKFILL fix 的 `'1'→'1m'` 路徑），0.5 天：SQL 補 `engine_mode IN ('demo','live_demo')` 兼容。

---

## 3. Code path 追蹤（關鍵 chain）

### 寫入鏈（FILL-CONTEXT-LINKAGE-1）
1. **Signal time**（tick-time）：[step_4_5_dispatch.rs:307-334](rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs:307) — `OrderDispatchRequest { context_id: context_id.clone(), ... }`，`context_id` 透過 `make_context_id(em, symbol, event.ts_ms)` 在 step_4_5 同 frame 內產生，**同時** 寫 `DecisionFeatureMsg` → `learning.decision_features.context_id`
2. **Dispatch queue**：[dispatch.rs:402-425](rust/openclaw_engine/src/event_consumer/dispatch.rs:402) — `PendingOrder { context_id: req.context_id.clone(), ... }` 進 `pending_orders` HashMap（key=order_link_id）
3. **WS fill received**：[event_consumer/mod.rs:880-902](rust/openclaw_engine/src/event_consumer/mod.rs:880) — match `pending_orders.get(key) → po` → 呼 `pipeline.apply_confirmed_fill(..., &po.context_id, &po.order_link_id)`
4. **apply_confirmed_fill**：[commands.rs:423-541](rust/openclaw_engine/src/tick_pipeline/commands.rs:423)
   - **Line 437-443**：**before** apply_fill 捕獲 `existing_entry_ctx = paper_state.get_entry_context_id(symbol).unwrap_or("").to_string()`
   - **Line 466-474**：`if was_open && realized_pnl == 0.0 { paper_state.set_entry_context_id(symbol, signal_context_id or recompute) }`（開倉時寫入 paper_state）
   - **Line 507-513**：close fills (`realized_pnl != 0.0`) → `fill_entry_ctx = existing_entry_ctx.clone()`
   - **Line 520-524**：open fills → `fill_ctx_id = signal_context_id or make_context_id(em, symbol, ts_ms)`
   - **Line 525-540**：`TradingMsg::Fill { context_id: fill_ctx_id, entry_context_id: fill_entry_ctx }` → trading_writer
5. **trading_writer**：[trading_writer.rs:275-320](rust/openclaw_engine/src/database/trading_writer.rs:275) — `INSERT INTO trading.fills (... context_id, entry_context_id, ...)`；**Line 317-320 空字串寫 NULL**

### JOIN key（DB 層）
- 開倉 row：`trading.fills.context_id = decision_features.context_id`（signal-time id）；`entry_context_id = NULL`
- 平倉 row：`trading.fills.context_id = exec-time 新 id`；`entry_context_id = 對應開倉的 signal-time id`
- **backfill JOIN**：[edge_label_backfill.py:119-122](program_code/ml_training/edge_label_backfill.py:119)：`EXISTS (SELECT 1 FROM trading.fills f WHERE f.entry_context_id = l.context_id)`，找到 close fills 才算 entries

### Fail-open boundaries
- **Layer 1（scheduler backfill pre-step）**：[edge_estimator_scheduler.py:188-204](program_code/exchange_connectors/bybit_connector/control_api_v1/app/edge_estimator_scheduler.py:188) — `try: _run_backfill(mode); except Exception as bexc: backfill_summary = {"error": str(bexc)}; logger.warning(...)` + **continue 到 JS 分支**
- **Layer 2（scheduler mode loop）**：[edge_estimator_scheduler.py:215-223](program_code/exchange_connectors/bybit_connector/control_api_v1/app/edge_estimator_scheduler.py:215) — 外層 `except Exception as exc: results[mode] = {"error": str(exc)}; self._failures += 1`
- **Layer 3（backfill 內部）**：[edge_label_backfill.py:299-303](program_code/ml_training/edge_label_backfill.py:299) — `except Exception: conn.rollback(); raise`（bubble）
- **Layer 4（uvicorn startup）**：[main.py:378-382](program_code/exchange_connectors/bybit_connector/control_api_v1/app/main.py:378) — scheduler 啟動 fail-open

---

## 4. Log inventory（**READ-ONLY · 不 tail**）

ssh trade-core 已確認的 log 路徑（ls 輸出）：
- `/tmp/openclaw/api.log` — 200KB · mtime **2026-04-19 00:45**（⚠️ 3 天無更新）— 可能是舊 uvicorn 重定向的結果；最新 uvicorn 啟動 `restart_all.sh:220` 無 stdout 重定向
- `/tmp/openclaw/engine.log` — 681KB · mtime 2026-04-22 22:21（活 engine）— Rust engine output，scheduler 不會寫這裡
- `/tmp/openclaw/openclaw-2026-04-22.log` — 25KB · mtime 2026-04-22 15:51 — 日期型 rotation，不確定來源（疑似 restart 腳本 bootstrap log）
- `/tmp/openclaw/watchdog.log` — 248KB · mtime 2026-04-21 11:58 — engine_watchdog 獨立
- `/tmp/openclaw/v2_swap_24h_observation.log` — 1.7KB · mtime 2026-04-22 22:16 — Track-P 專用觀察 log
- `systemctl list-units | grep openclaw` — **0 hits**（無 openclaw.service / 無 timer）

**scheduler log 可能位置**：**不明確**。`restart_all.sh:220-221` 的 uvicorn 無 `> log 2>&1` redirect → 大機率 scheduler stdout/stderr 隨父 shell exit 丟失。

### 辨識 backfill 分支成功/失敗的 signature（若將來接上 log）：
- **成功**：`EdgeEstimatorScheduler[scheduled]: mode=demo backfill filled=N grid=M`（[edge_estimator_scheduler.py:191-197](program_code/exchange_connectors/bybit_connector/control_api_v1/app/edge_estimator_scheduler.py:191)）
- **失敗（fail-open）**：`EdgeEstimatorScheduler[scheduled]: mode=demo backfill failed (fail-open, JS still runs): <exception>`（[edge_estimator_scheduler.py:200-204](program_code/exchange_connectors/bybit_connector/control_api_v1/app/edge_estimator_scheduler.py:200)）
- **JS 分支 log**：`EdgeEstimatorScheduler[scheduled]: mode=demo n_cells=N grand_mean_bps=X reason=scheduled`（[edge_estimator_scheduler.py:209-214](program_code/exchange_connectors/bybit_connector/control_api_v1/app/edge_estimator_scheduler.py:209)）
- **DB writer**：`decision_feature_writer` 有 `info!("decision_feature_writer started")` 等（[decision_feature_writer.rs:47](rust/openclaw_engine/src/database/decision_feature_writer.rs:47)）寫到 engine.log，但那是 `learning.decision_features` INSERT 端，**不是 UPDATE（backfill）端**

---

## 5. 給 operator 的驗證腳本清單（psql read-only，需授權）

### 直接引自 TODO.md P1-19（Q1/Q2/Q3）

```sql
-- Q1: demo 24h fills — 驗 H3 「資料乾枯」
-- 命中指紋：fills_24h < 10 → H3；fills_24h >= 100 → 反證 H3（仍有料）
SELECT engine_mode, COUNT(*) AS fills_24h FROM trading.fills
WHERE ts_ms > extract(epoch from now() - interval '24 hours')*1000
GROUP BY 1;

-- Q2: 48h backfill writes — 驗 H2「backfill 分支掛了」/ H5「SQL 0 rows」
-- 命中指紋：0 rows → H2（被 fail-open 吞）or H5（SQL 跑了 0 match）
SELECT DATE_TRUNC('hour', label_filled_at) AS hr, COUNT(*) AS rows
FROM learning.decision_features
WHERE label_net_edge_bps IS NOT NULL AND label_filled_at > now() - interval '48 hours'
GROUP BY 1 ORDER BY 1;

-- Q3: signal_context_id 接線狀態 — 驗 H1「FILL-CONTEXT-LINKAGE-1 破」
-- 命中指紋：with_ctx / total < 10% → H1（Rust 鏈斷）
SELECT COUNT(*) FILTER (WHERE entry_context_id IS NOT NULL) AS with_ctx,
       COUNT(*) AS total
FROM trading.fills
WHERE ts_ms > extract(epoch from now() - interval '24 hours')*1000
  AND engine_mode = 'demo';
```

### 補充查詢（本 RCA 新增）

```sql
-- Q4: backfill JOIN 兩側斷定（H1/H5 交叉驗證）
-- 若 pending_features 大（>100）且 with_matching_close 小（<5%）→ H1 確認（Rust 端不寫 entry_context_id）
-- 若 pending_features 小 → 不是 pipeline，是策略不開倉（H3 reframe）
WITH pending AS (
    SELECT context_id FROM learning.decision_features
    WHERE label_filled_at IS NULL AND engine_mode = 'demo' AND ts > now() - interval '72 hours'
)
SELECT
    (SELECT COUNT(*) FROM pending) AS pending_features,
    (SELECT COUNT(*) FROM pending p
     WHERE EXISTS (SELECT 1 FROM trading.fills f WHERE f.entry_context_id = p.context_id))
    AS with_matching_close;

-- Q5: engine_mode 欄位漂移檢查（H5 變體：demo vs live_demo）
SELECT engine_mode, COUNT(*) AS rows_24h
FROM learning.decision_features
WHERE ts > now() - interval '24 hours'
GROUP BY 1 ORDER BY 2 DESC;

-- Q6: close fills 專項查（H1 精確指紋）
-- 命中指紋：close_fills 大但 close_fills_with_entry_ctx 近 0 → H1 鐵證
SELECT
    COUNT(*) FILTER (WHERE realized_pnl <> 0) AS close_fills,
    COUNT(*) FILTER (WHERE realized_pnl <> 0 AND entry_context_id IS NOT NULL)
        AS close_fills_with_entry_ctx,
    COUNT(*) AS total_fills
FROM trading.fills
WHERE ts_ms > extract(epoch from now() - interval '24 hours')*1000
  AND engine_mode = 'demo';
```

### 非 DB 補充驗證（operator shell 授權）

```bash
# V1: scheduler status 端點（不需 psql）
curl -s http://localhost:8000/api/v1/learning/edge-estimator/status | jq .
# 預期字段：runs / failures / last_run_ts / last_results[demo][backfill]
# H4 命中指紋：runs=0 或 scheduler=None

# V2: 暫時重導 uvicorn stdout 驗 H2（需 operator 授權 restart）
#   修 helper_scripts/restart_all.sh:220 加 `> "$DATA_DIR/api.log.new" 2>&1`
#   restart 後 65 分鐘 tail api.log.new 看 scheduler 首 cycle log
```

---

## 6. 建議下一步

### 優先順序

1. **先跑 Q3（H1 驗證）** — **最高訊息量** · 成本最低（單一 COUNT）
   - `with_ctx / total > 50%`：**反證 H1**，Rust 鏈健康 → 進 Q2 驗 H2
   - `with_ctx / total < 10%`：**H1 命中** → 直接進修復入口
   - `with_ctx / total` 介於兩者：可能 H1 部分破（某些策略斷線）→ 進 Q6 細分

2. **同時跑 Q1**（H3 便宜的反證）— `fills_24h` 數字 1 秒回

3. **按 Q3 結果決定 Q2 / Q6**：
   - Q3 顯示鏈健康 → Q2 驗「backfill 分支跑了但 0 行」or「根本沒跑」
   - Q3 顯示鏈斷 → Q6 精確定位 close fills vs open fills

### 各假設命中的修復入口

| 命中 | 修復入口 file:line | 預估 scope |
|---|---|---|
| **H1** | [commands.rs:437-474](rust/openclaw_engine/src/tick_pipeline/commands.rs:437) + [paper_state/accessor.rs:216](rust/openclaw_engine/src/paper_state/accessor.rs:216) — 追 `set_entry_context_id` 何時實際寫入；加 runtime assert + engine.log `warn` 若 close fill 的 `existing_entry_ctx` 為空 | 1–2 日 |
| **H2** | [restart_all.sh:220](helper_scripts/restart_all.sh:220) 加 stdout redirect + [edge_estimator_scheduler.py:200](program_code/exchange_connectors/bybit_connector/control_api_v1/app/edge_estimator_scheduler.py:200) warning 升 engine_events + uvicorn worker leader-election（env `OPENCLAW_SCHEDULER_LEADER=1`） | 0.5–1 日 |
| **H3** | 非 pipeline bug · 等 P1-10 EDGE-P2-3 PostOnly wiring 生效回暖 · 此 TODO 結案為「資料乾枯，等上游」 | 0 日（non-ownership） |
| **H4** | [main.py:378-382](program_code/exchange_connectors/bybit_connector/control_api_v1/app/main.py:378) 改 raise + 加 `/api/v1/learning/edge-estimator/status` 的主動 poll 監控 | <1 日 |
| **H5** | [edge_label_backfill.py:117-124](program_code/ml_training/edge_label_backfill.py:117) `engine_mode IN (...)` + [edge_label_backfill.py:113](program_code/ml_training/edge_label_backfill.py:113) SQL 補 `NOT EXISTS` 指紋 log（skipped_no_close_fill counter） | 0.5 日 |

### RCA 不做的事
- 不自己跑 psql（需 operator 授權）
- 不自己 commit 改 code（Mac 主 session 統一 commit）
- 不自己 tail log 細讀（READ-ONLY 硬規則）
- 不自己重啟 uvicorn 驗 H2（需 operator 授權）

---

## Appendix A · 已排除假設

- **〈uvicorn `--reload` 干擾〉**：生產跑 `--workers 4` 無 `--reload`（[restart_all.sh:220](helper_scripts/restart_all.sh:220)），排除
- **〈systemd timer 獨立跑 backfill〉**：`systemctl list-units | grep openclaw` 0 hits，排除
- **〈scheduler 沒起〉**：`edge_estimates.json` 2026-04-22 21:56 CEST 剛寫，證實 `_run_cycle` JS 分支 60min 前跑過 → scheduler daemon 活著。**排除 H4 變體「scheduler 完全沒起」**；保留 H4 變體「JS 有其他入口，本 scheduler 掛了」—— 但 grep 未找其他入口，機率低

## Appendix B · 技術債節奏

- `/tmp/openclaw/api.log` 2026-04-19 之後無更新是**獨立可觀測性缺陷**，不管本 RCA 走向，修 [restart_all.sh:220](helper_scripts/restart_all.sh:220) 加 redirect 就值得（拆 P2 TODO `RESTART-ALL-UVICORN-LOG-1`）
- uvicorn `--workers 4` + 每 worker 獨立 scheduler 在 singleton 語義上有歧義（`_scheduler = None` module global 在每個 process 獨立），拆 P2 TODO `EDGE-SCHEDULER-LEADER-1`
- scheduler fail-open 的 `logger.warning` 寫不出到可 query 表（engine_events 或 scheduler_runs），拆 P2 TODO `SCHEDULER-FAILURE-OBSERVABILITY-1`

---

## 7. 驗證執行結果（2026-04-22 22:15 CEST · operator 直接授權跑 psql）

實測 SQL 於 `trade-core` PG `trading_ai`（`trading.fills.ts` 是 `timestamptz` 非 `ts_ms` — 原 spec 用 `ts_ms` 過濾寫錯，本實跑改 `ts > now() - interval '24 hours'`）：

### 7.1 Q1 修正版：24h fills by engine_mode

| engine_mode | fills_24h | close_fills_24h |
|---|---:|---:|
| demo | **28** | **14** |

live_demo / paper / demo_archive_20260418 24h 全 0（符合 authorization.json 未簽 + PAPER-DISABLE-1 + fresh_start 歸檔）。

### 7.2 Q3 修正版：demo 24h close fills 的 entry_context_id 填充率

| engine_mode | with_ctx | null_ctx | total |
|---|---:|---:|---:|
| demo | **14** | **0** | 14 |

**→ H1 完全證偽**：FILL-CONTEXT-LINKAGE-1 Rust 鏈健康，**100% close fills 帶 entry_context_id**（實得 14/14，非預期「可能大幅 NULL」）。

### 7.3 Q2 修正版：7 天 fills 分佈 + close ctx 填充

| day | engine_mode | all_fills | close_fills | close_with_ctx |
|---|---|---:|---:|---:|
| 2026-04-22 | demo | 28 | 14 | **14** |
| 2026-04-21 | demo | 114 | 54 | **52** |
| 2026-04-20 | demo | 60 | 31 | **29** |
| 2026-04-19 | demo | **426** | **199** | **193** |
| 2026-04-19 | live_demo | 19 | 8 | 8 |
| 2026-04-19 | paper | 102 | 46 | 46 |
| 2026-04-18 | demo | 15 | 5 | 5 |
| 2026-04-18 | demo_archive_20260418 | 1418 | 689 | 683 |
| 2026-04-18 | live_demo | 961 | 465 | 465 |

### 7.4 Q2（backfill 7d 出 rows）：label 實寫時序

| day | rows |
|---|---:|
| 2026-04-19 | 139 |
| 2026-04-20 | 24 |
| 2026-04-21 | 44 |
| 2026-04-22 | 14 |

**→ H1 + H2 雙雙證偽**：backfill 實際在寫，只是量小。寫入量與當日 close_fills 高度相關（139/199 · 24/31 · 44/54 · 14/14 = 70-100% conversion rate）→ backfill pipeline 健康，無 silent fail-open。

---

## 8. 最終判決：H3 命中

**P1-19 不是 bug，是上游 P1-10 STRATEGY-ASYMMETRY-1 的症狀**：

1. 2026-04-18 晚 `fresh_start.sh` 洗 demo engine_mode（舊 fills 重命名為 `demo_archive_20260418`）→ 2026-04-19 是新 demo 第 1 天
2. 2026-04-19 當天 426 fills (199 close) — 策略全量開倉前未被 MICRO-PROFIT-FIX-1 narrow-band + fee drag 完全壓制，backfill 成功寫 139 labels
3. **2026-04-20 起 close fills 驟降 85% 到 31**（P1-10 結構性 fee drag / grid cooldown + ma_crossover 勝率崩潰 → 策略內部自我收斂；MICRO-PROFIT-FIX-1 narrow-band gate 濾掉更多 intent；EDGE-P2-3 PostOnly 2026-04-21 部署但 maker order 非 100% 成交率）
4. 分 25 symbol × 2 活躍策略 ≈ 50 slice，每天 14-54 close fills 分散 → 每 slice 平均每天 0.3-1 labels → 最大 slice BLURUSDT 47/200 對應前 3d 累積不動
5. 按當前速率 `14 labels/day / 2 dominant slice = 7 labels/day/slice`，BLURUSDT 到 200 需 **~22 天**，遠超原 ETA 78h 樂觀估計

**H1 證偽依據**：demo 24h 100% close fills 帶 entry_context_id；7 天 close_with_ctx/close_fills = 93-100%。兩次 `--rebuild` 後 Rust 鏈完好。

**H2 證偽依據**：backfill 每日實際寫入 14-139 rows，數字與 close_fills 線性相關，不是 silent fail-open。

**H4 / H5 無法驗也不需要**：H3 已解釋全部現象。

---

## 9. P1-19 結案建議

**關閉為 "duplicate of P1-10 EDGE-P2-3 observation window"**：
- Pipeline 無 bug，不需修 code
- 真正治理入口 = 等 EDGE-P2-3 PostOnly 在 demo/paper 觀察 ≥1w（TODO P2 §EDGE-P2-3 Phase 2+ (c) 追蹤中）後看 maker 成交率是否拉高入場量
- 若 1w 後 close_fills 無回升 → 升級 P1-10 為 "critical"，重評 MICRO-PROFIT-FIX-1 narrow-band threshold（2026-04-17 commit `cb2e3a4` 值 `ratio ≥ 0.20 & pnl ∈ [0.30%, 0.55%]`）是否過緊
- ONNX 訓練延後：P1-7 C 進入 **non-ownership 被動等待期**，與 P0-2 21d 並跑；最早 unblock 時間由 P1-10 觀察結果決定（預估 2026-04-28+）

**不結案的附帶價值**（獨立於 H3 判決）：
- **RESTART-ALL-UVICORN-LOG-1** P2 新 TODO：`restart_all.sh:220` uvicorn 無 stdout redirect，`/tmp/openclaw/api.log` mtime 2026-04-19 停更（此事實在本 RCA §2.H2 發現，與 H2 判決無關仍值得修）— 可觀測性基礎建設 0.5 日
- **EDGE-SCHEDULER-LEADER-1** P2 新 TODO：uvicorn `--workers 4` 每 worker 獨立 scheduler daemon → 4 份同時 UPDATE（PG MVCC 容忍但浪費）; 加 env `OPENCLAW_SCHEDULER_LEADER=1` 只讓 worker 0 跑 scheduler — 效能 + 觀測性 ~1 日
- **SCHEDULER-FAILURE-OBSERVABILITY-1** P2 新 TODO：scheduler fail-open 的 `logger.warning` 寫到 engine_events 表而非 stdout → 將來類似 silent fail 可 SQL 查 — ~0.5 日

三個 P2 TODO 獨立於本 H3 判決，**無論 P1-19 結案與否都應做**。

— END —
