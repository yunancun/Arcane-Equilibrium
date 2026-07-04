# 2026-07-03 冷酷對抗審計 — Stage 3 Validated Fix Plan(PA 驗真層)

> 主會話(conductor)親做 PA 層。凍結基準見 [baseline 報告](../../../PM/workspace/reports/2026-07-03--cold_audit_baseline.md):Mac/origin `d68a1329`,Linux checkout `262596c6`。
> Stage 2 run `wf_6dc68c2f-4a0`,101 agents,7.475M subagent tokens,42 min。原始軸報告見 workflow 返回 report_paths(各 agent workspace)。

## 0. 可信度聲明(必讀,誠實報告)

本輪 Stage 2 有兩處降級,影響範圍已標定:

1. **conductor 調用失誤**:args 以 JSON 字串誤傳,腳本未收到 baseline/focus/axes 注入 → 實跑默認 10 軸(**E4/TW 兩軸缺席**),各軸按 role SOP 全量基準審計(SOP 已含 07-03 裁決座標校準,over-gate/token-稅視角未丟失),但劇本靶向 focus 未注入、affected-line 未錨定凍結 SHA。
2. **月度 spend limit 於 Verify 段中途觸頂**:30 個質疑者(A3/E5/R4/AI-E 四軸全部 + 部分)未跑,按法定人數=2 規則這四軸 C/H finding 全部降 **disputed**(未靜默 confirmed——設計正確運作)。**disputed≠被駁倒**,其中 8 條已由本 Stage 3 主會話親自取證翻案(見 §2)。
3. **A3/R4 報告檔未落盤**(spend limit 波及):兩軸原始 finding 完整保存在 Stage 2 raw result(`PM/workspace/reports/2026-07-03--cold_audit_stage2_raw_result.json`),本 plan 引用處以該檔為證據正本。
4. **補救路徑**:spend limit 解除後可 `Workflow({scriptPath, resumeFromRunId:"wf_6dc68c2f-4a0"})` 廉價補跑缺票質疑者(已完成 agents 走 cache);E4/TW 兩軸另派小規模補審(估 <1M tokens)。

覆蓋結論:10 軸產 143 findings(40 C/H),confirmed 18 / disputed 18 / latent 4 / seam re-probe 12 / assumptions 93。E4 測試盲區、TW 文檔去重兩個視角本輪**零覆蓋**,列入下輪 focus。

## 1. Stage 3 主會話親證結果(runtime + 源碼定向取證)

以下逐條為主會話 2026-07-04 親自取證,證據等級 FACT:

| # | 原 finding(軸/級) | 親證結果 | 證據 |
|---|---|---|---|
| V1 | E5/R4-HIGH TODO.md 超 Read cap | **CONFIRMED** | 實測 233 行 / 129,772 bytes ≈59k tokens,超 25k cap |
| V2 | E5-HIGH 13 檔破 2000 行 vs CC 報 9 檔 | **雙方皆對,seam #9 收口** | git-tracked >2000 = 13 檔;排除 4 個測試檔 = 9 個生產檔。權威清單:discovery_loop.py 5954 / runtime_runner.py 4500 / profitability_path_scorecard.py 3789 / fill_sim.py 2796 / engine_watchdog.py 2412 / commands.rs 2266 / status.py 2238 / step_4_5_dispatch.rs 2193 / intent_processor/mod.rs 2032(+4 測試檔) |
| V3 | A3-HIGH mode-tag 硬編碼 | **CONFIRMED** | `console.html:183` 硬編碼 `shadow_only`,全部 JS 零引用 `mode-tag`,無任何更新路徑 |
| V4 | A3-HIGH 緊急停止=停止Live 同 endpoint | **CONFIRMED(定性修正)** | `tab-live.js:1065` 與 `:1093` 同打 `/api/v1/live/session/stop` 空 body。server 端兩者都做撤單+平倉+撤授權;緊急 modal 額外承諾「封鎖引擎需手動解除」僅部分由 `_LIVE_USER_STOPPED`+EA-PERSIST 承載,「與普通停止不同」的語義是假的 |
| V5 | FA-HIGH crontab 70→5 | **CONFIRMED** | `crontab -l` 實測 5 條非註釋行,全為 cost_gate/demo_learning 族;engine_watchdog、passive_wait_healthcheck、bybit_announcement_sentinel、edge_label_backfill 等全部不在 |
| V6 | FA-HIGH 學習 SSOT 在 /tmp | **CONFIRMED** | 5 條 cron 全帶 `OPENCLAW_DATA_DIR=/tmp/openclaw`;logs 亦在 /tmp/openclaw/logs |
| V7 | FA-HIGH expected-head pin stale | **CONFIRMED+量化** | 全部 pin `00a78d92`(2026-06-30),距 Linux HEAD **422 commits** |
| V8 | E5-HIGH PG 出廠默認 | **CONFIRMED** | `shared_buffers=128MB`,`effective_cache_size=4GB`,cache hit **62.40%**(E5 報 62.38 同源);PG 在 docker `trading_postgres`(up 13d),非裸機 |
| V9 | AI-E-MED l2_call_ledger 表不存在 | **CONFIRMED** | `to_regclass('agent.l2_call_ledger')` = ABSENT |
| V10 | MIT-HIGH G3 drift lane 凍結 | **CONFIRMED** | `features.online_latest` max(updated_ts_ms) = **2026-05-06 00:39** |
| V11 | FA/AI-E AI 治理 30d 零調用 | **CONFIRMED** | `agent.ai_invocations`:30d=0,全史=2 |
| V12 | AI-E-HIGH cost_edge 原則13 雙腿 dormant | **CONFIRMED** | 三環境 TOML `[cost_edge] enabled=false` + `budget_config.toml cost_edge_max_ratio=100.0`(永不觸發) |
| V13 | R4-HIGH PM memory 4352 行 | **CONFIRMED** | wc -l 實測 4352 |
| V14 | BB-MED live_demo 憑證 env fallback | **CONFIRMED(代碼級)** | `bybit_rest_client.py:178 _resolve_credentials` 以 `is_mainnet` 判斷;live_demo slot 仍走 env fallback,與 Rust live-slot 禁令語義漂移 |
| V15 | A3 「runtime 落後 164 commits」 | **方向對,數字修正** | 運行中 uvicorn(4 workers)自 **06-30** 起跑,對應 00a78d92 世代;源碼已前進 **422 commits**。`d0eeafb41` drift-gate 修復**不在運行進程內** |
| V16 | seam #1 running binary ≠ checkout | **升級為 P0-1(見下)** | 主機無 openclaw_engine 進程、無 binary、bybit_connector 容器=alpine 心跳空殼(03-11 建)、worker maps 無 openclaw .so;**但 trading.fills 最新寫入 2026-07-04 07:21(30d 1268 筆,unattributed 15 筆)**——訂單/fill 寫入者身份不明 |

## 2. Validated Fix Plan(confirmed-only;P 級=CRITICAL→P0/HIGH→P1/MEDIUM→P2/LOW+INFO→P3,同級內按淨貢獻 tiebreak)

### P0(生存/審計不可逆風險,先於一切)

**P0-1 RUNTIME-EXECUTION-IDENTITY — 運行時執行身份與代碼世代失控**(升級自 seam #1 + A3/CC/V15/V16;dt=drift-source-runtime,lineage-gap;觸原則 1「單一受控寫入口」與 8「可重構可解釋」)
- 事實:fills 持續產生(今晨 07:21)但無獨立引擎進程/binary/PyO3 映射可指認寫入者;運行棧世代=06-30(00a78d92),落後 422 commits;07-03 的 drift-gate 修 `d0eeafb41` 未生效於任何運行進程 → **v739 若不重啟,實走的還是死循環世代的代碼**。
- 修復:①CC+MIT 帶證據確立「當前下單/寫 fill 的具體進程與其 code SHA」(lsof/proc 級證據,read-only);②受控重啟(restart SOP,bind-host 教訓 `feedback_restart_bind_host_default`)把運行棧對齊凍結後的 HEAD;③重啟時同步更新 cron EXPECTED_SOURCE_HEAD pin(併 P1-4);④建立「運行進程 SHA」可觀測面(啟動時寫 build/boot SHA 到 PG 或持久 log),杜絕本類問題再犯。
- owner:PM→(取證)CC/MIT→(重啟決策)**operator**→E1→E4;驗收:運行進程可指認+SHA=重啟時 HEAD+v739 實走 d0eeafb41 判準。**重啟時機需 operator 拍板**(交易活躍中)。

**P0-2 CRON-MASSACRE-RECOVERY — 06-27 crontab 置換的監測自盲與學習斷供**(FA/MIT/BB/AI-E 四軸切片 + seam #3;V5 親證)
- 事實:70→5 行,倖存者全為 cost_gate/demo_learning 族;被殺者含 passive_wait_healthcheck(90+ 檢查)、engine_watchdog、bybit_announcement_sentinel(25 pinned symbols 的 delisting/maintenance watch 停擺 7 天,**從 latent 升格:這是進行中的實際暴露**)、edge_label_backfill、canary_audit_pg_writer、kline truth-drift(V141)等 ~30 條;無 mutation 紀錄、無作者、無意圖標註(DOC-06 缺口,CC 條併入)。
- 修復:①FA 還原 06-27 前 crontab 全文(備份/shell history/log 交叉),逐條分類「有意退役/誤刪/superseded」;②先行快速恢復無爭議三條:bybit_announcement_sentinel、passive_wait_healthcheck、engine_watchdog(若 P0-1 判定引擎形態已變則 watchdog 對象隨之調整);③恢復清單全量交 operator 批;④補 mutation 紀錄治理規則(crontab 變更須留檔)。
- owner:PM→FA(對帳)→operator(批)→E1(裝回)→E4;驗收:每條被刪 cron 有處置標註;三條快恢復 lane 有心跳。

**P0-3 SSOT-ON-VOLATILE-TMP — 學習 SSOT 與治理證據在 boot-volatile /tmp**(FA-HIGH;V6 親證;dt=lineage-gap;審計可追蹤性支柱的不可逆損失類)
- 事實:`OPENCLAW_DATA_DIR=/tmp/openclaw`,學習 ledger、治理證據 artifact、全部 cron log 都在重啟即滅、30d age 清理的路徑上。
- 修復:遷移至持久路徑(建議 `~/BybitOpenClaw/var/openclaw` 或掛 NAS),cron env 與消費者同步改;歷史 /tmp 現存 artifact 先行搶救性拷貝(read-only cp,不動原件);補每日備份。目標路徑需 operator 確認。
- owner:PM→E1→E4;前置:先做搶救拷貝(可即刻,零風險)。

### P1(HIGH confirmed)

| ID | 內容 | 淨貢獻/計價 | owner 鏈 | 驗收 |
|---|---|---|---|---|
| P1-1 | **over-gate 複合體**:standing envelope TTL 12h 殘留側(QC)× plan-stale × exact-head pin 死循環(FA)× exact-sha 批准循環(CC)。v710-v738 拒真率 100%,零 probe outcome,已授權 Demo 自主迴圈被自家 gate 凍結 28 輪 | 負淨貢獻 gate:避免虧損≈0(Demo)、誤殺=全部學習流、摩擦=每輪 refresh 人工介入。**Demo 放寬/Live 收緊政策適用,live 5 gates 不碰** | PM→PA(統一設計,禁零敲碎打)→E1→E2→E4;QC 驗淨貢獻翻正 | v739+ 連續 3 輪無人工介入通過或按真判準 fail-close;與 P0-1 重啟綁定同批 |
| P1-2 | QC:反事實 markout fill-at-signal-price + cost_bps=4.0 平價假設,污染 probe evidence(replay-misuse;v739 起的 promotion 證據面) | 學習證據誠實性;修不貴 | PM→QC(給保守成本模型)→E1→MIT 驗 | 反事實成本 ≥ 同 cell realized cost 分位保守值;回填標記歷史高估 |
| P1-3 | MIT:訓練集 99.9% 合成 0.0 reject label(V17 派生);quantile/scorer lane 永久 degenerate | evolution-blocker 主幹 | PM→MIT(label 方案)→E1→MIT/E4 | 重訓後 label 分布非退化;acceptance report 含 label 溯源 |
| P1-4 | MIT:G3 drift lane 全鏈 no-op,`features.online_latest` 凍 05-06(V10);cron pin stale 422 commits(V7,與 P0-1 重啟合併執行) | 漂移偵測=風控腿;現為擺設 | PM→E1(feature_tx 接非 paper pipeline)→MIT 驗 | online_latest 持續更新;pin 隨部署自動派生非手寫 |
| P1-5 | E5:PG 出廠默認 128MB/62.4% cache hit(V8)+ MLDE QueryCanceled(seam #8 同根候選) | 便宜大杠杆:一次調參救 MLDE lane+全庫查詢 | PM→E5(調參方案:shared_buffers 4-8GB per hardware doc、pg_stat_statements 開)→operator 批(需重啟 PG 容器)→MIT EXPLAIN 驗 MLDE 查詢 | cache hit>95%;mlde_shadow_advisor 連續 3 日零 QueryCanceled |
| P1-6 | BB:字典 §4.1 rate-limit erratum 第三輪未修(SSOT 毒化所有讀字典的 agent) | token 稅+錯誤決策源;修=改文檔 | PM→BB 供正表→TW 落檔 | 字典與官方 per-endpoint 模型一致,內部矛盾清零 |
| P1-7 | TODO.md 59k tokens 超 Read cap(V1;E5/R4 同錨合併)+ PM memory 4352 行(V13)等 6 檔 memory 超標 | **token 稅最重單項**:每 session 每 agent 都在繳;agent 讀不到 Active Queue=調度盲 | PM→R4(按 todo-maintenance 歸檔方案)→PM 執行 | TODO.md <25k tokens;PM memory <限;歸檔守恆(內容移 archive 不刪) |
| P1-8 | seam #12:06-30 cutover 後 Rust↔Python 內側契約 vs contract test 覆蓋,零流量掩蓋錯配;v739 首批 fill 將行經未測路徑 | v739 前置閘;E4 缺席本輪的最大殘留風險 | PM→BB(cutover diff 盤點)→E4(補測)| v739 放行前:新/變更 message 型別 100% 有 contract test |
| P1-9 | A3 GUI live-ops 對:緊急停止語義修正(V4)+ mode-tag 假資訊(V3) | live 操作面誠實性;修便宜(改 modal 文案/接真值或移除 badge) | PM→E1a→A3 驗→node --check | 緊急停止 modal 承諾=後端實際行為;mode-tag 接真值或刪除 |

### P2(MEDIUM confirmed / 高價值 PLAUSIBLE;按淨貢獻排序)

1. **P2-1 憑證判準對齊**:`_resolve_credentials` `is_mainnet`→`is_live_slot`(V14;LiveDemo 按 Live 標準之 operator 政策)。E1+E3 驗;live 邊界類優先。
2. **P2-2 cost_edge 原則13 雙腿 dormant**(V12)——**需 operator 決策**:AI 調用現≈0,實際暴露≈0,但鐵則 dormant=治理漂移。建議:demo advisory 腿 arm(enabled=true 純建議),budget ratio 100.0 收斂至設計值;live 不動。
3. **P2-3 觀測雙開關**:`OPENCLAW_AGENT_EVENT_STORE_ENABLED` 默認 OFF(latent→一個 env var 之遙)+ DOC-08 daily_usd_max Rust 側無 enforcement 腿(latent;AI 復用前必須先閉)。與 P2-2 同批。
4. **P2-4 unattributed fill lineage 中段追蹤**(seam #4;30d 15 筆進行中):MIT 取 3-5 筆 fill ID 全鏈路追蹤,判定是否污染 decision_outcomes/訓練表。
5. **P2-5 授權四表示法一致性**(seam #5):E3 同刻四方快照(authorization.json/Rust/Python gate/GUI),審傳播時滯 fail-open 窗口。
6. **P2-6 fake-success 93 endpoints 全量掃**(seam #6):E3+A3 判準(後端實際 effect vs 前端成功語義);Risk Governor override ok:true 一例已具體錨定(PLAUSIBLE,掃描中一併核)。
7. **P2-7 bounded probe n=2 power≈8%**(QC):evidence ladder 統計功效重設計;與 P1-1 同批進 PA 設計。
8. **P2-8 best-of-K 無多重比較控制**(QC):headline 上偏;promotion 證據面方法論修正,與 P1-2 同批。
9. **P2-9 l2_call_ledger migration 溯源**(seam #11;V9 表 ABSENT 已證):MIT 判「從未寫/寫了未 apply/有意留空」,三種結論修法不同。
10. **P2-10 token 稅精簡批**:2000 行 13 檔權威清單(V2)按讀改頻率排序(status.py/commands.rs/step_4_5_dispatch.rs 熱檔優先,discovery_loop 等 research 冷檔降級);cost_gate_learning_lane 87 檔重複邏輯(_authority_preserved ×32)提公共 lib;research 356 檔補 active/stale 歸檔機制。E5 主導,**report 先行、動碼需 operator 批**。
11. **P2-11 V 系遷移衛生**:V142-144 Guard A 註釋不誠實(MIT)+ V141 kline guardrail 雙盲(cron 未裝×哨兵停擺,與 P0-2 綁定);linucb arms=0 回 ok 假成功。MIT→E1。
12. **P2-12 sizing 語義混雜**(QC):per_trade_risk_pct fraction/percent 混雜+dynamic_sizing band 無交叉驗證——**需 operator 決策**(觸風險參數,按 `feedback_risk_changes_scoped` 只改被批准範圍)。
13. **P2-13 Layer2CostTracker 4-worker 無鎖共寫 JSON**(AI-E;dormant 但 AI 復用前必修)。

### P3(LOW/INFO + 文檔批)

- 文檔/索引批(R4 5 條:L2_TODO 斷鏈、DOC-05 缺席、README tabs 漂移(A3 同錨)、document_index 零 2026-07 條目、R4.md 審計目標 stale)+ FA SPECIFICATION_REGISTER 模組欄漂移 + CC DOC-06 runtime mutation 紀錄規則 + AI-E 報告索引幽靈(06-13/14 報告全史不存在)。TW/R4 一批清,[skip ci]。
- BB rpiTakerAccess:**移入機會清單**(非缺陷;正淨貢獻機會,BB 已裁安全,maker 費率面;交 opportunity-cost 節)。

### 被駁回/重校準(rejected-unproven / recalibrated)

- A3「164 commits」→ 實測 422(方向對,量錯;不影響結論成立)。
- A3 緊急停止「完全 fake」→ server 端確實平倉撤單;假的是「與普通停止不同」的差異化承諾(V4 定性修正)。
- CC 9 檔 vs E5 13 檔矛盾 → 無矛盾,filter 口徑差(V2 收口)。
- BB「哨兵停擺」原判 latent → **升格 active**(crontab 親證缺席,暴露進行中)。
- 其餘 10 條 disputed(MLDE 衰減 83%、Cloud L2 key 錯位、AI-E 報告 lineage、E5 1m 指標重算、README tabs 等)= **quorum-missing 未驗**,非被駁倒;resume 補票或下輪覆核,暫不入 fix 隊列(README tabs 除外——R4 獨立同錨,升 P3 文檔批)。

### 需 operator 決策清單(未批前禁動手)

| # | 決策 | 綁定項 |
|---|---|---|
| D1 | 受控重啟時機與範圍(uvicorn 棧對齊 HEAD;交易活躍中) | P0-1/P1-1/P1-4 |
| D2 | cron 恢復清單批准(FA 對帳後) | P0-2 |
| D3 | SSOT 遷移目標路徑 | P0-3 |
| D4 | PG 調參窗口(需重啟 PG 容器,~分鐘級) | P1-5 |
| D5 | cost_edge demo advisory 腿 arm 與 budget ratio 收斂 | P2-2 |
| D6 | sizing 語義修正範圍 | P2-12 |
| D7 | token 稅精簡批動碼授權(report 先行) | P2-10 |
| D8 | spend limit 解除後:verify resume + E4/TW 補審(估 <1.5M tokens) | §0 |

### 並行/序列化與 session 拆分

- **可並行**(read-only/互不相交):P0-2 FA 對帳、P0-3 搶救拷貝、P1-2/P1-3 方案設計、P1-6 字典、P1-7 TODO 瘦身、P2-4/5/9 re-probe、P3 文檔批。
- **必序列化**:P0-1 取證 → D1 重啟 → P1-1 over-gate 統一設計 → P1-4 pin 派生 → v739 實走(P1-8 contract test 須在 v739 放行前完成)。
- session 拆分建議:①P0 批(取證+對帳+搶救);②重啟+over-gate 批(D1 後);③學習證據面批(P1-2/3 + P2-7/8);④token 稅/文檔批(獨立 session,防 compact)。

### Latent debt 紀錄

- AI-E DOC-08 enforcement 腿、event store 開關(P2-3 已列,AI 復用前為閘)。
- FA E2E-1 L2 真模型調用驗證缺口(承 [[project_l2_mesh_arc]],追蹤 row 已被 v530 刪——本輪再證其 open,P2-3 併)。
- E5 layer2_tools 3/4 SearchProvider 同步阻塞(0 prod caller,dormant)。

### 附錄:待證假設(不入 TODO)

assumptions 93 條(CC10/FA10/E3 5/BB9/QC11/MIT10/AI-E9/E5 10/A3 9/R4 10)與 seam #2(GUI↔engine↔TOML 三方對表)、#7(vacuous PASS 分母標記)留檔各軸報告;下輪 focus 回流。

---

# Addendum v2(2026-07-04 補票 + E4/TW 補審收斂)

## A. 證據面補全帳

1. **Verify 補票**(resume `wf_6dc68c2f-4a0`,2.08M tokens):30 張缺票補齊,disputed 18→1,confirmed 18→34;16 條轉正**與 §1 主會話手工判定零矛盾**。唯一殘留 disputed = AI-E cost_edge 原則13 條——事實面(雙腿 dormant)已由 V12 親證,爭議僅在「是否構成原則違反」的解讀 → 維持 P2-2 operator 決策項。
2. **E4/TW 補審**(`wf_63ba9216-071`,補丁腳本 focus/baseline 注入生效,1.67M tokens):25 findings,7 confirmed 全票,0 disputed。報告:E4 `2026-07-04--e4_test_matrix_blindspot_audit.md`、TW `2026-07-04--tw_full_audit_doc_dedup_comment_governance.md`。
3. A3/R4 報告檔已由 conductor 代落盤(出處=raw result,檔頭有聲明);正本腳本 `openclaw-full-audit.js` 已補 args-parse guard(字串 args 靜默降級缺陷根修)。
4. 三輪合計實耗:7.475M + 2.082M + 1.673M = **11.23M subagent tokens**,220 agents。

## B. P0-1 事實修正(evidence discipline,誠實糾錯)

原 P0-1 稱「主機無引擎進程/binary,寫 fill 者不可指認」——**該子claim 錯誤**,根因是 conductor 取證失誤:①pgrep/find 用底線名 `openclaw_engine`,實際 binary 為連字號 `openclaw-engine`;②`ps | head -6` 被 uvicorn 6 進程佔滿截斷了引擎行。E4 F9 抓出,已用正確名複核:

- 引擎進程存在:PID 2368227,`rust/target/release/openclaw-engine`,36.1% CPU / 2.5GB RSS。
- 啟動於 **2026-07-03 03:02:41** = CC 所報「無 mutation 紀錄的 runtime 重啟」即此;重啟**未 rebuild**。
- binary build **2026-06-29 19:28** → 運行世代比 cron pin(00a78d92,06-30)更老;`d0eeafb41`(07-03)與 IMPL-A/IMPL-B(已測未部署,E4 F9)均不在線上。

**P0-1 改述**:執行身份已指認(引擎+uvicorn 雙棧),缺陷收斂為「**運行世代失控 + 重啟不 rebuild + 無 build-SHA 可觀測面**」:engine=06-29 build、uvicorn=06-30 世代、HEAD=07-03,重啟這一 mutation 本身無紀錄。修復動作不變(受控重啟需 **--rebuild**、pin 隨部署派生、boot SHA 落 PG/持久 log),acceptance 補「重啟後 `openclaw-engine` binary mtime≥部署時刻且 build SHA=部署 HEAD」。D1 依然是 operator 先決。
（memory `build-SHA≠git-commit` 教訓第三次應驗;另 F2 之 36% CPU/2.5GB RSS 直接歸因 P1-10 ledger 全量重讀,重啟前後應對照。）

## C. E4/TW 增量併入(7 confirmed)

- **P1-8 擴充(主體實錘,v739 前置不變)**:F1 跨語言契約**零 golden-vector parity test**(plan envelope/ledger 行/order_link_id+FNV lineage hash/AdmissionConfig 全部雙實現各自自洽)+ F3 plan 檔路徑 env-override 不對稱→**runtime 雙 plan 檔分裂實錘** + F8 `candidate_matched_demo_fills` 無 in-repo producer(fills→promotion 證據鏈斷點)。owner 鏈改:PM→E4(fixture 設計)+BB(cutover diff)→E1→E4。
- **新 P1-10**:probe_ledger.jsonl 無界成長(472MB/388,798 行)+雙寫者兩側全量重讀,零 rotation/retention/scale 測試;直接吃掉引擎 36% CPU/2.5GB RSS(F2)。與 P0-3 遷移同批設計(rotation+retention+增量讀)。
- **新 P1-11**:1m 指標每 tick 無條件重算(補票轉正 E5 HIGH;PERF-1 只做了 5m 半邊)。E5→E1,熱路徑 SLA 驗收。
- **P2 增**:F5 `BYBIT_MODE`/`BYBIT_CONNECTOR_WRITE_ENABLED` 零 runtime 強制消費者(治理語義純表示層,missing-gate);F6 soak withhold/Indeterminate 無哨兵消費者(over-gate 誤殺不可觀測;latent 但機能類不降級);F7 markout exit 無 max-delay 上界(併 P1-2 方法論批);TW 兩條 HIGH:SCRIPT_INDEX.md 巨型 changelog 劣化(229 段)、Codex 直駕代碼注釋治理(中文優先+MODULE_NOTE)整體未執行(stock_etf 41+ 模塊)→ 併 P2-10/P3 文檔治理批,owner TW。
- **P3 增**:F10 engine_mode 正規化不對稱、F11 四段版 order_link_id 校驗零 caller(dead-code)、F14 probe_outcome 未與真 fill 對賬(admitted-but-unfilled 同權)。
- **P0-2 補充**:F12 證 4/5 cron pin stale 外加**兩個 cron log 0-byte**(head-gated cron 實際行為未驗)——對帳範圍含 log 產出驗證。

## D. 收斂後隊列總覽

P0×3(P0-1 已修正表述)/ P1×11 / P2×15 / P3 文檔+小項批。operator 決策 D1-D8 不變,新增 **D9:probe_ledger rotation 策略**(與 D3 同一討論)。quorum 完整度:40 C/H + 7 補審 C/H 全部雙質疑者(高危類三)全票;唯一 disputed=cost_edge 解讀,已隔離為決策項。
