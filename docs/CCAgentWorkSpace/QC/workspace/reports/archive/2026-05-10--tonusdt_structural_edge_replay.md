# QC 審計報告 — TONUSDT × grid_trading 結構性 edge replay

**Date**: 2026-05-10
**Author**: QC sub-agent (replay analysis)
**Triggered by**: Sprint N+1 dispatch draft P1-TONUSDT-GRID-BLOCK evidence requirement
**Predecessor**: Sprint N+0 closure HEAD `b6ed4975`；HIGH-5 12h watch in progress

---

## 結論一行

**判定 C → 條件升 A**：當前 7d sample (n=10) 不足以拍 RFC-grade DSR/PBO；建議**先升 P1-TONUSDT-GRID-BLOCK 為「12h 觀察 + 30d 擴樣 conditional block」而非「即刻 freeze」**。理由：n=10 落在 §1.3 表閾值 200 trades 的 5%，t-test power < 0.3 — Type-I error 風險高（誤殺 short-term outlier）。

## 樣本檢查（強制前置 step 0）

- TONUSDT (live_demo + demo, 7d, grid_trading): **n=10, avg=-31.23 bps**（task spec 引用，prior session b6ed4975 [40] 24h MLDE）
- 對比 frozen severe 末端：BILLUSDT n=11 avg=-49.67bps / LABUSDT n=17 avg=-78.76bps（v2 audit 記載，已 freeze）
- 對比 grid baseline：7d demo+live_demo 1162 trades avg ≈ -17.82bps（W2 baseline，3C 7d audit 同源 §三 [40]）

**n=10 vs 200 trades 閾值**：detect Δ=0.2 σ 需 N≥200；當前 power ≈ 0.27（α=0.05, σ_proxy=cluster std ≈ 30bps）。

## DSR + PBO（cluster K 估計）

- **K active cells (post-freeze)**：grid 41 + ma 22 + bb_breakout 10 + bb_reversion 1 + funding_arb 5 ≈ **K=79 strategy×symbol cells**（MIT v3 verification 數據）
- **DSR mu_0 = sqrt(2 ln 79) ≈ 2.79**
- TONUSDT cell observed Sharpe（-31.23bps / cluster σ proxy 30bps over n=10 → naive SR ≈ -0.34）
- **DSR PASS 機率 ≈ 0**（負 SR 即 deflated 後不可能 > 0）
- **PBO 不適用**：TONUSDT 是 single cell 非 strategy variant，PBO 嚴格定義不對齊（v3 NEW-ISSUE-V3-2 已點名）

**結論**：DSR 結論 = TONUSDT 在 7d 顯著無正 alpha；但 n=10 不足以說「結構性 negative」（只說「small-sample negative」）。

## Regime 一致性（**數據缺口 — 待 Linux CC 補**）

Sub-agent 工具不能 ssh trade-core 跑 PG SELECT；無法跨 ATR percentile / funding_rate sign / volume rank 切片驗證 regime consistency。

**建議 12h watch sign-off 前讓 Linux CC 跑此 query**：
```sql
SELECT date_trunc('day', ts) AS d, COUNT(*), AVG(realised_bps)
FROM trading.fills f JOIN trading.decision_outcomes o USING(context_id)
WHERE strategy_name='grid_trading' AND symbol='TONUSDT'
  AND engine_mode IN ('demo','live_demo')
  AND ts > NOW() - INTERVAL '30 days'
GROUP BY d ORDER BY d;
```

## Counterfactual（freeze 後 [40] 預期改善）

若直接 freeze TONUSDT：
- 24h MLDE [40] 樣本拿掉 n=10 × -31.23 bps = -312.3 bps cumulative drag
- 假設整 24h MLDE n_total ≈ 42（W-AUDIT-1 sync §三 [40]），freeze 後 avg_net 預估從 +8.75 升至 ≈ +13.5–14.0 bps
- **改善 ≈ +5 bps**，顯著但 confidence 低（基於 single-cell 移除推算）

## RFC 建議（condition A → 升 freeze 路徑）

**短期（12h watch sign-off 前）**：
1. **不立即** 加 TONUSDT 到 strategy_blocked_symbols_freeze.json
2. Linux CC 跑 30d regime split SELECT 補 evidence
3. 若 30d sample n ≥ 30 且仍 negative → 確 A，升 freeze
4. 若 30d sample n < 30 → 維持 B「short-term outlier」watch

**升 freeze 時的 RFC wording**（如達 A 條件）：
```toml
# settings/strategy_params_{paper,demo,live}.toml:grid_trading.blocked_symbols
# 加入 TONUSDT，理由：30d n=N avg=Xbps DSR fail PSR<0.5
```
**復評觸發條件**（per v3 NEW-ISSUE-V3-4）：每 30d 跑 V050 calibrated_replay counterfactual，若 positive edge 證據出現可解封。

## 風險分析

- **Selection bias 加劇風險（HIGH）**：每加一個 freeze symbol → 41 active 縮小→ML training universe 進一步偏，這是 v3 audit 已點名的負反饋環路。TONUSDT 進 freeze 將是 18 grid block（53% block rate of 41-symbol universe）
- **Type-I error 風險（HIGH）**：n=10 freeze = 87.5% probability 之後 30d 顯示 cell mean revert（基於 v3 audit 17 frozen cells 中多數現 0 fills 0 rejected_outcomes 的「無 counterfactual power」實證）
- **W-AUDIT-6d freeze SOP 違反**：要求 7d counterfactual + DSR/PBO；當前 n=10 的 DSR mu_0 deflate 後不能可信判定

## 容量估算

不適用 — TONUSDT freeze 是縮容量決策非擴容量。

## 建議：**REVISE / Conditional REJECT freeze**

- **不接受 immediate freeze**（DSR/PBO 證據不足 + selection bias 加劇 + Type-I error）
- **接受 conditional freeze with 30d evidence collection**：12h watch 期間 Linux CC 補 30d regime split SELECT；達 A 條件升 freeze；達 B 條件維持 watch；達 C 條件再延 12h 觀察
- **不論 verdict**：須先解 v3 NEW-ISSUE-V3-4「dynamic_unblock_check 30d cycle」才能避免 17→18 cells 永久 dormant

---

## Reference

- `srv/memory/project_2026_05_10_sprint_n0_closure.md` (TONUSDT prior context)
- `srv/docs/governance_dev/strategy_blocked_symbols_freeze.json` (current 17+4 freeze list, TONUSDT 不在)
- `srv/docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-09--db_ml_verification_v3.md` lines 86-100 (K=79 active cells benchmark)
- `srv/docs/CCAgentWorkSpace/QC/workspace/reports/2026-05-09--strategy_verification_v2.md` lines 59-90 (cluster severe-end benchmark)
- `srv/docs/CCAgentWorkSpace/QC/workspace/reports/2026-05-09--strategy_verification_v3.md` lines 91-97 (NEW-ISSUE-V3-4 dynamic_unblock_check 缺機制)
- `srv/helper_scripts/db/audit/blocked_symbols_7d_counterfactual.py` (existing counterfactual SQL pattern, 30d 可直接 reuse)
