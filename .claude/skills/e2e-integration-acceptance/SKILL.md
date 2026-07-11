---
name: e2e-integration-acceptance
description: QA read-only verifier；只有任務宣稱 end-to-end、runtime-backed business outcome、major GUI journey 或 phase/wave acceptance 時使用。
allowed-tools: Read, Grep, Glob, Bash
---

# E2E Integration Acceptance

> Authority 使用 `.codex/agent_registry_v1.json` typed matrix。Normative
> permission、source contract、active TODO、runtime observation、external policy、
> claim evidence 分類保留；runtime 綠不能合法化 policy denial。

## Activation

Use QA only when completion claims a real cross-Interface outcome. Narrow source
changes without an E2E/runtime claim stop at relevant source review/tests; QA is
not ceremony.

## Permission

QA is read-only. It does not implement fixes, deploy/restart, write PG, read raw
secret content, mutate auth/risk/config, contact private broker effects, or write
role reports/memory. Every Bash command must pass:

```bash
python3 helper_scripts/maintenance_scripts/agent_governance.py authorize-command \
  --role QA --command "<exact command>"
```

If an effect is needed, return the exact OPS/Deploy/Broker Adapter intent and
wait for new evidence; do not perform it as QA.

## Acceptance design

Map each operator-visible acceptance item to one or more direct evidence refs:

- source contract and direct caller
- focused/broad test capsule (EXECUTED or exact REUSED)
- runtime host/environment/head/build/observed_at/expiry
- API/IPC/schema boundary
- browser screenshot/trace/viewport/keyboard/accessibility evidence for GUI
- audit/reconstructability/denial evidence
- correct BB or IB venue compatibility fragment

An item without evidence is `UNVERIFIED`, never inferred PASS from test count or
source readiness.

## Core checks

### Business journey

- Trace the actual input -> authority/gate -> effect/read -> persisted state ->
  operator feedback chain.
- Verify failure/recovery and honest error state, not only happy path.
- Check source/runtime generations align; stale evidence remains visible.
- Distinguish source-ready, deployed, active, authorized, and profit-proven.

### Cross-language/process

- Python/Rust IPC schema and error semantics align.
- Rust remains trading/risk/config authority; GUI/Python do not fake success.
- Process outage/reconnect behavior is observed through an approved read-only
  health surface; QA does not create the outage.
- DB/API/GUI terms and identity keys remain consistent.

### GUI visual/accessibility

- Use a real browser capability when available; do not replace it with a prose
  screenshot description.
- Cover relevant viewport matrix, keyboard navigation/focus, accessibility tree,
  loading/empty/error/stale states, destructive confirmations, and recovery.
- Capture artifact digest and timestamp; source inspection alone is not visual
  acceptance.

### Hard boundaries

- Load the exact applicable Root Principle/Hard Boundary/ADR denial.
- Verify existing typed gate evidence without exposing secret values.
- Bybit LiveDemo remains live-grade; IBKR remains ADR-0048 read-only/paper/shadow
  and live/tiny-live denied.
- Missing/expired authorization or stale runtime proof blocks the claim.

## Evidence freshness

Runtime evidence requires host, environment, source/runtime head, observed_at,
expiry, and digest. A cached runtime health result outside TTL is UNVERIFIED.
Test proof uses the content-addressed signature from Development-Agent
Governance. Failed/flaky/critical evidence is not reused as green.

## Verdict

QA returns immutable `role_fragment_v1` with `payload_kind=gate_fragment_v1` with:

- work status and gate verdict (DONE+FAIL is valid)
- acceptance criterion -> evidence mapping
- source/runtime/external scopes and freshness
- browser/accessibility artifacts when applicable
- FACT/INFERENCE/ASSUMPTION + confidence
- concerns, skipped/unverified scope, side effects
- next owner/action

QA does not automatically write a report or memory. PM merges the fragment into
one `closure_packet_v1`; PM cannot override QA hard failure without new evidence.

## Anti-patterns

- Always running QA for a docs-only or narrow source change
- Treating E4 passed count as business-chain proof
- Treating Mac engine absence as Linux runtime failure
- Running restart, auth, broker, PG-write, or secret-inspection commands as QA
- Accepting a GUI path without real visual evidence when visual outcome is claimed
- Declaring stable from one stale snapshot or an unexpired-window assumption
- Hiding a failed criterion behind overall DONE
