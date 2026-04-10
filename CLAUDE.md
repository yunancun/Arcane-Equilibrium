# OpenClaw / Bybit AI Agent 交易系統
# CLAUDE.md — 項目指令文件（核心規則 + 下一步指針）
# 最後更新：2026-04-10

---

## 一、項目定位

長期進化型 AI Agent 自動交易系統。OpenClaw 為中樞、**Bybit 為唯一交易所**（專攻）。

> Agent 自主完成交易決策與執行，對成本與收益有清晰感知，能感知自身狀態，能持續學習，在嚴格風控框架下逐步贏得更高自主權。

人類 Operator 角色：不定時檢查、審閱、矯正、批准關鍵步驟、推動策略演進。

**交易所決策（2026-04-03）：** 早期規劃含 Binance 雙平台，現已明確專攻 Bybit。Binance 僅作為超長期可能方向保留，當前開發、設計、架構決策均不需考慮 Binance 兼容性。

**系統管線：** 市場數據 → H0 本地判斷 → H1-H5 AI 治理 → I Decision Lease → 執行適配層 → 學習/歸因

---

## 二、16 條根原則（DOC-01 項目憲法 §5.1–§5.16，不可違背）

1. **單一寫入口** — 所有訂單/執行動作通過唯一受控入口
2. **讀寫分離** — 研究/GUI/學習：只讀。寫入權限極度受限、可審計、可鎖定
3. **AI 輸出 ≠ 即時命令** — AI → Decision Lease（帶時效、可撤銷）→ 本地復核 → 執行
4. **策略不能繞過風控** — 所有交易意圖必須經 Guardian 審批
5. **生存 > 利潤** — 先判斷「不會螺旋崩潰」，再判斷「能否盈利」
6. **失敗默認收縮** — 不確定時默認保守：不開新倉、降頻率、降風險
7. **學習 ≠ 改寫 Live** — 學習平面與 Live 平面隔離
8. **交易可解釋** — 每筆交易必須可重建：為什麼、何時、風控審批、授權、執行、結果
9. **交易所災難保護** — 本地止損 + 交易所條件單雙重防線
10. **認知誠實** — 所有結論區分事實 / 推斷 / 假設
11. **Agent 最大自主權** — P0/P1 硬邊界內，Agent 完全自主決定：幣種、策略、參數、時機
12. **持續進化** — 系統必須從交易行為中自動學習（當前 demo 階段：Paper 驗證→參數進化，live 自動部署待 Phase 3 放權框架）
13. **AI 資源成本感知** — 每次 AI 調用計費，cost_edge_ratio ≥ 0.8 → 建議關倉
14. **零外部成本可運行** — 基礎運營僅需 L0+L1（Ollama + 免費搜索）
15. **多 Agent 協作** — 5 Agent（Scout/Strategist/Guardian/Analyst/Executor）+ Conductor 編排，正式對象通信
16. **組合級風險意識** — 監控關聯曝險、策略重疊持倉、資金分配合理性

**優先級序：** 帳戶生存 > 風控治理 > 系統健康 > 審計可追溯 > 人類終審 > 真實 Net PnL > 自主能力進化

**實施準則（從根原則衍生，非憲法級但強制遵守）：**
- **認知調製 ≠ 能力限制** — Agent 壓力下更審慎的方式是提高決策門檻，不是關閉能力。虛擬稀缺性（能量/積分/內部貨幣）被明確否決。（衍生自原則 #11，見 `docs/references/2026-04-03--agent_cognitive_adaptation_spec_v1_draft.md`）

---

## 三、當前系統狀態摘要

**ARCH-RC1 1C-4 WRAP COMPLETE** ✅ — Rust ConfigStore 為所有交易/風控/學習/預算參數權威，4 IPC 寫入面 → tick-level hot-reload → 5 engines；Rust `openclaw_engine` 為 paper/demo/live 唯一引擎；Python 風控/紙盤雙退場；Guardian = RiskConfig 純派生視圖。**禁止 restart-to-apply**。

**StrategyAction Enum ✅**（2026-04-09）— 策略出場死鎖修復。策略 `on_tick()` 返回 `Vec<StrategyAction>`（`Open` 走完整治理，`Close` 輕量路徑繞過 Guardian/cost_gate/Kelly/P1）。5 策略改造完畢 + QC/FA 全修（grid 庫存漂移 P1、exchange Kelly P2、audit logging P2）。830 lib tests pass。

**Phase 5 P0 ACTIVE**（2026-04-08 提前）— Edge 危機：realized ≈ 2 bps vs fee 11 bps。PH5-WIRE-0 ✅ · PH5-DL-2+JS-1 ✅ · PH5-WIRE-1 ✅（mode-aware cost_gate 已上線，引擎已加載 8 cells，exploration mode 激活）· 5-01~03 ✅（per-param JS + k-means）· PH5-VERIFY-1 ⬜（7d 觀察期進行中）。**數據策略**：2026-04-10 執行 DB fresh-start reset（71.3M 開發噪音行清除，市場數據保留）。乾淨數據從 2026-04-10 重新起算，JS-1 滾動重跑排程：Day 2（2026-04-11）`--days 2` → Day 3（2026-04-12）`--days 3` → Day 7（2026-04-17）`--days 7` → 之後每週拉長窗口直到估計穩定。

**Rust 市場掃描器 Phase A-D + QC/FA + P2 ✅**（2026-04-09）— ScannerRunner 完整接線 + D2/D3 動態 symbol + C-3 XRP + C-4 pinned cap + M-1 pending_close + adl_alerts + M-2 TOML + M-3 f_ma 閾值 1.5%→0.5% + M-5 edge_bonus +5→+2 + m-1 relay log + m-3 rest_poller Vec<String> + **IPC-SCAN-1 掃描器可觀測性**（get_active_symbols / get_scanner_status）。**系統目標達成度 ~100%**。835 lib tests pass。

**Runtime 狀態**：`Live_Ready` ✅ — 所有前置阻隔已移除。**實際 Live 交易上線條件（唯一）**：`settings/secret_files/bybit/live/{api_key,api_secret}` 配置完畢（OPENCLAW_ALLOW_MAINNET env var 鎖已從 Rust 源碼移除）。execution_authority 在 live session start 時自動授予。**Live 縮倉監控 ✅**：session 啟動後每 5 分鐘輪詢 peak_balance/bybit_sync_balance；回撤 ≥5% → 警告；回撤 ≥15% → 自動撤銷 execution_authority + 平倉 + 凍結 GovernanceHub 授權。

**A2 NewsPipeline Scheduler ✅**（2026-04-10）— 60s 定時排程器接入 main.rs：3 providers（CryptoPanic free + CoinTelegraph RSS + Google News RSS）→ 去重 → severity → DB write → 4-09 三路 fan-out（Guardian/Regime/Learning）。受 `LearningConfig.switches.news_pipeline_enabled` 熱重載 gate 控制。

**DEAD-PY-1 全部完成 ✅**（2026-04-10）— Wave A/B/C 標籤 + WP-ARCH-RC1 舊命名 + whitelist UI 全量移除（tab-governance.html 220 行 + governance.js 19 行）。唯一殘留：test_risk_view_client 1 pre-existing fail。

**DEAD-PY-2 全部完成 ✅**（2026-04-10）— ~4500 行 Python 死代碼清除。Phase A：4 bridge 文件全刪（bridge_core/agents/stats/pipeline_bridge）。Phase B：5 Python 策略類全刪（ma_crossover/bollinger_reversion/funding_rate_arb/grid_trading/bb_breakout）。Phase C：ProtectiveOrderManager 全刪。Phase D：BybitDemoConnector 交易方法全刪（保留 2 個純工具函數）。Phase E：11 死 test 文件刪除 + 10+ 文件外科手術刪 dead class + strategy_wiring.py 瘦身。Python 層**完全無交易邏輯**，僅剩 API 橋接 + GUI 路由 + 輔助工具。872 Rust lib + 2427 Python passed (1 pre-existing fail)。

**LIVE-P0/P1/P2 全部完成 ✅**（2026-04-10）— P0: API key 管理 + tab-live 前置條件動態化 + 儀表板框架（commit c680ffd）。P1: `read_secret_file(slot)` 槽位感知 + `TradingMode::Live` variant + Python live session routes（commit 11283c7）。P2: `PerEngineRiskStores` 3 獨立 ConfigStore + IPC engine 路由 + GUI per-engine tab + Live 二次確認彈窗（commit 006d905）。840 lib tests pass。

**Live GUI Phase 4 完成 ✅**（2026-04-10）— `_EXECUTION_AUTHORITY_OVERRIDE` 記憶體覆蓋（in-memory gate，重啟清空 fail-closed）+ grant/revoke endpoints + `_ipc_command()` 3 bug 修復 + 實盤端點接入 PyO3 BybitClient（真實交易所數據）+ demo 模式 live session start + tab-live.html Grant/Revoke 按鈕 + 儀表板解析 PyO3 snake_case/Bybit camelCase 雙格式。（commit af392c2）

**SEC-05 innerHTML XSS ✅ + WP-F/AH-06 ✅**（2026-04-10）— `safeText()`→`ocEsc()` 委託 + 4 badge/label 函數 fallback 修復 + 逐文件 `ocEsc()` 包裹（app.js / linucb_card / tab-ai）。Risk-tab `_riskFormDirty` 防覆蓋。

**Live GUI Phase 5 完成 ✅**（2026-04-10）— 紫色主題（live_reserved 所有紅色 → #a855f7 / rgba(168,85,247,..)）+ 擴展儀表板（Account Balance 卡片組：equity/available/wallet/margin-used；PnL Overview：unrealized large + realized from cumRealisedPnl + net；持倉表 + Leverage 列；成交記錄折疊區懶加載 `/api/v1/live/fills`）+ Global Mode Gate（`_get_global_mode_state()` + 409 block if not live_reserved）+ auto-stop on mode exit + `oc-chip-live` 紫色 chip。緊急停止保持紅色。（commit c392220）

**Live GUI Phase 6 完成 ✅**（2026-04-10）— Live-Demo 虛擬 API key 槽（`settings_routes.py`：validate via demo server → 寫入 live path，operator 可用 Demo 帳號完整測試 live 路徑，換 key 時零代碼改動）；`tab-settings.html` 3 槽位卡片（Demo / Live-Demo / Live）+ peek 按鈕 + 上下文警示；`GET /api/v1/live/metrics` 新端點；paper_trading_routes `/metrics` 修復（`compute_full_metrics()` 返回完整 trade_metrics / drawdown_metrics / holding_period / sharpe，修復所有欄位顯示 "--"）；`tab-live.html` 新增 Performance Metrics 區塊（10 個指標卡，30s 自動刷新）。Signal Diamond 多引擎數據隔離規劃（共享市場數據 + per-mode intents/fills/positions，5 階段實施）已歸檔至 `docs/references/2026-04-10--signal_diamond_db_todo.md`。（commit 25b5d73）

**Live/Demo GUI 平倉按鈕 + Sidebar 修復 ✅**（2026-04-10）— (1) sidebar `refreshSidebar()` 改用 `/api/v1/live/session/status` 修復 "mode unknown auth: Not_Granted" 顯示；(2) live/demo 持倉表各行加單獨「平倉」按鈕（`POST /api/v1/live/positions/{symbol}/close` via IPC `close_position`；`POST /api/v1/strategy/demo/positions/{symbol}/close` via PyO3 `place_order reduce_only`）；(3) Positions 段落 header 加「全部平倉」按鈕，同時移除 control bar 重複按鈕；(4) paper tab 同步加「全部平倉」按鈕；(5) `_normalize_execution()` Rust→Bybit camelCase 映射。（commits c370cd1 / bfc3cea / 81a0acb）

**SM-1 治理授權統一 ✅**（2026-04-10）— (1) `max_position_usd` 不再硬編碼：`grant_paper_authorization()` 新增 `max_position_usd` 參數，`post_session_reauth` 改 async 從 Rust `RiskConfig.limits.max_order_notional_usdt` 讀取（commit 4815386）；(2) live SM-1 授權完整生命週期：session start / `grant_execution_authority` → SM-1 DRAFT→PENDING→ACTIVE（mode: live），session stop / `revoke_execution_authority` → SM-1 REVOKED；`governance_hub.get_status()` 多授權並存時優先顯示 mode=live；`_revoke_live_governance_auth()` 新增helper。（commit 435e613）2676 Python tests pass。

**Signal Diamond Fix Round ✅**（2026-04-10）— Phase 3+4 審計發現 9 gaps → 全部修復：P0 `set_trading_mode()` 雙向 swap 保存/恢復各模式狀態；P2 `AddMode`/`SwitchMode` IPC command 全鏈路接線；P3 Python IPC 層 mode-aware 參數化 + alias fallback；Phase 3 已知限制記錄（同時多模式需 per-mode Orchestrator，Phase 5+ 工作）。+5 Rust tests。E2 PASS + E4: 850/3/2692 全基線達標。

**Phase 6 Reconciler 自動降級 ✅**（2026-04-10）— 6-RC-1~5,7,8,9,10 完成。Reconciler 從 AUDIT-ONLY 升級為自動動作層：漂移→escalation（收緊風控）→漂移消失→hybrid 恢復（clean cycles + wall-clock）。觸發：MinorDrift 不動作 / MajorDrift·Orphan·Ghost·SideFlip→Cautious / persistent≥3→Defensive / burst≥5→CB+CloseAll / REST fail≥10→Cautious。恢復：逐級，CB/MR operator only。`ReconcilerState` + `evaluate_actions()` + `ReconcilerEscalate/DeEscalate` IPC + `Arc<AtomicU8>` shared risk level。+27 tests。872 engine lib + 365 core pass。6-RC-7 e2e 集成測試 7 場景 pass。6-RC-8 live blocker 解除。排除：6-RC-6（OC-3 阻塞）。

**留尾**（非阻塞）：W1 event_consumer 拆分。6-RC-6 多通道告警阻塞於 OC-3。

**歷史細節**（不要重複載入）：
- 1A→1C-4 commit 敘事 → `docs/worklogs/2026-04-08--arch_rc1_1c_history_archive.md`
- Phase 0-4 Sprint/Wave → `docs/archive/2026-04-07--claude_md_section3_history_phase0_4.md`
- 逐 commit 行數 → `docs/CLAUDE_CHANGELOG.md`
- 1C-3/1C-4 narrative → `docs/archive/2026-04-08--main_docs_1c3_1c4_narrative.md`

---

## 四、硬邊界（永遠不能違背）

```python
# ── Live_Ready 狀態（2026-04-10 更新）─────────────────────────────
# Live 基礎設施全部實施完畢（LIVE-P0/P1/P2 ✅ + Gov-P1 ✅）。
# 系統行為：完全以 Live 模式運行，前置阻隔已移除。
# 實際 Live 交易上線僅需 operator 提供以下兩個條件：
#   1. OPENCLAW_ALLOW_MAINNET=1   （Rust Mainnet guard，Rust 側硬鎖）
#   2. settings/secret_files/bybit/live/{api_key,api_secret} 配置完畢
#      （trading_mode 引擎配置對應調整）

execution_authority     = "auto_granted_on_start"  # live session start 時自動授予，stop 後重置
decision_lease_emitted  = False
max_retries             = 0

# 永不允許的硬錯誤（不因 Live_Ready 而放寬）：
# - 繞過 Operator 角色認證或 live_reserved global mode 直接啟動 live session
# - 自動修改 engine trading_mode 為 live（需 operator 顯式配置）
# - Bybit API timeout / retCode != 0 → fail-closed，不重試
# - should_call_ai=true 但 invocation 沒發生
# - 偽造 AI 調用或交易活動
# - Live 模式下無 OPENCLAW_ALLOW_MAINNET=1
```

---

## 五、架構總覽

```
[數據與觀察層]           Bybit REST + WS → Postgres + Observer
[H0 本地判斷內核]        freshness / health / eligibility / risk envelope（<1ms SLA）
[GovernanceHub]          SM-01 授權 + SM-04 風控 + SM-02 租約 + EX-04 對賬
[H1-H5 AI 治理層]       thought_gate / budget / model_router / governor / cost_logging
[I Decision Lease]       GovernanceHub.acquire_lease() / release_lease()
[Control API v1]         FastAPI 183 路由
[GUI + Learning]         11-Tab 控制台 + Learning Cockpit + Paper Trading Dashboard
[Rust openclaw_engine]   paper / demo / live 三模式唯一引擎（1C-3-F 後）
                         tick pipeline + IntentProcessor + paper_state + governance + stop_manager
[Layer 2 AI 推理]        L0 確定性 → L1 Ollama → L2 Claude
[風控框架]               P0/P1/P2 三層 + 對抗性止損 + AI 注意力稅
[策略工具包]             KlineManager → IndicatorEngine → SignalEngine → 5 策略 → Orchestrator
[管線橋接]               PipelineBridge: Tick Fan-Out + Intent→Order + 治理 gate
[止損管理器]             StopManager: Hard/Trailing/Time Stop + ATR 動態倉位
```

---

## 六、路徑與啟動

```
GitHub repo:    yunancun/BybitOpenClaw
本地主工作樹:   /home/ncyu/BybitOpenClaw/srv（/home/ncyu/srv ← symlink）
本地-only：     settings/（secrets）  trading_services/（runtime）
```

### 啟動檢查
```bash
git status && git log --oneline -5
```

### ★ 灰度驗證檢查（每次啟動必做，直到 R-07 Go/No-Go 通過）
Rust 引擎灰度驗證正在後台運行。**每次 session 啟動時先跑以下命令確認引擎健康：**
```bash
# 引擎存活？+ canary 記錄數 + 崩潰數 + 最新狀態
python3 helper_scripts/canary/engine_watchdog.py --data-dir /tmp/openclaw --stale-threshold 45 --grace-period 120 --status
wc -l /tmp/openclaw/engine_results.jsonl
grep -c "ENGINE_CRASH" /tmp/openclaw/watchdog.log 2>/dev/null || echo "0 crashes"
```
詳細操作指南見 TODO.md 頂部「灰度驗證檢查」段。如引擎掛了按 TODO.md 指引重啟。

### TODO.md 強制規則（每次接手必須遵守）

**接手時：** 必須讀 `TODO.md` 確認當前工作狀態，找第一個 `[ ]` 未完成項作為起點。用戶有明確指令時以用戶為準。

**發現新問題時：** 立即追加到 TODO.md，不等會話結束。

**修復完成後：** `[ ]` → `[x]`，追加完成 commit 號，更新測試基準線。

---

## 七、代碼與文檔規範

### ★★ 跨平台兼容性（強制，所有開發必須遵守）

**大前提：項目必須隨時可以部署在 macOS 上運行。**

1. **路徑不硬編碼** — 所有路徑使用環境變量或 config，禁止硬編碼 `/home/ncyu/`。
   用 `os.environ.get("OPENCLAW_BASE_DIR", ...)` 或 `Path(__file__).parent` 相對路徑。
   E2 必查：grep `/home/ncyu` 新代碼 → 打回。

2. **LocalLLMClient 抽象乾淨** — 不洩漏 Ollama-specific 細節。
   所有 LLM 調用通過 `LocalLLMClient` ABC 接口（Phase 1 任務 1.8）。
   禁止在業務邏輯中直接調用 Ollama HTTP endpoint。

3. **服務部署可遷移** — systemd → launchd 遷移路徑清晰。
   服務配置邏輯寫成文檔或腳本（`helper_scripts/deploy/`）。
   不依賴 systemd-specific 特性（如 `sd_notify`）。

4. **依賴管理乾淨** — `requirements.txt` 保持更新，禁止隱式依賴。
   新增 `import` 時同步更新 requirements。E2 必查。
   避免 Linux-only 依賴（如 `psutil` 的 Linux 特定 API），需要時加平台守衛。

### 雙語注釋（強制）
每個新建/修改的函數、類、模塊必須中英對照注釋（MODULE_NOTE / docstring / inline / fail-closed 路徑 / 安全代碼）。E2 必查。

### 強制同步規則
- **Sprint/Wave 完成**：更新 §三 + §十一 + `docs/CLAUDE_CHANGELOG.md` + README，與生產代碼同 commit
- **Commit 時**：摘要追加到 `docs/CLAUDE_CHANGELOG.md` 頂部，格式 `### 標題（YYYY-MM-DD · commit XXXXXXX）`
- **Context ≥90%**：立即寫 `docs/worklogs/YYYY-MM-DD--session_progress_N.md`（已完成/進行中/未完成/決策/下一步）
- **每日整合**：當天 worklog 碎片合併為 `YYYY-MM-DD--daily_summary.md`，刪碎片
- **新腳本**：MODULE_NOTE 雙語 + latest+dated 輸出 + contract check + 更新 SCRIPT_INDEX.md
- **docs/**：分類目錄 + `YYYY-MM-DD--描述.md` + 更新 `docs/README.md` 索引

---

## 八、16 Agent 角色體系與強制工作鏈

**強制**：所有任務按角色派發，主會話 = PM+Conductor。完整角色定義/激活矩陣見 `docs/CLAUDE_REFERENCE.md`。

**標準鏈**：PM+FA → PA 派發 → E1/E1a 並行 → **E2 代碼審查 → E4 測試回歸**（兩者絕不可跳）→ E5 優化（每 Phase/Wave/≥3 E1 任務強制）→ QA → PM 確認。E3/CC/A3/R4/TW 按需。
**P0 快速通道**：PA → E1 並行（≤5）→ E2 → E4 → PM。

**Bybit API 強制**：所有 Bybit 相關開發（REST/WS/IPC）先查字典手冊 `docs/references/2026-04-04--bybit_api_reference.md`，新增端點同步更新手冊，E2 必查。審計：`docs/audits/2026-04-04--bybit_api_infra_audit.md`。

---

## 九、代碼結構約定

### 文件大小限制
- **800 行** ⚠️ 警告線（E2 必須標記）
- **1200 行** 🛑 硬上限（不允許 merge）

### 模塊依賴方向（禁止循環 import）
```
state_models ← state_compiler ← state_store ← main_legacy ← main.py
其他 route 文件 ← main_legacy（通過 from . import main_legacy as base）
```

### Monkey-patch 安全
被 main.py patch 的函數（compile_state / STORE / envelope_response 等），新模塊必須通過 `main_legacy` 命名空間間接引用，不可直接 import 原始版本。

### Singleton 管理
| Singleton | 創建位置 | 導入方式 |
|-----------|---------|---------|
| `settings` | main_legacy.py | `base.settings` |
| `STORE` | main_legacy.py（main.py 重建） | `base.STORE` |
| `app` | main_legacy.py | `base.app` |
| `limiter` | main_legacy.py | `base.limiter` |

新增 singleton 必須在此表登記。禁止子模塊創建未登記的全局可變狀態。

### 其他
- Route Handler 只做 parse → call → format，不含業務邏輯
- 新 Pydantic model 放 `*_models.py` 或所屬模塊，不加入 main_legacy.py

---

## 十、下一步工作指針

**當前焦點（2026-04-10 審計後更新）**：10 個架構 gap 全部入計劃（TODO.md Gap 索引）。
- **W19（04-14~18）**：G-3 IPC 認證 + G-5 Rate Limiting + OC-3 多通道告警 + 6-RC-6（Live 阻塞項全清）
- **W20（04-21~25）**：SEC-04/06/13 E3 審查 + G-9 HMAC 確認 + 6-01~03 漸進放權
- **W21（04-28~05-02）**：6-04~13 Phase 6 完整驗收；LG-1 21d paper 到期（05-01）
- **W22（05-05~09）**：G-1 R-02 AI Agent（Strategist/Guardian）+ G-2/OC-5 FundingArb + LG-2/3
- **W23（05-12~16）**：G-1 R-06 全 5 agent + G-7 ClaudeTeacher + G-10 Calibration + LG-4/5 Live

**關鍵路徑**：`G-3 → OC-3 → 6-RC-6 → 6-01~13 → LG-1(05-01) → LG-2 → LG-4 → Live`
**最早 Live 日期**：W23 末（～2026-05-16）

**路線圖**：Phase 0-5 ✅ · Live GUI P0~P6 ✅ · **Phase 6 (W19-21) 🟡** 自動降級 ✅ · 告警+漸進放權+壓測 ⬜ · **AI 治理層 (W22-W23) ⬜**（H1-H5 AI agent 目前全 stub）。

**Live 前置**：Paper trading ≥21d · G-3 IPC 認證 · G-5 Rate Limiting · Phase 6 完成 · provider pricing 綁定。API key 填入即可上線（所有代碼阻隔已移除）。

**關鍵文件指針**（按需 Read，不要全載入）：
- Bybit API 字典/審計：`docs/references/2026-04-04--bybit_api_reference.md` · `docs/audits/2026-04-04--bybit_api_infra_audit.md`
- 融合方案/執行計劃/ML/DB/Rust：`docs/references/2026-04-04--*` · `docs/references/2026-04-03--*` · `docs/rust_migration/README.md`
- 完整參考索引：`docs/CLAUDE_REFERENCE.md`

---

## 十一、一句話狀態

> 截至 2026-04-10：tests engine lib **872** / core **365** / integration **11** / Python **2427** passed **1 pre-existing fail** · **DB fresh-start reset ✅**（71.3M 開發噪音清除，市場數據保留，PH5-VERIFY-1 從今天重新起算） · **DEAD-PY-2 ✅**（~4500 行 Python 死代碼清除，Python 層完全無交易邏輯） · **Phase 6 Reconciler 自動降級 ✅**（6-RC-1~5,7,8,9,10：漂移→escalation→hybrid 恢復，CB+CloseAll，+27 tests，7 e2e 場景） · **DEAD-PY-2 ✅** · **Signal Diamond Phase 1-4 ✅ + Fix Round ✅** · **Live/Demo 平倉按鈕 ✅** · **SM-1 live 授權統一 ✅** · **Live GUI P0~P6 ✅** · **Live 縮倉監控 ✅** · **Live_Ready ✅** · **SEC-05 XSS ✅** · **A2 NewsPipeline ✅** · **DEAD-PY-1 ✅** · **1C-4 ✅** · PH5-VERIFY-1 觀察期進行中 · **Live 唯一前置**：`settings/secret_files/bybit/live/` API key 填入。
