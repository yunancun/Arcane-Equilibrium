# 2026-06-11 AEG-S3 + Claude Tooling Three-Side Sync

## Status

`STATUS: DONE_WITH_CONCERNS`

This sync checkpoint packages two local batches:

1. Claude-side workflow/tooling updates that were already present locally:
   hooks, rtk pin/patch, four-state subagent completion contract, agent-wave
   status parsing, skill trigger rewrites, and mirrored Codex memory pointers.
2. PM-local AEG-S3 artifact-only research infrastructure:
   `aeg_s3_candidate_rows`, `aeg_s3_listing_fade`, and `aeg_s3_oi_delta`.

Concern: this is sync/infrastructure, not promotion proof. It does not create
true candidate rows from production artifacts, does not add PBO candidate grids,
and has not been through E2/MIT/QC promotion review.

## Scope

Included:

- `.claude/settings.json`
- `.claude/hooks/session-start.sh`
- `.claude/hooks/rtk-rewrite.sh`
- `tools/rtk/`
- `.claude/agents/*` and `.claude/skills/*` wording updates already present
  locally
- `.claude/workflows/agent-wave.js`
- `CLAUDE.md`, `.codex/MEMORY.md`,
  `.codex/SUBAGENT_EXECUTION_RULES.md`
- role memory updates under `docs/CCAgentWorkSpace/*/memory.md`
- AEG-S3 PM reports and research modules under `helper_scripts/research/`
- `TODO.md` and `helper_scripts/SCRIPT_INDEX.md`

Excluded:

- runtime restart or rebuild
- DB writes or migrations
- auth renewal or secret mutation
- risk/trading config changes
- Bybit/API calls

## Verification

AEG-S3 focused regression:

```bash
PYTHONPATH=helper_scripts/research:helper_scripts python3 -m pytest \
  helper_scripts/research/tests/test_aeg_s3_oi_delta.py \
  helper_scripts/research/tests/test_aeg_s3_listing_fade.py \
  helper_scripts/research/tests/test_aeg_s3_candidate_rows.py \
  helper_scripts/research/tests/test_aeg_candidate_metrics.py \
  helper_scripts/research/tests/test_aeg_robustness_matrix.py \
  helper_scripts/research/tests/test_gate_b_probe.py -q
```

Result:

```text
70 passed in 1.52s
```

Additional checks:

```bash
python3 -m compileall -q helper_scripts/research/aeg_s3_oi_delta \
  helper_scripts/research/aeg_s3_listing_fade \
  helper_scripts/research/aeg_s3_candidate_rows
bash -n .claude/hooks/session-start.sh .claude/hooks/rtk-rewrite.sh
node --check .claude/workflows/agent-wave.js
python3 -m json.tool .claude/settings.json >/dev/null
```

Static forbidden-route search found no runtime/DB/Bybit route in the new
AEG-S3 modules. Secret-pattern search only hit documented security terms,
skill examples, and existing operational path names, not concrete credentials.

## Runtime Decision

No rebuild/restart is required for this checkpoint:

- AEG-S3 modules are offline helper scripts.
- Claude hooks/tooling affect Claude/Codex workflow only.
- No Rust runtime, Python control API, SQL migration, env file, auth, or
  trading config changed.

P5-SM soak should continue without reset.

## Next

1. Import or wait for an operator-timed Gate-B true transition artifact for
   listing fade.
2. Export V125 accepted-run OI/price/regime panel for `oi_delta`.
3. Add explicit candidate-grid PBO evidence for listing fade and `oi_delta`.
4. Implement `funding_revive` evidence producer.
5. Route true candidate rows through `aeg_candidate_metrics` and
   `aeg_robustness_matrix`, then send E2/MIT/QC review before any promotion
   interpretation.
