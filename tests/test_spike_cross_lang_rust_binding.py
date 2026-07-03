"""Sprint 1B AC-7 — Rust ↔ Python cross-language 1e-4 fixture (FULL PASS).

MODULE_NOTE
模塊用途:
  AC-7 spec §AC-7 字面要求 `engine_cpu_pct` 5 sample window mean / sigma 在
  Rust 端與 Python replay 端 1e-4 容差對齊。

  Sprint 1A-ζ Phase 3b 已交付 PARTIAL PASS PoC
  (`tests/test_spike_cross_lang_fixture.py`,7/7 PASS,Python naive two-pass +
  Welford + numpy 三實作互驗 algorithm contract 數位 fingerprint)。

  本 file 是 Sprint 1B 補對齊:Rust binding (Option A subprocess + JSON):
    - subprocess.run `cargo test --release --features spike --test
      m3_cross_lang_window_fixture -- --nocapture`
    - parse stdout 中 `RUST_FIXTURE_JSON: {...}` marker
    - 比對 Rust 算的 mean / sigma 與 Python expected 1e-4 對齊
    - AC-7 PARTIAL PASS → FULL PASS

  Sprint 2+ carry-over (per spec §5.3 H-18):PyO3 binding 全套替換 subprocess
  binding (in-process call, 更快, 更輕)。

設計:
  - input: [10.0, 20.0, 30.0, 25.0, 15.0] (Phase 3b PoC line 40 同)
  - Python expected mean = 20.0
  - Python expected sample stddev (ddof=1) = sqrt(62.5) ≈ 7.905694150420948
  - Rust 端讀同 input, println! 輸出 JSON, Python parse 比對

依賴:
  - 標準 lib (json / re / shutil / subprocess / pathlib / math / os)
  - 不需 numpy;cargo workspace 路徑走 SRV_ROOT 推算
  - cargo binary 走 _locate_cargo() 多層定位 (PATH → ~/.cargo/bin →
    rustup which → ~/.rustup/toolchains/*/bin);全部缺席才 skipif
  - cargo workspace 在 srv/rust/openclaw_engine/Cargo.toml

硬邊界:
  - 純 subprocess + JSON parse;不污染 production code path
  - cargo 必經 --features spike 編譯 (production binary 不含 fixture)
  - 容差 1e-4 對齊 spec §AC-7
  - subprocess timeout 300s 防卡死
"""

from __future__ import annotations

import json
import math
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest


# 對齊 spec §AC-7 line 277 / Phase 3b PoC line 40
SPIKE_SAMPLE: list[float] = [10.0, 20.0, 30.0, 25.0, 15.0]

# Python expected (與 Phase 3b PoC 同源)
EXPECTED_MEAN: float = 20.0
EXPECTED_SAMPLE_STD: float = math.sqrt(62.5)  # ≈ 7.905694150420948

# AC-7 容差
TOLERANCE: float = 1e-4


def _locate_cargo() -> str | None:
    """多層定位 cargo binary,回傳絕對路徑;全部缺席回傳 None。

    為什麼: Mac 非互動 shell (裸跑 `python3 -m pytest`) 的 PATH 常無 cargo,
      且 homebrew rustup 改名 rustup-init→rustup 後 `~/.cargo/bin/cargo`
      symlink 鏈可能斷裂 (指向不存在的 rustup-init)。直接寫死 "cargo" 會
      FileNotFoundError 假紅。定位順序:
        1. shutil.which("cargo") — PATH 正常時的標準路徑
        2. ~/.cargo/bin/cargo — rustup 預設安裝位 (is_file() 跟隨 symlink,
           斷裂 symlink 自動跳過)
        3. `rustup which cargo` — rustup 權威解析當前 toolchain 的 cargo
        4. ~/.rustup/toolchains/*/bin/cargo — rustup 慣例 toolchain 路徑兜底
    不變量: 回傳的路徑必為真實可執行檔;None 代表工具真缺席 (skipif 唯一
      合法情境),cargo 存在時測試必須真跑。
    """
    found = shutil.which("cargo")
    if found:
        return found

    home = Path.home()
    default_cargo = home / ".cargo" / "bin" / "cargo"
    if default_cargo.is_file() and os.access(default_cargo, os.X_OK):
        return str(default_cargo)

    rustup = shutil.which("rustup")
    if rustup is None:
        default_rustup = home / ".cargo" / "bin" / "rustup"
        if default_rustup.is_file() and os.access(default_rustup, os.X_OK):
            rustup = str(default_rustup)
    if rustup is not None:
        try:
            probe = subprocess.run(
                [rustup, "which", "cargo"],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            probe = None
        if probe is not None and probe.returncode == 0:
            candidate = Path(probe.stdout.strip())
            if candidate.is_file() and os.access(candidate, os.X_OK):
                return str(candidate)

    toolchains = home / ".rustup" / "toolchains"
    if toolchains.is_dir():
        for candidate in sorted(toolchains.glob("*/bin/cargo")):
            if candidate.is_file() and os.access(candidate, os.X_OK):
                return str(candidate)

    return None


CARGO_BIN: str | None = _locate_cargo()

# skipif 只允許「cargo 工具真缺席」情境;reason 列出全部已檢查位置供排查。
pytestmark = pytest.mark.skipif(
    CARGO_BIN is None,
    reason=(
        "cargo not found: checked PATH, ~/.cargo/bin/cargo, "
        "`rustup which cargo`, and ~/.rustup/toolchains/*/bin/cargo"
    ),
)


def _srv_root() -> Path:
    """從本 test file 路徑反推 srv/ root。

    為什麼: 跨平台 / 跨 dev machine 走相對 path, 不硬編 `/Users/ncyu/...`
    或 `/home/ncyu/...` (跨平台合規 per E1 hard constraint)。
    """
    # tests/test_spike_cross_lang_rust_binding.py → parents[1] = srv/
    return Path(__file__).resolve().parents[1]


def _run_rust_fixture() -> str:
    """Subprocess 跑 cargo test, 回傳 stdout (含 RUST_FIXTURE_JSON marker)。

    為什麼 release: 對齊 Phase 3b spec literal (cargo test --release);
      production deploy 用 release build, fixture 對齊 production toolchain。
    為什麼 --features spike: helper compute_window_stats 走
      `#[cfg(any(test, feature = "spike"))]` gate, integration test 走
      `#![cfg(feature = "spike")]` gate, 不帶 flag 不編譯。
    為什麼 --nocapture: cargo test default 隱藏 println!, --nocapture 顯示
      stdout 供 parse。
    """
    srv_root = _srv_root()
    cargo_manifest = srv_root / "rust" / "openclaw_engine" / "Cargo.toml"
    assert cargo_manifest.exists(), f"Cargo.toml not found: {cargo_manifest}"
    assert CARGO_BIN is not None, "cargo missing; skipif should have skipped"

    # 為什麼補 PATH: 直呼 toolchain cargo (~/.rustup/toolchains/*/bin/cargo)
    # 時 rustc 需同目錄可尋;把 cargo 所在 bin 目錄前置到子行程 PATH,
    # 保證 rustc/rustdoc 與 cargo 同 toolchain,不影響父行程環境。
    env = dict(os.environ)
    cargo_bin_dir = str(Path(CARGO_BIN).parent)
    env["PATH"] = cargo_bin_dir + os.pathsep + env.get("PATH", "")

    cmd = [
        CARGO_BIN,
        "test",
        "--release",
        "--features",
        "spike",
        "--manifest-path",
        str(cargo_manifest),
        "--test",
        "m3_cross_lang_window_fixture",
        "test_window_stats_fixture_json",
        "--",
        "--nocapture",
    ]
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=300,  # 300s 防 cold-build 超時
        check=False,
        env=env,
    )
    assert result.returncode == 0, (
        f"cargo test failed (rc={result.returncode})\n"
        f"--- stdout ---\n{result.stdout}\n"
        f"--- stderr ---\n{result.stderr}"
    )
    return result.stdout


def _parse_rust_json(stdout: str) -> dict[str, float]:
    """從 cargo test stdout 抓 RUST_FIXTURE_JSON marker 並 parse JSON。

    為什麼 regex 而非 str.contains: cargo 輸出可能含其他 line, 需精確抓
      `RUST_FIXTURE_JSON: {...}` 該行;regex non-greedy + DOTALL 不需。
    為什麼 cast float: Rust f64 Display 對整數值省 .0 (例 `20` 而非 `20.0`),
      json.loads parse 為 int;cast float() 確保 type 一致。
    """
    match = re.search(r"RUST_FIXTURE_JSON: (\{[^}]+\})", stdout)
    assert match, (
        "RUST_FIXTURE_JSON marker not found in stdout. "
        f"Got stdout (last 500 char):\n{stdout[-500:]}"
    )
    raw = json.loads(match.group(1))
    return {"mean": float(raw["mean"]), "sigma": float(raw["sigma"])}


def test_rust_python_cross_lang_fixture_mean_1e_4() -> None:
    """AC-7 Rust mean ↔ Python expected mean 1e-4 對齊。"""
    stdout = _run_rust_fixture()
    rust_stats = _parse_rust_json(stdout)
    rust_mean = rust_stats["mean"]
    diff = abs(rust_mean - EXPECTED_MEAN)
    assert diff < TOLERANCE, (
        f"Rust mean cross-lang diff exceed 1e-4: "
        f"rust={rust_mean}, py_expected={EXPECTED_MEAN}, diff={diff}"
    )


def test_rust_python_cross_lang_fixture_sigma_1e_4() -> None:
    """AC-7 Rust sample sigma (ddof=1) ↔ Python expected sigma 1e-4 對齊。"""
    stdout = _run_rust_fixture()
    rust_stats = _parse_rust_json(stdout)
    rust_sigma = rust_stats["sigma"]
    diff = abs(rust_sigma - EXPECTED_SAMPLE_STD)
    assert diff < TOLERANCE, (
        f"Rust sigma cross-lang diff exceed 1e-4: "
        f"rust={rust_sigma}, py_expected={EXPECTED_SAMPLE_STD}, diff={diff}"
    )


def test_rust_python_cross_lang_fixture_combined() -> None:
    """AC-7 一次跑 + 同時驗 mean/sigma (省 1 次 cargo invocation)。

    為什麼 combined: 上面 2 條 test 各跑一次 cargo test 浪費編譯時間
      (release 1 次 ~5s);combined 1 次驗 2 個 metric, 純 evidence 用。
      上面 2 條保留是因 pytest 報告分項清晰。
    """
    stdout = _run_rust_fixture()
    rust_stats = _parse_rust_json(stdout)

    rust_mean = rust_stats["mean"]
    rust_sigma = rust_stats["sigma"]
    mean_diff = abs(rust_mean - EXPECTED_MEAN)
    sigma_diff = abs(rust_sigma - EXPECTED_SAMPLE_STD)

    assert mean_diff < TOLERANCE, (
        f"AC-7 mean fail: rust={rust_mean} py={EXPECTED_MEAN} diff={mean_diff}"
    )
    assert sigma_diff < TOLERANCE, (
        f"AC-7 sigma fail: rust={rust_sigma} py={EXPECTED_SAMPLE_STD} "
        f"diff={sigma_diff}"
    )


@pytest.mark.parametrize(
    "metric_key,expected",
    [
        ("mean", EXPECTED_MEAN),
        ("sigma", EXPECTED_SAMPLE_STD),
    ],
)
def test_rust_python_cross_lang_fixture_parametric(
    metric_key: str, expected: float
) -> None:
    """Parametric variant: 同 sample, 兩 metric 分項 1e-4 驗 (報告易讀)。"""
    stdout = _run_rust_fixture()
    rust_stats = _parse_rust_json(stdout)
    diff = abs(rust_stats[metric_key] - expected)
    assert diff < TOLERANCE, (
        f"{metric_key} cross-lang diff exceed 1e-4: "
        f"rust={rust_stats[metric_key]}, py_expected={expected}, diff={diff}"
    )
