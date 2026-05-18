# E2 PR Adversarial Review — W-AUDIT-8a B-REM-5 SourceAvailability schema

Branch: `feature/w-audit-8a-b-rem-5-source-availability`
Commit: `5997dd43`
Date: 2026-05-18
Reviewer: E2 (adversarial code-review + auditor)

---

## §0 Verdict

**APPROVE (schema IMPL)** — pass to E4 regression
**MUST-FIX before merge to main**: ADR-0023 documentation (separate dispatch, not E1 schema work)

Verdict rationale: schema IMPL itself is clean, well-tested, cardinality-safe,
serde stable, backward-compatible with existing `source_tier` field. ADR-0023
absence is documented governance gap explicitly called out in commit body
(`NOT TO BE MERGED TO main WITHOUT: ADR-0023 documentation written`). PM should
dispatch ADR-0023 write as separate ticket before merge.

1 LOW finding inline (downstream count docstring inconsistency 6 vs 7) —
recommend fix in same PR via 1-character docstring edit; can also defer to PM
as P3.

---

## §1 改動範圍（單檔，scope clean）

- Single file: `rust/openclaw_core/src/alpha_surface.rs` +369 / -0
- Single commit `5997dd43` post merge-base `ab6f5c3e` (PA TODO update)
- 0 unrelated file changes
- File total post-IMPL: 1019 lines (above 800 review-attention but well under 2000 cap; pre-existing file size driven by Tier 1-4 snapshot types, not B-REM-5)

---

## §2 E2 8 條 reviewer checklist

| Item | 狀態 | 備註 |
|---|---|---|
| 改動範圍與 PA §6.2 一致 | ✅ | enum + tests + governance comment 落地；variant set 是 PA §6.2 + §6.4 superset（design enhancement，見 §4.4） |
| 無 except:pass / 靜默吞異常 | N/A | Rust enum schema 無 IO 路徑 |
| 日誌 %s 格式 | N/A | 純 schema 定義 |
| 新 API 端點有 _require_operator_role | N/A | 無 HTTP 端點 |
| except HTTPException raise 在 except Exception 前 | N/A | 純 Rust |
| detail=str(e) 已改 Internal server error | N/A | 純 Rust |
| asyncio blocking Lock | N/A | 純 Rust + 純 type definition |
| 私有屬性穿透 ._xxx | N/A | Rust |

純 schema/enum 工作，多數 Python-向 checklist 不適用。

---

## §3 OpenClaw §3 特殊 9 條

| Item | 狀態 | 證據 |
|---|---|---|
| 3.1 跨平台 grep `/home/ncyu` `/Users/[^/]+` | ✅ | grep 0 hit |
| 3.2 注釋規範（中文為主） | ✅ | 全 enum + impl 註釋中文；技術名詞保留 snake_case identifier；MODULE_NOTE 級別 doc-comment 規範 |
| 3.3 Rust unsafe / unwrap / expect / panic | ✅ | 0 unsafe；4 unwrap 全在 `#[cfg(test)]` test code（JSON round-trip，test failure 即可恢復信號） |
| 3.4 跨語言 IPC schema 一致 + serde 型別安全 | ✅ | `#[serde(tag="kind", rename_all="snake_case")]` 內部標記 + 全 8 變體 round-trip test 覆蓋 |
| 3.5 Migration Guard A/B/C | N/A | 無 V### migration |
| 3.6 healthcheck 配對 | N/A | 純 type，無 passive-wait |
| 3.7 Singleton / monkey-patch | N/A | 無 singleton |
| 3.8 文件大小 800/2000 | ⚠ 1019 行 | 已過 800 警告線；2000 cap 充足；B-REM-5 +369 增量不應推進拆檔（其他 Tier snapshot 集中此檔利於 alpha source bundle 一致性） |
| 3.9 Bybit API 改動 | N/A | 不觸 Bybit API |
| 3.10 P0/P1 leak/bias caller proof | N/A | 不涉指標/leak/look-ahead |

---

## §4 對抗反問結果（12 條 probes）

### §4.1 PA §6.2 spec compliance

PA §6.2 acceptance criteria:
1. **enum + tests** ✅ — 8 variants（5 PA §6.2 baseline + 3 PA §6.4 B-REM-3 reasons）+ 6 tests + 442 total unit test PASS
2. **ADR-0023 land** ❌ **NOT LAND** — 文件不存在；commit body 明 flag
3. **6 downstream worktree spec cite** ⏸ DEFER — 屬 Wave 2 PA dispatch，本 worktree 無責

PA §6.2 spec compliance：**1/3 直接交付，1/3 設計超出 spec（合理增強），1/3 deferred to PM**。

### §4.2 SourceAvailability + AvailabilitySource 設計品質

**正向設計亮點**：
- **巢狀 `Available { tier }`** 而非平鋪 `{ WsLive, RestSeed, CohortExcluded ... }` — 把「是否可用」與「資料來源層」拆兩個正交問題，杜絕 `WsLive + StalePanel` 之類非法組合（spec 強化）
- **`as_metric_label()` 對 `Available { .. }` 統一回 `"available"`** — 杜絕 Prometheus tag cardinality 爆炸（tier 子標籤透過獨立 `availability_tier_label()` API 提供）
- **`is_available()` / `unavailable_reason()` 互逆 API** — 下游 candidate report 寫入 `unavailable_reason` 欄位時直接 `availability.unavailable_reason()` 即可；E1 對應 test `source_availability_is_available_and_unavailable_reason_inverse` 鎖死互逆契約
- **Display impl 對 Available 與 unavailable 分別處理**（`"available(ws_live)"` vs `"stale_panel"`）— 日誌人讀友善
- **Hash + Eq 在 Available 變體的 payload 上自動 Hash**（因 AvailabilitySource derives Hash/Copy/Eq）— 可作為 HashMap key

**Derive 評估**：
- `Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize` 全到位
- 未 derive `Copy` — 雖然當前所有變體都 Copy-safe（AvailabilitySource 是 Copy + 其他變體 unit），但**故意不 Copy 是 forward-compat 設計選擇**（未來變體可能帶 String reason / source chain）。可接受。

### §4.3 7 downstream worktree cross-ref 完整性

E1 commit body + IMPL test fixture：
```
("B-REM-2", "funding consumer report"),
("B-REM-3", "bb_breakout OI consumer report"),
("C2-ORDERFLOW", "Tier 3 orderflow panel provider"),
("C3-SPREAD", "Tier 3 spread dynamics extension"),
("D1-EVENT", "Scout→Rust EventAlert provider"),
("D2-REGIME", "RegimeTag provider"),
("D3-SENTIMENT", "SentimentPanel provider"),
```
與 PA §6.2 `B-REM-2/3 + C2/C3 + D1/D2/D3` = 7 worktree 對齊。**但**注釋上方寫「6 個下游 worktree」與計列出的 7 個不一致 — 見 §5 LOW 1。

### §4.4 Variant 集設計超出 PA §6.2 raw spec 評估

PA §6.2 原列 5 variant: `WsLive, RestSeed, CohortExcluded, StalePanel, Absent`。

E1 IMPL 變更：
- 把 `WsLive`/`RestSeed` 折疊進 `Available { tier: AvailabilitySource }`（淨減 1 variant，型別更乾淨）
- 新增 `MissingSymbol, NonFiniteAbsolute, NonFiniteDelta`（從 PA §6.4 B-REM-3 spec 引用 5 reason 變體：`absent / stale / missing-symbol / non-finite-absolute / non-finite-delta`）

評估：**合理 design enhancement，非 scope creep**：
- PA §6.4 spec 明顯要求 B-REM-3 有 5 reasons（absent/stale/missing-symbol/non-finite-absolute/non-finite-delta）
- 把這 5 reason 提到共享 schema = 單一來源 of truth，避免 B-REM-3 自定義 + 之後 C2/C3/D1/D2/D3 重複/分歧
- ADR-0023 在 Decision 章節需 lock 完整 8-variant 集（含這 3 新增）

### §4.5 Cardinality safety

Prometheus + PG label 重排：
- `as_metric_label()` 只回 8 個 string（其中 `Available` 統一回 `"available"`）— **cardinality bounded**
- Tier 子標籤透過 `availability_tier_label()` 提供（只有 Available 才回 ws_live/rest_seed） — **2 額外子標籤 only when available**
- 下游 report writer 應該用 `(as_metric_label, availability_tier_label)` 雙標籤 — 但 E1 沒有強制 — 信任下游 IMPL pattern。可接受。

### §4.6 Serde 跨語言契約

Internally-tagged `#[serde(tag = "kind", rename_all = "snake_case")]`：
```json
{"kind":"available","tier":"ws_live"}
{"kind":"available","tier":"rest_seed"}
{"kind":"cohort_excluded"}
{"kind":"stale_panel"}
{"kind":"missing_symbol"}
{"kind":"non_finite_absolute"}
{"kind":"non_finite_delta"}
{"kind":"absent"}
```
E1 全 8 case round-trip test `source_availability_serde_round_trip_internally_tagged`。Python 端 writer 須產出對應 dict（B-REM-2/3 IMPL 階段責任）。**Python 端 schema 未在本 PR 觸碰 — 屬 schema-only worktree 正確邊界**。

### §4.7 Backward compatibility with existing `source_tier: String`

既存 panel snapshot（FundingCurveSnapshot / BasisCurveSnapshot / OIDeltaPanel / OrderflowFeatures / LiquidationPulse / SentimentPanel 等）皆有 `source_tier: String` 字段（自由文本 provenance e.g. `"bybit_v5_ws_tickers"`）。E1 明文：

> 既存字串字段（panel snapshot 的 `source_tier`）**不被本 enum 取代**，兩者並存。

並在 AvailabilitySource doc 加注：

> 既存 `source_tier` = "bybit_v5_ws_tickers" 描述具體 endpoint；
> 本 enum 描述「實時 WS 還是 REST 冷啟動 seed」這一語意層次。

**0 既存字段被 break，正交設計**。PASS。

### §4.8 AlphaSurface struct 沒有 retrofit

`AlphaSurface { funding_curve: Option<&'a FundingCurveSnapshot>, ... }` 沒改成 `funding_curve: SourceAvailability` 或類似。**這是設計正確**：

- B-REM-5 是 schema-only worktree（PA §6.2 「shared report-fields helper」非「AlphaSurface 型別替換」）
- 策略 consumer 仍用 `surface.funding_curve.is_none() → fail-closed skip` pattern
- 新 enum 用於 **candidate report writer**（B-REM-2/3 + 5 個下游）的 `unavailable_reason` 欄位 — 報「為什麼 None」的分類成因，不取代 None 本身
- 拆分職責正確：surface = realtime gating；availability enum = post-hoc classification for reporting

### §4.9 ADR-0023 引用

doc-comment line 191：`**添加 variant 必經 ADR**（per ADR-0023 §Decision）`

- ADR-0023 不存在（grep `ls docs/adr/ | grep 0023` = 0 hit；highest existing = 0022）
- E1 commit body 明 flag `ADR-0023 documentation pending`
- 這是 **forward reference** 等待 PA 寫 ADR 後 backfill
- **MUST-FIX before merge to main** — 否則嚴重違反「治理引用實體不存在」反模式

### §4.10 編譯與測試獨立驗證

```
cargo build -p openclaw_core --lib
  Finished `dev` profile [unoptimized + debuginfo] target(s) in 1.10s

cargo test -p openclaw_core --lib
  test result: ok. 442 passed; 0 failed; 0 ignored; 0 measured

cargo test -p openclaw_core --lib source_availability
  test result: ok. 6 passed; 0 failed; 0 ignored

cargo test -p openclaw_core --lib availability_source
  test result: ok. 2 passed; 0 failed; 0 ignored
```

**8 B-REM-5 tests pass + 442 total tests pass + 0 compile error + 4 pre-existing warnings (not B-REM-5 related)**

### §4.11 文檔 vs IMPL 計數不一致

SourceAvailability doc-comment line 176 寫「**6 個下游 worktree**」但右括號內列 7 個（B-REM-2/B-REM-3/C2/C3/D1/D2/D3 = 7），下方 markdown 表也 7 行，test fixture assert downstream.len() == 7。

PA §6.2 spec 也有相同 imprecision（`Five downstream worktrees` 與 `B-REM-2/3 + C2/C3 + D1/D2/D3` = 7 互相矛盾）— 是 PA→IMPL 一致傳遞的 imprecision，但 IMPL test fixture 正確選 7。

詳見 §5 LOW 1。

### §4.12 共享 schema downstream consumer pattern 完整性

E1 doc-comment 提供下游 7 worktree 引用表，但**未強制下游 IMPL 用 `availability` 或 `unavailable_reason` 哪個欄位名**。考慮：

- B-REM-3 spec 明列 5 reasons：`absent / stale / missing-symbol / non-finite-absolute / non-finite-delta` → 用 `unavailable_reason` 欄位（與 enum `unavailable_reason()` API 對齊）
- B-REM-2 spec 含 `source_tier` 欄位 → 用 `availability` field 帶 `Available { tier }` Available case

E1 doc-comment 提供「`availability` 或 `unavailable_reason`」彈性選擇 — 下游 PA spec 階段須統一決定。**不視為 finding，留作 PA Wave 2 IMPL spec dispatch 注意點**。

---

## §5 Findings

| 嚴重性 | 位置 | 描述 | 建議修法 |
|---|---|---|---|
| **MUST-FIX before merge** | docs/adr/0023-*.md 不存在 | ADR-0023 documentation 缺失；code 引用「per ADR-0023 §Decision」forward reference 但 ADR 未寫 | PM 派 PA 寫 ADR-0023 落地 enum governance（添加/刪除/重命名觸發 ADR 規則 + 8 variant 完整集 + 7 worktree 引用點） |
| **LOW 1** | alpha_surface.rs:176 (相對 5997dd43 後檔) | doc-comment 寫「**6 個下游 worktree**」但同行 parenthesized list 與下方表均列 7 個（test fixture 也 assert 7） | doc-comment 改「6 個」→「7 個」（1-字符 edit） |
| WATCH (E2 觀察) | alpha_surface.rs 1019 行 | 文件已過 800 review-attention 線 | 不在 B-REM-5 範圍內；後續 Tier-by-Tier IMPL 可考慮拆檔（如 `alpha_surface/{tier_1, tier_2, tier_3, tier_4, source_availability}.rs`），P3 |

**沒有 MEDIUM/HIGH/CRITICAL finding**。

---

## §6 §5 Multi-session race check（P0-GOV-MULTI-SESSION-RACE-SOP-1）

| Check | 狀態 |
|---|---|
| 5a 提交前 fetch + sibling window check | ✅ `git fetch --prune origin` 跑完；origin/main HEAD = 59d9338b 領先 B-REM-5 base ab6f5c3e (10+ commits)，與 B-REM-5 沒文件 overlap (B-REM-5 純 schema vs main 進展純 docs/phase 1b runtime + w-audit-8b round 2 reports) |
| 5b sub-agent IMPL DONE 前 status clean | N/A — E2 read-only review，不創 commit |
| 5c 看到 unknown WIP 禁 revert | ✅ 開始時 5 個 sibling agent memory 檔 unstaged (E2/E4/MIT/PA/QA memory.md) — 識別為其他並行 review session 工作；正確 stash + 還原，不 revert |
| 5d Sign-off report commit | N/A — E2 不 commit |
| 5e Sibling 推 origin 期間 → 重 fetch 重 review | ✅ 開始時 + 中段 fetch；無新 push 影響本 review file scope (alpha_surface.rs 0 sibling 改動) |

**All 5 checks PASS** — review session 期間無 multi-session race violation。

---

## §7 結論

**APPROVE schema IMPL — pass to E4 regression**

**MUST-FIX before merge to main**:
1. **ADR-0023 documentation** — PM 派 PA 寫 `docs/adr/0023-source-availability-schema.md`
   - §Decision: 8 variant 完整集 + 添加/刪除/重命名觸發 ADR 規則
   - §Consequences: 7 個下游 worktree 引用 + 既存 `source_tier: String` 並存合理性
   - §Status: Accepted（schema commit 後即 land）

**RECOMMEND fix in same PR**:
2. **LOW 1 docstring 6 → 7**：alpha_surface.rs line 176 一字符 edit；可由 E1 補一次 amend 或留 P3 ticket

**E4 regression scope**：
- `cargo test -p openclaw_core --lib`（已 442 PASS）+ workspace 級別 `cargo test --workspace`
- 預期無 regression（純 schema 增量，0 既存 logic 改動）

**Sign-off 鏈**：
- E1 IMPL ✅ DONE (5997dd43)
- E2 review ✅ APPROVE (本報告)
- PA ADR-0023 ⏸ PENDING（PM 派發）
- E4 regression ⏸ PENDING
- QA / PM sign-off ⏸ PENDING

---

E2 REVIEW DONE: APPROVE (schema) + MUST-FIX ADR-0023 before merge

Report: `docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-18--w_audit_8a_b_rem_5_e2_review.md`
