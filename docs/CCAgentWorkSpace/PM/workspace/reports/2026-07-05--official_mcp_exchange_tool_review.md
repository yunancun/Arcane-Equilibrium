# Official MCP Exchange Tool Review

Date: 2026-07-05
Repo head: `70d1143166a41edf127af4a745348baba8ff9159`
Scope: source-only architecture review for IBKR and Bybit official MCP / connector surfaces.

## Verdict

Do not replace current execution infrastructure with official MCP tools.

Use the official tools as reference material and optional future read-only diagnostics only. The project should preserve Rust-owned authority, Decision Lease, Guardian, Cost Gate, audit/reconstructability, and exchange-specific fail-closed handling.

Shortened chain note: this is PM local synthesis using CC/FA/PA lenses. No sub-agents were spawned because the user did not explicitly request sub-agent work and this task is documentation/review only. E3/BB are required before any future exchange-facing runtime use.

## Non-Actions

This review did not:

- install or configure MCP in Codex, Claude, VS Code, Cursor, or the runtime host
- read, create, copy, or validate any Bybit or IBKR credential
- run a Bybit or IBKR API call
- start IB Gateway, TWS, or an MCP server
- change runtime, DB, crontab, env, service, Cost Gate, Decision Lease, Guardian, or adapter state
- grant order, probe, paper, live, tiny-live, or promotion authority

## Sources Checked

Official external sources:

- IBKR AI integrations page: `https://www.interactivebrokers.com/en/trading/ai-integrations.php`
- IBKR Claude / ChatGPT connector guide: `https://www.interactivebrokers.com/campus/traders-insight/ibkr-toolbox/how-to-connect-claude-ai-and-chatgpt-to-your-ibkr-account/`
- IBKR API home: `https://www.interactivebrokers.com/campus/ibkr-api-page/ibkr-api-home/`
- Bybit official MCP repo: `https://github.com/bybit-exchange/trading-mcp`
- npm metadata: `bybit-official-trading-server@2.1.15`, repository `github.com/bybit-exchange/trading-mcp`

Repo sources:

- `docs/adr/0048-ibkr-stock-etf-paper-shadow-lane.md`
- `docs/governance_dev/amendments/2026-06-29--AMD-2026-06-29-01-ibkr-stock-etf-paper-shadow-lane.md`
- `program_code/broker_connectors/ibkr_connector/`
- `rust/openclaw_types/src/ibkr_non_bybit_api_allowlist.rs`
- `rust/openclaw_types/src/ibkr_phase2_gate.rs`
- `rust/openclaw_engine/src/bybit_rest_client.rs`
- `README.md`, `CLAUDE.md`, `TODO.md`

## IBKR Assessment

### Facts

IBKR's official AI integration is a broker-hosted connector workflow. IBKR says it acts as the MCP server, keeps control of authentication, and does not pass login credentials to the AI platform. The connector exposes account context such as positions, balances, trades, open orders, margin, and market data after explicit authorization.

IBKR also states Claude and ChatGPT do not place trades directly. They generate structured trade instructions, which appear inside IBKR's trading platform for investor review/edit/discard before any live order submission. Current launch scope described by IBKR is equities and ETFs, market and limit orders.

### Repo Fit

This security model is directionally aligned with our root principles: AI output is a proposal/instruction, not an immediate command; execution remains behind a human or local authority gate.

But it is not a drop-in runtime for ADR-0048. Our accepted baseline is IB Gateway + TWS API over loopback paper, with Phase 2 external-surface gate, session attestation, separate secret slots, Rust authority, scoped authorization, and no Client Portal Web API. The current Python connector package is explicitly inert: typed blocked previews only, no SDK import, no socket/HTTP, no secret read, no broker write method.

### Decision

Do not replace the `stock_etf_cash` IBKR plan with the official Claude/ChatGPT connector.

Borrow the human-in-the-middle pattern for UI and governance design: AI can propose a structured instruction; local system must convert it to a Decision Lease / scoped authorization packet; only Rust-owned paper authority may rehearse broker-paper behavior after gates pass.

If future work wants to consider IBKR's official hosted connector, it needs a new ADR/AMD because it changes the API baseline from loopback IB Gateway/TWS to broker-hosted AI connector / platform instruction flow.

## Bybit Assessment

### Facts

Bybit's official `trading-mcp` repo exposes Bybit V5 REST and WebSocket capabilities as MCP tools. Its README describes a production-ready MCP server with broad coverage: market, account, trade, RFQ, position, asset, user, spread trading, bot, earn, P2P, card, alpha, websocket, and WS trade categories. Market tools can operate without API keys; authenticated tools use environment variables such as `BYBIT_API_KEY`, `BYBIT_API_SECRET`, `BYBIT_API_PRIVATE_KEY_PATH`, and `BYBIT_TESTNET`.

Local source sampling of the public repo showed a direct MCP `CallTool` handler calling tool handlers after schema validation. The REST client selects testnet only when `BYBIT_TESTNET === "true"`; otherwise it uses mainnet. Auth is loaded from process env and request signing is handled inside the server. The sampled code did not expose project-equivalent Decision Lease, Guardian, Rust authority, Cost Gate, candidate identity, or reconstructability gates.

### Repo Fit

Bybit MCP is useful as an official API coverage index and possibly as a human-operated diagnostic tool outside the trading runtime.

It is not acceptable as an execution replacement. Our Rust `BybitRestClient` already owns Bybit signing, demo/testnet/mainnet environment mapping, private WS topic policy, response header rate-limit tracking, latency instrumentation, retCode fail-closed incident handling, and downstream integration with order/intent governance. Replacing that with MCP would route order-capable actions through an AI tool boundary instead of the single controlled write entry.

Specific risk deltas:

- MCP tools are too broad for our runtime. They include user/account management, bot, earn, P2P, card, alpha, spread/RFQ, and WS trade surfaces beyond the current approved Bybit execution envelope.
- Environment-variable credential loading conflicts with our secret-slot and signed authorization model.
- Mainnet default when `BYBIT_TESTNET` is not explicitly true is incompatible with this project's fail-closed posture.
- MCP tool invocation is not equivalent to Decision Lease + Guardian + Rust authority + audit lineage.

### Decision

Do not route Bybit orders, account writes, private reads, Earn writes, asset movements, or strategy actions through Bybit MCP.

Potentially use the official repo as an offline comparison source for:

- endpoint/tool coverage drift against `docs/references/2026-04-04--bybit_api_reference.md`
- auth-category classification
- market-data public tool list
- WebSocket topic inventory
- error/rate-limit documentation cross-checks

Any actual exchange-facing invocation via MCP requires a separate PM -> E3 -> BB review and should start, if ever, with no-key public market-data only.

## Replacement Matrix

| Surface | Replace with official MCP? | Reason |
|---|---:|---|
| Bybit live/demo order execution | No | Would bypass Rust authority, Decision Lease, Guardian, Cost Gate, and audit reconstruction. |
| Bybit public market-data reference | Maybe, source-only | Useful for tool/endpoint inventory comparison; no runtime call needed. |
| Bybit private account diagnostics | No for now | Credentials/env boundary conflicts with current secret-slot and authorization model. |
| Bybit manual operator diagnostics | Maybe later | Only under separate E3/BB-reviewed, read-only, sanitized, no-order envelope. |
| IBKR `stock_etf_cash` paper/shadow runtime | No | Current ADR baseline is IB Gateway/TWS loopback, not hosted AI connector. |
| IBKR AI instruction UX | Yes, as pattern | Human-in-the-middle instruction review maps well to Decision Lease/operator review. |
| IBKR account/portfolio conversational analysis | Maybe outside runtime | Could be operator-side research, not project truth or evidence lane, unless a new ADR imports sanitized artifacts. |

## Borrowable Ideas

1. Official capability taxonomy

Bybit's auth-category table is a good model for our own capability registry: every tool/endpoint should be bucketed into public read, private read, paper write, live write, account-management write, asset movement, and denied.

2. Explicit human-in-the-middle wording

IBKR's connector messaging is clearer than typical "AI trading" tools: AI generates instructions; the trading platform remains the place where execution is reviewed and submitted. Our GUI / Gateway copy should keep this distinction.

3. Connector-side credential minimization

IBKR's hosted connector avoids passing login credentials to the AI platform. For our local system, equivalent posture means no env fallback, no secret serialization, fingerprint-only status, and explicit redaction evidence.

4. Tool surface freeze

The Bybit MCP tool breadth is exactly why our project needs a deny-by-default MCP capability matrix before any future tool integration. Broad official coverage is a risk unless narrowed by a local allowlist.

5. No-key public diagnostics

Bybit's no-key market-data split can inspire a source-only or optional public-only diagnostic lane, but it must remain separate from current bounded Demo execution envelopes and cannot clear Cost Gate or proof by itself.

## Proposed Follow-Up Tickets

1. `P2-OFFICIAL-BYBIT-MCP-TOOL-INVENTORY-SOURCE-ONLY`

Create a static inventory generator that reads the official Bybit MCP repo/package metadata offline and emits a denied-by-default tool matrix. No credentials, no MCP server start, no exchange calls.

Acceptance:

- categories and tool names captured with package version and source hash
- each tool mapped to public read / private read / trade write / account write / asset movement / denied
- no runtime integration, no credential read, no npm install inside repo, no API call

2. `P2-BYBIT-REFERENCE-DRIFT-CROSSCHECK-OFFICIAL-MCP`

Compare official MCP market/account/trade/websocket coverage against our Bybit reference document and Rust client coverage. This is documentation/test input only.

Acceptance:

- list of possible missing endpoints/topics
- list of endpoints intentionally denied by project policy
- BB review before any reference doc update

3. `P2-IBKR-OFFICIAL-CONNECTOR-PATTERN-ADR-NOTE`

Add an ADR note or appendix clarifying that IBKR's official AI connector is a pattern reference, not ADR-0048 runtime baseline.

Acceptance:

- preserves IB Gateway/TWS loopback baseline
- records that hosted connector import would need new ADR/AMD
- maps IBKR "AI Instructions tab" to our proposal/Decision Lease language

## PM Sign-Off

PM SIGN-OFF: CONDITIONAL.

Approved only for source-only documentation and future offline inventory work. Blocked for any runtime MCP integration, credential configuration, exchange contact, private/account read, paper order, Bybit order, live/tiny-live, Cost Gate change, proof claim, or promotion use.
