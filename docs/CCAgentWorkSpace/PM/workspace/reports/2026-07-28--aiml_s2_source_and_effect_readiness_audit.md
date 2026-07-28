# AI/ML S2 Source 與 Effect Readiness 獨立審核

- 審核日期：2026-07-28
- 審核基線：`a7c36775dc4050616dc3c3dbbd475135280e290d`
- 範圍：S2.0、S2.1、S2.2A、S2.2B、S2.3、S2.4、S2.5；W5 artifacts；
  governance routing；Linux `trade-core` runtime；PR/CI/publication evidence
- 性質：唯讀審核與派發校正；沒有 production PG、deploy、restart、migration、
  credential、broker、order 或 live effect

## PM 結論

前六個 PR 交付的 contracts、schemas、validators、source-only lifecycle seam、
fixtures 與 W5 artifacts 在它們宣告的窄義邊界內成立，可以保留
`SOURCE_READY`。但 `SOURCE_READY` 只表示「可供後續 effect engineering 使用的
source seam 已落地」，不表示 effect route、host runner、production
attestation 或 S2 closure 已完成。

`BLOCKED_OPERATOR_ACTION_PACKET_READY` 不成立。當前真實狀態校正為：

`S2_EFFECT_EXECUTION_READINESS_ACTIVE`

Fresh Operator authorization 不是唯一 blocker。在取得授權前仍有可執行且必須
完成的 source engineering；即使現在取得授權，治理路由也不會注入 S2.4/S2.5
effect adapter，S2.2B 也沒有可產生並驗證 production runtime attestation 的執行
路徑。

## 分軸狀態

| 軸 | 真實狀態 | 判定 |
|---|---|---|
| 已定義 source predicates | 7/7 landed；S2.0/S2.1/S2.2A/S2.3/S2.4/S2.5/S2.2B | 保留窄義 `SOURCE_READY` |
| W5 artifact 投影 | 8 artifacts；唯一 `source_head=5be472193...`；self digest、ledger count=28、ledger digest 與 live ABI 一致 | PASS |
| Governed effect route | S2.4/S2.5 hypothetical authorized route 均沒有 effect-adapter node | NOT READY |
| S2.5 effect durability | reconcile 在 hold 前；install/lifecycle lock 語義共用；release failure 無 typed outcome；journal 無完整性鏈 | NOT READY |
| S2.2B runtime attestation | `apply` 恆 `EXTERNAL_VERIFICATION_PENDING`；CLI 無 trusted observer/attestor 執行與 SSHSIG 驗證路徑 | NOT READY |
| Production effect DAG | `S2.0→S2.4→S2.5A→S2.1→S2.5B→S2.2B` 共 0/6 EFFECT_DONE | NOT STARTED |
| Linux runtime | 2026-07-28T15:55:23+02:00：兩個候選 unit 均 `not-found/inactive/dead`；`/var/lib/arcane-equilibrium/aiml` 與 `/opt/arcane-equilibrium/aiml` 均不存在 | ABSENT |
| S2 closure | 無 running/final attestation、無 runtime-compatible receipt | NOT CLOSED |

## 已完成部分復盤

1. PR #145/#146/#148/#149/#150/#151 均已 exact-head merge；相應 classified
   required checks 綠。Mac、GitHub、Linux source head 在審核起點均為
   `a7c36775d...`。
2. S2.5 已具備有價值的 closed schemas、permit/attestor profiles、replay ledger、
   lifecycle state machine、typed systemd driver abstraction、source simulations 與
   adversarial tests。此前查出的 self-digest 假信任、effect exception 裸逸、
   replay ledger 尾截斷、simulated anchor 越權等 P1 已有實質修復。
3. S2.2B 已具備 ingestion compatibility receipt 的 shape、V151-V160 全項
   fail-closed 與 S2.2A/S2.5 anchor binding；它是有效的 source contract，不是
   runtime observer。
4. W5 八件 artifacts 及 28 條 obligation ledger 可重放且內部一致。這證明 source
   投影沒有被任意手改，不能證明 ledger 中未關閉義務已完成。

## 對抗性發現

### P0：Operator packet 終態為假

Packet 同時聲稱「唯一 blocker 是 fresh authorization」與「apply 前必須完成
AMEND-1/2、S2.5 F2/F3/F4/note-1、W6/W6B obligations」。前置清單本身證偽了
終態。`S2.4-AMEND-1` 缺 dependency-refresh ingress、terminal receipt refresh
digest 與 profile threading；`S2.4-AMEND-2` 缺 plan-derived
`expected_topology`。這些都是 source work，不是外部授權。

### P0：治理 route 無法執行 effect DAG

`agent_governance_routing.py` 只註冊 S2.4/S2.5 adapter identity，現有 source route
刻意不注入 effect node；測試也明確釘住 effect adapter list 為空。尚未存在
「fresh authorization + exact intent → selected adapter → distinct postcheck →
closure binding」的 claim-gated effect route。因此授權到位也不能合規執行 packet。

### P1：S2.5 concurrency 與 durable-state 邊界未收口

- `reconcile_s2_5_journal()` 在 lifecycle hold 之前執行，兩個 applier 可先後通過
  reconcile 再依次進入效果窗。
- 同一個 `lock_probe` 同時表示 S2.4 install-lock free probe 與 S2.5 lifecycle
  hold，兩種資源/語義未被 API 分離。
- release exception 被吞掉且 release status 未進 typed outcome，無法證明鎖窗已
  正常釋放。
- journal 沒有 self-digest/hash-chain；具 state-root write 權限者可以改寫歷史，
  與長效自主 runtime 的可追溯要求不相容。

### P1：S2.2B 尚不能證明 production compatibility

CLI `build` 只消費 caller-provided observation；`apply` 恆 pending。中央 validator
只檢查 `runtime_attestor` shape/digest binding，source 文件亦明說 SSHSIG 驗證留給
未來 EFFECT session。缺少 approved remote-readonly observer、trusted-host
attestor signing/verification、identity/namespace/key/freshness 驗證及治理 route。
因此目前可防 shape mismatch，不能防 caller 自造 observation 或偽 signature 欄位。

### P1：28 條 ledger 不能在 effect intake 自動視為已解

其中 W6/W6B 仍有 startup reconcile、pre-state/prior-lineage、expiry、journal
parents、clock cross-check、attestor key separation、composite secret scanning、
`PR_SET_DUMPABLE` 等 OPEN/PARTIAL/NOT_PROVIDED 義務。每條必須在 source wave 中
關閉或由 PM 以具體風險理由正式裁決；不能把它們整批延後到 production effect。

## 校準後工程安排

| Wave | 工作 | Exit |
|---|---|---|
| `S2E.0` | 落地 AMEND-1/2；refresh identity 進 APPLY/receipt/profile；topology 只可由 signed plan derivation；收口相應 W6 設計決定 | schema/ABI/tests/negative mutations 全綠 |
| `S2E.1` | 為六段 effect DAG 建 claim-gated governance routing、adapter selection、distinct OPS postcheck 與 closure binding | authorized fixture 恰好選中正確 adapter；ordinary/source route 零 effect |
| `S2E.2` | 建 trusted-host host runners/observers，覆蓋 S2.0、S2.4、S2.5、S2.1；固定 preflight、rollback、postcheck 與 startup recovery | disposable target rehearsal 可完整 apply→rollback→postcheck，production 仍 fail closed |
| `S2E.3` | 修 S2.5 F2/F3/F4/note-1：reconcile 納入 hold、雙 lock API、typed release、journal hash chain | concurrency/crash/tamper mutations 全被殺 |
| `S2E.4` | 建 S2.2B remote-readonly observer + runtime attestor SSHSIG producer/verifier + CLI/route/closure | forged/caller-authored/stale/wrong-key evidence 全拒；valid disposable chain 可達 runtime-compatible |
| `S2E.5` | 在非 production disposable target rehearsal 全六段 DAG；逐條關閉/裁決 28 obligations；重發 operator packet | 零未解 source P0/P1，packet machine-checkable 且只剩 fresh external authority |

依賴順序：

`S2E.0 → S2E.1 → (S2E.2 ∥ S2E.3) → S2E.4 → S2E.5`

並行只允許 owned paths 與 effect manifest 互斥的 `S2E.2`/`S2E.3`，最多兩個
writer。Production effect 必須等 `S2E.5` 關閉、packet 重發及 fresh exact
Operator authorization；舊 S1 authority 與本次 source publication 均不可沿用。

## 終態規則

- `S2_EFFECT_EXECUTION_READINESS_ACTIVE`：目前狀態，仍有上述 source work。
- `BLOCKED_OPERATOR_ACTION_PACKET_READY`：只在 S2E.0-S2E.5 全部關閉、28 條義務
  無未裁決 source blocker、disposable rehearsal 完整通過、packet 重新綁定 current
  head 後成立。
- `S2_CLOSED`：只在 production 六段 effect DAG 全部產生 current
  platform/external-attested receipts，Linux runtime 真實 installed/active，且
  S2.2B runtime-compatible receipt 驗證通過後成立。

## 驗證

- 基線全量：`python3 -m pytest -q tests/structure program_code/ml_training/tests`
  → `6306 passed, 46 skipped`（693.32s）。
- 校正文檔消費者/投影守衛：8 個相關 test modules → `188 passed`（52.62s）。
- W5 八 artifacts 的 current source head、self digest、28-row obligation ledger
  與 live ABI 重算一致。
- `agent_governance.py validate`、JSON/Markdown 基礎檢查與 `git diff --check`
  需在 publication 前維持 PASS。

任何 source/CI PASS 均不得升格為 runtime PASS。
