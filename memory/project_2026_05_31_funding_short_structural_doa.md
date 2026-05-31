---
name: project_2026_05_31_funding_short_structural_doa
description: A1 funding_short_v2 結構性 DOA — Bybit 正側 funding 硬上限 +10.9% APR < 策略 30% 入場門檻；附 f7271405 隔壁修復三審核驗
metadata: 
  node_type: memory
  type: project
  originSessionId: 202b21e7-31be-4a10-b388-799ce5018582
---

核驗隔壁 session commit `f7271405`（restore A1 functional replay）+ 深挖 A1 (funding_short_v2) 無 alpha 真因。三層遞進結論。

**三個 program 問題：真且基本修對（但有殘留）**
- A1 stale stub：修前硬編 `basis_panel_infra_missing`；`V115__panel_basis_panel.sql` 建表後 stub 沒更新 → stale。修法把硬編換成 runtime `to_regclass('panel.basis_panel')` 動態探測（report.py:191）＝正確。
- A1 funding carry：新 SQL 把持倉窗 settlement 加進 net_bps（leak-free，as-of join `snapshot_ts ≤ signal_ts`），方法論對（funding 策略只看價格 PnL 會系統性低估）。但目前 exercise 零行（0 signal 過 gate）。
- A2 `%(name)s` 註釋：psycopg2 帶 params dict 時掃**含註釋**的整個 query 做 % 代換，假鍵 → KeyError，真 footgun。但**反應式非系統性**：同類 bug 之前炸過（8c report:1070 漏傳 notional_pct_floor）→ 應加 SQL 註釋 % 的 CI/lint 根治。
- params.rs/toml 純註釋改動、常量未動（沒造假 alpha）；compute_edge 14.67bps/8h≈160.6% APR break-even 已親驗（mod.rs:166 = 22/10000/1.5），Python runner 忠實鏡像。

**載重結論被修正（隔壁說「funding 太低、不是 basis pipeline 缺失」— 後半錯）**
- THIS probe #1 reject 是 `missing_basis_asof` **93%**（basis_panel 僅 1.8/14 天數據覆蓋 probe 窗）。隔壁混淆「表存在（stub 確 stale）」與「數據足夠」；basis 數據其實仍大量缺，as-of join 空。funding gate 只擋了走到那步的 7%（456 row，30% gate 與 160% compute_edge gate lockstep co-bind）。
- funding 數據**可信非假**：我方 WS panel（funding_curve.rs:80 純 ×10000 無 clamp）+ raw REST（rest_poller.rs 純轉發）+ Bybit 官方 API 三方一致；clamp-bug 假設被外部數據推翻。

**結構性根因（我獨立外部驗證 = 最大發現）**
- Bybit linear perp **正側 funding 硬上限 +0.01%/8h = +10.9% APR**，負側自由（不對稱）。自抓 Bybit funding/history API 200 結算/symbol（含 probe 窗）：BTC/SOL/DOGE/**1000PEPE/WIF** 全部 max ≤ +0.0001，1000 筆 **0 筆破 30% gate**；WIF 負側到 -0.00776（-85% APR）。MIT 同步驗 25-symbol universe 517k row 0 跨 gate。
- ∴ funding_short_v2 的 30% 入場 / 160% break-even 門檻**設在交易所結構上限之上 → 結構性 DOA，永遠不 fire**。非市場（不是「目前低」）非 pipeline，是 **QC 設計時一眼可查的可行性錯誤**（建策略前先查交易所 funding cap）。

**行動**：A1 funding_short NO-GO 是結構性永久；等 basis_panel 累積（≥14天 ~2026-06-13）或擴 universe **都無效**，停止打磨。BTC/ETH fence **不是**主因（我先前 push back 錯，已收回）。A2 (liquidation_cascade_fade) 同 probe avg_net -4.11bps 負、n_eff=9 也 non-viable。延續 [[project_2026_05_31_v58_alpha_pivot]] 的「A1 NO-GO」結論並給出結構性 why。
