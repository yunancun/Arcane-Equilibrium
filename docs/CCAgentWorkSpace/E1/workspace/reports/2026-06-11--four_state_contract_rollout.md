# E1 報告 — subagent 四態契約落地（2026-06-11）

## 任務摘要

按 PM 定稿設計落地「subagent 四態回報協議」（借 obra/superpowers MIT，適配本 repo）：
`agent-wave` workflow 自動 append 收尾契約 footer + contextPath 共同背景注入 + STATUS 解析統計；
PM/E1/E1a/E2/E4/BB/R4 七個 agent 檔各加對應節；六角色 memory 各 append 一條生效條目。
**未 commit**（PM 統一批次提交）。

## 修改清單（14 檔，全部在派工檔案所有權內）

| 檔 | delta | 內容 |
|---|---|---|
| `.claude/workflows/agent-wave.js` | +46/−9（62→99 行） | CONTRACT footer / contextPath / STATUS 解析 / 回傳 statuses 索引 / 檔頭+whenToUse 同步 |
| `.claude/agents/PM.md` | +7（≤16 ✓） | 新節「派工四態契約與升級階梯」（處置表/餵全文/contextPath SOP/解析責任） |
| `.claude/agents/E1.md` | +5（≤8 ✓） | 新節「收尾契約（四態回報）」 |
| `.claude/agents/E1a.md` | +5（≤8 ✓） | 同上 |
| `.claude/agents/E2.md` | +4（≤6 ✓） | 新節「審查順序鐵律」（stage 0=spec 合規先於代碼質量） |
| `.claude/agents/E4.md` | +5（≤8 ✓） | 新節「rtk 壓縮層下的測試紀律」（四元組/tee log/rtk proxy） |
| `.claude/agents/BB.md` | +3（≤4 ✓） | 新節「外部抓取物圍欄」（`<untrusted_content>`） |
| `.claude/agents/R4.md` | +5（≤10 ✓） | 新節「Memory 巡檢追加項」（配額 ≤40 先 MERGE/heat 欄/演變軌跡） |
| 6× `docs/CCAgentWorkSpace/{E1,E2,E4,BB,PM,R4}/memory.md` | 各 +3~4 | 各 append 一條 2026-06-11 契約生效條目（E1 條目只記契約，不含本次施工內容，照派工要求） |

## 關鍵 diff — agent-wave.js

```diff
+// 四態收尾契約 footer（四態協議借 obra/superpowers MIT；PM 處置表正本見 PM.md「派工四態契約與升級階梯」）。
+// 為什麼 append 在 runner：保證 wave 內每個 agent 收到同一份契約，PM 手寫 prompt 漏附時不破洞。
+const CONTRACT = `
+
+【收尾契約】最終回覆第一行必須是 \`STATUS: DONE|DONE_WITH_CONCERNS|NEEDS_CONTEXT|BLOCKED\` + 一行理由。完整報告寫 docs/CCAgentWorkSpace/<你的角色>/workspace/reports/YYYY-MM-DD--<desc>.md；回覆正文只給 ≤500 字摘要 + 報告路徑 + 關鍵結論，不貼全文。說「做不到/卡住」永遠可以；爛活比沒活更糟，絕不沉默交出不確定的工作。`
...
+  if (t.contextPath !== undefined && (typeof t.contextPath !== 'string' || !t.contextPath.trim())) {
+    throw new Error(`args[${i}] contextPath 存在時必須是非空字串`)
+  }
...
+// 完整派發 prompt = 共同背景前綴（可選）+ 原 prompt + 收尾契約。CONTRACT 恰 append 一次：
+// Retry 走 RELAY + fullPrompt(t)，只多接力前綴，不會疊兩份 CONTRACT。
+const fullPrompt = (t) => (t.contextPath ? `【共同背景】先讀 ${t.contextPath}（wave 共同背景檔，PM 已寫好）。\n\n` : '') + t.prompt + CONTRACT
...
-const first = await parallel(args.map((t, i) => () => agent(t.prompt, mkOpts(t, i, 'Wave'))))
+const first = await parallel(args.map((t, i) => () => agent(fullPrompt(t), mkOpts(t, i, 'Wave'))))
...
-  const second = await parallel(deadIdx.map(i => () => agent(RELAY + args[i].prompt, mkOpts(args[i], i, 'Retry'))))
+  const second = await parallel(deadIdx.map(i => () => agent(RELAY + fullPrompt(args[i]), mkOpts(args[i], i, 'Retry'))))
...
+const STATUS_RE = /^\s*STATUS:\s*(DONE_WITH_CONCERNS|DONE|NEEDS_CONTEXT|BLOCKED)\b/m
+const statuses = {}
+args.forEach((t, i) => {
+  const m = typeof results[i] === 'string' ? STATUS_RE.exec(results[i]) : null
+  statuses[key(t, i)] = results[i] === null ? 'FAILED' : (m ? m[1] : 'UNKNOWN')
+})
+const counts = {}
+Object.values(statuses).forEach(s => { counts[s] = (counts[s] || 0) + 1 })
+log(`STATUS 統計：${Object.entries(counts).map(([s, n]) => `${s}=${n}`).join(' ')}`)
+const attention = Object.keys(statuses).filter(k => statuses[k] === 'NEEDS_CONTEXT' || statuses[k] === 'BLOCKED')
+if (attention.length) {
+  log(`【需 PM 處置，不自動重派】${attention.map(k => `${k}=${statuses[k]}`).join('、')}（NEEDS_CONTEXT→補餵缺的 context 重派；BLOCKED→換強模型/拆任務/升級 operator）`)
+}
...
-return out
+return { statuses, attention, results: out }
```

另：檔頭註釋 + `meta.whenToUse` 同步寫入四態行為與 `contextPath?` 欄；args 陣列錯誤訊息補 `contextPath?`。
null 續作棒邏輯 / journal cache 語義 / `mkOpts` / RELAY 前綴防 cache 誤命中，全部不變。

### 設計小決策（派工允許的擇一，附理由）

1. **回傳結構選「字串原樣 + 另回 statuses map」**（`return { statuses, attention, results }`），未選 per-value `{status, text}`：
   - results 各 value 保留原始 final message 純字串 → PM.md 既有回傳契約「value = sub-agent final message」不破，STATUS 行本就在字串首行可直讀；
   - `{status, text}` 要 PM 取文多剝一層、且 N 個 value 全變形；頂層加 `statuses`/`attention` 索引是單點改動；
   - journal 是步級（agent call）cache，回傳 shape 改動不影響 resumeFromRunId 重放。
2. **STATUS 解析容錯**：`/m` 全文取第一個 STATUS 行（不死磕「必須是第 1 行」——agent 偶有前言時仍能收）；缺行=UNKNOWN、兩輪皆 null=FAILED。`DONE_WITH_CONCERNS` 置 alternation 首防 `DONE` 前綴吞匹配（harness 已 bite 驗證）。
3. **attention 只含 NEEDS_CONTEXT/BLOCKED**：FAILED（null）已有既有「仍失敗」log 與 FAILED 字串標記，不重複入列。
4. **contextPath 注入文案用全形標點**（`（wave 共同背景檔，PM 已寫好）`）：匹配檔內中文 prose 既有文體；語義與派工正本逐字等價。

## 驗證（全部親跑）

1. `node --check .claude/workflows/agent-wave.js` → exit 0 PASS（派工指定 gate）。
   ⚠ 發現：**Node v26 對含 `export` 的 .js 走 ESM 偵測 lane 後 `--check` 是靜默 no-op**（實測注入爛語法 `const y = (` 也 exit 0；CJS lane 才真解析）。故字面 gate 本身無牙。
2. **有牙等價檢**（剝 `export` + async function wrapper → 強制 CJS lane 真解析）：PASS；且 wrapper 檢法自身 bite 驗證（注入爛行 → exit 1）。配方：
   ```bash
   { echo 'async function __wf_check(args, phase, log, parallel, agent) {'; sed 's/^export const meta/const meta/' .claude/workflows/agent-wave.js; echo '}'; } > /tmp/aw.js && node --check /tmp/aw.js
   ```
3. **stub-runtime 行為 harness（真跑 workflow body，14 斷言全過）**：contextPath 注入/不注入、CONTRACT 每個派發恰一次（含 Retry 不疊兩份）、Retry=RELAY+fullPrompt、四態各值解析、次行 STATUS 容錯、`DONE_WITH_CONCERNS` 不被 DONE 吞、缺行→UNKNOWN、attention 恰=BLOCKED+NEEDS_CONTEXT、results value 純字串、統計與醒目 log 行存在、contextPath 空字串 fail-fast。
4. `grep -cE 'Date\.now|Math\.random|new Date\('` → 0（禁字 clean）。
5. 各 .md diff 行數逐檔 `git diff --numstat` 對照上限：全過（見修改清單表）。
6. 14 個 owned 檔 delta 恰為我的增量，無 sibling 疊改。

## 治理對照

- 硬邊界 token（max_retries/live_execution_allowed/execution_authority/system_mode）：0 觸碰。
- 0 migration / 0 Rust / 0 production Python；改動全在 `.claude/` 配置層 + 文檔層。
- 跨平台路徑：新增內容 0 硬編碼 user path（CONTRACT 內路徑為 repo 相對路徑）。
- 注釋中文（bilingual-comment-style）：新增註釋全中文，解釋 why（append 在 runner 的理由、CONTRACT 恰一次的理由、回傳兼容理由）。
- 未 commit；工作樹另有大量非我改動（`.claude/skills/*`、`.codex/*`、`.gitignore`、`CLAUDE.md`、未追蹤 `.claude/hooks/`+`settings.json` = 並行 session rtk 落地），按 multi-session 紀律未碰未還原。PM 批次 commit 時建議用 `git commit --only` 列舉我 14 檔 + 本報告，與 rtk 批次分開。

## 不確定之處

1. **字面 `node --check` gate 無牙**（Node v26 ESM 偵測 lane no-op）——已用有牙 wrapper 等價檢補強並 bite 自證；建議 PM 把 wrapper 配方採納為 workflow .js 的標準檢法（E1a node --check 規則本就允許「或等價語法檢查」）。
2. 回傳 shape 從扁平 map → `{statuses, attention, results}`：無代碼消費者（return 直接渲染給 PM session），但 PM 既有心智模型需更新——PM.md 新節已寫明「agent-wave 回傳 statuses 解析索引」。
3. CLAUDE.md 本次施工中被並行 session 更新（rtk hooks + 四態契約指針 canonical→PM.md）——與本落地一致無衝突，僅供 E2 review 時知悉時序。

## Operator / PM 下一步

1. E2 對抗審查本 14 檔 diff（重點：agent-wave.js 的 CONTRACT 單次 append 與 STATUS regex；PM.md 處置表與設計正本逐字對照）。
2. E4：本改動無 pytest/cargo 面；建議以本報告 harness 斷言清單為回歸基準（必要時把 harness 轉正式檔，現為 /tmp 即棄）。
3. PM commit 時與 sibling rtk 批次分開 `--only` 提交。
