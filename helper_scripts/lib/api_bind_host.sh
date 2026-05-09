#!/bin/bash
# api_bind_host.sh — resolve the Trading API bind host safely.
#
# Default behavior is "auto": bind to the node's Tailscale IPv4 address when
# Tailscale is installed and up, otherwise bind to loopback. This keeps GUI
# access available over the tailnet without reopening all interfaces.

_openclaw_is_tailscale_ipv4() {
    local value="$1"
    [[ "$value" =~ ^100\.([6-9][0-9]|1[01][0-9]|12[0-7])\.[0-9]{1,3}\.[0-9]{1,3}$ ]]
}

resolve_openclaw_api_bind_host() {
    local requested="${OPENCLAW_BIND_HOST:-auto}"
    local ip

    case "$requested" in
        ""|"auto")
            if command -v tailscale >/dev/null 2>&1; then
                ip="$(tailscale ip -4 2>/dev/null | sed -n '1p' | tr -d '[:space:]' || true)"
                if _openclaw_is_tailscale_ipv4 "$ip"; then
                    printf '%s\n' "$ip"
                    return 0
                fi
            fi
            printf '%s\n' "127.0.0.1"
            ;;
        "tailscale"|"tailscale-ip"|"ts")
            if ! command -v tailscale >/dev/null 2>&1; then
                echo "ERROR: OPENCLAW_BIND_HOST=$requested requested, but tailscale is not in PATH" >&2
                return 2
            fi
            ip="$(tailscale ip -4 2>/dev/null | sed -n '1p' | tr -d '[:space:]' || true)"
            if ! _openclaw_is_tailscale_ipv4 "$ip"; then
                echo "ERROR: unable to resolve a Tailscale IPv4 address for OPENCLAW_BIND_HOST=$requested" >&2
                return 2
            fi
            printf '%s\n' "$ip"
            ;;
        "0.0.0.0"|"::")
            echo "ERROR: OPENCLAW_BIND_HOST=$requested exposes the Trading API on all interfaces." >&2
            echo "Use OPENCLAW_BIND_HOST=auto, OPENCLAW_BIND_HOST=tailscale, a specific Tailscale 100.64.0.0/10 IP, or 127.0.0.1." >&2
            return 2
            ;;
        *)
            printf '%s\n' "$requested"
            ;;
    esac
}
