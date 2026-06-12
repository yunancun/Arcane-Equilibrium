# Polymarket 數據軸移植 — QC 紀律 memo · 2026-06-11

判定:PROCEED(定位=離線研究數據採集,artifact-only;非策略提案,本 memo 不含任何 edge 聲明)
移植源:/tmp/repo-eval/last30days-skill/skills/last30days/scripts/lib/polymarket.py(786 行,MIT,Gamma API 免費無 auth)
背景:FinceptTerminal 評估(2026-06-04)列為值得項;operator 2026-06-11 拍板。
(本檔由 PM 代落檔;內容=QC agent 原文,僅此註記行為 PM 添加)

## 0. 定位鐵則(進任何下游前先讀本節)
1. CLAUDE.md「Alpha Evidence Governance」:prediction-market 賠率 = **corroborating context only**——不可作主信號、不可 override 失敗的量化 gate、不可直驅交易。
2. 本軸產出 = 研究 artifact。任何由此衍生的策略想法進交易鏈前必走完整三段鏈:`quant-strategy-design`(alpha 8 來源歸類)→ `math-model-audit` → `walk-forward-validation-protocol`,再過既有 Stage0R/demo promotion gate。無捷徑。
3. Polymarket 價格 = 另一群交易者的聚合 posterior,有自身 microstructure(流動性薄、大戶主導、長 horizon 市場含 time-value 折價)。它是 feature 候選/regime 佐證,**本身不是 alpha 證明**。
4. 不在 Polymarket 交易(Bybit 唯一執行所,Product Boundary);CLOB 下單/auth 類 endpoint 全程不碰。

## 1. 移植取捨(對 786 行源碼)
- **保留**:HTTP 層、`_parse_outcome_prices`(outcomes/outcomePrices 雙層 JSON-encoded 解析)、`_safe_float`、closed/active 判別、欄位讀取。
- **丟棄**:`relevance` 評分、`_compute_text_similarity`、`_MIN_RELEVANCE` 截斷、`RESULT_CAP`、`_shorten_question` 等搜索-UX 邏輯。理由:採集端 ranking/截斷 = 不可逆選擇偏差;研究數據要 raw 全量。
- **端點換主**:lib 只包 `/public-search`(每頁 5 events、ranking 不確定、limit 為 no-op)。採集器主路改 Gamma `GET /events` deterministic 枚舉(官方參數含 `tag_id/tag_slug/closed/limit/offset/volume_min/end_date_min...`),crypto tag 枚舉+分頁;`/public-search` keyword 僅作補充發現面。E1 移植時對官方文檔逐參數核對。

## 2. 採集 spec
**查詢集 v1**(版本號寫進 manifest;改集合=升版,不回溯重算):
- tag 枚舉:crypto(主)。keyword 補充:bitcoin, btc, ethereum, eth, solana, xrp, "bitcoin price", "all time high", etf, blackrock, grayscale, sec, cftc, stablecoin, regulation, "bitcoin reserve", fed, fomc, "rate cut", inflation, cpi, recession, tether, binance, coinbase。

**欄位最小集**(market-level 一行/每 snapshot;event 欄位攤平):
`snapshot_ts_utc`(採集時戳)、`event_id/slug/title/tags`、`market_id/question`、`outcomes[]/outcome_prices[]`、`volume24hr/volume1wk/volume1mo`、`liquidity`、`competitive`、`end_date`、`closed/active`、`oneDay/oneWeek/oneMonthPriceChange`、`updatedAt`、`query_set_version`、`collector_git_sha`;另存 `raw` 原始 JSON(schema 漂移時 fail-soft 保底)。

**point-in-time 紀律**(鐵則,呼應 leak-free feature 原則):
- append-only:每次採集 = 新 run dir;**禁回填、禁覆寫舊 snapshot**。補抓另開 run 標 `retrospective=true`。
- 重建「當時知道什麼」:研究 join 只允許 `snapshot_ts ≤ t` 的行。`volume/liquidity/priceChange` 是 as-of 查詢時刻值、官方無歷史可回補——snapshot 是這些欄位唯一來源,丟一天少一天。
- **track-to-resolution**:已見過的 market 即使 closed 也續抓至 resolution,記最終結算結果。lib 預設 skip closed(搜索 UX)——採集器必須反向,否則 calibration/事後研究帶 survivorship bias。
- 採集端最小過濾:只按查詢集圈範圍,不做 relevance 截斷;雜訊留研究端過濾(filter 是代碼可改版,raw 過去不可再生)。

**頻率**:
- baseline = daily 全量 sweep(固定 UTC 時刻 cron,與 residual producer 03:17 同型錯峰)。
- 加密 = hourly 僅對 top-N(volume 排序,N≈30-50)crypto markets。理由:lead-lag 假說(本軸最有價值用途)在 daily-only 下 horizon<1d 全不可測;hourly 成本可忽略。
- 事件窗(FOMC/ETF deadline)手動加密為可選,非必須。
- rate limit:上游稱 15K req/10s,非約束;仍設 client-side throttle(≤2-5 req/s)+ retry/backoff——保守假設、禮貌採集。

**歷史回補(分道,不污染 snapshot lane)**:CLOB `GET /prices-history`(`market=<clob_token_id>&interval&fidelity` 分鐘級)可免費拉 odds 歷史序列。已知限制:resolved/closed 市場僅 ≥12h 粒度、部分 token 空回應。允許用,但存**獨立 artifact lane** 標 `retrospective`+拉取日;永不混入 snapshot lane 充當「當時採集」。

## 3. 存儲形(對齊 aeg_s3 / gate_b 慣例)
- 代碼:`helper_scripts/research/polymarket_axis/`;R-0 同款紅線:不 import 生產模組、零 auth、零 order、零 PG write;新增腳本更新 `helper_scripts/SCRIPT_INDEX.md`。
- artifact:`${OPENCLAW_DATA_DIR:-/tmp/openclaw}/polymarket_axis_runs/<run_id>/`:`snapshots.jsonl`(market-level 行)+ `manifest.json`(schema_version/run_id/created_at_utc/created_by_role/git_sha/git_dirty/runtime_host/query_set_version/point_in_time=true/sha256 artifact index——照 aeg_s3 `artifact.py::write_all` 形)+ 可選 duckdb parquet 鏡像(缺套件 skip 不阻斷,照 gate_b `mirror_jsonl_to_parquet`)。
- 不進 PG、不進 runtime、不接 engine/conductor/signal bus;唯一消費者 = 離線研究腳本。cron 排程與活化 = operator 決策(本 memo 只定 spec)。

## 4. 研究假說清單(數據先積累,假說後驗;全部 corroborating/feature-candidate 定位)
| # | 假說 | 最小樣本窗 | 備註 |
|---|---|---|---|
| H4* | crypto 市場 calibration:resolved 結果 vs 賠率(Brier/calibration curve) | resolved n≥50(~3-6mo;BTC 週/月度市場結算頻) | **前置 gate:calibration 差→全軸永久降級 context-only** |
| H1 | 賠率劇變(abs Δp≥5pp/24h)vs BTC/ETH 永續 lead-lag(±1-48h) | hourly top-N 90d,事件 n≥30 | daily-only 不可測,故需 hourly lane |
| H2 | 監管/ETF 事件市場定價 vs funding regime 切換 | 6-12mo,事件 n≥10 | 低頻,learning-only |
| H3 | 宏觀市場(Fed cut 機率)Δ vs crypto realized vol/funding 日級關聯 | daily 180d(~180 obs) | |
| H5 | volume/competitive 結構(crowd attention proxy)vs 次日 realized vol/turnover | daily 90-180d | |

驗證紀律:leak-free join(`snapshot_ts ≤ t`)、≥3 假說同測必 Bonferroni、單信號 IC<0.02 即棄、OOS 在 demo lane;任何「顯著」結論回 §0 三段鏈,不直通交易。

## 5. 不做清單
- 不接 Kalshi(另軸另議,勿在本移植夾帶)。
- 不做實時 WS/stream(daily+hourly 拉取即可)。
- 不輸出交易信號、不接 signal bus、不餵 edge_estimates。
- 不碰 CLOB 下單/auth 類 endpoint;不在 Polymarket 開倉。
- 採集端不做 LLM 解讀(deterministic 採集;解讀屬研究端)。
- 不寫 PG、不動 runtime config、不改 engine。

## 6. 成本與風險注記
- 成本:工程 ~1 E1 session;運行 = cron + 數 MB/day(遠低 rate limit)。交易風險 0(read-only 公共 API)。
- 數據風險:Gamma 無 SLA,schema 可漂移 → manifest 記 schema_version、解析 fail-soft 存 raw;`/prices-history` 對 resolved 市場粒度劣化(≥12h)是已知坑,研究端勿假設細粒度可事後補。
- 方法論最大風險 = 把賠率當 oracle。釘死:H4 calibration 不過,H1-H3「賠率=資訊」前提自動弱化;本軸永遠不豁免量化 gate。

— QC,2026-06-11

Sources:
- https://docs.polymarket.com/developers/gamma-markets-api/get-events
- https://docs.polymarket.com/developers/CLOB/timeseries
- https://github.com/Polymarket/py-clob-client/issues/216
