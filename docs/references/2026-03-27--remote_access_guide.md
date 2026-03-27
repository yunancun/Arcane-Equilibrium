# Remote Access Guide / 远程访问指南

## Current: SSH Tunnel (已可用)

The API server binds to 127.0.0.1:8000. Access remotely via SSH tunnel:

```bash
# From your local machine:
ssh -L 8000:127.0.0.1:8000 ncyu@your-server-ip

# Then open http://localhost:8000 in your browser
```

## Option 2: Tailscale (推荐)

```bash
# On server:
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
# Note the Tailscale IP (e.g., 100.x.y.z)

# Access from any Tailscale-connected device:
# http://100.x.y.z:8000
```

Pros: zero-config VPN, encrypted, no port forwarding needed
Cons: requires Tailscale client on all devices

## Option 3: Cloudflare Tunnel

```bash
# Install cloudflared
wget https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64
chmod +x cloudflared-linux-amd64
sudo mv cloudflared-linux-amd64 /usr/local/bin/cloudflared

# Create tunnel
cloudflared tunnel login
cloudflared tunnel create openclaw
cloudflared tunnel route dns openclaw trading.your-domain.com
cloudflared tunnel run --url http://127.0.0.1:8000 openclaw
```

Pros: HTTPS, custom domain, no open ports
Cons: requires Cloudflare account + domain

## Security Checklist

- [ ] API token set (not default)
- [ ] CORS configured (OPENCLAW_CORS_ORIGINS)
- [ ] Rate limiting enabled (OPENCLAW_RATE_LIMIT)
- [ ] CSP headers (if using Cloudflare, add via dashboard)
- [ ] State file permissions 0o600
