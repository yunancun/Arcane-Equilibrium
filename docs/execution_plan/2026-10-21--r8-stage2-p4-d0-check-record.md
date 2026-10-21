# R8 階段 2 P4-D0 檢查紀錄（2026-10-21）

## 1. 目的、依據與發布邊界

- 依 [P4 補充指令](2026-10-20--r8-stage2-p4-research-core-addendum.md) §8.1、§12.4、§13.3、§14.3，記錄 U5 的固定映像煙霧檢查、U6 獨立重算，以及從第一次啟動失敗到 FIX3 九案例通過的完整經過。§12.4 要求本紀錄隨來源發布合入 main，之後才執行 §8.2 的 P4-D。
- 記錄者由 Codex 執行；Claude Code 擔任 conductor，獨立核對與最終把關。conductor 已確認 FIX3 程式審查通過，並獨立重讀九個 `run.json`／`recompute.json` 與凍結預期值雜湊。本次續派依既有 §14.3 發布，沒有新增 Operator 裁決。
- 本紀錄與 U5-FIX3、U6-FIX2 來源由同一 PR 發布；U5／U6 結案及 P4-D 可派發狀態在該 PR 合入後生效。合併由 conductor 在 CI 與自動審查無阻塞後執行，記錄者不合併。

## 2. 固定來源與執行環境

| 項目 | 身分與核對 |
|---|---|
| 發布基線 | `ad50ab78a6be007d9cb3746ebe8a05e786fdbc48`（PR #230）；發布開工 fetch 後 origin/main 未前進 |
| U5 | `R8-S2-ENGINE-LEAN-FIX3-20261021`；`codex/r8-s2-engine-lean-fix3-20261021`；`cac86b74423290e62389eb1370b22b4c5896a9a9` |
| U6 | `R8-S2-ENGINE-SERIES-FIX2-20261021`；`codex/r8-s2-engine-series-fix2-20261021`；`bfa151375c5b640602dbbc4fd71e655db1080a69`；原版未改 |
| 驗收合併樹 | `1ddbdce8ff72abc7d9d262c12434471fa17a3b4c`；整樹 `abff2fc72715941e262c0538f310065088c53197` |
| 程式樹 | 發布分支依序以 `git merge --no-ff` 合入 U5、U6，保留原提交；`git diff 1ddbdce8f -- program_code/` 為空，兩者 `program_code` tree 均為 `f937adce10c9b1ebf637cff486eca08f779a4c85` |
| 固定映像 | `quantconnect/lean@sha256:2657ed3355efb78d78bd0a5d4f126b01367a635e01bccd220b654d7742d182b6` |
| 隔離與資料 | 本機合成資料，U4 `--validation` 物化；最終 9 次 LEAN 與 9 次準備讀取的 Docker 命令全部 `--network none`；輸入掛載在 `/Users` 下 |
| 執行來源 | 正式 `FixedSchedule`；`fixed_schedule.py` SHA-256 `905d8c065eb27dcfeb343cdb8c854ec4cb4f499f0154d10f78bb8edf58dfcb9b`；U6 `series.py` SHA-256 `1b83f74575fb270fc5ae81abb003e1662ba61c1585ac5790218ae67f149fa5fc`；沒有診斷轉接 |

FIX3 依 §14.3 承接 U5-FIX2 至 `eb669cd3c`，排除 `6bb60cf3f`；FIX2 的停止與審查歷史保留。最終驗收的設定與 `run.json` 綁定驗收樹 `1ddbdce8f`，沒有為發布提交改寫歷史輸出。發布只新增本紀錄與狀態文件，不改八個程式／測試檔。

## 3. 經過與失敗紀錄

1. **2026-10-20，第一次啟動器失敗**：交付 `R8-S2-P4-D0-LEAN-SMOKE-20261020` 使用 U5 `540ac84fa`。H 在啟動 dotnet 前以 `launcher key mismatch: algorithm-location` 失敗，沒有模擬步；G、D、L 依停止規則為 NOT_RUN。其空 `fills`、空 `steps` 與組裝的殘差 0 不構成通過。後續記錄者查明固定映像 `config.json` 第 19 行有註解 `algorithm-location`，原正則同時比對註解與有效鍵；只比對未註解的鍵後，H/G/D/L 完成且相符。當時 U6 的計分窗與訂單排列另有不一致，副本診斷修正不作正式交付。
2. **2026-10-21，FIX1 暖機失敗**：U5 `4aada352f`、U6 `60310c74f`。H/G/D/L/P 首次均在暖機第一步失敗並記為 `invalid_decision`。探針證實 pythonnet 將 LEAN `System.Decimal` 轉成 Python 浮點數；.NET 端 `JsonConvert.SerializeObject` 才保留精確現金。副本診斷後五案符合預期、殘差及 U6 重算差異為 0；兩份後續 E2 仍為 FAIL，導出 §13 的正式修補契約。失敗與診斷不能改記為 FIX1 正式通過。
3. **FIX2 首輪回歸停止**：U5 166、U6 171 passed；原指令的完整 research/tests 目錄收集發生 5 個錯誤（三個缺 `program_code`、兩個缺 `pandas`），尚未執行 LEAN 即停止。之後 conductor 續派按 `test_r8_*.py` 執行，兩個合併樹分別為 U5/U6/全部 R8 166/171/732 與 164/171/730 passed。
4. **FIX2 雙版本九案例與診斷**：H/G/D/L/P/Q 兩版均相符、現金殘差 0、原 U6 重算差異 0；N/E 兩版 LEAN 相符、殘差 0，但原 U6 對 N/E/B 均在事件重建前拒絕 `neighborhood`。U5 的 `categorical` 為對應，U6 為軸名清單且要求網格鍵恰等於宣告軸；兩者不能接受同一設定。僅供診斷的轉接後，N/E 兩版及 B 的 `eb669cd3c` 版差異 0，該轉接不作驗收。最初 N/B 因正式範例不支援 `no_trade_at` 而 NOT_RUN；其後受指派的 fixture 診斷另存版本，舊紀錄保留。
5. **B 證實折界錯序**：`6bb60cf3f` 在成交模型內先啟用新折並取消應先入帳的 X，`fills=[]`、`lean_error`。這違反 §3.2 第 1 步；原 FIX2 初審把 §13.2 第 3 點誤讀為原生成交前先取消。`eb669cd3c` 版 X 先以 `100.05` 成交、Y 以 `no_trade` 取消，再於 s 以 `no_trade_flatten` 將 X 平倉（`100.9495`），現金 `100007.88950275` 逐位符合預期。Operator 在 §14 選定 U6 鄰域格式、只修 U5，另立 FIX3。
6. **FIX3 最終驗證**：正式 U5-FIX3＋原版 U6-FIX2 共 9 次 LEAN，全部 completed、與凍結預期逐位相符、殘差 0、`recompute_passed=true`、差異 0。驗收樹本機回歸 U5 222、U6 171、全部 R8 788 passed，全部 0 failed/skipped/error；全部 R8 有兩個未知 asyncio 設定警告。這些是驗收樹的本機結果，發布分支的提交前回歸與 hosted CI 另隨 PR 留證。

### 3.1 最終設定的版本與預期凍結

- H/G/D/L/P/Q 初版只改鄰域形狀、仍為 `grid=[]`，六案都在 LEAN 啟動前以「網格數目不合法」拒絕，未呼叫 Docker、未產生 `run.json`。另存第二版 `grid=[{}]` 後才各執行一次：一個空參數點，`neighborhood={"numeric":{},"categorical":[]}`；`folds=[]`、schedule、資料、成本與預期原樣。
- N/B 的類別軸為 `["n","no_trade_at","schedule","score"]`，E 為 `["n","schedule","score"]`，數值軸皆 `{}`，網格全部鍵均已宣告。正式範例依 §14.2 第 4 點構造前折交易、後折不交易。
- H/G/D/L/P/Q 的 expected 逐位複用 FIX2 dual-rerun；N/E/B 複用 fixture-diagnostic 的最後凍結 `cases-v2`。所有 expected SHA-256 前後相同，未依 FIX3 輸出修改預期。B 預期檔中的歷史 AMBIGUOUS 文字保留，§14.2 第 1 點已裁明原生成交先行，不再是未決規則。
- 初版設定凍結 `2026-10-21T19:54:23.727512Z`，首次 Docker `19:55:33.616690Z`；六案第二版凍結 `19:56:39.247644Z`，其首次 Docker `19:56:39.461840Z`。前置拒絕、兩版設定、命令及新舊雜湊皆在最終證據目錄保留。

## 4. 案例構造與條文對照

| 案例 | 檢查條文 | 構造要點與已核對範圍 |
|---|---|---|
| H | §8.1 的 EV-1、EV-6；§3.1、§9.8 | 小時線固定時點開平倉，開盤與前收不同；高／中／低流動性 5／10／20 bps、雙邊 0.055% 手續費；另構造不足 12 日、單筆上限、min_qty、min_notional 的作廢及減曝險 60 bps 懲罰滑價 |
| G | EV-1、EV-7；§3.1、§3.5 | 下一根及其後一根小時線缺漏，未成交單保留，以第一根存在 K 線的開盤成交；不造前值填補 K 線，核對結束時刻 |
| D | EV-1 的日線分支、EV-7 | UTC 00:00 的日線決策，以次日首根小時開盤成交；核對非日線時刻不決策、成交與終點；策略收到前一日完成日線的直接證據仍 UNVERIFIED |
| L | EV-7；§3 的下架結算規則、§9.8 | DELISTUSDT 於非整點下架，最後不完整 K 線不交策略，下架後不可見；持倉以保守價格及 60 bps 結算，核對費用與現金 |
| P | §12.2 第 7 點、§13.2 第 1 點 | 數量 `0.123`、開盤 `43246.6`、5 bps；成交 `43268.2233`、費 `2.927095306245`、資金費 `-0.667420464474`，超過 15 位有效數字的最終現金精確相符 |
| Q | §13.2 第 2 點、§12.2 第 4 點 | 缺漏的 MID 有未成交單 450，延後成交；BTC 新部位 500，以舊可知 MID 收盤 100 計得曝險 95000/100000=0.95，不把延後送達收盤 300 回填先前價格表 |
| N | §13.2 第 3 點、§14.2 第 3、4 點 | 不交易折起點 BTC 缺漏且有部位 10，MID 缺漏且有未成交單 20，LOW 可見且有部位 30；先取消 MID、平 LOW，BTC 第一次恢復可見時平倉，折內後續交易被抑制；零部位恢復不產生額外決策的完整反例由 U5 回歸測試覆蓋 |
| E | §13.2 第 6 點、§12.2 第 12 點 | 第一計分終點 03:00 無 K 線，MID 於 04:00 以 score_end 取消，平倉取終點前收盤 100 而非後續 1000；第二終點 08:00 先處理界線，再作曝險檢查；未涵蓋 e 後完全無時間步的分支 |
| B | §3.2 第 1 步、§14.2 第 1、4 點 | s=2022-01-15T02:00:00Z，X 成交 K 線開始於 s−1h，先原生成交；Y 成交 K 線開始於 s，仍未成交而取消；X 再於 s 平倉。擬合終點恰在折界與否的兩例由 U5 假 LEAN 流程回歸測試覆蓋 |

## 5. 最終九案例結果

| 案例 | LEAN／預期 | 現金殘差 | recompute_passed | max_difference／differences | 最終現金 |
|---|---|---:|---|---|---:|
| H | completed／逐位相符 | 0 | true | 0／`[]` | `100021.98607725` |
| G | completed／逐位相符 | 0 | true | 0／`[]` | `99997.879` |
| D | completed／逐位相符 | 0 | true | 0／`[]` | `100007.88950275` |
| L | completed／逐位相符 | 0 | true | 0／`[]` | `99972.533959` |
| P | completed／逐位相符 | 0 | true | 0／`[]` | `99988.7886242630335` |
| Q | completed／逐位相符 | 0 | true | 0／`[]` | `103028.18839375` |
| N | completed／逐位相符 | 0 | true | 0／`[]` | `99991.6` |
| E | completed／逐位相符 | 0 | true | 0／`[]` | `99232.705525` |
| B | completed／逐位相符 | 0 | true | 0／`[]` | `100007.88950275` |

九案 `failure_reason`／`failure_t` 均為 null，`unexplained_cash_residual` 均為 `{"per_step":[],"total":"0"}`；原版 U6 每案 exit 0。記錄者另核對 orders、fills、voided、funding、endpoint_funding、steps 的逐位診斷皆無差異，但未用此診斷生成或修改預期。

## 6. 倉庫外證據與 SHA-256

### 6.1 各輪證據目錄

以下目錄均在 `/Users/ncyu/Projects/TradeBot/audits/` 下，表中列完整目錄路徑。既有證據只讀，不為補齊檔名而建立或改寫歷史報告。

| 證據目錄 | REPORT.md SHA-256 | manifest.json SHA-256 |
|---|---|---|
| `/Users/ncyu/Projects/TradeBot/audits/2026-10-20-r8-p4-d0-lean-smoke-173246Z` | 不存在（原證據未採此檔名） | 不存在（原證據未採此檔名） |
| `/Users/ncyu/Projects/TradeBot/audits/2026-10-20-r8-p4-d0-recorder-diag` | 不存在（原證據未採此檔名） | 不存在（原證據未採此檔名） |
| `/Users/ncyu/Projects/TradeBot/audits/2026-10-21-r8-p4-d0-recorder-rerun` | 不存在（原證據未採此檔名） | 不存在（原證據未採此檔名） |
| `/Users/ncyu/Projects/TradeBot/audits/2026-10-21-r8-p4-d0-fix2-rerun` | `01e9b6073f3d4e8f828e16ee80bea6e4f31ef57e5a9373c4b6f291e2eb23581d` | `ae95507d6b206fdd8f9b7d473a3c0129beccbd2c0c79533b3b0de191f9041649` |
| `/Users/ncyu/Projects/TradeBot/audits/2026-10-21-r8-p4-d0-fix2-dual-rerun` | `aff4b4c8636b33b7a8431e3ae88a810b359df7193049c7b85f434e64c43d45f2` | `4365dcb716508ed6b6c0aeb94fc97d3b3a337facc052537b4ee304eadd4c5245` |
| `/Users/ncyu/Projects/TradeBot/audits/2026-10-21-r8-p4-d0-fix2-fixture-diagnostic` | `7dd72d3372de1db6e327936d9496411e65ebe77b85cfacc454ea498a55a203b8` | `643093a58d8cc2733d0f695c605a9216ca9f169e7cd534041505789ebd72796c` |
| `/Users/ncyu/Projects/TradeBot/audits/2026-10-21-r8-p4-d0-fix3-rerun` | `d9b3236c1c94a1328bddfe8d68f6d12a5fbf979924bb510fe72ef7d32901007a` | `2be429f71707e005699c695ca91a2f9db38f87ea6364d9abb8c28686d3bcdcd4` |

前三個目錄的歷史敘事另見補充指令 §12.1、§13.1。第一次的原始正式紀錄保留於 `c9c64b4f45fb2f4f96693bc5e8667f9af24afbc0:docs/execution_plan/2026-10-20--r8-stage2-p4-d0-lean-smoke-record.md`（SHA-256 `0780a0338a7c905c995e81045bbbb360b602f7c957280cc846bd62ac1e4a8e96`），本紀錄收納其失敗經過，不改原停止判定。

| 歷史原始證據檔（相對上述 audits 根目錄） | SHA-256 |
|---|---|
| `2026-10-20-r8-p4-d0-lean-smoke-173246Z/handoff.json` | `58b2e7c990c0696f886beac198a75ab5574a428b63fce42f6b4aca893ef8bcf9` |
| `2026-10-20-r8-p4-d0-lean-smoke-173246Z/execution-evidence-hashes.json` | `c6f795f72d538a0f904b9488b28fda81d246a89845c676af9bb04be958778a92` |
| `2026-10-20-r8-p4-d0-lean-smoke-173246Z/cases/H/lean-output-attempt1/run.json` | `1da8361f91269e762016bd5ffa152cbbdd7b9fa4f6cf434adef191083cb45661` |
| `2026-10-21-r8-p4-d0-recorder-rerun/case-matrix.json` | `e9335ead0ede8be48a50a52eacd1845b68eec19aa4d421f43d638e7455381066` |
| `2026-10-21-r8-p4-d0-recorder-rerun/fixture-provenance.json` | `6f92aa6d4a5398c7f61e03216adc5aa524a4e29b5fbd7ed2e4babf4067c4e1e8` |

FIX2 各輪 manifest 已保存逐檔清單及先前證據綁定；最終 manifest 同時保存命令、來源、設定、預期、輸出與上輪完整性核對。沒有把 FIX2 的診斷轉接資料列為最終驗收輸出。

### 6.2 最終九案例逐檔清單

下表路徑相對 `/Users/ncyu/Projects/TradeBot/audits/2026-10-21-r8-p4-d0-fix3-rerun/`。
`shared-config.json` 是共用設定，`config.json` 是實際執行的完整提交綁定設定；兩者分別列雜湊。expected、run 與 recompute 逐檔計算並與封存 manifest 核對，recompute 的 `run_sha256` 亦與 run 原檔相符。

| 案例 | 檔案 | SHA-256 |
|---|---|---|
| H | `cases-v2/H/shared-config.json` | `aa65142c112b34eac7befee182483dac0f2a69df3020206572e5b77d4d0bc572` |
| H | `runs-v2/H/config.json` | `92d03486fcea3ecfdf089db54c0dd18cc47c8f07d2fcfd68b971eb293cc83071` |
| H | `cases-v2/H/expected.json` | `21640cca447b12b0c83d687dc57f98c97d4b03651523a02436cbf0276ea5e02d` |
| H | `runs-v2/H/out/run.json` | `2a9940785f0e0d207dcdb91fe3fc41a87ee42caca216046f2c95e4a52e5eca29` |
| H | `runs-v2/H/recompute.json` | `a22d164893f98fc1a89faf79cd0288c553b741f0803c86d853c516762e646404` |
| G | `cases-v2/G/shared-config.json` | `de02f1ee61ad34bbd6dc74974688ba7ffdf53083755ae9d7ad3489044f81106e` |
| G | `runs-v2/G/config.json` | `d75b82466e7d9b6240fd48ef0667c6471f2e65deec80d6fbb460188517c52163` |
| G | `cases-v2/G/expected.json` | `caae32fb7da8785fecf23921f98c578f686baf04ba08750840a616c22ca8eaeb` |
| G | `runs-v2/G/out/run.json` | `4438cf6eac70fd30dd6e762e481c68fa362d1534b4e294602c5a454af2f325d6` |
| G | `runs-v2/G/recompute.json` | `d8750771628e1567fe9d7be5b922fdcffe944d06c3c7ceee265155d04234cd20` |
| D | `cases-v2/D/shared-config.json` | `50e59afd154484a720648d14628c0df210e12f6e80f6709d35faa5a211ec080c` |
| D | `runs-v2/D/config.json` | `6b08e9da118238aae5f8935b3610c3f3e437121af510186ed421b8f41d6b09fd` |
| D | `cases-v2/D/expected.json` | `f65580f9d7265bdd53a4c96df45640c6f1e764f8ff7fbd0dd4ec194e35478098` |
| D | `runs-v2/D/out/run.json` | `33492a2a34b05727329f40e661e35b984f5e9342ce10f4471b8120159276176b` |
| D | `runs-v2/D/recompute.json` | `3a96d813551da2136f565b771c8fd76b4198b626732c7eba30a2b2c0e9ab78ee` |
| L | `cases-v2/L/shared-config.json` | `35a93007314d3cbd153ccfc3f73bd21826b430fb8cfba3d722d5d949f1e75bda` |
| L | `runs-v2/L/config.json` | `873158f5dd6fa37742f3e862cf53ddb9c26fc4e6e6d4f9c7f482cd99c35f8f1a` |
| L | `cases-v2/L/expected.json` | `fae5385468b7a2bb773c1445edaf19ea515bd9b7559b39dd500b29d8bff561a9` |
| L | `runs-v2/L/out/run.json` | `893166b7c1ccc0a3e6eff248700749a95b98c23403a20aa9282c00a415037682` |
| L | `runs-v2/L/recompute.json` | `135fc4ca298beaa2fefe798e4727034fc2efe37ed6de34208e8d0f8f6424a8f4` |
| P | `cases-v2/P/shared-config.json` | `0eb18aeefe50c1470e633d98d39398fe95339d0e1a65be29fe3bb6587fecf0d6` |
| P | `runs-v2/P/config.json` | `58a7ed1cce61eb5f55c4f08d574b18f2b516f9477e28871ec3f37a41fcaa9c49` |
| P | `cases-v2/P/expected.json` | `0a82613994a7200cbb6835adee36c1f6f5e7794d5a6da1e4cf3e8738684e6407` |
| P | `runs-v2/P/out/run.json` | `51a06b94085330f9a4e8644153e76bfe68c2117ce806fc7511c15876b6f74c09` |
| P | `runs-v2/P/recompute.json` | `7e00b3ed9f567590d49741a72df8349d457d68ca5371cfab097678e66076b98c` |
| Q | `cases-v2/Q/shared-config.json` | `187468bfc508a8ca7be122169782345aef9b72816a5788bf275a06c0be03f8c7` |
| Q | `runs-v2/Q/config.json` | `f8f9f8cd6a2866cfc03724fdc06b304d193d2edb963dacd00ceb3793a20e38f4` |
| Q | `cases-v2/Q/expected.json` | `ae6ad5fc66f5e975d668ff6bbe2b6f3a9f8e3d5b23ef446a8bac86d281b84266` |
| Q | `runs-v2/Q/out/run.json` | `90b1d2d920c792334556a234919488af9c6e65e9e761a2ade5788b4637e537e6` |
| Q | `runs-v2/Q/recompute.json` | `a8b23fd29ae3f593a7a032bd7da4d0d39c165753f617ac5abb3c2d132f839038` |
| N | `cases/N/shared-config.json` | `174f2534838f219d97a54eb24073637549f71fee56dfa5e17bd24e56fd4c296f` |
| N | `runs/N/config.json` | `58bbb4c33f4b89aa0ec05f11298cd975e1b457f18aad6facf8feab2b9104ac33` |
| N | `cases/N/expected.json` | `beb0cdbfa9192a03556b44c1ca5d8ba564824a59ab46d2be11ab34ca5e24e4fa` |
| N | `runs/N/out/run.json` | `275ce4739d9a449cb2edfb172d64d3d2ae089e01e80b3634e50359154306f971` |
| N | `runs/N/recompute.json` | `a668fedb350f1a743a14cf0e4d3c5014c6aba1b34fecbed70bd758e19a065cf9` |
| E | `cases/E/shared-config.json` | `930d6a8dc46fdbb6f3a3c08a54b0e6979198df4c5261db119ef2479c44b1919b` |
| E | `runs/E/config.json` | `e5bfed1ff36339b69f71bf16b54b02cff121561f50893445567ec991d9ff71b0` |
| E | `cases/E/expected.json` | `46207f5167552bc40b00690aa7b705e86caef89cad318c23b8f8b87786842f66` |
| E | `runs/E/out/run.json` | `da0bf91dd821f7a37cb5837bbe72bbdde6ffe258849d61155f3752310f10a0d1` |
| E | `runs/E/recompute.json` | `8f5b1ba270637c6777e9b22b646041998e53af2a7951a4c93c3d95e14a00aef5` |
| B | `cases/B/shared-config.json` | `686473984bf1921fc45ce6f1bcb73bb7346087701b5ca032db26ec08180804e9` |
| B | `runs/B/config.json` | `c7d4a11783135f15c479d39695c3fe36316d40ba32f4547529df1ac270948ea9` |
| B | `cases/B/expected.json` | `f09154dbff1731db1ccb6bdf992049861247de7c6aad6dd6b9c105f1ab8619ad` |
| B | `runs/B/out/run.json` | `0239f1c7306264540f21f0c4248cf2c29847430db9f0e93f25c8ba1a333ba32d` |
| B | `runs/B/recompute.json` | `6c10954e2f5b587b72dbb2f744dc4d14cb69348a39b29babb7efc2480ba9d036` |

## 7. 限制與後續

- **D 的策略端日線可見性直接證據仍為 UNVERIFIED**。日線決策與成交時刻相符不能替代 EV-1 要求的策略所見資料證據，須在 P4-D 補足。
- Q 的曝險參照價格表沒有獨立 telemetry；本次依未修改來源及反例行為核對。E 未覆蓋 e 之後完全無時間步、於 window.end 取消的分支。N、B 的上述額外反例只屬 U5 回歸覆蓋，不冒充九案例另有固定映像執行。
- 本紀錄只涵蓋 P4-D0 的構造檢查與 §13／§14 修補驗收，不代表 §8.2 的 EV-1 至 EV-14 已全部執行或 P4-D 通過。沒有真實市場資料檢查、假說研究、獲利、Demo／live、部署或交易效果結論。
- U4 已隨 PR #227 合入，P3b 已完成；本 PR 把 U5／U6 來源與本紀錄合入後，P4-D 的解除條件才全部成立。PM 依 §8.2 派記錄者執行 EV-1 至 EV-14（EV-12 只量測）；不是本次發布工作的續跑授權。
- §10 的記錄者收尾列為 P4-D 期間待辦：在 `helper_scripts/SCRIPT_INDEX.md` 登記 U4–U6 命令列入口，並撰寫研究工具核心 runbook。本 PR 不實作這兩項。
- 最終固定映像驗證時段：`2026-10-21T19:53:08Z` 至 `2026-10-21T19:58:54.799619Z`。本次發布的提交前測試、CI、自動審查與 UTC 起訖另隨 PR 回報，不覆寫驗收時段。
