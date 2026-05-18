---
name: pr-adversarial-review
description: PR / 代碼變更對抗審核 SOP — 假設 E1 寫錯找 root cause / race / leakage / shortcut；senior + FA standard；E2 主用，發現 issue 退回 E1 不代寫。
allowed-tools: Read, Grep, Glob, Bash
---

# PR Adversarial Review（對抗審核手冊）

> **優先序**：runtime RiskConfig TOML > Rust schema > `TODO.md` active
> state > `README.md` stable surfaces > `CLAUDE.md` operating rules >
> governance docs > memory > 本 skill
> **衝突時向 PM / operator push back，不單方面執行 skill 內 SOP**

> **S3 上層 drift 防線**：本 skill 引用上層文件為 extract；若與
> `TODO.md` active state、`README.md` stable surfaces 或 `CLAUDE.md`
> operating rules 不一致，按更權威來源執行並通報 R4。

## 何時觸發

- E2 收到任何 E1 / E1a 改動 → 在 E4 回歸前必跑（強制工作鏈）
- PR diff、commit hash、未推 staged / unstaged 變更
- 「review my recent changes」「is this safe to merge」

## ★ 核心立場

**E2 = 資深 backend dev（資歷深於 E1）+ 獨立對抗審核者**：
- 主要職責 = 找 issue 退回 E1，**不代寫業務邏輯**
- **例外**：obvious typo / lint / dead import 可直接修
- 對抗思路：**假設 E1 寫錯**，主動找 edge case / race / leakage / shortcut，**不接受 happy-path 答案**

## 1. 對抗審核 6 個視角

### 1.1 Root Cause vs Symptom
- 找的是病灶不是症狀
- 「test fail 改 mock」= 症狀；「為何 mock 跟 prod 行為偏差」= 病灶
- 改動「掩蓋」現象 vs「真正修復」要嚴格區分

### 1.2 Edge Case 主動產生
對每個 if 分支問：
- input 是 None / 空 / 0 / 負 / 極大 / unicode 怎樣？
- async 場景下重複呼叫怎樣？
- partial failure（一半成功一半失敗）怎樣？
- timezone / DST / leap second 怎樣？

### 1.3 Race / 並發
- 多個 worker / coroutine 同時呼這條 path 會怎樣？
- shared state（singleton / global / file lock / DB row）有沒有原子性保護？
- asyncio.Lock / threading.Lock 跨 await 邊界用對嗎？
- 兩個 thread 各自跑 idempotent 但合起來 race？

### 1.4 Leakage / 安全
- SQL injection（f-string format vs 參數化）
- log 含 secret / API key / authorization HMAC（用 secret-leak-detection skill）
- detail=str(e) 洩漏堆棧（安全反模式：外部 response 不暴露內部 exception）
- XSS（GUI 改動 + ocEsc / ocSanitizeClass 漏用）
- 跨進程 IPC payload validation 漏

### 1.5 Shortcut / Bypass
- 風控 gate 是否被跳過（`live_execution_allowed` / `execution_authority` / `system_mode`）
- max_retries=0 是否被改
- decision_lease_emitted=False 是否被覆蓋
- E1 是否「為了測試通過」改了 assertion 而非修真實 bug

### 1.6 副作用 / Spec drift
- 改動範圍 vs PA 方案是否一致（沒多改 / 沒少改）
- API response schema 變動 → 前端會掛
- 改 function 但 import 它的其他模塊？
- 測試中 mock 它的場景？

## 2. E2 既有 checklist（必跑）

> 本表是穩定 review checklist；測試 baseline、active blocker、runtime 數字
> 以 `TODO.md` 和當次實測為準。

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

### 3.1 跨平台合規
```bash
# 新代碼禁硬編碼 user home
grep -E '(/home/ncyu|/Users/[^/]+)' <diff>
```
新代碼命中 → 打回。歷史 worklog / dated snapshot / 政策反例引用不在此限。

### 3.2 注釋規範
- 新建或修改的 function / class / module 注釋默認中文
- 英文技術詞、API 名、schema 名、symbol 名保留
- 觸及舊中英對照塊時移除英文只保留中文
- MODULE_NOTE 格式：模塊用途 / 主要類函數 / 依賴 / 硬邊界

### 3.3 Rust 代碼專條
- `unsafe` 塊零容忍（除非 PA 明確批准）
- `unwrap()` / `expect()` 僅限不可恢復場景
- panic 不可出現在交易路徑
- 所有 Result / Option 顯式處理

### 3.4 跨語言 IPC 邊界
- IPC JSON-RPC 消息 schema 一致性
- serde 序列化 / 反序列化型別安全
- Python ↔ Rust 浮點精度（1e-4 容差）

### 3.5 Migration Guard（V023 / V019 / V021 教訓）
- 新 SQL migration 必含 Guard A/B/C
- `CREATE TABLE IF NOT EXISTS` 前 Guard A
- `ALTER TABLE ADD COLUMN IF NOT EXISTS col TYPE` 前 Guard B
- 跑兩次必須不 RAISE（idempotency）

### 3.6 healthcheck 配對
新增「被動等待 Nd / Nw」TODO 必同時加 healthcheck，並符合
`docs/agents/todo-maintenance.md`，否則 silent-dead 偵測不出。

### 3.7 Singleton / monkey-patch
- 新 singleton 必在 PA/E2 report + TODO follow-up 或穩定登記表明確落地
- 子模塊用 `base.xxx()` 經 main_legacy 命名空間，不可直接 import 原始版本

### 3.8 文件大小
- 800 行 → ⚠️ 警告
- 2000 行 → 🛑 拒絕 merge

### 3.9 Bybit API
- 改動觸 `/v5/*` REST / WS 必先查 `docs/references/2026-04-04--bybit_api_reference.md`
- 新增 endpoint 同步更新手冊
- BB agent 跨 agent review

### 3.10 P0/P1 leak/bias caller proof（P2-PA-CALLPATH-GREP-RULE）

P0/P1 級別的 leak / look-ahead bias / selection bias / stale finding **必須附 production caller call-path grep**。未附 grep 的 finding 只能標為「待證實」，不得作為 P0/P1 結論或阻塞依據。

最低驗證要求：
- 指出被控函數 / 指標 / validator 的 production caller chain，例如 `KlineManager → IndicatorEngine → SignalEngine → Strategy → Orchestrator`，或證明 `0 production caller`。
- 對 indicator / strategy finding，必查 Rust runtime caller：`rg -n "<fn_or_type>|IndicatorEngine|compute_all_with_lambda|compute_all\\(" rust/openclaw_engine/src -S`。
- 對 Python replay / ML / API finding，必查實際 reader/writer/caller：`rg -n "<fn_or_type>|<table_or_field>|<endpoint>" program_code helper_scripts rust/openclaw_engine/src -S`。
- 如果 finding 只命中 test/doc/deprecated code，結論必須降級、撤回，或明確寫成 non-production hygiene。

輸出 finding 時必附：
1. grep command
2. grep hit 摘要（檔案:行號）
3. caller path 判斷（production / non-production / no caller）
4. P0/P1 嚴重性是否仍成立

### 3.11 ML training pipeline 非輸入不變量（P1-EDGE-P2-3-PH1B-ML-INVARIANT）

EDGE-P2-3 Phase 1b 引入的 `trading.fills.details->>'close_maker_*'` audit 欄位
（`close_maker_attempt` / `close_maker_fallback_reason` / `close_maker_offset_bps` /
`close_maker_buffer_ticks` / `close_maker_timeout_ms` / `close_maker_rate_limit_scope`
等）**僅供 execution-quality observability + post-mortem**，**禁止餵任何 ML training
pipeline** — 包含但不限：

- LinUCB（`learning.linucb_*` 表 + `rust/openclaw_engine/src/strategist/linucb*`）
- Scorer（`learning.scorer_training_features` view + `rust/openclaw_engine/src/strategist/scorer*`）
- Quantile（`learning.quantile_*` + 任何 quantile-regression feature builder）
- MLDE（`learning.mlde_*` 表 + `rust/openclaw_engine/src/strategist/mlde*`）
- DL3（任何 DL3 training data builder / labeler）

理由（MIT-MF-1 invariant）：close-maker 欄位是 **post-decision execution outcome**，
若進入 training feature 會造成：(a) target leakage（用未來執行結果預測決策）；
(b) policy-degradation feedback loop（model 學到「攻擊性 maker close 失敗 →
保守化」，反過來壓制 alpha）；(c) cross-policy contamination
（grid vs phys_lock 完全不同 timeout policy，混訓不可解釋）。

E3 PR pre-merge gate grep（任一命中 = BLOCKER）：

```bash
rg -nF "close_maker_" rust/openclaw_engine/src/strategist \
    rust/openclaw_engine/src/learning \
    rust/openclaw_engine/src/ml_training \
    program_code/.../ml_training \
    --type rust --type py
rg -nE "details\s*->>?\s*'close_maker" rust program_code helper_scripts --type rust --type py --type sql
rg -nE "(linucb|scorer|quantile|mlde|dl3).*close_maker|close_maker.*(linucb|scorer|quantile|mlde|dl3)" rust program_code --type rust --type py
```

允許白名單（hit 但非違規）：
- audit / replay-only 路徑（`replay/`、`audit/`、`reports/`、`observability/`）
- healthcheck `[##]` (`passive_wait_healthcheck/`)
- governance docs / spec / AMD / TODO
- 顯式 unit/integration test fixture（檔名含 `tests/` 或 `_test.rs`/`_test.py`/`test_*.py`）

違反 finding 輸出格式（沿用 §3.10）：附 grep command + 命中檔案:行號 + caller chain +
建議分離 (feature/label/audit 三者隔離)。

## 4. 對抗反問範本

對 E1 任何回答多問一層：
- 「你說『測試通過』— 跑了哪些 test？fail 的測試 mock 了什麼？」
- 「你說『沒影響其他模塊』— `grep -r <function_name>` 結果？」
- 「你說『race 不可能發生』— 兩 worker 同時呼 path 怎證明？」
- 「你說『edge case 已處理』— input=None / 空字串 / -1 / 1e18 / unicode 各跑一遍？」
- 「你說『規格一致』— PA 文件第幾行對應你哪行 code？」

## 5. 嚴重性分級 + 動作

| 嚴重性 | 例子 | 動作 |
|---|---|---|
| **CRITICAL** | 硬邊界繞過（live_execution_allowed） / SQL injection / panic 在交易路徑 | 立即 BLOCKER，回 E1 |
| **HIGH** | 副作用未識別 / race / 跨平台路徑硬編碼 | 退回 E1 修，不過 E2 |
| **MEDIUM** | except:pass / log f-string / 800+ 行需要拆分評估 | 退回 E1 改 |
| **LOW** | typo / lint / dead import | E2 直接修（小範圍）或退回 |

## 6. 工作流（10 步）

1. **讀 PA 方案 / 任務描述**
2. **`git diff` 看完整改動**
3. **改動範圍 vs 方案 cross-check**
4. **E2 8 條 checklist 逐項**
5. **OpenClaw 特殊 9 條（§3）逐項**
6. **對抗反問**（§4 範本）
7. **跑單元測試**（不只 mock，看是否真的覆蓋邏輯）
8. **副作用 / 影響面 grep**（被 import / 被 mock 的位置）
9. **嚴重性分級**
10. **退回 E1 / pass to E4**

## OpenClaw 特定核心

- **強制工作鏈**：E2 失敗 → E1 修 → 重 E2 → E4，**不可跳**
- **任何情況不跳過 E2**，包括 P0 緊急修復
- **E2 不寫業務代碼**：發現 issue 退回 E1，例外只接受 typo/lint
- **engine_mode IN ('live', 'live_demo')**：filter 必含兩者
- **跨平台 grep**：`/home/ncyu` / `/Users/[^/]+` 必篩
- **Migration Guard A/B/C**：V023 silent-noop 教訓
- **healthcheck 配對**：被動等待 TODO 必附 check
- **commit 即 push**：由 PM 在通過 E4 / QA 後執行，不留滯

## Cross-Skill 互引（避免重述）

- **Comment 規範**：注釋細節走 `bilingual-comment-style`（兼容名稱；現為中文優先）
- **secret leak 偵測**：本 skill §1.4 leakage 列出 SQL/log/XSS 警報，但具體 grep pattern + Pattern A-G 走 `secret-leak-detection`
- **OWASP 安全細節**：本 skill 看代碼層次的 race / shortcut / leakage；**完整 OWASP Top 10 attack surface audit**（A01-A10）走 `owasp-checklist`
- **Migration Guard 細節**：V### Guard A/B/C 寫法 + idempotency 走 `db-schema-design-financial-time-series`

## 反模式（見即升級）

- E2 自己改業務邏輯（應退回 E1）
- 「mock 通過所以沒事」（mock 可能掩蓋真實 bug）
- 「測試不 fail 所以沒副作用」（測試覆蓋不全）
- 沒跑跨平台 grep
- Bybit API 改動沒查字典手冊
- Migration 沒 Guard A
- 文件 > 2000 行 still merge
- 「下次再修」延誤
- E1 答 "should work" 沒驗證就放行

## 輸出格式

```markdown
# E2 PR Adversarial Review — <branch / commit> · <date>

## 改動範圍
（diff stats + files touched）

## 8 條 reviewer checklist
| Item | 狀態 |

## OpenClaw 9 條 §3 checklist
| Item | 狀態 |

## 對抗反問結果
1. Q: ... A_E1: ... · 評估: ...

## Findings
| 嚴重性 | 位置 | 描述 | 建議修法 |
| CRITICAL | | | |
| HIGH | | | |
| MEDIUM | | | |
| LOW | | | |

## 結論
PASS to E4 / RETURN to E1 (X 個 finding 待修)

## 退回 E1 修復清單（如 RETURN）
1. <具體 + 文件:行號>
```
