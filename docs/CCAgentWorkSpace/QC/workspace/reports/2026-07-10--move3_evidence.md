# QC/MIT 取數報告 — Move 3 日級 cross-sectional horizon arbitrage 證據盤點 · 2026-07-10

**角色**：QC/MIT 混合取數員（只取數與盤點，不設計、不裁決）
**範圍**：(a) 1d klines 庫存審計 (b) 宇宙擴張可行性 (c) 成本模型輸入 (d) 執行面現狀 (e) funding drag
**紀律**：全程 read-only；所有 FACT 附可重跑 SQL/命令/file:line；regime 鐵律適用（in-DB funding/slippage 窗全落 2026-04~07，屬 regime-specific 樣本）。
**取數時點**：2026-07-10 17:4x–18:0x CEST（Linux trade-core PG + api.bybit.com public REST + Mac repo HEAD 1a3ecdd57）。

---

## 0. Executive Summary（純事實，不含 GO/NO-GO）

1. **1d 庫存**：`market.klines` timeframe='1d' = 19,776 rows / 26 symbols / 2024-06-02→2026-07-09；缺口僅一個全體共同缺日 2026-06-27。universe = `settings/backfill_universe.toml` 固定 26 名單（= 現 roster 25 + 已下架 TON）→ **survivorship-conditioned by construction**。
2. **最重事實（HIGH）**：Bybit REST kline 對已下架 symbol 回 `retCode=0` 但 **0 bars**（TONUSDT、MATICUSDT 實測）→ 下架歷史**不可回補**；今天建的任何 2yr 日線面板天然以「存活到 2026-07」為條件。唯二緩解：庫內已留存的 TON 744 根 1d（2024-06-02→2026-06-15）；forward 持續跑 daily cron 從今起累積 point-in-time 無倖存者偏差面板。
3. **宇宙擴張**：現 Bybit linear USDT perp Trading = **617** symbols；AEG backfill 擴到 top-50/100 = 改一個 TOML 名單 + 一次 operator-gated `--apply`（1d 730 根 = 1 request/symbol，$0，分鐘級），daily cron（05:29, lookback 7d）自動維護。「176-symbol 1m×3mo」= `market.klines` timeframe='1m'（現 179 symbols，16.57M rows，2026-04-05 起；其中 ~86 symbols 的 wide ingest 於 2026-06-15 21:39 同分鐘停止）。
4. **成本輸入**：slippage artifact（v2, asof 2026-07-10, 90d, n=2531）global q50=3.0 / q90=34.8 / mean_abs=17.9 bps；roster alt 常見 q50≈5–13 bps。23bps/RT 單腿攤提：5d 持有 = **4.6 bps/day**；L/S 雙腿 46bps/RT = **9.2 bps/day**。
5. **執行面**：多日持有**無硬阻擋**——`holding_hours_max=168h`（7d）time stop、funding_arb 已有 72h max_hold 前例、funding settlement 有記帳（`trading.funding_settlements`）。缺口：KlineManager **無 1d buffer**（flash_dip 已有 DB 直讀 1d 前例可循）。
6. **Funding drag**：in-DB 窗（多數 2026-05-11→07-10，~60d）26 symbols mean daily funding 中位數 **+0.35 bps/day**（F>0 = short 收）；短腿 drag 集中於負 funding 尾部：TRX **−4.0 bps/day**（5d ≈ −20 bps）、INJ −1.7、BCH −1.6、ATOM −1.2。2yr funding 史**不在庫**（`research.alpha_funding_rates_history`=0 rows），REST $0 可補（~11 pages/symbol）。

---

## (a) 1d klines 庫存審計

### FACT A1 — 總量與範圍
`market.klines` timeframe='1d'：**19,776 rows / 26 symbols / 2024-06-02 → 2026-07-09**（UTC 午夜對齊；ts 顯示 02:00+02 = 00:00 UTC）。
重跑：`SELECT timeframe, COUNT(*), COUNT(DISTINCT symbol), MIN(ts), MAX(ts) FROM market.klines GROUP BY timeframe;`

### FACT A2 — per-symbol 起訖與缺口
| 組 | symbols | first_day | last_day | n_rows | 缺口 |
|---|---|---|---|---|---|
| 原始 20 名單 | BTC ETH SOL BNB XRP DOGE ADA AVAX LINK TRX DOT LTC BCH NEAR APT ARB OP SUI (+TON 特例) | 2024-06-02 | 2026-07-09 | 767 | 缺 2026-06-27 一天 |
| altcap 6 補齊（2026-06-10 --apply） | ATOM ETC FIL ICP INJ UNI | 2024-06-10 | 2026-07-09 | 759 | 缺 2026-06-27 一天 |
| POLUSDT | POL | 2024-09-05 | 2026-07-09 | 672 | 缺 2026-06-27 一天 |
| TONUSDT（已下架） | TON | 2024-06-02 | **2026-06-15** | 744 | 0 |

- **唯一缺口 = 2026-06-27 全體共同缺日**（25 active symbols 同缺；單次 ingest 中斷，非 per-symbol 隨機洞）。7d-lookback cron 已無法自癒（已超窗）；一次 `--lookback-days 30` 重跑可補。
- **起點 ≠ 上市日**：2024-06-02 = 部署日 2026-06-02 − 730d lookback；2024-06-10 = 2026-06-10 − 730d。**歷史深度被 lookback_days=730 截斷，非交易所可得性上限**；`--lookback-days` 可覆蓋取更深（Bybit 對上市中 symbol 服務全歷史，`paginate_daily_klines` 支援分頁）。POL 2024-09-05 = 真上市日（MATIC→POL 遷移）。
重跑：`SELECT symbol, MIN(ts)::date, MAX(ts)::date, COUNT(*), (MAX(ts)::date-MIN(ts)::date+1)-COUNT(*) AS missing FROM market.klines WHERE timeframe='1d' GROUP BY symbol ORDER BY 1;` + 缺日定位 SQL 見附錄 R1。

### FACT A3 — Survivorship 判定
- 26-symbol 名單 = `settings/backfill_universe.toml` 固定清單（= 現 roster 25 + TON）。檔內自註：「常見高流動 perp 的初版工程預設……非量化排名……正式啟用前必由 QC/MIT 依 PIT 流動性指標確定 cutoff」。**是，只含現 roster**；在 2026-06-02 前已下架的 symbol 完全不在面板。
- **[HIGH finding / confidence high] 下架歷史不可回補**：`GET /v5/market/kline?category=linear&symbol=TONUSDT&interval=D` → retCode=0, **0 bars**；MATICUSDT 同（2026-07-10 實測，附錄 R2）。TONUSDT 已從 instruments-info 完全消失。⇒ 任何「今天回補出來的 2yr cross-section」都以存活為條件。**緩解庫存**：TON 在庫 744 根 1d + 102,782 根 1m（至 2026-06-15）是僅存的下架樣本；forward daily cron 持續跑 = 從今起的 PIT 無偏面板。
- 量化 attrition 參考：179-symbol 1m 宇宙中僅 **1/179（TON）** 在 ~3 個月內真下架（178 仍 Trading；其餘 feed 停止全是 ingest scope 變更，非下架）。附錄 R3。

### FACT A4 — 1m 能否聚合補歷史/補宇宙
- **補歷史：不能**。1m 留存起點 = **2026-04-05**（16,566,630 rows）——早於此無 1m。
- **補宇宙：部分能（僅 2026-04-05 之後）**。179 symbols 中 **148 個有 ≥60d 的 1m span**（151 個 ≥30d）；其中 ~86 symbols 的 wide-universe ingest 於 **2026-06-15 21:39 同分鐘停止**（n=103,420 齊一）→ 有效 wide 窗 ≈ 2026-04-05→06-15（~71 天）。1d bar 為 UTC 午夜對齊，1m→1d UTC 聚合無歷法障礙。
- **替代路徑**：`intraday_kline_backfill` binary（research-unblock 交付物 A）可對上市中 symbol 用 REST 回補 1m/5m/15m/1h/4h（`--symbols-from-db` / `--start/--end`；apply 預設 vol+turnover-only 保護 OHLC）。1m 90d ≈ 130 pages/symbol；1d 730d = 1 page/symbol。
- **[LOW finding] 精度**：`market.klines` OHLC 欄位為 `real`（f32，~7 位有效數字）——對日級 bps 計算的 majors 足夠；對極小價 symbol（1000PEPE 級）做長鏈條累乘時留意。

---

## (b) 宇宙擴張可行性（只評估，不執行）

### FACT B1 — 現行宇宙規模
`GET /v5/market/instruments-info?category=linear&limit=1000`（2026-07-10）：單頁 721 linear instruments、無 nextPageCursor；其中 **USDT 結尾且 status=Trading = 617**。top-50/100 選集空間充足。

### FACT B2 — 上架/下架歷史清單：**庫內無**
- `research.listing_capture_events` = **0 rows**（部署 5 週零捕捉，與 memory 一致）。
- 無任何 instruments/listing 歷史表。instruments-info 只反映**當前**狀態（下架即消失，無 tombstone）。
- 既有 forward 基建：`bybit_announcement_sentinel.py`（`GET /v5/announcements/index`，public 無 auth，cron 每 30min `7,37 * * * *`，2026-06-11 起）= 上/下架**事件級** forward 捕捉面已存在（API 手冊 line 1127-1146）。
- ⇒ 歷史下架名單要靠外部來源（announcements 歷史頁 / 第三方存檔），**不屬 $0 庫內可得**；forward 從 sentinel + daily backfill 累積。

### FACT B3 — 「176-symbol 1m×3mo」定位
= `market.klines` timeframe='1m'：**179 symbols / 16,566,630 rows / 2026-04-05 → now**。145 symbols 自 2026-04-05（留存起點）起有數據；34 個為其後新增（新上市/scope 加入）。140/179 的 feed 現已 stale >24h（86 個同停 2026-06-15 21:39 = scope 縮編；其餘散停），僅 ~39 活躍更新。

### FACT B4 — AEG backfill $0 擴張機制（改動面初估，不執行）
- **機制已在**：Rust `daily_kline_backfill` binary（`rust/openclaw_engine/src/bin/daily_kline_backfill.rs`）+ `settings/backfill_universe.toml`（category=linear, lookback_days=730, symbols=26）+ daily cron（`helper_scripts/cron/daily_kline_backfill_cron.sh`, 05:29, lookback 7d, ON CONFLICT 冪等）。provenance 帳本 `research.alpha_klines_provenance`（1,272 rows，最新 run 2026-07-10 05:29 全 pass）。
- **擴張改動面 = 純配置**：TOML symbols 名單擴到 top-50/100 + 一次 `--apply` 歷史回填（operator-gated：`--apply --i-understand-this-modifies-db` 或 `OPENCLAW_DAILY_KLINE_BACKFILL_APPLY=1`）。無代碼變更。此後 daily cron 自動維護新名單。
- **成本算術**：1d × 730d = 730 bars < 1000/page ⇒ **1 request/symbol**；top-100 ≈ 100 sequential requests（binary 內建 per-symbol 防 burst），$0、分鐘級。深歷史（>730d）同樣 $0（多一頁/symbol）。
- **前置待決（TOML 自註 + 本盤點確認）**：top-N 選集的 liquidity cutoff（24h turnover / OI / 上市時長 / tick size）**尚未經 QC/MIT 量化定義**——這是擴張前唯一實質工作項。
- **結構性限制（承 A3）**：擴張所得歷史仍為 survivor-conditioned；擴張的價值主張裡「回溯 2yr 檢驗」與「forward PIT 累積」需分開計。

---

## (c) 成本模型輸入

### FACT C1 — slippage 實測分位（我們的 size 下）
檔名澄清：**不存在 `slippage_quantiles_latest.json`**；權威 artifact = `docs/CCAgentWorkSpace/E1/workspace/reports/2026-07-10--counterfactual_rerun_evidence/slippage_quantiles_v2_input.json`（schema `cost_gate_slippage_quantile_artifact_v2`，asof 2026-07-10T01:39Z，window 90d，生成器 `helper_scripts/research/cost_gate_learning_lane/slippage_quantile_artifact.py`）。

Global（n=2,531 fills）：

| 指標 | bps |
|---|---|
| q50 | 3.00 |
| q75 | 12.58 |
| q90 | 34.75 |
| mean_abs (E\|slip\|) | 17.90 |
| mean_signed | −2.45 |
| CVaR90 | 126.68 |

Roster alt cells（n≥30 者摘錄，mean_abs / q50 / q90 bps）：ADA 24.7/0/31.3 (n=37)、APT 18.7/12.4/45.6 (n=50)、ARB 14.4/5.6/31.6 (n=78)、ATOM 9.7/7.2/22.6 (n=67)、AVAX 13.0/4.7/25.8 (n=56)、DOGE 8.1/1.0/16.7 (n=36)、DOT 15.5/7.6/37.4 (n=66)、ETC 17.2/11.0/43.1 (n=41)、FIL 21.6/12.4/51.0 (n=64)、ICP 45.9/27.3/110.5 (n=34)、INJ 20.0/11.6/41.6 (n=49)、LINK 8.7/4.6/25.9 (n=48)、LTC 17.2/7.9/50.2 (n=30)、NEAR 10.5/6.4/21.3 (n=85)、OP 10.4/6.4/24.2 (n=78)、SUI 8.4/2.7/19.6 (n=87)、XRP 7.1/1.0/23.3 (n=80)。BTC 2.6/0.4/1.2 (n=113)、ETH 5.2/0.7/3.7 (n=213)。
- **[INFO] 樣本狀態**：僅 BTC/ETH/TON `thin_sample=false`；全部 alt cells thin → per-cell 分位噪音大，研究用 global/pooled-alt 分位為宜。
- **[INFO] 保守紀律**：mean_signed=−2.45（signed 平均略有利）**不得**當成本抵扣（硬約束 4）；且承 07-09 教訓：E[slip] 入 gate、tail（q90/CVaR90）入 CVaR 預算，兩軌分離。

### FACT C2 — 23bps/RT 上界對多日持有的攤提算術
以 taker RT 成本上界 23 bps（= 2×5.5 fee + 2×~6 slip，與 roster-alt q50 量級一致；prior 19–23bps 之上端）：

| 持有天數 | 單腿 RT 攤提 (bps/day) | L/S 雙腿（46bps/RT pair）攤提 (bps/day) |
|---|---|---|
| 1d | 23.0 | 46.0 |
| 3d | 7.67 | 15.3 |
| 5d | **4.60** | **9.20** |
| 7d | 3.29 | 6.57 |

- Tail 版（用 mean_abs 17.9 代 E|slip|）：單腿 RT ≈ 2×5.5+2×17.9 ≈ 46.8 bps → 5d 攤提 9.4 bps/day/腿——此為 CVaR 預算軌，非期望軌。
- 在 X = 「日級信號、5d 持有、taker 進出、L/S 成對」假設下，pair-level 毛 edge 需 >9.2 bps/day 才過期望成本線（不含 funding，funding 見 (e)）；此為算術非裁決。

---

## (d) 執行面現狀盤點（多日持有支援）

### FACT D1 — 風控層：多日持有無硬阻擋
- Time stop：`rust/openclaw_engine/src/risk_checks.rs:389` `max_hours = limits.holding_hours_max * rm.time` → `RiskAction::ClosePosition("TIME STOP ...")`。demo SSOT `settings/risk_control_rules/risk_config_demo.toml:22` `holding_hours_max = 168.0`（**7 天**）。regime multiplier `rm.time` 可向下收縮有效上限（數值依 regime 狀態）。
- `min_hold_ms = 120000`（demo toml:189，2 分鐘）對日級無約束。
- 多日前例：funding_arb per-strategy `max_hold_ms` default **72h**（`strategies/strategy_params.rs:825-861`）。

### FACT D2 — funding 結算處理：已有記帳
`trading.funding_settlements`（exec feed 落帳，含 symbol/side/amount/strategy_name/engine_mode）：demo 225 rows / 32 symbols / 2026-04-28→07-10；live_demo 54 rows / 26 symbols / →06-12。⇒ 持倉跨結算的 funding 現金流已被系統記帳，非盲區。

### FACT D3 — 隔夜/跨日風控面
24/7 市場無「隔夜」概念；適用的是 `session_drawdown_max_pct=25.0`、`daily_loss_max_pct=15.0` + halt 階梯（daily_loss_cautious/reduced/circuit 5/10/14%）與 `daily_loss_halt_ttl_ms=86400000`（24h）。**未追蹤項（open question）**：多日在倉部位與 daily-loss halt 的交互（halt 期間持倉是否被強平/僅禁新倉）本盤點未逐路徑核實。

### FACT D4 — 1d 數據面：KlineManager 無 1d buffer，但有 DB 直讀前例
- `DEFAULT_TIMEFRAMES = 1m/5m/15m/1h/4h`，**不含 "1d"**（`event_consumer/bootstrap.rs:988` 註解明示；WS 訂閱 `kline.1.{sym}` 起步，`multi_interval_topics.rs` 至 4h）。對不存在的 "1d" buffer 呼叫 `seed_bars` 曾是 silent no-op（FLASH-DIP-SEED-FIX 教訓）。
- **前例**：flash_dip_buy boot 時直接 `SELECT` `market.klines` 1d 最後收盤 close（2 日 staleness fail-safe，DB 過期當日 inert）——日級 lane 的 feature 來源可循此 DB-read 模式，不必動 KlineManager。
- Exit-feature 路徑現為 1m-ATR 基準（唯一 `get_ohlcv("1m")` call site）——日級 lane 的動態 SL/TP 尺度若需 daily-ATR 屬設計題，非本盤點範圍。

### FACT D5 — 加一條日級 lane 的改動面初估（只盤點）
| 面 | 現狀 | 改動量級 |
|---|---|---|
| 信號/feature 來源 | market.klines 1d 在庫 + daily cron 維護 + flash_dip DB-read 前例 | 小（複用模式） |
| 持有期風控 | holding_hours_max=168h 已容 5d；per-strategy max_hold 參數模式已有 | 近零（config） |
| funding 記帳 | funding_settlements 已落帳 | 零 |
| 出場尺度 | 現 1m-ATR；daily-ATR 需新路徑 | 中（設計題） |
| 宇宙接線 | `event_consumer/types.rs:25` SYMBOLS 常量=5（BTC/ETH/SOL/XRP/DOGE）；roster 25 走 per-strategy config——日級 lane 若用擴張宇宙（top-50/100），訂閱/tick 接線面**未逐條追蹤** | 未定（open question） |
| halt 交互 | D3 未追蹤項 | 未定（open question） |

---

## (e) Funding drag（短腿多日持有，funding panel 實數）

### FACT E1 — 數據源與覆蓋
`market.funding_rates`（4,907 rows / 26 symbols）：多數 symbol 自 **2026-05-11**（176 settlements，2.93/day ≈ 8h interval）；BTC/ETH/DOGE/SOL/XRP 自 2026-04-05；POL/TON 5.77/day（4h interval）。**覆蓋警示**：DOGE/SOL/XRP 僅 1.97 settles/day（應 ~3）= settlement 行有 ingest 缺洞。`panel.funding_rates_panel`（512,096 rows / 25 symbols）僅 2026-06-25 起（快照面）。**2yr funding 史不在庫**（`research.alpha_funding_rates_history` = 0 rows；WP-B.4 的 2yr×20 majors 是 ad-hoc REST 拉取未落庫）。REST `/v5/market/funding/history` $0 可補：2yr×3/day ≈ 2,190 行 ≈ 11 pages/symbol。

### FACT E2 — per-symbol funding 實數（窗 2026-05-11→07-10 為主；**regime-specific，bull/flat 窗標註**）
符號約定：F>0 → long 付 short（short 腿收錢）。mean_daily_bps = 平均每日 funding（bps/day，正 = short 收）：

| 分佈統計（26 symbols） | bps/day |
|---|---|
| 中位數 | **+0.35** |
| 平均（含 TON 尾） | −0.23 |
| 平均（ex-TON 25 syms） | +0.06 |
| 最大（SUI） | +1.40 |
| 最小 active（TRX） | **−4.01** |
| TON（下架前，參考） | −7.36 |

負 funding 尾（short 腿要付）：TRX −4.01（69.3% settlements 為負）、INJ −1.67、BCH −1.62、ATOM −1.20、XRP −0.19、SOL −0.09。其餘 19 active symbols 為正（short 腿收）。全表 SQL 見附錄 R4。

### FACT E3 — 5d 短腿持有的 funding 期望算術
- 典型正 funding alt（中位數 +0.35 bps/day）：5d short = **收 ~+1.7 bps**（等值地：long 腿付 ~1.7 bps）。
- 負 funding 尾：short TRX 5d ≈ **付 −20 bps**；INJ/BCH/ATOM 5d ≈ 付 −6 至 −8 bps。
- ⇒ 對 cross-sectional L/S 籃：cross-section 中位數下兩腿 funding 大致對消（±2 bps/5d 量級），但**短腿落在負-funding symbol 上時 funding drag 可達成本模型同量級（−20bps/5d ≈ 攤提後 4 bps/day）**——per-symbol funding 必須入成本模型而非平均化。
- **條件聲明**：以上僅在「2026-05/07 窗的 funding 分佈延續」假設下成立；此窗 25-symbol 宇宙 funding 貼 IR floor（承 07-09 EXT 掃描），牛市 premium 窗會系統性上移。

---

## Findings 匯總（全量，severity + confidence）

| # | Severity | Confidence | Finding |
|---|---|---|---|
| F1 | HIGH | high | 下架 symbol 歷史不可從 Bybit REST 回補（TON/MATIC 0 bars）→ 今日回補的 2yr 面板必為 survivor-conditioned；forward PIT 累積是唯一無偏路徑 |
| F2 | MEDIUM | high | 1d universe = 固定 26 名單、非量化選集（TOML 自註待 QC/MIT cutoff）；擴張前唯一實質工作項 = 定義 PIT liquidity cutoff |
| F3 | MEDIUM | high | 1d 歷史被 lookback=730d 截斷（非上市日）；--lookback-days 可加深 |
| F4 | MEDIUM | medium | 2yr funding 史不在庫；in-DB funding 僅 ~60-96d × 26 syms 且 DOGE/SOL/XRP 有 settlement 缺洞 → 日級研究的 funding 成本項需先 REST 回補 |
| F5 | MEDIUM | medium | 日級 lane 改動面兩項未追蹤：多日持倉 × daily-loss halt 交互；擴張宇宙的訂閱/tick 接線面 |
| F6 | LOW | high | 1d 面板全體共同缺 2026-06-27 一天（已超 7d cron 自癒窗，需一次 lookback≥30d 重跑補洞） |
| F7 | LOW | high | market.klines OHLC 為 f32；極小價 symbol 長鏈計算留意精度 |
| F8 | INFO | high | slippage artifact 除 BTC/ETH/TON 外全 thin_sample；per-cell 分位噪音大 |
| F9 | INFO | high | mean_signed −2.45 bps 不得當成本抵扣（保守紀律）；E[slip] 與 tail 雙軌分離 |
| F10 | INFO | high | 1m wide-universe 窗（~150 syms）僅 2026-04-05→06-15 有效；可橫向擴 cross-section 不能縱向補歷史；intraday_kline_backfill 可 REST 補上市中 symbol |
| F11 | INFO | high | announcement sentinel（30min cron）已是 forward 上/下架事件捕捉面；listing_capture_events 0 rows 為既知 |

**假陽性候選**：F6 的「2026-06-27 缺日」有極小可能是 Bybit 端該日無 bar（判斷依據：25 symbols 同缺 + 前後日皆在 → ingest 中斷遠更可能；重跑 backfill 即可判別）。

## 附錄 R — 可重跑命令
- R1 缺日定位：`WITH d AS (SELECT generate_series('2024-06-02'::date,'2026-07-09'::date,'1 day')::date AS day), have AS (SELECT symbol, ts::date AS day FROM market.klines WHERE timeframe='1d') SELECT h.symbol, d.day FROM (SELECT DISTINCT symbol FROM have) h CROSS JOIN d LEFT JOIN have ON have.symbol=h.symbol AND have.day=d.day WHERE have.day IS NULL AND d.day BETWEEN (SELECT MIN(day) FROM have WHERE symbol=h.symbol) AND (SELECT MAX(day) FROM have WHERE symbol=h.symbol);`
- R2 下架回補測試：`curl -s "https://api.bybit.com/v5/market/kline?category=linear&symbol=TONUSDT&interval=D&limit=5"`（retCode 0、list 空）；MATICUSDT 同。
- R3 attrition：`SELECT symbol FROM market.klines WHERE timeframe='1m' GROUP BY symbol;` 對比 `curl -s "https://api.bybit.com/v5/market/instruments-info?category=linear&limit=1000"` USDT+Trading 集合 → 差集 = {TONUSDT}。
- R4 funding 表：`SELECT symbol, COUNT(*), MIN(ts)::date, MAX(ts)::date, ROUND((COUNT(*)::numeric/GREATEST(MAX(ts)::date-MIN(ts)::date,1)),2) AS settles_per_day, ROUND(AVG(funding_rate)::numeric*10000,3) AS mean_F_bps, ROUND(AVG(funding_rate)::numeric*10000*(COUNT(*)::numeric/GREATEST(MAX(ts)::date-MIN(ts)::date,1)),3) AS mean_daily_bps, ROUND(100.0*SUM(CASE WHEN funding_rate<0 THEN 1 ELSE 0 END)/COUNT(*),1) AS pct_neg FROM market.funding_rates GROUP BY symbol ORDER BY symbol;`
- R5 slippage artifact：`docs/CCAgentWorkSpace/E1/workspace/reports/2026-07-10--counterfactual_rerun_evidence/slippage_quantiles_v2_input.json`
- 檔案座標：backfill binary `rust/openclaw_engine/src/bin/daily_kline_backfill.rs`；universe `settings/backfill_universe.toml`；cron `helper_scripts/cron/daily_kline_backfill_cron.sh`；intraday `rust/openclaw_engine/src/bin/intraday_kline_backfill.rs`；time stop `rust/openclaw_engine/src/risk_checks.rs:389`；1d-buffer 註解 `rust/openclaw_engine/src/event_consumer/bootstrap.rs:988`。

---
*QC/MIT 取數員 · 2026-07-10 · 本報告為證據盤點，不含策略設計或 GO/NO-GO 裁決；下游設計工作應引用本報告的 FACT 編號。*
