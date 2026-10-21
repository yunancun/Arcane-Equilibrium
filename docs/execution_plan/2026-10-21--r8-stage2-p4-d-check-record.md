# R8 階段 2 P4-D 檢查紀錄（2026-10-21～2026-10-22）

> **目前狀態（2026-10-22）**：§9 已補齊 B 段，§8.2 要求的 13 項全部通過，P4-D 通過條件已滿足；與本次修補 source 同 PR 合入後結案生效。EV-12 的 1,087 標的仍為部分量測，BCHUSDT 正式資料處理待 Operator 裁決。
>
> 本頁原標題為「R8 階段 2 P4-D 檢查紀錄：A 段（2026-10-21）」。§1～§8 保留當時記載，包括尚未執行、未完成與失敗狀態；目前結論及證據以 §9 為準，原歷史不覆寫。

## 1. 目的、依據與判定

- 依 [P4 補充指令](2026-10-20--r8-stage2-p4-research-core-addendum.md) §8.2、§15，記錄構造資料的 A 段：EV-1～EV-9、EV-13、EV-14 共 **11 項通過**。原 A 段 8 PASS，加上 PR #232 修正 EV-9 與 FIX4 的四個可見性探針，補足 EV-1／EV-2。
- conductor 已獨立核對四份探針 run.json／recompute.json、凍結預期值雜湊及演算法綁定，授權記錄者依 §15.3 發布 FIX4，並收錄 A 段結果。Codex 執行記錄者工作；conductor 在 CI 與自動審查無阻塞後最終把關及合併，Codex 不合併。
- **B 段 EV-10～EV-12 尚未執行，留待後補；P4-D 整體尚未完成。** 本次沒有新 Operator 裁決，不新增 RH 事件。§15 的裁決已由 PR #233 合入，事件為 RH-20261021-02。

## 2. 固定來源、執行環境與比對方式

| 項目 | 身分與邊界 |
|---|---|
| 發布基線 | `ca5a543f906fe7bdb2b8081e9fc082b7c86e53e4`（PR #233）；fetch 後符合派工基線 |
| FIX4 | `R8-S2-ENGINE-LEAN-FIX4-20261021`；`codex/r8-s2-engine-lean-fix4-20261021`；`5e452d4873b862d235f1cf4fa6a711f1ca7c377c` |
| 驗收合併樹 | `b4e66d18bab66f8dcbfeb2fb9da1c45afb9277d3` |
| 發布合併提交 | `3a48cb08a8da46d5dc6ce3058f0eed7b7743a5e9`；以 `git merge --no-ff` 保留 FIX4 原提交；`git diff b4e66d18b -- program_code/` 為空，兩者 program_code tree 均為 `c27d611dbb964af5542c864040ef381ba207b0df` |
| 固定映像 | `quantconnect/lean@sha256:2657ed3355efb78d78bd0a5d4f126b01367a635e01bccd220b654d7742d182b6` |
| 隔離 | 原 A 段25次 LEAN／25次屬性表準備，探針4次 LEAN／4次準備，Docker 均 `--network none` |
| 模式與資料 | 正式 FixedSchedule，`mode=validation`、`trial_id=null`；本機構造資料，U4 `--validation` 物化；未讀真實市場或 P3b 資料 |
| 驗證帳本 | 原 A 段各案另建驗證帳本；存取檢查另建六本。探針使用原驗證帳本的逐位元組副本，只讀查詢、未新增帳本事件，鏈頭及檔案雜湊不變；正式帳本未碰 |
| 原 A 段來源 | main `9fae470f5`；EV-9 用 PR #232 的 U6 `series.py` SHA-256 `dd2ec8bef1168263610151916d240d23dd1ba69122ae31c5e3453a3c6ed27e53` 重算，沒有重跑 LEAN |
| 探針演算法綁定 | 四份 run.json 的 code_commit／engine_commit 綁定驗收樹；FixedSchedule SHA-256 `1b6ec29fff8e10b551c4383dd7df06f50443e40cea8de583400eb9d1967bacbe`，其餘 algorithm_files 與乾淨驗收樹一致 |

- FIX4 只改正式範例與 `test_r8_engine_lean.py`。探針以 `data[symbol][dataset][-1][field]` 讀策略收到的同一公開視圖；其他可見標的沿 schedule，無排程者目標0；缺列／未映射值拋例外。未改框架、規則、執行器、U4、U6，沒有診斷轉接或自寫假說替代正式入口。
- 原 A 段的 design／oracle 先宣告事件並以標準庫 Decimal precision=50 計算，未匯入 U5／U6；預期與設定先凍結並在證據目錄的獨立 git 留錨。三個設定更正版沿用原預期雜湊，沒有依輸出調整經濟預期。
- 原 A 段逐項比對成交、取消、作廢、資金費、終點資金費、現金／權益／部位與週期報酬。數值依 §3.9 用 Decimal 相等、無容差；68處原文字串的負零／正零差異皆數值0，明列 comparison.json，**不聲稱原 A 段 JSON 逐位元組相同**。週報酬依U6介面為JSON float，獨立Decimal預期再轉同一float比對，權益本身仍為Decimal。
- 四個探針預期在 `2026-10-21T21:34:38.481149Z` 凍結、早於Docker；未改預期或中途改設定。事前列出的成交、資金費、每步結果與相應訂單／決策逐字串及型別相符，沒有負零格式豁免；預期雜湊執行後不變。

## 3. 經過與保留的失敗

1. 原 A 段在 main `9fae470f5` 執行11項，8 PASS，EV-1／EV-2／EV-9未通過；EV-10～EV-12沒有執行。共25次正式LEAN，其中三個舊設定版本保留但不作驗收，最後22個有效版本 completed。
2. EV-9 的 LEAN 成交與帳務已符合預期，但 U6 在 source/funding_BTCUSDT_funding.csv 第一列 `1641081600000,1e-05` 被一般小數檢查拒絕，無重算報告。U4依§4保留原字串正確；conductor依§8.1／§8.2授權記錄者小修，PR #232只放寬交易所來源值，以Decimal精確解析科學記號，其他輸入仍嚴格。以原run重算true、差異0；其他A段21個有效執行及P4-D0九案例共30份新重算輸出與原檔逐位相同。
3. EV-1／EV-2 的固定排程雖成交相符、物化known_at正確，無法直接證明策略收到哪一列。另寫的DailyVisibility／InterestVisibility在LEAN啟動前被§5第4點固定類別限制拒絕，無run.json、無U6重算；這與§8.2策略實收證據要求衝突，不代表發現實際前視。
4. Operator選定在正式範例加可見性探針，§15由PR #233合入；FIX4在正式FixedSchedule加入探針。四次固定映像執行完成，LEAN與凍結預期相符、殘差0、U6全部true／0／[]。conductor獨立核對後授權發布；本次文件依此把A段改記11項通過。
5. 原設定錯誤保留：EV1-hour初版MID的open104但high102不合法，U6拒絕；v2只改high106並重物化，open／close／經濟預期不變。EV14-carry與EV14-no-trade初版缺internal_validation_days／internal_gap_days，首次擬合lean_error，fits空；v2補182／8，原資料、schedule、fold與expected雜湊不變。舊失敗不改記PASS，U6只核對失敗前綴的差異0也不算通過。

## 4. A 段逐項條件與最終結果

表中 U6 的 `true／0／[]` 分別為 recompute_passed、max_difference、differences；適用於有效LEAN執行。EV-3／EV-8另有預期拒絕的存取檢查，沒有run.json，U6不適用。逐子案例現金及舊失敗見§5；四個探針詳見§4.1。

| 項目 | §8.2通過條件 | 構造要點 | 預期與實際 | 現金殘差 | U6重算 | 結論 |
|---|---|---|---|---|---|---|
| EV-1 | 成交價等於下一根開盤價乘以（1 ± 滑價）；部位變動時刻在 `run.json` 與重算中都是 t + Δ；下一根缺漏時以其後第一根的開盤成交；日線決策的策略收到的是前一日完成的日線（以構造的日線訊號驗證），以次日開盤成交 | EV1-hour-v2／EV1-day：開盤100／104、前收99，MID缺兩根；日線00:00及01:00誘餌。FIX4另以close111／222構造盤中及次日00:00探針。 | 小時買100.05、MID延後買104.052；原日線買100.05、次日賣101.949，均相符。兩個日線探針量10／20、現金99997.9／99955.757989相符（§4）。 | 0 | true／0／[]（有效執行；預期拒絕見說明） | PASS |
| EV-2 | 構造在某根之內跳變的價格，以該根收盤決策的部位不含跳變的捕獲；持倉量在時間戳加 4 小時之前不可見；成交那一根或當日未完成時段的成交額突增，不改變分級與單筆上限 | EV2-lookahead：同根價格100→200、下一開210；成交根及當日未完成成交額突增。OI T−4h=11111、T=77777，探針於T+1h及T+4h。 | 買210.105、現金98896.7446975；LOW untradeable、CAP order_cap皆相符。OI提前可見被量10排除，界線更新為量20；現金99997.9／99995.8相符。 | 0 | true／0／[]（有效執行；預期拒絕見說明） | PASS |
| EV-3 | 暖機期間沒有下單、不計分；暖機需要不可讀區間的資料時 U4 拒絕；首根 1 小時 K 線收盤之前不能交易，上市時間不起作用 | 暖機下單誘餌；NEW的launchTime早於首根，首根S+1h；另建可讀起點2021-01-01的帳本。 | 暖機無單，NEW至S+2h才進targets、歷史不足作廢；現金99997.9相符。暖機越界物化exit2且無輸出，符合預期拒絕。 | 0 | true／0／[]（有效執行；預期拒絕見說明） | PASS |
| EV-4 | 8、4、1 小時與歷史上改變的間隔（含由 8 小時縮短為 4 小時、交界缺一筆的案例）；§3.9 的 G3 至 G6；空白的估計；P_T 缺漏時取前一根收盤並計為填補期；下架之後不計；恰在 s 的結算在下一個時間步計入；下一根缺漏、訂單較晚成交時，T 後的部位不含該訂單 | 8／4／1h及8→4交界缺4h；G3–G6、多空於T開平、下架正負費率、缺價格、延後成交與空頭跨空白。 | G3/G5=-5.176755、G4=4.973745、G6正=-10.251／負=0；P_T fallback=99、MID於T部位0不計；空頭空白為支付。逐筆及步驟相符，分案現金見§5。 | 0 | true／0／[]（有效執行；預期拒絕見說明） | PASS |
| EV-5 | 開倉、加倉、減倉、反手、平倉、下架結算（含不在整點下架、下架前一根缺漏而有未成交訂單的案例）與計分終點的平倉，每一步的部位與現金和 U6 的重算一致 | 數量10→20→5→−7→0→3→終點平；非整點下架；另一品種缺最後兩根且有待成交單。 | 現金99989.0705476／99945.067918相符；delivery取消在03:00、結算change_t=02:30、價格97.412。 | 0 | true／0／[]（有效執行；預期拒絕見說明） | PASS |
| EV-6 | 手續費依成交價、雙邊計入；三個流動性等級；不足 12 個完整日與單筆上限的作廢；`min_qty` 與 `min_notional`；懲罰滑價 | 高／中／低、未滿12日、不可交易、單筆cap、min_qty/min_notional；反手增加段作廢、減少段60bps。 | 買100.05／100.1／100.2、一般賣99.95／99.9／99.8、懲罰賣99.4；六筆作廢、雙邊費與現金99974.50605相符。 | 0 | true／0／[]（有效執行；預期拒絕見說明） | PASS |
| EV-7 | 沒有前值填補的 K 線；回測在最後一根的結束時刻結束；下架品種最後一根不完整的 K 線沒有交給策略 | 小時線缺兩根，末根結束05:00；非整點下架的不完整bar。 | 無fill_forward，02:00／03:00無時間步，末步05:00；下架品種03:00不在targets；現金99982.468492相符。 | 0 | true／0／[]（有效執行；預期拒絕見說明） | PASS |
| EV-8 | holdout 區間一律拒絕物化（本版）；`data_access` 只給候選假說本世代的區間、第二代查不到第一段；跨空窗的第 15 折可以物化 | unopened／denied／other_candidate／candidate四種holdout；第二代帳本含兩世代開啟事件；第15折跨空窗。 | 所有holdout物化拒絕；data_access只給本世代候選、第二代不回第一段，查詢帳本位元組不變；第15折合法物化且完成，現金100000相符。 | 0 | true／0／[]（有效執行；預期拒絕見說明） | PASS |
| EV-9 | 構造 1e-05 量級的資金費與小價格品種，結算金額正確 | 原始資金費1e-05、小價格1.01e-4、quantity12345.67；使用原LEAN輸出、PR #232修正後U6重算。 | 成交0.0001010505／0.0001009495，現金99999.997344083420302相符；第一次U6拒絕，修正後true／0／[]。 | 0 | true／0／[]（有效執行；預期拒絕見說明） | PASS |
| EV-13 | 持有部位的標的在星期四期初前後有 K 線缺漏：沒有前值填補、缺漏標的在缺漏內的損益貢獻為 0 而同期另一個持有標的的損益與資金費照常計入、價格跳動計入缺漏後第一期；`filled_periods` 依 §9.14 的五種情形（含下一根缺漏使訂單延後成交、缺漏恰在星期四 00:00 UTC 結束）逐一驗證，與 U6 相同 | 兩個星期四錨定週期，逐一構造§9.14五種條件；含恰星期四恢復、空白資金費、缺價格與延後成交，另一BTC同期照常。 | filled_periods依次2／2／2／1／2，預期與實際相同；每步權益與兩週returns相符，未把全期損益歸0。逐案現金見§5。 | 0 | true／0／[]（有效執行；預期拒絕見說明） | PASS |
| EV-14 | 後一折的擬合窗終點落在前一折的計分窗內；新模型只在其計分窗起點才啟用，前一折計分窗的最後 8 日仍用舊模型；相鄰兩折的交界不平倉，新一折的第一次決策以延續的部位計算差額 | 後折fit_end=01-16在前折內，計分起點01-24、提前8日；正式no_trade_at與兩折交易延續。 | 01-16 01:00仍加10、01-23 23:00仍減5；carry折界持15目標25僅買10不平倉；no_trade折界才賣15。現金99946.355476／99995.8相符。 | 0 | true／0／[]（有效執行；預期拒絕見說明） | PASS |

### 4.1 FIX4 的四個策略端可見性探針

兩個日線案例共用同一份物化，OI兩案亦同；每組params只有一個probe，故拆四次執行，decision_resolution=hour。探針時刻沒有schedule；schedule只在探針後2h全平。visibility_probe在params及唯一grid點一致，categorical=["visibility_probe"]、numeric={}。其他可見標的目標0。

| 案例／UTC探針時刻 | 可見列／值 | 預期＝實際目標與成交量 | 買入價／費 | 平倉價／費 | 預期＝實際末現金 | 殘差／U6 |
|---|---|---|---|---|---|---|
| DAY-INTRADAY<br>2022-01-15 12:00 | 01-14 00:00；kline_day.close=111 | 10；10、−10 | 100.05／0.550275 | 99.95／0.549725 | 99997.9 | 0／true、0、[] |
| DAY-BOUNDARY<br>2022-01-16 00:00 | 01-15 00:00；kline_day.close=222 | 20；20、−20 | 102.051／1.122561 | 99.95／1.09945 | 99955.757989 | 0／true、0、[] |
| OI-BEFORE<br>2022-01-15 01:00 | 01-14 20:00；open_interest.value=11111 | 10；10、−10 | 100.05／0.550275 | 99.95／0.549725 | 99997.9 | 0／true、0、[] |
| OI-BOUNDARY<br>2022-01-15 04:00 | 01-15 00:00；open_interest.value=77777 | 20；20、−20 | 100.05／1.10055 | 99.95／1.09945 | 99995.8 | 0／true、0、[] |

各值在對應輸入資料集唯一；正式探針只從公開視圖最後可見列取值，未映射即例外。因此量10／20直接辨識策略實際看到的列，不能由固定排程冒充。每筆開倉change_t等於探針時刻，於下一小時時間步原生入帳；平倉change_t為探針+2h。日線界線案另含事前列出的0費率資金費：q_before=0、q_after=20、P_T=99、amount=0。

### 4.2 前視與未更新的對照推導

下表是事前Decimal反例推導，**沒有故意修改框架執行前視版本**。初始平倉，開q再全平−q；成交價=開盤×(1±5/10000)，fee=abs(q)×成交價×0.00055，最終現金=100000+已實現損益−雙邊費+資金費。

| 案例 | 若發生錯誤 | 錯誤值→量 | 反例現金 | 正確量／現金 |
|---|---|---|---|---|
| DAY-INTRADAY | 提前給當日未完成日線 | 222→20 | 99995.8 | 10／99997.9 |
| DAY-BOUNDARY | 次日00:00仍不更新、停留舊列 | 111→10 | 99977.8789945 | 20／99955.757989 |
| OI-BEFORE | 把T時間戳直接當可知時刻 | 77777→20 | 99995.8 | 10／99997.9 |
| OI-BOUNDARY | T+4h仍不更新、停留舊列 | 11111→10 | 99997.9 | 20／99995.8 |

兩個界線案排除永遠停留舊列的假通過。U6只依已記錄決策獨立核對成交與帳務，不執行假說；可見性結論來自凍結預期、正式探針決策及演算法綁定，不能單靠U6重算通過替代。

## 5. 原 A 段各執行版本

原25次執行的狀態全部保留；22個有效版本加4個探針，共26個有效LEAN執行構成11項事件的證據，不把子案例數誤當EV項數。以下EV-9列使用修正後重算，原拒絕仍另記。

| 子案例 | LEAN狀態 | 預期末現金 | 實際末現金 | 殘差 | U6 | 用途 |
|---|---|---|---|---|---|---|
| EV1-day | completed | 100017.8790055 | 100017.8790055 | 0 | true／0／[] | 有效版本 |
| EV1-hour | completed | 99955.757989 | 99955.757989 | 0 | 原U6拒絕、無報告 | 舊設定，保留、不作驗收 |
| EV1-hour-v2 | completed | 99955.757989 | 99955.757989 | 0 | true／0／[] | 有效版本 |
| EV13-1 | completed | 100105.57743025 | 100105.57743025 | 0 | true／0／[] | 有效版本 |
| EV13-2 | completed | 100105.47645025 | 100105.47645025 | 0 | true／0／[] | 有效版本 |
| EV13-3 | completed | 100105.47645025 | 100105.47645025 | 0 | true／0／[] | 有效版本 |
| EV13-4 | completed | 99905.36737525 | 99905.36737525 | 0 | true／0／[] | 有效版本 |
| EV13-5 | completed | 100105.57743025 | 100105.57743025 | 0 | true／0／[] | 有效版本 |
| EV14-carry | failed | 99946.355476 | 100000 | 0 | false／0／[]（僅失敗前綴） | 舊設定，保留、不作驗收 |
| EV14-carry-v2 | completed | 99946.355476 | 99946.355476 | 0 | true／0／[] | 有效版本 |
| EV14-no-trade | failed | 99995.8 | 100000 | 0 | false／0／[]（僅失敗前綴） | 舊設定，保留、不作驗收 |
| EV14-no-trade-v2 | completed | 99995.8 | 99995.8 | 0 | true／0／[] | 有效版本 |
| EV2-lookahead | completed | 98896.7446975 | 98896.7446975 | 0 | true／0／[] | 有效版本 |
| EV3-warm-first | completed | 99997.9 | 99997.9 | 0 | true／0／[] | 有效版本 |
| EV4-G345 | completed | 100012.836262 | 100012.836262 | 0 | true／0／[] | 有效版本 |
| EV4-G6-negative | completed | 99966.191728268125 | 99966.191728268125 | 0 | true／0／[] | 有效版本 |
| EV4-G6-positive | completed | 99955.940728268125 | 99955.940728268125 | 0 | true／0／[] | 有效版本 |
| EV4-fallback-delay | completed | 99995.69506 | 99995.69506 | 0 | true／0／[] | 有效版本 |
| EV4-intervals | completed | 99988.5706 | 99988.5706 | 0 | true／0／[] | 有效版本 |
| EV5-delisting | completed | 99945.067918 | 99945.067918 | 0 | true／0／[] | 有效版本 |
| EV5-lifecycle | completed | 99989.0705476 | 99989.0705476 | 0 | true／0／[] | 有效版本 |
| EV6-costs | completed | 99974.50605 | 99974.50605 | 0 | true／0／[] | 有效版本 |
| EV7-ending | completed | 99982.468492 | 99982.468492 | 0 | true／0／[] | 有效版本 |
| EV8-fold15 | completed | 100000 | 100000 | 0 | true／0／[] | 有效版本 |
| EV9-small | completed | 99999.997344083420302 | 99999.997344083420302 | 0 | 原拒絕；PR #232後true／0／[] | 有效版本 |

EV-13的兩個週期為[2022-01-13,01-20)、[01-20,01-27)，五種條件並非互斥；各案核對條件聯集，缺漏恰在星期四00:00結束的案把價格跳動放入新期，另一標的的損益／資金費照常。週期權益與returns逐項詳列A/REPORT.md及各comparison.json。

## 6. 倉庫外證據與逐檔 SHA-256

以下代號僅縮短表格路徑；全部原證據只讀保留，本次直接計算檔案SHA並核對封存manifest。SHA-256指檔案位元組，不把Decimal數值等價混稱為檔案相同。

| 代號 | 絕對目錄 | REPORT.md SHA-256 | manifest.json SHA-256 |
|---|---|---|---|
| A | `/Users/ncyu/Projects/TradeBot/audits/2026-10-21-r8-p4d-a/` | `2deca9fb39fa564e144de122ba341994fe2264ae32c642ea1f7507b26116bb89` | `e32c046f17afbc0d8c00949c178708d0f38b20626b0753e25250f0404746b199` |
| S | `/Users/ncyu/Projects/TradeBot/audits/2026-10-21-r8-u6-sci-notation-fix/` | `cbaebb8eb5dfdbca189cbd8453533ca8a6d045928cedeb5a647675719767311a` | `eb4c278ac2d6755f8013fa8f8d4dcd4ddc810fd6552f4a46e6119512a5def8e7` |
| P | `/Users/ncyu/Projects/TradeBot/audits/2026-10-21-r8-p4d-a-ev12-probe/` | `4f95794dedc04f310c0e3f2a5ff597f343b84f8434422bcfafa8d2c342d41235` | `6e28ce96ab71d4d6201de000d797de1b83f86416d4c7e5847344a1f2282838ba` |

### 6.1 A：原 A 段的設定、預期與執行／重算

路徑相對A。EV1-hour與EV9-small原U6拒絕，沒有recompute.json；EV-9修正後檔案在§6.2。舊EV14失敗有重算報告，但recompute_passed=false。

| 案例 | 檔案 | SHA-256／未產生原因 |
|---|---|---|
| EV1-day | `cases/EV1-day/config.json` | `e1bb989cf0113bc5580a0527fb005c78a8b5e8123e2fa071a0e98fbbf5bdc03a` |
| EV1-day | `cases/EV1-day/expected.json` | `9926744507aa12502605ae5d4a17d97f93058ce2831e7dc827dff4c3cf520822` |
| EV1-day | `runs/EV1-day/out/run.json` | `85311c5e8a2c56408f7cc315cabc6abde1ea1565642b11612a7a578b279e192f` |
| EV1-day | `runs/EV1-day/recompute.json` | `6bc89690da15da40ca264719357e59d100a6d526e68570ecc6a5fae5c14915c1` |
| EV1-hour | `cases/EV1-hour/config.json` | `b125e0f019c233f28dc388721f184e69da568780dc1668aa02b3238b634185c6` |
| EV1-hour | `cases/EV1-hour/expected.json` | `52297efa6ea85f885a4582ebeb58e4931ef21ff2c9e402bc8dffd5fca13d10e0` |
| EV1-hour | `runs/EV1-hour/out/run.json` | `b078fa70f85c34616c330f5fb4c41b1aa76b9b510f53e02c103d78bc30e4d39d` |
| EV1-hour | `runs/EV1-hour/recompute.json` | 未產生（原拒絕保留） |
| EV1-hour-v2 | `cases/EV1-hour-v2/config.json` | `15ccadde07130d70dbecd63c182a12c4d2b677b279d996e63b76c9ca86ea6cfe` |
| EV1-hour-v2 | `cases/EV1-hour-v2/expected.json` | `52297efa6ea85f885a4582ebeb58e4931ef21ff2c9e402bc8dffd5fca13d10e0` |
| EV1-hour-v2 | `runs/EV1-hour-v2/out/run.json` | `298a9bfab35529a03560c4d6497d01b27b1b85bcf96a017ec32322f918bf5355` |
| EV1-hour-v2 | `runs/EV1-hour-v2/recompute.json` | `944ab04fa48a262f31b06e8fb7fd1dde1f58aa509a9ca3f4a4a238247d1b4b62` |
| EV13-1 | `cases/EV13-1/config.json` | `93e69ce8813eab54b9e426f21a0459486cf1186b224b59ee7261c0fafa11ccac` |
| EV13-1 | `cases/EV13-1/expected.json` | `b9ec1ef0a79cd96dfa4fbe068c913870cf948b42ee286ea5c0b3dc05ac8a07ae` |
| EV13-1 | `runs/EV13-1/out/run.json` | `1fadfb5a601180da286ea9cdf27b0ad1e2b669cb0669e341fc0289ae7a01aff7` |
| EV13-1 | `runs/EV13-1/recompute.json` | `fda28befeb649fb354e14017e5fed63dfd2883a7d2c139115b5ac2c383408753` |
| EV13-2 | `cases/EV13-2/config.json` | `92080f94fbbb38c30646b03a82fef2cc5915400494532d4e17ea3b937e62b16e` |
| EV13-2 | `cases/EV13-2/expected.json` | `b3034251bd662c9125c71e1c87d3cf9c381924c3dc4ec0bfe9dfc150f7a9aecf` |
| EV13-2 | `runs/EV13-2/out/run.json` | `670cfaec06f7d99703d78efb629ffe5f0c82dc096788cf733caa3e78cf0b8aee` |
| EV13-2 | `runs/EV13-2/recompute.json` | `5d977eb5652898170e23e68921f1ff0807b860b38e138f6ca0534a1e6b5d5d0c` |
| EV13-3 | `cases/EV13-3/config.json` | `9b7584be2926af5f1e8454ee93edaffbb3ede65c53e306aa71b14f746f8361da` |
| EV13-3 | `cases/EV13-3/expected.json` | `a4d52fe80ae7f7ca981f67a37407284f784d2057cfc7d408e414bdd07bb8cbc3` |
| EV13-3 | `runs/EV13-3/out/run.json` | `a901dc4730935d7fd9eaad0ed2356f9b605ffb88ffe336ab431ada3370d666d8` |
| EV13-3 | `runs/EV13-3/recompute.json` | `cbc0b17a1966f993c40df8cdfcf3b57bd795ad8a90e32edd6790ddf66beb0cc3` |
| EV13-4 | `cases/EV13-4/config.json` | `9922a38975feb8d12125412f01c0167ff8e224e976ed0656cac190563132648f` |
| EV13-4 | `cases/EV13-4/expected.json` | `9f53a8f0f2d56e60f0c498752b6828b09d65d3f15896822e31f2c7b612326b97` |
| EV13-4 | `runs/EV13-4/out/run.json` | `0533fc23287e22508c5fa7226f8dab69610bc2c9c94550dc1f8531accd690621` |
| EV13-4 | `runs/EV13-4/recompute.json` | `74ab081c543675d263f38eece47063f13fdc6b18b53e45e15342d2491157c819` |
| EV13-5 | `cases/EV13-5/config.json` | `269c00b19d155534d1acf892dd85035174467167235ca33e15d5490faca20079` |
| EV13-5 | `cases/EV13-5/expected.json` | `09ede5506368ea6925db02552cba21baba9fcc97a3c4e756f28d1e954c999a0a` |
| EV13-5 | `runs/EV13-5/out/run.json` | `bf03d6b0d9e33f8946f4698592e8094cfb4ea233d06c1404609f4f71682d1597` |
| EV13-5 | `runs/EV13-5/recompute.json` | `849a041e72fb23bcd88e0252fa71b896491c793b24a1631368bb42b07ecdb53f` |
| EV14-carry | `cases/EV14-carry/config.json` | `0aa7d635398df33e4e5dd8b77591a02c8c50a3bc57bc1311b6fef2dfec4327b3` |
| EV14-carry | `cases/EV14-carry/expected.json` | `d4b8343d5989d0d94515c21f812ca260eb273e9b852b7fe4bceeef4a66fe789a` |
| EV14-carry | `runs/EV14-carry/out/run.json` | `7dd6e5d5f85c823f0569b2dfe83d303fd66de2ae13233e15e369fbcec3a4b093` |
| EV14-carry | `runs/EV14-carry/recompute.json` | `7fe155537fc27c32f050023000462489aefd81d62b46efc0f47312344d64cef8` |
| EV14-carry-v2 | `cases/EV14-carry-v2/config.json` | `73ab9029ca0e66f5f3c3dd1f819517be88096b05855ad4d3fb748f16defd426b` |
| EV14-carry-v2 | `cases/EV14-carry-v2/expected.json` | `d4b8343d5989d0d94515c21f812ca260eb273e9b852b7fe4bceeef4a66fe789a` |
| EV14-carry-v2 | `runs/EV14-carry-v2/out/run.json` | `cb6855030c71b2502487ab55fab5ee9407fe951249df969bb9b2698cd7b1234a` |
| EV14-carry-v2 | `runs/EV14-carry-v2/recompute.json` | `ddbc2804e75f7b384bfe488dd9362b32eafb145c0b6b6732506ec605345093be` |
| EV14-no-trade | `cases/EV14-no-trade/config.json` | `a95b8e73e86e092a744b1ab8576eb415e98b68fdfb5ed8d7ee697d939a9d3d78` |
| EV14-no-trade | `cases/EV14-no-trade/expected.json` | `0028259018c8e863395fc863a753a150d120d947f382b20ba6b476c125b25163` |
| EV14-no-trade | `runs/EV14-no-trade/out/run.json` | `4a4d1ba5d99c234e9dce5e3e946373a2a153dbf77c327ec100d2f4886722dffe` |
| EV14-no-trade | `runs/EV14-no-trade/recompute.json` | `66ae09d59b2c5fd142cfd5c9c56e7b2804d6709a1dc174a648282157deac94d1` |
| EV14-no-trade-v2 | `cases/EV14-no-trade-v2/config.json` | `24c87196042795b54ccb7e5d5d4d1137d3780b299e987d79cf2abd7801bb29fa` |
| EV14-no-trade-v2 | `cases/EV14-no-trade-v2/expected.json` | `0028259018c8e863395fc863a753a150d120d947f382b20ba6b476c125b25163` |
| EV14-no-trade-v2 | `runs/EV14-no-trade-v2/out/run.json` | `04ad60f3d332a809bc0c5359e2a218be68422e9e83b5571820753637e521e2dd` |
| EV14-no-trade-v2 | `runs/EV14-no-trade-v2/recompute.json` | `4908f75fd4ef54d876c4f52eae0f7db77cb35e7a306940e0605c014e8c08fc63` |
| EV2-lookahead | `cases/EV2-lookahead/config.json` | `c4b546903489696105ba762f24e58b4ad8dedf76bace7a4b8dac307b53b8b5c6` |
| EV2-lookahead | `cases/EV2-lookahead/expected.json` | `6b3f48788c42c82365523fcd72f3d83a1190b5bbf745c6ff571958460ab42991` |
| EV2-lookahead | `runs/EV2-lookahead/out/run.json` | `9c55c72511d85446896a5ac96690e9265d05555848b79d3772235ee163b8b9d0` |
| EV2-lookahead | `runs/EV2-lookahead/recompute.json` | `4af919f0d0f106596edbb23376a45be421f2194f70a6617d9ac13ab13cee2d54` |
| EV3-warm-first | `cases/EV3-warm-first/config.json` | `ebd773aed7b820ac564b080dfb154c9db87f396aded8a1d41f5280dab09230d1` |
| EV3-warm-first | `cases/EV3-warm-first/expected.json` | `f4940a726c4a8a1c71865df17d3337a596d2e9fde9173436ee4a75b01473d0ff` |
| EV3-warm-first | `runs/EV3-warm-first/out/run.json` | `f461de46882a5025d3b224447ffb771ab984b48044280ce5eac06c193f60337f` |
| EV3-warm-first | `runs/EV3-warm-first/recompute.json` | `27a8398639cc3c00c0ed8748b2e2cd0ca9eaa67e635acb1dd5cb8dba3863296c` |
| EV4-G345 | `cases/EV4-G345/config.json` | `4eb09527b51a73f46d7fba110b72dd94880c18ef7957d5e60441892a76996c7e` |
| EV4-G345 | `cases/EV4-G345/expected.json` | `4d7b0048f765cbf2277609801e236701f9ebe5a58c83b4afb1ce28376428c80f` |
| EV4-G345 | `runs/EV4-G345/out/run.json` | `ea0f8c2a3dc6bc4612fda8ea7b594bf48f4b799eb37586ba11d6a16c57d20241` |
| EV4-G345 | `runs/EV4-G345/recompute.json` | `0b82d7d0180bafeb4f124bf56048b6f423a46da0e7f11944822097d563940243` |
| EV4-G6-negative | `cases/EV4-G6-negative/config.json` | `86bf407a36259e6fdef3ebe816a19e5f72a093702329a9e694484106426775d0` |
| EV4-G6-negative | `cases/EV4-G6-negative/expected.json` | `9ad23d48c086214ee618b8a69826538b7b19cca90e9b5329b719b1656f58312d` |
| EV4-G6-negative | `runs/EV4-G6-negative/out/run.json` | `352d7a2314963470acb698e26fa06159e4d8caaa3d991bb4c30139d5bc9d54fb` |
| EV4-G6-negative | `runs/EV4-G6-negative/recompute.json` | `9f5d7c1ac1172d52bcc17305d2c07047977eb199f134e6e5f78db61d7936e120` |
| EV4-G6-positive | `cases/EV4-G6-positive/config.json` | `1163fdab479767c76c767993e07a982f425dace2347a1819df6c91887b87ed11` |
| EV4-G6-positive | `cases/EV4-G6-positive/expected.json` | `e4230191423bfad3d1e398348be3b75e7f91e788542628c0282c9159c372ae66` |
| EV4-G6-positive | `runs/EV4-G6-positive/out/run.json` | `e7eb9191940f3a6c1736501eb4bb17c8990c9f0c2cd3b9eee107005d5d92f8ed` |
| EV4-G6-positive | `runs/EV4-G6-positive/recompute.json` | `542489047d7a794d4e86cea96e978e606bd5f73b56b7c98e5a28e713a27ae64c` |
| EV4-fallback-delay | `cases/EV4-fallback-delay/config.json` | `6dfc5839e59283a41d76cffd4ba3ca190e49048a28da078e91653da9b8adb654` |
| EV4-fallback-delay | `cases/EV4-fallback-delay/expected.json` | `ec801d5c92e9b85fcf093c31743d43564dbf1fb1c88fabf11a089203b06bb7b1` |
| EV4-fallback-delay | `runs/EV4-fallback-delay/out/run.json` | `b599bb199d76ae9c2b2ab025ab723b98b7cf15bd3aad7439ace207401a264207` |
| EV4-fallback-delay | `runs/EV4-fallback-delay/recompute.json` | `cf1196f572ee9e90ab714366117a16b6326b9902b102371122d84d8368eb207c` |
| EV4-intervals | `cases/EV4-intervals/config.json` | `1fd8e64adc943693eeee3f434ba38e4e406d3f96615c58632547c5301ac7e5cd` |
| EV4-intervals | `cases/EV4-intervals/expected.json` | `1deba782bc4ae5aad5782510e830cb73d130308b0281092e2004a3e3313f992d` |
| EV4-intervals | `runs/EV4-intervals/out/run.json` | `36acfb981a32bf0ef66d02382280204997245c3930ea6b4cf7f534b51c81637f` |
| EV4-intervals | `runs/EV4-intervals/recompute.json` | `1c374419b8729260dfbb8ed62d4586eff4ffa9d71f88e10b29b4add31e2fe21d` |
| EV5-delisting | `cases/EV5-delisting/config.json` | `a91659b35d9dd91c6cba0db719bcd8895d76dc36bcd4bc597f3da08f0b255b4d` |
| EV5-delisting | `cases/EV5-delisting/expected.json` | `dbe295edc1b6b1ad0387bafe5d86d5c548840249e35e560a9a7a2a964c21bbea` |
| EV5-delisting | `runs/EV5-delisting/out/run.json` | `6d8a63ba5d7c4f4249c8268ed90d2ffcf5d7238ad5098aa6c43324686e055ad6` |
| EV5-delisting | `runs/EV5-delisting/recompute.json` | `5f2c9fcbec144ef42a68f31295782588c9ecb7d9b129eff2ddb5c84f07519b02` |
| EV5-lifecycle | `cases/EV5-lifecycle/config.json` | `cd5d20035cacccc1d63a35143b7a570999e6374747298857e0117b9f953c6662` |
| EV5-lifecycle | `cases/EV5-lifecycle/expected.json` | `efd550c7ffbcff64dcbd2bf67b3b2f02901b4845750589595f46f921a0f102dc` |
| EV5-lifecycle | `runs/EV5-lifecycle/out/run.json` | `a3455bee72f37e4cc0f46d21b1a3f1f2d7e16334b547ecc2beed1689db4d15fc` |
| EV5-lifecycle | `runs/EV5-lifecycle/recompute.json` | `ff3d738744ea1ae75f99f4c0a8c354f6d85592ba7abbd961e8332bd19550c74d` |
| EV6-costs | `cases/EV6-costs/config.json` | `2b24c4e7f491761f628213d0b69bdbb9f0550674bb7a31356e6689ac9a9f147e` |
| EV6-costs | `cases/EV6-costs/expected.json` | `65a3689f2ea6f8b6a8fcf251fa995e294232f0d0b0562e69a954b055646dc190` |
| EV6-costs | `runs/EV6-costs/out/run.json` | `275d611b73ec26f8fdd836d2b451ac9263d2353f227f607ff8b07704833f546f` |
| EV6-costs | `runs/EV6-costs/recompute.json` | `7707af01acd56c608210fa1fa943b30b02478e7d53298247b9d50738361b3a95` |
| EV7-ending | `cases/EV7-ending/config.json` | `1476a16ece3864e4590715ae5099e9ca57d703017459abdbc8128154591c7f83` |
| EV7-ending | `cases/EV7-ending/expected.json` | `49d4055aec0e9504e36b9b27fa77cb2be3a520490167fd6f18ba64075d518e1c` |
| EV7-ending | `runs/EV7-ending/out/run.json` | `3ce48c72896aee5ab5790639469c82358764ca01e80911a5a452c55506f98a99` |
| EV7-ending | `runs/EV7-ending/recompute.json` | `b4fa8ac16d72cd6a9a3c04f71711bffee8fb77dea7769df1d026c9a2c82e0ba8` |
| EV8-fold15 | `cases/EV8-fold15/config.json` | `24069947b084513b9f068bd32f6f43c0b121e4df6ba26bb4a6728aa39ea806bd` |
| EV8-fold15 | `cases/EV8-fold15/expected.json` | `9410770a4837702e37e4de160638d8aaff7c6c6f7d6025b2eb1319cd38907ae4` |
| EV8-fold15 | `runs/EV8-fold15/out/run.json` | `1598b6787546f03747756124b29cd4d9ec1b875f8935199e56f4a404867c6422` |
| EV8-fold15 | `runs/EV8-fold15/recompute.json` | `335105db5409dfcf3d37e84f5ae57b6337eb9ddab6efea8c567749349f50de11` |
| EV9-small | `cases/EV9-small/config.json` | `ecafadc97487760268d5f812fd6122ee9f7c375a7c5e14e20cf21e2aaa4c4f9e` |
| EV9-small | `cases/EV9-small/expected.json` | `bd2cbb4239b9dc157123a8417e99252f22eb015e88880b5b6f479982426893ca` |
| EV9-small | `runs/EV9-small/out/run.json` | `2ed314f4ee15aec4be265319c21520cf7f9b0dfd471e5787d05346118995bf2c` |
| EV9-small | `runs/EV9-small/recompute.json` | 未產生（原拒絕保留） |

### 6.2 S：PR #232 的修正後重算

A段22份重算使用§6.1的同一設定／預期／run；其他21份與原重算逐位相同，EV-9從拒絕改為通過。另9份P4-D0重算也逐位相同，其設定／預期／run雜湊沿用[P4-D0檢查紀錄](2026-10-21--r8-stage2-p4-d0-check-record.md) §6.2。以下路徑相對S，31份均true／0／[]，沒有重跑LEAN。

| 群組／案例 | 修正後重算檔 | SHA-256 |
|---|---|---|
| p4d-a/EV9-small | `recompute/p4d-a-EV9-small.json` | `ca4bf34f158b71a34f5845a9f6ef58cb1079375dd5ee4f3b993348703dde4480` |
| p4d-a/EV1-day | `recompute/p4d-a-EV1-day.json` | `6bc89690da15da40ca264719357e59d100a6d526e68570ecc6a5fae5c14915c1` |
| p4d-a/EV1-hour-v2 | `recompute/p4d-a-EV1-hour-v2.json` | `944ab04fa48a262f31b06e8fb7fd1dde1f58aa509a9ca3f4a4a238247d1b4b62` |
| p4d-a/EV13-1 | `recompute/p4d-a-EV13-1.json` | `fda28befeb649fb354e14017e5fed63dfd2883a7d2c139115b5ac2c383408753` |
| p4d-a/EV13-2 | `recompute/p4d-a-EV13-2.json` | `5d977eb5652898170e23e68921f1ff0807b860b38e138f6ca0534a1e6b5d5d0c` |
| p4d-a/EV13-3 | `recompute/p4d-a-EV13-3.json` | `cbc0b17a1966f993c40df8cdfcf3b57bd795ad8a90e32edd6790ddf66beb0cc3` |
| p4d-a/EV13-4 | `recompute/p4d-a-EV13-4.json` | `74ab081c543675d263f38eece47063f13fdc6b18b53e45e15342d2491157c819` |
| p4d-a/EV13-5 | `recompute/p4d-a-EV13-5.json` | `849a041e72fb23bcd88e0252fa71b896491c793b24a1631368bb42b07ecdb53f` |
| p4d-a/EV14-carry-v2 | `recompute/p4d-a-EV14-carry-v2.json` | `ddbc2804e75f7b384bfe488dd9362b32eafb145c0b6b6732506ec605345093be` |
| p4d-a/EV14-no-trade-v2 | `recompute/p4d-a-EV14-no-trade-v2.json` | `4908f75fd4ef54d876c4f52eae0f7db77cb35e7a306940e0605c014e8c08fc63` |
| p4d-a/EV2-lookahead | `recompute/p4d-a-EV2-lookahead.json` | `4af919f0d0f106596edbb23376a45be421f2194f70a6617d9ac13ab13cee2d54` |
| p4d-a/EV3-warm-first | `recompute/p4d-a-EV3-warm-first.json` | `27a8398639cc3c00c0ed8748b2e2cd0ca9eaa67e635acb1dd5cb8dba3863296c` |
| p4d-a/EV4-G345 | `recompute/p4d-a-EV4-G345.json` | `0b82d7d0180bafeb4f124bf56048b6f423a46da0e7f11944822097d563940243` |
| p4d-a/EV4-G6-negative | `recompute/p4d-a-EV4-G6-negative.json` | `9f5d7c1ac1172d52bcc17305d2c07047977eb199f134e6e5f78db61d7936e120` |
| p4d-a/EV4-G6-positive | `recompute/p4d-a-EV4-G6-positive.json` | `542489047d7a794d4e86cea96e978e606bd5f73b56b7c98e5a28e713a27ae64c` |
| p4d-a/EV4-fallback-delay | `recompute/p4d-a-EV4-fallback-delay.json` | `cf1196f572ee9e90ab714366117a16b6326b9902b102371122d84d8368eb207c` |
| p4d-a/EV4-intervals | `recompute/p4d-a-EV4-intervals.json` | `1c374419b8729260dfbb8ed62d4586eff4ffa9d71f88e10b29b4add31e2fe21d` |
| p4d-a/EV5-delisting | `recompute/p4d-a-EV5-delisting.json` | `5f2c9fcbec144ef42a68f31295782588c9ecb7d9b129eff2ddb5c84f07519b02` |
| p4d-a/EV5-lifecycle | `recompute/p4d-a-EV5-lifecycle.json` | `ff3d738744ea1ae75f99f4c0a8c354f6d85592ba7abbd961e8332bd19550c74d` |
| p4d-a/EV6-costs | `recompute/p4d-a-EV6-costs.json` | `7707af01acd56c608210fa1fa943b30b02478e7d53298247b9d50738361b3a95` |
| p4d-a/EV7-ending | `recompute/p4d-a-EV7-ending.json` | `b4fa8ac16d72cd6a9a3c04f71711bffee8fb77dea7769df1d026c9a2c82e0ba8` |
| p4d-a/EV8-fold15 | `recompute/p4d-a-EV8-fold15.json` | `335105db5409dfcf3d37e84f5ae57b6337eb9ddab6efea8c567749349f50de11` |
| p4-d0/H | `recompute/p4-d0-H.json` | `a22d164893f98fc1a89faf79cd0288c553b741f0803c86d853c516762e646404` |
| p4-d0/G | `recompute/p4-d0-G.json` | `d8750771628e1567fe9d7be5b922fdcffe944d06c3c7ceee265155d04234cd20` |
| p4-d0/D | `recompute/p4-d0-D.json` | `3a96d813551da2136f565b771c8fd76b4198b626732c7eba30a2b2c0e9ab78ee` |
| p4-d0/L | `recompute/p4-d0-L.json` | `135fc4ca298beaa2fefe798e4727034fc2efe37ed6de34208e8d0f8f6424a8f4` |
| p4-d0/P | `recompute/p4-d0-P.json` | `7e00b3ed9f567590d49741a72df8349d457d68ca5371cfab097678e66076b98c` |
| p4-d0/Q | `recompute/p4-d0-Q.json` | `a8b23fd29ae3f593a7a032bd7da4d0d39c165753f617ac5abb3c2d132f839038` |
| p4-d0/N | `recompute/p4-d0-N.json` | `a668fedb350f1a743a14cf0e4d3c5014c6aba1b34fecbed70bd758e19a065cf9` |
| p4-d0/E | `recompute/p4-d0-E.json` | `8f5b1ba270637c6777e9b22b646041998e53af2a7951a4c93c3d95e14a00aef5` |
| p4-d0/B | `recompute/p4-d0-B.json` | `6c10954e2f5b587b72dbb2f744dc4d14cb69348a39b29babb7efc2480ba9d036` |

### 6.3 P：四個 FIX4 探針

路徑相對P；四份設定與預期均在啟動前凍結。

| 案例 | 檔案 | SHA-256 |
|---|---|---|
| DAY-INTRADAY | `cases/DAY-INTRADAY/config.json` | `69df10274119c445a733ea11f475c881bfcd445e80acd0dd8a2a6f77eb288c01` |
| DAY-INTRADAY | `cases/DAY-INTRADAY/expected.json` | `9437649c798e26a8e66c05e9d890b62d406d9bf4c8abf2f45d41d829229ad66e` |
| DAY-INTRADAY | `runs/DAY-INTRADAY/out/run.json` | `3373ac96daa95f029762db05dbe3b8782ab1fa3375c6a96c6171b4bece5ca8f8` |
| DAY-INTRADAY | `runs/DAY-INTRADAY/recompute.json` | `175ebcfc050bb4bcbf38d5244fc9b48cffb92b0e47cd934a108e1f09a63e16ee` |
| DAY-BOUNDARY | `cases/DAY-BOUNDARY/config.json` | `a50d8e0b883b5cf26b43b29a565e38789832095ea7012bbe391bd4d28655aba6` |
| DAY-BOUNDARY | `cases/DAY-BOUNDARY/expected.json` | `9d2416ec1fad44afec35ceacc3e7c280e1e26a96342050899d6059c95390336e` |
| DAY-BOUNDARY | `runs/DAY-BOUNDARY/out/run.json` | `5b9042d55045eadbc63ea3526699e25ce415642dde4ccf57bfc1dccf02805879` |
| DAY-BOUNDARY | `runs/DAY-BOUNDARY/recompute.json` | `a52d78cd4dd85902452ce6627e7a06ffdf12d93f41c0e7c1b6dbf4a5cd91f600` |
| OI-BEFORE | `cases/OI-BEFORE/config.json` | `d4a86451902e669a79552507f1d8a09a3ded03a1645f36e40eb49c65f40382cb` |
| OI-BEFORE | `cases/OI-BEFORE/expected.json` | `0bf4a5b426ebeb362b8ece14622bf17d58d80cb55ac0f42cb0cca60d24b2c005` |
| OI-BEFORE | `runs/OI-BEFORE/out/run.json` | `b27b6bf3bedf84d9cb6a17e45ad8bc078fcd95770d583139ce4ae293da737179` |
| OI-BEFORE | `runs/OI-BEFORE/recompute.json` | `f8550bdafe188edf8b328e0ac6a6645db41048109527c6fd045f52bf8b435b92` |
| OI-BOUNDARY | `cases/OI-BOUNDARY/config.json` | `a0cb0e7ccd20e67b93ee08bc7b7644908cfcdab07cb7b2bb9a79ab7d8c5bc2ec` |
| OI-BOUNDARY | `cases/OI-BOUNDARY/expected.json` | `283064a80057227b6d437b0478fed80e1758ac2cc03e4d86ba36225feeb55d11` |
| OI-BOUNDARY | `runs/OI-BOUNDARY/out/run.json` | `f110888a497aacaf0d30635fd92b6e07c879e606166c6f09f4b7c9fdf8d33a36` |
| OI-BOUNDARY | `runs/OI-BOUNDARY/recompute.json` | `87f1c0930890b6b7e660fcf7a73eabd628343772d7f6786d8368660f8f2bbfb3` |

### 6.4 凍結、拒絕與完整性支援證據

EV-3暖機越界與EV-8存取拒絕不產生run；原可見性探針在啟動前拒絕亦無run／recompute。這些結果及設定以以下檔案與各封存manifest留證；ModelVisibility為原診斷附帶探針，不新增驗收條件。

| 目錄 | 檔案 | SHA-256 |
|---|---|---|
| A | `expected-freeze.json` | `28c9e736916d7896e0c47446ea79fd2968a480e17d9c403aa3698545414e9f7c` |
| A | `inputs-freeze.json` | `85d2f97bda97de2b6b7bc498571d44615f2fa790b43f7cffd49c91f0e46b40cc` |
| A | `supplement-freeze.json` | `09e12d9008d3b4b7d7ee22c643daba449668755cc2e332c0fd2e304a46b38787` |
| A | `integrity-check.json` | `16493d53883e42dcc6f2ac6f6d84224f49c6986800f205fe337049d8cb605a16` |
| A | `ledger-readonly-check.json` | `9b984676289f906be077150f427a17e57a1a92f824cc8ffe5b1a22d94a172184` |
| A | `run-source-binding-check.json` | `d8552743e7c2c630015acd3e28ea33a75570bfb1fa2d8fcb6be86563efda5a15` |
| A | `diagnostics.json` | `dd74ecf2c89b95aaa63a0422e887d391b11a2811273b29136bf2cba4994983a5` |
| A | `ev-summary.json` | `b675d74e85a4a64017646bd54f16af9eb95b83cc74a4f7bdc59487b6d68352ca` |
| A | `probes/DailyVisibility.config.json` | `db3a4f72582212880b761a1c1a4990690a296f8c6920c89ac60820ff12a34082` |
| A | `probes/InterestVisibility.config.json` | `94e22c5d52386561d68a0c97f4d2e3fc8211bd29c4f2d595923c785351f2cc24` |
| A | `probes/expected.json` | `7db493e5e9709a5f7ecc5d94a40c5f9c2ab3f1ccea21b8c9fb28e295a95fc8a4` |
| A | `probes/expected-freeze.json` | `8e0f4412dde291e9962cba3a332965d709d10147195ba63a06867cdbd0151742` |
| A | `probes/results.json` | `00a350031057ba5b13de96c16006a7fc383a449ed0de722a396b333381ff53ea` |
| S | `recompute-summary.json` | `01c97a71afacdfce01d47b1db2e1d9aac795ee5393f3638a4b59491ab99b7a7f` |
| S | `recompute-manifest.json` | `ff89c81c3f913924cb5447db6665ec65b30e7261833f956957507ac8a04b3c12` |
| P | `expected-freeze.json` | `b1651fabaee74ca5e37641e6f0354e22d642b24b974fd1dab94066d7432195ae` |
| P | `inputs.json` | `d56d856547a5d70449f27e30e55590dd2f8a52436f6078226a69292629e2a9e1` |
| P | `integrity-check.json` | `113c511af86c41261247bd95130ae129b084d507510fe9b245bd95ccd491ab35` |
| P | `source-bindings.json` | `3554669d18fc8e023595ea6ea0776de054f1ccc39513f13846c180de42552ae8` |
| P | `case-results.json` | `9ff83163ccd090eff68c3dc83f66df459f88f49a8fc2ac06df28f85730edf4dc` |

## 7. 限制、D 的關閉與後續

- **P4-D0 D 的策略端日線可見性 UNVERIFIED 已關閉**：DAY-INTRADAY直接識別前一日完成列，DAY-BOUNDARY直接識別次日00:00更新；conductor已獨立核對。此補充同時追加到P4-D0紀錄§7，原UNVERIFIED文字保留為當時歷史。
- 本紀錄只完成A段11項。**B段EV-10～EV-12尚未執行**，真實訓練資料的獨立重算、成本壓力與執行時間量測留待後補；沒有真實資料、假說研究或獲利結論，也沒有Demo／live、部署或交易效果結論。
- §10的U4–U6命令列入口索引及研究工具核心runbook仍為P4-D期間待辦，本PR不實作。未增加FIX4專屬TODO列；P4-D列下一步為B段EV-10～EV-12。
- 原A段執行時段為2026-10-21 20:37:51～20:48:37.184352 UTC；PR #232重算為20:53:27.837514～20:53:30.627333 UTC；四探針驗收為21:32:46～21:36:47.552884 UTC。發布分支的提交前測試、CI、自動審查與起訖另隨PR回報，不改寫驗收時段。

## 8. B 段執行狀態追加更正（2026-10-21）

- §7 與 PR #234 發布時的「B 段 EV-10～EV-12 尚未執行」保留為當時記載；實際上 B 段已於同時段另行執行。EV-10／EV-11 原報告時段為 `2026-10-21T21:38:42Z` 至 `2026-10-21T21:46:58.801451Z`。本次 §16 派工時，conductor 回報 EV-10 不通過、EV-11 通過、EV-12 量測進行中；B 段完整紀錄待 EV-10 重跑與 EV-12 完成後補，本段不把進行中的量測改判為完成。
- **EV-10 不通過**：BTCUSDT＋BENDOGUSDT 真實訓練資料加減倉後平均成本為無限小數，LEAN 使用 .NET `System.Decimal`（28–29 位有效數字）。自 `2024-07-03T02:00:00Z` 起，現金約 `99833`，每步 LEAN 與框架 `Decimal` 預期差 `1e-23`（28 位有效數字的最後一位，1 ulp），不累積；48 筆紀錄（含結束時另記一筆）的 `total=0.00000000000000000000048` 不是最終現金差額。容器 `finished=completed`，`assemble_run` 依原零殘差規則標為 `failed`／`lean_error`。完整路徑診斷重播的 8 筆成交、18 筆資金費、37,502 步均在 §9.8.8 容差內，最大差 `4.472101636863276116134e-24`；原正式 `recompute_passed=false` 保留。表示精度的內部機制為原報告依時序與程式提出的診斷，未取得 .NET 內部平均成本追蹤。
- **EV-11 通過壓力數值核對**：`completed`、8 筆成交、18 筆資金費、37,502 步；現金殘差 0，U6 `recompute_passed=true`、`differences=[]`，最大差 `3.122386395316420407026e-24`，在 §9.8.8 容差內。手續費 `22.34838906189`、資金費 `0.327631101289364`、滑點金額 `29.98993204`、最終現金 `99598.376849999399364` 與獨立壓力核對一致。EV-10 基準失敗所阻擋的正式 stress／損益兩平未成立，EV-11 數值通過不等於 B 段完成。
- Operator 2026-10-21 選定「加精度容差」，規則與兩個修補交付見 [P4 補充指令 §16](2026-10-20--r8-stage2-p4-research-core-addendum.md#16-現金殘差的表示精度容差2026-10-21)：U5-FIX5 與 U6-FIX3 以同一個 100 ulp 界限判定，仍記錄所有非零殘差；原失敗不因本文件而變成通過。§16 合入後才實作，再以原物化與設定重跑 EV-10。
- 本次只追加執行狀態、契約依據與證據索引；§7 的「沒有真實資料」限定為原 A 段結論，B 段已使用真實訓練資料，仍沒有假說研究或獲利結論。原報告把 EV-12 記為當時 NOT_RUN，後續量測狀態另行記錄，兩者不互相覆寫。

證據目錄為 `/Users/ncyu/Projects/TradeBot/audits/2026-10-21-r8-p4d-b/`。以下雜湊綁定本次讀取的檔案；manifest 已收錄另行量測的 EV-12 子目錄，不能用它把原 REPORT 的停止時點改寫為完成。

| 檔案（相對上述目錄） | SHA-256 |
|---|---|
| `REPORT.md` | `33c24087fab442a351816234511eb45b65bfd1ed69e28b6d1d23696048bfd2c1` |
| `manifest.json` | `bd58fe78ecc82982142eb00774449b810250dd2b237092edf39397a7a65c878c` |
| `runs/EV10-v3/out/run.json` | `45477fbe813db39607b34a2bc5a37eb1509dd08ec0bbbdb3b4ba502020113ecd` |
| `runs/EV10-v3/recompute.json` | `11da3ab676a1c3500961bed50cb06ec25089d25aaad339933ea8bbb044a2fe93` |
| `runs/EV11-v3/out/run.json` | `3632cf0255b9f4059814fdc9852ed0055cae0bd83b7b8836fbd7d39bc8074031` |
| `runs/EV11-v3/recompute.json` | `48cf9c8715293839fbc9a04f20bf9b7118240cbbca53b417a839850be13dac23` |

## 9. B 段驗收、執行時間量測與 P4-D 結案（2026-10-22）

### 9.1 依據、來源與執行界線

- 本節依補充指令 §8.2、§16.3 追加 B 段結果，與本紀錄的 A 段及 §8 更正共同構成 P4-D 檢查紀錄；先前失敗、尚未執行與待核准文字保留為各次觀察，不回寫歷史。
- 驗收合併樹為 `ffaf8d1966db5950d8ee0c02c0bdcbbb88c0977e`：main `17345cf08e3c88d2aac1dd9d5b7707e890ad2632` ＋ U5-FIX5 `722c66f3f2290a79f5e405e0190a1f17e4277a2c` ＋ U6-FIX3 `4638af48d0a004e9315fda1de04751b29015d081`。main 已含精度契約 PR #236 與 U4 小修 PR #235；conductor 已核對 EV-10 原始檔。發布分支依序以 `--no-ff` 保留兩份原提交，`program_code/` 與驗收樹相同（tree `4b21823614c9df5831a9fcd438deaaffda126c93`）。
- 固定映像為 `quantconnect/lean@sha256:2657ed3355efb78d78bd0a5d4f126b01367a635e01bccd220b654d7742d182b6`，Docker 執行皆 `--network none`，使用正式 `FixedSchedule`、執行器 `validation` 模式及 `trial_id=null`，沒有轉接。
- B 段使用 P3b 的真實訓練資料，manifest SHA-256 `b6519a7b2f5eae4759612690790ddb6680db62aa4e723427f51c21a7d6257006`。U4 不帶 `--validation`，資料窗限制在 `[2020-01-01T00:00:00Z,2025-07-01T00:00:00Z)`；暖機早於起點的部分為空，恰在 `window.end` 的資金費依 §4.3 保留，沒有更晚市場數值。整檔位元組只用於雜湊，範圍外只掃時間戳。另建的驗證 fixture 帳本僅供 `data_access`，前後雜湊不變，不是正式研究帳本，沒有假說預登記或試驗 API 呼叫。
- 收尾驗證 UTC 為 `2026-10-21T22:28:19Z`～`22:36:49.644117Z`；EV-10 核准續跑為 `22:38:13Z`～`22:40:23.538597Z`。章節與交付日期採本地 2026-10-22，UTC 時刻照原始證據記載。

### 9.2 EV-10：獨立重算與精度修補

**構造與第一次失敗**：§8.2 要求 BTCUSDT 與一個下架品種。BTCUSDT 為指定基準；BENDOGUSDT 從訓練段下架候選中，按 ASCII 代號選取小時線無缺漏的第一個標的，選取只看資料覆蓋與生命週期，不看報酬。其可用小時線自 `2024-06-03T09:00:00Z` 至 `2025-01-30T08:00:00Z`，下架時刻為 `2025-01-30T09:00:00Z`。本例在下架前的 2024-07-01～04 每日 01:00 UTC，BTC 權重依序為 `0.10`、`0.15`、`0.05`、`0`；BENDOG 為 `0.0005`、`0.001`、`0.00025`、`0`，構造開倉、加倉、減倉與平倉。

- 舊 v1 物化未含首根資料，沒有可見標的、成交或資金費；v2 的 BENDOG 目標超過單筆上限，只有 BTC 事件，兩者均為 NOT_EXERCISED。v3 保留含首根的物化並縮小 BENDOG 目標，各設定與預期先凍結再執行，沒有依報酬選擇設定。
- v3 產生 8 筆成交、18 筆資金費、37,502 步，卻自 `2024-07-03T02:00:00Z` 起每步現金差 `1e-23`；當時現金 `99833.46012581705203930431319`，差額為 1 ulp、不累積。容器 `finished=completed`，組裝器按原零殘差條件標為 `failed`／`lean_error`，正式重算為 false。原始失敗與診斷見 §8，不因後續修補刪除。
- Operator 選定精度容差，PR #236 的 §16 明定 `ulp=max(10^(e−27),10^−28)`，e 取框架預期現金 `steps[].cash` 的 `Decimal.adjusted()`，零現金取 `10^−28`；絕對殘差不大於 100 ulp 為表示誤差，結束時以最後一步現金計算。仍記錄所有非零殘差，`total` 不作判定。U5-FIX5 在組裝時採此判定，U6-FIX3 獨立採同一界限；§9.8.8 的數值比對容差不變。

**設定來源綁定的更正**：conductor 原指令要求「同一份設定、相同 SHA」，但舊設定的 `code_commit`／`engine_commit` 仍綁 `ca5a543f9`，與修補後來源不相容，屬指令錯誤。記錄者實際呼叫在 `verify_source` 被拒：`來源與 code_commit 不符: program_code/research/r8_engine/lean_algo/examples/fixed_schedule.py`，沒有啟動 Docker，也沒有繞過來源驗證。conductor 隨後核准只把這兩欄改成驗收合併樹 `ffaf8d1966db5950d8ee0c02c0bdcbbb88c0977e`，其餘欄位逐值相同，沿用原物化及經濟設定。舊設定 SHA-256 `98b9a71f1205d2d89f470f5f055f4e403c3b8a2c66d258e3427437fb9cadd7aa`；核准設定 `c3b31951e81c93ae9242f0a8a23bb167eca1c60c1fe7e66a9d376852ae1226de`；原物化 manifest `205fc6aa30b47a73bf6a639d21153df93472c33fbf9302eaa85bf776735bf086`。核准與重新凍結另存，提案中的 PENDING、原拒絕與前版報告均保留。

**最終結果**：

| 指標 | 結果 |
|---|---|
| LEAN／組裝狀態 | `completed`；`failure_reason=null`、`failure_t=null` |
| 原始現金殘差 | 48 筆，各 `1e-23`，含演算法結束時另記的一筆；總和 `4.8e-22`，不作失敗判定 |
| 獨立 Decimal 核對 | precision=80；48 筆均為 1 ulp，沒有超過 100 ulp 的未解釋殘差 |
| U6 | `recompute_passed=true`、`differences=[]`（0 筆） |
| U6 殘差報告 | `max_cash_residual_ulps="1"`、`first_unexplained_cash_residual_t=null` |
| 數值最大差 | `4.472101636863276116134e-24`，位置 `steps.37455.cash`；在 §9.8.8 容差內，並非數值精確為 0 |
| 最終現金 | `99619.331486333096364` |
| 來源綁定 | run 的兩個 commit 欄位為核准 head；10 個 algorithm_files 雜湊均與驗收樹相符 |

與舊 v3 逐筆比對：orders 8、fills 8、funding 18、endpoint_funding 0、steps 37,502、decisions 4、voided 0、fits 0，這八個陣列與原始殘差紀錄全部相同。兩標的各 4 筆成交、9 筆資金費；改變的是來源提交綁定與殘差分類後的完成狀態，沒有改事件內容。EV-10 結論為通過。

U6 stress 原始輸出如下，只作事件級核對與記錄：

| 滑點倍數 | 費率 | 狀態 | fees | funding | slippage | net_return |
|---:|---:|---|---:|---:|---:|---:|
| 1 | 0.00055 | completed | 16.388718748193 | 0.327631101289364 | 14.99496602 | -0.00380668513666903636 |
| 2 | 0.00055 | completed | 16.388818645386 | 0.327631101289364 | 29.98993204 | -0.00395663579584096636 |
| 3 | 0.00055 | completed | 16.388918542579 | 0.327631101289364 | 44.98489806 | -0.00410658645501289636 |
| 2 | 0.00075 | completed | 22.34838906189 | 0.327631101289364 | 29.98993204 | -0.00401623150000600636 |

損益兩平回傳 `multiplier="0"`、`status="nonpositive_without_slippage"`，lower／upper 及兩端 net_return 均為 null；方法原值 `bracketed_repricing; discrete quantities can create multiple crossings`。`stress_passed=false` 原樣保留，依本次驗收指令只記錄，不是 §8.2 事件級檢查的失敗條件，不作策略優劣、研究或獲利結論。

### 9.3 EV-11：成本壓力

- 以固定目標權重、滑點 ×2、費率 `0.00075`（0.075%）執行原 EV11-v3，數量隨壓力後權益改變。LEAN `completed`，8 筆成交、18 筆資金費、37,502 步、現金殘差 0；U6 重算 true、`differences=[]`，最大差 `3.122386395316420407026e-24` 在 §9.8.8 容差內。
- 費用 `22.34838906189`、資金費 `0.327631101289364`、滑點金額 `29.98993204`、最終現金 `99598.376849999399364` 與壓力重算相符。修補後 EV-10 的 stress 第四情境亦為相同成本與淨報酬，原事件與 1,647 期序列的核對證據保留。
- 本輪不重跑 EV-11 的 LEAN，只用新 U6 重算原 run；原欄位及數值均不變。EV-11 結論為通過，與 `stress_passed` 的研究指標判定分開。

### 9.4 EV-12：選取、資料修補與量測限制

**選取與執行方法**：單一標的為 BTCUSDT；100 標的為 BTC 加上訓練段有小時線的其他標的按 ASCII 排序前 99 個，BTC 已含在 100 個內。原完整集合為 P3b 的 1,088 個，本輪只為量測排除 BCHUSDT，成為 1,087 個；其中 450 個在訓練段沒有小時資料，保留空輸入、對策略不可見。100 清單不含 BCHUSDT，前後不變。固定時點策略對 BTC 使用 EV-10 的四個權重，其他標的為 0；沒有按報酬篩選。

20×16 量測使用 BTC、正式 FixedSchedule、20 個 numeric index 網格點、score 固定為 1、空 schedule，全部軸依 §14.2 宣告。16 個量測折全在訓練段：初始擬合 728 日，其後每 84 日一折，擬合終點從 2021-12-29 至 2025-06-11；內部驗證 182 日／間隔 8 日，計分槽在擬合終點後 8 日、長 1 日。這是供量測的折表，不是 §9.1 每 91 日的正式研究折表；輸出 16 筆 fits、各 20 個 score，共 320 個結果。牆鐘含資料推進，未單獨量測 callback CPU 耗時。

**U4 `minNotionalValue` 小修**：初次 100／1,088 物化都在空字串屬性被拒，沒有啟動 LEAN。conductor 依 §4.5「缺少時記為 0」授權 PR #235 小修：缺鍵、None、空字串或僅空白記為字串 `"0"`，limitations 區分原因；其他無效、負值、非有限值與非字串數字仍拒絕，tickSize／qtyStep／minOrderQty 檢查不變。該修正已隨 main `17345cf08` 合入，本發布不另改 U4。

本輪 1,087 標的物化中，以下 22 個標的的 `minNotionalValue` 原為空字串，已實際記為 0 並列入 limitations：1000000VINUUSDT、ANCUSDT、BITUSDT、BTTUSDT、BUSDUSDT、COCOSUSDT、CREAMUSDT、FTTUSDT、GSTUSDT、IGUUSDT、KEEPUSDT、LUNAUSDT、MCUSDT、MULTIUSDT、RAYUSDT、SRMUSDT、STRAXUSDT、TOMOUSDT、USTUSDT、WSMUSDT、YFIIUSDT、ZBCUSDT。100 清單中有前兩個。PR #235 當時的 1,088 物化因另一資料問題失敗，沒有成功輸出的 limitations；本輪成功物化的 22 個紀錄不回填成舊輪成功。

**BCHUSDT 排除**：`kline_BCHUSDT_D.csv.gz` 第 2 列，`2020-12-14T00:00:00Z`（1607904000000），`open=0.0`、`low=0.0`，不符 U4 OHLC >0。原始檔 SHA-256 `a1e9e370499251f3abb5f03ddd8bab2d132f6d55effe9f57e8a76d4655e86183`。本輪依核准僅為量測排除此標的，未改原始資料、U4 或正式處理規則；正式資料前檢及 BCHUSDT 等異常列處理仍待 Operator 裁決。訓練段掃描覆蓋 1,088 標的、4,352 來源檔、13,093,816 列，沒有另發現 U4 數值／結構／合約屬性拒絕項。

**量測表**：秒為牆鐘，MiB／GiB 採 1024 進位。單一與 20×16 沿用先前 EV12 證據；100 與 1,087 為本輪驗收合併樹上的量測。

| 案例 | LEAN 容器秒 | runner 秒 | 容器觀測峰值 MiB | wrapper 峰值 MiB | VM RSS 峰值 GiB | Mac 全機已用峰值 GiB | 物化 MiB | 結果 |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| 1 標的 BTC | 12.021 | 12.443 | 669.30 | 112.78 | 3.334 | 55.672 | 8.62 | completed，46,166 steps |
| 100 標的 | 60.706 | 61.179 | 3,820.87（3.731 GiB） | 121.344 | 6.446 | 56.472 | 267.756 | completed，46,166 steps、4 fills |
| 1,087 標的 | 38.469（至停止） | 39.694（至停止） | 7,469.44（7.294 GiB） | 87.891 | 9.661 | 57.564 | 1,626.163 | 初始化時保護停止，部分量測；0 steps |
| 1 標的、20×16 擬合 | 10.868 | 11.237 | 623.62 | 111.62 | 3.371 | 56.008 | 8.62（共用） | completed，16 fits／320 scores、46,166 steps |

| U4 物化 | 牆鐘秒 | 主機程序峰值 MiB | 邏輯 bytes |
|---|---:|---:|---:|
| 單一／20×16 共用 | 0.954 | 800.47 | 9,038,014 |
| 100 標的 | 10.772 | 800.156 | 280,762,324 |
| 1,087 標的 | 66.626 | 800.516 | 1,705,155,779 |

- 單一與擬合共用準備成本，不重複加總；這兩案及 100 標的完成時現金殘差皆 0。全訓練窗指請求窗內全部可用資料，BTC 首根為 2020-03-25 10:00 UTC，之前不補 K 線。100 標的日誌在 Python 關閉階段另有 10 秒 `Execution Security Error: Operation timed out`；finished 與 run 均 completed、Docker exit 0，保留異常，不稱為無異常完成。
- 1,087 標的初始化期間，7.74 GiB、4 CPU 的 Docker VM 可用記憶體連續兩次低於預設 256 MiB 保護線，最後為 78,164 KiB（約 76.33 MiB），依條件 `docker stop`，exit 143。cgroup 的 oom／oom_kill 均為 0；Mac 尚約有 70 GiB 可用。因此是 Docker VM 記憶體壓力觸發保護停止，沒有觀測到 OOM kill。events 為空、沒有 finished，組裝結果 failed／lean_error；38.469 秒只到停止，不能當成完整訓練段耗時。本輪未加資源或重試。
- 容器記憶體約每秒讀 cgroup v2 memory.peak，最後採樣到退出間未保存，為觀測峰值／可能的實際峰值下界。wrapper 用 ru_maxrss；VM RSS 與 Mac 總量由 ps／vm_stat 取樣，包含原有 VM 與其他程序，不能全歸因本任務。監控成本含在牆鐘；兩個 LEAN 執行未並行，但全部物化與 100 標的關閉階段少量重疊。四列分屬兩輪、來源不同，不作嚴格擴展性基準比較。

### 9.5 歷史執行重算與發布驗證

- 修正後 U6 對 36 份原 run 重算：P4-D0 九個、A 段 22 個（EV-9 對照 PR #232 修正後報告）、FIX4 四個可見性探針、B 段 EV11-v3 一個。沒有重跑這些 LEAN 執行。
- 36／36 的所有原有 key/value 逐值相同，含判定、differences、max_difference、counts 與 totals；不只是旗標相同。新報告恰新增 `max_cash_residual_ulps="0"`、`first_unexplained_cash_residual_t=null`，所以不稱整份新舊 JSON 位元組相同。全部 true、differences=[]；EV-11 原本容差內的非零 max_difference 亦原樣保留。
- 驗收樹既有回歸為全部 R8 911、U4 63、U5 269、U6 226 passed，均 0 failed／skipped／error；這是驗收紀錄，不替代發布分支的提交前測試與 hosted CI。發布分支另跑結構測試與全部 R8，結果隨 PR 回報。

### 9.6 證據索引與 SHA-256

以下證據位於倉庫外，唯讀引用。B 包含最初 EV-10／EV-11 與首次 EV-12；U 為 PR #235 小修；C 為本輪收尾與核准續跑。B 的 `EV12/REPORT.md` 使用 B 根目錄 manifest，不另虛構子目錄 manifest。各表 SHA-256 綁定本次讀取的檔案；其餘指令、來源、監控採樣及 36 份逐檔新舊重算雜湊由相應 manifest 與 historical/results 索引。

| 代號 | 目錄 |
|---|---|
| B | `/Users/ncyu/Projects/TradeBot/audits/2026-10-21-r8-p4d-b/` |
| U | `/Users/ncyu/Projects/TradeBot/audits/2026-10-21-r8-u4-minnotional-fix/` |
| C | `/Users/ncyu/Projects/TradeBot/audits/2026-10-22-r8-p4d-b-closure/` |

| 目錄 | 相對檔案 | SHA-256 |
|---|---|---|
| B | `REPORT.md` | `33c24087fab442a351816234511eb45b65bfd1ed69e28b6d1d23696048bfd2c1` |
| B | `manifest.json` | `bd58fe78ecc82982142eb00774449b810250dd2b237092edf39397a7a65c878c` |
| B | `symbol-selection.json` | `df18d036b949bed23172e798869b1c5dba60ada038c723ed559d9af07440542f` |
| B | `cases/EV10-v3/config.json` | `98b9a71f1205d2d89f470f5f055f4e403c3b8a2c66d258e3427437fb9cadd7aa` |
| B | `cases/EV11-v3/config.json` | `6b479226863c402cc0959df6547061883fee10b4fb3e866eac8213eafa537708` |
| B | `inputs/ev10-11-v2/materialization/materialization.json` | `205fc6aa30b47a73bf6a639d21153df93472c33fbf9302eaa85bf776735bf086` |
| B | `runs/EV10-v3/out/run.json` | `45477fbe813db39607b34a2bc5a37eb1509dd08ec0bbbdb3b4ba502020113ecd` |
| B | `runs/EV10-v3/recompute.json` | `11da3ab676a1c3500961bed50cb06ec25089d25aaad339933ea8bbb044a2fe93` |
| B | `runs/EV11-v3/out/run.json` | `3632cf0255b9f4059814fdc9852ed0055cae0bd83b7b8836fbd7d39bc8074031` |
| B | `runs/EV11-v3/recompute.json` | `48cf9c8715293839fbc9a04f20bf9b7118240cbbca53b417a839850be13dac23` |
| B | `EV12/REPORT.md` | `c37488d97106b17f208848daa87c3c5630d8fd2d90e23729207790cf01e8628a` |
| B | `EV12/measurement-plan.json` | `263ddd86df53c5d297d2d8336ca05270735a346631ea760c37be7eaf4c505d03` |
| B | `EV12/plan-freeze.json` | `4a8dacd82823ed20892404af7ce871888ad35885c6e91efe10be07cc7cca21c5` |
| B | `EV12/measurement-results.json` | `26d6b529a4b683138744586d18d286c37aac44eaf95ff2241b235ab0154f76ee` |
| B | `EV12/cases/single/config.json` | `c89c576395466b0b1aabf36750e53246f36947a7bdbd33469290bd3cbfaa506a` |
| B | `EV12/cases/fit20x16/config.json` | `30f5fba9a451de2673cbaa07a9c34f511b5391b0284b966756007517c48691a3` |
| B | `EV12/runs/single/out/run.json` | `00e6bd9f515d60db84f04ddd5564291148c4f63d5e12afe59609d379a5b95c03` |
| B | `EV12/runs/fit20x16/out/run.json` | `c8b74f764384d77089713ff4d4c3a416a3c3e7c35bc2a46815861cc2a5465beb` |
| U | `REPORT.md` | `708ffa0a96b63d3899a962e8047b1c242d0e8d9772ad99016e7465179d865161` |
| U | `manifest.json` | `cfc2656ba9bb74d374f18fc1829f21a59c7ff2f9ac28fae209447e0fb78932da` |
| U | `instrument-attributes.json` | `5f33fe3c2968133dc101008e68d956402308c5f4ba8ae2a3fe06428fedbdfae1` |
| U | `hundred/result.json` | `aa677b02e96443525f18579289df9a5d2862f0a181cb463d4b5dc18b412c7665` |
| U | `all-rejection.json` | `1c3e3f648f2f03675aa8662a3ccc2853aa5312f2af8acb9750f09ffe259355d8` |
| C | `REPORT.md` | `ed1c52eaa194b46e4552843f819a62ccf56bcf2dd1b85d20a6adaa4fa9edead2` |
| C | `manifest.json` | `0ed2fb666a80fd674917d75fd4b314627e44c82ad206e263265e037ca316b77a` |
| C | `EV10/prior-closure-report/REPORT.md` | `ce973cafa1fdd49bef9c310e81638dc6b17723ea9846628b648287e0d9b53eab` |
| C | `EV10/proposed-config-diff.json` | `9ebc5a9ca1b7df30c3256f7772dda9384b0f1db6189d46a4a489a3acf9fba407` |
| C | `EV10/proposed-config.json` | `c3b31951e81c93ae9242f0a8a23bb167eca1c60c1fe7e66a9d376852ae1226de` |
| C | `EV10/conditions.json` | `31a5680a72923e8e851e07c6bc54b23a693c3008c20ed4e546d0a236f54c7f84` |
| C | `EV10/conditions-freeze.json` | `31d996d301c79e1e76c002e286b795fed6cc85b2416588d4991de7211b9cc16f` |
| C | `EV10/approved/authorization-and-freeze.json` | `fe42f1330572d5fe2f095af509410c4ee8b9aed0956881a6c70128e3bc093ee4` |
| C | `EV10/approved/out/run.json` | `fede386fb1b8e1d1bb3b46ea0eea271617ab063dae9349f9c7ae5f3ead642f32` |
| C | `EV10/approved/recompute.json` | `e912e9046b6af3ff3dd6ff47c50d12243f25f1ca6d1a73df32fdbfb26b0db91e` |
| C | `EV10/approved/stress.json` | `630a75f194bdbe12a4530a05d9be7513d25b18e32ed1075393e0256971ecb39c` |
| C | `EV10/approved/independent-ulp-check.json` | `f9b1d4314c666df49bf86a8c9b674f6d34d7f3e3b1ae4fd70a219334958f91e3` |
| C | `EV10/approved/v3-comparison.json` | `d5e14887ad44b04d73446e3e0d07e0bfe7abd742cd879d5b4d544c050eb1946b` |
| C | `EV10/approved/source-bindings-check.json` | `fd0efb3a6fdbaccb0df51823826a98468381609d88c3db5dc91d573886cec5b9` |
| C | `historical/inputs-freeze.json` | `34e43e055a11b8e91e87e7b95434bb90abd43220326f6b68e4f86b39e2ea85ad` |
| C | `historical/results.json` | `0e263c8a796d17aef1730c59e2cd8f894e198f5c3a18d01484f7b14945da0dae` |
| C | `EV12/scan/result.json` | `10acc25bb0a4790832da0a9c56a736921b9f33ef64e79c30780a8555d808d1f2` |
| C | `EV12/scan/bad-rows.jsonl` | `dec2f0f6231b6c3a8abdb2d7cafd02abd154b1af0db02aca392ac7a34130ab1a` |
| C | `EV12/cases/hundred/config.json` | `b6cb9654cc5cac93df99a2ca5584e6c729c6e3ba170fb1ed4b2b41c7e99fc903` |
| C | `EV12/cases/all/config.json` | `3c9a084fd267ca6688052e73e73b8d5f73fc8a1d811ea19524449e91df087251` |
| C | `EV12/inputs/hundred/materialization/materialization.json` | `1acb194385a249d48f57794197bfafb8ad3b2f4ba101b20e7a79545fcd91ae18` |
| C | `EV12/inputs/all/materialization/materialization.json` | `84a4d49a76c0c82348644d7268f7033992fc7147d8878332a6fcb57a6d7942f0` |
| C | `EV12/inputs/hundred/materialization-measurement.json` | `ba93211f93d0ee8c966c21f6621f0f96ab97b942088aeabe3097d52013ffcc40` |
| C | `EV12/inputs/all/materialization-measurement.json` | `b270e5ea2fc136693a6d7394d6767b6ea54ec3f18b918c1fcd109d82bd2c13e7` |
| C | `EV12/runs/hundred/out/run.json` | `3512f5d7e33a5d5e731b54df989c00dba39f7ba9d8d5a214fb8139e77eefd5f5` |
| C | `EV12/runs/all/out/run.json` | `9b5bdf9d565a8d82c99b13fa85fd118edf1fd6c1141875451534061ee6fcabc1` |
| C | `measurements/hundred/summary.json` | `946e5730d75212705baf169db7c6adbbb7e56204ea2d1175f53c0f233b18be61` |
| C | `measurements/all/summary.json` | `0b3fe12ab45fcc4329bc5e3ab96768f0fa5889663e52c383a64f322f7876b41f` |

### 9.7 P4-D 結論與後續

- A 段 EV-1～EV-9、EV-13、EV-14 共 11 項已依本紀錄 §1～§7 通過；EV-9 的 PR #232 小修、EV-1／EV-2 的 FIX4 探針及原失敗歷史均保留。本節 EV-10 經 §16、FIX5／U6-FIX3 通過，EV-11 通過，合計 §8.2 要求的 13 項全部通過，**P4-D 通過條件已滿足**。
- EV-12 只量測、不作通過門檻：單一、100 與 20×16 已取得完成量測，1,087 標的只有記憶體保護停止前的部分量測；不能聲稱已完成全標的全訓練窗。BCHUSDT 排除僅供此次量測，正式處理仍待 Operator 裁決。這兩項限制隨 DONE_WITH_CONCERNS 結案保留。
- 本列與本次修補 source 同一 PR 合入後，TODO 的 P4-D CLOSED 才生效。沒有新 Operator 規則裁決，不新增 RH 事件；既有 §16 與 PR #235 的授權均照原紀錄引用。
- §10 的 U4–U6 命令列入口索引與研究工具核心 runbook 另列 PM 的 WAITING 待辦；報告工具的補充指令／P3b 前置已滿足，仍 WAITING，待 PM 撰寫 §9.18 派工並合入；BCHUSDT 等交易所異常列規則先由 Operator 裁決。P5 還須資料品質前檢，不由本次結案自動開工。
- B 段使用真實訓練資料，但只驗證儀器與量測固定範例；沒有假說研究、獲利、Demo／live、部署或交易效果結論。
