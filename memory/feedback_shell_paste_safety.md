---
name: Shell commands must survive terminal paste
description: Operator runs commands by pasting into macOS Terminal / zsh. Multi-line constructs, indented heredoc EOF, and long commands with shell metachars repeatedly break on paste. Write commands that paste cleanly, or use file-based approach.
type: feedback
originSessionId: e4e30d79-5f1f-4c57-8304-9912d02477df
---
當 operator 要把 shell 指令貼進 macOS Terminal / zsh 執行時，**不得**使用以下會被終端折行或 zsh 解析誤判的構造。Operator 已多次因同一類問題卡住並明確要求停止重犯。

**禁止 / 避免：**

1. **Heredoc (`<<EOF ... EOF`)**：Operator 貼進來 EOF 前面會被保留前導空格 → zsh 看不到結尾標記 → 永遠 `heredoc>`。即便用 `<<-EOF` 也會被 tab/space 混合干擾。改用檔案寫入（`printf > /tmp/x.sql` + `psql -f`）或 `psql -c "..."` 單行。

2. **多行 for/while/if**：寫成跨多行的
   ```
   for x in a b c; do
     ...
   done
   ```
   Terminal 經常在 `do` 前換行，zsh `parse error near 'do'`。**必須寫成單列 one-liner**，分號串接：`for x in ...; do ...; done`，整條一行（不論多長）。

3. **長 command 中間含 `&&` 或 `|` 的換行**：終端把 `-f docker/compose.yml` 折成 `-f` 在一行、`docker/compose.yml` 在下一行 → `unknown shorthand flag: 'f'`。長指令請分拆成多個**獨立**單行指令，每條一個 Enter，不用 `&&` 串。

4. **shell 變數含特殊字元注入雙引號字串**（如密碼含 `(` `)` `$` `"` `\``）：`$PG_PASS` 展開後可能截斷外層 quote → `dquote>`。改用檔案：`printf "SQL ... '%s';\n" "$VAR" > /tmp/x.sql` + 執行檔案，永遠避開 inline quote 地獄。

5. **heredoc 嵌 SQL 裡含引號**：即便 EOF 沒被折斷，SQL 裡的 `'...'` 也會和 heredoc quoting 打架。一律走檔案路徑。

**首選模式：**

- 單行 `psql -c "..."` 或 `docker exec ... psql -c "..."`，SQL 中不含密碼/複雜字元。
- 敏感/複雜 SQL → `printf ... > /tmp/x.sql` → `docker cp` → `psql -f`。
- Loop/batch → 一列 one-liner；超長可先寫成 script 檔（`cat > /tmp/run.sh << ... # 但這又回 heredoc 禁區，改用 Write tool 寫到 repo 下`）。
- 如果真要多行，**在 repo 寫一個 `.sh` 檔**，讓 operator 跑 `bash path/to/script.sh`，永遠不讓 operator 手貼 multi-line shell。

**Why:** Operator 2026-04-20/21 Mac bootstrap session 內至少 5 次卡在 heredoc、for-loop parse error、soft-wrap 截斷、`$VAR` 注雙引號被截斷同一類問題；明確要求記入 memory 不再犯。

**How to apply:** 只要在跟 operator 對話中要他貼 shell 指令執行（Mac zsh / Linux bash 皆適用，Mac 更嚴），先心裡檢查這條指令 A) 是否多行 B) 是否含 heredoc C) 是否含需展開的複雜變數 D) 是否 >120 char 容易軟折行。任一條命中就改用檔案 / 單行 / 腳本檔路徑。
