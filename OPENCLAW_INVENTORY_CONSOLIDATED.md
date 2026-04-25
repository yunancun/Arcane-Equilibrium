# OpenClaw 系統盤點統合報告（5-Session Consolidated Inventory）

> **整合對象**：2026-04-24 ~ 2026-04-25 五個 Mac CC Session 的盤點產出
> **原始來源**：[`.claude_reports/inventory_{1a,1b,2,3,4}_*.md`](.claude_reports/) + [`session_{1..5}_summary.md`](.claude_reports/)
> **產出時間**：2026-04-25
> **整合者**：Mac CC Session 5/5 收官
> **覆蓋規模**：~357 個產品向模組（Rust+Python）/ ~215,720 LOC / 10 條端到端資料流 / 16 條根原則 / 6 類風險熱點 / Top 5 紅色清單

---

## 目錄（Table of Contents）

**統合導讀**
- [0. 前言](#0-前言preface)
- [1. 統合摘要](#1-統合摘要executive-summary)
- [2. 紅色清單 Top 5](#2-紅色清單-top-5live-上線前優先處理項)
- [3. Operator 建議](#3-operator-建議)
- [4. 跨 Session 重要觀察](#4-跨-session-重要觀察)
- [5. 各 Session「最不確定的 5 件事」彙總](#5-各-session最不確定的-5-件事彙總)

**正文 — 各 Session 詳細產出**
- [Part 1A — Rust 模組清單（Session 1）](#part-1a--rust-模組清單session-15)
- [Part 1B — Python 模組清單（Session 2）](#part-1b--python-模組清單session-25)
- [Part 2 — 端到端資料流地圖（Session 3）](#part-2--端到端資料流地圖session-35)
- [Part 3 — 16 條根原則治理對照（Session 4）](#part-3--claudemd-二-16-條根原則治理對照session-45)
- [Part 4 — 風險熱點與紅色清單（Session 5）](#part-4--風險熱點清單與紅色清單session-55)

**附錄**
- [附錄 A — 各 Session 摘要原文](#附錄-a--各-session-摘要原文)

---

## 0. 前言（Preface）

### 0.1 盤點背景與目的

OpenClaw 走到 2026-04-25 已具備完整 5-Agent + 3-Engine（paper/demo/live_demo）+ Rust hot path 架構，但歷次 P0/P1 揭發顯示「紙面治理」與「實際代碼」之間存在多處 silently drifted 的 gap（如 G1-01 edge_estimator 4 天停滯、verified finding 3 ExecutorAgent shadow hardcoded、PostOnly TOML 反向）。為避免 Live 階段才在事後 RCA 中暴露這些風險，operator 在 2026-04-24 啟動了**系統性 5-Session 盤點**，要求對全部 Rust + Python 產品向模組做一次自頂向下的審查，輸出可追蹤、可審計、可帶入下一階段工作的「知識地圖」。

### 0.2 5-Session 結構

| Session | 主題 | 主要交付物 | 行數估計 |
|---|---|---|---|
| 1/5 | Rust 模組地圖 | [`inventory_1a_rust_modules.md`](.claude_reports/inventory_1a_rust_modules.md) | 308 行 / 7 批 |
| 2/5 | Python 模組地圖 | [`inventory_1b_python_modules.md`](.claude_reports/inventory_1b_python_modules.md) | 302 行 / 13 批 |
| 3/5 | 端到端資料流地圖 | [`inventory_2_data_flows.md`](.claude_reports/inventory_2_data_flows.md) | 984 行 / 8 必含 + 2 額外 |
| 4/5 | 16 條根原則治理對照 | [`inventory_3_governance_audit.md`](.claude_reports/inventory_3_governance_audit.md) | 724 行 / 16 主節 |
| 5/5 | 風險熱點 + 紅色清單 + 收官 | [`inventory_4_risk_hotspots.md`](.claude_reports/inventory_4_risk_hotspots.md) + 本統合報告 | 328 行 / 6 類熱點 + Top 5 紅色 |

每個 Session 同時產出對應 `.claude_reports/YYYYMMDD_HHMMSS_inventory_session_N_summary.md` 摘要，記錄當次最不確定的 5 件事 + 給下 Session 的 hint。

### 0.3 本統合文件結構

- **§1–5（統合導讀）**：跨 5 Session 提煉，給沒時間讀完整 ~3,750 行原始產出的讀者快速進入。
- **Part 1A–4（正文）**：5 份原始 inventory 文件全文按 Session 順序串接，保留每張表格與 file:line 引用。
- **附錄 A**：5 份 Session summary 全文，給想看原作者「自承不確定」的讀者。

---

## 1. 統合摘要（Executive Summary）

### 1.1 涵蓋規模

| 平面 | 模組數 | LOC（產品向）| 備註 |
|---|---|---|---|
| **Rust**（openclaw_types + openclaw_core + openclaw_engine）| ~180 `.rs`（含 test）| **131,120** | 7 個 batch；test ~15k / prod ~116k |
| **Python**（app + ml_training + local_model_tools + helper_scripts + observer_pipeline + io_and_persistence + audit）| ~177 個（13 個 batch） | **~84,600** | stub ~1,520（local_model_tools 14 stub）+ 真實 ~83k |
| **總計** | **~357 個** | **~215,720** | 不含 .toml / .sql / static / docs / scripts |

10 條完整資料流（8 必含 + scanner cycle + news pipeline）均到「步驟編號 + file:line + 持久化點 + 斷鏈點」級別。

### 1.2 16 條根原則治理 gap 分布

| Gap 嚴重度 | 條數 | 條目編號 |
|---|---|---|
| **無 gap** | 0 | — |
| **僅輕微 gap（設計合理）** | 4 | #1, #2, #4, #16 |
| **部分 gap（需 watch）** | 6 | #5, #7, #8, #9, #11, #14 |
| **嚴重 gap（已知 P0/P1 觸碰）** | 6 | #3, #6, #10, #12, #13, #15 |

**meta-gap 跨條樞紐 1 個**：RiskConfig + ConfigStore ArcSwap（同時承擔 #2/#4/#5/#6/#11/#16 共 6 條原則）。
**治理盲區 5 個**：A audit chain 須對齊到 PG / B 熱重載一致性 / C 雙源 byte-identical 驗證 / D 主動推進 cadence audit / E GUI 寫入面 hot/cold 制度化。

### 1.3 三大跨 Session 重大發現（Top 3 Surprise）

#### 發現 1：Session 4 嚴重 gap 與 Session 5 熱點 100% 重合

6 個 Session 4 嚴重 gap 模組（ExecutorAgent / PostOnly / edge_estimates / change_audit_log / fast_track / RiskConfig）**全部**同時是 Session 5 風險熱點。**沒有「治理是紙面、代碼是另一回事」的脫節**——治理 gap 就是代碼風險集中區。意味 operator 不需要在「修代碼」與「補治理」之間選；修紅色清單 Top 5 就同時關閉 8 條原則的 gap。

#### 發現 2：`change_audit_log.py` 全文 0 個 `INSERT INTO`

Session 3 標「⚠️ DB 表名未驗」原以為是 sub-agent 漏 grep；Session 4 重新 grep 全 `srv/` 確認**為負**——Python 的 `change_audit_log.py` + `audit_persistence.py` **真的**沒有任何 PG 寫入，全靠 in-memory + JSONL。`governance.change_audit` 表名可能根本不存在於 schema。如果 operator 對「Python agent audit 已寫 PG」有任何隱性假設（例如「事故重建可以從 PG 拉到 agent log」），這個假設**不成立**。Live 階段一次 5-Agent 路徑事故，重建就只能靠 in-memory（重啟後 0 行）+ JSONL（可能已輪轉）。

#### 發現 3：`local_model_tools/` 27 檔中 14 檔是 stub，仍被多處 import 為 fallback

Session 2 第 10 批揭露 14 個 stub（KlineManager / IndicatorEngine / SignalEngine / Orchestrator / IndicatorBase 等），全部 `compute()` 回 None / 空 list / zero qty。Rust 真實實作已接管，但 `strategy_read_routes.py` / `strategy_ai_routes.py` / `scanner_rate_limiter.py` 仍 import stub 作 fallback。**這意味 strategy_wiring.py 的 12+ singleton 中有 5+ 個是「有 type 但無實作」的 placeholder**——任一 stub 被誤改為「半實作」會讓 Rust 真實實作與 Python stub 同 import 點雙寫。Operator 可能以為這些 stub 已可安全刪除，但 deletion 會破壞下游 wiring：必須先重構 stub-import 站點，再刪 stub。

### 1.4 六維風險熱點 Top 模組速覽

| 類別 | 評選標準 | Top 1 / 最高頻 |
|---|---|---|
| 1. **複雜度熱點** | 行數 proxy + 非測試 + 多職責 | `main.rs` 2062 行（**遠超 §九 1200**）+ `passive_wait_healthcheck.py` **1822 行** |
| 2. **耦合熱點** | fan-in 最高 + 跨流共享狀態 | **`RiskConfig + ConfigStore ArcSwap`** — 6 條根原則共用樞紐 |
| 3. **沉默熱點** | critical path × 「無對應測試/未直接驗證/推測」 | **`change_audit_log.py` + `audit_persistence.py` 0 個 `INSERT INTO`**（grep 已驗為負） |
| 4. **新鮮熱點** | 30 天 commit 數最高 production code | `paper_trading_routes.py` 67 commit + `pipeline_bridge.py` 63 commit |
| 5. **歷史熱點** | CLAUDE.md §三 P0/P1 編號出現次數 | **`edge_estimator_scheduler.py` + `edge_estimates.rs`** — G1-01 / EDGE-DIAG-1 / LEARNING-PIPELINE-DORMANT-1 / P1-7 B 多重觸碰 |
| 6. **邊界熱點** | Rust↔Python IPC + 系統↔Bybit + 系統↔DB | **Bybit REST**（`bybit_rest_client.rs` 1725 行 + `order_manager.rs` 1554 行）跨 Bybit edge |

唯一在三類熱點同時命中的條目：**`edge_estimates.json` startup-only 熱重載**（沉默 + 歷史 + 邊界），是 Live 上線前優先級最高的單點修復。

---

## 2. 紅色清單 Top 5（Live 上線前優先處理項）

排序原則：「如果不處理就上 live 會怎樣」，不基於「容易處理」。重 Live 階段直接後果（資金安全 / 治理鏡頭 / 監控失靈）。

### 紅色 #1：ExecutorAgent shadow hardcoded（治理鏡頭破洞）

**風險描述**：Python 5-Agent 框架 ExecutorAgent `_shadow_mode=True` 寫死，永遠寫 audit log 不發 IPC `submit_order`。Operator 看 audit 以為 agent 在工作，實際下單路徑 = Rust hot path 完全繞過 Lease 機制。

- **涉及**：[executor_agent.py:482](srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/executor_agent.py:482) + [strategy_wiring.py:467](srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/strategy_wiring.py:467)
- **資料流**：流 7（Agent audit）+ 流 1（tick → order）
- **觸碰原則**：#3 AI ≠ 即時命令、#15 多 Agent 協作
- **建議處理**：啟動 G3-02 Wave 2 重構（CLAUDE.md §三 已標目標），設計 ExecutorAgent shadow→live 切換 + IPC `submit_order` 必須經 SM-02 lease，與 Rust hot path lease-id 雙寫對賬。
- **估計工作量**：8–12 人日

### 紅色 #2：edge_estimates.json startup-only 熱重載

**風險描述**：scheduler 4d stall 已驗為治理事件（G1-01）；即使 scheduler 修復，engine 不重啟就用舊 1-cell HashMap。Live 階段 stale `edge_estimates.json` → cost_gate fallback ATR×conf×0.2 → 全策略持續低 edge 但無告警 → 學習鏈完全斷。

- **涉及**：[edge_estimates.rs:387](srv/rust/openclaw_engine/src/edge_estimates.rs) + [edge_estimator_scheduler.py:716](srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/edge_estimator_scheduler.py)
- **資料流**：流 5（Learning → cost_gate）
- **觸碰原則**：#6 失敗默認收縮、#7 學習 ≠ 改寫 Live、#12 持續進化（**三原則同時觸碰**）
- **建議處理**：`edge_estimates.rs` 加 IPC `reload_edge_estimates` method（類似 EDGE-DIAG-1-FUP-IPC 7 個 `exit.*` 欄位的模式），Python scheduler 寫完 atomic rename 後立即透過 IPC 通知 Rust 熱重載，ETT < 60s。
- **估計工作量**：3–5 人日

### 紅色 #3：Python agent audit 無 PG 持久化

**風險描述**：`change_audit_log.py` + `audit_persistence.py` 全文 0 個 `INSERT INTO`（grep 驗）。所有 5-Agent decision/state event 只在 in-memory list + JSONL；重啟丟記憶體 list；JSONL 滾出後 audit 也丟。原則 #8「每筆交易必須可重建」在 Python agent 路徑根本不滿足。

- **涉及**：[change_audit_log.py:160](srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/change_audit_log.py) + [audit_persistence.py:549](srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/audit_persistence.py)
- **資料流**：流 7（Agent audit）+ 流 4（Guardian 風控）
- **觸碰原則**：#8 交易可解釋、#15 多 Agent 協作
- **建議處理**：新增 V025 migration `governance.agent_audit_log` 表（同 V014 schema 模式）；`change_audit_log.record_change()` 內加 PG INSERT + JSONL 雙寫；先 grep 確認沒有「另一檔讀 in-memory list 寫 PG」的隱藏 audit consumer。
- **估計工作量**：4–6 人日

### 紅色 #4：PostOnly TOML 反向 + RiskConfig 樞紐多原則風險

**風險描述**：`strategy_params_demo.toml` PostOnly=false / `_live.toml` PostOnly=true——**demo 不收縮、live 偏激進**，違反「失敗默認收縮」字面意。RiskConfig 為 6 條原則共用樞紐，TOML 直編輯無 V014 audit；任一配置反向 silently 失守多原則。

- **涉及**：`strategy_params_{paper,demo,live}.toml` + [risk_config.rs:908](srv/rust/openclaw_engine/src/config/risk_config.rs) + [config/store.rs:837](srv/rust/openclaw_engine/src/config/store.rs)
- **資料流**：流 1+4（cost_gate + Guardian 共用 RiskConfig）
- **觸碰原則**：#6 失敗默認收縮（直接違反）+ #2/#4/#5/#11/#16（樞紐間接觸碰）
- **建議處理**：立即修 PostOnly：demo=true / live=false；ConfigStore.patch() 後加 invariant 自動檢查 hook（純記憶體 < 1ms）；TOML 直編輯路徑加 git pre-commit hook 對 `strategy_params_*.toml` / `risk_config.toml` 啟用 invariant linter；CLAUDE.md §三 加「多原則樞紐改動需 PA + FA + PM 三角 review」。
- **估計工作量**：1–2 人日修 PostOnly + 3–4 人日加 invariant linter & pre-commit hook = 4–6 人日

### 紅色 #5：fast_track.rs Guardian 旁路設計風險（FA-PHANTOM-1 復發風險）

**風險描述**：fast_track 是設計性 Guardian 旁路（緊急閃崩/保證金時不經 Guardian veto 直接全平）。memory `project_fa_phantom_bug.md` 記錄「90% 閾值＜100% 設計上限」歷史 bug，root cause 是把 notional/balance 當 margin_util。雖已修，但設計風險仍在——未來新增閃崩規則仍可能誤觸全平所有策略。

- **涉及**：[fast_track.rs:407](srv/rust/openclaw_engine/src/fast_track.rs)
- **資料流**：流 1（tick → order，Step 0 fast_track）
- **觸碰原則**：#4 策略不能繞過風控、#5 生存 > 利潤
- **建議處理**：fast_track 觸發次數加獨立 metric；fast_track 內加 sanity check「margin_util 實際值在 0–1 範圍才視為 valid」（防 notional/balance 誤代）；增加雙閾值規則「fast_track 單次最大平倉 ratio 上限（如 50%），ratio 超出時退回 Guardian 路徑」。
- **估計工作量**：2–3 人日

### 紅色清單 Top 5 工作量總計

| 紅色 # | 風險主題 | 觸碰原則 | 工作量（人日） |
|---|---|---|---|
| 1 | ExecutorAgent shadow hardcoded | #3 + #15 | 8–12 |
| 2 | edge_estimates startup-only 熱重載 | #6 + #7 + #12 | 3–5 |
| 3 | Python agent audit 無 PG | #8 + #15 | 4–6 |
| 4 | PostOnly 反向 + RiskConfig 樞紐 | #6 + #2/#4/#5/#11/#16 | 4–6 |
| 5 | fast_track Guardian 旁路防呆 | #4 + #5 | 2–3 |
| **總計** | — | **8 條原則覆蓋** | **21–32 人日** |

**並行性分析**：5 項中 #1 與 #4 高度耦合（Lease enforcement 與 RiskConfig invariant 都涉及樞紐），建議串行；其餘 3 項（#2 / #3 / #5）可並行。最佳順序：**#4（1d 修 PostOnly 立即可上）→ #5（防呆獨立）→ #2（IPC 熱重載）→ #3（PG audit）→ #1（最大重構）**。理性 Live 上線時間估算：1 個工程師 5–7 週；2 工程師並行 3–4 週。

---

## 3. Operator 建議

### 3.1 填寫理解度的時間規劃

**建議：8–12 小時，分 3 段**

- **4h**：Session 1+2（357 個模組）— 只填理解度欄位，不寫備註，按表中 batch 順序快速掃過
- **2h**：Session 3（10 條資料流）— 填理解度 + 標註自己最熟/最陌的 step（最熟的 1–2 條留作他日 mob session 教材）
- **2–4h**：Session 4（16 條原則）— 填運行時信任度（高/中/低）；如果填「低」就跳到 Session 5 紅色清單對照
- **2h**：Session 5（六類熱點 + 紅色清單）— 重點填**沉默熱點 Top 10 的理解度**（這是 operator 最可能不知道自己不知道的區）

完成後產出 1 個總結 issue：「我熟悉度 ≤2 的模組共 N 個」 — 這是 mob session 候選。

### 3.2 修紅色清單的兩波分批

**第一波（Live 上線前必修，~4–6 人日）**：
- 紅 #4 PostOnly 反向（1 人日修 + 3 人日 invariant linter）— 最快 ROI，TOML 一改可立即 ship
- 紅 #5 fast_track 防呆（2 人日 metric + sanity check）— 預防 FA-PHANTOM-1 復發

**第二波（Live demo 階段並行修，~12–18 人日）**：
- 紅 #2 edge_estimates IPC 熱重載（3 人日）— 解決 G1-01 復發風險
- 紅 #3 Python agent audit PG（4 人日）— 補治理盲區
- 紅 #1 ExecutorAgent shadow 重構（8 人日）— **最大改動，建議放在 Live demo 21d 觀察期內動**

**理由**：紅 #4+#5 是 Live 上線前的「不修就立即出事」風險；紅 #1 是 Live 階段的「治理鏡頭」風險，但 Rust hot path 已實質下單，重構期可同時 demo 跑（雙保險）；紅 #2+#3 是「治理可審計性」風險，Live 出事時的 RCA 能力鍵 — 在 Live demo 期跑進去比 Live 啟動後再追補便宜。**不建議延後到 Live 之後**：5 項中除 #1 外，其餘 4 項在 Live 第一週內任一誤觸都會直接影響資金安全或診斷能力。

### 3.3 立刻提出修改 DOC/EX 治理文件的 3 條

1. **CLAUDE.md §二 加新原則衍生：「跨平面橋必熱重載 < 60s」**（治理盲區 §3.B）
   - 為什麼：edge_estimates startup-only 是「學習平面 → Live 平面」單向跨橋無熱重載；如果 §二 沒明文，下次新增類似橋（例如 ml/registry 上線時）會重蹈覆轍
   - 改寫位置：原則 #6（失敗默認收縮）下衍生「Config drift detect」實施準則

2. **CLAUDE.md §二 加新原則衍生：「audit chain 任一路徑必達 PG」**（治理盲區 §3.A）
   - 為什麼：Python agent audit 在 Python 平面不到 PG，原則 #8「可重建」靠 PG 串接；§二 字面只說「可解釋」沒說「PG 必達」
   - 改寫位置：原則 #8 下衍生「audit row 24h count > 0 healthcheck 強制」

3. **CLAUDE.md §三 加「多原則樞紐改動需 PA + FA + PM 三角 review」**（meta-gap top 1 對應）
   - 為什麼：RiskConfig 6 原則樞紐當前任一改動只走一般 review；TOML 直編輯（PostOnly verified finding 2）即多原則 silently 失守
   - 改寫位置：§三 「三大 Verified 發現」結尾加新衍生規範

EX 治理文件（DOC-08 / DOC-01 / EX-XX）暫不需立改，§二 + §三 改完已涵蓋。

---

## 4. 跨 Session 重要觀察

### 4.1 治理 gap × 代碼熱點完美重合

從 Session 4 找出「有 gap」的根原則對應模組，檢查是否同時出現在 Session 5 風險熱點：

| Session 4 識別的 Gap 模組 | 同時出現在 Session 5 熱點 # | 上 live 前優先 |
|---|---|---|
| **`executor_agent.py:482`（原則 #3 + #15 嚴重 gap）** | [5] 歷史熱點 #2 | **是** — Wave 2 重構未啟動 |
| **`strategy_params_{demo,live}.toml` PostOnly 反向（原則 #6）** | [5] 歷史熱點 #3 | **是** — G1-05 未驗 ship；TOML 直編輯無 audit |
| **`edge_estimates.rs` startup-only（原則 #6 + #7 + #12 嚴重 gap）** | [3, 5, 6] **三類熱點** | **是** — 三類熱點同時命中 |
| **`change_audit_log.py` 無 PG（原則 #8 + #15 嚴重 gap）** | [3, 6, 5] | **是** — 治理盲區 §3.A |
| **`fast_track.rs` Guardian 旁路（原則 #4）** | [5] 歷史熱點 #4 | **是** — FA-PHANTOM-1 設計風險仍在 |
| **`RiskConfig` 6 原則樞紐（meta-gap top 1）** | [2] 耦合熱點 #1 | **是** — 任何 TOML 直編輯仍可繞過 V014 audit |
| **`live_authorization.rs` + `live_auth_watcher.rs`（原則 #2/#3/#5/#11）** | [5] 歷史熱點 #7 + [6] 邊界熱點 #6 | **是** — drawdown 從未真實 live 觸發過，HMAC key 漂移風險 |
| **`step_4_5_dispatch.rs:935` + `intent_processor:1100`（原則 #1/#4/#6/#8/#13）** | [1] 複雜度 #7 + [2] 耦合 #8 | **中** — NLL 鎖定為設計強約束，但下次 borrow checker 放寬時須警惕 |

**結論**：Session 4 嚴重 gap 的 6 個對應模組 100% 同時是 Session 5 熱點 — 證明治理 gap 不是紙面分析，是實質風險集中區。

### 4.2 Memory 數字漂移

Session 3 同時發現「memory/CLAUDE.md 中的絕對數字」與實證不符的兩處：
- 「Guardian 15+ checks」實為 9 checks（Session 3 Flow 4）
- 「authorization.json 5min file poll」實為 5s file poll，5min 是 SM-01 lease 層

建議 Session 後續：列「memory 中所有絕對數字」交給 healthcheck 或 grep 重驗。

### 4.3 跨流共享狀態 = 一致性 bug 高風險區

| 共享狀態 | 共享的流 | 風險 |
|---|---|---|
| `Arc<AtomicBool> session_halted` | Flow 7 (Teacher) + Flow 10 (News Guardian) | 雙寫源；任一斷線 halt flag 不一致 |
| `ConfigStore<RiskConfig> ArcSwap` | Flow 1 (cost_gate) + Flow 4 (Guardian) + Flow 5 (cost_gate fallback) + Flow 6 (live auth) | 6 條根原則樞紐 |
| `edge_estimates HashMap` | Flow 5 (Learning) + Flow 1 (CostGate) | startup-only 熱重載斷鏈 |

---

## 5. 各 Session「最不確定的 5 件事」彙總

每個 Session 的作者都自承了當時最不確定的 5 件事，下面是合併與分類版（避免重複，按主題歸檔）：

### 5.1 hot path call graph 未直接驗證（推測居多）

1. **`step_4_5_dispatch.rs` 內 IntentProcessor 呼叫位置**（Session 1+3）— 935 行 NLL 鎖定，但實際 file:line 沒直接 grep 命中。
2. **`event_consumer/bootstrap.rs` 27 interdependent bindings 具體是哪些**（Session 1）— 只看了 20 行檔頂。
3. **Flow 2 ExecutionListener callback 註冊位置未直接驗證**（Session 3）— sub-agent 推測在 bootstrap.rs 27 binding 中之一。
4. **`5-agent wiring asymmetric audit_callback`**（Session 3+4）— ExecutorAgent line 482 + strategy_wiring 467-468 已驗，其他 4 agent wiring 未直接 grep。

### 5.2 PG 寫入路徑驗證為負或未驗

5. **`change_audit_log` 是否真的完全沒 PG 寫入路徑**（Session 4+5）— grep 全 srv/ 只找到 `governance.lease_transitions` / `authorization_transition` / `risk_governor_transition` SQL，change_audit_log.py + audit_persistence.py 0 INSERT；但**未排除** governance_hub.py / state_machine_base.py 是否在 cascade callback 中**間接**呼某個 audit consumer。
6. **engine_maintenance.flag CREATE 點**（Session 3+4）— sub-agent 6 + 主會話 grep 找不到 `touch` / `> file` 命令。可能是 operator 手動 touch、deploy script、或 systemd unit。

### 5.3 雙源語意對齊未驗

7. **Python guardian_agent / portfolio_risk_control / atr_tracker 是否實際在 hot path 被呼到**（Session 4）— Session 3 Flow 4 推測「僅 IPC `_handle_guardian` handler 被呼，非 hot path」未實證。
8. **Rust + Python SM-02 / SM-04 雙源語意 byte-identical 約束的實際自動測試覆蓋**（Session 4）。

### 5.4 學習 → Live 平面 cadence 不確定

9. **strategist_scheduler 5min 自動 tune 的「邊界」實際範圍**（Session 4）— [strategist_scheduler/mod.rs:1166](srv/rust/openclaw_engine/src/strategist_scheduler/mod.rs)每 5min UpdateStrategyParams IPC 改 5 策略運行時參數，無 operator 批准，但實際可調的參數範圍 / 上限 / clamp 在哪定義未追。
10. **edge_estimates 從 startup-only → IPC 熱重載的 commit 是否確實落實**（Session 4）— EDGE-DIAG-1-FUP-IPC 加 7 個 `exit.*` 欄位，但這 7 欄位是 `exit.*`（Track P 物理 lock），**不含** edge_estimates.json 本身。

### 5.5 風險熱點工作量估計的盲區

11. **「複雜度」用行數 proxy 的偏差**（Session 5）— 沒跑 `radon cc` 或類似工具量真實 cyclomatic complexity。Top 10 中可能有 2–3 個應降排（特別是 6 號 `on_tick/helpers.rs` 1182 行多為 e2e test fixture）。
12. **「新鮮」未抽 +/- 行數**（Session 5）— 無法區分 refactor vs 業務改動。
13. **30 天內 `--rebuild` 次數與 `edge_estimates.json` 改檔次數的對賬**（Session 5）— 紅色 #2 ROI 取決於這個對賬，30d 內 engine 真的有新 edge_estimates 寫入但 engine 未重啟的窗口次數。
14. **Top 5 紅色清單的工作量估計缺乏 Linux runtime 驗證**（Session 5）— 我作為 Mac dev session（per memory `project_dev_runtime_split.md`）只讀靜態代碼 + 跑 grep；沒法跑 `cargo test` / 沒法 ssh trade-core 跑 Linux runtime 驗證。**實際工作量區間應 ±30%**。
15. **CLAUDE.md §三宣稱的「engine lib 1980 passed / Part A 1905」與實際 cargo test 跑得通的對應關係**（Session 1）— 我的理解度完全基於靜態閱讀；沒跑 `cargo test`，沒驗 `#[cfg(test)]` 實際通過率。

---

> 以下為各 Session 詳細產出原文，按 Session 順序串接。每 Part 內保留原 inventory 的章節結構與表格，可作為「給定問題從哪條流追入」的索引。

---



## Part 1A — Rust 模組清單（Session 1/5）

> 來源：[.claude_reports/inventory_1a_rust_modules.md](.claude_reports/inventory_1a_rust_modules.md)
> 涵蓋：openclaw_types + openclaw_core + openclaw_engine 三 crate × ~180 `.rs` 檔，共 131,120 LOC（test ~15k / prod ~116k）。

### 盤點交付物 #1（Rust 部分）— openclaw_types / openclaw_core / openclaw_engine 模組清單

本文件是 Session 1/5 Rust 模組盤點結果。Operator 在「理解度」欄填 0-5 後，後續 session 會交叉引用作為知識地圖。行數取自 2026-04-24 `wc -l`；職責一段取自檔頂 MODULE_NOTE 或 use 聲明交叉驗證。

---

#### 第 1 批：openclaw_types（跨 crate 共享型別）

| 路徑 | 職責 | 行數 | 關鍵依賴 | 輸入 | 輸出 | 核心設計決策 | 潛在風險 | 理解度 | 備註 |
|---|---|---|---|---|---|---|---|---|---|
| openclaw_types/src/lib.rs | 暴露跨 crate 6 類型 + CI 黃金 schema 校驗 | 161 | serde_json, std::fs | rust/schemas/shared_types.json | 6 個 pub use 再匯出 + 4 個 schema golden 測試 | 1) 測試讀 schemas/shared_types.json fail→panic 2) 1C-1 Batch 6 刪 `StopConfig` / composite `RiskConfig` 重複定義 | 無識別風險 |  |  |
| openclaw_types/src/price.rs | 定義 PriceEvent/Kline/OHLCV/PriceEventKind | 244 | serde, std::HashMap | — | pub struct/enum | FIX-31 typed `PriceEventKind` 取代 stringly-typed metadata | 無識別風險 |  |  |
| openclaw_types/src/intent.rs | 交易意圖/風控裁決型別（TradeIntent/OrderIntent/RiskVerdict） | 162 | serde, HashMap | — | pub struct 含 DataQualityLevel（Fact/Inference/Hypothesis） | DataQualityLevel 落實原則 #10（認知誠實） | 無識別風險 |  |  |
| openclaw_types/src/risk.rs | H0 Gate 跨 crate 共享型別（Config/Snapshot/CheckResult） | 147 | serde | — | pub struct 4 種 H0GateConfig/HealthSnapshot/RiskSnapshot/CheckResult | 1C-1 Batch 6 明確職責：composite RiskConfig 已刪除，權威在 `engine::config::RiskConfig` | 無識別風險 |  |  |
| openclaw_types/src/agent.rs | 6 個 AgentRole + MessageType 協議 | 126 | serde | — | pub enum | 落實原則 #15（5-Agent + Conductor） | 無識別風險 |  |  |
| openclaw_types/src/cognitive.rs | CognitiveParams/DreamInsight/RegretSummary/SkippedOpportunity | 157 | serde | — | pub struct 4 種 | EMA α=0.3 smoothing 預設（對齊 Python cognitive_modulator） | 無識別風險 |  |  |
| openclaw_types/src/state.rs | GovernanceMode/AgentState/OmsState/OrderInitiator/RiskLevel | 198 | serde | — | pub enum | 與 Python shared_types.py 契約對齊 | 無識別風險 |  |  |

#### 第 2 批：openclaw_core（風控 / 門控 / 狀態機 / 計算）

| 路徑 | 職責 | 行數 | 關鍵依賴 | 輸入 | 輸出 | 核心設計決策 | 潛在風險 | 理解度 | 備註 |
|---|---|---|---|---|---|---|---|---|---|
| openclaw_core/src/lib.rs | 核心 crate 根，re-export sm/indicators/risk 等 | 36 | openclaw_types | — | pub mod × 17 + `use sm::{now_ms, is_stale}` | 跨 crate 工具函式 `now_ms` / `is_stale` 單一定義避 5+ 副本 | 無識別風險 |  |  |
| openclaw_core/src/h0_gate.rs | H0 本地確定性門控（freshness/health/eligibility/risk/cooldown） | 1067 | openclaw_types::H0Gate*, Instant, VecDeque | H0GateConfig + tick ts_ms + health/risk snapshot | H0CheckResult{allowed,reason}+GateStats+ShadowEntry | 1) <1ms SLA，熱路徑無 I/O 2) 5 子檢查 fail-fast 順序 3) Shadow 模式觀察不阻擋 | 1067 行接近 §九 1200 硬上限；未來增項需拆分 |  |  |
| openclaw_core/src/governance_core.rs | 4 SM 級聯（auth/lease/oms/risk）+ GovernanceMode 派生 | 580 | sm::{auth,lease,oms,risk_gov} | SM 狀態變更事件 | 4 SM transition + cascade verdict | all-or-nothing clone→execute→commit/rollback；risk≥CB→auth freeze+lease revoke | 無識別風險 |  |  |
| openclaw_core/src/guardian.rs | 4 項確定性風控 veto（方向衝突/槓桿/回撤/持倉數） | 314 | serde | GuardianConfig + TradeIntent | 拒絕/通過 verdict | 1C-4 E-Merge-4：GuardianConfig 成為 RiskConfig 派生視圖，tick hot-reload 完整覆蓋無 RMW | 無識別風險 |  |  |
| openclaw_core/src/cognitive.rs | L0 決策門檻調製（confidence_floor/qty_ceiling/sl_mult/scan_interval） | 524 | serde, HashMap | 歷史績效 + 遺憾 + Monte Carlo 建議 | CognitiveParams EMA 平滑 | 1) EMA α=0.3 防振盪 2) \[Q1\] max 單因子非求和 3) \[R1-5\] 連虧時忽略負向壓力 | 無識別風險 |  |  |
| openclaw_core/src/klines.rs | 多時間框架 K 線聚合器 (Kahan compensated sum) | 1086 | serde, HashMap, VecDeque | tick 原始資料 | 聚合 OHLCV buffer | 1) Kahan 補償求和確保 volume/turnover 浮點精度 [V3-QC-2] 2) 只讀，永不下單 | 1086 行接近 §九 1200 硬上限 |  |  |
| openclaw_core/src/attention.rs | Session/position 驅動的行情節流層級（Dormant/Low/Medium/High） | 424 | HashMap, VecDeque | 交易上下文 | AttentionLevel + 節流間隔 | 高關注頻繁處理；低關注省計算；只讀評估 | 無識別風險 |  |  |
| openclaw_core/src/attribution.rs | 6 因子 PnL 分解（alpha/timing/sizing/execution/cost/luck） | 267 | serde | TradeRecord | 分解結果 | 記錄 best_price/worst_price 供 luck 因子 | 無識別風險 |  |  |
| openclaw_core/src/backtest.rs | 逐 K 線回放 + Sharpe/回撤 | 490 | execution, stop_manager | BacktestConfig + OHLCV | 權益曲線 + Sharpe | turnover_24h 驅動滑點模型 | 無識別風險 |  |  |
| openclaw_core/src/cost_gate.rs | 往返成本估算（volume tier）+ ATR 覆蓋判斷 | 250 | — | 24h volume + ATR | 通過/拒絕 | 1) 首筆 ATR>0.5×cost 放行防零交易日 2) ATR=None fail-open | 無識別風險 |  |  |
| openclaw_core/src/dream.rs | 閒置 Monte Carlo 參數網格搜索 | 936 | rand::StdRng, Arc<Mutex>, serde | 最近 K 線片段 + 參數網格 | DreamInsight | 1) 每參數值 ≥30 simulations [Q4] 2) binomial test 信心 [Q5] 3) Arc<Mutex<bool>> 可重入防護 [R1-3] | 936 行；Mutex 可重入保護需驗證 poisoning 處理 |  |  |
| openclaw_core/src/execution.rs | 滑點/成交價/手續費計算（確定性） | 346 | serde | Intent + 市價 | FillResult | 常數 TAKER=0.055% / MAKER=0.02% | 硬編碼費率 — 動態 fee_rate 覆蓋需 caller 提供 |  |  |
| openclaw_core/src/message_bus.rs | Agent 消息路由（6 角色） | 296 | serde, VecDeque | AgentMessage | 路由結果 | Guardian verdict 永遠覆蓋 Strategist | 無識別風險 |  |  |
| openclaw_core/src/opportunity.rs | 虛擬 PnL 追蹤 + 遺憾摘要 | 861 | serde, uuid, HashMap, VecDeque | 被跳過的信號 + tick price | RegretSummary | 1) [Q2] 虛擬 PnL 扣 2× fee 防假後悔 2) [Q3] 歸一化比較 3) [R1-8] ≥5 樣本才判斷方向 | 861 行；call sites 驗證不足 |  |  |
| openclaw_core/src/order_match.rs | Paper 限價單匹配（touch/cross） | 308 | execution::FillResult | PaperOrder + 市場 tick | 成交/未成交 | 無識別風險 | 無識別風險 |  |  |
| openclaw_core/src/portfolio.rs | 組合層風控（correlation/集中度/儲備） | 362 | serde | PortfolioConfig + 倉位集合 | 違反報告 | 預設 correlation_threshold=0.7, sector cap 40%, reserve 30% | 無識別風險 |  |  |
| openclaw_core/src/stop_manager.rs | Hard/Trailing/Time stops + ATR 倉位計算 | 557 | serde | 持倉 + 當前價 + ATR | 止損觸發/trailing 更新 | trailing_activation_pct 獨立於 trailing_stop_pct 以嚴格鎖利 | 無識別風險 |  |  |
| openclaw_core/src/sm/mod.rs | SM 共用 now_ms/is_stale/TransitionRecord/SmError | 97 | rand, thiserror, serde | — | pub fn + struct + thiserror enum | `transition_id` 用 rand u64 前 12 hex | `rand::random::<u64>` 非 cryptographic；用於 ID 非安全敏感 |  |  |
| openclaw_core/src/sm/auth.rs | SM-01 授權狀態機（8 態 16 遷移 6 禁 5 守衛） | 817 | sm::{SmError,TransitionRecord}, serde | Auth event | AuthState + transition | Terminal: Revoked/Expired/Rejected | 無識別風險 |  |  |
| openclaw_core/src/sm/lease.rs | SM-02 決策租約狀態機（9 態 20 遷移 12 禁 5 守衛） | 747 | sm::{SmError,TransitionRecord}, serde | Lease event | LeaseState + transition | 落實原則 #3 AI 輸出 ≠ 即時命令 | 無識別風險 |  |  |
| openclaw_core/src/sm/oms.rs | OMS 11 態訂單生命週期 | 728 | sm::{SmError,TransitionRecord}, serde | Order event | OrderState transition | 不可跳授權/對賬 | 無識別風險 |  |  |
| openclaw_core/src/sm/risk_gov.rs | SM-04 6 級風控總督（Normal→CB→MR） | 933 | sm::{SmError,TransitionRecord}, serde | Risk event + tier | RiskLevel + cascade | 升級自動、降級需審批 + min hold time | 933 行接近軟警告；可觀察未來 tier 增加 |  |  |
| openclaw_core/src/indicators/mod.rs | 16 指標引擎（SMA/EMA/RSI/MACD/BB/ATR/...） | 304 | serde, momentum, trend, volatility, volume | close/high/low/volume 序列 | IndicatorSnapshot | 1) Kahan compensated sum [V3-QC-2] 2) conservative_atr = max(atr_5, atr_14) | 無識別風險 |  |  |
| openclaw_core/src/indicators/momentum.rs | RSI + Stochastic + ADX（Wilder smoothing） | 278 | kahan_sum | close series | Option<f64> 指標值 | Wilder smoothing 對齊 Python | 無識別風險 |  |  |
| openclaw_core/src/indicators/trend.rs | SMA/EMA/MACD/KAMA/Donchian | 308 | kahan_sum | close series | Option<f64> | 無識別風險 | 無識別風險 |  |  |
| openclaw_core/src/indicators/volatility.rs | BollingerBands/ATR/EWMA Vol/Hurst | 394 | kahan_sum | OHLC series | Option<f64>+BollingerResult | 無識別風險 | 無識別風險 |  |  |
| openclaw_core/src/indicators/volume.rs | VolumeRatio (current/avg) | 56 | kahan_sum | volume series | Option<f64> | avg<1e-15 → None 避免除零 | 無識別風險 |  |  |
| openclaw_core/src/signals/mod.rs | SignalEngine 共識（8 規則 + freshness 衰減） | 465 | rules | IndicatorInput 集合 | Signal + consensus | consensus = confidence × freshness_weight（5 min 線性衰減） | 無識別風險 |  |  |
| openclaw_core/src/signals/rules.rs | 8 個純計算信號規則 | 731 | — | IndicatorInput | Option<Signal> | QC 邊界豁免：RSI ±0.03 / MA ±1e-8 / ATR ±0.01% [V3-QC-2] | 無識別風險 |  |  |
| openclaw_core/src/risk/mod.rs | ARCH-RC1 後 risk crate 純計算層（config-free） | 24 | price_tracker, regime, stops | — | pub use | 明確：config 讀取搬到 `engine::risk_checks` | 無識別風險 |  |  |
| openclaw_core/src/risk/price_tracker.rs | 價格歷史追蹤器（ATR + 尖峰偵測） | 898 | HashMap, VecDeque | tick (symbol,price,ts) | ATR + SpikeInfo | 1) SPIKE σ threshold=3.0 2) window=5min 3) ≥10 樣本才計算 | 898 行；window 邊界條件（多幣/高頻）需測試 |  |  |
| openclaw_core/src/risk/regime.rs | regime→risk multiplier 純查找表（硬編碼 fallback） | 59 | — | regime &str | RegimeMultipliers{stop,tp,time} | 說明 core 不依賴 engine；engine 端 `RegimeMultipliers` 為權威 | 硬編碼與 engine 權威可能漂移 |  |  |
| openclaw_core/src/risk/stops.rs | 動態止損計算（ATR 自適應 + 反聚集偏移） | 169 | super::regime | symbol/ts/ATR | dynamic_stop_pct + anti_cluster_offset | anti_cluster_offset 用 symbol+ts hash 範圍 [-0.15,+0.15] | 無識別風險 |  |  |

#### 第 3 批：openclaw_engine 核心層（lib / main / config / common）

| 路徑 | 職責 | 行數 | 關鍵依賴 | 輸入 | 輸出 | 核心設計決策 | 潛在風險 | 理解度 | 備註 |
|---|---|---|---|---|---|---|---|---|---|
| openclaw_engine/src/lib.rs | Engine crate 根，pub mod × 44 + re-export core/types | 61 | openclaw_core, openclaw_types | — | pub mod 聲明 | 介面面向 binary（main.rs）與整合測試 | 無識別風險 |  |  |
| openclaw_engine/src/main.rs | 引擎 binary 入口 tokio 運行時 + SIGHUP/SIGTERM + 引導 | 2062 | tokio, tokio-util, startup::* | engine.toml + env | 引擎進程 | 1) multi-thread tokio 2) SIGHUP→config hot-reload 3) SIGTERM→graceful shutdown | 2062 行遠超 §九 1200 硬上限；startup 拆出後 main 仍過大 |  |  |
| openclaw_engine/src/config/mod.rs | 3 Config hot-reload + RuntimeConfig 載入 | 457 | arc_swap, serde, toml | engine.toml + 3 Config TOML | 3 ConfigStore<T> | ARCH-RC1 權威；後續 Session 1C 將移除 RuntimeConfig 重複欄位 | 3 Configs 欄位與 RuntimeConfig 重複待清理 |  |  |
| openclaw_engine/src/config/store.rs | 泛型 ConfigStore<T>：ArcSwap 無鎖讀 + Mutex 序列化補丁 | 837 | arc_swap, parking_lot, serde | patch JSON + source | next T + version + audit | 1) 讀 ~5ns 無鎖 2) 批次補丁 all-or-nothing 3) PatchSource 審計（Operator/Agent/Migration/Startup） | 837 行 E5-P1 拆分後仍偏重 |  |  |
| openclaw_engine/src/config/risk_config.rs | 風控權威配置（P0 品類/P1 硬頂/P2 agent/6 級 SM/regime/cost/dynamic_stop/anti-cluster） | 908 | serde, HashMap, exit_features::ExitConfig, advanced::* | TOML | RiskConfig | 1) RiskConfig 為**所有**風控決策單一真相 2) tick 路徑 ArcSwap ~5ns 3) partial_tp_* 在 agent P2 | 908 行；`#[path]` 載入 advanced 跨檔複雜度 |  |  |
| openclaw_engine/src/config/risk_config_advanced.rs | EdgePredictor/DynamicStop/MarketGate/AntiCluster/Correlation/RuntimeKnobs/Experimental 子 struct | 396 | super::default_true, serde, HashMap | — | 子 struct 集 | Wave 1 G1-03 拆分，用 `#[path]` 隱藏檔名，`pub use` 保持 API | `#[path]` 機制對 IDE 跳轉不直觀 |  |  |
| openclaw_engine/src/config/risk_config_tests.rs | RiskConfig validator + patch 行為測試 | 423 | — | RiskConfig 構造 + patch | test assertions | 單獨檔是 dev-time artifact；`#[cfg(test)]` 不進 binary | 無識別風險 |  |  |
| openclaw_engine/src/config/budget_config.rs | AI 成本上限/attention tax/model pricing | 560 | serde, HashMap | TOML | BudgetConfig | ARCH-RC1 三 Config 之一；attention_tax.enabled 只在這裡 | 無識別風險 |  |  |
| openclaw_engine/src/config/learning_config.rs | ML/RL/Agent 行為開關 + Teacher loop kill-switch | 459 | serde, HashMap | TOML | LearningConfig | `teacher_loop_enabled` 統一來源；partial_tp_* 屬 RiskConfig 不在此 | 無識別風險 |  |  |
| openclaw_engine/src/config/io.rs | 泛型 TOML load/save with validator closure | 177 | serde | path + validator | Result<T,String> | default 分支也必須通過 validator（catches default 回歸） | 無識別風險 |  |  |
| openclaw_engine/src/config/legacy_migration.rs | operator_risk_config.json → risk_config.toml 一次性遷移 | 327 | super::budget_config | 舊 JSON | TOML + .legacy 重命名 | max_cost_edge_ratio 跨 Config → 僅 log | 未知欄位 silently drop 潛在資料丟失 |  |  |
| openclaw_engine/src/common/mod.rs | 交易所層共用原語（ws_backoff + bybit_signer） | 19 | — | — | pub mod | E1-P0-3 dedup | 無識別風險 |  |  |
| openclaw_engine/src/common/bybit_signer.rs | HMAC-SHA256 REST/WS auth 簽名 | 162 | hmac, sha2, hex | timestamp+params | lowercase hex | SHA-256 key 長度永不溢出，`.expect()` 安全 | 無識別風險 |  |  |
| openclaw_engine/src/common/ws_backoff.rs | 指數退避 base*multiplier^attempt 飽和 + cap | 192 | — | attempt + base_delay | delay ms | jitter_pct 預設 0 = RNG 停用（E1-P0-3 契約） | 無識別風險 |  |  |

#### 第 4 批：tick_pipeline + event_consumer + ipc_server

| 路徑 | 職責 | 行數 | 關鍵依賴 | 輸入 | 輸出 | 核心設計決策 | 潛在風險 | 理解度 | 備註 |
|---|---|---|---|---|---|---|---|---|---|
| openclaw_engine/src/tick_pipeline/mod.rs | TickPipeline struct + 子模組聲明 + SystemMode + PipelineKind | 1035 | openclaw_core::{governance_core,h0_gate,indicators,klines,signals,risk}, paper_state, intent_processor | Arc<各 Config> + channel rx/tx | TickPipeline 實例 | 1) 獨佔所有者 pattern 無鎖 [V3-PA-1] 2) SystemMode 從 Python GUI 同步 3) 2274→1012 行 TICK-PIPELINE-MOD-SPLIT-1 | 1035 行接近 §九 硬上限 |  |  |
| openclaw_engine/src/tick_pipeline/pipeline_ctor.rs | TickPipeline 建構子 + endpoint/registry/mode 注入器 | 448 | 各種 openclaw_core + serde | 構造參數 | TickPipeline | 單一大 fn 避 27 interdependent bindings 爆炸 | 無識別風險 |  |  |
| openclaw_engine/src/tick_pipeline/pipeline_config.rs | Config store wiring + tick 熱重載 helper | 300 | super::TickPipeline | config channel | apply_risk_snapshot 等 | apply_risk_snapshot private；sync_* 升 pub(super) 供 step_* 呼叫 | 無識別風險 |  |  |
| openclaw_engine/src/tick_pipeline/pipeline_helpers.rs | close + exit_features + channel setter + misc | 702 | super::TickPipeline | — | emit_close_fill/emit exit feature row 等 | PNL-FIX-1 close_position_at_symbol_market；EXIT-FEATURES-TABLE-1 row builder | 無識別風險 |  |  |
| openclaw_engine/src/tick_pipeline/commands.rs | 外部命令處理（下單/風控狀態/fill/snapshot/系統模式） | 1039 | super::TickPipeline | PipelineCommand | 副作用 + 回覆 | 新 API 不再模仿 Python RiskManager.get_status shape | 1039 行接近硬上限 |  |  |
| openclaw_engine/src/tick_pipeline/on_tick/mod.rs | 4 步編排器（Step 0→0.5→1+2→3→4+5→6）+ `pub use` re-exports | 160 | super::* | PriceEvent | Option<CanaryRecord> | 每 step 回 `ControlFlow::{Break,Continue}`；跨 step 以 owned return 避 &mut self 借用衝突 | 無識別風險 |  |  |
| openclaw_engine/src/tick_pipeline/on_tick/step_0_fast_track.rs | Step 0 快速通道（閃崩/保證金/持倉跌幅） + tick 前段 | 516 | openclaw_types::PriceEventKind | PriceEvent | ControlFlow<Option<CanaryRecord>,bool> | 合併原 on_tick 前段（boot_ts/price cache/synthetic re-triage/ADL fan-out） | 無識別風險 |  |  |
| openclaw_engine/src/tick_pipeline/on_tick/step_0_5_h0_gate.rs | Step 0.5 H0 門控（影子/硬阻斷） | 93 | h0_gate | PriceEvent | ControlFlow<...,bool h0_allowed> | 硬阻斷僅跑止損然後 Break；影子 debug log | 無識別風險 |  |  |
| openclaw_engine/src/tick_pipeline/on_tick/step_1_2_klines_indicators.rs | Step 1+2 K 線聚合 + 指標計算 + FeatureSnapshot emit | 111 | super | PriceEvent | Option<IndicatorSnapshot> | 無早退；FeatureSnapshot 發 feature writer channel | 無識別風險 |  |  |
| openclaw_engine/src/tick_pipeline/on_tick/step_3_signals.rs | Step 3 pause gate + boot cooldown + 信號評估 | 192 | SignalEngine | IndicatorSnapshot | ControlFlow<...,Vec<Signal>> | paper_paused→跑止損後 Break；boot N ms 抑制策略信號 | 無識別風險 |  |  |
| openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs | Step 4+5 逐策略分派 + 意圖處理 + maker sweep + 延遲平倉 | 935 | orchestrator, intent_processor | signals + indicators | ControlFlow<...,Vec<OrderIntent>> | **不可再拆**：disjoint-field NLL 僅單 fn 有效 | 935 行接近硬上限；重構受語意鎖定 |  |  |
| openclaw_engine/src/tick_pipeline/on_tick/step_6_risk_checks.rs | Step 6 9 項持倉風控 + halt/cooldown 派發 | 554 | position_risk_evaluator, exit_features | 持倉快照 | side-effects (close/halt/cooldown) | 政策（純計算）/ 機制（side-effect）拆開；兩階段 snapshot-then-act 語意等價 | 無識別風險 |  |  |
| openclaw_engine/src/tick_pipeline/on_tick/helpers.rs | Track P T4 audit wrapper (risk_close: prefix 對齊) + e2e test | 1182 | tracing | RiskAction::ClosePosition reason | 單一 risk_close:* tag | RUST-DOUBLE-PREFIX-1：確保前綴永遠只有一個 | 1182 行逼近硬上限；合併 test+helper |  |  |
| openclaw_engine/src/tick_pipeline/on_tick_helpers.rs | FIX-29 extracted helpers (cooldown/push_capped/make_*_id) | 413 | — | — | pub(crate) fn | P0-5 ReduceToHalf 60s cooldown 與 governance 狀態解耦 | 無識別風險 |  |  |
| openclaw_engine/src/tick_pipeline/tests.rs | TickPipeline 整合測試 | 3524 | tempfile, 全子系統 | test fixtures | assertions | 93 unwrap 在測試中可接受 | 3524 行單測試檔巨大；難以維護 |  |  |
| openclaw_engine/src/event_consumer/mod.rs | WS 事件消費 + 6-arm select!（cancel/cross_engine/kline_seed/exchange/pending_reg/paper_cmd/tick） | 225 | tokio::select, loop_handlers, bootstrap | PriceEvent + cross events | pipeline 推進 | 主事件循環；shutdown 時平掉所有倉 + 寫最終 snapshot | 無識別風險 |  |  |
| openclaw_engine/src/event_consumer/bootstrap.rs | 主迴圈前所有管線構造與接線（27 interdependent bindings） | 847 | 全體 engine | EventConsumerDeps | BootstrappedRuntime | 單一大 fn 避參數爆炸；對齊 pipeline_ctor 先例 | 847 行；依賴圖複雜 |  |  |
| openclaw_engine/src/event_consumer/loop_handlers.rs | 5 個 select! arm 獨立 handler + LoopState | 1096 | super::* | arm event | 副作用 | LoopState 合併 7 loop-internal mut 欄位；receiver 仍留在父函式（select! &mut） | 1096 行接近硬上限 |  |  |
| openclaw_engine/src/event_consumer/dispatch.rs | 訂單派發 task spawn（shadow/primary）+ retry policy | 1124 | bybit_rest_client, order_manager | OrderDispatchRequest | OrderManager call + PendingOrder | DISPATCH-RETRY-1 指數 backoff for OPEN intents | 1124 行接近硬上限 |  |  |
| openclaw_engine/src/event_consumer/governor_cooldown.rs | Governor 降級冷卻 PG 持久化（V014）+ 純決策函式 | 126 | TickPipeline | stored_ts + now | Option<still_active> | 純決策 unit-testable 無 PG fixture | 無識別風險 |  |  |
| openclaw_engine/src/event_consumer/paper_state_restore.rs | QoL-1 從 trading.fills 還原累計計數（per engine_mode） | 132 | PaperState::restore_from_db | audit pool + engine_mode | restored counters | fail-soft boot-time；3 模式隔離 | 無識別風險 |  |  |
| openclaw_engine/src/event_consumer/pending_sweep.rs | Pending order 分類 + PostOnly maker cancel helper | 286 | tracing | PendingOrder + elapsed_ms | classification | EDGE-P2-3 1B-3.2 sweep | 無識別風險 |  |  |
| openclaw_engine/src/event_consumer/setup.rs | Pipeline wire-up（fee rate + risk config + instrument cache + DB channels） | 108 | EngineBootstrap | bootstrap deps | wired pipeline | I-22 extraction | 無識別風險 |  |  |
| openclaw_engine/src/event_consumer/types.rs | EventConsumerDeps bundle + ExchangeEvent + PendingOrder | 305 | bybit_private_ws, instrument_info | — | pub type/struct/enum | SYMBOLS + STATUS_INTERVAL_SECS 常量；3E D20 Arc<MetadataMap> fan-out 避 clone | 無識別風險 |  |  |
| openclaw_engine/src/event_consumer/handlers/mod.rs | IPC command dispatch facade（7 domain sibling re-export） | 378 | super::types | PipelineCommand | dispatch | 1:1 原 match arm 保留；E5-P1-3 拆 handlers.rs | 無識別風險 |  |  |
| openclaw_engine/src/event_consumer/handlers/lifecycle.rs | 生命週期命令（pause/resume/reset/close_all/submit/active/system_mode/adopt_orphan） | 255 | persistence::DualStateWriter, TickPipeline | PipelineCommand | 副作用 + ack | match arm body 1:1 拆出 | 無識別風險 |  |  |
| openclaw_engine/src/event_consumer/handlers/strategy_params.rs | UpdateStrategyParams/GetStrategyParams/GetParamRanges | 107 | TickPipeline | params JSON | IPC ack | CONF-D conf_scale strip-and-apply 保持 | 無識別風險 |  |  |
| openclaw_engine/src/event_consumer/handlers/risk.rs | 風控 IPC（runtime status / 連虧計數 / risk config setter / governor 覆蓋 / 動態 sizer toggle） | 563 | persistence, TickPipeline | RiskCommand | IPC + side-effects | I-09 clamp 範圍不放鬆；ForceGovernorLooser 24h cooldown + CB/MR 硬鎖 | 無識別風險 |  |  |
| openclaw_engine/src/event_consumer/handlers/edge_predictor.rs | EdgePredictor IPC（Shadow/Reload/DisableAll + ShadowFill + DecisionFeature） | 434 | EdgePredictorStore | IPC params | two-phase kill-switch + V014 audit | Disable-all 兩階段 fsync→ArcSwap→clear_all | 無識別風險 |  |  |
| openclaw_engine/src/event_consumer/handlers/tests.rs | dispatch handlers 單元測試 | 695 | fixtures | IPC fixtures | assertions | 32 unwrap 在測試中可接受 | 無識別風險 |  |  |
| openclaw_engine/src/ipc_server/mod.rs | Unix socket JSON-RPC 2.0 伺服器（newline-delimited） | 1192 | tokio::net UnixListener, handlers, param_extractor | 連線 + JSON-RPC req | JSON-RPC resp | 每連線 tokio task；支援 ping/get_state/reload/paper/snapshot/strategy params | 1192 行**擠爆** §九 硬上限；需拆分 |  |  |
| openclaw_engine/src/ipc_server/handlers_config.rs | ARCH-RC1 1C-2-C Config IPC helpers（deep merge patch） | 194 | super | JSON patch + current snapshot | next config | 物件深合併，純量/陣列覆蓋 | 無識別風險 |  |  |
| openclaw_engine/src/ipc_server/param_extractor.rs | JSON-RPC 參數提取/驗證（E5-P1-5） | 441 | serde_json | params | 解析結果或 error reply | 30+ near-identical snippet 集中 | 無識別風險 |  |  |
| openclaw_engine/src/ipc_server/handlers/mod.rs | Handlers facade re-export（7 domain） | 58 | 7 子模組 | — | pub(in crate::ipc_server) use | 可見性不拓寬：模組間 `pub(in)` + facade `pub use` | 無識別風險 |  |  |
| openclaw_engine/src/ipc_server/handlers/misc.rs | 雜項 IPC（state snapshot/Phase4 card/scanner status） | 189 | 共享 registry + snapshot | req params | JSON resp | 不走 event-consumer channel | 無識別風險 |  |  |
| openclaw_engine/src/ipc_server/handlers/budget.rs | AI budget IPC（status read / upsert / record Layer 2 usage） | 225 | BudgetTrackerSlot | req params | JSON resp | 讀 fail-soft；寫 fail-closed (-32603) | 無識別風險 |  |  |
| openclaw_engine/src/ipc_server/handlers/teacher.rs | Teacher loop enabled toggle + status counters | 82 | TeacherLoopSlot | — | JSON resp | 未接線時 fail-soft uninitialized | 無識別風險 |  |  |
| openclaw_engine/src/ipc_server/handlers/strategy.rs | Strategy params CRUD + active toggle + submit paper order | 215 | PipelineCommand, oneshot | — | ack with 3-5s timeout | StrategyParamOp enum `pub(in crate::ipc_server)` | 無識別風險 |  |  |
| openclaw_engine/src/ipc_server/handlers/risk.rs | 21 risk 參數 live hot-patch + runtime status + 連虧 reset | 266 | PipelineCommand | 參數 JSON | IPC ack | clamp/validation 集中在 event-consumer 端 | 無識別風險 |  |  |
| openclaw_engine/src/ipc_server/handlers/dynamic_risk.rs | DYNAMIC-RISK-1 sizer status + toggle | 86 | extract_engine_tx | — | JSON resp | 切換屬運行時，下次 TOML 熱重載還原 | 無識別風險 |  |  |
| openclaw_engine/src/ipc_server/handlers/governance.rs | Operator governor escalate/de-escalate + 全局 system mode 廣播 | 293 | pipeline_cmd_tx, EngineCommandChannels | — | V014 audit row | 被拒絕路徑也寫 audit（原則 #8 可解釋可審計） | 無識別風險 |  |  |
| openclaw_engine/src/ipc_server/tests/* | IPC 各 domain 單元測試（budget/config/dispatch/phase4/risk/risk_update/scanner/snapshot/strategy/teacher/mod） | 1696 合計 | fixtures | params | assertions | 按 domain 隔離測試；dispatch/config tests 涵蓋 | 無識別風險 |  |  |

#### 第 5 批：paper_state + strategies + risk + orchestrator + position

| 路徑 | 職責 | 行數 | 關鍵依賴 | 輸入 | 輸出 | 核心設計決策 | 潛在風險 | 理解度 | 備註 |
|---|---|---|---|---|---|---|---|---|---|
| openclaw_engine/src/paper_state/mod.rs | Paper/demo/live 倉位 + PnL 管理 root | 204 | serde, sub-modules | Fill event, tick price | PaperStateSnapshot, positions | E5-P1-1 拆 2380→8 檔；零行為變更 bit-exact | 無識別風險 |  |  |
| openclaw_engine/src/paper_state/containers.rs | PaperPosition 純資料結構 | 273 | serde | — | pub struct | 最輕量以降低依賴 | 無識別風險 |  |  |
| openclaw_engine/src/paper_state/accessor.rs | 純 getter + SEC-18 clamped setter + 共用 helper | 446 | super::PaperState | — | getter/setter | SEC-18 夾值防 IPC 惡意/bug 值 | 無識別風險 |  |  |
| openclaw_engine/src/paper_state/fill_engine.rs | apply_fill / close / reduce / restore（變動熱路徑） | 505 | super | Fill + market | 倉位更新 | 1) MICRO-PROFIT-FIX-1 entry_notional 累加不減 2) FIX-03 fast_track ReduceToHalf 3) B-1 Phase 2 upsert 方向翻轉 best_price reset | bit-exact 約束強，未來改動風險高 |  |  |
| openclaw_engine/src/paper_state/owner_attribution.rs | symbol↔strategy tracking + synthetic owner 重分流 | 223 | — | symbol/strategy/label | RetriageOutcome | P1-8 FUP tick-level retriage；SYNTHETIC_OWNER_LABELS 常量 | 無識別風險 |  |  |
| openclaw_engine/src/paper_state/resting_orders.rs | 掛單佇列（PostOnly）+ enqueue/touch/cross 評估 | 659 | — | Intent + tick | 成交/取消 | EDGE-P2-3 1B-4.1 plumbing；bias guards（TODO 1B-4.2 實際啟用） | 1B-4.2 tick 級 touch/cross 未完全實裝；佇列目前空 |  |  |
| openclaw_engine/src/paper_state/maker_stats.rs | Maker 掛單統計 + KPI tri-state gate | 1011 | — | submit/fill-full/fill-partial/timeout | MakerKpiStatus | bias-guard #4 adverse-selection；config 暫硬編碼（1B-5 FUP） | 1011 行接近硬上限；閾值硬編碼 |  |  |
| openclaw_engine/src/paper_state/dust_gate.rs | Dust/orphan-frozen triage（P0-6 + DUST-EVICTION-GAP-1） | 129 | super | bybit_sync 位置 | TriageOutcome (adopted/evicted/dust-frozen) | DUST_FROZEN_STRATEGY 不派發 close；dust_frozen 計數必保 | 無識別風險 |  |  |
| openclaw_engine/src/paper_state/checkpoint.rs | trading.paper_state_checkpoint 跨重啟 drawdown 連續性 | 141 | sqlx | engine_mode | 3 free fn (read/write/reset) | V018 schema；每 engine_mode 一行 | 無識別風險 |  |  |
| openclaw_engine/src/paper_state/snapshots.rs | PositionSnapshot/PaperStateSnapshot + export_state（重算 unrealized） | 86 | serde | — | DTO | 1) live unrealized PnL 2) E5-P1-1 拆出 | 無識別風險 |  |  |
| openclaw_engine/src/paper_state/resting_orders_tests.rs | Resting orders 單元測試 | 723 | — | fixtures | assertions | — | 無識別風險 |  |  |
| openclaw_engine/src/paper_state/tests.rs | PaperState 核心測試 | 1362 | — | — | — | 36 unwrap 合理 | 無識別風險 |  |  |
| openclaw_engine/src/strategies/mod.rs | Strategy trait + StrategyAction enum + 子模組宣告 | 168 | — | — | trait + enum | C4c 拆分後 150 行下 §九 | 無識別風險 |  |  |
| openclaw_engine/src/strategies/params.rs | 共用 ParamRange/StrategyParamsConfig/StrategyParams trait + TOML loader | 152 | serde | strategy_params.toml | StrategyParamsConfig | load_strategy_params_from() | 無識別風險 |  |  |
| openclaw_engine/src/strategies/strategy_params.rs | 5 策略的 *Params struct + Default + StrategyParams impl | 798 | super::confluence, serde | — | 5 Params + build_confluence_config | C4c 切出以符合 §九 800 軟警告 | 無識別風險 |  |  |
| openclaw_engine/src/strategies/registry.rs | StrategyFactory 單一建構點（create_all/_for_engine/_with_params） | 208 | super | kind/params | Vec<Box<dyn Strategy>> | 建構點唯一；測試用直注參數 | 無識別風險 |  |  |
| openclaw_engine/src/strategies/confluence.rs | 加權匯流評分（4 條件 65 分）+ 平滑倉位插值 + 持續性過濾 | 811 | serde, HashMap | 條件布林 + 時間 | ConfluenceResult | 供 ma_crossover/bb_reversion/bb_breakout；Grid 用 TrendCooldown | 無識別風險 |  |  |
| openclaw_engine/src/strategies/grid_helpers.rs | 純網格數學（層級建構/最近索引/OU 最佳間距） | 224 | serde | price bounds + vol | grid levels | 無策略狀態/副作用 | 無識別風險 |  |  |
| openclaw_engine/src/strategies/maker_rejection.rs | Post-submit maker 拒絕分類（EC_PostOnlyWillTakeLiquidity 等） | 216 | — | rejectReason str | MakerRejectionCategory | EDGE-P2-3 1B-2 純分類 | 無識別風險 |  |  |
| openclaw_engine/src/strategies/tests.rs | Strategies 共用測試 | 552 | — | fixtures | assertions | — | 無識別風險 |  |  |
| openclaw_engine/src/strategies/common/mod.rs | Common helpers re-export（PerSymbolState/ConfidenceBuilder/TrendCooldown） | 22 | — | — | pub use | 去重 4 策略重複 | 無識別風險 |  |  |
| openclaw_engine/src/strategies/common/confidence_builder.rs | ADX + regime 信心值公式 | 235 | — | adx/regime | entry_confidence | 中心化避免 MA/BB 端漂移 | 無識別風險 |  |  |
| openclaw_engine/src/strategies/common/per_symbol_state.rs | 泛型 HashMap<String,S> thin wrapper | 190 | — | — | PerSymbolState<S> | pass-through API 只改 rename | caller 不可假設迭代順序（HashMap）|  |  |
| openclaw_engine/src/strategies/common/trend_cooldown.rs | saturating_sub 冷卻閘門 | 168 | — | now_ms + last_ms | cooled: bool | 未見 symbol = cooled；時鐘倒退時 0→not cooled | 無識別風險 |  |  |
| openclaw_engine/src/strategies/ma_crossover/mod.rs | KAMA 交叉 + ADX + Hurst + 多時間框架 | 406 | indicators, confluence, common | TickContext | StrategyAction | E5-P2-4c 拆分保留型別 + `Strategy` trait impl | 無識別風險 |  |  |
| openclaw_engine/src/strategies/ma_crossover/config.rs | MaCrossover helpers / config | 81 | — | — | — | — | 無識別風險 |  |  |
| openclaw_engine/src/strategies/ma_crossover/helpers.rs | MaCrossover 內部 helper fn | 218 | — | — | — | — | 無識別風險 |  |  |
| openclaw_engine/src/strategies/ma_crossover/strategy_impl.rs | MaCrossover Strategy trait 主實作 | 285 | — | — | — | — | 無識別風險 |  |  |
| openclaw_engine/src/strategies/ma_crossover/tests.rs + tests_a1_a2_maker.rs | MA crossover 測試 | 999 | — | fixtures | assertions | — | 無識別風險 |  |  |
| openclaw_engine/src/strategies/bb_breakout/mod.rs | BB squeeze→expansion + Volume + Donchian + ATR trailing | 818 | indicators, confluence | TickContext | StrategyAction | FIX-26-DEADLOCK-1 squeeze_detected_ms 過期 auto-clear（2026-04-24）| 1B-11 deadlock fix 驗證窗 6h cron；舊 runtime bug 風險 |  |  |
| openclaw_engine/src/strategies/bb_breakout/params.rs | BbBreakoutParams + validate + build_confluence_config | 555 | serde | TOML | BbBreakoutParams | DonchianMode + BbBreakoutProfile enum（2026-04-24） | 無識別風險 |  |  |
| openclaw_engine/src/strategies/bb_breakout/runtime_params.rs | update_params / get_params 熱重載 | 116 | super | patch | params | 與 `PipelineCommand::UpdateStrategyParams` 對接 | 無識別風險 |  |  |
| openclaw_engine/src/strategies/bb_breakout/tests*.rs | BB breakout 3 測試檔（core / OI / P1-11） | 1759 | fixtures | — | — | tests_p1_11 涵蓋 F4 deadlock regression | 無識別風險 |  |  |
| openclaw_engine/src/strategies/bb_reversion.rs | BB 均值回歸 + RSI 過濾 | 1143 | indicators, confluence, common | TickContext | StrategyAction | 1143 行接近硬上限；touch 帶中線或 time stop | 無識別風險 |  |  |
| openclaw_engine/src/strategies/grid_trading/mod.rs | Grid struct + Strategy impl thin delegators + GridHealth enum | 322 | super::grid_helpers, common | TickContext | StrategyAction | GRID-TRADING-MOD-SPLIT-1（2026-04-23）拆 1729→6 檔 | 無識別風險 |  |  |
| openclaw_engine/src/strategies/grid_trading/{params,constructors,grid_layout,position_mgmt,signal}.rs | Grid 子模組（params/ctor/layout/pos_mgmt/signal） | 925 合計 | — | — | — | OU 動態間距 + fee floor 2× round-trip + 幾何模式 + inventory drift health | 無識別風險 |  |  |
| openclaw_engine/src/strategies/grid_trading/tests.rs | Grid 測試 | 696 | fixtures | — | — | — | 無識別風險 |  |  |
| openclaw_engine/src/strategies/funding_arb.rs | 資金費率套利 V2（directional capture）| 982 | HashMap | funding_rate + index_price | StrategyAction | 入場 |rate|>thresh + edge>0 + basis<max；退出 rate flipped / exit_thresh / basis / 72h | G-2 2026-04-18 結案 NEGATIVE；demo 已關 active=false |  |  |
| openclaw_engine/src/orchestrator.rs | 策略調度器（dispatch tick → strategies, 收集 StrategyAction） | 250 | strategies | TickContext | Vec<StrategyAction> | Vec<Box<dyn Strategy>> 靜態註冊 | 無識別風險 |  |  |
| openclaw_engine/src/risk_checks.rs | 訂單准入 + tick 級持倉風控（讀 RiskConfig + exit_features） | 874 | config::RiskConfig, exit_features::physical_micro_profit_lock_v2, core::risk | RiskConfig + position + tick | PositionCheck / PhysicalDecision | 1C-1 遷移自 core::risk::checks；cost_edge_max_ratio 跨 Config 讀（caller 傳入）；fail-closed | 874 行；跨 Config 契約依 caller 紀律 |  |  |
| openclaw_engine/src/position_risk_evaluator.rs | Step 6 逐倉純函數風控評估（policy vs mechanism 拆開） | 352 | config::RiskConfig, paper_state | 持倉 + config | RiskAction | 兩階段 snapshot-then-act 語意等同原內聯；HaltSession 仍 break | 無識別風險 |  |  |
| openclaw_engine/src/dynamic_risk_sizer.rs | per-engine Sharpe-aware 單筆風險調整 | 518 | VecDeque | 已實現 PnL 序列 | per_trade_risk_pct | 預設關；~簡化 Sharpe 非年化；in-memory MVP 無 DB | 無識別風險 |  |  |
| openclaw_engine/src/position_manager.rs | Bybit V5 持倉查詢 + 槓桿/TP-SL/trailing 配置 + closed PnL | 845 | bybit_rest_client | Bybit REST | 持倉結構/成功 ack | 1) async 2) Arc<BybitRestClient> 共用 | 無識別風險 |  |  |
| openclaw_engine/src/position_reconciler/mod.rs | 30s `/v5/position/list` 輪詢 vs 內存 baseline diff（5 tier drift）| 809 | bybit_rest_client, core::sm::risk_gov | REST snapshot | DriftVerdict + ReconcilerAction | 1) first-cycle warmup 避 orphan storm 2) Phase 6 auto-contraction（drift→governor escalate→recover）3) CB 5+ drifts → CloseAll | 無識別風險 |  |  |
| openclaw_engine/src/position_reconciler/orphan_handler.rs | 統一 orphan 決策 + 平倉分發（ORPHAN-ADOPT-1 Phase 1） | 1009 | super | Orphan verdict | OrphanDecision | A1-A3 硬安全路徑（liq 距離/全局 CB/notional cap）→ B soft eval | 1009 行接近硬上限；A4 scanner universe gating 已搬 tick_pipeline |  |  |
| openclaw_engine/src/position_reconciler/escalation.rs | Phase 6 escalation 邏輯 + recovery + 狀態追蹤（純函式） | 820 | core::sm::risk_gov::RiskLevel | DriftVerdict | ReconcilerAction | 6-RC-5 dust_floor × minOrderQty 忽略 | 無識別風險 |  |  |
| openclaw_engine/src/position_reconciler/tests.rs | Reconciler 測試 | 684 | — | — | — | — | 無識別風險 |  |  |
| openclaw_engine/src/fast_track.rs | 緊急執行路徑（risk≥DEFENSIVE 預定義規則立即執行） | 407 | core::sm::risk_gov | — | FastTrackAction | 閃崩/保證金危機 → 立即全平 | 無識別風險 |  |  |
| openclaw_engine/src/intent_processor/mod.rs | Intent → H0→Guardian→CostGate→Kelly→OMS 管線 | 1100 | core::*, edge_predictor, config::RiskConfig | OrderIntent + FeatureVectorV1 | IntentResult | 持 RiskConfig 快照；EDGE-P3-1 gate 整合 | 1100 行擠爆硬上限；需拆 |  |  |
| openclaw_engine/src/intent_processor/gates.rs | cost_gate_paper / profile-aware EV 過濾 | 205 | super | 策略 JS 估計 | cost gate verdict | PH5-WIRE-1 正估計→EV 比較；負→探索；無→ATR×conf×0.2 | 無識別風險 |  |  |
| openclaw_engine/src/intent_processor/router.rs | Paper/exchange gate 路徑 | 701 | super | intent + governance + paper_state | IntentResult | `process_with_features(None,...)` legacy entry | 無識別風險 |  |  |
| openclaw_engine/src/intent_processor/rejection_coding.rs | 拒絕原因碼統一（E5-P1-8） | 561 | — | reason 字面量 | RejectionCode | byte-identical 以保 audit + test 契約 | 字面值釘死 — 改動需同步測試與下游 parser |  |  |
| openclaw_engine/src/intent_processor/tests.rs | Intent processor 測試 | 1905 | fixtures | — | — | 52 unwrap 在測試中可接受 | 1905 行單檔過大 |  |  |

#### 第 6 批：學習 / Edge / ML / Exit / AI 預算 / News

| 路徑 | 職責 | 行數 | 關鍵依賴 | 輸入 | 輸出 | 核心設計決策 | 潛在風險 | 理解度 | 備註 |
|---|---|---|---|---|---|---|---|---|---|
| openclaw_engine/src/claude_teacher/mod.rs | Teacher directive fetch / parse / persist 門面 | 305 | 子模組 + openclaw_core::budget | LlmClient + scope | Directive 或 err | BudgetTracker fail-closed 在 DB 寫之前 | 無識別風險 |  |  |
| openclaw_engine/src/claude_teacher/client.rs | LlmClient trait + Anthropic 真實 + Mock | 284 | reqwest | prompt | llm resp | 無 API key→fail-closed；避 dev 誤燒預算；Pin<Box<Future>> dyn 相容 | 無識別風險 |  |  |
| openclaw_engine/src/claude_teacher/parser.rs | Strict fail-closed JSON parser | 230 | serde | raw JSON | Directive 或 err | 未知欄位/type/過期 expiry 拒絕，不靜默 coerce | 無識別風險 |  |  |
| openclaw_engine/src/claude_teacher/writer.rs | PG writer（learning.teacher_directives + experiment_ledger audit） | 251 | sqlx, experiment_ledger_pg | Directive | row + audit id | DB 不可用→Ok(0)，讓 happy path 跑 | 無識別風險 |  |  |
| openclaw_engine/src/claude_teacher/applier.rs | Directive → hint（fail-closed P0/P1 + Governance veto） | 1068 | GovernanceCheck trait, StrategyIpcSink trait | Directive + governance | DirectiveOutcome + audit | **唯一**改變運行狀態路徑；每次 outcome 寫 learning.directive_executions | 1068 行接近硬上限；P0/P1 denylist 為字串常量非邏輯 |  |  |
| openclaw_engine/src/claude_teacher/applier_test_fixtures.rs | Applier 共用 fixture | 119 | — | — | — | — | 無識別風險 |  |  |
| openclaw_engine/src/claude_teacher/consumer_loop.rs | Phase 4.1 定期 Teacher 調用器（default-off） | 665 | tokio, applier, OutcomeTracker | AtomicBool enabled | 副作用 | 需 E3 R6 audit PASS 後手動 flip；round-robin scope | 無識別風險 |  |  |
| openclaw_engine/src/claude_teacher/outcome_tracker.rs | 定期計算 directive 實現 PnL + 24h Sharpe | 409 | sqlx, trading.fills | directive rows | UPSERT outcome 欄 | 1h/4h/24h/7d windows；fail-soft log warn | 無識別風險 |  |  |
| openclaw_engine/src/claude_teacher/governance_impl.rs | GovernanceCheck 生產 wrapper（共享 Arc<AtomicBool> session_halted） | 206 | Arc atomics | setter | veto verdict | 與 news::guardian_impl 共享同一 Arc，single source | 無識別風險 |  |  |
| openclaw_engine/src/claude_teacher/strategy_ipc_impl.rs | StrategyIpcSink 生產 wrapper（PipelineCommand sender） | 220 | tokio oneshot | params | ack | 唯一 prod sink；禁觸 Python RiskManager | 無識別風險 |  |  |
| openclaw_engine/src/linucb/mod.rs | LinUCB crate root + arms_v1_15 re-export | 26 | — | — | pub use | Phase 4 4-04 推理層 | 無識別風險 |  |  |
| openclaw_engine/src/linucb/arms_v1_15.rs | v1.15 cold-start arm id 列舉 | 57 | — | — | &[&str] | — | 無識別風險 |  |  |
| openclaw_engine/src/linucb/inference.rs | ridge-regression theta/UCB/select_arm/update | 288 | — | A/b/context | theta/UCB | 自包含線性代數 no nalgebra（d≈16）；Kahan 不需（d 小） | 無識別風險 |  |  |
| openclaw_engine/src/linucb/runtime.rs | per-decision arm selection（std::sync::RwLock） | 319 | super::inference | intent context | ArmSelection | sync RwLock 以支援同步+異步 caller | 無識別風險 |  |  |
| openclaw_engine/src/linucb/state_io.rs | PG IO（learning.linucb_state V009+V010）+ schema hash fail-closed | 263 | sqlx, super::inference | DB row | ArmState | feature_schema_hash 不符 → SchemaMismatch；byte blob little-endian | 無識別風險 |  |  |
| openclaw_engine/src/linucb/schema_hash.rs | 特徵 schema hash 計算 | 50 | — | feature names + version | hash 字串 | 單一 source of truth for writer+reader | 無識別風險 |  |  |
| openclaw_engine/src/edge_predictor/mod.rs | Per-strategy quantile LGBM 骨架 + EdgePredictor trait | 428 | arc_swap, feature | features | Prediction/Error | Store per-strategy ArcSwap；PerEnginePredictors 隔離 paper/demo/live | 無識別風險 |  |  |
| openclaw_engine/src/edge_predictor/features.rs | FeatureVectorV1 17 維 + all_in_range invariant #12 | 485 | — | — | Copy struct | NaN/Inf/out-of-range → fail-closed；schema+definition hash | 無識別風險 |  |  |
| openclaw_engine/src/edge_predictor/feature_builder.rs | 從 runtime context 組裝 FeatureVectorV1 | 491 | PriceEvent, indicators, paper_state, intent | — | FeatureVectorV1 | clamp-to-range 前 handoff；Grid/FundingArb 未接線 confluence 時填 0.0 | 無識別風險 |  |  |
| openclaw_engine/src/edge_predictor/gate.rs | §7.3 純函式 gate decision（feature→predictor→cost margin→ε-greedy） | 691 | rand::SmallRng, super::rearrangement | features + store + cfg | PredictorGateOutcome | 純函式無副作用；ε-greedy 僅 paper；Fallback(reason) 交回 JS gate | 無識別風險 |  |  |
| openclaw_engine/src/edge_predictor/null_backend.rs | 永遠 Err(NoModel) 預設後端 | 96 | super::* | — | Err(NoModel) | 安全 prod；等同「預測器未啟用」 | 無識別風險 |  |  |
| openclaw_engine/src/edge_predictor/ort_backend.rs | ort (ONNX Runtime 1.24) 三 quantile 模型載入器（feature `edge_predictor_ort`） | 561 | ort::Session, super::* | ONNX 路徑 | trio predictor | tract 缺 TreeEnsembleRegressor；download-binaries 內建 +~20MB dylib | feature-gated；default build 不含 |  |  |
| openclaw_engine/src/edge_predictor/rearrangement.rs | 三值升序確保 q10≤q50≤q90 | 213 | — | (q10,q50,q90) | sorted tuple | 冪等；刻意用 sort 避 median-preserving 不對稱 bias | 無識別風險 |  |  |
| openclaw_engine/src/ml/mod.rs | ML root（OnnxModelManager + Scorer + KellySizer）+ ScorerResult | 42 | 子模組 | — | pub use | 3-tier degradation: ONNX → rule-based → fixed 0.5 | 無識別風險 |  |  |
| openclaw_engine/src/ml/model_manager.rs | ArcSwap ONNX 熱交換 | 163 | arc_swap | SIGHUP + path | 熱換後模型 | 無模型→predict()→None 優雅降級；ort 依賴延後 | 無識別風險 |  |  |
| openclaw_engine/src/ml/scorer.rs | 3-tier scorer（ONNX→rule→0.5 固定） | 129 | super | signal + model | ScorerResult | 從不 block / 從不 panic | 無識別風險 |  |  |
| openclaw_engine/src/ml/kelly_sizer.rs | Fractional Kelly + sample-size 調整 | 281 | — | win_rate + R/R + N trades | qty | <50 trades: 1/8 Kelly, <200: 1/6, ≥200: 1/4；ATR 波動率調整 | 無識別風險 |  |  |
| openclaw_engine/src/ml/registry.rs | model_registry (V023) resolver | 470 | sqlx | (strategy,engine_mode,quantile) | artifact path + meta | Phase 3+ 整合；現 Phase 1a dormant | 無識別風險 |  |  |
| openclaw_engine/src/exit_features/mod.rs | DUAL-TRACK-EXIT-1 Track P 共享型別 re-export | 68 | 子模組 | — | pub use | EXIT-FEATURES-SPLIT-1 2026-04-21 拆 1317→4 檔 | 無識別風險 |  |  |
| openclaw_engine/src/exit_features/core.rs | ExitFeatures 快照 + PhysicalDecision enum | 204 | serde | — | type | Option None = 歷史不足，下游 gate 須 Hold 保守 | 無識別風險 |  |  |
| openclaw_engine/src/exit_features/v2.rs | ExitConfig + non_linear_giveback_fn + physical_micro_profit_lock_v2 | 895 | super::core | ExitFeatures + config | PhysicalDecision | Gate 1 semantics v2 修正：唯有 Gate 4 trailing 合法 Lock | TRACK-P-V2-SWAP-1 已部署 runtime |  |  |
| openclaw_engine/src/exit_features/builder.rs | Tick 時刻 ExitFeatures 組裝（供 Priority 6 消費） | 368 | super::core | PaperState + price_tracker + edge_estimates | Option<ExitFeatures> | TRACK-P-T4-WIRING-1 commit `e95c779` 首次 runtime 接線 | 無識別風險 |  |  |
| openclaw_engine/src/combine_layer.rs | Track P + Track L 退場決策融合（物理 Lock 不可被 ML veto） | 779 | exit_features::* | physical + ml_opt + config | (Decision, ExitSource) | Phase 1a `ml_opt=None` + `ml_override_high=2.0` 雙重保險→永 P-only；4 穩定 exit_source tag | ML override 未來上線需驗證不破 invariant |  |  |
| openclaw_engine/src/edge_estimates.rs | JS shrunk 實現 edge 快照 loader（settings/edge_estimates.json） | 387 | std::fs, HashMap | Python estimator 產出的 JSON | CellEstimate map | 檔案不存在→空集回退 ATR×conf×0.2；set_edge_estimates() 熱更 | PH5-WIRE-1；scheduler 2026-04-24 恢復 |  |  |
| openclaw_engine/src/ai_budget/mod.rs | AI budget module root + pub use | 29 | 子模組 | — | pub use | Fail-closed 月度 USD 預算；三階降級 | 無識別風險 |  |  |
| openclaw_engine/src/ai_budget/tracker.rs | BudgetTracker 核心（hot-reload config + MTD 原子計數 + degrade level） | 897 | sqlx, HashMap | LLM call attempt | DegradeLevel + record 結果 | 寫 PG 失敗→Err→caller 必拒絕；三段 $80/$95/$100 | 897 行；硬編碼占位 pricing 待 4-17 替換 |  |  |
| openclaw_engine/src/ai_budget/pricing.rs | ai_pricing.yaml → model→pricing 載入 | 299 | serde_yaml | YAML | HashMap<model,Pricing> | env OPENCLAW_PRICING_PATH 優先；fail-closed on missing/parse/inactive | 無識別風險 |  |  |
| openclaw_engine/src/ai_budget/config_io.rs | learning.ai_budget_config 讀寫 | 68 | sqlx | scope + new config | BudgetConfig snapshot | 純 sqlx runtime queries | 無識別風險 |  |  |
| openclaw_engine/src/ai_budget/usage_io.rs | learning.ai_usage_log 寫 + MTD 查詢 | 118 | sqlx | call event | insert + aggregate | `ON CONFLICT (time,scope,request_id)` idempotent；月界自動 reset | 無識別風險 |  |  |
| openclaw_engine/src/news/mod.rs | News root + 4 provider + dedup + severity + pipeline + router + guardian/learning impl | 37 | 子模組 | — | pub use | Phase 4 4-07→4-09 整條 | 無識別風險 |  |  |
| openclaw_engine/src/news/provider.rs | NewsProvider trait | 27 | async_trait | — | trait | Mock/CryptoPanic/RSS(CoinTelegraph/GoogleNews) 4 impl | 無識別風險 |  |  |
| openclaw_engine/src/news/cryptopanic.rs | CryptoPanic free tier（28min 最小輪詢）| 248 | reqwest | api_key + since | Vec<RawNewsItem> | 50 req/day quota；URL unit-test 但實際 HTTP 不跑（dev 不燒 quota）| api_key 缺失 → AuthMissing |  |  |
| openclaw_engine/src/news/rss.rs | 通用 RSS（feed-rs）+ CoinTelegraph / Google News 預設 | 310 | feed-rs, reqwest | RSS URL | Vec<RawNewsItem> | parse_feed_xml() 直接單測；fixture XML | 無識別風險 |  |  |
| openclaw_engine/src/news/mock.rs | Mock provider（固定 fixture） | 290 | async_trait | — | 5 條預設含 high severity | 單元測試用 | 無識別風險 |  |  |
| openclaw_engine/src/news/dedup.rs | 標題 SHA1[:16] + 24h 滑動窗口去重 | 162 | sha1, Mutex | title | is_new bool | 純 in-memory 不寫 PG | Mutex 全局鎖可能爭用（新聞吞吐低可接受） |  |  |
| openclaw_engine/src/news/severity.rs | keyword × source 加權（無 LLM） | 207 | — | RawNewsItem | severity 0..1 | Phase 5 會換 LLM；現為確定性字典 | 權重硬編碼 |  |  |
| openclaw_engine/src/news/pipeline.rs | Provider 拉取 → dedup → severity → DB 寫入 | 321 | pool, dedup, severity, router | 定期 tick | 副作用 + ProcessedNewsItem | 三層消費路由屬 4-09 分檔 | 無識別風險 |  |  |
| openclaw_engine/src/news/router.rs | 3 獨立消費者 fan-out（Guardian / Regime / Learning） | 428 | trait objects | ProcessedNewsItem | 3 consumer callbacks | Guardian halt threshold；Regime buffer；Learning sink | 無識別風險 |  |  |
| openclaw_engine/src/news/guardian_impl.rs | GuardianHaltCheck 生產 wrapper（flip session_halted 共享 Arc） | 169 | Arc<AtomicBool> | severity | halted flag | 與 Teacher governance_impl 共享同一 Arc | 無識別風險 |  |  |
| openclaw_engine/src/news/learning_context_impl.rs | LearningContextSink 生產 wrapper（next decision ctx msg） | 232 | Arc atomics | severity + ts | context snapshot | 鬆耦合：news ingest async / tick 同步讀 | 無識別風險 |  |  |
| openclaw_engine/src/news/types.rs | ProviderError + RawNewsItem | 47 | serde | — | pub type | — | 無識別風險 |  |  |

#### 第 7 批：Bybit 交易所層 / WS / Database / Scanner / 持久化 / 其他

| 路徑 | 職責 | 行數 | 關鍵依賴 | 輸入 | 輸出 | 核心設計決策 | 潛在風險 | 理解度 | 備註 |
|---|---|---|---|---|---|---|---|---|---|
| openclaw_engine/src/bybit_rest_client.rs | Bybit V5 REST 基礎 client + HMAC 簽名 | 1725 | reqwest, common::bybit_signer | request params | REST resp + rate limit | 1) GET query string / POST JSON body 簽名 2) header rate limit 追蹤 3) mainnet/testnet/demo base URL | 1725 行遠超 §九 硬上限；部分為 struct/enum 撐篇幅；需拆分 |  |  |
| openclaw_engine/src/ws_client.rs | Bybit V5 公共 WS（kline + trade + 指數退避重連） | 1136 | tokio-tungstenite, common::ws_backoff | WS endpoint | PriceEvent via mpsc | 27 unwrap！主要在 payload parse path；重連配置化 | 27 unwrap/expect 在生產路徑（解析失敗會 panic / log 後退連）|  |  |
| openclaw_engine/src/bybit_private_ws.rs | Bybit V5 私有 WS（HMAC 認證 + auto-reconnect） | 1013 | tokio-tungstenite, common::bybit_signer | api_key/secret + topics | PrivateWsEvent via mpsc | 訂閱 order/execution/position/wallet；同 ws_client backoff | 無識別風險 |  |  |
| openclaw_engine/src/bybit_private_ws_status_writer.rs | 5s 週期 status JSON 寫入（接管 Python listener） | 604 | Arc<AtomicStats>, tmp-then-rename | Execution stats | JSON file atomic write | WS-RETIRE-1 取代 Python 340 行；cancel 時寫 running=false | 無識別風險 |  |  |
| openclaw_engine/src/execution_listener.rs | 私有 WS 事件分派（fills/orders/positions/balance）+ 彙總計數 | 528 | bybit_private_ws | PrivateWsEvent | 回調觸發 + AtomicStats | 回調可驅動 paper state / reconciler / Python IPC | 無識別風險 |  |  |
| openclaw_engine/src/account_manager.rs | Bybit 錢包 + fee rate 查詢（快取） | 837 | bybit_rest_client, parking_lot::RwLock | api query | WalletBalance + fee rate | USDT 權益解析；快取最新狀態 | 無識別風險 |  |  |
| openclaw_engine/src/order_manager.rs | Bybit V5 訂單生命週期（create/amend/cancel/query/execution） | 1554 | bybit_rest_client, instrument_info | OrderReq + instrument spec | resp + error | 提交前 InstrumentInfoCache 驗證 qty/price/min notional；支援所有訂單類型 | 1554 行超 §九 硬上限 |  |  |
| openclaw_engine/src/position_manager.rs | Bybit V5 持倉查詢 + 槓桿/TP-SL 配置（已在第 5 批） | 845 | — | — | — | — | — |  |  |
| openclaw_engine/src/instrument_info.rs | 合約規格快取（lot/tick/min notional 圓整 helper） | 1975 | bybit_rest_client, parking_lot, async_trait | REST instruments-info | 精度 helper | 可定期刷新快取 | 1975 行 — 多數為規格常量表撐篇幅 |  |  |
| openclaw_engine/src/ai_service_client.rs | IPC client to Python AIService（Unix socket JSON-RPC） | 364 | tokio::net UnixStream | method + params | Option<resp> | 100ms connect + 5-15s method TTL；fail-closed 不阻塞引擎 | 無識別風險 |  |  |
| openclaw_engine/src/market_data_client/mod.rs | Bybit V5 公開市場資料 REST（klines/tickers/ob/OI/funding/LSR/ADL/...） | 532 | bybit_rest_client, parsers, types | REST params | 強型別 resp | 全面公共端點；Arc<BybitRestClient> 共用 | 無識別風險 |  |  |
| openclaw_engine/src/market_data_client/parsers.rs | Bybit string-encoded JSON → 強型別解析 | 158 | super::types | raw JSON | typed struct | 純函式；檔案大小紀律抽出 | 無識別風險 |  |  |
| openclaw_engine/src/market_data_client/types.rs | Market data 回應型別 | 194 | serde | — | pub struct | — | 無識別風險 |  |  |
| openclaw_engine/src/market_data_client/tests.rs | Market data client 測試 | 290 | fixtures | — | — | — | 無識別風險 |  |  |
| openclaw_engine/src/platform_client.rs | Bybit V5 平台級（margin/collateral/DCP/transfer/tx log/status/demo fund） | 713 | bybit_rest_client | — | platform resp | DCP 對帳戶安全關鍵；transfer 跨帳戶 | 無識別風險 |  |  |
| openclaw_engine/src/live_authorization.rs | HMAC-SHA256 簽名 authorization.json 讀取 + 驗證 | 620 | hmac, sha2, hex, serde_json | $OPENCLAW_SECRETS_DIR/live/authorization.json | AuthPayload 或 AuthError | 1) 啟動 build_exchange_pipeline + 每 5min re-verify 2) 失效 → engine graceful shutdown 3) LiveDemo 同 Mainnet 嚴格 | 無識別風險 |  |  |
| openclaw_engine/src/live_auth_watcher.rs | Live auth watcher state machine（auto re-spawn / immediate teardown） | 957 | live_authorization, pipeline_slot | 5s poll | respawn/teardown signals | PIPELINE-SLOT-1 Phase 3；Phase 2 teardown-only → Phase 3 state machine | 無識別風險 |  |  |
| openclaw_engine/src/pipeline_slot.rs | PIPELINE-SLOT-1 Phase 2 pipeline slot + Live-scoped teardown | 896 | tokio cancellation_token | — | slot lifecycle | Token 階層：engine_shutdown > live_slot（cancel 只拆 Live） | 無識別風險 |  |  |
| openclaw_engine/src/pipeline_types.rs | 管線快照/狀態型別（IPC + canary + 狀態報告） | 174 | openclaw_core indicators/signals, serde | — | pub struct | 從 tick_pipeline.rs 抽出（RRC-1 E2）保 §九 | 無識別風險 |  |  |
| openclaw_engine/src/persistence.rs | Debounced JSON 寫 + JSONL append audit | 385 | serde, Instant | state + interval | file writes | State: max 1/interval debounce；audit 永附加 | 無識別風險 |  |  |
| openclaw_engine/src/multi_interval_topics.rs | 多時間框架 WS topic 字串建構（純函數） | 315 | — | intervals + symbols | Vec<String> | 無 side-effect；契約被 live subscription set 釘住 | 無識別風險 |  |  |
| openclaw_engine/src/mode_state.rs | 每 engine_mode 獨立狀態（paper/demo/live 隔離） | 426 | config::ConfigStore, bybit_rest_client | — | ModeState | 3E-ARCH 並行；各 ModeState 擁 PaperState+IntentProcessor+Governance+config | 無識別風險 |  |  |
| openclaw_engine/src/drawdown_revoke.rs | G1-06 Drawdown 觸發 HaltSession + 刪 authorization.json | 442 | live_authorization | drawdown event | revoke decision + file delete | 落實原則 #5 #6；5s 內 watcher 偵測並拆 Live；純決策 vs 副作用分拆 | 無識別風險 |  |  |
| openclaw_engine/src/spawn_backoff.rs | Live slot 指數 backoff（防 REST storm） | 345 | — | 失敗次數 | delay ms | 避 Bybit REST 下時每 5s 重試風暴 | 無識別風險 |  |  |
| openclaw_engine/src/restart_kind.rs | 重啟類型 sentinel（manual/auto）偵測 + 消費 | 178 | std::fs | settings/runtime/last_shutdown_kind | RestartKind | 讀後刪；僅 "manual" 精確文字生效 | 無識別風險 |  |  |
| openclaw_engine/src/startup/mod.rs | 啟動輔助（餘額/管線偵測/replay/config 載入/signal handling/banner） | 1126 | 全體 engine | env + TOML | 啟動完成實例 | Wave 1 G1-03 拆 private_ws 後控制檔案大小 | 1126 行接近硬上限 |  |  |
| openclaw_engine/src/startup/private_ws.rs | 私有 WS supervisor spawn + ExecutionListener + status writer wiring | 293 | bybit_private_ws, execution_listener, status_writer | deps | PrivateWsBindings | Demo/LiveDemo 才 spawn；WS-RETIRE-1 取代 Python | 無識別風險 |  |  |
| openclaw_engine/src/tasks.rs | Background 任務集合 spawn（DB writers/fee/instrument/news/teacher/reconciler） | 690 | 全體 engine | bootstrap deps | JoinHandles | supervised_spawn 抽 4+ 重複 tokio::spawn 模式 | 無識別風險 |  |  |
| openclaw_engine/src/tasks/supervised_spawn.rs | 受監管 interval spawner（跳過首 tick / cancellable） | 214 | tokio::time::interval | period + fn | JoinHandle | 統一 select!+interval.tick() 模式 | 無識別風險 |  |  |
| openclaw_engine/src/scanner/mod.rs | Rust 市場掃描器 root（動態 symbol universe） | 21 | 子模組 | — | pub use | 取代 Python market_scanner.py；BTC/ETH pinned | 無識別風險 |  |  |
| openclaw_engine/src/scanner/config.rs | Scanner 配置（schedule/universe/filters/anti-churn/scoring weights） | 397 | serde | TOML | ScannerConfig | 跟隨 BudgetConfig 模式；Meta 版本控制 | 無識別風險 |  |  |
| openclaw_engine/src/scanner/registry.rs | SymbolRegistry（active set + anti-churn + removal cooldown） | 486 | Arc<RwLock> | 掃描結果 | 更新後 set | Pinned（BTC/ETH）不受 anti-churn；min_hold_cycles / challenger_threshold | 無識別風險 |  |  |
| openclaw_engine/src/scanner/runner.rs | 掃描運行器 background task（scan-score-select 30min） | 315 | bybit REST, registry | CancellationToken | ws topic changes + seed | 7 步：fetch tickers→filter→score→positions query→apply→ws sub/unsub→kline bootstrap | 無識別風險 |  |  |
| openclaw_engine/src/scanner/scorer.rs | 4 個 fitness fn (F_ma/F_grid/F_bbrv/F_bkout) + edge bonus + correlation filter | 901 | edge_estimates, market_data_client::TickerInfo | tickers + edge | ScoredSymbol Vec | 純函數無 I/O；BTC-beta/策略/板塊 cap | 901 行接近硬上限 |  |  |
| openclaw_engine/src/scanner/sectors.rs | 板塊 + stablecoin 靜態分類 | 133 | — | symbol &str | sector tag | 純查找表；未知→"other" | 無識別風險 |  |  |
| openclaw_engine/src/scanner/types.rs | 純資料結構（ScoredSymbol/ScanResult/ChurnState） | 168 | serde | — | pub struct/enum | ScoredSymbol 攜全中間值供審計 | 無識別風險 |  |  |
| openclaw_engine/src/strategist_scheduler/mod.rs | Rust tokio 5min strategist periodic configurator | 1166 | ai_service_client, PipelineCommand, sqlx | fills + IPC | UpdateStrategyParams | 單例（R3-1 修復，取代 Python FastAPI 4-worker race）；指數 backoff 5m→30m→60m→4h | 1166 行接近 §九 硬上限 |  |  |
| openclaw_engine/src/strategist_scheduler/persist.rs | 已應用 params PG 持久化（fail-soft） | 446 | sqlx | applied params | DB row | 拆 mod.rs 避 §九 超限 | 無識別風險 |  |  |
| openclaw_engine/src/decision_context_producer.rs | DecisionContextMsg 生產（read-only）+ LinUCB arm selection | 319 | linucb::runtime | signals/indicators/news | DecisionContextMsg try_send | try_send → drop-on-full back-pressure；immutable refs 易測 | 無識別風險 |  |  |
| openclaw_engine/src/feature_collector.rs | IndicatorSnapshot → 34 維 f32 FeatureSnapshot（ML/DB） | 406 | openclaw_core::indicators | IndicatorSnapshot | FeatureSnapshot via mpsc | 1) 31 標量 + 2 regime enum + 1 price 2) 環形 VecDeque cap 3000 3) try_send 非阻塞 | 無識別風險 |  |  |
| openclaw_engine/src/canary_writer.rs | 灰度 JSONL dedicated task（BufWriter + size rotation） | 569 | tokio mpsc 4096-slot, BufWriter | record via try_send | file | 避 event_consumer 熱路徑 fsync stall（2026-04-15 incident）；drop-on-full + rate-limited warn | 無識別風險 |  |  |
| openclaw_engine/src/database/mod.rs | DB module root + pub use + sqlx helpers | 712 | sqlx::postgres | — | pub use + helpers | Optional pool；非阻塞；JSONL fallback on PG 失敗 | 無識別風險 |  |  |
| openclaw_engine/src/database/pool.rs | sqlx::PgPool wrapper + health check + graceful shutdown | 193 | sqlx::postgres, AtomicU32 | config | DbPool Option | 可選 init；graceful on CancellationToken；runtime sqlx::query() 無 compile-time dep | 無識別風險 |  |  |
| openclaw_engine/src/database/migrations.rs | OPENCLAW_AUTO_MIGRATE opt-in Flyway V###__*.sql 自動套用 | 746 | sqlx, Migrator | SQL files | applied rows | 1) ambiguous state→RAISE 不靜默猜 2) 自刻 parser（sqlx 不吃 Flyway）3) seed V001-V023 when 空+canary | V023 postmortem 導致此模組新增；ambiguous detection 複雜 |  |  |
| openclaw_engine/src/database/batch_insert.rs | QueryBuilder push_values + PG 65535 param guard | 355 | sqlx, QueryBuilder | rows | INSERT | chunk=min(65535/columns,10000) | 無識別風險 |  |  |
| openclaw_engine/src/database/aggregators.rs | 1m trade + orderbook 聚合（flush on bucket change） | 486 | — | events | MarketDataMsg flush | Session 11 fix idle writers；UTC-aligned bucket | 無識別風險 |  |  |
| openclaw_engine/src/database/black_swan_detector.rs | 4 signal 投票（MAD/correlation/volume/velocity） on kline close | 536 | indicators | kline close events | RiskLevel escalate | 2/4→Observe 3/4→Upgrade 4/4→Defensive；bar_close only | 無識別風險 |  |  |
| openclaw_engine/src/database/context_writer.rs | decision_context_snapshots 寫入（15 扁平 + JSONB） | 307 | super::batch_insert | DecisionContextMsg | INSERT | dedup by context_id；epoch-0 拒絕 | 無識別風險 |  |  |
| openclaw_engine/src/database/decision_feature_writer.rs | learning.decision_features 寫入（EDGE-P3-1 7a） | 231 | sqlx | DecisionFeatureMsg | INSERT ON CONFLICT DO NOTHING | PK context_id；label_* 由 Python backfill | 無識別風險 |  |  |
| openclaw_engine/src/database/drift_detector.rs | PSI + ADWIN 特徵漂移監控 | 1010 | features.online_latest, observability | stored baseline | drift_events | 非重疊 7 天測試窗（W2 audit）；ADWIN δ=0.05+3 consecutive+30d burn | 1010 行；複雜統計 | |  |
| openclaw_engine/src/database/exit_feature_schema.rs | 7 維 Track P feature name + schema hash 常量 | 93 | — | — | 常量 | 重命名 → hash 旋轉 → 強等檢測不匹配 | 無識別風險 |  |  |
| openclaw_engine/src/database/exit_feature_writer.rs | learning.exit_features 寫入（hypertable PK (context_id,ts)） | 325 | sqlx | ExitFeatureRow | UPSERT | ON CONFLICT DO UPDATE 允許 re-emit 覆寫 | 無識別風險 |  |  |
| openclaw_engine/src/database/experiment_ledger_pg.rs | learning.experiment_ledger CRUD | 295 | sqlx | Hypothesis | id + update | Phase 1 debt（1-14/1-15，F7 audit）清除 | 無識別風險 |  |  |
| openclaw_engine/src/database/fallback.rs | PG 3+ 失敗 → JSONL 檔落盤 | 197 | std::fs | MarketDataMsg | JSONL file | Recovery 手動 scripts/recover_jsonl.sh + COPY FROM | 無識別風險 |  |  |
| openclaw_engine/src/database/feature_writer.rs | features.online_latest UPSERT（34 維 REAL[]） | 169 | sqlx, FeatureSnapshot | FeatureSnapshot | UPSERT | 每 feature_upsert_interval_ms flush | 無識別風險 |  |  |
| openclaw_engine/src/database/market_writer.rs | 10 market.* tables 批量 INSERT | 686 | sqlx, QueryBuilder | MarketDataMsg | INSERT | 3 連續 PG 失敗 → JSONL fallback | 無識別風險 |  |  |
| openclaw_engine/src/database/outcome_backfiller.rs | decision_outcomes 回填（1m/5m/1h/4h/24h return） | 276 | sqlx, market.klines | decision_context_snapshots rows | INSERT outcomes | 每 5min 掃描 ts>25h 未回填 | timeframe '1' vs '1m' 曾致 100% NULL（2026-04-21 `5e2981d` fix） |  |  |
| openclaw_engine/src/database/quality_writer.rs | observability.data_quality_events writer（tick freshness 監控） | 220 | Arc<AtomicU64 last_tick_ms> | tick events | INSERT | F-3 audit fix：simple map + shared atomic | 無識別風險 |  |  |
| openclaw_engine/src/database/rest_poller.rs | Funding / OI / LSR REST 定期輪詢 → market_data_tx | 359 | MarketDataClient | interval config | MarketDataMsg | funding 15min / OI 5min / LSR 15min；non-fatal | 無識別風險 |  |  |
| openclaw_engine/src/database/shadow_exit_writer.rs | learning.decision_shadow_exits 寫入（Combine Layer divergence） | 467 | sqlx | ShadowExitMsg | INSERT | Phase 2+ when `shadow_enabled=true` | 無識別風險 |  |  |
| openclaw_engine/src/database/shadow_fill_writer.rs | learning.decision_shadow_fills 寫入（ε-greedy paper only） | 282 | sqlx | ShadowFillMsg | INSERT | paper-only；parquet_etl 排除 close_tag=shadow_fill:epsilon_greedy | 無識別風險 |  |  |
| openclaw_engine/src/database/trading_writer.rs | 7 trading.* 寫入（signals/intents/fills/position_snapshots/risk_verdicts/orders/order_state_changes） | 728 | sqlx, QueryBuilder | TradingMsg | INSERT | NaN sanitization 共用 | 無識別風險 |  |  |

#### 尾注

- **總計行數實測**：131,120 LOC（不含 target/）
- **測試/非測試比**：test files 約 15k；prod ~116k
- **unwrap/expect 分布**：非測試路徑最集中於 `ws_client.rs` (27)、`bybit_rest_client.rs` (24)、`config/store.rs` (31)、`main.rs` (12)；其他 production path unwrap/expect 多為常數構造或文件存在性驗證。


---

## Part 1B — Python 模組清單（Session 2/5）

> 來源：[.claude_reports/inventory_1b_python_modules.md](.claude_reports/inventory_1b_python_modules.md)
> 涵蓋：app/ 126 檔 + ml_training/ 25 檔 + local_model_tools/ 27 檔（14 stub）+ helper_scripts/ 17 檔 + observer_pipeline/ 10 檔 + io_and_persistence/ 3 檔 + audit/ 1 檔 ≈ ~84,600 LOC。

### 盤點交付物 #1（Python 部分）— srv/app + ml_training + local_model_tools + helper_scripts + observer 模組清單

本文件是 Session 2/5 Python 模組盤點結果。行數實測自 2026-04-24 `wc -l`。職責一段多取自各檔頂 MODULE_NOTE；若僅讀 imports/docstring 而未核實 class body 則在備註或潛在風險欄標「推測」。與 Session 1 Rust 盤點（`.claude_reports/inventory_1a_rust_modules.md`）欄位嚴格一致，後續 session 會交叉引用。

`app/` 相對路徑 = `srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/`。`ml_training/` / `local_model_tools/` / `audit/` 相對 `srv/program_code/`。`helper_scripts/` 相對 `srv/`。observer/IO 相對 `srv/program_code/exchange_connectors/bybit_connector/`。

---

#### 第 1 批：Governance 核心（SM + Hub + Cascade + Events）

| 路徑 | 職責 | 行數 | 關鍵依賴 | 輸入 | 輸出 | 核心設計決策 | 潛在風險 | 理解度 | 備註 |
|---|---|---|---|---|---|---|---|---|---|
| app/governance_hub.py | SM 級聯協調 + ACL 裁決（cascades/event_handlers mixin） | 1014 | state_machine_base, governance_events, cascades, event_handlers | `cascade()` / `acquire_lease()` | CascadeVerdict, lease_id | 1) 原則 #9 幾何性驗證 2) all-or-nothing clone→commit 3) Mixin 拆分保留 API 簽名 | 1014 行接近 §九 1200 硬上限；已拆 cascades/event_handlers 仍偏重 |  |  |
| app/governance_hub_cascades.py | 狀態查詢 + 跨 SM 級聯回調（Mixin） | 811 | governance_events, change_audit_log, utils/time_utils | `get_status()` / `_on_risk_escalation()` | GovernanceStatus, governance_event | 1) Mixin 方式保 API 2) 所有回調鎖外發 | 無識別風險 |  |  |
| app/governance_hub_event_handlers.py | 回調工廠 + wiring 事件連線（Mixin） | 237 | change_audit_log, utils/time_utils | `_make_audit_callback()` / `_wire_callbacks()` | Callable audit sink | 純工廠 + wiring 無狀態；fail-open 語義 | 無識別風險 |  |  |
| app/governance_events.py | 統一治理事件模型（3 dim enum + dataclass） | 262 | enum, dataclass, uuid | — | GovernanceEvent dataclass | 信號中立分類（restrict/expand/neutral）；多源彙聚 | 無識別風險 |  |  |
| app/state_machine_base.py | 3 SM 共享引擎核心（Generic[S] + callback） | 474 | threading, enum, typing | `transition()` | bool or exception | 1) Generic[S] 支援 str/int enum 2) callback 鎖外發防 deadlock | 無識別風險 |  |  |
| app/authorization_state_machine.py | SM-01 授權機（8 態 16 遷移 6 禁 5 守衛） | 654 | state_machine_base | `transition()` | AuthState + authorization_transition audit | 1) auto_approve 分支 2) Terminal: Revoked/Expired/Rejected | Python 與 Rust `sm/auth.rs` 狀態鏡像須手動對齊 |  |  |
| app/decision_lease_state_machine.py | SM-02 決策租約機（9 態 20 遷移 12 禁 5 守衛） | 652 | state_machine_base | `transition()` | LeaseState + lease_transition audit | 1) BRIDGED→terminal 必閉合 2) ACTIVE max 30s TTL | 與 Rust `sm/lease.rs` 雙源；須依 lease_ttl_config SSOT 對齊 |  |  |
| app/risk_governor_state_machine.py | SM-04 6 級風控總督（Normal→CB→MR） | 844 | state_machine_base, enum.IntEnum | `evaluate_risk_context()` | RiskLevel + risk_governor_transition | 1) 升級自動 2) 降級需審批 + min hold time 3) LEVEL_CONSTRAINTS 表 | 與 Rust `sm/risk_gov.rs` 6 級雙源；手動同步風險 |  |  |
| app/lease_ttl_config.py | SM-02 TTL 規範對齊 SSOT + Singleton | 470 | dataclass, enum, json | `get_instance()` / `validate()` | LeaseTTLConfig | SSOT 防 drift（30s vs 60s 歷史偏差）；不可覆蓋列表；規範合規性報告 | §九 登記 `LeaseTTLConfigManager._instance` / `DEFAULT_LEASE_TTL_CONFIG` |  |  |
| app/ttl_enforcer.py | TTL 強制執行 daemon（auto-REJECT/EXPIRE/ESCALATE） | 607 | enum, dataclass, threading | `start_ttl_sweep()` / `check_expired()` | TTLConfig, TTLExpiryAction | daemon sweep 週期檢查；3 分支策略 | daemon thread 無停止信號即 hang |  |  |
| app/earned_trust_engine.py | TTL 階梯狀態機 + 晉升邏輯（T0-T3） | 817 | enum.IntEnum, dataclass, json | `promote()` / `record_downgrade()` | TrustTier + TrustMetrics | 1) T3 auto-renew 1 次上限 2) pending_downgrade 延遲執行 3) 連續 clean 天數追蹤 | 817 行；接近硬上限 |  |  |
| app/recovery_approval_gate.py | 降級恢復審批守衛（observ 期 + multi type） | 583 | dataclass, enum, uuid | `approve_recovery()` | RecoveryRequest + ApprovalStatus | 升級自動；降級需觀察期；多恢復型態 | 無識別風險 |  |  |
| app/live_session_governance.py | Live 模式 SM-01 生命週期 helper | 178 | logging | `_submit_live_governance_request()` / `_freeze_live_governance_auth()` | None (side-effects) | fail-soft 不阻塞 session；延遲查找 GOV_HUB | 依賴 strategy_wiring 全域符號 |  |  |
| app/agent_audit_bridge.py | 5-Agent→審計橋（fail-open 工廠） | 406 | dataclass, logging, json | `make_agent_audit_callback()` | Callable[[str, Any], None] | 1) fail-open 契約 2) 決策/狀態級事件分類 3) 零行為變更 | §九 登記 `_<AGENT>_AUDIT_CB`（放在 strategy_wiring 側）；bridge 本身無狀態 |  |  |
| app/change_audit_log.py | 變更紀錄（誰/何時/批准）append-only | 616 | dataclass, enum, json, threading | `record_change()` / `approve_change()` | ChangeRecord + approval_status | 7 變更型態 + 5 批准狀態；緊急變更事後審查；immutable append-only | 無識別風險 |  |  |
| app/audit_persistence.py | 追加式 jsonl 審計日誌（日期 + size 輪轉） | 549 | dataclass, threading, pathlib, json | `record_change()` / `query_range()` | audit event persisted | 立即 flush 不緩衝；損壞行 skip 不 silent drop | 無識別風險 |  |  |
| app/truth_source_registry.py | 模式聲明 + 認知誠實儲存（TTL 陳舊） | 977 | dataclass, enum, json, threading | `register_claim()` / `record_falsification()` | PatternClaim + confidence | 1) 認識論級別上限 per 來源 2) TTL 自動過期 3) 只讀查詢 | 977 行接近硬上限 |  |  |
| app/data_source_enforcer.py | 未標記數據阻擋 fail-closed | 589 | dataclass, enum, typing | `tag()` / `reject_untagged()` | DataSourceTag | 來源自動分類（API→FACT, search→INFERENCE）；frozen tag | 無識別風險 |  |  |
| app/incident_event_model.py | 5 級事件 + 事故記錄（NOTICE→CRITICAL） | 614 | dataclass, enum, threading | `record_incident()` / `apply_policy()` | IncidentRecord + IncidentActionType | 策略引擎自動觸發 SM 轉換；不可刪改 | 無識別風險 |  |  |
| app/auth.py | 認證配置 + token 解析 + failure 追蹤 | 281 | fastapi, dataclass, os.environ | `_load_auth_credentials()` / `_resolve_api_token()` | Settings + AuthenticatedActor | 1) IP-level 鎖定 5/15m 2) 跨平台 secrets 解析 3) timing-safe 比較 | settings singleton reload 契約；2000 IP 上限 OOM 防衛 |  |  |
| app/perception_data_plane.py | 統一感知資料平面（FACT/INFERENCE/HYPOTHESIS 標註 + freshness） | 601 | threading, uuid, enum | `record(data_item, cognitive_level, source_type)` | QueryResult + quality score | 未標註 inference 禁進決策鏈（EX-07 §1）；freshness FRESH→RECENT→STALE→EXPIRED | 淺讀推測；learning_history consumer / drift detect 未必全接線 |  | T2.11 governance |
| app/risk_manager.py | ARCH-RC1 1C-3-D shim over RiskViewClient | 52 | risk_view_client | `RiskManager()` | REGIME_TIME_MULTIPLIERS dict | 1) 純 shim 無邏輯 2) REGIME 常數留存 | 禁止再加邏輯；新代碼改 RiskViewClient | 1 | DEAD-PY-2 殘留 |

#### 第 2 批：Main + Legacy 聚合 + 5 個 sibling routes（Wave A-D 拆分結果）

| 路徑 | 職責 | 行數 | 關鍵依賴 | 輸入 | 輸出 | 核心設計決策 | 潛在風險 | 理解度 | 備註 |
|---|---|---|---|---|---|---|---|---|---|
| app/main.py | FastAPI 主入口 + snapshot identity 穩定編譯 + runtime bridge | 567 | main_legacy (as base), runtime_bridge, state_compiler | GET/POST API routes | ResponseEnvelope[T] JSON | 1) snapshot identity 不變性（讀路徑不刷新）2) runtime 事實層疊加 3) 確定性重編譯；monkey-patches `_patched_read`/STORE/compile_state | main.py 同時承擔 monkey-patch 入口 + 子路由 include_router 聚合，責任偏重 |  |  |
| app/main_legacy.py | Core singleton + Settings + middleware + 5-way `register_*_legacy_routes` 聚合 | 468 | fastapi, slowapi, auth, state_models, state_store, state_compiler | — | Settings / STORE / app / limiter 4 singleton + 3 helpers + 4 middleware | 1) reload 安全契約（settings 留此檔）2) CORSMiddleware + slowapi Limiter 3) 465-470 行 `register_*(app)` 聚合 5 sibling | §九 4 singleton 登記；monkey-patch 入口（18 檔 `from . import main_legacy as base`）；reload 測試契約必保持 | 4 |  |
| app/main_snapshot_stable.py | 相容性入口（純 re-export app from main） | 14 | main | — | app (re-exported) | empty | 無識別風險 |  |  |
| app/auth_legacy_routes.py | 3 認證路由（login/logout/check）+ 5/min 限速 | 128 | fastapi, slowapi, auth, auth_routes_common, main_legacy as base | POST /api/v1/auth/login | JSONResponse + cookie | 5/min rate limit；IP-level 鎖定；constant-time token 驗證 | 無識別風險 |  |  |
| app/auth_routes_common.py | auth 路由共用 helpers（IP 鎖定 + cookie + timing attack 防衛） | 224 | fastapi, hmac, asyncio, auth | `check_ip_lockout()` / `set_auth_cookie()` | None (side-effects) | read-check-write 原子性；HttpOnly + Secure cookie；timing attack 防衛 | 無識別風險 |  |  |
| app/control_legacy_routes.py | 15 control/operator 寫入路由 | 493 | fastapi, control_ops, pydantic, main_legacy as base | POST /api/v1/control/demo/arm | ResponseEnvelope[DemoTransitionData] | monkey-patch 安全間接查找（`base.STORE.xxx()`）；envelope 模式 | 無識別風險 |  |  |
| app/gui_legacy_routes.py | 5 GUI/HTML 靜態頁面路由 | 81 | fastapi, pathlib, starlette, main_legacy as base | GET /login, /console, /trading | FileResponse HTML | no-cache headers 防陳舊；client 端 cookie 判定 | 無識別風險 |  |  |
| app/learning_legacy_routes.py | 19 learning + PnL 路由 | 553 | fastapi, learning_ops, pnl_ops, state_models, main_legacy as base | POST /api/v1/input/observation | ResponseEnvelope[various] | 讀/寫/管理/PnL/自動管線 5 類；monkey-patch 安全 | 無識別風險 |  |  |
| app/system_legacy_routes.py | 13 系統/health 只讀路由 | 330 | fastapi, control_ops, pnl_ops, main_legacy as base | GET /api/v1/system/overview | ResponseEnvelope[OverviewData] | 章節/控制面/能力矩陣/產品族；DB 池健康；liveness probe | 無識別風險 |  |  |

#### 第 3 批：Governance / Live / Risk / Settings Routes（非 legacy sibling）

| 路徑 | 職責 | 行數 | 關鍵依賴 | 輸入 | 輸出 | 核心設計決策 | 潛在風險 | 理解度 | 備註 |
|---|---|---|---|---|---|---|---|---|---|
| app/governance_routes.py | Governance REST 14 routes（auth/lease/risk/oms） | 1172 | fastapi, pydantic, hmac, governance_hub | POST /api/v1/governance/auth/request | JSON GovernanceResponse | 1) 原則 #3 lease-based 非同步 2) hmac 簽名授權檔 | 1172 行接近硬上限；已拆 extended/promotion |  |  |
| app/governance_extended_routes.py | 審計批准 + 租約 + 事件 + OMS + H0（12 routes） | 585 | governance_routes, fastapi | POST /api/v1/governance/audit/approve/{change_id} | dict[str, Any] | lazy `_get_*()` 避免循環 dep；fail-soft | 無識別風險 |  |  |
| app/governance_promotion_routes.py | 策略漸進放權管線 3 端點 | 240 | governance_routes, threading | GET /api/v1/governance/promotion-pipeline/status | PromotionGate JSON | 單例 lazy + 線程鎖；DB 同步備份 | 無識別風險 |  |  |
| app/live_session_routes.py | Live session 控制 14 routes（start/stop/pause/close） | 1449 | fastapi, ipc_state_reader, live_session_governance, ipc_dispatch | POST /api/v1/live/session/start | JSON session status | 1) 雙重門控 operator + live_reserved 2) EA-PERSIST 信任恢復 3) fail-closed | **1449 行超過 §九 1200 硬上限** — 須拆分 |  |  |
| app/live_trust_routes.py | TTL 階梯續期 + HMAC 簽名 authorization.json | 845 | earned_trust_engine, fastapi, hmac | POST /api/v1/live/auth/renew | authorization.json 簽名檔 | 1) T0-T3 4 階晉升 2) HMAC-SHA256 與 Rust `live_authorization.rs` 對接 3) 5min re-verify | 與 Rust HMAC key/payload schema 契約單點漂移風險 |  | LIVE-GATE-BINDING-1 |
| app/risk_routes.py | 12 risk API routes（config CRUD + runtime status + agent_adjust） | 694 | fastapi, risk_view_client, ipc_client | GET /api/v1/risk/config?engine=demo | RiskConfig JSON | 全讀路徑走 IPC `get_risk_config`；寫路徑 IPC `update_risk_config` patch | 寫路徑契約須與 Rust `ipc_server/handlers/risk.rs` 欄位一致 |  |  |
| app/settings_routes.py | GUI 設定 CRUD（operator/display/cost） | 474 | fastapi, pydantic, urllib | POST /api/v1/settings/operator | 設定 JSON | 設定拆 3 domain；部分走 IPC 部分走檔 | 推測；未驗 IPC/檔切分正確性 |  |  |
| app/phase2_strategy_routes.py | Phase 2 策略工具包外觀（TD-02 split facade） | 86 | strategy_wiring + _read/_write/_ai routes re-export | re-export imports | backward-compat facade | 所有 import 透過 re-export 鏈有效 | import 順序重要（_ai before _read） |  |  |
| app/phase4_routes.py | Phase 4 儀表板骨架 9 routes（4-00 skeleton） | 897 | IPC get_phase4_status, static HTML | GET /api/v1/phase4/status | phase4 status JSON（4 模組交通燈） | fail-closed：IPC down→grey；無硬編碼路徑 | 4-01~4-21 子任務尚未填色（skeleton only） |  |  |
| app/ai_budget_routes.py | AI 預算 API（status / upsert / monthly 限制） | 219 | ipc_client `get_ai_budget_status`, `record_ai_usage` | GET /api/v1/ai/budget/status | 預算餘額 + 降級等級 | 三段 $80/$95/$100 降級；月重置 | 推測；配置兩側契約對齊 |  |  |
| app/engine_capabilities_routes.py | Engine capabilities IPC 讀（build_capabilities / risk_config） | 254 | ipc_client, ipc_dispatch | GET /api/v1/engine/capabilities | capabilities JSON | lazy singleton `_IPC_CLIENT`；一次查 engine build info | 無識別風險 |  |  |
| app/layer2_routes.py | Layer 2 AI API 10 routes（trigger/session/cost） | 451 | Layer2CostTracker, Layer2Engine, ShadowDecisionConsumer | POST /api/v1/ai/layer2/trigger | session detail + cost summary | ARCH-RC1 1C-3-F：Paper 走 IPC，consumer 按需構造 | cost_tracker lazy init |  |  |
| app/attribution_routes.py | 交易歸因查詢 routes | 177 | trade_attribution, fastapi | GET /api/v1/learning/attribution | 分解因子 JSON | 讀取 `trade_attribution` 內部快照 | 推測；caller 未全驗 |  |  |
| app/edge_estimator_routes.py | Edge estimator 手動觸發 + 狀態讀 | 134 | edge_estimator_scheduler.trigger_now | POST /api/v1/learning/edge-estimator/trigger | 觸發 ack + mtime | 暴露 `trigger_now()` 繞過 1 小時 cadence | 無識別風險 |  |  |

#### 第 4 批：Paper / Strategy / Scout / ML / Shadow Routes

| 路徑 | 職責 | 行數 | 關鍵依賴 | 輸入 | 輸出 | 核心設計決策 | 潛在風險 | 理解度 | 備註 |
|---|---|---|---|---|---|---|---|---|---|
| app/paper_trading_routes.py | Paper trading API 30 routes facade | 1088 | paper_trading_wiring re-export, ipc_dispatch | POST /api/v1/paper/submit | ResponseEnvelope (is_simulated=True) | TD-03 拆分：facade + wiring re-export；粘性 stop flag 區分 user stop vs pause | 1088 行接近硬上限；IPC command wrapper `_ipc_command` 與 live_session_routes 重複（ipc_dispatch 已抽但殘留） |  |  |
| app/strategy_read_routes.py | 策略讀取 16 GET routes（kline/indicator/signal） | 707 | Rust reader priority, Python fallback | GET /api/v1/strategy/kline/{symbol} | klines/indicators/signals JSON | Rust-first for klines；Python KlineManager stub 降級 | stale fallback data 無告警 |  |  |
| app/strategy_write_routes.py | 策略寫入 6 POST routes（activate/pause/stop） | 231 | strategy IPC client, ORCHESTRATOR | POST /api/v1/strategy/{name}/activate | IPC ack | Python fallback，Rust IPC 為主路徑；fire-and-forget | IPC error→log warning 不崩 |  | DYNAMIC-RISK-1 |
| app/strategy_ai_routes.py | AI 諮詢 + Telegram + Demo 讀取 14 routes | 849 | BybitClient (httpx), TELEGRAM | POST /api/v1/strategy-ai/consult | AI status + telegram stats + demo data | PYO3-ELIMINATE-1 Phase 2：pure Python httpx；§九 `_BYBIT_CLIENT` lazy | lazy None check 每 call 重複；Demo connector 已 deprecated | 2 |  |
| app/strategist_history_routes.py | 策略師已應用參數歷史（V019+V020 schema） | 701 | learning.strategist_applied_params | GET /api/v1/strategist/history | history rows + summary + 7d 效果 | STRATEGIST-HISTORY-OBSERVABILITY-1；auto-tune + manual promote 兩源 | 7d edge effect join trading.fills 有 lag |  |  |
| app/scout_routes.py | ScoutAgent REST API 5 routes | 722 | ScoutAgent, MessageBus, IntelObject | POST /api/v1/scout/intel | intel/alert list + status | token-based auth；POST 推送外部 intel | ScoutAgent/MessageBus 必須由 wiring 注入 |  |  |
| app/ml_routes.py | ML registry routes（INFRA-PREBUILD-1 Part B 5 routes） | 401 | learning.model_registry | GET/POST /api/v1/ml/{model_registry,model_info,model_promote} | registry list/info/promote | Operator-gate state machine；`canary_status` 需 explicit `confirm:true` + retirement_reason | Phase 1a 全回 404 / rows=0（registry 空） |  |  |
| app/shadow_fills_routes.py | Shadow fill consumer 讀取（EDGE-P3-1 7c） | 445 | learning.decision_shadow_fills | GET /api/v1/shadow/fills | shadow fill rows + promotion gate | ε-greedy paper exploration rows；off-policy only | paper default OFF (PAPER-DISABLE-1)→n=0 |  |  |
| app/backtest_routes.py | BacktestEngine REST（POST /run + GET） | 420 | BacktestEngine (stub), KlineManager (stub), TruthSourceRegistry | POST /api/v1/backtest/run | BacktestResult | backtest_mode=True forced；sharpe>1.0 + trades≥10→auto TruthRegistry inject | §九 `_backtest_engine` 懶加載；Python BacktestEngine 已 stub，結果全 zero-filled |  |  |
| app/experiment_routes.py | 實驗 ledger CRUD routes | 342 | experiment_ledger, fastapi | POST /api/v1/experiment | experiment row | §九 `_ledger` 懶加載 via `get_experiment_ledger()` | 無識別風險 |  |  |
| app/evolution_routes.py | 策略進化 routes（調用 EvolutionEngine） | 255 | evolution_engine, fastapi | POST /api/v1/evolution/trigger | evolution result | §九 `_evolution_engine` 懶加載 via `get_evolution_engine()` | EvolutionEngine 結果可信度未驗；見 evolution_engine.py |  |  |

#### 第 5 批：5-Agent 業務層 + Multi-Agent Framework

| 路徑 | 職責 | 行數 | 關鍵依賴 | 輸入 | 輸出 | 核心設計決策 | 潛在風險 | 理解度 | 備註 |
|---|---|---|---|---|---|---|---|---|---|
| app/base_agent.py | 5-Agent 公共基類（lifecycle + audit + cost tracker） | 255 | AgentRole enum, MessageBus, audit_cb | ctor(role, bus, audit_cb) | start/pause/stop, get_stats() | 零行為改動：僅提取重複骨架；子類 init 必須呼叫 parent | None hardcoded |  | E5-P1-4 |
| app/multi_agent_framework.py | 5-Agent 通訊協議 + lifecycle + MessageBus | 1137 | AgentRole, MessageType, DataQualityLevel enum | pub/sub message struct | msg routing + state transition | Guardian 永遠勝 Strategist（EX-06 §9）；fact/inference/hypothesis marking；TYPE_CHECKING guard | 1137 行接近硬上限 |  |  |
| app/analyst_agent.py | 交易結果分析 + pattern discovery + L2 升級 | 834 | ROUND_TRIP_COMPLETE msg, OllamaClient/Qwen | TradeRecord list | PatternInsight (winning/losing) | >20 samples 才觸發 L2；Ollama 不可用→heuristic；fail-closed | 推測；實際 L2 升級路徑未手動追蹤 |  |  |
| app/strategist_agent.py | AI 增強信號評估 + TradeIntent 產出 | 1170 | IntelObject, local_llm_factory, H1-H4 chain | Scout intel + H1/H3/H4 verdicts | TradeIntent | Shadow mode = 僅記錄不產出；H1-H4 拆分完整；shadow=False live（strategy_wiring:243） | 1170 行接近硬上限 |  |  |
| app/guardian_agent.py | 風控審查（5 檢查 + dynamic risk） | 587 | TradeIntent, RiskVerdict | intent + EventAlert | APPROVED/REJECTED/MODIFIED | fail-closed：unavailable→default REJECTED；Guardian 優於 Strategist | 無識別風險 |  |  |
| app/executor_agent.py | 訂單執行包裝 + quality feedback | 630 | APPROVED_INTENT msg, IPC `submit_order` | intent from Guardian | ExecutionReport | `_shadow_mode=True` hardcoded（ExecutorConfig default，executor_agent.py:156 + strategy_wiring.py:468） | **違反原則 #3**：shadow→live 切換流程 + Rust IPC SubmitOrder 整合契約缺；G3-02 Wave 2 重構 |  | CLAUDE.md §三 3 大 Verified 發現 (3) |
| app/scout_worker.py | 後台定時掃描 daemon（30 min 間隔） | 194 | scan_fn callback | interval_seconds | daemon thread call scan_fn | 薄薄 E1 觸發層；情報路由在 ScoutAgent | daemon flag not cleared on hang |  |  |
| app/strategist_models.py | StrategistAgent data models + heuristic（§14.1 拆分） | 167 | StrategistConfig, EdgeEvaluation | config + intel | edge eval result | Pure fn + data def；零副作用 | min_relevance 0.3 / heuristic fallback 0.6 |  |  |
| app/strategist_fast_channel.py | 緊急 intent 構建（close_all / flash_crash） | 93 | TradeIntent class | trigger str + symbols list | emergency intent list | Pure fn；呼叫者管 `_emergency_mode` flag | Unknown trigger→skip (fail-closed) |  |  |
| app/shadow_decision_builder.py | H chain → Paper Engine 橋樑 | 395 | H trusted verdict, IPC client | observer verdict + H decision | paper order via IPC | is_simulated=True；system_mode/execution_state 不變；IPC fail→silent drop (fail-open) | fail-open 與原則 #6「失敗默認收縮」緊張 |  | ARCH-RC1 1C-3-F |

#### 第 6 批：Layer 2 AI + LLM + H-Gates

| 路徑 | 職責 | 行數 | 關鍵依賴 | 輸入 | 輸出 | 核心設計決策 | 潛在風險 | 理解度 | 備註 |
|---|---|---|---|---|---|---|---|---|---|
| app/ai_service.py | Rust IPC JSON-RPC listener + 5 Agent handler 分派 | 1258 | asyncio UnixServer, 5 handlers | Rust engine JSON-RPC request | EdgeEvaluation / verdict / PatternInsight JSON | 長度前綴 JSON-RPC；multi-worker 安全（僅 1 worker 綁定）；per-handler TTL；fail-closed：error trunc 200 | **1258 行超過 §九 1200 硬上限** — 須拆分 |  | R01-7, LLM-ABC-MIGRATION-1 |
| app/ai_service_feedback.py | DB 反饋路徑（pattern + reject rate） | 205 | pattern_insights / risk_verdicts | AnalystAgent patterns + guardian verdict | DB writes (fail-open) | 兩條路徑均 fail-open：DB error 不阻 IPC | 無識別風險 |  | R-06-v2 |
| app/layer2_engine.py | L2 深度推理核心 Agent 迴圈 | 730 | Haiku L1 triage, Sonnet/Opus L2, Anthropic SDK | market state + account + decisions | Recommendation + ShadowDecision | L1 Haiku quick→L2 iter；session budget dual limit；budget_exceeded state；當日 hard cap $2 | 無識別風險 |  | DOC-08 §4 |
| app/layer2_tools.py | L2 Agent 工具 8 個（get/search/submit） | 906 | SearchProvider ABC, Anthropic schema | market/account state + search query | recommendation + insight record | 4-tier search degradation（Perplexity→Ollama→DuckDuckGo） | 906 行接近硬上限 |  |  |
| app/layer2_types.py | L2 data models + const + SearchProvider ABC | 477 | dataclass, ABC | — | Layer2Config, Layer2Session, Recommendation | pricing table + 30d re-verify reminder；ADAPTIVE_TIERS ROI bands | 無識別風險 |  |  |
| app/layer2_cost_tracker.py | L2 成本追蹤 + adaptive budget + pricing | 726 | cost_state.json persist | claude_usd / search_usd / session_usd | daily spend + adaptive multiplier | $2/day hard cap（DOC-08 §4）；7d ROI tier-based boost | PnL attribution lag（fill 追蹤） |  |  |
| app/local_llm_factory.py | LocalLLMClient ABC factory（Ollama ↔ LMStudio） | 417 | urllib, LOCAL_LLM_PROVIDER env | provider name | OllamaResponse-shaped object | LM Studio shim 鏡面 OllamaClient surface；0 改動 call-site | env 未知 fallback Ollama |  | LLM-ABC-MIGRATION-1 ✅ 2026-04-20 |
| app/ollama_client.py | Ollama HTTP client（subprocess 取代） | 506 | urllib, Ollama /api/generate /api/chat | model + prompt + temp | OllamaResponse (text, latency_ms) | max_retries=0（CLAUDE.md 硬邊界）；timeout enforced | model unavailable→success=False |  |  |
| app/llm_call_wrapper.py | 5-Agent 統一 LLM 呼叫封裝 | 176 | ollama client, cost_tracker | signal / intent / event | ollama response wrapper | call_ollama_judge_edge/classify/generate；cost provider="ollama" | L0/L1 邊界保留 |  | E5-P1-4 |
| app/api_budget_manager.py | 月度 API 預算 + 分層冷卻（L1.5/L2） | 250 | api_budget_state.json, threading | tier + call_ts | can_call bool + monthly spend | L1.5 cooldown 1800s / L2 cooldown 3600s | UTC calendar month reset |  |  |
| app/h0_gate.py | 本地確定性 <1ms SLA 門控 | 971 | health + risk snapshot | symbol + category | H0GateCheckResult (allowed, reason) | 5 個子檢查順序 fail-fast；熱路徑純計算無 I/O；Rust `core::h0_gate` 鏡像 | 與 Rust H0Gate 雙源；須確保語意與閾值同步 |  | P1-16, <1ms SLA |
| app/h1_thought_gate.py | AI 調用前確定性判斷（complexity + cooldown） | 185 | cost_tracker, cooldown dict | intel object + stats | should_call_ai bool | complexity threshold 0.3；30s 同幣種 cooldown；`_H1_COOLDOWN_MAX_SIZE=1000` memory safety | 無識別風險 |  | §14.1 拆分 |
| app/h4_validator.py | AI 輸出結構驗證（confidence/has_edge/reason） | 103 | pure fn | parsed dict | bool (valid/invalid) | confidence [0,1] range；reason non-empty；action enum valid；fail-closed | 無識別風險 |  | §14.1 拆分 |
| app/model_router.py | H3 Model tier routing（l1_9b/l1_27b/l2） | 292 | complexity score, cache, budget checker | signal complexity + symbol | model tier string | l1_9b<0.5 / l1_27b 0.5-0.8 / l2≥0.8；L2 cache TTL 1h 200 entries cap | 無識別風險 |  | §14.1 拆分 |

#### 第 7 批：Wiring + Paper + Scanner + Regime

| 路徑 | 職責 | 行數 | 關鍵依賴 | 輸入 | 輸出 | 核心設計決策 | 潛在風險 | 理解度 | 備註 |
|---|---|---|---|---|---|---|---|---|---|
| app/strategy_wiring.py | Phase 2 singletons + DI 接線（12+ singletons） | 912 | local_model_tools (stubs), multi_agent_framework, bybit_demo_connector | module-load-time init | initialized instances | KLINE_MANAGER / INDICATOR_ENGINE / SIGNAL_ENGINE / ORCHESTRATOR + 5 agents + MessageBus；**ExecutorAgent `config=ExecutorConfig()` 在 line 468 使默認 shadow=True** | §九 登記 12+ singletons；循環 import 風險；ExecutorAgent 硬編碼 shadow（G3-02 重構目標） | 3 | CLAUDE.md §三 3 大 Verified 發現 (3) |
| app/paper_trading_wiring.py | Paper 模組單例 + DI（ARCH-RC1 1C-3-F 後） | 529 | Rust IPC state reader | RISK_MANAGER, RiskConfig | ENGINE=None stub（Rust owns paper） | PAPER_STORE deprecated；Rust 為 paper state 權威 | legacy import site 依 None guard |  | ARCH-RC1 1C-3-F |
| app/paper_trading_metrics.py | paper PnL metrics 計算（win_rate/sharpe/dd） | 528 | fills list + balance series | engine_mode + strategy_name | win_rate, sharpe, max_dd, pnl_factor | realized_pnl（非 fee）；per-symbol PnL 配對；rolling avg smooth over N trades | 無識別風險 |  | Paper→Live gate input |
| app/paper_live_gate.py | Paper→Live 正式門控（GAP-M4） | 738 | GateCheckResult, threshold config | engine snapshot + 7d metrics | GateStatus enum (passed/failed/pending) | Operator approval required；6 項檢查 duration/trade count/win rate/sharpe/dd/pf | 與 Rust live gate 協同；須與 LIVE-GATE-BINDING-1 對齊 |  | DOC-08 §11 |
| app/scanner_rate_limiter.py | 掃描器速率限制（5 min 間隔） | 342 | ScannerConfig, audit callback | can_scan check | scan lifecycle (pending/active/complete/failed) | fail-closed：超限直接拒絕；error cooldown 10 min | Rust scanner 取代後 Python 側用途縮減 |  | T2.22 GAP-L3 |
| app/symbol_category_registry.py | Bybit symbol→category 啟動快取（方案 A） | 247 | urllib, Bybit /v5/market/instruments-info | API call | category dict + tickSize/qtyStep 快取 | 原則 #10 確定性；原則 #6 刷新失敗不阻啟動；TTL 6 小時 | 無識別風險 |  |  |
| app/market_regime.py | 市場體制形式化（TRENDING_UP/DOWN/RANGING/SQUEEZE） | 706 | threading, HurstHysteresis | K 線 + Hurst 指數 | MarketRegimeSnapshot + RegimeTransition | GAP-M6：多時間框架 + 歷史追蹤 + 衝突檢測；線程安全 | Hurst 閾值 0.60/0.40 硬編碼 |  |  |
| app/hurst_hysteresis.py | Hurst 滯後過濾器（防 regime 震盪） | 129 | dataclass | Hurst 指數 | 確認 regime | Appendix B.2.1：H>0.60 連 6 bar→trending；6 根 bar = 6 小時假設 | 計數衰減速率硬編碼 |  |  |
| app/atr_tracker.py | 純價格歷史追蹤器（ATR 推斷 + 尖刺檢測） | 153 | time | symbol + price tick | ATR + spike info | 從 risk_manager.py 拆出；Rust engine 有自己的 PriceHistoryTracker | Spike 閾值硬編碼 |  | Python bridge/工具專用 |
| app/portfolio_risk_control.py | 組合相關性風控（0.7 + 30% 儲備） | 557 | threading, dataclass | 持倉 + 回報 | 相關性矩陣 + 風險度量 | EX-01 §6：硬限制不可 AI/P2 調；30% 儲備緩衝恆定 | 與 Rust `core::portfolio.rs` 雙源，語意須一致 |  |  |
| app/trade_attribution.py | 交易歸因（ALPHA/TIMING/SIZING/EXECUTION/COST/LUCK） | 958 | dataclass, threading | 已完成交易 | 歸因因子分解 + skill_ratio | 原則 5.8 可解釋；原則 5.12 skill vs luck；線程安全 | 與 Rust `core::attribution.rs` 雙源 |  | 支撐 L2 假設生成 |
| app/reconciliation_engine.py | 對賬引擎（Paper vs Demo/Exchange） | 948 | threading, dataclass | 本地 order/position/fill + 外部狀態 | 差異分類 + 事件觸發 | EX-02 §14：不改交易狀態只判定；發現不一致冷凍優先 | 與 Rust `position_reconciler/` 雙源 — 職責切分未完全畫清 |  |  |
| app/grafana_data_writer.py | Grafana 監控（PnL 快照 + 系統健康） | 283 | threading, psycopg2 | Rust IPC 快照 + system_health | PG `paper_pnl_snapshots` + `system_health` | Rust 已直寫 fills/signals；本檔補 paper_pnl + system_health | PG 連接池隱式依賴；secrets 路徑硬編碼 |  |  |

#### 第 8 批：Learning / Experiment / Estimator / Evolution / Promotion

| 路徑 | 職責 | 行數 | 關鍵依賴 | 輸入 | 輸出 | 核心設計決策 | 潛在風險 | 理解度 | 備註 |
|---|---|---|---|---|---|---|---|---|---|
| app/learning_auto_pipeline.py | 自動審核包構建 + AI 問題生成 + 審核決策執行 | 827 | main_legacy as base, state_compiler | 運行狀態 + 掃描指令 | 審核包 + AI 問卷 | 原則 7：自動生成僅創建審核包，不自動寫正式記錄；base 間接存取 singleton | 單例間接存取脆弱性 |  | Wave E 拆分 |
| app/learning_records.py | 觀察/經驗/假設/實驗 CRUD（寫） | 626 | main_legacy as base, auth, state_compiler | 4 類 payload | 更新快照 | 寫全走 `_base.STORE` / `_base.get_latest_snapshot()` 間接存取 | 依單例存取 |  | Wave E 拆分 |
| app/learning_queries.py | 審核隊列 / 觀察流 / 實驗隊列（只讀） | 106 | — | 快照 | 視圖（最近 N + 摘要） | 純讀；不寫不依 `_base.STORE` | 無識別風險 |  | Wave E 拆分 |
| app/learning_ops.py | Learning 門面（re-export） | 47 | learning_records, learning_auto_pipeline, learning_queries | — | 向後兼容 re-export | 僅 re-export；新代碼應直接 import 子模塊 | re-export 層疊維護負擔 |  |  |
| app/learning_tier_gate.py | L1-L5 分級門控（Analyst Agent 進化） | 712 | threading, dataclass | 觀察數 / 經驗數 / 假設驗證結果 | 晉升事件 | 原則 12 持續進化；單向（L1→L5）；晉升寫 learning_tier_promotion audit | 晉升條件複雜；原則 11 嚴格不可降級 |  |  |
| app/experiment_ledger.py | 假設生命週期（提出→確認→證偽） | 974 | threading, db_pool, json | 假設提議 + 觀察證據 | 結案 + TruthSourceRegistry 注入 | §九 `_ledger` 懶加載；REFUTED 不注入；線程安全 | 974 行接近硬上限 |  |  |
| app/edge_estimator_scheduler.py | James-Stein 估計器自動排程（每小時） | 716 | threading, fcntl, ml_training/james_stein_estimator | demo/live_demo 模式 | settings/edge_estimates*.json | daemon 每小時；P1-7 B；**leader election via fcntl 防 uvicorn 4-worker race**；engine 重啟才熱重載 | §九 `_scheduler / _scheduler_lock / _LEADER_LOCK_FD` 登記；cost_gate 綁定未啟（grand_mean 條件未達） |  | memory: project_edge_scheduler_stalled.md 2026-04-24 修復 |
| app/evolution_auto_scheduler.py | 策略進化自動排程（參數優化 + 假設過期清理） | 485 | threading, datetime, EvolutionEngine (stub) | 引擎實例 | 進化結果 + 晉升建議 | §九 `_scheduler` 懶加載；原則 7 隔離 backtest_mode=true；fail-open | EvolutionEngine 已 stub；假設過期邏輯硬編碼 1 小時 |  |  |
| app/promotion_pipeline.py | 策略漸進放權（LEARNING→PAPER_SHADOW→DEMO_ACTIVE→LIVE_PENDING→LIVE_ACTIVE） | 636 | threading, dataclass | 策略指標 | 晉升/降級事件 | 6-01~03：LIVE_ACTIVE 需 operator 批准；轉換寫審計 | 晉升門檻無數據驅動；LIVE_ACTIVE 無自動指標閾值 |  |  |
| app/pnl_ops.py | PnL 與經營指標操作（錄入 + 摘要 + 快照） | 303 | main_legacy as base, auth, state_compiler | PnL payload | 快照更新 | `_base.STORE` 間接存取；從 main_legacy 拆分 | unrealized vs realized 邏輯混淆風險 |  |  |
| app/control_ops.py | 交易控制操作門面（demo arm/disarm 等） | 668 | main_legacy as base, auth, state_compiler | 控制指令 | 風控決策 + 執行狀態 | `_base.STORE` 間接存取；Rust 為執行權威 | 控制邏輯分散 Rust+Python 同步風險 |  |  |
| app/alert_router.py | 多通道告警扇出 | 87 | telegram_alerter, webhook_alerter | alert_*() methods | 扇出 side-effect | 獨立失敗語義；按通道分發 | 無識別風險 |  |  |
| app/webhook_alerter.py | HTTP POST webhook 告警 | 176 | urllib, hmac, threading | send() | bool success | 多端點扇出；HMAC 簽名；指數退避重試 | 告警失敗不影響交易 |  |  |
| app/telegram_alerter.py | Telegram Bot API 告警 | 172 | urllib, threading | send() | bool success | Bot token + chat_id；速率限制；統計計數器 | 無識別風險 |  |  |

#### 第 9 批：ml_training/（25 檔 Phase 2-4 訓練管線）

| 路徑 | 職責 | 行數 | 關鍵依賴 | 輸入 | 輸出 | 核心設計決策 | 潛在風險 | 理解度 | 備註 |
|---|---|---|---|---|---|---|---|---|---|
| ml_training/__init__.py | 根模組 docstring（Phase 2 LightGBM+ONNX） | 12 | — | — | — | 純文檔 | 無識別風險 |  |  |
| ml_training/quantile_reports.py | 三分位驗收報告（EDGE-P3-1 Stage 2 §6.2） | 344 | numpy, dataclass | QuantileTrainingResult | 驗收結論（should_ship/shadow_only/no_ship） | 六項指標門檻；<200 強制 no_ship；≥500 + 全過才 ship | 門檻組合複雜；6 項獨立不相關 |  |  |
| ml_training/dl3_go_no_go.py | DL-3 Go/No-Go 決策報告（AI-E 簽核用） | 370 | dataclass, datetime | AbResult + 運營 metadata | Markdown 報告 + GO/NO_GO/PENDING_DATA | 決策矩陣：PROMOTE+快+便宜→GO；AUC delta 0.01 閾值 | AUC delta 相對小對噪聲敏感 |  |  |
| ml_training/label_generator.py | 標籤生成（ATR 歸一化 PnL + winsorization） | 86 | numpy, dataclass | net_pnl + atr | 標籤 + is_extreme | y = clip(net_pnl / max(atr, atr_floor), -Y_MAX, Y_MAX)；ATR_FLOOR 動態 q=0.05；1st/99th winsorize | ATR_FLOOR 每樣本重算低效；MAD 3.5× 硬編碼 |  |  |
| ml_training/leakage_check.py | 特徵洩漏白名單檢查 | 78 | logging | 特徵名列表 | 通過 / 違反列表 | 禁 outcome_/future_/backfilled 前綴；允許 sma_/ema_/atr_；strict mode | 洩漏規則手工維護風險 |  | 重要防線 |
| ml_training/run_training_pipeline.py | 端到端訓練管線編排器 | 526 | dataclass, pathlib | 策略/symbol/regime + 配置 | PipelineResult | 兩路徑：(A) 傳統 regression (B) EDGE-P3-1 Stage 2 分位（pooled vs per-symbol）| 路徑選擇複雜；pooled 樣本不一定夠 |  | Stage 5.5 hook for model_registry |
| ml_training/linucb_trainer.py | LinUCB 批次訓練（rebuild A/b 充分統計量） | 345 | numpy, psycopg2 | decision_context_snapshots + decision_outcomes | learning.linucb_state UPSERT | Phase 4 4-05：A=λI+Σxxᵀ / b=Σrx；feature_schema_hash 與 Rust 4-04 byte 對齊 | schema_hash 漂移無日誌；BYTEA codec 依 numpy 字節序 |  |  |
| ml_training/realized_edge_stats.py | 實現邊際統計（per (策略, 幣種) 往返 PnL） | 526 | json, dataclass | trading.fills | 往返 PnL 分布 | P1-17：winsorize ±5000 bps；防禦性 ln(exit/entry)>0.5 gate；模組級 clamp 審計 | winsorize 5000 未驗證；漂變 gate 經驗值 |  |  |
| ml_training/james_stein_estimator.py | James-Stein 收縮（跨幣種部分池化） | 555 | json, math | realized_edge_stats 結果 | learning.james_stein_estimates + edge_estimates.json | Phase 5：B_j=min(1,(p-2)/n·σ²_j/‖raw-grand_mean‖²)；proxy cells sync-label 策略注入；top-level key 格式 | hot-reload 無 IPC；proxy cell 複雜 |  | G1-01 修復 2026-04-24 |
| ml_training/parquet_etl.py | Parquet ETL（PG→Parquet via DuckDB） | 574 | pathlib, re | decision_context_snapshots + features | Parquet 檔案 | 17-feature 規範順序 byte-for-byte aligned；SEC-B02 SQL 注入防；DuckDB 列式 | 特徵順序不能改（綁 Rust schema_hash）|  |  |
| ml_training/quantile_trainer.py | 三分位 LightGBM（q10/q50/q90 獨立 pinball） | 670 | numpy, lightgbm (lazy) | decision_features + labels | QuantileTrainingResult（三 booster）| per-quantile alpha；CPCV + strategy-specific embargo；feature_schema_hash 驗證 | 訓練成本 3 倍；early_stopping_rounds 50 硬編碼；670 行偏大 |  | EDGE-P3-1 Stage 2 主線 |
| ml_training/cpcv_validator.py | 組合清洗交叉驗證（4-fold CPCV + embargo） | 360 | numpy | 特徵矩陣 + 標籤 | CPCVResult（fold metrics + power）| 4-fold + 策略 embargo（ma 24/bb 4/arb 8/grid 72）；power<0.5 標記參考 | embargo 依 strategy 分類；fold 數固定 4 |  |  |
| ml_training/thompson_sampling.py | Thompson Sampling（NIG posterior）跨策略資源 | 488 | numpy | paper 回報列表 | NIGPosterior(μ,λ,α,β) | Layer 2 優化；Empirical Bayes init；數值安全邊界（_MIN_LAMBDA 1e-6）| Rust Phase 4 推理延後；數值穩定性依超參 |  |  |
| ml_training/dl3_ab_runner.py | DL-3 A/B 跑批（Phase 3 Scorer baseline vs +DL-3） | 451 | dataclass, lazy imports | 訓練資料 + DL-3 預測 | AbResult（決策 + AUC delta）| fail-soft：缺依/DSN 無→INSUFFICIENT_DATA；AUC delta 0.01 門檻 | 訓練成本高 |  |  |
| ml_training/linucb_arm_migration.py | LinUCB warm-start（V1→V2 / V2→V1） | 636 | numpy, psycopg2 | linucb_state 記錄 | learning.linucb_migrations | Phase 4 4-06；BYTEA codec 與 4-05 byte 對齊；schema_hash 漂移 raise；parent n_pulls 不足 cold-start | 數學複雜；feature_schema_hash 單點失敗 |  |  |
| ml_training/onnx_exporter.py | ONNX 導出（LightGBM→ONNX tract/ort） | 385 | numpy, pathlib | booster 或 QuantileTrainingResult | ONNX 檔 + symlink 原子換 | (1) 舊單模型 (2) EDGE-P3-1 三分位；精度驗證 max|LGB-ONNX|<1e-3 | ONNX 版本兼容性（tract vs ort） |  |  |
| ml_training/edge_cluster_analysis.py | 邊際聚類分析（k-means on JS 估計） | 441 | json, dataclass | edge_estimates.json 或 DB 估計 | settings/edge_clusters.json | Phase 5 5-02~03；k=2/3 分層；多維（shrunk_bps, combined_ev, win_rate, n）| k 啟發式；特徵工程未驗 |  |  |
| ml_training/linucb_shadow_compare.py | LinUCB 影子比較 + regret 自動回滾 | 300 | numpy, psycopg2 | 兩 arm-space 決策日誌 | ShadowCompareResult + rollback 操作 | champion/challenger 1-2 週 shadow；sigma pooled stddev/√N；auto-rollback 歸檔 challenger | Rust 推理尚未就位；delta 檢驗簡單 |  | LINUCB-SHADOW-RETENTION（memory）|
| ml_training/model_registry.py | Model registry Python writer（INFRA-PREBUILD-1 B） | 430 | hashlib, psycopg2 | ONNX artifact + metadata | learning.model_registry 行 | V023 hypertable；ON CONFLICT UPDATE；canary 狀態機（shadow→promoting→production→retired）；DB 不可用 fail-soft | Phase 1a 空態；滿 200 label 自動填 |  |  |
| ml_training/edge_label_backfill.py | 邊緣標籤回填（label_net_edge_bps） | 456 | psycopg2, argparse | unlabeled decision_features + trading.fills | UPDATE label | EDGE-P3-1 Stage 1；join entry+close fills；split qty-weighted；grid VWAP；排除 orphan/shadow；§8.2 驗收 demo 48h>95% | 標籤計算複雜 case |  |  |
| ml_training/scorer_trainer.py | LightGBM scorer（CPCV + embargo） | 242 | numpy, lightgbm, dataclass | decision features + labels | model.pkl + metrics.json | Phase 3b；regression；CPCV 4-fold + 策略 embargo；power guard | 無 ONNX（Phase 4 才進） |  |  |
| ml_training/optuna_optimizer.py | Optuna TPE 參數優化（層 1 of 2）| 946 | optuna (JournalFileStorage), psycopg2 | 策略 + 參數空間 + backtest fn | ml_parameter_suggestions 表 | Layer 1 優化；non-PG 存儲（E5-O4 審計）；參數更新 via IPC | 946 行接近硬上限；Optuna 4.x JournalFileBackend 命名變 |  |  |
| ml_training/weekly_report_generator.py | Phase 4 週度審查報告 | 614 | psycopg2, datetime | 7d 統計 | Markdown 報告 | DoD 門檻：A Sharpe+0.15 / C AUC≥0.55 / E exec_rate≥80%；fail-soft | Phase 4 4-20 尚未運行；614 行偏大 |  |  |
| ml_training/dl3_foundation.py | DL-3 基礎模型包裝（TimesFM/Chronos zero-shot） | 391 | asyncio, dataclass | K 線 + metadata | learning.foundation_model_features | 異步；5min 超時→fail-soft；不阻塞交易 | 模型可用性依本地部署 |  |  |
| ml_training/calibration.py | 等調校準 + CQR（EDGE-P3-1 Stage 2） | 204 | numpy, sklearn, pickle | raw_predictions + actual_outcomes | calibrator + metrics (ECE/brier) | (1) binary outcome isotonic (2) CQR 單邊 marginal（Romano 2019 + (n+1) 有限樣本修正）| Isotonic out_of_bounds="clip" 假設 |  |  |

#### 第 10 批：local_model_tools/（Rust 遷移後 14 檔 stub + 3 真實計算）

| 路徑 | 職責 | 行數 | 關鍵依賴 | 輸入 | 輸出 | 核心設計決策 | 潛在風險 | 理解度 | 備註 |
|---|---|---|---|---|---|---|---|---|---|
| local_model_tools/__init__.py | 根模組 docstring（read_only / execution_state=disabled 硬邊界） | 22 | — | — | — | 純文檔 | 無識別風險 |  |  |
| local_model_tools/backtest_engine.py | STUB: BacktestEngine（Rust `core::backtest` 權威） | 87 | backtest_types | BacktestConfig + ohlcv | BacktestResult (zero-filled) | run() 返回警告；evolution_engine 相容 | 完全 stub；evolution 依虛假結果 |  |  |
| local_model_tools/backtest_types.py | STUB: Backtest dataclass 定義（zero-fill default） | 140 | dataclass | — | BacktestConfig, BacktestTrade, BacktestResult | Rust 遷移後保留 dataclass | 無識別風險 |  |  |
| local_model_tools/cognitive_modulator.py | L0 決策門檻調製（真實計算） | 193 | dataclass, logging | 連虧/weekly PnL/regret_data | 調製參數 + EMA 平滑 | EMA α=0.3；max 單因子非求和；連虧忽略負向壓力 | 與 Rust `core::cognitive.rs` 雙源 |  | Layer 2 L0 fallback |
| local_model_tools/evolution_engine.py | 策略參數網格搜索（真實計算） | 567 | itertools, threading, BacktestEngine (stub) | ParameterGrid + BacktestEngine | EvolutionResult | 原則 7 backtest_mode=True 強制；不改 live/paper；max_combinations 50 | 網格指數爆炸；依 BacktestEngine stub 結果無效 |  |  |
| local_model_tools/ewma_vol_estimator.py | EWMA 波動率（真實計算） | 159 | defaultdict, math | symbol + log_return | σ + regime (low/normal/high) | Report §5.3：lambda 按 timeframe；σ²(t)=λσ²(t-1)+(1-λ)r² | regime 閾值 0.6/1.5 硬編碼 |  |  |
| local_model_tools/hurst_exponent.py | Hurst 指數 R/S（真實計算） | 164 | math | 價格序列 | H ∈ [0,1] | R/S 統計；H>0.60 趨勢 / H<0.40 均值回歸；數據不足回 0.5 | lag 範圍 10-100 硬編碼 |  |  |
| local_model_tools/indicator_engine.py | STUB: IndicatorEngine（Rust `openclaw_core::indicators` 權威） | 64 | indicators/base | symbol + timeframe | 空字典 | 全 getter 回空；get_conservative_atr()=None | 完全 stub |  |  |
| local_model_tools/kline_manager.py | STUB: KlineManager（Rust `openclaw_engine::market_data_client` 權威） | 230 | dataclass | symbol + timeframe | 空列表 | KlineBar 結構保留無實例 | 完全 stub |  |  |
| local_model_tools/local_llm_client.py | LocalLLMClient ABC（Ollama/LM Studio 抽象） | 251 | abc, dataclass | prompt + metadata | LLMResponse | 統一介面 generate/is_available/get_model_info；cost=0 本地 | 實現（Ollama/LMStudioProvider）在 app/；原則 §七 #2 LocalLLMClient 抽象乾淨 |  |  |
| local_model_tools/market_scanner.py | STUB: MarketScanner（Rust `openclaw_engine::scanner` 權威） | 88 | dataclass | scan_interval_sec + min_volume | 空列表 | SymbolOpportunity 結構保留；scan() 永遠回空 | 完全 stub |  |  |
| local_model_tools/position_sizer.py | STUB: PositionSizer（Rust `position_manager+risk_checks` 權威） | 99 | dataclass | position 參數 | zero qty | Python 類保留以兼容 strategy_auto_deployer | 完全 stub |  |  |
| local_model_tools/signal_engine.py | STUB: SignalEngine（Rust `core::signals` 權威） | 81 | — | signal ctx | 空 | getter 回空；legacy wiring 用 | 完全 stub |  |  |
| local_model_tools/signal_generator.py | STUB: SignalGenerator（Rust `core::signals::rules` 權威） | 269 | — | ctx | None | evaluate() 恒 None；Signal/SignalRule 類保留 | 完全 stub；269 行為 class 定義撐 |  |  |
| local_model_tools/strategy_auto_deployer.py | STUB: AutoDeployer（Rust scanner + orchestrator + lifecycle 權威） | 114 | — | — | 空 | 方法全 no-op 或回空 | 完全 stub；strategy_read/write_routes 仍 import |  |  |
| local_model_tools/strategy_orchestrator.py | STUB: Orchestrator（Rust `orchestrator + strategies` 權威） | 152 | — | — | 空 | getter 回空；ORCHESTRATOR singleton 兼容 | 完全 stub |  |  |
| local_model_tools/strategies/__init__.py | 策略 package root | 16 | — | — | — | 純文檔 | 無識別風險 |  |  |
| local_model_tools/strategies/base.py | STUB: Strategy 抽象基類（Rust `strategies/` 權威） | 167 | abc | — | — | 純介面；行為無操作；STRATEGY_IDLE 常數 | 完全 stub |  |  |
| local_model_tools/indicators/__init__.py | Indicators package root | 40 | — | — | — | 純文檔 | 無識別風險 |  |  |
| local_model_tools/indicators/base.py | STUB: IndicatorBase（abstract compute() 回 None） | 30 | abc | — | — | 純介面 | 完全 stub |  |  |
| local_model_tools/indicators/atr.py | STUB: ATR（Rust `volatility` 權威） | 57 | indicators/base | period=14 | — | 僅 ctor；compute 回 None | 完全 stub |  |  |
| local_model_tools/indicators/bollinger_bands.py | STUB: BB（Rust `volatility` 權威） | 46 | indicators/base | period=20, std_mult=2.0 | — | 僅 ctor | 完全 stub |  |  |
| local_model_tools/indicators/extended.py | STUB: KAMA/Donchian/EWMA Vol/Hurst（Rust `indicators` 權威） | 124 | indicators/base | period 參數 | — | 多 class；全 stub | 完全 stub |  |  |
| local_model_tools/indicators/macd.py | STUB: MACD（Rust `momentum` 權威） | 40 | indicators/base | 12/26/9 | — | 僅 ctor | 完全 stub |  |  |
| local_model_tools/indicators/moving_averages.py | STUB: SMA/EMA（Rust `trend` 權威） | 77 | indicators/base | period=20 | — | 僅 ctor；兩 class | 完全 stub |  |  |
| local_model_tools/indicators/rsi.py | STUB: RSI（Rust `momentum` 權威） | 41 | indicators/base | period=14 | — | 僅 ctor | 完全 stub |  |  |
| local_model_tools/indicators/stochastic.py | STUB: Stochastic（Rust `momentum` 權威） | 42 | indicators/base | k/d/slow_k | — | 僅 ctor | 完全 stub |  |  |

#### 第 11 批：Infrastructure（IPC / DB / REST / State / Shared）

| 路徑 | 職責 | 行數 | 關鍵依賴 | 輸入 | 輸出 | 核心設計決策 | 潛在風險 | 理解度 | 備註 |
|---|---|---|---|---|---|---|---|---|---|
| app/ipc_client.py | JSON-RPC 2.0 IPC 客戶端（Unix socket 連 Rust engine）| 818 | asyncio, json, socket | method + params + timeout | JSON-RPC result dict 或 exception | 1) 指數退避（base=1s max=30s factor=2）2) 連續 3 失敗→ai_available=false 3) per-method timeout（strategist=15s/analyst=30s/conductor=10s/default=5s）4) asyncio.Lock 序列化 5) 原子計數器生成 req_id | DEFAULT_SOCKET_PATH `/tmp/openclaw/engine.sock` 硬編碼（env `OPENCLAW_IPC_SOCKET`）；fallback 後無自動恢復 |  | E5-P1-5 基礎 |
| app/ipc_dispatch.py | IPC 派發輔助（E5-P1-5 孤兒抽取）| 242 | ipc_client, ipc_error_handler | method + params + slot_key | result dict 或 HTTPException | one-shot `one_shot_ipc_call` + lazy singleton `get_or_connect_shared_client`；零行為變動 | §九 `_SHARED_IPC_SLOTS / _SHARED_SLOT_LOCK` 登記 |  |  |
| app/ipc_error_handler.py | IPC 錯誤分類 → HTTPException 統一 | 199 | ipc_client (lazy), fastapi | exception 物件 | HTTPException(504/503) | Lazy 匯入例外類型；fallback built-in ConnectionError/TimeoutError；永不吞異常 | 無識別風險 |  |  |
| app/ipc_state_reader.py | 讀 Rust engine pipeline_snapshot*.json（3E-5 per-engine）| 356 | threading, json, pathlib | data_dir + engine 名 | paper_state / latest_prices dict | 每引擎快照 + 主相容檔；TTL=2s；staleness threshold=60s；失敗回 None/empty | 檔案 I/O 每 2s；過期檔無清理 |  | R06-B / 3E-5 |
| app/risk_view_client.py | Rust RiskConfig 權威 IPC 視圖（ARCH-RC1 1C-3）| 435 | ipc_client | field name (GUI flat) | Rust nested RiskConfig | GUI→Rust 欄位對映 `_GLOBAL_TO_RUST`；讀 IPC 快取；寫走 `update_risk_config` patch | Python 風控邏輯已全刪；讀寫契約複雜；GUI 需同步改欄位 1C-3-C |  | DEAD-PY-2 |
| app/runtime_bridge.py | Runtime 快照橋接（外部 JSON → system_mode/execution_state） | 186 | pathlib, json, hashlib | snapshot 檔案路徑（env `OPENCLAW_RUNTIME_SNAPSHOT_FILE`）| `system_mode_fact` / `execution_state_fact` dict | 缺檔 fallback 本地 guarded-demo；fail-safe；overlay 而非覆蓋 | snapshot 檔損壞無驗証；fallback 沉默 |  |  |
| app/bybit_rest_client.py | Python httpx Bybit V5 REST client（drop-in 取代 PyO3 BybitClient） | 914 | httpx, HMAC-SHA256, pathlib | REST params + API credentials | dict（snake + camelCase 混） | LIVE-GUARD-1：憑證優先級 param>env>slot 對齊 Rust；同步阻塞 FastAPI handler；HMAC 依 Bybit spec | response shape 混合；credential fallback 複雜 |  | PYO3-ELIMINATE-1 Phase 2 |
| app/bybit_demo_connector.py | Bybit 工具（DEAD-PY-2 後僅 round_qty/round_price） | 97 | math | qty/price + 精度參數 | rounded float | 向下取整保守；精度推 qty_step | 無識別風險 |  | BybitDemoConnector 交易類已刪 |
| app/bybit_demo_sync.py | Bybit Demo API 定期拉 executions/positions/wallet → PG | 331 | threading, Demo API httpx | Demo credentials | DB INSERT (is_demo=true) | Demo/Paper 寫同表分 flag；interval 可配；pgpass 讀 secrets | threading 無鎖保護 |  |  |
| app/db_pool.py | PostgreSQL 連接池（ThreadedConnectionPool singleton） | 161 | psycopg2.pool, os.environ | PG 連接參數 | 可重用連接或 None | 連接池大小 env PG_POOL_MIN/MAX 配置；優雅降級；跨平台 secrets 路徑（OPENCLAW_SECRETS_ROOT）| §九 `_pool` 登記；連接耗盡返 None caller 必檢 |  |  |
| app/state_compiler.py | 狀態編譯器 compile_state + 所有衍生欄位 + 系統常量 | 635 | hashlib, json, threading, weakref | raw state dict | compiled output dict | 純函數；常量白名單（OBSERVATION/LESSON/CONFIDENCE categories）；衍生欄位 lazy compute | 被 main.py monkey-patch；weakref 緩存策略未詳 |  | 從 main_legacy 拆分 |
| app/state_store.py | JSON 狀態存儲（thread-safe atomic write） | 402 | tempfile, json, threading, pathlib | state dict | 檔讀寫（原子 rename） | tempfile→rename；build_default_state() 初值；monkey-patch 相容註記 | monkey-patch 死碼警告（見檔頂）；檔 I/O blocking |  |  |
| app/state_models.py | Pydantic 狀態模型（RequestEnvelope/ResponseEnvelope 等） | 391 | pydantic | request JSON | Pydantic model instance | 純資料；Literal type aliases；Generic TypeVar；model_dump() JSON 相容 | 無識別風險 |  | 新 Pydantic 建議放此檔（§九）|
| app/state_helpers.py | 狀態操作輔助（request 指紋 + idempotency + audit） | 159 | hashlib, json, fastapi | RequestEnvelope + snapshot | fingerprint + cached/fresh resp | SHA256 fingerprint；idempotency TTL=24h max=500；revision check | revision check 在 lock 前（併發下可能偽陽，line 50-56 註記）|  |  |
| app/shared_types.py | Python↔Rust IPC 共享型別（RiskLevel/OrderState/H0GateConfig/PriceEvent） | 234 | dataclass, enum, json | Rust struct（遷移期） | Python dataclass/Enum（1:1 mirror） | asdict() JSON 序列化；原始定義與此模塊共存；遷移後統一 | 雙定義 legacy + shared 同步風險 |  |  |
| app/_path_setup.py | sys.path 注入（5 層上溯至 program_code/）| 46 | os, sys | — | sys.path 修改 | 冪等；原則 7 路徑隔離 | 全域 side-effect；app/ 路由檔常 `import _path_setup` noqa |  |  |
| app/utils/time_utils.py | 統一 now_ms() 毫秒時間戳 | 10 | time | — | int (ms since epoch) | 消除 `int(time.time()*1000)` 重複；純工具 | 無識別風險 |  |  |

#### 第 12 批：Helper Scripts（canary / db / phase4 / research）

| 路徑 | 職責 | 行數 | 關鍵依賴 | 輸入 | 輸出 | 核心設計決策 | 潛在風險 | 理解度 | 備註 |
|---|---|---|---|---|---|---|---|---|---|
| helper_scripts/canary/canary_comparator.py | Canary 比較器（R07-3 Rust vs Python shadow JSONL） | 660 | canary_schema | 2 JSONL 檔 | report JSON（PASS/WARNING/CRITICAL/MISSING）| (timestamp_ms, symbol) join；tolerance tier SIMPLE(1e-6)/RECURSIVE(1e-2)/COMPLEX(5e-2)/BALANCE(1e-4)；邊界豁免 0.5% | tolerance 1e-10→1e-6 寬鬆化跨語言 |  | R07-3 |
| helper_scripts/canary/canary_schema.py | Canary JSONL schema + validator | 263 | dataclass, json, enum | CanaryRecord | validated + schema version | SCHEMA_VERSION="1.0.0"；TOLERANCE_* tier；known_missing_indicators 白名單 | tolerance 值硬編碼多 tier |  |  |
| helper_scripts/canary/engine_watchdog.py | Engine watchdog（R07-6 snapshot staleness + 3 strike rollback） | 699 | fcntl, json, subprocess | snapshot freshness | crash/recovery event + restart 命令 | STALE=45s；grace=120s startup；3 strike window=3600s；指數退避（60/120/300/600/3600s）；WATCHDOG-DNS-CLASSIFY-1 | DNS vs crash 分類未完整 |  | P0-9 RCA 驗證 |
| helper_scripts/canary/replay_runner.py | Canary 回放（REST klines→合成 ticks→JSONL） | 450 | urllib, json | symbol + days + timeframe | engine_results.jsonl + shadow_results.jsonl | 合成 4 ticks/bar OHLC；MAX_BARS/REQUEST=200；TICKS/BAR=4；5 symbols × 7 days | 合成 tick 無真實流動性；simulator TODO |  |  |
| helper_scripts/db/audit_migrations.py | Migration audit（SQL 期望 vs DB 實況）| 350 | psycopg2 (late), re, glob | migration 目錄 + DB | drift/missing/mismatched report | 正則解析 SQL；比對 information_schema；Guard A/B/C | 正則解析 SQL 易誤判；V023 postmortem 曾發現 silent-noop |  | §七 新 SQL migration 規範強制 |
| helper_scripts/db/check_migration_status.py | DDL 遷移狀態（V001-V005 + EXPECTED dict）| 162 | psycopg2 | DSN 或 POSTGRES_* | PASS/FAIL per migration | schema/table 白名單；env var DSN 簡便 | EXPECTED dict 手工維護落後 |  |  |
| helper_scripts/db/counterfactual_exit_replay.py | Counterfactual 出場回放（reads trading.fills）| 1216 | numpy, psycopg2 | 時間窗 | counterfactual outcome 報告 | **1216 行超 §九 1200 硬上限** | 須拆分 |  |  |
| helper_scripts/db/counterfactual_v2_parity.py | Counterfactual v1 vs v2 parity check | 168 | psycopg2 | 時間窗 | parity 報告 | 驗證 TRACK-P-V2-SWAP-1 bit-parity | 無識別風險 |  |  |
| helper_scripts/db/fresh_start_reset.py | 開發資料清理（fills/orders/intents/...）| 573 | argparse, psycopg2 | `--execute --confirm DATE` | TRUNCATE + archive to `learning.linucb_state_archive` | 3 模式 --report-only/--dry-run/--execute；LinUCB archive 前清；PRESERVE_TABLES 白名單 | TRUNCATE 危險；無 transaction rollback；confirm string 簡單 |  |  |
| helper_scripts/db/passive_wait_healthcheck.py | Healthcheck（17+ 檢查 + cron 6h） | 1822 | psycopg2 | — | status report | **1822 行遠超 §九 1200 硬上限**；單檔多 check；[1]-[17] 各類別 | 須拆分；維護成本高 |  | G6 audit 框架核心；CLAUDE.md §三 healthcheck 來源 |
| helper_scripts/db/phase1a_c_readiness.py | Phase 1a→C labels 累積檢查 | 195 | psycopg2 | — | 就緒狀態 | 輕量 readiness checker | 無識別風險 |  | P1-7 C |
| helper_scripts/phase4/dl3_go_no_go.py | DL-3 Go/No-Go 報告 CLI 薄包裝 | 34 | sys, pathlib | --ab-result-json + --output | Markdown 報告 | 實際邏輯在 ml_training/dl3_go_no_go.py；本檔 CLI 入口 | 無識別風險 |  |  |
| helper_scripts/phase4/weekly_report.py | Phase 4 週報 CLI 薄包裝 | 25 | sys, pathlib | --output | Markdown 報告 | 實際邏輯在 ml_training/weekly_report_generator.py | 無識別風險 |  |  |
| helper_scripts/research/bb_breakout_threshold_sweep.py | BB Breakout 信號級 threshold sweep（P1-11 Phase 1） | 719 | psycopg2, numpy | symbol list + params | sweep 結果表 | multi-role audit 修正：ddof=1 + df-aware t_crit + Bonferroni + cluster-SE + leak-free Donchian shift(1)；QC/MIT/PM/PA/FA 5 agent audit | 719 行接近硬上限 |  | P1-11 close-out 2026-04-24 |
| helper_scripts/schema_diff.py | SQL schema 差異比對 | 300 | psycopg2, re | 期望 vs DB | diff 報告 | 輕量 diff checker | 無識別風險 |  |  |
| helper_scripts/golden_dataset_gen.py | Golden dataset 生成器（fixture） | 402 | json, psycopg2 | 時間窗 | JSONL fixture | 測試用金標準資料 | 無識別風險 |  |  |
| helper_scripts/clean_restart_flatten.py | Clean restart 輔助 | 183 | pathlib, shutil | archive 目錄 | 清理動作 | 輔助 clean_restart.sh；flatten 歷史歸檔 | 無識別風險 |  |  |

#### 第 13 批：Observer Pipeline + IO Persistence + Audit

| 路徑 | 職責 | 行數 | 關鍵依賴 | 輸入 | 輸出 | 核心設計決策 | 潛在風險 | 理解度 | 備註 |
|---|---|---|---|---|---|---|---|---|---|
| readonly_observer_pipeline/bybit_build_decision_packet.py | 彙總 snapshot + ws_smoke + ws_runtime_facts + preflight → decision packet | 234 | json, pathlib | 4 JSON 快照檔 | decision_packet JSON | 來源引用；freshness ts；should_query_ai=false；risk_flags 統一 | 快照缺失 load_json 回 None 無故障信號 |  |  |
| readonly_observer_pipeline/bybit_build_ws_runtime_facts.py | WS runtime facts 彙整（接管 Python listener 退役後） | 161 | json, pathlib | Rust 寫的 status JSON | ws_runtime_facts JSON | WS-RETIRE-1 後讀 Rust writer 檔（`listener_version=rust-v1`） | 無識別風險 |  | CLAUDE.md §三 WS-RETIRE-1 |
| readonly_observer_pipeline/bybit_full_readonly_observer_cycle.py | Observer 串行執行（4 private_rest + 1 guard + 4 post_guard） | 141 | subprocess, json | 9 script 路徑 | cycle_latest.json | 硬編碼 PRIVATE_REST_STEPS / GUARD_SCRIPT / POST_GUARD_STEPS；fail→stop | 路徑用 OPENCLAW_SRV_ROOT 脆弱；subprocess 無 timeout |  | D21/D22 |
| readonly_observer_pipeline/bybit_observer_pipeline.py | 5 stage 串行編排器 | 61 | subprocess, json | script 路徑 | JSON(overall_ok + steps) | 每 stage run_cmd()；early exit；無 state persist | 無識別風險 |  |  |
| readonly_observer_pipeline/bybit_observer_verdict_to_postgres.py | Observer verdict JSON → trading_raw.observer_verdicts | 118 | json, subprocess | verdict_latest.json | DB INSERT | docker exec psql；JSONB payload；自動建表 + INDEX | SQL 字串 quote 手工逃逸；docker exec 依賴 container |  |  |
| readonly_observer_pipeline/bybit_readonly_status_writer.py | Observer status JSON writer | 122 | json, pathlib | 雜訊 status 指標 | readonly_status_latest.json | 純寫檔 | 無識別風險 |  |  |
| readonly_observer_pipeline/bybit_next_phase_handoff.py | 階段交接（cycle 後判定下一 phase） | 139 | json, pathlib | cycle_latest.json | next-phase 判定 JSON | 純邏輯；無 DB | 無識別風險 |  |  |
| readonly_observer_pipeline/bybit_readonly_preflight.py | Readonly preflight 檢查 | 61 | json, subprocess | preflight 輸入 | preflight_latest.json | 薄檢查 | 無識別風險 |  |  |
| readonly_observer_pipeline/bybit_runtime_state_resolver.py | 運行狀態解算器（彙整 8 JSON → runtime_state） | 191 | json, pathlib | 8 JSON 快照檔 | runtime_state JSON | freshness_reference_ts_ms；age_state()；business_event_state 集成 v5；FRESH=15min | 快照缺失 load_json 回 {}；過期進 degraded 可能非 code bug |  | MODULE_NOTE v5 |
| readonly_observer_pipeline/bybit_build_system_snapshot.py | 系統快照建構 | 128 | json, pathlib | 多源輸入 | system_snapshot JSON | 薄彙整器 | 無識別風險 |  |  |
| io_and_persistence/bybit_decision_packet_to_postgres.py | Decision packet JSON → trading_raw.decision_packets | 96 | json, subprocess | packet_latest.json | DB INSERT | docker exec psql；JSONB；自動建表 + INDEX | SQL quote 手工逃逸 |  |  |
| io_and_persistence/bybit_load_ws_jsonl_to_postgres.py | WS JSONL → PG（業務細節未詳讀） | 112 | json, subprocess | JSONL 檔 | DB INSERT | 推測：與 decision_packet 同模式 | 推測；未完整讀 |  | 未讀檔內 |
| io_and_persistence/bybit_normalize_latest_snapshot_to_postgres.py | Snapshot 正規化 → latest 表（業務細節未詳讀） | 261 | json, subprocess | snapshot JSON | DB INSERT/UPSERT | 推測：snapshot normalize | 推測；未完整讀 |  | 未讀檔內 |
| audit/counterfactual_exit_audit.py | Counterfactual 出場審計（分析工具，未詳讀） | 792 | 推測 numpy + psycopg2 | 時間窗 | audit 報告 | 推測：分析出場決策反事實 | 推測；未讀檔內；792 行接近硬上限 |  | 未讀檔內 |

---

#### 尾注

- **總計行數**（本次盤點 Python 模組）：
  - `app/`：126 檔 ≈ **60,840 LOC**
  - `ml_training/`：25 檔 ≈ **10,180 LOC**
  - `local_model_tools/`：27 檔（含 indicators/strategies） ≈ **3,090 LOC**（其中 14 檔 stub ≈ 1,520 LOC；真實計算 3 檔 ≈ 920 LOC）
  - `helper_scripts/`（本次 17 檔非一次性）≈ **7,980 LOC**
  - `audit/` / `observer_pipeline/` / `io_and_persistence/` 合計 ≈ **2,530 LOC**
  - **合計：~84,600 LOC Python（產品向）**，其中 stub ≈ 1,520 LOC
- **STUB 占比**：local_model_tools 27 檔中 14 檔為純 stub（Rust 真值源）；`strategy_read_routes.py`、`strategy_ai_routes.py`、`scanner_rate_limiter.py` 等多處 call-site 仍 import stub 作為 fallback 或 wiring 骨架
- **§九 檔案大小違反**（本次確認超 1200 硬上限）：
  - `app/live_session_routes.py` 1449
  - `app/ai_service.py` 1258
  - `app/multi_agent_framework.py` 1137（接近）
  - `app/strategist_agent.py` 1170
  - `helper_scripts/db/passive_wait_healthcheck.py` **1822**
  - `helper_scripts/db/counterfactual_exit_replay.py` 1216
  - 其他接近上限：`app/governance_hub.py` 1014 / `app/governance_routes.py` 1172 / `app/paper_trading_routes.py` 1088 / `app/layer2_tools.py` 906 / `app/optuna_optimizer.py` 946 / `app/experiment_ledger.py` 974 / `app/h0_gate.py` 971 / `app/trade_attribution.py` 958 / `app/reconciliation_engine.py` 948
- **FastAPI route 總數**（`@\w+_router.(get|post|put|delete|patch)` grep）：**234 decorators**（部分重複 import，非唯一 endpoint）。5 個 legacy sibling 聚合 55 routes（auth 3 + gui 5 + system 13 + learning 19 + control 15），其餘分散在 route-per-domain 檔案（paper 30 / governance 14 / live_session 14 / risk 12 / strategy_read 16 / strategy_ai 14 / phase4 9 / layer2 11 / scout 5 / ml 5 / governance_ext 12）。
- **Monkey-patch 擴展**：18 檔 `from . import main_legacy as base`，呼 `base.settings` / `base.STORE` / `base.app` / `base.envelope_response()`（原則 §九 登記的 4 singleton 入口；main.py 另外 monkey-patch `_patched_read` / `stable_compile_state` 覆蓋 state_store.JsonStateStore.read + state_compiler.compile_state）。


---

## Part 2 — 端到端資料流地圖（Session 3/5）

> 來源：[.claude_reports/inventory_2_data_flows.md](.claude_reports/inventory_2_data_flows.md)
> 涵蓋：8 必含資料流 + 2 額外（scanner cycle + news pipeline），均到「步驟編號 + file:line + 持久化點 + 斷鏈點」級別。

### 盤點交付物 #2 — 端到端資料流地圖（Session 3/5）

本文件是 Session 3/5 產出，依 [inventory_1a_rust_modules.md](inventory_1a_rust_modules.md) + [inventory_1b_python_modules.md](inventory_1b_python_modules.md) 為骨架，追 8 條核心資料流 + 2 條「非必含但值得列」。

**閱讀指南**：每條流以「業務意義 / 觸發源 / 終點 / 完整路徑（編號步驟）/ 資料結構演變 / 持久化點 / 可能斷鏈點 / §三 對應」八節組織。Rust↔Python 邊界以「↕ IPC edge」標記。

**校對狀態**：Step file:line 採 6 個並行 Explore sub-agent + 主會話直查 Grep 交叉驗證。標「⚠️ 未驗」= 該行只讀檔頂或子代理推斷未復查；標「❌ 未找到」= grep 失敗。

---

#### 資料流 1：市場 tick → 訂單提交到 Bybit

**業務意義**：Bybit 公開 WS 推送 K 線 / trade tick，引擎在 <2ms 內判斷 5 策略是否要下單，最終透過 REST 呼 Bybit V5 `/v5/order/create`。Live/Paper/LiveDemo 三引擎共享同一 tick pipeline。

**觸發源**：Bybit V5 Public WS 推送 `kline.{interval}.{symbol}` 或 `publicTrade.{symbol}` 事件。

**終點**：Bybit REST `POST /v5/order/create` 回傳 `result.orderId`，存入 Rust `event_consumer/loop_handlers.rs:41` 的 `order_id_to_link` HashMap，以及 PG `trading.orders` / `trading.intents` / `trading.signals`（透過 `trading_writer.rs`）。

**完整路徑**：

1. **WS 接收與解析**
   - 位置：[srv/rust/openclaw_engine/src/ws_client.rs:74-100](srv/rust/openclaw_engine/src/ws_client.rs:74)
   - 輸入：Bybit V5 WS JSON
   - 輸出：`PriceEvent`（`openclaw_types::price::PriceEvent`）via `mpsc::Sender<PriceEvent>`
   - 通道：`(price_tx, price_rx)` 在 main_pipelines.rs 構造
   - 備註：27 unwrap! 於 parse path（`ws_client.rs` 整體）；指數退避 `BACKOFF_POLICY` 重連
   - 持久化：無

2. **event_consumer 6-arm select! 接收 tick**
   - 位置：[srv/rust/openclaw_engine/src/event_consumer/mod.rs:93-156](srv/rust/openclaw_engine/src/event_consumer/mod.rs:93)
   - 輸入：`PriceEvent`
   - 輸出：dispatch 到 `loop_handlers::handle_tick_event`
   - 通道：6 arm（cancel / cross_engine / kline_seed / exchange / pending_reg / paper_cmd / tick）

3. **loop_handlers 推進 pipeline**
   - 位置：[srv/rust/openclaw_engine/src/event_consumer/loop_handlers.rs:724-754](srv/rust/openclaw_engine/src/event_consumer/loop_handlers.rs:724)
   - 輸入：`PriceEvent` + `&mut TickPipeline`
   - 輸出：`pipeline.on_tick(event)` 回傳 `Option<CanaryRecord>`

4. **TickPipeline 7 step 編排**
   - 位置：[srv/rust/openclaw_engine/src/tick_pipeline/on_tick/mod.rs:1-160](srv/rust/openclaw_engine/src/tick_pipeline/on_tick/mod.rs:1)
   - 編排：每 step 回 `ControlFlow::{Break,Continue}`，跨 step 以 owned return 避借用衝突
   - 子步驟：
     - **Step 0**：[step_0_fast_track.rs:1-516](srv/rust/openclaw_engine/src/tick_pipeline/on_tick/step_0_fast_track.rs) 閃崩/保證金 fast path
     - **Step 0.5**：[step_0_5_h0_gate.rs:1-93](srv/rust/openclaw_engine/src/tick_pipeline/on_tick/step_0_5_h0_gate.rs) H0 確定性硬阻斷（<1ms SLA，呼 `openclaw_core::h0_gate`）
     - **Step 1+2**：[step_1_2_klines_indicators.rs:1-111](srv/rust/openclaw_engine/src/tick_pipeline/on_tick/step_1_2_klines_indicators.rs) K 線聚合 + 16 指標 + emit `FeatureSnapshot`（→ `feature_collector.rs` 34 維 f32 → `feature_writer.rs` 寫 `features.online_latest`）
     - **Step 3**：[step_3_signals.rs:1-192](srv/rust/openclaw_engine/src/tick_pipeline/on_tick/step_3_signals.rs) `SignalEngine` 8 規則計算 → `Vec<Signal>`，含 `paper_paused` 短路 + N ms boot cooldown
     - **Step 4+5**：[step_4_5_dispatch.rs:1-935](srv/rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs)（**935 行不可再拆**）每策略 `Strategy::on_tick()` → `StrategyAction` enum → 構造 `OrderIntent` → 呼 `IntentProcessor::process_with_features()` → 收集 `Vec<OrderIntent>`（已風控通過）
     - **Step 6**：[step_6_risk_checks.rs:1-554](srv/rust/openclaw_engine/src/tick_pipeline/on_tick/step_6_risk_checks.rs) 9 持倉風控 → 呼 `position_risk_evaluator::evaluate_position()` → `RiskAction` enum → 派發
   - 輸入/輸出：見資料結構演變段
   - 持久化：FeatureSnapshot via mpsc → `feature_writer` → `features.online_latest`（UPSERT 34 維 REAL[]）

5. **Intent processor pipeline（H0→Guardian→CostGate→Kelly→OMS）**
   - 位置：[srv/rust/openclaw_engine/src/intent_processor/router.rs:27](srv/rust/openclaw_engine/src/intent_processor/router.rs:27) `process_with_features()`
   - 輸入：`OrderIntent` + `Option<FeatureVectorV1>` + `context_id`
   - 輸出：`IntentResult::{Approved | Rejected(reason_code) | Modified(...)}`
   - Gate 順序（見 [intent_processor/mod.rs:1100](srv/rust/openclaw_engine/src/intent_processor/mod.rs)）：
     - Gate 1（auth）→ 1.6（負餘額 / Paper-disable）
     - Gate 2 Guardian 4 vetos（見 Flow 4）
     - Gate 3 CostGate（[gates.rs:1-205](srv/rust/openclaw_engine/src/intent_processor/gates.rs) — 見 Flow 5）
     - Gate 4 Kelly Sizing（[ml/kelly_sizer.rs:1-281](srv/rust/openclaw_engine/src/ml/kelly_sizer.rs)，<50 trades 1/8 Kelly）
     - Gate 5 ε-greedy paper 探索（PAPER ONLY，預設 OFF）
     - Gate 6 OMS register（向 `OmsState` 登記訂單）
   - 通道：透過 `OrderDispatchRequest` mpsc 投到 dispatch task
   - 持久化：`trading.intents`（via `TradingMsg::Intent`）+ rejected → `intent_processor/rejection_coding.rs:561` 統一原因碼

6. **訂單派發（shadow vs primary）**
   - 位置：[srv/rust/openclaw_engine/src/event_consumer/dispatch.rs:1-1124](srv/rust/openclaw_engine/src/event_consumer/dispatch.rs)
   - 輸入：`OrderDispatchRequest`
   - 輸出：spawn tokio task → 呼 `OrderManager::create_order()` 或寫 `paper_state` shadow fill
   - 重試：DISPATCH-RETRY-1 OPEN intents 3 重試（200/800/3200 ms 指數）；CLOSE 2 重試（100/400 ms）
   - Result：`DispatchRetryResult<T>`

7. **OrderManager 驗證 + REST 提交**
   - 位置：[srv/rust/openclaw_engine/src/order_manager.rs:1-1554](srv/rust/openclaw_engine/src/order_manager.rs)（**遠超 §九 1200 硬上限**）
   - 輸入：`OrderReq`（symbol/side/qty/price/order_type/...）
   - 輸出：`OrderManager::create_order()` 回 `Result<OrderResp, BybitError>`
   - 驗證：[`InstrumentInfoCache`](srv/rust/openclaw_engine/src/instrument_info.rs)（1975 行）— qty step / tick size / min notional 圓整
   - REST：呼 [bybit_rest_client.rs](srv/rust/openclaw_engine/src/bybit_rest_client.rs)（1725 行）`post_with_signing()` HMAC-SHA256 簽名 → `POST /v5/order/create`
   - Fail-closed：retCode != 0 → 不重試，直接 Err

**資料結構演變**（典型 Demo bb_breakout BTCUSDT 路徑）：

```
Bybit WS frame
  → PriceEvent { kind: KlineUpdate, symbol: "BTCUSDT", price: 67234.5, ts_ms: ... }
    ↘ (mpsc price_rx)
  → TickPipeline.on_tick(event)
    ↘ Step 1+2
  → IndicatorSnapshot { sma_20, ema_50, atr_14, bb_*, rsi_14, ... }  (16 指標)
    ↘ feature_collector
  → FeatureSnapshot { 34 f32 標量 + 2 regime enum + 1 price }  → DB features.online_latest
    ↘ Step 3
  → Vec<Signal> { kind: BbSqueezeBreakoutLong, confidence: 0.74, ... }
    ↘ Step 4+5 per-strategy dispatch
  → StrategyAction::Open { side: Long, qty: ..., reason: "squeeze→expansion" }
    ↘ build_intent
  → OrderIntent { symbol, is_long, qty, confidence, strategy: "bb_breakout", ... }
    ↘ IntentProcessor.process_with_features
  → IntentResult::Approved(OrderIntent { qty: kelly_sized })
    ↘ dispatch.rs spawn
  → Bybit REST /v5/order/create
  → OrderResp { orderId: "abc...", orderLinkId: "..." }
```

**持久化點總覽**：

| 路徑 | 持久化目標 | Writer |
|---|---|---|
| Step 1+2 | `features.online_latest`（PG）+ ringbuf cap 3000 | `feature_writer.rs` |
| Step 3 | `trading.signals`（PG）via `TradingMsg::Signal` | `trading_writer.rs` |
| Step 4+5 | `trading.intents`（PG）+ rejection codes | `trading_writer.rs` |
| Step 5 (gate 6) | OMS state in-memory + `trading.orders` | `trading_writer.rs` |
| Step 7 | Bybit REST log + `trading.order_state_changes` | `trading_writer.rs` |

**可能的斷鏈點**：

1. **`step_4_5_dispatch.rs` 實際呼 IntentProcessor 的位置未直接 grep 驗證**（agent 1 報告）。如果這裡 NLL borrow checker 失敗，會看到 strategy → intent 的 plumbing 緊張，編譯期錯誤而非 runtime。
2. **dispatch.rs 1124 行接近硬上限**，DISPATCH-RETRY-1 的指數退避如果 budget 配置錯，會看到「OPEN intents 卡 retry 3 次後超時被丟」— 症狀：Bybit 端收到請求但內部 idempotency key 重複。
3. **OrderManager 驗證失敗**（qty 不整 / min notional 不足）→ `IntentResult::Rejected("InstrumentValidation")`，但不寫 `trading.intents`（拒絕在 OMS 之前）→ 症狀：策略發信號但 PG `trading.intents` 為空。

**CLAUDE.md §三 相關**：

- **ORDER-SUBMIT-GAP-1**：未在當前 §三 列出，意味 flow 1 從 WS 到 REST 是**接通的**。
- **EDGE-DIAG-1 Phase 3**：Step 5 Gate 3 cost_gate 受 Flow 5 影響；如 edge_estimates 過期 → CostGate fallback ATR×conf×0.2。
- **Python ExecutorAgent**：`_shadow_mode=True` hardcoded（[executor_agent.py:482](srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/executor_agent.py:482)）→ Python 不能透過 IPC `submit_order` 觸發真實下單；此流純 Rust 路徑為唯一活躍下單路徑（G3-02 Wave 2 重構目標）。

---

#### 資料流 2：Bybit fill → DB 持久化

**業務意義**：當下單成交（execution event）後，Rust 必須在 <100ms 更新內存 `paper_state`、寫 `trading.fills`、廣播給對賬 / Grafana。

**觸發源**：Bybit Private WS topic `execution`（Mainnet 走 `execution.fast` ~50ms）。

**終點**：PG `trading.fills`（含 `engine_mode` + `exit_source`），同時更新內存 `PaperPosition`，並 5s 寫一次 `bybit_private_ws_listener_status_latest.json`。

**完整路徑**：

1. **Bybit Private WS 認證 + 訂閱**
   - 位置：[srv/rust/openclaw_engine/src/bybit_private_ws.rs:1-1013](srv/rust/openclaw_engine/src/bybit_private_ws.rs)
   - 訂閱：`execution`（Demo/LiveDemo）/ `execution.fast`（Mainnet，~50ms 延遲）
   - HMAC：`common::bybit_signer.rs:1-162`

2. **Private WS 解析**
   - 位置：[bybit_private_ws.rs:585-623](srv/rust/openclaw_engine/src/bybit_private_ws.rs:585) `parse_private_message()`
   - 輸入：原始 WS JSON
   - 輸出：`PrivateWsEvent::Execution(ExecutionUpdate)`
     - `ExecutionUpdate { exec_id, order_id, symbol, side, exec_price, exec_qty, exec_fee, exec_type, exec_time }` (lines 135-167)
   - 通道：`mpsc::Sender<PrivateWsEvent>` line 247；`event_tx.send(event)` line 408

3. **ExecutionListener 派發 + 計數**
   - 位置：[srv/rust/openclaw_engine/src/execution_listener.rs:193-282](srv/rust/openclaw_engine/src/execution_listener.rs:193) `run()`
   - 輸入：`PrivateWsEvent`
   - Action：呼 callback `on_fill(exec)`（lines 210-212）+ 增 `total_fills` 計數（line 201）
   - Stats：`Arc<AtomicStats>` 暴露給 status_writer（line 184 `stats_arc()`）

4. **Fill callback → TickPipeline.apply_fill()** ⚠️ **未直接驗證 callback 註冊位置**
   - 位置：sub-agent 推測在 `tick_pipeline` 初始化或 `event_consumer/bootstrap.rs` 27 binding 中
   - 應該透過 `PipelineCommand::ApplyFill` 進入 [tick_pipeline/commands.rs:1-1039](srv/rust/openclaw_engine/src/tick_pipeline/commands.rs)
   - 然後呼 `paper_state::fill_engine::apply_fill()`

5. **PaperState fill_engine 變動熱路徑**
   - 位置：[srv/rust/openclaw_engine/src/paper_state/fill_engine.rs:1-505](srv/rust/openclaw_engine/src/paper_state/fill_engine.rs)
   - 操作：`apply_fill / close / reduce / restore`
   - 輸入：`Fill { exec_qty, exec_price, fee, ... }` + tick price
   - 輸出：更新 `PaperPosition { qty, entry_price, best_price, entry_notional, entry_fee, ... }`（[containers.rs:1-273](srv/rust/openclaw_engine/src/paper_state/containers.rs)）
   - 約束：bit-exact 重構（MICRO-PROFIT-FIX-1 entry_notional 累加不減 / FIX-03 fast_track ReduceToHalf / B-1 Phase 2 反轉 best_price reset）

6. **TradingMsg::Fill emit**
   - 位置：[tick_pipeline/pipeline_helpers.rs:190](srv/rust/openclaw_engine/src/tick_pipeline/pipeline_helpers.rs:190) — `engine_mode: em.to_string()` 注入
   - 通道：`trading_msg_tx` mpsc → `trading_writer.rs`
   - 結構：`TradingMsg::Fill { ts, fill_id, order_id, symbol, side, qty, price, fee, fee_rate, realized_pnl, is_paper, strategy_name, context_id, entry_context_id, engine_mode: String, exit_source: Option<String> }`
   - **engine_mode source**：per-pipeline `EngineMode`（paper / demo / live_demo / live）— **memory 已驗 2026-04-16 升級為 `live_demo` 區分 LiveDemo vs Mainnet**

7. **trading_writer.flush_fills() INSERT**
   - 位置：[srv/rust/openclaw_engine/src/database/trading_writer.rs:259-338](srv/rust/openclaw_engine/src/database/trading_writer.rs:259) `flush_fills()`
   - SQL（line 275）：
     ```sql
     INSERT INTO trading.fills (ts, fill_id, order_id, symbol, side, qty, price, fee,
       fee_rate, realized_pnl, is_paper, strategy_name, context_id, entry_context_id,
       engine_mode, exit_source) VALUES (...)
     ```
   - `engine_mode` bind：line 323 `b.push_bind(engine_mode.as_str())`
   - `exit_source` bind：line 329 `b.push_bind(exit_source.as_deref())`（V021 migration 新增）
   - PG 65535 param guard：`batch_insert.rs:1-355` chunk = min(65535/columns, 10000)
   - 失敗：3 連續 PG 失敗 → JSONL fallback（[fallback.rs:1-197](srv/rust/openclaw_engine/src/database/fallback.rs)）

8. **decision_features 鏈接（**獨立路徑**）**
   - 位置：[srv/rust/openclaw_engine/src/database/decision_feature_writer.rs:116-134](srv/rust/openclaw_engine/src/database/decision_feature_writer.rs:116)
   - 不在 fill 流程觸發；在 Step 4+5 派發時 emit `DecisionFeatureMsg`（PK=context_id），由獨立 task 寫 `learning.decision_features`
   - INSERT line 116 `INSERT INTO learning.decision_features ... ON CONFLICT DO NOTHING`
   - **與 fill 的關聯**：`trading.fills.context_id` = `learning.decision_features.context_id`（join 鍵）

9. **WS status writer 5s 心跳 ↕ IPC edge（檔案）**
   - 位置：[srv/rust/openclaw_engine/src/bybit_private_ws_status_writer.rs:1-604](srv/rust/openclaw_engine/src/bybit_private_ws_status_writer.rs)
   - 來源：clone Arc<AtomicStats>（line 184 ExecutionListener）
   - 輸出：tmp-then-rename 寫 `$OPENCLAW_DATA_DIR/bybit_private_ws_listener_status_latest.json`
   - 含 `listener_version: "rust-v1"` / `engine_mode` / `auth_ok_count` / 4 topics live
   - 取代原 Python listener（WS-RETIRE-1，2026-04-23 完成）

**資料結構演變**：

```
Bybit WS execution frame
  → PrivateWsEvent::Execution(ExecutionUpdate { exec_id, order_id, symbol, side, exec_price, exec_qty, exec_fee, exec_type, exec_time })
    ↘ (mpsc event_rx)
  → ExecutionListener::run() match arm + callback
    ↘ on_fill(exec)
  → PipelineCommand::ApplyFill (推測)
    ↘ commands.rs match
  → fill_engine.apply_fill(symbol, qty, price, fee)
  → PaperPosition mut { qty +=, entry_notional +=, fee +=, best_price = max(best_price, price), ... }
    ↘ helpers.emit_close_fill or emit_open_fill
  → TradingMsg::Fill { engine_mode: "demo"|"live_demo"|"live"|"paper", exit_source: Option<String>, ... }
    ↘ (mpsc trading_msg_tx)
  → trading_writer.flush_fills() batch
  → INSERT INTO trading.fills (...) VALUES (...)
```

**持久化點總覽**：

| 寫入點 | 目標 | Writer | 失敗處理 |
|---|---|---|---|
| 4 | in-memory `PaperState.positions` | `fill_engine.rs` | bit-exact 重構約束 |
| 5 | `trading.fills`（PG hypertable）| `trading_writer.rs:259` | 3× 失敗 → JSONL |
| 5 | `trading.position_snapshots` | `trading_writer.rs` | 同上 |
| 5 | `trading.orders` (state changes) | `trading_writer.rs` | 同上 |
| 8 | `learning.decision_features`（PK=context_id）| `decision_feature_writer.rs:116` | ON CONFLICT DO NOTHING |
| 9 | `bybit_private_ws_listener_status_latest.json`（檔）| status_writer.rs | tmp-then-rename atomic |

**可能的斷鏈點**：

1. **ExecutionListener callback 註冊位置未直接驗證**（sub-agent 2 報告）。如果某次重構漏掉 `set_on_fill()`，會看到 Bybit 端有 fill 但 Rust 內存未更新 → 後續 reconciler 30s 輪詢揭發 drift → SM-04 escalate。
2. **engine_mode 來源不在 `trading_writer.rs` 內驗證**（值由 caller 注入）。如某 `TradingMsg::Fill` 構造點漏注入正確 mode，會回退到 schema DEFAULT 'paper' — 這是 2026-04-21 commit `5e2981d` 之前的歷史 bug 重現風險。
3. **WS-RETIRE-1 後 Python observer 假設 Rust writer 永遠寫**：若 `status_writer` task panic，`bybit_build_ws_runtime_facts.py` 讀到 stale 檔卻無告警 → 症狀：observer 通過但實際 4 topics 已下線。

**CLAUDE.md §三 相關**：

- **outcome_backfiller fix `5e2981d`**：[srv/rust/openclaw_engine/src/database/outcome_backfiller.rs:37-113](srv/rust/openclaw_engine/src/database/outcome_backfiller.rs) timeframe `'1' → '1m'` + `engine_mode` INSERT 漏接補回，歷史回填 ~267k rows。
- **engine_mode 標籤 live_demo 升級（2026-04-16）**：見 memory `project_engine_mode_tag_live_demo.md`，Live+LiveDemo 寫 "live_demo" 非 "live"。
- **INFRA-PREBUILD-1 Part A（dormant）**：`fills.exit_source` 在 V021 migration 加入，Phase 1a `shadow_enabled=false` → 除 PHYS-LOCK 外全 NULL。

---

#### 資料流 3：AI 推理完整路徑

**業務意義**：tick 路徑判斷需要深度推理時，Rust 不直接呼 LLM；它呼 Python AIService（Unix socket），由 Python 走 H1（thought_gate）→ H3（model_router）→ LLM（Ollama / LM Studio / Anthropic）→ H4（validator）→ 回 Rust。Rust 端先 / 後雙重檢查預算。

**觸發源**：兩條獨立觸發：
- (A) **Strategist scheduler 5min 週期**（[strategist_scheduler/mod.rs:341](srv/rust/openclaw_engine/src/strategist_scheduler/mod.rs:341)）：呼 `ai_client.request("strategist_evaluate", params).await` — **這是目前唯一活躍的 Rust 觸發點**。
- (B) **Layer 2 手動觸發**：Python `app/layer2_routes.py` POST `/api/v1/ai/layer2/trigger` → `Layer2Engine` 自主深度推理（不經 Rust）。

**終點**：PG `learning.ai_usage_log` （Rust 寫，via IPC `record_ai_usage`） + 檔案 `cost_state.json`（Layer 2 only）+ Python AIService 回應（含 edge / params 建議）。

**完整路徑**：

1. **Rust → Python IPC client**
   - 位置：[srv/rust/openclaw_engine/src/ai_service_client.rs:1-364](srv/rust/openclaw_engine/src/ai_service_client.rs)
   - Method TTL：line 31 `strategist_evaluate => 15s`
   - Connect timeout：100ms
   - 通道：Unix socket `/tmp/openclaw/ai_service.sock`
   - Fail-closed：100ms connect 失敗 → 回 None，引擎不阻塞

2. **↕ IPC edge：長度前綴 JSON-RPC**
   - 4-byte big-endian u32 header + UTF-8 JSON payload
   - newline-delimited（與 Python ipc_server 不同協議）
   - multi-worker safe（僅 1 uvicorn worker 綁定，其他 passive）

3. **Python AIService 派發**
   - 位置：[srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/ai_service.py:131-152](srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/ai_service.py:131) ctor
   - Dispatch：line 206
   - Handler registry：lines 196-202 method name → async handler
   - 5 handler（line 269 strategist / 470 analyst / 535 conductor / 567 scout / 665 guardian）

4. **H1 thought gate（在 StrategistAgent 上游，非 _handle_strategist 內）**
   - 位置：[srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/h1_thought_gate.py:35-99](srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/h1_thought_gate.py:35) `H1ThoughtGate.check()`
   - 邏輯：
     - `_check_budget()` (line 102) → 呼 `cost_tracker.check_daily_budget()`，fail-open if None
     - `complexity_score()` (line 122) = relevance + multi-symbol bonus + urgency bonus；< 0.3 → skip AI
     - `_check_cooldown()` (line 139) → 30s 同幣種去重
   - 呼叫者：[strategist_agent.py:350](srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/strategist_agent.py:350)
   - **⚠️ 關鍵**：H1 在 `_handle_strategist` 之**前**（StrategistAgent.evaluate() 內），不在 ai_service handler 內

5. **預算檢查（3 層獨立追蹤！）**
   - **Path A（Python 月度 $50）**：[api_budget_manager.py:41-100](srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/api_budget_manager.py:41) `can_call(tier)` → 月度 cap + 1800s/3600s 冷卻；state file `api_budget_state.json`
   - **Path B（Layer 2 日 $2）**：[layer2_cost_tracker.py:75-726](srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/layer2_cost_tracker.py) `check_budget_for_session()`；DOC-08 §4 absolute hard cap；state file `layer2_cost_state.json`；7d ROI 自適應 multiplier
   - **Path C（Rust 月度 $80/$95/$100 三段降級）**：[ai_budget/tracker.rs:1-897](srv/rust/openclaw_engine/src/ai_budget/tracker.rs) **Rust 側為 SSOT 強制執行**；其他兩層 = audit log
   - **⚠️ 雙計風險**：Layer 2 呼叫被 Python `layer2_cost_tracker` + Rust `tracker` 雙寫；但 enforcement 只看 Rust。

6. **H3 model router**
   - 位置：[model_router.py:36-292](srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/model_router.py:36) `ModelRouter.route()`
   - 規則：complexity < 0.5 → `l1_9b`；0.5–0.8 → `l1_27b`；≥0.8 → `l2`
   - L2 cache：1h TTL，cap 200 entries

7. **LLM 呼叫（兩條 route）**
   - **Route A（local LLM，免費）**：[local_llm_factory.py:1-417](srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/local_llm_factory.py) lazy singleton；env `LOCAL_LLM_PROVIDER=ollama|lm_studio`；OllamaClient HTTP `/api/generate` `/api/chat`，max_retries=0（CLAUDE.md §四 hardline）
   - **Route B（Anthropic API）**：[layer2_engine.py:1-730](srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/layer2_engine.py) Anthropic SDK；session budget dual limit；當日 hard cap $2

8. **H4 validator**
   - 位置：[h4_validator.py:38-103](srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/h4_validator.py:38) `validate_ai_output()`
   - 檢查：confidence ∈ [0,1] / has_edge bool / reason non-empty / action ∈ {BUY,SELL,HOLD,SKIP}
   - Fail-closed：任一失敗 → heuristic fallback

9. **成本記錄 → IPC `record_ai_usage` ↕ IPC edge**
   - Python 觸發：[layer2_cost_tracker.record_session_end()](srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/layer2_cost_tracker.py)
   - IPC method：`record_ai_usage`（[ipc_client.py:281](srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/ipc_client.py:281) `record_ai_usage()`）
   - Rust handler：[ipc_server/handlers/budget.rs:140-200](srv/rust/openclaw_engine/src/ipc_server/handlers/budget.rs)
   - 寫 fail-closed -32603（不可 silent-drop）

10. **PG 寫入 `learning.ai_usage_log`**
    - 位置：[ai_budget/usage_io.rs:1-118](srv/rust/openclaw_engine/src/ai_budget/usage_io.rs)
    - SQL：`ON CONFLICT (time, scope, request_id) DO NOTHING` idempotent
    - 月界自動 reset

**資料結構演變**：

```
Rust strategist_scheduler tick (5min interval)
  → params { intel, model_tier, current_params, param_ranges }
    ↘ ai_service_client.request("strategist_evaluate", params)
    ↕ IPC edge (Unix socket /tmp/openclaw/ai_service.sock, 4-byte length-prefix)
  → JSON-RPC { method: "strategist_evaluate", params: {...} }
    ↘ Python AIService.dispatch (ai_service.py:206)
  → _handle_strategist
    ↘ delegate to StrategistAgent.evaluate()
    ↘ H1 check (skip if cooldown / complexity<0.3 / budget exhausted)
    ↘ ModelRouter.route() → tier
    ↘ LLM call (Ollama / LM Studio / Anthropic)
  → LlmResponse { text, tokens_in, tokens_out }
    ↘ H4 validate
  → EdgeEvaluation { confidence, has_edge, reason, suggested_params }
    ↕ IPC edge (return path)
  → Rust receives JSON
    ↘ if Anthropic, layer2_cost_tracker.record_session_end → IPC record_ai_usage
    ↕ IPC edge (Python → Rust budget IPC)
  → Rust ai_budget/tracker.rs:record_usage
  → INSERT INTO learning.ai_usage_log (time, scope, model, tokens_in, tokens_out, cost_usd, request_id, ...)
```

**持久化點總覽**：

| 寫入點 | 目標 | Writer | 備註 |
|---|---|---|---|
| 5 (Path A) | `api_budget_state.json` | api_budget_manager.py | 月度 $50 |
| 5 (Path B) | `layer2_cost_state.json` | layer2_cost_tracker.py | 日 $2 |
| 5 (Path C) | `learning.ai_budget_config` | ai_budget/config_io.rs | hot-reload |
| 10 | `learning.ai_usage_log`（hypertable）| usage_io.rs | SSOT 用量帳 |

**可能的斷鏈點**：

1. **`claude_teacher/client.rs` ≠ `ai_service_client.rs`**：兩條獨立路徑。Teacher 是另一個 Rust→Anthropic 路徑（[claude_teacher/client.rs:1-284](srv/rust/openclaw_engine/src/claude_teacher/client.rs)），用於 directive 生成；如果 operator 把兩者搞混，會誤以為 Layer 2 在 Rust 裡。
2. **三層預算雙計**：如果 Rust tracker 和 Python tracker 對「同一筆 Layer 2 呼叫」配對失敗，會看到「Rust 帳本顯示 $X，Python 帳本 $Y」不一致 — 但 enforcement 只看 Rust（其他為 audit）。
3. **strategist_scheduler 5min 週期**：[mod.rs:1166](srv/rust/openclaw_engine/src/strategist_scheduler/mod.rs) 是**單例**（R3-1 fix，取代 Python 4-worker race），如果 spawn 失敗，會看到 5min 內無 strategist evaluate 觸發但無告警。

**CLAUDE.md §三 相關**：

- **LLM-ABC-MIGRATION-1（2026-04-20 ✅）**：5 call-site 切 `local_llm_factory.get_local_llm_client()`，Ollama / LM Studio 可切換；Mac operator 設 `LOCAL_LLM_PROVIDER=lm_studio` 即可不裝 Ollama。
- **Layer 2 daily cap $2**：absolute hard，DOC-08 §4。
- **strategist_scheduler 接管 Python**：取代 Python FastAPI 4-worker race；指數 backoff 5m→30m→60m→4h。

---

#### 資料流 4：Guardian 風控審批

**業務意義**：每張 `OrderIntent` 進來時，Guardian（4 vetos）+ position-level 9 checks 審批；通過則 `RiskVerdict::Pass` 寫 PG，否則 `RiskVerdict::Reject` + reason；audit log 對 Operator 操作獨立寫。

**觸發源**：tick pipeline Step 4+5 派發每張 intent → `IntentProcessor::process_with_features()` 進入 Gate 2。

**終點**：PG `trading.risk_verdicts`（Rust 寫）+ Python `change_audit_log`（Operator manual changes audit）。

**完整路徑**：

1. **IntentProcessor entry**
   - 位置：[srv/rust/openclaw_engine/src/intent_processor/router.rs:27](srv/rust/openclaw_engine/src/intent_processor/router.rs:27) `process_with_features()`
   - 輸入：`OrderIntent` + `Option<FeatureVectorV1>` + `context_id`
   - Gate 順序：Gate 1（auth）→ 1.6（負餘額 / Paper-disable）→ Gate 2 Guardian → Gate 3 CostGate → ...

2. **RiskConfig 快照（ArcSwap ~5ns 讀）**
   - 位置：[srv/rust/openclaw_engine/src/config/risk_config.rs:1-908](srv/rust/openclaw_engine/src/config/risk_config.rs)
   - 模式：`tick_pipeline.apply_risk_snapshot()` 在 tick 開始時 swap
   - **Guardian = RiskConfig 派生視圖**（ARCH-RC1 1C-4 E-Merge-4，無 RMW 完整覆蓋）

3. **Guardian 4 deterministic vetos**
   - 位置：[srv/rust/openclaw_core/src/guardian.rs:14-49](srv/rust/openclaw_core/src/guardian.rs:14)
   - 輸入：`GuardianConfig` + `TradeIntent` + position state
   - 4 vetos：
     - direction conflict（max_same_direction_positions）
     - leverage cap（max_leverage）
     - drawdown limit（max_drawdown_pct）
     - position count anti-cluster（modification_size_factor / modification_leverage_cap）
   - 呼叫：`router.rs:95-120` `Guardian::review() → Verdict { passed, rejections }`

4. **tick-level position checks（9 項，**非 15+**）**
   - 位置：[srv/rust/openclaw_engine/src/risk_checks.rs:144](srv/rust/openclaw_engine/src/risk_checks.rs:144) `check_position_on_tick()`
   - 9 項（sub-agent 4 列出）：
     1. Hard stop（pnl ≤ -stop_loss_max_pct）
     2. Dynamic stop（ATR multiplier）
     3. Take profit（if enforced）
     4. Trailing stop（peak drawdown guard）
     5. Time stop（holding_hours limit）
     6. PHYS-LOCK（physical_micro_profit_lock_v2，DUAL-TRACK-EXIT-1 Track P v2）
     7. Session drawdown halt
     8. Consecutive loss cooldown
     9. Daily loss limit
   - 輸出：`RiskAction` enum: `Hold | ClosePosition | HaltSession | SetCooldown`
   - 備註：原盤點任務描述「15+ 項」應為 9 項（policy 與 mechanism 加總計算 → 9 項決策 + 多項配套輔助常數）

5. **Position risk evaluator（純函式）**
   - 位置：[srv/rust/openclaw_engine/src/position_risk_evaluator.rs:103](srv/rust/openclaw_engine/src/position_risk_evaluator.rs:103) `evaluate_position()`
   - Pure fn 抽出於 Step 6 後（P2 refactor）
   - 輸入：`PositionRow` + `RiskConfig`
   - 輸出：`PositionDecision { action, symbol, is_long }`

6. **RiskVerdict emit**
   - 通道：`TradingMsg::RiskVerdict` mpsc → trading_writer
   - 位置：[srv/rust/openclaw_engine/src/database/trading_writer.rs](srv/rust/openclaw_engine/src/database/trading_writer.rs) `flush_risk_verdicts()`（推測，未直接驗 line）
   - SQL：INSERT INTO trading.risk_verdicts (verdict, intent_id, reasons, ts, engine_mode)

7. **Change audit log（Python 側 — Operator 手動操作）**
   - 位置：[change_audit_log.py:160-246](srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/change_audit_log.py:160) `record_change()`
   - 寫 in-memory `_changes` list（line 234）
   - 7 變更型態 + 5 批准狀態
   - **⚠️ DB 表名未在檔內找到**（sub-agent 5 報告）— 推測 `governance.change_audit` 或類似
   - 並列：[audit_persistence.py:1-549](srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/audit_persistence.py) JSONL append-only 磁碟備份

8. **Rust 側 governance audit（V014 schema）**
   - 位置：[srv/rust/openclaw_engine/src/event_consumer/handlers/risk.rs:1-563](srv/rust/openclaw_engine/src/event_consumer/handlers/risk.rs) + [handlers/governance.rs:1-293](srv/rust/openclaw_engine/src/event_consumer/handlers/governance.rs)
   - 觸發：每次 IPC `update_risk_config` / `force_governor_looser` / `set_system_mode` → 寫 V014 audit row
   - **被拒絕路徑也寫 audit**（原則 #8 可解釋可審計）

**資料結構演變**：

```
OrderIntent { symbol, qty, is_long, strategy, confidence, ... }
  ↘ process_with_features
  → Gate 1 (auth check) → Gate 1.6 (balance/paper-disable)
  → Gate 2 Guardian
    ↘ TradeIntentCheck { intent, config, positions }
  → Verdict { passed: bool, rejections: Vec<RejectReason> }
    ↘ if passed, continue Gate 3+
  → Gate 3-7 (CostGate / Kelly / ε-greedy / OMS / Profile)
  → IntentResult::Approved(OrderIntent { qty: kelly_sized })
                  | Rejected { reason_code, intent_id }
                  | Modified { qty, reason }
    ↘ TradingMsg::RiskVerdict
  → INSERT INTO trading.risk_verdicts (verdict, intent_id, reasons, ts, engine_mode)
```

```
Operator API call (e.g., POST /api/v1/risk/config)
  ↘ FastAPI risk_routes
  → IPC update_risk_config(patch)
    ↕ IPC edge (Unix socket /tmp/openclaw/engine.sock)
  → Rust handlers/risk.rs::handle_update_risk_config
  → V014 audit row INSERT (含被拒絕路徑)
  → ConfigStore.patch() → ArcSwap.swap()
```

**持久化點總覽**：

| 寫入點 | 目標 | Writer | 備註 |
|---|---|---|---|
| 6 | `trading.risk_verdicts` | trading_writer.rs | 含 reasons JSON |
| 7 | Python in-memory + JSONL audit_persistence | change_audit_log.py | 表名未驗 |
| 8 | V014 governance audit table | handlers/risk.rs + governance.rs | 含被拒絕路徑 |

**可能的斷鏈點**：

1. **`trading.risk_verdicts` flush 失敗（PG 不可用）**：3× 失敗 → JSONL fallback；但 fallback 後 V014 audit 是否同樣 fallback 未驗 → 症狀：Rust 重啟後 risk_verdict 缺幾分鐘。
2. **Python `change_audit_log.py` DB 表名未驗**：[change_audit_log.py:160](srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/change_audit_log.py:160) `record_change()` 只寫 in-memory `_changes` list，無明顯 SQL — 可能依賴 `audit_persistence.py` 或從未真實 PG 寫 — 需驗。
3. **Guardian 與 Python Guardian agent 雙源風險**：Rust `core::guardian.rs` 是 RiskConfig 派生（純函數），但 Python `guardian_agent.py:587` 也存在；如果 Python guardian_agent 在某些路徑取代 Rust Guardian，會導致風控雙寫不一致。memory `feedback_rust_authoritative_config.md` 明定 Rust 為權威 — 需驗 Python guardian_agent 實際是否被 hot path 呼叫（推測：僅 `_handle_guardian` IPC handler 呼，非 hot path）。

**CLAUDE.md §三 相關**：

- **PostOnly 配置反向（2026-04-24 verified finding 2）**：`strategy_params_{demo,live}.toml` 中 demo=false / live=true → 違反原則 #6（失敗默認收縮），G1-05 立即修。
- **DEAD-PY-2 完成**：Python RiskManager 已收編到 Rust ConfigStore + intent_processor + position_risk_evaluator；Python `risk_manager.py` 僅 52 行 shim。

---

#### 資料流 5：Learning 累積 → Edge estimation → cost_gate 門檻

**業務意義**：每筆 fill 完成後，PnL 被歸戶到 `(strategy, symbol)` cell，做 winsorize → James-Stein 收縮 → 寫 `settings/edge_estimates.json` → Rust 啟動時讀一次 → cost_gate 用此估計判斷是否值得下單。**這是 Phase 5 / EDGE-DIAG-1 的核心循環**。

**觸發源**：每小時 cron — Python `edge_estimator_scheduler.py` daemon（fcntl leader lock）。

**終點**：`settings/edge_estimates.json` 檔（Rust 讀）+ DB `learning.james_stein_estimates`、`learning.realized_edge_stats`、`learning.labels`。

**完整路徑**：

1. **Decision feature 寫入（Rust 即時）**
   - 位置：[srv/rust/openclaw_engine/src/database/decision_feature_writer.rs:1-231](srv/rust/openclaw_engine/src/database/decision_feature_writer.rs)
   - 觸發：Step 4+5 構造 `DecisionFeatureMsg` → mpsc → writer
   - SQL（line 116）：`INSERT INTO learning.decision_features ... ON CONFLICT (context_id) DO NOTHING`
   - 17 維 FeatureVectorV1：見 [edge_predictor/features.rs:1-485](srv/rust/openclaw_engine/src/edge_predictor/features.rs)

2. **Outcome backfill（Rust 5min 輪詢）**
   - 位置：[srv/rust/openclaw_engine/src/database/outcome_backfiller.rs:1-276](srv/rust/openclaw_engine/src/database/outcome_backfiller.rs)
   - 操作：掃描 `decision_context_snapshots` 中 ts > 25h 未回填的 → 從 `market.klines` 取 1m/5m/1h/4h/24h return → INSERT `decision_outcomes`
   - **`5e2981d` fix**：timeframe `'1' → '1m'` + engine_mode INSERT 漏接（lines 37-113 + 234-260 regression test）

3. **Label backfill（Python，每小時）**
   - 位置：[srv/program_code/ml_training/edge_label_backfill.py:1-456](srv/program_code/ml_training/edge_label_backfill.py)
   - 操作：join entry `decision_features` + `trading.fills` (close) → 計算 `label_net_edge_bps`
   - 處理：`split qty-weighted`（multi-fill close）/ `grid VWAP` / 排除 orphan / shadow_fill / epsilon_greedy
   - 輸出：UPDATE `learning.decision_features` SET `label_net_edge_bps`

4. **Realized edge stats（Python，每小時）**
   - 位置：[srv/program_code/ml_training/realized_edge_stats.py:1-526](srv/program_code/ml_training/realized_edge_stats.py)
   - 操作：per (strategy, symbol) 聚合 round-trip PnL → winsorize **±5000 bps**（P1-17 修正）→ 計算 mean/std
   - 輸出：DB `learning.realized_edge_stats`

5. **James-Stein 收縮（Python，每小時）**
   - 位置：[srv/program_code/ml_training/james_stein_estimator.py:1-555](srv/program_code/ml_training/james_stein_estimator.py)
   - 公式：`B_j = min(1, (p-2)/n × σ²_j / ‖raw - grand_mean‖²)`（partial pooling）
   - 輸出：
     - DB `learning.james_stein_estimates`
     - 檔 `settings/edge_estimates.json` — top-level keys 格式 `"strategy::symbol"` + `grand_mean_bps`
   - 備註：含 `_inject_sync_label_proxy_cells`（P0-14 B 92 proxy cells from 4 sync-label strategies × 23 symbols）

6. **Edge estimator scheduler（Python daemon）**
   - 位置：[srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/edge_estimator_scheduler.py:1-716](srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/edge_estimator_scheduler.py)
   - 啟動：隨 uvicorn `start_scheduler()`；fcntl leader lock 防 4-worker race
   - 週期：每 1 小時觸發 step 3-5
   - 暴露：`/api/v1/learning/edge-estimator/trigger` POST 手動觸發（[edge_estimator_routes.py:1-134](srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/edge_estimator_routes.py)）
   - **歷史 outage（2026-04-24 G1-01 verified finding 1）**：daemon 4 天停滯 → mtime 2026-04-20 → 1 cell only（grid_trading::ORDIUSDT, n=3, grand_mean=-45.73）

7. **Rust 啟動時讀（一次性，**無 hot reload**）↕ IPC edge（檔）**
   - 位置：[srv/rust/openclaw_engine/src/edge_estimates.rs:1-387](srv/rust/openclaw_engine/src/edge_estimates.rs)
   - `set_edge_estimates()` 從 `settings/edge_estimates.json` 讀 → `HashMap<"strategy::symbol", CellEstimate>`
   - **⚠️ 關鍵限制**：JSON 檔修改後**不會 hot reload**；engine restart 才生效（即使 IPC `reload_config` 也不重讀此檔）
   - Fallback：檔不存在 → 空 HashMap → cost_gate 用 ATR×conf×0.2

8. **CostGate 門檻計算（每 intent）**
   - 位置：[srv/rust/openclaw_engine/src/intent_processor/gates.rs:1-205](srv/rust/openclaw_engine/src/intent_processor/gates.rs)
   - 邏輯（PH5-WIRE-1）：
     - 正 JS 估計（shrunk_bps > 0）：threshold = fee_bps / max(0.3, win_rate) × 1.3 → reject if shrunk_bps < threshold
     - 負 JS 估計：探索模式（allow，log）
     - 缺估計（cold-start）：fallback ATR × confidence × 0.2
   - 輸出：`IntentResult::rejected(CostGateJsPaper {...})` 或繼續

9. **Phase 5 / EDGE-DIAG-1 cost_gate 綁定**
   - 條件：grand_mean > -50 bps 且 ≥2 策略 shrunk_bps > 0 → bind hard threshold
   - 現狀（2026-04-25）：未滿足（受 P1-10 結構性 fee-drag / R:R 不對稱壓制）

**資料結構演變**：

```
TickPipeline Step 4+5 emit
  → DecisionFeatureMsg { context_id, 17-dim FeatureVectorV1, ... }
    ↘ (mpsc decision_feature_tx)
  → INSERT INTO learning.decision_features (PK=context_id)
  
[5min 輪詢]
  → outcome_backfiller scans rows with ts>25h, no outcome
  → INSERT INTO learning.decision_outcomes (1m/5m/1h/4h/24h returns)
  
[每小時 Python]
  → edge_label_backfill.py: join decision_features+trading.fills → label_net_edge_bps
  → realized_edge_stats.py: winsorize ±5000bps → mean/std per (strategy, symbol)
  → james_stein_estimator.py: shrunk_bps = (1-B) * raw + B * grand_mean
  → settings/edge_estimates.json (file write atomic rename)
    ↕ IPC edge (file, no IPC reload)
  → [Engine restart] edge_estimates.set_edge_estimates() reads JSON → HashMap

[每 intent tick]
  → CostGate reads cached HashMap[strategy::symbol] → CellEstimate { shrunk_bps, win_rate, n }
  → if shrunk_bps>0 and shrunk_bps<threshold → reject
```

**持久化點總覽**：

| 寫入點 | 目標 | Writer | 備註 |
|---|---|---|---|
| 1 | `learning.decision_features`（PK=context_id）| decision_feature_writer.rs | ON CONFLICT DO NOTHING |
| 2 | `learning.decision_outcomes` | outcome_backfiller.rs | 1m/5m/1h/4h/24h |
| 3 | `learning.decision_features.label_net_edge_bps` UPDATE | edge_label_backfill.py | 7 段落 §8.2 |
| 4 | `learning.realized_edge_stats` | realized_edge_stats.py | winsorize ±5000bps |
| 5 | `learning.james_stein_estimates` + `settings/edge_estimates.json` | james_stein_estimator.py | top-level key 格式 |
| 7 | Rust in-memory `EdgeEstimates`（HashMap）| edge_estimates.rs | startup-only |

**可能的斷鏈點**：

1. **scheduler 停滯（已發生）**：fcntl leader lock 在 uvicorn worker 異常死 (SIGKILL) 後不釋放 → 後續 worker 無法接管 → 週期不執行；2026-04-24 復現了 4d 停滯。**症狀**：`settings/edge_estimates.json` mtime 不前進 + cells 不增加。**healthcheck [13]** 已加入 `cells=62 mtime fresh` 驗證。
2. **Engine restart 才能熱重載 edge_estimates.json**：scheduler 寫了新檔，但 engine 持續用舊 HashMap → 直到 `restart_all.sh --rebuild` 為止。**潛在症狀**：scheduler 顯示 162 cells，cost_gate 仍在用 1 cell 行為。
3. **P0-14 A Gate 1 fallback `missing_edge_fallback_bps = -10.0`**：缺 cell 時的 fallback；**EDGE-DIAG-1-FUP-IPC commit** 加 7 個 `exit.*` IPC 熱重載路徑（不含 edge_estimates 本身）→ rollback ETT <60s。
4. **Phase 5 cost_gate 綁定條件不達**：grand_mean > -50bps 且 ≥2 策略 shrunk_bps>0 — 從未達成（CLAUDE.md §三）。

**CLAUDE.md §三 相關**：

- **LEARNING-PIPELINE-DORMANT-1**（P1）：semi-resolved 2026-04-19，剩餘 gap = 21 schema 表無 consumer + cost_gate 綁定條件未達。
- **EDGE-DIAG-1**：Phase 1+2+4+FUP-IPC 完成（commits `5b0908b` + `1a53400`）；Phase 3 strategy-scoped Gate 1 fallback auto-gated by healthcheck [11]。
- **G1-01（2026-04-24 verified finding 1）**：edge_estimator_scheduler 4d 停滯 → operator 同日 commits `f32629c`/`abc85c0` + 02:06 --rebuild 復活；現 187 cells / 59 updated/cycle / mtime <30min。

---

#### 資料流 6：Operator 授權 → Live session spawn（LIVE-GATE-BINDING-1）

**業務意義**：Live 模式需要 5 重門控，其中 #5（HMAC `authorization.json`）由 Python 簽 / Rust 驗。Python `live_trust_routes` POST `/auth/renew` 寫檔，Rust `live_auth_watcher` 每 5 秒輪詢驗證；任一檢查失敗 → `pipeline_slot::teardown()` 拆 Live 但保 Demo/Paper。

**觸發源**：(A) Operator 主動 POST `/api/v1/live/auth/renew`；(B) 定時 EarnedTrust 自動續期；(C) drawdown event 觸發 G1-06 revoke。

**終點**：`$OPENCLAW_SECRETS_DIR/live/authorization.json`（HMAC 簽名檔）+ Rust live pipeline 啟動或拆除（slot lifecycle）。

**完整路徑**：

1. **Python `/auth/renew` endpoint**
   - 位置：[srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/live_trust_routes.py:641-757](srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/live_trust_routes.py:641)
   - 流程：check T3 mandatory review → evaluate 推薦 tier → revoke existing auths → 建立新 SM-01 auth → write signed authorization → trigger watcher recheck
   - Authentication：line 657 `_require_operator(actor)` → `governance_routes._require_operator_role()`

2. **EarnedTrust engine evaluate_renewal**
   - 位置：[earned_trust_engine.py:621-710](srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/earned_trust_engine.py:621) `evaluate_renewal()`
   - TTL 階梯：T0–T3（lines 50–54, 57）
   - 晉升要求：lines 137–170
   - mid-session 降級檢查：lines 522–599
   - T3 auto-renewal cap：line 72 `T3_MAX_AUTO_RENEWALS=1`

3. **HMAC-SHA256 簽署 authorization.json**
   - 位置：[live_trust_routes.py:160-219](srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/live_trust_routes.py:160) `_write_signed_live_authorization()`
   - HMAC：line 123 `_sign_authorization_payload()` → `hmac.new(ipc_secret, payload, hashlib.sha256).hexdigest()`
   - Canonical payload（line 107-120）：`version|tier|issued_at_ms|expires_at_ms|operator_id|env_allowed_sorted_csv`
   - Atomic write：line 129 `_atomic_write_json()` (tmp-then-rename)

4. **檔案路徑**
   - 位置：[live_trust_routes.py:77-87](srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/live_trust_routes.py:77) `_live_secret_slot_dir()`
   - 路徑：`$OPENCLAW_SECRETS_DIR/live/authorization.json`
   - Fallback：`$HOME/BybitOpenClaw/secrets/secret_files/bybit/live/`
   - Rust 端常量：[live_authorization.rs:27-47](srv/rust/openclaw_engine/src/live_authorization.rs:27)

5. **Rust load + verify ↕ IPC edge（檔）**
   - 位置：[srv/rust/openclaw_engine/src/live_authorization.rs:329-380](srv/rust/openclaw_engine/src/live_authorization.rs:329) `load_and_verify(env: BybitEnvironment)`
   - 驗證：
     - HMAC 簽名 via `compute_signature()` (line 256-270)
     - Expiry：`now_ms < record.expires_at_ms`
     - `env_allowed` 包含當前 endpoint label（[line 316-319](srv/rust/openclaw_engine/src/live_authorization.rs:316) → `AuthError::EnvNotAllowed`）
     - Schema version：line 39 `SCHEMA_VERSION = 1`（line 289 拒絕 mismatch）

6. **5 秒輪詢 watcher**
   - 位置：[srv/rust/openclaw_engine/src/live_auth_watcher.rs:1-957](srv/rust/openclaw_engine/src/live_auth_watcher.rs)
   - 輪詢：line 99 `DEFAULT_POLL_INTERVAL = Duration::from_secs(5)`（**5 秒，非 5 分鐘** — sub-agent 5 修正用戶原本的「每 5min re-verify」描述）
   - 實際 5min re-verify 為 SM-01 lease 層級邏輯，不是 file poll
   - State machine：respawn live pipeline when auth becomes valid + slot=Empty；teardown when auth becomes invalid + slot=Spawned
   - IPC wake-up：`trigger_live_auth_recheck`（line 24，TTR ≤5s）

7. **Pipeline slot teardown**
   - 位置：[srv/rust/openclaw_engine/src/pipeline_slot.rs:1-896](srv/rust/openclaw_engine/src/pipeline_slot.rs)
   - Token 階層：`engine_shutdown_token` (parent) → `live_slot.cancel_token` (child)
   - Revoke Live 不 cancel Demo/Paper（lines 14-24 文檔化）
   - `PipelineSlot::teardown()`：cancel slot-scoped child + await JoinHandles

8. **drawdown_revoke (G1-06)**
   - 位置：[srv/rust/openclaw_engine/src/drawdown_revoke.rs:1-442](srv/rust/openclaw_engine/src/drawdown_revoke.rs)
   - 觸發：HaltSession reason 含 DRAWDOWN_REASON_PREFIX
   - 動作：
     - `revoke_live_authorization()` 刪除 `authorization.json`（lines 95-100）
     - 5 秒內 watcher 偵測 `AuthError::FileMissing`
     - 呼 `PipelineSlot::teardown()` 拆 Live（保 Demo/Paper）

**5 重門控映射**：

| Gate | 位置 | 類型 | 實作 |
|---|---|---|---|
| 1. Python `live_reserved` global mode | live_trust_routes.py / earned_trust_engine.py | Restart-lost session flag | Python only |
| 2. Python Operator role auth | [live_trust_routes.py:657](srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/live_trust_routes.py:657) | HTTP auth | delegates to governance_routes._require_operator_role |
| 3. `OPENCLAW_ALLOW_MAINNET=1` env | [live_authorization.rs:?](srv/rust/openclaw_engine/src/live_authorization.rs) | Process env | Rust check during load_and_verify |
| 4. Secret slot 有 api_key + api_secret | [bybit_rest_client.rs:386-497](srv/rust/openclaw_engine/src/bybit_rest_client.rs) | File presence | ⚠️ 確切 line 未直接驗 |
| 5. authorization.json HMAC + 未過期 + env_allowed match | [live_authorization.rs:329](srv/rust/openclaw_engine/src/live_authorization.rs:329) | Crypto | HMAC-SHA256 |

**資料結構演變**：

```
Operator HTTP POST /api/v1/live/auth/renew
  ↘ live_trust_routes.py:641
  → check T3 mandatory + evaluate tier + revoke existing
    ↘ _write_signed_live_authorization()
  → payload = "1|t3|1714050000000|1714053600000|op_alice|live_demo,mainnet"
    ↘ HMAC-SHA256(ipc_secret, payload)
  → record { version, tier, issued_at_ms, expires_at_ms, operator_id, env_allowed[], signature_hex }
    ↘ _atomic_write_json
  → $OPENCLAW_SECRETS_DIR/live/authorization.json (tmp-then-rename)
  
[5s 輪詢]
  → live_auth_watcher.rs poll
    ↘ load_and_verify(BybitEnvironment::LiveDemo)
  → LiveAuthorization { version, tier, ... } | AuthError::{FileMissing, SignatureInvalid, Expired, EnvNotAllowed, VersionMismatch}
    ↘ if Ok and slot=Empty → spawn live pipeline
    ↘ if Err and slot=Spawned → PipelineSlot::teardown()
```

**持久化點總覽**：

| 寫入點 | 目標 | Writer | 備註 |
|---|---|---|---|
| 3 | `$OPENCLAW_SECRETS_DIR/live/authorization.json` | live_trust_routes.py | atomic tmp-then-rename |
| 8 | DELETE `authorization.json` | drawdown_revoke.rs | drawdown event triggers |

**可能的斷鏈點**：

1. **HMAC key drift（環境變數 `OPENCLAW_IPC_SECRET`）**：Python 簽名與 Rust 驗證使用同一 env var；若 ops 改了 secret 但只 reset 一邊 → Rust 拒簽名 → engine graceful shutdown。
2. **5 秒輪詢延遲**：DELETE `authorization.json` 後最壞 5s + cancel time 才停 Live 下單 — 不是即時。drawdown 事件下 5s 內仍能下幾筆單（除非 G1-06 同時 broadcast HaltSession）。
3. **Env_allowed 不對稱**：Python 寫 `["live_demo", "mainnet"]`；Rust 嚴格比對當前 endpoint label。Mainnet/LiveDemo 切換時 env_allowed 必須包含 active label。

**CLAUDE.md §三 相關**：

- **LIVE-GATE-BINDING-1**（2026-04-18 ✅）：HMAC `authorization.json` 簽名 + 5min lease re-verify。
- **§四 硬邊界**：Live 5 重門控明確列出（line 102-113）。
- **execution_authority**：Rust 端只是 P0/P1 denylist 字串常量（[claude_teacher/applier.rs:226](srv/rust/openclaw_engine/src/claude_teacher/applier.rs:226)）— 非真實授權邏輯。

---

#### 資料流 7：Agent 事件 → change_audit_log

**業務意義**：5-Agent（Strategist/Guardian/Executor/Analyst/Scout）關鍵決策事件統一進審計鏈，但目前 ExecutorAgent shadow hardcoded 意味實際下單路徑不發 audit。

**觸發源**：5-Agent 任一在內部呼 `self._audit(event_type, data)`。

**終點**：Python in-memory `change_audit_log._changes` list + 磁碟 JSONL audit_persistence + （推測）DB `governance.change_audit` 表。

**完整路徑**：

1. **Agent 內 `_audit()` 呼叫**（5 個檔案）
   - [strategist_agent.py:1170](srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/strategist_agent.py)
   - [guardian_agent.py:587](srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/guardian_agent.py)
   - [executor_agent.py:482, 512](srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/executor_agent.py:482) `_shadow_mode: bool = True`（hardcoded）
   - [analyst_agent.py:834](srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/analyst_agent.py)
   - [scout_routes.py / ScoutAgent](srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/scout_routes.py)

2. **base_agent.py `_audit()` 抽取**
   - 位置：[base_agent.py:1-255](srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/base_agent.py)
   - 提供：所有子類繼承 `self._audit(event_type, data)`
   - 條件：`audit_callback` 不為 None（若 wiring 注入）

3. **agent_audit_bridge factory**
   - 位置：[agent_audit_bridge.py:237-403](srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/agent_audit_bridge.py:237) `make_agent_audit_callback(gov_hub, role_name)`
   - 回傳 `Callable[[str, Any], None]`
   - Fail-open：`gov_hub None` 或 `_change_audit_log None` → silent skip + DEBUG log（lines 334-347）
   - Exception swallow + 60s throttled WARNING（lines 373-401）

4. **Strategy_wiring 注入**
   - 位置：[strategy_wiring.py:467-468](srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/strategy_wiring.py:467) ExecutorAgent ctor with default ExecutorConfig (shadow=True)
   - 推測：所有 5 agent 在 strategy_wiring 內注入 `audit_callback=make_agent_audit_callback(GOV_HUB, role)` — **未直接驗 wiring 注入是否覆蓋全 5 agent**

5. **classify event_type → change_type**
   - 位置：[agent_audit_bridge.py:177-206](srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/agent_audit_bridge.py:177) `_classify_event()`
   - 分類為 7 變更型態之一（DECISION/STATE/RISK/...）

6. **GovernanceHub.change_audit_log forwarder**
   - 位置：[agent_audit_bridge.py:363-372](srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/agent_audit_bridge.py:363)
   - 呼 `change_audit_log.record_change(change_type, who=role_name, what=f"Agent event: {event_type}", auto_approve=True)`

7. **change_audit_log.record_change()**
   - 位置：[change_audit_log.py:160-246](srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/change_audit_log.py:160)
   - 構造 `ChangeRecord` 不可變 dataclass（lines 79-134）
   - Append to `self._changes` list (line 234)
   - **⚠️ DB 表名未在 source 找到**（sub-agent 5 報告）— 推測 `governance.change_audit` 但無 SQL 字串 grep 命中

8. **audit_persistence.py JSONL 磁碟備份**
   - 位置：[audit_persistence.py:1-549](srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/audit_persistence.py)
   - 機制：append-only JSONL；按日期 + size 輪轉
   - 立即 flush 不緩衝；損壞行 skip 不靜默 drop

**資料結構演變**：

```
Agent decision (e.g. StrategistAgent.evaluate emits TradeIntent)
  ↘ self._audit("trade_intent_emitted", {symbol, qty, confidence})
  → BaseAgent._audit invokes self.audit_callback (if wired)
  → make_agent_audit_callback closure
    ↘ _classify_event → ChangeType.DECISION
  → change_audit_log.record_change(change_type=DECISION, who="strategist", what="Agent event: trade_intent_emitted", details={...}, auto_approve=True)
  → ChangeRecord (immutable dataclass)
    ↘ self._changes.append(record)
    ↘ audit_persistence.write_jsonl(record)
  → file: change_audit.YYYY-MM-DD.jsonl
  → (推測) DB INSERT INTO governance.change_audit (...)
```

**持久化點總覽**：

| 寫入點 | 目標 | Writer | 備註 |
|---|---|---|---|
| 7 | Python in-memory `_changes` list | change_audit_log.py | 重啟丟失（除非有 reload from JSONL） |
| 8 | `change_audit.YYYY-MM-DD.jsonl` 檔 | audit_persistence.py | append-only, 每日輪轉 |
| - | （推測）`governance.change_audit` PG | ❌ 未找到 SQL 寫入點 | 需驗 |

**可能的斷鏈點**：

1. **ExecutorAgent shadow hardcoded（CLAUDE.md §三 verified finding 3）**：[executor_agent.py:482](srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/executor_agent.py:482) `_shadow_mode: bool = True` + [strategy_wiring.py:468](srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/strategy_wiring.py:468)。
   - 含義：Python ExecutorAgent **永遠**走 line 512 shadow path，寫 audit log（"shadow_intent_logged"），但**不**透過 IPC 發 `submit_order`。
   - 症狀：audit log 顯示 ExecutorAgent 在工作，但 `trading.intents` / `trading.fills` 中不出現由 ExecutorAgent 觸發的 row（只 Rust hot-path 觸發）。
2. **DB 表名 confirm 缺失**：[change_audit_log.py:160](srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/change_audit_log.py:160) `record_change()` 的實際 PG 寫入是否真存在 — 需驗（grep `INSERT INTO` 全 source 無命中）。可能審計只在 in-memory + JSONL，從未寫 PG。
3. **5-agent wiring 不對稱（E5-FN-3 部分接線 per memory）**：strategy_wiring 是否對所有 5 個 agent 都注入 audit_callback 未直接驗證；如果 ScoutAgent 漏接，他的 intel events 永遠不進審計。

**CLAUDE.md §三 相關**：

- **3 大 Verified 發現 (3) ExecutorAgent hardcoded shadow**：違反原則 #3（AI 輸出 ≠ 即時命令），G3-02 Wave 2 重構目標。
- **E5-FN Functional Defects Wave**（2026-04-19 完成）但具體修了哪 5 agent 的 wiring 未列。

---

#### 資料流 8：Crash → Watchdog → Maintenance flag → Restart

**業務意義**：engine panic 或 DNS 故障時，由 Python watchdog daemon（systemd / launchd）偵測 snapshot 過期 + 分類失敗類型 → DNS-only 不重啟、真 panic 觸發 restart_all.sh。

**觸發源**：watchdog 2s 週期輪詢 `pipeline_snapshot*.json` mtime。

**終點**：spawn `bash helper_scripts/restart_all.sh --engine-only` (timeout 120s) 或記錄 `network_outage`。

**完整路徑**：

1. **Watchdog daemon 主迴圈**
   - 位置：[srv/helper_scripts/canary/engine_watchdog.py:509](srv/helper_scripts/canary/engine_watchdog.py:509) `run_watchdog()`
   - 週期：2s
   - 常量：
     - `STALE_THRESHOLD=45s`（line 44）
     - `GRACE_PERIOD=120s`（line 48）
     - `STRIKE_WINDOW=3600s`（line 46）
     - `MAX_STRIKES=3`
     - `MAX_CONSECUTIVE_FAILURES=5`（line 60）
     - 指數 backoff `[60, 120, 300, 600, 3600]`（line 57）

2. **Snapshot freshness check**
   - 位置：line 126 `check_snapshot_freshness()`
   - 讀檔：`pipeline_snapshot*.json`（per-engine + 主相容檔）
   - 來源：[srv/rust/openclaw_engine/src/persistence.rs:14-90](srv/rust/openclaw_engine/src/persistence.rs:14) `StateWriter`（5s debounced，atomic rename）
   - 判定：`now - mtime > STALE_THRESHOLD` → 過期

3. **Classify engine failure**
   - 位置：[engine_watchdog.py:174-223](srv/helper_scripts/canary/engine_watchdog.py:174) `classify_engine_failure(log_path)`
   - 讀 engine.log 尾 20 行（≤256KB）
   - **Override 1**（line 205-207）：任一行匹配 `CRASH_INDICATOR_PATTERNS`（panic/assertion/stack）→ 強制 `"engine_crash"`
   - **Heuristic**（line 213-219）：≥5 連續行匹配 `NETWORK_OUTAGE_PATTERNS`（"temporary failure in name resolution" / "dns error" / "http transport error" / "connection refused"）→ `"network_outage"`
   - 分類結果：
     - `"network_outage"` → 不算 strike，不 auto-restart（line 423-441），但 `engine_alive=False`
     - `"engine_crash"` → 計算 strike，觸發 auto-restart（line 443-489）

4. **Maintenance flag 檢查**
   - 路徑：`$OPENCLAW_DATA_DIR/engine_maintenance.flag`
   - Watchdog check：[engine_watchdog.py:285-288](srv/helper_scripts/canary/engine_watchdog.py:285) `should_restart()` → `(False, "maintenance flag present")`
   - **⚠️ 未找到 flag CREATE 點**：應為 operator 手動 `touch` 或 (推測) `restart_all.sh` 開頭創建 — 需驗
   - Cleanup：[restart_all.sh:188](srv/helper_scripts/restart_all.sh:188) `rm -f` 在 restart 前

5. **Trigger restart**
   - 位置：line 305 `trigger_restart(data_dir)`
   - 前置：`should_restart()=True` + 不在 backoff window
   - 動作：spawn `bash helper_scripts/restart_all.sh --engine-only` (timeout 120s)
   - Circuit breaker：lines 291-295 `consecutive_failures >= 5` → circuit_broken，停重試

6. **restart_all.sh 主流程**
   - 位置：[srv/helper_scripts/restart_all.sh:1-285](srv/helper_scripts/restart_all.sh)
   - 順序：
     1. `rebuild_engine_binary()` (line 69-85) if `--rebuild`：`cargo build --release -p openclaw_engine`
     2. `graceful_stop_engine()` (line 145-180)：SIGTERM → 5s grace → SIGKILL
     3. Rotate log (line 185)：archive → `engine_logs/engine-${ts}.log`，keep 10
     4. `write_restart_sentinel()` (line 112-143)：寫 `last_shutdown_kind = "manual"` 到 `settings/runtime/`（PIPELINE-SLOT-1 Phase 1）
     5. Clear maintenance flag (line 188)：`rm -f`
     6. Start engine (line 189-214)：nohup → `rust/target/release/openclaw-engine`
     7. `restart_api()` (line 217-247)：lsof kill :8000 + uvicorn nohup
     8. `wait_and_verify()` (line 257-266)：sleep 10 → call `engine_watchdog.py --status`

7. **Engine startup reads sentinel**
   - 位置：[srv/rust/openclaw_engine/src/restart_kind.rs:1-178](srv/rust/openclaw_engine/src/restart_kind.rs)
   - 讀 `settings/runtime/last_shutdown_kind`
   - 僅 `"manual"` 精確文字生效；讀後刪
   - 影響：manual restart 清空 live auth state；非 manual 保留

8. **Engine panic 路徑**
   - 位置：[srv/rust/openclaw_engine/src/main.rs:122-164](srv/rust/openclaw_engine/src/main.rs:122)
   - Panic hook（line 133）：捕獲 unwind panic + backtrace → tracing sink
   - SIGTERM/SIGHUP：line 5-6 MODULE_NOTE
   - `run_pipeline_crash_only()` line 63 `catch_unwind()`
   - Result：broadcast `EngineEvent::Crashed`，set health=Down，cancel.cancel()（lines 91-97）
   - **OS SIGKILL → no panic hook → 靜默死亡 → watchdog 從 stale snapshot 偵測**

**WATCHDOG-DNS-CLASSIFY-1（P0-9 RCA 後加入）**：

CLAUDE.md §三 line 60 說 "WATCHDOG-DNS-CLASSIFY-1" — sub-agent 6 已找到 [engine_watchdog.py:174-223](srv/helper_scripts/canary/engine_watchdog.py:174) `classify_engine_failure()`。
- 2026-04-20 加入（per line 73 comment）。
- 解決 P0-9 STABILITY-1（2026-04-16 power outage RCA）發現的 30 ENGINE_CRASH 事件實為 DNS 失敗。

**資料結構演變**：

```
Engine writes pipeline_snapshot*.json every 5s (debounced via persistence.rs:14-90 StateWriter)
  ↘ atomic tmp-then-rename
[Watchdog 2s poll]
  → check_snapshot_freshness(file) → mtime, age
  → if age > 45s and uptime > 120s grace:
    ↘ classify_engine_failure(log_path)
    → tail engine.log 20 lines
    → grep CRASH_INDICATOR_PATTERNS (override 1)
    → grep NETWORK_OUTAGE_PATTERNS (≥5 consecutive)
  → classification: "engine_crash" | "network_outage"
  → if engine_crash AND should_restart() AND !in_backoff:
    ↘ trigger_restart()
    → subprocess: bash restart_all.sh --engine-only (timeout 120s)
  → restart_all.sh:
    ↘ rebuild (if flag) → graceful_stop → rotate_log → write_sentinel → start_engine → start_api → verify
```

**持久化點總覽**：

| 寫入點 | 目標 | Writer | 備註 |
|---|---|---|---|
| 7 | `settings/runtime/last_shutdown_kind` | restart_all.sh:112-143 | "manual" 精確文字 |
| - | `engine_logs/engine-${ts}.log` (rotated) | restart_all.sh:185 | keep 10 |
| - | `engine_maintenance.flag` | (未找到 CREATE) | 推測手動 / restart_all 起始 |

**可能的斷鏈點**：

1. **DNS classify 邏輯弱**：5 連續行 NETWORK_OUTAGE 才不算 strike；若 DNS 問題與 panic 混雜（DNS error → unwrap panic）→ 仍會 force "engine_crash"（override 1）→ 重啟可能無效。
2. **maintenance flag CREATE 未在代碼中找到**：可能依賴 operator 手動 `touch` — 如果 ops 流程錯，watchdog 會在 deploy 時誤認 crash。
3. **Mac dev 環境**：engine 不跑 Linux only；Mac 上 watchdog 永遠回 `engine_alive: false`（CLAUDE.md §六 line 214）— 需要 ssh trade-core 跑 Linux watchdog 才有真實狀態。
4. **systemd unit file 缺失**（sub-agent 6 報告）：「2026-04-15 engine_watchdog systemd unit ✅」但 repo 內未找到 `.service` 檔；只找到 `com.openclaw.engine-watchdog.plist`（macOS launchd）。Linux 端可能直接 nohup 跑無 supervision，crash → 靜默死。

**CLAUDE.md §三 相關**：

- **P0-9 STABILITY-1**（2026-04-16 ✅ closed）：停電基礎設施事件 RCA，非 code bug，不重置 21d 時鐘。
- **WATCHDOG-DNS-CLASSIFY-1**（2026-04-20 加入）：邏輯在 engine_watchdog.py:174-223。
- **engine_maintenance.flag**（CLAUDE.md §六 line 196）：「上次異常留下會阻塞 watchdog → 開工前先 `rm -f`」。

---

#### 資料流 9（額外，非必含）：Scanner 30min cycle → 動態 symbol universe

**業務意義**：每 30 分鐘 Rust scanner 掃 Bybit USDT-perp tickers，按 4 strategy fitness function 評分 → 更新 active symbol set → 對 Bybit Public WS 增刪 topic 訂閱。取代 Python market_scanner.py。

**觸發源**：Rust [scanner/runner.rs:1-315](srv/rust/openclaw_engine/src/scanner/runner.rs) tokio interval 30min。

**完整路徑**（簡述）：

1. Fetch tickers via `market_data_client::get_tickers()` ([market_data_client/mod.rs:1-532](srv/rust/openclaw_engine/src/market_data_client/mod.rs))
2. Filter by `ScannerConfig` ([scanner/config.rs:1-397](srv/rust/openclaw_engine/src/scanner/config.rs))
3. Score 4 fitness fns ([scanner/scorer.rs:1-901](srv/rust/openclaw_engine/src/scanner/scorer.rs)) — F_ma / F_grid / F_bbrv / F_bkout + edge bonus + correlation filter
4. Query positions（避免拆已持有倉位的 symbol）
5. Apply to `SymbolRegistry` ([scanner/registry.rs:1-486](srv/rust/openclaw_engine/src/scanner/registry.rs))（pinned BTC/ETH 不受 anti-churn）
6. WS sub/unsub topic changes ([multi_interval_topics.rs:1-315](srv/rust/openclaw_engine/src/multi_interval_topics.rs))
7. Kline bootstrap for newly added symbols

**為何值得列**：scanner cycle 是 tick 流的「上游選股」決策點，非 §三 P0/P1 但若 scorer 失靈 → 整個策略池會選錯 symbol → 持續低 edge。

---

#### 資料流 10（額外，非必含）：News pipeline → Guardian halt + Regime + Learning

**業務意義**：4 news provider（Mock / CryptoPanic / RSS CoinTelegraph / RSS Google News）每 28min+ 拉新聞 → dedup → severity 評分 → 3 consumer fan-out（Guardian halt / Regime buffer / Learning sink）。

**觸發源**：Rust [news/pipeline.rs:1-321](srv/rust/openclaw_engine/src/news/pipeline.rs) tokio interval。

**完整路徑**（簡述）：

1. **Provider 拉取**：[news/provider.rs:1-27](srv/rust/openclaw_engine/src/news/provider.rs) trait + 4 impl（mock / cryptopanic 28min / rss CoinTelegraph / rss Google News）
2. **Dedup**：[news/dedup.rs:1-162](srv/rust/openclaw_engine/src/news/dedup.rs) SHA1[:16] 標題 hash + 24h 滑動窗口
3. **Severity**：[news/severity.rs:1-207](srv/rust/openclaw_engine/src/news/severity.rs) keyword × source 加權
4. **Pipeline orchestrate**：news/pipeline.rs:1-321 → DB 寫入（推測 `news.events` 表）
5. **Router fan-out**：[news/router.rs:1-428](srv/rust/openclaw_engine/src/news/router.rs) 3 consumer
   - **Guardian halt**：[news/guardian_impl.rs:1-169](srv/rust/openclaw_engine/src/news/guardian_impl.rs) flip Arc<AtomicBool> session_halted（與 claude_teacher 共享同一 Arc）
   - **Regime buffer**：[news/learning_context_impl.rs:1-232](srv/rust/openclaw_engine/src/news/learning_context_impl.rs)（推測，next decision ctx）
   - **Learning sink**：context snapshot 給 next tick

**為何值得列**：Guardian 共享 Arc<AtomicBool> 與 claude_teacher（[claude_teacher/governance_impl.rs:1-206](srv/rust/openclaw_engine/src/claude_teacher/governance_impl.rs)）— 雙路徑可改變 halted flag → 任一斷線會導致 halt 不一致。

---

#### 尾注：與 Session 1 + 2 的交叉引用

- **每條流的 step file 引用**：對應 Session 1 / 2 表格中職責欄。可作為「給定問題從哪條流追入」的索引。
- **§三 P0/P1 對應總表**：

| 流 | §三 對應 |
|---|---|
| 1 (tick→order) | 通則正常；ExecutorAgent shadow hardcoded（G3-02 Wave 2） |
| 2 (fill→DB) | outcome_backfiller `5e2981d`；engine_mode `live_demo` 升級；INFRA-PREBUILD-1 Part A dormant |
| 3 (AI 推理) | LLM-ABC-MIGRATION-1 ✅；strategist_scheduler 5min |
| 4 (Guardian) | DEAD-PY-2 完成；PostOnly 配置反向（G1-05）|
| 5 (edge) | LEARNING-PIPELINE-DORMANT-1（P1）；EDGE-DIAG-1 Phase 3；G1-01 scheduler 復活 |
| 6 (live authz) | LIVE-GATE-BINDING-1 ✅；§四 5 重門控 |
| 7 (agent audit) | E5-FN Wave；ExecutorAgent hardcoded（G3-02）|
| 8 (watchdog) | P0-9 STABILITY-1 ✅；WATCHDOG-DNS-CLASSIFY-1 |

- **跨流共享 Arc<AtomicBool> session_halted**：news::guardian_impl + claude_teacher::governance_impl（Flow 10 + Teacher loop）。
- **跨流共享 ConfigStore<RiskConfig>**：Flow 1 + 4（cost_gate + Guardian + position_risk_evaluator 全讀同一 ArcSwap）。



---

## Part 3 — CLAUDE.md §二 16 條根原則治理對照（Session 4/5）

> 來源：[.claude_reports/inventory_3_governance_audit.md](.claude_reports/inventory_3_governance_audit.md)
> 涵蓋：DOC-01 §5.1–§5.16 逐條檢視代碼層的實作 + 運行時驗證，暴露「紙面治理」與「實際治理」的 gap。

### 盤點交付物 #3 — CLAUDE.md §二 16 條根原則治理對照（Session 4/5）

本文件對照 [srv/CLAUDE.md](srv/CLAUDE.md) §二（DOC-01 §5.1–§5.16）逐條檢視代碼層的實作 + 運行時驗證，暴露「紙面治理」與「實際治理」的 gap。引用 Session 1/2 模組（[1a Rust](inventory_1a_rust_modules.md) / [1b Python](inventory_1b_python_modules.md)）+ Session 3 資料流（[流 1–10](inventory_2_data_flows.md)）。

**校對狀態**：每條原則先查代碼路徑，必要時跑 grep 交叉驗證；標「⚠️ 推測」= 沒實際驗證；標「❌ 未找到」= grep 失敗。

---

#### 原則 #1：單一寫入口

**原文**：所有訂單/執行動作通過唯一受控入口。

**實作位置**：
- 主要負責的模組：
  - 唯一入口 = `IntentProcessor::process_with_features()` ([intent_processor/router.rs:27](srv/rust/openclaw_engine/src/intent_processor/router.rs:27)，Session 1 第 5 批)
  - 派發層 = `event_consumer/dispatch.rs` ([dispatch.rs:1-1124](srv/rust/openclaw_engine/src/event_consumer/dispatch.rs)，Session 1 第 4 批)
  - REST = `OrderManager::create_order()` ([order_manager.rs:1554](srv/rust/openclaw_engine/src/order_manager.rs)，Session 1 第 7 批)
- 相關資料流：[Flow 1（市場 tick → 訂單）](inventory_2_data_flows.md#資料流-1)
- 配置來源：`RiskConfig` ArcSwap（[config/risk_config.rs:908](srv/rust/openclaw_engine/src/config/risk_config.rs)）+ TickPipeline 持有快照

**測試覆蓋**：
- 單元測試：[intent_processor/tests.rs](srv/rust/openclaw_engine/src/intent_processor/tests.rs:1905)（1905 行，52 unwrap，涵蓋 H0/Guardian/CostGate/Kelly 各 gate）
- 整合測試：[handlers/tests.rs](srv/rust/openclaw_engine/src/event_consumer/handlers/tests.rs:695)（IPC dispatch handlers 整測）
- IPC 測試：`ipc_server/tests/strategy.rs`、`tests/dispatch.rs`

**運行時驗證**：
- ✅ Rust 端：唯一 hot path（5 策略 → Step 4+5 → IntentProcessor → dispatch.rs → OrderManager），編譯期由 `&mut self` 借用語意鎖定
- ❌ **Python `submit_order` IPC handler 是並列入口**：[ipc_server/handlers/strategy.rs:215](srv/rust/openclaw_engine/src/ipc_server/handlers/strategy.rs)（Session 1 第 4 批）+ Python `executor_agent.py:550/555` 也呼叫 `submit_order`（Session 2 IPC 表）。當前 `_shadow_mode=True hardcoded` 阻斷了實際發送，但**契約上**仍是兩個入口
- 無持續性 audit：trading.intents 只記成功 + 拒絕；無「對 IntentProcessor 的呼叫總數 vs 對 OrderManager 的呼叫總數」一致性 metric

**Gap 說明**：
- **代碼有並列入口風險**：Python ExecutorAgent 一旦解除 hardcoded shadow（G3-02 Wave 2），`submit_order` IPC handler 即同時被 Rust hot path（自動）+ Python ExecutorAgent（可能）兩方寫入
- **Rust 內部 fan-in 缺一致性 audit**：dispatch.rs 1124 行 + IntentProcessor 1100 行 + step_4_5_dispatch.rs 935 行均接近/超過 §九 1200 硬上限，後續拆分一旦漏接 callback，hot-path 沉默繞過 IntentProcessor 也無 metric 偵測
- §三 P0/P1 已知關聯：CLAUDE.md 3 大 Verified 發現 (3) ExecutorAgent shadow hardcoded — 直接觸碰本原則

**運行時證據**：
- ✅ `trading.intents`（PG）24h 應有 N 千筆條目（Session 3 Flow 1 步驟 5 持久化）
- ✅ `trading.risk_verdicts`（PG）有 [trading_writer.rs](srv/rust/openclaw_engine/src/database/trading_writer.rs:728) 寫入點（grep 命中唯一）
- ❌ 「總 intent 數 vs 總 fill 數」+「Rust hot-path 觸發 vs Python 觸發」對照儀表盤 — 不存在

**operator 信任度**：（由 operator 自填）

---

#### 原則 #2：讀寫分離

**原文**：研究/GUI/學習：只讀。寫入權限極度受限、可審計、可鎖定。

**實作位置**：
- 主要負責的模組：
  - Rust = 唯一寫權威：[config/store.rs:837](srv/rust/openclaw_engine/src/config/store.rs)（ConfigStore<T> ArcSwap+Mutex）+ 21+ IPC method（Session 2 IPC 表 `update_risk_config` / `set_system_mode` / `submit_order` 等）
  - Python `risk_manager.py` 52 行 shim（[risk_manager.py:52](srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/risk_manager.py)）— DEAD-PY-2 完成
  - GUI 讀路徑：`ipc_state_reader.py`（[ipc_state_reader.py:356](srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/ipc_state_reader.py)）TTL 2s + staleness 60s
  - Python 寫路徑全走 IPC：[risk_view_client.py:435](srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/risk_view_client.py)（GUI flat→Rust nested）
- 相關資料流：[Flow 4（Guardian 風控）](inventory_2_data_flows.md#資料流-4) + [Flow 5（cost_gate）](inventory_2_data_flows.md#資料流-5)
- 配置來源：3 ConfigStore（risk/budget/learning）+ env vars（OPENCLAW_*）+ secret 檔

**測試覆蓋**：
- 單元測試：[config/risk_config_tests.rs:423](srv/rust/openclaw_engine/src/config/risk_config_tests.rs)（patch 行為 + validator）
- 整合測試：[ipc_server/tests/risk.rs + risk_update.rs + config.rs](srv/rust/openclaw_engine/src/ipc_server/tests)（Session 1 第 4 批，1696 行合計）
- 契約測試：Python `test_stub_contracts.py` 59 tests（Session 1 footer，DEDUP-PY-RUST Tier A 收尾）

**運行時驗證**：
- ✅ ConfigStore.patch() 寫入 PatchSource enum（Operator/Agent/Migration/Startup）+ 版本號（Session 1 第 3 批）— V014 audit row（Session 1 governance handler）
- ✅ Python local_model_tools/ 14 stub（Session 2 第 10 批）— `compute()` 全回 None / 空 list；契約上不可寫
- ❌ **「讀路徑無 mutation」靜態保證缺失**：Python GUI route 雖 IPC-only，但 Python in-memory `STORE`（[main_legacy.py:468](srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/main_legacy.py)）+ `state_store.py:402` 仍可寫；非 Rust 權威配置之外的 GUI 狀態（settings/operator/display）走檔（Session 2 settings_routes.py 第 3 批）
- ❌ 學習平面寫權限的「鎖定」憑藉約定：`edge_estimator_scheduler` 寫 settings/edge_estimates.json（Session 3 Flow 5 步 5），無 RBAC

**Gap 說明**：
- **「可鎖定」靠 secret 路徑檢查**：API key + authorization.json + Operator role 都是「沒 token 就寫不了」，不是 OS-level 寫鎖定
- **Python in-memory STORE 可寫**：state_compiler/state_store 受 monkey-patch 約束（main.py snapshot identity 不變性，Session 2 第 2 批），但約束不是強制鎖定
- §三 已知 P0/P1：3 大 Verified 發現 (2) PostOnly 配置反向 — TOML 直接編輯，無 IPC audit

**運行時證據**：
- ✅ V014 governance audit row（[handlers/governance.rs:293](srv/rust/openclaw_engine/src/event_consumer/handlers/governance.rs) + [handlers/risk.rs:563](srv/rust/openclaw_engine/src/event_consumer/handlers/risk.rs)）含被拒絕路徑
- ✅ `learning.directive_executions`（Teacher applier 寫，每 directive outcome 一行）
- ❌ 「過去 24h Python 寫 IPC 次數 vs 真正配置改變的 ConfigStore.patch 次數」對照 — 不存在

**operator 信任度**：

---

#### 原則 #3：AI 輸出 ≠ 即時命令

**原文**：AI → Decision Lease（帶時效、可撤銷）→ 本地復核 → 執行。

**實作位置**：
- 主要負責的模組：
  - Rust SM-02 Lease 狀態機：[core/sm/lease.rs:747](srv/rust/openclaw_core/src/sm/lease.rs)（Session 1 第 2 批）— 9 態 20 遷移 12 禁 5 守衛
  - Python SM-02 鏡像：[decision_lease_state_machine.py:652](srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/decision_lease_state_machine.py)（Session 2 第 1 批）
  - Lease TTL SSOT：[lease_ttl_config.py:470](srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/lease_ttl_config.py)（§九 登記 singleton）
  - Lease enforce daemon：[ttl_enforcer.py:607](srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/ttl_enforcer.py) auto-REJECT/EXPIRE/ESCALATE
  - GovernanceHub.acquire_lease：[governance_hub.py:1014](srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/governance_hub.py)
  - Teacher directive applier（lease-like 行為）：[claude_teacher/applier.rs:1068](srv/rust/openclaw_engine/src/claude_teacher/applier.rs)
- 相關資料流：[Flow 3（AI 推理）](inventory_2_data_flows.md#資料流-3) + [Flow 7（agent 事件）](inventory_2_data_flows.md#資料流-7)
- 配置來源：lease_ttl_config + LearningConfig.teacher_loop_enabled + ExecutorConfig.shadow_enabled

**測試覆蓋**：
- 單元測試：Rust [sm/lease.rs:747](srv/rust/openclaw_core/src/sm/lease.rs) 內含 #[cfg(test)]
- Python：governance route handler tests（governance_routes 1172 行 lease/auth 共 14 endpoint）
- agent_audit_bridge：[test_strategist_audit_wiring.py](srv/program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_strategist_audit_wiring.py)（grep 命中 1 檔）

**運行時驗證**：
- ✅ TTL daemon sweep 週期（ttl_enforcer 自動清過期 lease）
- ⚠️ **半失效**：Python ExecutorAgent `_shadow_mode=True` hardcoded（[executor_agent.py:482](srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/executor_agent.py:482) + [strategy_wiring.py:467](srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/strategy_wiring.py:467)）— Session 3 Flow 7 步 4 直接驗
  - 含義：5-Agent 從 Strategist 出 intent → Guardian 通過 → ExecutorAgent **不 IPC**，只寫 shadow audit log
  - 真實下單路徑 = Rust hot path（tick → Step 4+5 → IntentProcessor → dispatch.rs，Session 3 Flow 1）
  - **真實 lease 行為缺**：Rust hot path 不經 SM-02 lease；lease 只用於 Python agent 的「審計記錄」
- ✅ Teacher loop（claude_teacher）有獨立 default-off 開關（[consumer_loop.rs:665](srv/rust/openclaw_engine/src/claude_teacher/consumer_loop.rs)）— 須 E3 R6 audit PASS 後手動 flip

**Gap 說明**：
- **Lease 概念在 Rust hot path 缺席**：實際下單路徑零 lease 存在；lease 只在 Python 5-Agent 框架（不發 SubmitOrder）+ Teacher directive（dormant）走
- §三 3 大 Verified 發現 (3) 直接觸碰：「真正 gap」= ExecutorAgent shadow→live + Rust IPC SubmitOrder 整合契約
- Python SM-02 與 Rust SM-02 雙源：手動同步，drift 風險

**運行時證據**：
- ✅ `governance.lease_transitions`（推測 V014 schema，未直接 grep 確認 SQL）— Python audit
- ❌ Rust hot path 「lease_id 對應 trading.intents.context_id」的關聯性查詢 — 不存在（hot path 不經 lease）
- ❌ 「過去 24h lease 數 vs intent 數」一致性 — 必為大幅不對等

**operator 信任度**：

---

#### 原則 #4：策略不能繞過風控

**原文**：所有交易意圖必須經 Guardian 審批。

**實作位置**：
- 主要負責的模組：
  - Rust Guardian：[core/guardian.rs:314](srv/rust/openclaw_core/src/guardian.rs)（Session 1 第 2 批）— 4 確定性 veto
  - Position-level 9 checks：[risk_checks.rs:874](srv/rust/openclaw_engine/src/risk_checks.rs) `check_position_on_tick()` line 144（Session 1 第 5 批）
  - Pure fn evaluator：[position_risk_evaluator.rs:352](srv/rust/openclaw_engine/src/position_risk_evaluator.rs)
  - Python `guardian_agent.py`：[guardian_agent.py:587](srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/guardian_agent.py)（Session 2 第 5 批）— 並列審計鏈，Rust 為熱路徑權威
- 相關資料流：[Flow 4（Guardian 審批）](inventory_2_data_flows.md#資料流-4)
- 配置來源：RiskConfig（Rust 為 SSOT，ARCH-RC1 1C-4 E-Merge-4）

**測試覆蓋**：
- 單元測試：[strategies/tests.rs:552](srv/rust/openclaw_engine/src/strategies/tests.rs) + [tick_pipeline/tests.rs:3524](srv/rust/openclaw_engine/src/tick_pipeline/tests.rs)（涵蓋 Step 4+5+6 整鏈）
- 整合測試：[risk_checks](srv/rust/openclaw_engine/src/risk_checks.rs) + [position_risk_evaluator](srv/rust/openclaw_engine/src/position_risk_evaluator.rs) 內含 #[cfg(test)]

**運行時驗證**：
- ✅ Step 4+5 dispatch 對每張 OrderIntent 強制呼 IntentProcessor（[on_tick/step_4_5_dispatch.rs:935](srv/rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs)，**935 行不可再拆**）— 編譯期 NLL 鎖定
- ✅ Step 6 持倉風控每 tick 呼（[step_6_risk_checks.rs:554](srv/rust/openclaw_engine/src/tick_pipeline/on_tick/step_6_risk_checks.rs)）— policy/mechanism 拆開
- ✅ ArcSwap RiskConfig tick 級熱重載 ~5ns（Session 1 第 3 批）
- ❌ **「策略繞過 Guardian」靜態保證缺失**：依賴所有 strategy 路徑都呼 IntentProcessor — 主路徑由 §九 NLL 鎖定，但任何新 fast_track / 旁路（fast_track.rs 407 行已存在！）都需手動審查
- ⚠️ fast_track 路徑：[fast_track.rs:407](srv/rust/openclaw_engine/src/fast_track.rs)（緊急閃崩/保證金）— **這是設計上的 Guardian 旁路**，CLAUDE.md §三 FA-PHANTOM-1 ROOT CAUSE 曾揭發 fast_track 誤用 notional/balance 當 margin_util 全平所有策略

**Gap 說明**：
- **fast_track 是設計性旁路**：閃崩/保證金緊急時不經 Guardian veto，直接全平。memory `project_fa_phantom_bug.md` 記錄此處「90% 閾值＜設計上限 100%」歷史 bug — 旁路本身的 trigger 條件即「風控規則」，bug 直接違反原則 #4
- **Python guardian_agent 雙源**：Session 1 footer + Session 3 Flow 4 斷鏈點 3 — Python guardian_agent 在 hot path 不被呼叫（推測），但 IPC `_handle_guardian` handler（Session 2 IPC 表）可能在 Strategist 觸發時被間接呼到 — 兩源語意 drift 為靜默風險

**運行時證據**：
- ✅ `trading.risk_verdicts` 24h 應有 N 千筆（Session 3 Flow 4 步 6 持久化）
- ✅ rejection_coding.rs 561 行統一原因碼（Session 1 第 5 批）+ V014 governance audit
- ❌ 「fast_track 觸發次數」獨立 metric — 推測在 healthcheck 但未直接確認

**operator 信任度**：

---

#### 原則 #5：生存 > 利潤

**原文**：先判斷「不會螺旋崩潰」，再判斷「能否盈利」。

**實作位置**：
- 主要負責的模組：
  - SM-04 RiskGovernor 6 級：[core/sm/risk_gov.rs:933](srv/rust/openclaw_core/src/sm/risk_gov.rs)（Session 1 第 2 批）— Normal→CB→MR
  - Black swan detector：[database/black_swan_detector.rs:536](srv/rust/openclaw_engine/src/database/black_swan_detector.rs)（4 signal 投票）
  - Drawdown revoke：[drawdown_revoke.rs:442](srv/rust/openclaw_engine/src/drawdown_revoke.rs)（Session 1 第 7 批）— G1-06 觸發 HaltSession + 刪 authorization.json
  - Position reconciler 5 tier drift：[position_reconciler/mod.rs:809](srv/rust/openclaw_engine/src/position_reconciler/mod.rs)
  - Python SM-04 鏡像：[risk_governor_state_machine.py:844](srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/risk_governor_state_machine.py)
- 相關資料流：[Flow 6（Operator 授權）](inventory_2_data_flows.md#資料流-6)（含 G1-06 drawdown revoke）+ [Flow 8（crash watchdog）](inventory_2_data_flows.md#資料流-8)
- 配置來源：RiskConfig.risk_governor + cost_gate + drawdown thresholds

**測試覆蓋**：
- 單元測試：sm/risk_gov.rs 內含 #[cfg(test)]
- 整合測試：position_reconciler/tests.rs 684 行；black_swan_detector 內測
- E2E：watchdog 3 strike rollback 流程（[engine_watchdog.py:699](srv/helper_scripts/canary/engine_watchdog.py)）

**運行時驗證**：
- ✅ Reconciler 30s 輪詢（CLAUDE.md §三 / Session 1 第 5 批）— Phase 6 auto-contraction（drift→governor escalate→recover）
- ✅ Watchdog 2s 週期 snapshot freshness（Session 3 Flow 8 步 1）— STALE=45s + grace=120s + 3 strike + 指數 backoff
- ✅ Drawdown revoke 5s 內 watcher 偵測（Session 3 Flow 6 步 8）
- ✅ Black swan detector 4 signal 投票 2/4→Observe 3/4→Upgrade 4/4→Defensive
- ❌ **fast_track 旁路歷史 bug**：FA-PHANTOM-1（memory `project_fa_phantom_bug.md`）— fast_track 90% 閾值＜設計上限 100% 全平所有策略；root cause 是把 notional/balance 當 margin_util，違反「不會螺旋崩潰」假設

**Gap 說明**：
- **2 個 SM-04 雙源**：Rust + Python；手動同步，6 級轉換語意必須 byte-identical
- **fast_track bug 已修但 design 風險仍在**：依賴 trigger 條件正確；未來新增閃崩規則仍可能誤觸全平
- §三 已知 P0：drawdown_revoke G1-06 已部署但「drawdown 觸發 → revoke 流程從未真實 live 觸發」

**運行時證據**：
- ✅ `paper_state_checkpoint`（V018，[paper_state/checkpoint.rs:141](srv/rust/openclaw_engine/src/paper_state/checkpoint.rs)）跨重啟 drawdown 連續性
- ✅ healthcheck [13] 採 cells=62 mtime fresh（CLAUDE.md §三）
- ❌ 「過去 7d HaltSession 觸發次數 + 各 trigger 來源（drawdown/black_swan/fast_track/reconciler）」分桶 — 不存在

**operator 信任度**：

---

#### 原則 #6：失敗默認收縮

**原文**：不確定時默認保守：不開新倉、降頻率、降風險。

**實作位置**：
- 主要負責的模組：
  - H0 Gate 5 子檢查 fail-fast：[core/h0_gate.rs:1067](srv/rust/openclaw_core/src/h0_gate.rs)（Session 1 第 2 批）
  - Python H0：[h0_gate.py:971](srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/h0_gate.py)
  - Cognitive modulator：[core/cognitive.rs:524](srv/rust/openclaw_core/src/cognitive.rs)（連虧時 confidence_floor↑、qty_ceiling↓、scan_interval↑）
  - Live auth fail → graceful shutdown：[live_authorization.rs:620](srv/rust/openclaw_engine/src/live_authorization.rs) + [live_auth_watcher.rs:957](srv/rust/openclaw_engine/src/live_auth_watcher.rs)
  - Strategist scheduler 指數 backoff（5m→30m→60m→4h，Session 1 第 7 批）
- 相關資料流：[Flow 5（cost_gate fallback）](inventory_2_data_flows.md#資料流-5) + [Flow 6（live auth）](inventory_2_data_flows.md#資料流-6)
- 配置來源：RiskConfig.cognitive + cost_gate.missing_edge_fallback_bps + ws_backoff

**測試覆蓋**：
- 單元測試：h0_gate.rs 內測 + cognitive.rs（EMA α=0.3 平滑）+ ws_backoff.rs（jitter_pct=0 RNG 停用）
- Python：cognitive_modulator.py 雙源測試

**運行時驗證**：
- ✅ Live auth failure → engine graceful shutdown（cancel_token，[live_authorization.rs:329](srv/rust/openclaw_engine/src/live_authorization.rs)）
- ✅ ws_backoff 指數退避防 reconnect 風暴（[ws_backoff.rs:192](srv/rust/openclaw_engine/src/common/ws_backoff.rs)）
- ✅ cost_gate fallback ATR×conf×0.2 當 edge_estimates 缺（Session 3 Flow 5 步 8）
- ✅ Spawn backoff for Live slot（[spawn_backoff.rs:345](srv/rust/openclaw_engine/src/spawn_backoff.rs)）防 REST 風暴
- ❌ **3 大 Verified 發現 (2) PostOnly 配置反向**：`strategy_params_demo.toml` PostOnly=false / `_live.toml` PostOnly=true — **demo 不收縮、live 偏激進**，違反原則 #6（CLAUDE.md §三 + Session 3 Flow 4 §三 相關）
- ⚠️ **Python `shadow_decision_builder.py:395` IPC fail → silent drop**（fail-open）— Session 2 第 5 批，**與原則 #6 緊張**

**Gap 說明**：
- **PostOnly 反向**是 G1-05 立即修目標（CLAUDE.md §三）— 這條原則在實際 TOML 配置上**已知違反**
- **fail-open 多處**：agent_audit_bridge fail-open（Session 3 Flow 7 步 3）；shadow_decision_builder fail-open；觀察上「不阻塞主流程」屬合理，但**監控側不靜默**就需另寫 healthcheck
- **edge_estimates startup-only 熱重載**（Session 3 Flow 5 斷鏈點 2）：scheduler 寫了新檔，engine 不讀到，cost_gate 持續用 stale fallback — 類似「失敗默認收縮失效」
- §三 LEARNING-PIPELINE-DORMANT-1：cost_gate 綁定條件未達，目前不上限 / 不收縮

**運行時證據**：
- ✅ ws_backoff 計數（Session 1 第 3 批）
- ✅ Live auth re-verify 次數（5min lease 層）
- ❌ 「fail-open 路徑被觸發次數」綜合儀表 — 不存在

**operator 信任度**：

---

#### 原則 #7：學習 ≠ 改寫 Live

**原文**：學習平面與 Live 平面隔離。

**實作位置**：
- 主要負責的模組：
  - Rust ML registry V023 dormant（[ml/registry.rs:470](srv/rust/openclaw_engine/src/ml/registry.rs)，Session 1 第 6 批）
  - Python model_registry：[ml_training/model_registry.py:430](srv/program_code/ml_training/model_registry.py)
  - Edge predictor 永 Err(NoModel) default：[edge_predictor/null_backend.rs:96](srv/rust/openclaw_engine/src/edge_predictor/null_backend.rs)
  - Optuna 強制 backtest_mode=True：[ml_training/optuna_optimizer.py:946](srv/program_code/ml_training/optuna_optimizer.py)
  - EvolutionEngine 強制 backtest_mode=True：[local_model_tools/evolution_engine.py:567](srv/program_code/local_model_tools/evolution_engine.py)
  - Promotion pipeline 5 tier：[promotion_pipeline.py:636](srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/promotion_pipeline.py) LEARNING→PAPER_SHADOW→DEMO_ACTIVE→LIVE_PENDING→LIVE_ACTIVE
  - Strategist scheduler 持久化已應用 params（[strategist_scheduler/persist.rs:446](srv/rust/openclaw_engine/src/strategist_scheduler/persist.rs)）
- 相關資料流：[Flow 5（learning→edge_estimates→cost_gate）](inventory_2_data_flows.md#資料流-5) + [Flow 3（Layer 2）](inventory_2_data_flows.md#資料流-3)
- 配置來源：LearningConfig.teacher_loop_enabled（Session 1 第 3 批）

**測試覆蓋**：
- 單元測試：cpcv_validator.py（4-fold CPCV + embargo）+ leakage_check.py（特徵洩漏白名單）
- Rust ml/scorer.rs 3-tier degradation（ONNX→rule→0.5 固定）
- onnx_exporter 精度驗證 max|LGB-ONNX|<1e-3

**運行時驗證**：
- ✅ Phase 1a：registry 空 + 5 `/api/v1/ml/*` routes 回 404（CLAUDE.md §三）— Live 端不讀 ML 推理
- ✅ Combine layer Phase 1a `ml_opt=None` + `ml_override_high=2.0` 雙重保險（[combine_layer.rs:779](srv/rust/openclaw_engine/src/combine_layer.rs)）
- ✅ Teacher loop default OFF（[consumer_loop.rs:665](srv/rust/openclaw_engine/src/claude_teacher/consumer_loop.rs)）
- ⚠️ **Edge estimates 是「學習→Live」唯一活躍橋**：JS shrunk 估計直接影響 cost_gate；Phase 5 cost_gate 綁定條件未達意味目前 Live 行為不被學習實質改變（CLAUDE.md §三）
- ❌ Strategist scheduler 寫已應用 params 持久化在 V019/V020 schema — 5min 自動下發策略參數修改是「學習→Live」途徑（不需 Operator 批准）

**Gap 說明**：
- **strategist scheduler 自動參數變更**：[strategist_scheduler/mod.rs:1166](srv/rust/openclaw_engine/src/strategist_scheduler/mod.rs)（Session 1 第 7 批）每 5min UpdateStrategyParams IPC 改 5 策略運行時參數 — 落在「學習平面 → Live 平面」灰色區
- **edge_estimates startup-only 反成保護**：意外地 enforce 隔離（學習更新需 restart 才生效），但這不是設計（Session 3 Flow 5 斷鏈點 2）
- promotion_pipeline.py LIVE_ACTIVE 需 operator 批准 — 純 Python 路徑（Rust 不參與晉升決策）

**運行時證據**：
- ✅ `learning.strategist_applied_params` 表（V019+V020，[strategist_history_routes.py:701](srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/strategist_history_routes.py)）有 7d edge effect join
- ✅ `learning.linucb_state`（V009/V010）+ schema_hash 不符 → SchemaMismatch（Session 1 第 6 批）
- ❌ 「過去 7d 自動 strategist tune 次數 vs operator manual promote 次數」對照 — 部分在 STRATEGIST-HISTORY-OBSERVABILITY-1 但完整性未驗

**operator 信任度**：

---

#### 原則 #8：交易可解釋

**原文**：每筆交易必須可重建：為什麼、何時、風控審批、授權、執行、結果。

**實作位置**：
- 主要負責的模組：
  - context_id 為交易主鍵：所有 trading.* + learning.* 表共享
  - rejection_coding.rs 561 行：[intent_processor/rejection_coding.rs:561](srv/rust/openclaw_engine/src/intent_processor/rejection_coding.rs)（統一原因碼）
  - decision_features writer：[decision_feature_writer.rs:231](srv/rust/openclaw_engine/src/database/decision_feature_writer.rs)（17 維 FeatureVectorV1）
  - exit_features writer：[exit_feature_writer.rs:325](srv/rust/openclaw_engine/src/database/exit_feature_writer.rs)（7 維 Track P）
  - decision_context_snapshots writer：[context_writer.rs:307](srv/rust/openclaw_engine/src/database/context_writer.rs)
  - V014 governance audit row：handlers/governance.rs + handlers/risk.rs
- 相關資料流：[Flow 1 步 5+7+8](inventory_2_data_flows.md#資料流-1) + [Flow 2 步 7+8](inventory_2_data_flows.md#資料流-2) + [Flow 4 步 7+8](inventory_2_data_flows.md#資料流-4)
- 配置來源：所有 trading.* + learning.* schema（V001-V024）

**測試覆蓋**：
- 單元測試：rejection_coding.rs（字面值釘死 byte-identical，保 audit + test 契約）
- 整合：trading_writer.rs 內測 + handlers/risk.rs 含 V014 audit 寫入測試

**運行時驗證**：
- ✅ trading.fills.context_id ↔ learning.decision_features.context_id 為主關聯鍵（Session 3 Flow 2 步 8 + Flow 5 步 1）
- ✅ rejection 原因碼統一（rejection_coding.rs 字面值不可動）
- ✅ V014 audit 含被拒絕路徑（CLAUDE.md §三）
- ⚠️ **Python change_audit_log 無 PG 寫入**（grep 驗證：change_audit_log.py + audit_persistence.py 全文 0 個 INSERT INTO）— Session 3 Flow 7 步 7「DB 表名未驗」確認**為負**
- ⚠️ outcome_backfiller bug 歷史：timeframe '1' vs '1m' + engine_mode INSERT 漏接（Session 1 第 7 批 + Session 3 Flow 5 步 2）已 2026-04-21 fix `5e2981d` — 過去 audit chain 曾斷
- ❌ **engine_mode 100% 'paper' 過往 bug**：memory `project_decision_outcomes_not_dead.md` — 修復後 engine_mode 標籤 live_demo 升級（memory `project_engine_mode_tag_live_demo.md`）

**Gap 說明**：
- **Python agent audit 無 PG**：grep 驗證確認 change_audit_log.py 0 INSERT；audit_persistence.py 0 INSERT — agent 事件只在 in-memory + JSONL；重啟記憶體 list 丟失，JSONL 滾出後也丟。**這是治理盲區**，原則 #8「可重建」靠 PG，agent 路徑不滿足
- **decision_outcomes 100% NULL** 歷史 bug + 修復見 memory；當前狀態「現 187 cells / mtime <30min」（CLAUDE.md §三）— 但 1 cell 災難 4 天無人發現顯示 healthcheck 滯後
- §三 P1：strategist_history_routes 7d edge effect join 有 lag — 可解釋鏈在「應用後 effect 觀察」這環有時間窗

**運行時證據**：
- ✅ `trading.intents` / `trading.fills` / `trading.risk_verdicts` / `trading.signals` / `learning.decision_features` 全 PG（Session 3 各流持久化點）
- ✅ V014 governance audit
- ❌ Python agent decision audit 無 PG 表 — Session 3 Flow 7 確認

**operator 信任度**：

---

#### 原則 #9：交易所災難保護

**原文**：本地止損 + 交易所條件單雙重防線。

**實作位置**：
- 主要負責的模組：
  - 本地止損：[core/stop_manager.rs:557](srv/rust/openclaw_core/src/stop_manager.rs)（Session 1 第 2 批）— Hard/Trailing/Time stops + ATR 倉位
  - Track P v2 物理 lock：[exit_features/v2.rs:895](srv/rust/openclaw_engine/src/exit_features/v2.rs)（physical_micro_profit_lock_v2）
  - Combine layer 物理 Lock 不可被 ML veto：[combine_layer.rs:779](srv/rust/openclaw_engine/src/combine_layer.rs)
  - 交易所條件單：[position_manager.rs:845](srv/rust/openclaw_engine/src/position_manager.rs) Bybit V5 槓桿/TP-SL/trailing 配置
  - Drawdown revoke：[drawdown_revoke.rs:442](srv/rust/openclaw_engine/src/drawdown_revoke.rs) HaltSession + 刪 authorization.json
- 相關資料流：[Flow 4 持倉 9 checks 含 PHYS-LOCK](inventory_2_data_flows.md#資料流-4)
- 配置來源：RiskConfig.exit + RiskConfig.stop_loss_max_pct

**測試覆蓋**：
- 單元測試：stop_manager.rs（trailing_activation_pct 獨立於 trailing_stop_pct）+ exit_features/v2.rs（Gate 1 semantics v2 修正）
- 整合：position_reconciler/tests.rs 684 行 + tick_pipeline/tests.rs 3524 行涵蓋 Step 6
- e2e：on_tick/helpers.rs 1182 行（Track P T4 audit wrapper + e2e test）

**運行時驗證**：
- ✅ Step 6 9 持倉風控每 tick 呼（PHYS-LOCK 為其中第 6）
- ✅ Phase 6 reconciler 自動降級（CLAUDE.md §三）
- ⚠️ **TRACK-P-V2-SWAP-1 已部署但 v1 仍在當前 PID** — 2026-04-22 V2 swap commit `306993e`，operator 指示先不部署，engine PID 3954769 跑 v1（memory `project_track_p_runtime_live.md`），v2 待下次 `--rebuild` — 與 §三「2026-04-24 21:58 CEST engine 重啟載入」可能已過此 gap，但 memory 顯示對齊
- ✅ healthcheck [7] 135/135 PASS 即時驗證 + phys_lock fire 1-10/day（CLAUDE.md §三）

**Gap 說明**：
- **Bybit 條件單在策略外**：Rust 設置交易所端 TP/SL（position_manager.rs），但設置時機與本地止損的協同邏輯由 strategy 決定 — 沒有「強制要求每筆 open 都同步推交易所條件單」的 invariant 檢查
- §三 P0-13 ATR scale 修復（per-tick → 持倉期 Wilder's ATR），歷史顯示物理 lock 設定值錯誤的 bug 真實發生
- 雙源指標（Rust ATR / Python atr_tracker.py 153 行 [Session 2 第 7 批]）— 「Python bridge/工具專用」標記但雙源語意 drift 風險

**運行時證據**：
- ✅ phys_lock fire 次數（每日 1-10）+ DB `learning.exit_features.giveback_atr_norm` avg 0.3-3.0
- ✅ `market.klines` 1m + Wilder's ATR(14) 持倉期計算
- ❌ 「過去 7d 本地止損觸發 vs 交易所條件單觸發」的對賬 — 推測在 reconciliation_engine.py 但未直接驗

**operator 信任度**：

---

#### 原則 #10：認知誠實

**原文**：所有結論區分事實 / 推斷 / 假設。

**實作位置**：
- 主要負責的模組：
  - DataQualityLevel enum：[openclaw_types/intent.rs:162](srv/rust/openclaw_types/src/intent.rs)（FACT/INFERENCE/HYPOTHESIS，Session 1 第 1 批）
  - Python data_source_enforcer：[data_source_enforcer.py:589](srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/data_source_enforcer.py)（fail-closed 阻未標記）
  - Truth source registry：[truth_source_registry.py:977](srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/truth_source_registry.py)
  - Perception data plane：[perception_data_plane.py:601](srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/perception_data_plane.py)（FACT/INFERENCE/HYPOTHESIS 標註 + freshness）
  - Cognitive params smoothing：[core/cognitive.rs:524](srv/rust/openclaw_core/src/cognitive.rs) EMA α=0.3 防振盪
- 相關資料流：[Flow 3（AI 推理 H4 validate）](inventory_2_data_flows.md#資料流-3) + [Flow 5（shadow vs production）](inventory_2_data_flows.md#資料流-5)
- 配置來源：感知層運行時 tag

**測試覆蓋**：
- 單元測試：data_source_enforcer.py（DataSourceTag fail-closed）+ perception_data_plane.py（quality score）
- Python truth_source_registry：認識論級別 TTL + falsification flow

**運行時驗證**：
- ✅ DataQualityLevel 三值在 TradeIntent 內傳遞（Session 1 第 1 批）
- ✅ Shadow vs production tag（exit_source: 4 stable tags = `phys_lock` / `track_p_micro_profit_lock_v2` / etc.）
- ⚠️ **未標記的數據能否實際進入 hot path 缺強制檢查**：`data_source_enforcer.py:589` reject_untagged 是 Python 層 — Rust hot path 直接從 WS 拿原始 PriceEvent 不經此 gate
- ❌ Truth registry 977 行有 patterns/falsification API，但未驗 hot path 是否消費

**Gap 說明**：
- **Rust hot path 不識別 DataQualityLevel**：tag 在 intent 上但「不影響執行」（Guardian/cost_gate 不讀此值）— 標籤式存在，無實際治理力
- §一定位「對成本與收益有清晰感知，能感知自身狀態」+ 原則 #10 — 概念上清晰但代碼僅在 Python 半實作
- 與 Layer 2 推理鏈記錄相關（memory `project_layer2_agent_design.md`）— Layer 2 自主推理循環尚未完整，認知誠實的「推理鏈追溯」缺實質落地

**運行時證據**：
- ✅ exit_source 4 stable tags（[combine_layer.rs:779](srv/rust/openclaw_engine/src/combine_layer.rs)）
- ✅ shadow_fills_routes 讀 `learning.decision_shadow_fills`（ε-greedy paper only，PAPER-DISABLE-1 後 n=0）
- ❌ DataQualityLevel 統計分佈（hot path 過 N 條 intent，FACT/INFERENCE/HYPOTHESIS 各幾條）— 不存在

**operator 信任度**：

---

#### 原則 #11：Agent 最大自主權

**原文**：P0/P1 硬邊界內，Agent 完全自主決定：幣種、策略、參數、時機。

**實作位置**：
- 主要負責的模組：
  - 此原則主要依賴**設計自律**而非代碼強制
  - Rust scanner 動態 universe（[scanner/runner.rs:315](srv/rust/openclaw_engine/src/scanner/runner.rs)）— 30min cycle，BTC/ETH pinned 其餘自選
  - Strategist scheduler 5min auto-tune 5 策略參數（[strategist_scheduler/mod.rs:1166](srv/rust/openclaw_engine/src/strategist_scheduler/mod.rs)）
  - 5-Agent framework（[multi_agent_framework.py:1137](srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/multi_agent_framework.py)）+ Conductor
  - P0/P1 denylist 字串常量：[claude_teacher/applier.rs:226](srv/rust/openclaw_engine/src/claude_teacher/applier.rs)（CLAUDE.md §四）
  - Cognitive modulator：[core/cognitive.rs:524](srv/rust/openclaw_core/src/cognitive.rs)
- 相關資料流：[Flow 9（Scanner cycle）](inventory_2_data_flows.md#資料流-9-scanner-30min-cycle--動態-symbol-universe)
- 配置來源：ScannerConfig + StrategyParams + cognitive params

**測試覆蓋**：
- 單元測試：scanner/scorer.rs 901 行（4 fitness fn + edge bonus + correlation filter）
- 整合：scanner/registry.rs 486 行（active set + anti-churn）

**運行時驗證**：
- ✅ Scanner 30min 自動選 universe（CLAUDE.md §三）
- ✅ Strategist scheduler 5min 自動 tune 參數（不需 Operator 批准）
- ❌ Agent autonomy「實質受限」由設計自律決定：Python ExecutorAgent shadow hardcoded（CLAUDE.md §三 verified finding 3）— 原則 #11 + #15 共同被原則 #3 蓋過
- ⚠️ Scanner edge bonus 用 `edge_estimates`（Session 3 Flow 9 + Flow 5 串聯斷鏈）— 學習 stale 時 scanner 自主性退化

**Gap 說明**：
- **此原則主要依賴設計自律而非代碼強制** — 不算 gap，但要記憶
- **Live 階段未到，自主性不必極強**：CLAUDE.md §三 demo ≥21d 穩定期，Agent autonomy 在 Live 階段才有壓力測試
- 衍生實施準則「認知調製 ≠ 能力限制」（CLAUDE.md §二）— 提高決策門檻而非關閉能力，cognitive modulator 落實此衍生原則

**運行時證據**：
- ✅ scanner_status IPC（Session 1 第 4 批 handlers/misc）
- ✅ strategist_applied_params 表 7d effect join
- ❌ 「過去 7d Scanner 換 universe 次數 + Strategist auto-tune 次數 + Operator 介入次數」三方對照 — 不存在

**operator 信任度**：

---

#### 原則 #12：持續進化

**原文**：系統必須從交易行為中自動學習（當前 demo 階段：Paper 驗證→參數進化，live 自動部署待 Phase 3 放權框架）。

**實作位置**：
- 主要負責的模組：
  - Edge estimator scheduler：[edge_estimator_scheduler.py:716](srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/edge_estimator_scheduler.py)
  - James-Stein estimator：[ml_training/james_stein_estimator.py:555](srv/program_code/ml_training/james_stein_estimator.py)
  - LinUCB inference + state_io：[linucb/inference.rs:288 + state_io.rs:263](srv/rust/openclaw_engine/src/linucb)
  - Promotion pipeline 5 tier：[promotion_pipeline.py:636](srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/promotion_pipeline.py)
  - Learning tier gate L1-L5：[learning_tier_gate.py:712](srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/learning_tier_gate.py)
  - Quantile reports + dl3_go_no_go + run_training_pipeline（Session 2 第 9 批 ml_training/）
- 相關資料流：[Flow 5（learning→edge_estimates）](inventory_2_data_flows.md#資料流-5)
- 配置來源：LearningConfig + ScannerConfig + 各 ml_training pipeline

**測試覆蓋**：
- 單元測試：cpcv_validator.py + leakage_check.py + quantile_reports.py + dl3_go_no_go.py
- 整合：ml_training/run_training_pipeline.py 526 行 stage 5.5 hook for model_registry
- 契約：parquet_etl 17-feature byte-aligned with Rust schema_hash

**運行時驗證**：
- ⚠️ **LEARNING-PIPELINE-DORMANT-1**（CLAUDE.md §三 P1）— 半解，剩餘 gap：
  - cost_gate 綁定門檻 grand_mean > -50 bps 且 ≥2 策略 shrunk_bps>0 未達
  - ONNX 訓練資料量不足（最大切片 47/200 labels）
  - 21 個 learning schema 表仍無 consumer
- ✅ edge_estimator_scheduler 4 天停滯後 2026-04-24 復活（cells=187 / mtime <30min，CLAUDE.md §三）
- ❌ **Phase 5 PAUSED**（CLAUDE.md §三，2026-04-12 reframe）— PNL-FIX-1/2 揭露所有策略 gross edge 為負 → cost_gate/DL/JS 接線完成但需真實正 edge

**Gap 說明**：
- **學習機制接好但「沒在學」**：管道全通但餵入空（21 表無 consumer + 47/200 labels）
- §三 大量 P1 揭發此原則執行困境：edge_scheduler 停滯靠人發現（healthcheck 4d 滯後）
- model_registry V023 dormant（Phase 1a registry 空 + 5 ml/* routes 全 404）

**運行時證據**：
- ⚠️ `settings/edge_estimates.json` 187 cells fresh
- ⚠️ `learning.realized_edge_stats` + `learning.james_stein_estimates` 應有近期 row（推測，未直接 grep 數量）
- ❌ `learning.model_registry` Phase 1a 空 — 確認

**operator 信任度**：

---

#### 原則 #13：AI 資源成本感知

**原文**：每次 AI 調用計費，cost_edge_ratio ≥ 0.8 → 建議關倉。

**實作位置**：
- 主要負責的模組：
  - Rust BudgetTracker：[ai_budget/tracker.rs:897](srv/rust/openclaw_engine/src/ai_budget/tracker.rs)（SSOT，三段 $80/$95/$100 降級）
  - Pricing：[ai_budget/pricing.rs:299](srv/rust/openclaw_engine/src/ai_budget/pricing.rs)
  - Usage IO：[ai_budget/usage_io.rs:118](srv/rust/openclaw_engine/src/ai_budget/usage_io.rs)
  - Python api_budget_manager 月度 $50：[api_budget_manager.py:250](srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/api_budget_manager.py)
  - Layer 2 cost tracker 日 $2：[layer2_cost_tracker.py:726](srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/layer2_cost_tracker.py)
  - cost_gate（cost vs edge）：[intent_processor/gates.rs:205](srv/rust/openclaw_engine/src/intent_processor/gates.rs)
  - Cost edge ratio 0.8 → 關倉：未在當前 grep 命中具體實作 — 可能在 risk_config_advanced.cost_edge_max_ratio
- 相關資料流：[Flow 3（AI 推理 5+9+10）](inventory_2_data_flows.md#資料流-3) + [Flow 5（cost_gate）](inventory_2_data_flows.md#資料流-5)
- 配置來源：BudgetConfig（Session 1 第 3 批）+ risk_config.cost_edge_max_ratio

**測試覆蓋**：
- 單元測試：ai_budget/tracker.rs 897 行內測 + pricing.rs（fail-closed on missing/parse/inactive）
- Python：api_budget_manager.py（cooldown）+ layer2_cost_tracker.py（adaptive multiplier）

**運行時驗證**：
- ✅ Rust BudgetTracker 為 SSOT（3 層的另兩層為 audit log）— Session 3 Flow 3 步 5
- ✅ 三段降級 $80/$95/$100 寫 PG fail-closed → caller 必拒絕（Session 3 Flow 3 步 10）
- ⚠️ **三層雙計風險**（Session 3 Flow 3 斷鏈點 2）：Layer 2 呼叫被 Python `layer2_cost_tracker` + Rust `tracker` 雙寫；enforcement 只看 Rust
- ❌ cost_edge_ratio ≥ 0.8 → 關倉的具體實作位置與運行時觸發未驗

**Gap 說明**：
- **三層預算雙計**：3 個獨立追蹤但 SSOT 在 Rust，Python 兩層為 audit；對齊機制只在 [layer2_cost_tracker.record_session_end → IPC record_ai_usage] 串聯，配對失敗則 audit 帳本不一致（Session 3 Flow 3 斷鏈點 2）
- AI 成本 → 「關倉」連動的具體實作不在 Session 1/2 模組表格欄位明示

**運行時證據**：
- ✅ `learning.ai_usage_log`（hypertable，Session 3 Flow 3 步 10）— ON CONFLICT DO NOTHING idempotent
- ✅ `cost_state.json`（Layer 2）+ `api_budget_state.json`（Python 月度）
- ❌ 「cost_edge_ratio 觸發關倉的歷史次數」— 不存在

**operator 信任度**：

---

#### 原則 #14：零外部成本可運行

**原文**：基礎運營僅需 L0+L1（Ollama + 免費搜索）。

**實作位置**：
- 主要負責的模組：
  - LocalLLMClient ABC：[local_llm_factory.py:417](srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/local_llm_factory.py)（Ollama / LM Studio 抽象）
  - Ollama client：[ollama_client.py:506](srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/ollama_client.py) max_retries=0 + timeout enforced
  - L1 path (StrategistAgent + h0_gate + h1_thought_gate)：Session 2 第 5+6 批
  - 4-tier search degradation in layer2_tools：[layer2_tools.py:906](srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/layer2_tools.py)（Perplexity→Ollama→DuckDuckGo）
- 相關資料流：[Flow 3 步 7（LLM 兩條 route）](inventory_2_data_flows.md#資料流-3)
- 配置來源：LOCAL_LLM_PROVIDER env + LM_STUDIO_BASE_URL env

**測試覆蓋**：
- 單元測試：local_llm_factory.py 17 pytest（LLM-ABC-MIGRATION-1，CLAUDE.md §三 2026-04-20）+ 11 既有 patch-target 更新
- 契約：LMStudioShimClient 鏡面 OllamaClient surface 0 改動 call-site

**運行時驗證**：
- ✅ LLM-ABC-MIGRATION-1（CLAUDE.md §三 2026-04-20）— 5 call-site 切 `local_llm_factory.get_local_llm_client()` 全業務 code 0 個直接 import OllamaClient
- ✅ Layer 2 hard cap $2/day（DOC-08 §4 absolute）— 觸頂後系統繼續用 L0+L1
- ✅ Mac operator 設 `LOCAL_LLM_PROVIDER=lm_studio` 即可不裝 Ollama

**Gap 說明**：
- **Anthropic API（Layer 2 / Teacher）= 外部成本**：當前可關（hard cap + opt-in）但若 enable 即外部依賴
- 4-tier search 中 Perplexity 也 paid；但有 fallback DuckDuckGo（免費）

**運行時證據**：
- ✅ Ollama HTTP `/api/generate` 與 `/api/chat`（L0+L1 路徑）
- ⚠️ Layer 2 budget_exceeded state（layer2_engine.py:730）切 Anthropic 後可被關
- ❌ 「過去 30d 是否曾在無 Anthropic key 下啟動成功」的歷史日誌 — 不存在

**operator 信任度**：

---

#### 原則 #15：多 Agent 協作

**原文**：5 Agent（Scout/Strategist/Guardian/Analyst/Executor）+ Conductor 編排，正式對象通信。

**實作位置**：
- 主要負責的模組：
  - 5-Agent 業務層 + multi_agent_framework：Session 2 第 5 批（~4552 行）
  - MessageBus：[multi_agent_framework.py:1137](srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/multi_agent_framework.py)
  - 6 AgentRole + MessageType：[openclaw_types/agent.rs:126](srv/rust/openclaw_types/src/agent.rs)
  - core/message_bus.rs：[message_bus.rs:296](srv/rust/openclaw_core/src/message_bus.rs)（Guardian verdict 永遠覆蓋 Strategist）
  - agent_audit_bridge：[agent_audit_bridge.py:406](srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/agent_audit_bridge.py)
  - Strategy_wiring 5 agent + audit_callback wiring（grep 驗證 line 146 / 247 / 308 / 361 / 472 / 511 全 5 agent + paper_live_gate）
- 相關資料流：[Flow 3（5 agent IPC handler）](inventory_2_data_flows.md#資料流-3) + [Flow 7（agent 事件 audit）](inventory_2_data_flows.md#資料流-7)
- 配置來源：strategy_wiring.py（912 行，§九 12+ singleton 登記）

**測試覆蓋**：
- 單元測試：multi_agent_framework.py 1137 行內測（pub/sub + lifecycle）+ test_strategist_audit_wiring.py
- 整合：base_agent.py 公共基類 + 各 agent specialized

**運行時驗證**：
- ✅ 5 agent runtime + audit_callback 全注入（grep `audit_callback` 在 strategy_wiring.py 確認 5 agent + paper_live_gate）
- ✅ StrategistAgent shadow=False live（strategy_wiring:243）
- ❌ **ExecutorAgent shadow=True hardcoded**（CLAUDE.md §三 verified finding 3 + Session 3 Flow 7 步 4）— Python agent 框架運行但**不對 Rust 發單**
- ✅ Rust→Python 5 IPC handler（strategist/analyst/conductor/scout/guardian，Session 2 IPC 表）— 但 Rust 主動觸發只有 strategist_evaluate

**Gap 說明**：
- 5 agent 「協作通信」運行，但 Executor 不 IPC 發單 — 協作鏈到 Executor 為止 shadow（CLAUDE.md §三 G3-02 Wave 2 重構目標）
- Conductor 角色：[ai_service.py:535](srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/ai_service.py:535) `_handle_conductor` 存在但「未完全驗證」（Session 2 IPC 表）
- §三 Layer 2 自主推理循環（新聞搜索 / 宏觀判斷 / 工具箱 / 推理鏈記錄）尚未完整實作

**運行時證據**：
- ✅ 5 agent audit_callback 全注入（grep 驗證）
- ✅ MessageBus pub/sub + Guardian veto override（[message_bus.rs:296](srv/rust/openclaw_core/src/message_bus.rs)）
- ❌ Executor IPC submit_order 觸發次數 — 必為 0（hardcoded shadow）
- ❌ Conductor 觸發次數 — 推測未啟用

**operator 信任度**：

---

#### 原則 #16：組合級風險意識

**原文**：監控關聯曝險、策略重疊持倉、資金分配合理性。

**實作位置**：
- 主要負責的模組：
  - Rust portfolio：[core/portfolio.rs:362](srv/rust/openclaw_core/src/portfolio.rs)（correlation_threshold=0.7, sector cap 40%, reserve 30%）
  - Python portfolio_risk_control：[portfolio_risk_control.py:557](srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/portfolio_risk_control.py)（EX-01 §6 硬限制不可 AI/P2 調）
  - Scanner correlation filter：[scanner/scorer.rs:901](srv/rust/openclaw_engine/src/scanner/scorer.rs)（BTC-beta / 策略 / 板塊 cap）
  - Reconciliation engine：[reconciliation_engine.py:948](srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/reconciliation_engine.py)
- 相關資料流：[Flow 9（Scanner cycle 含 correlation filter）](inventory_2_data_flows.md#資料流-9-scanner-30min-cycle--動態-symbol-universe)
- 配置來源：PortfolioConfig + scanner_config

**測試覆蓋**：
- 單元測試：portfolio.rs 內測（預設 correlation_threshold=0.7）
- Python：portfolio_risk_control.py 557 行（線程安全）

**運行時驗證**：
- ✅ Scanner 30min cycle 應用 correlation filter（Session 1 第 7 批 scorer.rs）
- ⚠️ **Rust portfolio.rs 與 Python portfolio_risk_control.py 雙源**（Session 2 第 7 批標明）— 語意須一致
- ❌ Step 4+5/6 hot path 是否查 portfolio limit？grep 未直接驗
- ❌ 跨 engine_mode 組合視角（paper+demo+live 同時持倉）— 推測由 reconciliation_engine 處理但 948 行未詳讀

**Gap 說明**：
- **雙源 portfolio**：Rust + Python；Rust 為熱路徑，Python 也存在；如 Python 未被 hot path 呼，純 audit 角色
- §三 PIPELINE-SLOT-1 Phase 4 完成（2026-04-19）但完整 portfolio-level 連動未列為已完成里程碑
- §三 G-2 FundingArb 結案 NEGATIVE — 策略級退場，組合級風控的「策略重疊持倉」缺實證 case 觸發

**運行時證據**：
- ✅ scanner correlation 在 [scorer.rs:901](srv/rust/openclaw_engine/src/scanner/scorer.rs)
- ⚠️ portfolio.rs 預設 reserve 30% — 是否 enforce 在 hot path 未驗
- ❌ 「過去 7d 因 correlation 拒絕 intent 次數」— 不存在

**operator 信任度**：

---

### 跨條原則的 gap 分析

#### 1. 優先級衝突的代碼仲裁

CLAUDE.md §二 列出優先級序：

> 帳戶生存 > 風控治理 > 系統健康 > 審計可追溯 > 人類終審 > 真實 Net PnL > 自主能力進化

**代碼如何仲裁**：

| 衝突 | 代碼仲裁點 | 落實程度 |
|---|---|---|
| 風控（#4）vs 自主性（#11）| [intent_processor/router.rs:27](srv/rust/openclaw_engine/src/intent_processor/router.rs:27) Gate 順序強制（H0→Guardian→CostGate→Kelly→OMS）| ✅ 編譯期 NLL 鎖定 |
| 帳戶生存（#5）vs 利潤 | [drawdown_revoke.rs:442](srv/rust/openclaw_engine/src/drawdown_revoke.rs) HaltSession + 刪 authorization | ✅ 5s 內 watcher 偵測 |
| 系統健康 vs 自主性 | [scanner/runner.rs:315](srv/rust/openclaw_engine/src/scanner/runner.rs) `min_hold_cycles` + `challenger_threshold` 防 churn | ✅ 配置層強制 |
| 審計可追溯（#8）vs 性能 | trading.fills + risk_verdicts 同步寫（3× 失敗 → JSONL fallback）| ⚠️ Python agent audit 無 PG（grep 驗證確認）— 此優先級在 Python 平面**沒落地** |
| 人類終審 vs 自動學習（#7/#12）| [promotion_pipeline.py:636](srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/promotion_pipeline.py) LIVE_ACTIVE 需 operator 批准 | ✅ 但 strategist_scheduler 5min 自動 tune 不需 operator — 灰色 |
| 自主能力進化（#11+#12）為最低 | LEARNING-PIPELINE-DORMANT-1 + Phase 5 PAUSED 同時阻塞 | ✅ 自然下沉 — 高優先 P0/P1 卡住，學習自動推遲 |

**結論**：優先級序在 Rust hot path 由 Step 順序 + NLL 鎖定（強），在 Python 並列鏈（agent / GUI / settings）多為「設計自律」（弱）。

---

#### 2. 多條原則共用的單點

| 樞紐 | 同時承擔原則 | 風險 |
|---|---|---|
| **RiskConfig（[risk_config.rs:908](srv/rust/openclaw_engine/src/config/risk_config.rs)）+ ConfigStore ArcSwap** | #2 讀寫分離 / #4 風控不可繞過 / #5 生存 / #6 失敗收縮 / #11 P0/P1 邊界 / #16 組合風險 | RiskConfig.toml 編輯（如 PostOnly 反向 verified finding 2）即多原則同時失守 |
| **GovernanceHub + 5 SM cascade** | #2 / #3 / #4 / #8 | governance_hub.py 1014 行接近硬上限；mixin 拆分後 cascade.py 811 行；任一 SM 邏輯 bug 級聯失效 |
| **IntentProcessor.process_with_features**（[router.rs:27](srv/rust/openclaw_engine/src/intent_processor/router.rs:27)）+ 935 行 step_4_5_dispatch.rs | #1 / #4 / #6 / #8 / #13 | NLL 借用語意鎖定不可拆，但若有 fast_track（[fast_track.rs:407](srv/rust/openclaw_engine/src/fast_track.rs)）旁路 bug，4 條原則同時破（FA-PHANTOM-1 歷史驗證）|
| **trading.fills + context_id**（trading_writer.rs / decision_feature_writer.rs / outcome_backfiller.rs）| #7 / #8 / #12 | engine_mode INSERT 漏接（2026-04-21 fix）一度讓 #8 可解釋 + #12 持續進化同時失守 |
| **edge_estimates.json startup-only**（[edge_estimates.rs:387](srv/rust/openclaw_engine/src/edge_estimates.rs)）| #6 失敗收縮 / #7 學習隔離 / #12 持續進化 | scheduler 4d 停滯 + 1 cell 災難（CLAUDE.md §三 G1-01）— 學習斷鏈 + cost_gate 用 stale fallback + 收縮失效|
| **authorization.json HMAC + watcher**（[live_authorization.rs:620](srv/rust/openclaw_engine/src/live_authorization.rs) + [live_auth_watcher.rs:957](srv/rust/openclaw_engine/src/live_auth_watcher.rs)）| #2 寫入受限 / #3 lease / #5 生存 / #11 P0/P1 邊界 | HMAC key 漂移即 5 重門控之一失效，全 Live 拆 |

**最高風險樞紐**：**RiskConfig + ConfigStore ArcSwap** — 1 個結構同時承擔 6 條原則；其 TOML 配置由 4 IPC 寫入面 + TOML 直接編輯雙路徑，配置反向（PostOnly verified finding 2）即多原則 silently 失守。

---

#### 3. 治理盲區（§二 沒規範但實際需要）

本次盤點發現以下治理條目 §二 未規範，但實作中已半實作或缺失：

##### A. **Audit chain 應同時在 Rust + Python 平面持久化到 PG**

**現狀**：Python `change_audit_log.py` + `audit_persistence.py` 全文 0 個 `INSERT INTO`（grep 驗證）— Python agent audit 只在 in-memory list + JSONL；Rust 有 V014 governance audit。

**問題**：原則 #8「可重建」靠 PG 串接，agent 路徑無 PG = 重啟丟記憶體 + JSONL 滾出後也丟。

**建議新增**：原則 #8 衍生「所有 audit 路徑必達 PG」實施準則，或 §三 列為新 P1。

##### B. **熱重載契約應對所有 Config 一致**

**現狀**：RiskConfig / BudgetConfig / LearningConfig / StrategyParams 走 ArcSwap tick-level；但 `edge_estimates.json` startup-only（Session 3 Flow 5 斷鏈）；ScannerConfig 推測 30min cycle 才 reload。

**問題**：某些「學習平面 → Live 平面」的關鍵橋（edge_estimates）無熱重載 = scheduler 修復後仍需 restart engine 才生效。

**建議新增**：實施準則「跨平面橋必熱重載 < 60s」；或將原則 #6 衍生「Config drift detect」要求。

##### C. **雙源語意對齊驗證**

**現狀**：多個 Rust ↔ Python 雙源（SM-04 / SM-02 / Guardian / atr_tracker / portfolio / cognitive_modulator）由「memory `feedback_rust_authoritative_config.md`」聲明 Rust 為權威，但 byte-identical 約束無自動測試。

**問題**：drift 風險長期累積；Python 端代碼若被 hot path 呼到（Session 3 Flow 4 斷鏈點 3 guardian_agent 推測未呼），語意分叉。

**建議新增**：原則 #2 衍生「雙源語意 byte-identical 自動驗證」，類似 openclaw_types schemas/shared_types.json golden test 模式。

##### D. **「被動等待」必附 healthcheck 已落實但**「**主動推進**」**事件無類似 invariant**

**現狀**：CLAUDE.md §七 已有「被動等待 TODO 必附 healthcheck（強制，2026-04-23 新增）」+ 17 check；但「主動推進」事件（如 strategist_scheduler 自動 tune / scanner 換 universe）無類似 cadence audit。

**問題**：scheduler 4d 停滯靠人發現（G1-01）— 主動週期任務若靜默卡住，無 metric 偵測。

**建議新增**：實施準則「定期 daemon 必附 last-cycle ts metric + cron alarm」。

##### E. **GUI 寫入面盤點已存在但未制度化**

**現狀**：memory `project_gui_write_paths_inventory.md`（93 endpoints 分類 + Rust trading_mode 是冷參數陷阱 + fake-success 真假判別）— 但無法常態確認新 GUI route 不引入新冷參數。

**問題**：fake-success / 冷參數陷阱屬「假寫」+「假治理」雙重盲區。

**建議新增**：原則 #2 衍生「新 GUI write endpoint 必標 hot/cold + IPC verify」。

---

### 結論摘要

- **最強原則**：#1 / #4 / #5 / #8（Rust hot path 由 Step 順序 + NLL 鎖定 + PG audit 強制）
- **最弱原則**：#3 AI ≠ 即時命令（Executor shadow hardcoded）+ #10 認知誠實（DataQualityLevel hot path 不識別）+ #15 多 agent 協作（Executor 不 IPC 發單）
- **最高風險樞紐**：RiskConfig + ConfigStore ArcSwap（6 條原則共用）
- **最大治理盲區**：Python agent audit 無 PG 持久化（原則 #8 半失守）


---

## Part 4 — 風險熱點清單與紅色清單（Session 5/5）

> 來源：[.claude_reports/inventory_4_risk_hotspots.md](.claude_reports/inventory_4_risk_hotspots.md)
> 涵蓋：六維風險熱點（複雜度/耦合/沉默/新鮮/歷史/邊界）+ Top 5 紅色清單作為 Live 上線前優先處理項。

### 盤點交付物 #4 — 風險熱點清單（Session 5/5 收官）

本文件交叉提煉前四份盤點（[1a Rust](inventory_1a_rust_modules.md) / [1b Python](inventory_1b_python_modules.md) / [2 資料流](inventory_2_data_flows.md) / [3 治理](inventory_3_governance_audit.md)）為六維風險熱點 + Top 5 紅色清單，作為「上 live 前優先處理項」的對照地圖。

每個熱點條目都可追溯到 Session 1–4 的**具體位置**（檔案 + 行號或表格批次）；「最壞情況」欄位描述「如果不修就上 live 會發生什麼」的具體後果。

**校對狀態**：
- 「複雜度」用行數作為 cyclomatic complexity 的 proxy（未跑 `radon cc`，因 Mac 開發機上無 PG runtime + sub-agent 已抽掉檔頂結構）
- 「新鮮」直接 `git log --since="30 days ago" --name-only` 統計，已過濾 markdown/static
- 「歷史」抽自 CLAUDE.md §三 P0/P1 條目與 Session 1–4 中的相關引用
- 所有「最壞情況」欄位以「Live 階段未上前」立場推演，非「現在 demo 已壞」

---

#### 1. 複雜度熱點 Top 10

**標準**：行數作為 cyclomatic complexity 的 proxy（未跑 `radon`），優先取「單檔超 §九 1200 硬上限或接近、且非測試檔、且承擔多責的 production 模組」。

| 排名 | 函式 / 模組 | 位置 | 複雜度指標 | 最壞情況 |
|---|---|---|---|---|
| 1 | `main.rs`（tokio runtime + SIGHUP/SIGTERM + 引導，**Session 1 第 3 批**） | [srv/rust/openclaw_engine/src/main.rs](srv/rust/openclaw_engine/src/main.rs) | 2062 行（**遠超 §九 1200 硬上限**），12 unwrap/expect 在 production path | 啟動順序若有 race，engine crash 後 watchdog 重啟仍進壞態（如 ConfigStore 載入失敗但 Pipeline 已 spawn）；rolling restart 時 Live auth 載入路徑未完全分離。Session 1 自承「main.rs 拆 startup/ 後仍 2062 行」。 |
| 2 | `instrument_info.rs`（合約規格快取，Session 1 第 7 批） | [srv/rust/openclaw_engine/src/instrument_info.rs](srv/rust/openclaw_engine/src/instrument_info.rs) | 1975 行（**超硬上限**） | qty/price/min notional 圓整錯誤 → `OrderManager::create_order()` validate fail → 策略發信號但 PG `trading.intents` 為空（Session 3 Flow 1 斷鏈點 3 已記錄）。 |
| 3 | `bybit_rest_client.rs`（V5 REST 簽名 + rate limit 追蹤，Session 1 第 7 批） | [srv/rust/openclaw_engine/src/bybit_rest_client.rs](srv/rust/openclaw_engine/src/bybit_rest_client.rs) | 1725 行，24 unwrap/expect | HMAC 簽名邏輯 + 3 種 base URL（mainnet/testnet/demo）混在單檔；rate limit 計算錯誤直接導致 Bybit 拒簽，全策略下單失敗。 |
| 4 | `order_manager.rs`（V5 訂單生命週期，Session 1 第 7 批） | [srv/rust/openclaw_engine/src/order_manager.rs](srv/rust/openclaw_engine/src/order_manager.rs) | 1554 行 | create/amend/cancel/query/execution 全在單檔；某次 amend 路徑 bug 可能導致 live order 卡 PartiallyFilled，position 被掛在交易所無法關閉。 |
| 5 | `ipc_server/mod.rs`（Unix socket JSON-RPC 伺服器，Session 1 第 4 批） | [srv/rust/openclaw_engine/src/ipc_server/mod.rs](srv/rust/openclaw_engine/src/ipc_server/mod.rs) | 1192 行（**剛好擠爆硬上限**） | 連線握手 / auth / dispatch 全在單檔；某條 IPC method 解析 bug 可能讓 GUI 無法 patch RiskConfig，Operator 緊急修參時 5–10s 無回應。 |
| 6 | `tick_pipeline/on_tick/helpers.rs`（Track P T4 audit wrapper + e2e test，Session 1 第 4 批） | [srv/rust/openclaw_engine/src/tick_pipeline/on_tick/helpers.rs](srv/rust/openclaw_engine/src/tick_pipeline/on_tick/helpers.rs) | 1182 行（**接近硬上限**） | RUST-DOUBLE-PREFIX-1 「risk_close: 前綴永遠只有一個」靠這層保證；下次拆分若漏接 `audit_wrapper`，PG `trading.fills.exit_source` 會寫雙前綴，下游 ML/audit grouping 全亂。 |
| 7 | `intent_processor/mod.rs`（H0→Guardian→CostGate→Kelly→OMS 管線，Session 1 第 5 批） | [srv/rust/openclaw_engine/src/intent_processor/mod.rs](srv/rust/openclaw_engine/src/intent_processor/mod.rs) | 1100 行（**擠爆硬上限**） | **唯一寫入口**；任一 Gate 增刪未同步 `rejection_coding.rs:561` 字面值 → audit 原因碼漂移 → 下游 ML feature mismatch（Session 3 Flow 4 §三 列為原則 #1+#4 樞紐）。 |
| 8 | `event_consumer/dispatch.rs`（OPEN intents 指數 backoff 重試，Session 1 第 4 批） | [srv/rust/openclaw_engine/src/event_consumer/dispatch.rs](srv/rust/openclaw_engine/src/event_consumer/dispatch.rs) | 1124 行（**接近硬上限**） | DISPATCH-RETRY-1 OPEN 3 重試 + CLOSE 2 重試；若 budget 配置錯，會看到「OPEN intents 卡 retry 3 次後超時被丟」— Bybit 端收到請求但內部 idempotency key 重複。Live 階段直接導致 orphan position（Session 3 Flow 1 斷鏈點 2）。 |
| 9 | `passive_wait_healthcheck.py`（17+ check + cron 6h，Session 2 第 12 批） | [srv/helper_scripts/db/passive_wait_healthcheck.py](srv/helper_scripts/db/passive_wait_healthcheck.py) | **1822 行**（嚴重超硬上限） | 17 個 check 在單檔 1822 行；G6 audit 框架的核心。曾經 `[13]` 漏判 edge_estimator 4 天停滯（G1-01）；下次邊界 case 漏判靜默 pass 風險高。Live 階段「壞了沒人知道」。 |
| 10 | `live_session_routes.py`（14 routes Live session 控制，Session 2 第 3 批） | [srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/live_session_routes.py](srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/live_session_routes.py) | 1449 行（**超硬上限**） | start/stop/pause/close 全在單檔；雙重門控 operator + live_reserved 邏輯複雜；某次 race 可能讓 Operator 看到 Live=Active 但實際 Rust pipeline 未 spawn → 「假成功」陷阱（memory `project_gui_write_paths_inventory.md`）。 |

備註：以下純測試檔行數更高，但不列入因不在 production hot path：`tick_pipeline/tests.rs` 3524、`bb_breakout/tests*.rs` 1759、`intent_processor/tests.rs` 1905、`paper_state/tests.rs` 1362。

---

#### 2. 耦合熱點 Top 10

**標準**：被依賴次數（fan-in）最高的模組。從 Session 1/2 盤點中「關鍵依賴」欄位 + Session 3 跨流共享狀態 + Session 4 多原則樞紐分析提取。

| 排名 | 模組 | 被 X 個模組依賴 | 如果改它會影響 | 最壞情況 |
|---|---|---|---|---|
| 1 | **RiskConfig + ConfigStore ArcSwap**（[risk_config.rs:908](srv/rust/openclaw_engine/src/config/risk_config.rs) + [config/store.rs:837](srv/rust/openclaw_engine/src/config/store.rs)） | tick_pipeline / intent_processor / position_risk_evaluator / risk_checks / edge_predictor / scanner / Guardian（派生視圖）— **6 條根原則共用**（Session 4 跨條 meta-gap top 1） | 21 IPC 風控參數 + 4 寫入面 + TOML 直編輯 | TOML PostOnly demo=false / live=true 反向（已知 G1-05 verified finding 2）即 6 原則 silently 失守。Live 階段一次配置反向直接 5–10 分鐘窗口下「demo 不收縮、live 過度激進」。 |
| 2 | **TickPipeline**（[tick_pipeline/mod.rs:1035](srv/rust/openclaw_engine/src/tick_pipeline/mod.rs)） | 持有 IntentProcessor + paper_state + governance + 各 Config 快照；Step 0–6 全經此（Session 1 第 4 批） | 任一 sub-pipeline 改造 | 「獨佔所有者」pattern 無鎖；任何 borrow 結構改變都可能破編譯 OR 引入 silent runtime bug。Session 1 自承 1035 行接近硬上限。 |
| 3 | **`main_legacy.py` 468 行 singleton 聚合**（Session 2 第 2 批） | 18 檔下游 `from . import main_legacy as base` + 3 個 `importlib.reload(main_legacy)` 測試契約 | Settings / STORE / app / limiter 4 singleton + middleware 重新初始化 | reload 契約破壞 → CI 測試 hang；STORE 寫入點漂移 → GUI 看到的快照與真實狀態不一致（snapshot identity 不變性違反）。 |
| 4 | **GovernanceHub**（[governance_hub.py:1014](srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/governance_hub.py) + cascade 811 + event_handlers 237） | 3 SM cascade（auth/lease/risk_gov）+ 5-Agent audit_callback wiring + ACL 裁決 | 任一 SM 邏輯 bug 級聯失效 | cascade 回調若鎖外發失誤 → deadlock；mixin 拆分後 cascade.py 811 行任一語意改變都可能讓 SM-04 Risk escalation 不觸發。 |
| 5 | **shared `Arc<AtomicBool> session_halted`**（[news/guardian_impl.rs:169](srv/rust/openclaw_engine/src/news/guardian_impl.rs) + [claude_teacher/governance_impl.rs:206](srv/rust/openclaw_engine/src/claude_teacher/governance_impl.rs)） | News pipeline halt + Teacher veto **同一 Arc** — Session 3 Flow 7+10 共享 | 雙寫源任一斷線 | News severity flip halt → teacher 拒新 directive；若反向 race，teacher 解 halt 但 news 仍 high severity → 在重大新聞期間恢復下單。 |
| 6 | **`ipc_client.py`**（[ipc_client.py:818](srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/ipc_client.py)） | 全 Python 寫路徑經此（risk_routes / live_session_routes / paper_routes / strategy_write / control_ops / live_trust_routes / 等 12+ caller） | 連續 3 失敗→ai_available=false 後**無自動恢復**（Session 2 footer #4） | Engine restart 時 Python 連續失敗 3 次後 GUI 顯示「IPC 不可用」直到 uvicorn 重啟；Operator 看不到 Engine 已恢復。 |
| 7 | **`ai_service_client.rs`** ↔ **`ai_service.py`**（Session 2 IPC 表第二段） | Rust→Python 5 handler（strategist/analyst/conductor/scout/guardian） | 唯一 Rust 熱路徑能觸發 Python AI 路徑 | strategist_evaluate IPC 斷線 → 5min 內無 AI tune；但 Rust hot path 不依賴此（Pure Rust 下單），AI tune 是 cherry on top — 風險中等而非高危。 |
| 8 | **`step_4_5_dispatch.rs:935`**（**不可再拆**，Session 1 第 4 批） | 5 strategy → IntentProcessor 主分派；NLL borrow checker 鎖定（disjoint-field 僅單 fn 有效） | 任一拆分嘗試 | 重構失誤 → strategy → intent plumbing 編譯錯（Session 3 Flow 1 斷鏈點 1）；若 NLL 在新版本 Rust 編譯器放寬，可能新增子函式拆出，但語意 invariant 缺自動測試。 |
| 9 | **`local_model_tools/` 14 stub**（Session 2 第 10 批）+ `strategy_wiring.py:912` | KLINE_MANAGER / INDICATOR_ENGINE / SIGNAL_ENGINE / ORCHESTRATOR + 5 agents + MessageBus + ... 12+ singleton；strategy_read_routes / strategy_ai_routes / scanner_rate_limiter 等 import stub 作 fallback | 任一 stub 改為實作 | 若 operator 誤以為 stub 是「乾淨的 fallback」，新增 strategy 註冊邏輯到 stub 會讓 Rust 真實 strategies 與 Python stub 雙寫，運行時行為依 import 順序。 |
| 10 | **`exit_features/v2.rs`**（physical_micro_profit_lock_v2，Session 1 第 6 批） | combine_layer.rs（Track P+L 融合）+ tick_pipeline Step 6 priority 6 + position_risk_evaluator 全消費此 | TRACK-P-V2-SWAP-1 commit 已部署但 `2026-04-22` operator 指示先不部署，PID 3954769 仍跑 v1（memory `project_track_p_runtime_live.md`）— 雖 §三 已記載 04-24 重啟 | v1 與 v2 行為差別在 Gate 1 semantics（v2 限定唯有 Gate 4 trailing 合法 Lock）；現網若還在 v1 + memory 紀錄錯，物理 Lock 觸發次數異常但不被偵測（healthcheck `[7]` 對 v2 specific 假設）。 |

---

#### 3. 沉默熱點 Top 10

**標準**：critical path（Session 3 必含 8 條資料流）× 測試覆蓋低。覆蓋低 = Session 1/2 表格中「潛在風險」欄位提到「無對應測試」/「未直接驗證」/「推測」/「未完整讀過」。

| 排名 | 模組 | 位於資料流 # | 測試現況 | 最壞情況 |
|---|---|---|---|---|
| 1 | **`change_audit_log.py:160`** + **`audit_persistence.py:549`**（Session 2 第 1 批） | 流 7（Agent audit） | grep 全 srv/ 0 個 `INSERT INTO`（Session 4 §3.A 驗證）；只在 in-memory `_changes` list + JSONL | 重啟丟記憶體 list；JSONL 滾出後 audit 也丟。原則 #8「可重建」在 Python agent 路徑根本不滿足。Live 階段 5-Agent 任一決策事件無 PG 記錄 → 事故重建只能靠 in-memory（0 行）。 |
| 2 | **`edge_estimates.rs:387` startup-only**（Session 1 第 6 批） | 流 5（Learning→cost_gate） | 無 IPC 熱重載；改檔需 engine restart 才生效 | scheduler 修復後（如 G1-01 同日 02:06 `--rebuild`）engine 不重啟就用舊 1-cell HashMap。Live 階段 4 天 stale → cost_gate fallback ATR×conf×0.2 → 全策略持續低 edge 拒單但無告警。 |
| 3 | **`engine_maintenance.flag` CREATE 點**（Session 3 Flow 8 步 4） | 流 8（Crash→Watchdog→Restart） | sub-agent 6 + 主會話 grep 在 restart_all.sh / watchdog 全 source 找不到 `touch` / `> file` 命令 | 若 deploy 流程依賴「flag 自動建立 → 阻塞 watchdog → 升級完 rm」invariant，但 CREATE 點實際不存在，watchdog 可能在 deploy 中誤啟動 restart。 |
| 4 | **`ExecutionListener` callback 註冊位置**（Session 3 Flow 2 步 4） | 流 2（Bybit fill→DB） | sub-agent 2 報告「Cannot trace exact file:line」；推測在 `event_consumer/bootstrap.rs:847` 27 binding 中 | 某次 refactor 漏掉 `set_on_fill()`，會看到 Bybit 端有 fill 但 Rust 內存未更新 → reconciler 30s 輪詢揭發 drift → SM-04 escalate；Live 階段 30s 內 `paper_state` 落後現實。 |
| 5 | **`5-agent wiring asymmetric audit_callback`**（Session 3 Flow 7 斷鏈點 5） | 流 7（Agent audit） | 主會話只直接驗 ExecutorAgent line 482 + strategy_wiring line 467–468；其他 4 agent wiring 注入未直接 grep（`feedback_workflow_audit_chain.md` 暗示 E5-FN-3 部分接線 NOT all） | 若 ScoutAgent 或 AnalystAgent 漏接 `audit_callback`，他們的 _audit() 永遠 silent skip（fail-open）；audit log 看不到該 agent 的事件，operator 誤以為「沒事」。 |
| 6 | **`Python guardian_agent.py`** vs **Rust `core::guardian.rs`** 雙源（Session 3 Flow 4 斷鏈點 3） | 流 4（Guardian） | 「推測：僅 IPC `_handle_guardian` handler 呼，非 hot path」未實證 | 若 Python guardian_agent 在某條路徑取代 Rust Guardian，會導致風控雙寫不一致；DEAD-PY-2 後不應該再有，但 Strategist→Guardian IPC handler 是設計性二份，drift 風險長期累積。 |
| 7 | **`atr_tracker.py`** vs **Rust `core::risk::price_tracker.rs`** 雙源（Session 1 第 2 批 + Session 2 第 7 批） | 流 1+4（cost_gate 用 ATR） | 「Python bridge/工具專用」標記但 byte-identical 約束無自動測試 | Spike 閾值 / window 邊界 case Python ≠ Rust → 同 tick 雙端對 ATR 估計分叉 → cost_gate threshold 計算（fee_bps / ATR）誤差，部分 intent 在邊界處被誤拒/誤通。 |
| 8 | **`intent_processor/tests.rs:1905`** 涵蓋率**未驗實際 assertion**（Session 1 footer #5） | 流 1（tick→order） | 1905 行單檔，52 unwrap，但「測試檔行數 ≠ 測試覆蓋」— Session 1 footer 自承 | 若大量是 `assert!(true)` 或 `#[ignore]`，CLAUDE.md §三宣稱「engine lib 1980 passed」可能與實際 cargo test 跑得通的對應關係漂移；Live 上線後發現 H0/Guardian/CostGate gate 邏輯有未測 corner case。 |
| 9 | **`black_swan_detector.rs:536`** 4 signal 投票閾值（Session 1 第 7 批） | 流 1（Step 6）+ 流 4（Guardian） | 內測 + bar_close 觸發；2/4 → Observe / 3/4 → Upgrade / 4/4 → Defensive | 4 signal 中某 signal 失靈（如 MAD/correlation/volume/velocity 任一）→ 仍可能 2/4 通過 → escalate to Defensive 全平。Live 階段一次誤觸全平所有倉位。 |
| 10 | **`audit/counterfactual_exit_audit.py:792`** 整檔未讀（Session 2 第 13 批） | 流 5+研究路徑 | 標「推測：分析出場決策反事實」；Session 2 自承「未讀檔內」 | 若 cron 定期跑且寫入 PG 而誤判 valid `RiskAction` 為 anomalous，可能誤觸 Operator 訊號；或反之，cron 已死但 operator 仍信任其輸出。 |

---

#### 4. 新鮮熱點 Top 10

**標準**：最近 30 天 commit 數最高的 production code（已過濾 `*.md` / `static/` / `tab-*.html`）。指令：

```bash
git log --since="30 days ago" --name-only --pretty=format: | sort | uniq -c | sort -rn
```

**重要說明**：因 git rename 軌跡（如 `tick_pipeline.rs` 之前是單檔，現拆 `tick_pipeline/{mod,on_tick,...}.rs`），同一邏輯模組會跨多 path 出現；表中合併計數有意義的條目。新增/刪除行數未抽（會超出 token 預算），改為「重整類型」標記。

| 排名 | 模組 | 30 天內 commit 數 | 重整類型 | 相關 CLAUDE.md §三 條目 | 最壞情況 |
|---|---|---|---|---|---|
| 1 | `paper_trading_routes.py` | 67 | refactor + PAPER-DISABLE-1 | PAPER-DISABLE-1 / 2026-04-16 paper 預設關 | TD-03 facade + ipc_dispatch 抽出殘留；未拆乾淨可能讓 paper 路徑 silent enable（memory `project_paper_pipeline_disabled_by_default.md`）。 |
| 2 | `pipeline_bridge.py` | 63 | bridge | strategy_wiring 12+ singleton 接線 | 共享 bridge 的任一接線錯，5-Agent 路徑可能讓 ExecutorAgent 走非 shadow（已被 hardcoded 阻擋，但雙保險弱）。 |
| 3 | `event_consumer/mod.rs` | 58 | refactor + bug fix | FIX-26-DEADLOCK-1 / EDGE-DIAG-1 整合 | 6-arm select! 邏輯+ shutdown 平倉序列；任一 arm 改動可能讓 shutdown 漏掉某條 channel → orphan position。 |
| 4 | `phase2_strategy_routes.py` | 58 | facade refactor | TD-02 split facade | 86 行 facade re-export；若新 ai/read/write 子 route 加錯 import 順序（`_ai before _read` 必須），phase 2 GUI 整體 404。 |
| 5 | `tick_pipeline/on_tick.rs`（rename 軌跡） | 51 | TICK-PIPELINE-MOD-SPLIT-1 拆分 | 2274→1012 行 | 主 tick 編排器；任一 step refactor 漏接 `pub use` re-export → 整 tick 路徑 silent skip 該 step。 |
| 6 | `tick_pipeline/mod.rs` | 51 | refactor | TICK-PIPELINE-MOD-SPLIT-1 | 1035 行接近硬上限；下次拆分風險與 5 同源。 |
| 7 | `governance_hub.py` | 44 | mixin 拆分 + cascade | E5-FN Wave + GovernanceHub mixin | cascade 鎖外發回調若 monkey-patch 順序錯，SM-01/SM-02/SM-04 cascade 級聯失效。 |
| 8 | `paper_trading_engine.py` | 43 | reset / sync | PAPER-DISABLE-1 + ARCH-RC1 1C-3-F | Rust 已接管 paper state 權威，Python 還活躍改動意味 wiring shim 仍有改動空間 → 雙寫風險長期累積。 |
| 9 | `main.py` | 43 | runtime_bridge + state_compiler 整合 | snapshot identity 不變性 | runtime_bridge overlay 若 race 寫入 STORE，Operator 看到的 GUI 快照可能與真實狀態漂移幾秒。 |
| 10 | `live_session_routes.py` | 38 | LIVE-GATE-BINDING-1 整合 | 1449 行（**超硬上限**） | start session → SM-01 submit → HMAC 寫入三步跨檔；若順序 race 可能讓 Rust 讀到部分寫入檔案（Session 2 footer #1）。 |

備註：CLAUDE.md（286 commit）/ TODO.md（403）/ docs/CLAUDE_CHANGELOG.md（151）排名前列但不視為代碼熱點，已過濾。

---

#### 5. 歷史熱點 Top 10

**標準**：CLAUDE.md §三 已完成里程碑與進行中清單中多次出現 P0/P1/G/E 編號的模組。從 Session 1–4 中 grep 編號出現次數人工抽取。

| 排名 | 模組 | 關聯編號 | 修復狀態 | 復發風險 | 最壞情況 |
|---|---|---|---|---|---|
| 1 | **`edge_estimator_scheduler.py:716`** + **`edge_estimates.rs:387`** | G1-01 / EDGE-DIAG-1 / EDGE-P3-1 / LEARNING-PIPELINE-DORMANT-1 / P1-7 B | G1-01 同日 2026-04-24 commits `f32629c`/`abc85c0` + 02:06 `--rebuild` 復活；現 187 cells / 59 updated/cycle / mtime <30min | **高** — fcntl leader lock 在 SIGKILL 後不釋放；Rust startup-only 熱重載缺；下次 daemon stall 4 天無人發現重複（healthcheck `[13]` 是後加） | Live 階段 stale `edge_estimates.json` → cost_gate fallback ATR×conf×0.2 → 全策略持續低 edge 但無告警 → 學習鏈完全斷。 |
| 2 | **`executor_agent.py:482`** + **`strategy_wiring.py:467`** | G3-02 Wave 2 / Verified Finding 3 / 原則 #3 / #15 | 確認 hardcoded `_shadow_mode=True`；G3-02 重構未啟動 | **設計性 gap，非 bug** — 但 Live 階段「假治理」鏡頭 | Python 5-Agent 框架運行但 ExecutorAgent **永遠**寫 audit log 不發 IPC `submit_order` → operator 看 audit 以為 agent 在工作，實際下單路徑 = Rust hot path 完全繞過 Lease 機制（原則 #3 lease-based 鏈在 Rust hot path **缺席**）。 |
| 3 | **`strategy_params_{paper,demo,live}.toml` PostOnly** | G1-05 / Verified Finding 2 / 原則 #6 | demo=false / live=true 反向；G1-05 立即修目標但未驗證已 ship | **高** — TOML 直編輯，無 IPC audit；改完 deploy 沒人會 grep 確認 | demo 不收縮 vs live 偏激進，違反「失敗默認收縮」字面意；Live 階段 PostOnly=true 在高波動期 maker 全 timeout → 全策略下不到單。 |
| 4 | **`fast_track.rs:407`** | FA-PHANTOM-1 / 原則 #4 | 90% 閾值＜100% 設計上限的 ratio bug 已修；fast_track 設計性 Guardian 旁路保留 | **中** — 設計風險仍在；下次新增閃崩規則仍可能誤觸全平 | 緊急閃崩判斷誤觸（如 funding 異常被誤判為閃崩）→ ALL strategies forced flatten → Live 階段一次性平倉所有倉位，現金 stuck 在交易所。 |
| 5 | **`engine_watchdog.py:699`** + **`restart_all.sh`** | P0-9 STABILITY-1 / WATCHDOG-DNS-CLASSIFY-1 / P0-6 RCA | P0-9 closed 2026-04-16 為基礎設施事件；DNS classify 邏輯加入 2026-04-20；P0-6 startup triage + natural bootstrap | **中** — Linux systemd unit 缺（sub-agent 6 找不到 `.service` 檔，只有 macOS launchd plist） | DNS 與 panic 混雜（如 DNS error → unwrap panic）→ 強制 "engine_crash" override → 重啟可能無效；Linux 上 watchdog 無 supervision → silent death。 |
| 6 | **`outcome_backfiller.rs:276`** + **`decision_outcomes` 表** | 5e2981d / project_decision_outcomes_not_dead | 2026-04-21 fix；timeframe `'1' → '1m'` + engine_mode INSERT 漏接已修；歷史回填 ~267k rows | **中** — 修了一次的 INSERT 漏接 pattern 可能在新加欄位時重現 | 新加 outcome 欄位（如未來 P3 加 ml_score）若再次漏 INSERT → engine_mode 100% 'paper'（過往 bug）類似復現；ML 訓練資料一直只看到 paper engine。 |
| 7 | **`live_authorization.rs:620`** + **`live_auth_watcher.rs:957`** + **`drawdown_revoke.rs:442`** | LIVE-GATE-BINDING-1 / G1-06 / §四 5 重門控 | LIVE-GATE-BINDING-1 closed 2026-04-18；G1-06 部署但未真實 live 觸發過 | **高** — drawdown event 從未真實 live 觸發（CLAUDE.md §三 自承）；HMAC env var `OPENCLAW_IPC_SECRET` 漂移風險 | drawdown 觸發路徑首次在 Live 跑可能曝露 silent bug（5s 內仍能下幾筆單，watcher 來不及 teardown）；HMAC key 改一邊未改另一邊 → engine graceful shutdown 全停。 |
| 8 | **`bb_breakout/mod.rs:818`** | FIX-26-DEADLOCK-1 / 原則 #11 / first-detection deadlock pattern | 2026-04-24 squeeze_detected_ms 過期 auto-clear fix；6h cron 監控 | **高** — `project_first_detection_deadlock_pattern.md` 警告其他策略可能有同 pattern：`is_none()` guard + 無過期 auto-clear → symbol 永久 dormant | 其他 4 strategy（ma/bb_reversion/grid/funding_arb）若有同 deadlock pattern，Live 階段某 symbol 在某條件下永遠不再觸發信號（如 fix 前 2026-04-24 之前的 bb_breakout）。 |
| 9 | **`paper_state/fill_engine.rs:505`** | MICRO-PROFIT-FIX-1 / FIX-03 fast_track ReduceToHalf / B-1 Phase 2 反轉 best_price reset / 原則 #5 | 各 fix 已 land；bit-exact 重構約束 | **高** — 約束強，未來改動風險高；Session 1 自承 | 任一未來 fill_engine 改動破 bit-exact → MICRO-PROFIT 鎖利語意漂移（memory `feedback_micro_profit_fix_intent.md`「有微利就套」）→ Live 階段 PnL 攝動。 |
| 10 | **`bybit_private_ws_status_writer.rs:604`** + **`readonly_observer_pipeline/bybit_build_ws_runtime_facts.py`** | WS-RETIRE-1 | 2026-04-23 完成；取代 Python 340 行 listener | **中** — Python observer 假設 Rust writer 永遠寫；若 status_writer task panic，Python 讀 stale 檔卻無告警 | observer 通過 healthcheck 但實際 4 topics（order/execution/position/wallet）已下線 → Live 階段 Rust 收不到 fill 但 GUI 顯示一切正常。 |

---

#### 6. 邊界熱點 Top 10

**標準**：Rust ↔ Python IPC、系統 ↔ Bybit API、系統 ↔ DB。從 Session 3 資料流提取所有「↕ IPC edge」、「寫 DB」、「呼叫 Bybit API」的點。

| 排名 | 邊界類型 | 位置 | 資料流向 | fail-closed 策略 | 最壞情況 |
|---|---|---|---|---|---|
| 1 | **Bybit REST**（系統→Bybit） | [bybit_rest_client.rs:1725](srv/rust/openclaw_engine/src/bybit_rest_client.rs) + [order_manager.rs:1554](srv/rust/openclaw_engine/src/order_manager.rs) | Rust 寫 → Bybit `/v5/order/create` | retCode != 0 → 不重試 Err；DISPATCH-RETRY-1 OPEN 3 次 / CLOSE 2 次指數 backoff | rate limit 被達 → Bybit 拒簽 → 全策略下單失敗；Live 階段網路抖動 + 重試窗口設置錯 → orphan position。 |
| 2 | **Bybit Public WS**（Bybit→系統） | [ws_client.rs:1136](srv/rust/openclaw_engine/src/ws_client.rs) | Bybit → Rust mpsc PriceEvent | 27 unwrap! 在 parse path；指數退避重連 | 某種新的 frame 格式 → unwrap panic → 整個 ws_client task crash → engine watchdog 觸發；Live 階段斷線最壞 60s（reconnect backoff）。 |
| 3 | **Bybit Private WS**（Bybit→系統，HMAC auth） | [bybit_private_ws.rs:1013](srv/rust/openclaw_engine/src/bybit_private_ws.rs) | Bybit → Rust mpsc PrivateWsEvent（execution / order / position / wallet） | HMAC 失敗 → graceful close + reconnect | Demo/LiveDemo `execution`，Mainnet `execution.fast`（~50ms 延遲）；某次 Bybit 改字段順序 → parser 失敗 → fill 漏收 → 30s reconciler poll 才偵測。 |
| 4 | **Rust→Python IPC（length-prefix JSON-RPC）** | [ai_service_client.rs:364](srv/rust/openclaw_engine/src/ai_service_client.rs) ↔ [ai_service.py:1258](srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/ai_service.py) | Rust → Python AI handler（5 method） | 100ms connect + 5–15s method TTL；fail-closed 不阻塞引擎 | strategist_evaluate IPC 斷 5min → 無自動 tune；不影響 hot path 但 strategist scheduler 5min 自動參數變更（[strategist_scheduler/mod.rs:1166](srv/rust/openclaw_engine/src/strategist_scheduler/mod.rs)）暫停。 |
| 5 | **Python→Rust IPC（newline-delimited JSON-RPC）** | [ipc_client.py:818](srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/ipc_client.py) ↔ [ipc_server/mod.rs:1192](srv/rust/openclaw_engine/src/ipc_server/mod.rs) | Python GUI/route → Rust 21 寫 method + 多讀 method | 連續 3 失敗→ai_available=false（無自動恢復）；HMAC `__auth` 握手 | Engine 重啟時 GUI 顯示「IPC 不可用」直到 uvicorn 重啟（Session 2 footer #4）；Operator 緊急修參時 5–10s 無回應。 |
| 6 | **HMAC `authorization.json`（檔案 IPC，雙端 HMAC）** | [live_trust_routes.py:160](srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/live_trust_routes.py) 寫 / [live_authorization.rs:329](srv/rust/openclaw_engine/src/live_authorization.rs) 讀 + 5s watcher | Python 簽 → 檔 → Rust 5s 輪詢驗證 | HMAC 失敗 / Expired / EnvNotAllowed / VersionMismatch / FileMissing 任一 → engine graceful shutdown | HMAC env var `OPENCLAW_IPC_SECRET` 漂移（ops 改一邊未改另一邊）→ 全 Live 拆；Mainnet/LiveDemo 切換時 env_allowed 必須包含 active label。 |
| 7 | **`settings/edge_estimates.json`（檔案 IPC，無熱重載）** | [edge_estimator_scheduler.py:716](srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/edge_estimator_scheduler.py) 每小時寫 / [edge_estimates.rs:387](srv/rust/openclaw_engine/src/edge_estimates.rs) **startup-only** | Python 寫 → 檔 → Rust 啟動時讀一次 | 缺檔 → 空 HashMap → cost_gate ATR×conf×0.2 fallback | scheduler 寫了新檔，engine 持續用舊 HashMap → restart_all.sh `--rebuild` 才生效；scheduler 4d stall + restart 同步問題。 |
| 8 | **PG `trading.fills` + `trading.intents` + `trading.risk_verdicts`** | [trading_writer.rs:728](srv/rust/openclaw_engine/src/database/trading_writer.rs) 寫 7 trading.* 表 | Rust → PG | 3 連續 PG 失敗 → JSONL fallback；NaN sanitization 共用 | 某次新加欄位漏 INSERT 接線（如歷史 5e2981d）→ engine_mode 100% 'paper' 重現；Live 階段 ML 訓練資料一直只看到 paper engine。 |
| 9 | **PG `learning.decision_features` + `learning.decision_outcomes`** | [decision_feature_writer.rs:231](srv/rust/openclaw_engine/src/database/decision_feature_writer.rs) + [outcome_backfiller.rs:276](srv/rust/openclaw_engine/src/database/outcome_backfiller.rs) | Rust 寫 PG（PK=context_id）+ 5min 輪詢回填 | ON CONFLICT DO NOTHING（idempotent）；fail-soft log warn | timeframe `'1' vs '1m'` 歷史 bug（已修）— 同類字串格式 mismatch 在新加 timeframe 時可能重現；outcome 100% NULL 重複。 |
| 10 | **PG `governance.change_audit`（推測，未驗）** + V014 audit row | [change_audit_log.py:160](srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/change_audit_log.py) (Python 0 INSERT) + [handlers/risk.rs:563](srv/rust/openclaw_engine/src/event_consumer/handlers/risk.rs) + [handlers/governance.rs:293](srv/rust/openclaw_engine/src/event_consumer/handlers/governance.rs) | Rust 寫 V014 audit；Python agent 路徑只 in-memory + JSONL | Rust 端 fail-closed；Python 端 fail-open silent skip | Python agent 事件 audit chain 在 PG 缺席（治理盲區 §3.A）；重啟丟記憶體；JSONL 滾出後也丟。 |

---

### 特別任務

#### 交集 A：熱點 × 低理解度（待 operator 填）

由於 operator 尚未填理解度欄位，本節先產出模板。從六類熱點去重合併 → Top 20 高頻出現項：

> **Top 20 熱點模組**（六類熱點重複出現 ≥2 類即列入）：
>
> 1. **`main.rs`** — 出現於熱點類別 [1, 4]
>    operator 理解度：__（待填）
> 2. **`bybit_rest_client.rs`** — 出現於熱點類別 [1, 6]
>    operator 理解度：__
> 3. **`order_manager.rs`** — 出現於熱點類別 [1, 6]
>    operator 理解度：__
> 4. **`ipc_server/mod.rs`** — 出現於熱點類別 [1, 6]
>    operator 理解度：__
> 5. **`intent_processor/mod.rs` + `step_4_5_dispatch.rs:935`** — 出現於熱點類別 [1, 2]
>    operator 理解度：__
> 6. **`event_consumer/dispatch.rs`** — 出現於熱點類別 [1, 4]
>    operator 理解度：__
> 7. **`tick_pipeline/mod.rs` + `on_tick.rs`** — 出現於熱點類別 [1, 4]
>    operator 理解度：__
> 8. **`tick_pipeline/on_tick/helpers.rs`** — 出現於熱點類別 [1] (1182 行)
>    operator 理解度：__
> 9. **`passive_wait_healthcheck.py`（1822 行）** — 出現於熱點類別 [1, 3]
>    operator 理解度：__
> 10. **`live_session_routes.py`（1449 行）** — 出現於熱點類別 [1, 4]
>     operator 理解度：__
> 11. **`RiskConfig + ConfigStore ArcSwap`** — 出現於熱點類別 [2]（**6 條原則樞紐**）
>     operator 理解度：__
> 12. **`change_audit_log.py + audit_persistence.py`（無 PG）** — 出現於熱點類別 [3, 6, 5]
>     operator 理解度：__
> 13. **`edge_estimates.rs` + `edge_estimator_scheduler.py`（startup-only）** — 出現於熱點類別 [3, 5, 6]（最高頻 — 三類都出現）
>     operator 理解度：__
> 14. **`engine_maintenance.flag` CREATE 點未找到** — 出現於熱點類別 [3]
>     operator 理解度：__
> 15. **`ExecutorAgent shadow hardcoded`（executor_agent.py:482 + strategy_wiring.py:467）** — 出現於熱點類別 [5]
>     operator 理解度：__
> 16. **`PostOnly toml inversion`（strategy_params_{demo,live}.toml）** — 出現於熱點類別 [5]
>     operator 理解度：__
> 17. **`fast_track.rs`** — 出現於熱點類別 [5]
>     operator 理解度：__
> 18. **`live_authorization.rs + live_auth_watcher.rs`** — 出現於熱點類別 [5, 6]
>     operator 理解度：__
> 19. **`governance_hub.py`（mixin 拆分）** — 出現於熱點類別 [2, 4]
>     operator 理解度：__
> 20. **`paper_trading_routes.py`** — 出現於熱點類別 [4]（30d commit=67，最高頻代碼）
>     operator 理解度：__

operator 填完後，理解度 ≤ 1 的條目自動成為「沉默 + 不熟」雙重風險區，建議優先補 RCA 文件或 mob session 共讀。

---

#### 交集 B：熱點 × 治理 gap

從 Session 4 找出「有 gap」的根原則對應模組，檢查是否同時出現在本次熱點清單。

| Session 4 識別的 Gap 模組 | 同時出現在熱點 # | 上 live 前優先 |
|---|---|---|
| **`executor_agent.py:482`（原則 #3 + #15 嚴重 gap）** | [5] 歷史熱點 #2 | **是** — Wave 2 重構未啟動，Live 階段 lease 鏈缺席 |
| **`strategy_params_{demo,live}.toml` PostOnly 反向（原則 #6）** | [5] 歷史熱點 #3 | **是** — G1-05 未驗 ship；TOML 直編輯無 audit |
| **`edge_estimates.rs` startup-only（原則 #6 + #7 + #12 嚴重 gap）** | [3, 5, 6] **三類熱點** | **是** — 三類熱點同時命中 |
| **`change_audit_log.py` 無 PG（原則 #8 + #15 嚴重 gap）** | [3, 6, 5] | **是** — 治理盲區 §3.A，Live 階段 audit chain 在 Python 平面斷 |
| **`fast_track.rs` Guardian 旁路（原則 #4）** | [5] 歷史熱點 #4 | **是** — FA-PHANTOM-1 設計風險仍在 |
| **`RiskConfig` 6 原則樞紐（meta-gap top 1）** | [2] 耦合熱點 #1 | **是** — 任何 TOML 直編輯仍可繞過 V014 audit |
| **`live_authorization.rs` + `live_auth_watcher.rs`（原則 #2/#3/#5/#11）** | [5] 歷史熱點 #7 + [6] 邊界熱點 #6 | **是** — drawdown 從未真實 live 觸發過，HMAC key 漂移風險 |
| **`step_4_5_dispatch.rs:935` + `intent_processor:1100`（原則 #1/#4/#6/#8/#13）** | [1] 複雜度 #7 + [2] 耦合 #8 | **中** — NLL 鎖定為設計強約束，但下次 borrow checker 放寬時須警惕 |

**交集結論**：Session 4 嚴重 gap 的 6 個對應模組（#3 ExecutorAgent / #6 PostOnly / #6+#7+#12 edge_estimates / #8 change_audit_log / #4 fast_track / 樞紐 RiskConfig）**全部**同時是本 session 風險熱點 — 治理 gap 與代碼複雜度/沉默/邊界熱點高度重合。**這驗證 Session 4 識別的 gap 不是紙面分析，是實質風險集中區。**

---

### 上 live 前的紅色清單 Top 5

**排序原則**：「如果不處理就上 live 會怎樣」，不基於「容易處理」。重 Live 階段直接後果（資金安全 / 治理鏡頭 / 監控失靈）。

#### 紅色 #1：ExecutorAgent shadow hardcoded（治理鏡頭破洞）

**風險描述**：Python 5-Agent 框架 ExecutorAgent `_shadow_mode=True` 寫死，永遠寫 audit log 不發 IPC `submit_order`。Operator 看 audit 以為 agent 在工作，實際下單路徑 = Rust hot path 完全繞過 Lease 機制。

**涉及**：
- 模組：[executor_agent.py:482](srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/executor_agent.py:482) + [strategy_wiring.py:467](srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/strategy_wiring.py:467)
- 資料流：流 7（Agent audit）+ 流 1（tick → order）
- 原則：#3 AI ≠ 即時命令、#15 多 Agent 協作

**建議處理方式**（修代碼）：
- 啟動 G3-02 Wave 2 重構（CLAUDE.md §三 已標目標）
- 設計 ExecutorAgent shadow→live 切換的 lease enforcement chain
- IPC `submit_order` 必須經 SM-02 lease，與 Rust hot path lease-id 雙寫對賬

**估計工作量**：8–12 人日（含設計、實作、雙端契約測試、Lease byte-identical 驗證）

---

#### 紅色 #2：edge_estimates.json startup-only 熱重載

**風險描述**：scheduler 4d stall 已驗為治理事件（G1-01）；即使 scheduler 修復，engine 不重啟就用舊 1-cell HashMap。Live 階段 stale `edge_estimates.json` → cost_gate fallback ATR×conf×0.2 → 全策略持續低 edge 但無告警 → 學習鏈完全斷。

**涉及**：
- 模組：[edge_estimates.rs:387](srv/rust/openclaw_engine/src/edge_estimates.rs) + [edge_estimator_scheduler.py:716](srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/edge_estimator_scheduler.py)
- 資料流：流 5（Learning → cost_gate）
- 原則：#6 失敗默認收縮、#7 學習 ≠ 改寫 Live、#12 持續進化（**三原則同時觸碰**）

**建議處理方式**（修代碼 + 加 IPC）：
- `edge_estimates.rs` 加 IPC `reload_edge_estimates` method（類似 EDGE-DIAG-1-FUP-IPC 加 7 個 `exit.*` 欄位的模式）
- Python scheduler 寫完 atomic rename 後立即透過 IPC 通知 Rust 熱重載
- ETT < 60s（rollback 對齊 §六 invariant）

**估計工作量**：3–5 人日（IPC handler 加掛 + scheduler 觸發接線 + 雙端整合測試）

---

#### 紅色 #3：Python agent audit 無 PG 持久化

**風險描述**：`change_audit_log.py` + `audit_persistence.py` 全文 0 個 `INSERT INTO`（grep 驗）。所有 5-Agent decision/state event 只在 in-memory list + JSONL；重啟丟記憶體 list；JSONL 滾出後 audit 也丟。原則 #8「每筆交易必須可重建」在 Python agent 路徑根本不滿足。

**涉及**：
- 模組：[change_audit_log.py:160](srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/change_audit_log.py) + [audit_persistence.py:549](srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/audit_persistence.py)
- 資料流：流 7（Agent audit）+ 流 4（Guardian 風控）
- 原則：#8 交易可解釋、#15 多 Agent 協作

**建議處理方式**（修代碼 + 補 PG schema）：
- 新增 V025 migration：`governance.agent_audit_log` 表（同 V014 schema 模式，含 reasons JSON）
- `change_audit_log.record_change()` 內加 PG INSERT + JSONL 雙寫（兩端冗餘 + 失敗 fallback）
- 前提：先 grep 確認到底有沒有「另一檔讀 in-memory list 寫 PG」的 audit consumer（Session 4 §1 自承未驗）

**估計工作量**：4–6 人日（含 schema 設計、雙端寫入、healthcheck 加入「audit row 24h count > 0」驗證）

---

#### 紅色 #4：PostOnly TOML 反向 + RiskConfig 樞紐多原則風險

**風險描述**：`strategy_params_demo.toml` PostOnly=false / `_live.toml` PostOnly=true — **demo 不收縮、live 偏激進**，違反「失敗默認收縮」字面意。RiskConfig 為 6 條原則共用樞紐，TOML 直編輯無 V014 audit；任一配置反向 silently 失守多原則。

**涉及**：
- 模組：`strategy_params_{paper,demo,live}.toml` + [risk_config.rs:908](srv/rust/openclaw_engine/src/config/risk_config.rs) + [config/store.rs:837](srv/rust/openclaw_engine/src/config/store.rs)
- 資料流：流 1+4（cost_gate + Guardian 共用 RiskConfig）
- 原則：#6 失敗默認收縮（直接違反）+ #2/#4/#5/#11/#16（樞紐間接觸碰）

**建議處理方式**（修配置 + 加治理檢查）：
- 立即修 PostOnly：demo=true / live=false（CLAUDE.md §三 G1-05 立即修目標）
- ConfigStore.patch() 後加 invariant 自動檢查 hook（純記憶體計算 < 1ms）
- TOML 直編輯路徑加 git pre-commit hook：對 `strategy_params_*.toml` / `risk_config.toml` 啟用 invariant linter
- CLAUDE.md §三 加「多原則樞紐改動需 PA + FA + PM 三角 review」實施準則（Session 4 已建議）

**估計工作量**：1–2 人日修 PostOnly + 3–4 人日加 invariant linter & pre-commit hook = 4–6 人日

---

#### 紅色 #5：fast_track.rs Guardian 旁路設計風險（FA-PHANTOM-1 復發風險）

**風險描述**：fast_track 是設計性 Guardian 旁路（緊急閃崩/保證金時不經 Guardian veto 直接全平）。memory `project_fa_phantom_bug.md` 記錄「90% 閾值＜100% 設計上限」歷史 bug，root cause 是把 notional/balance 當 margin_util。雖已修，但設計風險仍在 — 未來新增閃崩規則仍可能誤觸全平所有策略。

**涉及**：
- 模組：[fast_track.rs:407](srv/rust/openclaw_engine/src/fast_track.rs)
- 資料流：流 1（tick → order，Step 0 fast_track）
- 原則：#4 策略不能繞過風控、#5 生存 > 利潤

**建議處理方式**（補 audit + 加防呆）：
- fast_track 觸發次數加獨立 metric（推測在 healthcheck 但 Session 4 §B.5 未直接確認）
- fast_track 內加 sanity check：「margin_util 實際值在 0–1 範圍才視為 valid」（防 notional/balance 誤代）
- 增加雙閾值規則：fast_track 單次最大平倉 ratio 上限（如 50%），ratio 超出時退回 Guardian 路徑

**估計工作量**：2–3 人日（含 metric 加入、sanity check 邏輯、單元測試）

---

#### 紅色清單 Top 5 工作量總計

| 紅色 # | 風險主題 | 工作量（人日） |
|---|---|---|
| 1 | ExecutorAgent shadow hardcoded | 8–12 |
| 2 | edge_estimates startup-only 熱重載 | 3–5 |
| 3 | Python agent audit 無 PG | 4–6 |
| 4 | PostOnly 反向 + RiskConfig 樞紐 | 4–6 |
| 5 | fast_track Guardian 旁路防呆 | 2–3 |
| **總計** | — | **21–32 人日** |

**並行性分析**：5 項中 #1 與 #4 高度耦合（Lease enforcement 與 RiskConfig invariant 都涉及樞紐），建議串行；其餘 3 項（#2 / #3 / #5）可並行。最佳順序：**#4（1d 修 PostOnly 立即可上）→ #5（防呆獨立）→ #2（IPC 熱重載）→ #3（PG audit）→ #1（最大重構）**。

理性 Live 上線時間估算：1 個工程師 21–32 人日 = 5–7 週；2 工程師並行 = 3–4 週。

---

#### 尾注：本次盤點的不可忽略觀察

1. **Session 4 的 gap 模組與 Session 5 的熱點高度重合**（交集 B 結論）— 證明治理 gap 不是紙面分析，是實質風險集中區。
2. **6 類熱點中，「歷史」與「邊界」是最對齊已知 P0/P1 的兩類**；「沉默」是最反映「我們不知道我們不知道」的一類，**operator 應優先填這 10 個沉默熱點的理解度**。
3. **`edge_estimates.json` startup-only 是唯一在三類熱點同時命中的條目**（沉默 + 歷史 + 邊界），在 16 條原則中觸碰最多原則（#6+#7+#12）。**這是 Live 上線前優先級最高的單點修復**。
4. **新鮮熱點 Top 10 與紅色清單 Top 5 重合度低** — 30 天內最頻繁改動的代碼**不是**紅色清單；意味 operator 與 sub-agent 已經在處理「正常工作量」，但 Live 風險（紅色 5）需要刻意 carve out 時間。


---

## 附錄 A — 各 Session 摘要原文

> 各 Session 完成後產出的摘要，記錄當次最不確定的 5 件事 + 給下一 Session 的 hint，作為盤點過程的「meta-record」。

### A.1 Session 1/5 摘要 — Rust 模組盤點

#### Session 1/5 Summary — Rust 模組盤點

##### 任務摘要

- Operator 意圖：產出 Rust 模組理解度地圖（非架構文檔），Session 1/5。
- 完成狀態：✅ 已產出 [inventory_1a_rust_modules.md](.claude_reports/inventory_1a_rust_modules.md)。

##### 已掃描模組總數 vs 估計

- **實際產出行數**：~205 行表格（7 + 33 + 14 + 38 + 37 + 40 + ~40）
- **原估計**：80-150 行
- **超出原因**：openclaw_engine 檔案比預想多（44 pub mod + 各 subdir）；為遵守「具體>籠統」原則未合併中等大小檔案；test 檔案已盡量合併為 1 行/子模組。
- **涵蓋**：`srv/rust/` 下 3 crate × ~180 `.rs` 檔案（含 test），共 131,120 LOC。

##### 未掃描部分清單

- **完全未讀**：以下檔案僅從檔名、mod.rs 聲明推斷，沒讀檔頂 MODULE_NOTE：
  - `openclaw_engine/src/common/{bybit_signer,ws_backoff}.rs` 僅讀前 10 行
  - `openclaw_engine/src/linucb/arms_v1_15.rs` (57 行)、`linucb/schema_hash.rs` (50 行) — 檔頂未讀
  - `openclaw_engine/src/news/types.rs` (47 行) — 檔頂未讀
  - 所有 `tests/` 目錄（`openclaw_engine/tests/*.rs`）— integration tests 未列入
  - `openclaw_engine/src/common/bybit_signer.rs` / `ws_backoff.rs` test 章節未讀
- **不完整讀**：大型檔案（>500 行）我只讀檔頂 25-60 行的 MODULE_NOTE + imports，未讀實作與 match arm 細節。職責欄準確度 85%，核心設計決策欄因此偏向「宣告性」而非「實質」。
- **整合測試與 Cargo feature**：`Cargo.toml` 中 `edge_predictor_ort` feature、`#[cfg(test)]`、dev-dependencies 只做表層理解。
- **Python 側**：本 session 不含（Session 2 任務）。

##### 本次盤點中最不確定的 5 件事

1. **openclaw_engine/src/main.rs (2062 行) 與 `startup/` 的實際分工比例**
   - 我只讀了 main.rs 前 40 行，看到它 import `startup::*` 並啟動 tokio runtime。但 2062 行的 main.rs 仍含大量邏輯；startup (1126 行) 另外有一堆 helper。兩者在「誰擁有 config 載入」「誰 spawn 什麼任務」上的邊界我沒畫清楚。職責欄「tokio runtime + SIGHUP/SIGTERM + 引導」可能低估了 main.rs 的實際職責。

2. **`intent_processor/mod.rs` (1100 行) vs `tick_pipeline` Step 4+5 之間的邊界**
   - IntentProcessor 被 TickPipeline 持有，但實際「誰呼叫誰」的方向與頻率我沒實際追蹤 call graph。Step 4+5 dispatch 說 IntentProcessor 在迴圈內被呼叫 N 次/tick/strategy，這與 IntentProcessor 的 lifetime（Arc? owned?）耦合度不明。`process_with_features` 的實際 caller 集合我沒驗證。

3. **`event_consumer/bootstrap.rs` 的 27 interdependent bindings 具體是哪些**
   - 檔頂說 `triage_cmd_tx @~142 line 被 ~329 line 使用` 等。我只看了 20 行檔頂，沒追那 27 個 binding 的實際依賴圖。「一個大 fn 避免參數爆炸」是宣告，但真實的耦合點（例如：是否有可拆的子群）需看 847 行實作才能判斷。

4. **`strategies/funding_arb.rs` (982 行) 當前是否還是 dead code**
   - memory 說 G-2 2026-04-18 結案 NEGATIVE、demo funding_arb.active=false，但 Rust 模組 982 行 Strategy trait impl 仍在 `strategies::registry::StrategyFactory::create_all()` 中，還是已被 `#[allow(dead_code)]` 註解或 registry 篩掉？我沒讀 registry.rs 實作，職責欄寫「directional funding rate capture」可能讓 operator 誤以為還活著。

5. **CLAUDE.md §三宣稱的「engine lib 1980 passed / Part A 1905」與實際 cargo test 跑得通的對應關係**
   - 我的理解度完全基於靜態閱讀；我沒跑 `cargo test`，沒驗 `#[cfg(test)]` 實際通過率。若 CLAUDE.md 過期（G6-04 §三 drift 規則警告），某些檔案的測試可能實際 0 assertions 或 `#[ignore]`。「測試檔行數 = 測試覆蓋」是錯誤假設。

##### 建議 Session 2（Python 盤點）需特別留意的對應關係

1. **Rust↔Python IPC 契約的對應**
   - Rust: `ipc_server/mod.rs` (1192 行) + 7 domain handlers 暴露 JSON-RPC 方法
   - Python 應有 `IpcClient` / `PipelineIpcClient` 類讀相同 method names
   - **核對**：每個 `ipc_server/handlers/*.rs` 的 public method 名稱 vs Python 端是否一對一；有沒有 Python 呼叫了 Rust 不存在的 method（dead call）

2. **Config 權威 vs Python 讀取面**
   - Rust: `config/risk_config.rs` + `budget_config.rs` + `learning_config.rs` 為權威
   - Python 應為**只讀**（CLAUDE.md 原則 #2 讀寫分離）
   - **核對**：Python 端是否有 `risk_config` 寫入路徑（應全部透過 `ipc_server::handlers::risk::handle_update_risk_config` 等 patch_*_config）

3. **authorization.json 雙端契約**
   - Rust: `live_authorization.rs` + `live_auth_watcher.rs` 讀 + 驗 HMAC
   - Python: EarnedTrust engine 寫 `_write_signed_live_authorization()`
   - **核對**：HMAC key 來源、簽名欄位、expiry 格式兩端一致性

4. **Teacher + Layer 2 的 LLM 路徑**
   - Rust: `claude_teacher/client.rs` 透過 Anthropic reqwest；無 API key→fail-closed
   - Python: memory 說 Layer 2 走 `local_llm_factory.get_local_llm_client()`（Ollama 或 LM Studio）+ `ai_service_client.rs` IPC (Unix socket)
   - **核對**：Python AIService 是否 proxy Anthropic 到 Rust？還是 Rust teacher 直連？API key 實際注入點在哪

5. **H0 → H1-H5 治理層的真假**
   - Rust: `core::h0_gate` + `core::governance_core` + `core::sm/*` 全部實作
   - Python: CLAUDE.md 2026-04-23 更正：H1-H5 middleware `h1_thought_gate.py` (185) / `model_router.py` (292) / `h4_validator.py` (103) 全實作；5-Agent ~4552 行 live
   - **核對**：Python H1-H5 哪些與 Rust 重複？哪些真的 live 被調用？有沒有 dead module

6. **策略參數 TOML 雙端**
   - Rust: `strategies/strategy_params.rs` + `params.rs` 載 `strategy_params_{paper,demo,live}.toml`
   - Python: 應有 GUI 可讀可 patch（透過 IPC）
   - **核對**：`PostOnly 配置 demo=false/live=true 反向`這類 memory 警告涉及的 TOML 值源位置

7. **Scanner 取代 Python 的影響範圍**
   - Rust: `scanner/runner.rs` 每 30min 取代 Python market_scanner.py
   - **核對**：Python `market_scanner.py` 現在是 stub / dead / 保留？有無 dual-write 風險

8. **decision_outcomes 回填鏈**
   - Rust: `database/outcome_backfiller.rs` 每 5min 回填
   - Python: memory `project_decision_outcomes_not_dead.md` 提到 writer 活躍但 engine_mode 100% 'paper' 過 INSERT bug（2026-04-21 `5e2981d` fix）
   - **核對**：Python 端還有沒有競爭的 backfiller / 讀取 engine_mode 的下游

9. **main_legacy.py 的 468 行 singleton 與 Rust 配對**
   - CLAUDE.md 說 `main_legacy.py` 僅 468 行純基礎設施（singleton+helpers+middleware+register_* 聚合）；下游 28 檔 `_base.xxx()` 動態查找為 monkey-patch + 3 個 `importlib.reload(main_legacy)` 測試契約
   - **核對**：這 28 檔哪些實際與 Rust 模組做過資料往來

##### 建議 Session 3+ 需要注意的 Rust-side 未解

- `main.rs` 2062 行 是否有拆分計畫（§九 硬上限 1200 明顯超）
- `instrument_info.rs` 1975 行、`bybit_rest_client.rs` 1725 行、`order_manager.rs` 1554 行 都超硬上限，常數表/配置多但未驗
- `ipc_server/mod.rs` 1192 行剛好爆硬上限，應拆
- `strategies/bb_reversion.rs` 1143 行、`strategist_scheduler/mod.rs` 1166 行、`tick_pipeline/on_tick/helpers.rs` 1182 行 都接近或超限
- 上述大檔規範違反未列在 CLAUDE.md §三 作為已知 debt，是否為靜默狀態需 operator 確認

##### 交付物對照表

| 文件 | 路徑 | 行數 |
|---|---|---|
| Rust 模組清單 | [inventory_1a_rust_modules.md](.claude_reports/inventory_1a_rust_modules.md) | ~260 |
| 本摘要 | `.claude_reports/20260424_213529_inventory_session_1_summary.md` | ~130 |


### A.2 Session 2/5 摘要 — Python 模組盤點

#### Session 2/5 Summary — Python 模組盤點

##### 任務摘要

- Operator 意圖：產出 Python 模組理解度地圖（非架構文檔），Session 2/5。
- 完成狀態：✅ 已產出 [inventory_1b_python_modules.md](.claude_reports/inventory_1b_python_modules.md)（302 行 · 13 批 · ~177 個模組）。
- 策略：並行派 4 個 Explore sub-agent（batch 1~4），同時自己獨立核對 `main_legacy.py` / `strategy_wiring.py` / `risk_manager.py` / `ipc_client.py` / `ipc_dispatch.py` / `live_trust_routes.py` / `db_pool.py` / `edge_estimator_scheduler.py` 等 8 檔的檔頂或 __init__ 段，作為 agent 輸出的交叉驗證。

##### 已掃描模組總數 vs 估計

- **實際產出行數**：~177 個模組 row + 13 批 header
- **原估計**：100-180 個，實際在範圍內
- **涵蓋**：
  - `app/`：126 檔 Python 源（控制 API + 業務層），全部納入
  - `ml_training/`：25 檔，全部納入
  - `local_model_tools/`：27 檔（主 14 stub + 3 真實計算 + 10 strategies/indicators），全部納入
  - `helper_scripts/`：17 檔（canary 4 / db 7 / phase4 2 / research 1 / 根 3），納入
  - `readonly_observer_pipeline/`：10 檔，納入
  - `io_and_persistence/`：3 檔（有業務邏輯的）納入
  - `audit/counterfactual_exit_audit.py`：1 檔，列入但未讀檔內（標註未讀）
- **總 Python LOC（產品向）**：~84,600 行

##### 未掃描 / 不完整讀部分清單

###### 完全未掃描（蓄意排除）
- `tests/` 下所有 test_*.py — operator 指示另有風險熱點盤點處理
- `docs/` / `worklogs/` 下的 .py（純文檔化 snippet）
- `archive/` 下的歷史檔
- `venv*/` 的安裝套件
- `database_setup/` 與 `*scripts/` 的一次性 fix/migration shell wrapper
- `program_code/exchange_connectors/bybit_connector/misc_tools/` 下的 `*_contract_check.py` / `*_final_audit.py`（audit 合約定義，~60+ 檔）
- `program_code/ai_agents/bybit_thought_gate/` 下的 `*_contract_check.py`（~40+ 檔，絕大多數為合約定義非 runtime）
- `helper_scripts/maintenance_scripts/bybit_connector/` 的殘留 repair shell wrapper

###### 部分掃描（檔頂 + imports 讀過，未讀實作細節）
- **Batch 1~4 agent 多數檔案**：只讀 docstring/MODULE_NOTE + imports + 第一個 public class signature（~前 40-80 行）；大檔（>500 行）未追 method body；因此「核心設計決策」多為檔頂宣告，非實際驗證
- **未完整讀（標註於表中）**：
  - `io_and_persistence/bybit_load_ws_jsonl_to_postgres.py` (112 行) — 僅推測
  - `io_and_persistence/bybit_normalize_latest_snapshot_to_postgres.py` (261 行) — 僅推測
  - `audit/counterfactual_exit_audit.py` (792 行) — 僅推測
- **Batch 3 agent 對 ml_training/ 子模組部分給出估計行數**（如 `~150`），我已獨立 `wc -l` 校對並全部替換為實測值

###### 規模雖納入但「深度理解」為零的模組
- 行數 > 500 且我沒讀實作的 ~40 檔（含 `live_session_routes.py` 1449 / `ai_service.py` 1258 / `passive_wait_healthcheck.py` 1822 / `counterfactual_exit_replay.py` 1216 / 等）
- Operator 請將「理解度」欄填入實際 0-5，以這份表為起點交叉參考本 session 1 Rust 的理解度

##### 🔌 Rust ↔ Python IPC 介面總覽（Session 3 重度使用）

###### Python → Rust（client: `app/ipc_client.py` 呼 Rust `openclaw_engine/src/ipc_server/`）

協議：JSON-RPC 2.0 over Unix domain socket (`/tmp/openclaw/engine.sock`)；newline-delimited；asyncio.Lock 序列化；per-method TTL。

| Method | Python 呼叫點 | Rust handler（Session 1 對應） | 備註 |
|---|---|---|---|
| `ping` | ipc_client:257 | `ipc_server/handlers/...` (misc) | 連線健康檢查 2s timeout |
| `__auth` | ipc_client:559 / 792 | `ipc_server/mod.rs` auth hook | HMAC-SHA256 token + ts 初始握手 |
| `get_state` | ipc_client:268 | `handlers/misc.rs` state snapshot | 全域狀態快照 |
| `reload_config` | ipc_client:274 | `handlers_config.rs` | SIGHUP 等效熱重載 |
| `get_paper_state` | ipc_client:284（+paper/live/demo route 廣用） | `handlers/misc.rs` | params={engine} |
| `get_mode_snapshot` | ipc_client:292 | `handlers/misc.rs` | per-engine 快照 |
| `get_active_modes` | ipc_client:299 | — | paper/demo/live 活躍狀態 |
| `get_latest_prices` | ipc_client:306 | — | 價格快照（主要給 GUI） |
| `get_tick_stats` | ipc_client:313 | — | tick 吞吐統計 |
| `get_ai_budget_status` | ipc_client:347（ai_budget_routes）| `handlers/budget.rs` | BudgetTrackerSlot 讀 |
| `record_ai_usage` | layer2_cost_tracker:282 | `handlers/budget.rs` | Layer 2 usage fail-closed 寫 |
| `pause_paper` | ipc_client:386（各 route）| `handlers/lifecycle.rs` | engine=paper/demo/live |
| `resume_paper` | ipc_client:393（各 route）| `handlers/lifecycle.rs` | 同上 |
| `close_all_positions` | ipc_client:400（廣用）| `handlers/lifecycle.rs` | engine=paper/demo/live |
| `close_position` | paper/live/strategy_ai routes | `handlers/lifecycle.rs` | 單倉位關閉 |
| `reset_paper_state` | ipc_client:407 | `handlers/lifecycle.rs` | params={new_balance} |
| `submit_paper_order` | ipc_client:440 | `handlers/strategy.rs` | 手動下單 paper |
| `submit_order` | executor_agent:550 / 555 | `handlers/strategy.rs` | **G3-02 重構目標**：5-Agent→Rust live 橋 |
| `update_risk_config` | ipc_client:485, risk_routes | `handlers/risk.rs` patch_risk_config | 21 參數 hot-patch |
| `get_risk_config` | engine_capabilities:162, risk_routes:588, risk_view_client:175 | `handlers/risk.rs` | params={engine} |
| `get_risk_runtime_status` | ipc_client:595, risk_view_client:188 | `handlers/risk.rs` | 連虧/降級狀態 |
| `clear_consecutive_losses` | risk_view_client:353 | `handlers/risk.rs` | 重置計數 |
| `reset_drawdown_baseline` | risk_view_client:383, risk_routes | `handlers/risk.rs` | 調整 baseline（audit row）|
| `get_build_capabilities` | engine_capabilities:140 | `handlers/misc.rs` | engine build info |
| `get_scanner_status` | strategy_read:424 | `handlers/misc.rs` | Rust scanner 狀態 |
| `get_active_symbols` | strategy_read:512 | `handlers/misc.rs` | scanner universe |
| `set_system_mode` | control_ops:515 | `handlers/lifecycle.rs` | Python GUI → Rust（global trading_mode） |
| `trigger_live_auth_recheck` | live_trust_routes:297 | `handlers/governance.rs` 或類似 | 強制重新驗證 authorization.json |
| `UpdateStrategyParams` / `GetStrategyParams` / `GetParamRanges` | strategy_write_routes | `handlers/strategy_params.rs` | 5 策略參數 hot-patch |
| `get_phase4_status` | phase4_routes | `handlers/misc.rs`（Phase4 card）| 4 模組交通燈 |
| Edge predictor IPC（Shadow/Reload/DisableAll/ShadowFill/DecisionFeature）| 路由未廣掃 | `handlers/edge_predictor.rs` | 未完全驗證 Python 呼叫點 |
| Dynamic risk sizer toggle | 未廣掃 | `handlers/dynamic_risk.rs` | DYNAMIC-RISK-1 |
| Governor escalate/de-escalate + set_system_mode（governance 層）| governance_extended_routes | `handlers/governance.rs` | V014 audit row（包含被拒絕路徑）|

**Rust 側有 handler 但 Python 側未驗到 caller**（可能是新 API 尚未接線，或我漏找）：
- `governance escalate/de-escalate`（Rust handler 存在但 Python caller 未 grep 到具體 method name）
- `edge_predictor Shadow/Reload/DisableAll`（未驗證 Python 完整呼叫鏈）

**Python 側呼叫但 Rust handler 未在 Session 1 明確列出**（需 Session 3 進一步驗）：
- `get_latest_prices` / `get_tick_stats` — handler 名字與 Session 1 Rust inventory 中 `handlers/misc.rs` 的行為推測對應，未逐一比對

###### Rust → Python（client: Rust `ai_service_client.rs` 呼 Python `app/ai_service.py::AIServiceListener`）

協議：**長度前綴**（4-byte big-endian u32 header + UTF-8 JSON payload）；Unix socket `/tmp/openclaw/ai_service.sock`；multi-worker safe（僅 1 uvicorn worker 綁定，其他 passive）。

| Method | Python handler 位置 | 功能 | Rust 呼叫 timeout |
|---|---|---|---|
| `strategist_evaluate` | ai_service.py:269 `_handle_strategist` | 信號 → 是否值得下單 + edge estimate | 15s |
| `analyst_evaluate` | ai_service.py:470 `_handle_analyst` | 交易結果 → pattern discovery | 30s |
| `conductor_evaluate` | ai_service.py:535 `_handle_conductor` | agent 協調（未完全驗證） | 10s |
| `scout_evaluate` | ai_service.py:567 `_handle_scout` | 情報處理 | default 5s |
| `guardian_evaluate` | ai_service.py:665 `_handle_guardian` | 風控審查前置 | default 5s |

**觀察**：這 5 個 Rust→Python handler 是 5-Agent 目前唯一的「Rust 熱路徑能觸發 Python AI」路徑。CLAUDE.md §三「ExecutorAgent _shadow_mode=True hardcoded」意指 **反向** — Python ExecutorAgent **不能**通過 IPC 讓 Rust 執行真實 SubmitOrder，只記錄 shadow 日誌。這是 G3-02 Wave 2 的重構目標。

###### 其他 IPC / 檔案 interface
- **HMAC `authorization.json`**：Python `live_trust_routes.py::_write_signed_live_authorization()` 寫，Rust `live_authorization.rs` 讀 + 每 5min re-verify；路徑 `$OPENCLAW_SECRETS_DIR/live/authorization.json`（LIVE-GATE-BINDING-1）
- **`settings/edge_estimates.json`（+ `_live_demo.json`）**：Python `edge_estimator_scheduler.py` 每小時寫，Rust `edge_estimates.rs` 啟動時 `set_edge_estimates()` 讀一次（**無熱重載** — 改檔需 engine restart 才生效）
- **`pipeline_snapshot*.json`（per-engine）**：Rust `persistence.rs` 寫，Python `ipc_state_reader.py` 讀（TTL=2s，staleness=60s）
- **`bybit_private_ws_listener_status_latest.json`**：Rust `bybit_private_ws_status_writer.rs` 每 5s 寫，Python `readonly_observer_pipeline/bybit_build_ws_runtime_facts.py` 讀（WS-RETIRE-1 之後）
- **`runtime_snapshot.json`（外部 runtime）**：Python `runtime_bridge.py` 讀（env `OPENCLAW_RUNTIME_SNAPSHOT_FILE`），overlay 到 compile_state
- **`authorization.json` watcher**：Rust `live_auth_watcher.rs` 5s 輪詢；Python 寫完立即生效（不需通知）
- **`engine_maintenance.flag`**：shell script 建立；Python/Rust watchdog 尊重

##### Python 側最不確定的 5 件事

1. **`live_session_routes.py` (1449 行) 與 `live_trust_routes.py` (845 行) 之間誰擁有 HMAC 簽名 `authorization.json`**
   - 我讀了 live_trust_routes 前 50 行確認 LIVE-GATE-BINDING-1 落在此檔（POST `/api/v1/live/auth/renew`）；但 live_session_routes 1449 行含 14 routes 也讀/寫 authorization 流程（grep 命中 4 檔）。
   - 不確定「start session → SM-01 submit → HMAC 寫入」三步的跨檔邊界；若順序 race 可能讓 Rust 讀到部分寫入檔案。
   - Session 3（資料流）應詳追此寫入序列。

2. **`ai_service.py` (1258 行) 與 Layer 2 engine/tools/cost_tracker 的職責分工**
   - `ai_service.py` 有 5 個 Rust→Python handler（strategist/analyst/conductor/scout/guardian），Layer 2（`layer2_engine.py` 730 行 + `layer2_tools.py` 906 行 + `layer2_cost_tracker.py` 726 行）是「另一條」AI 迴圈（Claude Haiku/Sonnet/Opus）。
   - 不確定這兩條路徑是否 **互斥獨立**（H1 判斷後選一條）還是 **可以同時**（strategist→analyst 結束後觸 Layer 2 深度推理）。memory `project_layer2_agent_design.md` 說 Layer 2 是獨立 agent，但實際 trigger 路徑我沒追。
   - 若同時，那 `api_budget_manager.py`（月 API $50 cap）與 `layer2_cost_tracker.py`（日 $2 cap）是否 double-count？

3. **`strategy_wiring.py` (912 行) 實際執行時 12+ singleton 的 init 順序**
   - §九 登記的 singleton：`KLINE_MANAGER / INDICATOR_ENGINE / SIGNAL_ENGINE / ORCHESTRATOR + 5 agents + MessageBus + PipelineBridge + PaperLiveGate + ...`（總計 12+）
   - 我確認 line 468 是 `ExecutorAgent(config=ExecutorConfig())`（shadow=True default）。但 **哪些 singleton 是「純 stub」**（`local_model_tools/` 的 14 個 stub）**以及 5 agents 的實際 init order 是否有循環依賴**，我只讀了檔頂 module note，未追 import 順序與 late binding 點。
   - 如果 ScoutAgent ctor 需要 MessageBus，MessageBus 又註冊 agents，那迴圈打開點在哪？strategy_wiring 的「預期行為」不等於「實際 runtime 接線」。

4. **`passive_wait_healthcheck.py` (1822 行) 內 17+ check 的實際覆蓋範圍**
   - CLAUDE.md §三 多次引用 healthcheck `[7]` `[8]` `[9]` `[11]` `[12]` `[13]`（各 check 編號）驗證「fresh」/「 mtime <30min」等；但我沒打開看每個 check 的實際 SQL / 判定邏輯。
   - 潛在風險：17 個 check 在單檔 1822 行（§九 硬上限 1200 超 622 行），內部是否有 check 互相污染共享狀態？有沒有 check `[N]` 靜默 pass（見 QC audit 2026-04-24 對 edge_estimator_scheduler 誤判 4 天停滯的先例）？

5. **ml_training/ 25 檔中哪些是「死碼」vs「被 operator 手動 cron 觸發」vs「被 uvicorn 內部呼叫」**
   - 我讀的是檔頂 MODULE_NOTE + 第一個 class；Batch 3 agent 對 `dl3_ab_runner.py` / `weekly_report_generator.py` / `promotion_pipeline.py` 標「推測」— 這與 CLAUDE.md §三 `LEARNING-PIPELINE-DORMANT-1`（21 learning schema 表仍無 consumer）相符，但具體哪些 script 真的在 cron、哪些只存在於 `run_training_pipeline.py` 編排器內，我沒驗證。
   - 例如 `optuna_optimizer.py` 946 行，若沒有 cron 也沒被 route 觸發，等同 dead code，不應算入「live 代碼量」。

##### 意外發現 / 與 Session 1 Rust 盤點的矛盾與互補

1. **`risk_manager.py` 52 行「shim」vs Rust `position_risk_evaluator.rs` 352 行**
   - Python `risk_manager.py` 檔頂明言「原 1633 行 Python RiskManager 已被 ARCH-RC1 收編到 Rust ConfigStore + intent_processor + position_risk_evaluator。本檔僅保留兩個對外符號…禁止再加任何邏輯到本檔」。
   - 這與 Rust 盤點第 5 批的 `risk_checks.rs` (874 行) + `position_risk_evaluator.rs` (352 行) + `dynamic_risk_sizer.rs` (518 行) 配合完美 — DEAD-PY-2 實質完成。
   - **互補驗證**：CLAUDE.md §三 宣稱「Python 無交易邏輯（DEAD-PY-2 清除 ~4500 行後）」得到獨立確認。

2. **`local_model_tools/` 27 檔中 14 檔是 stub**
   - 這對應 Rust 盤點第 5+6 批的 `core::indicators/` + `core::signals/` + `strategies/` 真實實作。
   - **互補**：`strategy_wiring.py` 把 stub 塞入 12+ singleton 只為保留 import 契約（`KLINE_MANAGER` / `INDICATOR_ENGINE` / `SIGNAL_ENGINE` / `ORCHESTRATOR` 等），但這些 singleton 在 runtime 實際被 Rust 接管。Session 3 應畫清「Python 單例誰在用」對「Rust 權威實作」的實際替代關係。

3. **Python 側 IPC method 與 Rust 側 handler 幾乎 1:1 對應**
   - 證實 CLAUDE.md 宣稱「Rust 為所有交易參數權威，Python 僅只讀」— 觀察到的 29 個 method 中 ~20 是讀路徑（get_*），寫路徑都是可逆命令（pause/resume/close/submit_order/patch_config），無 Python 寫 Rust 的「底層狀態」路徑。
   - **互補**：這份 IPC 表可作為 Session 3 資料流的主幹。

4. **`main_legacy.py` 468 行的「reload 契約」與 Rust 啟動順序有隱含相依**
   - 檔頂明言「多個測試依賴 `importlib.reload(main_legacy)` 重建 Settings」，代表 Python 測試套件對 settings + STORE 有 reload-safe 期待。
   - Rust 側沒有對應「reload singleton」的概念（Rust 只有 `ArcSwap` 熱重載單個 Config）。**潛在衝突**：如果 CI 或測試場景下 Python reload 發生在 Rust binary runtime 中，IPC client 的 `ai_available=false` 後 **是否會自動重連成功**？我的 `ipc_client.py` 讀到「連續 3 失敗→ai_available=false fallback，之後無自動恢復」 — 這可能是潛在 bug。

5. **`ai_service.py` 有 5 handler，但 Session 1 Rust 的 `ai_service_client.rs` 只列「100ms connect + 5-15s method TTL」**
   - Rust 端 `ai_service_client.rs` 只有 364 行，相對於 Python 端 1258 行的 listener（含 5 handler + AIService 主類）。**Rust 端是「瘦 client」，Python 端是「胖 listener + 業務邏輯」**。
   - 這補全了 CLAUDE.md §三「5-Agent ~4552 行 live shadow」中「代碼在 Python 但呼叫發自 Rust 熱路徑」的結構圖。

6. **`edge_estimator_scheduler.py` 有 `_LEADER_LOCK_FD` fcntl leader election**
   - §九 登記但 Rust 側沒有對應的 leader lock（Rust engine 是單進程；Python uvicorn --workers 4 才需 leader）。
   - **Session 3 注意**：若 uvicorn worker 崩潰而未釋放 fcntl lock（SIGKILL 以外），fallback 是什麼？memory `project_edge_scheduler_stalled.md` 指 2026-04-24 同日修復，代表這個 lock 機制之前沒有在 uvicorn restart 路徑上驗證過。

##### 建議 Session 3（資料流）需特別追蹤的 Python 側點

1. **Tick 事件從 Rust → Python 的唯一 AI 觸發點**：`ai_service_client.rs` 呼 `strategist_evaluate` → Python `_handle_strategist` → StrategistAgent → LLM call（Ollama/LMStudio/Anthropic）→ return edge JSON → Rust 再 gate cost → intent processor → order
2. **Python 對 Rust 的所有「寫」都是可逆命令**：pause_paper / resume_paper / close_position / submit_order / update_risk_config（patch-based），**沒有直接寫 Rust 內存狀態的路徑**
3. **Config 權威：Rust RiskConfig 為唯一來源**（risk_config.toml / patch_risk_config），Python risk_routes / risk_view_client 全走 IPC；Python 端無 in-memory override
4. **5-Agent runtime 路徑**：Rust tick → IPC → Python `ai_service.py` → 分派到 5 agent handler → agent 內呼 local_llm_factory/Ollama/Layer2 → 回傳 JSON → Rust 再判 H0/H1-H5 gate
5. **Edge 資料**：Python `edge_estimator_scheduler` 寫 `settings/edge_estimates.json` → Rust 啟動時 `set_edge_estimates()` 讀一次（無熱重載）→ Rust intent_processor 用於 cost_gate
6. **Shadow 資料**：Rust 寫 `learning.decision_shadow_fills` / `learning.decision_shadow_exits` → Python `shadow_fills_routes.py` 讀（EDGE-P3-1 7c）→ GUI 顯示
7. **Paper state**：Rust `paper_state` → `pipeline_snapshot*.json` 檔 → Python `ipc_state_reader.py` 讀（TTL 2s），或直接 IPC `get_paper_state`

##### 交付物對照表

| 文件 | 路徑 | 行數 |
|---|---|---|
| Python 模組清單 | [inventory_1b_python_modules.md](.claude_reports/inventory_1b_python_modules.md) | 302 |
| 本摘要 | `.claude_reports/20260424_221449_inventory_session_2_summary.md` | ~230 |


### A.3 Session 3/5 摘要 — 端到端資料流盤點

#### Session 3/5 Summary — 端到端資料流盤點

##### 任務摘要

- Operator 意圖：Session 3/5，產出 5–8 條端到端資料流地圖（按圖索驥追任一條流的每一步）。
- 完成狀態：✅ 已產出 [inventory_2_data_flows.md](.claude_reports/inventory_2_data_flows.md)（~840 行 / 8 必含 + 2 額外 = **10 條流**）。
- 策略：派 6 個並行 Explore sub-agent 各追一條流（agent 4 同時追 flow 4+5；agent 5 同時追 flow 6+7）+ 主會話直查 Grep 交叉驗證 5 個關鍵 file:line 點。

---

##### 已完成流數 vs 必含 8 條

| # | 流名稱 | 狀態 | 核心發現 |
|---|---|---|---|
| 1 | 市場 tick → 訂單提交 | ✅ 通 | 純 Rust 路徑；Python ExecutorAgent shadow hardcoded 導致非主路徑 |
| 2 | Bybit fill → DB 持久化 | ✅ 通 | engine_mode 來源在 `pipeline_helpers.rs:190`；exit_source V021 dormant |
| 3 | AI 推理（thought_gate→LLM→cost log）| ✅ 通 | 3 層獨立預算追蹤；H1 在 StrategistAgent 上游非 ai_service handler |
| 4 | Guardian 風控審批 | ✅ 通 | 9 checks（非 15+，原描述偏高）；DB 表 `trading.risk_verdicts` |
| 5 | Learning → edge_estimates → cost_gate | ⚠️ **斷鏈於 7（無 IPC hot reload）** | edge_estimates.json 改檔需 engine restart 才生效 |
| 6 | Operator 授權 → live spawn | ✅ 通 | 5s 輪詢 file（不是 5min file poll，5min 是 lease 層） |
| 7 | 5-Agent 事件 → change_audit_log | ⚠️ **DB 表名未確認** | grep 無 `INSERT INTO governance.change_audit` 命中 |
| 8 | Crash → watchdog → restart | ⚠️ **systemd unit 缺**、**maintenance flag CREATE 點未找到** | 但 DNS classify 邏輯確實存在 |
| 9 | Scanner 30min cycle（額外）| ✅ 簡述 | 取代 Python market_scanner.py |
| 10 | News pipeline（額外）| ✅ 簡述 | Guardian halt 共享 Arc<AtomicBool> 與 Teacher |

**達成**：8 必含 + 2 額外，全部都到「步驟編號 + file:line + 持久化點 + 斷鏈點」級別。其中 Flow 5/7/8 標明確切斷鏈或 unconfirmed 點。

---

##### 本次盤點中最不確定的 5 件事

1. **`step_4_5_dispatch.rs` 內 IntentProcessor 呼叫位置未直接 Grep 驗證**
   - sub-agent 1 報告「step_4_5_dispatch 935 行 NLL borrow checker 鎖定」，沒有直接呼出 `intent_processor.process_with_features` 的 line number。我也沒看 935 行實作。
   - 含義：「Step 4+5 收集 intent → IntentProcessor」是業界常識性的拼湊，但具體呼叫頻率（每 strategy / 每 signal / 條件分支）我沒實際追到。
   - 風險：若這條呼叫路徑有 bug（例如未呼叫 IntentProcessor 直接寫 paper_state），整個風控鏈可能繞過。

2. **Flow 2 的 ExecutionListener callback 註冊位置**
   - sub-agent 2 明說「Cannot trace exact file:line without knowing callback registration site」。`event_consumer/bootstrap.rs` 847 行有 27 binding，callback 註冊應在其中之一。
   - 含義：fill 從 WS event 變成 PaperState 變動的 plumbing 我沒驗證；如果某次 refactor 漏掉 callback 注入，會造成 Bybit fill 但 Rust 不知道。
   - 風險：對賬 reconciler 30s 輪詢會發現 drift，但會延遲 30s。

3. **`change_audit_log.py` 真實有沒有寫 DB？**
   - sub-agent 5 + 我都沒在 source 找到 `INSERT INTO` SQL 字串。`record_change()` 只 append 到 `_changes` list + JSONL 磁碟備份。
   - 含義：「audit 寫 PG `governance.change_audit`」可能是錯誤假設；實際 audit 可能只在記憶體 + JSONL 檔案。
   - 風險：如果只在 in-memory + JSONL，重啟後會丟記憶體部分；JSONL 滾出後 audit 也沒了。Operator 可能對「audit 永久保存」有錯期待。

4. **engine_maintenance.flag 由誰 CREATE**
   - sub-agent 6 + 我都沒在 restart_all.sh 或 watchdog 找到 `touch engine_maintenance.flag` 或 `> engine_maintenance.flag` 的命令。CLAUDE.md §六 line 196 只說「上次異常留下會阻塞 watchdog → 開工前先 `rm -f`」。
   - 含義：可能是 operator 手動 touch，或某個我沒查到的 deploy script，或 systemd unit。
   - 風險：如果 deploy 流程依賴「flag 自動建立 → 阻塞 watchdog → 升級完 rm」這個 invariant，但 CREATE 點實際不存在，watchdog 可能在 deploy 中誤啟動 restart。

5. **5-Agent wiring 是否對全 5 個 agent 都注入 audit_callback**
   - 我只直接驗了 ExecutorAgent line 482 + strategy_wiring line 467-468。其他 4 個 agent（Strategist / Guardian / Analyst / Scout）的 wiring 注入點沒 grep。memory `feedback_workflow_audit_chain.md` 暗示 E5-FN-3 wired some agent audit but NOT all。
   - 含義：可能 ScoutAgent 或 AnalystAgent 的 _audit() 永遠 silent skip（fail-open），audit 鏈缺角。
   - 風險：operator 看 audit log 看不到某個 agent 的事件，誤以為「沒事」。

---

##### 追路過程中發現的、不在必含清單但值得關注的第 9、10 條流

###### 流 9：Scanner 30min cycle → 動態 symbol universe

**為何值得列**：scanner cycle 是 tick 流的「上游選股」決策點。CLAUDE.md §三 沒列 P0/P1 但若 [scanner/scorer.rs:1-901](srv/rust/openclaw_engine/src/scanner/scorer.rs) 4 個 fitness fn（F_ma / F_grid / F_bbrv / F_bkout）失靈（例如 edge bonus 用 stale `edge_estimates.json`，由 Flow 5 斷鏈影響）→ 整個策略池會選錯 symbol → 持續低 edge。

**斷鏈影響**：scorer 引用 `edge_estimates`（[scanner/scorer.rs](srv/rust/openclaw_engine/src/scanner/scorer.rs) 第 1 批盤點欄）→ Flow 5 dormant 期間 scanner 也得 stale 估計 → 選 universe 行為退化。

###### 流 10：News pipeline → Guardian halt + Regime + Learning

**為何值得列**：4 provider × 3 consumer 多端 fan-out；Guardian halt 共享 `Arc<AtomicBool> session_halted` 與 [claude_teacher/governance_impl.rs:1-206](srv/rust/openclaw_engine/src/claude_teacher/governance_impl.rs)。**雙寫源** → 任一斷線會導致 halt flag 不一致。

**典型問題**：
- CryptoPanic free tier 50 req/day quota；若超則 `AuthMissing` 但 pipeline 繼續無告警。
- RSS feed parse fail（feed-rs 解析錯）→ silent skip，severity 0 → Guardian 不 halt。

---

##### 給 Session 4（治理對照）的 hint：哪些根原則對應哪些流

CLAUDE.md §二 16 條根原則 →本 session 8 + 2 流的對應：

| 根原則（§二）| 主要關聯流 | 關聯點 |
|---|---|---|
| #2 Rust 為交易參數權威 | Flow 1, 4, 5 | RiskConfig ArcSwap / edge_estimates startup-only |
| #3 AI 輸出 ≠ 即時命令 | Flow 1, 7 | ExecutorAgent shadow hardcoded（G3-02 Wave 2 重構目標）|
| #5 對抗性止損 | Flow 4 | 9 position checks 含 PHYS-LOCK + DUAL-TRACK-EXIT |
| #6 失敗默認收縮 | Flow 1, 5, 6 | PostOnly 配置反向違反（G1-05）；live auth 失效 → graceful shutdown |
| #7 Backtest 強制 backtest_mode=true | Flow 5 | edge estimator 純歷史 PnL，不用未實現 PnL |
| #8 可解釋可審計 | Flow 4, 7 | 被拒絕路徑也寫 audit；rejection_coding.rs 統一原因碼 |
| #9 治理幾何性驗證 | Flow 6, 7 | 5 重門控 + change_audit_log 7 變更型態 |
| #10 認知誠實（DataQualityLevel）| Flow 3, 5 | FACT/INFERENCE/HYPOTHESIS marking；shadow vs production |
| #11 漸進放權（不可降級）| Flow 6 | EarnedTrust T0-T3 ladder + T3 max 1 auto-renewal |
| #15 5-Agent + Conductor | Flow 3, 7 | ai_service.py 5 handler + agent_audit_bridge factory |
| #16 SM cascading | Flow 1, 4, 6 | governance_core 4-SM 級聯 / SM-01 auth / SM-04 risk |

**Session 4 建議切入點**：
1. 從原則 #3（AI ≠ 即時命令）切入，對照 Flow 1 + 7 的 ExecutorAgent hardcoded shadow，問「這算原則違反還是設計上的故意分隔？」
2. 從原則 #6（失敗默認收縮）切入，對照 Flow 5 的 edge_estimates startup-only 限制，問「scheduler dormant 期間 cost_gate fallback 行為是否符合原則？」
3. 從原則 #8（可解釋可審計）切入，對照 Flow 7 的 change_audit_log DB 表名 unconfirmed 問題。

---

##### 交付物對照表

| 文件 | 路徑 | 行數 |
|---|---|---|
| 8+2 條資料流地圖 | [inventory_2_data_flows.md](.claude_reports/inventory_2_data_flows.md) | ~840 |
| 本摘要 | `.claude_reports/20260425_013122_inventory_session_3_summary.md` | ~150 |

---

##### 給 Session 4 / 5 的工作流改進建議

1. **「斷鏈點」應該交叉驗證**：本 session 標了 6 處斷鏈/unconfirmed，其中 4 處（Flow 2 callback 註冊 / Flow 7 DB 表 / Flow 8 systemd unit / Flow 8 maintenance flag CREATE）是「沒查到」而非「確認斷」。Session 4 / 5 任一觸碰這些主題前，應該先實證解決這 4 個未驗點。
2. **memory drift**：本 session 發現「9 checks 而非 15+」「5s file poll 而非 5min」兩處 memory/CLAUDE.md 表述偏差。Session 4 應先列「memory 中所有絕對數字」交給 healthcheck 或 grep 重驗。
3. **跨流共享狀態地圖**：流 1+4 共享 RiskConfig；流 7+10 共享 session_halted Arc<AtomicBool>；流 5+1（cost_gate）共享 edge_estimates HashMap。這些**跨流共享狀態**是 race condition / 一致性 bug 的高風險區，Session 4（治理）建議專列一節。


### A.4 Session 4/5 摘要 — 治理對照

#### Session 4/5 Summary — 治理對照（CLAUDE.md §二 16 條根原則）

##### 任務摘要

- Operator 意圖：Session 4/5，逐條對照 §二 16 條根原則的代碼實作 + 運行時驗證，暴露「紙面治理」vs「實際治理」的 gap。
- 完成狀態：✅ 已產出 [inventory_3_governance_audit.md](.claude_reports/inventory_3_governance_audit.md)（~590 行，16 條主節 + 跨條 gap 分析 3 大塊 + 結論）。
- 策略：先載入 Session 1/2/3 三份 summary + 1a/1b 全文 + 2 部分；用 grep 交叉驗證 6 處關鍵點（change_audit_log INSERT、agent audit_callback wiring、Teacher loop、trading.risk_verdicts INSERT 等）；不再派 sub-agent（治理判斷需主視野收口）。

---

##### 16 條原則的 gap 統計

| Gap 嚴重度 | 條數 | 條目編號 |
|---|---|---|
| **無 gap** | 0 | — |
| **僅輕微 gap（設計合理）** | 4 | #1, #2, #4, #16 |
| **部分 gap（需 watch）** | 6 | #5, #7, #8, #9, #11, #14 |
| **嚴重 gap（已知 P0/P1 觸碰）** | 6 | #3, #6, #10, #12, #13, #15 |

說明：
- 「無 gap」一條都沒有 — 16 條原則全部找到至少一個 gap，符合 operator「誠實 > 完整」原則
- #11 Agent autonomy 的 gap 主要是「依賴設計自律而非代碼強制」+ Live 階段未到，不算嚴重
- #3 / #15 的嚴重 gap 同源（ExecutorAgent shadow hardcoded）— CLAUDE.md §三 已知 verified finding 3，G3-02 Wave 2 重構目標
- #12 / #13 的 gap 與 LEARNING-PIPELINE-DORMANT-1 + Phase 5 PAUSED 同源

---

##### 最嚴重的 3 條 gap

###### 1. **原則 #8 認知誠實 + #15 多 Agent 協作 — Python agent audit 無 PG 持久化**

- **嚴重在哪**：grep 驗證 [change_audit_log.py](srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/change_audit_log.py) + [audit_persistence.py](srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/audit_persistence.py) 全文 0 個 `INSERT INTO`。所有 5-Agent decision/state event 只在 in-memory `_changes` list + JSONL 磁碟備份，無 PG 表。
- **後果**：(1) 重啟丟記憶體 list；(2) JSONL 滾出後 audit 也丟；(3) 原則 #8「每筆交易必須可重建」在 Python agent 路徑根本不滿足
- **CLAUDE.md §三 關聯**：3 大 Verified 發現 (3) ExecutorAgent shadow hardcoded — agent 不發單但發 audit；audit 卻無 PG，雙重「半治理」

###### 2. **原則 #3 AI ≠ 即時命令 + #15 多 agent 協作 — Executor 不發 IPC submit_order**

- **嚴重在哪**：[executor_agent.py:482](srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/executor_agent.py:482) `_shadow_mode: bool = True` + [strategy_wiring.py:467](srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/strategy_wiring.py:467) `ExecutorConfig()` 預設未覆蓋
- **後果**：(1) Python 5-Agent 框架運行但 ExecutorAgent **永遠**走 shadow path 寫 audit log，**不**透過 IPC `submit_order` 發 Rust；(2) Rust hot path 才是真實下單；(3) 原則 #3 lease-based 鏈在 Rust hot path **缺席**（hot path 不經 SM-02 lease）
- **CLAUDE.md §三 關聯**：明確列為 G3-02 Wave 2 重構目標

###### 3. **原則 #6 失敗默認收縮 — PostOnly 配置反向 + edge_estimates startup-only**

- **嚴重在哪**：(1) `strategy_params_demo.toml` PostOnly=false / `_live.toml` PostOnly=true（CLAUDE.md §三 verified finding 2）— **demo 不收縮、live 偏激進**，違反「失敗默認收縮」字面意；(2) [edge_estimates.rs:387](srv/rust/openclaw_engine/src/edge_estimates.rs) startup-only 熱重載 — scheduler 修復後仍需 restart engine 才生效，意味學習斷鏈 + cost_gate 用 stale fallback + 收縮失效串聯
- **後果**：(1) PostOnly 反向是 G1-05 立即修目標；(2) edge_estimator scheduler 4 天停滯（G1-01 verified finding 1）後 → 1 cell 災難 → cost_gate 用 stale ATR×conf×0.2 fallback；(3) 「不確定時保守」在 Live 階段直接違反
- **CLAUDE.md §三 關聯**：G1-01 + G1-05 兩條 P1 直接觸碰

---

##### 跨條原則 meta-gap top 1

**RiskConfig + ConfigStore ArcSwap 為 6 條原則共用樞紐**

[risk_config.rs:908](srv/rust/openclaw_engine/src/config/risk_config.rs) + [config/store.rs:837](srv/rust/openclaw_engine/src/config/store.rs) 同時承擔：

- #2 讀寫分離（patch via IPC + audit row）
- #4 風控不可繞過（Guardian 為派生視圖）
- #5 生存（cost_gate / drawdown thresholds）
- #6 失敗收縮（cognitive params / cost_gate fallback）
- #11 P0/P1 邊界（denylist 字串常量在 [applier.rs:226](srv/rust/openclaw_engine/src/claude_teacher/applier.rs:226)）
- #16 組合風險（portfolio params）

**為何嚴重**：4 IPC 寫入面（risk patch / strategy params / governor escalate / dynamic risk toggle）+ TOML 直接編輯（如 PostOnly verified finding 2 反向）共 5 條寫入路徑；任一**配置反向 / 熱重載順序顛倒** 即多原則 silently 失守。已知歷史案例 PostOnly verified finding 2 直接觸碰。

**建議 mitigation**：
1. RiskConfig 任何欄位變更（不限 patch_*_config 路徑，含 TOML 直編輯）必寫 V014 audit row + 6 條原則 invariant 自動測試
2. ConfigStore.patch 後加一個「是否仍滿足 16 條原則 invariant」的快速校驗 hook（純記憶體計算 < 1ms）
3. CLAUDE.md §三 加「多原則樞紐改動需 PA + FA + PM 三角 review」實施準則

---

##### 給 Session 5（風險熱點）的 hint

依本 session 發現，Session 5 風險熱點建議優先盤點以下 8 區：

###### A. 已知 P0/P1 觸碰原則的代碼點

1. **[executor_agent.py:482 + strategy_wiring.py:467](srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app)** — ExecutorAgent shadow hardcoded（觸碰 #3 / #15）
2. **`strategy_params_{demo,live}.toml` PostOnly 反向** — 觸碰 #6
3. **[edge_estimator_scheduler.py:716](srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/edge_estimator_scheduler.py)** + [edge_estimates.rs:387](srv/rust/openclaw_engine/src/edge_estimates.rs) — 雙風險（fcntl leader lock 死鎖 + startup-only 熱重載，觸碰 #6 / #7 / #12）
4. **[change_audit_log.py:160](srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/change_audit_log.py:160)** — 無 PG 寫入確認（觸碰 #8 / #15）

###### B. 多原則樞紐單點故障風險

5. **[risk_config.rs:908](srv/rust/openclaw_engine/src/config/risk_config.rs) + [config/store.rs:837](srv/rust/openclaw_engine/src/config/store.rs)** — 6 條原則共用樞紐
6. **[live_authorization.rs:620](srv/rust/openclaw_engine/src/live_authorization.rs) + HMAC key 漂移**（觸碰 #2 / #3 / #5 / #11）

###### C. 編譯期/設計鎖定的隱形邊界

7. **[step_4_5_dispatch.rs:935](srv/rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs)** + [intent_processor/mod.rs:1100](srv/rust/openclaw_engine/src/intent_processor/mod.rs)（**1100 行擠爆 §九 1200 硬上限**）— 不可拆 + 接近硬上限，下次 refactor 是熱點
8. **[fast_track.rs:407](srv/rust/openclaw_engine/src/fast_track.rs)** — 設計性 Guardian 旁路（FA-PHANTOM-1 歷史 bug 已修但設計風險仍在，觸碰 #4 / #5）

###### D. 文件大小違反 §九 1200 硬上限的熱點

詳見 Session 1 footer + Session 2 第 13 批：
- Rust 超 1200：`main.rs` 2062 / `bybit_rest_client.rs` 1725 / `instrument_info.rs` 1975 / `order_manager.rs` 1554 / `ipc_server/mod.rs` 1192 / `intent_processor/tests.rs` 1905 / `tick_pipeline/tests.rs` 3524
- Python 超 1200：`live_session_routes.py` 1449 / `ai_service.py` 1258 / `passive_wait_healthcheck.py` **1822** / `counterfactual_exit_replay.py` 1216

任一拆分時 NLL/borrow 變更可能引入沉默 bug — Session 5 應列為高優先風險區。

###### E. 雙源 byte-identical 約束的代碼點

- SM-02 / SM-04（Rust + Python）
- portfolio.rs / portfolio_risk_control.py
- atr_tracker.py / Rust price_tracker.rs
- cognitive.rs / cognitive_modulator.py
- guardian.rs / guardian_agent.py

需驗：(1) 哪些 Python 端確實在 hot path 被呼到；(2) byte-identical 約束的實際自動測試覆蓋

###### F. fail-open 路徑（與原則 #6 緊張）

- [agent_audit_bridge.py:373](srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/agent_audit_bridge.py:373) Exception swallow + 60s throttled WARNING
- [shadow_decision_builder.py:395](srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/shadow_decision_builder.py) IPC fail → silent drop（fail-open）
- audit_persistence 損壞行 skip 不靜默 drop（但仍 fail-open）

需驗：fail-open 集合是否完整列出，是否有 healthcheck 覆蓋

###### G. 未驗的關鍵 grep 點（Session 3 已標）

- ExecutionListener callback 註冊位置（Flow 2 步 4 sub-agent 推測）
- engine_maintenance.flag CREATE 點
- governance.change_audit DB 表名（grep 已驗為**負**：無 PG INSERT — 需 Session 5 確認 audit 確實只在 in-memory + JSONL）

###### H. 治理盲區（§二 沒規範但實作中半實作或缺失）

詳見本 Session 「跨條原則的 gap 分析」§3：
- A. Audit chain 應同時在 Rust + Python 平面持久化到 PG
- B. 熱重載契約應對所有 Config 一致
- C. 雙源語意對齊驗證
- D. 主動推進事件無 cadence audit
- E. GUI 寫入面 hot/cold 制度化

---

##### 交付物對照表

| 文件 | 路徑 | 行數 |
|---|---|---|
| 16 條原則治理對照 | [inventory_3_governance_audit.md](.claude_reports/inventory_3_governance_audit.md) | ~590 |
| 本摘要 | `.claude_reports/20260425_014527_inventory_session_4_summary.md` | ~190 |

---

##### 本次盤點中最不確定的 5 件事

1. **change_audit_log 是否真的完全沒 PG 寫入路徑？**
   - grep 全 srv/ 只找到 governance.lease_transitions / authorization_transition / risk_governor_transition 的 SQL 字串散落於 SM 各檔；change_audit_log.py + audit_persistence.py 自身都 0 個 INSERT。
   - **不確定**：(1) governance_hub.py / state_machine_base.py 是否在 cascade callback 中間接寫 PG（grep 顯示「change_audit」字串命中但無對應 INSERT）；(2) 是否有獨立的 audit consumer 在另一檔讀 in-memory list 寫 PG。Session 5 應實證 PG 端 `governance.*` 表是否真有 row。

2. **hot path 是否真有 fast_track 以外的 Guardian 旁路**
   - 只追了 step_4_5_dispatch + intent_processor + fast_track 三條主路徑；step_6_risk_checks 的 9 持倉風控有獨立分派（risk_close: tag）— 但這些是 close 不是 open，是否有「open 路徑繞 Guardian」的設計性旁路未驗。
   - **風險**：若 fast_track 之外還有第二條設計性旁路，原則 #4 守備面更大。

3. **Python guardian_agent / portfolio_risk_control / atr_tracker 是否實際在 hot path 被呼到**
   - Session 3 Flow 4 斷鏈點 3 推測 Python guardian_agent 僅 IPC `_handle_guardian` handler 被呼（非 hot path），但未實證。
   - **風險**：若 Python 端在某條路徑被熱呼，雙源 drift 風險顯著。Session 5 應對每對雙源跑 grep + tracing 驗證 hot path 是否觸碰 Python。

4. **strategist_scheduler 5min 自動 tune 的「邊界」實際範圍**
   - [strategist_scheduler/mod.rs:1166](srv/rust/openclaw_engine/src/strategist_scheduler/mod.rs) 每 5min UpdateStrategyParams IPC 改 5 策略運行時參數，無 operator 批准 — 但實際可調的參數範圍 / 上限 / clamp 在哪定義未追。
   - **風險**：若 strategist 自動調過 cost_gate 閾值或某個 P1 邊界值（例如 max_drawdown_pct），原則 #11 P0/P1 邊界守備可能弱於想像。

5. **edge_estimates 從 startup-only → IPC 熱重載的 commit 是否確實落實**
   - CLAUDE.md §三 提到「**先前 EDGE-DIAG-1-FUP-IPC 前無 IPC 路徑**，TOML 編輯需引擎重啟才生效，本 commit 新增 7 個 `exit.*` 欄位的 IPC 熱重載路徑」— 但這 7 欄位是 `exit.*`（Track P 物理 lock），**不含** edge_estimates.json 本身。
   - **風險**：edge_estimates 仍 startup-only；scheduler 修復後 4-day stall recovery 需 engine restart 才能讓 cost_gate 用新值。Session 5 應實證此熱重載 gap 是否仍存在。


### A.5 Session 5/5 摘要 — 風險熱點 + 整個盤點收官

#### Session 5/5 Summary — 風險熱點清單 + 整個盤點收官報告

##### 任務摘要

- Operator 意圖：Session 5/5 — 從前四份盤點交叉提煉風險熱點 + 紅色清單 + 整個盤點總結。
- 完成狀態：✅ 已產出 [inventory_4_risk_hotspots.md](.claude_reports/inventory_4_risk_hotspots.md)（~470 行 + 表格）。
- 策略：先讀四份前序產出（含 Session 1–4 摘要 + 全文按 chunk 讀取，因每份均超 25k token 限制）；不再派 sub-agent — 風險熱點需要主視野收口；用 git log 統計補 30 天新鮮數據；交叉引用六類熱點導出紅色清單。

---

#### 本次 Session 摘要

##### 六類熱點的 Top 熱度模組

| 類別 | 評選標準 | Top 1 / 最高頻 |
|---|---|---|
| 1. **複雜度熱點** | 行數作為 cyclomatic 的 proxy + 非測試 + 多職責 | `main.rs` 2062 行（**遠超 §九 1200**）+ `passive_wait_healthcheck.py` **1822 行** |
| 2. **耦合熱點** | fan-in 最高 + 跨流共享狀態 | **`RiskConfig + ConfigStore ArcSwap`** — 6 條根原則共用樞紐（Session 4 meta-gap top 1） |
| 3. **沉默熱點** | critical path × 「無對應測試/未直接驗證/推測」 | **`change_audit_log.py` + `audit_persistence.py` 0 個 INSERT INTO**（grep 已驗為負） |
| 4. **新鮮熱點** | 30 天 commit 數最高 production code | `paper_trading_routes.py` 67 commit + `pipeline_bridge.py` 63 commit |
| 5. **歷史熱點** | CLAUDE.md §三 P0/P1 編號出現次數 | **`edge_estimator_scheduler.py` + `edge_estimates.rs`** — G1-01 / EDGE-DIAG-1 / LEARNING-PIPELINE-DORMANT-1 / P1-7 B 多重觸碰 |
| 6. **邊界熱點** | Rust↔Python IPC + 系統↔Bybit + 系統↔DB | **Bybit REST**（`bybit_rest_client.rs` 1725 行 + `order_manager.rs` 1554 行）跨 Bybit edge |

##### 交集分析主要發現

###### 交集 A（熱點 × 低理解度）
- 模板已產出 Top 20 熱點模組待 operator 填（六類熱點重複出現 ≥2 類即列入）
- 唯一在三類熱點同時命中的條目：**`edge_estimates.json` startup-only 熱重載**（沉默 + 歷史 + 邊界）
- operator 應優先填的 10 個 = **沉默熱點 Top 10**（其他類別有歷史記錄可查）

###### 交集 B（熱點 × 治理 gap）
- Session 4 嚴重 gap 的 **6 個對應模組全部**同時是本 session 風險熱點：
  1. ExecutorAgent shadow（原則 #3+#15）→ 歷史 #2
  2. PostOnly 反向（原則 #6）→ 歷史 #3
  3. edge_estimates startup-only（原則 #6+#7+#12）→ 沉默+歷史+邊界
  4. change_audit_log 無 PG（原則 #8+#15）→ 沉默+邊界
  5. fast_track Guardian 旁路（原則 #4）→ 歷史 #4
  6. RiskConfig 樞紐（meta-gap top 1）→ 耦合 #1

**結論**：治理 gap 與代碼複雜度/沉默/邊界熱點高度重合，**驗證 Session 4 識別的 gap 不是紙面分析**。

---

#### 整個盤點（5 個 session 總結）

##### 總掃描模組數

| 平面 | 模組數 | LOC（產品向）| 備註 |
|---|---|---|---|
| **Rust**（openclaw_types + openclaw_core + openclaw_engine） | ~180 `.rs`（含 test） | **131,120** | 7 個 batch；test ~15k / prod ~116k |
| **Python**（app + ml_training + local_model_tools + helper_scripts + observer_pipeline + io_and_persistence + audit） | ~177 個（13 個 batch） | **~84,600** | stub ~1,520（local_model_tools 14 stub）+ 真實 ~83k |
| **總計** | **~357 個** | **~215,720** | 不含 .toml / .sql / static / docs / scripts |

##### 總資料流數

8 條必含 + 2 條額外（scanner cycle + news pipeline）= **10 條完整流**，均到「步驟編號 + file:line + 持久化點 + 斷鏈點」級別。

##### 治理 gap 總數

16 條根原則 vs 代碼實作對照：
- **無 gap**：0 條（全部至少有一個 gap，符合「誠實 > 完整」）
- **僅輕微 gap（設計合理）**：4 條（#1, #2, #4, #16）
- **部分 gap（需 watch）**：6 條（#5, #7, #8, #9, #11, #14）
- **嚴重 gap（已知 P0/P1 觸碰）**：6 條（#3, #6, #10, #12, #13, #15）

**meta-gap 跨條樞紐**：1 個 — RiskConfig + ConfigStore ArcSwap（6 條原則共用）。
**治理盲區**：5 個（A audit chain 須對齊到 PG / B 熱重載一致性 / C 雙源 byte-identical 驗證 / D 主動推進 cadence audit / E GUI 寫入面 hot/cold 制度化）。

##### 紅色清單 Top 5 與預估總工作量

| 紅色 # | 風險主題 | 觸碰原則 | 工作量（人日） |
|---|---|---|---|
| 1 | ExecutorAgent shadow hardcoded | #3 + #15 | 8–12 |
| 2 | edge_estimates startup-only 熱重載 | #6 + #7 + #12 | 3–5 |
| 3 | Python agent audit 無 PG | #8 + #15 | 4–6 |
| 4 | PostOnly 反向 + RiskConfig 樞紐 | #6 + #2/#4/#5/#11/#16 | 4–6 |
| 5 | fast_track Guardian 旁路防呆 | #4 + #5 | 2–3 |
| **總計** | — | **8 條原則覆蓋** | **21–32 人日** |

**並行性**：5 項中 #1 與 #4 高度耦合（Lease enforcement 與 RiskConfig invariant），建議串行；#2 / #3 / #5 可並行。1 工程師 5–7 週；2 工程師並行 3–4 週。

---

#### 對 Operator 的建議

##### 1. 先花多少時間填四份盤點的理解度與備註欄位？

**建議：8–12 小時，分 3 段**

- 4h：Session 1+2（357 個模組）— 只填理解度欄位，不寫備註，按表中 batch 順序快速掃過
- 2h：Session 3（10 條資料流）— 填理解度 + 標註自己最熟/最陌的 step（最熟的 1–2 條留作他日 mob session 教材）
- 2–4h：Session 4（16 條原則）— 填運行時信任度（高/中/低）；如果填「低」就跳到 Session 5 紅色清單對照
- 2h：Session 5（六類熱點 + 紅色清單）— 重點填**沉默熱點 Top 10 的理解度**（這是 operator 最可能不知道自己不知道的區）

完成後產出 1 個總結 issue：「我熟悉度 ≤2 的模組共 N 個」 — 這是 mob session 候選。

##### 2. 紅色清單是應該現在處理、還是延後？

**建議：分兩波**

**第一波（Live 上線前必修，~4–6 人日）**：
- 紅 #4 PostOnly 反向（1 人日修 + 3 人日 invariant linter）— 最快 ROI，TOML 一改可立即 ship
- 紅 #5 fast_track 防呆（2 人日 metric + sanity check）— 預防 FA-PHANTOM-1 復發

**第二波（Live demo 階段並行修，~12–18 人日）**：
- 紅 #2 edge_estimates IPC 熱重載（3 人日）— 解決 G1-01 復發風險
- 紅 #3 Python agent audit PG（4 人日）— 補治理盲區
- 紅 #1 ExecutorAgent shadow 重構（8 人日）— **最大改動，建議放在 Live demo 21d 觀察期內動**

**理由**：
- 紅 #4+#5 是 Live 上線前的「不修就立即出事」風險
- 紅 #1 是 Live 階段的「治理鏡頭」風險，但 Rust hot path 已實質下單，重構期可同時 demo 跑（雙保險）
- 紅 #2+#3 是「治理可審計性」風險，Live 出事時的 RCA 能力鍵 — 在 Live demo 期跑進去比 Live 啟動後再追補便宜

**不建議延後到 Live 之後**：5 項中除 #1 外，其餘 4 項在 Live 第一週內任一誤觸都會直接影響資金安全或診斷能力。

##### 3. 有沒有需要立刻提出修改 DOC/EX 治理文件的項目？

**建議：3 條**

1. **CLAUDE.md §二 加新原則衍生：「跨平面橋必熱重載 < 60s」**（治理盲區 §3.B）
   - 為什麼：edge_estimates startup-only 是「學習平面 → Live 平面」單向跨橋無熱重載；如果 §二 沒明文，下次新增類似橋（例如 ml/registry 上線時）會重蹈覆轍
   - 改寫位置：原則 #6（失敗默認收縮）下衍生「Config drift detect」實施準則

2. **CLAUDE.md §二 加新原則衍生：「audit chain 任一路徑必達 PG」**（治理盲區 §3.A）
   - 為什麼：Python agent audit 在 Python 平面不到 PG，原則 #8「可重建」靠 PG 串接；§二 字面只說「可解釋」沒說「PG 必達」
   - 改寫位置：原則 #8 下衍生「audit row 24h count > 0 healthcheck 強制」

3. **CLAUDE.md §三 加「多原則樞紐改動需 PA + FA + PM 三角 review」**（meta-gap top 1 對應）
   - 為什麼：RiskConfig 6 原則樞紐當前任一改動只走一般 review；TOML 直編輯（PostOnly verified finding 2）即多原則 silently 失守
   - 改寫位置：§三 「三大 Verified 發現」結尾加新衍生規範

EX 治理文件（DOC-08 / DOC-01 / EX-XX）暫不需立改，§二 + §三 改完已涵蓋。

##### 4. 本次盤點揭露的、operator 可能最沒預期的發現 Top 3

###### Top 1：Session 4 嚴重 gap 與 Session 5 熱點 100% 重合

6 個 Session 4 嚴重 gap 模組（ExecutorAgent / PostOnly / edge_estimates / change_audit_log / fast_track / RiskConfig）**全部**同時是 Session 5 風險熱點。**沒有「治理是紙面、代碼是另一回事」的脫節** — 治理 gap 就是代碼風險集中區。這意味 operator 不需要在「修代碼」與「補治理」之間選 — 修紅色清單 Top 5 就同時關閉 8 條原則的 gap。

###### Top 2：`change_audit_log.py` 全文 0 個 `INSERT INTO`

Session 3 標「⚠️ DB 表名未驗」原以為是 sub-agent 漏 grep；Session 4 重新 grep 全 srv/ 確認**為負** — Python 的 `change_audit_log.py` + `audit_persistence.py` **真的**沒有任何 PG 寫入，全靠 in-memory + JSONL。`governance.change_audit` 表名可能根本不存在於 schema。如果 operator 對「Python agent audit 已寫 PG」有任何隱性假設（例如「事故重建可以從 PG 拉到 agent log」），這個假設**不成立**。Live 階段一次 5-Agent 路徑事故，重建就只能靠 in-memory（重啟後 0 行）+ JSONL（可能已輪轉）。

###### Top 3：`local_model_tools/` 27 檔中 14 檔是 stub，仍被多處 import 為 fallback

Session 2 第 10 批揭露 14 個 stub（KlineManager / IndicatorEngine / SignalEngine / Orchestrator / IndicatorBase 等），全部 `compute()` 回 None / 空 list / zero qty。Rust 真實實作已接管（`openclaw_core::indicators` / `openclaw_engine::scanner` / `orchestrator` 等），但 `strategy_read_routes.py` / `strategy_ai_routes.py` / `scanner_rate_limiter.py` 仍 import stub 作 fallback 或 wiring 骨架。**這意味 strategy_wiring.py 的 12+ singleton 中有 5+ 個是「有 type 但無實作」的 placeholder** — 任一 stub 被誤改為「半實作」會讓 Rust 真實實作與 Python stub 同 import 點雙寫，運行時行為依 import 順序。Operator 可能以為這些 stub 已可安全刪除，但 deletion 會破壞下游 `wiring`：必須先重構 stub-import 站點，再刪 stub。

---

#### 本次盤點中最不確定的 5 件事

##### 1. **「複雜度」用行數 proxy 的偏差**

我沒跑 `radon cc` 或類似工具量真實 cyclomatic complexity。行數作為 proxy 對「常數表撐篇幅」的檔案（如 `instrument_info.rs` 1975 行多為合約規格、`bb_breakout/tests.rs` 1759 行測試 fixture）會高估複雜度。Top 10 中可能有 2–3 個應降排（特別是 6 號 `on_tick/helpers.rs` 1182 行多為 e2e test fixture）。

**含義**：紅色清單由「複雜度 + 沉默 + 歷史」三個維度共同決定，但複雜度權重偏高可能讓某些 hot-path 簡單但風險高的模組排不到熱點 Top 10。

##### 2. **「新鮮」未抽 +/- 行數，無法區分 refactor vs 業務改動**

git log 命令未抽 `--shortstat`，所以 Top 10 新鮮熱點只看 commit 數，無法區分「commit 多但都是測試/格式」與「commit 多且改業務邏輯」。例如 `pipeline_bridge.py` 63 commit 可能多為 import 整理 + wiring 順序調整，業務改動實際很少；反之 `governance_hub.py` 44 commit 是 mixin 拆分（高風險改動）。

**含義**：建議 operator 對 Top 10 中 4–6 名做一次 `git log -p --since="30 days ago"` 抽樣判斷新鮮度的「真實風險度」。

##### 3. **`change_audit_log` 是否真的完全沒 PG 寫入路徑**

Session 4 結論「全 source 0 個 INSERT INTO」基於 grep `INSERT INTO` 字面 + 無 dynamic SQL；但若 `governance_hub.py` / `state_machine_base.py` 在 cascade callback 中**間接**呼某個 audit consumer（grep 顯示「change_audit」字串命中但無對應 INSERT），仍可能存在我漏找的 PG 寫入點。

**含義**：紅色 #3 的工作量估計（4–6 人日）含「先驗證真的沒有」的時間；如果實證有，工作量降到 1–2 人日（在現有 PG 寫路徑上加 healthcheck 即可）。

##### 4. **30 天內 `--rebuild` 次數與 `edge_estimates.json` 改檔次數的對賬**

紅色 #2 的最壞情況「scheduler 寫了新檔，engine 持續用舊 HashMap 直到 restart」依賴一個事實：30 天內 engine 真的有新 edge_estimates 寫入但 engine 未重啟的窗口。我沒實證查 `git log --follow settings/edge_estimates.json` 的 mtime + `helper_scripts/restart_all.sh` 跑次數對照。如果實際上 operator 30 天內 `--rebuild` 跑了 5+ 次，每次 restart 都吸收最新 edge_estimates，IPC 熱重載的 ROI 比我估計低。

**含義**：紅色 #2 的優先級可能應降一級。建議 operator 在開始紅色 #2 工作前，先抽 30d `restart_all.sh` 觸發次數 + scheduler 寫次數 — 如果接近 1:1，工作量 3–5 人日不必投。

##### 5. **Top 5 紅色清單的工作量估計缺乏 Linux runtime 驗證**

我作為 Mac dev session（per memory `project_dev_runtime_split.md`）只讀靜態代碼 + 跑 grep；沒法跑 `cargo test` / 沒法 ssh trade-core 跑 Linux runtime 驗證；沒法實證「紅 #4 PostOnly 改 1 行 commit + restart 確實 60 分鐘 ship 完」這類經驗值。21–32 人日是「我能想到的」而非「實際需要的」。

**含義**：實際工作量區間應 ±30%。建議 operator 在 Linux runtime 跑紅色 #4 完整流程（修 toml → restart_all.sh --rebuild → grep settings/edge → healthcheck pass）量取真實的 1 人日工作量，再線性外推剩餘 4 項。

---

#### 交付物對照表

| 文件 | 路徑 | 行數 |
|---|---|---|
| Rust 模組清單（Session 1）| [.claude_reports/inventory_1a_rust_modules.md](.claude_reports/inventory_1a_rust_modules.md) | 308 |
| Python 模組清單（Session 2）| [.claude_reports/inventory_1b_python_modules.md](.claude_reports/inventory_1b_python_modules.md) | 302 |
| 端到端資料流地圖（Session 3）| [.claude_reports/inventory_2_data_flows.md](.claude_reports/inventory_2_data_flows.md) | 984 |
| 16 條根原則治理對照（Session 4）| [.claude_reports/inventory_3_governance_audit.md](.claude_reports/inventory_3_governance_audit.md) | 724 |
| **風險熱點清單（Session 5，本次）** | [.claude_reports/inventory_4_risk_hotspots.md](.claude_reports/inventory_4_risk_hotspots.md) | ~470 |
| Session 1 摘要 | `.claude_reports/20260424_213529_inventory_session_1_summary.md` | ~130 |
| Session 2 摘要 | `.claude_reports/20260424_221449_inventory_session_2_summary.md` | ~230 |
| Session 3 摘要 | `.claude_reports/20260425_013122_inventory_session_3_summary.md` | ~150 |
| Session 4 摘要 | `.claude_reports/20260425_014527_inventory_session_4_summary.md` | ~190 |
| **Session 5 摘要 + 整個盤點收官（本次）** | `.claude_reports/20260425_015739_inventory_session_5_summary.md` | ~270 |

**全 5 個 session 總交付**：~3,750 行表格 / 摘要 + 收官結論，覆蓋 357 模組 + 10 資料流 + 16 原則 + 6 類熱點 + 5 紅色清單 + 8 跨流共享狀態 + 5 治理盲區。


---

## 文件結束

本統合報告整合 2026-04-24 ~ 2026-04-25 五個 Session 共 ~3,750 行表格 / 摘要，涵蓋 ~357 個產品向模組、10 條資料流、16 條根原則、6 類熱點、Top 5 紅色清單、8 跨流共享狀態、5 治理盲區。

原始素材保存於 `.claude_reports/` 目錄，本文件為 operator 「先看一份統合再決定要不要追原檔」的單一入口。
