# 已完成 TODO 歸檔 — 2026-04-16（STRATEGY-CLOSE-TAG-FIX + EDGE-P3-1 Phase B #3 + DEDUP-PY-RUST）

> 自 `TODO.md` 於 2026-04-16 傍晚整理時切出。條目依主題分組，commit 為權威出處。

---

## 🧷 P0-4 · STRATEGY-CLOSE-TAG-FIX — `execute_position_close` 吞掉策略退場 tag ✅

**commit** `a5401ce` fix(engine): P0-4 R1 execute_position_close trigger_tag propagation

**結果**：`execute_position_close()` 新增 `trigger_tag: &str` 參數；commands.rs:459 硬編碼 `"risk_check"` 移除。全部 7 個 caller 傳真實因果 tag：

- Strategy 主動退場（exchange + shadow）→ `strategy_close:{reason}`（on_tick.rs:969, 1007）
- Risk close 評估器（exchange + shadow）→ `risk_close:{reason}`（on_tick.rs:1108, 1135）
- Fast_track ReduceToHalf → `risk_close:fast_track_reduce_half`（on_tick.rs:213）
- HaltSession 熔斷 → `risk_close:halt_session`（on_tick.rs:1173）
- paper_paused stop trigger → `stop_trigger:{trigger.reason}`（on_tick.rs:434）

**回歸測試**：`test_execute_position_close_propagates_trigger_tag`（tests.rs；5 組 is_primary × tag 案例） · engine lib 1322 → **1323** passed · core 380 / e2e 35 全綠。

**診斷文件**：`docs/audits/2026-04-16--demo_zero_strategy_exit_audit.md` V2

**還原**：`settings/strategy_params_demo.toml [funding_arb] active=true` 已恢復。

**後續部署**：operator `bash helper_scripts/restart_all.sh --rebuild` 部署新 bin；驗證 SQL：
```sql
SELECT substring(strategy_name from 1 for 30), COUNT(*)
FROM trading.fills
WHERE engine_mode='demo' AND ts > '<rebuild_ts>'
GROUP BY 1;
```
重啟後應看到 `strategy_close:*` 與分離的 `risk_close:*` 桶。

---

## 🔮 P1-1 · EDGE-P3-1 Phase B #3 ONNX loader（Rust 端）✅

**commit** `7bd8cff` feat(edge-p3): Phase B #3 ONNX loader — ort backend + dynamic capability probe

**結果**：ort 2.0.0-rc.12 後端取代 tract-onnx 0.21（tract 缺 `TreeEnsembleRegressor` 無法跑 LightGBM 分位 export）；`ort_backend::OnnxTrioPredictor` 實現 9-key metadata 讀取 + schema_hash fail-closed + 三重 predictor 同一邏輯單元 + `enforce_monotone`（Spec §7.3）。

**Feature 結構**：
- `Cargo.toml` feature `edge_predictor_ort`（gated）+ `download-binaries` + `copy-dylibs` + `tls-rustls`
- 純 Rust TLS（無 openssl-sys 系統依賴，保留 Mac zero-system-dep 故事）
- default build 仍走 null stub（不觸發 ort binary 下載）

**Invariant**：NaN/Inf features 觸發 Invariant #12；quantile 單調性在 load time 驗證。

**測試**：5 個整合測試（fixture ONNX trio）全綠；engine lib 1323 → **1330 (ort) / 1323 (default)**。

---

## 🧰 P1-2 · EDGE-P3-1 Step 7b Python route + flag flip ✅

**commit** `7bd8cff`（與 P1-1 同次）

**結果**：Python static flag 無法靜態知道 Rust build feature，故新增 Rust IPC `get_build_capabilities` 回報 `cfg!(feature = "edge_predictor_ort")`；Python capabilities endpoint 於 probe 時動態 overlay。

**行為**：
- ort build → 自動翻 True，無需 Python 重啟
- default build → 保持 False
- probe fail-soft：IPC 失聯 fallback 到原 static flag

**測試**：2 個新 Python 測試驗證 overlay + fail-soft。

**解鎖**：P1-4 產線化首個 ONNX artifact 後 `ReloadEdgePredictor` IPC 即可載入，進入 Stage 2 shadow mode。

---

## 🧹 DEDUP-PY-RUST · Python–Rust 重複計算代碼清理 ✅

**Phase 1 Step 1-3 stub 化**（indicators/ + indicator_engine + signal_generator/signal_engine）— commit `d41f72a` 內含

**Phase 2 Step 4-6 stub 化**（kline_manager + market_scanner + position_sizer）— commit `d41f72a` 內含

**Phase 3 Step 7-10 stub 化**（orchestrator + auto_deployer + backtest + strategies/base）— commit `d41f72a` 內含

**Follow-up 1**：`local_model_tools/tests/` 重寫為 `test_stub_contracts.py` 契約測試 **59 passed** — commit `d1e171c`
- shape-only，無 behavior 斷言
- 保留 accepted ctor kwargs / `__all__` surface / documented empty return shapes 守護

**Follow-up 2**：`restart_all.sh --rebuild` 後 route fallback 行為驗證 — commit `d1e171c`
- 2026-04-16 rebuild 後 10 個策略路由全數 HTTP 200
- 6 個 Rust-first 回 `source=rust_engine` / `rust_engine_primary`
- 4 個 Python-stub-only 回 documented 空 / stub shape，無 500
- `signal_engine.get_signal_summary` 補回 `consensus_direction` / `long_score` / `short_score` 鍵保守舊路由契約（原 stub 漏鍵會使 `/api/v1/strategy/signal-summary` 斷言失敗）

**總效益**：Tier A 21 檔 ~8,506 行 → 1,982 行 stub（淨減 ~6,524 行）。

**驗證**：
- FastAPI 217 routes 全載入
- Bybit connector 2,454 tests passed / 1 skipped
- Python 全域 2875 passed / 5 skipped

**計劃原文**：`docs/references/2026-04-16--python_rust_dedup_cleanup_plan.md`

**架構意涵**：Python 側僅保留 FastAPI 匯入表面與 stub 降級備援；計算真值源全數在 Rust `openclaw_core` / `openclaw_engine`。新計算邏輯一律 Rust-first（見記憶體 `feedback_new_code_rust_first.md`）。

---

## 📎 相關提交摘要（時間順）

| commit | 主題 |
|--------|------|
| `d41f72a` | DEDUP-PY-RUST stub Tier A (~6.5k lines) |
| `e736761` | audit(demo-exit-tag): V2 + temp disable funding_arb demo |
| `a5401ce` | P0-4 R1 `execute_position_close` trigger_tag propagation |
| `d1e171c` | DEDUP-PY-RUST Follow-up 1/2 — contract tests + stub shape fix |
| `7bd8cff` | EDGE-P3-1 Phase B #3 ONNX loader — ort backend + dynamic capability probe |
| `cd78ee9` | docs(todo): P0-3 阻塞者改為 P0-0；關鍵路徑剝離 P0-1 |

---

## 🧭 P0-0 · RECONCILER-BURST-FIX — 對帳器啟動期誤升級風控 ✅

**commit** `a2e4719` P0-0 startup grace fix · `a068d4a` e2e regression test · 部署：engine PID 1340527 於 2026-04-16 21:08 local 啟動（binary 建於 a068d4a 之後）

**根因**：引擎重啟後 warmup baseline 與本地 paper_state 未同步 → 首輪 tick 將 Ghost/Orphan 誤判為 live drift burst。2026-04-15 事故：9 drifts（6 ghost + 2 orphan + 1 minor_drift）→ burst streak=1 升 Defensive → FAST_TRACK ReduceToHalf 全組合半倉 + `ft_pause_new_entries` 鎖新開倉 → 46min 才 Cautious→Normal。

**修復**（方案 A startup grace window 5min）：
- `escalation.rs`：新增 `STARTUP_GRACE_MS = 5 * 60 * 1000` + `ReconcilerState.startup_ms` 欄位
- `evaluate_actions()` 入口：寬限期內早退返空 actions，**不累加** drift_streak / burst_drift_streak / clean_cycles
- `check_rest_failure_escalation()` 入口同樣 grace 檢查
- `run_position_reconciler()` 啟動時 `rc_state.startup_ms = now_ms_util()`
- 寬限期內 orphan_handler / V014 audit / baseline update 全部照常運作

**回歸**：
- 6 新 unit tests（escalation.rs）+ 1 e2e regression test（`e2e_startup_grace_window_ignores_orphan_storm`，replicate 2026-04-15 事故場景）
- engine lib 1330 default / 1336 ort · reconciler_e2e 18 → 19 · 全綠 0 fail

**部署驗證**：重啟後 11+ 分鐘：0 auto-escalations · 0 CircuitBreakers · 0 ReduceToHalf events · 0 `ft_pause_new_entries`。"startup grace suppressed" log 未觸發（baseline reseed 乾淨收斂、未產生 drift）。

**RCA 文件**：`docs/references/2026-04-16--reconciler_burst_escalation_rca.md`

---

## 🧰 P1-3 · EDGE-P3-1 Step 7c Python consumer ✅

**commit** 同本批次（見 P1-1 / P1-2 歸檔塊以 Step 7c 配對）

**結果**：三條讀取路由骨架 + 15 新單元測試
- `app/shadow_fills_routes.py`：`GET /api/v1/edge/shadow_fills`（分頁列表）、`/summary`（per-strategy 聚合）、`/promotion_gate/{strategy}`（樣本數分級裁決）
- `tests/test_shadow_fills_routes.py`：fake DB + fail-closed + 空資料 fallback + verdict 分支覆蓋；15 passed
- `app/main.py`：路由註冊於 `engine_capabilities_router` 之後

**Promotion gate 門檻**（spec §8.3 line 714）：
- `n < 200` → `insufficient_samples`
- `200 ≤ n < 500` + synthetic 覆蓋 → `ship_shadow_candidate`
- `n ≥ 500` + synthetic 覆蓋 → `ship_prod_candidate`
- `n ≥ 200` 但 synthetic 仍 NULL → `awaiting_synthetic_labels`

**注意**：PAPER-DISABLE-1 後 paper 預設關，shadow fills 表目前為空。等 `OPENCLAW_ENABLE_PAPER=1` + ONNX artifact 載入 + synthetic-close writer 接線後自動回資料。

**驗收**：`pytest program_code/exchange_connectors/bybit_connector/control_api_v1/tests/ -q` → 2469 passed / 1 skipped（+15 自本 PR）

**部署**：需重啟 control_api_v1 服務載入新路由（`bash helper_scripts/restart_all.sh` 不含 `--rebuild` 即可）

---

## 🧱 PAPER-DISABLE-1 · Paper 管線預設關閉 + 負餘額 Gate 1.6 ✅

**commits**：`ba7b083` + `6fc7f1e`（近日；見 git log 精確範圍）· engine PID 1340527 21:08 local 啟動後生效

**背景**：Paper 管線在 4-14~16 兩天 balance $783→-$292（137% drawdown），5055 fills / -$1076 net。Demo 同期 3295 fills / -$63 net。根因：
- Paper 配置刻意寬鬆（`risk_config_paper.toml`："maximum exploration"）：position_size 50% vs demo 25%、leverage 100x vs 50x、daily_loss 30% vs 15%、h0_shadow_mode=true、min_confidence 0.05 vs 0.10
- Paper 走 `process_with_features`（`on_tick.rs:752`）合成 fill at `event.last_price` → 零延遲/零 partial/零 reject
- paper_state 無負餘額守門 → 穿倉後仍繼續刷 intent
- 同策略 grid_close_short：paper 745 fills/-$218 vs demo 28 fills/-$0.06（27x fills, 3600x 虧損差）

**實作**：
- `rust/openclaw_engine/src/main.rs`：`OPENCLAW_ENABLE_PAPER=1` 才 spawn paper pipeline；預設走 drain task 消費 `paper_event_rx` + `paper_cmd_rx`
- `rust/openclaw_engine/src/tick_pipeline/mod.rs`：新增 `PipelineHealth::Disabled = 3` + `from_u8(3)` 處理
- 禁用時寫入 `paper_state.json` + `pipeline_snapshot_paper.json` 含 `disabled: true` + `disabled_since_ms`
- `rust/openclaw_engine/src/intent_processor/router.rs`：新增 Gate 1.6 `insufficient_balance`（balance ≤ 0 且無持倉時拒絕開新倉；反向平倉仍允許）

**測試**：`test_pnl1_rejects_qty_zero_process` 更新（接受 `insufficient_balance:` 或 `qty_zero:` 前綴）+ `test_d6_pipeline_health_*` 新增 `Disabled=3` 斷言 · engine lib 1330 default / 1336 ort 全綠

**如何重新啟用**：`export OPENCLAW_ENABLE_PAPER=1` 後重啟引擎。GUI tab 仍運作（Python 側 ENGINE=None stub 不變）。

**Why not delete outright**：3E-ARCH 是 4-11 剛完成的架構成果；env gate 保留未來 W22+ Agent 探索階段一鍵啟用能力。

---

## 📈 G-2 FundingArb 監控 daemon — option D 設定 ✅

**2026-04-16T19:35Z 更新**：daemon 從 20 fills 目標 + 無牆鐘上限改為 **10 fills / 72h deadline**（擇先達觸發 audit）

**前情**：P0-4 R1 合入前 daemon SQL `strategy_close:funding_arb%` 永返 0（tag 被硬編碼吞成 `risk_check`）。R1 合入且引擎重建後 DB 出現真 `strategy_close:*` 分流（近 2h demo：grid_close_short 15、ma_reverse_cross 7、grid_close_long 1、funding_arb 2）。

**為何改 option D**：funding_arb 退場頻率遠低於其他策略（hold 整個 8h funding 週期）。原 20 fills 需 3-7 天自然累積。改 10 fills + 72h 牆鐘讓即使低頻也有 N≥某值的 audit 結束條件。

**腳本**：`/tmp/openclaw/g2_monitor.py`
- `TARGET_FILLS = 10` · `DEDLINE_SECONDS = 72 * 3600`
- 達 target 或超 deadline 任一條件 → 寫 `docs/audits/2026-04-16--g2_funding_arb_clean_edge.md` 然後 exit
- PID 1349961 · baseline 2026-04-16 15:40:48 UTC 不變
- 進度檢視：`cat /tmp/openclaw/g2_monitor.progress.json`

**G-2 在工作量上的定位**（重要澄清）：
- **非主路徑**：TODO §P0-3 明寫「P0-1 不必要 — G-2 只覆蓋 funding_arb 子集，Phase 5 整體 edge 用其他 6 策略 fills 已足夠」
- **非 LG-1 阻塞**：TODO §P0-2 明寫「P0-1 為 funding_arb 子集並行」
- G-2 實際只卡 **funding_arb 單策略的 R-02 promotion 決定**（繼續跑 / 改參數 / 停用），其他 6 策略 edge 評估、21d demo、LG-2/3、Live gate 均不等 G-2

