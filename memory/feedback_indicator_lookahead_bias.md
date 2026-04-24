---
name: 滾動視窗 breach 信號的 look-ahead bias 檢查
description: rolling(N).max()/min() 含 current bar 時用作 breach 信號 → 必然選到 mean-reverting 局部峰，假負相關 artifact 不是真信號質量
type: feedback
originSessionId: dc1c922e-d7a7-48f1-a251-1b3d6ddb3049
---
**規則**：用「rolling-window max/min vs current price」作 breach 信號（如 Donchian breakout、N-bar high/low breakout、ATR/range envelope）時，**必須先檢查 rolling window 是否包含 current bar**。

**Why**：
- pandas `df['high'].rolling(N).max()` 預設**包含 current row**；`numpy.lib.stride_tricks` 等大部分 rolling impl 同樣。
- 若 dc_upper[i] = max(high[i-N+1..=i])，則 close[i] >= dc_upper[i] 只在 close == high == max 時 true → 等於選「current bar 是 N-bar 局部新高」。
- 局部新高 bars 由「mean reversion」特性，後續往往回調 → forward returns from breach bars 平均負。
- **這是 measurement / selection bias 不是 signal property**：任何不含 leak 的 breakout 信號定義（用 prior-bar-only `shift(1)`）下這個效應消失。
- Rust `openclaw_core::indicators::donchian` (`trend.rs:190`) 也用 `&high[n-period..n]` 含 current bar — production engine 真實如此使用，所以**這個 bias 是真實 production behavior**，但**不該作「Donchian 信號質量」的研究結論**。

**實證（2026-04-24 P1-11 sweep audit）**：
- 原 F3 結論「Donchian breach 反向關聯 fwd30 -3.20 顯著」(>99%)，看起來像強統計信號
- FA agent 獨立審核指出此 look-ahead bias
- leak-free shift(1) 重算：breach_diff_tstat 變 **-0.45**（接近 0，無效應）
- F3 撤回 — 原信號 100% 是 measurement artifact

**How to apply**：
1. **任何信號級研究**用 rolling-window breach signal 時，腳本內**並列計算兩版**：
   - engine-faithful (含 current bar) — 反映 production 實際行為
   - leak-free (`.shift(1)` 排除 current bar) — 反映 signal 的真信號質量
2. 報告**必須同時呈現兩組**結果；單獨 quote engine-faithful tstat 是 misleading
3. 若 leak-free 下 effect 消失 → 不是「Donchian 信號弱」，是「測量定義有 bias」；不能作為策略決策依據
4. 若 leak-free 下 effect 仍在 → 才是 robust signal property，可進一步討論 production 層次（要不要 fix engine 的 Donchian usage）
5. **生產 strategies 也應審視**：engine 是否有用「含 current bar rolling」作 entry filter / breakout confirmation？這些是 latent measurement-bias 來源，operator 觀察「breakout 信號表現差」時可能歸因於市場而非 measurement design

**檢查清單**（任何用 rolling 的 strategy/indicator）：
- [ ] `rolling(N).max()` / `rolling(N).min()` — 是否含 current bar？
- [ ] 信號定義 `current_value >= rolling_extreme` — 是否退化為「current 是 N-bar extreme」？
- [ ] forward return measurement — 是否從含 current bar 的 breach 計算？

**相關 memory**：
- `feedback_working_principles.md` 原則 3「對抗性驗證」 — 此 bias 正是該原則要 catch 的東西
- `feedback_multi_role_strategic_review.md` — FA 角色獨立審核發現此 bias
- `project_first_detection_deadlock_pattern.md` — 同 session 另一個 sweep audit 發現的 production bug
