# E1(M2 線) — L2 記憶層 cron 三件套 + seed CLI + manual V140 工具 + [88][89] 哨兵

- 日期：2026-06-11
- 線別：E1-B（PA spec §14；與 M1 線 V139+package 檔案零重疊）
- spec 正本：`docs/CCAgentWorkSpace/PA/workspace/reports/2026-06-11--l2_memory_layer_design.md`
- base：local main `5c37ba48`（fetch 後 == origin/main）
- 狀態：IMPL DONE，**未 commit**（鏈 E1→E2→E4→QA→PM）；全部交付 flag-OFF inert

## 1. 任務摘要

按 PA spec E1-B 線清單實作：①cron 三件套（CLI 殼 + wrapper + installer，daily 05:23 UTC，
flag `OPENCLAW_L2_MEMORY_PIPELINE` 默認 0=inert）；②seed CLI（兩源：agent.lessons dead-modes
+ repo `memory/MEMORY.md` 索引行，敏感雙層過濾，默認 dry-run）；③manual V140 手動 apply 工具
（pgvector 軸，**不入 sql/migrations/** 防 sqlx fail-stop）；④healthcheck [88][89] 接線
（dormant 友好：flag-OFF ⇒ PASS-skip 非 FAIL）。

## 2. 修改清單（7 source + 4 test，全部新檔除 runner.py）

| 檔 | 行數 | 內容 |
|---|---|---|
| `helper_scripts/cron/l2_memory_distill.py` | 251 | CLI 殼：flag gate 先於任何重 import/DB 連線；`_ensure_repo_imports` 仿 G8；游標檔（atomic replace；窗=(cursor+1)..昨日、回看 cap 7 日、首跑只補昨日）；string import `learning_engine.memory_distiller.pipeline`，ImportError ⇒ log+exit 0（兩線合流前合法）；exit 0/1/2 |
| `helper_scripts/cron/l2_memory_distill_cron.sh` | 112 | wrapper mirror `incident_sentinel_cron.sh`：mkdir lock 防重入 + stale lock >180min 自清 + secrets grep-parse + heartbeat `l2_memory_distill.last_fire` + fail-soft exit 0；**外加 size-based 日誌輪轉**（>5MB ⇒ .1 一代，PM 要求） |
| `helper_scripts/cron/install_l2_memory_distill_cron.sh` | 131 | installer mirror：Linux-only / dry-run 預設 / `OPENCLAW_L2_MEMORY_CRON_APPLY=1` gate / `--remove` / idempotent refuse / cron env value validation（flag 值另限 0\|1）；entry `23 5 * * *` 含 `OPENCLAW_L2_MEMORY_PIPELINE=0` 顯式 inert |
| `helper_scripts/memory/seed_agent_memory.py` | 404 | seed CLI（§9）：A 源 lessons dead_mode→rule/90、B 源 MEMORY.md 索引行（feedback_→rule/80、project_→incident/70、reference_*+External tool authority 節排除）；敏感雙層（spec keyword regex IGNORECASE + 個人路徑 detector）；冪等錨 `mem:seed:sha12(content)` + ON CONFLICT DO NOTHING；默認 dry-run 0 DB 連線；`--apply`（alias `--write`）+ `--dsn` 或 POSTGRES_* env；寫後中/英 hint 各跑一次真 recall SQL 驗收（0 命中 ⇒ exit 1） |
| `helper_scripts/db/manual_V140_agent_memory_vector.sql` | 70 | spec §3.1 DDL 改 manual 版（路徑 B 落點，V140 號保留給此檔）：V139 前提守門 RAISE + `CREATE EXTENSION IF NOT EXISTS vector` + Guard B'（udt_name 反射）+ `ADD COLUMN IF NOT EXISTS embedding vector(1024)` + HNSW IF NOT EXISTS；冪等雙跑安全 |
| `helper_scripts/db/apply_manual_V140_agent_memory_vector.sh` | 99 | apply 工具：psql ON_ERROR_STOP + stderr 分類 ⇒ exit 0=成功+verify(udt=vector)/1=SQL 失敗/2=配置缺/3=權限不足（附 superuser 指引）/4=V139 前提缺；冪等重跑 0 |
| `helper_scripts/db/passive_wait_healthcheck/checks_l2_memory.py` | 151 | [88] pipeline freshness（flag-OFF ⇒ PASS+"SKIP"；flag=1 ⇒ V139 表可達 + 游標滯後 >3 日 WARN）；[89] embedding meta vs config 漂移（backfill flag gate 同語義；meta 未初始化=PASS 過渡態） |
| `helper_scripts/db/passive_wait_healthcheck/runner.py` | +19/-0 | 三處最小 edit：import 塊（mirror [83]-[87] 註釋形）+ 註冊清單 `[88][89]` 行（**號占用正本**）+ cursor 區 [87] 後兩個 call site |
| `helper_scripts/cron/test_l2_memory_distill_cron.py` | 350 | 24 test：pending_days 純函數×5 / 游標檔×4 / flag gate 零副作用（forbid 注入）/ 模組未落地 exit 0 / 成功推進+失敗停游標+TypeError 接口縫 / wrapper bash -n + 鎖防重入 + stale 自清 + heartbeat + 輪轉 + flag passthrough（hermetic：tmp BASE + stub script） |
| `helper_scripts/memory/test_seed_agent_memory.py` | 346 | 27 test：B 源解析全分支 / 敏感網（keyword+路徑，樣本 runtime 拼接防 grep 誤中）/ 冪等錨 / **dry-run 對真 repo MEMORY.md（毒 psycopg2 自證 0 連線）** / fake-conn 寫路徑（ON CONFLICT、全參數綁定、0 DELETE/UPDATE、recall 驗收 2 hint、空命中 exit 1、重跑 inserted=0） |
| `helper_scripts/db/test_apply_manual_v140.py` + `test_l2_memory_healthchecks.py` | 186+189 | 27 test：mock psql（PATH 注入）⇒ 退出碼 0/1/2/3/4 全分類 + 調用面（ON_ERROR_STOP/-f/-c verify）+ 冪等重跑 + SQL 形狀靜態釘（IF NOT EXISTS 全覆蓋、0 破壞性語句）；[88][89] FakeCursor 全分支 + runner 接線釘子 |

## 3. 關鍵 diff（runner.py 唯一既有檔改動）

```python
from .checks_l2_memory import (
    # L2 記憶層 (2026-06-11 E1-B，PA spec §12) — `[88]`-`[89]` dormant 哨兵。…
    check_88_l2_memory_pipeline_freshness,
    check_89_l2_memory_embedding_drift,
)
# 註冊清單（main docstring，:589-591 區）：
#   [88][89]  (L2 記憶層 dormant 哨兵：…E1-B 2026-06-11 PA spec §12；號占用正本)
# cursor 區 [87] 後：
s, m = check_88_l2_memory_pipeline_freshness(cur)
results.append(("[88] l2_memory_pipeline_freshness", s, m))
s, m = check_89_l2_memory_embedding_drift(cur)
results.append(("[89] l2_memory_embedding_drift", s, m))
```

## 4. 測試結果（Mac venvs/mac_dev/bin/python 3.12，即時跑）

- 4 新測試檔合計 **78 passed / 0 failed**（24+27+13+14）。
- bash -n：wrapper / installer / apply 三 .sh 全過；py_compile 全過。
- 鄰接回歸：`test_mlde_healthchecks + test_cron_heartbeat_healthchecks + test_f7_new_healthchecks + test_lg5_healthchecks` **125 passed**（runner import 圖完好）。
- runner 真 import：`from passive_wait_healthcheck import runner` OK，[88][89] 綁定可見。
- 測試自抓 1 真 bug：apply script `$rc` 後接全形「（」在 `set -u` 下被 bash 併入變數名 ⇒ `${rc}` 加括號修復（mock psql sqlerr 路徑抓到）。

## 5. seed dry-run 樣例輸出（對真 repo MEMORY.md，rc=0）

```
[DRY-RUN] 將寫入 agent.agent_memory（未寫庫；--apply 才落庫）：
  [A 源 agent.lessons lesson_type='dead_mode'] deferred — 寫入時同連線讀取（dry-run 0 DB 連線；runtime 預期 6 rows）
  [B 源 MEMORY.md 索引行] 94 條：
    - mem:seed:5629a66a0b42  incident/p70  scene=seed:memory_index
      content[:88]: 五 repo 借用評估+P0/P1 落地 (2026-06-11) — **已落地 `4587f65f`**(E1×4→E2 兩輪→E4 GREEN)…
    - mem:seed:c6e4f32abea8  rule/p80  scene=seed:memory_index
      content[:88]: restart bind host safe default (2026-05-09) — auto 解析 Tailscale IPv4 否則 loopback;…
  攔截 5 條（spec R8：dry-run 人工過目清單）：
    - reference_ultracode_full_audit.md  reason=prefix_not_whitelisted
    - reference_remote_access.md  reason=prefix_not_whitelisted
    - reference_restart_script.md  reason=prefix_not_whitelisted
    - reference_external_tools.md  reason=prefix_not_whitelisted
    - feedback_external_tool_authority.md  reason=excluded_section:External tool authority
[DRY-RUN] 冪等錨 = record_id（mem:seed:sha12(content)）；INSERT ... ON CONFLICT DO NOTHING，可重跑。
```

註：B 源實際 94 條（spec 估 ~55——repo MEMORY.md 現況比估算多，誠實計數）；敏感 keyword 0 命中。

## 6. 治理對照

- 硬邊界 token：11 檔 grep `max_retries|live_execution_allowed|execution_authority|system_mode` = 0。
- 跨平台路徑：0 `home/ncyu` / 0 `Users/ncyu`；`$HOME/BybitOpenClaw` 默認值 = sentinel wrapper 既有慣例（runtime-relative）；個人路徑 detector regex 含 `(?:/home|/Users)/` 形狀字面，為過濾器本體非硬編路徑（檔內已註明）；測試樣本 runtime 拼接。
- spec E2 三重點：①seed 全鏈 0 DELETE/0 UPDATE（測試釘死）；②fail-open 邊界不在我線（pipeline 歸 M1）；③flag gate 先於 psycopg2 connect（forbid-injection 測試證）+ [88][89] 降級不冒泡。
- 寫入面：cron 殼自身 0 DB 寫（只寫游標檔）；seed 只 INSERT agent.agent_memory（學習平面，原則 7）；V140 SQL additive only。
- 檔案大小：全部 <800 行；runner.py 1501→1520（pre-existing exception，+19 行註冊）。
- 新 singleton：0（全部無狀態函數/短命進程）。
- SCRIPT_INDEX.md / E1 memory.md：**未動**（per PM；待合併行見 §8/§9）。

## 7. 偏差與裁決（prompt > spec；最小安全解）

1. **[88][89] 實作深度**：spec §12 = 僅 reserved 註釋行（不實作 check 本體）；PM 派發 = 「按範式接線，flag-OFF 報 SKIP 非 FAIL」。**從 PM**：實作真 check（新模組 + runner 註冊），flag-OFF ⇒ `("PASS", "SKIP (flag off): …")`（runner 無獨立 SKIP 狀態字，PASS-skip 為 [82]/[83]-[87] 既有慣例）；flag=1 才真檢（表缺/游標缺/滯後/漂移 ⇒ WARN，不佔 FAIL 頻寬——學習平面零資金風險）。註冊清單行兼任號占用正本。
2. **seed 寫入接口**：PM 寫「走與 package 同一 store 接口」；spec §9/§14 兩處明示「自帶 INSERT SQL、不 import memory_distiller（檔案零重疊=並行前提）」。**從 spec 字面**（import M1 半成品違反 PM 自己的「不要去讀 M1 半成品」+ 破壞 dry-run 今日可跑）；INSERT 形狀與 V139 store 契約一致（冪等錨/只 INSERT/默認欄不碰）。E2 合流時可比對 M1 `store.py` 的 INSERT 欄序一致性。
3. **寫 flag 命名**：PM=`--apply`、spec=`--write` ⇒ 取 m4 seeder 既有先例：`--apply` 主名 + `--write` alias（兩者皆可）。
4. **seed DSN 來源**：spec 允許 POSTGRES_* env fallback（m4 先例是 --dsn 強制）。從 spec；--dsn 優先、env 不完整即 fail-closed exit 2。
5. **V140 工具=2 檔**：spec 路徑 B 只名 .sql；PM 要求「退出碼+權限報錯」必需可執行殼 ⇒ .sql（spec 指定位置）+ .sh applier（PM 測試要求「mock psql」亦印證此形）。
6. **首跑游標缺省**：spec 未定 ⇒ 只補昨日（保守，防首 enable 即 7×2 LLM call 爆量；歷史回放歸 seed CLI）。
7. **spec G7 工廠路徑筆誤**：實際在 `program_code/exchange_connectors/bybit_connector/control_api_v1/app/local_llm_factory.py`，import 採 G8 vetted 形 `exchange_connectors.bybit_connector.control_api_v1.app.*`。
8. **個人路徑過濾**：PM 加項（spec 只有 keyword regex）⇒ 補 `(?:/home|/Users)/<user>` detector；keyword regex 取 IGNORECASE（誤殺安全向）。

## 8. 兩線接口假設（合流時 E2 核對點）

- cron 殼呼叫：`pipeline.run_daily(conn, llm, *, target_date: datetime.date) -> dict`（spec §4 僅給 `run_daily(conn, llm, ...)`；TypeError 有專屬 log 標記「疑簽名不匹配」供一行修正）。
- seed INSERT 欄：`(record_id, content, mem_type, priority, scene, source_refs, metadata)`，其餘 V139 DDL 默認。

## 9. SCRIPT_INDEX.md 待合併行（PM 合併；表 row 形式）

```
| `cron/l2_memory_distill.py` | L2 記憶蒸餾 daily cron CLI 殼（PA 2026-06-11 spec §6.1/§14）：flag `OPENCLAW_L2_MEMORY_PIPELINE` 默認 0 在**連 DB 前** gate（off=exit 0 零連線）；游標檔 `cron_state/l2_memory_distill_cursor.json`（成功才推進、回看 cap 7 日、首跑只補昨日）；string import `learning_engine.memory_distiller.pipeline`（未落地=log+exit 0）；POSTGRES_* env 連線 + `get_local_llm_client(heavy=False)` 注入；exit 0/1/2。 |
| `cron/l2_memory_distill_cron.sh` | daily 05:23 UTC wrapper（mirror incident_sentinel）：mkdir lock + stale>180min 自清 + secrets grep-parse + heartbeat `l2_memory_distill.last_fire` + **size-based 日誌輪轉（>5MB→.1）** + fail-soft exit 0。 |
| `cron/install_l2_memory_distill_cron.sh` | Linux-only idempotent installer：dry-run 預設、`OPENCLAW_L2_MEMORY_CRON_APPLY=1` 才寫、`--remove`、cron env validation（pipeline flag 限 0|1）；entry 含 `OPENCLAW_L2_MEMORY_PIPELINE=0` 顯式 inert。 |
| `cron/test_l2_memory_distill_cron.py` | 24 test：游標窗口純函數 / flag gate 零副作用（forbid 注入）/ 模組未落地 exit 0 / 失敗停游標 / wrapper 鎖防重入+stale 自清+輪轉+heartbeat（hermetic stub BASE）+ bash -n×2。 |
| `memory/seed_agent_memory.py` | L2 記憶層 seed CLI（spec §9）：A 源 agent.lessons dead_mode→rule/90 + B 源 repo memory/MEMORY.md 索引行（feedback_→rule/80、project_→incident/70；reference_*+External tool authority 節排除）→ agent.agent_memory（V139）；敏感雙層（keyword regex IGNORECASE + 個人路徑 detector）；冪等錨 `mem:seed:sha12(content)`+ON CONFLICT DO NOTHING；默認 dry-run 0 連線、`--apply`(alias `--write`)+`--dsn`/POSTGRES_* env 才寫；寫後中/英 hint 真 recall 驗收（0 命中=exit 1）。 |
| `memory/test_seed_agent_memory.py` | 27 test：B 源解析全分支 / 敏感網 / 冪等錨 / dry-run 對真 MEMORY.md（毒 psycopg2 證 0 連線）/ fake-conn 寫路徑（0 DELETE/UPDATE、recall 驗收、重跑 inserted=0）。 |
| `db/manual_V140_agent_memory_vector.sql` | **manual apply 檔，刻意不入 sql/migrations/**（spec §3.2 路徑 B；CREATE EXTENSION vector 需 superuser，入 sqlx 鏈失敗會 fail-stop 卡 V141+）：V139 前提守門 + Guard B'(udt_name) + ADD COLUMN IF NOT EXISTS embedding vector(1024) + HNSW；冪等；V140 號保留給此檔。 |
| `db/apply_manual_V140_agent_memory_vector.sh` | manual V140 applier：psql ON_ERROR_STOP + stderr 分類退出碼（0=成功+verify、1=SQL 失敗、2=配置缺、3=權限不足附 superuser 指引、4=V139 前提缺）；冪等重跑 0。 |
| `db/test_apply_manual_v140.py` | mock psql（PATH 注入）退出碼全分類 + 調用面 + SQL 冪等形狀靜態釘（IF NOT EXISTS 全覆蓋、0 破壞性語句）。 |
| `db/passive_wait_healthcheck/checks_l2_memory.py` | `[88]` l2_memory_pipeline_freshness（flag-OFF→PASS-skip；flag=1→V139 表可達+游標滯後>3 日 WARN）+ `[89]` l2_memory_embedding_drift（backfill flag gate；meta vs config 漂移 WARN；未初始化=PASS 過渡態）；runner 註冊清單 `[88][89]` 行=號占用正本。 |
| `db/test_l2_memory_healthchecks.py` | [88][89] FakeCursor 全分支（SKIP 語義/表缺/游標缺壞/滯後邊界恰 3 日 PASS/漂移/env model override）+ runner 接線釘子。 |
```

## 10. E1 memory.md 待合併行（PM 合併）

```
## 2026-06-11 L2 記憶層 M2 線（cron 三件套+seed CLI+manual V140+[88][89]）IMPL DONE 待 E2
- 7 source+4 test 全新檔（runner.py 僅 +21 註冊），78 新測試綠+125 鄰接回歸綠；全 flag-OFF inert。偏差裁決：[88][89] 從 PM 實作真 check（flag-OFF=PASS-skip，spec 原僅 reserved 註釋）；seed 自帶 INSERT SQL 從 spec（不 import M1 半成品）；V140=.sql+.sh 兩檔（退出碼 0/1/2/3/4 分類）。教訓：bash `set -u` 下 `$var` 後接全形標點（如「（」）會被併入變數名→必用 `${var}`（mock psql 測試抓到）；spec 的模組路徑（G7 factory）IMPL 前必 find 驗證（control_api_v1 實在 exchange_connectors/bybit_connector 下）。接口假設=run_daily(conn, llm, *, target_date)（合流時核對）。
```

## 11. 不確定之處

- `run_daily` 簽名為假設（§8）；M1 落地後若異，cron 殼一行改 + TypeError log 已預鋪定位。
- [89] 期望 dims=1024/provider='ollama' 是 spec §7 常數；若 M1 embedding.py 改提供 config 讀取點，E2 可指示改讀同源。
- seed B 源 94 條全進 p70/p80 是否過量由 operator dry-run 過目裁決（這正是默認 dry-run 的設計用途）。
- 本批 Mac-only 驗證；OWED E4 Linux：①seed `--apply` 入 scratch DB + 真 recall 中/英命中（spec §13.2-3）；②V140 trading_admin `CREATE EXTENSION` dry-run 裁決路徑 A/B（spec §13.2-2，本工具即路徑 B 載體）；③wrapper Linux 實機跑一輪（flag=0 inert log）；④healthcheck runner 全量跑（[88][89] 在 flag-OFF 下 PASS-skip）。

## 12. Operator 下一步

1. E2 對抗審（重點=§7 偏差裁決 + §8 接口假設 + seed 敏感網覆蓋）。
2. 合流後 E4 Linux 四項（§11）。
3. V139 prod apply（M1 線 owed）→ 才有條件跑 seed `--apply` 與 V140。
4. cron 安裝（installer dry-run → APPLY=1）可先行：flag=0 inert，行為中性。

E1 IMPLEMENTATION DONE: 待 E2 審查（report path: docs/CCAgentWorkSpace/E1/workspace/reports/2026-06-11--l2_memory_m2_cron_seed.md）
