---
name: 16-root-principles-checklist
description: 16 條根原則逐條 + 9 條安全不變量 + 硬邊界守護；CC agent 對代碼/設計/計劃做合規審查時使用。
allowed-tools: Read, Grep, Glob
---

# 16 根原則 Checklist（CLAUDE.md Root Principles + DOC-01 項目憲法）

> **優先序**：runtime RiskConfig TOML > Rust schema > `TODO.md` active state / runtime evidence > `README.md` stable surfaces > `CLAUDE.md` operating rules > governance docs > memory > 本 skill
> **衝突時向 PM / operator push back，不單方面執行 skill 內 SOP**

> **S3 上層 drift 防線**：本 skill 16 條根原則為 DOC-01 V2 §5.1-§5.16 的 extract（**真 SSOT 是 `srv/docs/decisions/DOC-01_..._V2.md`，不是 memory**），原文修改後可能漂移，發現不一致以 DOC-01 原文為準。

> **S6 P0/P1/P2 cross-ref**：三層風控定義見 `srv/docs/decisions/EX-01_..._V2.md` §2.1-§2.3；本 skill 引用屬語意重述。

## 何時觸發

- CC 收到「合規審查」「16 條原則檢查」「硬邊界體檢」
- 新 Sprint/Wave 計劃啟動前
- 接觸下列任一面：訂單寫入、風控、Decision Lease、學習平面、Operator 認證、live_reserved
- E2 PR 審查發現可疑硬邊界改動時呼叫此 skill

## 16 根原則速查

| # | 原則 | 關鍵檢查點 | grep 指紋 |
|---|------|-----------|----------|
| 1 | 單一寫入口 | 所有訂單通過唯一執行入口 | `IntentProcessor`, `submit_intent` |
| 2 | 讀寫分離 | GUI/研究只讀；寫入受限可審計可鎖定 | `READ_ONLY_*`, `_authorize_write` |
| 3 | AI 輸出 ≠ 命令 | AI → Decision Lease → 本地復核 → 執行 | `decision_lease`, `acquire_lease`, `_shadow_mode` |
| 4 | 策略不繞風控 | 所有意圖經 Guardian 審批 | `Guardian`, `risk_envelope`, `RiskConfig` |
| 5 | 生存 > 利潤 | 止損優先於盈利 | `hard_stop`, `liquidation_buffer` |
| 6 | 失敗默認收縮 | 不確定時保守 | `fail_closed`, `degrade_to_paper` |
| 7 | 學習 ≠ 改寫 Live | 學習平面與 Live 平面隔離 | `learning.*`, `paper_state` |
| 8 | 交易可解釋 | 每筆交易可重建 | `audit_log`, `trace_id` |
| 9 | 災難保護 | 本地 + 交易所雙重防線 | `local_stop` + `conditional_order` |
| 10 | 認知誠實 | 事實/推斷/假設明確區分 | 報告中三類標記 |
| 11 | Agent 最大自主 | P0/P1 硬邊界內完全自主 | `cognitive_modulator` 不降能力 |
| 12 | 持續進化 | 從交易自動學習 | `outcome_backfill`, `evolution_*` |
| 13 | AI 成本感知 | cost_edge_ratio ≥ 0.8 → 建議關倉 | `cost_edge_ratio`, `attention_tax` |
| 14 | 零外部成本可運行 | L0+L1 基礎運營 | Ollama / 免費搜索 fallback |
| 15 | 多 Agent 協作 | 5 Agent + Conductor 正式對象通信 | `MessageBus`, agent topics |
| 16 | 組合級風險 | 監控關聯曝險、策略重疊 | `portfolio_risk`, correlation matrix |

## 硬邊界（觸碰 = BLOCKER）

`CLAUDE.md` Hard Boundaries 列舉。grep 必查：
```
grep -nE '(execution_state|execution_authority|live_execution_allowed|decision_lease_emitted|max_retries|OPENCLAW_ALLOW_MAINNET|live_reserved|authorization\.json)' <diff>
```

任一新增 / 修改 / 拿掉 fail-closed → 升 BLOCKER；要 Operator 顯式 sign-off。

## DOC-08 §12 安全不變量（9 條）

逐條核對：
1. Pre-trade audit/replay 必開
2. Lease 必在執行前已 acquired
3. 執行回報必落 fills 表
4. 風控降級 → engine 自動止血
5. Authorization 過期/失效 → engine cancel_token shutdown
6. Mainnet 無 OPENCLAW_ALLOW_MAINNET → spawn 拒絕
7. Bybit retCode != 0 → fail-closed 不重試
8. Reconciler 對賬差異 → 自動降級 paper
9. Operator 角色與 live_reserved 缺一即拒

## 認知調製合規（原則 4 + 5 + 11 衍生）

- CognitiveModulator **不可**突破 P0/P1 風控邊界（原則 4）
- 調製只能讓 Agent **更審慎**，不能放寬硬上限（原則 5）
- Agent 能力**永遠完整可用**，不被虛擬約束（能量/積分/內部貨幣）限制（原則 11）

## 雙進程 / 三引擎合規

Rust Engine 降級 L0 時 16 條原則**全部仍成立**：
- 原則 3：AI→Lease→複核→執行 鏈條 L0 仍可走（純規則 fallback）
- 原則 9：本地 + 交易所雙重防線 L0 不依賴 AI
- 原則 14：L0+L1 零外部成本

3E-ARCH（paper/demo/live）：每條原則須在三引擎獨立驗，禁「只驗 paper 就 PASS」。

## AgentTool 訪問權限分類（V3 報告 B.3）

- 只讀：CognitiveModulator / DreamEngine
- 受限寫：OpportunityTracker
- 系統寫：唯一執行入口

新工具未列入此表 = 違反原則 1 + 2。

## 評級規則

- **A 級**：16/16 完全合規 + 硬邊界 0 觸碰
- **B 級**：14-15/16 合規，0 違反，部分項目可觀察修
- **B-/C 級**：≥1 BLOCKER 或 ≥3 部分合規
- **F 級**：硬邊界被改動且未經 Operator sign-off

## 輸出物

```markdown
# CC 合規審計 — <commit> · <date>

評級：A / B / B- / C / F
合規：N/16

## 16 原則逐條
| # | 原則 | 狀態 | 證據 |
|---|---|---|---|
| 1 | ... | ✅/⚠️/❌ | <file:line> |

## 安全不變量（9 條）
| # | 不變量 | 狀態 | 證據 |

## 硬邊界
（被觸碰列出，否則「無」）

## 違規清單 + 建議
判定：Approve / Conditional / Reject
```

## 反模式

- 「緊急」為由跳過原則 4/5
- 引用已棄用 DOC（查 DEPRECATED.md）
- 三引擎只驗一個就 PASS
- 「自主提升」實為突破 P1 上限（混淆原則 11 與「能力擴張」）
- AgentTool 新增未登記訪問權限類別
