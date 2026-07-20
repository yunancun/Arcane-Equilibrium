# Git Publication and Three-Side Sync Contract

Last updated: 2026-07-20

This is the canonical Git state machine for finite Codex feature tasks and
explicitly requested long-running loops. The three
source sides are Mac, the true GitHub `origin/main`, and the Linux `trade-core`
checkout. The running engine build is a separate fourth head and must never be
silently conflated with source sync.

This live repo contract supersedes cached prompts, reports, and personal skills
that prescribe a direct push to `main` or a generic Linux pull. Cached material
may explain history but cannot authorize a Git effect.

## Invariants

- One writable task owns one attached feature branch, one linked worktree, and
  one exclusive writer lease. Business/source work never runs directly on
  `main`; concurrent writers never share a checkout.
- Every iteration begins from an exact clean checkpoint HEAD and ends either at
  another clean commit or at a bounded dirty recovery stop.
- Only the PM-owned publication lane stages, commits, pushes, requests review,
  merges, synchronizes main, or retires a branch/worktree.
- Builders/reviewers return patches/fragments. They never race Git effects.
- No force push, history rewrite of an already published branch, destructive
  reset/clean, generic pull/implicit merge, automatic stash, or branch/worktree
  deletion is part of this workflow.
- GitHub CI/review binds the exact PR head. Merge binds that same head with
  `--match-head-commit`; `--admin` bypass is forbidden.
- Mac and Linux main move only by `--ff-only` to a previously captured true
  `origin/main` SHA. A dirty, detached, non-main, stale, or diverged checkout
  stops before mutation.
- Runtime rebuild/restart is not source sync. `HALF_DEPLOY_REBUILD_REQUIRED`
  means three-side source sync succeeded but deploy remains a separate governed
  effect.
- Ordinary task continuation is `finite`. This Git contract controls authorized
  checkpoints/publication/sync; it does not authorize a new agent turn. Only an
  exact prompt-bound `/loop` task may schedule another turn only when its persisted
  admission and preceding-snapshot no-delta gate passes.

## Read-only guard

`helper_scripts/maintenance_scripts/git_loop_guard.py` is the admission gate.
It emits `git_loop_guard_v1`, exits `3` on failure, and never mutates Git.

Phases:

- `start`: exact branch + exact HEAD + clean feature worktree.
- `checkpoint`: dirty paths are inside the selected work item's allowlist;
  default ceiling is 12 files, 1500 tracked diff lines, and 2 MB untracked.
- `publish`: clean feature branch, fresh local `origin/main`, upstream absent or
  correct for the not-yet-pushed branch, and true origin main is an ancestor of
  the exact head.
- `post-push`: upstream is exactly `origin/<branch>` and the true remote
  feature-branch SHA equals the exact local head.
- `main-sync`: after an explicit fetch, clean local main is fast-forwardable to
  the expected true origin SHA.
- `main-post-sync`: clean local main equals that exact SHA.

The ceiling is a checkpoint trigger, not permission to widen scope. Raising it
requires an explicit task/scope decision; a loop cannot self-raise it.

All feature phases also require a previously acquired writer lease. From a
clean attached non-main linked worktree, PM runs:

```bash
python3 helper_scripts/maintenance_scripts/agent_governance.py writer-lease \
  --lease-action acquire --repo . \
  --task-id "$WRITER_TASK_ID" --owner "$WRITER_OWNER"
```

Keep the returned `lease_id` as local, untracked execution state in
`WRITER_LEASE_ID`; never commit it to a task packet/report. Never infer it from
a different task, copy it to another worktree, or ask the read-only guard to
acquire/steal it. Renew/release requires the same task, owner, and fencing token.

## 1. Loop bootstrap and resume

Expected identity comes from durable loop state, not from whatever checkout is
currently open:

- On resume, load the persisted `loop_branch` and `checkpoint_head` from the
  latest validated loop state packet before inspecting the checkout. A resumed
  loop must not recapture either value from `git branch` or `git rev-parse`.
- On first boot only, PM admits one attached non-`main` feature branch and its
  full current HEAD, then writes those exact values as `loop_branch` and
  `checkpoint_head` to the bootstrap packet before dispatching any work.

After those expected values are loaded or first admitted, run:

```bash
python3 helper_scripts/maintenance_scripts/git_loop_guard.py \
  --phase start \
  --expected-branch "$LOOP_BRANCH" \
  --expected-head "$CHECKPOINT_HEAD" \
  --writer-task-id "$WRITER_TASK_ID" \
  --writer-owner "$WRITER_OWNER" \
  --writer-lease-id "$WRITER_LEASE_ID" \
  --human
```

`main`, detached HEAD, wrong branch, wrong head, or any dirty path stops as
`STOP_GIT_START_STATE`. Do not stash, reset, clean, switch, or absorb unknown
files. Record the path inventory and return it to the owner.

## 2. Per-iteration checkpoint

One selected work item owns one explicit file/prefix allowlist. Before staging:

```bash
python3 helper_scripts/maintenance_scripts/git_loop_guard.py \
  --phase checkpoint \
  --expected-branch "$LOOP_BRANCH" \
  --expected-head "$CHECKPOINT_HEAD" \
  --writer-task-id "$WRITER_TASK_ID" \
  --writer-owner "$WRITER_OWNER" \
  --writer-lease-id "$WRITER_LEASE_ID" \
  --allow-path path/to/owned-file \
  --allow-path path/to/owned-prefix/ \
  --human
```

Then run focused and required wider tests. The PM publication owner alone:

1. stages exact paths with `git add -- <exact paths>`;
2. verifies `git diff --cached --name-only` equals the allowlist delta;
3. commits with subject + body;
4. sets `CHECKPOINT_HEAD` to the new full SHA;
5. reruns `--phase start` and requires a clean PASS before selecting another
   row.

Local green commits do not trigger hosted CI. They prevent a long loop from
accumulating an unbounded dirty tree. A killed loop resumes from the last clean
checkpoint; at most the current bounded iteration needs recovery.

## 3. Stable-head publication

Publication needs explicit operator/checkpoint authority. Do not publish every
iteration.

1. From the feature worktree, fetch `origin/main` once.
2. Integrate current `origin/main` without rewriting already published history.
3. Rerun affected local regression and update `CHECKPOINT_HEAD`.
4. Run `git_loop_guard.py --phase publish` with the exact branch/head and the
   same task/owner/lease arguments.
5. Push the feature branch once, without force.
6. Run `--phase post-push` with that same lease; its
   `true_remote_branch_head` must equal the exact checkpoint head.
7. Request one current-head review and let path-classified CI run once.

Any head change invalidates earlier review/CI. A second identical hosted failure
fingerprint freezes publication as defined in `SUBAGENT_EXECUTION_RULES.md`.

## 4. Exact-head merge

Immediately before merge, query the PR and capture its current `headRefOid`.
It must equal the published checkpoint SHA and all required current-head gates
must be green. Merge without branch deletion:

```bash
gh pr merge <PR> --merge --match-head-commit "$CHECKPOINT_HEAD"
```

Never use `--admin` or `--delete-branch` in the loop. After GitHub reports the PR
merged, obtain the true merged main SHA with:

```bash
EXPECTED_ORIGIN_HEAD=$(git ls-remote origin refs/heads/main | awk '{print $1}')
```

If the PR head changed, merge queued a different head, authentication is absent,
or the result cannot be read back, stop as `STOP_MERGE_HEAD_DRIFT`. Do not guess
the merge SHA from the PR head because merge commits and squash commits differ.

## 5. Mac main fast-forward

Use the dedicated Mac main worktree; it must contain no unrelated edits.

```bash
git fetch origin main
python3 helper_scripts/maintenance_scripts/git_loop_guard.py \
  --phase main-sync --expected-origin-head "$EXPECTED_ORIGIN_HEAD" --human
git merge --ff-only origin/main
python3 helper_scripts/maintenance_scripts/git_loop_guard.py \
  --phase main-post-sync --expected-origin-head "$EXPECTED_ORIGIN_HEAD" --human
```

Failure means `STOP_MAC_MAIN_SYNC`; do not switch to a reset, stash, or force
operation. Preserve and surface the dirty worktree exactly as found.

## 6. Linux source fast-forward

Linux mutation requires the exact source-sync authority for the captured SHA.
First perform a read-only preflight and require:

- branch is `main`;
- `git status --porcelain` is empty;
- current HEAD is an ancestor of `EXPECTED_ORIGIN_HEAD` after fetching;
- fetched `origin/main` equals `EXPECTED_ORIGIN_HEAD`.

Only then use `git fetch origin main` followed by
`git merge --ff-only origin/main`. Never reset/clean the Linux checkout. Verify
Linux HEAD and status immediately afterward. A dirty or diverged Linux checkout
is `STOP_LINUX_SYNC`; it is not auto-repaired.

## 7. Three-side and runtime verification

Run the existing read-only four-head probe from the synchronized Mac repo:

```bash
python3 helper_scripts/healthchecks/four_head_reconcile_probe.py \
  --local-repo-root . \
  --ssh-host trade-core \
  --remote-repo-root /home/ncyu/BybitOpenClaw/srv \
  --human
```

Adjudication:

- `ALL_FOUR_SYNC`: Mac = true origin = Linux = engine build.
- `SOURCE_ONLY_DRIFT`: Mac = true origin = Linux; source sync is complete and
  the engine gap is source-only/exempt.
- `HALF_DEPLOY_REBUILD_REQUIRED`: Mac = true origin = Linux; source sync is
  complete, but deploy/rebuild is still required and must use its own authority.
- `MAC_BEHIND_ORIGIN`, `LINUX_BEHIND_ORIGIN`, or `INDETERMINATE`: three-side
  sync is not complete.

A loop cannot report `DONE` while its commits are only local, the PR is open,
the exact-head merge is unverified, or Mac/origin/Linux differ.

## 8. Branch and worktree retirement

Do not automatically delete the remote branch, local branch, or worktree.
Retirement is allowed only after all are true:

- PR is merged at the expected head;
- true origin main contains the result;
- Mac and Linux source sync is verified;
- the feature worktree is clean;
- no active task/agent owns the branch/worktree;
- the operator explicitly authorizes retirement.

After verified merge and three-side source sync, release the writer lease even
when branch/worktree retirement is not authorized. Release removes only the
local execution-control claim; it does not delete or rewrite Git state.

## Stop states

| State | Meaning |
|---|---|
| `STOP_GIT_START_STATE` | Wrong/detached/main branch, head drift, or dirty boot. |
| `STOP_WRITER_LEASE` | Missing, expired, foreign, colliding, or primary-worktree writer lease. |
| `STOP_CHECKPOINT_SCOPE` | Dirty path outside allowlist or checkpoint budget exceeded. |
| `STOP_PUBLISH_PREFLIGHT` | Branch/upstream/origin topology is unsafe or stale. |
| `STOP_PUSH_VERIFY` | Remote branch SHA does not equal the published checkpoint. |
| `STOP_MERGE_HEAD_DRIFT` | PR/merge did not bind the exact reviewed head. |
| `STOP_MAC_MAIN_SYNC` | Mac main is dirty, stale, detached, or non-ff. |
| `STOP_LINUX_SYNC` | Linux checkout is dirty, non-main, stale, or diverged. |
| `SOURCE_SYNCED_RUNTIME_PENDING` | Three git sides match; engine/deploy remains pending. |

## GitHub repository-settings gate

Repository code cannot prove or configure current GitHub branch protection by
itself. Before calling the system fully hardened, an authenticated admin must
verify `main` requires PRs and required checks, rejects force pushes/deletion,
and does not permit routine admin bypass. Record that verification with time and
repository. Until then the repo-side workflow is hardened but GitHub settings
remain `EXTERNAL_ADMIN_VERIFICATION_PENDING`.
