# E2 對抗審查 — 線 B 四件套（alert sink+BB 哨兵 / polymarket 軸 / analyze_token_usage / mnemopi 試點）· 2026-06-11

- 審查者：E2（對抗線 B）。HEAD=`e25fdb44`（=origin/main，0/0）。全部產物未 commit。
- 正本對照：BB advisory memo、QC discipline memo、四份 E1 報告（全文讀畢）；**不信報告讀真代碼**，全部測試親跑。
- 範圍外（E2-A 線，未審）：memory_distiller / V139 / V140 / l2_memory_distill* / checks_l2_memory / runner.py / helper_scripts/memory/seed_agent_memory*。
- brief 路徑筆誤註記：brief 寫 `helper_scripts/memory/mnemopi_seed*`，實物在 `helper_scripts/mnemopi_seed_from_memory.py`（`helper_scripts/memory/` 是 E2-A 線檔案）；按實物審。

## VERDICT：RETURN to E1（4 個 finding 待修：1 MEDIUM + 3 LOW；其餘全 PASS-grade）

無 CRITICAL / HIGH。四件交付的 spec 合規與核心安全不變量全部實證成立；退回項全為小範圍修補（合計 <20 行 + 1 條 TODO 行），修畢即可過 E4。

## 測試計數（親跑，Mac venvs/mac_dev py3.12）

| Suite | 結果 | vs E1 報告 |
|---|---|---|
| test_watchdog_alert（22 既有+6 新）+ test_engine_watchdog + test_incident_sentinel | **126 passed**（28+40+58） | 一致 |
| test_bybit_announcement_sentinel | **53 passed** | 一致 |
| test_polymarket_axis | **41 passed + 1 skipped**（opt-in 煙測） | 一致 |
| test_polymarket_axis_cron_static | **11 passed** | 一致 |
| research/tests 全套回歸 | **254 passed + 1 skipped, 0 failed** | 一致 |
| analyze_token_usage | py_compile + `--help` + 真 session 重跑 + **我自建合成 fixture 斷言全過** | 一致（會計修正全 bite） |
| mnemopi seed `--dry-run` | **200 = 101 topic + 99 bullet** | 一致 |
| `bash -n` × 4 cron 檔 | 全過；exec bit 全在 | 一致 |

## 攻擊面逐項結論

### ① engine_watchdog.py sink diff（最高危）

- **原 best-effort 對外契約零變化（實證）**：test diff 純 append（+126/−0，僅 MODULE_NOTE 一行 context）；既有 22 測試斷言未動全綠；函數仍恆回 None、永不拋、fire-and-forget 不阻塞（hanging-urlopen 測試 <5s 返回）。
- **sink 在 channel 之前 + try/except 全包（實證）**：mkdir-失敗（alerts 為普通檔）→ FileExistsError ⊂ OSError ⊂ Exception 被吞、遠端發送照常（test_sink_io_failure 用真 I/O 故障證）；磁碟滿/權限拒同屬 OSError 同路徑。creds-load-fail 分支也落 sink（channels_attempted=[]）。
- **輪轉**：`with_suffix(".jsonl.1")` 親驗產出 `alerts.jsonl.1`；>5MB 真 5.6MB 檔測試蓋。兩進程 race：append O_APPEND 單行短寫實務原子；輪轉互撞最壞早丟一代 .1（docstring 已聲明保一代）→ INFO 可接受。
- **全鏈 composition 我親跑**：`run_once`（alert_fn=None 真 resolve）→ `engine_watchdog._send_alert_best_effort` → `<data_dir>/alerts/alerts.jsonl` 真落一條（無 creds 場景），subject/body/channels_attempted 欄位全對 — 補上單測只有「identity 斷言+簽名 smoke 兩半拼接」的縫。
- **洩密面（轉 E3，先標）**：body 原樣落盤 ≤2000 字。我構造 token 樣式字串入公告 title → **原樣進 alerts.jsonl 與 INFO log（實證）**。內容類別=watchdog state 欄位（含 `last_failure_reason` 內嵌 restart `stderr[-500:]`）+ 哨兵外部公告 title/url；同類內容**本就**持久在 watchdog_state.json 且本就送遠端通道 → 無新增洩漏類別。E4/E3 後續照 secret-leak pattern 掃一輪即可。

### ② Bybit 公告哨兵

- 首輪 baseline 兩分支（缺檔/壞檔→空 state→baseline）測試蓋且自癒；`baseline_done=true 但 seen 被毀` 的洪水場景受 MAX_ALERTS_PER_RUN=10+1 彙總 cap 封頂（INFO）。
- 去重鍵：query/fragment/trailing-slash/scheme+host 大小寫變體同鍵（測試蓋）；path 大小寫保留=寧重報；sha256 fallback 含 publishTime（edit 改 publishTime→重報，BB 裁決可接受）。
- 90d 修剪：仍在 page-1 的 >90d 項修掉會重告 — docstring 誠實聲明「寧重報不漏報」（BB §4 一致），非 bug。
- state 寫入原子（tmp+os.replace，mirror incident_sentinel 親比對成立）；fail-quiet 不吞 state（失敗輪 state 照寫、不耗 baseline、恰 1 call、第 8 輪恰 1 條 meta-alert — 測試全蓋）。
- watermark 禁令=行為證明（更舊未見件仍告警）+ tokenize 剝註解輔證 — 測試法正確。
- **type.key=="" 寬網 P1 裁決：合理**。BB §2「寧誤升不漏降」明文；live 實證該類=行銷文，P1=WARN 通道，噪音可控且 E1 誠實披露降級規則留 operator。
- cron wrapper/installer 與 incident_sentinel 形一致（diff 親比對；差異=零 PG secrets 段，documented）；獨立 APPLY env `OPENCLAW_BB_SENTINEL_CRON_APPLY` 防殘留誤裝=好決策；installer cron-env 字元驗證齊。
- 字典 §1.11+§4.1 落地與 BB §7 草稿一致，佔位符已填、欄序適配正確、live 陷阱 5 補錄。

### ③ polymarket 對 QC memo 逐條

- 零 relevance 截斷：tokenize-strip 7 禁字結構測試 + 零過濾行為測試 + 真煙測 596 行/146 closed kept/0 parse_error（我重讀原始 jsonl 驗證）。
- append-only：`mkdir(exist_ok=False)` 真 raise（測試蓋）；lane 互斥 write_run 三向 raise + retro run 檔案集親驗只有 prices_history。
- track-to-resolution 終態機：resolved 判據=`closed && umaResolutionStatus=="resolved"`（probe 實證）；終態永不回退（測試蓋）；lost 30 連敗防無界；follow_up_ids 排除 seen+終態。
- R-0 紅線：imports 全 stdlib（我 grep 窮舉）；硬邊界 token 0；零 auth header；host allowlist fail-closed raise。
- 真煙測 artifact 我逐檔重驗：**3 個 run 的 manifest sha256 index 全 OK**；lane/retrospective/point_in_time 旗標全對。
- 25 keywords 與 QC memo §2 逐字一致；manifest 欄位全集對齊 §3。
- 存儲披露：per-row raw 設計 20-50MB/day vs memo「數 MB」— E1 已誠實披露，40TB NAS 下非阻斷；瘦身建議列 P-3（LOW 不擋）。
- cron：兩模式共用單鎖（直接封死 daily/hourly state race）；hourly 默認註釋停用+獨立活化 env=QC §3 operator 域正確落地。

### ④ analyze_token_usage.py

- 三會計修正讀碼+**我自建合成 fixture 親證 bite**：同 id 流式兩行 output 5→99 取 99（非 104）；agent transcript 權威（agA=300 取自 transcript，**非** toolUseResult 的 500 — seen_ids 互斥真防雙計）；無檔 agent fallback 恰計一次標 `last_call_only`；bad_json=2/missing_usage=1/fallback_agents=1 計數全對。
- 零寫入（唯一 open 全 read mode）、純 stdlib、`--help` 過、真 session 重跑（live session 已增長：61→68 calls 單調一致，無法 byte-exact 屬預期）。
- 跨平台：transcript 目錄 `parents[2]`+正則編碼動態推導，0 硬編 user 路徑。

### ⑤ mnemopi 試點

- **冪等機制讀碼驗真**：= `bank delete` + `bank create` 整 bank 重建（非 upsert/dedup），MODULE_NOTE 誠實聲明；與報告「重跑仍 200 非 400」實證一致。dry-run 200=101+99 我親跑。
- 協議檔退出三步完整（npm rm -g / rm -rf 數據目錄 / 刪 .mcp.json 條目，+可選 brew uninstall bun）。
- `.mcp.json` 實物在 `/Users/ncyu/Projects/TradeBot/.mcp.json`（git 確認 *outside repository*，結構性不入 git）；env 三閘在、零 key 傳遞。
- **零外連證據鏈實物複驗一點**：installed `@oh-my-pi/pi-mnemopi@15.11.2` 的 `src/core/embeddings.ts` — `embed()`:372 / `embedQuery()`:355 入口 `embeddingsDisabled()`（=`$flag("MNEMOPI_NO_EMBEDDINGS")`:110）短路 return null，`embedApi`:248 不可達 — 與報告聲明逐行一致。
- seed 腳本防禦縱深（env 剝 8 個 key/url）+ fail-loud（bank create 失敗 exit、JSON-RPC error raise）。

### ⑥ 全範圍

- SCRIPT_INDEX/memory.md：線 W/P **未動**（待合併行在各自報告，PM merge 時須折入，否則 CLAUDE §七「新腳本必更新 SCRIPT_INDEX」在 commit 時點不滿足）；線 ③④ 按**其各自任務契約**動了（diff 親驗 append-only、AEG-S3 並行內容零 clobber）。與本次 E2 brief「未動紀律」字面衝突=**派工契約口徑不一致**，列 CONFLICT 交 PM 裁決（非 E1 違紀：兩線報告均載明其契約要求登記）。
- 硬編碼 user 路徑 0（命中全為負面斷言測試行=政策反例豁免）；中文 MODULE_NOTE/注釋全；`except:`/f-string log/detail=str(e) 全 0；測試計數與報告全一致。

## Findings 全量表

| # | severity | confidence | 位置 | 描述 | 修法 |
|---|---|---|---|---|---|
| MED-1 | MEDIUM（process） | HIGH | `helper_scripts/canary/engine_watchdog.py`（2088→2150 行） | 觸碰前已超 2000 hard cap，本 diff 再 +62；TODO/governance 無 documented exception 或 split follow-up（grep 證） | 補一條 TODO split follow-up 行（或記 documented exception）；不要求本 diff 改碼（「exact-touch 默認補 split follow-up」前例） |
| W-3 | LOW | HIGH | `bybit_announcement_sentinel.py:356-366` `format_alert` | 外部公告 title/url 不剝控制字元/換行 → 可注入多行偽 log 行（watchdog INFO 行 log subject，我實證原樣透傳）與 Telegram text 偽段；alerts.jsonl 本身 json-escaped 安全 | title_trunc/url 過 `re.sub(r"[\\r\\n\\t]+", " ", …)` 後再截斷 |
| P-2 | LOW | HIGH | `polymarket_axis/state.py:102,114` | `entry["status"]` 直接下標：load_state fail-soft 接受任意 dict entry，缺 status 鍵 → KeyError 毀整輪 sweep（連 snapshot 全丟），與模塊自身「snapshot 丟一天少一天」fail-soft 立場不對稱 | 兩處改 `entry.get("status")` |
| W-2 | LOW | HIGH | `engine_watchdog.py:702-703, 784-786` | sink append 失敗只 logger.debug（默認 INFO 級不可見）且 unconfigured 分支 INFO 行恆稱「alert recorded to local sink」——sink 壞+無 creds 時告警實際全丟而 log 聲稱已記錄（觀測面說謊；淨行為仍不劣於改前） | `_append_alert_sink` 回傳 bool；INFO 行據實措辭；失敗升 warning（可一次性/節流） |
| S-1 | LOW | HIGH | 線 W cron 兩件套 | 無 shell 靜態測試（sibling 線 P 有同型 `test_polymarket_axis_cron_static.py` 11 條；W 只 `bash -n`） | 建議補同型 static 測試（可併 follow-up，不擋） |
| P-1 | LOW | HIGH | `artifact.py:246-253` + `/tmp/pm_axis_smoke/.../smoke-daily-1page/` | parquet 殘檔清理分支零測試覆蓋；smoke daily run（22:19）留 **0-byte raw_events.parquet 殘檔**=清理修復**前**產物（manifest 記 failed 但檔在=正是註解警告的誤認場景），hourly run（22:20）證清理已生效 | 補一條 conversion-fail→partial+殘檔 unlink 測試；scratch 殘檔可代清 |
| P-3 | LOW（任務指定列出） | MEDIUM | snapshots.jsonl per-row `raw_market` | 與 run-level raw_events.jsonl 的 event.markets 雙存（events_tag 行重複）→ 存儲約可省 ~40%：僅 follow_up 行帶 raw_market（該行無 raw_events 對應）或 raw_events 去 markets 鍵 | 研究端便利取捨，不擋 |
| W-4 | INFO→E3 | HIGH | alerts.jsonl | body 原樣持久 ≤2000 字（含 restart stderr 片段/外部公告文本；token 樣式字串實證原樣落盤）；無新洩漏類別（同內容本就在 watchdog_state.json+遠端通道） | E3 secret-leak pattern 掃描照律 |
| W-5 | INFO | MEDIUM | sink 輪轉 | 兩進程輪轉互撞最壞早丟一代 .1；append 原子性實務足夠 | 可接受（docstring 已聲明） |
| W-6 | INFO | HIGH | E1 報告 §2 | engine_watchdog.py 報「+68」，numstat 實 +65/−3 | 報告精度註記 |
| S-2 | INFO | HIGH | 哨兵 `--dry-run` | dry-run 照寫 state=消耗公告 newness（help 文檔已明示；installer 預檢導向 scratch dir 規避）；meta-alert 在 dry-run 不印 would-alert | 可接受；後者可加 print（cosmetic） |
| S-3 | INFO | MEDIUM | `_env_float` | 接受負值 → `time.sleep(-1)` ValueError 崩單輪（僅 operator 誤配置；wrapper fail-soft 兜底） | 可選 clamp ≥0 |
| P-4 | INFO | MEDIUM | state.py | closed-但 UMA 永不 resolved 的 market 永留 TRACKING→follow-up 緩慢累積（QC spec 即要求追到 resolution；lost 僅蓋 fetch-error 軸） | as-spec；研究端觀察 |
| P-5 | INFO | HIGH | collector.py `_safe_float` | 0 生產 caller（僅測試引用）；QC memo 指名保留 attribution，可接受 | 無動作 |
| A-1 | INFO | HIGH | analyze_token_usage.py | 無 checked-in 測試（E1 合成邊界探測未入庫不可重現；本輪我已重做合成驗證補位） | 可選補一檔輕量測試 |
| M-1 | INFO | HIGH | mnemopi_seed:82 | `/opt/homebrew/bin` fallback=機器類別路徑（非 user 路徑；Mac-only 試點工具） | 可接受 |
| M-2 | INFO | MEDIUM | mnemopi_seed `reset_bank` | delete 失敗被忽略；若未來版本 create-on-existing 成功會破冪等（當前版本實證無此問題；協議已要求升級重審計） | 試點期可接受 |
| M-3 | INFO | LOW | mnemopi_seed `client.tool` | 先 json.loads 再查 isError——error payload 非 JSON 時拋 JSONDecodeError 而非 RuntimeError（fail-loud 方向不變） | cosmetic |
| C-1 | CONFLICT（交 PM） | HIGH | SCRIPT_INDEX/memory.md | E2 brief「全範圍未動紀律」vs 線 ③④ 任務契約明令登記（append-only 無 clobber 親驗）——派工口徑不一致非 E1 違紀 | PM 裁決口徑；merge 時折入 W/P 待合併行 |

## §5 multi-session race check：5/5 PASS

- 5a：`git fetch --prune` 後 HEAD==origin/main `e25fdb44`（0/0）；時間窗 sibling push 全為 AEG-S3 panel（file scope 與本批 0 overlap）。
- 5b：髒樹 48 entries = 本批四線 + E2-A 線 + BB/PA/QC memo/memory（各有 owner），無不明外洩檔。
- 5c：3 條 stash 全 pre-existing 已標註，未碰；未做任何 git 寫操作。
- 5d：本報告檔為唯一新增（untracked），無 commit 行為。
- 5e：審查結束再 fetch=0/0，期間無 sibling push；我的全部探針（composition probe/合成 fixture/煙測重驗）均在 /tmp，樹零改動（前後 status 計數一致=48）。

## 退回 E1 修復清單

1. **MED-1**：TODO.md 補 engine_watchdog.py split follow-up 一行（或在 governance 記 documented exception）。
2. **W-3**：`bybit_announcement_sentinel.py:356-366` format_alert 對 title/url 剝 `[\r\n\t]` 再截斷（+1 條注入測試）。
3. **P-2**：`polymarket_axis/state.py:102,114` `entry["status"]` → `entry.get("status")`。
4. **W-2**：`engine_watchdog.py` sink 失敗觀測面據實（回傳 bool + INFO 行措辭 + 失敗升 warning）；對應調整 TestAlertSink 斷言。

S-1 / P-1 / P-3 / A-1 可併本輪或開 follow-up（不擋 re-review）。修畢 narrow re-E2（只審 delta）→ E4。

— E2，2026-06-11。
