# 2026-07-15 watchdog audit「no DSN buildable」RCA + 引擎死因 + runtime apply runbook

**Ticket**: WATCHDOG-AUDIT-DSN-1 | **PM chain**: PM → OPS(只讀取證)→ E1 → E2 → E3 →(E4)→ PM
**基底**: Mac main `834f6fe31`;Linux runtime checkout `0770bd138`(PR#15,乾淨);runtime 取證時刻 2026-07-15 ~16:52 CEST
**時區注意**: trade-core 本地=CEST(UTC+2);`watchdog.log`/journal 為本地時間,`engine.log`/`boot_history.jsonl` 為 UTC。

---

## 一、Operator 四問四答(TL;DR)

| # | 問 | 答 |
|---|---|---|
| 1 | DSN 組裝邏輯缺什麼 | `resolve_dsn()` 三顯式源(`OPENCLAW_DATABASE_URL_FILE`→`OPENCLAW_DATABASE_URL`→`POSTGRES_*`)在 watchdog 進程 env **全數缺席**。runtime 的 watchdog 是手管 user unit(`~/.config/systemd/user/openclaw-watchdog.service`,mtime 07-04),無任何 `EnvironmentFile=`、無 PG 變數;repo 模板(system unit)雖有 `EnvironmentFile=basic_system_services.env` 但 runtime 沒用模板,且模板本身也漏 `OPENCLAW_DATABASE_URL_FILE` 行(engine unit :62 有)。**chronic 自 2026-06-20 unit 上線首日**(watchdog.log 第 67 行即首發),非 07-15 新斷。 |
| 2 | 正確寫入路徑 | 已 source-landed(本 PR):①unit 模板補 `OPENCLAW_DATABASE_URL_FILE=__OPENCLAW_DATA_DIR__/runtime_secrets/openclaw_database_url`(對齊 engine unit);②`resolve_dsn()` 加第 4 步最後備援——三顯式源全敗且 `OPENCLAW_DATA_DIR` 非空時讀同一契約檔(顯式永遠優先;未設絕不猜默認路徑)。**沿用既有 audit_events INSERT 契約與既有 trading_admin DSN 檔,零新權限**。runtime 一行 apply 見 §五(operator-gated)。 |
| 3 | 14:51 事件回補 | **無需人工 backfill——帳沒有丟**。契約內建的 tail-bridge backstop(`canary_audit_pg_writer` cron,每 2 分鐘)已在 **14:52:01(+16s)** 把 crash/recovered 冪等補進 `audit_events`(id **1877** engine_crash critical / **1878** engine_recovered info;16:35 那輪=id 1879/1880 @16:40:01)。今天 24 行全在。損失的只是「直寫即時性」(降級為 ≤2 分鐘 bridge 延遲)。本報告即 ops note。 |
| 4 | 引擎當日死因 | **不是引擎 bug,是全機 OOM 風暴的下游症狀**(詳 §四)。14:51:27 kernel 殺掉一個 64.8GB 的 cron python 的同一秒,引擎(pid 683173)在記憶體/swap 壓力下 snapshot 停寫 47.2s>45s 閾值,被 watchdog 判死替換——引擎本體當時**未被殺、無 panic**。16:35:48 kernel 則實錘直接 OOM 殺引擎(pid 700258,`oom_score_adj=200` 偏好受害)。`engine.log` 每次 boot 截斷重建,14:51 前日誌已被覆蓋;死因鏈由 kernel journal + `boot_history.jsonl` 重建。 |

## 二、DSN RCA 細節

- watchdog 進程(取證時 PID 741031)env 實測:僅 `OPENCLAW_DATA_DIR=/home/ncyu/BybitOpenClaw/var/openclaw` + 少量 OPENCLAW_* flag,零 PG/DSN 變數;engine 進程(PID 741756)則有 `OPENCLAW_DATABASE_URL_FILE=…/var/openclaw/runtime_secrets/openclaw_database_url`(檔存在:76B/0600/mtime 隨每次 restart 重寫)。
- DSN 原料兩處俱在(契約檔+`basic_system_services.env` 的完整 `POSTGRES_*`),watchdog unit 一個都沒接——**純 env 鋪設缺口,非代碼壞**。
- 頻率:`no DSN buildable` per-day 07-11:2 / 07-12:0 / 07-13:4 / 07-14:0 / 07-15:24(每次 restart 事件 crash+recovered 各一條)。07-15 暴增是 OOM 風暴放大重啟次數所致。
- 「Python fallback strike 1/3」是正常重啟記帳(1 小時窗三振制,`STRIKE_WINDOW_SECONDS=3600`),非第二故障;今天 strike 最高到 2/3,從未 3/3——watchdog 自己被 OOM 連坐重啟會歸零計數(附帶觀察:三振保護在 OOM 風暴形態下被稀釋)。

## 三、修復(source-landed,本 PR)

| 檔 | 內容 |
|---|---|
| `helper_scripts/systemd/openclaw-watchdog.service` | 補 `OPENCLAW_DATABASE_URL_FILE` env 行(對齊 engine unit :62);注釋記事故形+為何不加 `ExecStartPre -s`(watchdog fail-soft,DSN 缺不得拒啟)。 |
| `helper_scripts/canary/canary_audit_common.py` | `resolve_dsn()` 第 4 步備援 `_derive_dsn_from_data_dir()`:`OPENCLAW_DATA_DIR` 非空時讀 `$OPENCLAW_DATA_DIR/runtime_secrets/openclaw_database_url`;未設絕不猜默認(/tmp 植檔風險);例外覆蓋 `(OSError, ValueError)`(E2 P2-1,branch 1 同步)。 |
| `helper_scripts/canary/test_canary_audit_common.py` | +6 測試(備援分支五情境 + partial-POSTGRES_* 語意釘住;鐵則測試以 read_text 探針做到環境無關 mutation-bite);setUp 補 `OPENCLAW_DATA_DIR` 清理。 |
| `helper_scripts/canary/canary_audit_pg_writer.py` | 排錯提示補列第 4 步(E2 P2-3)。 |
| `helper_scripts/SCRIPT_INDEX.md` | `canary_audit_common.py` 行解析序描述同步。 |

**審查 verdict**:E2 PASS(0 P0/P1;P2×5 → P2-1/2/3/5 已收,P2-4 記錄如下)、E3 PASS(0 P0/P1;P2×4 recommendation-only;runtime apply=條件 GO,條件已內嵌 §五)。測試:canary 三檔 pytest 全綠(見 PR)。

**記錄的殘餘風險(接受理由)**:
1. *env/arg split-brain*(E2 P2-4):推導 keyed on env `OPENCLAW_DATA_DIR` 而非 `--data-dir` 實參;兩者不一致時最壞=audit 寫錯庫(observability 誤導,無交易面;dedup 冪等)。當前 runtime 兩者一致(皆 var)。
2. */tmp 殘留 unit 條件*(E3 P2-1):若任何 live unit 仍 export `/tmp` 下 DATA_DIR,跨 uid /tmp 植檔可把 audit 改道假 PG(升 P1)。取證證實 watchdog/engine/bridge cron 皆已 var;durable-unit 收口時需保持。不加 stat 驗證:同 uid 信任域 + env 行落地後 branch 4 在 watchdog 上實質休眠。
3. *installer 默認值*(E2 P2-4 附帶):`install_watchdog_service.sh` 默認 `OPENCLAW_DATA_DIR=/tmp/openclaw`,與 runtime 已遷 var 相左——future durable-unit 安裝必須顯式傳 var 路徑。
4. *相鄰缺口*:`incident_sentinel.py:441` 有獨立三源 DSN 副本,不獲本次備援;同型漂移會在該處復發(follow-up 候選,未納本 ticket)。

## 四、引擎死因:trade-core OOM 風暴(升格 P0)

取證事實(2026-07-15,kernel journal + `boot_history.jsonl` + `ps`):

- **kernel 至少 16 次 OOM kill**(12:36–16:51 本地,約每 15 分鐘一次,吻合 crontab `*/15` 族排程);受害者幾乎全是 cron 側 60–84GB anon-rss 的 python。
- 現行元兇證據:`…alpha_discovery_throughput.runtime_runner` 25GB RSS / 92% CPU、`…cost_gate_learning_lane.outcome_review` 22GB RSS / 92% CPU(主機 124GB RAM + 8GB swap,取證時 60GB used / swap 3.7GB)。
- **watchdog unit 今天被 OOM 連坐 5 次**(06:05/07:22/09:53/10:36/16:35,memory peak 21.8–47.2GB);引擎裸進程活在 watchdog cgroup 內(無獨立 unit),`oom_score_adj=200` 使其成偏好受害者;`OOMPolicy=stop`+`KillMode=control-group` 耦合=殺引擎連坐殺 watchdog。
- 引擎今天 5 次 boot(UTC 08:38/10:35/11:52/12:51/14:37),全部 `build_sha 0a4d38ee`(落後 main 12c,皆 learning/ML 修復,與本案無關)。

**E5 代碼級 RCA(2026-07-15,只讀)結論**:
- 單進程 20-25GB:兩模組共同模式=「**全量物化 + 純 Python 統計**」。`outcome_review` 經 `read_jsonl_ledger`(`cost_gate_learning_lane/runtime_adapter.py:215-236`)把 probe_ledger 主檔(~393MB)+14d 輪轉段全行 parse 駐留(代表行實測膨脹 **5.3x**;07-11 lineage 驗證每行再加 2-4 個 dict 複製),再跑 B=1000 sign-flip 置換檢定(`evidence_stats.py:177-216`,純 Python 雙層迴圈=92% CPU 數十分鐘高 RSS 持有);`runtime_runner`(*/15)在 status 摘要內 **inline 重做 hourly 的完整 review**(`cost_gate_learning_lane/status.py:649-762`,`read_text()` 一次吞主檔),另 `polymarket_leadlag/replay_history.py:159-178` **glob-parse 目錄內全部報告(~3000+ 檔)後才截斷 limit**。
- **全機 60-84GB 的主放大器=stale-lock 疊加**:`alpha_discovery_throughput_cron.sh:36-44`(20 分鐘)與 `cost_gate_learning_lane_cron.sh:152/367-372`(30 分鐘)超時即**清鎖照跑新進程、舊進程不殺**——單次 run 超時後每 15 分鐘淨增一個 20-25GB python,124GB+8GB swap 擊穿。
- 非單點回歸:06-21~24 舊無界讀模式 × 三波常數放大(07-04 sign-flip 進 review `002b8f4be`/07-10 `_effective_entries` 每 cell 兩算 `49049f84d`/07-11 每行 lineage 複製 `38ccd014c`)× 數據單調增長跨閾值 × stale-lock 疊加。
- 量級歸因缺口(誠實聲明):主檔-only 只解釋 ~2-3GB;需 3 個零風險 runtime 量測定權重:①`ls -lh …/cost_gate_learning_lane/probe_ledger*.jsonl`(主檔+段檔總量);②`du -sh …/research/polymarket_leadlag/`+檔數;③對現行 hog `py-spy dump`(只讀 attach)看棧停在 json.loads/sign_flip/load_replay_reports 哪個。

**緩解選單(E5 優先序;均 runtime mutation=operator-gated)**:
- **P0 零代碼圍欄(今天可上)**:重 cron 包 `systemd-run --user --scope -p MemoryMax=… -p MemorySwapMax=0`(alpha 12G/cost_gate 12G/polymarket 6G;代碼修後可再降),或統一 `openclaw-research.slice`(MemoryHigh=24G/MemoryMax=32G);watchdog unit `OOMScoreAdjust=-900`、引擎 `-600`(現 +200=把交易權威標成首選獵物)。風險:cgroup kill 留 stale artifact(下游 fail-closed 可容忍);不用 `ulimit -v`(VSZ 誤殺)。
- **P1 小 shell diff(單獨可終止疊加)**:stale-lock 清理改「先殺舊進程組再接手」或 `flock -n` 進程綁定鎖,嚴禁 rmdir-and-run;alpha `*/15`→`*/30` 並與 `:27`/polymarket 槽錯位。風險:killboard 新鮮度 15→30 分(artifact-only,可接受)。
- **P2 代碼級最小修**(行為保持型,需 E2/E4 鏈):status.py 改 streaming+欄位投影(~95% 削減)或直接消費 hourly 產物;`read_jsonl_ledger` 加 record_type/欄位過濾;`_effective_entries` 一算兩用;replay_history 先排序只 parse 最新 limit 個+polymarket 目錄 retention;sign-flip numpy 化(統計語義需 QC 過目)。
- **P3 結構**:*/15 觀測面與 hourly 統計面解耦;查 ledger 輪轉為何主檔仍 393MB(Rust 側 rotation 是否活躍/引擎 build 落後)。

註:16:35 級直接殺引擎若復發於持倉時段,恢復鏈=watchdog 120s grace+restart ≈2-3 分鐘引擎中斷。

## 五、Runtime apply runbook(operator-gated;E3 條件 GO 已內嵌)

**Step 1|unit env 一行(不重啟,建議即批)**
編輯 `~/.config/systemd/user/openclaw-watchdog.service` 的 `[Service]`,緊鄰既有 `Environment=OPENCLAW_DATA_DIR=…` 加一行(單行、逐字):

```
Environment=OPENCLAW_DATABASE_URL_FILE=/home/ncyu/BybitOpenClaw/var/openclaw/runtime_secrets/openclaw_database_url
```

然後 `systemctl --user daemon-reload`。**E3 條件 1 post-check(必做)**:

```
systemctl --user show openclaw-watchdog.service -p LoadState -p Environment
```

驗 `LoadState=loaded` 且 Environment 含上行;缺一即回退編輯(失敗模式=unit 載入壞 → 下次自然退出後 watchdog 不重生=引擎失去 restarter,靜默監控真空)。生效時機:**下次 watchdog 重生**(當前 OOM 風暴下自然重生頻繁;或 Step 2 主動 restart)。E3 條件 3:此手管 unit 編輯記入 durable-unit 收口任務(TODO row)+ 下次重生後 journal/watchdog.log 確認不再出現 `no DSN buildable`。

**Step 2|(可選)主動 restart watchdog——注意連坐**
`systemctl --user restart openclaw-watchdog` 因 `KillMode=control-group` 會 **SIGTERM 引擎**(引擎活在同 cgroup):代價=引擎優雅停機 → watchdog 重生 → 120s grace → 判 stale → restart_all --engine-only 拉回,**≈2-3 分鐘引擎中斷+一次偽 ENGINE_CRASH 記帳**(16:35 事件即此形)。若可等自然重生,不建議主動 restart。

**Step 3|(可選)Linux srv 同步源碼**
`cd ~/BybitOpenClaw/srv && git fetch origin && git pull --ff-only`——使 `resolve_dsn` 第 4 步備援落地(watchdog 下次重生吸收;bridge cron 下輪 fire 即吸收)。注意:pull 同時帶入 main 上 `0770bd138..` 之後全部 commits(取證時 12c,皆 learning/ML;本 PR 併後再多 1-2c),屬標準三端同步判斷。**Step 1 與 Step 3 二取一即可閉合直寫**(Step 1=舊代碼 branch 1 生效;Step 3=新代碼 branch 4 兜底);建議兩者都做=縱深。

**Step 4|驗證(下次 restart 事件後,只讀)**
`watchdog.log` 無新 `no DSN buildable`;PG `SELECT id,created_at,event_type,summary FROM audit_events WHERE event_source='engine_watchdog' ORDER BY id DESC LIMIT 4;` 出現 **summary 不帶 "backstop" 字樣**的直寫行(bridge 補的行帶 backstop 標記)。

## 六、順帶觀察(不在本 ticket 動作)

- `openclaw-alr-shadow` user unit 取證時 activating/auto-restart flapping——ALR 軌(V151-V157 pending chain)範疇,已有 TODO 行,未深查。
- `openclaw-gateway` inactive/dead(disabled)=既知 dormant 姿態,符合預期。

**證據錨**:watchdog.log 49009–49015(14:51 事件五行);user journal oom-kill×5 時刻;`boot_history.jsonl` 今日 5 boot;audit_events id 1877/1878/1879/1880;engine_watchdog.py sha `ba877a03…`(Mac/Linux 一致);Linux HEAD `0770bd138` 乾淨;E2/E3 fragment 全文由 PM 持有(本輪未落 role report 檔,per governance)。
