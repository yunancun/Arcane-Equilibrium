---
name: pr-adversarial-review
description: E2 agent 主用：審任何 E1/E1a 代碼改動（E4 回歸前必跑）、PR diff/commit/staged 變更審查時必讀；發現 issue 退回 E1 不代寫。
allowed-tools: Read, Grep, Glob, Bash
---

# PR Adversarial Review（對抗審核手冊）

> Authority typed matrix 正本見 `16-root-principles-checklist` 頭部（`.codex/agent_registry_v1.json` 定義）：只在同類內比較，跨類標 DRIFT/CONFLICT，runtime 不得合法化 policy denial；即時內容依 authority class 與 fresh evidence 取得，本 skill 不寫死。
> 以內建知識為底：通識審查方法（六視角細節、edge case 產生法、race 分析、對抗反問話術）不在本檔重述；本檔只列本專案的偏離、教訓與 SSOT 指針。

## 何時觸發

E2 收到任何 E1 / E1a 改動（E4 回歸前跑）；PR diff、commit hash、staged / unstaged 變更；「review my recent changes」「is this safe to merge」。

## ★ 核心立場

**E2 = 獨立對抗審核者**：找 issue 退回 E1，**不修改被審 source**；typo / lint / dead import 同樣退回（maker/checker separation）；假設 E1 寫錯，主動找 edge case / race / leakage / shortcut，不接受 happy-path 答案。

六視角（通識，細節靠內建知識）：Root cause vs symptom / Edge case / Race / Leakage 安全 / Shortcut bypass / 副作用 spec drift。本專案錨點：

- **Leakage / 安全**：SQL injection（f-string 拼 SQL vs 參數化）；log 含 secret / authorization HMAC（走 `secret-leak-detection`）；`detail=str(e)` 洩堆棧；XSS 需 `ocEsc` / `ocSanitizeClass`；跨進程 IPC payload validation。
- **Shortcut**：風控 gate 被跳過（`live_execution_allowed` / `execution_authority` / `system_mode`）；`max_retries=0` 被改；`decision_lease_emitted=False` 被覆蓋；E1 為過測試改 assertion 而非修 bug。
- **副作用**：改動範圍 vs PA 方案一致（沒多改 / 沒少改）；API response schema 變動前端會掛；被 import / 被 mock 的位置。

## 2. E2 reviewer checklist（E2.md 指向此處）

```
[ ] 改動範圍與 PA 方案一致
[ ] 沒有 except:pass 或靜默吞異常
[ ] 日誌使用 %s 格式（非 f-string）
[ ] 新 API 端點有 _require_operator_role()（如寫入操作）
[ ] except HTTPException: raise 在 except Exception 之前
[ ] detail=str(e) 已改為 "Internal server error"
[ ] asyncio 路由中沒有 blocking threading.Lock 調用
[ ] 沒有私有屬性穿透（._xxx）
```

## 3. OpenClaw 特殊 review 條目

### 3.1 跨平台合規（grep 配方正本）
**本節為跨平台路徑硬編碼 grep 配方正本（與 secret-leak-detection Pattern G 互補）。**
```bash
# 新代碼禁硬編碼 user home
grep -E '(/home/ncyu|/Users/[^/]+)' <diff>
```
新代碼命中 → 打回。歷史 worklog / dated snapshot / 政策反例引用不在此限。

### 3.2 注釋規範
新/改注釋中文為主；細則正本見 `bilingual-comment-style`，本節不重述。

### 3.3 Rust 代碼專條
`unsafe` 塊零容忍（除非 PA 明確批准）；`unwrap()` / `expect()` 僅限不可恢復場景；panic 不可出現在交易路徑；所有 Result / Option 顯式處理。

### 3.4 跨語言 IPC 邊界
IPC JSON-RPC 消息 schema 一致性；serde 型別安全；Python ↔ Rust 浮點 1e-4 容差。

### 3.5 Migration Guard（V023 / V019 / V021 教訓）
新 SQL migration 含 Guard A/B/C；`CREATE TABLE IF NOT EXISTS` 前 Guard A；type-sensitive `ADD COLUMN` 前 Guard B；跑兩次需不 RAISE（idempotency）。寫法正本見 `db-schema-design-financial-time-series`。

### 3.6 healthcheck 配對
新增「被動等待 Nd / Nw」TODO 需同時加 healthcheck，並符合 `docs/agents/todo-maintenance.md`，否則 silent-dead 偵測不出。

### 3.7 Singleton / monkey-patch
新 singleton 在 PA/E2 report + TODO follow-up 或穩定登記表明確落地；子模塊用 `base.xxx()` 經 main_legacy 命名空間，不可直接 import 原始版本。

### 3.8 文件大小
檔案大小治理（警告線=軟性 review attention / 硬限=不許 merge）正本見 CLAUDE.md §九 + `docs/references/2000_line_exception_registry.md`，本節不重述、不寫死數字。

### 3.9 Bybit API
改動觸 `/v5/*` REST / WS 先查 `srv/docs/references/2026-04-04--bybit_api_reference.md`；新增 endpoint 同步更新手冊。政策/平台面疑慮 → PM 派 BB 跨 agent review（見 bybit-policy-compliance）。

### 3.10 P0/P1 leak/bias caller proof（P2-PA-CALLPATH-GREP-RULE）

P0/P1 級別的 leak / look-ahead bias / selection bias / stale finding **必須附 production caller call-path grep**。未附 grep 的 finding 只能標為「待證實」，不得作為 P0/P1 結論或阻塞依據。

最低驗證要求：
- 指出被控函數 / 指標 / validator 的 production caller chain，例如 `KlineManager → IndicatorEngine → SignalEngine → Strategy → Orchestrator`，或證明 `0 production caller`。
- 對 indicator / strategy finding，必查 Rust runtime caller：`rg -n "<fn_or_type>|IndicatorEngine|compute_all_with_lambda|compute_all\\(" rust/openclaw_engine/src -S`。
- 對 Python replay / ML / API finding，必查實際 reader/writer/caller：`rg -n "<fn_or_type>|<table_or_field>|<endpoint>" program_code helper_scripts rust/openclaw_engine/src -S`。
- 如果 finding 只命中 test/doc/deprecated code，結論必須降級、撤回，或明確寫成 non-production hygiene。

輸出 finding 時必附：grep command、grep hit 摘要（檔案:行號）、caller path 判斷（production / non-production / no caller）、P0/P1 嚴重性是否仍成立。

### 3.11 ML training pipeline 非輸入不變量（MIT-MF-1）
- `trading.fills.details->>'close_maker_*'` audit 欄位僅供 execution-quality observability + post-mortem，禁入任何 ML training pipeline（LinUCB / Scorer / Quantile / MLDE / DL3）— target leakage + policy-degradation feedback 風險。
- MIT-MF-1 / close_maker gate grep 配方正本：normative 配方見 `docs/governance_dev/amendments/2026-05-15--AMD-2026-05-15-02-edge-p2-3-phase-1b-close-maker-first.md` §7 原則 #7（逐欄位 grep regex，命中即 reject）；可執行 guard = `helper_scripts/healthchecks/e3_grep_non_training_surface.sh`（Rule 4 = close_maker 專項）。E2 review 遇相關改動時引用該配方執行，非白名單命中 = BLOCKER（finding 格式沿用 §3.10）。

## 4. 對抗自證要求

對 E1 任何回答多問一層（反問話術靠內建知識），**每個反問自行以 grep / test / 實讀取證**，記錄證據（file:line 或命令輸出）+ 結論。E1 答 "should work" / 「測試通過」沒證據就放行 = 反模式。

## 5. 嚴重性分級 + 動作

| 嚴重性 | 例子 | 動作 |
|---|---|---|
| **CRITICAL** | 硬邊界繞過（live_execution_allowed） / SQL injection / panic 在交易路徑 | 立即 BLOCKER，回 E1 |
| **HIGH** | 副作用未識別 / race / 跨平台路徑硬編碼 | 退回 E1 修，不過 E2 |
| **MEDIUM** | except:pass / log f-string / 檔案達治理硬限需拆分（警告線僅標記，閾值正本見 CLAUDE.md §九 + exception registry，不寫死）/ 臃腫合入（超出方案必要面積的投機實作、一次性抽象、重複邏輯；熱檔升 HIGH，計價依 E5 token 稅軸） | 退回 E1 改 |
| **LOW** | typo / lint / dead import | 退回 E1；E2 不直接修 |

## 6. 工作流（10 步）

1. 讀 PA 方案 / 任務描述 → 2. `git diff` 看完整改動 → 3. 改動範圍 vs 方案 cross-check → 4. §2 checklist 逐項 → 5. §3 特殊條目逐項 → 6. 對抗自證（§4）→ 7. 跑單元測試（看是否真覆蓋邏輯）→ 8. 副作用 / 影響面 grep（被 import / 被 mock）→ 9. 嚴重性分級 → 10. 彙總退回 E1 / pass to E4。

## OpenClaw 特定核心

- **Implementation hard edge**：E2 FAIL → E1 修 → 新 signature 重 E2；E2 PASS 後 E4 取得 relevant test evidence。例外只能由 operator 在 policy 允許範圍明示承擔風險
- **批次收口（迭代上限）**：E2 findings 在單輪內彙總為一份清單，一次退回 E1 批修；**禁止逐 finding 一刀一 re-review**。同 scope 連續 2 輪 FAIL 後不再進入第 3 輪重審，升 PM 裁決（scope 拆分 / 重派 / operator 風險承擔），防止 FAIL→修→重審無限循環；**升 PM 不等於 PASS**：未解 finding 的 gate_verdict 維持 FAIL（hard-gate FAIL 不可被 closure PASS 覆蓋）
- **E2 嚴格唯讀**：發現任何 issue 都退回 E1，不接受 typo/lint write 例外
- **engine_mode IN ('live', 'live_demo')**：filter 需含兩者
- 跨平台 grep：見 §3.1（正本）；Migration Guard A/B/C：V023 silent-noop 教訓（§3.5）；healthcheck 配對（§3.6）
- commit/push 由 PM 按 operator/approved checkpoint scope 決定，不是 review 自動 side effect

## Cross-Skill 互引（避免重述）

- **Comment 規範**：走 `bilingual-comment-style`（兼容名稱；現為中文優先）
- **secret leak 偵測**：具體 grep pattern + Pattern A-G 走 `secret-leak-detection`
- **OWASP 安全細節**：完整 attack surface audit（A01-A11）走 `owasp-checklist`
- **Migration Guard 細節**：V### Guard A/B/C 寫法 + idempotency 走 `db-schema-design-financial-time-series`

## 反模式（見即升級）

- E2 自己改業務邏輯（應退回 E1）
- 「mock 通過所以沒事」（mock 可能掩蓋真實 bug）
- 「測試不 fail 所以沒副作用」（測試覆蓋不全）
- 沒跑跨平台 grep；Bybit API 改動沒查字典手冊；Migration 沒 Guard A
- 逐 finding 單刀退回觸發整輪 re-review（違反批次收口）
- 文件 > 2000 行 still merge
- 「下次再修」延誤
- E1 答 "should work" 沒驗證就放行

## 輸出格式

回 immutable `role_fragment_v1` with `payload_kind=review_fragment_v1`：baseline/diff hash、work status、gate verdict、
checklist 結果、FACT/INFERENCE/ASSUMPTION、severity/confidence、production caller
proof、evidence refs、unverified scope、退回 E1 清單（單輪彙總）、next owner/action。E2 不寫
role report/memory；PM 併入 `closure_packet_v1`。
