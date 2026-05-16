# E2 Retroactive Adversarial Review — Wave 3 WP-06 state_compiler deepcopy 3→2

**對象**：commit `f31b6e8f` 內 `program_code/exchange_connectors/bybit_connector/control_api_v1/app/state_compiler.py` 約 +12 / -10 LOC
**Review 模式**：retroactive — commit body self-claim 「E2 review: 0 CRITICAL / 0 HIGH / 1 MEDIUM pre-existing / 2 LOW cosmetic → PASS」 0 真實 dispatch；CC cross-validation 確認
**Verdict**：**APPROVE → PASS to E4** · 0 BLOCKER / 0 HIGH / 0 MEDIUM / 1 LOW / 1 WATCH

---

## 一、改動範圍 vs PA 方案核對

**Scope claim**：`compile_state()` deepcopy 3 次精簡為 2 次 — cache 內存 deepcopy(result)、caller 拿 raw result。
**Diff 實測**：
- Line 635 `compiled = copy.deepcopy(state)` — INPUT deepcopy（保留，必要）
- Line 640 `_compile_cache = copy.deepcopy(result)` — CACHE deepcopy（保留，必要）
- 移除 Line 642 原始 `return copy.deepcopy(result)` → 改為直接 `return result`

**Cache hit 路徑**：line 631 `return copy.deepcopy(_compile_cache)` — 仍 deepcopy 一次（cache 已是 deepcopy，避免 caller 修改污染 cache 本身）

**精簡證明**：
- 原 path：input deepcopy + compile + cache=result + return deepcopy(result) → 3 次
- 新 path：input deepcopy + compile + cache=deepcopy(result) + return result → 2 次

✅ Claim 正確。

---

## 二、Root cause 分析（對抗視角）

**為什麼省一次 deepcopy 有意義**：`state` 是 trade-core snapshot，含 ~25 symbols × N strategies × M klines/indicators → deepcopy ms 級成本；每 GUI poll / IPC tick / cron 都呼 → cumulative ms-per-second 浪費。

**正確性分析**：原邏輯 `_compile_cache = result` + `return copy.deepcopy(result)` 是「cache 持 raw / caller 拿 deepcopy」；新邏輯 `_compile_cache = copy.deepcopy(result) / return result` 是「cache 持 deepcopy / caller 拿 raw」 — 兩者**功能等價**：
- Caller A 拿 raw result（即 compiled raw），caller A 修改 result → 不影響 cache（cache 是獨立 deepcopy）✅
- Caller B 後續呼 cache hit → 拿 `copy.deepcopy(_compile_cache)` fresh deepcopy → 與 caller A 的 result 完全獨立 ✅

**Invariant 不變**：「cache 內物件不被 caller 修改污染」維持。

---

## 三、對抗 7 checklist

| Item | Verdict |
|---|---|
| 1. Root cause vs 表面 patch | ✅ 真省一次 deepcopy（不是改完忘記 deepcopy）|
| 2. Lexical scope shadow | ✅ `result` 是 `compiled` 別名（_do_compile_core 是 in-place），無新 shadow |
| 3. Race condition | ✅ 詳下節「Race detail」|
| 4. Backward compat | ✅ caller 拿到的物件型別不變（dict），內容不變；caller 不能假設「拿 raw vs deepcopy」（這是內部 implementation detail）|
| 5. Perf regression | ✅ 反向改善 — 每次 compile 省一次 deepcopy（~ms）|
| 6. Test 強度 | ⚠️ E1 自承「PA spec 沒提 test 要求」；建議 add unit test 驗 caller 修改 result 不污染 cache（reproduce 不變式）|
| 7. Comment / citation accuracy | ✅ 註釋寫「WP-06 E5-P-2 deepcopy 精簡」誠實標 wave；無 fabricated reference |
| 8. §九 singleton 表 | N/A — _compile_cache 是 module-level 不是 class singleton，pre-existing |
| 9. 跨檔影響面 | ⚠️ 詳下節「Caller impact」|
| 10. 新引入 issue | LOW 1 + WATCH 1 |

---

## 四、Race detail（深度對抗）

**Pre-existing pattern**（不是 WP-06 引入）：
```python
with _compile_cache_lock:
    cached_rev = ...
    if not _compile_dirty and ...:
        return copy.deepcopy(_compile_cache)  # ← lock 內 hit path

# ── lock 外 compile ──
compiled = copy.deepcopy(state)
result = _do_compile_core(compiled, ...)

with _compile_cache_lock:
    _compile_cache = copy.deepcopy(result)
    _compile_dirty = False
return result
```

**Concurrent scenario**：
- T1 / T2 同時 miss cache
- T1 lock 外 compile state_A → store cache_A
- T2 lock 外 compile state_A → store cache_A（覆蓋 T1 的 cache_A，但內容一樣）
- T1 / T2 各自拿 result raw — 都是 valid compile of state_A

✅ **無實質 race**：lock-外 compile 雙做但結果相同；last writer wins 但內容相同；caller 拿 result 是 own copy（compiled 是 input 的 deepcopy，T1 與 T2 各 own）。

**WP-06 對 race surface 影響**：未改變（仍是 pre-existing double-checked lock pattern）。

---

## 五、Caller impact 對抗 grep

```bash
# state_store.py:347 / state_store.py:366 - compile_state() callers
# learning_records.py / control_ops.py / learning_auto_pipeline.py / pnl_ops.py - 經 _compile_for_response 間接
# main.py:60/68 - stable_compile_state 不經本 path
```

**潛在 caller 反模式**：caller 拿 result 後**修改**它然後**期待下次 compile_state 返回同樣修改後內容** → 這在原邏輯下也不會工作（拿的是 deepcopy 不是 cache reference）；新邏輯下 caller 拿的是 compiled raw（fresh copy）也不會。invariant 不變。

**唯一風險場景**：若 caller 拿 result → 同步操作 → 進入 `_compile_cache_lock`（其他 thread 競爭 lock） → 期間 caller A 拿的 result 物件可能被 caller A 自己修改 → 但這跟 cache 無關，cache 已存 deepcopy。
✅ Safe.

---

## 六、Findings

### LOW — `_compile_cache = copy.deepcopy(result)` 在 lock 內做 deepcopy 拖長 lock hold time
**位置**：state_compiler.py:640
**內容**：原邏輯 `_compile_cache = result` 是 ns 級；新邏輯 `_compile_cache = copy.deepcopy(result)` 是 ms 級，且在 lock 內做。其他 thread 進 cache hit 路徑必等待。
**對抗反問**：「你在 lock 內 deepcopy 是不是用『caller wait 一次 deepcopy』換『caller 跳一次 deepcopy』 — 但 lock-internal deepcopy 阻塞**所有**其他 caller 而原邏輯只阻塞 lock-internal critical section？net deepcopy 數量相同，但 contention 變高。」
**證據**：
- 原邏輯 lock-internal time = nanoseconds（assignment）
- 新邏輯 lock-internal time = milliseconds（deepcopy large state）
- 高頻 caller 場景（GUI poll 1 Hz + cron 0.1 Hz + IPC）lock contention 上升
**建議修法**：
```python
# 在 lock 外先做 deepcopy 再進 lock 賦值
cache_snapshot = copy.deepcopy(result)
with _compile_cache_lock:
    _compile_cache = cache_snapshot
    _compile_dirty = False
return result
```
**嚴重性**：LOW — 真實 deepcopy 時間 ms 級，hot path 影響可量化但不阻 deploy。建議 P2 ticket 修。

### WATCH — `_compile_cache` mutation 與 `mark_compile_dirty()` race window
**位置**：state_compiler.py:111-120 vs 639-641
**內容**：原邏輯 `_compile_cache = result` 後 lock 釋放，後續 `mark_compile_dirty()` 進 lock 設 `_compile_dirty=True`；新邏輯 lock 內 deepcopy 加長 critical section，writer（mark_compile_dirty）排隊更久。
**對抗反問**：「state 寫入線程必先 `mark_compile_dirty()` 才寫；若 dirty 設遲，concurrent reader 還用 stale cache」
**證據**：但 reader hit cache 拿的是 deepcopy，stale 也只是 staleness magnitude 問題（read-after-write inconsistency）— pre-existing pattern，WP-06 不引入新 race。
**嚴重性**：WATCH — pre-existing，記錄供 E5 perf audit 時觀察。

---

## 七、結論

**APPROVE → PASS to E4** · 0 BLOCKER / 0 HIGH / 0 MEDIUM / 1 LOW / 1 WATCH

WP-06 真省一次 deepcopy，invariant（cache 不被污染）維持；對抗 grep 確認 caller 不依賴「拿 deepcopy」假設。LOW-1 lock contention 是 trade-off（pre-existing path 模式內），建議 P2 修但不阻 merge。

### Pushback（可選）
**LOW** — line 640 `_compile_cache = copy.deepcopy(result)` 移到 lock 外做 deepcopy；lock 內僅 assignment（P2 follow-up，不阻 merge）

### Retroactive caveat
commit `f31b6e8f` body 寫「E2 review: 0 CRITICAL / 0 HIGH / 1 MEDIUM pre-existing / 2 LOW cosmetic → PASS」 — 0 真實 E2 agent dispatch（CC cross-validation 確認）。本 retroactive review verdict APPROVE 與 commit body self-claim 一致，但**治理 chain breach 事實**仍需 PM 補救路徑。
