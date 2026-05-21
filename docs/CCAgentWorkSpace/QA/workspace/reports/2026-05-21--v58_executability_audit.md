# v5.8 QA 執行性審核 — 13-Module Autonomy Track

**日期**：2026-05-21
**審核人**：QA (Quality Assurance)
**Verdict**：**GO-WITH-CONDITIONS**
**One-liner**：v5.8 13-module 設計與 operator directive 對齊，但 M1 Lease Tier 5 層 vs AMD-01 Stage 0R-4 對齊矩陣未明寫；7d 0 CRITICAL 灰度在 13 module 啟用時觸發點與計時器歸零規則未定；雙進程 E2E 對 13 module 新增 V105-V116 schema 覆蓋 SOP 不明；M9 A/B variant promote 是否走完整 Stage 0R→4 漏寫；Sprint 1A 派發前必修 4 項，β-ε should-fix 5 項。

---

## 0. Stage gate vs 13 module 對齊矩陣

對 v5.7 audit 主表的延伸，新增「v5.8 module 是否觸發 Stage 流程 / 是否破壞 Stage 出口條件」評估：

| Module | 是否引入新 Stage 流程 | 對 AMD-2026-05-15-01 Stage 0R/1/2/3/4 對齊 | QA 清晰度 |
|---|---|---|---|
| **M1 Lease Tier** | 是（Tier 0-4 五層） | **未對齊**：M1 Tier 命名與 AMD-01 Stage 0R-4 名稱衝突（Tier 0 ≠ Stage 0 但讀者必混淆）；M1 Tier 2 auto-execution Y2 啟用是否要 per-strategy 重走 Stage 0R→4 未寫 | **MISSING** |
| **M2 Overlay 5-state** | 是（COUNTERFACTUAL_ONLY/SHADOW_TRIGGER/ADVISORY_TRIGGER/PRODUCTION_TRIGGER/DISABLED_AUTO） | PARTIAL：5-state 與 Stage gate **平行**而非嵌套；PRODUCTION_TRIGGER 是否要走 Stage 0R replay preflight 沒寫 | **PARTIAL** |
| **M3 Health** | 否（HEALTH_NORMAL/WARN/DEGRADED/CRITICAL/CATASTROPHIC 是 runtime 響應） | CLEAR：與 Stage 正交 | CLEAR |
| **M4 Hypothesis discovery** | 否（DRAFT 不走 Stage；approved DRAFT 進 Alpha Tournament 才開始 Stage 流程） | CLEAR：「Bot CANNOT promote」邊界明確 | CLEAR |
| **M5 Online learning** | 否（interface stub） | N/A Y1 | CLEAR |
| **M6 Reward weight** | 否（Allocator 權重 tune；不啟動新策略） | CLEAR | CLEAR |
| **M7 Decay STAGE_DEMOTE_PROPOSED → STAGE_DEMOTED** | 是（生命週期狀態） | **未對齊**：M7 用「STAGE_」前綴但與 AMD-01 Stage 0R/1-4 **方向相反**（M7 是 demote / AMD-01 是 promote）；STAGE_DEMOTED 在 AMD-01 Stage 0R-4 表中沒對應入口；rollback 路徑（demoted → Stage 0 fall-back? → 14d review）沒寫 | **MISSING** |
| **M8 Anomaly** | 否（Y1 read-only / Y2 active trigger 入 M3） | CLEAR | CLEAR |
| **M9 A/B test** | **隱含是**（variant 「promotion」需走 Stage gate） | **MISSING**：§M9「test cannot promote variant to live without operator approval + Stage gate」一句帶過；variant **同策略不同參數**是否一次走完整 Stage 0R→4，還是同一策略 Stage 4 內做 variant 灰度，沒定 | **MISSING** |
| **M10 Discovery Tier A-E** | 是（Tier B-E 觸發新 strategy / venue） | PARTIAL：「activation initiates phased IMPL」沒寫 IMPL 完是否再走 Stage 0R→4 流程；Tier C 新 symbol 是 strategy variant 還是新策略沒明確 | **PARTIAL** |
| **M11 Nightly replay** | 否（連續 validation，不是 Stage gate） | CLEAR；但見 §0.6 與 Stage 0R replay preflight 重複/互補需澄清 | CLEAR |
| **M12 Order routing** | 否（執行層；不影響 Stage） | CLEAR | CLEAR |
| **M13 AssetClass/Venue** | 是（新 venue 必走 Stage 0R replay 用 Binance 數據） | PARTIAL：§M13 已寫「Y2: Binance perp trade enable with Stage 0R replay using Binance data」對齊正確；但 Bybit Earn 在 Y1 已 live 是否補 Stage 0R 沒寫 | PARTIAL |

**核心缺**（3 項）：
1. M1 Lease Tier 0-4 vs AMD-01 Stage 0R-4 命名碰撞 + 嵌套關係
2. M7 STAGE_DEMOTE_PROPOSED/STAGE_DEMOTED 與 AMD-01 Stage 命名同前綴但語意反向
3. M9 variant promote 走 Stage 完整性沒定

---

## 0.5 灰度 7 天 0 CRITICAL 在 13 module 啟用時可行性

v5.7 audit §0.5 已指 4 new sensor 7d 灰度缺；v5.8 額外問題：

| 維度 | v5.8 module 啟用對 7d 0 CRITICAL 影響 | 狀態 |
|---|---|---|
| **M1 Tier 2 auto-execution 首次啟用** | Y2 Q2 預期啟用；單次 auto-approval 算 0 CRITICAL 還是「異常事件」？M1 §「auto-approval emits Slack/email」非 CRITICAL 級，但首 7d 觀察期沒寫 | **MISSING** |
| **M2 PRODUCTION_TRIGGER 首次轉態** | Y2 Q1 enable 後第一個 overlay-enabled trade 是否觸發 7d 觀察期？Auto-disable 條件「30d Sharpe<0」遠超 7d，二者時序未明 | **MISSING** |
| **M3 HEALTH_DEGRADED 自動觸發** | 自動 throttle 算 CRITICAL（系統行為改變）還是 WARNING（健康降級但非失敗）？v5.8 沒定 | **MISSING** |
| **M7 STAGE_DEMOTED 自動觸發** | M1 Tier 1 auto-demote 後 50% 縮位算事件？M7 §「review window 14d」與 7d 0 CRITICAL 計時重疊或獨立未寫 | **MISSING** |
| **M9 A/B test 啟動** | Variant 50/25/25 切量是「Stage 4 內小變化」還是「新 Stage 0R-4 流程」決定 7d 觀察期是否歸零；無 SOP | **MISSING** |
| **M11 Nightly replay 高 divergence flag** | 「High-divergence flag → M3 HEALTH_WARN」會被當成 WARNING；連續 7 天 flag 是否升 CRITICAL 沒寫 | **PARTIAL** |
| **M13 Binance perp trade enable** | Y2 新 venue 首日是否要 7d 0 CRITICAL 觀察期？§M13 寫 Stage 0R replay 但沒寫 7d 灰度 | **MISSING** |

**核心結論**：v5.8 引入 7 種「自動行為改變」事件，這些事件在 7d 0 CRITICAL 計時器中算什麼級別沒定。建議在 Sprint 1A-β ADR-0034 / 0038 補入「事件 → 嚴重度」對照表，明確：
- M1 auto-approve：INFO（已 audit）
- M2 auto-disable：WARNING（保守降級不算 CRITICAL）
- M2 auto-enable：CRITICAL-eligible（升級行為，連 7d 觀察期歸零）
- M3 HEALTH_DEGRADED：WARNING
- M3 HEALTH_CRITICAL：CRITICAL
- M7 auto-demote：WARNING
- M9 variant 切量 >25%：觸發新 7d 觀察期
- M13 新 venue 首交易：觸發 21d full Stage 3 等價觀察期

---

## 0.6 雙進程 E2E (Python+Rust) 對 13 module 覆蓋

v5.8 §9 schema 新增 V105-V116（共 12 個遷移）。雙進程 E2E 必驗：

| Module | Rust-side IPC schema 變動 | Python ↔ Rust 1e-4 容差驗收 | QA 覆蓋 |
|---|---|---|---|
| **M1** Lease Tier | **是**：Decision Lease IPC 新增 tier 欄位 | Tier 自動性 routing 必驗 Rust 端決策 = Python 影子 | **MISSING IPC schema** |
| **M2** Overlay state | 否（state 邏輯 Python-side allocator） | N/A | CLEAR |
| **M3** Health 5-state | **是**：HEALTH_DEGRADED 觸發 Rust 端 throttle 必走 IPC | throttle latency 雙端 metric 對齊 | **MISSING IPC schema** |
| **M4** Hypothesis miner | 否（Python-only research path） | N/A | CLEAR |
| **M5** Online learning | 否（Y1 stub） | N/A | CLEAR |
| **M6** Reward weight | 否（Allocator monthly Python-only） | N/A | CLEAR |
| **M7** Decay state machine | **是**：STAGE_DEMOTED 觸發 Rust 端 50% 縮位 IPC | 縮位 fill ratio 雙端對齊 | **MISSING IPC schema** |
| **M8** Anomaly | 否 Y1 read-only / Y2 觸發入 M3 | N/A Y1 | CLEAR Y1 |
| **M9** A/B test | **是**：trial_id hash 分配走 Rust（執行端） | variant 命中率分布 ±1% | **MISSING IPC schema** |
| **M10** Discovery Tier | 否 Y1（Tier A 已 Python cron） | N/A Y1 | CLEAR Y1 |
| **M11** Nightly replay | 否（replay engine 獨立進程 vs Rust prod） | replay engine 輸出 vs prod 對齊已是 M11 核心 | CLEAR |
| **M12** Order routing | **是**：maker-vs-taker 決策 Rust-side | routing decision 雙端必對齊 | **MISSING IPC schema** |
| **M13** AssetClass/Venue | **是**：venue routing Rust-side | 跨 venue 訂單必驗 IPC type | **MISSING IPC schema** |

**核心缺**：M1/M3/M7/M9/M12/M13 都涉及 Rust-side IPC schema 變動，v5.8 §M1-M13 spec 沒列「IPC message type 增量」清單。Sprint 1A-β/γ DESIGN 必補。

**新增 12 個 schema migration（V105-V116）的 PG dry-run requirement**：
- v5.8 §10 風險 1「Schema sprawl」已標識
- 但無「每個 V### 必走 ssh trade-core empirical query」SOP 落到 ε 整合 audit
- QA 建議：Sprint 1A-ε 必跑 12 個 V dry-run（per-migration twice idempotency test）

---

## 1. Top 3 風險（v5.8 新增；v5.7 §1 三 risk 不重複）

### Risk A：M1 Lease Tier 5 層命名與 AMD-2026-05-15-01 Stage 0R-4 衝突

- **嚴重度**：CRITICAL
- **位置**：v5.8 §M1（line 64-85）+ AMD-2026-05-15-01 §1 Stage 表
- **描述**：v5.8 M1 用「Tier 0-4」，AMD-01 用「Stage 0/0R/1/2/3/4」。讀者必混淆：
  - Tier 0 (per-fill autonomous) 與 Stage 0 (Shadow baseline) 是兩件事
  - Tier 2 auto-execution Y2 啟用對 per-strategy 是否要重走 Stage 0R→4 沒寫
  - 「30d stable」是 Tier 1 進 Tier 2 條件，但與 Stage 1 (7d) / Stage 2 (14d) / Stage 3 (21d) 對應到 Stage 幾沒寫
- **為何「執行性」**：M1 IMPL Sprint 4 + Sprint 7-8 時，E1 sub-agent 不知道 Tier 升級是否要先過 Stage gate
- **Must-fix 建議**：
  1. 改名「Lease Tier」為「Lease Authority Level (LAL 0-4)」（避免 Tier 與 Stage / Stage 0R 字面衝突）
  2. M1 §加表「LAL n 升級條件 ↔ AMD-01 Stage n 對齊」：例如 LAL 1 → LAL 2 條件 = 該策略已過 Stage 4 + 90d stable + 30 Advisory approvals
  3. ADR-0034 必含此對齊矩陣
- **Owner**：PA + CC

### Risk B：M7 STAGE_DEMOTE_PROPOSED / STAGE_DEMOTED 與 AMD-01 Stage 命名同前綴反向

- **嚴重度**：HIGH
- **位置**：v5.8 §M7（line 254-277）
- **描述**：M7 state machine 用「STAGE_LIVE / DECAY_DETECTED / STAGE_DEMOTE_PROPOSED / STAGE_DEMOTED」，但：
  - AMD-01「Stage」是 promote 方向（0R→1→2→3→4）
  - M7「STAGE_DEMOTED」是反向（從 LIVE 退回）
  - rollback 路徑「DEMOTED → 50%」沒寫退回 AMD-01 哪個 Stage（Stage 3 21d 全 demo？Stage 1 7d demo micro-canary？或就保持 50% live 14d review？）
  - 14d review window 與 AMD-01 Stage 2 14d 同數字易混淆
- **為何「執行性」**：M7 Sprint 8 IMPL 時，E1 不知道 demoted 50% size 是 demo 還是 live；違反「demo only 是 alpha-bearing 評價路徑」
- **Must-fix 建議**：
  1. M7 改名「DECAY_PROPOSED / DECAY_ENFORCED」（避免 STAGE_ 前綴）
  2. 寫明 DECAY_ENFORCED = live 50% size + 14d 持續觀察（不退回 demo，否則學習數據 paper 化）；或寫明 demo fall-back 14d 路徑明確
  3. ADR（v5.8 未列 M7 ADR；建議補 ADR-0034b 或合入 0034）
- **Owner**：PA + QC（demoted state 統計設計）+ FA

### Risk C：M9 A/B variant promote 是否走完整 Stage 0R→4 未定

- **嚴重度**：HIGH
- **位置**：v5.8 §M9（line 319-355）
- **描述**：§M9「test cannot promote variant to live without operator approval + Stage gate」一句太抽象：
  - Variant 是「同策略不同參數」還是「新策略」？
  - 若同策略：variant promote 是 Stage 4 內參數熱重載（不重走 Stage）還是要 Stage 0R replay preflight 重來？
  - mSPRT 早期停止 efficacy → 是否直接套用 main，還是觸發 Stage 1 demo 7d 重驗？
  - 50/25/25 切量本身算「Stage 4 內已 live 變化」還是「new sub-Stage」？
- **為何「執行性」**：M9 IMPL Sprint 4 read-only + Sprint 7-8 operator-approved manual A/B + Y2 auto-gate，每階段沒明確 Stage 路徑，E1 + QC 不知道怎麼設計 acceptance threshold
- **Must-fix 建議**：
  1. §M9 加表「variant 類型 → Stage 路徑」：
     - parameter variant 在 Stage 4 內 25% 灰度 7d → 採納（不重走 Stage）
     - sizing variant > +20% → 觸發 Stage 1 demo 7d 重驗
     - trigger variant → 改變 entry 語意 = 觸發 Stage 0R replay preflight + Stage 1 7d 完整
     - overlay variant → 走 M2 overlay state machine（不走主策略 Stage）
  2. ADR-0037 必含此分類
- **Owner**：QC + PA

---

## 2. 5-gate live boundary 在 Y2/Y3 module 啟用

v5.7 audit §1 Risk 2 已指 Earn vs 5-gate 不明；v5.8 額外問題：

| Module | Y2/Y3 啟用時 5-gate 是否仍 hard | 風險 |
|---|---|---|
| **M1 Tier 2 auto-execution** | **必須仍 hard** | auto-approve 不能繞 `live_reserved` / `OPENCLAW_ALLOW_MAINNET=1` / `authorization.json` 簽名；v5.8 §M1 沒明寫；建議 ADR-0034 加「Tier 2 auto-execution 不替代 5-gate；每次 auto-approval 走完整 5-gate 重檢」 |
| **M2 PRODUCTION_TRIGGER auto-enable** | **必須仍 hard** | overlay enable 改變策略行為 = 等價策略參數變更；不可繞 Operator role auth；建議 ADR-0035（v5.8 §8 ADR-0035 是 M5 online learning；M2 沒分配 ADR；建議補 ADR-0034c 或編號重整）|
| **M3 HEALTH_DEGRADED auto-throttle** | **降級方向不繞 gate**（只剩讀 / 縮位），但**升回 NORMAL** 必驗 5-gate hard | v5.8 §M3 沒寫 recovery / auto-restore 路徑 5-gate 檢核 |
| **M9 variant Stage 4 25% 灰度** | **必須仍 hard** | variant 是 live 行為改變；不可繞 5-gate；建議 ADR-0037 加 |
| **M12 Cross-venue routing Y2** | **必須仍 hard + 多一層 venue 認證** | Binance perp trade authority 是新 venue secret slot；v5.8 §M12 沒寫「跨 venue 5-gate 是否要每 venue 各一份 authorization.json」 |
| **M13 Binance perp trade Y2 enable** | **必須仍 hard + 新 ADR-0040** | Bybit-only 5-gate 不夠；ADR-0040 必補「multi-venue 5-gate spec」（per-venue mainnet flag、per-venue secret、per-venue authorization）|

**核心結論**：v5.8 5 個 module 涉及 live boundary 但 ADR 安排：
- ADR-0034 M1：必補「5-gate hard」段
- ADR-0035 M5：無 live boundary 影響（interface stub）
- ADR-0036 M8：Y2 active trigger 入 M3，需補
- ADR-0037 M9：必補「variant 5-gate hard」段
- ADR-0038 M11：無 live boundary 影響
- ADR-0039 M12：必補「cross-venue 5-gate 設計」
- ADR-0040 M13：必補「multi-venue 5-gate spec」（最重要）

**M2 + M3 + M6 + M7 沒分配 ADR**（v5.8 §8 表只列 7 個新 ADR：0034-0040 對應 M1/M5/M8/M9/M11/M12/M13）。M2/M3/M6/M7 應有 ADR 還是合入既有？建議 PA dispatch 前確認，否則 Sprint 1A-β/γ 工時估算缺。

---

## 3. M9 A/B variant promote 走 Stage gate 完整性

§Risk C 已詳述，補充矩陣：

| Variant 類型 | Stage 影響 | Y1 H2 read-only 階段 | Sprint 7-8 manual approved 階段 | Y2 auto-gate 階段 |
|---|---|---|---|---|
| Parameter (MA=20 vs 30) | Stage 4 內 25% 灰度 | logging only | 顯著 → operator 採納 | mSPRT efficacy → auto 採納（無 5-gate 重檢需求） |
| Sizing (1.5% vs 2.0%) | Sizing 變化 >20% 觸發 Stage 1 demo 7d 重驗 | logging only | operator approve + Stage 1 7d | auto 不允許 sizing increase；只允許 sizing decrease |
| Trigger (touch vs close) | Entry semantic 變 → Stage 0R replay 重來 | logging only | Stage 0R + Stage 1 demo 7d | NOT auto-eligible Y2 |
| Overlay (with macro halt vs without) | 走 M2 overlay state | logging only | 入 M2 ADVISORY_TRIGGER | M2 auto-enable |

**v5.8 §M9 缺**：上表沒寫；E1 IMPL Sprint 4 不知 variant 切量規則。

---

## 4. 對 PA+PM 必收 top 3

1. **M1 Lease Tier 命名衝突 + ADR-0034 必含 LAL vs AMD-01 Stage 對齊矩陣** — Sprint 1A-β ADR-0034 起草前必收，否則 Sprint 4 + 7-8 IMPL 必撞牆
2. **M2/M3/M6/M7 沒分配 ADR：v5.8 §8 7 個新 ADR 不夠覆蓋 13 module 治理面** — PA dispatch 前必收：要嘛補 ADR-0034b/c/d/e（4 個 lite ADR），要嘛把 M2/M3/M6/M7 設計合入 0034（不推薦，因為主題分散）；推薦補 4 個 lite ADR
3. **新 12 個 schema migration V105-V116 PG dry-run SOP land Sprint 1A-ε** — v5.7 audit 已指 V### 必走 Linux PG empirical；v5.8 12 個 V 連續 land 風險倍增；ε 整合 audit 必含 12-V dry-run（twice idempotency）

---

## 5. v5.8 派發前 must-fix（Sprint 1A-β 啟動前完成）

1. **Risk A**：M1 Tier → LAL 改名 + ADR-0034 LAL vs Stage 對齊矩陣（Sprint 1A-β 起草必含）
   - 工時：3-5 hr（CC 文檔 + PA 校對）
   - Owner：CC + PA

2. **Risk B**：M7 STAGE_DEMOTED → DECAY_ENFORCED 改名 + 路徑明確化（demo fall-back 或 live 50%）
   - 工時：3-4 hr
   - Owner：PA + QC

3. **Risk C**：M9 variant 分類表 + ADR-0037 加 variant Stage 路徑
   - 工時：4-6 hr
   - Owner：QC + PA

4. **§4 top 3 第 2 項**：M2/M3/M6/M7 ADR 分配明確化（4 個 lite ADR or 合入 0034）
   - 工時：2-3 hr decision + 後續 ADR 起草各 8-12 hr
   - Owner：PA + CC

5. **§0.6**：12 V### dry-run SOP 落 Sprint 1A-ε 整合 audit
   - 工時：8-12 hr（per-V twice）
   - Owner：E3 + QA

---

## 6. Sprint 1A-β-ε should-fix（派發後第 1-7 週）

1. **§0.5 灰度事件嚴重度對照表** — 7 種自動行為改變事件 INFO/WARNING/CRITICAL 分級寫入 ADR-0036（M8 anomaly taxonomy 自然延伸）
2. **§0.6 IPC schema 增量清單** — M1/M3/M7/M9/M12/M13 涉及 Rust IPC 變動的 message type 在 Sprint 1A-β 列入，避免 Sprint 4-8 IMPL 撞 schema race
3. **§2 ADR-0034/0037/0039/0040 5-gate hard 段補入** — 各 ADR 起草時必含「不繞 5-gate」明文
4. **§3 M9 variant 4 類型 acceptance threshold spec** — Sprint 2 派 QC 並行起草（早於 IMPL Sprint 4）
5. **§0 表「M2 5-state vs Stage gate 嵌套」澄清** — M2 PRODUCTION_TRIGGER 是否要 Stage 0R replay preflight；建議要（overlay enable 改變策略 PnL 分布 = 等價策略行為改變）

---

## 7. v5.7 已 audit 項在 v5.8 是否修復（regression check）

| v5.7 audit Risk | v5.8 修復狀態 |
|---|---|
| Risk 1：Sprint 1B C10 跳 Stage gate | **MITIGATED**：v5.7 dispatch packet §1 已 reframe Stage 0R + Stage 1 Demo；v5.8 §3 Sprint 1A α 已 PM signed off；本 audit 不重做 |
| Risk 2：Earn governance 5-gate boundary | **PARTIAL**：v5.8 §10 風險 1-5 提到 D1c/D1d + D2，但 Earn vs 5-gate 在 v5.8 沒重訪；v5.7 audit must-fix #1 是否完成需 PA 確認；建議 v5.8 ADR-0040 spec 自然帶上 multi-venue 5-gate 設計時順帶把 Earn 納入 |
| Risk 3：SHADOW gate + counterfactual A/B threshold | **PARTIAL**：v5.8 §M2 5-state 對 counterfactual 有更明確路徑（COUNTERFACTUAL_ONLY → SHADOW_TRIGGER 看 t-stat≥1.5 + n≥30 + 60d）；但 t-stat ≥ 1.5 / 60d / n ≥ 30 三個閾值的選擇理由沒寫，QC 仍需起草 |
| 依賴 3.2：V101/V102 vs V103/V104 race | v5.8 §9 V105-V116 + V114-V116 reserve 是更大範圍 race；v5.7 audit must-fix #2 SOP 必延伸到 12 V |
| 依賴 3.3：既有 writer healthcheck SOP | v5.8 沒重訪；v5.7 must-fix #3 須先閉合再派發 v5.8 |

---

## QA Verdict Summary

**Verdict**：GO-WITH-CONDITIONS

**5 個 must-fix v5.8 派發前完成**：
- M1 Tier → LAL 改名 + ADR-0034 LAL vs Stage 對齊矩陣
- M7 STAGE_DEMOTED → DECAY_ENFORCED 改名 + 路徑明確化
- M9 variant 分類表 + ADR-0037 加 Stage 路徑
- M2/M3/M6/M7 ADR 分配明確化（4 個 lite ADR 推薦）
- 12 V### dry-run SOP 落 Sprint 1A-ε 整合 audit

**5 個 should-fix β-ε 週內完成**：
- 灰度事件嚴重度對照表
- IPC schema 增量清單
- ADR-0034/0037/0039/0040 5-gate hard 段
- M9 variant acceptance threshold spec
- M2 5-state vs Stage gate 嵌套澄清

**v5.7 audit 5 必收項未完全閉合**（Earn 5-gate + SHADOW threshold + 4 sensor healthcheck SOP），v5.8 派發前必先閉合 v5.7 audit 餘項。

v5.8 13-module thesis 與 operator directive 對齊（Round-16 reviewer + 2026-05-21 operator reject Claude push-back），這份 audit 不挑戰 13-module 必要性，只挑執行性層面的 Stage gate 對齊、5-gate boundary 一致性、schema 增量風險、IPC 變動可見性。GO-WITH-CONDITIONS 而非 NO-GO，因為缺項都是文檔層面（命名 + 對齊表 + ADR 分配），可在 Sprint 1A-β 啟動前的 1 週內完成（操作工時估 20-30 hr，並行 owner CC + PA + QC + FA）。

**Sprint 1A-α v5.7 baseline 已 PM signed off，不受 v5.8 影響**。v5.8 Sprint 1A-β 啟動條件 = 本 audit 5 必修 + v5.7 audit 餘項閉合。

---

**END v5.8 QA Executability Audit**
