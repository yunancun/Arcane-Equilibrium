from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BIN_ROOT = ROOT / "rust/openclaw_engine/src/bin"
RUNNER = BIN_ROOT / "replay_runner.rs"
SPLIT_DIR = BIN_ROOT / "replay_runner"


def _loc(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines())


def test_replay_runner_root_stays_thin_orchestration_entrypoint() -> None:
    text = RUNNER.read_text(encoding="utf-8")

    assert _loc(RUNNER) <= 800
    assert '#[path = "replay_runner/manifest.rs"]' in text
    assert '#[path = "replay_runner/config.rs"]' in text
    assert '#[path = "replay_runner/calibration.rs"]' in text
    assert '#[path = "replay_runner/manifest_tests.rs"]' in text


def test_replay_runner_split_modules_stay_below_hard_limit() -> None:
    modules = {
        path.name: _loc(path)
        for path in SPLIT_DIR.glob("*.rs")
    }

    assert set(modules) == {
        "calibration.rs",
        "config.rs",
        "manifest.rs",
        "manifest_tests.rs",
    }
    assert all(loc <= 800 for loc in modules.values())
