# QC 對抗紅隊審計 — Move 2：bb_reversion maker 化 fill_sim 重放預註冊 · 2026-07-10

**Agent**: QC（對抗紅隊模式；目標=殺掉本線或逼出誠實邊界）
**受審對象**: `docs/CCAgentWorkSpace/QC/workspace/reports/2026-07-10--move2_methodology_prereg_draft.md`（+同前綴 evidence/external 兩份）
**邊界**: 全程 read-only（Mac repo HEAD `1a3ecdd57` + `ssh trade-core` psql SELECT only）；唯一寫入=本報告檔+QC memory 追加。依任務指令不落 Operator 副本，由 PM 決定是否複製（同 move2 系列前例）。
**黑名單檢查**: 無觸發（受審設計不用 HMM/GARCH/VPIN/含 current-bar rolling；本審計亦無新方法提案）。無需 RETRACT。
**8 節模板對映**: §1=Executive Summary；§2-§7=六攻擊面（理論基礎/數學模型/成本分析/回測驗證要求/風險分析/容量估算內嵌各攻擊）；§8=建議（含 5 條強制修正）。

---

## 1. Executive Summary（verdict 總表）

**總判定：REVISE — 預註冊草案在 6 個攻擊面下無一 FATAL 於「R1 重放」本體，但 5 條強制修正未落地前不得凍結；其中 1 條（L1 21 天滾動保留）有日曆死線（~2026-07-19）。probe 前置工程與「JS 自鎖破鎖」敘事兩個子項按現狀為 FATAL，需 descope/撤敘事後才可倖存。**

| # | 攻擊面 | Verdict | 一句話 |
|---|---|---|---|
| ① | 信號變質（non-execution bias）致命性 | **SURVIVABLE_WITH_FIX** | ITT 三軌設計已把主刀擋掉；但 M-fb fallback 晚於 realized exit 的退化 case（≥50% pairs）未定義=G4/K3 承重腿有洞（FIX-1） |
| ② | markout n=3/−2.37 當先驗 | **DEFLECTED** | 預註冊已更正 n=1+語義釘死+逐出判定式；殘餘影響只在「宿主選擇」，轉入⑤ |
| ③ | 30d 單窗×16 symbols 的選擇效應 | **SURVIVABLE_WITH_FIX** | 選擇修正後 motivating cell p≈0.08-0.16（family=6-12）；G6/解除條件 4 的 gross_all 分母把選擇效應漏回判定式（FIX-2/FIX-3） |
| ④ | L1 對 16 symbols 覆蓋充分性 | **SURVIVABLE_WITH_FIX（緊急）** | 覆蓋今日充分（25/25 對齊）；但 `l1_events` retention=**21 天滾動**——「每週累積重放到 n_eff≥30」的數學前提不存在，且凍結斷言 07-19 起開始蒸發（FIX-4，本週必跑 R1+切片釘存） |
| ⑤ | +0.3bps/RT 的月化價值 | **SURVIVABLE_WITH_FIX（probe 子項 FATAL）** | 單 cell 月化 0.77-9.0 USDT 封頂；bb_reversion 無 `use_maker_entry` knob=probe 需新 Rust 管道——為 ≤9 USDT/月建 sprint 級工程=經濟性死；重放本體 $0 保留（FIX-5 descope） |
| ⑥ | JS 自鎖「零成本破鎖」敘事 | **敘事 FATAL / 設計 SURVIVABLE_WITH_FIX** | 三腿全斷：soak 全攔 07-02 已結束（labels 已恢復自流）、probe 對 label 量零增量、cost_gate 解鎖不隨 fill 而來；預註冊本文乾淨（未引此敘事），但 stage2/roadmap 語境的敘事禁止遷入 probe 價值論證（FIX-5） |

**紅隊淨結論**：這條線最誠實的形態=「$0 R1 重放，量三個執行分量，KILL-capable，本週跑（趕在 L1 左緣蒸發前），機構價值=fill 模型校準資產（M12 前置），不是 bb_rev cell 拯救」。任何超出此形態的投入（probe 管道預建、cell 拯救敘事、label 供血敘事）都被本審計殺掉。

---

## 2. 攻擊① — 信號變質：maker 化後成交子樣本 gross 遠低於 +9.06？

### 2.1 攻擊的定量形態（紅隊親算）

以 MM Dilemma 90/10 fill 不對稱 [外部類比] 套 30d cell 實測結構（20W avg +20.53 / 9L avg −17.42，evidence a.5）：

```
fill-only gross ≈ (0.1×20×20.53 − 0.9×9×17.42) / (0.1×20 + 0.9×9) = −100.0/10.1 ≈ −9.9 bps
```

即在外部先驗的最壞形態下，成交子樣本 gross 從 +8.86 翻到 **−9.9bps**（符號翻轉，非折扣）。「+9.06→+0.3」的算術在此情境下屍骨無存。

### 2.2 設計已覆蓋的部分（判 DEFLECTED 的理由）

- 判定綁 **per-episode ITT**（fill/adverse_through/no_fill/reject 全入分母，prereg §4.1）；fill-only 僅機制分解，**上述 −9.9bps 情境正是 K2 kill gate 與 selection gap（第一輸出）要量的東西**——設計不是沒看到這把刀，是把它做成了主測量對象。
- M-fb 主政策保持交易集不變：兩臂都成交每個 episode，信號組成不變，選擇效應轉化為可量測的 fallback drift 成本——正交分解正確。
- M-skip（會死於 −9.9bps 的政策）已降為次要欄，不承載判定。

### 2.3 三個殘餘洞（故 SURVIVABLE_WITH_FIX 非 DEFLECTED）

**h1（FIX-1，凍結前必修）— fallback 晚於 realized exit 的退化 case 未定義**：p50 持倉 **0.8min（48s）< τ=60s**（evidence a.6）。對 ≥50% 的 Lane A pairs，M-fb fallback taker 進場發生在 realized exit **之後**——「maker entry（模擬）+ realized exit」的配對 Δnet 出現負持倉時長，凍結文本（§2.4/§4.2/R-3）只講了 exit 時點漂移，沒定義這個退化 case。R1 執行時任何 ad-hoc 選擇（跳過該 pair / 改用固定 horizon / 記為放棄）都是 deviation §12.2 級=強制 v2。**必須現在預先指定**（紅隊建議：fallback_ts ≥ realized_exit_ts ⇒ 該 episode M-arm 記「trade forgone」，Δnet = −(realized net PnL)，即把錯過的整筆交易入帳——最保守且與 ITT 一致；固定 horizon 欄並列）。
**h2 — K2 的 kill power 實際近零**：selection gap MDE@n=30 ≈ 23bps（prereg §5.2 自認）→ K2 要求 day-cluster 95% CI 排除 0，在 n=30-60 幾乎不可能觸發。真實的 selection kill 會表現為 G4 長期不過 → 慢性 INSUFFICIENT 至 2026-08-10 park，而非 KILL。§1.2「KILL 的 power 在 R1 即可達」只對 K1/K4 成立，對 K2 不成立——申報措辭需改。
**h3 — 結構性先驗：信號壽命 ≈ 隊列等待時長**：p50 持倉 48s 與 τ=60s 同量級。QC 2026-04-20 教訓（grid 入場信號 half-life=秒級 → timeout 必須 < cooldown）在此的對應物：**對 sub-minute half-life 的 reversion pop 做 maker 排隊，贏家側 fallback 幾乎必然吃掉全部反轉幅度**。這不是設計錯誤（實驗正是量它），但 KILL 先驗應上調——直接餵給⑤的期望值計算。

**Verdict ①：SURVIVABLE_WITH_FIX**（FIX-1 凍結前必修；h2 措辭修正；h3 入期望值申報）。

---

## 3. 攻擊② — markout n=3 的 −2.37 可信度≈0：設計把它當先驗了嗎？

**沒有。** 逐點核對：

- §0.2 把 −2.37 列入「已污染、不得作為發現」清單；§2.2 標「僅結構類比，不入判定」；evidence F-1/F-2 已把 n=3→n=1、語義=fill-vs-submit-reference（非 post-fill markout）雙重釘死（`execution_fill_helpers.rs:27-42`）。
- §6 判定式全部用 L1 實測 AS/fill rate/Δcost，無一項引 −2.37；σ_AS=10bps 只進 power 表且申報 ASSUMPTION+「門檻不隨 σ 移動」。
- 動機句「Δcost 符號真不確定 → 實驗值得做」是先驗中性的——與 n=1 讀數無關也成立（費率差 3.5bps 確定 vs AS 未知，符號本來就不確定）。

**殘餘（不改判定）**：stage2 用 n=3 排出「bb_rev AS 全策略最溫和」的順位，**這個順位是 bb_rev 被選為宿主的理由之一**——n=1 下該順位零可信度，宿主選擇的合理性問題轉入攻擊⑤（grid 有 n=96 markout 讀數+現成 knob+8× notional）。

**Verdict ②：DEFLECTED**。

---

## 4. 攻擊③ — 30d 單 regime 窗+16 symbols：這個 cell 本身就是選擇效應？

### 4.1 選擇賬本（從多少 cells 挑出來？selection p 多少？）

- **家族**：stage2 按 30d gross 掃了 ≥6 個策略級 cell（flash_dip/funding_arb/grid/ma/bb_breakout/bb_rev），bb_rev 被點名「**唯一 gross 正 cell**」（stage2 QC 報告 line 16）=定義上的 max-of-K；同一輪 review 還翻過 76 個 strategy::symbol cells。窗口本身（30d 而非 60d/all-time）也是挑過的：31-60d 單獨 **−7.07**（符號翻轉）、all-time gross +3.58/net −7.41（sign p=0.232）。
- **紅隊復算（day-cluster）**：30d 29 closes 落 **15 個交易日**（SQL 見 §9），day-mean gross = 7.11bps、day-SD 11.34、t=2.43（df=14）、單側 p≈**0.0145**（未修正）。
- **選擇修正**：Sidak K=6（策略族）→ p≈**0.084**；K=12（×2 窗）→ **0.16**；對 76-cell 家族，null 下 max 的期望值≈2.4σ > 本 cell 的 1.9-2.4σ——**作為被挑出的最大值，+8.86 的證據含量≈0**。加上跨窗符號翻轉，誠實的 gross 先驗=60d 的 +3.66（或更低）。

### 4.2 設計的暴露面（大部分中和，兩處漏回）

預註冊的主防禦（「不測 gross、只測執行分量」+R-1 HIGH/HIGH 申報）是對的：fill rate/AS/Δcost 不以 cell 被選中為條件。**但兩處把 gross_all 漏回判定式**：

1. **G6 的分母 = gross_all(全窗累積)**，而重放全窗（L1 06-20→07-10）≈就是選擇窗（07-06 佔 30d gross 52%）。紅隊親算：G6 分子下界 ≈ 2.0(maker fee) + exit 腿實付 ~3.3-7.3bps → 以 60d gross 3.66 為分母時 ratio ≈ **1.46-2.54 >> 0.8（必 fail）**；以 30d 8.86 為分母才可能過。**G6 的 pass/fail 完全由窗口選擇決定=選擇效應直通判定式**。（附帶：「exit 腿實付」是否含 favorable slippage −1.77 的符號約定未釘死，同須凍結。）
2. **更隱蔽的耦合**：使 30d gross 為正的那份運氣（反轉真的發生了）**同時機械性壓低同窗實測 AS**（掛 bid 成交後價格回升=markout 好看）。G4/G6 在選擇窗內量測=繼承 cell 選擇的運氣。G7 regime 標註不覆蓋這個 channel。

### 4.3 修正（FIX-2/FIX-3）

- **FIX-2**：G6 分母改取 worst-of {重放窗 gross_all, 60d realized gross, all-time gross}（或 JS-shrunk 值）；不願改則 G6 降級為 annex 欄、逐出 SCREEN_PASS 條件。probe 解除條件 4 的「合併窗 gross_all」同樣適用 worst-of。
- **FIX-3**：SCREEN_PASS 的決策樣本須含 **≥15 個 post-registration episodes**（ts > 2026-07-10；~12.5 天累積，與 2026-08-10 checkpoint 相容），且所有 primary outcomes 必報 in-selection-window vs post-window 分裂欄——把「決策多數票」搬到選擇窗之外。

**Verdict ③：SURVIVABLE_WITH_FIX**。

---

## 5. 攻擊④ — fill_sim L1 數據對 16 symbols 覆蓋足夠嗎？

### 5.1 今日覆蓋：充分（evidence 已核，本審計複驗）

332.4M 行/85 symbols；bb_rev 15 個信號 symbols 全覆蓋；25/25 episodes ±60s 對齊；episode 日期 06-28→07-10（本審計重跑枚舉 SQL：10 個 distinct 日，top-day 07-08 佔 8/25=32%——**按 E3 的 episode-share 定義其實過門檻**，prereg R-4「top-day 邊緣違反」混用了 gross-share 與 episode-share 兩個定義，措辭需對齊）；trades 282.6M 行在位。

### 5.2 紅隊新事實（evidence 報告漏查）：**`l1_events` retention = 21 天滾動窗**

```
timescaledb_information.jobs: l1_events policy_retention drop_after='21 days'（hypertable_id 153；compression after 7d）
同框架：trades 45d / ob_top 30d / signals 90d / risk_verdicts 30d / fills 365d
L1 min(ts) 實測 = 2026-06-20 02:18 ≈ now − 20.6d —— 這不是「部署起點」，是滾動窗左緣。
```

四個直接後果，全部打在預註冊的執行計畫上：

1. **§5.3 累積數學的前提不存在**：穩態可重放 episodes ≈ 21d × 1.2/day ≈ **25 個/快照，永遠**。「~2026-07-14 後 n_eff≥30 首次可審」「p=0.35 → 86 episodes → 2026-08-30」整張表隱含 L1 累積增長——實際上舊 episode 的 L1 以與新 episode 流入相同的速率蒸發。單次重放永不可達 n_eff≥30。
2. **凍結斷言開始蒸發**：06-28 episode 的 L1 約 **2026-07-19** 掉出窗、06-30 約 07-21；「重放第 0 步逐字重跑 25 斷言」屆時無法以對齊態複驗（signals 表 90d 保留 → 計數仍=25，對齊率開始 <100% → censored 上升 → E4 風險）。
3. **可復現性/審計死亡**：R1 結果在 ~3 週後永久不可重跑複核——對一份以 pre-registration 紀律立身的設計，這是自毀級漏洞。
4. **G8 校準同鐘**：grid close_maker 408 attempts 的 L1 同樣 21d 滾動——G8 不本週跑，校準母集開始蒸發。

### 5.3 修正（FIX-4，緊急、廉價）

- **本週執行 R1**（趕在 07-19 前），且每次 run 把 episode 窗 L1+trades 切片（[t_place−60s, t_place+τ+300s]，per symbol；25 episodes × ~7min 切片，MB 量級）匯出為 immutable run artifact（含 sha256），**凍結斷言改錨定 artifact store 而非活 DB**。
- **累積機制改為跨 run 增量 ledger**：每個 episode 在首個覆蓋它的 run 中重放一次、結果+切片入 ledger，後續 run 只追加新 episodes——pooling 數學不變（per-episode 統計量不依賴共同重放），但必須寫進 v1.1 文本，否則每週重放=每週丟左緣。
- 附帶申報：risk_verdicts 30d 滾動 → blocked 母集（71,207 行）同樣在蒸發，反事實 lane（另線）同型風險。

**Verdict ④：SURVIVABLE_WITH_FIX（緊急，日曆死線 2026-07-19）**。

---

## 6. 攻擊⑤ — +0.3bps/RT 成立又如何？月化多少 USDT？值一個 sprint 嗎？

### 6.1 月化親算（SQL 見 §9，全 FACT）

| 情境 | 算式 | 月化 |
|---|---|---|
| 宣稱效應 +0.3bps/RT（bb_rev 單 cell） | 25,761 USDT entry 腿 30d notional × 0.3e-4 | **0.77 USDT/月** |
| 費率差全額上界（3.5bps、100% fill、AS=0、零 fallback） | 25,761 × 3.5e-4 | **9.0 USDT/月** |
| Roster 全策略 entry 腿理論天花板 | ~333k × 3.5e-4 | 116.7 USDT/月 |
| Roster 現實帶（fill~0.5、strategy-conditional AS：flash_dip/funding_arb 讀數 −12.7/−13.5 大概率 port 不動） | — | ~20-50 USDT/月（INFERENCE） |
| 對照：demo 30d 全系統 net | stage2 | −406 USDT/月 |

單 cell 的宣稱效應=**每年 9.3 USDT**。cell 30d net 本身 −4.52 USDT：+0.3bps 效應連把該 cell 推到 0 都不夠（−1.76 net bps + 0.3 仍負）。

### 6.2 成本側新 FACT：probe 不是 config 翻牌，是 Rust 工程

`use_maker_entry` 僅存在於 ma_crossover / bb_breakout / grid_trading（`strategies/registry.rs:144/242/272`）；**bb_reversion 無此 knob**（params 只有 close 路徑的 `maker_price_buffer_ticks`，`bb_reversion/params.rs:63-64`）。demo TOML 只有 `use_maker_close=true`（`risk_config_demo.toml:267`）。→ probe = strategy_params + registry + bb_reversion mod 接線 + 測試 + E2/E4 鏈 + config 治理審批。prereg §7.1 的 open question 本審計已答死：**不存在現成路徑**。

### 6.3 判定（分層）

- **「拯救 bb_rev cell」作為目標：FATAL**。≤9 USDT/月封頂 vs sprint 級工程，成本效益差 2 個數量級。翻案條件（硬約束 #8）：(i) bb_rev cell notional 規模 ≥20×（需 gross 證據先成立，雞生蛋）；(ii) 費率結構變化（RPI taker 免費腿 / VIP≥1）改變分子；(iii) roster 級 port 證據（見下）使 bb_rev 只是首個量測點而非價值載體。
- **「R1 重放作為量測儀器」：保留**。$0、harness 改造小-中（evidence c.3）、KILL-capable、產出=fill 模型校準資產（M12 自適應 router 的前置，maker-nogo 留的唯一真 dormant）+ strategy-conditional maker viability 的第一份真 post-fill markout 分佈。這個價值不依賴 bb_rev cell 賺錢。
- **FIX-5（descope）**：(a) probe 的 Rust 管道 **SCREEN_PASS 前一行不寫**（prereg 已有此意，明文化為凍結條款）；(b) 若目標是可移植執行 lever，經濟上正確的 probe 宿主是 **grid_trading**（現成 knob、205k entry notional=8× bb_rev、408 attempts 校準數據、n=96 的 −2.45 讀數）——bb_rev 只能以「信號條件化最乾淨的量測宿主」為由保留，且此理由須明寫，宿主變更走 v2；(c) 價值主張改寫為「校準資產+roster 路由決策輸入」，任何「cell 拯救」語言撤下。

**Verdict ⑤：SURVIVABLE_WITH_FIX（probe 子項按現狀 FATAL，descope 後倖存）**。

---

## 7. 攻擊⑥ — JS 自鎖「零成本破鎖」：demo PostOnly fills 真能供血 realized_fill 標籤？

### 7.1 Runtime FACTs（全部本審計實測，SQL 見 §9）

1. **soak 全攔已於 2026-07-02 結束**：`bounded_probe_soak_isolation:ordinary_demo_entry_blocked` 415,651 筆全部落 06-29→07-02；dispatch-edge withhold 時代（IMPL-A 07-03 部署後）僅 **6 筆**（全在 07-09）。bb_rev demo 交易已恢復：last-7d 15 closes/30 fills。
2. **標籤管線在自流**：last-7d realized-outcome 標籤 bb_rev **15/15 closes 全標**、flash_dip 23/23（lineage=`label_close_tag`）。管線按 `entry_context_id` join fills、對 maker/taker role 不可知——**PostOnly fill 會以完全相同方式產生標籤，機械上 YES**。
3. **但 typed lineage 半接線**：15 筆 bb_rev 新標籤中僅 **1 筆** `label_source='realized_fill'`，14 筆 NULL（V147 前向接線=明文 follow-up 未完成）。訓練側無恙（parquet_etl 以 `label_close_tag IS DISTINCT FROM 'rejected_governance'` 過濾）；**但任何按 label_source 過濾的監測/消費者少算 ~15×**——MIT stage2 提議的 D4 healthcheck（`WHERE label_source='realized_fill'`）會回報一個已不存在的饑荒。新 finding（MEDIUM）。

### 7.2 敘事三腿全斷（敘事 FATAL）

- **腿 1「破鎖」不成立**：probe fills 只給**已通過 cost_gate 的 episodes**（~1.2/day）添標籤；被鎖母集（bb_rev FIL 3,556/ARB 2,270 個 blocked 信號分鐘）不因 probe 有任何 fill 而解鎖——解鎖需要 cost_gate 的成本輸入改按 maker 費率計，那是另一個獨立 gated 變更，無人提案、不在本預註冊範圍。JS cells 的 n 以同樣 ~1.2/day 生長，**有沒有 probe 都一樣**。
- **腿 2「零成本」有條件**：soak withhold gate 是**全局時間閘**（`demo_learning_lane_soak_gate.rs:54` `should_withhold_approved_open(now_ms)`，無 strategy/candidate 維度）——若 probe 沿用 bounded-probe envelope 機制運行，envelope Active 期間**全 roster 的 ordinary entries 被截留**（06-29→07-02 的 415k 攔截+標籤斷糧就是這個成本的實測值）。probe 若以普通 demo config 變更方式跑則無此成本，但那需要 6.2 的 Rust 管道。兩條路都不是「零成本」。
- **腿 3「供血」是零增量**：M-fb 對標籤量中性（每 episode 都成交）、M-skip 嚴格減少標籤。與現狀（taker 自流供血，07-03 起已恢復）相比，probe 增加的是 **maker 執行 ground truth（V1 校準用）**，不是標籤量。stage2 寫該敘事時 soak 全攔尚在（標籤確實斷糧）——**敘事的事實前提已於 07-03 過期**。

### 7.3 設計責任劃分

預註冊本文乾淨：§7 probe 定位=「量測儀器」，未引用 label 供血/破鎖敘事——**攻擊⑥殺的是 stage2/roadmap 語境裡的敘事，不是預註冊**。修正（併入 FIX-5）：(a) probe 價值論證凍結為「V1 fill-model 校準」單一理由，label/破鎖語言明文禁入；(b) probe 執行方式若涉 soak envelope，先解決全局 withhold 的 per-strategy scoping 或明示接受全 roster 截留成本並計價；(c) E1 修 V147 前向接線 + MIT D4 healthcheck 改用 label_close_tag lineage（或雙欄 OR）。

**Verdict ⑥：敘事 FATAL（撤下）；設計 SURVIVABLE_WITH_FIX**。

---

## 8. 建議（判定 + 5 條強制修正 + findings 全量）

### 8.1 判定

**REVISE**：預註冊 v1 不得按現文凍結。完成 FIX-1~FIX-5 出 v1.1 後可凍結執行；R1 重放本體保留且**本週必跑**（L1 左緣 07-19 開始蒸發）。

### 8.2 強制修正清單

| # | 修正 | 死線 |
|---|---|---|
| FIX-1 | M-fb fallback_ts ≥ realized_exit_ts 退化 case 的記帳規則凍結前預指定（建議：trade-forgone 記 −realized net；固定 horizon 欄並列）；「KILL power 在 R1 可達」限定至 K1/K4 | 凍結前 |
| FIX-2 | G6 分母（及 probe 解除條件 4）改 worst-of {重放窗, 60d, all-time} gross，或 G6 逐出判定式降 annex；「exit 腿實付」符號約定釘死 | 凍結前 |
| FIX-3 | SCREEN_PASS 決策樣本 ≥15 個 post-registration（>07-10）episodes + 全 primary outcomes 報選擇窗內/外分裂 | 凍結前 |
| FIX-4 | **本週跑 R1+G8**；episode 窗 L1/trades 切片入 immutable artifact（sha256）；凍結斷言錨改 artifact store；累積機制改跨 run 增量 ledger 並寫入文本 | **2026-07-19 前** |
| FIX-5 | descope：probe Rust 管道 SCREEN_PASS 前不建；「cell 拯救」與「label 供血/破鎖」語言全撤；宿主經濟性（grid 8× notional+現成 knob）與 bb_rev 量測純度的取捨明文化；V147 前向接線+label_source 監測修正交 E1/MIT | 凍結前（工程項可並行） |

### 8.3 Findings 全量（含假陽性候選，不自行剔除）

| # | severity | conf | finding |
|---|---|---|---|
| RT-1 | HIGH | HIGH | `l1_events` retention 21d 滾動：累積數學前提不存在+凍結斷言 07-19 起蒸發+R1 結果 3 週後不可複核（§5.2，FACT） |
| RT-2 | HIGH | HIGH | M-fb fallback 晚於 realized exit（p50 持倉 48s < τ=60s）的記帳未定義，打擊 G4/K3 承重腿 ≥50% pairs（§2.3 h1，FACT+INFERENCE） |
| RT-3 | HIGH | HIGH | probe 需新 Rust 管道（bb_reversion 無 `use_maker_entry`，registry.rs:144/242/272 反證）；單 cell 價值 0.77-9.0 USDT/月 → probe 按現狀經濟性死（§6，FACT） |
| RT-4 | HIGH | MEDIUM | G6/解除條件 4 的 gross_all 分母把 cell 選擇效應漏回判定式；60d gross 下 G6 必 fail、30d 下才可能過=窗口決定判定（§4.2，親算） |
| RT-5 | MEDIUM | HIGH | 「零成本破鎖」敘事三腿全斷（soak 已解/label 零增量/cost_gate 不解鎖），事實前提 07-03 過期（§7，FACT） |
| RT-6 | MEDIUM | HIGH | V147 label_source 前向半接線（bb_rev 新標籤 14/15 NULL）：label_source 基監測少算 ~15×，MIT D4 healthcheck 按現文會誤報饑荒（FACT） |
| RT-7 | MEDIUM | MEDIUM | motivating cell 選擇修正後 p≈0.084（K=6）~0.16（K=12）+跨窗符號翻轉：30d gross 作為動機的證據含量≈0（§4.1，親算；family 大小=INFERENCE） |
| RT-8 | MEDIUM | MEDIUM | 選擇窗運氣與同窗 AS 量測的機械耦合（反轉發生⇒markout 好看）：G4/G6 繼承 cell 選擇運氣，G7 不覆蓋此 channel（INFERENCE） |
| RT-9 | MEDIUM | MEDIUM | G4 power 表未計 day-cluster：σ_Δ=8bps 下 n=16/G=8 → MDE≈7.9bps、n=30/G≈15 → ≈5.4bps（非 3.6）；「恰可辨 3.5bps」樂觀 ~1.5×（親算，σ=ASSUMPTION） |
| RT-10 | LOW | HIGH | K2 實際 kill power 近零（gap MDE 23bps@30）：真 selection kill 表現為慢性 INSUFFICIENT 非 KILL（prereg 自認數字的推論） |
| RT-11 | LOW | HIGH | E3 定義混用：episode-share（32%，過）vs gross-share（52%，不過）；R-4 措辭與凍結定義不一致（FACT） |
| RT-12 | LOW | MEDIUM | Lane B Track T 模擬 taker 計價於 t_place+1s，realized taker 實測 −6.07bps favorable drift 未被模擬捕捉 → Lane B Δcost 有 pro-maker 偏置風險；緩解=G4/K3 在 Lane A 用 realized 價（Lane A M-arm 建議改錨 realized order submit ts，orders 表 365d 保留可取） |
| RT-13 | INFO | HIGH | risk_verdicts 30d 滾動 → 71,207 行 blocked 母集同樣蒸發中（另線 counterfactual lane 同型風險，本線僅申報） |
| RT-14 | INFO | MEDIUM | 假陽性候選：RT-7 的 family 大小可辯（若 stage2 掃描視為單一 pre-specified 檢查則 K=1、p=0.014 成立）；判斷依據=「唯一 gross 正 cell」措辭與 76-cell review 同輪存在。裁決留 PM |

### 8.4 對「殺掉本線」的誠實回答

紅隊沒能殺死 R1 重放：ITT 三態記帳+三軌對比+episode 聚類+KILL 判定式是本 repo 迄今對 non-execution bias 最完整的一次設計，外部方法論（Handa-Schwartz/DeLise/MM Dilemma）已內化。被殺掉的是三個寄生物：cell 拯救敘事（③⑤）、label 供血敘事（⑥）、probe 預建衝動（⑤）。**修完 5 條，這條線的正確身份是一次 $0 的儀器校準實驗，本週跑，預期大概率 INSUFFICIENT-then-KILL，而它的 KILL 也有淨價值（M12 路由的第一份 strategy-conditional 真 markout 數據）。**

---

## 9. 可重跑證據（全部 read-only）

```bash
# RT-1 retention 政策
ssh trade-core "psql -h 127.0.0.1 -U trading_admin -d trading_ai -Atc \"SELECT hypertable_name, proc_name, config FROM timescaledb_information.jobs WHERE hypertable_name IN ('l1_events','trades','signals','risk_verdicts')\""
# ③ 30d 逐日 gross/notional（day-cluster 復算輸入）
ssh trade-core "psql -h 127.0.0.1 -U trading_admin -d trading_ai -Atc \"SELECT date_trunc('day', ts)::date, count(*), round(sum(realized_pnl)::numeric,2), round((sum(qty*price))::numeric,0) FROM trading.fills WHERE strategy_name='bb_reversion' AND engine_mode IN ('demo','live_demo') AND realized_pnl<>0 AND ts>now()-interval '30 days' GROUP BY 1 ORDER BY 1\""
# ⑤ roster/bb_rev entry 腿 notional
ssh trade-core "psql -h 127.0.0.1 -U trading_admin -d trading_ai -Atc \"SELECT strategy_name, round(sum(qty*price)::numeric,0) FROM trading.fills WHERE engine_mode IN ('demo','live_demo') AND ts>now()-interval '30 days' AND entry_context_id IS NULL GROUP BY 1 ORDER BY 2 DESC\""
# ⑥ soak 兩時代計數
ssh trade-core "psql -h 127.0.0.1 -U trading_admin -d trading_ai -Atc \"SELECT reason, count(*), min(ts)::date, max(ts)::date FROM trading.risk_verdicts WHERE ts>now()-interval '12 days' AND reason ILIKE '%soak%' GROUP BY 1\""
# ⑥ 標籤供血（lineage 雙欄對照）
ssh trade-core "psql -h 127.0.0.1 -U trading_admin -d trading_ai -Atc \"SELECT label_source, label_close_tag, count(*) FROM learning.decision_features WHERE label_filled_at>now()-interval '7 days' AND label_net_edge_bps IS NOT NULL GROUP BY 1,2 ORDER BY 3 DESC\""
# ④ episode 日期分佈（凍結枚舉重跑）
# （SQL 同 move2_evidence §d.3，GROUP BY ts::date）
# ⑤ use_maker_entry 覆蓋面
grep -n "use_maker_entry" srv/rust/openclaw_engine/src/strategies/registry.rs   # 144/242/272：ma/bbb/grid，無 bb_reversion
```

關鍵 file:line：`demo_learning_lane_soak_gate.rs:54`（全局時間閘）、`parquet_etl.py` `_LOAD_TRAINING_DATA_SQL`（label_close_tag 過濾）、`V147__decision_features_label_source.sql`（前向接線=follow-up）、`bb_reversion/params.rs:63-64`（僅 close-maker buffer）、`risk_config_demo.toml:267`（use_maker_close）。

QC AUDIT DONE: docs/CCAgentWorkSpace/QC/workspace/reports/2026-07-10--move2_redteam.md
