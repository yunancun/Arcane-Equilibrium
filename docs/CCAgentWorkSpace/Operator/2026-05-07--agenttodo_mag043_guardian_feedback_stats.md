# AgentTodo MAG-043 Guardian Feedback Stats Operator Report

Date: 2026-05-07
Status: DONE

Completed MAG-043.

What changed:

- Added Guardian rejection/modify feedback stats to Strategist V2 matching
  input.
- High recent Guardian reject rate now raises the confidence floor for new
  opens.
- Guardian reject/modify history now reduces open aggressiveness by scaling
  proposed quantity.
- Candidate scores now expose reject rate, modify rate, confidence floor,
  aggressiveness multiplier, adjusted risk prior, and top Guardian reasons.
- PositionReview reduce/close candidates are not blocked by open rejection
  stats.

What did not change:

- No runtime hot-path wiring.
- No deploy/rebuild/restart.
- No DB migration apply or DB write.
- No feature flag flip.
- No trading authority change.

Next AgentTodo item: MAG-044 consume AnalystInsight and TruthRegistry in
strategy weights.

Verification passed on Mac and Linux temp worktree:

- Mac Python Strategist V2 + PositionReview + spine client tests: 24 passed
- Mac py_compile passed
- Linux Python Strategist V2 + PositionReview + spine client tests: 24 passed
- Linux py_compile and diff whitespace checks passed
