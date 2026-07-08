---
name: project_2026_06_02_aeg_trend_listing_infra_deployed
description: 2026-06-02 AEG alpha-source 研究基礎設施部署——V125 alpha 儲存 + 日線回填(多日 trend 資料源) + Gate-B 隔離 listing 探針；本身不產 alpha，是研究資料/驗證層
metadata:
  node_type: memory
  type: project
  originSessionId: 07386332-55ba-43c0-a468-02f0f16dd863
---

承 [[project_2026_05_31_v58_alpha_pivot]] 的 alpha-source 研究方向。2026-06-02 部署 AEG 研究基礎設施（三端同步，最終 SHA `c1c017b0`；V126 DB 清理見 [[project_2026_06_01_db_schema_hygiene_cleanup]]）。**本身不產 alpha＝研究資料/驗證層。**

## 部署成果（耐久）
- **V125 alpha-history 儲存**：6 張 `research.alpha_*` 表（3 hypertable，chunk 7d/compress 30d/retain 1095d）+ `market.klines` retention 365→1095d；funding/OI/buy/sell ratio 全 `DOUBLE PRECISION NOT NULL`（C-3 拒 fake-zero/NULL）。§E TSDB 2.26.1 reflection 修（無 `compression_settings.segmentby` 欄 → 改 `segmentby_column_index IS NOT NULL` EXISTS；原寫法 deploy crash-loop，MIT Linux dry-run 兩度把關）。
- **daily-kline backfill**（Rust 獨立 `[[bin]] daily_kline_backfill`，不在 engine runtime 路徑）：已 `--apply` **14505 日線**（20 liquid perp×730d）寫 `market.klines timeframe='1d'`（與 live 1m-1h disjoint，ON CONFLICT DO NOTHING 冪等）。C-3 strict-parse 拒 OHLC==0/非有限（上游 `parse_kline_list` `.unwrap_or(0.0)` 是 fake-zero 地雷）；走 signed GET via demo slot；無憑證 fail-closed 在 get()→EXIT_OK（cron 須檢 coverage 非僅 exit code）。
- **Gate-B 隔離 listing 探針**（Python research，`helper_scripts/research/gate_b_*`）：R-0 隔離紅線（E3 對抗驗零洩漏，注入 fake prod module 證測試有牙齒）＝0 生產 import / 0 auth/order/DB write、只 public WS+REST；SoT＝live `instruments-info?status=PreLaunch`（前瞻 launchTime）；verdict 含 `INCONCLUSIVE_NO_TRANSITION` + `TRANSITION_BUT_NO_CAPTURE`（集合完備性 fail-closed，絕不誤報 PASS_CAPTURE）。Linux duckdb 1.5.1 smoke EXIT=0。

## 多日 trend 診斷 = NO-GO-TREND（2026-06-02，commit `a99ef886`）
用 14505 日線跑診斷（harness=`helper_scripts/research/multiday_trend_diagnostic/`，唯讀 PG，4-reviewer 收斂）。**結論：20 liquid perp 多日 trend-following 無可偵測 tradeable edge，關閉此路徑。** 表面 0.66 Sharpe＝short-side 厚尾/funding artifact（long≈0 / short 299bps / win 0.45 / 吃 mean-reversion）；HAC-corrected TSMOM 無相干 plateau；per-symbol 自相關 0/20。

### 方法論教訓（durable，比結論本身更重要）
- **daily-lag Ljung-Box 測 trend 是尺度錯置**（QC 自 RETRACT）：trend 統計基礎須 **horizon-matched 直接測**（過去 k→未來 k + Newey-West HAC lag=k-1），不靠單序列短-lag，否則 FALSE-KILL 慢趨勢。
- **N_eff（獨立 bet）≠ effective N（trade 數）**：effective N=237 充分，但 N_eff=2.09（PC1=68.7% BTC beta）power binding——屬相關結構維度，**longer-history backfill 救不了**。混淆兩 N 會誤判（→假「INCONCLUSIVE→backfill」出口）。
- **孤立顯著 cell 是 red flag 非 evidence**：真 momentum 應相鄰 k plateau；5 個 k 冒 1 個 t=2.72 在 N_eff=2+多變體下是預期雜訊。
- **任何正 Sharpe 先拆 regime×side**：查是否 short-side funding-harvest/崩盤保險偽裝（hit<0.5+負偏度+chop>bull＝反 trend 指紋）。
- **post-deploy 真連線 smoke > mock 單元測試**：抓到 unit test + dry-run 都漏的 parquet-mirror 崩潰（duckdb `COPY TO ?` 不支援 bind 參數 + per-channel try/finally 不 catch）；研究便利層也要 fail-safe。comment-fix 也會引入新錯（FIX-3 註解二次錯被 re-E2 抓）＝工作鏈價值。

## 已了結的運維線（2026-06-02 曾為 park 點，現已 resolved / stale）
- **funding/OI backfill ＝ RESOLVED**：當時「impl-complete 但故意未 commit（待審+改了 production `rest_poller.rs`）」的孤兒 WIP，已於 2026-06-03 過審 + commit `5b80c2f71`（writer，AEG-S1 P0 基礎）並經 TODO v110（`94c1c7b7b`）落地；TODO row 於 2026-06-18 archived（`be4c8651a`）。已非 pending。
- **listing 24h 捕捉（Linux nohup PID 2146070，run_id `listing_24h_20260602_1847`）＝ STALE**：當時 `--duration-seconds 86400` 一次性 nohup 進程，早已結束（非常駐 service），此 PID 不可能仍運行。持續累積需 recurring service（當時未設）；capture_lag / alpha 定論本就 operator-timed（~Q4 真上市樣本）。

---

## [index-archive 2026-06-10] 原 MEMORY.md 索引條目全文(壓縮索引前歸檔,內容為當時點狀態)

- [AEG trend/listing infra 部署 (2026-06-02)](project_2026_06_02_aeg_trend_listing_infra_deployed.md) — alpha-source 研究基礎設施全鏈部署+驗證(commits 0f19c861/e3233647/eae0b890/c1c017b0,三端同步 c1c017b0)：**V125** alpha 儲存(6 表/3 hypertable,§E TSDB 2.26.1 reflection 修)+**daily-kline backfill**(Rust 獨立 bin,已 --apply **14505 日線** 20 perp/730d 作多日 trend PIT 資料源,C-3 strict-parse 拒 fake-zero,signed GET via demo slot)+**Gate-B 隔離 listing 探針**(R-0 零洩漏 E3 驗,verdict INCONCLUSIVE_NO_TRANSITION/TRANSITION_BUT_NO_CAPTURE,Linux duckdb 1.5.1 smoke 過 EXIT=0,**尚未跑 24h 真捕捉**=operator-timed ~Q4);**部署機制**:OPENCLAW_AUTO_MIGRATE 預設0(restart_all 只從 basic_system_services.env 讀,deploy 暫設1→restart→復原0),engine auto-migrate=sqlx fresh-register 無 drift,restart_all 需 cargo on PATH(ssh non-interactive);**教訓**:full E1→E2→E3→BB→MIT→E4 鏈抓多 bug(window UTC partial/probe 假 PASS/FIX-3 註解二次錯被 re-E2 抓/**post-deploy Linux real-smoke 抓 parquet COPY-TO-? 崩潰=unit test+dry-run 漏**=真連線 smoke>mock);V126 DB 清理見 [[project_2026_06_01_db_schema_hygiene_cleanup]](909MB 回收);本身不產 alpha=研究資料/驗證層,承 [[project_2026_05_31_v58_alpha_pivot]]
</content>
