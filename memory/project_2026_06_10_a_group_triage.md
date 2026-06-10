---
name: a-group-triage-2026-06-10
description: 2026-06-10 PM 接手 A 組排程 triage:OPS-2 cutover 證據達成+E1 派工、A-1/B 複查、AC19 final verdict、TONUSDT watch 關閉、P5-SM soak 監測重設計(PA S1-S5 gate)、MEMORY.md 壓縮治理
metadata:
  type: project
---

2026-06-10 PM 接手 TODO(權威=origin/main v121,本 branch v119 已 stale 兩版),跑完當日到期 A 組四項+memory 治理+三端同步,TODO 升 v122。

**A1 OPS-2 Phase-2 cutover = 證據達成,E1 已派**:engine.log(238MB)+api.log `ops2_secret_split_phase1_fallback` grep = 0。誠實 caveat:log 被 06-03/06-07/06-08 三次 restart 截斷,「14d 連續 log」不可從現存檔重建;判定依據=3 個獨立 restart 窗(每次全量重讀 env)全 0 WARN+fallback 若觸發是 24/day rate-limited 結構性信號、非縫隙事件。E1 在獨立 worktree branch `fix/ops2-phase2-cutover` 移除 fallback+陳舊 panic/reason 變體(env 缺失改 fail-loud),完成後須走 E2→E4 鏈,merge/deploy operator-gated。

**A2 P0-EDGE-1 A-1/B 複查**:A-1=bb_breakout 7d fire 4 次無異常→維持 QA preventive re-scope,關閉;B=`market.regime_snapshots` 仍 0 rows+`trading.intents.details` hurst key 0(all-time,938832 rows)→INCONCLUSIVE 維持,唯一正面證據路徑=`P1-BB-REVERSION-REGIME-OBSERVABILITY`(bb_reversion 7d 12 intents,持久化一落地樣本即流)。`research.aeg_regime_labels` 也是 0 rows(V127 表在未 populate,regime runner 至今 artifact-only)。

**A3 過期 triage 全清**:AC19 14d bucket-split(欠 8 天)=alt **FAIL**(42 attempts/fill 23.8%/Wilson lower 13.5%/28 timeout→taker)、large_cap n=9 INCONCLUSIVE-LOW-N;QA final verdict 報告 `docs/CCAgentWorkSpace/QA/workspace/reports/2026-06-10--ac19_alt_bucket_14d_final_verdict.md`;後續(alt taker-direct/縮 timeout/維持)屬 PA/QC+operator。TONUSDT watch 關閉(live_demo cell n=6/shrunk −7.72bps,較設 watch 時 −31.23 改善,insufficient_samples,QC verdict C 維持)。C10 funding=moot 歸檔(funding_arb 已不在 demo risk_config)。WORKFLOW-F-D7 轉條件制(R4 下次 doc audit)。BBO-V094 併入 [74]/AC19 證據面(close_maker 全期 93 attempts,post-0602 +35)。

**A4 P5-SM soak 監測重設計(PA 報告 `docs/CCAgentWorkSpace/PA/workspace/reports/2026-06-10--p5sm_soak_observability_redesign.md`)**:
- **狀態校正**:06-03 已落一輪 gate rework(`b904125f`→`87047e32`→`b847ae28`:V129 PG 投影+30s flusher+`[81]` P-LIVE healthcheck;operator 拍板 (b)+(b-i) comparator 降觀測信號非 gate;EQUIV sampler 建後同日棄;`governance_divergence.py:33` gate 公式=stale docstring)——TODO v121 該 row 整條過期,v122 已重寫。
- **真缺口=Python→IPC→Rust 生產管線零 runtime 曝險**(P-LIVE 不經 IPC arm、4a 是離線 parity;shadow 默認 SHADOW_BYPASS hub.py:990-1001 短路→organic 流量對 comparator 貢獻恰=0)。
- **設計鐵則(雙邊比對死因)**:Rust per-pipeline 自動授權 vs Python hub-level 授權=兩個獨立狀態實例→雙邊 divergence 結構性不可達,canary 驅動亦永久卡死。任何人再提「重建雙邊 divergence gate」先讀這條。
- 新 gate=S1-S5(4a CI+`[81]` P-LIVE+唯讀 IPC canary 48h/跨 epoch ≥500 probe/≥99%+flag/epoch 完整性+operator 收口 smoke N≥10);flag 持久化機制其實已在 `restart_all.sh:717`(`basic_system_services.env`),前兩次 soak 都沒用=SOP 缺口非機制缺口。E1 規模 5 task/3 wave,~1100+750 LOC,0 Rust/0 live-auth。

**Runtime 快照**:intents 流到 06-09 19:19(total 938832);7d intents=grid 243/ma 130/bb_reversion 12/bb_breakout 4;demo alive。Mac→GitHub 直連恢復(fetch+push 親驗,bundle 流程退役);Mac main ff→`28e376c0`=origin=Linux。

**Why**(教訓):①psql `2>/dev/null` 會把 ORDER BY 越界等 SQL error 靜默吞掉——「7d 0 intents」是這樣的誤報,靠 max(ts) 交叉驗證抓回;聚合查詢必須帶一個獨立交叉檢核。②派 PA 前我的 brief 本身 stale(06-03 gate rework 已落地我不知道)——PA 設計任務必須要求「先親驗代碼現實再設計」,本次 PA 正確推翻 brief 四處。③log 證據會被 restart 截斷:依賴「N 天連續 log」的 soak 判準,要在設計期就規定 log 留存或改用 DB 帳本(PA 的 epoch ledger 正是解這個)。
**How to apply**:OPS-2 cutover 鏈下一步=E1 完成→E2→E4;AC19 決策排 PA/QC;P5-SM 下一步=operator 審 PA 設計→E1 5-task wave;L2 線歸 L2_TODO(該 session 活躍中,P3b 已 commit `24d049fc`)。relates [[project_2026_06_01_rust_python_boundary_simplification_audit]] [[project_2026_06_03_v58_archive_audit_s2_design]] [[feedback_evidence_discipline_under_degraded_tools]]
