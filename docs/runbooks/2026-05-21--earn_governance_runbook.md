# Bybit Earn Governance — Operator 介入 SOP

**狀態：** Draft（v5.7 §4 + §8 Sprint 1A-α land；ADR-0030/0031/0032 placeholder pending commit）
**版本：** v0.1（2026-05-21）
**Runbook ID：** RUNBOOK-EARN-GOV-001
**Module：** Bybit Earn dynamic APR + asset movement Guardian
**Severity coverage：** SEV-1 / SEV-2 / SEV-3
**On-call role：** Operator（5-Gate Adapter Gate 1 / Gate 4 manual approval）+ PM（governance review）+ E3（cred / authorization 流程）
**Depends on：** ADR-0030 (Copy Trading evidence-gated; Y1 末 4-gate framework；本 runbook 同期 Earn evidence 上 Y1 income 計算用) / ADR-0031 (Framework expansion — Earn governance 父框架) / ADR-0032 (Earn asset movement Guardian — 5-gate adapter + Decision Lease retrofit + audit log) / v5.7 §4 (Bybit Earn dynamic APR + governance) / v5.7 §8 Sprint 1A (Earn API recorder + Earn governance policy land) / CLAUDE.md §四 D1c (no withdrawal API key) + D1d (Earn governance per ADR-0030/0031/0032)

> **Hands off — operator only**：所有 Earn stake / redeem **必走 Console + Decision Lease + 5-gate adapter**；本 runbook 列的 SQL / IPC 路徑 **僅供 emergency mitigation + audit verification**，平常運維走 Console UI。Y1 first 3 months 強制 manual rebalance；不允許任何 auto-redeem 直到 evidence-based 紀律驗證。

---

## 1. TL;DR / 用途

Bybit Earn（v5.6 → v5.7 reviewer correction #2/#5/#6）是 v5.7 §1 honest Y1 income 唯一被算入的「真實 income」項目（tiered APR ~$26/yr，非 macro / on-chain）。v5.7 §4 + ADR-0031 + ADR-0032 把 Earn 從「靜態 cash management」升級為「**慢資產移動治理**」：

- **Dynamic APR tracking**（per ADR-0031 §1.1）— 每次 stake/redeem 前查 Bybit API；不可用 cached static APR
- **5-Gate Adapter**（per ADR-0032）— Earn stake/redeem 對齊既有 Five-Gate（authorization / risk envelope / Decision Lease retrofit / API call / audit log）
- **Decision Lease retrofit**（per ADR-0032 Gate 3）— stake intent emit lease（lease ID format `lease_earn_<product>_<direction>_<ts>`；TTL min-hr 級；新增 `unstake_pending` state）
- **Audit log**（per ADR-0032 Gate 5）— `learning.earn_movement_log` 完整紀錄 stake/redeem direction + amount + APR snapshot + governance approval

本 runbook 規範 4 類事件：(a) **5-Gate Adapter 觸發場景**（per ADR-0032 各 gate 各自處置）/ (b) **Earn deposit / withdraw operator approval flow**（manual rebalance first 3 months）/ (c) **APY 異常處置**（dynamic APR drift / Bybit Earn product 變動） / (d) **跨 venue 帳本 reconciliation**（Bybit Earn 與 trading wallet）。

> **D1c 紀律提醒**：production secret slot **無 withdrawal API key**；Earn stake / redeem 不需 withdrawal 權；如真需要 withdraw asset 到外部 → 走 Operator manual 走 Bybit GUI + 補 audit log，**不**透過本系統自動化路徑（per CLAUDE.md §四 D1c）。

---

## 2. Detection / Alarm Symptoms

| Symptom | 來源 | 對應 section |
|---|---|---|
| Console 顯示 stake / redeem intent pending Operator approve | `learning.decision_lease_audit` lease_id 含 `lease_earn_*` | §6 manual approval flow |
| Slack 收到 `[EARN] stake intent <product>` notification | Earn API recorder + Slack | §6 + §4 triage |
| `learning.earn_apr_log` APR snapshot 突然 jump（drift > 50%） | per stake event APR snapshot 對比 | §7 APY 異常 |
| Trading wallet margin headroom < 30% 警告 | risk envelope probe + Earn Gate 2 | §5 Gate 2 + §8 reconciliation |
| Bybit Earn product 顯示 issuer 變更 / unstake period 變更 | Bybit Earn API metadata change | §7 APY 異常 + §6 Gate 2 |
| `learning.earn_movement_log` 與 Bybit Earn position 對不上 | reconciliation SQL | §8 |
| Y1 末 4-gate evaluation 期間 Earn evidence 缺漏 | per ADR-0030 evaluation | §9 escalation |

---

## 3. Severity Matrix

| Severity | Impact | Response time | Escalation path |
|---|---|---|---|
| **SEV-1** | 任一 5-Gate adapter 路徑被繞過（如 stake 寫 live 但無 Decision Lease record / 無 authorization check / 無 Guardian envelope check）；或 first 3 months 内出現 auto-redeem | < 5 min | Operator 立刻 stop Earn 路徑 → §9 escalate；PM 30 min 內加入；24h postmortem |
| **SEV-2** | Earn API recorder 故障（APR snapshot 無法 query） / `learning.earn_movement_log` 寫入失敗 / reconciliation 顯示 drift > $5 | < 30 min | On-call PM 走 §8 reconciliation；4h 內修；阻擋下一次 stake/redeem 直到修復 |
| **SEV-3** | APY drift > 30% 但仍在 Bybit announced range / 第三方 issuer 比例變化 / unstake period 延長 | < 4h | On-call PM 看 dashboard；登錄 12-week trend；Y1 末 4-gate 評估時 review |

---

## 4. Initial Triage Checklist（5-10 步）

```bash
# Step 1 — 列當前 pending stake/redeem intent
psql -h trade-core -U openclaw -d openclaw -c "
SELECT lease_id, status, payload->>'product' AS product,
       payload->>'direction' AS dir, payload->>'amount_usd' AS amt,
       created_at, ttl_expires_at
FROM learning.decision_lease_audit
WHERE lease_id LIKE 'lease_earn_%'
  AND status IN ('pending_operator', 'pending_guardian', 'unstake_pending')
ORDER BY created_at DESC LIMIT 20;"
# decision branch:
#   status='pending_operator' → §6 manual approval
#   status='unstake_pending' 且超 product unstake_period → SEV-2（unstake 卡住）
```

```bash
# Step 2 — 確認 5-Gate adapter 各 gate 健康
curl -sS http://localhost:8001/api/v1/earn/gate_status | jq
# expected:
#   .gate1_authorization: 'green'（authorization.json 有效 + Operator role）
#   .gate2_risk_envelope: 'green'（margin headroom OK + total asset cap OK）
#   .gate3_decision_lease: 'green'（lease state machine 正常）
#   .gate4_api: 'green'（Bybit Earn API reachable）
#   .gate5_audit_log: 'green'（earn_movement_log writer alive）
# decision branch:
#   任一 gate red → 對應 §5 處置
```

```bash
# Step 3 — Earn position vs trading wallet margin reconciliation
psql -h trade-core -U openclaw -d openclaw -c "
SELECT product, total_staked_usd, last_snapshot_apr,
       (SELECT trading_margin_headroom_pct FROM trading.account_health
        WHERE recorded_at = (SELECT MAX(recorded_at) FROM trading.account_health)) AS headroom
FROM learning.earn_position_snapshot
WHERE recorded_at > NOW() - INTERVAL '1 hour'
ORDER BY recorded_at DESC LIMIT 10;"
# decision branch:
#   headroom < 30% → SEV-2 + Gate 2 應拒絕新 stake；驗 §5 Gate 2
#   total_staked_usd / account_total > 80% → SEV-2 + §6 review
```

```bash
# Step 4 — APR drift check
psql -h trade-core -U openclaw -d openclaw -c "
SELECT product, snapshot_at, apr,
       LAG(apr) OVER (PARTITION BY product ORDER BY snapshot_at) AS prev_apr,
       (apr - LAG(apr) OVER (PARTITION BY product ORDER BY snapshot_at)) /
         NULLIF(LAG(apr) OVER (PARTITION BY product ORDER BY snapshot_at), 0) AS pct_change
FROM learning.earn_apr_log
WHERE snapshot_at > NOW() - INTERVAL '7 days'
ORDER BY product, snapshot_at DESC LIMIT 50;"
# decision branch:
#   pct_change > 0.5 或 < -0.5 → §7 APY 異常 SEV-3
```

```bash
# Step 5 — First 3 months manual rebalance 紀律驗
psql -h trade-core -U openclaw -d openclaw -c "
SELECT lease_id, payload->>'actor' AS actor, payload->>'auto_executed' AS auto
FROM learning.earn_movement_log
WHERE event_type IN ('stake', 'redeem')
  AND created_at > (SELECT MIN(deployed_at) FROM system.deployment_history) + INTERVAL '90 days' * 0  -- v5.7 §8 Sprint 1A first 3mo
ORDER BY created_at DESC LIMIT 50;"
# expected: actor = '<operator_id>'；auto = 'false'
# 如 auto = 'true' 在 first 3mo 內 → SEV-1 紀律違反
```

```bash
# Step 6 — Bybit Earn API 連線 + retCode
psql -h trade-core -U openclaw -d openclaw -c "
SELECT endpoint, retcode, retry_count, created_at
FROM learning.bybit_earn_api_audit
WHERE created_at > NOW() - INTERVAL '24 hours'
  AND retcode != 0
ORDER BY id DESC LIMIT 20;"
# decision branch:
#   個別 retcode 5xx → SEV-2；可能 Gate 4 timeout
#   全 endpoint 0 row → API 完全不通；§5 Gate 4
```

```bash
# Step 7 — Reconciliation drift（per §8）
psql -h trade-core -U openclaw -d openclaw -c "
WITH local AS (
  SELECT product, SUM(amount_usd) FILTER (WHERE event_type='stake')
       - SUM(amount_usd) FILTER (WHERE event_type='redeem') AS local_net_usd
  FROM learning.earn_movement_log
  GROUP BY product
),
bybit AS (
  SELECT product, last_known_balance_usd FROM learning.earn_position_snapshot
  WHERE recorded_at = (SELECT MAX(recorded_at) FROM learning.earn_position_snapshot)
)
SELECT b.product, local.local_net_usd, b.last_known_balance_usd,
       ABS(local.local_net_usd - b.last_known_balance_usd) AS drift_usd
FROM bybit b LEFT JOIN local USING (product)
ORDER BY drift_usd DESC NULLS LAST;"
# decision branch:
#   drift_usd > $5 → SEV-2 §8 reconciliation
```

```bash
# Step 8 —（only if SEV-1）emergency disable Earn 路徑
curl -sS -X POST -H "Cookie: $OPERATOR_SESSION_COOKIE" \
  -d '{"earn_enabled":false, "reason":"<rca>"}' \
  http://localhost:8001/api/v1/earn/config
# 預期 effect：所有 pending lease 進入 force_cancel；不接受新 stake/redeem
# unstake_pending lease 不受影響（exchange 端已 commit 到 unstake period）
# §9 escalate；24h postmortem 必補
```

---

## 5. 5-Gate Adapter 各 Gate 觸發場景處置（per ADR-0032）

### Gate 1 — Authorization Gate（任一條 fail → reject + log）

**Trigger**：Python `live_reserved` / Operator role / `OPENCLAW_ALLOW_MAINNET=1` / valid secret slot / signed `authorization.json` 任一 fail。

**Mitigation**：
- 與 trading authorization 同一路徑；走既有 `live_trust_routes::renew()` 補 authorization
- 不接受手寫 `authorization.json`（CLAUDE.md §四）
- D1c 紀律：production secret slot **無 withdrawal API key**；Earn stake/redeem 路徑只用 Earn product permission scope

### Gate 2 — Risk Envelope Gate（Guardian envelope）

**4 sub-criterion**（per ADR-0032）：
- Stake 後 trading margin headroom ≥ 30%
- Stake amount / 主帳 total assets ≤ 80%
- Earn product unstake period < 下個策略 promotion 預期時間
- Bybit Earn product issuer 為 Bybit 自營 = PASS；第三方 = 需 Operator manual approve

**Mitigation**：
- 任一 fail → Guardian block + log `learning.guardian_block_log` with `block_reason=earn_*`
- 第三方 issuer 場景 → Console banner 必顯示 "Third-party issuer; manual approval required"

### Gate 3 — Decision Lease Gate（retrofit per ADR-0032）

**Lease 結構**：
- Lease ID format: `lease_earn_<product>_<direction>_<ts>`（vs trading `lease_<strategy>_<symbol>_<ts>`）
- TTL: min-hr 級（vs trading ms-sec）
- State: 既有 `open/matched/submitted/cancelled` + 新增 `unstake_pending`

**Mitigation**：
- `unstake_pending` 內 lease **不可 cancel**（已 staked，等 unstake period 結束）；違反 → SEV-1
- 如 lease state machine regression → 走 ADR-0008 runbook（本 runbook scope 外）

### Gate 4 — Execute Gate（Bybit Earn API call）

**Trigger**：API timeout / partial fill / non-2xx return。

**Mitigation**：
- Timeout → fail-closed（per CLAUDE.md §四 既有 Bybit API timeout 紀律）；不暗自 retry
- Partial fill → log + Operator manual review；Bybit Earn 通常 atomic，partial = 例外
- Stake_id / unstake_id 寫進 `learning.earn_movement_log`

### Gate 5 — Audit Log Gate（post-execute）

**Trigger**：`learning.earn_movement_log` 寫入失敗。

**Mitigation**：
- writer 失敗 → SEV-2；任何 stake/redeem 完成但 audit 缺失 = audit chain 斷裂
- Recovery：手補 row（per next stake event Bybit API 返回的 stake_id / unstake_id 對應）+ 補簽 `actor` + `governance_approval`

---

## 6. Earn Deposit / Withdraw Operator Approval Flow（first 3 months manual）

```
1. Strategist / Allocator / Operator 提出 stake/redeem intent (per ADR-0032 Gate 3 lease emit)
2. Console 顯示 banner；Slack notification 發到 #ops-earn channel
3. Operator 開啟 Console → Earn tab → 找到該 lease_id
4. Console 顯示 5-Gate Adapter 狀態：
   Gate 1 authorization: green
   Gate 2 risk envelope: green (含 4 sub-criterion 各自結果)
   Gate 3 lease: green (TTL countdown)
   Gate 4 API: ready
   Gate 5 audit: ready
5. Operator 必填 approval form（3 條）：
   (a) 「我已確認 Earn product issuer + APR snapshot」
   (b) 「我接受 unstake_period 內 asset 鎖定」
   (c) 「我理解 first 3 months 為 manual rebalance 紀律，本次非 auto」
6. 2FA confirm
7. Console 點 "Approve" → lease state → submitted；Bybit Earn API call
8. API return → Gate 5 writes `learning.earn_movement_log` with full attestation
9. Console 顯示 "Stake/Redeem executed; Earn position updated; unstake_pending until <date>"
```

**Hands off — operator only**：上 9 步全部走 Console UI；CLI / IPC 路徑僅 emergency。

**Withdraw（外部）**：D1c 紀律 — production secret slot 無 withdrawal API key；如需 withdraw → Operator 走 Bybit GUI manual + 補本系統 audit log（手動 INSERT `learning.earn_movement_log` row with `event_type='external_withdraw_manual'`）。

---

## 7. APY 異常處置

**Trigger 場景**：
1. APR snapshot drift > 30%（per §4 Step 4 query）
2. Bybit Earn product issuer 變更（Bybit 自營 → 第三方 issuer）
3. Unstake period 延長（如從 7d → 14d）

### 7.1 Drift > 30%（dynamic APR 政策觸發）

**Mitigation**：
- 第一時間查 Bybit Earn announcement page；如 Bybit 主動調 APR → 正常變化（SEV-3 紀錄即可）
- 如 Bybit 未發 announcement 但 API APR 變化 → 走 Bybit support；SEV-2；暫停下次 stake 直到澄清
- `learning.earn_apr_log` 加 `drift_alert=true` flag；月度報告含 APR drift event 列表

### 7.2 Issuer 變更（Bybit 自營 → 第三方）

**Mitigation**（per ADR-0032 Gate 2 sub-criterion 4）：
- Next stake intent 自動進入 Gate 2 fail 路徑（issuer mismatch）→ Operator manual approve 必須
- Console banner 必標明「Issuer changed: <old> → <new>; manual review required」
- Operator 評估 issuer trust：(a) Bybit 自營 keep；(b) 第三方 = case-by-case approve；(c) 拒絕 → manual redeem 全部 stake

### 7.3 Unstake period 延長

**Mitigation**（per ADR-0032 Gate 2 sub-criterion 3）：
- Next stake intent 觸發 Gate 2 check「unstake period < 下個策略 promotion 預期時間」
- 如新 unstake period 超過 promotion calendar → Gate 2 fail → Operator manual review
- Operator 可選 (a) 縮 stake amount; (b) 改用其他 product; (c) 接受延長 unstake period + 重排策略 promotion

---

## 8. 跨 Venue 帳本 Reconciliation

**目標**：local `learning.earn_movement_log` 累計 net stake 必對得上 Bybit Earn position snapshot；drift > $5 = SEV-2。

```bash
# Reconciliation step 1 — 拉 Bybit Earn position snapshot
ssh trade-core "python3 helper_scripts/operator/earn_position_snapshot.py --refresh-now"
# 寫入 learning.earn_position_snapshot 一筆新 row
```

```bash
# Reconciliation step 2 — 對齊 local vs Bybit
psql -h trade-core -U openclaw -d openclaw -c "
-- 同 §4 Step 7 query
"
# decision branch:
#   drift_usd > $5 → §8 reconciliation 必修
```

```bash
# Reconciliation step 3 — 補 drift root cause
# 可能 root cause:
#   (a) 第三方 issuer 變 APR + interest 累計入 position 但 local log 沒記
#   (b) Bybit 端 product 過期自動 redeem 但 local 沒收 webhook
#   (c) Manual external withdraw 未補 audit log (per §6 withdraw 段)
# 對應 root cause 補 row 或調整 reconciliation 邏輯
```

**Mitigation**：
- Drift > $5 → 暫停下次 stake/redeem 直到對齊
- 補 audit row 後 reconciliation drift 應降為 0；再 enable Earn 路徑
- 連續 3 次 drift > $5 → SEV-1；§9 escalate；ADR-0032 audit log 設計 review

---

## 9. Escalation

**Trigger**：§4 任一 Step 顯示 SEV-1；§5 任一 Gate 規則繞過；§6 first 3 months 內出現 auto-stake/redeem；§8 reconciliation 連續 3 次 drift。

**Escalation channel**：
- SEV-1：Slack `#ops-critical` + 電話 PM + email Operator + FA（Y1 income 評估）@here
- SEV-2：Slack `#ops-earn` + email PM
- SEV-3：Slack `#ops-info`

**Attach evidence**：
- `learning.decision_lease_audit` 對應 lease_earn_* row 7d 全 export
- `learning.earn_movement_log` 7d 全 export
- `learning.earn_apr_log` 對應 product 30d snapshot
- `learning.earn_position_snapshot` 7d snapshot
- `learning.guardian_block_log` block_reason='earn_*' 7d
- Bybit Earn announcement screenshot（如 §7 trigger）
- engine.log 最近 24h `earn_*` grep

**Post-escalation action**：
- PM 30 min 內派 FA review Y1 income $26 影響評估 + ADR-0030 Y1 末 4-gate evidence prep
- 24h 內補 postmortem `docs/audits/<date>--earn_<incident>_postmortem.md`
- 如 §6 紀律違反 → ADR-0032 amendment + manual rebalance 紀律強化

---

## 10. Post-Incident

### Postmortem template

```markdown
# Earn Governance Incident Postmortem — <YYYY-MM-DD>

## TL;DR
- Event type: <stake / redeem / APR drift / issuer change / reconciliation>
- Severity: SEV-?
- Product(s) affected: <list>
- Amount(s): <$USD>
- 5-Gate fail point (if any): <Gate 1-5>
- Operator action(s): <list>
- Y1 income impact: <$ delta>

## Timeline (UTC)
- T+0: <symptom or stake intent>
- T+N: <step>

## Root cause
- 5-Gate adapter 紀律是否被尊重？
- ADR-0032 哪個 Decision 缺失或不足？
- Bybit-side 變化還是 internal regression？

## Mitigation
- 即時 mitigation (§5/§7/§8 對應)
- 永久 mitigation（ADR-0032 amendment / Console UI 修 / audit log schema 補）

## Action items
- [ ] ADR-0032 amendment 對應 finding
- [ ] `learning.earn_movement_log` schema 補 column
- [ ] runbook §X 更新
- [ ] Y1 末 4-gate evidence prep 補

## 12-week trend
- 加入 monthly Earn trend dashboard tracking entry（link）
```

### 12-week trend tracking entry

每月 PM Monthly Operator Review Wizard 含 Earn section：
- 4 週 / 12 週 stake / redeem count + 累計 net amount
- APR drift event count + average drift magnitude
- Reconciliation drift count + max drift
- 5-Gate adapter 各 gate fail count
- Y1 末 ADR-0030 4-gate evidence 預估（Alpha / Governance / Infra / Regulatory）

Dashboard：`http://localhost:8001/console#income/earn` → "12w trend" tab（pending Sprint 1A-ε A3 land）。

---

## 11. Cross-References

- **ADR-0030**：`docs/adr/0030-copy-trading-evidence-gated.md`（Y1 末 4-gate framework；Earn evidence 是 governance gate input）
- **ADR-0031**：`docs/adr/0031-framework-expansion-earn-macro-onchain.md`（Earn / Macro / On-chain framework 父；§1.1 dynamic APR 設計意圖；§1.2 Earn movement governance overview）
- **ADR-0032**：`docs/adr/0032-bybit-earn-asset-movement-guardian.md`（5-gate adapter + Decision Lease retrofit + audit log；本 runbook 主要 reference）
- **v5.7 §4**：`docs/execution_plan/2026-05-15--execution-plan-v5.7.md` Bybit Earn dynamic APR + governance 段
- **v5.7 §8 Sprint 1A**：同上 — Earn API recorder + Earn governance policy land
- **CLAUDE.md §四 D1c**：no withdrawal API key 紀律
- **CLAUDE.md §四 D1d**：Earn governance per ADR-0030/0031/0032
- **既有 LG-2 pricing runbook（風格參考）**：`docs/runbooks/2026-05-11--lg2_pricing_assertion_failure.md`
- **既有 H0 runbook（風格參考）**：`docs/runbooks/2026-05-11--lg1_h0_flip_rollback.md`
- **Counterfactual quality report runbook**：`docs/runbooks/2026-05-21--counterfactual_quality_report_runbook.md`（月報生成 SOP；Earn evidence 是 input）
- **Metric dashboard**：`http://localhost:8001/console#income/earn`（pending）
- **Healthcheck integration**：`helper_scripts/db/passive_wait_healthcheck.py --check earn_reconciliation` + `--check earn_apr_snapshot_fresh`（pending）

---

## 12. Version History

| 版次 | 日期 | 修訂者 | 摘要 |
|---|---|---|---|
| **v0.1** | 2026-05-21 | TW | Sprint 1A-β deliverable draft；5-Gate Adapter 各 gate 處置 + manual approval flow (first 3 months) + APY 異常 3 trigger + reconciliation drift > $5 SOP + ADR-0030/0031/0032 cross-ref |

---

*OpenClaw / Arcane Equilibrium Runbook — Bybit Earn governance operator 介入 SOP (Draft — ADR-0030/0031/0032 land 後 v1 promote)*
