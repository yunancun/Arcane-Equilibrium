# N+0 Sign-off + N+1 Dispatch Fire SOP

**Date**: 2026-05-10
**Trigger**: 21:30 UTC HIGH-5 12h watch confirm window
**Owner**: PM
**Predecessors**: HEAD `4bb5d485` (dispatch v3.4 + 4 sub-agent reports + W7 PR ready)

---

## §1 Pre-fire 檢查清單（21:30 UTC PM 確認）

### §1.1 N+0 sign-off pre-flight
- [ ] HIGH-5 12h watch 3 metric 驗：
  - [ ] **metric 1 chain integrity**：MIT 已提早 sign-off（chain pre+post V083 100%）
  - [ ] **metric 2 [40] avg_net** ≥ 5 bps（forward trajectory）
    - 跑 healthcheck `[40] realized_edge_acceptance` 看 24h MLDE 結果
    - 對比 baseline +8.75 bps（restart 09:23 UTC）— 維持 ≥ 5 bps 即 PASS
    - 如 < 5 bps → 不 sign-off，看 cause（可能 cron 觸發新影響）
  - [ ] **metric 3 TONUSDT cell** isolate（不擴散到 BTCUSDT/ETHUSDT/SOLUSDT 等）
    - SQL: `SELECT symbol, AVG(net_edge_bps proxy) FROM trading.fills WHERE strategy='grid' AND ts > NOW() - INTERVAL '12 hours' GROUP BY symbol`
- [ ] sign-off report 寫入 `srv/docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-10--n0_high5_signoff.md`

### §1.2 N+1 deploy 前置檢查
- [ ] commit chain HEAD 確認（main + Linux 同步）
- [ ] W7-3 commit `b42731f6` 仍 PR ready（NOT DEPLOYED）
- [ ] W7-1 + W2 trait skeleton commit `c9fb0b8f` 仍 PR ready（NOT DEPLOYED）
- [ ] dispatch v3.4 + 4 sub-agent reports 全 land (HEAD `4bb5d485`)
- [ ] git status clean（無 uncommitted）

### §1.3 Operator 拍板確認
- [ ] 5 ambiguous mapping (A1-A5) 已 PA W6-3b 拍板（全 ACCEPT MIT）— operator 確認 OK 進 V086 IMPL
- [ ] BB W1 WS-first push back 採納（W1 IMPL 走 WS-first not REST polling）
- [ ] W7-3 Option B 補丁 deploy（per W7-3 deploy SOP）

---

## §2 Deploy 步驟（21:30 UTC + 5 min, 一次 restart 含 W7-3 + W7-1 + W2 trait）

### §2.1 Linux trade-core deploy
```bash
ssh trade-core "cd ~/BybitOpenClaw/srv && \
  git pull --ff-only origin main && \
  bash helper_scripts/restart_all.sh --rebuild --keep-auth 2>&1 | tail -30"
```

**預期**：~3-5 min downtime（Rust release rebuild + engine restart + Python venv reload）

### §2.2 Post-restart 5 min 驗證
```bash
ssh trade-core "PG_PASS=\$(awk -F= '/^POSTGRES_PASSWORD=/{print \$2}' /home/ncyu/BybitOpenClaw/secrets/environment_files/basic_system_services.env) && \
  echo '=== engine alive ===' && pgrep -af openclaw_engine | head -1 && \
  echo '=== ma_crossover INXUSDT reject 5min ===' && \
  PGPASSWORD=\$PG_PASS psql -h 127.0.0.1 -U trading_admin -d trading_ai -c \
  \"SELECT COUNT(*) reject_5min FROM trading.risk_verdicts WHERE ts > NOW() - INTERVAL '5 minutes' AND reason ILIKE '%duplicate_position%INXUSDT%';\" && \
  echo '=== [55] healthcheck chains_with_lease ===' && \
  PGPASSWORD=\$PG_PASS psql -h 127.0.0.1 -U trading_admin -d trading_ai -c \
  \"SELECT chains, chains_with_lease, chains_with_report, bad_report_quality FROM agent_decision_spine_lineage WHERE ts > NOW() - INTERVAL '5 minutes' ORDER BY ts DESC LIMIT 1;\""
```

**驗收**:
- engine alive (PID found)
- ma_crossover INXUSDT reject < 5/5min（W7-3 fix 生效；從 baseline 666/min 降）
- chains_with_lease > 0（W7-1 + W7-3 deploy 後 lease lifecycle normal）

### §2.3 Rollback Plan（任一驗收 FAIL）
```bash
# Mac 端
cd /Users/ncyu/Projects/TradeBot/srv && \
  git revert b42731f6 c9fb0b8f --no-edit && \
  git push origin main

# Linux 端
ssh trade-core "cd ~/BybitOpenClaw/srv && git pull --ff-only origin main && \
  bash helper_scripts/restart_all.sh --rebuild --keep-auth 2>&1 | tail -10"
```

---

## §3 Sprint N+1 Dispatch Fire（21:30 UTC + 30 min, deploy 驗收 PASS 後）

### §3.1 派發順序（per dispatch v3.4 §4 Schedule D+1）

**並行 sub-agent dispatch list**:

1. **W7-2 ma_crossover entry path fix**（E1, 0.5 day）
   - 用 ctx.position_state query before entry
   - ~10 LOC + 1 unit test

2. **W6 三角 RFC**（PA + QC + MIT 並行, 1 day, baseline + 3 視角預備立場已備）
   - 直接走 sign-off 流程：PA + QC + MIT 各自 verify 預備立場 + final RFC verdict
   - 可能 W6-3b A1-A5 final acceptance + W6-1 verdict 明文化 + W6-3 sub-task scope confirm

3. **W2 A4-C IMPL chain**（5 sub-agent, 5-7 day）
   - C-IMPL-1 NO-OP（trait c9fb0b8f land 已驗收）
   - C-IMPL-2 lead-lag producer + V088 panel migration（E1, 2 day）
   - C-IMPL-3 strategy paper-only 接收（E1, 1 day）
   - C-IMPL-4 paper engine 7d evidence collection（D+5 起, paper engine running）

4. **W1 IMPL chain**（3 sub-agent + WS-first revision per BB push back, 5-7 day）
   - PA + BB final WS-first integration（0.5 day）
   - E1-α funding_curve writer + V085（WS-first, 3 day）
   - E1-β oi_delta_panel writer + V087（WS-first, 3 day）
   - E1-γ NO-OP（trait c9fb0b8f land 已驗收）

5. **W4 W-AUDIT-3b runtime smoke**（E4, 1 day）
   - pytest test_executor_fail_closed
   - runtime smoke script

6. **W5 9 P1/P2 並行**（per dispatch v3.4 §3.5）
   - PA spec + E1 IMPL 分散到 D+1-7
   - 移除 P2-DECISION-FEATURES-DOUBLE-PREFIX-BUG-1（per PA P2 RCA, 4-23 已 fix）

### §3.2 W3 Stage 1 cohort 暫不派
- 等 W6 verdict + W7 完成 (~D+3-4)

---

## §4 Memory + Commit Persist

### §4.1 Sprint N+0 closure memory update
- update `srv/memory/project_2026_05_10_sprint_n0_closure.md`：
  - 補正「attribution_chain_ok 0.5%→100%」描述為 mock baseline 誤讀
  - 補新「真正 bottleneck = governance reject 99.5% reframe」（W6-3 18+ enum + Track A/B 拆 retrain）
  - 補新「9→10 fill 計數修正」
- update `srv/memory/MEMORY.md` index 加 Sprint N+1 dispatch v3.4 + W7-3 + W7-1 entry

### §4.2 N+1 dispatch fire commit
- commit message：`Sprint N+1 dispatch fire: deploy W7-3 + W7-1 + W2 trait + 派 W7-2/W7-4/W7-5/W6/W1/W2/W4/W5`
- push origin + Linux 同步

---

## §5 Risk + Watch Post-deploy 24h

### §5.1 Watch 觀察項
- ma_crossover INXUSDT reject 24h < 240（從 baseline 666/h × 24 = 16k 降）
- chains_with_lease 持續 > 0
- bad_report_quality = 0
- 5 策略 fire pattern：grid 持續 / ma_crossover 預期回升（fix 後不被 hot loop block）/ bb_breakout 等 W1 Phase B / bb_reversion + funding_arb dormant
- W1 IMPL 過程不影響 5 策略 demo edge baseline
- W2 paper IMPL 不污染 demo edge baseline（三層 paper-only fence）

### §5.2 W3 Stage 1 cohort 觸發條件
- W6 verdict APPROVE + W7 sign-off + W1 land + 24h cooling = D+3-4 啟動
- per AMD-2026-05-10-04 atomic patch SOP

---

**End of SOP**. PM 21:30 UTC 用此 SOP 走 sign-off + dispatch fire 流程。
