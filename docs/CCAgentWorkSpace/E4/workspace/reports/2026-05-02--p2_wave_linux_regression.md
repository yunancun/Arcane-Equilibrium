# E4 P2 Wave Linux Regression — 2026-05-02

**Verdict**: **PASS** — ready for PM Sign-off

**Scope**: PM commit `1f3acc5` 4 fast-win fixes
- MIT-S2-6 `opportunity_tracker.py` early-exit
- E3-S2-P2-1 `strategy_read_routes.py` exception envelope
- E3-S2-P2-2 `live_session_account_routes.py` IPC error detail
- PA-DRY-1 `tick_pipeline/mod.rs` + `commands.rs` `is_legacy_close_tag` helper

**Baseline reference**: parent commit `9dd71a2`（pre-P2-wave）

## Test 結果

| Suite | passed | failed | baseline | delta | verdict |
|---|---|---|---|---|---|
| Cargo lib `openclaw_engine` | **2404** | 0 | 2404 | +0 | ✅ |
| Cargo tests aggregate (14 binaries) | **2560** | 0 | 2560 | +0 | ✅ |
| Pytest control_api_v1（excl integration） | **3262** | 1 (pre-existing) | ~3261 / 1 | +0 effective | ✅ |
| MLDE shadow advisor focused | **5** | 0 | 5 | +0 | ✅ |
| Live session endpoint actual_engine_kind | **17** | 0 | 17 | +0 | ✅ |
| Edge gates / prelive_edge focused | **5** | 0 | 5 | +0 | ✅ |
| Pytest 2nd run (excl pre-existing fail) | **3262** | 0 | 3262 | match | ✅ non-flaky |
| Focused 2nd run (advisor+endpoint) | **22** | 0 | 22 | match | ✅ non-flaky |

## Pre-existing fail clarification

`test_grafana_data_writer.py::TestGrafanaDataWriterLifecycle::test_start_sets_running`
- Assertion fail: `writer._running is True` 取得 `False`
- 在 baseline `9dd71a2`（P2 wave 之前）已重現同樣 fail — 由 E4 親自 checkout baseline 驗證
- File 最後修改 commit `bc3fa70` / `7178059`，遠早於 P2 wave `1f3acc5`
- 與 P2 wave 4 file changes 0 overlap（`opportunity_tracker.py` / `strategy_read_routes.py` / `live_session_account_routes.py` / `tick_pipeline/{mod,commands}.rs`）
- **Scope 完全正交本 wave，不阻塞 PM Sign-off**

## Healthcheck（Step 9）

| 對比項 | Baseline (CLAUDE.md §三) | This run | 狀態 |
|---|---|---|---|
| `[4]` phys_lock_runtime | WARN | WARN | == |
| `[10]` intents_writer_ratio | WARN | WARN | == |
| `[11]` counterfactual_clean_window | WARN | WARN | == |
| `[22]` trading_pipeline_silent_gap | WARN | **PASS** | improved |
| `[27]` intents_counter_freeze | WARN | WARN | == |
| `[33]` maker_fill_rate | WARN | WARN | == |
| `[38]` grid_trading_lifecycle_drift | WARN | **PASS** (insufficient sample skip) | improved |
| `[40]` realized_edge_acceptance | WARN | WARN | == |
| `[41]` scanner_market_gate_confirmation | WARN | WARN | == |
| 新增 WARN | — | 無 | ✅ |
| 新增 FAIL | — | 無 | ✅ |

## opportunity_tracker noise baseline (Step 8)

```
opp_24h_rows = 50, opp_24h_noise_rows = 50 (100%)
```

**解讀**：Linux source pull 完但 engine **未** `--rebuild`，runtime 仍跑舊 `opportunity_tracker.py`（Fix 1 早退邏輯尚未生效）。Task spec 明示「不阻塞，只記錄 baseline」。Operator deploy 後 24h 重測應顯著降至 < 50%（task 提門檻）。

## Mock 安全 audit
N/A — E4 為純驗證階段，未引入 mock。所跑測試套件為 production test code。

## SLA 壓測
N/A — P2 wave 4 fix 無 hot-path 影響：
- Fix 1 (opportunity_tracker) 在 advisor 層，非 tick path
- Fix 2/3 (route) 在 control plane，非 H0/IPC 預算
- Fix 4 (`is_legacy_close_tag` extract) 是 zero-cost helper inline，pure refactor

## 跨語言浮點 1e-4 一致性
N/A — 4 fix 無 indicator/計算公式變動。

## 退回 E1 修復清單
**N/A**（PASS）— 無需退回 E1。

## Operator 下一步

1. **PM Sign-off** — 引本 report + `.claude_reports/20260502_144705_e4_p2_wave_linux_regression.md` 兩份
2. **（可選）Runtime promote**：`ssh trade-core "cd ~/BybitOpenClaw/srv && bash helper_scripts/restart_all.sh --rebuild --keep-auth"` — Rust Fix 4 必需 `--rebuild`；Python Fix 1/2/3 理論可純重啟但一次 `--rebuild` 統一 promote 較乾淨
3. **24h 後**：重測 Step 8 opp_24h_noise_rows，驗證 Fix 1 deploy 後實際下降幅度

## Reports
- `.claude_reports/20260502_144705_e4_p2_wave_linux_regression.md`（6 節格式 + 完整 stdout）
- `srv/docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-02--p2_wave_linux_regression.md`（本檔）

E4 REGRESSION DONE: PASS · report path: srv/docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-02--p2_wave_linux_regression.md
