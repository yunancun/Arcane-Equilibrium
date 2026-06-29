# 2026-06-29 External Repo Read-Only Fusion Implementation

Status: implemented and verified as **read-only advisory tooling**.

Added:
- `helper_scripts/docs_context_retrieval/` for offline repo-local BM25 docs retrieval.
- `helper_scripts/research/aeg_report_audit/` for advisory PM/AEG/M4 report audit and falsification checklist.
- `helper_scripts/research/external_repo_fusion_smoke.py` for end-to-end smoke under `/tmp/openclaw`.
- `helper_scripts/SCRIPT_INDEX.md` registration.

Verification:
- New focused tests: `40 passed`.
- Adjacent AEG tests: `9 passed`.
- M4 leakage regression: `52 passed`.
- Smoke: `EXTERNAL_REPO_FUSION_SMOKE_COMPLETE`, chunks `2544`, retrieval/audit/authority all ready.
- Retrieval CLI and audit CLI passed.
- `git diff --check` passed.

Linux rebuild + restart:
- Source commit `523fcb48` was deployed to `trade-core`.
- First atomic deploy attempt was blocked by an existing `/tmp/openclaw/build_window.lock`; no partial deploy occurred.
- Second `build_then_restart_atomic.sh` completed with engine PID `877736` and `/proc` SHA verified against binary SHA `c867c89cfbbde8f02a5ef6cf985a629aa8eeb544784dab6d7b883f4435854be0`.
- API-only reload completed with API PID `878457`.
- Post-restart focused tests passed (`40 passed`), smoke completed (`2545` chunks), retrieval CLI passed, and audit CLI preserved no-authority flags.
- Warning: signed live authorization was absent and preserved absent; no authority was created.

Boundary:
- Advisory-only, no authority.
- No Bybit, PG/DB, network/API/LLM, runtime IPC, order/cancel/modify, risk/config/env/crontab mutation, Decision Lease acquire/release, writer/adapter enablement, Cost Gate lowering, promotion proof, Stage0/trading approval, or sizing recommendation.

Operator note:
Retrieval score means relevance only. Audit findings are gaps/redlines only. Do not use these artifacts as trading, promotion, risk, or runtime authority.
