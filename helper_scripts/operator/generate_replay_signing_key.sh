#!/usr/bin/env bash
# ============================================================
# generate_replay_signing_key.sh — REF-20 Paper Replay Lab
# HMAC-SHA256 signing key 生成 + 部署 helper
# ============================================================
#
# Why this script exists / 為什麼有這個檔案：
#   REF-20 V3 §5 manifest signature contract 要求 server-side
#   HMAC-SHA256 簽名所有 replay manifest（防止 client tampering）。
#   Key 必須與 live `auth_signing_key` 隔離（V3 §5 key separation
#   invariant），且須支援 90d rotation + 180d retention（V3 §3 G9）。
#
#   This script generates a 256-bit random key, writes to the
#   spec'd path with mode 0600, and prints a fingerprint for the
#   operator to record in the offline secret vault. It does NOT
#   auto-deploy, auto-restart engines, or write to any DB table —
#   key version archive (replay_signing_keys, V042) is updated by
#   the rotation runbook step that follows this script.
#
# Spec source / 規格來源:
#   - V3 §3 G9 manifest quotas (90d/180d/key separation)
#   - V3 §5 manifest signature (HMAC-SHA256, 4 fail-mode audit)
#   - workplan R20-P0-T8 (Wave 1 P0)
#   - runbook docs/runbooks/replay_signing_key_rotation.md
#
# Usage / 使用：
#   $ OPENCLAW_SECRETS_DIR=/secure/openclaw bash helper_scripts/secrets/generate_replay_signing_key.sh <env>
#   <env> ∈ {paper, demo, live}
#
# Exit codes:
#   0   success (key written, fingerprint printed)
#   2   missing OPENCLAW_SECRETS_DIR or env arg
#   3   openssl unavailable
#   4   existing key would be overwritten without operator confirm
#   5   write permission denied / target dir missing
#   6   live `auth_signing_key` collision detected (separation invariant)

set -euo pipefail

# ----- 1. arg / env validation / 入參與環境校驗 ----------------
ENV_ARG="${1:-}"
if [[ -z "$ENV_ARG" ]]; then
    echo "ERROR: usage: $0 <paper|demo|live>" >&2
    exit 2
fi
case "$ENV_ARG" in
    paper|demo|live) ;;
    *)
        echo "ERROR: env must be one of: paper, demo, live (got '$ENV_ARG')" >&2
        exit 2
        ;;
esac

if [[ -z "${OPENCLAW_SECRETS_DIR:-}" ]]; then
    echo "ERROR: OPENCLAW_SECRETS_DIR not set" >&2
    echo "       expected: env var pointing at host secret root (e.g. /secure/openclaw)" >&2
    exit 2
fi

if ! command -v openssl >/dev/null 2>&1; then
    echo "ERROR: openssl not found in PATH" >&2
    exit 3
fi

TARGET_DIR="${OPENCLAW_SECRETS_DIR}/${ENV_ARG}"
TARGET_KEY="${TARGET_DIR}/replay_signing_key"
LIVE_AUTH_KEY="${OPENCLAW_SECRETS_DIR}/${ENV_ARG}/auth_signing_key"

if [[ ! -d "$TARGET_DIR" ]]; then
    echo "ERROR: target dir does not exist: $TARGET_DIR" >&2
    echo "       create it first with mode 0700, owned by the openclaw runtime user" >&2
    exit 5
fi

# ----- 2. existing key handling / 既有 key 處置 ---------------
if [[ -f "$TARGET_KEY" ]]; then
    if [[ "${OPENCLAW_REPLAY_KEY_FORCE:-0}" != "1" ]]; then
        echo "ERROR: existing replay_signing_key found at $TARGET_KEY" >&2
        echo "       refuse to overwrite without explicit OPENCLAW_REPLAY_KEY_FORCE=1" >&2
        echo "       for rotation, follow runbook: docs/runbooks/replay_signing_key_rotation.md" >&2
        exit 4
    fi
    BACKUP="${TARGET_KEY}.rotated.$(date -u +%Y%m%dT%H%M%SZ)"
    echo "INFO: existing key archived to $BACKUP"
    cp "$TARGET_KEY" "$BACKUP"
    chmod 0400 "$BACKUP"
fi

# ----- 3. live auth key separation invariant / 與 live auth key 必隔離 -
if [[ -f "$LIVE_AUTH_KEY" ]]; then
    LIVE_FP=$(openssl dgst -sha256 -hex < "$LIVE_AUTH_KEY" | awk '{print $NF}' | cut -c1-16)
    if [[ -f "$TARGET_KEY" ]]; then
        REPLAY_FP=$(openssl dgst -sha256 -hex < "$TARGET_KEY" | awk '{print $NF}' | cut -c1-16)
        if [[ "$LIVE_FP" == "$REPLAY_FP" ]]; then
            echo "ERROR: replay_signing_key fingerprint matches live auth_signing_key" >&2
            echo "       V3 §5 key separation invariant violated; refuse to proceed" >&2
            exit 6
        fi
    fi
fi

# ----- 4. key generation (256-bit / 32-byte) / 生成 256-bit key ---
NEW_KEY=$(openssl rand -hex 32)  # 32 bytes = 256 bits = 64 hex chars

# ----- 5. write with mode 0600 / 寫入 + 嚴格 permission ---------
umask 0077
printf '%s\n' "$NEW_KEY" > "$TARGET_KEY"
chmod 0600 "$TARGET_KEY"

# ----- 6. fingerprint for operator audit / 印 fingerprint 供操作員留存 ----
NEW_FP=$(openssl dgst -sha256 -hex < "$TARGET_KEY" | awk '{print $NF}' | cut -c1-16)
GENERATED_AT=$(date -u +%Y-%m-%dT%H:%M:%SZ)
EXPIRES_AT=$(date -u -v+90d +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u -d '+90 days' +%Y-%m-%dT%H:%M:%SZ)

cat <<EOF

==================================================================
REPLAY SIGNING KEY GENERATED — RECORD THIS BLOCK IN OFFLINE VAULT
==================================================================
env:               $ENV_ARG
path:              $TARGET_KEY
fingerprint(16):   $NEW_FP
generated_at:      $GENERATED_AT
rotation_due_at:   $EXPIRES_AT  (90 days, V3 §3 G9 target)
retention_until:   $(date -u -v+180d +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u -d '+180 days' +%Y-%m-%dT%H:%M:%SZ)  (V3 §5)
==================================================================

NEXT STEPS / 操作員後續：
  1. Copy the FINGERPRINT above to 1Password vault entry
       'OpenClaw / replay_signing_key / ${ENV_ARG}'
     and tag with rotation_due_at + retention_until.
  2. Update replay_signing_keys archive (V042 will land in Wave 3 P2a)
     INSERT INTO replay.replay_signing_keys (env, fingerprint, generated_at,
       rotation_due_at, retention_until) VALUES (...).
  3. Restart openclaw_engine + python API to pick up new key:
       bash helper_scripts/restart_all.sh
  4. Verify post-deploy:
       curl -s http://localhost:8001/api/v1/replay/health/signature
       expected: {"signature_check":"PASS","fingerprint":"$NEW_FP"}
  5. NEVER commit this fingerprint or key value to git; this script
     prints it once and only writes the key bytes to disk.
EOF

echo
echo "DONE. Key file mode: $(stat -f '%Sp' "$TARGET_KEY" 2>/dev/null || stat -c '%A' "$TARGET_KEY")"
exit 0
