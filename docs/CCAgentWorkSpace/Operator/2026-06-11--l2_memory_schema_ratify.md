# MIT — L2 記憶層 schema + pipeline ratify（V139 / manual V140 / memory_distiller）

- 日期：2026-06-11
- 審計對象（工作樹未 commit）：`sql/migrations/V139__agent_memory_store.sql`、`helper_scripts/db/manual_V140_agent_memory_vector.{sql,sh}`、`program_code/learning_engine/memory_distiller/`（8 模組+tests）、cron 三件套、seed CLI、`checks_l2_memory.py` [88][89]、runner.py 註冊
- 正本 spec：PA `2026-06-11--l2_memory_layer_design.md`；E1 兩線報告 M1/M2
- 證據基礎：全源碼逐檔精讀 + Mac 188/188 測試親跑 + **Linux prod PG 唯讀 empirical probe**（sqlx head / locale / trgm / FTS，本檔引用處標 [PROD]）

## 裁決：**RATIFY-WITH-CONDITIONS**

4 條 binding 條件（§C），其餘 findings 為非阻斷建議。Schema 本體（V139 DDL）無需修改即可進 E4。

---

## 逐項裁決（任務清單 1-6）

### 1. db-schema skill 對照

**Guard A/B/C（vs V133/V134 範式）— PASS**
- Guard A：表存在時 16 欄反射缺欄 RAISE（含 `content_tsv` 生成列）；embedding_meta 5 欄獨立 Guard A。**正確不含 `embedding` 欄** → V140 後 re-apply V139 不誤殺。與 V133 範式逐字同構。
- Guard B：7 個型別敏感欄反射（smallint/jsonb×2/timestamptz×2/boolean/tsvector）。`content_tsv` 以 `data_type='tsvector'` 反射的註解論證正確（pg_catalog 內建型非 USER-DEFINED；對照 manual V140 對 extension 型 `vector` 正確改用 `udt_name`）。
- Guard C：existence-only（3/5 索引）。**[LOW/高信度]** 兩缺口：(a) 不驗 indexdef（同名異定義索引可 silent pass `CREATE INDEX IF NOT EXISTS`——skill §Guard C 完整形）；(b) `idx_agent_memory_type_status_priority` 與 partial `idx_agent_memory_embed_pending` 未列入 Guard C。緩解：V133/V134 既有範式同為 existence-only（非 V139 獨有退步）；prod 表全新建（無 pre-existing 漂移面）。判定：repo-paradigm 一致，可接受；indexdef 深化列入未來範式升級債，非本批 blocker。
- 事務形：單 BEGIN/COMMIT，全部 Guard 在 COMMIT 前 → guard fail = 整體 rollback，無「post-COMMIT guard」crash-loop 向量（V114 教訓 clean）。`CREATE EXTENSION IF NOT EXISTS pg_trgm` 在 prod 已 installed 1.6 為 no-op。

**Plain table 裁決 — PASS（驗算成立）**
寫入率驗算：extraction 每日 ≤8 條 + merge/supersede 同量級 + seed 一次性 ~100 rows（M2 dry-run 實測 94+6）→ 年增 O(3k) rows，<10k 量級成立。表需 UPDATE（supersede/補嵌）→ hypertable+compression 與 UPDATE 衝突（compressed-twin 整族問題）；skill §1.1 此類 mutable 記憶庫=regular table 正解。**裁決正確**。

**索引集 vs 查詢模式 — PASS-with-notes**
| 查詢 | 索引命中 |
|---|---|
| dedup/B3 top-5 召回（FTS 雙路）| `idx_agent_memory_tsv`(GIN) + `idx_agent_memory_content_trgm`(GIN)，status filter 殘餘過濾（<10k rows 無礙）✓ |
| 補嵌游標 `WHERE embedding_pending AND status='active' ORDER BY updated_at` | partial `idx_agent_memory_embed_pending` 精確匹配 ✓ |
| load_by_ids | PK ✓ |
| `idx_agent_memory_status_updated` / `idx_agent_memory_type_status_priority` | **[INFO]** 當前零 coded consumer（dedup 池來自召回非游標掃描；B3 type 分塊在 Python 端做）。表小寫放大可忽略；按 skill 慣例日後監 `pg_stat_user_indexes.idx_scan=0` |

**tsvector 'simple' 對中英混排 — 風險已量化，trgm 已補位但有一條真缺口 [PROD empirical]**
- prod locale `en_US.utf8`[PROD] → glibc 視 Han 為 alpha → **pg_trgm 真會對中文產 trigram**（`show_trgm('中性化檢驗')` 回 6 個 trigram [PROD]）。trgm 補位軸成立，非理論。
- 'simple' FTS 對中文的實際傷害 [PROD]：`to_tsvector('simple','任何短 bias 信號必須先做 beta 中性化檢驗')` → 中文連續 run 成整塊 token（'任何短','信號必須先做','中性化檢驗'）；`plainto_tsquery('simple','beta 中性化')` → **f**（'中性化'≠'中性化檢驗'，無 bigram/前綴）；`'beta'` → **t**。結論：FTS 軸對中文僅命中「標點切出的整 clause」級 token；英文技術詞錨點正常。語料偏英文技術詞+中文敘事 → FTS 承擔英文錨，中文召回實質全壓在 trgm。
- **[MED/高信度] trgm 0.1 門檻對「短中文 hint × 長 content」幾何會漏真命中**：[PROD] `similarity(長混排 content, '中性化檢驗')=0.092 < 0.1`（漏）；`'beta 中性化'=0.121`（險過）。similarity 是長度對稱度量（交集/聯集 trigram），dedup 用途（content-vs-content 同長度級）門檻 0.1 充分；但 B3 `recall_for_prompt(symbol, context_hint)` 與 seed 驗收的「短 hint」幾何屬 `word_similarity`（`<%`，長度非對稱）的設計場景。建議（非阻斷，SQL 在代碼層非 schema）：hint 式召回改 `word_similarity`/`strict_word_similarity` 或對 hint 路徑降門檻；dedup 路徑維持現狀。
- **[LOW/高信度] GREATEST(ts_rank, similarity) 混兩個不同尺度**（ts_rank 單詞命中典型 ~0.03-0.1 vs similarity 0-1）→ trgm 分恆壓過 FTS 分的排序偏置。top-5 小池影響有限，記錄之。
- 既有緩解已內建且必須維持 binding：seed CLI `--apply` 後**真 recall 中/英 hint 各一次非空否則 exit 1**（直接打 prod，閉掉「scratch locale ≠ prod locale」盲點）；E4 scratch 復驗時 scratch DB 必須以 prod 同 locale（en_US.utf8）建庫（memory 教訓：TEMPLATE template0 需顯式指定 locale）。

### 2. embedding_meta 漂移偵測

**鏈條設計本體 — PASS**：`detect_meta_drift` 嚴格三元組（provider/model/dims）；dims 取**活探測向量長度**非硬編（`len(probe[0])`）→ 同維度換模型（model 名變）與異維度皆可偵測；漂移 ⇒ `UPDATE embedding=NULL, embedding_pending=true`（全表）+ meta upsert 同 commit；meta=None=首跑 INSERT 非漂移（防 R6 誤觸發）✓。meta 先寫後嵌的順序保證「任何已入庫向量必有 meta 記錄」✓。

**[MED/高信度] F-1 鏈條第一環在生產接線中斷 — 整條 embedding 軸現為 unreachable**：`OllamaEmbeddingClient` 全 repo **零非測試構造點**（grep 自證）；cron CLI 呼叫 `run_daily(conn, llm, target_date=day)` 不帶 `embed_client` → `run_backfill(conn, None)` 恆回 `embed_unavailable`。即使 operator：V140 applied + bge-m3 pulled + `EMBED_BACKFILL=1`，補嵌**永不執行**、meta 行永不建立、[89] 恆停在「meta not initialized=PASS 過渡態」。flag 有 gate 無 functional consumer（典型 writer-exists≠wired）。dormant 期零影響；**列 binding 條件 C-3**（backfill flag-ON 前修：CLI 在 backfill flag=1 時構造 client 注入，一行級）。

**bge-m3 1024 維寫死位置盤點 + 換 768 維遷移路徑**：寫死共 3 處——(a) manual V140 `vector(1024)` 列型（真鎖點）；(b) `checks_l2_memory.EXPECTED_EMBED_DIMS=1024`（tripwire，反而有用）；(c) V140 註釋。runtime 側（store/backfill/embedding.py）**無** 1024 硬編（dims 活測）✓。換 768 維模型時實際行為：drift 偵測命中 → 全表 NULL+pending → 重嵌寫回 `set_embedding` 768 維 literal 撞 `vector(1024)` 列 → PG RAISE → backfill 每輪 `batch_stage_failed`（fail-soft 不死循環）→ [89] 因 (b) 持續 WARN（信號存在，但 WARN 文案「backfill 將標記全表重索引」在此態為誤導——backfill 已無法收斂）。**[LOW-MED/高信度] 缺維度遷移 runbook**：正確序列=（漂移已全表 NULL 後）`DROP INDEX idx_agent_memory_embedding_hnsw; ALTER TABLE agent.agent_memory ALTER COLUMN embedding TYPE vector(768); CREATE INDEX ... hnsw ...`（全 NULL 列 ALTER TYPE 秒級）+ 同步改 (b)。建議落 manual V140 檔頭註釋。非阻斷（bge-m3 尚未 pull，軸本身 dormant）。

**[LOW/中信度] F-2 vector 級空結果不回落 FTS**：`recall_top_k` L1 查詢成功但 0 rows（全表 embedding NULL——重索引窗口/補嵌未收斂的常態）→ 回 `([], "vector")` 不降 L2 → dedup 池空 → 全 store（重複堆積，方向安全但 dedup 失效於最需要的窗口）。spec §6.4 L1 前置「meta 行存在」檢查代碼亦未實作。廉價修法：vector 0 rows → fall through FTS。現實影響被 F-1 遮蔽（vector 級無生產 caller），與 F-1 同批修。

### 3. ML 衛生（leakage 視角）

**as-of 紀律 — PASS（架構性成立）**：
- 蒸餾窗 = 已收盤 UTC 日（昨日及以前），源取數用**到達時間**（l2_calls.created_at / drar.first_seen_ts）非事件時間 → 晚到資訊晚蒸餾，ingestion 無前視；記憶 content 不可能含其 created_at 之後的資訊（窗終點 ≤ 蒸餾時刻 -5h）。
- **B3 未來餵回的前視風險定性**：live session 注入「含結局的 incident」= 學習非 leakage；**真 leakage 向量 = replay/counterfactual（Stage 0R / M11 類）以「現在的記憶庫」重放歷史 session** → 注入了決策時點之後才蒸餾出的結局知識 → 重放績效虛高。本批 B3 零接線（layer2_engine 0 diff，git 自證）無此風險；**列 binding 條件 C-4 給未來 B3 批次**。
- **PIT 重建能力 — 強（V139 設計的隱性優點，明確記錄）**：content 不可變 + DELETE REVOKE + status 單向單次轉移（`_SUPERSEDE_SQL` WHERE status='active' 防重指）+ updated_at 僅在 supersede 時 bump + **`set_embedding` 刻意不 bump updated_at（E1 D8 小決策——此決策恰好保住 PIT 語義，應升格為文檔化不變式）** ⇒ 「時刻 T 的活性記憶集」可精確重建：`created_at<=T AND (status='active' OR updated_at>T)`。
- source_refs 溯源充分性：l2_call → append-only ledger（FULL prompt 落庫）✓；drar → report_jsonb 不可變 row ✓；lesson/memory_topic ✓。**[LOW/高信度]** postmortem 分類器版本未入 metadata（taxonomy 文本是蒸餾時點分類器輸出，重建需 git 考古）；建議 metadata 加 `pipeline_version`/classifier 標記。**[INFO]** `event_start/event_end` typed 欄目前零 writer（pipeline/seed 皆不填，LLM 時間僅入 event_time_str+metadata）——出生即死欄，B3 期若需事件時間範圍查詢須補解析器。
- **merge 時間戳並集語義 — PASS-with-note**：source_refs 新∪舊（確定性序列化鍵去重）保全雙側血緣 ✓；舊 row 的 event_time_str 不併入 merged row（僅留新候選的），但舊 row 全文存活於 supersede 鏈 → 時間線無破壞、僅 head 敘述偏新（LOW，可沿鏈回溯）。
- 6 類型逐項：Look-ahead **N/A-by-construction**（到達時間窗+收盤日）；Target leakage **N/A**（無 label）；Survivorship **PASS**（軟刪鏈全史保留；dedup 'skip' 丟棄為設計語義之 LLM 裁量，skip 計數在 day stats 可觀測）；Cross-section **N/A**；Time-zone **PASS**（全鏈 UTC：窗、游標、材料 ts）；Resample boundary **PASS**（僅處理已結束 UTC 日）。

### 4. supersede 軟刪鏈

**數學保證範圍（精確陳述）**：
- 保證的：(a) 每 row 至多一次轉移、superseded_by 首指針不可覆蓋（WHERE active 守衛）；(b) CHECK `supersede_link` 把「active 有指針/superseded 無指針」擋在 DB 層；(c) 無環——指針只指向 supersede 時刻剛 INSERT 的新 row，superseded row 永不再入召回池（召回 WHERE active）故不可能被反向指；鏈為時間前向 DAG。
- **不保證的（設計接受，非 bug）**：同一事實/scene 的活性記錄唯一性**無約束**——fail-open-to-store 與池空短路天然產生多活頭，靠未來輪次 dedup 收斂（spec §6.3 明文）。同 scene 多活鏈=合法常態。
- **[LOW/高信度] F-3 merge 路徑 insert 成功未驗**：`insert_record` 回 bool 在 merge 分支未檢——record_id 撞號（uuid12 ~2^-48/對，或 LLM 異常複用）時 INSERT no-op 而 supersede 照常執行 → superseded_by 指向既存無關 row（superseded_by 無 FK，dangling 語義錯）。概率可忽略，建議 merge 分支斷言 insert 回 True 否則 rollback 該裁決。
- **同批雙 merge 同一 target**：先到者得指針，後到者 supersede rowcount=0、血緣存於其 metadata.merged_from——一致且可審計 ✓。
- 召回 filter 與索引配合：兩級 SQL 皆 `WHERE status='active'`（只取 head）✓；GIN match 後殘餘過濾 status，量級無礙（§1）。

### 5. V### 流程

- **dry-run gate 覆蓋面 — 充分**：spec §13.2（雙 apply 冪等 + Guard A 漂移表負測 + trading_ai DELETE revoke 實測 + seed 真 recall 中/英 + FakeLLM 真 scratch E2E + V140 權限裁決）對齊 memory 長期教訓（boundary INSERT 驗 CHECK、負測包 SAVEPOINT+ON_ERROR_STOP、TEMPLATE template0）。補一條 **binding：scratch 建庫須 prod 同 locale en_US.utf8**（否則 trgm-CJK 驗證失真，§1 [PROD] 證據）。E1 M1 §6 誠實列舉 Mac 蓋不到的 6 項（含 psycopg2 `%%`、SET LOCAL 作用域、pgvector literal）= E4 清單正確。
- **V138→V139 順序依賴 [PROD 證實]**：prod `_sqlx_migrations` head=137[PROD] → V138/V139 雙 pending，sqlx 順序語義下 **apply V139 必先 apply V138，不可繞**。技術風險低：兩檔皆單 BEGIN/COMMIT（V138 BEGIN:71/COMMIT:468 親驗，COMMENT 在 COMMIT 前）、純增表、schema 不相交（research.* vs agent.*）、V138 已 E4 GREEN scratch 雙 apply。**治理風險須顯式化：V139 的 prod apply 即消費掉 operator-gated 的 V138 決策**——apply 計劃必須寫明「本次連帶 V138」，由 operator 一次拍兩個。失敗模式：V138 prod-specific 漂移致 fail → sqlx fail-stop → V139 不 apply + engine 拒啟（fail-closed 正確但停機）；緩解=apply 前跑 sqlx checksum drift 檢核（V137 曾經歷 P4 撞號改號史，applied-content vs 現檔 drift 非假想；SOP=`repair_migration_checksum` 在手）。列 **binding 條件 C-2**。
- **V140 號保留（鏈外手動檔）— PASS**：號空洞有 V116-V124/V128 先例（prod head=137 已含洞照常運行[PROD]）→ sqlx 容忍非連續。號占用以檔頭+SCRIPT_INDEX 註記為正本（V137/[82] 教訓已內化）。applier 退出碼 0/1/2/3/4 分類 + udt verify + 冪等重跑設計乾淨。**[INFO/中信度]** pgvector ≥0.5 control file 標 `trusted=true`，db-owner（trading_admin）`CREATE EXTENSION vector` 大概率直接成功——§13.2-2 裁決 dry-run 仍照跑，但結果為 A 時維持路徑 B 亦無害（手動檔冪等、不擋未來入鏈）。
- **[INFO]** 工作樹另見 `helper_scripts/SCRIPT_INDEX.md` 已 modified（M2 報告聲明未動、歸 PM 合併）——多 session 髒樹常態，合流時 E2 核對歸屬即可。

### 6. healthcheck [88][89] 監測語義

- **flag-OFF=PASS-skip 不會掩蓋 flag-ON 壞死 — 核心成立**：兩 check 的 skip 分支以 flag 為唯一條件，flag-ON 立即切真檢；[88] 的主信號=游標滯後（游標**僅成功推進**——CLI 以「無例外」決定 write_cursor，pipeline 單日模式失敗必 raise，鏈條自洽）→ extraction 連續失敗/cron 不跑/Ollama 死 → 滯後 >3 日 WARN。表缺+flag=1 → WARN（配置死亡覆蓋）。
- **flag-ON FAIL 條件夠不夠尖 — 兩個已識別盲點**：
  - **[LOW-MED/高信度] F-4 語義性死亡不可見**：no-op 日（兩源空）與「extraction 全 dropped」日皆算成功推進游標 → 上游 l2_calls writer 死亡或 parser 全丟時 [88] 恆 PASS 而記憶零累積。`rows=` 在訊息中但無增量斷言。廉價尖化：CLI 已產 day stats，落一個 last-run summary JSON（stored/materials/dropped）於游標旁供 [88] 引用「連續 N 個非 no-op 日 stored=0」WARN。非阻斷（學習平面+l2 呼叫本就稀疏，現 1 row[PROD]）。
  - [89] 對「pipeline flag=1 + backfill flag=0 + 換模型」窗口靜默（混向量空間風險）——但該態在 F-1 修復前不可達，與 C-3 同批考慮即可。
  - WARN-not-FAIL 分級：學習平面零資金風險論證成立，接受（碼內已自書理由）。
- 接線本體：runner import 塊/註冊清單行（號占用正本）/cursor 區 [87] 後雙 call site，三處最小 diff 親驗 ✓；`_rollback_quietly` 防前序 aborted txn 污染（既有慣例）✓。

---

## Component maturity（5 階段 × 4 維度，本批部署後預期態）

| Component | Writer spawn | Consumer | Row 累積 | Decision impact | Stage |
|---|---|---|---|---|---|
| `agent.agent_memory`（V139）| 代碼就緒/flag-OFF | recall 代碼就緒/零生產 caller | 0（表未 apply）| 無（學習平面 by design）| **Foundation** |
| 蒸餾管線（cron+pipeline）| cron 可裝/flag-OFF inert | dedup 自消費 | 0 | 無 | **Skeleton**（flag-ON 即起）|
| seed CLI | 一次性/默認 dry-run | 同上 | 0 | 無 | ready（非常駐）|
| embedding 軸（V140+backfill+L1 recall）| 模組在/**注入缺（F-1）** | L1 recall 零 caller | 0 | 無 | **Foundation-with-gap**（flag-ON 亦不可達，C-3 前不得宣稱 Skeleton）|
| B3 召回注入 | 接縫 only（zero engine diff）| 無 | — | 無 | **Foundation**（dormant seam）|
| [88][89] 哨兵 | 已接線 runner | healthcheck 報表 | — | 觀測 only | live（PASS-skip 態）|

## 結論

V139 DDL 與 distiller 是這批 L2 工作裡 schema 紀律最完整的一檔：Guard 範式忠實、plain-table 裁決經得起驗算、supersede 狀態機有 DB 層 CHECK、PIT 重建能力是同類記憶庫少見的強性質、兩段差異化 fail 策略（extraction fail-to-skip / dedup fail-open-to-store）方向全部正確且測試有 bite（188/188 親跑）。中文檢索的真實風險已用 prod empirical 量化：trgm 補位成立但短 hint 幾何有實測漏召回（0.092<0.1），靠 binding 驗收 + word_similarity 建議收口。唯一結構性缺口是 embedding 軸的生產注入缺失（F-1）——dormant 期無害，但 flag 語義已名存實亡，必須在 backfill 啟用前修。

### C. Binding 條件（RATIFY-WITH-CONDITIONS 之「conditions」）
1. **C-1（E4 gate）**：scratch dry-run 照 spec §13.2 全跑，scratch DB 以 prod 同 locale（en_US.utf8）建；seed `--apply` 後中/英 hint 真 recall 驗收維持 fail-closed（exit 1）。
2. **C-2（prod apply gate）**：V139 prod apply 計劃顯式寫明「sqlx 順序連帶 V138（operator-gated 決策於此消費）」；apply 前跑 sqlx checksum drift 檢核（V137 改號史故）。
3. **C-3（embedding 軸啟用 gate）**：`OPENCLAW_L2_MEMORY_EMBED_BACKFILL=1` 之前，cron CLI 須在該 flag 下構造 `OllamaEmbeddingClient` 注入 `run_daily(embed_client=...)`（F-1）；同批建議帶 F-2（vector 空結果回落 FTS）。
4. **C-4（B3 接線批 gate）**：任何 replay/counterfactual 路徑注入記憶必 PIT 過濾 `created_at<=t AND (status='active' OR updated_at>t)`；`set_embedding` 不 bump updated_at 升格為文檔化不變式（破壞它=破壞 PIT 重建）。

### 非阻斷建議（severity 序）
- MED：B3/seed hint 召回改 `word_similarity` 或降 hint 路徑門檻（[PROD] 0.092 證據）。
- LOW-MED：維度遷移 runbook 落 manual V140 檔頭（DROP HNSW → ALTER TYPE → 重建 + 改 [89] 常數）；[88] 語義死亡尖化（last-run stats JSON）。
- LOW：merge 分支驗 insert 回值（F-3）；[89] 漂移 WARN 文案在 dims≠1024 態誤導；postmortem 分類器版本入 metadata；GREATEST 尺度混合排序偏置記錄。
- INFO：兩條零 consumer 索引（idx_scan 監測）；event_start/end 出生死欄；CLI 多日循環每日重跑 backfill（no-op 廉價）；pgvector trusted=true 大概率路徑 A 可行（dry-run 照裁）；seed 內容編輯後重 seed 產新 hash 多活頭（靠 dedup 收斂）。

### 假陽性候選（列出不剔除，判斷依據附）
- 「`trigger` 裸列名撞 PG 保留字」——V134 DDL 未加引號已 apply 至 prod（head≥134），證非保留；非問題。
- 「`SET LOCAL ... %s` 參數化不可行」——psycopg2 客戶端插值非 server-prepare，layer2_critic 同款已在 prod 跑；psycopg3/asyncpg 遷移時才需重審。
- 「V138 含 post-COMMIT DDL」——親驗為單 BEGIN/COMMIT，COMMENT 在 COMMIT 前；不成立。

MIT AUDIT DONE: docs/CCAgentWorkSpace/MIT/workspace/reports/2026-06-11--l2_memory_schema_ratify.md
