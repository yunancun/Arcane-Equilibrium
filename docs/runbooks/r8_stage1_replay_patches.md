# R8 階段 1：隔離回放修補設計

狀態：DESIGN_REVIEW_PENDING；A–D 未實作。本文件是新交付的受審設計，不是 runtime 授權。
交付 `R8-STAGE1-REPLAY-PATCHES-20261009`；PM／唯一 writer：`codex-r8-stage1`。
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
   pending Close 綁定訊號時持倉方向；若已無倉或方向不符，記 `close_position_unavailable`，不能反向開倉。
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
先以新 public Interface 寫可觀察驗收，再實作；不改、刪或略過原 152 項以取得通過。
測試讀取 repository state 時整個工作樹保持不變。E2 看正確性／邊界，E4 驗行為，R4 驗文件與證據。
無法保持缺省 bytes、需改 production 熱路徑、需重建撮合／資料平台、或唯一複核仍失敗，都停止。
不取數、不連 Linux／DB／Demo，不部署、不改治理、不啟動階段 2；GitHub 操作限已授權的 feature 發布及 PR。
所有 source 檔案小於 2000 行，新增註釋用中文。
