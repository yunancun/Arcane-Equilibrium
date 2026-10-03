# 玄衡開發歷程與路線變更

首次記錄／分期採用：2026-10-03（Asia/Shanghai）。歷史來源觀察基線：`af12fc9e0b75925ad0404a351018cebd21598277`。
Operator 已採用 R1–R8 作為日誌分類；這是七個主要開發階段加一個架構候選，
不是八個正式產品 release，也不聲稱前七階段全部完成。期間是近似且重疊的開發重心。

[Git 記錄決策與查詢方法](../decisions/2026-10-03--route-history-versioning.md) ·
[結構化登記簿](2026-10-03--route-history-register.json) ·
[日常工程日誌](../CLAUDE_CHANGELOG.md) · [現行 TODO](../../TODO.md)

## R1–R8 路線總覽

| Route-Id | 時期／記錄狀態 | 主要重心 | 轉變理由與保留能力 |
|---|---|---|---|
| R1：受治理的 Bybit 自動交易系統 | 2026-03 ～ 2026-04 初；`historical` | 建立多策略、五 Agent、風控與 Decision Lease，當時以 Paper 穩定運行後準備 Live 為目標。 | 先把自動交易置於受控、可解釋的執行框架。 保留：風控、執行與學習分離。 |
| R2：Rust 交易核心與研究基礎整合 | 2026-04 ～ 2026-05 初；`historical` | Rust 單一交易權威、三模式引擎與 DB／ML／回放研究基礎整合。 | 消除 Python／Rust 雙權威漂移，建立共用交易與研究底座。 保留：Python API／GUI／分析與既有治理能力。 |
| R3：產品定位與盈利路徑收斂 | 2026-05-20 ～ 2026-05 下旬；`historical` | 同一審議週期比較策略工廠、直接 alpha、雙軌、商業驗證、Copy Trading，收斂為完整自營 quant bot。 | 校準產品定位、成本、資本規模與可驗證的盈利路徑。 保留：自營主帳完整能力；Copy Trading 保留為有條件後續渠道。 |
| R4：完整自治能力擴張 | 2026-05-21 ～ 2026-05-31 起凍結大部分實作；`historical` | v5.8 補充 M1–M13，自主選題、學習、監控、退役、配置與路由。 | 把長期自行迭代目標拆成具體自治能力。 保留：v5.7 派工基線及交易權威。 |
| R5：Alpha 證據優先 | 2026-05-31 ～ 2026-06 起延續；`historical` | v5.9 凍結大部分自治 active-IMPL，先找可信成本後 alpha；M7 保留例外。 | 當時成本牆調查顯示候選優勢不足，先解策略證據缺口。 保留：自治設計與既有 Stage／風控；凍結並非全部取消。 |
| R6：AI／ML 真實落地與證據修復 | 2026-07 ～ 2026-09 及未完成尾項；`historical_with_open_program` | AIML V2 要求合格資料、真實 fit、Rust 消費、自然第二代、恢復與運行證據。 | 修復 source／tests 與真正功能、部署及效果之間的差距。 保留：研究資料與模型零件、Rust 權威、資格與效果邊界。 |
| R7：有限工程單元、可用功能優先 | 2026-09 下旬 ～ 截至 2026-10-03；`current_delivery_emphasis` | 先以有限單元驗證窄範圍功能；Bybit 修復與 D1.1 本機模型消費屬此分期。 | 避免把遠端正式環境證明前置為所有本機開發的阻塞。 保留：正式上線要求、舊契約與權限繼續有效；只調整交付節奏。 |
| R8：本機學習與交易＋外部歷史回測 | 2026-10-03；`candidate` | 本機草擬、學習及交易，成熟平台提供歷史回測／評估，回傳有限結果。 | 減少全市場歷史自持與研究基礎設施維護負擔。 保留：本機交易證據、策略／學習所有權與既有風控／採用閘門。 |

## 各期證據與限制

- **R1**：[march-roadmap](../archive/2026-07-09--governance_dev_phase_history/audits/2026-03-31--development_roadmap_v2.md)。Paper promotion 是歷史路線，後續 Stage 0R／Demo 政策已改。
- **R2**：[rust-authority](../adr/0001-rust-as-trading-authority.md)、[three-engine](../adr/0002-three-mode-engine-independent-risk-configs.md)、[fusion-plan](../references/2026-04-04--execution_plan_v1.md)。融合方案的舊二十週排程只供歷史追溯。
- **R3**：[may-v2](../archive/2026-05-21--srv_root_cleanup/2026-05-20--autonomous-strategy-system-v2.md)、[may-v3](../archive/2026-05-21--srv_root_cleanup/2026-05-20--lean-direct-alpha-capture-v3.md)、[may-v4](../archive/2026-05-21--srv_root_cleanup/2026-05-20--dual-track-architecture-v4.md)、[may-v4.3](../archive/2026-05-21--srv_root_cleanup/2026-05-20--commercial-evidence-sprint-v4.3.md)、[may-v5.5](../archive/2026-05-21--srv_root_cleanup/2026-05-20--execution-plan-v5.5.md)、[may-v5.7](../execution_plan/2026-05-20--execution-plan-v5.7.md)、[positioning-amendment](../governance_dev/amendments/2026-05-25--AMD-2026-05-25-02-v55-bot-positioning-capital-structure-formalization.md)。本期含多個草案與否決；不是所有方案均實作或正式採納。
- **R4**：[may-v5.8](../execution_plan/2026-05-20--execution-plan-v5.8.md)、[plan-changelog](../../CHANGELOG.md)。十三模組入 scope 不等於全部已實作、採用或有效。
- **R5**：[plan-changelog](../../CHANGELOG.md)、[alpha-amendment](../governance_dev/amendments/2026-05-31--AMD-2026-05-31-01-alpha-edge-evidence-governance.md)。歷史研究結果不能當今日候選／市場結論。
- **R6**：[aiml-v2](../execution_plan/2026-07-19--ai_ml_long_lived_repair_and_landing_plan.md)、[aiml-ledger](../execution_plan/ai_ml_landing/PROGRESS.md)。PROGRAM_ADOPTED／S1_CLOSED 不等於完整學習或交易落地；狀態仍讀 TODO。
- **R7**：[current-todo-snapshot](../../TODO.md)、[engineering-log](../CLAUDE_CHANGELOG.md)。H2 source 採用、D1.1 候選與 runtime 狀態分開；不是重開已關閉 workflow。
- **R8**：[r8-portable](../decisions/2026-10-03--r8-hybrid-research-candidate.md)。分類已採用，技術架構仍候選；QuantConnect 選型與遷移未驗收。

以上連結方便閱讀工作樹；需要精確原文時使用登記簿的固定 Git commit/path/blob/sha256。
原文中歷史數值、採用或運行敘述只屬原觀察期，本次沒有重驗其市場、主機或交易結果。

## 五月路線方案版本鏈

以下十八個節點屬同一策略路線審議 family，不包含四月融合方案 V1／V2、Rust 遷移 V3、
TODO v884、資料庫 V### 或產品 release。文件日期不等於 Git 提交、Operator 採納或部署日期。

| 版本 | 文件日期 | 分期／變動類型 | 內容與證據 |
|---|---|---|---|
| v1 | 2026-05-20 | R3／`initial_proposal` | 策略與架構重設計；其中人工紀律執行層分支後被拒絕。[來源](../archive/2026-05-21--srv_root_cleanup/2026-05-20--strategy-architecture-redesign-recommendation.md)；`DRAFT` |
| v2 | 2026-05-20 | R3／`thesis_change` | ASDS：自主策略發現工廠，保留執行與治理底盤。[來源](../archive/2026-05-21--srv_root_cleanup/2026-05-20--autonomous-strategy-system-v2.md)；`DRAFT` |
| v3 | 2026-05-20 | R3／`thesis_change` | 直接 alpha／短期現金流，策略工廠後置。[來源](../archive/2026-05-21--srv_root_cleanup/2026-05-20--lean-direct-alpha-capture-v3.md)；`DRAFT` |
| v4 | 2026-05-20 | R3／`thesis_change` | 短期 Direct Exploit＋長期 ASDS 雙軌。[來源](../archive/2026-05-21--srv_root_cleanup/2026-05-20--dual-track-architecture-v4.md)；`DRAFT` |
| v4.1 | 2026-05-20 | R3／`engineering_correction` | 對齊真實 schema、資料與派工條件。[來源](../archive/2026-05-21--srv_root_cleanup/2026-05-20--dual-track-architecture-v4.1.md)；`DRAFT` |
| v4.2 | 2026-05-20 | R3／`scope_contraction` | Track B 投入縮至零，收緊資料與 Demo 證據。[來源](../archive/2026-05-21--srv_root_cleanup/2026-05-20--dual-track-architecture-v4.2.md)；`DRAFT` |
| v4.3 | 2026-05-20 | R3／`thesis_change` | 改為技術＋商業證據衝刺；IP sale 後被撤回。[來源](../archive/2026-05-21--srv_root_cleanup/2026-05-20--commercial-evidence-sprint-v4.3.md)；`DRAFT_WITH_RETRACTION` |
| v4.4 | 2026-05-20 | R3／`scope_reframe` | 放棄雙軌敘事及內容訂閱變現，重定資本／時間邊界。[來源](../archive/2026-05-21--srv_root_cleanup/2026-05-20--execution-plan-v4.4.md)；`ACTIVE_AS_WRITTEN` |
| v5.0 | 2026-05-20 | R3／`thesis_change` | 放棄訂閱成本損益兩平敘事，候選回到資料驗證。[來源](../archive/2026-05-21--srv_root_cleanup/2026-05-20--execution-plan-v5.0.md)；`DRAFT` |
| v5.1 | 2026-05-20（間接） | R3／`reviewer_proposal` | 僅在 v5.2 引用的 reviewer proposal；未找到獨立正文。[來源](../archive/2026-05-21--srv_root_cleanup/2026-05-20--execution-plan-v5.2.md)；`REFERENCE_ONLY` |
| v5.2 | 2026-05-20 | R3／`thesis_change` | Adaptive Strategy Lab：生存底座＋動態 alpha＋配置。[來源](../archive/2026-05-21--srv_root_cleanup/2026-05-20--execution-plan-v5.2.md)；`DRAFT` |
| v5.3 | 2026-05-20 | R3／`engineering_correction` | Sensor-first／alpha-first，修正期權成本與開發順序。[來源](../archive/2026-05-21--srv_root_cleanup/2026-05-20--execution-plan-v5.3.md)；`DRAFT` |
| v5.4 | 2026-05-20 | R3／`scaling_reframe` | 把 Master Trader Copy Trading 設為主要擴張途徑。[來源](../archive/2026-05-21--srv_root_cleanup/2026-05-20--execution-plan-v5.4.md)；`DRAFT` |
| v5.5 | 2026-05-20 | R3／`product_positioning_change` | 完整自營 quant bot 單一產品；Copy Trading 有條件後置。[來源](../archive/2026-05-21--srv_root_cleanup/2026-05-20--execution-plan-v5.5.md)；`FINAL_DRAFT` |
| v5.6 | 2026-05-20 | R3／`scope_expansion` | 加 Macro／On-chain／Earn，並修正策略建設順序。[來源](../archive/2026-05-21--srv_root_cleanup/2026-05-20--execution-plan-v5.6.md)；`FINAL_PENDING_DISPATCH` |
| v5.7 | 2026-05-20 | R3／`engineering_correction` | Dispatch-Safe Patch；六項工程精度修正，thesis 不變。[來源](../execution_plan/2026-05-20--execution-plan-v5.7.md)；`HISTORICAL_DISPATCH_PACKET` |
| v5.8 | 2026-05-21 | R4／`scope_expansion` | M1–M13 自治擴張，補充 v5.7 而非全面取代。[來源](../execution_plan/2026-05-20--execution-plan-v5.8.md)；`HISTORICAL_FROZEN_AUTONOMY_TRACK` |
| v5.9 | 2026-05-31 | R5／`priority_shift` | 凍結大部分自治 active-IMPL，改為 Alpha-Edge 證據優先。[來源](../../CHANGELOG.md)；`THESIS_SHIFT_RECORDED` |

證據數量：**16 份獨立方案正文＋v5.9 CHANGELOG 條目＋v5.1 間接引用＝18 節點**。
v1 名稱由 v2 的取代聲明確認；v5.1 僅由 v5.2 引用，未找到獨立正文。
v5.8 檔名是 2026-05-20，正文日期為 2026-05-21，本表採正文並在固定來源保留兩者。

v5.6 → v5.7 明確是 engineering-only；舊 CHANGELOG 引言把它列為 thesis-shift，
與條目正文衝突。本次採正文判定，保留舊 Git blob 以供追溯。
v5.8 **補充** v5.7，v5.9 **凍結大部分實作並重排優先級**；不能把整條鏈一律叫全面取代。
早期方案中的高收益、工期或資本假設都不是本次背書，更不能當作當前投資建議。

## 工程交付如何掛回路線

工程版本以既有交付 ID＋commit／PR 為準；路線版號描述方向，驗證／採用狀態描述證據。

| 分期／交付 | Git 錨點 | 這個錨點能說明什麼 |
|---|---|---|
| R7／Bybit H2 | `52a884d93f774a5f625a7d2db4ebe6e2ec95b23a`，PR200 merge | 本次基線的 ancestor，source 已整合；不證明 Linux／PG／真 venue recovery |
| R7／D1.1 | `4b5b6b0079b2b4614692b7df2e0185f6b4923d45`，feature checkpoint | 本次基線的非 ancestor 候選；不表示完整 D1.1、独立 review、main 採用或 serving 已完成 |
| R8／混合研究架構 | [可攜候選紀錄](../decisions/2026-10-03--r8-hybrid-research-candidate.md) | 歷史需求／候選分工；平台選型及遷移尚未驗收 |

H1/H2、D1.1 是工程單元；AIML V2 是子計畫；TODO／PROGRESS 版號是帳本修訂；
Route-Id 是本歷史命名空間。這些都不能互相當成完整產品版本。
外部平台、IBKR、GUI 和開發 workflow 可用既有交付 ID 記支線，不因新增支線自動增加 R 編號。

## 記錄事件

- **RH-20261003-01／taxonomy_adopted**：Operator 採用 R1–R8 分期與 Git 記錄要求。
  今日回溯補建歷史，而非補造過去的發布；R8 保持候選。
- 新路線、採納、撤回、取代及更正按 [決策規則](../decisions/2026-10-03--route-history-versioning.md)
  追加事件；現行派工及效果授權仍回 TODO 與既有 ADR/AMD。
