"""OPS-F1 (2026-07-15) 守門:長命進程 log 重導向必須 O_APPEND('>>')。

病理:缺 O_APPEND 的 fd × logrotate copytruncate → 截斷後寫入 offset 不回捲 →
NUL 前綴 sparse 檔(表觀 size 立回閾值 → 每小時輪替空轉),.gz 歸檔開頭全 NUL
毀法證可讀性(法證:trade-core engine.log.1.gz 2026-06-27 開頭全 NUL)。

本測試釘死兩個不變量,防止任一側被單獨回退:
1. 三個啟動腳本對 engine.log / api.log 的 spawn 重導向全部為 '>>',無 O_TRUNC 殘留;
2. logrotate conf 對兩 log(var 真身 + /tmp 舊路徑保險)皆有 copytruncate stanza,
   且全檔不用 maxsize/dateext(2026-07-15 教訓:無 daily/weekly 排程的 conf 中
   maxsize 退化為默認 1MiB size 基線;dateext 同日二次觸頂因檔名衝突被跳過)。
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
HELPER = REPO_ROOT / "helper_scripts"

SPAWN_SCRIPTS = ("restart_all.sh", "fresh_start.sh", "clean_restart.sh")
LONG_LIVED_LOGS = ("engine.log", "api.log")


def _noncomment_lines(text: str):
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped and not stripped.startswith("#"):
            yield line


def test_engine_and_api_spawn_redirects_are_append_only() -> None:
    for name in SPAWN_SCRIPTS:
        text = (HELPER / name).read_text(encoding="utf-8")
        for log in LONG_LIVED_LOGS:
            target = f'"$DATA_DIR/{log}"'
            append_re = re.compile(r">>\s*" + re.escape(target))
            trunc_re = re.compile(r"(?<!>)>\s*" + re.escape(target))
            append_hits = 0
            for line in _noncomment_lines(text):
                if target not in line:
                    continue
                if append_re.search(line):
                    append_hits += 1
                    continue
                assert not trunc_re.search(line), (
                    f"{name} 對 {log} 殘留 O_TRUNC '>' 重導向(OPS-F1 回歸): {line!r}"
                )
            assert append_hits >= 1, (
                f"{name} 找不到 {log} 的 '>>' spawn 重導向——啟動行被移除或改寫,"
                "請同步更新本守門測試"
            )


def test_logrotate_conf_covers_both_logs_with_copytruncate() -> None:
    conf = (HELPER / "logrotate-openclaw.conf").read_text(encoding="utf-8")
    expected_stanzas = (
        "/home/ncyu/BybitOpenClaw/var/openclaw/engine.log",
        "/tmp/openclaw/engine.log",
        "/home/ncyu/BybitOpenClaw/var/openclaw/api.log",
        "/tmp/openclaw/api.log",
    )
    for path in expected_stanzas:
        m = re.search(re.escape(path) + r"\s*\{(?P<body>[^}]*)\}", conf)
        assert m is not None, f"logrotate conf 缺 stanza: {path}"
        body = m.group("body")
        assert "copytruncate" in body, f"{path} stanza 缺 copytruncate"
        assert "missingok" in body, f"{path} stanza 缺 missingok"
        assert re.search(r"\bsize\s+\S+", body), f"{path} stanza 缺 size 行"
        assert re.search(r"\brotate\s+[1-9]\d*", body), (
            f"{path} stanza 缺 rotate 行(logrotate 默認 rotate 0=輪替即刪檔)"
        )


def test_logrotate_conf_avoids_maxsize_and_dateext() -> None:
    conf = (HELPER / "logrotate-openclaw.conf").read_text(encoding="utf-8")
    for line in _noncomment_lines(conf):
        assert "maxsize" not in line, (
            f"logrotate conf 出現 maxsize(無排程 conf 中退化為 1MiB 基線): {line!r}"
        )
        assert "dateext" not in line, (
            f"logrotate conf 出現 dateext(同日二次觸頂檔名衝突破 size-cap 語意): {line!r}"
        )
