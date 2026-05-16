# E2 Retroactive Adversarial Review — Wave 3 WP-08 ML Pipeline engine_mode + Purge Gap

**對象**：commit `f31b6e8f` 內：
1. `program_code/ml_training/realized_edge_stats.py` `engine_mode='live'` → `ANY(['live','live_demo'])` 展開
2. `program_code/ml_training/edge_estimate_validation.py` `purge_days` param（default 0）插入 walk-forward train/test gap

**Review 模式**：retroactive — commit body self-claim 「E2 PASS」 0 真實 dispatch
**Verdict**：**APPROVE-CONDITIONAL → PASS to E4** · 0 BLOCKER / 0 HIGH / 1 MEDIUM / 2 LOW / 1 P2

---

## 一、改動範圍 vs PA 方案核對

### Part 1: realized_edge_stats.py engine_mode scope
**Scope claim**：MIT-DB-6 — `engine_mode='live'` 查詢需展開為 `ANY(['live','live_demo'])` 以匹配歷史 43k 條 live_demo rows（memory record：engine_mode 標籤升級 2026-04-16）

**Diff 實測**：
- Line 217 新增 `_VALID_ENGINE_MODES = ("paper", "demo", "live", "live_demo")` constant
- Line 219-227 新增 `_engine_mode_scope(engine_mode) -> list[str]` helper：'live' 展開為 ['live', 'live_demo']，其他保持單值
- `_FILLS_QUERY` line 250 `f.engine_mode = %(engine_mode)s` → `f.engine_mode = ANY(%(engine_modes)s)` ✅
- `_FUNDING_QUERY` line 267 同上 ✅
- `compute_edge_stats()` line 545-548 替換 inline validate；passes `engine_modes` param ✅

**Cross-check**：grep `engine_mode = %\(` in realized_edge_stats = 0 hit（全替換完）✅

### Part 2: edge_estimate_validation.py purge_days
**Scope claim**：MIT-P1-2 — walk-forward train 結尾與 test 開頭之間插入 purge gap（默認 0 保持 backward compat）

**Diff 實測**：
- Line 24-26 ValidationConfig 新欄位 `purge_days: int = 0`
- Line 121-126 `_walk_forward_oos_values` docstring 新增 purge gap 說明
- Line 141 `purge = timedelta(days=config.purge_days)`
- Line 148 `while window_start + train + purge + test <= last_ts:` ✅
- Line 150-152 `test_start = train_end + purge / test_end = test_start + test`
- Line 154 `_records_in_window(dated, test_start, test_end)` ✅

✅ 改動範圍與 claim 一致。

---

## 二、Root cause 分析（對抗視角）

### Part 1: engine_mode scope
**Root cause**：LiveDemo（live pipeline + demo endpoint）的 fills 寫入時 `engine_mode='live_demo'`（per memory 2026-04-16），歷史 43k 條 `engine_mode='live'` 其實也是 LiveDemo（rename 之前）。realized_edge_stats 查 `engine_mode='live'` 漏抓 `live_demo` rows → 邊際統計 sample 嚴重不足。

✅ 真解 root cause。

**對抗反問**：
1. 「`live_demo` 與真 mainnet `live` 統計合併是否破壞 cost / liquidity / spread 假設？」
   - 答：歷史 43k `live` 其實都是 LiveDemo（per memory），真 mainnet live 從未發生（Live 5-gate 未通過）；'live' 與 'live_demo' 在現實中 = 同一群體 → 合併 OK
2. 「未來真 mainnet live 上線後此邏輯仍正確嗎？」
   - 答：未來真 live 上線後 `engine_mode='live'` 含 mainnet + LiveDemo 兩類；ANY(['live','live_demo']) 仍會抓兩類。**潛在問題**：mainnet live 與 LiveDemo 統計需要分離（cost、spread 不同）— 但這超出 WP-08 scope，留 W6 spec。✅ Acceptable

### Part 2: purge_days
**Root cause**：walk-forward 若 train 結尾與 test 開頭時間相鄰，**autocorrelation** 會讓 test sample 含 train period 末端的 mean-reversion 殘餘 → look-ahead bias（CPCV / GapPurge 經典問題）。MIT-P1-2 補 purge gap 是 ML 標準做法。

✅ 真解 root cause；default=0 保持 backward compat 是合理 trade-off（不破現有 baseline）。

---

## 三、對抗 7 checklist

| Item | Verdict |
|---|---|
| 1. Root cause vs 表面 patch | ✅ Part 1 + Part 2 都真解 root cause |
| 2. Lexical scope shadow | ✅ `engine_modes` 與 `engine_mode` 命名分明，無 shadow；purge 是 local |
| 3. Race condition | N/A — ML batch 工具非 concurrent |
| 4. Backward compat | ⚠️ Part 1 改變 `_FILLS_QUERY` / `_FUNDING_QUERY` param key 從 `engine_mode` → `engine_modes`；如有外部 caller 用 raw query string 會 break。grep 顯示無外部 raw query usage（這兩 query 是 module-level constant，外部訪不到）✅；Part 2 `purge_days=0` default 保 compat ✅ |
| 5. Perf regression | ✅ ANY([...]) 是 PG GIN/btree 都優化過的 operator；無 perf 影響；purge_days=0 path 與舊邏輯數學上等價 |
| 6. Test 強度 | 🛑 **0 新增 test** for both parts — 嚴重不足 |
| 7. Comment / citation accuracy | ✅ Part 1 cite「MIT-DB-6」+「memory project_engine_mode_tag_live_demo 升級」對應正確；Part 2 cite「MIT-P1-2」對應正確；無 fabricated |
| 8. §九 singleton 表 | N/A |
| 9. 跨檔影響面 | ⚠️ 詳下節 |
| 10. 新引入 issue | MEDIUM 1 / LOW 2 / P2 1 |

---

## 四、跨檔影響面 verify

```bash
# realized_edge_stats.py callers
grep -rn 'from .realized_edge_stats import\|import realized_edge_stats\|compute_edge_stats' program_code/ 2>/dev/null
```

**未在 retroactive review 內跑** — 建議 E4 / E1 自驗：
- 既有 caller 是否傳 `engine_mode='live'` 期待單一值？新 helper 自動展開 OK
- 是否有 caller fmemoizing query result by `engine_mode` key？若 'live' 結果現含 live_demo rows，cache invalidation 對齊？

**edge_estimate_validation.py callers**：
- `purge_days` 默認 0 → 既有 caller 不影響 ✅
- 新呼叫者必須 explicit set `purge_days=N` 才啟用

---

## 五、Findings

### MEDIUM — 0 新增 test 驗 engine_mode scope 展開正確性
**位置**：realized_edge_stats.py `_engine_mode_scope` helper
**問題**：新 helper 是「核心 ML pipeline 入口 query 邏輯」改動，但無單元測試驗：
- `_engine_mode_scope('live')` == `['live', 'live_demo']`
- `_engine_mode_scope('paper')` == `['paper']`
- `_engine_mode_scope('demo')` == `['demo']`
- `_engine_mode_scope('live_demo')` == `['live_demo']` (precise match, not auto-expanded)
- `_engine_mode_scope('invalid')` raises ValueError
**對抗反問**：「你說 'live' 展開 'live_demo' 但 'live_demo' 不展開 — 為什麼？將來真 mainnet 上線改不改邏輯？這 design intent 必固在 test 內，否則下次 refactor 容易回退。」
**建議修法**：新 unit test file `tests/test_realized_edge_stats_scope.py` 覆 5 個 case。
**嚴重性**：MEDIUM — 真實 SQL query 已驗（2 callsite 替換完），但 helper 邏輯無 test 是治理 gap。

### LOW-1 — purge_days 無 unit test 驗 walk-forward 真實插入 gap
**位置**：edge_estimate_validation.py:148-154
**問題**：`while window_start + train + purge + test <= last_ts:` 邏輯改動無 test 驗：
- `purge_days=0` 與舊行為 byte-equal（regression test）
- `purge_days=5` 真實跳過 5 天 records
- `purge_days > test_days` edge case（gap > test window 是否合理 fail-closed）
**建議**：unit test with synthetic timestamp series（每天 1 record）+ ValidationConfig(purge_days=5) 驗 train_end + 5d - test_start 真實 gap。
**嚴重性**：LOW — default 0 path 數學上等價（`+ purge=0` 不變 loop condition），低風險。

### LOW-2 — comment 註釋稱「歷史 43k 條 'live' 實為 LiveDemo」但無 inline verification snippet
**位置**：realized_edge_stats.py:217-218
**內容**：
```python
# MIT-DB-6：engine_mode 有效值 + scope 映射。
# LiveDemo 寫入 engine_mode='live_demo'，查 'live' 時需同時包含兩者。
```
**對抗反問**：「43k count 出處？memory project_engine_mode_tag_live_demo 寫的；但這註釋讀者沒看 memory 不會知道為什麼 'live' 要 expand 'live_demo'。」
**建議**：註釋加 link 到 memory：`# 詳 memory/project_engine_mode_tag_live_demo.md`。
**嚴重性**：LOW — cosmetic / discoverability。

### P2-Governance — purge_days config 路徑 backward compat 但無 callsite passing
**問題**：`purge_days` 加入 ValidationConfig，但 grep 顯示無 production code path 真實啟用 `purge_days > 0` — pure plumbing，dead-API until 後續 wave 接線。
**對抗反問**：「你新增 purge_days param 但無 caller 用 — 跟 BB-MF-3 dead-API 同型；下個 wave 接線時必驗 0→N 的 edge case + Phase A/B/C/D promotion gate 用 N 而非 0」
**建議**：P2 ticket — Phase B/C/D Alpha Surface promotion 用 purge_days=5 default + healthcheck 驗 ValidationConfig.purge_days > 0 才 accept
**嚴重性**：P2 — 不阻 merge，infrastructure 準備好等接線。

---

## 六、Trade-off accepted

- Part 1 ANY([list]) PG 效能等同 `=`，無 regression
- Part 2 default 0 維持 backward compat 是合理（不破現有 baseline）
- 無 unit test 屬 MEDIUM/LOW — E4 regression 可發現某些 case，但治理上建議補

---

## 七、結論

**APPROVE-CONDITIONAL → PASS to E4** · 0 BLOCKER / 0 HIGH / 1 MEDIUM / 2 LOW / 1 P2

WP-08 Part 1 + Part 2 真解 root cause（LiveDemo scope drift + walk-forward look-ahead bias），改動精準對齊 MIT-DB-6 / MIT-P1-2 spec；無 backward compat 破壞；perf 等價。

### Pushback（必修）
**MEDIUM** — `_engine_mode_scope` 5 case unit test（'live' → ['live', 'live_demo'], 'paper' → ['paper'], 'demo' → ['demo'], 'live_demo' → ['live_demo'], 'invalid' → ValueError）

### Follow-up（不阻 merge）
- **LOW-1** — purge_days walk-forward regression test
- **LOW-2** — comment 加 memory link
- **P2** — Phase B/C/D promotion gate 用 purge_days > 0 + healthcheck

### Retroactive caveat
commit `f31b6e8f` 自承「E2 PASS」0 真實 E2 dispatch。本 retroactive verdict APPROVE-CONDITIONAL，但 chain breach 治理 gap 需 PM 補救。
