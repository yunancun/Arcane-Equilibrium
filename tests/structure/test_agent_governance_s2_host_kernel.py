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
# S2E.2b-1 曾以手維護 tuple 當 AST scanner 的唯一輸入；新 runner 若漏加便完全不被看見。
# 現在 family 直接由磁碟形狀導出，新增符合命名契約的 runner 在同一個 test run 即進 scanner。
RUNNER_FAMILY_GLOBS = ("agent_governance_s2_*host_*.py", "aiml_s2_*host_run*.py")
# glob 是形狀判準,不是語義判準:S2.4 的 row driver **protocol 葉**恰好也叫 ``…_host_identity``,
# 但它不是 runner(沒有 lane、沒有主機能力、其匯入面由 S2.4 wave 治理)。故此處允許顯式除名,
# 但除名**只**豁免 per-file import 白名單與 ``shell=`` 呼叫形狀兩項:被除名的檔案仍要通過
# raw-command 掃描的其餘每一道,且一律不得碰 :data:`KERNEL_ONLY_IMPORTS` 或
# :data:`EXEC_CAPABLE_IMPORT_DENYLIST`。
#
# S2E.2b-1 P2-1(E2 實證):關掉正面 import 白名單,關掉的**恰好**是唯一擋得住 ``pty`` /
# ``importlib`` 的那一道——E2 兩個全綠反例是「除名檔帶 ``pty.spawn(argv)``」與「除名檔帶
# ``importlib.import_module(name)``」(名稱是變數,故字面拼接那道也抓不到)。原註解宣稱「四道
# 一道都不放…根本沒有任何 shell 可以到達」是 **overclaim,在此撤回**。改法:除名 = 白名單關掉
# **加上**一張顯式 import 黑名單(下方 :data:`EXEC_CAPABLE_IMPORT_DENYLIST`),於是「把新
# runner 塞進除名表」仍然換不到任何 exec 能力,只換到一次必須寫明理由的顯式動作。
NON_RUNNER_HOST_LEAVES = {
    "agent_governance_s2_4_host_identity.py": (
        "S2.4 HOST_IDENTITY_INSTALL row 的 typed driver Protocol 與純導出葉;它不驅動任何 lane、"
        "不持有主機能力,匯入面屬 s2_4_install_adapter_v1 的 component_paths 治理範圍"
    ),
}


def _discover_runner_family(helpers_dir: Path) -> list[Path]:
    """由磁碟導出受信 host runner family；只有具理由的 protocol 葉可除名。"""

    return sorted({
        path
        for glob in RUNNER_FAMILY_GLOBS
        for path in helpers_dir.glob(glob)
        if path.name not in NON_RUNNER_HOST_LEAVES
    })


RUNNER_FAMILY = tuple(_discover_runner_family(HELPERS))
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
    # aggregate 交易葉的 rollback 契約、殘留觀測與 lock-release 折入政策,絕不另抄一份),
    # 也是唯一需要中央 schema/digest 驗證器的成員(permit 身分與 rollback artifact 的再導出)。
    # 本表是**每檔模組**白名單,不限於 ``agent_governance_*`` 前綴——前綴是名字,不是能力。
    "agent_governance_s2_4_host_recovery.py": frozenset({
        "agent_governance_s2_4_component",
        "agent_governance_s2_4_install_driver",
        "agent_governance_s2_4_install_evidence",
        "agent_governance_s2_4_journal",
        "agent_governance_s2_4_lock",
        "agent_governance_s2_4_reconcile",
        "aiml_gate_receipt_validator",
    }),
    "aiml_s2_effect_host_run.py": frozenset({
        "agent_governance_alr_quiesce_fence",
        "agent_governance_pg_observer_bootstrap",
        "agent_governance_s2_0_host_runner",
        "agent_governance_s2_1_host_runner",
        "agent_governance_s2_4_host_recovery",
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
# S2E.2b-1 P2-1:除名檔案(``exec_family=False``)沒有正面白名單可依,故改以一張顯式**黑**名單
# 兜底。每一個都是一條完整的行程生成/動態載入路徑,且沒有任何一條是 protocol 葉會需要的:
# ``pty``(``spawn``)、``importlib``(名稱可為變數 ⇒ 字面拼接那道抓不到)、``commands``、
# ``asyncio``(``create_subprocess_exec``)、``multiprocessing``(``Popen``/spawn)。
EXEC_CAPABLE_IMPORT_DENYLIST = frozenset({
    "pty", "importlib", "commands", "asyncio", "multiprocessing", "runpy", "imp",
    "code", "pdb", "timeit", "concurrent",
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
DYNAMIC_ATTRIBUTE_BUILTINS = frozenset({
    "getattr", "setattr", "delattr", "__getattribute__",
})
# 被字串拼接混淆出來就一定是繞過意圖的識別碼。
OBFUSCATION_SENSITIVE_LITERALS = (
    FORBIDDEN_RAW_COMMAND_NAMES | FORBIDDEN_BUILTINS
    | {"subprocess", "importlib", "pty", "commands", "ctypes"}
)
FORBIDDEN_EXEC_CAPABILITY_NAMES = (
    FORBIDDEN_RAW_COMMAND_NAMES
    | FORBIDDEN_BUILTINS
    | {
        "run_module", "run_path", "import_module", "reload", "interact", "runcall",
        "runctx", "timeit", "repeat", "ProcessPoolExecutor", "create_subprocess_exec",
        "create_subprocess_shell", "capture_command",
    }
)
SUBPROCESS_EXEC_CAPABILITY_NAMES = frozenset({
    "run", "Popen", "call", "check_call", "check_output", "getoutput",
    "getstatusoutput",
})


def _present_family() -> list[Path]:
    return _discover_runner_family(HELPERS)


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
    POSIX 帳號的**登入 shell** 當一個同名欄位傳給 ``create_system_account``。

    S2E.2b-1 P2-1:關掉①原本連帶關掉了唯一擋得住 ``pty`` / ``importlib`` 的那一道(E2 兩個全綠
    反例)。故除名路徑改為「白名單關掉 **+** :data:`KERNEL_ONLY_IMPORTS` ∪
    :data:`EXEC_CAPABLE_IMPORT_DENYLIST` 顯式黑名單」;其餘四道(raw-command 名稱 / builtin /
    動態取名 / 字面拼接)本來就照跑。
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
    dynamic_callable_aliases: set[str] = set()
    dynamic_return_functions: set[str] = set()
    ctypes_handles: set[str] = set()
    builtins_aliases: set[str] = {"__builtins__", "builtins"}
    module_registry_aliases: set[str] = set()
    module_lookup_aliases: set[str] = set()
    os_aliases: set[str] = {"os"}
    subprocess_aliases: set[str] = {"subprocess"}
    container_aliases: dict[str, object] = {}
    family_aliases = {
        "builtins": builtins_aliases, "ctypes": ctypes_handles,
        "module_lookup": module_lookup_aliases,
        "module_registry": module_registry_aliases, "os": os_aliases,
        "subprocess": subprocess_aliases,
    }
    for imported in (item for item in ast.walk(tree) if isinstance(item, ast.Import)):
        for alias in imported.names:
            if alias.name.split(".")[0] == "os":
                os_aliases.add(alias.asname or alias.name.split(".")[0])
    containing_function: dict[int, str] = {}
    for function in (
        item for item in ast.walk(tree)
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
    ):
        for child in ast.walk(function):
            containing_function[id(child)] = function.name

    def _check_module(lineno: int, module: str, rendered: str) -> None:
        top = (module or "").split(".")[0]
        if allowed_modules is None:
            # 除名檔案:白名單關掉,但 kernel 專屬三支 + exec-capable 黑名單一律仍擋。
            if top in KERNEL_ONLY_IMPORTS:
                findings.append(
                    f"line {lineno}: kernel-only module outside the kernel: {rendered}"
                )
            elif top in EXEC_CAPABLE_IMPORT_DENYLIST:
                findings.append(
                    f"line {lineno}: exec-capable module on a non-runner leaf: {rendered}"
                )
            return
        if top in allowed_modules:
            return
        findings.append(f"line {lineno}: import outside the declared allowlist: {rendered}")

    def _flatten_provenance(provenance: object) -> set[str]:
        if isinstance(provenance, set):
            return set(provenance)
        families: set[str] = set()
        if isinstance(provenance, dict):
            for member in provenance.values():
                families.update(_flatten_provenance(member))
        return families

    def _merge_provenance(left: object, right: object) -> object:
        if isinstance(left, dict) and isinstance(right, dict):
            merged = dict(left)
            for key, member in right.items():
                merged[key] = (
                    _merge_provenance(merged[key], member)
                    if key in merged else member
                )
            return merged
        return _flatten_provenance(left) | _flatten_provenance(right)

    def _value_provenance(node: ast.AST | None) -> object:
        if isinstance(node, ast.Name):
            if node.id in container_aliases:
                return container_aliases[node.id]
            families = {
                family for family, aliases in family_aliases.items()
                if node.id in aliases
            }
            return families | ({"ctypes"} if node.id == "ctypes" else set())
        if isinstance(node, (ast.List, ast.Tuple)):
            return {
                index: _value_provenance(item)
                for index, item in enumerate(node.elts)
            }
        if isinstance(node, ast.Dict):
            return {
                key.value: _value_provenance(item)
                for key, item in zip(node.keys, node.values)
                if isinstance(key, ast.Constant)
            }
        if isinstance(node, ast.Attribute):
            if (
                node.attr == "modules" and isinstance(node.value, ast.Name)
                and node.value.id == "sys"
            ):
                return {"module_registry"}
            return {"subprocess"} if node.attr == "subprocess" else set()
        if isinstance(node, ast.Call):
            if (
                isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "ctypes"
                and node.func.attr == "CDLL"
            ):
                return {"ctypes"}
            if (
                isinstance(node.func, ast.Attribute) and node.func.attr == "get"
                and "module_registry" in _flatten_provenance(
                    _value_provenance(node.func.value)
                )
            ):
                return {"module_lookup"}
            return set()
        if isinstance(node, ast.Subscript):
            provenance = _value_provenance(node.value)
            if isinstance(provenance, dict):
                provenance = (
                    provenance.get(node.slice.value, set())
                    if isinstance(node.slice, ast.Constant)
                    else _flatten_provenance(provenance)
                )
            families = _flatten_provenance(provenance)
            if isinstance(provenance, set) and "module_registry" in families:
                return (families - {"module_registry"}) | {"module_lookup"}
            return provenance
        return set()

    def _value_families(node: ast.AST | None) -> set[str]:
        return _flatten_provenance(_value_provenance(node))

    def _module_registry(receiver: ast.AST | None) -> bool:
        return "module_registry" in _value_families(receiver)

    def _module_lookup(receiver: ast.AST | None) -> bool:
        return "module_lookup" in _value_families(receiver)

    def _builtins_source(node: ast.AST | None) -> bool:
        return "builtins" in _value_families(node)

    def _callee_capability(node: ast.AST) -> str | None:
        """Resolve only execution-capable callees; unknown data stays fail-closed."""

        def _sensitive_receiver(receiver: ast.AST | None) -> bool:
            return (
                bool(_value_families(receiver) & {
                    "builtins", "ctypes", "module_lookup", "module_registry",
                    "os", "subprocess",
                })
                or isinstance(receiver, ast.Attribute)
                and (
                    _sensitive_receiver(receiver.value)
                )
            )

        if isinstance(node, ast.Name):
            if node.id in FORBIDDEN_EXEC_CAPABILITY_NAMES:
                return node.id
            if node.id in dynamic_callable_aliases:
                return "dynamic callable alias"
            return None
        if isinstance(node, ast.Attribute):
            if (
                node.attr in SUBPROCESS_EXEC_CAPABILITY_NAMES
                and "module_lookup" in _value_families(node.value)
            ):
                return "dynamic module execution"
            if (
                node.attr in SUBPROCESS_EXEC_CAPABILITY_NAMES
                and "subprocess" in _value_families(node.value)
            ):
                return "raw subprocess execution"
            return node.attr if node.attr in FORBIDDEN_EXEC_CAPABILITY_NAMES else None
        if isinstance(node, ast.Subscript):
            key = _fold_string(node.slice)
            if key in FORBIDDEN_EXEC_CAPABILITY_NAMES:
                return "dynamic execution subscript"
            if (
                _builtins_source(node.value)
                or isinstance(node.value, ast.Name)
                and node.value.id in dynamic_callable_aliases
            ):
                return "dynamic execution subscript"
            if (
                _module_registry(node.value)
            ):
                return "dynamic module execution"
            if (
                isinstance(node.value, ast.Attribute)
                and node.value.attr == "__dict__"
                and _module_lookup(node.value.value)
            ):
                return "dynamic module execution"
            return None
        if isinstance(node, ast.Call):
            if (
                isinstance(node.func, ast.Attribute)
                and node.func.attr == "get"
                and _builtins_source(node.func.value)
            ):
                return "dynamic execution subscript"
            called = (
                node.func.id if isinstance(node.func, ast.Name)
                else node.func.attr if isinstance(node.func, ast.Attribute) else None
            )
            if called in {"getattr", "__getattribute__"}:
                name_arg = (
                    node.args[1] if called == "getattr" and len(node.args) >= 2
                    else node.args[-1] if len(node.args) >= 2 else None
                )
                folded = _fold_string(name_arg) if name_arg is not None else None
                if folded in FORBIDDEN_EXEC_CAPABILITY_NAMES:
                    return folded
                receiver = (
                    node.args[0] if called == "getattr" and node.args
                    else node.func.value if isinstance(node.func, ast.Attribute) else None
                )
                if folded is None and _sensitive_receiver(receiver):
                    return "dynamic callable attribute"
            if isinstance(node.func, ast.Name) and node.func.id in dynamic_return_functions:
                return "dynamic callable return"
        if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
            if any(_callee_capability(item) is not None for item in node.elts):
                return "dynamic callable container"
        if isinstance(node, ast.Dict):
            if any(
                item is not None and _callee_capability(item) is not None
                for item in node.values
            ):
                return "dynamic callable container"
        return None

    # A dynamic getter can be returned by a helper and invoked later.
    for function in (
        item for item in ast.walk(tree)
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
    ):
        if any(
            _callee_capability(item.value) is not None
            for item in ast.walk(function)
            if isinstance(item, ast.Return) and item.value is not None
        ):
            dynamic_return_functions.add(function.name)

    # A dynamic getattr/subscript/container can be assigned and called later. Propagate
    # aliases to a fixed point so ``f = getattr(os, name); box = [f]; box[0](...)`` cannot
    # hide the callee.
    def _assignment_bindings(
        target: ast.AST, value: ast.AST | None
    ) -> list[tuple[ast.AST, ast.AST | None]]:
        if (
            isinstance(target, (ast.List, ast.Tuple))
            and isinstance(value, (ast.List, ast.Tuple))
            and len(target.elts) == len(value.elts)
        ):
            return [
                binding
                for item_target, item_value in zip(target.elts, value.elts)
                for binding in _assignment_bindings(item_target, item_value)
            ]
        return [(target, value)]

    changed = True
    while changed:
        changed = False
        for node in ast.walk(tree):
            value: ast.AST | None = None
            targets: list[ast.AST] = []
            if isinstance(node, ast.Assign):
                value, targets = node.value, list(node.targets)
            elif isinstance(node, ast.AnnAssign):
                value, targets = node.value, [node.target]
            elif isinstance(node, ast.NamedExpr):
                value, targets = node.value, [node.target]
            bindings = [
                binding
                for target in targets
                for binding in _assignment_bindings(target, value)
            ]
            for target, bound_value in bindings:
                if not isinstance(target, ast.Name):
                    continue
                provenance = _value_provenance(bound_value)
                for family in _flatten_provenance(provenance):
                    aliases = family_aliases[family]
                    if target.id not in aliases:
                        aliases.add(target.id)
                        changed = True
                if (
                    isinstance(provenance, dict)
                ):
                    merged = _merge_provenance(
                        container_aliases.get(target.id, {}), provenance
                    )
                    if container_aliases.get(target.id) != merged:
                        container_aliases[target.id] = merged
                        changed = True
            for target, bound_value in bindings:
                if bound_value is None or _callee_capability(bound_value) is None:
                    continue
                names = [
                    item.id for item in ast.walk(target)
                    if isinstance(item, ast.Name) and isinstance(item.ctx, ast.Store)
                ]
                for name in names:
                    if name not in dynamic_callable_aliases:
                        dynamic_callable_aliases.add(name)
                        changed = True

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                _check_module(node.lineno, alias.name, f"import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if node.level:
                findings.append(
                    f"line {node.lineno}: relative import is outside the declared allowlist"
                )
            _check_module(node.lineno, module, f"from {module} import ...")
            for alias in node.names:
                if alias.name == "*":
                    findings.append(
                        f"line {node.lineno}: star import is outside the declared capability allowlist"
                    )
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
                name_arg = (
                    node.args[1] if called == "getattr" and len(node.args) >= 2
                    else node.args[-1] if len(node.args) >= 2 else None
                )
                if isinstance(name_arg, ast.Constant) and isinstance(name_arg.value, str):
                    if name_arg.value in OBFUSCATION_SENSITIVE_LITERALS:
                        findings.append(
                            f"line {node.lineno}: {called}(…, {name_arg.value!r})"
                        )
                elif not isinstance(name_arg, ast.Name):
                    findings.append(
                        f"line {node.lineno}: {called}() with a computed attribute name"
                    )
            capability = _callee_capability(func)
            if capability == "dynamic callable attribute":
                findings.append(f"line {node.lineno}: dynamic callable attribute")
            elif capability == "dynamic execution subscript":
                findings.append(f"line {node.lineno}: dynamic execution subscript")
            elif capability == "dynamic callable alias":
                findings.append(f"line {node.lineno}: dynamic callable alias")
            elif capability == "dynamic callable return":
                findings.append(f"line {node.lineno}: dynamic callable return")
            elif capability == "dynamic module execution":
                findings.append(f"line {node.lineno}: dynamic module execution")
            elif capability == "raw subprocess execution":
                exact_kernel_run = (
                    is_kernel
                    and containing_function.get(id(node)) == "_execute"
                    and isinstance(func, ast.Attribute)
                    and isinstance(func.value, ast.Name)
                    and func.value.id == "subprocess"
                    and func.attr == "run"
                    and len(node.args) == 1
                    and isinstance(node.args[0], ast.Call)
                    and isinstance(node.args[0].func, ast.Name)
                    and node.args[0].func.id == "list"
                    and {
                        keyword.arg for keyword in node.keywords
                    } == {
                        "shell", "stdin", "stdout", "stderr", "env", "timeout", "check",
                    }
                    and all(
                        not (
                            keyword.arg in {"shell", "check"}
                            and not (
                                isinstance(keyword.value, ast.Constant)
                                and keyword.value.value is False
                            )
                        )
                        for keyword in node.keywords
                    )
                )
                if not exact_kernel_run:
                    findings.append(f"line {node.lineno}: raw subprocess execution")
            if (
                isinstance(func, ast.Attribute)
                and isinstance(func.value, ast.Name)
                and func.value.id == "ctypes"
                and func.attr in {"CDLL", "get_errno"}
            ):
                exact_cdll = (
                    is_kernel
                    and containing_function.get(id(node)) == "enforce_process_hardening"
                    and (
                        func.attr == "get_errno"
                        and not node.args
                        and not node.keywords
                        or func.attr == "CDLL"
                        and len(node.args) == 1
                        and isinstance(node.args[0], ast.Constant)
                        and node.args[0].value is None
                        and len(node.keywords) == 1
                        and node.keywords[0].arg == "use_errno"
                        and isinstance(node.keywords[0].value, ast.Constant)
                        and node.keywords[0].value.value is True
                    )
                )
                if not exact_cdll:
                    findings.append(
                        f"line {node.lineno}: ctypes call outside the hardening allowlist"
                    )
            if (
                isinstance(func, ast.Attribute)
                and isinstance(func.value, ast.Name)
                and func.value.id in ctypes_handles
            ):
                exact_prctl = (
                    is_kernel
                    and containing_function.get(id(node)) == "enforce_process_hardening"
                    and func.attr == "prctl"
                    and len(node.args) == 5
                    and isinstance(node.args[0], ast.Name)
                    and node.args[0].id in {"_PR_SET_DUMPABLE", "_PR_GET_DUMPABLE"}
                    and all(
                        isinstance(item, ast.Constant) and item.value == 0
                        for item in node.args[1:]
                    )
                    and not node.keywords
                )
                if not exact_prctl:
                    findings.append(
                        f"line {node.lineno}: ctypes call outside the hardening allowlist"
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
    # (raw-command 名稱 / builtin / 動態取名 / 字面拼接 / kernel-only + exec-capable 模組)
    # 一道都不放。
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


# S2E.2b-1 P2-1:E2 的兩個全綠反例 —— 除名檔案帶 ``pty.spawn`` / ``importlib.import_module``。
# 兩者在修前都完全不被任何一道抓到(白名單被關掉、模組名不是被禁**屬性**名、
# ``import_module(name)`` 的名稱是**變數**故字面拼接那道也沉默)。
EXEMPT_LEAF_EXEC_COUNTEREXAMPLES = {
    "E2_pty_spawn_on_an_exempt_leaf": "import pty\n\n\ndef f(argv):\n    return pty.spawn(argv)\n",
    "E2_importlib_dynamic_name_on_an_exempt_leaf": (
        "import importlib\n\n\ndef f(name):\n    return importlib.import_module(name)\n"
    ),
    "asyncio_create_subprocess": (
        "import asyncio\n\n\nasync def f(argv):\n"
        "    return await asyncio.create_subprocess_exec(*argv)\n"
    ),
    "multiprocessing_spawn": (
        "import multiprocessing\n\n\ndef f(fn):\n    return multiprocessing.Process(target=fn)\n"
    ),
    "commands_legacy": ("import commands\n\n\ndef f(cmd):\n    return commands.getoutput(cmd)\n"),
}


@pytest.mark.parametrize("mutation", sorted(EXEMPT_LEAF_EXEC_COUNTEREXAMPLES))
def test_the_exec_family_exemption_never_admits_an_exec_capable_module(tmp_path, mutation):
    path = tmp_path / f"{mutation}.py"
    path.write_text(EXEMPT_LEAF_EXEC_COUNTEREXAMPLES[mutation], encoding="utf-8")
    findings = _raw_command_findings(path, exec_family=False)
    assert any("exec-capable module on a non-runner leaf" in item for item in findings), findings
    # 對照:同一份 source 在 exec 家族路徑上本來就被正面白名單擋下(兩條路都紅,不是二選一)。
    assert _raw_command_findings(path, exec_family=True)


@pytest.mark.parametrize("module", sorted(EXEC_CAPABLE_IMPORT_DENYLIST))
@pytest.mark.parametrize("form", ["import {m}", "import {m}.sub", "from {m} import x"])
def test_every_exec_capable_denylist_entry_is_caught_in_every_import_form(
    tmp_path, module, form
):
    path = tmp_path / f"denied_{module}_{abs(hash(form))}.py"
    path.write_text(form.format(m=module) + "\n", encoding="utf-8")
    assert any(
        "exec-capable module on a non-runner leaf" in item
        for item in _raw_command_findings(path, exec_family=False)
    ), (module, form)


def test_the_two_import_denylists_never_overlap_the_positive_allowlist():
    # 黑名單若與白名單相交,exec 家族上就會出現「宣告過但仍被擋」的自相矛盾條目。
    allowed = ALLOWED_STDLIB_IMPORTS | ALLOWED_THIRD_PARTY_IMPORTS
    for name, modules in GOVERNANCE_IMPORTS_BY_FILE.items():
        allowed = allowed | modules
    assert not (EXEC_CAPABLE_IMPORT_DENYLIST & allowed)
    assert not (EXEC_CAPABLE_IMPORT_DENYLIST & KERNEL_ONLY_IMPORTS)


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


def test_the_runner_family_is_auto_discovered_not_copied_into_a_tuple(tmp_path):
    """新增 runner 不需第二次手改表；檔案一出現就立刻進 scanner 的輸入集合。"""

    expected = []
    for name in (
        "agent_governance_s2_9_host_runner.py",
        "aiml_s2_other_host_run.py",
    ):
        path = tmp_path / name
        path.write_text("x = 1\n", encoding="utf-8")
        expected.append(path)
    # 形似 host protocol 的已解釋除名葉不進 exec family。
    (tmp_path / "agent_governance_s2_4_host_identity.py").write_text(
        "x = 1\n", encoding="utf-8"
    )
    assert _discover_runner_family(tmp_path) == sorted(expected)


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
    # ── S2E.LW1:callee alias / dynamic attribute / string-index execution escapes ──
    "dynamic_getattr_name_then_call": (
        "import os\n\ndef f(name, argv):\n    return getattr(os, name)(*argv)\n",
        "dynamic callable attribute",
    ),
    "builtins_string_index_then_call": (
        "def f(expr):\n    return __builtins__['e' + 'val'](expr)\n",
        "dynamic execution subscript",
    ),
    "compile_attribute_alias": (
        "def f(builtins_obj, source):\n"
        "    compiler = getattr(builtins_obj, 'compile')\n"
        "    return compiler(source, '<x>', 'exec')\n",
        "getattr(…, 'compile')",
    ),
    "dynamic_callable_alias_chain": (
        "import os\n\ndef f(name, argv):\n"
        "    first = getattr(os, name)\n    second = first\n    return second(*argv)\n",
        "dynamic callable alias",
    ),
    "variable_builtins_key_then_call": (
        "def f(key, expr):\n    return __builtins__[key](expr)\n",
        "dynamic execution subscript",
    ),
    "builtins_alias_variable_subscript": (
        "def f(key, expr):\n"
        "    builtins_alias = __builtins__\n"
        "    return builtins_alias[key](expr)\n",
        "dynamic execution subscript",
    ),
    "builtins_get_variable_key_then_call": (
        "def f(key, expr):\n    return __builtins__.get(key)(expr)\n",
        "dynamic execution subscript",
    ),
    "nested_list_held_builtins_alias_variable_subscript": (
        "def f(key, expr):\n"
        "    outer = [[__builtins__]]\n"
        "    return outer[0][0][key](expr)\n",
        "dynamic execution subscript",
    ),
    "recursively_unpacked_builtins_alias_variable_subscript": (
        "def f(key, expr):\n"
        "    _, (harmless, builtins_alias) = (object(), (object(), __builtins__))\n"
        "    return builtins_alias[key](expr)\n",
        "dynamic execution subscript",
    ),
    "variable_sys_modules_key_then_run": (
        "import sys\n\ndef f(key, argv):\n    return sys.modules[key].run(argv)\n",
        "dynamic module execution",
    ),
    "sys_modules_alias_variable_subscript": (
        "import sys\n\ndef f(key, argv):\n"
        "    module_map = sys.modules\n"
        "    return module_map[key].run(argv)\n",
        "dynamic module execution",
    ),
    "sys_modules_get_variable_key_then_run": (
        "import sys\n\ndef f(key, argv):\n"
        "    return sys.modules.get(key).run(argv)\n",
        "dynamic module execution",
    ),
    "sys_modules_dunder_dict_variable_lookup": (
        "import sys\n\ndef f(module_key, name, argv):\n"
        "    return sys.modules[module_key].__dict__[name](argv)\n",
        "dynamic module execution",
    ),
    "assigned_sys_modules_lookup_alias_call": (
        "import sys\n\ndef f(module_key, argv):\n"
        "    sp = sys.modules[module_key]\n"
        "    return sp.call(argv)\n",
        "dynamic module execution",
    ),
    "recursive_mixed_container_sys_modules_alias_call": (
        "import sys\n\ndef f(module_key, argv):\n"
        "    outer = ({'level': [(sys.modules,)]},)\n"
        "    sp = outer[0]['level'][0][0][module_key]\n"
        "    return sp.call(argv)\n",
        "dynamic module execution",
    ),
    "nested_list_held_sys_modules_alias_call": (
        "import sys\n\ndef f(key, argv):\n    outer = [[sys.modules]]\n"
        "    return outer[0][0][key].call(argv)\n", "dynamic module execution",
    ),
    "os_dunder_getattribute_then_call": (
        "import os\n\ndef f(name, argv):\n"
        "    return os.__getattribute__(os, name)(*argv)\n",
        "dynamic callable attribute",
    ),
    "imported_os_alias_variable_getattr": (
        "import os as operating_system\n\ndef f(name, argv):\n"
        "    return getattr(operating_system, name)(*argv)\n",
        "dynamic callable attribute",
    ),
    "assigned_os_alias_variable_getattr": (
        "import os\n\ndef f(name, argv):\n"
        "    other = os\n"
        "    return getattr(other, name)(*argv)\n",
        "dynamic callable attribute",
    ),
    "dict_held_os_alias_variable_getattr": (
        "import os\n\ndef f(name, argv):\n"
        "    box = {'safe': object(), 'os': os}\n"
        "    return getattr(box['os'], name)(*argv)\n",
        "dynamic callable attribute",
    ),
    "nested_list_held_os_alias_variable_getattr": (
        "import os\n\ndef f(name, argv):\n    outer = [[os]]\n"
        "    return getattr(outer[0][0], name)(*argv)\n", "dynamic callable attribute",
    ),
    "computed_getattr_stored_in_container": (
        "import os\n\ndef f(name, argv):\n"
        "    calls = [getattr(os, name)]\n    return calls[0](*argv)\n",
        "dynamic execution subscript",
    ),
    "computed_getattr_returned_then_called": (
        "import os\n\ndef pick(name):\n    return getattr(os, name)\n"
        "\ndef f(name, argv):\n    return pick(name)(*argv)\n",
        "dynamic callable return",
    ),
    "already_imported_kernel_subprocess_run": (
        "def f(kernel, argv):\n    return kernel.subprocess.run(argv)\n",
        "raw subprocess execution",
    ),
    "already_imported_kernel_subprocess_popen": (
        "def f(kernel, argv):\n    return kernel.subprocess.Popen(argv)\n",
        "raw subprocess execution",
    ),
    "already_imported_kernel_subprocess_call": (
        "def f(kernel, argv):\n    return kernel.subprocess.call(argv)\n",
        "raw subprocess execution",
    ),
    "already_imported_kernel_subprocess_check_call": (
        "def f(kernel, argv):\n    return kernel.subprocess.check_call(argv)\n",
        "raw subprocess execution",
    ),
    "already_imported_kernel_subprocess_check_output": (
        "def f(kernel, argv):\n    return kernel.subprocess.check_output(argv)\n",
        "raw subprocess execution",
    ),
    "already_imported_kernel_subprocess_getoutput": (
        "def f(kernel, command):\n    return kernel.subprocess.getoutput(command)\n",
        "raw subprocess execution",
    ),
    "already_imported_kernel_subprocess_getstatusoutput": (
        "def f(kernel, command):\n"
        "    return kernel.subprocess.getstatusoutput(command)\n",
        "raw subprocess execution",
    ),
    "assigned_kernel_subprocess_alias_call": (
        "def f(kernel, argv):\n"
        "    sp = kernel.subprocess\n"
        "    return sp.call(argv)\n",
        "raw subprocess execution",
    ),
    "assigned_kernel_subprocess_alias_check_output": (
        "def f(kernel, argv):\n"
        "    sp = kernel.subprocess\n"
        "    return sp.check_output(argv)\n",
        "raw subprocess execution",
    ),
    "runpy_import_alias": (
        "import runpy as runner\nrunner.run_path('payload.py')\n",
        "import outside the declared allowlist",
    ),
    "concurrent_futures_from_alias": (
        "from concurrent import futures as pool\npool.ProcessPoolExecutor()\n",
        "import outside the declared allowlist",
    ),
    "relative_import": (
        "from . import helper\n",
        "relative import is outside the declared allowlist",
    ),
    "star_import": (
        "from os import *\n",
        "star import is outside the declared capability allowlist",
    ),
    "string_import_builtin": (
        "def f(b):\n    return getattr(b, '__import__')('subprocess')\n",
        "getattr(…, '__import__')",
    ),
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


def test_kernel_ctypes_is_limited_to_the_exact_prctl_hardening_shapes(tmp_path):
    """Kernel-only import is not a blanket libc FFI capability."""

    path = tmp_path / KERNEL_PATH.name
    path.write_text(
        "import ctypes\n"
        "libc = ctypes.CDLL('/tmp/foreign.so', use_errno=True)\n"
        "libc.execve(b'/bin/id', (), ())\n",
        encoding="utf-8",
    )
    findings = _raw_command_findings(path)
    assert any("ctypes call outside the hardening allowlist" in item for item in findings)


def test_assigned_ctypes_handle_cannot_hide_dynamic_ffi_getattr(tmp_path):
    path = tmp_path / KERNEL_PATH.name
    path.write_text(
        "import ctypes\n"
        "def enforce_process_hardening(name, argv):\n"
        "    libc = ctypes.CDLL(None, use_errno=True)\n"
        "    other = libc\n"
        "    return getattr(other, name)(*argv)\n",
        encoding="utf-8",
    )
    findings = _raw_command_findings(path)
    assert any("dynamic callable attribute" in item for item in findings), findings


def test_nested_ctypes_handle_cannot_hide_dynamic_ffi_getattr(tmp_path):
    path = tmp_path / KERNEL_PATH.name
    source = (
        "import ctypes\n"
        "def enforce_process_hardening(name, argv):\n"
        "    libc = ctypes.CDLL(None, use_errno=True)\n"
        "    outer = [[libc, object()]]\n"
        "    return getattr(outer[0][0], name)(*argv)\n"
    )
    path.write_text(source, encoding="utf-8")
    findings = _raw_command_findings(path)
    assert any("dynamic callable attribute" in item for item in findings), findings
    path.write_text(source.replace("[0][0]", "[0][1]"), encoding="utf-8")
    assert _raw_command_findings(path) == []


def test_container_aliases_do_not_taint_a_benign_sibling(tmp_path):
    sources = (
        "outer = [[__builtins__, {}]]\nouter[0][1][key](expr)\n",
        "import sys\nouter = [[sys.modules, {}]]\nouter[0][1][key].call(argv)\n",
        "import os\nouter = [[os, object()]]\ngetattr(outer[0][1], name)\n",
    )
    for index, source in enumerate(sources):
        path = tmp_path / f"benign_container_sibling_{index}.py"
        path.write_text(source, encoding="utf-8")
        assert _raw_command_findings(path) == []


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
