# 2026-04-14 Daily Summary

ENGINE-HEAL 5 Fix（Panic Hook + Crash-Only + WS Stale + Watchdog Auto-Restart + Zombie API 清理）· QoL-1 PaperState 重啟還原 + QoL-3 PyO3 雙 venv 統一部署 · Trailing Stop Activation Gate + `net_realized_pnl` fee attribution 修復。

## 完成項目 / Completed

### ENGINE-HEAL — 引擎自癒 5 Fix（單 session）
**觸發**：~11:38 CEST engine ws tick 停止，~11:52 CEST 靜默退出（無 panic log / shutdown 日誌 / crash dump），12:10 CEST operator 透過 GUI 發現 paper 無交易。事故當日 `restart_all.sh` 用 `>` truncate `engine.log` → 死因證據全滅 18 min。

**Phase 0 根因調查**（medium 30min）：排除 OOM / SIGKILL / `process::exit` / tokio deadlock。最可能根因 = panic 被吞 + tracing 未 flush 就退出。意外發現 `restart_all.sh` 的 `>` redirect 是系統性缺陷。現有自癒盤點：`engine_watchdog.py` 只記錄不重啟、無 systemd unit 守護 engine、`openclaw-trading-api.service` 因 port 衝突 restart 1074+ 次循環。

**Operator 批 3 決策**：D1 crash-only 語義含 Live · D2 WS tick stale 120s 閾值 · D3 Phase 0 medium 投資。

#### Fix 1 — Panic Hook 診斷可見性
`rust/openclaw_engine/src/main.rs:55-108` 在 tracing init 之後立即 `std::panic::set_hook`，捕獲 thread id / thread name / location / payload / `Backtrace::force_capture()` + `stdout/stderr.flush()`。覆蓋所有 tokio worker / `std::thread::spawn` / non-async path。不阻止 panic，只保證留下結構化日誌 — 其他 fix 驗證有效性的前提。

#### Fix 3 — Crash-Only Semantics（含 Live）
`main.rs:57-119` 新增 `run_pipeline_crash_only<F>()` helper；L882 paper / L940 demo spawn 改包；Live thread `catch_unwind` 後補 `live_cancel.cancel()`。任一 pipeline panic → `AssertUnwindSafe.catch_unwind` → `tracing::error!` `pipeline_crash` event → `AtomicU8 health=Down` → broadcast `EngineEvent::Crashed(kind)` → 全局 `CancellationToken.cancel()` → ordered shutdown → exit → watchdog 45s 內拉起。

**對比 isolate**：isolate 會讓三引擎共享的 `RiskConfigStore` 帶病繼續（靜默錯單）；crash-only 最糟停機 30-90s 但每次事故都有可查死因 + 無污染傳染。敏感交易「帶病繼續」比「停機 30s」風險高 1000×。

#### Fix 4 — WS Tick Stale 自救
`main.rs:1108-1155` 新增 watchdog task，`TICK_STALE_THRESHOLD_MS=120_000` + 30s polling。`last_tick_ms == 0` 冷啟動跳過；`now - last > 120s` → 觸發 `cancel_ref.cancel()` 並 `break`（單次觸發）。120s 而非 60s：Bybit 維護窗口 / CDN 故障轉移會產生 60-90s 靜默誤報。詳 `docs/known_issues/2026-04-14--ws_stale_detector.md`。

#### Fix 2 — Watchdog Auto-Restart + 4 道保險
`engine_watchdog.py` +180 行 helpers · `stop_all.sh` 新增 ~90 行 · `restart_all.sh` +50 行。

1. **`fcntl.flock` 單例** — `/tmp/openclaw/watchdog.lock` LOCK_EX|LOCK_NB，重複啟動 `BlockingIOError` → `exit 3`，防 operator 誤啟雙殺 engine。
2. **Maintenance flag** — `/tmp/openclaw/engine_maintenance.flag`：`stop_all.sh` 先建 flag 再殺 engine，`restart_all.sh` 清 flag；watchdog `should_restart()` 看到 flag 不重啟，避免誤以為事故。
3. **SIGTERM-first graceful kill** — `pkill -TERM` → 5s 輪詢 → 仍活則 `SIGKILL`。原直接 SIGKILL 會打斷 `paper_state.json` atomic rename 產生 `.tmp` 殘留 → `JSONDecodeError` → 虛假重啟循環。
4. **指數退避 + 熔斷** — `RESTART_BACKOFF_SECONDS=[60,120,300,600,3600]`，連續 5 次失敗 `circuit_broken=True` 停止重啟；`/tmp/openclaw/watchdog_state.json` 原子寫入持久化；`canary_events.jsonl` append-only 四事件（`RESTART_SUCCESS/FAILED/CIRCUIT_BROKEN/SKIPPED`）供 Grafana/PagerDuty tail。

**Bonus — Log Rotation**：`rotate_engine_log()` 在 restart 前將 `engine.log` mv 到 `/tmp/openclaw/engine_logs/engine-<epoch>.log`，cap 10 份 — 直接解決 `>` truncate 的根因放大器。

#### Fix 5 — Zombie `openclaw-trading-api.service` 清理
症狀：port 8000 被手啟 uvicorn 佔用 + systemd unit cwd 錯導致 `No module named 'program_code'` + `Restart=always` → 每 3-10s 重啟 1074+ 次。決策 B（禁用而非修復）：`systemctl --user disable --now` — 服務控制集中到 `restart_all.sh` 為唯一入口。sibling `openclaw-gateway.service`（8h uptime）不動。

### QoL-1 — PaperState 重啟還原
**痛點**：engine 重啟後 `total_realized_pnl / total_fees / trade_count` 歸零 → GUI 累計 PnL 卡片每次重啟顯示 0 → 治理/cost_gate 內部消費方讀不到正確累計。

**實施**：
- 新增 `rust/openclaw_engine/src/event_consumer/paper_state_restore.rs`（81 行）— `restore_paper_counters(pipeline, kind, audit_pool)` fail-soft glue：`None pool` / `SQL Err` / `Ok(())` 三分支均雙語 log，**引擎必須一定能啟動**（憲法 §5.5 生存 > 利潤）。
- 擴充 `rust/openclaw_engine/src/paper_state.rs`（866→1107，+241）— `async fn restore_from_db(&mut self, pool, engine_mode)` + `fn apply_restored_counters()` 純函數 helper + 公開 accessors `total_realized_pnl()` / `trade_count()` + `balance/peak_balance = initial_balance + realized_pnl_sum - fees_sum`。
- 接線 `event_consumer/mod.rs` +6 行：在 `TickPipeline::with_kind()` 之後、`import_positions` 之前呼叫 restore。
- **按 `engine_mode` 隔離**（3E-ARCH 必然）— 三引擎共寫 `trading.fills`，若不過濾 paper 會吃 demo 的 PnL。
- 聚合公式：`SUM(fee)`, `SUM(realized_pnl)`, `COUNT(*) FILTER (WHERE realized_pnl <> 0)` — 只數 close leg 避免 open/close 雙記。

**還原驗證**（engine.log post-deploy）：
```
demo  → total_realized_pnl=-3.49  total_fees=29.11  trade_count=254
paper → total_realized_pnl=-14.40 total_fees=58.21  trade_count=333
live  → total_realized_pnl=  0.0  total_fees= 0.0   trade_count=  0
```

### QoL-3 — PyO3 .so 統一部署
**痛點**：`maturin develop` 一次裝一個 venv（`~/.venv` vs `control_api_v1/.venv`），Rust struct 改動後漏裝一次就是 GUI 和引擎 schema 不一致 bug。

**實施**：
- 新增 `helper_scripts/build_pyo3.sh`（285 行）— 改用 `maturin build` 生成 wheel 一次 → `pip install --force-reinstall --no-deps` 分發到多個 venv。預設雙寫 `~/.venv` + `control_api_v1/.venv`，支援 `--venv <path>` / `--debug` / `-n/--dry-run` / `--help`。Exit codes 0/1/2/3/4（ok/args/build/install/verify）。
- **跨平台**（CLAUDE.md §七）：`stat -c`（Linux）+ `stat -f`（BSD/macOS）雙 fallback · bash 4+ guard（macOS 預設 3.2 需 `brew install bash`）· `mktemp -d -t` 可攜寫法 + `trap EXIT` 清理。
- 修改 `restart_all.sh`（+56/-5）：新增 `--rebuild` 任意位置接受；`rebuild_pyo3()` 失敗 → `exit 2` 不啟動服務。向後相容：無旗標行為不變。
- **Scope 邊界**：`--rebuild` 只重建 **PyO3 .so**（`openclaw_pyo3` crate → `openclaw_core` module），**不**重建 `openclaw-engine` binary — 引擎本體改動仍需 `cargo build --release --bin openclaw-engine`。
- 更新 `helper_scripts/SCRIPT_INDEX.md`（+1 entry）。

**驗證**：兩 venv `.so` size 一致 6915056B。

### Trailing Stop Activation Gate + net_realized_pnl Fee Attribution
**觸發**：Operator 報告 GUI 未實現 PnL 恒正 / 已實現 PnL 恒負。

**首輪誤診自我矯正**：Explore sub-agent 假設「unrealized GROSS vs realized NET 手續費非對稱」；直讀 `paper_state.rs:563-567`（unrealized 純 gross）/ `708-712`（realized 純 gross，fee 單獨記 `total_fees`）推翻。

**真 smoking gun**（`openclaw_core/src/stop_manager.rs` pre-fix L152-166）：啟動閘只要 `best_price > entry_price`（+$0.01 即算），但 `trail_price = best_price × 0.98` 可低於 entry。示範 long entry=$100 trail=2%：價格上衝 $100.10 啟動 → `trail_price = $98.10`（低於 entry $1.90）→ 回撤 $98 觸發 → **鎖定虧損**。加上策略無百分比止盈（`on_tick.rs` close 皆為信號翻轉），生存者偏誤 × trailing-at-loss → unrealized⁺ / realized⁻ 數學必然。

**方案選 B（教科書分離閾值）** vs A（`max(entry)` break-even guard）：B 新增 `trailing_activation_pct: Option<f64>`，預設等同 `trail_pct`，保證 `trail_price ≥ entry × (1 - trail_pct²/10000)`（2% 時 lock-in ≤ 0.04%）；operator 設 `activation > trail_pct` 得嚴格鎖利。

**Rust 實施**：
- `StopConfig` 新增 `trailing_activation_pct: Option<f64>` + `#[serde(default)]` 向後兼容。
- `check_trailing_stop()` 重寫（L154-213）：activation_price 分 long/short 計算 → 未啟動 return None。觸發時 `tracing::info!(event="trailing_stop_triggered", is_long, entry_price, best_price, trigger_price, trail_price, activation_pct, trail_pct, pnl_pct_approx, entry_ts_ms)` 結構化 log 供後續量化分析。
- IPC 熱重載鏈路接線：`paper_state.rs::set_trailing_activation_pct` clamp(0.0, 50.0) · `tick_pipeline/mod.rs::PipelineCommand::UpdateRiskConfig` · `event_consumer/handlers.rs` destructure + clamp(0.0, 0.5) + info log · `ipc_server/handlers.rs::parse_opt_opt_f64`。
- +6 單元測試（4 activation 基礎 + 2 本日延後補齊）：`test_trailing_stop_below_activation_skip_long/short` · `test_trailing_stop_explicit_activation_threshold` · `test_trailing_with_higher_activation_locks_profit` · `test_trailing_activation_zero_fires_at_entry`（文檔化舊行為）· `test_trailing_short_higher_activation_locks_profit`。
- +2 IPC 回環測試：`test_handle_update_risk_config_sets_trailing_activation_pct`（UpdateRiskConfig → assert setter + 顯式清除 `Some(None)` 路徑）。

**Python net_realized_pnl fee attribution（3+1 站點同語意）**：
```python
open_entry_fees = sum(p.get("entry_fee", 0.0) for p in positions)
closed_fees    = max(0.0, total_fees - open_entry_fees)
net_realized   = realized - closed_fees
```
- `paper_trading_routes.py:441,474`（/status）· `:631,640`（/pnl）— flat 訪問。
- `grafana_data_writer.py:208-213`（持久化 DB）— nested `p.get("position", {}).get("entry_fee", 0)` 對齊 `pipeline_snapshot.json` 的 `PositionSnapshot { position: PaperPosition }` 結構。
- `paper_trading_metrics.py:185-198`（本日延後補齊）— `compute_trade_metrics` 無 round-trips 時的 fallback，list / dict / None 三路徑防禦。

### SIGTERM 插曲
QoL Merge 完成（18:07 CEST）後發現 engine 17:55:54 UTC 乾淨 SIGTERM 關機，時間點**早於** merge → 無因果（git 不動已編譯 binary）。無 systemd 單元紀錄，來源未確認。**Action item**：下次 session 追查。

## 測試基準線 / Test Baseline
| 層級 | pre-session | ENGINE-HEAL 後 | QoL 後 | Trailing Stop 後 |
|---|---|---|---|---|
| engine lib | 1136 | 1136 | **1144**（+8）| **1146**（+2 IPC 回環）|
| core | 366 | 366 | 366 | **372**（+6）|
| e2e | 33 | 33 | 33 | 33 |
| **Rust 總計** | **1535** | **1535** | **1543** | **1551** |
| Python | 2852 | 2852 | 2852 | 2446 pass / 1 skip（0 regression）|
| watchdog unit | — | 8/8 PASS | 8/8 | 8/8 |
| `bash -n` | — | clean | clean | clean |

E2 審查結論：ENGINE-HEAL 5 Fix 全部審過；Trailing Stop `Merge-ready for demo/paper validation`。

## 關鍵決策 / Decisions
1. **Crash-only 含 Live**（D1）— 帶病繼續 >> 停機 30s 的風險比
2. **WS stale 120s 而非 60s**（D2）— Bybit 維護 / CDN 切換會 60-90s 靜默
3. **Phase 0 medium 投資**（D3）— 不追 gdb/core file（已無死屍）
4. **禁用 zombie API systemd unit 而非修復**（Fix 5 選項 B）— 服務控制集中到 `restart_all.sh` 唯一入口
5. **按 engine_mode 隔離 PaperState 還原** — 3E-ARCH 後三引擎共寫 `trading.fills` 的必然
6. **Trailing stop 選教科書 activation_pct 方案 B** vs break-even guard A — 給 operator 旋鈕
7. **`apply_restored_counters` 抽 helper** — SQL 測試需 PG 連線，純函數測試 <1ms
8. **`--rebuild` 只重建 PyO3 不重建 engine binary** — 明確 scope 邊界避免誤解
9. **Log rotation 保 10 份歸檔**（非無限）— 足夠回溯 2-3 個事故但不塞磁碟

## 留尾 / Remaining
1. **ENGINE-HEAL Fix 1/3/4 binary 部署** — 待 operator `bash helper_scripts/restart_all.sh --rebuild`（Fix 2 + Fix 5 已即時生效）
2. **真實 panic 注入測試** — 合 R07 Go/No-Go 一併在 canary 環境
3. **17:55 SIGTERM 來源追查** — 外部 cron / pkill 殘留待確認
4. **IPC outer-clamp fraction-vs-percent latent bug** — `event_consumer/handlers.rs` clamp(0.0, 0.5) 與 setter clamp(0.0, 50.0) 不一致（stop family 全家族既有缺陷），另案處理
5. **策略百分比止盈缺失** — unrealized⁺/realized⁻ 模式根因另一半，需策略層產品決策
6. **Phase 2 TODO**：`OPENCLAW_TICK_STALE_THRESHOLD_MS` env 覆蓋 · per-tier stale threshold · Metric export · IPC `get_tick_stale_ms` 給 GUI · systemd user unit 守護 watchdog · pre-cancel warning · `canary_events.jsonl` auto-rotate
7. **QoL-2 Demo AI cost 追蹤** — 依賴 G-1 AI 治理層
8. **Trailing stop post-deploy 24h 觀察** — `grep event=trailing_stop_triggered` 量化 winner/loser 分佈驗證 Fix B 成效

## 運行時產物 / Runtime Artifacts（`/tmp/openclaw/`）
| Path | 用途 | Lifecycle |
|---|---|---|
| `watchdog.lock` | flock 單例鎖 | 啟動建立，退出釋放 |
| `watchdog_state.json` | 重啟狀態持久化 | watchdog 維護，熔斷後 operator 可手刪重置 |
| `canary_events.jsonl` | 事件 append-only | 無限增長（operator 定期 rotate）|
| `engine_maintenance.flag` | operator 停機意圖 | `stop_all.sh` 建 / `restart_all.sh` 清 |
| `engine_logs/engine-<epoch>.log` | 歸檔 engine log | cap 10 份 |

## Commits
- `c510388` feat(qol-3): unify PyO3 build deployment across venvs
- `dc2eec3` Merge QoL-3: unify PyO3 build deployment across venvs
- `22a0b36` feat(qol-1): restore paper_state counters from trading.fills on startup
- `ea25844` Merge QoL-1: restore paper_state counters from trading.fills on startup
- `179822d` doc sync: TODO QoL-1/3 done + CLAUDE.md §三/§十一 baseline 1535→1543
- ENGINE-HEAL 5 Fix + Trailing Stop Activation Gate + `net_realized_pnl` fee attribution 待 commit（本日 session 尾）

## 參考 / References
- 工程日誌（權威紀錄）：`docs/worklogs/2026-04-14--engine_self_healing.md`（30KB）
- WS stale 閾值設計與誤報場景：`docs/known_issues/2026-04-14--ws_stale_detector.md`
- QoL 細節：`docs/worklogs/2026-04-14--qol_1_and_qol_3_delivery.md`
- Trailing Stop 細節：`docs/worklogs/2026-04-14--trailing_stop_activation_and_net_pnl_fix.md`
- Paper edge 污染隔離：`memory/project_edge_data_isolation.md`
- G-2 FundingArb 驗證窗口：`memory/project_g2_funding_arb_monitor.md`

**一句話**：ENGINE-HEAL 讓引擎從「靜默死亡 18min 無人知」進化到「panic 留 backtrace + crash-only ordered shutdown + 45s watchdog 拉起 + maintenance flag 表達 operator 意圖 + 熔斷防死循環 + log 歸檔 10 份」；QoL-1/3 解決重啟累計歸零與雙 venv 部署摩擦；Trailing Stop Activation Gate 終結「價格碰 entry 回撤就鎖損」的假 trailing 行為。Rust 測試 1535 → 1551（+16），Python 無回歸。
