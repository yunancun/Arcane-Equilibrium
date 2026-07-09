# v5.7 Dispatch-Safe Patch 執行性審核 — A3 視角

**日期**：2026-05-21
**Verdict**：**GO-WITH-CONDITIONS**
**One-line summary**：v5.7 thesis 與 6 個 reviewer 修復都合理，但 §9 工時表 0 行 GUI 工作 = 對 5 個新 operator-facing surface（Earn stake/redeem / Allocator monthly approval / Counterfactual dashboard / 5 strategy 並行儀表盤 / Macro+On-chain log viewer）的 UX 工時系統性失明；Sprint 1A 可以派發但必須先加 60-90 hr GUI 工時池並指定 ownership，否則 Sprint 1B 末 Earn 第一筆 $200-400 manual stake 會在「沒有真實 UI 的 Decision Lease 路徑」上被推上線。

---

## 1. Top 3 執行性風險（排序）

### Risk 1：Earn stake/redeem GUI 缺工時 + 缺 tab 定位 — 第一個資產寫入操作無 UI 路徑

- **嚴重度**：CRITICAL
- **位置**：v5.7 §4「Asset movement governance」+ §8 Sprint 1B「Earn governance policy + first small manual stake $200-400」+ §9 工時表
- **描述**：
  - §4 明文「Decision Lease pattern: stake intent → guardian → execute → audit log」+「Manual rebalance initially (first 3 months)」+「Auto-redeem trigger: trading margin headroom < 30%」
  - §4「Engineering scope」45 hr 細項：API 整合 15 + Governance 整合 20 + Audit log schema 10 = **0 hr GUI / 前端**
  - §8 Sprint 1B 工時 50-70 hr，其中 Earn governance 計入但未拆 GUI
  - README §22-42 16 個 tab **沒有 Earn 對應位置**；不在 `settings`（settings 是參數）；不在 `governance`（governance 是 Decision Lease 列表，不是 stake form）；不在 `live`（live 是 PnL/持倉/成交）
  - operator manual stake $200-400 需要「輸入金額 → 看 APR → 確認 Guardian policy → 觸發 Decision Lease → 等 audit log」這條 flow，目前 v5.7 文檔 0 mockup
- **為何屬「執行性」（非邏輯）**：thesis 沒錯（Earn 該過 Guardian），但要實際讓 operator 在 Sprint 1B 末（W3）真的點按鈕 stake $200，需要先決定（a）GUI 落在哪個 tab（b）誰寫前端 JS（c）防誤觸閘位（d）APR 顯示更新節奏。文檔現狀讓 PA 不知道派誰、E1a 不知道在哪裡寫、A3 不知道審什麼。
- **Must-fix 建議**：
  1. **Sprint 1A 工時表加一行**「E1a Earn stake form mockup + governance/live tab 歸屬決策」8-12 hr
  2. **Sprint 1B 工時表加一行**「E1a Earn stake/redeem manual UI + 二次確認 modal + audit log viewer」16-24 hr
  3. **§4 明示防誤等級**：stake = 資產寫入 → 等同「平倉單 symbol」級（Lv 3：modal + 打字金額確認 + Operator role gate）；auto-redeem trigger 觸發必須 toast 通知 + 24h audit footer
  4. **tab 歸屬決策**：建議落在 `governance` tab 新增 sub-section「Asset Movement (Earn)」，避免新增 17th tab 增加學習曲線

### Risk 2：Sprint 7 Advisory Allocator「operator approves via Console」未指 console 哪裡 + 工時表無 GUI 行

- **嚴重度**：HIGH
- **位置**：v5.7 §7「Sprint 7 (W24-27): Advisory Allocator activation - Generates monthly proposals - Operator approves via Console」+ §9 Sprint 7 工時 110-150 hr
- **描述**：
  - §7「multi-component reward function + monthly proposals + operator approves via Console + Decision Lease + Guardian + Stage gate」
  - §9 Sprint 7 包括「Top-5 + Advisory Allocator + Live promos」110-150 hr，**未拆 Allocator GUI 工時**
  - Console 16 個 tab 沒有 allocator 位置：proposal 不屬於 `governance`（單筆授權）也不屬於 `strategy`（部署）也不屬於 `learning`（學習指標）
  - monthly proposal 涉及「多策略當前 weights → proposed weights → reward function breakdown → operator approve/reject/edit」這條 review flow，v5.7 0 mockup
  - 認知負荷：operator 一個月 review 一次，需要看「上月實績 vs proposal 預測差距」否則純拍腦袋 approve → 80% approval rate gate（§7 Y2 自動化 trigger）失去意義
- **為何屬「執行性」（非邏輯）**：Advisory 設計合理（人在 loop），但 monthly review 沒 GUI = 變成 markdown 報告 + 人工算 reward → operator 60 sec 就 approve 完，**80% approval rate gate 變成統計噪音**，Y2 auto-activation 證據基礎被掏空。
- **Must-fix 建議**：
  1. **Sprint 7 工時表拆**「E1a Allocator monthly proposal viewer + diff view + approve/reject form」20-30 hr
  2. **§7 補章**：Allocator GUI 落 `agents` tab（現「本地 5-Agent 只读状态 / proposal relay」已有 proposal 概念基礎），新增「Allocator Proposals」sub-section
  3. **防 rubber-stamp**：approve 路徑強制 modal 顯示「上月 reward 實際 vs predicted Δ」+ 強制 operator 在輸入框打「reviewed reward breakdown」短語 → 才能 enable approve button
  4. **§7 Y2 gate 補語**：「>80% approval rate」需附「approval 有實質 review evidence」副指標（modal 停留時間 + 改 weight 比例），純 click-through approval 不計入 gate 通過

### Risk 3：5 策略並行 + Macro + On-Chain Counterfactual 無聚合儀表盤 — operator 認知負荷在 Sprint 6 末爆炸

- **嚴重度**：HIGH
- **位置**：v5.7 §1（5 策略 live 時間軸）+ §5（macro/on-chain counterfactual logging Y1）+ §8 Sprint 1A「Macro calendar feed NEW」
- **描述**：
  - §1 Sprint 6 末（W23）live 策略 = C10 + Unlock SHORT + Pairs + C13 + Funding short = **5 個並發策略，每個自己的 Decision Lease/positions/PnL/kill switch**
  - §5 增加 macro 與 on-chain counterfactual 兩個「read-only logging」流 + counterfactual A/B
  - README §22-42 現有 tab `system` 是總覽，但設計為 1-2 strategy 時代；`strategy` tab 是部署，不是並行監控
  - 認知負荷檢查（ux-checklist 第 2 維度）：單頁 ≤ 7 個關注點 — 5 策略 × 4 metric (PnL/DD/Sharpe/exposure) = 20 個關注點 + macro overlay state + on-chain signal state + counterfactual divergence = **遠超 7**
  - §5「Y1 末 evaluate counterfactual evidence」需要 6-12 個月的 A/B 比較數據 — 沒有可視化，operator 無法在 Sprint 10 末做出「enable Y2 / retire layer」決策
- **為何屬「執行性」（非邏輯）**：counterfactual logging 設計合理（DB 記錄）但 evaluate 動作需要 visual diff 工具，否則 §5「Y1 末 if overlay 真 alpha → Y2 enable」決策變成「翻 DB 表」= 不可行 operator 行為。
- **Must-fix 建議**：
  1. **Sprint 5-6 工時表加**「E1a Multi-strategy aggregate dashboard」25-35 hr — 5 策略 grid + 每策略 traffic-light 狀態（healthy/warn/critical/halted）+ 一鍵 drilldown
  2. **Sprint 8 工時表加**「E1a Counterfactual A/B viewer」15-20 hr — macro/on-chain layer ON vs OFF 收益對比表 + winsorized t-stat 視覺
  3. **dashboard 設計**：套 ux-checklist「數字成組 / 顏色語義一致」— 每策略卡片用 traffic-light 取代純數字，避免認知 overflow
  4. **§5 Y1 末 evaluate 條款補一句**：「evidence quality 包含 dashboard usage telemetry — operator 是否真的在每月 review counterfactual delta；若 0 次 view → 同樣不計 gate 通過」

---

## 2. Hours sanity check（A3 角度）

v5.7 §9 工時表 1,190-1,590 hr / 11 個 sprint。A3 抽 GUI 工時，發現：

| Sprint | v5.7 列工時 | A3 拆 GUI 部分 | GUI 缺口 |
|---|---|---|---|
| 1A | 60-80 hr | Earn API recorder GUI（APR readonly viewer）8-12 hr | **8-12 hr** |
| 1B | 50-70 hr | Earn stake/redeem manual UI + modal 16-24 hr | **16-24 hr** |
| 4 | 160-210 hr | Top-1 live 策略卡片 + macro overlay status badge 10-15 hr | **10-15 hr** |
| 5-6 | 290-380 hr 合 | Multi-strategy aggregate dashboard 25-35 hr | **25-35 hr** |
| 7 | 110-150 hr | Allocator monthly proposal viewer 20-30 hr | **20-30 hr** |
| 8 | 110-150 hr | Counterfactual A/B viewer + decay detector alert 15-20 hr | **15-20 hr** |
| 10 | 70-100 hr | Y1 review aggregator + copy trading evidence gate dashboard 10-15 hr | **10-15 hr** |

**GUI 工時總缺口：~104-151 hr**（≈ v5.7 總工時的 8-10%），未列入 §9。

對照：v5.6 §7 Sprint 1 工時 100-130 hr 也未列 GUI 工時，但 v5.6 Earn 設計是「passive 6% APR yield + no governance」（簡單），v5.7 把 Earn 升級為 Guardian/Decision Lease 工作流 — GUI 複雜度躍升但工時未隨。

**結論**：§9 1190-1590 hr 在 GUI 維度 underestimated ~104-151 hr；若按 v5.6 → v5.7 修復精度標準，這是第 7 個應修而未修的 reviewer issue。

---

## 3. 未識別的依賴 / 阻塞

1. **E1a (前端 engineer) 在 v5.7 全文 0 次提及** — Sprint 7 Allocator GUI 與 Sprint 1B Earn stake form 都需要 E1a 工時，但 §9 未列、§13 references 未指 E1a profile。PA dispatch Sprint 1A 時若不指 E1a，會默認 E1 處理 → 但 E1 工時表已滿。
2. **A3 在 v5.7 sprint sign-off chain 缺席** — v5.6 §7 Sprint 1 governance + sensor 工作未列 A3 review gate。Earn stake / Allocator approve 是 high-risk operator surface，按 CLAUDE.md §八「Sub-agent IMPL DONE 必走 A3+E2 對抗性核驗」應在 Sprint 1B / Sprint 7 sign-off 強制 A3 + E2 雙審。
3. **OPENCLAW_ALLOW_MAINNET=1 gate vs Earn stake** — v5.7 §4 Earn stake 也是資產寫入，但 CLAUDE.md §四「真 live 需 5 個閘」是針對「下單」設計。Earn stake 在 Demo 階段不需 mainnet=1，但在 Live 階段是否需要過同一閘？v5.7 未定義 — A3 視角這是「同色按鈕不同邏輯」紅旗（ux-checklist 第 4 維度一致性）。
4. **Counterfactual log 顯示位置缺定** — §5 counterfactual logging Y1，§9 0 GUI 工時，但 §10「Y1 末 evaluate」需要 viewer。若 Sprint 1-9 全程 0 GUI，operator 到 Sprint 10 才看 = 樣本不足以做 Y2 enable 決策（沒有過程中發現信號就停 / 推進的能力）。

---

## 4. 對 PA+FA 匯總的必收 top 3

1. **§9 工時表加 GUI 列**：每 Sprint 拆 E1a GUI 工時行；總計補 ~104-151 hr；不加會在 Sprint 1B 末 Earn stake 上線時臨時掉鍋；建議補完後 §9 總工時改為 1,294-1,741 hr。
2. **Console tab 結構決策必須在 Sprint 1A 完成**：Earn → 落 `governance` 內 sub-section / Allocator → 落 `agents` 內 sub-section / Counterfactual → 落 `learning` 內 sub-section；不增第 17 個 tab，避免認知曲線陡升。決策結果寫入 ADR-0030 草案（v5.7 §12 已 propose ADR-0030 Earn movement policy，加 UI 位置條款）。
3. **A3 sign-off gate 列入 Sprint 1B / Sprint 7 / Sprint 8**：對應 Earn stake / Allocator approve / Counterfactual viewer 三個 high-risk operator surface。每個 sign-off 必須包含 ux-checklist 5 維度 + 防誤觸 Lv 3+ 確認 + browser-native confirm/prompt 禁用（援引 A3 memory 2026-04-24 Live Tab 教訓）。

---

## 5. Sprint 1A 派發前 must-fix

- [F1] §9 工時表加「E1a Sprint 1A Earn APR readonly viewer」8-12 hr + ownership 明示
- [F2] Tab 歸屬決策：Earn 在哪個 console tab — 寫入 v5.7 §4 或 ADR-0030 草案
- [F3] §11 第 6 個 reviewer condition「Earn 防誤觸 SOP」補上 — 不是只說 Guardian policy，要說 modal Lv3 + 打字確認
- [F4] A3 sign-off 列入 Sprint 1A 末檢查項（避免 Sprint 1B 第一天 stake form 已寫但無 UX review）

---

## 6. Sprint 1B-3 should-fix

- [S1] Sprint 1B「Earn first $200-400 manual stake」必須附「該操作的 GUI flow 文檔」（mock-up / wireframe / state diagram 三選一）
- [S2] Sprint 2 Alpha Tournament 排名 GUI — 5 候選策略 ranked candidate list 需可視化（operator 在 Sprint 3 末要決策 top-1 build），目前 §9 Sprint 2 工時 110-150 hr 未列
- [S3] Sprint 3 Top-1 build 末附 strategy card mockup（為 Sprint 5-6 multi-strategy aggregate dashboard 預埋一致樣式）
- [S4] Macro overlay 「24h before FOMC → halt new put sales」這條 rule（§3）— operator 看到 halt 必須有 banner + reason，現 v5.7 0 UI mention

---

## 7. 可優化 / 拆分 / 並行

- **Console tab 不擴張原則**：strict 16 → 16；新功能落 sub-section 或 collapsible card。避免出現 v5.5/v5.6 → v5.7 演進中「framework expansion 對應 tab 擴張」反模式。
- **Sprint 1A 並行**：tab 歸屬決策（A3 + PA + operator）與 Earn API integration（E1）可並行，避免 GUI 決策阻塞 backend 啟動。
- **Sprint 7 Advisory Allocator 拆並行**：reward function 工程（MIT/AI-E）+ proposal viewer GUI（E1a + A3）+ approve flow Guardian 接線（E1）三條並行；現 v5.7 Sprint 7 110-150 hr 是合計但未拆 owner。
- **Counterfactual viewer 可後置**：Sprint 8 落地即可（不需在 Sprint 2 macro/on-chain setup 時就建），但 schema 必須在 Sprint 2 設計時為 viewer 預留（時間維度 join key + winsorized field），避免 Sprint 8 重做 schema。
- **複用 A3 既有教訓**：browser-native `confirm()` / `prompt()` 禁用（A3 memory 2026-04-24 §2 教訓） — Earn stake / Allocator approve 路徑全部用 custom modal，寫入 Sprint 1B / Sprint 7 sign-off invariant。

---

**A3 UX AUDIT DONE: 7.5/10**

評分說明：thesis 與工程精度（6 reviewer fix）皆通過；扣 2.5 分主要在（a）GUI 工時系統性缺失（−1.5）（b）Earn stake / Allocator approve 兩個 high-risk surface 無 UX 設計依據（−0.5）（c）Console tab 歸屬未決策（−0.5）。Sprint 1A 派發前若補完 §5 must-fix F1-F4，evaluator 可升至 8.5/10 並 unconditional GO。
