# Memory — Claude Code auto-memory for this repo（repo＝正本）

This directory is the **canonical store** of the CC auto-memory for this
project, committed into the repo to sync across machines (Mac dev, Linux
trade-core, future CI sandboxes). Mac CC writes land here **directly** (its
project keys' `memory` are symlinks into the repo); the Linux live dir is an
rsync **receiver** of this directory (2026-08-01 起實務).

本目錄為本專案 CC auto-memory 的**正本**：Mac CC 經 symlink 直寫本目錄（事實上的
寫入主流），Linux 端 live 目錄自 2026-08-01 起實務上為 rsync 收端。

## Source of truth（現實拓撲；2026-08-01 更正）
- 正本（source of truth）: `srv/memory/` （this directory / 本目錄）。Mac 兩個
  project key 的 `memory` 均 symlink 進 repo（見下方 2026-07-09 更正節），Mac CC
  寫入直接落在本目錄＝事實上的寫入主流。
- Linux 收端（rsync receiver）: `~/.claude/projects/-home-ncyu-BybitOpenClaw-srv/memory/`
  （`-home-ncyu-BybitOpenClaw` 與 `-home-ncyu` 是同路徑的 symlink）。Linux 端更新
  ＝repo `git pull` 後 rsync repo→live（見下節）；Linux CC session 若在 live 端
  寫入新 memory，須先手動吸收回 repo 再同步。

## How to sync to a new machine (e.g. Mac dev)

> ⚠️ **2026-07-09 correction**: the Mac does **not** rsync memory. Both project
> keys' `memory` are **symlinks into the repo**. The old instruction
> (`rsync -av --delete ... "$HOME/.claude/projects/$MAC_PROJECT_KEY/memory/"`)
> would run `--delete` **onto a symlink of the repo itself** — a footgun. Use
> the symlink setup below instead.

On this Mac, CC actually loads memory via the **no-`srv` project key**
(`-Users-ncyu-Projects-TradeBot`), which chains to the `-srv` key's symlink;
the `-srv` key points straight at the repo. Verified live (`readlink`):

```
~/.claude/projects/-Users-ncyu-Projects-TradeBot-srv/memory
  → /Users/ncyu/Projects/TradeBot/srv/memory            # 直指 repo
~/.claude/projects/-Users-ncyu-Projects-TradeBot/memory
  → ../-Users-ncyu-Projects-TradeBot-srv/memory          # chain 到上者
```

On a new machine, after `git pull`, **create the symlinks** (do not copy):

```bash
# -srv key points straight at the repo ($OPENCLAW_BASE_DIR = your srv abs path)
ln -sfn "$OPENCLAW_BASE_DIR/memory" "$HOME/.claude/projects/-Users-ncyu-Projects-TradeBot-srv/memory"
# no-srv key chains to the -srv key (this is the path CC on this Mac loads)
ln -sfn "../-Users-ncyu-Projects-TradeBot-srv/memory" "$HOME/.claude/projects/-Users-ncyu-Projects-TradeBot/memory"
```

Verify CC sees it on next launch:

```bash
readlink "$HOME/.claude/projects/-Users-ncyu-Projects-TradeBot-srv/memory"
ls "$HOME/.claude/projects/-Users-ncyu-Projects-TradeBot/memory/MEMORY.md"
```

## How to update the Linux live dir (repo → live)

repo 為正本；Linux 端更新一律 `git pull` 後 rsync repo→live。真跑的 `--delete`
會刪掉 live 端獨有檔案，且**對兩邊都存在的檔會直接以 repo 版覆蓋 live 端的修改**
——後者在 rsync dry-run 輸出裡只是一行普通傳輸檔名、不會出現 `deleting`，故 gate
不能只看 deleting 行，必須用 `diff -ru` 檢視**全部**差異：

```bash
cd "$OPENCLAW_BASE_DIR" && git pull --ff-only
# gate：逐項檢視差異。「repo 有而 live 沒有／repo 內容較新」＝正常待同步；
# 發現 live 端獨有內容（live 側新檔**或 live 側對既有檔的新增段落**）即停手，
# 先反向吸收（rsync live→repo **不帶 --delete**）、git diff 檢視後 commit，再回本節重跑
diff -ru "$HOME/.claude/projects/-home-ncyu-BybitOpenClaw-srv/memory/" "$OPENCLAW_BASE_DIR/memory/"
# gate 通過（全部差異均為 repo 較新、live 無獨有內容）後真跑
rsync -av --delete "$OPENCLAW_BASE_DIR/memory/" "$HOME/.claude/projects/-home-ncyu-BybitOpenClaw-srv/memory/"
```

（歷史：2026-08-01 前本節方向相反——live→repo 快照刷新。舊指令保留於 git 史；
repo 轉正本後不再適用。）

## Bidirectional sync caveat

> ⚠️ **2026-07-09 correction (Mac side)**: since the Mac's `memory` is a symlink
> into the repo, Mac CC writes land **directly in `srv/memory/`** — there is no
> "reverse rsync from the Mac" step; just `git add memory/ && git commit && push`
> from the repo. The reverse-rsync text below is retained as history for
> non-symlink setups only.

**2026-08-01 現實務**：Mac→Linux 方向已無任何反向 rsync 步驟——Mac 寫入即
repo，commit＋push 後 Linux 端依上節 repo→live 同步即完成。反向流（Linux
live→repo）只在 Linux CC session 於 live 端寫入新 memory 時發生：手動 rsync
**不帶 `--delete`** 把新／改檔吸收回 repo、檢查 diff 後 commit。

（history, non-symlink setups only）If Mac CC writes new memories and you want
them to flow back to Linux, run the same rsync in reverse from the Mac side
into the repo, then push. Resolving conflicts is manual — memories are
append-mostly so conflicts are rare, but check `MEMORY.md` index diffs
carefully.

兩邊合併不會自動發生。memory 多為 append-only，衝突罕見；若兩邊同時改同一
memory 檔，以手動解為主，特別注意 `MEMORY.md` index 差異。

## What lives here

- `MEMORY.md` — the index (~150 chars per entry, loaded into every CC session)
- `<type>_<topic>.md` — individual memory files (types: user / feedback / project / reference)
- `archive/` — superseded / stale memories kept for historical reference
