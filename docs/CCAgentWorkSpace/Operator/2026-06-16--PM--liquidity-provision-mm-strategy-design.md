# 流動性提供 / 做市策略設計 — 12-campaign 價格預測範式封閉後的範式跳躍

**日期** 2026-06-16 · **作者** 主會話 PM（PA-design 子代理因 API 500 連續失敗，改主會話 inline 撰寫 + 自我對抗審查）
**狀態** DESIGN-ONLY（無代碼、無部署）；所有可部署細節 recorder-v2-gated · **honest probability：MEDIUM-LOW，但為剩餘唯一活路**

---

## 0. 為什麼需要這份設計（範式跳躍的觸發）

12 個 campaign 跨維度窮盡了 **$0 價格預測範式**：頻率（HF sub-cost / LF arbitraged-down-beta）× 信號型（reversal/momentum/carry/microstructure/lead-lag/liquidation/listing 全 NO-GO）× 成本側（fee 牆固定；listing fee 可忽略仍無 edge）。

**這不是「市場無 edge」**——真 beta-clean 信號確實存在：
- PCA-residual cross-sectional reversal (1m)：gross ~0.8-1.5bp/turn
- OFI@10s：resid-IC +0.031，broad（28/36 同號），bounce-test 過
- **BTC 2s return → alt residual 5s lead：resid-IC +0.077（t=30.8，32/40 alts），最強，1m 不可見**

**問題是它們全部 sub-taker-cost**（per-turn gross < 11bp taker / 4bp maker RT）。operator 鐵則「市場必然可主動盈利」在最深層被 vindicated；只是**為方向性 taker 價格預測設計的那一角落**已窮盡。

範式跳躍（operator mandate「挖到頭→跳出範式重新構思」的直接執行）：**從「預測方向賺價差」轉為「提供流動性收價差」**（alpha class #3，與已窮盡的 class 1/6 預測型正交）。

---

## 1. 核心 reframe — 為什麼這 sidesteps 殺死 12 campaign 的牆

| | 價格預測範式（已死） | 做市範式（本設計） |
|---|---|---|
| 利潤公式 | `predicted_move − cost` | `captured_half_spread − adverse_selection − maker_fee` |
| edge 來源 | 預測（信號要 > 成本） | **結構性 spread**（被付錢提供流動性）|
| 信號角色 | 利潤本身（撞牆：0.5-2.5bp < 11bp）| **adverse-selection 規避器**（skew/pull quote，不需打贏成本）|
| 致命 gate | 成本牆（固定，無解）| fill-conditional adverse selection（recorder-v2 可測）|

**關鍵洞察**：信號不需要打贏 fee（它們打不贏）。它們只需要把 adverse selection 降到 `spread − fee − reduced_adverse_selection > 0`。利潤源是 spread（結構性、機械性，非預測），完全符合 operator「偏結構性·機械性 edge 非靠預測」的 mandate。

---

## 2. Edge 來源算術（誠實版）

- campaign-8 實證：~25/37 symbol 的 half-spread > 4bp maker（DOT/UNI/LINK/ARB 等 wide-spread alts；majors BTC 0.34bp / ETH 0.84bp 太窄賺不到）。
- 掛 maker bid 成交 = 在 bid 買入（mid 下方 half-spread）。若在 ask 平掉（捕另一半 spread）：**gross/RT = full_spread − 4bp maker RT**。10bp spread 的 symbol：10 − 4 = **+6bp gross**，IF 雙邊無 adverse selection 都成交。
- **但 adverse selection 是本質**：你的 bid 正是在價格下跌時被知情賣單打到 → 你常持到 loser。`NET = spread − fee − adverse_selection × P(fill_adverse)`。
- campaign-8 dose-response 已警示：**NET 符號完全卡 queue position**（front-of-queue +5.5bp / 5bp-queue ≈0 / back-of-queue −6.9bp）。

---

## 3. 信號的角色（真正的創新點）

OFI@10s + BTC-lead@5s + PCA-residual 給出短 horizon fair-value/方向估計，用於：
1. **SKEW quotes**：信號示價將漲 → 偏多掛單（bid 更積極 / ask 後撤），inventory 順信號傾斜。
2. **PULL/WIDEN 將被 run over 的一側**：OFI/BTC-lead 強烈指向某側 → 不在該側 rest（避開 adverse fill）。

這是 **informed market making**：圍繞「你的 fair value（mid + 信號）」報價而非市場 mid。uninformed flow 以對你有利的價格 fill 你；你避開最糟的 informed fill。

---

## 4. 驗證計畫（recorder-v2-gated）

唯一決定 viability 的未知 = **fill-conditional adverse selection net of half-spread**。

- recorder-v2 full-L1 event stream（已 shipped commit `df4dd58b`，gated OFF，CP-1 後 enable，accruing）→ 建 fill-sim：建模 queue position（size-at-touch Q0 + 同側 aggressor 消耗 + cancel；僅 cumulative_consumed ≥ Q0 才 fill），模擬 informed-skewed vs naive quoting，量 fill-conditional adverse selection。
- 延伸 campaign-8b 的 `adverse_selection_framework.py`（已 scaffold，returns gate-stub on sampled data，待 full-L1）。

| CP | 時點 | 內容 | gate |
|---|---|---|---|
| CP-1 | ~1wk | OFI/BTC-lead 在新 regime 窗複驗 holds | t≥3、IC band、same-sign≥0.7 → enable recorder-v2 |
| CP-2 | ~2wk | l1_events 健康 + bad-tick 從 14.7% 降趨近 0（驗 stateful 重建）| storage 在 band、rate-cap 未誤觸 |
| CP-3 | ~4wk（≥10-12 regime-day）| **fill-sim go/no-go**：informed-skewed passive net 半價差在真 queue 模型下 survive？| net>0 跨 regime + DSR/PBO → 進 demo build |

---

## 5. 風控框架（全新風險剖面）

做市 = 與當前 taker/intent flow 完全不同的風險：
- **Inventory risk**：fill 累積部位，暴露於 trend。
- **Getting-run-over（adverse-selection 死法）**：trending move 把你整批 resting size 在錯的一側成交。
- **雙邊曝險**。

限額：per-symbol max inventory、aggregate inventory cap、inventory 破限 auto-flatten、high-vol/trend regime pull-all-quotes（CognitiveModulator 式）、沿用 3%-risk + 25-symbol 框架改造。

- **survival-first**：demo-first（既有 gradient）、fail-closed、任何 live 走 5-gate。做市是**新 execution mode** → 須走完整 PA→E1→E2→E4→QA 鏈 + demo soak 才談 live。
- **Kill-switches**：inventory 破限、drawdown、signal staleness、spread collapse。

---

## 6. 誠實 soundness 自我對抗審查（PM 兼 QC 角色，不 hype）

**站得住的部分**：
- edge 源（spread）在 wide-spread alts 上結構性真實；genuinely sidesteps 價格預測成本牆；找到的信號真實、可能 plausibly 降 adverse selection；是唯一未測的 alpha class #3。

**硬實話（必須直視）**：
- **wide spread 本身常是「低量 / 高 adverse selection / 高 inventory risk」的標誌**。half-spread > 4bp 的恰是 illiquid alts —— 低 fill 量、難 scale、一旦 move 來懲罰性。你可能**主要在錯的時候被 fill**。
- campaign-8 dose-response 已示 NET 在 ~5bp queue position 處穿零；**無 maker rebate（campaign-10 確認不可及）下 margin 很薄**（spread − 4bp − adverse selection）。maker rebate 會讓它 robust，但 institutional-MM-gated。

**probability 讀數**：**MEDIUM-LOW，但為剩餘唯一活路**。單一決定因素 = wide-spread alts 上的 fill-conditional adverse selection —— **唯 recorder-v2 數據（數週）可答**。

**誠實裁決**：
- 值得 recorder-v2 等待（數據已在 ~零邊際成本累積）+ CP-3 fill-sim go/no-go。
- **CP-3 確認正 fill-conditional 經濟性前，不建議建執行代碼**（別為可能為負的 edge 造 maker engine）。
- 若 CP-3 為負 → 做市路徑也誠實關閉，剩餘全為 operator 資源決策（fee tier / 新帳戶 / 機構 MM 程式 / listing live-capture）。

---

## 7. Operator 決策點

1. **CP-1（~1wk）後 enable recorder-v2**（你已決定的時點）。
2. **CP-3 若 fill-sim 正** → 建 maker-quoting execution mode（全鏈）→ demo soak → 漸進 live。
3. **fee rebate 問題在此重現**：maker rebate 會 transform 經濟性；institutional MM program 是閘（operator 商業決策）。
4. **平行 lever**：listing live-capture（V130 collector 部署 → n≥30 → AEG-S3 seconds-horizon harness）—— 同屬「結構性非預測」象限的 operator-timed lever。

---

## 附：主會話不自動執行任何 write（read/write 分離 + survival-first）。本設計為 proposal/architecture，待 operator 決策 + recorder-v2 數據才推進。
