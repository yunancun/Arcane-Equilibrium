# Operator Report: MAG-024/MAG-026 Scanner Authority Shadow

Date: 2026-05-07
Status: DONE

## What Changed

Scanner authority is now a consumed runtime config:

```toml
[authority]
mode = "legacy_gate"
```

Missing `[authority]` still defaults to `legacy_gate`, so current runtime behavior is unchanged by default.

In `advisory_shadow` and `advisory_enforced`, scanner legacy gate decisions are recorded as audit metadata instead of directly blocking the open path. Recorded fields include `details.scanner_gate.authority_mode`, `legacy_would_block`, and `legacy_block_reason`.

Scanner decay on an open position remains review-only evidence and is explicitly marked as not a close dispatch.

## Verification

Mac and Linux targeted Rust tests passed for:

- scanner authority config parsing/defaults
- scanner advisory decay no-close regression
- tick-pipeline scanner gate audit metadata
- scanner timeline replay compatibility

## Runtime Notes

No restart, deploy, or config flip was performed.

Current effective default remains `legacy_gate`. Enabling `advisory_shadow` requires adding `[authority].mode = "advisory_shadow"` to scanner config and restarting/reloading through the normal scanner config path.
