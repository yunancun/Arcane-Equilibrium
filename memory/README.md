# Memory snapshot — Claude Code auto-memory for this repo

This directory is a **snapshot** of the CC auto-memory accumulated on the Linux
trade-core host, committed into the repo to sync across machines (Mac dev, other
Linux boxes, future CI sandboxes).

本目錄為 Linux trade-core 上 CC 累積的 auto-memory 快照，提交進 repo 讓多機共享。

## Source of truth (live)
- Linux authoritative path: `~/.claude/projects/-home-ncyu-BybitOpenClaw-srv/memory/`
  （`-home-ncyu-BybitOpenClaw` 與 `-home-ncyu` 是同路徑的 symlink）
- Repo snapshot: `srv/memory/` （this directory / 本目錄）

## How to sync to a new machine (e.g. Mac dev)

On the new machine, after `git pull`:

```bash
# Replace <MAC_PROJECT_KEY> with the slash-to-dash form of your absolute
# $OPENCLAW_BASE_DIR, e.g. /Users/ncyu/Projects/TradeBot/srv → -Users-ncyu-Projects-TradeBot-srv
MAC_PROJECT_KEY="-Users-ncyu-Projects-TradeBot-srv"

mkdir -p "$HOME/.claude/projects/$MAC_PROJECT_KEY"
rsync -av --delete "$OPENCLAW_BASE_DIR/memory/" "$HOME/.claude/projects/$MAC_PROJECT_KEY/memory/"
```

Verify CC sees it on next launch:

```bash
ls "$HOME/.claude/projects/$MAC_PROJECT_KEY/memory/MEMORY.md"
```

## How to refresh this snapshot (from Linux)

When memory has been updated during a session and you want to sync it across:

```bash
rsync -av --delete "$HOME/.claude/projects/-home-ncyu-BybitOpenClaw-srv/memory/" "$OPENCLAW_BASE_DIR/memory/"
cd "$OPENCLAW_BASE_DIR"
git add memory/
git commit -m "chore(memory): refresh snapshot from live CC memory"
git push
```

## Bidirectional sync caveat

If Mac CC writes new memories and you want them to flow back to Linux, run the
same rsync in reverse from the Mac side into the repo, then push. Resolving
conflicts is manual — memories are append-mostly so conflicts are rare, but
check `MEMORY.md` index diffs carefully.

兩邊同向合併不會自動發生。memory 多為 append-only，衝突罕見；若兩邊同時改同一
memory 檔，以手動解為主，特別注意 `MEMORY.md` index 差異。

## What lives here

- `MEMORY.md` — the index (~150 chars per entry, loaded into every CC session)
- `<type>_<topic>.md` — individual memory files (types: user / feedback / project / reference)
- `archive/` — superseded / stale memories kept for historical reference
