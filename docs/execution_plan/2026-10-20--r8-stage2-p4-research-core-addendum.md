# R8 階段 2 P4 補充指令：研究工具核心

| 項目 | 內容 |
|---|---|
| 文件性質 | 階段 2 派工指令 §5 P4 所稱的補充指令。不是授權文件；是否可派發以 [TODO](../../TODO.md) 的對應各列為準 |
| 日期 | 2026-10-20 起草；同日記入 Operator 對 §9 三項的裁決（事件 `RH-20261020-01`），並依 QC、R4、PA 的審查修訂（Asia/Shanghai） |
| 依據 | [R8 修訂二](../decisions/2026-10-14--r8-amendment-2-multi-strategy-first-loop.md) N3 第 4、5 點、N4 第 1、3 點、N5 與其註記；[階段 2 派工指令](2026-10-14--r8-stage2-local-research-dispatch.md) §5 P4、§7.4、§7.5、§8；[選型查核紀錄](2026-10-19--r8-stage2-p1-engine-selection-record.md) §4.5、§5（選型定為 LEAN，事件 `RH-20261019-01`）。§9 由 QC 起草，記錄者整合 |
| 前提 | main 含本文件。P4-D 以 P3b 的資料執行。U4 至 U6 的實作與單元測試不需要真實資料，可以先開工 |
| 投入上限 | 計入階段 2 至 3 的十個工作日（修訂二 N8 與其裁決註記）。每個單元回報開始、結束時間與投入工時 |
| 不在範圍 | 見 §1.2 |

本文中的「實作者」「記錄者」與階段 2 派工指令的用法相同。U4 至 U6 是本文新增的實作單元，編號接續階段 2 派工指令的 U1 至 U3。
文中的事件級檢查以 `EV-` 編號，與審查角色的代號（E2、E4 等）區分。

## 1. 範圍

### 1.1 要交出什麼

| 修訂二與階段 2 派工指令的要求 | 本文的落實 |
|---|---|
| N4 第 1 點：以本機構造的資料檢查資料何時可知、何時可成交、指標預熱、資金費結算時點與狀態轉移 | §3 的規則；U4 至 U6 實作；§8 的事件級檢查由記錄者在 LEAN 中執行 |
| N3 第 4 點：雙邊吃單手續費、滑點基準與壓力測試、資金費以歷史實際費率在結算點計入 | §3 的規則與 §9.8 的數值；U5 的成交、手續費與資金費；U6 的獨立重算與壓力重算 |
| 階段 2 派工指令 §5 P4：資料載入器讀 holdout 時必經 U2 的「開啟」，並依 U2 第 5 點的暖機規則讀取暖機資料 | U4 以帳本的唯讀查詢決定可讀的區間；U5、U6 只讀 U4 的輸出 |
| 階段 2 派工指令 §7.5：預登記所需的 14 項方法論參數 | §9.1 至 §9.14 |
| 階段 2 派工指令 §8.6 第 5 點：下架品種的最後一根 K 線、下架時刻的資金費 | §9.8.4 至 §9.8.6 |
| 選型查核紀錄 §4.5 的四項發現與兩則附註 | 科學記號：§4 第 4 點；手續費依成交價：§3.4；前值填補：§3.5；下一根開盤成交：§3.1；資金費的計價基礎與費率來源：§9.8 |

階段 2 派工指令 §5 P4 與 U2 第 6 點原寫「以試驗帳的輸入呼叫既有 DSR 閘門」。階段 2 派工指令 §7.4 改由研究帳本自行計算 DSR，§7.5 並規定研究帳本不呼叫既有閘門；本文依此，不使用 `program_code/learning_engine/dsr_gate.py`。

### 1.2 不在範圍

- 秒級與依賴逐筆資料的假說。第一代不登記秒級假說（事件 `RH-20261018-02`）；依賴逐筆資料的分鐘級事件型假說，記錄者的保守落實同樣不登記（階段 2 派工指令 §4 的註記）。
  因此本文不建逐筆模擬與 300 毫秒延遲的成交模型。這是記錄者依上述裁決收窄的範圍，不是 Operator 另行裁決；秒級或逐筆假說登記之前，另以補充指令處理。
- 1 分鐘 K 線的物化；限價單與掛單成交模型；標記價格 K 線與交割價格的取數。
- 報告工具：9.18 的資料品質前檢，以及 §9 的 N_eff、區塊自助法、行情標示、集中度與事後貝塔的計算，另立單元（§10）；前者須在 P5 之前完成。
- 假說本身與其試驗；Linux、資料庫、Demo、live；任何交易效果。

### 1.3 分工與授權

| 編號 | 內容 | 執行者 | 先後 |
|---|---|---|---|
| U4 | 資料物化與帳本的唯讀查詢（§4） | 實作者 | 與 U5、U6 平行 |
| U5 | LEAN 研究框架與執行器（§5） | 實作者 | 同上 |
| U6 | 帳本序列、獨立重算、基準序列與成本壓力重算（§6） | 實作者 | 同上 |
| P4-D0 | U5 代碼審查通過後的 LEAN 煙霧檢查（§8.1） | 記錄者 | U5 代碼審查通過之後，不等合入 |
| P4-D | 事件級檢查、成本壓力檢查與執行時間量測（§8.2） | 記錄者 | U4 至 U6 經獨立驗證並合入 main，且 P3b 完成之後 |
| P5 | 假說預登記草案，送 Operator 覆閱 | 記錄者 | P4-D 通過之後（階段 2 派工指令 §5 P5 的前提另加這一項） |

- 階段 2 派工指令 §1 已列「P4：記錄者撰寫，實作者執行」。U4 至 U6 是三個新的交付身分，U4 另修改 U2 的 `ledger.py`（階段 2 派工指令 §2.3 原只允許新增檔案）。
  依 `AGENTS.md`，新交付身分須 Operator 明示確認。Operator 的確認：2026-10-20 已確認（在對話中確認三個交付）。
- 三個單元之間只經 §7 的介面（含 §4 第 4 點的檔案格式）相接，任何一個單元都不得改動另外兩個單元的檔案。

## 2. 共同規則

階段 2 派工指令 §2 照舊適用，以下列差異為準：

1. 交付名稱：`R8-S2-ENGINE-DATA-20261020`（U4）、`R8-S2-ENGINE-LEAN-20261020`（U5）、`R8-S2-ENGINE-SERIES-20261020`（U6），`work_item_id` 與 `lane_id` 都用這三個名稱。
   各開新的 worktree 與分支：`codex/r8-s2-engine-data-20261020`、`codex/r8-s2-engine-lean-20261020`、`codex/r8-s2-engine-series-20261020`。
2. 三個單元從**同一個**含本文件的 main commit 開工，把完整 commit 記下來，task contract 與 context 都綁它；main 上找不到本文件就停止並回報 `NEEDS_CONTEXT`。
   task contract 的 surfaces 須含 `agent_workflow`。開工之後 main 若前進，不要自行 rebase。
3. 套件 `program_code/research/r8_engine/` 的 `__init__.py` 已由本文件所在的 PR 建立，三個單元都不改它。
4. 主機端的程式只用 Python 標準函式庫，相容 Python 3.10；測試另外只用 pytest，全部離線、封鎖 socket。
   - 主機端模組可匯入的範圍：標準函式庫、`program_code.research.r8_engine` 與 `program_code.research.r8_ledger`。每個單元各有一個 AST 檢查，確認自己的主機端模組只匯入這三者。
   - 標準化 JSON 一律匯入帳本的 `canonical`，不另寫一份。
   - 測試檔名必須符合 `program_code/research/tests/test_r8_*.py`，GitHub CI 的研究測試項目才會執行。測試以絕對匯入載入模組；受控測試若移除工作目錄，比照 PR #225 在測試檔的匯入處把倉庫根目錄加入 `sys.path`。
   - 本機在倉庫根目錄以 `python3 -m pytest` 執行（Python 3.10；這台機器上是 `/usr/local/bin/python3`）。
   - 命令列入口都有 `if __name__ == "__main__":`。
5. U5 在 LEAN 容器內執行的模組（`lean_algo/framework.py` 與範例演算法）例外：它們匯入 `AlgorithmImports`，不在主機端匯入、不列入 AST 檢查，也不能由 pytest 執行。
   這部分的正確性由 §8 的煙霧檢查與事件級檢查驗收。實作者不需要、也不應自行執行 docker。
6. 不碰：`TODO.md`、`docs/` 下的任何檔案、`helper_scripts/SCRIPT_INDEX.md`、`CHANGELOG.md`、`program_code/research/r8_data/`、
   `program_code/learning_engine/`，以及各單元「可改檔案」以外的任何檔案。需要改到清單外的檔案才能完成時，該單元停止並回報。
7. 實作者不執行實際取數，也不讀真實資料；不連 Linux、資料庫、Demo 或 live；不部署。
8. 計時器、審查與交付方式同階段 2 派工指令 §2.4、§2.6；PR 標題分別以 `R8 S2 U4`、`R8 S2 U5`、`R8 S2 U6` 開頭。
   受控測試驗證無法執行時，代碼審查通過後停止，把提交留在本機分支並回報。
9. 本文的數值（費率、滑點、δ、門檻等）一律由執行設定傳入，不寫死在程式中；程式只實作規則。
10. §3.9 的固定案例是 U5 與 U6 共同的驗收輸入：兩個單元各自的測試都必須逐位重現表中的結果。

## 3. 時間語義與成本的規則

本節是 U4 至 U6 共同遵守的規則；數值見 §9。§8 的檢查逐項驗證。

### 3.1 何時可知、何時成交

- K 線以開始時刻 t 標示，涵蓋 [t, t + Δ)，在 t + Δ 才可知。LEAN 在 t + Δ 送達該根，沒有前視（P1b）。
- 策略在 t + Δ 收到該根後決策。市價單以**下一根的開盤價**成交，也就是時刻 t + Δ 的開盤價，再依 §3.4 加上不利方向的滑價。不得以剛收到的那根的收盤價成交（選型查核紀錄 §4.5 第 4 點）。
- 部位變動的時刻記為 t + Δ。LEAN 在下一個時間步（t + 2Δ）才發出成交事件，且在該步的 `on_data` 之前處理（PA 2026-10-20 在映像中以探針確認）；`run.json` 與獨立重算一律以 t + Δ 為部位變動時刻。
- 下一根缺漏時，以缺漏之後第一根存在的 K 線的開盤價成交，部位變動時刻為那一根的開始時刻；該期依 §9.14 計為填補期。
- 下架品種最後一根不完整的 K 線：可以在它的開盤成交（價格真實存在），但它不交給策略作決策（§9.8.5）。
- 作為訊號的資料，以下列時刻為可知時刻（§9.0 第 4 點）：
  - 資金費：其結算時刻；不使用預測資金費；
  - 持倉量：時間戳 t 的值在 t + 4 小時才可知（交易所的時間戳是區間起點還是終點，未驗證，取保守值）；
  - 成交額：所在 K 線的結束時刻。
- 第一代只用市價單，全部視為吃單。

### 3.2 時間步內的順序與權益取樣

每個時間步 s（一根 1 小時 K 線的結束時刻）依下列順序處理：

1. 決策時刻在 s − Δ、以 s − Δ 的開盤價成交的訂單入帳（LEAN 原生，`on_data` 之前）；
   之後，`deliveryTime` 不晚於 s 而尚未結算的品種，由框架先取消其未成交的訂單，再依 9.8.6 下架結算（價格用已送達的最後一根，含不在整點下架時的那一根不完整的 K 線），部位變動時刻記為 `deliveryTime`；此後該品種不交給策略；
2. 策略收到結束於 s 的 K 線，決策；框架完成作廢判定，送出將以 s 的開盤價成交的訂單；
3. 結算時刻 T < s 且尚未計入的資金費，依 §3.3 計入。T 前與 T 後的部位一律由成交紀錄依實際的部位變動時刻重建：T 前 = 部位變動時刻早於 T 的成交累計，T 後 = 部位變動時刻不晚於 T 的成交累計；不取 LEAN 在 s 的持倉，也不取尚未成交的訂單。
   結算時刻恰為 s 的那一筆，要等以 s 的開盤價成交的訂單入帳（下一個時間步的第 1 步）之後才知道 T 後的部位，所以在下一個時間步計入；下一根缺漏、訂單較晚成交時，它的部位變動時刻晚於 T，不算進 T 後的部位；
4. 記錄時間步 s 的現金、權益與部位。

兩種權益要分開：
- **時間步權益**：上述第 4 步記錄的值，用於 LEAN 與 U6 的逐步比對；U6 依同一順序（含「恰在 s 的資金費在下一步計入」）重建。
- **期初權益 E(s)**：帳本序列用的值，由 U6 依時間戳計算：含部位變動時刻早於 s 的全部成交、結算時刻早於 s 的全部資金費，以結束於 s 的 K 線收盤價計價。
  在每一個期界 s，以 s 的開盤價成交的那一筆（含其手續費與滑價）與結算時刻恰為 s 的資金費，都屬於從 s 開始的那一期。
  帳本序列只以 U6 計算的 E(s) 產生，不依賴 LEAN 在每個期初都有時間步（§6 第 1 點）。
- 連續計分區間終點 e 的例外：e 之後沒有下一期，所以 E(e) 另含部位變動時刻為 e、種類為 `score_end_liquidation` 或 `delisting_settlement` 的成交（§3.5 的平倉成本、恰在 e 的下架結算），以及結算時刻恰為 e 的資金費，使它們計入最後一期；
  測試涵蓋終點仍有部位、恰在終點下架、期界恰為資金費結算時刻，以及相鄰計分窗之間部位延續、不平倉的情形。
- 連續計分區間的起點 s₀ 依上述一般規則處理：起點之前部位為 0（§3.5），E(s₀) 就是當時的現金，s₀ 的開倉成交與恰在 s₀ 的資金費都計入第一期。
- 結算時刻恰為執行終點的那一筆，LEAN 沒有下一個時間步可計入；它只進入 U6 依時間戳計算的 E(終點)，時間步權益與期末權益的比對都不含它；框架把它寫入 `run.json` 的 `endpoint_funding` 段（格式同 `funding`，未計入 LEAN 現金），U6 據此比對。
- 決策時換算目標權重所用的權益（§3.7）是第 2 步時的時間步權益，不含恰在 s 的資金費；U6 依此重算。下架結算的成交，部位變動時刻記為 `deliveryTime`。

### 3.3 資金費

- 依 U1 的歷史紀錄，在每一筆紀錄的結算時刻 T 計入；不以現行間隔推算。
- 金額依 §9.8.3：以 T 之前與 T 之後兩個部位中，資金費現金流較不利的那一個計算，並加上不利調整 δ。
- 多頭在正費率時支付、負費率時收取；空頭相反。
- 資金費紀錄的空白、下架時刻的那一筆與下架之後的紀錄，依 §9.8.4、§9.8.7。空白的判定是規則的一部分：`rules.py` 與 U6 各自由可讀的資金費紀錄判定，不由 U4 提供。
- 資金費由框架以直接調整現金計入（`Cash.AddAmount`），LEAN 原生的資金費關閉（`MarginInterestRateModel.NULL`）。兩者 PA 已在映像中確認可行。

### 3.4 手續費、滑價與作廢

- 手續費 = |成交數量| × 成交價（含滑價）× 費率，開倉與平倉雙邊計入，在成交事件中設定；LEAN 的手續費模型設為 `ConstantFeeModel(0)`。
  否則 LEAN 的權益會先扣除一筆估計的平倉手續費，與重算不一致（PA 已確認）。
- 滑價以基點表示，對買單加價、對賣單減價，作用在開盤價上；依決策時可知的流動性分級（§9.8.2）。成交價不取整到最小跳動單位。
- 數量：由目標權重換算後向零取整到 `qtyStep`。變動量小於 `minOrderQty`，或名目（變動量 × 決策價）小於 `minNotionalValue` 時作廢，原因 `min_qty` 或 `min_notional`；全部平倉例外，一律執行。
  兩者與倉庫現行的 Bybit 檢查一致（`symbol_category_registry.py` 分別檢查最小數量與最小名目）。
- 每個標的同時至多一筆未成交的訂單：新的決策到來時，先取消該標的尚未成交的訂單，再以實際部位（不含未成交的訂單）計算差額並下單；取消記入執行紀錄的 `orders`（§7.2，含被取代的訂單代號）。U6 依同一規則重算，取消與取代的對應必須一致。
- 反手（部位跨過 0）以一筆複合訂單表示，含兩段：減少曝險的一段（到 0）一律執行，增加曝險的一段依 §9.8.2 判定是否作廢；兩段在同一根的開盤成交，各自計手續費與滑價。
  複合訂單在「每個標的至多一筆未成交訂單」中算一筆；作廢只作用於增加的一段（`orders` 中記為同一 `order_id` 的兩段，`voided` 記增加的一段）。
- 增加曝險的訂單依 §9.8.2 作廢；減少曝險的訂單在「不可開倉」等級或超過單筆上限時，以懲罰滑價成交，記為 `forced_reduce_penalty`。
- LEAN 拒絕任何訂單（例如保證金不足），即視為該次執行失敗。

### 3.5 前值填補、執行期間與暖機

- 每一個訂閱都關閉前值填補；回測中出現前值填補的 K 線，即視為該次執行失敗（選型查核紀錄 §4.5 第 3 點）。
- `SetEndDate` 會延伸到當日結束；關閉前值填補之後，回測在最後一根資料的結束時刻結束（PA 已確認）。執行的結束時刻以最後一根資料為準。
- 缺漏期間不前值填補、不內插：缺漏的標的在缺漏期間以缺漏前最後一根的收盤價計價（不產生新的 K 線，也不交給策略），它在缺漏期間的損益貢獻為 0，跨過缺漏的價格變動計入缺漏之後第一根所在的那一期（§9.14）。
  同一期內其他標的的損益、手續費與資金費照常計入；每期報酬仍依 §3.7 以帳戶權益計算，不把整期記為 0。
- 暖機由框架實作，不使用 LEAN 的 `SetWarmUp`：回測從暖機區間的起點開始，暖機期間不下單、不計分。
- 計分區間以外（第一個計分起點之前、各計分窗之外）不得有部位：框架拒絕在計分窗外下單；第一個計分起點時部位必須為 0。
- 相鄰的計分窗合併為一段連續計分區間（樣本外的 16 折首尾相接，合併為一段；holdout 是另一段）。相鄰計分窗之間不平倉：部位延續到下一折，新一折的第一次決策以實際延續的部位計算差額。
- 每段連續計分區間的終點 e 仍有的部位，以結束於 e 的那根 K 線的收盤價（該根缺漏時，取 e 之前最後一根的收盤價，最後一期計為填補期）、加 §9.8.2 的懲罰滑價（60 bps 乘以壓力倍數，刻意不用該級滑價，屬保守取法）與手續費，計算平倉成本，記為 `score_end_liquidation`、部位變動時刻為 e，計入最後一期；不讀 e 之後的資料。
  在 e 不再有新的決策，所以平倉與決策沒有先後問題。平倉之前，先取消所有尚未成交的訂單（例如下一根一直缺漏到 e），在 `orders` 記為 `cancelled`、原因 `score_end`。

### 3.6 暖機與可讀範圍

- 可讀範圍依 U2 第 5 點與階段 2 派工指令 §7.4 第 4 點：
  - 樣本外範圍 = [訓練段起點, 驗證段終點)，含中間的空窗（帳本 `_validate_trial` 以這段為 `allowed`）；
  - 本世代的 holdout 段：只有 holdout 已開啟、且本假說在候選之中時可讀；
  - 緊接在可讀 holdout 段之前的空窗，只可作暖機。
- 暖機長度取自該假說預登記的「最長回看」（帳本欄位 `max_lookback_seconds`）。帳本已把第二段 holdout 的起點依最長回看往後移（U2 第 5 點），所以第二代的暖機不會落進第一段。
- 流動性分級需要決策前 12 個完整日的日線成交額（§9.8.2），因此每個假說登記的 `max_lookback_seconds` 不得小於 13 日（1,123,200 秒）。
- 暖機落在 U1 的資料範圍起點（2020-01-01）之前的部分，允許且為空；輸出 manifest 記為限制。暖機落進其他不可讀的區間時，U4 拒絕物化，不以縮短暖機代替。

### 3.7 部位與權益

- 策略以目標權重表示部位：權重 = 帶正負號的名目 ÷ 決策時的權益；換算以決策時最後一根已收盤 K 線的收盤價為準。
- 初始資金 100,000 USDT（§9.0 第 2 點）；各標的槓桿設為 10 倍，使購買力在總曝險 1 倍以內不構成限制。
  各假說的總曝險上限在預登記時寫明，不得超過 1 倍；需要更高時另行說明並經量化方法論審查。
- 總曝險上限以 `gross_exposure_cap` 傳入執行設定。每次決策後，框架以取整與作廢之後的目標部位、**決策時的價格**（換算數量所用的收盤價）與決策時的權益計算總曝險 Σ|數量 × 決策價| ÷ 權益；超過上限即中止該次執行並標記失敗，不縮放、不部分執行。
  U6 以同一規則、同樣的決策時價格重算。成交價與決策價的差異造成的實際曝險超出不構成失敗，只報告每一步的實際最大總曝險。
  成交不同步也要檢查：每個時間步的成交入帳之後，框架以實際部位、最近一次決策的決策價與決策時的權益計算 Σ|實際數量 × 決策價| ÷ 權益（以決策價計價，排除價格漂移）；
  例如輪動時減倉的標的下一根缺漏、加倉的標的照常成交，實際部位暫時超過上限，即中止並標記 `gross_exposure_cap` 失敗（失敗的處理見 §6 第 1 點）。預登記時，總曝險貼近上限的輪動設計應保留餘裕。
- 觸發 LEAN 的追加保證金或強制平倉，即視為該次執行失敗。
- 未實現損益以時點或之前最後一根已收盤 K 線的收盤價計價。一期的淨報酬 = E(期末) ÷ E(期初) − 1；手續費、滑價與資金費都已含在權益內。

### 3.8 策略可見的資訊

- 策略只看得到首根 1 小時 K 線已收盤、且尚未過 `deliveryTime` 的標的；完整的標的清單、首根時刻與下架資訊只有框架可見（§9.0 第 4、5 點）。
- 框架覆寫下單函式，只允許框架內部呼叫；策略直接下單即中止。
- 執行器在執行前以靜態檢查審核假說的演算法檔：只允許匯入框架、`rules.py` 與標準函式庫中的數學類模組；不得有檔案或網路存取、不得存取底線開頭的屬性、不得呼叫下單函式；
  不得呼叫 `random` 模組層級的函式（只能用 `random.Random(self.random_seed)`）；不得有 `global`、`nonlocal`，不得對模組層級的名稱或類別屬性賦值（使不同實例之間無法經由模組或類別共用狀態，§5 第 2 點）。以程式無法完全排除的共用途徑，列為殘餘風險。
- Python 無法在同一程序內隔離資訊；靜態檢查與覆寫之外的殘留風險，回報時列明。

### 3.9 固定案例（U5 與 U6 都必須逐位重現）

以 `decimal.Decimal` 計算。費率 0.055%，δ = 2%，滑價依表內所註。「逐位重現」指數值相等；寫入 JSON 時，數值字串一律為 `format(d.normalize(), 'f')`（例如 `100.1`、`-5.176755`、`0.9443`、`100`），使兩個單元的輸出位元組相同。

| 編號 | 情形 | 輸入 | 結果 |
|---|---|---|---|
| G1 | 開倉買入 | 權益 100,000；權重 0.5；決策價（收盤）99.50；`qtyStep` 0.1；下一根開盤 100.00；10 bps | 數量 502.5（502.5125… 向零取整）；成交價 100.10；手續費 27.6651375 |
| G2 | 平倉賣出 | 部位 502.5；下一根開盤 101.00；10 bps | 成交價 100.899；手續費 27.885961125 |
| G3 | 平倉於 T | T 前 +502.5、T 後 0；P_T 101.00；費率 +0.0001 | T 前現金流 −5.07525，T 後 0；取較不利者 −5.07525；乘 1.02 得 **−5.176755** |
| G4 | 持有空頭，費率為正 | T 前後都是 −502.5；P_T 101.00；費率 +0.0001 | 現金流 +5.07525（有利）；乘 0.98 得 **+4.973745** |
| G5 | 開倉於 T | T 前 0、T 後 +502.5；P_T 101.00；費率 +0.0001 | 較不利者為 T 後 −5.07525；乘 1.02 得 **−5.176755** |
| G6 | 下架時刻的那一筆 | T 前 +502.5、T 後 0（下架）；P_T 1.00；費率 +0.02，另一例費率 −0.02 | 費率 +0.02：−10.05 乘 1.02 得 **−10.251**；費率 −0.02：T 前 +10.05、T 後 0，較不利者為 0，**不計** |
| G7 | 下架結算（多頭） | 最後一根低點 0.95、前一根完整 K 線低點 0.97；懲罰滑價 60 bps | 結算價 0.95 × (1 − 0.006) = **0.9443**；手續費 = 數量 × 0.9443 × 0.00055 |
| G8 | 反手 | 部位 +100 → 目標 −50；增加曝險的一段被作廢 | 減少曝險的一段 −100 照常成交；結果部位 0 |

## 4. U4 `R8-S2-ENGINE-DATA-20261020`：資料物化與帳本的唯讀查詢

**為什麼**：LEAN 讀取掛載進容器的資料目錄，U6 讀取 U1 的資料列。holdout 與暖機的規則只能在「寫出來的資料」上落實，所以由物化工具依帳本決定可讀的區間，只寫出允許的資料列；U5 與 U6 都只讀它的輸出，不讀 U1 的檔案。

**可改檔案**：
- 新增：`program_code/research/r8_engine/materialize.py`、`program_code/research/tests/test_r8_engine_materialize.py`、`program_code/research/tests/test_r8_ledger_access.py`；
- 修改：`program_code/research/r8_ledger/ledger.py`，只新增第 1 點的兩個唯讀方法，不改既有行為；既有的 `test_r8_ledger.py` 不改。`test_r8_ledger_access.py` 自行建構測試紀錄，不從 `test_r8_ledger.py` 匯入。

**要求**：

1. **帳本的唯讀查詢 `ResearchLedger.data_access(hypothesis_id, trial_id=None)`。**
   - 與 `verify_heads` 相同，只取 `_lock` 並以 `_read` 驗證三本帳的鏈接；不呼叫 `_write_lock`，不寫入任何紀錄。
   - 呼叫者必須確認帳本目錄與 `ledger_id.json` 已存在，才建構 `ResearchLedger`（建構函式在兩者不存在時會建立它們）；不存在即拒絕。
   - 回傳：該假說登記的世代；登記紀錄的 `time_splits` 與 `selection`；樣本外範圍 [time_splits[0].start, time_splits[1].end)；`max_lookback_seconds`；
     本世代 holdout 的狀態：只有 holdout 帳中有本世代的 `opened` 事件、且其 `intervals` 含本假說時，回傳 `intervals[hypothesis_id]`，否則回傳 null。`denied` 事件一律不計。
   - 另新增 `ResearchLedger.trial_record(trial_id)`：同樣只取 `_lock` 並以 `_read` 驗證鏈接、不寫入；回傳該試驗的完整身份（`begin_trial` 的紀錄）、是否已結束與狀態；試驗不存在時拒絕。
     U5 的執行器與 U6 的 `submit` 以此取得試驗身份。三個單元平行開發：U5、U6 以注入的查詢函式取得試驗紀錄（預設呼叫 `trial_record`），測試注入假的查詢函式，與 U4 的實際整合在 P4-D 驗證；
   - 假說不存在時拒絕；已撤回時，只在帶 `trial_id`、且它是該假說已開始的試驗時回傳（供 U6 `submit` 與記錄者重跑時重新物化），否則拒絕。U4 以 `--trial <試驗代號>` 傳入，此時 `--window` 必須等於該試驗的 `data_window`。
   - 用途說明（寫入方法的註解）：`open_holdout` 的回傳只在開啟當下取得一次，物化需要可以重複查得同一區間，所以另設這個唯讀查詢；它不改變 `open_holdout` 的規則，也不構成第二次開啟。
     holdout 區間的每一次物化都以輸出 manifest 的雜湊記入試驗紀錄，使讀取可以追溯。
2. **輸入核對。**
   - `--u1 <U1 輸出目錄>` 與 `--u1-manifest-sha256 <雜湊>`：manifest 的 SHA-256 必須等於傳入值；用到的每一個資料檔，SHA-256 必須等於 manifest 的記錄；
   - manifest 的 `tool_version` 必須是 `r8-public-data-2`（P3b），否則拒絕；
   - `materialize.py` 以常數寫入 P3b 的 U1 manifest SHA-256 `b6519a7b2f5eae4759612690790ddb6680db62aa4e723427f51c21a7d6257006`（2026-10-20 P3b 的結果，記錄者已重算核對；結案紀錄見階段 2 派工指令 §8.8，TODO `P1-R8-S2-P3-FETCH` 已結案），`--u1-manifest-sha256` 必須等於這個常數，否則拒絕。
     常數隨 `code_commit` 釘住（§5 第 4 點），呼叫者改不了；測試以替換模組常數的方式使用構造的 U1 目錄；
   - 唯一的例外是 `--validation`（只供 §8 以構造資料的檢查）：此時 `--u1-manifest-sha256` 不必等於常數，輸出的 `materialization.json` 記 `purpose: "validation"`（否則為 `"research"`）。
     執行器在 `trial` 與 `verification` 模式拒絕 `purpose` 不是 `research` 的物化，U6 的 `submit` 也拒絕；構造資料的 U1 manifest 雜湊，由記錄者在執行檢查之前寫入檢查紀錄並提交；
   - 建合約屬性（第 5 點）之前，核對請求記錄 `requests.jsonl` 的 SHA-256 等於 manifest 的 `request_log_sha256`，且 `universe_request_ids` 所指的每一個原始頁 `raw/<id>.json` 的 SHA-256 等於請求記錄中該筆的 `raw_sha256`；任一不符即拒絕；
   - `--ledger <帳本目錄>`、`--hypothesis <假說代號>`、`--window <起點>,<終點>`（UTC，ISO 8601，半開區間）、`--out <輸出目錄>`；
   - 標的清單不由呼叫者指定：取自預登記紀錄的 `selection.symbols`（P5 規定預登記須在 `selection` 中列出明確的標的清單；橫截面假說列出全部候選標的，時點上的可交易性由框架依首根與下架時間判定）。`data_access` 一併回傳這份清單；預登記沒有 `selection.symbols` 時拒絕。BTCUSDT 另加，只供基準使用、不交給策略；
   - 每次都物化 1 小時 K 線、日線、持倉量、資金費與成交額。BTCUSDT 一律包含在內（基準與行情標示需要）。
3. **可讀區間**（§3.6）：
   - 要求的視窗必須整段落在樣本外範圍之內；否則拒絕，不輸出任何檔案。
   - **本版不物化 holdout 區間**，即使 holdout 已開啟、本假說在候選之中也一律拒絕。理由：holdout 開啟之後 `data_access` 可以重複查得同一區間，而物化發生在 `begin_trial` 之前，研究者可以在登記試驗之前反覆物化並查看 holdout 資料，帳本無從察覺。
     holdout 的物化要等帳本補上「先保留試驗、再釋出資料、每次物化都記入帳本」之後才啟用（TODO `P1-R8-S2-LEDGER-FIXES`），屆時另以補充指令規定；在那之前，holdout 證偽試驗無法執行。holdout 要到第一代主試驗結束、第二代計畫列妥之後才開啟，不影響之前的步驟；
   - 暖機區間 = [視窗起點 − `max_lookback_seconds`, 視窗起點)，只可落在 §3.6 允許的部分；`max_lookback_seconds` 小於 13 日時拒絕；
   - 只寫出暖機區間加視窗之內的資料列。資金費另含結算時刻恰等於視窗終點的那一筆（恰在終點的那一筆計入最後一期，§3.2 中 e 的例外）。
4. **輸出格式**（PA 2026-10-20 在映像中確認的部分標明「已確認」，其餘標明「未驗證」，由 §8 的檢查確認）：
   - 1 小時 K 線：`lean/cryptofuture/bybit/hour/<小寫標的>_trade.zip`，內含 `<小寫標的>_trade_perp.csv`（沿用 P1b 的檔名，P1b 已以此執行），每行 `yyyyMMdd HH:mm,開,高,低,收,量`，時間為 K 線開始時刻（UTC）。
     例：`20220301 01:00,43160.5,43320,43012.5,43225,1532.418`。
   - 不寫 `margin_interest`（LEAN 原生的資金費以 `NULL` 模型關閉，§3.3）。
   - 自訂資料：`custom/<資料集>/<小寫標的>.csv`，資料集為 `kline_day`、`funding`、`open_interest`、`turnover_hour`、`turnover_day`；
     `kline_day` 每行為 `可知時刻的 UTC 毫秒,開始時刻的 UTC 毫秒,開,高,低,收,量`，可知時刻為該日結束（次日 00:00 UTC）；日線不寫成 LEAN 的資料目錄。其餘資料集每行 `可知時刻的 UTC 毫秒,資料時間戳的 UTC 毫秒,值`，可知時刻依 §3.1。例：`1646092800000,1646092800000,0.0001`。框架自行讀取這些檔案（§5 第 2 點），不使用 LEAN 的 `PythonData`。
   - 原始資料列的切片：`source/<U1 檔名去掉 .gz>`，內容是 U1 檔案中落在暖機區間加視窗之內的列，保留 U1 的標頭與原字串，不轉換。供 U6 讀取（§6 第 0 點）。
   - 數值一律以十進位一般小數寫出，不得出現科學記號（選型查核紀錄 §4.5 第 1 點）；以 `decimal.Decimal` 由 U1 的原字串轉換，不經過浮點數。原始切片例外，照原字串保留。
5. **合約屬性。** 映像內的屬性表在 `/Lean/Data/symbol-properties/symbol-properties-database.csv`，只有 631 個 Bybit 永續合約；LUNAUSDT 只有現貨列，以它新增永續合約時失敗（已確認）。
   由 U1 保存的 instruments-info 原始回應（manifest 的 `universe_request_ids` 所指的各頁），為每個用到的標的寫一列到 `symbol_properties_overlay.csv`：
   `bybit,<標的>,cryptofuture,<標的>,USDT,1,<tickSize>,<qtyStep>,<標的>,<minOrderQty>,`（11 個欄位，與表頭一致；PA 已確認追加這樣一列之後 LUNAUSDT 可以載入）。
   另把 `lotSizeFilter.minNotionalValue` 逐標的寫入輸出 manifest 的 `min_notional`（屬性表沒有這一欄）；缺少時記為 0 並列入限制。
   原始回應缺這些欄位或值不合法即拒絕。這是取數當時的值，歷史上的變更無從得知，輸出 manifest 記為限制。
6. **缺漏與下架**（只依可讀的資料列計算，不讀暖機加視窗以外的資料）：
   - 依 U1 manifest 的 `gaps`，把暖機區間加視窗之內的缺漏區間逐檔寫入輸出 manifest；
   - `first_bar`：各標的第一根 1 小時 K 線的時刻（不在可讀範圍內者記 null）；
   - `delistings`：只記 `deliveryTime` 落在暖機區間起點到視窗終點之間（含恰等於視窗終點者，與資金費的端點規則相同）的標的，含 `deliveryTime` 與最後一根是否只涵蓋部分時段。
     `deliveryTime` 恰等於計分終點時，下架結算（§9.8.6）優先，不再另計 `score_end_liquidation`。
   這些資訊只寫在輸出 manifest，不寫進 `lean/` 與 `custom/`（§3.8）。
7. **原子發布。** 輸出是確定性的：檔案內容、列的順序與 JSON 鍵序只由輸入決定，壓縮檔的時間戳與檔頭固定，不寫入產生時刻（§7.1）。`--out` 必須不存在。全部檔案與 §7.1 的 `materialization.json` 先寫到同一檔案系統上的新暫存目錄，完成後以一次 rename 發布為 `--out`；中途失敗時刪除暫存目錄，不留下部分輸出。輸出目錄在倉庫內時拒絕（沿用 U1 的檢查方式）。
8. 命令列：`python -m program_code.research.r8_engine.materialize <參數>`。

**測試**（全部離線，以構造的 U1 目錄與帳本）：
- 第 1 點：`trial_record` 回傳完整身份與結束狀態、不存在時拒絕、查詢前後三本帳的位元組不變；holdout 未開啟、已開啟但不在候選、已開啟且在候選、只有 `denied` 事件四種情形；已撤回的假說只在帶已開始的 `trial_id` 時可查、視窗須等於其 `data_window`；第二代查不到第一段；已撤回與不存在的假說被拒；帳本目錄或 `ledger_id.json` 不存在時拒絕且不建立；查詢前後三本帳的位元組不變；
- 第 2 點：manifest 雜湊、檔案雜湊、工具版本任一不符即拒絕；`--validation` 時接受其他雜湊並記 `purpose: "validation"`，不帶時記 `"research"`；U1 manifest 的雜湊不等於常數時拒絕（自行改動 U1 資料並重寫一份自洽的 manifest 也被拒）；物化的標的等於預登記的 `selection.symbols`（加 BTCUSDT），預登記缺清單時拒絕；
- 第 3 點：
  - holdout 區間（不論是否已開啟、是否在候選之中）一律拒絕物化；
  - 第 15 折的視窗（2025-07-03 至 2025-10-02，跨過訓練段與驗證段之間的空窗）可以物化；整個樣本外範圍 [2020-01-01, 2026-01-01) 可以物化，暖機落在資料起點之前的部分為空並記入限制；
  - 視窗跨入未開啟的 holdout、暖機跨入另一代的 holdout、`max_lookback_seconds` 小於 13 日，都拒絕且不輸出；
  - 只寫出暖機加視窗之內的資料列，資金費含結算時刻等於視窗終點的那一筆；
- 第 4 點：以 `9.464e-05` 等科學記號的輸入，輸出為一般小數且數值相等；時間格式與檔名；持倉量的可知時刻為時間戳加 4 小時；下架時刻之後的資金費不寫；原始切片逐字保留；
- 第 5 點：屬性列取自原始回應；缺欄位拒絕；請求記錄或原始頁的雜湊被改動時拒絕；
- 第 6、7 點：同樣的輸入物化兩次，輸出目錄逐位元組相同；缺漏、首根與下架資訊只依可讀列計算（改動可讀範圍外的資料列不影響輸出），且不出現在 `lean/` 與 `custom/`；manifest 的雜湊與檔案一致；`--out` 已存在時拒絕；中途失敗不留下部分輸出；輸出目錄在倉庫內被拒；
- AST 檢查。

## 5. U5 `R8-S2-ENGINE-LEAN-20261020`：LEAN 研究框架與執行器

**為什麼**：選型查核紀錄 §4.5 的四項發現顯示，LEAN 的預設成交、手續費與前值填補不符合修訂二 N4 的時間語義與 N3 的悲觀成本；資金費的「較不利者」規則也不是 LEAN 原生的做法。框架把這些規則集中在一處，假說的演算法只寫訊號與目標權重。

**可改檔案**（全部新增）：
- 主機端：`program_code/research/r8_engine/lean_algo/__init__.py`（只有說明字串）、`program_code/research/r8_engine/lean_algo/rules.py`、`program_code/research/r8_engine/lean_runner.py`、`program_code/research/tests/test_r8_engine_lean.py`；
- 容器內：`program_code/research/r8_engine/lean_algo/framework.py`、`program_code/research/r8_engine/lean_algo/examples/fixed_schedule.py`。

**要求**：

1. **`rules.py`：全部規則的純函式。** 只用標準函式庫，以 `decimal.Decimal` 計算，輸入輸出皆為 `Decimal` 或字串，實作 §3 與 §9.8 的全部規則：
   - 下一根開盤成交的判定（含下一根缺漏）；
   - 流動性分級、單筆上限、作廢與懲罰滑價（§3.4、§9.8.2）；依成交價的手續費；目標權重換算數量、向零取整、`minOrderQty` 與 `minNotionalValue`；反手拆段；
   - 資金費：較不利者規則、δ、空白的判定與估計、下架時刻與之後的紀錄（§9.8.3、§9.8.4、§9.8.7）；
   - 下架結算的價格（§9.8.6）與計分終點的平倉成本（§3.5）；
   - 折內網格選擇 `select_grid_point`（§9.2 第 4 點：合格點、鄰域平均、同分取預登記順序在前者、不交易）。
   `framework.py` 只把這些函式接到 LEAN 的介面上，不另寫一份規則。U6 的獨立重算另寫一份，不匯入 `rules.py`。
2. **`framework.py` 的基底類別 `R8Algorithm`。**
   - 由掛載的執行設定讀取 §7.0 的鍵；框架專用的資訊（完整標的清單、首根時刻、下架資訊）由執行器另以框架專用的檔案傳入；
   - 每個標的：`AddCryptoFuture(標的, Resolution.HOUR, Market.BYBIT, fillForward=False, leverage=10)`；手續費模型 `ConstantFeeModel(0)`；資金費模型 `MarginInterestRateModel.NULL`；自訂成交模型（下列）；
   - 自訂成交模型：`market_fill` 在下單的時間步回傳不成交的事件，使訂單保持 SUBMITTED；在下一根送達的時間步，以 `rules.py` 計算成交價與手續費，設定 `FillPrice`、`FillQuantity`、`Status` 與 `OrderFee`。
     比較時間前先統一時區：`order.time` 帶 UTC 時區，K 線的時間不帶（PA 已確認）；
   - 依 §3.2 的順序：在 `on_data` 中決策、作廢判定、送出訂單、計入資金費（以 `Cash.AddAmount` 調整 USDT 現金；補計所有 T < 現在而尚未計入者；T 恰為現在者留到下一個時間步，§3.2 第 3 步）、記錄時間步；
   - 自訂資料（日線、持倉量、資金費、成交額）由框架在初始化時讀入記憶體，依可知時刻提供給策略，不使用 `PythonData`（以免每列一次 Python 呼叫）；
   - 日線決策：LEAN 只訂閱 1 小時 K 線。以日線決策的假說，只在 00:00 UTC 的時間步收到前一日完成的日線並決策，訂單以當時那一根 1 小時 K 線的開盤價（即次日開盤）成交；`run_config` 的 `decision_resolution` 為 `hour` 或 `day`；
   - 選中結果為不交易（`no_trade`）的折，依 §9.2 第 4 點：框架在該折計分窗起點的時間步以目標權重 0 平掉延續的部位，該折其餘時間不呼叫 `on_decision`；
   - 暖機、計分窗與第一代的訓練段規則依 §3.5；`run_config` 帶 `folds`，框架在每折擬合窗終點執行該折的擬合（下述）取得新模型，但保留到該折計分窗的起點才啟用；在那之前（前一折計分窗的最後 8 日）仍用前一折的模型；並拒絕計分窗外的訂單；
   - 下架：在 `deliveryTime` 之後（含恰等於）的第一個時間步處理，也就是最後一根 K 線送達的時間步（不在整點下架時，那一根不完整的 K 線依 §3.1 在其所屬整點結束時才送達）；順序依 §3.2 第 1 步：
     先取消該品種所有尚未成交的訂單（`orders` 記為 `cancelled`、`cancel_reason` 為 `delivery`），再依 `rules.py` 平倉，記為下架結算，部位變動時刻記為 `deliveryTime`；之後拒絕對該品種下單；
   - §3.8 的資訊限制與下單函式覆寫；
   - 假說是繼承 `R8Hypothesis` 的獨立類別，不繼承 `QCAlgorithm`、拿不到 LEAN 的演算法物件；LEAN 執行的是框架的固定類別 `R8Algorithm`，由它依 `run_config.algorithm` 載入假說類別（以下「子類別」指假說類別）。
     子類別實作 `score(params, train_window, validation_window, data, cost)`、`fit(fit_window, data, params)` 與 `on_decision(time, data, model, params)`，最後一個回傳各標的的目標權重；框架負責換算、作廢判定與下單。
     擬合與決策不共用實例：每次擬合（每折一次）框架另建一個新的假說實例，只呼叫 `score` 與 `fit`，用完即丟；每折的計分窗起點，框架再建一個新的實例負責該折的決策。下一折提前 8 日擬合時，正在決策的實例因此不受影響。
     每折的擬合由框架執行，選擇不由子類別決定：
     - 網格與成本由框架傳入，子類別不自備：網格是 `run_config.strategy.grid`（預登記的變體參數清單，依序，至多 20 組），成本是 `run_config.cost`；
       框架依 §9.2 第 4 點由擬合窗算出內部訓練段與內部驗證段（最後 182 日為驗證，其前留 8 日），對網格中的每一組參數依序呼叫一次 `score`，收集成 `grid_scores`；
     - 框架以 `rules.select_grid_point`（§9.2 的合格點、鄰域平均與同分規則）由成績與預登記的鄰域推出完整的 `selection`（`grid_scores`、`neighborhood_means`、`qualified`、`selected`、`selected_minus_neighborhood`、`no_trade`）；
     - 不交易時不呼叫 `fit`；否則以選中點的參數呼叫 `fit`，該折的模型為 {`params`: 選中點的參數, `model`: `fit` 的回傳值}；計分時框架把同一組 `params` 與 `model` 交給 `on_decision`；
     - 每折的結果記入 `run.json` 的 `fits`（§7.2）。子類別的程式若不依 `params` 擬合或決策，或 `score` 回報的成績不是依 §9.2 算出的內部驗證成績（U6 只由成績重推選擇，不重算成績本身；重跑只證明確定性），屬假說程式的缺陷，由階段 3 的代碼審查把關，列為殘餘風險；
     交給 `score` 與 `fit` 的 `data` 只含時間戳（可知時刻）早於 `fit_window.end` 的資料，交給 `on_decision` 的只含當時已可知的資料；兩者都是框架建立的唯讀視圖，不是框架持有的完整資料；
   - 模型檔：擬合執行中，框架把最後一折的模型（{`params`, `model`}）以標準化 JSON 寫成模型檔並記錄 SHA-256；評分執行中，框架依 `run_config` 的 `model_artifact` 核對模型檔的 SHA-256，載入後交給子類別，不呼叫 `score` 與 `fit`。
     模型檔是執行的產物，不屬於試驗身份（§7.0）；`score` 與 `fit` 必須是確定性的（給定資料、參數與 `random_seed`），使記錄者可以重跑擬合並得到同一個雜湊。
     假說的演算法本身不讀寫檔案（§3.8）；
   - 執行中寫出原始紀錄（JSON Lines）；`run.json` 由主機端的執行器組裝（第 4 點）。部位只記非零值。
3. **範例演算法** `examples/fixed_schedule.py`：在設定指定的時刻設定指定的目標權重或固定數量（類似 P1b 的固定時點策略），供 §8 的檢查使用；不是假說。它的 `score` 回傳設定中為該組參數指定的成績（使檢查可以構造合格、不合格與不交易的折），`fit` 回傳 {`fit_end`: 擬合窗終點}（使 EV-14 可以看出啟用的是哪一折的模型）；`folds` 為空清單時框架不擬合，`params` 為 `run_config.strategy`、`model` 為 null。
4. **執行器** `lean_runner.py`（主機端）：
   - 映像固定為 `quantconnect/lean@sha256:2657ed3355efb78d78bd0a5d4f126b01367a635e01bccd220b654d7742d182b6`，以 `docker run --rm --network none` 執行；
   - 掛載逐目錄進行，不得覆蓋整個 `/Lean/Data`（否則 `market-hours` 與 `symbol-properties` 會被遮住而無法啟動）：
     U4 的 `lean/cryptofuture/bybit/hour` 以唯讀掛到 `/Lean/Data/cryptofuture/bybit/hour`；U4 的 `custom/`、演算法目錄、執行設定與框架專用檔案以唯讀掛到另外的路徑；另掛一個可寫的輸出目錄；
   - 合約屬性表：以映像內的屬性表為底（記錄其 SHA-256；PA 量得 `53072f5a…e236a`），對 U4 `symbol_properties_overlay.csv` 中的每個標的，**替換**同鍵（market、symbol、type）的列或新增，產生的單一檔案以唯讀掛載覆蓋映像內的屬性表；
   - 啟動器的設定改寫沿用 P1b 已驗證的方式：在容器內 `/Lean/Launcher/bin/Debug/config.json` 中，把 `"algorithm-type-name"` 改為框架的固定類別 `R8Algorithm`、`"algorithm-language"` 改為 `"Python"`、
     `"algorithm-location"` 改為 `framework.py` 在容器內的路徑（假說模組依 `run_config.algorithm.path` 唯讀掛載，由框架載入 `run_config.algorithm.class`），並在 `"environment": "backtesting",` 之後加入 `"close-automatically": true,`；然後在同一目錄執行 `dotnet QuantConnect.Lean.Launcher.dll`。
     設定檔的 `"data-folder"` 是 `"../../../Data/"`（PA 已確認），不改；
   - 執行前：`run_config` 的 `code_commit` 必須是完整的 commit；被執行的每一個演算法檔（框架、`rules.py`、範例或假說的演算法），以及主機端的 `program_code/research/r8_engine/` 與 `program_code/research/r8_ledger/` 下的全部檔案（含執行器本身、`materialize.py`、`series.py`、`ledger.py`），
     必須與該 commit 中的同一路徑逐位元組相同，且工作樹中這些路徑沒有未提交的改動，否則拒絕執行；這些檔案的 SHA-256 全部記入 `algorithm_files`。假說的演算法檔因此必須先提交（位置由階段 3 的派工指令規定，不得位於下述的引擎目錄內）；
   - 引擎必須是已審查合入 main 的版本：`code_commit` 中 `program_code/research/r8_engine/` 與 `program_code/research/r8_ledger/` 下的全部檔案，必須與 `run_config` 的 `engine_commit` 中的同一組檔案逐位元組相同（檔案清單也相同），且 `engine_commit` 是本機 `origin/main` 的祖先（`git merge-base --is-ancestor`）；否則拒絕執行。
     自行改動常數或規則的 commit 因此無法執行；假說程式另由 `algorithm` 與 `code_commit` 綁定。本機的 `origin/main` 可以被改動，記錄者批次核對時以 GitHub 上的 main 再核對每個試驗的 `engine_commit` 一次；`submit` 依同一規則核對。
     `validation` 模式不適用這一條（P4-D0 在 U5 合入 main 之前執行，檢查的就是待合入的引擎）；`engine_commit` 記為 `code_commit`，`run.json` 照常記錄全部檔案的雜湊；
   - `mode` 為 `trial` 時，`run_config` 帶 `trial_id`：帳本中必須已有這個試驗、已 `begin_trial`、尚未結束，且其身份與 `run_config` 逐項一致（含 `manifest_sha256` 與 `algorithm`）；否則拒絕執行。任何假說的執行因此都對應一筆已計入 K 的試驗，探索不同的設定必須各自登記試驗。
     `mode` 為 `verification` 時（只供記錄者重跑已提交的試驗，§6 第 5 點）：`trial_id` 所指的試驗必須已結束，身份與 `run_config` 逐項一致，其餘核對同 `trial`；`run.json` 記 `mode: verification`，U6 的 `submit` 拒收，只用於比對。
     `mode` 只存在於主機端的執行器與 `run.json`，不交給容器：容器內可見的設定 `algorithm_config` = `run_config` 去掉 `mode`，`trial` 與 `verification` 兩種執行寫入容器的設定檔、掛載的容器內路徑、環境變數與 docker 參數（輸出目錄的主機路徑除外）必須相同；
     `run.json` 記錄容器設定檔的 SHA-256 `algorithm_config_sha256`，記錄者的重跑比對包含它。假說的演算法因此無從得知自己是在重跑；其他可能的偵測途徑（例如讀取時鐘）由 §3.8 的靜態檢查阻擋，殘餘風險同 §3.8；
     `mode` 為 `validation` 時（只供 §8 的檢查）：`trial_id` 必須為 null，`algorithm` 只能是 `examples/fixed_schedule.py` 的固定類別，其他演算法一律拒絕；`run.json` 記 `mode: validation`，U6 的 `submit` 拒收。物化經 U4，使用另建的驗證用帳本，不是研究帳本；
     繞過執行器、私下執行未登記的變體，無法以程式完全防止；這是殘餘風險，回報時列明（§3.8 的同類限制）；
   - `run_config.symbols` 必須等於物化 manifest 的 `strategy_symbols`（依序），框架只把這些標的交給策略；
   - `run_config.warmup` 必須等於物化 manifest 的 `warmup`，`score_windows` 必須等於 `folds` 中各折的 `score_window`（依序）；不符即拒絕。暖機與計分窗因此由已納入試驗身份的物化與摺表決定，不能在同一試驗中改變；
   - 核對 U4 的 `materialization.json` 的雜湊與執行設定中記錄的值相同；核對要掛載的 `lean/` 與 `custom/` 目錄中的檔案清單與 manifest 完全相同、每檔雜湊相符，有多出或缺少的檔案即拒絕；對假說的演算法檔執行 §3.8 的靜態檢查；
   - 執行後：由原始紀錄組裝 §7.2 的 `run.json`（以帳本的 `canonical` 寫出），記錄映像摘要、完整的 docker 參數、演算法檔與設定的雜湊、起訖時間、結束碼與 LEAN 日誌的雜湊；
   - 輸出目錄在倉庫內時拒絕。

**測試**（主機端，全部離線）：
- 視圖：改動 `fit_window.end` 之後的資料列不改變 `score` 與 `fit` 收到的內容（以不依賴 LEAN 的視圖建構函式測試）；
- 擬合：框架對 `strategy.grid` 的每一組參數依序呼叫 `score` 並傳入內部訓練與驗證窗及 `cost`；以 `select_grid_point` 選出的參數呼叫 `fit`，並把同一組參數交給 `on_decision`；不交易時不呼叫 `fit`；擬合用的實例與決策用的實例不是同一個（擬合時改動實例狀態，不影響正在決策的實例）（以記錄呼叫與實例的假假說類別測試，不依賴 LEAN）；
- 靜態檢查拒絕 `global`、`nonlocal` 與對模組層級名稱或類別屬性的賦值；
- 模型檔：擬合執行寫出、評分執行載入的往返，以及 SHA-256 不符時拒絕（以不依賴 LEAN 的序列化函式測試）；
- `rules.py`：§3.9 的 G1 至 G8 逐位重現；另以手算案例核對日線決策只在 00:00 UTC 且以次日開盤成交、總曝險超過上限即失敗、下一根缺漏、三個流動性等級、單筆上限、不足 12 個完整日、`min_qty`、`min_notional`、全部平倉例外、`select_grid_point`（成績 [−1, 100, −1, −1] 不選第一點、[100, −1, −1] 不合格而不交易、全部不合格時不交易、同分取順序在前者）、懲罰滑價乘以壓力倍數、資金費空白的估計筆數與時刻、多空正負號；
- `lean_runner.py`：`random_seed` 不是整數時拒絕；`trial` 與 `verification` 模式拒絕 `purpose: "validation"` 的物化；`run_config.symbols`、`warmup` 或 `score_windows` 與物化、摺表不符時拒絕；引擎目錄的內容與 `engine_commit` 不同、或 `engine_commit` 不是 `origin/main` 的祖先時拒絕（以構造的 git 倉庫測試）；`trial` 模式下帳本中沒有對應的已開始、未結束且身份相符（含入口）的試驗時拒絕執行（以注入的假查詢函式測試）；`verification` 模式下試驗尚未結束或身份不符時拒絕；同一試驗的 `trial` 與 `verification` 執行寫入容器的設定檔逐位元組相同、不含 `mode`；`validation` 模式下以範例以外的演算法或帶 `trial_id` 時拒絕；演算法檔與 `code_commit` 不符或有未提交的改動時拒絕執行（以構造的 git 倉庫測試）；組出的 docker 參數（以注入的執行函式攔截，不真的執行 docker）含 `--network none`、固定的映像摘要、逐目錄的唯讀掛載；屬性表合併是替換而非追加；`materialization.json` 雜湊不符、掛載目錄有 manifest 未列的檔案或缺少檔案，都拒絕；靜態檢查拒絕檔案存取、底線屬性與下單呼叫；輸出目錄在倉庫內被拒；`run.json` 的組裝；
- AST 檢查涵蓋 `rules.py`、`lean_runner.py` 與 `lean_algo/__init__.py`。

## 6. U6 `R8-S2-ENGINE-SERIES-20261020`：帳本序列、獨立重算與基準序列

**為什麼**：帳本只接受研究者提交的報酬序列，統計量由帳本計算（階段 2 派工指令 §7.4 的原則）。序列必須由執行紀錄機械地產生，並以獨立於 LEAN 與 `rules.py` 的重算核對，否則引擎的錯誤會直接成為試驗結果。

**可改檔案**（全部新增）：`program_code/research/r8_engine/series.py`、`program_code/research/tests/test_r8_engine_series.py`。

**要求**：

0. **讀取範圍。** 本單元只讀 U4 的輸出：`materialization.json`、其中記錄雜湊的 `source/` 切片與 `symbol_properties_overlay.csv`。每個檔案的 SHA-256 必須等於 manifest 的記錄；不讀 U1 的任何檔案。
1. **帳本序列。** 由獨立重算的權益（第 2 點）產生階段 2 派工指令 §7.4 格式的序列檔：
   - 期初為計分窗在 Sharpe 頻率上的期數網格（階段 2 派工指令 §7.4 的定義），暖機不計；E(期初) 依 §3.2；
   - `filled_periods` 依 §9.14 計算；
   - 執行紀錄為 `completed` 時：獨立重算的比對不通過、`fill_forward_bars` 不為空，或 `unexplained_cash_residual` 不為 0，即拒絕產生序列並說明原因；`submit` 依第 5 點拒絕提交、不寫入帳本，由記錄者回報。執行器應已把出現前值填補的執行記為 `failed`（§3.5），`completed` 的執行出現這些情形屬實作缺陷，不得改以 `failed` 提交。
   - 執行紀錄為 `failed` 時：帳本不接受部分序列（附序列時必須涵蓋完整的期數網格，且產出期數等於網格長度；`ledger.py` 的 `_store_series` 與 `finish_trial`），
     而失敗的樣本外試驗在已產生不少於 2 期時又必須附序列。因此以完整網格提交：失敗之前已完整的期數取獨立重算的報酬，失敗之後的期數填 0，並全部計入 `filled_periods`；
     實際產生的期數、失敗原因與 `recompute_passed: false` 寫入旁註檔與 `result_summary`。依帳本規則，主試驗失敗時 p 值記 1；V 與 PBO 只用已完成的試驗。
     失敗可能取決於資料（例如看到不利的樣本外路徑之後才觸發例外或超過曝險上限），而失敗試驗的序列不進入 V 與 PBO，等於刪去不利的結果。因此：任一 `out_of_sample` 試驗（主試驗或探索性試驗）的 `failure_t`（§7.2；null 視同不早於）不早於第一個計分起點時，記錄者不呼叫 `close_generation`，依修訂二 §5 階段 2 的停止條件回報 Operator；
     帳本補上把失敗試驗的序列保守納入 V 與 PBO 的處理之前（列入 TODO `P1-R8-S2-LEDGER-FIXES` 的待議事項），沒有其他處理方式。失敗時刻早於第一個計分起點者（尚未看到任何樣本外結果）不在此限。
     帳本接受部分序列屬帳本（U2）的行為變更，併入 TODO `P1-R8-S2-LEDGER-FIXES`。
2. **獨立重算。** 自行實作 §3 與 §9.8 的規則，以 `decimal.Decimal` 由原字串計算，不匯入 `rules.py`，也不使用 LEAN 的任何數值；只用 U4 的輸出與執行紀錄中的決策（時刻、標的、目標權重或數量）：
   - 依 §3.2 的順序，重算每筆成交的價格、數量、手續費、作廢與原因、懲罰滑價，每次資金費結算的金額（含空白的判定與估計），下架結算，計分終點的平倉成本，以及每個時間步的現金與權益；
   - 與執行紀錄逐筆、逐步比對，容差依 §9.8.8；另比對期末權益與手續費、資金費的累計值；
   - 輸出比對報告：比對的筆數、最大差異與其位置、是否通過。
3. **基準序列**（§9.7）：
   - `beta_matched_btc_v1`（`exposure_matched`，帳本基準）：每個試驗各自產生；貝塔只用各折擬合窗最後 365 日的日報酬估計（相鄰兩根都存在的日報酬）；部位權重用作廢之後的實際部位，不用決策；
   - `btc_perp_hold_v1`（確定性，只作報告，不登記為帳本基準）：以同一份物化的 BTCUSDT 資料產生，同樣輸入必須產生同樣位元組；
   - `no_trade` 由帳本自行產生，本單元不產生。
   主試驗的物化視窗是整個樣本外範圍（§7.0），各折擬合窗都在其中；holdout 證偽試驗的擬合窗為 [訓練段起點, 驗證段終點)（§9.10），由擬合執行的物化提供。
4. **成本壓力重算**（§9.8.2）：以同一次執行記錄的目標權重（決策不變），在壓力參數下的現金與權益路徑重新換算數量，重做取整、作廢（含流動性分級與單筆上限）、總曝險檢查與成交，計算成本與淨報酬序列；某情境中曝險超過上限時，該情境記為失敗並照實報告。
   決策不變是近似：假說的決策若依賴自身部位或權益，壓力下的決策可能不同；這只影響這類假說，報告註明；彙整各情境的淨結果、成本佔比與損益兩平的滑點倍數，供試驗紀錄的 `result_summary` 使用。
5. **提交帳本。** `submit` 子命令是唯一的提交途徑，它自己產生所有寫入帳本的內容，不接受呼叫者提供的序列、基準、壓力摘要或旁註：
   - 輸入只有：帳本目錄、試驗代號、U1 輸出目錄、執行紀錄（以及 holdout 啟用之後的模型檔）；
   - 狀態不由呼叫者指定：執行紀錄須為 `mode: trial` 且 `run_config.trial_id` 等於試驗代號；帳本狀態取自 `run.json` 的 `status`（`completed` 或 `failed`，`failed` 時 `failure_reason` 須為 §7.2 列出的原因之一）；
     `completed` 的執行重算不通過時拒絕提交、不寫入帳本，屬實作缺陷，由記錄者回報處理，不得改以 `failed` 提交；`submit` 不寫入 `aborted`；
   - 重新物化：以試驗身份的 `hypothesis_id` 與 `data_window`（回看長度取自帳本登記的 `max_lookback_seconds`）與 U1 輸出目錄執行 U4，並帶 `--trial`（假說在試驗開始後撤回時仍可完成，§4 第 1 點；以子程序執行 U4 的命令列，不匯入 `materialize.py`，使 U4 與 U6 可以平行開發；U6 的測試注入假的物化函式，與 U4 的實際整合在 P4-D 驗證），產生的 manifest 必須與試驗身份的 `manifest_sha256` 與 `data_files` 逐位元組相同（U4 是確定性的；U1 manifest 的雜湊必須等於 `materialize.py` 中的 P3b 常數，`--u1` 只是檔案位置，不是信任來源）；
   - 核對：執行紀錄的 `run_config` 與試驗身份逐項一致；`engine_commit` 依 §5 第 4 點的引擎規則核對；`algorithm_files` 中每一檔等於 `code_commit` 中同一路徑的內容，且 `submit` 執行當下 `r8_engine/` 與 `r8_ledger/` 沒有未提交的改動；
   - 產生：由執行紀錄與重新物化的輸出，依序執行第 2 點的重算、第 1 點的序列、第 3 點的 `beta_matched_btc_v1`、第 4 點的四個固定壓力情境，以及旁註檔；
   - 寫入：完成的試驗須重算通過；失敗的試驗依第 1 點以完整網格提交，不要求重算通過。`result_summary` 另寫入 `fits`（取自執行紀錄，經第 2 點核對）。`out_of_sample` 試驗以帳本要求的 `baselines` 參數傳入基準序列；
     `result_summary` 寫入 `stress`（取自自行產生的壓力摘要）與 `provenance`：{`materialization_sha256`, `run_sha256`, `recompute_report_sha256`, `series_sha256`, `baseline_sha256`, `stress_sha256`, `stress_scenarios`, `sidecar_sha256`, `model_artifact_sha256`（holdout 證偽試驗；其他為 null）, `recompute_passed`}；
   - 本版的 `submit` 拒收 `holdout_falsification` 試驗（holdout 尚不能物化，見 §4 第 3 點）；holdout 證偽的提交與兩份物化的綁定，隨帳本單元另以補充指令規定。
   帳本本身不檢查 `provenance`（不改 U2）；記錄者在第一代各批試驗結束、提交帳本鏈頭時：
   - 對每個試驗，以保存的檔案重跑 `submit` 的「重新物化」與「產生」兩步（不寫入帳本），結果與帳本中的雜湊逐位元組相同；
   - 對每個已提交的試驗（主試驗與探索性試驗，完成與失敗都算；兩者都可能進入 PBO 與 V/SR0 的計算或影響 K），另以 `code_commit` 與同一份物化、以執行器的 `verification` 模式（§5 第 4 點）重跑 LEAN 執行，比對 `algorithm_config_sha256`、`status`、`failure_reason`、`failure_t`、`decisions`、`orders`、`fills`、`voided`、`funding`、`fits` 與提交的執行紀錄完全相同，證明決策出自被釘住的程式，而不是事後編輯；
   - 呼叫 `close_generation` 之前，每個已開始的試驗都必須已經提交：帳本對未提交的試驗預設為 `aborted`，會把它排除在 PBO 與 V/SR0 之外。執行是確定性的，記錄者對已開始而未提交的試驗以其身份自行執行並經 `submit` 提交，並在報告中列出；
   - 任一不符即停止，不呼叫 `close_generation`，依修訂二 §5 階段 2 的停止條件回報 Operator：帳本是只增不改的，已提交的序列無法剔除，若照常結算，不符的試驗仍會進入 PBO 與 V/SR0，影響其他假說的判定。
     帳本補上「保留 K、但把試驗排除在這兩個計算之外」的作廢機制之前，沒有其他處理方式（列入 TODO `P1-R8-S2-LEDGER-FIXES` 的待議事項）。框架與假說的演算法因此必須是確定性的（給定設定與 `random_seed`）；執行紀錄、物化 manifest 與重算報告都以內容雜湊為檔名保存。
6. 命令列：`python -m program_code.research.r8_engine.series <子命令>`，子命令與參數：
   - `recompute --materialization <檔> --run <run.json> --out <報告>`；
   - `series --materialization <檔> --run <run.json> --recompute <報告> --out <序列檔>`；
   - `baseline --materialization <檔> --run <run.json> --out <目錄>`（摺表取自執行紀錄 `run_config` 的 `folds`，不另收檔案）；
   - `stress --materialization <檔> --run <run.json> --out <摘要>`（情境不另收檔案：固定為滑點 ×1、×2、×3 配基準費率，以及滑點 ×2 配 `stress_fee_rate`；數值取自執行紀錄 `run_config` 的 `cost`）；
   - `submit --ledger <帳本目錄> --trial <試驗代號> --u1 <U1 輸出目錄> --run <run.json>`；前四個子命令供檢查與報告使用，提交只經 `submit`。

**測試**（全部離線，以構造的物化輸出與執行紀錄）：
- 第 0 點：任一檔案雜湊不符時拒絕；
- 第 1 點：期數網格（含未對齊的視窗端點與星期四期初）、暖機排除、`filled_periods`（§9.14 的五種情形，含缺漏恰在星期四 00:00 UTC 結束時，跨缺漏的價格變動所在的新一期計為填補期）、各種拒絕；
- 第 2 點：§3.9 的 G1 至 G8 逐位重現；下架結算與計分終點平倉的訂單紀錄（`kind`、`order_id`、`decision_t`）依 §7.2 的規則重建，與執行紀錄相同；`trial` 模式的執行紀錄中出現 `quantity` 目標時拒絕；`fits` 中每折 `selection` 除 `grid_scores` 外的全部欄位，以本單元自行實作的 §9.2 規則由 `grid_scores` 重新推出，`params` 等於選中點的預登記參數，任一不符即判重算不通過（以成績 [−1, 100, −1, −1] 等案例測試）；改動執行紀錄中的一筆成交價、數量、手續費、作廢原因、一筆資金費或一個權益值，比對都能抓到；
- 第 3 點：`btc_perp_hold_v1` 的輸出確定且雜湊穩定；`beta_matched_btc_v1` 的貝塔不使用測試窗的資料（以只在測試窗變動的資料驗證）；少於 90 個日觀測時取中位數；
- 第 4 點：壓力重算的數值與損益兩平倍數；
- 第 5 點：狀態取自執行紀錄，命令列沒有狀態參數；`completed` 的執行重算不通過時不寫入帳本；`validation` 或 `verification` 模式、或 `trial_id` 不符的執行紀錄被拒；改動物化輸出中的任一資料列並重寫 manifest 時，重新物化的結果不同而拒絕；`submit` 自行產生的序列、基準與壓力摘要與單獨執行各子命令的結果逐位元組相同；演算法檔或主機端程式與 `code_commit` 中的內容不符時拒絕（以構造的 git 倉庫測試）；`failed` 的執行紀錄提交、帳本接受（完整網格、失敗後填 0 並計入 `filled_periods`）；執行紀錄的 `run_config` 與試驗身份不一致時拒絕；重算未通過時拒絕以 `completed` 提交且不寫入帳本；`holdout_falsification` 試驗被拒；命令列不接受序列、基準、壓力摘要或旁註的檔案參數；通過時寫入的 `provenance` 與 `stress` 正確，`out_of_sample` 試驗附上基準序列，且帳本接受提交（以構造的帳本，含已登記的 `beta_matched_btc_v1` 基準測試）；
- 總曝險：`completed` 的執行紀錄中，某次決策以決策價計算的總曝險超過上限（與執行器應已中止的結果矛盾）時拒絕；`failed` 且原因為 `gross_exposure_cap` 的執行紀錄，依觸發的情形核對：決策後的目標部位以決策價計算超過上限，或在 `failure_t` 成交入帳之後，以實際部位、最近一次決策的決策價與決策時的權益重建的總曝險超過上限（成交不同步，§3.7）；核對成立、`failure_t` 相符，才依第 1 點產生完整網格序列；成交價造成的實際曝險超出只報告，不拒絕（§3.7）；
- AST 檢查。

## 7. 介面契約

三個檔案都是標準化 JSON（帳本的 `canonical`），附 `schema_version`。欄位以本節為準，單元之間不得各自增減；需要新增欄位時停止並回報。

### 7.0 共同約定

- 時間：一律為 UTC 毫秒整數。
- 價格、數量、金額、費率、基點：一律為十進位字串（由 `decimal.Decimal` 轉成，不用科學記號）；部位數量帶正負號，多頭為正。
- 執行設定 `run_config` 的鍵：
  - `trial_id`、`materialization_sha256`、`code_commit`（與試驗身份的 `code_commit` 相同）、`engine_commit`（§5 第 4 點）、`symbols`、`initial_cash`（"100000"）、`leverage`（"10"）、`gross_exposure_cap`（不大於 "1"）、`decision_resolution`（`hour` 或 `day`）、`sharpe_frequency_seconds`；
  - `warmup`、`score_windows`（各計分窗的 {`start`, `end`}）、`folds`（帳本產生的摺表；擬合執行與 holdout 評分執行另以 `fit_window` 表示）；
  - `cost`：`taker_fee_rate`、`stress_fee_rate`、`slippage_tiers_bps`、`untradeable_below_turnover`、`order_cap_fraction`、`forced_reduce_penalty_bps`、`slippage_multiplier`、`funding_delta`、`funding_blank_min_rate`、`liquidity_window_days`；
    其中 `slippage_tiers_bps` 為依門檻遞減排列的清單 `[{"min_turnover": "100000000", "bps": "5"}, {"min_turnover": "10000000", "bps": "10"}, {"min_turnover": "1000000", "bps": "20"}]`；
  - `folds`：帳本 `walk_forward_folds` 的輸出原樣傳入，每項為 `{"fit_window": {"start", "end"}, "score_window": {"start", "end"}}`（時刻為帳本的 ISO 8601 字串）；
  - `model_artifact`：擬合執行為 null；評分執行為 `{"path", "sha256"}`；
  - `random_seed`：整數，與試驗身份的 `random_seed` 相同。帳本允許 null，但執行器一律要求整數（所有試驗與三種模式；null 會使 `random.Random(None)` 取系統亂數，重跑無法重現），null 即拒絕執行；主試驗另見 9.13；擬合執行與評分執行都傳入；框架建立每個假說實例時以 `R8Hypothesis(random_seed)` 傳入，子類別以唯讀屬性 `self.random_seed` 取得，供 `score`、`fit` 與 `on_decision` 使用（亂數只能來自 `random.Random(self.random_seed)`，§3.8 的靜態檢查拒絕 `random` 模組層級的函式）；
  - `strategy`：假說的參數（標準化後），含 `grid`（預登記的網格，依序）、`neighborhood`（預登記的鄰域定義）與其他固定參數；
  - `algorithm`：{`path`（倉庫內的相對路徑）, `class`（假說類別名稱）}，框架只依此載入假說類別；
  - `mode`：`trial`、`verification` 或 `validation`（§5 第 4 點）。
- 與帳本的對應：試驗身份的 `configuration` 只能有 `strategy_parameters` 與 `cost_model_parameters` 兩個鍵（`ledger.py`）。
  - `cost_model_parameters` = `run_config` 的 `cost`；
  - `strategy_parameters` = {`run`: {`initial_cash`, `leverage`, `gross_exposure_cap`, `decision_resolution`, `sharpe_frequency_seconds`, `algorithm`, `engine_commit`}, `strategy`: `run_config` 的 `strategy`}；入口（檔案與類別）因此凍結在試驗身份中，同一 commit 中的其他演算法不能以同一試驗執行；
  - 視窗與摺表對應試驗身份的 `data_window`、`fit_window`、`score_window` 與 `folds`；種子對應 `random_seed`；
  - 物化在 `begin_trial` 之前完成，並納入試驗身份：`manifest_sha256` = 該試驗所用物化 manifest 的 SHA-256（holdout 證偽試驗有擬合與評分兩份物化時，取 `canonical`({"fit": …, "score": …}) 的 SHA-256），`data_files` = 物化 manifest 中各檔的 SHA-256（兩份時鍵前加 `fit/`、`score/`）。
  - `trial_id` 是帳本的試驗代號，供執行器在執行前核對（§5 第 4 點）；試驗的執行 `mode` 恆為 `trial`；除這兩個鍵外，不屬於試驗身份的只有 `model_artifact`（擬合執行在 `begin_trial` 之後才產生）。標的清單由預登記決定（§4 第 2 點）；其餘會改變訂單或報酬的設定一律在試驗身份中。
  - `submit` 核對執行紀錄中的 `run_config` 與試驗身份逐項一致、執行所用的物化等於身份中的 `manifest_sha256` 與 `data_files`，不一致即拒絕。
  - 執行環境的身份欄位一律取固定值，寫成常數 `RUNTIME_METADATA`（隨 `engine_commit` 釘住；U5 寫在主機端可匯入的 `rules.py`，U6 在 `series.py` 自行寫一份，不匯入 `rules.py`；兩份都必須等於本點的值，各自以測試核對）：`cost_model` = {`id`: `r8_cost_rules`, `version`: `r8-p4-v1`}，`fill_model` = {`id`: `r8_next_open_fill`, `version`: `r8-p4-v1`}，
    `engine` = {`id`: `lean`, `version`: 映像摘要 `sha256:2657ed33…82b6` 的完整值}，`dependencies` = {`lean_image_digest`: 同上}，`time_semantics` = {`known_at`: `bar_end`, `fill_at`: `next_bar_open`, `simulated_latency_ms`: 0}。
    執行器在執行前、`submit` 在提交前核對試驗身份的這五個欄位與常數完全相同，`engine.version` 也與 `run.json` 的 `image_digest` 相同；不符即拒絕。規則改版時另以補充指令更新版本字串。
- 物化：每次執行使用一份物化。主試驗與探索性樣本外試驗的物化視窗是整個樣本外範圍；holdout 證偽試驗分兩次執行：擬合執行物化 [訓練段起點, 驗證段終點)，輸出模型檔；評分執行物化該 holdout 區間（加暖機）。這一段描述的是日後的設計；本版不物化 holdout 區間（§4 第 3 點），holdout 的部分待帳本單元完成後另以補充指令啟用。
- 試驗身份與執行產物分開：帳本在 `begin_trial` 時凍結試驗身份，`finish_trial` 不能修改。因此：
  - 順序為：物化 → `begin_trial`（身份含物化的雜湊）→ 執行（含擬合執行）→ `submit`；`begin_trial` 必須在該試驗的任何執行之前呼叫；
  - 試驗身份含全部會改變訂單或報酬的設定與所用物化的雜湊（上一點的對應），不含 `model_artifact`；
  - 擬合執行輸出的模型檔雜湊與各次執行的雜湊，由 U6 的 `submit` 寫入 `result_summary.provenance`（§6 第 5 點）；
  - 記錄者批次核對時重跑擬合，模型檔雜湊不符即判該試驗無效。

### 7.1 物化 manifest `materialization.json`（U4 產生；U5、U6 讀取）

`schema_version`（`r8_materialization_v1`）、`u1_manifest_sha256`、`u1_tool_version`、`ledger_id`、`hypothesis_id`、`generation`、
`purpose`（`research` 或 `validation`，§4 第 2 點）、`window`（{`start`, `end`}）、`warmup`（{`start`, `end`}）、`readable`（§4 第 1 點的查詢結果）、`symbols`（物化的全部標的）、`strategy_symbols`（預登記的 `selection.symbols`，交給策略的標的；只為基準加入的 BTCUSDT 不在其中）、
`files`（相對路徑 → {`sha256`, `rows`, `first`, `last`, `source_file`, `source_sha256`}，含 `lean/`、`custom/` 與 `source/` 下的全部檔案）、
`gaps`（標的 → 資料集 → 缺漏區間清單）、`first_bar`（標的 → 時刻或 null）、`min_notional`（標的 → 十進位字串）、`funding_interval_ms`（標的 → instruments-info 的現行間隔，供邊緣空白的估計）、`delistings`（標的 → {`deliveryTime`, `partial_last_bar`}）、
`symbol_properties_overlay_sha256`、`limitations`（字串清單）。不記產生時刻：同樣的輸入必須產生逐位元組相同的輸出（含 `materialization.json` 與壓縮檔），U6 的 `submit` 依此重新物化核對（§6 第 5 點）。

### 7.2 執行紀錄 `run.json`（U5 的執行器組裝；U6 讀取）

`schema_version`（`r8_lean_run_v1`）、`materialization_sha256`、`run_config_sha256`、`run_config`、
`image_digest`、`docker_argv`、`algorithm_config_sha256`、`algorithm_files`（路徑 → SHA-256）、`base_symbol_properties_sha256`、`started_at`、`ended_at`、`exit_code`、`lean_log_sha256`、
`mode`（`trial`、`verification` 或 `validation`）、`status`（`completed` 或 `failed`）、`failure_reason`（`completed` 時為 null；否則為 `fill_forward_bar`、`gross_exposure_cap`、`invalid_decision`、`algorithm_exception`、`lean_error` 之一）、
`failure_t`（模擬時間的失敗時刻：失敗發生時正在處理的時間步 s，UTC 毫秒；`completed` 時為 null；LEAN 異常結束而無法確定時為 null，視同不早於第一個計分起點）、
以及下列各段（鍵名以此為準；時刻為 UTC 毫秒整數，其餘數值依 §7.0 為十進位字串）：

| 段 | 每筆的鍵 | 例 |
|---|---|---|
| `steps` | `t`、`equity`、`cash`、`positions`（標的 → 數量，只列非零） | `{"t": 1646096400000, "equity": "100012.5", "cash": "99987.2", "positions": {"BTCUSDT": "0.5"}}` |
| `decisions` | `t`、`targets`（必須含當時交給策略的每一個標的，不得含其他標的；缺少或多出即中止執行，`failure_reason` 為 `invalid_decision`；`on_decision` 回傳 null 表示這一步不決策、不下單，不寫入本段；標的 → `{"weight": …}`；`{"quantity": …}` 只限 `validation` 模式的範例演算法，`trial` 與 `verification` 模式中出現即中止執行，U6 也拒絕） | `{"t": 1646096400000, "targets": {"BTCUSDT": {"weight": "0.5"}}}` |
| `orders` | `order_id`（框架依序指派的整數）、`kind`（`strategy`、`no_trade_flatten`、`delisting_settlement`、`score_end_liquidation`）、`decision_t`、`symbol`、`quantity`（帶正負號）、`status`（`filled`、`cancelled`、`voided`）、`cancel_t` 與 `cancel_reason`（`replaced`、`score_end`、`delivery` 或 `no_trade`，被取消時；`no_trade` 見 13.2 第 3 點）、`replaced_by`（被新決策取代時的新 `order_id`） | `{"order_id": 7, "decision_t": 1646096400000, "symbol": "XUSDT", "quantity": "120", "status": "cancelled", "cancel_t": 1646100000000, "replaced_by": 9}` |
| `fills` | `order_id`（下架結算與計分終點平倉也有，見表後說明）、`decision_t`、`change_t`、`symbol`、`quantity`（帶正負號）、`price`、`slippage_bps`、`fee`、`kind`（`normal`、`forced_reduce_penalty`、`delisting_settlement`、`score_end_liquidation`） | `{"decision_t": 1646096400000, "change_t": 1646096400000, "symbol": "BTCUSDT", "quantity": "0.5", "price": "43246.6125", "slippage_bps": "5", "fee": "11.8928184375", "kind": "normal"}` |
| `voided` | `order_id`、`decision_t`、`symbol`、`quantity`、`reason`（`untradeable`、`insufficient_history`、`order_cap`、`min_qty`、`min_notional`、`outside_score_window`、`after_delivery`） | `{"decision_t": 1646096400000, "symbol": "XUSDT", "quantity": "120", "reason": "untradeable"}` |
| `funding` | `t`、`symbol`、`q_before`、`q_after`、`price`、`rate`、`amount`、`estimated`（布林） | `{"t": 1646121600000, "symbol": "BTCUSDT", "q_before": "0.5", "q_after": "0.5", "price": "43510", "rate": "0.0001", "amount": "-2.21901", "estimated": false}` |
| `endpoint_funding` | 同 `funding`；只列結算時刻恰為執行終點、未計入 LEAN 現金的那幾筆（§3.2） | `{"t": 1767225600000, "symbol": "BTCUSDT", "q_before": "0.5", "q_after": "0.5", "price": "93000", "rate": "0.0001", "amount": "-4.743", "estimated": false}` |
| `unexplained_cash_residual` | `per_step`（`[{"t", "residual"}]`，只列非零）、`total` | `{"per_step": [], "total": "0"}` |
| `fits` | `fold`（摺表序號，從 0 起）、`fit_window`、`selection`（§5 第 2 點，框架推出）、`params`（選中點的參數；不交易時為 null）、`model_sha256`（該折模型 {`params`, `model`} 的標準化 JSON 的 SHA-256；不交易時為 null） | `{"fold": 0, "fit_window": {"start": "2020-01-01T00:00:00Z", "end": "2021-12-30T00:00:00Z"}, "selection": {…}, "model_sha256": "…"}` |

下架結算與計分終點平倉由框架產生，不來自策略的決策；框架為每一筆建立一筆訂單：`kind` 為 `delisting_settlement` 或 `score_end_liquidation`，`decision_t` 等於部位變動時刻（`deliveryTime` 或 e），`status` 為 `filled`；
`order_id` 接續框架的序號，同一時刻有多筆時依標的代號的字典序指派。成交紀錄以這個 `order_id` 對應。U6 依同一規則重建，兩者必須相同。
全部訂單（含策略的訂單）的 `order_id` 依產生順序指派：同一時間步內，先是 §3.2 第 1 步的下架結算，再是第 2 步的訂單（策略的訂單或 `no_trade_flatten`）；同一步、同一類之內依標的代號的字典序。反手的複合訂單算一筆。

`unexplained_cash_residual` = LEAN 現金 −（初始資金 + 已實現損益 − 手續費 + 框架的現金調整），每步都必須為 0。
另有 `fill_forward_bars`：框架收到的每一根 `IsFillForward` 為真的 K 線（時刻、標的），應為空清單；不為空時框架照規則中止（§3.5），U6 據此拒絕產生序列。

### 7.3 帳本序列

即階段 2 派工指令 §7.4 的序列檔格式：`{"period_seconds": f, "filled_periods": n, "returns": [[期初 UTC 秒數, 淨報酬], …]}`（帳本以秒計，這是唯一不用毫秒的地方）。
U6 另寫一份旁註檔，記錄所用的執行紀錄、物化 manifest 與獨立重算報告的雜湊，供試驗紀錄引用。

## 8. 檢查（記錄者）

### 8.1 P4-D0 煙霧檢查

U5 的代碼審查通過後、合入之前，由記錄者以構造的資料在本機 LEAN（固定映像、`--network none`）執行 EV-1、EV-6、EV-7，並確認 `unexplained_cash_residual` 為 0。
不通過時，問題回到 U5 的同一交付處理；該交付已無修補額度時，小修由記錄者在發布時處理，需要改動規則或介面時另立修補交付，須 Operator 確認新的交付身分。

### 8.2 P4-D 事件級檢查、成本壓力檢查與執行時間量測

U4 至 U6 經獨立驗證並合入 main、P3b 完成之後執行。除 EV-10 至 EV-12 外都用構造的資料；構造的開盤價一律與前一根收盤價不同，使開盤成交與收盤成交可以區分。
EV-10 至 EV-12 只用訓練段的真實資料，以範例演算法的固定時點策略執行，不是假說試驗，不計入試驗帳（與 P1b 相同）。全部檢查以執行器的 `validation` 模式執行（§5 第 4 點），物化使用另建的驗證用帳本；構造資料的物化以 U4 的 `--validation` 產生（§4 第 2 點），EV-10 至 EV-12 的真實資料以 P3b 的常數物化。

| 編號 | 檢查 | 通過的條件 |
|---|---|---|
| EV-1 | 下一根開盤成交（小時線決策與日線決策各一） | 成交價等於下一根開盤價乘以（1 ± 滑價）；部位變動時刻在 `run.json` 與重算中都是 t + Δ；下一根缺漏時以其後第一根的開盤成交；日線決策的策略收到的是前一日完成的日線（以構造的日線訊號驗證），以次日開盤成交 |
| EV-2 | 沒有前視 | 構造在某根之內跳變的價格，以該根收盤決策的部位不含跳變的捕獲；持倉量在時間戳加 4 小時之前不可見；成交那一根或當日未完成時段的成交額突增，不改變分級與單筆上限 |
| EV-3 | 暖機與可讀範圍 | 暖機期間沒有下單、不計分；暖機需要不可讀區間的資料時 U4 拒絕；首根 1 小時 K 線收盤之前不能交易，上市時間不起作用 |
| EV-4 | 資金費 | 8、4、1 小時與歷史上改變的間隔（含由 8 小時縮短為 4 小時、交界缺一筆的案例）；§3.9 的 G3 至 G6；空白的估計；P_T 缺漏時取前一根收盤並計為填補期；下架之後不計；恰在 s 的結算在下一個時間步計入；下一根缺漏、訂單較晚成交時，T 後的部位不含該訂單 |
| EV-5 | 狀態轉移 | 開倉、加倉、減倉、反手、平倉、下架結算（含不在整點下架、下架前一根缺漏而有未成交訂單的案例）與計分終點的平倉，每一步的部位與現金和 U6 的重算一致 |
| EV-6 | 手續費、滑價與作廢 | 手續費依成交價、雙邊計入；三個流動性等級；不足 12 個完整日與單筆上限的作廢；`min_qty` 與 `min_notional`；懲罰滑價 |
| EV-7 | 前值填補與結束時刻 | 沒有前值填補的 K 線；回測在最後一根的結束時刻結束；下架品種最後一根不完整的 K 線沒有交給策略 |
| EV-8 | 可讀範圍 | holdout 區間一律拒絕物化（本版）；`data_access` 只給候選假說本世代的區間、第二代查不到第一段；跨空窗的第 15 折可以物化 |
| EV-9 | 數值格式 | 構造 1e-05 量級的資金費與小價格品種，結算金額正確 |
| EV-10 | 獨立重算 | BTCUSDT 與一個下架品種，成交、資金費與權益和 U6 的重算逐筆、逐步相符（容差見 §9.8.8）；`unexplained_cash_residual` 為 0 |
| EV-11 | 成本壓力 | 以固定目標權重的時點策略（不用固定數量，使數量隨壓力下的權益改變），用「滑點 × 2、手續費 0.075%」執行 LEAN 一次，結果與 U6 的壓力重算相符 |
| EV-12 | 執行時間 | 單一標的、100 個標的、全部標的各以小時線執行訓練段一次；另量 20 組網格 × 16 折的擬合執行；記錄耗時與記憶體，只量測 |
| EV-14 | 模型的啟用時點與折的交界 | 後一折的擬合窗終點落在前一折的計分窗內；新模型只在其計分窗起點才啟用，前一折計分窗的最後 8 日仍用舊模型；相鄰兩折的交界不平倉，新一折的第一次決策以延續的部位計算差額 |
| EV-13 | 缺漏跨期初 | 持有部位的標的在星期四期初前後有 K 線缺漏：沒有前值填補、缺漏標的在缺漏內的損益貢獻為 0 而同期另一個持有標的的損益與資金費照常計入、價格跳動計入缺漏後第一期；`filled_periods` 依 §9.14 的五種情形（含下一根缺漏使訂單延後成交、缺漏恰在星期四 00:00 UTC 結束）逐一驗證，與 U6 相同 |

- EV-1 至 EV-11、EV-13 與 EV-14 全部通過，P4-D 才算通過。任一項不通過，依修訂二 §5 階段 2 的停止條件停止並回報；修正的處理同 §8.1。
- 檢查的資料、演算法設定、執行紀錄與結果寫入記錄者的檢查紀錄，逐檔記 SHA-256；檢查紀錄以文件提交到倉庫。
- EV-12 的結果用於 P5：假說族的標的數與試驗數須使第一代能在投入上限內執行完畢。

## 9. 預登記的方法論參數

本節規定階段 2 派工指令 §7.5 所列的 14 項，以及成本模型的方法論參數。由 QC 起草、記錄者整合，QC 已複核記錄者的改動（2026-10-20）。
數值計算由 QC 以腳本完成（報酬獨立同分布、單尾檢定、80% 統計力、年化），腳本留在記錄者本機的暫存區、未提交，屬未經獨立複驗的估算；R4 已複算其中的日期、折數與可偵測 Sharpe。

### 9.0 共同記號與報酬序列

1. 報酬序列的每一期是成本後的淨報酬：r_p =（E(p + f) − E(p)）÷ E(p)。E 為帳戶權益（現金加未實現損益），依 §3.2 取樣；手續費、滑點與資金費全部計入 E。
2. 部位以「名目金額 ÷ 決策當時的權益」表示。名目初始資金 100,000 USDT，用於 §9.8.2 的單筆上限；Sharpe 與權益規模無關。
3. 第一代的成交全部假設為吃單。2026-07-06 maker-first 已判 NO-GO；掛單成交不建模。
4. 可知時點：K 線在結束時刻；資金費在結算時刻（不得使用預測費率）；持倉量在時間戳加 4 小時；
   instruments-info 的 `deliveryTime` 與狀態是今日取得的資訊，對策略一律不可見。
5. 標的進入可交易集合的時點，是它第一根實際存在的 1 小時 K 線收盤，不是 instruments-info 的上市時間（例如 LINKUSDT 的上市時間比首根 K 線早 7,065 小時）。退出時點是 `deliveryTime`。

### 9.1 `oos_protocol` 的數值（第 1 項）

全帳本共用下列一份協定（共用的理由見 9.5）：

```
{"scheme": "expanding", "initial_train_seconds": 62899200, "test_seconds": 7862400,
 "step_seconds": 7862400, "purge_seconds": 691200, "embargo_seconds": 691200}
```

- 初始訓練 728 日（2020-01-01 至 2021-12-29），每折測試 91 日（13 週），步長 91 日，清除與空窗各 8 日。
- 帳本依此產生 16 折：第一折測試窗為 2022-01-06 至 2022-04-07，最後一折為 2025-10-02 至 2026-01-01。
  各折測試窗首尾相接；樣本外總長 1,456 日，即 3.99 年、208 週，恰好用到驗證段終點。
- 2022-01-06 與 2026-01-01 都是星期四，落在帳本以 UTC 紀元計的週網格上（9.3），各折邊界不損失不足一期的頭尾。

可偵測的最小年化 Sharpe：

| 情形 | 可偵測的最小年化 Sharpe |
|---|---|
| 單次檢定，α = 0.05 | 1.25 |
| 10 個假說，BY，FDR 0.10（最嚴一級） | 1.78 |
| 同上，加上 DSR 門檻，K = 10 | 2.57 |
| 同上，K = 100 | 3.04 |
| 同上，K = 1,000 | 3.41 |

- DSR 門檻以 V 的下限 1 ÷（T_eff − 1）估算，年化 SR0 ≈ E[max Z(K)] ÷ √Y：K = 10 時 0.79，K = 100 時 1.27，K = 1,000 時 1.63。
- 模擬（每週報酬、常態，10 個假說，BY 0.10）：真實年化 Sharpe 1.5 的策略在樣本外判定成立的機率，K = 10 時約 8%，K = 100 時約 1%；真實 2.5 的策略分別約 70% 與 33%。
- 結論：本設計實際只看得到年化 Sharpe 約 2.5 以上的策略，試驗數越多門檻越高。比 2026-10-16 註記所估的樣本外 2.9 年略好，因為訓練起點已提前到 2020-01-01。

考慮過的選項：初始訓練 365 日（19 折、4.73 年；2020 年標的很少且以多頭為主，第一個擬合窗太薄）；1,092 日（12 折、2.99 年，統計力較差）；
滾動視窗（每折可用的訓練資料少，第一代的訊號雜訊比低，擴張式較穩）；測試窗 84 日（損失 28 日）；56 日（每折交易筆數更少）。

附帶後果：上市較晚的標的在早期各折沒有部位，這些期數的報酬記 0，不屬於 `filled_periods`；測得的 Sharpe 約按「有部位期數佔比」的平方根縮小，不另作調整。

### 9.2 清除、空窗與折內的超參數選擇（第 2 項）

1. 清除與空窗各 8 日。第一代每個假說的標籤期與最長持有期都不得超過 7 日；這樣假說的空窗恰為帳本預設的 7 日，第一段 holdout 從 2026-01-08（星期四）開始，與週網格對齊。
2. 訓練樣本的標籤終點不得晚於擬合窗終點：擬合窗最後一個標籤期內產生的樣本，不用於訓練。8 日的間隔另吸收序列相關。
3. 前進式切分不需要測試窗之後的空窗：下一折的擬合窗只用更早的資料；帳本在測試窗之前留 g = max(purge, embargo)，已足夠。
4. 超參數只在各折的擬合窗內選擇：
   - 擬合窗的最後 182 日（26 週）作為內部驗證；其前留 8 日的內部空窗，再往前是內部訓練；
   - 候選網格寫入變體參數，至多 20 組；每個數值軸在預登記時列出依大小排列的取值，類別軸列出取值。
   - 每個網格點的內部驗證成績 = 成本後淨 Sharpe（基準成本，9.8，以 `rules.py` 的成本函式計算）：內部驗證段週頻淨報酬的平均 ÷ 樣本標準差（ddof = 1），不年化；期數少於 2 或標準差為 0 時記 0（因此不合格）。
     成績以十進位字串回傳，不得為非有限值；框架拒收格式不符或非有限的成績，該次執行以 `invalid_decision` 失敗。
   - 鄰域：一個網格點與所有「各數值軸的取值序號相差不超過 1、類別軸取值相同」的網格點（含自身）；位於邊緣的點只含實際存在的鄰點。鄰域定義在預登記時寫明，不得事後更改。
   - 合格點：自身成績大於 0，且其鄰域中成績大於 0 的點多於鄰域點數的一半（嚴格過半；鄰域只有自身時即自身為正）；孤立的高點因鄰點虧損而不合格，緊鄰高點但自身虧損的點也不合格。
     位於邊緣的點同樣適用：成績 [100, −1, −1] 時，第一點的鄰域只有兩點、只有一點為正，不過半，不合格（記錄者依 PR #226 的自動審查把「不少於一半」改為嚴格過半，比 QC 的原規則更保守，原則不變；QC 2026-10-20 對 `f597cdeea` 之後方法論改動的累積複核（PASS_WITH_NOTES）接受。代價：數值軸只有兩個取值時要求鄰域全部為正，小網格較易判為不交易，損失的是統計力，不是有效性，預登記時須知悉）。
   - 選擇：在合格點中取鄰域平均成績最高者；同分時取預登記時列在前面的那一組。網格只有一組時，鄰域就是它自己。
   - 不交易：沒有合格點，或選中點的鄰域平均成績不大於 0 時，該折不交易：不建立新部位；延續自前一折的部位，由框架在該折計分窗起點的時間步以目標權重 0 平倉（`orders` 的 `kind` 為 `no_trade_flatten`；照一般訂單在下一根開盤成交，照常計滑價、手續費與作廢規則，§3.4），該折其餘時間不呼叫 `on_decision`、不下單；
     該折的期數照實計入平倉前的損益與平倉成本，平倉之後沒有部位的期數報酬為 0；這一條適用於所有假說（包括網格只有一組者），依 9.11 第 1 點照實計入，並計入 9.11 第 2 點的折數下限。
     「合格點」一條由記錄者依 PR #226 的自動審查補充（例：成績 [−1, 100, −1, −1] 時，只看鄰域平均會選中自身虧損的第一點），比 QC 的鄰域平均規則更保守，原則不變。
   - 選定之後，以整個擬合窗重新擬合，再用於該折的測試窗。
   - 記錄：每折把全部網格點的成績、各點的鄰域平均、選中的點、選中點的成績減其鄰域平均，以及是否不交易，寫入 `result_summary`（熱圖的資料）。
   - holdout 證偽的重新擬合（9.10）依同一規則。
   - 理由：以鄰域平均選擇，孤立的高點（cliff）不會因單點最高而被選中，平穩的區域（plateau）較易被選中（`walk-forward-validation-protocol` §6）；選擇規則在程序之內、只用擬合窗的資料，仍算一個試驗（2026-10-20 裁決）。
     邊緣點的鄰點較少、平均的雜訊較大，略偏向邊緣；以記錄的「成績減鄰域平均」揭露，不另調整。依 PR #226 的自動審查補入，QC 複核接受。
5. 某一折的擬合窗不足以擬合模型時，該折不交易，處理同第 4 點的「不交易」（平掉延續的部位，之後報酬為 0）。何謂不足（例如事件型假說的擬合窗事件少於 30 個），在預登記時寫明。

> **2026-10-20 裁決（事件 `RH-20261020-01`）**：Operator 接受 QC 的解讀：同一試驗程序在各折擬合窗內、只用過去資料的自動網格選擇（至多 20 組）算一個試驗，網格的各點不另計入 K；
> 研究者自行嘗試的不同網格、不同結構或不同程序，各是一個試驗，計入 K。這是修訂二 N5「每個結構選擇與參數變體都計入試驗數」的落實方式。
> 選項內容：樣本外序列只看到選中的那一組，選擇偏差在走動式樣本外內部承擔；另一選項是每個網格點都計入 K，K 會放大到網格大小的倍數。

考慮過的選項：巢狀走動（較精確，計算量是折數的平方，第一代不採）。

### 9.3 Sharpe 頻率（第 3 項）

第一代的 `sharpe_frequency_seconds` = 604,800（一週）。

- 帳本以 T_eff ≤ T × f ÷ max(決策週期, 最長持有期, 標籤期) 封頂。f 短於持有期時，檢定量依 √(f ÷ 持有期) 縮小，例如以日頻評估持有 3 日的策略，可偵測的 Sharpe 乘以 1.73。
- 選 f 不短於全部假說的獨立週期，上限就不生效，只剩 Bartlett 調整；報酬獨立時，檢定量與 f 無關，改用週頻在漸近意義上不損失統計力。
- 週頻下：樣本外 208 期，Bartlett 的 q = 4；PBO 的 16 塊每塊 13 期；第一段 holdout 為 2026-01-08 至 05-14，共 18 期（0.345 年）。
- 帳本的週網格以 UTC 紀元對齊，期初是星期四 00:00 UTC。
- 代價：每期樣本較少，偏態與峰度的估計較粗；第一代因此限制標籤期與最長持有期不超過 7 日（9.2）。

考慮過的選項：日頻（持有期多半長於 1 日，受上限懲罰）；日頻並限持有期不超過 1 日（排除過多假說）。

### 9.4 有效試驗數 N_eff（第 4 項）

另報，不影響 p 值；p 值一律用全帳本的 K。報兩種：以全部已完成的樣本外試驗序列的平均兩兩相關 ρ̄ 計算 N_eff = ρ̄ + (1 − ρ̄) × K；以相關矩陣的特徵值計算的有效個數。
並報以 N_eff 代替 K 時的 DSR，作敏感度參考。N_eff 是依結果而定的估計，以它決定 p 值等於事後放寬門檻。計算工具屬階段 3 的報告工具。

### 9.5 `oos_protocol` 全帳本共用（第 5 項）

第一代與第二代的全部假說使用 9.1 的同一份協定與同一個 Sharpe 頻率；協定雜湊不同的預登記，由 P5 的覆閱退回。

- V 只彙集協定雜湊與頻率都相同的試驗；共用一份協定，V 才能跨假說估計。跨假說的 Sharpe 離散度通常較大，共用會提高 SR0，結果偏保守。
- 允許逐假說的協定，等於允許以無實質差異的改動把 V 縮回下限，從而降低門檻。
- 帳本不強制這一點（9.16 第 1 點），由 P5 的覆閱落實。

### 9.6 多重檢驗的方法（第 6 項）

第一代與第二代都用 BY，FDR 水準 0.10，不主張 PRDS。

- 各假說都交易同一個高度共變的加密市場，檢定量之間可能有負相關（例如做多動能與做空反轉）；各 p 值共用同一個 K 與 SR0；能否滿足 PRDS 無法證明。BY 在任意相依下都成立。
- 10 個假說時，BY 0.10 最嚴一級的單次水準為 0.0034，與 BH 0.05 的 0.005 相近；樣本外可偵測 Sharpe 分別為 1.78 與 1.71。
- FDR 0.10 與 `no_trade` 的 PSR(0) ≥ 0.95 不衝突：10 個假說時，通過 BY 0.10 的原始 p 值不超過 0.034，PSR(0) 必大於 0.95；只有假說很少時，後者才額外剔除。
- K 是全帳本的試驗數，DSR 已就全部試驗的最大值扣除一次，再對各假說作 BY，兩者有部分重複扣除；這是 2026-10-16 裁決的內容，本節不改。

> **2026-10-20 裁決（事件 `RH-20261020-01`）**：Operator 從 QC 提出的選項中選擇「BY，FDR 0.10」。其他選項：BH 0.05（需主張 PRDS，無法證明）、BY 0.05（更嚴，統計力更低）。2026-10-16 的估算用的是 BH，本節改為 BY。

### 9.7 基準、市場貝塔與逐折的行情標示（第 7 項）

每一代的帳本基準清單為兩項：

1. `no_trade`（`strategy_independent`）：全 0，由帳本自行產生。
2. `beta_matched_btc_v1`（`exposure_matched`），每個試驗各自產生：
   - 每小時 h：b_h = Σ_i w_{i,h} × β̂_i，w_{i,h} = q_{i,h} × P_{i,h} ÷ E_h：
     q_{i,h} 是 h 開盤的成交入帳之後的部位（部位變動時刻不晚於 h 的成交累計，作廢的不計）；P_{i,h} 是開始於 h 的 K 線的開盤價（該根缺漏時取 h 之前最後一根的收盤價）；
     E_h 是期貨記帳的帳戶權益（與 §7.2 的現金恆等式相同）：現金 = 初始資金 + 已實現損益 − 手續費 + 資金費等現金調整（含部位變動時刻不晚於 h 的全部成交、結算時刻早於 h 的資金費），權益 = 現金 + Σ_i 未實現損益，未實現損益以 P_{i,h} 計價。
     不得以「現金 + 名目」計算：永續合約開倉不從現金扣除名目，那樣會重複計入（依 PR #226 的自動審查更正）。
     測試以既有部位加上 h 開盤的調整、開盤價與前一根收盤不同的案例驗證：跳空依調整前的曝險、盤中依調整後的曝險計入（依 PR #226 的自動審查修改）。
     b⁻_h 以開盤價計價，跳空起點的曝險嚴格說應以 C_prev 計價；誤差約為 w(1 − w)g²，屬二階，只在缺漏後的大跳空時明顯，接受並註明（QC 2026-10-20 對 `f597cdeea` 之後方法論改動的累積複核（PASS_WITH_NOTES））。
   - β̂_i 是標的 i 的日報酬對 BTCUSDT 日報酬的最小平方法係數，只用該折擬合窗的最後 365 日估計（相鄰兩根都存在的日報酬）。
     日報酬為簡單報酬 y_d = C_d ÷ C_{d−1} − 1（C 為日線收盤價，d 與 d − 1 兩根日線都存在，且標的 i 與 BTCUSDT 在 d 都有報酬才納入）；含截距的最小平方法：β̂ = Σ(x − x̄)(y − ȳ) ÷ Σ(x − x̄)²，x 為 BTCUSDT、y 為標的 i；
     分母為 0 時視同觀測不足；以 `Decimal` 計算。U6 的測試以平均不為 0 的手算案例驗證（含截距與不含截距結果不同的例子）；少於 90 個日觀測時，取同一物化中至少有 90 個觀測的其他標的 β̂ 的中位數。
     BTCUSDT 本身為 1；β̂ 截在 [0, 3]。holdout 證偽試驗以 [訓練段起點, 驗證段終點) 的最後 365 日估計（9.10）。
   - 跳空與盤中分開計算，使新部位不承擔它存在之前的價格變動：b⁻_h 依「每小時 h」一點的公式，但 q 改用 h 開盤成交之前的部位（部位變動時刻早於 h 的成交累計），E 改用這些成交之前的權益（同樣以期貨記帳、以同一組開盤價計價未實現損益）；b_h 即該點的 b_h（含 h 開盤的調整）。
   - 基準每期報酬 = Π_{h∈p}(1 + b⁻_h × g_h) × (1 + b_h × i_h − b_h × f_h) − 1：g_h = O_h ÷ C_prev − 1 是跳空（O_h 是開始於 h 的 BTCUSDT 1 小時 K 線的開盤價，C_prev 是前一根存在的 K 線的收盤價），i_h = C_h ÷ O_h − 1 是盤中（C_h 為該根收盤價）；
     BTCUSDT 某一小時缺漏時，該小時 g_h = i_h = 0，跳動計入其後第一根存在的 K 線的 g_h；f_h 是結算時刻落在 [h, h + 1 小時) 的資金費率，沒有結算時為 0。
     資金費以帶號曝險計入：b_h > 0 且費率為正時支付，b_h < 0 且費率為正時收取。
   - 基準不計手續費與滑點，使基準較強、比較偏保守。
   - 超額序列 = 策略 − 基準，近似扣除市場貝塔之後的結果，對應修訂二 N5 第三項。帳本無法驗證這個序列，回報時列為未驗證項。

另產生一個與策略無關的確定性序列 `btc_perp_hold_v1`，不登記為帳本基準：
- 每折測試窗開始時以全部權益做多 BTCUSDT 永續，持有到該折結束；每期報酬依 9.0 計算，含資金費；每折首尾各計一次 9.8 的吃單手續費與滑點。
- 以固定的程式版本、物化 manifest 雜湊與摺表為輸入，以帳本的 `canonical` 寫出，同樣輸入必須產生同樣位元組。
- 用途：報告策略的事後貝塔（樣本外報酬對它回歸的係數與 t 值）與 b_h 的平均；逐折的行情標示。
- 不作門檻的理由：帳本要求每個基準的超額序列 PSR(0) ≥ 0.95；以 BTC 持有為基準，市場中性的策略必須在樣本外勝過 BTC 的報酬（以年化波動約 55% 估，超額年化 Sharpe 需約 0.82，即每年多約 45%），與修訂二 N5 的「暴露相近的被動持有」不同義。
  記錄者註：這是依 N5 原文的落實，未另請 Operator 裁決；Operator 可要求加上。

逐折行情標示（Alpha 證據治理）：
1. 以 `btc_perp_hold_v1` 該折 13 週的報酬分類：不低於 +20% 為多頭，不高於 −20% 為空頭，其餘為盤整（20% 約為 BTC 13 週報酬的 0.75 個標準差）。
2. 報告各折的成本後淨損益，以及多頭折所佔的比例。
3. 「regime-bet，只作學習用途」：除去多頭折之後，把其餘各折的期數依時間順序串接，策略的複利淨值 Π(1 + r_p) 不大於 `beta_matched_btc_v1` 的複利淨值 Π(1 + b_p)。帶此標示者不得記為候選成立（9.12）。
   以複利而非報酬合計判定：+20% 之後 −18% 合計為 +2%，複利為 −1.6%（依 PR #226 的自動審查修改）。
4. 任一曆年貢獻超過樣本外淨損益的 50% 時，標示該年主導（例如「2024-dominated」），只作報告。
5. 2020–2021 年的多頭行情只在初始擬合窗內；樣本外涵蓋 2022 年的下跌與 2023–2024 年的上漲。

### 9.8 成本（第 8 項，含資金費與下架）

**9.8.1 吃單手續費**
- 費率 0.055%，雙邊計入；計費基礎是成交價（滑點之後的價格）× 數量。
- 來源：倉庫現行的吃單費率常數（例如 `prelive_edge_gate_trends.py` 的 `TAKER_FEE_RATE = 0.00055`）；QC 查到的 Bybit 官方費率表（非 VIP 永續吃單 0.0550%）只看到搜尋摘要、未開啟原頁，屬未驗證。帳戶的實際費率屬私有端點，研究不查詢。
- 壓力情境用 0.075%，涵蓋地區差異與歷史上可能較高的費率。研究一律用現行費率，因為裁決的對象是今後的交易。

**9.8.2 滑點、作廢與壓力**
- 每邊的不利滑點依決策時可知的流動性分級。分級依據是決策前 12 個完整日的日線成交額（USDT）的中位數：

  | 成交額中位數 | 每邊滑點 | 一次來回的總成本（含 0.055% 手續費） |
  |---|---|---|
  | 1 億 USDT 以上 | 5 bps | 21 bps |
  | 1,000 萬至 1 億 USDT | 10 bps | 31 bps |
  | 100 萬至 1,000 萬 USDT | 20 bps | 51 bps |
  | 未滿 100 萬 USDT | 不可開倉 | 增加曝險的訂單作廢 |

  記錄者改動 QC 原稿的 30 日為 12 日，使最長回看 13 日即可涵蓋、第二段 holdout 維持 18 週（9.16 第 5 點）；QC 複核接受，並指出 12 日中位數在流動性崩落時反應較快，屬保守方向。
- 資料不足：自首根 1 小時 K 線起不足 12 個完整日，屬「不可開倉」；缺漏的日線以成交額 0 計。第一代因此不能交易上市未滿約 12 日的標的（9.17）。
- 單筆上限：單筆名目超過決策時最後一根已收盤 1 小時 K 線成交額的 1% 時，增加曝險的訂單作廢；以 9.0 的名目資金計算。那一根缺漏時上限為 0。
  記錄者改動 QC 原稿以成交那一根的成交額為準（決策時尚不可知），改用前一根；QC 複核接受。
- 減少曝險的訂單（減倉、平倉；反手時減少曝險的一段）一律執行，不作廢（§3.4 的最小數量與最小名目除外：部分減倉低於 `minOrderQty` 或 `minNotionalValue` 時作廢，全部平倉仍執行）：「減少曝險」以單一標的計，指部位絕對值下降且不跨過 0。
  在「不可開倉」等級或超過單筆上限時，以懲罰滑價成交：60 bps（20 bps 的 3 倍）乘以壓力倍數，記為 `forced_reduce_penalty`。這一條由記錄者補充，QC 複核後補上上述定義與壓力倍數。
- 這些數值是假設，沒有盤口歷史可以校準；校準在階段 5 的 Demo 前向對照（修訂二 N4）。
- 壓力：滑點 ×1（基準）、×2、×3；另報損益兩平的滑點倍數。壓力不是新的試驗：以主試驗記錄的目標權重（決策不變），依 §6 第 4 點在壓力下的權益路徑重新換算數量並重算；決策不變對依賴自身部位或權益的假說是近似。
  帳本在主試驗開始之後不再接受該假說的新試驗（9.16 第 2 點），所以壓力結果在主試驗結束之前算出，記入 `result_summary`，並附執行紀錄的雜湊。
- 判定（9.12 的附加條件）：在滑點 ×2 且手續費 0.075% 下，樣本外的複利淨報酬（期末權益 ÷ 期初權益 − 1）仍須大於 0；這一情境若因曝險上限等原因記為失敗（§6 第 4 點），判定一律為不通過，不得以缺值略過；各期淨報酬的算術平均只作報告。

**9.8.3 資金費：時點與名目金額**
- 只在資金費歷史的實際結算時間戳計入，不假設固定 8 小時。
- 金額 = −q_T × P_T × r_T：
  - P_T 是結束於 T 的那根 1 小時 K 線的收盤價；該根缺漏時，取 T 之前最後一根的收盤價，該期依 9.14 計為填補期；
  - q_T 取 T 之前與 T 之後兩個部位中，資金費現金流較不利的那一個（§3.2 第 3 步）。
- 計價基礎的近似：Bybit 依標記價格計算持倉價值（只見搜尋摘要，未驗證）；研究以成交價 K 線近似，誤差為 |q × r| × |成交價 − 標記價|。
  每次結算另加不利調整 δ = 2%：不利的資金費乘以 1.02，有利的乘以 0.98。只要結算時兩個價格相差不超過 2%，誤差就有上界。費率 0.01% 時這項調整約為名目的 2 × 10⁻⁶（0.02 bps），費率 2% 時約為 4 bps。
- 同意以成交價近似的理由：第一代的成本以手續費與滑點為主（每次來回 21 至 51 bps）；以 δ 涵蓋之後，近似誤差不會改變裁決。
- 例外：候選的資金費損益超過其成本前毛損益的 50% 時（以資金費為主要來源的假說），記為候選成立之前，須以標記價格 K 線核對；標記價格端點不在 U1 的白名單內，屆時取數須 Operator 另行同意。

**9.8.4 下架時刻與其後的資金費**
- 恰在 `deliveryTime` 的那一筆：依 9.8.3 的 q_T 規則，T 之後的部位為 0，等於只在不利時計入（§3.9 的 G6）。交易所是否在下架時刻收付這一筆，未查證；不利時才計，是在未知下的保守取法。已知費率可達 2%（AIAUSDT、ICXUSDT）或 −1.7%（OMNIUSDT）。
- `deliveryTime` 之後的紀錄（LUNAUSDT、ANCUSDT、USTUSDT 共 174 筆）一律不計：下架之後不存在部位。U4 不寫入這些紀錄，EV-4 驗證。

**9.8.5 不在整點下架的最後一根 K 線**
- 27 個下架品種的最後一根 1 小時 K 線（以及最後一根日線）只涵蓋到 `deliveryTime`。這一根不作為決策用的 K 線：它的收盤之後沒有下一根可以成交，成交額也只代表部分時段。
- 它可以作為前一根決策的成交價（它的開盤，§3.1），也用於下架時的強制平倉計價（9.8.6）與最後一期的權益計價。

**9.8.6 下架時仍有部位的平倉價格**
- 策略不可見 `deliveryTime`，不能據此提前退場；下架時仍有的部位，在 `deliveryTime` 強制平倉。
- 平倉價格取最後一根（不論是否完整）與其前一根完整 K 線兩者中的不利極值：多頭取兩根的最低價，空頭取最高價；另計 60 bps 乘以壓力倍數的懲罰滑價（與 9.8.2 相同，不依該品種的等級）與 0.055% 手續費（§3.9 的 G7）。
- 理由：交易所的交割價格多半是某段時間的平均價格（未查證），研究也沒有取得交割價格；不利極值加懲罰滑價，應不比實際有利。
- 交易所公開的交割價格端點（`/v5/market/delivery-price`）是否適用於永續合約下架，未驗證；不在階段 2 派工指令 §4 的範圍內，第一代不取。

**9.8.7 資金費紀錄的空白**
- 空白：相鄰兩筆資金費紀錄的間隔，大於前一段與後一段實際間隔中的較小者。只依可讀範圍內的紀錄判定；在可讀範圍的右緣只和前一段比較。
  取較小者是保守取法：間隔縮短的交界缺一筆時（例如紀錄在 −8、0、8、12 小時，0 之後改為 4 小時），不會被較長的那一段掩蓋；代價是每次間隔改變的交界（縮短或延長）都多估計一筆不利的資金費並計為填補期（依 PR #226 的自動審查由「較大者」改為「較小者」）。
  只看紀錄無法區分「缺一筆」與「間隔真的改變」，而 Bybit 縮短間隔常在費率觸及上限時，這筆估計可能很大。因此：P5 之前，記錄者由 P3b 的資金費歷史統計各標的的間隔改變次數（與假說結果無關），寫入 9.18 的資料品質前檢紀錄；
  報告另列「交界估計」的成本與填補期數，評估是否逼近 9.14 的 5% 門檻（QC 2026-10-20 對 `f597cdeea` 之後方法論改動的累積複核（PASS_WITH_NOTES）的要求）。
- 在可讀範圍的左緣只和後一段比較。
- 物化邊界：可讀範圍不含邊界外的紀錄，所以跨越邊界的空白只能單側估計。若可讀範圍起點到第一筆紀錄、或最後一筆紀錄到可讀範圍終點的距離，不小於最近一段實際間隔（依觀測到的相位，邊界之內還應有至少一筆結算，含恰在邊界上者；只有一筆紀錄時，用 instruments-info 的現行間隔，U4 記入 manifest、策略不可見），
  這一段視為邊緣空白：以最近一段間隔推算估計的時刻，估計費率取最近一筆紀錄費率的絕對值，且不低於 0.01%；金額依本節末的「估計的金額」；該期計為填補期。沒有任何紀錄時，以 0.01% 與現行間隔估計。
  估計的時刻（Δ 為上述的間隔）：
  - 左緣：第一筆紀錄的時刻減 k × Δ（k = 1, 2, …），取不早於可讀範圍起點者；
  - 右緣：最後一筆紀錄的時刻加 k × Δ，取不晚於可讀範圍終點者（恰等於終點者計入，與 §4 第 3 點的端點規則相同）；
  - 沒有任何紀錄：可讀範圍內 UTC 毫秒能被 Δ 整除的時刻（Bybit 的結算以 UTC 00:00 為錨），兩端含入的規則同上。
  這些時刻依 §3.2 的第 3 步與 9.0 的期界規則歸期；`rules.py` 與 U6 各自依此產生，測試以 8 小時間隔、可讀範圍起點不在結算時刻上的案例驗證。
- 有部位跨過空白時，在空白中估計 n = max(1, round_half_up(間隔 ÷ min(前一段間隔, 後一段間隔)) − 1) 筆不利的資金費（四捨五入用 `ROUND_HALF_UP`，不用 Python 的 `round`），時刻為前一筆時刻加上 k × min(前一段間隔, 後一段間隔)（k = 1 至 n）；
  估計費率取空白前後兩筆紀錄費率絕對值的較大者，且不低於 0.01%；該期依 9.14 計為填補期。
- 估計的金額（空白與邊緣空白一律適用）：估計的資金費一律為支付，金額 = −|q| × P_T × r̂ × (1 + δ)，|q| 取 T 之前與之後兩個部位絕對值的較大者，r̂ 為上述的估計費率（非負）；不依 −q × P × r 的一般公式，使空頭部位的估計也是不利的。測試涵蓋空頭部位跨過空白（依 PR #226 的自動審查修改）。

**9.8.8 獨立重算的容差**
- 價格（成交價、結算價）：只用相對差異，不超過 1e-9。
- 手續費與每筆資金費：相對差異不超過 1e-9，或絕對差異不超過 1e-6 USDT。
- 必須完全相同：數量、作廢的訂單與原因、滑價基點、部位變動時刻、成交種類。
- 權益：每一步的絕對差異不超過初始資金的 1e-8（0.001 USDT）；U6 以 `decimal.Decimal` 由原字串計算。另比對期末權益與手續費、資金費的累計值，容差同上。
- P1b 的重算期末權益相差 0、資金費誤差小於 1e-6；超出上述容差即視為 LEAN 與重算不一致。

### 9.9 `degradation_z`（第 9 項）

`degradation_z` = 1.0，全帳本共用。

模擬條件：每週報酬、常態，10 個假說，BY 0.10；第一段 holdout 18 週（0.345 年）；以樣本外判定成立為條件。表中是誤殺率（真實策略被判不成立的機率）：

| 真實年化 Sharpe | z = 0.5 | z = 1.0 | z = 1.282 | z = 1.645 | 只檢查正負 |
|---|---|---|---|---|---|
| 1.5（K = 10） | 32% | 19% | 19% | 19% | 19% |
| 1.5（K = 100） | 31% | 20% | 19% | 19% | 19% |
| 2.5（K = 10） | 20% | 9% | 7.5% | 7% | 7% |

- 以 t 分佈（自由度 4）模擬厚尾，結果相近。量化審查原先的估計是 19% 至 42%，屬同一量級。
- 假發現在樣本外剛好達標時，SR_ref ≈ 1.36（年化），holdout 的標準誤約 1.70；z ≥ 1.0 時劣化條件幾乎不起作用，通過率約 50%，由正負判定決定；z = 0.5 時約 38%。
- 理由：z = 1.0 時，真實 Sharpe 1.5 的誤殺率不高於「只看正負」的下限 19%；樣本外 Sharpe 異常高時（例如 SR_ref = 2.5）仍有作用，假發現的通過率由 50% 降到約 32%。z = 0.5 每擋下一成的假發現，要多誤殺一成三的真實策略。
- 結論：holdout 對假發現的篩選很弱（約一半會通過），與 2026-10-16 裁決「holdout 只作證偽」一致；顯著性由樣本外承擔。

### 9.10 在 holdout 上評估哪一個模型（第 10 項）

- 沿用主試驗的同一套程序（包括 9.2 的網格與選擇規則），不沿用最後一折選出的數值。
- 擬合窗為整個樣本外範圍 [2020-01-01, 2026-01-01)，標籤終點不得晚於 2026-01-01；在 `begin_trial` 之後以此重新選擇、擬合一次（§7.0 的擬合執行），在 holdout 上評估；選出的數值與模型檔的 SHA-256 記入試驗的 `result_summary`（不是試驗身份）。
- 理由：這就是走動式的下一折，日後在 Demo 上運行的也是這套程序以最新資料擬合的模型；帳本要求 `holdout_falsification` 的變體參數雜湊與主試驗相同，程序寫在變體參數內，兩者一致。
- 第二代的模型同樣只用到 2026-01-01 為止的資料，不得用第一段 holdout；它在第二段 holdout 評估時，模型已有約 4.5 個月的時差，回報時標示。

考慮過的選項：直接用最後一折的模型（只擬合到 2025-09-24，與日後實際運行的不同）；凍結數值、只重新擬合（與主試驗的程序不一致）。

### 9.11 每折的最少交易筆數（第 11 項）

1. 計分時不剔除任何一折；交易少或不交易的折照實計入（不交易的折在平掉延續的部位之後報酬為 0，9.2 第 4 點）。依結果剔除各折屬資料相依的選擇。
2. 假說層級的下限（9.12 的附加條件，不足時不得記為候選成立）：16 折中至少 8 折有至少一筆交易。「交易」指 `kind` 為 `strategy` 的訂單的成交；框架產生的平倉（不交易折的平倉 `no_trade_flatten`、`score_end_liquidation`、`delisting_settlement`）不算該折的交易；不交易的折計入 16 折的分母、不計入 8 折的分子；樣本外完成的來回至少 200 筆。
   一筆來回是單一標的的一段部位：自部位由 0 開始（或反手後以新方向開始），到回到 0 或再次反手為止；段內的加減倉不另計；計分終點的平倉與下架結算視為完成。只計段內最大 |權重| 不小於 0.01 的來回。
   200 是集中度與穩健性的下限，統計力由週頻序列的 DSR 承擔；預期每年少於約 50 段的假說（例如低頻事件型），P5 覆閱退回，此門檻不得事後調整。
   200 依倉庫的量化審查準則（`math-model-audit`：單一策略至少 200 筆交易或 30 日，取較嚴者；在 3.99 年的樣本外，30 日不是約束）。QC 原稿為 30 筆，依 PR #226 的自動審查改為 200；QC 複核接受 200，並補上來回的定義。
   代價：最長持有期 7 日時，單一標的的策略須在 208 週中約 96% 的時間有部位才能達到；選擇性或事件型的假說實際上會被排除。
3. 擬合窗內的下限見 9.2 第 5 點：不足時該折不交易。
4. 集中度只作報告：去掉獲利最大的 5 筆來回之後樣本外淨損益的正負；單一折貢獻超過 50% 時標示。
5. 預登記的預期換手率須足以使第 2 點的下限可以達到；預期換手率須計入可能不交易的折。不能時 P5 覆閱退回。

### 9.12 「候選成立」的附加條件與第二代的時點（第 12 項）

附加條件：帳本的合格（`eligible`）與 holdout 證偽通過之外，記為候選成立還須滿足：9.7 的非 regime-bet；9.8.2 的壓力判定；9.11 第 2 點的樣本量；9.8.3 資金費主導時的標記價格核對；9.14 的填補比例；9.13 的年化 Sharpe 95% 區間下界大於 0；
U6 `submit` 的 `provenance` 經記錄者核對與重算相符（§6 第 5 點）；預登記符合 9.18 的資料品質處置；
預登記的 `selection.type` 為 `cross_sectional` 或 `filtered` 時，9.15 的下架清單完整性核對須已成立，核對紀錄的雜湊記入候選的判定文件（U1 manifest 的 `cross_sectional_candidate_allowed` 恆為 false，不以它代替核對）。

- 這些條件在主試驗結束之後、`close_generation` 之前算出，連同計算所用的雜湊提交到倉庫文件。
- 帳本規定 `open_holdout` 的候選集合必須恰好等於全部合格者，所以不符附加條件的假說仍會開啟 holdout，但不得記為候選成立。
- 不採「結算前撤回」：撤回會改變同世代其他假說的校正後 p 值，使結算結果依這些附加篩選而定。

第二代的時點：Operator 2026-10-18 已確認第二代須在第一代開啟 holdout 之前預登記並列妥試驗計畫（事件 `RH-20261018-01`）。依帳本的實作，順序與內容如下：
1. 第一代全部主試驗結束；`close_generation(1)`；第二代全部假說預登記；第二代每個假說以 `commit_trial_plan` 列出全部試驗；封存並開啟第一段 holdout。
2. 第二代的計畫須逐項寫出完整身份，包括主試驗與第二代的 `holdout_falsification` 試驗（評分窗依帳本切分算出的第二段區間）。
   帳本在第一段開啟之後，對第二代的每一種試驗（包括 holdout 證偽）都只接受已列入計畫的身份（9.16 第 3 點），因此第二代主試驗的試驗代號要事先決定，並寫入證偽項的 `primary_trial_id`。
3. 計畫在 `close_generation(1)` 之後提交，不影響第一代的 K；第二代結算時，K 含第一代全部試驗與第二代計畫中的全部非 holdout 項。
4. 第一段開啟之後，第二代不能再作計畫外的搜尋；計畫的規模宜控制在每個假說 20 項以內。
5. **前提（尚未滿足）**：帳本的 `commit_trial_plan` 只比對變體參數雜湊、`evaluation_kind`、`role`、譜系親代、資料窗與主試驗代號（`ledger.py` 的計畫欄位），不比對程式 commit、`configuration` 雜湊、成本／成交／引擎版本、manifest 與資料檔雜湊、相依套件與隨機種子。
   看過第一段 holdout 之後，研究者可以在計畫允許的身份下改動這些欄位，資訊流規則因此不成立。
   補上的比對須避免循環：holdout 證偽試驗在計畫時還沒有物化，計畫中改為預先承諾確定性的物化請求（假說、視窗、標的清單）與來源身份（U1 manifest 雜湊、程式 commit、設定雜湊、種子），資料釋出、物化產生之後，再把產生的雜湊綁定到已保留的試驗。
   在帳本補上完整身份的比對之前，不得提交第二代的試驗計畫。補上比對是帳本（U2）的行為變更，另立單元（TODO `P1-R8-S2-LEDGER-FIXES`，與接受部分序列一併處理），須 Operator 確認新的交付身分；在第一代主試驗結束之前完成。

### 9.13 區塊自助法（第 13 項）

對主試驗的樣本外淨報酬序列作平穩自助法（Politis–Romano）：平均區塊長度 max(4, ⌈T^(1/3)⌉) 期（T = 208 時為 6 週）；重抽 10,000 次；種子取該試驗的 `random_seed`。主試驗的 `random_seed` 因此必須為整數，不得為 null（P5 的預登記規則）。每個試驗只計算一次，不得更換種子、區塊長度或重抽次數重算。
1. 年化 Sharpe：報告點估計與 95% 百分位區間（2.5% 與 97.5% 分位數），以及重抽 Sharpe 不大於 0 的比例。
2. 最大回撤：每次重抽以淨報酬連乘得權益路徑，計算最大回撤（峰值到其後谷值的跌幅比例）；報告點估計與 95% 百分位區間。只作報告，不作判定（回撤依各假說登記的曝險而定，沒有與其無關的門檻）。
3. 判定（9.12 的附加條件）：年化 Sharpe 95% 區間的下界必須大於 0；否則不得記為候選成立。
   計算方法固定為 `r8_stationary_bootstrap_v1`，兩份實作必須得到相同的結果：
   - 亂數：Python 標準函式庫的 `random.Random(random_seed)`，只呼叫 `.random()`；記錄 Python 版本；
   - 每次重抽依序產生 T 個索引：第一個索引為 ⌊u × T⌋；之後每個位置先抽 u，若 u < 1 ÷ L（L 為平均區塊長度）則另抽 u′、新索引為 ⌊u′ × T⌋，否則為前一索引加 1 再對 T 取餘數（環狀接續）；10,000 次重抽依序進行，共用同一個亂數產生器；
   - 每次重抽的年化 Sharpe = 平均 ÷ 樣本標準差（ddof = 1）× √(365.25 × 86400 ÷ `sharpe_frequency_seconds`)，與帳本未年化 SR 的算法（`ledger.py` 的樣本標準差）一致，只多乘年化因子；標準差為 0 時，平均大於 0 記為 +∞、小於 0 記為 −∞、等於 0 記為 0；
   - 分位數不內插：由小到大排序，2.5% 分位數取第 ⌈0.025 × 10,000⌉ = 250 個值，97.5% 取第 9,750 個值；不大於 0 的比例 = 不大於 0 的個數 ÷ 10,000。
   這些選擇由記錄者依 PR #226 的自動審查補入，經QC 2026-10-20 對 `f597cdeea` 之後方法論改動的累積複核（PASS_WITH_NOTES）接受；報告工具單元（TODO `P1-R8-S2-REPORT-TOOLS`）以手算的小案例驗證。
4. 理由：多重檢驗之後再加這一道篩選，只剔除已通過 BY 的假說，代價是統計力。但剔除與否和假說的真偽不是獨立的（自助法用的是同一條報酬序列），子集合的錯誤發現比例可能高於原集合（例如剔除真發現、保留假發現），因此最終候選集合的錯誤發現率不由 BY 0.10 保證，屬未驗證項，報告照此陳述；BY 0.10 只對 BY 通過的集合成立（依 PR #226 的自動審查更正）。對已通過 DSR 與 BY 的候選，它多半不另起作用；只在序列的厚尾或序列相關超出 PSR 與 Bartlett 調整所能涵蓋時才剔除，這正是它的用途（`walk-forward-validation-protocol` §6）。
   QC 原稿只作報告；依 PR #226 的自動審查改為判定，QC 複核接受。
5. 計算工具屬階段 3 的報告工具，須在第一代的主試驗結束之前完成。

### 9.14 `filled_periods` 的算法（第 14 項）

一期 p 計為填補期，若下列任一情形成立：
1. 在 p 內，某個標的 i 有非零部位，而 U1 manifest 記錄 i 的 1 小時 K 線在 p 內有缺漏區間，且該缺漏的起點時部位仍未平倉；
2. 在 p 內，某個有部位的標的跨過一段資金費紀錄的空白（9.8.7）；
3. 在 p 內，資金費的計價依 9.8.3 取了 T 之前最後一根的收盤價；
4. 在 p 內，有訂單因下一根缺漏而以其後第一根的開盤成交（§3.1）；
5. 在 p 內，某個在缺漏起點時有非零部位的標的，其缺漏之後第一根存在的 K 線落在 p 內（含開始時刻恰為 p 的起點者）：跨缺漏的價格變動計入 p，即使缺漏本身在 p 之前結束。

說明：
- 缺漏的標的在缺漏期間內的損益貢獻為 0（以缺漏前最後一根的收盤價計價），跨過缺漏的價格變動計入缺漏之後第一根所在的那一期；兩者所在的期都計為填補期。其他標的的損益與現金流照常計入該期（§3.5）。
- 不計入填補期：沒有部位的期；上市之前（首根 K 線之前）與 `deliveryTime` 之後的時段；持倉量缺漏（持倉量只是特徵，缺漏時策略不作新決策，由假說登記其處理方式）。
- 帳本在 `filled_periods` 超過 T 的 5% 時記 p = 1；holdout 序列同樣報 `filled_periods`，超過 5% 時屬 9.12 的附加條件不符。
- 帳本無法驗證此欄；EV-13 以構造的缺漏驗證算法，回報時仍列為未驗證項。

### 9.15 橫截面假說的前提

- P3b 的下架探測取得多少下架品種，不能證明時點清單完整：完全移除或改名的品種可能不在 `status=Closed` 的回應內。
- 在完整性有獨立核對之前，manifest 的 `cross_sectional_candidate_allowed` 維持 false，橫截面與依標的篩選的假說不得記為候選成立（修訂二 N3 的釐清註記）。
- 核對方式：比對 `public.bybit.com/trading/` 的目錄清單（含已下架品種的歷史成交檔）與 P3b 的標的清單。只讀目錄頁，不下載資料檔；由記錄者在 P3b 之後執行，結果寫入檢查紀錄。
  目錄中有、P3b 沒有的 USDT 永續品種，逐一列出；能說明者（例如改名、從未上市）註明，不能說明者使該核對不成立。

> **2026-10-20 裁決（事件 `RH-20261020-01`）**：Operator 同意讀取 `public.bybit.com/trading/` 的目錄清單（只讀目錄頁、不下載資料檔），用來核對下架品種清單的完整性。

- 核對結果（2026-10-20，階段 2 派工指令 §8.8）：**部分成立**。目錄中有、P3b 沒有的 26 個品種，20 個是上市不早於計畫終點者；6 個不在任何 instruments-info 回應中，其成交都晚於 2026-01-01。
  但這不構成完整性的證明：目錄本身不是完整的母集合（BITUSDT、LAYERUSDT 在 P3b 中、卻不在目錄中），目錄與 instruments-info 都沒有的品種無從察覺（依 PR #226 的自動審查更正）。
  因此 `cross_sectional_candidate_allowed` 維持 false：橫截面與依標的篩選的假說仍不得記為候選成立，除非取得完整的來源或有獨立依據的完整性上界，或 Operator 裁決接受此殘餘風險（待議）。

### 9.16 與帳本實作（`ledger.py`）的關係

1. 帳本只要求同世代的多重檢驗（含成員）、Sharpe 頻率與基準相同；不比對 `oos_protocol` 與 `falsification_rule`。9.5 的共用協定與 9.9 的共用 z，只能靠 P5 的覆閱落實。
2. 某假說的主試驗一開始，帳本即拒收該假說新的 `in_sample` 與 `out_of_sample` 試驗；帳本的合格判定也不含壓力、行情、樣本量條件。因此壓力只能在主試驗結束之前以重算算出（9.8.2），附加條件在帳本之外判定（9.12）。
3. 第一段開啟之後，計畫檢查適用於第二代的每一種試驗，包括 `holdout_falsification`；階段 2 派工指令 §7.4 第 4 點的文字沒有寫明這一後果（9.12）。計畫只比對部分身份欄位，是第二代的前提缺口（9.12 第 5 點）。
4. T_eff 的上限與以 UTC 紀元對齊的期數網格，限制了頻率與邊界的選擇：週頻的期初是星期四；各折邊界不對齊時，每折頭尾不足一期的損益不進入序列，可能隱藏虧損。9.1 的邊界依此選定。
5. 第二段 holdout 的起點後移 max(空窗, 最長回看)：回看不超過 13 日時仍有 18 週；30 日時剩 15 週；60 日時剩 11 週。
   §3.6 要求最長回看不小於 13 日（流動性分級），第二代宜把回看限在 13 日，或在預登記時寫明縮短後的長度。
6. `filled_periods` 與 `exposure_matched` 序列，帳本都無法驗證（已知）。
7. 其餘數值規則（T_eff、V 的下限、DSR、BY 的調和數、PBO 的 16 塊 CSCV、證偽三項檢查、可偵測 Sharpe）都與階段 2 派工指令 §7.4 的文字一致，QC 沒有發現差異。

### 9.17 尚待處理與限制

| 項目 | 狀態 |
|---|---|
| 以資金費為主要來源的候選，是否取標記價格 K 線（9.8.3） | 屆時另請 Operator 同意 |
| 費率 0.055% 對應的帳戶等級與地區（9.8.1） | 依倉庫現行常數；帳戶費率未查詢 |
| 統計力：真實 Sharpe 1.5 的策略約 8% 會在樣本外成立（9.1） | 已向 Operator 說明 |
| 第一代限制：標籤期與最長持有期不超過 7 日；最長回看不小於 13 日；上市未滿約 12 日的標的不可開倉；預登記的 `selection` 須列出明確的標的清單（§4 第 2 點）；主試驗的 `random_seed` 必須為整數（9.13） | 寫入 P5 的預登記規則 |

### 9.18 資料品質前檢（記錄者依 PR #226 的自動審查補充，QC 複核修改）

依倉庫的驗證準則（`walk-forward-validation-protocol` §5：回測前跑 ADF、KPSS、Ljung-Box、JB 與 ARCH 效應五項檢定），在 P5 預登記之前：
1. 對象：P3b 中每個標的在**訓練段**（2020-01-01 至 2025-07-01，各標的自首根 K 線起）的 1 小時與日對數報酬；不用驗證段與 holdout。
   本前檢的結果只用於模型假設的限制與資料查錯。訓練段與樣本外範圍重疊（2022-01-06 起為計分窗），任何以前檢結果決定標的、參數或篩選的做法都等於使用計分窗的資訊，禁止。
2. 五項檢定與處置：
   - ADF 與 KPSS：ADF 不拒絕單根且 KPSS 拒絕平穩的標的，不排除，列為「資料品質待查」：記錄者查對 U1 的缺漏、異常價格與上市初期資料，結果寫入附錄；查明為資料錯誤者以 U1 的修補交付處理。
     標的的納入只能依時點可知的規則（9.0 第 5 點、9.8.2），不得依本前檢的結果。
   - JB：預期拒絕常態（厚尾）。假說的模型、倉位或門檻不得假設常態報酬；統計推論只用帳本的 DSR 與 PSR（已含偏態與峰度）與 9.13 的區塊自助法。
   - Ljung-Box（報酬與報酬平方）：自相關由帳本的 T_eff 處理；報酬平方顯著自相關即視同 ARCH 效應。
   - ARCH 效應：顯著時，任何以樣本變異數直接估計風險的假說，須改用條件變異數或在預登記中說明為何不受影響；信賴區間只用區塊自助法。
3. 檢定的水準 0.05；結果逐標的寫入預登記的附錄，並記 P3b manifest 的雜湊。
   不作多重檢定校正，結果只作描述；樣本很大時 KPSS、Ljung-Box 與 ARCH 幾乎必然拒絕，第 2 點的處置因此對全部假說一律適用，不依個別標的。
   第 2 點中對模型假設的處置（不假設常態、以 T_eff 處理自相關、以條件變異數或說明處理 ARCH、只用區塊自助法區間）是**預先固定、無條件適用**的規則，不依本前檢的結果而增減；
   前檢的結果只用於資料查錯（「資料品質待查」），不得影響任何假說的模型、參數或標的。這樣訓練段與計分窗的重疊不會讓計分窗的資訊進入預登記。
4. 停止條件：檢定工具失敗，或預登記的假說違反第 2 點預先固定的處置；任一成立時 P5 不送 Operator 覆閱。觀測數不足（少於 500 個 1 小時報酬或 60 個日報酬）的標的記為不足，不構成停止。
5. 檢定工具屬第 10 節的報告工具單元，須在 P5 之前完成；該單元因此改為 P5 之前執行。

## 10. 驗收與之後的步驟

- U4 至 U6：各單元的測試全部通過、獨立代碼審查與測試驗證通過、合入 main。
- P4-D0、P4-D：§8 的檢查通過，檢查紀錄合入 main。
- 9.15 的目錄核對由記錄者在 P3b 之後執行。
- 記錄者的收尾：在 `helper_scripts/SCRIPT_INDEX.md` 登記 U4 至 U6 的命令列入口，並寫研究工具核心的使用說明（runbook）。
- 報告工具另立單元：9.18 的資料品質前檢須在 P5 之前完成；9.4、9.7 的行情標示與事後貝塔、9.11 的集中度、9.13 的區塊自助法，在第一代的主試驗結束之前完成。
- 之後 P5 依修訂二 N1 與本文 §9 起草假說預登記（附 9.18 的結果），送 Operator 覆閱。

## 11. 回報

三個單元全部處理過之後，依階段 2 派工指令 §6 的格式一次回報，另附：每一項要求對應的測試名稱；§3.9 固定案例的重現結果；§7 介面的實際欄位與本文是否一致。

## 12. P4-D0 之後的修補（2026-10-21）

### 12.1 經過

- 三個單元都在 main `33fd730f5` 上完成本機提交：U4 `3f77a8483`、U5 `540ac84fa`、U6 `a19b12e99`。只改了各自允許的檔案。Codex 的受控審查都沒有完成：
  - U4 的 E2 在 300 秒上限到期、沒有判定；
  - U5 的 E2 PASS，E4 UNVERIFIED；
  - U6 的 E2 複核 FAIL。複核提出的新問題，記錄者另派的審查判為不可達。
- P4-D0（Codex 記錄者交付 `R8-S2-P4-D0-LEAN-SMOKE-20261020`）：以 U4 `--validation` 物化 4 組構造案例 H、G、D、L，第一個案例就在啟動器失敗，`launcher key mismatch: algorithm-location`。
- 記錄者在固定映像中查明：`config.json` 第 19 行另有一行註解 `//"algorithm-location": …`，正則同時比對到兩行。
  只比對未註解的鍵之後，4 個案例在真實 LEAN 上全部完成，與預先凍結的預期逐項相符，現金殘差為 0。案例 D 的日線可見性沒有策略端的直接證據，仍屬未驗證。
- 記錄者把這 4 次執行交給 U6 的 `recompute`，發現兩處介面不一致（12.2 第 2、3 點）。在副本上排除之後，4 次執行的獨立重算全部相符，差異為 0。
- 記錄者另派的 E2 對抗審查結果：
  - U4：PASS_WITH_NOTES，由記錄者發布，PR #227 已合入 main `62a495bfd`；
  - U5：FAIL，2 個 BLOCKER、4 個 MAJOR；
  - U6：FAIL，2 個 BLOCKER、5 個 MAJOR。
  需要修改的項目全部列入 12.2。

### 12.2 契約補充（U5、U6 共同遵守；與前文不一致時以本節為準）

1. **啟動器**：只替換未註解的鍵，也就是行首只有空白、接著是 `"鍵"` 的那一行。測試以固定映像實際的 `config.json` 片段驗證，片段須含 `//"algorithm-location"` 的註解行。
2. **驗證模式的計分窗**：`validation` 模式且 `folds` 為空時，`score_windows` 必須恰為物化的 `window`（一個元素），框架不得自行補上。U6 依 `run_config.score_windows` 處理。
3. **`run.json` 各段的排列**：
   - `orders`、`voided` 依 `order_id` 排列；
   - `fills` 依 (`change_t`, `order_id`) 排列；
   - 反手的複合訂單有兩段，`order_id`（與成交時的 `change_t`）相同；在 `orders` 與 `fills` 中，減少曝險的一段（部位移向 0 的那一段）都排在前；
   - `funding`、`endpoint_funding` 依 (`t`, `symbol`) 排列；
   - `decisions`、`steps` 依 `t` 排列；`fits` 依 `fold` 排列。
   U5 組裝時排序；U6 依同一順序產生，逐位置比對。
4. **缺漏中的標的**：結束於 s 的那根 1 小時 K 線缺漏的標的，在 s 不交給策略，不得出現在 `targets` 中（§3.5）。
   - 它的部位與未成交的訂單不變：不取消、不平倉。缺漏之後第一根送達時恢復可見。
   - 日線決策同樣以結束於 00:00 的那根 1 小時 K 線判定。
   - 9.8.2 的「那一根缺漏時上限為 0」因此只作防衛之用。
   - U6 遇到「有未成交訂單、沒有部位、該次決策不含它」的標的，不得出錯。
5. **不交易折的平倉**不寫入 `decisions`。`decisions` 只記 `on_decision` 的輸出；這筆平倉以 `orders` 中 `kind` 為 `no_trade_flatten` 的訂單記錄。
6. **差額為 0 的取代**：新決策的目標等於實際部位、而該標的有未成交訂單時，只取消那筆訂單（`cancel_reason` 為 `replaced`，`replaced_by` 為 null）。不產生新訂單，也不消耗 `order_id`。
7. **十進位跨越 LEAN 的邊界**：
   - 寫入 LEAN 的金額（資金費、下架結算的現金調整）以 `System.Decimal` 由十進位字串解析（InvariantCulture）後傳入，不經過浮點數；
   - 讀回 LEAN 的現金與數量時，以 `System.Decimal` 的精確字串轉成 `Decimal`；
   - `steps` 的 `equity`、`cash`，以及換算目標權重所用的決策時權益，一律取框架自己的 `Decimal` 帳，LEAN 的值只用於現金殘差的比對；
   - 殘差仍須恰為 0。若在固定映像中證實只能取得浮點數，停止並回報 NEEDS_CONTEXT，不得改用容差；
   - P4-D0 另加一個有 15 位以上有效數字的案例（例如數量 0.123、開盤 43246.6、5 bps）。
8. **靜態檢查**另拒絕下列寫法：
   - 存取屬性 `gi_frame`、`gi_code`、`gi_yieldfrom`、`cr_frame`、`cr_await`、`cr_code`、`ag_frame`、`ag_code`、`f_back`、`f_locals`、`f_globals`、`f_builtins`、`f_code`、`tb_frame`、`tb_next`；
   - 可變的預設參數值（串列、字典、集合的字面值或呼叫）；
   - 呼叫 `decimal.getcontext`、`setcontext`、`localcontext`。
   其餘無法以程式排除的同程序途徑，列為殘餘風險（§3.8）。
9. **效能**：每次決策建立資料視圖的成本，不得隨已可知的列數線性增加。
   - 各資料集依可知時刻排序一次，以二分搜尋取前綴；視圖是不複製的唯讀切片。
   - 資金費 T 前後的部位，以依部位變動時刻排序的累計部位查詢，不逐筆掃描全部成交；決策時的成交額查詢同理。
   - 測試以相對耗時驗證：10 萬列與 1 千列建立視圖的耗時比不超過 10 倍。不用絕對秒數。
10. **失敗執行的重算**（U6）：
    - 可由重算重現的失敗只有 `gross_exposure_cap`（§6 的兩種情形）：U6 重算到 `failure_t`，必須在同一時間步重現同一失敗：`status`、`failure_reason`、`failure_t` 都相同。
    - 由 LEAN 或假說程式本身造成、重算無從重現的失敗（`algorithm_exception`、`lean_error`、`fill_forward_bar`，以及 `invalid_decision`：它可能來自假說的 `score` 或決策輸出，U6 不執行假說程式）：U6 只核對 `failure_t` 之前的重算沒有差異、也沒有更早的失敗。失敗原因本身由記錄者以 `verification` 模式重跑時重現（§6 第 5 點）。
    - 重算在 `failure_t` 之前發現失敗或差異，即拒收、不寫入帳本。
    - 期數的處理：結束時刻早於 `failure_t` 的期數取重算的報酬；其餘（含結束恰為 `failure_t` 的那一期）填 0，並計入 `filled_periods`。
    - `failure_t` 為 null 時（LEAN 異常結束而無法確定時刻）：不比對任何時間前綴，只做不依時間的核對（雜湊、設定、身份）；整個期數網格填 0，全部計入 `filled_periods`；結算與否依 §6 第 1 點，視同不早於第一個計分起點。
11. **基準的權益**：計算 E_h 與 E⁻_h 時，只對有部位的標的計價。部位為 0 的標的不需要價格，尚未上市的標的不影響計算。
12. **計分終點沒有 K 線**：
    - 自訂成交模型拒絕以開始時刻不早於 e 的 K 線成交；這些訂單在終點平倉之前，以 `score_end` 取消。
    - e 沒有任何 K 線送達時，框架在 e 之後的第一個時間步處理終點平倉；若之後沒有時間步，就在演算法結束時處理。價格取不晚於 e 的最後一根收盤價，部位變動時刻記為 e，不得使用 e 之後的價格。
13. **成交不同步的曝險檢查**，放在 §3.2 第 1 步的下架結算之後。
14. **其他**：
    - `trial` 模式拒絕位於引擎目錄內的假說檔；
    - `score` 的回傳值必須是十進位字串，不是字串即以 `invalid_decision` 失敗。
15. **U6 的 `btc_perp_hold_v1`**：每折首尾的成交，用 BTCUSDT 決策時的流動性分級滑價與基準費率，不用 60 bps 的懲罰滑價（9.7）。
16. **U6 的貝塔估計窗**含恰結束於擬合窗終點的那根日線。
17. **U6 讀取 `trial_record`**，依 U4 實際的回傳格式 {`record`, `finished`, `status`}。測試以真實的 `ResearchLedger` 建立帳本並呼叫 `trial_record`（main 上已有 U4），不只用扁平的假函式。
18. **缺漏的資料集名稱**沿用 U4 輸出 manifest 的 `gaps` 鍵：`kline_hour`、`kline_day`、`open_interest`、`funding`。

U4 的 5 項 MINOR 記在 PR #227，holdout 啟用時一併處理。其中最需要注意的一項：`readable` 含帳本即時的 holdout 狀態，holdout 開啟之後重新物化，位元組會不同。
因此記錄者對樣本外試驗的批次核對，以及樣本外試驗的 `submit`，都必須在 `open_holdout` 之前完成。holdout 證偽試驗的提交本來就在開啟之後，由帳本單元之後的補充指令另行規定。

### 12.3 修補交付

| 交付 | 承接 | 可改檔案 | 內容 |
|---|---|---|---|
| `R8-S2-ENGINE-LEAN-FIX1-20261020` | U5 `6a126a072`、`540ac84fa` | §5 的六個檔案 | 12.2 第 1–9、12–14 點，以及第 3 點的排序 |
| `R8-S2-ENGINE-SERIES-FIX1-20261020` | U6 `411b0a090`、`2c9078700`、`a19b12e99` | §6 的兩個檔案 | 12.2 第 2–6、10–13、15–18 點（第 12 點：依同一規則重建終點的取消、平倉價格與部位變動時刻；第 13 點：同一時間步有延後成交與下架結算時，曝險檢查在結算之後，測試涵蓋這一合併情形） |

- Operator 的確認：2026-10-21 已確認兩個交付（在對話中）。原交付 `R8-S2-ENGINE-LEAN-20261020` 與 `R8-S2-ENGINE-SERIES-20261020` 的歷史、停止紀錄與審查嘗試保留，不重開、不重設額度。
- 承接來源：原提交已推送到 origin 的同名分支 `codex/r8-s2-engine-lean-20261020`（`540ac84fa`）與 `codex/r8-s2-engine-series-20261020`（`a19b12e99`），只作承接來源，不開 PR。
- 先後：
  - 本節合入 main 之後才開工（U4 已於 PR #227 合入）；
  - 先在乾淨的 main 上取得准入，再 cherry-pick 原提交（准入記錄當時的 HEAD）；
  - 原 U6 的准入仍為 ACTIVE，FIX1 開工前先以公共入口釋放（保留歷史）。
- 兩個交付的檔案不重疊，可以同時派。其餘規則同 §2；審查同階段 2 派工指令 §2.4。受控測試驗證跑不了時，代碼審查通過後停止，提交留在本機分支。
- 驗收：
  - 各自的測試全部通過，並逐位重現 §3.9 的 G1–G8；
  - U5-FIX1 代碼審查通過後，記錄者重跑 P4-D0：H、G、D、L 加上 12.2 第 7 點的精度案例；
  - 這些執行交給 U6-FIX1 的 `recompute`，差異必須為 0；
  - 都通過之後，由記錄者獨立驗證並發布。

### 12.4 之後

- P4-D0 通過之後，記錄者把檢查紀錄（含第一次的啟動器失敗）合入 main，再依 §8.2 執行 P4-D。
- 治理工具分支 `codex/governance-operator-reopen-20261020`（新增 `operator-reopen` 入口，E4 未執行）依 Operator 2026-10-21 的指示擱置，不合入。

## 13. FIX1 之後的修補（2026-10-21）

### 13.1 經過

- 兩個 FIX1 交付都只改了允許的檔案，在 main `851127b2d` 上完成本機提交：
  - U5-FIX1 `4aada352f`（128 passed）。Codex 的 E2 在 300 秒上限到期、沒有判定。
  - U6-FIX1 `60310c74f`（154 passed）。
  - 兩者都已推送到 origin 的同名分支，只作承接來源。
- 記錄者在乾淨的 checkout 重跑全部 R8 測試：U5-FIX1 為 523 passed，U6-FIX1 為 549 passed。
- P4-D0 重跑（記錄者，固定映像），用 H、G、D、L 加上精度案例 P：
  - **第一次失敗**：五個案例都在暖機的第一個時間步失敗，記為 `invalid_decision`。
  - **探針證實**：在固定映像中，pythonnet 把 LEAN 的 `System.Decimal` 一律轉成 Python 浮點數。直接讀屬性、或經反射讀取都一樣，例如 99997.0729046937550 讀回 99997.07290469376。
    - 寫入方向可行：以 `System.Decimal` 呼叫 `add_amount`。
    - 唯一精確的讀回途徑：在 .NET 端以 `Newtonsoft.Json.JsonConvert.SerializeObject` 序列化 `Cash`，取得 `"Amount":99997.072904693755`。
    - U5-FIX1 依 12.2 第 7 點拒收浮點數，但這個錯誤被歸為 `invalid_decision`，而不是邊界錯誤。
  - **修正後的結果**：在副本上改以上述 JSON 途徑讀現金，其他 LEAN 數值以浮點數的 `repr` 轉換，限 15 位有效數字之內。五個案例全部符合預期、現金殘差為 0。
    - 案例 P 的成交價 43268.2233、手續費 2.927095306245、資金費 -0.667420464474 都逐位相符，最終現金 99988.7886242630335。
    - U6-FIX1 的 `recompute` 對這五次執行的差異全部為 0。
- 記錄者另派的 E2 審查兩者都判 FAIL：
  - U5-FIX1：1 個 BLOCKER、2 個 MAJOR；
  - U6-FIX1：1 個 BLOCKER、3 個 MAJOR。
  多數是兩個單元在第 12 節沒有寫死的細節上做法不同。13.2 一律以 U5 的做法為準寫定，兩個單元都要照做。

### 13.2 契約補充（與前文、第 12 節不一致時以本節為準）

1. **LEAN 邊界**（U5）：
   - 現金：以 .NET 端的 `JsonConvert.SerializeObject` 序列化 `cash_book["USDT"]`，再以 `Decimal` 解析 `Amount`。
   - 價格：一律取自框架自己讀入的物化資料（`lean/` 的十進位字串），以 K 線開始時刻對應；LEAN 的 K 線只用於判斷時刻與是否存在。兩者不一致（缺列、或 LEAN 的浮點值與字串不符）即以 `lean_error` 失敗。
   - 成交：價格、數量、手續費由框架自己計算並記錄，不從 LEAN 的成交事件讀回。
   - 邊界轉換或讀取的錯誤一律記為 `lean_error`；`invalid_decision` 只用於決策本身不合規定（目標的標的集合或格式、`score` 的格式）。
2. **曝險檢查的價格表**（U5、U6）：含所有有部位或有未成交訂單的標的。不在該次決策中的標的（例如缺漏中），取決策時刻之前最後一根的收盤價。
3. **不交易的折**（U5、U6）：
   - 在該折計分窗起點的時間步，先取消所有標的的未成交訂單（`cancel_reason` 新增 `no_trade`）；
   - 再對該步可見的標的下目標權重 0（`no_trade_flatten`）。目標集合就是可見集合，含部位為 0 的標的；差額為 0 的不產生訂單。
   - 起點時不可見、且仍有部位的標的，在該折內第一次恢復可見的時間步平倉；起點那一步全部標的都不可見時同理。
   - 該折內不再有其他訂單。
4. **失敗執行的 `orders`**（U6 依 U5 的做法）：
   - `orders` 只記已成交、已取消或已作廢的訂單；執行失敗時仍未成交的訂單不記。
   - 決策時的曝險檢查在建立訂單、取消與作廢之前執行；超過上限時，該次決策不產生任何訂單紀錄。
5. **執行終點**（U5、U6）：
   - 執行終點等於物化的 `window.end`。
   - 結算時刻晚於最後一個時間步、早於 `window.end` 的資金費，在演算法結束時照常計入 `funding` 與 LEAN 現金；恰在 `window.end` 的計入 `endpoint_funding`。
   - 本點取代 §3.5「執行的結束時刻以最後一根資料為準」中有關資金費的部分。
6. **計分終點的時刻與先後**（U6 依 U5 的做法）：
   - 以 `score_end` 取消的訂單，`cancel_t` 為實際處理的時刻：e 之後的第一個時間步，或演算法結束時的 `window.end`。
   - 時刻等於 e 的時間步，先處理全部界線（下架結算、終點平倉），再做曝險檢查。
7. **靜態檢查**（U5）另拒絕：
   - 屬性 `format`、`format_map`；
   - 內建函式 `getattr`、`setattr`、`delattr`、`vars`、`dir`、`globals`、`locals`、`eval`、`exec`、`compile`、`__import__`、`open`。
   資料視圖不得經由任何公開屬性取得可知時刻之後的列。
8. **測試**：
   - U5 須有以假 LEAN 驅動 `framework.py` 流程的測試，涵蓋第 2、3 點的情形（缺漏標的延後成交後的曝險檢查；不交易折起點有缺漏標的、有未成交訂單、全部不可見）。
   - U6 的回歸測試須以 U5 形狀的執行紀錄為輸入，不可只用 U6 自己重算的結果當觀測值。

### 13.3 修補交付

| 交付 | 承接 | 可改檔案 | 內容 |
|---|---|---|---|
| `R8-S2-ENGINE-LEAN-FIX2-20261021` | U5-FIX1 `f81010cce`、`2c3b25b14`、`4aada352f` | §5 的六個檔案 | 13.2 第 1、2、3、5、7、8 點 |
| `R8-S2-ENGINE-SERIES-FIX2-20261021` | U6-FIX1 `a978ae158`、`a9113d73c`、`6f6b13751`、`c086bb301`、`60310c74f` | §6 的兩個檔案 | 13.2 第 2、3、4、5、6、8 點 |

- Operator 的確認：2026-10-21 已確認兩個交付（在對話中）。FIX1 交付的歷史、停止紀錄與審查嘗試保留，不重開。
- 承接來源：origin 的 `codex/r8-s2-engine-lean-fix1-20261020` 與 `codex/r8-s2-engine-series-fix1-20261020`。
- 先後與規則同 12.3：本節合入 main 之後才開工；在乾淨的 main 上先取得准入，再 cherry-pick。兩個交付的檔案不重疊，可以同時派。
- 驗收：
  - 各自的測試全部通過，並逐位重現 §3.9 的 G1–G8；
  - 記錄者重跑 P4-D0，案例為 H、G、D、L、P，另加三個案例：
    - Q：缺漏標的有未成交訂單，延後成交；
    - N：不交易的折，起點有缺漏標的；
    - E：e 沒有 K 線；
  - 這些執行交給 U6-FIX2 的 `recompute`，差異必須為 0；
  - 之後由記錄者獨立驗證並發布。

## 14. FIX2 之後的修補（2026-10-21）

### 14.1 經過

- Operator 2026-10-21 指示：Claude Code 擔任 R8 conductor，只負責檢查與最終把關；具體工作派給 Codex。記錄者的執行由 Codex 負責，conductor 獨立核對。
- 兩個 FIX2 交回：U5 `6bb60cf3f`（E2 初審 FAIL，唯一複核 PASS；E4 受控入口拒絕、測試未執行）、U6 `bfa151375`（E2 PASS；E4 受控入口拒絕、測試未執行）。兩者的准入與租約皆已釋放，停止紀錄保留；E2 通過不代表獨立驗收完成。
- 記錄者第一次重跑完整 `program_code/research/tests`，在五個既有非 R8 測試的收集錯誤後停止，LEAN 與重算均未執行。conductor 隨後明示全部 R8 依 CI 的 `test_r8_*.py` 範圍重跑；兩棵合併樹都固定 U6-FIX2 `bfa151375`，結果如下（本機回歸，不是 hosted CI）：

| U5 版本 | U5 passed | U6 passed | 全部 R8 passed | failed / skipped / error |
|---|---:|---:|---:|---|
| `6bb60cf3f` | 166 | 171 | 732 | 各組均 0 / 0 / 0 |
| `eb669cd3c` | 164 | 171 | 730 | 各組均 0 / 0 / 0 |

- P4-D0 九案例 × 兩個 U5 版本的最新結果如下。N、B 使用「原框架＋明示驗證 fixture」（只改 `examples/fixed_schedule.py` 的 `score`，見 14.2 第 4 點）；E 使用補齊軸宣告的設定重跑。診斷轉接只在副本上把 U5 的類別軸對應轉為 U6 接受的軸名清單，**不作 U6 驗收**。

| 案例 | `6bb60cf3f`：LEAN／殘差／原 U6 重算 | `eb669cd3c`：LEAN／殘差／原 U6 重算 | 診斷轉接（不作驗收） |
|---|---|---|---|
| H | 相符／0／差異 0 | 相符／0／差異 0 | 未執行 |
| G | 相符／0／差異 0 | 相符／0／差異 0 | 未執行 |
| D | 相符／0／差異 0 | 相符／0／差異 0 | 未執行 |
| L | 相符／0／差異 0 | 相符／0／差異 0 | 未執行 |
| P | 相符／0／差異 0 | 相符／0／差異 0 | 未執行 |
| Q | 相符／0／差異 0 | 相符／0／差異 0 | 未執行 |
| N | 相符／0／事件重建前拒絕 | 相符／0／事件重建前拒絕 | 兩版差異 0 |
| E | 相符／0／事件重建前拒絕 | 相符／0／事件重建前拒絕 | 兩版差異 0 |
| B | 不符，`lean_error`／0（失敗執行）／事件重建前拒絕 | 相符／0／事件重建前拒絕 | `eb669cd3c` 差異 0；`6bb60cf3f` 只比對失敗前區段、差異 0，但 `recompute_passed=false`，不能證明折界相符 |

- 上表為最新 18 次執行；另保留 E 舊設定的兩次執行，歷史共 20 次。案例 D 的策略端日線可見性直接證據仍未驗證，不因數值相符而改判。
- **折界**：conductor 審讀發現 `6bb60cf3f` 在成交模型內先啟用新折並取消舊單，與 §3.2 第 1 步衝突。該提交源自 FIX2 代碼審查初審把 §13.2 第 3 點讀成「折界處理在原生成交之前」，原初審與唯一複核紀錄保留。
  - 案例 B 的 s = `2022-01-15T02:00:00Z`（`1642212000000`），X 為 BTCUSDT，Y 為 MIDUSDT。`6bb60cf3f` 把決策於 s − Δ、成交 K 線開始於 s − Δ 的 X 單以 `no_trade` 取消，`fills` 為空，並在 s 以 `lean_error` 失敗。殘差 0 不是完成案例的證據；例外的具體觸發分支仍未驗證。
  - `eb669cd3c` 的 X 先以 `100.05` 成交，Y 以 `no_trade` 取消，X 於 s 的 `no_trade_flatten` 以 `100.9495` 平倉；最終現金 `100007.88950275`，與事前預期逐位相符。
- **鄰域**：原契約未寫定 `neighborhood` 的形狀。U5 要求 `categorical` 為 `{軸: [取值]}`，U6 要求軸名清單且網格點的鍵恰為已宣告的軸；沒有任何鄰域設定能同時被兩者接受。原版 U6 對 N、E、B 的重算全部在事件重建前拒絕；以僅供診斷的轉接換掉格式後，N、E 兩版與 B 的 `eb669cd3c` 版重算差異皆為 0，不能據此發布原版 U6。
- **次要不一致**：U5 的不交易等待集合含零部位標的，恢復可見時多做一次平倉決策並更新曝險檢查的參照價格；U6 只對仍有部位者處理。
- 證據位於倉庫外的下列目錄，原報告與停止紀錄唯讀保留。各列為該目錄 `REPORT.md` 的 SHA-256：

| 證據目錄 | REPORT.md SHA-256 |
|---|---|
| `/Users/ncyu/Projects/TradeBot/audits/2026-10-21-r8-p4-d0-fix2-rerun/` | `01e9b6073f3d4e8f828e16ee80bea6e4f31ef57e5a9373c4b6f291e2eb23581d` |
| `/Users/ncyu/Projects/TradeBot/audits/2026-10-21-r8-p4-d0-fix2-dual-rerun/` | `aff4b4c8636b33b7a8431e3ae88a810b359df7193049c7b85f434e64c43d45f2` |
| `/Users/ncyu/Projects/TradeBot/audits/2026-10-21-r8-p4-d0-fix2-fixture-diagnostic/` | `7dd72d3372de1db6e327936d9496411e65ebe77b85cfacc454ea498a55a203b8` |

- FIX2 交付報告：`/Users/ncyu/Projects/TradeBot/audits/2026-10-21-r8-s2-engine-lean-fix2/REPORT.md`，SHA-256 `1a5506a4db2db5133e6cae308630cb5d3142c1f5a0b560f3fed3f34edb552d72`；`/tmp/r8-s2-engine-series-fix2-20261021/delivery-report.md`，SHA-256 `82279504d47a8159577858b8a0bf6b87c40c015950357c1933b38b182cacb236`。這些本機報告的存在不等於本節或實作已合入 main。

### 14.2 契約補充（與前文、§12、§13 不一致時以本節為準）

1. **折界的先後**：時間步 s 先依 §3.2 第 1 步，把決策於 s − Δ、以 s − Δ 開盤價成交的訂單入帳（含前一折下的訂單），之後才處理計分窗起點（啟用新折、§13.2 第 3 點的取消與平倉）。§13.2 第 3 點所稱「未成交訂單」，指此後仍未成交者，也就是成交 K 線開始於 s 或更晚的訂單。框架不得在成交模型內提前啟用新折或取消前述應先入帳的訂單。U6 現行做法即為此規則，不改。
2. **`neighborhood` 的形狀**（Operator 2026-10-21 選定，以 U6 的做法為準）：
   - `{"numeric": {軸名: [取值, …]}, "categorical": [軸名, …]}`；兩個鍵都必須有（可以是 `{}`、`[]`），不得有其他鍵；
   - 數值軸的取值非空、以十進位比較嚴格遞增；類別軸名不重複；兩類軸名不重疊；
   - 每個網格點的鍵恰為全部已宣告的軸；數值軸上的值必須在列出的取值之中；
   - U5 的執行器在啟動 LEAN 之前驗證，不符即拒絕執行設定、不產生 `run.json`；框架內 `select_grid_point` 保留同一檢查。U6 不改。
   - 下列 JSON 為 `strategy` 中的鄰域與網格範例，含一個數值軸、一個類別軸及四個網格點。U5 的測試須直接使用這段原文：

   ```json
   {
     "neighborhood": {
       "numeric": {"lookback": ["10", "20"]},
       "categorical": ["mode"]
     },
     "grid": [
       {"lookback": "10", "mode": "trend"},
       {"lookback": "20", "mode": "trend"},
       {"lookback": "10", "mode": "revert"},
       {"lookback": "20", "mode": "revert"}
     ]
   }
   ```

3. **不交易折的恢復平倉**（補 §13.2 第 3 點）：起點時不可見的標的，只有仍有部位者在折內第一次恢復可見的時間步平倉；零部位的標的恢復可見時不產生決策，也不更新曝險檢查的參照價格與權益。
4. **驗證範例**：`examples/fixed_schedule.py` 的 `score` 在網格參數含 `no_trade_at` 時，對驗證窗終點不早於該值的折回傳 `"-1"`，其餘回傳 `params["score"]`（只供 P4-D0 的 N、B 與 P4-D 的 EV-14 構造「前折交易、後折不交易」）。驗證設定須把網格點用到的全部鍵宣告為類別軸，以符合第 2 點。

本節只補明折界、鄰域形狀、恢復平倉與驗證範例；§9.2 的合格點、鄰域平均與同分選擇規則不改。既有規則、實作與測試的保留範圍見 14.3。

### 14.3 修補交付

| 交付 | 承接 | 可改檔案 | 內容 |
|---|---|---|---|
| `R8-S2-ENGINE-LEAN-FIX3-20261021` | U5-FIX2 的 `0a6f0d52f`、`f817fecc4`、`acea8fe51`、`eb669cd3c`（依序；不承接 `6bb60cf3f`） | §5 的六個檔案 | 14.2 第 1–4 點；新增符合第 1 點的假 LEAN 流程測試 |

- Operator 的確認：2026-10-21 已確認（在對話中；事件 `RH-20261021-01`）。另立 FIX3，由實作者執行；FIX2 交付的歷史、停止紀錄與審查嘗試保留，不重開。U6-FIX2 `bfa151375` 不另修，與 U5-FIX3 一同發布。
- 承接來源：origin 的 `codex/r8-s2-engine-lean-fix2-20261021`（head `6bb60cf3f`），只作承接來源，不開 PR；只依上表承接至 `eb669cd3c`，丟棄最後一筆的變更、不刪除其歷史。U6-FIX2 的 `codex/r8-s2-engine-series-fix2-20261021`（`bfa151375`）亦已原樣推送，保留作驗證與發布來源。
- 先後與規則同 12.3：本節先以文件 PR 交 conductor 審過，CI 與自動審查無阻塞後由 conductor 合入 main，之後才開工；在乾淨的 main 上先取得准入，再依序 cherry-pick。契約的 surfaces 須含 `agent_workflow`；寫入租約取最長並在長工作中續租。
- 不得改：§13.2 第 1、2、5、7 點已完成的實作與其測試；§3.9 的 G1–G8；§7 介面的欄位；U6 的兩個檔案。鄰域形狀依 14.2 第 2 點補明，不新增 §7 欄位。
- 測試要求：
  - **折界**：以符合 14.2 第 1 點的假 LEAN 流程測試，取代 `6bb60cf3f` 寫錯的折界測試；X（成交 K 線開始於 s − Δ）先成交、再於 s 以 `no_trade_flatten` 平倉；Y（成交 K 線開始於 s）以 `no_trade` 取消；擬合終點恰於折界與否各一例。
  - **鄰域**：直接使用 14.2 第 2 點的範例 JSON；另有拒絕案例：`categorical` 為對應、網格點多出未宣告的鍵、兩類重疊、數值軸不遞增。
  - **恢復平倉**：零部位標的恢復可見時不產生決策、曝險參照價格不變。
  - **驗證範例的 `no_trade_at`**：前折交易、後折不交易。
- 審查：代碼審查的提問須附 §3.2 第 1 步與 14.2 第 1 點的原文。受控測試驗證跑不了時，代碼審查通過後停止，提交留在本機分支。
- 驗收：
  - U5 的測試全部通過，並逐位重現 §3.9 的 G1–G8；
  - 記錄者以 U5-FIX3 與 U6-FIX2（不加任何轉接）重跑 P4-D0 九個案例 H、G、D、L、P、Q、N、E、B，每次交 U6-FIX2 的 `recompute`，差異必須全部為 0；
  - 之後由記錄者獨立驗證，並發布 U5-FIX3 與 U6-FIX2；P4-D0 的檢查紀錄合入 main（§12.4）。

## 15. 驗證範例的可見性探針（2026-10-21）

### 15.1 經過

- P4-D A 段共 11 項：EV-3、EV-4、EV-5、EV-6、EV-7、EV-8、EV-13、EV-14 共 8 PASS；EV-9 的原始科學記號被 U6 拒絕，已由記錄者小修 PR #232 處理。修正後以原 `run.json` 重算，`recompute_passed=true`、差異 0；另 30 個既有執行（A 段 21 個有效執行與 P4-D0 九案例）的重算輸出與原檔逐位相同，沒有重跑 LEAN。PR #232 已合入 main `4e86c9f76`。
- EV-1、EV-2 無法取得策略端直接證據，原因是契約內部衝突：§8.2 要求以構造訊號驗證「策略實際收到的」日線只到前一日、持倉量在時間戳 ＋ 4 小時後才可見；§5 第 4 點卻限定 `validation` 模式只能執行正式 `examples/fixed_schedule.py` 的固定類別，而它不讀資料。另寫的日線與持倉量探針被固定類別入口拒絕，沒有執行；原固定排程的成交相符、物化的 `known_at` 相符，均不能替代策略實收證據。P4-D0 紀錄中 D 的策略端日線可見性仍為 UNVERIFIED，EV-10～EV-12 尚未執行。
- Operator 2026-10-21 在對話中以選項回覆選定「在正式驗證範例加可見性探針」，並確認另立 `R8-S2-ENGINE-LEAN-FIX4-20261021`，只改範例檔與測試；先合入本節，再由實作者開工，之後在真實 LEAN 重跑 EV-1／EV-2。這同時用來關閉 D 的策略端日線可見性 UNVERIFIED；在 15.3 驗收完成前，不改判為已驗證。路線事件為 `RH-20261021-02`。
- 原失敗與修正後證據各自保留於倉庫外，以下為各目錄 `REPORT.md` 的 SHA-256：

| 證據目錄 | REPORT.md SHA-256 |
|---|---|
| `/Users/ncyu/Projects/TradeBot/audits/2026-10-21-r8-p4d-a/` | `2deca9fb39fa564e144de122ba341994fe2264ae32c642ea1f7507b26116bb89` |
| `/Users/ncyu/Projects/TradeBot/audits/2026-10-21-r8-u6-sci-notation-fix/` | `cbaebb8eb5dfdbca189cbd8453533ca8a6d045928cedeb5a647675719767311a` |

### 15.2 契約補充（與前文不一致時以本節為準）

1. **探針參數**：`FixedSchedule` 的網格參數可含 `visibility_probe`，只在 `validation` 模式有意義；`trial`／`verification` 模式不得使用正式範例，本點不改變這一規定。形狀為：

   `{"t": <決策時刻，UTC 毫秒>, "symbol": <標的>, "dataset": <資料集名稱>, "field": <欄位>, "map": {<該欄位值的十進位字串>: <數量的十進位字串>}}`

   資料集名稱與欄位以框架交給策略的資料視圖實際使用的名稱為準，實作者查明後寫入測試。目前公開視圖的日線資料集為 `kline_day`，價格欄位含 `open`、`high`、`low`、`close`（日線探針可用 `close`）；持倉量資料集為 `open_interest`，數值欄位為 `value`。
2. **探針行為**：在時刻 `t` 的 `on_decision`，經由框架交給策略的**同一個資料視圖的公開介面**，取該標的、該資料集在此刻可見的最後一列，以其欄位值查 `map`，回傳 `{symbol: {"quantity": map[值]}}`。其他交給策略的標的照 `schedule` 或目標 0，由實作者擇一並寫明，須符合 §7 的 `decisions` 必須含當時交給策略的每一個標的。值不在 `map` 中，或該時刻沒有可見列時，拋出例外，以 `algorithm_exception` 失敗，不得默默回傳預設值。不得讀物化檔案或任何資料視圖以外的來源；其餘時刻照原 `schedule`。
3. **鄰域宣告**：`visibility_probe` 依 §14.2 第 2 點宣告為類別軸。
4. **構造方法（供 EV-1、EV-2）**：令「前一日已完成的日線」與「當日未完成的日線」的欄位值不同，各自映射到不同的數量；持倉量令時間戳 T 與 T − 4 小時兩列的值不同，各自映射到不同的數量，探針時刻取 T 之後、T ＋ 4 小時之前，再加一個恰在 T ＋ 4 小時的探針。由成交的數量即可直接讀出策略看到的是哪一列；U6 照常重算，決策已記在 `run.json`。
5. **保留範圍**：U6 不改；U4 不改；執行器的固定類別限制不改。

### 15.3 修補交付

| 交付 | 承接 | 可改檔案 | 內容 |
|---|---|---|---|
| `R8-S2-ENGINE-LEAN-FIX4-20261021` | main（U5-FIX3 已合入） | `examples/fixed_schedule.py`、`tests/test_r8_engine_lean.py` | 15.2 第 1–3 點 |

- 上表兩個檔案的倉庫路徑分別為 `program_code/research/r8_engine/lean_algo/examples/fixed_schedule.py` 與 `program_code/research/tests/test_r8_engine_lean.py`。
- Operator 的確認：2026-10-21（在對話中；事件 `RH-20261021-02`）。
- 先後：本節先以文件 PR 交 conductor 審過，CI 與自動審查無阻塞後由 conductor 合入 main，之後才開工；在乾淨的 main 上先取得准入；契約的 surfaces 須含 `agent_workflow`；寫入租約取最長。
- 不得改：框架、規則、執行器、U4、U6；§3.9 的 G1–G8；FIX3 的全部測試。
- 測試：以假 LEAN 驅動，日線與持倉量各有「只看到應看到的列」與「若前視會看到另一列」兩種構造，前者回傳對應數量，後者的數量不同；值不在 `map`、沒有可見列各一例拋出例外；未帶 `visibility_probe` 時行為不變，既有測試全部通過。
- 審查：代碼審查提問須附 15.2 原文；受控測試驗證跑不了時，代碼審查通過後停止，提交留在本機分支。
- 驗收：記錄者以 FIX4 在固定映像重跑 EV-1（日線部分）與 EV-2（持倉量部分），預期值先凍結再執行，LEAN 與預期相符、殘差 0、U6 重算通過且差異 0；之後由記錄者發布，並把 P4-D 的 A 段結果併入檢查紀錄。

## 16. 現金殘差的表示精度容差（2026-10-21）

### 16.1 經過

- P4-D B 段 EV-10 使用 BTCUSDT＋BENDOGUSDT 的真實訓練資料，加減倉後平均成本為無限小數；LEAN 以 .NET `System.Decimal`（28–29 位有效數字）記帳。自 `2024-07-03T02:00:00Z` 起，每步 LEAN 現金與框架的 `Decimal` 預期差 `1e-23`，現金約 `99833`，恰為 28 位有效數字的最後一位（1 ulp），差額不累積。原診斷以事件時序與帳務程式支持表示精度的解釋，沒有宣稱已取得 .NET 內部平均成本的逐步追蹤。
- 容器內 `finished=completed`，但 `assemble_run` 依原「殘差必須為 0」規則把執行標為 `failed`／`lean_error`。原紀錄有 48 筆非零殘差（含結束時同時刻另記的一筆），每筆 `1e-23`；`total=0.00000000000000000000048` 是逐筆加總，不是最後現金的差額。
- 以完整路徑重播，8 筆成交、18 筆資金費、37,502 步均在 §9.8.8 容差內，最大差 `4.472101636863276116134e-24`（約 `4.47e-24`）。這是診斷重播；原 EV-10 的正式 `recompute_passed=false`，不能以完整路徑相符取代原失敗結論。
- EV-11 通過壓力數值核對：執行 `completed`、8 筆成交、18 筆資金費、37,502 步，現金殘差 0，U6 `recompute_passed=true`、`differences=[]`，最大差 `3.122386395316420407026e-24`，在 §9.8.8 容差內。EV-10 基準失敗所阻擋的正式 stress／損益兩平仍未成立，不據此宣告 B 段完成；EV-12 另行量測。
- 證據目錄：`/Users/ncyu/Projects/TradeBot/audits/2026-10-21-r8-p4d-b/`；`REPORT.md` SHA-256：`33c24087fab442a351816234511eb45b65bfd1ed69e28b6d1d23696048bfd2c1`。原失敗、診斷與停止紀錄保留；[P4-D 檢查紀錄](2026-10-21--r8-stage2-p4-d-check-record.md) §8 追加 B 段狀態更正。
- Operator 2026-10-21 在對話中以選項回覆選定「加精度容差」：把超過 .NET decimal 解析度界限的差定義為未解釋殘差，每步 100 ulp 以內作表示誤差、仍全部記錄；確認另立 U5-FIX5 與 U6-FIX3，使用同一判定規則，先合入本節再實作。路線事件為 `RH-20261021-03`。

### 16.2 契約補充（與前文、§8、§12–§15 不一致時以本節為準）

1. **定義**：時間步 t 的現金殘差 r_t ＝ LEAN 現金（§13.2 第 1 點的 JSON 讀回）－ 框架預期現金；ulp_t ＝ max(10^(e_t − 27), 10^−28)，其中 e_t 為 `run.json` 該步 `steps[].cash`（框架預期現金）以十進位表示的調整指數（Python `Decimal.adjusted()`；現金為 0 時取 10^−28）。
2. **判定**：|r_t| ≤ 100 × ulp_t 為表示誤差；超過者為未解釋殘差。演算法結束時的殘差以最後一個時間步的現金計算 ulp。
3. **記錄**：`run.json` 的 `unexplained_cash_residual` 欄位名稱與形狀不變，仍逐步記錄**所有**非零殘差（不隱藏表示誤差）；`total` 照舊只作記錄，不作判定。
4. **U5**：`lean_runner.assemble_run` 只在出現未解釋殘差時把執行標為 `failed`／`lean_error`，`failure_t` 為第一個未解釋殘差的時刻；全部殘差都在容差內時，以容器的結果為準。
5. **U6**：`recompute` 只在任一步出現未解釋殘差（依第 1、2 點以 `run.json` 的現金獨立計算界限）時記入 `differences`；容差內的殘差不影響 `recompute_passed`。報告另輸出最大殘差的 ulp 倍數。
6. **既有通過條件**：§8.1、§8.2 與前文各處「`unexplained_cash_residual` 為 0」的通過條件，一律改讀為「沒有未解釋殘差（第 2 點）」。已通過的檢查殘差皆為 0，結論不變。
7. **不改**：§3.9 的 G1–G8；§9.8.8 的容差；`run.json` 的其他欄位；U4。

### 16.3 修補交付

| 交付 | 承接 | 可改檔案 | 內容 |
|---|---|---|---|
| `R8-S2-ENGINE-LEAN-FIX5-20261021` | main | `program_code/research/r8_engine/lean_runner.py`、`program_code/research/tests/test_r8_engine_lean.py` | 16.2 第 1–4 點 |
| `R8-S2-ENGINE-SERIES-FIX3-20261021` | main | `program_code/research/r8_engine/series.py`、`program_code/research/tests/test_r8_engine_series.py` | 16.2 第 1、2、3、5 點 |

- Operator 的確認：2026-10-21（在對話中；路線事件 `RH-20261021-03`）。兩個交付的檔案不重疊，可同時派。
- 先後：本節合入 main 之後才開工；在乾淨的 main 上先取得准入；契約的 surfaces 含 `agent_workflow`；租約取最長。
- 測試：兩邊各自要有下列案例，且 U6 的觀測值以 U5 形狀的執行紀錄人工構造，不用 U6 自己的輸出當觀測值；以 Decimal 手算界限值寫在測試中。
  - 殘差為 0；恰為 100 ulp（通過）；101 ulp（失敗）。
  - 現金數量級跨越（例如 9.99…×10^4 與 1.00…×10^5）時 ulp 隨之改變；現金為 0；負殘差。
  - 一筆未解釋殘差之前有多筆表示誤差時，`failure_t` 取未解釋的那一筆。
- 審查：代碼審查提問須附 16.2 原文，並請審查者核對兩個單元對同一份執行紀錄的判定必然一致。受控測試驗證跑不了時，代碼審查通過後停止，提交留本機分支。
- 驗收：記錄者在兩個修補合併後的樹上，以同一份物化與設定重跑 EV-10；執行須為 `completed`、沒有未解釋殘差、U6 `recompute_passed=true`、差異 0。並以修正後的 U6 重算先前全部已通過的 P4-D0 與 P4-D 執行，結果與原重算一致；之後由記錄者發布。

## 17. 研究資料驗證與更正規範（2026-10-22，待 Operator 核准）

見[〈R8 研究資料驗證與更正規範〉](2026-10-22--r8-stage2-data-verification-standard.md) §6：已記錄 Operator 的 open、成交額、暫行驗收及上市期方向裁決；上市門檻與實施細節仍待確認。**整份規範核准前不生效。**
