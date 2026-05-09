# A3 GUI UX Verification Report v2 — 2026-05-09

審查員：A3 · baseline `455d796e` → HEAD `1bd55689` (34 commits)

**Tally：✅ 7 / ⚠️ 5 / ❌ 18 / 🆕 7 · 整體 8.3 / 10 · Critical 5 closed: 4/5**

## §1 Executive Summary

**整體評分：8.1 → 8.3 / 10**（+0.2，34 commit 期間實際 UX 變化收斂）

**Critical 5 closure：4 / 5 closed**（v1 已 4/5；v2 未動 #5）

**v2 新關閉**：
- ✅ NEW-1（v1 Critical）`openConfirmModal()` a11y — **真補完**：commit `441ff9b5` 在 common.js:1633 加 `role="dialog" aria-modal="true" aria-labelledby` + `tabindex="-1"`、`overlay.onkeydown` 處理 Escape / Tab focus trap、`previousActive.focus()` 還原焦點、`setTimeout(() => cancelBtn.focus(), 0)` 初始焦點。實作品質：A 級。

**v2 仍未關**：
- ❌ #5 index.html 仍渲染含 Paper Submit Order 表單（line 221-227）
- ❌ #10 API Key 「清除」仍 `confirm()` (tab-ai.html:652)
- ❌ #11 Settings 8 種性質仍單頁
- ❌ #12 console.html:178 mode-tag initial DOM 仍 hard-coded — JS 雖然會 dynamic 切色但首屏渲染 SSR-window 仍是錯誤色
- ❌ #14 Live tab 仍 14+ sub-section 過載
- ❌ #15 Risk tab 雙層 sub-tab + P0/P1/P2 仍未響應式
- ❌ NEW-2 tab-system confirm-overlay 仍**完全沒**加 Esc / role / aria-modal / focus trap
- ❌ NEW-3 tab-live 3 個 dialog (532-563) 仍裸 div — 無 role + 無 keydown handler
- ❌ NEW-4 setInterval(updateCountdown, 100) 仍 100ms 閃爍
- ❌ NEW-5 重讀 index.html:42 實際只有一個 display:flex（v1 誤報），但 banner 後面 Paper 表單還在
- ❌ NEW-6 z-index scale token 未建立

**4 維評分**：
| 維度 | v1 | v2 | 變化 |
|---|---:|---:|---:|
| 術語友好性 | 6.5 | 6.5 | — |
| 操作流完整性 | 9.0 | 9.2 | +0.2 |
| 學習曲線 | 7.5 | 7.5 | — |
| 錯誤提示質量 | 8.0 | 8.0 | — |

## §2 v2 對抗性核實逐項

### Critical 5 v2 狀態
| # | Issue | v1 | v2 | 證據 |
|---|---|:---:|:---:|---|
| 1 | Decision Lease hard-coded false | ✅ | ✅ | (v1 已驗) |
| 2 | live_reserved 確認無倒計時 | ✅ | ✅ | tab-system.html:289-624 5s+1.2s hold |
| 3 | governance 4 prompt() | ✅ | ✅ | grep 0 prompt() |
| 4 | learning 2 prompt() | ✅ | ✅ | 同 |
| 5 | index.html legacy fallback | ⚠️ HALF | ⚠️ HALF | gui_legacy_routes.py:97-103 / 已導 console.html，但 /gui 仍服務 index.html 含 Paper 表單 |

### v1 ❌ 20 + ⚠️ 4 在 v2 重核
| # | Issue | v1 | v2 | 對抗證據 |
|---|---|:---:|:---:|---|
| 5 | risk Live 「確認修改」Enter | ❌ | ❌ | 無變化 |
| 6 | strategy Stop/Pause/Delete 三按鈕 | ✅ | ✅ | (v1 已驗) |
| 7 | live 「停止/緊急」並排 | ✅ MOSTLY | ✅ MOSTLY | tab-live 結構未動 |
| 8 | paper sessionStopAll() native | ✅ | ✅ | tab-paper.html:372 openConfirmModal |
| 9 | system 5 button 純 grid | ❌ | ❌ | 無變化 |
| 10 | ai API Key 清除 native confirm() | ❌ | ❌ | tab-ai.html:652 仍 confirm() — **24h+34commit 都沒做** |
| 11 | settings 8 種性質塞 1 tab | ❌ | ❌ | 無變化 |
| 12 | mode-tag tag-green hard-coded | ❌ | ⚠️ PARTIAL | initial DOM 仍錯，JS dynamic — 半修 |
| 13 | iframe 子頁無 mode chip | ❌ | ❌ | 無變化 |
| 14 | live 14 sub-section 過載 | ❌ | ❌ | 無變化 |
| 15 | risk 雙層 sub-tab | ❌ | ❌ | 無變化 |
| 16 | index.html legacy fallback | ⚠️ | ⚠️ | 同 #5 |
| 17-20 | 工程術語 / SM 縮寫 | ❌ | ⚠️ PARTIAL | tab-governance abbr 加；tab-risk 仍裸 |
| 21 | Esc 不關 modal | ⚠️ | ✅ MOSTLY | openConfirmModal 修，tab-system/tab-live/tab-demo 未修 |
| 22-30 | 各類 Medium | ❌ | ❌ | 無變化 |

### v1 🆕 6 NEW issues 在 v2 狀態
| # | NEW Issue | v1 | v2 |
|---|---|---|:---:|
| NEW-1 | openConfirmModal() 無 a11y | Critical | ✅ CLOSED |
| NEW-2 | tab-system confirm 無 Esc | High | ❌ OPEN |
| NEW-3 | tab-live 3 dialog 無 Esc | High | ⚠️ PARTIAL（close-position 用 openConfirmModal；3 dialog 仍裸）|
| NEW-4 | countdown 100ms 閃爍 | Medium | ❌ OPEN |
| NEW-5 | banner display 衝突 | Medium | ❌ FALSE-POSITIVE（v1 誤判）|
| NEW-6 | z-index 衝突風險 | Low | ❌ OPEN |

### 🆕 v2 新發現
| # | 嚴重度 | 證據 | 影響 |
|---|---|---|---|
| NEW-7 | Medium | tab-demo.html:1047/:1057 Demo 平倉 / 清塵仍 native confirm() — v1 漏報 | 與 Live close-position 已用 a11y modal 形成不一致 |
| NEW-8 | Medium | cards/linucb_card.html:186/:190 LinUCB migrate / rollback 仍 confirm() + alert() | 違反「Esc 永遠關 modal」consistency |
| NEW-9 | Low | console.html:178 mode-tag 初始 textContent shadow_only 是工程術語直暴露 | 應初始用 `--` 或 `加载中...` |

## §3 對抗性 Push Back（v2 增加）

### Push back 1：commit `441ff9b5` 「a11y controls」名稱 over-promised
單一 commit 只修了 openConfirmModal()。**未涵蓋** openPromptModal 已有 a11y、tab-system / tab-live / tab-demo / linucb_card 仍無。

### Push back 2：v2 34 commits 期間 UX 工作非常少
GUI 修復**只 1 commit**（441ff9b5）+ 1 Layer2 (35f81a7b context distiller，與 GUI 無關)。**24h sprint 之後 UX work-rate 急降到 2.9%**。

### Push back 3：mode-tag 「半修」風險
console.html:178 initial DOM `class="tag tag-green" id="mode-tag">shadow_only</span>`。執行流：
1. SSR 渲染：tag-green (錯) + textContent shadow_only (英文工程術語)
2. JS load → console.html:807-812 讀 systemMode → 切 modeColor
3. 但 JS 改的是 `modeEl.style.color`（行 815），**沒改 class** — 仍是 tag-green bg

實際結果：first-time operator 進來 1-2 秒看到綠 tag「shadow_only」，誤判系統健康。**JS 半修反而更危險**。

### Push back 4：Critical #10 持續 ignore
API Key clear 從 v1 發現以來已 24h+34commits，**0 行修改**。應該是 P0 優先序。

### Push back 5：tab-live 3 dialog 不一致
同檔內：close-position 用 openConfirmModal ✅；emergency stop / stop session / close all 用裸 dialog ❌。**Operator 凌晨點「平倉某幣」按 Esc 會關**，**緊接著點「緊急停止」按 Esc 不會關**——肌肉記憶不一致。

### Push back 6：tab-demo Dust / Demo close 未動
NEW-7 v2 也未修。

### Push back 7：v1 NEW-5 我承認誤報但保留扣分
重讀 index.html:42 後 display:flex 只出現一次（v1「兩次」是錯的）。但 banner 下方仍渲染 Paper 表單。

## §4 整體 v2 verdict

**34 commit 期間 GUI 真實進步**：openConfirmModal() a11y 真做（A 級實作）— 影響 ~10 caller，是 single-point fix 中影響最廣的修復

**34 commit 期間 GUI 真實停滯**：
- 18 ❌ open issues 中 0 項移動
- 6 NEW issues 中只 1 項閉合，5 項仍 open，且 v2 出現 3 新 NEW
- Critical #10 (API Key clear) 在 24h 1.5 day 都被排隊靠後

**24h+1.5 day 累積 sprint 質量**：B-（v1 是 B+，v2 因 UX 工作 rate 下降扣分，但 NEW-1 是 high-impact close）

### 修復路徑優先序（v2 update）

1. **P0**：tab-system confirm-overlay 加 Esc/aria/focus trap（template 已在 openConfirmModal 證明 30 行可解）
2. **P0**：tab-live 3 dialog 改用 openConfirmModal — 既然 same file 內已有用例，遷移成本最小
3. **P0**：API Key clear 改 modal+打字確認（24h 持續忽視，已該升 SLA）
4. **P0**：tab-demo close-position / dust 改 openConfirmModal
5. **P1**：mode-tag SSR initial DOM 改 `class="tag tag-grey">--</span>` + JS 切 class 不只 style.color
6. **P1**：linucb_card 兩個 confirm() / alert() 改 openConfirmModal
7. **P1**：countdown 改 1000ms tick + 內部 100ms only 更 progress bar
8. **P2**：settings 拆 4 sub-tab；live 14 sub-section 拆；risk 雙層 sub-tab 改用 collapsible

---

**A3 VERIFICATION v2 DONE** · ✅ 7 / ⚠️ 5 / ❌ 18 / 🆕 7 · 整體 8.3/10 · Critical 5 closed: 4/5
