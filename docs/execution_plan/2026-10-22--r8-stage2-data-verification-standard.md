# R8 研究資料驗證與更正規範

| 欄位 | 內容 |
|---|---|
| 文件日期／時區 | 2026-10-22／Europe/Madrid；資料時間一律 UTC |
| Route-Id／事件 | R8／起草 `RH-20261022-02`；方向裁決 `RH-20261022-03`；整份核准 `RH-20261022-04` |
| 狀態／效力 | **APPROVED — Operator 2026-10-22 已核准；自 PR #240 合入 main 時生效** |
| 記錄者／把關 | Codex 執行記錄者工作；Claude Code 擔任 conductor（Operator 2026-10-21 分工） |
| 起草／整合基線 | 起草 main `6c96b8806cc472bcb9da39241f495930cea3d8a8`；整合 main `ea3cdae1dc767e2c4766199e599698d60640092c`（PR #239，研究核心程式未變） |
| 工作項目 | `P1-R8-S2-DATA-VERIFY`；ACTIVE、`dispatchable=true`（本列與規範同一 PR 合入後生效） |
| 本次交付 | 文件 PR；不改程式、不取數、不更動 P3b／帳本、不更新 Wiki、不合併 |
| 核准與實作的區分 | Operator 以四項選項回覆核准剩餘參數、DV6、抽樣計畫及整份規範（§2.1、§6.4、§12）；conductor 方法論審查完成。核准不等於已合入、工具完成或資料驗收通過；舊資料未決後續 A／B 處置仍待凍結稽核結果 |

## 1. 目的、範圍與效力

**版本二修訂註記（2026-10-22）**：下列原文與勘誤一保留其 v1 歷史語義；本次 Operator 的 B／(e) 裁決、效力及尚未實作的界線見新增 §13「版本二：成交量語義——尾段補入、逐筆為準（DV-V2）」。本次文件交付只另更新 DV1 的 `STANDARD_SHA256` 單行，不將 pin 更新解讀為 v2 已實作。

建立從發現、旁證、逐筆裁決、版本化更正，到物化與失敗記錄的同一條可重現流程，避免把「來源已保存」「週期相符」「逐筆檔可重建」混稱為資料絕對正確。
適用於 R8 Bybit USDT 線性永續的研究 K 線 O/H/L/C、volume、turnover；資金費、持倉量的可讀範圍、來源與缺漏規則沿用既有契約，本規範不創造其新數值。

本文件已由 Operator 核准，conductor 方法論審查完成；自 PR #240 合入 main 時生效，作為 §9 六個交付的實作規則來源。各交付仍依指定身分、依賴及現行准入／驗收程序執行；本輪只完成核准登錄，由 conductor 審查本輪提交並合併。文件合入不代表工具或更正檔已完成，更不代表 BCH 候選已套用。
本文件與 [P4 補充指令](2026-10-20--r8-stage2-p4-research-core-addendum.md) 的關係如下：

- 保留 §3、§9.0 的 UTC、可知時刻、成交順序、策略可見性；保留 §9.8 的成本／作廢算法、§9.14 缺漏與填補期、§9.15 橫截面完整性閘門、§9.18 五項前檢及 §§12–16 的驗收／精度規則。
- **自本 PR 合入生效後**，§4 第 4 點中 `source/`「原始切片」對被裁決列改為本文件 §8 的有效資料視圖；原字串另存，原 P3b 不動。§9.18 第 2 點「資料錯誤以 U1 修補交付處理」對本規範所涉已凍結 P3b K 線改走更正檔，不覆寫 U1。§9.18 的五項資料品質前檢只用一般市場階段，§6.3 明定上市族與一般族的視圖；交易規則本身不因階段改變。其餘不改。
- §6 已裁決參數、公式與介面不得由實作者、假說程式或命令列另選舊方案；變更須另經裁決／版本化，依規定計入試驗數。舊資料未決後的 A／B 處置不因本次核准預先選定。
- holdout 的自動驗證是將來啟用條件；現行 U4 一律拒絕 holdout，仍受 `P1-R8-S2-LEDGER-FIXES` 的先保留試驗、再釋出、記錄每次物化及單次限制約束。本文件不提前打開 holdout。

## 2. 背景、授權來源與實證

### 2.1 Operator 原文與授權界線

Operator 2026-10-22 在對話中指示（本次 conductor 派工轉引）：

> 「看看是否可以交差比对修复。我们需要确保原始用来学习和训练的资料绝对无误。bybit的错误可以比对binance或者其余交易所，或者你有更好的方案可以按照你的思路完成」

> 「比对多交易所，尽量确保我们最终用于训练和学习的数值准确无误，必要的话我希望你预先设计并完成一套基于我们需求的，关于这类分歧的判断逻辑和后续处理的规范」

上述起草指示保存在 `RH-20261022-02`。同日續派提供以下 Operator 裁決原文，逐字保存於 `RH-20261022-03` 的 `authority_source`，`follows` 指向前一事件：

> 「K线按照你建议的采取交易所定义」

> 「成交额我们先看我们具体需要这个数值多么准确再酌情照原值用并列为限制，疑点日采取小时成交额加总并比对原值。」

> 「上市日需要被记录为讯号，但必须要和其余市场信号做出明确分类上的区分，一定周期内应该被视为特殊。」

> 「验收标准暂时同意。」

成交額精度分析後，對增加觸發條件：

> 「同意添加触发条件」

上市期與其後的因果設計方向：

> 「上市期分三个阶段，初期1-3天中期7-15天。稳定15天到30天后。我认为有必要基于交易量判断时常。有的新币只是昙花一现，有的现象级但是很快冷却。所以我认为时常应该分类对待」

> 「同意方向」

在 RH-20261022-03 記錄時，上述只裁決方向，具體門檻、公式與工程展開尚未逐項批准。conductor 同輪要求成交額不套 G、揭露舊年未決風險、以上市期設計取代原 D3，並補工時與投入上限；這四項是方法論指示，不冒稱 Operator 原文。

本輪 conductor 續派轉錄 Operator 2026-10-22 的四項選項回覆，保存於 `RH-20261022-04`（follows=`RH-20261022-03`）：

> 「中間值 (Recommended)」

對應 X=50%、Y=20%、Z=20%、W=7日；q 採選項 A（每小時平均基礎幣成交量，首日按實有箱數），相對變異採 §6.3 均量相對差公式。

> 「啟動 DV6 (Recommended)」

對應 §6.2 第5點的 U6 決策輸入表介面與 §9 的 DV6，已啟動，不再是條件單元。

> 「每層 300，可擴到 900 (Recommended)」

對應 §4.5 全計畫：種子20261022、每層300、一次擴到900、保守95%上界≤2.5%，連同下載與工時估計。

> 「核准並開始實作 (Recommended)」

對應整份規範核准；依 conductor 本輪指示記錄方法論審查完成，規範與 ACTIVE 派工列自本 PR 合入 main 時生效。此處不代替合併事實或宣稱程式已開始執行；簽核見 §12。

### 2.2 固定實證來源

以下簡稱 I、C、T；所有**市場觀測數字與來源證據雜湊**均引自這三份報告，不作本輪重新取數或獨立資料驗證的聲稱。§4、§6、§9 的設計數值已依本輪裁決固定，估算仍明標為規模情境或由報告數字推算；本文件與 Git 基線的身份不屬市場觀測。

| 簡稱 | 本機來源（倉庫外，未隨本 PR 發布） | 引用內容 |
|---|---|---|
| I | `/Users/ncyu/Projects/TradeBot/audits/2026-10-22-r8-invalid-row-investigation/REPORT.md` | §1 原始零列與來源鏈；§3 全訓練段日／時差異；§7 缺漏與下游影響；§8 範圍例外 |
| C | `/Users/ncyu/Projects/TradeBot/audits/2026-10-22-r8-crosscheck/REPORT.md` | §1–3 取數、方法與 BCH 見證；§4–6 涵蓋與逐欄差異；§8 成交額；§9 規則草案；§10 範圍例外 |
| T | `/Users/ncyu/Projects/TradeBot/audits/2026-10-22-r8-turnover-accuracy/REPORT.md` | 成交額精度／分級與單筆上限敏感度、觸發帶、26日逐筆比較；SHA-256 `a81b7faf36849851c827f40097b69fc765e85d6dc7d4d255364790f8974eae0f`（本輪核對一致） |

- I §3：掃描 1,088 標的，638 個在訓練段有資料、450 個沒有；379,169 日線、9,092,375 小時線，其中 378,425 日有從 00:00 起連續 24 根小時線。OHLC 分歧共 10 標的、26 個標的－日；不是 26 個已證實錯價日。
- C §1、§5：26 個逐筆檔合計 904,227 筆；原 31 個 OHLC 分歧中，26 個與至少一個 K 線來源相符且該邊界無多價，4 個有邊界同戳多價，XEM open 與三種 K 線都不同。相符不等於涵蓋檢查通過。
- C §4：XEM 逐筆早於可得 H/M；PUMPBTC 的 H/M 有逐筆檔未涵蓋的早段。PUMPBTC 日線六欄與該逐筆檔全等，仍不能判完整；LTC 末戳多價也不能用檔案順序挑收盤。
- C §8：22 個較早案例的 485 根小時、28,927 根分鐘 turnover 精確等於各自 close×volume；日線 5/26 精確相等，另 17 日僅有相同模式的浮點尾數診斷。**不外推全部 Bybit 歷史，不稱交易所內部算法已證實。**
- I §8、C §10 已披露超出當輪限定範圍的中繼資料／單筆訓練列輸出；沒有據此分析 holdout。兩輪都沒有獨立 E2/E4 驗收。保留這些限制，不改寫成零偏差或外部完整性認證。

- T：378,531 個可決策標的－日中，全面把日額換成小時加總產生 **4 個分級翻轉（0.001057%）**，均為 10／20 bps 互換；**0 個跨越 100 萬 USDT 不可開倉界線、0 個單筆上限改變**。完整日 D/H 差異只出現在 2020–2021 年；不把這次觀測外推為以後永不跨界。
- T：±5% 觸發帶涵蓋 370,907 個歷史足夠決策日中的 15,470 個（4.170857%），包含全部 4 次翻轉；±2% 只含 3 次。26 個逐筆日中小時加總在 24 日更接近逐筆值；排除 XEM／PUMPBTC 兩個涵蓋衝突日後，24 日的絕對相對誤差 P99=0.429832%（約0.43%）。這是疑點樣本，非全市場誤差保證。
- T：剔除兩個衝突日後的 512 個可比小時，小時成交額對逐筆值誤差 P99=1.938247%、最大2.578852%；日額換成小時和不能消除單筆上限輸入的近似限制。

固定回歸清單：I 的 `daily-hourly-findings-verified.jsonl`，C 開頭引用 SHA-256 `935697488054e1e0765a16656fc5eb857aed2a05a14d828fc5d2a528359b06f8`。
P3b manifest：I §1 的 `b6519a7b2f5eae4759612690790ddb6680db62aa4e723427f51c21a7d6257006`。

## 3. 原則與共同資料契約

本節的機械表示隨整份規範獲核准，實作須遵循 §8.4 的固定資料格式。

1. **原件不可變**：P3b raw bytes、requests、manifest、CSV 永不覆寫；新規則、新證據、新裁決均產生新版本，不在原件刪列、改字串或重新壓縮。
2. **旁證不填值**：Binance／OKX 只作 L4 篩檢與 limitations；不得以外所數值填補、平均、投票或取代 Bybit。D/H/M 無無條件優先級；更多來源一致不等於正確。
3. **未決即缺漏**：任一必要欄位未決，該資料集的該根整列不進有效視圖；其他獨立週期、資金費與 OI 不自動一併刪除。重複鍵下的所有衝突列一同隔離，不任取首列。缺漏按 P4 §3.5、§9.14 處理，無前值 K 線或內插；日線缺漏的成交額依 §9.8.2 在計算分級時作 0，這不是補出零成交額來源列。
4. **只在可讀範圍內**：先判斷資料集、標的、時間戳與授權範圍，再解碼市場欄位；跨範圍原檔可作不透明雜湊，不輸出範圍外值／統計。所需整日不完全可讀時不下載跨界逐筆日檔、不用外部資料補齊，記 `SCOPE_INCOMPLETE`，受影響列未決。資金費終點例外沿用原契約，不擴及 K 線／逐筆。
5. **holdout**：在合法開啟且先保留證偽試驗之後，由工具自動執行相同已凍結版本，不讓研究者選日期、門檻或更正。原值、更正值、逐筆與詳細發現只供受控驗證／物化流程；對人的輸出只含計數與類別，不含價格、數量、成交額、標的－日期明細、可還原值的錯誤訊息。世代間仍禁止交叉讀取；失敗不能重開或以換種子重試選樣。
6. **精確算術**：來源數字由原字串直接轉有限 Decimal／整數縮放，科學記號可解析但不經 binary64；比較數值完全相等，原字串仍保留。價格 tick 差只供診斷，當前 tick 快照不當歷史容差。P4 §16 的現金 ulp 與 §9.8.8 重算容差**不適用**於市場資料比對。
7. **時間與單位**：K 線時間戳是 UTC 毫秒起點，時間箱 `[t,t+Δ)`；逐筆秒時間戳保留十進位小數，以精確乘法對齊箱界，不截去子毫秒。volume 為基礎幣數量，turnover 為 USDT；逐筆 `Σsize`、`Σ(price×size)`，買賣兩方向各筆只計一次。禁止把張數、買賣淨額或派生 foreignNotional 當作精確基準。
8. **品質不作收益選樣**：資料裁決不看策略、PnL、參數、候選輸贏；同一來源／範圍與政策產生同一結果。訓練段與樣本外計分窗重疊的限制沿用 §9.18：驗證結果不可用來優化假說或選標的。

### 3.1 發現清單、更正檔與版本

每次流程輸出 `findings.jsonl`（所有命中／未涵蓋）、`corrections.jsonl`（逐欄裁決，含保留與未決）、`verification.json`（政策、分母、來源與狀態），均以固定鍵序、UTF-8、排序、內容 SHA-256 封存。
規範及政策版本、工具 commit、輸入 manifest、可讀範圍、抽樣計畫、上一版更正檔 SHA、覆核記錄均必填；新版本不可默認成為舊 trial 的新輸入。

每個裁決至少有下列欄位；值皆為原字串或 null，不以缺值偽造 0：

| 欄位組 | 必填內容與拒絕條件 |
|---|---|
| 身份 | `correction_id`、`symbol`、`dataset`、`interval`、`timestamp`、`field`；鍵為標的＋資料集＋週期＋時刻＋欄位；時刻無法解析時以檔案與原列定位，不能猜日期 |
| 原值 | `original_value`、CSV 相對檔名／SHA／解壓行號、raw URL／SHA／request_id／list 索引／byte offset；raw 與 CSV 有轉換差異時兩者都保存 |
| 候選 | `corrected_value`（僅 `CORRECT` 非 null）、`candidate_value`、單位、計算公式、證據數值；`KEEP` 不能偷偷改寫格式或數值 |
| 證據型態 | `evidence_kind` 區分 `trade_adjudication` 與 `reported_turnover_selection`；後者記日／小時原檔 URL、SHA、逐列位置、涵蓋小時鍵、求和與差異，不要求逐筆證據，也不因缺逐筆而判失敗 |
| 逐筆證據（價格／成交量裁決） | 原始逐筆檔 URL、壓縮原檔 SHA-256、原 CSV 行號／trade ID／行 SHA、涵蓋對帳檔 SHA；缺檔時 URL／狀態照錄、SHA=null 且原因必填，不造雜湊 |
| 規則與結果 | `rule_ids`、`decision`=`CORRECT`／`KEEP`／`UNRESOLVED`、`reason_code`、`coverage_status`、`order_status`、`row_action`=`include`／`missing`；整列有未決時後者必為 missing |
| 核准與追溯 | 規範版本／核准記錄、裁決版本、`supersedes`、來源層（raw／CSV）、適用讀取範圍；pending 候選不得套用 |

相同鍵不同有效裁決、原值或原來源雜湊不符、缺證據、循環 supersedes、跨範圍裁決、未核准政策、工具錯誤，一律拒絕發布該物化。裁決順序為先驗證身份，再按證據型態驗 G 或 §6.2 的自報小時網格，逐欄決定後重跑 L1/L2；不能讓後一筆更正蓋掉前一筆失敗。

## 4. 檢查層與統計抽樣

以下精確定義與門檻已隨整份規範核准；執行前須固定政策／計畫身份，不得看結果後調整。

### 4.1 L1：全部列的硬性有效性（DV-L1）

每個可讀 K 線列均須有限可解析，O/H/L/C > 0、`low ≤ min(open,close)`、`max(open,close) ≤ high`、volume ≥ 0、turnover ≥ 0。
時刻為整數且 `t mod Δ = 0`；D 的 Δ=86,400,000、60 的 Δ=3,600,000，疑點用 1 的 Δ=60,000。以 `(symbol,dataset,interval,t)` 檢查唯一、排序及缺漏；完全相同的重複也屬命中，不靜默去重。

每個命中記欄位及原位置；價格、成交量或時間／唯一性命中且時刻可定位者把所在 UTC 日送入 L3，**僅 turnover 非法者走 DV-A 的自報值分支，不因此下載逐筆**；時刻不可定位者記 `INVALID_TIMESTAMP`，隔離並停止該資料集物化，不能移動時間戳或把它當別日。L1 通過僅代表結構有效。

### 4.2 L2：全部日的跨週期一致（DV-L2）

對可讀範圍內日線與小時線所出現日期的聯集逐日檢查，包含只有一方有列的日。 未另註時，L1／L2 及 C3 的待驗 K 線值為 P3b CSV 值；raw 另作來源對照，不能為通過對帳而默換 raw 值或容忍浮點尾差。`FULL` 指日界完整可讀、24 根唯一且 L1 合格的小時線正好從 UTC 00 至 23 時連續、沒有已知開／停市截短時窗；24 根存在本身不證明逐筆齊全。
其餘以可同時存在的狀態旗標記 `PARTIAL`（已知部分交易／資料起訖日）、`GAPPED`（內部缺小時）、`SCOPE_INCOMPLETE`（可讀界線不足）、`MISSING_COUNTERPART` 及 `INVALID_INPUT`（原列 L1 失敗）；不把缺口稱無成交。無合格小時可彙總時記 `NO_VALID_HOURLY`，不產生比較值或 PASS；L1 的價格／量／時間命中仍照送 L3；僅額命中依 DV-A，不另觸發逐筆。

- FULL：`D.O=H首.O`、`D.H=max(H.H)`、`D.L=min(H.L)`、`D.C=H末.C`，逐欄 Decimal 精確相等。
- PARTIAL／GAPPED：`D.L ≤ min(H.L)` 且 `D.H ≥ max(H.H)`，即日線區間須包住所有現有且 L1 合格的小時區間；O/C 與現有小時首末的差異仍記錄並送 L3，但不得直接推斷日線錯。缺一方或範圍不足亦記明未涵蓋。
- 全部日另列 `D.volume−ΣH.volume`，不與 OHLC 合併成一個 PASS；非零量差異送 L3。`D.turnover−ΣH.turnover` 另作 §5／§6 的成交額語義診斷，不單憑額差異標記 L2 或認定錯價；不能把已知 close×volume 的週期差異悄悄變成全市場逐筆取數要求，也不套價格容差。
- 1 分鐘線僅可對已被 L1、L2、L4 標記的疑點日取得；用相同半開箱與六欄算式逐欄記錄。它不是無條件裁決來源，也不因分鐘較細而取代逐筆涵蓋檢查。

### 4.3 L3：標記日的逐筆裁決（DV-L3）

**DV-V2 修訂註記**：本節 C3 原文永久保留為 `v1-strict`；§13.2–13.3 另定 (e) 的來源選擇適用域，原 C3 失敗仍保存，不能改稱嚴格通過。C4 依末尾勘誤一逐欄判定。

候選為 L1（排除僅成交額命中）、L2 價格／成交量、L4 命中日的去重聯集；抽樣日也走相同逐筆驗證器。每個候選必有終態，不能因下載失敗、無逐筆或無外部來源就消失。成交額選擇僅記 `REPORTED_TURNOVER_SELECTION`，既不要求 G，也不單獨觸發逐筆下載。G 只裁決價格與成交量，不能用它否決可獨立驗證的交易所自報成交額選擇。
取得當日 `https://public.bybit.com/trading/<symbol>/<symbol>YYYY-MM-DD.csv.gz`，保存請求 URL／UTC／HTTP、原 bytes、SHA、解壓行號與 ID；不換別名、其他合約或其他日期填補。

**先過涵蓋閘門，才可逐欄採值：**

1. `C1_ID_TIME`：標的與合約一致；每筆在所核對日及可讀範圍，price>0、size>0，時間精確可解析；trade ID 不重複，時鐘方向可確定。重複、矛盾或來源不明均未決，不能直接去重後宣稱完整。
2. `C2_WINDOWS`：以每個小時箱比對逐筆時段與 K 線時段。K 線正 volume 卻無逐筆、逐筆位於 K 線未涵蓋小時、已知開／停市窗不符，均為涵蓋矛盾。首筆可晚於箱起點（BCH 06:51 仍在 06 時箱），不要求交易恰在整點發生，也不把第一筆當首次上市證明。
3. `C3_QUANTITY`：對所有現有小時逐一核對 `K.volume = Σsize`，另報交易筆數、首末時間及整日量；「逐筆數量」是 size 合計，不是交易筆數。任一小時量不相等、缺所需小時或非正價格使時窗不可核實，即 `COVERAGE_CONFLICT`。日線量不符可在小時全部對帳後另裁決；小時量本身衝突時不靠同一逐筆檔自我證明其完整而改量。
4. `C4_ORDER`：保留所有同時間戳的不同價格集合；同戳多價的受影響 K 線記 `TIMESTAMP_MULTI_PRICE`、未決，不把檔案行順序當撮合次序，不以 D/H/M 多數決。整日裁決若包含該歧義也不得放行；無歧義的其他獨立小時可另判。報告只證明部分邊界無多價者，不能升格為本條全檢通過。
5. `C5_REBUILD`：在上述條件全通過的目標時窗，精確重建 `O=最早時刻唯一價`、`H=max(price)`、`L=min(price)`、`C=最晚時刻唯一價`、`V=Σsize`、`A=Σprice×size`，與原 raw、CSV、H、疑點 M 各自比對。無成交箱不製造 OHLC；原零量 K 線的延續語義無充分證據則未決。

「涵蓋通過」表示所有可取得來源未見矛盾且各小時量精確對帳，仍不等於交易所公開檔含全部真實成交的證明。外所相近不解除任何 C1–C5 失敗。

### 4.4 L4：跨交易所合理性篩檢（DV-L4）

範圍為全部當下可讀、可比的完整小時，對 Binance USDT-M 永續及 OKX USDT-SWAP 分別檢查。
同一基礎資產、USDT 報／結算、線性永續、同單位及合約乘數、同 UTC `[t,t+1h)`、均為已收盤交易價格 K 線才可比；不以現貨、指數、標記價、反向合約、改名或千倍別名代替。同名仍須核實這些條件。
首個可觀測小時或下架截短小時無完整時窗證據時排除為 `INCOMPARABLE_PARTIAL`；完整性／合約識別證據缺失記 `INCOMPARABLE`，HTTP 空檔、錯誤或缺時段記 `UNAVAILABLE`，均列覆蓋率與限制，不作相符。

事前價格門檻固定為 **1%**（沿用 C §2 的數值，但本條明確改為完整小時收盤篩檢）：
`abs(C_external − C_Bybit) × 100 > C_Bybit` 時命中，等於不命中。Bybit 基準是未更正的原生小時收盤；非正則 L1 命中、比率 `UNDEFINED`。
任一可比交易所超標即將該日送 L3；另一所相符不得否決。外部量／額只記可用度與單位，不用跨所量相等或來源投票裁決 Bybit；未超標不證明每 tick 正確。

### 4.5 統計抽樣稽核（DV-SAMPLE）

**已核准計畫（Operator 2026-10-22，選項「每層 300，可擴到 900 (Recommended)」）；本輪未抽樣、未下載。** 目的為估計「完整標的－日」依本規範可證實的錯誤及未決比例，不宣稱逐筆、逐列或全市場絕對錯誤率；沒有獨立市場真值時，本上界不能保證未被任何來源揭露的共同錯誤率。

1. 母集合：當次可讀範圍內日界完整、原 CSV 已出現 UTC 00 至23時全部24個應有小時鍵、且無已知開／停市截短時窗的標的－日。這裡只以時間網格判完整，**不以 L1 通過或 L2 FULL 為抽樣資格**；價格／量／額錯誤、重複或額外列、L1/L2/L4 命中仍留在母集合，避免先排錯誤再估錯誤率。不可定位的壞時間戳使母集合無法可靠封存時停止抽樣，不悄悄剔除該資料集。部分／缺漏日另報，不能把本上界推到它們、未收錄標的或未開啟 holdout。訓練段固定 `[2020-01-01,2025-07-01)`；I 的 378,425 日只作候選量級，實際 N 由未來工具依本定義封存。
2. 分層：UTC 年份 × 決策日 00:00 的流動性等級，使用 P4 §9.8.2 的四級（≥1億、≥1千萬且<1億、≥1百萬且<1千萬、不可開倉）。分類只用此前可讀的 12 完整日；歷史不足或無法形成該分級歸「不可開倉」，另記原因。為避免更正後重抽，**抽樣分層只用凍結原 P3b 值**，缺日以既有規則作 0；它不是正式交易的分級結果。訓練段最多 6 年×4級=24 層。
3. 種子 `20261022`；排序規範與演算法釘為 Python 3.12 `random.Random(seed).sample`：層按年份遞增、tier按 §8.4 固定列舉順序排序，各層母集合按 `(symbol,YYYY-MM-DD)` ASCII 排序，以同一 RNG 依序抽出 `min(900,N_h)` 的不放回有序序列，先封存整個序列 SHA，前 `min(300,N_h)` 為基礎樣本。**每層 300、最多 7,200 日**；小層全查。新合法可讀範圍各自使用相同算法與種子，不能因此重開同一 holdout。
4. 每個抽中日取得 Bybit 日逐筆、重建 D 及所有小時的六欄，走 C1–C5 與 §5。抽中但無檔、涵蓋矛盾、同戳多價或未完成者不替換樣本，記未決；下載中止時已凍結的未完成樣本仍在分母並計保守失敗。
5. 逐層記 `N_h,n_h,e_h,u_h,s_h`：e=確認錯誤的日數（任一欄），u=尚未決的日數（與 e 去重；同日已確認錯誤歸 e），s=已選語義可解釋而保留的日數；另列各欄差異與原因。主報告為更正前 e/n 與保守 `(e+u)/n`，不能以更正後一致把已發現錯誤抹成零。
6. 95% 上界使用**分層、不放回抽樣的超幾何反演**：H 為非空層數，α_h=0.05/H；對 x=e（另算 x=e+u），令 `M_h` 為 `[0,N_h]` 內滿足 `Pr[X≤x | X~Hypergeom(N_h,M_h,n_h)] ≥ α_h` 的最大整數，`U_h=M_h/N_h`；全查層直接用 x/N。全體估計 `Σ(N_h/N)(x_h/n_h)`、聯合至少 95% 的上界 `Σ(N_h/N)U_h`。每層另列單獨 95% 上界但不冒稱它們聯合 95%。抽樣隨機性以預登記 PRNG 設計為前提，關聯的行情數值不作 IID ticks 假設。
7. 已核准驗收：保守全體 95% 上界 **≤2.5%**；任何必要層未抽、規則無法執行或結果未封存，不得 PASS。24 大層各 300 且零錯誤／未決時，二項近似的保守設計值 `1−(0.05/24)^(1/300)≈2.037%`，實際必報上式有限母體結果；不是把 7,200 日當單一簡單隨機樣本套「零錯誤法則」。Operator 已核准本計畫、精確參數與估計成本；同意驗收規則不等於已有通過結果（§6 D4）。
8. **擴大規則先寫死**：基礎樣本任一 e>0 或 u>0，該層延伸至已凍結序列的 `min(900,N_h)`，最多合計 21,600 日，只擴一次；同一根因的一切已知命中按 L1–L3 處理。擴樣仍有新錯誤／未決即停止該層驗收、交 conductor／Operator，不無限下載或改門檻。擴大樣本為診斷，不用結果依賴的擴樣分母取代基礎樣本的主信心上界；更正後再驗作回歸，不能降低原錯誤率。未通過須另定新版本計畫，保留本次失敗。

### 4.6 下載量與執行預算估計

C §1 的 26 個壓縮逐筆檔共 **36,944,407 bytes**，均值約 **1.421 MB／標的－日**。以此推算（十進位 GB）：

| 階段 | 最大抽樣日檔數 | 依已知均值的壓縮 payload 估計 | 3 倍容量情境（估計，非上界） |
|---|---:|---:|---:|
| 基礎樣本 | 7,200 | 約 10.23 GB | 約 30.69 GB |
| 全部層擴大後的總量（含基礎） | 21,600 | 約 30.69 GB | 約 92.08 GB |

這 26 日不是隨機大小樣本，偏舊且僅 10 標的；估計可能嚴重低估繁忙年份／大標的。只估逐筆壓縮檔，不含解壓暫存、L1/L2/L4 所有候選、疑點分鐘線或全市場外部小時線。已有雜湊相同日檔可重用，重疊不可重複計量。
未來取數單元須在已核准清單上先以 HEAD／既有 Content-Length 作精確總量預檢，記無長度者，另報其他來源請求數、預估 bytes、儲存及時間；任何未知長度或超過當次派工限額者停在預檢，不以本粗估當無限取數授權。本次沒有 HEAD／GET 市場資料請求。

## 5. 逐欄裁決規則表

**DV-V2 修訂註記**：DV-V 列及 G 的 v1 原文保留；v2 只在 §13.2 的完整適用域依 §13.3 採完整逐筆 V/H/L/C，O 沿 v1／D1、A 沿 DV-A。域外失敗維持 v1 未決，沒有 (b) 或 (b)+D1 後備。

本表的機械展開已隨整份規範核准；D1／D2 的已裁決方向保持不變。先決條件 G = 目標時窗 C1–C5 全通過、所有來源身份／單位可核對、沒有同戳多價／涵蓋矛盾。**G 只適用 O/H/L/C 與 volume 的逐筆裁決，不適用 DV-A 成交額選擇。** 價格／量未決仍使整列 missing；DV-A 不得以成功選額掩蓋它。表中 T 是合格 Bybit 逐筆重建值，不是外所值。

| 規則／欄位 | 證據組合 | 裁決與採值 | 保留／未決界線 |
|---|---|---|---|
| DV-O／open | G；原 O 非正或不在原 L/H 內，T.O 唯一且至少一種 Bybit 原生細週期 O 同值 | `CORRECT=T.O`，更正後整列須過 L1 | G 失敗、無唯一價、原生來源無支持或更正後 L1 仍失敗：未決；BCH 僅為此分支候選 |
| DV-O-SEM／有效 open | 原 O 通過 L1；與首筆成交不同本身不構成修正理由 | **已裁決 D1-A：KEEP** 原 K 線 open，reason=`EXCHANGE_OPEN_SEMANTICS`；不換當根第一筆 | L3 若另有涵蓋／價格／量未決仍隔離整列；G 通過時可把純 open 差異歸語義。L2 原差異永久保留，不偽裝數值相等 |
| DV-H／high | G；max(price) 唯一數值；原 H 與 T.H 比較 | 原 H=T.H：`KEEP`；不同：`CORRECT=T.H` | 不以較細 K 線投票；保留 open 後導致 H<O/C 則整列未決，不能憑空把 H 夾到 O |
| DV-L／low | G；min(price) 唯一數值；原 L 與 T.L 比較 | 原 L=T.L：`KEEP`；不同：`CORRECT=T.L` | 同上；尤其零 L 有實證也須 G 與全列 L1，不能只見正數就套用 |
| DV-C／close | G；最大時間戳價格唯一 | 原 C=T.C：`KEEP`；不同：`CORRECT=T.C` | 有同戳多價即未決，即使原 C 是可能價集合的一員也不能判唯一正確 |
| DV-V／volume | G；日線量可與每小時已對帳的 Σsize 再比 | 原 V=T.V：`KEEP`；日線不同：`CORRECT=Σsize` | 小時量與逐筆不符使 G 失敗，保持未決；不能用日線相等反證小時缺量不存在 |
| DV-A／turnover | **不套 G、不要求逐筆**；依 §6.2 驗原額與完整自報小時鍵／非負有限額 | **已裁決 A＋限定 B**：一般日 `KEEP=exchange_reported`；疑點日用 `sum_hourly_reported`，原值不同則 `CORRECT`；門檻觸發日雙算，分級不同以小時加總為準並記錄 | 小時額不改。必要小時缺漏／重複或額非法且無有效替代時，日額未決；部分上市日只加實有完整小時箱、標 PARTIAL，不拼24小時、不進12完整日窗口。`trade_sum` 僅診斷，未獲採用 |
| DV-KEEP／相符或純旁證命中 | G；所選語義下全部相符，或 L4 超標但 Bybit 證據一致 | `KEEP` 原值，記已檢查來源與原 L4 命中 | 外部相符本身不構成 G；未決不可改成 KEEP 以通過 L1 |

量／額的 raw 與 CSV 浮點轉換差異另列 `SOURCE_REPRESENTATION_DIFFERENCE`；它不自動證明任一來源較正確，只有依本表具名裁決才改有效值。H/M 等新取來源也逐列 L1，不能把新的壞列當支持票。
全列重跑後，L2 仍不同者必須逐差異有 KEEP 語義裁決或未決／缺漏，不能以更正檔存在即 PASS；證據支援有限欄位時不宣稱整根修好。

## 6. 已裁決事項、上市期條文與舊資料後續處置

### 6.1 已裁決方向與原選項背景

下列方向及 §6.4 的剩餘參數已由 Operator 裁決；§4 抽樣／門檻、§5 未決分支及 §8 介面隨整份規範核准。原選項留作背景，實作不得自行重選。

| ID／事項 | 已裁決 | 原選項背景與未採用部分 |
|---|---|---|
| D1／open | **選 A：保留交易所 K 線 open 語義**（可能延續前一根收盤），不以當根第一筆取代；只有原 O 違反 L1 時依 G／DV-O 證據更正 | 原 A 如左；原 B 為全部改第一筆成交，會改成交／訊號並需更廣逐筆證據。B 未採用；保留語義不等於已證明交易所歷史內部算法 |
| D2／成交額 | **A 為一般日，B 限疑點日及門檻觸發雙算**；近似列限制，疑點日用小時加總與原值比對。增加觸發條件方向已同意，精確 ±5% 算法見 §6.2 | 原 A 全部保留原值；B 全部日額換小時和；C 疑點日／小時改逐筆 Σprice×size。Operator 採 A＋限定 B，未採全面 B 或 C。舊草案套 G／要求逐筆的限制由 conductor 明示撤除；單筆上限仍用原小時額 |
| D3／部分交易日 | **由 §6.3 的三階段上市期設計取代**：觀測上市首日的部分日屬上市初期訊號，與一般市場分類分離；其餘因資料起訖／缺漏而部分的日，日頻訊號依缺漏規則處理 | 原 A 排除部分日日頻訊號、B 保留並預登記。Operator 選分類處理，並非無條件 A 或 B；本輪已固定 X=50%、Y=20%、Z=20%、W=7日及選項 A 的量定義，不把資料起點當已證明真實上市 |
| D4／可達驗收 | **已核准 A（沿用暫行驗收標準）：L1–L3 全覆蓋＋預登記抽樣錯誤率的95%上界**；L1 全列、L2 全日、L3 全價格／量候選有裁決或未決終態（僅額選擇依 DV-A）。明認無法對全部列逐筆證明 | 原 A 含每層300／最多900、保守上界≤2.5%的提議；B 另定更嚴上界／樣本；C 全列逐筆證明（現階段不可達）。本輪已核准具體抽樣參數與估計成本，仍不等於抽樣已通過，不能事後放寬 |

### 6.2 成交額：自報值選擇與雙算（DV-A）

1. 一般日保留有效非負有限原值 `exchange_reported`，揭露 2020–2021 年近似及 T 的4個分級翻轉；疑點日為 L1／L2／L3／L4 標記日的聯集（含抽樣新發現），日額改為當日小時 turnover 加總 `sum_hourly_reported`，保存原值、差值、相對差（原值0則未定義）、小時鍵與來源 SHA。只選交易所自報彙總，**不過 G、不因此下載逐筆**；同日原有價格／量疑點仍照 L3 執行。
2. **小時網格條件（已隨規範核准）**：完整 UTC 日須24個唯一對齊小時，每個 turnover 有限且≥0；不因小時量與逐筆不合而否定這個自報額加總。價格／量未決仍依 §3.3 隔離所涉列，不能靠額選擇救回整列。觀測上市首日只可加上市首箱至23時的全部已閉合箱，標記 `PARTIAL`、記箱數，不外推24小時且不列為流動性完整日；其餘不完整日走缺漏，不把殘缺和冒稱完整日額。缺必要小時、重複、非法額則 `TURNOVER_INPUT_INCOMPLETE`／未決，依既有缺日為0的計算規則處理。
3. **觸發規則（已隨規範核准）**：在決策 t，只取 P4 §9.8.2 的此前12個完整曆日；不足12日仍不可開倉，缺日仍依既有規則為0。令 `M_D` 為原生日額中位數（12筆排序後第6、7平均，供對照），`M_E` 為疑點日選額後、實際供分級的同一窗口中位數；M_E 對任一 `T∈{1,000,000;10,000,000;100,000,000} USDT` 滿足 `abs(M_E−T)/T ≤ 0.05`（含邊界）即雙算。觸發以實際供分級的 M_E 為準，另保留 M_D 作原值比較；不能先看雙算結果再選觸發基準。
4. 雙算須在同一12日窗口另求每個完整日的小時和，再求 `M_H`；原／有效日額與小時和的值、分級、已選來源逐項記錄。與 M_E 的分級不同時，以 M_H 對應的流動性級為準；若原 M_D 與 M_H 不同也必記錄。級別相同時保留疑點日替換後的既有選額。**±5% 是觸發雙算範圍，不是允許5%誤差**；沒有資料支持未來不會在帶外翻級。
5. **決策輸入介面（已核准；DV6 已啟動）**：疑點日的固定日額選擇由更正檔表達；觸發雙算則由 U4 另產生 `verification/turnover_decisions.jsonl`，以 `(symbol,decision_utc_day,policy_sha256)` 為鍵，逐日保存12個輸入日／來源、M_D／M_E／M_H、各級別、選用級別／中位數及原因、known_at／不完整狀態，SHA 寫入 manifest。這是決策輸入，不把它偽裝成某一日 K 線的靜態更正，也不因後來觸發追溯改寫先前日額。必要小時缺漏時不使用殘缺和；該輸入日按既有缺日為0處理並保留原因，不回退為未檢查原值。U5/U6 須對同一表及來源獨立核對規則；現行 U6 只由 `source/` 日額算中位數、不讀此表，因此依 Operator「啟動 DV6 (Recommended)」，由 §9 的 DV6 交付實作此對稱介面，格式固定於 §8.4。上市階段只改可見性仍不需 U6 改動；不能把兩個原因混為一談。不得自行取消 DV6、改用追溯日額回寫或全面改日額取代已核准的限定雙算。
6. 單筆上限始終取個別小時線的原 turnover；不因日額換和而改變。小時 close×volume 近似仍列 limitation，不能由日和較接近逐筆推論每小時精確。DV1／DV2 記選額與差異；DV4 驗4個已知翻轉、0跨不可開倉界線與0單筆上限變更的原分析案例，不把歷史觀測當未來保證。

### 6.3 上市期：三階段、成交量自適應與因果分類

**Operator 已核准方向、精確表示、公式與介面；X=50%、Y=20%、Z=20%、W=7日，q 採選項 A。** 樣本量推算仍是估計，不升格為已觀測。 本分類不是「上市後走勢能預測報酬」的先驗結論；該問題只可作上市族研究假說。

**觀測起點與時鐘。** `observed_listing_at` 為 P3b 中該標的第一根 volume>0 的小時箱起點，只在該箱收盤後可知；一併保存 instruments 的 `launchTime` 及來源身份，兩者絕對差>86,400,000毫秒標 `LISTING_TIME_MISMATCH`。conductor 提供的例子為 BCHUSDT／LINK／LTC／XTZ 的 launchTime=2018-01-01；本輪不另讀市場檔核實。觀測起點可能只是保存起點，不能改寫 launchTime，也不據其較早值虛構上市前資料。若真正首根位於不可讀範圍，記 `LISTING_ORIGIN_UNKNOWN`，不跨範圍尋找；未能以已合法保存的前綴狀態還原者阻擋階段發布。

以觀測首箱所屬 UTC 日期為第1日，後續依 UTC 曆日遞增；初日可部分。每日收盤後用當時可知前綴計算下一日階段；當日 bar 保留當日階段，不以收盤結果倒改。小時線只在該小時結束時可知，日線只在該日結束時可知；一個日界至多前進一階、永不回退。本節 `q[a:b]` 明定為含兩端日期的數列（不是 Python 排除右端的 slice）。對時間 t 的視圖只揭露現在與過去階段，**不得提供未來轉換時刻、終局冷卻分類或完整時間軸**。

| 階段 | 允許結束日（自觀測首日計） | 在範圍內提前結束的條件；未滿足則至上限強制結束 |
|---|---|---|
| 初期 `initial` | 第1–3日 | `q_d / max(q_1,…,q_d) ≤ X/100`；分母為當時已知峰值。有效 q 不足／峰值0時不提前，至第3日結束 |
| 中期 `middle` | 第7–15日 | 最近3日與7日 q 的相對變異收斂：`abs(mean(q[d−2:d])−mean(q[d−6:d])) / mean(q[d−6:d]) ≤ Y/100`；須7個連續有效日，分母>0。已選此均量相對差，不把它冒稱標準差／CV |
| 穩定過渡 `stabilizing` | 第15–30日 | `abs(median(q[d−6:d])−median(q[d−13:d])) / median(q[d−13:d]) ≤ Z/100`，須14個連續有效日、分母>0，且滿既有12完整日歷史要求 |
| 一般市場 `ordinary` | 穩定過渡結束後 | 非新的可開倉保證；原流動性、缺漏、暖機與交易閘門全部保留 |

**量與部分日（已選 A）。** q 為單一標的的「每個觀測小時箱平均基礎幣成交量」：`q_d=Σvolume_hour/m_d`。完整日 m=24；觀測上市首日 m 為首箱至23時應有箱數，全部箱須存在，零量箱也計分母，不以只計正量箱抬高平均、不外推補24箱。首箱可能在箱內才上市，這種整箱平均偏差單列 limitation。之後缺任一應有小時／量未決則該日 q 未定義，不刪去缺口縮短回看；只時鐘前進、不得以缺資料作「已冷卻」。日線／小時自報量差照 L3 處理，不因階段需求放寬 C3。

**上限與歷史閘門。** 既有12完整日要求沿用 §9.8.2：自原首根小時線起經過12個完整曆日，缺日成交額仍按0計，不能改成「必須12個無缺漏觀測日」。因此已知起點的第30日強制結束與該歷史要求沒有衝突；階段標為一般仍不保證流動性／暖機／有效資料合格。起點不可知時依前述拒絕發布，不用推測階段通過交易閘門。

**冷卻／淡出。** 與階段正交的因果旗標：最近 W 個連續完整 UTC 日的有效日成交額各自嚴格<1,000,000 USDT，才標 `cooling=true`；額依 §6.2 的疑點日選額（冷卻不是新的流動性分級），不把部分首日或缺日當低量。任一≥門檻時當時清除旗標；窗口資料缺失則 `cooling=unknown`，不把未知歸為持續活躍。此旗標可隨已知資料改變，三個階段仍只前進。`cooling=false` 僅表示當下未滿冷卻條件，不保證未來持續。

**假說族別及品質前檢。** 所有三階段產生的訊號屬「上市期訊號」，只能供預登記為上市族的假說；一般族在 score、fit、on_decision 三個入口都由框架自動遮蔽所有上市階段的日／小時 K 線及其量／額衍生視圖，不能在第31日回看時重新取得曾被遮蔽的上市歷史。目前階段可見，未來轉換時刻不可見；不把更正旗標或未來分類當特徵。§9.18 的五項資料品質檢定只用一般市場階段；§4 的 L1–L4 與抽樣品質稽核仍覆蓋全部可讀階段，不能以此排除難驗的上市資料。上市族也服從原12日流動性歷史規則，初期訊號可供研究，不表示前12日已獲交易准入。

**預登記與試驗數。** X、Y、Z、W、量的定義、相對變異公式、階段時鐘及族別在預登記時寫死，不得依報酬或分類結果調整；每次調整算一個試驗，納入多重檢驗與 DSR 的 K，失敗或中止也不得抹去。U4 所用政策版本須與預登記一致，改版產生新 manifest／試驗身份。

**樣本數估計與未知。** I／T 只有638個訓練有資料標的，沒有經核實的上市事件清單；故本設計至多638個「觀測起點事件」，真實訓練段上市事件數／各階段可用量均 **UNVERIFIED**，不能把378,531個決策日當獨立上市樣本。若638事件全有三階段，且僅分冷卻／非冷卻兩類，平衡情境每階段每格約319事件；實際各格可為0–638，未知另列，同一事件跨階段非獨立。再細分6年×4流動性級×2狀態時，每階段48格，平均最多約13.3事件／格，屬上限量級推算而非觀測。第一代建議先只分上市族／一般族，上市族以三階段為描述、不再把冷卻交叉切成大量獨立假說；DV2／DV4 在既有可讀範圍內交付事件去重、各格 n、缺失與每假說樣本不足標記，未達技能硬門檻則停止該假說。

### 6.4 已裁決參數、介面與抽樣計畫

**DV-V2 修訂註記**：下表舊資料處置列是先前狀態；Operator 2026-10-22 已選「B」及「(e) 逐筆為準 (Recommended)」，由 §13.1、RH-20261022-05 續錄，不再是 A／B 尚未選定。§4.5 原文不變；另待凍結結果後裁決的驗收估計目標見 §13.6。

Operator 2026-10-22 的四項選項回覆與含義見 §2.1；以下已固定，原選項保留作背景。最後一列的舊年處置仍須等待實際凍結稽核結果。

| 項目 | 原選項背景 | 已裁決／後續處置 |
|---|---|---|
| X：初期峰值比 | 25%／50%／75% | **50%**，選「中間值 (Recommended)」；不是以資料結果最佳化 |
| Y：3／7日相對變異 | 10%／20%／30%；另議 CV | **20%**，採 §6.3 均量相對差公式，不採 CV |
| Z：7／14日中位數差 | 10%／20%／30% | **20%**，保留14日有效量與既有12完整日歷史條件 |
| W：冷卻期間 | 3／7／14完整日 | **7個連續完整日**；不足／缺漏記 unknown |
| q 的量與頻率 | A 小時基礎幣 volume 日均；B 小時 USDT turnover 日均；C 只用完整日 volume 總量 | **A**：每小時平均基礎幣成交量，首日按實有應有箱數；冷卻另用日 USDT 額，公式見 §6.3 |
| 成交額觸發雙算介面 | 原 DV6 為需確認的條件單元 | **「啟動 DV6 (Recommended)」**；保留 ±5% 觸發、M_E／M_D 對照及逐決策日輸入表，U6 獨立讀取與重算，不全面改日額 |
| 抽樣計畫及估計成本 | 每層300／最多900或另定強度 | **「每層 300，可擴到 900 (Recommended)」**：核准 §4.5 全計畫、種子20261022、一次擴大、保守95%上界≤2.5%，連同下載與工時估計；估計不延長15工作日總上限 |
| 整份規範 | 核准或繼續修訂 | **「核准並開始實作 (Recommended)」**；自 PR #240 合入 main 時生效，依 §9 身分派工 |
| 舊資料未決時的處置 | A 若實際大量未決，2020–2021整年不納研究並揭露限制；B 另定成交量語義後重驗；C 維持逐列隔離、上界不過停止研究准入 | **目前維持 C，不預放寬；看到凍結稽核結果後由 Operator 決定 A 或 B**。本輪沒有預先選定 A／B，不能事後改容差後稱原標準通過 |

舊年風險的可據範圍：C §6 的 BCH 2021-02-18 小時量總和較逐筆 Σsize **−0.68 BCH**，已足以證明至少一小時不可能逐位相等；相近差異在多個2020–2021疑點日出現。T 的完整日分母為2020年511日、2021年8,694日，共 **9,205個標的－日（約佔378,373完整日的2.43%）**，是可能受影響的年份範圍，**不是已證實9,205日全錯或全未決**。嚴格 C3 可能使早年層大量 `COVERAGE_CONFLICT`，抽樣擴大／停止，保守95%上界可能無法≤2.5%，大量列將依規則視缺漏；加權上界是否不過仍須實測，不能把2.43%當抽樣錯誤率。不能在本規範預先放寬 C3。

## 7. 第一筆更正候選：BCHUSDT 2020-12-14

**第一筆候選，未套用；本規範已核准，合入生效且工具完成後由驗證工具依涵蓋／同戳檢查產生更正檔，不手動改資料。** 報告目前足以支持兩個候選價格，不足以把 §4.3 全部新條件標成通過。

| 項目 | 原件／證據（I §1、C §3） |
|---|---|
| 原列 | `raw/3352.json:1`，`result.list[116]`（第117筆）、request 第3頁；byte `[9794,9863)`；CSV `kline_BCHUSDT_D.csv.gz` 解壓第2行；t=`1607904000000` |
| 原字串 | `["1607904000000","0","280.35","0","276.95","10905.15","3020181.2925"]` |
| raw 頁 SHA-256 | `5df3591553de9b5929a7ff10294727d15aa7708adc9b4e8eaab915fa68777b7d` |
| 原 CSV.gz SHA-256 | `a1e9e370499251f3abb5f03ddd8bab2d132f6d55effe9f57e8a76d4655e86183` |
| 原列 69 bytes SHA-256 | `735dbfcfe041c6c8e007d1339e9434f57d0cf2818b7738bc0c4c28ec1b48734b` |
| 逐筆檔 | [Bybit BCHUSDT2020-12-14.csv.gz](https://public.bybit.com/trading/BCHUSDT/BCHUSDT2020-12-14.csv.gz)，551,946 bytes；SHA-256 `39ff0c85cff7200ac0922fcf8ea0a5d13c2123b0e89483c7aff31de40cc72db6` |
| open 候選 | **0 → 272.95**；首筆 `2020-12-14T06:51:59.7121Z`，原 CSV 第13046行；trade ID `c0ce0ea6-9905-5824-a146-22ab98373396`；行 SHA `dc5189bf6e4f82a62ed88e1d5e482c0192e70ab76c5d74aaa5dab4de025ffa1a` |
| low 候選 | **0 → 265.15**；最低價見證 `2020-12-14T17:04:56.2563Z`，原 CSV 第5338行；trade ID `cd0b2607-ce1d-575b-a3e7-1c32c24e0646`；行 SHA `c7334725b042c429500cf1786a2c359f2f15e9413dc080774d2997e0ac4fdfa1` |
| 同所支持 | 日逐筆 13,045 筆，O/H/L/C=272.95／280.35／265.15／276.95，V=10905.15；H/M 的 O/L 與候選一致；18 個小時箱，非完整 UTC 日 |
| 成交額另案 | 原 D=3020181.2925、H 合計=2954180.78、M 合計=2955069.0385、逐筆=2955170.064；四者不同；依已裁決 D2 作自報小時加總，18箱標部分日，不進12完整日窗口、不改小時額；若價格／量仍未決，整列仍缺漏 |

第一筆交易晚於 06:00 箱起點，不等於首次上市；不把 instruments-info 的 2018 時間覆蓋為此日。只有 DV-O、DV-L 的裁決及全列檢查成立後才輸出有效列；否則保留候選並將該日線視為缺漏。其他日／時／量／額不因本候選自動獲准。

## 8. U4 物化、U5 資料視圖、U6 消費與失敗記錄

本節為已核准的實作契約；新介面仍須 DV1–DV6 實作與驗收，核准不等於現行程式已支援。

### 8.1 現行來源查核與 U6 不改的條件

以表頭 main 基線讀原碼確認：

| 現行來源 | 已確認行為 | 對設計的約束 |
|---|---|---|
| `program_code/research/r8_engine/series.py`：`Materialization.__init__`（277–361） | manifest 用 `exact_keys`；只解析 `source/` 的 K 線／funding／OI CSV，K 線只收 60／D；驗切片 SHA、列數、時間、L1；讀 `symbol_properties_overlay.csv` | **不能新增 manifest 頂層鍵而聲稱 U6 自動相容**；有效 K 線須在同名 source 檔，不可只修 lean/custom |
| 同檔 `liquidity`（403–414） | 日分級取 source 日線 `turnover`；單筆上限取 source 小時 `turnover` | 疑點日的日額須同步進 U5／U6；小時額保留。決策日觸發雙算的12日輸入由已啟動 DV5／DV6 讀同一 DV2 表，兩側獨立核對，不能只改 custom |
| 同檔 `rematerialize`、`_verify_identity`、`submit`（1460–1545） | `--u1` 只傳 U4 子程序，U6 不開原 U1；重新物化須與帳本 manifest SHA 及完整 `files` SHA 表相等 | U4 重跑須自動解析同一釘住的更正版本；不能需要 U6 尚未傳入的新 CLI 選項或依賴可變 latest |
| `materialize.py`：`materialize`（238–325） | 同一來源列產生 source、lean、custom，`files` 記輸出與來源 SHA；原子發布 | 在此處統一疊加裁決／缺漏；不要讓三種視圖各用不同更正邏輯 |
| `lean_runner.py`：`read_materialization`（178–197） | 核對 manifest SHA、lean/custom 檔案集合及雜湊、overlay；正式身份比對 files 表 | 證據檔放其他前綴，不掛為策略資料；U5/U6 一致不等於市場真值 |
| `lean_algo/framework.py`：`_load_custom`、`_visible`；`lean_algo/rules.py`：`KnownRows`／`data_view`／`fit_fold`／`decide` | 目前載入日／小時及量額資料，依 known_at 截前綴；沒有上市階段／族別遮蔽 | **U5 必須改視圖**，涵蓋 score／fit／on_decision；目前階段依 known_at 截取。不能只在決策入口遮蔽而讓 fit 洩漏 |

**結論分開記錄：上市階段若只改假說資料可見性，U6 不需改；U5 視圖必須改。** 保留完整有效 source 給市場成交／成本重算，上市族遮蔽不刪市場 source，不改訂單集合、成本／成交或可交易規則；假說仍回傳既有完整標的目標結構。若日後讓階段影響交易規則，U6 必須獨立實作同一算法，並以 U5／U6 **對方真實實作**交叉測試，不能用假替身或共用被驗函式冒充獨立重算。
一般更正疊加與固定疑點日選額可沿用現有 U6；**門檻雙算已啟動 DV6，新增 U6 對 U4 決策輸入的受控讀取**（§6.2.5／§8.4），不得籠統宣稱所有成交額新規則 U6 一概免改。若須新鍵、CLI、消費語義或交易規則，先交 conductor 調整派工與相互獨立檔案範圍；本 PR 不改任何程式。

### 8.2 相容的疊加方案

1. U4 用 P3b 固定 SHA＋已合入 `code_commit` 的政策／更正集索引選唯一核准版本；禁止 caller 自選其他值或 `latest`。核准 bundle 放 `--u1` 父目錄的 `verification-bundles/<bundle_sha256>/`，位於原 P3b 目錄之外；相對位置只是定位，信任以程式釘住的 digest 為準。重新物化不需要 U6 新參數；找不到或 hash 不符拒絕，不退回未驗資料。 此靜態索引方案只適用已合法可讀、可先驗證的範圍。holdout 不得預先產出更正集或假裝已知其 digest：未來須先承諾政策／工具／原來源身份，合法開啟後由同一固定流程自動產生唯一 bundle，再把結果 manifest SHA 綁定已保留的試驗並記帳，不讓人挑更正值。這種延後綁定須由 LEDGER-FIXES 及其 holdout 啟用派工另驗；尚未完成就保持拒絕。本節免改 U6 的結論不替尚未啟用的 holdout 介面背書。
2. bundle 索引只綁版本與分片位置／digest，不含範圍外市場值或統計；U4 只解碼可讀範圍的裁決。先驗原值／原列定位再套用，按有效視圖產生同名 `source/kline_<symbol>_{D,60}.csv`、lean 與 custom；保留現有標頭與未改欄位原字串，改值以一般十進位字串寫出。
3. 原 P3b 永不改；另把本視窗原字串切片存 `verification/original/<原檔名去掉.gz>`。裁決、品質結果與政策的可讀切片存 `verification/corrections.jsonl`、`verification/verification.json`、`verification/policy.json`；均加入既有 manifest `files`，用現有 `sha256,rows,first,last,source_file,source_sha256` 形狀。更正檔本身 SHA 必須實際寫入 files，limitations 摘要不可代替雜湊。
4. 保留 `r8_materialization_v1` 的頂層鍵；更正版本、規範 SHA、原值與有效值關係放上述 evidence 檔，`limitations` 列未決、語義、外所覆蓋不足與近似。`source_file/source_sha256` 仍明指 P3b 的原檔身份，verification 證據另解釋衍生關係，不能把有效列冒稱原位元組。
5. missing 列自 source、lean、相關 custom 一致移除，和原 gaps 取聯集、合併重疊且不雙計 count；沿用資料集鍵 `kline_hour/kline_day/open_interest/funding`。保留可讀範圍內原 `first_bar` 以區分上市前與資料隔離，不因首列被移除而把整個後續歷史變成未知上市；策略的實際可見性仍須有合格已收盤小時列。資金費與 OI 不被無關日線裁決移除。
6. U4 依政策逐日產生 `verification/listing_regimes.jsonl`（標的、觀測起點／launchTime身份、known_at、當時階段、觸發原因、q輸入範圍／缺失、冷卻旗標），另輸出同一時間軸的框架必要投影 `custom/listing_regime/<symbol.lower()>.csv`（固定格式見 §8.4）；兩者 SHA 寫入既有 `files`，不增 manifest 頂層鍵。U5 應逐 t 截前綴，原始完整時間軸只在框架內；假說取得的是目前／過去階段及依族別已遮蔽的資料。預登記族別／政策 digest 在 U4 核對 hypothesis_id 的既有預登記記錄後寫入 §8.4 的 `verification/hypothesis_binding.json`，不能由假說任選族別；缺綁定拒絕發布。現有精確 schema 若容不下必要綁定，先停並另派介面，不能把身份偷偷塞入策略可改參數。
7. 本 bundle 是框架的資料品質依據，不是策略特徵；不交出更正旗標、原值、外所值、來源清單或未來日的品質摘要。假說只看 §3.8 已可知且依 §6.3 族別過濾的有效資料與當時階段。現有 Python 同程序與靜態檢查不是完整隔離，保留殘餘風險，不宣稱程式絕無繞過可能。
8. 同一版本／範圍須逐位元組重現，含 gzip、JSON、排序；更正版產生新的 manifest 及 trial 身份，不能覆蓋已開始／已提交試驗的輸入。舊 P4-D0／P4-D 物化與 run 只作歷史回歸，不能因舊檔未帶新證據而重寫歷史。

### 8.3 更正失敗與帳本可表達的邊界

- 在 begin_trial 之前發現不可發布物化：`verification.json` 記 `BLOCKED`、層／規則／理由與來源，保留發現／候選更正檔，不產生可用物化、假 run 或假成功 trial。
- 未決可依已核准規則轉缺漏後產生物化：缺漏與 limitations 隨 manifest hash 進 trial 身份；執行、`filled_periods`、成本與作廢照既有算法，不填假行情列。日線缺漏並不必然等於一次無決策；小時可見性仍獨立判定。
- 已 begin_trial 後重新物化不符、驗證失敗或證據缺失：submit 拒絕；保留該 trial 與失敗證據，停止世代結算交 conductor，不裸用 finish_trial、刪掉 trial 或把它自動改為不計 K 的成功。帳本沒有新的 `data_quality` failure reason 時，不捏造已接受的狀態。
- 現有帳本的 `result_summary/provenance`、manifest 身份與已知失敗途徑可引用上述證據；**它不自行驗證更正檔、filled_periods 或新增前置失敗語義**。計分開始後失敗、作廢／V/PBO 及 holdout 保留試驗缺口仍由 `LEDGER-FIXES` 管理。本規範不能把尚缺的帳本執法聲稱為已完成。

### 8.4 跨單元資料格式與回傳形狀（固定契約）

以下新增介面由本規範寫死，實作者不得各自發明欄位、排序、包裝層或成功回傳值；缺欄、未知欄、重複鍵、錯誤型別／版本均拒絕並保留原因。既有 P4 `run_config`、`run.json`、帳本 `trial_record` 與 manifest 介面仍以補充指令 §§4、7 及其真實實作為準，不新增不相容包裝。

**共同型別與編碼。** 新 JSON／JSONL 使用 UTF-8、無 BOM，物件鍵字典序、分隔符 `,`／`:` 無額外空白、禁 NaN／Infinity，每物件後一個 LF；JSONL 每行一個完整物件。既有 `materialization.json` 繼續使用現行 canonical 編碼。市場量值為來源字串或一般十進位字串，時間為 UTC 毫秒整數，未知為 null，不拿空字串／0冒充未知。來源價格／量／額計算精確；q 的均量與相對差用整數縮放／有理數交叉相乘比較，不因重複小數捨入跨門檻。SHA-256 為64位小寫十六進位字串。路徑為安全相對路徑、禁止 symlink／`..`／絕對路徑；證據不跨可讀範圍。

共同 `SourceRef` 物件的鍵固定為 `{kind,relative_path,url,sha256,row,request_id,list_index,byte_start,byte_end,trade_id,line_sha256}`。kind 為 `raw|csv|trade|instruments|policy|plan|report`；row 為原解壓檔含標頭的1起算行號，list_index／byte_start／byte_end為0起算（byte_end不含），request_id／trade_id為字串；不適用欄位 null，不可省略。已取得原件的 relative_path、sha256 必填，未取得者兩者 null 且上層 reason_code 必填；url 保存實際來源，離線產物可 null。source_refs 依 `(kind,relative_path或空字串,row或−1,list_index或−1,byte_start或−1)` 排序，不藉排序捏造逐筆撮合次序。

| 產物／生產者→消費者 | 固定鍵／形狀、排序與狀態 |
|---|---|
| `policy.json`／規範固定、DV2封裝→各單元 | `{schema_version,standard_sha256,approval_event,p3b_manifest_sha256,listing,sampling,turnover,l4_price_threshold_pct}`；schema=`r8_data_verification_policy_v1`、approval_event=`RH-20261022-04`。listing=`{x_pct:"50",y_pct:"20",z_pct:"20",cooling_days:7,quantity:"hourly_base_volume_daily_mean",variation:"mean_relative_difference",stage_end_ranges:[[1,3],[7,15],[15,30]]}`；sampling=`{seed:20261022,base_per_stratum:300,max_per_stratum:900,max_expansions:1,confidence:"0.95",upper_limit:"0.025"}`；turnover=`{window_days:12,thresholds:["1000000","10000000","100000000"],trigger_pct:"5",general:"exchange_reported",suspect:"sum_hourly_reported"}`；L4門檻字串`"1"`。其餘演算法由 standard_sha256 固定；DV1／DV3可直接依本規範產生相同政策位元組作啟動輸入，不依賴DV2程式完成；DV2封裝時必核對同一SHA |
| `sample_plan.json`／DV3→DV1、DV4 | `{schema_version,policy_sha256,p3b_manifest_sha256,readable,seed,strata}`；schema=`r8_verification_sample_plan_v1`；readable=`{start,end}`半開。strata逐項=`{year,tier,population_size,base_size,max_size,draws}`，按 `(year,tier)`；draws逐項=`{rank,symbol,day_start}`，rank從1開始，**保留抽樣順序**，先封存最多900序列，前base_size為基礎。tier固定 `GE_100M\|GE_10M\|GE_1M\|NO_OPEN`，排序按此列舉順序 |
| `sample_report.txt`（可選）／DV3→DV1 | DV3 既有 UTF-8／LF 文字報告；首行 `sample_plan_sha256=<原凍結計畫 SHA>`，第二行 `base denominator only; expansion is diagnostic`。有 e 或 u 的層宣告 `required_prefix=<該層 max_size> max_expansions=1`；DV1 經 `verify(..., sample_report_path=...)` 驗證計畫／分層身分，將該層 `draws[base_size:max_size]` 納入 L3。交接成功時原報告 bytes 一併存入 bundle，`verification.json.files` 及 handoff `files` 均以 `sample_report.txt`→`{sha256,rows}` 綁定（rows 為文字行數）；無此輸入則不產生此可選檔。這是 §4.5 第8點的實作對應，詳末尾勘誤二，不改主分母或抽樣規則 |
| `download_inventory.jsonl`／DV3→DV1 | 每列 `{schema_version,request_id,symbol,day_start,interval,source_kind,url,started_at,finished_at,http_status,api_status,byte_count,relative_path,sha256,status,reason_code}`；schema=`r8_verification_download_v1`，source_kind=`bybit_trade\|bybit_minute\|binance_hour\|okx_hour`，interval為`trade\|1\|60`字串；status=`AVAILABLE\|UNAVAILABLE\|SCOPE_INCOMPLETE\|SIZE_BLOCKED`。按 `(symbol,day_start,source_kind,interval,request_id)`；失敗仍一列、不替換抽樣，未回應欄位 null；相同SHA原件可重用但請求列保留 |
| `findings.jsonl`／DV1→DV2、DV3、DV4 | 每列 `{schema_version,finding_id,symbol,dataset,interval,timestamp,field,rule_id,reason_code,source_refs,details}`；schema=`r8_data_finding_v1`；details固定為`[{name,value}]`，name唯一按字典序，value為字串或null。按 `(timestamp或−1,symbol,dataset,interval,field,finding_id)`；壞時刻不猜值，以SourceRef定位 |
| `corrections.jsonl`／DV1→DV2、DV4 | 每列 `{schema_version,correction_id,symbol,dataset,interval,timestamp,field,original_value,candidate_value,corrected_value,unit,formula,evidence_kind,source_refs,coverage_status,order_status,rule_ids,decision,reason_code,row_action,policy_sha256,approval_event,supersedes}`；schema=`r8_data_correction_v1`，按 `(timestamp或−1,symbol,dataset,interval,field,correction_id)`；rule_ids去重字典序，supersedes為前版correction_id或null。decision／row_action與值限制沿§3.1；coverage_status=`PASS\|CONFLICT\|UNAVAILABLE\|NOT_APPLICABLE`，order_status=`UNIQUE\|TIMESTAMP_MULTI_PRICE\|UNAVAILABLE\|NOT_APPLICABLE`。DV-A不需逐筆，兩狀態可NOT_APPLICABLE，不能由此冒稱G通過 |
| `verification.json`／DV1→DV2、DV3、DV4 | `{schema_version,status,policy_sha256,p3b_manifest_sha256,sample_plan_sha256,previous_corrections_sha256,review_refs,tool_commit,readable,counts,files,reason_codes}`；schema=`r8_data_verification_v1`，status=`READY\|BLOCKED`；readable同上，review_refs為排序的SourceRef陣列。非抽樣批次的sample_plan_sha256、首版previous_corrections_sha256可null，覆核尚未完成則review_refs=[]並記原因，不冒稱已覆核。counts固定為`{input_rows,checked_days,flagged_days,corrected_fields,unresolved_rows}`非負整數；files為相對檔名→`{sha256,rows}`，只含本bundle產物、不含自身避免循環；reason_codes去重字典序。READY只指本次驗證產物可交接，不等於抽樣或研究驗收通過 |
| `verification/hypothesis_binding.json`／DV2→DV5、DV6 | `{schema_version,hypothesis_id,policy_sha256,family,registration_sha256}`；schema=`r8_verification_hypothesis_binding_v1`；family=`ordinary\|listing`，綁既有登記的身份／內容雜湊；不由策略選擇。不改帳本trial_record回傳形狀；無匹配登記拒絕發布 |
| `verification/listing_regimes.jsonl`／DV2→DV5、DV4 | 每列 `{schema_version,symbol,day_start,known_at,observed_listing_at,launch_time,listing_time_mismatch,origin_refs,stage,reason_code,cooling,quantity_inputs,policy_sha256}`；schema=`r8_listing_regime_v1`，按 `(known_at,symbol)`；stage=`initial\|middle\|stabilizing\|ordinary`，cooling為true／false／null；origin_refs為觀測首箱及instruments身份的SourceRef陣列。quantity_inputs按day_start遞增，每項`{day_start,volume_sum,hour_count,status,source_refs}`，status=`FULL\|PARTIAL\|MISSING`；量未知時volume_sum=null、hour_count保留應有數。known_at為階段首次可知時刻；初期首筆為首箱結束，後續每日午夜依已閉合前綴寫當日階段，缺未來轉換欄位 |
| `custom/listing_regime/<symbol.lower()>.csv`／DV2→DV5 | UTF-8／LF、**含標頭**，欄位次序固定`known_at,day_start,stage,reason_code,cooling,policy_sha256`；行按known_at遞增；cooling字面值`true\|false\|null`。只投影上列欄位，不在策略視圖暴露完整檔或未來時刻；不要套用現有無標頭custom檔的解析假設 |
| `verification/turnover_decisions.jsonl`／DV2→DV5、DV6、DV4 | 每列 `{schema_version,symbol,decision_utc_day,known_at,policy_sha256,history_sufficient,inputs,m_d,m_e,m_h,tier_d,tier_e,tier_h,triggered,selected_source,selected_median,selected_tier,status,reason_codes}`；schema=`r8_turnover_decision_v1`，按 `(decision_utc_day,symbol)`，known_at=decision_utc_day午夜。inputs正好12項按日遞增，每項`{day_start,exchange_reported,effective_reported,sum_hourly_reported,daily_status,hourly_status,source_refs}`；各status=`VALID\|MISSING\|INVALID\|NOT_EVALUATED`。金額原值未知用null，僅求中位數時按既有缺日規則映射0；未觸發可不求小時和，hourly_status=NOT_EVALUATED，m_h／tier_h=null。tier用上述四級；selected_source=`effective_daily\|hourly_sum`。status=`READY\|BLOCKED`；BLOCKED時selected_*為null、reason_codes必填；READY且歷史不足仍selected_tier=NO_OPEN。same-key不同內容拒絕，不能把後來觸發反寫較早列 |

新檔案均進既有 manifest `files`，metadata鍵仍是 `{sha256,rows,first,last,source_file,source_sha256}`；新JSONL的rows為物件數、first／last為已知UTC時刻最小／最大值（沒有時刻則null），單一JSON物件rows=1、first／last=null，CSV列數不含標頭。單一原檔衍生沿用其身份；多來源證據的source_file=`manifest.json`、source_sha256=原P3b manifest SHA，詳細來源列在檔內，不假稱由單一行情列產生。U5由runner驗證並將決策表作框架專用唯讀掛載；不交假說路徑或檔案內容。U6由DV6新增受控讀取；原日額從manifest已綁定的`verification/original/`可讀切片取得，有效日額／小時額從`source/`取得，不為核對而越界讀P3b；同時獨立用這些輸入與政策重算，拒絕偽造selected_*；不得匯入U5選級函式。

**交接回傳形狀。** DV1驗證及DV3計畫／取數工具的新公開交接回傳值一律為 `{schema_version:"r8_verification_handoff_v1",status:"READY"或"BLOCKED",artifact_root,primary_file,primary_sha256,files,reason_codes}`；files映射相對檔名→`{sha256,rows}`，primary_file必須在files且SHA相同。若連主產物也未生成，primary_file／primary_sha256=null且status=BLOCKED；不得回true、tuple或另一層`result`包裝。artifact_root為呼叫者已指定的輸出根（不寫入可重現內容雜湊），其餘都可由產物驗證。U4 `materialize(...)`仍**直接回傳 manifest dict**，同時寫`materialization.json`；U5／U6的既有run／recompute回傳形狀不變，整合驗收直接讀真實結果的`recompute_passed`及`differences`，不能自行假設tuple／record包裝。


#### 8.4.1 DV-V2 固定擴充（原 v1 格式保留）

本節與 §13 同屬版本二契約。`volume_semantics_policy` 固定為 `v2-terminal-suffix-20261022`；歷史 v1 身分為 `v1-strict`。既有 `_v1` 產物不加欄、不改 bytes，消費者按其 schema 明確認作 v1-strict；不能把缺新欄的一般輸入猜成 v2。下列 `_v2` 只由 DV7 實作後產生，缺鍵、未知鍵、版本／政策不符仍拒絕。共同編碼、SourceRef、排序、原值及 KEEP／CORRECT／UNRESOLVED 限制沿 §8.4。

| 產物 | v2 的固定形狀及含義 |
|---|---|
| `policy.json` | 原 policy 全部鍵加 `volume_semantics_policy`；schema=`r8_data_verification_policy_v2`、approval_event=`RH-20261022-05`、standard_sha256 為本文件完整 bytes SHA。listing／sampling／turnover／L4 值不改，政策選擇由驗證／物化端固定 |
| `volume_semantics.jsonl`／DV7 的 DV1→DV2、DV3、DV4 | 每個所需小時一列，固定 `{schema_version,policy_sha256,volume_semantics_policy,symbol,day_start,timestamp,hour_classification,day_applicable,original_volume,trade_volume,volume_delta,volume_source,tail_group_count,tail_count,tail_volume,tail_first_timestamp,tail_last_timestamp,prefix_first_timestamp,prefix_count,source_refs,reason_codes,confidence_evidence}`；schema=`r8_volume_semantics_v2`，按 `(day_start,symbol,timestamp)` 排序；timestamp 為小時 UTC 毫秒起點，day_applicable 為 §13.2 日適用條件的布林值，不代表整列 include |
| `corrections.jsonl` | 原 correction 全部鍵加 `{volume_semantics_policy,volume_source,reason_codes}`；schema=`r8_data_correction_v2`。原 reason_code 保留逐欄主原因，reason_codes 去重字典序保存全部原因，含原 C3 失敗及選源風險。volume_source 只對 field=volume 非 null；supersedes 指原 v1 correction_id（無前版才 null），不能覆寫舊檔 |
| `verification.json` | 原 verification 全部鍵加 `{standard_sha256,volume_semantics_policy}`；schema=`r8_data_verification_v2`；原 counts 定義不變，files 必須含 `volume_semantics.jsonl` 及政策／裁決／發現雜湊。status=READY 仍只表示可交接，不表示抽樣通過 |
| `findings.jsonl` | 保留 `r8_data_finding_v1` 的鍵與 details 形狀，v2 的每個 C3／尾段發現用 details 的唯一 name=`volume_semantics_policy`、`hour_classification` 明標政策與 §13.2 分類；原 C3 發現永久保留。其政策歸屬由所在 verification／files SHA 綁定，不靠欄位未出現推定成功 |

`hour_classification` 固定列舉為 `STRICT_C3|TERMINAL_SUFFIX_EXACT|PARTIAL_TIMESTAMP_SUBSET|NO_COMPLETE_SUFFIX|POSITIVE_VOLUME_DELTA|MISSING_ORIGINAL_HOUR|IDENTITY_UNCERTAIN|OUT_OF_SCOPE|C1_INVALID|C2_CONFLICT|EMPTY_PREFIX`。先拒絕越界、身分不確定、缺原小時、C1、C2 輸入，再在可核對的小時計算 §13.2 量分類；多個已知輸入失敗均入 reason_codes，單一分類按上述輸入檢查順序記第一個，不改變全部不放行的結果。C4／更正後 L1 是其後逐欄／逐列閘門，原因不覆蓋已保存的量分類。

`volume_source` 固定為 `v1_strict|trade_reconstructed_terminal_suffix|null`：第一值指完全沿 v1 嚴格裁決的量（包括按 v1 合法更正的日量，故不誤稱一概為交易所原值）；第二值指 (e) 適用日以完整逐筆取得的日量及尾段小時量；同日 STRICT_C3 小時量仍標 v1_strict。未決無可採量為 null；有量候選但其他欄未決時仍保存已選量來源，row_action=missing。選源與整列可用性分開。

量與差值為精確一般十進位字串；缺必要輸入為 null。`tail_*timestamp`／`prefix_first_timestamp` 為**精確 UTC epoch 秒十進位字串**，保留子毫秒，不套共同 K 線整數毫秒型別；分組按數值而非字串。count 為非負整數；無尾段的 STRICT_C3 用 tail_group_count=tail_count=0、tail_volume="0"、尾時間 null，prefix 為全部逐筆；不能判定者相應值 null。命中尾段的 count／時間／量與 SourceRef 見證逐項相符，前綴非空且首戳不變。

`confidence_evidence` 固定 `{prefix_hlc,tail_minute,next_hour_open}`，每項固定 `{status,source_refs,details}`；status=`SUPPORTS|CONTRADICTS|UNAVAILABLE|AMBIGUOUS`，details 沿 `[{name,value}]` 型別及排序。只記 §13.4 三類已授權可讀的證據，沒有證據為 UNAVAILABLE；不為補此欄越界、取未授權鄰日或改判詞。`reason_codes` 為非空時去重字典序陣列，§13.3 的原因碼按適用情況全部保留，輸入分類失敗亦用同名原因碼。

物化保留 `r8_materialization_v1` 頂層形狀；v2 政策身分與規範 SHA 經 `verification/policy.json`、`verification/verification.json` 及新增 `verification/volume_semantics.jsonl` 的 **manifest files SHA** 綁入 manifest／trial 身分，不偷加頂層鍵。原 sample_plan 及其 SHA 作凍結抽樣身分；v2 verification 引用同一 sample_plan_sha256，plan 內原 policy_sha256 是抽樣凍結時的 v1 身分，不能因重驗換寫。DV7 須核對同一 P3b、readable、抽樣參數與 draws，明確連結 v1 凍結計畫和 v2 驗證政策，不把這項經核准的雙政策關係當任意 POLICY_MISMATCH 豁免。公開 handoff 包裝及 U4 manifest dict 回傳形狀保持 §8.4 原約；DV2 消費新 schema，假說介面不得暴露此證據。

## 9. 實作單元、交付身分、檔案範圍與工作量

**六個單元均已獲准派工，DV6 已啟動；自本 PR 合入 main 時生效。本次仍只改文件。** 每個交付使用下列唯一身分，不能換ID重置審查額度。程式／測試／紀錄寫入範圍互不重疊，可唯讀他方介面；額外必改檔案先交 conductor，不順手擴檔。

| 單元／交付身分 | 唯一可改檔案 | 交付內容與依賴 | 人工作日 |
|---|---|---|---|
| DV1 驗證與裁決工具；`R8-S2-DATA-VERIFY-DV1-20261022` | 新增 `program_code/research/r8_data/verification.py`、`program_code/research/tests/test_r8_data_verification.py` | L1–L4、G價格／量、無G的DV-A、findings／corrections／verification及固定回傳；依本規範格式開工，可與DV3平行，消費其原件 | 3–5 |
| DV2 U4 疊加、上市時間軸與成交額決策輸入表；`R8-S2-DATA-VERIFY-DV2-20261022` | `program_code/research/r8_engine/materialize.py`、`program_code/research/tests/test_r8_engine_materialize.py`；新增 `program_code/research/r8_engine/data_verification_policy.json` | **依DV1介面**：疊加裁決、manifest、listing_regimes、hypothesis_binding及turnover_decisions；政策按本規範固定，生產與消費資料逐位一致 | 3–4 |
| DV3 抽樣計畫與取數工具；`R8-S2-DATA-VERIFY-DV3-20261022` | 新增 `program_code/research/r8_data/verification_fetch.py`、`program_code/research/tests/test_r8_verification_fetch.py` | 固定計畫／種子／分層／統計、有限取數及清單／大小預檢、一次擴大；**可與DV1平行**。真正取數另依已生效規範與派工的清單、可讀範圍及限額執行 | 2–3；下載／解壓另計 |
| DV4 記錄者整合驗收；`R8-S2-DATA-VERIFY-DV4-20261022` | 新增 `docs/execution_plan/2026-10-22--r8-stage2-data-verification-check-record.md`；倉庫外本交付專屬 evidence 目錄 | **最後，依DV1–DV3、DV5、DV6**：26日、4翻級、上市前綴／樣本格數、全訓練L1、抽樣及P4歷史重算；不改其他單元程式來通過驗收 | 1–2 |
| DV5 U5 資料視圖及決策輸入讀取；`R8-S2-DATA-VERIFY-DV5-20261022` | `program_code/research/r8_engine/lean_algo/framework.py`、`program_code/research/r8_engine/lean_algo/rules.py`、`program_code/research/r8_engine/lean_runner.py`、`program_code/research/tests/test_r8_engine_lean.py` | **依DV2產物**：t的階段、族別三入口遮蔽、讀取turnover_decisions並核對選級；不改單筆上限／成交規則 | 2–3 |
| DV6 U6 讀取決策輸入表、獨立重算；`R8-S2-DATA-VERIFY-DV6-20261022` | `program_code/research/r8_engine/series.py`、`program_code/research/tests/test_r8_engine_series.py` | **已啟動，依DV2產物**：獨立核對12日原／有效／小時輸入與選級、身份及重物化一致；與DV5真實實作交叉測試，不匯入其選級函式。上市可見性本身仍不新增U6交易規則 | 1–2 |

**依賴順序固定：** 本規範格式 → DV1 ∥ DV3；DV1介面 → DV2；DV2產物 → DV5 ∥ DV6；全部可用後 → DV4。平行是實作可同時開始，不免除跨單元真實互通測試；測試對方尚不可用時記待整合，保留同一交付身分，不以假函式充數。資料政策的事前固定由本規範／policy完成，不以尚未開工的P5假說預登記作工具開發前置；validation測試沿既有測試登記介面建立合法身份，不提前開holdout。

**每單元至少一個真實對方測試（交付驗收硬條件）。** 依本機倉庫記憶 `memory/reference_codex_delivery_timers.md` 的2026-10-21補記：各自測試全綠不代表互通；資料格式、排列及回傳形狀須固定，至少一個測試使用對方真實實作。該記憶是本機來源，未隨本PR發布；以下把可攜要求完整寫入規範：

| 單元 | 最少一個必需的真實整合測試 |
|---|---|
| DV1 | 真正呼叫DV3產生sample_plan／inventory／保存原件，再由DV1解析與裁決；可用本機固定檔來源測傳輸邊界，不能假造DV3回傳物件取代其實作 |
| DV3 | 以DV1真實verification／findings產物執行錯誤／未決計數及一次擴樣判定；同時把自身計畫／原件交給真實DV1驗收，不能各自假設schema |
| DV2 | 消費DV1真實更正bundle，呼叫現有真實帳本登記／trial_record與U4 materialize，核對實際manifest dict及三種資料輸出；不以假ledger回傳格式過關 |
| DV5 | 讀DV2真實物化、listing及turnover表，經真實U5視圖驗score／fit／決策遮蔽與前綴不變；至少一例將自身run交給DV6真實recompute作交叉核對 |
| DV6 | 讀DV2真實物化及DV5真實run，獨立重算並核對`recompute_passed=true`、`differences=[]`；篡改選級／身份另須拒絕，不以假U5或共用規則生成唯一預期 |
| DV4 | 將DV3→DV1→DV2實際產物接到固定映像U5→U6，按§10凍結獨立預期逐案比對；保留P4-D0／P4-D重算與所有非零殘差，不以模型自算預期代替證據 |

對方真實實作指受派單元的實際程式及其輸出，需記commit／檔案SHA、呼叫入口、輸入／輸出SHA與執行結果；抄一份對方算法、手工拼同形JSON、monkeypatch成lambda或只驗假物件都不算。單元內isolated測試仍可用固定fixture，但不能替代上述至少一例。DV4實跑輸入放共享的`/Users`路徑，不能假設`/private/tmp`已掛入Docker。執行者先依現場公開工具確認租約、有限審查時段與命令可用度；無可執行通道如實記未驗，交conductor處理，不改治理工具或另取身分繞過限額。

DV1–DV6 合計 **12–19人工作日**的規模參考（大量下載另計）；不是延長15工作日投入上限的授權。REPORT-TOOLS保持另單元且只用一般市場階段；holdout啟用仍待LEDGER-FIXES。

**Codex 執行時間粗估（隨計畫核准，仍非工期保證）。** 現場參考：C 的整輪調查／取數／報告為約12分30秒（23:37:01–23:49:31 UTC），T 的全訓練成交額離線分析／報告為7分47秒；兩者都不是正式驗證工具的開發／獨立驗收時間。[P4-D §9](2026-10-21--r8-stage2-p4-d-check-record.md#9-b-段驗收執行時間量測與-p4-d-結案2026-10-22) U4 的1／100／1,087標的物化為0.954／10.772／66.626秒；100標的 runner 61.179秒，1,087標的因記憶體保護停止，38.469秒不能外推完成時間。

依此只作排程情境：DV1 2–4小時、DV2 3–5小時、DV3程式／小型檢查1–2小時、DV5 2–4小時、DV4整合／凍結回歸／報告2–4小時，DV1–DV5小計10–19小時，已啟動DV6另計1–3小時，合計 **11–22個 Codex 執行小時**（可分派，不等於人工工時；獨立審查排隊、CI等待與介面返工另計）。正式抽樣計算的吞吐尚未量測，先以100日的已核准前綴作資源量測，再報全量 ETA，不能用上述小案例保證完成。

下載另外估：10.23／30.69 GB 若有效速度10 MB/s，純payload約17／51分鐘；1 MB/s約2.84／8.53小時。另加7,200／21,600請求的限流、延遲、重試與其他L3／L4來源，實際可更長。解壓／逐筆解析沒有獨立吞吐證據，計畫預留基礎1–4小時、擴大3–12小時作容量情境，**不是量測或完成上限**；先量測再派發。本輪未取數、未做該100日預檢。


**DV-V2 實作修訂（原六單元及停止歷史保留）。** 新增下列序列化後繼單元；本次只記規格與單行 pin，不實作 DV7、不重開原 DV1／DV3，也不重置其審查額度。

| 單元／交付身分 | 唯一可改檔案 | 依賴與驗收 |
|---|---|---|
| DV7 成交量語義版本二；`R8-S2-DATA-VERIFY-DV7-20261022` | `program_code/research/r8_data/verification.py`、`program_code/research/r8_data/verification_fetch.py`、`program_code/research/tests/test_r8_data_verification.py`、`program_code/research/tests/test_r8_verification_fetch.py` | 依 **PR #241 合入的 DV1／DV3**；前者依 §13 實作 v1/v2 固定政策、分類、原因碼及 §8.4.1；後者依 §13.6（調查 §15）雙政策統計。DV1 側至少一測試消費 DV3 真實計畫／原件；DV3 側至少一測試消費 DV1 真實 v2 verification／findings／corrections，另保留真實 v1 回歸與 §13.7 逐格對照 |
| DV2 既有身分與檔案不變 | 沿上表 DV2 範圍 | **排在 DV7 之後**：須讀 v2 schema 與固定選源，而目前 DV1 只有 v1；§8.4.1 雖先固定格式，僅靠手工 v2 物件不能滿足真實對方測試。可唯讀契約作準備，正式交付依 DV7 真實 bundle |
| DV4 既有身分與檔案不變 | 沿上表 DV4 範圍 | **最後，依 DV1–DV3、DV5、DV6、DV7**；先以 v1 跑凍結稽核並保留其失敗，再以 v2 重驗同一樣本；§13.6 的待裁決目標不得自行預設 |

v2 順序為 **#241 合入 → DV7 → DV2 → DV5 ∥ DV6 → DV4**。DV7 對原 DV1／DV3 檔案是後繼所有權，與 #241 執行手互斥，不是准許同時寫同檔。DV7 新增工時尚未量測／核定，原六單元估算不改寫為含 DV7；15工作日總投入上限維持，超出須交 conductor／Operator，不能自動延長。

## 10. 驗收與方法論自檢

**DV-V2 修訂註記**：本節原 V1／V2／V4 驗收保留為 v1；新增 §13.6–13.7 的雙政策凍結驗收及26日逐格預期。DV7 實作與 DV4 實跑仍待交付；不能用15/26可用性取代錯誤率上界。

以下是**未來實作驗收條件，現在全部 NOT_RUN**。本 PR 只驗文件結構與引用，不以文件 CI 代替資料驗證。

| 驗收 | 必須交付的證據／拒絕條件 |
|---|---|
| V1 26日固定回歸 | 逐一覆蓋 I §3.2 全26日及 C §5 原31欄，再加 C §6 的量／額／open 與涵蓋差異；D/H/M/T 原值、證據位置、規則、KEEP／CORRECT／UNRESOLVED 及有效列結果齊全。先人工依報告凍結預期；不得預設26日皆修好 |
| V2 必須抓住的反例 | BCH 兩零只為候選；PUMPBTC 六欄相等仍因缺早段未決；XEM 不以較細週期改低日高；LTC 同戳多價不挑檔案末價；有效 open 依 D1；小時量不對帳不改量；D2 自報日／小時和與逐筆三種金額不能混稱精確；額雙算不得要求 G／觸發取數 |
| V3 全市場訓練段 | 母清單仍是 P3b 全清單，不為通過移除異常標的；450 個訓練空標的依 I 記空，不算正常列。全部原列 L1、全部日 L2、全部命中日 L3 具有終態；物化有效列全通過 L1，未決全部落 gaps／limitations，覆蓋／排除分母相符。不要求清除發現紀錄或虛構缺失行情 |
| V4 抽樣 | 封存 N／分層／種子／清單／bytes；報 e、u、語義差異、逐欄錯誤率、加權95%上界及擴大結果；符合 D4 核准的上界與停止條件。部分日、未收錄市場與來源共同錯誤保留限制 |
| V5 更正與不可繞過 | 篡改原值／raw SHA／更正 SHA、未核准版、衝突鍵、跨界列／holdout、缺 bundle、raw 有而 source 未改、lean/custom 與 source 不一致均拒絕；無裁決旗標或未來證據進策略視圖。保持 Python 同程序限制的誠實說明 |
| V6 P4-D0／P4-D 回歸 | 使用原已保存的物化、run 與獨立凍結預期，全部已通過案例重算一致；保留 §16 所有非零殘差與 §9.8.8 比對標準。新物化另以同一合格視圖核對 U5／U6，不把歷史資料改成新值後要求舊 run 假裝相同；資料有變時列出預期差異，不能用更正掩蓋引擎回歸 |
| V7 決策影響 | 對被更正／隔離列列出 known_at、暖機、日線指標、12日分級、最後小時1%上限、作廢／減倉懲罰、資金費與 filled_periods 影響。無持倉不宣稱資金費必然改變；日線變更也不能宣稱全部成本不受影響 |
| V9 上市因果／族別 | 用相同前綴搭配不同未來量，直到 t 的階段／訊號視圖逐位相同；驗第3／15／30日上限、部分首日、缺日／零分母／12日歷史、冷卻unknown與轉換原因；一般族三入口及日後回看無上市 K 線、上市族只有當時階段；§9.18 只取一般市場。樣本以事件去重，不把階段重複作獨立樣本；比較 U5 真實視圖與固定預期 |
| V10 成交額觸發與限制 | 固定 T 的4個翻級例子、±5%含邊界／帶外、缺小時、原額0、疑點日及有效中位數觸發及原值對照；核對因果決策輸入與 U5/U6 真實實作。不能以全期回寫12日歷史令先前結果改變；單筆上限原小時值保持不變 |
| V8 重現與原件不變 | P3b 原件 SHA 不變；相同輸入／政策兩次物化逐位相同；U6 submit 重新物化身份相同；獨立算術驗證不借用被驗器產生預期 |

### 10.1 對相關技能硬門檻的覆蓋

| 技能／要求 | 規範涵蓋與狀態 |
|---|---|
| `walk-forward-validation-protocol` §5：ADF、KPSS、Ljung-Box、JB、ARCH | **保留，未執行**；P4 §9.18／REPORT-TOOLS 在 DATA-VERIFY 實作完成後、P5 前以訓練段**一般市場階段**有效資料執行，附原 P3b 與更正／物化 SHA。L1–L4 不是這五檢定 |
| 同技能：厚尾不採常態模型、自相關需 block bootstrap；樣本不足停止／標不足 | **保留** §9.18 預先固定無條件處置、樣本不足標記與停止條件；不能看本前檢結果才挑模型／標的。資料抽樣的有限母體區間不是策略報酬的 IID bootstrap |
| 同技能：PSR／DSR、sweep 多重檢驗、PBO、參數穩健性 | **保留於研究層**，不由資料通過推論策略成立；R8 已採的 BY、折內試驗定義與附加條件優先，本文不另改既有數值；上市 X／Y／Z／W 或量定義每次調整另算試驗並進 DSR 的 K |
| `time-series-cv-protocol`：時序不 shuffle、purge／embargo、樣本與 per-fold 檢查 | **保留** P4 §9.1／§9.2／§9.11；DV-SAMPLE 的無放回資料品質抽樣不是訓練／測試切分，不可搬成 KFold。通用技能的 rolling 建議不覆蓋 R8 已採的 expanding 契約 |
| `feature-engineering-protocol`：六類 leakage | **涵蓋邊界**：known_at／閉合 bar；不以品質或收益結果選模型／全期標準化；holdout／target 隔離；保留已下架標的與 §9.15 false；UTC 與重採樣界線；上市階段／族別視圖與部分日 D3。特徵本身的 shift(1)、target window 與逐特徵稽核仍由假說驗收執行 |
| `crypto-microstructure-knowledge`：Bybit 邊界、funding 不固定8h、非零成本 | **保留**：外所只旁證、無跨所交易；歷史資金費時刻與 §9.8 成本照舊，D2 只改經核准的金額輸入，不查私人費率、不改現行交易風控 |
| `doc-cross-reference`：正本、狀態與歷史分離 | **本文件交付檢查**：TODO ACTIVE（合入後生效）、§17 已核准指向、JSON／人類路線事件、文件 hash、changelog 同步；簽核依Operator選項回覆與conductor明示指令記錄，不冒稱本輪執行了獨立E2/E4驗證 |

三項自問的答案：

1. **每條規則能否機械執行？** L1–L4、C1–C5、取樣／上界／擴大、逐欄裁決均有輸入、精確比較與終態；D1–D4、上市參數／量定義、抽樣與雙算介面已固定，跨單元格式及至少一個真實對方測試由§8.4／§9寫死，實作者不得自行改約。來源不足產生未決，不以人工「看起來正常」放行；決策輸入介面未實作則 `TURNOVER_POLICY_INTERFACE_UNSUPPORTED`／前置 BLOCKED，不能交付半套雙算。
2. **假說程式能否觀察或繞過它？** 驗證在 U4 前完成，政策由 code_commit／manifest 綁住，假說只能見依族別過濾、已可知的有效資料與當時階段，不能讀未來轉換時刻；原件／更正旗標／旁證不作特徵。現有靜態檢查與同程序模型仍有殘餘風險，不能回答為已證明絕無繞過；V5 需具體拒絕證據。
3. **更正檔與帳本能否表達失敗？** 更正檔可表達每欄 KEEP／CORRECT／UNRESOLVED 及整列 missing，驗證報告可表達前置 BLOCKED；manifest／trial 身份可綁 evidence。帳本未實作的前置失敗原因與 holdout 路徑不能偽造，依 §8.3 停止並保留 trial／K，LEDGER-FIXES 未被繞過。

## 11. 風險、未決與未驗

**DV-V2 修訂註記**：以下舊年 A／B 待決文字保留為歷史；B／(e) 已採納。§13.5 的假成交、晚戳換 ID 重錄、內部抵銷及同源共錯仍無法排除，來源真值必記 `SOURCE_TRUTH_UNVERIFIED`；根因維持推論。

- 無法對全部列逐筆證明；公開檔可能與 K 線共享錯誤，也可能不完整。雜湊證明版本一致，不是交易所簽章／撮合完整性認證；抽樣上界只約束定義的母集合與錯誤判準。
- **2020–2021 大量未決風險**：C3 每小時量逐位相等，C 的 BCH 2021-02-18 已有小時總量−0.68；T 的這兩年9,205個完整標的－日（約2.43%完整日分母）只是可能影響範圍，不是錯誤率。多個舊年抽樣層可能大量 COVERAGE_CONFLICT、擴樣停止、保守95%上界無法≤2.5%，大量資料視缺漏。屆時可由 Operator 選整年不納入並列限制，或另定量語義後重驗；本規範不預放寬。C4 同戳多價的保守條件另可能擴大未決；缺漏改變研究樣本須揭露。
- 來源同意與歷史期間不等於當時資訊：修正是事後修復研究資料，不證明當年可即時取得相同修正版；已完成 bar 的 known_at 保持，事後品質判斷不可變成新訊號。
- 已核准的參數、量定義、公式、DV6、抽樣及估計成本不列回未決；舊年未決後A／B處置仍須凍結稽核結果再裁定。全量外部覆蓋、逐筆完整性／同戳排序、歷史 tick、交易所內部 open 定義仍未驗；T 在所分析2022–2025H1完整日觀測D/H無差異，不證明逐筆真值或未來相同。
- **投入上限**：R8 階段2–3合計上限為15個工作日，以實際工時記帳；本規範含DV6的12–19人工作日規模參考及抽樣將占相當部分，且不含其他R8工作。Operator已連同估計核准；PM執行時仍須依實際剩餘工時與停止條件記帳、達上限回報，不因Codex較快或下載等待而默認無成本／延長上限。
- §8 是經來源查核、已核准的介面契約，尚未實作驗證；U5/U6 相符只驗引擎一致，不再驗一次更正真值。獨立方法論審查由 conductor 把關，本文自檢不替代。
- 全市場訓練物化、抽樣、擴樣、26日新規則回歸、P4 重算、holdout 自動流程本輪均 **NOT_RUN**；沒有資料修復、研究成功、模型可用、收益或交易效果結論。

## 12. 簽核與生效

**DV-V2 修訂註記**：本節為 v1 簽核歷史；新增 §13.1／RH-20261022-05 記錄 B／(e) 裁決。本 v2 文件由 conductor 審查並合入後生效；Codex 不合併，DV7 合入前仍只有 v1 工具，v2 資料驗收未完成。

Operator 2026-10-22 以選項回覆核准，依本輪 conductor 續派轉錄；不捏造紙本簽名或新的審查報告。conductor 方法論審查完成依同輪明示指令登錄，本輪核准登錄提交的最終審查／合併仍由 conductor 執行。

| 簽核／裁決 | 選項或結論 | 簽核人／權威來源 | 日期／證據 |
|---|---|---|---|
| conductor 方法論審查 | 完成；核准登錄後由 conductor 審查本輪提交並合併 | Claude Code／conductor 本輪指示 | 2026-10-22；RH-20261022-04、§2.1 |
| D1 open 語義 | 保留交易所定義，僅L1失敗按證據更正 | Operator 原文裁決 | 2026-10-22；RH-20261022-03 |
| D2 成交額與U6介面 | 一般日原值、疑點日小時和、觸發雙算；**啟動DV6** | Operator「啟動 DV6 (Recommended)」及前輪裁決 | 2026-10-22；RH-20261022-03／04 |
| D3 上市參數、量定義與公式 | **X=50%、Y=20%、Z=20%、W=7日；量A、均量相對差公式** | Operator「中間值 (Recommended)」，對應內容由conductor逐項轉錄 | 2026-10-22；RH-20261022-04 |
| D4 驗收、抽樣及估計成本 | **種子20261022、每層300、一次擴至900、保守95%上界≤2.5%**，連同下載與工時估計 | Operator「每層 300，可擴到 900 (Recommended)」 | 2026-10-22；RH-20261022-04；不延長15工作日總上限 |
| Operator 整份規範核准 | **核准並開始實作**；依§9六個交付身分執行 | Operator「核准並開始實作 (Recommended)」 | 2026-10-22；RH-20261022-04 |
| 生效版本／合入main | **自PR #240合入main時生效**；本輪未合併，合併commit及時刻由Git記錄 | conductor負責合併；不是Codex合併授權 | 待實際合併記錄，不預填合併SHA／時刻 |
| 舊年未決後續A／B | 尚未選定；維持C，看到凍結稽核結果後再裁決 | Operator | 待凍結稽核結果 |


## 勘誤一（2026-10-22，conductor 依規範既有定義澄清）

C4 與 §5 G 閘門的「同戳多價」逐欄判定：O 只看目標時窗的最早時間戳是否具有唯一價格，C 只看最晚時間戳；H、L、V、A 與同一時刻內的成交先後無關，不因同戳多價而未決。中間時間戳的多價照常記入 findings，保留時間戳與價格集合；不得以檔案行順序推定成交先後。日線與各小時按各自目標時窗判定。

這是依 C5 既有的 O／H／L／C／V／A 定義所作的解釋，不是新規則。原文保留；C1–C3 的涵蓋／數量條件、DV-O-SEM 採交易所定義、DV-A 不套 G、逐欄後整列 L1／L2 重檢均不變。下表引用 DV1 報告的既有26日逐日結果，並非全市場驗收或公開逐筆檔完整性保證。

來源：`/Users/ncyu/Projects/TradeBot/audits/2026-10-22-r8-data-verify-dv1/REPORT.md`「26日逐日結果」，SHA-256 `b14f6b2756c62facfb22077ce393fbc4bbc892b0c6f5c80d3127b6c2dd598225`；機器明細 `26-day-results.json`，SHA-256 `302149717a84f1288bc46e93257d3f43aa44bcebb4164b0605315ab29ee46d2a`。DV1 原 E2 因300秒上限到期為 UNVERIFIED、E4 NOT_RUN；conductor 已審讀並接受核心裁決邏輯，原狀態不改寫。

K=KEEP、R=CORRECT、U=UNRESOLVED；欄位順序 O/H/L/C/V/A。整列 include 7、missing 19；C4 解釋不解除其他涵蓋失敗。

| 標的 | 日期 | O/H/L/C/V/A | 整列 |
|---|---|---|---|
| BCHUSDT | 2020-12-14 | R/K/R/K/K/R | include |
| BCHUSDT | 2021-02-18 | U/U/U/U/U/R | missing |
| BCHUSDT | 2021-02-28 | U/U/U/U/U/R | missing |
| BCHUSDT | 2021-03-03 | K/K/K/R/R/R | include |
| BCHUSDT | 2021-04-02 | U/U/U/U/U/R | missing |
| BTCUSDT | 2020-03-25 | K/K/R/K/K/R | include |
| BTCUSDT | 2021-02-12 | U/U/U/U/U/R | missing |
| BTCUSDT | 2021-02-13 | U/U/U/U/U/R | missing |
| BTCUSDT | 2021-02-14 | U/U/U/U/U/R | missing |
| BTCUSDT | 2021-02-27 | U/U/U/U/U/R | missing |
| BUZZUSDT | 2025-04-19 | U/K/K/R/R/U | missing |
| DOTUSDT | 2021-11-29 | U/U/U/U/U/R | missing |
| ETHUSDT | 2021-04-01 | U/U/U/U/U/R | missing |
| ETHUSDT | 2021-04-07 | U/U/U/U/U/R | missing |
| LINKUSDT | 2020-10-21 | K/K/R/K/K/R | include |
| LINKUSDT | 2021-03-03 | U/U/U/U/U/R | missing |
| LINKUSDT | 2021-03-25 | U/K/K/R/R/R | missing |
| LTCUSDT | 2020-10-21 | K/K/R/K/K/R | include |
| LTCUSDT | 2021-02-18 | U/K/K/U/R/R | missing |
| LTCUSDT | 2021-03-17 | U/U/U/U/U/R | missing |
| LTCUSDT | 2021-04-08 | K/K/K/R/R/R | include |
| LTCUSDT | 2021-04-10 | U/U/U/U/U/R | missing |
| PUMPBTCUSDT | 2025-06-03 | U/U/U/U/U/U | missing |
| XEMUSDT | 2021-11-30 | U/U/U/U/U/R | missing |
| XTZUSDT | 2020-10-21 | K/K/R/K/K/R | include |
| XTZUSDT | 2021-03-24 | U/U/U/U/U/R | missing |

其中 BCHUSDT 2020-12-14：O CORRECT 272.95、H KEEP 280.35、L CORRECT 265.15、C KEEP 276.95、V KEEP 10905.15、A CORRECT 2954180.78。A 依疑點日規則取小時交易所自報成交額加總，不以逐筆成交額取代。窗內3組同戳多價保留於 findings，首末時間戳均唯一價，因此不阻斷 O／C。


## 13. 版本二：成交量語義——尾段補入、逐筆為準（DV-V2）

### 13.1 裁決、背景與版本界線

Operator 裁決照錄（conductor 2026-10-22 派工轉引，RH-20261022-05 follows RH-20261022-04）：

1. 對 conductor 所列「A：這兩年不納入研究；B：另訂成交量規則後重新驗證」，Operator 2026-10-22 回覆：「B」。
2. 對成交量規則選項，Operator 2026-10-22 以選項回覆：「(e) 逐筆為準 (Recommended)」。conductor 呈報的選項為：(e) 逐筆為準（15/26）、(b)+D1 價格分離（12/26，Codex 建議）、(e) 優先其餘 (b)+D1、維持原標準（7/26）。Operator 選定 (e)，**不採** (b)／(b)+D1 作為後備：不符合 (e) 的 C3 失敗日維持 v1 的未決／缺失。

政策身分固定 `volume_semantics_policy=v2-terminal-suffix-20261022`；與規範 SHA 經 §8.4.1 進入 manifest。v1-strict 結果、失敗及原件永久保存；v2 是另一政策版本，不是把 v1 改成通過。規範仍由 conductor 審查本文件 PR 並合入後生效；本次不合併、不取數、不產生 v2 有效資料。

**pin 過渡界線。** 本 PR 從 #241 head `4b92cdae731c28cefe95505bb11921482b9600e4` 起，只將 DV1 `verification.py` 的 `STANDARD_SHA256` 單行更新為本規範 SHA，該 .py 其餘位元組不變，以配合 DV3 即時計算規範 SHA 的真實整合。**在 DV7 合入前，此 pin 下的工具只實作 v1-strict 成交量語義、只輸出 v1 政策，v2 分類不可用；不得把 pin 更新解讀為 v2 已實作。** DV7 須明確支援兩個版本，保留歷史 policy／standard SHA 身分，不回寫舊 bundle。

調查來源 V：`/Users/ncyu/Projects/TradeBot/audits/2026-10-22-r8-volume-semantics-investigation/`；REPORT SHA-256 `7a31e6537b414f4e0520c8ac63ab5261d8405a1c566adce17743800419c16adf`，manifest SHA-256 `e3669928b68ed8e43511cfd4a33fc7e785bb85e364c1832a47152139b8f9c1b0`，`E_26_DAY_TABLE.md` SHA-256 `a8e4cf7e7dc10548f7c5d6c9413384bc65a06670835ac3ff51ddb82ee0440435`。本章採 V §12 候選及 §14–16 的限制／報告契約；報告原先「候選、未採用」及 Codex 對 (b)+D1 的建議保留為歷史，由本次 Operator 裁決決定採用 (e)，不倒改報告。

V §3.3：24個負差小時有23個完整尾段精確見證，13日、55筆。**conductor 已用原始逐筆檔獨立重算23小時，23/23一致、13日、55筆**，依本次派工轉錄；這是 conductor 的核對證據，不冒稱本文件記錄者另重跑逐筆分析。來源仍只限已授權訓練段，不能外推全年或市場真值。

**conductor 2026-10-22 網路搜尋背景（轉錄，記錄者本輪未連網搜尋）**：公開社群、GitHub issue、資料商文件中未找到 Bybit K 線漏計尾段成交、首日 open=0 的回報或官方說明；業界一般做法是由逐筆重建 OHLCV（Coinpaprika、Mobula），資料商亦說明交易所 K 線與逐筆可能不一致（CoinAPI）。此為背景，不是根因證明；「原 K 可能在最後若干成交前停止更新」仍只是推論，沒有官方內部成因證明。未提供逐頁 URL／搜尋封存，本文不捏造引用或將「未找到」寫成不存在。

**搜尋背景來源補記（conductor 2026-10-22 網路搜尋；本次續派提供）**：上段「未提供逐頁 URL」保留為初稿記錄，以下補列 conductor 提供的來源；記錄者本輪未自行連網核對。

- [Bybit V5 Get Kline](https://bybit-exchange.github.io/docs/v5/market/kline)。
- [Bybit FAQ（成交額計價幣）](https://bybit-exchange.github.io/docs/zh-TW/faq)。
- [pybit issue #266（volume／turnover 回傳對調，結案不處理）](https://github.com/bybit-exchange/pybit/issues/266)。
- [Tardis.dev Bybit Derivatives](https://docs.tardis.dev/historical-data-details/bybit)；[Tardis.dev FAQ](https://docs.tardis.dev/faq/data)。
- [CoinAPI（交易所 K 線與逐筆不一致的原因）](https://www.coinapi.io/blog/crypto-candles-not-matching-ohlcv-explained)。
- [Coinpaprika（由逐筆重建 OHLCV、邊界慣例）](https://coinpaprika.com/education/ohlcv-data-crypto-chart/)。
- [Mobula changelog 2026-03-17](https://docs.mobula.io/changelog/2026-03-17)。

以上均為一般性背景，沒有任何一則回報 Bybit 尾段漏計或首日 open=0；此句依 conductor 搜尋結果轉錄，不是記錄者另行查證，亦不改變根因仍為「推論」的界線。

### 13.2 每小時唯一分類與日適用域

輸入固定為原件 SHA、合約／單位、授權 UTC 半開小時箱、**未更正 P3b CSV 的原 H.V** 與箱內完整已保存逐筆 T_h；raw 保留作對照。沿 §3 精確 Decimal／整數縮放，不用 binary64、容差、移時、刪筆或跨箱補筆。先驗 C1／C2、身分與可讀界線；缺原小時、身分不確定、跨界、C1 無效或 C2 衝突全部不放行。

令 `V_T=Σsize`、`δ=原 H.V−V_T`；只對原輸入分類一次，不先更正 H 再把新量代回 C3。

| 每小時分類 | 唯一可執行判準 |
|---|---|
| `STRICT_C3` | δ=0；仍須其他既有 C1／C2／C4／L1 條件，不等於整列可用 |
| `TERMINAL_SUFFIX_EXACT` | δ<0；逐筆按**數值時間戳**分組，自最晚組向前依次累加每組全部 size；首次累積 ≥−δ 即停，等於才命中。尾群完整且非空，移除候選尾群後的前綴非空、首時間戳不變；尾段可含多個時間戳群 |
| `PARTIAL_TIMESTAMP_SUBSET` | 首次累積超過−δ，只有拆開該時間戳群、保留全部較晚群再選該群的非空真子集才可精確湊足；只作拒絕分類，不採該子集、不挑同戳先後 |
| `NO_COMPLETE_SUFFIX` | 負差不能依完整尾群精確命中，且不屬上述部分同戳子集；全部不放行 |
| `POSITIVE_VOLUME_DELTA` | δ>0；全部不放行，不採 (b)／(b)+D1 |
| `EMPTY_PREFIX` | 雖尾量相等但前綴空（或不能保留首時間戳）；不放行 |
| `MISSING_ORIGINAL_HOUR`／`IDENTITY_UNCERTAIN`／`OUT_OF_SCOPE`／`C1_INVALID`／`C2_CONFLICT` | 分別對應缺原小時、身分不確定、越界、C1、C2 輸入失敗；不以 δ 計算取代失敗 |

C1 的 size>0 令累積嚴格遞增，完整群算法至多一個精確尾段；不依檔案列序、ID 字典序或任選 N 決定尾段／收盤。不存在完整群時的部分子集僅為診斷，即使命中亦拒絕。

**日適用條件**：C1、C2 通過；該日至少一小時 `TERMINAL_SUFFIX_EXACT`；其餘所需小時全為 `STRICT_C3` 或同樣的 `TERMINAL_SUFFIX_EXACT`。**同日可有多個尾段小時**，這是 Operator 選定 (e) 的主表口徑，非「每日至多一個失敗小時」。所需小時沿 v1 的原交易／可讀時窗，不擴範圍或偽造缺箱。沒有尾段失敗的日沿 v1；任一所需小時不符，本日 (e) 擴充不適用，原未決／missing 保留，沒有後備來源政策。

**不設尾段時間寬度門檻 N。** V §14.2 的本批距箱末0.4841–26.2371秒與診斷格點沒有獨立生成機制或誤差預算支持任何 N；不得用樣本最大距離或最佳 include 數選定。這不放寬完整群、C1／C2、C4 或 L1。

### 13.3 採值、硬閘門與原因碼

適用尾段小時：V=**完整 Σsize**；H=max(price)、L=min(price)、C=最晚時間戳唯一價；每欄與原值數值相等為 KEEP，不同為 CORRECT。日線用全日逐筆逐欄比較，**不是原 D.V 加尾量**，因原日量可能已含尾段。其他 STRICT_C3 小時沿原裁決。A 完全沿 v1／DV-A，不換成 Σ(price×size)。

**O 照 v1（含 D1 交易所語義）**：有效 open 沿 D1 保留，不因尾段改成首筆；原 O 非法仍須 v1 的 G、唯一首價及原生細週期支持，本政策不創造新的 O 更正權限。C4 按勘誤一逐欄：O／C 分別檢查目標窗首／末戳，相關多價為 TIMESTAMP_MULTI_PRICE／未決；中間多價只記錄，H／L／V／A 不靠同戳順序。不能用下一小時 O 從多價集合選 C。

C1、C2、完整非空尾群與非空前綴是選源硬條件；C4、改值後**全列 L1**仍是採值／可用性硬條件。保留 O 導致 H<O 或 L>O 時整列 missing，記 POST_CORRECTION_L1_FAIL；不得夾 H／L 到 O。日與小時各自判定，日 include 不代表全部小時有效。L2 原差異及改後差異逐項留存，逐筆證據定位保留；KEEP 語義／未決逐差異說明，缺漏候選小時的 V 和不得冒稱完整有效小時網格。

| 原因碼 | 必需含義 |
|---|---|
| `C3_ORIGINAL_FAIL` | 每個原量不相等的小時永久保留，並保留日的原失敗鏈；新政策可決不得命名為 `C3_STRICT_PASS` |
| `TERMINAL_SUFFIX_SOURCE_SELECTED` | (e) 日適用且該小時完整尾段被採用；單純有尾段形狀但全日不適用不能記已選源 |
| `TRADE_SOURCE_SELECTED_BY_E` | 因 (e) 以完整逐筆裁決 V/H/L/C 的欄／列，與最終 KEEP／CORRECT／UNRESOLVED 分開 |
| `SOURCE_TRUTH_UNVERIFIED` | 每個 (e) 選源日／小時的平行殘餘風險，不因可物化或量代數等式而移除 |
| `C2_CONFLICT`、`POSITIVE_VOLUME_DELTA`、`NO_COMPLETE_SUFFIX`、`PARTIAL_TIMESTAMP_SUBSET`、`EMPTY_PREFIX` | 各對應 §13.2 拒絕；維持原未決／缺失 |
| `TIMESTAMP_MULTI_PRICE`、`POST_CORRECTION_L1_FAIL` | 分別記 C4 受影響欄未決及改值後全列 L1 失敗；不可被選源成功覆蓋 |

### 13.4 信心證據與假說隔離

下列**只記錄、不作閘門、不提供假說**：前綴 H/L/C 與原 K 一致性、尾筆所屬分鐘線支持、下一小時 K 的 open 與完整逐筆 close。V §14.3–16：下一 H 可得15例，唯一末價可比14例，**14/14一致，其中7例不同於原 close**；另1例末戳多價不解除 C4，8個23時案例無授權鄰日，不讀翌日。這是交易所自身 K 線系統已記錄尾段價格的旁證，**不驗證尾段 size，也不是獨立交易所來源**。前綴 HLC 全等17/23、尾分鐘量支持19/23、尾分鐘 HLC 支持12/23；未支持／未知照錄，不加為新門檻。

政策、適用域、採值與 manifest 由驗證／物化端固定；假說只能讀已閉合、known_at 可見的單一有效視圖。假說不得選原 K 或逐筆版，不得讀尾段旗標、tail_count、更正旗標、來源風險或任何信心證據。下一小時證據屬**事後修復身分**，不得當作當時可知訊號；修正不能證明歷史即時可取得。更正量仍可能間接改變量衍生視圖與缺漏，不宣稱無法從有效資料間接辨認；拒絕繞過測試由 DV2／DV5／DV6 依既有範圍完成，Python 同程序限制仍在。

### 13.5 來源真值殘餘風險（V §14.1）

| 反例 | 現有證據的界線 |
|---|---|
| 原 K 正確，逐筆末尾混入假成交 | 獨立 ID、箱內末秒、正 size／合法價可精確命中尾群，甚至同下一 H.O；C1 與 SHA 不認證成交真實性 |
| 同一成交換 ID 並帶較晚時間戳重錄 | 不觸發同 ID 重複；新尾群仍精確，內容重複檢查亦可能看不出 |
| 內部漏錄與多錄抵銷 | 前綴少 q、多 q 互抵，另多一尾 q；總量、端點與極值相符仍不能排除內部錯誤 |
| 中段錯價或同源共錯 | 完整重建可能帶入無關錯價；分鐘線／下一 H 共享加工錯誤時局部相符不能認證真值 |

以上是反例，非已證實本批事故；現有證據均不能排除。完整尾段代數關係是定義本身，不是獨立真值證明；一律保留 SOURCE_TRUTH_UNVERIFIED。無官方根因、撮合序號完整性或獨立事件真值，不給出無據的錯放機率。

### 13.6 凍結抽樣、計數與待裁決驗收目標

**§4.5 的種子、分層、300／900、保守95%上界≤2.5%與全部現行計數定義一字不改。** 同一凍結 N、分層、原300基礎樣本與900有序序列，分別報告 v1-strict 與 v2-terminal-suffix-20261022；原 v1 結果與失敗保留，逐日記遷移原因。不得換難驗樣本、以新有效列重建母集合，或用擴樣／修後分母替換主上界。以下 n_error 對應 §4.5 的 e，避免與政策選項 (e) 混淆。

DV7 的 DV3 統計輸出依 V §15 固定五個分項，分母與層級（全批／完整日抽樣層）明列；本26日目的性樣本不能冒稱300／900隨機樣本。

| 分項 | 必報欄位／計數 |
|---|---|
| 原嚴格版本 | `n_error_v1,n_unresolved_v1,n_semantics_v1`，原逐欄原因與原上界，永久保留 |
| 來源選擇 | `n_terminal_source_selected_days,n_terminal_source_selected_hours,n_tail_trades,n_volume_corrected_e,n_price_corrected_e`；前兩項按選源日／小時去重，tail_trades為尾筆數，後兩項分別為 volume／OHLC 的 CORRECT 欄數、分 D／60 列報；列原件／候選值與 SHA，不混為整列 include |
| 政策錯誤／未決 | `n_error_policy,n_unresolved_policy,n_semantics_policy` 及逐欄原因；同日確認錯誤優先，e/u互斥，C2／C4／L1 等未決原因另列可重疊旗標。原 n_semantics 定義不變 |
| 來源真值風險 | `n_source_truth_unverified` 與日分母、原 C3 仍失敗的選源日集合；與政策 e/u 平行，不刪除已有錯誤。另報真值風險時以 `confirmed_error ∪ unresolved ∪ source_truth_unverified` 按日聯集去重，不能直接相加 |
| 可用性 | 各政策六欄 KEEP／CORRECT／UNRESOLVED 與整列 include／missing，日／小時分開；可用性增加不代表原錯誤率下降 |

採 (e) 後尾段小時屬**更正前錯誤、已更正**，計入 n_error，不轉 s、不歸零；可能只是 u 移到 e，未必減少 e+u。本批13個適用日各有 H.V 更正、共23小時，因此這13日均為政策條件下更正前錯誤日；8個日 V 原本 KEEP 不會消除同日小時錯誤。更正後仍 missing 的日依同日錯誤優先規則計 e，另保存未決原因。

**待 Operator 裁決（看到凍結抽樣結果後）：驗收門檻針對更正前錯誤率或更正後可用率。** 在裁決前不設預設值、不得以結果選定，也不得把更正後可用率冒稱既有≤2.5%已通過。先按未改的 §4.5 同時報原嚴格／新政策的更正前數字與上界、另報可用性；涉及此新目標的最終驗收結論保留待決，不自行放寬門檻或重解其含義。

### 13.7 26日固定預期：v1 與 Operator 選定 (e)

逐格轉錄 V 的 `E_26_DAY_TABLE.md` 中 v1 與「e：O照v1」兩欄；作 DV7 驗收的獨立固定預期，不由被驗實作生成預期。欄序 O/H/L/C/V/A；K=KEEP、R=CORRECT、U=UNRESOLVED、Ks=KEEP 且 D1 交易所 open 語義（不是新增 decision 列舉）。此表是來源報告預期，**本 PR 未實作／實跑 v2**。

| 標的 | 日期 | v1 O/H/L/C/V/A | v2 (e) O/H/L/C/V/A | v1 整列 | v2 整列 |
|---|---|---|---|---|---|
| BCHUSDT | 2020-12-14 | R/K/R/K/K/R | R/K/R/K/K/R | include | include |
| BCHUSDT | 2021-02-18 | U/U/U/U/U/R | U/K/K/K/K/R | missing | missing |
| BCHUSDT | 2021-02-28 | U/U/U/U/U/R | Ks/K/K/K/K/R | missing | include |
| BCHUSDT | 2021-03-03 | K/K/K/R/R/R | K/K/K/R/R/R | include | include |
| BCHUSDT | 2021-04-02 | U/U/U/U/U/R | Ks/K/K/K/K/R | missing | include |
| BTCUSDT | 2020-03-25 | K/K/R/K/K/R | K/K/R/K/K/R | include | include |
| BTCUSDT | 2021-02-12 | U/U/U/U/U/R | K/K/K/U/R/R | missing | missing |
| BTCUSDT | 2021-02-13 | U/U/U/U/U/R | Ks/K/K/R/R/R | missing | include |
| BTCUSDT | 2021-02-14 | U/U/U/U/U/R | K/K/K/R/R/R | missing | include |
| BTCUSDT | 2021-02-27 | U/U/U/U/U/R | U/K/K/K/K/R | missing | missing |
| BUZZUSDT | 2025-04-19 | U/K/K/R/R/U | U/K/K/R/R/U | missing | missing |
| DOTUSDT | 2021-11-29 | U/U/U/U/U/R | U/U/U/U/U/R | missing | missing |
| ETHUSDT | 2021-04-01 | U/U/U/U/U/R | Ks/K/K/K/K/R | missing | include |
| ETHUSDT | 2021-04-07 | U/U/U/U/U/R | Ks/K/K/K/K/R | missing | include |
| LINKUSDT | 2020-10-21 | K/K/R/K/K/R | K/K/R/K/K/R | include | include |
| LINKUSDT | 2021-03-03 | U/U/U/U/U/R | Ks/K/K/U/K/R | missing | missing |
| LINKUSDT | 2021-03-25 | U/K/K/R/R/R | U/K/K/R/R/R | missing | missing |
| LTCUSDT | 2020-10-21 | K/K/R/K/K/R | K/K/R/K/K/R | include | include |
| LTCUSDT | 2021-02-18 | U/K/K/U/R/R | U/K/K/U/R/R | missing | missing |
| LTCUSDT | 2021-03-17 | U/U/U/U/U/R | U/K/K/R/R/R | missing | missing |
| LTCUSDT | 2021-04-08 | K/K/K/R/R/R | K/K/K/R/R/R | include | include |
| LTCUSDT | 2021-04-10 | U/U/U/U/U/R | K/K/K/R/R/R | missing | include |
| PUMPBTCUSDT | 2025-06-03 | U/U/U/U/U/U | U/U/U/U/U/U | missing | missing |
| XEMUSDT | 2021-11-30 | U/U/U/U/U/R | U/U/U/U/U/R | missing | missing |
| XTZUSDT | 2020-10-21 | K/K/R/K/K/R | K/K/R/K/K/R | include | include |
| XTZUSDT | 2021-03-24 | U/U/U/U/U/R | Ks/K/K/K/K/R | missing | include |

總計 v1 **7 include／19 missing**，v2 **15 include／11 missing**；(e) 適用13日、23小時、55尾筆。13適用日的日 V 為8K／5R、C為7K／4R／2U、H及L各13K、O為10K／3U（K含D1）；A的13R全部沿 v1。23候選尾段小時僅19根價格與量全可決、4根仍缺漏；日線15 include 不能代替完整有效小時網格、暖機、上市 q 或其他下游可用性驗收。

DV7 測試另覆蓋：同日多尾段、跨多戳尾段、部分同戳子集／正差／空前綴拒絕、C2衝突、首末同戳多價、保留O後L1失敗、日量已含尾段仍KEEP、域外不回退(b)、未知信心證據不改判詞、原C3永久留存、同日錯誤優先及雙政策同一凍結樣本。原件 SHA、具體候選值與逐筆見證依 V manifest 定位；本表不能取代實際來源驗證。DV4仍須在DV7與下游完成後依§9最後整合。

## 勘誤二（2026-10-22，conductor 依 #241 審查補記實作對應）

本補記依已合入 main 的 PR #241 merge commit `1ea85a9a2128e2aaf9f70bf5bc462fd5c82a3527`（reviewed head `2b198b34c51f4d295177940dd15a2a37fa9fe30a`）實際程式核對；下列行號固定指該 main 版本。原規則、勘誤一及 §13 全部保留，本節只補 §8.4 與已核准規則的實作對應。PR #242 依續派以 merge 納入此 main，沒有 rebase；§13.1 初稿「其餘位元組不變」的比較基線隨此次授權更新為 `1ea85a9a`：本 PR 自行修改的程式仍只有 `STANDARD_SHA256` 一行，其他程式／測試差異均由 #241 合入。

1. **擴樣交接（§4.5 第8點、§8.4）**：DV1 `verify(..., sample_report_path=...)` 讀 DV3 既有 `sample_report.txt`；先驗原 `sample_plan_sha256`，逐層核對 year／tier／population_size／base_size。僅報告中 e 或 u 非零、且明列 `required_prefix=<該層 max_size> max_expansions=1` 的層，納入原凍結 `draws[base_size:max_size]`；與 base draws 聯集後進入 L3，不換樣、不改原 plan SHA 或主分母。報告須符合既有完整文字形狀；無額外 draws 時回 `EXPANSION_NOT_REQUESTED`。成功 bundle 可選含原 bytes 的 `sample_report.txt`，由 `verification.json.files` 與 handoff `files` 的 SHA／rows 綁定；DV3 消費時核對 files 中實際 bytes SHA。對應 `verification.py:738–800,956–964,994–1008,1029,1054–1067`；`verification_fetch.py:776–788,917–940`。擴樣入口與封存由 `256dcd4c6` 引入；`fb89a9ccd` 補缺失逐筆原件的未決證據處理，不另改擴樣規則。
2. **部分日診斷時間戳（§8.4 findings）**：可讀起點落在某 UTC 日內，而 DV-L2／DV-L4 日級 finding 原時間為該日午夜時，`timestamp` 改為可讀起點；既有 `details` 保存 `day_start=原日界`、`scope_start=可讀起點`、`scope_end=min(次日界,可讀終點)`，value 沿既有字串型別，不增頂層鍵。共用 finding 入口同樣涵蓋 POST_L2 診斷；不改 correction 的列身分，也不授權讀取午夜至可讀起點的行情。對應 `verification.py:243–251,917–948`；修正提交 `2b198b34c`。
3. **L2 涵蓋發現與成交額疑點日（§6.2.1–2）**：`PARTIAL`、`SCOPE_INCOMPLETE`、`MISSING_COUNTERPART`、`INVALID_INPUT`、`GAPPED` 及 `NO_VALID_HOURLY` 將所屬日納入 `flagged`，供疑點日的 DV-A 成交額選擇；這些涵蓋發現本身不加入 `price_days`，不單獨觸發逐筆裁決。該日若另有既有價格／量差異或屬實際抽樣 draws，仍按原入口進 L3。只有 flagged 而無 price_days 的日按原分支保留 L1 欄並執行 `_turnover(..., suspect=True)`。對應 `verification.py:468–502,1008–1033`；提交 `256dcd4c6`。未改價格／量／額的裁決條件。
4. **DV3 證據與統計（§4.5 第5點）**：完成的非 UNRESOLVED 逐筆裁決，除純 `L1_VALID`／`DV-L1` KEEP 且 coverage／order 皆 NOT_APPLICABLE 外，須有 L3 證據；完成裁決的原列綁定仍須成立。L3 缺證據時把 `EVIDENCE_INCOMPLETE` 按 `(symbol,UTC day)` 保存，不擴散至其他日；統計只納入實際評估的凍結 draws（base，以及 base e 或 u 非零時的已凍結擴樣序列）。同日已有認證完整的 CORRECT 優先計 e，否則證據不完整計 u；即使 e 優先，所屬已評估日的 `EVIDENCE_INCOMPLETE` 原因仍保留。原件缺失含 SourceRef 的 path／SHA 皆 null 表示法，不把該日移出分母。對應 `verification_fetch.py:436–469,718–755,812–853,884–889,918–940`；提交 `256dcd4c6`、`fb89a9ccd`、`9248ac79d`。這是既有錯誤優先及證據要求的實作，不新增抽樣門檻。

**與 §8.4.1／§13 的相容界線。** 可選文字報告沿既有 files 雜湊表，部分日資訊沿 findings.details，沒有新頂層鍵；涵蓋標記不新增逐筆來源選擇權；按日證據及 e 優先與 §13.6 一致。原凍結 plan／draws 不改，符合雙政策同一樣本的要求。main 的 v1 消費者仍核對 plan 與驗證政策相等，僅接受 v1 schema／嚴格 C3 證據；§8.4.1 已明定的 v1 計畫對 v2 驗證政策連結、v2 分類及證據驗證，由 DV7 實作，不能把本補記或 pin 更新當作現行工具已支援 v2。此次核對未發現須改動既有規則的契約衝突。

## 勘誤三（2026-10-22，conductor 依 #243 審查）

§8.4.1 的 `hour_classification` 固定列舉加入 `PARTIAL_SUBSET_UNDETERMINED`；其含義僅為「部分同戳子集的診斷搜尋超出固定資源上限而未判定」。上述原文與其他列舉全部保留。

此值與其他拒絕分類同樣不放行，不採該子集、不挑同戳先後，不改變任何採值或可用性結果；不得把未判定冒稱為 `NO_COMPLETE_SUFFIX` 或 `PARTIAL_TIMESTAMP_SUBSET`。

本次部分同戳子集診斷採精確整數縮放、最大公因數約分及位元集合動態規劃，固定資源上限為：狀態位元寬度 1,048,576（`MAX_PARTIAL_SUBSET_BITS`）、同戳群 4,096 筆（`MAX_PARTIAL_SUBSET_ITEMS`），以及輸入分子／分母與最小公倍分母各 4,096 位元（`MAX_PARTIAL_SCALE_BITS`）。任何一項超限即記上述未判定分類；這些上限只約束部分同戳子集的拒絕診斷，不約束已完整匹配的同戳群尾段。
