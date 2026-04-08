# OpenClaw / Bybit AI Agent 交易系統
# CLAUDE.md — 項目指令文件（核心規則 + 下一步指針）
# 最後更新：2026-04-08

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

**Phase 5 P0 ACTIVE**（2026-04-08 提前）— Edge 危機：realized ≈ 2 bps vs fee 11 bps。PH5-WIRE-0 ✅（ATR×0.2 dampening）· PH5-DL-2+JS-1 ✅（realized_edge_stats + james_stein_estimator，8 cells 全負）· PH5-WIRE-1 ✅（mode-aware cost_gate：paper/demo = exploration 模式打破循環依賴，live = fail-closed）· 5-01~03 ✅（per-param JS + k-means cluster analysis）· PH5-VERIFY-1 ⬜（7d 觀察期）。

**Runtime 硬狀態**：`demo_only` / `disabled` / `not_granted`。**Live blocker**：7d paper trading 觀察期 + 多通道告警上線。

**留尾**（非阻塞）：A2 News scheduler · W1 event_consumer 拆分 · DEAD-PY-1 完成度 P1+P2+P3+P4（唯一殘留：test_risk_view_client 1 pre-existing fail）。Phase 6 自動收縮 6-RC-1~9 規格已寫死於 TODO.md。

**歷史細節**（不要重複載入）：
- 1A→1C-4 commit 敘事 → `docs/worklogs/2026-04-08--arch_rc1_1c_history_archive.md`
- Phase 0-4 Sprint/Wave → `docs/archive/2026-04-07--claude_md_section3_history_phase0_4.md`
- 逐 commit 行數 → `docs/CLAUDE_CHANGELOG.md`
- 1C-3/1C-4 narrative → `docs/archive/2026-04-08--main_docs_1c3_1c4_narrative.md`

---

## 四、硬邊界（永遠不能違背）

```python
system_mode             = "demo_only"
execution_state         = "disabled"
execution_authority     = "not_granted"
decision_lease_emitted  = False
max_retries             = 0

# 硬錯誤：
# - should_call_ai=true 但 invocation 沒發生
# - Bybit API timeout / retCode != 0
# - execution authority 意外被授予
# - 偽造 AI 調用或交易活動
# - 自動改 live 配置 / 自動放開 execution authority
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

**當前焦點（2026-04-08 重排序 — Edge 危機）**：**(1) Phase 5 提前啟動 — DL-1/2 backtest infra + James-Stein shrinkage 整合到 cost_gate**。實證 paper realized edge ≈ 2 bps，fee 11 bps → Net EV ≈ −9 bps；cost_gate 公式 `EV = atr × conf × qty`（`intent_processor.rs:558`）把 ATR range 當 directional edge，高估 ~13×（DOGE 案例 0.052% predict vs 0.004% realized），qty 與 fee 兩邊約掉 → gate 與 size 無關。Hand-roll C+D（in-house realized-edge tracker）已被否決：跟 Phase 5 重疊 ~70%。次焦點：(2) 7d paper trading 觀察期（可與 Phase 5 並行）· (3) DEAD-PY-1 · (4) A2 News scheduler · (5) 多通道告警 (OC-3)。

**路線圖**：Phase 0-4 + ARCH-RC1 1A→1C-4 ✅ · **Phase 5 ⬜（從 W16-18 提前到立即）** · **Phase 6 (W19-20) ⬜** 漸進放權+自動收縮+壓測。

**Live 前置**：Paper trading ≥21d · Phase 6 完成 · Rust R-07 灰度通過 · Alpha PnL>0 · provider pricing 綁定。M/N 章未完成，執行權限未授予。

**關鍵文件指針**（按需 Read，不要全載入）：
- Bybit API 字典/審計：`docs/references/2026-04-04--bybit_api_reference.md` · `docs/audits/2026-04-04--bybit_api_infra_audit.md`
- 融合方案/執行計劃/ML/DB/Rust：`docs/references/2026-04-04--*` · `docs/references/2026-04-03--*` · `docs/rust_migration/README.md`
- 完整參考索引：`docs/CLAUDE_REFERENCE.md`

---

## 十一、一句話狀態

> 截至 2026-04-08（session 3）：tests engine lib 769 / Python control_api 2692 passed **1 pre-existing fail** · Phase 5 WIRE-1 ✅（mode-aware cost_gate，exploration mode 打破循環依賴）· 5-01~03 ✅（per-param JS + k-means cluster analysis）· PH5-VERIFY-1 ⬜（7d 觀察期）· Live blocker 仍在。
