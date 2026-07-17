---
name: project_2026_07_12_reconcile_pathb_arc
description: 玄衡 治理 reconcile (demo 引擎↔api-demo) Path B advisory-first 建置+部署弧;含 OPENCLAW_DATA_DIR /tmp-vs-var 漂移陷阱、v2 引擎 dust-freeze 修復、arming gate 待 Phase 2
metadata:
  node_type: memory
  type: project
  heat: 0
  originSessionId: e68bbc7b-975e-4ab2-8841-819d97ee4669
---

承 GUI 對齊 ratchet(P1.0 切片 5b)發現的 M1 drift。`governance.js govPostReconcile` 手動對賬鈕原本三層壞(dead route `/api/v1/paper/status`、client 建錯 shape、`demo_state=null` 自比恆 consistent)+ escalation 三重死(severity 字串不匹配 + dead action filter)→ 從未做過真對賬,且錯 shape 可能假 MISMATCH→假 risk escalate/auth freeze。Operator 裁 **Path B(建成真兩側對賬)** 而非移除。

## 弧與 SHA
- **v1 `c2cb45fc5`(2026-07-12)**:server-side 雙側組裝(GUI 只送 `{reason}`,結構消除 L1/L2/L3)+ 單一 `map_report_to_escalation` SoT + fail-closed STALE_DATA(demo/local 不可達→不呼 reconcile,永不空`{}`→永不假 freeze)+ 移除 self-compare/舊 "CRITICAL" 直升。**advisory-first**:`RECONCILE_ADVISORY_FIRST_MAX_ESCALATION="MISMATCH_MAJOR"` cap(手動路徑永不 auth-freeze/circuit-break)。審:E2 PASS/CC 條件批/E4 293。
- **v2 `497ebb4b2`(2026-07-12)**:讓 MATCH 可達(仍 advisory,不 arm)。**A(Rust 引擎)**=`evict_if_dust` 對「交易所可表示殘量」FREEZE(retain,relabel `DUST_FROZEN_STRATEGY`)而非 evict;gated real-strategy owner;representable=`residue>=step*(1-1e-9)`(float-tolerant);spec-unknown real-strategy 用 magnitude fallback(`>=1e-6`)retain,7e-13 phantom 仍 evict;保 apply_fill 唯一 mutator。**B(Python)**=`reconcile_orders=False` scope-exclusion(交易所是 order 權威),MATCH artifact 自揭 `orders_scope="excluded:exchange-authoritative"`(不可讀成「orders 對賬乾淨」)。**C(Python)**=drop `execType=Funding` + windowed per-symbol fill 比對。審:E2(M1 cold-cache+BB float-lossy 已修)/BB PASS/QC no-block/CC 條件批(C1 disclosure 已修,C2-C5+C-ARM-4 記入 C-ARM block)/E4 Rust 4452+Python+7 零回歸。

## Runtime 定案(source 被 runtime 覆寫)
- **UNKNOWN-1 定案(Rust source)**:`engine="demo"` 是對的 pair——Demo pipeline 真下單到 api-demo(`/v5/order/create`)+ boot seed + WS 對賬,故穩態應 MATCH;`engine="paper"` 是純本地 sim(錯 pair)。`main_pipelines.rs:468`/`step_4_5_dispatch.rs:945`。
- **分歧根因(runtime attribution)**:demo 帳戶 **100% 引擎自造**(全 `oc_…_dm_…` orderLinkId,無 bounded-probe/手動/外來)。59 discrepancies=①ATOM/AVAX 0.1 FATAL=**真引擎 intraday dust-eviction bug**(自己平倉 under-sweep 留 sub-min-notional dust,交易所留、本地 evict)→v2.A 修;②5 orders CRITICAL=reconcile v1 scope(orders:[])→v2.B scope-exclude;③fills 4v50=window/Funding artifact→v2.C。**reconcile 抓到真 bug=賺到了**。
- **advisory cap runtime 實證**:真 FATAL→`report_severity=FATAL` 但 `escalation_enacted=MISMATCH_MAJOR`(capped)——阻止了生產中的過早 auth-freeze。advisory-first 決策被最強驗證。

## ⚠ OPENCLAW_DATA_DIR /tmp-vs-var 漂移陷阱(復發性 ops gotcha)
control-api **無 systemd unit**(只 engine/watchdog/collector 有)→`restart_all.sh:45` 從 shell 取 `OPENCLAW_DATA_DIR`(default `/tmp/openclaw`)。引擎 2026-07-07 15:49 遷 `~/BybitOpenClaw/var/openclaw`(「home paths 非/tmp」),長跑 API 仍釘 `/tmp`→**讀 5 天 stale 快照**(demo/live/paper GUI 全 offline/stale via 60s freshness gate;+scheduler 雙主+alert_config 分裂)。**修**:2026-07-12 用 `OPENCLAW_DATA_DIR=/home/ncyu/BybitOpenClaw/var/openclaw bash restart_all.sh --api-only --keep-auth` 重啟(PID 3536174,已驗 build_local 讀 fresh)。**未修(durable)**:裸 API 重啟會再漂移→需裝 `openclaw-trading-api.service`+EnvironmentFile(`api_service_env_parity.py` 已預期)或 login-profile export。**教訓:重啟 control-api 必 export OPENCLAW_DATA_DIR=var/openclaw,否則 GUI demo/live 讀 stale**。

## 待辦(operator-gated)
- **v2 Phase 2**(EXTERNAL_VERIFICATION_PENDING):engine rebuild+restart(比 api-only 大;pause trading+watchdog)+ operator 一次性清 Bybit Demo GUI 殘 dust/stale orders(或重啟讓 startup `triage_bybit_sync` re-freeze)+ **live-shadow 穩態 MATCH** 觀察 → 才 arm(獨立 operator+CC audited diff 移 cap;C-ARM-1/2/3/4 全滿足)。
- ~~**DATA_DIR durable fix**(systemd unit/profile export)~~ → API 側已關閉,見下方「2026-07-15 API durable user unit 已存在」節(watchdog unit env 是另一軸=PR#22)。
- 設計正本:`srv/docs/execution_plan/gui_redesign/reconcile_pathB_design.md`(v1+§v2)。相關:[[project_2026_06_08_phantom_position_fill_fix]](同 paper_state/apply_fill 唯一 mutator/reconciler 軸)。

## 2026-07-15 watchdog audit DSN chronic 缺口 + OOM 風暴揭露(WATCHDOG-AUDIT-DSN-1,PR#22 `103f854e5`)
- operator 盤點:14:51:45 watchdog auto-restart 成功但 `audit write skipped: no DSN buildable`。OPS 只讀取證:watchdog=手管 user unit(`~/.config/systemd/user/`,無 EnvironmentFile/零 PG env,chronic 自 06-20 上線首日;DATA_DIR 已 var 無 /tmp 問題);engine 無獨立 unit,裸進程活在 watchdog cgroup(KillMode=control-group → restart watchdog 連坐引擎 ~2-3 分鐘)。
- **審計帳未丟**:tail-bridge(canary_audit_pg_writer cron,06-27 誤刪 07-09 復原)14:52:01 以 dedup_key 冪等補 audit_events id 1877/1878——backstop 契約自癒,無需人工 backfill;丟的只是直寫即時性。
- 修 source-landed(PR#22):unit 模板補 `OPENCLAW_DATABASE_URL_FILE` + `resolve_dsn()` 第 4 步備援(OPENCLAW_DATA_DIR 推導契約檔;顯式優先;未設絕不猜默認)+ except `(OSError,ValueError)` + 6 tests;E2/E3/E4 全 PASS。**runtime 一行 apply 待 operator**:runbook=`srv/docs/CCAgentWorkSpace/PM/workspace/reports/2026-07-15--watchdog_audit_dsn_rca_runbook.md` §五(Step 1 env 行+daemon-reload+post-check;可等自然重生不必 restart)。TODO row `P1-WATCHDOG-AUDIT-DSN-RUNTIME-APPLY`。
- **引擎當日「死因」=全機 OOM 風暴(升格 P0)**:cron python(alpha_discovery_throughput.runtime_runner / cost_gate_learning_lane.outcome_review)全量物化 probe_ledger(5.3x 膨脹)+純 Python sign-flip B=1000;**主放大器=cron shell stale-lock 超時清鎖照跑、不殺舊進程,每 15min 淨疊 20-25GB**(alpha cron :36-44 / cost_gate cron :152,367-372);kernel 16 kills、watchdog unit 連坐 5 次、16:35:48 直接殺引擎(oom_score_adj=+200 偏好受害)。14:51「crash」實為壓力下 snapshot 停寫 47.2s 被判死,無 panic。E5 RCA+緩解選單(MemoryMax wrap/OOMScoreAdjust 反轉/殺舊接手/streaming 投影)在 TODO `P0-TRADE-CORE-OOM-STORM-CRON-MEMORY`+報告 §四;量級歸因缺 3 個零風險量測。
- 教訓:①unit-env 漂移是家族病(API 07-12/watchdog 06-20),resolve_dsn 推導備援使 audit 面免疫 env 漂移;②dedup_key 冪等雙路徑審計在 direct write 斷線時真兜住,backstop 設計值得;③watchdog 三振計數在自身被 OOM 連坐時歸零→風暴形態下三振保護被稀釋;④TODO 版本號是多 session 競態資源(v808 被 IBKR loop 佔,本輪讓位 v809,rebase 前必 re-fetch)。

## 2026-07-15 API durable user unit 已存在(OPS-F1 api.log 收口時發現;演變:推翻上方「未修 durable」)
- `~/.config/systemd/user/openclaw-trading-api.service` 已在 runtime 存在並接管 API:現任 uvicorn(PID 374618,07-14 23:55:55 起)cgroup 在該 unit 下;enabled+`Linger=yes`;unit 內 `Environment=OPENCLAW_DATA_DIR=/home/ncyu/BybitOpenClaw/var/openclaw`+`OPENCLAW_DATABASE_URL_FILE=…runtime_secrets/openclaw_database_url`;`Restart=always/RestartSec=5`;stdout/stderr→journald(fd1/2=socket)。api.log 自此停更(var 16MB 停 07-14 01:02、/tmp 12.4MB 停 07-14 23:55——兩檔即歷史 DATA_DIR 漂移的地層證據)。unit 檔不在 repo(repo systemd/ 只有 engine/watchdog/collector/caddy/tls;README:220+TODO:106 有引用)。裸 API 重啟再漂移的風險由 unit 關閉;`api_service_env_parity.py` 全量 env parity 未逐項驗。
- 同日 OPS-F1 收口(本節佐證脈絡,git 已記錄細節):PR#25 engine.log O_TRUNC→O_APPEND ×3+fresh/clean spawn 前 mv 歸檔(E2 R1 MEDIUM:watchdog classify 依賴 fresh-file invariant);PR#26 api.log logrotate stanza 200M×7(var+/tmp)+`>>`×3+structure 守門測試(釘 6 spawn 行/copytruncate/禁 maxsize-dateext)。trade-core 已 pull(5f84db5c3)+conf cp 安裝(`.bak-20260715`)+`logrotate -d` 綠;與 PR#24 [95] drift 哨兵閉環(canonical=runtime)。腳本 api.log 路徑降為 fallback(`restart_all --api-only`/fresh/clean)。

## 2026-07-15 logrotate conf drift 哨兵 [95](OPS F4 收口,PR#24 `83c995d24`)
- 事故面:runtime `~/logrotate-openclaw.conf` 漂回只蓋 /tmp 死路徑(canonical 已入庫仍漂)→ var 真 engine.log 輪替自 06-27 空轉、alpha cron log 裸奔 4.5GB 才人工發現(OOM 風暴同家族症狀;當日 conf 修復 `00c11d55b`+`416b72835`,後者=maxsize 在無排程 conf 退化 1MiB 默認基線之修)。OPS F4=repo 全域零 logrotate drift 防線。
- 防線:passive_wait_healthcheck 新增 `checks_logrotate_governance.py` `[95] logrotate_runtime_matches_repo`——runtime vs repo canonical 整檔 sha256(安裝契約=整檔 cp,位元組平價即契約 machine-check,故不用 [92] 的 active-行口徑);不一致 >24h 預設 WARN、`OPENCLAW_LOGROTATE_GOVERNANCE_REQUIRED=1` 升 FAIL,<24h 容忍窗;純觀測 read-only、全 OSError fail-soft(runtime 缺失=WARN 帶 cp 提示);防禦深度=chunked sha256(1MiB,防 env 誤指大檔 MemoryError 崩 lane)+未來 mtime>now+60s 保守超窗(防時鐘偏移/竄改壓制升級)+stat-race 保守超窗。E1 兩波→E2 兩輪(8 情境反例重放,無 BLOCKER/MAJOR 殘留)→E4 兩輪(focused 11/lane 32/廣度 527 全綠,咬合驗真)。
- runtime 實證:trade-core pull `83c995d24` 後首讀 **PASS**(兩側 sha `88be16ff8b87`=07-15 人工 cp 已到位);完整 runner FAIL 集 merge 前後逐條一致(7 條全 pre-existing:[1][12][49][74][82][19][56]),本改動零擾動;lane cron `13,43 * * * *` 每 30min 自動巡,無需部署動作。
- 已知限制+follow-up:drift 時長以 mtime 為 proxy——持續手改 runtime 會反覆刷新容忍窗,REQUIRED=1 升級承諾對「持續竄改者」不成立(一次性漂移後擱置>24h 的本事故形態則正確升級;偵測面每輪 WARN 含兩側 hash 永不靜默);根治=仿 [92] 落安裝 receipt/manifest(MODULE_NOTE+PR body 已載)。runtime 缺失只 WARN(任務 spec 明文)弱於 [92] 空 crontab 無條件 FAIL——有意不對稱,E2 留 MINOR observation。

### 07-15 追記:疊加機 flock 修復 source-landed(CRON-STALE-LOCK-FLOCK-1,PR#27 `d7752254e`)
- OOM 風暴 P1 子項執行:新 `helper_scripts/cron/lib/cron_flock.sh`(`acquire_cron_flock`,flock -n 進程綁定鎖;活鎖絕不搶佔超齡只 WARN;鎖檔常駐禁刪;缺 flock/lib=fail-safe skip;**拒 kill-takeover**=PID 重用誤殺+長任務 livelock)+7-case 測試;兩元兇 cron 遷移,業務零改動。E2 PASS(0 P0/P1)/E4 trade-core 密閉 7/7 PASS(bash 5.2 真 flock;kill -9 反疊加核心性質實證;exec 開檔失敗 rc=2 shell 存活)。
- **部署待 operator**:Linux srv pull(換鎖窗先 pgrep 防新舊鎖並行一輪)+跨長跑週期驗 python 實例 ≤1(E2 gate#4);flock 後單進程 20-25GB 峰值猶在→P0 圍欄(MemoryMax/OOMScoreAdjust)仍建議。
- follow-up(SCRIPT_INDEX 有逐檔清單):鎖家族 34 檔——full-pattern 疊加機 14 修 2 留 12;**另 20 檔 mkdir+trap-rmdir 部分模式=SIGKILL 孤兒鎖→lane 永久 skip 飢餓(first-detection-deadlock 近親)**,同待遷;遷移 checklist 含 background-job 粗篩(fd 繼承→鎖永不釋放)。shellcheck 兩機皆缺(CI lane 或 brew,follow-up)。
- 教訓:①「清 stale 鎖」的正解不是把 stale 判準做對,而是讓 stale 態結構性不可能(kernel 綁定生命週期);②kill-takeover 在「任務比閾值長」的世界必然 livelock——閾值理應是觀測告警線,不是執行決策線;③TODO 版本號競態再現(v808/v810 皆被並行 session 佔),rebase-then-redo-docs 流程二連驗證有效。

## 2026-07-15(晚)logrotate manifest 治理入口+[95] proxy 升級(PR#30 `5366303`,收口 [95] 已知限制)
- 承 [95] 哨兵(PR#24)已知限制:mtime proxy 可被持續手改 runtime 刷新 24h 容忍窗。收口=①新唯一安裝入口 `helper_scripts/cron/install_logrotate_from_repo.sh`(鏡像 crontab installer:平台守門/預設 dry-run/空表+stanza shrink-guard(`OPENCLAW_LOGROTATE_ALLOW_SHRINK=1` 豁免)/`logrotate -d` validation gate(dry-run 也擋)/before-after-diff-manifest 落 `$OPENCLAW_DATA_DIR/logrotate_mutations/<UTC>Z/`(同秒碰撞 .$$ 後綴)/原子安裝+sha256 post-verify);②**manifest 兩段式=承重設計**:dry-run/被拒路徑只留 `applied:false` 不刷時鐘,--apply 過 post-verify 才改寫 `applied:true`;③[95] drift 起點改讀最新 applied:true manifest mtime,**廢除 file-mtime proxy**——無合規 manifest/dry-run-only/壞 JSON 的 mismatch 一律視為超窗(嚴格 [92] 口徑;比 follow-up 原文「退 mtime proxy」更嚴,fallback 會讓刪 manifest 重開漏洞,PM 有意偏離並記入 PR)。
- E2 R1 **FAIL-conditional** 抓到兩支真 MAJOR 後修復:manifest 解析三守衛(>1MiB skip 防 MemoryError 崩整個 runner/isinstance dict 防 null-list 頂層 AttributeError/except 含 RecursionError)+installer JSON escape(reason 含引號=自然語言常態,原會讓 applied receipt 自毀成壞 JSON→零 grace 誤超窗);`applied is True` 嚴格判定有雙突變殺傷測試(字串 "false" truthy/數字 1 等值)。E2 delta PASS(probe:64MB manifest 峰值 128MB→1.0MB)/E4 PASS(16+13+8+34+259 全綠+527 廣度)。
- runtime 實證(trade-core):pull `5366303` → installer dry-run(validation passed,5→5 stanza,receipt applied:false)→ --apply rc=0(第一份 applied:true manifest 落地,reason 全文入帳)→ [95] PASS(`af2913a42d73`)→ 完整 runner 零 traceback、FAIL 集=pre-existing(含 [68] portfolio divergence——merge 前 cron log 已連續 FAIL,OOM 後遺家族,非本改動)。
- 教訓:①machine-read 的 receipt 格式(JSON)一旦被下游 parse,上游裸 heredoc 內插就從化妝品缺陷升級為 load-bearing 缺陷(sibling crontab installer 同構裸內插但 [92] 只 stat 不 parse,故彼處無害);②「fallback 保底」在治理哨兵語意下常=「漏洞保留」,fail-closed(無 receipt=超窗)才是根治;③deploy 序:installer 與 healthcheck runner 的 `OPENCLAW_DATA_DIR` 必須同值,否則 receipt 互不可見=永久誤超窗(unit-env 漂移家族又一例)。

### 07-16 追記:OOM-victim 自標 source-landed + 圍欄量測定案 + flock 部署生效(承 07-15 疊加機弧)
- **operator 授權「做 1+2+3 後三端同步不 CI」**(1=部署本修 2=P0 圍欄 3=量測)。執行揭第2項圍欄的**權限硬約束**(探針實證):①引擎/watchdog `oom_score_adj=200` 來源=user manager `DefaultOOMScoreAdjust=200`,user 無 CAP_SYS_RESOURCE **不能降負**(systemd user `OOMScoreAdjust` 設不了/choom 降負需 root);②cron job 環境**無 DBUS**→`systemd-run --user` MemoryMax **不可用**;③唯一零特權=cron hog **提高自己** oom_score_adj(往正,實證 echo 800 成功)。
- **量測定案**:單進程失控**實測 79-85GB anon-rss**(kernel victim,非 E5 估 20-25GB;reject_materializer 71s→10.7GB 在漲);probe_ledger 6.2G/117 段;**polymarket_axis_runs 21GB/1708 檔**(E5 未覆蓋磁碟炸彈)。**MemoryMax 判不可安全定值**:失控 85GB vs 正常峰值未知(lane 一直被殺從沒正常跑完),盲設<正常=誤殺 livelock(與 flock 同構)→真解=P2 streaming 代碼修。
- **CRON-OOM-VICTIM-1 上 main PR#31 `6ffeb780b`**:新 `cron/lib/cron_oom_victim.sh`(`mark_cron_oom_victim` 寫 /proc/self/oom_score_adj=800,群組包 fail-soft,跨 fork+exec 繼承→標一次子孫全 victim;800>>引擎 200)+兩重 cron 取鎖後接線+7-case 測試。E2 PASS(0 P0/P1)/E4 trade-core 密閉(uid1000 真 /proc)五 case 兩跑全綠+繼承 777 跨兩代+消費者 smoke adj=800(probe PID==flock holder)。
- **第1項部署完成**:Linux runtime `git pull --ff-only`→`6ffeb780b`(flock PR#27+hog PR#31),**inode changed=YES 證 git unlink-then-create**(正在跑的舊實例讀舊 inode 安全、新 fire 用新腳本)。**postcheck flock 反疊加 runtime 鐵證**:新 `.lock` 檔在用+cron log `SKIP: already running (lock held)`(:15 alpha 被 flock 擋不再疊加)。引擎/watchdog adj 仍 200(降負待 operator root)。Mac 主 checkout 在別 session 的 gui recovery 分支,不強動(尊重多 session);三端 runtime 面=Linux pull 生效。
- **operator 剩餘待辦**(TODO `P0-TRADE-CORE-OOM-STORM-CRON-MEMORY` status=SOURCE_MITIGATIONS_LANDED_AWAITING_OPERATOR_DEPLOY_AND_ROOT):①跨長跑週期驗 python 實例≤1(E2 gate#4);②**需 root 降引擎 adj**(改 DefaultOOMScoreAdjust 或引擎轉 system unit)=唯一從根本移引擎出 OOM 射程;③P2 streaming 代碼修(reject_materializer/outcome_review 別全量物化,砍 95%)。
- 教訓:①「零代碼圍欄」的 E5 建議(MemoryMax/OOMScoreAdjust)在 **user 權限模型 + cron 無 DBUS** 下大半不可行——探針先行避免盲上失敗;②保護策略在無特權時反向做(不能降引擎、就升 hog);③MemoryMax 定值需「正常峰值」,而永遠被殺的 lane 無正常峰值可測=盲設即誤殺;④部署用 git unlink-then-create 語意可在疊加中安全 pull(inode 換,舊實例讀舊 inode)。

## 2026-07-16 深夜~07-17 追記:learning-lane 有界投影/streaming 修復波上 main(OOM「真解 P2」source 面大步落地)
- 承上節 OOM row「MemoryMax 不可安全定值→真解=P2 streaming 代碼修」:p0 系列連發併入(新史)main——**p0b candidate board 有界投影**(PR#43/#50)、**p0d sealed horizon 有界 streaming**(PR#52,commit body 明文「Replace full retained-ledger materialization with candidate-scoped disk projections + streaming JSONL I/O」=正面拆 79-85GB 全量物化路徑)、p0a outcome_refresh 記帳誠實(PR#44 batch mature backlog+fallback event time/PR#46 durable backlog 終端化計數)、p0c pre-capability 評估源終端化+runtime wiring(PR#54/#56,附 `pg_connect` 每連線 statement_timeout 持久化修)。
- 尚未收口:`agent/p0-oom-*` 4 支線(ledger streaming/polymarket streaming 投影/data-plane stability/systemd scope repair)仍 in-flight 未併;OOM row 的 root 降引擎 adj+跨週期驗 python 實例≤1 仍待 operator。
- 部署面:07-17 三端同步(見 [[project_ssh_bridge_workflow]] 全史重寫節)後 Linux checkout 已含上述已併修,cron 下輪 fire 即用新碼;OOM row 狀態重評歸下輪 loop。
