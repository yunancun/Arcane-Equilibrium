# Engineering Workflow Rules

## Preferred collaboration style

Use compact shell-based workflow with the following properties:

- one major shell block at a time
- bilingual comments (Chinese + English)
- clear numbered sections like `==[1]==`, `==[2]==`
- explicit instruction on what output to paste back
- avoid asking user to paste huge logs
- request only key excerpts needed for diagnosis

## Output discipline

Prefer requests like:

- paste only `==[1] path + git check ==`
- paste only `==[2] compile key scripts ==`
- paste only `==[3] run I10 clean recheck ==`

instead of full raw terminal dumps.

## Safety discipline

- default to read-only diagnosis first
- do not delete or move files unless the step explicitly says so
- do not restructure script physical layout casually
- protect runtime compatibility over cosmetic cleanup

## Git discipline

- keep public repo sanitized
- keep secrets/runtime/logs local-only
- review `git status --short` before commit
- push only after local compile / structural verification

## Debugging discipline

When a stage fails, prefer:
1. identify exact latest json artifact
2. inspect blocking_reasons / failed_checks / warning_flags
3. locate the earliest broken upstream stage
4. repair the earliest true blocker
5. rerun narrow checks before broad regression

## Interpretation discipline

Do not over-interpret empty state as a software defect.
Where appropriate, encode explicit state showing:

- no real trade occurred
- no AI call was actually required
- stage blocked because upstream conditions were empty/not eligible

This avoids false failure narratives.
