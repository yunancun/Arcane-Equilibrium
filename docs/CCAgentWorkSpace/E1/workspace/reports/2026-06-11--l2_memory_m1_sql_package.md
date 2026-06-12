# E1(M1) — L2 記憶層「SQL + Python package」半邊 IMPL 報告

- 日期：2026-06-11
- 角色：E1（線 M1）
- spec 正本：`docs/CCAgentWorkSpace/PA/workspace/reports/2026-06-11--l2_memory_layer_design.md`
- 基準：local main = origin/main `5c37ba48`（fetch 後驗證；V139 仍 free，head=V138 兩端一致）
- 狀態：**IMPL DONE，待 E2 → E4（Linux dry-run owed）**；未 commit、未動 SCRIPT_INDEX.md、未動任何 memory.md（PM 統一）

## 1. 任務摘要

按 PA spec E1-A 線實作：V139 migration + `learning_engine/memory_distiller/` 全 package + 單元測試。V140 不歸本線（dispatch 鐵則「零 pgvector 依賴」；樹上已見 M2/E1-B 落了 manual V140 路徑 B 檔，零重疊未碰）。B3 只留 dormant 接縫（zero engine diff，`layer2_engine.py` 0 改動）。

## 2. 檔案清單（全新檔，0 個既有 tracked 檔被改）

| 檔 | 行數 | 內容 |
|---|---|---|
| `sql/migrations/V139__agent_memory_store.sql` | 221 | spec §2.2 DDL 直抄 + Guard A/B/C（V133/V134 範式）+ DELETE REVOKE + supersede CHECK + tsvector('simple') 生成列 + 雙 GIN + 同名巧合警示 |
| `program_code/learning_engine/memory_distiller/__init__.py` | 63 | public API 導出 + MIT attribution + 同名巧合警示 |
| `…/prompts.py` | 244 | spec §5.1/§5.2 兩段 prompt 全文 + `format_extraction_prompt`/`format_batch_dedup_prompt` 純函數 + 截斷 helper；MODULE_NOTE 含 TencentDB MIT attribution（prompt 抄改處）+ OpenClaw 同名巧合警示 |
| `…/parsing.py` | 282 | fence 剝除/白名單校驗/**extraction fail-to-skip**/**dedup fail-open-to-store**/priority clamp+分類型 floor/source_ids 強制溯源/target_ids 越界降 store |
| `…/store.py` | 215 | `MemoryStore`（conn 注入、零模組級連線、caller 控事務）：INSERT ON CONFLICT 冪等/supersede 三欄 UPDATE/補嵌寫回/meta 單行 upsert/V140 欄探測；**全模組零 DELETE FROM** |
| `…/recall.py` | 235 | 三級降級 `recall_top_k`（vector→FTS 雙路 GREATEST→skip；兩 except 不冒泡）+ `RecallBundle` + `recall_for_prompt`（spec §8 釘死簽名，lazy db_pool，fail-open 空 bundle） |
| `…/embedding.py` | 174 | `OllamaEmbeddingClient`（urllib；**body 永不帶 dimensions**；/api/tags 可用性探測；64/請求批次切分）+ `detect_meta_drift` 嚴格三元組 |
| `…/pipeline.py` | 593 | `run_daily` 雙模式（見偏差 D1）+ 游標 + 兩段 LLM（池空短路省 call）+ 單裁決事務 + drar→`classify_signal_failure` 內聯（G11 首個消費者）+ LIMIT 200/20 + 4KB 截斷 + flag 入口閘 + timeout 參數名內省適配 |
| `…/backfill_embeddings.py` | 104 | 補嵌 batch（欄探測 no-op/meta 漂移→全表重索引標記/整批失敗不部分寫） |
| `…/tests/`（conftest+_fakes+6 test 檔+__init__） | 1,585 | 110 tests；autouse `_no_real_db` 鐵閘（psycopg2.connect + lazy db_pool + urlopen 全攔，承 0ce45a09） |

合計 3,710 行。所有 source 檔 <800（最大 pipeline.py 593）。

## 3. 測試結果（Mac venvs/mac_dev，python 3.12.13，即時跑）

- **新套件：110 passed / 0 failed**（prompts 12、parsing 26、store 13、recall 13、embedding 12、pipeline 24、backfill 10）。
- **回歸（不碰既有測試，0 修改）**：`learning_engine/tests` **403 passed**；`ml_training/tests` **712 passed / 16 skipped**；E1-B 殼 `helper_scripts/cron/test_l2_memory_distill_cron.py` **24 passed**（接縫無互踩）。
- **mutation bite A/B 實證（臨時注入 buggy 版→紅→還原→綠，殘留 grep=0）**：
  - 錨①（dedup 壞 JSON→全 store）：改 fail-open 為 skip → **5 紅**（parsing 4 + pipeline 1）。
  - 錨⑥（extraction 壞 JSON→cursor 不推進）：失敗日也推游標 → **3 紅**。
  - 錨④（merge→supersede 非 DELETE）：merge 不 supersede → **1 紅**。
  - 錨⑤（無 V140→vector 降級不 raise）：降級改冒泡 → **1 紅**。
  - 錨②（meta 漂移→重索引）由 `test_meta_drift_triggers_full_reindex_mark` 直接鎖 SQL 計數；錨③（flag=0 cron 零連線）歸 E1-B，本線以 `test_flag_off_*` 蓋 run_daily 對偶（零 SQL 零 LLM、conn=None 也不炸）。

## 4. 治理對照

- 硬邊界 token（max_retries/live_execution_allowed/execution_authority/system_mode）：新檔 **0 命中**（grep 自證）。
- 跨平台路徑（/home/ncyu、/Users/、TradeBot）：**0 命中**；游標路徑走 `OPENCLAW_DATA_DIR` env / 顯式注入。
- import 時零網路/零 DB：全部 HTTP 在方法內；`get_local_llm_client()` 由 cron CLI（E1-B）注入，本 package 不 import 工廠；E1-B 的 `learning_engine.memory_distiller.pipeline` 頂層路徑 import 實測 OK（相對 import 鏈 + numpy only）。
- flag 家族 `OPENCLAW_L2_MEMORY_*` 默認 0；`PIPELINE` 守 run_daily 入口、`EMBED_BACKFILL` 守 pipeline 尾端；RECALL 本批不接線（spec §10）。
- E2 三審查點自證位置：①supersede 紀律=`store.py` SQL 常數 + `test_all_update_statements_touch_only_whitelisted_columns`（動態掃全部 UPDATE 常數，content 0 處）+ 零 DELETE FROM；②fail-open 邊界=`parsing.py` 兩段 except 路徑 + 測試；③降級不冒泡 + dimensions=`recall.py` 兩 except / `embedding.py` body 斷言。
- 裸 except 0；logger 全 %s 格式；SQL 全參數化；新注釋全中文；MODULE_NOTE 全檔齊（MIT attribution + 同名巧合警示在 prompts/`__init__`/V139 頭）。
- 新 singleton：0（MemoryStore/client 皆 caller 持有實例，無模組級可變單例）。

## 5. 與 spec 的偏差（逐條，prompt > spec 紀律）

- **D1（合流接縫，最重要）**：`run_daily` 增加 `target_date` 單日模式。原因：E1-B（M2，同樹並行已完工）按 spec §4「游標狀態檔歸 CLI 殼」自管游標，並以 `run_daily(conn, llm, target_date=day)` 呼叫、以「無例外=成功」決定 write_cursor（其碼內留有 TypeError 接縫註記）；而 spec §13.1 pipeline 測試行又要求 pipeline 測「cursor 推進與失敗不推進」。兩讀並存 → 雙模式：`target_date` 提供=單日、不碰游標檔、**失敗 raise RuntimeError**（維持 CLI 游標紀律；靜默回 dict 會讓 CLI 把失敗日推進游標=違 §6.3 鐵則）；缺省=內部游標自管模式（永不 raise）。E1-B 檔案 0 觸碰；接縫以鏡像其精確呼叫形的 3 條測試鎖死。
- **D2**：run_daily 入口加 `OPENCLAW_L2_MEMORY_PIPELINE` 閘（spec §10 只列 CLI 殼；dispatch 鐵則「全部 flag 守在入口」→ 雙層 fail-closed）。**E4 注意：scratch E2E 直呼 run_daily 須先 export 該 flag=1**。
- **D3**：pipeline.py 593 行 vs spec 預算 ~330（spec 行數為估算；<800 硬上限內；超出部分=游標+雙模式+材料構建+中文注釋）。
- **D4**：priority 語義落地：clamp 到 [-1,100]（§13.1 字面）後按分類型 floor 丟棄（trait<50/incident<60/rule<70，R4 第二層）；`-1` 鐵則**僅 rule 有效**（spec prompt 只給 rule 定義 -1；incident/trait 的 -1 被 floor 丟棄）。
- **D5**：drar evidence 構造 `candidate_id=f"drar:{report_id}"`、`family_id=strategy_name`（spec 未明指；最小可溯源選擇，postmortem 自身誠實降 confidence）。
- **D6**：dedup 段 LLM「不可用」（非 parse fail）也 fail-open-to-store（spec 只明定 parse fail；同向最小安全解，已有抽取產物時不丟失）。
- **D7**：`_call_llm` 內省 timeout 參數名（G7 引 ABC `timeout_s=`，工廠實際回 OllamaClient `timeout=`，兩 surface 並存）；雙形測試鎖定。
- **D8（小決策）**：`EMBED_REQUEST_BATCH_SIZE=64`、`_PROMPT_RECALL_K=10`（spec 未釘值）；`is_available` 走 /api/tags 模型名查核（mirror OllamaClient 慣例，比真嵌入探測便宜）；`set_embedding` 不 bump updated_at（白名單允許，語義保留給狀態/血緣變更，碼內註記）。

## 6. 只有 E4 Linux dry-run 能驗的斷言（Mac mock 蓋不到，誠實列舉）

1. V139 雙 apply 冪等 + Guard A 故意漂移表 RAISE + Guard B `content_tsv` 反射 `data_type='tsvector'` + `trading_ai` DELETE revoke + 生成列 `to_tsvector('simple', content)` immutability 接受度。
2. FTS SQL 真 PG 語意：`SET LOCAL pg_trgm.similarity_threshold` 事務作用域、psycopg2 `%%`→`%` 運算子、`GREATEST(ts_rank, similarity)`、`plainto_tsquery('simple')` 對中文 hint 的實際命中率（spec §13.2-3 中/英各一次非空）。
3. supersede CHECK（active/superseded link 約束）在真 UPDATE 下不被違反；`record_id = ANY(%s)` list 綁定。
4. pgvector 文本字面 `'[x,y,...]'::vector` 接受度（V140 路徑下）；`embedding <=> %s::vector` 排序。
5. psycopg2 真型別 round-trip：jsonb→dict、timestamptz→aware datetime（材料 ts_iso/事件窗比較）。
6. 真 Ollama qwen3.5:9b extraction JSON 過 parser（spec §13.2-5，operator-gated 煙測）。

## 7. Operator / PM 下一步

1. E2 對抗審（重點=§4 三點 + 本報告 D1 接縫裁決是否接受）。
2. E4：V139 scratch-DB 雙 apply + §13.2 全套（注意 D2 的 flag 前置）；V138 prod apply 既有 owed 與本批解耦（V139 deploy 時 V138 連帶 apply，spec §2.3 已標）。
3. 兩線合流後 PM 統一 commit；healthcheck [88][89] 註釋與 SCRIPT_INDEX 歸 E1-B 線（樹上已見其交付）。

E1 IMPLEMENTATION DONE: 待 E2 審查（report path: docs/CCAgentWorkSpace/E1/workspace/reports/2026-06-11--l2_memory_m1_sql_package.md）

---

## 8. 修復輪（E2 RETURN + MIT §C binding）— 2026-06-12 續作棒收口

- 修法正本：E2 `2026-06-11--l2_memory_review.md` + MIT `2026-06-11--l2_memory_schema_ratify.md` §C。
- 前一棒（M 線修復輪 E1）被月度限額殺死於 06-11 23:35 前後；本棒先逐項盤點（py_compile 全 25 檔 OK + 逐檔精讀），**source 側 6 項全部已由前棒完成且無半成品**，缺口=兩個未更新的測試檔（mtime 證據：`test_l2_memory_distill_cron.py` 22:18 / `test_l2_memory_healthchecks.py` 22:20，早於對應 source 23:31/23:32 的改動）。本棒只補測試收口 + 全量 mutation 錨保活驗證，0 source 改動。

### 逐 finding 狀態

| # | finding | 狀態 | 修法（落點） | 測試證據 |
|---|---|---|---|---|
| 1 | E2 MED-1 / MIT F-1（embed 軸零建構點 = dead flag） | **前棒已完成** | `pipeline.py:_resolve_embed_client`：顯式注入優先；`EMBED_BACKFILL=1` 且未注入 ⇒ lazy 建構默認 `OllamaEmbeddingClient()`（默認 127.0.0.1:11434；建構子 0 網路，可達性由 is_available 探測 fail-soft 為 embed_unavailable 不 raise）；同實例 thread 進 recall L1（`recall_top_k(..., embed_client=)`）與雙模式 backfill | 前棒 5 測（flag-ON 建構真達 embed HTTP / unreachable fail-soft / flag-OFF 不建構 / thread 進 recall / 注入優先）；**本棒 mutation C 親注（拔 lazy 建構）→ 2 紅，還原綠（shasum 證）** |
| 2 | OLLAMA_BASE_URL 非 loopback 守衛 | **前棒已完成** | `embedding.py`：`_is_loopback_base_url`（解析失敗 fail-closed 當遠端）+ `OPENCLAW_L2_MEMORY_EMBED_ALLOW_REMOTE=1` 顯式放行；拒絕 = `_remote_rejected`（is_available 恆 False + `_embed_request` 雙保險恆 None + WARN log），不回退替代 URL | 前棒 5 測（env 遠端拒 / flag 放行 / 顯式建構子遠端同閘 / loopback 變體免 flag / 不可解析 host fail-closed）；**本棒 mutation E（守衛改 False）→ 2 紅，還原綠** |
| 3 | E3 MED-2 origin 譜系 | **前棒已完成** | `pipeline.py:_origin_for_refs`：任一 source ref kind='l2_call' ⇒ `origin:"l2_untrusted"`，否則 `"l2_curated"`；store 與 merge 兩路徑皆**無條件覆蓋** meta["origin"]（LLM 不可自填偽裝 curated）；merge 用並集 refs 推導 ⇒ 污染單向傳染 | 前棒 5 測（l2 源 untrusted / drar-only curated / LLM 不可 spoof / merge 並集推導 / 全 INSERT 必帶 origin 鍵）；**本棒 mutation D（拔 stamping）→ 4 紅，還原綠** |
| 4 | seed 敏感網補全 | **前棒已完成** | `seed_agent_memory.py:_SENSITIVE_KEYWORD_RE` 補 `hmac` / `signing[_-]?key`（substring 蓋 auth_signing_key）/ `private[_-]?key` / `X-BAPI-SIGN` / `postgres(?:ql)?://user:pass@` DSN 形（字元類線性掃描無回溯面）；無密碼 DSN 不誤殺 | 前棒參數化正向 9 形 + 負向 3 形 + 構造行級測試（`test_sample_md_sign_and_dsn_lines_skipped`）；本棒親跑 39/39 綠 |
| 5 | E2-A LOW-1/LOW-2 | **前棒已完成 source；本棒補 CLI 側核對測試** | `_flag_on` 補 `.strip()`；target_date+disabled ⇒ raise `PipelineDisabledError`（RuntimeError 子類，`__init__` 已導出）；`_parse_event_window`：metadata activity_*_time ISO 可解析才填 event_start/end（反向區間=幻覺 ⇒ 雙 NULL；naive 視 UTC）。**M2 CLI 處置核對（本棒）**：讀碼證 CLI 通用例外臂在 `write_cursor` 之前 return EXIT_RUNTIME_FAIL ⇒ 游標紀律保持；本棒補 `test_pipeline_disabled_error_keeps_cursor_discipline`（同 MRO 本地鏡像，exit 1 + 游標不動 + stats 不寫） | 前棒：strip 測 / disabled-raise 專測 / event window 5 測（ISO/缺席/垃圾/反向/naive-UTC）；本棒 CLI 側 +1 測 |
| 6① | MIT §C-recall：trgm hint 路改 word_similarity | **前棒已完成** | `recall.py`：新 `_FTS_HINT_SQL`（`word_similarity(%s, content)` + `<%%` 運算子，hint 在前）+ `hint_mode` 參數；`recall_for_prompt` 走 hint_mode=True；dedup content-vs-content 幾何維持對稱 similarity 0.1（MIT 裁定充分）。門檻 0.3（MIT 報告未釘值，僅指方向「改 word_similarity 或降門檻」；默認 0.6 對 CJK 偏嚴，0.3 寬鬆向 rationale 碼內注釋——**小決策**）。seed `_RECALL_SQL` 同步同幾何同門檻 | 前棒 CJK 混排測試 `test_recall_for_prompt_routes_hint_mode_with_cjk_mixed_hint` + hint/content 兩幾何分離測；**本棒 mutation F（hint_mode 路由拔除）→ 8 紅（含 CJK 測），還原綠** |
| 6② | MIT/E2 [88] 語義死亡盲點 | **前棒完成 data path；本棒完成測試收口** | 鏈：pipeline day result 帶 `materials_l2` 計數 → CLI `append_day_stats`（成功日才寫；bounded 14 環形 + atomic replace + fail-soft 不反殺管線）→ `checks_l2_memory._semantic_death_streak`：連續 3 個「materials_l2>0 且 stored=0」已處理日 ⇒ WARN；stats 缺/壞/與游標不同步 ⇒ fail-soft 不誤 WARN；lag WARN 優先 | **本棒 +22 測**：healthchecks +9（3 連死 WARN / 2 日不足 / noop 斷鏈 / stored 斷鏈 / 只看最近 N / 檔缺 / 壞檔 / stale 不同步 / lag 優先）+ cron +13（entry 提取 / 6 形防禦默認 / 環形有界 / 壞檔重建 / 寫失敗 fail-soft / 成功日落檔 / 失敗日不落檔 / disabled 紀律）；**mutation A（streak 恆 False）→ 1 紅精準；mutation B（拔 CLI stats 寫入）→ 1 紅精準** |
| 6③ | MIT §C：768 維 runbook 入 V140 檔頭 | **前棒已完成** | `manual_V140_*.sql` 檔頭 0-7 步 runbook：停 backfill flag → DROP INDEX → **DROP COLUMN + 重 ADD 新維度**（deviation：MIT 建議 ALTER TYPE；全 NULL 列上兩者終態等價，drop+重建免 cast 歧義且天然全 NULL——等價偏安全向）→ 重建 HNSW → 游標/meta reset（含「略過本步 backfill 漂移偵測自動收斂」誠實註記）→ 同步 `EXPECTED_EMBED_DIMS` 常數 + env → 重開 flag 驗收 | SQL 註釋無執行面；`test_apply_manual_v140.py` 12 綠（applier 行為未變） |

### 驗證總帳（Mac venvs/mac_dev python 3.12.13，全部即時親跑）

- L2 memory 全套 **252 passed / 0 failed**（package 140 + seed 39 + cron 37 + healthchecks 24 + V140 12；基線 188 → 前棒 +42 → 本棒 +22）。
- `learning_engine` 全樹 **543 passed**（=403 既有 + 140 package，算術守恆，0 回歸）。
- healthcheck 鄰接 5 檔（mlde/cron_heartbeat/lg5/f7/replay_maintenance）**164 passed**。
- mutation 錨 6/6 bite（A 語義死亡 / B CLI stats / C lazy 建構 / D origin / E remote 守衛 / F hint_mode），全部 cp+shasum 備份還原驗證，殘留 grep=0。
- 治理 grep：硬編路徑 0 / 硬邊界 token 0 / MUTATION 殘留 0；本棒 0 tracked 檔觸碰（兩個測試檔皆 untracked 集合內）；watchdog/sentinel/polymarket 並行線檔 0 觸碰。

### 本棒不確定之處 / E4 注意

- CLI↔pipeline 的 PipelineDisabledError 跨界整合（真 import 非 mock 鏡像）屬 E4 scratch E2E 縫（M2 測試 hermetic 設計使然）。
- [88] 語義死亡軸依賴 CLI 模式運行（pipeline 自管模式不寫 stats ⇒ 同步判準 fail-soft 靜默，碼內已注釋）；生產部署走 cron CLI 故成立。
- word_similarity 門檻 0.3 為小決策，E4 seed `--apply` 中/英 recall 驗收（MIT C-1）是該值的真實檢驗點。
