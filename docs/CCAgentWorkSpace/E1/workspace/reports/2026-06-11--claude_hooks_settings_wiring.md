# E1 Report — Claude Code hooks 接線(settings.json + rtk-rewrite + session-start)

日期:2026-06-11
任務:為 srv repo 建 Claude Code hooks 全新接線(rtk PreToolUse 壓縮層 + SessionStart 熱規則注入),含 gitignore 白名單、CLAUDE.md 指針節、.codex 鏡像 hint。
狀態:**DONE,待 E2 審查。未 commit(PM 統一批次)。**

## 1. 修改清單(footprint = 3 新檔 + 4 改檔,全在派發所有權內)

| 檔 | 動作 | 內容 |
|---|---|---|
| `.claude/settings.json` | 新建 | env RTK_TELEMETRY_DISABLED=1 + SessionStart/PreToolUse hooks |
| `.claude/hooks/rtk-rewrite.sh` | 新建(+x) | vendored rtk 官方 shim(v3)+ 靜默 fail-open |
| `.claude/hooks/session-start.sh` | 新建(+x) | PM 定稿熱規則逐字注入(additionalContext) |
| `.gitignore` | +3 行 | 白名單區(:102-104)追加 settings.json / hooks / hooks/** |
| `CLAUDE.md` | +11 行 | §八 BG-wave 段後加 Token hygiene and hooks 指針節 |
| `.codex/MEMORY.md` | +13 行 | 新節 Claude Code Hooks Mirror(rtk 壓縮+tee 規則、skill description=觸發條件) |
| `.codex/SUBAGENT_EXECUTION_RULES.md` | +9/-1 行 | 新節 Completion contract(四態,指針 .claude/agents/PM.md)+ Last updated 日期 |

dirty-tree 紀律:`git diff -U0` 驗證 4 個改檔 hunks 全為本任務(CLAUDE.md 單 hunk @205+11;.gitignore @102+3;codex 兩檔各一節);`.claude/agents/*`、`skills/*` 等他 session ` M` 檔未碰。

## 2. settings.json 全文

```json
{
  "env": {
    "RTK_TELEMETRY_DISABLED": "1"
  },
  "hooks": {
    "SessionStart": [
      {
        "matcher": "startup|clear|compact",
        "hooks": [
          {
            "type": "command",
            "command": "\"$CLAUDE_PROJECT_DIR\"/.claude/hooks/session-start.sh"
          }
        ]
      }
    ],
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "\"$CLAUDE_PROJECT_DIR\"/.claude/hooks/rtk-rewrite.sh"
          }
        ]
      }
    ]
  }
}
```

## 3. Schema 依據(rtk 模板出處 — 檔案路徑 + 行號)

樣本 checkout:`/tmp/repo-eval/rtk` @ `6785a6c7695d7273e722214a295249a84819b6f0`(2026-06-09;**參考 SHA,最終 pin 以 `tools/rtk/README.md` 為準** — 該檔由並行 E1 產出,本任務僅引用路徑)。

- **PreToolUse 條目結構**:`src/hooks/init.rs:1087-1093`(`insert_hook_entry`,程式化注入的權威形狀)+ `:513-521`(`print_manual_instructions` 同形)→ `{"matcher":"Bash","hooks":[{"type":"command","command":...}]}`。
- **SessionStart 結構**:`/tmp/repo-eval/superpowers/hooks/hooks.json:3-14`(matcher `startup|clear|compact`)。
- **schema 出入裁決**:superpowers 條目多 `"async": false` 欄;rtk 模板無此欄。按任務指示以 rtk 模板為準 → **省略 async**(亦為 Claude Code 默認值,語義相同)。
- **shim 正本**:`/tmp/repo-eval/rtk/hooks/claude/rtk-rewrite.sh:1-101`(`rtk-hook-version: 3`,thin delegating hook)。注意 repo 內另有 `.claude/hooks/rtk-rewrite.sh`(dogfood 舊變體,含 audit-log/set -e)— **未採用**,canonical 是 `hooks/claude/` 下的 v3。
- **exit-code 協議**:shim 正本 :10-14 註釋 + :58-79 case(0=改寫放行/1=透傳/2=deny 交原生/3=改寫仍確認)。
- **輸出 JSON**:shim 正本 :81-101(`hookSpecificOutput.hookEventName/permissionDecision/updatedInput`;ask 臂刻意省略 permissionDecision → 不繞權限模型)。
- **RTK_TELEMETRY_DISABLED**:`src/core/telemetry.rs:29`(`=="1"` 即關閉)— env 變數名實證正確。
- **session-start 注入格式**:`/tmp/repo-eval/superpowers/hooks/session-start`(Claude Code 分支:`hookSpecificOutput.{hookEventName:"SessionStart",additionalContext}`)。
- 備考:`src/hooks/constants.rs:12` 有新式 `CLAUDE_HOOK_COMMAND="rtk hook claude"`(免 shim)。**刻意不用**:rtk 未安裝時該 command 每次 Bash 呼叫都 exit 127 噴錯;vendored shim 才能做到「rtk 缺失=靜默透傳」的生死要求。

## 4. 兩腳本關鍵段

### rtk-rewrite.sh(vendored v3,對模板僅兩處行為改動,檔頭如實列舉)

改動 (a):缺 jq / 缺 rtk → 純 `exit 0`(上游噴 stderr 警告;上游 `hooks/claude/README.md:9` 自述意圖本就是 "Exits silently (exit 0) on any failure",實作與其 README 不一致,我們對齊 README)。改動 (b):stdin 解析 jq 加 `2>/dev/null`(與上游對 `rtk rewrite 2>/dev/null` 的自我靜默一致)。

```bash
# 守衛 1/3 + 2/3:jq / rtk 不存在 → 靜默透傳(Linux rtk 晚到位是預期狀態)
if ! command -v jq &>/dev/null; then exit 0; fi
if ! command -v rtk &>/dev/null; then exit 0; fi
# (中略:上游版本守衛 >=0.23.0 + cache,忠實保留)
INPUT=$(cat)
CMD=$(jq -r '.tool_input.command // empty' <<<"$INPUT" 2>/dev/null)
[ -z "$CMD" ] && exit 0  # (原樣為 if 塊)
# 守衛 3/3:rtk rewrite 崩潰/非預期 exit code → case * 透傳
REWRITTEN=$(rtk rewrite "$CMD" 2>/dev/null); EXIT_CODE=$?
case $EXIT_CODE in
  0) [ "$CMD" = "$REWRITTEN" ] && exit 0 ;;   # 改寫;相同=本來就是 rtk → 透傳
  1) exit 0 ;;  2) exit 0 ;;                  # 無等價 / deny 交原生
  3) ;;                                       # ask:改寫但不帶 permissionDecision
  *) exit 0 ;;                                # 崩潰兜底
esac
# 之後:allow 臂輸出 permissionDecision=allow + updatedInput;ask 臂只 updatedInput(逐字照抄模板 jq 塊)
```

超時:macOS 無 `timeout(1)`(跨平台紅線不硬包),rtk 掛死由 Claude Code 自身 hook timeout 兜底後照常執行原指令 = 等效透傳;已寫入檔頭註釋。

### session-start.sh

```bash
if ! command -v jq &>/dev/null; then exit 0; fi   # fail-open
out=$(printf '%s\n' \
  '<workflow-hot-rules>' \
  ... # PM 定稿 8 行逐字(單引號字面量;內容無 ASCII 單引號/反斜線,驗證安全)
  '</workflow-hot-rules>' \
  | jq -Rs '{hookSpecificOutput: {hookEventName: "SessionStart", additionalContext: (. | rtrimstr("\n"))}}' 2>/dev/null) || exit 0
[ -n "$out" ] || exit 0   # 絕不輸出半截 JSON
printf '%s\n' "$out"
```

轉義「擇穩」決策:用 printf 逐行 | `jq -Rs`(jq 做轉義),**不用 heredoc** — superpowers 在完全相同的 SessionStart hook 場景記錄過 bash 5.3+ heredoc 掛死(obra/superpowers#571),其修法即改 printf;沿用已驗證的穩定路線。`rtrimstr("\n")` 修掉 printf 最後一行帶入的尾換行,使注入內容與 PM INJECT 塊 byte-identical。

## 5. 驗證輸出(Mac,rtk 天然未裝)

```
[1] bash -n rtk-rewrite.sh: PASS
[2] bash -n session-start.sh: PASS
[3] jq empty settings.json: PASS
[4] echo '{"tool_name":"Bash","tool_input":{"command":"git status"}}' | bash .claude/hooks/rtk-rewrite.sh
    → exit=0,stdout+stderr 全空(rtk 缺失靜默透傳 ✓)
[5] session-start 輸出 | jq empty → valid JSON
[6] jq -r '.hookSpecificOutput.additionalContext' 與 INJECT 原文 diff → byte-identical
[7] grep /Users/ncyu|/home/ncyu 於 settings.json+hooks/ → clean
[8] 兩腳本 -rwxr-xr-x(git 會追蹤 +x bit)
```

協議臂測試(fake rtk + `XDG_CACHE_HOME=/tmp` 隔離,測畢清除):

```
exit0+改寫 → {"hookSpecificOutput":{...,"permissionDecision":"allow","updatedInput":{"command":"rtk git status"}}}
exit0+相同 → 無輸出 exit 0(已是 rtk,透傳)
exit1 / exit2 / exit101(crash) → 無輸出 exit 0(透傳)
exit3(ask) → {"hookSpecificOutput":{"hookEventName":"PreToolUse","updatedInput":{...}}}(無 permissionDecision → 照常向用戶確認)
jq 缺失模擬(env PATH=/var/empty /bin/bash)→ 兩腳本皆 exit 0 無輸出
malformed stdin / 缺 .command 欄 → exit 0 無輸出
```

gitignore 生效:`git check-ignore -v` 三新檔命中 `!` 反向規則(:102/:104),`git status` 呈 `??`(可入庫);`.claude/worktrees` 仍命中 `.claude/*`(維持忽略)。

## 6. 治理對照

- 權限模型:ask 臂(exit 3)不帶 permissionDecision、deny 臂(exit 2)透傳交 Claude Code 原生規則 — 照模板,**0 繞過**。協議臂實測佐證。
- fail-open 生死要求:rtk/jq 缺失、rtk 崩潰、malformed input 全部 exit 0 無輸出(Linux rtk 晚到位期間 hook 零干擾)。
- 跨平台:無硬編 user path(grep 自證);`$CLAUDE_PROJECT_DIR`/`$HOME`/`$XDG_CACHE_HOME` 推算;不依賴 `timeout(1)`。
- 注釋規範:新檔中文註釋 + MODULE_NOTE 等級檔頭(出處/SHA/License/為何 vendor/協議);上游英文警告字串保留原樣(greppability)。
- License:上游 Apache 2.0,檔頭已標注出處與 SHA。
- 硬邊界 0 觸碰(無 max_retries/live_execution 等 token);無 SQL/migration;無新 singleton。

## 7. 不確定之處 / 偏差聲明

1. **pin SHA 是參考值**:`6785a6c7…` 取自 /tmp/repo-eval/rtk checkout;最終 pin 權威=並行 E1 的 `tools/rtk/README.md`(寫本報告時尚未出現,僅引用路徑)。若該檔 pin 不同 SHA,需 diff 上游 `hooks/claude/rtk-rewrite.sh` 是否變動(v3 協議穩定,預期無實質差)。
2. **模板兩處靜默化偏差**:(a) 任務明令(「exit 0 無輸出」生死要求)且對齊上游 README 自述;(b) stdin jq 靜默為小決策(與上游 rtk rewrite 自我靜默同哲學),檔頭+本報告雙聲明。
3. **INJECT 塊 989 字元(CJK 為主)**:逐字照 PM 定稿注入;≤300 token 為 PM 的預算宣稱,CJK tokenization 實際 token 數可能高於 300 — 內容裁剪非我 scope,僅如實標注。
4. settings.json 省略 `async` 欄(rtk 模板為準;同 Claude Code 默認)。
5. `.codex/SUBAGENT_EXECUTION_RULES.md` Last updated 日期同步 bump(加節時的格式慣例,小決策)。
6. settings.json 為 project-level,會與各人 user-level settings 合併;若某機曾跑過 `rtk init`(user-level hook),兩 hook 疊跑無害(第二次 rewrite 對已是 rtk 的指令=identical→透傳),但建議該機移除 user-level 舊 hook 保單源。

## 8. Operator / PM 下一步

1. E2 對抗審查本報告 + 7 檔 diff → E4 回歸(Linux 端重點:settings 同步後、rtk 未裝期間 Bash 全鏈零干擾實測;rtk 裝好後真實 rewrite smoke `git status`)→ PM 統一 commit。
2. 真實生效需重啟 Claude Code session(settings/hook 於 session 啟動載入;SessionStart 的 compact 重注入屆時自動生效)。
3. Linux 裝 rtk 依 `tools/rtk/README.md`(並行 E1 產出)後,本接線即活,無需再改任何檔。
