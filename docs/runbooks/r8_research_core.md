# R8 階段 2：研究工具核心使用說明

狀態：U4–U6 與 P4-D 已隨 PR #237 合入 main；本文件完成補充指令 §10 的記錄者收尾。
命令核對基線：`bddd96d56f86e07e6000a9e26f0bd8a93f66079a`（2026-10-22）。
交付：`P1-R8-S2-CORE-DOC-CLOSEOUT`；conductor 派工與把關，Codex 執行文件工作。
這是已發布工具的使用說明；研究派工、預登記、資料品質前檢與 Operator 裁決仍依 TODO 及契約辦理。

## 依據與資料流

- [P4 補充指令 §§3–16](../execution_plan/2026-10-20--r8-stage2-p4-research-core-addendum.md)：§3 時間／成本語義、§4 U4、§5 U5、§6 U6、§7 介面、§8 檢查、§9 方法論、§10 收尾，以及 §§12–16 的後續補充；衝突依各補充節的優先條款處理。
- [P4-D0 檢查紀錄](../execution_plan/2026-10-21--r8-stage2-p4-d0-check-record.md)：首次啟動失敗、修補與九案例；D 的策略端日線證據已由後續探針關閉。
- [P4-D 檢查紀錄](../execution_plan/2026-10-21--r8-stage2-p4-d-check-record.md)：A 段、B 段與 §9 的結案／量測限制；原始證據路徑與 SHA-256 以該紀錄為準。
- [命令列入口索引](../../helper_scripts/SCRIPT_INDEX.md#r8-階段-2-研究工具核心2026-10-22)。

```text
P3b 已凍結 U1 目錄 + 帳本預登記／可讀範圍
  → U4 materialize → materialization.json + lean/ + custom/ + source/ + 屬性覆蓋表
  → U5 lean_runner → run.json + events.jsonl + lean.log
  → U6 recompute → series／baseline／stress（檔案檢查入口）
  → U6 submit（只限 trial；自行重新物化、重算並產生產物）→ 研究帳本
```

U5 讀 U4 的 LEAN／custom 物化；U6 獨立讀 U4 的 `source/` 原始字串切片及合約屬性，不依賴 U5 的成交實作。
`submit` 的 `--u1` 只交給 U4 子程序重新物化，U6 不直接解析 U1 原檔。U6 重算會驗事件與記帳，但不重跑策略模型；
已提交試驗仍須依 §6 第 5 點由記錄者以 `verification` 重跑並比對決策等欄位。

## 執行前準備與帳本

以下命令都在已核對的 repository 根目錄執行。範例路徑、假說代號、試驗代號與 JSON 是占位值，
須替換為當次派工的已凍結輸入；本文件沒有建立研究假說、啟動容器或提交帳本。
Python 範例用 `python3`，核對時使用 `/usr/local/bin/python3`。

```sh
R8_WORK=/Users/ncyu/Projects/TradeBot/audits/r8-authorized-run
R8_U1=/Users/ncyu/Projects/TradeBot/data/r8-p3b
R8_LEDGER="$R8_WORK/research-ledger"
R8_HYPOTHESIS=replace-with-registered-hypothesis
R8_TRIAL=replace-with-begun-trial
R8_WINDOW=2020-01-01T00:00:00Z,2025-07-01T00:00:00Z
mkdir -p "$R8_WORK"
```

視窗範例是訓練段；實際研究的 `data_window`、擬合窗、計分窗與摺表取自預登記／試驗身份，不能直接沿用量測設定。
P3b 的 `tool_version` 為 `r8-public-data-2`，固定 manifest SHA-256 為：

```text
b6519a7b2f5eae4759612690790ddb6680db62aa4e723427f51c21a7d6257006
```

研究帳本與構造檢查用的驗證帳本必須分開。U4、U5 的 trial 查詢及 U6 submit 都要求帳本目錄與 `ledger_id.json` 已存在。
帳本 CLI 使用 `--out`（不是 `--ledger`）；已授權的預登記範例如下，`preregistration.json` 須符合帳本與 §9 的完整契約：

```sh
python3 -m program_code.research.r8_ledger.ledger \
  --out "$R8_LEDGER" preregister --record "$R8_WORK/preregistration.json"
```

建構帳本會建立目錄與 `ledger_id.json`；寫入追加鏈為 `preregistrations.jsonl`、`trials.jsonl`、`holdouts.jsonl`（按事件產生）。
U4 先依預登記物化，將物化 SHA、逐檔 SHA 與執行身份填入 `begin-trial.json`，再開始正式 trial：

```sh
python3 -m program_code.research.r8_ledger.ledger \
  --out "$R8_LEDGER" begin_trial --record "$R8_WORK/begin-trial.json"
```

此命令在下一節物化完成後、U5 執行之前使用。`preregister`／`begin_trial` 的 `--record` 是紀錄本身；
其餘帳本動作按 `--help` 使用具名參數物件。第二代計畫另依 `commit_trial_plan` 契約；不要把本文件當成解除 holdout 的授權。
`heads` 匯出前可能補寫中斷遺留的證偽判定，不能當純唯讀命令；已有鏈頭的唯讀核對用 `verify --record <heads.json>`。

## U4：依可讀範圍物化

```sh
python3 -m program_code.research.r8_engine.materialize \
  --u1 "$R8_U1" \
  --u1-manifest-sha256 b6519a7b2f5eae4759612690790ddb6680db62aa4e723427f51c21a7d6257006 \
  --ledger "$R8_LEDGER" --hypothesis "$R8_HYPOTHESIS" \
  --window "$R8_WINDOW" --out "$R8_WORK/materialized"
```

全部六個選項必填。`--out` 必須尚不存在、父目錄已存在，且在倉庫外。成功寫入：

| 產物 | 用途 |
|---|---|
| `materialization.json` | 身份、範圍、來源／輸出 SHA-256、缺漏、下架、限制及合約屬性 |
| `lean/cryptofuture/bybit/hour/<symbol>_trade.zip` | LEAN 小時線；小寫標的，內為 `<symbol>_trade_perp.csv` |
| `custom/{kline_day,funding,open_interest,turnover_hour,turnover_day}/<symbol>.csv` | 帶可知時刻的自訂資料 |
| `source/<U1 檔名去掉 .gz>` | 暖機加執行視窗內的原始列，保留標頭及科學記號等原字串，供 U6 重算 |
| `symbol_properties_overlay.csv` | bybit 永續合約屬性覆蓋列；不是改寫映像原表 |

標的取自 `selection.symbols`，額外加入 BTCUSDT 作基準；額外加入的 BTC 不自動成為策略標的。
視窗採 `[start,end)`；暖機取 `max_lookback_seconds`，不得少於 13 日，也不得跨進不可讀 holdout。
早於 2020-01-01 的暖機部分為空並記限制；資金費另包含恰在視窗終點的結算。
本版一律拒絕 holdout 物化，即使帳本已開啟。重新物化已開始的試驗時加 `--trial "$R8_TRIAL"`，
此時 `--window` 必須等於該試驗的 `data_window`，不能改窗。

構造資料使用另一份驗證帳本，且只有這條路徑加 `--validation`：

```sh
python3 -m program_code.research.r8_engine.materialize \
  --u1 "$R8_WORK/fixture-u1" --u1-manifest-sha256 "$R8_FIXTURE_MANIFEST_SHA256" \
  --ledger "$R8_WORK/validation-ledger" --hypothesis "$R8_VALIDATION_HYPOTHESIS" \
  --window "$R8_VALIDATION_WINDOW" --out "$R8_WORK/validation-materialized" --validation
```

三個 `R8_FIXTURE_*`／`R8_VALIDATION_*` 值須由凍結的構造設定取得；驗證帳本須先登記。
`--validation` 只放寬 P3b 固定 manifest 的身份常數，仍核對傳入 manifest 與逐檔 SHA、工具版本及可讀範圍；
輸出 `purpose="validation"`，禁止送入 trial／verification。EV-10～EV-12 雖以 U5 validation 執行，
用的是真實 P3b 資料，U4 **不加** `--validation`，仍用另建的驗證用帳本。

## U5：固定映像 LEAN 執行

映像固定為下列值，不能換成浮動 tag：

```text
quantconnect/lean@sha256:2657ed3355efb78d78bd0a5d4f126b01367a635e01bccd220b654d7742d182b6
```

本機使用既有 Colima Docker 環境。先以 `colima status`、`docker context show` 確認環境，
再以 `docker --context colima image inspect <上述映像>` 確認固定映像已在該環境；沒有映像或環境未就緒時回到環境準備，勿換映像繼續。
現行 Colima 掛載配置只使用 `/Users` 下的主機路徑：物化、輸出、模型根與 Python 暫存都要在 `/Users` 內。
這是本機配置要求，`lean_runner.mount()` 本身沒有強制 `/Users` 前綴檢查。

```sh
mkdir -p "$R8_WORK/tmp"
DOCKER_CONTEXT=colima TMPDIR="$R8_WORK/tmp" PYTHONDONTWRITEBYTECODE=1 \
python3 -m program_code.research.r8_engine.lean_runner \
  --config "$R8_WORK/run-config.json" \
  --materialization "$R8_WORK/materialized" --out "$R8_WORK/lean-out" \
  --ledger "$R8_LEDGER"
```

U5 的 `--materialization` 是**目錄**；`--out` 必須是尚不存在的倉庫外目錄。
`--config`、`--materialization`、`--out` 必填；`--ledger` 是 trial／verification 的既有帳本，validation 不需要此選項。
`--model-root` 可指定模型檔根目錄，缺省為 repo；本版外部 `model_artifact` 只供 validation 無摺表構造檢查，不能跳過正式擬合。
`TMPDIR` 必須在啟動 Python 前指定且已存在，因快照存於 `tempfile.gettempdir()/r8-lean-inputs/<hash>`，macOS 預設 `/var/folders` 不適合本配置。
不要把 TMPDIR 設在 repo 內，也不要掛載整個 U1 來源或整個帳本給 LEAN。

執行器自行組出 `docker run --rm --network none`，讀映像屬性表的輔助容器亦禁網路。
正式容器只掛必要的小時線、custom、已核對的 source 快照與設定／屬性／模型（唯讀），以及輸出目錄（可寫）。
CLI 沒有 `--mode`、`--image`、`--network` 或 `--symbols`；這些不能自行加成命令列選項。
成功組裝後輸出 `run.json`、`lean.log`；`events.jsonl` 由容器產生，啟動失敗時可能不存在。
入口以 run 的 `status` 決定退出碼：completed 為 0，failed 為 1；前置拒絕可能根本沒有 `run.json`，須保留 stderr。

### 設定、模式與來源綁定

`run-config.json` 依 §7.0，必填 `trial_id`、`materialization_sha256`、`code_commit`、`engine_commit`、`symbols`、
`initial_cash`、`leverage`、`gross_exposure_cap`、`decision_resolution`、`sharpe_frequency_seconds`、`warmup`、
`score_windows`、`folds`、`model_artifact`、`random_seed`、`strategy`、`algorithm`、`mode`、`cost`；只有 `fit_window` 是額外允許鍵。
數量／價格等設定用一般十進位字串，不把交易所原始資料可含科學記號的例外套到設定或 run。
`strategy.neighborhood` 為 `{"numeric": {軸名: [取值]}, "categorical": [軸名]}`，兩鍵均須存在；
每個 grid 點的鍵恰為全部宣告軸，數值軸取值嚴格遞增；完整範例見 §14.2。

| `mode` | 身份與用途 | 帳本提交 |
|---|---|---|
| `validation` | `trial_id=null`；`algorithm` 只能是 `{"path":"program_code/research/r8_engine/lean_algo/examples/fixed_schedule.py","class":"FixedSchedule"}`；`engine_commit=code_commit`；檢查用 | U6 submit 拒收 |
| `trial` | 帳本中已開始且未結束的試驗；purpose=research，身份／設定／範圍逐項一致；正式假說不得放在引擎目錄 | 僅 U6 submit 寫入結果 |
| `verification` | 記錄者重跑已結束試驗；同一身份，purpose=research；正式範例不適用 | U6 submit 拒收；只作獨立比對 |

兩個 commit 都要完整 40 位雜湊。`code_commit` 中的引擎、帳本與演算法檔必須與當下檔案逐位相同，相關來源不得有未提交改動。
trial／verification 的 `engine_commit` 還須是 `origin/main` 祖先，且引擎／帳本內容與 `code_commit` 相同；正式試驗身份由帳本綁定。
可用 `git rev-parse HEAD` 取得當次完整提交，按核准設定綁定；不能只把舊設定的雜湊改新就視為已授權研究。
EV-10 曾因舊設定仍綁修補前來源在 Docker 啟動前被拒；其後只改兩個 commit 欄位是當次 conductor 明示核准的差異，見 P4-D §9。

`visibility_probe` 只供 validation，作為類別軸宣告：從策略同一公開資料視圖讀 `kline_day`（例如 `close`）或 `open_interest` 的 `value`，
最後可見列的值對映數量。缺列／未映射會拋例外而非回傳預設值；探針標的以外照 schedule，無排程時目標 0。
日線在次日 00:00、持倉量在原時間戳加 4 小時才可見；探針與前視對照的凍結值見 §15 及 P4-D A 段。
trial／verification 不使用 FixedSchedule，也不接受驗證專用的 quantity 目標。

## U6：重算、序列、基準與壓力

U6 的 `--materialization` 是 **`materialization.json` 檔案**，與 U5 的目錄參數不同。
以下前四個子命令都必填 `--materialization`、`--run`、`--out`；只讀輸入並寫指定輸出，不寫帳本。
`--out` 除 baseline 為目錄外，其餘為檔案；先建父目錄，為每輪選不同路徑以保留歷史，CLI 會覆寫同名結果。

```sh
mkdir -p "$R8_WORK/u6"
python3 -m program_code.research.r8_engine.series recompute \
  --materialization "$R8_WORK/materialized/materialization.json" \
  --run "$R8_WORK/lean-out/run.json" --out "$R8_WORK/u6/recompute.json"
python3 -m program_code.research.r8_engine.series series \
  --materialization "$R8_WORK/materialized/materialization.json" \
  --run "$R8_WORK/lean-out/run.json" --recompute "$R8_WORK/u6/recompute.json" \
  --out "$R8_WORK/u6/series.json"
python3 -m program_code.research.r8_engine.series baseline \
  --materialization "$R8_WORK/materialized/materialization.json" \
  --run "$R8_WORK/lean-out/run.json" --out "$R8_WORK/u6/baselines"
python3 -m program_code.research.r8_engine.series stress \
  --materialization "$R8_WORK/materialized/materialization.json" \
  --run "$R8_WORK/lean-out/run.json" --out "$R8_WORK/u6/stress.json"
```

- `recompute`：產生事件／現金重算報告，讀 `recompute_passed`、`differences`、`max_difference`、`max_cash_residual_ulps`、`first_unexplained_cash_residual_t`。
  CLI 退出碼 0 只代表報告寫出，不代表 `recompute_passed=true`；合法 failed run 即使前綴一致，也不是通過的 completed run。
- `series`：另必填 `--recompute`，會再次重算並要求報告與當次輸入一致，不能手改 PASS。
  輸出 `series.json` 及 **`series.json.sidecar.json`**，含產生／提交期數與來源雜湊；失敗試驗依契約填完整網格，不丟棄失敗。
- `baseline`：寫 `baselines/beta_matched_btc_v1.json`、`baselines/btc_perp_hold_v1.json`。
- `stress`：固定決策，以滑價 1／2／3 倍及 2 倍滑價加壓力費率重算，並求損益兩平區間；不能從 CLI 改情境。
  決策不隨壓力下部位／權益重新產生，報告保留此近似；輸出不等於策略研究或獲利成立。

baseline／stress 可單獨輸出，並不代替 recompute 的通過判定。交易所來源的 K 線、資金費、持倉量、成交額與合約屬性以 Decimal 精確解析科學記號；
其他設定、目標、run／帳本值仍維持嚴格一般小數檢查，NaN／Inf 及無法解析值拒絕。

## U6 submit：唯一的研究結果提交路徑

只對已授權且已 `begin_trial` 的研究試驗執行；前述 validation 範例不能接這一步。

```sh
python3 -m program_code.research.r8_engine.series submit \
  --ledger "$R8_LEDGER" --trial "$R8_TRIAL" --u1 "$R8_U1" \
  --run "$R8_WORK/lean-out/run.json" > "$R8_WORK/submit-receipt.json"
```

四個參數都必填，沒有 `--out`、`--status`、`--series`、`--baseline` 或壓力檔輸入。
命令拒收 validation／verification、不同 trial、已結束試驗、holdout_falsification、執行早於 begin_trial、來源或身份不符。
它以固定 P3b SHA 呼叫 U4 重新物化，自行產生 recompute／series／baseline／stress／sidecar，檢查完成後才寫
`<ledger>/u6_artifacts/<sha256>`（以內容雜湊命名，無副檔名）並呼叫 `finish_trial`；stdout 為帳本回傳 JSON。
completed run 重算不通過即拒絕；failed run 則依失敗前綴及補零規則保留試驗，不能刪掉或改寫成 completed。
樣本外失敗的 `operator_stop_required` 按報告及契約交 Operator 處理，不由工具自行批准下一次試驗。
不得用帳本裸 `finish_trial` 繞過 U6 的獨立計算。

## 驗收紀律與殘差判定

每個構造驗收先凍結設定、手算預期與 SHA-256，再執行；保留失敗及其後修補／重跑的不同目錄。
預期不能取自被驗的 U5／U6 自己輸出。記錄映像、來源提交、演算法檔雜湊與 Docker argv；
LEAN completed、獨立預期相符、沒有未解釋殘差及 U6 重算通過是分開核對的條件。

依 §16，時間步現金殘差 `r_t = LEAN JSON 讀回現金 − steps[].cash`，後者是框架預期現金。
非零 cash 的 `e_t = Decimal(cash).adjusted()`，`ulp_t = max(10^(e_t−27), 10^−28)`；cash=0 時 ulp=10^−28。
`abs(r_t) <= 100 * ulp_t` 是表示誤差，超過才是未解釋殘差；結束殘差用最後時間步現金。
`unexplained_cash_residual.per_step` 仍記錄所有非零殘差，不能刪除容差內值；`total` 只記錄、不判定。
U5 以第一個未解釋殘差時刻記 failed／lean_error；全在容差內仍以容器結果為準，不能掩蓋其他失敗。
U6 獨立計界限並報最大 ulp 倍數。§9.8.8 的數值比對容差另行適用，`differences=[]` 不必然表示 `max_difference="0"`。
既有 EV-10 的 48 筆殘差均為 1 ulp，最大重算數值差約 4.47e-24，屬已核對的接受結果，不是省略誤差。

## 已知限制與後續

| 項目 | 已有證據與使用限制 |
|---|---|
| EV-12 100 標的 | runner 牆鐘 61.179 秒（LEAN 60.706 秒），容器觀測峰值 3.731 GiB，物化 267.756 MiB；completed，但 Python 關閉階段另有 10 秒逾時訊息，不稱無異常完成 |
| EV-12 1,087 標的 | 現行 Docker VM 約 7.74 GiB／4 CPU，初始化未完成即記憶體保護停止，0 steps、exit143、oom_kill=0；僅部分量測，不是觀測到 OOM kill，也沒有全標的完整執行數字 |
| 量測可比性 | 不同輪與清單、採樣峰值可能為下界；20×16 使用量測用 84 日擬合，不是正式 91 日摺表，不作嚴格擴展性比較 |
| 合約屬性 | 取數當時的 instruments-info，不證明歷史值不變；PR #235 只將缺少／None／空白 minNotionalValue 記 0 並列 limitations，其他非法值不放寬 |
| BCHUSDT | 2020-12-14 日線 open／low=0；U4 正價檢查拒絕。只在 EV-12 量測排除，正式研究如何處理仍待 Operator 裁決，不得自行刪列或把量測排除變成通則 |
| 可見性／研究 | visibility_probe 僅供驗證；U6 記帳相符本身不能證明策略沒有前視。資料品質前檢與研究派工見 TODO `P1-R8-S2-REPORT-TOOLS`／P5；holdout 仍未啟用 |

本輪 1,087 標的物化有 22 個 minNotionalValue 空字串記為 0：
`1000000VINUUSDT`、`ANCUSDT`、`BITUSDT`、`BTTUSDT`、`BUSDUSDT`、`COCOSUSDT`、`CREAMUSDT`、`FTTUSDT`、
`GSTUSDT`、`IGUUSDT`、`KEEPUSDT`、`LUNAUSDT`、`MCUSDT`、`MULTIUSDT`、`RAYUSDT`、`SRMUSDT`、`STRAXUSDT`、
`TOMOUSDT`、`USTUSDT`、`WSMUSDT`、`YFIIUSDT`、`ZBCUSDT`。這是該物化的限制清單，不是所有未來來源的固定白名單。

P4-D 的 EV-1～EV-11、EV-13、EV-14 通過條件已滿足，EV-12 只量測；上述結果不構成假說研究、獲利、部署或交易效果結論。

## 本文件的命令核對

2026-10-22 在上述 main 基線逐一執行 U4、U5、U6 頂層及 `recompute`／`series`／`baseline`／`stress`／`submit` 的 `--help`，
另核對帳本 `--help`，九次均退出 0；並讀取 parser、物化範圍／輸出、來源身份、Docker argv、submit 及產物寫入原始碼。
核對證據在倉庫外 `audits/2026-10-22-r8-core-doc-closeout/cli-help-manifest.json` 與各 help 原文。
本次只驗文件與介面，不重跑 LEAN 或真實資料；歷史實跑證據仍由 P4-D0／P4-D 檢查紀錄承載。
