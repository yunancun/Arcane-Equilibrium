---
name: project_2026_06_02_aeg_trend_listing_infra_deployed
description: 2026-06-02 AEG alpha-source 研究基礎設施部署——V125 alpha 儲存 + 日線回填(多日 trend 資料源) + Gate-B 隔離 listing 探針；本身不產 alpha，是研究資料/驗證層
metadata:
  node_type: memory
  type: project
  originSessionId: 07386332-55ba-43c0-a468-02f0f16dd863
---

承 [[project_2026_05_31_v58_alpha_pivot]] 的 alpha-source 研究方向（6 週 textbook 策略死於 edge<成本，翻牆只剩事件驅動大 move / 低 turnover 多日 perp 兩條路）。operator 指示「並行做多日trend和listing + 清理資料庫」。2026-06-02 部署（commits 0f19c861 / e3233647[V126 見 [[project_2026_06_01_db_schema_hygiene_cleanup]]] / eae0b890 / c1c017b0，三端同步 Mac=origin=Linux）。

**V125 alpha-history 儲存（migration，applied max version 126）**：6 張 `research.alpha_*` 表（3 hypertable，chunk 7d/compress 30d segmentby=symbol/retain 1095d）+ `market.klines` retention 365→1095d。funding_rate/open_interest/buy_ratio/sell_ratio 全 `DOUBLE PRECISION NOT NULL`（C-3 不容 fake-zero/NULL）。**§E reflection 修正**（TSDB 2.26.1 無 `compression_settings.segmentby` 欄→改 `segmentby_column_index IS NOT NULL` EXISTS；原寫法 deploy crash-loop，MIT Linux dry-run 兩度把關）。

**daily-kline backfill（Rust 獨立 `[[bin]] daily_kline_backfill`，不在 engine runtime 路徑）**：多日 trend 研究的 PIT 資料源。已 `--apply` 寫入 **14505 日線**（20 liquid perp × 730d；19 pass，POLUSDT partial 635/730=POL 2024-09 由 MATIC 遷移較年輕，誠實 coverage 非 bug）+ `research.alpha_klines_provenance` 20 row 帳本。寫 `market.klines timeframe='1d'`（與 live 1m-1h disjoint，ON CONFLICT DO NOTHING 冪等）。**C-3 strict-parse**：上游 `parse_kline_list` 每 OHLC `.unwrap_or(0.0)` 是 fake-zero 地雷→`is_strict_valid_ohlc` 拒 OHLC==0/非有限/損壞，writer 直綁無 sanitize。dry-run 預設 + `--apply --i-understand-this-modifies-db` gate + V125 preflight fail-closed。**走既有 signed GET（demo slot 憑證簽名打 demo 端點，非 no-auth）；無憑證 new() 非 mainnet 僅 warn 回 Ok，fail-closed 在 get()→NoCredentials→failed coverage→EXIT_OK**（cron 須檢 coverage 非僅 exit code）。執行 env：`OPENCLAW_BASE_DIR`/`OPENCLAW_DATABASE_URL`(從 `/tmp/openclaw/runtime_secrets/openclaw_database_url` 讀)/`OPENCLAW_SECRETS_ROOT=/home/ncyu/BybitOpenClaw/secrets`。

**Gate-B 隔離 listing-capture 探針（Python research，`helper_scripts/research/gate_b_*` + entry）**：量測新 symbol PreLaunch→Trading 時本地 public WS 對首筆成交的 capture_lag + markout。**R-0 隔離紅線（E3 對抗驗零洩漏，注入 fake prod module 證測試有牙齒）**：0 import 生產模組、0 auth/order/DB write、只 public WS+REST。SoT=live `instruments-info?status=PreLaunch`（前瞻 launchTime，不用過去 listed_at）。verdict 含 `INCONCLUSIVE_NO_TRANSITION`（轉移稀有無事件非 fail）+ `TRANSITION_BUT_NO_CAPTURE`（集合完備性 fail-closed，轉移卻有 symbol 沒抓到 → 絕不誤報 PASS_CAPTURE）。Linux duckdb 1.5.1 smoke 驗證：連線/BTC poison 哨兵/verdict/parquet 鏡像全 ok、EXIT=0。**尚未跑真實 24h 捕捉**（operator-timed；capture_lag/alpha 定論需 ~Q4 真實上市樣本）。手動啟動：`python3 helper_scripts/research/aeg_gate_b_probe.py --duration-seconds <秒>`（system python3 有 websocket-client 1.9.0 + duckdb 1.5.1）。

**審查鏈完整教訓**：E1→E2→E3→BB→MIT→E4 全鏈 + 多輪抓真 bug——(1) E2 review-round 抓 window_end 未對齊 UTC 致結構性 partial（coverage 失區分力）+ probe verdict transition-but-no-capture 假 PASS；(2) E1 修 FIX-3 註解卻寫進「另一個方向的錯」（建構即 Err vs 實際 get() fail-closed）被 re-E2 讀源碼抓到——**comment-fix 也會引入新錯，工作鏈價值**；(3) **post-deploy Linux real-connect smoke 抓到 unit test+dry-run 都漏的 parquet-mirror 崩潰**（duckdb `COPY TO ?` 不支援 bind 參數 + per-channel try/finally 不 catch）——印證「真連線 smoke > mock 單元測試」，研究便利層也要 fail-safe 非阻斷契約。

**延後項（non-blocking）**：BB LOW instruments-info `nextPageCursor` loop（PreLaunch 少單頁足夠 defense-in-depth）；BB DICT-1/2/3 `bybit_api_reference.md` 補錄（public-kline 回填 / PreLaunch 端點 / 修 line 1120「10 topic」只對 Spot）；backfill 全 symbol failed 時退 EXIT_OK 對 cron 誤導（考慮 zero-total-observed 退非零）；gate_b_artifact MODULE_NOTE「duckdb+pyarrow」實不需 pyarrow（E2 觀察，pre-existing）；AEG backfill writer freshness healthcheck（MIT carry-forward，與 V115 basis_panel 同 owed）；srv/TODO.md 更新待平行 session commit 其 TODO WIP 後補。

## 多日 trend 診斷 = NO-GO-TREND（2026-06-02，commit a99ef886）

用上面 backfill 的 14505 日線跑多日 trend 樞紐診斷（operator 拍板「推進候選2多日trend」後）。harness=`helper_scripts/research/multiday_trend_diagnostic/`（唯讀 PG、36 測試、純 numpy 無 scipy）；協議+verdict 在 `docs/CCAgentWorkSpace/QC/workspace/reports/2026-06-02--multiday_trend_diagnostic_{protocol,verdict}.md`。鏈 QC→E1→E2+MIT+QC→E1→E2+MIT+QC→E1→E2，**4-reviewer 收斂**。

**結論：20 liquid perp 多日 trend-following 無可偵測 tradeable edge，關閉此路徑。** 證據（正確尺度）：(1) HAC-corrected TSMOM 過去 k 日→未來 k 日 t_HAC 僅 k40 孤立(2.72)、k90 反轉(-2.60)、hit≈50%、無相干 plateau；(2) per-symbol 自相關 0/20 universe-wide；(3) 表面 0.66 Sharpe 是 short-side 厚尾/funding artifact（long≈0/short 299bps/win 0.45/吃 mean-reversion/chop>bull）。

**方法論教訓（durable，比結論本身更重要）**：
- **daily-lag Ljung-Box 測 trend 是尺度錯置**（QC 自己 RETRACT 協議 §4.7/§5 設計）：daily-lag(1-10) 測「日報酬預測次日」，TSMOM(k=20-90) 賭「多日趨勢持續」，不同尺度（MOP 2012 TSMOM 日報酬同樣近白噪音）。會 FALSE-KILL 慢趨勢。**「trend 統計基礎」須 horizon-matched 直接測**（過去 k→未來 k + Newey-West HAC lag=k-1），不靠單序列短-lag。三審親跑真 PG 抓到。
- **N_eff（獨立 bet）≠ effective N（trade 數）**：effective N=237 充分（故非 INCONCLUSIVE-A 樣本不足出口），但 N_eff=2.09（PC1=68.7% BTC beta）power binding——**屬相關結構維度，longer-history backfill 救不了**（更多時間給不了更多獨立 bet；更早 crypto 史只加 cascade/mean-reversion 非正 momentum）。故 NO-GO+誠實 power caveat 比「INCONCLUSIVE→backfill」假出口誠實。混淆兩 N 會誤判。
- **孤立顯著 cell 是 red flag 非 evidence**：5 個 k 冒 1 個 t=2.72（過 5-scale Bonferroni）在 N_eff=2+24 變體下是預期雜訊；真 momentum 應相鄰 k plateau（coherence gate=≥1 對相鄰顯著正+無反轉）。
- **任何正 Sharpe 先拆 regime×side**：看是否 short-side funding-harvest/崩盤保險偽裝成 alpha（hit<0.5+負偏度+chop>bull=反 trend 指紋）。多審多輪價值=抓到並修 protocol 尺度錯置缺陷 + verdict-path fail-open + adjacency gap，避免「看似 0.66 Sharpe 就上」的 6 週假希望重演。
- **方向**：6 週成本牆翻牆路剩「事件驅動大 move」=**listing fade 主路**（probe 已建）；多日 single-name mean-reversion **不建議**（short-side 是崩盤結構非可交易 reversion，對稱性謬誤）；**funding+OI history backfill=多日持倉策略線 P0**（現覆蓋僅 58 天，複用 daily-kline backfill pattern，cap 用 upperFundingRate SSOT）。

## 進行中（operator 3h+ 喊停，park 點）
- **listing 24h 捕捉運行中**：Linux nohup PID 2146070，run_id `listing_24h_20260602_1847`，--duration-seconds 86400（→明日 ~18:47 寫 verdict）。獨立進程 survive ssh 斷。持續累積到 ~Q4 需 recurring service（未設，follow-up）。
- **funding/OI backfill WIP=impl-complete 但「故意未 commit」**（BB spec 在 `docs/CCAgentWorkSpace/BB/workspace/reports/2026-06-02--funding_oi_backfill_endpoint_spec.md`）：E1 跑 2h 被中止在收尾，但產出完整——3 新檔(`rust/openclaw_engine/src/backfill/funding_oi_backfill.rs` 795行+19測試 / `funding_oi_writer.rs` 391行+4測試 / `bin/funding_oi_backfill.rs` 899行) + 改 4 檔(Cargo.toml bin / backfill/mod.rs / market_data_client/mod.rs OI client 擴展 start/end/cursor / **database/rest_poller.rs=production caller ripple** / dict §132-146+§150-163)。**cargo check 0 error + 23/23 test 綠**（含最高風險 fake-zero variant 正確：真 0.0/負 funding 接受、missing reject、非 kline `>0`、ts reject-on-fail）。為何未 commit：**未過審查鏈 + 改了 production rest_poller.rs**，不應未審就進 git/deploy。**resume = E2(對抗,重點 rest_poller ripple 不破壞 live OI 輪詢)+E3(secret/mainnet)+BB(dict/端點複核)+E4(全 regression) → commit → restart_all --rebuild deploy bin → 跑 18mo funding+OI@1h 回填**。1 個 trivial unused-import(`LEAD_WINDOW_SECS_MAIN`) E2 可順手清。**教訓：單一大 feature(2085行) 對一個 agent dispatch 偏大致 2h+，下次拆(client/funding/OI 分派)**。
