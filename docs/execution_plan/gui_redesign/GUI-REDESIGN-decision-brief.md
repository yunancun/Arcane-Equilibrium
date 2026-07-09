# 玄衡 Console 改版 · 決策交接書

> 狀態：**方向已定，實作待命**（operator：「這輪先到樣品為止」）。
> 本檔是恢復點：任何 session 讀此即可續作，無需重跑研究。

## 0 · 已鎖定的三個決策
1. **視覺基調 = S1「Terminal」克制平面終端**（單色 chrome＋語義色＋等寬數字＋髮絲線扁平；冷調近黑）。
2. **架構終局 = 絞殺 iframe → 單文件 shell**（strangler-fig，漸進；交易關鍵 tab 最後遷、留 fallback）。
3. **框架 = 保留 Vanilla JS**（守 CLAUDE.md/gui-style-guide 硬規；不引入 React/Vue）。

## 1 · 冷審計根因（量化，全有檔案證據）
現有：18 tab / iframe-per-tab / 34,363 LOC / 1.8MB。「臃腫感」= 三個結構性根因：
- **A 架構**：iframe-per-tab → 143KB 共享 JS＋303 行 CSS **每個 iframe 重複解析**；7 種裸字串 postMessage；跨 frame 焦點/熱鍵碎裂；**每 tab 各開一條 WebSocket**（各有新鮮度時鐘＝安全隱患）。
- **B token/樣式分叉**：token 三處（styles.css＋common.js 硬編碼＋console.html 內聯）；**1,375 內聯 style=**；**83 hex／906 色字面**；盈利綠 4 套、紅 5 套 → 違反自訂原則「顏色語義固定」。
- **C KV 牆無披露**：stock-etf 一頁 19 tile＋20 常開面板＋**712 KV／0 details**；risk/governance 200+ 內聯手繪；**~480 處中英雙標**把標籤寬翻倍。
- **IBKR**：塞進 core 當 flat tab（crypto 攤 9 tab）；「零真錢/live 拒絕」只是小 chip；綠「false」紅「false」並存（裸布林上色）。
- **必須保留**：Live tab 真錢護欄（紫紅雙下劃線＋⚠REAL FUNDS＋LiveDemo 不冒充 Mainnet）＝全站最佳實踐；`oc-*` 已是 103-class 共享底座（收斂非重寫）。

## 2 · 設計系統規範（token 三層，Radix/Geist/Open-Props 方法）
**間距(4px)** `--space-1:4 -2:8 -3:12 -4:16 -5:24 -6:32 -7:48 -8:64`
**字級(~1.2, 13 base)** `11 / 12 / 13(base) / 14 / 15 / 20 / 27`；行高 tables 1.25、prose 1.5
**圓角** `--r-1:5 -2:8 -3:12`（資料控件 4–8，禁藥丸化資料控件）
**字體** UI=system-ui 疊 `Microsoft YaHei`；數字=mono 疊 `font-variant-numeric:tabular-nums slashed-zero`（所有 price/qty/PnL/%/ts/id 右對齊）
**暗色語義面（亮度分層非陰影）** app `#0a0c10` / surface `#101319` / raised `#161a21` / hover `#1c212a`；border-subtle `#202632` / strong `#313947`
**文字** primary `#e7edf4` / secondary `#98a2b0` / muted `#656e7c`
**語義色（各一，暗色調至 ~4.5:1）** `--pos #3fb950` `--neg #f85149` `--warn #d6a419` `--accent #4c8dff`（僅數據）`--live #ff5457`（真錢專屬，主題不可稀釋）
**冗餘編碼**：PnL 帶 +/− ＋色；方向 LONG/SHORT 文字＋色；狀態 pending=amber/filled=green/rejected=red 各配 icon（去色可讀）
**密度**：`[data-density=compact]` 收窄 row/pad/字級（研究要拿**中文字串**測 CJK 行高，勿只用英文調）
**主題**：primitives 不變，只覆蓋 semantic 層；default=prefers-color-scheme，`data-theme` 兩向覆蓋，`<head>` 同步 setter 防 FOUC
**唯一 sanctioned 內聯**：JS 動態值寫 scoped var（`el.style.setProperty('--bar',v)`），class 消費 —— 其餘 CI grep 禁 `style="`/`<style`/裸 hex

## 3 · 資訊架構：lane × environment
主軸=資產通道（**Crypto Perp·Bybit** / **Stock·ETF·IBKR**，平級），次軸=環境階梯（研究→Replay→Paper→Demo→Live），橫切=治理/風控/AI/學習/監控/設置。每個寫入面**只有一個家**（mode 開關只在治理；risk 降級只在風控，治理只連結不複製）。取代現有 6 主題組。IBKR 升為 lane workspace（Account/Orders/Research/Recon/Gates 子頁，隨成熟度長大），治理橫幅置頂，712 行矩陣收進審計抽屜。

## 4 · 分階段路線圖（交易安全排序）
- **Phase 0（可逆·留 iframe 內·零架構風險）**：抽單一 `tokens.css` 全 tab `<link>`＋刪 JS 注入 `:root`；1,375 內聯→~15 utility class；83 色→~12 token；全站數字排版；IBKR 裸布林→語義＋治理橫幅。**← 這步消掉八成臃腫感。**
- **Phase 1**：建單文件 shell＋view-router＋**單一共享 WS 層**（一連線一時鐘，per-view 新鮮度徽章）；先遷只讀低風險（Overview/System/Governance/Edge-Gates／整個 IBKR lane=GET-only）。
- **Phase 2**：逐一遷交易關鍵 tab（Live/Risk/Paper/Demo），feature-flag＋保留 iframe fallback＋遷前快照 Live 護欄清單。
- **Phase 3**：確認 legacy index.html＋~4,100 行 app-*.js 無真調用者後下架，刪 iframe/postMessage。

## 5 · 風險守則（對抗 critic）
先清點 Live 護欄與客戶端審計事件再動；`--live` 熱紅不可被主題稀釋；單一 WS 層保留 per-view 新鮮度徽章（never 0.00 當 loading）；密度 token 拿中文測；**每遷一 tab 加冒煙測試——目前 GUI 零自動化回歸網＝最大執行風險**；未知值=em-dash，stale=半透明＋徽章。

## 6 · 產物指針
- 樣品 S1 Terminal（採用）：https://claude.ai/code/artifact/07c769ec-b340-4118-812f-27decdaa2ea8
- 樣品 S2 Cockpit（未採用，備參）：https://claude.ai/code/artifact/23c24c3a-8b5e-4586-ac35-e33a06a82b7b
- 本地樣品：`scratchpad/gui/console-redesign-sample.html`、`…-sample-2.html`
- 研究/審計原始結果：`scratchpad/gui/res_1..6_*.json`（設計系統/交易審美研究＋架構/UX/IBKR 審計＋對抗 critic）
- GUI 根目錄：`srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/`

## 7 · 說「開工」時的第一動作（GUI Phase 0）
派 **PM→PA→E1a→E2→E4** 鏈執行 **Phase 0**（範圍見上，全可逆、留 iframe 內）。先由 PA 定 `tokens.css` 契約＋utility class 清單＋IBKR 語義映射，再 E1a 落地，E2 對抗審＋E4 加首批冒煙測試。

## 8 · 內容守恒審核結果（2026-07-08，零靜默丟失已量化證明）
盤點 210 個功能面：KEEP 115／RELOCATE 38／MERGE(去重) 26／COLLAPSE(折疊) 12／FLAG-DEAD(刪除候選,需證據) 19。115+38+26+12+19=210，總和守恒。三條缝已驗：mode 控制/risk 降級→去重到治理唯一家＋只讀鏡像；三個 close-all 按環境各留；Live「緊急停止(撤授權) vs 平倉」是兩種能力都留。**唯一灰區**：`app-learning.js`（觀察/教訓/假設/實驗**唯一錄入表單**）現狀已是孤兒（tab-learning.html 未載入它）——遷移時明確問 operator「復活還是退役」，不靜默刪。19 個 FLAG-DEAD 多為已下架殘留（HTTP 410 端點/torn-out modal/legacy index.html 層），刪前 grep 證明零調用者。

## 9 · IBKR 真實接入 · 兩條腿（2026-07-08 PM→CC→FA→PA 評估）
**裁決：FEASIBLE / `CERTIFIABLE_IF_GATES_PASS`。** 類型/契約腳手架已建 ~90%（validator/secret-slot/gate/TOML 轉換器皆有 `source_template()`）；缺的是產出真值的 runtime＋normalizer 同步演進。邊界永不變：**只讀/零真錢/live·tiny-live 結構性拒絕**。

**腿①（GUI，等「開工」）**：IBKR lane 改成誠實「就緒/治理/config 控制台」。含 real-NOW 誠實修：`tab-stock-etf-auth-account.js:187-197` 現在在 `account_snapshot_present:false` 仍渲染 `cash=0`（假 $0 反模式）→ 數字關進 `present && accepted`。

**腿②（後端，治理閘後）**：
- **解鎖鑰匙（operator 必簽）**：新 ADR/AMD ①授權 Phase 2 外部接觸 ②顯式修訂 SDK/socket 靜態守衛邊界。無此而動守衛=未授權改硬邊界=BLOCKER。「首次只讀 healthcheck 即外部接觸，不豁免」→ 一次性 operator 批准。
- **架構**：IB Gateway paper（loopback 4002）＋原生 TWS API socket，由 openclaw_engine 新受閘 Rust 模組說話（非 Python；Client Portal Web API 契約禁用）。密鑰槽 readonly/paper 只存指紋，live 槽結構性拒絕（三方指紋三角校驗）。
- **crux**：normalizer（負空間證明閘，現「有真值即違規」）須與 Rust 發射端同 PR 演進為「有真值但缺 PASS+attestation 血統才違規」；gate=BLOCKED 注入真值仍 fail-closed（E2 第一審查項）。
- **快贏**：風控 TOML→Rust（`from_source_config()` 已存在，未被 runtime 調用）→ 顯示 config=強制 source-of-record。~0.5–1d，不開下單路徑。
- **安全前置（CC MEDIUM）**：stock_etf 靜態守衛只在 E4 pytest 跑，未接 `ci.yml` → 加 `stock-etf-static-guards` CI job 為 G0.5。
- **工作圖 P0–P6**（硬依賴鏈，~15–23 E1-天，全 flag 門控，回滾=關 flag＋停 Gateway，只讀零 DB migration）：P0 風控 TOML 接線 → P1 密鑰槽 loader → P2 Phase-2 gate producer(sealed PASS) → P3 IB Gateway＋Rust 只讀 TWS 客戶端(spike) → P4 dispatch 分叉＋connection-health IPC/route＋normalizer 同步 → P5 帳戶/持倉/訂單讀＋session attestation → P6 行情/合約(需新 positions-row/quote-bar-row 契約)。
- **治理簽署鏈**：G0 新 ADR/AMD(Operator+PM+CC/FA/PA) → G0.5 CI 守衛 → G1 external-surface gate(E1→E2→E4→BB→E3→QA→CC/FA) → G2 probe 契約 → G3 secret slot(E3→BB→Operator) → G4 首次外部接觸(Operator 一次性批准) → G5 帳戶/行情讀 → G6(獨立)Phase 4 GUI runtime。
- **永不做**：任何寫/下單/live/tiny-live/margin/short/options、建 `ibkr/live/` 槽、env-var 憑證 fallback、Client Portal Web API、entitlement 購買、DB migration、自動升級、複用 Bybit `submit_paper_order` IPC。
