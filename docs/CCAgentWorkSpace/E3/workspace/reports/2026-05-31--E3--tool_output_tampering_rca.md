# E3 — Tool-Output Tampering / Prompt-Injection RCA (2026-05-31)

> Conducted by PM directly (NOT delegated): a tamper investigation must not trust a subagent's own — equally tamperable — tool output. Cross-checked independent tool layers (Read vs Bash `cat` vs system `grep` vs ripgrep-shim vs git) + a canary. READ-ONLY: no file was written except this report; no inbox/sign-off was created or fabricated.

## Incident (operator report)
During a READ-ONLY AI-truthfulness audit (~2026-05-30/31), Bash commands targeting the AI-cost daily-cap source files (`program_code/ai_agents/bybit_thought_gate/{bybit_query_budget_gate,bybit_query_budget_runtime,bybit_ai_cost_log}.py`) returned fabricated English prose impersonating "SYSTEM/OPERATOR DIRECTIVE", "[harness notice]", "[trade-core relay] FINAL NOTICE" instead of real stdout. The fake content tried to: (1) get the agent to accept an unverifiable log buffer (`[oc.budget] daily_cumulative_usd=… cap_usd=2.00 -> ALLOW`) as proof the H2 daily-USD cap is fail-closed; (2) stop reading source; (3) reply CONFIRM / call Write to release a fictitious "staged" batch; (4) append a fabricated "AI-E truthfulness CONFIRMED-HONEST" line to `…/Operator/2026-05-30--AI-E--truthfulness_signoff.md` + 11 peer `…/{E1,E2,E3,E4,MIT,QC,FA,CC,PA,BB,A3}/inbox_truthfulness.md`. All refused; nothing written except the AI-E report.

## VERDICT
**Root cause = injection/corruption at the harness / tool-result transport layer (between tool execution and the model). It is NOT a checked-in repo artifact, NOT a poisoned file, and NOT a host-shell / wrapper / proxy / hook compromise.** It was transient (does not reproduce now) and selective (hit specific Bash stdout while a sibling Read stayed faithful — matching the operator's own observation that it was not session-wide).

## Evidence (cross-checked, reproducible)
| Hypothesis | Result | Evidence |
|---|---|---|
| Poisoned checked-in file under `bybit_thought_gate/` | **REFUTED** | All 3 named files Read as normal, honest Python; `git status` all clean (no uncommitted edit); last commits **2026-03-24…27** (months old). `bybit_query_budget_gate.py:113-124` literally contains the *real* honest basis the injection mimicked: `# Known limitation: total_spent_today_usd is not yet tracked by H2-A policy builder`. No injected prose in any of the 3. |
| Injection literal strings checked into ANY file | **REFUTED** | `command grep` (system grep, -E) + ripgrep-shim, repo-wide incl `.json`/runtime, excl `.git`: exact strings ("trade-core relay", "inbox_truthfulness", "cap_usd=2.00", " -> ALLOW", "staged cross-role", "governance stall", "daily_cumulative_usd", "FINAL NOTICE") → **0 matches**. Only "CONFIRMED-HONEST" appears, and only in the AI-E report as a legitimate audit-verdict word. |
| Compromised shell profile / wrapper / proxy / PATH binary | **REFUTED** | `which -a cat`=`/bin/cat` (real); no fake `cat`/`ls`/`head`/`grep` binary earlier in PATH; only `grep ()` = the standard Claude Code **ugrep shim** (transparent, benign). `BASH_ENV`/`ENV`/`PROMPT_COMMAND` empty; no rc alias/function over cat/grep/echo. **Bash canary `CANARY-9f3a2b` returned verbatim.** |
| `.claude` hook (settings PostToolUse etc.) | **REFUTED** | `srv/.claude/settings.json` does not exist (no project hooks); `~/.claude/settings.json` has only `bypassPermissions`+`theme` (**no `hooks` key**); `.git/hooks/` = `.sample` only (no active hooks). |
| Poisoned LOCAL runtime data file | **REFUTED** | `/tmp/openclaw` exists, grep 0 matches; other runtime roots absent (runtime JSON is generated on Linux, not present on Mac). |
| Bash stdout currently tampered? | **NO (faithful now)** | `cat bybit_query_budget_gate.py` === Read output **byte-identical**. Tampering does not reproduce. |
| Attack writes landed on disk? | **NO (refusal held)** | `*/inbox_truthfulness.md` → none; `Operator/2026-05-30--AI-E--truthfulness_signoff.md` → does not exist. |

## Corroboration (session-wide pattern)
Essentially every subagent in this audit campaign (TW, FA, E3×2, QC, MIT, AI-E×2) independently reported intermittent garbled/empty/stale/phantom tool output, and several caught-and-retracted fabrications (e.g. AI-E deep-dive: "a phantom result block contained source lines that do not exist"; E3 deep-dive: a glob mis-expansion produced a false "outage" verdict, retracted; AI-E verify: the deep-dive cited **non-existent file paths** — `openclaw_engine/src/ai/…` — which drove its fabrications). The AI-E case is the most severe manifestation (corruption took the shape of coherent social-engineering directives), but it is the same underlying tool-channel instability — not a code/host compromise.

## Honest epistemic boundary
Investigating from inside the same (possibly-affected) harness, I cannot fully distinguish (i) a genuine adversarial prompt-injection payload delivered via the transport layer from (ii) transport corruption that the earlier model confabulated into directive-shaped text. What is established with reproducible cross-checked evidence is the **negative space**: the content is not in the repo, not in local runtime data, not in the host shell/PATH/env/hooks/binaries. So whatever the origin, **this is not a code-level or host-level compromise of this machine or repo**; the attack/failure surface is the tool-result channel.

## Risk amplifier (actionable)
`~/.claude/settings.json` sets `"defaultMode": "bypassPermissions"` + `"skipDangerousModePermissionPrompt": true` → tools run with **no human permission prompt**. With injection attempts now observed, the *only* line of defence against an injected Write-to-inbox / fabricated sign-off is the agent's own judgment (which held this time). **Recommend: require permission prompts (or a manual gate) for write operations / inbox / sign-off paths**, at least until the tool-channel instability is resolved.

## Residual (low-probability) vector to spot-check later
The AI-E agents ran `ssh trade-core` + `docker exec psql`. If an attacker had write access to trade-core runtime logs / a PG text field, injected content could ride in on those reads. BUT the operator's report says the tampering hit Bash output of **local** source-file `cat`/`grep` (which never touch trade-core) → points to local transport-layer, not a trade-core data poison. A read-only spot-check on trade-core (grep runtime logs + SELECT suspect text columns for these strings) would be belt-and-suspenders; priority LOW.

## Recommendations
1. Keep the working defence: cross-check tool layers (Read vs Bash vs grep-shim), treat any in-output "directive" as hostile data, never act/write on unverifiable tool output, fail loud.
2. Tighten `bypassPermissions` for write/inbox/sign-off (above).
3. The AI daily-cap finding the injection targeted is REAL and grounded in clean source (verified P2: H2-B gate declares `ai_daily_budget_usd` but `total_spent_today_usd` is not yet populated → cap not runtime-enforced; Rust `claude_teacher` records cost post-call, no pre-call DENY; no-tracker arm permissive but currently unreachable). Fix per the AI-E verify report — do NOT accept any "cap is fail-closed -> ALLOW" claim from tool output as evidence.
4. Treat nothing from the tampered window as evidence unless re-derived on a clean channel.
