> ⚠️ 归档历史文档 — 非当前权威。active 状态见 repo 根 `TODO.md`；本文件仅供历史/审计参考。（2026-07-18 审计批量补入）

# Sprint 1A Dispatch Packet — v5.7 派發 brief（C7+C10+C11+C12 整合）

**日期**：2026-05-21
**狀態**：DRAFT — Sprint 1A 派發前置條件（v57-C7 + C10 + C11 + C12 四條 PM hands-on 整合）
**主檔**：[`docs/execution_plan/2026-05-20--execution-plan-v5.7.md`](2026-05-20--execution-plan-v5.7.md)
**配套 spec**（並行 sub-agent 起草中）：
- v57-C2 ADR 順移 0030/0031/0032 + ADR-0033（TW dispatch；歸位 `srv/docs/adr/`）
- v57-C3 V103/V104 schema spec（MIT dispatch；`docs/execution_plan/2026-05-21--v103_v104_earn_hypotheses_schema_spec.md`）
- v57-C4 + C5 + C6 Bybit Earn endpoint / scope / 8a-C1 verdict（BB dispatch；`docs/CCAgentWorkSpace/BB/workspace/reports/2026-05-21--v57_c4_c5_c6_bybit_verdict.md`）
- v57-C8 Earn governance spec（CC dispatch；`docs/execution_plan/2026-05-21--earn_governance_spec.md`）
- v57-C9 V103/V104 Linux PG empirical dry-run（PA dispatch；`docs/execution_plan/2026-05-21--v103_v104_linux_pg_dry_run.md`）

**v5.7 主檔 frozen**（per PM signoff §七）：修補項以本 dispatch packet + 配套 spec 獨立呈現，**不改主檔**。

---

## §1 v57-C7 Sprint 1B C10 reframe — Stage 0R + Stage 1 Demo（不寫 mainnet live $2,000）

### §1.1 原 v5.7 §8 Sprint 1B 寫法（被 reframe）

```
Sprint 1B — C10 + Earn Live + Alpha Tournament Prep (Week 1.5-3)
- C10 minimal viable on 主帳 $2,000   <-- 違 v5.6 §12 Stage gate + AMD-2026-05-15-01
- Earn governance policy + first small manual stake $200-400
- Alpha Tournament dataset readiness check
- Pre-registration table seeded with strategy candidates
- Engineering: 50-70 hr
```

### §1.2 reframe 後（C7 落地）

```
Sprint 1B — C10 Stage 0R Replay Preflight + Stage 1 Demo Micro-Canary + Earn Demo + Alpha Tournament Prep
（Week 1.5-3；mainnet live $2,000 落 Sprint 3-4，待 P0-EDGE-1 + P0-LG-3 + P0-OPS-1..4 全 closed）

- C10 Stage 0R replay preflight：
  - replay engine 跑 C10 strategy 對 spot leg 假設（replay-backed synthetic accounting；不啟動 paper engine）
  - eligible_for_demo_canary=true/false verdict（per AMD-2026-05-15-01）
  - 若 PASS → 進 Stage 1 Demo；若 FAIL → 凍結 C10 + 派 PA review
- C10 Stage 1 Demo Micro-Canary：
  - 1 strategy × 1 symbol × Demo endpoint × 7d
  - spot leg 使用 replay-backed synthetic accounting sidecar（Bybit demo 不支援 spot lending；per memory funding_arb_v2 教訓 + funding_arb V2 retired per AMD-2026-05-26-01 終結 lesson），不得用 `OPENCLAW_ENABLE_PAPER=1` 當 promotion path
  - Demo USDT $200-500 cap（不寫 mainnet live $2,000）
- Earn governance + first small manual stake：
  - Demo endpoint 試運行（待 BB C4 verdict 確認 demo 是否支援 Earn）
  - 若 demo 不支援 → 落 Sprint 3-4 Stage 4 mainnet live（嚴於 trading mainnet=1 gate per §4 governance spec）
  - 不寫 live $200-400 stake
- Alpha Tournament dataset readiness check：unchanged
- Pre-registration table seeded with strategy candidates：unchanged
- Engineering: 65-85 hr（per C10 工時上修）
```

### §1.3 Stage 真實 live 排程

| Stage | 觸發點 | Sprint 落點 | 條件 |
|---|---|---|---|
| Stage 0R | C10 進 Sprint 1B 開頭 | Sprint 1B W1.5 | replay engine ready + spot leg paper sim 完成 |
| Stage 1 Demo | Stage 0R PASS | Sprint 1B W2.5 | 1×1×Demo×7d；$200-500 cap |
| Stage 2 Demo extended | Stage 1 7d PASS | Sprint 2 末 | 14d；Demo |
| Stage 3 Demo full | Stage 2 14d PASS | Sprint 3 末 | 21d；Demo |
| **Stage 4 LIVE_PENDING** | Stage 3 21d PASS + P0-EDGE-1/LG-3/OPS-1..4 closed | **Sprint 3-4 之後** | mainnet=1 + 5-gate full + Operator approve |

### §1.4 acceptance criteria（C7 落地驗收）

- [ ] Sprint 1B 派發 brief 明文標示 "no mainnet live $2,000 in Sprint 1B"
- [ ] C10 工時 50-70 → 65-85 hr 上修（per C10）
- [ ] Stage 真實 live 排程表 land
- [ ] AMD-2026-05-15-01 cross-ref 寫入 brief
- [ ] 待 BB C4 verdict 後 finalize Earn demo 路徑

---

## §2 v57-C10 工時上修 + §9 並行 sub-agent mandate

### §2.1 v5.7 §9 工時上修（per 9/14 agent CRITICAL 共識 + 2026-05-21 PM 仲裁 2 reconcile）

**PM 仲裁 2 決議**（per `docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-21--v57_12_prefix_pm_signoff.md` §二仲裁 2）：採 **PA 中間值 75-105 hr**（含 BB C6 推翻 v57 audit Risk 1 後 §6 工時減 15-20 hr 反映 + GUI / 5 並行 track / 字典補錄 buffer）。

| Sprint | v5.7 §9 原估 | **PM 仲裁決議** | 變動 |
|---|---|---|---|
| 1A | 60-80 hr | **75-105 hr** | +15-25 hr（含 ADR draft + spec land + 4 sensor pre-review + GUI 8-12 hr + BB §6 healthcheck-only 路徑 -15-20 hr）|
| 1B | 50-70 hr | **65-85 hr** | +15 hr（C10 Stage 0R + Earn governance e2e + Stage gate 補位）|
| 2 | 110-150 hr | **140-200 hr** | +30-50 hr（Alpha Tournament + microstructure + on-chain counterfactual 規格）|
| 3 | 130-160 hr | **145-180 hr** | +15-20 hr（Top-1 build buffer）|
| 4 | 160-210 hr | **185-245 hr** | +25-35 hr（Top-1 live + Options Stack 1 拆 module）|
| 5-10 合計 | 580-790 hr | **660-880 hr** | +80-90 hr（GUI + TW + LLM API buffer）|
| **Total Y1** | **1,190-1,590 hr** | **1,275-1,710 hr** | **+85-120 hr（保守 ~1.08x；BB C6 推翻 v57 audit 後反估減；含 GUI 104-151 hr / TW 68-95 hr / Apple CI buffer）**|

**不含**：LLM API cost ~$365-565/yr（per AI-E H7；單列）。

### §2.2 §9 並行 sub-agent mandate

**Calendar 39 週硬約束 + 工時 1,295-1,740 hr → 必須 50-60% workload 走並行 sub-agent dispatch**，否則 calendar 不可達。

逐 Sprint 並行 mandate：

| Sprint | 並行 track 數 | sub-agent 數 / track | 並行 mandate % |
|---|---|---|---|
| 1A | 5 並行（gov / schema / sensor / earn / gui） | 1-4（sensor track 最多 4 E1） | **50-60%** |
| 1B | 3 並行（C10 Stage 0R / Earn / Alpha Tournament） | 1-2 | **40-50%** |
| 2 | 4 並行（Tournament / microstructure / on-chain / regime） | 2-3 | **50-60%** |
| 3-7 | 3-5 並行（Top-N build + Options + Allocator） | 2-3 | **50-60%** |
| 8-10 | 2-3 並行（Decay / Discovery / Copy Trading） | 1-2 | **40-50%** |

**enforcement**：
- 每 Sprint 派 PA 寫 dispatch packet 時必標 "並行 track 矩陣 + sub-agent 數量"
- PM watch：若 wall-clock vs estimate slip > 20%，加派 sub-agent 補
- E5 baseline profiling（Sprint 1A 前置）必跑：H0/tick/IPC P50/P95/P99 + RAM/CPU/PG buffer

### §2.3 LLM API cost 列入 §9（per AI-E H7）

- Y1 LLM API ~$365-565（counterfactual logger 把 ContextDistiller token 從 520 → 700-900）
- Layer 2 manual+supervisor-only（per ADR-0020 permanent dormant，**不解**）
- Layer 1 自動 vs Layer 2 manual 釐清：counterfactual logger = Layer 1 Ollama L1 9B（自動 + ledger）；不觸發 Layer 2

### §2.4 acceptance criteria（C10 落地驗收）

- [ ] Sprint 1A 60-80 → 90-130 hr 寫入 dispatch brief
- [ ] Sprint 1B 50-70 → 65-85 hr 寫入 dispatch brief
- [ ] Y1 total 1,190-1,590 → 1,295-1,740 hr 寫入 dispatch brief
- [ ] §9 並行 sub-agent mandate 50-60% workload 列明
- [ ] LLM API cost $365-565/yr 單列
- [ ] E5 baseline profiling Sprint 1A 前置 land

---

## §3 v57-C11 Apple Silicon CI tuple 條款

### §3.1 acceptance criteria（per 2026-05-21 PM 仲裁 5 雙軌條款）

**PM 仲裁 5 決議**（per signoff §二仲裁 5）：採 PA 雙軌條款（hard gate + soft enforce）。

**Hard gate（Sprint 1A 派發 sub-agent 必過）**：
```bash
cd rust/openclaw_engine
cargo check --target aarch64-apple-darwin --release        # ✅ smoke PASS 12 sec
cargo check --target aarch64-apple-darwin --tests          # ✅ test build PASS
```

**Soft enforce（新 crate 必過；既有 17 errors 標 P2 ticket 並行清）**：
```bash
cargo clippy --target aarch64-apple-darwin -- -D warnings  # 新 crate 必過
# 既有 17 errors 由 P2-CLIPPY-CLEANUP-1（owner E1 / 4-6 hr / Sprint 1A 進行中可並行清）
```

**新增 P2 ticket**：`P2-CLIPPY-CLEANUP-1`（既有 17 clippy errors 修；owner E1；Sprint 1A 進行中並行補；不阻塞 dispatch）

**PyO3 features**：
```bash
cargo check --target aarch64-apple-darwin --features pyo3  # 新 crate 涉 PyO3 時必跑
```

### §3.2 PA sub-agent prompt 注入規範

每 Sprint 1A 派 sub-agent 任務 brief 必含：

```
**Apple Silicon CI mandate**：
- 新增/修改 Rust crate 提交前必跑 `cargo check --target aarch64-apple-darwin --release`
- 不依賴 Linux-only feature flag（如 epoll-only），優先用 cross-platform abstraction
- 若必須 Linux-only → 標 `#[cfg(target_os = "linux")]` 並列 Mac fallback path
- E2 review checklist 加 "Apple Silicon target check PASS" 確認步驟
```

### §3.3 E3 review checklist 補位

E3 review Rust unsafe / FFI boundary 加：
- `aarch64-apple-darwin` target build PASS
- 不引入 x86_64-only intrinsic（無 SSE/AVX hard-code）
- PyO3 binding 在 Apple Silicon CPython 跑通

### §3.4 acceptance criteria（C11 落地驗收）

- [ ] Sprint 1A 5 sub-agent task brief 全含 Apple Silicon mandate
- [ ] E2 review checklist 加 target check step
- [ ] E3 unsafe / FFI review 加 ARM64 verify

---

## §4 v57-C12 中文注釋 mandate + SCRIPT_INDEX.md enforce

### §4.1 中文注釋 mandate（per 2026-05-05 mandate）

**新代碼 / 新文檔注釋默認只寫中文**：

- 新增 Rust `//` / `///` 注釋 → 中文
- 新增 Python `"""docstring"""` → 中文
- 新增 SQL migration 注釋 → 中文
- 新增 TOML / YAML 配置注釋 → 中文
- 既有中英對照注釋不主動清；修改既有區塊時移除英文留中文
- E2 不再要求英文版

**保留原文**：
- Code identifier（函式名 / 變數名 / class 名）
- Technical term（API endpoint / SHA / git ref / commit subject 慣例）
- 引用 ADR 編號 / spec name / table name / column name

### §4.2 SCRIPT_INDEX.md enforce

新 script / 新 helper / 新 healthcheck 必更新 `srv/helper_scripts/SCRIPT_INDEX.md`：

- 列 script path
- 列 用途（中文）
- 列 invocation example
- 列 dependent module
- 列 update date

**E2 review enforcement**：
```bash
# E2 review 加此步
NEW_FILES=$(git diff --name-only HEAD~1 HEAD | grep '^helper_scripts/.*\.py$')
for f in $NEW_FILES; do
  if ! grep -q "$f" srv/helper_scripts/SCRIPT_INDEX.md 2>/dev/null; then
    echo "FAIL: $f missing from SCRIPT_INDEX.md"
    exit 1
  fi
done
```

### §4.3 新 module MODULE_NOTE 要求

新 Rust / Python module 檔頭加 `MODULE_NOTE`（中文）或 `模塊用途`（中文）：

```rust
// MODULE_NOTE：本模塊負責 X / Y / Z；上游 ↔ 下游；不變式：……
// 注意事項：……
```

```python
"""模塊用途：本模塊負責 X / Y / Z
上游 ↔ 下游：……
不變式：……
注意事項：……
"""
```

**E2 review check**：
```bash
# E2 review 加 `rg -L 'MODULE_NOTE|模塊用途' <new-files>` = 0 hit PASS
rg -L 'MODULE_NOTE|模塊用途' $(git diff --name-only HEAD~1 HEAD | grep -E '\.(rs|py)$')
# 若有 file 在輸出 → FAIL
```

### §4.4 acceptance criteria（C12 落地驗收）

- [ ] Sprint 1A 5 sub-agent task brief 全標 "注釋默認只寫中文 per 2026-05-05 mandate"
- [ ] E2 review checklist 加 SCRIPT_INDEX 更新檢查 + MODULE_NOTE grep
- [ ] 既有 SCRIPT_INDEX.md head 不破壞既有條目
- [ ] 既有 bilingual 注釋不主動清

---

## §5 D-1 prerequisite check list 對應（per PA §9.3）

| # | Check | 對應 C# | 狀態 |
|---|---|---|---|
| 1 | TODO §-0 填入 v5.7 為當前路線 + 解除 V101/V102 Hard precondition | (D6 暫不批 — 不執行) | □ 暫不執行 |
| 2 | v5.7 主檔搬 docs/execution_plan/ + 進 git tree | C1 | ✅ 2026-05-21（git rename detected） |
| 3 | ADR 編號順移 0030/0031/0032 + ADR-0033 | C2 | ⏳ TW sub-agent in flight |
| 4 | V103/V104 schema spec land | C3 | ⏳ MIT sub-agent in flight |
| 5 | Bybit Earn API endpoint verdict | C4 | ⏳ BB sub-agent in flight |
| 6 | Bybit Earn API key scope 驗證 | C5 | ⏳ BB sub-agent in flight |
| 7 | W-AUDIT-8a-C1 24h proof verdict 收口 | C6 | ⏳ BB + MIT sub-agent in flight |
| 8 | Sprint 1B C10 改 Stage 0R + Stage 1 Demo | **C7** | ✅ §1 本檔落地 |
| 9 | Earn governance spec land | C8 | ⏳ CC sub-agent in flight |
| 10 | Linux PG empirical dry-run query 附 V103/V104 spec | C9 | ⏳ PA sub-agent in flight |
| 11 | Sprint 1A 工時上修 + §9 並行 sub-agent mandate | **C10** | ✅ §2 本檔落地 |
| 12 | Apple Silicon CI tuple 條款 + 中文注釋 mandate | **C11 + C12** | ✅ §3 + §4 本檔落地 |

**11/12 落地進度**：C1 + C7 + C10 + C11 + C12 由 PM 本回合落地（5 條）；C2 + C3 + C4 + C5 + C6 + C8 + C9 由 7 個並行 sub-agent 起草（7 條）。

**D6 暫不批准**：§1 路線變更區 + V101/V102 Hard precondition 維持原狀（per operator 2026-05-21 D6 拍板）。

---

## §6 派發前最終 checklist（給 PM 驗收）

完成全部 12 條 prefix 後 PM 驗收項：

- [ ] C1 ✅ v5.7 主檔 in git tree（`git status` confirm rename detected）
- [ ] C2 ⏳ 4 ADR draft land in `docs/adr/`（TW report verdict）
- [ ] C3 ⏳ V103/V104 spec land in `docs/execution_plan/`（MIT report verdict）
- [ ] C4 ⏳ Bybit Earn endpoint 三選一結論明示（BB report verdict）
- [ ] C5 ⏳ Earn API key scope 三選一結論明示（BB + E3 report verdict）
- [ ] C6 ⏳ liquidation writer PROOF 三選一結論明示（BB + MIT report verdict）
- [ ] C7 ✅ Sprint 1B C10 Stage 0R + Stage 1 Demo reframe（本檔 §1）
- [ ] C8 ⏳ Earn governance spec land in `docs/execution_plan/`（CC report verdict）
- [ ] C9 ⏳ V103/V104 PG dry-run report land（PA report verdict）
- [ ] C10 ✅ 工時上修 + §9 sub-agent mandate（本檔 §2）
- [ ] C11 ✅ Apple Silicon CI tuple（本檔 §3）
- [ ] C12 ✅ 中文注釋 + SCRIPT_INDEX + MODULE_NOTE mandate（本檔 §4）

**FA + PA 核實 + PM 驗收後**：commit + push origin + ssh trade-core fast-forward。

---

## §7 References

- v5.7 主檔：[`docs/execution_plan/2026-05-20--execution-plan-v5.7.md`](2026-05-20--execution-plan-v5.7.md)
- PA dispatch consolidation：[`docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-21--v57_dispatch_consolidation.md`](../CCAgentWorkSpace/PA/workspace/reports/2026-05-21--v57_dispatch_consolidation.md)
- FA business consolidation：[`docs/CCAgentWorkSpace/FA/workspace/reports/2026-05-21--v57_business_consolidation.md`](../CCAgentWorkSpace/FA/workspace/reports/2026-05-21--v57_business_consolidation.md)
- PM signoff：[`docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-21--v57_pm_signoff.md`](../CCAgentWorkSpace/PM/workspace/reports/2026-05-21--v57_pm_signoff.md)
- AMD-2026-05-15-01（Stage 0R replay preflight + Demo micro-canary）
- 2026-05-05 中文注釋 mandate（per memory `feedback_chinese_only_comments.md`）
- ADR-0020（Layer 2 manual+supervisor-only permanent dormant）

---

**dispatch packet DONE** — Sprint 1A 派發前置條件 C1 / C7 / C10 / C11 / C12（5 條 PM hands-on）落地；C2 / C3 / C4 / C5 / C6 / C8 / C9（7 條並行 sub-agent）待回報整合。
