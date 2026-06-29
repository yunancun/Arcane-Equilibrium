# CC 合規審查 — IBKR Stock/ETF Paper + Shadow Plan

日期：2026-06-29
角色：CC(default)
範圍：`docs/execution_plan/2026-06-29--ibkr_stock_etf_paper_shadow_development_arrangement.md` 對 16 根原則、Rust authority、讀寫分離、Bybit-only execution boundary、live authorization hard gates 的相容性審查。
限制：operator 明確要求只寫本報告；未按 CC role 預設流程追加 `docs/CCAgentWorkSpace/CC/memory.md` 或複製 Operator mirror。

## Verdict

**狀態：DONE_WITH_CONCERNS**
**評級：B / Conditional**
**批准範圍：只批准 Phase 0 governance / ADR / spec review。**
**不批准範圍：Phase 1+ 實作、IBKR API 呼叫、IBKR secret slot 建立、IBKR paper order placement/cancel/replace、GUI lane runtime enable、TODO active implementation row、任何 IBKR live/tiny-live 探索。**

核心判斷：

- 以「設計提案 / 尚未開工 / 不授權任何非 Bybit 實盤交易」的現狀看，本計劃沒有造成已生效的 runtime 或 code boundary violation。
- `stock_etf_cash` 作為 research namespace / GUI filter 本身不構成 execution authority；但一旦它能選路到 adapter 或改變 order path，它就是交易控制上下文，必須納入 Rust authority + Decision Lease + Guardian + audit。
- `IBKR paper` 不是 live/mainnet，但它是對外 broker paper account 的 order-capable surface。若可 submit/cancel/replace，它必須被視為「非 Bybit、非 live、但 broker-paper execution authority」，不能被降格為純 research/read-only。
- 提案中的 Phase 0 ADR 是必要條件，但目前文字仍不足以單獨防止 boundary drift；Phase 0 ADR 必須把 `read-only`、`paper fill import`、`paper order rehearsal`、`live reserved` 四個 scope 分開定義並機器可檢查。

Finding counts: Critical 0 / High 1 / Medium 4 / Low 2 / Info 3.

## Sources

- `CLAUDE.md`: product boundary says Bybit is the only execution exchange, Rust is authority, Python is control/bridge, and root principles/hard gates are binding (`CLAUDE.md:27-32`, `CLAUDE.md:43-64`, `CLAUDE.md:81-99`).
- `.codex/MEMORY.md`: repeats Bybit-only target, Rust authority, Python non-truth-layer boundary, and current no-order/lease discipline (`.codex/MEMORY.md:97-140`, `.codex/MEMORY.md:155-160`).
- `README.md`: Bybit is the only order/execution adapter and current paper tab is archive/diagnostic, not promotion (`README.md:9`, `README.md:28-30`, `README.md:50`).
- `ADR-0001`: Rust `openclaw_engine` is sole trading authority; Python is bridge (`docs/adr/0001-rust-as-trading-authority.md:6-8`).
- `ADR-0006`: Bybit is sole exchange; new venue abstractions should not over-generalize (`docs/adr/0006-bybit-only-exchange.md:6-12`).
- `ADR-0033/0040`: non-Bybit exception precedent is Binance market-data-only; future trading requires explicit ADR gates, per-venue authorization, operator approval, and fail-closed design (`docs/adr/0033-adr-0006-bybit-binance-amendment.md:60-87`; `docs/adr/0040-multi-venue-gate-spec.md:73-127`).
- IBKR plan: declares paper/shadow-only intent, ADR-first unlock, Rust authority, Python no direct order, fail-closed live, and evidence requirements (`docs/execution_plan/2026-06-29--ibkr_stock_etf_paper_shadow_development_arrangement.md:3-24`, `:42-48`, `:119-140`, `:217-246`, `:389-409`, `:527-557`).
- Index check: initiative is not yet active TODO work and needs Phase 0 approval first (`docs/_indexes/initiative_index.md:21-23`).

## Findings

### HIGH-1 — `IBKR paper` can become hidden non-Bybit execution authority if treated as harmless research

Evidence:

- The plan allows “IBKR paper account order lifecycle rehearsal” (`...arrangement.md:16-18`) and proposes `ibkr_paper_execution_adapter` (`...arrangement.md:135-137`).
- It also proposes `OPENCLAW_IBKR_PAPER_ENABLED` for “paper order rehearsal” (`...arrangement.md:221-224`) and Phase 2 “paper-only order lifecycle rehearsal” (`...arrangement.md:431-439`).
- Current governance says Bybit is the only execution exchange and Rust is authority (`CLAUDE.md:27-32`; `ADR-0006:6-12`).

Assessment:

No active violation exists because this is docs-only and Phase 0 says no IBKR API/runtime work (`...arrangement.md:557`). But if implemented without a new ADR, paper order placement/cancel/replace would create a second non-Bybit outbound order surface. Paper account does not equal live capital risk, but it still creates broker-side order state, audit obligations, and execution semantics.

Required Phase 0 condition:

- ADR must explicitly classify IBKR paper submit/cancel/replace as **order-capable broker-paper execution**, not read-only.
- ADR must define that shadow signals and paper fill import are research/read-only, while paper order rehearsal is write/effect-capable and requires Rust-owned gating.
- No Phase 1+ code, no secret slots, no IBKR paper API calls, and no TODO active implementation row until this classification is accepted.

### MEDIUM-1 — Phase 0 gate is necessary but currently too loose if “operator explicit approval” bypasses formal ADR/AMD capture

Evidence:

- Plan correctly says formal work requires a new ADR/AMD before changing Bybit-only execution (`...arrangement.md:22-24`) and Phase 0 creates the ADR (`...arrangement.md:389-399`).
- Acceptance says “ADR accepted 或 operator 明確批准” (`...arrangement.md:405-409`).
- Existing source routing treats `CLAUDE.md`, `.codex/MEMORY.md`, README, TODO, and ADRs as source-of-truth files, not hidden chat state (`docs/agents/context-loading.md:8-21`, `.codex/MEMORY.md:47-63`).

Assessment:

Operator approval is valid only if it is durable, scoped, and reflected into the governance record before implementation. A chat-only “explicit approval” would not be enough to amend ADR-0006 / CLAUDE / README boundary language.

Required Phase 0 condition:

- Treat “operator explicit approval” as acceptable only when captured as an ADR/AMD or report-backed governance decision with scope, expiry if any, and implementation prohibitions.
- Before any implementation row, update the relevant source-of-truth documents or explicitly record why an ADR-only amendment is sufficient.

### MEDIUM-2 — Python IBKR connector must remain import/health/read-only; outbound paper orders must not be implemented in Python

Evidence:

- Plan proposes `program_code/broker_connectors/ibkr_connector/paper_client.py` and `readonly_client.py` (`...arrangement.md:165-175`).
- It says Python connector is API client / healthcheck / fixtures / paper fill import helper (`...arrangement.md:178-179`) and Python routes have no direct order submission unless routed through Rust IPC (`...arrangement.md:155-159`).
- ADR-0001 restricts Python to bridging and read-only proxying while Rust owns trading/risk/config/execution authority (`ADR-0001:6-8`).

Assessment:

The plan’s intent is mostly correct, but `paper_client.py` is a naming/API risk. If Python contains callable `place_order`, `cancel_order`, or `replace_order`, then Python becomes a broker-write adapter even if Rust approved the decision upstream. That would weaken the Rust authority boundary and make audit ownership ambiguous.

Required Phase 0 condition:

- ADR/spec must forbid Python IBKR connector methods that perform submit/cancel/replace.
- If IBKR paper order rehearsal is ever allowed, the outbound adapter must be Rust-owned, or a Rust-owned subprocess boundary must be specified with no autonomous Python write API.
- Tests/static scans should reject Python IBKR write method names and any route that calls broker-write APIs directly.

### MEDIUM-3 — Per-lane authorization schema is only sketched; it must become fail-closed before any paper order rehearsal

Evidence:

- Plan proposes flags and external secret slots (`...arrangement.md:217-234`) plus future auth fields (`...arrangement.md:236-246`).
- Live hard gates require `live_reserved`, Operator auth, `OPENCLAW_ALLOW_MAINNET=1`, valid secret slot, and signed unexpired `authorization.json` (`CLAUDE.md:81-88`).
- ADR-0040’s precedent requires venue-aware authorization and fail-closed per-venue outbound orders (`ADR-0040:73-88`, `ADR-0040:117-127`).

Assessment:

The plan is right not to reuse Bybit live authorization, but it has not yet defined exact paper/read-only authorization semantics. IBKR read-only, paper fill import, paper order rehearsal, and live reserved must not share one broad “IBKR enabled” meaning.

Required Phase 0 condition:

- Define separate permission scopes: `ibkr_readonly_health`, `ibkr_paper_fill_import`, `ibkr_paper_order_rehearsal`, and `ibkr_live_reserved`.
- Require signed, scoped, expiring envelopes for any paper order rehearsal.
- Define fail-closed behavior for missing/mismatched `asset_lane`, `broker`, `environment`, `permission_scope`, secret fingerprint, TTL, Decision Lease, Guardian, risk config, and audit sink.

### MEDIUM-4 — `OPENCLAW_IBKR_LIVE_ENABLED` should not become an executable toggle

Evidence:

- Plan proposes `OPENCLAW_IBKR_LIVE_ENABLED=0` and says it must permanently fail-closed until another live ADR (`...arrangement.md:221-224`).
- It also proposes a reserved live secret slot path (`...arrangement.md:230-233`) and `IbkrLiveReserved` enum (`...arrangement.md:85-89`).

Assessment:

The plan intends fail-closed live, but a live-looking env var is a drift hazard. Current live gates are intentionally multi-factor and signed; a single env key must never be able to unlock an IBKR live path.

Required Phase 0 condition:

- Prefer a compile/runtime hard error for `IbkrLiveReserved` over implementing a general `OPENCLAW_IBKR_LIVE_ENABLED` branch.
- If the key exists for UI display, static tests must prove it is not consumed by any outbound order path.
- Do not create the IBKR live secret directory during paper/shadow work; reserved path should remain absent or explicitly empty.

### LOW-1 — `stock_etf_cash` lane selector is safe only as display/filter state

Evidence:

- Plan adds a post-login lane selector and says GUI selector is not trading authority (`...arrangement.md:52-59`, `...arrangement.md:252-259`, `...arrangement.md:42-48`).
- Existing GUI/control plane is not a trading truth layer (`CLAUDE.md:31-32`).

Assessment:

The selector is compatible if it only scopes reads and operator navigation. It becomes authority if “active lane state” mutates adapter choice, risk config, or order routing without Rust revalidation.

Required Phase 0 condition:

- ADR/spec should declare `asset_lane` supplied by GUI as untrusted input.
- Rust must independently validate lane, broker, environment, risk config, auth scope, and allowed operation on every effect-capable request.

### LOW-2 — Paper/shadow evidence language must stay research-only and lane-local

Evidence:

- Plan states IBKR paper fill is not live proof (`...arrangement.md:200-203`) and no auto-upgrade from paper to tiny-live is allowed (`...arrangement.md:542-547`).
- Existing project boundary says paper is not active promotion evidence unless a future explicit operator decision reopens it (`CLAUDE.md:97-99`; `README.md:28-30`).

Assessment:

The plan is aligned, but Phase 0 should prevent future readers from treating IBKR paper/shadow as promotion evidence for Bybit live, IBKR live, or global strategy promotion.

Required Phase 0 condition:

- Scorecards must carry `asset_lane`, `broker`, `environment`, `synthetic_shadow`/`broker_paper`, cost model version, and proof exclusion labels.
- Any later tiny-live discussion must start a new ADR/spec and cannot inherit authorization from paper/shadow success.

## Info / Positive Findings

### INFO-1 — No current code/runtime IBKR authority was found

Repository search for `IBKR`, `Ibkr`, `stock_etf_cash`, `OPENCLAW_IBKR`, `AssetLane`, `BrokerVenue`, `IbkrPaper`, and `IbkrLiveReserved` found occurrences only in the execution plan and document indexes, not in runtime code. `git status --short --branch` was clean before this report was written.

### INFO-2 — The plan preserves core Rust authority in stated intent

The plan explicitly says any order-capable path must remain Rust-owned and Python can only forward operator requests or read state (`...arrangement.md:139-140`), and acceptance requires paper order path through Rust authority (`...arrangement.md:531-535`).

### INFO-3 — ADR-0040 is useful precedent but not authority for IBKR

ADR-0040 provides the correct shape for venue-aware gates, per-venue auth, hardcoded enums, and operator-only venue changes (`ADR-0040:73-127`), but it only amends the Binance path and does not approve stock broker execution (`...arrangement.md:30-34`).

## 16 Root Principles Matrix

| # | Principle | Status | CC assessment |
|---|---|---|---|
| 1 | Single controlled write entry | CONCERN | Compatible only if IBKR paper submit/cancel/replace has one Rust-owned write entry; otherwise hidden second venue authority. |
| 2 | Read/write separation | CONCERN | Read-only health, fill import, and shadow are fine; Python paper client must not become broker-write layer. |
| 3 | AI output is not command | PASS-WITH-CONDITION | Shared Decision Lease semantics are planned; paper order rehearsal must require a fresh scoped lease, not a reusable review artifact. |
| 4 | Strategies cannot bypass Guardian | PASS-WITH-CONDITION | Guardian/veto shared across lanes is planned; Phase 0 must define stock-specific cash/no-short/no-margin risk gates. |
| 5 | Survival above profit | PASS | Plan forbids live, margin, short, options, CFD, transfers, and auto-upgrade; this is conservative. |
| 6 | Uncertainty defaults conservative | PASS | Default flags are off; live reserved is fail-closed; evidence clock starts after stability prerequisites. |
| 7 | Learning must not rewrite live | PASS | Paper/shadow cannot auto-promote to live; later tiny-live requires separate ADR/spec. |
| 8 | Reconstructable trades | PASS | Plan requires reconstructable paper/shadow fills, broker IDs, costs, and scorecard lineage. |
| 9 | Local + exchange-side protection | N/A-WITH-CONDITION | For paper/shadow, live protection claims are not applicable. Future live would require a new broker-side protection design. |
| 10 | Separate fact/inference/assumption | PASS | Plan distinguishes current facts, assumptions, and prohibited actions. |
| 11 | Agent autonomy inside P0/P1 | PASS-WITH-CONDITION | No autonomous venue enable; Phase 0 review chain keeps venue change under governance. |
| 12 | Evidence over anecdotes | PASS | 6-8 week after-cost evidence, benchmark comparison, and sample-size/statistical requirements are planned. |
| 13 | AI calls justify edge | PASS/INFO | Not central to this plan; evidence design is cost-aware for trading costs. Any AI-assisted stock research must inherit existing AI cost gates. |
| 14 | Baseline operable without paid services | PASS-WITH-CONDITION | IBKR must remain optional. Crypto/Bybit baseline must operate when stock lane is disabled or IBKR unavailable. |
| 15 | Formal multi-agent collaboration | PASS | Phase 0 review chain includes CC/FA/PA/E3/QC/MIT/PM. |
| 16 | Portfolio-level risk | PASS-WITH-CONDITION | Plan includes concentration/overnight caps and lane-specific risk; ADR must define cross-lane exposure aggregation before any live discussion. |

## Hard Boundary Review

- **Bybit-only boundary:** Currently intact. The plan itself says ADR-0006 remains in force and requires a new ADR before work (`...arrangement.md:30-34`, `...arrangement.md:391-409`). However, IBKR paper order rehearsal is outside the existing accepted non-Bybit read-only exception and therefore must not proceed under current governance.
- **Rust authority:** Compatible in intent, not yet proven in design. The future ADR/spec must make the Rust-owned adapter boundary machine-checkable and prevent Python broker-write APIs.
- **Read/write separation:** Compatible for read-only health, account snapshot, fill import, and shadow collection. Paper order rehearsal is write/effect-capable and must be separated from research/fill-import surfaces.
- **Live authorization hard gates:** No live gate is currently changed. Proposed IBKR live fields must remain reserved, non-executable, and not convertible into a one-flag live path.
- **Paper promotion boundary:** Plan is compatible only if IBKR paper/shadow remains research-only and cannot satisfy existing Bybit Demo/live promotion gates.

## Required Phase 0 ADR Acceptance Criteria

1. Explicitly amend ADR-0006 only for `stock_etf_cash` read-only / shadow / broker-paper research scope; no IBKR live, no margin, no short, no options, no CFD, no transfers.
2. Classify operations by authority:
   - read-only: healthcheck, account snapshot, market data, paper fill import;
   - research-only: shadow signal/fill reconstruction;
   - order-capable: IBKR paper submit/cancel/replace rehearsal;
   - forbidden/reserved: any IBKR live.
3. Define per-lane authorization envelopes with `asset_lane`, `broker`, `environment`, `permission_scope`, `secret_slot_fingerprint`, TTL, and audit ID.
4. Require Rust-owned order-capable adapter path; Python IBKR connector may not expose submit/cancel/replace APIs.
5. Make `stock_etf_cash` GUI lane selector display/filter-only; every effect-capable operation must be revalidated by Rust.
6. Add static/focused tests for: default-off flags, absent live secret slot, no Python broker-write methods, live reserved hard error, missing/mismatched authorization fail-closed, no reuse of Bybit live authorization.
7. Require source-of-truth sync before implementation: ADR/AMD accepted, then PM decides/records required updates to `CLAUDE.md`, `.codex/MEMORY.md`, `README.md`, and `TODO.md` before active implementation begins.

## Final CC Decision

**Conditional pass for Phase 0 only.**
The plan is directionally compatible with the 16 root principles if and only if Phase 0 is treated as a hard governance unlock and resolves the findings above before implementation. `IBKR paper` must not be treated as pure read-only research; it is a broker-paper order-capable surface once it can place/cancel/replace orders. `stock_etf_cash` is safe as a lane label/filter, but not as a runtime authority switch. Phase 0 is necessary, but as currently worded it is not sufficient by itself to prevent boundary drift.
