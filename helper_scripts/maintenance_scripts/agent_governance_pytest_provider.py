"""Closed argv identity for governed no-site pytest execution."""

from __future__ import annotations


GOVERNED_PYTEST_BOOTSTRAP = (
    "import importlib.util,os,sys;"
    "_cwd=os.path.realpath(os.getcwd());"
    "sys.path[:]=[item for item in sys.path "
    "if item and os.path.realpath(item)!=_cwd];"
    "_provider_names=('exceptiongroup','iniconfig','packaging','pluggy',"
    "'pygments','pytest','tomli','typing_extensions');"
    "[__import__(name) for name in _provider_names "
    "if importlib.util.find_spec(name) is not None];"
    "import pytest;"
    "raise SystemExit(pytest.console_main())"
)
GOVERNED_PYTEST_PREFIX = (
    "python3",
    "-S",
    "-c",
    GOVERNED_PYTEST_BOOTSTRAP,
)
GOVERNED_PYTEST_REQUIRED_ARGS = (
    "--noconftest",
    "--import-mode=append",
    "-c",
    "/dev/null",
    "--rootdir=.",
)
