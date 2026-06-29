# 2026-06-29 External Repo Read-Only Fusion Implementation

Scope: implement the six-agent fusion conclusion for `xbtlin/ai-berkshire` and `AgriciDaniel/claude-obsidian` as TradeBot-native read-only helpers.

PM SIGN-OFF: **IMPLEMENTED / READ-ONLY ADVISORY ONLY**.

Runtime, trading, risk, Bybit, DB, Decision Lease authority, writer/adapter enablement, Cost Gate mutation, and promotion proof remain **BLOCKED**.

## Implemented

1. `helper_scripts/docs_context_retrieval/`
   - Offline BM25-style local docs retrieval.
   - Repo-contained source allowlist; absolute or `..` source escape fails closed.
   - Deterministic `index_sha256` excludes volatile timestamps.
   - Query results include `source_path`, `line_span`, snippet, score, `score_semantics=relevance_only`, index sha, and `degraded_level=offline_bm25_local`.
   - Snippets are hard-capped by local tokenizer budget.

2. `helper_scripts/research/aeg_report_audit/`
   - Advisory PM/AEG/M4 report audit.
   - Status enum is limited to `advisory_pass`, `audit_gap`, `insufficient_evidence`, and `citation_missing`.
   - Checks source lineage, OOS, PSR/DSR/PBO, independent sample, regime/freshness/breadth/costs, Bonferroni, shift(1)/leak-free, malformed JSON, NaN/Inf, unit confusion, missing/mismatched artifact hashes, unsafe authority flags, and forbidden promotion/order/sizing vocabulary.

3. `helper_scripts/research/external_repo_fusion_smoke.py`
   - End-to-end smoke wiring retrieval + PM/AEG/M4 audit.
   - Output is forced under `Path('/tmp/openclaw').resolve()`.
   - Smoke writes scratch artifacts only and preserves `advisory_only=true`, `order_authority_granted=false`, `promotion_authority=false`, and `runtime_mutation_authority=false`.

4. `helper_scripts/SCRIPT_INDEX.md`
   - Registered all new helpers, smoke command, verification results, and no-authority boundary statement.

## Verification

Commands run on Mac source checkout:

- `python3 -m py_compile helper_scripts/docs_context_retrieval/retriever.py helper_scripts/docs_context_retrieval/docs_context_retrieval.py helper_scripts/research/aeg_report_audit/audit.py helper_scripts/research/aeg_report_audit/aeg_report_audit.py helper_scripts/research/external_repo_fusion_smoke.py` -> PASS.
- `python3 -m pytest -q helper_scripts/docs_context_retrieval/test_retriever.py helper_scripts/research/aeg_report_audit/test_audit.py helper_scripts/research/tests/test_external_repo_fusion_smoke.py` -> `40 passed`.
- `PYTHONPATH=helper_scripts/research python3 -m pytest -q helper_scripts/research/tests/test_aeg_candidate_metrics.py` -> `9 passed`.
- `python3 -m pytest -q helper_scripts/m4/tests/test_m4_leakage_regression.py` -> `52 passed`.
- `python3 helper_scripts/research/external_repo_fusion_smoke.py --output-dir /tmp/openclaw/external_repo_fusion_smoke_codex` -> `EXTERNAL_REPO_FUSION_SMOKE_COMPLETE`, `docs_index_chunk_count=2544`, `retrieval_ready=true`, `audit_emitted=true`, `authority_preserved=true`.
- Retrieval CLI build/query -> index schema `tradebot.docs_context_retrieval.index.v1`, chunks `2544`, query results `3`, `order_authority_granted=false`.
- Audit CLI -> schema `tradebot.aeg_report_audit.batch.v1`, status `audit_gap`, input count `1`, `order_authority_granted=false`, `promotion_evidence=false`.
- `git diff --check` -> PASS.

## Role Review

- PA: conditional approval for the two helper locations plus smoke/tests/index/report requirements; direct runtime/DB/ContextDistiller integration remains blocked.
- E2: PASS after hardening; no blocking findings. Confirmed malformed JSON, unsafe authority flags, missing source refs, out-of-repo source paths, and invalid numeric args fail closed.
- E4: PASS after hardening; confirmed deterministic index sha, source containment, snippet hard cap, `/tmp/openclaw` smoke containment, focused tests, CLI checks, and actual smoke.
- QA: PASS; declared usable, effective, complete, and not orphaned.
- E3: PASS for deploy/restart; no BB required because this is not exchange-facing and does not change Bybit/order/runtime/risk/config/Decision Lease paths.

## Linux Rebuild + Restart

After commit `523fcb48` was pushed, `trade-core` was fast-forwarded to that SHA and deployed through the repo atomic path:

- Initial `build_then_restart_atomic.sh` attempt failed closed because another atomic build held `/tmp/openclaw/build_window.lock`; no partial deploy occurred.
- After the lock released, `bash helper_scripts/build_then_restart_atomic.sh` completed:
  - pre/post build SHA `c867c89cfbbde8f02a5ef6cf985a629aa8eeb544784dab6d7b883f4435854be0`
  - new engine PID `877736`
  - `/proc/877736/exe` SHA matched the post-build binary SHA
  - engine maintenance flag was cleared
- `bash helper_scripts/restart_all.sh --api-only --keep-auth` completed after the atomic engine restart:
  - API PID `878457`
  - API bind `100.91.109.86:8000`
- Restart warning observed: signed live authorization was missing at `secrets/secret_files/bybit/live/authorization.json`; `--keep-auth` preserved that absence and did not create authority.

Post-restart verification on `trade-core`:

- Source: `523fcb489823fb537c0736a61948df0d8f6a29cc`, clean against `origin/main`.
- Focused tests: `40 passed`.
- Smoke: `EXTERNAL_REPO_FUSION_SMOKE_COMPLETE`, `docs_index_chunk_count=2545`, retrieval/audit/authority all true.
- Retrieval CLI: schema `tradebot.docs_context_retrieval.query.v1`, result count `3`, `order_authority_granted=false`.
- Audit CLI: schema `tradebot.aeg_report_audit.batch.v1`, status `audit_gap`, input count `1`, `order_authority_granted=false`, `promotion_evidence=false`.

## Boundary

No Bybit call, no PG/DB read or write, no network/API/LLM call, no runtime IPC, no order/cancel/modify, no risk/config/env/crontab mutation, no Decision Lease acquire/release, no writer/adapter enablement, no Cost Gate lowering, no promotion proof, no Stage0/trading approval, and no sizing recommendation occurred.

## Next Use

Use these helpers only as PM/FA/QC/Operator advisory tooling. Retrieval relevance is not truth or evidence. Audit gaps are review blockers or redlines, not promotion or trading decisions.
