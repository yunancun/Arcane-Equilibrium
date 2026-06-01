# AEG-S1-FND-3 Side-Evidence Artifact Contract

Date: 2026-06-01
Status: PM/PA/QC contract complete; implementation still blocked until scoped separately
Owner chain: PM -> PA + QC -> E1 only after a separate artifact implementation scope
Mode: docs/design/read-only. No DB write, migration apply, retention mutation, runtime deploy, auth, order, collector runtime, endpoint ingestion, backfill run, alpha scoring, or promotion verdict.

## Verdict

FND-3 defines `side_evidence.json` as an optional child artifact for Alpha-Edge
research runs. It is secondary-only narrative/event context and is explicitly
excluded from promotion gates.

Positive side evidence cannot rescue a failed mathematical verdict. Missing,
stale, or negative side evidence cannot by itself fail a mathematical PASS.
Reports may say the context is consistent or inconsistent with a run; they must
not call side evidence proof of alpha.

## 1. Artifact Placement

The future runner may emit:

```text
${OPENCLAW_DATA_DIR:-/tmp/openclaw}/alpha_history_runs/<run_id>/side_evidence.json
```

`run_id` must match the parent AEG manifest. If the file exists, it must be
digested in both `manifest.json.artifacts` and `artifact_index.json`.

Required index metadata:

| Field | Requirement |
|---|---|
| `path` | Relative path under the run root. |
| `sha256` | Digest of the exact file bytes. |
| `byte_size` | Non-negative file byte size. |
| `row_count` | `items.length`; zero is allowed. |
| `schema_version` | `aeg.side_evidence.v0.1`. |
| `role` | `secondary_only`. |

## 2. Top-Level Schema

Minimum schema:

```json
{
  "schema_version": "aeg.side_evidence.v0.1",
  "run_id": "same-as-manifest",
  "created_at_utc": "ISO-8601",
  "window_start_utc": "inclusive",
  "window_end_utc": "exclusive",
  "closed_bar_cutoff_utc": "same-or-earlier-than-manifest",
  "policy": {
    "role": "secondary_only",
    "promotion_use": "excluded_from_promotion_gates",
    "may_change_final_label": false,
    "may_override_math_failure": false
  },
  "provenance": {
    "git_sha": "same source checkout",
    "git_dirty": false,
    "collector_or_query_version": "string",
    "source_surfaces": ["market.news_signals", "external_artifact"],
    "query_digest_sha256": "sha256-or-null"
  },
  "summary": {
    "item_count": 0,
    "category_counts": {},
    "max_severity": null,
    "coverage_notes": [],
    "limitations": []
  },
  "items": []
}
```

Required policy invariants:

- `policy.role = "secondary_only"`
- `policy.promotion_use = "excluded_from_promotion_gates"`
- `policy.may_change_final_label = false`
- `policy.may_override_math_failure = false`

Any future parser or validator must fail closed if these invariants are absent
or false.

## 3. Item Schema

Each `items[]` row must be a bounded, source-linked context annotation:

```json
{
  "item_id": "stable-hash",
  "source_category": "news",
  "source_name": "cryptopanic-or-rss-or-x-or-reddit-or-note",
  "source_url": "url-or-null",
  "published_at_utc": "ISO-8601",
  "observed_at_utc": "ISO-8601",
  "title_or_excerpt": "short text",
  "affected_symbols": ["BTCUSDT"],
  "is_market_wide": false,
  "event_category": "macro",
  "sentiment": null,
  "severity": 0.0,
  "confidence": null,
  "provenance_ref": {
    "db_table": "market.news_signals",
    "db_primary_key": null,
    "raw_payload_sha256": "sha256-or-null"
  },
  "allowed_use": "context_annotation_only",
  "forbidden_use": [
    "alpha_signal",
    "promotion_gate_input",
    "math_verdict_override",
    "direct_trading_input"
  ]
}
```

Allowed `source_category` values:

- `news`
- `x`
- `reddit`
- `market_commentary`

Allowed `event_category` values:

- `macro`
- `exchange`
- `regulatory`
- `listing`
- `hack`
- `liquidation`
- `funding`
- `other`

## 4. Reference Surfaces

Allowed source surfaces are context sources only:

| Surface | Allowed use | Forbidden use |
|---|---|---|
| `market.news_signals` | Existing DB-backed context annotations with source URL, severity, category, affected symbols, and raw content lineage. | Primary alpha table, promotion gate input, final verdict override. |
| Future X/Reddit artifacts | External child artifacts or DB-backed context records after a separate source contract exists. | Any direct trading or score path. |
| Market commentary notes | Human/operator or analyst notes, if source and timestamp are preserved. | Replacing math gates or PIT evidence. |

Runtime/control-plane surfaces remain excluded from promotion logic:

- `trading.decision_context_snapshots.news_severity`
- `NewsRouter`
- Guardian halt behavior
- Layer2 escalation news severity

Those are safety and runtime context surfaces, not Alpha-Edge promotion proof.

## 5. Acceptance Gates

| Gate | Requirement |
|---|---|
| Run linkage | `side_evidence.json.run_id` equals `manifest.json.run_id`. |
| Digest linkage | If present, the artifact is listed in `manifest.json.artifacts` and `artifact_index.json` with digest, size, row count, and schema version. |
| Secondary-only policy | `policy.role=secondary_only` and `promotion_use=excluded_from_promotion_gates`. |
| No override | `may_change_final_label=false` and `may_override_math_failure=false`. |
| Source taxonomy | `source_category` is constrained to the approved set. |
| Provenance | DB-backed rows include table/key or payload digest; external rows include stable source URL or artifact digest. |
| Reporting language | Reports describe context consistency, never alpha proof. |

Hard mathematical gates remain decisive:

- coverage gate
- feature lineage gate
- PIT universe / survivorship gate
- net/cost gate
- PSR / DSR / PBO gate
- freshness gate
- non-bull robustness gate
- execution realism gate

If any of these fail, side evidence may only add diagnostic context.

## 6. Future Implementation Scope

This contract does not authorize implementation. A later scoped task may add:

- JSON schema or validator fixtures.
- Runner emission of `side_evidence.json`.
- Artifact-index digest checks.
- Report rendering that uses only approved wording.

That task must remain downstream of the AEG run manifest and cannot create a
new evidence path that bypasses the mathematical verdict matrix.

Still blocked:

- Alpha scoring.
- Promotion verdict changes.
- Trading decision use.
- DB writes or migration apply for side evidence.
- Runtime collector or social/news agent implementation.
