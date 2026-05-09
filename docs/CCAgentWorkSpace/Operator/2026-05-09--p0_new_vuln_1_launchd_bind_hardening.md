# P0-NEW-VULN-1 Launchd Bind Hardening

Date: 2026-05-09
Status: DONE

The Mac launchd Trading API template now binds `127.0.0.1` instead of
`0.0.0.0`. The launchd preflight also rejects an installed Trading API plist
that binds all interfaces, and the static regression now covers this.

No launchd service was loaded/unloaded and no runtime process was changed.
