# Polymarket 數據採集軸移植（artifact-only 離線研究）— E1 線 P · 2026-06-11

任務：按 QC 紀律 memo（`docs/CCAgentWorkSpace/QC/workspace/reports/2026-06-11--polymarket_axis_discipline.md`）移植 last30days-skill 的 polymarket.py 為獨立離線採集器。
Base：origin/main `5c37ba48`（已 fetch；未 commit，待 E2→E4→PM 鏈）。
移植源 pin：`mvanhorn/last30days-skill` @ `122158415ae421da83e739f2668032f6bc78d39c`（v3.3.2，MIT，Copyright (c) 2026 Matt Van Horn）。

## 一、檔案清單（9 新檔，零改既有檔）

| 檔 | 行數 | 內容 |
|---|---|---|
| `helper_scripts/research/polymarket_axis/__init__.py` | 86 | 版本常數 + 查詢集 v1（crypto tag + 25 keywords memo 原文）+ MIT attribution dict + lane 枚舉 |
| `helper_scripts/research/polymarket_axis/collector.py` | 676 | ThrottledJsonClient（urllib stdlib、≤2 req/s、指數 backoff、host allowlist）+ Gamma /events tag 枚舉分頁主路 + /public-search keyword 補充 + /markets/{id} follow-up + CLOB /prices-history + market-level 攤平（零過濾） |
| `helper_scripts/research/polymarket_axis/state.py` | 192 | track-to-resolution 登記簿（tracking→resolved/lost 終態機 + 原子持久化 + 30 連敗 lost 防無界） |
| `helper_scripts/research/polymarket_axis/artifact.py` | 271 | append-only run dir（已存在即 raise）+ snapshots/raw_events/raw_markets/prices_history jsonl + manifest + sha256 index + duckdb parquet 鏡像 fail-soft（失敗殘檔清理） |
| `helper_scripts/research/polymarket_axis/cli.py` | 204 | `--mode daily\|hourly-topn\|retrospective`；retrospective 必須顯式 `--market-ids`/`--all-tracked` |
| `helper_scripts/cron/polymarket_axis_cron.sh` | 87 | wrapper（mirror incident_sentinel：lock+heartbeat+fail-soft exit 0；**零 secrets sourcing、零 POSTGRES_***） |
| `helper_scripts/cron/install_polymarket_axis_cron.sh` | 132 | idempotent installer（Linux-only / dry-run 預設 / `OPENCLAW_POLYMARKET_CRON_APPLY=1` gate / `--remove`）；daily `41 4 * * *` 活行 + hourly `7 * * * *` **默認註釋停用**（`OPENCLAW_POLYMARKET_CRON_HOURLY=1` 重裝才活化） |
| `helper_scripts/research/tests/test_polymarket_axis.py` | 682 | 41 test + 1 opt-in 真實煙測 |
| `helper_scripts/cron/tests/test_polymarket_axis_cron_static.py` | 86 | 11 static test（bash -n + 排程/gate/紅線 grep） |

## 二、測試結果（Mac venvs/mac_dev 3.12.13，即時跑）

- `test_polymarket_axis.py`：**41 passed + 1 skipped**（skip=opt-in 真實煙測；單跑 `OPENCLAW_POLYMARKET_SMOKE=1` → **1 passed**）。
- `test_polymarket_axis_cron_static.py`：**11 passed**。
- 全 research suite 回歸：**254 passed + 1 skipped, 0 failed**（既有 213 個 sibling 測試零回歸）。
- mutation bite 雙證（一 mutation 一輪，restore 後綠）：① append-only 守衛改 `exist_ok=True` → `test_append_only_*` 紅；② 攤平層注入 lib 原版 closed 過濾 → `test_closed_and_zero_liquidity_markets_are_kept` 紅。
- 已知併跑限制：research/tests 與 cron/tests 都是 top-level `tests` package，同一 pytest invocation 併跑會 import 碰撞（pre-existing 結構，sibling 慣例即分開跑）。

## 三、真實 API 煙測（樣例與計數）

**Schema probe（採集器動工前先驗假設）**：`/events` 回 **bare JSON array**（非物件包裝）；`tag_slug=crypto` 有效；event-level `volume24hr/1wk/1mo`、`updatedAt`、`competitive` 在；market-level `volume` 是字串、`volume24hr`/`liquidity` **可整欄缺席**（`_float_or_none` 的存在理由）；`outcomes`/`outcomePrices`/`clobTokenIds` 皆 JSON-encoded 字串；`umaResolutionStatus='resolved'` 可作 resolution 終態判據。
**兩個移植期實證修正**：① `/markets?id=` query-form **默認濾掉 closed market 回空**——follow-up 必須用 `/markets/{id}` path-form（probe 實證兩形對照）；② hourly-topn 排序參數 **`order=volume24hr`（camelCase）實證降冪有效**，官方文檔頁建議的 `volume_24hr` snake-case 實測不排序（已內嵌注釋）。

**三 lane 真 CLI 跑**（artifact 留存 `/tmp/pm_axis_smoke/` 供 E2 檢視）：

| lane | 指令要點 | 結果 |
|---|---|---|
| daily（1 頁限縮） | `--mode daily --max-event-pages 1 --keyword-pages 0` | 1 req → 100 events → **596 rows，146 closed rows 保留，0 parse_error**；tracker 451 tracking + 145 resolved；page_cap_hit=true 誠實入 manifest |
| hourly-topn | `--mode hourly-topn --top-n 50` | **1 req** → 50 events → 582 rows |
| retrospective | `--mode retrospective --market-ids 1007590 --interval 1w --fidelity 720` | 2 tokens × 15 points；manifest `lane=retrospective / retrospective=true / point_in_time=false`；run dir 只有 prices_history.jsonl（lane 檔案集合互斥實證） |

manifest sha256 index 逐檔重驗 **全 OK**。樣例 row（節選）：`event_slug=kraken-ipo-in-2025 / market_id=691547 / question="Kraken IPO by December 31, 2026?" / outcomes=[Yes,No] / outcome_prices=[0.31,0.69] / volume24hr=93.18 / liquidity_num=6968.09 / closed=false / query_set_version=v1 / discovery_queries=["tag:crypto"]`。
parquet 鏡像實測（Mac venv 有 duckdb）：snapshots/raw_markets OK、raw_events 轉換失敗 → **非阻斷契約如設計生效**（manifest 記 `partial`、JSONL SoT 完整、殘檔清理已補）。

## 四、QC memo 逐條對照

| QC 條目 | 落地 | 證據 |
|---|---|---|
| §0 定位鐵則（corroborating only / 不直驅交易 / 不碰 CLOB 下單 auth） | `__init__.py` MODULE_NOTE 內嵌鐵則正本指針；host allowlist 僅兩個唯讀 base；零 auth header | `test_host_allowlist_rejects_other_bases` |
| §1 保留 `_parse_outcome_prices`/`_safe_float`/closed-active 判讀 | collector.py 逐式移植 + attribution | `TestPortedParsing` 5 test |
| §1 丟棄 relevance/截斷/`RESULT_CAP`/`_shorten_question` | 未移植；tokenize 剝註釋字串後驗 7 禁字 0 引用 | `test_collector_code_has_no_relevance_truncation_tokens` |
| §1 端點換主：/events 枚舉主路 + /public-search 補充 | `fetch_events_by_tag`（官方參數逐一核對+實證）+ `fetch_search_events` | `TestClient` 分頁 test + 真煙測 |
| §2 查詢集 v1 25 keywords + 版本進 manifest | `QUERY_SET_V1_KEYWORDS` memo 原文；row + manifest 雙載 `query_set_version="v1"` | `test_row_carries_query_set_version_and_lane` / manifest 驗證 |
| §2 欄位最小集 + raw 保底 | 攤平 row 含全部 memo 欄位 + per-row `raw_market`/`raw_event_header` + run-level raw_events.jsonl | 真煙測 0 parse_error |
| §2 append-only / 禁覆寫 | run dir `mkdir(exist_ok=False)`，重名 raise | mutation A bite |
| §2 track-to-resolution | state.py 終態機 + daily follow-up `/markets/{id}` | `TestTrackerState` 7 test + follow-up sweep test |
| §2 採集端最小過濾（零 relevance 截斷、closed 不丟） | 攤平零過濾；event 去重=冪等合併非 ranking | mutation B bite + 真煙測 146 closed kept |
| §2 頻率（daily 全量 / hourly top-N 30-50 / throttle ≤2-5 req/s + backoff） | daily sweep + hourly-topn server-side top-50 + 0.5s min-interval + 指數 backoff | `test_throttle_spaces_requests` / `test_backoff_retry_then_success` |
| §2 歷史回補分道（retrospective 標記 + 拉取日 + 永不混 snapshot） | 獨立 lane + `retrieved_at_utc` + write_run lane 互斥 raise | `TestRetrospective` + `test_lane_isolation_*` |
| §3 存儲形（R-0 紅線 / manifest 形 / duckdb fail-soft / `${OPENCLAW_DATA_DIR:-/tmp/openclaw}`） | 照 aeg_s3 artifact 形 + gate_b 鏡像契約；零生產 import（grep 證僅 stdlib+package） | manifest sha256 重驗 / `test_parquet_mirror_skips_without_duckdb` |
| §3 cron 排程活化=operator | installer dry-run 預設 + APPLY gate + hourly 默認註釋 | `test_installer_hourly_default_commented_operator_gated` |
| §5 不做清單（Kalshi/WS/signal/PG/LLM/engine） | 全未做；wrapper 零 secrets/零 POSTGRES_* | `test_wrapper_zero_secrets_zero_pg` |
| §6 schema 漂移 fail-soft | 解析失敗 row 保留 + raw 全量 + manifest 記 errors | `test_flatten_failure_still_emits_row_with_raw` |

## 五、E1 小決策（按 prompt 授權自行擇定，附理由）

1. **HTTP 層內嵌 collector.py 不另開模塊**：嚴守任務給定的 4 模塊結構（gate_b_rest 同樣 HTTP+邏輯一檔）；HTTP 用純 urllib stdlib（aeg_s3 生態的 gate_b_rest 慣例，非 requests）。
2. **hourly-topn 用 server-side `order=volume24hr&limit=50` 單請求**：deterministic、1 req/輪；「top-N 圈定」是 memo §2 規定的 hourly 查詢範圍，非採集端 relevance 截斷。
3. **raw 雙層**：run-level `raw_events.jsonl`（verbatim 事實源）+ per-row `raw_market`+`raw_event_header`（memo 欄位表列明 `raw`；header 去 markets 鍵防 sibling N 倍重複）。
4. **follow-up 觀測歸 snapshot lane**（`row_source=resolution_follow_up`）：它是「現在抓到的現值」即 point-in-time 觀測；retrospective 僅指 prices-history 回補序列。
5. **state 檔在 `polymarket_axis_state/` 與 run dirs 分離**：登記簿是可變狀態，混入 append-only 區會破不變量。
6. **lost 終態（30 連敗）**：防 404 死 id 讓 follow-up 請求無界累積（latent-unbounded 既有教訓）。

## 六、治理對照

- 零生產模組 import / 零 auth / 零 PG / 零 signal 輸出 / 零 order：grep 證 imports 僅 stdlib+package；硬邊界 token（max_retries/live_execution_allowed/execution_authority/system_mode）grep 0 命中。
- 跨平台：零 `/home/ncyu`、`/Users/` 字面（命中僅測試負面斷言自身）；root 全 env 推導。
- 檔案大小：最大 collector.py 676 / 測試 682，全部 <800。
- 注釋：Chinese-first，MODULE_NOTE 全 5 模塊 + 2 shell 檔頭；MIT attribution pin commit 進 MODULE_NOTE 與 manifest 雙處。
- 多 session 並行：footprint 恰好 9 個自有新檔；SCRIPT_INDEX.md / memory.md 按任務指示**未動**（其他 session 的髒檔零觸碰）。

## 七、不確定之處（誠實披露）

1. **存儲量大於 memo 估算**：per-row raw 設計下 daily 全量 sweep 估 ~20-50MB/day（非「數 MB」）；hourly 若活化再 +~120-190MB/day。對 40TB NAS 可忽略，但 operator 活化 hourly 前應知。
2. **duckdb 對 raw_events.jsonl 轉換失敗**（深嵌套 event JSON）：非阻斷契約正確吞掉並記 manifest，JSONL SoT 不受影響；要不要調 duckdb 參數屬研究端便利性，未擴 scope。
3. **首輪 Linux 真跑的 follow-up 量**：全新 state 下第一輪無 follow-up；穩態 follow-up 數 = 每日 close 掉出枚舉的 market 數（有界），但無實測值。
4. tag 枚舉只圈 `closed=false` 的 active events（discovery 範圍=查詢集 v1 語義）；歷史已 closed 事件如需回補屬 retrospective lane 另議。

## 八、Operator / PM 下一步

1. E2 對抗審 → E4 Linux 回歸（含 trade-core 真跑一輪 daily + installer dry-run）→ PM commit。
2. Linux 部署後 operator 跑 `install_polymarket_axis_cron.sh`（dry-run 看 entry）→ `OPENCLAW_POLYMARKET_CRON_APPLY=1` 安裝 daily；hourly 活化另行決策（H1 lead-lag 需要它）。
3. H4 calibration 前置 gate：resolved n≥50 後研究端起算（state 檔 `resolved` 計數即進度表）。

## 九、SCRIPT_INDEX.md 待合併行（PM 合併時用；本任務按指示未動該檔）

新節 `## 2026-06-11 Polymarket 數據採集軸（research/polymarket_axis/）`：

| 檔 | 說明 |
|---|---|
| `research/polymarket_axis/`（__init__/collector/state/artifact/cli） | Polymarket Gamma 賠率 point-in-time 採集器（artifact-only 離線研究軸，QC 紀律 memo 2026-06-11 正本）：/events tag=crypto 枚舉主路 + /public-search 25-keyword 補充（查詢集 v1 進 manifest）+ track-to-resolution（closed 續抓至 uma resolved，state 持久 `polymarket_axis_state/`）+ CLOB /prices-history retrospective 獨立 lane（永不混 snapshot）。零過濾零截斷（raw 全量保底）、append-only run dir（重名 raise）、manifest+sha256 index、duckdb parquet 鏡像 fail-soft、urllib-only ≤2 req/s + backoff。R-0 紅線：零生產 import / 零 auth / 零 PG / 零 signal。MIT 移植 pin `mvanhorn/last30days-skill@12215841`。 |
| `cron/polymarket_axis_cron.sh` | wrapper（lock + stale-lock 自清 + heartbeat + fail-soft exit 0；零 secrets / 零 PG env——本軸 R-0）。模式參數 daily\|hourly-topn。 |
| `cron/install_polymarket_axis_cron.sh` | idempotent installer（Linux-only / dry-run 預設 / `OPENCLAW_POLYMARKET_CRON_APPLY=1` 才寫 / `--remove`）。daily `41 4 * * *` UTC + hourly `7 * * * *` 默認註釋停用（活化=operator：`OPENCLAW_POLYMARKET_CRON_HOURLY=1` 重裝）。 |

— E1（線 P），2026-06-11。未 commit；待 E2 審查。

---

## 十、修復輪（E2 RETURN P-1/P-2 + E3 findings，2026-06-11/12，續作棒完成）

> 修復輪前一棒被月度限額殺死（P 線源碼改動已全部完成、測試未補）。本棒逐項盤點
>（讀碼 + py_compile）後 NO-OP 跳過已完成項、補測試與一處小修。E2 正本：
> `E2/workspace/reports/2026-06-11--sentinel_polymarket_smallitems_review.md`。

### 盤點與完成狀態

| 項 | 修復輪前一棒 | 本棒動作 |
|---|---|---|
| P-2 壞 entry 容錯 | 源碼 DONE（`state.py` `entry["status"]`→`.get` 兩處 + **壞條目計數**：`counts()` 新 `STATUS_UNKNOWN` 披露桶，流進 manifest `stats.tracker_counts`（collector:647→cli:94）——壞 entry 可見不靜默、不毀整輪 sweep） | NO-OP；補 `TestTrackerState` ×3（缺 status 寫面不炸+不進 follow-up / unknown 桶計數（缺鍵+未知值） / load_state round-trip 後全 API 不炸） |
| P-1 parquet 原子寫 | 源碼 DONE（`artifact.py` 寫 `.parquet.tmp` + `os.replace` 原子落位；失敗分支 unlink tmp 殘檔；最終路徑在 replace 前零觸碰）；**/tmp/pm_axis_smoke 0-byte raw_events.parquet 殘檔已由前一棒清除**（實查 smoke-daily-1page 現無該檔，dir mtime 23:34） | NO-OP；補 `TestArtifact` ×1（fake duckdb 注入轉換中途炸：status=partial + 最終路徑零殘檔 + tmp 已 unlink + 好檔照常產出——舊直寫版此測必紅=真 bite） |
| E3 LOW 禁 redirect | 源碼 DONE（collector 自帶 `_RedirectRefusedHandler`+`_urlopen_no_redirect` 為 `ThrottledJsonClient` 默認 opener；gamma+clob 兩 host 全走單一 `get_json` chokepoint；30x 在 client 立即收斂 `redirect_refused` 不浪費 retry） | NO-OP；補 `TestClient` ×3（30x fail-fast 恰 1 call / default opener 接線斷言 / handler message 有界）；**新增小修**：redirect-refused message 的 `newurl` 截斷 200（與 canary/alert_sink.py 同步——Location 外部可控，原樣嵌 error 經 cron log 無界） |
| cron wrapper exc log 截斷自查 | — | 自查結論：collector `last_error`/`parse_error`/errors 列表嵌的 exc str 皆型別+短訊息（JSONDecodeError str 不嵌全文）；cli 頂層 traceback 有界；唯一無界點=redirect newurl（已截斷）。wrapper 只 append python 輸出，無自建無界面 |

### 測試（親跑，Mac venvs/mac_dev py3.12）

- `test_polymarket_axis.py` **48 passed + 1 skipped**（=E2 基線 41+1s + 7 新）；`test_polymarket_axis_cron_static.py` **11 passed**。
- research/tests 全套 **262 passed + 1 skipped + 0 failed**（=E2 基線 254+1s + 7 本棒 + 1 來自並行 AEG-S3 線 `03b308c7` commit，main 在 E2 審後前移）。
- 註：research/tests 與 cron/tests 兩目錄**同名 package `tests` 不能同一 pytest invocation 合跑**（collection ImportError）——以無關檔對照證實為 pre-existing 結構性，非本批引入；E2 原本也分開跑。

### 治理對照 / 偏差

- P-3（snapshots per-row raw_market 雙存瘦身）按 E2 裁定不擋，仍留 follow-up（研究端取捨）。
- 硬邊界 token 0、硬編碼 user path 0；未動 SCRIPT_INDEX / memory.md / TODO.md（派工契約）；memory_distiller / V139 / seed（並行修復線）零觸碰。

### 下一步

narrow re-E2（只審 delta）→ E4 Linux 回歸（含 duckdb 真鏡像一輪驗 partial 路徑）。

— E1（修復輪續作棒），2026-06-12。未 commit。
