# PA 決策檔案 — Move 3：日級 Cross-Sectional Horizon Arbitrage · 2026-07-10

- **性質**：決策綜合 dossier（PA 視角，read-only 研究；唯一寫入=本檔）。
- **輸入**（四份同前綴 QC 報告，`docs/CCAgentWorkSpace/QC/workspace/reports/`）：
  - EV = `2026-07-10--move3_evidence.md`（取數盤點，FACT A1-E3 / F1-F11）
  - EXT = `2026-07-10--move3_external.md`（外部文獻掃描，F1-F10）
  - PRE = `2026-07-10--move3_methodology_prereg_draft.md`（PREREG-DRAFT v1，未凍結）
  - RT = `2026-07-10--move3_redteam.md`（對抗紅隊，RT1-RT11 / FIX-1..7，總判定 REVISE 無 FATAL）
- **上游定位**：Move 3 = `PA/workspace/reports/2026-07-09--profit_opportunity_map_roi_ranked.md` Top Move #3（attack / paradigm blocker）。
- **PA 親驗**（不照單全收上游 verdict）：`settings/risk_control_rules/risk_config_demo.toml:22` `holding_hours_max = 168.0`、`rust/openclaw_engine/src/risk_checks.rs:389` `max_hours = limits.holding_hours_max * rm.time`、`event_consumer/bootstrap.rs:985-992`（KlineManager DEFAULT_TIMEFRAMES 不含 "1d" + flash_dip DB 直讀前例）、`strategies/strategy_params.rs:825/861`（per-strategy `max_hold_ms`，funding_arb 72h 前例）——RT6 的 file:line 全部屬實。
- **regime 鐵律**：本檔所有 in-DB funding/slippage 數字屬 2026-04~07 窗（regime-specific）；1d 驗證窗為完整 boom-bust mixed-regime（EXT F7），但 bear episode n=1（RT5）——「all-weather」表述全檔禁用。

---

## ① 一頁結論

### 裁決：**GO_WITH_CONDITIONS**（作為 $0 研究管線批准；作為近期 PnL 線不批准）

**置信度**：研究線該走 = **高**（四報告收斂、紅隊無 FATAL、$0、read-only、與全部既有 NO-GO 相容）；最終產出 demo-admissible 正 alpha = **低-中**（紅隊算術：Stage A P(GO) ≤ ~15%，正 net 是先驗上端 1/3 的條件事件）。兩個置信度必須分開報，不得混講。

**批准的東西是什麼（誠實價值主張，採 RT §0/§6.2 措辭）**：買的是「已預註冊的 XS 研究管線 + Stage B breadth 期權 + forward PIT 無偏面板累積」，**不是近期 PnL**。預期最可能結局 ≥85-90% INSUFFICIENT（-POSITIVE）→ 續累積；即使先驗上端全中，量級 = net +2.9-4.0%/yr ≈ $100k book 下 ~$3-4k/yr。

**五個 GO 條件（缺一 = 本裁決不生效）**：
1. **凍結前吸收 FIX-1..FIX-7** → prereg v1.1（RT 全部 pre-outcome 合法；零成本修補窗口只在凍結前）。v1 原樣凍結 = 不批（RT 翻案條件之兩個機械命題無人推翻）。
2. **敘事改寫入 v1.1**：「Stage A 不產 demo admission；demo admission 的現實路徑 = pooled E100⊕E_fwd」（RT1 處置，見 §③）。
3. **engine/demo 實作 0 授權**：GO verdict 機械產生之前，不寫任何 engine lane 代碼（批次權重執行器/hedge overlay/per-leg SL 治理）——那是 M12 級 workstream（3-5 sprint），在 P(GO)≤15% 下前置建設 = 負期望工程。
4. **Stage B 與 Stage A 同週啟動**（operator-gated `--apply`）：breadth 是唯一在合理時間內改變功效的槓桿（PRE §5.10）；Stage B 不批 → 本線降級為「forward 累積 + 描述性 grid」，且 KILL 永不可達（只能 PARK，須向 operator 明示）。
5. **價值主張以修正後形式呈交 operator**（見 §⑤ Q2）——operator 若不接受「管線+期權」定位，本線改列 PARK，forward cron 照跑（零人力）。

**為何不是 NO-GO**：(a) 紅隊自己的結論=線不死（六攻擊面 0 FATAL，4 個 SURVIVABLE_WITH_FIX + 1 DEFLECTED）；(b) 這是 06-14 mandate「換 lens 原生數學」下唯一直攻範式牆且外部有正刊證據鏈的 attack move；(c) R2 範疇邊界成立（成本歸一化差 7-14×、投影正交）——舊 NO-GO 數據無法裁決本線；(d) $0 + 全 additive + 可隨時 PARK，錯放成本被結構性壓低。

**為何不是無條件 GO**：prereg v1 自己的表格相乘後（RT1/RT2），26 名窗物理上不存在可信效應強度能過 G2；若不改寫敘事，operator 會以「效應夠強就能 GO」的錯誤預期計價本線。

---

## ② 關鍵數字表（全帶證據等級）

證據等級：**FACT**（可重跑 SQL/curl/file:line）> **DERIVED**（算術可復算）> **ASSUMPTION**（待實測）> **外部類比**（文獻，不等同本地證據）。

| # | 數字 | 值 | 等級 | 來源/重跑 |
|---|---|---|---|---|
| N1 | 1d 面板 | 19,776 rows / 26 sym / 2024-06-02→2026-07-09；唯一缺日 2026-06-27 | FACT | EV A1/F6；SQL 在 EV 附錄 |
| N2 | 面板 survivorship | 下架歷史不可回補（TON/MATIC REST 0 bars）→ retro 面板必 survivor-conditioned | FACT(HIGH) | EV F1；R2 curl |
| N3 | 下架公告可枚舉 | REST 全檔 442 則（in-window 398 / perp-titled 238），$0、9 pages | FACT | RT 1.2（升級 EV B2 的悲觀判定）|
| N4 | 現宇宙 | 617 USDT perp Trading；WIF/ORDI/PEPE 等衰退幣仍 Trading（通道 B 可由 Stage B 完整修復）| FACT | EV B1；RT 1.1 |
| N5 | Stage B 成本 | 1d×730d = 1 request/symbol；top-100 分鐘級 $0；改動=TOML+`--apply` | FACT | EV B4 |
| N6 | 成本線（taker 上界）| 23bps/RT 腿；pair 46/h bps/day：h=7/14/28 → 6.57/3.29/1.64；h=14 banded ≈59bps/月 | FACT 算術 | EV C2；RT §6.1 |
| N7 | slippage 實測 | global q50 3.0 / q90 34.8 / mean_abs 17.9 bps（n=2,531，90d）；除 BTC/ETH 全 thin_sample | FACT | EV C1/F8 |
| N8 | funding（regime-specific 窗）| 26 sym 中位 +0.35 bps/day；負尾 TRX −4.01（5d short ≈ −20bps）；2yr 史不在庫，REST ~11 pages/sym 可補 | FACT | EV E1-E3/F4 |
| N9 | E26 有效長度 | ≈504d（非面板 765d；174d warmup + 90d 首 train 燒掉）| DERIVED | RT2 |
| N10 | G2 門檻真值 | PSR(0)≥0.95 ⇔ 觀察 net SR_ann ≥ **1.40** @T=504（非 1.14）| DERIVED | RT2 |
| N11 | **Stage A P(GO)** | 任何 post-decay 可信 IC(≤0.10) 下 ≤ **~15%**；coin-flip GO 需 IC≈0.18-0.21（=CTREND 未衰減 2×）| DERIVED | RT1（紅隊核心 finding）|
| N12 | net 殘值 | 先驗均值 IC 0.03-0.05 → **−0.8~0 bps/day（負）**；上端 0.07-0.08 → +0.8-1.1 bps/day = +2.9-4.0%/yr ≈ $3-4k/yr @$100k book | DERIVED（book vol 15%/yr 為 ASSUMPTION）| RT §6.2 |
| N13 | survivorship 量級 | 單缺席 short-leg 衰退幣 ≈ +0.8 bps/day 動量低估 = **與全部淨 edge 同量級（一階項）**；方向對動量保守、對 reversal/Q 族樂觀 | DERIVED+ASSUMPTION | RT 1.3/1.4 |
| N14 | N_eff | ≈8-12（26 名宇宙 β 殘差化後）→ 名目 breadth 3-5× 高估 | ASSUMPTION（P0-3 PCA 實測前）| EXT §3.1；PRE MF8 |
| N15 | regime 窗 | BTC 62.7k→126k→57.8k→63.2k 完整 boom-bust（mixed，非 bull-heavy）；但 bear/bull episode 各 n=**1**；recovery 層在 E26=0d | FACT + RT5 | EXT §5.8；RT §3 |
| N16 | 外部錨 | CTREND JFQA 2024：net +2.90%/wk t=3.89、BETC 1.41%/wk、top-10% 大幣仍 α>2%；**止 2022-05，×0.3-0.5 折減後入先驗** | 外部類比 | EXT §2.1/§2.5 |
| N17 | REJECT 子方向 | 液態層 h=1 日級反轉 = illiquidity artifact（外部證據直接反對 + 365RT/yr 成本牆）；long-only liquid winners = regime-bet | 外部類比(HIGH) | EXT §8.2 |
| N18 | demo 硬截 | `holding_hours_max=168h`(toml:22) × `rm.time`(risk_checks.rs:389) → primary h=14 在 demo 被第 7 天強平（demo-cell ≠ GO-cell）| FACT（PA 親驗）| RT6 |
| N19 | 1d 數據面 | KlineManager 無 "1d" buffer（bootstrap.rs:985-992 註解明示）；flash_dip DB 直讀前例可循，不動 KlineManager | FACT（PA 親驗）| EV D4 |
| N20 | 統計功效鐵頂 | 26 名窗 t=2 只能確認 SR≳1.38-1.40；「等時間」不解決（SR=0.5 要 power 0.5 需 ~10.8yr）→ breadth 是唯一槓桿 | DERIVED | EXT §3.3；PRE §5.10 |

---

## ③ 紅隊攻擊處置表

**FATAL 項正面回答：紅隊六攻擊面 0 FATAL**（RT §0 明示）。兩個 HIGH（RT1/RT6）必須正面處置如下，其餘按表。

| 攻擊 | 紅隊裁決 | PA 處置 | 落點 |
|---|---|---|---|
| ① Survivorship | SURVIVABLE_WITH_FIX | **接受**。通道 B（roster churn）由 Stage B retro 完整修復（衰退幣仍 Trading，FACT）；通道 A（真下架）由 FIX-2 P0-6 tombstone 表枚舉+量化入界；per-family 方向表（Q 族=樂觀）強制入 v1.1；G5/maxDD 附「倖存面板=風險下界」標註；K1 加 attrition 敏感度（FIX-3）防假 KILL | v1.1 §3.7/§5.7 + 新 P0-6 |
| ② Breadth/功效（**RT1 HIGH**）| SURVIVABLE_WITH_FIX | **正面回答：接受紅隊算術，全盤採納**。IC 檢定功效 ≠ GO 閘鏈功效；用 prereg 自己的表 P3 相乘後，26 名窗不存在物理可信的效應強度能過 G2（需 IC 0.18-0.21）。**裁決後果：Stage A 的定位從「可能 GO」改寫為「產 primary 效應量 CI + 描述性 grid + INSUFFICIENT 起點」，demo admission 唯一現實路徑 = pooled E100⊕E_fwd**。功效表重算於 T=504（FIX-1）；G2 高拒真被成本不對稱論證支持（錯放=數週工程+60d demo 佔用 vs 錯殺=~$250-330/月推遲，不可逆性已被 fail→INSUFFICIENT 移除）| v1.1 §1/§5.10 敘事改寫 |
| ③ Regime episode n=1 | SURVIVABLE_WITH_FIX | **接受**。G4 保留為符號檢查（273d bear 無獨立裁決力，需 ~1,460d）；GO 報告強制標 n_episodes per regime；增 chop/dispersion 分層（可解釋指標 shift(1)）；forward 累積 ≥2 獨立 bear episode 前禁「all-weather」 | v1.1 §5.8（FIX-4）|
| ④ Engine lane 成本（**RT6 HIGH**）| SURVIVABLE_WITH_FIX | **正面回答：接受「近零」低估的指控**。PA 復驗確認：XS book = 目標權重批次 rebalance 執行器 + 常駐 BTC hedge overlay（現架構無此概念）+ 停用 per-leg SL 的治理裁決（與根則 9 交易所側保護衝突，須 CC/PA 具名裁決，非備註）= **M12 級新執行範式，初估 3-5 sprint，觸 orchestrator/PipelineBridge/風控 = 高風險面**。處置：全部 gated 在 GO verdict 之後，現在 0 授權（本裁決條件 3）。demo-cell≠GO-cell：採 FIX-5 選項 (a)——TOML holding 決策列為 GO→demo 具名 blocking 前置（owner=operator），**不採選項 (b)**（重凍 primary=h7），理由：h=7 成本 drag ×2 且 banded 14.4% 貼 INVALID_COST 線 15%，為遷就現行 demo config 而改 primary = 本末倒置；且 per-strategy `max_hold_ms` 前例（funding_arb 72h）存在，但 risk_checks.rs:389 全局 time stop 仍外層封頂 → 真解法必經 operator TOML 決策（scoped，只動 holding 一參數，承 `feedback_risk_changes_scoped`）| v1.1 MF3 升格（FIX-5）+ 本檔 §⑤ Q5 |
| ⑤ R2 範疇邊界 | DEFLECTED | **接受紅隊的 DEFLECTED**：邊界實質成立（成本歸一化 7-14×、XS demean 投影正交、外部先驗非空）。文檔級修補：v1.1 增「證偽範圍表」（H_R2 vs H_M3 逐軸）+ 兩條殘餘重疊（同資訊集/同線性 IC 法）顯式併入 ×0.3-0.5 折減論證——**不許用「不同域」一筆帶過** | v1.1 §8.5（FIX-7）|
| ⑥ Turnover/net 殘值 | SURVIVABLE_WITH_FIX | **接受**。結論句入文：「prereg 自己的先驗均值下 net 為負；正 net 是先驗上端 1/3 條件事件」；$-期望值表 + P(GO) 聯合行進 §7/§8 供 operator 直接計價 | v1.1 §7/§8（FIX-1 經濟誠實條款）|
| RT7 序貫洩漏 | MEDIUM | **接受**。登記 look 時點表（建議：凍結+6mo / +12mo / Stage B 完成時，共 3 個registered look）；解 §3.3 vs §5.7(e) 矛盾——PA 小決策：**採「v2 primary 若選自 v1 grid → DSR 繼承 K_cum」**（比「只在未用數據檢定」操作性強，且不阻斷 grid 的探索價值）| v1.1 §5.7（FIX-6）|

---

## ④ 預註冊定稿要點 + 實作工作量 + 驗證路徑 + kill 條件

### 4.1 預註冊定稿要點（v1 → v1.1，凍結前一次完成）

1. FIX-1：功效表全部重算於 T=E26≈504d；新增 P(GO|IC) 聯合行 + $-期望值表；§1/§5.10 敘事改寫（Stage A 不產 demo admission）。
2. FIX-2：新增 **P0-6 = 下架公告 tombstone 表**（9 REST pages 枚舉 + MATIC→POL/FTM→S 遷移映射）+ per-family survivorship 方向×量級表；G5/maxDD 附風險下界標註。
3. FIX-3：K1 加 attrition 敏感度（CI_upper+δ_attrition 仍<成本線才 KILL）；retro 面板 reversal/Q 族 Bonferroni 發現自動標 `SURVIVORSHIP_SUSPECT`。
4. FIX-4：chop/dispersion 分層 + n_episodes 標註 + recovery 層 E26=0d 明寫。
5. FIX-5：MF3 升格為具名 blocking 前置（owner=operator）；engine 改動按 §③④ 重新計價；`correlated_exposure_max_pct=65`（demo toml:16）與 8-9 腿同向 book 的交互 → 併入 EV F5 open-question 清單；明寫「demo 60d 只校準執行/成本/funding 記帳，不供 alpha 證據」（h=14 下 60d 僅 4.3 個獨立持有週期）。
6. FIX-6：registered look 時點表 + K_cum 繼承規則。
7. FIX-7：證偽範圍表（H_R2 vs H_M3）+ 殘餘重疊入折減論證。
8. 凍結三件套照 PRE §5.9 執行（面板 sha256 + 規則全文 sha256 + 計數斷言 K=114、primary=`M5|h14|EW`）。primary cell 不變（h=14 的分析動機成立，demo 衝突走 blocking 前置解）。

### 4.2 實作工作量初估（sprint + 觸碰面）

| 階段 | 內容 | 工時 | 觸碰面 | gating |
|---|---|---|---|---|
| R0 | QC 吸收 FIX-1..7 → v1.1 + PM/operator 批准 + 凍結 | ~0.5 sprint（QC）| 僅 QC workspace 文件 | PM/operator 批准 |
| P0 | P0-1 funding 2yr 回補（~11 pages×26/100 sym）、P0-2 缺日回補（`--lookback-days 30` 重跑）、P0-3 PCA+book vol 實測、P0-4 parquet f64 面板、P0-6 tombstone 枚舉 | ~0.5-1 sprint（E1）| research schema DB 寫（append-only）+ `market.klines`（ON CONFLICT 冪等）；0 engine 檔 | P0-1/P0-2 operator-gated `--apply`；P0-3/4/6 純讀 $0 |
| Stage A harness | `helper_scripts/research/xs_daily_lane/`（PRE §8.3-1 目錄結構：prereg json / build_panel / signals spec+PIT 斷言 / backtest engine / stats gates / 114-cell 全量落盤）| ~1-1.5 sprint（E1，MIT 審 leakage/CV）| **新研究目錄 only + SCRIPT_INDEX.md**；0 熱檔、0 engine、0 config、0 gate | 無（$0 離線）|
| Stage B | TOML universe 擴 top-100 + 一次 `--apply` + QC/MIT PIT liquidity cutoff 定義（PRE §8.3-4 提案為底）| ~0.25 sprint（QC/MIT）+ 分鐘級回填 | `settings/backfill_universe.toml` 一檔 | operator-gated `--apply` |
| Forward shadow | 凍結日起每日離線算 P* 信號+虛擬淨值（不下單不進 engine）→ E_fwd | ~0.25 sprint（E1，cron wrapper 套 `ml_training_maintenance_cron.sh` 範本）| 研究目錄 + cron 一行 | operator 認可 cron 行 |
| **Engine/demo lane** | 批次權重執行器 + hedge overlay + per-leg SL 治理 + halt 交互閉合 + holding TOML 決策 | **3-5 sprint（初估，GO 後 PA 重新設計）** | orchestrator/PipelineBridge/風控 = **高風險面** | **GO verdict + operator；現在 0 授權** |

Pre-GO 合計 ≈ **2.5-3.5 sprint**（QC/E1/MIT 分攤，可高度並行），全 $0、全 additive。

**代碼足跡與持續開發成本**：新增 ~1,500-2,500 LOC Python 研究碼（過半為 PIT 斷言/gate 測試），熱檔觸碰 = 0。**Rust-first 例外聲明（小決策）**：本 harness 屬離線研究分析，非 trading/risk/config 邏輯，沿 `residual_alpha_producer_db.py` / fill_sim / ADPE 既有 Python 研究範式（等效方案取讀碼成本低者；Rust 重寫無風險收益，違背既有 harness 複用）。持續成本：daily cron 零人力；30d 重跑按 registered look 時點，非常開。

**E1 派發計劃（PM 交接；時序決策權在 PM）**：R0(QC) ∥ E1-A(P0 腳本：funding 回補+tombstone+PCA+parquet) 可並行（檔零重疊）；E1-B(harness 本體) 可與 R0 並行搭骨架，但 `prereg/move3_prereg_v1.json` 與 gate 閾值須等凍結後注入；Stage B 等 operator 批。**E2 重點審查 3 點**：① PIT invariance 斷言真實 enforce（每特徵「t 後資料置 NaN 不改 t 值」0 fail；shift(1) 全覆蓋，含 z90/β/M4 權重）；② 判定式機械性（step-0 斷言 K=114+sha256 否則 abort；G 統計只算 E 序列，in-sample 不進判定；maker 僅 annex 不入判定式）；③ funding 逐倉逐日記帳（禁 cross-section 平均；缺值規則 long 付 floor/short 收 0 的保守方向）。

**降級/rollback 路徑**（缺此項=設計未完成）：全 additive——harness `rm -rf` 目錄 + 撤 SCRIPT_INDEX 行；Stage B = revert TOML 一檔（已回填 rows 無害留存，cron 停止維護擴張名單）；funding/tombstone 回補限 research schema append-only（rollback=DELETE by run tag）；forward cron = 撤一行。**0 engine binary 改動、0 V### migration、0 flag flip**——pre-GO 全程不存在需要 restart_all 的動作。運行時 kill：停 cron 即凍結累積，面板不腐爛（daily backfill 獨立維護）。

### 4.3 驗證路徑

```
v1.1 凍結 → P0 完成檢查 → Stage A（E26：WF-OOS 串接，taker+funding，demeaned）
  → 114-cell 全量落盤（Bonferroni 決策線 / BH 描述線）+ primary G1-G9 逐謂詞
  → Stage B（P100 面板 + tombstone 修正）→ pooled E100⊕E_fwd（時間不重疊串接）
  → registered looks（+6mo/+12mo/Stage B 完成時）
  → 若 GO：Stage 0R replay preflight（綠）→ Demo-only（硬邊界）≥60d
     【demo 只校準執行/成本/funding，不供 alpha 證據】→ operator 覆核
  → 若 INSUFFICIENT（預期主結局）：forward 累積 + 30d 凍結 spec 重跑（按 look 表）
```
輔助：153-sym 1h 宇宙聚合日級做 primary 同號檢查（異號→強制入風險節，不進判定）。

### 4.4 Kill / Park 條件

| 條件 | 觸發 | 動作 |
|---|---|---|
| **Family KILL**（機械）| P100 可用後：K1（gross demeaned spread 95% CI 上界 + δ_attrition < 成本線 46/h，h∈{7,14,28} 全部）∨ K2（家族複合 IC 95% CI 上界 <0.02）| 家族除名；翻案條件強制附帶（PRE §5.7 三條）|
| **Line PARK**（PA 增設）| 兩個 registered look（+6mo/+12mo）皆 INSUFFICIENT 且無 -POSITIVE 子標籤（效應連符號都不穩）| 降級為 forward-cron-only（零人力），不再佔 QC/E1 sprint |
| **即時停** | G1 leak-audit 任一 fail | outcome 主張全部凍結至修復+重跑 |
| **結構降級** | operator 不批 Stage B | 明示：KILL 永不可達（26 名窗禁 KILL），本線只剩 Stage A 描述 + forward 累積；重新計價是否值得佔 harness sprint |

---

## ⑤ Open Questions 給 Operator

| # | 問題 | 影響 | 建議 |
|---|---|---|---|
| Q1 | **Stage B 三個 `--apply` 授權**：top-100 1d 回補、funding 2yr 回補（26→100 sym）、2026-06-27 缺日回補（$0，分鐘級，冪等）| 不批 → KILL 不可達 + discovery 功效鎖死（N20：breadth 是唯一槓桿）| 批（read-only 研究面 DB 寫，additive）|
| Q2 | **價值主張接受**：本線買「管線+breadth 期權+forward 無偏面板」，非近期 PnL；預期 ≥85-90% INSUFFICIENT；上端情境 ~$3-4k/yr @$100k book | 不接受 → 改列 PARK（forward cron 照跑，零人力）| 誠實計價後再裁；這是 mandate 下唯一有外部正刊證據鏈的 attack move |
| Q3 | **Registered look 時點表批准**（FIX-6：凍結+6mo/+12mo/Stage B 完成時）| 防序貫檢定洩漏（null 越界 5%→8-12%）| 批 3 個 look |
| Q4 | **Forward shadow daily cron** 一行授權（離線信號+虛擬淨值，不下單不進 engine）| E_fwd 是 pooled evidence 與真 OOS 的來源 | 批 |
| Q5 | **holding_hours_max TOML 決策**（demo 168h vs primary h=14）——現在只具名登記為 GO→demo blocking 前置（owner=operator），**不是現在要改**（承 `feedback_risk_changes_scoped`，且 P(GO)≤15%）| 屆時不決 → demo 只能跑非 primary cell（禁互為證據）| GO 真發生時再裁；屆時連同 per-leg SL 治理（根則 9）一併走 CC/PA 裁決 |
| Q6 | **EV F5 兩個未閉 open question**（多日持倉×daily-loss halt 交互；擴宇宙訂閱接線）| demo enable 的 blocking 前置（prereg 已列）| GO 臨近時派 E1 read-only trace，現在不佔 sprint |

---

## 附：硬邊界與 16 根原則合規速查（16-root-principles-checklist 引用）

- **硬邊界 0 觸碰**：pre-GO 全程不觸 `live_execution_allowed` / `max_retries=0` / `system_mode` / lease / authorization.json；無 GovernanceHub SM / PipelineBridge / API schema 改動；grep 指紋掃描對象（研究目錄）無任何命中面。
- **Alpha Evidence Governance 內建**：math-primary（外部文獻僅先驗錨，×0.3-0.5 折減）；regime 分層機械化（G4）+ bull-only → `REGIME_BET_LEARNING_ONLY` 不可 GO；demeaned-β 鐵則 XS 版（雙 demean + raw/demeaned 並列）。
- **原則 7（學習≠改寫 Live）**：全程離線研究面；demo admission 走 Stage 0R→Demo-only 硬邊界。
- **原則 10（認知誠實）**：本檔全數字帶 FACT/DERIVED/ASSUMPTION/外部類比 四級標記。
- **原則 13（成本感知）**：$0 線；G7 cost_edge_ratio ≤0.8 硬線已入判定式。
- **唯一被前瞻性標記的原則衝突**：GO 後停用 per-leg SL vs 根則 9（交易所側條件保護）——已列為 CC/PA 具名治理裁決項（§③ 攻擊④），不在本輪範圍。

---
*PA · 2026-07-10 · read-only 決策綜合。Operator/ 副本未落（本次 dispatch 唯一寫入=role workspace 報告檔），PM 如需請代複製（沿 QC 同批 dispatch 慣例）。*
