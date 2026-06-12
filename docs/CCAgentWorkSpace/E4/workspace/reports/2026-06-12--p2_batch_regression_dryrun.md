# E4 回歸 + Linux empirical dry-run — 「殘項+BB 哨兵+P2 三項」批次 · 2026-06-12

- 被驗：工作樹 52 項全 uncommitted @ main `5a28ee16`（==origin/main，跑前/跑後 fetch 皆 0/0，全程無 sibling 推進）。
- 前置鏈：E1 兩線 → E2 四線（A 線 RETURN 1MED+3LOW / B 線 RETURN 1MED+3LOW）→ 修復輪 → narrow re-E2 PASS（12/12）。
- 環境：Mac `venvs/mac_dev` py3.12.13 / pytest 9.0.3，`PYTHONDONTWRITEBYTECODE=1 PYTHONHASHSEED=0`、跑前清 __pycache__/.pytest_cache、`-p no:cacheprovider`；Linux trade-core PG16（host psql 16.14，`psql -h 127.0.0.1 -U trading_admin`）。
- **總裁決：GREEN（PASS，ready for PM commit）**。

## A. Mac 回歸 — 四元組總帳（passed/failed/skipped/error；全部跑兩遍 byte-identical，零 flake）

| Suite | run1 | run2 | E1 宣稱 | 對賬 |
|---|---|---|---|---|
| learning_engine 全樹（含 memory_distiller package 140） | 543/0/0/0 | 543/0/0/0 | 543 | ✓（=403 既有+140 新，算術守恆） |
| memory_distiller 全套 252 = package 140 + seed 39 + cron 37 + healthchecks 24 + V140 12 | 全綠（分屬下列各套） | 同 | 252 | ✓（140+39+37+24+12=252 逐項實測） |
| canary 全目錄（427 collected = 四套 197 + healthchecks/tests 111 + 既有 119） | 427/0/0/0 +9 subtests | 同 | 四套 197 | ✓（watchdog_alert 41+engine_watchdog 40+bybit_sentinel 58+incident_sentinel 58=197 collect 精確） |
| incident_sentinel（=「sentinel(58)」） | 58 綠（在 canary 內） | 同 | 58 | ✓ |
| research/tests 全套（含 polymarket_axis 49） | 266/0/1s/0 | 266/0/1s/0 | 262+1s | **+4 = main 側 sibling commits**（`25ec85dd`/`5a0f9ab3`/`03b308c7` AEG-S3 線 +305 行測試，git log 歸因；polymarket 本檔 49=E2 時 41+修復輪 8 精確），0 回歸 |
| cron 全套（含 l2_memory_distill 37 + polymarket static 11） | 139/0/0/0 | 139/0/0/0 | 37/11 | ✓ |
| memory/seed | 39/0/0/0 | 39/0/0/0 | 39 | ✓ |
| db l2_memory_healthchecks + apply_manual_v140 | 36/0/0/0 | 36/0/0/0 | 24+12 | ✓ |
| healthcheck 鄰接 5 檔（mlde/cron_heartbeat/lg5/f7/replay_maintenance） | 164/0/0/0 | 164/0/0/0 | 164 | ✓ |
| ml_training（既有回歸抽查） | 712/0/16s/0 | 712/0/16s/0 | 基線 712/16s | ✓ 精確 |
| analyze_token_usage 自帶測試 | 無此檔（E2 A-1 INFO，修復輪未補）；py_compile + `--help` rc=0 | — | 「若有」 | 誠實標：無 checked-in 測試 |

error 欄全程 0。GUI 靜態（node --check）N/A：批次 0 個 .js。cross-language float N/A：純 Python/SQL/bash，0 Rust 觸碰。

## 改動面證明（A2）

- `git diff --name-only`（tracked code）僅 4 檔：`helper_scripts/canary/engine_watchdog.py`、`helper_scripts/canary/test_watchdog_alert.py`、`helper_scripts/db/passive_wait_healthcheck/runner.py`、`helper_scripts/SCRIPT_INDEX.md`（+docs/memory.md 多檔）。
- untracked `program_code/**` 僅 `learning_engine/memory_distiller/`（全新 package）。
- **grep rust/|openclaw_engine|execution|control_api = 0 命中 → 零 engine/execution 面**。
- 正式 BASELINE（4728/66，scope=control_api_v1/tests）**沿用不變**：該 scope 0 檔被觸碰、新檔無名稱遮蔽，結構性 delta=0（hurst-regime 條目同款先例）；未重跑 25min 全套屬比例原則，非省略。

## 靜態檢查（A3）

- **40/40 新+改 .py `py_compile` PASS**；**7/7 新 .sh `bash -n` PASS**。
- 3 個 installer（brief 寫「兩個」，實物 3 個，全測）：Mac 平台守門全 exit=2 fail-closed 正確拒跑；**Linux dry-run 全 rc=0**（proposed entry+rollback+「DRY-RUN: not modifying crontab」），前後 crontab md5 `71ece83a…` 不變。
- V139/V140 SQL 無法 Mac dry → 已 Linux 實證（§B）。

## Mutation 錨 4/4 親驗 bite（cp+shasum 備份還原；還原後 4 檔 shasum byte-identical、marker grep=0、239 測後綠）

| 錨 | 注入 | 結果 |
|---|---|---|
| M-C（MIT C-3/E2 MED-1 修）`pipeline._resolve_embed_client` lazy 建構 → None | **恰 2 紅**（flag-ON 建構達 embed HTTP + thread 進 recall）== 修復輪宣稱 |
| M-F（MIT 條件① 修）`recall_for_prompt` `hint_mode=True→False` | **1 紅精準**（CJK 混排路由測試）。註：修復輪 8 紅是打 recall_top_k 內部分支；本錨打 call-site 路由縫=更窄，1 紅為該縫唯一釘子，非缺口 |
| W-3（E2 修）sentinel `_strip_control` → no-op | **3 紅**（TestFormatAlertSanitization：換行注入/type_key+escalators/unicode 保留） |
| W-2（E2 修）watchdog sink 失敗仍稱 recorded | **1 紅精準**（`test_unconfigured_sink_failed_says_lost_never_recorded`） |

## B. Linux empirical（scratch `openclaw_scratch_e4_1781253116`，template0 + locale en_US.utf8 == prod；prod 全程唯讀）

### B4 V139 雙 apply + Guard + REVOKE

- **V138 先 apply（C-2 prod 連帶順序彩排）RC=0** → **V139 first RC=0**（兩表+5 索引+生成列+三 CHECK+grant 分支 fire：`trading_ai = SELECT/INSERT/UPDATE; DELETE revoked` NOTICE）→ **V139 re-apply RC=0、9 個 "already exists, skipping"、零 ERROR、COMMIT 收尾**＝冪等實證。過程註記：S1 第二次 apply 的 RC echo 因本地 tee|head SIGPIPE 截斷遺失，以第三次 apply（同一 re-apply 代碼路徑，遠端落 log）補證。
- **Guard A 漂移負測**：drift 庫預建缺 14 欄表 → V139 **RC=3 精確 RAISE**（列出全部 14 缺欄）；事務性：0 索引殘留（不半套用）。Guard B/C 在 re-apply 零 false-RAISE。重複建表/索引顯式重放=NOTICE no-op。
- **grant/REVOKE**（scratch 自建 `trading_ai` NOLOGIN role，teardown 已歸還）：`has_table_privilege(trading_ai)` 兩表 **DELETE=false / INSERT=SELECT=UPDATE=true**；`SET ROLE trading_ai; DELETE` → **permission denied**（無 USAGE 時拒於 schema 級；GRANT USAGE 後拒於**表級**=DELETE revoke 真咬）；trading_ai INSERT 經 USAGE 可通（grant 真可用）。
- **owner DELETE 字面實測（brief「以 trading_admin DELETE→應拒」）**：trading_admin 是表 owner，PG owner 隱含權不受 REVOKE FROM PUBLIC/trading_ai 影響 → **DELETE 1 成功**（BEGIN/ROLLBACK 不留痕）。brief 預期與 PG owner 語義不符；此即 E2 INFO-2 已標「REVOKE 宣示性，content 不可變靠 application discipline+測試」的已接受設計，**非回歸**（severity INFO / confidence 高）。
- CHECK 三探針全咬：supersede 無指針 / mem_type 非法 / priority=-2 全拒；content_tsv 真生成 tsvector。

### B5 V140 權限裁決

- **`CREATE EXTENSION vector` 以 trading_admin 於 scratch = 成功（RC=0）→ 裁決：V140 可裝（路徑 A 權限成立）**；manual 路徑 B 工具照樣有效=保守超集。
- applier `.sh` 雙跑 **exit 0/0**（二跑 3 個 no-op NOTICE=冪等）；verify embedding udt=`vector` + HNSW 索引在。前提負測（無 V139 庫）→ **exit 4** 訊息精確。
- 部署註記：`bge-m3` 未 pull（Ollama tags 僅 qwen3.5 9b/27b）→ V140 裝了 embedding 軸仍 FTS-only 直到 operator `ollama pull bge-m3`（G6 已知事實，運行時 fail-soft by design）。

### B6 seed --apply scratch 實證（MIT C-1）

- prod `agent.lessons` dead_mode 6 rows **唯讀 COPY** 入 scratch（V133 淺依賴先 apply）→ A 源幾何忠實。
- **seed --apply：A源=6 B源=94 inserted=100**；敏感攔截 5 條與 Mac dry-run 完全一致；**[VERIFY-en] hits=5 top 0.732（真 dead-mode rows 居首）/ [VERIFY-zh] hits=5 top 0.333** → exit 0；fail-closed exit-1 路徑代碼+Mac 測試雙釘（C-1 維持）。
- **重跑 inserted=0 / already_present=100** = 冪等錨真 PG 實證。
- 三組 recall（word_similarity 0.3 + `<%` 真運算子 + SET LOCAL 事務作用域全真跑）：中文「風控 教訓 修復」3 hits@0.333；英文「dead mode funding beta neutral」3 hits@0.732/0.666/0.581；混排「watchdog 告警 sink 修復 fail-closed」3 hits@0.400/0.375——**中/英/混排三語制全真召回**。行數帳閉合：100 seed + 1 E4 probe row = 101（incident 60 + rule 41）。
- **[88][89] 對 scratch**：flag-OFF = `('PASS','SKIP (flag off)…')` ×2 精確；flag-ON（INFO 加測）[88]=WARN cursor-missing（從未跑過的主機之誠實真態）、[89]=PASS 過渡態（meta 未初始化）。

### B7 Ollama 煙測

`/api/tags` 可達（qwen3.5:9b-q4_K_M + 27b）；`/api/generate` 1-token：done=True / eval_count=1 / model 回顯正確 —— LocalLLMClient 假設的 endpoint 形（tags 探測 + generate 單輪）實機成立，未跑真蒸餾。

### B8 清場 + prod 零觸碰終驗

scratch 主庫+drift 庫+nov139 庫全 dropdb（scratch like-query=0）；`DROP ROLE trading_ai`（pg_roles=0 復原）；`/tmp/e4-seed-test` 已刪。**prod：`_sqlx_migrations` head=137 / count=120 前後不變；agent.agent_memory 不存在；vector installed_version 空；dead_mode 仍 6**。

## MIT §C 四項覆蓋聲明

| # | 狀態 |
|---|---|
| C-1（E4 gate） | **DONE**：scratch 以 prod locale en_US.utf8（template0 顯式）建；spec §13.2 全跑（雙 apply/Guard A 漂移/DELETE revoke/seed 真 recall 中英/V140 裁決）；recall fail-closed exit-1 維持 |
| C-2（prod apply gate） | **彩排完成+移交 PM**：V138→V139 順序於 scratch 實跑（V138 先）；prod head=137 證雙 pending。**PM 的 prod apply 計劃必須寫明「本次連帶 V138（operator-gated 決策於此消費）」+ apply 前跑 sqlx checksum drift 檢核**——此半屬 operator-gated，非本輪可執行 |
| C-3（embedding 軸啟用 gate） | **VERIFIED**：`_resolve_embed_client` lazy 建構已落地且 mutation-bite（2 紅）；flag 默認 OFF |
| C-4（B3 接線批 gate） | **VERIFIED dormant**：零 layer2_engine/control_api diff（git 自證）；`set_embedding` 不 bump updated_at 不變式碼內註記+V140 runbook 文檔化；binding 移交未來 B3 批次 |

## Findings 全量（零 CRITICAL/HIGH/MED；全 INFO）

1. **INFO/高**：owner(trading_admin) DELETE 可刪（PG owner 語義；E2 INFO-2 已接受設計；runtime 連線恰為 owner→唯一防線=application discipline+測試白名單，已有 `test_all_update_statements_touch_only_whitelisted_columns` 類釘子）。
2. **INFO/高**：V139 對 trading_ai 無 `GRANT USAGE ON SCHEMA agent` → 若未來真建 trading_ai app role，INSERT 會 loud-fail（fail-closed 方向；role 現 prod 不存在=latent；mirror V133/V138 同款範式）。
3. **INFO/高**：bge-m3 未 pull → V140 裝後 embedding 軸仍 FTS-only（operator 部署清單項）。
4. **INFO/高**：research 套件 +4 vs brief 262 = main 側 AEG-S3 sibling commits（歸因閉合，非本批）。
5. **INFO/中**：analyze_token_usage 無 checked-in 測試（E2 A-1 既標 optional；py_compile+--help+E2 合成驗證在卷）。
6. **INFO/低**：S1 第二次 apply echo 被本地 SIGPIPE 截斷（第三次 apply 同路徑補證；教訓=遠端落 log 再取，勿 tee|head 長流）。

## 跑兩遍聲明

全部 Mac 套件 run1==run2 byte-identical（含 subtests 計數）；Linux seed/V140/V139 各自雙跑（apply×2、seed×2）冪等同值。flaky=0。

## BASELINE

正式 BASELINE 沿用 `2026-06-11 passed=4728 failed=66`（scope=control_api_v1/tests；本批 0 檔觸碰該 scope，結構性 delta=0）。新增 SCOPED-BASELINE 見 memory 追加行。

**E4 REGRESSION DONE: PASS（GREEN）** — owed：①V139+V138 prod apply（operator-gated，C-2 計劃語句移交 PM）；②`ollama pull bge-m3`（embedding 軸真活化前置）；③cron installer APPLY=1 真裝（operator）。
