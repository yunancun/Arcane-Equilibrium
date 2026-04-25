---
name: e2e-integration-acceptance
description: Wave 完成 / Phase 結束 / Live 前置端到端集成驗收 — 雙進程 E2E、灰度 7 天 0 CRITICAL、冒煙最短路徑、業務鏈完整度。QA agent 主用。
allowed-tools: Read, Grep, Glob, Bash
---

# E2E Integration Acceptance（端到端集成驗收手冊）

> **優先序**：runtime RiskConfig TOML > Rust schema > CLAUDE.md > 治理 .md > memory > 本 skill
> **衝突時向 PM / operator push back，不單方面執行 skill 內 SOP**

> **S3 上層 drift 防線**：本 skill 引用上層（CLAUDE.md / DOC-XX / SM-XX / EX-XX）為 extract；原文修改後可能漂移，發現不一致以原文為準。

## 何時觸發

- QA 收到「Wave 完成驗收」「Phase 結束 sign-off」「Paper → Live 前置」「重大架構改動後」
- 多模塊 PR 合入後的第一次集成驗收
- Demo 21d 穩定期前後檢核（Phase 5 reframed）
- AI 治理層 / Layer 2 / 5-Agent 接線完成後

## ★ 核心立場

**E4 看代碼層測試，QA 看業務層完整性**：
- E4：unit / integration test 過了
- QA：跑通完整業務鏈、跨模塊一致、上線前驗收清單

**QA 失敗 = block 進入下一 Phase**，包括但不限於 Live 啟動。

## 1. CLAUDE.md §九 既有 E2E 驗收清單

> ⚠️ **數字為 2026-04-25 snapshot**（治理端點 28/28、SLA <1ms 等可能演進）；以 CLAUDE.md §九 + §四 hard gates 原文為準，本表為 extract。

```
[ ] 測試數超過基準線（無新增 failed）— 數字以最近 baseline run 為準
[ ] H0 Gate SLA 通過（<1ms，verify: passive_wait_healthcheck check_h0_gate）
[ ] 治理端點 28/28 Operator 驗證完整 — 實際數以 grep "/api/v1" + 實測為準
[ ] paper_trading 完整流程：掃描 → 信號 → 審批 → 下單 → 止損
[ ] GovernanceHub fail-closed 在 FREEZE 模式真實拒絕訂單
[ ] 審計日誌完整（每筆訂單有 trace）
[ ] CLAUDE.md 狀態描述與代碼現狀一致
[ ] live_execution_allowed = false 確認
```

## 2. 業務鏈完整性（OpenClaw 5 階段）

| 階段 | 端到端驗證 | 命令 / 證據 |
|---|---|---|
| **市場數據** | Bybit WS + REST 都連 | `tail bybit_listener_status_latest.json` 看 4 topics live |
| **H0 本地判斷** | freshness / health / eligibility / risk envelope < 1ms | `passive_wait_healthcheck.py` check_h0_gate |
| **AI 治理（H1-H5）** | thought_gate / budget / model_router / governor / cost_logging | `tail layer2_cost_tracker.log` |
| **5-Agent + Conductor** | scout / strategist / guardian / analyst / executor 通信 | strategy_wiring.py 檢視 PID + log |
| **Decision Lease + Rust Engine** | acquire_lease / release_lease + engine SubmitOrder | engine_alive=true + lease grant log |
| **執行 + 止損** | order placed / fill received / stop manager active | trading.fills 最新 row |
| **學習 / 歸因** | exit_features / outcome_backfiller / edge_estimator | learning.exit_features count + edge_estimates mtime |

每階段 0 CRITICAL = 整體 PASS。

## 3. 雙進程 E2E（Rust Engine + Python AI/GUI）

### 3.1 啟動序
```
1. Rust openclaw_engine 啟動（systemd / restart_all.sh --rebuild）
2. Python uvicorn 連 IPC（engine.sock）
3. AI 請求送 Rust → Rust 處理 → 回 Python → GUI 讀
```

### 3.2 故障降級驗證
```
1. Python 主動斷連 → Rust L0 自動降級
2. Python 重啟 → 重連 → state 恢復
3. Rust 重啟 → Python 偵測 IPC fail → graceful retry
```

### 3.3 灰度驗收（CLAUDE.md memory `project_track_p_runtime_live`）
- 連續 7 天 CRITICAL=0 且 WARNING<10
- Python 影子進程 vs Rust Engine tick 輸出差異 < 1e-4
- DB row count 持續累積（無 silent dead）

## 4. 冒煙測試（最短路徑）

5 個必跑：

### 4.1 Health
```bash
ssh trade-core "curl -s http://localhost:8000/api/v1/health | jq"
```
預期：`{"status":"ok", "engine_alive":true}`

### 4.2 Strategy 信號
```bash
ssh trade-core "curl -s http://localhost:8000/api/v1/paper/shadow/decisions?limit=5 | jq '.decisions | length'"
```
預期：> 0（last 5 min）

### 4.3 Engine status
```bash
ssh trade-core "python3 helper_scripts/canary/engine_watchdog.py --data-dir /tmp/openclaw --status"
```
預期：engine_alive: true + binary mtime fresh

### 4.4 DB write activity
```bash
ssh trade-core "psql -c 'SELECT max(ts), count(*) FROM trading.fills WHERE ts > now() - interval \\'5 min\\''"
```

### 4.5 Healthcheck pipeline
```bash
ssh trade-core "python3 helper_scripts/db/passive_wait_healthcheck.py"
```
預期：17 check 全 PASS（或非新增 FAIL）

## 5. Live 前置（Phase 6 / Mainnet 啟動）

CLAUDE.md §四 hard gates 5 項：
1. Python `live_reserved` global mode（Python 側 RAM）
2. Python Operator role auth
3. `OPENCLAW_ALLOW_MAINNET=1` env（Rust 側）
4. secret slot 有 api_key + api_secret
5. `authorization.json` HMAC 簽名 + 未過期 + env_allowed 匹配

QA 必逐項驗：
```bash
# Gate 1: live_reserved
ssh trade-core "python3 -c 'from app.modes import is_live_reserved; print(is_live_reserved())'"

# Gate 3: env var
ssh trade-core "echo \$OPENCLAW_ALLOW_MAINNET"

# Gate 4: secret slot
ssh trade-core "ls \$OPENCLAW_SECRETS_DIR/live/"

# Gate 5: authorization.json
ssh trade-core "python3 helper_scripts/live/verify_authorization.py"
```

任一 fail = Live 啟動 BLOCKED。

## 6. 跨模塊一致性

### 6.1 API ↔ GUI ↔ DB 同步
- API response schema vs GUI render
- DB schema vs API response
- 命名術語：`engine_mode` 在 API / GUI / DB 都用同一字串

### 6.2 Python ↔ Rust 一致
- IPC schema 雙向對應
- Indicator 計算 1e-4 容差
- engine_mode 標籤 ('paper'/'demo'/'live_demo'/'live') 兩側統一

### 6.3 RAM ↔ DB ↔ TOML 一致
- `RiskConfig` 熱重載：TOML edit → IPC patch → engine RAM 同步
- 不應出現「TOML 改了但 engine 沒生效」

## 7. 工作流（12 步 Wave 驗收 SOP）

1. **E4 baseline 確認**（測試數無回退）
2. **5 階段業務鏈逐項**（§2 表）
3. **雙進程 E2E**（啟動 / 降級 / 重連）
4. **冒煙 5 條**（§4）
5. **跨模塊一致性 3 維**（§6）
6. **CLAUDE.md §九 8 條 checklist**（§1）
7. **Live 前置 5 hard gate**（如 Phase 6）
8. **灰度 7 天驗證**（CRITICAL=0 / WARNING<10）
9. **healthcheck cron 24h 全 PASS**（17 check）
10. **GovernanceHub FREEZE 模式真實拒單測試**
11. **CLAUDE.md §三 狀態描述對照**（drift 檢查）
12. **report + sign-off**

## OpenClaw 特定核心

- **強制工作鏈 E1→E2→E4→QA→PM**（CLAUDE.md §八）
- **Phase 5 reframed**：所有活躍策略 gross edge 為負，Live 前最早 ~2026-05-23
- **Demo 21d 時鐘**：從 2026-04-16 22:16 起算（CLAUDE.md §十）
- **engine_mode 4 值**：paper / demo / live_demo / live
- **engine_alive 不在 Mac**：Mac 端永遠 false 是預期，必走 ssh trade-core
- **passive_wait_healthcheck.py 17 check**：cron 6h
- **commit 即 push**（CLAUDE.md §七 git 自動化）
- **§三 drift 規則**（G6-04）：runtime 數值 + 採集時間註明，7d 未驗即刪
- **CLAUDE.md §三 vs runtime drift 防線**：採納前 source-of-truth 實測

## Cross-Skill 互引（避免重述）

- **C1.g E4 vs QA 角色界定**：本 skill 看「業務鏈完整 + 跨模塊一致 + 灰度趨勢 + Phase 6 hard gates」；**單元/整合/並發/SLA 壓測 baseline 細節**走 `regression-testing-protocol`。E4 過了 QA 才能跑，**不是同層**
- **PR review 前置**：QA 之前 E2 對抗審查走 `pr-adversarial-review`，QA 不重做 code review

## 反模式（見即 BLOCKER）

- E4 過了直接放行 QA（不跑業務鏈）
- 冒煙測試只跑 1 條
- 雙進程不驗降級 + 重連
- Live 前置只驗 1-3 gate
- 7d 灰度沒看 CRITICAL 趨勢
- healthcheck cron 沒跑就宣稱「stable」
- §三 數值沒對照 runtime 實測
- 跨模塊一致性沒驗 API ↔ GUI ↔ DB
- TOML 改了但 IPC 沒 patch（RAM 不同步）

## 輸出格式

```markdown
# QA E2E Acceptance — <Wave / Phase> · <date>

## E4 baseline
| Engine | passed | failed | baseline 變動 |

## 5 階段業務鏈
| 階段 | 證據 | 狀態 |
| 市場數據 | | |
| H0 本地 | | |
| H1-H5 AI | | |
| 5-Agent | | |
| Decision Lease + Rust | | |
| 執行 + 止損 | | |
| 學習 + 歸因 | | |

## 雙進程 E2E
- 啟動: Y/N
- 降級: Y/N (Python 斷 → Rust L0)
- 重連: Y/N

## 冒煙 5 條
| Test | 證據 | 狀態 |

## 跨模塊一致性
- API ↔ GUI ↔ DB: ...
- Python ↔ Rust 1e-4: ...
- RAM ↔ DB ↔ TOML: ...

## §九 8 checklist
| Item | 狀態 |

## Live 前置 5 gate（如適用）
| Gate | 狀態 |

## 灰度 7d 統計
- CRITICAL: X (target = 0)
- WARNING: Y (target < 10)
- Healthcheck pass rate: Z%

## §三 drift check
| 數值 | source-of-truth 實測 | drift? |

## 結論
PASS to next Phase / BLOCK (X 個 finding)

## BLOCKER 清單（如 BLOCK）
1. <具體 + 修法 + owner>
```
