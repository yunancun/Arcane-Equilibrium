# Batch A-F Release Gate Reverification

Date: 2026-04-29
Status: local code gates green; deployment gate still not executed

## Verdict

A-F remediation is locally verified against broad code/test gates. I found and fixed release-gate drift during this pass:

- Control API full-suite drift: Phase2 auth header was static and failed after broad-suite auth setting mutations; roster fallback test had an incomplete hard-coded state set.
- Rust full-package doctest drift: prose blocks in module docs were parsed as Rust doctests.
- ML full-suite drift: pooled training tests monkeypatched the wrong module path; `requirements-ml.txt` did not install `psycopg2-binary` even though legacy training readers still import `psycopg2`.

These were verification-chain issues, not evidence that the A-F production fixes were invalid. After fixes, the local broad gates are green.

## Green Gates

- `cargo test -p openclaw_engine --manifest-path rust/Cargo.toml` -> passed, including lib/bin/integration/doc tests.
- `cargo build --release -p openclaw_engine --manifest-path rust/Cargo.toml` -> passed with existing unused/dead-code warnings.
- `/tmp/openclaw-batch-a-venv/bin/python -m pytest -q program_code/exchange_connectors/bybit_connector/control_api_v1/tests --tb=short` -> 3182 passed, 5 skipped.
- `/tmp/openclaw-ml-verify-venv/bin/python -m pytest -q program_code/ml_training/tests --tb=short` -> 317 passed, 17 skipped.
- `git diff --check` -> passed.
- `bash -n` over shell scripts under `helper_scripts` and `control_api_v1` -> passed.
- `py_compile` over changed/untracked Python files -> 55 files passed.
- `docs/audit/remediation_tracking.md` finding ledger -> 62 findings, 62 unique IDs, all status `fixed`.

## Remaining Release Boundaries

This pass did not deploy. The Mac worktree is still uncommitted/unpushed, and `trade-core` is still on `890e578` with a clean remote worktree. Therefore the system is not already production-updated.

Before claiming production release complete, perform:

1. Commit and push the full A-F worktree as an intentional release unit.
2. Pull on `trade-core` and rebuild/restart there.
3. Run target-runtime smoke: engine health, API health, watchdog, DB migrations, live/demo/paper mode checks, and fail-closed auth/secret checks.
4. Run the remaining Batch F runtime smokes if release scope includes live ML autonomy: live Postgres model-registry integration with `OPENCLAW_DATABASE_URL`, real ONNX artifact end-to-end load, and LinUCB live boot/state-load smoke.
5. Decide whether `cargo fmt --all --check` is a release gate. It still fails on broad repo-wide formatting drift and was not auto-applied because the worktree contains many dirty changes from parallel sessions.

## PM Conclusion

Code-level A-F remediation is locally acceptable after this pass. Production release is still a No-Go until commit/push/deploy and target-runtime smoke complete.
