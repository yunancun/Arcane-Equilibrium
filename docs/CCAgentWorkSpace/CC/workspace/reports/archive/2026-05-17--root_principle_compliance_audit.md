# CC Root-Principle Compliance Audit

Audit date: 2026-05-29 Europe/Madrid  
Role: CC(default)  
Repo root: `/Users/ncyu/Projects/TradeBot/srv`  
Commit audited: `5097bd0670277e24516460f6914a85acf9969d87`  
Mutation scope: this report only

## Verdict

No P0 findings.

P1 findings: 3.

P2 findings: 1.

Overall status: conditional compliance. Rust governance, Decision Lease, LiveDemo/Mainnet mapping, and Bybit `retCode` fail-closed behavior are materially present. Full root-principle compliance is blocked by one active live-authority defect, one missing evidence table, and one docs/source-of-truth drift class.

## Evidence Scope

Startup docs inspected: `AGENTS.md`, `CLAUDE.md`, `TODO.md`, `.codex/MEMORY.md`, `.codex/agents/INDEX.md`, `.codex/AGENT_DISPATCH_PROTOCOL.md`, `.codex/SUBAGENT_EXECUTION_RULES.md`, `.codex/agents/CC.md`, `.claude/agents/CC.md`, CC profile/memory, PM baseline, R4 report, and TW report.

Representative commands:

```bash
git rev-parse HEAD
git status --porcelain=v1 -b
rg -n "execution_state|execution_authority|live_execution_allowed|decision_lease_emitted|max_retries|OPENCLAW_ALLOW_MAINNET|live_reserved|authorization.json|retCode" .
rg -n "cancel-all|close_all_positions|Decision Lease|live_demo|Binance" CLAUDE.md README.md rust program_code docs
ssh trade-core 'cd /home/ncyu/BybitOpenClaw/srv && git rev-parse HEAD'
ssh trade-core 'find /home/ncyu/BybitOpenClaw/secrets -maxdepth 3 -name bybit_endpoint -print'
ssh trade-core 'grep -h "^OPENCLAW_ALLOW_MAINNET=\|^OPENCLAW_LEASE_ROUTER_GATE_ENABLED=" /home/ncyu/BybitOpenClaw/secrets/environment_files/basic_system_services.env 2>/dev/null || true'
ssh trade-core 'psql -h 127.0.0.1 -p 5432 -U trading_admin -d trading_ai -Atc "SELECT to_regclass('\''learning.close_maker_audit'\'');"'
```

Runtime read-only observations:

- Mac repo, origin main, and Linux source all resolved to `5097bd0670277e24516460f6914a85acf9969d87`.
- Worktree was already dirty before this report; this audit did not modify those files.
- No `bybit_endpoint` file was found under `/home/ncyu/BybitOpenClaw/secrets` at max depth 3.
- `basic_system_services.env` contains `OPENCLAW_ALLOW_MAINNET=1` and `OPENCLAW_LEASE_ROUTER_GATE_ENABLED=1`.
- `learning.close_maker_audit` returned blank from `to_regclass`.

## Root-Principle Matrix

| # | Status | Notes |
|---|---|---|
| 1 | FAIL-P1 | Single controlled write entry is violated by Python live cancel-all; CC-RP-001. |
| 2 | FAIL-P1 | Read/write separation is violated by the same Python live exchange write. |
| 3 | PASS | Production lease/auth surfaces exist in Rust governance; runtime env source has router gate enabled. |
| 4 | PASS | No strategy bypass of Guardian/risk found in inspected live path. |
| 5 | PASS | Survival-above-profit posture is present; CC-RP-001 is an authority placement defect, not a profit-seeking order path. |
| 6 | PASS | Rust Bybit REST checked helpers fail closed on nonzero `retCode`. |
| 7 | PASS | No learning-to-live mutation path found. |
| 8 | FAIL-P1 partial | Close-maker audit table is absent; CC-RP-002. |
| 9 | PASS with caveat | Local/exchange protection posture exists; cancel-all should still move behind Rust authority. |
| 10 | FAIL-P1 docs | R4/TW source-of-truth drift remains active; CC-RP-004. |
| 11 | PASS | No new capability-throttling violation found. |
| 12 | FAIL-P1 partial | Evidence evolution is weakened by the missing close-maker audit lane. |
| 13 | PASS | No mandatory paid AI dependency found in inspected core paths. |
| 14 | PASS | No mandatory external paid service dependency found. |
| 15 | PASS | Multi-agent dispatch and role rules are formalized in `.codex/` and role docs. |
| 16 | PASS | No new portfolio-risk bypass found; existing edge/backoff work remains tracked separately. |

## Findings

### CC-RP-001 - Python live Stop performs direct Bybit cancel-all write

Label: FACT  
Severity: P1

Affected path + line:

- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/live_session_routes.py:686`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/live_session_routes.py:700`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/live_session_endpoints.py:274`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/live_session_endpoints.py:282`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/bybit_rest_client.py:681`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/bybit_rest_client.py:714`
- Boundary references: `CLAUDE.md:27`, `CLAUDE.md:28`, `CLAUDE.md:30`, `CLAUDE.md:42`, `CLAUDE.md:157`, `README.md:176`

Evidence command or inspection method:

```bash
nl -ba program_code/exchange_connectors/bybit_connector/control_api_v1/app/live_session_routes.py | sed -n '680,714p'
nl -ba program_code/exchange_connectors/bybit_connector/control_api_v1/app/live_session_endpoints.py | sed -n '260,306p'
nl -ba program_code/exchange_connectors/bybit_connector/control_api_v1/app/bybit_rest_client.py | sed -n '681,720p'
nl -ba CLAUDE.md | sed -n '27,60p;154,158p'
nl -ba README.md | sed -n '172,178p'
```

Impact:

Python/FastAPI remains a direct live exchange writer for order cancellation during live Stop. The action is risk-reducing, but it is still an exchange order-management write against Bybit and weakens root principles 1 and 2.

Why this is real, not false positive:

The code explicitly says REST cancel-all is exempt from `_LIVE_REST_FALLBACK_DISABLED`, calls `_sweep_orphan_orders(rc, "live", errors)`, and the client posts to `/v5/order/cancel-all`. This is executable live Python REST write code, not stale documentation.

Suggested fix direction:

Move live cancel-all into the Rust live pipeline behind the same IPC/authority pattern used for `close_all_positions`, or formalize a narrow emergency-stop exception with ADR coverage, 5-gate requirements, audit row, and CC/PA/BB sign-off. Preferred direction is Rust IPC authority.

Fix owner role: E1 with PA boundary design  
Verification owner role: CC + E2, with BB confirming Bybit cancel semantics

### CC-RP-002 - `learning.close_maker_audit` is specified/tracked but not deployed

Label: FACT  
Severity: P1

Affected path + line:

- `TODO.md:209`
- `docs/CCAgentWorkSpace/QA/memory.md:651`
- `docs/CCAgentWorkSpace/QA/memory.md:653`
- `docs/CCAgentWorkSpace/QA/workspace/reports/2026-05-25--phase_1b_acceptance_qa_verify.md:292`
- `docs/CCAgentWorkSpace/QA/workspace/reports/2026-05-25--phase_1b_acceptance_qa_verify.md:479`

Evidence command or inspection method:

```bash
nl -ba TODO.md | sed -n '204,212p'
nl -ba docs/CCAgentWorkSpace/QA/memory.md | sed -n '646,655p'
nl -ba docs/CCAgentWorkSpace/QA/workspace/reports/2026-05-25--phase_1b_acceptance_qa_verify.md | sed -n '288,296p;474,482p'
ssh trade-core 'psql -h 127.0.0.1 -p 5432 -U trading_admin -d trading_ai -Atc "SELECT to_regclass('\''learning.close_maker_audit'\'');"'
```

Impact:

The close-maker adverse-selection monitoring path cannot use the audit table referenced by spec/QA evidence lanes. Operators must reconstruct offline from `trading.fills` and market data, weakening principles 8 and 12.

Why this is real, not false positive:

The live PG `to_regclass('learning.close_maker_audit')` check returned blank, and QA docs independently record the same empirical gap.

Suggested fix direction:

Either deploy the intended migration plus writer/healthcheck wiring, or amend the spec to make `trading.fills` plus market-data joins the canonical evidence lane. Do not leave both truths active.

Fix owner role: PA + E1, with MIT for migration/runtime safety  
Verification owner role: QA + MIT + CC

### CC-RP-003 - Bybit-only boundary is diluted by Binance read-only/future venue stubs

Label: FACT + INFERENCE  
Severity: P2

Affected path + line:

- `CLAUDE.md:27`
- `README.md:9`
- `docs/adr/0033-adr-0006-bybit-binance-amendment.md:14`
- `docs/adr/0033-adr-0006-bybit-binance-amendment.md:15`
- `docs/adr/0033-adr-0006-bybit-binance-amendment.md:23`
- `docs/adr/0033-adr-0006-bybit-binance-amendment.md:60`
- `docs/adr/0033-adr-0006-bybit-binance-amendment.md:82`
- `rust/openclaw_types/src/asset_venue.rs:64`
- `rust/openclaw_types/src/asset_venue.rs:72`
- `rust/openclaw_types/src/asset_venue.rs:75`
- `rust/openclaw_types/src/asset_venue.rs:109`
- `rust/openclaw_engine/src/order_router.rs:375`

Evidence command or inspection method:

```bash
nl -ba CLAUDE.md | sed -n '27,31p'
nl -ba README.md | sed -n '4,10p'
nl -ba docs/adr/0033-adr-0006-bybit-binance-amendment.md | sed -n '1,32p;60,88p'
nl -ba rust/openclaw_types/src/asset_venue.rs | sed -n '1,15p;64,82p;105,112p'
nl -ba rust/openclaw_engine/src/order_router.rs | sed -n '368,383p'
find . -iname '*binance*' -print
```

Impact:

Top-level docs still say Bybit is the only exchange target/adapter, while ADR-0033 approves Binance market-data-only usage and Rust type stubs accept Binance venues. This is not active Binance trading, but it creates governance ambiguity about whether "Bybit-only" means execution-only or all exchange-facing integration.

Why this is real, not false positive:

ADR-0033 explicitly approves Binance market data and `asset_venue.rs` accepts Binance variants. The router returns `VenueDeferred` for Binance trading, so severity is P2 rather than P1.

Suggested fix direction:

Either restore strict Bybit-only wording and remove non-Bybit venue/secret-slot stubs until a new operator decision, or update `CLAUDE.md`/`README.md` to say "Bybit-only execution; registered non-Bybit read-only data exceptions require ADR and cannot trigger strategy/order paths."

Fix owner role: PA + CC + TW  
Verification owner role: R4 + BB + CC

### CC-RP-004 - Source-of-truth drift remains in governance/docs surfaces

Label: FACT  
Severity: P1

Affected path + line:

- `docs/governance_dev/SPECIFICATION_REGISTER.md:133`
- `docs/CCAgentWorkSpace/R4/workspace/reports/2026-05-17--index_integrity_audit.md:21`
- `docs/CCAgentWorkSpace/R4/workspace/reports/2026-05-17--index_integrity_audit.md:66`
- `docs/CCAgentWorkSpace/TW/workspace/reports/2026-05-17--doc_inventory_dedup_audit.md:43`
- `docs/CCAgentWorkSpace/TW/workspace/reports/2026-05-17--doc_inventory_dedup_audit.md:60`
- `docs/CCAgentWorkSpace/Operator/2026-05-09--full_loss_architectural_root_cause_redesign.md:259`
- `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-09--full_loss_architectural_root_cause_redesign.md:260`

Evidence command or inspection method:

```bash
nl -ba docs/governance_dev/SPECIFICATION_REGISTER.md | sed -n '128,136p'
rg -n "P1|ADR-0036|broken|missing|Finding" docs/CCAgentWorkSpace/R4/workspace/reports/2026-05-17--index_integrity_audit.md
nl -ba docs/CCAgentWorkSpace/TW/workspace/reports/2026-05-17--doc_inventory_dedup_audit.md | sed -n '43,83p'
nl -ba docs/CCAgentWorkSpace/Operator/2026-05-09--full_loss_architectural_root_cause_redesign.md | sed -n '255,263p'
nl -ba docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-09--full_loss_architectural_root_cause_redesign.md | sed -n '255,264p'
```

Impact:

Principle 10 is not fully met. The governance register points ADR-0036 through ADR-0041 at dead filenames, and an Operator mirror still carries a stale `liquidation_pulse` revival claim that the PA canonical report retracts. Future roles can follow stale authority surfaces.

Why this is real, not false positive:

The R4 report lists exact registered ADR paths that do not exist while same-number ADRs exist under different filenames. The TW report compares a stale Operator mirror against the corrected PA report, and direct line inspection confirms the Operator copy lacks the PA correction block.

Suggested fix direction:

Fix register paths to actual ADR filenames and add path-existence checking for register entries. Convert Operator mirror reports with material corrections into stubs linking to canonical sources, or copy correction blocks and freeze the mirrors as historical evidence.

Fix owner role: R4 + TW + PM  
Verification owner role: CC + R4

## Hard Boundary Notes

- Bybit-only: active execution remains Bybit-only; Binance trading is explicitly deferred in `rust/openclaw_engine/src/order_router.rs:375`. Wording drift is tracked in CC-RP-003.
- Rust authority: Rust production auth/lease fail-closed logic is present, but Python live cancel-all remains a live write exception; CC-RP-001.
- Read/write separation: research/learning/docs are mostly evidence surfaces. `learning.close_maker_audit` is an evidence gap, not a live mutation path.
- AI output != command: Decision Lease and Production authorization requirements are present in Rust governance; runtime env source has router gate enabled.
- Live/LiveDemo: Rust maps Demo/LiveDemo to `api-demo.bybit.com` and Mainnet to `api.bybit.com`; no current secret endpoint file was found in the checked runtime path.
- Bybit `retCode`: Rust checked helpers call `.into_result()` and error on nonzero `retCode`; no hidden retry-to-fill path was found in scope.

## Blockers To Full Compliance

1. P1 CC-RP-001: move live Stop cancel-all behind Rust authority or formalize a tightly scoped emergency exception.
2. P1 CC-RP-002: deploy or spec-amend the close-maker audit evidence source.
3. P1 CC-RP-004: clear governance/docs source-of-truth drift so future roles do not follow stale facts.
