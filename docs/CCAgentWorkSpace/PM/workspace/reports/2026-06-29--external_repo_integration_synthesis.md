# 2026-06-29 External Repo Integration Synthesis

Scope: subagent deep evaluation of `xbtlin/ai-berkshire` and `AgriciDaniel/claude-obsidian`, then TradeBot/OpenClaw fusion decision.

External baselines:
- `xbtlin/ai-berkshire` HEAD `1f2ef67a8e39598323b5096256c553e524c4937e`, MIT.
- `AgriciDaniel/claude-obsidian` HEAD `cb93ff6d82f9c35a08bf6010e7fac36dfddc827b`, MIT.

PM SIGN-OFF: **CONDITIONAL APPROVED FOR READ-ONLY SMOKE ONLY**.

Runtime/trading integration is **BLOCKED**. Neither repo may enter Rust `openclaw_engine`, order admission, risk/config mutation, Guardian, Decision Lease activation, Bybit connector, live/demo authority, or promotion evidence paths.

## Subagent Consensus

| Role | Verdict |
|---|---|
| CC | Research-only / isolated read-only sidecar only; reject runtime integration and Obsidian hooks/MCP as TradeBot authority. |
| PA | `claude-obsidian` has better architectural leverage as a Knowledge Vault Adapter; `ai-berkshire` is only a Research Discipline Adapter. |
| QC | ADR-0047 math-primary remains unchanged; both repos are rejected as alpha proof or promotion proof. |
| MIT | First integration must be scratch read-only JSON; no DB, no runtime prompt, no shell `flock`, no durable absolute paths. |
| AI-E | Retrieval is useful only with no-egress, bounded snippets, ledger metadata, and ADR-0041 token discipline; current `ContextDistiller` char cap blocks direct prompt injection. |
| FA | Best functional fit is PM/AEG report audit, offline docs retrieval, and M4/AEG falsification checklist. |

## Repo Verdicts

### `ai-berkshire`: Partial Useful, Alpha-Proof Reject

Useful ideas:
- Exact arithmetic and cross-source verification pattern from `tools/financial_rigor.py`.
- Report sampling /准出-打回 pattern from `tools/report_audit.py`.
- Thesis / checklist / adversarial research templates for operator-readable review.

Rejected uses:
- Any performance claim, portfolio review, BUY/SELL/sizing language, DCF/price-band, moat narrative, or company report as TradeBot alpha evidence.
- Any scraper or data source path (`Yahoo`, `Tencent`, `Eastmoney`, `Xueqiu`, login-state tooling) in runtime or cron.
- Direct skill install/symlink into TradeBot agent triggers.

### `claude-obsidian`: Partial Useful, Proof-Layer Reject

Useful ideas:
- BM25/retrieve/citation workflow for offline docs/reports lookup.
- Hot/index/cache discipline as a design reference for reducing repeated context load.
- Wiki-lint style health checks for stale links, orphan docs, or missing citations.

Rejected uses:
- Obsidian as canonical GUI, source of truth, or TradeBot memory authority.
- `wiki-ingest`, auto hooks, auto commits, MCP/local REST write paths, or vault writes into `srv/`.
- Shell `wiki-lock.sh` / `allocate-address.sh` unchanged: macOS tests already fail because `flock` is unavailable.
- Contextual prefix egress paths unless a future Y2 opt-in and ledgered cost gate explicitly allow it.

## Fusion Plan

### A. `aeg_report_audit` Adapter

Candidate path: `helper_scripts/research/aeg_report_audit/` after smoke passes.

Purpose: TradeBot-native report QA gate inspired by `ai-berkshire`, not copied from it.

Inputs:
- PM reports under `docs/CCAgentWorkSpace/PM/workspace/reports/`.
- AEG artifacts from `helper_scripts/research/aeg_candidate_metrics/`, `aeg_robustness_matrix/`, `aeg_execution_realism/`, and `alpha_discovery_throughput/artifact_spine.py`.

Outputs:
- Advisory-only JSON/Markdown findings.
- Required fields: `source_path`, `line_span`, `claim_type`, `artifact_sha`, `source_sha`, `candidate_identity`, `missing_evidence`, `authority_flags`.

Hard gates:
- No DB writes, no config writes, no runtime reads, no order/risk/lease mutation.
- Findings can only say `audit_gap`, `insufficient evidence`, `citation_missing`, or `advisory_pass`; no promotion verdict.

### B. `docs_context_retrieval` Adapter

Candidate path: `helper_scripts/docs_context_retrieval/` after scratch smoke passes.

Purpose: offline retrieval sidecar for PM/FA/QC/Operator review.

Sources:
- `docs/adr/`
- `docs/execution_plan/`
- `.codex/MEMORY.md`
- `docs/CCAgentWorkSpace/PM/memory.md`
- `docs/CCAgentWorkSpace/PM/workspace/reports/`

Interface:
- Query in, citation candidates out.
- Output shape: `source_path`, `line_span`, `snippet`, `score`, `index_sha`, `degraded_level`.

Hard gates:
- BM25-only first; no API, no remote Ollama, no contextual-prefix egress.
- Snippet budget <= 200 tokens per result.
- Retrieval score means relevance only, never truth/proof.
- Stay out of `ContextDistiller` prompt injection until ADR-0041 token hard cap and ledger fields are actually enforced.

### C. M4 / AEG Falsification Checklist

Candidate surface:
- `helper_scripts/m4/attribute_enforcer.py`
- `helper_scripts/m4/draft_writer.py`
- `helper_scripts/m4/stage1_production_runner.py`
- `helper_scripts/research/aeg_execution_realism/builder.py`
- `docs/adr/0047-alpha-edge-regime-evidence-governance.md`

Purpose: make existing math-primary evidence easier to reject correctly.

Allowed output:
- Operator-readable redlines: missing OOS, PSR/DSR/PBO, n_independent, multiple-testing correction, regime/breadth/survivorship/freshness, execution realism, fee/slippage/capacity, or Decision Lease DRAFT lineage.

Rejected output:
- No strategy logic.
- No promotion.
- No Decision Lease activation.
- No paper-lane shortcut.

## First Executable Step

Run a read-only smoke outside repo/runtime:

1. Build a BM25-only index over 30-50 local docs into `/tmp/openclaw/docs_retrieval_smoke/`.
2. Produce retrieval JSON for representative PM/QC questions.
3. Manually run report-audit style checks against 3 PM reports and 2 AEG artifacts into `/tmp/openclaw/external_repo_eval/report_audit_smoke.json`.
4. Verify:
   - zero repo mutation,
   - zero network / API / LLM,
   - zero DB / runtime / Bybit,
   - zero trading/risk/order/config touch,
   - no shell `flock`,
   - every finding has local citation and `advisory_only=true`.

Only after this passes should PA/MIT/AI-E write a local design spec for a TradeBot-native adapter.

## Open Blockers

1. Direct runtime/order integration: **blocked permanently under current architecture**.
2. Direct ContextDistiller injection: **blocked** until token counting replaces char truncation and ADR-0041 ledger fields exist.
3. Obsidian write workflow: **blocked** because it conflicts with repo SoT and Mac portability.
4. External research as alpha proof: **blocked** by ADR-0047.

