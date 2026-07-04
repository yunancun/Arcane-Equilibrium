# B2-5a over-gate 統一設計落地 A(E1-A/C/F)實現報告 — 2026-07-04

> 角色 E1;冷審計 R2 修復 Phase B2。嚴格按 PA spec `docs/CCAgentWorkSpace/PA/workspace/reports/2026-07-04--overgate_residual_unified_design_p11.md` §4.A/B/E + §6 E2 審查點 + §7 驗收執行,不擴 scope。
> 隔離 worktree:`.../scratchpad/wt-overgate-a`,branch `fix/overgate-a-0704`(自 origin/main `2be58c19`),commit `d15fd44d`。**未 push;主樹未動。**

## 1. 任務摘要

實現 over-gate 殘差統一設計中 E1 派發的 A/C/F 三條(檔零重疊,SCRIPT_INDEX 交 E1-D):
- **E1-A** soak-window TTL 對齊 + /tmp 默認收口(RES-7)。
- **E1-C** 新 soak plan 自動 re-materialization(plan freshness 與 authority 解耦)。
- **E1-F** soak 哨兵軸(RES-9)+ refresh round orchestrator/ledger(RES-3)。

全部 demo learning lane 源碼側,0 Rust 改動,0 engine rebuild;live 5 gates 與 9 不變量零觸碰。

## 2. 修改清單

| 檔 | 類型 | 內容 |
|---|---|---|
| `helper_scripts/research/cost_gate_learning_lane/standing_demo_authorization_refresh_guardrail.py` | 改 | E1-A:`--soak-window-hours`+SOAK_MAX=96+/tmp→OPENCLAW_DATA_DIR |
| `helper_scripts/research/cost_gate_learning_lane/soak_plan_rematerializer.py` | 新 | E1-C:fail-closed re-materializer(byte-preserve) |
| `helper_scripts/cron/cost_gate_learning_lane_cron.sh` | 改 | E1-C:`OPENCLAW_COST_GATE_REFRESH_SOAK_PLAN`(默認0)步驟+rc/status |
| `helper_scripts/cron/demo_learning_stack_healthcheck.py` | 改 | E1-F:soak 哨兵軸(admission 分布判據) |
| `helper_scripts/research/cost_gate_learning_lane/refresh_round_orchestrator.py` | 新 | E1-F:refresh SOP 確定性步驟機 + ledger |
| `.../tests/test_standing_demo_authorization_refresh_guardrail.py` | 改 | +6 soak/path 測 |
| `.../tests/test_soak_plan_rematerializer.py` | 新 | 12 測(含雙向 mutation) |
| `.../tests/test_refresh_round_orchestrator.py` | 新 | 7 測 |
| `helper_scripts/cron/tests/test_demo_learning_stack_soak_sentinel.py` | 新 | 9 測 |

## 3. 關鍵設計決策 / diff 要點

- **E1-A TTL 作用域封鎖**:`soak_window_hours` 為 None 時 `authorization_ttl_hours`/`max_authorization_ttl_hours` 逐位沿用 12/24;設定時 TTL=N∧max 帽=SOAK_MAX=96。**載重約束**:`summarize_standing_demo_authorization` 驗 `expires_at ≤ now+max_authorization_ttl_hours`,故放寬時 caller 必同傳抬高的 max_authorization_ttl_hours(現碼已傳),否則 72h envelope 過 expiry_valid 失敗——mutation-bite 證此判準真 load-bearing。SOAK_MAX=96=72h soak+24h margin(PA 小決策,168h API 天花板內保守半值)。
- **E1-C byte-preserve 雙層防線**(E2 審查點①核心):
  1. 授權邊界指紋(逐欄位鎖 order_authority/probe/order granted True/promotion False/cost_gate NONE,鏡像 `bounded_probe_plan_inclusion_review._auth_packet_safe`)——攔越權形態篡改。原因:byte-preserve 只保證搬運不改,若 plan 內 auth 塊本身被改成越權態,byte-preserve 會忠實搬運越權塊=腳本代簽災難。
  2. 可選 `--expected-authorization-sha256` anchor(orchestrator 簽名時記錄)——攔連指紋都合法但欄位被改、腳本無法獨立再推導者(operator_id/max_authorized_probe_orders)。
  3. 輸出自證:re-stamp 後重算 auth 塊 sha 必等於輸入 sha,否則 `rematerialized_plan=None`+拒。
- **E1-F 哨兵判據=admission decision 分布**(禁 ledger 行數):只計 `record_type=probe_admission_decision` 記錄,capture-error/probe_outcome 等雜 record 不算,防「有行=健康」失明(§1.4 評審實證)。soak WARN 僅在 stack 否則 green 時升起,不掩蓋更嚴重 blocker。
- **E1-F orchestrator 停點紀律**:兩停點(E3/BB 審、operator 簽)是僅有人工交接口;停點步驟不接受無 `human_intervention` 標記的 DONE(碼化「機器只能停在停點等人」),繞行=ledger 缺步驟可審計。

## 4. 治理對照

- **live 5 gates / 9 不變量**:零觸碰(全改動位 demo learning lane helper_scripts+cron)。硬邊界指紋掃自身 diff:`live_execution_allowed|OPENCLAW_ALLOW_MAINNET|live_reserved|max_retries|system_mode|execution_authority` = **0 命中**;bare/live `authorization.json` = 0 命中(唯一匹配=demo 檔 `standing_demo_operator_authorization.json`,pre-existing,非 live 授權面)。
- **跨平台**:新增/改動路徑全走 `OPENCLAW_DATA_DIR` 派生;added 行掃 `/home/ncyu`、`/Users/` = 0 命中。
- **fail-closed**:每件存疑態(JSON 壞/git 缺/簽名塊 sha 不符/候選變更/授權過期)全收斂 no-op+告警,無 fail-open 邊。
- **降級**:全 additive/參數門控——A(不傳參=舊行為)、C(cron flag 默認0)、F(純觀察面+新腳本);rollback=逐 commit revert(0 schema/IPC/Rust)。
- **注釋**:新注釋中文為主,英文留技術識別符;新檔均含 MODULE_NOTE。

## 5. 測試證據

- E1-A `test_standing_demo_authorization_refresh_guardrail.py` **16 passed**(10 既有 byte-preserve + 6 新:default 不變/soak 放寬+審計字段/ceiling/floor/超界拒/path 派生);mutation-bite:移 max-TTL 帽 soak 抬升 → soak 放寬測真 FAIL,還原後綠。
- E1-C `test_soak_plan_rematerializer.py` **12 passed**(含 E2 審查點① 授權欄位雙向 mutation 8 欄+sha anchor 非指紋類 2 欄+byte-preserve round-trip+e2e 0600+no-op 守恆);mutation-bite:輸出 auth 塊被改 → byte-preserve 自證 FAIL,還原後綠。CLI e2e:0600、generated_at 重蓋、auth 不變、soak_rematerialization 快照。
- E1-F healthcheck **21 passed**(12 既有無回歸 + 9 哨兵:未武裝/envelope 過期/零 admission WARN/雜 record 不餵飽=分布非行數/窗外剔除/缺 ledger 不崩/端到端不掩蓋);orchestrator **7 passed**(兩停點/停點無人工拒/DONE 帶人工/AWAITING_HUMAN/未知步/dry-run);mutation-bite:移停點守衛 → 停點紀律測真 FAIL,還原後綠。
- 環境:Mac python 3.10.1(無 tomllib,但測用 dict fixture 非 TOML 不受限);`bash -n` cron 綠;全 py_compile 綠。

## 6. 不確定之處 / 偏差

- **SCRIPT_INDEX.md 未動**:2 新腳本(soak_plan_rematerializer/refresh_round_orchestrator)登記交 E1-D/PM 收口(spec §5「其餘新腳本登記由 E1-D 統一收尾」;避免與 E1-D 檔 overlap)。**follow-up 明確落地此處**。
- **orchestrator 定位=編排/記帳器**:不代執行子 CLI、不代簽名/審查(spec §4.E「判斷留人/agent」+安全 scope)。子 CLI 實走由 E4 回歸/operator 串接;orchestrator 提供確定性步驟序+ledger 為量測基礎。spec §8④指 orchestrator 引用的各 CLI 形態=today FACT,E4 落地前逐一 `--help` 重驗——本實現不硬綁具體 CLI 調用,故不受該漂移影響。
- **PG dry-run 不涉**:本任務 0 SQL migration、0 PG 寫;rematerializer/healthcheck 全讀本地 artifact,無需 Linux PG empirical。
- **哨兵 armed 輸入**:healthcheck 唯讀無 engine env,adapter armed 由 `--soak-adapter-armed` 顯式傳(cron 接線時由 operator/E1-D 依 engine env 決定);envelope Active 由 soak plan 簽名塊 expires 判(read-only 可判)。

## 7. Operator / 下一步

1. E2 審查(spec §6 三點,重點:E1-C byte-preserve 雙向 mutation 已自證、E1-A TTL 作用域封鎖已測、哨兵 admission 分布判據);
2. E4 回歸(§7 AC:TTL 全鏈一致/re-stamp 跨 24h 綠/哨兵/orchestrator 子 CLI `--help` 重驗);
3. E1-D/PM:SCRIPT_INDEX.md 補 2 新腳本登記 + cron 接線 `--soak-adapter-armed`;
4. E3/BB one-time policy 簽核 → v739 實走。

E1 IMPLEMENTATION DONE: 待 E2 審查(branch fix/overgate-a-0704,commit d15fd44d)
