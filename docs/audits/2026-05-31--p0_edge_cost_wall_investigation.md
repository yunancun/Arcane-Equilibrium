# P0-EDGE-1 成本牆調查匯報

| 項目 | 內容 |
|------|------|
| 日期 | 2026-05-31 |
| 觸發 | 對照 v5.8 執行計劃 audit 現有進度；P0-EDGE-1（系統缺 net-positive edge）已 OPEN 6+ 週，逐個 alpha 候選失敗，需查清根因與最快路徑 |
| 範圍 | v5.8 模組進度、alpha 候選池（textbook + A1/A2/A3 + oi_delta + 多日 trend + listing fade）、成本結構、Bybit funding 機制 |
| 方法 | 多角色獨立審計（PA/QC/FA）+ 5 個 MIT read-only PG 診斷 + QC 成本牆量化 + BB Bybit 官方 API 查證；全程 read-only，0 下單 / 0 部署 / 0 runtime 改動 |
| 結論等級 | ★★ 根因確認：兩道結構性 binding constraint（成本牆 + 資料深度）；net-positive edge 可達但路徑窄；最快路徑已識別 |

---

## 摘要

6 週、4 個 alpha 候選、4 個 textbook 策略全部失敗，**不是 4 個獨立問題，是同一條經濟學定律的反覆顯影**。根因是兩道結構性約束：**① 成本牆**——我們測的訊號 gross edge 量級（1-3 bps）打不過 Bybit 零售交易成本量級（11-27 bps）；**② 資料深度**——內部 klines 僅累積 56 天，使得能翻過成本牆的兩類 alpha 都缺樣本。問題不在「找不到訊號」（oi_delta 的訊號真實且 leak-free），在「訊號的 edge 量級不足以扛成本」。net-positive edge 在現有約束下**可達但路徑窄**，且最快路徑（回填歷史 klines → 測多日 trend）已識別。

---

## 一、檢查了什麼

| # | 檢查 | 執行 | 性質 |
|---|------|------|------|
| 1 | v5.8 模組 IMPL 真實狀態 + 排程 drift | PA | 源碼審計 |
| 2 | P0-EDGE-1 alpha 可行性 + 候選管線是否枯竭 | QC | 量化審計 |
| 3 | v5.8 → 現實功能性 Gap + 帳本 drift | FA | 規格審計 |
| 4 | A1 funding >30% 觸發頻率（events/yr） | MIT | PG read-only |
| 5 | R-1a oi_delta cross-sectional alpha probe | MIT + QC | PG + 先驗 cross-verify |
| 6 | R-2a listing pump-dump fade 資料可行性 | MIT | PG read-only |
| 7 | R-2b 多日 perp trend（TSMOM）診斷 | MIT | PG read-only |
| 8 | 成本牆量化 + alpha-class 地圖 | QC | 微結構分析 |
| 9 | Bybit 正側 funding 結構 cap 查證 | BB | Bybit 官方 API + 文件 |

---

## 二、發現

### 2.1 兩道 binding constraint

**① 成本牆（不可協商，由 Bybit fee + crypto 流動性決定）**

| 執行模式 | net-clear 最小 gross edge |
|----------|---------------------------|
| BTC/ETH taker | ~15 bps |
| Top-10 alt taker | ~20 bps |
| Mid-cap alt taker | ~35 bps |
| Maker（fill 100% 假設） | ~6-8 bps（但需 fill≥60% + adverse<3.5bps；A2 實證 49% 不可達） |

VIP tier 對 $10k 是 chicken-and-egg 死局（需 ~$10M+/月成交量），成本鎖死 VIP0（taker 5.5bps/leg、maker 2bps/leg）。

**② 資料深度**：klines 僅累積 ~56 天（collector onset 2026-04-05，非 retention 上限——retention 實為 365d）。多日策略在 56d 內只有 ~8 個獨立週期，無法 robust 驗證。

### 2.2 候選結果

| 候選 | Verdict | 失敗層次 | 關鍵證據 |
|------|---------|----------|----------|
| 4 textbook（ma/bb_breakout/bb_reversion/grid） | reject | 成本 + SNR | demo runtime −11~−42 bps |
| A1 funding_short_v2 | **regime-dormant**（非永久死，見 2.4） | 當前低-premium regime + 160% break-even 設計 | >30% funding 56d 觸發 0 次；max +10.95% APR（IR floor） |
| A2 liquidation cascade fade | reject | 執行可達性 | maker-fill 49%<50%；R:R<1；avg_net −2.45bps |
| A3 BTC/ETH pairs | reject | 統計（不協整） | corr 0.53；half-life 4110 bars；avg_net −24bps |
| R-1a oi_delta cross-sectional | reject（standalone）→ 留作 ensemble feature | **成本（非資訊）** | 訊號真實 leak-free（n=80393，shift(1) 對照證實）；gross 1.9-2.9bps ≪ 成本 |
| R-2a listing pump-dump fade | observe_more（不可診斷） | 資料覆蓋 | 權威 listing SoT 有 52 新上市，但 0 個被 klines 捕捉到上市瞬間 |
| R-2b 多日 perp trend | observe_more（機制已驗，edge 未測） | 樣本/歷史深度 | gross multi-day move 389-1213bps，成本僅占 3-4%（成本牆逃逸機制 VALIDATED）；但 56d 僅 ~8 獨立週期 |

### 2.3 兩條成本牆逃逸路（唯二在成本牆正確一側的 alpha class）

- **① 事件驅動大 move（listing pump fade）**：單次 move 500-1500bps，成本占比<5%。機制最高機率（QC ~50-65%）。**但當前不可診斷**——collector 用 $50M 24h turnover hard filter，新上市 turnover≈0 過不了 filter，等漲到 $50M 才被訂閱、pump 已過（根因 grep 自證）。需改 collector 在 `listed_at` 訂閱 + ~5-6mo 累積（~Q4 可測）。
- **② 低 turnover 多日 perp**（QC ~40-55%）：成本攤薄機制**已驗**。**可由回填 ≥12-18mo 歷史日線/4h klines 快速 unblock**（Bybit 公開市場資料、no-auth、ADR 不觸發、~125 requests≈幾分鐘）→ **數天內可出 edge 定論**，比 listing fade（~Q4）快得多。

### 2.4 治理發現（審計過程中查出的記錄問題）

1. **funding_short_v2「永久結構性 NO-GO」結論的理由被否證**：平行 session audit（`2026-05-31--funding_short_v2_structural_infeasibility.md`）稱 Bybit 正側 funding「結構封頂 +10.9% APR」。BB 實際 curl `api.bybit.com` 查證 = **過度詮釋**：真實 per-symbol 正側 cap = `instruments-info.upperFundingRate`（BTC/SOL +547% APR、PEPE +1095%、WIF +2190%），比宣稱值高 50-200×；+0.0001 是 funding 公式 IR baseline（floor）非 cap；2024-11 bull 窗 PEPE 69% 結算破 30% APR。→ funding_short_v2 是 **regime-dormant 低頻策略**，真 viability 問題是 **160% APR break-even 門檻過高**（QC 設計範疇），非交易所結構 cap。該 audit 的 3 個程序修復 + basis 修正 + no-clamp 驗證**仍正確有效**。已加 erratum。
2. **V### schema 編號雙佔（BLOCKER 級）**：v5.8 §9 把 V113 分給 M7 decay，但真實 `V113` 是 P0-OPS-4 pg_dump（已 applied）；V104/V114/V115 同樣被 LG-3/Packet C/basis 佔用。真實 `sql/migrations/` head=V115，非 §9 寫的 V098。M7 改用 free 的 V116，模組 reserve 改 V118-124。
3. **M1 LAL「feature-live」標籤誇大**：`governance/lal/mod.rs` 565 LOC 但 0 runtime caller，Tier 2/3/4 全 `unimplemented!()`。實際為 PARTIAL-IMPL（孤立未接線）。

---

## 三、結論

1. **根因 = 成本牆 + 資料深度兩道結構性約束，非訊號缺失。** oi_delta 證明資訊層常常活著（真實 leak-free 訊號），是經濟層（成本）殺死它。翻牆只能把分子做大（事件驅動大 move）或分母做小（低 turnover 多日）。

2. **net-positive edge 在 $10k + Bybit + 無付費 feed + demo 無 spot lending 約束下可達但路徑窄。** 最快可信路徑 = **回填歷史 klines → 測多日 trend**（成本牆逃逸機制已驗，數天可出 edge 定論）；中期 = listing capture（~Q4）+ multi-factor ensemble（3-4 月）。誠實 ETA：real-profit harvest 數週到數月，gated on 資料累積。

3. **funding_short_v2「永久結構不可行」結論被否證** = regime-dormant + break-even 設計問題（BB 查證）。可由代碼處理（low-turnover 多結算 carry 攤薄 break-even），但 demo 上會變 directional regime bet，非乾淨市場中性 carry。

4. **戰略決策已定（operator 2026-05-31 拍板）**：
   - 凍結 autonomy 13 模組 active-IMPL（保留 DESIGN/schema/stub），解凍 gate = 首個 net-positive candidate 達 stage0_ready；
   - 主力轉系統性 alpha-source 主線；M7 decay detector 唯一例外（V116 spec done，E1 按住等首個 alpha）；
   - Sprint 4 走 LiveDemo 降級（驗 live 管線可靠性而不需 edge）；
   - 現有約束內走窄路、目標仍真盈利。

---

## 四、後續

工程安排（waves/sprints/work-chains/acceptance/parallelism）由 PA 基於 QC 解決方案研究提議撰寫，經 PM 兩次簽收後 land 為 dispatch packet；TODO 同步重整。三個 E1-ready spec 已就緒：歷史 kline backfill（最快路）、collector listing-capture（~Q4）、M7 V116 detector（按住）。

---

## 附錄：證據與可復現

- **sub-agent 報告**：QC 成本牆地圖 / A2 LCS fade 評估 / strategy_verification_v3（QC workspace）；多日 trend + listing feasibility 診斷（MIT workspace `2026-05-31--*`）。
- **spec**：`docs/execution_plan/specs/2026-05-31--{historical-kline-backfill,collector-listing-capture,v116-m7-decay-detector}-spec.md`。
- **funding-cap 查證**：BB curl `api.bybit.com/v5/market/instruments-info?category=linear&symbol=<SYM>`（upperFundingRate 欄位）+ `/v5/market/funding/history`（2024 bull 窗反例）；公式見 `docs/references/2026-04-04--bybit_api_reference.md` funding 段。
- **被否證的 audit**：`docs/audits/2026-05-31--funding_short_v2_structural_infeasibility.md`（已加 erratum 指向本文）。
- **戰略決策記錄**：`TODO.md` v92（commit `3a7c4853`）。
- **PG 診斷方法**：`docker exec trading_postgres psql -U trading_admin -d trading_ai`（非互動 ssh `DATABASE_URL` 空）；migration head 115；全程純讀。
