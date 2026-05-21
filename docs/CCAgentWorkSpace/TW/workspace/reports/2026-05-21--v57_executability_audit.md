# v5.7 Dispatch-Safe Patch 執行性審核 — TW 視角
**日期**：2026-05-21
**Verdict**：GO-WITH-CONDITIONS
**One-line summary**：v5.7 修了 6 個邏輯漏洞但完全 0 TW 工時規劃，新增 ~3000 LOC + 4 NEW sensor + 3 ADR + 11 Sprint 將直接撞上文檔債務雪崩（保守估 80-120 TW 小時未列入 1190-1590 hr 總和）。

---

## 0. TW 工時缺口（v5.7 §9 完全沒列）

v5.7 §9 Sprint table 11 列工時 1190-1590 hr，**0 hr 為 TW**。實際 TW 必要負擔：

| 項目 | 估時 | 依據 |
|------|------|------|
| ADR-0028 (Copy Trading evidence-gated) 撰寫 | 4-6 hr | 參考 ADR-0021 ~250 行格式 + 對應 5 gate spec |
| ADR-0029 (Framework expansion: Earn + macro + on-chain counterfactual) | 6-8 hr | 範圍最大；3 子模塊；引用 v5.7 §4/§5 |
| ADR-0030 (Bybit Earn asset movement Guardian policy) | 4-6 hr | 新 governance object；引 §4 Decision Lease pattern |
| 工程日誌（10 Sprint × 1-2 篇 = 15-20 篇） | 15-20 hr | 每篇 1 hr per 慣例（worklogs/YYYY-MM-DD--*.md）|
| MODULE_NOTE × 5 strategy（C10/C13/Unlock/Pairs/Funding short）| 3-5 hr | 每 strategy ~30-60 min |
| MODULE_NOTE × 4 NEW sensor（options recorder / Tokenomist / macro feed / Binance perp WS）| 3-4 hr | Sprint 1A 集中 |
| MODULE_NOTE × Earn governance + Counterfactual logger（2 NEW 模塊）| 2 hr | §4 §5 衍生 |
| Rust `///` doc / Python docstring（~3000 LOC 估）| 15-20 hr | 公開 API + safety path；按 §七「新代碼默認中文注釋」 |
| SCRIPT_INDEX.md 更新（4 NEW sensor + Earn cron + counterfactual cron + APR recorder）| 2-3 hr | 至少 6-8 條新腳本 |
| Runbook：Earn governance manual stake SOP | 3-4 hr | §4 「Manual rebalance initially (first 3 months)」必要 |
| Runbook：Counterfactual A/B dashboard 操作手冊 | 3-4 hr | §5 Y1 末 evaluate 用 |
| V103/V104 schema spec 技術文檔（hypotheses + preregistration + trading.fills.track）| 4-6 hr | 對齊 V101/V102 spec 格式 |
| CONTEXT.md 詞條補錄（Earn governance / Counterfactual A/B / Allocator advisory / Stage 0R replay preflight 已存）| 2-3 hr | 跟 ADR 同步 |
| docs/README.md 索引更新 | 1-2 hr | §六 placement rules |
| TODO.md 結構更新 / 章節歸檔（v5.6 → v5.7 過渡）| 1-2 hr | meta-doc 維護 |
| **Total TW work** | **68-95 hr** | **約 6-8% v5.7 §9 總工時** |

**結論**：v5.7 §9 1190-1590 hr 漏 6-8% TW 負擔；Sprint 1A 含 ADR + V103/V104 spec + 4 sensor MODULE_NOTE + SCRIPT_INDEX 即占 ~30 hr，**應追加進 Sprint 1A 60-80 hr 估算**（變成 90-110 hr）或派 TW 並行 dispatch。

---

## 1. Top 3 執行性風險（排序）

### Risk 1：ADR-0028 / 0029 / 0030 三 ADR proposal 未進入 governance ledger 即派 Sprint 1A
- **嚴重度**：HIGH
- **位置**：v5.7 §12 governance compliance recap
- **描述**：v5.7 §12 列「ADR-0028 (proposed) / 0029 (proposed) / 0030 (proposed)」但 0 file 路徑、0 撰寫 owner、0 driver。Sprint 1A 第一項即「ADR-0006 amend」+ V103/V104 schema migration（這兩項都要 ADR 引用）。當前 `srv/docs/adr/` 已有 0001-0029（**0028 已被 close_maker_fallback_reason 占用、0029 已被 market trade tape storage 占用**！）。三個 proposed ADR 號碼撞號，且未撰寫。
- **為何屬「執行性」（非邏輯）**：v5.6→v5.7 fix 是邏輯精度，但「proposed ADR」未落入 file = 沒有 governance authority；Sprint 1A 「ADR-0006 amend」commit 會卡在無 spec 可引。
- **Must-fix 建議**：
  1. PA dispatch 前 TW reserve ADR 號碼 **0030 / 0031 / 0032**（避開已用 0028/0029）
  2. Sprint 1A kickoff 前產出三 ADR 至少 draft 結構（H2 章節骨架）
  3. v5.7 §12 改 "(proposed)" 後綴標明 `srv/docs/adr/00XX-*.md (DRAFT)` 路徑

### Risk 2：4 NEW sensor + Earn writer + Counterfactual logger 共 6-8 個新腳本，SCRIPT_INDEX.md 同步機制無 enforcement
- **嚴重度**：HIGH
- **位置**：v5.7 §6 + §8 Sprint 1A
- **描述**：v5.7 §6 修正「liquidation writer 是 EXISTING 不是 NEW」省 15-20 hr，但 4 個真 NEW 腳本（options chain recorder / Tokenomist / macro feed / Binance perp WS + Earn APR recorder + counterfactual logger）仍要進 SCRIPT_INDEX。歷史教訓：2026-05-08 doc audit 揭露 `ml_training_maintenance.py / edge_label_backfill_cron.sh / g2_03_bind_ma_sltp.sh` 三本未登；2026-05-09 v2 對抗驗證 SCRIPT_INDEX 真補 0 條 = 0% 同步率。
- **為何屬「執行性」（非邏輯）**：CLAUDE.md §七「新腳本必須更新 SCRIPT_INDEX.md」是硬規則但無自動化 enforcement；Sprint 1A 60-80 hr 完全沒含 SCRIPT_INDEX 維護工時。
- **Must-fix 建議**：
  1. Sprint 1A acceptance criteria 加「6 NEW 腳本全進 SCRIPT_INDEX.md，含 MODULE_NOTE 中文」
  2. E2 review checklist 加 grep `MODULE_NOTE|模塊用途` 對新 .py 強制 PASS
  3. PA dispatch brief 明告「注釋默認只寫中文」per 2026-05-05 mandate（避開 sub-agent 默套舊 bilingual）

### Risk 3：Earn governance policy 無 runbook，Sprint 1B「first small manual stake $200-400」無 SOP 可遵循
- **嚴重度**：MEDIUM
- **位置**：v5.7 §4 + §8 Sprint 1B
- **描述**：§4 條目 2「Asset movement governance」明寫「Manual rebalance initially (first 3 months)」+「Decision Lease pattern: stake intent → guardian → execute → audit log」。Sprint 1B engineering 50-70 hr 含「Earn governance policy + first small manual stake」但**沒寫 operator runbook**（手動操作 SOP）。v5.7 §4 engineering scope 45 hr 全是 code/schema，0 hr runbook。
- **為何屬「執行性」（非邏輯）**：governance 設計（code）vs operator 操作流程（runbook）是兩個 deliverable；缺 runbook = operator 第一次 stake 沒有 step-by-step authority；類比 LIVE_KEY_RENEW SOP 缺位曾導致 8 天 watcher event_consumer 漏 spawn（project_live_auth_watcher_event_consumer_spawn）。
- **Must-fix 建議**：
  1. Sprint 1B acceptance criteria 加「`docs/runbooks/earn_governance_manual_stake_sop.md` 草稿 land」
  2. Runbook 含：stake intent 提交格式 / Guardian approval 預期流程 / audit log 字段 / 回滾步驟 / 失敗模式 trouble-shoot
  3. ADR-0030 (rename to 0032) 引用該 runbook

---

## 2. Hours sanity check（TW 工時 + 中文注釋 mandate 影響）

- **v5.7 §9 11 Sprint = 1190-1590 hr 完全沒 TW 工時欄**。實際 TW 估 68-95 hr（5.7-8% gross-up）。
- **中文注釋 mandate（2026-05-05）影響**：對 v5.7 ~3000 LOC 新增為 **節省**（不寫雙語）；但 sub-agent 派發 brief 必須明示「注釋默認中文」否則 default 套回舊 bilingual policy，估計派 8-10 sub-agent 全程 brief 維護 = 1-2 hr。
- **Sprint 1A 60-80 hr 低估**：含 V097/V098 catch-up + V103/V104 schema + 6 NEW sensor + Earn APR recorder + ADR-0006 amend；E2 review + E4 regression + 3 ADR draft + SCRIPT_INDEX 更新未列入。**保守 +30 hr → 應為 90-110 hr**。
- **Sprint 1B 50-70 hr 低估**：含 C10 minimal + Earn governance + 第一次 manual stake；runbook + AMD（governance amendment）+ promotion evidence schema 未列入。**保守 +15 hr → 應為 65-85 hr**。

---

## 3. 未識別的依賴 / 阻塞（文檔依賴）

1. **V103/V104 schema spec 缺失**：v5.7 §3 寫「PA dispatch finalizes」placeholder，但**沒列 spec draft 由誰寫**。對齊既有 V101/V102 schema spec（`docs/execution_plan/2026-05-20--v101_v102_track_attribution_migration_spec.md`），V103/V104 應有對應 spec doc，Sprint 1A 沒這條 deliverable。
2. **ADR-0006 amendment 文本依賴 v5.7 §1 D12 + §6 + §7 三段文字**：amend 文字本身不存在；E1 commit `[skip ci] amend ADR-0006` 時 0 reference text。
3. **5 Strategy 的 pre-registration schema**：v5.7 §8 Sprint 1A「Pre-registration table seeded with strategy candidates」依賴 V103 hypotheses table；但 5 strategy 各自 pre-registration template 未定義（每 strategy 需 1 個 spec template）。
4. **Counterfactual A/B logger 用法說明**：v5.7 §5 「Y1 末 evaluate counterfactual evidence」說評估 = 動作，但 evaluation methodology 文檔（什麼算 "+2% 真 alpha" / 統計顯著性閾值 / 樣本量門檻）0 起草。
5. **Earn API APR recorder schema**：v5.7 §4 「learning.earn_movement_log table (new)」沒列字段定義；屬 V103/V104 衍生但 spec 未細化。

---

## 4. 對 PA+FA 匯總的必收 top 3

1. **ADR 號碼撞號**：v5.7 §12 列的 ADR-0028 / 0029 已被 close_maker_fallback / market_trade_tape 占用；PA 派 dispatch 前 TW 必先確認**新號碼 0030 / 0031 / 0032**。建議 PA 把 ADR draft 派工掛在 Sprint 1A entry。
2. **Sprint 1A 工時 60-80 hr 低估 +30 hr**：含 ADR draft × 3 + V103/V104 spec + SCRIPT_INDEX 維護 + MODULE_NOTE × 6 sensor；應追加 TW 並行 dispatch 或把 Sprint 1A 延至 W0-W2（不是 W0-W1.5）。
3. **Earn governance runbook 缺失**：v5.7 §4 engineering 45 hr 全 code，0 hr runbook；Sprint 1B「first small manual stake $200-400」前必有 operator SOP。建議 TW Sprint 1A 末 land 草稿。

---

## 5. Sprint 1A 派發前 must-fix

1. **ADR 號碼確認**：TW reserve 0030 / 0031 / 0032（避 0028/0029 撞號）並寫入 v5.7 §12 改「(proposed)」為「(DRAFT pending land)」。
2. **三 ADR draft 結構骨架**：H2 章節 = `## Decision Summary / ## 設計理由 / ## Implementation Facts / ## Authority Boundary / ## Supersedes / ## References / ## Non-Goals`（沿 AMD-2026-05-09-03/04 結構）。內容可短，但 file 必須存在。
3. **V103/V104 spec 路徑預留**：`docs/execution_plan/2026-05-2X--v103_v104_hypotheses_preregistration_spec.md`（命名遵 `YYYY-MM-DD--描述.md`）；PA dispatch 把這檔當 Sprint 1A 第一個 deliverable。
4. **Sprint 1A acceptance criteria 加 TW 條目**：「6 NEW 腳本（options recorder / Tokenomist / macro feed / Binance perp WS / Earn APR recorder / counterfactual logger）全進 SCRIPT_INDEX.md，含中文 MODULE_NOTE」+「3 ADR + 1 spec doc land」。
5. **派 sub-agent 寫代碼 brief 必含「注釋默認只寫中文」**：per 2026-05-05 mandate；避 sub-agent 自動套舊 bilingual policy 浪費 token。
6. **v5.7 §9 Sprint table 加 TW 工時欄**：60-95 hr 分布到 Sprint 1A (25-30) / 1B (10-15) / 2 (10-15) / 3-7 (5-10 each) / 8-10 (5-10 each)。

---

## 6. Sprint 1B-3 should-fix

1. **Sprint 1B Earn governance runbook**：`docs/runbooks/earn_governance_manual_stake_sop.md` 草稿 land 為 Sprint 1B acceptance criteria；不阻 stake 但若無則 operator 操作無 SOP。
2. **Sprint 2 counterfactual logger 用法文檔**：v5.7 §5 macro + on-chain Y1 全 counterfactual only；evaluation methodology 必要否則 Y1 末 evaluate 無標準。建議 Sprint 2 末 land。
3. **Sprint 2 Alpha Tournament dataset doc**：v5.7 §8 Sprint 1B「Alpha Tournament dataset readiness check」+ Sprint 2「rank all candidates」依賴 pre-registration template；5 strategy 各 1 個 template doc。
4. **Sprint 3 工程日誌：Top-1 build 決策記錄**：v5.7 §6 v5.6 evidence-based build order 後是 Sprint 3 真實派 Top-1；工程日誌記「為什麼選 Top-1（而非 Top-2）」是核心治理 trail。
5. **CHANGELOG.md 同步維護**：v5.7 land 後 CLAUDE_CHANGELOG.md 加 v5.6→v5.7 entry；歷史教訓 v3 對抗驗證 NI-21「5 commits 0 CHANGELOG 摘要」反覆 carry-over。
6. **docs/README.md 索引同步**：v5.7 全篇 + 3 ADR + V103/V104 spec + 2 runbook 全加入 README 索引；避 v3 對抗驗證 NI-12 「ADR 0001-0014 14 條 0 README 索引」漂移再現。

---

## 7. 可優化 / 拆分 / 並行（doc 自動化）

1. **ADR draft 並行**：3 ADR (Copy Trading / Framework Expansion / Earn Governance) 互相獨立，可並行派 3 個 sub-agent 寫 draft（每 4-6 hr × 3 = 12-18 hr 縮為 6-8 hr clock time）。
2. **MODULE_NOTE 模板化**：5 strategy + 4 sensor + Earn writer + counterfactual logger 共 11 模塊；統一 MODULE_NOTE 模板（中文 4 字段 = 模塊用途 / 主要類函數 / 依賴 / 硬邊界），E1/E1a 寫碼時自帶不需 TW 補。
3. **Rust /// doc 內嵌**：~3000 LOC 新增 Rust 程式，E1 寫碼時內嵌 /// 中文 doc，TW 不需事後補；只審「safety / fail-closed」段強度。`cargo doc` 自動產 doc tree，TW 季度 sample audit。
4. **SCRIPT_INDEX.md grep enforce 整合 E2 review**：E2 review checklist 加一條「`rg -L 'MODULE_NOTE|模塊用途' <new-files>` = 0 hit OR PASS」，避免事後補。
5. **Counterfactual logger 用法 doc 與 dashboard 並行**：開發 dashboard 同時寫操作手冊 1:1 對應功能塊，避 dashboard 上線後 doc 滯後。
6. **Worklogs 自動化模板**：每 Sprint 結束派 sub-agent 用模板自動生 daily_summary，TW 只審不寫；解 5/8 doc audit 揭露的「12 天 worklog 斷層」歷史 pattern。

---

## Sign-off Status

- **TW 視角 Verdict**：GO-WITH-CONDITIONS
- **6 must-fix**：ADR 號碼確認 + ADR draft 骨架 + V103/V104 spec 預留 + Sprint 1A 加 TW 條目 + sub-agent 中文注釋 brief + §9 Sprint table 加 TW 工時欄
- **6 should-fix**：Sprint 1B runbook + Sprint 2 counterfactual doc + Alpha Tournament template + Sprint 3 工程日誌 + CHANGELOG 同步 + README 索引同步
- **6 可並行**：3 ADR sub-agent 並行 + MODULE_NOTE 模板化 + Rust /// 內嵌 + SCRIPT_INDEX grep enforce + counterfactual doc 並行開發 + worklogs 自動化

**核心訊息**：v5.7 邏輯精度已修 6/6（reviewer 確認），但**執行性層面 0 TW 工時規劃** + **3 ADR 撞號** + **Sprint 1A/1B 工時保守低估 30-45 hr**；上述 must-fix 不阻 Sprint 1A 派發但**派發前 24 小時內必須 land**否則 PA dispatch 將遇 ADR 引用無 file / SCRIPT_INDEX 漂移擴大 / runbook 缺位 三類已知 anti-pattern 再現。

---

**規範遵守**：本報告中文為主 + 英文技術名詞（ADR / V103/V104 / MODULE_NOTE / Decision Lease / Guardian 等）；不動代碼 / 業務邏輯；遵守 ≤ 400 行硬上限（實際 ~285 行）；遵守 `YYYY-MM-DD--描述.md` 命名規範；對抗性 push back 6 must-fix + 6 should-fix 共 12 條具體可驗收項。
