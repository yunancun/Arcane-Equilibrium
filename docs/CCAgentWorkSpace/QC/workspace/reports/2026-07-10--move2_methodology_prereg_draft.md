# QC 預註冊草案 — Move 2：bb_reversion maker 化 fill_sim 重放方法論 · 2026-07-10

**Agent**: QC（方法論設計者；三段鏈 quant-strategy-design → math-model-audit → walk-forward-validation-protocol 已載入）
**性質**: **預註冊草案（DRAFT）**。本檔為判準先於執行的 pre-registration 文本；經 PM/operator 認可並 commit 後即凍結——執行方（E1）與審查方在看到重放統計量之後不得修改任何門檻、判定式或 family 定義；偏離按 §12 處理。
**邊界**: 全程 read-only 研究產出。零代碼、零 config、零 runtime、零交易。唯一寫入=本報告檔+QC memory 追加。依任務指令（僅允許寫 role workspace 報告檔）本次**不落 Operator 副本**，由 PM 決定是否複製（同 move2_external 前例）。
**黑名單檢查**: 無觸發。本檔不使用 HMM/GARCH/VPIN/單獨波動率均回/含 current-bar 的 Donchian。所有 rolling 統計依 shift(1) leak-free 鐵則。無需 RETRACT。
**8 節模板對映**: §1=Executive Summary；§2=理論基礎（估計對象+邊界）；§3-§4=數學模型；§8=成本分析；§3-§7=回測驗證要求；§9=風險分析；§10=容量估算；§11=建議。

---

## 0. 預註冊聲明、凍結錨、資料窺探申報

### 0.1 凍結錨（2026-07-10，全部 read-only 取得）

| 錨 | 值 |
|---|---|
| Mac repo HEAD（撰檔時） | `1a3ecdd57` |
| 本地證據正本 | `docs/CCAgentWorkSpace/QC/workspace/reports/2026-07-10--move2_evidence.md` sha256 `da20251b4e29…c45a00` |
| 外部方法論正本 | `docs/CCAgentWorkSpace/QC/workspace/reports/2026-07-10--move2_external.md` sha256 `8b80ac0eb5…dc7a27` |
| 統計框架母本 | `docs/research/2026-07-10--counterfactual_rerun_preregistration.md` sha256 `4a3b7c26a2…c6a22`（dedup/n_eff/day-cluster CR1/BH 框架沿用） |
| maker-nogo 裁決正本 | `docs/CCAgentWorkSpace/PM/workspace/reports/2026-07-06--maker_first_microstructure_feasibility_verdict.md` sha256 `187a866879…961989`（本檔不重打，見 §2.3） |
| 重放工具 | `program_code/research/microstructure/fill_sim.py` sha256 `4a142af9ad…bee44`（2,796 行；harness 改造後須重記 sha） |
| 信號母集 | `trading.signals`，strategy_name='bb_reversion'，L1 窗內（ts ≥ 2026-06-20T02:19+02）原始 22,774 行 → gap-dedup(30min) = **25 episodes**（凍結枚舉斷言；SQL=move2_evidence §d.3，重放第 0 步逐字重跑，凍結窗 ts < 2026-07-10T17:54+02 計數 ≠25 → deviation log + 停） |
| L1 母集 | `market.l1_events` 332,432,554 行（count(*) 實測）/85 symbols/2026-06-20→07-10；`market.trades` 282.6M 行 |
| Lane A 母集 | 60d bb_rev realized RT 中兩腿皆落 L1 窗者 = **16 個**（07-03→07-10；凍結斷言同上） |

### 0.2 資料窺探申報（pre-registration hygiene）

撰檔時 QC 已見（=已污染、不得作為本實驗「發現」）：30d/60d/all-time gross 與 net（+8.86/+3.66/+3.58 bps）、fee 腿結構（10.61bps/RT 實付）、maker markout 單筆讀數（−2.37，n=1，且語義=fill-vs-submit-reference）、taker slippage 均值（entry −6.07）、episode 計數與對齊率、top-day 濃度（07-06=52%/84%）、maker-nogo 兩窗 0/172。
**未見（=本實驗 primary outcomes，判準在其之前凍結）**：bb_rev 信號條件下的 post-fill 60s/300s beta-residual markout 分佈、無條件 fill rate、贏家/輸家 fill 率分層、fill-subsample gross vs all-signal gross 的 selection gap、Lane A paired Δcost。

### 0.3 與既有裁決的關係（不重打清單）

- maker-nogo（2026-07-06，SHA 5d1622994）**不重打**；本檔 §2.3 給邊界聲明。
- 07-10 反事實重跑（誤殺假說落錘、gate=淨止損）**不重打**；本檔沿用其統計框架（§5）。
- 30d「+0.3bps/RT」點估計**不作為本實驗檢定目標**（§5.3 證明其在可行樣本量下不可檢定；改測分量帶）。

---

## 1. Executive Summary

1. **估計對象重定義**：本研究測的不是「bb_reversion maker 化後 net=+0.3bps 嗎」（該 0.3bps 效應在 σ≈8bps 下需 n≈4,400 episodes ≈ 10 年，不可檢定），而是三個可測分量：(i) 信號條件下無條件 maker fill rate；(ii) 真 post-fill 60s/300s beta-residual markout（現有效 n=1）；(iii) 同 episode 配對的 maker-vs-taker 執行成本差 Δcost（配對設計把 MDE 壓到 n=30 時 ≈3.6bps，足以分辨 3.5bps 的確定性費率差是否被逆選擇吃掉）。
2. **判定式三態**（§6）：SCREEN_PASS（→ bounded probe 候選）/ KILL（附翻案條件）/ INSUFFICIENT（禁方向性結論，按 ~1.2 episodes/day 累積重審）。KILL 的 power 在 R1（現有 20.6d L1）即可達；SCREEN_PASS 最早在 n_eff≥30 episodes（~2026-07-14 後首次重放可審）。
3. **記帳 = intention-to-treat**：per-episode 無條件三態（fill/no_fill/reject 全入分母），fill-only 統計僅作機制分解，不承載判定（外部正本 Handa-Schwartz 1996 起；DeLise 2024 touch-based 85% vs 真值 60% 教訓）。
4. **與 maker-nogo 無衝突**（§2.3）：彼裁決殺的是「做市報價作為 alpha 來源」（無條件 cadence 雙側掛單，0/172 淨正，break-even maker ≤0.4bps）；本研究是「既有信號的執行路由」——收入項不是 spread capture 而是費率替代（taker 5.5 → maker 2.0，entry 腿確定性省 3.5bps）±選擇效應。估計對象、分母、機會集合全不同；本研究任何結果都不推翻也不依賴推翻 maker-nogo。
5. **誠實前置**：60d gross +3.66bps 下即使 markout=0 maker 化算術也是負（move2_evidence F-3）——執行 lever 通過 screen ≠ cell 可盈利；cell 的 gross 證據按既有標準另行累積，probe 定位=量測儀器（learning-only、loss budget 封頂），非 promotion 證據。

---

## 2. 理論基礎：估計對象（estimand）與邊界

### 2.1 Alpha 來源歸類（quant-strategy-design 第 1 步）

本研究**不提出新 alpha**。bb_reversion 既有歸類=類別 6（短期均值回歸）；本研究對象是類別 3 邊緣的**執行成本結構**（fee schedule 的 maker/taker 價差是交易所定價的結構性事實，非市場低效）。「為什麼應該賺錢」的誠實答案：**執行 lever 本身不賺錢，它降低既有信號的成本下限**；cell 是否賺錢仍由信號 gross 決定（目前證據不足且 60d 轉弱）。

### 2.2 三個分量預算（成本恒等式，全部以 bps of notional，成本為正）

以 mid@signal 為基準價，entry 腿單腿成本：

```
c_T(taker)   = hs(t_place) + fee_taker                          [hs=半價差；impact≈0（最小單，聲明）]
c_M(M-fb, τ) = p·(−hs_captured + AS + fee_maker)
             + (1−p)·(drift_τ + hs(t_place+τ) + fee_taker)      [timeout 後 taker fallback]
Δcost_entry  = c_T − c_M                                        [>0 = maker 較便宜]
```

- p=1 時 Δcost = 3.5 + hs_captured − AS → **執行 lever 的 AS 預算 ≈ 3.5 + hs ≈ 4.5-5.5bps/leg**（majors hs~1-2bps）。
- 對照 **cell 淨值預算**（30d gross）：AS ≤ (8.86−4.0)/2 = **2.43bps/leg**（100% fill、兩腿 maker）；60d gross 下該預算為負。兩個預算不同：screen 測前者；後者需 gross 證據另行成立。
- 外部先驗（僅結構類比，不入判定）：DeLise 2024 negative drift 回吞 ~90% 半價差 → hs_captured 有效值可能僅 0.1-0.2bps；fill_sim 兩窗 pooled AS 0.85-2.6bps@15s；bb_rev 單筆 −2.37。**Δcost 符號真不確定 → 實驗值得做**。

### 2.3 與 maker-nogo 裁決的邊界聲明（任務 (f)；為何不重打）

| 維度 | maker-nogo（2026-07-06） | 本研究 |
|---|---|---|
| 估計對象 | 做市報價 NET = hs − AS − 2×maker_fee（自足 alpha） | 執行路由 Δcost = c_T − c_M（既有信號的成本差） |
| 分母 | 固定 cadence 無條件 quote-trials（兩側恆掛） | bb_reversion 信號 episodes（單側、事件觸發） |
| 反事實 | 不掛=0（沒有 taker 對照） | 不 maker=taker 執行（同 episode 配對對照） |
| 費用角色 | +2bps maker fee 是收入端的牆 | 2.0 vs 5.5 是成本端的確定性節省 3.5bps/leg |
| 裁決適用 | 0/172 淨正 → 報價業務 NO-GO（不動搖） | 未被彼裁決覆蓋；maker-nogo 自身把 cost-reduction 列為 open fork #3 |

**不重打承諾**：本研究任何結果不得被引用為「maker-first 翻案」。若 screen KILL → 強化 maker-nogo 的 fee 牆敘事；若 SCREEN_PASS → 僅證明「信號條件下的執行路由」可行，報價業務仍被 0/172 + break-even ≤0.4bps 鎖死。maker-nogo 的 QC wave 輸入已預示本方向（fill 經濟學 strategy-conditional：grid 34.8% fill vs flash_dip 0%）。

### 2.4 執行政策空間（凍結）

- **主政策 M-fb**：maker entry（PostOnly join-BBO）+ timeout τ 後 taker fallback。理由：保持交易集不變，把「信號 EV」與「執行成本」正交分解；M-skip 的評估與信號 EV 糾纏（漏掉的贏家按 taker 軌計價），降為次要政策。
- **Entry 腿 only 為主**：exit 72% 是 phys_lock giveback（tick 級動態，不可獨立再生，move2_evidence F-7）→ exit 沿用 realized ts/price（execution-counterfactual）。兩腿全 maker 僅 Lane A 次要欄。**此設計取代 stage2 的「兩腿 maker 8.7bps」算術**——主判的確定性費率節省是 3.5bps/RT（entry 腿），非 7bps。

---

## 3. 重放判準（任務 (a)；全部凍結）

### 3.1 Fill 規則帶（三層，主判用中層）

| 帶 | 規則 | 用途 |
|---|---|---|
| 上界 | touch-based（價觸及=成交） | **僅列報，禁入判定**（DeLise 實測 85% vs 真值 60%，PnL 失真）；唯一判定用途=K4 死刑檢查（連上界都輸 taker → 必 KILL） |
| **主判** | fill_sim queue 狀態機（fill_sim.py:152 `simulate_symbol`）：掛單時 snapshot 同側 size-at-touch=Q0；同側 aggressor at-or-through 累減；cancel-ahead 只推進不觸發成交（fill_sim.py:293-301）；三態 FILL / NO_FILL / ADVERSE_THROUGH（fill_sim.py:168-170） | 全部 G/K 判準 |
| 下界 | through-print only（僅價格實穿才 fill） | G5 穩健性檢查（不得災難性翻轉） |

### 3.2 Queue 折扣：**拒絕 50% 檔位作主判，主判=back-of-queue（size_ahead_frac=1.0）**

理由（四條）：
1. **物理**：信號觸發的掛單永遠加入既有隊列尾端（1m close 計算 + IPC/REST 延遲後到達）；50% 檔位隱含「掛單時身前一半量已消失」，無機制支持。
2. **不重複計算**：fill_sim resolver 已動態建模 cancel-ahead 推進（同側 size 縮減按比例縮 size_ahead）——靜態 50% 折扣會把撤單利益算兩次。
3. **偏置方向**：MM Dilemma 隊尾 markout −0.775bp vs 隊頭 −0.058bp [外部類比]——隊列位置越前 AS 越輕；用 mid 檔會把 AS 系統性做小。
4. **可比性**：maker-nogo 兩窗即以 back-of-queue 為 default，跨研究可比。
front(0.0)/mid(0.5) 保留為劑量反應敏感性欄（fill_sim 既有 sweep），不得進判定。

### 3.3 Through-print / ADVERSE_THROUGH 判別（沿用工具現行語義）

- 隊列耗盡且 best 仍在你的 level → FILL；成交同刻 best 已穿過你的 level → ADVERSE_THROUGH（fill_sim.py:257-265），其 half_spread 改以 mid@fill 為基準（BUG-2 修正，fill_sim.py:401-411）——防 adverse fill 高估 captured spread。
- best 改善離開（未耗盡隊列）→ NO_FILL 入分母；資料尾截斷 → NO_FILL（保守，fill_sim.py:306-307）。
- ADVERSE_THROUGH 在記帳上=fill（真實會成交），在機制分解上單列（結構性壞 fill 佔比為必報欄）。

### 3.4 Placement 參數（凍結主格）

| 參數 | 主判值 | 敏感性掃描（僅列報） |
|---|---|---|
| δ_place（信號 ts → 掛單） | **1s**（覆蓋 1m close 計算+IPC+REST，保守） | 250ms / 5s |
| 掛價 | join BBO 同側（OpenLong→bid；與 fill_sim BBO-join 一致；signals.details 全 NULL → 價格錨=t_place 的 L1 BBO，move2_evidence F-10） | one-tick improve |
| timeout τ | **60s**（≈1 bar；p50 持倉 0.8min 同量級；承 2026-04-20 教訓 timeout<cooldown、0.5-0.75×） | 30s / 180s |
| side | **OpenLong only 主判**（OpenShort 僅 07-06 後 7 episodes，新行為+down-beta 風險 → 單列、demeaned beta 標註，禁入主判定） | — |
| horizons（markout） | **60s + 300s 主判雙窗**（AND 邏輯）；5/15/30s（AS 分量）與 holding-horizon（Lane A 至 realized exit）必列 | — |

### 3.5 PostOnly reject 建模（兩層）

1. **確定性層**：t_place 時若意向掛價會立即 cross 對側 best（買掛 bid ≥ 當時 ask）→ PostOnly reject（Bybit 機制），計 reject 態入分母；resubmit 一次於 t_place+1s，再 reject → 該 trial 按 no_fill+fallback 政策計價。此層捕捉 quote-stale×短窗波動的主因（Oxford Albers et al.：fail 機率是延遲×波動的函數，非常數）。
2. **隨機敏感帶**：0/1/2/5% 隨機殺單+resubmit 延遲成本，報退化斜率；斜率陡（2% 殺單即翻轉 G4 符號）→ 結論標不穩，SCREEN_PASS 降級 INSUFFICIENT。

### 3.6 資料品質前置（重放第 0 步）

- L1 crossed-row / ts-floor fail-loud 過濾沿用（`--clean-since` ≥ 2026-06-17T14:25+02）；per-symbol L1 gap 審計（episode ±τ 窗內最大 L1 空洞 > 5s → 該 trial 標 censored）；censored 入分母不入檢定，censored_pct >30% → E4 fail。
- 資料品質 5-test（walk-forward skill §5）在 markout 序列上跑（ADF/KPSS/Ljung-Box/JB/ARCH）——預期 JB 拒 normality（故 §5 全部用 cluster-robust t 與 bootstrap，不用 normal 假設 VaR 類量）。

---

## 4. 記帳與 non-execution bias（任務 (b)；凍結）

### 4.1 裁決記帳 = intention-to-treat（per-episode 無條件）

- **觀測單位 = episode**（gap-dedup 30min；同分鐘跨 symbol 齊發合併為 1 個時間簇用於 cluster 計數）。per-quote/per-minute 行數永遠不是 n_eff（F1 偽複製教訓；episode 內連續分鐘共享同一價格路徑）。
- 每 episode 三軌並列（同一信號集）：**Track T**（taker-at-signal；Lane A 用 realized 成交價=最乾淨的對照，Lane B 用 t_place 對側 best 模擬）/ **Track M-fb**（主政策）/ **Track M-skip**（次要）。
- 結局四態全入分母：fill / adverse_through / no_fill / reject。**fill-only 與 unconditional 兩版並列，兩者之差 = selection bias 的直接量測值（本實驗第一輸出）**。
- 漏掉的 fills（價格未回穿）計價：M-fb 下=fallback taker 實付（drift_τ + 當時 hs + 5.5）；M-skip 下=0 倉位，其機會成本體現在與 Track T 的 episode 級差值（漏掉贏家按 taker 軌淨值扣分）。**判定綁 ITT 量；per-fill 僅作機制分解。**

### 4.2 兩條 lane（母集不同、用途不同）

| Lane | 母集 | 產出 | 承載判準 |
|---|---|---|---|
| **A：RT execution-counterfactual** | 16 個 realized RT（兩腿在 L1 窗內） | 配對 Δnet_RT：maker-entry（模擬）+ realized exit vs realized 全程；兩腿 maker 為次要欄 | G4 / K3（配對檢定，power 最高） |
| **B：per-signal entry 腿** | 25+ episodes（含未成交信號） | 無條件 fill rate、markout 曲線（5/15/30/60/300s）、贏家/輸家 fill 率分層、selection gap | G2 / G3 / K1 / K2 |

- Lane A 的已知侷限（申報）：maker entry 價位偏移會改變 phys_lock giveback 觸發時點——realized exit ts 的沿用是近似，偏置方向不明；緩解=並列「entry 起固定 horizon markout」欄（不依賴 realized exit）。
- 贏家/輸家 fill 分層（MM Dilemma 度量複製）：W_e = sign(all-signal gross@300s)；報 P(fill|W=1) vs P(fill|W=0) 及 cluster-bootstrap CI。R1-R2 階段此欄為描述性（power 不足以檢定 90/10），不入判定。

### 4.3 校準 gate：fill rate 0.7-1.3 帶（兩次適用）

1. **Pre-probe（G8）**：把同一模擬器套在 grid demo close_maker 的 408 筆真實掛單嘗試上（唯一有量的 realized maker 嘗試資料；realized fill rate 34.8%），模擬/實測 fill rate 比 ∈ [0.7, 1.3] 才可信重放的 fill 模型（承 QC memory 2026-04-20 paper/demo 一致性鐵則）。caveat：exit 腿、offset 不同，屬跨情境校準；attempt 級資料不足以重放時記 deviation，此 gate 降級為 probe 階段執行。
2. **Probe 階段（V1）**：probe realized fill rate / 重放預測 ∈ [0.7, 1.3]；帶外 → 重放模型作廢，所有 replay-derived 數字撤下承重資格，回 §12 走 v2。

---

## 5. 統計推斷、樣本量與 power（任務 (c)；凍結）

### 5.1 推斷框架（沿用 07-10 反事實預註冊 §2-§5，逐條映射）

- **n_eff** = episodes（已 gap-dedup=非重疊化的對應物；Lane A = 配對 RT 數）。
- **Cluster**：CR1 cluster-robust variance by UTC day，`V=[G/(G−1)]·(1/n²)·Σ_g S_g²`，t 檢定 df=G−1，單側。比例類（fill rate）用 day-cluster bootstrap B=1000、seed=20260710，Wilson CI 並列。
- **Eligibility（E 門檻）**：E1 n_eff≥30 episodes（主判 side）；E2 distinct UTC days≥5；E3 top-day episode share ≤50%；E4 censored_pct≤30%；E5 有 fill 的 symbols ≥5（防單 symbol artifact）。任一 fail → INSUFFICIENT，禁方向性結論。
- **多重比較**：主判定=單一預註冊 conjunction（G1-G8 AND 邏輯、雙 horizon AND）→ 無選擇效應，不需 Bonferroni；全部 sweep 欄（τ/δ/queue/improve/reject 帶）標 `exploratory=true`，禁入判定、禁候選語言；artifact 登記全部已計算 cells（K 登記），從 sweep 中「發現」更好格子 → 必須 v2 重預註冊。

### 5.2 Power 表（σ 為 ASSUMPTION，R1 實測後更新表；**門檻不隨 σ 移動**）

假設：σ_Δ（Lane A 配對 Δnet/episode）≈ 8bps；σ_AS（per-fill 60s markout）≈ 10bps；σ_gross（per-trade）≈ 25bps。單側 α=0.05、power 80%（z 和=2.486）：

| 檢定 | n | MDE |
|---|---|---|
| Lane A 配對 Δcost | 16 | 5.0bps |
| | 30 | **3.6bps** ← 3.5bps 確定性費率差恰在可辨邊緣 |
| | 60 | 2.6bps |
| Lane B AS（per-fill） | 30 fills | 4.5bps（**不足以裁 2.43bps 的 cell 預算 → AS 只作 CI 帶檢查**） |
| | 105 fills | 2.4bps（cell 預算可裁級） |
| Fill rate（Wilson 95% 半寬） | 30 | ±18pp |
| | 100 | ±10pp |
| Selection gap（兩子樣本差） | 30 episodes | ~23bps（R1-R2 僅點估+CI，低 power 申報） |
| 「net=+0.3bps」直接檢定 | — | 需 n≈4,400 episodes（≈10 年）→ **正式宣告不可檢定，移出目標** |

### 5.3 「markout n=1 → n≥30」需要多少歷史窗（任務 (c) 直答）

- 更正基準：有效 n=**1**（非 3；move2_evidence F-2）。realized 路線不可行（all-time maker fills=5）。
- **重放路線**：30 個 maker-fill markout 需 episodes ≈ 30/p̂。episode 累積 ~1.2/day（現 25 個/20.6d）：

| 假設 fill rate p | 需 episodes | 距今 | 日曆日期（約） |
|---|---|---|---|
| 0.60 | 50 | +21d | 2026-07-31 |
| 0.50 | 60 | +29d | 2026-08-08 |
| 0.35 | 86 | +51d | 2026-08-30 |

- **probe 路線**（真實 fills）：同數學，30 attempts ≈ +25d 起，30 fills 視 p 而定 ≈ 6-10 週。兩路線可並行（重放先行、probe 驗證），**皆 $0/demo**。
- ΔAS 檢定 MDE：見 §5.2——n_fills=30 時 MDE≈4.5bps，只能裁「AS 是否明顯大於執行預算 4.5-5.5bps」，不能裁 2.43bps 的 cell 預算；後者需 ~105 fills（~2026-10 量級或 probe 加速）。

### 5.4 重審節奏

R1（即刻，25 episodes/16 RT）→ 每週重放一次（純累積，$0）→ 硬檢查點 **2026-08-10**：仍 INSUFFICIENT 且無 KILL → 交 PM 裁 continue/park（避免無限期 passive-wait，對齊 TODO passive-wait 規範）。

---

## 6. GO / KILL 判定式（任務 (d)；機械可裁，凍結）

主格（back-queue、δ=1s、τ=60s、join-BBO、long-only、horizons 60s∧300s）上計算：

```
KILL ⇔ K1 ∨ K2 ∨ K3 ∨ K4
  K1（fill 饑餓）：無條件 P(fill|τ=60s) 的 Wilson 95% 上界 < 0.40
  K2（selection 殺信號）：gross_fill ≤ 0（60s 與 300s 皆是）∧ gross_all > 0
      ∧ selection gap 的 day-cluster 95% CI 不含 0
  K3（配對成本劣勢）：Lane A Δnet(M-fb − T) day-cluster 單側 t（H1: maker 更貴）p < 0.05，n_pair ≥ 16
  K4（上界死刑）：touch-based 上界下 maker RT 成本 ≥ taker RT 成本（最樂觀 fill 規則都輸 → 結構死）

SCREEN_PASS ⇔ G1 ∧ G2 ∧ G3 ∧ G4 ∧ G5 ∧ G6 ∧ G7 ∧ G8
  G1：E1-E5 全過（n_eff≥30 / days≥5 / top-day≤50% / censored≤30% / ≥5 symbols with fills）
  G2：p̂_fill ≥ 0.55 ∧ Wilson 95% 下界 ≥ 0.40（60% 慣例點值 + CI 地板；crypto-microstructure skill ≥60% 起點的 CI 化）
  G3：selection gap ≤ 0.5 × gross_all ∧ gross_fill > 0（60s 與 300s 皆是）
  G4：Lane A Δnet(T − M-fb) 點估 ≥ 3bps ∧ day-cluster 單側 t（H1: maker 更便宜）p < 0.05
  G5：through-print 下界帶的 Δnet(T − M-fb) 點估 ≥ −2bps（最保守 fill 規則下 maker 不decisively更貴）
  G6：cost_edge_ratio 投影 = [2.0 + AS_60s點估 + no_fill 攤提 + exit腿實付] / gross_all(全窗累積) < 0.8
      （probe 准入級；< 0.5 仍是 promotion 級標準，CLAUDE.md Root Principles）
  G7：regime 守門——per-episode regime 標註（沿用反事實預註冊 §7：btc_trend_30d / btc_ret_7d /
      sym_vol_30d，D−1 leak-free）；bull_heavy（bull 佔比>60%）不否決但強制 regime-bet/learning-only
      標籤且 probe 排序後置；short 側永不入主判定
  G8：fill 模型校準——grid close_maker 408 attempts 模擬/實測 fill rate 比 ∈ [0.7, 1.3]（§4.3）

INSUFFICIENT ⇔ ¬KILL ∧ ¬SCREEN_PASS
  唯一合法行動 = 繼續累積（~1.2 ep/day，$0）或 operator 授權加速取數；
  禁止寫成「maker 化不行」或「maker 化可行」。
```

**判定式性質申報**：G2/G3/G5/G6 是點估+CI 帶（screen 級，非統計證明）；唯一顯著性承重 = G4/K3（配對，power 最好）與 K2（方向殺）。SCREEN_PASS 的語義上限 = 「bounded probe 候選」，不是 edge 證明、不是 promotion 證據（`order_authority=NOT_GRANTED`、`promotion_evidence=false` 承 lane 慣例）。

**KILL 翻案條件**（硬約束 #8）：(i) fee 結構變化——RPI taker 免費腿（07-09 EXT）或 VIP≥1（現 notional 6.9% 門檻，不可達）→ §8 成本輸入重算，重放免重跑（費率是後乘項）；(ii) 新累積 episodes 使 E1-E5 重過且 G 條件全過 → 自動恢復候選；(iii) 信號宇宙變化（新 symbol 集的 hs/AS 結構不同）→ v2 重預註冊。

---

## 7. Bounded probe 草案（任務 (e)；SCREEN_PASS 後、operator-gated，本檔僅設計不派工）

### 7.1 設計

- **儀器**：demo lane bb_reversion **entry 腿 PostOnly**（join-BBO、τ=60s taker fallback，鏡像重放主格）；exit 路徑不動。前置工程疑問（交 PA/E1）：maker-nogo 稱 `use_maker_entry=true` 已在 demo TOML，但 bb_rev 30d entry 29/29 全 taker——per-strategy 配置差異須先查明（open question，不在本檔裁）。
- **隨機化**：episode 級雙臂——context_id hash 奇偶決定 arm T（taker 現狀）/ arm M（PostOnly+fallback）。確定性、可審計、消除 regime 漂移混淆（同一信號流內配對比較）。工程成本過高時降級單臂 all-M + 歷史 T 基線（regime-confounded，降級申報）。
- **Envelope**：P0/P1 硬上限不動；cost_gate 不降級；最小 qty；PostOnly only；probe 自動停止條件（下）。

### 7.2 停止與判讀規則（預設防 optional stopping）

- **Loss budget**：arm M 累計 net − arm T 累計 net < −B_rel，或 arm M 絕對累計 net < −B_abs → 自動停 arm M。定價公式：`B = n_target × notional_med × CVaR90(per-trade net)`（notional_med ≈ 888 USDT/trade，CVaR 由 R1 重放實測填入；數字由 PM/operator 落定）。
- **效力判讀只在預設里程碑**：n_attempts ∈ {30, 60, 100}；週間只查 envelope/資料品質，不看效力（防 alpha 洩漏）。
- **V1 校準 gate**：realized/replay fill-rate 比 ∈ [0.7, 1.3]（§4.3），帶外 → probe 暫停 + 重放模型 v2。

### 7.3 Conditional 解除條件（「21d ≥200 trades」的誠實化）

bb_rev 信號率 ~1.2 episodes/day → 21d 僅 ~25 attempts，**200 trades 在單 cell 上 21d 不可達**（roster 級標準誤植到 cell 級會造成永久 Conditional）。解除條件改為（全部滿足）：

1. probe 運行 ≥21d 且 attempts ≥30（infra 驗證）∧ V1 校準帶內；
2. 真實 maker fill markout n_fills ≥ 30（60s/300s 皆有）；
3. 無條件記帳（replay + probe 合併）≥ **200 signal-episode**——即 200-trade 標準的 per-signal 對應物（~2026-11 量級或宇宙擴張加速）；
4. 合併窗 gross_all > maker RT 成本實測（cost_edge_ratio < 0.8 維持）∧ top-day ≤50% ∧ 非 bull_heavy（或帶 regime-bet 標籤走 learning-only 軌）。

全過 → cell 進常規 promotion 評審（仍 demo；live 另走五 gate，本檔不觸）。任一不過 → 維持 Conditional/learning-only。

---

## 8. 成本分析（輸入凍結）

| 成分 | 凍結值 | 出處/備註 |
|---|---|---|
| taker fee | 5.5 bps/side（不打折） | VIP0；硬約束 #4 |
| maker fee | 2.0 bps/side（**費用非 rebate**） | maker-nogo BB 確認；MAKER_FEE_BPS=2.0（fill_sim.py:52） |
| 確定性節省 | entry 腿 3.5bps/RT（主判）；兩腿 7.0（次要欄） | §2.4 |
| hs / AS / drift_τ | 全部由 L1 量測，不用先驗值 | §3 |
| funding drag | Lane A per-RT 按 realized 持倉是否跨 settlement 計（p90 持倉 10min，多數不跨；per-symbol fundingInterval 即時查，不假設 8h） | crypto-microstructure skill |
| VIP1 lever | **排除**（30d notional $690k = 門檻 6.9%） | move2_evidence e.3 |
| RPI taker 免費腿 | 排除本輪；列為 KILL 翻案條件 (i) | 07-09 EXT |
| 滑點/impact | 最小單 impact≈0 申報（hftbacktest 同款免責）；**禁 size 外推** | move2_external F-EXT-7 |

## 9. 風險分析（threats to validity + findings 全量）

| # | severity | conf | 項 |
|---|---|---|---|
| R-1 | HIGH | HIGH | **Winner's curse on cell selection**：bb_rev 是因 30d gross 好看被選中的 cell（60d 已回歸：31-60d −7.07）——本設計以「不測 gross、只測執行分量」中和之；任何引用 30d gross 的推導都須並列 60d/全窗 |
| R-2 | HIGH | HIGH | 0.3bps 級 net 點估在可行樣本下不可檢定（§5.2）——判定式已改分量帶；若任何下游報告宣稱「重放證實 +0.3bps」= 違反本預註冊 |
| R-3 | MEDIUM | HIGH | Lane A exit-leg 近似（maker entry 價位偏移 → phys_lock 觸發時點漂移）；緩解=固定 horizon markout 並列欄 |
| R-4 | MEDIUM | HIGH | Top-day 07-06 濃度（30d 52%/60d 84%）+ 獨立時間簇僅 ≈14 → E2/E3 直接打擊；R1 大概率 INSUFFICIENT，屬預期非失敗 |
| R-5 | MEDIUM | MEDIUM | OpenShort 全部 07-06 後出現（regime 新行為）→ 主判 long-only；short 側單列 demeaned |
| R-6 | MEDIUM | MEDIUM | PostOnly reject 常數化不當（latency-conditional）→ §3.5 兩層建模+敏感帶 |
| R-7 | LOW | HIGH | L1 20.6d 單一 regime 窗（calm-recent 為主）→ per-episode regime 標註 + bull_heavy 強制標籤；fee 牆本身 regime 無關（maker-nogo 同判） |
| R-8 | LOW | MEDIUM | grid close_maker 校準（G8）是跨腿/跨 offset 近似；attempt 級資料不足時 gate 移到 probe 階段（deviation 申報） |
| R-9 | INFO | HIGH | 06-20→06-28 bb_rev 零成交空窗原因未明（move2_evidence F-12）→ 影響 episode 母集代表性判讀，列 open question |

**假陽性候選申報（不剔除）**：σ 假設（8/10/25bps）全部 ASSUMPTION，R1 實測後 power 表更新（門檻不動）；「fill 率結構性較高（mean-revert 側掛 bid）」是 INFERENCE 非 FACT，G2 實測裁決。

## 10. 容量估算

最小單/demo 量級：majors touch 深度 >> 自單 size，無衝擊假設成立帶內；容量非本階段約束。唯一保留：per-symbol 分層必報（crypto perp spread 異質性大 [外部類比]；maker-nogo「wide-spread 不救」已在既有宇宙確認），禁 pooled 單值結論。放大 size 需另行 impact 建模（禁外推，§8）。

## 11. 建議

**PROCEED（方法論定稿送審）**：本檔作為預註冊草案交 PM/operator 認可；認可後 E1 按 move2_evidence §c.3 六項盤點改造 harness（placement 觸發+單側+episode 聚類 reduce；`--horizons 60,300` 免改碼），R1 重放即可執行（$0、read-only、~20.6d L1）。**預期路徑**：R1 大概率 INSUFFICIENT（n_eff 25<30、時間簇 14、top-day 邊緣違反）但 KILL-capable；每週累積重放；硬檢查點 2026-08-10。
**兩個不可讓渡的誠實條款**：(i) SCREEN_PASS ≠ cell 可盈利——60d gross 下 cell 淨值仍負，gross 證據另行累積；(ii) 本研究任何結果不觸碰 maker-nogo 報價業務裁決（§2.3）。

## 12. 偏離處理（deviation policy；沿用反事實預註冊 §10）

1. 任何與本檔不符的計算選擇 = deviation，artifact `deviation_log` 記 what/why/影響面。
2. 影響判定式、門檻、family、成本輸入的偏離 → 停，回 PM，重預註冊 v2（本檔保留供 diff）。
3. 純實作層偏離（欄名/路徑）記 log 續跑。
4. Pre-reg 外切片一律 `exploratory=true`，禁入 §6 判定式，禁候選/證據語言。
5. 執行產出 artifact 必含：本檔 repo 路徑+commit SHA、§0.1 全部凍結錨複驗、episode/RT 枚舉斷言（25/16 凍結窗）、per-episode 全欄、σ 實測+更新 power 表、K 登記、deviation log（可為空）。

---

**QC 落款**：本檔全部門檻與判定式在 primary outcomes（fill rate / post-fill markout / selection gap / paired Δcost）未被計算的狀態下設定（§0.2 申報）。在「σ_Δ≈8bps、episodes 高度集中於少數 UTC 日、fill 規則真值介於 queue 狀態機與 touch 之間」的假設下，§6 判定式對『費率差被逆選擇吃掉與否』的辨識力在 n_eff=30-60 可用；對 0.3bps 級淨值宣稱則永遠不可用——此非缺陷，是把不可檢定的問題誠實地換成可檢定的問題。

QC AUDIT DONE: docs/CCAgentWorkSpace/QC/workspace/reports/2026-07-10--move2_methodology_prereg_draft.md
