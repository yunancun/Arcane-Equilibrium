---
name: Remote Access Configuration
description: Current Trading GUI remote-access boundary after Gateway retirement (updated 2026-07-16)
type: reference
---

## Remote Access Configuration

### Trading GUI
- Service: authenticated FastAPI OpenClaw Control Console on port `8000`
- Bind: concrete tailnet IPv4 when explicitly selected, otherwise loopback
- Config: `~/.config/systemd/user/openclaw-trading-api.service`
- Remote access must use the current Trading API bind/reverse-proxy policy; never
  expose it on `0.0.0.0` or `::`.
- The retained `/api/v1/openclaw/*` routes are local, authenticated, and
  read-only control/monitoring surfaces.

### Retired surfaces (2026-07-16)

- The external OpenClaw Gateway, its system service, remote endpoint, proxy, and
  device-pairing path were retired and removed.
- The Grafana container, dashboards, data writer, and remote monitoring endpoint
  were retired and removed.
- Archived setup instructions are historical evidence only and must not be used
  to recreate either surface without a new accepted security/architecture
  decision.

### Active secret boundary

- Control API credentials belong only in protected runtime secret storage and
  must never be committed or copied into documentation.
