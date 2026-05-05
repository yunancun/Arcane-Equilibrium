---
status: accepted
date: 2026-05-05
supersedes: bilingual-comment-mandate (informal, 2025–2026)
---

# New code comments default to Chinese-only; bilingual mandate retired

Effective 2026-05-05, new and modified comments are written in Chinese only; the prior bilingual-comment mandate (every comment in both Chinese and English) is retired. Rationale: bilingual comments pushed `runner.rs` to 41% comment-by-line and added ~4000 LOC of comment overhead during V055 + REF-20 Sprint C, with significant token + LOC cost. Chinese alone carries the necessary semantics for this single-operator project.

## Consequences

Existing bilingual blocks are not proactively cleaned, but when modifying a bilingual block the English half is removed in the same edit. E2 review: Chinese-only comments PASS; English-only comments are still pushed back (Chinese is the required layer). Identifier names, log keys, and error strings stay English — this rule is for human-prose comments only.
