# A3 V099 對抗性核驗

**Owner**: A3 · **Date**: 2026-05-27 · **Verdict**: **APPROVE-CONDITIONAL**
- Schema 本體: 8.5/10
- First-time operator walkthrough: 7.0/10
- Packet B 接入 ready: y (with 5 conditions)

> Reconstructed from sub-agent inline return (harness constraint).

## §1 IPC race graceful
- ✅ DB 層 PG advisory_xact_lock(99001) D10 PASS；LISTEN/NOTIFY D12 ACK；polling 5s fallback
- ⚠ GUI 層雙擊 / NETWORK lag 重發 POST 無 IMPL 保護（PB-1）
- ⚠ escalation 1h timer 起點僅由 switched_at_utc + audit INSERT 推算，三路通知 emit 時點無 column 紀錄（PB-2）

## §2 Packet B GUI 接入 readiness 5 維度
1. **ENUM uppercase**: V099 `'CONSERVATIVE'/'STANDARD'` 非 prompt 描述 `level_1_conservative` (PB-3 prompt drift；無實際 schema 問題)
2. **CONFIRM SWITCH typed-confirm**: ✅ case-sensitive ≤13 char；雙向統一 phrase acknowledged trade-off
3. **雙向 differential warning copy**: 升級「13/14」/降級「(a)/(c)/(d)/(f) 字母代號」對 first-time operator 不可讀（PB-4 HIGH UX critical）
4. **14 path matrix 漸進披露**: 20 行密度高，須分組或展開折疊
5. **Level 2 disabled state tooltip**: 「Wilson CI 95% lower bound 正向」對 first-time operator 不可解，須 plain-language（PB-5 HIGH UX critical）

## §3 Mainnet fallback closed 紀律
- ✅ 0 violation；Level 2 13 path 全不繞 5-gate / 永鎖 venue / §Decision 2 fail-safe
- ✅ `runtime_failsafe_override` / `disable_failsafe` grep 0 hit
- ✅ ENUM 不含 mainnet 路徑

## §4 雙時間戳 + escalation enum UX
- D13 PG TZ=Europe/Madrid empirical PASS；production cross-TZ 需 Packet C engine listener 加 PG/OS TZ assertion
- `escalation_result` enum 3 狀態（NULL/operator_responded/auto_escalated_to_sm04_defensive）GUI 顯示需 plain-language hover

## §5 First-time operator walkthrough 12 步
關鍵阻力點：
- 步驟 2 banner 直顯 `CONSERVATIVE` uppercase → 工程術語暴露
- 步驟 4 matrix 20 行 + 字母代號逃避行為
- 步驟 12 三路通知 fail → 1h auto SM-04 Defensive，需 hardware buzzer + UX 明示 active 鎖利減倉

## §6 5 push back

| # | 對象 | 內容 | 嚴重 |
|---|---|---|---|
| PB-1 | Packet B E1a | GUI 雙擊 / network lag POST 重發無 idempotency；client-side token | 中 |
| PB-2 | E1 / V099 | escalation 1h timer 起點精度；補 `escalation_started_at` column | 中 |
| PB-3 | Operator prompt drift | prompt ENUM naming 與 V099 實際不一致 | 低 |
| PB-4 | Packet B 未來 | 字母代號 (a)-(n) → 明文標籤強制 | **高** |
| PB-5 | Packet B 未來 | Wilson CI tooltip plain-language + README link | **高** |

## §7 Verdict

**APPROVE-CONDITIONAL** — V099 schema 本體 APPROVE，可 PM push + engine restart auto-migrate。

5 conditions（必入 Packet B/C dispatch AC）：
1. Packet B i18n mapping ENUM uppercase → 中文 label
2. Packet B warning modal 字母代號 → 明文標籤
3. Packet B Level 2 disabled state tooltip plain-language + link
4. Packet C engine listener 1h timer 起點精度 + PG/OS TZ assertion
5. Packet B client-side idempotency token 防 POST 重發

A3 UX AUDIT DONE: 8.5 schema / 7.0 walkthrough · Packet B 接入 ready with 5 conditions
