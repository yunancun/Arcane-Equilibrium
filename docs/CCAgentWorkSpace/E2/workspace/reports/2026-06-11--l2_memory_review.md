# E2 對抗審查 — L2 記憶層（M1 SQL+package / M2 cron+seed）· 2026-06-11

- 審查者：E2（線 A）
- 對象：工作樹未 commit 改動（兩條 E1 線）：`sql/migrations/V139__agent_memory_store.sql`、`program_code/learning_engine/memory_distiller/**`（9 source + 10 test 檔）、`helper_scripts/cron/l2_memory_distill*`（三件套+test）、`helper_scripts/memory/seed_agent_memory.py`（+test）、`helper_scripts/db/manual_V140*`（.sql/.sh/+test）、`helper_scripts/db/passive_wait_healthcheck/checks_l2_memory.py`（+test）、`runner.py`（+19 行 [88][89] 接線）
- 正本：PA spec `docs/CCAgentWorkSpace/PA/workspace/reports/2026-06-11--l2_memory_layer_design.md`；E1 報告 ×2（M1/M2 同日）
- 測試環境：`venvs/mac_dev/bin/python`（3.12）
- **VERDICT：RETURN to E1（M1 線）— 1 MED + 3 LOW；M2 線 0 actionable（3 自裁決全 PASS）。0 CRITICAL / 0 HIGH。**

## 1. Stage 0 spec 合規（逐項，先於質量審查）

| spec 項 | 結果 |
|---|---|
| V139 DDL（§2.2） | PASS — 與 spec 逐行一致 +2 處誠實附註（同名巧合警示、Guard B tsvector 反射說明，後者經 PG information_schema 定義核實正確：pg_catalog 型 format_type 反射、extension 型才 USER-DEFINED） |
| V140 路徑 B（§3.2） | PASS — manual .sql（V139 前提守門 + udt_name Guard B' + 全 IF NOT EXISTS）+ .sh applier（退出碼 0/1/2/3/4 分類）；不入 sqlx 鏈防 fail-stop；§13.2-2 dry-run 裁決仍 owed E4（先走 B = 保守超集，A 成立亦無害） |
| memory_distiller 8 模組（§4） | PASS — 全部 <800 行（最大 pipeline 593）；行數預算超出已在 M1 D3 誠實披露 |
| 兩段 prompt（§5） | PASS — spec 全文落地；對照 TencentDB 原版（`/tmp/repo-eval/.../l1-extraction.ts`/`l1-dedup.ts`）：寧缺毋濫/獨立完整/歸納合併保留；source_ids 反編造**強於**原版；「背景禁抽取」結構性 N/A（本設計無 background 段）；「merged_timestamps 並集」為 spec 層有意以 source_refs 並集 + supersede 全史鏈取代（原則 8 等價）；原版無 OpenClaw 字樣、E1 三處加同名巧合警示 |
| 管線流程/游標/cap（§6） | PASS — 窗=(cursor+1)..昨日、回看 cap 7、LIMIT 200/20、4KB 截斷、池空短路省 call、單裁決一事務全對；列名對 V134/V131 DDL 逐欄核實（trigger/parsed_output/raw_response/report_jsonb 等全存在） |
| embedding 軸（§7） | **MED-1（見 §4）** — 模組本體合格（body 無 dimensions、404→unavailable、批次切分、漂移三元組），但生產鏈零建構點 |
| B3 接縫（§8） | PASS — `recall_for_prompt` 簽名與 spec 釘死契約逐字一致；0 production caller（grep 證 dormant）；zero engine diff（layer2_engine 0 改動） |
| seed CLI（§9） | PASS — 兩源映射/雙層敏感網（+IGNORECASE 加嚴安全向）/冪等錨 sha12/默認 dry-run 0 連線/寫後中英 recall 驗收 0 命中 exit 1 全對 |
| flag 表（§10） | PASS-with-MED-1 — PIPELINE 守 CLI 連 DB 前 + run_daily 入口雙層；CRON_APPLY 守 installer；EMBED_BACKFILL 有 gate 無 functional consumer（MED-1） |
| cron 三件套（§11） | PASS — mirror incident_sentinel 逐項（lock/stale 180min/heartbeat/secrets grep-parse/fail-soft exit 0 = spec 明定）+ 日誌輪轉（PM 加項）；installer Linux-only/dry-run 預設/APPLY gate/--remove/idempotent refuse/env 值校驗 |
| healthcheck [88][89]（§12） | PASS（偏差從 PM，見 §3 裁決 1）— runner 三處最小 edit，[88][89] 號占用正本落註冊清單 |
| 測試計劃（§13.1/13.3） | PASS — 110+78 全綠親跑；6 mutation 錨中 5 個親自注入驗 bite（§5） |
| 派工切分（§14） | PASS — 兩線檔案零重疊屬實；seed 不 import M1（自帶 SQL）；SCRIPT_INDEX/E1 memory 條目備好待 PM 合併（owed，commit 前必折入） |

**漏建/超建**：漏建=event_start/event_end 永不被填（LOW-2）；超建=healthcheck 真 check（從 PM 裁 PASS）、run_daily 雙模式+入口 flag 閘（接縫必需+fail-closed 加層，PASS）、日誌輪轉/路徑 detector（PM 加項）。其餘 0。

## 2. 攻擊面結果（dispatch 指定 7 項）

1. **兩線接縫 — PASS（實證）**：CLI `run_daily(conn, llm, target_date=day)`（cron/l2_memory_distill.py:222）vs `run_daily(conn, llm, *, target_date=None, now=None, state_path=None, embed_client=None)`（pipeline.py:91）咬合；target_date 模式 0 游標檔觸碰（`_run_single_day` 無 `_read/_write_cursor` 呼叫）、失敗 raise RuntimeError；缺省模式成功才 `_write_cursor`。mutation B（raise→return dict）→ `test_target_date_mode_failure_raises_for_cli_cursor_discipline` 精準紅。seed INSERT 列集 `(record_id, content, mem_type, priority, scene, source_refs, metadata)` 對 V139 DDL 逐欄核：NOT NULL 全滿足、CHECK（mem_type/priority/status+supersede_link）全滿足、與 M1 store `_INSERT_SQL` 契約一致（store 多 event_* 三欄，皆合法）；ON CONFLICT (record_id) DO NOTHING 撞 PK 冪等。
2. **V139 DDL 對抗 — PASS + 2 INFO**：supersede CHECK 只鎖 status↔指針配對，自指/環 DDL 層不擋（INFO-1：spec 原樣，應用層不可達——target ⊆ DB 召回 active 集、新 id=fresh uuid、supersede SQL `AND status='active'` 防重指）；REVOKE DELETE FROM PUBLIC 宣示性（新表 PUBLIC 本無 DELETE；有效防線=trading_ai 顯式 GRANT 排除 DELETE，mirror V133/V134；content 不可變靠 application discipline+測試，column-level GRANT 可加固=INFO-2）；雙 apply 靜態冪等成立（全 IF NOT EXISTS+Guard 反射式），Linux 真驗 owed E4；`to_tsvector('simple', content)` 雙參形 IMMUTABLE 合法生成列。
3. **fail-open 方向 — PASS（mutation 證）**：extraction 整體壞損→ok=False→游標不推進（mutation E 反轉→4 紅）；單條壞損→丟棄（寧缺毋濫）；source_ids 缺/越界→整條丟（反幻覺）；dedup 全路徑（壞 JSON/缺欄/非法 action/越界 target/漏答/重複 rid）→降 store 絕不丟（mutation A 反轉→9 紅）；幻覺 record_id：target_ids 必 ⊆ 該候選關聯列表（DB 真實 rows），未知 rid 行直接忽略走漏答降 store。方向零接反。
4. **flag 紀律 — PASS-with-MED-1**：CLI flag gate 先於重 import/DB（forbid 注入測試證）；run_daily 入口雙層；healthcheck flag-OFF=PASS-skip 且 0 DB 查詢（僅 rollback）；import 安全親證（毒 socket 下 import package+pipeline+recall OK）；**原則 #7 grep 證**：全部寫語句目標僅 `agent.agent_memory`（17 INSERT/5 UPDATE）+ `agent_memory_embedding_meta`（5 INSERT），零既有表寫入；DELETE FROM 僅出現於負向測試斷言。
5. **M2 三自裁決 — 全 PASS**（§3）。
6. **prompt 質量 — PASS**（§1 表）。
7. **測試 bite — PASS**：5 mutation 全 bite（§5）；行數全 <800；注釋中文優先（MODULE_NOTE 全檔齊、why 註釋到位）；0 硬編路徑/0 邊界 token/0 f-string log/0 裸 except（`_safe_rollback` 帶 noqa+rationale 屬既有範式）。

## 3. M2 三個自裁決（報告 §7/§8）裁定

1. **[88][89] 真 check vs spec reserved 註釋 → PASS（從 PM 正確）**。spec §12 反對實作的理由=「dormant 系統無 runtime 可監測，假 check=噪音」；實作以 flag-OFF→PASS-skip 結構性解掉噪音顧慮（flag-OFF 路徑 0 查詢），flag-ON 即時切真檢；runner pin test（test_l2_memory_healthchecks.py:181）防 silent-dead；號占用正本落 runner 註冊清單（V137/[82] 撞號教訓履行）。prompt>spec 優先序正確。
2. **seed 自帶 INSERT SQL 不 import M1 → PASS（從 spec 正確）**。spec §9/§14 兩處明示；親驗列集/CHECK/conflict 行為與 V139+M1 store 三方一致（§2-1）。
3. **接口假設 run_daily(conn, llm, *, target_date) → PASS**。M1 已按此落地；TypeError 接縫 log 真存在（CLI:224-230）且有測試（test_interface_mismatch_typeerror_exit1）。

M1 偏差 D1-D8 全裁 PASS（D1 接縫 mutation 證；D2 雙層 fail-closed，E4 flag 前置已標；D7 親驗：OllamaClient.generate 簽名確為 `timeout: int|None`（ollama_client.py:198-208）、ABC 為 `timeout_s`，內省適配有據；OllamaResponse 確有 .text/.success）。

## 4. Findings（全量，含 LOW/INFO）

| # | 嚴重性/信度 | 位置 | 描述 | 修法方向（不代寫） |
|---|---|---|---|---|
| MED-1 | MED / 高 | `pipeline.py:91-185`（invocation owner）；`cron/l2_memory_distill.py:222`；`embedding.py:38` | `OllamaEmbeddingClient` 全 repo 零非測試建構點（grep 證：僅 `__init__` re-export+test）。CLI 不傳 embed_client → run_daily 默認 None → `run_backfill(conn, None)` 恆回 `embed_unavailable`、recall L1 永不嘗試。即使 V140 applied+bge-m3 pulled+`EMBED_BACKFILL=1`，補嵌永不執行、meta 永不建立、[89] 永停過渡態。flag 有 gate 無 functional consumer = dead param（違 feedback_no_dead_params）；embedding.py:80-82「pull 後自動升級無需代碼變更」在集成層不成立。**MIT 並行 ratify 線獨立收斂同一 finding（F-1/C-3），雙線交叉證實。**spec 未指派建構責任=spec gap，但 dead-param 治理優先 | M1：backfill flag=1 且 embed_client is None 時 lazy 建構默認 `OllamaEmbeddingClient()`（同 package 零新依賴），並 thread 進 recall 路徑；+1 測試釘「flag=1 無注入 client 仍走到 embed 請求」（mock urlopen）。替代裁決=接受 MIT C-3（backfill flag-ON 前修），PM 拍 |
| LOW-1 | LOW / 機制高、生產觸發低 | `pipeline.py:115-116` vs `cron/l2_memory_distill.py:180` | target_date 模式 flag-disabled 回 dict 不 raise；CLI gate 有 `.strip()` 而 pipeline gate 無 → env 值 `"1 "`/`"1\n"` 時 CLI 放行、pipeline 回 disabled、CLI「無例外=成功」推進游標=該日靜默跳過。installer 已驗 flag 限 0\|1 故安裝路徑安全；手動 crontab 編輯/直呼 run_daily 可達 | M1：pipeline gate 補 `.strip()`（1 字修）；可選 target_date 模式 disabled→raise（與單日失敗語義一致） |
| LOW-2 | LOW / 高 | `pipeline.py:496-508`；V139 `event_start/event_end` | extraction prompt 指示 LLM 在 metadata 填 activity_start/end_time（ISO 8601），MemoryRecord/store 支持 event_start/event_end，但 `_record_from_candidate` 與 merge 路徑永不解析填入 → 兩 typed 欄從管線恆 NULL，spec §2.1「可解析時填…供範圍查詢」死欄位。spec §6.3 未列解析步=E1 spec-literal，歸 spec gap | M1：metadata 兩鍵可解析 ISO 時填 event_start/end（~10 行+test）；或 PA 出 erratum 標 reserved。PM 擇一 |
| LOW-3 | LOW / 高（機制親驗） | `checks_l2_memory.py:69-109` + `pipeline.py:260-276` | 語義性死亡不可見：no-op 日（兩源空）與「extraction 全 dropped」日皆 ok=True 推進游標 → 上游 l2_calls writer 死/parser 全丟時 [88] 恆 PASS 而記憶零累積（rows= 在訊息中無增量斷言）。**MIT F-4 同源**；非阻斷（學習平面、l2_calls 現僅 1 row） | M2（MIT 方向）：CLI 落 last-run summary JSON（stored/materials/dropped）於游標旁，[88] 引用「連續 N 非 no-op 日 stored=0」WARN；可隨 MED-1 輪一併或開 follow-up |
| INFO-1 | INFO / 高 | V139:95-98 | supersede CHECK 不擋自指/環/懸空指針（無 FK）；應用路徑不可達（§2-2）；spec 原樣非 E1 偏差 | E4 scratch 可加對抗 UPDATE 探針；長期可考慮自參照 FK |
| INFO-2 | INFO / 高 | V139:160-170 | REVOKE FROM PUBLIC 宣示性；content 不可變靠 application discipline；column-level `GRANT UPDATE (status,…)` 可 DB 層加固 | spec-level 備忘，不阻本批 |
| INFO-3 | INFO / 高 | `parsing.py:273` | merged_priority 無分類型 floor（extraction 才有）——LLM 可在 merge 時把高 priority 記憶降至任意 [-1,100]；degradation 有界（row 仍 active），spec 未定 | 可選：merge 後 priority 也過 floor |
| INFO-4 | INFO / 高 | `pipeline.py:312-318` | D6：dedup 段 LLM 不可用（非 parse fail）也 fail-open-to-store=spec 未明定的同向擴展；persistent Ollama-down 時 extraction 先失敗，觸發窗極窄 | 接受（已披露） |
| INFO-5 | INFO / 中 | wrapper:20 / installer:32 | DATA 默認 `/tmp/openclaw`（sibling 同款慣例）：reboot 丟游標→視同首跑只補昨日，中間日缺口（非重複）。dormant+學習平面低風險 | operator 安裝時指定持久 DATA dir 即解；備忘 E4 runbook |
| INFO-6 | INFO / 高 | `prompts.py:167-175` | truncate_text 對「已帶 marker 文本再經更小 limit」會切掉 marker；生產路徑同 limit 冪等，邊角不可達 | 無動作 |
| INFO-7 | INFO / 高 | SCRIPT_INDEX.md / E1 memory.md | 兩線皆未動（多 session 安全策略）；M2 §9/§10 已備好待合併行。spec §4 要求更新 ⇒ **PM commit 前必折入** | PM |
| INFO-8 | INFO / 高 | installer:53 | `--remove` 當 marker 為唯一 crontab 行時 `grep -v` 空輸出→pipefail→腳本提前死（crontab 已清但無 REMOVED 確認）；sibling installer 同款=範式繼承 | 可選 follow-up（兩 installer 一起） |

## 5. Mutation 親跑（5/5 bite；untracked 檔以 cp+shasum 備份還原驗證）

| 錨 | 注入 | 結果 |
|---|---|---|
| A（spec ①）dedup fail-open→skip | `_store_fallback` action 改 skip | **9 紅**（parsing 8 + pipeline `test_dedup_bad_json_all_store_fail_open`） |
| B（接縫）單日失敗不 raise | `_run_single_day` raise→return | **1 紅**（`test_target_date_mode_failure_raises_for_cli_cursor_discipline` 精準）；M2 cron 24 測仍綠（mock pipeline，接縫由 M1 側鎖=正確分工） |
| C（spec ④）merge 不 supersede | supersede 呼叫削除 | **1 紅**（`test_merge_inserts_new_row_and_supersedes_old_without_delete`） |
| D（白名單）supersede SQL 加 content='' | `_SUPERSEDE_SQL` SET 加欄 | **2 紅**（含動態掃全 UPDATE 常數的 `test_all_update_statements_touch_only_whitelisted_columns`） |
| E（spec ⑥）extraction 壞 JSON→ok=True | parse 例外分支反轉 | **4 紅**（parsing 1 + pipeline 游標三測） |

還原後全套回 **110 passed**；三檔 shasum 與備份逐一比對一致，備份已清。

## 6. 回歸與環境

- 新套件 110 + M2 四檔 78 全綠親跑；`learning_engine` 全樹 **513 passed**（=403 既有+110 新，算術守恆）；healthcheck 鄰接四檔 **125 passed**；runner 真 import OK；bash -n ×3 過；import 毒 socket 親證零網路。
- `recall_for_prompt`/`run_daily` production caller grep：CLI 唯一（dormant 接縫 0 caller=spec 預期）。
- ml_training 712 由 M1 自報未重跑（memory_distiller 不被 ml_training import，learning_engine 全樹綠覆蓋集成面）——標註為採信項。

## 7. E4 owed（Linux，本批 sign-off 前置）

M1 §6 全清單成立 + 補三項：①V139 scratch 雙 apply+Guard A 漂移表探針+trading_ai DELETE 拒絕實證；②§13.2-2 `CREATE EXTENSION vector` 權限裁決（路徑 A/B 終局）；③seed `--apply` 入 scratch + 中英 recall 真命中（注意 `SET LOCAL %s` psycopg2 客戶端插值=layer2_critic:346 已 prod 驗證範式）；④直呼 run_daily 須 `OPENCLAW_L2_MEMORY_PIPELINE=1`（M1 D2）。

## 8. §5 race check（5/5 PASS）

- 5a/5e：fetch 後 HEAD==origin/main `e25fdb44`（0/0）；窗內 origin 推送全 AEG-S3 線（file scope 零重疊）；review 期間 0 sibling push 進 origin；工作樹期間出現 sibling 產物（MIT ratify 報告、E2 線 B 報告、多角色 memory.md）=docs-only 零代碼 overlap，MIT 結論與本審交叉比對已納入（MED-1 收斂、F-4 採納為 LOW-3、trigger 非保留字/SET LOCAL 可參數化兩項獨立結論一致）。
- 5b：本審 0 寫入 production 檔（mutation 全還原 shasum 證）；新增僅本報告+memory 追加。
- 5c：3 條 pre-existing stash 未動。
- 5d：報告 commit 歸 PM。

## 9. 結論

**RETURN to E1（M1 線）**：MED-1 + LOW-1 + LOW-2（LOW-3 可併輪歸 M2 或開 follow-up，PM 拍）。核心架構（接縫/fail 方向/supersede 紀律/flag 紀律/原則 #7）全部實證成立，0 CRITICAL/HIGH——預期為小修一輪後 narrow re-review 直通 E4。

### 退回修復清單
1. **[MED-1]** `pipeline.py` backfill/recall 路徑：embed_client is None 且 backfill flag=1 時 lazy 建構 `OllamaEmbeddingClient()` + 測試釘 reachability（或 PM 採 MIT C-3 binding-condition 改判）。
2. **[LOW-1]** `pipeline.py:115` flag gate 補 `.strip()`；可選 target_date+disabled→raise。
3. **[LOW-2]** metadata activity_*_time→event_start/event_end 解析填入（或 PA erratum 標 reserved，PM 擇一）。

E2 REVIEW DONE: RETURN to E1(M1) · report path: docs/CCAgentWorkSpace/E2/workspace/reports/2026-06-11--l2_memory_review.md
