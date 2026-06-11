# PA DESIGN — L2 Mesh P2p: `incident_sentinel` 本地哨兵（alert-only, never remediate）

Date: 2026-06-10
Author: PA
Risk class: 低-中（standalone read-only cron 腳本；0 app/engine/schema 改動；0 硬邊界觸碰）
Scope: 一次設計到 E1-ready。承 sibling 設計 `2026-06-05--watchdog_alert_wiring_design.md`（該設計已全量落地，見 §1.1）。
Worktree: `/tmp/wt-l2-p2p` branch `feat/l2-p2p-design` @ `13ae589f6`（docs-only，不 commit）。

---

## 0. 問題陳述與動機

兩個已發生的「靜默異常」缺口，P2p 將其制度化為常駐偵測：

1. **2026-06-05 引擎掛 20h 無人知**（bind-host 事故）。watchdog 卡死 → 無自愈、無告警。
   後續 watchdog→alert wiring 已修「watchdog 活著但引擎掛」的告警，但 **watchdog 自己死掉
   /卡住時仍然全系統靜默**（watchdog 是 bare process，`restart_all.sh:758` spawn，無
   `Restart=always`）。`canary_events.jsonl` 至今**無告警消費者**（pre-existing MEDIUM-2）：
   watchdog 寫入的 9 種事件中只有 circuit-broken 族接了 alert，`RESTART_FAILED` /
   `NETWORK_OUTAGE` / `TRADING_INERT_PROLONGED` / `RESTART_SKIPPED` 只落檔無人讀。
2. **2026-06-10 fixture 污染 prod 21 rows 無告警**。`test_l2_p3b_hypothesize` sink 測試漏
   mock DB 連線，在連得上 prod PG 的環境每輪寫 3 條假資料進 `agent.lessons`（7 輪 21
   rows，污染 M4 novelty 語料；RCA 全文在 `control_api_v1/tests/conftest.py:488-517`）。
   危險模式 = 「測試永遠 pass，污染只在特定環境發生」——**事後靠人眼發現**。conftest
   guard v2 堵了測試端，但 prod 表的「異常寫入率」缺第二道偵測防線。

P2p = 獨立第二觀察者：**只告警，永不修復**（never remediate）。與 watchdog 的職責分界：
watchdog = 偵測 + 自愈 + 對「自愈放棄」告警；sentinel = 不依賴 watchdog 存活的旁路觀察
者，覆蓋 watchdog 的盲區（watchdog 自身死亡）與 watchdog 不看的面（DB 異常率、API、
migration drift）。

---

## 1. 既有基建盤點（全 ground，file:line）

### 1.1 告警發送（reuse 目標）— 06-05 設計已全量落地

`helper_scripts/canary/engine_watchdog.py`（commit `92cdcc41` GUI-configurable alerting）：

| 構件 | 位置 | 性質 |
|---|---|---|
| `_load_alert_creds(data_dir)` | :607 | file-primary `<data_dir>/alert_config.json`（與 app `alert_config.py` :35/:58 共用 schema，GUI 可配）+ env-fallback（`OPENCLAW_TELEGRAM_BOT_TOKEN/CHAT_ID`、`OPENCLAW_WEBHOOK_URLS/SECRET`，:641-660） |
| `_post_telegram_alert` / `_post_webhook_alert` | :664 / :676 | stdlib urllib、5s timeout（`ALERT_HTTP_TIMEOUT_SECONDS` :107）、catch-all 永不拋 |
| `_send_alert_best_effort(subject, body, severity, data_dir)` | :698 | daemon-thread fire-and-forget；通道未配置 = 一次性 warn 後靜默 no-op |
| `emit_engine_down_alert_if_new` | :746 | key-dedup，marker 持久化於 `watchdog_state.json` —— **sentinel 不可共用**（見 §5.2） |

**import 慣例先例**：`test_watchdog_alert.py:26-40` 以
`sys.path.insert(0, dirname(__file__))` + `import engine_watchdog` 直接 sibling-import，
已證 module-level import 無副作用（103KB 檔，`main()` 在 `__main__` guard 內）。

### 1.2 watchdog canary 事件 × alert 接線現狀（A2 軸的事件分類依據）

| 事件 | 寫入點 | 已接 alert? |
|---|---|---|
| `RESTART_CIRCUIT_BROKEN` | :1054 | ✅（`circuit_broken` key :1078） |
| `INERT_CIRCUIT_BROKEN` | :870 | ✅（:875） |
| prolonged-down re-alert | :1206 | ✅ |
| `ENGINE_RECOVERED` | :1275-1283 | ✅（直呼 `_send_alert_best_effort`） |
| `ENGINE_DOWN_ALERT_SENT` | :774 | n/a（本身是「已發 alert」的審計事件） |
| `RESTART_FAILED` | :1065 | ❌ 只寫 jsonl |
| `RESTART_SKIPPED` | :568 | ❌ 只寫 jsonl（有 reason_key dedup） |
| `NETWORK_OUTAGE` | :1154 | ❌ 只寫 jsonl |
| `TRADING_INERT_PROLONGED` | :1647 | ❌ 只寫 jsonl |
| `RESTART_SUCCESS` / `TRADING_INERT_CLEARED` | :1030 / :1680 | n/a（正向事件） |

### 1.3 各監測軸的證據源

- **engine 心跳**：`<data_dir>/pipeline_snapshot{,_paper,_demo,_live}.json` mtime（watchdog
  主循環同源，:1860-1864，任一 fresh = alive）。watchdog `STALE_THRESHOLD_SECONDS=45.0`
  （:57）。`data_dir` 默認 `OPENCLAW_DATA_DIR` else `/tmp/openclaw`（:2015）。
- **api healthz**：`GET {api_prefix}/healthz` = `/api/v1/healthz`，**無 auth 輕量 liveness
  probe，註明監控用**（`system_legacy_routes.py:20,303-304,326-329`）。uvicorn port 8000
  （`restart_all.sh:791`）。
- **L2 ledger**：`learning.l2_gate_seam_log`（V135）`verdict CHECK IN
  ('pass','clamp','reject')`（V135:94），hypertable 7d chunks，PK `(seam_id, ts)`。現 prod
  恰 1 row（deployed-E2E-0 的 admission/reject）→ baseline ≈ 0。
- **agent.lessons**（V133:80-95）：欄 `created_at/symbol/lesson_type/content/.../source
  DEFAULT 'l2_session'`。**合法 source 全集（exhaustive caller grep）**：
  `'l2_session'`（layer2_critic 走 column DEFAULT，:483）、`'ml_advisory'`
  （`l2_ml_advisory_executor.py:443` `_SINK_SOURCE`，INSERT :501）、`'dead_mode_seed'`
  （`helper_scripts/m4/seed_dead_mode_lessons.py`）。
  **關鍵：06-10 污染 rows 的 source='ml_advisory' 是合法值** —— 純 source 白名單抓不到
  該事故，**必須配 rate 軸**（§3 A5 雙層設計的依據）。
- **migrations**：repo max = `V136__l2_provenance_columns.sql`；prod applied max=136
  （L2_TODO §2 deploy 記錄）。`_sqlx_migrations` 有 `version/success/checksum` 欄（sqlx 標準）。

### 1.4 cron 慣例（sibling 範本）

- 1min cron wrapper 先例：`helper_scripts/cron/halt_audit_pg_writer_cron.sh`（secrets env
  從 `$OPENCLAW_SECRETS_ROOT/environment_files/basic_system_services.env`、mkdir lock 防
  overrun）。
- heartbeat sentinel 慣例：`${OPENCLAW_DATA_DIR}/cron_heartbeat/<name>.last_fire`
  （`trading_ai_pg_dump_cron.sh` 等）。
- idempotent installer 慣例：`install_pg_dump_cron.sh` / `install_m11_replay_runner_cron.sh`
  （Linux only、`--dry-run` 預設、`OPENCLAW_*_CRON_APPLY=1` 才寫 crontab、偵測既有條目）。
- 已占用時段：02:30 / 03:00 / 03:17 / 04:00 / 04:41 / 06:00 / 08:00 / 09:00 / 6h
  passive_wait / 1min halt_audit —— `*/5` 分鐘級與 daily jobs 無互斥（sentinel 輕 + lock 自護）。
- exit code 慣例（`canary/healthchecks/_common.py`）：0=PASS、1=FAIL、2=CONNECT_ERROR。

### 1.5 與既有巡檢框架的分界（為什麼不併入 passive_wait_healthcheck）

`helper_scripts/db/passive_wait_healthcheck/`（33 個 checks_* 模組，6h cron，exit
code + log）**沒有任何 alert 通道**。不併入的三個理由：

1. **粒度**：6h 對 engine-down / 污染偵測都太粗（20h 事故在 6h 粒度下最壞 6h 才見，且
   FAIL 只落 log = 同款「無消費者」問題）。
2. **噪音**：33-check 全量接 alert = 告警災難；sentinel 刻意只挑 6 條高信號軸。
3. **依賴方向**：passive_wait 依賴 venv+psycopg2+PG up；sentinel 恰要在「PG down / api
   down」時也能告警 → file/HTTP 軸必須零 DB 依賴、per-axis 隔離。

sentinel 與 passive_wait 互補不重疊；passive_wait 不動。

---

## 2. 定位與檔案歸屬（任務範圍 #4）

- **P2p 不進 L2 capability registry**——確認。它不是 advisory capability（無 LLM、無
  orchestrator、無 contract/guard/admission），是 ops 哨兵。`l2_capability_registry.toml`
  /`LANE_DIRECTION`/tier gate 一概不涉。它與 L2 的全部關係 = **唯讀監測** L2 的兩張
  ledger 表（A4/A5 軸）。L2_TODO §3 P2p 行「獨立可隨任何 phase ship」與此一致。
- **檔案歸屬 `helper_scripts/canary/`**（非 program_code）：
  - canary/ 是系統健康域既有正位（watchdog、healthchecks、test_canary 全在此）；
  - sibling-import `engine_watchdog._send_alert_best_effort` 需要同目錄（§4 reuse 定案）；
  - program_code 是 runtime app/engine 域，哨兵不進 app import chain（06-05 設計 PART B
    option (a) 的 REJECT 理由反向同樣成立：app 也不得依賴哨兵）。
- **Rust-first 規則判定**：不適用。哨兵是 ops glue（stat + curl + SELECT count + urllib
  send），與 watchdog / healthchecks / cron wrappers 同類，Python-in-helper_scripts 是該
  域既有慣例；非「新獨立交易/風控/config 模組」。與 06-05 watchdog alert wiring 同判例。
- **AgentTool 分類**：不適用——sentinel 非 AgentTool（不進 agent runtime / MessageBus），
  是 crond 驅動的獨立腳本。

新檔案（4 + 1 索引更新）：

```
helper_scripts/canary/incident_sentinel.py          # 主件（stdlib-first；psycopg2 僅 DB 軸延遲 import）
helper_scripts/canary/test_incident_sentinel.py     # 單元測試（隔離鐵則見 §8.2）
helper_scripts/cron/incident_sentinel_cron.sh       # 5min cron wrapper（mirror halt_audit 模式）
helper_scripts/cron/install_incident_sentinel_cron.sh  # idempotent installer（mirror install_pg_dump 模式）
helper_scripts/SCRIPT_INDEX.md                      # 慣例強制更新
```

---

## 3. 監測軸清單（任務範圍 #1）——最小有用集 6 軸

全部閾值為默認值、env-overridable（`OPENCLAW_SENTINEL_*`）。severity 僅兩級
（CRITICAL / WARN），對齊 `_send_alert_best_effort` 的自由字串 severity。

| # | 軸 | 證據來源（唯讀） | 觸發條件（默認） | severity | 為什麼是這個閾值 |
|---|---|---|---|---|---|
| A1 | engine 心跳 | stat 4 個 `pipeline_snapshot*.json` mtime（watchdog 同源清單 :1860-1864；獨立 stat 不經 watchdog） | 全部 stale 或缺檔，age > **900s** | CRITICAL | watchdog 閾值 45s、自愈循環+circuit-break 通常 <10min；15min 仍 stale = watchdog 自愈失敗**或 watchdog 已死**（20h 事故形狀）。sentinel 是後盾不是替身，必須晚於 watchdog 反應 |
| A1b | watchdog 活性（次軸） | `pgrep -f engine_watchdog.py`（Linux/Mac 皆有） | 無進程 **且** A1 未觸發 | WARN | engine 仍 fresh 但 watchdog 死 = 自愈失能降級（尚非事故）；A1 已觸發時 A1b 不另發（資訊併入 A1 payload） |
| A2 | canary 事件消費（MEDIUM-2 收口） | tail `canary_events.jsonl` 自上輪 cursor（ts 游標存 state，rotate-safe，rotate 在 `fresh_start.sh:279`） | 新增事件 ∈ {`RESTART_FAILED`, `NETWORK_OUTAGE`, `TRADING_INERT_PROLONGED`, `RESTART_SKIPPED`} ≥1 | WARN | **排除集** = watchdog 已自行 alert 的 {`RESTART_CIRCUIT_BROKEN`, `INERT_CIRCUIT_BROKEN`, `ENGINE_DOWN_ALERT_SENT`, prolonged-down} 與正向事件 {`RESTART_SUCCESS`, `TRADING_INERT_CLEARED`}（§1.2 表）——不重複告警。多事件聚合為一條（計數摘要） |
| A3 | api healthz | `GET http://127.0.0.1:8000/api/v1/healthz`（base env-overridable `OPENCLAW_SENTINEL_API_BASE`），timeout 5s，stdlib urllib | 非 200 / timeout / connection refused | CRITICAL | 無 auth 監控端點（`system_legacy_routes.py:326`），本就為此設計。GUI/console 同 host 同進程，api down = operator 全盲 |
| A4 | L2 gate-seam reject 暴增 | `SELECT count(*) FROM learning.l2_gate_seam_log WHERE verdict='reject' AND ts > now() - interval '1 hour'` | count > **10** | WARN | baseline ≈ 0（全 capability disabled；operator 手動 dispatch 一天數條是預期）。>10/h = 有 caller 在 loop dispatch 或 gate 異常翻 reject，絕對閾值即可、無需 baseline 學習 |
| A5 | agent.lessons 異常寫入（污染偵測制度化） | (a) rate：`count(*) WHERE created_at > now() - interval '1 hour'`；(b) 白名單：`count(*) WHERE source NOT IN ('l2_session','ml_advisory','dead_mode_seed') AND created_at > now() - interval '24 hours'` | (a) > **6**/h；(b) ≥ **1** | WARN | **雙層必要性**：06-10 污染 rows source='ml_advisory' 合法（§1.3）→ 白名單抓不到，rate 抓量（7 輪×3=21 rows 遠超 6/h）；白名單抓未來新出現的越權 namespace。白名單以 TOML/常數維護，新增合法 writer 時同步 |
| A6 | `_sqlx_migrations` drift | (a) `SELECT max(...), bool_and(success) FROM _sqlx_migrations`；(b) repo max：解析 `<BASE_DIR>/sql/migrations/V*.sql` 最大編號（BASE_DIR 由 wrapper 注入，不硬編碼） | DB max ≠ repo max，或任一 `success=false` | WARN | 部署完整性軸（05-02 sqlx hash drift 事故域）：DB<repo = 部署漏 apply；DB>repo = worktree stale 或手動 apply；success=false = apply 中斷。非即時事故故 WARN |

**DB 依賴失敗語意（A4/A5/A6 共通）**：psycopg2 import 失敗或連線失敗 → 三軸標
`db_unreachable`，**自身作為一條 WARN alert**（PG down 也是 incident），與各軸 alert 分
key；file/HTTP 軸（A1/A1b/A2/A3）照常完成。**per-axis try/except 隔離：單軸異常絕不毀
整輪**。

**刻意不納入**（最小集紀律）：l2_calls 成本暴增（budget gate + cost_tracker 已是 runtime
防線，DOC-08 cap $2/day）、引擎業務停滯細分類（watchdog inert-probe Layer B 已有）、PG
磁碟/dump freshness（healthcheck [80] 已 cover）。未來加軸走 §10 演進路徑。

---

## 4. 通知路徑（任務範圍 #2）

### 4.1 reuse 評估結論：sibling-import watchdog 的零依賴 emitter

| 選項 | 評估 |
|---|---|
| (a) import app 的 `telegram_alerter/webhook_alerter/alert_router`（`program_code/.../app/`） | **REJECT**——拉 FastAPI app import chain 進 ops 腳本（06-05 設計同判例）；且 alert_router singleton 構造在 `paper_trading_wiring.py`，依賴 app 進程語境 |
| (b) POST 給 control-API 端點轉發 | **REJECT**——A3 軸本身在監測 api down；告警不得依賴被監測對象（06-05 option (b) 同款 fatal flaw） |
| (c) **sibling-import `engine_watchdog._send_alert_best_effort`** | **RECOMMEND**——同目錄 `sys.path.insert` + `import engine_watchdog` 是 `test_watchdog_alert.py:26-40` 既有慣例；函數無狀態純發送；creds 走 file-first `alert_config.json`（GUI 可配）+ env fallback，與 watchdog/app 三方單一 schema；0 行 watchdog 改動 |
| (d) 第三份 urllib send 拷貝 | **REJECT**——已有兩份（app alerters、watchdog emitter），第三份 = 3-way drift |
| (e) 現在抽共用 `alert_emit.py` 模組 | **DEFER**——要動 watchdog（剛經多輪修復穩定的高價值件，徒增回歸面）。06-05 設計已預告「DRY refactor 是 SEPARATE optional task」；若未來出現第三個消費者再抽（follow-up 註記，非本件） |

(c) 的耦合風險與守護：watchdog 未來改 `_send_alert_best_effort` 簽名會破 sentinel →
test_incident_sentinel 含**簽名 smoke**（import + callable + 4-arg 調用於 monkeypatch
urllib 下），任何簽名漂移在測試層 fail-loud。E1 同時在 watchdog 該函數 docstring 加一行
消費者註記（1 行註釋，非邏輯改動，唯一允許觸碰 watchdog 之處）。

### 4.2 alert-only 鐵則（never remediate）——與 watchdog 自愈職責分界

結構性保證（E2 可 grep 驗證）：

1. **0 修復動作**：全檔無 `subprocess` restart/kill/signal、無 `restart_all`、無
   systemctl、無任何進程操作（A1b 的 `pgrep` 唯讀例外，只 list 不 signal）。
2. **0 權威面寫入**：DB 連線設 read-only session
   （`options='-c default_transaction_read_only=on'`），SQL 全 SELECT；不寫 app/engine
   任何 config/state/auth 檔。
3. **唯二本地寫入**：`<data_dir>/incident_sentinel_state.json`（dedup state）+
   `<data_dir>/incident_sentinel_events.jsonl`（自身審計，append-only）。**不寫
   `canary_events.jsonl`**（避免與 watchdog 併發 append 交織）、**不寫
   `watchdog_state.json`**（watchdog 進程獨占）。
4. 告警失敗不重試不升級（fire-and-forget 繼承自 `_send_alert_best_effort`）；通道未配置
   = 靜默 no-op，本地審計照寫（原則 14：零外部服務可運行）。

---

## 5. 形態與降噪（任務範圍 #3）

### 5.1 cron（定案）vs daemon

**cron 每 5 分鐘**（`*/5 * * * *`）。理由：

- daemon 重現「who watches the watcher」遞迴（watchdog 是 bare process 正是 20h 事故的
  深因之一）；cron 由 crond 保證調度，crond 是系統件，遞迴終結。
- 5min 偵測窗對標的事故等級（20h / 數小時污染）綽綽有餘；比 halt_audit 的 1min 省 12 倍
  DB 查詢，比 passive_wait 的 6h 細 72 倍。
- crash 自癒：本輪炸 → 下輪乾淨重跑（state json 損壞 = 當新 run，最壞多發一條 alert）。
- 對齊 `helper_scripts/cron/` 全套慣例（§1.4）：mkdir lock 防 overrun、heartbeat sentinel
  `cron_heartbeat/incident_sentinel.last_fire`、wrapper fail-soft exit 0 避 cron mail spam
  （.py 自身 exit 0/1/2 對齊 `_common.py`，供手動跑判讀）。

### 5.2 dedup / 降噪（同 alert 不重發窗口）

Mirror `emit_engine_down_alert_if_new` 的 key-dedup 語義（:746-776，repo 已驗證模式），但
**state 檔獨立**（`incident_sentinel_state.json`；watchdog_state.json 由 watchdog 進程高頻
讀寫，跨進程共用 = race）：

- 每軸維護 stable `alert_key`：`{axis_id}:{狀態指紋}`（如 `a1:engine_stale`、
  `a5:rate_exceeded`、`a6:db135_repo136`）。key 與上輪相同 → 不重發。
- **re-alert 窗口**：同 key 持續異常，每 `RE_ALERT_INTERVAL`（默認 4h，對齊 watchdog
  prolonged-down 慣例）在 key 尾附窗口序號重發一次（neither spam nor miss）。
- **恢復清 key**：軸轉 OK → 清該軸 key；CRITICAL 軸（A1/A3）恢復時發一條 INFO
  RECOVERED（mirror `ENGINE_RECOVERED` :1275 慣例），WARN 軸靜默清除。
- A2 游標：state 存 `canary_cursor_ts`（上輪處理的最大事件 ts）。用 ts 而非 byte offset
  → rotate（`fresh_start.sh:279`）後新檔事件 ts 必然更新，游標天然安全；首跑游標 = now
  - 1h（不回放陳年事件）。
- 全軸異常風暴上限：6 軸 × 每 4h 1 條 = 最壞 6 條/4h，結構性封頂。

### 5.3 調用流程（單輪）

```
cron(*/5) → incident_sentinel_cron.sh
  ├─ mkdir lock（已存在 → exit 0 skip）
  ├─ source secrets env（basic_system_services.env；mirror halt_audit:cron 模式）
  ├─ touch cron_heartbeat/incident_sentinel.last_fire
  └─ <venv python> incident_sentinel.py --data-dir $OPENCLAW_DATA_DIR --base-dir $BASE_DIR
       ├─ load incident_sentinel_state.json
       ├─ A1/A1b/A2: 純檔案 stat / tail / pgrep（零網路零 DB）
       ├─ A3: urllib GET healthz（5s timeout）
       ├─ A4/A5/A6: psycopg2 read-only SELECT（延遲 import；失敗→db_unreachable WARN）
       ├─ per-axis verdict → dedup（key 比對 + re-alert 窗）
       ├─ 對新 key：engine_watchdog._send_alert_best_effort(subject, body, severity, data_dir)
       ├─ append incident_sentinel_events.jsonl（每輪 verdict 摘要，含未告警軸）
       └─ save state；exit 0(all-pass)/1(任一 FAIL)/2(connect error)
```

payload 格式沿 watchdog B.5 慣例：`[SEVERITY] OpenClaw sentinel: <axis> — <一行事實>`
+ 證據（數值/路徑/時戳）+ `action: ssh trade-core; <對應排查指引>`。**絕不在 payload
放 creds / DSN / token**。

---

## 6. 接口設計（`incident_sentinel.py` 內部結構，~400 行）

```python
# 常數區：閾值默認 + env override 名 + 事件分類集（ALERTED_BY_WATCHDOG / POSITIVE / ALERTABLE）
AXIS_DEFAULTS = {...}                      # 全部 OPENCLAW_SENTINEL_* overridable
LESSONS_SOURCE_WHITELIST = ("l2_session", "ml_advisory", "dead_mode_seed")

@dataclass
class AxisResult:           # 每軸統一輸出
    axis: str               # "a1_engine" ... "a6_migrations"
    ok: bool
    alert_key: str | None   # None = 無告警需求
    severity: str           # "CRITICAL" / "WARN"
    subject: str
    body: str
    evidence: dict          # 落審計 jsonl

# 純函數軸（檔案系統注入 path、時鐘注入 now、DB 注入 conn-factory → 全部可測零真依賴）
def check_engine_heartbeat(data_dir, now, threshold) -> AxisResult
def check_watchdog_alive(engine_ok) -> AxisResult           # pgrep 包裝，可注入 runner
def check_canary_events(data_dir, cursor_ts, now) -> tuple[AxisResult, float]  # 回新 cursor
def check_api_healthz(base_url, opener) -> AxisResult       # opener 注入（測試 fake）
def check_l2_seam_rejects(conn, now) -> AxisResult
def check_lessons_anomaly(conn, now) -> AxisResult
def check_migrations_drift(conn, repo_migrations_dir) -> AxisResult

# 編排層
def load_state(data_dir) / save_state(data_dir, state)       # 獨立 state 檔
def should_emit(state, result, now, re_alert_interval) -> bool   # key-dedup + 窗口
def run_once(data_dir, base_dir, dsn_resolver, alert_fn, now) -> int  # exit code
# alert_fn 默認 = engine_watchdog._send_alert_best_effort（sys.path sibling import）
# dsn_resolver：OPENCLAW_DATABASE_URL 優先，否則 POSTGRES_* 拼裝（host 默認 127.0.0.1，
#   口徑對齊 lib/pg_connect.py 注釋；不 import 它——其 MODULE_NOTE 明文「只服務 offline
#   report scripts」，sentinel 是 runtime cron，自帶 ~10 行等價解析）
# CLI: --data-dir / --base-dir / --once(默認) / --dry-run(全軸跑但不發送、印 verdict)
#      / --probe-alert(發一條 INFO probe 驗通道，§8.3 演練用)
```

跨平台：所有路徑由參數/env 注入，0 硬編碼 home；pgrep 在 darwin/linux 通用；Mac dev 可
`--data-dir /tmp/x --dry-run` 全鏈跑（Mac engine not_running = 天然 A1 stale 樣本）。

---

## 7. 副作用清單（PA checklist 逐項）

1. **誰 import 被改檔？** 新檔無人 import；唯一觸碰既有檔 = watchdog docstring 1 行註釋
   （無邏輯）+ SCRIPT_INDEX.md。app / engine / migrations / TOML 全零改動。
2. **mock 脆弱面**：sentinel 對 `engine_watchdog._send_alert_best_effort` 的 import 是新
   耦合——簽名 smoke 測試守護（§4.1）。反向：watchdog 的既有測試不受影響（watchdog 零
   邏輯改動）。
3. **asyncio/threading 邊界**：sentinel 是同步 CLI；告警線程 = `_send_alert_best_effort`
   內部 daemon thread（既有語義）。進程壽命 < thread 完成時 alert 可能丟失——cron 場景
   下 main 結束前 `time.sleep(ALERT_DRAIN_SECONDS=6)`（> 5s timeout）兜底排空；可注入
   sleep 供測試。E1 注意此點（watchdog 是長駐進程沒這問題，sentinel 是短命進程**有**）。
4. **API schema**：零改動（只 GET 既有無 auth 端點）。
5. **Rust↔Python IPC**：零觸碰。
6. **DB 負載**：3 條 count 查詢/5min，read-only session，hypertable 近窗 chunk 輕查詢；
   statement_timeout 設 10s 防掛。
7. **告警通道**：dedup 封頂 6 條/4h（§5.2）；通道未配置 = 靜默（runtime 現狀待 operator
   確認，§11 OQ-1）。
8. **canary_events.jsonl**：只讀 + ts 游標；rotate 安全；不寫入。
9. **測試覆蓋範圍邊界**：helper_scripts/canary/ 不在 control_api_v1/tests conftest guard
   v2 的進程級封鎖範圍內 → 隔離鐵則必須自帶（§8.2，E2 第一審查點）。

---

## 8. E1 派發計劃 + 測試隔離鐵則 + 驗收標準（任務範圍 #5）

### 8.1 E1 拆分：單一 E1（不拆並行）

輕量件、檔案間強內聚（test 隨 main、wrapper 隨 installer），拆兩個 E1 的協調成本 >
並行收益。單 E1 串行四件套，估 0.5-1 天：

| task | 檔案 | 內容 |
|---|---|---|
| T1 | `canary/incident_sentinel.py` | §6 全部；軸函數純函數化（依賴注入）；~400 行 |
| T2 | `cron/incident_sentinel_cron.sh` + `cron/install_incident_sentinel_cron.sh` | mirror halt_audit wrapper + install_pg_dump installer；~140 行 |
| T3 | `canary/test_incident_sentinel.py` | §8.2 鐵則 + §8.4 案例；~350 行 |
| T4 | `SCRIPT_INDEX.md` 更新 + watchdog docstring 1 行消費者註記 | 慣例收尾 |

依賴序 T1→T3（T2/T4 隨時）。NO-OP exit 條款：若發現 main 已有
`incident_sentinel.py`（sibling session 撞單），停手回報。

### 8.2 測試隔離鐵則（conftest guard v2 教訓的本目錄等價物）

helper_scripts/canary/ **無 conftest 進程級封鎖庇護**，必須在設計層做到「測試結構性無法
觸 prod」：

1. **連線層隔離**：所有 DB 軸吃注入 `conn`（FakeConn/FakeCursor）；`run_once` 的
   `dsn_resolver` 可注入恆 None；**測試檔 0 個真 DSN、0 次 psycopg2.connect**。模組層
   psycopg2 延遲 import（無 DB 軸調用即不 import）。
2. **網路層隔離**：A3 吃注入 opener；alert 路徑測試一律 monkeypatch
   `urllib.request.urlopen`（`test_watchdog_alert.py` 既有同款手法）；**測試 0 真外發**。
3. **默認無害 CLI**：`--dry-run` 跑全軸不發送；DSN 不隱式從測試環境吸入（顯式參數才連，
   承 m4 seeder「默認 --dry-run 零連線」原則）。
4. **檔案系統**：全部 tmp_path fixture；不觸真 `OPENCLAW_DATA_DIR`。

（mock 不掩蓋邏輯的對偶：業務邏輯全在純函數軸內被真測，只有連線/外發層被隔離。）

### 8.3 一次真 alert 演練的安全做法（驗收必含）

**禁止製造真事故**（不停 engine、不殺 api——違原則 5）。三段式：

1. **通道演練**（Linux，operator-gated）：`incident_sentinel.py --probe-alert` 發一條
   `[INFO] incident_sentinel probe — channel verification` 到已配置通道；通道未配置則驗
   證「一次性 warn + 靜默 + 本地審計仍寫」分支。零事故注入。
2. **軸演練（合成證據）**：Linux 上 `--data-dir /tmp/sentinel_drill --dry-run`——空目錄
   = A1 全 stale + A2 缺檔 + （指向假 port 的 `OPENCLAW_SENTINEL_API_BASE`）A3 down，驗
   三軸 verdict 與 dedup state 寫入；不碰真 data_dir、不發送。
3. **真 prod 首跑**：installer apply 後觀察兩輪（10min）：heartbeat sentinel mtime 前進、
   `incident_sentinel_events.jsonl` 兩條 all-pass 記錄、零 alert 發出（系統健康時的
   no-op 證明）。

### 8.4 驗收標準（E4 測試清單）

1. 六軸各自的 fault-injection 單測：stale/缺 snapshot、pgrep 空、canary 注入 4 種
   alertable 事件（+ 排除集事件不觸發）、healthz 非 200/timeout、seam reject 11 筆、
   lessons 7/h + 白名單外 source、DB max≠repo max、success=false。
2. dedup：同狀態兩輪恰 1 alert；恢復清 key 後再壞→重發；4h 窗口 key 演進恰 1 條/窗；
   CRITICAL 恢復發 INFO、WARN 恢復靜默。
3. per-axis 隔離：注入單軸 raise → 其餘軸照常完成 + exit code 反映。
4. DB unreachable：conn factory 回 None → A4/A5/A6 聚合一條 `db_unreachable` WARN，
   file/HTTP 軸不受影響。
5. canary 游標：rotate 模擬（換 inode 新檔）後不重複消費、不漏新事件；首跑不回放 >1h
   舊事件。
6. never-remediate 結構斷言：源檔 grep 0 `subprocess.*(kill|restart|systemctl)`、0
   INSERT/UPDATE/DELETE 字串（自身 jsonl append 除外）；DB session read-only 參數存在。
7. 簽名 smoke：`engine_watchdog._send_alert_best_effort` import + 4-arg 調用於
   monkeypatch 下成功。
8. 短命進程 alert 排空：monkeypatch 慢 send → main 結束前 drain 等待生效。
9. Mac 全綠零連線零外發；Linux parity（E4 標準雙平台）。

---

## 9. 降級 / rollback 路徑（設計完成必要件）

- **部署面**：crontab 1 行 + 4 個新檔。rollback = installer `--remove`（或
  `crontab -l | grep -v incident_sentinel | crontab -`）→ 系統回到 P2p 前狀態，**零殘留**
  （state/audit 檔為 inert 資料，可留可刪）。無 DB schema、無 app 重啟、無 engine 觸碰
  → blast radius = cron 行本身。
- **sentinel 自身故障**：crash → 下輪 cron 乾淨重跑；state 損壞 → 重置 dedup（最壞重發
  一條）；hang → mkdir lock 防 overrun，下輪 skip + lock 過期清理（wrapper 內 mtime
  >15min 的 stale lock 自清，mirror 既有 lock dir 慣例）。
- **誤報風暴**：單軸閾值 env-override 即時調高；極端情況移除 cron 行全停。dedup 結構性
  封頂 6 條/4h 已限幅。
- **告警通道故障**：fire-and-forget + 本地審計 jsonl 仍完整（事後可查）；不影響任何
  runtime 進程（原則 14 + watchdog 同款不變式）。

---

## 10. 演進路徑（不在本件 scope，僅錨點）

- 第三個 alert 消費者出現時：抽 `canary/alert_emit.py` 零依賴共用模組（06-05 設計預告的
  SEPARATE task）。
- 軸擴充：AxisResult 統一接口下加軸 = 加一個純函數 + 一行註冊；閾值進
  TOML（`watchdog_inert_probe.toml` 同款慣例）若軸數 >8。
- systemd timer 遷移：若 operator 決定把 watchdog 遷 systemd（06-05 OQ-2 仍開放），
  sentinel cron 可同批遷 systemd timer——非前置條件。

---

## 11. 開放問題（operator；均不阻塞 E1）

1. **OQ-1 告警通道配置現狀**：06-05 時 4 個 cred keys ABSENT；現已有 GUI 配置面
   （`alert_config.json`）。sentinel 不依賴配置存在（未配置=靜默+本地審計），但**演練
   §8.3-1 需要至少一個通道**才有端到端證明。請 operator 確認/補配。
2. **OQ-2 默認值認可**：A1=900s、re-alert=4h、cron=5min、A5 rate=6/h、A4=10/h——全部
   env-overridable，默認值如上（PA 自決，理由見 §3 表）。
3. **OQ-3 A2 事件集中 `RESTART_SKIPPED`**：包含（自愈被擋是 20h 事故家族的早期信號）；
   若 operator 認為日常 skip 噪音高（如 frequent manual stop），可 env 移出事件集。

---

## 12. 16 根原則 / 硬邊界合規（checklist 觸發要求）

- **硬邊界指紋掃描**：設計零觸碰 `execution_state / execution_authority /
  live_execution_allowed / decision_lease_emitted / max_retries /
  OPENCLAW_ALLOW_MAINNET / live_reserved / authorization.json`——sentinel 不讀不寫任何
  授權/執行面；E2 對 E1 diff 跑同款 grep 應為 0 hits。
- 原則 1/3/4（寫入口/Lease/風控）：不適用且不觸碰——0 訂單面、0 lease 面。
- 原則 2（讀寫分離）：✅ 全讀；唯二寫 = 自身 state/audit（§4.2）。
- 原則 5/6（生存>利潤/失敗收縮）：✅ alert-only；任何軸失敗 = skip + 下輪重試，不升級
  為動作。
- 原則 8（可解釋）：✅ 每輪 verdict 落審計 jsonl，alert 與證據一一對應。
- 原則 9（雙重防線）：✅ sentinel = watchdog 之外的獨立本地第二觀察者。
- 原則 14（零外部成本可運行）：✅ 通道未配置仍完整運行；0 付費依賴。
- DOC-08 §12 安全不變量：全部不涉（無交易效果面）。
- AgentTool 訪問權限分類：不適用（非 AgentTool，crond 驅動 ops 腳本，§2）。

---

## 13. E2 重點審查 3 點

1. **測試隔離鐵則無漏**（直接對位 06-10 污染事故）：helper_scripts/canary 無 conftest
   guard 庇護——逐測試確認 0 真 DSN / 0 psycopg2.connect / 0 真 urlopen；主碼 DB
   session read-only 參數真實生效（非註釋承諾）。
2. **never-remediate 結構性成立**：全檔 grep 0 進程操作 / 0 DB 寫 / 0 config 寫；A1b
   pgrep 唯讀；alert 失敗無重試無升級路徑。
3. **dedup 與短命進程語義**：state 檔與 watchdog_state.json 嚴格分離（防跨進程 race）；
   canary ts-游標 rotate-safe；daemon-thread alert 在 main 退出前 drain（§7-3 是
   sentinel 與 watchdog 場景的真差異點，最易被照抄漏掉）。

---

PA DESIGN DONE: report path: docs/CCAgentWorkSpace/PA/workspace/reports/2026-06-10--l2-p2p-incident-sentinel-design.md
