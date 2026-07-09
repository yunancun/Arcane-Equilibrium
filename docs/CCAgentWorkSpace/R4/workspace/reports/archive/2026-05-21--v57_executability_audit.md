# v5.7 Dispatch-Safe Patch 執行性審核 — R4 視角
**日期**：2026-05-21
**Verdict**：HOLD（必須先補 ADR 編號衝突 + ADR-0006 amendment 文件 + AMD 編號 + docs index）
**One-line summary**：v5.7 邏輯端 6/6 reviewer 修正合格，但 8 個執行性 doc/編號漂移其中 3 個 must-fix（ADR-0028/0029 已被 2026-05-21 ADR 佔用 → 提案 ADR-0028/0029/0030 全衝突；ADR-0006 amendment 無對應分離文件；TODO.md Hard precondition「路線敲定前不啟動任何 V101/V102 / dispatch wave」與 v5.7 「Sprint 1A dispatch ready」直接衝突），Sprint 1A 派 PA 前必須先處理。

## 0. 文檔 / Reference 完整度

v5.7 §13 reference 核驗：

| Reference | 路徑 | 狀態 | 備註 |
|---|---|---|---|
| v5.6 superseded | `srv/2026-05-20--execution-plan-v5.6.md` | EXISTS | 同 v5.7 在 `srv/` 根（同樣 docs/ placement 違規） |
| V101/V102 spec | `docs/execution_plan/2026-05-20--v101_v102_track_attribution_migration_spec.md` | EXISTS | spec v3 已標 "real V### PA dispatch 時 final 鎖定，預期 V101/V102 但可能順延 V103/V104"；v5.7 §3 寫「V101 已被 reserve」與 spec v3 自身條件式描述語意對齊但邏輯有縫 |
| AMD-01 to AMD-05 | （無編號路徑） | MISSING-NAMING | 實際 AMD 編號體系是 `AMD-YYYY-MM-DD-NN`（檔案系 `2026-05-20--AMD-2026-05-20-01..05`），不存在 `AMD-01..05`。v5.7 reference 命名違反 governance 編號規範，CC 接手會找不到 |
| Round 15 reviewer audit | （無路徑） | MISSING | 沒有「2026-05-21--round_15_reviewer_audit*.md」或同等 audit log 路徑；6/6 corrections 來源無可追溯 |
| Bybit Earn tiered APR | （Round 15 web search） | UNTRACKED-EVIDENCE | 純 reviewer 對話無 evidence file；Earn APR 數值來自 web search snapshot 沒入庫 |
| market.liquidations writer | `rust/openclaw_engine/src/database/market_writer.rs` | EXISTS（且活躍寫入） | 路徑正確 |

額外缺失 reference：
- **v5.7 §11**「14 hard problems from reviewer rounds 12-15」— **v5.6 + v5.5 grep 全部找不到 round 12-14 編號**；無 audit trail，數字可能是叙述近似而非實際 round 編號
- **v5.7 主檔位置**：`srv/2026-05-20--execution-plan-v5.7.md`（root），**違反 docs/README.md §強制規則第 1 條** 「文件必须放到对应分类目录，不允许直接扔在 `docs/` 根目录」（即使在 srv/ 不在 docs/，但 governance doc 應放 `docs/execution_plan/`）
- **v5.7 docs/README.md index 0 條**：v5.0/v5.2-v5.7 全系列 docs/README.md 底部 index **無條目**

## 0.5 ADR / AMD 編號連續性

ADR 編號分配實況（grep `srv/docs/adr/` 全部 .md）：

| ADR | 已分配 | 狀態 | 來源 |
|---|---|---|---|
| ADR-0027 | ai-plan-mode-time-based-budgeting | 已 land | active |
| **ADR-0028** | **close-maker-fallback-reason-dead-enum-reservation** | **Accepted-pending-commit（Date 2026-05-21）** | TODO §12.4 C 批 closure；FA SPEC-1 出單 |
| **ADR-0029** | **market.public_trades + market.orderbook_l2_snapshot Storage Policy** | **Proposed（Date 2026-05-21）** | FA EVID-1 出單 |
| ADR-0030 | （NUMBER FREE） | 未分配 | — |

**v5.7 §11 提案**：
- ADR-0028 (proposed)：Copy Trading evidence-gated → **CONFLICT**（0028 已被 close-maker dead enum 佔用）
- ADR-0029 (proposed)：Framework expansion → **CONFLICT**（0029 已被 trade tape storage policy 佔用）
- ADR-0030 (proposed)：Bybit Earn Guardian policy → NUMBER FREE，可用但須補 ADR 文件

**修法建議**：v5.7 §11 + §12 三個 ADR 提案號順移為 **0030 / 0031 / 0032**（PA 接手 dispatch 前 final 鎖定）。

**ADR-0006 amendment**（v5.7 §12 第一條）：
- 現有 `docs/adr/0006-bybit-only-exchange.md` 內文「Binance is retained only as a hypothetical long-term option」**不含 v5.7 提案的 amendment 內容**（Binance market data approved + Binance trading defer Y2 + DEX/Hyperliquid NOT approved + D12）
- **需新建 ADR-0033（或同層 amendment 文件）** 寫 ADR-0006 amendment 內容；v5.7 §12「ADR-0006 amendment」描述存在但**對應文件不存在** = doc drift

**ADR 命名漂移**：v5.7 §12 寫「ADR-0024-lite」— 實際 ADR-0024 檔名 `0024-cowork-subscription-operator-assistant.md` **不含 "lite" 後綴**；v5.6 §11 同樣寫 ADR-0024-lite。應**統一為 ADR-0024**（或於該 ADR 補 "lite" 命名 amendment）。

**AMD 編號漂移**：
- v5.7 §13 + v5.6 §15「AMD-01 through AMD-05」**不是現有 AMD 編號體系**（`AMD-YYYY-MM-DD-NN`，例 `AMD-2026-05-15-01` / `AMD-2026-05-20-01..05`）；可能指 2026-05-20 5 個 AMD（01..05），但需顯式重命名 reference 為 `AMD-2026-05-20-01..05`
- AMD-2026-05-20-05 已 retract（stream 3 IP sale）— 與 v5.7 thesis「Self-Trading primary + Copy Trading evidence-gated」一致，但 v5.7 §0/§11 thesis 無 cross-link 到 AMD-2026-05-20-05 retract

## 0.6 Migration 編號衝突

repo `sql/migrations/` head = **V098**（V099 / V100 / V101 / V102 / V103 / V104 全 NUMBER FREE）

| V### | TODO active state | v5.7 §3 規劃 | 衝突分析 |
|---|---|---|---|
| V097 | apply 待對齊 Linux DB（drift = 2 missing） | V097 catch-up Phase 0 | 一致 |
| V098 | apply 待 | V098 catch-up Phase 0 | 一致 |
| V099 | **TODO §10 P0-LG-3** 寫「V094 已被 W-AUDIT-8c 佔用 → V099/V100」reserved for LG-3 | v5.7 §3 寫「V099-V100 reserved for LG-3 + W-AUDIT-8a 殘留」 | 一致（v5.7 §3 cite TODO 正確） |
| V100 | 同 V099 reserved | 同 | 一致 |
| V101 | V101/V102 spec v3 「**預期** V101/V102 但若殘留多可能順延 V103/V104」 | v5.7 §3 寫「Track schema 12-table attribution」reserved | 一致（但 v5.7 §3 寫 "V101 already reserved" 略強，spec v3 自己是條件式 "預期 V101"） |
| V102 | 同 V101 | 同 | 一致 |
| V103 | NUMBER FREE | v5.7 placeholder：hypotheses + hypothesis_preregistration | FREE，可用 |
| V104 | NUMBER FREE | v5.7 placeholder：`trading.fills.track` column add | **CONFLICT WARNING**：v5.7 §3 自己標「subset of V101 work; PA may consolidate」— `trading.fills.track` 已在 V101 spec v3 §1 「12 個既有表 ADD COLUMN track」明確 in-scope，V104 placeholder **重複** V101 工作 |

**修法建議**：v5.7 §3 V104 應**收回**或顯式標為「依 V101 spec scope 決定，PA dispatch 時若 V101 spec consolidate `trading.fills.track` 則 V104 退號」。

## 1. Top 3 執行性風險（排序）

### Risk 1：ADR-0028 / 0029 編號完全衝突 + ADR-0006 amendment 無對應文件
- 嚴重度：**CRITICAL**
- 位置：v5.7 §11 + §12（ADR 提案表）
- 描述：
  - v5.7 §11 提案 ADR-0028 / 0029 / 0030；ADR-0028 已被 close-maker dead enum 佔用（2026-05-21 Accepted-pending-commit），ADR-0029 已被 market.public_trades storage 佔用（2026-05-21 Proposed）
  - v5.7 §12 「ADR-0006 amendment」描述存在但 `docs/adr/0006-bybit-only-exchange.md` 文件內容**不含**該 amendment（Binance market data approved + DEX NOT approved + D12）；沒有獨立 amendment 文件
- 為何屬「執行性」：v5.7 邏輯（Copy Trading + Framework expansion + Earn）已通過 15 round audit，**問題在編號分配 + 文件落地**，不是邏輯
- Must-fix 建議：
  1. v5.7 §11 三 ADR 順移為 **ADR-0030/0031/0032**（或 PA dispatch 時 final 鎖定 0030+）
  2. ADR-0033（或 ADR-0006-amendment-01）新建 ADR-0006 Binance amendment 文件
  3. v5.7 §12 三 ADR 號同步順移；改 "ADR-0006 amendment" 為「見 ADR-0033」

### Risk 2：TODO Hard precondition 直接禁 dispatch；v5.7 「Sprint 1A dispatch ready」與 TODO §-0 衝突
- 嚴重度：**CRITICAL**
- 位置：v5.7 §11 + §13（Sprint 1A ready for PA dispatch upon operator final approval）vs TODO.md L42
- 描述：
  - TODO.md L42 寫「**Hard precondition**：路線敲定前不啟動任何 V101 / V102 / Track A/B / dispatch wave。當前 in-flight active 工作見 §3 / §10 / §11.3 / §12」
  - TODO.md §-0 寫「v5.2-v5.6 untracked，operator 隔壁敲定後重填本區」
  - v5.7 主檔 untracked（`git status` 未進入 working tree）也未進 TODO §-0
  - v5.7 §11「Sprint 1A ready for PA dispatch upon operator final approval」**忽視** TODO Hard precondition 的「路線敲定」步驟
- 為何屬「執行性」：v5.7 派 Sprint 1A 前必先讓 operator 在 TODO §-0 填入路線、解除 Hard precondition，否則 PA 派 V103/V104 + 其他工作會撞 TODO active state
- Must-fix 建議：
  1. operator 在 TODO §-0 確認 v5.7 為當前路線 + 解除 V101/V102 Hard precondition
  2. v5.7 §11/§13 加一行「Operator 須先在 TODO §-0 填入 v5.7 為路線後解除 Hard precondition」
  3. v5.7 進 docs/execution_plan/ 並進 git tree（解除 untracked 狀態）+ 進 docs/README.md index

### Risk 3：AMD 命名漂移 + reviewer round 12-14 audit trail 不可追溯 + docs/README.md index 缺 v5.x 全系列
- 嚴重度：**HIGH**
- 位置：v5.7 §13 + §11
- 描述：
  - v5.7 §13 「AMD-01 through AMD-05」與真實 AMD 編號 `AMD-YYYY-MM-DD-NN` 不對齊；2026-05-20 5 個 AMD 實際是 `AMD-2026-05-20-01..05`
  - v5.7 §11「14 hard problems from reviewer rounds 12-15 addressed」— grep v5.6 + v5.5 找不到 round 12-14 編號；6/6 corrections 已 verify but「14 hard problems」**無可追溯 source**
  - docs/README.md 整 1100+ 行 index 對 v5.x 全系列 **0 條目**；v5.0 / v5.2 / v5.3 / v5.4 / v5.5 / v5.6 / v5.7 全缺
  - AMD-2026-05-20-05 已 retract stream 3 IP sale；v5.7 thesis 雖一致但無 cross-link
- 為何屬「執行性」：CC 接手 v5.7 找 AMD reference 會迷路；docs/README.md 加 v5.7 條目是 R4 governance 必修
- Must-fix 建議：
  1. v5.7 §13 reference 改寫「AMD-2026-05-20-01..05」全名（去掉 AMD-01..05 短號）
  2. v5.7 §11 「14 hard problems」改為「6 hard problems from reviewer round 15」或明確指出 round 12-14 audit log 路徑（若不存在就退到 6 problems）
  3. docs/README.md 底部 index 補 v5.0/v5.2-v5.7 全系列 + V101/V102 spec 條目（v5.0~v5.6 過去也漏）

## 2. Hours sanity check（文檔工時 vs estimate）

| Section | v5.6 estimate | v5.7 estimate | 變化 | sanity |
|---|---|---|---|---|
| §4 Bybit Earn | 10 hr | **45 hr**（API 15 + Governance 20 + Audit 10） | +35 hr | reviewer §2 + §6 fix；數字合理 |
| §5 Macro/On-chain | 70-110 hr（production trigger） | 70-95 hr（counterfactual only + A/B framework） | -15 hr | counterfactual only 應更少不只 -15 hr；可能略偏低 |
| §6 Liquidation writer | "NEW" 隱含 ~15-20 hr | HEALTHCHECK existing | -15-20 hr | grep verified 為真，數字合理 |
| §8 Sprint 1A+1B 合計 | 100-130 hr | 110-150 hr | +10-20 hr | Sprint 1 split 加治理 + Earn governance；數字合理 |
| §9 39-week 全週期 total | 1,180-1,570 hr | 1,190-1,590 hr | +10-20 hr | 「reallocated」描述對；總增 +10-20 hr 與 §4 (+35) - §5 (-15) - §6 (-15) ~= 同數，數字內部一致 |

整體 hours 內部一致；唯一 sanity flag = §5 Macro/On-chain counterfactual only 比 v5.6 production trigger 整合只少 15-25 hr，counterfactual 是純 logger 應更少，疑略偏高（但容忍範圍內，不阻派發）。

## 3. 未識別的依賴 / 阻塞（文檔交叉引用）

1. **AMD-2026-05-15-01 → Stage 1 Demo-only**（v5.7 §12 提 Stage transitions per AMD-2026-05-15-01 unchanged）— 一致；但 v5.7 §12 描述「全部 Stage 透過 AMD-2026-05-15-01」，**未交叉引用 PM Freeze（TODO §0.0）**：Paper 不是 active promotion lane。v5.7 sensor + counterfactual 不會踩這條，但 Sprint 4 「Top-1 live + Top-2 build」**應引用** TODO §0.0 Stage 0R → Stage 1 Demo lane
2. **V094 close_maker_audit dependency on V095 (ADR-0028)**：v5.7 §3 規劃 V103/V104 不踩 V094/V095，無實質衝突；但 V094 schema dead enum reservation（ADR-0028 = close-maker）若 PA 之後再做 schema 變更，v5.7 §3 需注意 `close_maker_fallback_reason` enum 不能被 v5.7 V103/V104 動到
3. **V101 spec v3 Phase 0 V097/V098 catch-up dependency**：v5.7 §3 + §8 Sprint 1A 都列 V097/V098 catch-up；spec v3 §2.1 寫「Linux DB head = V096, repo head = V098, drift = 2」— 順序一致，但 v5.7 應 cross-link V101 spec v3 §2 Phase 0 sequence（v5.7 §3 / §8 缺對 spec v3 §2.1 verbose sequence 的 cite）
4. **funding_arb 治理 + ADR-0018 deprecation watch**：v5.7 不提 funding_arb；TODO §-0/§3 也未顯式列入 v5.7 scope。若 Sprint 7-8 「Top-4 + funding short-only」候選包含 funding_arb shadow，需 cross-link ADR-0018（funding-arb-v2-deprecation-watch）

## 4. 對 PA+FA 匯總的必收 top 3

1. **ADR 編號 0028/0029 衝突 + ADR-0030 順移到 0030/0031/0032**（Risk 1）— PA dispatch Sprint 1A 前必須先讓 operator 簽 ADR 順移；FA 應同步 ADR-0028 close-maker amendment 文件
2. **TODO §-0 Hard precondition 解除 + v5.7 主檔入 git tree + 進 docs/README.md index**（Risk 2）— PA 應協調 operator 在 TODO §-0 填入 v5.7 為路線、解除 V101/V102 Hard precondition；R4 應同步 docs/README.md index 補 v5.x 全系列
3. **ADR-0006 amendment 文件落地 + AMD 編號規範化**（Risk 3）— PA 應新建 ADR-0033（或 ADR-0006-amendment-01）；FA 應再驗 reviewer round 15 audit log 是否存在（若 round 12-14 audit 不存在 v5.7 §11 應降為「6 hard problems」）

## 5. Sprint 1A 派發前 must-fix（必須先補的文檔 / 編號）

1. ADR 號順移：v5.7 §11/§12 ADR-0028/0029/0030 → **ADR-0030/0031/0032**（PA dispatch 時 final 鎖定）
2. ADR-0033 新建（或 ADR-0006-amendment-01）：ADR-0006 Binance market data + DEX NOT approved + D12 amendment
3. operator 在 TODO §-0 填入 v5.7 為路線 + 解除 V101/V102 Hard precondition
4. v5.7 主檔搬 `docs/execution_plan/2026-05-20--execution-plan-v5.7.md`（從 `srv/` 根遷移）+ 進 git tree
5. v5.7 §13 reference 改 AMD-01..05 → AMD-2026-05-20-01..05 + 標 AMD-2026-05-20-05 retract
6. v5.7 §11 「14 hard problems」改 「6 hard problems」或補 round 12-14 audit log path
7. docs/README.md 底部 index 補 v5.0/v5.2-v5.7 全系列 + V101/V102 spec + 兩個新 ADR
8. v5.7 §3 V104 placeholder 收回或標「依 V101 spec consolidate 與否而定」

## 6. Sprint 1B-3 should-fix

- v5.7 §3 cross-link V101 spec v3 §2.1 Phase 0 catch-up verbose sequence
- v5.7 §12 cross-link TODO §0.0 PM Freeze Demo-only Stage 1 lane（避免 Sprint 4 「Top-1 live」誤踩 paper lane）
- v5.7 §10 cross-link ADR-0018 funding-arb-v2-deprecation-watch（若 Top-4 funding short 候選和 funding_arb 重疊）
- v5.7 §11 cross-link AMD-2026-05-20-05 retract（stream 3 IP sale）以說明 Self-Trading primary thesis 一致性
- v5.7 §6 grep verified market.liquidations writer 應加 grep timestamp + commit SHA 引用（避免 «已驗 existing» 過期）

## 7. 可優化 / 拆分 / 並行

- v5.7 §8 Sprint 1A 60-80 hr + 1B 50-70 hr **可並行軌**：1A governance + migration（V097/V098 catch-up + V103/V104 placeholder）是序列依賴的；1A sensor build（options recorder + Tokenomist + macro feed + Binance WS NEW + Earn API read-only）可與 1A migration 並行 → Sprint 1A 內部拆 1A-gov（governance + migration，~25-30 hr 序列）+ 1A-sensors（external API + reader，~35-50 hr 並行）
- ADR 順移（Risk 1）+ ADR-0006 amendment（Risk 1）+ v5.7 主檔入 git tree（Risk 2）+ docs/README.md index 補 v5.x（Risk 3）— 4 條 must-fix **彼此無依賴**，可一次 commit 並行修
- v5.7 §11 「reviewer round 12-15」audit trail 確認 — 若實際只有 round 15 = R4 直接刪「14 hard problems from rounds 12-15」改「6 hard problems from round 15」即可；若 round 12-14 存在則需 FA 另開 audit log 路徑審計（單獨 PR）

---

**Verdict 重申**：HOLD — Sprint 1A 派發前**必須先處理** 8 個 must-fix（Risk 1 三條 + Risk 2 兩條 + Risk 3 三條），其中 Risk 1（ADR 編號衝突）+ Risk 2（TODO Hard precondition）為 CRITICAL 阻塞；Risk 3（AMD 編號 + index）為 HIGH 但不阻塞派 PA（PA 可同步補）。v5.7 邏輯內容（thesis + Y1/Y2 income + Sprint 1A/1B split + Earn governance + counterfactual logging）**全部合格**；問題集中於編號 / 文件落地 / index。建議 operator 一次 commit 並行修完 8 條 must-fix 後再簽 PA dispatch。
