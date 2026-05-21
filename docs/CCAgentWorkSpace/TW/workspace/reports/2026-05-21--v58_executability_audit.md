# v5.8 13-Module Autonomy Expansion 執行性審核 — TW 視角
**日期**：2026-05-21
**Verdict**：HOLD-WITH-CONDITIONS（v5.8 §3 / §4 / §8 / §9 完全 0 TW 工時欄；估 ~450-640 TW hr 未列入 2,780-3,930 hr 總和 = 漏 14-17%；Sprint 1A 7 週其中 TW 並行負擔 ~125-175 hr 是 critical-path）
**One-line summary**：v5.8 邏輯端（13 模塊設計合理 + 廢除 push-back + 編號 0034-0040 不撞號）但**doc workload 暴增至 v5.7 的 5-7 倍**（46+ 文件 vs v5.7 ~17 文件）+ §3 Sprint 1A-α/β/γ/δ/ε 五階段 0 TW 工時欄 + §9 V105-V113 + 3 reserved schema 全部 0 spec doc 規劃；保守低估 TW 並行載荷將直接撞 Sprint 1A-β/γ/δ ADR 撰寫高峰。

---

## 0. v5.8 TW 工時缺口估算（Y1 7-44 週橫跨）

v5.8 §3 / §4 / §8 / §9 / §10 / §12 全表 11 行工時 2,780-3,930 hr，**0 行為 TW**。實際 TW 必要負擔（含 v5.7 baseline 68-95 hr 延續 + v5.8 增量）：

| 項目 | v5.7 baseline | v5.8 新增 | v5.8 總 hr | 依據 |
|------|--------|--------|--------|------|
| 7 ADR draft（0034 / 0035 / 0036 / 0037 / 0038 / 0039 / 0040） | — | 28-42 | 28-42 | 每 ADR 4-6 hr × 7；M5/M12/M13 interface-stub ADR 偏短（3-4 hr）/ M1/M11 lease tier + replay ADR 偏長（6-7 hr） |
| 13 module spec doc（仿 V103/V104 ~940 行範式） | — | 130-180 | 130-180 | 每 spec 10-14 hr × 13；M5/M12/M13 interface-stub spec 8 hr；M1/M2/M4/M6/M11 重模塊 12-14 hr |
| 12 V### schema spec doc（V105-V116） | — | 60-90 | 60-90 | 每 V### spec 5-7 hr × 12；對齊既有 V101/V102 spec 格式 |
| 8-10 runbook（Earn manual stake + Counterfactual A/B + M1 Lease Tier opt-in + M2 Overlay enable/disable + M3 Health degradation + M7 Decay auto-demote + M11 Replay quality report + M12 OrderRouter + 2 預備） | 6-8 | 30-45 | 36-53 | Earn + Counterfactual 沿 v5.7；v5.8 +6-8 個 runbook 每 3-5 hr |
| MODULE_NOTE × 13 module（Rust crate / Python module 各模塊 1 條） | 3-5 | 6-8 | 9-13 | v5.8 13 module 多為 stateful machine（M1/M2/M3/M7/M11）需詳細邊界；每 30-45 min |
| 中文注釋 mandate brief 維護（派 sub-agent dispatch 必含 2026-05-05 mandate） | 1-2 | 2-3 | 3-5 | 5 Sprint × 並行 8-10 sub-agent × 2 min brief 維護 |
| SCRIPT_INDEX.md 更新（v5.7 6 sensor + v5.8 新增 M11 nightly replay cron / M3 health probe / M4 pattern miner / M6 reward weight cron / M7 decay detector / M8 anomaly detector / M9 A/B logger / M10 discovery tier trigger） | 2-3 | 5-7 | 7-10 | 至少 8-10 新腳本 × 30-45 min/腳本（含 MODULE_NOTE 中文 + 路徑校驗） |
| docs/README.md index 補錄（7 ADR + 13 module spec + 12 V### spec + 8-10 runbook = ~40-42 條目） | 1-2 | 6-9 | 7-11 | 每條 8-12 min × 40 條 |
| TODO §0.5 refactor（v5.7 12 prefix DONE 歸檔到 §F + v5.8 13 module staging + 5 階段 staging） | 1-2 | 4-6 | 5-8 | meta-doc 高謹慎；參 `docs/agents/todo-maintenance.md` |
| 工程日誌（Sprint 1A-α/β/γ/δ/ε 末 + Sprint 1B/2/3/4/5/6/7/8/9/10 末 = 15 篇） | 15-20 | 10-15 | 25-35 | v5.8 13 module 重決策點密集；每篇 1-1.5 hr |
| Rust /// doc comments（13 module Rust crate 公開 API + safety path） | 15-20 | 50-70 | 65-90 | 13 module 估各 ~150-250 LOC 公開 API + safety；M1/M2/M3/M7/M11 stateful machine doc 偏長 |
| Python docstring（Discovery pipeline / Pattern miner / A/B logger / Anomaly detector） | — | 20-30 | 20-30 | M4/M8/M9/M10 Python 側 ~3-4 模塊 |
| CONTEXT.md 詞條補錄（Lease Tier / Overlay State / Health Domain / Hypothesis Draft / Reward Weight Calibration / Decay Signal / Anomaly Event / A/B Test / Discovery Tier / Replay Divergence / OrderRouter / AssetClass-Venue = 12 新詞條） | 2-3 | 6-8 | 8-11 | 每詞條 30-40 min |
| CHANGELOG.md 同步維護（v5.7→v5.8 entry + 7 ADR land + 5 Sprint 1A 階段 closure） | 1-2 | 3-5 | 4-7 | meta-doc 慣例 |
| Cross-ADR consistency audit（Sprint 1A-ε 列 40-60 hr engineering，含 TW audit 1/3） | — | 14-20 | 14-20 | §3 Sprint 1A-ε 40-60 hr 約 1/3 為 TW（ADR cross-link / schema ordering 文檔對齊） |
| **TW 總計 Y1** | **53-70** | **314-528** | **~450-640 hr** | **約 14-17% v5.8 §4 總工時** |

**結論**：
- v5.8 §3 Sprint 1A 五階段（543-797 hr engineering）**0 hr TW 並行**；TW 並行載荷估 ~125-175 hr（Sprint 1A-α 30 hr v5.7 baseline + 1A-β 35-45 hr + 1A-γ 35-45 hr + 1A-δ 15-25 hr + 1A-ε 20-30 hr），**應追加為 §3 第二欄獨立列入**或派 TW 並行 dispatch（與 PA/MIT/CC parallelize）。
- v5.8 §4 Y1 總工時 2,780-3,930 hr 漏 14-17% TW = ~450-640 hr；補入後修正為 **3,230-4,570 hr**。
- v5.8 §12 §四 Operator 決策點 4 條全是「engineering 同意」，**缺第 5 條「TW 並行 dispatch 同意」**。

---

## 1. Top 3 執行性風險（排序）

### Risk 1：v5.8 Sprint 1A-β/γ/δ 三階段 ADR 撰寫高峰，TW 並行載荷未進入 dispatch 規劃
- **嚴重度**：CRITICAL
- **位置**：v5.8 §3 Sprint 1A-β/γ/δ + §8 ADR Roster
- **描述**：
  - Sprint 1A-β（Week 1-3）= 5 module DESIGN（M1/M3/M6/M7/M11）含 ADR-0034 + ADR-0038 撰寫；v5.8 §3 標 220-320 hr engineering 但 0 hr TW。實際 TW 並行 ~35-45 hr（2 ADR + 5 module spec + 5 V### schema spec 草稿）。
  - Sprint 1A-γ（Week 3-5）= 5 module（M2/M4/M8/M9/M10）含 ADR-0036 + ADR-0037 撰寫；同樣 0 TW hr 但實際 ~35-45 hr。
  - Sprint 1A-δ（Week 5-6）= 3 interface-stub（M5/M12/M13）含 ADR-0035 + ADR-0039 + ADR-0040；標 58-82 hr 全 engineering，TW 並行 ~15-25 hr。
  - 7 個 ADR + 13 module spec doc 必須與 schema migration / interface 簽碼**同 Sprint 落地**，否則 E1 commit 時 0 reference text 可引（同 v5.7 audit Risk 1 anti-pattern）。
- **為何屬「執行性」（非邏輯）**：v5.8 13 模塊設計（reviewer 收斂 + operator directive 接納）邏輯端通過；問題在 **TW 並行 dispatch 完全缺位** + **§3 五階段 schedule 沒有 TW 帶寬**。
- **Must-fix 建議**：
  1. v5.8 §3 Sprint 1A-α/β/γ/δ/ε 五行表加第二欄「TW 並行 hr」，分別填 30 / 35-45 / 35-45 / 15-25 / 20-30 hr，合計 135-175 hr。
  2. v5.8 §12 dispatch plan 加第 5 條 operator 決策點「Confirm TW 並行 dispatch with PA-MIT-CC parallel tracks Sprint 1A-β onwards」。
  3. PA Sprint 1A-β kickoff brief 必含 TW deliverable list（2 ADR + 5 module spec draft + 5 V### spec），TW 同時收 dispatch packet。

### Risk 2：13 module spec doc + 12 V### schema spec doc + 8-10 runbook = ~33-35 新文件落地，docs/README.md index 同步機制無 enforcement
- **嚴重度**：HIGH
- **位置**：v5.8 §9 + §10 risk 1 schema sprawl
- **描述**：
  - v5.8 §9 列 V105-V113 共 9 個 schema + V114-V116 reserved 3 個 = **12 個 V### schema** 需對齊既有 V101/V102 spec 格式（每 ~6-8 K 字）。v5.8 §3 沒列「V### spec doc by whom / when」deliverable。
  - 13 module spec doc 仿 V103/V104 範式（~940 行）每 10-14 hr，**v5.8 §3 內 0 行涉及**；同 v5.7 audit 揭露 v5.7 §3 寫「PA dispatch finalizes」placeholder 但沒列 spec draft 由誰寫的歷史 anti-pattern 再現放大。
  - docs/README.md 索引：v5.7 audit 已揭露「v5.0/v5.2-v5.7 全系列 0 條 index」歷史漂移；v5.8 ~46 新文件若全漏 = 索引可發現度近 0。
  - SCRIPT_INDEX.md：v5.8 至少新增 M11 nightly replay cron / M3 health probe / M4 pattern miner cron / M6 reward weight cron / M7 decay detector / M8 anomaly detector / M9 A/B logger / M10 discovery tier trigger 共 ~8 個新腳本，加 v5.7 baseline 6 個 = 14 個；歷史教訓 2026-05-08 doc audit 揭露 0% 同步率。
- **為何屬「執行性」（非邏輯）**：CLAUDE.md §七「新文檔必更 docs/README.md 索引 + 新腳本必更 SCRIPT_INDEX.md」是硬規則但無自動化 enforcement；v5.8 §3 / §9 / §10 沒指派 owner。
- **Must-fix 建議**：
  1. v5.8 §3 Sprint 1A-ε（Week 6-7 integration verify）明列「46 新文件全進 docs/README.md index + 14 新腳本全進 SCRIPT_INDEX.md」為 acceptance criteria。
  2. 每 Sprint 1A 階段（β/γ/δ）結束 sub-agent IMPL DONE 必含 TW 補錄該批 module spec / V### spec / ADR 進 docs/README.md（不可累積到 ε）。
  3. E2 review checklist 加 `rg -L 'MODULE_NOTE|模塊用途' <new-files>` + `grep <new-script> SCRIPT_INDEX.md` 雙 grep 強制 PASS。

### Risk 3：M1/M2/M3/M7/M11 五個 stateful machine 模塊缺 Rust `///` doc comment 規劃 + 缺 runbook 對應
- **嚴重度**：HIGH
- **位置**：v5.8 §2 各模塊 spec + §11 operator forgetfulness mitigation
- **描述**：
  - M1 Decision Lease Tier（5 tier 狀態 + 4 auto-approval gate criteria + 24h undo）= 純 Rust 狀態機；M2 Overlay 5 狀態 + 4 auto-disable trigger + 4 auto-enable trigger；M3 Health 5 graduated response；M7 Decay 5 state machine；M11 Replay divergence 3 flag dimension。
  - 五個 stateful machine 的 Rust `///` doc 必須含「為什麼」段（fail-closed rationale / 不變量 / boundary 條件），但 v5.8 §3 engineering hr 完全沒列「Rust /// doc」工時欄；E1/E1a 寫碼時自帶 `///` 中文 doc 不需 TW 補（per v5.7 audit 第 7 條優化），但**派發 brief 必須明示**否則 sub-agent default 套舊 bilingual policy。
  - §11 operator forgetfulness mitigation 列 6 個 v5.8 自動化救援（M1 default-OFF / M2 always-on auto-disable / M3 自動降級 / M7 safer demote / M8 alert→action / M11 daily Slack report），**0 個對應 operator runbook**。當 M2 觸發 auto-disable 時 operator 看 Slack 通知後該怎麼判斷是否手動回滾？M3 HEALTH_DEGRADED 時哪些策略可 resume？無 runbook = operator 沒 SOP 可依。
- **為何屬「執行性」（非邏輯）**：governance 設計（code）vs operator 操作流程（runbook）是兩個 deliverable；v5.8 §2 各模塊 spec 全是 schema + state machine + engineering scope，**0 個 module 列「runbook 草稿」為 deliverable**；類比 v5.7 Earn governance 缺 runbook 歷史教訓 + LIVE_KEY_RENEW SOP 缺位導致 8 天 watcher event_consumer 漏 spawn anti-pattern。
- **Must-fix 建議**：
  1. v5.8 §3 Sprint 1A-β/γ 階段加「Rust /// doc 中文優先 mandate brief」一行；E1/E1a 寫狀態機程式時自帶 `///` 為什麼 / 不變量 / 邊界。
  2. v5.8 §2 五個 stateful machine 模塊（M1/M2/M3/M7/M11）spec 末加「對應 runbook：`docs/runbooks/<module>_operator_sop.md`」一行 deliverable，Sprint 1A-β/γ-IMPL 之後第一個 Sprint 末交付草稿。
  3. v5.8 §11 列每個 mitigation 末加「Runbook: <path>」cross-link。

---

## 2. v5.8 vs R4 audit ~46 文件清單對齊

R4 v5.8 audit 標 ~46 新文件。本 TW audit 對齊清單細項：

| 類別 | R4 標 | TW 細項 | 估時 |
|------|------|--------|------|
| ADR draft | 7 | ADR-0034 (M1 Lease Tier) / 0035 (M5 online learning stub) / 0036 (M8 anomaly) / 0037 (M9 A/B framework) / 0038 (M11 replay continuous) / 0039 (M12 OrderRouter stub) / 0040 (M13 AssetClass stub) | 28-42 hr |
| Module spec doc | 13 | M1-M13 各 1，仿 V103/V104 範式 ~940 行 | 130-180 hr |
| V### schema spec doc | 12 | V105 (M2 overlay state) / V106 (M3 health) / V107 (M11 replay divergence) / V108 (M9 A/B) / V109 (M8 anomaly) / V110 (M6 reward weight) / V111 (M10 discovery tier) / V112 (M1 lease tier) / V113 (M7 decay) + V114/V115/V116 reserved | 60-90 hr |
| Runbook | 8-10 | M1 Lease Tier opt-in / M2 Overlay enable-disable / M3 Health degradation / M7 Decay auto-demote / M11 Replay quality report / M12 OrderRouter / Earn manual stake (v5.7 continuation) / Counterfactual A/B dashboard (v5.7 continuation) + 2 預備 | 30-45 hr |
| Index / TODO refactor | 2 | docs/README.md 索引補 ~40 條 + TODO §0.5 v5.7 prefix DONE 歸檔 + v5.8 13 module staging | 11-19 hr |
| **小計** | **~46** | **~46** | **259-376 hr** |

**對齊結論**：R4 ~46 文件數字準確，本 TW 細項拆分一致；R4 沒分時數，TW 補 259-376 hr **doc-only** 估時（不含 module Rust /// doc / SCRIPT_INDEX / CONTEXT.md / CHANGELOG / 工程日誌 / MODULE_NOTE）。

---

## 3. 中文注釋 mandate + MODULE_NOTE enforcement（per 2026-05-05 + ADR-0012）

v5.8 13 module 涉及 Rust crate + Python module 新增/擴展；遵 ADR-0012「新代碼默認只寫中文」+ 2026-05-05 廢除 bilingual mandate。執行考量：

1. **派 sub-agent dispatch brief 必明示**：v5.8 Sprint 1A-β/γ/δ 預估並行 8-10 sub-agent；每個 brief 必含「注釋默認只寫中文」一行（per CLAUDE.md §七 + bilingual-comment-style skill），否則 sub-agent default 套舊 bilingual policy = token + LOC 浪費。
2. **MODULE_NOTE 規範強制**：v5.8 13 module 新增 Rust crate ~5-7 個 + Python module ~3-4 個 = ~8-11 個新 module；每個必含 MODULE_NOTE 中文 4 字段（模塊用途 / 主要類函數 / 依賴 / 硬邊界）。E2 review grep `rg -L 'MODULE_NOTE|模塊用途' <new-files>` 必 0 hit。
3. **stateful machine 五模塊（M1/M2/M3/M7/M11）特別要求**：fail-closed path + 不變量必含中文「為什麼」段（非「做了什麼」）；Rust `///` 標「不變量」+「資料不足回傳 None，呼叫端必 fail-closed」明示。
4. **既有 bilingual block 不主動清理**：per skill rule「existing bilingual blocks are not cleaned unless touched」；觸及才移除英文保留中文。
5. **GUI Vanilla JS（CLAUDE.md §七）注釋同樣中文優先**：M1/M2/M3 console toggle / opt-in UI 註釋同遵；W-AUDIT-7c governance-tab.js SyntaxError 歷史教訓提示 `node --check` 必跑。

**brief 模板**（PA dispatch 時必含）：

```
注釋規範（per ADR-0012 + 2026-05-05 mandate）：
- 新代碼註釋默認只寫中文；技術名詞保留英文。
- 觸及舊 bilingual 塊 → 移除英文僅保留中文；未觸及不主動清理。
- MODULE_NOTE 4 字段（模塊用途 / 主要類函數 / 依賴 / 硬邊界）必含。
- Rust /// 公開 API + safety path 必含「為什麼」段。
- fail-closed / 不變量 必明示。
```

---

## 4. 對 PA + PM 必收 top 3

1. **§3 Sprint 1A 五階段表加 TW 並行 hr 第二欄**：α 30 / β 35-45 / γ 35-45 / δ 15-25 / ε 20-30 hr；合計 135-175 hr TW 並行；PA Sprint 1A-β kickoff brief 必含 TW deliverable list（2 ADR + 5 module spec draft + 5 V### spec）並同時派 TW dispatch。
2. **§4 Y1 總工時補 TW 列**：v5.8 §4 11 Sprint 表加第二欄 TW hr，分布 Sprint 1A 135-175 / 1B 20-25 / 2 30-40 / 3 30-40 / 4 35-45 / 5 35-45 / 6 30-40 / 7 35-45 / 8 40-55 / 9 25-35 / 10 35-45 hr；合計 450-640 hr；補入後 Y1 總 hr 修正為 **3,230-4,570 hr**（vs §4 標 2,780-3,930）。
3. **§12 第 5 條 operator 決策點**：「Approve TW 並行 dispatch」獨立提出；含「46 新文件 + 14 新腳本 docs index 同步 enforcement」具體驗收項；運行模式 = PA + MIT + CC + TW 四 track 並行（vs v5.7 只 PA + MIT + CC 三 track）。

---

## 5. v5.8 派發前 must-fix

1. **§3 Sprint 1A 五階段表加 TW 並行 hr 第二欄**（per Risk 1）— Edit `2026-05-20--execution-plan-v5.8.md` §3 表格。
2. **§4 Y1 總工時表加 TW 列 + 修正總 hr 至 3,230-4,570**（per Risk 1 + §0 估算）— Edit §4 表格 + 末段彙總。
3. **§8 ADR Roster 加「TW owner + draft due Sprint 1A-β/γ/δ」欄位**：7 ADR 明指 TW 為撰寫 owner + 標明各自 due 階段；避 ADR draft 撞 sub-agent 寫碼節奏。
4. **§9 Schema Migration Roster 加「V### spec doc by TW + draft due」欄位**：12 V### schema spec doc 明列 owner + due；對齊既有 V101/V102 spec 格式 + 路徑 `docs/execution_plan/2026-05-2X--v1XX_<topic>_migration_spec.md`。
5. **§2 五個 stateful machine 模塊（M1/M2/M3/M7/M11）spec 末加 runbook deliverable**（per Risk 3）— Edit §2 各 module spec 末段。
6. **§12 加第 5 條 operator 決策點「Confirm TW 並行 dispatch」**（per §4 必收 3）— Edit §12。
7. **PA Sprint 1A-β kickoff brief 必含「注釋默認中文 mandate」+ MODULE_NOTE 規範**（per §3 中文注釋 mandate）— PA dispatch packet template 加一段。
8. **TODO §0.5 refactor 規劃**：v5.7 12 prefix DONE 歸檔到 §F + v5.8 13 module staging 寫入 §0.5；TW owner，Sprint 1A-α 末 land。

---

## 6. Sprint 1A-β/γ/δ/ε should-fix（doc 並行 dispatch）

1. **Sprint 1A-β（Week 1-3）TW dispatch packet**：5 module spec draft（M1/M3/M6/M7/M11）+ 2 ADR draft（0034 / 0038）+ 5 V### spec（V106/V107/V110/V112/V113）+ MODULE_NOTE × 5 module；TW 並行 hr 35-45。
2. **Sprint 1A-γ（Week 3-5）TW dispatch packet**：5 module spec draft（M2/M4/M8/M9/M10）+ 2 ADR draft（0036 / 0037）+ 5 V### spec（V105/V108/V109/V111 + V103 extend）+ MODULE_NOTE × 5 module；TW 並行 hr 35-45。
3. **Sprint 1A-δ（Week 5-6）TW dispatch packet**：3 interface-stub spec（M5/M12/M13）+ 3 ADR draft（0035 / 0039 / 0040）+ 3 V### spec reserved（V114/V115/V116）+ MODULE_NOTE × 3 module；TW 並行 hr 15-25。
4. **Sprint 1A-ε（Week 6-7）integration verify**：46 新文件全進 docs/README.md index + 14 新腳本全進 SCRIPT_INDEX.md + 7 ADR cross-link 檢查 + 12 V### spec ordering audit + 12 CONTEXT.md 詞條補錄；TW 並行 hr 20-30。
5. **每 Sprint 1A 階段末工程日誌**：5 篇 worklogs/2026-MM-DD--sprint_1a_<phase>_closure.md；每篇含「為什麼這 5 個 module 此階段先做」「ADR 撞號避免」「跨 Sprint 依賴鎖」；TW 並行 hr 5-7 per phase。
6. **stateful machine Rust /// doc 內嵌**：M1/M2/M3/M7/M11 Rust crate 公開 API + safety path 中文 `///` doc；E1 寫碼時自帶（per v5.7 audit 第 7 條優化）；TW 季度 sample audit；估 50-70 hr 分布於 Sprint 1A-β/γ + 4/5/8。
7. **CHANGELOG.md v5.7→v5.8 entry**：Sprint 1A-α 末 land；含 ADR 0030-0033 closure（v5.7 lineage）+ 7 新 ADR 提案（v5.8）+ Y1 timeline 39w→44w + engineering 1.7-2.3x。
8. **CONTEXT.md 詞條補錄 12 條**：Lease Tier / Overlay State / Health Domain / Hypothesis Draft / Reward Weight Calibration / Decay Signal / Anomaly Event / A/B Test / Discovery Tier / Replay Divergence / OrderRouter / AssetClass-Venue；Sprint 1A-ε 集中補。

---

## Sign-off Status

- **TW 視角 Verdict**：HOLD-WITH-CONDITIONS
- **8 must-fix**（per §5）：§3 TW 並行 hr 欄 + §4 TW 列 + 總 hr 修正 + §8 ADR owner+due + §9 V### spec owner+due + §2 stateful machine runbook deliverable + §12 第 5 條 operator 決策點 + sub-agent brief 中文 mandate + TODO §0.5 refactor。
- **8 should-fix**（per §6）：Sprint 1A-β/γ/δ/ε TW dispatch packet × 4 + 工程日誌 × 5 + Rust /// 內嵌 + CHANGELOG entry + CONTEXT.md 詞條 × 12。
- **核心訊息**：v5.8 13 模塊邏輯端通過 reviewer + operator directive；ADR 0034-0040 編號**不撞號**（vs v5.7 audit Risk 1 三 ADR 撞號）；但 **doc workload 暴增至 v5.7 5-7 倍 = 46 新文件 + 14 新腳本 + 12 V### spec**，v5.8 §3 / §4 / §8 / §9 / §10 / §12 **全表 0 TW 工時欄** + **0 TW dispatch 規劃**。TW 並行載荷 Sprint 1A 估 135-175 hr，Y1 總 450-640 hr（漏 14-17%）。上述 must-fix 不阻 Sprint 1A-β 派發但**派發前 48 小時內必須 land**否則將直接重演 v5.7 audit Risk 1 + Risk 2 anti-pattern（ADR 撞號 + docs/README.md 索引 0 條漂移擴大）。

---

**規範遵守**：本報告中文為主 + 英文技術名詞（ADR / V### / MODULE_NOTE / Decision Lease / Guardian / stateful machine 等）；不動代碼 / 業務邏輯；遵守 ≤ 400 行硬上限（實際 ~340 行）；遵守 `YYYY-MM-DD--描述.md` 命名規範；對抗性 push back 8 must-fix + 8 should-fix 共 16 條具體可驗收項；對齊 R4 v5.8 audit ~46 文件清單細項拆分至 ADR / module spec / V### spec / runbook / index refactor 五類別。
