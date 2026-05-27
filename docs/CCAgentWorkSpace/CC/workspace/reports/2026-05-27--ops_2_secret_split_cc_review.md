# CC 合規審計 — OPS-2 SECRET-SPLIT Phase 1 IMPL

**Owner**: CC · **Date**: 2026-05-27 · **Verdict**: **APPROVE-CONDITIONAL A-** · **Block commit**: NO

合規：16/16 PASS + 9/9 PASS + 4/4 hard gate PASS + Mainnet env-var fallback closed 紀律 reconcile **PASS（語意切換非紀律違反）**

> Reconstructed from sub-agent inline return (harness constraint).

## §1 — 16 根原則 cross-ref（16/16 PASS or N/A）

10 PASS + 6 N/A — 全合規。關鍵：
- #1 Single write entry: `_write_signed_live_authorization` 仍唯一寫 authorization.json 路徑
- #2 Read/write separation: Phase 1 fallback 是讀路徑，未引入新寫路徑
- #5 Survival > profit: Phase 1 設計優先 backward-compat
- #6 Default conservative: 兩 env unset → fail-closed `AuthError::LiveAuthSigningKeyMissing`
- #8 Trade 可解釋: WARN emit `event=ops2_secret_split_phase1_fallback`；seed echo 標記
- #10 認知誠實: E1 報告 fact/inference/assumption 三類分明
- #14 零外部成本: 純 local file + env var

## §2 — 9 安全 invariants verify（9/9 PASS）

- **I1** 5-gate live boundary: PASS / 強化（#4 +1 file 並列；#5 signing key 切換但 HMAC 算法 0 變更）
- **I2** Python sign / Rust verify: PASS（line 253 single sign entry 不變；Rust verify 邏輯 0 變更）
- **I3** LiveDemo 不降級: PASS（fallback 不分 endpoint, 同 fail-closed）
- **I4** Mainnet env-var fallback closed: PASS（詳 §4 reconcile）
- **I5** Watcher teardown: PASS（5s poll + AuthError teardown 0 改動）
- **I6** Mainnet panic block: PASS（main.rs:399-407 不動，Phase 2 才加第二 panic）
- **I7** Bybit retCode: N/A
- **I8** 不 fake: PASS（cross-lang fixture pin `1b2b18d7...` 雙端 byte-identical 真實）
- **I9** Operator + live_reserved: PASS（auth path 0 改動）

## §3 — Hard boundary 體檢（5/5）

| Gate | 狀態 |
|---|---|
| #1 live_reserved global mode | 不變 |
| #2 Operator role auth | 不變 |
| #3 OPENCLAW_ALLOW_MAINNET=1 | 不變 |
| #4 Valid secret slot | **強化**（+1 file 並列；chmod 600；seed [ ! -f ] 嚴守 rotated key） |
| #5 Signed authorization.json + env_allowed | **強化**（signing key vs IPC HMAC blast radius 隔離；cross-lang fixture byte-identical） |

## §4 — Mainnet env-var fallback closed 紀律 reconcile

**CLAUDE.md §四原文**：「Mainnet env-var fallback as the only credential source is closed.」

**精確語意**：禁止「以 env var 為**唯一** credential 來源」（指 Bybit api_key/api_secret slot）。

**本 IMPL Phase 1 fallback 性質**：
- fallback 範圍 = **HMAC signing key material**（簽 authorization.json），**不**是 Bybit credential
- 兩端 env 都 unset → fail-closed
- gate #4 secret slot（Bybit api_key/api_secret）邏輯 0 改動

**Reconcile**：Phase 1 fallback 在 signing-key 域 vs CLAUDE.md「mainnet credential fallback closed」紀律屬不同信任域，**不觸碰該紀律**。

**Phase 2 紀律收緊軌跡**：D+0..D+14 fallback + WARN → D+14 Phase 2 移 fallback + 第二 panic block + Python reason rename。TODO sign-off block + 3 處 `TODO(P1-OPS-2-SECRET-SPLIT-PHASE-2 D+14)` code anchor 防永久化。

## §5 — Verdict: APPROVE-CONDITIONAL

**5 Conditions（Phase 2 cutover 前清）**：
1. **C-1 (P0 hard gate)**: D+14 land Phase 2 PR — 移 fallback + main.rs 第二 panic block + Python reason 字串 rename + AuthError::IpcSecretMissing 變體刪除。**Phase 2 不 land 即 hardcoded fallback 永久化 = 違規。**
2. **C-2 (P1)**: D+14 cutover 前 operator empirical 確認 14d soak `grep -c "ops2_secret_split_phase1_fallback"` 累積 = 0
3. **C-3 (P1)**: 14d soak 期間 operator 至少走過 1 次 `/api/v1/live/auth/renew` 重簽 authorization.json
4. **C-4 (P2)**: E3-MED-1 audit row endpoint follow-up 須在 OPS-2 runbook §G land 前敲定
5. **C-5 (P2)**: BB 須 ping operator 確認 repo 外 Grafana/journald 規則同步加 `live_auth_signing_key_missing` 字串

**Strengths**: 16/16 + 9/9 + 5-gate 4/4 + 強化 #4 #5；cross-lang fixture 真實；Phase 1 surgical；seed [ ! -f ] 守 rotated；Phase 2 D+14 due TODO anchor；4 IPC client domain grep 0 hit；跨平台 0 user-home 硬編碼；認知誠實。

CC AUDIT DONE: APPROVE-CONDITIONAL · BLOCK commit: NO
