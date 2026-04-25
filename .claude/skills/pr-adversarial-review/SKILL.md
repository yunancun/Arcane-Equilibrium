---
name: pr-adversarial-review
description: PR / 代碼變更對抗審核 SOP — 假設 E1 寫錯找 root cause / race / leakage / shortcut；senior + FA standard；E2 主用，發現 issue 退回 E1 不代寫。
allowed-tools: Read, Grep, Glob, Bash
---

# PR Adversarial Review（對抗審核手冊）

> **優先序**：runtime RiskConfig TOML > Rust schema > CLAUDE.md > 治理 .md > memory > 本 skill
> **衝突時向 PM / operator push back，不單方面執行 skill 內 SOP**

## 何時觸發

- E2 收到任何 E1 / E1a 改動 → 在 E4 回歸前必跑（強制工作鏈，CLAUDE.md §八）
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
- detail=str(e) 洩漏堆棧（CLAUDE.md §九 SEC-04）
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

## 2. CLAUDE.md §九 E2 既有 checklist（必跑）

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

### 3.1 跨平台合規（CLAUDE.md §七 ★★）
```bash
# 新代碼禁硬編碼 user home
grep -E '(/home/ncyu|/Users/[^/]+)' <diff>
```
新代碼命中 → 打回。歷史 worklog / dated snapshot / 政策反例引用不在此限。

### 3.2 雙語注釋（CLAUDE.md §七）
- 每個新建 / 修改的 function / class / module 必須中英對照
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
- 新 SQL migration 必含 Guard A/B/C（CLAUDE.md §七）
- `CREATE TABLE IF NOT EXISTS` 前 Guard A
- `ALTER TABLE ADD COLUMN IF NOT EXISTS col TYPE` 前 Guard B
- 跑兩次必須不 RAISE（idempotency）

### 3.6 healthcheck 配對（CLAUDE.md §七）
新增「被動等待 Nd / Nw」TODO 必同時加 `passive_wait_healthcheck.py` check_X()，否則 silent-dead 偵測不出。

### 3.7 Sigleton / monkey-patch（CLAUDE.md §九）
- 新 singleton 必登記 §九 表
- 子模塊用 `base.xxx()` 經 main_legacy 命名空間，不可直接 import 原始版本

### 3.8 文件大小（CLAUDE.md §九）
- 800 行 → ⚠️ 警告
- 1200 行 → 🛑 拒絕 merge

### 3.9 Bybit API（CLAUDE.md §八）
- 改動觸 `/v5/*` REST / WS 必先查 `docs/references/2026-04-04--bybit_api_reference.md`
- 新增 endpoint 同步更新手冊
- BB agent 跨 agent review

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
| **MEDIUM** | except:pass / log f-string / 800-1200 行 | 退回 E1 改 |
| **LOW** | typo / lint / dead import | E2 直接修（小範圍）或退回 |

## 6. 工作流（10 步）

1. **讀 PA 方案 / 任務描述**
2. **`git diff` 看完整改動**
3. **改動範圍 vs 方案 cross-check**
4. **CLAUDE.md §九 8 條 checklist 逐項**
5. **OpenClaw 特殊 9 條（§3）逐項**
6. **對抗反問**（§4 範本）
7. **跑單元測試**（不只 mock，看是否真的覆蓋邏輯）
8. **副作用 / 影響面 grep**（被 import / 被 mock 的位置）
9. **嚴重性分級**
10. **退回 E1 / pass to E4**

## OpenClaw 特定核心

- **強制工作鏈**：E2 失敗 → E1 修 → 重 E2 → E4，**不可跳**（CLAUDE.md §八）
- **任何情況不跳過 E2**，包括 P0 緊急修復
- **E2 不寫業務代碼**：發現 issue 退回 E1，例外只接受 typo/lint
- **engine_mode IN ('live', 'live_demo')**：filter 必含兩者
- **跨平台 grep**：`/home/ncyu` / `/Users/[^/]+` 必篩
- **Migration Guard A/B/C**：V023 silent-noop 教訓
- **healthcheck 配對**：被動等待 TODO 必附 check
- **commit 即 push**（CLAUDE.md §七 git 自動化）：E2 通過後 push 不滯留

## 反模式（見即升級）

- E2 自己改業務邏輯（應退回 E1）
- 「mock 通過所以沒事」（mock 可能掩蓋真實 bug）
- 「測試不 fail 所以沒副作用」（測試覆蓋不全）
- 沒跑跨平台 grep
- Bybit API 改動沒查字典手冊
- Migration 沒 Guard A
- 文件 > 1200 行 still merge
- 「下次再修」延誤
- E1 答 "should work" 沒驗證就放行

## 輸出格式

```markdown
# E2 PR Adversarial Review — <branch / commit> · <date>

## 改動範圍
（diff stats + files touched）

## 8 條 §九 checklist
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
