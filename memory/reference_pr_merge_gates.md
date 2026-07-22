---
name: reference_pr_merge_gates
description: "GitHub main-branch merge gates on Arcane-Equilibrium — Codex auto-reviewer threads, [skip ci] head trap, and the Mac governed-attestation limitation."
metadata:
  node_type: memory
  type: reference
  originSessionId: 07e83463-9c2c-4475-8221-65951702b432
  modified: 2026-07-21T17:42:28.335Z
---

**Merging a PR to `main` on `yunancun/Arcane-Equilibrium` (public repo, ruleset "Protect main after public hardening", id 19071223):** requires PR, strict required status checks (classify-paths, migration/stable_id/git-workflow/hygiene guards, 3× CodeQL Analyze), **thread resolution**, 0 bypass actors, `current_user_can_bypass=never`. `required_approving_review_count=0` (no human approval needed).

Durable gotchas (all hit 2026-07-21, PRs #104/#105):

1. **Codex bot (`chatgpt-codex-connector[bot]`) auto-reviews EVERY PR** ("💡 Codex Review") and leaves inline threads. Unresolved threads block merge → `gh pr merge` fails with **"base branch policy prohibits the merge"** (misleading; `mergeable_state` shows `blocked`). Codex threads are frequently **real P1s** (it caught 3 valid forge-resistance gaps + a doc-consistency P1 this session) — READ them, fix or resolve with `resolveReviewThread` mutation, then merge. It re-reviews on each push, so expect another pass after a fix.

2. **`[skip ci]` on the PR HEAD commit blocks the merge** — GitHub-native skip means the required checks never run → never satisfy the ruleset. Put code/doc chapters with `[skip ci]` in the middle of the branch, but the HEAD commit that becomes the PR tip must NOT carry `[skip ci]` (so CI runs on Linux runners).

3. **`gh pr merge --admin` is forbidden** by the ruleset; use `--merge --match-head-commit <sha>` (exact head). `mergeable_state` can lag "clean" by ~30-60s after checks go green; re-check before assuming a real block.

4. **The governed `capture-command` wrapper cannot run pytest on Mac** — it hard-isolates `HOME`, hiding the user-site pytest (`~/Library/Python/3.10/...`); there is no HOME-independent pytest. So E2/E3/E4 governed test-evidence attestation on Mac degrades to `LOCAL_REPRODUCIBLE` (direct pytest under a git-status mutation guard); a governed-receipt-attested run needs Linux `trade-core`. This is the same PLATFORM_ATTESTED boundary that makes closure PASS a trusted-host step. See [[project_ssh_bridge_workflow]] and [[project_2026_07_21_aiml_s0_adoption_gate]].
