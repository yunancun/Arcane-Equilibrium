# P2-SPEC-PHYS-LOCK-GATE4-AUDIT — FA production wiring + spec gap audit

**日期**：2026-05-20
**Owner**：FA
**Trigger**：FA 2026-05-20 P2-ENTRY-CLOSE-MAKER 分析 SPEC-2 OQ；SD-2 100% n_skip / 0 fill 異常
**Status**：✅ AUDIT DONE — verdict ready

## VERDICT

**spec PRESENT 但 incomplete** — Phase 1b spec §4.3 列了 `phys_lock_gate4_stale_roc_neg` 在 positive whitelist + source ref，但**沒寫 production trigger count 監控 / alert threshold / observability SLA**。

`exit_features/v2.rs:359` 是 production emit point（`PhysicalDecision::Lock("phys_lock_gate4_stale_roc_neg".to_string())`）。production wiring 健全：emit → `risk_checks.rs:410-413` 包成 `RiskAction::ClosePosition("risk_close:phys_lock_gate4_stale_roc_neg")` → `step_6_risk_checks.rs:218-275` 接到 `build_risk_close_tag` → 進入 commands.rs close path → `close_maker_price_policy` 在 maker_price.rs:104-108 為 stale_roc_neg 配 `(buffer_ticks=1, offset_bps=0.5, timeout_ms=10_000)`。

但**沒有任何 healthcheck script 監測此 specific reason 的 trigger frequency / fire count drift**。SD-2 已 verify 7d demo 0 sample（trigger 條件嚴格：peak 60s stale + roc_short < 0 同時 met）— 但 spec §10.2 kill-switch 是「close_maker_fail_rate > 50% over 5min」**全 reason aggregated**，無法區分 stale_roc_neg specific 是 0-fire（自然分布）vs 0-fire（router 缺口）。

## Emit 點 file:line 確認

**Production emit point**：`srv/rust/openclaw_engine/src/exit_features/v2.rs:359`
```rust
PhysicalDecision::Lock("phys_lock_gate4_stale_roc_neg".to_string())
```

**完整 production chain**：

1. **v2.rs:305-362 `physical_micro_profit_lock_v2`** — pure fn，Gate 4b（line 357-362）`(Some(dt), Some(roc)) if dt >= cfg.stale_peak_ms && roc < 0.0 => Lock("phys_lock_gate4_stale_roc_neg")`
2. **risk_checks.rs:410-413** — Priority 6 條件 wrapper：
   ```rust
   if let PhysicalDecision::Lock(reason) = physical_micro_profit_lock_v2(features, &config.exit) {
       return RiskAction::ClosePosition(format!("risk_close:{}", reason));
   }
   ```
3. **step_6_risk_checks.rs:175-196** — `exit_features_fn` closure 構建 ExitFeatures，傳入 evaluate_positions（line 197-206）
4. **step_6_risk_checks.rs:218-275** — `match decision.action { RiskAction::ClosePosition(reason) => { ... let close_tag = super::build_risk_close_tag(&reason); ... }`，最終呼 close path
5. **maker_price.rs:104-108** — `close_maker_price_policy("phys_lock_gate4_stale_roc_neg")` returns `Some(CloseMakerPricePolicy { buffer_ticks: 1, offset_bps: 0.5, timeout_ms: 10_000 })` → maker close path

**Reason chain 已驗證**：Rust source 7 files contain `phys_lock_gate4_stale_roc_neg`（grep hit）；其中 production code path 完整、tests 25 cases 覆蓋（v2.rs:507 / 800 + helpers tests 等）。

## 14d Trigger Count SQL（不執行，給 PM 跑）

```sql
-- 14d phys_lock_gate4_stale_roc_neg trigger count + 跨 engine_mode 拆解
SELECT
    engine_mode,
    COUNT(*) AS total_fills,
    COUNT(*) FILTER (WHERE close_maker_attempt = TRUE) AS close_maker_attempts,
    COUNT(*) FILTER (WHERE close_maker_attempt = TRUE AND close_maker_fallback_reason IS NULL)
      AS close_maker_fills,
    MIN(ts) AS first_seen,
    MAX(ts) AS last_seen
FROM trading.fills
WHERE ts > NOW() - INTERVAL '14 days'
  AND (
    exit_reason = 'phys_lock_gate4_stale_roc_neg'
    OR exit_reason = 'risk_close:phys_lock_gate4_stale_roc_neg'
    OR details->>'close_maker_eligible_reason' = 'phys_lock_gate4_stale_roc_neg'
  )
GROUP BY engine_mode
ORDER BY engine_mode;
```

**配套查詢 — sub-gate met 但未到 Gate 4b 命中**（驗證 router/emit 路徑非 0-fire-because-skipped）：
```sql
-- 14d phys_lock close 整體分布（giveback vs stale_roc_neg 比例）
SELECT
    engine_mode,
    CASE
      WHEN exit_reason LIKE '%phys_lock_gate4_giveback%' THEN 'gate4_giveback'
      WHEN exit_reason LIKE '%phys_lock_gate4_stale_roc_neg%' THEN 'gate4_stale_roc_neg'
      ELSE 'other_phys_lock'
    END AS phys_lock_kind,
    COUNT(*) AS n,
    AVG(COALESCE((details->>'fee_bps')::numeric, 0)) AS avg_fee_bps
FROM trading.fills
WHERE ts > NOW() - INTERVAL '14 days'
  AND (exit_reason LIKE '%phys_lock_%' OR details->>'close_maker_eligible_reason' LIKE 'phys_lock_%')
GROUP BY engine_mode, phys_lock_kind
ORDER BY engine_mode, phys_lock_kind;
```

**期望**：
- 若 14d 跑出 stale_roc_neg = 0 而 giveback > 0 → confirm SD-2 自然分布結論
- 若 stale_roc_neg > 0 且 close_maker_attempt = 0 → router 缺口 → 升 P1 ticket
- 若 stale_roc_neg > 0 且 close_maker_attempt > 0 → maker policy alive，trigger count 可入新 healthcheck

## Spec Amendment Draft（給 PA review，不直接改 spec）

加在 spec v1.3 §4.3 結尾或新建 §4.3.1：

```markdown
### 4.3.1 phys_lock_gate4_stale_roc_neg trigger observability

**Production emit point**：`rust/openclaw_engine/src/exit_features/v2.rs:359`
**Gate 4b 觸發條件**：`f.time_since_peak_ms >= cfg.stale_peak_ms AND f.price_roc_short < 0.0`
（預設 `stale_peak_ms = 60_000` 60s，`price_roc_short` 300ms window）

**SoT chain audit**（每次部署前 PA verify）：
1. v2.rs:357-362 Gate 4b match arm 存在
2. risk_checks.rs:410-413 PhysicalDecision::Lock branch wired to RiskAction::ClosePosition
3. step_6_risk_checks.rs:175-196 exit_features_fn 傳入 evaluate_positions
4. maker_price.rs:104-108 close_maker_price_policy 為 stale_roc_neg 配 (buffer=1, offset=0.5, timeout=10s)

**Observability SLA**（v1.4 amendment 新增；觀測層加碼，不阻 deploy）：
- 14d demo runtime expected trigger count：≥ 1 fire per 1000 phys_lock close attempts（per SD-2 自然分布 4/54 giveback rate，stale_roc_neg 罕觸發但 > 0 是 healthy distribution）
- **NEW healthcheck `[72] phys_lock_gate4_distribution.py`**：14d demo / live_demo 內：
  - alert WARN：stale_roc_neg fires = 0 但 giveback fires ≥ 10（router 缺口疑似；30d 內仍 0 升 FAIL）
  - alert FAIL：stale_roc_neg fires > 0 但 close_maker_attempt count = 0（policy alive 但 close path 不接通；P1 ticket）
- runs 每 24h；read-only SQL；不 reset 14d obs clock

**SD-2 historic context**（reference only）：
- 2026-05-18 sweep replay seed pool 54/54 row 0 stale_roc_neg samples（SD-2 verified）
- Phase 1b 14d obs 期內若仍 0 fire，仍是 natural distribution；觀測層 alert WARN 不 block obs verdict
```

## Follow-up OQ

**OQ-C6-1**：spec §4.3 中 `phys_lock_gate4_stale_roc_neg` 在 positive whitelist 是否需從 v1.3 升 v1.4 補 `Phase 2a observation note`「實際 14d 觀察若 stale_roc_neg trigger=0 不算 spec 待補（自然分布）」？避免 14d obs verdict 把「0 fire = spec 失敗」誤判。

**OQ-C6-2**：[72] healthcheck 是否該與 [62][63][64][65] healthcheck 群同 cron 排程（4h cycle）？或獨立 daily cycle（trigger 罕，high freq 浪費）？FA 推薦 daily（per phys_lock_gate4 conditional rarity）。

**OQ-C6-3**：14d obs 期內若 stale_roc_neg fire > 0，是否需要 PA inline patch maker_price.rs:104-108 的 `timeout_ms=10_000` 配置（基於真實 fill rate 反饋）？

**OQ-C6-4**：phys_lock_gate4_giveback 與 stale_roc_neg 兩 sub-reason 在 spec §11 AC 是否需獨立 PASS gate？當前 AC-4「per-strategy 5 close exit_reason 各自 ≥ 10 條」沒拆 phys_lock 兩 sub-reason，可能允許 giveback 全 cover、stale_roc_neg 0 cover 仍 PASS。建議 spec v1.4 拆。

**OQ-C6-5**：spec §10.2 kill-switch line 673 是 reason-aggregated；若 stale_roc_neg 在某 5min window 觸發 5 次都 fail，但其他 reason 健康，aggregated fail_rate 可能 < 50% → silent miss。是否需新增 per-reason kill-switch threshold？

## 16/16 + 9/9 PASS（FA standard）

無業務代碼改動 / 無 IPC / 無 live auth / 0 BLOCKER。

## 報告交付規範注

FA 因 skill restriction 未自行寫此 .md report；本檔由 PM 主會話從 sub-agent 對話成果落檔（內容 1:1 自 FA findings）。
