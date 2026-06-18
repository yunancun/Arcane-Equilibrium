# TODO SignalSpec Conformance Stale-Defer Relocation

Date: 2026-06-18
Owner: PM
Scope: TODO/changelog/memory/report hygiene plus source/read-only status correction

## Decision

Move `P2-AST-SIGNALSPEC-CONFORMANCE` from `TODO.md` §5 active engineering queue to §7 conditional wait.

This is not a completed-row archive and not an implementation approval. The row remains deferred until formal SignalSpec schema freeze plus PA/PM GO.

## Evidence Rechecked

- Source now contains `program_code/ml_training/candidate_signal_spec_producer.py` with `build_signal_spec`.
- Source now contains `candidate_signal_spec.py`, `candidate_evidence_manifest.py`, `candidate_evidence_manifest_builder.py`, hidden-OOS bridge/sealer files, and residual Stage0R preflight source.
- `memory/project_2026_06_06_p2_orderlinkid_postmortem_ast.md` records that the original #8 NO-GO reason included producer being branch-only, then later notes this premise became stale after residual-producer source landed on main.
- `memory/project_2026_06_05_residual_producer_build.md` states the later correction: SignalSpec producer / hidden-OOS sealer / mlde hook / replay bridge were completed and deployed by the 2026-06-07 rebuild path, while #8 AST unfreeze gate remains schema freeze.
- `docs/CLAUDE_CHANGELOG.md` v170 already archived the operator-history row for `P2 #8 AST 解凍決策` and residual-producer baseline completion.

## Preserved Boundary

Future work must not revive the old "AST expression tree" wording. The real schema is a flat metadata manifest. If thawed, implement a `SignalSpec schema/lineage conformance checker` covering:

1. required fields,
2. duplicate fingerprint,
3. feature-count budget,
4. deterministic hypothesis alignment.

No CI, source code change, deploy, rebuild, restart, runtime mutation, DB mutation, auth change, risk change, order change, or trading change in this pass.
