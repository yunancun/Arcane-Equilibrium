STATUS: DONE_WITH_CONCERNS
VERDICT: CONDITIONAL|FINDINGS=6(C:0/H:3/M:3/L:0)

# CC 二輪對抗性審查 — IBKR Stock/ETF Paper + Shadow 補丁後安排

日期：2026-06-29
角色：CC(default)
範圍：治理、根原則、硬邊界、Phase gate 二輪 adversarial audit。
邊界：report-only；未改 runtime/code/TODO，未呼叫 IBKR/Bybit，未觸碰 Linux `trade-core`、PG、services、secrets 或網路。依本任務「只寫指定報告」邊界，未追加 CC memory 或 Operator mirror。

## 總判定

補丁後的方案可以作為 **Phase 0 ADR/spec packet** 繼續；仍不能作為 Phase 1+ implementation、IBKR API/secret、paper order rehearsal、GUI runtime activation、evidence clock、或任何 tiny-live/live 的授權依據。

我沒有看到新的 active runtime/code bypass：repo 當前硬邊界仍是 Bybit-only execution、Rust authority、Python bridge/control plane，且窄範圍 grep 未在 `program_code/`、`rust/`、`sql/`、`settings/`、`helper_scripts/` 找到 IBKR/stock lane runtime/code 表面。`docs/_indexes/initiative_index.md:23` 也標明該 initiative 尚未進 `TODO.md` active queue，需 Phase 0 ADR/spec 後才開工。

但 operator 問的「按排程後可以完整上線」不能被本計劃認證。當前計劃最多能定義與驗證 paper/shadow research lane；任何 production readiness、IBKR live、tiny-live、資金/券商實際風險承擔都需要新的 ADR/spec/runbook 與獨立 gate。

## Findings

### H-1 — Phase 1+ 仍被硬阻斷；補丁不能被解讀成 implementation authority

證據：
- 計劃開頭明確：第一輪對抗審查只批准 Phase 0 ADR/spec；Phase 1+、IBKR API、secret slot、paper order rehearsal、GUI runtime enablement、evidence clock 均需先補第 11 節 blocker（`docs/execution_plan/2026-06-29--ibkr_stock_etf_paper_shadow_development_arrangement.md:14-17`）。
- §11 共識寫明唯一可立即前進的是 Phase 0，所有 Phase 1+、IBKR API、secret slot、paper order、GUI runtime activation、evidence clock 均 BLOCKED（同檔 `:670-678`），且 PM 判定當前方案「有效但未可開工」，有效性只限 Phase 0（同檔 `:707`）。
- PM 整合報告同樣不批准 Phase 1+、IBKR API、secret、paper order、GUI runtime rollout、TODO implementation row、evidence clock、任何 IBKR live/tiny-live（`docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-29--ibkr_stock_etf_plan_adversarial_pm_integration.md:18-28`）。
- 當前憲法邊界仍是 Bybit-only execution、Rust authority、Python 非交易真相層（`CLAUDE.md:27-32`；`docs/adr/0001-rust-as-trading-authority.md:6-8`；`docs/adr/0006-bybit-only-exchange.md:6-12`）。

Required resolution：
- Phase 1 entry gate 必須是 accepted ADR/AMD + report-backed operator decision + source-of-truth sync check，而不是計劃文件本身。
- 在該 gate 前，不得新增 `TODO.md` active implementation row、不得建立 secret slot、不得 scaffold connector、不得跑 migration apply、不得呼叫任何 IBKR API。

### H-2 — Phase 2 首次 IBKR 外部接觸需要單一 machine-checkable gate manifest

證據：
- 計劃 Phase 0 已要求補 exact IBKR API baseline、paper attestation、secret contract、non-Bybit API allowlist、feature flag matrix（`...arrangement.md:292-301`），但 Phase 2 啟動條件只寫「Phase 0 已選定 IBKR API baseline，並完成 E3 secret/runtime topology 審查」（同檔 `:529-535`）。
- E3 指出 paper/live binding 仍未 machine-checkable：host/port/session/account-mode 錯配可能使 paper path 連到 live session（`docs/CCAgentWorkSpace/E3/workspace/reports/2026-06-29--ibkr_stock_etf_plan_e3_review.md:41`）。
- E3 也要求 secret exact files/modes/no-env-fallback、authorization schema、API allowlist、redaction、runtime topology 都在任何 IBKR call 前落成（同報告 `:42-47`、`:78-89`、`:94`）。

Required resolution：
- Phase 2 前新增 `phase2_ibkr_external_surface_gate_v1` manifest，至少包含：API family choice、runtime process owner、host/port/session lifecycle、account fingerprint、market-data tier、allowed endpoint/action list、transport limits、secret filenames/chmod/fingerprint/rotation/no-env-fallback、live slot absent/empty proof、broker-reported paper attestation、redaction fixtures、permission-scope proof、kill switch。
- 該 manifest 未 PASS 前，read-only healthcheck 也不得呼叫，因為 healthcheck 已是非 Bybit 外部接觸與 secret/session surface。

### H-3 — 「完整上線」與 future tiny-live 必須另開 production-readiness ADR/runbook

證據：
- 計劃禁止 live IBKR、margin、short、options、CFD、資金劃轉、非 Bybit live（`...arrangement.md:25`），Phase 5 驗收仍寫 live 禁止；若要 tiny live probe，另開 ADR/authorization/spec（同檔 `:610-615`），paper 成功不得自動升級，只允許開新 ADR 討論 tiny-live（同檔 `:653-658`）。
- README/CLAUDE 的真 live 五 gate 仍成立（`CLAUDE.md:81-88`；`README.md:195-203`）。
- ADR-0040 的 per-venue 5-gate 只是 Binance precedent，不批准 IBKR；它要求 per-venue secret slot、venue-aware authorization、fail-closed outbound orders（`docs/adr/0040-multi-venue-gate-spec.md:73-88`），且 venue change / authorization 三元組簽署仍需 operator session（同檔 `:117-127`）。
- ADR-0034 把 venue change 歸入 LAL 4，operator approval mandatory；Level 2 也不把 venue change 納入 auto path（`docs/adr/0034-decision-lease-layered-approval-lal.md:14-20`、`:151-159`）。

Required resolution：
- 「按排程後完整上線」只能在另立 `stock_etf_cash_production_readiness_v1` ADR/runbook 後討論。最低內容：IBKR live/tiny-live 是否存在、per-broker 5 gate、LAL 4 operator path、live credential/secret policy、KYC/ToS/jurisdiction/tax posture、broker-side protection/reconciliation、incident response、rollback/kill switch、monitoring/SLO、DR、support owner、weekly review、go/no-go packet。
- Phase 5 即使產生 positive paper/shadow evidence，也只能觸發「是否起草 tiny-live ADR」的問題，不能觸發自動 live/tiny-live。

### M-1 — Phase 3/evidence clock 可作 screening gate，不能認證 durable alpha 或 production readiness

證據：
- 計劃已修正為：6-8 週窗口默認只可作 engineering shakedown + preliminary feasibility screen；低頻策略樣本不足只能 `research_promising` 或 `insufficient_evidence`，不能輸出 durable-alpha proof（`...arrangement.md:471-473`）。
- Phase 3/evidence clock 前需 manifest、frozen hashes、source as-of、sample-size rules、divergence thresholds、matched controls、ADR-0047 labels、scorecard formula appendix（同檔 `:696-705`）。
- QC 明確說當前窗口能回答 operational feasibility，不能可靠回答 durable after-cost alpha；修正後也只可作 screening gate（`docs/CCAgentWorkSpace/QC/workspace/reports/2026-06-29--ibkr_stock_etf_plan_qc_review.md:11-15`、`:193-199`）。
- MIT 要求 Phase 3 前 vendor/tier、calendar-aware coverage、PIT universe、corporate-action set、cost/benchmark versions、paper/shadow reconciliation、pre-registered stats 全部 machine-checkable（`docs/CCAgentWorkSpace/MIT/workspace/reports/2026-06-29--ibkr_stock_etf_plan_mit_review.md:300-311`）。
- ADR-0047 要求 regime/breadth/freshness/survivorship/execution realism/statistical gates，bull-only/stale-only positive 不能 promote（`docs/adr/0047-alpha-edge-regime-evidence-governance.md:21-29`、`:42-51`）。

Required resolution：
- `stock_etf_evidence_clock_v1` 必須把「天數合格」與「盈利可行」分離。`profitability_feasible` 只能在 pre-registered independent sample、benchmark-relative lower bound、PSR/DSR or equivalent、cost stress、paper-vs-shadow divergence、concentration/regime gates 全 PASS 時出現。
- 未達獨立樣本或跨 regime 條件時，強制標 `insufficient_evidence` / `research_promising` / `regime-bet / learning-only`。

### M-2 — Phase 4 GUI runtime activation 還需要 route/cache/auth negative-test contract

證據：
- 計劃已正確聲明 GUI lane selector 只可作 query/filter state；effect-capable operation 必須由 server/Rust 重新驗證 lane/broker/environment/risk/auth/Decision Lease/Guardian（`...arrangement.md:316-319`）。
- 計劃也要求先做 lane badge/readiness page，後端 interface 與 fail-closed gates 穩定後才做完整 selector（同檔 `:574-580`）。
- 但 Phase 4 驗收仍偏 GUI smoke：`node --check`、desktop/mobile screenshot、crypto tabs 不回歸、stock live fail-closed（同檔 `:590-595`）。
- FA 指出缺 route-level validation、cache partition、disabled-lane negative tests、stale/no-data/error/operator workflow states（`docs/CCAgentWorkSpace/FA/workspace/reports/2026-06-29--ibkr_stock_etf_plan_fa_review.md:94-118`）；E3 要求證明 hidden fields/client-side lane changes 不能授權 orders（`docs/CCAgentWorkSpace/E3/workspace/reports/2026-06-29--ibkr_stock_etf_plan_e3_review.md:48`、`:74-75`）。

Required resolution：
- Phase 4 前新增 `gui_lane_display_filter_only_v1` contract：server-side `asset_lane` enforcement、invalid/missing lane behavior、cache partition、CSRF/auth continuity、localStorage/query/hidden field untrusted tests、disabled `cfd_margin` no write path、stock live no authorization path、existing crypto tab regression suite。

### M-3 — 可認證聲明與假設仍需在 PM/operator 溝通中硬分離

證據：
- 本項目的 source of truth 是 `CLAUDE.md`、`.codex/MEMORY.md`、README、TODO、ADR、reports；不得依賴 hidden chat memory（`.codex/MEMORY.md:47-63`；`docs/agents/context-loading.md:8-18`）。
- 計劃的核心假設是 IBKR 可能降低 cost wall、股票/ETF alpha 需獨立 evidence、lane 價值在於低相關/成本/報表/paper-shadow audit（`...arrangement.md:41-45`）。這些還不是證據。

Required resolution：
- 任何對 operator 的後續摘要必須分成：
  - Certified facts：docs-only、Phase 0 only、no code/runtime IBKR surface、chat-only 不足、functional live flag 移除、paper/shadow 不自動 live。
  - Assumptions：IBKR cost wall 改善、paper/live attestation 可可靠取得、6-8 週足以 screening、market/corporate/tax/fee source 可取得、GUI 分路可低債落地、future tiny-live 值得討論。

## Review Questions Direct Answers

1. 是否仍有 governance bypass、ambiguous paper/live boundary、chat-only approval path？
   - active bypass：未發現。
   - chat-only：補丁已加「不允許 chat-only approval 代替 ADR/AMD；operator approval 必須落入治理文檔」（`...arrangement.md:499-502`）。因此 line 499 的「operator 明確批准」只能按 line 502 解讀為治理文檔化批准。
   - paper/live：文案已大幅收斂；但 IBKR paper submit/cancel/replace 仍是 effect-capable broker-paper surface，必須用 H-2 的 paper attestation + scoped authorization + Rust authority manifest 才能解除 ambiguity。

2. Phase 1/2/3/4/future tiny-live 前是否還缺 hard blockers？
   - Phase 1：只要 §11 的 ADR/AMD、API baseline、Rust IPC/lifecycle、DB contract、flag/secret matrix、Python no-write、GUI display-only contract 全部成為 accepted spec，才可進入；目前仍 blocked。
   - Phase 2：缺單一 `phase2_ibkr_external_surface_gate_v1`；首次 IBKR call/secret/healthcheck 都要等它。
   - Phase 3/evidence clock：§11 + QC/MIT gates 足夠作方向，但必須落成 `stock_etf_evidence_clock_v1` manifest，不得用 6-8 週直接宣稱 durable alpha。
   - Phase 4 GUI：缺 `gui_lane_display_filter_only_v1` route/cache/auth negative tests。
   - Future tiny-live：缺全新的 ADR/authorization/spec + production readiness runbook + LAL 4 operator gate；本計劃不能授權。

3. 「按排程後可以完整上線」是否需要 separate production-readiness ADR/runbook？
   - 是。當前排程只覆蓋 paper/shadow research lane 的工程與 evidence collection；不覆蓋 production live/tiny-live readiness。

4. 哪些 claim 可 certified，哪些仍是假設？
   - 可 certified：當前補丁是 docs/report/index 層；未發現 code/runtime IBKR surface；Bybit-only/Rust authority/live 5-gate 仍是現行邊界；PM/計劃均只批准 Phase 0；chat-only approval 被文檔化 gate 關閉；IBKR live 不在本計劃授權內。
   - 仍是假設：IBKR 會降低足夠 cost wall；6-8 週能得到足夠 independent sample；IBKR paper 能代表可用 execution realism；資料/費用/稅務/corporate-action source 足夠穩定；GUI 分路可無債落地；future tiny-live 值得啟動。

## Can This Advance Beyond Phase 0?

可以，但不是現在，也不能靠本計劃自動前進。精確 gate：

1. Phase 0 accepted ADR/AMD：只批准 `stock_etf_cash` read-only/paper/shadow research；明確不批准 live、margin、short、options、CFD、transfer；同步 source-of-truth 或記錄為何 ADR-only 足夠。
2. Phase 1 conditional：type/config/schema/IPC 只做 default-OFF reservation + denial tests + DDL/dry-run packet；無 connector、無 secret、無 external call、無 runtime mutation。
3. Phase 2 conditional：`phase2_ibkr_external_surface_gate_v1` PASS 後，才可做 read-only/paper connector；paper order rehearsal 另需 Rust-owned lifecycle + scoped envelope + paper attestation。
4. Phase 3 conditional：`stock_etf_evidence_clock_v1` PASS 後，才可起算 evidence clock。
5. Phase 4 conditional：`gui_lane_display_filter_only_v1` PASS 後，才可 runtime activation GUI slice。
6. Future tiny-live：另開 ADR/spec/runbook；LAL 4 operator approval + venue/broker live gates + E3/QC/MIT/CC/PM sign-off 全部重新審。

PM-facing gate decision: APPROVE_PHASE0_ONLY
