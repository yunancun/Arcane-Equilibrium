# E1 報告 — R3 WP-A.4 反事實重跑:71,207 母集 + 33 GROSS cells 新統計裁決

日期:2026-07-10 · 執行者:E1(WP-A.4)· charter:`scratchpad/r3_fix_charter.md` WP-A 第 4 點 · 狀態:IMPLEMENTATION DONE,待 E2 審查
判準正本:`docs/research/2026-07-10--counterfactual_rerun_preregistration.md`(git `10dbfb10b`,凍結,未改任何判準)

## 裁決(一句話)

**誤殺假說在 E[cost] 主判下落錘(FALSE_KILL_HYPOTHESIS_HAMMERED)**:7 個可檢定 (cell,horizon) 全部 VETO(mean_net_E −23~−67bps、cluster p 0.98~1.0、BH 0 過),0 個翻正 cell;NEAR 候選(`ma_crossover|NEARUSDT|Buy`)5,058 行去重後 n_eff=1、單日,判 `SAMPLE_INSUFFICIENT_AFTER_DEDUP` 且同時觸發 `EXECUTION_REALISM_SUSPECT`(realized EV −12.0bps/n=14 vs 反事實 +130.5bps,gap>50)——F1 偽複製裁決落錘,原「64.98bps 候選」證據作廢。

## 產出

| 物件 | 路徑 |
|---|---|
| verdict artifact(`counterfactual_rerun_prereg_v1`,265KB) | `docs/CCAgentWorkSpace/E1/workspace/reports/2026-07-10--counterfactual_rerun_evidence/counterfactual_rerun_prereg_v1.json`(sha256 `d09bf86c…`) |
| 成本輸入快照(slippage v2 artifact,2026-07-10T01:39Z) | 同目錄 `slippage_quantiles_v2_input.json` |
| 重跑管線(新代碼) | `helper_scripts/research/cost_gate_learning_lane/counterfactual_rerun.py`(~1,000 行,>800 需 E2 留意,<2000 硬頂) |
| CR1 cluster-t 純函數(預註冊 §4 指名) | `evidence_stats.py::cluster_one_sided_t_p_value` |
| 單元測試(10 條) | `helper_scripts/research/tests/test_cost_gate_counterfactual_rerun.py` |
| SCRIPT_INDEX | 新增 2026-07-10 條目 |

## 凍結錨驗證(§0.1/§1,全部機械比對通過)

- 母集 A:凍結 SQL 逐字執行 = **71,207**;join 守恆(no-join == joined);6 cell 計數與預註冊 §1.1 表逐格一致(59,597/3,556/2,375/2,317/2,270/1,092)。
- 母集 B:v3 凍結分類器(git `8dfa1200a` 提取)在重建凍結 ledger 視圖上重放 → side_cell_count=76、diagnosis_counts 五格逐格吻合(28/1/**33**/1/13)、outcome_count=951,456 → 枚舉 **33** cells 寫入 artifact。
- 凍結 review artifact:`blocked_outcome_review_20260709T212701Z.json` sha256 = 預註冊錨 `299751f2…` 逐字節一致(latest 已被 hourly cron 覆蓋,見 deviation log)。
- Ledger:36 檔(35 輪轉段 + 主檔)逐檔 sha256 記入 artifact;主檔/晚段以 `generated_at_utc ≤ frozen` 過濾重建凍結視圖。

## 統計結果(§2-§8)

- **Family m=7**(A∪B 過 E1-E5 者),全為 `grid_trading|*|Buy@60m`(ATOM/ETC/FIL/LINK/NEAR/POL/UNI),n_eff 80-140、G 10-13 天、top-day ≤19%、觀測 100% ledger 源。7/7 VETO=`BLOCK_CONFIRMED_UNDER_EXPECTED_COST`;敏感性欄(全 n_dedup+day-cluster)p 同樣 ≈1,結論對非重疊化不敏感;tail(CVaR90)與 conservative_v1 對照欄全負,三軌同向。
- **σ_dedup = 67.3bps**(遠低於污染態假設 200bps)→ power 表更新:n_eff=30 可偵測效應 ≈30.5bps;50bps 需 n≈11、20bps 需 n≈70(門檻不動,§3.3)。
- **Headline sign-flip**:p_selection=1.0(observed_best=−23.3bps)→ 任何 headline 禁用 edge/cushion 語言。
- **Gate 雙向計價(§8.4)**:檢定 cells Σ n_eff×mean_net_E = **−33,608 bps·n**(負值 ⇒ 誤殺期望損失上界為 0,gate 為淨止損);`candidacy_flipped_by_cost_model_count=3`(bb_reversion|ATOMUSDT|Buy@60、flash_dip_buy|APTUSDT|Buy@60、ma_crossover|ETHUSDT|Sell@240——新成本模型下唯三分類翻轉,全部仍不過 eligibility/realism)。
- **DATA_INTEGRITY_SUSPECT_EXCLUDED = 24 rows**(§2.3 凍結規則:同 (cell,entry_minute,horizon) 複本 gross/net 超 1e-9 容差 → 排除出 family,無統計結論):含三個 A 重 cell(ma_crossover|ETHUSDT|Sell@60 n_eff=30、grid_trading|APTUSDT|Sell@60 n_eff=167、grid_trading|ETHUSDT|Sell@60 n_eff=125)。成因=秒級重發信號同分鐘不同秒的 entry 價差(數據生成機制,非儲存損壞)。此 24 cells 的 mean_net_E 全部為負(−3.8~−93.6),方向與 VETO 一致但按 §2.3 不得給結論。**建議 QC follow-up**:若要納入這批 cell,需發預註冊 v2 放寬 §2.3 為「同分鐘代表行容忍組內秒級價差」——本次嚴格按 v1 執行,未擅改。
- 其餘 47 rows = `SAMPLE_INSUFFICIENT_AFTER_DEDUP`(§3.4:無方向性結論;含預註冊已預判必然不足的 FILUSDT/ARBUSDT bb_reversion cells)。
- **Regime(§7)**:7 個 bull_heavy 全是單日 episode 的 bb_reversion/NEAR 形態(自動 regime-bet/learning-only 標籤);eligible cells 無一 single_regime_episode。

## NEAR 候選重判(charter 指定)

`ma_crossover|NEARUSDT|Buy`(family 外單列,`near_candidate_rejudgment` 節):@60m n_raw=5,058 → n_dedup=2 → **n_eff=1**、G=1、E1+E2+E3 全 fail → `SAMPLE_INSUFFICIENT_AFTER_DEDUP`;附加 `EXECUTION_REALISM_SUSPECT`(反事實 +130.5 vs realized −12.0)。v3 凍結診斷 `FALSE_NEGATIVE_CANDIDATE_AFTER_COST` 正式作廢。按 §3.4 亦**不得**反向宣稱「已證無 edge」——唯一合法行動 = 繼續累積 distinct-entry 樣本。

## 執行方式(charter 紀律遵循)

- 新代碼只在 Mac;rsync 至 `trade-core:~/tmp/r3_rerun_staging/`(lane 包 + pg_connect + v3 凍結檔),未碰 Linux repo;ledger 先快照入 staging(防 retention sweep 損凍結輸入)。
- PG 全程 SELECT-only(psycopg2 `set_session(readonly=True)` + 凍結 SQL);成本 artifact 由 staging 內新版 `slippage_quantile_artifact.py` 現產(global mean_abs=17.90bps、cvar90=126.68bps、n=2,531)。
- 跑完 staging 已刪除(`rm -rf ~/tmp/r3_rerun_staging` 確認 cleaned);產物 sha256 雙端比對一致後才清。

## Deviation log(全實作層,§10.3 記錄後續行;無判定式偏離)

1. 母集 B 重放 sign_flip_b=1(headline 欄不參與枚舉);2. 凍結輸入用 stamped 檔(latest 被 cron 覆蓋,sha256 錨吻合);3. realized EV 取 edge_estimates `raw_bps`(檔內無 realized_ev_bps 鍵);4. ledger=close 價 vs backfill=open 價雙源(§2.1 預期,obs_source 申報);5. funding interval 六 symbol 缺歷史 → 8h fallback(影響 ≤1bps)。

## 測試

`pytest helper_scripts/research/tests/` → **1,579 passed, 1 failed, 4 skipped**;唯一紅 = pre-existing decision_packet 牆鐘 time-bomb(前兩輪報告已記錄,`git status` 顯示該兩檔未觸)。新增 10 條測試全綠(CR1 手算對照/IID 收斂性/退化保護/偽複製稀釋/greedy/leak-free markout/censored/判定式真值表/凍結視圖歸屬)。

## 治理對照

- 不觸 max_retries/live_execution_allowed/execution_authority/system_mode;無 SQL migration;無新 singleton;無 runtime/order/Bybit 面;`order_authority=NOT_GRANTED`、`promotion_evidence=false`、`main_cost_gate_adjustment=NONE` 全 artifact 明示;Cost Gate 不降級(結論反而確認 gate 為淨止損)。
- 新注釋全中文;無硬編碼機器路徑(staging 路徑僅出現在 CLI 參數與本報告)。

## Operator / PM 下一步

1. E2 對抗審查(counterfactual_rerun.py + evidence_stats.py + 測試 + SCRIPT_INDEX)→ E4 回歸。
2. WP-A.7(TODO.md 記 F1 裁決 + NEAR dispatch 凍結解除條件 + 候選榜按本 artifact 重排)可據本 artifact 落筆——候選榜重排結果:**零候選**,全部回 continue_recording。
3. QC follow-up ticket(非本 scope):§2.3 複本一致性在「同分鐘秒級價差」數據生成機制下掃出 24 cells,是否發 prereg v2 調整取樣代表行語義由 QC 裁。

E1 IMPLEMENTATION DONE: 待 E2 審查(report path: docs/CCAgentWorkSpace/E1/workspace/reports/2026-07-10--r3-wpa4-counterfactual-rerun-verdict.md)
