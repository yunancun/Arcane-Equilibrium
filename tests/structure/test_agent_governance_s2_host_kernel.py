"""S2E.2a:S2 受信主機 runner 家族 kernel 的結構證明。

四道 §E.3「禁止 raw command 繞過 Adapter」全部在此執法,其中第四道(AST 掃描)是本波**驗收的
機器判準**:

1. 唯一 exec 點 —— kernel 之外的 runner 家族檔案不得出現 ``subprocess`` / ``os.system`` /
   ``os.popen`` / ``shell=True`` / ``eval`` / ``exec`` / ``__import__``;
2. kernel 側獨立 re-assert —— 非 allowlist argv 一律 raise 且**絕不執行**;
3. 能力分割硬檢 —— ``assert_read_only_surface`` 在呼叫任何方法之前拒絕寫能力面;
4. allowlist ≡ 原 owner 集合 —— 以「錄音式 host_probe 驅動 ``build_owner_inventory``」比對實際
   送出的 argv,證明 kernel 的表是**導出**而非手抄。

另證 target class 由主機事實導出(caller 字串永遠進不來)、``unknown`` 與 ``production`` 同等
對待、``--allow-production`` 單獨不足,以及 ``PR_SET_DUMPABLE`` 真的被執法。
"""

from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts/maintenance_scripts"
ML_ROOT = ROOT / "program_code/ml_training"
for candidate in (HELPERS, ML_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import agent_governance_alr_quiesce_inventory as qi  # noqa: E402
import agent_governance_s2_host_kernel as kernel  # noqa: E402


# ── runner 家族(§G owned paths;AST 掃描的對象) ──
KERNEL_PATH = HELPERS / "agent_governance_s2_host_kernel.py"
RUNNER_FAMILY = (
    KERNEL_PATH,
    HELPERS / "agent_governance_s2_host_observer.py",
    HELPERS / "agent_governance_s2_0_host_runner.py",
    HELPERS / "agent_governance_s2_1_host_runner.py",
    HELPERS / "agent_governance_s2_4_host_storage.py",
    HELPERS / "agent_governance_s2_4_host_recovery.py",
    HELPERS / "aiml_s2_effect_host_run.py",
)
# S2E.2b-1:``RUNNER_FAMILY`` 過去是**純手維護**的 tuple,而它同時是 AST no-raw-command 掃描的
# 唯一對象(:func:`_present_family`)⇒ 一個新 runner 檔只要忘了加進來,就完全不被掃描,任何新的
# exec 面都能全綠落地。手維護的表本身不是問題,**沒有任何東西比對它與磁碟上的事實**才是。以下
# 兩張 glob 把「長得像 S2 受信主機 runner 的檔案」由檔案系統導出,再要求它是 family 的子集。
RUNNER_FAMILY_GLOBS = ("agent_governance_s2_*host_*.py", "aiml_s2_*host_run*.py")
# glob 是形狀判準,不是語義判準:S2.4 的 row driver **protocol 葉**恰好也叫 ``…_host_identity``,
# 但它不是 runner(沒有 lane、沒有主機能力、其匯入面由 S2.4 wave 治理)。故此處允許顯式除名,
# 但除名**只**豁免 per-file import 白名單那一項:被除名的檔案仍要通過 raw-command 掃描的其餘
# 每一道,且一律不得碰 :data:`KERNEL_ONLY_IMPORTS`(見
# ``test_every_file_that_looks_like_an_s2_host_runner_is_scanned``)。於是「把新 runner 塞進除名表」
# 換不到任何 exec 能力,只換到一次必須寫明理由的顯式動作。
NON_RUNNER_HOST_LEAVES = {
    "agent_governance_s2_4_host_identity.py": (
        "S2.4 HOST_IDENTITY_INSTALL row 的 typed driver Protocol 與純導出葉;它不驅動任何 lane、"
        "不持有主機能力,匯入面屬 s2_4_install_adapter_v1 的 component_paths 治理範圍"
    ),
}
# 四個 S2 effect adapter 的 apply 進入點 + 其驅動葉:observer/kernel 的 import closure 不得含它們。
APPLIER_MODULES = frozenset({
    "agent_governance_pg_observer_bootstrap",
    "agent_governance_alr_quiesce_fence",
    "agent_governance_s2_4_apply",
    "agent_governance_s2_4_install",
    "agent_governance_s2_4_install_driver",
    "agent_governance_s2_4_prepare",
    "agent_governance_s2_4_probe",
    "agent_governance_s2_5_lifecycle",
    "agent_governance_s2_5_driver",
})

# ── ★驗收判準★ 的兩張表:正面 import 白名單 + 名稱層 denylist ──
# E2 的突變實證(M2/M2b/M2c)證明「只列黑名單模組」抓不到 ``from os import system`` /
# ``importlib.import_module("sub"+"process")`` / ``getattr(_o, "sys"+"tem")``。改成**正面白名單**:
# runner 家族只准 import 這一組宣告過的模組,任何其他 import 一律是 finding —— 於是
# ``importlib`` / ``pty`` / ``commands`` / ``ctypes``(可 `CDLL(None).system`)全都不必逐一列黑。
# ``fcntl``(``flock``)與 ``errno``(``EWOULDBLOCK``/``ELOOP``/``ENOTDIR`` 的**具名**常量;
# 硬編數值在 Linux 與 darwin 上不同)是 S2.4 POSIX file/lock driver 的最小需求;兩者都沒有
# 任何行程生成能力。
ALLOWED_STDLIB_IMPORTS = frozenset({
    "__future__", "argparse", "base64", "datetime", "errno", "fcntl", "hashlib", "json",
    "os", "pathlib", "re", "socket", "stat", "sys", "typing",
})
ALLOWED_THIRD_PARTY_IMPORTS = frozenset({"psycopg2"})
# E2 RES-5:原本是 ``GOVERNANCE_IMPORT_PREFIX = "agent_governance_"`` 的**無條件前綴放行**,而
# ``agent_governance_command_capture_v2`` 本身就是一個 ``subprocess.run`` 執行器 —— 於是「import
# 它 + ``capture_command(argv)``」這條 exec 路徑在五個檔案上全綠(E2 的 N16 探針)。前綴是名字,
# 不是能力。改成**顯式模組列**:新增任何一個都必須在這裡明說。
#
# S2E.2b-1:再從「全家族共用一個集合」改成 **per-file**。共用集合有一個結構性的副作用——S2.4 的
# 啟動補償 runner 需要 import 多個 applier 模組(``agent_governance_s2_4_install_driver`` 等),
# 而把它們塞進共用集合等於**同時**允許 observer 與 kernel import applier;
# ``test_kernel_import_closure_excludes_every_applier_module`` 只覆蓋 kernel,於是 E2 RES-5 收掉的
# 那個洞會從側門回到 observer 上。白名單是**能力**宣告,能力屬於檔案,不屬於家族。
#
# 未列名的檔案(含合成突變樣本)其治理白名單為**空集**——fail-closed:新 family 檔的第一個治理
# import 就必須在此顯式宣告。
GOVERNANCE_IMPORTS_BY_FILE: dict[str, frozenset[str]] = {
    "agent_governance_s2_host_kernel.py": frozenset({
        "agent_governance_alr_quiesce_inventory",
    }),
    "agent_governance_s2_host_observer.py": frozenset({
        "agent_governance_alr_quiesce_inventory",
        "agent_governance_s2_host_kernel",
    }),
    "agent_governance_s2_0_host_runner.py": frozenset({
        "agent_governance_pg_observer_bootstrap",
        "agent_governance_s2_effect_binding",
        "agent_governance_s2_host_kernel",
    }),
    "agent_governance_s2_1_host_runner.py": frozenset({
        "agent_governance_alr_quiesce_fence",
        "agent_governance_alr_quiesce_inventory",
        "agent_governance_s2_effect_binding",
        "agent_governance_s2_host_kernel",
    }),
    # S2.4 §5.2 的 POSIX 檔案/lock driver:只需 journal/lock 兩葉的**常量**(路徑、mode、
    # open flags),不 import 任何 applier。
    "agent_governance_s2_4_host_storage.py": frozenset({
        "agent_governance_s2_4_journal",
        "agent_governance_s2_4_lock",
    }),
    # S2.4 §5.4 的啟動逆序補償器:它是唯一需要 applier 匯入面的 family 成員(補償要重用
    # aggregate 交易葉的 rollback 契約、殘留觀測與 lock-release 折入政策,絕不另抄一份)。
    "agent_governance_s2_4_host_recovery.py": frozenset({
        "agent_governance_s2_4_component",
        "agent_governance_s2_4_host_storage",
        "agent_governance_s2_4_install_driver",
        "agent_governance_s2_4_install_evidence",
        "agent_governance_s2_4_install_plan",
        "agent_governance_s2_4_journal",
        "agent_governance_s2_4_lock",
        "agent_governance_s2_4_reconcile",
    }),
    "aiml_s2_effect_host_run.py": frozenset({
        "agent_governance_alr_quiesce_fence",
        "agent_governance_pg_observer_bootstrap",
        "agent_governance_s2_0_host_runner",
        "agent_governance_s2_1_host_runner",
        "agent_governance_s2_4_host_recovery",
        "agent_governance_s2_4_host_storage",
        "agent_governance_s2_host_kernel",
        "agent_governance_s2_host_observer",
    }),
}
# 只有 kernel 可以 import 的三個模組:``subprocess``(唯一 exec 點)、``ctypes``(prctl 執法;
# 它同時也是一條 libc ``system()`` 路徑)、以及 ``agent_governance_command_capture_v2``
# —— 後者**本身就是一個 exec 器**(``capture_command`` 內有 ``subprocess.run``),kernel 只從它
# 導出 ``SAFE_INHERITED_ENVIRONMENT`` 與 ``_redact_preview`` 兩個純值/純函式(不另造第二套規則),
# 但對其他家族成員它是一條完整的 exec 路徑,故一律禁止(E2 RES-5 的 N16 探針)。
KERNEL_ONLY_IMPORTS = frozenset({
    "subprocess", "ctypes", "agent_governance_command_capture_v2",
})

FORBIDDEN_RAW_COMMAND_NAMES = frozenset({
    "system", "popen", "startfile", "fork", "forkpty",
    "spawnl", "spawnle", "spawnlp", "spawnlpe", "spawnv", "spawnve", "spawnvp", "spawnvpe",
    "execl", "execle", "execlp", "execlpe", "execv", "execve", "execvp", "execvpe",
    "posix_spawn", "posix_spawnp",
})
FORBIDDEN_BUILTINS = frozenset({
    "eval", "exec", "compile", "__import__", "globals", "locals", "vars",
})
# 動態取名的三個 builtin:名稱參數若是**算出來的**(``"sys"+"tem"`` / f-string / call)一律 finding。
DYNAMIC_ATTRIBUTE_BUILTINS = frozenset({"getattr", "setattr", "delattr"})
# 被字串拼接混淆出來就一定是繞過意圖的識別碼。
OBFUSCATION_SENSITIVE_LITERALS = (
    FORBIDDEN_RAW_COMMAND_NAMES | FORBIDDEN_BUILTINS
    | {"subprocess", "importlib", "pty", "commands", "ctypes"}
)


def _present_family() -> list[Path]:
    return [path for path in RUNNER_FAMILY if path.is_file()]


# --------------------------------------------------------------------------- #
# (4) ★驗收判準★ — AST no-raw-command scan over the runner family
# --------------------------------------------------------------------------- #
def _fold_string(node: ast.AST) -> str | None:
    """把純字面的 ``"a" + "b"`` 折成 ``"ab"``(其他形一律回 None)。"""

    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _fold_string(node.left)
        right = _fold_string(node.right)
        if left is not None and right is not None:
            return left + right
    return None


def _raw_command_findings(path: Path, *, exec_family: bool = True) -> list[str]:
    """整個 runner 家族的 no-raw-command 掃描;kernel 之外**任何** finding 即紅。

    五道:①import **正面白名單**(``subprocess``/``ctypes`` 只准 kernel;治理模組是
    :data:`GOVERNANCE_IMPORTS_BY_FILE` 的 **per-file** 顯式列,而非 ``agent_governance_`` 前綴
    放行 —— E2 RES-5:前綴會放行 ``agent_governance_command_capture_v2``,而它自己就是一個
    ``subprocess.run`` 執行器);②``from <allowed> import <forbidden name>``(收口 E2 的 M2:
    ``from os import system as _s``);③屬性名層 denylist(不論 receiver,故 ``libc.system`` /
    ``_o.system`` 都抓得到);④``getattr``/``setattr``/``delattr`` 的名稱參數不得是**算出來的**,
    也不得是被禁名字面(收口 M2c);⑤字面字串拼接折疊(收口 ``"sub"+"process"`` 這類混淆,連帶
    讓 M2b 即使不 import ``importlib`` 也被抓)。另加 ``shell=`` 必須是常量 ``False``。

    ``exec_family=False`` 只給 :data:`NON_RUNNER_HOST_LEAVES` 用,關掉兩件**只對 exec 家族成立**
    的判準:①per-file import 白名單(那些檔案的匯入面由別的 wave 治理);②``shell=`` 必須是常量
    ``False``——它是 ``subprocess`` **呼叫形狀**的規則,而 S2.4 的 host-identity row driver 把
    POSIX 帳號的**登入 shell** 當一個同名欄位傳給 ``create_system_account``。關掉它是**可證安全**
    的:被除名的檔案一律不得 import :data:`KERNEL_ONLY_IMPORTS`(下方 ``_check_module`` 仍執法),
    也一律過不了 raw-command 名稱 denylist / builtin denylist / 動態取名 / 字面拼接四道,故它根本
    沒有任何 shell 可以到達。
    """

    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    is_kernel = path.name == KERNEL_PATH.name
    allowed_modules: frozenset[str] | None = None
    if exec_family:
        allowed_modules = (
            ALLOWED_STDLIB_IMPORTS
            | ALLOWED_THIRD_PARTY_IMPORTS
            # 未列名 = 空集(fail-closed);family 成員的每一個治理 import 都必須顯式宣告。
            | GOVERNANCE_IMPORTS_BY_FILE.get(path.name, frozenset())
        )
        if is_kernel:
            allowed_modules = allowed_modules | KERNEL_ONLY_IMPORTS
    findings: list[str] = []

    def _check_module(lineno: int, module: str, rendered: str) -> None:
        top = (module or "").split(".")[0]
        if allowed_modules is None:
            # 除名檔案:只擋 kernel 專屬的三個 exec 路徑模組,不管其餘匯入面。
            if top in KERNEL_ONLY_IMPORTS:
                findings.append(
                    f"line {lineno}: kernel-only module outside the kernel: {rendered}"
                )
            return
        if top in allowed_modules:
            return
        findings.append(f"line {lineno}: import outside the declared allowlist: {rendered}")

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                _check_module(node.lineno, alias.name, f"import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            _check_module(node.lineno, module, f"from {module} import ...")
            for alias in node.names:
                if alias.name in FORBIDDEN_RAW_COMMAND_NAMES or alias.name in FORBIDDEN_BUILTINS:
                    findings.append(
                        f"line {node.lineno}: from {module} import {alias.name}"
                    )
        elif isinstance(node, ast.Attribute):
            if node.attr in FORBIDDEN_RAW_COMMAND_NAMES:
                findings.append(f"line {node.lineno}: attribute .{node.attr}")
        elif isinstance(node, ast.Name):
            if node.id in FORBIDDEN_BUILTINS and isinstance(node.ctx, ast.Load):
                findings.append(f"line {node.lineno}: builtin {node.id}")
        elif isinstance(node, ast.BinOp):
            folded = _fold_string(node)
            if folded in OBFUSCATION_SENSITIVE_LITERALS:
                findings.append(
                    f"line {node.lineno}: obfuscated identifier literal {folded!r}"
                )
        if isinstance(node, ast.Call):
            for keyword in node.keywords:
                if exec_family and keyword.arg == "shell" and not (
                    isinstance(keyword.value, ast.Constant) and keyword.value.value is False
                ):
                    findings.append(f"line {node.lineno}: shell= is not the constant False")
            func = node.func
            called = (
                func.id if isinstance(func, ast.Name)
                else func.attr if isinstance(func, ast.Attribute) else None
            )
            if called in DYNAMIC_ATTRIBUTE_BUILTINS:
                name_arg = node.args[1] if len(node.args) >= 2 else None
                if isinstance(name_arg, ast.Constant) and isinstance(name_arg.value, str):
                    if name_arg.value in OBFUSCATION_SENSITIVE_LITERALS:
                        findings.append(
                            f"line {node.lineno}: {called}(…, {name_arg.value!r})"
                        )
                elif not isinstance(name_arg, ast.Name):
                    findings.append(
                        f"line {node.lineno}: {called}() with a computed attribute name"
                    )
    return findings


def test_no_raw_command_outside_the_kernel():
    present = _present_family()
    assert KERNEL_PATH in present
    for path in present:
        findings = _raw_command_findings(path)
        assert findings == [], f"{path.name} carries a raw-command surface: {findings}"


# --------------------------------------------------------------------------- #
# S2E.2b-1 (a) — RUNNER_FAMILY 由檔案系統**導出**比對,不是純手抄
# --------------------------------------------------------------------------- #
def _unscanned_runner_candidates(helpers_dir: Path, family_names: set[str]) -> list[str]:
    """磁碟上「長得像 S2 受信主機 runner」但不在掃描家族、也未被顯式除名的檔案。"""

    discovered = {
        path.name for glob in RUNNER_FAMILY_GLOBS for path in helpers_dir.glob(glob)
    }
    return sorted(discovered - family_names - set(NON_RUNNER_HOST_LEAVES))


def test_every_file_that_looks_like_an_s2_host_runner_is_scanned():
    # 反例式判準:family 表若漏了一個新 runner,這裡必紅(該檔在漏加之前完全不被 AST 掃描,
    # 於是任何新的 exec 面都能全綠落地 —— 那正是本測試存在的理由)。
    unscanned = _unscanned_runner_candidates(HELPERS, {path.name for path in RUNNER_FAMILY})
    assert unscanned == [], (
        f"{unscanned} match the S2 host-runner shape but are neither in RUNNER_FAMILY (so the "
        "AST no-raw-command scan never looks at them) nor declared in NON_RUNNER_HOST_LEAVES"
    )


def test_a_declared_non_runner_leaf_is_still_denied_every_exec_path():
    # 除名不是逃生門:它只豁免 per-file import 白名單與 ``shell=`` 呼叫形狀兩項,exec 能力面
    # (raw-command 名稱 / builtin / 動態取名 / 字面拼接 / kernel-only 模組)一道都不放。
    for name, reason in NON_RUNNER_HOST_LEAVES.items():
        path = HELPERS / name
        assert path.is_file(), name
        assert reason.strip(), name
        assert _raw_command_findings(path, exec_family=False) == [], name
        assert "subprocess" not in path.read_text(encoding="utf-8"), name


def test_the_exec_family_exemption_never_admits_a_kernel_only_module(tmp_path):
    for module in sorted(KERNEL_ONLY_IMPORTS):
        path = tmp_path / f"exempt_{module}.py"
        path.write_text(f"import {module}\n", encoding="utf-8")
        findings = _raw_command_findings(path, exec_family=False)
        assert any("kernel-only module outside the kernel" in item for item in findings), module


def test_the_family_derivation_is_red_when_a_new_runner_is_left_out(tmp_path):
    # 突變:一個新的 runner 檔落在 helpers 目錄卻沒進 family 表。
    (tmp_path / "agent_governance_s2_9_host_runner.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "aiml_s2_other_host_run.py").write_text("x = 1\n", encoding="utf-8")
    assert _unscanned_runner_candidates(tmp_path, set()) == [
        "agent_governance_s2_9_host_runner.py", "aiml_s2_other_host_run.py"
    ]
    # 對照:同樣兩個檔案一旦進表就不再是 finding(判準是「有沒有被掃描」,不是檔名黑名單)。
    assert _unscanned_runner_candidates(
        tmp_path,
        {"agent_governance_s2_9_host_runner.py", "aiml_s2_other_host_run.py"},
    ) == []


# --------------------------------------------------------------------------- #
# S2E.2b-1 (b) — 治理 import 白名單是 per-file 的能力宣告
# --------------------------------------------------------------------------- #
def test_the_governance_import_allowlist_is_per_file_not_family_wide(tmp_path):
    """S2.4 補償 runner 需要的 applier 匯入面,絕不因此在 observer / kernel 上也成立。"""

    applier = sorted(APPLIER_MODULES & GOVERNANCE_IMPORTS_BY_FILE[
        "agent_governance_s2_4_host_recovery.py"
    ])
    assert applier, "the S2.4 recovery runner is expected to declare applier imports"
    source = "".join(f"import {module}\n" for module in applier)
    # 同一份 source 放在補償 runner 的檔名下:合法(它宣告過這些能力)。
    admitted = tmp_path / "agent_governance_s2_4_host_recovery.py"
    admitted.write_text(source, encoding="utf-8")
    assert _raw_command_findings(admitted) == []
    # 放在任何**沒有**宣告它們的 family 成員檔名下:一律 finding。
    for name in ("agent_governance_s2_host_observer.py", "agent_governance_s2_host_kernel.py",
                 "agent_governance_s2_0_host_runner.py"):
        elsewhere = tmp_path / name
        elsewhere.write_text(source, encoding="utf-8")
        assert _raw_command_findings(elsewhere), name


def test_every_governance_allowlist_entry_belongs_to_a_family_member():
    # per-file 表不得長出「沒有對應檔案」的條目(那是一張永遠不被執行的宣告)。
    family_names = {path.name for path in RUNNER_FAMILY}
    assert set(GOVERNANCE_IMPORTS_BY_FILE) <= family_names, sorted(
        set(GOVERNANCE_IMPORTS_BY_FILE) - family_names
    )
    # 沒有任何檔案被允許 import kernel-only 的三個 exec 路徑模組。
    for name, modules in GOVERNANCE_IMPORTS_BY_FILE.items():
        assert not (modules & KERNEL_ONLY_IMPORTS), name


# E2 重做的三個突變(M2 / M2b / M2c)+ 既有四類 + 白名單外 import。全部必須被抓到。
AST_SCANNER_MUTATIONS = {
    # ── E2 的 M2:舊掃描器全綠,新掃描器必紅 ──
    "M2_from_os_import_system": (
        "from os import system as _s\n_s('id > /tmp/pwned')\n", "from os import system",
    ),
    # ── E2 的 M2b ──
    "M2b_importlib_concat": (
        "import importlib\nimportlib.import_module('sub' + 'process').run(['id'])\n",
        "import outside the declared allowlist",
    ),
    "M2b_concat_literal_alone": (
        "def f(m):\n    return m('sub' + 'process')\n", "obfuscated identifier literal",
    ),
    # ── E2 的 M2c ──
    "M2c_getattr_computed_name": (
        "import os\n_o = os\ngetattr(_o, 'sys' + 'tem')('id')\n",
        "getattr() with a computed attribute name",
    ),
    "M2c_getattr_constant_name": (
        "import os\ngetattr(os, 'system')('id')\n", "getattr(…, 'system')",
    ),
    # ── 既有四類 ──
    "raw_import_subprocess": ("import subprocess\n", "import outside the declared allowlist"),
    "os_system_attribute": ("import os\nos.system('x')\n", "attribute .system"),
    "shell_true": (
        "import subprocess\nsubprocess.run(['x'], shell=True)\n", "shell= is not the constant False",
    ),
    "builtin_eval": ("eval('1')\n", "builtin eval"),
    # ── 新增的縱深:ctypes 是 libc.system 的路,pty/commands 亦然 ──
    "ctypes_libc_system": (
        "import ctypes\nctypes.CDLL(None).system(b'id')\n",
        "import outside the declared allowlist",
    ),
    "ctypes_attribute_even_if_imported_elsewhere": (
        "def f(libc):\n    libc.system(b'id')\n", "attribute .system",
    ),
    "pty_spawn": ("import pty\npty.spawn('/bin/sh')\n", "import outside the declared allowlist"),
    "dunder_import": ("__import__('subprocess')\n", "builtin __import__"),
    # ── E2 的 N16(RES-5):前綴放行下這條 exec 路徑在五個檔案上全綠 ──
    "N16_governance_prefix_exec_module": (
        "import agent_governance_command_capture_v2 as cap\n"
        "cap.capture_command(['/bin/sh', '-c', 'id'])\n",
        "import outside the declared allowlist",
    ),
    "N16_governance_prefix_from_import": (
        "from agent_governance_command_capture_v2 import capture_command\n",
        "import outside the declared allowlist",
    ),
}


@pytest.mark.parametrize("mutation", sorted(AST_SCANNER_MUTATIONS))
def test_the_ast_scanner_actually_catches_a_violation(tmp_path, mutation):
    # 反例:掃描器若抓不到違規就是空轉。E2 突變實證的三支(M2/M2b/M2c)在此逐一釘死。
    source, expected = AST_SCANNER_MUTATIONS[mutation]
    path = tmp_path / f"{mutation}.py"
    path.write_text(source, encoding="utf-8")
    findings = _raw_command_findings(path)
    assert any(expected in item for item in findings), (source, findings)


@pytest.mark.parametrize("mutation", sorted(AST_SCANNER_MUTATIONS))
def test_a_declared_non_runner_leaf_is_scanned_by_the_same_exec_rules(tmp_path, mutation):
    # 反例:除名檔案若被塞進任何一條 exec 路徑,``exec_family=False`` 這條路徑也必須抓到它。
    # (唯二被關掉的判準是 import 白名單與 ``shell=`` 呼叫形狀,故該兩類突變在此跳過。)
    source, expected = AST_SCANNER_MUTATIONS[mutation]
    if expected in {"import outside the declared allowlist", "shell= is not the constant False"}:
        pytest.skip("this rule is deliberately exec-family-only; see _raw_command_findings")
    path = tmp_path / f"{mutation}.py"
    path.write_text(source, encoding="utf-8")
    assert any(expected in item for item in _raw_command_findings(path, exec_family=False))


def test_a_mutation_injected_into_a_real_family_file_is_caught(tmp_path):
    """把 M2 的突變真的注進一個**家族成員的副本**,證明掃描器對真檔也紅(不只對合成樣本)。"""

    for original in _present_family():
        mutated = tmp_path / original.name
        mutated.write_text(
            original.read_text(encoding="utf-8")
            + "\n\nfrom os import system as _s\n\n\ndef _pwn():\n    return _s('id')\n",
            encoding="utf-8",
        )
        findings = _raw_command_findings(mutated)
        assert any("from os import system" in item for item in findings), original.name


def test_the_import_allowlist_is_positive_and_kernel_only_imports_are_kernel_only(tmp_path):
    # 白名單是**正面**的:一個從未宣告過的模組(即使人畜無害)也必須被抓到 —— 這正是它比黑名單
    # 難繞的原因。
    sample = tmp_path / "unknown_module.py"
    sample.write_text("import socketserver\n", encoding="utf-8")
    assert _raw_command_findings(sample)
    # subprocess / ctypes 只准 kernel:同一份 source 放在非 kernel 檔名下必紅。
    for module in sorted(KERNEL_ONLY_IMPORTS):
        elsewhere = tmp_path / f"not_the_kernel_{module}.py"
        elsewhere.write_text(f"import {module}\n", encoding="utf-8")
        assert _raw_command_findings(elsewhere), module


def test_kernel_is_the_only_family_member_importing_subprocess():
    for path in _present_family():
        source = path.read_text(encoding="utf-8")
        if path == KERNEL_PATH:
            assert "import subprocess" in source
        else:
            assert "subprocess" not in source, path.name


# --------------------------------------------------------------------------- #
# (1)+(4) allowlist ≡ owner — derived, not hand-copied
# --------------------------------------------------------------------------- #
_FRAG = "/etc/systemd/system/arcane-equilibrium-aiml-engine-scanner.service"
_FLOCK = "/run/arcane-equilibrium/aiml-engine-scanner/consumer.lock"
_DSN = "/run/credentials/arcane-equilibrium-aiml-engine-scanner.service/pg-dsn"


class _RecordingProbe:
    """錄音式 host_probe:記下 owner 模組**實際**送出的每一條 argv。"""

    def __init__(self, proc_root: Path) -> None:
        self.proc_root = proc_root
        self.argv: list[tuple[str, ...]] = []

    def run(self, argv):
        self.argv.append(tuple(argv))
        if list(argv[:3]) == [qi.SYSTEMD, "show", qi.UNIT_NAME]:
            props = {
                "LoadState": "loaded", "ActiveState": "active", "SubState": "running",
                "MainPID": "0", "InvocationID": "inv", "NRestarts": "0", "ControlGroup": "",
                "FragmentPath": _FRAG, "DropInPaths": "", "NeedDaemonReload": "no",
                "Environment": "", "Restart": "on-failure", "RestartUSec": "5s",
                "TimeoutStopUSec": "30s", "WatchdogUSec": "0", "NoNewPrivileges": "yes",
                "ProtectSystem": "full", "PrivateTmp": "yes",
                "RestrictAddressFamilies": "AF_UNIX",
            }
            return "\n".join(f"{key}={props[key]}" for key in qi.QUIESCE_SHOW_PROPERTIES)
        if list(argv[:2]) == [qi.SYSTEMD, "list-units"]:
            return ""
        raise AssertionError(f"unexpected argv: {argv}")

    def dsn_stat(self):
        return {"dsn_file_path": _DSN, "dsn_mode": "0600", "dsn_owner_uid": 4001,
                "world_readable": False}

    def flock_held(self):
        return True


class _ScriptedCursor:
    """read_db_quiesce 的最小回應腳本(hashtext → holders → session*3 → queue usage)。"""

    def __init__(self) -> None:
        self._rows: list = []

    def execute(self, statement, parameters=None):
        text = " ".join(str(statement).split())
        if text.startswith("SELECT hashtext"):
            self._rows = [(1234,)]
        elif "pg_locks" in text:
            self._rows = []
        elif "pg_notification_queue_usage" in text:
            self._rows = [(0.0,)]
        else:
            self._rows = [(0,)]

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)


def test_kernel_read_allowlist_equals_the_argv_the_owner_actually_issues(tmp_path):
    proc_root = tmp_path / "proc"
    (proc_root / "sys" / "kernel" / "random").mkdir(parents=True)
    (proc_root / "sys" / "kernel" / "random" / "boot_id").write_text("b\n", encoding="utf-8")
    probe = _RecordingProbe(proc_root)
    intent = {
        "flock_path": _FLOCK,
        "unit_fragment_path": _FRAG,
        "advisory_lock_name": qi.ADVISORY_LOCK_NAME,
        "consumer_session_relation": qi.DEFAULT_CONSUMER_SESSION_RELATION,
    }
    qi.build_owner_inventory(probe, _ScriptedCursor(), intent=intent)
    issued = set(probe.argv)
    assert issued, "the owner module issued no host command"
    # 導出比對(非手抄):owner 實際送出的每一條 argv 都在 kernel 的唯讀 allowlist 內,且兩者相等。
    assert issued == set(kernel.SESSION_ARGV_ALLOWLISTS[kernel.SESSION_S2_1_QUIESCE_READ])


def test_kernel_read_allowlist_is_accepted_by_the_owner_assert():
    for argv in kernel.SESSION_ARGV_ALLOWLISTS[kernel.SESSION_S2_1_QUIESCE_READ]:
        qi._assert_allowlisted_systemctl(list(argv))


def test_fence_allowlist_is_exactly_the_units_own_stop_start():
    fence = kernel.SESSION_ARGV_ALLOWLISTS[kernel.SESSION_S2_1_QUIESCE_FENCE]
    assert fence == frozenset({
        (qi.SYSTEMD, "stop", qi.UNIT_NAME),
        (qi.SYSTEMD, "start", qi.UNIT_NAME),
    })
    # fence argv 絕不是 pkill / kill-by-name / kill-by-pattern / kill-by-pid,也永遠不是 --user。
    for argv in fence:
        assert argv[0] == qi.SYSTEMD
        assert argv[2] == qi.UNIT_NAME
        assert "--user" not in argv


def test_s2_0_session_has_no_argv_surface_at_all():
    assert kernel.SESSION_ARGV_ALLOWLISTS[kernel.SESSION_S2_0_OBSERVER_BOOTSTRAP] == frozenset()
    with pytest.raises(kernel.S2HostArgvNotAllowlisted):
        kernel.assert_session_argv(kernel.SESSION_S2_0_OBSERVER_BOOTSTRAP, ["/usr/bin/psql", "-c", "select 1"])


# --------------------------------------------------------------------------- #
# (2) kernel-side independent re-assert — a non-allowlisted argv NEVER executes
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("argv", [
    [qi.SYSTEMD, "stop", qi.UNIT_NAME],                                   # 唯讀 session 不得 stop
    [qi.SYSTEMD, "show", qi.UNIT_NAME],                                   # 屬性集不完整
    [qi.SYSTEMD, "--user", "show", qi.UNIT_NAME],                         # --user 形
    ["systemctl", "list-units", "--type=scope", "--state=active",
     "--no-legend", "--no-pager"],                                        # 非絕對路徑
    [qi.SYSTEMD, "list-units", "--type=scope", "--state=active", "--no-legend"],
])
def test_non_allowlisted_argv_raises_and_never_executes(argv, monkeypatch):
    def _boom(*args, **kwargs):  # pragma: no cover - 必須永不被呼叫
        raise AssertionError("subprocess.run must never be reached for a non-allowlisted argv")

    monkeypatch.setattr(subprocess, "run", _boom)
    host = kernel.HostExecutionKernel(session=kernel.SESSION_S2_1_QUIESCE_READ)
    with pytest.raises(kernel.S2HostArgvNotAllowlisted):
        host.run(argv)
    assert host.calls == []


def test_shell_string_argv_is_refused(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: pytest.fail("must not execute"))
    host = kernel.HostExecutionKernel(session=kernel.SESSION_S2_1_QUIESCE_READ)
    with pytest.raises(kernel.S2HostArgvNotAllowlisted):
        host.run(f"{qi.SYSTEMD} show {qi.UNIT_NAME}")


def test_there_is_no_generic_session():
    with pytest.raises(kernel.S2HostSessionError):
        kernel.HostExecutionKernel(session="generic")
    with pytest.raises(kernel.S2HostSessionError):
        kernel.session_argv_allowlist("anything_else")


def test_mutating_session_requires_explicit_acknowledgement():
    with pytest.raises(kernel.S2HostSessionError):
        kernel.HostExecutionKernel(session=kernel.SESSION_S2_1_QUIESCE_FENCE)
    with pytest.raises(kernel.S2HostSessionError):
        kernel.HostExecutionKernel(
            session=kernel.SESSION_S2_1_QUIESCE_READ, allow_mutation=True
        )
    fence = kernel.HostExecutionKernel(
        session=kernel.SESSION_S2_1_QUIESCE_FENCE, allow_mutation=True
    )
    assert fence.allow_mutation is True


def test_kernel_execution_is_shell_false_absolute_and_sanitized(monkeypatch):
    captured: dict = {}

    class _Completed:
        returncode = 0
        stdout = b"LoadState=loaded\n"
        stderr = b""

    def _fake_run(argv, **kwargs):
        captured["argv"] = argv
        captured["kwargs"] = kwargs
        return _Completed()

    monkeypatch.setattr(subprocess, "run", _fake_run)
    host = kernel.HostExecutionKernel(session=kernel.SESSION_S2_1_QUIESCE_READ)
    allowed = sorted(kernel.SESSION_ARGV_ALLOWLISTS[kernel.SESSION_S2_1_QUIESCE_READ])[0]
    output = host.run(list(allowed))
    assert output == "LoadState=loaded\n"
    assert captured["argv"] == list(allowed)
    assert captured["argv"][0].startswith("/")
    assert captured["kwargs"]["shell"] is False
    assert captured["kwargs"]["timeout"] == kernel.SESSION_TIMEOUT_SECONDS[
        kernel.SESSION_S2_1_QUIESCE_READ
    ]
    environment = captured["kwargs"]["env"]
    assert environment["LC_ALL"] == "C"
    assert not {"HOME", "PGPASSWORD", "PYTHONPATH"} & set(environment)


def test_nonzero_exit_and_timeout_fail_closed(monkeypatch):
    class _Failed:
        returncode = 3
        stdout = b""
        stderr = b"boom"

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _Failed())
    host = kernel.HostExecutionKernel(session=kernel.SESSION_S2_1_QUIESCE_READ)
    allowed = sorted(kernel.SESSION_ARGV_ALLOWLISTS[kernel.SESSION_S2_1_QUIESCE_READ])[0]
    with pytest.raises(kernel.S2HostCommandFailed):
        host.run(list(allowed))

    def _timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="x", timeout=1)

    monkeypatch.setattr(subprocess, "run", _timeout)
    with pytest.raises(kernel.S2HostCommandFailed):
        host.run(list(allowed))


def test_stdout_is_redacted_with_the_existing_capture_v2_patterns(monkeypatch):
    class _Completed:
        returncode = 0
        stdout = b"Environment=PGPASSWORD=hunter2\n"
        stderr = b""

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _Completed())
    host = kernel.HostExecutionKernel(session=kernel.SESSION_S2_1_QUIESCE_READ)
    allowed = sorted(kernel.SESSION_ARGV_ALLOWLISTS[kernel.SESSION_S2_1_QUIESCE_READ])[0]
    output = host.run(list(allowed))
    assert "hunter2" not in output
    assert "<redacted>" in output


# --------------------------------------------------------------------------- #
# (3) capability partition
# --------------------------------------------------------------------------- #
class _WriterSurface:
    def stop(self):  # pragma: no cover - 必須永不被呼叫
        raise AssertionError("assert_read_only_surface must refuse BEFORE calling anything")

    def read(self):
        return "ok"


class _ReaderSurface:
    def read(self):
        return "ok"


def test_assert_read_only_surface_refuses_before_calling_anything():
    errors = kernel.assert_read_only_surface(_WriterSurface())
    assert errors and "stop" in errors[0]
    assert kernel.assert_read_only_surface(_ReaderSurface()) == []


def test_forbidden_read_only_surface_covers_the_four_adapter_mutators():
    for name in ("stop", "start", "create_read_only_observer", "compensate",
                 "signed_apply_attestation", "enable_now"):
        assert name in kernel.FORBIDDEN_READ_ONLY_SURFACE


# --------------------------------------------------------------------------- #
# target class is derived from HOST FACTS (a caller string can never reach it)
# --------------------------------------------------------------------------- #
def _force_host(monkeypatch, *, platform, hostname, writable, roots):
    monkeypatch.setattr(kernel.sys, "platform", platform)
    monkeypatch.setattr(kernel, "_observed_nodename", lambda: hostname)
    monkeypatch.setattr(kernel.socket, "gethostname", lambda: hostname)
    monkeypatch.setattr(kernel, "_writable", lambda path: writable)
    monkeypatch.setattr(kernel, "_present", lambda path: roots)


@pytest.mark.parametrize("platform,hostname,writable,roots,expected", [
    ("darwin", "trade-core", True, True, kernel.TARGET_CLASS_NON_TARGET),
    ("linux", "some-laptop", True, True, kernel.TARGET_CLASS_NON_TARGET),
    # P1-A:未供裝 + 非 root(unit dir 不可寫、canonical roots 全缺)**曾經**落
    # ``disposable_candidate``(= 無條件放行)。那是初始供裝 / 恢復期的真 trade-core 常態視圖,
    # 故 hostname 支配供裝訊號,結果必須是 ``unknown``(與 production 同等對待)。
    ("linux", "trade-core", False, False, kernel.TARGET_CLASS_UNKNOWN),
    ("linux", "trade-core", True, True, kernel.TARGET_CLASS_PRODUCTION),
    ("linux", "trade-core", None, True, kernel.TARGET_CLASS_UNKNOWN),
    ("linux", "trade-core", True, None, kernel.TARGET_CLASS_UNKNOWN),
    ("linux", "trade-core", True, False, kernel.TARGET_CLASS_UNKNOWN),
    ("linux", "trade-core", False, True, kernel.TARGET_CLASS_UNKNOWN),
])
def test_derive_host_target_class_matrix(monkeypatch, platform, hostname, writable, roots, expected):
    _force_host(monkeypatch, platform=platform, hostname=hostname, writable=writable, roots=roots)
    view = kernel.derive_host_target_class()
    assert view["target_class"] == expected
    assert view["facts"]["hostname"] == hostname


def test_derive_host_target_class_takes_no_caller_argument():
    import inspect

    assert list(inspect.signature(kernel.derive_host_target_class).parameters) == []


def test_this_development_machine_is_never_a_production_target():
    # Mac 開發機:不論本地檔案系統長什麼樣,必為 non_target(絕不可能誤判成 production)。
    view = kernel.derive_host_target_class()
    if sys.platform != "linux":
        assert view["target_class"] == kernel.TARGET_CLASS_NON_TARGET


# --------------------------------------------------------------------------- #
# production / unknown admission matrix — --allow-production alone is NOT enough
# --------------------------------------------------------------------------- #
DIGEST = "sha256:" + "a" * 64


ADMITTED = {
    "allow_production": True, "production_confirm": DIGEST, "intent_digest": DIGEST,
    "operator_authorization_verified": True,
    "intent_target_class": kernel.INTENT_TARGET_CLASS_PRODUCTION,
}


@pytest.mark.parametrize("target_class", sorted(kernel.PRODUCTION_GRADE_TARGET_CLASSES))
def test_allow_production_alone_is_insufficient(target_class):
    view = {"target_class": target_class, "reason": "x", "facts": {}}
    errors = kernel.host_target_admission_errors(
        view, allow_production=True, production_confirm=None,
        intent_digest=DIGEST, operator_authorization_verified=False,
        intent_target_class=kernel.INTENT_TARGET_CLASS_PRODUCTION,
    )
    assert errors
    assert any("operator SSHSIG" in error for error in errors)
    assert any("--production-confirm" in error for error in errors)


@pytest.mark.parametrize("target_class", sorted(kernel.PRODUCTION_GRADE_TARGET_CLASSES))
def test_all_four_conditions_admit_and_any_missing_one_refuses(target_class):
    view = {"target_class": target_class, "reason": "x", "facts": {}}
    assert kernel.host_target_admission_errors(view, **ADMITTED) == []
    for override in (
        {"allow_production": False},
        {"operator_authorization_verified": False},
        {"production_confirm": "sha256:" + "b" * 64},
        {"production_confirm": None},
        # P1-B:第四條件 —— intent 自宣告的 class 必須與導出的主機 class 同一級。
        {"intent_target_class": kernel.INTENT_TARGET_CLASS_DISPOSABLE_LOCAL},
        {"intent_target_class": None},
    ):
        assert kernel.host_target_admission_errors(view, **{**ADMITTED, **override})


def test_the_admission_predicate_cannot_silently_skip_the_intent_binding():
    """P1-B:``intent_target_class`` 是**必填** kwarg —— 忘了遞是 TypeError,不是靜默放行。"""

    import inspect

    parameter = inspect.signature(kernel.host_target_admission_errors).parameters[
        "intent_target_class"
    ]
    assert parameter.kind is inspect.Parameter.KEYWORD_ONLY
    assert parameter.default is inspect.Parameter.empty


@pytest.mark.parametrize("target_class", sorted(kernel.PRODUCTION_GRADE_TARGET_CLASSES))
def test_a_disposable_local_intent_is_refused_on_a_production_grade_host(target_class):
    """P1-B:一份合法簽章的 ``disposable_local`` intent 絕不可在生產級主機上被承認。

    它若被承認,``apply_quiesce_fence`` 會走 disposable 分支,用**真的** kernel capability 發
    system-level ``stop``/``start``,再把那次真實 effect 標成 rehearsal 級的 local 證據。
    """

    view = {"target_class": target_class, "reason": "x", "facts": {}}
    errors = kernel.host_target_admission_errors(
        view, **{**ADMITTED, "intent_target_class": kernel.INTENT_TARGET_CLASS_DISPOSABLE_LOCAL}
    )
    # 其餘三條件全部滿足 ⇒ 唯一的拒絕理由就是這道綁定(不是碰巧被別的條件擋下)。
    assert len(errors) == 1
    assert kernel.INTENT_TARGET_CLASS_DISPOSABLE_LOCAL in errors[0]


def test_the_intent_binding_reason_never_echoes_the_caller_string():
    """理由字串會落進 artifact 與 stdout summary ⇒ 只准複述封閉枚舉,絕不回寫呼叫端遞來的位元組。"""

    view = {"target_class": kernel.TARGET_CLASS_PRODUCTION, "reason": "x", "facts": {}}
    hostile = "PG" + "PASSWORD" + "=" + "s3cr3t-not-real"
    errors = kernel.host_target_admission_errors(
        view, **{**ADMITTED, "intent_target_class": hostile}
    )
    assert errors
    joined = " ".join(errors)
    assert hostile not in joined
    assert "unrecognized" in joined
    # 壞 intent 可能遞來不可雜湊值:謂詞必須照樣回一份 typed 拒絕,而不是自己炸成 TypeError。
    for unhashable in ([], {}, {"target_class": "production"}):
        assert kernel.host_target_admission_errors(
            view, **{**ADMITTED, "intent_target_class": unhashable}
        )


def test_non_target_and_the_rehearsal_only_class_are_both_refused():
    """P1-A:``disposable_candidate`` 是 rehearsal-only class ⇒ 生產進入點一律拒(曾經是放行)。"""

    assert kernel.host_target_admission_errors(
        {"target_class": kernel.TARGET_CLASS_NON_TARGET, "reason": "mac"}, **ADMITTED
    )
    errors = kernel.host_target_admission_errors(
        {"target_class": kernel.TARGET_CLASS_DISPOSABLE_CANDIDATE, "reason": "throwaway"},
        **ADMITTED,
    )
    assert any("rehearsal-only" in error for error in errors)
    # 連「四條件全滿足」都救不回來:它根本不是一個可導出的主機事實。
    assert kernel.host_target_admission_errors(
        {"target_class": kernel.TARGET_CLASS_DISPOSABLE_CANDIDATE, "reason": "throwaway"},
        allow_production=False, production_confirm=None, intent_digest=None,
        operator_authorization_verified=False, intent_target_class=None,
    )


def test_the_rehearsal_only_class_is_never_derivable_from_host_facts(monkeypatch):
    """P1-A 的核心:任何主機事實組合都導不出 ``disposable_candidate``。"""

    assert kernel.REHEARSAL_ONLY_TARGET_CLASSES == frozenset(
        {kernel.TARGET_CLASS_DISPOSABLE_CANDIDATE}
    )
    assert not (kernel.DERIVABLE_TARGET_CLASSES & kernel.REHEARSAL_ONLY_TARGET_CLASSES)
    for platform in ("linux", "darwin"):
        for hostname in ("trade-core", "trade-core.internal", "some-laptop"):
            for writable in (True, False, None):
                for roots in (True, False, None):
                    _force_host(
                        monkeypatch, platform=platform, hostname=hostname,
                        writable=writable, roots=roots,
                    )
                    derived = kernel.derive_host_target_class()["target_class"]
                    assert derived in kernel.DERIVABLE_TARGET_CLASSES
                    assert derived not in kernel.REHEARSAL_ONLY_TARGET_CLASSES


@pytest.mark.parametrize("writable,roots", [(False, False), (False, True), (True, False)])
def test_an_unprovisioned_target_host_stays_inside_the_production_gate(monkeypatch, writable, roots):
    """P1-A 的實景:初始供裝 / 恢復期的真 trade-core(非 root、roots 未建)必須落 production 閘。"""

    _force_host(
        monkeypatch, platform="linux", hostname="trade-core", writable=writable, roots=roots
    )
    view = kernel.derive_host_target_class()
    assert view["target_class"] == kernel.TARGET_CLASS_UNKNOWN
    assert kernel.host_target_admission_errors(
        view, allow_production=False, production_confirm=None, intent_digest=None,
        operator_authorization_verified=False,
        intent_target_class=kernel.INTENT_TARGET_CLASS_PRODUCTION,
    )


def test_the_intent_target_classes_are_pinned_to_both_adapters():
    """kernel 不匯入 applier 模組,故 intent 側的字面量必須在測試裡對兩個 adapter 常量釘死。"""

    import agent_governance_alr_quiesce_fence as fence
    import agent_governance_pg_observer_bootstrap as bootstrap

    for adapter in (fence, bootstrap):
        assert kernel.INTENT_TARGET_CLASS_PRODUCTION == adapter.PRODUCTION_TARGET_CLASS
        assert kernel.INTENT_TARGET_CLASS_DISPOSABLE_LOCAL == adapter.DISPOSABLE_TARGET_CLASS
        assert kernel.INTENT_TARGET_CLASSES == adapter.TARGET_CLASSES


def test_unknown_is_treated_exactly_like_production():
    unknown = {"target_class": kernel.TARGET_CLASS_UNKNOWN, "reason": "x"}
    production = {"target_class": kernel.TARGET_CLASS_PRODUCTION, "reason": "x"}
    for override in (
        {"allow_production": False},
        {"production_confirm": None},
        {"intent_target_class": kernel.INTENT_TARGET_CLASS_DISPOSABLE_LOCAL},
    ):
        kwargs = {**ADMITTED, **override}
        assert bool(kernel.host_target_admission_errors(unknown, **kwargs)) == bool(
            kernel.host_target_admission_errors(production, **kwargs)
        )


# --------------------------------------------------------------------------- #
# rehearsal lane — an injected view may only TIGHTEN, never loosen (RUN-1)
# --------------------------------------------------------------------------- #
DISPOSABLE = {"target_class": kernel.TARGET_CLASS_DISPOSABLE_CANDIDATE, "reason": "throwaway"}
NON_TARGET = {"target_class": kernel.TARGET_CLASS_NON_TARGET, "reason": "mac"}


@pytest.mark.parametrize("derived,injected,refused", [
    (DISPOSABLE, None, False),
    (NON_TARGET, None, False),
    # derived 落在 production-grade ⇒ 拒,任何注入都救不回來(注入不能放寬)。
    ({"target_class": kernel.TARGET_CLASS_PRODUCTION}, None, True),
    ({"target_class": kernel.TARGET_CLASS_UNKNOWN}, None, True),
    ({"target_class": kernel.TARGET_CLASS_PRODUCTION}, DISPOSABLE, True),
    ({"target_class": kernel.TARGET_CLASS_UNKNOWN}, DISPOSABLE, True),
    # injected 落在 production-grade ⇒ 也拒(注入只能加嚴)。
    (NON_TARGET, {"target_class": kernel.TARGET_CLASS_PRODUCTION}, True),
    (NON_TARGET, {"target_class": kernel.TARGET_CLASS_UNKNOWN}, True),
    (DISPOSABLE, {"target_class": kernel.TARGET_CLASS_PRODUCTION}, True),
])
def test_rehearsal_refusal_is_the_stricter_of_derived_and_injected(derived, injected, refused):
    assert bool(kernel.rehearsal_target_refusals(derived, injected)) is refused


def test_rehearsal_unknown_is_treated_exactly_like_production():
    assert kernel.REHEARSAL_REFUSED_TARGET_CLASSES == frozenset(
        {kernel.TARGET_CLASS_PRODUCTION, kernel.TARGET_CLASS_UNKNOWN}
    )


def test_the_recorded_target_class_is_always_the_derived_one():
    record = kernel.rehearsal_target_view_record(
        DISPOSABLE, {"target_class": kernel.TARGET_CLASS_NON_TARGET}
    )
    assert record["target_class"] == kernel.TARGET_CLASS_DISPOSABLE_CANDIDATE
    assert record["derived"] is DISPOSABLE
    assert record["injected"] == {"target_class": kernel.TARGET_CLASS_NON_TARGET}
    assert record["injected_is_authoritative"] is False


# --------------------------------------------------------------------------- #
# W5 #21 — PR_SET_DUMPABLE is actually enforced (not a declared constant)
# --------------------------------------------------------------------------- #
def test_process_hardening_is_observed_and_load_bearing():
    observation = kernel.enforce_process_hardening(force=True)
    if sys.platform == "linux":
        assert observation == {"enforced": True, "observed_dumpable": 0, "reason": None}
    else:
        assert observation["enforced"] is False
        assert observation["observed_dumpable"] is None
        # P2 #7:舊理由字串宣稱「the kernel executes no host command here」是**假的**
        # ——這條路徑確實會 exec(observer child)。新字串必須誠實。
        assert "executes no host command" not in observation["reason"]
        assert "cannot be observed on this platform" in observation["reason"]
        assert "may still execute here" in observation["reason"]


def test_process_hardening_is_re_observed_on_every_execution(monkeypatch):
    """P2 #10:快取會讓「執法」只發生一次;每次 exec 前都必須真的重新觀測。"""

    observations = {"count": 0}

    def _count(*, force: bool = False):
        observations["count"] += 1
        assert force is True, "run() must force a fresh observation, never reuse the cache"
        return {"enforced": True, "observed_dumpable": 0, "reason": None}

    class _Completed:
        returncode = 0
        stdout = b""
        stderr = b""

    monkeypatch.setattr(kernel, "enforce_process_hardening", _count)
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _Completed())
    host = kernel.HostExecutionKernel(session=kernel.SESSION_S2_1_QUIESCE_READ)
    allowed = sorted(kernel.SESSION_ARGV_ALLOWLISTS[kernel.SESSION_S2_1_QUIESCE_READ])[0]
    host.run(list(allowed))
    host.run(list(allowed))
    assert observations["count"] == 2


# --------------------------------------------------------------------------- #
# P2 #7 — the read-only observation face also passes an L1 gate (a weaker one)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("target_class,allow,refused", [
    (kernel.TARGET_CLASS_NON_TARGET, False, False),
    # P1-A:rehearsal-only class 導不出來 ⇒ 觀測面見到它也只能是偽造視圖,一律拒。
    (kernel.TARGET_CLASS_DISPOSABLE_CANDIDATE, False, True),
    (kernel.TARGET_CLASS_DISPOSABLE_CANDIDATE, True, True),
    (kernel.TARGET_CLASS_PRODUCTION, False, True),
    (kernel.TARGET_CLASS_UNKNOWN, False, True),      # unknown 同等對待
    (kernel.TARGET_CLASS_PRODUCTION, True, False),
    (kernel.TARGET_CLASS_UNKNOWN, True, False),
])
def test_read_only_observation_admission(target_class, allow, refused):
    errors = kernel.host_observation_admission_errors(
        {"target_class": target_class, "reason": "x"}, allow_production=allow
    )
    assert bool(errors) is refused


def test_the_observation_gate_is_deliberately_weaker_than_the_apply_gate():
    # 觀測面不需要 SSHSIG / --production-confirm(觀測正是拿到 permit 之前要做的事),但 apply 面
    # 在同一份 view 上仍然需要四條件 —— 兩者絕不可被混為一談。
    view = {"target_class": kernel.TARGET_CLASS_PRODUCTION, "reason": "x"}
    assert kernel.host_observation_admission_errors(view, allow_production=True) == []
    assert kernel.host_target_admission_errors(
        view, allow_production=True, production_confirm=None, intent_digest=DIGEST,
        operator_authorization_verified=False,
        intent_target_class=kernel.INTENT_TARGET_CLASS_PRODUCTION,
    )


# --------------------------------------------------------------------------- #
# P2 #12 — hostname is derived from the same source as S1.6B
# --------------------------------------------------------------------------- #
def test_hostname_comes_from_the_same_source_as_the_s1_6b_preflight():
    import agent_governance_target_host_probe as th
    import inspect

    # S1.6B 用 os.uname().nodename;kernel 必須同源(否則同一台主機會有兩個身分)。
    assert "os.uname().nodename" in inspect.getsource(th.preflight_target_host)
    assert kernel._observed_nodename() == os.uname().nodename


@pytest.mark.parametrize("hostname,expected", [
    ("trade-core", kernel.TARGET_CLASS_PRODUCTION),
    ("trade-core.internal", kernel.TARGET_CLASS_PRODUCTION),   # FQDN nodename 仍是同一台
    ("trade-core-staging", kernel.TARGET_CLASS_NON_TARGET),    # 前綴相同但不是同一個 label
    ("some-laptop.trade-core", kernel.TARGET_CLASS_NON_TARGET),
])
def test_fqdn_nodename_still_resolves_to_the_pinned_target(monkeypatch, hostname, expected):
    monkeypatch.setattr(kernel.sys, "platform", "linux")
    monkeypatch.setattr(kernel, "_observed_nodename", lambda: hostname)
    monkeypatch.setattr(kernel, "_writable", lambda path: True)
    monkeypatch.setattr(kernel, "_present", lambda path: True)
    assert kernel.derive_host_target_class()["target_class"] == expected


def test_process_hardening_refusal_blocks_execution(monkeypatch):
    def _refuse(*args, **kwargs):
        raise kernel.S2HostKernelError("PR_GET_DUMPABLE observed 1")

    monkeypatch.setattr(kernel, "enforce_process_hardening", _refuse)
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: pytest.fail("must not execute"))
    host = kernel.HostExecutionKernel(session=kernel.SESSION_S2_1_QUIESCE_READ)
    allowed = sorted(kernel.SESSION_ARGV_ALLOWLISTS[kernel.SESSION_S2_1_QUIESCE_READ])[0]
    with pytest.raises(kernel.S2HostKernelError):
        host.run(list(allowed))


# --------------------------------------------------------------------------- #
# derived constants are pinned against their owners (no re-invented host facts)
# --------------------------------------------------------------------------- #
def test_target_hostnames_are_pinned_to_the_s1_target_host():
    import agent_governance_target_host_probe as th

    assert kernel.TARGET_HOSTNAMES == frozenset({th.EXPECTED_TARGET_HOST_DEFAULT})


def test_canonical_roots_and_unit_dir_match_the_s2_4_constants():
    import agent_governance_s2_4_apply as s2_4_apply

    assert set(kernel.CANONICAL_INSTALL_ROOTS) == set(s2_4_apply.INSTALL_ROOTS.values())
    assert kernel.SYSTEMD_SYSTEM_UNIT_DIR == str(
        Path(s2_4_apply.UNIT_FRAGMENT_PATH).parent
    )


def test_kernel_import_closure_excludes_every_applier_module():
    argv = [
        sys.executable, "-c",
        "import sys; sys.path.insert(0, %r); sys.path.insert(0, %r); "
        "import agent_governance_s2_host_kernel; "
        "print('\\n'.join(sorted(sys.modules)))" % (str(ML_ROOT), str(HELPERS)),
    ]
    loaded = set(
        subprocess.run(argv, capture_output=True, text=True, check=True).stdout.split()
    )
    assert not (loaded & APPLIER_MODULES), sorted(loaded & APPLIER_MODULES)


def test_kernel_abi_projection_is_code_owned():
    projection = kernel.kernel_abi_projection()
    assert projection["sessions"] == sorted(kernel.SESSION_ARGV_ALLOWLISTS)
    assert projection["mutating_sessions"] == [kernel.SESSION_S2_1_QUIESCE_FENCE]
    assert projection["production_grade_target_classes"] == sorted(
        {kernel.TARGET_CLASS_PRODUCTION, kernel.TARGET_CLASS_UNKNOWN}
    )
    # P1-A / P1-B 的兩條硬邊界必須在 artifact 上看得見(稽核不必讀原始碼)。
    assert projection["rehearsal_only_target_classes"] == [
        kernel.TARGET_CLASS_DISPOSABLE_CANDIDATE
    ]
    assert kernel.TARGET_CLASS_DISPOSABLE_CANDIDATE not in projection[
        "derivable_target_classes"
    ]
    assert projection["production_entry_intent_target_class"] == (
        kernel.INTENT_TARGET_CLASS_PRODUCTION
    )
    # 出境守衛必須在 artifact 上看得見,且其判準明記為 capture_v2 的既有規則(非自造)。
    assert projection["egress_secret_scanner"].endswith(
        "scan_serializable_surface_for_secrets"
    )
    assert projection["egress_secret_scanner_rules"].endswith("SECRET_VALUE_PATTERNS")


# --------------------------------------------------------------------------- #
# (6) 出境秘密掃描 —— 判準必須是 capture_v2 的既有規則,而不是本 kernel 自造的第二套
# --------------------------------------------------------------------------- #
# 反例以片段拼接構造(repo 內不留任何看起來像真憑證的字面量);三段分別命中
# ``SECRET_VALUE_PATTERNS`` 的三條規則:賦值形 / bearer 形 / URL user:pass 形。
_SECRET_SHAPED_VALUES = (
    "PG" + "PASSWORD" + "=" + "s3cr3t-not-real",
    "Authorization: " + "Bearer " + "abcdef0123456789",
    "htt" + "ps://reader" + ":" + "s3cr3t-not-real" + "@trade-core/db",
)


def _clean_observation() -> dict:
    """一份形狀與真 observation 相同、但不含任何 secret 形的 payload。"""

    return {
        "schema_version": "s2_host_observation_v1",
        "observed_at": "2026-07-29T00:00:00Z",
        "target_class_view": kernel.derive_host_target_class(),
        "request_digest": "sha256:" + "0" * 64,
        "faces": {
            "unit_state": {
                "unit": "arcane-equilibrium-aiml-engine-scanner.service",
                "properties": {
                    "ActiveState": "active",
                    "Environment": "ALR_SOURCE_HEAD=" + "0" * 40,
                    "FragmentPath": "/etc/systemd/system/x.service",
                },
            },
            "file_identity": {"unit_fragment": {"present": False, "mode": "0644"}},
        },
        "self_digest": "sha256:" + "1" * 64,
    }


def test_a_clean_observation_shaped_payload_is_not_flagged():
    assert kernel.scan_serializable_surface_for_secrets(_clean_observation()) == []


@pytest.mark.parametrize("value", _SECRET_SHAPED_VALUES)
def test_every_central_secret_rule_blocks_an_observation(value):
    payload = _clean_observation()
    payload["faces"]["unit_state"]["properties"]["Environment"] = value
    reasons = kernel.scan_serializable_surface_for_secrets(payload)
    assert reasons, value
    # 理由只帶鍵名 trail;命中的值本身**絕不**出現在理由裡(否則理由就是第二條洩漏路徑)。
    assert "faces.unit_state.properties.Environment" in reasons[0]
    assert value not in reasons[0]


def test_the_key_value_adjacency_form_is_caught_too():
    """``{"password": "..."}`` 這種「鍵值相鄰」形只有掃 canonical JSON bytes 才看得見。"""

    payload = _clean_observation()
    payload["faces"]["pg_acl"] = {"pass" + "word": "s3cr3t-not-real"}
    reasons = kernel.scan_serializable_surface_for_secrets(payload)
    assert reasons and "faces.pg_acl" in reasons[0]


def test_the_scanner_delegates_to_the_capture_v2_rules_not_a_second_set():
    import inspect

    from agent_governance_command_capture_v2 import SECRET_VALUE_PATTERNS

    source = inspect.getsource(kernel._carries_secret_shaped_value)
    assert "from agent_governance_command_capture_v2 import _redact_preview" in source
    # kernel 不得自造第二套 secret 正則。
    assert "re.compile" not in source
    # 中央規則各有一個對應反例:新增一條中央規則而沒補反例 ⇒ 本測試變紅。
    assert len(SECRET_VALUE_PATTERNS) == len(_SECRET_SHAPED_VALUES)


def test_the_non_http_uri_dsn_gap_is_pinned_as_an_honest_boundary():
    """釘住殘餘缺口:中央規則的 URL 形只涵蓋 ``http(s)`` scheme,不涵蓋 DB-scheme 的 URI 形。

    這條缺口**不在**本波收口:正確的修法是把該形併進
    ``agent_governance_command_capture_v2.SECRET_VALUE_PATTERNS``(那樣全 repo 的 governed capture
    preview 一起受惠),而在 runner 家族自造第二套判準正是本波刻意拒絕的事。repo 內另有一支涵蓋
    該形的 ``public_repo_security_gate.EMBEDDED_CREDENTIAL_DSN``,但那個模組 ``import subprocess``
    ⇒ 匯入它等於給 runner 家族重開一條完整 exec 路徑(E2 RES-5 收掉的那條縫),故不採用。S2.4
    實際使用的封閉 DSN 是 libpq 鍵值形,那一形**有**被擋(下面第二個斷言)。未來一旦中央規則加寬,
    本測試變紅並被看見。
    """

    uri_form = "postgre" + "sql://reader" + ":" + "s3cr3t-not-real" + "@trade-core/db"
    assert kernel.scan_serializable_surface_for_secrets({"faces": uri_form}) == []
    libpq_form = "host=127.0.0.1 " + "pass" + "word=" + "s3cr3t-not-real" + " dbname=x"
    assert kernel.scan_serializable_surface_for_secrets({"faces": libpq_form})


def test_an_unserializable_payload_is_scanned_rather_than_waved_through():
    class _Opaque:
        def __repr__(self) -> str:
            return _SECRET_SHAPED_VALUES[0]

    assert kernel.scan_serializable_surface_for_secrets({"faces": _Opaque()})
