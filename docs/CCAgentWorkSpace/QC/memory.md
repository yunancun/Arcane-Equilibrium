# QC — Quantitative Consultant 工作記憶

## Memory Usage Contract (2026-05-16)

- 本文件保存歷史教訓與角色偏好，不是 active state、TODO 或 runtime ledger。
- 若舊條目與 `TODO.md`、`README.md`、`CLAUDE.md`、`.codex/MEMORY.md`、`docs/agents/context-loading.md`、代碼或 runtime 證據衝突，信任較新的有證據來源並顯式說明衝突。
- 不要靜默刪除舊條目；只追加可復用的 durable lesson。長報告放 `workspace/reports/`，active 進度放 `TODO.md`。

> 初始化日期：2026-04-02
> 本文件隨每次任務完成後更新，記錄關鍵發現、決策依據、需記住的教訓。

---

## 當前系統策略狀態（首次評估前快照）

### 已實現策略（5 個）
| 策略 | 類型 | 數學基礎 | QC 初步印象 |
|------|------|---------|------------|
| MA_Crossover | 趨勢跟蹤 | EMA(12)×EMA(26) + MACD | 標準技術指標，無獨特 edge |
| BB_Reversion | 均值回歸 | %B < 0.1 + RSI 超賣 | 有回歸邏輯但缺乏統計檢驗（half-life？協整？） |
| BB_Breakout | 突破 | 布林帶擠壓→擴張 | 波動率 regime 切換信號，需驗證假突破率 |
| FundingRateArb | 套利 | 永續-現貨基差 | 結構性 edge 最清晰，但需精算成本 |
| GridTrading | 網格 | 等距掛單 | 本質是做空波動率，趨勢市場風險極大 |

### FA 審計已指出的關鍵問題
- 「策略层标准 RSI/MACD/MA，无可证明的 alpha」
- 策略選擇完成度僅 40%
- 無 AI、無回測驗證、無動態倉位（部分已改善）

### 系統基礎設施（與 QC 相關）
- **BacktestEngine**：已建好（純函數指標 + KlineAdapter），但缺乏 walk-forward 和過擬合檢測
- **EvolutionEngine**：網格搜索（max 50 組合），無貝葉斯優化
- **TruthSourceRegistry**：AI confidence 上限 0.85，TTL by source
- **RiskManager**：P0/P1/P2 三層規則型，無統計風控（VaR/CVaR）
- **H0 Gate**：<1ms 確定性門控（freshness/health/eligibility/risk/cooldown）

### 風控參數
- risk_per_trade_pct = 3%（每筆最大虧損佔總額）
- max_symbols = 25（最多同時部署 25 個幣種）
- max_single_position_pct = 15%
- max_leverage: linear=10.0, spot=1.0, inverse=50.0

---

## 待辦評估清單（尚未執行，按優先級排序）

1. **[ ] 五策略 Edge 審計** — 逐一評估每個策略是否存在可論證的 alpha
2. **[ ] FundingRateArb 精算** — 這是最可能有結構性 edge 的策略，需要精確成本建模
3. **[ ] 回測方法論設計** — 為 BacktestEngine 補充 walk-forward + 過擬合檢測框架
4. **[ ] 組合風險模型提案** — 從規則型 → 統計型風控的路線圖
5. **[ ] 新策略方向研究** — 基於 crypto 市場結構性特徵的 alpha 來源識別

---

## 關鍵教訓（任務完成後追加）

### 2026-04-24：策略・風控・數學全面 audit
- **ATR P0-13 修復確認有效**：`atr(high, low, close, 14)` 用 Kahan summation + Wilder's smoothing 實作正確，且 `tick_pipeline/pipeline_helpers.rs::build_exit_feature_row` + `step_6_risk_checks.rs` 都已從 `kline_manager.get_ohlcv("1m", 20)` + `atr(_, _, _, 14)` 取 atr_pct（~0.05-0.5% scale），舊 per-tick `compute_atr_pct` deprecated。phys_lock Gate 3 peak/ATR 閾值在新 scale 下健康運作。
- **Donchian leak-free bias 還沒修 runtime**：CLAUDE.md F3 retract 已記述 measurement bias 在 leak-free `shift(1)` 下消失，但 `openclaw_core/src/indicators/trend.rs::donchian` 視窗 `&high[n-period..n]` 仍含 current bar，`bb_breakout/mod.rs:532` Hard mode 仍做 current-bar-inclusive breach 判定。P1-11 Phase 2 backlog 需修 `&high[n-period-1..n-1]`（或加 shift 參數）。
- **v2 `physical_micro_profit_lock_v2` 25 測試 + 設計文檔對齊**：Gate 1 Hold（非 Lock）、Non-linear giveback fn NaN/Inf 輸入 clamp 到 0、volatility normalisation 經 peak_atr_norm 雙路驗證。設計 + 實作雙重嚴謹，無 finding。
- **Kelly tier 邊界 50 / 200 trades 寫死不在 config**：`ml/kelly_sizer.rs:153-159` 分母 `8/6/4` 全 hardcoded；operator 前置 memory「200+ 筆同 regime」意圖 — 要 regime shift 重置 sample timer 沒 knob。
- **Guardian 裁決數學全硬編碼**：`risk_score` 增量 `0.4/0.3/0.4/0.15/0.35` + verdict threshold `0.3` + `leverage_ratio > 2.0` 寫死；與 E-Merge-4「GuardianConfig = RiskConfig 派生視圖」精神對立，operator 無 IPC/TOML 調裁決敏感度路徑。
- **grid_trading OU σ 估計有偏**：`grid_helpers.rs:128 sigma = sqrt(Σ Δx²/n)` 是 raw second moment，非 residual std；weak drift 期 mean_dx≠0 會高估 σ → ou_step 偏大。對 `b >= 0` fallback 路徑無影響（擋趨勢期），但 ranging 期 σ 高估導致 levels 過鬆、fewer fills。
- **cost_gate safety margin 30%（`fee_bps/wr*1.3`）寫死**：三個 cost_gate 變體（paper/moderate/live）都用同一 literal `1.3`，EDGE-P2-3 PostOnly 降 fee 後此 margin 是否過嚴需重驗。
- **SLIPPAGE_TIERS 整張表 const**：`intent_processor/mod.rs:229-235` 五層硬編碼，IPC 不可改；altseason vs bear 流動性差異需 config table。
- **FastTrack 閾值 15% / 5% / 3σ 寫死，僅 90% margin 合法寫死（Bybit MMR 物理常數）**：fast_track.rs:64 comment 正確文件化為何 90% 不可 auto-scale；但 74/89 的 15% 閃崩 + 5%+3σ 是風控參數不是物理常數，應 config 化。
- **Bb_breakout ctor vs params.default `cooldown_ms` 分歧（600_000 vs 300_000）**：潛在 BUG candidate —— 取決於 factory 是否在 cold-boot 跑 `update_params(Default::default())`，現場生效值需驗證。
- **ewma_vol `(w[1]/w[0]).ln()` 無 w[0]>0 guard**：與 hurst() 的 filter 不一致，零成本修補。

### 2026-04-20：EDGE-P2-3 Phase 1B — maker timeout & paper fill sim
- **Timeout 應 < cooldown，不是 ≥ cooldown。** grid entry 信號 half-life = 秒級（瞬時價格穿越，非 regime 信號）。timeout 1.5× 的提議錯在方向：舊未成交單會與下一個 cooldown 週期的新 tick 評估重疊，造成 stale order 與 fresh intent 雙重 exposure。正確 = 0.5–0.75× cooldown。
- **Timeout 要 scale with A3 effective cooldown，不是 base。** 趨勢越強 → maker 單在 1 bps offset 上越難 fill（單邊行情很少回探），同比例拉長 timeout 給 resting order 一個 fill 窗口才合理。推薦公式 `min(0.75 × effective_cooldown, 300_000)`。
- **Maker passive order = 賣出一個看跌期權。** 思考 timeout 不該問「信號還有效嗎」（45s 後幾乎都無效了），要問「order 還在 book 上提供選擇性嗎」。附帶指標 `(fill × rebate) - (cancel × adverse_move × size)` 為負 → timeout 太長或 offset 太窄。
- **Paper Limit fill 必須 touch-based，不是 optimistic。** optimistic fill 高估 edge 5-8 bps/RT（maker rebate 全吃 + 零 adverse selection），會再次污染 edge_estimates，重演 `project_edge_data_isolation.md` 的墮落循環。
- **Paper→demo 一致性必須 day-1 catch 4 項 bias：** (i) queue position 折扣（tick == limit 僅 50% fill，tick 真實穿越 100% fill）；(ii) partial fill 不模擬但 schema 預留 `filled_qty`；(iii) funding 跨越結算邊界即使未 fill 也要計 funding drag（grid 大量 resting 放大此 bias）；(iv) 記 adverse selection marker `mid@submit` vs `mid@fill`。
- **Paper fill_rate / demo fill_rate 比例 >1.3 或 <0.7 → paper 微結構偏離真實**，禁止餵 edge_estimates（原則重申）。

### 2026-04-02：自適應參數審查
- **20 筆交易的統計量什麼都說明不了。** 任何基於歷史交易的參數優化需要 200+ 筆同 regime 數據。Deflated Sharpe 修正後觀察到的 SR 要扣掉 ~0.9。
- **MA Crossover 的 Kelly fraction 為負 (f* = -0.014)。** 數學上建議不交易。根本問題不在參數，在策略本身無 edge。
- **確定性適應 vs 統計適應是完全不同的東西。** 前者（ATR 縮放、成本門檻）可以立即做；後者（歷史表現 → 參數調整）需要極其謹慎，數據不足時必須禁用。
- **追蹤止損存在成本陷阱：** 若 trail_activation - trail_distance < round_trip_cost，追蹤止損鎖定的利潤 < 手續費，實質上每次觸發都虧錢。必須加約束。
- **FundingRateArb 是 5 個策略中唯一有結構性 edge 的。** 應優先精算其成本模型。

---

## 報告索引

| 日期 | 報告 | 結論 |
|------|------|------|
| 2026-04-02 | [自適應參數架構審查](workspace/reports/2026-04-02--adaptive_params_architecture_review.md) | PROCEED WITH REVISIONS — 確定性適應立即做，統計適應暫緩，核心問題是策略無 edge |
| 2026-04-03 | [外部改善報告數學驗證](workspace/reports/2026-04-03--improvement_report_math_validation.md) | 6/6 兼容，0 衝突，3 採用 / 2 疊加 / 1 暫緩 |
| 2026-04-20 | [EDGE-P2-3 Phase 1B timeout & paper sim](workspace/reports/2026-04-20--edge_p2_3_phase1b_timeout_and_paper_sim.md) | timeout = 0.75× effective_cooldown (base 45s / cap 300s)；paper = (a) touch-based + 4 項 bias 保護 |
| 2026-04-24 | [策略・風控・數學全面 audit](workspace/reports/2026-04-24--strategy_risk_math_audit.md) | 16 findings（1 HIGH leak-free donchian, 5 HIGH 硬編碼 fast_track/guardian/cost_gate/slippage/kelly, 11 MEDIUM/LOW），P0 修補 = donchian shift(1) + StopConfig-RiskConfig drift 文件化；P1 = cost_gate 1.3 safety margin / fast_track thresholds / Guardian scoring weights config 化 / Grid OU σ residual-based |

### 2026-04-24：TODO.md 全面審計 — Edge 危機診斷 + 統計方法驗證

**審計報告位置**：`workspace/reports/2026-04-24--4.24TodoAudit.md` (435 行)

**主要發現**（分層）：

1. **數據不一致 — edge_estimates.json 陳舊 4 日**
   - TODO 聲稱 §P0-14「162/162 cells」，實況 n_cells=1 (grid_trading::ORDIUSDT only)
   - mtime 2026-04-20 23:50，當前 2026-04-24 02:06，未更新 4 日
   - Proxy cell 注入邏輯 (james_stein_estimator.py:490-496) 存在但 JSON 缺失代理
   - 可能根因：edge_estimator_scheduler.py cron 未跑，或 JSON 是舊版本未被讀取

2. **grand_mean_bps = -45.7275 無統計意義（n=1 樣本）**
   - James-Stein 公式在 p < 3 時未定義 (正確) ，但代碼未標記 `is_valid=false`
   - 單一 cell 的 grand_mean 等於該 cell 的 raw 值，無「跨域平均」意義
   - QC 建議：當 n_cells < 3 時，grand_mean 改設 NaN 並加 `_meta.is_valid = false`

3. **策略層 edge 結構診斷（可信）**
   - **Grid Trading**：fee drag 佔 74% 虧損 (~3.5 bps/RT)；PostOnly 改革預期可降 50% (→ 1.75 bps/RT)
   - **MA Crossover**：R:R 不對稱（avg_win=1.2 bps vs avg_loss=4.7 bps，不匹配）; win_rate 64% 折算為有效 37.8% 
     - TODO 數字需驗證：淨 -31.3 bps/RT，毛虧損推測 -27.8 bps 無法對齊上述 W/L
     - 建議查 SQL：SELECT ... WHERE direction=1/−1 驗證平均贏/虧計算
   - **FundingArb**：邏輯正確 (永續-現貨套利) 但成本未精算，樣本量太低 (n=77 fills)
   - **BB Reversion/Breakout**：無 edge 數據，信號量過低或純技術指標無 alpha

4. **統計方法正確性評分 8/10**
   - ✅ James-Stein estimator 公式無誤；per-parameter 多維收縮 (win_rate/avg_win/avg_loss) 合理
   - ✅ BB breakout sweep 用 ddof=1 (Bessel correction) + df-aware t-critical table，防小樣本膨脹
   - ✅ Donchian leak-free shift(1) 驗證了測量偏 (F3)，雙軌計算設計優雅
   - ⚠️ 缺 Bonferroni 修正在代碼層（但代碼註明在報告層應用），OK
   - 🟡 樣本量不足根本問題：edge cells 平均 n=8.9/135 (grid 1200 RT / 135 cells)，遠低於 30 基準

5. **P0-13 ATR 修復驗證（無法完全驗證，缺 Rust 源碼）**
   - CLAUDE.md 聲稱 Wilder's ATR (α=1/14)；TODO 稱 atr_pct 0.05-0.5% scale 驗證過
   - 無 Rust 代碼可讀，建議：測試 10 根 K 線 ATR vs pandas_ta，差異 > 3% 需 hotfix

**關鍵教訓（須記住）**：
- **Grand mean 統計有效性門檻**：p ≥ 3 個 cells 才能信任 JS 收縮目標，否則回 NaN
- **Edge estimate 樣本量門檻**：n ≥ 30 per cell (= ~4050 total RT for 135 cells) 才可 bind cost_gate；目前 8.9/cell 是噪音主導
- **策略層 alpha 缺失是根本問題**：4/5 策略無可解釋的邏輯，PostOnly fee 改革 (grid) 與 R:R 調優 (ma) 可救一部分，但需新策略研究
- **Win rate 折扣**：勝率本身不等於 PnL 正，需同時看 win_bps / loss_bps 幅度；MA 64% 勝率折算為實質 37.8% 有效勝率示例
- **Paper → Demo 一致性**：紙盤樂觀偏誤 (optimistic fill, 零 adverse selection) 污染過 edge_estimates；監控 paper/demo fill_rate ratio，超過 ±30% 應警告

**下一審查點**：
- ≥ 5 月 1 日 （EDGE-DIAG-1 Phase 3 passive-wait 至 clean n≥200）
- 或 ≥ 5 月 7 日 (21d demo 時鐘解鎖，P0-3 Phase 5 edge 重評)

## 2026-06-10 — L2 P3b B1 wiring sign-off = SANE（兩段式：BLOCKED-HANDOFF → 預註冊帶機械裁決）

- **流程教訓**：QC 無 Bash——PM dispatch 假設可 ssh 跑 runtime 與工具授權衝突。正解 = 我出**預註冊驗收帶**（解析式預期 + FATAL 指紋 + 帶界），E4 執行位代跑，我按帶機械裁決（數分鐘）。此模式可複用：QC 的 runtime 取數一律 handoff，預註冊防 post-hoc 合理化。
- **裁決**：B1 wiring（load_factor_bundle→reindex→beta_neutral_check）SANE——13 判準全落帶、零 FATAL；clone witness β_btc=0.99984（共享 int-bar-index 對齊的銳利見證，位置性錯位會使其崩向 0）；噪音候選 pass 合法（down 155 bars/286d span 過 30/180 門檻）。帶外復算 3 項自洽（upper 公式 bit 級/SE 比例=σ 比/超帶量=buffer 天數）。
- **harness 期抓 2 修**：altcap producer dsn 漏傳（harness 錯非 adapter）；bundle 未裁窗（340 vs 295，`_clip_window` 修，mask 回看 buffer 保留）。
- **範圍紀律**：wiring sanity ≠ alpha 裁決；真實候選仍須完整 B1+Q1+M3/M4 閘鏈。報告正本 = workspace/reports/2026-06-10--l2-p3b-b1-wiring-signoff.md（PM 代寫）。

## 2026-06-10 — P4 online-FDR QC sign-off（APPROVE-with-FIX，P4 可進 E1-READY）

兩 sign-off 點皆 APPROVE-with-FIX。點 1 pre-reg hash 鏈：FIX-1.1 consume 限 supersedes 鏈 head / FIX-1.2 hash 釘 evidence 窗+重算先於一切渲染 / FIX-1.3 falsification 真評估+觸發鑄 dead-mode lesson。點 2 sealed-holdout §9（含對照原文重裁）：**FIX-2.1b 唯一 §9 阻斷**——gate 4(b) 原文 `>` 點比較對 daily-bar 區間對象語義不足（`==` off-by-one + 非對齊 oos_start 跨界 bar 全漏），正確=「末 bar 尾端 ≤ oos_start」區間算術鏡像 `_bucket_admissible`，reason 統一 `sealed_holdout_overlap`；FIX-2.3 re-scope 至 M1（confirm=accounting-confirm，null-confirm 率 15-40%，P5 晉升另要求 opened-OOS math gate+regime 標籤）。交互：MIT #3 × B1 promotion 語義零副作用；FIX-3.1 pre-DSR skip 經 MIT ACK-with-條件（謂詞 value-invariance 邊界，down-span 須換 value-free 版）。QN-1 V132 單向性非 DB-enforced（state_flags_chk 有部分防護）/QN-3 grep proof point-in-time/QN-4 同 cell 多 sealed row 聚合規則 fail-closed 取任一重疊即 DEFER。教訓：工具缺口（無 Bash 讀 branch）下重構原文必標註並留重裁條款——本次重構失準但條款救回。報告：workspace/reports/2026-06-10--l2-p4-qc-signoff.md

## 2026-06-11 — Polymarket 數據軸紀律 memo(PROCEED, artifact-only)
- 賠率=corroborating context only 釘死,進交易鏈必走三段鏈;採集端禁 relevance 截斷(不可逆選擇偏差)、append-only point-in-time、track-to-resolution(反 lib 預設 skip-closed,防 survivorship bias);H4 calibration=全軸前置 gate;CLOB /prices-history 回補走獨立 retrospective lane(resolved 市場僅 ≥12h 粒度)。報告:workspace/reports/2026-06-11--polymarket_axis_discipline.md(PM 代落檔)

## 2026-07-03 — 全倉 read-only 數學審計（FINDINGS: 2H/5M/5L/3I，無 CRITICAL）
- 前輪 P0/P1 全修復確認（donchian_prior/OU 殘差 σ/Kelly Wilson-LB/fast_track+slippage config 化/confluence load guard）；edge estimator 已內建 WF+PSR/DSR/bootstrap gate，113 real cells 0 過驗證、median n=6（樣本饑餓仍第一約束）。
- 兩 HIGH 均在進化回路：(1) blocked-signal 反事實 markout fill-at-signal-price+4bps 平價成本，與同 cell realized EV 直接矛盾（ATOM|Sell +75 vs −16.8bps）——false-negative 敘事根基不保守；(2) standing envelope refresh 死循環=負淨貢獻 gate（v710-738 拒真率 100%），d0eeafb41 修判準側、TTL 12h 側殘留。
- 復用教訓：反事實 lane 的矛盾檢查=同 cell realized edge 必附；probe n=2 對 75bps 檢定 power≈8%（驗證用途須明示）；per_trade_risk_pct 是 fraction（0.1=10%）與同塊 percent 欄位混雜，見 4 處 stale "2%" 註解。報告：workspace/reports/2026-07-03--qc-full-repo-math-audit.md
