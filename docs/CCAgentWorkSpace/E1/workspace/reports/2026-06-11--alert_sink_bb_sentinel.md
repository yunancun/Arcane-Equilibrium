# E1 報告 — watchdog 告警耐久 sink + Bybit 公告增量哨兵三件套（線 W，續作棒收尾）

- 日期：2026-06-11 · 角色：E1（線 W，續作棒第二棒）
- 設計 SSOT：`docs/CCAgentWorkSpace/BB/workspace/reports/2026-06-11--bybit_announcement_sentinel_advisory.md`（全文已讀，endpoint/severity 映射/去重鍵/輪詢紀律照它）
- 狀態：IMPLEMENTATION DONE，待 E2 審查。未 commit（鏈 E1→E2→E4→QA→PM）。

---

## 0. 前一棒遺留盤點（續作棒紀律：NO-OP 跳過，禁止重做）

前一棒（27 tool uses 被 API Overloaded 殺死）git status+diff 盤點結果：

| 件 | 前一棒狀態 | 本棒處置 |
|---|---|---|
| `engine_watchdog.py` sink edit（+68 行） | 完整（常數+`_append_alert_sink`+`_send_alert_best_effort` 接線） | 驗證後 NO-OP 保留 |
| `test_watchdog_alert.py` +TestAlertSink 6 測試（+126 行） | 完整 | 親跑全綠後 NO-OP 保留 |
| `bybit_announcement_sentinel.py`（535 行，untracked） | 完整（讀全文逐條對 BB advisory 驗合規） | NO-OP 保留 |
| `bybit_announcement_sentinel_cron.sh`（untracked） | 完整（鎖+stale-lock 自清+heartbeat+fail-soft，mirror incident） | `bash -n` 過後 NO-OP 保留；補 chmod +x |
| `install_bybit_announcement_sentinel_cron.sh` | **缺** | 本棒新建 |
| `test_bybit_announcement_sentinel.py` | **缺** | 本棒新建（53 測試） |
| `bybit_api_reference.md` §1.11+§4.1 append | **缺** | 本棒完成 |
| 測試跑全+真實煙測+報告 | **缺** | 本棒完成 |

並行三線（memory_distiller/V139/cron/seed/polymarket_axis）的未 commit 成果（含 `SCRIPT_INDEX.md`、各 `memory.md`、`passive_wait_healthcheck/runner.py`、V139/V140、`helper_scripts/memory/` 等）**全程未碰**。`SCRIPT_INDEX.md` 現行 diff 經查 100% 是並行線內容（analyze_token_usage/mnemopi），0 行屬本線。

## 1. 任務摘要

① watchdog 告警鏈補「無 creds 也必達」本地耐久 sink：`_send_alert_best_effort` 在嘗試 Telegram/webhook **之前**無條件 append 一條 JSON 到 `<data_dir>/alerts/alerts.jsonl`；全程吞例外不拋不阻塞；>5MB 輪轉一代；creds 缺席不再完全沉默（sink+INFO log）。
② Bybit 公告增量哨兵三件套：plain GET 公開 API（零 credential 面）→ seen-set 差集去重（禁 watermark）→ BB §2 severity 分級 → `_resolve_alert_fn()` 接 watchdog emitter；cron 30min（7,37 offset）+ 冪等 installer；alert-only 零 PG 零 runtime。

## 2. 修改清單（線 W 全footprint，2 modified + 4 new + 1 doc）

| 檔 | 性質 |
|---|---|
| `helper_scripts/canary/engine_watchdog.py` | modified（+68，前一棒；surgical：4 常數 + `_append_alert_sink` + `_send_alert_best_effort` 三處接線） |
| `helper_scripts/canary/test_watchdog_alert.py` | modified（+126，前一棒；TestAlertSink ×6） |
| `helper_scripts/canary/bybit_announcement_sentinel.py` | new（535 行，前一棒） |
| `helper_scripts/canary/test_bybit_announcement_sentinel.py` | new（本棒，53 測試） |
| `helper_scripts/cron/bybit_announcement_sentinel_cron.sh` | new（前一棒；本棒 chmod +x） |
| `helper_scripts/cron/install_bybit_announcement_sentinel_cron.sh` | new（本棒，mirror install_incident_sentinel_cron.sh） |
| `docs/references/2026-04-04--bybit_api_reference.md` | modified（本棒：§1.11 get_announcements 新節 + §4.1 表 Announcement 行，BB memo §7 草稿落地、佔位符填實） |

## 3. watchdog diff 全文（`git diff helper_scripts/canary/engine_watchdog.py`）

```diff
diff --git a/helper_scripts/canary/engine_watchdog.py b/helper_scripts/canary/engine_watchdog.py
index 0d452649..9c484ae6 100755
--- a/helper_scripts/canary/engine_watchdog.py
+++ b/helper_scripts/canary/engine_watchdog.py
@@ -105,6 +105,14 @@ ALERT_CONFIG_FILE = "alert_config.json"
 # Alert HTTP timeout — stricter than the app's 10s; the watchdog must never stall.
 # 告警 HTTP 超時 — 比 app 的 10s 更嚴；watchdog 絕不可被告警卡住。
 ALERT_HTTP_TIMEOUT_SECONDS = 5.0
+# WATCHDOG-ALERT-SINK (2026-06-11)：本地耐久告警 sink。
+# 為什麼需要：Telegram/webhook creds 缺席（P2p operator 後補中）時告警完全蒸發——
+# 「無 creds 也必達」的最後防線是無條件 append 到 <data_dir>/alerts/alerts.jsonl，
+# 之後才嘗試遠端通道。sink 失敗絕不影響原 best-effort 發送語義。
+ALERT_SINK_DIRNAME = "alerts"
+ALERT_SINK_FILE = "alerts.jsonl"
+ALERT_SINK_MAX_BYTES = 5 * 1024 * 1024  # >5MB 輪轉一代（rename .1，保一代）
+ALERT_SINK_BODY_MAX_CHARS = 2000  # body 截斷上限（防單條告警撐爆 sink）
 ENGINE_LOG_FILENAME = "engine.log"
 ENGINE_LOG_ROTATED_DIRNAME = "engine_logs"
 ENGINE_LOG_ROTATED_GLOB = "engine-*.log"
@@ -661,6 +669,43 @@ def _load_alert_creds(data_dir: str) -> dict:
     return cfg
 
 
+def _append_alert_sink(
+    data_dir: str, subject: str, body: str, severity: str, channels_attempted: list
+) -> None:
+    """本地耐久告警 sink：append 一條 JSON 到 <data_dir>/alerts/alerts.jsonl。
+
+    為什麼存在：遠端通道（Telegram/webhook）creds 缺席或全掛時，告警不得蒸發——
+    本地 jsonl 是「無 creds 也必達」的最後審計線（operator 可事後 tail 查）。
+    為什麼包死 try/except 永不拋：sink 是附加觀測面，任何 I/O 失敗（磁碟滿/權限/
+    路徑被占）都不得影響 _send_alert_best_effort 原有 best-effort 語義，
+    更不得回拋進 watchdog 恢復迴圈。
+    輪轉：append 前 size > ALERT_SINK_MAX_BYTES → os.replace 成 .1（保一代），防無界增長。
+    channels_ok 恆 null：發送是 fire-and-forget daemon thread，append 時點無法同步
+    得知送達結果；欄位保留為 schema 前向兼容（未來同步確認模式可填真值）。
+    """
+    try:
+        sink_dir = Path(data_dir) / ALERT_SINK_DIRNAME
+        sink_dir.mkdir(parents=True, exist_ok=True)
+        path = sink_dir / ALERT_SINK_FILE
+        try:
+            if path.stat().st_size > ALERT_SINK_MAX_BYTES:
+                os.replace(path, path.with_suffix(".jsonl.1"))
+        except OSError:
+            pass  # 檔不存在或 stat 失敗 → 不輪轉，直接 append
+        record = {
+            "ts_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
+            "subject": str(subject),
+            "severity": str(severity),
+            "body": str(body)[:ALERT_SINK_BODY_MAX_CHARS],
+            "channels_attempted": list(channels_attempted),
+            "channels_ok": None,
+        }
+        with open(path, "a", encoding="utf-8") as f:
+            f.write(json.dumps(record, default=str) + "\n")
+    except Exception as exc:  # noqa: BLE001 - sink 失敗絕不影響告警主路徑
+        logger.debug("alert sink append failed (non-fatal): %s", exc)
+
+
 def _post_telegram_alert(token: str, chat_id: str, text: str) -> None:
     """stdlib urllib 送一則 Telegram 訊息；catch-all，永不拋（在 daemon thread 內呼叫）。"""
     try:
@@ -699,16 +744,21 @@ def _send_alert_best_effort(subject: str, body: str, severity: str, data_dir: st
     """best-effort 發告警：file/env 讀憑證，daemon thread fire-and-forget，5s timeout，catch-all。
 
     為什麼 fire-and-forget + 永不拋：告警必須與 watchdog 恢復迴圈完全解耦 —— 任何
-    掛起 / 失敗 / 缺端點都不得拖住 poll 或阻塞重啟。無任一通道配置時靜默 no-op，
-    僅一次性 logger.warning（避免每 poll 灌 log）。憑證只讀進記憶體，絕不寫進
+    掛起 / 失敗 / 缺端點都不得拖住 poll 或阻塞重啟。憑證只讀進記憶體，絕不寫進
     canary_events.jsonl / log / payload（log 通道名，不 log token）。
+    WATCHDOG-ALERT-SINK (2026-06-11)：嘗試任何遠端通道「之前」，無條件 append 一條
+    JSON 到本地耐久 sink（_append_alert_sink）——無通道配置時不再完全沉默（sink 必達
+    + 每次一行 INFO log；一次性 warning 保留）。sink 失敗被吞，不影響本函數對外語義。
     消費者註記：incident_sentinel.py（P2p 哨兵）sibling-import 本函數發告警——改簽名須同步該檔與其簽名 smoke 測試。
     """
     global _alert_unconfigured_warned
+    resolved_dir = data_dir or os.environ.get("OPENCLAW_DATA_DIR", "/tmp/openclaw")
     try:
-        creds = _load_alert_creds(data_dir or os.environ.get("OPENCLAW_DATA_DIR", "/tmp/openclaw"))
+        creds = _load_alert_creds(resolved_dir)
     except Exception as exc:  # noqa: BLE001 - 憑證讀取必須 fail-safe
         logger.debug("alert creds load failed (non-fatal): %s", exc)
+        # 憑證讀取失敗也要落 sink（channels_attempted 留空）——耐久線無條件成立。
+        _append_alert_sink(resolved_dir, subject, body, severity, [])
         return
 
     tg = creds["telegram"]
@@ -716,6 +766,14 @@ def _send_alert_best_effort(subject: str, body: str, severity: str, data_dir: st
     tg_active = bool(tg["enabled"]) and bool(tg["bot_token"]) and bool(tg["chat_id"])
     wh_active = bool(wh["enabled"]) and len(wh["urls"]) > 0
 
+    channels_attempted = []
+    if tg_active:
+        channels_attempted.append("telegram")
+    if wh_active:
+        channels_attempted.append("webhook")
+    # 本地耐久 sink：在任何遠端通道嘗試之前無條件 append（失敗被吞，永不拋）。
+    _append_alert_sink(resolved_dir, subject, body, severity, channels_attempted)
+
     if not tg_active and not wh_active:
         if not _alert_unconfigured_warned:
             logger.warning(
@@ -723,6 +781,10 @@ def _send_alert_best_effort(subject: str, body: str, severity: str, data_dir: st
                 "/ 告警通道未配置 — engine-down 告警停用",
             )
             _alert_unconfigured_warned = True
+        # creds 缺席不再完全沉默：sink 已落，補一行 INFO 指向本地 jsonl。
+        logger.info(
+            "alert recorded to local sink only (channels unconfigured): %s", subject,
+        )
         return
 
     text = f"[{severity}] {subject}\n{body}"
```

## 4. 測試計數（Mac venvs/mac_dev python 3.12.13，2026-06-11 親跑）

| Suite | 結果 |
|---|---|
| `test_bybit_announcement_sentinel.py`（新） | **53 passed** |
| `test_watchdog_alert.py`（22 既有 + 6 新 TestAlertSink） | **28 passed** |
| `test_incident_sentinel.py`（回歸：emitter 簽名接縫共用） | **58 passed** |
| `test_engine_watchdog.py`（回歸：同檔被改） | **40 passed** |
| **合計** | **179 passed / 0 failed** |

新 53 測試覆蓋：去重鍵 9（normalize/blt/sha256 fallback/malformed/**watermark 行為證明**=比已見更舊的未見公告仍告警 + 剝 COMMENT/STRING 的 code-token 輔證）/ 分類映射 13（8 type 檔位+tag/keyword escalator+word-boundary 防 capital→api+watchlist env 注入無內建默認）/ fetch 8（V5 envelope 衛生/恰 1 call/請求形 locale+page+limit 無 type/retCode/403/壞 JSON/list 缺/空 list 非錯）/ baseline+增量 9（首輪 flood guard/二輪僅新件/三輪去重/url 變體同鍵/P2 落 state 不告警/malformed 不毒化/untrusted body 不含 description/上限+彙總/dry-run）/ 修剪 3（>90d 清/近期留/壞 ts 視同過期）/ fail-quiet 5（exit 0+不耗 baseline/單次 call 禁 tight retry/恰閾值輪 1 條 meta-alert/成功歸零/壞 state 自癒）/ 接縫+結構 6（emitter 4-arg 簽名 smoke/_resolve_alert_fn 真解析/subject 前綴+截斷/零 credential 零 DB source 斷言/host 鎖 api.bybit.com/唯一本地寫入=state json）。

測試陷阱（已修，承 L2 P2 教訓）：watermark 裸 source-grep 會被 MODULE_NOTE 解釋文（「禁 timestamp watermark」）誤紅 → 改行為證明 + tokenize 剝註解字串；watchlist 硬編碼 grep 會被 docstring csv 範例誤紅 → 改行為斷言（env 未設=空 tuple）。

## 5. 真實 API 煙測樣例（恰 1 call，2026-06-11 22:38 local，scratch dir /tmp/bb_sentinel_smoke）

```
GET https://api.bybit.com/v5/announcements/index?locale=en-US&page=1&limit=50
INFO baseline 輪：50 條標 seen、0 告警（flood guard）；malformed=0
INFO round done：items=50 new=50 alerts=0 malformed=0 pruned=0 baseline=True seen_total=50
```

分類分佈（live 50 條）：delistings P0 ×10 / maintenance_updates P0 ×6 / latest_bybit_news P0 ×1 + P1 ×1 / new_crypto P1 ×6 / latest_activities P2 ×25 / 空 type.key P1 ×1。

BB F-4 同件被真捕捉：
```json
{"type_key": "delistings", "severity": "P0", "title": "Delisting of TONUSDT Perpetual Contract",
 "blt_id": "bltd27f1f00e6b0f5ed", "matched_escalators": ["kw:delist"]}
```
（blt UID 與 BB memo 樣本不同 = CMS 同文多 entry，正印證「url 主鍵、blt 輔助」裁決。）

**live 新發現**：存在 `type.key==""` 條目（type.title="Spot"，行銷文「Bybit HotSpot BLEND…」）→ 未知桶寬網歸 P1（符 BB §2 寧誤升不漏降）；已記入字典 §1.11 陷阱 5。輕微噪音面：此類條目會以 P1 告警，operator 若嫌吵可後續加降級規則（不在本 scope）。

## 6. index 待合併行（本棒依契約**未動** `SCRIPT_INDEX.md` 與任何 `memory.md`；由 PM 合併）

`SCRIPT_INDEX.md`「2026-06-10 L2 Mesh P2p incident sentinel」節旁新增同構節（或表內追加 4 行）：

```markdown
## 2026-06-11 Bybit 公告增量哨兵（alert-only）+ watchdog 本地耐久告警 sink

| 腳本 | 用途 |
|------|------|
| `canary/bybit_announcement_sentinel.py` | Bybit 公告增量哨兵（cron 30min，alert-only 絕不自動觸發交易動作）：plain GET `api.bybit.com/v5/announcements/index?locale=en-US&page=1&limit=50`（public 無 auth、不經簽名 client、零 credential 面，每輪恰 1 call）→ seen-set 差集去重（主鍵=正規化 url、輔助 `blt<hex>` UID、fallback sha256(locale\|title\|publishTime)；**禁 timestamp watermark**，排序 inversion 實證）→ BB §2 severity 分級（delistings/maintenance=P0；product_updates tag/keyword escalator 升 P0；P2 不告警仍落 state）→ sibling-import `engine_watchdog._send_alert_best_effort`（subject `[BB-SENTINEL]` 前綴；body=title+url+類別，description 不展開，原文存 state raw 欄供審計）。首輪 baseline 全標 seen 不告警；>90d 修剪；單輪 >10 條彙總；網路失敗 fail-quiet skip exit 0 禁 tight retry，連續 8 輪（≈4h）發一條 sentinel-health meta-alert；watchlist `OPENCLAW_BB_SENTINEL_WATCHLIST` csv runtime 注入。唯一本地寫入=`<data_dir>/bybit_announcements_state.json`。設計 SSOT=BB advisory 2026-06-11。 |
| `canary/test_bybit_announcement_sentinel.py` | 53 測試：去重鍵/watermark 行為證明（更舊未見件仍告警）/分類映射全分支/V5 envelope 衛生/每輪恰 1 call/baseline flood guard/修剪/fail-quiet+meta-alert 恰一條/untrusted body 紀律/emitter 簽名 smoke/零 credential 零 DB 結構斷言。隔離鐵則：0 真 urlopen / 0 真外發 / 全 tmp_path。 |
| `cron/bybit_announcement_sentinel_cron.sh` | 30min cron wrapper（mirror incident_sentinel 形）：mkdir lock + stale-lock >45min 自清 + `cron_heartbeat/bybit_announcement_sentinel.last_fire` + fail-soft exit 0；零 PG secrets 段（plain GET 公開 API）。 |
| `cron/install_bybit_announcement_sentinel_cron.sh` | idempotent installer（mirror install_incident_sentinel 模式）：Linux only / dry-run 預設 / `OPENCLAW_BB_SENTINEL_CRON_APPLY=1` 才寫 crontab（獨立 gate env，防 incident_sentinel 殘留 APPLY 誤裝）/ 偵測既有條目 refuse / `--remove`。Entry：`7,37 * * * *`（避整點）。 |
```

另 `canary/engine_watchdog.py` 既有條目可追加一句：「2026-06-11 WATCHDOG-ALERT-SINK：`_send_alert_best_effort` 在遠端通道前無條件 append `<data_dir>/alerts/alerts.jsonl`（ts_utc/subject/severity/body≤2000/channels_attempted/channels_ok；>5MB 輪轉一代；失敗吞沒不拋）——無 creds 也必達。」

E1 memory.md 待合併行（1 行）：「2026-06-11 線 W：watchdog 告警耐久 sink（alerts.jsonl，遠端通道前無條件落地）+ BB 公告哨兵三件套 shipped（179 測試綠+真實煙測抓到 TONUSDT delisting P0）；教訓=watermark/硬編碼類『負面 grep』測試必剝 COMMENT/STRING 或改行為證明，docstring 解釋文必誤紅。」

## 7. 治理對照

| 項 | 結果 |
|---|---|
| 硬邊界 token（max_retries/live_execution_allowed/execution_authority/system_mode） | 0（grep 證） |
| 硬編碼 user path（/Users//home/ncyu） | 0（grep 證，5 檔全掃；路徑全 env+`$HOME` 推導） |
| BB §10 驗收 #1 不經簽名 client / 零交易副作用 | PASS（結構測試 `test_zero_credential_zero_db_structure` 鎖死） |
| BB §10 #2 url 主鍵+seen-set 差集、無 watermark | PASS（行為證明測試 + code-token 輔證） |
| BB §10 #3 severity 映射 + escalator + watchlist runtime 注入 | PASS（13 分類測試；env csv，無內建默認） |
| BB §10 #4 raw 原文 + first_seen_at 落地 | PASS（state raw 欄；本實作 0 LLM 路徑故無圍欄需求） |
| BB §10 #5 fail-quiet + meta-alert、無 tight retry | PASS（失敗輪恰 1 call 斷言） |
| BB §10 #6 字典 §1.11+§4.1 同批落地 | PASS（本報告 §2） |
| BB §10 #7 timestamp parse-fail reject | N/A-by-design（見 §8 偏差 3） |
| 注釋規範（中文優先） | PASS（新檔全中文 MODULE_NOTE+why 注釋） |
| migration / singleton / SQL | 無（零 PG、零 singleton、零 migration） |
| 既有測試回歸 | 179/179 綠（含 incident_sentinel 簽名接縫、engine_watchdog 40 測） |

## 8. 偏差與小決策（最小安全解，依執行協議註明）

1. **§4.1 表欄序適配**：BB §7 草稿行欄序（name|path|limit|note）與實表欄序（Group|上限|適用路徑|備註）不符 → 按實表欄序填，語意不變。
2. **installer APPLY gate 用獨立 env** `OPENCLAW_BB_SENTINEL_CRON_APPLY`（非復用 `OPENCLAW_SENTINEL_CRON_APPLY`）：防 operator 同 shell 裝 incident_sentinel 後殘留 APPLY=1 連帶誤裝本哨兵。已在 installer 註釋言明。
3. **BB §10 #7（timestamp parse-fail reject）N/A**：該條款屬 BB §4 PG schema sketch（ms→TIMESTAMPTZ parse）；任務契約拍板 state json 零 PG，本實作完全不 parse 公告 timestamp（無 watermark、`first_seen_at` 用本地時鐘、原始 ms 值僅原樣存 raw），epoch 落庫面結構性不存在。
4. **channels_ok 恆 null**（前一棒決策，本棒覆核同意）：發送是 fire-and-forget daemon thread，append 時點無法同步得知送達結果；欄位保留為 schema 前向兼容。
5. **單輪告警上限 MAX_ALERTS_PER_RUN=10 + 彙總 1 條**（前一棒加，advisory 未明指）：哨兵長停擺後復跑的洪水保險，明細全落 state 不丟，符合 advisory 防 spam 精神。
6. **meta-alert 恰在第 8 輪發一次**（episode ≤1 條，成功歸零後重新累積）：避免持續故障每 30min 灌一條 meta。

## 9. 不確定之處

- Mac-only 驗證：cron wrapper/installer 為 `bash -n` + 模式對照（incident_sentinel 同形已在 Linux 跑），未在 Linux 實機裝。installer 平台守門會擋 Mac 執行（by design）。
- 煙測為 baseline 輪（首輪天然 0 告警）；增量告警路徑由 53 測試中 9 條 mock 鏈覆蓋，未對 live 第二輪驗（再打 1 call 無必要）。
- alerts.jsonl 目前無自動消費者（operator tail 查）；P2p Telegram creds 後補後自動雙路 — 與 BB F-9 跨線依賴一致，本任務 ① 正是其本地兜底。

## 10. Operator / PM 下一步

1. E2 對抗審查（本報告 + 7 檔 diff）→ E4 Linux 回歸。
2. 合併 §6 的 SCRIPT_INDEX.md / E1 memory.md 待合併行（PM commit 時）。
3. Linux 部署後啟用序（installer dry-run 輸出已含）：手動 dry-run 一輪（baseline）→ wrapper 手跑一輪 → `OPENCLAW_BB_SENTINEL_CRON_APPLY=1 install_bybit_announcement_sentinel_cron.sh`。
4. BB F-4 知悉項：TONUSDT 永續 2026-06-15 09:00 UTC 下架公告已被哨兵真捕捉（與 06-10 TONUSDT watch 關閉決策鏈一致）。
5. BB F-8 scope 缺口（docs-changelog 哨兵 = phase-2 候選）不在本任務，留 TODO owner 裁量。

E1 IMPLEMENTATION DONE: 待 E2 審查（report path: docs/CCAgentWorkSpace/E1/workspace/reports/2026-06-11--alert_sink_bb_sentinel.md）

---

## 修復輪（E2 RETURN + E3 findings，2026-06-11/12，續作棒完成）

> 修復輪前一棒被月度限額殺死（源碼改動已完成、test_watchdog_alert.py 只寫了 MODULE_NOTE
> 宣告未寫類體）。本棒逐項盤點（git diff + 讀碼 + py_compile/bash -n 完整性檢查）後
> NO-OP 跳過已完成項、補齊半成品。E2 正本：
> `E2/workspace/reports/2026-06-11--sentinel_polymarket_smallitems_review.md`。

### 盤點與完成狀態（W 線 + 共用件）

| 項 | 修復輪前一棒 | 本棒動作 |
|---|---|---|
| E3 MED-1 redactor | 源碼 DONE（`alert_sink.py` 5 規則：DSN userinfo / X-BAPI header / keyword=value / 長 hex≥32 / 長 base64≥40；`redact_and_sink` 接 `_send_alert_best_effort` 雙路徑（creds-fail 分支 + 主路徑）；遠送/INFO log 必用回傳的脫敏文本——rebind 在 thread spawn 前=Telegram/webhook 結構性同享） | NO-OP；補 `TestAlertRedactor` ×6（毒樣本逐規則 / 冪等 / fail-closed 佔位 / sink+遠送雙路無 secret / INFO log subject 已脫敏 / creds-fail 分支） |
| E2-B MED-1 抽模組 | `alert_sink.py`（新模組）DONE，watchdog 只剩薄調用 | 行數 2104→**2100**（≤2100 驗收達標）：import 塊 5→2 行、調用點註釋摺行、W-2 分支 if/else→`logger.log` 三行（級別/措辭逐字不變） |
| W-2 觀測面據實 | 源碼 DONE（`append_alert_sink` 回 bool + 失敗 `logger.warning`；INFO 行據 sink_ok 措辭，失敗=WARNING「alert LOST」） | NO-OP；補 `TestSinkObservability` ×4（bool 雙態 / 失敗 warning / 「recorded」vs「LOST」互斥 / LOST 必 WARNING 級） |
| W-3 控制字符 | 源碼 DONE（哨兵 `_strip_control` C0/C1 全剝→空格；title/url/type_key/escalators 進 subject/body 前必過） | NO-OP；補 `TestFormatAlertSanitization` ×3（換行注入偽 log 行 / escalators+type_key / unicode 保留） |
| E3 LOW 禁 redirect | `urlopen_no_redirect` 正本在 alert_sink.py；哨兵 fetch 默認 opener 已接 | 補 `TestNoRedirectOpener` ×3（**loopback 自架 server**：200 透傳 / 302 拒且 /target 零命中 / 超長 Location message 有界）+ `TestNoRedirectWiring` ×2（default 接線 / 30x 收斂 FetchError）；**新增小修**：redirect-refused message 的 `newurl` 截斷 200（Location 外部可控可達數十 KB，原樣嵌 error 會經 exc log 灌爆 cron log） |
| cron wrapper exc log 截斷自查 | — | 自查結論：哨兵 `retMsg` 已 [:120]、`FetchError`/parse error 嵌的 exc str 皆有界；唯一無界點=redirect handler 的 newurl（已截斷如上）。wrapper 本身只 append python stdout/stderr，無自建無界面 |

### 測試（親跑，Mac venvs/mac_dev py3.12）

- `test_watchdog_alert.py` **41 passed**（=E2 基線 28 + 13 新）；canary 四套合跑（watchdog_alert + engine_watchdog + incident_sentinel + bybit_sentinel）**197 passed 0 failed**（=E2 基線 179 + 13 + 5）。
- `test_bybit_announcement_sentinel.py` **58 passed**（53 + 5 新）。
- 全部 py_compile + 4 cron 檔 bash -n 過（前棒斷點完整性確認：無半寫檔，唯一斷口=test MODULE_NOTE 宣告了未寫的 3 個類，本棒補齊）。

### 治理對照 / 偏差

- **MED-1（2000 行硬頂）**：engine_watchdog.py **pre-existing 2088 行已超 2000 硬頂**（本批觸碰前即超），本批薄調用淨 +12（終 2100）。Follow-up 建議：TODO 補一行 split 計畫（候選切面：state/canary-event IO 層、alert 通道層——alert_sink.py 已開頭、restart/triage 編排層 sibling 化）；本棒按派工契約不動 TODO.md。
- 測試 fail-closed 注入改用替換 `_REDACTION_RULES` 表（`re.Pattern.sub` 是 C 層唯讀不可 mock.patch——RLock `__enter__` 同類教訓）。
- 硬邊界 token 0、硬編碼 user path 0（grep 自證）；未動 SCRIPT_INDEX / memory.md / TODO.md（派工契約）。

### 下一步

narrow re-E2（只審 delta：本節 + 檔 diff）→ E4。S-1（W 線 cron static 測試同型補）按 E2 裁定不擋，留 follow-up。

— E1（修復輪續作棒），2026-06-12。未 commit。
