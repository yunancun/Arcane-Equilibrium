# R8 階段 1 後續小單元派工指令

| 項目 | 內容 |
|---|---|
| 文件性質 | 六個互相獨立的小工程單元的派工指令。不是授權文件；是否可派發以 [TODO](../../TODO.md) 的對應各列為準 |
| 日期 | 2026-10-12（Asia/Shanghai）記錄；Operator 的指示於 2026-10-11 發出 |
| 依據 | Operator 指示：後續項拆成小單元，一次交給原實作的執行者（路線事件 `RH-20261012-01`）；[R8 修訂一](../decisions/2026-10-08--r8-amendment-1-first-loop-on-native-replay.md)（已採納）§5 階段 1 |
| 前提 | 階段 1 的四項回放修補已在 main 上（PR #206，merge commit `a71b3f5b6`）。設計、審查結果與已知限制見 [runbook](../runbooks/r8_stage1_replay_patches.md) |
| 內容來源 | runbook「已知限制與後續項」，加上 PR #206 自動審查提出的七點（六點併入下列單元，一點列為已知限制，見 §5） |
| 不在範圍 | 階段 2 及以後。Linux 主機於 2026-10-11 離線（Operator 告知），階段 2 暫不進行 |

## 1. 為什麼拆成小單元

上一個交付把四項修補放在一起，實作約四小時。治理工具有兩個計時器，過期後公開工具都無法恢復：

- **寫入租約**：預設 7200 秒，最長 86400 秒。續租只在到期前有效；開工提交之後就不能重新取租。
- **受控審查時段**：從該交付**第一次**審查呼叫起算，該交付所有的審查（含修補後的複核）都要在同一時段內完成。
  時段長度由預算等級決定，standard 為 3600 秒，narrow 為 1800 秒。

所以這次每個單元都小到可以在審查時段內完成全部審查，並且彼此獨立，任何一個停止都不影響其他單元。

## 2. 共同規則（六個單元都適用）

### 2.1 身分與基線

1. 每個單元是一個獨立的交付。`work_item_id` 與 `lane_id` 都用該單元標題所列的名稱。這些名稱由記錄者擬定，依據是 Operator 的明示指示；
   不要自行改名，也不要為同一單元另立第二個名稱。
2. 先 `git fetch origin`。六個單元都從**同一個** main commit 開工，就是含有本文件的那個 main；把完整 commit 記下來，各單元的 task contract 與 context 都綁它。
   main 上找不到本文件，或找不到 `rust/openclaw_engine/src/replay/stage1.rs`，就停止並回報 `NEEDS_CONTEXT`。
3. 各單元改動的檔案互不重疊（見各單元的「可改檔案」）。每個單元一個自己的 worktree、一個自己的 feature 分支、一個自己的 PR。
   不要把單元疊在一起，也不要合成一個 PR。
4. 依序執行：U1、U2、U3、U4、U5、U6。U1、U2、U3 必須在階段 3 之前完成，排在前面。
   一個單元停止或失敗時，保留它的 patch 與停止原因，然後繼續下一個單元。停止的單元不得另立名稱重來。

### 2.2 不要碰的檔案

- `TODO.md`、`docs/` 下的任何檔案（含 runbook 與路線歷史）、`helper_scripts/SCRIPT_INDEX.md`、`CHANGELOG.md`。
  各單元在 TODO 的列已由記錄者登記；合併之後的文件收尾也由記錄者處理。證據寫在 PR 說明與你的回報裡。
- 既有的測試檔。每個單元的新測試放在該單元指定的**新**測試檔裡。
  例外只有該單元「可改檔案」明列的既有測試檔（U5、U6 各有），而且只能做該單元寫明的修改。
- 各單元「可改檔案」以外的任何檔案。需要改到清單外的檔案才能完成時，該單元停止並回報，不要擴大範圍。
- 治理源碼、任何准入帳本、租約或審查狀態檔。

### 2.3 計時器

1. **租約**：取得時指定 `--ttl-seconds 86400`。每次提交之前與發布之前各查一次 `status`；剩餘時間不足一半就先續租。
2. **審查時段**：在第一次審查呼叫之前，把該單元的實作與你自己的驗證全部做完並提交。之後連續送審，不要在兩次審查之間做別的事。
3. 任務事實如實填寫。記錄者以這些單元的範圍試跑過路由（單一語言、`implementation`、風險與不確定性皆為 medium）：得到的流程是
   實作 → 代碼審查 → 測試驗證，standard 等級，沒有排在實作之前的審查。只寫測試的單元（`task_shape=test`，須搭配 `side_effect_class=local_test`）得到的是 測試撰寫 → 代碼審查。
   你實際得到的流程若把某個審查排在實作之前，照做，但要先評估：審查時段從那一次呼叫起算，實作與之後所有審查都必須在裡面完成。
   評估後認為放不進去，就在送出那一次審查**之前**停止並回報，不要讓時段在工作途中到期。
4. 每個審查節點至多兩次呼叫：初審一次，修補後複核一次。複核的提問必須與初審逐字相同，
   所以提問要用檔案路徑指向受審內容，並寫明「讀當次提交中的版本」；不要把設計或程式內容直接寫在提問裡。
5. 審查採「一批審查、一次集中修補、一次原阻塞項複核」。複核仍不通過，該單元停止。
6. 修補會改變受審的內容：下游審查（測試驗證）提出阻塞而修補之後，上游審查（代碼審查）先前的通過不再對應目前的內容，
   必須先複核上游，再複核下游。兩個節點合計最多四次呼叫，每次上限 900 秒，四次都用滿就已經是整個 standard 時段。
   所以修補要小、要快；第一輪兩次審查若已用掉一半以上的時段，修補後的複核多半放不進去，這時在送出複核**之前**停止並回報。

### 2.4 不變量

- 沒有新欄位的舊 manifest 與舊 fixture，回放報告逐位元組不變（只排除 `generated_at_ms` 那一行）。每個改到 Rust 的單元都要以實跑確認並留下輸出。
- 既有測試一律不改、不刪、不略過。開工前的基線（含階段 1 修補的 main，本機 Mac，離線）：
  回放單元 117、原七組回放整合 35、`replay_stage1_acceptance` 21、`m3_emitter_replay_forbidden` 3、`replay_runner` binary 單元 9、
  `test_stage1_offline_tools.py` 40，皆 0 失敗。先重現這組數字，重現不了就停。
- 不碰 production 熱路徑：引擎主流程、intent processor、`strategies/`、`Strategy` trait、Guardian、Decision Lease、Control API 路由。
- 不取數，不發任何網路請求；不連 Linux、資料庫、Demo 或 live；不部署；不啟動階段 2。
- 新增與修改的註釋用中文；不硬編機器路徑；不提交任何金鑰或私有 fixture。測試需要的金鑰在測試的暫存目錄內產生。
- 這台開發機上 `~/.cargo/bin/cargo` 的捷徑失效，遇到時把 `~/.rustup/toolchains/<toolchain>/bin` 加進 PATH。Rust 測試加 `--features replay_isolated --offline`。
  執行 `replay_runner` 需要環境變數 `OPENCLAW_REPLAY_MAC_NO_PRIVATE=1`。

### 2.5 交付

- 每個單元完成審查後推送自己的分支並開 PR，標題以 `R8 S1F U<n>` 開頭。不直接推 main，不自行合併。
- PR 說明寫明：改了什麼、測試的四個數字（passed／failed／skipped／error）、審查結論、未驗證的範圍。
- 跑不了或跳過的檢查要明說，不要寫成通過。本機結果不要寫成 Linux 或 CI 的結果。

## 3. 階段 3 之前必須完成的三個單元

### U1 `R8-S1F-ANALYTICS-20261012`：分析工具的回放結束時間與報告狀態

**為什麼**：回放結束時還有未平倉部位時，結算點只檢查到最後一根 K 線的**開盤**時間。最後一根 K 線的收盤恰為結算時刻
（例如整日資料結束於 00:00 UTC）不會被標記，而工具仍回報 `crossing_check_exact=true`。另外，中途中止的回放也會寫出報告，
工具現在照樣算出來回交易與資金費欄位。階段 3 的增益閘門要讀這些輸出。

**可改檔案**：
`program_code/exchange_connectors/bybit_connector/control_api_v1/replay/offline_analytics.py`、
`helper_scripts/replay/replay_local.py`、
新增 `program_code/exchange_connectors/bybit_connector/control_api_v1/tests/replay/test_stage1_offline_analytics_followup.py`。

**要求**：
1. 新增一個可選輸入「K 線長度（毫秒）」，CLI 與函式都要有，名稱由你定。有給時，未平倉部位的持倉區間結束於
   報告記錄的結束時間加上一根 K 線長度，也就是最後一根 K 線的收盤時間；輸出記下所用的結束時間與來源。必須是正整數，否則報錯。
2. `funding.crossing_check_exact` 的語意收緊為：時間基準為 `execution_event_open`，**並且**（沒有未平倉部位，或已給 K 線長度）才為真。
   有未平倉部位而沒有給 K 線長度時為假。舊時序（`bar_open_label`）一律為假，不因為給了 K 線長度而變成真。
3. 呼叫者給的結束時間與報告記錄不同即拒絕的現行規則不變。
4. 報告裡的 `stage1` 若存在但不是物件（例如 `null`），以 `ValueError` 拒絕，讓 CLI 以結束碼 2 與一行訊息結束，不拋出未處理的例外。
5. 報告的 `result.status.kind` 存在而不是 `completed` 時，以 `ValueError` 拒絕。沒有這個欄位的舊報告照常處理。
6. 已完成來回交易的判定、對帳與其他輸出不變。

**驗收**（每一條都要有會在行為錯誤時失敗的測試）：
- 最後一根 K 線開盤於 23:59:00、仍有未平倉部位、K 線長度 60000：`open_position_crossing_count` 為 1，`funding_crossed` 為真，`crossing_check_exact` 為真。
- 同一份報告不給 K 線長度：`crossing_check_exact` 為假。
- 沒有未平倉部位的 `next_symbol_open` 報告：不論有沒有給 K 線長度，`crossing_check_exact` 為真。
- 舊時序的報告給了 K 線長度：`crossing_check_exact` 仍為假。
- K 線長度為 0、負數或非整數：報錯。`"stage1": null`：`ValueError`；經 CLI 時結束碼為 2。
- 狀態為 `aborted_forbidden` 的報告被拒絕；沒有狀態欄位的報告照常分析。
- 既有 40 項測試不改而通過。

### U2 `R8-S1F-REPLAY-GUARDS-20261012`：回放擴充的三項防護與穩健性

**為什麼**：前三點是自動審查指出的證據完整性與偷看問題。後四點是代碼審查留下、不影響目前結果但會在誤用或中途失敗時出問題的缺口。

**可改檔案**：
`rust/openclaw_engine/src/replay/stage1.rs`、`rust/openclaw_engine/src/replay/runner.rs`（只在確有需要時）、
`rust/openclaw_engine/src/replay/fixture_loader.rs`（只新增，不改既有函式的行為）、
`rust/openclaw_engine/src/bin/replay_runner.rs`、
新增 `rust/openclaw_engine/tests/replay_stage1_guards_acceptance.rs`。

**必須完成**：
1. **fixture 雜湊**：manifest 帶有 `parameter_provenance.fixture.sha256` 時，`replay_runner` 對實際用來執行的 fixture 位元組計算 SHA-256，
   與該值不符即拒絕執行。沒有這個欄位的 manifest 不受影響。現在這個雜湊只被簽名，從未與實際載入的資料比對。
   fixture 現在被讀兩次（載入器一次，`Stage1Config::from_fixture` 一次）。雜湊、事件解析與擴充欄位解析必須來自**同一次**讀到的位元組；
   為此可以在 `fixture_loader.rs` 新增從已讀入的位元組解析的函式。做法寫在 PR 說明裡。
2. **全域時間順序**：`next_symbol_open` 模式下，除了既有的「同一標的時間嚴格遞增」，再要求整份 fixture 的時間不遞減，否則拒絕。
   多標的 fixture 若按標的分組排列，現在會被接受；較早的事件會在較晚的事件已改變帳戶之後才做風控評估。
3. **覆寫與策略**：manifest 帶有 `parameter_overrides` 而沒有 `strategy` 時必須拒絕。
   現在這種 manifest 會走合成路徑，報告卻回寫了沒有套用到任何策略的覆寫。
   這是 `replay_runner.rs` 內一個獨立的判斷；擴充是否啟用的既有判斷不含這個欄位，不要把它掛在那上面。

第 1 至 3 點都在 `replay_runner` 的 `main` 裡，測試需要實際啟動編好的 binary：整合測試可以用 Cargo 提供的 `CARGO_BIN_EXE_replay_runner`，
測試檔開頭加 `#![cfg(feature = "replay_isolated")]`，manifest 在測試內以函式庫的簽名器簽名，金鑰在暫存目錄產生。

**穩健性**（其中某一項做不到時，那一項列為未完成並說明，其餘照做）：
4. `extend_report` 先寫同目錄的暫存檔，再以改名取代原檔。中途失敗時原報告保持完整。
5. 函式庫層的三個防護，目前只有經 `replay_runner` 的路徑有擋：啟用 `next_symbol_open` 之後再設定非零延遲；啟用擴充而沒有策略 adapter；
   擴充設定的筆數與 fixture 不符。三種都必須以錯誤結束，不得 panic，也不得靜默繼續。
   沒有 adapter 與筆數不符可以在 `with_stage1` 回 `Err`（現有呼叫都在掛上 adapter 之後才呼叫它）。
   「之後再設定非零延遲」的設定函式回傳的不是 `Result`，只能在 `execute` 擋；不得借用禁用路徑類的錯誤來表達設定錯誤。
   既有公開函式的簽名與既有公開結構的欄位不變，未啟用擴充時的行為不變。
   某一種必須新增公開的列舉值或改動簽名才能做到時，那一種列為未完成。
6. `next_symbol_open` 模式下所有零數量記錄（`unsupported_nonmarket`、`selector_veto`、`pending_open_exists`、`reduction_position_changed`、`close_no_position`）的
   `price` 欄一律為 0，與到期記錄一致。現在有的填訊號那一根的收盤價，有的填下一事件的開盤價。
   `current_bar_close` 模式不變，所以產生這些記錄的函式要依模式分支。
7. 以測試固定現行行為，不改行為：`next_symbol_open` 下同一事件發出 Close 與反向 Open 時，Close 在下一事件成交，
   Open 以 `reduction_position_changed` 被拒，不會開出反向的新倉。

**驗收**：
- 第 1 點：雜湊相符可執行；fixture 改動一個位元組後被拒；沒有該欄位的舊 manifest 照常執行。
- 第 2 點：按標的分組的多標的 fixture 在 `next_symbol_open` 下被拒；同一份 fixture 在缺省時序下行為不變。
- 第 3 點：帶覆寫而沒有 `strategy` 的 manifest 被拒，沒有寫出聲稱已覆寫的報告。
- 第 4 至 7 點：每一項一個測試（第 5 點三種誤用各一個）。第 4 點要證明寫入失敗時原檔位元組不變。
- 2.4 的逐位元組檢查通過；既有測試不改而通過。

### U3 `R8-S1F-MANIFEST-TOOL-20261012`：manifest 工具的兩項輸入檢查

**為什麼**：自動審查指出，工具會替錯誤的資料層標示簽名，也擋不住以硬連結指向輸入檔的輸出路徑。

**可改檔案**：
`program_code/exchange_connectors/bybit_connector/control_api_v1/replay/offline_manifest.py`、
新增 `program_code/exchange_connectors/bybit_connector/control_api_v1/tests/replay/test_stage1_offline_manifest_followup.py`。

**要求**：
1. fixture 外層有 `source` 欄位時，與 `data_tier` 核對：`data_tier` 為 S2 時，`source` 必須以 `s2_` 開頭
   （現有的值有 `s2_bybit_public` 與 `s2_bybit_public_full_chain`）；`data_tier` 為 S3 時，`source` 不得以 `s2_` 開頭。
   不符即拒絕，不產生 manifest。現在合成資料可以被標成公開行情並簽名。
   沒有 `source` 的 fixture 維持現行行為：`replay_runner` 的載入器要求這個欄位，這種 fixture 本來就無法執行，
   而既有測試用的就是沒有 `source` 的 fixture，它們必須不改而通過。不要在簽名主體新增欄位。
2. 輸出路徑已存在時，以檔案系統身分（同一個 inode）而不是路徑字串，判斷它是否就是金鑰、fixture、快照或設定檔；是就拒絕。
   現在以硬連結指向金鑰的輸出路徑會通過檢查，寫入時把金鑰截斷。
3. 其他行為不變，包括來源路徑的記法、簽名與 canonical 的重用、三個環境設定檔分開。

**驗收**：
- S2 配 `s3_synthetic` 被拒；S3 配 `s2_bybit_public` 被拒；S2 配 `s2_bybit_public`、S2 配 `s2_bybit_public_full_chain`、S3 配 `s3_synthetic` 成功；
  沒有 `source` 的 fixture 與現在一樣成功。
- 輸出路徑是金鑰、fixture、快照的硬連結時被拒，且被指向的檔案位元組不變。
- 既有 40 項測試不改而通過。

## 4. 可以稍後完成的三個單元

### U4 `R8-S1F-BINARY-TESTS-20261012`：經 `replay_runner` 的測試（只寫測試）

**為什麼**：現有測試都在函式庫層。`replay_runner` 的 `main` 新增了每次都會執行的接線（重讀 fixture、回寫報告），目前只有實跑證據，沒有倉庫內的測試。

**可改檔案**：新增 `rust/openclaw_engine/tests/replay_stage1_binary_acceptance.rs`；需要小型 fixture 時放在新目錄 `rust/openclaw_engine/tests/fixtures/replay_stage1/`。
不改任何非測試檔，包括 `Cargo.toml`。

**要求**：測試實際啟動編好的 `replay_runner`，manifest 在測試內以函式庫的簽名器簽名，金鑰在暫存目錄產生。
1. 缺省路徑不啟用擴充：下列沒有新欄位的 manifest 都能跑完，報告沒有 `stage1`、`parameter_provenance`、`parameter_overrides` 三個鍵，
   同一份輸入跑兩次的報告只在 `generated_at_ms` 一行不同：（甲）沒有 `strategy` 的合成路徑；（乙）帶 `strategy`、`strategy_params` 與 `risk_overrides`；
   （丙）帶執行延遲；（丁）資料層 S3。`full_chain` 與多標的帶報價的情形，能用既有測試輔助組出來就加，組不出來就在回報裡列為未涵蓋。
2. 啟用擴充而沒有 `strategy`：結束碼非零，訊息指出需要明示策略。
3. fixture 帶不合法的選擇器（例如係數 2，或明確的 `null`）：結束碼非零。
4. manifest 帶 `strategy`、`parameter_provenance` 與 `parameter_overrides`：報告內後兩者與輸入相等，並有 `stage1` 區塊。
   `parameter_provenance.fixture.sha256` 要填該 fixture 的正確雜湊，讓這個測試在 U2 合併前後都成立。
5. 簽名後竄改 manifest 主體：驗簽失敗，結束碼非零。

測試取不到編好的 binary 路徑、或必須改 `Cargo.toml` 才能做到時，這個單元停止並回報所需的最小變更。

**驗收**：新測試全數通過，且每一條在對應行為錯誤時會失敗；沒有任何非測試檔被改；既有測試不改而通過。

### U5 `R8-S1F-SYMBOL-AUDIT-20261012`：讓回放的禁用符號稽核有實質偵測力

**為什麼**：`helper_scripts/ci/replay_runner_symbol_audit.sh` 稽核的是 release binary。release 已剝除符號，在 macOS 上只掃到 1 個符號，
而且符號數為 0 時也照樣回報通過。`helper_scripts/ci/ibkr_g4_symbol_audit.sh` 已經處理過同樣的問題，可以對照。

**可改檔案**：`helper_scripts/ci/replay_runner_symbol_audit.sh`，以及它既有的模擬測試 `helper_scripts/ci/test_replay_runner_symbol_audit.sh`。
後者現有五個案例；加上定位符號檢查之後，「乾淨符號清單」的案例需要補上定位符號才會通過。可以補模擬資料與新增案例，不得刪除或放寬既有案例的斷言。

**要求**：
1. 稽核保留符號的建置產物（未剝除），掃描完整的符號表，包含非對外符號。
2. 符號表是空的、已剝除，或找不到能證明符號表有內容的定位符號時，以結束碼 5 結束（與 IBKR 的稽核腳本一致；2、3、4 已有用途），不得回報通過。
3. 提供正向對照：能證明禁用樣式確實會命中（例如一個自我測試模式，餵入含禁用名稱的符號清單必須回報命中）。
4. 既有的結束碼意義保留；禁用樣式清單不放寬。macOS 與 Linux 兩個分支都要處理；本機只能驗證 macOS，Linux 分支標為未驗證。

**驗收**：在本機對目前的 main 執行，結果是通過，掃到的符號數與未剝除的 binary 相符（數千以上，不是 1）；
對已剝除的 binary 執行，結果是結束碼 5；正向對照回報命中；模擬測試全數通過。把這些執行的輸出留作證據。
未剝除的產物在目前的 main 上若有禁用樣式命中，貼出命中清單並停止這個單元，不要放寬樣式，也不要改動被命中的程式。
`helper_scripts/ci/README.md` 與 `helper_scripts/SCRIPT_INDEX.md` 對這支腳本的描述會因此過時；兩者不在可改清單內，由記錄者在文件收尾時更新。

### U6 `R8-S1F-CI-REPLAY-20261012`：讓 GitHub CI 執行回放測試

**為什麼**：CI 設定裡沒有 `replay_isolated`，回放的測試只在本機執行過。日後有人改到回放，CI 不會發現。

**可改檔案**：`.github/workflows/ci.yml`、`helper_scripts/ci/classify_ci_changes.py`，以及兩個既有測試檔
`tests/ci/test_classify_ci_changes.py` 與 `tests/ci/test_github_ci_workflow_static.py`。
這兩個測試檔有三處斷言窮舉了全部的分類輸出，新增輸出之後必須把新的那一項補進去：
前者兩處（全部為真的那個字典，以及 CLI 寫出的輸出行清單，行的順序跟分類器內輸出的排列順序走），後者一處（job 與輸出的對照表）。
除了補這一項與新增案例，不得更動既有斷言。

**要求**：
1. 比照既有做法（分類器輸出加上受它控制的 job，例如 `stock_etf`）：分類器新增一個輸出，在改動碰到回放相關路徑時為真。
   路徑至少涵蓋 `rust/openclaw_engine/src/replay/`、`rust/openclaw_engine/src/bin/replay_runner.rs` 與 `rust/openclaw_engine/src/bin/replay_runner/`、
   `rust/openclaw_engine/tests/` 下以 `replay_` 開頭的檔案與 `m3_emitter_replay_forbidden.rs`、`helper_scripts/replay/`、
   `program_code/exchange_connectors/bybit_connector/control_api_v1/replay/` 下以 `offline_` 開頭的檔案、
   `program_code/exchange_connectors/bybit_connector/control_api_v1/tests/replay/` 下以 `test_stage1_` 開頭的檔案。
2. 新增一個只在 Linux 標準 runner 上執行的 job，比照 `stock_etf` 的條件寫法（只在 `pull_request` 事件、且該輸出為真時執行），執行回放的 Rust 測試與 Python 測試。
   Python 步驟要安裝 pytest 與 pydantic（工具的匯入鏈需要）。
   以樣式選取測試，讓其他單元新增的測試檔自動納入：回放單元測試、所有以 `replay_` 開頭的整合測試、`m3_emitter_replay_forbidden`、
   `replay_runner` binary 單元測試，以及 `tests/replay/` 下以 `test_stage1_` 開頭的 Python 測試。
   不新增 macOS job。設定逾時上限。沿用檔案內既有的 Rust 快取與設定步驟，不另寫一套。
3. 不改動既有 job 的觸發條件與內容。不把禁用符號稽核接進這個 job（那是 U5 合併之後的事，由記錄者另行安排）。

**驗收**：`tests/ci` 的分類器測試新增對應案例並全數通過，既有案例不改而通過；`ci.yml` 語法有效。
新 job 本身只能由這個 PR 自己的 CI 執行來驗證：開 PR 之後讀一次檢查結果寫進回報，仍在執行就照實寫「尚未完成」，不要輪詢等待。
改動 `ci.yml` 與分類器會讓這個 PR 的全部 CI 項目都執行。**這個 PR 以 draft 開啟**，draft 不會執行計費倍率高的 macOS 項目；由 Operator 決定何時轉為正式。

## 5. 沒有列為單元的一點

PR #206 的自動審查另指出：manifest 工具對呼叫者快照只做淺層檢查，結構不對的快照要到 `replay_runner` 反序列化時才被拒，
工具因此可能簽出一份跑不起來的 manifest。這一點不列為單元：參數結構的權威是 `replay_runner` 的型別，在 Python 另寫一份結構檢查會與它漂移；
失敗發生在執行前，不會產生錯誤的結果。它記為已知限制，由記錄者在文件收尾時寫進 runbook。

## 6. 回報格式

六個單元全部處理過之後，一次回報：

- 一張總表：每個單元的 `work_status`、`gate_verdict`、`disposition`、PR 連結（或停止原因）、測試的四個數字。
- 每個單元一段：做了什麼、與本指令的偏差、殘留風險、未驗證的範圍。
- 固定的基線 commit，以及各單元的分支名稱。
- 計時器：每個單元的租約到期時間、第一次審查呼叫的時間與審查時段的截止時間、實際完成時間。
