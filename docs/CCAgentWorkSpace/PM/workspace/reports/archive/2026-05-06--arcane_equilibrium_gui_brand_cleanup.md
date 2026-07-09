# 玄衡 GUI brand cleanup

Date: 2026-05-06
Role: PM
Status: APPROVED

## Decision

The external GUI entry surfaces now present **玄衡 · Arcane Equilibrium** branding. The old claw mark was removed from login and console headers.

## Scope

- Replaced claw-mark logo glyphs with a text monogram `玄`.
- Updated login, console, legacy index, trading chart titles, and visible header copy.
- Updated explanatory GUI copy where OpenClaw was incorrectly used as the total project brand.
- Added a static regression test that rejects the old claw glyph and old total-project GUI titles.

## Boundary

Retained compatibility/service names:

- `OpenClaw Gateway`
- `window.OpenClaw*` JavaScript namespaces
- `/openclaw` route
- `OPENCLAW_*`
- Rust crate / binary names
- Bybit connector paths

No runtime deploy, restart, DB write, strategy/risk config edit, or live authorization mutation was performed.

## Verification

- Targeted static asset pytest: `35 passed`.
- Old claw mark / old total-project GUI titles are now covered by static regression assertions.
- `git diff --check`: PASS.
- Three-end sync after commit: planned.
