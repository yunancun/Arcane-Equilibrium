#!/usr/bin/env bash
# rtk-hook-version: 3 (vendored)
#
# 出處:rtk-ai/rtk 官方 Claude Code shim 模板 `hooks/claude/rtk-rewrite.sh`
#   參考 pin SHA: 6785a6c7695d7273e722214a295249a84819b6f0(最終 pin 以 tools/rtk/README.md 為準)
#   License: Apache 2.0(上游 repo LICENSE)
# 為何 vendor 而非用 `rtk init` 散裝產物:
#   1. 版本控制:shim 入 repo 三端同步,行為可審計、可回溯,不依賴各機 init 時點的模板版本。
#   2. fail-open 守衛:rtk / jq 缺失時必須「靜默透傳」(exit 0 無輸出)。Linux 端 rtk 二進制
#      可能晚於 settings.json 到位,期間每一次 Bash 呼叫都會經過本 hook——任何噪音或非零
#      exit 都是事故。對模板僅有兩處行為改動,皆為靜默化(對齊上游 README
#      「Exits silently (exit 0) on any failure」的文檔意圖):
#      (a) 缺 jq / 缺 rtk 的 stderr 警告移除,改純 exit 0;
#      (b) stdin 解析 jq 加 2>/dev/null(與上游對 rtk rewrite 的自我靜默一致)。
#
# 協議(忠實照抄上游;改寫規則的單一事實來源在 rtk 的 src/discover/registry.rs,
# 要加/改規則改 Rust 端 registry,不改本檔):
#   `rtk rewrite` exit code:
#     0 + stdout  找到改寫且無 deny/ask 規則命中 → 自動放行(permissionDecision=allow)
#     1           無 RTK 等價指令 → 原樣透傳
#     2           命中 deny 規則 → 透傳,交給 Claude Code 原生 deny 規則處理(絕不繞過權限模型)
#     3 + stdout  命中 ask 規則 → 改寫但不帶 permissionDecision,Claude Code 照常向用戶確認
#   其他 / rtk 崩潰 → case * 透傳(fail-open)。
#   rtk 掛死(超時)由 Claude Code 自身的 hook timeout 兜底後照常執行原指令;
#   macOS 預設無 timeout(1),故不在腳本內包 timeout(跨平台紅線)。

# 守衛 1/3:jq 不存在 → 靜默透傳。
if ! command -v jq &>/dev/null; then
  exit 0
fi

# 守衛 2/3:rtk 不存在 → 靜默透傳(Linux 端 rtk 晚到位是預期狀態,不是錯誤)。
if ! command -v rtk &>/dev/null; then
  exit 0
fi

# 版本守衛:`rtk rewrite` 自 0.23.0 起才存在;太舊 → 警告並透傳(仍 fail-open)。
# 結果緩存,避免每次 hook 呼叫都 spawn 一個 `rtk --version`。
CACHE_DIR=${XDG_CACHE_HOME:-$HOME/.cache}
CACHE_FILE="$CACHE_DIR/rtk-hook-version-ok"
if [ ! -f "$CACHE_FILE" ]; then
  RTK_VERSION_RAW=$(rtk --version 2>/dev/null)
  RTK_VERSION=${RTK_VERSION_RAW#rtk }
  RTK_VERSION=${RTK_VERSION%% *}
  if [ -n "$RTK_VERSION" ]; then
    IFS=. read -r MAJOR MINOR PATCH <<<"$RTK_VERSION"
    # 要求 >= 0.23.0
    if [ "$MAJOR" -eq 0 ] && [ "$MINOR" -lt 23 ]; then
      echo "[rtk] WARNING: rtk $RTK_VERSION is too old (need >= 0.23.0). Upgrade: cargo install rtk" >&2
      exit 0
    fi
  fi
  mkdir -p "$CACHE_DIR" 2>/dev/null
  touch "$CACHE_FILE" 2>/dev/null
fi

INPUT=$(cat)
# stdin 解析失敗(理論上 Claude Code 必送合法 JSON)→ CMD 為空 → 下方靜默透傳。
CMD=$(jq -r '.tool_input.command // empty' <<<"$INPUT" 2>/dev/null)

if [ -z "$CMD" ]; then
  exit 0
fi

# 守衛 3/3:改寫 + 權限判定全部委派 Rust 二進制;rtk rewrite 自身崩潰/非預期
# exit code 由下方 case 的 * 臂透傳(fail-open)。
REWRITTEN=$(rtk rewrite "$CMD" 2>/dev/null)
EXIT_CODE=$?

case $EXIT_CODE in
  0)
    # 找到改寫且無權限規則命中 — 可安全自動放行。
    # 若輸出與原指令相同,代表指令本來就在用 RTK,直接透傳。
    [ "$CMD" = "$REWRITTEN" ] && exit 0
    ;;
  1)
    # 無 RTK 等價指令 — 原樣透傳。
    exit 0
    ;;
  2)
    # 命中 deny 規則 — 透傳,讓 Claude Code 原生 deny 規則處理。
    exit 0
    ;;
  3)
    # 命中 ask 規則 — 改寫但「不」自動放行,讓 Claude Code 向用戶確認。
    ;;
  *)
    exit 0
    ;;
esac

if [ "$EXIT_CODE" -eq 3 ]; then
  # ask:改寫指令,省略 permissionDecision,Claude Code 照常提示用戶確認。
  jq -c --arg cmd "$REWRITTEN" \
    '.tool_input.command = $cmd | {
      "hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "updatedInput": .tool_input
      }
    }' <<<"$INPUT"
else
  # allow:改寫指令並自動放行。
  jq -c --arg cmd "$REWRITTEN" \
    '.tool_input.command = $cmd | {
      "hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "allow",
        "permissionDecisionReason": "RTK auto-rewrite",
        "updatedInput": .tool_input
      }
    }' <<<"$INPUT"
fi
