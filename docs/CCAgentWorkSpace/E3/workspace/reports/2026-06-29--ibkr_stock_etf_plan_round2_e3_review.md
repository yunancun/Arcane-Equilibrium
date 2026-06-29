STATUS: DONE_WITH_CONCERNS
VERDICT: CONDITIONAL|FINDINGS=6(C:0/H:3/M:3/L:0)

# IBKR Stock/ETF Paper + Shadow Plan Round 2 E3 Review

日期：2026-06-29
角色：E3(explorer)
範圍：security、secrets、broker API/session、runtime/deploy safety
模式：report-only；未修改 runtime/code/TODO；未觸碰 Linux `trade-core`、PG、services、secrets、network、IBKR 或 Bybit。

## 總結

補丁後的方案已把第一輪主要問題提升成 Phase 0/Phase 1 blocker：IBKR API baseline、broker-paper attestation、lane-scoped Rust IPC、Python no-write、secret invariant matrix、GUI display-only、DB/evidence contract 都已回到計劃內。這足以批准 Phase 0 ADR/spec。

但它仍不足以進入 IBKR read-only healthcheck、paper fill import 或 paper order rehearsal。當前計劃多處使用「定義 / 必須補充」而不是可執行 gate；paper/live/session/account attestation、外部 broker process topology、secret/session/redaction、API allowlist、kill switch、degraded mode、audit/runbook gate 尚未形成機器可檢查契約。

## 直接回答

1. Paper/live/session/account attestation：不夠強。計劃要求 broker-reported paper attestation，但沒有定義 API-family-specific 證明欄位、pre-order binding、host/port/session/account fingerprint、negative tests。
2. Secret/session/redaction contract：不完整。計劃要求 exact filenames/chmod/fingerprint/redaction，但還沒有覆蓋 TWS API / IB Gateway / Client Portal 的 session cookies、client id、gateway logs、renewal、2FA、local certs、account id masking。
3. API allowlist / local binding / ownership / firewall / Tailscale / renewal / rate-limit / kill-switch / degraded mode：未完整定義。現在只有 Phase 0 blocker 級摘要，不是 deploy/runbook 級契約。
4. Python broker writes：尚未結構性防止。計劃禁止 Python `place_order/cancel/replace`，但還需要 AST/grep/route negative tests 覆蓋 IBKR library 方法、generic HTTP writer、Client Portal order endpoints、reconnect retry。
5. Mandatory E3 gates：見本文「E3 Mandatory Gates」。結論是 Phase 0 only；Phase 1+ 仍 blocked。

## Evidence

- 當前硬邊界仍是 Bybit-only execution、Rust authority、Python not truth layer：`CLAUDE.md:27-32`；根原則要求 single controlled write entry、read/write separation、reconstructability：`CLAUDE.md:43-52`。
- True live 仍需五項 gate，且不得偽造 healthcheck/trading evidence：`CLAUDE.md:81-96`。README 同樣標明 Bybit 是唯一下單/執行 adapter：`README.md:4-10`，live 五門摘要在 `README.md:199-203`。
- IBKR 計劃已明確只批准 Phase 0，Phase 1+、IBKR API、secret slot、paper order、GUI runtime activation、evidence clock 均 blocked：`docs/execution_plan/2026-06-29--ibkr_stock_etf_paper_shadow_development_arrangement.md:14-17`、`:670-679`。
- 計劃新增了 broker paper attestation、secret contract、allowlist、feature flag matrix 的 Phase 0 要求：`docs/execution_plan/2026-06-29--ibkr_stock_etf_paper_shadow_development_arrangement.md:292-301`，以及 Phase 1 前 blockers：`:680-694`。
- PM integration 不批准 IBKR API call/runtime healthcheck、secret slot、paper order rehearsal、GUI runtime rollout、evidence clock 或 any IBKR live/tiny-live：`docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-29--ibkr_stock_etf_plan_adversarial_pm_integration.md:18-28`。
- 第一輪 E3 已指出 paper/live binding、secret slots、authorization schema、API policy、Python boundary、redaction、runtime topology 都需 testable gate：`docs/CCAgentWorkSpace/E3/workspace/reports/2026-06-29--ibkr_stock_etf_plan_e3_review.md:41-47`、`:78-89`。

## Findings

### H-01 — Paper/live/session/account attestation is still not executable

Evidence:
- Plan requires broker-reported paper attestation before order and account fingerprint/host/port/environment matching, but only as Phase 0 bullets: `docs/execution_plan/2026-06-29--ibkr_stock_etf_paper_shadow_development_arrangement.md:292-301`、`:684-685`。
- Plan says paper order lifecycle goes through Rust authority and Python only forwards/reads: `docs/execution_plan/2026-06-29--ibkr_stock_etf_paper_shadow_development_arrangement.md:155-160`。
- First-round E3 finding explicitly warned that host/port/session/account-mode misconfiguration can make a paper path touch live IBKR: `docs/CCAgentWorkSpace/E3/workspace/reports/2026-06-29--ibkr_stock_etf_plan_e3_review.md:41`。

Risk:
IBKR paper/live separation is operationally fragile because API family, login/session, host/port, account selector, and paper account identity are external to OpenClaw. A prose statement that `OPENCLAW_IBKR_PAPER_ENABLED=1` is paper-only does not prevent connecting to a live TWS/Gateway/Client Portal session.

Required resolution:
- Define `ibkr_session_attestation_v1` before any healthcheck evolves toward order-capable use.
- Required fields: API family, process identity, bind host/port, client id, session fingerprint, account id salted fingerprint, broker-reported paper/live environment, secret slot fingerprint, permission scope, market-data tier, timestamp, expiry, and source artifact hash.
- Rust must verify the attestation immediately before any paper order intent is constructed. Mismatch must fail before order intent, not after submit.
- Negative tests must cover live account/session response, wrong account, wrong host/port, stale session, multiple accounts, missing paper marker, and live secret material present.

### H-02 — External broker process topology and runtime safety are not deploy/runbook ready

Evidence:
- Plan requires choosing TWS API / IB Gateway / Client Portal and defining runtime process owner, host/port, session lifecycle, and market-data tier: `docs/execution_plan/2026-06-29--ibkr_stock_etf_paper_shadow_development_arrangement.md:684-685`。
- First-round E3 required local binding, process ownership, service policy, kill switch, and no `trade-core` broker process without separate E3 runtime review: `docs/CCAgentWorkSpace/E3/workspace/reports/2026-06-29--ibkr_stock_etf_plan_e3_review.md:47`、`:88`。
- TODO loss controls require kill-switch and reconstructability limits for autonomous actions: `TODO.md:117-118`。

Risk:
IBKR integration is not just an API client. TWS / IB Gateway / Client Portal introduce an external process, local ports, session renewal, logs, GUI/login state, and potentially browser/cookie surfaces. Without topology constraints, the broker terminal can become an uncontrolled second runtime or a live-session bridge.

Required resolution:
- Phase 0 ADR must choose exactly one API baseline or create a no-order spike with exit criteria.
- Define process owner, host placement, allowed bind address, firewall posture, Tailscale exposure rule, service unit policy, log location, permissions, upgrade policy, and operator runbook.
- Require local-only binding unless a separate E3 runtime review approves otherwise. No broker API port may be exposed over Tailscale/public LAN by default.
- Define session renewal/expiry behavior, reconnect/backoff, rate limits, maintenance windows, and hard degraded states: `BROKER_DOWN`, `SESSION_EXPIRED`, `ACCOUNT_ATTESTATION_MISMATCH`, `DATA_TIER_INSUFFICIENT`, `KILL_SWITCH_ACTIVE`.
- Define a kill switch that overrides all IBKR flags and blocks new broker calls while preserving read-only status/audit.

### H-03 — API allowlist and Python no-write guard remain too abstract

Evidence:
- Plan says Python connector must not expose direct broker `place_order/cancel_order/replace_order` and needs grep/static tests: `docs/execution_plan/2026-06-29--ibkr_stock_etf_paper_shadow_development_arrangement.md:212-217`。
- Plan requires a non-Bybit API allowlist by method/action/transport/rate-limit/raw artifact policy: `docs/execution_plan/2026-06-29--ibkr_stock_etf_paper_shadow_development_arrangement.md:299`。
- PM deduplicated blockers require Python health/snapshot/fill import only and static guards against direct broker writes: `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-29--ibkr_stock_etf_plan_adversarial_pm_integration.md:68-72`。

Risk:
Naming only `place_order/cancel_order/replace_order` is insufficient. IBKR libraries and Client Portal can submit or cancel orders through generic `req*`, `EClient.placeOrder`, `cancelOrder`, REST POST/DELETE, or wrapper methods whose names do not match the three obvious strings. A Python `paper_client.py` with a generic authenticated request helper can become a broker writer without a method named `place_order`.

Required resolution:
- Define operation-class allowlists: read-only health/session/account, fill/commission import, market data, paper order rehearsal, forbidden live/account-management/transfer/margin/options/CFD.
- Define exact method/action/endpoint allowlists for the chosen API family before first call.
- Python may not hold an authenticated generic broker write helper. If a generic request helper exists, it must enforce a deny-by-default allowlist and be covered by tests.
- Add AST/grep guards for IBKR library writer calls and Client Portal order endpoints, not just local method names.
- Paper submit/cancel/replace must be Rust-owned. Python may only call Rust IPC after Rust has authorization, Decision Lease, Guardian, risk, attestation, and audit sink ready.

### M-01 — Secret/session/redaction contract is not complete across IBKR API surfaces

Evidence:
- Plan defines external IBKR secret slot paths and says `live/` should not be created; live material makes healthcheck fail: `docs/execution_plan/2026-06-29--ibkr_stock_etf_paper_shadow_development_arrangement.md:272-278`。
- Plan requires exact filenames, chmod 700/600, fingerprint, rotation, TTL, no-env-fallback, and redaction rules: `docs/execution_plan/2026-06-29--ibkr_stock_etf_paper_shadow_development_arrangement.md:297-298`。
- First-round E3 requires no secrets in argv/log, no cookies/session tokens, account-id masking/fingerprinting, error classification, and synthetic IBKR credential/session tests: `docs/CCAgentWorkSpace/E3/workspace/reports/2026-06-29--ibkr_stock_etf_plan_e3_review.md:46`。

Risk:
IBKR credentials are not only API keys. Depending on API baseline, the sensitive surface can include paper username/password, Client Portal cookies/session tokens, brokerage session ids, local gateway SSL material, TWS settings, 2FA state, client IDs, account aliases, raw order ids, and Java/gateway logs. The plan says to create a contract, but does not yet define it.

Required resolution:
- For each candidate API family, enumerate credential classes, session artifacts, log files, config files, renewal artifacts, and redaction patterns.
- Ban secrets/session tokens in argv, environment dumps, process listings, service logs, raw artifacts, stack traces, exception strings, and GUI payloads.
- Store account identity as salted fingerprint plus masked display form unless raw account id is strictly required in an encrypted/local artifact.
- Add synthetic redaction fixtures for TWS/Gateway/Client Portal shapes: cookies, session ids, account ids, order ids, client ids, local paths, headers, cert paths, tracebacks, and broker error payloads.

### M-02 — Audit, degraded mode, and runbook gates are under-specified

Evidence:
- Plan says lanes share append-only audit and PnL evidence contracts: `docs/execution_plan/2026-06-29--ibkr_stock_etf_paper_shadow_development_arrangement.md:65-70`。
- Plan lists `audit.asset_lane_events` but does not define schema: `docs/execution_plan/2026-06-29--ibkr_stock_etf_paper_shadow_development_arrangement.md:223-235`。
- MIT first-round review also found append-only audit is not yet an evidence schema and needs event types, actor, source, payload hash, previous hash/sequence, environment, asset lane, broker, and immutable artifact refs: `docs/CCAgentWorkSpace/MIT/workspace/reports/2026-06-29--ibkr_stock_etf_plan_mit_review.md:261-267`。

Risk:
Safe runtime behavior depends on what happens when the broker is down, the session expires, market data is delayed, account attestation becomes unknown, a fill import disagrees with shadow, or the kill switch is active. The current plan lists evidence goals but not degraded-state semantics or operator runbook gates.

Required resolution:
- Define `audit.asset_lane_events_v1` before Phase 2: event type, actor, source, asset_lane, broker, environment, account/session fingerprint, permission scope, decision id, order intent id, payload hash, previous hash/sequence, denial reason, artifact refs.
- Define degraded state taxonomy and allowed actions per state. Degraded must never silently downgrade from paper to shadow or from live to paper; it must fail closed or mark evidence invalid/quarantined.
- Define operator runbooks for session renewal, account mismatch, stale open order, `STATE_UNKNOWN`, kill switch, connector down, data-tier insufficiency, and paper-vs-shadow divergence.

### M-03 — Phase-specific E3 gates are still not a checklist

Evidence:
- Phase 2 says it must not start unless Phase 0 has selected API baseline and completed E3 secret/runtime topology review: `docs/execution_plan/2026-06-29--ibkr_stock_etf_paper_shadow_development_arrangement.md:529-535`。
- Phase 2 acceptance only says reconstructable snapshot, broker ids, no argv/log secrets, live fail-closed: `docs/execution_plan/2026-06-29--ibkr_stock_etf_paper_shadow_development_arrangement.md:544-550`。
- PM integration explicitly blocks IBKR API healthcheck, secret slot, paper order rehearsal, GUI runtime, evidence clock, and any tiny-live: `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-29--ibkr_stock_etf_plan_adversarial_pm_integration.md:18-28`。

Risk:
The plan now has blockers, but a future implementer still lacks exact go/no-go gates for the first read-only call, first fill import, first paper order rehearsal, and any tiny-live ADR. That ambiguity is exactly where security debt tends to enter as "temporary" scaffolding.

Required resolution:
- Add the checklist below to the ADR/spec as mandatory gates.
- Treat missing gate artifact as `BLOCKED_BY_SECURITY`, not `DONE_WITH_CONCERNS`.
- Gate artifacts must be immutable report/artifact files with hashes and must not rely on chat approval.

## E3 Mandatory Gates

### Before IBKR read-only healthcheck

Mandatory gates:
- Accepted ADR/AMD approving only `stock_etf_cash` read-only/paper/shadow research, not live/margin/short/options/CFD/transfer.
- Chosen API baseline or no-order spike scope with explicit no-order allowlist.
- E3-approved topology: process owner, host, bind address, service policy, logs, firewall/Tailscale posture, no public exposure.
- Read-only secret slot contract: exact files, 700/600 modes, typed slot enum, no env fallback, fingerprint algorithm, rotation/TTL, live slot absent/empty proof.
- API allowlist limited to session/account/market-data entitlement health. No order, cancel, account-management write, transfer, margin, options, or CFD endpoints.
- Redaction regression suite green for selected API family.
- Rate limit, timeout, no-redirect, TLS verification, session renewal/expiry, and degraded state policy defined.
- Audit event emitted for healthcheck attempt/result with masked account/session fingerprint and raw response hash policy.

Gate decision if missing any item: BLOCK before healthcheck.

### Before IBKR paper fill import

Mandatory gates:
- Read-only healthcheck gate green and not stale.
- Paper account/session attestation green: expected account fingerprint, environment paper, host/port/process identity, secret slot fingerprint.
- Source priority order for fills/orders/commissions chosen: API callbacks, reports/statements, Flex/Client Portal/TWS source, and disagreement policy.
- DB/evidence schema accepted: instrument identity, broker order ids, execution ids, commission report ids, FX/cash ledger, append-only audit, idempotency keys.
- Import path proves no submit/cancel/replace capability is used or required.
- Redaction masks account ids, session ids, order ids where appropriate, raw broker payloads, local paths, errors.
- Idempotency and duplicate import tests green; stale/unknown fill state routes to manual review or quarantine.

Gate decision if missing any item: BLOCK before fill import.

### Before IBKR paper order rehearsal

Mandatory gates:
- Lane-scoped Rust IPC/order lifecycle Interface accepted; current Bybit/Paper `submit_paper_order` not reused.
- Python no-write guard green: AST/grep/route tests reject direct IBKR writer methods/endpoints/generic write helpers outside Rust-owned path.
- Signed scoped paper-order envelope includes asset_lane, broker, environment, permission_scope, account/session fingerprint, secret slot fingerprint, expiry, operator, audit id, no-live/no-transfer/no-margin/no-short/no-options flags.
- Fresh Decision Lease, Guardian/risk, cost model, instrument tradability, market session, and paper account attestation all pass in the same final window.
- Paper submit/cancel/replace allowlist is exact and method-specific; reconnect logic cannot resubmit orders automatically.
- Loss controls present: max notional, max loss, max attempts, max concurrency, kill switch, stale-state manual review, post-order reconciliation.
- Append-only order lifecycle audit writes submit/ack/partial/fill/cancel/replace/reject/inactive/unknown transitions with broker ids and hashes.

Gate decision if missing any item: BLOCK before order rehearsal.

### Before any future tiny-live ADR

Mandatory gates:
- Separate ADR/AMD. Paper/shadow success cannot promote into live by inheritance.
- Source-of-truth updates reviewed: ADR, CLAUDE/MEMORY/README/TODO as applicable.
- New IBKR live authorization design with at least the existing five-gate rigor: reserved live mode, Operator role auth, explicit env/global live allow, valid live secret slot, signed unexpired authorization with matching broker/environment/account.
- Live secret material absent until ADR acceptance and E3-approved creation ceremony.
- Broker account permission proof: cash-only if required, no withdrawal/transfer, no margin, no short, no options/CFD, approved instruments only.
- Broker-side protection/rollback design: cancel/close/kill switch, stale order recovery, manual intervention, incident runbook, degraded mode.
- QC/MIT evidence gate: paper/shadow evidence passed pre-registered statistical and execution-realism gates; still only authorizes ADR discussion, not live execution.
- E3 + CC + FA + PA + QC + MIT review, plus a broker/API-specific reviewer assigned by ADR. Existing BB role is Bybit-specific and should not be the only broker-side reviewer for IBKR.

Gate decision if missing any item: BLOCK tiny-live ADR or mark ADR as incomplete.

## Final E3 Decision

Current plan is approved only as a Phase 0 ADR/spec packet. It is not safe for IBKR API contact, secret-slot creation, read-only healthcheck, fill import, paper order rehearsal, GUI runtime activation, evidence clock start, or any tiny-live preparation until the findings above are converted into reviewed, testable gates.

PM-facing gate decision: APPROVE_PHASE0_ONLY
