# AMD-2026-07-09-01: IBKR Credential-Provisioning Write Path (paper/readonly, GUI-triggered, Rust-authority)

Date: 2026-07-09
Status: **DRAFT — pending Operator acceptance + explicit ACK of the new trust face** (not yet in force)
Related ADRs: ADR-0048. Related AMD: AMD-2026-06-29-01, AMD-2026-07-08-01 (which this amendment extends).
Scope: `stock_etf_cash` read-only research lane only. Does **not** touch the Bybit `crypto_perp` runtime path.

> Provenance: PM→CC governance gate (2026-07-09). CC ruled that a GUI-triggered credential-write path is **substantive** (a new trust face, not a CC-level clarification) and requires this Operator-approved amendment before any build. This draft materializes CC's ruling for Operator review. Nothing in the credential-write path (design or code) may begin before the Operator accepts this amendment **and** explicitly acknowledges the new trust face in the sign-off table.

## Why this needs Operator approval (the new trust face)

AMD-2026-07-08-01 authorized a **fingerprint-only read** loader + a **read-only** TWS client + **read-only** external contact. Credential *placement* into the slots was framed as an **out-of-band Operator action** (`E3→BB→Operator`). This amendment introduces a different capability and trust model:

- **New capability:** writing IBKR **paper** credential material into `external/ibkr/{readonly,paper}/` slots through an application-mediated path (GUI form → Rust-authority-validated IPC), rather than the Operator placing the file out-of-band.
- **Changed protected quantity:** secret custody moves from "Operator out-of-band" into an application write path. This touches ADR-0048's secret-creation denial posture, root principle #2 (read/write separation), and AMD-2026-07-08-01 invariant #5 (GUI/client lane state is never authorization).

Because it changes a protected quantity, it is out of scope for a CC-level non-substantive clarification (unlike the 2026-07-09 base-path and approval-model clarifications, which changed no protected quantity). Only the Operator can accept this new trust face.

## Decision (proposed)

Authorize a **Rust-owned credential-provisioning write path** for the `stock_etf_cash` IBKR lane, strictly scoped to **paper and readonly** slots, under an unchanged fail-closed, zero-real-money, read-only-trading posture:

1. A single Rust-owned, `openclaw_engine`-side write path may create/populate `<secrets-root>/external/ibkr/{readonly,paper}/` credential material (e.g., the `account_id` token and paper API credentials).
2. It is triggered via a **single restricted mutating IPC method** on the `stock_etf` lane, invoked by the GUI credential form, with the request authorized by **Rust authority** (Operator-role check), never by GUI/client lane state.
3. Writing to `external/ibkr/live/` is **categorically denied** and structurally impossible in the write path (consistent with AMD-2026-07-08-01 invariant #6: live secret slot absent).

This amendment does **not** approve any IBKR live/tiny-live credential write, any order-write (incl. paper order write), any Python secret write, or any capital exposure. It does **not** change AMD-2026-07-08-01's read-only external-contact scope, the live/tiny-live denial, the fingerprint-only read loader, or the P3 read-only TWS connector authorization.

## Invariants That Never Loosen (the 10 hard guards — all required; any breach = fail-closed / authorization revoked)

1. **Rust-owned backend.** Python stays display-only + thin IPC caller; the Python no-write / no-SDK static guard (`test_stock_etf_python_no_write_static_guard.py`) is **not** revised and remains in force. No Python secret write.
2. **Owner-only permissions.** Slot dirs `0o700`, credential files `0o600`, owner-only ancestor chain, symlink-reject (reuse the P1 loader `ensure_ancestor_owner_only` / `reject_symlink_slot` patterns).
3. **`live/` write categorically denied.** The write path structurally refuses any `live/` target; only `paper` and `readonly` are writable. Live secret slot remains absent.
4. **GUI/client lane state is never authorization.** The mutating request is authorized by Rust authority (Operator-role check); `localStorage` / query / hidden form fields are never trusted.
5. **Plaintext zero-serialization / zero-log.** Credential material is written to the slot file only; it is never returned in any IPC response, written to DB, or logged. The path may return a fingerprint, never plaintext.
6. **paper + readonly only; `OPENCLAW_SECRETS_DIR` not overloaded.** Base resolved via the IBKR-distinct locator (`OPENCLAW_SECRETS_ROOT`, else `$HOME`/`$USERPROFILE` `/BybitOpenClaw/secrets`) + `external/ibkr` (per AMD-2026-07-08-01 clarification #1).
7. **Idempotent + audited + fail-closed.** Write events are audited (fingerprint only, no plaintext); any validation failure → refuse write, no partial state.
8. **No order-write / trading surface.** Pure credential provisioning; `FORBIDDEN_FUNCTION_NAMES` / `FORBIDDEN_IPC_METHOD_STRINGS` retained and never removed.
9. **Restricted mutating-IPC exception (explicit).** The stock_etf lane's current GET-only FastAPI method partition is amended **only** to permit this single restricted mutating credential-provisioning IPC method. No other mutating surface is opened; the GET-only posture holds for everything else.
10. **Non-live triangulation preserved.** Paper credentials written must keep the `FeatureFlagSecretAuthMatrixV1` account-fingerprint triangulation resolving to a **non-live** account.

## Compliance-Gated Sequence (proposed; no step begins before the prior signs off)

| Gate | Content | Sign-off (order) |
|---|---|---|
| G-A0 | This amendment accepted + Operator ACK of the new trust face | **Operator (accept + explicit ACK)** · PM · CC |
| P1.5 | Rust-owned credential-provisioning write path + restricted mutating IPC route | FA → PA → **E3 (secret-custody security review, hard prerequisite)** → E1 → E2 → E4 · E3→BB→Operator |
| (GUI) | GUI credential form (separate GUI-lane workstream) calling the P1.5 IPC route | governed by `gui_lane_contract_v1`; separate sign-off |

## Completion Criteria

Accepted when: (1) Operator accepts + explicitly ACKs the new trust face in the sign-off table; (2) this amendment records the 10 invariants + the restricted mutating-IPC exception; (3) a P1.5 gate row is added to `TODO.md` without implying any live/order write; (4) verification confirms no live credential write, no order-write, no Python secret write, and no Bybit path regression are introduced by the amendment itself (it authorizes the build; it does not perform it).

## Sign-off

| Role | Source | Date | Status |
|---|---|---|---|
| Operator | — | — | **PENDING — must accept + explicitly ACK the GUI-can-write-paper-credentials trust face** |
| PM | Amendment drafting from PM→CC governance gate (2026-07-09) | 2026-07-09 | Draft |
| CC | Governance gate ruling: credential-write path is substantive, requires this Operator-approved amendment; 10 hard guards specified | 2026-07-09 | `CONDITIONAL` — approves-if-amendment-accepted |
| FA / E3 | Functional spec / secret-custody security review | — | Pending at P1.5 (after acceptance) |
