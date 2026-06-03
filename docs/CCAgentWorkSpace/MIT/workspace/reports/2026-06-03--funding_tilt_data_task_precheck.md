# MIT Data-Task Pre-Check — funding-tilt carry diagnostic (DATA TASK #0 + #1)

**日期**：2026-06-03 | **作者**：MIT（分析） | **持久化**：PM（MIT Write 禁用，內容為 MIT 產出）
**範圍**：read-only Linux PG 分析，`research.alpha_funding_rates_history`
**Canonical run**：`18b3c2f8-6125-42a8-a42c-cfcc8aec9406`（唯一 `accepted` run；window 2024-06-03 → 2026-06-03；git_sha `44364d67`，git_dirty=f）
**對應協議**：`docs/CCAgentWorkSpace/QC/workspace/reports/2026-06-03--funding_tilt_carry_diagnostic_protocol.md`（§3.4 break-even + DATA TASKS）

## EARLY VERDICT：PROCEED-TO-HARNESS（conditional / narrow）— **不是** 早期 NO-GO-C

覆蓋乾淨（#0 PASS）。carry 量級（#1）**marginal-not-dead**——不觸發 QC ~45% prior 預期的 ~1 天 NO-GO-C。但 carry 結構性不對稱（≈70% 來自 short-top leg），集中在協議預登記的失敗模式（§4b short-squeeze-insurance-disguised-as-carry）。全 harness 正當性 = 裁決 §4.5 horizon-vs-cost 曲線 + §3.5/§4b carry-purity / 短腿擠壓問題——直奔第二可能失敗模式，非第一。**不建議當「likely GO」綠燈，建議當「60-65% likely NO-GO-C/squeeze、需 price-side（klines）才能定論」綠燈**（cheap DB pass 給不了 price side）。

---

## DATA TASK #0 — 覆蓋（PASS，無歧義）

| 檢查 | 結果 |
|---|---|
| Accepted runs | **恰 1**（`18b3c2f8…`）。run-versioning 陷阱（trend/funding_short_v2）避免——canonical 選擇 trivial。 |
| 總列/symbol | 46539 / 20，category=linear（符合協議 46539） |
| Per-symbol 覆蓋 | **18/20 = 精確 2190 列 / 730d = 3.0/day（8h，零 gap）**。TONUSDT 3701（4h+8h mix）。POLUSDT 3418 自 2024-09-05（POL ticker birth——其上市生命全覆蓋，非 gap）。 |
| 結算間距 | **只存在兩值**：480min（8h，87%）+ 240min（4h，13%）。零異常 gap——最乾淨指紋。均勻，**非近期密集/早期稀疏**。 |
| `coverage_status`（pages） | pass 1908 / partial 77 → **96.1% pass ≥ AEG-S0 §1.5 的 0.95 gate**。partial 為 per-symbol history 邊界。avg coverage_pct 1.01。 |
| `funding_interval_minutes` | **0/46539 populated（全 NULL）**——確認 `funding_oi_backfill.rs:611 = None`。Harness 須從 `funding_ts` 間距推 interval（§2.2）。 |

**→ 覆蓋不是 blocker。INCONCLUSIVE-on-coverage 排除。**

## DATA TASK #1a — Per-settlement |F| 量級
整體（bps/結算）：mean **0.906** / median **0.853** / p75 **1.000** / p90 **1.237** / p99 **5.249**。
- **33.4% 結算恰在 1bp IR floor；54.9% 低於 1bp**。分布重壓在利率 baseline。
- 72.4% funding 為正 → bull-dominated cohort（須標 `breadth-limited / bull-heavy / regime-bet`，CLAUDE Alpha Evidence Governance）。
- median |F|（0.853）**略低於** §3.4「≳1bp」線，但**非** QC NO-GO-C 描述的 ~0.01bp IR-floor-only 級。naive 1a 讀數「borderline」→ 1b 才決定性。

## DATA TASK #1b — Cross-sectional tilt spread（THE binding number）
Per-settlement（top-tertile mean − bottom-tertile mean），n_sym≥9，2190 結算：

| Metric | Value |
|---|---|
| **Median tilt spread** | **1.436 bps / 結算**（mean 1.505；p25 0.94 / p75 1.90 / p90 2.45） |
| 橫截面離散度 | median per-settle std 0.76 bps，IQR 0.80 bps，avg breadth 19.9——離散度存在，tertile long-short 可支撐 |
| Regime 穩定性 | prior-12mo 1.414 / recent-12mo 1.469——**跨兩半段穩定，非近期 artifact**（正面 robustness） |

**累積 gross carry（spread × n_settlements）vs RT 成本：**

| Horizon | Gross carry（兩腿） | Taker RT（2腿×21bps） | Maker RT（2腿×~14bps） |
|---|---|---|---|
| **7d（H_min，21結算）** | **30.15 bps** | 42 bps → **net −12** | 28 bps → **net +2** |
| 14d（42結算） | 60.31 bps | 42 bps → net +18 | 28 bps → net +32 |
| 21d（63結算） | 90.46 bps | 42 bps → net +48 | 28 bps → net +62 |

H_min=7d taker（worst-case）下 gross carry **不過** 2-leg RT。只在 ≥14d 持有 OR maker fill 才清。這正是 **§4.5 horizon-vs-cost-amortization 問題**——net 隨 horizon 變，正是全 harness 要畫的曲線。故非乾淨 1-day NO-GO-C。

## ★ 決定性 caveat — per-leg 拆解（真風險）
spread 拆腿（正確符號，funding_pnl 為正收割）：

| Tertile | mean F (bps) | median F | % time funding<0 | Per-settle collected |
|---|---|---|---|---|
| **T3 short-top leg** | +1.027 | +1.000 | **1.4%** | **+1.00 bps（reliable）** |
| T2 mid | +0.565 | +0.500 | 15.9% | （flat，不交易） |
| **T1 long-bottom leg** | −0.464 | −0.233 | **僅 59.5%** | **+0.47 bps（弱/噪音）** |

**~68% gross carry 來自 short-top leg。** long-bottom leg 幾乎不收（0.47bps）且 **40.5% 時間「bottom」tertile 其實是正 funding** → 長腿付費非收割。per-leg break-even（協議 §3.4 單腿框架）：短腿 21×1.0=21bps vs 21bps RT = **恰零 net**；長腿 21×0.47=9.9bps vs 21bps RT = **−11bps 淨損**。

這是協議預登記的 **§4b NO-GO 分支**：72.4%-正-funding bull 窗，cross-sectional tilt 退化成「做空最擁擠多單 alt」= **賣 short-squeeze 保險偽裝 carry**，負偏尾風險 DB pass 無法定價（需 klines `gross_price_bps`）。

## 與 QC prior 誠實對賬
QC 預判清牆 ~20-25%，最可能死於 **NO-GO-C carry 量級不足（~45%，median|F|≈IR floor）**。我的資料**部分證偽**量級不足機制：median spread 1.44 / median|F| 0.85 在 1bp baseline 附近，**非** ~0.01bp floor，carry 在 ≥14d/maker 清。但**強化**失敗模式 #3（short-squeeze insurance ~15% → 我會大幅上調）與 #2（horizon-decay-vs-amortization ~25% → 現在是 live 問題）。淨：kill 機率較 QC 分布略上調，從「量級」重分配到「短腿擠壓 + price-side horizon-decay」。

## 給 PM/QC 的建議
1. **PROCEED-TO-HARNESS，但 scoped**：harness 工作不再是「carry 存在嗎」（存在，marginal）——而是解 (a) §4.5 net-vs-horizon 曲線（taker AND maker），(b) §3.5 `carry_share` + SHORT-top leg 的 `gross_price_bps`（price 反向吃 carry 嗎=擠壓），(c) §4b regime split 確認有無 non-bull slice 給對稱（雙腿）spread。(b)/(c) 需 klines，cheap DB pass 給不了 → harness 正當，但**進場預期 NO-GO/regime-bet 非 GO**。
2. **預登記短腿不對稱**：harness 須分報 long-leg vs short-leg `funding_pnl`（§3.3 已要求）+ 按腿標 carry_share，否則 aggregate 正 net 會藏住「70% 單邊擠壓風險」。
3. **標 cohort** `breadth-limited / survivor-cohort / bull-heavy (72.4% +funding)`——任何正結果 = `regime-bet / learning-only`，除非 non-bull slice 獨立過。
4. **harness 須從間距推 interval**（funding_interval_minutes 100% NULL）；TONUSDT/POLUSDT 是 4h → 7d=42 結算，不可 hardcode 21。

全部數字來自 live Linux PG（canonical run `18b3c2f8…`），零文檔採信。
