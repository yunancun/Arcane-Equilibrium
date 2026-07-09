# GUI Baseline Manifest — Pre-Redesign Snapshot (2026-07-09)

Immutable snapshot of the OpenClaw Control Console GUI **before** the ground-up redesign
(S1 "Terminal" direction). Purpose: **comparison/reference** during the redesign, and
**rollback in extreme cases**.

## Baseline identity
| Field | Value |
|---|---|
| Git tag (canonical) | `gui-baseline-2026-07-09` |
| Commit | `d077949fc1ec1a39b6121566f8a2333f87fee27c` |
| Date | 2026-07-09 |
| Scope | `program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/` |
| Files / lines | **61 files / 36,337 lines** |
| Portable image | `gui-baseline-2026-07-09-static.tar.gz` |
| Image sha256 | `d6a15818a8da05bab4506f0b7a52778423cc3b2c175a967a86acfc1a6d66e37e` |

> The image is the **committed tree** at the tag (via `git archive`). `login.html` had an
> unrelated parallel-session uncommitted edit at snapshot time — correctly **excluded** so the
> image byte-matches the tag. The git tag is the canonical rollback anchor; the tarball is a
> portable convenience and can be regenerated anytime with:
> `git archive --format=tar.gz HEAD -- <scope>` at the tag.

## Rollback (extreme case)
```bash
# restore the entire GUI to the baseline (working-tree only; review + commit deliberately)
git checkout gui-baseline-2026-07-09 -- \
  program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/
# or restore a single file
git checkout gui-baseline-2026-07-09 -- <path/to/file>
# or extract from the portable image
tar xzf gui-baseline-2026-07-09-static.tar.gz
```

## Compare (during development)
```bash
# what changed vs baseline
git diff gui-baseline-2026-07-09 -- <path>
git diff --stat gui-baseline-2026-07-09 -- \
  program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/
```

## File manifest (line counts at baseline)
| lines | file (relative to static/) |
|---:|---|
| 47 | `_dashboard_card.html` |
| 264 | `app-actions.js` |
| 654 | `app-gui.js` |
| 413 | `app-learning.js` |
| 1628 | `app-paper.js` |
| 415 | `app-review.js` |
| 744 | `app.js` |
| 238 | `autonomy-posture.js` |
| 468 | `canary-tab.js` |
| 132 | `cards/dl3_card.html` |
| 184 | `cards/linucb_card.html` |
| 193 | `cards/news_card.html` |
| 120 | `cards/teacher_card.html` |
| 560 | `common-formatters.js` |
| 482 | `common-modals.js` |
| 357 | `common-mode-badge.js` |
| 1046 | `common.js` |
| 1074 | `console.html` |
| 758 | `earn-tab.js` |
| 1921 | `governance-tab.js` |
| 255 | `governance.js` |
| 1056 | `handoff_helper.js` |
| 394 | `i18n_zh.js` |
| 285 | `index.html` |
| 997 | `js/agent-tracker.js` |
| 83 | `js/fetch_with_csrf.js` |
| 270 | `js/openclaw-agent-control.js` |
| 168 | `login.html` |
| 1126 | `risk-tab.js` |
| 651 | `styles.css` |
| 425 | `tab-agents.html` |
| 1457 | `tab-ai.html` |
| 1442 | `tab-demo.html` |
| 427 | `tab-development.html` |
| 525 | `tab-earn.html` |
| 389 | `tab-edge-gates.html` |
| 1601 | `tab-governance.html` |
| 495 | `tab-learning.html` |
| 551 | `tab-live.html` |
| 1886 | `tab-live.js` |
| 262 | `tab-monitoring.html` |
| 1025 | `tab-paper.html` |
| 395 | `tab-phase4.html` |
| 66 | `tab-replay.html` |
| 606 | `tab-risk.html` |
| 1826 | `tab-settings.html` |
| 258 | `tab-stock-etf-auth-account.js` |
| 480 | `tab-stock-etf-data-policy.js` |
| 132 | `tab-stock-etf-disable-cleanup.js` |
| 296 | `tab-stock-etf-evidence-paper.js` |
| 642 | `tab-stock-etf-fallbacks.js` |
| 164 | `tab-stock-etf-phase0.js` |
| 180 | `tab-stock-etf-readiness.js` |
| 177 | `tab-stock-etf-reconciliation.js` |
| 138 | `tab-stock-etf-release-packet.js` |
| 303 | `tab-stock-etf-scorecard-launch.js` |
| 402 | `tab-stock-etf.html` |
| 217 | `tab-stock-etf.js` |
| 820 | `tab-strategy.html` |
| 1089 | `tab-system.html` |
| 678 | `trading.html` |
| **36,337** | **61 files total** |

## Visual reference (before / after)
- **Before (this baseline):** the live console at `http://trade-core:8000/console` (authed, runtime-driven) is the visual "before". A headless screenshot is not captured here (the console needs the running authed app + engine + DB; not reproducible from static files alone). Screenshot the live app if a pixel "before" is needed.
- **After (redesign target):** S1 sample `https://claude.ai/code/artifact/07c769ec-b340-4118-812f-27decdaa2ea8` (chosen direction). Design system + specs: `scratchpad/gui/GUI-DESIGN-WORKING-DOC.md` + `scratchpad/gui/design/`.

## Related
- Redesign working doc (anchor): `scratchpad/gui/GUI-DESIGN-WORKING-DOC.md`
- Deep specs: `scratchpad/gui/design/{01_typography,02_layout,03_copy,04_identity}.md`
- Decision brief: `scratchpad/gui/GUI-REDESIGN-decision-brief.md`
