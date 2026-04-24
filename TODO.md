# OpenClaw TODO — 工作清單（2026-04-24 FIX-PLAN v2 整合版）

**最後更新**：2026-04-24 16:00 CEST（FIX-PLAN v2 PM 簽核版；整合 10-agent audit + 180-220 findings）  
**簽核**：PM Approved with 6 adjustments · [Sign-off](docs/CCAgentWorkSpace/PM/workspace/reports/2026-04-24--FixPlan_v2_PMApproval.md)  
**FIX-PLAN**：[v2 完整方案](docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-24--4.24TodoAudit_FixPlan_v2.md) · [PA 核實](docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-24--4.24TodoAudit_FixPlan_v2.md#3-工作分組按執行軸) · [10 agent 提案彙整](docs/audits/2026-04-24--todo_refactor_audit.md)

**Engine**：PID **884467** · binary mtime **2026-04-24 02:06** · baseline HEAD `1a53400`（含 EDGE-DIAG-1-FUP-IPC + Phase 4 counterfactual cron；待 `--rebuild` 部署 P1-11 FIX-26-DEADLOCK-1）  
**測試基準線**：Rust engine lib **1980 passed / 0 failed** · pytest **2996**  
**健康狀態**：demo alive · 0 panics · 21d clock 起算 2026-04-16 22:16 → 目標解鎖 2026-05-07

---

## 🎯 接手三連檢查

```bash
# 1. git 狀態 + log
git status && git log --oneline -5

# 2. engine 存活 + watchdog
ssh trade-core "python3 helper_scripts/canary/engine_watchdog.py --data-dir /tmp/openclaw --status"

# 3. healthcheck 掃一遍（W1 新強制規則）
python3 helper_scripts/db/passive_wait_healthcheck.py

# 若 healthcheck FAIL：evaluate whether passive-wait prerequisite still holds
# 若 engine 掛：bash helper_scripts/restart_all.sh --engine-only --rebuild
```

---

## 🗺️ 核心路線圖（Wave 1-4 結構）

| Wave | 週次 | 日期 | 主軸 | 結束狀態 | PM 簽核 |
|---|---|---|---|---|---|
| **W1** | W17/18 | 2026-04-24~2026-05-08 | G1 scheduler 恢復 + fn 拆分 + G6 healthcheck | 基礎設施解凍 | ✅ |
| **W2** | W19 | 2026-05-08~2026-05-22 | G3 AI 接線 + G5 refactor + G4 ML pipeline + G7 量化 | AI 全連接 + 代碼合規 | ✅ |
| **W3** | W20-W23 | 2026-05-22~2026-06-12 | EDGE-DIAG Phase 3 + Phase 1b + Phase 2 shadow | 邊界穩定 + ML canary | ✅ |
| **W4** | W23-W24 | 2026-06-12~2026-06-23 | LG-2/3/4/5 + P0-3 edge 決策 + Phase 2→3 | Live Gate 簽準 → Live | ✅ |

**最早 Live**：中位 **2026-05-30** / 樂觀 ~2026-05-23 / 悲觀 ~2026-06-15（PM 簽核 +10% 緩衝建議 ~2026-06-01）  
**關鍵依賴鏈**：G1 → G3/G5 (並行) → EDGE-DIAG Phase 3 + Phase 1b → LG-2/3/4/5 → Live  
**3 大 Verified 發現**：(1) scheduler 4d 停滯 G1-01 即時 (2) PostOnly 配置正確 G1-05 簡化 (3) ExecutorAgent shadow G3-02 W2 核心

---

## 🔴 P0 — Live 阻塞關鍵路徑

### ✅ P0-13/14/15 三連 — 歸檔 2026-04-24
ATR-SCALE-BUG-1 · EDGE-ESTIMATES-MISS-1 · COST-EDGE-DEPRECATION → `docs/archive/2026-04-24--completed_todo_batch.md`

### P0-2 · LG-1 Demo 21d 觀察期 🕰️

**時鐘**：2026-04-16 22:16 local → 目標解鎖 **2026-05-07**  
**狀態**：🟡 進行中（~8d 無異常）  
**healthcheck 對應**：[0] engine_alive last 24h + [1] 0 engine_crash（CLAUDE.md §七 強制）  
**完成標準**：連續 21d 無異常火警 → P0-3 邊評觸發  
**Audit 指針**：[PM](docs/CCAgentWorkSpace/PM/workspace/reports/2026-04-24--4.24TodoAudit.md) § B.1 / [QA](docs/CCAgentWorkSpace/QA/workspace/reports/)

### P0-3 · Phase 5 策略 Edge 重評（決策點）

**狀態**：⬜ 待 P0-2 解鎖後 3 日內觸發  
**決策輸入**：counterfactual replay（EDGE-DIAG Phase 2 result）+ P1-10 邊際分析 + PostOnly 1-2w 驗證  
**outcome 分支**：
  - A. edge 翻正 → cost_gate 重啟 / Track P Phase 1b 解凍
  - B. edge 仍負 → DUAL-TRACK 全力 / Phase 5 重做 / 策略下架
  - C. edge 結構性改善（策略層調適）→ Phase 5 部分接線

**Audit 指針**：[FA](docs/CCAgentWorkSpace/FA/workspace/reports/) C-3 / [QC](docs/CCAgentWorkSpace/QC/workspace/) B.5

---

## 🟠 Wave 1（W17/18 · 2026-04-24~2026-05-08）— 基礎設施解凍

### G1 Edge 危機根源修復

| ID | 項目 | 狀態 | 前置 | 負責修/驗 | 工時 | 優先級 | 完成標準 |
|---|---|---|---|---|---|---|---|
| **G1-01** | edge_estimator_scheduler 診斷 + 恢復（4 天停滯 root cause） | ⬜ | 無 | MIT+E4 / E2 | **2h 診斷 + 1d 修復** | **🔴 P0** | `edge_estimates.json` mtime 24h fresh、cell count ≥50 |
| **G1-02** | event_consumer/mod.rs fn 1696 行拆分（硬上限 1200） | ⬜ | 無 | E1+PA / E2 | **4-5d** | **🔴 P0** | <1200 行、test coverage ≥95% |
| **G1-03** | Rust 硬違反 8 檔 refactor（bybit_rest_client/order_manager 等） | ⬜ | G1-02 | E5+E1 / E2+E4 | 2-3d | 🟠 P1 | all files <1200 lines |
| **G1-04** | fee drag / R:R 邊際驗證基線 | ⬜ | P1-10 demo | QC / FA | 1-2d | 🟠 P1 | counterfactual analysis complete |
| **G1-05** | PostOnly 配置驗證（demo=true/live=false） | ⬜ | 無 | FA+E1 / E2 | **≤0.5d** | **🔴 P0 簡化** | read TOML + design intent doc |
| **G1-06** | Drawdown auto-revoke 實裝（原則 #5） | ⬜ | 無 | E1 / E2 | 1d | 🟠 P1 | reconciler.py implement + test |

### G6 合規 + 觀察性（W1 起，W2 完成）

| ID | 項目 | 狀態 | 前置 | 負責修/驗 | 工時 | 優先級 | healthcheck |
|---|---|---|---|---|---|---|---|
| **G6-01** | passive_wait_healthcheck.py 補齊 5 缺陷 | ⬜ | 無 | E1 / QA | 1-2d | 🟠 P1 | [0-7] core checks |
| **G6-02** | 被動等待 TODO 全覆蓋 healthcheck [13-15] | ⬜ | G6-01 | PM+E1 / QA | 1d | 🟠 P1 | [13] postonly_fee_drag / [14] exit_features_rate / [15] shadow_exit_agreement |
| **G6-03** | V019/V020 retrofit Guard A（V023 postmortem） | ⬜ | 無 | E1+E2 | 1d | 🟡 P2 | migration test suite pass |
| **G6-04** | CLAUDE.md §三 敘述同步規則 | ⬜ | 無 | TW | 0.5d | 🟡 P2 | §三 ≤2 日敘述 |

---

## 🟡 Wave 2（W19 · 2026-05-08~2026-05-22）— AI 接線 + 架構合規

### G3 AI 多 Agent 接線（執行 Agent 決策鏈補全）

| ID | 項目 | 狀態 | 前置 | 負責修/驗 | 工時 | 優先級 | 完成標準 |
|---|---|---|---|---|---|---|---|
| **G3-01** | ExecutorAgent ConfigStore + IPC RFC | ⬜ | G1-02 | PA / E2 | 1d | **🔴 P0** | RFC 設計 doc + PA 簽核 |
| **G3-02** | ExecutorAgent shadow→live toggle 實裝 | ⬜ | G3-01 | E1+PA / E2+E4 | **2-3d** | **🔴 P0** | e2e test shadow→live + Rust intent receive |
| **G3-03** | Rust intent_processor IPC handler | ⬜ | G3-02 | E1 / E2+E4 | 2d | **🔴 P0** | Rust can receive Python intent IPC |
| **G3-04** | ExecutorAgent shadow→live e2e 整合 | ⬜ | G3-03 | E4 / QA | 2d | 🟠 P1 | QA 端到端驗證 pass |
| **G3-05** | EDGE-DIAG-1-FUP-SHADOW-ENABLED-IPC | ⬜ | 無 | E1+E2 | 1d | 🟡 P2（PM 升） | IPC hotpatch test |
| **G3-06** | Layer 2 自主推理升級觸發規則 | ⬜ | G3-02 | AI-E+PA / E2 | 2-3d | 🟡 P2 | L0→L1→L2 量化 criteria active |
| **G3-07** | Layer 2 工具箱補全（query_onchain 等） | ⬜ | G3-06 | E1 | 2-3d | 🟡 P3 | tool unit tests + e2e |
| **G3-08** | H1-H5 → Rust IPC Gateway | ⬜ | G3-03 | E1+PA / E2 | 3-5d | 🟡 P3 | Rust can query H1-H5 state |
| **G3-09** | cost_edge_ratio 原則 #13 演算法 | ⬜ | G3-08 | AI-E+E1 / E2 | 2d | 🟡 P3 | cost_gate active when ratio ≥ 0.8 |
| **G3-10** | STRATEGIST-PROMOTE-TRIGGER-1 | ⬜ | G3-02 | E1+E2 | 1d | 🟡 P2 | POST /api/v1/learning/strategist_promote |

### G4 ML 管線解凍

| ID | 項目 | 狀態 | 前置 | 負責修/驗 | 工時 | 優先級 | healthcheck |
|---|---|---|---|---|---|---|---|
| **G4-01** | Labels 累積加速（pooled → 200） | ⬜ | commit pending | MIT+E1 / E2 | 1-2d | 🟠 P1 | labels ≥200 pooled in DB |
| **G4-02** | run_training_pipeline 首跑 grid_trading | ⬜ | G4-01+labels≥200 | MIT / E4 | 4h | 🟠 P1 | model_registry has first ONNX |
| **G4-03** | model_registry canary rules + auto-promote | ⬜ | G4-02 | E1+E2 | 2d | 🟡 P2 | /api/v1/ml/model_promote routes active |
| **G4-04** | edge_estimator_scheduler healthcheck [13] | ⬜ | G1-01 | E1 / QA | 0.5d | 🟡 P2 | [13] freshness check in cron |
| **G4-05** | ExitConfig.shadow_enabled flip ON + 24h | ⬜ | G3-05 | PM+MIT / QA | passive 24h | 🟡 P2 | healthcheck [8] decision_shadow_exits |

### G5 架構 / 可讀性債務

| ID | 項目 | 狀態 | 前置 | 負責修/驗 | 工時 | 優先級 | 完成標準 |
|---|---|---|---|---|---|---|---|
| **G5-01** | main.rs 2062 行拆分 | ⬜ | 無 | E5+E1 / E2 | 2-3d | 🟠 P1 | main.rs <1200 lines |
| **G5-02** | live_session_routes.py 1449 行拆 | ⬜ | 無 | E5+E1 / E2 | 1-2d | 🟠 P1 | <1200 lines |
| **G5-03** | instrument_info.rs 1975 行拆 | ⬜ | 無 | E5+E1 / E2 | 1-2d | 🟠 P1 | <1200 lines |
| **G5-04** | ai_service.py 1258 行拆 | ⬜ | 無 | E5+E1 / E2 | 1d | 🟡 P2 | <1200 lines |
| **G5-05** | bb_reversion.rs 1143 行拆 sibling | ⬜ | 無 | E5 | 1h | 🟡 P3 | <1200 lines |
| **G5-06** | bybit_rest_client / order_manager / startup 等 | ⬜ | 無 | E5+E1 / E2+E4 | 5-8d 並行 | 🟡 P2 | all files <1200 |

### G7 量化 / 統計方法論（新增，共 8-10d）

| ID | 項目 | 狀態 | 前置 | 負責修/驗 | 工時 | 優先級 | 完成標準 |
|---|---|---|---|---|---|---|---|
| **G7-01** | Kelly 分級 tier boundaries 參數化 | ⬜ | 無 | QC+E1 / FA | 1d | 🟠 P1 | TOML config 50/200 dividers |
| **G7-02** | EWMA Vol lambda 參數化 | ⬜ | 無 | QC+E1 | 0.5d | 🟠 P1 | TOML per-timeframe lambda |
| **G7-03** | Hurst + Hysteresis 整合 | ⬜ | 無 | QC / FA+MIT | 2-3d | 🟠 P1 | R/S analysis + 6-period lag |
| **G7-04** | CUSUM 策略衰減監控 | ⬜ | 無 | QC+E1 | 1-2d | 🟠 P1 | σ-based slack/threshold |
| **G7-05** | cost_gate grand_mean binding | ⬜ | G1-01 | QC+E1 / FA | 2-3h | 🟠 P1 | bind when grand_mean > -50 bps |
| **G7-06** | Grid OU σ residual-based 修正 | ⬜ | 無 | QC / E1+E2 | 1d | 🟠 P1 | σ = sqrt(Σ(Δx-mean)²/n) |
| **G7-07** | Slippage / Kelly / confluence 參數化 | ⬜ | 無 | QC+E1 / FA | 2-3d | 🟠 P1 | TOML hardcoded cleanup |

---

## 🟢 Wave 3（W20-W23 · 2026-05-22~2026-06-12）— 量化驗證 + 灰度部署

### EDGE-DIAG-1 Phase 1+2+4 已完成；Phase 3 + 1b 活躍

| ID | 項目 | 狀態 | 前置 | 負責修/驗 | 工時 | 優先級 | healthcheck |
|---|---|---|---|---|---|---|---|
| **EDGE-DIAG-P3** | Phase 3 strategy-scoped Gate 1 部署 | ⬜ | Phase 1b完成 + [11]≥3d | PM+FA+QC / E2 | 2d | 🟡 MID | [11] gate auto-check |
| **EDGE-DIAG-P1b** | exit_features 累積 ≥1w（2026-04-26） | ⬜ | 無 | PM+QC / E4 | passive 7d | 🟡 MID | [14] accumulation_rate ≥threshold |
| **EDGE-DIAG-P2** | Track L shadow flip + P1-10 並行 | ⬜ | Phase 1b | QC+PM / E2 | passive 7d | 🟡 MID | [15] shadow_exit_agreement ≥95% |

### G2 策略驗證 + 決策

| ID | 項目 | 狀態 | 前置 | 負責修/驗 | 工時 | 優先級 | healthcheck |
|---|---|---|---|---|---|---|---|
| **G2-01** | P1-10 PostOnly 1-2w 驗證（passive） | ⬜ | PostOnly demo | PM+QC+FA / E4 | **≥1w 被動**（04-21~05-07） | 🟠 P1 | [3] maker_fill_rate > X% |
| **G2-02** | ma_crossover R:R 對稱性 counterfactual | ⬜ | EDGE-DIAG Phase 2 | QC+FA / E2 | 2-3d | 🟠 P1 | counterfactual output analysis |
| **G2-03** | ma_crossover SL/TP 策略定制 | ⬜ | G2-02 結果 | E1+FA / E2+E4 | 2-3d | 🟡 P2 | test backtest pass |
| **G2-04** | Grid disable 決策會 | ⬜ | G2-01 + P0-3 | PM+FA | 1h 會議 | **🔴 P0** | keep/kill decision log |
| **G2-05** | bb_breakout FIX-26-DEADLOCK-1 rebuild | ⬜ | operator rebuild | MIT / QA | 6h+ 監控 | 🟠 P1 | [12] bb_breakout fill_rate |

### G8 測試 / Healthcheck 擴展（新增）

| ID | 項目 | 狀態 | 前置 | 負責修/驗 | 工時 | 優先級 | 完成標準 |
|---|---|---|---|---|---|---|---|
| **G8-01** | e2e 認知自適應測試 | ⬜ | 無 | QA+E4 / E2 | 2-3d | 🟠 P1 | 80+ test coverage |
| **G8-02** | Python↔Rust parity test | ⬜ | 無 | QA+E4 / E2 | 1-2d | 🟠 P1 | decision agreement rate ≥95% |
| **G8-03** | 灰度驗收自動化 | ⬜ | 無 | QA / E2 | 2-3d | 🟠 P1 | production shadow metrics active |

---

## 🔵 Wave 4（W23-W24 · 2026-06-12~2026-06-23）— Live Gate + 決策

### P0-3 邊評 + LG-2/3/4/5

| ID | 項目 | 狀態 | 前置 | 負責修/驗 | 工時 | 優先級 | 完成標準 |
|---|---|---|---|---|---|---|---|
| **P0-3-01** | counterfactual_exit_replay 完整分析 | ⬜ | Phase 2 result | MIT+PM / FA | 2d | **🔴 P0** | analysis report complete |
| **P0-3-02** | edge 重評決策會（邊正/負/重做） | ⬜ | P0-3-01 | PM+FA+PA+QC | 1d 決策 | **🔴 P0** | decision vote + direction lock |
| **LG-2** | H0 Gate blocking 驗證 | ⬜ | P0-3 | E1+PM / E2 | 1d | 🔴 P0 | shadow → blocking confirm |
| **LG-3** | provider pricing 綁定 | ⬜ | P0-3 | E1 | 0.5d | 🔴 P0 | pricing table finalized |
| **LG-4** | M 章 Supervised Live Gate | ⬜ | P0-3 | E1 | 1d | 🔴 P0 | supervised mode verified |
| **LG-5** | N 章 Constrained Autonomous | ⬜ | P0-3+LG-2/3/4 | E1+PM | 0.5d | 🔴 P0 | autonomous mode confirmed |

### G9 Bybit API 精進（新增）

| ID | 項目 | 狀態 | 前置 | 負責修/驗 | 工時 | 優先級 | 完成標準 |
|---|---|---|---|---|---|---|---|
| **G9-01** | Bybit API 字典更新 | ⬜ | 無 | BB+E1 | 2h | 🟡 P2 | dictionary sync |
| **G9-02** | WS 容錯強化 | ⬜ | 無 | BB+E1 / E2 | 1-2h | 🟡 P2 | handler not found reconnect |

---

## 📚 已完成歸檔索引

| 日期 | 歸檔路徑 | 批次 | 行數 |
|---|---|---|---|
| 2026-04-24 | `docs/archive/2026-04-24--todo_v1_refactor_snapshot.md` | v1 重構版（本 session 稍早完成） | 328 |
| 2026-04-24 | `docs/archive/2026-04-24--todo_snapshot_pre_refactor.md` | v0 原始版（舊完整版） | 700 |
| 2026-04-24 | `docs/archive/2026-04-24--completed_todo_batch.md` | P0-13/14/15 三連 | — |
| 2026-04-23 | `docs/archive/` | DEDUP-PY-RUST + INFRA-PREBUILD-1 系列 | — |
| 更早 | `docs/archive/` | 見各批次歷史歸檔檔 | — |

**當前 TODO 版本**：v2 FIX-PLAN 整合版（2026-04-24，包含 180-220 findings，6 Wave 工作組）

---

## ⚙️ 工作流程速查

```
E1/E1a 並行（≤5）→ E2 審查（強制）→ E4 回歸（強制）→ PM 確認 → commit + push
被動等待 TODO 必附 healthcheck（CLAUDE.md §七新規則）
詳見 CLAUDE.md §八 · 16 Agent 定義 docs/CLAUDE_REFERENCE.md
```

**Bybit API 開發必查**：`docs/references/2026-04-04--bybit_api_reference.md`

**風控參數修改**：必須透過 IPC `patch_risk_config` 單一通道  

**部署三件套**：  
```
改了代碼需部署              → bash helper_scripts/restart_all.sh --rebuild
只想清交易所持倉             → bash helper_scripts/clean_restart.sh --yes
開發告一段落要清 PnL         → bash helper_scripts/fresh_start.sh --yes
```

**Mac↔Linux SSH bridge**：  
```
ssh trade-core "cd ~/BybitOpenClaw/srv && git log --oneline -5"  # 查 Linux repo 狀態
ssh trade-core "python3 helper_scripts/canary/engine_watchdog.py --status"  # 查 engine 狀態
ssh trade-core "bash helper_scripts/restart_all.sh --rebuild"  # 遠端部署
```


---

## 🔵 P1 — 當週活躍（跨 Wave 1-3）

### DUAL-TRACK-EXIT-1（主軸 W19-W27+）

- **✅ Phase 1a 完成 2026-04-21**：T1-T5 骨架 + v2 + T4 wiring + P1-7 A/B
- **🟡 Phase 1b（W3）**：exit_features 累積 ≥1w（2026-04-19 起算，2026-04-26 滿週）+ 7 維度閾值 bind + counterfactual audit
  - 前置：Phase 1a complete + ≥1w exit_features 數據
  - healthcheck：[14] exit_features_accumulation_rate ≥閾值
  - 負責：MIT+QC / E2
  - 工時：7d passive + 2d audit
- **⬜ Phase 2（W3-W4）**：Track L shadow flip + P1-10 並行驗證
  - 前置：Phase 1b 結果
  - healthcheck：[15] shadow_exit_agreement_phase2 ≥95%
  - 負責：QC+PM / E2+E4
  - 工時：7d passive + 2d tuning
- **⬜ Phase 3（W4-W5）**：Track L 灰度 + ml_override_high 下調
  - 前置：Phase 2 gate
  - 負責：FA+QC / E2
  - 工時：7d灰度 + 3d tuning

### P1-6 · DEMO-BYBIT-SYNC-ORPHAN-1（被動觀察）

- **狀態**：🟡 被動等待（起算 2026-04-17，1w 觀察）
- **描述**：6 倉位 bybit_sync 策略；P1-8 FUP `retriage_synthetic_owner` tick-level 自主接管
- **healthcheck**：[2] synthetic_owner_retriage 接管成功（row count > baseline）
- **完成標準**：1w 期間 synthetic_owner 無 duplication
- **Audit 指針**：[PM audit](docs/CCAgentWorkSpace/PM/workspace/reports/) § B.5

### P1-10 · STRATEGY-ASYMMETRY-1（已納入 G2）

- 已納入 Wave 3 G2-01 被動驗證

### P1-11 · BB-BREAKOUT-DORMANT-1（Phase 1 完成，待 rebuild）

- **✅ (2)+(3) DonchianMode/BbBreakoutProfile enum** 完成 2026-04-24
- **✅ (1) Phase 1 信號級 sweep** 完成 2026-04-24
- **✅ FIX-26-DEADLOCK-1 bug fix** 完成 2026-04-24（commit `63957ad`）
- **⬜ 待 `--rebuild` 部署**
- **後置 Phase 2 backlog**：sweep fee model / persistence+cooldown 模擬 / Rescale seed / Python SQUEEZE_EXPIRY_BARS / bb_reversion sibling
- **healthcheck**：[12] bb_breakout_post_deadlock_fix fill rate recover
- **Audit 指針**：[QC](docs/CCAgentWorkSpace/QC/workspace/) / [MIT](docs/CCAgentWorkSpace/MIT/workspace/)

### P1-7 · ML 訓練管線（Phase 1 C 部分合入 G4）

- Labels 累積加速已納入 G4-01
- run_training_pipeline 首跑已納入 G4-02
- model_registry canary 已納入 G4-03

### P1 其他項（簡化）

| ID | 項目 | 狀態 | 完成標準 |
|---|---|---|---|
| P1-8 FUP DUST-EVICTION-GAP-1 | 🟡 被動觀察滿 1w | DUST-EVICTION log-only 無新動作 |
| P1-13 SAMPLE-FLOOR-GAP | ✅ 已決策 | Phase 1a 限 grid_trading pooled；其他策略延後 ≥1000 RT |
| P1-14 EDGE-ESTIMATE-BIND | ⬜ 待 G1-01 | grand_mean > -50 bps ∧ ≥2 策略 shrunk>0 |

---

## 🟢 P2 — 下週 / Live Gate / QoL（跨 Wave 2-4）

### P2 高優先項

| ID | 項目 | 狀態 | 工時 | 前置 | 負責 | healthcheck |
|---|---|---|---|---|---|---|
| **P2-01** | EDGE-DIAG-1-FUP-IPC（✅ 完成） | ✅ | — | — | FA verified | [4] IPC hotpatch confirmed |
| **P2-02** | EDGE-DIAG-1-FUP-SHADOW-ENABLED-IPC（升 P2）| ⬜ | 1d | Phase 3 前 | G3-05 | [8] shadow_exit writing |
| **P2-03** | STRATEGIST-PERSIST-AUDIT-GAP-COUNTER-1 | ⬜ | 1d | G3-02 | E1+E2 | [5] strategist audit counter >0 |
| **P2-04** | STRATEGIST-TUNE-TARGET-CONFIG-1 | ⬜ | 1d | G3-02 | E1 | [6] strategist target firing |
| **P2-05** | STRATEGIST-HISTORY-OBSERVABILITY GUI | ⬜ | 0.5d | backend live | E1a | [7] history dashboard endpoint |
| **P2-06** | counterfactual_exit_replay Linux deploy | ⬜ | 1d | operator | MIT | [9] replay output fresh |

### Live Gate（W4 最後檢查）

| # | 項目 | 狀態 | 前置 | 負責 |
|---|---|---|---|---|
| **LG-2** | H0 Gate blocking 驗證（shadow → blocking） | ⬜ | P0-3 | E1+PM |
| **LG-3** | provider pricing 綁定 | ⬜ | P0-3 | E1 |
| **LG-4** | M 章 Supervised Live Gate | ⬜ | P0-3 | E1 |
| **LG-5** | N 章 Constrained Autonomous | ⬜ | LG-2/3/4 | E1+PM |

### AI Layer 補遺

| # | 項目 | 狀態 | 前置 | 負責 | 優先級 |
|---|---|---|---|---|---|
| **G-7** | ClaudeTeacher 啟用（consumer_loop.rs） | ⬜ | 21d demo + G-3 | E1 | P2 Phase 2+ |
| **G-10** | Calibration.py 整合（ECE < 0.05） | ⬜ | run_training_pipeline | MIT+E1 | P2 Phase 3+ |
| **LLM-ABC-MIGRATION-1** | ✅ 2026-04-20 完成（BLOCKER FA 驗） | ✅ | — | — | — |

### QoL & 設計債

| # | 項目 | 狀態 | 優先級 |
|---|---|---|---|
| **QoL-2** | Demo AI cost 追蹤（依 G3-08） | ⬜ | P2 |
| **DUST-EVICTION GUI** | 已 P1-8 log-only 觀察中 | 🟡 passive | QoL |
| **LEARNING-COCKPIT-NO-IPC** | Learning 8 端點走 Python state_store | ⬜ | P2 design debt |

---

## ⚪ P3 — 中期（Wave 2-4 後）

| # | 項目 | 狀態 | 前置 | 優先級 |
|---|---|---|---|---|
| **STRATEGIST-AUTO-PROMOTE** | 自動晉升規則（可選，默認關） | ⬜ | P2-01 | P3 |
| **EDGE-P2 Phase B** | Liquidation signal + OI confluence | ⬜ | EDGE-P2-2 Phase A ✅ | P3 |
| **EDGE-P2-3 Phase 2+** | live endpoint 啟用；funding_arb PostOnly；ML integration | ⬜ | Phase 1b | P3 |
| **Phase 5 補強** | Symbol Embedding / Regime LSTM / JS+Scorer / correlation_pairs | ⬜ | P0-3 判決 | P3-P4 |
| **G-2 FundingArb 重評** | 三參數重評（待 R-02 Strategist） | ⬜ | G-2 launch | P3 |
| **ORPHAN-ADOPT-1 Phase 2B** | 前置 G-1 R-02 | ⬜ | G-1 stub fill | P3 |

---

## ⚫ P4 — Backlog / Conditional

| # | 項目 | 狀態 | 觸發條件 | 優先級 |
|---|---|---|---|---|
| **IP-DEDUP-1** | IntentProcessor 去抖 | ⬜ | P0-3 判決後 edge 仍負 + 重發率高 | P4 |
| **4-06** | LinUCB live warm-start | ⬜ | v1→v2 遷移 | P4 |
| **OC-4** | MCP PostgreSQL 自然語言查詢 | ⬜ | Phase 5+ | P4 |
| **G-6** | Edge JS 滾動重訓（P1-7 B 解後） | ⬜ | Phase 5+ | P4 |
| **G-8** | cost_gate 可信度評估（EDGE-P3） | ⬜ | EDGE-P3-1 Stage 2 | P4 |
| **4-Conditional** | PairsTrading / Beta Hedging / Kalman / Mac遷移 / Jump detection | ⬜ | post-live | P4 |

---

## 🔍 Gap 索引

| Gap | 描述 | Wave | 狀態 |
|---|---|---|---|
| **G-1** | AI Agent 5 stub（Conductor 剩 stub） | W2 G3 | 🟡 |
| **G-2** | FundingArb 三參數待 R-02 重評 | P3 | 🔵 |
| **G-3/5/9** | IPC auth / Rate Limit / HMAC | — | ✅ |
| **G-4** | Cookie secure=False | W4 LG | ⬜ |
| **G-6** | ML edge 噪音（P1-7 B 解後自然解） | W3 G4 | ⬜ |
| **G-7** | ClaudeTeacher consumer_loop | W3 G4 | ⬜ |
| **G-8** | cost_gate 可信度 | P3 | ⬜ |
| **G-10** | Calibration.py isotonic | W3 G4 | ⬜ |
| **G-11** | dust silent drift（P1-8） | — | ✅ FUP 觀察中 |
| **G-12** | 微利退場（DUAL-TRACK） | W1-W4 | 🟢 |

---

## 📊 Healthcheck 監控清單（CLAUDE.md §七 新強制規則）

**被動等待 TODO 必附 healthcheck**（每 6h cron 檢查）。若連續 3 次 FAIL 中止被動等待，轉人工介入。

### 強制 Healthcheck（已實裝）

| Check # | 項目 | SQL / 檢查 | PASS 條件 | 失效影響 |
|---|---|---|---|---|
| **[0]** | engine_alive | last PID activity last 24h | true | engine hang → 重啟 |
| **[1]** | engine_crash | COUNT crash logs last 24h | = 0 | multiple crash → RCA |
| **[2]** | synthetic_owner_retriage | row count growth | > baseline | P1-6 stalled |
| **[3]** | postonly_fee_drag_baseline | maker fill rate | > X% + fee drop ≥60% | G2-01 驗證失效 |
| **[4]** | IPC_hotpatch_working | IPC last applied ts | within 5min | G3-05 dead |

### 新增 Healthcheck（W1 補齊）

| Check # | 項目 | SQL / 檢查 | PASS 條件 | 失效影響 | 來源 |
|---|---|---|---|---|---|
| **[13]** | edge_estimator_scheduler | edge_estimates.json mtime | < 24h old + n_cells ≥50 | G1-01 / G4-04 失效 | G6-02 新增 |
| **[14]** | exit_features_accumulation_rate | weekly row count growth | ≥閾值 | EDGE-DIAG Phase 1b 緩 | G6-02 新增 |
| **[15]** | shadow_exit_agreement_phase2 | Python vs Rust decision agree rate | ≥95% | EDGE-DIAG Phase 2 失效 | G6-02 新增 |

### 其他 Healthcheck（被動等待 / 監控）

| Check # | 項目 | 對應 Wave TODO | 監控頻率 |
|---|---|---|---|
| **[5]** | strategist_audit_counter | P2-03 | 每 1h |
| **[6]** | strategist_target_firing | P2-04 | 每 6h |
| **[7]** | history_dashboard | P2-05 | 每 6h |
| **[8]** | decision_shadow_exits | G4-05 | 每 6h |
| **[9]** | counterfactual_replay_fresh | P2-06 | 每 12h |
| **[10]** | model_registry_freshness | G4 canary | 每 24h |
| **[11]** | edge_diag_phase3_gate | EDGE-DIAG-P3 | 每 6h（決策）|
| **[12]** | bb_breakout_post_deadlock | G2-05 | 每 6h |

---

## 📝 會話操作指引

### Session 起手三連

```bash
# 1. Sync local → remote
git fetch --prune origin
if git log --oneline -1 | grep -v "$(git rev-parse origin/main | cut -c1-7)"; then
  git pull --ff-only origin main
fi

# 2. Check engine status
ssh trade-core "python3 helper_scripts/canary/engine_watchdog.py --status"

# 3. Healthcheck scan
python3 helper_scripts/db/passive_wait_healthcheck.py --check all

# If any FAIL: evaluate whether passive-wait prerequisite still holds
```

### Session 完成三連

```bash
# 1. Stage + commit
git add docs/CCAgentWorkSpace/PM/workspace/reports/2026-04-24--FixPlan_v2_PMApproval.md
git commit -m "PM Sign-off FIX-PLAN v2 + approve 6 adjustments"
git push origin main

# 2. Archive old TODO
cp TODO.md docs/archive/2026-04-24--todo_v1_refactor_snapshot.md
git add docs/archive/2026-04-24--todo_v1_refactor_snapshot.md TODO.md
git commit -m "Archive TODO v1 + adopt v2 FIX-PLAN integration (500-800 lines, G1-G9)"
git push origin main

# 3. Sync to Linux
ssh trade-core "cd ~/BybitOpenClaw/srv && git pull --ff-only origin main"
```

