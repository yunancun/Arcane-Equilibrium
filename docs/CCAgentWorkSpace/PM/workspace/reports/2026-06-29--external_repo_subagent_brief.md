# 2026-06-29 External Repo Deep Evaluation Brief

## Scope

Evaluate whether the following external GitHub projects are useful for TradeBot / OpenClaw, and if useful, where they can be fused into the existing framework:

- `xbtlin/ai-berkshire`
- `AgriciDaniel/claude-obsidian`

This is a read-only evaluation. Do not edit project code. Do not propose direct runtime/order-path integration.

## Local Roots

- TradeBot canonical repo: `/Users/ncyu/Projects/TradeBot/srv`
- External repo clone root: `/tmp/tradebot-external-audit.0a2EDp`
- `ai-berkshire`: `/tmp/tradebot-external-audit.0a2EDp/ai-berkshire`
- `claude-obsidian`: `/tmp/tradebot-external-audit.0a2EDp/claude-obsidian`

## External Repo Facts Already Verified

### ai-berkshire

- HEAD: `1f2ef67a8e39598323b5096256c553e524c4937e`
- Latest local commit date: 2026-06-29 17:13:13 +0800
- License: MIT
- Shape: large investment research vault with Codex/Claude skills, reports, tools, prompts, data, assets
- Initial commands:
  - `python3 scripts/sync-codex-skills.py --check` passed: checked 18 Codex skills
  - `python3 tools/financial_rigor.py --help` worked
  - `python3 tools/report_audit.py --help` worked
- Initial concern: useful methodology/templates, but no verified production trading alpha; README/performance claims must be treated as unverified unless independently reproduced.

### claude-obsidian

- HEAD: `cb93ff6d82f9c35a08bf6010e7fac36dfddc827b`
- Latest local commit date: 2026-05-28 03:42:42 +0300
- License: MIT
- Shape: Claude plugin / Obsidian vault workflow with skills, retrieve scripts, lock/address scripts, tests, wiki assets
- Initial commands:
  - `make test-retrieve` passed
  - `make test-bm25` passed
  - `make test`, `make test-lock`, and `bash tests/test_allocate_address.sh` failed on macOS because `flock` is unavailable
- Initial concern: retrieval/wiki patterns useful; shell locking/address allocation cannot be ported unchanged.

## TradeBot Hard Boundaries

- Rust `rust/openclaw_engine` is the only trading/risk/config/execution authority.
- Python/FastAPI is control plane, GUI, bridge, replay, research, local agent host only.
- Bybit is the only execution exchange.
- OpenClaw Gateway is communication/supervisor/proposal relay only, not conductor, not GUI replacement, not hot path.
- AI output can only become a Decision Lease proposal and must pass local GovernanceHub / Guardian / lease checks.
- Live/mainnet authority is not in scope. Current posture is Demo-only; do not infer active lease/order authority from older artifacts.
- Alpha evidence is math-primary. News, narrative, filings, reports, X/Reddit-style context, and LLM analysis are secondary context only.
- Paper promotion lane is frozen. Do not propose reopening it as an integration shortcut.

## Relevant Local Architecture References

- `docs/adr/0001-rust-as-trading-authority.md`
- `docs/adr/0006-bybit-only-exchange.md`
- `docs/adr/0007-mac-dev-linux-runtime-split.md`
- `docs/adr/0008-decision-lease-state-machine.md`
- `docs/adr/0013-openclaw-gateway-not-trading-conductor.md`
- `docs/adr/0021-alpha-source-architecture-upgrade.md`
- `docs/adr/0041-context-distiller-v4-and-ai-cost-cap-amendment.md`
- `docs/adr/0045-m4-hypothesis-discovery-governance.md`
- `docs/adr/0047-alpha-edge-regime-evidence-governance.md`
- `CONTEXT.md`
- `CLAUDE.md`
- `TODO.md`
- `.codex/MEMORY.md`

## Candidate Fusion Areas To Evaluate

1. Research skill/template library for PM/QC/AI-E assisted equity/market research.
2. AEG / M4 hypothesis review templates, evidence matrices, and report audit gates.
3. Offline knowledge base ingestion/retrieval for docs, reports, ADRs, and PM memory.
4. Operator Console / Control Plane read-only assistant surfaces.
5. ContextDistiller v4 or AI invocation ledger improvements.
6. Repo-internal documentation, report QA, and research reproducibility checks.

## Non-Candidate Areas Unless Strongly Justified

- Direct strategy logic import.
- Direct order placement, risk sizing, exchange connector, or live config mutation.
- Obsidian plugin as canonical GUI.
- Multi-exchange abstraction.
- Narrative/news as promotion authority.
- Shell lock logic requiring Linux-only `flock` in Mac development paths.

## Required Output Shape Per Agent

Return concise but concrete findings:

1. Verdict: useful / partial / reject for each repo.
2. Top 3 integration opportunities with exact local Module / Interface / Adapter candidates.
3. Top blockers or failure modes.
4. Minimal safe first step, ideally read-only or report-only.
5. Files inspected and commands run.

