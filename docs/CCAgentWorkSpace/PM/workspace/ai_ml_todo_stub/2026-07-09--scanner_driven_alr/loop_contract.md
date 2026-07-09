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
7. Run `git status --short --branch` and preserve unrelated dirty changes.

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
7. Run focused unit/static checks and `git diff --check`.
8. Write:
   - `alr_work_item_v1`
   - `alr_effect_review_v1`
   - `alr_loop_state_packet_v1`
   - PM report
   - Operator summary when useful
9. Stage only owned files.
10. Commit each green checkpoint with subject and body.
11. Re-read state and continue while result is `ADVANCED`,
    `ADVANCED_WITH_CONCERNS`, or a recovered `ROTATED` with a source-only next
    row.

## State Packet Minimum Fields

Every `alr_loop_state_packet_v1` must include:

- `schema`
- `created_at`
- `repo_head_before`
- `repo_head_after`
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
