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
