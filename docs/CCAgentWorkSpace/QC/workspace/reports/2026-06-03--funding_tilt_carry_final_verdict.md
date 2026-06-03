# QC 最終統計判定 — Funding-Tilt / 多日 Funding Carry 樞紐診斷

**日期**：2026-06-03 | **作者**：QC（判定） | **持久化**：PM（QC Write 禁用）
**判定**：**PROCEED（維持關閉 funding-tilt，回 listing fade 路①）**。E1 verdict **NO-GO-C 成立**，非 bug 假陰性、非過嚴門檻誤殺。
**審查鏈**：PM scope → E1 IMPL（`6aefa576`）→ E2 對抗碼審 → MIT leak/sample 審 → QC 最終判定 → PM JSON 原檔對賬收口。**四方一致。**
**run artifact**：`trade-core:/tmp/openclaw/funding_tilt_diagnostic_runs/real_20260603/diagnostic_report.{json,md}`（canonical run `18b3c2f8`）。

---

## 一句話
逃逸路②的 funding 維度**正當關閉**——carry 量級（best variant 5.4bps/trade）連自己 21bps 的交易成本都付不起（carry_cost_ratio 3.896），正向 net 是 short-leg 裸價格方向（down-market short-beta）偽裝的 carry（aggregate carry_share 僅 0.179），forward HAC t=1.64 不顯著；三重否決互相獨立佐證；**無殘留變體值得在關閉前再試**。

## 1. NO-GO-C = 三重獨立否決（PM JSON 原檔對賬 ✓）

| 否決 | 數值（raw JSON 親驗） | 含義 |
|---|---|---|
| **carry_cost_ratio** | best variant **3.896** ≥ 0.8（A_L3 更差到 13.88）| carry 5.4bps 付不起 21bps 成本（門檻 4.87×，非邊緣失格）|
| **forward HAC t** | **1.6393** < 2（naive 1.895，HAC<naive 有 bite）| funding-tiltscore 對未來報酬無顯著 cross-sectional 預測力 |
| **DSR(K=8)** | **0.0**（pass=False）+ bootstrap CI 下界<0 | deflate 後信號完全不 survive（地板值，非差一點）|

三道門檻**任一單獨都擋下**，三道一致 = 結論 robust。`net_turns_positive_with_horizon=True`（H14 net 微正）證實 binding 是 **cost-wall 腿**非攤薄失敗腿（MIT framing 校正：見 §3）。

## 2. ★ per-leg「directional 偽裝 carry」判定（本診斷最有價值發現，正確）

best variant（A_L21__flip_hold_min）：

| leg | gross_price | funding_pnl | net | carry_share |
|---|---|---|---|---|
| long-bottom（做多最負 funding）| **−63.4** | +0.88 | −83.5 | 1.0 |
| short-top（做空最正 funding）| **+88.6** | +8.66 | +76.3 | 0.089 |
| **aggregate** | +24.7 | +5.39 | **+9.12** | **0.179** |

- aggregate 正 net +9.12bps 中 carry 只佔 ~18%，~82% 是**裸價格方向**（短最擁擠 alt 在 down market 下跌的 down-beta）。
- **long-leg gross_price −63.4 = 協議 §4b squeeze/reversal 警告兌現**：做多「funding 最負」幣（常因正被拋售）= 接下跌的刀；funding_pnl 僅 +0.88（做多卻在付 funding，與 MIT pre-check「40.5% 時間長腿付費」一致）。
- **short-top net +76.3、carry_share 0.089 = 賣 short-squeeze 保險偽裝 carry**：平時收小額 funding 保費 + 賺下跌；一旦 squeeze（擁擠多頭幣猛拉）瞬間吐光。典型賣尾部保險損益（平時小賺、尾部巨虧）。

跨變體同型（A_L3：short gross_price +38.6 主導、long −9.47 弱、carry_share 0.074）→ 結論不依賴單一變體。

## 3. operator 核心問題 — N_eff 2.033 ≈ 2.087，QC 收回樂觀假設

- funding-tiltscore N_eff **2.033**（PC1 69.4%）vs price-return **2.087**（PC1 68.7%）（MIT 從 raw DB 獨立重算到小數，PM JSON 親驗）。
- crypto funding 橫截面相關性**和價格報酬一樣高**——BTC 主導時整個 universe funding 同步擺動，cross-sectional dispersion **沒提供額外獨立維度**。**funding-tilt 並不比 trend 更獨立**。
- 這摧毀了 funding-tilt 的核心立論（協議 §0.1「它是更獨立的命題」）。**QC 明確收回 pre-check 的樂觀假設。**
- **★ MIT framing 校正（重要）**：關掉這條路的 binding gate **不是 N_eff**（Step0 沒 fire，8/8 變體過 floor 60，max_eff_n=731.88），而是 **gate C 的 carry_cost_ratio 3.90 cost-wall + forward t=1.64 不顯著**。**N_eff=2.033 是佐證**（解釋為何不該對 cross-sectional funding 寄望更高獨立性），非斷頭台。

## 4. 反假陰性 — 五路變體全 Reject，無殘留值得追

| 變體 | 判定 | 理由 |
|---|---|---|
| volume-weighted（協議未測）| ❌ Reject | 不改 carry 5.4 vs 21bps 根本算術；需 carry 翻 4.9× 不可能 |
| 不同 L/tertile 切分 | ❌ Reject | 只減每腿樣本、惡化 N_eff；加變體只抬 K、進一步壓 DSR |
| ≥14d horizon（operator 攤薄論點）| ❌ Reject | §4.5 已掃描；學術紅旗 carry 隨 horizon 衰減 + 長持倉放大接刀風險 |
| maker fee 情境 | ❌ Reject | 加回 slippage 後 carry_cost_ratio 2.59 仍 >0.8；且不解 HAC 1.64/carry_share 0.179/N_eff 三問題 |

四個獨立失敗維度（carry 量級 / forward 不顯著 / directional 偽裝 / N_eff 不獨立）**沒有任何一個能靠變體調參修復**。

## 5. harness 方法學審計（QC）
- 黑名單全 clean（rule-based regime 禁 HMM + expanding/prior-365 leak-fix；無 GARCH/VPIN/獨立 Donchian；leak-free 雙軌）。
- HAC（Newey-West lag=overlap）/ DSR(K=8) / PSR(skew-kurt) / block bootstrap 公式逐行核對正確。
- **PBO insufficient 是正確 fallback**（K=8<10 candidate floor，協議 §4.2 預期，主防線回 walk-forward OOS；因 NO-GO-C 在更前 fail-fast，OOS 不必跑）。

## 6. 系統元發現收斂
這是 6 週以來**第 5 個結構性候選死於同一根因 = down-market beta 偽裝 edge**（funding_short_v2 DOA / multiday-trend NO-GO / blocked-signal grid_short / cascade-fade / 本 funding-tilt）。此 BTC regime 趨勢 beta 主導，**任何方向策略的短 bias 都被誤認為 alpha**。funding-tilt 只是換了 cross-sectional funding rank 包裝的同一陷阱。

## 7. 收尾
1. **形式收口已完成**：QC 原報告無 ssh 未讀 JSON 的缺口，已由 (a) E2 親讀 artifact+DB、(b) MIT 從 raw DB 獨立重算到小數、(c) PM JSON 原檔對賬 三方補上，全 ✓exact。
2. **harness 資產保留**（不刪）：與 trend harness 同骨架；若未來 V125 backfill 到 1095d + 出現 non-bull regime slice 可重跑對照（caveat：backfill 救 trade 數救不了 N_eff，期望仍 NO-GO）。**重跑前須先修 E2 的 3 LOW**（leak 邊界 `<`→`≤` / reason 字串 / docstring 符號）。
3. **下一步**：回 listing fade（路①，Gate-B 探針已部署，待 operator-timed 24h 真捕捉）；AEG-S2 證據自動化基建（regime/breadth/robustness）可並行起步（FND-2 builder IMPL 為前置）。
