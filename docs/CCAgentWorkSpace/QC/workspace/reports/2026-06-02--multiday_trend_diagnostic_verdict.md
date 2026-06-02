# 多日 Trend/Momentum 樞紐診斷 — 最終 VERDICT

**日期**：2026-06-02 | **結論**：**NO-GO-TREND（關閉多日 trend-following）** | **資料**：`market.klines` 1d，20 liquid perp，~730d（2024-06-02→2026-06-01，POLUSDT 635）
**審查鏈**：QC（設計協議）→ E1（實作 harness）→ E2+MIT+QC（核驗，抓 protocol 尺度錯置缺陷並退回）→ E1（修正改用正確尺度）→ E2+MIT+QC（背書）→ E1（tool-hardening）→ E2（commit-ready）。4-reviewer 對 OUTCOME 完全收斂。

---

## 結論

**多日 trend-following（TSMOM / vol-scaled / MA-cross / cross-sectional momentum）在這 20 個 liquid perp 上沒有可偵測的 tradeable edge。** 不接 longer-history backfill（救不了），不進 Phase 2（孤立顯著是雜訊取樣）。

## 證據（建立在正確尺度，非第一輪的瑕疵 daily-Ljung-Box）

1. **正確尺度 TSMOM（Newey-West HAC lag=k-1）不顯著且非相干**：t_HAC = {k20:0.40, k30:1.66, **k40:2.72（孤立）**, k60:0.83, **k90:−2.60（顯著反轉，mean −623bps）**}，hit rate 44-53%（≈coin-flip）。唯一過 |t|≥2 的是孤立 k40（勉強過 5-scale Bonferroni 2.576），但無相鄰支撐 + k90 反轉 → coherence gate 正確判 `coherent_positive_momentum=False`。MIT 獨立驗 bandwidth 敏感度（往更長帶寬幾乎不動）確認 HAC 把 naive t(9.65)→2.72 的 3.55x 壓縮合理；孤立尖峰+長尺度反轉是 N_eff=2.087 + 24 變體 multiple-testing 下的雜訊取樣指紋，非結構性 momentum。
2. **per-symbol 自相關 0/20**（universe-wide，非單 BTC）：median ρ₁=0.017，pooled `positive_autocorr=False`。趨勢延續的統計前提（正自相關）在橫截面普遍缺席。2 個 symbol LB 顯著但 ρ 為負（mean-reversion）。
3. **表面 0.66 Sharpe = short-side 厚尾/funding artifact，非 trend alpha**：最佳變體 B_k30 拆解——long net **7.5bps≈0** / short net **299bps**、win_rate **0.45（<coin-flip）**、look_ahead_inflation **−0.376**（naive gross < leak-free = 吃 mean-reversion/崩盤而非順勢）、per-regime **chop 0.81 > bull 0.46**（反 trend——真 trend 該在 bull 最強）。即「賺錢」全在做空厚尾 + 收 funding，是賣崩盤保險的 risk-of-ruin 結構（live 一次 short-squeeze 吐光，2022 LUNA/FTX 反彈為證），不是可持續方向 alpha。

## 誠實 power caveat（QC 終裁 NO-GO vs INCONCLUSIVE）

- effective N=237（15/24 變體過 Step 0 floor 60）→ 資料**足以跑檢定**，故非 INCONCLUSIVE-A（樣本不足出口）。daily backfill 已解掉 power 不足，binding gate 從樣本量轉為 TSMOM coherence。
- N_eff=2.087（PC1=68.67% BTC beta）power 確實受限，**但這是相關結構維度，longer-history backfill 救不了**：更多時間樣本給不了更多獨立 bet；更早 crypto 史（2021 頂/2022 LUNA-FTX cascade）只加 mean-reversion/崩盤非正 momentum；自相關在 universe-wide 已缺席，backfill 製造不出。
- 故「INCONCLUSIVE→backfill」是空頭支票（承諾 backfill 給答案，但有充分理由相信不會）。**NO-GO + 顯式 power caveat 比 INCONCLUSIVE + 假出口更誠實。** 這是 informative negative（測到 non-trend 正向指紋），非單純測不到。

## 方向建議（4-reviewer 收斂）

| 方向 | 裁決 | 理由 |
|---|---|---|
| 多日 trend-following | **關閉**（本診斷） | 不消耗 Phase 2 帶寬 |
| 多日 single-name mean-reversion | **不建議** | 對稱性謬誤——short-side 是崩盤/funding 結構非可交易 reversion；crypto long-memory + structural break 主導 |
| **listing fade** | **主路（next）** | 行為偏差（Alpha 來源 #1，listing pump-dump 是 graveyard 外已知 pattern）+ 事件驅動大 move（能翻成本牆兩條路之一）；Gate-B 隔離探針已部署（R-0 zero-leak、Linux smoke EXIT=0）；待 operator-timed 24h 真捕捉 |
| **funding+OI history backfill** | **P0 基礎** | 現 funding 覆蓋僅 ~58 天是所有多日持倉策略的硬約束（成本只能用代表性均值）；複用已部署的 daily-kline backfill pattern；cap 永遠查 `upperFundingRate` SSOT（禁從 history max 反推，funding_short_v2 教訓） |

## 方法論教訓（durable）

- **協議自身的 daily-Ljung-Box gate 是尺度錯置缺陷**（QC RETRACT）：daily-lag(1-10) 測「日報酬能否預測次日」，但 TSMOM(k=20-90) 賭「多日趨勢持續」——不同尺度（MOP 2012 TSMOM 日報酬同樣近白噪音）。會 FALSE-KILL 慢趨勢。**「trend 統計基礎」須在 horizon-matched 尺度直接測，不靠單序列短-lag。** 三審（E2+MIT 各自親跑真 PG）抓到並修正。
- **孤立顯著 cell 是 red flag 非 evidence**：5 個 k 裡冒 1 個 t=2.72 在 N_eff=2+24 變體下是預期雜訊；真 momentum 應是相鄰 k plateau（coherence gate）。
- **N_eff（獨立 bet）≠ effective N（trade 數）**：前者由相關結構決定、backfill 救不了；後者由樣本量決定。混淆兩者會誤把 NO-GO 當 INCONCLUSIVE。
- **任何正 Sharpe 先拆 regime×side**：看是不是 short-side funding-harvest / 崩盤保險偽裝成 alpha。

## 產物

- 可重用診斷 harness：`helper_scripts/research/multiday_trend_diagnostic/`（4 信號 leak-free+naive 雙軌、正確尺度 TSMOM HAC、coherence gate、per-symbol LB、含 funding 多日成本、36 測試）
- 協議 spec：`docs/CCAgentWorkSpace/QC/workspace/reports/2026-06-02--multiday_trend_diagnostic_protocol.md`
- real-PG artifact（ephemeral，本報告為 repo 永久存證）：`trade-core:/tmp/openclaw/multiday_trend_diagnostic_runs/`
