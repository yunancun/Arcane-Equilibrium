---
歸檔日期: 2026-04-29
來源: srv/CLAUDE.md §三「當前系統狀態摘要」
原段落採集時間: 2026-04-24 22:00 CEST 起 (G6-04 §三 drift 規則) 至 2026-04-26
歸檔理由: §三 衛生規則 (line 308) 規定「§三 只記載現況/活躍狀態 + 過去 ≤2 天完成里程碑；任何完成里程碑當天 +2 日必須歸檔」。Today = 2026-04-29，故 2026-04-26 (含) 之前的詳細執行敘述全部歸檔到本檔。
語言策略: 中文敘述為主，搬運自 CLAUDE.md 原文 (不改原意)；英文技術名詞 / commit hash / 路徑保留。
---

# CLAUDE.md §三 歸檔：2026-04-22 ~ 2026-04-26 詳細執行敘述

本檔保存 CLAUDE.md §三 在 2026-04-29 衛生整理前的詳細敘述，涵蓋：

1. 2026-04-22 ~ 2026-04-23 INFRA-PREBUILD-1 Part A (Combine Layer shadow 骨架) 5 commits
2. 2026-04-23 INFRA-PREBUILD-1 Part B (Model Registry + Canary 骨架) 5 commits
3. 2026-04-23 DEDUP-PY-RUST 獨立重審全鏈閉環 A+B+C+D 5 commits
4. 2026-04-22 P0-13 ATR scale 修正 + P0-14 A/B Gate 1 fallback + JS proxy cells + Priority 6 物理層細節
5. WS-RETIRE-1 Python `bybit_private_ws_listener.py` 退役完成
6. 2026-04-23 audit 更正：`main_legacy.py` 拆分閉環確認 (54 routes / 5 sibling / 468 行瘦身結果)

對應 §三 line 50 (Runtime 巨型 paragraph)、line 52 (權威原則 audit 更正 paragraph)、line 87 (2026-04-23 表格行)。

---

## 2026-04-22~23 INFRA-PREBUILD-1 Part A (Combine Layer shadow 骨架)

**狀態**: ✅ 5 commits — `6226b38` / `419bd34` / `83ece53` / `66b061f` / `74b678a`
**runtime 影響**: Phase 1a 全 dormant，flag OFF 時 0 emit / 0 row、`fills.exit_source` 除 PHYS-LOCK 外全 NULL。

### A1 — V021 migration
- `trading.fills.exit_source` 欄位 + partial index
- `learning.decision_shadow_exits` hypertable + 4 indexes

### A2 — `shadow_exit_writer.rs` + 接線
- `ShadowExitMsg` 訊息類型新增
- `tasks.rs` 8-tuple 擴充
- `main.rs` 3× `EventConsumerDeps` 接線
- pipeline setter / accessor 補齊

### A3 — combine_layer 雙跑骨架
- `combine_layer::build_ml_inference_shadow` mock producer
- `helpers::emit_shadow_exit_observation` sibling fn 走 `combine_exit_decision` 兩次比對 disagreed
- `try_send` shadow exit msg

### A4 — `TradingMsg::Fill.exit_source: Option<String>`
- `trading_writer` INSERT 從 V017 升級到 V021 欄位
- 6 construction sites 同步更新
- `emit_close_fill` 從 `close_tag` 經 `strip_phys_lock_prefix` 推 Physical tag (避 RUST-DOUBLE-PREFIX-1 regression)

### A5 — `ExitConfig.shadow_enabled: bool` flag
- 3 env TOML 同步 (paper / demo / live)

### A6 — passive_wait_healthcheck [8] `check_shadow_exit_ratio`
- silent-dead guard
- Phase 1a dormant 與 Phase 2+ silent-dead 藉 row count / rowcount breakdown 三角檢

### Verification
- engine lib **1905 passed** (+70 vs 1835 baseline)
- Phase 2 啟動 = operator 改 TOML 或 IPC `patch_risk_config` flip `shadow_enabled=true`，**無須 rebuild**
- 後續 Part B = Model Registry + Canary deployment 基礎設施

---

## 2026-04-23 INFRA-PREBUILD-1 Part B (Model Registry + Canary 骨架)

**狀態**: ✅ 5 commits — `3c3a030` / `91288f1` / `9f6d4c5` / `061cb19` / `01085a6`
**runtime 影響**: Phase 1a 零影響 — registry 空，所有 routes 回 404 / rows=0，直到訓練 pipeline 寫入第一行 (P1-7 C labels 47/200 還在累積)。

### B1 — V023 migration
- `learning.model_registry` hypertable + 4 indexes
  - 唯一鍵
  - production-latest partial
  - canary_status
  - train_date freshness
- auto-touch trigger

### B2 — Python `model_registry.py`
- ~295 LOC + 11 unit tests
- `register_model` + `register_quantile_trio_from_onnx_out` wrapper
- `transition_canary_status` state machine validator
- `ON CONFLICT` 保 `canary_status` 不退 shadow
- `test_model_registry.py` 11 tests 全綠
- `run_training_pipeline.py` stage 5.5 hook

### B3 — Rust `ml::registry` 讀 helper
- 5 unit tests
- `ModelSlot` Hash / Eq
- `resolve_latest_production_artifact` async fn
- `symlink_filename` 命名對齊 Python
- `log_registry_failure` warn-log wrapper
- `OnnxModelManager` 不動，Phase 3+ 整合

### B4 — IPC SKIP
- Rust 端無 live consumer，Python 直查 DB 更乾淨

### B5 — `/api/v1/ml/{model_registry|model_info|model_promote}` routes
- list + single-slot resolver
- Operator-gate 狀態機 promote
- irreversible 轉移需 `confirm:true` + `retirement_reason`

### B6 — Canary rules draft
- `docs/references/2026-04-23--model_canary_promotion_rules_draft.md`
- 狀態機 + 每 Phase 晉升閾值 + Operator playbook
- Phase 4 auto-promote cron 延後

### B7 — healthcheck [9] `check_model_registry_freshness`
- per-slot oldest train_date 30d / 60d 閾值
- Phase 1a / 2 empty PASS note

### Verification
- engine lib **1910 passed** (Part A 1905 + B3 5 registry tests)
- operator 下一步 = labels 滿 200 跑 `run_training_pipeline.py` 觀察 registry 自動填入 → 人工評估 → `POST /model_promote` 狀態推進

---

## 2026-04-23 DEDUP-PY-RUST 獨立重審全鏈閉環 A+B+C+D

**狀態**: ✅ 5 commits — `87e3ecf` / `16acb64` / `b9b0a57` / `b5cf59e` / `f42face`
**淨減**: Rust +685 / Python+shell -12.8k (98 shells + 3 retire + 7 governance 合計)

### A — 刪 `program_code/governance/`
- commit `87e3ecf`
- 7 檔 284 行刪除

### B — docs-only canonical path note 清理
- commit `16acb64`

### C 前半 — Rust `bybit_private_ws_status_writer.rs`
- commit `b9b0a57`
- +664 行含 11 單測
- `ExecutionListener.stats_arc()` 曝露
- `spawn_private_ws_supervisor` Demo / LiveDemo 條件 spawn

### C 後半 — Python listener + ctl shell 退役
- commit `b5cf59e`
- 刪 `bybit_private_ws_listener.py` + 2 `_ctl.sh` 共 3 檔 340 行

### D — legacy 修復 / shim shell 清掃
- commit `f42face`
- 刪 `helper_scripts/maintenance_scripts/bybit_connector/` 53 個 legacy H/I/J/K-chain 修復 shell
- 刪 `program_code/.../scripts/` 45 個對應 shim wrapper
- 共 98 檔

### 多角色 audit 修正
- 3 並行 Explore sub-agent 獨立核實 + 主會話交叉驗證
- 修正 Agent 1 對 `local_model_tools/` 19 個 singleton-contract stub 的誤刪判斷
- 修正 Agent C「Rust never spawned」誤判 (實際 `startup.rs:872` 已 spawn)

### Deploy & Verification
- 2026-04-23 21:13 CEST `--rebuild` 後 Rust writer 接管 status JSON 產生 (`listener_version: "rust-v1"`)
- `pkill -f bybit_private_ws_listener.py` exit=1 (Python 進程早已不跑)
- observer pipeline smoke 通過
- `SCRIPT_INDEX.md` + `LOGICAL_SCRIPT_CATEGORY_MAP.md` + `helper_scripts/SCRIPT_INDEX.md` 同步更新
- engine lib 本 session +11 (writer tests)，與 operator Part A/B 合計達 **1910 passed**
- 報告 `.claude_reports/20260423_200043_dedup_fresh_audit_A_governance_delete.md`
- 報告 `.claude_reports/20260423_202943_dedup_fresh_audit_BC_ws_retire.md`

---

## 2026-04-22 P0-13 ATR scale 修正 + P0-14 A/B Gate fallback + JS proxy cells + Priority 6 物理層

**runtime 來源**: 2026-04-22 23:35 rebuild 引入，至 2026-04-24 22:00 仍 live。

### P0-13 ATR scale (持倉期 Wilder's ATR)
- `kline_manager.get_ohlcv("1m", 20) + indicators::atr(14)`
- 持倉期 Wilder's ATR ~0.05-0.5%
- 舊 per-tick `compute_atr_pct` `#[deprecated]` 保留 `fast_track` 用

### P0-14 A — Gate 1 fallback
- `ExitConfig.missing_edge_fallback_bps = -10.0`
- 本 commit EDGE-DIAG-1-FUP-IPC 前**無 IPC 路徑**，TOML 編輯需引擎重啟才生效
- 本 commit 新增 7 個 `exit.*` 欄位的 IPC 熱重載路徑 + TOML persist
- Phase 3 部署後可 <60s 回滾

### P0-14 B — JS proxy cells
- Python `_inject_sync_label_proxy_cells` 從 43 → **135 cells**
- +4 sync-label strategies × 23 symbols = 92 proxy cells

### Priority 6 物理層 (V2 SWAP 後)
- 每 tick 呼 `physical_micro_profit_lock_v2` + `ExitConfig`
- healthcheck [7] 135 / 135 PASS 即時驗證
- `phys_lock_*` fire 1-10 / day
- DB `learning.exit_features.giveback_atr_norm` avg 從 364 → ~0.3-3.0
- DB `atr_pct` avg 從 0.003 → ~0.05-0.5
- 觀察中

### 詳見報告
- `docs/worklogs/2026-04-22--passive_wait_silent_fail_audit.md`
- `docs/worklogs/2026-04-22--p0_13_14_execution_resume_plan.md`
- `.claude_reports/20260423_202943_dedup_fresh_audit_BC_ws_retire.md`

---

## WS-RETIRE-1 Python `bybit_private_ws_listener.py` 退役完成

**狀態**: ✅ (2026-04-23 完成，runtime 2026-04-24 22:00 已驗證生效)

### 取代關係
- Rust `bybit_private_ws_status_writer.rs` 每 5s 產 `bybit_private_ws_listener_status_latest.json`
- 內含：
  - `listener_version: "rust-v1"`
  - `engine_mode: "demo"`
  - `auth_ok_count: 1`
  - 4 topics live

### Python 端刪除
- `bybit_private_ws_listener.py` + 2 `_ctl.sh` 共 3 檔 340 行刪除

### 下游驗證 (readonly_observer_pipeline)
- `bybit_build_ws_runtime_facts.py` 讀取無感
- `listener_health: healthy`
- `business_signal_state: active`
- 即時驗證通過

---

## 2026-04-23 audit 更正：`main_legacy.py` 拆分閉環確認

**重要更正**: 先前 2026-04-16 audit「共 1630 行 · 此層拆分未完成」**敘述過期**。

### 實況 (2026-04-23 audit 確認)
Wave A-D 拆分**已完成**，54 routes 已分至 5 個 sibling：
- `auth` 128 行
- `gui` 81 行
- `system` 303 行
- `learning` 553 行
- `control` 493 行

### 聚合註冊
- 由 `main_legacy.py:464-468` `register_*_legacy_routes(app)` 5 行聚合註冊

### `main_legacy.py` 瘦身結果
- 瘦至 **468 行** (原 ~5265 行瘦身 91.1%)
- 只剩：
  - 4 singleton (`settings` / `STORE` / `app` / `limiter`)
  - 3 helpers (`envelope_response` / `get_latest_snapshot` / `current_actor`)
  - 4 middleware

### 總和
- main 468 + sibling 1558 = **2026 行**

### Tier B 結案決定
- Tier B 實質閉環
- 進一步拆 singleton / 改名屬 cosmetic 非必要
- 下游 28 檔 `_base.xxx()` 動態查找為 `main.py` monkey-patch + 3 個 `importlib.reload(main_legacy)` 測試之契約
- 選 α 結案 — 純 doc 改動無 Rust / Python 邏輯變更，engine lib baseline 1835 不變

### 連帶 Tier A 收尾 (commits `b4d6a56` + `d39d1b4`)
- A+B pre-work：刪 `cleanup_legacy_ai_env.py` 95 行 + 裁 `replay_runner.py` 4 個無人用 `_serialize_*` helpers，共減 ~145 行 dead code
- Tier A 10 steps 由 sub-agent 逐檔驗證**全部已 stub** (主 commit `d41f72a` + follow-up `d1e171c` + stub-shape fix `2215bee`，2026-04-16~17)
- `test_stub_contracts.py` 59 tests 採 RUNNING_OK 模式全綠
- contract_check 已清除
- `dedup_cleanup_plan.md` header 從「計劃級 (尚未動工)」更新為「✅ 已完成」+ 實測效益 ~6700 行淨減

---

## 歷史指針

- §三 2026-04-16 STABILITY-1 / LIVE-GUARD-1 + 2026-04-19 完整敘述 → `docs/archive/2026-04-21--claude_md_section3_snapshot.md`
- §三 2026-04-17 / 18 完整敘述 → `docs/archive/2026-04-20--claude_md_section3_snapshot.md`
- §三 2026-04-15 之前完整敘述 → `docs/archive/2026-04-15--claude_md_section3_snapshot.md`
- 1A → 1C-4 commit 敘事 → `docs/archive/2026-04-08--arch_rc1_1c_history_archive.md`
- Phase 0-4 Sprint / Wave → `docs/archive/2026-04-07--claude_md_section3_history_phase0_4.md`
- 逐 commit 行數 → `docs/CLAUDE_CHANGELOG.md`
- 1C-3 / 1C-4 narrative → `docs/archive/2026-04-08--main_docs_1c3_1c4_narrative.md`

---

## 歸檔元資料

- 歸檔者: TW agent
- 歸檔指令: operator 透過 PM 派發「歸檔 CLAUDE.md §三中超過 2 天的詳細執行敘述」
- 對應 CLAUDE.md §三 衛生規則: line 308「§三 只記載現況/活躍狀態 + 過去 ≤2 天完成里程碑；任何完成里程碑當天 +2 日必須歸檔」
- 後續行動: 主會話另派 TW 修改 CLAUDE.md，將上述 6 大塊內容替換為單行歸檔指針。本檔不修改 CLAUDE.md / TODO.md / memory。
