---
name: restart_all.sh bind host safe tailnet default
description: Non-interactive restart scripts must preserve Tailscale GUI access without defaulting to all-interface binds.
type: feedback
originSessionId: 5fa09684-0362-40a5-922c-c5caf97fe97e
---
Lifecycle restart scripts run through non-interactive SSH and do not reliably
read `.bashrc`, `.profile`, or user environment.d files. The bind-host decision
therefore must be encoded in the scripts, not left as an operator shell
profile assumption.

Correct rule:
- default `OPENCLAW_BIND_HOST=auto`
- `auto` resolves the node's Tailscale IPv4 address with `tailscale ip -4` and
  binds that concrete `100.64.0.0/10` address when Tailscale is up
- if Tailscale is unavailable, fallback is `127.0.0.1`
- `OPENCLAW_BIND_HOST=tailscale` forces tailnet-only binding and fails closed if
  no Tailscale IPv4 exists
- `OPENCLAW_BIND_HOST=0.0.0.0` and `OPENCLAW_BIND_HOST=::` are forbidden because
  they expose the Trading API on all interfaces, not just the tailnet

This preserves GUI access at `http://trade-core:8000` over Tailscale while
keeping P0-NEW-VULN-1 closed. Do not reintroduce default `0.0.0.0`; use a
specific Tailscale IP, `tailscale`, or Tailscale Serve / reverse proxy instead.
