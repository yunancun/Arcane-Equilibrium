# MIT Wave 3 Data Audit — EDGE-P3 / EDGE-P1b / G2-06

**Date**: 2026-04-26
**Auditor**: MIT (ML & Database Auditor)
**Scope**: 3 Wave 3 questions per PM dispatch (`TODO.md` 275-313 + healthcheck [11] [14])
**Method**: Mac static read（`passive_wait_healthcheck.py` check 邏輯 + `V999__exit_features.sql` schema + `bb_breakout_threshold_sweep.py` audit fixes + `paper_state/dust_gate.rs` orphan_frozen 流程）
**Mac RCA 盲點**：rate per day 推估、orphan_frozen DB 實量、healthcheck 連 PASS streak 必由 operator Linux 端 cron 跑 6h 一次的歷史 audit/daily JSON 來驗證。本 report 只給判斷邏輯。

---

## 1. EDGE-P3 — 4 前置條件詳查 + 解鎖時程

### (a) clean bucket ≥200 rows（當前 150，ETA ~1d）

`check_counterfactual_clean_window_growth()` 計算邏輯（line 1283-1330）：
- 從 `audit/daily/YYYYMMDD.json` 取**最舊 + 最新-歷史**兩錨點
- `rate_per_day = (newest_n_rows - oldest_n_rows) / days_between` 動態算
- 無歷史點 fallback `rate_per_day = 30.0` static
- ETA = `(200 - n_rows) / rate_per_day`

「30/day」**並非依據實證統計**，是無歷史時的硬編碼 fallback。當前 healthcheck 訊息 `n_rows=150` + `ETA ~1d`，**反推實際使用的 rate 約 50/day**（≥30 fallback），代表已有 ≥2 個歷史 daily snapshot。

**穩定性風險**：
- counterfactual replay 是 **daily cron** 跑（非 tick-rate），增量取決於 close_fills 24h 流量；P0-9 後 demo PID 多次輪替不影響但 engine restart 期 fills 短暫斷流會壓 rate
- `post-P013-clean` window 是「P0-13 ATR fix 後新樣本」，每天等比累積，**不是 burst 而是線性 streaming**，1d 達 200 可信度高（前提：engine 不崩 + cron 不掛）
- **驗證需 operator 跑**：`ls -la $OPENCLAW_DATA_DIR/audit/daily/*.json | tail -5` 看歷史點是否單調遞增；若 JSON 跳到 200 後只有 1 個歷史點，rate 計算會回退到 fallback

### (b) per-strategy bootstrap 95% CI lo > 0

healthcheck **沒有直接驗** bootstrap CI lo，只驗 `grid_fired ≥ 50` AND `ma_fired ≥ 50` 個別計數（line 1263-1267）。bootstrap CI 是離線 FM/QC 跑 EDGE-DIAG-1 Phase 4 報告才出，不在 cron path。

**該過的策略**（從 `criteria_ok` evaluation 推回）：
- `grid_trading` cf_fired ≥50（樣本量）
- `ma_crossover` cf_fired ≥50
- 沒列 `bb_breakout` / `fast_track` / `phys_lock` / `orphan_*`（dormant 或 too sparse → 不單獨 gate）

**樣本量需求**：bootstrap CI lo>0 對 mean=+12 bps、std≈30 bps 的 noisy edge 需要 **n ≥ 80-100** 才穩定區隔 0；50 fires 是樣本量底線（CI 寬度容忍）；MIT 立場 **建議單策略 cf_fired ≥80**（不是 healthcheck 50）做 EDGE-P3 真正 deploy gate，否則 CI lo 抖動可能繞 gate。

### (c) orphan_frozen clean ≥20（當前 0，**真正瓶頸**）

讀 `dust_gate.rs:99-114` + `orphan_handler.rs:101`：
- `DUST_FROZEN_STRATEGY = "orphan_frozen"` 是**「retain in paper_state, NO close dispatched」**的 sink label
- 觸發條件：bybit_sync 倉位 + 不在 active_symbols + `est_notional < min_notional`
- **關鍵設計**：dust_frozen 倉位**永不被 close**（exchange min-notional 會擋），所以 `learning.exit_features` 永遠不會有 `owner_strategy="orphan_frozen"` 的 row

**根因**：orphan_frozen 是 quarantine label，定義上不會產生 exit row → counterfactual replay 看不到 → 永遠 0。**這條 gate (c) 邏輯錯誤**，等於把 EDGE-P3 卡死在永不滿足。

**FIX-PLAN 建議**（push back 到 PM）：
1. 把 (c) 改為「`orphan_adopted` clean ≥20」— `orphan_adopted` 是接管路徑會關倉
2. 或改「**non-dormant strategies** clean ≥20」並列舉 (grid/ma/bb/fast_track/phys_lock)
3. 或把 (c) 直接刪除，gate 改 (a)+(b)+(d) — 因為 orphan 是低優先 edge cohort

**P1-8 dust eviction**：本身運作正常（owner_attribution.rs:130 會把 dust 標 frozen），但 cohort 由 design 不進 exit pipeline；不需要再「進一步調 P1-8」，需要的是改 gate 條件。

### (d) healthcheck [11] 連 3d PASS

從**今天 2026-04-26 WARN** 起算，需 (a)+(b)+(c) 同時滿足才會 PASS。

| 場景 | (a) 達 200 | (b) grid+ma 各 ≥50 | (c) orphan≥20 | day 1 PASS | 連 3d PASS |
|---|---|---|---|---|---|
| 樂觀（修 c gate） | 4/27 (~ETA 1d) | ~4/28-29 | (c) 改後立達 | 4/28 | **4/30** |
| 中位（不修 c gate） | 4/27 | ~5/01 | 永不達 | — | **永不解鎖** |
| 悲觀（c 不修 + cron 偶斷 + grid_fired stagnate） | 4/29 | ~5/05 | — | — | **永不解鎖** |

**結論**：**EDGE-P3 解鎖最早 4/30（前提：(c) gate 修）；不修 → 永遠 WARN**。PM 必須先決策 (c) 條件正確性，否則 Wave 3 stalled。

---

## 2. EDGE-P1b — exit_features ≥1w + 7 維閾值 bind

### Timeline 校準

`check_exit_features_accumulation_rate()` 計算（line 1511-1524）：
- `this_week = COUNT(*) WHERE ts > now() - 7d`
- `last_week = COUNT(*) WHERE 14d < ts ≤ 7d`
- PASS：`this_week > 0 AND this_week ≥ last_week × 0.5`

當前 `this_week=447, last_week=0` → PASS，**但** writer 從 04-19 才 active。`last_week=0` 是因為 04-12~04-19 沒寫，不代表崩潰。**真正「滿一週的可信 weekly stat」要 last_week > 0**：04-26 起 last_week 滑進 04-19+ 區段 → **5/03 才有真正的 week-over-week trend**。

W19 = 04-19 起算 + 滿週 = 5/03 邏輯**成立**，TODO 寫對。

### 7 維閾值 bind

`V999__exit_features.sql:33-41` 定義 **7 dim** 為：
1. `est_net_bps`（JS edge + cost_gate 推算）
2. `peak_pnl_pct`
3. `atr_pct`
4. `giveback_atr_norm`
5. `time_since_peak_ms`
6. `price_roc_short`
7. `entry_age_secs`

「閾值 bind」**不是** JS estimator 的 grand_mean → cost_gate（那是 P1-14 的 separate bind，gated by `grand_mean > -50 + ≥2 strategies shrunk_bps>0`），而是 **Track P 物理層 ExitConfig 的 7 dim threshold（peak/giveback/ATR/time/ROC/age 觸發點）**。

當前 ExitConfig 預設值是工程常數（如 `giveback_atr_norm > 1.5` 觸發 phys_lock），**不來自資料分布**。EDGE-P1b 後的 bind 流程：
1. `learning.exit_features` 累積 ≥1000 rows（multi-strategy）
2. 對 `realized_net_bps > 0` cohort 算每維 distribution percentile（例如 75% giveback_atr_norm，25% time_since_peak_ms）
3. 用 percentile 寫回 `RiskConfig.exit.*` 各 threshold（IPC `patch_risk_config` 路徑）
4. 觀察 7d shadow → flip live

### Rolling vs Strict-week

5/03 滿週後：
- **Rolling 7d**（穩態 PASS sentinel）— 當前 [14] 已是這個語意，繼續用
- **Strict calendar week**（research-time bind）— 跑 percentile 計算時用「過去 7d 整個視窗」（不是 ISO week）以維持 sample stationarity；regime shift 應用 `purge + embargo`（per `time-series-cv-protocol`），不是按日曆切

**MIT 建議**：bind 動作用 rolling 14d 視窗 + 7d embargo + per-strategy stratification（避免 dominant strategy 主導 percentile）。Sample size 需求估：每策略 ≥200 rows × 5 strategy = 1000 rows，目前 447/週 ≈ 5/03 達 ~700-900 → **再延 1 週至 5/10 較穩**。

---

## 3. G2-06 — bb_breakout threshold recalibrate ML/data 視角

### (a) 30d sample size 是否足夠

從 `bb_breakout_threshold_sweep.py:663-666` defaults: `--days 14`, `--timeframe 1m`。**TODO 改 30d 是合理擴展**。

每 (symbol × bandwidth-grid combo) 的樣本量：
- 1m × 30d = 43,200 bars/symbol
- 25 symbols → 1.08M bar-observations
- bandwidth grid（squeeze_bw × expansion_bw × volume × donchian_mode）若 4×4×3×3 = 144 combo
- 每 combo 平均 ~7,500 bar/symbol — **充足**（per-combo Bonferroni-corrected t-test 可達 power 0.9）

但 **squeeze + breach 事件本身稀疏**：F1 confirmed bw=0.03 是 100% 觸發、bw=0.04 永不達 → 只有 bw 居中區間（如 0.025-0.035）才有非平凡事件量。**有效 sample**：估 30d × 25 symbol × 居中 bw 區間 ~= 200-1000 fires/combo（足夠 single-strategy sweep，不夠 cross-fold CV）。

### (b) 1m vs 5m timeframe 權衡

| 維度 | 1m | 5m |
|---|---|---|
| sample size | 30d × 1440 = 43,200 bars | 30d × 288 = 8,640 |
| BB squeeze noise floor | 高（micro-vol 干擾）| 低 |
| structure mismatch（F1）| 確認存在 | likely 修正（squeeze_bw 0.03 在 5m 機率 ~10-30% 而非 100%）|
| forward return horizon 對齊 | 需 5-15min 才有信號-to-noise 比 | 5 bars = 25min 自然對齊 |
| fee drag 影響 | 高（每分鐘 entry 機會多）| 低（事件稀疏）|

**MIT 結論**：**5m 更乾淨**。F1 1m bandwidth mis-scale 是**結構性問題**不是 calibration 不準 — squeeze_bw 設計時是 lower-frequency band（典型 BB squeeze 文獻 5m+ 起），1m 等於把 squeeze 條件下調到「永遠很窄」。**改 timeframe 比硬調 bw 乾淨**。

### (c) 之前 multi-role audit 修齊的 — 還需重做嗎

`bb_breakout_threshold_sweep.py:188-258` 已有：
- ✅ leak-free shift(1) Donchian（line 205-206 `donchian_upper_leakfree`）
- ✅ 同時 emit 兩組 stats（`donchian_breach` + `donchian_breach_leakfree`）對比
- ✅ Bonferroni / cluster-SE / df-aware t_crit 修齊（per CLAUDE.md §三 audit 條目）

**G2-06 不需要重做這些** — Phase 1 multi-role audit 修的是**信號級研究工具的方法論**，G2-06 是**換資料集 + 換 timeframe 重跑**。但 MIT push back 一條：
- **timeframe 切 1m → 5m 後，donchian_period (default 20 bars) 對應的 lookback window 從 20min → 100min 變動**，需驗證 squeeze persistence 假設仍成立；若不成立需 sweep period 一起（bb_breakout_threshold_sweep.py:74 註明「BB indicator period (20) and stddev (2) are fixed — sweeping those is a separate study」）

### (d) 切 5m 是否比硬調 bw threshold 更乾淨

**MIT 強烈 +1**：
- **F1 root cause 是 timeframe-bandwidth mis-design，不是 threshold mis-tune**
- 硬調 bw（如 squeeze_bw 0.015 + expansion_bw 0.025）等於**把 1m fit 在錯誤的 frequency** — 信號率達標但 forward-return signal-to-noise 差
- 5m 是**架構級正確解**，threshold 只需微調（已有 `BbBreakoutProfile::Aggressive` enum 落 TOML）

**operator 步驟建議**：
1. G2-06 (a) 跑 1m + 5m **雙跑** sweep（同 bw grid）→ 對比 forward-return mean / hit-rate
2. 若 5m 在同 bw 下 forward-return ≥ 1m 且 fire-rate 仍合理 → 直接切 5m（profile mismatch 結構解決）
3. 若 5m 也差 → bb_breakout 是 **alpha-failed**（disable 而非調整）

---

## MIT 對 PM 的建議

1. **EDGE-P3 (c) gate 邏輯錯誤** — orphan_frozen by design 永不出現在 exit pipeline；建議改 `orphan_adopted ≥20` 或刪掉 (c)。**不修 = Wave 3 永遠 stalled**。**最高優先**。
2. **EDGE-P3 解鎖最早日期 4/30**（修 (c) 後）;  **5/02 中位** ; **5/05 悲觀**（cron 偶斷 + grid_fired stagnate）。事件驅動，非 hard date。
3. **EDGE-P1b 5/03 滿週為 weekly stat 起點，bind 動作建議延至 5/10**（每策略 ≥200 rows 累積 + per-strategy stratification 防 dominant 策略主導 percentile）。
4. **G2-06 跑 1m + 5m 雙 timeframe sweep**（不只 1m 30d），如 5m forward-return ≥ 1m 直接切 timeframe；F1 是結構級 mis-design，硬調 bw 等於 fit 錯 frequency。
5. **G2-06 若 5m 也差 → bb_breakout disable**，不是再調參 — 該策略可能 alpha-failed in 1m crypto regime。
6. **per-strategy bootstrap CI lo>0 的 sample size**：MIT 立場 cf_fired ≥80（非 healthcheck 50）才穩定；EDGE-P3 (b) 條件實際比 healthcheck gate 嚴一檔，PM 須跟 QC/FM 對齊驗收門檻。

MIT AUDIT DONE: /Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/MIT/workspace/reports/2026-04-26--wave3_data_audit.md
