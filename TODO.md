# OpenClaw TODO — 工作計劃清單

**最後更新：2026-04-18**（**慢性虧損全週期 audit**：entry_context_id 配對 demo 24h → grid_trading net −$43.36 / ma_crossover −$11.90，fees 佔 grid gross loss 74%；bb_reversion 66 signals 0 fills，bb_breakout 0 signals；MICRO-PROFIT-FIX-1 narrow band 勝率實為 **99.39%**（491/494，非 100%）且為 sampling bias 非獨立 edge · 新增 **P1-9 ~ P1-12** 記錄成因鏈 · **P0 歸檔整理**：P0-5 / P0-8 / P0-9 / P0-10 四條完整內容移至 `docs/archive/2026-04-17--completed_todo_p0_scanner_phantom_live_guard.md`，TODO 內僅保留 2 行 stub · **P0-6 INTENT-WRITE-GAP-1 RCA DONE** · **P0-7 REFRAMED** 為 P0-6 子問題 · P1-7 LEARNING-PIPELINE-DORMANT-1 🟡）

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

### P0-1 · G-2 FundingArb 驗證 ✅ 2026-04-18 v2 NEGATIVE 結案（commit 9bd637a）
v2 n=13 partial 提前結案，net −$2.90 / −36.76 bps / 0 勝率、13/13 exit 命中 `max_basis_pct=0.5%` 邊界。Daemon PID 1834915 killed、demo `funding_arb.active=false`（含 IPC hot-toggle surface + 5 新單測）。MICRO-PROFIT-FIX-1 窄帶對 funding_arb 是錯誤成本模型。v2 audit：`docs/audits/2026-04-17--g2_funding_arb_clean_edge_v2.md`、v1 audit：`docs/audits/2026-04-16--g2_funding_arb_clean_edge.md`。待 R-02 Strategist 重評三參數（funding_threshold / max_basis_pct / total_cost_bps）。詳見記憶庫 `project_g2_funding_arb_monitor.md`。

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
**提前預覽（2026-04-18 全週期 audit，P1-10 詳）**：
- demo 24h entry-side: grid_trading **net −$43.36** / ma_crossover **−$11.90** / funding_arb −$2.07（已 disable）
- grid fee $31.43 = gross loss 74%；grid avg_loss/avg_win = **1.71×**、ma_crossover = **2.54×**（每次止損吃 1.5~2.5 次獲利）
- live_demo 24h: grid −$5.67 / ma_crossover +$0.79 / bb_* 0 fills
- **初步指示**：gross edge 大概率仍負 → P0-3 判斷結果可能是「策略重做」路徑；需與 P1-9 MICRO-PROFIT-FIX 重構聯動，才能辨別「策略本身沒 edge」vs「rule gate 過嚴把微利丟掉」

### P0-5 · PHANTOM-2-FUP ✅ 2026-04-16（已歸檔）
已部署（PID 1771173 於 2026-04-17 20:55 起跑，binary mtime 同刻）。詳見歸檔 `docs/archive/2026-04-17--completed_todo_p0_scanner_phantom_live_guard.md` §P0-5。

### P0-8 · LIVE-GUARD-1 ✅ 2026-04-16（已歸檔）
已部署。詳見歸檔 `docs/archive/2026-04-17--completed_todo_p0_scanner_phantom_live_guard.md` §P0-8。

### P0-6 · INTENT-WRITE-GAP-1 — live/live_demo `trading.intents` = 0 🟢 方案 A 部署 2026-04-17 夜
**原描述**：`trading.risk_verdicts` 大量 Approved 但 `trading.intents` live/live_demo/demo = 0。
**根因**（2026-04-17 確認，非 DEDUP-PY-RUST write path 斷裂）：**Rust gate cascade 在 Guardian 之後、intent 持久化之前拒絕 100% intents**。代碼路徑正確（`persist_intent` 只在 `gate.approved=true` 時觸發），問題是 **沒有任何 intent 最終被 approved**。

**✅ 方案 A 部署 2026-04-17 夜**（LiveDemo → Validation cost-gate mapping）：
- 新增 `mode_state::effective_governance_profile(kind, env)` 自由函式，endpoint-aware 映射：
  - Paper → Exploration · Demo → Validation · Live+Mainnet → Production · Live+LiveDemo/Testnet/Demo/None → **Validation**
- `TickPipeline::effective_governance_profile()` 方法 + `on_tick.rs` 兩處 callsite（exchange + paper）從 `self.pipeline_kind.governance_profile()` 改走新函式
- Scope：**僅** per-intent cost-gate tier selection；`GovernanceCore::new_with_profile()` 構造時 profile 不動，Live 管線的 Auth/Lease 語義不變（Python Operator auth 仍必須）
- Tests：engine lib 1415 (+2 new) / core 380 / reconciler_e2e 19 / stress 35 / micro_profit_fix 7 / phase4 3 / rrc1_audit 4 — 全綠 0 fail
- Build+Deploy：`bash helper_scripts/restart_all.sh --engine-only --rebuild`，PID 1827304 於 22:21 local 起（binary mtime 2026-04-17 22:20）
- 初步觀察（~1min post-deploy）：`cost_gate(JS-live): no edge estimate — fail-closed` = **0**（之前 85+/hr），`cost_gate(demo-cold-start): no JS estimate — allowing for data accumulation` = 3（Validation moderate gate 正確放行）

| 管線 | 阻擋 Gate | 根因 | 診斷證據 |
|---|---|---|---|
| **Live_Demo** | Gate 3 `cost_gate_live` | `edge_estimates.json = {}` → `get_cell()=None` → cold-start fail-closed（根原則 #5） | 630k decision_features = intents 通過所有 pre-cost-gate 檢查；engine.log: `cost_gate(JS-live): no edge estimate — fail-closed` |
| **Demo** | Gate 2.7 `check_order_allowed` | Bybit demo 帳戶 seeded positions → correlated exposure ~70% >= limit 65% | 0 decision_features = intents 在 evaluate_predictor_gate 之前被擋；engine.log: `risk_gate: correlated exposure 69-70% >= limit 65%` |
| **Demo** (次要) | Gate 2 Guardian | Seeded positions 觸發 `direction_conflict: opposite position exists` | 17.8k Rejected verdicts（`openclaw_core/guardian.rs:122`） |

**死循環結構**（與 P0-7 交織）：
- Live_Demo：`cost_gate_live` fail-closed → 0 fills → 0 edge data → `edge_estimates.json` 永遠是 `{}` → `cost_gate_live` 永遠 fail-closed
- Demo：correlated exposure 超限 → 0 new opens → 0 fills → positions 不關（P0-7 order submit gap）→ exposure 不降 → 永遠超限

**診斷方法**：`on_tick.rs` 添加 P0-6 DIAG `tracing::warn!` 在 `!gate.approved` 時輸出 `rejected_reason`（rate-limited: 前 50 條 + 每 10000 條一次）。此前 `rejected_reason` 被計算但從未 persist/log — 設計盲區。

**下一步**：
- [x] **Live_Demo 死循環打破**：方案 A — LiveDemo→Validation profile mapping（`cost_gate_moderate` cold-start 允許）✅ 2026-04-17 夜部署
- [x] **Live_Demo 觀察 ✅ 2026-04-18**：部署後 ~26h 驗證 — live_demo fills 1073 筆（grid/ma_crossover/MICRO-PROFIT-FIX-1 全活躍），`cost_gate(JS-live): no edge estimate` engine.log 出現次數從 85+/hr **歸零**。殘留觀察：(a) `trading.intents` 24h 仍 0 rows（與 P0-6 cost-gate 解耦，是 DEDUP-PY-RUST Tier A 後 Rust 端 intent 持久化未補接線 — 轉為下一步「永久修復」的延伸）；(b) `settings/edge_estimates.json` 仍 `{}`（P1-7 LEARNING-PIPELINE-DORMANT-1 範疇，edge estimator job 未啟）
- [ ] **Demo 死循環打破**：P1-8 FUP `retriage_synthetic_owner` 已 tick-level 執行（Agent 自主），等一週觀察是否消化 6 個 bybit_sync orphan；若不消化再轉方案 B 臨時調 `correlated_exposure_max_pct` 或方案 C 修 P0-7 Close path
- [x] **永久修復 ✅ 2026-04-18**：`rejected_reason` 已透過 synthetic `VerdictInfo::rejected(reason)` attached 到 `IntentResult` / `ExchangeGateResult`（`intent_processor/mod.rs` 新增 `VerdictInfo::rejected` / `IntentResult::rejected` / `ExchangeGateResult::rejected` 構造器，`gates.rs` + `router.rs` 所有前置 gate 拒絕點 refactor 使用新構造器）。`persist_verdict` 自此寫入 `trading.risk_verdicts.reasons` 真實拒絕理由（原本 `verdict_info: None` → 寫入被跳過）。+2 新單測（paper + exchange 各一條驗證 synthetic VerdictInfo 存在）。engine lib **1454 passed / 0 failed**。待下次 `--rebuild` 部署。
- [x] **移除 `on_tick.rs` P0-6 DIAG 代碼 ✅ 2026-04-18**：24-48h 條件已滿，`cost_gate(JS-live)` 0 occurrence 確認，移除 826-839 block（DIAG_COUNTER + rate-limited warn!）。engine lib 測試 **1437 passed / 0 failed**。待下次 `--rebuild` 部署

**注意**：`correlated_exposure_max_pct` config TOML = 60.0 但 runtime 為 65.0（GUI hot-reload 修改過）

**阻塞**：Live gate（需真實 fill data → edge 估計 → cost gate 通過；P0-7 共同阻塞。方案 A 部署後 Live_Demo 死循環已解，但 Live+Mainnet 仍靠 edge 累積 → P1-7 LEARNING-PIPELINE-DORMANT-1 共同阻塞真 live）

### P0-7 · ORDER-SUBMIT-GAP-1 — live/live_demo Approved verdict 沒觸發真實下單 🟡 REFRAMED 2026-04-17
**原描述**：570k Approved verdicts + 0 fills = order submit path 被跳過。
**P0-6 RCA 後更正**：**不存在獨立的 order-submit gap**。0 fills 的根因是 P0-6 gate cascade 拒絕 100% intents，`gate.approved` 從未為 true，所以 `on_tick.rs:690-733` 的 order dispatch 代碼從未被進入。order submit path 本身（OrderDispatchRequest → exchange REST）未壞，但從未被觸發。
**與 P0-6 死循環**：Demo positions 不關 → correlated exposure 超限 → 0 new opens 是因為 **Demo pipeline 無法自行 close 這些 seeded positions**。Close 動作走 StrategyAction::Close 分支（on_tick.rs），理論上不受 open gate cascade 限制，但需要策略主動 emit Close。如果 seeded positions 不屬於任何活躍策略（orphan positions），不會有策略 emit Close → 死循環。
**下一步**：
  - [ ] 確認 seeded positions 是否為 orphan（不屬於活躍策略）→ 若是，方案 = 手動清理或引擎 startup orphan reconciler
  - [ ] P0-6 修復後（Live_Demo cost gate / Demo correlated exposure）此 issue 自動消失
**阻塞**：Live gate（已與 P0-6 合併為同一阻塞點）

### P0-10 · SCANNER-GATE ✅ 2026-04-17（已歸檔）
已部署（PID 1771173, binary mtime 2026-04-17 20:55 local）。詳見歸檔 `docs/archive/2026-04-17--completed_todo_p0_scanner_phantom_live_guard.md` §P0-10。

### P0-9 · STABILITY-1 ✅ 2026-04-16（已歸檔）
RCA 完成：30 次 crash 全為單次停電 infra 事件，非 code bug；21d 時鐘不重置。詳見歸檔 `docs/archive/2026-04-17--completed_todo_p0_scanner_phantom_live_guard.md` §P0-9。

### P0-11 · LIVE-GATE-BINDING-1 — Python Earned-Trust ↔ Rust 授權綁定 ✅ 2026-04-18
**根因**：LIVE-GUARD-1 補完三重 Mainnet 硬鎖後，**LiveDemo 路徑仍可在 Operator 未 renew / approve 的情況下由 Rust 自拉**。Python 側 Earned-Trust / TTL / SM-01 對 Rust `build_exchange_pipeline()` 無任何執行性約束 — Rust 只認 slot 憑證。Operator 明確指示：LiveDemo 雖跑 `api-demo.bybit.com`，**不可因 endpoint 差異降級任何 live-level 門控**，否則 LiveDemo 就失去「驗證 Live 可靠」的價值。

**修復**：在 Python ↔ Rust 之間架 HMAC-SHA256 signed `authorization.json` 契約：
- **Rust 新模組** `rust/openclaw_engine/src/live_authorization.rs`：canonical payload（`version|tier|issued|expires|op|env_sorted_csv`）+ `verify_in_memory()` + `load_and_verify()` + `auth_error_kind()` telemetry label
- **Rust 啟動驗簽** `startup.rs::build_exchange_pipeline` — Live pipeline 在讀 Bybit client 前先 `load_and_verify(env)`；失敗即 `return None`（不 spawn）
- **Rust mid-session re-verify** `main.rs` — 引擎 started 後 spawn 5 min interval 任務，失效即 `cancel_token.cancel()` 優雅停機
- **Python 寫入** `live_trust_routes.py` — `_canonical_authorization_payload()` + `_sign_authorization_payload()` + `_atomic_write_json()`（tmpfile + 0o600 + `os.replace`）+ `_write_signed_live_authorization()` hook 到 `POST /api/v1/live/auth/renew` 與 `/renew/review` 成功路徑；失敗 `HTTPException(500)` 不謊報
- **Python 撤銷** `_delete_live_authorization_file()` 掛在 `_revoke_existing_live_auths()` 結尾 — Rust 下個 5 min re-verify 即 fail-closed shutdown
- **Fail-safe**：`OPENCLAW_IPC_SECRET` 不存在 → Python raise（絕不 silent 寫未簽檔）；`bybit_endpoint` 檔案缺失 → `env_allowed=["mainnet"]`（不偷偷放水 live_demo）

**測試**：
- Rust `cargo test -p openclaw_engine --lib live_authorization` **15/15** — canonical sort/dedup / 合法 live_demo+mainnet / EnvNotAllowed / Expired（`==` 邊界拒）/ 竄改 tier/env/expiry / 錯 secret / UnsupportedVersion（驗簽前擋）/ UnsupportedEnv(Demo/Testnet) / load_and_verify env override / auth_error_kind label 穩定
- Rust engine lib 全量 **1452 passed / 0 failed**
- Python `tests/test_live_authorization_signing.py` **10/10** — canonical byte-for-byte / sort+dedup / 手算 HMAC / 端到端寫檔 0o600 / 缺 IPC_SECRET raise + 不寫檔 / mainnet vs demo env_allowed / 缺 endpoint → mainnet / delete 冪等 / 模擬 crash 不留半成品 / TrustTier 全覆蓋

**效果**：真實 Live 門控 Rust 可驗證 **3→4 項**（見 CLAUDE.md §四 Gate #5），全部 5 項：
1. Python `live_reserved` global mode（Python）
2. Operator 角色 auth（Python）
3. `OPENCLAW_ALLOW_MAINNET=1`（Rust，LIVE-GUARD-1，僅 Mainnet）
4. secret slot 憑證非空（Rust，LIVE-GUARD-1）
5. **`authorization.json` 簽名有效+未過期+env 匹配（Rust，LIVE-GATE-BINDING-1，LiveDemo+Mainnet 等同）**

**部署**：`helper_scripts/restart_all.sh --rebuild`（Rust binary 變更）→ Operator 於 GUI renew/approve → Live pipeline 下次重啟或 config reload 才通過驗簽。

**工程日誌**：`docs/worklogs/2026-04-18--live_gate_binding_1_implementation.md`

**已知限制**：
- Revoke 生效最壞 5 min 延遲（Mainnet 上線前可降到 60s，改 `main.rs::AUTH_REVERIFY_INTERVAL_SECS`）
- LiveDemo 與 Mainnet 共用 `live/` slot（operator 切換 `bybit_endpoint` 檔時若 authorization.json 的 env_allowed 不匹配 → `EnvNotAllowed` 拒 spawn，符合 fail-safe）

**關鍵路徑**:`~~P0-0 reconciler burst fix~~ ✅ → ~~restart_all --rebuild 部署~~ ✅ → ~~P0-9 STABILITY-1 引擎崩潰 RCA~~ ✅（停電 infra 事件，非 code bug）→ ~~P0-11 LIVE-GATE-BINDING-1~~ ✅（2026-04-18，Python↔Rust 授權綁定）→ P0-6/P0-7 查清 intent/order 寫入斷點 → P0-3 Phase 5 edge 2w 評估 + P0-2 LG-1 21d demo → **P1-7 LEARNING-PIPELINE-DORMANT-1** → LG-4/5 → Live`(P0-1 G-2 並行驗證 funding_arb 子集,不在主路徑;~~P0-5 PHANTOM-2-FUP~~ ✅ 待 `--rebuild` 部署即生效;~~P0-8 LIVE-GUARD-1~~ ✅ Rust 端 Mainnet 三重硬鎖回補)
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

### P1-8 · DUST-EVICTION-GAP-1 — P0-6 triage evict dust 倉位無法平倉（engine/exchange silent drift）🟢 E1/E4 DONE 2026-04-17
**發現**：2026-04-17 ADAPTIVE-EXIT-FASTTRACK 部署（commit 待補）後驗證重啟 orphan 接管，抓到 P0-6 triage 對 dust 倉位處理 gap：
- 重啟 capture 7 個 demo bybit_sync 持倉；triage 分流 `adopted=1` (ETHUSDT→ma_crossover) `evicted=5`
- 5 個 evict 全部經 `ipc_close_symbol` 派發，但只有 **AVAXUSDT / CLUSDT** 真正進 `trading.fills`
- 另 3 個被 `event_consumer::dispatch` min_notional gate 擋下（`min_notional=$5.0`）：
  - PNUTUSDT: 3.0 × 0.06644 = $0.20
  - IPUSDT: 1.4 × 0.6007 = $0.84
  - AAVEUSDT: 0.02 × 117.15 = $2.34
- 證據 `/tmp/openclaw/engine.log 2026-04-17T18:55:57Z`：`order dispatch skipped: notional below exchange minimum`
- **silent drift**：3 個 dust 已從 `demo_state.json` 移除（engine 視為 evicted），但交易所仍持有；reconciler 後續會以 fresh-fill race 抑制 → 長期分歧無人察覺

**根因**：`event_consumer` P0-6 triage evict 路徑 fire-and-forget 假設 `ipc_close_symbol` 必然落地；`dispatch.rs` min_notional gate 是設計上的 fail-closed（Bybit retCode=170124 一類拒單防護），但對 dust 倉位無 fallback 分支；triage 本身不讀回 close 結果就把 engine 狀態清掉。

**候選修復**：
1. **最小動（推薦）**：evict 前預估 `est_notional = qty × ref_price`，小於 `min_notional` 改標 `orphan_frozen` 並保留在 engine state，不派 close、列入 operator 日報
2. **中動**：triage evict 改 two-phase（派 close → 等 reconciler 確認 fill → 才清 engine 狀態），close 失敗則標 frozen
3. **激進（不建議）**：實作內部對沖撮合 dust 清算路徑（與單一寫入口 §憲法 #1 衝突，需 Guardian 批）

**影響範圍**：demo/live 共通；live 下累積 dust 會造成 ledger ↔ exchange 對賬偏差，違反 §憲法 #9「交易所災難保護位置對稱」前提。

**不阻 Live**：FUP（2026-04-17）引入 tick-level `retriage_synthetic_owner` 後，dust 倉位由 Agent 自主復活/清理，無需 operator 介入或 Bybit GUI 手動清 dust（§原則 #11）。P1 優先級保留，僅剩 P2 QoL GUI 曝光。

**關聯**：
- P0-10 SCANNER-GATE（scanner 輪替退集合 → owner 倉位需 evict，dust 在此路徑特別易產生）
- ORPHAN-ADOPT-1 Phase 2A / P0-6 triage 設計
- 原始 `tick_pipeline::commands` ipc_close_symbol orphan hint 路徑（18:55:57Z 5 次 INFO log 可印證）

**下一步**：
  1. ~~E1 pick-up：確認 `event_consumer.rs` P0-6 triage evict callsite + `dispatch.rs` min_notional gate 行號~~ ✅
  2. ~~方案 1 實作（evict 前 notional 預檢，< min_notional 直接 mark `orphan_frozen`）~~ ✅ 2026-04-17
  3. ~~E4 寫單測（3 dust + 1 normal）~~ ✅ 2026-04-17 `paper_state.rs` 新增 5 個 DUST-EVICTION 測試（dust_frozen / normal evict / None fallback / 邊界 `==` / 三分支 mixed）
  4. 部署後觀察：先 log-only 一週，後續 GUI 曝光歸入 P2 QoL

**實施結果**（2026-04-17）：
- `position_reconciler/orphan_handler.rs` +`DUST_FROZEN_STRATEGY = "orphan_frozen"` 常量（刻意不入 `KNOWN_STRATEGY_NAMES`）
- `paper_state.rs` `TriageOutcome` +`dust_frozen: Vec<(symbol, is_long, qty, est_notional, min_notional)>`；`triage_bybit_sync` 加 `dust_check: impl Fn(&str, f64) -> Option<(f64, f64)>` 參數
- `event_consumer/mod.rs` triage 調用前建 `ref_prices` HashMap（latest_price → entry_price 備援），dust_check 回傳 `(qty * ref_price, spec.min_notional)`；新 warn! log `DUST-EVICTION-GAP-1:` + `P0-6 triage complete` 加 `dust_frozen` 計數
- 邊界對齊：est_notional `< min_notional` 嚴格小於（與 `dispatch.rs:76` 一致）
- engine lib 測試：**1391 passed / 0 failed**（triage 模組 11 passed = 6 legacy + 5 新增）

**FUP（2026-04-17，覆蓋全 synthetic labels 自主接管）**：
- **問題**：初版只在啟動時 triage `bybit_sync` → live session 期間 `orphan_frozen` / `orphan_adopted` / `bybit_sync` 三 synthetic labels 無路徑自動升級回真策略；違反 §原則 #11。
- **設計**（Opt A tick-level opportunistic）：
  - `paper_state.rs` 新增 `SYNTHETIC_OWNER_LABELS = ["bybit_sync", "orphan_adopted", "orphan_frozen"]`
  - `RetriageOutcome` enum（`NoOp` / `FrozenAsDust` / `Promoted` / `NeedsEviction`）+ `retriage_synthetic_owner(symbol, price, in_universe, target_strategy, min_notional)` 方法
  - `tick_pipeline` 新增 `retriage_last_evict_ms: HashMap<String, u64>` + `retriage_synthetic_owner_for_symbol()`；`on_tick.rs` 在 `set_latest_price` 後掛 hook
  - Fast path：非 synthetic label 單次 HashMap lookup + string compare return
  - Promoted 時清 dedup entry；NeedsEviction 走 `ORPHAN_CLOSE_DEDUP_MS=2min` dedup 後 `ipc_close_symbol` 派發
- **行為矩陣**：
  | 條件 | 結果 |
  |---|---|
  | 非 synthetic owner | NoOp（fast path） |
  | qty=0 / price≤0 | NoOp |
  | `est_notional < min_notional` | FrozenAsDust（首次 demote 時 was_downgraded=true warn） |
  | `in_universe && notional OK` | Promoted → `KNOWN_STRATEGY_NAMES[0]` |
  | `!in_universe && notional OK` | NeedsEviction → 2min dedup `ipc_close_symbol` |
- **engine lib 測試**：**1413 passed / 0 failed**（retriage 模組 10 新增 = noop_real / noop_no_pos / freeze_dust / idempotent_frozen / promote_frozen_recovery / promote_bybit_sync / promote_orphan_adopted / needs_eviction_oob / zero_price_noop / no_min_notional_skip）

### P1-9 · MICRO-PROFIT-FIX-1 語意重構 — 從 cost_edge gate 改為 net-profit 套利 🟢 NEW 2026-04-18
**發現**：2026-04-18 operator 澄清設計意圖：MICRO-PROFIT-FIX-1 應該是「**有微利就套**」，不是「低收益條件下 `cost_edge_ratio` 夠大才套現」的 gate。
**現況**（`rust/openclaw_engine/src/risk_checks.rs:227`）：
- 觸發條件：`cost_edge_ratio in [0.20, ...] AND pnl_pct >= 0.30%`（MICRO-PROFIT-FIX-1 narrow band）
- 24h demo + live_demo 觸發 494 筆、勝率 **99.39%**（491/494，非 100%，2 筆 −$0.0045 微負 + 1 筆 0）
- net +$47 demo / +$13 live_demo；但這是 **sampling bias**，不是獨立 edge — 規則按定義只在 pnl_pct ≥ 0.30% 時觸發，自選正收益
**語意問題**：當前 `pnl_pct >= 0.30%` 門檻**偏高**，可能把 < 0.30% 的真實微利（扣完 fee 仍為正）全部丟掉。正確語意應是 `realized_pnl_estimate - fee_estimate > min_net_profit` 為**主門**，`cost_edge_ratio` 降為輔助信號。
**候選方案**：
1. **最小動**：新增 `micro_profit_lock_min_net_bps`（如 5 bps = 0.05% 淨利），觸發條件改 `(est_pnl - est_fee) / notional >= min_net_bps`；保留 `cost_edge_ratio` 做 tie-breaker 排序但不作為 hard gate
2. **中動**：拆出獨立 `take_profit_on_micro_gain` rule（與 cost_edge 剝離），新規則只管 `net_pnl > threshold`，cost_edge 規則只管「成本吃光預期利潤時關倉」
3. **激進**：徹底移除 MICRO-PROFIT-FIX-1 narrow band，改做 strategy-native micro-TP（每策略自帶 `take_profit_bps` 參數）
**下一步**：
  1. [ ] E1 確認 `risk_checks.rs` MICRO-PROFIT-FIX-1 邏輯位置 + `PaperPosition.entry_notional` accumulate 與 fee 估計路徑
  2. [ ] 設計 `min_net_profit_bps` config（ConfigStore hot-reload，預設 5 bps）+ 保持向後兼容（舊 `min_profit_to_close_pct` 路徑可配置為 fallback）
  3. [ ] E2 審查 + E4 單測（<0.30% pnl 但 net>0 場景、剛好 break-even、邊界）
  4. [ ] 部署後 48h 觀察：catch rate（微利捕獲筆數）+ 錯誤套現（套了但後續大漲失去的更多）誤傷率
**預期效果**：grid/ma_crossover 部分倉位在 0.10~0.29% 區間的 **unrealized profit** 被提前鎖，avg_win 上升、勝率升、不對稱倍數下降；但可能犧牲「繼續持倉走向更大獲利」的尾部
**影響 P0-3 判斷**：與 P0-3 Phase 5 edge 2w 重評**聯動**。需辨別「策略本身負 edge」vs「rule gate 把微利丟掉造成假負 edge」— 先重構 MICRO-PROFIT-FIX-1，再評 Phase 5 才能得出乾淨結論
**風險**：若降門檻後反而因為「過早鎖利 + 隔夜 funding 磨損」惡化 edge，需要 rollback；單測必須包含「long-hold winner 被過早砍斷」情境

### P1-10 · STRATEGY-ASYMMETRY-1 — grid/ma_crossover 風險報酬不對稱 + 過度交易 🟢 NEW 2026-04-18
**發現**：2026-04-18 全週期 audit（`entry_context_id → context_id` 配對 exit fills 歸回 entry strategy）
| engine | strategy | n_exits | sum_pnl | fee | net | 勝率 | avg_win | avg_loss | 不對稱倍數 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| demo | grid_trading | 747 | −$11.92 | $31.43 | **−$43.36** | 59% | $0.145 | −$0.248 | **1.71×** |
| demo | ma_crossover | 135 | −$6.47 | $5.43 | **−$11.90** | 64% | $0.186 | −$0.471 | **2.54×** |
| live_demo | grid_trading | 405 | +$2.16 | $7.83 | **−$5.67** | 66% | $0.060 | −$0.103 | 1.72× |
| live_demo | ma_crossover | 102 | +$2.79 | $2.00 | **+$0.79** | 67% | $0.104 | −$0.126 | 1.21× |
**兩個核心問題**：
1. **grid demo fee $31.43 = gross loss 74%** — 過度交易；747 exits / 24h 平均 **31 筆/h**，Bybit taker fee 吃掉主要成本。Live_demo 405 exits 相對合理但仍偏多
2. **ma_crossover demo 不對稱 2.54×** — 勝單 $0.19 vs 虧單 $0.47，等於一次止損吃 2.5 次獲利。勝率 64% 本應正 edge，但不對稱倍數讓它反轉為負（數學上 64% × 0.19 − 36% × 0.47 = −$0.048/筆）
**下一步**：
  1. [ ] **grid 交易頻率 audit**：查 `grid_trading.rs` 掛單/平倉節奏；`grid_levels=10 + spacing_mode=linear` 是否過密；考慮提高 `cooldown_ms`（目前未見該參數）或加 per-fill min holding time
  2. [ ] **ma_crossover SL/TP 對稱性 audit**：目前靠 P2 動態 SL/TP（ATR 動態）；實際止損距離 vs 止盈距離比率是否 ≥2：1？若是，需調整 ATR mult 或加上 asymmetric R:R ratio gate
  3. [ ] 聯合 P1-9 MICRO-PROFIT-FIX 重構後重新評估 — 微利捕獲改善後不對稱倍數應下降
**阻塞**：不阻 Live（Live 前置以 LG-1/2/3 為準），但這是 Phase 5 edge 負的**結構原因**；不修 P0-3 Phase 5 edge 無法真正翻正
**影響**：若 ma_crossover 2.54× 無法收斂到 ≤1.5×，應考慮 disable 或等 R-02 Strategist 重評入場信號

### P1-11 · BB-BREAKOUT-DORMANT-1 — 5 重 AND 入場門過嚴，14d 零觸發 🟢 NEW 2026-04-18
**發現**：2026-04-18 全週期 audit 揭露 bb_breakout 14 天 demo/live_demo **0 fills**（連 decision_features 都 0 筆），但 `strategy_params_demo.toml` `active=true`。
**根因**（`rust/openclaw_engine/src/strategies/bb_breakout.rs:457-518`）：入場條件為 5 重 AND：
1. `bb.bandwidth < squeeze_bw (0.02)` 先觸發 squeeze
2. `bb.bandwidth > expansion_bw (0.04)` 再擴張突破（時序要求：先收窄再擴張）
3. `volume_ratio >= volume_threshold (1.5)` 量爆確認
4. Donchian 突破確認（價格越過 upper/lower）
5. `persistence filter` 信號持續性（`min_persistence_ms`）
**評估**：設計為高選擇性（避免假突破），但 5 重 AND + 時序要求讓多數幣種多數時間都過不了。0 觸發不是 bug 而是**設計過嚴**。
**下一步**：
  1. [ ] **閾值 offline backtest**：降 `squeeze_bw` 至 0.025 / `expansion_bw` 至 0.035 / `volume_threshold` 至 1.2，跑 30d 歷史回測看頻率 vs edge 變化
  2. [ ] **Donchian 改 OR**：把 Donchian 從 AND gate 降為 OR/score（bb 突破 + Donchian 確認 boost confidence，但非硬 gate）
  3. [ ] **考慮分拆**：bb_breakout_aggressive（降閾值）vs bb_breakout_conservative（保留當前），同時上線做 A/B
**阻塞**：非關鍵路徑。若不啟用只是少一個策略貢獻 edge；但 bb_breakout 本身設計為趨勢捕獲，在 ma_crossover 表現差的情況下可能是重要補充
**優先級**：P1 低 — 不緊急但影響 Phase 5 策略多樣性

### P1-12 · BB-REVERSION-BLOCKED-1 — 66 signals 產生但 100% 被下游擋下 🟢 NEW 2026-04-18
**發現**：2026-04-18 audit 揭露 bb_reversion 24h 在 live_demo 產生 **66 筆 decision_features**（信號層有輸出）但 **0 fills**（14d 內 demo 僅 2 筆，最後一筆 2026-04-15）。
**問題**：信號生成 → fill 之間的轉化率 = 0%。可能阻擋點：
- confluence 評分過濾過嚴
- risk_gate `check_order_allowed` 拒絕（correlated exposure / drawdown / margin util）
- cooldown_ms（600000 = 10 分鐘）在高信號頻率下可能鎖死
- `use_limit=false` 下市價入場被 dispatch 拒單（notional gate）
- 被 MICRO-PROFIT-FIX-1 之外的 risk_close reason 秒殺
**下一步**：
  1. [ ] 找出 66 筆 `decision_features` 的 intent_id/context_id，join `risk_verdicts` + engine.log trace 每筆命運
  2. [ ] 統計阻擋分佈：confluence / correlated_exposure / cooldown / dispatch min_notional / 其他
  3. [ ] 根據主要阻擋原因對症處理（調閾值 / 降 cooldown / etc.）
**阻塞**：非關鍵路徑；與 P1-11 類似（策略多樣性問題）
**優先級**：P1 中 — 比 P1-11 優先，因為信號層已有輸出只差通路打通
**備註**：需要 rejected_reason persist（P0-6 下一步 #3 「永久修復：rejected_reason 應 persist 到 DB」）才能高效 trace；否則只能靠 engine.log grep

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

## 🔍 Gap 排期索引（2026-04-10 審計 10 項 + 2026-04-17 補 1 項）

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
| G-11 | P0-6 triage evict dust 倉位無法平倉（silent drift）→ P1-8 DUST-EVICTION-GAP-1 | W23（log-only 先） | 🟢 E1/E4 DONE 2026-04-17 |

---

## 📚 已完成歸檔索引

- **2026-04-17 SCANNER-GATE + PHANTOM-2-FUP + LIVE-GUARD-1 + STABILITY-1 RCA**：`docs/archive/2026-04-17--completed_todo_p0_scanner_phantom_live_guard.md` ← **本次整理新增**
- **2026-04-16 STRATEGY-CLOSE-TAG-FIX + EDGE-P3-1 Phase B #3 + DEDUP-PY-RUST**：`docs/archive/2026-04-16--completed_todo_strategy_close_tag_edge_p3_dedup.md`
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
