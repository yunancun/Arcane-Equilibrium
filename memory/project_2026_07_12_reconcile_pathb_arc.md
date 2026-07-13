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
- **DATA_DIR durable fix**(systemd unit/profile export)。
- 設計正本:`srv/docs/execution_plan/gui_redesign/reconcile_pathB_design.md`(v1+§v2)。相關:[[project_2026_06_08_phantom_position_fill_fix]](同 paper_state/apply_fill 唯一 mutator/reconciler 軸)。
