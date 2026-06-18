# 尾部錯位 alpha 存活安全變體 — 量化（$0 唯讀 OFFLINE research，交 QC/MIT）

日期：2026-06-18 · 角色：E1 · 狀態：IMPL DONE，待 E2 審查
產物：`helper_scripts/research/tail_dislocation_meanrev/survival_safe.py`（import sibling `screen.py`，0 改）
artifact（Linux read-only）：`/tmp/openclaw/research/tail_dislocation_meanrev/survival_safe_20260617T224333Z.json`(+`.sha256`)

## 任務摘要

prior `screen.py` 證實本盈利弧的「第一個真 alpha」（maker 接刀 mean-rev：掛 BUY @prior_close*(1-K)，只在 flash-crash 成交，hold N 收盤平倉，beta-clean alpha 截距 +1.1~+11.3% t 5.9~12.6），但死於相關 falling-knife 尾部（all-in maxDD 0.77）。本批量化其**存活安全變體**：能否把相關尾部壓到可存活（maxDD<=~20-25%）同時保正 net 期望值（portfolio-construction / risk-management 問題，Principle 16）。

五加固全部實作並 Linux read-only 跑通（寫探針 fail-loud `ReadOnlySqlTransaction`；R-0 隔離紅線同 screen.py：0 寫 PG / 0 order / 0 auth/lease/risk / 0 production 改）。

## 修改清單

- 新增 `survival_safe.py`（~620 行，MODULE_NOTE 中文齊全）：import `screen` 的 read-only 連線/事件/統計 helper，新增 hard-stop 事件報酬、concurrency cap、fractional survival-first sizing 等值曲線、death-spiral 多 seed 壓力、day-clustered 顯著性、alpha-survives-stop 對比。
- `helper_scripts/SCRIPT_INDEX.md`：新增 survival_safe.py 條目。
- E1 memory.md：新增本批結論條目。

## 決定性結果（Linux 實證，2024-06..2026-06，26 sym）

### universe（鐵則更正）
清潔 1d-kline universe **結構性恰是 26 個存活兩年大-cap**（PG 直查：全 730 bar，POL 635 為較晚上市，min_low 全遠 > 0，`truly_dead` 候選 = 0）。**「broaden 到全集」在此資料上不可能** —— 全 1d-kline 集就是這 26，表內 0 真下市/歸零。screen.py 的 `>7d-gap` flag 標 20 個「possibly delisted」是 **backfill 批次結束日不同**（16 個 last_day=2026-06-01 vs global 2026-06-09）的 FALSE POSITIVE，非真死亡。intraday 153-symbol 集（129 個不在 1d）只 ~73 天（2026-04-05 起）且已知壞 → 無法擴日層 2yr 尾部。**survivor bias 不可從此資料移除 → 唯一誠實補償 = 合成 death-spiral 壓力疊加。**

### hard stop grid（K×N×S：%stopped / mean net taker）
- 設 stop → 大量觸發（K10/N3 S5% 61.8% stopped、S10% 40.4%、S15% 23.9%），且 stopped 中位數 = −S（多數在最低點被砍）。
- **stop 砍 mean net**：K10/N3 net_taker 從 unstopped +3.32% → S5% +0.86% / S8% +0.59% / S10% +0.51% / S15% +0.98%。
- 深-K 例外：K20/N3 unstopped +13.3%，S15% 仍 +7.3%（深-K 罕跌穿 15%）。

### alpha survives stop?（QC 要的 tradeoff）
**hard stop 砍掉 mean-rev alpha**：beta-clean OLS alpha 截距 —
- K10/N3：unstopped **+2.88%(t=7.3)** → S8% stopped **+0.51%(t=1.2，不顯著)**、S10% +0.39%(t=0.90)、S15% +0.62%(t=1.35)。
- K15/N3：unstopped +5.47%(t=7.6) → S8/S10% stopped **轉負**(−1.1%/−1.2%)、僅 S15% +0.92%(t=0.98)。
- K20/N3：unstopped +11.3%(t=11.3) → 僅 **S15% 留顯著 +4.9%(t=2.9)**。
機制：bounce 波動大，常先跌穿 stop 再反彈 → stop 在最低點實現損失 = **切贏家**。只有深-K(20%)+寬 stop(15%) 能讓 alpha 部分存活。

### concurrency cap（頭號存活 lever）
**cap 直接壓相關尾部**，K10/N3/S5%/r1% SIZED maxDD 隨 C 單調：
- C=unlimited(max conc=26) maxDD **0.6546** / annret 0.856 / CVaR_day −0.21
- C=5 maxDD **0.2081** / annret 0.554 / CVaR_day −0.050
- C=3 maxDD **0.1823** / annret 0.364 / CVaR_day −0.030
- C=1 maxDD **0.0867** / annret 0.163 / CVaR_day −0.010
這是 Principle-16 解：限制同日並發=限制「最壞崩盤日全部 symbol 同時 fill」的零分散。

### SIZED 組合（真 Principle-5 測試）
fractional survival-first sizing（stop-anchored：risk_unit=S，lever=r/S；無 stop 用 max(0.20,worst) 隱含停損）重建等值曲線 → maxDD/CVaR/Sharpe/Sortino/annret。prior all-in 0.77 確被取代：多數帶 cap 配置 SIZED maxDD 落 0.09~0.25。

### death-spiral 壓力（多 seed=64，per-entry 條件死亡率）
- gap-through honest：死亡事件 50% 跳空穿 stop 實現 −95%（hard stop 只部分擋）。
- **反直覺但正確**：stop-anchored sizing 使**有 stop 配置在 death-spiral 下更脆**（risk_unit=S 小→lever 大→gap-through 時損失被放大；stop 雙重反效果）。
  - rep_stopped K10/N3/S10%/C3/r2：cond-death 0.5% maxDD p95 已 0.44（破門）。
  - rep_unstopped K10/N3/C3/r2：cond-death 0.5% maxDD p95 0.144（存活）、2% p95 0.133（存活）、5% 才破門。
- cond-death **2%/entry 起多數配置 maxDD p95 破 25%**（best/unlimited-conc 配置在 2% 即 p95 0.262）。

### day-clustered 顯著性（MIT flag = KILL）
best config(K10/N2)：per-trade naive t **7.684**，但以 119 distinct crash episode 為有效 N（within-day 等權聚合後 block-bootstrap）→ day-clustered boot_t **1.43(block=1) / 1.36(block=5)，95%CI [−0.004,+0.027] 含 0**。**iid-OLS 高估 ~5x；誠實聚類下 per-trade edge 不顯著。** 有效 N 是 tens（crash 日）非 thousands（trade）。

### best survival-safe config
optimizer（最大化 annret s.t. 正 EV ∧ maxDD<=0.25）選 **K10/N2/S=None/C=unlimited/r3%**（maxDD 0.215、annret 2.33、Sharpe 2.05、Sortino 5.72、mean net +2.59%）—— 但 (i) C=unlimited(conc=26) 未壓相關尾部、(ii) day-clustered 不顯著。有 stop 的 survivable+EV 配置存在但低 annret（~15-65%/yr、Sharpe ~1.0-1.2，例 K10/N2/S5%/C5/r1% maxDD 0.198 annret 0.65 Sharpe 1.19）。

## 治理對照

- Root Principle 5（survival>profit）：本批正是其量化測試；concurrency cap 能達 survivable maxDD。
- Principle 16（portfolio-level risk）：concurrency cap + fractional sizing 是核心 lever，實證有效。
- Alpha Evidence Governance：math-primary，誠實標 survivor bias + 合成壓力 ESTIMATE + day-clustered。
- R-0 隔離：純讀（fail-loud 寫探針驗證）、0 production 改、死亡注入獨立 RNG 不污染實證。

## 不確定之處 / caveat

- death-spiral cond-death rate 是 ESTIMATE（無清潔資料佐證，industry ~10%/yr 集體下市為大盤值，深-K 條件率取 0.5~10% 敏感度）。
- gap-through-frac=0.5、death-terminal=−95% 為假設參數（敏感度未全掃）。
- sizing 模型 stop-anchored（tight stop→大 position）是一種慣例；若改用固定 notional sizing，stop 的 death-spiral 放大效應會減弱（未掃此替代 sizing）。
- funding 僅 ~2 個月覆蓋（多數窗回 0），略偏 conservative-favorable，已標。
- 最終 GO/NO-GO verdict 屬 QC/MIT。

## Operator / 下一步

1. E2 審查本 IMPL（read-only research，無 production 改）。
2. QC/MIT 裁 verdict：concurrency cap 壓尾部有效，但 (a) hard stop 砍 alpha、(b) day-clustered 顯著性蒸發、(c) death-spiral 多配置破門 → 傾向 **LEANS_GUARDRAILS_EAT_ALPHA**。
3. 若 QC 要續探：替代 sizing（固定 notional 而非 stop-anchored）+ 只用 concurrency cap 無 hard stop 的配置，可能是唯一存活路徑，但須先解 day-clustered 不顯著（有效樣本太少）。
