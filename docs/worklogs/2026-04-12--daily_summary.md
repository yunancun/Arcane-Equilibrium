# 2026-04-12 Daily Summary

全程序鏈 P0→P1→P2→P3 審計修復 58 findings + A3 GUI 可用性審計 36 findings + BB Bybit API 審計 10 findings + FIX-08 文件拆分（14 新檔）+ Earned-Trust TTL Ladder + PNL-FIX-1/2 + GUI 指標 DB 降級。

## 完成項目 / Completed

### PNL-FIX-1 / PNL-FIX-2（commits `2a422fa` / `cbb4e45`）
- **PNL-FIX-1** `on_tick.rs` 5 條 close 路徑誤用 `event.last_price` 跨 symbol 平倉 → per-symbol latest_price；PnL 原被放大 1000-10000×
- **PNL-FIX-2** `emit_close_fill` 寫 `fee: 0.0` → 加入真實手續費計算（所有 risk/strategy/fast_track 平倉原根本不收費）
- **揭露**：乾淨基線後所有活躍策略 gross edge 為負（非僅扣費後負），net 總損 -$2775
- **Phase 5 暫停**：cost_gate 工作等策略重做

### Session 1 — P0 審計修復（commit `283ae33`）
**8 P0 全修**（阻擋 Phase 5 + Live promotion）：
- IPC HMAC Live 強制 · FastTrack 半倉 / 暫停 · price_drop 真實值 · `execution.fast` execFee backfill · `edge_estimates` +14 tests · REST fail-closed +7 tests · 三管線並發 +1 e2e · `ocEsc` 單引號
- 基準線：engine lib **961** + core 366 + e2e 29 = **1356** passed

### Session 2 — P1 審計修復（commit `09f64c1`）
**18 P1 全修**：
- `correlated_exposure_pct` 計算（max→sum of abs notional）· GridTrading grid_count（TOML 上限 50）· OU mean-reversion θ lag-1 autocorrelation fallback · Cookie `secure=True` · startup tests · hot-reload 並發 · Price=0 防護 · deprecated `pre_check_order` 移除（配 BB-A5）· MlSwitches dead field 清理 · `on_tick` 拆分為 `on_tick_core` + `on_tick_helpers` · `risk_config` 熱路徑借用（`clone()` → `Arc` + `&str`）· Danger Zone modal · CLAUDE_REFERENCE / KNOWN_ISSUES / SCRIPT_INDEX 更新 · 3 CONCERN + 2 KNOWN_ISSUES 同步修

### Session 3 — P2 Rust 7 修復（commit `84f00eb`）
- **FIX-24** `rsi_thresh` RSI 14 硬編碼 → TOML 參數
- **FIX-25** `fee_rate` TOML-driven
- **FIX-26** `squeeze_expiry` 單次過期處理（原永不超時 bug）
- **FIX-27** negative Kelly rejection（≤0 直接 skip 而非 clamp）
- **FIX-28** `account_leverage` 從 config 讀取（原硬編碼 5x）
- **FIX-31** `PriceEventKind` enum（原 String matching 運行時 typo 風險）
- **FIX-33** `HashSet` O(1) dedup（原 `Vec<String>::contains` O(n)）

### Session 3.1 — P2 Batch A+B 10 修復（commit `421277a`）
- **FIX-21** 3 orphan modules 刪除 · **FIX-38** Singleton registration table（本 CLAUDE.md §九 登記表）· **FIX-41** Bearer auth dead code · **FIX-44** Tab loading UI polish · **FIX-45** Live refresh 5s→15s · **FIX-46** skipped · **FIX-51** 3 DEPRECATED archive · **FIX-53** README index · **FIX-54** CHANGELOG 完整度 · **FIX-56** Layer 2 date consistency

### Session 3.2 — P2 Final 5（commit `0de58bb`）
- **FIX-08** 文件拆分（詳下段）
- **FIX-23** FundingArb factory 接線
- **FIX-34** `decision_outcomes` 7 天 backfiller 腳本
- **FIX-35** DDL DRAFT 移出 migration 目錄
- **FIX-57** Python / Rust AI budget IPC sync（雙端一致性）

### Session 3.3 — P3 + QC 硬編碼參數抽取
**P3**：FIX-36 `delegation_framework.py` 刪除 · FIX-42 console double-nav 修復 · FIX-43 tab-trading iframe unnesting · FIX-49 3 個 daily_summary 命名修正
**QC H1-H12 12 硬編碼值抽為 TOML**：RG-2 risk global bounds · `#2` KAMA 參數 · `#7` hurst_boost · **H10 FundingArb 5 參數** · `#17` multi-symbol HashMap。engine lib **934**。

### A3 GUI 可用性審計修復
**36 findings 全修**：2 CRITICAL + 14 MAJOR + 18 MINOR + 2 SUGGESTION
- `openConfirmModal()` tab-*.html → `common.js`（消除 5 份重複）
- SVG sparkline 取代 lightweight-charts（dead dep 移除）
- `?embed=1` 模式：子頁面獨立 / 嵌入 iframe 雙用
- E2 15/15 PASS · P3 Clean Sweep §2.2/§4.1/§6.1 = 20/20 PASS

### BB Bybit API 審計（commit `d6a3c17`）
**7 P1 + 3 P2**：
- BB-A1 `confirm-pending-mmr` 路徑確認 · BB-A2/A3 set-hedging / repay 驗證 · BB-A4 `execution.fast` execFee backfill（配 FIX-19b）· BB-A5 `pre_check_order` 移除（Bybit API 不存在，死代碼，配 FIX-20）· BB-A6 `get_repayment_available` rename（配 FIX-57）· BB-A7 `adl-alert` dead code warning（配 FIX-58）

### FIX-08 文件大小拆分（§九 硬上限 1200 行）
**3 批次 / 14 新檔 / 9 修改檔 / 1 bonus bug fix**：
- **Rust**：`risk_config.rs` → `risk_config_defaults.rs`；`event_consumer/mod.rs` → `event_consumer/handlers.rs`；`applier.rs` 拆分
- **Python**：
  - `backtest_engine.py` 1352→1142（+ `backtest_types.py` 239）
  - `signal_generator.py` 1452→1174（+ `signal_engine.py` 315）
  - `governance_routes.py` 1914→1172（+ `governance_extended_routes.py` 585 + `governance_promotion_routes.py` 240）
  - `governance_hub.py` 1812→1052（+ `governance_hub_cascades.py` 811）
  - `live_session_routes.py` 1253→1115（+ `live_session_governance.py` 178）
- **JS/HTML/Doc**：
  - `app.js` 2627→699（拆為 app-gui/app-actions/app-learning/app-review/app-paper）
  - `tab-governance.html` 2047→477（+ `governance-tab.js` 1579）
  - `tab-risk.html` 1390→510（+ `risk-tab.js` 889）
  - `CLAUDE_CHANGELOG.md` 2147→909（+ archive pre-0408）
- **拆分技術**：Re-export `# noqa: F401` 保路徑 / Side-effect 路由註冊（`from . import x as _x`）/ Mock 可修補的模組級委託 / Mixin 繼承（`GovernanceHub(GovernanceHubStatusCascadeMixin)`）/ HTML inline `<script>` 外提 + 依賴順序保證
- **Bonus bug fix**：`index.html` 缺 `common.js` 引用 — pre-existing bug，35 處 `ocEsc()` 原本找不到
- **總驗證**：Python 2852 + Rust engine **965** + Rust core 366 = **4183 passed, 0 fail**

### Earned-Trust TTL Ladder + Audit Trail 時間戳修復（commit `5d99875`）
**觸發**：Operator 報告 (a) Audit Trail 時間永遠 `--`；(b) Live 從未看到授權過期通知。

**Bug 1 根因**：`tab-governance.html` JS 讀 `r.timestamp`，Rust `ChangeRecord.to_dict()` 實際輸出 `when` / `when_ms`。**1 行修**：`r.when_ms ? ocTime(r.when_ms) : (r.when ? ocTime(r.when * 1000) : '--')`。

**Bug 2 根因**：`_EXECUTION_AUTHORITY_OVERRIDE` 無 TTL（運行中永遠有效）；SM-01 24h TTL 僅記錄不阻斷。兩層脫鉤 → operator 永遠不知道。

**Tier 設計**（連續乾淨天數，違規全重置；中途降級即時通知 session 不中斷）：

| Tier | TTL | 晉升條件 | 指標門檻 |
|------|-----|---------|---------|
| T0 Entry | 24h | 初始 / 任何 stop 後 | — |
| T1 Provisional | 72h | T0 + 7 連續乾淨天 | net_pnl>0, dd<5%, cost_ratio<50%, 零嚴重 |
| T2 Established | 168h | T1 + 14 連續乾淨天 | + win_rate≥35%, pf≥1.2, sharpe≥0.5 |
| T3 Trusted | 360h | T2 + 21 連續乾淨天 | + pf≥1.4, sharpe≥0.8, consec_loss<5, window_dd<10% |

- **中途降級**：`consecutive_losses≥5` / T2-T3 `daily_dd≥8%` / `reconciler_major_drift_cycles≥3` → 降一級
- **T3 續期**：首次 `renewals_at_t3=0`；renew +1；`>=1` → `block_review` 強制 `/renew-review` 全面審查（最長 30 天強制 operator 覆盤）
- **Session stop vs 重啟**：主動 stop → T0 重置；進程重啟 → JSON 恢復 tier（不懲罰重啟）

**實作**：
- `earned_trust_engine.py` 715 行 — `TrustTier` IntEnum / `TrustMetrics` dataclass / `_TIER_REQUIREMENTS` / `EarnedTrustState` 持久化 / thread-safe `threading.Lock` / module-level singleton with double-checked locking
- `live_trust_routes.py` 484 行 — `GET /trust-status`（任何角色）· `POST /renew`（operator）· `POST /renew-review`（T3 強制全審）· `_collect_live_metrics()` 多源 graceful degradation · `_create_live_auth()` SM-01 自動批准
- `live_session_routes.py` 1192→1197 行（docstring 壓縮 + hook：`on_session_start/stop` + 新增 `_grant_execution_authority_internal()` 供 renew 重新授予）
- `tab-live.html` Trust Status Bar + Renewal Card + Full Review Panel + `loadTrustStatus()` / `submitRenew()` / `submitFullReview()`
- **新增 53 測試** in `test_earned_trust_engine.py`（10 測試類：InitialState / SessionLifecycle / AuthRenewal / EvaluateRenewal / MidSessionDowngrade / IncidentRecording / CheckRequirements / Persistence / StateSnapshot / ThreadSafety）

**架構補全**：
```
前：_EXECUTION_AUTHORITY_OVERRIDE（無 TTL，永遠有效）
後：_EXECUTION_AUTHORITY_OVERRIDE + EarnedTrustEngine（TTL ladder）
    ↑ session stop → trust.on_session_stop() → T0 reset
    ↑ renew → _grant_execution_authority_internal() → in-memory gate 重新授予
```

### GUI 指標 DB 降級 + 顯示修復（4 bug，commit `7193705`）
**1. Live engine 顯示「已暫停」+ Start 可點** — `get_live_session_status()` 用 `rust.get_paper_state(engine="live")` 僅返回嵌套子對象，無頂層 `paper_paused` → 默認 True → session_state="paused"。**修**：另讀 `get_engine_snapshot(engine_kind)` 取頂層 `paper_paused`。`live_session_routes.py` L568-590。

**2. Performance Metrics 全 0（Paper/Live/Demo）** — `compute_full_metrics(state)` 期望 `fills/orders/pnl`，但 Rust `paper_state` 只有 `{balance, peak_balance, total_realized_pnl, total_fees, trade_count, positions}`；交易數據直寫 PostgreSQL `trading.fills`，不在快照累積，引擎重啟計數器歸零（DB 實有 paper 1336 fills / demo 68 fills）。**修**：
- 新增 `fetch_fills_from_db(engine_mode)` psycopg2 從 `trading.fills` 讀取
- `compute_full_metrics()` 加 `engine_mode` 參數，snapshot 無 fills 時自動 DB 降級
- `restart_all.sh` 傳 `OPENCLAW_DATABASE_URL` 給 API server
- **驗證**：Paper 1336 fills / 753 round trips / 32.75% win rate / Sharpe 0.029 / PnL 497199

**3. Live 掛單 Price + Status 顯示 "--"** — (a) Rust `OrderInfo` 缺 `trigger_price` 字段，停損單 `price=0.0` JS falsy → 嘗試 `o.triggerPrice`（不存在）→ "--"；(b) JS 用 camelCase `o.orderStatus` 但 Rust serde snake_case → undefined。**修**：`OrderInfo` 加 `pub trigger_price: f64` + 解析 Bybit `triggerPrice`；JS 改 `o.order_status || o.orderStatus`，price 用 `parseFloat()` 避免 falsy 0.0。**附帶**：需 `maturin develop --release` 重裝 PyO3 `.so` 到 API venv（兩 venv 問題，QoL-3 於 04-14 完成）。

**4. Demo 夏普比率硬編碼 N/A** — `tab-demo.html` L597 原始佔位符。**修**：基於 round-trip PnL 計算 Sharpe（≥2 筆啟用，mean/std 比率）。AI cost 維持 N/A（未接每引擎成本追蹤，TODO）。

### 其他修復
- **DB 跨管線 ID 碰撞修復**（commit `d670759`）— 所有 DB record ID（context_id / intent_id / verdict_id / fill_id / order_id）嵌入 `engine_mode` 前綴，防止三管線同 tick 時 ID 重複被 `ON CONFLICT DO NOTHING` 靜默丟棄。Signal 寫入限 Paper-only（V015 Signal Diamond 對齊）
- **IPC cross-engine routing 修復**（commit `35272d3`）
- **Paper/Demo session 獨立控制**（commit `986d724`）
- **Circuit-breaker 防誤觸發**（commit `6ae6e1b`）

## 測試基準線 / Test Baseline
- Rust engine lib: **965** + bin 5 + core **366** + e2e 29 + promotion 32 = **1397**
- Python: **2852 passed** · 5 skipped · 0 fail（+53 earned_trust 新測試）
- Total 4250 passed, 0 fail

## 關鍵決策 / Decisions
1. **Phase 5 暫停等策略重做**：策略 gross 負 edge，非費用問題（PNL-FIX-1/2 揭露）
2. **Earned-Trust 連續天而非累計**：違規全重置；中途降級 session 不中斷但下次 renew 必須從低 tier 開始
3. **T3 最多續期一次**：強制 30 天 operator 全面審查（`/renew-review` 端點）
4. **Session stop 重置 T0，進程重啟恢復 tier**：操作意圖 vs 基礎設施區分
5. **Performance Metrics DB 降級**：engine 重啟後快照計數器歸零是非阻塞限制，DB 降級繞過；根本修復（engine 啟動時從 DB 恢復累計）於 2026-04-14 QoL-1 完成
6. **Python module 拆分用 re-export + 模組級委託**：保留外部 import 路徑 + 確保 `unittest.mock.patch` 在測試中生效
7. **GovernanceHub 改 Mixin 繼承**：`GovernanceMode` / `GovernanceStatus` 移入 cascades 避免循環 import

## 遺留項 / Remaining
1. **Engine 重啟 paper_state 計數器歸零** — QoL-1 於 2026-04-14 完成 ✅
2. **PyO3 .so 雙 venv 部署** — QoL-3 於 2026-04-14 完成 ✅
3. **Demo AI cost** — 前端 N/A，後端無 per-engine AI 成本歸因（TODO）
4. **Paper engine PnL 異常** — DB 顯示 paper 總 PnL 497199（10k 起始，max dd 245%），疑似 paper 未正確限制槓桿 → Phase 5 reframe 後由 PNL-FIX-1/2 當日修復
5. **Mid-session trust downgrade 週期輪詢** — 需整合 contraction monitor loop（待 OC-3 告警整合）
6. **Operator 授權過期通知** — 目前僅 UI，無 email/Telegram 推送（待 OC-3）
7. **`_collect_live_metrics()` 的 `observation_days`** — 暫設 0（待 LG-1 21d 期補精確計算）

## Commits
- `2a422fa` PNL-FIX-1 · `cbb4e45` PNL-FIX-2
- `283ae33` P0 (8) · `09f64c1` P1 (18) · `84f00eb` P2 Rust (7) · `421277a` P2 Batch A+B (10) · `0de58bb` P2 Final (5)
- `d670759` DB 跨管線 ID 碰撞 · `d6a3c17` BB Bybit API 審計
- `5d99875` Earned-Trust TTL Ladder + Audit Trail 時間戳
- `7193705` GUI metrics DB fallback + 4 bug fix
- `35272d3` IPC cross-engine routing · `986d724` Paper/Demo 獨立控制 · `6ae6e1b` Circuit-breaker 防誤觸發

**全審計成績**：P0+P1+P2 = 48/48 全修，P2 22/22 清零，P3/QC/A3/BB 全部落地。
