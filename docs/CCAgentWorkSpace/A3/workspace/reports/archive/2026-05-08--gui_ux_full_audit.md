# A3 GUI Cold UX Audit — 2026-05-08

審查員：A3 (UX Auditor) · 工作根 `/Users/ncyu/Projects/TradeBot/srv` · HEAD `4e2d2883`
範圍：16 個 console tabs + 5 個 cards + console shell + login + index + trading
基準：first-time operator 視角

---

## §1 Executive Summary

**整體評分：7.4 / 10**（vs 2026-04-24 的 6.5、2026-03-31 的 6.2）

**過去 14 天進步**：
- D01 Paper 手動下單死按鈕已**整塊 retire**（REF-20 R20-P1-U3）
- D07 Demo close-all silent-fail 已修
- A02 Live `prompt()` 續期已**搬到 Governance Hub**
- 新增 **Edge Gates Tab** 作為 Pre-Live readiness 一屏看板
- 新增 **Agents Tab** 作為 5-Agent 工作台獨立位
- 新增 **Replay Tab**、**Development Tab**（opt-in）
- console.html 增加 6-tab-group sticky bar + 1-6 keyboard shortcut + Live tab「⚠ REAL FUNDS」常駐徽章
- Mobile WCAG 2.1 AA touch target 補丁

**仍需修的痛點**：
- **Settings Tab Decision Lease 永遠顯 false**（hard-coded text 而非真實狀態）
- **`tab-system.html` Mode 切換 confirm modal 無倒計時**
- **Learning Tab `prompt()` 收實驗結論摘要**
- **Governance Hub 仍用 `prompt()` 收 renew reason / tier / review notes**（4 個原生彈窗）
- 死按鈕殘留：`index.html:144-155` legacy fallback、`tab-system.html:452-457` `executeConfirmed()` 對 feed/demo/scanner 仍有死分支
- 新 tab `requiresPaperEngine` flag false 時 Paper 整個 hidden 無提示
- Trigger AI Session cost-est 是寫死的範圍
- 「Decision Lease」「SM-01/02/03/04」「EX-04」依然在 Governance/Risk tab 主視圖暴露

**4 維評分**：
| 維度 | 分 | 較 04-24 |
|---|---:|---:|
| 術語友好性 | 6.5 | +0.5 |
| 操作流完整性 | 8.0 | +1.5 |
| 學習曲線 | 7.0 | +0.5 |
| 錯誤提示質量 | 7.5 | +0.7 |

---

## §2 死按鈕清單（按嚴重度排序）

| # | Severity | 位置 | 按鈕/元素 | 真實 backend 狀態 | 建議 |
|---|:---:|---|---|---|---|
| 1 | **Critical** | `tab-settings.html:393` | `<div class="oc-metric-val">false</div>` 「Decision Lease」 | 假數字 — Sprint 3 Track H IMPL `dbcf845b` 已 LAND，但 GUI 寫死 `false` | 改為 dynamic 從 `/api/v1/governance/lease-router/status` 讀 |
| 2 | **High** | `tab-system.html:81` | 「模拟 Paper」按鈕 → `executeConfirmed` | 唯一仍走真實 `/api/v1/paper/session/<action>`；CONFIRM_MSGS 仍存在 feed/demo/scanner 死分支 | 刪除這 3 死分支 |
| 3 | **High** | `index.html:144-155` | 6 個 quick-action button + 4-metric grid | legacy fallback；users 從 `/` 進入會看到完整 UI；應 301 redirect | 加 meta refresh 或 server-side 301 |
| 4 | **High** | `tab-system.html:81` | Paper tab `requiresPaperEngine=false` 時 silent redirect | console.html:527 silent redirect 到 Replay 無 toast | 加 `ocToast('Paper engine 未啟用')` |
| 5 | **Medium** | `tab-strategy.html:46` | 「+ 创建策略」按鈕 | 真實調用，但 5 策略 7d gross net negative 無預警 | create form 加紅字提示 |
| 6 | **Medium** | `tab-ai.html:49` | 「⚡ Trigger Session」cost-est 寫死範圍 | 不是真實當前 provider/model 的預估 | dynamic 從 current provider 算 |
| 7 | **Medium** | `tab-monitoring.html:77` | 「Open Gateway ↗」 | OpenClaw Gateway declined 仍存在 | status check 後 disabled |
| 8 | **Medium** | `tab-development.html:77` | next_version 卡片 | 誤導 op 以為可加下一個 V | 加說明 |
| 9 | **Medium** | `tab-risk.html:435-443` | 「波动率自动杠杆」chip 「始终启用」 | 無 checkbox / API；I05 老問題 | 改 🔒 icon |
| 10 | **Low** | `tab-paper.html:256-272` | 「📩 手动下单」disabled `<details>` | UI 殼仍存在 | 完全移除或 collapsed-by-default |

**整體死按鈕健康度**：相比 2026-04-24 的 8 個 critical/high，今天剩 **5 critical/high + 5 medium/low**。改善 ~37%。

---

## §3 反人類設計清單（按 operator pain 排序）

### Top 反人類

1. **`tab-system.html:243-252` Mode 切換 confirm 無倒計時 / 無 hold-to-confirm**
   - 用戶點 `🟣 实盘 live_reserved` → 彈窗 → 立即可點「确认执行」
   - 建議：紅色 `live_reserved` 確認按鈕 default `disabled`，5s 倒計時後解鎖；或 hold-to-confirm（按住 3s）

2. **`tab-governance.html:868/872/906/913` 4 個 `prompt()` / `confirm()`**
   - Live auth renewal reason / tier picker / T3 review notes / confirmed_tier 全用 browser-native `prompt()`
   - 在 Firefox 可禁用此 API；移動端 prompt 樣式很差
   - 建議：補自定義 modal + textarea + tier dropdown + review 注意事項

3. **`app-learning.js:359/361` 實驗結論用 `prompt()`** — 兩個連環 prompt；建議改自定義 modal + 三 radio button

4. **`tab-risk.html:155-159` Live 風控修改紅色「確認修改」按鈕無倒計時**（I05 老問題）— Modal 第 2 個按鈕 Enter 直接觸發 → 改 Live 引擎 risk

5. **`tab-strategy.html:407-413` Stop / Pause / Delete 三按鈕一字排開** — Stop（紅）+ Pause（中性）+ 1px 分隔 + Delete（紅虛邊），視覺易誤觸

6. **`tab-live.html:308-313` 「停止 Live」與「緊急停止」並排** — 兩按鈕視覺差異不夠大

7. **`tab-paper.html:362` `sessionStopAll()` 用 browser-native `confirm()`** — 雙引擎停止屬高風險

8. **`tab-system.html:130-160` 5 個 mode button 是純 grid，不是 stepper** — 用戶可從 design_only 直接點到 live_reserved

9. **`tab-ai.html:121` Anthropic API key 「保存」+「清除」並排** — 「清除」沒有 modal 確認

10. **`tab-settings.html` 仍混雜 8 種性質** — Demo Control / Mode / Product Family / Cost-PnL 錄入 / Restart / API Key / Debug / System Info；建議拆 4 sub-tab

### 中等反人類

11. `tab-live.html:309-311` 1px 分隔線太細
12. `tab-risk.html` dirty-bar 不指出哪個區塊
13. `tab-settings.html:138-184` 計劃重啟 3 步無「上一步」
14. `tab-strategy.html` Scanner Score 列無單位
15. `tab-monitoring.html:123` Grafana iframe 硬編碼 `http://trade-core:3000`

---

## §4 不清楚之處清單

### 工程術語暴露

1. `tab-governance.html:106` SM-01 / `:158` SM-02 / `:199` SM-03：abbr tooltip 屬進步，但縮寫本身對 operator 無意義
2. `tab-system.html:75` 「阶段标签」mc-val = `Live_Ready ⚠️` / `LiveDemo` 對 first-time op 模糊
3. `tab-live.html:235-239` 「engine_kind != 'live'」integrity-fail view 會驚慌
4. `tab-risk.html` P0 / P1 / P2 三層卡 — 標題對 op 模糊
5. `tab-edge-gates.html` `[33] [38] [40]` 數字 ID 對 op 是隨機數
6. `tab-agents.html:285` 「思考預算」是工程術語
7. `tab-live.html:443-451` Trust status bar T0/T1/T2/T3 op 看不懂層級
8. `tab-governance.html:163-167` 「決策租约」learn-more body 工程化
9. `tab-paper.html:99-105` 「P3 待啟用 — calibration not complete」disabled subtab
10. `tab-settings.html:393` 「Decision Lease」value=false op 看不懂

### 顏色 / Icon 語義模糊

11. `tab-strategy.html:30-32` chip：active 綠 / paused 黃 / stopped 灰；stopped 主動 vs crash 不分
12. `tab-live.html` mainnet 紫紅 vs livedemo 橙與其他 chip 不一致
13. `tab-system.html:71-75` 5 個 metric tooltip 才見原文工程值
14. `tab-monitoring.html:73` 「Channels」永遠是 0
15. `console.html:178` 「shadow_only」mode-tag tag-green — 紅警告語意但用綠色

### 數字無單位 / 無上下文

16-20: Scanner Score 0.72 無 0-1 vs 0-100；平均成本/推理 無 trend；Gate cells 無 ✓/✗ 對比目標；feed-stats 3600秒 應改 1h；Dirty Files count 不知是什麼

---

## §5 可優化之處清單

### 高 ROI 優化

1. **沒有全局 Dashboard / Landing**：進入默認 tab-system 但 6+ 卡片，需 scroll；建議頂部加 5-metric 一屏看板
2. **缺少 keyboard navigation**：1-6 group shortcut 有，但 tab 內無；`Esc` 不關閉 modal
3. **`tab-governance.html` Audit Trail 無 filter / search / pagination**
4. **`tab-strategy.html` 100 cards 一字排開**：沒搜索 / filter
5. **Auto-refresh 期間無 visual heartbeat**
6. **`tab-ai.html` Provider 卡片 6 格 grid 固定** — 第 7 個 provider 需改 HTML

### 中 ROI

7-15: 貨幣切換無 localStorage / 平倉 1s delay / Save 後無時間戳 / 平倉無滑點預估 / Review Queue 不突出 / 模式升級流程圖只是裝飾 / 30s auto-refresh 太頻 / Grafana fail 無重試

### 低 ROI

16-20: API Key dialog Enter 不觸發 / cookie-auth 工程術語 / migration grid expand 異常 / Balance input 無單位 / Replay Refresh 無 loading

---

## §6 資訊密度評估

**過載 tab**：live (14 sub-section) / risk (12) / governance (12) / settings (9 種性質)
**典範**：edge-gates (4 summary metric + readiness checklist)
**整體**：4 tab 過載，平均 ~9 sub-section，超過 UX 慣例 7

---

## §7 錯誤訊息品質

**良好範例**：`tab-live.html:1546-1547` Live phantom-view fallback / `tab-paper.html:464-465` 連線失敗灰字 + 「↺ 重试」

**需改進 12 處**：
1-12: `操作失败` / `删除失败` / `排程重啟失敗` / `触发失败` / `平仓失败` / `风控配置保存失败` / `'✗ ' + msg` 後端英文 HTTP error / autoScan / gateBox edge-muted / 連不上引擎 humor 無「立即重試」 / Grafana fallback / s-api Offline 不知是什麼

**建議**：建立 unified error envelope `{ status, reason_code, user_message_zh, remediation }` + GUI 統一渲染

---

## §8 權限視覺化

**良好**：Live tab「⚠ REAL FUNDS」常駐徽章 / Mainnet 紫紅 / LiveDemo 橙 / live_reserved (locked) disabled option

**需補強**：
1. mode-tag tag-green 對 shadow_only 是錯誤色語意
2. Operator role / Researcher / Viewer 識別缺
3. T0/T1/T2/T3 顏色：T0 灰應提醒「最低權限」
4. iframe 子頁無法獲得父視窗 mode
5. API Key 槽位 demo / live_demo / live 用同樣 UI
6. OPENCLAW_ALLOW_MAINNET=1 env 狀態不顯
7. OPENCLAW_LEASE_ROUTER_GATE_ENABLED=0 flag 不顯
8. SM-04 De-escalate 默認 `display:none` 看不到時不知為什麼

---

## §9 Mobile / Small-Screen Responsive

**已落實**：5 個 tab 加 `min-height:44px` WCAG 2.1 AA touch target

**仍需改進**：
1. `tab-system.html` 無 mobile media query
2. `tab-live.html` 14 sub-section 過載 + live-control-bar wrap 4 行
3. `tab-strategy.html` 100 cards + orchestrator-bar 不 sticky
4. `tab-risk.html` 雙層 sub-tab 在窄視窗極難用
5. `tab-governance.html` SM abbr 在 mobile 點擊不易
6. `tab-settings.html` 8 種性質滾動極長
7. `tab-monitoring.html` Grafana iframe 在 mobile 只剩 ~300px

**結論**：手機可用度 ~50%。core tab OK，但 live/risk/governance/settings 在手機極不友好

---

## §10 §三 Stale 數字 GUI 假綠

**好消息：GUI 不假綠**。`tab-edge-gates.html` + `tab-live.html` 「Pre-Live Gate 趨勢」段都調用 `/api/v1/strategy/prelive/edge-gates`，背後是 `prelive_edge_gate_trends.py` 直接 query PG，no caching。

**真風險**：「§三 7d 周期數字 vs GUI 即時 24h 數字會不同步」

§三 寫 `[33] live_demo 7d 36.6%` + `[40] 24h n=19 avg net -27.93 bps`。GUI default window 是 7d，但 `[40]` window 是 24h，op 看 GUI 的「24h Avg Net」與 §三 數字會偏離 5-15%。

**建議**：
1. GUI window selector 加 `24h / 7d / 14d / 30d` 4 選項
2. 每個 gate card 顯示 `last_updated_at`
3. 添加 footer chip「§三 對齊：vs healthcheck 上次跑時 [33]=36.6% / [40]=-27.93bps · diff < ±2% PASS」

---

## §11 Agent 追蹤視圖真實狀態

`tab-agents.html` 是 2026-04-28 MVP shipped 後成果。從 Learning Tab 抽出至獨立 Tab。

### 結構

5 cards + feed + governance：A 5-Agent roster / D 思考預算 / E Demo vs LiveDemo fills / C 最近活動 / F 治理租约 + 拒單

### Empty / Error UX

每 card 4-state pattern（loading / empty / error / data）+ humor 「仪表板自己迷路了，30 秒后再试」。

**問題**：
1. 5 cards 同時 error 變成 5 個雷同訊息
2. 「30 秒后再试」沒有 actionable「立即重試」
3. MAG-018 OpenClaw Agent Control disclaimer 仍困惑 op
4. Phase chip「P5 抽出 active」對 op 模糊
5. 4 維 mode badge 工程概念 hard-coded
6. redirect banner 在 Learning Tab 90d 後重新顯示是好設計

**真實使用度**：CLAUDE.md §三 [52] strict PASS messages=2 state_changes=11 ai_invocations=2 很少；op 進來看 cards 全 empty 概率高。

**結論**：UI 設計 A 級，但**真實 row 數少 → empty state 是 default 體驗**。

---

## §12 Top 30 UX Issues（按 operator pain 排序）

| # | Severity | Tab | 痛點 |
|---|:---:|---|---|
| 1 | Critical | settings | Decision Lease hard-coded false |
| 2 | Critical | system | live_reserved 確認無倒計時 |
| 3 | Critical | governance | 4 個 prompt() 收 renew reason/tier |
| 4 | High | learning | 2 連 prompt() 收實驗結論 |
| 5 | High | risk | Live 紅色「確認修改」Enter 鍵可達 |
| 6 | High | strategy | Stop/Pause/Delete 三按鈕一字排 |
| 7 | High | live | 「停止 Live」與「緊急停止」並排 1px 分隔 |
| 8 | High | paper | sessionStopAll() 用 native confirm() |
| 9 | High | system | 5 mode button 純 grid 非 stepper |
| 10 | High | ai | API Key 「清除」用 native confirm() |
| 11 | High | settings | I06 8 種性質塞 1 tab |
| 12 | High | / | mode-tag tag-green 對 shadow_only 錯誤色 |
| 13 | High | (multi) | iframe 子頁無 mode chip |
| 14 | High | live | 14 sub-section 過載 |
| 15 | High | risk | 雙層 sub-tab + P0/P1/P2 mobile 不友好 |
| 16 | High | / | index.html legacy fallback |
| 17-30 | Medium | various | 阶段标签模糊 / SM 縮寫 / [33] ID 隨機 / Phase 模糊 / Esc 不關 modal / Audit 無 filter / 100 cards 無搜尋 / Auto-refresh 無 heartbeat / Trigger Cost-est 寫死 / 平倉無滑點 / dirty-bar 不指明 / 計劃重啟無上一步 / 錯誤訊息 vague / redirect banner 不醒目 |

---

## §13 A3 Verdict

### GUI 整體健康度：**74%**

|  | 分 | 說明 |
|---|---:|---|
| **死按鈕健康度** | 80% | 5 critical/high + 5 medium/low |
| **反人類設計健康度** | 65% | 仍 10 處 Top 反人類 |
| **不清楚之處健康度** | 70% | abbr tooltip 系統大進步 |
| **可優化健康度** | 75% | 新 tab 結構優化 |
| **錯誤訊息健康度** | 70% | live phantom-view 是好範例 |
| **權限視覺化健康度** | 80% | Live REAL FUNDS 徽章是亮點 |
| **Mobile responsive 健康度** | 50% | live/risk/governance/settings 在手機極不友好 |
| **資訊密度健康度** | 60% | 4 tab 過載 |

### 反人類設計重災區

1. **`tab-settings.html`** — 8 種性質塞 1 tab；Decision Lease hard-coded false 是 critical
2. **`tab-governance.html`** — 4 個 `prompt()`；SM 縮寫 + 雙語 + 12 sub-section 過載
3. **`tab-live.html`** — 14 sub-section 過載；停止 vs 緊急停止 視覺差不夠
4. **`tab-risk.html`** — 雙層 sub-tab + P0/P1/P2 三 card 在 mobile 極不友好
5. **`tab-system.html`** — mode 切換無 stepper + 無倒計時

### 改進路線圖建議

**P0（≤1 日）**：#1 Decision Lease hard-coded、#2 live_reserved 倒計時、#3-4 governance/learning prompt() 替換、#16 index.html redirect

**P1（1-3 日）**：#5 live risk 確認倒計時、#6-7 strategy delete + live emergency stop 視覺、#8 paper sessionStopAll modal、#10 API Key clear modal

**P2（1 週）**：#11 settings 拆 4 sub-tab、#12 mode-tag dynamic 色、#13 父視窗 mode chip、#14-15 live/risk 過載拆分、#22-23 search/filter

**P3（>1 週）**：landing page、keyboard nav 全面、mobile retrofit、unified error envelope

### 對比

| 日期 | 整體分 | 死按鈕 | 反人類 | 不清楚 | 可優化 | 錯誤訊息 |
|---|---:|---:|---:|---:|---:|---:|
| 2026-03-31 | 6.2 | 12 | 18 | ~30 | ~25 | 60% |
| 2026-04-24 | 6.5 | 8 | 15 | ~25 | ~16 | 65% |
| **2026-05-08** | **7.4** | **10** | **10** | **20** | **20** | **70%** |

**整體進步**：6.2 → 6.5 → 7.4（+19% in 38 days）

**仍須投入**：Top 30 中 20 個 P0-P2 等待修復，主要在 settings / governance / live / risk / system 5 個 tab；建議下個 sprint 集中改，預計可推進到 8.0/10。

---

**A3 UX AUDIT DONE** · 7.4/10 · 30 issues / 5 critical · 16 tabs audited
