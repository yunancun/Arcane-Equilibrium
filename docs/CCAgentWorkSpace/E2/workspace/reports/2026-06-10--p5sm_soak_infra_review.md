# E2 PR Adversarial Review — feat/p5sm-soak-observability @ 9dc533b0 · 2026-06-10

- 對象:worktree `/tmp/wt-p5sm-soak`,base main `bb02b14c`,5 commits(`58ad4dba`/`4d4ac6fb`/`e9b99b07`/`9eba5a40`/`9dc533b0`)
- 設計權威:PA `2026-06-10--p5sm_soak_observability_redesign.md` + PM `2026-06-10--p5sm_soak_cadence_decision.md`
- 測試環境:`srv/venvs/mac_dev/bin/python`(3.12)

## Verdict:RETURN to E1(2 HIGH + 2 LOW;其餘全綠)

兩個 HIGH 都在 `[82]` gate 算術的「無假綠」軸(PA §5.3 指定 E2 重審軸 2),非隔離性/零 mutation 問題。隔離性與零 mutation 兩軸全綠;E1 三項自決偏差全 ACCEPT;242+2 復現;E1 兩個 mutation 紅→綠復現。

## 改動範圍

17 檔 +3328/−17。生產碼:canary 模組(NEW 499)/flusher 擴充(+404/−9,刪 9 行中 8 docstring + 1 行為 loop 呼叫換複合 cycle,comparator 投影為 cycle 第一步行為保持)/lease_ipc_schema additive(+105)/main.py wiring(+27)/`[82]` healthcheck(+353,`[81]` 0 刪除位元組不變)/runner 註冊(+19)/restart_all.sh 轉發 2 env(+10)/V137(NEW 256)/smoke(NEW 337)/殘文修正 2 檔(docstring-only)。測試:+24/+16/+53 個 test,0 刪測。docs:singleton-registry §2.5.5/§2.5.6 + SCRIPT_INDEX + E1 memory。

範圍 vs PA task 表:E1-A~E1-E 全對應;additive 偏差 = restart_all.sh 轉發(PA 未列檔,但 PM 防護 4「kill-switch env-file 持久」的必要後果,E1 註釋已說明理由,judged in-scope)。TODO §5 row 76 已由 PM v127 重寫,SOP 落在 smoke MODULE_NOTE(可接受)。

## 三點指定軸結論(PA §5.3)

1. **隔離性 = PASS**。canary 只 import schema 常數/parser、lazy `one_shot_ipc_call`、flusher 私有鎖函數;0 hub/comparator/5 閘接觸;probe 雙層 2s timeout 有界;例外全收斂為計 fail(雙保險 per-tick catch);`_CANARY_LOCK` 持鎖僅 dict 操作、log 在鎖外;flusher PG I/O 在 executor、不持 comparator lock;main.py wiring 與既有 3 個 task 範式逐字同構,flag-OFF 時協程立即 return(一次性 INFO log,零週期負載);restart_all.sh 僅加 2 個鏡像既有 lease-flag 範式的 env 轉發,`bash -n` 過 + 讀邏輯無控制流改動。50 拍混合故障注入親證 attempts==ok+fail 不變量、in-flight skip 不計數、backoff 方向(600s 配置不被加速到 300s)。
2. **無假綠 = FAIL(2 HIGH,見 findings)**。七支路逐一有咬合(E1 八 mutation 中抽 2 redo 紅→綠;我方 probe B/D2 證 stall floor 與 500 floor 真咬),但兩個 E1 未覆蓋的算術縫隙可在現實觸發鏈下產生 PASS 假綠。
3. **零 mutation 鐵則 = PASS**。canary 真碼 token-strip 0 acquire/release 引用(測試含正向自證非空測,獨立 grep 復核 0 hit);canary 0 PG 寫;V137 writer 只 INSERT;smoke 無 cron/scheduler 接線(grep cron/ + healthcheck/ 0 hit;SCRIPT_INDEX+注釋雙重明文禁);`OPENCLAW_ALLOW_MAINNET=1` 親跑 → REFUSED exit 7(--run --yes 與 dry-run 兩態均拒);默認 dry-run exit 0 零 IPC;--ops 3 → exit 2。

## E1 三項自決偏差裁決

| # | 偏差 | 裁決 | 證據 |
|---|---|---|---|
| ① | smoke profile=Production 非字面「demo profile」 | **ACCEPT** | 親驗 `governance_core.rs:131-133` `requires_lease()` 只對 Production true;`:400-421` `!requires_lease()` → `Ok(LeaseId::Bypass)` 短路不碰 SM(`:1294-1330` 測試同證);bypass wire 哨兵=`{"lease_id":"bypass","outcome":"Bypass"}`(event handler :85-89),smoke 的 `=="bypass"` 比對正確;IPC 路徑 release "bypass" 字串 → 反查 LeaseNotFound(event handler :119),smoke 註釋準確。Validation/Exploration 跑 smoke = 驗不到 mutating arm,E1 結論成立;環境圍欄=mainnet guard(exit 7 親驗) |
| ② | V137 event_type 6 型(PA 草案 4 型 +canary_fail_streak/counter_regression) | **ACCEPT** | PA §3.1 明標「schema 草案」;V129 'canary' row 只有累計 attempts/ok/fail(查 V129 schema 證),散發 vs 連續失敗結構性不可區分 → S3「無 ≥15min 連段」必須事件型;S4 regression 交叉偵測同理。migration 頭部已文檔化理由 |
| ③ | engine_mode 不作環境斷言軸(只驗非空) | **ACCEPT** | 既有語義 Live+LiveDemo 同寫 'live_demo'(2026-04-16 紀錄),值無辨別力;環境圍欄由 mainnet guard 承擔,smoke 注釋誠實聲明 |

## 對抗反問結果(自證;probe 腳本 /tmp/e2_probe_82.py、/tmp/e2_probe_canary.py)

1. Q:probe 全 0 + 50h 窗 gate 會 PASS 嗎? · 證據:Probe B → `FAIL canary stalled: attempts=0 < floor=300` · 結論:停擺支路真咬合。
2. Q:快速 crash-loop 的重複 epoch_rollover 會稀釋失敗率嗎? · 證據:Probe A(30 個 <30s epoch 各攜同一 V129 終值 800/795 + 當前 epoch 60/20)→ **PASS rate=0.9921**,真實 dedup 帳=860/815=94.8% 應 FAIL · 結論:**HIGH-1 假綠成立**。
3. Q:canary 中途死/停擺 48h 收口時會被抓嗎? · 證據:Probe D(510 ok probes=17h@120s 後 31h 全黑,flusher 持續 flush 保 V129 fresh)→ **PASS window=48.0h probes=510 rate=1.0000**;Probe D2(499 probes)→ FAIL 500-floor · 結論:**HIGH-2 假綠成立**——死亡時點在 ~17h 後即收口不可見。
4. Q:同秒邊界(anchor 事件與 FAIL 事件同 created_at)? · 證據:Probe C → fail_streak 與 OFF→ON anchor 同秒被 `ts > anchor` 排除,PASS · 結論:邊界事件歸屬前一(已作廢)窗,語義可辯護;同批 INSERT 共享 PG now() 是真機制,但 prod 觸發需 in-process flag 翻轉(env 進程內不可變)→ LOW。
5. Q:anchor==rollover 時 prev 計數歸屬? · 證據:Probe E → 排除(700 非 1500) · 結論:保守方向(少算),正確。
6. Q:畸形 get_status 變體(1-as-bool/空字串/bool 子類/負 int)全拒? · 證據:canary probe 5/5 rejected,PascalCase 合法值收 · 結論:fail-closed 自身判定成立。
7. Q:serde 大小寫宣稱屬實? · 證據:`GovernanceMode`(governance_core.rs:82-88)/`RiskLevel`(risk_gov.rs:14-23)derive 無 rename_all → wire=PascalCase;dispatch.rs:422 doc 的 UPPERCASE 是 `as_str()` 殘文 · 結論:E1 schema 注釋正確,parser 不釘大小寫是對的。
8. Q:get_status result 是 dict 還是字串? · 證據:`await_governance_reply`(ipc_server/handlers/governance.rs:256-270)把內層 JSON 字串 parse 成 Value 再放 result · 結論:canary Mapping 檢查對真 wire 形狀成立。

## Findings

| 嚴重性 | 位置 | 描述 | 建議修法方向(不代寫) |
|---|---|---|---|
| **HIGH-1** | `checks_governance_lease_ipc.py:469-473`(`[82]` 步驟 9 跨 epoch 求和) | **重複 epoch_rollover 重複計數 → S3 成功率稀釋假綠**。epoch 存活 <30s(死於首次 flush 前)時,下一 epoch 的 rollover 重讀**未刷新**的 V129 → 攜帶與前一 rollover 完全相同的終值。crash-loop(watchdog/systemd 重啟循環,k 次 <30s epoch)產生 k 份相同 prev 計數,`cum += ev["canary_attempts"]` 全數疊加。Probe A:k=30 健康舊值 + 劣化當前 epoch(60/20)→ 計得 99.21% PASS,真值 94.8% 應 FAIL。crash-loop 與管線劣化高度相關(同為壞部署症狀),非獨立巧合;probe floor 同被虛增,與 HIGH-2 複合 | dedupe:rollover 的 `detail.prev_canary_updated_at_epoch_s`(+prev 計數)與已計入者相同 → 跳過(同一底層 V129 快照只計一次);加 regression test:兩個 identical-prev rollover 斷言單次計入 |
| **HIGH-2** | `checks_governance_lease_ipc.py:225-233,493-506`(停擺下限)+ PA §5.3 case 3 | **canary 死(probe 不增長)在 ≥~500 probe 累積後不可偵測**。停擺下限=300s×0.5 安全係數(48h 窗 floor=288);500 floor=16.7h@120s 的量。canary 在 ~17h 後任何時點死亡/長停擺(GC'd task、kill-switch env 被誤關、event-loop 長病後恢復):flusher 照常 flush(V129 fresh,flusher-dead 軸不咬)、無失敗產生(連段軸不咬)、窗照走(時間軸不咬)→ 48h 收口 PASS(Probe D:31h 全黑 PASS rate=1.0000);永久死亡在 48-85h 窗區間全 PASS。PA §5.3.2 四案例之 3「canary 死(probe 數不增長)→ FAIL」在收口時點最關鍵的區域未交付;singleton-registry §2.5.5 health_monitoring 欄「canary 死 → [82] FAIL」宣稱同步過強。E1 已誠實標注此縫隙(0.5 係數+99% 兜底),裁決=PA §4 S3 字面合規但 §3.4 fail-closed 連續性意旨(30min 間隙都重置錨點 vs 中段 31h 黑洞不可見)被擊穿,且擊穿的正是本輪要證的對象(管線持續曝險) | 方向(任選,V137 未 apply 可直接改同檔 CHECK 白名單免 V138):(a) flusher 低頻 heartbeat 事件(如每 6h)攜 attempts,`[82]` 要求窗內相鄰 heartbeat 與 heartbeat→當前快照嚴格增長(48h 僅 +8 row);(b) 等價的 last-probe-growth 時間戳投影軸。同步修 §2.5.5 health_monitoring 宣稱 |
| **LOW-1** | `app/main.py`(804 行) | base 777 + wiring 27 跨過 800 行警戒線(CLAUDE §九) | 按 exact-touch 慣例補 split follow-up 註記(startup wiring 抽離為候選),不阻本輪 |
| **LOW-2** | `checks_governance_lease_ipc.py:449`(`ts > anchor`)+ `governance_divergence_flush.py:305-346` | 同批 INSERT 事件共享 PG `now()`(單 transaction)→ anchor-reset 事件與 FAIL-worthy 事件同批時後者被永久排除(Probe C)。prod 觸發需 in-process flag 翻轉(env 靜態)→ 基本不可達;且 anchor reset 本身已 fail-closed 作廢舊窗,被排除事件歸屬舊窗語義可辯護 | 接受現狀;若修 HIGH-1 時順手:in_window 改 `>=` + 對 anchor 事件自身豁免,或文檔化邊界歸屬語義 |
| INFO-1 | V137 | append-only 僅靠 writer 慣例,無 `REVOKE UPDATE/DELETE`(V054/V129 同無,合本地慣例;PA 未要求) | 可選:加防禦性 REVOKE;不阻 |
| INFO-2 | `checks_governance_lease_ipc.py:324,381` | SQL f-string 內插模組 int 常數(非用戶輸入,無注入面) | 下次觸碰改參數化 |
| INFO-3 | `governance_divergence_flush.py:357-373` | `_current_counts_snapshot` 兩處 `except: pass`(有注釋,prev_* NULL-able by design,fail-soft 契約內) | 接受;可降為 debug log |
| INFO-4 | `main.py:625` | `create_task` 不持引用(與既有 3 處 wiring 同構,非新缺陷;但 task-GC 是 HIGH-2 死亡機制之一) | 修 HIGH-2 時考慮 module-level 引用持有 |
| INFO-5 | `governance_ipc_canary.py:435` | 跨模組 import 私有函數 `_acquire_flusher_leader_lock`(load-bearing 同鎖不變量,MODULE_NOTE+registry+測試三重文檔化) | 下次觸碰 flusher 時導出公開別名 |
| INFO-6 | `dispatch.rs:422` 一帶 | Rust doc 散文 UPPERCASE enum 值為 as_str() 殘文與 serde wire 不符(0-Rust-change 約束內,E1 已在 Python 側文檔化陷阱) | 留待下次 Rust 觸碰修字 |

## 8 條 reviewer checklist

| Item | 狀態 |
|---|---|
| 改動範圍與 PA 方案一致 | PASS(restart_all.sh additive 偏差有理由) |
| 沒有 except:pass 靜默吞 | PASS-with-INFO-3(觀測層 fail-soft 契約內,有注釋) |
| 日誌 %s 格式 | PASS(diff 0 f-string log) |
| 新 API 端點 operator gate | N/A(0 新 HTTP 面,PA 設計如此) |
| except HTTPException 順序 | N/A(無路由改動) |
| detail=str(e) | PASS(0 hit) |
| asyncio 路由 blocking lock | PASS(`_CANARY_LOCK` 微臨界區非路由;PG I/O 全 executor) |
| 私有屬性穿透 | PASS-with-INFO-5(deliberate 文檔化) |

## OpenClaw §3 checklist

| Item | 狀態 |
|---|---|
| §3.1 跨平台路徑 | PASS(diff 新增行 0 hit) |
| §3.2 中文注釋 | PASS(全 diff 中文優先,MODULE_NOTE 齊,why 充分) |
| §3.3 Rust 專條 | N/A(0 Rust 改動,PA 約束) |
| §3.4 IPC 邊界 | PASS(get_status 7 鍵/serde PascalCase/result-dict 形狀全親驗對 Rust 真碼) |
| §3.5 Migration Guard | PASS(Guard A 缺欄 RAISE/條件式 CHECK/Guard C index 驗到位/單 transaction/COMMENT/rollback 註;E1 稱 Linux dry-run 雙跑已做,正式 apply 前仍須 per-SOP 雙跑=owed-Linux) |
| §3.6 healthcheck 配對 | PASS(`[82]` 即是配對;runner 註冊可達,cursor 區塊內真 fire) |
| §3.7 Singleton 登記 | PASS(§2.5.5/§2.5.6 全欄位;§2.5.5 health_monitoring 宣稱隨 HIGH-2 修正) |
| §3.8 檔案大小 | LOW-1(main.py 804) |
| §3.9 Bybit API | N/A |
| §3.10 caller proof | PASS(canary wiring=main.py:625 真排程;`[82]`=runner:1300 真註冊;HIGH-1/2 附 probe 重現非推測) |

## 測試與 mutation 親跑數字

- **242 passed + 2 skipped 復現**(5 檔:canary 53 / flusher 25 / soak healthcheck 35+1s / bridge 68 / hub 61+1s);新 3 檔單獨 113+1s;`[81]` 12 test 保留 0 刪。
- **E1 mutation redo ×2 紅→綠**:①移除 single-flight 守衛 → `test_single_flight_guard_skips_overlapping_tick_without_counting` 1 紅(精準);②移除 flag-OFF 觀測 anchor-reset 支路 → `test_flag_off_observation_resets_anchor` 1 紅(E1 第三棒補強的 belt-and-suspenders 測試真咬)。每輪 cp 備份→還原→`git status --porcelain` 空 + 綠復跑。
- **獨立 probe 6 條**(A-E + canary 不變量組):A/C/D 命中(上表),B/D2/E 證對應支路與保守方向成立。
- bash -n OK;py_compile 7 檔 OK;smoke 三態(guard 7/dry-run 0/floor 2)親跑。

## §5 race check

5a fetch ×2(起審+終審)origin/main=`9a8d9a98` 無變;sibling 窗內 P2p sentinel merge 與本 PR 檔案 overlap 僅 `E1/memory.md`+`SCRIPT_INDEX.md`(docs/index 層,merge 時 SCRIPT_INDEX 頭行會 textual conflict,PM 處理);5b worktree porcelain 空(mutation 全還原親驗);5c 3 條 stash 全 pre-existing 已知不碰;5d 本報告寫主 checkout docs 區,不 commit(PM 鏈);5e review 期間 0 新 sibling push。

## 退回 E1 修復清單

1. **HIGH-1**:`checks_governance_lease_ipc.py` 步驟 9 — 對 epoch_rollover 以 `detail.prev_canary_updated_at_epoch_s`(+prev 計數)去重後再求和;補「兩個 identical-prev rollover 只計一次」regression test(可直接取 /tmp/e2_probe_82.py Probe A 場景縮減版)。
2. **HIGH-2**:probe-growth 連續性證據(方向 (a) heartbeat 事件為佳;V137 未 apply,CHECK 白名單同檔改);`[82]` 加對應 FAIL 支路 + mutation test;同步修 singleton-registry §2.5.5 health_monitoring 宣稱。
3. **LOW-1**:main.py 804 行 — 註記 split follow-up(TODO 或 registry debt 行)。
4. LOW-2/INFO 項自由裁量,不阻 re-review。

re-E2 範圍:fix delta only(HIGH-1/HIGH-2 兩支路 + 對應測試),不重審全量。

## re-E2 2026-06-10 0ce0874c

### Verdict:ACCEPT → PASS to E4(0 阻塞 finding;2 LOW + 3 INFO 不阻)

fix commit `0ce0874c`(疊 `9dc533b0`),diff 恰 7 檔 +549/−32,全在允許清單(healthcheck/flusher/V137/2 test/main.py MODULE_NOTE/singleton-registry §2.5.5-§2.5.6),**0 漂移**。測試環境 `srv/venvs/mac_dev`(3.12)。

### 四項原 finding 全閉(實證非讀碼)

| 原 finding | 結論 | 證據 |
|---|---|---|
| **HIGH-1** dup-rollover 稀釋 | **CLOSED** | 修法=步驟 9 dedup key `(detail.prev_canary_updated_at_epoch_s, prev_attempts, prev_ok)`;`last_rollover_ts` 前移移到 dedup 前(被去重的 rollover 仍推進 epoch 邊界——regression 交叉偵測語義保持,關鍵正確)。**Probe A 重放**:原版(無 hb)FAIL(10b (i) 擋);**A-hb 變體(加合規 heartbeat 隔離算術軸)→ FAIL `success rate=0.9477`/`cum_attempts=860`**=正是上輪 94.8% 真值,稀釋假綠死。key 前提親驗:flusher V129 UPSERT 每輪 `updated_at=now()`(:230-236/:303-309)→ 任何 flush 過 ≥1 次的 epoch 其 updated_at 必異;同 key 僅出現在「死於首次 flush 前」=正是該去重的同一未刷新快照 |
| **HIGH-2** 中段死亡不可見 | **CLOSED** | flusher 30min `canary_heartbeat`(攜程內 canary counters 快照;`_event_payload` 親驗)+`[82]` 10b 四子軸。**Probe D 重放**:原版(無 hb)FAIL((i) 證據鏈缺失);**D-hb 變體(31h 全黑+完整 flat heartbeat 鏈,flusher 全程照發)→ FAIL `did not grow between adjacent heartbeats(510 -> 510)`**=最對抗形態(flusher 盡責、事件新鮮、僅 canary 死)被 (iii) 殺。chain-stop(最新 hb 5h 前)由 (ii) 殺、尾段死亡由 (iv) 殺(G-b 700s/G-c 1700s 親證)。`[82]` 事件 SQL 無 event_type 過濾(heartbeat 必入掃描);全 repo 唯二 V137 消費者=flusher writer+`[82]` reader,無第三者帶 6 型假設 |
| **LOW-1** main.py 804 行 | CLOSED | MODULE_NOTE 債務註記(startup wiring 抽離候選,本輪不拆)=上輪建議的 exact-touch 慣例形態 |
| **LOW-2** ts>anchor 邊界 | CLOSED | 選「文檔化」(上輪二選一之一):步驟 8 注釋完整載歸屬語義+不可達性+保守方向,與實況一致 |

§2.5.5 過強宣稱修正到位:health_monitoring 欄改為 heartbeat 支路語義+誠實標注「修復前宣稱過強」+偵測粒度(30min hb+6h cron,粗粒度兜底=stall floor)——與實作逐句對得上。§2.5.6 補 `last_heartbeat_mono`。V137 同檔加第 7 型合法(未 apply 任何環境,PM 親驗 prod=136+dry-run 重做 PASS;量級註釋 ~700 row 修正一致)。

### 新假綠縫隙自查(brief 指定軸)

- **crash-loop 偽造增長:不可能**。增長斷言只看 attempts counters(僅 `run_canary_tick` 遞增,restart 歸零只會降不會升);時間軸全 DB-side(`created_at DEFAULT now()`+`now()` epoch 同源),app wall-clock 漂移無從偽造;app 端 `time.monotonic()` 僅管 emit 間距(免疫時鐘跳變,E1 注釋正確)。
- **INSERT 失敗不卡死 flusher**:`_insert_soak_events` 全例外吞噬回 False 永不拋(親讀);tracker 不前移→下輪 30s 重試,僅 debug-log 噪音;`_insert_soak_events([])` 回 True 但 `heartbeat_due=False` 不誤前移。M3 mutation(無條件前移)→ `test_detect_heartbeat_retry_after_insert_failure` 精準紅。
- **殘餘縫隙(量化,LOW-B)**:G-a 親證——canary 死後**持續 <30min 重啟循環**(每 epoch 恰 1 條 hb,rollover 重置 (iii) 基線)+ 評估落在最新 hb 600s 寬限內 → PASS。逐讀逃逸率 ≈ 600/重啟週期(29min 循環 ≈34%);讀落 ≥600s 即被 (iv) 殺(G-b/G-c FAIL 親證);連續 k 讀全逃 ≈0.345^k(2 讀 12%/8 讀 0.02%)。前提=雙重病態(canary kill-switch 中途關+小時級 sub-30min 重啟風暴,後者 watchdog+P2p sentinel A2 軸操作面必響)。vs 修復前單一故障即**永不偵測**,定級 LOW 不阻;濾裁交 PM。
- **30min vs ≤1h 裕度算術**:常態成立;對抗對齊極端(hb 後 1799s 重啟+恰 1800s 最大容忍中斷+首輪 ~30s 延遲 ≈3629s>3600)有 ~29s 假 FAIL 窗,方向保守、下一 cron 自癒 → INFO-A。

### Mutation 親跑(全 bite;每輪 cp 還原+`git status --porcelain` 驗空)

1. **M1**(HIGH-1 去重還原)→ 恰 2 紅(`test_probe_a_dup_rollover_dilution_fails`+`test_identical_prev_counted_once_distinct_prev_still_counted`)。
2. **M2**(10b (iii) `<=`→`<` 容持平)→ 恰 1 紅(`test_probe_d_midwindow_death_flat_heartbeats_fails`)。
3. **M3**(flusher tracker 無條件前移)→ 恰 1 紅(retry 測試)。
4. **M1b(over-dedup:key 削 updated_at)→ 44 全綠存活**=LOW-A test-pin 缺口(下節)。

### 新 findings(全不阻 merge)

| # | 嚴重性/信心 | 描述 | 建議 |
|---|---|---|---|
| LOW-A | LOW/高 | dedup key 的 `updated_at` 分量無測試釘:M1b mutant(key 只剩 prev 計數)44 測試全綠;probe F 親證該 mutant 把「真實兩個不同 epoch 同計數(290/290×2,不同 updated_at)」誤去重 590→300 → S3 probes 假 FAIL(false-NOGO)。同計數場景現實可達(等長排程重啟+100% ok)。**現碼正確**(probe F 真碼 PASS `probes=590`) | 後續補一條 probe-F 形 regression(distinct-updated_at-same-counts 計 590);不阻本輪 |
| LOW-B | LOW/高(算術)/中(定級) | G-a 殘餘縫隙(上節量化):雙病態+寬限窗逐讀 ~34% 逃逸,重複讀坍縮 | 文檔化即可或 accept;若要收緊=(iv) 對 attempts=0 的 heartbeat 免寬限(0 拍 epoch 無「剛寫完」誤殺問題) |
| INFO-A | INFO | STALE_MAX=3600 vs 極端對齊 3629s 的 ~29s 假 FAIL 窗(保守向,自癒) | 下次觸碰可改 3700;不阻 |
| INFO-B | INFO | 若任何 DB 曾以 6 型白名單 apply V137 再上新碼:heartbeat CHECK violation 使整批事件 INSERT 連坐失敗+30s 重試循環(其他事件型連帶丟)。現況 moot(V137 全環境未 apply,單一 auto_migrate 路徑上 7 型新檔) | 部署順序意識即可 |
| INFO-C | INFO | commit body「flusher 4 紅」=只計新測試;實際修前紅 5(含改寫的既有 `test_detect_first_observation_is_baseline_no_event`)。計法一致非 overclaim(healthcheck 7/9 同規則) | 無需動作 |

### 親跑數字

- 全套 5 檔 **256 passed + 2 skipped** 復現(基線 242+2;healthcheck 35→44=+9、flusher 25→30=+5、`git diff | grep -cE '^\+\s*def test_'`=14 算術守恆)。
- **修前紅親證**:兩生產檔 checkout 回 `9dc533b0`(保新測試)→ healthcheck 恰 7 紅 + flusher 5 紅(=宣稱 4 新+1 改寫);還原後 256+2 綠、`py_compile` 3 檔 OK。
- 獨立 probe 9 條:A-orig/A-hb/D-orig/D-hb/F/G-a/G-b/G-c(+G 首版構造 bug 自糾:while-loop 產未來時間戳亂序——合成事件必須遵守 ORDER BY created_at 遞增,修正後 G-b 由 (iv) 正確殺)。
- 衛生 grep:diff 0 硬編路徑/0 f-string log/0 except-pass;新注釋全中文優先含 why。

### §5 race

5a/5e fetch ×2 origin/main=`9a8d9a98` 全程無變(0 sibling push);5b/5d worktree porcelain 空(mutation 逐輪還原親驗);5c 3 條 pre-existing stash 未動。

**re-E2 verdict:ACCEPT → PASS to E4。**
