# E1 報告 — 25 個 skill description 改寫為觸發條件式 · 2026-06-11

## 任務摘要

把 `srv/.claude/skills/` 下全部 25 個 SKILL.md frontmatter `description:` 改寫成「觸發條件式」（WHEN 不 WHAT）：刪內容清單、保留 owner agent 路由標註與互補關係（壓縮）、目標 ≤120 全形字/條、YAML 單行安全。依據 obra/superpowers 實證（description 摘要工作流 → 模型照 description 做跳過正文；25 條常駐 system prompt → 變短=每 session 固定 token 下降）。

**只改 description 欄位**：git diff 證 25 檔各 1 行（25 insertions / 25 deletions），正文與 `name:` 零觸碰。**未 commit**（PM 統一批次提交）。

## 修改清單

`srv/.claude/skills/<name>/SKILL.md` × 25（frontmatter `description:` 行各 1 處）。
根目錄 `/Users/ncyu/Projects/TradeBot/.claude/skills` 為 symlink → `srv/.claude/skills`（實查 `lrwxr-xr-x`），單副本即全覆蓋。

## 25 條 old → new 對照全表

| # | skill | old | new |
|---|---|---|---|
| 1 | 16-root-principles-checklist | 16 條根原則逐條 + 9 條安全不變量 + 硬邊界守護；CC agent 對代碼/設計/計劃做合規審查時使用。 | CC agent 合規審查時必讀：任何觸及執行權限/live_execution_allowed/system_mode 的代碼、設計、Sprint 計劃，或全系統審計；E2 發現可疑硬邊界改動時亦讀。 |
| 2 | bilingual-comment-style | Compatibility skill name for the current OpenClaw comment style. Enforces Chinese-first comments, MODULE_NOTE clarity, and touched-block cleanup. TW writes; E2 reviews. | 注釋規範唯一正本：TW 接注釋/MODULE_NOTE 工作、E1/E1a 新增或實質改動代碼需補注釋、E2 審查 diff 注釋品質時必讀。 |
| 3 | bybit-policy-compliance | Bybit 平台政策合規 — ToS / 地理禁區 / KYC / API 用戶協議 / Rate limit / Broker rebate / IP whitelist / UTA / Master-Sub account / 公告追蹤節奏。BB agent 主用，與 crypto-microstructure-knowledge 互補（後者技術微結構，本檔政策面）。 | BB agent 主用：新 Bybit endpoint/功能接通前合規 review、API 鎖/帳戶異常、rate limit 警報、政策公告變動、新地區部署評估時讀（微結構歸 crypto-microstructure-knowledge）。 |
| 4 | crypto-microstructure-knowledge | Crypto perpetual / spot 微結構知識手冊 — Funding rate 動態、Liquidation cascade、Basis trading、Perpetual term structure、Execution optimization (TWAP/VWAP/Implementation Shortfall)、PostOnly/IOC fee 計算。QC agent 主用（技術微結構視角）；BB agent 按需 cross-ref（policy 視角由 bybit-policy-compliance 主負）。 | QC agent 主用：評估涉 funding/basis/liquidation 的策略、執行成本/fee 爭議、套利提案時讀；BB 涉微結構時 cross-ref（政策面歸 bybit-policy-compliance）。 |
| 5 | data-drift-detection | 資料漂移偵測 — Distribution shift / Concept drift / Population Stability Index (PSI) / KL divergence / KS test / Wasserstein distance；live 階段 ML 模型監控 SOP。MIT agent 主用。 | MIT agent 主用：懷疑 live ML 模型輸入分布漂移、預測質量退化、或設計 drift 監控時讀。 |
| 6 | db-schema-design-financial-time-series | 金融時序資料庫 schema 設計 — TimescaleDB hypertable / partition / compression / hot-path index / engine_mode 隔離 / Guard A/B/C migration 規範 / V001-V024 lessons。MIT agent 主用。 | MIT agent 主用：設計新 ML/trading 表、寫 V### migration、規劃 hypertable/chunk、PG 慢查詢或 migration silent-noop 排查時讀。 |
| 7 | doc-cross-reference | 治理文件交叉引用一致性審計（DOC-XX / SM-XX / EX-XX / P0-XX 編號 + 索引 + 鏈接 / README ↔ TODO ↔ memory 漂移偵測）；R4 agent 純審查。 | R4 agent 純審查：文檔索引一致性、DOC-XX 等編號引用漂移、README/TODO/memory 邊界衛生、歸檔後索引驗證、引用 path 失效排查時讀。 |
| 8 | e2e-integration-acceptance | Wave 完成 / Phase 結束 / Live 前置端到端集成驗收 — 雙進程 E2E、灰度 7 天 0 CRITICAL、冒煙最短路徑、業務鏈完整度。QA agent 主用。 | QA agent 主用：Wave/Phase 收尾 sign-off、Live 前置驗收、多模塊合入後首次集成驗收、重大架構改動後必讀；E4 管代碼層測試，QA 管業務鏈完整性。 |
| 9 | feature-engineering-protocol | ML 特徵工程嚴謹性審計 — Look-ahead bias / target leakage / survivorship bias / cross-section leakage / time-zone leakage / re-sample boundary leak。MIT agent 主用，含偵測 SQL 範本。 | MIT agent 主用：設計 feature pipeline、準備 ML 訓練 dataset、新 feature 表上線前、或 IS 漂亮 OOS 崩（疑 leakage）的 RCA 時必讀。 |
| 10 | gui-style-guide | OpenClaw Control Console GUI style and interaction guide; E1a agent primary skill. Uses README-listed tabs and the existing vanilla HTML/JS/CSS stack. | E1a agent 主用：新增或改動 Control Console GUI 元件、Tab 改版、修改前端 static 檔，或對 GUI 做風格與互動審查時必讀。 |
| 11 | math-model-audit | 策略數學基礎審計、VaR / CVaR / Kelly / position sizing 驗證、Alpha 研究方法論審查；含 Operator 已拒絕方法黑名單。QC agent 純審查，不寫代碼。 | QC agent 純審查不寫碼：策略數學體檢、sizing/risk metric 驗證、alpha 研究方法論審查、edge 估計可疑、或新方法提案需核對 operator 已拒黑名單時讀（quant 三段鏈中段）。 |
| 12 | ml-pipeline-maturity-audit | ML pipeline 成熟度審計 — 5 階段（Foundation / Skeleton / Shadow / Canary / Production）+ 4 維度（writer-spawn / consumer-exists / row-accumulation / decision-impact）評級框架。MIT agent 主用，避免「表存在 = pipeline live」假象。 | MIT agent 主用：評估 ML pipeline 真實成熟度與接線狀態、驗證 dormant/shadow/canary 宣稱、phase launch 前 readiness、或疑「表存在=pipeline live」假象時讀。 |
| 13 | owasp-checklist | OWASP Top 10 (2021) 項目化審計，針對 OpenClaw FastAPI / Rust IPC / PostgreSQL / Bybit REST 的 attack surface 量身。E3 agent 主用。 | E3 agent 主用：安全審計、PR pre-merge security gate、新增 API 路由/IPC handler/webhook、或改動觸及認證、密鑰、SQL、subprocess 時必讀。 |
| 14 | performance-profiling | Rust + Python + PostgreSQL 三層效能分析；針對 128GB 統一記憶體 / 4-8GB PG 限制 / Apple Silicon 部署目標調校。E5 agent 主用。 | E5 agent 主用：效能優化、latency 超 SLA、記憶體/CPU spike、DB 慢查詢排查，及每 Phase/Wave 完成後強制體檢時讀；SLA 閾值唯一正本在此。 |
| 15 | portfolio-construction-protocol | 組合構建與資金管理手冊 — Kelly fractional 四層、Risk parity、相關性與因子分析、VaR/CVaR/EVT、Stress test、Risk decomposition、Drawdown control、Live 階段績效歸因。QC agent 主用。 | QC agent 主用：多策略資金分配、sizing 設計、組合級風險評估、drawdown 降倉決策、live PnL 偏離 backtest 歸因時讀；新策略/新 symbol 加入前必過。 |
| 16 | pr-adversarial-review | PR / 代碼變更對抗審核 SOP — 假設 E1 寫錯找 root cause / race / leakage / shortcut；senior + FA standard；E2 主用，發現 issue 退回 E1 不代寫。 | E2 agent 主用：審任何 E1/E1a 代碼改動（E4 回歸前必跑）、PR diff/commit/staged 變更審查時必讀；發現 issue 退回 E1 不代寫。 |
| 17 | quant-strategy-design | 量化交易策略「設計」視角（先用本 skill）→ math-model-audit（數學審計）→ walk-forward-validation-protocol（驗證），三者順序遞進不可顛倒；Alpha 來源 framework、信號融合、衰減分析、多時間框架、行為金融異常、replication crisis 警覺。QC agent 主用。 | QC agent 主用：新策略提案、alpha hypothesis、信號設計、paper/KOL 異常評估、edge 衰減接班評估時先讀（三段鏈之首 → math-model-audit → walk-forward-validation-protocol，順序不可顛倒）。 |
| 18 | regression-testing-protocol | 回歸測試 SOP — 測試基準線追蹤、不刪測試遮蓋失敗、並發測試、跨語言浮點 1e-4 容差、SLA 壓測、mock 不掩蓋邏輯、Rust + Python 雙引擎測試。E4 agent 主用。 | E4 agent 主用：跑回歸/驗收測試、報告測試計數、新增或改動測試檔、或測試結果與基準線有出入時必讀。 |
| 19 | secret-leak-detection | 掃描代碼/log/commit 中的 API key、authorization HMAC、密鑰路徑、credential pattern 洩漏。E3 agent 主用，PR pre-merge gate。 | E3 agent 主用：密鑰洩漏掃描、PR pre-merge gate、部署前最後一道閘、commit history 體檢、或改動觸及 secret/authorization 路徑、新增 env var 或 log 時必讀。 |
| 20 | spec-compliance | 對照 OpenClaw 治理文件做 Gap 分析（.docx + .md，數量隨治理演進變動，以 SPECIFICATION_REGISTER.md 為準）；提交前/PR 審查/Wave 計劃合規性審查時使用。FA agent 主用。 | FA agent 主用：治理符合性審計、DOC-XX Gap 分析、Wave/Sprint 計劃合規 sign-off、或 PR 觸及 governance/risk/lease/order/audit 路徑與硬邊界字段時必讀。 |
| 21 | time-series-cv-protocol | 時序 ML 模型 cross-validation 設計 — Purged k-fold、Embargo、TimeSeriesSplit、Walk-forward variants、CSCV。MIT agent 主用，與 walk-forward-validation-protocol（QC 視角）互補：QC 看策略 alpha 顯著性，MIT 看 ML 模型訓練 CV 嚴謹性。 | MIT agent 主用：設計 ML 訓練 CV、任何 model 訓練前、OOS 退化排查、ONNX export 前驗證時讀；策略 alpha 顯著性（QC）歸 walk-forward-validation-protocol。 |
| 22 | token-cost-analysis | Layer 2 AI 推理（Ollama L1 / Claude L2 / LM Studio）token 用量、成本歸因、cost_edge_ratio 監控；AI-E agent 純分析。 | AI-E agent 純分析：AI token 成本審計、cost_edge_ratio 評估、Layer 2 預算超標、月度成本回顧、新 L2 工具上線前 cost projection 時讀。 |
| 23 | ultracode-full-audit | OpenClaw 全盤多視角審計編排設置（主會話/conductor 專用，非 subagent skill）。當 operator 啟用 ultracode 並要求「全盤審查/全面檢查/multi-agent 優化/冷酷對抗審計」時使用：主會話親做 Stage 0 凍結與 Stage 3-4 收斂，並行審計段（Stage 2）以 Workflow 調用 saved script openclaw-full-audit。未啟用 ultracode 時降級為 PM 順序鏈或先徵求 operator 同意。 | 主會話/conductor 專用，非 subagent skill：operator 要求「全盤審查/全面檢查/multi-agent 優化/冷酷對抗審計」時必讀，含 ultracode 未啟用時的降級判斷。 |
| 24 | ux-checklist | 交易系統 GUI 可用性 / 認知負荷 / 錯誤狀態 / 防誤觸 audit；A3 agent 純審查不寫代碼。 | A3 agent 純審查不寫碼：GUI UX/可用性審計、新 tab/modal/表單上線前、Live GUI readiness、或操作流被回報易誤操作/看不懂時讀。 |
| 25 | walk-forward-validation-protocol | 量化策略「驗證 / 回測」操作手冊 — Walk-forward、Deflated Sharpe、PSR、PBO、CSCV、multiple testing 修正、樣本量、資料品質統計診斷、參數穩健性。QC agent 主用，與 quant-strategy-design 互補（design vs validation）。 | QC agent 主用：策略上線前驗證、Sharpe/OOS 顯著性判斷、參數 sweep 評審、提案只引 in-sample 表現時讀（quant 三段鏈之末）；ML 訓練 CV 歸 MIT time-series-cv-protocol。 |

## 總字數 before/after

- **raw 字元數：3,525 → 2,469（−30.0%）**（description 值本身，不含 `description: ` 前綴）。
- 全形等效寬度（CJK=1、ASCII=0.5，east_asian_width 計算）：**25 條全部 ≤91.0**，全數達標 ≤120 全形字。
- raw 字元數 3 條 >120：bybit-policy-compliance 124 / quant-strategy-design 138 / walk-forward-validation-protocol 121。**全因保留長英文 skill 名交叉引用**（`crypto-microstructure-knowledge` 31 字、`walk-forward-validation-protocol` 32 字、`math-model-audit`+`walk-forward-validation-protocol` 合計 48 字），互補路由是規則 2/3 要求保留項；按「全形字」口徑（ASCII 半形計 0.5）三條分別為 84.0 / 91.0 / 81.5，均達標。

## YAML 驗證結果

- 驗法：`venvs/mac_dev/bin/python`（PyYAML 6.0.3）逐檔 `yaml.safe_load(text.split('---')[1])`，檢查 dict 含 name+description、description 為單行 str、name 與目錄名一致。
- **25/25 PASS，0 失敗**。新文案統一用全形標點（：、；（））+ 半形 `/`，無 `": "`、無 ` #`、無起始特殊字元，plain scalar 安全（`V###` 的 `#` 前無空白，非註釋）。
- 驗證腳本：`/tmp/validate_skill_yaml.py`（臨時，不入庫）。

## 治理對照

- 規則 1（WHEN 不 WHAT）：25 條全部刪除內容/步驟清單，改為任務/症狀/觸發詞，逐條對照各檔正文「何時觸發」段撰寫（先讀後改）。
- 規則 2（owner 路由）：25 條全部保留 owner agent 標註（CC/TW+E1/E1a+E2/BB/QC/MIT/R4/QA/E1a/E3/E5/E2/E4/FA/AI-E/主會話 conductor/A3），「純審查不寫碼」「純分析」姿態字樣保留。
- 規則 3（互補關係壓縮保留）：quant 三段鏈（design→audit→validation；之首/中段/之末三標籤互鎖）、QC↔MIT CV 分工、BB↔QC 政策/微結構分工、QA↔E4 業務鏈/代碼層分工皆保留壓縮版。
- 三個錨定範例：#5 data-drift、#18 regression 照錨文採用（僅標點轉全形）；#1 16-root-principles 照錨文 + 追加「E2 發現可疑硬邊界改動時亦讀」（正文「何時觸發」明列 E2 為呼叫方，錨文未涵蓋，補上防漏觸發——deviation 已此處標註）。
- 「唯一正本」指針保留 2 處：bilingual-comment-style（注釋規範正本）、performance-profiling（SLA 閾值正本）——屬「何時來讀本檔」的路由信息非內容清單。
- 改動範圍：`git status`+`git diff --stat` 證 25 檔、25 insertions/25 deletions，無正文/name/allowed-tools 觸碰；未 commit。

## 別處複述掃描（只報告，未改）

grep docs/ + .codex/ + .claude/agents/（26 個舊 description 特徵片段）：

- **無任何檔案逐字複述完整舊 description**（全文探針 0 命中）。
- 近似複述 3 處（內容清單式 echo，在 agent 正文，非 skill frontmatter）：
  1. `.claude/agents/CC.md:28` —「16 條根原則 + 9 條安全不變量 + 5 hard gates 逐項合規檢查」≈ 舊 #1 內容清單。
  2. `.claude/agents/E3.md:56` —「API key / authorization HMAC / 密鑰路徑 / credential pattern」≈ 舊 #19 清單。
  3. `.claude/agents/FA.md:31` —「治理文件以 SPECIFICATION_REGISTER.md 索引為準（數量隨演進變動）」≈ 舊 #20 片段。
- 歷史報告引用 1 處：`docs/CCAgentWorkSpace/CC/workspace/reports/2026-03-31--wave5_compliance_review.md`（含「16 條根原則逐條」，歸檔性質）。
- 其餘大量「9 條安全不變量」命中為 DOC-08 §12 領域術語（PA/E1/FA 等歷史報告、execution_plan、amendments），非 description 複製，屬噪音。
- `.codex/`（AGENT_DISPATCH_PROTOCOL.md / DEPLOYMENT.md / DISPATCH_LEDGER.md）0 命中。
- 建議（PM 裁量，本任務不動）：CC.md:28 / E3.md:56 / FA.md:31 三處與新 description 風格無衝突（agent 正文允許職責描述），但若 PM 想全面去 WHAT 化可列 follow-up。

## 不確定之處（誠實披露）

1. **「≤120 全形字」口徑**：按「ASCII 半形計 0.5」的全形等效口徑 25/25 達標（max 91.0）；按 raw 字元數口徑 3 條超標（121-138），超出部分全為必留的長英文 skill 名。若 PM 採 raw 口徑為硬上限，唯一再壓縮路徑是把交叉引用改為「三段鏈」標籤不點名（會弱化路由明確性），請 PM 裁決。
2. **#1 對錨文的偏離**：追加了「E2 發現可疑硬邊界改動時亦讀」一句（依正文觸發面補全）；若 PM 要嚴格錨文可一行還原。
3. **#23 ultracode**：舊 description 含的 fallback 行為（「未啟用降級 PM 順序鏈」）屬 WHAT 已刪，僅留「含降級判斷」觸發提示；reference_ultracode_full_audit memory 條目仍描述舊機制，無漂移風險（機制在正文未動）。
4. 模型「照新 description 觸發」的真實效果需 1-2 個 session 實際派工觀察（本任務只能保證文本對正文保真，無法在本 session 內實證觸發行為變化）。

## Operator / PM 下一步

1. E2 對抗審查本 25 行 diff（重點：觸發面是否寫漏/寫寬、路由標註完整性、YAML 安全）。
2. E4 無代碼回歸需求（純 .claude 配置文檔）；可由 R4 做一次 skill↔agent profile 交叉引用巡檢代替。
3. PM 統一批次 commit（建議 `--only` 25 檔 + 本報告 + E1 memory，`[skip ci]`）。
4. 三端同步時注意根目錄 `.claude/skills` 為 symlink，無需另行同步副本。
