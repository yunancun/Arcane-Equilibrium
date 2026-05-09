---
name: GitHub Actions macOS cost policy
description: Private repo CI: macOS runner 10x multiplier; never push-trigger macOS, only PR + weekly schedule
type: feedback
originSessionId: 7df8889a-72c6-455e-8dac-abbc0b15b3f1
---
Private repo `yunancun/BybitOpenClaw` runs `srv/.github/workflows/ci.yml`. Current policy (2026-05-09): Linux runs on every push to main; macOS only runs on `pull_request` and a weekly Monday 03:00 UTC schedule. Job-level `if: ${{ matrix.os != 'macos-latest' || github.event_name != 'push' }}` enforces this.

**Why:** Repo is private (free tier = 2000 billable minutes / month). macOS-latest carries a 10x billing multiplier. Operator commits at very high velocity (~99 commits / day in early May 2026); running Linux + macOS on every push consumed ~90% of the monthly quota within 9 days. Operator approved the PR-only + weekly cron split on 2026-05-09 rather than buying additional minutes.

**How to apply:**
- Do not propose adding macOS to the push trigger again without recomputing quota impact.
- New CI workflows in this repo default to Linux-only on push; if a workflow truly needs macOS, mirror the same `if:` guard.
- Future Apple Silicon deployment target invariant is still honored — weekly schedule + on-demand PR coverage is enough; no need to push-trigger macOS to "prove" it builds.
- If the user later asks about Actions cost again, the bottleneck is almost always macOS multiplier × commit frequency, not Linux runners.
- Same change must be reflected in `.codex/MEMORY.md` (see "GitHub Actions cost policy" section there) so codex sessions don't re-enable push-trigger macOS.
