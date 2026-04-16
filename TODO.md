# OpenClaw TODO — 工作計劃清單

**最後更新：2026-04-17**（**P0-6 INTENT-WRITE-GAP-1 RCA DONE** — 非 write path 斷裂，是 gate cascade 100% 拒絕：Live_Demo=cost_gate cold-start fail-closed + Demo=correlated exposure ~70%>=65% · **P0-7 REFRAMED** 為 P0-6 子問題 · P0-9 STABILITY-1 ✅ · P1-7 LEARNING-PIPELINE-DORMANT-1 🟡 · LIVE-GUARD-1 ✅）

**測試基準線**：Rust **engine lib 1351 (default) / 1348 (ort) + core 380 + e2e 35 + reconciler_e2e 19 + ort integration 5** · Python **2898 passed (5 skipped · 0 fail)** · ml_training **182 passed (10 skipped)**

> compact 後從此文件恢復工作狀態。第一個 `[ ]` 即為下一步起點。
> 條目分級：**P0 阻塞關鍵路徑** → **P1 當週活躍** → **P2 下週排期** → **P3 長期專項** → **P4 Backlog / Conditional**
> 歷史歸檔索引在文件末尾。已完成里程碑視角見 README.md 與 CLAUDE.md §三。

---

## 🎯 啟動時必做檢查

### 引擎健康三連（每 session 開頭）

```bash
# 1. 引擎存活 + canary 記錄 + 崩潰數
python3 helper_scripts/canary/engine_watchdog.py --data-dir /tmp/openclaw --stale-threshold 45 --grace-period 120 --status
systemctl --user status openclaw-watchdog --no-pager | head -5
grep -c "ENGINE_CRASH" /tmp/openclaw/watchdog.log 2>/dev/null || echo "0 crashes"

# 2. G-2 FundingArb 監控 daemon 進度（達 demo ≥20 fills 自動寫 audit）
cat /tmp/openclaw/g2_monitor.progress.json

# 3. git 狀態
git status && git log --oneline -5
```

如引擎掛了：`bash helper_scripts/restart_all.sh --engine-only --rebuild`。

---

## 🔴 P0 — 阻塞關鍵路徑（先清才能推 Live Gate）

### P0-0 · RECONCILER-BURST-FIX ✅ 2026-04-16（已歸檔）
已部署（engine PID 1340527, 21:08 local 啟動）+ 驗證 11+ min 0 auto-escalations。詳見歸檔 `docs/archive/2026-04-16--completed_todo_strategy_close_tag_edge_p3_dedup.md` §P0-0。

### P0-1 · G-2 FundingArb 驗證 🟡 daemon restarted option D config
**狀態**：daemon PID 1349961 已重啟，target 20→10 + 72h wall-clock deadline。baseline 2026-04-16 15:40:48 UTC 不變，progress 2/10，net −$0.46。P0-4 R1 已部署且驗證（DB 已出現 `strategy_close:grid_close_short`/`ma_reverse_cross` 等真實 tag）。
**定位**（重要）：**非主路徑** — Phase 5 edge 評估用其他 6 策略 fills 即足夠、LG-1 非阻塞、Live gate 不等 G-2。G-2 只卡 funding_arb 單策略 R-02 promotion 決定。
**診斷文件**：`docs/audits/2026-04-16--demo_zero_strategy_exit_audit.md` V2
**結束條件**：達 10 fills 或超 72h（2026-04-19 19:35 UTC）→ 自動寫 audit `docs/audits/2026-04-16--g2_funding_arb_clean_edge.md`
**進度檢視**：`cat /tmp/openclaw/g2_monitor.progress.json`（session 開頭三連的一部分）

### P0-2 · LG-1 Demo Trading 21d 觀察期 🕰️
**狀態**：PAPER-DISABLE-1（2026-04-16）後改口徑為 demo 觀察；起點待 P0-0 部署後 48h 無事故
**目的**：Live 前置條件；≥21d 穩定 demo 運行零事故（Bybit testnet 實際 API，驗證價值高於 paper 合成 fill）
**阻塞者**：非必要阻塞 — LG-1 覆蓋全策略穩定度，不限 funding_arb；P0-1 為 funding_arb 子集並行
**解鎖**：LG-2/3 shadow→blocking + provider pricing 正式化
**預估**：3 週連續觀察
**語義變更記錄**：原設計為「21d paper 零事故」。PAPER-DISABLE-1 後 paper 預設不 spawn（env gate `OPENCLAW_ENABLE_PAPER=1` 才啟用），LG-1 改以 demo 為觀察基準。若未來 Agent 階段（W22+ Strategist）重新啟用 paper 作探索環境，LG-1 可擴為「paper + demo 雙環境觀察」

### P0-3 · Phase 5 策略 Edge 2w 重評 📊
**狀態**：待乾淨 demo 累積 2 週（歸因已通：P0-4 R1 ✅ 2026-04-16）
**判斷**：
- 若 gross edge 翻正 → Phase 5 cost_gate 工作重啟（現有 JS / cost_gate / DL 機械已接線）
- 若 gross edge 仍負 → 策略本身需重做，轉向 EDGE-P3-1 接管（替換 shrunk_bps 為 per-trade 動態預測）或更激進的 EDGE-P2
**阻塞者**：~~P0-0 RECONCILER-BURST-FIX~~ ✅ 已部署。~~P0-1~~ 不必要 — G-2 只覆蓋 funding_arb 子集，Phase 5 整體 edge 用其他 6 策略 fills 已足夠。
**預估**：乾淨 demo 開跑（2026-04-16 21:08 local 起）後 2 週

### P0-5 · PHANTOM-2-FUP — ReduceToHalf one-shot guard 跨 tick 失效 ✅ 2026-04-16
**狀態**：修復完成，engine lib 1335 passed / 0 failed（+5 新單測）。待 `restart_all.sh --rebuild` 部署。
**方案**：**A+C 組合**（先 propose C-alone，QC 對抗性審查翻轉為 A+C — 因 `risk_gov.rs:617` 無自動降級路徑 + `position_risk_evaluator` 不認 sigma 離群，純 C 會讓 drawdown-driven Cautious 下已半倉 symbol 永久鎖定直到 operator 手動 de-escalate）
- **A**：`ft_reduced_symbols: HashSet<String>` → `HashMap<String, i64>`（symbol → last reduce ts_ms）+ 60s cooldown 封毫秒連發
- **C**：clear 條件 `< Defensive` → `== Normal`，僅完全回到 Normal 清空（快速 re-arm 新 episode）
- 新常數 `FT_REDUCE_COOLDOWN_MS = 60_000` 於 `on_tick_helpers.rs:23`（const 不熱載 — 60s 配合 governance Defensive 窗，足夠保守）
- 新 pure helper `ft_reduce_cooldown_expired()` 使 filter 可單測
**改動檔案**：
- `rust/openclaw_engine/src/tick_pipeline/mod.rs`（struct 欄位型別 + init）
- `rust/openclaw_engine/src/tick_pipeline/on_tick.rs:151-237`（clear 條件 + filter + insert）
- `rust/openclaw_engine/src/tick_pipeline/on_tick_helpers.rs`（+const + fn）
- `rust/openclaw_engine/src/tick_pipeline/tests.rs`（+5 新單測）
**新單測**：
- `test_ft_reduce_cooldown_expired_no_prior_entry`：首次永遠放行
- `test_ft_reduce_cooldown_blocks_within_window`：+0ms / +59999ms 一律擋（複現 1.3s/9 次 cascade）
- `test_ft_reduce_cooldown_re_arms_after_window`：+60000ms 解鎖 + 跨 symbol 獨立
- `test_ft_reduce_clear_only_on_normal`：Cautious/Reduced/Defensive 絕不清空
- `test_ft_reduce_cooldown_map_stamps_once_per_window`：真實 TickPipeline + paper_state 整合
**驗收（部署後觀察）**：
- `grep "FAST_TRACK ReduceToHalf" /tmp/openclaw/engine.log` 同 symbol 連續事件時間戳間隔 ≥60s（不再毫秒連發）
- `risk_close:fast_track_reduce_half` 24h 計數 < 50（vs 修復前 335/2.6h，預期降 >80%）
**RCA**：`docs/references/2026-04-16--phantom2_fup_reduce_to_half_cascade_rca.md`（歷史記錄，已落實）

### P0-8 · LIVE-GUARD-1 — Rust 端 Mainnet 三重硬鎖回補 ✅ 2026-04-16
**狀態**：修復完成，engine lib 1342 passed / 0 failed（+7 新單測）。E2 對抗性審查 5/5 APPROVED。不需 rebuild 部署（Rust 側變更 — 需走 `restart_all.sh --rebuild`，但**生效條件是 env=Mainnet**，當前 LiveDemo 流量零影響）。
**根因**：SEC-17（2026-04-10 commit 25b5d73）移除 `OPENCLAW_ALLOW_MAINNET=1` Rust guard 後未補替代 fail-safe；憑證來源同時從「slot 文件唯一」擴展為「env var > slot」雙路徑，導致任何能設環境變數的進程都能繞過 secret slot。門控完全外移 Python → Rust 長跑 × Python 重啟脆弱的對稱性崩潰。
**方案**：**三重加固 Gate #1/#2/#3**（env 路徑，非 operator-signed file — CLAUDE.md §三建議選項；後者 HMAC+mtime freshness 屬 over-engineer）
- **Gate #1**: `env=Mainnet` 需 `OPENCLAW_ALLOW_MAINNET=1`（exact "1"，拒絕 "0"/"true"/"yes"/"1 "），缺即 `BybitApiError::Business`
- **Gate #2**: `env=Mainnet` 時禁用 `BYBIT_API_KEY`/`BYBIT_API_SECRET` env var fallback，只允許 param → slot file（封閉 env 繞 slot 的攻擊面）
- **Gate #3**: `env=Mainnet` 時憑證空 → 構造時 `Err` fail-closed（之前只 `warn!` + client 建立 + 簽名階段 401，污染重試循環）
- Demo/Testnet/LiveDemo 不受影響（向後兼容，當前 live pipeline 走 LiveDemo endpoint 零回歸）
**改動檔案**：
- `rust/openclaw_engine/src/bybit_rest_client.rs:386-497`（new() 重寫 + 三重 gate + bilingual docstring）
- 同檔 tests mod +7 新單測（LIVE_GUARD_ENV_LOCK Mutex + EnvSnapshot RAII）
**新單測**：
- `test_mainnet_blocked_without_allow_env` — 未設 env → Err
- `test_mainnet_blocked_with_wrong_allow_value` — "0"/"true"/"yes"/"1 "/" 1" 全拒絕
- `test_mainnet_blocked_without_credentials` — allow=1 無 creds → Err
- `test_mainnet_ignores_env_var_credentials` — BYBIT_API_KEY env 有值、slot 無 → 仍 Err（驗 Gate #2）
- `test_mainnet_accepts_explicit_param_creds` — allow=1 + param 傳入 → OK
- `test_demo_env_var_creds_still_work` — 回歸守衛：Demo + env var 不壞
- `test_testnet_no_guard_check` — 回歸守衛：Testnet 不需 allow env
**E2 審查結論**（5/5 APPROVED）：無 struct literal 繞過、startup.rs:432 + pyo3/client.rs:93 Err 硬傳播、無獨立 HTTP client 可打 mainnet、WS 靠 REST 憑證無獨立 guard 需求、repo grep 無既存 OPENCLAW_ALLOW_MAINNET 誤用值。
**部署**：下次 `restart_all.sh --rebuild` 附帶生效。當前 LiveDemo→Demo endpoint 零影響；真實 Mainnet 僅在 operator 顯式配置 `trading_mode=Live` + secret slot + env var 三項俱全時可用（門控從 1 項 Rust-verifiable 升為 3 項）。

### P0-6 · INTENT-WRITE-GAP-1 — live/live_demo `trading.intents` = 0 根因已確認 🟡 RCA DONE 2026-04-17
**原描述**：`trading.risk_verdicts` 大量 Approved 但 `trading.intents` live/live_demo/demo = 0。
**根因**（2026-04-17 確認，非 DEDUP-PY-RUST write path 斷裂）：**Rust gate cascade 在 Guardian 之後、intent 持久化之前拒絕 100% intents**。代碼路徑正確（`persist_intent` 只在 `gate.approved=true` 時觸發），問題是 **沒有任何 intent 最終被 approved**。

| 管線 | 阻擋 Gate | 根因 | 診斷證據 |
|---|---|---|---|
| **Live_Demo** | Gate 3 `cost_gate_live` | `edge_estimates.json = {}` → `get_cell()=None` → cold-start fail-closed（根原則 #5） | 630k decision_features = intents 通過所有 pre-cost-gate 檢查；engine.log: `cost_gate(JS-live): no edge estimate — fail-closed` |
| **Demo** | Gate 2.7 `check_order_allowed` | Bybit demo 帳戶 seeded positions → correlated exposure ~70% >= limit 65% | 0 decision_features = intents 在 evaluate_predictor_gate 之前被擋；engine.log: `risk_gate: correlated exposure 69-70% >= limit 65%` |
| **Demo** (次要) | Gate 2 Guardian | Seeded positions 觸發 `direction_conflict: opposite position exists` | 17.8k Rejected verdicts（`openclaw_core/guardian.rs:122`） |

**死循環結構**（與 P0-7 交織）：
- Live_Demo：`cost_gate_live` fail-closed → 0 fills → 0 edge data → `edge_estimates.json` 永遠是 `{}` → `cost_gate_live` 永遠 fail-closed
- Demo：correlated exposure 超限 → 0 new opens → 0 fills → positions 不關（P0-7 order submit gap）→ exposure 不降 → 永遠超限

**診斷方法**：`on_tick.rs` 添加 P0-6 DIAG `tracing::warn!` 在 `!gate.approved` 時輸出 `rejected_reason`（rate-limited: 前 50 條 + 每 10000 條一次）。此前 `rejected_reason` 被計算但從未 persist/log — 設計盲區。

**下一步**（修復方案 TBD）：
- [ ] **Live_Demo 死循環打破**：方案 A — 用 LiveDemo→Validation profile mapping（`cost_gate_moderate` cold-start 允許）；方案 B — bootstrap edge 估計（需學習管線 P1-7）
- [ ] **Demo 死循環打破**：方案 A — 清理 orphan positions（手動或自動）；方案 B — 臨時調高 `correlated_exposure_max_pct`；方案 C — 修 P0-7 使 Close actions 生效
- [ ] **永久修復**：`rejected_reason` 應 persist 到 DB（新欄位或復用 `reason`），而非只在 struct 裡丟棄
- [ ] 移除 `on_tick.rs` P0-6 DIAG 代碼（根因確認後）

**注意**：`correlated_exposure_max_pct` config TOML = 60.0 但 runtime 為 65.0（GUI hot-reload 修改過）

**阻塞**：Live gate（需真實 fill data → edge 估計 → cost gate 通過；P0-7 共同阻塞）

### P0-7 · ORDER-SUBMIT-GAP-1 — live/live_demo Approved verdict 沒觸發真實下單 🟡 REFRAMED 2026-04-17
**原描述**：570k Approved verdicts + 0 fills = order submit path 被跳過。
**P0-6 RCA 後更正**：**不存在獨立的 order-submit gap**。0 fills 的根因是 P0-6 gate cascade 拒絕 100% intents，`gate.approved` 從未為 true，所以 `on_tick.rs:690-733` 的 order dispatch 代碼從未被進入。order submit path 本身（OrderDispatchRequest → exchange REST）未壞，但從未被觸發。
**與 P0-6 死循環**：Demo positions 不關 → correlated exposure 超限 → 0 new opens 是因為 **Demo pipeline 無法自行 close 這些 seeded positions**。Close 動作走 StrategyAction::Close 分支（on_tick.rs），理論上不受 open gate cascade 限制，但需要策略主動 emit Close。如果 seeded positions 不屬於任何活躍策略（orphan positions），不會有策略 emit Close → 死循環。
**下一步**：
  - [ ] 確認 seeded positions 是否為 orphan（不屬於活躍策略）→ 若是，方案 = 手動清理或引擎 startup orphan reconciler
  - [ ] P0-6 修復後（Live_Demo cost gate / Demo correlated exposure）此 issue 自動消失
**阻塞**：Live gate（已與 P0-6 合併為同一阻塞點）

### P0-10 · SCANNER-GATE — orphan_handler death loop fix ✅ 2026-04-17
**原問題**：策略開倉 → scanner 輪替移除 symbol → orphan_handler A4 強平 → 策略再開 → 死循環。BASEDUSDT 等 20+ 個 symbol 受影響（228 筆 `ipc_close_symbol` fills）。
**根因**：A4 `HardSafetyNotInUniverse` 把「掃描器輪替掉的持倉」當作 orphan 強平，但引擎會在下一 tick 重新開倉 → 無限循環。同時 REST→WS 時間差（FUP race condition）使引擎自家剛下的單也被誤判為 orphan。
**修復（三部分）**：
1. **SCANNER-GATE**：tick_pipeline 新增 `symbol_registry` 字段 + `set_symbol_registry()` setter，在 `on_tick.rs` strategy Open dispatch 前檢查 `reg.is_active(symbol)`，非活躍 symbol 阻止開新倉
2. **FUP-RACE**：`paper_state.rs` 新增 `proactive_mirror_insert()`，exchange OrderDispatchRequest 發送後立即寫 mirror，彌合 REST→WS 空窗
3. **A4 移除**：`orphan_handler.rs` Stage A4 代碼移除（enum 變體保留 DB backward compat），orphan 定義改為純「重啟後遺留」，不含 scanner 輪替
**改動檔案**：`tick_pipeline/mod.rs`（+field +setter +init）· `on_tick.rs`（+scanner gate + proactive mirror）· `paper_state.rs`（+proactive_mirror_insert）· `orphan_handler.rs`（-A4 +updated tests +doc）· `event_consumer/mod.rs`（+registry wiring）
**測試**：engine lib 1351 passed / 0 failed（含 17 orphan_handler 測試全綠）· core 380 passed
**部署**：待 `restart_all.sh --rebuild`

### P0-9 · STABILITY-1 — 2026-04-16 停電事件 RCA 完成 ✅（非代碼 bug，單次基礎設施事件）
**原敘述**：當日 9h 引擎 5 次崩潰被誤判為「代碼穩定性 P0-CRITICAL 阻塞 + 21d 時鐘必須重置」。
**RCA 結論（2026-04-16 深夜，operator 確認）**：**全部 30 次 crash（深入撈後實為 30 非 5）均為單次斷電造成的網路基礎設施事件，非引擎代碼 bug。** 21d demo 時鐘**不重置**。

**證據鏈**：
- 時區：operator 筆電 CEST (UTC+2) — UTC→local 加 2h
- operator 報告：**2026-04-16 10:00-16:00 local 停電 ~6h**，造成斷網
- **第一次 crash 10:45 local**（08:45 UTC）= 停電後 45min（電池 + 路由器失電）
- **watchdog 完全靜默 13:16-18:03 local**（4h 47min blackout）= 筆電電池耗盡或硬關機期間
- **post-gap 首條** `snapshot age=17313.5s`（4.81h 陳舊）= 硬斷電復電鐵證
- **engine log（engine-1776330656.log 09:10 UTC 啟動）**所有錯誤簽名一致：
  - `HTTP transport error: error sending request for url (https://api-demo.bybit.com/...)`
  - `IO error: failed to lookup address information: Temporary failure in name resolution`（DNS 失敗）
  - REST / WS private / WS public 全部連不上 Bybit
- 非代碼 bug 的證據：**零 panic、零 assertion、零 rust backtrace**；全部為 DNS/transport error 合理 fail-closed 行為
- 斷網恢復後（18:03 local 之後）網路還不穩又滾了幾輪，再之後當前 PID 1364222 於 22:16 local 穩定啟動

**對觀察期時鐘的判定**：
- **P0-2 LG-1 21d demo 時鐘不重置**：基礎設施事件 ≠ 引擎不穩定。若每次停電都重置時鐘，21d 永遠達不到
- **P0-3 Phase 5 edge 2w 重評**：crash 時段（10:45-18:03 local）fills 樣本應排除（自然也沒有 fills，因為引擎連不上 Bybit）

**Nice-to-have（不阻塞）**：
- `engine_watchdog` 可加 network-loss detection（DNS failure 連續 N 次分類為 `network_outage`，不計入 stability strike）
- 不急，等有空再做

**阻塞**：無（已解除，非 Live 前置）
**歸檔**：本 audit 結論取代 §三「9h 5 crash / 21d 時鐘未啟動」敘述，CLAUDE.md §三 + §十 + §十一 同步更新

**關鍵路徑**:`~~P0-0 reconciler burst fix~~ ✅ → ~~restart_all --rebuild 部署~~ ✅ → ~~P0-9 STABILITY-1 引擎崩潰 RCA~~ ✅（停電 infra 事件，非 code bug）→ P0-6/P0-7 查清 intent/order 寫入斷點 → P0-3 Phase 5 edge 2w 評估 + P0-2 LG-1 21d demo → **P1-7 LEARNING-PIPELINE-DORMANT-1** → LG-4/5 → Live`(P0-1 G-2 並行驗證 funding_arb 子集,不在主路徑;~~P0-5 PHANTOM-2-FUP~~ ✅ 待 `--rebuild` 部署即生效;~~P0-8 LIVE-GUARD-1~~ ✅ Rust 端 Mainnet 三重硬鎖回補,解除 CLAUDE.md §三 LIVE-GUARD-1 P0-CRITICAL 阻塞)
**最早 Live 日期**:回到 **W24 末（～2026-05-23）** — P0-9 停電事件 RCA 後不延後

---

## 🟡 P1 — W22 當週活躍

> P1-1 EDGE-P3-1 Phase B #3 ONNX loader ✅ 2026-04-16 · P1-2 Step 7b Python route + flag flip ✅ 2026-04-16 — 已歸檔（索引見文件末尾）。

### P1-3 · EDGE-P3-1 Step 7c Python consumer ✅ 2026-04-16（已歸檔）
三條讀取路由骨架 + 15 新單元測試。詳見歸檔 `docs/archive/2026-04-16--completed_todo_strategy_close_tag_edge_p3_dedup.md` §P1-3。

### P1-4 · 在真 ETL 資料跑首個 ONNX export
**狀態**：`learning.decision_features` 於 Step 7a 後開始採集；等足夠樣本（≥100k rows per strategy 推薦）
**工作內容**：`run_training_pipeline.py --strategy <name>` → 產 `models/<engine>/<strategy>_vYYYYMMDD.onnx` + symlink
**解鎖**：整個 EDGE-P3-1 Stage 2 shadow mode（P1-1/P1-2 已解鎖 ✅，等此產出首個 artifact 後執行 `ReloadEdgePredictor` IPC 載入）

### P1-5 · DEMO-REBOOT-PNL-RESET-1 — 重啟清洗歷史 drawdown audit 🟡 NEW 2026-04-16
**發現**：實現性審查發現 `/tmp/openclaw/demo_state.json` 本輪重啟後 `initial_balance == peak_balance == current_balance (747.56)`、`total_realized_pnl=72.68`；但 `trading.risk_verdicts` 24h 內仍有 **91,798** 條 `drawdown_breach: 92.2% > 25.0%`（最後 2026-04-16 10:57 UTC+2 = 08:57 UTC）證明**本輪之前 demo 帳戶曾達 92% drawdown，觸發 9 萬+ 次 P0 硬邊界 reject**。
**問題**：本輪啟動時 state file 被重 seed 為 current balance，歷史 drawdown 在 engine in-memory 視角被清掉。是設計還是 bug？
- 若設計：審計上 drawdown 監控跨 session 斷鏈（只有 DB 能還原）
- 若 bug：應從 bybit_sync 或 session store 正確恢復 peak_balance 以維持累積 drawdown 視角
**下一步**：查 `event_consumer/paper_state_restore.rs` + `demo_state.json` 寫入路徑
**影響**：Phase 5 edge 重評期（P0-3）drawdown 真實軌跡可能被遮蔽；21d demo 穩定性判斷基準被影響

### P1-6 · DEMO-BYBIT-SYNC-ORPHAN-1 — bybit_sync 倉位策略動不了 🟡 NEW 2026-04-16
**發現**：`demo_state.json.positions` 6 個全部 `owner_strategy="bybit_sync"`（DOTUSDT / NEARUSDT / BLESSUSDT / ENAUSDT / AAVEUSDT / BTCUSDT）
**問題**：這些倉位是從 Bybit demo account 同步下載（之前 session 遺留），**不是本輪策略開的**。ORPHAN-ADOPT-1 Phase 1/2A 完成後，bybit_sync orphan 應該能被策略 adopt 並 close — 但實測 1h43min demo 沒新 intent 意味著這 6 個仍被孤立。
**下一步**：
  1. 查 orphan adoption 日誌 `grep ORPHAN /tmp/openclaw/engine.log`
  2. 確認 Phase 2A 的 adopt logic 是否會處理 bybit_sync 來源（相對於 external operator 來源）
  3. 若不會：ORPHAN-ADOPT-1 Phase 2B 或獨立 P1 補 bybit_sync 路徑
**影響**：21d demo 觀察期內這些倉位若 drawdown，策略層無法反應（只能靠 Guardian ReduceToHalf / fast_track close）

### P1-7 · LEARNING-PIPELINE-DORMANT-1 — 半殼學習管線（數據累積 ✅、訓練/edge/Teacher ❌ 全 dormant）🟡 NEW 2026-04-16 audit
**發現**：2026-04-16 audit 原本假設學習管線空殼，深挖後發現真相比想像複雜——是「**半殼**」：
- **數據累積層 ✅**：`learning.decision_features` 1,650,330 rows（live 1,073,468 + live_demo 576,062 + demo 800）；`trading.risk_verdicts` 24h 1.54M rows
- **edge 估計層 ❌**：`settings/edge_estimates.json` = `{}` 3 bytes，從未被寫過
- **experiment_ledger 異常**：`experiment_ledger_snapshot.json` top-level 是 `list` 非 `dict`（結構與 Python 期望不符）
- **21 個 learning schema 表**存在但無消費者：`bayesian_posteriors / linucb_state / linucb_state_archive / linucb_migrations / teacher_directives / directive_executions / james_stein_estimates / model_registry / promotion_pipeline / rl_transitions / scorer_training_features / symbol_clusters / pattern_insights / cpcv_results / ai_budget_config / ai_usage_log / decision_features / decision_shadow_fills / foundation_model_features / ml_parameter_suggestions / promotion_pipeline`
- **EDGE-P3-1 Phase B #3 ONNX loader** 宣稱 ✅ 部署（2026-04-16）但 **0 artifact 產出**；ort 2.0 backend + capability probe 載入端就緒、訓練端空轉
**真正的 gap**：
  - 沒有訓練 job consume `decision_features` → 不產 ONNX
  - 沒有 edge 估計 job consume `risk_verdicts + fills` → 不寫 `edge_estimates.json`
  - Teacher directive pipeline（G-7 at W23）未啟 → `teacher_directives` 空
  - LinUCB / JS estimator / Bayesian posterior updater 等全休眠
**下一步**：
  1. 定位 EDGE-P3-1 Step 7a ETL（應該寫 `decision_features` 的組件）→ 已在跑 ✅
  2. 找 run_training_pipeline.py（P1-4）→ 跑首個 ONNX artifact
  3. 啟用 JS edge estimator（G-6，原排 P0-2 後）
  4. G-10 Calibration + G-7 Teacher（W23）
**阻塞**：不阻 Live（Live 用 demo fills 做 edge 估計路徑另案），但阻 Phase 5 edge 收斂 + Stage 2 shadow mode 起步
**與 P1-4 關係**：P1-4「跑首個 ONNX」是本項子任務；本項是框架性 audit finding（數據到訓練到載入三段，只有載入端就緒）

### AI 治理層補強
- [ ] **G-7** ClaudeTeacher 正式啟用（W23）
  - 現況：`consumer_loop.rs` `enabled = false`；learning_store "no consumer"
  - 前置：E3 審查 PASS ✅ + G-3 IPC 認證 ✅ + 21d paper 穩定（P0-2）
- [ ] **G-10** Calibration.py 整合（W23）
  - 現況：`ml_training/calibration.py` 骨架，`apply_calibration` 缺整合入口
  - 目標：isotonic → `run_training_pipeline.py` + ECE < 0.05 門檻
  - 前置：fills 累積 + 2-11 actual training

### Live Gate
- [ ] **LG-2** H0 Gate blocking 驗證（shadow → blocking，W23）
- [ ] **LG-3** provider pricing table 正式綁定（W23）
- [ ] **LG-4** M 章 Supervised Live Gate（W24）
- [ ] **LG-5** N 章 Constrained Autonomous Live（W24）
- [ ] **G-4 / SEC-21** Cookie `secure=True`（HTTPS 部署後，W24）

### QoL
- [ ] **QoL-2** Demo AI cost 無追蹤 — `tab-demo.html` 硬編碼 `'N/A'`，後端無 per-engine AI 調用成本歸因（依賴 G-1 H1-H5 接通）

### Audit 衍生架構對稱性債
- [ ] **LEARNING-COCKPIT-NO-IPC-1** 🟢 NEW 2026-04-16 audit — Learning Cockpit 走 Python state_store 而非 Rust IPC snapshot
  - **發現**：`tab-learning.html` 8 個端點（`/api/v1/learning/{overview,hypotheses,feed,experiments,net-pnl,review,review-queue,auto/*}`）全部在 `legacy_routes.py:645-840+` 由 `_base.get_latest_snapshot()["learning_state"]` 驅動，**無一處 `ipc_state_reader.get_rust_reader()` 調用**
  - **對比**：paper/live/risk/strategy_read/reconciliation 路由已全部走 Rust IPC snapshot（`ipc_state_reader`）；只有 learning 還是 Python state_compiler 派生
  - **非 bug，是設計債**：learning_state 本質是 `experiment_ledger + learning_records` 等 Python-owned 資產的派生視圖（Rust 不擁有這些資產，僅透過 DB 寫 decision_features/risk_verdicts 等原始事件）
  - **與 P1-7 疊加**：Learning Cockpit 顯示的 learning_state 是「Python state_compiler 讀 experiment_ledger_snapshot.json + 學習 DB」的結果；P1-7 確認學習管線下游 dormant → Cockpit 顯示的是**半殼數據**（DB 有 1.65M decision_features，GUI 端見不到 edge estimates / ONNX artifacts / Teacher 指令）
  - **修復方向**（等 G-7/G-10 整合後再議）：要麼把 learning_state 產出移入 Rust（跟 3E-ARCH 對稱），要麼正式承認 Python 擁有 learning 平面（與「Rust 為唯一寫入權威」原則劃清邊界，明記 `learning.*` schema 由 Python 寫）
  - **不阻 Live**（學習平面與 Live 平面隔離，原則 #7）

---

## 🔵 P3 — W25+ 長期專項

### AI Agent 全 5 鏈路（G-1 / R-06）
- [ ] **G-1 / R-06 全 5 agent** — 當前 Conductor 仍 stub；其他 4 agent 已 real（R-06-v2 ✅）
- [ ] **FIX-01** H1-H5 AI Agent 接入（= R-06 完整）
- [ ] **FIX-02** Decision Lease Rust 接入（與 FIX-01 一起）
- [ ] **FIX-12** CSP nonce 遷移（長期）
- [ ] **FUP-8 Phase 2 殘留** — OrderIntent 加 `edge / funding_rate / basis / regime` 欄位（等 G-1 Strategist 串線）
  - Paper sentinel 根治已完，此項僅剩欄位擴充

### ORPHAN-ADOPT-1 Phase 2B
- [ ] **Phase 2B** Strategist 判斷同向信號升級
  - 把 Stage B2 從「正 edge」升級為「Strategist 現時 `would_take(symbol, side)`」
  - `KNOWN_STRATEGY_NAMES` + `EdgeEstimates` probe 降為 fast-path，Strategist 為 slow-path 最終仲裁
  - 前置：G-1 R-02 Strategist agent 在線

### Phase 5 補強（非阻塞，等 P0-3 判斷後定）
- [ ] **5-04~07** DL-1 Symbol Embedding + DL-2 Regime LSTM Shadow
- [ ] **5-08~09** JS + Scorer 整合 + correlation_pairs
- [ ] **5-10~13** E2 + E4 + QC + E5

### EDGE P2（架構層重工）
- [ ] **EDGE-P2-2** OI + Liquidation 信號源 — 給 `bb_breakout` 加領先信號（Bybit WS `tickers` OI + `liquidation` stream）
- [ ] **EDGE-P2-3** Maker order 支持 — fee 5.5 bps → ~1 bps/side（post-only limit；改 IntentProcessor + order_manager + exchange execution layer，根本性改變盈利方程式）

---

## ⚪ P4 — Backlog / Conditional

### WP-F GUI 殘留
- [ ] WP-F/O-xx / AH-08~11（詳 `docs/audits/2026-04-06--consolidated_remediation_report.md` §10.1）

### WP-E4 測試覆蓋
- [ ] T-P2-9 PyO3 bridge tests · T-P2-10 panic-path · T-P2-11 並發
- [ ] T-Q3/Q4/Q7/Q8 覆蓋品質
- [ ] T-I1~I4 tarpaulin / CI 門禁 / 文檔
- [ ] WP-E4/T-P1-1 殘餘 event_consumer 完整事件循環整合測試

### WP-E5 大文件
- [ ] `tick_pipeline.rs` 2117 行 — 留專屬 session

### WP-I 文檔衛生
- [ ] R4-NAME-1 / R4-MEM-1 / R4-REF-ST-1

### 🧹 PAPER-DISABLE-1 · Paper 管線預設關閉 ✅ 2026-04-16（已歸檔）
已部署（engine PID 1340527 後生效，`OPENCLAW_ENABLE_PAPER=1` 可重開）。詳見歸檔 `docs/archive/2026-04-16--completed_todo_strategy_close_tag_edge_p3_dedup.md` §PAPER-DISABLE-1。

### 🧹 IP-DEDUP-1 · IntentProcessor 同幣種重發去抖 🆕 2026-04-16
**背景**：Problem 2 診斷（見 `project_engine_mode_tag_live_demo.md` + `project_phase5_promotion_edge_crisis.md`）揭露：cost_gate 拒絕後無 position → 策略每 tick 看到「沒倉位」狀態重發同向 intent（ORDIUSDT 14min 內 8439 筆）。每筆重發都觸發 `evaluate_predictor_gate` → emit DF snapshot → 放大 `learning.decision_features` 寫入量 + 無謂 cost_gate CPU。
**症狀**：Live+LiveDemo 43k DF rows vs Demo 42 rows，98%+ 是殭屍重發（同 symbol+side+strategy 秒級重複）。
**建議方案**：
- IntentProcessor 加 `last_rejected_intent: HashMap<(symbol, is_long, strategy), (ts_ms, reason)>`
- 同 key 在 N 秒（建議 60s，可配置）內重發 → 早退，不計 gate、不 emit DF、寫 `dedup_skipped` 計數器
- 只去抖**被拒絕**的 intent；被批准的 intent 走正常路徑（避免吞掉真正想連續開倉的策略信號）
- 配置項：`risk.intent_dedup.enabled=true` + `dedup_window_secs=60`
**Why**：
- 減 DF 寫入 ≥95%，ML 訓練資料訊噪比提升
- 減 cost_gate CPU / DB IO（Phase 5 負 edge 期間重發主要成本來源）
- 留 counter 讓 GUI 看到「被去抖的 intent 數」保持透明度
- 不修復 Phase 5 edge crisis 本身（那是 G-SR-1 / Strategist agent 的工作），純優化
**Why not 現在做**：Phase 5 策略重做（P0-3 判決後）可能讓負 edge 消失 → 重發率自然下降 → 本優化效益降低。先等 P0-3。
**前置**：P0-3 Phase 5 Edge 2w 重評完成；若 edge 仍負且策略重做時程延長，則提前啟動。
**工作量**：~1d（含 config 欄位、E1/E2/E4、counter GUI 接線）
**驗收**：
- 啟用後同幣種+方向+策略 60s 內重發被早退，`intent_dedup_skipped` counter 遞增
- DF 每日行數 ≥95% 下降（特別是 Live+LiveDemo engine_mode）
- 被去抖不影響**首筆**intent 的 gate 評估 + 仍寫 DF（保留探索樣本）
- 同 symbol 但不同 side（反手）/不同策略 → 不觸發去抖
**接手指南**：
- 相關程式：`rust/openclaw_engine/src/intent_processor/mod.rs`（`evaluate_predictor_gate` 上游）
- 類似機制：`governor_cooldown` 的 24h 冷卻（`mode_state.rs`）、`last_ai_call_time_ms`（cost gate）
- Counter 可復用 `IntentProcessor::stats` 結構

### 🧹 WATCHDOG-DNS-CLASSIFY-1 · Watchdog 區分 DNS/網路斷線 vs 引擎崩潰 🆕 2026-04-16 audit
**背景**：P0-9 STABILITY-1 RCA 揭露：2026-04-16 當日 30 次 `ENGINE_CRASH` 全部為 operator 筆電 10:00-16:00 local **停電斷網**期間的 REST/WS 連線失敗（`Temporary failure in name resolution` + HTTP transport error），**非引擎 bug**。但 watchdog 無從區分「引擎真的 panic」與「外部網路斷線導致 fail-closed」，兩者都計入 `ENGINE_CRASH` strike，並觸發 Python fallback。
**症狀**：
- 停電 45min 後（engine 資源耗盡或 router 失電）第一次 strike
- 13:16-18:03 watchdog 完全靜默（硬斷電）
- 復電後 post-gap snapshot age=17313.5s (4.81h) → fresh strike
- engine.log 零 panic / 零 assertion / 零 rust backtrace — 明顯是外部事件
**建議方案**：
- `engine_watchdog.py` 加 crash log 分類：
  - 讀 engine.log 最後 N 行（N=20）
  - 若連續 ≥5 條 `Temporary failure in name resolution` / `HTTP transport error` / `connection refused` → 分類 `network_outage`，**不計** stability strike，不觸發 Python fallback
  - 若有 `panic` / `assertion failed` / `rust backtrace` → 分類 `engine_crash`，正常 strike
  - 其他（timeout / unknown）→ `unknown`，記警告但寬鬆計分
- 新增 counter：`network_outage_events` / `true_crash_events` 分別統計
- `/tmp/openclaw/watchdog.log` 格式擴充：`event=ENGINE_CRASH type=network_outage|engine_crash|unknown`
**Why**：
- P0-2 LG-1 21d demo 穩定期期間若再停電/斷網，不應誤判為引擎不穩而重置時鐘
- 未來任何基礎設施事件（ISP 故障、DNS 污染、NAS 掉線）都會重現本次誤判
- 不改 fail-closed 語義 — 引擎仍然 shutdown，只是 watchdog 不當「真 crash」處理
**Why not P0/P1**：
- 已確認 2026-04-16 事件非 code bug，不阻 21d 時鐘
- 操作上：operator 已知此類事件發生時需要人工覆核，watchdog 分類只是減輕覆核負擔
- 發生頻率低（家用斷電年均 ≤3 次）
**前置**：無
**工作量**：~2h（純 Python，不動 Rust；watchdog 即時可測）
**驗收**：
- 模擬連續 10 次 DNS failure 日誌 → watchdog 歸類 `network_outage`，strike 不遞增
- 注入 `panic!` 測試 → watchdog 歸類 `engine_crash`，strike 正常遞增
- `/tmp/openclaw/watchdog.log` 可見 type 欄位

### 前 phase 殘留
- [ ] **2-11** actual training（等 fills 累積）
- [ ] **ort crate** activation（首個 ONNX 模型訓練後 — 現由 P1-4 推進）
- [ ] **4-06** LinUCB live warm-start deployment（script 交付，等首次 v1→v2 遷移）
- [ ] **OC-4** MCP PostgreSQL 自然語言查詢
- [ ] **G-6** Edge estimates 重訓（JS 滾動；P0-2 後）
- [ ] **G-8** cost_gate 可信度評估（依賴 EDGE-P3-1 Stage 2 或 G-6）

### Phase 4-Conditional（觸發後才做）
- [ ] 4-1 PairsTrading（需 3 月協整）· 4-2 Beta Hedging · 4-3 Kalman · 4-5 Mac Studio 遷移 · 4-10 Jump detection

---

## 🗓️ 排期總覽

| 週次 | 日期 | 主要焦點 | 狀態 |
|------|------|---------|------|
| W19-W21 | 04-14~05-02 | 基礎設施 / 安全 / Phase 6 / 3E-ARCH / Audit | ✅ 歸檔 |
| W22 | 05-05~09 | **ENGINE-HEAL FUP-1/2/3 + FIX-PHASE1 · FA-PHANTOM-2 · EDGE-P3-1 Phase A/B + Step 7 · ML-MIT #26 Lane A · GUI fills 鏈** | ✅ 歸檔 |
| W22 末 | 2026-04-16 | P0-4 R1 · P0-0 reconciler grace · PAPER-DISABLE-1 · G-2 daemon option D · DEDUP-PY-RUST · Phase B #3 ONNX loader | ✅ 歸檔 |
| W23 | 05-12~16 | P0-2 LG-1 21d demo 觀察起點 · G-7 Teacher · G-10 Calibration · LG-2/3 | ⬜ |
| W24 | 05-19~23 | LG-4/5 Live Gate · SEC-21 · QoL-2 | ⬜ |
| W25+ | 05-26+ | EDGE-P3-1 產線化 · Phase 5 補強或重做 · G-1 R-06 全 5 agent | ⬜ |

---

## 🔍 Gap 排期索引（2026-04-10 審計，10 項全錄）

| Gap | 描述 | 排期週 | 狀態 |
|-----|------|--------|------|
| G-1 | AI Agent 5 stub | W22(R-02) ✅ · W25+(R-06 full) | 🟡 |
| G-2 | FundingArb.on_tick() | W22 | 🟡 驗證中（daemon active）|
| G-3 | IPC socket 無認證 | W19 | ✅ |
| G-4 | Cookie secure=False | W24 | ⬜ |
| G-5 | API Rate Limiting | W19 | ✅ |
| G-6 | ML edge 噪音數據 | LG-1 觀察期後 | ⬜ |
| G-7 | ClaudeTeacher disabled | W23 | ⬜ |
| G-8 | cost_gate 可信度低 | EDGE-P3-1 後 | ⬜ |
| G-9 | HMAC dead import | W20 | ✅ |
| G-10 | Calibration.py 骨架 | W23 | ⬜ |

---

## 📚 已完成歸檔索引

- **2026-04-16 STRATEGY-CLOSE-TAG-FIX + EDGE-P3-1 Phase B #3 + DEDUP-PY-RUST**：`docs/archive/2026-04-16--completed_todo_strategy_close_tag_edge_p3_dedup.md` ← **本次整理新增**
- **2026-04-15 W22 ENGINE-HEAL + EDGE-P3-1 + GUI Fills**：`docs/archive/2026-04-15--completed_todo_w22_engine_heal_edge_p3.md`
- **2026-04-14 Phantom-Heal + Engine Self-Healing + EDGE**：`docs/archive/2026-04-14--completed_todo_w22_phantom_heal.md`
- **2026-04-12 全程序鏈審計**：`docs/archive/2026-04-12--completed_todo_full_program_audit.md`
- **W19 + W20 + Phase 6 + 3E-E2 Fix Rounds A-G**：`docs/archive/2026-04-11--completed_todo_w19_w20_phase6.md`
- **3E-ARCH 三引擎並行**：`docs/archive/2026-04-11--completed_todo_3e_arch.md`
- **Live GUI P0~P6 + DEAD-PY-1/2 + 1C-4 收尾**：`docs/archive/2026-04-10--completed_todo_live_gui_dead_py.md`
- **Phase 5 P0 promotion + WIRE chain**：commits `5d7d673` → `0e848fa` → `638afa3` → `563d54a` → `5e760be`
- **ARCH-RC1 Session 1A → 1C-4 WRAP**：`docs/archive/2026-04-08--arch_rc1_1c_history_archive.md` + `docs/archive/2026-04-08--main_docs_1c3_1c4_narrative.md`
- **Phase 4 (4-00 ~ 4-21 + 4.1)**：`docs/audits/2026-04-07--phase4_final_signoff_audit.md`
- **Session 11 之前**：`docs/archive/2026-04-06--completed_todo_archive_l3_phases.md`
- **Phase 0/1/2/3 + Rust migration**：`docs/archive/2026-04-04--completed_todo_archive_phase0123_rust.md`
- **已知問題清單**：`docs/KNOWN_ISSUES.md`
- **Bybit API 字典手冊**：`docs/references/2026-04-04--bybit_api_reference.md`

---

## ⚙️ 工作流程速查

```
E1/E1a 並行（最多 5 路）→ E2 審查（強制）→ E4 回歸（強制）→ PM 確認 → commit
角色定義詳見 CLAUDE.md §八
```

**Bybit API 開發必查**：先讀 `docs/references/2026-04-04--bybit_api_reference.md`。

**風控參數修改強制原則**：所有風控/止損/cost-gate/regime 參數必須透過 IPC `patch_risk_config` 單一通道更新。

**腳本速查**（詳 `helper_scripts/SCRIPT_INDEX.md` + `README.md` 「常用腳本」章節）：
```
改了代碼需部署              → bash helper_scripts/restart_all.sh --rebuild
只想清交易所持倉             → bash helper_scripts/clean_restart.sh --yes
開發告一段落要清 PnL/勝率    → bash helper_scripts/fresh_start.sh --yes
臨時停機 debug              → bash helper_scripts/stop_all.sh
```
