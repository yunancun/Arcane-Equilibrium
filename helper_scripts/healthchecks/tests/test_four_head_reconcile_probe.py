"""four_head_reconcile_probe 的 local-mode client 測試。

mirror ``deploy/tests/test_runtime_source_remote_reconcile_probe.py`` 的
local-mode client 模式：本地 git fixture 模擬 Linux checkout、dict 模擬
proc/檔案面。覆蓋：四頭全同步 / engine ancestor 半部署（rust 觸與否雙向）/
stale-tmp-datadir 拒讀 / INDETERMINATE fail-close + CLI exit 3。
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "four_head_reconcile_probe.py"
SPEC = importlib.util.spec_from_file_location("four_head_reconcile_probe", SCRIPT)
probe = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(probe)


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return proc.stdout.strip()


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _init_repo(repo: Path) -> None:
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "Test User")


def _commit_all(repo: Path, message: str) -> str:
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


def _clone(origin: Path, dest: Path) -> None:
    subprocess.run(["git", "clone", "-q", str(origin), str(dest)], check=True)
    _git(dest, "config", "user.email", "test@example.invalid")
    _git(dest, "config", "user.name", "Test User")


def _engine_fixture_client(
    repo: Path,
    data_dir: Path,
    *,
    engine_build_sha: str,
    extra_files: dict[str, str] | None = None,
    environ_override: bytes | None = None,
) -> "probe.LocalFixtureClient":
    boot_history_path = str(data_dir / "boot_history.jsonl")
    lines = [
        # 舊世代 engine 行在前：驗「最後一筆帶 build_sha 的引擎紀錄」勝出。
        json.dumps(
            {
                "component": "openclaw_engine",
                "boot_ts": "2026-07-01T00:00:00Z",
                "build_sha": "0000000000000000000000000000000000000000",
                "pid": 1,
                "binary_path": "/old/openclaw-engine",
            }
        ),
        json.dumps(
            {
                "component": "openclaw_engine",
                "boot_ts": "2026-07-11T10:20:16Z",
                "build_sha": engine_build_sha,
                "pid": 100,
                "binary_path": "/srv/rust/target/release/openclaw-engine",
            }
        ),
        json.dumps(
            {
                "component": "control_api",
                "boot_ts": "2026-07-12T02:44:07+00:00",
                "repo_head": "cafecafecafecafecafecafecafecafecafecafe",
                "pid": 200,
                "workers": None,
            }
        ),
    ]
    environ = environ_override
    if environ is None:
        environ = (
            b"HOME=/home/test\0OPENCLAW_DATA_DIR="
            + str(data_dir).encode()
            + b"\0OTHER=1\0"
        )
    files = {boot_history_path: "\n".join(lines) + "\n"}
    files.update(extra_files or {})
    return probe.LocalFixtureClient(
        repo,
        pids=[100, 999],
        # 999 模擬 pgrep -f 自我命中（remote shell 的 command line 含 pattern）。
        comm_by_pid={100: "openclaw-engine", 999: "bash"},
        environ_by_pid={100: environ},
        files=files,
    )


def test_all_four_sync(tmp_path: Path) -> None:
    origin = tmp_path / "origin_repo"
    _init_repo(origin)
    _write(origin / "rust/openclaw_engine/src/lib.rs", "// v1\n")
    _write(origin / "docs/note.md", "v1\n")
    _commit_all(origin, "c1")
    _write(origin / "docs/note.md", "v2\n")
    head = _commit_all(origin, "c2")

    work = tmp_path / "work"
    _clone(origin, work)

    client = _engine_fixture_client(
        work,
        tmp_path / "var_openclaw",
        # 用 12 碼短前綴驗 Mac 側 rev-parse 展開。
        engine_build_sha=head[:12],
    )
    packet = probe.build_packet(
        work, client=client, remote_repo_root=str(work), remote_label="fixture"
    )
    assert packet["status"] == "ALL_FOUR_SYNC"
    assert packet["heads"]["mac_head"] == head
    assert packet["heads"]["true_remote_head"] == head
    assert packet["heads"]["true_remote_head_source"] == "ls_remote"
    assert packet["heads"]["true_remote_head_stale_possible"] is False
    assert packet["heads"]["linux_head"] == head
    assert packet["heads"]["engine_build_sha"] == head
    # 順帶回報 control_api repo_head（TODO pin-drift-hygiene packet 驗收面）。
    assert (
        packet["heads"]["control_api_repo_head"]
        == "cafecafecafecafecafecafecafecafecafecafe"
    )
    assert packet["mutated_remote"] is False
    assert packet["mutated_local"] is False


def test_engine_ancestor_half_deploy_rust_gap(tmp_path: Path) -> None:
    origin = tmp_path / "origin_repo"
    _init_repo(origin)
    _write(origin / "rust/openclaw_engine/src/lib.rs", "// v1\n")
    _write(origin / "docs/note.md", "v1\n")
    engine_sha = _commit_all(origin, "c1")
    _write(origin / "rust/openclaw_engine/src/lib.rs", "// v2\n")
    _commit_all(origin, "c2 rust change")

    work = tmp_path / "work"
    _clone(origin, work)

    client = _engine_fixture_client(
        work, tmp_path / "var_openclaw", engine_build_sha=engine_sha
    )
    packet = probe.build_packet(
        work, client=client, remote_repo_root=str(work), remote_label="fixture"
    )
    assert packet["classification_base"] == "GIT_SYNC_ENGINE_ANCESTOR"
    assert packet["status"] == "HALF_DEPLOY_REBUILD_REQUIRED"
    assert packet["gap"]["touches_rust_non_exempt"] is True
    assert "rust/openclaw_engine/src/lib.rs" in packet["gap"]["rust_paths_sample"]


def test_engine_ancestor_source_only_gap(tmp_path: Path) -> None:
    origin = tmp_path / "origin_repo"
    _init_repo(origin)
    _write(origin / "rust/openclaw_engine/src/lib.rs", "// v1\n")
    _write(origin / "docs/note.md", "v1\n")
    engine_sha = _commit_all(origin, "c1")
    # gap 僅 docs（豁免面）+ 非 rust 的 helper（非豁免但不觸 rust）→ SOURCE_ONLY_DRIFT。
    _write(origin / "docs/note.md", "v2\n")
    _write(origin / "helper_scripts/some_tool.py", "x = 1\n")
    _commit_all(origin, "c2 source only")

    work = tmp_path / "work"
    _clone(origin, work)

    client = _engine_fixture_client(
        work, tmp_path / "var_openclaw", engine_build_sha=engine_sha
    )
    packet = probe.build_packet(
        work, client=client, remote_repo_root=str(work), remote_label="fixture"
    )
    assert packet["classification_base"] == "GIT_SYNC_ENGINE_ANCESTOR"
    assert packet["status"] == "SOURCE_ONLY_DRIFT"
    assert packet["gap"]["touches_rust_non_exempt"] is False
    assert packet["gap"]["changed_path_count"] == 2


def test_stale_tmp_data_dir_refused(tmp_path: Path) -> None:
    origin = tmp_path / "origin_repo"
    _init_repo(origin)
    _write(origin / "docs/note.md", "v1\n")
    _commit_all(origin, "c1")
    work = tmp_path / "work"
    _clone(origin, work)

    # environ 無 OPENCLAW_DATA_DIR；/tmp/openclaw 放 stale decoy —— 探針必須
    # fail-close 拒讀，絕不默認 /tmp/openclaw（否則會回報錯誤 build_sha）。
    stale_decoy = json.dumps(
        {
            "component": "openclaw_engine",
            "boot_ts": "2026-07-07T13:48:57Z",
            "build_sha": "54d5fbf99dcbc3de13375debfa38f32367262312",
            "pid": 1,
            "binary_path": "/old",
        }
    )
    client = _engine_fixture_client(
        work,
        tmp_path / "var_openclaw",
        engine_build_sha="deadbeef",
        extra_files={"/tmp/openclaw/boot_history.jsonl": stale_decoy + "\n"},
        environ_override=b"HOME=/home/test\0OTHER=1\0",
    )
    packet = probe.build_packet(
        work, client=client, remote_repo_root=str(work), remote_label="fixture"
    )
    assert packet["status"] == "INDETERMINATE"
    assert "engine_environ_missing_data_dir_refuse_tmp_default" in packet["reasons"]
    assert packet["heads"]["engine_build_sha"] is None
    # decoy 檔絕不能被讀到（拒讀而非回落）。
    assert "/tmp/openclaw/boot_history.jsonl" not in client.read_file_paths


def test_indeterminate_fail_close_and_cli_exit_3(tmp_path: Path, capsys) -> None:
    origin = tmp_path / "origin_repo"
    _init_repo(origin)
    _write(origin / "docs/note.md", "v1\n")
    _commit_all(origin, "c1")
    work = tmp_path / "work"
    _clone(origin, work)

    # Linux git 面不可用 + 無 engine 進程 → INDETERMINATE（fail-close，不猜）。
    client = probe.LocalFixtureClient(work, git_available=False)
    packet = probe.build_packet(
        work, client=client, remote_repo_root=str(work), remote_label="fixture"
    )
    assert packet["status"] == "INDETERMINATE"
    assert "linux_head_unavailable" in packet["reasons"]
    assert "engine_process_not_found" in packet["reasons"]

    # CLI：--fail-on-drift 於非 ALL_FOUR_SYNC → exit 3；--json-output 寫出 packet。
    out = tmp_path / "packet.json"
    rc = probe.main(
        [
            "--local-repo-root",
            str(work),
            "--remote-repo-root",
            str(work),
            "--json-output",
            str(out),
            "--fail-on-drift",
        ],
        client=client,
    )
    capsys.readouterr()
    assert rc == 3
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "four_head_reconcile_v1"
    assert payload["status"] == "INDETERMINATE"
    assert payload["boundary"].startswith("read-only git/ssh/proc/file probe")
