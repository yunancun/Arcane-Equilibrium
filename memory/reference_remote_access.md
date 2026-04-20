---
name: Remote Access Configuration
description: Tailscale remote access setup for Trading GUI and OpenClaw Gateway (2026-03-27)
type: reference
---

## Remote Access Configuration (2026-03-27)

### Trading GUI
- URL: `http://trade-core:8000`
- Bind: `0.0.0.0:8000` (systemd user service)
- Config: `~/.config/systemd/user/openclaw-trading-api.service`
- No HTTPS needed (Tailscale WireGuard encrypts)

### OpenClaw Gateway
- URL: `https://trade-core.tail358794.ts.net`
- Bind: loopback + `--tailscale serve` (auto HTTPS)
- Config: `~/.config/systemd/user/openclaw-gateway.service`
- Token: `<REDACTED>`
- Key flags: `--port 18789 --token <REDACTED> --tailscale serve`
- `~/.openclaw/openclaw.json`: `bind=loopback`, allowedOrigins includes HTTPS domain

### Device Pairing
- MacBook Pro auto-paired in `~/.openclaw/devices/paired.json`
- No password needed, token auth only

### Key Files (NOT in git)
- `~/.config/systemd/user/openclaw-trading-api.service`
- `~/.config/systemd/user/openclaw-gateway.service`
- `~/.openclaw/openclaw.json`
- `~/.openclaw/devices/paired.json`
