# QC 裁決 — 反事實重跑 §2.3 複本一致性語義(prereg v2 修訂 + 24 個 DATA_INTEGRITY_SUSPECT_EXCLUDED cells 處置)

**日期**:2026-07-12
**作者角色**:QC(Quantitative Consultant,外部量化顧問)
**任務來源**:auto-fix loop ledger 隊列 I(`docs/CCAgentWorkSpace/PM/workspace/reports/2026-07-12--auto_fix_loop_ledger.md`);上游=E1 重跑報告的 QC follow-up ticket(該報告「Operator / PM 下一步」第 3 點)
**性質**:預註冊判準的**裁決 + v2 修訂正本**(依 v1 §8.3:「判準本身的修改→必須發布本檔 v2 並 supersede,不得原地改」)。本檔 §E 即 prereg v2 的規範性全文(delta-supersede 形式,基準逐字節釘死,見 §E.0)。

## 凍結錨(2026-07-12 QC 親查,全部 read-only)

| 錨 | 值 |
|---|---|
| prereg v1 正本 | `docs/research/2026-07-10--counterfactual_rerun_preregistration.md`,git `10dbfb10b` |
| verdict artifact | `docs/CCAgentWorkSpace/E1/workspace/reports/2026-07-10--counterfactual_rerun_evidence/counterfactual_rerun_prereg_v1.json`,sha256 `d09bf86c5031652b53d58e97a75818d8b70e0b2e360127bd13a7f66a4d5cd832` |
| E1 重跑報告 | `docs/CCAgentWorkSpace/E1/workspace/reports/2026-07-10--r3-wpa4-counterfactual-rerun-verdict.md` |
| 實作正本 | `helper_scripts/research/cost_gate_learning_lane/counterfactual_rerun.py::build_observations_for_cell`(`_REPLICA_TOL=1e-9`) |
| 裁決時 Mac HEAD | `7d4d43789` |

---

## A. 問題陳述

v1 §2 第 3 點(下稱 §2.3)規定:同 `(side_cell_key, entry_minute, horizon)` 去重組內,複本 `realized_net_bps` 或 `gross_bps` 不一致(容差 1e-9 bps)→ 該 cell 標 `DATA_INTEGRITY_SUSPECT`,排除出檢定 family。2026-07-10 重跑據此排除 **24 個 (cell,horizon)**,其中 **21 個原本通過全部 E1-E5 eligibility**(n_eff 30-167、G 10-14 天、top-day ≤19%),24 個 `mean_net_E` 全負(−3.8 ~ −93.6 bps),敏感性欄 cluster p 全部 ≈0.67-1.0(與 VETO 同向)。E1 按 v1 嚴格執行、未擅改,並把「是否發 v2 放寬語義」交 QC 裁決。

裁決問題:這 24 個排除是**真數據完整性風險**(必須維持隔離),還是 **§2.3 檢查設計與數據生成機制的錯配**(檢查器把合法觀測誤判為損壞)?

## B. QC 親驗證據(全部 read-only;Linux 經 ssh trade-core 唯讀)

### B.1 artifact 24 cells 全表(自 verdict artifact `cells[]` 逐格抽出)

| side_cell_key | h | n_dedup | n_eff | 不一致組 | 組占比 | mean_net_E | G | eligibility |
|---|---|---|---|---|---|---|---|---|
| grid_trading\|APTUSDT\|Buy | 60 | 1,801 | 134 | 1 | 0.06% | −43.9 | 11 | 全過 |
| grid_trading\|APTUSDT\|Sell | 60 | 7,098 | 167 | 19 | 0.27% | −50.0 | 14 | 全過 |
| grid_trading\|ARBUSDT\|Buy | 60 | 1,503 | 133 | 2 | 0.13% | −31.8 | 13 | 全過 |
| grid_trading\|AVAXUSDT\|Sell | 60 | 6,406 | 155 | 8 | 0.12% | −35.0 | 13 | 全過 |
| grid_trading\|BCHUSDT\|Buy | 60 | 1,762 | 129 | 1 | 0.06% | −80.1 | 12 | 全過 |
| grid_trading\|BCHUSDT\|Sell | 60 | 6,666 | 159 | 7 | 0.11% | −93.6 | 13 | 全過 |
| grid_trading\|BNBUSDT\|Buy | 60 | 1,272 | 116 | 5 | 0.39% | −43.0 | 10 | 全過 |
| grid_trading\|DOTUSDT\|Sell | 60 | 5,255 | 143 | 13 | 0.25% | −41.3 | 13 | 全過 |
| grid_trading\|ETCUSDT\|Sell | 60 | 4,512 | 125 | 10 | 0.22% | −42.3 | 13 | 全過 |
| grid_trading\|ETHUSDT\|Sell | 60 | 3,070 | 125 | 14 | 0.46% | −23.7 | 13 | 全過 |
| grid_trading\|FILUSDT\|Sell | 60 | 4,264 | 124 | 14 | 0.33% | −53.4 | 13 | 全過 |
| grid_trading\|ICPUSDT\|Buy | 60 | 1,591 | 122 | 10 | 0.63% | −84.6 | 12 | 全過 |
| grid_trading\|INJUSDT\|Buy | 60 | 2,276 | 143 | 1 | 0.04% | −49.3 | 12 | 全過 |
| grid_trading\|LTCUSDT\|Buy | 60 | 930 | 95 | 3 | 0.32% | −43.8 | 11 | 全過 |
| grid_trading\|NEARUSDT\|Sell | 60 | 5,650 | 153 | 10 | 0.18% | −29.2 | 13 | 全過 |
| grid_trading\|OPUSDT\|Buy | 60 | 1,689 | 146 | 3 | 0.18% | −30.2 | 13 | 全過 |
| grid_trading\|OPUSDT\|Sell | 60 | 6,788 | 158 | 10 | 0.15% | −36.8 | 13 | 全過 |
| grid_trading\|SUIUSDT\|Sell | 60 | 6,736 | 162 | 11 | 0.16% | −26.4 | 13 | 全過 |
| grid_trading\|XRPUSDT\|Buy | 60 | 2,499 | 144 | 8 | 0.32% | −21.5 | 13 | 全過 |
| grid_trading\|XRPUSDT\|Sell | 60 | 4,868 | 153 | 4 | 0.08% | −26.3 | 12 | 全過 |
| ma_crossover\|BTCUSDT\|Buy | 60 | 118 | 29 | 4 | 3.39% | −9.7 | 13 | E1 fail |
| ma_crossover\|BTCUSDT\|Sell | 60 | 107 | 25 | 7 | 6.54% | −12.2 | 10 | E1 fail |
| ma_crossover\|BTCUSDT\|Sell | 240 | 23 | 6 | 4 | 17.39% | −3.8 | 3 | E1+E2 fail |
| ma_crossover\|ETHUSDT\|Sell | 60 | 91 | 30 | 1 | 1.10% | −31.0 | 11 | 全過 |

合計:不一致組 **170 / 76,975 去重組 = 0.221%**;`zero_variance_suspect` 全 false;24 cells 觀測源 100% ledger。**單一不一致組即可整 cell 排除**(如 APTUSDT|Buy:1/1,801 組 → n_eff=134 的 cell 全滅)。

### B.2 實作正本閱讀(檢查器實際比對什麼)

`build_observations_for_cell`:分組鍵=`entry_minute`(cell/horizon 內);觸發條件=組內 `gross_bps`/`realized_net_bps` 值域 >1e-9 **或欄位缺失不對稱**(`len(present) != len(values)`)。檢查器**不區分**組內成員是「同一 `entry_ts_ms` 的真複本」還是「同分鐘不同秒的不同 entry」;也不做行內算術自洽驗證。代表行規則(attempt_id 字典序最小)本身確定性選一行,組內離散**不污染**保留樣本值——排除是純 flag 級隔離。

### B.3 Linux ledger 機制驗證(QC 2026-07-12 親跑,唯讀)

**申報**:以下掃描用 current ledger(含 post-freeze 行),計數**不可**與凍結視圖對表;僅用於機制定性。

1. **抽樣 3 個受影響 cell**(APTUSDT|Sell、ETHUSDT|Sell grid、ETHUSDT|Sell ma;h=60):35 個組內 gross 漂移組中,**23 組=entry 側**(同分鐘不同秒的 `entry_ts_ms`,entry 價不同 → gross 不同),**12 組=exit 側**(entry_ts_ms 與 entry_price 完全相同,但各 attempt 的 exit 觀測快照時點不同 → exit_price 差 1-2 tick,gross 漂移可達 ~20bps;部分組 `generated_at_utc` 相差一個 watcher pass)。兩種模式都是 lane watcher 的**觀測粒度效應**(信號秒級重發 × 觀測快照非同時),不是儲存損壞。
2. **全量行內算術自洽**(233 萬行,110 萬非 censored 行):以 `entry_price`/`exit_price`/`side` 重算 gross_bps,容差 1e-4 bps → **0 違例**。儲存與計算管線算術乾淨。
3. **全量同 (attempt_id, horizon) 值漂移**:110.9 萬 distinct 鍵中僅 **2 例**(`ctx-demo-ATOMUSDT-1783063742813`、`ctx-demo-INJUSDT-1783171744508`,均在 `probe_ledger.20260704T234944Z.jsonl`,同 attempt 寫入兩行、exit_price 同、gross 不同 ⇒ entry_price 不同)——這才是真「同一觀測記了兩個值」的完整性異常,發生率 0.00018%。

## C. 分析

1. **v1 §2.3 把兩個失效模式混進一個檢查**:(i) 真完整性違例(同一觀測身分記了不同值——B.3 第 3 點,實測極稀);(ii) 分鐘量化桶內的合法觀測異質(B.3 第 1 點,佔絕對多數)。v1 的分組鍵(entry_minute)+ 零容差(1e-9)使模式 (ii) 必然觸發——只要該分鐘內價格動過且信號重發過。
2. **對高頻重發 cell 是系統性 false positive**:grid_trading 重發最密 → 24 個排除 cell 中 20 個是 grid_trading;n_dedup 越大越必中(APTUSDT|Sell 7,098 組僅需 1 組中招)。後果:**v1 §8.3 的 flip-condition(「新的去重樣本使 E1-E3 重過 → 自動恢復候選資格」)對這批母集中最大的 cells 結構性不可達**——未來任何重跑,同一機制會再次把它們排除。這不是保守,是把「誤殺量測」與「gate 淨貢獻收口」兩個方向的結論都永久擋死(cell 永遠 UNDECIDED,§8.4 雙向計價無法覆蓋)。
3. **排除不提供統計保護**:代表行規則已確定性取一行(attempt_id 字典序最小=最早重發,13 位等長 ms 後綴下字典序=數值序,與 outcome 符號無相關性),組內離散從未進入統計量。v1 §2.3 的 cell 級隔離在模式 (ii) 下只有資訊損失、沒有偏誤防護。
4. **v1 §2 的分鐘量化前提部分不成立**:「同一分鐘內的多個 entry_ts_ms 共享同一根 1m bar 的價格路徑,屬同一觀測」只對 kline_backfill 源嚴格成立;ledger 源在秒級觀測 entry/exit。但分鐘量化本身仍應保留——它使 n 低估(保守)且是 v1 凍結的觀測單位定義;需要修的只是「桶內異質=損壞」這一推定。
5. **欄位缺失不對稱觸發**(B.2)同屬誤設計:組員缺 `realized_net_bps` 不影響代表行統計;缺 `gross_bps` 的行本就走 E5 剔除路徑。

## D. 裁決(兩部,機械可執行)

### D.1 對 2026-07-10 verdict artifact:維持 v1 原判,不追改

- 24 cells 維持 `DATA_INTEGRITY_SUSPECT_EXCLUDED`;**不得**因「mean 全負同 VETO 向」追認為 VETO——v1 §2.3 下排除 cell 無統計結論,事後看了統計量再改判正是預註冊禁止的模式(v1 檔頭:「看到重跑統計量之後,不得修改任何判準」)。
- 全域裁決 **FALSE_KILL_HYPOTHESIS_HAMMERED 不受影響**:它站在 m=7 family(7/7 VETO、BH 0 過)上,與這 24 cells 無涉。
- 24 cells 的全負 means 在 v2 語義重跑正式納入前,**不得**在任何報告中引用為 gate 淨貢獻或誤殺排除證據(可引用為「待 v2 重跑覆核的方向性一致觀察」,須附本檔引用)。

### D.2 發布 prereg v2:§2.3 兩層化(僅前瞻生效)

理由總結:模式 (ii) 誤判有實證機制解釋(B.3);真異常檢測按 attempt 身分與行內算術自洽才對症(B.3 第 2/3 點);v1 檢查對最大 cells 的系統性 false positive 使 §8.3 承諾的自動重審機制空轉。修訂**不移動任何統計門檻**(E1-E5、P1-P5、q、horizon 宇宙、成本雙軌全部不動),不引入自由參數,fail-closed 方向保留(真完整性違例仍整 cell 排除)。

---

## E. Preregistration v2(規範性全文,delta-supersede)

### E.0 基準與生效範圍

- **基準**:v1 = `docs/research/2026-07-10--counterfactual_rerun_preregistration.md` @ git `10dbfb10b`。v2 = v1 全文逐字承接 + 本節列舉的修訂。除本節明文替換/新增者外,v1 §0-§10 一切條款(母集凍結、觀測單位、去重、n_eff、E1-E5、cluster-SE、BH-FDR、成本雙軌、regime 標註、判定式 P1-P5/VETO/SAMPLE_INSUFFICIENT、三態裁決語言、翻案條件、artifact 契約、邊界、偏離政策)**逐字有效、一字不動**。
- **生效**:v2 只約束**未來**執行的重跑。2026-07-10 artifact(sha256 `d09bf86c…`)永久保持 v1 原判,不追改、不重新標註。
- **schema**:v2 重跑 artifact 用 `schema_version="counterfactual_rerun_prereg_v2"`,必引本檔路徑+git SHA。

### E.1 替換條文:§2 第 3 點(複本一致性檢查)→ v2 兩層語義

**層 1 — 記錄級完整性違例(真損壞檢測;fail-closed 處置與 v1 相同)**。以下任一成立 → 該 cell 標 `DATA_INTEGRITY_SUSPECT`,排除出檢定 family,artifact 列明細,不得靜默取平均、不得給統計結論:

- (a) 同 `(attempt_id, horizon_minutes)` 存在多行,且 `gross_bps` 或 `realized_net_bps` 值域 > 1e-9 bps(同一觀測身分記了不同值;實測基準率 2/1.1M,見本檔 B.3)。
- (b) 任一非 censored 行**行內算術自洽**失敗:`|gross_bps − sign(side) × (exit_price − entry_price)/entry_price × 10⁴| > 1e-4 bps`(容差=float64 於 1e4 尺度的往返誤差上界;實測全量 0 違例)。

**層 2 — 分鐘桶內觀測異質(合法生成機制;不觸發排除)**。同 `(side_cell_key, entry_minute, horizon)` 組內、**不同** `attempt_id` 成員之間的 `gross_bps`/`realized_net_bps` 漂移(entry 側秒級重發或 exit 側觀測快照非同時,機制見本檔 B.3),重新定性為取樣代表行語義的預期現象:

- 代表行規則不變(v1 §2.2:attempt_id 字典序最小,確定性)。
- 不標 suspect、不排除;cell 照常進入 eligibility 與 family。
- **新增披露欄(僅列報,不參與判定)**:per (cell,horizon) 記 `intra_minute_dispersion = {heterogeneous_group_count, heterogeneous_group_pct, max_intra_group_gross_range_bps}`。

**欄位缺失不對稱**(組內部分成員缺 `realized_net_bps`/`gross_bps`):不再觸發 cell 級 suspect。缺 `gross_bps` 的行沿 v1 §3 E5 既有剔除路徑處理(剔除計數照記)。

**V=0 退化保護**(v1 §4)不變:樣本全同值仍標 `DATA_INTEGRITY_SUSPECT`(去重逃逸嫌疑)。

### E.2 同凍結窗重跑的重標註契約

若未來以 v2 對**同一凍結輸入**(v1 §0.1 錨)重跑:

- family 與 BH-FDR 必須在 v2 語義下**整體重算**(不得把 v1 的 m=7 結果與 v2 新納入 cells 混拼)。
- 原 24 cells 的輸出行必帶 `reclassified_under_v2=true` + `v1_verdict="DATA_INTEGRITY_SUSPECT_EXCLUDED"` 對照欄。
- headline 語言義務:v2 重跑報告必須並列 v1/v2 兩版 family 計數與裁決語言;若三態裁決(v1 §8.2)不變,標明「v2 重跑無決策增量,僅收口覆蓋」。

### E.3 資料窺探申報與無害性論證(v2 版 §0.2)

- **申報**:本 v2 撰寫時,QC 已見 24 個被排除 cells 的 outcome 統計(mean_net_E 全負 −3.8~−93.6、敏感性 cluster p ≈0.67-1.0、n_eff/G/top-day 全欄)。這與 v1 §0.2 的「未見統計量」狀態不同,必須申報。
- **無害性論證**(修訂為何仍成立):(i) 修訂動機來自**機制證據**(entry_ts_ms 秒級分佈、exit 觀測快照、算術自洽、attempt 重複率——全部是結構 metadata 與生成機制事實,見 B.3),不是 outcome 統計量的形狀;(ii) 在凍結資料上,重納入只可能新增 P1-fail(mean<0)的 VETO 向 cells,**數學上不可能製造 PROMOTE**——修訂無從為任何候選翻正服務;(iii) 對未來資料,兩層規則對 promote/veto 方向中立(層 1 排除與層 2 納入都不看 outcome 符號)。
- **不動門檻聲明**:E1-E5、P1-P5、q=0.10、horizon 宇宙 {60,240}、成本雙軌公式、1e-9(層 1a)容差全部與 v1 相同;v2 唯一新數值 1e-4 bps(層 1b)由浮點精度界定,非統計調參。

### E.4 v2 執行邊界(承 v1 §9,逐字)

PG read-only;不動 runtime cost gate/風控閾值/授權;Cost Gate 不降級;`order_authority=NOT_GRANTED`;`promotion_evidence=false`;demo-only;fail-closed 不鬆動。結論最大效力=bounded probe 候選榜重排,不構成 live 或 promotion 證據。

---

## F. Follow-up 歸屬(本輪不執行)

1. **v2 重跑不在本輪**(任務約定)。且 QC 明示:在同一凍結資料集上立即重跑**無決策價值**——24 cells mean 全負 ⇒ P1 全 fail ⇒ 只會把 family 從 m=7 擴到最多 m≈28 並全數 VETO;BH step-up 對新增 p≈1 成員單調,7 個既有 VETO 不可能翻;三態裁決語言不變。其淨效益僅是 §8.4 gate 雙向計價的覆蓋收口(Σ n_eff×mean_net_E 更負)。
2. **自然執行時點**:下一次因新增去重樣本觸發 v1/v2 §8.3 flip-condition 重審時,以 v2 語義執行(屆時 v2 修訂同時解鎖這 21 個大 cell 的自動重審通道——這才是本修訂的主要價值)。
3. **實作 follow-up**(E1 範疇,獨立票):`counterfactual_rerun.py::build_observations_for_cell` 按 E.1 改寫檢查器 + 單元測試(層 1a/1b/層 2/缺欄不對稱四個真值分支);2 例已知 attempt 重複行(B.3 第 3 點)作為層 1a 的真陽性 fixture。
4. **ledger 生成端觀察票**(低優先):同 attempt_id 雙寫(2 例,2026-07-04 檔)的 watcher 寫入路徑值得一查,但發生率 0.00018% 不構成本輪修復標的。

## 落款

本裁決在已見 24 cells outcome 統計的狀態下作出,窺探狀態已於 E.3 全額申報;裁決的兩部結構(v1 原判不追改 + v2 僅前瞻)正是為了使該窺探無法回流進任何已發布結論。v2 未移動任何統計門檻;唯一放寬的是「把合法觀測異質誤標為數據損壞」的檢查器語義,且以更精確的記錄級檢測(attempt 身分 + 算術自洽)替代,fail-closed 方向不變。

**QC 簽署**:2026-07-12
