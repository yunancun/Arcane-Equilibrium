# OpenClaw / Bybit AI Agent 交易系統
# CLAUDE.md — 項目指令文件（核心規則 + 下一步指針）
# 最後更新：2026-04-16

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

**Runtime**：`Live_Ready` ⚠️（2026-04-16 audit 修正：原宣告不準確）— LIVE-P0/P1/P2 代碼完整、單測綠，但 **0 真實 live 流量**（歷史 43k 條 `engine_mode="live"` 實為 LiveDemo）。**真實 live 門控**：(1) Python `live_reserved` global mode、(2) Python Operator 角色 auth、(3) secret slot 有 `BYBIT_API_KEY/SECRET` 或 `settings/secret_files/bybit/live/{api_key,api_secret}`。`execution_authority` 在 Rust 僅為 P0/P1 denylist 字串常量（`claude_teacher/applier.rs:226`），非真實授權邏輯；「auto_granted_on_start」屬 Python 概念。Live 縮倉監控：5min 輪詢，≥5% 警告，≥15% 自動撤權+平倉+凍結 GovernanceHub（代碼已寫、e2e 測試綠，**從未真實觸發**）。

**權威原則**：Rust `openclaw_engine` = paper/demo/live 三引擎並行唯一引擎（ARCH-RC1 1C-4 + 3E-ARCH）。Rust ConfigStore 為所有交易/風控/學習/預算參數權威，4 IPC 寫入面 → tick-level hot-reload。**禁止 restart-to-apply**。Guardian = RiskConfig 純派生視圖。Python 無交易邏輯（DEAD-PY-2 清除 ~4500 行後）。**2026-04-16 audit 更正**：`legacy_routes.py + main_legacy.py` 共 1630 行**仍是活躍主承載**（main_legacy.py:450-451 `register_legacy_routes(app)` 注冊 54 路由），覆蓋 auth/login/gui/console/`/api/v1/system/*`/`/api/v1/health/db`/`/api/v1/learning/*`——原「已隔離不執行」敘述錯誤，此層拆分未完成。

**進行中/阻塞**：
- **STABILITY-1 ✅ RCA 完成（2026-04-16 深夜，operator 確認停電原因）**：當日 30 次 crash（初報 5，深撈後 30）**全部為單次停電斷網基礎設施事件，非代碼 bug**。operator 筆電 10:00-16:00 local 停電 ~6h，第一次 crash 10:45 local（停電 45min 後電池/路由器失電）；watchdog 13:16-18:03 local 完全靜默（硬斷電，post-gap `snapshot age=17313.5s` = 4.81h 陳舊鐵證）；engine log 全部為 `Temporary failure in name resolution` DNS 失敗 + HTTP transport error，**零 panic、零 assertion、零 rust backtrace**，純屬 REST/WS 連不上 Bybit 的合理 fail-closed。當前 PID 1364222 於 22:16 local 穩定。**P0-2 LG-1 21d demo 時鐘不重置**——基礎設施事件 ≠ 引擎不穩定，否則每次停電都重置永遠達不到。Nice-to-have：watchdog 加 DNS-loss 分類（連續 N 次 DNS failure → `network_outage`，不計 stability strike），不急。TODO §P0-9 已歸檔。
- **LEARNING-PIPELINE-DORMANT-1（P1-HIGH，2026-04-16 audit 新增）**：學習管線不是空殼是**半殼**——`learning.decision_features` 已累積 **1.65M rows**（live 1.07M / live_demo 576k / demo 800），`trading.risk_verdicts` 已累積 1.54M 24h，但：(1) `settings/edge_estimates.json` = `{}` 3 bytes（從未被寫過）；(2) `experiment_ledger_snapshot.json` top-level 是 list 非 dict（結構異常）；(3) 21 個 learning schema 表（bayesian_posteriors/linucb_state/teacher_directives/james_stein_estimates/model_registry/promotion_pipeline/rl_transitions 等）存在但無訓練任務消費；(4) **EDGE-P3-1 Phase B #3 ONNX loader 宣稱部署但 0 artifact 產出**。真正 gap：數據累積層 ✅、canonical intent 審計表 ❌、下游訓練/edge 估計/Teacher 指令 ❌ 全 dormant。TODO §P1-7。
- **LIVE-GUARD-1 ✅ 2026-04-16 深夜**：Rust 端 Mainnet 三重硬鎖回補（TODO §P0-8，E2 5/5 APPROVED，+7 新單測，engine lib 1342 passed）。Gate #1 `OPENCLAW_ALLOW_MAINNET=1` exact match · Gate #2 Mainnet 禁用 `BYBIT_API_KEY/SECRET` env var fallback（封閉 env 繞 slot 攻擊面）· Gate #3 憑證空時構造即 `Err`（不再 warn!+401）。Demo/Testnet/LiveDemo 零回歸。真實 live 門控從 1 項 Rust-verifiable 升為 **3 項**（見 §四表更新）。
- **INTENT-WRITE-GAP-1（P0-CRITICAL，2026-04-16 refine）**：`trading.risk_verdicts` 24h 內 live/live_demo Approved **154 萬條**（每條含 `intent_id`），`learning.decision_features` 同期 live/live_demo **165 萬 rows**，但 `trading.intents` 對 live/live_demo 同期 **0 條**。→ 改釐清為「canonical `trading.intents` 斷鏈 vs Rust 側影子路徑寫入」：Rust 分析/風控 path 照跑、canonical intent 持久化被 DEDUP-PY-RUST Tier A stub 掉 Python 端後未補 Rust 接線。下游 Phase 5/experiment_ledger 讀 `trading.intents` 查不到；讀 `decision_features` 可以。TODO §P0-6。
- **ORDER-SUBMIT-GAP-1（P0-CRITICAL，2026-04-16 新增）**：live_demo Approved verdict 持續但 `trading.fills` live/live_demo = 0。意味 Guardian 在跑、Approved verdict 寫入 DB，但 order submit path 被跳過（可能 OMSProxy 是 noop、或 trading_mode/live_reserved 未啟）。「Live_Ready」下真實下單能力 0%。TODO §P0-7。
- **Phase 5 PAUSED**（2026-04-12 reframe）— PNL-FIX-1/2 清理後所有活躍策略 gross edge 為負（net -$2775）；cost_gate/DL/JS 機械已接線但需真實正 edge。**下一步**：乾淨 demo 2 週後 P0-3 重評，若仍負則轉 EDGE-P3-1/EDGE-P2 接管。詳見 `memory/project_phase5_promotion_edge_crisis.md`。
- **P0-10 SCANNER-GATE ✅ 2026-04-17**：策略在 scanner 輪替出的 symbol 上反復開→平死循環（BASEDUSDT 等 20+ symbols，228 筆 ipc_close_symbol fills）。三部分修復：(1) tick_pipeline 新增 SymbolRegistry gate 阻止非活躍 symbol 開倉 (2) paper_state proactive_mirror_insert 彌合 REST→WS 空窗 (3) orphan_handler A4 移除（orphan=重啟遺留，非 scanner 輪替）。engine lib 1351 passed / 0 failed。
- **P0-5 PHANTOM-2-FUP ✅**：A+C 方案實作完成（HashMap+60s cooldown + clear 條件只在 Normal 時觸發）+5 新單測。已隨 P0-10 一起 `--rebuild` 部署。
- **P1 audit 衍生**：DEMO-REBOOT-PNL-RESET-1（重啟洗歷史 drawdown）、DEMO-BYBIT-SYNC-ORPHAN-1（6 個 bybit_sync 倉位策略動不了）— 詳 TODO §P1-5/P1-6。
- **非阻塞留尾**：W1 event_consumer 拆分；D-02 PriceEvent metadata HashMap 移除；IP-DEDUP-1（等 P0-3 判決）。

**已完成里程碑索引**（完整敘述 + commit + 測試數保留於 `docs/archive/2026-04-15--claude_md_section3_snapshot.md`）：

| 日期 | 里程碑 |
|---|---|
| 2026-04-08 | ARCH-RC1 1C-4 WRAP ✅ |
| 2026-04-09 | StrategyAction Enum ✅ · Rust 市場掃描器 Phase A-D + QC/FA + P2 ✅ |
| 2026-04-10 | DEAD-PY-1/2 · A2 NewsPipeline · LIVE-P0/P1/P2 · Live GUI Phase 4/5/6 + 平倉按鈕 · SEC-05 XSS · SM-1 治理統一 · Signal Diamond Fix · Phase 6 Reconciler 自動降級 · W20 ✅ |
| 2026-04-11 | 3E-ARCH 三引擎並行 · Multi-Symbol Position Tracking · W21 6-04~08 ✅ |
| 2026-04-12 | E5 Performance Optimization（23 項） ✅ |
| 2026-04-13 | G-SR-1 Signal Tightening · OC-5 FundingArb · Edge 數據 engine_mode 隔離 ✅ |
| 2026-04-14 | ORPHAN-ADOPT-1 Phase 1 · QoL-1/3 · ENGINE-HEAL 4 Fix · WP-F/UX-07~10 術語統一 ✅ |
| 2026-04-15 | EDGE-P3-1 ML-MIT #26 Lane A · FA-PHANTOM-2 spec · ORPHAN-ADOPT-1 Phase 2A · engine_watchdog systemd unit ✅ |
| 2026-04-16 | P0-4 R1 STRATEGY-CLOSE-TAG-FIX · P0-0 RECONCILER-BURST-FIX · P0-5 PHANTOM-2-FUP · PAPER-DISABLE-1 · DEDUP-PY-RUST Tier A · EDGE-P3-1 Phase B #3 + Step 7b/7c · G-2 daemon option D ✅ |
| 2026-04-17 | P0-10 SCANNER-GATE death loop fix（orphan A4 移除 + scanner universe gate + FUP race fix）· P1-8 DUST-EVICTION-GAP-1 E1/E4（dust_check 預檢 + orphan_frozen 凍結分支）· P1-8 FUP tick-level `retriage_synthetic_owner` 覆蓋全 synthetic labels 自主接管 · **MICRO-PROFIT-FIX-1**（fast_track 25% entry_notional 底線 + COST EDGE 窄帶 [0.3%, 0.55%]；12 檔修改，+11 單測/+7 整合測試，hot-reloadable via ConfigStore）✅ |
| 2026-04-18 | **LIVE-GATE-BINDING-1** ✅（HMAC-SHA256 signed `authorization.json` Python↔Rust 綁定契約；Rust 新 `live_authorization.rs` 模組 + `build_exchange_pipeline` 啟動驗簽 + `main.rs` 每 5 min re-verify；Python `_write_signed_live_authorization()` / `_delete_live_authorization_file()` hook 到 renew/approve/revoke 路由；canonical payload byte-for-byte 雙端對齊；Rust 15 新單測 / Python 10 新單測；真實 live 門控 Rust 可驗證從 3 項升為 **4 項**；LiveDemo 不因 api-demo endpoint 降級任何 live-level 檢查；詳見 `docs/worklogs/2026-04-18--live_gate_binding_1_implementation.md`） |

**歷史細節指針**（不要重複載入）：
- §三 2026-04-15 之前完整敘述 → `docs/archive/2026-04-15--claude_md_section3_snapshot.md`
- 1A→1C-4 commit 敘事 → `docs/archive/2026-04-08--arch_rc1_1c_history_archive.md`
- Phase 0-4 Sprint/Wave → `docs/archive/2026-04-07--claude_md_section3_history_phase0_4.md`
- 逐 commit 行數 → `docs/CLAUDE_CHANGELOG.md`
- 1C-3/1C-4 narrative → `docs/archive/2026-04-08--main_docs_1c3_1c4_narrative.md`

---

## 四、硬邊界（永遠不能違背）

```python
# ── Live_Ready 真實狀態（2026-04-18 LIVE-GATE-BINDING-1 ✅ 後更新）──
# LIVE-P0/P1/P2 基礎設施代碼完整（SM-01/02/04 + Reconciler + 3E-ARCH）
# 單測綠但 0 真實 live 流量（歷史 43k 條 "live" 實為 LiveDemo）。
#
# 當前真實 live 門控（Rust 端可驗證 = 4 項 / 全部 = 5 項）：
#   1. Python `live_reserved` global mode          （Python 狀態，重啟會丟）
#   2. Python Operator 角色 auth                   （Python 側）
#   3. OPENCLAW_ALLOW_MAINNET=1 env var            （Rust 側，LIVE-GUARD-1，僅 Mainnet）
#   4. secret slot 有 api_key + api_secret         （Rust 側，LIVE-GUARD-1，憑證空 → Err）
#        來源優先級（bybit_rest_client.rs:386-497）：
#          Mainnet:  a. 顯式參數 → b. slot file（env var 回退已封閉）
#          Demo/Testnet: a. 顯式參數 → b. env var → c. slot file
#   5. authorization.json 簽名+未過期+env_allowed 匹配  （Rust 側，LIVE-GATE-BINDING-1，新）
#        路徑：$OPENCLAW_SECRETS_DIR/live/authorization.json
#        驗證：canonical_payload HMAC-SHA256（key=OPENCLAW_IPC_SECRET）
#        檢查點：build_exchange_pipeline 啟動 + main.rs 每 5 min re-verify
#        失效 → engine 優雅 shutdown（cancel_token）
#        涵蓋 LiveDemo + Mainnet（LiveDemo 不因 api-demo endpoint 降級）
#
# ✅ LIVE-GATE-BINDING-1（TODO §P0-11，2026-04-18）：
#   - Python EarnedTrust renew/approve 路由寫出 signed authorization.json（0o600 + atomic rename）
#   - Revoke 路徑刪 authorization.json → Rust 下個 5 min re-verify 即 shutdown
#   - canonical payload byte-for-byte Python↔Rust 雙端對齊（sort+dedup envs）
#   - Rust 15 新單測 / Python 10 新單測 / engine lib 1452 passed
#   - 閉合「Operator 未 renew 即 Live 自拉」旁通漏洞
#
# ✅ LIVE-GUARD-1（TODO §P0-8，2026-04-16 深夜）：
#   - Gate #3: 恢復 OPENCLAW_ALLOW_MAINNET=1（SEC-17 回退）
#   - Gate #4a: Mainnet 禁用 BYBIT_API_KEY/SECRET env var fallback（封閉繞 slot 攻擊面）
#   - Gate #4b: 憑證空時構造 Err（不再 warn!+signing-stage 401）
#   - 7 新單測 + E2 對抗性審查 5/5 APPROVED
#
# execution_authority：Rust 僅為 P0/P1 denylist 字串常量
#                      （claude_teacher/applier.rs:226）非真實授權邏輯
#                      「auto_granted_on_start」= Python 概念
decision_lease_emitted  = False
max_retries             = 0

# 永不允許的硬錯誤（2026-04-18 LIVE-GATE-BINDING-1 後修正）：
# - 繞過 Operator 角色認證或 live_reserved global mode 直接啟動 live session
# - 自動修改 engine trading_mode 為 live（需 operator 顯式配置）
# - Bybit API timeout / retCode != 0 → fail-closed，不重試
# - should_call_ai=true 但 invocation 沒發生
# - 偽造 AI 調用或交易活動
# - Mainnet 下無 OPENCLAW_ALLOW_MAINNET=1 env var（LIVE-GUARD-1）
# - Mainnet 下試圖用 BYBIT_API_KEY/SECRET env var 作為唯一憑證來源（LIVE-GUARD-1）
# - Live（含 LiveDemo）下沒有有效 authorization.json 即 spawn pipeline（LIVE-GATE-BINDING-1）
#   LiveDemo 不因使用 api-demo endpoint 而降級任何 live-level 門控
# - 不經 _write_signed_live_authorization() 手動寫 authorization.json
#   必經 Python renew/approve 路由簽章寫入
```

---

## 五、架構總覽

```
[數據與觀察層]           Bybit REST + WS → Postgres + Observer
[H0 本地判斷內核]        freshness / health / eligibility / risk envelope（<1ms SLA）
[GovernanceHub]          SM-01 授權 + SM-04 風控 + SM-02 租約 + EX-04 對賬
[H1-H5 AI 治理層]       thought_gate / budget / model_router / governor / cost_logging
[I Decision Lease]       GovernanceHub.acquire_lease() / release_lease()
[Control API v1]         FastAPI 209 /api/v1 + 11 non-api 路由（2026-04-16 audit 實測）
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
- **§三 衛生規則（強制）**：§三 只記載「現況/活躍狀態」+「過去 ≤2 天的完成里程碑」。**任何完成里程碑當天 +2 日（以 `currentDate` 為準）必須在 commit 同次操作中歸檔到 `docs/archive/YYYY-MM-DD--claude_md_section3_*.md`** 並從 §三 刪除，僅在「已完成里程碑索引」表保留 1 行條目。違反 = §三 膨脹回 ~10K tokens、context 提早撞 compact。
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
| `_pool` | db_pool.py | `from .db_pool import get_conn` |
| `DEFAULT_LEASE_TTL_CONFIG` | lease_ttl_config.py | `from .lease_ttl_config import DEFAULT_LEASE_TTL_CONFIG` |
| `_backtest_engine` | backtest_routes.py | 內部懶加載 `_get_backtest_engine()` |
| `_scheduler` | evolution_auto_scheduler.py | 內部懶加載 `start_scheduler()` |
| `_evolution_engine` | evolution_routes.py | 內部懶加載 `get_evolution_engine()` |
| `_ledger` | experiment_routes.py | 內部懶加載 `get_experiment_ledger()` |
| `LeaseTTLConfigManager._instance` | lease_ttl_config.py | `LeaseTTLConfigManager.get_instance()` |
| `_RUST_BYBIT_CLIENT` | strategy_ai_routes.py | 內部懶加載 `_get_rust_client()` |
| `KLINE_MANAGER` / `INDICATOR_ENGINE` / `SIGNAL_ENGINE` / `ORCHESTRATOR` 等 12+ | strategy_wiring.py | 模組級全局，import 時初始化 |

新增 singleton 必須在此表登記。禁止子模塊創建未登記的全局可變狀態。

### 其他
- Route Handler 只做 parse → call → format，不含業務邏輯
- 新 Pydantic model 放 `*_models.py` 或所屬模塊，不加入 main_legacy.py

---

## 十、下一步工作指針

**當前焦點**：活躍任務與週次排期以 `TODO.md` 為準（P0/P1/P2/P3/P4 分層）。CLAUDE.md 不重複列週。

**關鍵路徑（2026-04-16 夜 audit 刷新 v3，P0-9 停電 RCA 後）**：
`P0-0 ✅ → P0-4 R1 ✅ → ~~LIVE-GUARD-1 Rust fail-safe~~ ✅ → ~~P0-9 STABILITY-1~~ ✅（停電基礎設施事件，非 code bug）→ P0-6 intent write gap → P0-7 order submit gap → P0-3 Phase 5 edge 2w 重評 + P0-2 LG-1 21d demo → P1-7 LEARNING-PIPELINE-DORMANT-1 → LG-4/5 → Live`
- P0-1 G-2（funding_arb 子集驗證）與 P0-5 PHANTOM-2-FUP 均**不在主路徑**
- P0-6/P0-7 若揭露架構級 DB write path 斷裂，Live 日期可能延後
- P1-7 LEARNING-PIPELINE-DORMANT-1 不阻 live 但阻 Phase 5 edge 收斂
- **最早 Live 日期**：**W24 末（～2026-05-23）**（P0-9 停電 RCA 後不延後，不重置 21d 時鐘）

**路線圖**：Phase 0-5 ✅ · Live GUI ✅ · Phase 6 ✅ · **AI 治理層 (W22-W23) ⬜**（H1-H5 AI agent 目前全 stub，待 G-1 R-06 展開）。

**Live 前置**：~~G-3 / G-5 / Phase 6~~ ✅ · ~~LIVE-GUARD-1 Rust fail-safe 補回~~ ✅（2026-04-16 深夜，三重 Mainnet 硬鎖，見 §三/§四） · ~~LIVE-GATE-BINDING-1 Python↔Rust 簽名授權綁定~~ ✅（2026-04-18，HMAC `authorization.json` + 5 min re-verify，見 §四 Gate #5） · ~~P0-9 STABILITY-1~~ ✅（停電基礎設施事件 RCA 完成，非 code bug，不重置 21d 時鐘） · demo ≥21d 穩定（P0-2，當前 PID 1364222 於 22:16 local 啟動，時鐘從此起算）· provider pricing 綁定（LG-3）· API key 填入 ≠ 即可上線（Rust 側 4 項可驗證硬鎖 + Python 側 2 項門控共 5 項，全綠才真實 live）。

**關鍵文件指針**（按需 Read，不要全載入）：
- Bybit API 字典/審計：`docs/references/2026-04-04--bybit_api_reference.md` · `docs/audits/2026-04-04--bybit_api_infra_audit.md`
- 完整參考索引：`docs/CLAUDE_REFERENCE.md`

---

## 十一、一句話狀態

> 截至 2026-04-18：tests engine lib **1452 (default)** + core **380** + e2e **35** + reconciler_e2e **19** + micro_profit_fix_integration **7** Rust 全綠 **0 fail** · Python `test_live_authorization_signing` **10/10 passed** · **LIVE-GATE-BINDING-1 ✅**（HMAC-SHA256 signed `authorization.json` Python↔Rust 綁定；Rust 新 `live_authorization.rs` +15 單測 + `build_exchange_pipeline` 啟動驗簽 + `main.rs` 5 min re-verify；Python `_write/_delete_live_authorization` hook 到 renew/approve/revoke；canonical payload byte-for-byte 雙端對齊；閉合「Operator 未 renew 即 Live 自拉」P0-CRITICAL 旁通漏洞；LiveDemo 不因 api-demo 降級；Rust 可驗證門控 3→**4 項**）· **MICRO-PROFIT-FIX-1 ✅**（fast_track `ft_min_notional_ratio_of_entry=0.25` 底線 + COST EDGE 窄帶 `cost_edge_max_ratio=0.2` + `min_profit_to_close_pct=0.3`，pnl_pct 目標帶 [0.3%, 0.55%]；E2 APPROVED_WITH_NITS）· **P1-8 DUST-EVICTION-GAP-1 E1/E4 ✅** · **P1-8 FUP tick-level `retriage_synthetic_owner` ✅** · **P0-10 SCANNER-GATE ✅ 部署** · **P0-5 PHANTOM-2-FUP ✅ 部署** · **P0-4 R1 ✅** · **P0-0 ✅** · **P0-9 STABILITY-1 ✅ RCA** · **LIVE-GUARD-1 ✅** · **Phase 5 PAUSED** · **Live_Ready ⚠️** · **下一步**：LIVE-GATE-BINDING-1 部署（`restart_all.sh --rebuild`）+ 1 週觀察 · P0-2 LG-1 21d demo 觀察 → P0-3 edge 重評 · P0-6 intent write / Demo 死循環打破 · **P1-7 LEARNING-PIPELINE-DORMANT-1** · P1-4 真 ETL 首個 ONNX artifact → Stage 2 shadow mode · Phase 2B Strategist 等 G-1 R-02。
