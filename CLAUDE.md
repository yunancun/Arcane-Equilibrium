# OpenClaw / Bybit AI Agent 交易系統
# CLAUDE.md — 項目指令文件（核心規則 + 下一步指針）
# 最後更新：2026-04-14

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

**Runtime**：`Live_Ready` ✅ — 所有前置阻隔已移除。Live 上線唯一條件：`settings/secret_files/bybit/live/{api_key,api_secret}` 配置 + `OPENCLAW_ALLOW_MAINNET=1`。execution_authority 在 live session start 自動授予。Live 縮倉監控：5min 輪詢，≥5% 警告，≥15% 自動撤權+平倉+凍結 GovernanceHub。

**權威原則**：Rust `openclaw_engine` = paper/demo/live 三引擎並行唯一引擎（ARCH-RC1 1C-4 + 3E-ARCH）。Rust ConfigStore 為所有交易/風控/學習/預算參數權威，4 IPC 寫入面 → tick-level hot-reload。**禁止 restart-to-apply**。Guardian = RiskConfig 純派生視圖。Python 無交易邏輯（DEAD-PY-2 清除 ~4500 行後）。

**進行中/阻塞**：
- **Phase 5 PAUSED**（2026-04-12 reframe）— PNL-FIX-1/2 清理後所有活躍策略 gross edge 為負（net -$2775）；cost_gate/DL/JS 機械已接線但需真實正 edge。**下一步**：策略重做（G-SR-1 / Strategist agent / 新信號邏輯）。詳見 `memory/project_phase5_promotion_edge_crisis.md`。
- **ENGINE-HEAL 部署留尾**：Fix 1-4（panic hook / crash-only / WS stale self-cancel 120s / watchdog 4 道保險）已 merge，運行中引擎仍 pre-fix binary。operator 需 `restart_all.sh --rebuild` 部署。**FUP-1 ✅ systemd user unit 正式結清**（2026-04-15）。**FUP-2/3**（TODO.md 事故 follow-up）：live pipeline lagging 上游根因 ✅ + FIX-PHASE1 合併；`engine_results.jsonl` 111GB 滾動或關閉 ✅ 折入 FIX-PHASE1。
- **非阻塞留尾**：W1 event_consumer 拆分；D-02 PriceEvent metadata HashMap 移除。

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

**歷史細節指針**（不要重複載入）：
- §三 2026-04-15 之前完整敘述 → `docs/archive/2026-04-15--claude_md_section3_snapshot.md`
- 1A→1C-4 commit 敘事 → `docs/archive/2026-04-08--arch_rc1_1c_history_archive.md`
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

**當前焦點（2026-04-10 審計後更新）**：10 個架構 gap 全部入計劃（TODO.md Gap 索引）。
- **W19（04-14~18）**：G-3 IPC 認證 + G-5 Rate Limiting + OC-3 多通道告警 + 6-RC-6 ✅
- **W20（04-21~25）**：SEC-04/06/13 E3 審查 + G-9 HMAC 確認 + WP-CC(FS-1/BI-1/P9/SM-1) + 6-01~03 漸進放權 ✅
- **W21（04-28~05-02）**：6-04~08 ✅ · 6-09~13 Phase 6 PM 驗收 ✅；LG-1 21d paper 到期（05-01）
- **W22（05-05~09）**：G-1 R-02 AI Agent（Strategist/Guardian）+ G-2/OC-5 FundingArb + LG-2/3
- **W23（05-12~16）**：G-1 R-06 全 5 agent + G-7 ClaudeTeacher + G-10 Calibration + LG-4/5 Live

**關鍵路徑**：`~~G-3 → OC-3 → 6-RC-6 → 6-01~13~~ ✅ → LG-1(05-01) → LG-2 → LG-4 → Live`
**最早 Live 日期**：W23 末（～2026-05-16）

**路線圖**：Phase 0-5 ✅ · Live GUI P0~P6 ✅ · **Phase 6 (W19-21) ✅** 自動降級 ✅ · 告警 ✅ · 漸進放權 ✅ · 壓測+驗收 ✅ · PM 端到端 ✅ · **AI 治理層 (W22-W23) ⬜**（H1-H5 AI agent 目前全 stub）。

**Live 前置**：Paper trading ≥21d · ~~G-3 IPC 認證~~ ✅ · ~~G-5 Rate Limiting~~ ✅ · ~~Phase 6 驗收~~ ✅ · provider pricing 綁定。API key 填入即可上線（所有代碼阻隔已移除）。

**關鍵文件指針**（按需 Read，不要全載入）：
- Bybit API 字典/審計：`docs/references/2026-04-04--bybit_api_reference.md` · `docs/audits/2026-04-04--bybit_api_infra_audit.md`
- 融合方案/執行計劃/ML/DB/Rust：`docs/references/2026-04-04--*` · `docs/references/2026-04-03--*` · `docs/rust_migration/README.md`
- 完整參考索引：`docs/CLAUDE_REFERENCE.md`

---

## 十一、一句話狀態

> 截至 2026-04-15：tests engine lib **1285** + core **372** + e2e **35** = **1692** Rust passed **0 fail** · Python **2852** passed · **ENGINE-HEAL 4 Fix ✅** + 已部署（11:13 rebuild + restart）· **engine_watchdog systemd user unit ✅** `openclaw-watchdog.service` Restart=always + linger=yes（FUP-1 正式結清，跨重啟存活）· **G-2 FundingArb 監控 daemon ACTIVE** PID 598572，等 demo ≥20 fills 自動寫 `docs/audits/2026-04-15--g2_funding_arb_clean_edge.md`（接手先 `cat /tmp/openclaw/g2_monitor.progress.json`）· **EDGE-P3-1 Phase A/A5/A6 ✅ + Phase B #1/#2/#5 ✅ + PA #63 parquet_etl ETL ✅ + Step 7a ✅ (commit `d73addb`)**（Rust-direct writer + passthrough IPC：`DecisionFeatureSnapshot` 於 gate 頂端發射，Stage 0 即寫 `learning.decision_features`；Phase B 3/5；Step 7b-7f 5 條餘項獨立可推；Stage 2+ 現唯一 blocker = ML-MIT 首 ONNX）· **WP-F/UX-07~10 / QoL-1/3 / ORPHAN-ADOPT-1 P1 / OC-5 FundingArb / G-SR-1 / Edge 隔離 ✅** · **Phase 5 PAUSED** · **Live_Ready ✅** · **下一步**：G-2 daemon 完成（~17h ETA）→ audit → 升 R-02 · LG-1 21d · Phase 2 Adopt 等 G-1 R-02 Strategist · ML-MIT #26 訓練首個 ONNX 解鎖 Stage 2+ · EDGE-P3-1 Step 7b-7f 可並行。
