# R8 階段 1：隔離回放修補設計

狀態：A–D 已實作，並經獨立的代碼審查與測試驗證（皆為 PASS_WITH_NOTES，2026-10-11），見文末「獨立審查與發布」。
設計初審 PASS（`85af1387`，attempt `91085a66`）。本文件是受審設計與使用說明，不是 runtime 授權。
交付 `R8-STAGE1-REPLAY-PATCHES-20261009`；PM／唯一 writer：`codex-r8-stage1`。該交付在發布前因寫入租約與審查時限到期而停止，
補丁保留；Operator 於 2026-10-11 指示由另一執行者獨立審查並發布（路線事件 `RH-20261011-01`）。
固定 main 基線：`0174315628ba74c322c0c9404a1bba446759763a`。
唯一派工正本：[2026-10-09 派工指令](../execution_plan/2026-10-09--r8-stage1-replay-patches-dispatch.md)。
Operator 以 `RH-20261009-06` 明示另立新交付；曲線範圍按 `RH-20261009-05` 僅含已實現餘額。

## 歷史來源與本次放行

舊交付 `R8-STAGE1-NATIVE-REPLAY` 維持失敗結案，不改其帳本、審查紀錄或次數。
設計起點為本機 commit `42a659b9eab88e7177b69bdbe302336682126988` 的
`docs/runbooks/r8_stage1_native_replay.md`；停止紀錄為 `003a4c609aa259d0c09ab482e40e82e5490d26c0` 同檔。
舊初審、複核原件在工作區（倉庫外）`audits/2026-10-08-r8-stage1-execution/PA-review/verdict.txt`、
`PA-recheck/verdict.txt`；本次 task contract 引用完整路徑。它們都是 FAIL，不能沿用成 PASS。
舊複核未讀修正檔或修正 commit，仍報原提案的問題，因此依停止規則結案。

| 舊初審阻塞 | 本次處理位置 |
|---|---|
| PA-1：Demo ma_crossover 掛單與下一事件模式衝突 | D：明示吃單覆寫，簽入前後值及理由；A：拒絕非市價 |
| PA-2：價格、時間、BBO 可得時點不嚴 | A：成交前更新 open 錨、訊號時 ATR／turnover、報價宣告、非零延遲拒絕 |
| PA-3：多 action 無唯一對接、VETO 佔 pending | B：事件序號與 action 序號；VETO 即時拒絕、不入隊 |
| PA-4：設定失敗回退、金鑰路徑未閉合 | D：必要輸入失敗即停；呼叫者 key 與既有 sibling key 核對 |

本次先透過既有工具取得設計寫入／推送及唯讀審查所需的 controller admission／writer lease；
這不放行 A–D 實作。設計提交並推送後，PA 從頭獨立審查；PA PASS 才把 TODO 該列移入 ACTIVE 並開始 A–D。
提問固定指向此檔、初審設計 commit 與 Context 所綁當次提交；複核讀當次提交中的修正版本，不內嵌舊設計內容。
每個受審節點至多初審一次與原阻塞複核一次；複核仍失敗停止，不改治理、不另立交付。
來源實作由同一 writer 依 A→B→C→D 完成；既有 DAG 的 E2／E4／R4 各守其審查範圍。

## 介面與相容性

- 只改隔離 `replay/`、獨立 binary 及 manifest、兩個新 Python 純工具、新測試、入口／索引與本文件／TODO。
- 不修改 `Strategy`、`strategies/`、production intent processor、Guardian、Decision Lease、Control API 路由。
- `MarketEvent`、`SimulatedFill`、`ReplayResult` 與既有 trace 公開結構保留原欄位，避免要求原 152 項測試改 struct literal。
  fixture 新欄位由獨立擴充解析器讀取，與原 loader 的事件順序逐筆校驗；不是重用 `h0_allowed`。
- 新模組 `replay/stage1.rs`（必要時拆同目錄子模組）承擔新選項、待成交、稽核與參數驗證；
  `IsolatedPipeline` 增加可選內部狀態及 setter。未啟用時保留原管線及 report writer 的呼叫。
- manifest 新欄位 `execution_timing`：缺省／`current_bar_close` 維持舊路徑；`next_symbol_open` 啟用 A。
  未知值直接失敗。`include_replay_metadata` 是另一個可選布林，缺省 false；D 產生的 manifest 設 true。
- 只有新時點、fixture 明示 selector、metadata 或參數來源出現時才輸出擴充欄位。
  缺全部新欄位時 JSON（只移除 `generated_at_ms` 那一行）與固定基線逐位元組相同。
- 擴充 writer 在 JSON 各 action／fill 內附加其稽核索引與 selector；另輸出完整 action audit，
  保持原公開 Rust 型別及既有 summary 不變。新增欄位不影響既有消費者，也不接入任何學習注入入口。

## A：下一標的事件成交

1. fixture 順序沿用原 loader，擴充資料與其逐筆對齊。啟用新時點時，同標的時間必須嚴格遞增，否則拒絕 fixture；
   這避免相同 timestamp 被當成下一根。不同標的交錯不觸發別的標的待成交。
2. 事件 t 的市價 Open／Close 在該標的下一事件 u 處理，位於 context_builder.update(u) 與 scanner skip 之前。
   成交參考價是 u.open；BBO 仍用既有 buy=max(open,ask)、sell=min(open,bid) 規則與既有滑點模型。
   不取 t.close 作成交參考價，也不取 u.close／high／low／volume 或由它們算出的指標。
3. 若 u 有 BBO／size／depth，fixture 該事件必須明示 `execution_quote_at_open=true`；缺宣告則拒絕此模式。
   這只是輸入資料契約，不是資料確實開盤可得的外部證明。缺報價沿用既有缺深度的標記，不補造行情。
4. 風控在成交時以當時餘額、持倉與 u.open 的該標的價格錨評估；先更新 snapshot 的全域及 per-symbol open 錨。
   ATR 與 turnover_24h 在訊號 t 時計算並一併排入 pending，不能讀 u 的收盤資料。所有既有風控 gate 保留。
5. `effective_ts_ms=u.ts_ms`，fill.ts_ms 也是 u.ts_ms；manifest 的 execution latency 缺省或零合法，非零組合直接拒絕。
   風控與帳戶資料使用成交時狀態；selector 使用訊號事件 t 的決定，u 的決定不能回頭改寫 t。
6. pending 按標的、訊號事件序號、action 序號有序處理；每個標的最多一個 pending Open。
   尚未成交不提前建立持倉；同批／交錯標的事件再發 Open 時以 `pending_open_exists` 拒絕並留痕。
   下一事件處理完 pending 後才執行當前 on_tick，策略看到實際成交後持倉。
7. Close 也延到下一事件，繞過 selector；以成交時仍持有的實際數量平倉，保留既有深度部分成交。
   pending Close 綁定訊號時持倉方向與世代；若已無倉、方向或世代不符，記 `reduction_position_changed`，不能誤平重開新倉；訊號時無倉則記 `close_no_position`。
   同標的重複 Close 不新增可過度平倉的數量。深度未成交餘額不自動跨更多事件重掛，保留既有一次性模型。
8. 市價要求為 Open 的 order_type=market（不分大小寫）、limit_price=None 且非 PostOnly。
   非市價 Open 記 `unsupported_nonmarket` 零量列；不能暗轉市價。Close 本身沒有 order type，沿用市價語義。
9. EOF 未等到下一事件的 Open／Close 皆記 `expired_no_next_event` 零量列及 action audit，不成交、不扣費。

驗收涵蓋明顯不同的 t.close／u.open、BBO、交錯標的、非零 latency、缺 quote 宣告、末根、
scanner skip 前處理 pending、風控價格／ATR／turnover、重複 Open／Close、部分平倉及成交時餘額改變。

## B：只減少進場的選擇器

fixture 新欄位：`selector_decision: {"action":"NO_OP|VETO|SIZE_DOWN","size_factor":0.5}`。
缺欄位等於 NO_OP；明示 NO_OP 會有稽核。action 必須是三個精確值；SIZE_DOWN 係數必須有限且 `0 < factor <= 1`。
缺失、零、負值、超過 1、非數字、非有限或未知 action 都拒絕 fixture，不默默改成 NO_OP。
NO_OP／VETO 不接受額外 size_factor，防止含混資料被誤用。

- 先辨識當前持倉。純增加風險 Open 才消費 selector；Close 完全 bypass。
  若 Open 與既有持倉方向相反，減倉部分 bypass selector；新路徑將其量上限約束為實際持有量，
  不允許把超出的數量算作反向新倉。既有缺省路徑不改；這項處理限明示的新回放模式。
- VETO 在訊號時對純進場立即記 `selector_veto`、零量 fill 與 audit，不進 pending，也不影響後來合法 Close。
- SIZE_DOWN 在既有風控 Accepted 的 final_qty 之後縮量，再套既有部分成交上限；不能將 gate deny 改成 allow。
  若訊號與成交時持倉分類不同，再保守重判；任何實際減倉不套 selector。
  audit 同時記 baseline accepted_qty、factor、縮量後 requested_qty、實際 filled_qty；方向／symbol 不變。
- 每個動作鍵為 `{fixture_event_index}:{action_index}`，不是 timestamp join。
  記 signal_ts、signal_symbol、target_symbol、action_kind、trace_index/action_index、selector、處置、fill indices、
  若有成交則 execution_event_index／execution_ts。拒絕、非市價、到期、重複與風控拒絕各有不同處置。
- 選擇器的決定附在決策軌跡 action 與其每個 fill；Close 明示 `selector_applied=false`。
  沒有成交的 Close 仍有 action audit。零數量列不進 C 的交易配對。

驗收：無新欄位完全相容；VETO 不影響 Close／减倉；SIZE_DOWN factor=0.5 的成交量不大於 baseline，
之後 Close 只平實際持有量；非法係數拒絕；同事件多 action 可唯一重建。
指定 ma fixture 後半天 VETO，後半天不新增風險進場，並能從 signal 與 execution 的關聯解釋差異。
下一事件模式中，上半天最後一個訊號若於後半天第一根成交，按訊號時間歸屬並明示；
此 half-day 驗收另用 current_bar_close 隔離檢查 B，不能把跨界 pending 稱成後半天新訊號。

## C：離線逐筆分析

新增 `replay/offline_analytics.py`，重用 `report_analytics.build_replay_result_analytics` 的純函數餘額曲線／回撤。
其 import 與執行在本機封鎖 socket 的測試下驗證，不經資料庫或 Control API。
新增配對與成本／資金費時點標記，不複製既有 balance curve／bootstrap 實作。

- 配對依 effective_ts_ms（缺省 ts_ms）及原 fill index 穩定排序，qty=0 的拒絕列分類列出、略過配對。
  每標的維護加權均價部位及各進場 lot 的時間與費用；同向加倉更新加權價，反向 fill 依當前持倉量配對。
  部分出場按比例攤 entry fee／entry slippage；反向超量只在報告真有可重建反轉時建立新 lot，否則 fail-closed，
  不以假平倉填平殘差。舊 runner 可能丟棄反向超量的缺陷不在本次修補範圍；不符時拒絕可信對帳。
- 每段已配對資料給 entry/exit 時間、方向、數量、均價、entry/exit 費用及滑點成本、gross/net PnL、net return bps。
  net return bps = net PnL / entry_notional × 10000。成交价已含滑點，net PnL 僅再扣手續費；不二次扣滑點。
  滑點成本從 `price / (1 + slippage_bps/10000)` 還原 BBO 錨後參考價，乘 quantity 與不利差額；它不包含未提供的 spread 成本。
- 未配對成交另列入場時間、方向、剩餘量、入場價、已付 entry fee 與滑點；不捏造退出或未實現損益。
- 事前對帳絕對容差固定 `1e-8` quote units。報告分列 completed_round_trip_net_pnl、
  unmatched_balance_effect（負的尚未分攤 entry fees）、residual；三者之和等於 report.net_pnl。
  abs(residual)>容差時輸出失敗，不能標為一致。
- 曲線標為 realized_balance_curve、includes_unrealized_pnl=false；明示由此得出的回撤低估持倉期間風險。
  權益曲線為 unavailable，不在本次實作。成本合計包含所有實際成交（含未平倉 entry）的 fee／slippage。
- 資金費結算時刻以 CLI 參數提供，可按 symbol 覆寫，缺省 UTC 00:00／08:00／16:00。
  保守採閉區間 `[entry_ts, exit_ts]`：端點恰在結算點算跨越，包括同時刻進出。
  多次加倉分別保留各 lot 的持有區間；配對筆的旗標為所含 lot 的 OR，不能用加權平均入場時間漏掉早期 lot。
- 未平倉区間直到整次回放最後事件。新擴充報告含 `replay_end_ts_ms`（不是最後成交時間）。
  舊報告若 diagnostics.last_action_label 為明確 `on_tick:<symbol>@<ts>`，可取其最後事件時間；
  否則有未平倉時必須由呼叫者提供 `--replay-end-ts-ms`，缺失直接報錯，不能當作沒有跨點。
  supplied end 必須不早於最後成交；基線對帳的 end 取固定 fixture 最後事件，記錄來源。
  2026-10-11 審查修正：報告已記錄結束時間時，呼叫者的值與它不同即拒絕；只有由最後動作標籤推得的時間時，呼叫者的值不得更早。見文末已修正的第 1 項。
- 輸出 completed_crossing_count、open_position_crossing_count，以及 funding_crossed = 任一持倉區間跨點。
  不計提、不扣資金費。此旗標為 true 時第一圈不能作增益裁決。

驗收包括基線 13 次完整出場與 1 個未平倉入場費、grid 的 14 筆零量拒絕、部分成交、short／加倉、
閉區間端點、不同標的結算表、未平倉跨點、缺 end 拒絕、餘額／費用／滑點對帳及非法非有限數值。

## D：離線來源 manifest

新增 `replay/offline_manifest.py` 與 `helper_scripts/replay/replay_local.py`。
入口子命令 `manifest`／`analytics` 登記 `helper_scripts/SCRIPT_INDEX.md`；只讀本機輸入，輸出到呼叫者路徑。

1. `manifest` 必填 experiment-id、fixture、key-file、output；starting-balance 缺省 10000。
   run-id 選填且由呼叫者固定；不插入現在時間、隨機 UUID 或其他非確定值。禁止 key/output 路徑重疊。
2. 來源二選一：`--environment demo|paper|live`（缺省 demo）的倉庫設定，或 `--snapshot <json>`。
   snapshot 必須有 `strategy_params`、`risk_overrides`，可有 scanner_config，均為完整可反序列化物件；
   不擷取 runtime。宣告 source_kind=repository_config 或 caller_snapshot，後者也不自動稱已證實 runtime。
3. 倉庫路徑用既有 full_chain_fixture 的設定解析與 TOML loader；三環境策略／風控檔保持分開。
   對必要檔案做存在、解析與非空檢查，既有 loader 回 None 一律失敗，不能退回策略／風控預設。
   需要 full_chain 時才載入 scanner_config；呼叫者 snapshot 若要求 full_chain 而缺 scanner 就失敗。
   2026-10-11 審查修正：資料層只接受 S2 與 S3；`--snapshot` 與 `--environment` 並用即報錯；缺 TOML 解析器時明確報錯。見文末已修正的第 5 項。
4. 主體先重用 `route_helpers.build_default_manifest_payload(cur=None)`，再顯式填 fixture/data_tier/strategy、
   載入的 strategy_params/risk_overrides/scanner_config；不傳 cursor、不走現有路由、不寫 DB。
   canonical 用 `experiment_registry.compute_manifest_canonical_bytes`，簽名用 `ManifestSigner(key_path, fingerprint)`
   與既有 `compute_body_hash`；不用測試 constructor、不新增第二套 canonical／HMAC。
5. caller 的 key-file 必須是 32-byte hex；manifest 輸出同目錄必須已由 caller 放好 key.hex。
   比對兩檔原始 bytes 的既有 fingerprint，不一致就失敗。工具不生成／複製金鑰，也不從 ambient secrets 取 key。
6. 來源路徑與原始檔 SHA-256 寫入 `parameter_provenance`，fixture hash 也寫入主體；
   manifest 及 stdout 摘要標示來源、環境、覆寫。binary 將 provenance 原樣回聲至擴充報告。
   倉庫路徑盡量用 repository-relative；外部 snapshot 的 caller path 如實保留，不把本機路徑硬編碼進源碼。
7. `--taker-entry` 只適用 ma_crossover，明示將 `use_maker_entry` 改 false；前值、後值、固定理由與參數路徑
   記入 `parameter_overrides` 並簽名、回聲至 report。沒給時保持原設定，包括 Demo 的 true。
   下一事件模式搭配 ma_crossover 的 maker 設定時，入口要求此明示覆寫，否則報錯；binary 仍防禦性拒絕非市價意圖。
8. D 預設 include_replay_metadata=true，確保 C 可從報告讀末事件。這是新入口的行為；舊 manifest 缺欄位不受影響。
   CLI 不匯入／呼叫取數、Control API app、帳戶初始化或 evidence injection。測試封鎖 socket 並檢查相關 import 路徑。

驗收：同檔同參數產生相同 canonical bytes；Rust 驗簽成功且兩個 supplied=true；跨語言既有測試不改而通過；
snapshot 與 repo 來源明確區分；缺／壞設定、壞 key、sibling key 不符及不合法覆寫均拒絕；無覆寫完全保留 Demo 值。

## 驗證與停止

固定 fixture SHA-256：`ef64d48bc2f4b7212f97f64955143939d4454803c4dde96aa76a0ac1e185de38`。
本次基線離線 build 與實跑：1440 events、27 fills、net_pnl=-9.137611406571523，數值驗收 1/0/0/0。
這不是 152 項回歸通過；下列命令在實作後／獨立驗證執行，尚未執行的不得寫成 PASS。

```sh
cargo test -p openclaw_engine --features replay_isolated --offline --lib replay::
cargo test -p openclaw_engine --features replay_isolated --offline --test replay_runner_e2e --test replay_runner_e2e_param_delta --test replay_tier_a_acceptance --test replay_manifest_signer_xlang_consistency --test replay_forbidden_guard_acceptance --test replay_mac_policy_acceptance --test replay_profile_acceptance
cargo test -p openclaw_engine --features replay_isolated --offline --test m3_emitter_replay_forbidden --test replay_stage1_acceptance
bash helper_scripts/ci/replay_runner_symbol_audit.sh
python3 -m pytest program_code/exchange_connectors/bybit_connector/control_api_v1/tests/replay/test_stage1_offline_tools.py
```

此外補跑其他 replay_*.rs 與對應 Python 回歸；只能在 Linux 跑的檢查標 UNVERIFIED。
新增驗收透過 public Interface 檢查行為；不改、刪或略過原 152 項以取得通過。
測試讀取 repository state 時整個工作樹保持不變。E2 看正確性／邊界，E4 驗行為，R4 驗文件與證據。
無法保持缺省 bytes、需改 production 熱路徑、需重建撮合／資料平台、或唯一複核仍失敗，都停止。
不取數、不連 Linux／DB／Demo，不部署、不改治理、不啟動階段 2；GitHub 操作限已授權的 feature 發布及 PR。
所有 source 檔案小於 2000 行，新增註釋用中文。


## 本次送審 checkpoint（2026-10-09，本機 Mac）

以下是實作者在 2026-10-09 送審時的自我驗證，原文保留。其後的獨立審查、修正與最終數字見文末「獨立審查與發布」。

本節記錄 PM 的 source 驗證，不代替 E2／E4／R4；獨立 verdict 另保存在本工作區
`audits/2026-10-09-r8-stage1-replay-patches/`，並彙整於 feature PR。尚未合併或部署。
fixture 仍為前述固定 hash；新 fixture 只在本機由它追加 selector，不另行取數。

| 檢查 | passed / failed / skipped / error | 證據 |
|---|---|---|
| 既有 replay 單元 | 117 / 0 / 0 / 0 | `rust-unit-verified.log` |
| 原七組 replay 整合 | 35 / 0 / 0 / 0 | `rust-integration-verified.log`；原測試檔無差異 |
| 新 Stage 1 整合 | 16 / 0 / 0 / 0 | 同上；時點、BBO、同標的、scanner skip、風控餘額、部分平倉、重開世代、單調選擇器 |
| m3 emitter 隔離 | 3 / 0 / 0 / 0 | 同上 |
| replay_runner binary 單元 | 9 / 0 / 0 / 0 | `rust-binary-verified.log` |
| Python 新工具＋既有 analytics／xlang | 43 / 0 / 0 / 0 | `python-tests-verified.log` |
| 真策略／逐位元組／設定來源驗收組 | 8 / 0 / 0 / 0 | `run_acceptance.py`、`acceptance-results.json`（倉庫外） |
| release forbidden symbol audit | 1 / 0 / 0 / 0 | `symbol-audit-verified.log`，Darwin `nm -gU`；0 forbidden，1 defined symbol（macOS 上的偵測力見文末已知限制） |

原 152 項全部保留。迭代中曾有新測試 fixture 少了 `source`（11 失敗），修正測試後另發現
NO_OP 多餘係數未被拒絕（10 通過／1 失敗）；已改用嚴格物件 variant，最後結果如表。
這些失敗記錄保留，不覆寫成初次即通過。測試與實作交錯完成，沒有主張全程先測後寫。

- A：同 fixture 缺省 27 fills、net_pnl=-9.137611406571523；只移除 generated_at_ms 一行後 byte-identical。
  next-symbol-open 的 27 個正量 fill 均核對下一事件 open 加既有滑點，effective_ts_ms 是成交事件時間。
- B：current-bar-close 後半天 VETO 有 15 個拒絕進場記錄，該段沒有新風險進場；Close 仍可執行。
  報告 net_pnl=-5.49817523677666，與缺省不同；這是機制驗收，不能據此裁決增益。
- C：13 筆來回交易 net 合計 -8.97267702976942；1 個未平倉入場費的餘額影響 -0.16493437680442335；
  殘差 2.320366121466577e-12。grid 原始 62 列中有 14 個零量拒絕，分析成功。
  只交付已實現餘額曲線；權益曲線仍未完成。保留當前逐筆成交標籤與資料分級。
- D：repo Demo＋明示 taker-entry 與 caller snapshot 都通過 Rust 驗簽，stderr 的兩個 supplied=true；
  同組檔案重跑 manifest 相同。來源與覆寫均已簽名並回聲至報告。離線 imports 沒有載入 app 或 DB driver。
- 新選項要求明示 strategy，不能讓 synthetic walker 默默忽略選項；公開 pipeline setter 也拒絕非零 latency。

### 本機使用

先由呼叫者在輸出 manifest 同目錄放妥自己的測試 `key.hex`（工具不生成／複製），
以下 `$FIXTURE`、`$OUT`、`$KEY` 均由呼叫者提供；勿把私有 fixture／金鑰提交進倉庫。

```sh
python3 helper_scripts/replay/replay_local.py manifest --fixture "$FIXTURE" --key-file "$KEY" --output "$OUT/manifest.json" --experiment-id r8-local --next-open --taker-entry
OPENCLAW_REPLAY_MAC_NO_PRIVATE=1 rust/target/debug/replay_runner --manifest "$OUT/manifest.json" --output-dir "$OUT/report"
python3 helper_scripts/replay/replay_local.py analytics "$OUT/report/replay_report.json" --output "$OUT/analytics.json"
# 舊報告沒有可靠末事件時間時，必須額外給實際 fixture 最後事件時間。
python3 helper_scripts/replay/replay_local.py analytics "$OUT/legacy-report.json" --replay-end-ts-ms 1704153540000 --output "$OUT/legacy-analytics.json"
```

caller snapshot 使用 `--snapshot snapshot.json`；不同標的結算時刻以 `--funding-hours hours.json` 提供，
例如 `{"*": [0,8,16], "ETHUSDT": [0,4,8,12,16,20]}`。`funding.funding_crossed=true` 時不作第一圈增益裁決。
倉庫設定檔的來源路徑記為相對倉庫根的路徑（2026-10-11 審查修正後；送審當時是絕對路徑）。
呼叫者提供的快照與 fixture 仍記為解析後的絕對路徑，`fixture_uri` 也是絕對路徑，所以同一組輸入在不同機器上的 `manifest_hash` 不同。
沒有把機器路徑硬編入源碼；檔案 SHA-256 保留。

未驗證 Linux、資料庫、Demo／live 帳戶與 runtime 生效參數；沒有執行需這些環境的測試，也未啟動階段 2。
階段 2 建議另行授權 Linux 唯讀讀取：生效策略／風控快照、實際委託／成交／費用／資金費流水與同時段行情，
用共同時間與訂單識別鍵對帳；公開一分鐘 fixture 只能提供 sandbox 時點與機制證據，不能替代 Demo 對帳。

## 獨立審查與發布（2026-10-11）

實作者的交付 `R8-STAGE1-REPLAY-PATCHES-20261009` 在發布前停止：寫入租約於 2026-10-09 16:10 UTC 到期而未續租，
受控審查的時限也在代碼審查開始之前到期。設計審查已通過；代碼審查、測試驗證與文件審查當時都沒有執行。
該交付維持停止狀態，它的准入帳本與審查狀態沒有被更動。
Operator 於 2026-10-11 指示由另一執行者獨立審查並發布保留的補丁，局部修正由該執行者處理（路線事件 `RH-20261011-01`）。
審查方與實作方是不同廠商的代理。

### 審查結果

| 步驟 | 對象 | 結論 |
|---|---|---|
| 設計審查（沿用實作方的結果，未重做） | `85af1387` 的設計 | PASS，無 finding。實作期間設計改過一條規則（待成交的 Close 綁定持倉的方向與世代），已交代碼審查特別核對 |
| 代碼審查，初審 | `d48b84e75` | PASS_WITH_NOTES：無阻塞項；1 項重要、9 項次要 |
| 修正 | `4623a5525` | 處理其中 5 項，見下 |
| 代碼審查，複核一次 | `4623a5525` | PASS_WITH_NOTES：5 項皆已關閉；另有 3 項低度註記 |
| 測試驗證，初審 | `4623a5525` | PASS_WITH_NOTES：A 至 D 每條驗收都有可判別的測試或實跑證據；2 項檢查須補跑、6 項測試或證據缺口 |
| 補測試與補跑 | `dc30286e6` | 只新增測試；補跑見下表 |
| 測試驗證，複核一次 | `dc30286e6` | PASS_WITH_NOTES：8 項皆已關閉；指出禁用符號稽核在 macOS 上偵測力很弱（見已知限制） |

已修正的五項：

1. 分析工具：呼叫者給的回放結束時間不得與報告內記錄的不同。先前可以往前覆寫，會漏標跨結算點的未平倉部位。輸出同時記下所用的值與來源。
2. 分析工具：輸出 `funding.timestamp_basis` 與 `funding.crossing_check_exact`。只有 `next_symbol_open` 的報告標為精確。
3. 回放：fixture 內明確寫 `"selector_decision": null` 會被拒絕，不再當成缺欄位。
4. manifest 工具：倉庫設定檔的來源改記相對路徑。
5. manifest 工具：不再接受資料層 S1；`--snapshot` 與 `--environment` 並用即報錯；缺 TOML 解析器時給出明確錯誤。

### 最終驗證（本機 Mac，離線，提交 `dc30286e6`，乾淨工作樹）

數字順序為 passed／failed／skipped／error。測試由發布方直接執行並保留輸出，不是治理工具的受控擷取：
受控擷取會隔離家目錄，離線的 cargo 讀不到本機套件快取。測試驗證角色讀的是測試源碼與這些輸出。

| 檢查 | 結果 |
|---|---|
| 回放單元測試（`--lib replay::`） | 117／0／0／0 |
| 原七組回放整合測試（測試檔未改動） | 35／0／0／0 |
| 階段 1 驗收（`replay_stage1_acceptance`） | 21／0／0／0 |
| emitter 隔離（`m3_emitter_replay_forbidden`） | 3／0／0／0 |
| `replay_runner` binary 單元測試 | 9／0／0／0 |
| Python 新工具測試（`test_stage1_offline_tools.py`） | 40／0／0／0 |
| Python 既有簽名相關兩檔 | 26／0／0／0 |
| 禁用符號稽核腳本（release） | 腳本回報通過，但 macOS 的 release binary 已剝除符號，只掃到 1 個；這個結果沒有實質偵測力 |
| 禁用符號補充檢查 | 以同一組禁用樣式掃描未剝除的 debug binary（16,083 個符號，其中 113 個屬於新模組）：0 個命中 |
| 缺省路徑 | 補丁前簽好的四份 manifest（ma_crossover、grid_trading、bb_reversion，另一份帶 `h0_allowed`）在補丁後的 binary 重跑，報告只排除 `generated_at_ms` 一行後逐位元組相同 |
| 對舊報告跑分析工具 | ma_crossover：13 筆來回、1 個未平倉，殘差 2.3e-12；grid_trading：24 筆來回，14 筆零數量拒絕列分類列出且未配對，殘差 8.4e-12 |
| 新路徑端到端 | 倉庫 Demo 設定加明示吃單覆寫、`next_symbol_open`，三組（無選擇器、後半天 VETO、全程 SIZE_DOWN 0.5）：正數量成交的價格皆為下一事件開盤價加既有滑點；後半天 VETO 組沒有新的風險進場；SIZE_DOWN 的成交量皆不大於係數乘以風控核可量；對帳殘差在 1e-12 量級；兩個 `supplied=true` |

fixture 是前述固定雜湊的一日公開一分鐘線。端到端各組的損益只用來核對機制，不是增益或策略結論。
GitHub CI 不執行 `replay_isolated` 的測試，所以以上只有本機證據。Linux、資料庫、Demo／live 與 runtime 都沒有驗證。

### 三方對照的使用要求

1. 三組都用同一組 manifest 選項（`execution_timing=next_symbol_open`、`include_replay_metadata=true`、同一參數來源與覆寫），
   只在 fixture 的 `selector_decision` 上不同。不要拿沒有新欄位的舊路徑當對照組：擴充啟用後，即使全是 `NO_OP`，
   反向 Open 的數量也會被截到持倉量，無倉的 Close 會多一列記錄。
2. 增益裁決只接受 `funding.crossing_check_exact=true` 且 `funding.funding_crossed=false` 的報告。
   舊時序（`current_bar_close`）的成交時間戳是 K 線開盤時間，成交卻模擬在收盤，結算前最後一根的出場不會被標記。
3. 回放結束時仍有未平倉部位（`unmatched_fills` 非空）時，結算點只檢查到最後一根 K 線的開盤時間。
   最後一根 K 線的收盤恰為結算時刻的情形（例如整日 fixture 結束於 00:00 UTC）不會被標記，而工具此時仍回報 `crossing_check_exact=true`。
   這一點補上之前，有未平倉部位的組別不作增益裁決，或改用在結算時刻之前結束的 fixture。
4. 核對成交價時先濾掉零數量列。它們的 `price` 欄只是標示：訊號那一根的收盤價，或到期列的 0。
5. `selector_decision` 的鍵若拼錯，會被當成缺欄位，該組實際跑成基線。跑完後核對報告 `stage1.action_audit` 內的 selector 是否如預期。
6. `SIZE_DOWN` 的「只會變小」是逐筆成立的。前一筆縮量之後，後續進場可能比基線組大，
   或通過在基線組被曝險上限擋下的進場。解讀對照時要留意這種路徑依賴。

### 已知限制與後續項（本次未處理）

| 項目 | 說明 |
|---|---|
| 回放結束時的結算點檢查 | 上面第 3 點。需要工具以最後一根 K 線的收盤時間作結束時間，或允許呼叫者給較晚的結束時間；現在呼叫者的值與報告值不同即拒絕 |
| 同事件的平倉加反手 | `next_symbol_open` 下同一事件發出 Close 與反向 Open 時，Open 會以 `reduction_position_changed` 被拒，反手進場不成立。比設計寫的「保守重判」更嚴。現有三個策略每個事件只發一種動作，不會觸發 |
| 擴充報告的寫入 | `extend_report` 以整檔覆寫，不是先寫暫存檔再改名；鍵會變成字母序。只影響啟用擴充的報告 |
| 函式庫層的防護 | 延遲檢查只在設定階段做；沒有策略 adapter 的管線會靜默忽略擴充；設定與 fixture 筆數不符時會 panic。經 `replay_runner` 的路徑都有擋 |
| 手工製作的報告 | `"stage1": null` 會讓分析工具拋出未轉換的例外。結果仍是失敗，不會給出錯誤的數字 |
| TOML 解析器檢查 | 檢查的是當下能否匯入；既有載入器在匯入時就綁定了結果，兩者通常一致。對應測試驗到的是錯誤訊息，不是原始情境 |
| binary 層的缺省路徑 | `full_chain`、帶延遲、S3、多標的、無 `strategy` 的 manifest 只有函式庫層測試，沒有經 `replay_runner` 的逐位元組對照 |
| binary 層的回寫 | 來源與覆寫回寫到報告，只有端到端實跑與函式庫層測試，沒有倉庫內的 binary 層測試 |
| 跨機器重現 | `fixture_uri` 與呼叫者提供的檔案是絕對路徑。Python 與 Rust 對指數形式浮點數的 canonical 寫法不同（既有問題；現有設定檔沒有這類值） |
| 禁用符號稽核腳本 | 在 macOS 上 release binary 已剝除符號，腳本只掃到 1 個，且符號數為 0 時不會失敗。既有腳本的限制，不是本次引入；有效的檢查要在 Linux 做 |
| CI | GitHub CI 不執行 `replay_isolated` 的測試；日後的回歸只能靠本機執行 |
