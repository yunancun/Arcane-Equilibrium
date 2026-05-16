---
name: bilingual-comment-style
description: Compatibility skill name for the current OpenClaw comment style. Enforces Chinese-first comments, MODULE_NOTE clarity, and touched-block cleanup. TW writes; E2 reviews.
allowed-tools: Read, Grep, Glob, Edit, Write
---

# Chinese-First Comment Style

> **Compatibility note**: the skill directory keeps the historical
> `bilingual-comment-style` name so existing agent settings do not break.
> The active rule is now Chinese-first comments.

> **Source order**: runtime config / Rust schema > `TODO.md` active state >
> `README.md` stable surfaces > `CLAUDE.md` operating rules > governance docs >
> role memory > this skill. If sources conflict, surface the conflict and ask
> PM / operator; do not average rules silently.

## When To Use

- TW receives comment, MODULE_NOTE, engineering-log, or doc-comment work.
- E1 / E1a adds or materially changes functions, classes, modules, fail-closed
  paths, safety logic, or complex invariants.
- E2 reviews a diff and checks whether comments explain intent without carrying
  stale bilingual duplication.

## Current Rule

- New or modified comments default to Chinese.
- Keep English only for exact technical identifiers, protocol terms, API names,
  SQL schema names, Rust/Python symbols, and user-facing copy that is already
  intentionally English.
- Existing bilingual blocks are not cleaned unless touched.
- When a touched block already has Chinese + English duplicate prose, remove the
  English duplicate and keep the Chinese explanation.
- Comments must explain **why** the invariant, boundary, or decision exists.
  Do not add decorative comments that restate the code.

## Required Comment Coverage

| Area | Required style |
|---|---|
| New module | `MODULE_NOTE` with purpose, main classes/functions, dependencies, hard boundaries |
| New public function/class | Doc comment or docstring when behavior is non-trivial or externally called |
| Safety / fail-closed path | Chinese rationale for why fail-closed is required |
| Complex invariant | Chinese explanation plus exact technical identifiers |
| TODO / FIXME / NOTE | Chinese context + ticket / owner when known |
| User-facing GUI text | Follow existing UI language pattern; do not invent a new translation system |

## Templates

### Rust Module

```rust
// MODULE_NOTE
// 模塊用途：處理單筆 K-line tick，產出 intent 候選後送 governance 審批。
// 主要類/函數：process_tick、build_intent_candidates。
// 依賴：BybitWsListener、IntentProcessor、Guardian。
// 硬邊界：交易 hot path 不得 panic；資料不足必 fail-closed。
```

### Rust Function

```rust
/// 計算 ATR 動態止損。
///
/// 為什麼：止損距離必須隨波動調整，否則低波動時過寬、高波動時過窄。
/// 不變量：資料不足或 NaN 回傳 None，呼叫端必 fail-closed。
pub fn compute_atr_stop(kline: &[Ohlcv]) -> Option<f64> { ... }
```

### Python Module

```python
"""
MODULE_NOTE
模塊用途：定時刷新每個 strategy::symbol 的 edge estimate。
主要類/函數：EdgeEstimatorScheduler、refresh_edge_estimates。
依賴：trading.fills、learning.exit_features、settings/edge_estimates.json。
硬邊界：leader election 必須防止多 worker 重複寫入。
"""
```

### Python Function

```python
async def submit_intent(intent: TradeIntent, actor: str, lease_id: str) -> SubmitResult:
    """
    提交交易意圖並經 Guardian 審批。

    為什麼：AI 只能產生建議，所有交易意圖必須經 lease + 風控 gate。
    任一授權、lease、風控檢查失敗時 return ok=False，不拋給下游補救。
    """
    ...
```

### Inline Invariant

```rust
// 不變量：超過 MAX_OPEN_POSITIONS 代表風控前已有 race，必須拒絕新單並記 telemetry。
debug_assert!(positions.len() <= MAX_OPEN_POSITIONS);
```

```python
# 為什麼 fail-closed：authorization.json 失效時，下游 IPC 可能尚未收到 cancel token。
if not auth.is_valid():
    return Err("authorization invalid")
```

## E2 Review Grep

```bash
# 新檔缺 MODULE_NOTE 或模塊用途
rg -L 'MODULE_NOTE|模塊用途' <new-files>

# 大段英文註釋：通常是舊 bilingual block 或新規則違反，需要人工判斷
rg -n '^[[:space:]]*(#|//|///|\\*) [A-Za-z][A-Za-z ,.;:()/-]{50,}$' <changed-files>

# 空洞 TODO
rg -n 'TODO: (fix|update|handle this|misc|later)' <changed-files>
```

## Anti-Patterns

- 新增中英逐句重複，沒有額外信息。
- 修改舊 bilingual block 時只改英文、不修中文。
- 只寫「處理資料」「do stuff」這類無信息注釋。
- `# TODO: fix this` 沒有中文上下文或 ticket。
- 安全 / fail-closed / hard boundary 只描述做了什麼，沒有說為什麼。

## TW Workflow

1. Read the task scope and `git diff`.
2. Identify new or materially changed modules / public APIs / safety paths.
3. Add or clean comments only inside the task scope.
4. Do not change business logic while doing comment cleanup.
5. Report changed files, comment categories, and any unresolved ambiguity.

## Output Format

```markdown
# TW 注釋審查 — <commit> · <date>

範圍：<files>

## 補充或清理
| 檔:行 | 類型 | 結果 |
|---|---|---|
| foo.rs:42 | safety invariant | 補中文 rationale |

## 未處理
- <reason / owner / follow-up>
```
