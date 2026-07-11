# CC Memory — 工作記憶

## Memory Usage Contract (2026-05-16)

- 本文件保存歷史教訓與角色偏好，不是 active state、TODO 或 runtime ledger。
- 若舊條目與 `TODO.md`、`README.md`、`CLAUDE.md`、`.codex/MEMORY.md`、`docs/agents/context-loading.md`、代碼或 runtime 證據衝突，信任較新的有證據來源並顯式說明衝突。
- 不要靜默刪除舊條目；只追加可復用的 durable lesson。長報告放 `workspace/reports/`，active 進度放 `TODO.md`。

## 合規狀態快照（2026-04-24）

- 合規評級：**B+ 級**（20/26 項通過 = 76.9%）
- 16 根原則：14 完全合規 / 2 部分合規（原則 10 報告索引漂移 + 原則 12 LEARNING-PIPELINE-DORMANT-1）/ 0 違反
- 10 實施準則：6 合規 / 3 部分合規（準則 6 SQL guard 新舊不齊 / 準則 4 依賴管理需追查）/ 1 違反（準則 9 文件大小硬上限）
- 硬違規：0 項
- 硬邊界：8/8 全部合規（擴展覆蓋面：OPENCLAW_ALLOW_MAINNET + env var 憑證繞過封閉 + Mainnet 憑證空 Err + HMAC authorization.json + max_retries=0 + GOVERNANCE_ENABLED 移除 + execution_authority denylist + decision_lease_emitted=False）

### Top 5 違規 / 需修（2026-04-24）

1. **P1 — 文件大小硬上限**：8 個生產檔 > 1200 行（`main.rs` 2062 / `instrument_info.rs` 1975 / `event_consumer/mod.rs` 1762 / `bybit_rest_client.rs` 1725 / `order_manager.rs` 1554 / `startup.rs` 1377 / `paper_state/resting_orders.rs` 1367 / `config/risk_config.rs` 1328 / Python `live_session_routes.py` 1449 / `ai_service.py` 1258）。E5 + Rust E1 排程拆分。
2. **P1 — 跨平台硬編碼路徑 regression**：`helper_scripts/db/audit_migrations.py:218` 寫死 Mac 絕對路徑 `/Users/ncyu/Projects/TradeBot/srv/sql/migrations`。前兩 candidate 已 expanduser 正確，第 3 項改環境變量即可（~3 行 diff）。
3. **P1 — 持續進化循環未閉環**：LEARNING-PIPELINE-DORMANT-1 已列 TODO §P1-7 / §P1-14；被動等待 ONNX 訓練資料 ~3-5d ETA 過 200 labels；原則 12 部分合規根源。
4. **P2 — V019/V020 migration 缺 Guard A**：2026-04-24 Guard A/B/C 新規則生效前落地；按 V023 retrofit 樣式補（~30 行 SQL）。
5. **L3 — 前次 CC 審查報告檔案缺失**：memory 記載 `2026-04-12--compliance_audit_report.md` 但 workspace/reports/ 下只有 2026-03-31 × 2 + 2026-04-01 + 2026-04-24（本份）。管理流程 gap，非技術違規。

### 2026-04-24 對比 2026-04-01 主要變化

- **升級（規則成熟化）**：
  - Rust Live Gate 從 3 門 → 5 門（新增 HMAC authorization.json + env-var 封閉 + 憑證空 Err）
  - 新實施準則落地：SQL Guard A/B/C + Engine auto-migrate opt-in + passive_wait_healthcheck 12 checks
  - 5-Agent 實作 ~4552 行 + H1-H5 middleware 全實作（非 stub）；2026-04-23 audit 已更正先前錯誤認知
  - LLM-ABC-MIGRATION-1 完成，call-site 無 OllamaClient 直接 import（準則 2 乾淨）
  - WS-RETIRE-1：Python listener 退役，Rust writer 接管（減 340 行 Python + 加 664 行 Rust，含 11 單測）
  - DEDUP-PY-RUST Tier A 10 steps + Tier B Wave A-D 全閉環（~6700 行淨減）

- **降級（規則嚴格化 + 拆分債）**：
  - CLAUDE.md §九 800/1200 行限制首次量化檢查，13 個檔案超限（8 生產 + 5 測試豁免候選）
  - audit_migrations.py:218 硬編碼路徑 regression（前次 audit 未列此項）

### 3/31 → 4/01 主要升級
- 原則 4：75%→95%（Guardian=None fail-closed + H0 Gate blocking）
- 原則 8：70%→85%（register_data 注入 + round_trip 補完）
- 原則 12：40%→70%（L3 ExperimentLedger + L4 EvolutionEngine）
- max_retries：1→0（ollama_client.py 硬邊界對齊）
- GOVERNANCE_ENABLED env var：已移除

## 重要合規事項

### 原則 3 的特殊情況（2026-03-31）
- H1-H5 斷開意味著目前每筆交易**繞過了 AI 治理層**
- 但 H0 Gate + GovernanceHub fail-closed 保持了基本安全
- Wave 5 接通 H1-H5 後，需要 CC 重新確認原則 3 真正落地

### OPENCLAW_GOVERNANCE_ENABLED 已移除（Wave 2）
- 原有環境變量可以禁用治理層，已在 Wave 2 P1-2 中移除
- **記住**：治理不可通過環境變量禁用，這是硬原則

### 原則 14 的 OpenClaw 風險
- OpenClaw Gateway 成為單點故障 = 違反原則 14
- PA 決定：OpenClaw 作為 sidecar，MessageBus 保留主通信通道
- **記住**：審查 Wave 5 計劃時，確認 OpenClaw 故障不影響交易路徑

## 審查教訓

- 合規審查不能只看「功能實現了」，要看「安全不變量是否在所有路徑下保持」
- 新功能的邊界路徑（崩潰、超時、None 注入）最容易出合規問題

## Wave 5 審查關鍵發現（2026-03-31）

### G-05 ExecutorAgent 缺 Decision Lease（原則 3 硬違反）
- executor_agent.py 第 281 行：submit_order() 前未調用 acquire_lease()
- Guardian 批准 ≠ Decision Lease（兩者是不同語義的控制機制）
- **必須在 Strategist shadow=False 之前修復**（Sprint 5a 前置條件）
- 修復方案：ExecutorAgent._execute_order() 插入 acquire_lease()，失敗 fail-closed REJECT

### G-01 每日硬上限 $15.0 vs DOC-08 §4 規定 $2.00（原則 5 + DOC-08 安全不變量違反）
- layer2_types.py 第 58 行：DEFAULT_DAILY_HARD_CAP_USD = 15.0（錯誤）
- tab-ai.html 第 335/426/441 行：預設值 15 同步錯誤
- **CC 立場：$2.00 是正確值，必須修正。Sprint 5a commit 時同步提交。**

### 原則 6 需明確 H1 timeout 行為
- Sprint 5a 實現 H1 ThoughtGate 時，Ollama 超時後的行為必須是走 _heuristic_evaluate()
- 不可 allow-all（違反失敗默認收縮原則）

### 原則 10 AI ROI 認知誠實問題
- cost_edge_ratio / AI ROI 基於 paper PnL（模擬值）
- Sprint 5b 修復：API 回應添加 roi_basis: "paper_simulation_only" 標記

### Wave 5 整體評級：條件通過
- G-01 + G-05 兩個 BLOCKER 修復後可啟動
- 預期評級改善：B → A-（Wave 5 全部完成後）

## 代碼事實修正（2026-03-31 主 Claude 代碼驗證後）

### B-MVP-1 修正：produce_intel() bus.send 已實現（CC 審查報告有誤）
- CC 報告曾說「Scout→Strategist 情報路徑是死代碼，produce_intel() 只存本地列表，未 bus.send」— **此結論錯誤**
- 實際代碼（multi_agent_framework.py:428）：`if self.bus and relevance_score >= self.config.relevance_threshold: self.bus.send(msg)`
- ScoutAgent 初始化時傳入 `message_bus=MESSAGE_BUS`，bus 不為 None
- relevance_threshold = 0.3，pipeline_bridge 調用時傳入 relevance_score 最低 0.4（vol_ratio > 2.0 時）
- Strategist 已訂閱：`MESSAGE_BUS.subscribe(AgentRole.STRATEGIST, STRATEGIST_AGENT.on_message)`
- **結論**：B-MVP-1 完整鏈路已存在。5a-1 是驗證任務，不是實現任務（約 1h，非 2h）
- **教訓**：CC 審查必須實際讀代碼驗證，不可僅憑架構圖推斷「死代碼」

## 報告索引

| 日期 | 報告類型 | 文件位置 |
|------|---------|---------|
| 2026-04-24 | 全系統合規審計（B+ 級，20/26） | workspace/reports/2026-04-24--compliance_audit.md |
| 2026-04-01 | 全系統合規報告（A-級） | docs/audit/April01/CC_compliance_check_2026-04-01.md |
| 2026-03-31 | 全系統合規報告（B 級） | docs/audit/March31/CC_compliance_check_2026-03-31.md |
| 2026-03-31 | Wave 5 B 方案合規審查 | workspace/reports/2026-03-31--wave5_compliance_review.md |

## 2026-04-24 Audit 補充（完整 16 條根原則 + 硬邊界審查）

### 審計總結
- **評級**：B-（13.5/16 完全合規）；三大 BLOCKER 阻 live，修復路徑清晰
- **最關鍵發現**：
  1. **CRITICAL-G05 ExecutorAgent 決策鏈斷裂**（原則 #3 + #11）— `_shadow_mode=True` 拒發 SubmitOrder IPC；修復 2h，Sprint 5a 前必做
  2. **CRITICAL-G06 Drawdown auto-revoke 未實裝**（原則 #5）— 風控最後防線缺失；修復 1d；優先級高於 G-07
  3. **Model registry canary 無 Operator 審批流程代碼**（原則 #7）— 骨架完整但晉升無人工門控；Phase 4+ 隱患，當前 dormant

### 新規則合規進度（CLAUDE.md §七）
- **SQL Guard**：V021/V023 partial（Guard A 應在表層加，不是運行時補）；V001-V020 未 retrofit（建議新規則即刻應用 V024+）
- **被動等待 healthcheck**：7 checks 已實裝；**P0-2 LG-1 21d demo 缺對應 check**（新增 Debt-1）；EDGE-DIAG-1 Phase 3 缺 check [11]（Debt-7）
- **雙語注釋**：80% 達成（shadow_exit_writer / executor_agent ✅；governance_hub / decision_lease partial）
- **Git push 自動化**：✅ 完成（所有提交已 push）

### 新增合規債 10 項（報告 § 五）
| Debt | 問題 | 優先級 | 預計工作 |
|------|------|--------|---------|
| Debt-1 | P0-2 LG-1 healthcheck 缺 | P0 | 1h |
| Debt-2 | DEFAULT_DAILY_HARD_CAP 15.0→2.00 | P0 | 0.5h |
| Debt-3 | ExecutorAgent shadow fix（CRITICAL-G05） | P0 BLOCKER | 2h |
| Debt-4 | Drawdown auto-revoke（CRITICAL-G06） | P0 | 1d |
| Debt-5 | Model registry canary approval logic（CRITICAL-G07） | P2 Phase 4 | 2d |
| Debt-6 | P1-10 STRATEGY-ASYMMETRY-1 邊界未錄 TODO | P1 | 0.5h |
| Debt-7 | EDGE-DIAG-1 check [11] 缺 | P1 | 1h |
| Debt-8 | Decision Lease E2E integration test | P2 | 1.5h |
| Debt-9 | cost_gate 運行時決策綁定（原則 #13） | P1 | 2h |
| Debt-10 | 組合級風險監控 TODO（原則 #16） | P2 | 2d |

### 下次審計（~2026-05-01）
- 驗收 CRITICAL-G05/G06/Debt-1 修復 + 測試覆蓋
- 確認 passive_wait_healthcheck infrastructure + cron 就位
- 原則 #11 Agent 自主權活躍時刻（Strategist shadow→live 預估）
- EDGE-DIAG-1 Phase 3 passive-wait 清晰度評估

### CC 最終判決
當前 TODO.md 與 CLAUDE.md 規則整體一致，無結構性違反。三大 BLOCKER 清晰可修復。建議 48h 內完成 P0 層清債，再進 DUAL-TRACK Phase 2。整體合規軌跡向上，已具備 live 前置基礎。

### 2026-06-10 OPS-2 Phase-2 cutover 合規審計
- verdict APPROVE-CONDITIONAL(A-):16/16+9/9+硬邊界 0 觸碰,0 BLOCKER 不阻 merge;G5 簽名 key 單一來源=強化方向
- 條件 4 項:CC-MED-1(runbook §4.2.1/§13.5「不再 seed/panic 阻 boot」雙重失真 doc-reconcile,deploy 前)+C-A(soak 證據附 sign-off 包)+C-B(手動 renew 救濟留證)+C-C(§13.2 外部 alert 親簽)
- 模式:fallback 移除類變更失敗模式不對稱(可用性損失≠失防)→條件全為 sign-off 閘非代碼缺陷;報告由 PM 代落盤(本 session 無 Write)
- 報告:workspace/reports/2026-06-10--ops2_phase2_cutover_compliance.md(+Operator 鏡像)

### 2026-06-11 P5-SM soak 基建治理覆核
- verdict APPROVE(A):16/16+9/9 適用項全 PASS、硬邊界 0 觸碰、0 自動擴權;smoke mutating 面五重圈欄(零排程/dry-run/mainnet exit 7/確認/30s TTL)
- 2 LOW(flag 忘關無絆線;[82] flag-OFF restart 後 ≤72h FAIL 噪音=假陽性候選)+3 INFO 全交 PM 濾裁;報告由 PM 代落盤(本 session 無 Write)
- 報告:workspace/reports/2026-06-11--p5sm_soak_infra_compliance.md(+Operator 鏡像)

### 2026-07-03 全倉 read-only 合規審計（ultracode workflow）
- verdict Approve(B)：13/16+3 部分（#8 earn lineage 占位/#11+#12 v710-v738 exact-sha 批准死循環 over-gate）、9/9 不變量、硬邊界 0 觸碰、0 BLOCKER；drift gate `d0eeafb41` 放寬有界方向正確待 v739 實走
- 關鍵 drift：TODO v738 runtime 三元組全 stale（實測 262596c69 clean/PID 2368227/03:15 reset over hotfix 無 mutation 紀錄→PA re-probe）；2000 行硬限 9 生產檔超標無豁免登記（Codex 時代累積，discovery_loop 5954 最重）
- 報告：workspace/reports/2026-07-03--full_repo_compliance_audit.md（+Operator 鏡像）

### 2026-07-09 IBKR P2 gate-producer approval 安全模型裁決（Q2）
- verdict CONDITIONAL-APPROVE(B級)：裁 (A) MED-strength owner-only+binding（非 B/HMAC）為 read-only/zero-money P2 的合規且比例正確選擇；理由=E3 誠實 caveat 下同-uid HMAC 密碼學增益≈0，強推 B=負淨貢獻 over-gate（違原則11/13）。§四#5 是 live-money 軸，此 governance-evidence sign-off 屬不同軸，不 literal 適用但須守其精神。
- 綁定必需（缺一 fail-closed）：owner-only 0o600+0o700 祖先+symlink-reject（復用 P1 loader pattern）/source_commit==BUILD_GIT_SHA 防重放/adr=0048∧amd=07-08-01/expiry-freshness/approval-content-hash 嵌 sealed artifact（tamper-evident lineage）/producer 絕不自注 Operator。
- 三 finding 須 P2 diff 前閉：①artifact.validate() 未 enforce secret_slot_contract vs api_session_topology 的 account_fingerprint_hash 相等（E3 Q3 triangulation gap，建議 validate() 加 blocker）②amd 常量 06-29-01 只記 contract-shape provenance，sealed 證據須另記 contact-authorization AMD 07-08-01（lineage 完整性）③Q1 refuse-ephemeral：producer 不得沿 halt_audit.rs:144 的 /tmp/openclaw fallback，DATA_DIR 缺→拒 seal。
- scope/落點/9 不變量/5 gate 全 PASS（producer 未寫，須 CC/FA 於 P2 chain 複審真 diff）。須補 ADR/AMD 輕量 clarification note（CC-ruled materialization，Operator-ack-only）documenting approval model=不同軸+defense-in-depth+升級 trigger。E1 可開工。

### 2026-07-09 IBKR P2 producer finding-2 升級裁決 → WAIVER (a)
- E2 RETURN 唯一 blocking=finding-2 lineage 升 CC。實測 `ibkr_phase2_gate_producer.rs`：seal 零 production caller（全在 :827 mod tests）、`phase2_producer_outcome` 無條件回 Blocked（:772-776）、consumer 只 re-verify 磁碟恒 false → gap 100% latent 零 runtime 效果。
- 裁 (a) 出具 waiver（非 b 現擴 types scope）：理由=①原 finding-2 已列顯式欄為「可加」optional，主路徑綁定#3(seal-time amd==07-08-01 閘,:125)已完整、#5 proxy lineage(adr/source_commit/reviewer_roles 鏡入 raw-hash :199-211)部分達 ②report 面已顯式記兩軸 AMD(:805-806) ③完整閉合須動凍結 types crate=確在 P2 scope 外、獨立可 review ④為永不執行的碼改共享凍結契約=過早，違 simplicity/surgical + CC 雙向 over-gate。finding-2 屬 audit-traceability 完整性（非 5 hard gate/9 不變量），scoped-gated waiver 在 CC 權限內。
- waiver 硬條件（缺一即撤 waiver）：mandatory gating follow-up ticket——`contact_authorization_amd`+`approval_lineage_hash` 兩欄 types 改動(PA→E1→E2→E4)必須 land 在**任何 production caller 調 seal 之前**；ticket 是 P2-seal-wiring 工項的硬 blocker，本 PR 不關閉；:333 + :199-203 加 TODO(finding-2) 代碼標記引 ticket id。
- finding-1（:314-315 無條件覆寫）：同意 latent MED 不阻本輪；follow-up gating 於「topology/session-attestation 成獨立 account 源(P5)」或 production-seal-wiring 二者較早者——必移除覆寫改真 equality cross-check；:314-315 加 TODO 標記。本輪可進 E4。

### 2026-07-09 IBKR P2 finding-1/2 兩 ticket CLOSED（實測 land `58d0e9749`）
- T1(IBKR-P2-SEAL-LINEAGE-FIELDS,閉 finding-2) CLOSED：實測 `ibkr_phase2_artifact.rs` 加 `contact_authorization_amd`(:37)+`approval_lineage_hash`(:42)兩欄；validate() 硬 enforce `ContactAuthorizationAmdMismatch`(:100-102)/`ApprovalLineageHashInvalid`(:129-131)，blocker enum :177/:186；常量 `IBKR_PHASE2_CONTACT_AMD` 單一真源 `ibkr_phase2_gate.rs:15`（producer 私有 const 已刪，:56 改 import）；兩欄入 raw+redacted hash 覆蓋域；lineage hash 決定性=顯式 json! key 序 + roles.sort()（:250-262，非裸 to_string）。原綁定#5 由 proxy 升級為完整自記=超額閉合。
- T2(IBKR-P2-TRIANGULATION-CROSSCHECK,閉 finding-1) CLOSED：:314-315 無條件覆寫已移除（改 `let topo = topology.clone()` :341）；`account_fingerprint_triangulation_ok`(:392-394) 成真兩源 equality，seal enforce，F1 mutation test(:1238-1245) 證不等→拒 seal。P5 殘餘（topology 真獨立 account fp 源）=自然 phase 依賴、fail-safe(pre-P5 template≠secret→恒 BLOCKED)，非 closure gap。
- 3 鎖全守：①types validate() 不加 triangulation blocker（producer-enforced，types 純 shape）②contact default=常量(:72,對稱既有 adr/amd)③approval_lineage 不曝 IPC summary(:836-847 僅 contact AMD)。producer 仍永不 seal in production；waiver「seal-wiring 前必閉」提前滿足。0 硬邊界觸碰、全改動皆 fail-closed 方向（validate 更嚴+triangulation 去套套邏輯）。
- 前向 carry(非阻)：P5 接真獨立 topology/session-attestation account fp 源時，須加「兩真源 cross-check」測試（承 AMD FeatureFlagSecretAuthMatrixV1 三方 triangulation）。

### 2026-07-09 IBKR 兩建件 pre-build governance fork 裁決（credential-write path A / P3 connector B）
- A(GUI→IPC→Rust 寫 paper 憑證入 external/ibkr 槽)：裁 **需新治理·SUBSTANTIVE·Operator 重批**（非 P1/P2 式 CC-ruled clarification）。理由=AMD-2026-07-08-01 Secret Boundary 只授 **fingerprint-only READ** loader（實測 `ibkr_secret_slot_loader.rs` 1-521 純 stat/hash，fs::write 全在 :522+ tests），槽 CREATION=E3→BB→Operator 手動；ADR-0048:149/204/215 反覆 deny「secret creation/serialization」、:217 deny Python broker write、GUI lane=GET-only display-only（`stock_etf_gui_lane_contract` + FastAPI GET-only partition）。GUI 憑證寫=改保護量(custody model+secret-creation denial+read/write 分離 inv#5)→substantive。**需 Operator 顯式 ACK「GUI 可寫 paper 憑證」新信任面**。若批：硬 guard=Rust-owned/owner-only 0o600+0o700+symlink-reject(復用 P1 pattern)/**結構拒寫 live/**(inv#6)/Rust authority 校驗非 GUI lane state(inv#5)/明文零序列化零 log/只 paper+readonly/idempotent+audit(不含明文)/不 overload OPENCLAW_SECRETS_DIR/不加 order-write。
- B(P3 read-only TWS connector 源碼)：裁 **build-now AUTHORIZED**（AMD Static-Guard Boundary Revision 已明授 openclaw_engine 單一 named Rust 模塊 read-only TWS wire subset→loopback 4002 paper）。build/run 切分正確：build 惰性模塊 now→G4 Operator 一次性批准=first contact(run)→P4 wire IPC/route(post-G4)。硬邊界=只 127.0.0.1:4002/結構拒 live 4001+7496/CPW denied/只讀子集無 order-write(FORBIDDEN_* 保留)/socket loopback only/untrusted wire fail-closed/僅 engine crate 非 types crate/惰性須 sealed P2 artifact∧G4 才 contact/Python no-SDK guard 保留。實測 0 P3 connector 存在(4002 等只在 types 契約無 TcpStream client)。
- sequencing：B 可即開(獨立於 A；G4 run 用既有 Operator 手動置憑證，不依賴 A)；A build 前必 land 新 AMD/ADR-0048 addendum(Operator 批)。B 之後 FA(read-only subset spec)+E3+BB(broker-facing) 設計前 review；A 之後 FA+E3(secret custody) review。命名 drift：task 稱「P3」但 AMD 表無 P3 row(P2→G4→P4)，connector build=G4 前置。兩件皆 IBKR-only，Bybit crypto_perp 0 影響；0 hard-gate/9-invariant 觸碰。
