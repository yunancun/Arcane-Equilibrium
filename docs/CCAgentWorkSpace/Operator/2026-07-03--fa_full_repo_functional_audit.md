# FA 全倉功能審計 — 2026-07-03

Bound role: FA（Functional Auditor）· skill: spec-compliance
Scope: srv/ 全倉（rust engine / control_api / GUI / helper_scripts / .claude / 治理文檔）+ ssh trade-core read-only runtime 證據
Mode: read-only audit。無修復、無 runtime mutation、無 PG 寫入、無 auth 觸碰。
Baseline: Mac source head `d68a13298`（=GitHub origin/main, 07-03 11:54 CEST）；runtime head `262596c69`（clean, HEAD==runtime origin/main, 落後 GitHub 3 commits, 線性無分叉）；engine PID `2368227`（07-03 ~03:05 CEST 啟動, `OPENCLAW_ALLOW_MAINNET=0`, `OPENCLAW_DEMO_LEARNING_LANE_WRITER=1`）。

## Verdict: FINDINGS（無 BLOCKER 級硬邊界違反；2 HIGH 級功能斷鏈 + 1 HIGH 級 over-gate）

---

## 一、業務鏈完整度（分段沿用 e2e-integration-acceptance 正本拆法）

| 環節 | 評分 | 證據（07-03 runtime read-only） | 斷點 |
|---|---:|---|---|
| 市場數據/自動掃描 | 95% | trading.signals 24h=90,870 | 無 |
| 策略選擇 | 70% | cost gate JS 選擇活躍；候選輪替運作 | 僅 flash_dip_buy 實際成交；grid 候選被凍（見 F3） |
| AI 風險評估 | 50% | Rust Guardian rule-based 活躍；`agent.ai_invocations` 7d=0 / **30d=0** | AI advisory 全 dormant（AMD-2026-05-09-02 governed）；E2E-1 未閉 |
| 下單 | 60% | orders 24h=35 / fills 24h=21（flash_dip 直通道）；bounded probe 通道 0 admission | probe 通道 100% 凍結（F3） |
| 止損 | 90% | Rust protective stops + EDGE-P1-1 grid 趨勢入場硬停（signal.rs:135） | exit 側趨勢止損本輪未證 |
| 學習 | 45% | probe_ledger.jsonl 310k rows 活躍；writer=1 已解凍 | label backfill / edge estimates cron 06-27 起死（F2）；SSOT 在 /tmp 揮發面（F1）；PG cutover 缺 |
| 進化 | 20% | proposal/adjudicator/proof-gate 全 source-only 契約 | 零 probe outcome；tournament orchestrator stub；無自主參數 apply 環 |

**整體 ≈ 55-60%**。最薄弱斷點 = 進化（20%）；binding constraint = 治理證據新鮮度死鎖（F3）+ 學習 producer cron 斷供（F2）。

---

## 二、Findings（全量，含 LOW/INFO）

### F1 [HIGH · FACT · high] 學習 SSOT 與全部治理證據 artifact 位於 boot-volatile /tmp
- **證據**：`/usr/lib/tmpfiles.d/tmp.conf` = `D /tmp 1777 root root 30d`（`D` = 每次開機清空 + 30d age 清理）；`/tmp/openclaw/cost_gate_learning_lane/probe_ledger.jsonl` 393MB（earliest row 2026-06-22，上次 reboot 06-20 後起算）；standing auth、canonical soak plan、全部 E3/BB packet/manifest/session-state（TODO 以 sha 引用者）全在 `/tmp/openclaw/`；crontab 明寫 `OPENCLAW_DATA_DIR=/tmp/openclaw`。
- **影響**：下次 reboot 學習 SSOT（`P1-LEARNING-LOOP-CLOSURE` 裁定 probe_ledger.jsonl 為 current SSOT）+ 治理審計證據鏈全滅 → 根原則 8（可重建）與 DOC-07 audit persistence 設計性破口；30d age 清理將自 ~07-22 起靜默刪除 06-26 前的 timestamped 證據檔，TODO/報告中 sha 引用逐步斷鏈。
- **Fix 方向**：遷移 OPENCLAW_DATA_DIR 至持久路徑（/var/lib/openclaw 或 NAS）+ ledger 週期歸檔 + 重開 PG cutover。**驗收標準**：reboot 演練後 probe_ledger row count 不變、TODO 引用之任一 sha artifact 仍可解析。

### F2 [HIGH · FACT(停擺)+INFERENCE(無記錄) · high] 06-27 crontab 重寫掉 ~12 個既有 producer crons，無治理記錄
- **證據**：現 crontab 僅 5 行（demo learning stack ×4 + ml_training_maintenance）；`/tmp/openclaw/logs/` 中 edge_label_backfill(17:30)、edge_estimate_snapshots_cycle(17:12)、canary_audit_pg_writer(17:58)、halt_audit_pg_writer(17:59)、panel_aggregator_health、polymarket_axis、polymarket_leadlag_ic、alpha_discovery_throughput、gate_b_watch、bybit_announcement_sentinel、adpe_runner、ref21_symbol_universe_snapshot、flash_dip_touchability 全部凍在 06-27 17:12-17:59；同日 PM 報告仍記 `crontab lines=70`（`2026-06-27--standing_demo_loss_control_envelope_runtime_materialization_apply.md:53` 起）；其後所有 PM 報告與 TODO 無「70→5 縮減」記錄。residual_stage0r cron 同批消失（flag 本就 OFF）。
- **影響**：學習 label 回填、edge estimates 刷新、canary/halt PG audit mirror、alpha discovery 全軸、listing 哨兵全部斷供 — 學習/進化 chain 的上游 producer 無主 dormant（無 owner/解凍條件/復查日）= FA 規則下與缺失同級 gap；審計面（DOC-06/07 PG mirror）靜默斷。
- **Fix 方向**：對照 06-27 前 crontab（`crontab_pre_sha256=8403678a…` 有 sha 但檔在 /tmp）逐條裁決 恢復/正式退役+記錄 owner。**驗收標準**：每條被移除 cron 有顯式裁決記錄；恢復者 log 重新滾動。

### F3 [HIGH · FACT · high] over-gate/evolution-blocker：bounded probe lane 100% 凍結（plan stale × standing auth expired × E3/BB exact-head 死循環）
- **證據**：ledger 最近 5h（07-03 06:29→11:24Z）12,646 筆 admission decision：`PLAN_STALE_OR_MISSING_GENERATED_AT`=11,075（87.6%）/ `SIDE_CELL_NOT_SELECTED`=1,374 / `ORDER_AUTHORITY_NOT_GRANTED`=197 / **admitted=0**；canonical plan generated_at `2026-06-30T21:43Z` vs `max_plan_age_hours=24`（`demo_learning_lane.rs:42`, 判定 `demo_learning_lane.rs:912-932`）；standing auth expires `2026-07-01T17:16:05Z`，07-03T11:22Z 實測仍為同一過期 sha `8c891b4e…`（**過期 ~42h**）；standing TTL=12h（generated 05:16→expires 17:16）< E3/BB exact-head 審批週期（TODO v710-v738 ~28 次 rotation，v731 差 80.4s 過期）。Rust hot path 本身已就緒（writer=1、admission 每小時千次評估）— 凍結純因上游治理 artifact 新鮮度。
- **影響**（按被凍結進化價值計價）：profit-first loop 的 probe→outcome→learning→promotion 全鏈自建立以來 **零 probe outcome**（`NO_PROBE_OUTCOMES_RECORDED`）；operator 首要目標（可進化+盈利證據）被流程摩擦鎖死；v710-v738 消耗數十 PM/E3/BB session = 高額 token 稅。緩解已 land source 側（`standing_envelope_post_approval_drift_gate.py` + `docs_tests_codex_exempt_v1`，TODO v739 指令），但 runtime 尚未實走成功；且 drift-exemption 只解 approval-void 一半，**不解 TTL<週期 的結構問題**。
- **Fix 方向**：(a) TTL 與審批週期對齊（TTL ≥ 週期 p95 或 refresh 專用快速通道）；(b) plan/envelope 新鮮度與全 repo quiet-window 解耦（drift-exemption 落地實走）。**驗收標準**：自 v739 起 N=3 個自然日內出現 ≥1 筆 admitted probe decision + 對應 candidate-matched outcome row；期間 standing auth 過期時長為 0。

### F4 [HIGH · FACT · high] cron expected-head pins 再度 stale → 健康面長期 SOURCE_NOT_READY（06-24 已修類別復發）
- **證據**：crontab 9 個 pin 全為 `00a78d92`（06-30 commit，且非現 main lineage 祖先）；runtime head `262596c`；`demo_learning_stack_healthcheck_latest.json`（07-03T10:32Z）`status=SOURCE_NOT_READY, blockers=[]`；sealed_horizon preflight 同類 pin。06-24 E3/MIT 已標同類（當時 pin `1b6173e3`）並「已對齊」，一週內復發。
- **影響**：健康面常紅 → 告警疲勞、真故障被淹沒；每次 head 前進需人工改 crontab literal = 重複開發成本。
- **Fix 方向**：pin-by-value 改 pin-by-reference（cron script 內 `git rev-parse HEAD` 或 deploy 路徑維護的 pin file）。**驗收標準**：head 前進後無人工介入，healthcheck 於下一 cron cycle 自行轉綠。

### F5 [MEDIUM · FACT · high] AI 治理環節 30d 零調用；E2E-1 真模型調用驗證缺口未閉
- **證據**：`agent.ai_invocations` 7d=0 / 30d=0；Layer2 manual-supervisor-only 為 AMD-2026-05-09-02 governed dormant（有 owner/依據）；但 L2 mesh E2E-1「真模型調用」驗證從未完成，追蹤 row 於 v530 被刪非閉（memory 07-02 檔）；Telegram 通知 creds 缺（三路通知 fail-safe 依賴）。
- **影響**：dormant 本身合規；gap 在「解凍時無法證明可用」— 4 維評分：代碼存在=1 / 可調用=1 / 端到端=0 / 邊界=未知。
- **Fix 方向**：一次性 E2E-1 真調用煙測（預算 cap 內）+ 補 Telegram creds 或正式降級通知路徑。**驗收標準**：ai_invocations ≥1 筆帶 cost 記錄 + ThoughtGate lineage 完整。

### F6 [MEDIUM · FACT · high] SPECIFICATION_REGISTER 模組欄漂移：兩個 implementing module 不存在 + 一個 Rust 對應物為死碼
- **證據**：register `DOC-01`/`EX-01` 指 `protective_order_manager.py`、`SM-03`/`EX-02` 指 `oms_state_machine.py` — repo 全域 find 均 0 檔；`rust/openclaw_core/src/sm/oms.rs` 存在但 openclaw_engine 0 引用（`sm::oms|OmsState` grep 0 hit；符合 FA-H3 死碼名單）。止損/OMS 實質功能在 `position_risk_evaluator.rs`/`order_manager.rs`/`risk_checks.rs` 等（功能未缺，索引錯位）。
- **影響**：治理索引錨點失效 → 未來 spec 對照審計低效/誤判。
- **Fix 方向**：register 模組欄更新為 Rust 實際檔；sm/oms.rs 標死碼裁決。

### F7 [MEDIUM · FACT+INFERENCE · med] cost_gate_learning_lane 治理 helper 面積膨脹：86 檔 / 4.4MB
- **證據**：`helper_scripts/research/cost_gate_learning_lane/*.py` = 86 檔；TODO §2 ~40 個一次性 no-repeat marker 各對應專用 packet/review helper；envelope/freshness/authority 檢查邏輯多檔重複。
- **影響**（按重複開發成本計價）：每個新 checkpoint 生新 helper+tests；agent 讀改頻率高 × 體量大 = 持續 token 稅；F3 的死循環同時放大此稅。
- **Fix 方向**：收斂為參數化 packet generator 核心庫 + 薄 CLI；與 F3 修復同批做。

### F8 [MEDIUM · FACT · high] 唯一活躍成交通道 flash_dip_buy 30d 淨 -7.04 USDT；unattributed fills 殘留
- **證據**：trading.fills 30d：flash_dip_buy n=154, realized_pnl=-7.0375, fees=13.0837；7d n=66, -2.3593；7d 另有 `unattributed:bybit_auto|LINKUSDT` n=2（lineage gap 殘留，量小）。
- **影響**：06-24 FA verdict「profit evidence NOT ACHIEVED」維持不變；demo 學習成本可接受，但全系統無任何 promotion-grade 正證據；fill lineage 未 100% 淨。

### F9 [LOW · FACT · high] SCRIPT_INDEX.md 未收錄 7/86 lane helpers
- **證據**：`bounded_probe_candidate_construction_preview.py`、`bounded_probe_lower_price_reroute_review.py`、`bounded_probe_order_construction_repair.py`、`current_candidate_active_decision_lease_gate_window.py`、`current_candidate_actual_admission_bbo_lease_window.py`、`proof_exclusion.py`、`standing_demo_authorization.py` 不在 `helper_scripts/SCRIPT_INDEX.md`。違 CLAUDE §七「新腳本必須更新 SCRIPT_INDEX」。

### F10 [LOW · FACT · med] 治理 .docx→.md 轉檔 SOP 腳本不存在
- **證據**：spec-compliance skill 指名 `helper_scripts/maintenance_scripts/governance_docx_to_md.py`（或等價）— repo 內無任何 docx 轉檔腳本；現況 22 .docx 均有對應 .md 且無 mtime 落後（本輪實測 0 stale）。
- **影響**：operator 下次改 .docx 時 SOP step 1 不可執行 → .md 漂移風險。

### F11 [INFO · FACT · high] alpha_tournament orchestrator 仍為 stub（與 ARCH-05 標註一致）
- **證據**：`helper_scripts/alpha_tournament/tournament_orchestrator.py`（47 行）自報 `sprint_2_stub` / `ranking_logic=not_implemented_in_sprint_2`。documented 未實現，進化環節主要缺口之一，register 誠實。

### F12 [INFO · FACT · high] Stage0R residual preflight dormant（flag 預設 0 + cron 未裝）
- **證據**：`helper_scripts/cron/residual_stage0r_preflight_cron.sh:16` `OPENCLAW_RESIDUAL_STAGE0R_PREFLIGHT=1`（NEW flag，預設 0）；現 crontab 無 entry。與 memory 07-02 確認一致 — documented dormant，但其解凍條件與 owner 建議併入 F2 的 cron 裁決清單。

### F13 [INFO · FACT · high] TODO.md v738 runtime facts 已被 overnight 進展超越
- **證據**：TODO 記 engine PID `1538641`、writer 未啟、runtime `ahead 8, behind 164`；實測 PID `2368227`、`OPENCLAW_DEMO_LEARNING_LANE_WRITER=1`、runtime clean at `262596c`。正常版本節奏內的滯後；下一 dispatcher 必須以 runtime 實測為準。

### F14 [INFO · FACT · high] 硬邊界正向驗證（無違反）
- `OPENCLAW_ALLOW_MAINNET=0`（engine env 實測）；stock_etf routes 全 GET-only（`stock_etf_routes.py:100-262`，ADR-0048 Phase 4 display-only 合規）；生產碼無 `/home/ncyu|/Users/` 硬編碼（僅注釋）；.claude 18 agents + 25 skills 完整；DEPRECATED.md 禁引紀律良好；Mac/GitHub/runtime 三頭線性無分叉。

---

## 三、Gap 三分表

| 類別 | 條目 |
|---|---|
| dead code（有碼不可用） | openclaw_core `sm/oms.rs`（F6）；FA-H3 歷史名單本輪未複掃（見盲區） |
| 根本沒實現 | alpha_tournament ranking（F11）；自主參數 apply 環（僅契約）；probe outcome→promotion 實走證據 |
| dormant 凍結（有主） | AI advisory/L2（AMD-2026-05-09-02，owner=operator，解凍=supervisor 授權；F5）；Stage0R flag（F12）；IBKR P1-P5 source-only（ADR-0048 phase unlock table 齊備）；`P1-FEE-TIER-PRIVATE-READ` DEFERRED（TODO 有 reopen 條件） |
| dormant 凍結（**無主 = 同級 gap**） | F2 全部 12 條被移除 cron（無退役記錄/owner/復查日）；bounded probe lane 事實凍結（F3，有修復方向但無 TTL 結構裁決） |
| over-gate（負淨貢獻控制） | F3 exact-head 審批 × 12h TTL × 24h plan age 疊加 → 拒真率 100%（11,075/11,075 plan-stale 拒絕中 0 真風險攔截）；F4 stale pin 常紅健康面 |

## 四、負空間（本輪未展開盲區 → PA re-probe 線索）
見 StructuredOutput assumptions；重點：GUI 93 寫入端點 fake-success 未複掃、DOC-01..08 條文級全文對照未重做、exit 側趨勢止損未證、openclaw_core 死碼名單未複掃、06-27 crontab 變更是否存在 repo 外（.codex session）授權記錄未窮盡。

FA AUDIT DONE: report path: docs/CCAgentWorkSpace/FA/workspace/reports/2026-07-03--full_repo_functional_audit.md
