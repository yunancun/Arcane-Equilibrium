# 2026-05-15 — TODO v22 Cleanup

## Scope

PM documentation cleanup only:

- Read and reconciled `TODO.md` v21 (754 lines).
- Cross-checked completed/superseded items with PA(default), FA(default),
  `git log`, reports, governance sign-offs, and `active-plan.md`.
- Archived completed sprint ledgers and DONE-row evidence to
  `docs/archive/2026-05-15--todo_v21_completion_cleanup_archive.md`.
- Updated `docs/README.md` archive index.

Boundary: no `active-plan.md`, runtime code, live auth, rebuild, restart, or
deploy was changed.

## Result

- `TODO.md` is now v22 and reduced to 453 lines.
- Stage 0R GATE-RED and `[55]` WARN remain visible as active blockers.
- `W6-5 sample_weight ratio sensitivity + 5 ML pipeline metrics` was preserved
  in §11.3 before archiving the old §6.6 history.
- `P1-STABLE-ID-1`, `P1-RCA-1`, `P1-FILL-LINEAGE-DROP`,
  `P2-DUAL-RAIL-ORDER-ID`, `P2-RUNTIME-SHADOW-SPLIT`, and
  `P0-MIT-LABEL-CLOSE-TAG-1` were marked complete or moved out of the active
  flow with follow-up rows retained where needed.

## Priority Verdict

No full W-AUDIT roadmap rewrite is needed. The required priority delta is:

1. Stage 1 demo micro-canary is blocked, not active execution.
2. `[55]` cleanup remains P1 as the shared infrastructure gate for future demo
   canaries.
3. A4-C is implementation-complete but promotion-blocked; next work is
   diagnostic maturity / revise-or-archive, not launch SOP.
4. Continue Alpha Surface Phase C/D and alternative alpha candidates.
5. P0-LG-1/2/3, P0-OPS, and P0-EDGE-1 remain true-live prerequisites.

## Verification

- `wc -l TODO.md` -> 453
- `git diff --check` -> PASS
- `python3 -m pytest tests/structure/test_docs_readme_index_static.py -q` ->
  5 passed
