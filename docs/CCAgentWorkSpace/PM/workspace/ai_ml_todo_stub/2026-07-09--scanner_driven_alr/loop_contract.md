# ALR Foreground Codex Loop Contract

This loop is for Codex source development. It is not an application runtime loop.
Boundary label: `SOURCE_ONLY_OFFLINE_P0_P1`.

## Boot

1. Start from `/Users/ncyu/Projects/TradeBot`.
2. Read `srv/AGENTS.md` and treat `srv/` as the authoritative repo root.
3. Follow the mandatory boot sequence in `srv/AGENTS.md`.
4. Read this stub directory:
   `docs/CCAgentWorkSpace/PM/workspace/ai_ml_todo_stub/2026-07-09--scanner_driven_alr/`.
5. Read the current root `TODO.md` only for active blocker truth. Do not import
   this stub into root `TODO.md` unless PM explicitly chooses to do so.
6. Do not inherit current trading P0 candidate context, standing Demo
   authorization, prior no-order approval, prior Bybit public GET approval,
   operator-review-ready artifacts, or cached exchange credentials.
7. Bind `LOOP_BRANCH` and full `CHECKPOINT_HEAD`, then run
   `helper_scripts/maintenance_scripts/git_loop_guard.py --phase start` with
   both expected values. The loop must use an attached non-`main` feature branch
   and a clean worktree. Any pre-existing dirty path stops as
   `STOP_GIT_START_STATE`; preserve it exactly and do not stash/reset/clean it.

## Iteration

Each iteration:

1. Recover the latest ALR state packet if present.
2. Re-read `queue.md`, `boundaries.md`, and `retention_guardian_contract.md`.
3. Select exactly one row:
   - first `ACTIVE` row;
   - otherwise first row whose waiting condition is satisfied;
   - otherwise stop with the blocking state.
4. Dispatch the required chain for the selected row.
5. If required dispatch tooling or role-chain execution is unavailable, stop as
   `STOP_DISPATCH_BLOCKED`; do not silently substitute single-agent PM/PA work.
6. Implement only the selected row's allowlisted source/doc/test scope.
7. Before staging, run `git_loop_guard.py --phase checkpoint` with the exact
   branch, checkpoint head, and this row's file/prefix allowlist. Defaults are a
   hard checkpoint trigger: at most 12 dirty files, 1500 tracked diff lines,
   and 2 MB untracked. A binary diff, pre-staged path, unowned path, or exceeded
   limit stops as `STOP_CHECKPOINT_SCOPE`.
8. Run focused unit/static checks, required adjacent/wider regression, and
   `git diff --check`.
9. Write:
   - `alr_work_item_v1`
   - `alr_effect_review_v1`
   - `alr_loop_state_packet_v1`
   - PM report
   - Operator summary when useful
10. The PM-owned checkpoint lane stages only exact owned files and verifies
    `git diff --cached --name-only` before commit. No sub-agent stages, commits,
    pushes, merges, or cleans up a branch/worktree.
11. Commit each green checkpoint with subject and body, update the full
    `CHECKPOINT_HEAD`, then rerun `git_loop_guard.py --phase start`; the next row
    cannot begin until the worktree is clean at that exact commit.
12. Re-read state and continue while result is `ADVANCED`,
    `ADVANCED_WITH_CONCERNS`, or a recovered `ROTATED` with a source-only next
    row.

Local checkpoint commits are intentionally not pushed per iteration. This keeps
hosted CI off the edit loop while bounding crash recovery to at most the current
iteration instead of a multi-hour dirty tree.

## Publication, merge, and three-side sync

When the selected queue segment is locally complete:

1. Require explicit publication authority and follow `.codex/SYNC.md`.
2. Fetch/integrate current `origin/main` once without rewriting published
   history; rerun affected local regression.
3. Require `git_loop_guard.py --phase publish` PASS.
4. Push one stable feature-branch head without force and require
   `--phase post-push` to prove the true remote branch SHA equals
   `CHECKPOINT_HEAD`.
5. Request one exact-head review and one path-classified CI run. Never rerun an
   unchanged head.
6. Merge only with
   `gh pr merge <PR> --merge --match-head-commit "$CHECKPOINT_HEAD"`; never use
   `--admin` or automatic branch deletion.
7. Capture the resulting true `origin/main` SHA. With separately authorized
   source-sync effects, fast-forward clean Mac main and clean Linux main to that
   exact SHA; no reset/clean/generic pull fallback is allowed.
8. Run `four_head_reconcile_probe.py`. `ALL_FOUR_SYNC` completes source/runtime
   alignment. `SOURCE_ONLY_DRIFT` completes three-side source sync.
   `HALF_DEPLOY_REBUILD_REQUIRED` completes three-side source sync but returns
   `SOURCE_SYNCED_RUNTIME_PENDING`; deploy remains separately governed.

Without publication/merge/sync authority the loop returns
`STOP_SYNC_AUTH_REQUIRED`, not `DONE`. It must never claim completion while
commits are only local, the PR is unmerged, or Mac/origin/Linux differ.

## State Packet Minimum Fields

Every `alr_loop_state_packet_v1` must include:

- `schema`
- `created_at`
- `repo_head_before`
- `repo_head_after`
- `loop_branch`
- `checkpoint_head`
- `checkpoint_guard_status`
- `checkpoint_dirty_file_count`
- `checkpoint_tracked_diff_lines`
- `checkpoint_untracked_bytes`
- `selected_work_item`
- `selection_reason`
- `state`
- `next_state`
- `next_action`
- `stop_reason`
- `owned_files`
- `verification_commands`
- `candidate_matched_fills_count`
- `proof_packet_ready_count`
- `reward_ledger_ready_count`
- `effect_review_ready`
- `model_training_performed=false`
- `serving_authority_granted=false`
- `llm_authority=false`
- `runtime_authority=false`
- `exchange_authority=false`
- `trading_authority=false`
- `boundary_escalation_required`
- `dispatch_tooling_available`
- `dispatch_blocker`
- `published_head`
- `remote_branch_head_verified`
- `merged_origin_head`
- `mac_main_head`
- `linux_main_head`
- `three_side_source_sync_status`
- `four_head_reconcile_status`

## Stop States

| State | Meaning |
|---|---|
| `DONE` | Selected queue segment is complete and no required P0 work remains. |
| `ADVANCED` | One row advanced cleanly; continue to next row. |
| `ADVANCED_WITH_CONCERNS` | One row advanced with explicit non-blocking concerns; continue only if the next row does not depend on the concern. |
| `DEFER_EVIDENCE` | Missing candidate-matched proof/reward/control/repeat/OOS evidence. |
| `HYPOTHESIS_ONLY` | Target can be ranked for investigation but no edge claim is allowed. |
| `ROTATED` | Source head, candidate id, input hash, auth/envelope, or referenced artifact drifted. Re-intake source-only state before continuing. |
| `STOP_NO_EDGE` | Proof-ready evidence shows non-positive conservative after-cost lower confidence bound. Not used for missing proof. |
| `STOP_RETENTION_RISK` | Cleanup candidate touches proof, dispute, audit, lineage, unknown reference, or negative-example risk. |
| `STOP_DISPATCH_BLOCKED` | Required role-chain dispatch tooling is unavailable. Stop and request operator direction instead of silently substituting single-agent implementation. |
| `STOP_GIT_START_STATE` | Loop did not start from the exact clean feature-branch checkpoint. |
| `STOP_CHECKPOINT_SCOPE` | Dirty scope escaped the row allowlist or exceeded the bounded checkpoint budget. |
| `STOP_PUBLISH_PREFLIGHT` | Feature branch, upstream, origin tracking, or topology is unsafe/stale. |
| `STOP_PUSH_VERIFY` | True remote branch SHA does not equal the stable checkpoint. |
| `STOP_MERGE_HEAD_DRIFT` | Merge did not bind the exact reviewed head. |
| `STOP_SYNC_AUTH_REQUIRED` | Publication/merge/Mac-Linux source-sync effect lacks exact authority. |
| `STOP_MAC_MAIN_SYNC` | Mac main cannot cleanly fast-forward to the captured origin SHA. |
| `STOP_LINUX_SYNC` | Linux checkout is dirty, non-main, stale, or diverged. |
| `SOURCE_SYNCED_RUNTIME_PENDING` | Mac/origin/Linux match; runtime build/deploy remains separately pending. |
| `BLOCKED_BOUNDARY` | Work would require runtime, PG, IPC, exchange, official MCP, order, scheduler, serving, promotion, or delete authority. Stop before the tool call and hand off. |

## Dispatch Chains

- Boundary packet: `PM -> CC -> FA -> PA -> PM`
- Quant/ML/data audit: `PM -> QC -> MIT -> AI-E -> PM`
- Implementation: `PM -> PA -> E1/E1a -> E2 -> E4 -> QA -> PM`
- Runtime/exchange escalation only: `PM -> E3 -> BB -> PM`

## Static Boundary Checks

Run checks against changed files only. Legacy files may contain forbidden
surfaces for unrelated reasons.

```bash
FILES=$(git diff --name-only --diff-filter=ACMR HEAD -- \
  program_code/ml_training docs/CCAgentWorkSpace/PM docs/CCAgentWorkSpace/Operator | tr '\n' ' ')

if [ -n "$FILES" ]; then
  ! rg -n "(cron|crontab|launchd|systemd|daemon|sidecar|watchdog|scheduler|while True|asyncio\\.create_task|BackgroundTasks|tokio::spawn|sleep\\()" $FILES
  ! rg -n "(psycopg|asyncpg|sqlalchemy|DATABASE_URL|PGHOST|psql|INSERT|UPDATE|DELETE|CREATE TABLE|DROP TABLE|ALTER TABLE|migration|Timescale)" $FILES
  ! rg -n "(Bybit|bybit|official MCP|requests\\.|httpx|urllib|aiohttp|websocket|/v5/|place_order|cancel_order|modify_order|OrderDispatchRequest|TradingMsg)" $FILES
  ! rg -n "(BybitRestClient|OrderManager|api\\.bybit|stream\\.bybit|/v5/order|MCP|official MCP|fee-rate|cancel-all|amend)" $FILES
  ! rg -n "(Decision Lease|acquire.*lease|IPC|engine\\.sock|OPENCLAW_IPC|adapter_enabled|writer_enabled)" $FILES
  ! rg -n "(OPENCLAW_|os\\.environ|getenv|secret|authorization\\.json|api_key|api_secret|token|password|HMAC|X-BAPI|load_dotenv)" $FILES
  ! rg -n "(_latest|symlink|promot|serving|reload_model|unlink|rmtree|os\\.remove|Path\\.unlink|shutil\\.rmtree|--apply)" $FILES
fi

git diff --check
```

If a boundary check fails because a doc quotes the forbidden term in a boundary
section, record that explicitly in the effect review and verify no executable
source path uses it.
