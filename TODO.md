# OpenClaw TODO — 工作清單（2026-04-24 10-Agent Audit 重構版）

**最後更新**：2026-04-24（10 agent 獨立 audit + PA FIX-PLAN + PM Sign-off 後重構；舊 TODO 700 行歸檔 → `docs/archive/2026-04-24--todo_snapshot_pre_refactor.md`）
**簽核**：PM Approved with 6 minor adjustments · [Sign-off](docs/CCAgentWorkSpace/PM/workspace/reports/2026-04-24--FixPlan_PMApproval.md)
**Audit 索引**：[2026-04-24--todo_refactor_audit.md](docs/audits/2026-04-24--todo_refactor_audit.md) · 10 agent 報告 + FIX-PLAN

**Engine**：PID **884467** · binary mtime **2026-04-24 02:06** · baseline HEAD `1a53400`（含 EDGE-DIAG-1-FUP-IPC + Phase 4 counterfactual cron；**P1-11 FIX-26-DEADLOCK-1 + RUST-DOUBLE-PREFIX-1 + SCHED-PAPER-ORPHAN 等待 `--rebuild` 部署**）
**測試基準線**：Rust engine lib **1980 passed / 0 failed** · bin 38 · e2e 35 · reconciler_e2e 19 · pytest **2996** passed
**健康**（post-rebuild 2026-04-23）：demo alive · paper disabled · live not alive（auth 未簽預期）· 0 panics
**21d demo 時鐘**：起算 2026-04-16 22:16 local → 目標 2026-05-07 解鎖 → P0-3 邊評 3d 內

---

## 🎯 接手三連檢查

```bash
# 1. 引擎存活 + canary + 崩潰數
python3 helper_scripts/canary/engine_watchdog.py --data-dir /tmp/openclaw --stale-threshold 45 --grace-period 120 --status
grep -c "ENGINE_CRASH" /tmp/openclaw/watchdog.log 2>/dev/null || echo "0 crashes"

# 2. git 狀態
git status && git log --oneline -5

# 3. healthcheck 掃一遍（被動等待 TODO 必附 healthcheck — CLAUDE.md §七）
python3 helper_scripts/db/passive_wait_healthcheck.py

# 引擎掛 → bash helper_scripts/restart_all.sh --engine-only --rebuild
```

---

## 🗺️ 核心路線圖（Wave 結構）

| Wave | 週次 | 日期 | 主軸 | 結束狀態 |
|---|---|---|---|---|
| **W1** | W17/18 | 4/24-4/30 | G1 scheduler 恢復 + event_consumer 拆分 + G6 健康檢查補齊 | 基礎設施解凍 |
| **W2** | W19 | 5/1-5/7 | G3 AI 接線 + G5 refactor + G4 ML pipeline 熱啟 | AI 全連接 + 代碼結構合規 |
| **W3** | W20-W23 | 5/8-5/23 | EDGE-DIAG Phase 3 + Phase 1b FUP + Phase 2 shadow | 邊界穩定 + ML canary |
| **W4** | W23-W24 | 5/19-5/30 | LG-2/3/4/5 + P0-3 決策 + Phase 2 → Phase 3 | Live Gate 簽準 → Live |

**最早 Live**：W24 末（~2026-05-23 樂觀 / ~2026-05-30 中位 / ~2026-06-15 悲觀）
**關鍵依賴鏈**：G1 → G3/G5 (並行) → EDGE-DIAG Phase 3 + DUAL-TRACK Phase 1b → LG-2/3/4/5 → Live

---

## 🔴 P0 — 阻塞 Live Gate 關鍵路徑

### ✅ P0-13/14/15 三連 — 歸檔 2026-04-24

ATR-SCALE-BUG-1 · EDGE-ESTIMATES-MISS-1 · COST-EDGE-DEPRECATION — `docs/archive/2026-04-24--completed_todo_batch.md`

### P0-2 · LG-1 Demo 21d 觀察期 🕰️
- **時鐘**：2026-04-16 22:16 local → 目標解鎖 **2026-05-07**
- **狀態**：🟡 進行中（~8d 無異常）
- **Audit 指針**：[PM](docs/CCAgentWorkSpace/PM/workspace/reports/2026-04-24--4.24TodoAudit.md) · [QA](docs/CCAgentWorkSpace/QA/workspace/reports/2026-04-24--4.24TodoAudit.md)
- **FIX-PLAN**：[§5](docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-24--4.24TodoAudit_FixPlan.md#5-關鍵路徑--時序)
- **healthcheck 配對**：`passive_wait_healthcheck.py` engine_alive last 24h + 0 engine_crash（CLAUDE.md §七 強制）
- **負責**：被動觀察 · PM 日常檢查

### P0-3 · Phase 5 策略 Edge 重評（決策點）
- **狀態**：⬜ 待觸發
- **觸發條件**：P0-2 解鎖後 **3 日內**（**事件驅動，非 hard date** — PM Sign-off 調整 3）
- **決策輸入**：counterfactual replay（EDGE-DIAG Phase 2）+ P1-10 邊際分析 + PostOnly 1-2w 驗證
- **Audit 指針**：[FA](docs/CCAgentWorkSpace/FA/workspace/reports/2026-04-24--4.24TodoAudit.md) · [QC](docs/CCAgentWorkSpace/QC/workspace/reports/2026-04-24--4.24TodoAudit.md) · [MIT](docs/CCAgentWorkSpace/MIT/workspace/reports/2026-04-24--4.24TodoAudit.md)
- **outcome 分支**：
  - A. edge 翻正 → cost_gate 重啟 / Track P Phase 1b 解凍
  - B. edge 仍負 → DUAL-TRACK 全力 / Phase 5 重做 / 策略下架

---

## 🟠 Wave 1（W17/18 · 4/24-4/30）— 基礎設施解凍

### G1. Edge 危機根源修復

| ID | 項目 | 狀態 | 前置 | 負責修/驗 | 工時 | 並行 |
|---|---|---|---|---|---|---|
| **G1-01** | edge_estimator_scheduler 診斷 + 恢復（4 天停滯 root cause） | ⬜ P0 | 無 | MIT / E4 | 2h | ✅ |
| **G1-02** | event_consumer/mod.rs `run_event_consumer()` fn 拆分（1696 行單 fn） | ⬜ P0 | 無 | E1 + PA / E2 | **3-4d** (PM 調整 1) | 與 G1-01 並行；PA/E1 緊密同 session |
| **G1-03** | Rust 硬違反 8 檔 refactor（event_consumer 拆後） | ⬜ P1 | G1-02 | E5 + E1 / E2+E4 | 2-3d | G1-02 完成後並行 |
| **G1-04** | fee drag / R:R 邊際驗證（基準線） | ⬜ P1 | P1-10 PostOnly 部署（已 2026-04-21 demo） | QC / FA | 8h | 獨立軌道 |
| **G1-05** | PostOnly 配置反向 bug 核實與修（FA 發現 demo=false/live=true） | ⬜ P0 | 讀 `settings/strategy_params_{demo,live}.toml` | FA + E1 / E2 | 0.5d | 立即 |

- **Audit**：[MIT 報告](docs/CCAgentWorkSpace/MIT/workspace/reports/2026-04-24--4.24TodoAudit.md) · [E5 報告](docs/CCAgentWorkSpace/E5/workspace/reports/2026-04-24--4.24TodoAudit.md) · [FA 報告](docs/CCAgentWorkSpace/FA/workspace/reports/2026-04-24--4.24TodoAudit.md)
- **FIX-PLAN**：[§3 G1](docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-24--4.24TodoAudit_FixPlan.md#3-工作分組按執行軸)
- **完成標準**：edge_estimator_scheduler 24h fresh · event_consumer <1200 行 · Rust 8 檔合規 · PostOnly 配置正向（demo=true, live=false）

### G2. 策略層改造（獨立軌道，跨 Wave 1-2）

| ID | 項目 | 狀態 | 前置 | 負責修/驗 | 工時 |
|---|---|---|---|---|---|
| **G2-01** | P1-10 PostOnly 1-2w 驗證（被動觀察 counterfactual cross-check） | 🟡 P1 | PostOnly demo 已部署 | PM + QC + FA / E4 | passive 1-2w (PM 調整 5) |
| **G2-02** | ma_crossover R:R 對稱性 counterfactual 驗證 | ⬜ P1 | EDGE-DIAG Phase 2 replay 結果 | QC + FA / E2 | 2-3d |
| **G2-03** | ma_crossover SL/TP 策略層定制（Option B） | ⬜ P2 | G2-02 驗證結果 | E1 + FA / E2+E4 | 2-3d |
| **G2-04** | Grid disable 決策（若 PostOnly 後 gross edge 仍負） | ⬜ P0 | G2-01 結果 | PM + FA 決策 | 1h 會 |
| **G2-05** | bb_breakout FIX-26-DEADLOCK-1 `--rebuild` 部署驗證 | ⬜ P1 | operator rebuild | MIT / QA [12] healthcheck | 6h+ 監控 |

- **Audit**：[QC 報告](docs/CCAgentWorkSpace/QC/workspace/reports/2026-04-24--4.24TodoAudit.md) · [FA 報告](docs/CCAgentWorkSpace/FA/workspace/reports/2026-04-24--4.24TodoAudit.md)
- **FIX-PLAN**：[§3 G2](docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-24--4.24TodoAudit_FixPlan.md)
- **完成標準**：策略層決策全閉合（grid keep/kill、ma R:R ≤1.5×、bb_breakout 復活或正式 disable）

### G6. 合規 + 觀察性（W1 部分；W2 完成）

| ID | 項目 | 狀態 | 前置 | 負責修/驗 | 工時 |
|---|---|---|---|---|---|
| **G6-01** | `passive_wait_healthcheck.py` 補齊 5 缺陷（QA 發現） | ⬜ P1 | 無 | E1 / QA | 1-2d |
| **G6-02** | 「被動等待 TODO 必附 healthcheck」全覆蓋（CLAUDE.md §七） | ⬜ P1 | G6-01 | PM + E1 / QA | 1d |
| **G6-03** | V019/V020 retrofit Guard A（V023 postmortem 規範） | ⬜ P2 | 無 | E1 + E2 | 1d |
| **G6-04** | CLAUDE.md §三 TODO 敘述同步規則（Lessons） | ⬜ P2 | 無 | TW | 0.5d |

- **Audit**：[QA 報告](docs/CCAgentWorkSpace/QA/workspace/reports/2026-04-24--4.24TodoAudit.md) · [CC 報告](docs/CCAgentWorkSpace/CC/workspace/reports/2026-04-24--4.24TodoAudit.md)

---

## 🟡 Wave 2（W19 · 5/1-5/7）— AI 接線 + 架構合規

### G3. AI 多 Agent 接線（ExecutorAgent 決策鏈補全）

| ID | 項目 | 狀態 | 前置 | 負責修/驗 | 工時 |
|---|---|---|---|---|---|
| **G3-01** | ExecutorAgent ConfigStore + IPC RFC（architecture design） | ⬜ P0 | G1-02 完成 | PA / E2 | 1d |
| **G3-02** | ExecutorAgent shadow→live toggle 實裝（IPC patch_executor_config） | ⬜ P0 | G3-01 RFC | E1 + PA / E2+E4 | 2-3d |
| **G3-03** | Rust `intent_processor` 接收 Python intent 的 IPC handler | ⬜ P0 | G3-02 | E1 / E2+E4 | 2d |
| **G3-04** | ExecutorAgent shadow→live e2e 整合測試 | ⬜ P1 | G3-03 | E4 / QA | 2d |
| **G3-05** | EDGE-DIAG-1-FUP-SHADOW-ENABLED-IPC（shadow_enabled 熱重載）★ 優先級 P3→P2（PM 調整 4） | ⬜ P2 | 無 | E1 + E2 | 1d |
| **G3-06** | Layer 2 autonomous 升級觸發規則（L0→L1→L2 量化 criteria） | ⬜ P2 | G3-02 | AI-E + PA / E2 | 2-3d |
| **G3-07** | Layer 2 工具箱補全（`query_onchain` / `check_derivatives`） | ⬜ P3 | G3-06 | E1 | 2-3d |
| **G3-08** | H1-H5 → Rust IPC Gateway（Rust tick pipeline 享受 H1-H5 閘） | ⬜ P3 | G3-03 | E1 + PA / E2 | 3-5d |
| **G3-09** | `cost_edge_ratio` 原則 #13 演算法實裝 | ⬜ P3 | G3-08 | AI-E + E1 / E2 | 2d |
| **G3-10** | STRATEGIST-PROMOTE-TRIGGER-1（手動 API + IPC） | ⬜ P2 | G3-02 | E1 + E2 | 1d |

- **Audit**：[AI-E 報告](docs/CCAgentWorkSpace/AI-E/workspace/reports/2026-04-24--4.24TodoAudit.md) · [CC 報告](docs/CCAgentWorkSpace/CC/workspace/reports/2026-04-24--4.24TodoAudit.md) · [PA 報告](docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-24--4.24TodoAudit.md)
- **FIX-PLAN**：[§3 G3](docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-24--4.24TodoAudit_FixPlan.md)
- **完成標準**：ExecutorAgent shadow→live 完整契約 · 5-Agent→Rust intent 流暢 · H1-H5 對 Rust 生效 · cost_edge_ratio 可計算

### G4. ML 管線解凍

| ID | 項目 | 狀態 | 前置 | 負責修/驗 | 工時 |
|---|---|---|---|---|---|
| **G4-01** | Labels 累積加速（per-strategy pooled，PM 調整 6） | ⬜ P1 | commit pending `PipelineConfig.symbol` Optional | MIT + E1 / E2 | 1-2d |
| **G4-02** | `run_training_pipeline.py` 首跑 grid_trading pooled（產首個 ONNX） | ⬜ P1 | G4-01 + labels ≥200 pooled | MIT / E4 | 4h |
| **G4-03** | model_registry canary rules 實裝 + 自動晉升 | ⬜ P2 | G4-02 輸出第一筆 row | E1 + E2 | 2d |
| **G4-04** | `edge_estimator_scheduler` healthcheck [13] 文件新鮮度 | ⬜ P2 | G1-01 | E1 / QA | 0.5d |
| **G4-05** | `ExitConfig.shadow_enabled` flip ON + 24h 觀察 | ⬜ P2 | G3-05 FUP-SHADOW-IPC | PM + MIT / QA [8] | passive 24h |

- **Audit**：[MIT 報告](docs/CCAgentWorkSpace/MIT/workspace/reports/2026-04-24--4.24TodoAudit.md)
- **完成標準**：首個 ONNX artifact · registry 有 rows · shadow exit 開始寫 `learning.decision_shadow_exits`

### G5. 架構 / 可讀性債務

| ID | 項目 | 狀態 | 前置 | 負責修/驗 | 工時 |
|---|---|---|---|---|---|
| **G5-01** | main.rs 2062 行 + bootstrap 拆分 | ⬜ P1 | G1-02 | E5 + E1 / E2 | 2-3d |
| **G5-02** | live_session_routes.py 1449 行拆分 | ⬜ P1 | 無 | E5 + E1 / E2 | 1-2d |
| **G5-03** | instrument_info.rs 1975 行拆分 | ⬜ P1 | 無 | E5 + E1 / E2 | 1-2d |
| **G5-04** | ai_service.py 1258 行拆分 | ⬜ P2 | 無 | E5 + E1 / E2 | 1d |
| **G5-05** | bb_reversion.rs 1143 行拆 sibling（E5-P2-4c 延續） | ⬜ P3 | 無 | E5 | 1h |
| **G5-06** | bybit_rest_client.rs / order_manager.rs / startup.rs / resting_orders.rs / risk_config.rs 硬違反 | ⬜ P2 | 無 | E5 + E1 / E2+E4 | 5-8d 全部 |

- **Audit**：[E5 報告](docs/CCAgentWorkSpace/E5/workspace/reports/2026-04-24--4.24TodoAudit.md)
- **完成標準**：所有 Rust / Python 檔 <1200 行（§九 硬上限合規）

---

## 🟢 P1 — 當週活躍（跨 Wave 1-3）

### EDGE-DIAG-1（Phase 1+2+4 + FUP-IPC 完成；Phase 3 待）

- **已完成**：Phase 1 commit `5cabfd9` · Phase 2 post-P013 clean +11.95 bps · Phase 4 daily cron · FUP-IPC（commits `5b0908b` + `1a53400`）
- **Phase 3（strategy-scoped Gate 1 fallback 部署）**：⬜ 待 4 項前提（PM 調整 2 補 (d)）
  - (a) post-P013-clean bucket ≥200 rows pooled
  - (b) per-strategy bootstrap 95% CI lo > 0
  - (c) orphan_frozen clean ≥20 rows
  - **(d) healthcheck [11] 連續 PASS ≥3 天**（PM 新增）
- **Audit 指針**：[QC](docs/CCAgentWorkSpace/QC/workspace/reports/2026-04-24--4.24TodoAudit.md) · [PA](docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-24--4.24TodoAudit.md)
- **healthcheck**：`passive_wait_healthcheck.py [11]` auto-gate（~2026-05-01 ETA）

### DUAL-TRACK-EXIT-1（主軸 W19-W27+）

- **✅ Phase 1a**：T1-T5 骨架 + v2 + T4 wiring + P1-7 A/B 完成 2026-04-21
- **🟡 Phase 1b** (W24)：
  - `exit_features` 累積 ≥1w（2026-04-19 起算，2026-04-26 滿週）
  - 7 維度閾值 bind 真實數據
  - Counterfactual replay audit（Linux 執行）
- **⬜ Phase 2** (W25)：Track L shadow flip + P1-10 並行（見 G2）
- **⬜ Phase 3** (W26-W27)：Track L 灰度 + `ml_override_high` 下調
- **⬜ Phase 4** (W28+)：週 retraining cron + canary（registry 骨架 ready）
- **Audit 指針**：[PA](docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-24--4.24TodoAudit.md) · [MIT](docs/CCAgentWorkSpace/MIT/workspace/reports/2026-04-24--4.24TodoAudit.md)
- **QA 守衛**：每策略 <1000 RT → P-only · 禁 random split · hold-out 5-10% · Brier score · Feature drift 報警 · IPC rollback

### P1-7 C · Labels pooled 訓練（已合入 G4-01/02）

### P1-10 · STRATEGY-ASYMMETRY-1（已合入 G2-01~04）

### P1-11 · BB-BREAKOUT/REVERSION DORMANT（已合入 G2-05）

- **Phase 2 backlog**（priority sorted，待 FIX-26 deploy 後 1w 觀察）：
  1. F3 leak-free 大樣本（30-60d × 20+ symbols）真實重驗
  2. sweep 加 fee model (round-trip 11 bps taker)
  3. sweep 加 persistence + cooldown 模擬
  4. Rescale Conservative/Aggressive profile 種子值為 1m-realistic
  5. Python `SQUEEZE_EXPIRY_BARS` 改 derive from MS
  6. bb_reversion 拆 sibling + enum 改造

### 其他 P1 項（簡化）

- **P1-6** DEMO-BYBIT-SYNC-ORPHAN：P1-8 FUP 自主接管觀察一週（起算 2026-04-17，週末解除）
- **P1-13** SAMPLE-FLOOR-GAP：已決策 Phase 1a 限 grid_trading pooled；其他策略延後至 ≥1000 RT
- **P1-14** EDGE-ESTIMATE-BIND：當前 grand_mean=-45.73 不達 bind；G1-01 恢復後重跑

---

## 🔵 P2 — 下週 / Live Gate / QoL（跨 Wave 2-3）

### P2 高優先項

| ID | 項目 | 狀態 | 工時 | 前置 | 負責 |
|---|---|---|---|---|---|
| **P2-01** | EDGE-DIAG-1-FUP-IPC（✅ commit `1a53400` 已完成） | ✅ | — | — | FA verified |
| **P2-02** | EDGE-DIAG-1-FUP-SHADOW-ENABLED-IPC（PM 調整 4 升 P2） | ⬜ | 1d | Phase 3 前 | 見 G3-05 |
| **P2-03** | STRATEGIST-PERSIST-AUDIT-GAP-COUNTER-1（Phase 5+ 硬依賴） | ⬜ | 1d | G3-02 | E1 + E2 |
| **P2-04** | STRATEGIST-TUNE-TARGET-CONFIG-1 | ⬜ | 1d | G3-02 | E1 |
| **P2-05** | STRATEGIST-HISTORY-OBSERVABILITY GUI tab | ⬜ | 0.5d | backend 已 live | E1a |
| **P2-06** | `counterfactual_exit_replay.py` Linux 部署 7d 跑 | ⬜ | 1d | operator Linux sub-agent | MIT |

### Live Gate（W24）

| ID | 項目 | 狀態 |
|---|---|---|
| **LG-2** | H0 Gate blocking 驗證（shadow → blocking） | ⬜ |
| **LG-3** | provider pricing table 正式綁定 | ⬜ |
| **LG-4** | M 章 Supervised Live Gate | ⬜ |
| **LG-5** | N 章 Constrained Autonomous Live | ⬜ |
| **G-4 / SEC-21** | Cookie `secure=True`（HTTPS 部署後） | ⬜ |

### AI Layer 補遺

- **G-7** ClaudeTeacher 啟用（`consumer_loop.rs enabled=false`，前置 21d demo + G-3）
- **G-10** Calibration.py 整合（isotonic → `run_training_pipeline.py` ECE < 0.05）
- ✅ **LLM-ABC-MIGRATION-1** 2026-04-20 完成（BLOCKER FA 額外驗證：call-site 0 `import OllamaClient`）

### QoL & 設計債

- **QoL-2** Demo AI cost 追蹤（依 G3-08 H1-H5 → Rust gateway）
- **DUST-EVICTION GUI 曝光**（P1-8 FUP）：log-only 觀察滿一週
- **LEARNING-COCKPIT-NO-IPC-1**：Learning 8 端點走 Python state_store（設計債）

### Session 2026-04-23 Review Follow-up

所有 ✅ 已完成項（QC-2/3 / FA-1/2 / E4-1/2/3/4/5 / STRATEGIST-PARAMS-PERSIST-1 / SCHEDULER-SHUTDOWN-PRIMITIVE-1 / IPC-SERVER-TESTS-SPLIT-1 / RUST-DOUBLE-PREFIX-1 / STRATEGIST-SCHED-CHANNEL-PAPER-ORPHAN-1 / RESTART-ALL-UVICORN-LOG-1 / EDGE-SCHEDULER-LEADER-1 / SCHEDULER-FAILURE-OBSERVABILITY-1）→ 歸檔索引

---

## ⚪ P3 — 中期

- **STRATEGIST-AUTO-PROMOTE-CRITERIA-1**（可選，operator 預設關）
- **EDGE-P2-2 Phase B Liquidation signal**（Phase A OI 已 2026-04-20 完成）
- **EDGE-P2-3 Phase 2+ (c)**：live endpoint 啟用 · funding_arb 接 PostOnly · learning integration
- **Phase 5 補強**：Symbol Embedding / Regime LSTM / JS + Scorer / correlation_pairs（待 P0-3 判決）
- **G-2 FundingArb 三參數重評**（待 R-02 Strategist 上線）
- **ORPHAN-ADOPT-1 Phase 2B**（前置 G-1 R-02）

---

## ⚫ P4 — Backlog / Conditional

- **IP-DEDUP-1** IntentProcessor 去抖（觸發：P0-3 判決後 edge 仍負 + 重發率高）
- **4-06** LinUCB live warm-start（首次 v1→v2 遷移）
- **OC-4** MCP PostgreSQL 自然語言查詢
- **G-6** Edge JS 滾動重訓（P1-7 B 解阻塞後自然解）
- **G-8** cost_gate 可信度評估（EDGE-P3-1 Stage 2）
- **4-Conditional**：4-1 PairsTrading / 4-2 Beta Hedging / 4-3 Kalman / 4-5 Mac Studio 遷移 / 4-10 Jump detection
- **2-11** actual training（與 P1-7 C 同源）
- **WP-F/E4/E5/I 技術債**（詳 `docs/audits/2026-04-06--consolidated_remediation_report.md`）

---

## 🔍 Gap 索引

| Gap | 描述 | 所屬 Wave | 狀態 |
|---|---|---|---|
| G-1 | AI Agent 5 stub（Conductor 剩 stub） | W2 G3 | 🟡 |
| G-2 | FundingArb 三參數待 R-02 重評 | P3 | 🔵 |
| G-3/5/9 | IPC auth / Rate Limit / HMAC | — | ✅ |
| G-4 | Cookie secure=False | W4 LG | ⬜ |
| G-6 | ML edge 噪音（P1-7 B 解後自然解） | W3 G4 | ⬜ |
| G-7 | ClaudeTeacher consumer_loop | W3 G4 | ⬜ |
| G-8 | cost_gate 可信度 | P3 | ⬜ |
| G-10 | Calibration.py isotonic | W3 G4 | ⬜ |
| G-11 | dust silent drift（P1-8） | — | ✅ FUP 觀察中 |
| G-12 | 微利退場（DUAL-TRACK） | W1-W4 | 🟢 |

---

## 📚 已完成歸檔索引

| 日期 | 歸檔路徑 | 批次 |
|---|---|---|
| 2026-04-24 | `docs/archive/2026-04-24--completed_todo_batch.md` | P0-13/14/15 三連 · P1-11 Phase 1 · EDGE-DIAG 1+2+4 |
| 2026-04-23 | `docs/archive/` | DEDUP-PY-RUST A+B+C+D · INFRA-PREBUILD-1 A+B · E5 觀測性 · STRATEGIST 系列 |
| 2026-04-22 | `docs/archive/2026-04-22--step_0_derived_todo_batch.md` | TRACK-P-V2-SWAP-1 · TICK-PIPELINE-MOD-SPLIT-1 等 |
| 2026-04-21 | `docs/archive/2026-04-21--completed_todo_batch.md` | TRACK-P-T4-WIRING-1 主軸 + 14 項 |
| 2026-04-20 | `docs/archive/2026-04-20--completed_todo_batch.md` | Step 0 Sprint · P1-7 A/B · Track P T1-T5 · PYO3-ELIMINATE-1 |
| 更早 | `docs/archive/` | 見各批次歸檔檔 |

**舊 TODO 完整快照**：`docs/archive/2026-04-24--todo_snapshot_pre_refactor.md`（700 行，重構前狀態）

---

## ⚙️ 工作流程速查

```
E1/E1a 並行（≤5）→ E2 審查（強制）→ E4 回歸（強制）→ PM 確認 → commit + push
詳見 CLAUDE.md §八 · 16 Agent 定義 docs/CLAUDE_REFERENCE.md
```

**Bybit API 開發必查**：`docs/references/2026-04-04--bybit_api_reference.md`
**風控參數修改**：必須透過 IPC `patch_risk_config` 單一通道
**被動等待 TODO**：必附 `passive_wait_healthcheck.py` check（CLAUDE.md §七）

**部署三件套**：
```
改了代碼需部署              → bash helper_scripts/restart_all.sh --rebuild
只想清交易所持倉             → bash helper_scripts/clean_restart.sh --yes
開發告一段落要清 PnL/勝率    → bash helper_scripts/fresh_start.sh --yes
臨時停機 debug              → bash helper_scripts/stop_all.sh
```

**SSH bridge（Mac → Linux）**：`ssh trade-core "<cmd>"`（Tailscale + key auth，免密碼）
