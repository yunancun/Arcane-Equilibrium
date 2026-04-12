# 2026-04-12 Session 2 — P1 全程序鏈審計修復

> Session 1 完成 P0（8/8），本 session 完成 P1（18/18）。

---

## 完成項目（18 項 P1 全部完成）

### 一、P1 核心修復（7 項）

| FIX | 問題 | 修復方式 | 文件 |
|-----|------|---------|------|
| **FIX-05** | `correlated_exposure_pct` 永遠 0.0，原則 #16 組合級風險失效 | 新增 `compute_correlated_exposure_pct()` — max(long_notional, short_notional)/balance×100%，替換 router.rs 兩處硬編 0.0 | `intent_processor/mod.rs` (+23), `intent_processor/router.rs` (×2) |
| **FIX-06** | GridTrading `grid_levels` TOML 配置存但不用（假功能） | `GridTradingParams` 新增 `grid_levels` 欄位 + `GridTrading` 新增 `grid_count` 字段 + `update_params()` 接線 + 替換 5 處 `DEFAULT_GRID_COUNT` 為 `self.grid_count` | `strategies/grid_trading.rs` (+57-) |
| **FIX-07** | OU theta clamp 0.001 在非均值回歸序列產生 44.7× sigma 巨大間距 | `compute_ou_step()`: b>=0 時 return None（非 OU 回退 adaptive ±10%），theta 下限從 0.001 提高到 0.01 | `strategies/grid_trading.rs` |
| **FIX-11** | Cookie `secure=False` — HTTP 明文傳輸 auth token | `secure=request.url.scheme == "https"` 自動偵測，login+logout 兩處 | `legacy_routes.py` (L322, L342) |
| **FIX-20** | `pre_check_order()` 使用真實 `/v5/order/create` — 意外下單風險 | 函數整體刪除（死碼，從未被調用） | `platform_client.rs` (-20) |
| **FIX-22** | 4 個 `MlSwitches` 欄位（linucb/thompson/directive/scorer_enabled）從未被運行時讀取 — 假功能 | 刪除 4 欄位 + Default impl + 2 個相關測試斷言，僅保留 `teacher_loop_enabled` + `news_pipeline_enabled` | `config/learning_config.rs` (-37), `ipc_server/tests.rs` |
| **FIX-55** | 3 個 Bybit API 路徑 MISMATCH（confirm_pending_mmr/set_hedging_mode/repay）— 死碼 | 查閱 Bybit API 手冊確認路徑正確，標註 `#[allow(dead_code)]` + 驗證注釋 | `position_manager.rs`, `account_manager.rs` |

### 二、P1 性能優化（3 項）

| FIX | 問題 | 修復方式 | 影響 |
|-----|------|---------|------|
| **FIX-29** | on_tick.rs 1307 行 > 1200 硬上限 | 新建 `on_tick_helpers.rs`，抽出 `maybe_canary_record()` + `compute_indicators()` + `process_aggregator_events()` + `emit_periodic_snapshots()` | 1307 → 1186 行 |
| **FIX-30** | symbol.clone() ~37 次在 on_tick 熱路徑 | 審查全部 37 處 — 多數為必要（建構 owned struct），真正的 perf win 在 FIX-32 | 文檔性結論 |
| **FIX-32** | `risk_config().clone()` 每 tick 深拷貝 RiskConfig | 改為借用 `&RiskConfig`（`evaluate_positions` 已接受引用） | 每 tick 省一次深拷貝 |

### 三、P1 測試覆蓋（3 項，+9 新測試）

| FIX | 問題 | 新增測試 | 位置 |
|-----|------|---------|------|
| **FIX-16** | startup.rs 856 行零測試 | +5: version 非空 / channel_size 合理 / paper_balance env 缺失 / toml 缺失 / load_unified_configs 默認值 | `startup.rs` #[cfg(test)] |
| **FIX-17** | ConfigStore hot-reload 並發未驗證 | +2: 10 reader + 5 writer 無撕裂狀態 / version 單調遞增（3 writer ×100 = 300） | `config/store.rs` |
| **FIX-18** | Price=0.0 tick 除零風險未測試 | +2: 零價 tick 不 panic / 有持倉時零價不產 NaN | `tick_pipeline/tests.rs` |

### 四、P1 GUI + 文檔（5 項）

| FIX | 問題 | 修復方式 |
|-----|------|---------|
| **FIX-39** | Danger Zone（resetCooldown/unhaltSession）用原生 `confirm()` | 替換為 `openConfirmModal("reset-cooldown"/"unhalt-session")`，新增 CRITICAL_ACTIONS 條目 |
| **FIX-40** | 策略刪除用原生 `confirm()` | 替換為 `openConfirmModal("delete-strategy")`，新增 CRITICAL_ACTIONS 條目 |
| **FIX-47** | CLAUDE_REFERENCE.md 過時 6 天 | 更新至 2026-04-12，加入 DEAD-PY-2 / 3E-ARCH / Phase 6 狀態摘要 |
| **FIX-48** | KNOWN_ISSUES.md 過時 7 天 | ARCH-2→RESOLVED（PipelineBridge 已刪）、RISK-3→RESOLVED（Rust 日損限額已實現）、統計更新 |
| **FIX-52** | SCRIPT_INDEX.md 覆蓋率 ~11% | 全面重寫：6 頂層 + 1 db + 6 canary + 3 phase4 + 1 maintenance + 7 legacy 常用項，~90% 覆蓋 |

---

## 測試基線

| 類別 | Session 前 | Session 後 | 差異 |
|------|-----------|-----------|------|
| Engine lib tests | 961 | 965 | +4（FIX-17 ×2, FIX-18 ×2） |
| Engine bin tests | 0 | 5 | +5（FIX-16 startup） |
| Engine e2e tests | 29 | 29 | 不變 |
| **Engine 合計** | **990** | **999** | **+9** |

全部 0 failure。

---

## 新增/修改文件清單

### 新增文件（2）
- `rust/openclaw_engine/src/tick_pipeline/on_tick_helpers.rs` — FIX-29 抽出的 4 個輔助方法
- `docs/worklogs/2026-04-12--session2_p1_full_program_audit_fixes.md` — 本日誌

### Rust 修改（12 文件）
- `intent_processor/mod.rs` — FIX-05 compute_correlated_exposure_pct()
- `intent_processor/router.rs` — FIX-05 替換兩處 0.0
- `strategies/grid_trading.rs` — FIX-06 grid_count + FIX-07 OU theta
- `config/learning_config.rs` — FIX-22 刪除 4 假欄位
- `config/store.rs` — FIX-17 +2 並發測試
- `ipc_server/tests.rs` — FIX-22 測試更新
- `platform_client.rs` — FIX-20 刪除 pre_check_order
- `position_manager.rs` — FIX-55 #[allow(dead_code)]
- `account_manager.rs` — FIX-55 #[allow(dead_code)]
- `startup.rs` — FIX-16 +5 tests
- `tick_pipeline/mod.rs` — FIX-29 新增 mod on_tick_helpers
- `tick_pipeline/on_tick.rs` — FIX-29 抽出方法 + FIX-32 借用
- `tick_pipeline/tests.rs` — FIX-18 +2 tests

### Python/GUI 修改（4 文件）
- `legacy_routes.py` — FIX-11 cookie secure 自動偵測
- `app.js` — FIX-39/40 新增 3 個 CRITICAL_ACTIONS
- `tab-risk.html` — FIX-39 替換 confirm()
- `tab-strategy.html` — FIX-40 替換 confirm()

### 文檔修改（4 文件）
- `TODO.md` — P1 全部 18 項標記 [x]
- `CLAUDE_REFERENCE.md` — FIX-47 時間戳 + 狀態更新
- `KNOWN_ISSUES.md` — FIX-48 ARCH-2/RISK-3→RESOLVED
- `helper_scripts/SCRIPT_INDEX.md` — FIX-52 全面重寫

---

## 決策記錄

1. **FIX-30 結論**：37 處 symbol.clone() 中 95% 為必要（建構 owned String 欄位）。Rust String clone 對 ~10 字元 symbol 約 40ns，與 FIX-32 的 RiskConfig 深拷貝（含 HashMap/Vec 嵌套）相比可忽略。不做無意義的 `&str` 改造。

2. **FIX-55 處置**：3 個 API 路徑查閱 Bybit V5 API 手冊確認均正確（`/v5/position/confirm-mmr`, `/v5/account/set-hedging-mode`, `/v5/account/repay`）。函數為預接線死碼（UTA/Hedging/Spot Margin 功能），標註 `#[allow(dead_code)]` 而非刪除。

3. **FIX-29 拆分策略**：選擇最低風險方案 — 抽出 4 個自包含方法到 `on_tick_helpers.rs`（同為 `impl TickPipeline`），不改變任何邏輯。避免重構核心 on_tick 迴圈。

---

## 二輪嚴格驗證 + CONCERN 修復（Session 2 延伸）

8 組並行 agent 逐行讀碼驗證全部 26 FIX，結果 **26/26 PASS**。發現 3 CONCERN + 2 過期 KNOWN_ISSUES，全部當場修復：

### CONCERN 修復（3 項）

| 問題 | 修復 | 文件 |
|------|------|------|
| **FIX-03b** ReduceToHalf 缺 `dispatch_close_order()` — Live 真金白銀 bug | 半倉平倉後補 `dispatch_close_order(sym, is_long, half_qty, event, is_primary)` | `on_tick.rs` +4 行 |
| **FIX-19b** 單一 taker_fee_rate 近似所有 symbol | 改用 `pipeline.intent_processor.fee_rate(&exec.symbol)` — 3 級解析 AM→legacy→constant | `event_consumer/mod.rs` |
| **FIX-16b** 2/5 startup tests trivially passing（編譯期常量） | `test_version_is_nonempty` → `test_version_is_valid_semver`（semver 格式）；`test_event_channel_size_reasonable` → `test_paper_balance_from_env_valid_and_invalid`（4 case） | `startup.rs` |

### KNOWN_ISSUES 修復（2 項）

| Issue | 狀態 | 理由 |
|-------|------|------|
| **TRADE-2** Intent 排隊競態 | → RESOLVED | Rust on_tick 同步：fast_track L80-155 先於 intent L500+，`ft_pause_new_entries` 阻止同 tick 開倉 |
| **TRADE-4** Partial Fill 回滾量不一致 | → RESOLVED | Rust 每筆 fill 獨立攜帶 exec_qty，`apply_fill`/`reduce_position` 僅用傳入量，無"回滾"概念 |

統計行修正：OPEN 8 → 9（原始計數錯誤）→ 修 TRADE-2/4 後 OPEN 9 / RESOLVED 15。

---

## 未完成 / 不在範圍

- **P2/P3 共 25 項**（文件拆分、策略參數化、ML backfill、文檔清理等）— 見 TODO.md
- **Commit**：所有改動未提交，等待 operator 確認後一次性 commit

---

## 下一步

- P0+P1+CONCERN 全完 → commit
- W22 Thu+: G-1 R-02 AI Agent（Strategist/Guardian）
- LG-1 21d paper 到期（2026-05-01）
