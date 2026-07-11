# MIT 盈利研判 Stage 2（守/攻）— ML/DB lens · 2026-07-09

**Agent**: MIT（ML & Database Auditor）
**範圍**: srv/ 全系統盈利面 + IBKR stock_etf_cash 研究 lane（ADR-0048 邊界內，僅研究價值/數據 ROI）。read-only：零修復/零 config/零 deploy/零 restart/零 auth 變更；Linux 僅 ssh trade-core read-only。
**底稿**: Stage 1 證據報告 `2026-07-09--profit-evidence-readonly-probe.md`（MIT，本檔引用為 §probe）+ AI-E `2026-07-09--ai_cost_roi_dormant_capability_audit.md`（引用為 §AI-E）。本檔只補增量判斷與新取證，不重推導。
**證據紀律**: FACT=可重跑命令/SQL/file:line；INFERENCE=靜態推論或不可重跑；ASSUMPTION=未取證假說。bull-only/單 regime 標 regime-bet。

---

## 本輪增量取證（Stage 1 之外新取的證據）

1. **outcome_review.py 無去重（F1 機制 file:line 落地）**：`helper_scripts/research/cost_gate_learning_lane/outcome_review.py` 全檔 grep `entry_ts|dedup|distinct|uniq` = 0 hit；score/eligibility（line 100-152）直接用 raw `outcome_count`，`sample_factor = min(2.0, outcome_count/min_outcomes_per_side_cell)`（line 116）把 5058 份偽複製當獨立樣本。F1 判定由 INFERENCE 升格 FACT（靜態+runtime 雙證）。
2. **訓練集 label 構造溯源（Stage 1 gap 5 關閉）**：canonical 訓練 SQL `program_code/ml_training/parquet_etl.py:457-480` 在邊界排除合成 reject（line 471 `label_close_tag IS DISTINCT FROM 'rejected_governance'`）→ model_registry `training_sample_size` 316/836 是 90d realized 標籤存量（`max_age_days=90`, line 478），非合成灌水；7d realized_fill 僅 +14（§probe D）→ **樣本增速 ≈2/day，訓練管線正在餓死而非被污染**。V147 `label_source` CHECK 僅 `('realized_fill','synthetic_reject')`（`sql/migrations/V147__decision_features_label_source.sql:131-132`）。
3. **model promotion 結構性死鎖（新診斷）**：`program_code/ml_training/canary_promoter.py:76-83` shadow→promoting 需 `shadow_min_training_samples=200`（grid 836/ma 316 可過）**且** `promoting_min_observations=500` 讀 `learning.decision_shadow_exits`（line 82 + `_query_shadow_observations` line 169-183）——該表 runtime 0 row、writer 未活（§probe D DEAD/FOUNDATION）→ **93/93 model 永鎖 shadow_only 與模型質量無關**。
4. **$0 數據資產已累積、零消費者（新取證，ssh read-only）**：
   - `deribit_vol_axis`：crontab 有 daily 05:17 條目（`crontab -l | grep deribit`）；`~/BybitOpenClaw/var/openclaw/deribit_vol_axis_runs/` **12 個 daily run（2026-06-21 起）**，最新 run `daily-20260709T031703Z` = surface 1,592 行 + skew 24 + term_structure 24（cron log tail）。採集端 raw-first 設計正確（`helper_scripts/research/deribit_vol_axis/collector.py` MODULE_NOTE：零過濾零丟 instrument、host allowlist 唯讀公開 API）。**repo 內 grep 零 feature/eval consumer**（僅 SCRIPT_INDEX 與 hftbacktest_fill_realism 的 client-pattern 引用）。
   - `polymarket_axis`：crontab 4×/hr capture + 4×/hr leadlag IC；`polymarket_axis_runs/` **1,130 runs**，最新 07-09 23:07（事件/監管 PARK 子軸的 $0 累積真的在跑）。
5. **profit-first loop TODO 狀態核對**：`TODO.md` P0 家族（line 24/33/37/38/39）確認 READY_FOR_PM_E3_DISPATCH 停點 + order-capable packet sha `305774b2` 唯一記錄 blocker=`renewed_active_bbo_manifest_stale_for_review_packet`；疊加 §probe F3（auth 過期）+ F1（證據無效）= 三重失效。

---

## 守 — Diagnoses（現有盈利歸因）

### D1 [leak/cost][FACT/high] 30d 全 roster true net 為負，費用主導
§probe A：30d gross −150.72 / fees 255.39 / **true net −406.11 USDT**；6 策略 net bps 全負（bb_reversion 唯一 gross 正 +9.06bps，扣兩腿費 −1.54bps）。fills.realized_pnl=GROSS（`pipeline_helpers.rs:507-529`）。可重跑：`SELECT engine_mode,count(*),sum(fee),sum(realized_pnl) FROM trading.fills WHERE ts>now()-interval '30 days' GROUP BY engine_mode`。
**盈利含義**：現 roster 在 VIP0 taker ~5.5-5.8bps/腿 + slippage ~6bps 結構下期望為負；bb_reversion 與翻正差恰好一個費率檔（往返 ~10.6bps vs gross 9bps）——與 maker-nogo infra-tier 結論同構，**premise 槓桿=fee tier**。regime-caveat：30d 單窗。

### D2 [leak/gate][FACT/high] gate 拒單整體真負；唯一誤殺候選母集=「正 edge <threshold」49,388 筆，其成本模型高估 ~5×
§probe C：blocked counterfactual 949,629 筆 avg −75.13bps、正率 14.9% → 系統性誤殺假說再次不成立（over-gate 淨貢獻為正：避免的虧損 >> 可能誤殺）。但 conservative_v1 假設 cost 92.3bps（slippage 30bps/腿）vs demo 實測 taker slippage ~6bps → 對高流動性 symbol 成本高估 ~5×，「edge 3.61bps < threshold 8.80bps」類 49,388 筆是唯一數學上可能藏誤殺的母集。
**盈利含義**：見 O1——這是零新數據的潛在直接回收。

### D3 [leak/other][FACT/high] profit-first loop 候選統計無效：5058 outcomes = 2 真觀測 ×2529 偽複製
§probe F1 + 本輪增量 1：兩個 distinct entry_ts（2026-07-07 16:19/16:20Z），60min markout 重疊 59/60，n_eff≈1-2；`outcome_review.py` 無 entry-window 去重、raw count 進 t/FDR。READY_FOR_PM_E3_DISPATCH 鏈三重失效（證據無效 + auth 過期 20.7h + BBO manifest stale）。
**盈利含義**：照跑 dispatch = E3/BB window 消耗在單日 NEAR +1.6% pop 的 regime-bet 上；修去重後 false-negative 榜可能整個重排。**loop 的「零 order/fill proof 缺口」根因不是執行阻塞，是上游證據品質**。regime-bet：bull-episode 單日。

### D4 [frozen/gate][FACT/high] ML 標籤斷糧：soak isolation 10d+ 把 realized_fill 供血掐到 ≈2/day
§probe F5 + 本輪增量 2：soak isolation 06-29 起擋 415,651 次 ordinary demo entry；7d realized_fill 標籤僅 14 行；訓練集確認 realized-only（parquet_etl.py:471），316/836 是 90d 存量。
**盈利含義**：學習迴路無新血——soak 每續一天，(a) 訓練窗 realized 密度再降 (b) JS estimates 凍在舊分布上（gate 的阻擋判斷也在老化）。**「隔離保護 probe」vs「餓死學習迴路」是 operator 未顯式計價的 trade-off**（O5 監測項）。可救性：高——非代碼債，純 gate 決策。

### D5 [frozen/dormant][FACT/high] model promotion 結構性死鎖：晉升 gate 讀 0-row 死表
本輪增量 3：canary_promoter 需 `decision_shadow_exits ≥500` 但該表 0 row、writer 未活 → 93/93 shadow_only 永鎖，**與模型質量無關**。maturity 評級：model_registry 鏈 = Shadow 階段但 promotion 維度 Foundation（consumer gate 存在、上游 writer 死）。
**盈利含義**：即使 D4 解除且模型變好，ML→決策影響恆為 0。可救性：中——V021 shadow-exit writer 活化是老債（接線後 0 row），需 E1 查 spawn 條件 + healthcheck；在那之前任何「訓練改善」的盈利貢獻上限=0。

### D6 [frozen/dormant][FACT/high] AI 三層零貢獻零成本；L1 98% timeout 白耗延遲
§AI-E N1/N4/N5/N8/N11：L1 judge_edge 728/743 timeout（8s 硬編）、成功樣本 avg 7s 仍超 3s SLA；param-apply 停 15d；L2 全史 0 call（$2/day 閒置 3 個月）；WP1-7 契約 DONE 零 runtime consumer。AI 可歸因 edge=0。
**盈利含義**：AI 棧目前既不燒錢也不賺錢；~180 call/day ×8s ≈24min/day 純延遲稅。修向（timeout 校準/keep_alive/降級）屬 E1；L2 消費決策屬 PM/operator。

### D7 [unrealized/undeveloped][FACT+INFERENCE/med] blocked-signal outcome ledger 是現成 fills-free 標籤源，訓練管線零利用
14d ledger 949,629 行 counterfactual markout outcome，只餵 review 榜（且帶 F1 缺陷），不進 decision_features 標籤鏈；V147 label_source 無 counterfactual 值。**這是系統已經在生產、但學習面白白丟掉的數據**。→ O2。

### D8 [unrealized/undeveloped][FACT/high] $0 數據資產已在累積、零消費端：deribit option surface 12d + polymarket 1,130 runs
本輪增量 4。option surface（DVOL/skew/term-structure）每日 1,592 行 raw 落盤 12 天，repo 零 consumer；polymarket 事件軸 $0 累積活著（leadlag IC 4×/hr）。「option flow 真未試」的實況=**capture 已 live、消費端未建**——研究期權值零兌現，捕捉維護成本白付。→ O3。

---

## 攻 — Opportunities

### O1 [INFERENCE/med] 「正 edge <threshold」49,388 母集的 realistic-cost 反事實重跑（前置：去重）
- **Hypothesis（可證偽）**：以實測 slippage 分位（`slippage_quantile_artifact.py` 已存在）替換 conservative_v1（92.3bps→實測 ~12-17bps 往返）重算該母集，去重後存在 ≥1 個 side-cell 的 HAC-t + BH-FDR 顯著 net>0。若重跑後 0 cell 顯著翻正 → gate 無誤殺結案，假說死。
- **why_not_tried**：review 鏈固定用 conservative_v1；5× 高估是 Stage 1 才量化的；且 F1 去重缺陷讓現榜不可信，須先修。
- **est_edge**：母集名義 edge 3.6-8.8bps 區間 × 49,388 signal；即使 5% cell 翻正、demo 量級估 O(10) USDT/月起步——價值主要在「解鎖被 gate 鎖死的正 edge 類」的機制驗證，非額度。
- **est_cost**：$0 數據、純離線 compute + E1/QC 工時（去重補丁 + 重跑腳本）。
- **wall_break_prob**：med——realistic 成本後部分 cell 名義 edge 仍在 taker 牆（~11-12bps 往返）邊緣；能翻正的是 spread/流動性最佳的 symbol 子集。
- **how_to_validate（leak-free）**：(1) `outcome_review.py` 加 per-(side_cell, entry_ts) 去重 + effective-n；(2) markout 窗用 entry 後固定 horizon（已是 PIT）；(3) HAC Newey-West（overlapping windows）+ BH-FDR；(4) 顯著 cell 走既有 bounded-probe 鏈（E3/BB）拿真 fill 驗證。owner=QC(顯著性)+E1(去重)；MIT 審 leak/effective-n。

### O2 [ASSUMPTION/med][paradigm_challenge=TRUE] Fills-free 標籤軸：去重後的 counterfactual markout 進訓練供血
- **Hypothesis（可證偽）**：對同 (strategy,symbol) 在重疊時窗內，去重後 blocked-outcome markout 標籤與 realized_fill 標籤的 net_bps 分布一致（KS p>0.05 / Wasserstein 小於閾值）；若一致，訓練樣本增速可從 ~2/day 恢復至 >100/day 而不引入 look-ahead；若分布系統性偏移（無 fill 的 selection bias / 無滑點實現差）→ 假說死或需 bias-correction（credit reject-inference 同款校正）。
- **why_not_tried**：範式鎖定「標籤=真實成交」——V147 label_source 只有 realized_fill/synthetic_reject；soak isolation 決策時學習面代價未被計價。外部文獻已有同構方法：Post-Rejection Follow-up Sampling（PRFS，arXiv 2606.08228，DEX 交易的 rejected-signal counterfactual 前向採樣）+ credit-scoring reject inference。
- **paradigm_challenge**：true——挑戰「學習必須等 fill」；直接回應 operator「被動等數據=不接受」鐵則：系統每天已生產 ~68k 條 counterfactual outcome，是自家丟掉的供血。
- **est_edge**：間接——解 D4 斷糧（樣本增速 ×50）+ 讓 JS estimates/quantile 模型跟上當前 regime；上限受 D5 死鎖約束（須並行解）。
- **est_cost**：E1 工時 + V148 migration（label_source 加 'counterfactual_markout'，Guard A/B/C + CHECK 擴值）+ 訓練管線 label_source-aware 加權（synthetic:informative 比例 gate 既有機制可複用，parquet_etl.py:444 注釋已預留 classifier lane 語義）。
- **wall_break_prob**：unknown——翻的是內部「標籤斷糧」牆，非市場成本牆；不直接產 alpha。
- **how_to_validate（leak-free）**：(1) 先離線：歷史重疊窗 paired KS/Wasserstein（realized vs counterfactual 同 cell）；(2) markout 計算全 PIT（entry_ts 後固定 horizon，無 current-bar 污染）；(3) 訓練 A/B：realized-only vs mixed，CPCV + purge/embargo，看 OOS pinball skill 是否退化；(4) 任何混入前 label_source typed lineage 落 V148（防 V147 CHECK silent-noop——CHECK 是 NOT VALID 加的，新值須 Guard）。
- **regime_caveat**：counterfactual markout 無 queue/fill 模擬 → 只對 taker-style 信號有效；maker 策略（fill_sim NO-GO 域）不適用。

### O3 [ASSUMPTION/med] Deribit option surface 消費端：regime/drift 防禦特徵（數據已在手，12 天存量）
- **Hypothesis（可證偽）**：DVOL 分位 + 25Δ skew 變率 + term-structure 斜率（全 shift(1) PIT）對 BTC down-regime 切換的偵測 lead 於 realized-vol 特徵；以 06-15 grid-in-trend 事件類回放，counterfactual 降倉可避免該類虧損的顯著部分（grid_trading 30d net −232 USDT 的可歸因份額）。若 lead-lag（HAC）不顯著或 counterfactual 減虧 ≤ 摩擦 → 假說死。
- **why_not_tried**：06-13 另類數據軸螢幕未覆蓋 option flow；capture 06-21 才上（已 12 runs）；消費端從未排program。**注意：這不是重打已 NO-GO 的方向預測（線性 IC×OHLCV×taker）——是 regime gating 防禦價值，減虧=net PnL 組件（CLAUDE.md root principle：risk control is loss-reduction）**。
- **est_edge**：防禦端：demo 30d grid −232 USDT 中 down-beta 事件類的可避免份額（06-15 RCA 已證該類是主虧因）；無新增市場成本。
- **est_cost**：$0 數據（已累積 + CryptoDataDownload 免費歷史 CSV 回補 backtest 窗）+ E1 建 PIT 特徵表（hypertable + engine_mode N/A market 表規範）+ MIT drift/lead-lag 評估工時。
- **wall_break_prob**：med——防禦不需翻 taker 牆；牆在統計檢定（skew 訊號在 crypto 的雜訊率高）。
- **how_to_validate（leak-free）**：(1) 12d 存量不夠 backtest → 用 CryptoDataDownload 歷史 DVOL/options CSV 回補 ≥1y（含 2026-06 BTC +4.5% 與 5 月下行段，雙 regime）；(2) 特徵全 shift(1)、resample closed-bar only；(3) lead-lag 用 HAC + 對稱鏡像測試（up-regime 同構檢驗防 down-only cherry-pick）；(4) counterfactual replay 只動倉位縮放不動信號（隔離防禦價值）。QC 共審顯著性。
- **regime_caveat**：防禦價值集中 down-regime；up-regime 降倉的機會成本必須入帳（雙向淨額）。

### O4 [ASSUMPTION/low] IBKR stock_etf_cash lane 數據 ROI：S3/S5 契約先鎖 PIT lifecycle 基座，近期兌現=跨資產 regime 特徵
- **Hypothesis（可證偽）**：(a) lane 的首年研究價值主要不在美股 alpha（樣本/費用/authority 全未備）而在：day-1 起 survivorship-correct 的 universe lifecycle（listed/delisted/corporate actions）——crypto 側教訓（948 symbols/296 delisted 才補）值一次前置設計；(b) SPY/QQQ 日線 vol/breadth 作 crypto regime 特徵的增量 IC>0（可證偽：對 BTC down-regime 標籤 HAC lead-lag 不顯著即死）。
- **why_not_tried**：lane 剛過 P2 gate producer（TODO line 45），S3/S5 row 契約未定——正是 schema 決策窗口；跨資產 regime 特徵從未入 feature 盤。
- **est_edge**：研究期權值 + regime 特徵增量（低，crypto-equity 相關性眾所周知，增量可能被 BTC realized vol 自身吸收——誠實標 low）。
- **est_cost**：日線級存量小（regular table 即可，非 hypertable 級）；讀路徑在已授權 read-only 邊界內；禁 order-write/auto-promote 不變。
- **wall_break_prob**：unknown——lane 本身不面對 crypto 成本牆；美股側的牆（PFOF/最小費率/資本）評估屬未來 ADR。
- **how_to_validate**：MIT 審 S3/S5 契約時強制 PIT 欄位（listed_at/delisted_at/adjustment factors/engine_mode 隔離即 lane 隔離）；跨資產特徵走 O3 同款 leak-free lead-lag 協議。6 個月累積後首個 walk-forward 研究再評。

### O5 [FACT/high] Unlock 監測包：把三個「內部牆」變成有 owner 有閾值的監測項
本域找得到直接機會（O1-O3），此條是把守側三個 blocker 顯式變 unlock 項（operator 鐵則：前提監測=合法機會）：
1. **標籤供血監測（解鎖 D4）**：`SELECT count(*) FROM learning.decision_features WHERE label_source='realized_fill' AND ts>now()-interval '7 days'`（<50/7d = 餓死中）。owner=operator 週巡檢；建議 E1 加 `passive_wait_healthcheck.check_label_supply()`（CLAUDE.md §七 被動等待必附 healthcheck）。soak isolation 存續決策顯式計價：「probe 隔離收益」vs「每天 ~2 標籤 vs 潛在 >100」。
2. **promotion 死鎖監測（解鎖 D5）**：`SELECT count(*) FROM learning.decision_shadow_exits`（=0 即死鎖持續）。owner=PM 派 E1 查 writer spawn 條件；任何「模型改善」工作在此表通水前盈利上限=0，排期應據此排序。
3. **loop 證據品質 gate（解鎖 D3）**：dispatch 前置檢查 `distinct entry_ts count ≥ min_outcomes_per_side_cell`（把 n_eff 檢定寫進 READY 判準）。owner=PM/E3 review checklist；在 outcome_review 修去重前凍結對現榜的 order-capable 消耗。
4. **infra-tier/fee 前提監測（解鎖 D1 的 premise 槓桿）**：bb_reversion 類 cell 的 break-even 差一個費率檔——監測 Bybit VIP tier 門檻與自家 30d volume 距離（`SELECT sum(qty*price) FROM trading.fills WHERE ts>now()-interval '30 days'`）+ maker rebate 檔位變化。owner=operator 月檢。（維持 maker-nogo 裁決不重打；這是裁決自帶的 premise 監測。）

---

## 已判定裁決遵循聲明
本檔未重提：OHLCV+TA 線性方向 alpha（NO-GO）、maker fill_sim 雙窗（NO-GO，僅引其 premise 監測）、funding/OI/LSR/liq-cascade down-beta 軸（NO-GO）、Polymarket 價格衍生子軸（KILL——本檔僅取證事件/監管 PARK 子軸的累積仍活著：1,130 runs，覆核歸 QC）。O3 的 option surface 是 06-13 盤點的真未試軸且用途為 regime 防禦非方向預測，非重跑同一測試。

## 與 QC 邊界
O1/O3 的顯著性判定=QC；MIT 持 leak-free/effective-n/PIT 審計權。O2 的分布一致性檢驗=MIT 主負（label 工程），訓練後 alpha 影響=QC。

## Gaps（本輪）
1. deribit/polymarket run 內容只驗 wiring+體積，未逐 run 質檢（surface 完整性/停機窗）。
2. `decision_shadow_exits` writer 未活的根因（spawn 條件 vs flag）未追——歸 E1。
3. O3 lead-lag 未做任何預跑（純假說）；O4 增量 IC 同。
4. Polymarket leadlag IC artifact 內容未讀（QC 域）。

## 外部借鑒來源
- PRFS counterfactual outcome measurement（rejected-signal 前向採樣）: arXiv 2606.08228
- Off-policy evaluation 框架: arXiv 2405.10024 等（見 sources）
- Deribit 免費歷史數據（DVOL/options CSV）: cryptodatadownload.com/data/deribit
- Deribit 公開 API 文檔: docs.deribit.com

MIT AUDIT DONE: docs/CCAgentWorkSpace/MIT/workspace/reports/2026-07-09--profit-diagnosis-stage2-ml-lens.md
