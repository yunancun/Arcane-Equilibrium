# Move 2 決策 Dossier — bb_reversion maker 化 fill_sim 重放 · 2026-07-10

**Agent**: PA（決策檔案綜合者）
**輸入正本**（四份，`docs/CCAgentWorkSpace/QC/workspace/reports/`）：
`2026-07-10--move2_evidence.md`（證據盤點）/ `2026-07-10--move2_external.md`（外部方法論）/ `2026-07-10--move2_methodology_prereg_draft.md`（預註冊草案 v1）/ `2026-07-10--move2_redteam.md`（對抗紅隊）
**PA 親自復驗**（3 個最 load-bearing claim，全部確認）：
1. `use_maker_entry` 僅存在 `rust/openclaw_engine/src/strategies/registry.rs:144/242/272`（ma/bbb/grid），bb_reversion 全樹 grep=0 → RT-3 probe-需-Rust-工程 FACT。
2. `execution_fill_helpers.rs:26-43` `split_markout_by_role`：maker 欄實際計算= `adverse_slippage_bps(is_buy, fill_price, reference_price@submit)`——**代碼註釋自稱「掛單成交後 mid 逆向走=adverse selection」但數學是 fill-vs-submit-reference**（註釋是 aspiration 非 runtime fact）→ QC F-1 語義更正成立。
3. Linux PG `timescaledb_information.jobs`：`l1_events` `policy_retention drop_after='21 days'`（trades 45d / signals 90d）→ RT-1 成立，**R1 日曆死線 ~2026-07-19 真實**。
**邊界**: 全程 read-only；唯一寫入=本檔+PA memory 追加（依任務指令不落 Operator 副本，由 PM 決定複製；同 move2 系列 QC 前例）。Mac repo HEAD `1a3ecdd57`。

---

## ① 一頁結論

### 建議：GO_WITH_CONDITIONS（置信度 HIGH）——限定為「$0 R1 重放量測儀器」形態

**GO 的東西**（一句話身份）：一次 $0、read-only、KILL-capable 的執行分量量測實驗——量 (i) 信號條件下無條件 maker fill rate、(ii) 真 post-fill 60s/300s beta-residual markout（現有效 n=1）、(iii) 同 episode 配對 maker-vs-taker Δcost；副產出=本 repo 第一份 strategy-conditional fill 模型校準資產（M12 自適應 router 前置，maker-nogo 留下的唯一真 dormant 能力層）。

**同時 NO-GO 的三個寄生子項**（紅隊 FATAL，PA 裁決全部接受）：
1. **probe Rust 管道預建 = NO-GO**。bb_reversion 無 `use_maker_entry` knob（PA 親 grep 復驗），probe=strategy_params+registry+接線+E2/E4 鏈的 sprint 級工程；單 cell 效應封頂 0.77-9.0 USDT/月——成本效益差 2 個數量級。SCREEN_PASS 前一行不寫（凍結條款）。
2. **「拯救 bb_rev cell」作為目標 = NO-GO**。cell 30d net −1.76bps：+0.3bps 效應連推到 0 都不夠；60d gross +3.66 下即使 markout=0 maker 化算術已負（−0.34）。
3. **「label 供血/零成本破鎖」敘事 = 撤下**。三腿全斷（soak 全攔 07-02 已結束、probe 對 label 量零增量、cost_gate 不因 fill 解鎖）；stage2/roadmap 該敘事的事實前提 07-03 已過期，禁遷入任何 probe 價值論證。

**GO 的 5 個綁定條件**（任一不滿足 → 本 GO 失效）：
- **C1**：預註冊 v1.1 納入紅隊 FIX-1~FIX-5 + RT-9/RT-11/RT-12 修正後才凍結（見 §④A）；v1 草案不得按現文凍結（紅隊 verdict=REVISE，PA concur）。
- **C2**：**R1 本週跑（≤2026-07-19）**——`l1_events` 21 天滾動保留使 06-28 episode 的 L1 自 07-19 起蒸發；R1+G8 校準+L1/trades 切片釘存必須趕在左緣前。
- **C3**：判定目標=三分量帶，**永久放棄「+0.3bps/RT 淨值」直接檢定**（σ≈8bps 下需 n≈4,400 episodes ≈10 年；任何下游報告宣稱「重放證實 +0.3」=違反預註冊）。
- **C4**：**不觸碰 maker-nogo**。任何結果不得引用為重開 TODO `P1-MAKER-FIRST-MATURE-PERP-PIVOT`（NO_GO marker 原文親核在位）；估計對象/分母/機會集合三重不同（prereg §2.3 邊界聲明保留）。
- **C5**：regime 鐵律——L1 窗 20.6d 單一 calm-recent regime；bull_heavy → 強制 regime-bet/learning-only 標籤；OpenShort（僅 07-06 後 7 episodes）永不入主判定、單列 demeaned beta 標註（06-03 鐵則）。

**置信度分層（誠實申報）**：對「descoped 形態值得做且安全」= HIGH（$0、read-only、全 additive、KILL 也有淨價值）；對「最終 SCREEN_PASS」先驗反而**低**——紅隊 h3 結構性先驗（p50 持倉 48s < τ=60s：信號壽命≈隊列等待時長，贏家側 fallback 幾乎必然吃掉反轉幅度）+ 60d gross 轉弱。**預期路徑=R1 INSUFFICIENT → 每週增量 → 大概率 KILL**，而 KILL 本身是 M12 路由的第一份真數據。

---

## ② 關鍵數字表（全帶證據等級）

| # | 數字 | 值 | 證據等級 | 出處/可重跑 |
|---|---|---|---|---|
| N1 | 30d gross / net | **+8.86 / −1.76 bps**（29 closes） | FACT | evidence §a.1（SQL 附） |
| N2 | 60d gross / net | **+3.66 / −7.20 bps**（58 closes） | FACT | evidence §a.1 |
| N3 | 31-60d 差分 gross | **−7.07 bps**（符號翻轉） | FACT | evidence §a.1 |
| N4 | maker markout 有效樣本 | **n=1**（−2.37 單筆；語義=fill-vs-submit-reference 非 post-fill） | FACT（PA 復驗 `execution_fill_helpers.rs:26-43`） | evidence F-1/F-2 |
| N5 | L1 母集 | 332,432,554 行 / 85 symbols / 06-20→07-10（20.6d） | FACT（count(*) 實測；n_live_tup 4.3M 是 stale） | evidence §c.2 |
| N6 | **L1 retention** | **21 天滾動**（trades 45d / signals 90d） | FACT（PA 復驗 ssh timescaledb jobs） | redteam §5.2 |
| N7 | 信號 episodes | 25（gap-dedup 30min）；獨立時間簇 ≈14；對齊率 25/25=100%（±60s） | FACT | evidence §d.2/d.3（SQL 附） |
| N8 | Lane A 配對母集 | 16 個 realized RT 兩腿在 L1 窗內 | FACT | evidence §d.3 |
| N9 | top-day 濃度 | 07-06 = 30d gross 52% / 60d gross 84%；episode-share 32%（07-08） | FACT（兩定義並存，v1.1 釘死 episode-share） | evidence F-4 + redteam RT-11 |
| N10 | 確定性費率節省 | entry 腿 **3.5 bps/RT**（taker 5.5→maker 2.0；費用非 rebate） | FACT（費率表） | prereg §2.4/§8 |
| N11 | entry taker slippage | **−6.07 bps（favorable）**——realized gross 內嵌、maker 化不保留 | FACT | evidence §b.3 |
| N12 | +0.3bps 直接檢定樣本需求 | n≈4,400 episodes（≈10 年）→ **不可檢定** | INFERENCE（power 親算；σ=ASSUMPTION） | prereg §5.2 |
| N13 | Lane A MDE@n=30 | prereg 3.6bps → **紅隊 day-cluster 修正 ≈5.4bps**（3.5bps 費率差 n=30 邊緣不可辨，需 ~60 pairs） | INFERENCE（σ=ASSUMPTION） | redteam RT-9 |
| N14 | 單 cell 月化封頂 | 宣稱效應 0.77 USDT/月；費率差全額上界 9.0；roster 理論天花板 116.7 | FACT-based 親算 | redteam §6.1（SQL 附） |
| N15 | motivating cell 選擇修正 | 未修正 p≈0.0145 → Sidak K=6 p≈0.084 / K=12 p≈0.16 + 跨窗符號翻轉 | INFERENCE（family 大小可辯，RT-14） | redteam §4.1 |
| N16 | probe 工程前提 | bb_reversion **無 use_maker_entry knob**（僅 ma/bbb/grid 有） | FACT（PA 親 grep `registry.rs:144/242/272`） | redteam §6.2 |
| N17 | G8 校準母集 | grid close_maker 408 attempts、realized fill rate 34.8%（同受 21d L1 蒸發鐘） | FACT | prereg §4.3 + redteam §5.2 |
| N18 | episode 累積率 | ~1.2/day；21d 滾動下穩態可重放 ≈25/快照——**不做增量 ledger 則 n_eff≥30 永不可達** | FACT+INFERENCE | redteam §5.2 |
| N19 | 外部先驗（結構類比，不入判定） | fill 率與 post-fill 報酬負相關 90/10（Binance perp live 232,897 單）；negative drift 回吞 ~90% 半價差（10Y 期貨） | [外部類比] | external §1 |
| N20 | 系統對照 | demo 30d 全系統 net −406 USDT/月 | FACT | redteam §6.1 |

---

## ③ 紅隊攻擊處置表（FATAL 項正面回答）

| # | 攻擊 | 紅隊 verdict | PA 裁決與處置 |
|---|---|---|---|
| ① | 信號變質（non-execution bias）：最壞形態 fill-only gross −9.9bps | SURVIVABLE_WITH_FIX | **接受**。ITT 三態記帳+三軌對比已把主刀變成量測對象（設計正確）；**FIX-1 凍結前必修**：fallback_ts ≥ realized_exit_ts 退化 case（p50 持倉 48s < τ=60s ⇒ ≥50% Lane A pairs 觸發）採紅隊建議=trade-forgone 記 −realized net + 固定 horizon 欄並列；「KILL power R1 可達」措辭限 K1/K4（K2 gap MDE 23bps@30 近零 kill power，真 selection kill 表現為慢性 INSUFFICIENT） |
| ② | markout n=3/−2.37 當先驗 | DEFLECTED | **確認 DEFLECTED**（PA 親讀碼復驗語義更正）。殘餘=宿主選擇順位失據，轉入⑤處置；「Δcost 符號真不確定」動機先驗中性、與 n=1 無關仍成立 |
| ③ | 30d 單窗×16 symbols 選擇效應（p≈0.084-0.16） | SURVIVABLE_WITH_FIX | **接受 FIX-2/FIX-3**。FIX-2 兩案中 PA 裁 **worst-of 分母保留 G6**（G6 是 root principle 13 cost_edge_ratio 在判定式的唯一投影，逐出=弱化誠實性；worst-of {重放窗, 60d, all-time} gross 消除窗口選擇直通判定的洞）+ exit 腿實付符號約定用 realized 實付（含 favorable slippage 實測符號）。FIX-3（≥15 post-registration episodes + 選擇窗內/外分裂欄）原文採納 |
| ④ | L1 覆蓋充分性 → **retention 21d 新事實** | SURVIVABLE_WITH_FIX（緊急） | **接受 FIX-4，升級為 GO 條件 C2**（PA 親驗 retention 政策）。本週 R1+G8；episode 窗 L1/trades 切片（[t_place−60s, t_place+τ+300s]，MB 級）入 immutable artifact（sha256）；凍結斷言錨遷 artifact store；累積改跨 run 增量 ledger（per-episode 統計量不依賴共同重放，pooling 數學不變）。**不修 FIX-4 則 §5.3 整張累積數學表作廢 + R1 三週後永久不可複核**——對 pre-registration 紀律是自毀級 |
| ⑤ | 月化價值：probe 子項 **FATAL** | probe FATAL / 重放保留 | **正面回答：接受 FATAL，probe 管道 descope（NO-GO 之 1）**。本 dossier 不派任何 probe 工程；SCREEN_PASS 前一行 Rust 不寫（凍結條款）。宿主取捨明文化：若未來目標是可移植執行 lever，經濟正確宿主是 **grid_trading**（現成 knob + 205k entry notional=8× + 408 attempts 校準 + n=96 markout 讀數）；bb_rev 僅以「信號條件化最乾淨的量測宿主」身份保留本輪，宿主變更=v2 重預註冊。重放本體 $0 保留，其價值（校準資產+路由決策輸入）不依賴 bb_rev cell 賺錢 |
| ⑥ | 「零成本破鎖」敘事 **FATAL** | 敘事 FATAL / 設計 SURVIVABLE | **正面回答：接受 FATAL，敘事全撤（NO-GO 之 3）**。三腿全斷是 runtime FACT（soak 攔截 415,651 筆全落 06-29→07-02；last-7d bb_rev 15/15 closes 標籤自流）；預註冊本文乾淨（未引此敘事），處置=stage2/roadmap 語境該敘事標 stale、禁遷入 probe 價值論證。**衍生工程項**（不阻塞 R1，獨立小 E1/MIT）：V147 label_source 前向接線半完成（bb_rev 新標籤 14/15 NULL）+ MIT D4 healthcheck 改用 label_close_tag lineage，否則按 label_source 過濾的監測少算 ~15× |

**次級修正一併採納**：RT-9（G4 power 表 day-cluster 修正，MDE 3.6→≈5.4bps@n=30；門檻不動、預期時程外推）、RT-11（E3 凍結定義=episode-share）、RT-12（Lane A M-arm 錨 realized order submit ts，orders 365d 保留可取，消 Lane B pro-maker 偏置）、RT-13（risk_verdicts 30d 滾動 → 另線 counterfactual blocked 母集同型蒸發，僅申報轉 PM）。

---

## ④ GO 執行包：預註冊定稿要點 + 工作量 + 驗證路徑 + kill 條件

### A. 預註冊 v1.1 定稿要點（在 QC 草案 v1 上的全部 delta；凍結前完成）

1. **FIX-1**：M-fb fallback_ts ≥ realized_exit_ts ⇒ 該 episode M-arm 記 trade-forgone、Δnet=−(realized net PnL)；固定 horizon markout 欄並列；「KILL power 在 R1 可達」限定 K1/K4。
2. **FIX-2**：G6 分母=worst-of {重放窗 gross_all, 60d realized, all-time}（G6 保留於判定式，PA 裁決見 §③-③）；probe 解除條件 4 同步；exit 腿實付=realized 實付含符號。
3. **FIX-3**：SCREEN_PASS 決策樣本 ≥15 個 post-registration（ts>2026-07-10）episodes；全 primary outcomes 報選擇窗內/外分裂欄。
4. **FIX-4**：R1+G8 本週；L1/trades episode 切片 immutable artifact（sha256）；凍結斷言錨=artifact store；跨 run 增量 ledger 機制寫入文本。
5. **FIX-5**：probe 管道 SCREEN_PASS 前不建（凍結條款）；cell 拯救/label 供血語言全撤；grid-vs-bb_rev 宿主取捨明文。
6. **RT-9/11/12**：power 表 day-cluster 修正（σ 實測後更新、門檻不動）；E3=episode-share 凍結定義；Lane A M-arm 錨 realized submit ts。
7. 其餘 v1 內容（三層 fill 規則帶 back-queue 主判、ITT 四態記帳、G1-G8/K1-K4 判定式、δ=1s/τ=60s/join-BBO/long-only 主格、σ-ASSUMPTION 申報、deviation policy §12）**原文凍結**——紅隊六面攻擊無一 FATAL 於重放本體，判定式框架 survives。

### B. 實作工作量初估

| 項 | 內容 | 規模 |
|---|---|---|
| 觸碰面 | **純 research Python，0 Rust / 0 migration / 0 config / 0 runtime / 0 engine**。`program_code/research/microstructure/fill_sim.py`（2000-line 例外 registry #8 已登記；additive 改動合規，新邏輯優先放 sibling 新檔避免加深例外）+ 新 placements 匯出 script（read-only SQL：trading.signals/fills → CSV，**維持 data_loader「只讀 market.*」契約不變**）+ 新 episode-ledger/切片 artifact 模組 + `SCRIPT_INDEX.md` 行 | LOC 估：fill_sim 入口鏈 +150-250、exporter ~100、ledger/artifact ~200、tests ~300 |
| Rust-first 合規註 | 既有 Python 研究 harness 的 additive 擴展，非新 standalone trading/risk/config 模組——Rust-first 不適用（等效方案取讀碼成本低者） | — |
| E1 派發 | **E1-A**（harness：placement 觸發+單側+ITT 四態記帳+FIX-1 規則+episode-cluster reduce；`--horizons 60,300` 免改碼）≈3-5 工作日；**E1-B**（切片 artifact+增量 ledger+exporter，新檔零重疊可並行）≈1-2 日 | **合計 ≤1 sprint；本週內可跑 R1** |
| 並行不阻塞項 | V147 label_source 前向接線 + D4 healthcheck lineage 修正（RT-6；獨立小 E1/MIT） | ~1 日 |
| E2 重點審查 3 點 | ① ITT 分母完整性（fill/adverse_through/no_fill/reject/censored 全入；fill-only 禁承載判定）② FIX-1 退化 case 記帳逐字符合 v1.1（≥50% pairs 觸發，任何 ad-hoc=deviation v2）③ artifact 切片 sha256 + 凍結斷言錨遷移完成（防 3 週後不可複核） | — |
| 降級/rollback | 全 additive research 檔：rollback=revert commits；產物 artifact-only，0 schema/0 部署副作用。**時間降級路徑**：若 harness 完整版 07-17 仍未 ready → 先跑最小版（既有 fill_sim + 手工 placement 清單 + `--horizons 60,300`）**優先保住 L1 切片釘存**，完整 ITT 版次輪補跑（切片在手即可離線重放，死線只綁數據不綁代碼） | — |

### C. 驗證路徑

```
v1.1 凍結（C1）→ E1 harness（≤07-17）→ R1 + G8 校準 + 切片釘存（≤07-19，C2）
  → 預期 INSUFFICIENT（n_eff 25<30、簇 14）但 KILL-capable（K1/K4）
  → 每週增量 ledger 重放（$0；per-episode 首覆蓋 run 入帳，後續只追加）
  → n_eff≥30 ∧ ≥15 post-reg episodes（最早 ~07-26 後）首次 SCREEN 審
  → 硬檢查點 2026-08-10：仍 INSUFFICIENT 且無 KILL → PM 裁 continue/park
  → 若 SCREEN_PASS：才進 probe 設計（另輪 PA + operator gate；宿主 grid-vs-bb_rev 屆時裁；
     Rust 管道屆時才寫）。SCREEN_PASS 語義上限=bounded probe 候選，非 edge 證明、非 promotion 證據
```

### D. Kill 條件（機械可裁，凍結於 v1.1）

- **K1** fill 饑餓：無條件 P(fill|τ=60s) Wilson 95% 上界 < 0.40。
- **K2** selection 殺信號：gross_fill≤0（60s∧300s）∧ gross_all>0 ∧ gap CI 排除 0（低 power 申報：n=30-60 幾乎不觸發，真 kill 走慢性 INSUFFICIENT）。
- **K3** 配對成本劣勢：Lane A Δnet day-cluster 單側 p<0.05（H1: maker 更貴），n_pair≥16。
- **K4** 上界死刑：touch-based 最樂觀 fill 規則下 maker RT 成本 ≥ taker → 結構死。
- **程序性 kill**：censored>30% 持續（E4）/ G8 校準比帶外 [0.7,1.3] → 重放模型作廢走 v2 / 2026-08-10 checkpoint park。
- **KILL 翻案條件**（凍結）：(i) fee 結構變化（RPI taker 免費腿 / VIP≥1——現 notional 6.9% 門檻不可達）→ 成本輸入重算免重跑；(ii) 新累積使 E+G 全過 → 自動恢復候選；(iii) 信號宇宙變化 → v2 重預註冊。

---

## ⑤ Open Questions 給 Operator

1. **形態認可**（決定 v1.1 凍結）：是否接受本 dossier 的 descoped 身份——「$0 儀器校準實驗，預期大概率 INSUFFICIENT-then-KILL，KILL 也有 M12 淨價值」；cell 拯救與 label 供血敘事撤下。
2. **排程優先權**（C2 死線）：本週 R1（07-19 前）需要 PM 立即派 E1——是否接受其相對其他 active work 的插隊。錯過死線的代價=06-28→07-02 episodes 的 L1 永久蒸發 + R1 不可複核。
3. **宿主意圖裁決**：若 operator 真正想要的是「可移植 maker 執行 lever」（roster 級 ~20-50 USDT/月 INFERENCE 帶）而非 bb_rev 量測，紅隊已示 grid_trading 是經濟正確宿主（現成 knob+8× notional+408 attempts 校準）——是否要 QC 出 grid 版 prereg 分支（v2 級決策，不阻塞本輪 R1）。
4. **G6 處置確認**：PA 裁 worst-of 分母保留 G6（vs 紅隊備選=降級 annex）——operator 若偏好更嚴（G6 逐出、SCREEN 純執行分量）亦可，兩案都封住選擇效應直通判定的洞。
5. **F-12 空窗**：06-20→06-28 bb_rev 零成交原因未明（soak 只解釋 06-29 後）——建議 E1 在 R1 第 0 步順帶查（cost_gate ledger vs 信號缺席），影響 episode 母集代表性判讀。
6. **RT-13 外溢**（另線申報）：risk_verdicts 30d 滾動使反事實 lane 的 71,207 行 blocked 母集同步蒸發——是否對另線也做同款切片釘存（本線僅申報，不裁）。

---

## 附：與既有裁決的關係（不可讓渡條款）

- **maker-nogo（2026-07-06, SHA 5d1622994）不重打不觸碰**：TODO `P1-MAKER-FIRST-MATURE-PERP-PIVOT` NO_GO marker 原文在位（PA 親核）；本研究=既有信號的執行路由（費率替代 3.5bps/leg ± 選擇效應），非做市報價 alpha；任何結果禁引為「maker-first 翻案」。
- **07-10 反事實預註冊統計框架沿用**（dedup/n_eff/day-cluster CR1/BH），不重打。
- **SCREEN_PASS ≠ cell 可盈利**：60d gross 下 cell 淨值仍負；gross 證據按既有標準另行累積；probe（若達）=量測儀器、learning-only、loss budget 封頂、`order_authority=NOT_GRANTED`、`promotion_evidence=false`。

PA DESIGN DONE: report path: docs/CCAgentWorkSpace/PA/workspace/reports/2026-07-10--move2_decision_dossier.md
