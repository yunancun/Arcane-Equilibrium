# QC 盈利研判 Stage 2 — 全系統盈利面 + IBKR 研究 lane · 2026-07-09

**Agent**: QC（Quantitative Consultant，外部顧問）
**範圍**: srv/ 全系統盈利面（策略/gate/風控/fills/AI 成本/dormant/未開發 alpha）+ IBKR stock_etf_cash read-only lane（ADR-0048 邊界，僅研究價值層面）。
**邊界**: 全程 read-only；Linux 證據僅 `ssh trade-core` 唯讀命令；零修復/零 config/零 deploy/零 restart/零 auth 變更。
**基礎**: Stage 1 報告（MIT `2026-07-09--profit-evidence-readonly-probe.md`、AI-E `2026-07-09--ai_cost_roi_dormant_capability_audit.md`）已讀；本報告含 QC 獨立復核 + 增量取證。
**黑名單檢查**: 本報告所有提案不觸 HMM/GARCH/VPIN/獨立波動率均回/含 current-bar 的 rolling max（唯一正本 `math-model-audit` skill）。無需 RETRACT。

---

## 1. Executive Summary

系統 30d demo true net = **−406 USDT（gross −150.7、fees 255.4；fee 是 gross 虧損的 1.7×）**，全部策略 net 為負——不賺錢的根因仍是「1m 頻率 edge < 固定成本牆」，與 06-13 搜索空間結論一致。但本輪新增三個結構性事實改變了行動排序：
(a) **誤殺偵測 lane 本身雙重失效**（F1 pseudo-replication 已由我逐位復核 + conservative_v1 成本模型把期望成本高估 ~4×），目前系統**無法可信回答「gate 有沒有誤殺」**；33/76 side cells 落在「gross 正但成本墊不足」帶，是唯一數學上可能藏誤殺的母集。
(b) **Adverse selection 是 strategy-conditional 而非全域常數**：aggregate maker markout −7.57bps 被 flash_dip_buy（−12.68）/funding_arb（−13.48）拖垮；grid −2.45 / ma −1.34 / bb_reversion −2.37。maker-nogo 的 aggregate 結論對「執行成本削減」路徑（M12，被明確留為真 dormant）不構成封鎖。
(c) **bb_reversion 是唯一 gross 正 cell（+9.06bps）**，taker RT 成本 ~19.5bps vs maker RT ~8.7bps——差一個執行檔，非一個 alpha。
攻方向首位 = **horizon arbitrage（paradigm challenge）**：成本牆固定 per-RT，edge 隨 horizon 的 σ 放大；1m 不可跨、multi-day 可跨；in-house 1d klines 26 symbols × 2 年已在位，$0 可驗。

## 2. 理論基礎（為什麼現在不賺錢、錢可能在哪）

- **成本牆數學**：taker RT 實測 E[cost] ≈ 2×(fee 5.5bps + E[slip] ~6bps) ≈ 23bps；per-fill gross p50 = −1.17bps（MIT §A.3）。任何 1m 級信號要求 IC×σ(1m) > 23bps，σ(1m)≈5-10bps → 需 IC>2，不存在。此為範式約束，非參數問題。
- **Edge–horizon 標度**：E[edge] ≈ IC × σ(h)，σ(h) ∝ √h（近似）。σ(1d) ≈ 300-500bps（crypto majors）→ IC 0.03-0.05 即 9-25bps/day，5d 持有攤薄後成本 ≈ 4.6bps/day。同一資訊水平下，唯一可自由選擇的跨牆變數是 h。
- **自鎖迴路（epistemic deadlock）**：JS cells n=3-20、grand mean 負（−10.35）→ 正 raw cell（bb_reversion|ETH +3.39、|ARB +4.00，n=3）被 shrink 為負 → gate 擋 → 無新 fills → n 不長 → 永負。gate 在「其估計下」正確，但估計端被 gate 餓死。破鎖手段就是 profit-first bounded probe——而該 loop 執行腿三重失效（auth 過期/BBO stale/F1 無效）從未通電。

## 3. 數學模型 / 數字復算（QC 獨立驗證）

| 指標 | Stage 1 報告值 | QC 復算 | 差異 | 結論 |
|---|---|---|---|---|
| 30d demo fills/fee/gross | 1,011 / 254.68 / −148.61 | 同（重跑 SQL） | 0 | 驗證通過 |
| 30d live_demo | 44 / 0.71 / −2.11 | 同 | 0 | 驗證通過 |
| F1：NEAR 候選 5,058 outcomes | 2 distinct entry | **2,614×+70.28bps + 2,444×+59.32bps**（重跑 grep+uniq） | 0 | **CRITICAL 確認**：n_eff≈1-2，`one_sided_t_p=0.0` 與 `bh_fdr_pass` 全建立在 ×2529 偽複製上，統計無效 |
| Maker markout aggregate −7.57 | （MIT 全域值） | per-strategy：flash_dip −12.68(n=97)/funding_arb −13.48(n=37)/grid −2.45(n=356)/ma −1.34(n=73)/bb_rev −2.37(n=3) | 結構性新增 | aggregate 掩蓋 strategy-conditional 結構 |
| Taker slippage | mean −6.08 | p50 −0.02 / p25 −5.91 / p10 −37.79（n=462） | 重尾 | E[slip]≈6bps 但 tail 須另行以 CVaR 預算控制，不可混入 E[cost] |
| 「正 edge < threshold」母集 | 49,388（單一 reason 字串） | **71,207**（regex 全類）：ETH 63,006（edge 3.46/thr 9.49）、FIL 3,556（24.90/53.30）、APT 2,375（6.61/10.08）、ARB 2,270（21.77/53.30） | 母集更大且高度集中 4 symbols | 這些是 signal 級重複行，有效 cell 數 ~4-10 |

可重跑命令（示例）：
```
ssh trade-core "psql -h 127.0.0.1 -U trading_admin -d trading_ai -Atc \"SELECT strategy_name, liquidity_role, count(*), round((avg(fee_rate)*10000)::numeric,2), round(avg(slippage_bps)::numeric,2), round(avg(maker_markout_bps)::numeric,2) FROM trading.fills WHERE ts > now()-interval '30 days' AND engine_mode IN ('demo','live_demo') GROUP BY 1,2 ORDER BY 1,2\""
ssh trade-core "grep -h 'ma_crossover|NEARUSDT|Buy' ~/BybitOpenClaw/var/openclaw/cost_gate_learning_lane/probe_ledger.20260707T163027Z.jsonl ~/BybitOpenClaw/var/openclaw/cost_gate_learning_lane/probe_ledger.20260707T213755Z.jsonl | grep blocked_signal_outcome | jq -r '[.entry_ts_ms,.realized_net_bps]|@tsv' | sort | uniq -c"
ssh trade-core "jq '{diag:.diagnosis_counts, flipped:.candidacy_flipped_by_cost_model_count}' ~/BybitOpenClaw/var/openclaw/cost_gate_learning_lane/blocked_outcome_review_latest.json"
```

## 4. 成本分析（gate 雙向體檢核心）

**Cost gate 淨貢獻 =（避免虧損）−（誤殺正 edge）−（摩擦）**：
- 避免虧損：放行者（99.93% 拒絕率下仍成交的）30d realized net 全負 → gate 的第一項為正，方向無爭議。
- 誤殺正 edge：**當前不可信地量測**。兩個失真方向相反：F1 偽複製（膨脹誤殺敘事）vs conservative_v1 成本 92.3bps vs 實測 E[cost]≈23bps（壓低誤殺敘事，見 `cost_model_version_counts`: conservative_v1 718,765 / legacy_optimistic_v0 230,864）。33/76 cells 落 `GROSS_EDGE_POSITIVE_COST_CUSHION_INSUFFICIENT`、`candidacy_flipped_by_cost_model_count=3`——成本模型選擇已在翻轉候選資格。**在 O3 修復前，任何「gate 無誤殺」或「gate 大量誤殺」的結論都不成立。**
- 摩擦：soak isolation 415,651 拒/10d → realized_fill 標籤 7d 僅 14 行 → JS/ML 供血斷絕（資訊成本，非直接 PnL 成本）。
- conservative_v1 的方法論錯誤：把 p10 tail slippage（−37.79）當 E[slip] 用。正確 = E[cost] 用均值/中位（fee 5.5 + slip ~6/leg），tail 用 CVaR 預算單列。成本假設保守 ≠ 期望值×4。

**cost_edge_ratio 現況**：以 bb_reversion 計 gross 9.06 vs taker cost 19.5 → ratio 2.15（>0.8 關倉帶）；maker 化後 8.7/9.06 → 0.96，仍高於 0.5 目標——這說明 maker 化只把該 cell 推到 break-even 附近，價值是「零成本累積樣本」而非利潤引擎。

## 5. 回測驗證要求（各 opportunity 的 leak-free 路徑）

- **O1 horizon/cross-sectional**：1d klines（`market.klines` timeframe='1d'：19,751 行、26 symbols、2024-06-02→2026-07-08）；週度 rebalance cross-sectional rank（beta 中性 demeaned，承 06-03 鐵則）；全特徵 shift(1)；rolling 90/30 walk-forward；sweep 記 K → DSR/Bonferroni；block bootstrap CI；**bull-heavy 標註強制**（窗含 2024H2-2025 bull）。成本按 taker 23bps/RT 上界入模，不假設 maker。
- **O2 bb_reversion maker 化**：先 read-only 擴 markout 樣本（bb_reversion maker n=3 → 需 ≥30；34M L1 fill_sim 重放 bb_reversion 信號，touch-based 判 fill，承 2026-04-20 教訓禁 optimistic fill）；paper/demo fill_rate 比例 0.7-1.3 帶外禁餵 edge_estimates。
- **O3 反事實重跑**：dedup by (side_cell, entry_ts_ms) → effective-n；HAC/cluster-SE by day；成本改 E[cost] 版（slippage_quantile_artifact.py 已存在）；FDR q=0.1 重跑 76 cells。
- **O4 listing niche**：AEG Gate-B listing 探針（2026-06-02 部署）收的 L1 數據 → fill_sim 雙窗判準原樣複用，只換樣本母集；pre-register 判準防 garden-of-forking-paths。
- **O6 IBKR regime factor**：日級 SPY/QQQ/VIX PIT 特徵 shift(1)；標的 = crypto 策略虧損 episode 的反事實避免率；不進交易鏈，僅 regime gate 研究。

## 6. 風險分析

- **F1 修復前對 NEAR 候選 dispatch**：統計依據不存在（n_eff≈1-2 的單日 episode，NEAR +1.6%/1h pop = regime-bet）。若 bounded probe 執行，其結果既不能證實也不能證偽 64.98bps——樣本自相關 100%。建議 PM 依 MIT 建議先修 F1 再續 chain（QC 附議，本報告提供修復數學規格 §5-O3）。
- **O1 regime 風險**：momentum/cross-sectional 在 regime 切換時 crash（外部文獻同示警）；驗證必須含 2025 下行窗與 risk-managed 變體。
- **O2 機會成本**：PostOnly fill rate <60% 時 missed-trade 成本反超省費（skill 判準）；bb_reversion n=28/30d 本身樣本饑餓，任何結論 21d+200 trades 前皆為 Conditional。
- **soak isolation 拆除風險**：直接拆 = 恢復 net 負策略放血（30d −406 USDT 節奏）；正確路徑是 bounded probe 定向補標籤，不是開閘。

## 7. 容量估算

當前全部在 demo，live fills 30d = 0（MIT Gaps#6），無真金容量問題。O1 若成立，週度 rebalance × 26 liquid symbols 的容量遠高於 1m 策略（turnover 低 ~100×）；O2/O4 容量受 maker queue 限制，屬 micro-scale（與 3% risk/trade 及 MICRO-PROFIT-FIX-1 意圖相容）。容量不是現階段約束——樣本與證據才是。

## 8. 建議（PROCEED / REVISE / REJECT）

| 項 | 裁決 | 一句話 |
|---|---|---|
| profit-first loop NEAR 候選 dispatch | **REVISE（先修 F1）** | 翻案條件：outcome_review 按 entry window 去重後該 cell effective-n ≥30 且 FDR 仍過 → 恢復 dispatch 資格 |
| 反事實成本模型 conservative_v1 | **REVISE** | E[cost] 與 tail 分離；33 cell 母集重跑（O3） |
| bb_reversion maker 化 fill_sim 驗證 | **PROCEED（研究）** | M12 dormant 能力的第一個具體 cell；先擴 markout 樣本 |
| horizon arbitrage 日級 cross-sectional 研究 | **PROCEED（研究，paradigm challenge）** | $0 數據在位；bull-heavy 標註強制 |
| listing niche fill_sim | **PROCEED（研究）** | maker-nogo 明留的口子；判準複用 |
| funding regime 監測 cron | **PROCEED（監測項）** | A1 翻案條件自動化 |
| soak isolation | **維持 + 定向補標籤**（operator 決策） | 拆閘=放血；不拆=餓死學習；第三路=bounded probe 補標籤 |

**外部參考（WebSearch 2026-07-09）**：
- Cross-sectional momentum in crypto（liquid winners 扣費後存活）：starkiller.capital cross-sectional momentum；arxiv.org/pdf/1904.00890（Momentum and liquidity in cryptocurrencies）；springer FMPM 2025 momentum moments（crash 風險示警）。
- Crypto VRP（contango 期 IV 溢價 ~+15pts，regime 依賴）：insights.deribit.com Bitcoin options volatility regimes；arxiv.org/html/2410.15195（Risk Premia in the Bitcoin Market）。VRP 軸本輪未立項（Bybit options demo 可行性未查證，僅列為未來數據軸候選）。

**QC 取數缺口（自申報）**：(1) cost_gate threshold 公式的 edge 語義（JS realized_edge_bps 是否已含費）未溯源到代碼——若 edge 已 net 而 threshold 再加 fee/wr×1.3，即 06-14 PROFIT-1 雙重扣成本仍在，需 E1 核對 `cost_gate` 變體實作；(2) FIL/ARB thr=53.3bps 的 fee/wr 輸入未逐 cell 拆解；(3) bb_reversion maker markout n=3——本報告所有 maker 化推論皆以此為上限標注 INFERENCE。

QC AUDIT DONE: docs/CCAgentWorkSpace/QC/workspace/reports/2026-07-09--profit-diagnosis-stage2-qc.md
