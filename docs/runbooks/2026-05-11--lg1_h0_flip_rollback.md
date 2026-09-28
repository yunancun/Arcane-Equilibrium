# LG-1 H0 Hard-Block — Flip / Rollback / 監測 SOP 手冊

**狀態：** Active（Wave 2.2 LG1-T3 land）
**版本：** v1（2026-05-11）
**Owner：** Operator + PM
**契約上游：** [PA tech plan](../CCAgentWorkSpace/PA/workspace/reports/2026-05-11--lg_2_3_4_design_plan.md) §1 + [LG-2 H0 Blocking Verification RFC](../CCAgentWorkSpace/PA/workspace/reports/2026-05-01--lg2_h0_blocking_verification_rfc.md)
**並行兄弟 task：** LG1-T1（E2E integration test）/ LG1-T2（healthcheck `[59]` h0_block_acceptance）/ LG1-T4（operator verification route `/api/v1/risk/h0_block_summary`）
**Runtime smoke 上游：** [W-AUDIT-3b runtime smoke](../CCAgentWorkSpace/E4/workspace/reports/2026-05-11--w_audit_3b_runtime_smoke.md)

---

## 1. 用途 / Why this runbook exists

H0 Gate 是 `<1ms` 本地確定性合規層（freshness / health / eligibility / risk envelope / cooldown 5 個 sub-check），落在 tick pipeline 的 Step 0.5（`rust/openclaw_engine/src/tick_pipeline/on_tick/step_0_5_h0_gate.rs`）。每筆 tick 走完 H0 後才能進到策略 dispatch + intent 階段；H0 阻斷時只走 stops，不開新倉。

H0 有兩種模式：
- **Shadow（觀察）**：執行全部 5 sub-check，命中時記日誌，**仍回 `allowed=true`** 讓策略繼續跑。
- **Hard-block（硬阻斷）**：命中任一 sub-check 即 `ControlFlow::Break` 早退，**0 intent / 0 lease / 0 exchange dispatch**。

模式由 `H0GateConfig.shadow_mode` 控制，runtime 透過 `runtime.h0_shadow_mode` TOML 欄位或 IPC `patch_risk_config` 動態切換。

**本 runbook 規範三類事件：**
- **Flip**（從 shadow 切到 hard-block）
- **Rollback**（從 hard-block 回到 shadow）
- **誤觸 / 過度阻斷之事故處置**

H0 是 §五 [架構總覽] 中 5-Agent runtime 的 **第一道防線**；任何 flip / rollback 都必須能在 60 秒內完成且不重啟 engine。

---

## 2. 治理約束 / Governance Invariants

| Invariant | 來源 | 違反後果 |
|---|---|---|
| H0 是 hot path `<1ms` SLA | h0_gate.rs 行 269 + GateStats.max_latency_us | p99 latency > 1ms → 主路徑延遲漂移 |
| Hard-block 時必須走 stops only，**不**走 intent dispatch | step_0_5_h0_gate.rs:43-94 ControlFlow::Break | open-order leakage |
| H0 是 pre-lease；lease consumption 在 H0-blocked tick **必為 0** | RFC §Required Metrics | lease 被 H0-blocked intent 消耗 = SM-02 lifecycle 漏洞 |
| 切換 shadow_mode 必須寫審計日誌（SEC-02） | h0_gate.rs::set_shadow_mode | 遠程切換不可追溯 |
| Demo / Live TOML 預設 `h0_shadow_mode = false`（hard-block） | risk_config_demo.toml:171 / risk_config_live.toml:188 | demo / live 退回 shadow = 失 hard-block 保護 |
| Paper TOML 預設 `h0_shadow_mode = true`（shadow） | risk_config_paper.toml:187 | 2026-05-23 起 Paper runtime 長期 Archive；paper TOML 僅保留 diagnostic/replay lineage，不可作 observation/promotion path |
| ctor 預設 `shadow_mode = false`（LG1-T3 之後） | pipeline_ctor.rs:75–93 | 啟動瞬窗 fail-open；ctor 必為 fail-closed safety net |
| Flip / rollback 不需重啟 engine | RFC §Acceptance | 「需重啟才能 flip」= operator 體驗倒退 |
| Flip 後 24h 內必持續觀察 5 metric（latency / FP / leak / lease / fail-closed proof） | RFC §Required Metrics + healthcheck `[59]` | 沒觀察期 = 沒驗收依據 |

---

## 3. 預設配置矩陣 / Default config matrix

| Engine | TOML | ctor default（LG1-T3 後） | runtime SoT |
|---|---|---|---|
| Paper | `runtime.h0_shadow_mode = true`（shadow） | `false` | TOML / IPC patch（runtime IPC 為主） |
| Demo | `runtime.h0_shadow_mode = false`（hard-block） | `false` | TOML / IPC patch |
| LiveDemo | `runtime.h0_shadow_mode = false`（hard-block） | `false` | TOML / IPC patch |
| Live mainnet | `runtime.h0_shadow_mode = false`（hard-block） | `false` | TOML / IPC patch |

**關鍵說明**：
- **ctor default `false` 是 fail-closed safety net**：engine 啟動瞬間（首次 TOML 載入 / IPC 接管前）H0 直接 hard-block，不留 shadow 觀察窗。
- **TOML / IPC 是 SoT**：first tick 後 ctor default 被 runtime 值覆蓋（透過 `patch_risk_config` IPC path → `H0Gate::set_shadow_mode` → audit log）。
- **2026-09-28 source 修正（候選，尚未部署）**：`set_risk_store` 首次載入立即同步 H0；之後 ConfigStore 升版在下一個有效價格 tick 同步。缺 runtime section／缺欄位均預設 hard-block；明確的 `true` 才啟用 shadow。舊 IPC setter 亦先寫回同一 validated store，詳 §10。目標 runtime 是否採用須另驗。

---

## 4. Flip — shadow → hard-block

### 4.1 前置 / Preconditions

- [ ] 目標 engine（paper / demo / live_demo）當前 H0 mode 為 shadow
  ```bash
  curl -s http://localhost:8001/api/v1/risk/config | jq -r '.config.global_config.h0_shadow_mode'
  # expect: true
  ```
- [ ] Engine 健康：`engine_watchdog.py --status` 顯示 `engine_alive=true`，snapshot fresh
  ```bash
  ssh trade-core "python3 helper_scripts/canary/engine_watchdog.py --data-dir /tmp/openclaw --stale-threshold 45 --grace-period 120 --status"
  ```
- [ ] 5 metric baseline 已採集（latency / block rate / leak / lease / FP；shadow 期 baseline）
- [ ] 24h 觀察期排程已寫入 calendar；on-call 已知會

### 4.2 操作步驟

1. **發送 IPC patch**（operator 角色 auth）:
   ```bash
   # OPERATOR_SESSION_COOKIE 來源：GUI 登入後 DevTools → Application → Cookies → 取 `session=` 值；
   # 或 `curl -c cookies.txt -X POST -d 'username=...&password=...' http://localhost:8001/api/v1/auth/login` 拿 + export OPERATOR_SESSION_COOKIE=$(grep '^session' cookies.txt | awk '{print "session="$7}')
   curl -sS -X POST -H 'Content-Type: application/json' -H "Cookie: $OPERATOR_SESSION_COOKIE" -d '{"h0_shadow_mode": false}' http://localhost:8001/api/v1/risk/config/global
   ```
   - Route：`risk_routes.py::update_global_config`（行 222–243）
   - 內部：FastAPI → RiskViewClient → IPC `patch_risk_config{runtime.h0_shadow_mode: false}` → Rust `event_consumer/handlers/risk.rs::handle_patch_config` 行 313 `pipeline.h0_gate.set_shadow_mode(false)`
   - 寫入 V014 audit row（source=operator）+ SEC-02 audit log

2. **驗證 IPC 已生效**:
   ```bash
   curl -s http://localhost:8001/api/v1/risk/config | jq -r '.config.global_config.h0_shadow_mode'
   # expect: false
   ```

3. **驗證 5 metric baseline 維持 SLA**（首 5 分鐘）:
   ```bash
   # H0 latency + block counter
   curl -s http://localhost:8001/api/v1/risk/status | jq '.h0_gate_stats'
   # expect:
   #   .max_latency_us < 1000
   #   .total_checks ↑
   #   .blocked_* per sub-check 計數 ↑ when natural triggers fire
   ```

4. **24h 觀察期內持續監測 healthcheck `[59]`**（LG1-T2 land 後）:
   ```bash
   python3 helper_scripts/db/passive_wait_healthcheck.py --check h0_block_acceptance
   # expect: PASS（24h 內 0 confirmed false-block + 0 leak）
   ```

5. **24h 觀察期通過後 PM sign-off** → Flip 收口

### 4.3 TOML 永久持久化（可選，flip 通過 sign-off 後做）

IPC patch 是 runtime in-memory 切換；engine 重啟會丟。如要永久 flip，需改對應 TOML：

```bash
# 例：paper TOML flip 為 hard-block
sed -i.bak 's/^h0_shadow_mode = true$/h0_shadow_mode = false/' \
    settings/risk_control_rules/risk_config_paper.toml

# Commit + restart_all（permanent 持久化）
git add settings/risk_control_rules/risk_config_paper.toml
git commit -m "LG1-T3: paper engine flip H0 hard-block (24h obs PASS)"
bash helper_scripts/restart_all.sh
```

⚠️ Demo / Live TOML 已預設 `false`；只有 paper 翻 hard-block 才需動 TOML。

---

## 5. Rollback — hard-block → shadow

### 5.1 觸發條件 / Trigger

- 24h 觀察期內出現任一 metric FAIL（p99 latency > 3ms / 任一 confirmed false-block / 任一 confirmed open-order leak / 任一 lease consumed by H0-blocked intent）
- Healthcheck `[59]` 連續 3 cycle 報 FAIL
- Operator 手動判定（如 H0 sub-check 邏輯 regression 確認）

### 5.2 操作步驟（與 §4 對稱）

1. **發送反向 IPC patch**:
   ```bash
   curl -sS -X POST -H 'Content-Type: application/json' -H "Cookie: $OPERATOR_SESSION_COOKIE" -d '{"h0_shadow_mode": true}' http://localhost:8001/api/v1/risk/config/global
   ```

2. **驗證 IPC 已生效**：同 §4.2 step 2，expect `true`

3. **確認 hard-block 已停**（H0 BLOCKED 日誌不再出現）:
   ```bash
   ssh trade-core "tail -100 /tmp/openclaw/logs/engine.log | grep 'H0 BLOCKED'"
   # expect: 無新 entry（rollback 後）
   ```

4. **Audit row 確認**:
   ```sql
   SELECT created_at, source, payload->>'runtime' FROM learning.risk_config_audit
   ORDER BY id DESC LIMIT 5;
   -- expect: 最新 row source='operator' 帶 h0_shadow_mode=true
   ```

5. **PM root-cause 24h 內補 postmortem**（`docs/audits/<date>--h0_rollback_postmortem.md`），含：
   - 觸發 metric + 數值
   - H0 sub-check 命中 reason 抽樣
   - 是否為 H0 邏輯 bug / TOML 設值錯 / observation period 異常事件

---

## 6. 監測指標 / Monitoring metrics

### 6.1 五大 acceptance metric（RFC §Required Metrics）

| Metric | PASS Threshold | WARN | FAIL | 採集來源 |
|---|---:|---:|---:|---|
| H0 latency | p99 < 1ms over 24h | p99 1–3ms | p99 > 3ms | `GateStats.max_latency_us` via `/api/v1/risk/status`.h0_gate_stats |
| False-positive block rate | 0 confirmed false blocks over 24h replay | 1 disputed | >1 confirmed | healthcheck `[59]`（LG1-T2 land 後）+ canary_records 對照 |
| Fail-closed proof count | ≥3 synthetic blocked cases in tests PASS | missing 1 case | no E2E proof | LG1-T1 `h0_blocking.rs` integration test |
| Open-order leakage | 0 exchange dispatches after H0 block | any ambiguous audit row | any confirmed | canary_records join trading.fills |
| Lease consumption | 0 leases consumed by H0-blocked intents | any ambiguous lease row | any confirmed | learning.lease_transitions join canary_records |

### 6.2 持續 healthcheck

| Check | Cron | 預期 |
|---|---|---|
| `[59] h0_block_acceptance`（LG1-T2 land 後） | 5 min | PASS / WARN（24h sliding window） |
| `engine_watchdog.py --status` | 30 s | `engine_alive=true` + snapshot age < 45s |
| `[45] pricing_binding` | 5 min | PASS / WARN |

### 6.3 GUI surface（route ready；GUI integration TBD `[Phase B 後續]`）

- 新 route ✅ ready：`GET /api/v1/risk/h0_block_summary`（per RFC §T2 / PA §1.4 T4）— 21 unit tests + Linux PG 0.461ms / 24h scan
- ❗**13-tab console `risk` tab GUI card** ⏳ **Phase B 後續 wave**：route 已 ship，GUI 整合留後續（per A3 R2 audit, 避 operator 撲空）
- 當前驗證方式：直接 `curl -sS http://localhost:8001/api/v1/risk/h0_block_summary` 或經 `/api/v1/openapi.json` 看 schema
- 預計 GUI card 含內容（待 ship）：
  - 5 sub-check 各自 block count
  - Latest block reason by symbol（last 100）
  - 24h block rate trend

---

## 7. 失敗模式 / Failure modes

| Fail-mode | 觸發條件 | 操作員處置 |
|---|---|---|
| **Flip 後 latency p99 > 3ms** | hot path 引入新 sub-check 或 H0Gate clone 開銷 | Rollback（§5）+ 24h postmortem；PM 重排 hot path |
| **誤 block 全部 tick**（block rate ~100%） | health snapshot 卡死 / freshness 配置誤 / system_mode = read_only | Rollback（§5）+ 立查 `system_mode` + `health_snapshot_max_age_ms`；防範 = LG1-T1 unit test 預先 cover |
| **shadow 一直開不掉**（IPC patch 不生效） | event_consumer handler 失效 / IPC handler 沒接 `h0_shadow_mode` field | 檢查 IPC server log + restart engine（如 IPC race）；確認 risk_routes.py:120 + risk.rs:313 wire-in |
| **shadow_mode default vs TOML race**（啟動瞬窗）| 已由 LG1-T3 修：ctor default `false`（fail-closed）| **不會發生**；如真發生表示 LG1-T3 commit 被 revert，retest `test_lg1_t3_new_default_shadow_mode_is_false` |
| **Hot-reload 與設定不一致** | 舊 binary 未含 §10 source 修正，或尚未收到有效 tick | 核對 binary source／ConfigStore version／H0 snapshot；不要把 source 測試當 runtime 生效證據 |
| **Audit row 未寫入** | event_consumer audit writer 故障 / SEC-02 audit log 失效 | 立刻 `tail` engine.log + V014 risk_config_audit；確認 patch_risk_config 寫了 source='operator' + h0_shadow_mode 欄位 |

每個 fail-mode 都必寫 `learning.governance_audit_log` row（如健康）+ dashboard 顯示。

---

## 8. Operator 操作 checklist

### 8.1 Flip pre-flight checklist
- [ ] §4.1 全部前置滿足
- [ ] LG1-T1 `cargo test --lib --release -p openclaw_engine h0_blocking` PASS（fail-closed proof 已就位）
- [ ] LG1-T2 `[59] h0_block_acceptance` 已 register 在 cron
- [ ] LG1-T4 `/api/v1/risk/h0_block_summary` route 200 OK（可選，convenience）
- [ ] 24h calendar slot reserved
- [ ] PM + on-call 知會

### 8.2 Flip 執行 checklist
- [ ] §4.2 step 1 IPC patch 發出
- [ ] §4.2 step 2 GET /config 驗證 false
- [ ] §4.2 step 3 status latency < 1ms（首 5 min）
- [ ] 5 min 後 healthcheck `[59]` PASS
- [ ] 30 min 後 healthcheck `[59]` 仍 PASS
- [ ] 1h, 4h, 8h, 16h, 24h 各 checkpoint 通過
- [ ] 24h 完成 → PM sign-off + 收口

### 8.3 Rollback emergency checklist
- [ ] §5.2 step 1 反向 IPC patch 發出（不超過 60s 從決定到生效）
- [ ] H0 BLOCKED 日誌不再出現（grep 確認）
- [ ] Audit row 確認 source='operator' + h0_shadow_mode=true
- [ ] PM 24h 內補 postmortem

---

## 9. Rollback Procedure（更廣義 — engine 啟動失敗）

如 IPC patch 後 engine 失敗 / shutdown：

1. **Stop engines**:
   ```bash
   bash helper_scripts/stop_all.sh
   ```
2. **檢查 TOML 是否誤改**（如 §4.3 commit 被推 production 後 engine 拒啟）:
   ```bash
   git diff HEAD~1 settings/risk_control_rules/risk_config_*.toml
   ```
   如有 → `git revert` 回上一版 commit + push + 重啟。
3. **強制 ctor default rebuild**（極端情境）:
   ```bash
   bash helper_scripts/restart_all.sh --rebuild --keep-auth
   # ctor default = shadow_mode=false (LG1-T3 後)
   # 啟動後立刻 IPC patch 切回需要的值
   ```
4. **PM root-cause 24h 內**：補 audit + 修腳本/TOML 後再 retry。

---

## 10. H0 hot-reload gap：歷史原因與2026-09-28本地修正

2026-05-11 的 E2 reviewer note 指出：`apply_risk_snapshot` 沒有複製 `runtime.h0_shadow_mode`，因此 TOML／ConfigStore 與 H0 派生狀態不一致；當時以 ignored regression 留下證據。此歷史 finding 由2026-09-28本地候選修正處理，**尚未合併／部署，也不是獨立 reviewer PASS**。

目前 source 契約：

1. `set_risk_store` 立即套用 startup snapshot；ConfigStore 升版後，在下一個有效價格 tick 同步。H0 用 `set_shadow_mode` 套用模式，以保留 transition audit log；原有健康／時效欄位不被重置。
2. `RiskConfig::default()`、缺 runtime section、缺 `h0_shadow_mode` 欄位均為 `false`，保留 ctor hard-block。顯式設定 `true` 才進 shadow；未改 paper/demo/live 現有 TOML 或 live gate。
3. Legacy `update_risk_config` 的 H0 修改先經 `ConfigStore.apply_patch`＋validate，成功才改 H0；失敗回錯誤且保留舊狀態。無 store 的本地 setter 保留相容行為。後續 unrelated config reload 不會回退已接受的 H0 選擇。
4. 原 ignored case 已納入 ordinary regression：[`h0_ctor_default.rs`](../../rust/openclaw_engine/src/tick_pipeline/tests/h0_ctor_default.rs) 的 `bya_gap_h0_*` 覆蓋 startup、雙向切換、真 gate verdict、缺欄位與三引擎隔離；[`handlers_paper_cmd_tests.rs`](../../rust/openclaw_engine/src/event_consumer/tests/handlers_paper_cmd_tests.rs) 覆蓋 legacy IPC 與再熱更新。

版本化設定是 reload 的權威來源；直接改 `H0Gate` 只屬 in-process 操作，不另建立持久真值。Linux 本輪 offline，相關 runtime 驗證依 Operator 指示跳過。沒有從本地 fixture 推定配置已在目標機生效。

---

## 11. 修訂歷史 / Revision History

| 版次 | 日期 | 修訂者 | 摘要 |
|---|---|---|---|
| **v1** | 2026-05-11 | E1 (LG1-T3) | Wave 2.2 baseline runbook：flip / rollback / 監測 / fail-mode / checklist / reviewer note |

---

## 12. Cross-References

- 上游 PA tech plan：[`docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-11--lg_2_3_4_design_plan.md`](../CCAgentWorkSpace/PA/workspace/reports/2026-05-11--lg_2_3_4_design_plan.md) §1
- 原 RFC：[`docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-01--lg2_h0_blocking_verification_rfc.md`](../CCAgentWorkSpace/PA/workspace/reports/2026-05-01--lg2_h0_blocking_verification_rfc.md)
- W-AUDIT-3b runtime smoke：[`docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-11--w_audit_3b_runtime_smoke.md`](../CCAgentWorkSpace/E4/workspace/reports/2026-05-11--w_audit_3b_runtime_smoke.md)
- H0Gate 實作：[`rust/openclaw_core/src/h0_gate.rs`](../../rust/openclaw_core/src/h0_gate.rs)
- Hot path 接入：[`rust/openclaw_engine/src/tick_pipeline/on_tick/step_0_5_h0_gate.rs`](../../rust/openclaw_engine/src/tick_pipeline/on_tick/step_0_5_h0_gate.rs)
- ctor default：[`rust/openclaw_engine/src/tick_pipeline/pipeline_ctor.rs:75–93`](../../rust/openclaw_engine/src/tick_pipeline/pipeline_ctor.rs)
- LG1-T3 unit tests：[`rust/openclaw_engine/src/tick_pipeline/tests/h0_ctor_default.rs`](../../rust/openclaw_engine/src/tick_pipeline/tests/h0_ctor_default.rs)
- LG1-T1 E2E tests：[`rust/openclaw_engine/src/tick_pipeline/tests/h0_blocking.rs`](../../rust/openclaw_engine/src/tick_pipeline/tests/h0_blocking.rs)（並行 land）
- IPC patch route：[`program_code/exchange_connectors/bybit_connector/control_api_v1/app/risk_routes.py:222–243`](../../program_code/exchange_connectors/bybit_connector/control_api_v1/app/risk_routes.py)
- IPC handler：[`rust/openclaw_engine/src/event_consumer/handlers/risk.rs:313`](../../rust/openclaw_engine/src/event_consumer/handlers/risk.rs)
- TOML 預設：`settings/risk_control_rules/risk_config_{paper,demo,live}.toml`
- Sibling runbook（風格參考）：[`docs/runbooks/replay_signing_key_rotation.md`](replay_signing_key_rotation.md)
