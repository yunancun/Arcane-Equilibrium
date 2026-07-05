# 2000 行硬上限 — Documented Pre-Existing Exception Registry

> 本檔為 CLAUDE.md §七 / §九「2000 lines is the hard cap unless a documented
> pre-existing exception applies」的 documented exception 正本（SSOT）。
>
> 背景：2026-05-30 冷審計已裁定 2000 行為 *convention-with-documented-exception*，
> 非 5 hard gates 之一（見 `docs/archive/2026-05-30--cold_audit_pm_final.md`）。
> 因此超標檔須在此登記為已知 pre-existing exception，冷審計據此不再重複觸發同一
> retroactive finding。
>
> 紀律：
> - 登記 ≠ 授權長期超標。每一列的拆分歸屬（owner / 觸發語義）為後續 E5-plan 依據。
> - **禁在登記波實際拆檔**：熱路徑 / 唯一執行入口檔拆分觸及執行語義，屬 E5 plan →
>   E1 → E2 專門工程，不在文檔登記波授權內。
> - 新增或移除超標檔須同步更新本表，並在 CLAUDE.md 指針處保持一致。

## 登記表（2026-07-05 建）

| # | 路徑 | 行數 | 理由 / 拆分歸屬 |
|---|---|---|---|
| 1 | `rust/openclaw_engine/src/intent_processor/mod.rs` | 2032 | 唯一執行入口（root principle 1）。拆分風險高，觸執行語義，待 E5 plan。 |
| 2 | `rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs` | 2193 | tick 熱路徑 dispatch。拆分觸執行語義，待 E5 plan。 |
| 3 | `rust/openclaw_engine/src/tick_pipeline/commands.rs` | 2266 | tick pipeline 命令面。拆分觸執行語義，待 E5 plan。 |
| 4 | `helper_scripts/canary/engine_watchdog.py` | 2412 | 災難保護（root principle 9）。自愈路徑，拆分風險高，待 E5 plan。 |
| 5 | `helper_scripts/research/alpha_discovery_throughput/discovery_loop.py` | 5954 | 研究一次性 evidence 迴圈。非熱路徑，拆分屬 E5/研究治理。 |
| 6 | `helper_scripts/research/alpha_discovery_throughput/runtime_runner.py` | 4500 | 研究 runner。非熱路徑，拆分屬 E5/研究治理。 |
| 7 | `helper_scripts/research/alpha_discovery_throughput/profitability_path_scorecard.py` | 3789 | 研究 scorecard。非熱路徑，拆分屬 E5/研究治理。 |
| 8 | `program_code/research/microstructure/fill_sim.py` | 2796 | 微結構 fill 模擬。研究面，拆分屬 E5/研究治理。 |
| 9 | `helper_scripts/research/cost_gate_learning_lane/status.py` | 2238 | cost_gate lane 狀態彙整。研究面，拆分屬 E5/研究治理。 |
| 10 | `helper_scripts/research/cost_gate_learning_lane/cost_gate_learning_lane_cron.sh` | ~2031 | cost_gate lane cron wrapper（shell）。該檔頭已由 E5-5 指向本 registry。研究面 cron，拆分屬 E5/研究治理。 |

> 行數為 2026-07-05 快照（精確值以 `wc -l` 為準，會隨編輯漂移）；本表登記意圖=標記
> 為已知 pre-existing exception，非行數 ledger。row 10 的 cron wrapper 於本檔建立時尚
> 在 `fix/remain-cron-0705` 分支（E5-5 已加檔頭指針），併入 main 後行數以實檔為準。
