# R8 階段 1 派工指令：既有 Rust 回放的四項修補

| 項目 | 內容 |
|---|---|
| 文件性質 | 單一工程單元的派工指令與交接摘要。不是授權文件；是否可派發以 [TODO](../../TODO.md) 的 `P1-R8-STAGE1-REPLAY-PATCHES` 一列為準 |
| 日期 | 2026-10-09（Asia/Shanghai） |
| 依據 | [R8 修訂一](../decisions/2026-10-08--r8-amendment-1-first-loop-on-native-replay.md)（已採納）§5 階段 1；[R8 採納決策](../decisions/2026-10-07--r8-adoption-agent-experiment-bench.md) §9 |
| 狀態 | 階段 1 尚未開始。沒有 task contract、routed DAG、writer lease 或任何源碼變更 |
| 倉庫外的依據 | 工作區 `audits/2026-10-08-r8-replay-gap-inventory/`：差距盤點報告與實跑證據。不隨 Git 傳遞；本文件已摘入必要的數字 |

## 交接摘要

- **上一單元的結果**：R8 方向與修訂一已由 Operator 採納，並經 PR #203 以 merge commit `49c05c6fd` 合入 main。
  既有 Rust 回放的差距盤點已完成。階段 1 只建立了 TODO 等待列，尚未動工。
- **關鍵證據**：本機離線編譯 `replay_runner` 並實跑，ma_crossover、grid_trading、bb_reversion 都走真策略路徑；
  77 筆實際成交全部以產生訊號的同一根 K 線收盤價成交；回放內沒有選擇器的注入點；指標只有一分鐘週期。
  回放單元測試 117 項、七個回放整合測試 35 項在本機全數通過。
  以上實跑與測試數字出自倉庫外的盤點證據與開發機上的執行，不隨 Git 傳遞；接手者須依 §0 第 3 點自行重現，不得直接引用。
- **偏差與更正**：R8 採納決策初版漏查了既有 Rust 回放，已以註記更正。提交 `b6ff86858` 的說明稱「五個 profit-control
  測試在改動前即已失敗」，該說法不成立：那是測試執行途中工作樹被編輯造成的，乾淨重跑為 263 項全過（見 §6）。
  2026-05-11 回放對實際成交的偏差仍未結案，屬階段 2 的範圍。
- **本文件的修訂**：PR #204 的自動審查提出十點，九點已修入本文件與登記簿（事件 `RH-20261009-04`）：
  先固定基線再綁定 context、備用 fixture 須固定、目標不再稱 production 參數、SIZE_DOWN 列為必做、
  未平倉部位納入跨結算點判定與對帳、餘額曲線不稱權益曲線、單一實作者、來源記錄改為追加。
  另一點稱事件提交缺少 trailer，查無此事：被檢查的是 GitHub 的合成合併提交，事件提交本身帶有 trailer。
- **功能可用程度**：回放的真策略路徑可以執行；R8 第一圈所需的四項修補都還沒做。沒有任何 runtime、Demo 或平台效果。
- **Operator 已決定**：資金費結算不納入階段 1（2026-10-09）。因此第一圈只能在各組持倉都不跨結算點時作增益裁決。
- **仍未決**：階段 2 所需的 Linux 唯讀存取；R8 採納決策 §12 的三項；訊號邊界 ADR 尚未起草。
- **下一步**：接手的 PM 對 TODO 該列做 fresh admission，然後依本文件執行。不要自行啟動階段 2。

以下為給執行者的指令原文。

你是本任務的 PM／Conductor。先完成 §0 第 1 點（`git fetch` 並選定基線），再依 `AGENTS.md`、`CLAUDE.md` 與
`.codex/agent_registry_v1.json`，用 `helper_scripts/maintenance_scripts/agent_governance.py route` 與 `context`
對**該固定的基線 commit** 綁定任務事實，然後才動工。綁定之後基線若有改變，重新綁定，不要沿用舊的 context。
這是源碼實作：需要簡短的 PA 設計說明在前，獨立的 E2 代碼審查與 E4 測試驗證在後。對 operator 一律用中文回報。

## 0. 前置檢查（任一不成立即停止並回報，不要繞過）

1. 基線必須含有已採納的修訂文件 `docs/decisions/2026-10-08--r8-amendment-1-first-loop-on-native-replay.md`，
   表頭狀態為 Accepted。它已於 2026-10-09 經 PR yunancun/Arcane-Equilibrium#203 合入 main（merge commit `49c05c6fd`）。
   先 `git fetch`，以當時最新的 main 為基線並記下它的完整 commit；task contract 與 context 都綁這個 commit。
   若 main 上找不到該文件，回報 `NEEDS_CONTEXT`。
2. 先查有沒有人做過：對 `rust/openclaw_engine/src/replay` 與遠端分支做 log 與 grep。已有等價實作就回報 NO-OP。
3. 重現基線：離線編譯 `replay_runner`（`-p openclaw_engine --features replay_isolated --offline`），
   用工作區 `audits/2026-10-08-r8-replay-gap-inventory/evidence/fixture_btc_1m.json`（倉庫外；
   sha256 `ef64d48bc2f4b7212f97f64955143939d4454803c4dde96aa76a0ac1e185de38`）跑 ma_crossover、策略預設參數、起始資金 10000。
   必須得到 27 筆成交、`net_pnl = -9.137611406571523`。重現不了就停，先查原因。
   取不到該檔時不要自行取數（§4 禁止網路請求）。改用已在本機、來源說得清楚的一分鐘線資料自建 fixture，
   並在改碼之前把它固定下來：保存 fixture 檔、它的來源說明（資料來源、標的、週期、起訖時間、取得日期）與 SHA-256，
   記下它的基線數字（成交筆數與 `net_pnl`），之後所有對照都用同一份。保存位置寫進回報；
   倉庫是公開的，要把資料提交進倉庫須先確認它可以公開。
   本機沒有可用資料時回報 `NEEDS_CONTEXT`，請 Operator 提供 fixture，不要用未固定的資料開工。
   manifest 需要同目錄的 `key.hex`（32 位元組的十六進位）；用你自己臨時生成的測試金鑰，不要提交。
   2026-10-08 開發機上 `~/.cargo/bin/cargo` 的捷徑失效；遇到時把 `~/.rustup/toolchains/<toolchain>/bin` 加進 PATH。

## 1. 目標

讓既有 Rust 回放足以承擔 R8 第一圈的「停手」選擇實驗：成交時點不偷看、可以注入選擇器的決定、
輸出能餵統計閘門、跑的是來源明確的參數（倉庫設定檔或呼叫者提供的快照，不再是策略預設值）。只做這四項，不做別的。
本階段不宣稱所跑的參數等於引擎實際生效的參數；那要等階段 2 擷取運行環境的快照。

## 2. 必讀

- `docs/decisions/2026-10-08--r8-amendment-1-first-loop-on-native-replay.md`：AM1、AM3、AM7、AM8、AM9、§5 階段 1。
- `docs/decisions/2026-10-07--r8-adoption-agent-experiment-bench.md`：§9 的權限邊界。
- 工作區 `audits/2026-10-08-r8-replay-gap-inventory/REPORT.md`（倉庫外，可取得時閱讀）：缺口 G1、G7、G8、G9 與實跑證據。
- `docs/adr/0051-registry-authorized-advisory-model-serving.md` 的 A3（動作集合與單調性）。
- `docs/runbooks/ref21_replay_operator_runbook.md`（資料分級規則）。
- 代碼：`rust/openclaw_engine/src/replay/runner.rs`（`execute_adapter_pipeline`）、`apply_fill.rs`、
  `context_builder.rs`、`fixture_loader.rs`、`strategy_adapter.rs`、`report_writer.rs`，
  `src/bin/replay_runner.rs` 與 `src/bin/replay_runner/manifest.rs`。

## 3. 四個工作項

### A. 成交時點開關（G1）

現況：`execute_adapter_pipeline` 在同一個事件內先 `context_builder.update(event)`，再 `strategy.on_tick`，
產生的 Open／Close 立刻以該事件的收盤價成交（`process_open_intent`／`process_close_intent`；
`apply_fill.rs` 的參考價是 `intent.limit_price.unwrap_or(close_price)`）。`execution_latency_ms` 只寫進 `effective_ts_ms`。
盤點實測 77 筆成交全部落在產生訊號的那一根收盤價加減 5 bps。

要求：
- manifest 新增可選欄位（名稱由 PA 定），缺省時行為與現行完全相同。
- 啟用時，事件 t 產生的市價意圖在**同一標的的下一個事件**成交，參考價取該事件的開盤價；
  有報價時沿用現行的 BBO 錨定規則，但用下一事件的報價。`effective_ts_ms` 取成交事件的時間。
- fixture 結尾沒有下一事件時，意圖作廢並留下明確記錄。
- 開倉與平倉一律適用。任何例外要在設計說明裡列出理由。
- 風控評估用哪個時點的狀態、待成交期間的持倉語義（例如是否會重複開倉），由 PA 明確規定並寫成測試。

驗收：
- 缺省時，既有回放測試不改而全數通過；同一 fixture 的報告排除 `generated_at_ms` 後逐位元組相同（前置檢查 3 的數字不變）。
- 啟用時，有測試證明沒有任何成交價取自產生訊號的那一根。
- 末根事件的意圖不成交；待成交期間不會重複開倉。

### B. 選擇器注入點（G9）

現況：回放內沒有。fixture 的 `h0_allowed` 會進 `TickContext`，但回放與 ma_crossover 都不消費它；
把後半天設為 `false` 重跑，結果與基線完全相同（證據在工作區同一目錄的 `evidence/mah0`）。

要求：
- 回放支援對風險增加型進場（回放內即 `StrategyAction::Open`）套用外部給定的決定。
- 動作集合限 `NO_OP | VETO | SIZE_DOWN`，語義比照 ADR-0051 A3：VETO 只能拒絕，SIZE_DOWN 只能縮小，
  兩者都不得影響 Close 或任何減倉。
- 決定以 fixture 事件上的**新**可選欄位提供（時間型）。不要重用 `h0_allowed`，那是另一個語義。缺欄位等於 `NO_OP`。
- 每個被套用的決定都寫進決策軌跡與成交記錄，使三方對照可以稽核。
- 這些決定只在隔離回放內生效，目的是讓三組對照的回放結果真的不同。它們不是對任何真實進場的採用；
  前向 shadow、Demo 與 live 的行為不在本項範圍內，也不得因本項改變。
- VETO 與 SIZE_DOWN 都必須完成。修訂一 AM3 的 2026-10-09 更正要求兩者都在隔離回放內生效；
  缺任何一個，本工作項即未完成，階段 1 不得回報為完成。
- SIZE_DOWN 帶一個縮量係數，只能讓該次進場的數量變小，不得放大，也不得改變方向或標的。
  係數缺失或超出合法範圍時怎麼處理（拒絕該 fixture，或保守地當成 VETO），由 PA 規定並寫成測試；不得默默當成 `NO_OP`。

驗收：
- 缺欄位時輸出與現行逐位元組相同。
- VETO 時該事件的 Open 不成交，Close 不受影響。
- SIZE_DOWN 時該事件的 Open 以縮小後的數量成交；有測試證明成交數量不會大於未套用時的數量。
  選擇器的決定不改變任何 Close 意圖；之後的 Close 平掉實際持有的數量，不得多平，也不得因此反向開倉，並有測試覆蓋。
- 用後半天全部 VETO 的 fixture 重跑 ma_crossover，後半天沒有新開倉；輸出與基線不同，且差異可由記錄解釋。

### C. 逐筆輸出（G7）

現況：報告只有成交、決策軌跡與總損益。Python 的
`program_code/exchange_connectors/bybit_connector/control_api_v1/replay/report_analytics.py`
已有以報告 JSON 為輸入的純函數（餘額曲線、回撤、bootstrap）。

要求：
- 先確認既有純函數能否離線直接使用，只補缺的部分。
- 補齊：由成交配對出的來回交易清單（進出時間、方向、數量、進出價、手續費、滑點成本、淨損益、淨報酬 bps）、
  已實現餘額曲線、手續費與滑點的成本分解。
- 回放結束時尚未平倉的部位另列為「未配對成交」（進場時間、方向、數量、進場價、已付手續費與滑點成本），
  不得當成來回交易。
- 餘額曲線只在成交時變動，不含未實現損益。輸出中要這樣標示，不得稱為權益曲線；由它算出的回撤會低估持倉期間的回撤。
  報告目前沒有逐事件的標記價格，真正的權益曲線不在本單元範圍內。
  修訂一把「權益曲線」列在缺口 G7 之下；本單元對這一部分只交付已實現餘額曲線，含未實現損益的權益曲線仍是缺口。
  這是記錄者的範圍界定，未經 Operator 確認；回報時列為未完成的部分，由 Operator 決定是否在階段 3 之前補上。
- 提供不依賴資料庫與 Control API 的本機入口，輸入 `replay_report.json`，輸出 JSON。
- 每一段持倉區間都標出是否跨越資金費結算點：已完成的來回交易用進場到出場的區間，
  未配對成交用進場到回放最後一個事件的區間。結算時刻以參數提供，預設為 UTC 00:00、08:00、16:00；
  不同標的的結算間隔可能不同，不要寫死。區間端點恰好落在結算時刻時算不算跨越，由 PA 規定並寫成測試。
- 輸出另給出：跨結算點的來回交易筆數、跨結算點的未平倉部位數，以及一個整次回放層級的旗標
  （任何一段持倉區間跨結算點即為真）。回放目前不結算資金費，修訂一規定第一圈只能在各組持倉都不跨結算點時
  作增益裁決；階段 3 的閘門讀的就是這個旗標，所以它不能漏掉未平倉的部位。
- 新腳本登記到 `helper_scripts/SCRIPT_INDEX.md`。

驗收：
- 對基線報告做對帳，分三項列出：已完成來回交易的淨損益加總、未配對成交對餘額的影響（已扣的手續費等）、殘差。
  三項之和等於報告的 `net_pnl`（回放以期末餘額減起始資金計算），殘差須在事前寫定的容差之內。
  ma_crossover 的基線結束時留有一個未平倉的多頭部位（倉庫外證據：27 筆成交的帶號數量加總等於最後一筆進場的數量），
  所以只加總來回交易是對不上的。
- 含風控拒絕記錄（數量為零）的報告不出錯（grid_trading 的基線報告有 14 筆）。
- 有測試覆蓋跨結算點與不跨結算點的來回交易，以及跨結算點的未平倉部位；後者必須讓整次回放的旗標為真。

### D. 帶參數來源的 manifest（G8）

現況：獨立執行時 stderr 顯示 `strategy_params_supplied=false risk_overrides_supplied=false`，跑的是策略預設值。
倉庫內 Demo 環境的設定檔是 `settings/strategy_params_demo.toml`、`settings/risk_control_rules/risk_config_demo.toml`、
`settings/risk_control_rules/scanner_config.toml`。既有的組裝與簽名在 Control API
（`app/replay_full_chain_routes.py`、`replay/route_helpers.py`），依賴資料庫與運行環境。

要求：
- 提供本機入口，從倉庫內的設定檔組出帶 `strategy_params` 與 `risk_overrides` 的 manifest 並簽名；需要時帶 `scanner_config`。
- 預設取 Demo 環境的設定。三個環境的設定是故意分開的，不要合併。
- 重用既有的組裝與 canonical 化、簽名函數，不要另寫一套。
- 簽名金鑰由呼叫者以路徑提供。工具不生成、不落地任何正式金鑰，不把金鑰寫進倉庫。
- 輸出記錄所用設定檔的路徑與 SHA-256。
- 記錄參數來源。倉庫內的設定檔不等於引擎實際生效的參數：策略參數可經 IPC 在運行中更新，只寫入運行時快照。
  因此入口須同時接受「倉庫設定檔」與「呼叫者提供的參數快照檔」兩種輸入，並在 manifest 與輸出中標明是哪一種。
  以倉庫設定檔組出的 manifest 一律標為「倉庫設定」，不得稱為 production 生效參數。
  擷取運行環境的快照屬於階段 2，本單元不做，也不連 Linux。

驗收：
- 產出的 manifest 通過 `replay_runner` 的簽名驗證，stderr 顯示兩個 `supplied=true`。
- `rust/openclaw_engine/tests/replay_manifest_signer_xlang_consistency.rs` 通過。
- 同一組設定檔重跑，manifest 主體逐位元組相同。

A 至 D 由同一位實作者依序完成（A 與 B 改同一批 Rust 檔；C、D 是 Python）。同一時間只有一位 writer；
E2 與 E4 只作唯讀的審查與驗證。

## 4. 明確不做

- 掛單排隊與觸價模型（G2）、資金費結算（G3）、多週期指標（G4）、成交標籤改名（G6）。
  Operator 已於 2026-10-09 裁決：資金費結算**不納入**階段 1。不要實作它，只做 C 項的跨結算點標記。
  因此第一圈只能在各組持倉都不跨結算點時作增益裁決。
- 任何 production 熱路徑：引擎主流程、intent processor、`strategies/` 下的策略本體、`Strategy` trait、Guardian、Decision Lease。
- Control API 既有路由的行為。
- 把回放結果接進學習或證據注入路徑。依 AM7，未經統計閘門的結果不得成為受信任的學習證據。
- 取數與任何網路請求；Linux、資料庫、Demo 帳戶；部署、重啟；平台帳戶與支出。
- 階段 2 及之後的任何工作。

## 5. 不變量

- `replay_isolated` feature、forbidden guard、Mac policy guard 不得放寬。
  `helper_scripts/ci/replay_runner_symbol_audit.sh` 必須仍然通過。
- manifest 與 fixture 的新欄位一律可選，缺省行為與現行逐位元組相同。既有 Stage 0R 封包與測試的語義不變。
- 回放結果的資料分級不變：只有公開 K 線時仍是開發沙盒級，不是晉級證據。
- 不寫假成功。跳過或無法執行的測試要明說。
- 新增與修改的註釋用中文；不硬編機器路徑；單檔不超過 2000 行（`runner.rs` 現為 1,172 行）。

## 6. 驗證與證據

- Rust：`cargo test -p openclaw_engine --features replay_isolated --offline`，至少涵蓋 `replay::` 的單元測試與
  `rust/openclaw_engine/tests/replay_*.rs`。
- Python：對應的 pytest。只能在 Linux 受治理環境跑的部分標為 `UNVERIFIED`，不要用 Mac 的結果代替。
- 測試結果以 passed／failed／skipped／error 四個數字回報。
- 動工前的基線（2026-10-09，本機 Mac，提交 `5bd70155c`；該分支相對 main 只改了文件，`rust/`、`program_code/`、`helper_scripts/` 無差異）：
  - `cargo test -p openclaw_engine --features replay_isolated --offline --lib replay::`：117 通過、0 失敗、0 略過、0 錯誤。
  - 七個整合測試（`--test replay_runner_e2e --test replay_runner_e2e_param_delta --test replay_tier_a_acceptance
    --test replay_manifest_signer_xlang_consistency --test replay_forbidden_guard_acceptance
    --test replay_mac_policy_acceptance --test replay_profile_acceptance`）：35 通過、0 失敗、0 略過、0 錯誤。
  - 完成後這 152 項必須仍然全數通過，而且不得靠修改、刪除或略過其中任何一項來達成。
    `tests/m3_emitter_replay_forbidden.rs` 與 Python 端的測試未納入這次基線，請自行補跑並回報。
- 每個工作項留下可重跑的指令與輸出摘要。
- `tests/structure/` 下讀取倉庫當下狀態的治理測試，執行期間不要改動工作樹，否則會出現假失敗。
  出現失敗時先在不變動的工作樹上重跑確認，再判斷是既有問題還是本次改動造成。
  （2026-10-09 在 `b6ff86858` 的乾淨工作樹上，讀取 TODO 的八個結構測試檔為 263 通過、0 失敗。）

## 7. 治理與交付

- TODO 已有本單元的等待列 `P1-R8-STAGE1-REPLAY-PATCHES`（狀態為等待准入）。完成 fresh admission 後，
  依 `docs/agents/todo-maintenance.md` 把它移入 ACTIVE 並更新證據；不要改動 AIML、IBKR 既有各行的狀態。
- 開 feature 分支，完成後開 PR。不直接推 main，不自行合併。
- 資金費結算不納入階段 1 的裁決已記入修訂一與 TODO（路線事件 `RH-20261009-03`），不需要你補記。
- 你的 PR 若含帶 `Route-Id` trailer 的提交，合併時必須用 merge commit，不可 squash。
- 審查採「一批互補審查、一次集中修補、一次原阻塞項複核」。複核仍不過就保留 patch 與停止原因，不換名重試。

## 8. 預算與停止條件

- 四項合計的工程投入估計為 2.5 至 4.5 個工程日，這是未量測的估計。階段 1 至 3 合計上限為十個工作日。
  盤點時的估計把 SIZE_DOWN 列為可以後補，所以這個數字沒有含它。超出預算時停止並回報，不要用省略 SIZE_DOWN 的方式收尾。
- 出現下列任一情形即停止並回報，不要擴大範圍：需要重造撮合或資料平台；需要改動 §4 所列的 production 熱路徑；
  無法維持缺省行為逐位元組不變；前置檢查不成立。

## 9. 回報格式

- `work_status`、`gate_verdict`、`disposition` 分開寫。
- A 至 D 各一段：完成與否、證據（指令與四個數字）、與本指令的偏差、殘留風險。
- 未驗證的範圍。
- 對階段 2 的建議：需要哪些 Linux 唯讀存取、fixture 的資料來源。不要自行啟動階段 2。
