# E1 IMPLEMENTATION — Phase 1（rich-input tuner）· 2026-06-17

> 待 E2 審查 → E4 回歸 → PM commit。不直接 commit。Mac self-test only（Linux demo engine cycle 實證 owed E4）。

## 任務摘要

PA master-spec PHASE 1 + QC/MIT synthesis overrides：餵 StrategistScheduler 更多 leak-free 證據（additive INPUT），不改它能寫什麼（仍 demo-only / 仍只調 agent_adjustable / 仍既有 clamp+range+weight-sum=65 / 仍 persist learning.strategist_applied_params）。flag `OPENCLAW_STRATEGIST_RICH_INPUT` default-OFF（OFF=bit-identical）。核心 must-fix=server-side news-blind quant gate（code+test 非註釋）。

## BUILD-BLOCKER U3-P1 — RESOLVED（keys 對齊，Phase 1 非 inert）

- edge cell key = `format!("{}::{}", strategy, symbol)`（edge_estimates.rs:280）。
- scheduler `pair.strategy_name` 來自 `trading.fills.strategy_name`，`engine_mode='demo'`，close-path 過濾（NOT LIKE risk_close:/strategy_close:/ipc_close）（evaluate.rs:332-339）。
- james_stein producer cell key = `f"{strategy}::{symbol}"`（james_stein_estimator.py:540），`strategy` 來自 realized_edge_stats.py FIFO 配對只保留 **entry** 成交的 strategy_name（is_exit 過濾 risk_close/stop_/strategy_close，realized_edge_stats.py:318-333）。
- **結論：兩側同一 entry 策略命名空間（grid_trading/ma_crossover/bb_*/funding_arb）、同 engine_mode='demo'、同 close-filter、同 `{strategy}::{symbol}` 格式。get_cell 命中，quant gate 不會永久拒。Phase 1 有效。** Mac 殘留 edge_estimates.json 含 `grid_trading::ORDIUSDT` 佐證格式。
- U6-P1（regime klines）：market.klines demo-readable（intraday backfill 已補，memory 06-15）；不足窗→"unknown"（context-only，acceptable）。

## 修改清單

| 檔 | 動作 |
|---|---|
| `rust/.../strategist_scheduler/rich_inputs.rs` | **新檔**：RichInputs 側車 + CellEstimateView/NewsItemView + compute_regime_label + verify_quant_justification（news-blind quant gate）+ 14 單元測試 |
| `rust/.../strategist_scheduler/mod.rs` | 宣告 rich_inputs mod + re-export；struct 加 3 Option 欄（rich_input_enabled/edge_store/news_router）；3 builder（with_rich_input/with_edge_store/with_news_router）；current_edge_ttl_secs helper + DEFAULT_EDGE_ESTIMATE_TTL_SECS；新 validate_recommendation_with_reason_rich（7-arg 疊加變體）+ rec_has_real_param_delta |
| `rust/.../strategist_scheduler/evaluate.rs` | build_strategist_eval_payload 加第 6 參 `rich: Option<&RichInputs>`（None=bit-identical）；evaluate_cycle flag-ON 組 RichInputs + 走 rich 變體；assemble_rich_inputs + compute_regime_for（market.klines 1m closes，`ts<now()` leak-free）；REGIME_WINDOW/MIN_WINDOW；unix_now_secs；2 payload 測試更新 + 2 新 payload 測試 |
| `rust/.../strategist_scheduler/cycle_counters.rs` | REJECT_REASONS 加 news_solo_trigger / quant_justification_unverified |
| `rust/.../strategist_scheduler/tests.rs` | +5 rich 變體整合測試；test_reject_reasons_list 加 2 新 reason |
| `rust/.../main_boot_tasks.rs` | spawn_strategist_scheduler 加 edge_estimates 參；讀 OPENCLAW_STRATEGIST_RICH_INPUT；接 with_edge_store + with_rich_input；log 加 rich_input_enabled |
| `rust/.../main.rs` | call site 傳 &scanner_edge_estimates |
| `program_code/.../app/ai_service_dispatch.py` | _parse_strategist_response 保留結構化 quant_justification（白名單 5 欄）；_build_strategist_prompt + _build_rich_input_section（flag-OFF None=byte-identical）；_handle_strategist 透傳 rich_input/quant_evidence_available |
| `program_code/.../tests/test_strategist_rich_input_phase1.py` | **新檔**：10 測試（parse 保留/白名單/不破既有；prompt flag-OFF identity/flag-ON rich/news 零權重） |

## 關鍵 diff / 設計決策

1. **疊加 gate 不改既有簽名**：`verify_quant_justification` 簽名 = `(rec, has_real_param_delta, edge, now_ts, ttl)` —— **無 news 參數**（結構性 news 零權重，E2 必證）。新 `validate_recommendation_with_reason_rich` 先跑既有 4-arg 3 gate（byte-identical），再疊 quant gate。flag-OFF caller 仍呼 4-arg 版 → 既有 direct-call 測試全綠零動。
2. **engine 自查 cell 不信 LLM**：gate 用 `edge.get_cell(strategy,symbol)` 拿真 shrunk_bps，比對 claimed（符號一致 + |Δ|≤1bps）；absent/!is_fresh/!validation_passed/符號不符 → unverified。
3. **TTL cost_gate 同源**：讀 `RiskConfig.slippage.edge_estimate_ttl_secs`（demo store，48h），避免「cost_gate 認 fresh、quant gate 認 stale」語意分裂。
4. **ml_shadow DROP**（synthesis override 1）：完全不填 ml_shadow 鍵/聚合/測試（MIT 裁 ONNX 非真，避免對 LLM 製造虛假獨立佐證）。

## 治理對照

- 硬邊界：未碰 tune_target=Demo fail-fast（evaluate.rs:310）/ ±clamp / range / weight-sum=65 / apply / persist / agent_adjustable 集 / max_retries / live_execution_allowed / system_mode。quant gate 是**更嚴第 4 gate**（疊加，永不放寬）。
- Alpha Evidence Governance：news=corroborating-only，結構性零 gate 權重（簽名無 news 參數）；regime 本地 leak-free 自算（`ts<now()` 等價 shift(1)）。
- 無新 migration（edge/regime 讀既有源）。無新 mutable singleton（edge_store=既有 Arc clone）。注釋中文（bilingual-comment-style）。0 hardcoded user path（grep 自證）。MODULE_NOTE 已寫（rich_inputs.rs / Python 測試檔）。

## 不確定之處 / 偏差

- **NEWS 偏差（最小安全解，已報 PM/E2）**：spec 寫 `news_router.snapshot_for(symbol,window)`，但實機 NewsRouter API 是 market-wide `regime_snapshot()` 非 per-symbol，且 router Arc 建於 tasks.rs news pipeline 內未對外曝露至 scheduler call site。決策：保留完整 `with_news_router` builder + RichInputs.news 欄 + NewsItemView（讓 T-P1-9/10 零權重不變量可測），但 **boot 接 `news_router=None`**（runtime news 欄 absent）。理由：news 零 gate 權重、不影響任何 verdict；threading router Arc 需改 tasks.rs/main.rs news 構造（scope 擴 + dirty-tree 檔重疊風險）。future additive 接線即生效。spec §1.2 已明示「news_router 若未建則 None，欄 absent」。
- **U4-P1 方向語意**：v1 不卡 direction×param（只驗 cell 真實+fresh+validated+符號一致）；QC 定映射後 additive 加（spec §1.6）。
- direction 欄保留進 quant_justification（給 QC 後續用）但 v1 gate 不驗。

## 測試 / 結果（Mac 實跑，誠實計數）

- Rust scheduler：`cargo test -p openclaw_engine --lib strategist_scheduler` → **57 passed / 0 failed**（含 14 rich_inputs + 5 rich 變體整合 + 既有全綠）。
- Rust full lib：**3957 passed / 0 failed / 1 ignored**。
- Mutation bite（Rust）：verify_quant_justification 早返 Ok → **8 紅**；還原全綠。
- Python：`test_strategist_rich_input_phase1.py` **10 passed** + `test_p1_audit_smoke.py` 13 passed（flag-OFF identity）。
- Mutation bite（Python）：移除 quant_justification preservation → **3 紅**；還原全綠。
- lib build 3 warnings 全 pre-existing（與我無關）。

## Operator / PM 下一步

1. **E2 對抗審查**：證 verify_quant_justification 簽名無 news 參數（news 零權重）；T-P1-2/3/9/10 news-solo reject；flag-OFF IDENTITY；既有 3 gate 不破；NEWS=None 偏差是否接受（或要求 follow-up 接 router）。
2. **E4 Linux 回歸**：flag-OFF byte-identical baseline + flag-ON 全 T-P1 + Linux demo engine 實證 cycle 真跑 reject/apply（Mac 無 PG/engine 不驗 cycle 端到端）。
3. **CC**：Alpha Evidence Governance（news corroborating-only 證）。
4. 不 commit（強制鏈 E1→E2→E4→QA→PM）。
