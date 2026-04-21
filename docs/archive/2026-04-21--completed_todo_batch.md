# 2026-04-21 完成 TODO 批次歸檔

本檔案歸檔 2026-04-21 當日完成的所有 TODO 項，從 `TODO.md` 主文件移出，避免膨脹。詳細 commit 敘述保留於 `docs/CLAUDE_CHANGELOG.md`；本檔僅列「TODO 項 → commit ref → 一句話結論」。

---

## 1. DUAL-TRACK-EXIT-1 / Track P 全鏈

### 1.1 DECISION-OUTCOMES-* 全系列 Linux 驗證結案
- **原 TODO**：`ATTEMPT-LOG-NOT-DEAD-1` 與 `DECISION-OUTCOMES-DEAD-1` 情境 3 doc-only（**被 Linux 驗證推翻**）
- **結案**：`decision_outcomes` 273,963 rows；engine_mode 分布 demo 136k / live 89k / live_demo 47k；outcome_1h non_null 覆蓋率 live 98% / demo 90% / live_demo 74%；max_favorable non_null live 100% / demo 72% / live_demo 21%（live_demo 21% 為 recent data 未到 25h+ backfill 窗口，非 bug）
- **memory**：`project_decision_outcomes_not_dead.md` 更新終態

### 1.2 DECISION-OUTCOMES-ENGINE-MODE-TAG-BUG-1 ✅ commit `5e2981d`
- `outcome_backfiller.rs` INSERT 漏接 `engine_mode` 欄位補上 + 3 新 regression tests；Linux backfill 歷史 267k rows；engine_mode 分布對齊 context_id 前綴

### 1.3 OUTCOME-BACKFILL-JOIN-NULL-1 ✅ commit `5e2981d`
- `outcome_backfiller.rs` 7 處 LATERAL timeframe 字串格式不一致（`'1' vs '1m'`）修復：`'1'→'1m'` / `'5'→'5m'` / `'60'→'1h'` / `'240'→'4h'`；Linux backfill 歷史 268k rows outcome_*；outcome_1h non-NULL 覆蓋率 74-98%

### 1.4 GATE1-REVERSAL-OBSERVABILITY-1 ✅ doc-only close
- Linux audit 揭露 Priority 6 PHYS-LOCK 從未 fire（`exit_features` 永遠 None）；加 Prometheus counter 無意義（upstream None）；`phys_lock_*` observability 等 `TRACK-P-T4-WIRING-1` 落地後自然解鎖

### 1.5 TRACK-P-T4-WIRING-1 ✅ commit `e95c779` 主軸解阻塞
- `tick_pipeline/on_tick.rs:1677` 硬編碼 `|_| None` 替換為實際 closure：查 `paper_state.position_exit_snapshot` + `price_tracker.compute_roc(300ms)` + `intent_processor.edge_estimates().get_cell` → 餵新 pure fn `exit_features::build_exit_features_for_tick` → 產 `Some(ExitFeatures)`
- 鏡像 close-time `tick_pipeline::build_exit_feature_row` 7 維衍生規則；Option::None → 4-Gate 保守 Hold（fail-soft，零 regression）
- engine lib 1827 → **1839 passed / 0 failed**（+12 new builder tests）；Mac debug + Linux release 均驗
- Runtime 效果已在 2026-04-21 20:44 `restart_all.sh --rebuild` 部署後生效（engine PID 3954769）；Priority 6 每 tick 評估，edge_estimates 冷啟動時 Gate 1 全 Hold（預期 fail-safe）
- 詳 `.claude_reports/20260421_191842_track_p_t4_wiring.md`

### 1.6 DUAL-TRACK-EXIT-1 Phase 1b Track P v2 pure fn ✅ commit `aee96b9`
- `exit_features.rs` +698：`physical_micro_profit_lock_v2` 非線性 giveback 4-Gate pure fn + `ExitConfig` 7 參數 + 31 單測
- QC 反轉 Gate 1 `edge <= floor → Hold` 對齊設計意圖；engine lib 1791 → **1816**
- Runtime 接線於 `e95c779`（見 1.5）

### 1.7 GATE1-REVERSAL-1 hotfix A ✅ commit `d0f0c21`
- v1 Priority 6 Gate 1 同步反轉 Lock → Hold；3 tests rename + assert 反轉；engine lib 仍 **1816**
- Runtime 接線於 `e95c779`（見 1.5）

---

## 2. EDGE-P2-3 PostOnly 擴展

### 2.1 Phase 2+ (b) bb_breakout + ma_crossover PostOnly entry ✅ merges `f5f4dc2` + `8280132`
- Feature commits `b2d8ac5` ma / `9edc6a4` bb 於 2026-04-20；rebase 解衝突後 `--no-ff` merge 進 main
- bb_breakout.rs 7 hunks + 三 env TOML 3 hunks 手動保留 EDGE-P2-2 OI + EDGE-P2-3 PostOnly 兩組正交 feature；ma_crossover 自動 merge
- 三環境 TOML `[bb_breakout]` + `[ma_crossover]` 加 `use_maker_entry`/`maker_price_offset_bps`/`maker_limit_timeout_ms`，demo/paper=true、live=false
- fee routing 沿用 `intent_processor::fee_rate_for_intent`；engine lib 1819 → **1827** passed（debug，+4 bb +4 ma PostOnly tests）
- Runtime 已在 2026-04-21 20:44 rebuild 後進入（engine PID 3954769）；本地分支 `bb_breakout_postonly`/`ma_crossover_postonly` + 遠端 `origin/feature/p1-16-h0-gate-deterministic` 皆已可清

---

## 3. 檔案拆分 / 重構系列

### 3.1 EXIT-FEATURES-SPLIT-1 ✅ commit `3a9b988`
- 單檔 `rust/openclaw_engine/src/exit_features.rs` 1317 行超 §七 1200 硬上限 → 拆為 `exit_features/{mod,core,v2,builder}.rs` 四檔
- **mod.rs** 68 行（頂層 doctrine + `pub use` re-exports，保向後相容 `crate::exit_features::…`）
- **core.rs** 204 行（`ExitFeatures` + `PhysicalDecision` types + 7 core tests）
- **v2.rs** 747 行（`ExitConfig` + `non_linear_giveback_fn` + `physical_micro_profit_lock_v2` + 24 v2 tests，含 Gate 1 v2 對齊設計 doctrine）
- **builder.rs** 368 行（`build_exit_features_for_tick` T4 wiring + 12 builder tests）
- 測試 1839 passed / 0 failed 不變；外部呼叫零改動（`risk_checks.rs` / `on_tick.rs` / `position_risk_evaluator.rs` / `combine_layer.rs`）

### 3.2 ON-TICK-SPLIT-1 ✅ commit `bfedb56` · sub-agent 並行派發
- 單檔 `rust/openclaw_engine/src/tick_pipeline/on_tick.rs` 2071 行超 §七 1200 硬上限 → 拆為 `tick_pipeline/on_tick/{mod,helpers,step_0_fast_track,step_0_5_h0_gate,step_1_2_klines_indicators,step_3_signals,step_4_5_dispatch,step_6_risk_checks}.rs` 八檔
- **mod.rs** 157 行（orchestrator，`ControlFlow<Break=early-return, Continue=state>` 串接 6 step + `pub(crate) use` re-exports）
- **helpers.rs** 152 行（strip/log PHYS-LOCK + T4-FIX 端到端測試）
- **step_0_fast_track.rs** 516 行 · **step_0_5_h0_gate.rs** 93 行 · **step_1_2_klines_indicators.rs** 111 行 · **step_3_signals.rs** 192 行 · **step_4_5_dispatch.rs** 929 行（超 soft warn 但 borrow-check NLL 限制無法再拆，doctrine 在 mod.rs header 記錄）· **step_6_risk_checks.rs** 359 行（T4 `exit_features_fn` closure 完整保留不得跨 step 拆）
- 跨 step owned state 串接：`ft_pause_new_entries`/`h0_allowed`/`IndicatorSnapshot`/`Vec<Signal>`/`Vec<OrderIntent>`
- Mac debug + Linux release 均 1840/0；Sub-agent (general-purpose) 並行 ~15min 完成
- 外部呼叫零改動（`tick_pipeline/mod.rs` 的 `mod on_tick;` 自動解析為 `on_tick/mod.rs`）

---

## 4. Test flake 根除系列（pure-fn 模板化）

### 4.1 AI-SERVICE-CLIENT-ENV-RACE-1 ✅ commit `580304a`
- 3 env-racy tests `ai_service_client::tests::{test_default_socket_path, test_env_override_socket_path, test_data_dir_fallback}` 原 `std::env::set_var/remove_var` `OPENCLAW_AI_SERVICE_SOCKET` + `OPENCLAW_DATA_DIR` 與並行測試競爭（Mac `$OPENCLAW_DATA_DIR` 有值時 ~1/1839 flake）
- 抽 pure fn `resolve_socket_path_from(sock: Option<&str>, data_dir: Option<&str>) -> PathBuf` 承接優先序
- 舊 `resolve_socket_path()` 改為薄包裝讀 env；測試改呼 pure fn 直接注入輸入，零 env 動作 = 零 race
- +1 新測試 `test_sock_override_beats_data_dir` 顯式斷言優先序
- Mac 9/9 ai_service_client 綠；engine lib 1839 → **1840**
- 詳 `.claude_reports/20260421_200045_ai_service_env_race.md`

### 4.2 CANARY-WRITER-ENV-RACE-1 ✅ commit `d454c17` · sub-agent 並行派發
- `canary_writer::tests::{spawn_honours_disable_dump, spawn_without_canary_mode_is_disabled}` 原 `OPENCLAW_CANARY_MODE` + `OPENCLAW_DISABLE_CANARY_DUMP` 並行 flake
- 抽 pure fn `decide_canary_enable_from(canary_mode, disable_dump) -> CanaryEnableDecision`（3-variant enum `Enabled` / `DisabledByMode` / `DisabledByKillSwitch`，保留原 silent-disable vs `info!` log 雙語意 — 3-variant 而非 bool 為保留此差異）
- `spawn()` 改為薄 wrapper 讀 env 轉呼 pure fn → match 3 variant 保持 fall-through 行為；runtime 行為 byte-identical
- 移除 2 env-racy 測試，新增 5 decision 測試（net +3）；7 → 10 tests
- 全 engine lib 1840 → **1843 passed**（Mac debug + Linux release 均驗）；2× parallel runs 清無 flake
- `canary_writer.rs` 454 → 569 行（仍 ≤ 800 soft cap）
- 加 `CANARY-WRITER-ENV-RACE-1 (2026-04-21)` 雙語 explanatory block 於 test module 頂部，鏡像 `580304a` 模板

### 4.3 TICK-PIPELINE-MOD-UNUSED-IMPORTS-1 ✅ commit `c164cb6` · sub-agent 並行派發
- 清除 ON-TICK-SPLIT-1 (commit `bfedb56`) 後 `tick_pipeline/mod.rs` 暴露的 3 個 unused-import warnings（`RiskAction` / `Instant` / `debug`）
- 採 Option A（最乾淨）：step files 原本已有直接 `use`，單純從 `mod.rs` 移除 3 個 `use` 行即可；無 step 檔變動
- warnings 13 → 10（-3 對齊）；engine lib 1843 passed / 0 failed 不變；零語意改動

---

## 5. 運行時部署

### 5.1 2026-04-21 20:44 CEST `restart_all.sh --rebuild` ✅
- 基於 commit `f128af5`（baseline 1843 passed / 0 failed）
- 首次進 runtime 的累積 commits：
  - TRACK-P-T4-WIRING-1 (`e95c779`) — Priority 6 PHYS-LOCK 現可實際 fire（Gate 1 cold-start Hold 為預期）
  - DUAL-TRACK-EXIT-1 Phase 1b Track P v2 + GATE1-REVERSAL-1 hotfix A (`aee96b9` + `d0f0c21`)
  - EDGE-P2-3 Phase 2+ (b) bb_breakout + ma_crossover PostOnly entry
  - DECISION-OUTCOMES-* backfill wiring fixes (`5e2981d`)
  - EXIT-FEATURES-SPLIT-1 / ON-TICK-SPLIT-1 / AI-SERVICE-CLIENT-ENV-RACE-1 / CANARY-WRITER-ENV-RACE-1 / TICK-PIPELINE-MOD-UNUSED-IMPORTS-1（refactor wave）
- 舊 engine PID 3813984（13:44 CEST rebuild） → 新 PID **3954769**（20:44 CEST）
- Binary mtime 20:44，22.85 MB release profile
- 驗證：demo engine snapshot_age 1.5s；paper disabled；live 未 alive；340k+ ticks / 20 min（~280/sec）
- Errors 24 全 pre-existing cold-start noise（21× cryptopanic news auth / 3× instrument spec 冷啟動 fail-closed），0 panics
- `phys_lock_*` log count = 0（符合 edge_estimates 冷啟動 → Gate 1 Hold 預測）
- 21d demo 時鐘**未重置**（計劃性 rebuild 不重置，時鐘仍從 2026-04-16 22:16 起算）

---

## 相關 commits 時序索引

```
8460505  docs(claude_md): update engine PID + rebuild timestamp post-deploy
f128af5  docs: sync TODO + §三 + §十一 + CHANGELOG for CANARY-WRITER + unused-imports cleanup
c164cb6  refactor(tick_pipeline): 清除 ON-TICK-SPLIT-1 後 mod.rs 3 個 unused-import warnings
d454c17  test(canary_writer): CANARY-WRITER-ENV-RACE-1 — 抽 pure fn 根除 env-var flake
d8d7653  docs: sync TODO + §三 + §十一 + CHANGELOG for 2026-04-21 refactor wave
bfedb56  refactor(tick_pipeline): ON-TICK-SPLIT-1 — 2071 行單檔拆為 8 檔目錄
580304a  test(ai_service_client): AI-SERVICE-CLIENT-ENV-RACE-1 — 抽 pure fn 根除 env-var flake
3a9b988  refactor(exit_features): EXIT-FEATURES-SPLIT-1 — 1317 行單檔拆為 4 檔目錄
77fda02  docs(track_p): close TRACK-P-T4-WIRING-1 — runtime 接線 + baseline 1839
e95c779  feat(track_p): TRACK-P-T4-WIRING-1 — wire ExitFeatures builder at on_tick Priority 6
8671e2d  docs(workflow): harden rule — commit 完必 push (no exception, all CCs)
7e4aeb2  docs(close): DECISION-OUTCOMES-* suite closed via Linux ssh psql verify
(...and earlier 2026-04-21 work d0f0c21 / aee96b9 / 5a2c241 / db65458 / 5e2981d / 4df1345 etc.)
```

---

## 後續 TODO（本批次衍生）

保留在 TODO.md 主文件的 open 項：
- `TRACK-P-V2-SWAP-1` (P2, ~1d)：Priority 6 從 v1 linear 切 v2 non-linear + ExitConfig ArcSwap 熱重載
- `TICK-PIPELINE-MOD-SPLIT-1` (P3, ~2-3d)：`tick_pipeline/mod.rs` 2276 行超 1200 hard cap，結構上比 on_tick.rs 難拆（涉及 `TickPipeline` struct + 多 impl block 分散）

---

## 測試基準線演進（2026-04-21 單日）

```
1816 → 1819 → 1827 → 1839 → 1840 → 1843 passed / 0 failed
  │     │      │      │      │      │
  │     │      │      │      │      └─ +3 CANARY-WRITER-ENV-RACE-1 decision tests
  │     │      │      │      └─ +1 AI-SERVICE-CLIENT-ENV-RACE-1 precedence test
  │     │      │      └─ +12 TRACK-P-T4-WIRING-1 builder tests
  │     │      └─ +4 bb PostOnly tests + +4 ma PostOnly tests (EDGE-P2-3 Phase 2+ (b))
  │     └─ +3 outcome_backfiller regression tests (5e2981d)
  └─ baseline（aee96b9 v2 pure fn + 31 單測已納入 1816）

Build warnings: 13 → 10 (−3 via TICK-PIPELINE-MOD-UNUSED-IMPORTS-1)
```

---

*生成：2026-04-21 晚 · Mac CC (PM+Conductor) 批次歸檔*
