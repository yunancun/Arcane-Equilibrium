#!/usr/bin/env python3
"""S2.5(WP5)production driver 葉——typed allowlisted 動詞,unit 名為模組常量。

design §7:driver 只有五個動詞 ``enable_now / stop / disable / reset_failed / show``,
全部指向**常量** unit(``arcane-equilibrium-aiml-engine-scanner.service``);driver 不接受
caller 提供的 unit 名/參數/命令文本。argv 由 :func:`allowlisted_systemctl_argv` 唯一構造,
任何越出封閉表的動詞即 raise。

硬邊界(source lane):本模組 import 期零副作用、零 subprocess;``TypedSystemdDriver`` 不帶
預設 runner——**不注入 runner 就無法執行任何東西**。真 runner 只在 S2.5 EFFECT session 由
OPS 於 Linux 注入(帶 exact operator 授權之後);任何測試都不得以真實 systemd runner 呼叫
本 driver(fixtures 一律注入假 runner)。Mac/tests/no-driver 一律走 lifecycle 葉的
``driver is None`` 臂(EXTERNAL_VERIFICATION_PENDING,零變更)。九項 authority 恆 false。
"""
from __future__ import annotations

from typing import Any, Callable, Protocol

# 與 WP3 quiesce inventory 同一把 owner 確認尺的常量面(import 複用屬 lifecycle 葉;
# 此處只釘 unit 常量與二進位路徑,不做任何讀取)。
S2_5_UNIT_NAME = "arcane-equilibrium-aiml-engine-scanner.service"
SYSTEMD_EXECUTABLE = "/usr/bin/systemctl"

# 封閉動詞表:動詞 → exact argv 尾段(unit 名恆為常量;無任何 caller 參數縫)。
_S2_5_ALLOWLISTED_VERBS: dict[str, tuple[str, ...]] = {
    "enable_now": ("enable", "--now", S2_5_UNIT_NAME),
    "stop": ("stop", S2_5_UNIT_NAME),
    "disable": ("disable", S2_5_UNIT_NAME),
    "reset_failed": ("reset-failed", S2_5_UNIT_NAME),
    "show": ("show", S2_5_UNIT_NAME, "--no-pager"),
}
# 明確拒絕的動詞(縱深防禦;不在允許表本來就拒,列名是為了 typed 錯誤訊息)。
_S2_5_FORBIDDEN_VERBS = frozenset({
    "daemon_reload", "daemon-reload", "kill", "restart", "start", "mask", "unmask",
    "edit", "set-property", "link", "revert",
})


class S2_5DriverContractError(RuntimeError):
    """driver 契約層硬錯誤(帶 typed ``code``)。"""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def allowlisted_systemctl_argv(verb: str) -> list[str]:
    """唯一的 argv 構造點:封閉表外的動詞、或任何 ``--user`` 形一律 raise。"""

    if verb in _S2_5_FORBIDDEN_VERBS:
        raise S2_5DriverContractError(f"s2_5_forbidden_verb:{verb}")
    tail = _S2_5_ALLOWLISTED_VERBS.get(verb)
    if tail is None:
        raise S2_5DriverContractError(f"s2_5_unknown_verb:{verb}")
    return [SYSTEMD_EXECUTABLE, *tail]


class S2_5HostServiceDriver(Protocol):
    """lifecycle 葉消費的 typed driver 面(五動詞;無任何 caller 參數)。"""

    def enable_now(self) -> None: ...

    def stop(self) -> None: ...

    def disable(self) -> None: ...

    def reset_failed(self) -> None: ...

    def show(self) -> dict[str, str]: ...


class TypedSystemdDriver:
    """production driver 骨架:runner 必須顯式注入,否則任何動詞都 raise。

    ``runner(argv) -> str`` 由 OPS 在 EFFECT session 注入(真 subprocess 執行面);
    source lane / 測試注入假 runner。本類**沒有**預設 runner——「忘了注入」不會靜默
    降級成真執行,而是 typed 拒。
    """

    def __init__(self, runner: Callable[[list[str]], str] | None = None) -> None:
        self._runner = runner

    def _run(self, verb: str) -> str:
        if self._runner is None:
            raise S2_5DriverContractError("s2_5_driver_runner_absent")
        return self._runner(allowlisted_systemctl_argv(verb))

    def enable_now(self) -> None:
        self._run("enable_now")

    def stop(self) -> None:
        self._run("stop")

    def disable(self) -> None:
        self._run("disable")

    def reset_failed(self) -> None:
        self._run("reset_failed")

    def show(self) -> dict[str, str]:
        raw = self._run("show")
        properties: dict[str, str] = {}
        for line in str(raw).splitlines():
            key, separator, value = line.partition("=")
            if separator:
                properties[key.strip()] = value.strip()
        return properties


def s2_5_driver_abi_projection() -> dict[str, Any]:
    """driver 面的 code-owned 投影(registry 對賬/測試釘 allowlist 用)。"""

    return {
        "unit_name": S2_5_UNIT_NAME,
        "systemd_executable": SYSTEMD_EXECUTABLE,
        "allowlisted_verbs": {
            verb: list(allowlisted_systemctl_argv(verb))
            for verb in sorted(_S2_5_ALLOWLISTED_VERBS)
        },
        "forbidden_verbs": sorted(_S2_5_FORBIDDEN_VERBS),
    }
