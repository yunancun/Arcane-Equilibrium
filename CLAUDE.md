# OpenClaw / Bybit AI Agent 交易系統
# CLAUDE.md — 項目指令文件（核心規則 + 下一步指針）

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

**進行中/阻塞**（已完成 ≤2 日的項目 + 仍活躍的 gap）：
- **LEARNING-PIPELINE-DORMANT-1（P1-HIGH，2026-04-16 audit · 2026-04-18 refine v2）**：學習管線半殼 — `learning.decision_features` 累積 **1.65M rows**（live 1.07M / live_demo 576k / demo 800），`trading.risk_verdicts` 累積 1.54M 24h；P1-16 halt_session cross-symbol price corruption 根因修復已完成（詳 `docs/archive/2026-04-21--claude_md_section3_snapshot.md` 引用的 `fef688e`）。**剩餘 gap**：`settings/edge_estimates.json` writer/reader 手動 run（無 cron/scheduler/hot-reload，bind cost_gate 門檻 grand_mean > −50 bps 且 ≥2 策略 shrunk_bps>0）；`experiment_ledger_snapshot.json` 結構異常；21 個 learning schema 表無訓練任務消費；**EDGE-P3-1 Phase B #3 ONNX loader 宣稱部署但 0 artifact 產出**。TODO §P1-7 / §P1-14 / §P1-17。
- **INTENT-WRITE-GAP-1（P0-CRITICAL，2026-04-16 refine）**：`trading.risk_verdicts` 24h 內 live/live_demo Approved **154 萬條**（每條含 `intent_id`），`learning.decision_features` 同期 live/live_demo **165 萬 rows**，但 `trading.intents` 對 live/live_demo 同期 **0 條**。→ 改釐清為「canonical `trading.intents` 斷鏈 vs Rust 側影子路徑寫入」：Rust 分析/風控 path 照跑、canonical intent 持久化被 DEDUP-PY-RUST Tier A stub 掉 Python 端後未補 Rust 接線。下游 Phase 5/experiment_ledger 讀 `trading.intents` 查不到；讀 `decision_features` 可以。TODO §P0-6。
- **ORDER-SUBMIT-GAP-1（P0-CRITICAL，2026-04-16 新增）**：live_demo Approved verdict 持續但 `trading.fills` live/live_demo = 0。意味 Guardian 在跑、Approved verdict 寫入 DB，但 order submit path 被跳過（可能 OMSProxy 是 noop、或 trading_mode/live_reserved 未啟）。「Live_Ready」下真實下單能力 0%。TODO §P0-7。
- **Phase 5 PAUSED**（2026-04-12 reframe）— PNL-FIX-1/2 清理後所有活躍策略 gross edge 為負（net -$2775）；cost_gate/DL/JS 機械已接線但需真實正 edge。**下一步**：乾淨 demo 2 週後 P0-3 重評，若仍負則轉 EDGE-P3-1/EDGE-P2 接管。詳見 `memory/project_phase5_promotion_edge_crisis.md`。
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
| 2026-04-17 | P0-10 SCANNER-GATE · P0-5 PHANTOM-2-FUP · P1-8 DUST-EVICTION-GAP-1 E1/E4 · MICRO-PROFIT-FIX-1 ✅（詳 `docs/archive/2026-04-20--claude_md_section3_snapshot.md`） |
| 2026-04-18 | LIVE-GATE-BINDING-1 · E5-P0 Refactor Wave · P1-16 HALT-SESSION CROSS-SYMBOL PRICE CORRUPTION ✅（詳 `docs/archive/2026-04-20--claude_md_section3_snapshot.md`） |
| 2026-04-19 | PIPELINE-SLOT-1 Phase 1-4 · E5-P1 Refactor Wave 1 · E5-P2 Refactor Wave 2 · FILL-CONTEXT-LINKAGE-1 · EXIT-FEATURES-TABLE-1 Phase 1b FUP · E5-FN Functional Defects Wave ✅（詳 `docs/archive/2026-04-21--claude_md_section3_snapshot.md`） |
| 2026-04-20 | **EDGE-P2-2 Phase A** ✅ `381c542`（OI confluence signal for `bb_breakout` — 3 新參數 `enable_oi_signal`/`oi_buffer_window_ms`/`oi_confluence_bonus`/`oi_min_delta_pct` + 3 env TOML；E2 對抗性審查 7 findings 全修（#1 buffer dedup / #2 on_rejection preserve / #3 noise floor / #4 validate_oi factory mirror / #5 hot-reload smoke / #6 ts regression guard / #7 unit coverage）；engine lib 1770→**1791** passed；Phase B Liquidation signal 待做） · **LLM-ABC-MIGRATION-1** ✅（5 call-site 切 `local_llm_factory.get_local_llm_client()` — `ai_service.py` / `strategy_wiring.py` / `layer2_engine.py` / `layer2_routes.py` / `layer2_tools.py`；新 `app/local_llm_factory.py` + `LMStudioShimClient` 暴露 OllamaClient-shape 介面回 `OllamaResponse`，call-site parsing 零變動；`LOCAL_LLM_PROVIDER` env 切 `ollama`(default)/`lm_studio`，未知值 fallback Ollama；17 pytest 新測 + 11 既有 patch-target 更新 + 1 訊息文案對齊；business code 0 `import OllamaClient`；**Mac operator 設 `LOCAL_LLM_PROVIDER=lm_studio`+`LM_STUDIO_BASE_URL` 即可不裝 Ollama 跑 Layer 2**；閉合 CLAUDE.md §七「LocalLLMClient 抽象乾淨」既有技術債） |
| 2026-04-21 | **DUAL-TRACK-EXIT-1 Phase 1b Track P v2 pure fn** ✅ commit `aee96b9`（`exit_features.rs` +698：`physical_micro_profit_lock_v2` 非線性 giveback 4-Gate pure fn + `ExitConfig` 7 參數 `Default`/`validate`/serde + `non_linear_giveback_fn` + 31 單測；QC 反轉 Gate 1 `edge <= floor → Hold` 對齊設計意圖「防止剛有大於 fee 的微利就套離場」、Lock 唯一路徑 = Gate 4 trailing；engine lib 1791 → **1816**） · **GATE1-REVERSAL-1 hotfix A** ✅（同日 follow-up：v1 `risk_checks::physical_micro_profit_lock` Priority 6 Gate 1 同步反轉 Lock → Hold 對齊 v2；3 tests rename + assert 反轉 risk_checks 2 + position_risk_evaluator 1；`phys_lock_gate1_low_edge` v1 不再 emit，下游 `strip_phys_lock_prefix` + `parse_exit_tag` 保留解析向後兼容；engine lib 仍 **1816** 不變；剩餘符號統一 + Priority 6 整體替換 v1→v2 + ConfigStore 綁定 + replay 校準留下一波，TODO `GATE1-REVERSAL-1` 改 `[~]` 部分完成） · **memory** 新增 `project_dev_runtime_split.md`（Mac 接手三連 engine 檢查 noop） |

**歷史細節指針**（不要重複載入）：
- §三 2026-04-16 STABILITY-1/LIVE-GUARD-1 + 2026-04-19 完整敘述 → `docs/archive/2026-04-21--claude_md_section3_snapshot.md`
- §三 2026-04-17/18 完整敘述 → `docs/archive/2026-04-20--claude_md_section3_snapshot.md`
- §三 2026-04-15 之前完整敘述 → `docs/archive/2026-04-15--claude_md_section3_snapshot.md`
- 1A→1C-4 commit 敘事 → `docs/archive/2026-04-08--arch_rc1_1c_history_archive.md`
- Phase 0-4 Sprint/Wave → `docs/archive/2026-04-07--claude_md_section3_history_phase0_4.md`
- 逐 commit 行數 → `docs/CLAUDE_CHANGELOG.md`
- 1C-3/1C-4 narrative → `docs/archive/2026-04-08--main_docs_1c3_1c4_narrative.md`

---

## 四、硬邊界（永遠不能違背）

```python
# ── Live_Ready 真實狀態 ──
# LIVE-P0/P1/P2 代碼完整（SM-01/02/04 + Reconciler + 3E-ARCH），0 真實 live 流量
# （歷史 43k 條 engine_mode="live" 實為 LiveDemo）。

# 真實 live 門控（Rust 端可驗證 = 4 項 / 全部 = 5 項）：
#   1. Python `live_reserved` global mode           （Python 側，重啟會丟）
#   2. Python Operator 角色 auth                    （Python 側）
#   3. OPENCLAW_ALLOW_MAINNET=1 env var             （Rust 側，僅 Mainnet）
#   4. secret slot 有 api_key + api_secret          （Rust 側，憑證空 → Err；
#        Mainnet env-var fallback 封閉，來源優先級見 bybit_rest_client.rs:386-497）
#   5. authorization.json 簽名+未過期+env_allowed 匹配  （Rust 側，HMAC-SHA256）
#        路徑：$OPENCLAW_SECRETS_DIR/live/authorization.json
#        檢查點：build_exchange_pipeline 啟動 + main.rs 每 5 min re-verify
#        失效 → engine 優雅 shutdown（cancel_token）
#        涵蓋 LiveDemo + Mainnet（LiveDemo 不因 api-demo endpoint 降級）
#        **必經** Python renew/approve 路由 `_write_signed_live_authorization()`，不可手動寫

# execution_authority：Rust 僅為 P0/P1 denylist 字串常量
# （claude_teacher/applier.rs:226），非真實授權邏輯；「auto_granted_on_start」屬 Python 概念。
decision_lease_emitted  = False
max_retries             = 0

# 永不允許的硬錯誤：
# - 繞過 Operator 角色認證或 live_reserved 直接啟動 live session
# - 自動修改 engine trading_mode 為 live（需 operator 顯式配置）
# - Bybit API timeout / retCode != 0 → fail-closed，不重試
# - should_call_ai=true 但 invocation 沒發生；偽造 AI 調用或交易活動
# - Mainnet 下無 OPENCLAW_ALLOW_MAINNET=1，或用 env var 當唯一憑證來源
# - Live（含 LiveDemo）下無有效 authorization.json 即 spawn pipeline
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
本地主工作樹:   由 $OPENCLAW_BASE_DIR 決定（repo 任意絕對路徑皆可）
                Linux 預設: $HOME/BybitOpenClaw/srv（/home/ncyu/srv ← symlink, legacy）
                Mac   範例: /Users/ncyu/Documents/Projects/TradeBot（或 $HOME/BybitOpenClaw/srv）
本地-only：     settings/（secrets）  trading_services/（runtime）
```

### 跨平台 Runtime 路徑（Mac/Linux 共用）
**Mac dev 必設**（Linux 上可選，默認 `/tmp/openclaw` + `$HOME/BybitOpenClaw/`）：
```bash
# Repo 位置（任意路徑皆可，例如 /Users/ncyu/Documents/Projects/TradeBot）
export OPENCLAW_BASE_DIR="/Users/ncyu/Documents/Projects/TradeBot"

# Runtime / socket / log 目錄（Mac /tmp 是 /private/tmp symlink，必須顯式設）
export OPENCLAW_DATA_DIR="$HOME/.openclaw_runtime"

# Secrets 根目錄（含 environment_files/ + secret_files/）
export OPENCLAW_SECRETS_ROOT="$HOME/.openclaw_secrets"

# Bybit slot base（Rust/Python 專用，= $SECRETS_ROOT/secret_files/bybit）
export OPENCLAW_SECRETS_DIR="$HOME/.openclaw_secrets/secret_files/bybit"

# 歸檔目錄（clean_restart / fresh_start 寫入）
export OPENCLAW_ARCHIVE_DIR="$HOME/.openclaw_archive"

mkdir -p "$OPENCLAW_DATA_DIR" "$OPENCLAW_SECRETS_ROOT/environment_files" \
         "$OPENCLAW_SECRETS_ROOT/secret_files/bybit" "$OPENCLAW_ARCHIVE_DIR"
```
原因：Mac `/tmp` 是 `/private/tmp` symlink 且 LaunchAgents 看到不同路徑；Mac 上跑 pytest、`restart_all.sh`、IPC socket 都必須走 `$OPENCLAW_DATA_DIR`。Linux 上不設時 fallback 到 `/tmp/openclaw` + `$HOME/BybitOpenClaw/{secrets,archive}`，行為不變。

**env var 語義速查**：
| env var | 指向 | 誰在讀 |
|---|---|---|
| `OPENCLAW_BASE_DIR` | repo 根（srv） | Rust `startup.rs` / `strategies` · Python 多處 · `start_paper_trading.sh` |
| `OPENCLAW_DATA_DIR` | runtime（sockets / logs / flags / snapshot） | Rust engine · API · scripts |
| `OPENCLAW_SECRETS_ROOT` | secrets/ 根（含 env_files + secret_files） | shell scripts（restart/clean/fresh） |
| `OPENCLAW_SECRETS_DIR` | secrets/secret_files/bybit（slot base） | Rust `bybit_rest_client` · Python `bybit_rest_client.py` · live_auth |
| `OPENCLAW_ARCHIVE_DIR` | archive（damaged_/fresh_start_ dumps） | clean_restart / fresh_start |
| `OPENCLAW_SRV_ROOT` | ⚠️ legacy alias，同 `OPENCLAW_BASE_DIR` | `bybit_path_policy.py` + 115 歷史 maintenance scripts — **新代碼請用 `OPENCLAW_BASE_DIR`**，兩者互不 fallback，Mac 部署時建議 `export` 同值 |

**Mac 差異注意**：`$HOME/.openclaw_runtime` **不會**在開機時被清（Linux `/tmp` 每次重啟清空），因此：
- `engine_maintenance.flag` 若上次異常留下會阻塞 watchdog → 開工前先 `rm -f "$OPENCLAW_DATA_DIR/engine_maintenance.flag"`
- 舊 socket 檔（`engine.sock` / `ai_service.sock`）殘留會讓新 process 拒綁 → 啟動前清或讓腳本 unlink 舊 socket
- 建議 Mac `.zshrc` 加 `alias oc-clean-runtime='rm -f "$OPENCLAW_DATA_DIR"/{*.sock,engine_maintenance.flag}'`

### 啟動檢查（每次 session 起點）
```bash
git status && git log --oneline -5
python3 helper_scripts/canary/engine_watchdog.py --data-dir "$OPENCLAW_DATA_DIR" --stale-threshold 45 --grace-period 120 --status
```
R-07 Go/No-Go 已 PASS（見 `memory/archive/project_rust_migration_status.md`）。watchdog 回 `engine_alive: false` 代表引擎沒在跑，按 TODO.md 重啟指引處理。

### TODO.md 強制規則（每次接手必須遵守）

**接手時：** 必須讀 `TODO.md` 確認當前工作狀態，找第一個 `[ ]` 未完成項作為起點。用戶有明確指令時以用戶為準。

**發現新問題時：** 立即追加到 TODO.md，不等會話結束。

**修復完成後：** `[ ]` → `[x]`，追加完成 commit 號，更新測試基準線。

---

## 七、代碼與文檔規範

### ★★ 跨平台兼容性（強制，所有開發必須遵守）

**大前提：項目必須隨時可以部署在 macOS 上運行。**

1. **路徑不硬編碼** — 所有路徑使用環境變量或 config，禁止任何 user-home 絕對路徑字面值（`/home/ncyu/`、`/Users/ncyu/`、`/Users/<name>/…/TradeBot` 等）。
   用 `os.environ.get("OPENCLAW_BASE_DIR", ...)`、docker-compose 相對路徑（`../../settings/...`），或 `Path(__file__).parent` 相對路徑。
   E2 必查：`grep -E '(/home/ncyu|/Users/[^/]+)' <diff>` 新代碼命中 → 打回（歷史 worklog / dated snapshot / 政策反例引用不在此限）。

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

### 本地 LLM 審核協作（Mac 環境，強制）

Operator 在 Mac 並行跑 Qwen3.6-35B（LM Studio）做代碼審核。CC 每完成一個任務，必寫結構化報告至：

    .claude_reports/YYYYMMDD_HHMMSS_<短描述>.md

（`.claude_reports/` 在 `.gitignore`，僅本機留存；供本地 LLM 審核 + 開發編年史 — 與 `docs/worklogs/` 職能互補：worklog 是會話時序流水，claude_report 是單任務審核單位）

**6 節必備**（中文，繁簡皆可）：
1. **任務摘要** — operator 意圖白話重述 + 完成狀態
2. **修改清單** — 逐檔 `path | 新增/修改/刪除 | 行數 | 一句話說明`
3. **關鍵 diff** — 最能說明變更的片段（非全量）
4. **治理對照** — 涉及的 DOC/SM/EX/P0 編號 + 符合 / 違反 / 未規範 / 建議修改文件
5. **不確定之處** — 未確認假設 / 跨平台風險（對照 §七.★★）/ 測試覆蓋判斷
6. **Operator 下一步** — 審查重點 / 需跑測試 / trade-core `git pull` 與重啟步驟

**Git 自動化（強制）**：
- CC 每完成一個**合理可交付單位**（任務完成 + 本節 report 已寫 + 無跑不過的測試）→ 自動 `git add` + `git commit`
- **Mac 端**：commit 後自動 `git push origin main`（operator 在 trade-core 端 `git pull` 拉取；此為同步方向）
- **CC 絕不執行**：`pull` / `merge` / `checkout` / `reset` / `rebase`（狀態變更操作留給 operator）

### Mac dev-only 模式（環境檢測 + 操作細節）

**環境檢測**：CC 從 system prompt `Platform:` 讀取，**不分大小寫**做子串比對：含 `darwin` → Mac dev-only · 含 `linux` → trade-core 生產（Linux session 實測回 `Linux`，Mac 回 `darwin`）。下面 4 條僅在 Mac 端生效，**不必詢問 operator**。

1. **pytest 必從 srv root 跑** — 部分測試用絕對 import `from program_code.…`，從 `control_api_v1/` 內跑會 `ImportError: No module named 'program_code'`（例：`test_earned_trust_engine.py`）。
2. **整合測試打真實 Bybit 會 fail —— by design** — 3 個 secret slot 已 rename 為 `*.dev_disabled_*`（避免與 Linux trade-core 撞單；還原見 README § Mac dev-only 模式）。任何 connect 真實 Bybit 的 test 拿不到 credentials → fail-closed。Mock-based unit test 不受影響。Reproduce「engine lib 1791 / 0 failed」基準需在 Linux 跑。
3. **Sub-agent (E1) 寫碼若 refuse** — Linux 端 2026-04-19「第 3 次驗證解除」refuse pattern，但跨平台/跨 session 仍偶發。Workaround：主 session 直接寫。
4. **Mac↔Linux 同步單向** — Mac → origin auto-push（per 上方規則）；Linux trade-core 由 operator 手動 `git pull`；反向（Linux 端 hotfix → Mac）由 operator 手動在 Mac `git pull`（CC 不 pull）。**啟動 Mac session 前**先確認 Linux main 無 in-flight commit，避免 push 衝突。

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
| `_BYBIT_CLIENT` / `_BYBIT_CLIENT_AVAILABLE` | strategy_ai_routes.py | 內部懶加載 `_get_rust_client()`（PYO3-ELIMINATE-1 Phase 2 後指向 `app.bybit_rest_client.BybitClient` 純 httpx；函數名為 grep-stability 保留） |
| `KLINE_MANAGER` / `INDICATOR_ENGINE` / `SIGNAL_ENGINE` / `ORCHESTRATOR` 等 12+ | strategy_wiring.py | 模組級全局，import 時初始化 |
| `_SHARED_IPC_SLOTS` / `_SHARED_SLOT_LOCK` | ipc_dispatch.py | 內部懶加載 `get_or_connect_shared_client(slot_key)`（E5-P1-5） |
| `_<AGENT>_AUDIT_CB` / `_GOV_HUB_FOR_<AGENT>` × 5（Scout/Strategist/Guardian/Analyst/Executor） | strategy_wiring.py | 模組級，由 `agent_audit_bridge.make_agent_audit_callback(...)` 構造；各 agent ctor 注入 `audit_callback`（E5-FN-3 Analyst pilot + FN-3-FUP-a~d 4 agents 補接線）。ImportError 時 GOV_HUB=None → bridge fail-open 靜默丟事件。`agent_audit_bridge` 本身無狀態工廠（不持 singleton） |

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

**Live 前置**：~~G-3 / G-5 / Phase 6~~ ✅ · ~~LIVE-GUARD-1 Rust fail-safe 補回~~ ✅（2026-04-16 深夜，三重 Mainnet 硬鎖，見 §三/§四） · ~~LIVE-GATE-BINDING-1 Python↔Rust 簽名授權綁定~~ ✅（2026-04-18，HMAC `authorization.json` + 5 min re-verify，見 §四 Gate #5） · ~~P0-9 STABILITY-1~~ ✅（停電基礎設施事件 RCA 完成，非 code bug，不重置 21d 時鐘） · demo ≥21d 穩定（P0-2，時鐘從 **2026-04-16 22:16 local** 起算 = P0-9 STABILITY-1 RCA 穩定點；PID 已多次輪替，當前 engine PID `3813984` 於 2026-04-21 13:44 CEST rebuild restart 起，計劃性 rebuild/deploy 不重置時鐘，僅 crash/hang 才重置）· provider pricing 綁定（LG-3）· API key 填入 ≠ 即可上線（Rust 側 4 項可驗證硬鎖 + Python 側 2 項門控共 5 項，全綠才真實 live）。

**關鍵文件指針**（按需 Read，不要全載入）：
- Bybit API 字典/審計：`docs/references/2026-04-04--bybit_api_reference.md` · `docs/audits/2026-04-04--bybit_api_infra_audit.md`
- 完整參考索引：`docs/CLAUDE_REFERENCE.md`

---

## 十一、一句話狀態

> 截至 2026-04-21：engine lib **1816 / 0 failed**（Mac debug；Linux release 待 `--rebuild` 驗證）+ bin 38 · pytest 全量 **2866 / 0 fail / 14 skipped** · **Live_Ready ⚠️**（門控 5 項，Rust 可驗證 4 項）· **Phase 5 PAUSED**（demo 2w 後 P0-3 重評）· **DUAL-TRACK-EXIT-1 Phase 1b Track P v2 pure fn ✅**（2026-04-21，Priority 6 接線 + `GATE1-REVERSAL-1` 下一波）· 主路徑：P0-6 intent write → P0-7 order submit → P0-2 21d demo → P0-3 edge 重評 → Live（最早 W24 末 ~2026-05-23）。活躍細節 → §三 · commit 歷史 → `docs/CLAUDE_CHANGELOG.md` · 里程碑敘述 → §三「已完成里程碑索引」+ `docs/archive/`。
