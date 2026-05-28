# OPS-1 First-Use HTTPS Certificate Trust Runbook

Purpose: remove ambiguity during the first Caddy + Tailscale cert browser check.

1. Open the GUI by certificate hostname only:
   `https://<OPENCLAW_TLS_CERT_HOST>/`
2. Do not verify with `https://100.91.109.86/` or `https://trade-core/`; those names can trigger hostname mismatch.
3. If Chrome or Safari shows a certificate/privacy warning, treat it as a checkpoint, not a prompt to click through.
4. Inspect the certificate subject/SAN. It must include the Tailscale cert hostname configured by `OPENCLAW_TLS_CERT_HOST`.
5. If the hostname is wrong, stop and fix `OPENCLAW_TLS_CERT_HOST`, regenerate the Caddyfile, and re-run `tailscale cert`.
6. If the issuer or validity window is wrong, stop and run the TLS renewal service manually, then reload Caddy.
7. Only continue when the browser shows a trusted certificate for the exact hostname.
8. Then verify `https://<OPENCLAW_TLS_CERT_HOST>/api/v1/healthz` returns 200.
9. After healthz is green, proceed to Secure cookie and CSRF enforcing checks.

Persistent warning after hostname correction is a deploy blocker for OPS-1 enforcing.
