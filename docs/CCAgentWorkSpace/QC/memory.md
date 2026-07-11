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

## 2026-07-09 — 盈利研判 Stage 2（FINDINGS：10 diagnoses / 7 opportunities）
- F1 逐位復核確認（5,058 NEAR outcomes = 2 distinct entry ×2529 偽複製，n_eff≈1-2）；誤殺偵測 lane 雙重失效（F1 膨脹 vs conservative_v1 成本 92.3bps ≈ 4× 實測 E[cost]~23bps 壓低），33/76 cells 落 GROSS_EDGE_POSITIVE_COST_CUSHION_INSUFFICIENT = 唯一可能藏誤殺母集。
- 新結構事實：maker adverse selection 是 strategy-conditional（flash_dip −12.68/funding_arb −13.48 vs grid −2.45/ma −1.34/bb_rev −2.37 bps）——aggregate −7.57 掩蓋結構；bb_reversion gross +9.06bps 差一個執行檔（taker RT 19.5 vs maker RT ~8.7）。攻首位 = horizon arbitrage（1d klines 26sym×2yr 在位，$0 可驗，bull-heavy 標註強制）。
- 教訓：成本模型「保守」≠ E[cost]×4——E[slip] 與 tail（p10 −37.79bps）必須分離（期望入 gate、tail 入 CVaR 預算）；counterfactual lane 修復前，gate 誤殺率雙向皆不可信。報告：workspace/reports/2026-07-09--profit-diagnosis-stage2-qc.md

## 2026-07-09 — EXT 外部盈利情報掃描（FINDINGS：7 機會項，全 $0 read-only 第一步）
- 三個前提變化未被舊裁決吸收：①Bybit Spread Trading（2025-04 API）把 funding carry 產品化為原子雙腿+費率 50% 折 → funding_short_v2 兩堵牆（leg risk+雙腿費）被交易所自己拆了，但 runtime 證實 25-symbol 宇宙 funding 現貼 IR floor（max APR 10.95%）→ 監測項非交易項；②RPI `rpiTakerAccess`（2026-06-03 changelog）= API taker 免費執行改善，maker-nogo 未覆蓋此 taker-腿 lever；③token unlock 事件軸有 16k+ 事件外部實證（~90% 負向、30d 前置 drift），多日持有攤薄 taker 牆，驗證必須 beta 中性化（down-beta 教訓內建）。
- runtime 事實：`research.listing_capture_events`=0 rows（部署 5 週零捕捉）——新上市 niche 不會自己出證據，需 operator 授權自動 capture 排程。
- 報告：workspace/reports/2026-07-09--ext-profit-intel-scan.md（Operator 副本已落）。

## 2026-07-10 — 反事實重跑預註冊落檔(R3 修復包 WP-A.3)
- 判準先於重跑凍結:`docs/research/2026-07-10--counterfactual_rerun_preregistration.md`——dedup=(cell,entry_minute,horizon)、n_eff=非重疊窗 greedy、E1-E5(n_eff≥30/days≥5/top-day≤50%/censored≤30%)、day-cluster CR1 t(df=G−1)、BH-FDR q=0.10 去重後 family、成本雙軌(E[cost]=2×5.5+2×E|slip| 無 SM;CVaR90 tail 並列不判)、PROMOTE/VETO/INSUFFICIENT 三態判定式+翻案條件。
- 母集凍結新事實(metadata 級,未預看 outcome 統計):母集 A=71,207 精確重現(risk_verdicts⋈decision_features via context_id,join 守恆),僅 6 cells;FIL n_dedup=2、ARB n_dedup=1 → 預判必然 SAMPLE_INSUFFICIENT;僅 ETH(578min/8d)與 APT(1,387min/8d)可能過門檻。33-cell 母集 B 以分類規則+review artifact sha256(299751f2…)凍結,重跑第 0 步枚舉斷言=33。
- 教訓:pre-registration 的凍結錨要用「輸入身分(sha256)+分類規則+計數斷言」三件套——review JSON 只留 top16 cells,清單不可直接凍結時,規則+輸入+斷言等價且更防篡改。

## 2026-07-10 — 極端 funding 結算窗 event study(WP-B.4;REJECT+翻案條件)
- 預註冊母集 |F|>30bps:2yr×20 majors 僅 11 事件,10/11=2025-10-11 00:00 UTC 清算瀑布同一瞬間(n_eff≈2,day-cluster G=2),且全部早於 1m kline 留存起點(2026-04-05)→ 分鐘級不可測,SAMPLE_INSUFFICIENT;SOL/APT 事件 F 精確=lowerFundingRate(cap 截尾)。
- 敏感性(1m 窗 2026-04~06,n=3,894 事件):逆 funding 漂移各 tier gross 近零/負,扣 23bps taker RT 全 horizon 淨負(−18~−47bps),|F| 劑量反應 ρ≈0;唯一 nominal 顯著 cell(IR-floor 30m +2.15bps p=.005)= 假陽性候選(Bonferroni/day-cluster 雙殺)。
- 教訓:major 宇宙的極端 funding 是「單一 cascade episode 的多份拷貝」(與 F1 偽複製同構);此 niche 證據只能前向捕捉(Gate-B 新上市 capture)或 1m REST 回補,不會從現有留存長出來。報告:workspace/reports/2026-07-10--extreme_funding_settlement_event_study.md

## 2026-07-10 — EXT 外部掃描：bb_rev maker 化重放方法論（PROCEED + 10 條預註冊要求）
- 外部收斂三錨點：①DeLise 2024（TY 期貨）adverse fill=確定性機制，negative drift ≈ 半價差的 ~90% 回吞、1/3 不成交集中贏家側、touch-based fill 規則 85% vs 真值 60%；②MM Dilemma（arXiv 2502.18625，Binance BTC perp 最小單 live n=233k）fill 率 vs post-fill 報酬 90%/10% 負相關、隊尾 markout −0.775bp vs 隊頭 −0.058bp；③校正正本 = per-signal 無條件記帳（fill/no_fill/reject 三態入分母，Handa-Schwartz 1996 起）。全部 [外部類比]。
- 對本地：stage2「maker RT ~8.7bps」= 樂觀上界，唯一無條件節省是費率差 ~7bps RT；本地 fill_sim 3-case resolver 已在外部最嚴慣例級，重放缺的是信號條件化+無條件記帳+markout 延窗（5/15/30s 只夠 AS 分量，信號存活需 60s/5m/持有全程）+ 贏家/輸家 fill 率分層。報告：workspace/reports/2026-07-10--move2_external.md

## 2026-07-10 — Move 3 日級 horizon arbitrage 取數盤點（純證據,無裁決）
- 最重事實:Bybit REST 對已下架 symbol 回 retCode=0 但 0 bars(TON/MATIC 實測)→ 任何今日回補的 2yr 日線面板必為 survivor-conditioned;forward daily cron(已在,05:29)是唯一 PIT 無偏累積路徑。1d 在庫=26 syms(=roster+TON)×730d 截斷、僅共同缺 2026-06-27 一日;宇宙擴張=改 backfill_universe.toml+一次 --apply($0,1 page/symbol,617 USDT perp 可選),唯一前置=PIT liquidity cutoff 未定義。
- 執行面:多日持有無硬阻擋(holding_hours_max=168h time stop/funding_arb 72h 前例/funding_settlements 有記帳);KlineManager 無 1d buffer 但 flash_dip 有 DB 直讀前例。成本:23bps RT 5d 攤提=4.6bps/day/腿(L/S 9.2);funding 中位 +0.35bps/day(short 收)但負尾 TRX −4.0bps/day=短腿 5d 付 20bps→per-symbol funding 必入成本模型。2yr funding 史不在庫(REST ~11 pages/sym 可補)。報告:workspace/reports/2026-07-10--move3_evidence.md

## 2026-07-10 — EXT Move 3 外部掃描:日級 XS horizon arbitrage(PROCEED 進本地驗證)
- 外部證據淨結論:液態大幣 XS momentum/trend 扣費存活有正刊證據(CTREND JFQA 2024:top-100 net 2.45%/wk、BETC 1.25%/wk,樣本止 2022-05)但 post-2020 衰減實證在(FMPM 2025 單調性斷裂);**日級反轉=小幣 illiquidity artifact,液態層呈日級動量 → h=1 反轉 DOA**;h≥14d+maker+banding 成本 drag ≈2-4%/yr → 此域瓶頸是 IC×√breadth 非成本牆(與 1m maker-nogo 相反)。
- Breadth 數學:26 名宇宙 N_eff≈8-12(待 PCA),h=14d 單因子 net IR 1.0 需 IC≈0.10 = 2-5× 常態 → 必須跨族複合(mom×低波×量價);本地 2.1yr 1d 窗 t=2 只能確認 SR≳1.38 → p<0.05 gate 拒真率≈100%,裁決須改 effect-size CI+先驗+三態。
- 新 FACT:market.klines 1d=19,776 行/26 sym/2024-06-02→2026-07-09(mixed-regime 完整 boom-bust,BTC 62.7k→126k→58.6k→63.2k,非 bull-heavy);另有 153-sym 1h 宇宙自 2026-04-05(寬 breadth 輔助窗);26 名單有 end-of-sample survivorship(momentum 保守/reversal 樂觀)。報告:workspace/reports/2026-07-10--move3_external.md

## 2026-07-10 — Move 2 取數：bb_rev maker 化重放證據盤點（供數，不裁決）
- 三更正落錘：①`maker_markout_bps`=fill vs submit-reference（reference_source 異質），非 post-fill markout——60s/300s 真 markout DB 不存在須 L1 重算；②bb_rev maker markout 有效 n=**1**（−2.37 單筆，Stage 2 的 n=3 是 fill 數）；③60d gross 僅 +3.66bps（31-60d 單獨 −7.07），maker 化算術 60d 窗 markout=0 也負——「+0.3bps/RT」全押 30d 窗 gross 持續性。
- 重放可行性正面：l1_events 實 332.4M 行（hypertable 21GB；n_live_tup 4.3M stale 再證 count(*) 鐵則）06-20→07-10/85sym；bb_rev 25 信號 episodes（gap-dedup；跨 symbol 聚簇後 ≈14 獨立簇）100% 對齊 L1±60s；fills 無偽複製但 top-day 07-06 佔 30d gross 52%；harness 需改僅 placement 觸發+單側+episode 聚類（--horizons 60,300 免改碼）；exit 72% phys_lock giveback → 只能 execution-counterfactual。報告：workspace/reports/2026-07-10--move2_evidence.md

## 2026-07-10 — Move 3 方法論預註冊草案 v1(PROCEED 設計層,未凍結)
- K=114(19 信號×h{7,14,28}×2 權重)+ 單一 primary endpoint `M5|h14|EW`(CTREND-lite 複合趨勢×量能,pre-outcome 指定);GO=G1-G9 全真(含 dispatch 指定 PSR(0)≥0.95 demo gate)、KILL 僅允許在 P100 寬面板(功效前置 PC)、默認結局=INSUFFICIENT。
- Gate 雙向計價核心數字:PSR gate 於 2.1yr 窗拒真率 82%(真 SR=0.5)/58%(SR=1.0);26 名 grid+Bonferroni114 功效 ≤0.35 → 26 名窗禁 discovery/禁 KILL;宇宙擴張=並行但為 KILL 前置;成本鎖 taker 23bps/RT+funding 逐日,maker 僅 annex。
- 教訓:高拒真 gate 要可用,必須配「誤殺可逆」結構(fail→INSUFFICIENT 非 KILL + pooled evidence 追加);h=14/28 與 holding_hours_max=168h 衝突是 demo 實作最早的硬前置。報告:workspace/reports/2026-07-10--move3_methodology_prereg_draft.md

## 2026-07-10 — Move 2 方法論預註冊草案（bb_rev maker 化重放;PROCEED 送審）
- 估計對象重定義落錘:「net=+0.3bps」在 σ_Δ≈8bps 下需 ~4,400 episodes(10 年)=正式宣告不可檢定;改測三分量(無條件 fill rate/真 post-fill 60s+300s markout/Lane A 配對 Δcost,MDE@n=30≈3.6bps 恰可辨 3.5bps 費率差)。判定式 SCREEN_PASS(G1-G8)/KILL(K1-K4)/INSUFFICIENT 三態機械可裁;queue 折扣拒 50% 檔(resolver 已動態建模 cancel-ahead,靜態折扣=重複計算)主判 back-of-queue;記帳=per-episode ITT 三軌(T/M-fb/M-skip),fill-only 僅機制分解。
- 邊界釘死:execution routing for existing signal ≠ market-making quoting——maker-nogo(0/172,break-even≤0.4bps)不重打不觸碰;SCREEN_PASS ≠ cell 可盈利(60d gross 下淨值仍負);probe「21d≥200 trades」在單 cell 不可達 → 解除條件改 200 signal-episode 對應物+V1 fill-rate 0.7-1.3 校準帶。報告:workspace/reports/2026-07-10--move2_methodology_prereg_draft.md

## 2026-07-10 — Move 3 prereg 對抗紅隊(REVISE;FIX-1..7 後可凍結)
- 核心 finding RT1:GO 閘鏈功效≠IC 檢定功效——用 prereg 自己的表 P3 相乘,IC 0.07-0.08 → net SR 0.18-0.42 → P(G2 PSR gate)≈8-15%,coin-flip GO 需 IC≈0.18-0.21;Stage A(26 名窗)實質不可 GO,demo 路徑只有 pooled E100⊕E_fwd。另 T 混同:功效表用 765d 但 E26 實長≈504d(174d warmup+90d 首 train),PSR 門檻 1.14→1.40。
- 新 FACT($0 可重跑):Bybit announcements REST type=delistings 全歷史檔可枚舉(total 442;in-window 2024-06→2026-07 398 則/perp-titled 238)→ survivorship 通道 A 可量化非只標註;通道 B(roster-churn:WIF/ORDI/1000PEPE/SHIB1000 等仍 Trading)可由 Stage B retro top-100 完整修復。單缺席 short-leg 衰退幣 ≈ +0.8bps/day 動量低估=與全部淨 edge 同量級(一階項)。
- 教訓:regime 穩健性的獨立單位是 episode 非 day(bear 273d=1 episode,與 F1 偽複製同構);demo-cell≠GO-cell(h14 被 holding_hours_max=168h 硬截)是 prereg 最易漏的實作斷點;R2 邊界的嚴格寫法=成本歸一化差 7-14×+投影正交+外部先驗非空,但同資訊集/同線性 IC 法的弱負先驗必須顯式入折減。報告:workspace/reports/2026-07-10--move3_redteam.md

## 2026-07-10 — Move 2 紅隊審計（REVISE；R1 保留、probe/敘事殺掉）
- 六攻擊面 0 FATAL 於 R1 重放本體，但 5 條強制修正（FIX-1 fallback晚於realized exit 記帳未定義=G4/K3 承重洞;FIX-2 G6 gross_all 分母漏回選擇效應;FIX-3 決策樣本 ≥15 post-reg episodes;FIX-4 **`l1_events` retention=21d 滾動**——累積數學前提不存在、凍結斷言 07-19 起蒸發、R1 本週必跑+切片釘 artifact;FIX-5 descope：probe 需新 Rust 管道（bb_rev 無 use_maker_entry，registry.rs:144/242/272）、單 cell 價值 0.77-9.0 USDT/月=經濟死、宿主經濟正解是 grid）。
- 「JS 自鎖零成本破鎖」敘事三腿全斷（FACT）：soak 全攔 07-02 已結束（415,651 拒全落 06-29→07-02，withhold 時代僅 6 筆）、標籤已自流（bb_rev 15/15 closes 7d 內標齊）、probe 對 label 量零增量、cost_gate 不因 fill 解鎖；新 finding=V147 label_source 半接線（14/15 NULL）→ label_source 基監測少算 ~15×。
- 教訓：任何「每週累積重放」設計必先查 timescaledb retention job（滾動窗 vs 累積庫）；motivating cell 作為 max-of-K 其 30d gross 證據含量≈0（Sidak K=6 → p 0.084），但執行分量估計對象可與 cell 選擇解耦——耦合殘留只在以 gross 為分母的 gate。報告：workspace/reports/2026-07-10--move2_redteam.md
