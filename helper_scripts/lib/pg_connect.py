"""共享 PG 連線 helper — offline report scripts 專用。

MODULE_NOTE:
  模塊用途：整併 W-AUDIT-8b / 8c / alpha_candidate report wrapper 之間原本
    byte-identical 的 PG 連線 helper（E5 finding #4 shared-lib infra）。三者原各有
    一份 ``_get_conn``，DSN 解析完全相同，只差 ``application_name`` 與預設
    ``statement_timeout``。
  主要函數：``connect_report_pg(application_name, *, statement_timeout_ms_default,
    statement_timeout_env)`` — 解析 DSN → psycopg2.connect → 設 statement_timeout。
  依賴：延遲匯入 psycopg2（連線時才 import，維持 metrics 層 import-time 零 DB 依賴）。
  硬邊界：
    - 只服務 offline report scripts；不得被 ``control_api_v1/app/`` runtime 匯入。
    - 不引入新可變 singleton（每次呼叫獨立 connection，由 caller 負責關閉）。
    - read-only 報告用途；本 helper 不執行任何寫操作。

  ── DSN 解析口徑（與整併前 8b/8c/alpha report wrapper byte-identical） ──
    優先 ``OPENCLAW_DATABASE_URL``；否則由離散 ``POSTGRES_*`` env 拼 DSN：
      ``postgresql://{USER}:{PASSWORD}@{HOST:-127.0.0.1}:{PORT:-5432}/{DB}``。
    為什麼禁硬編碼 hostname：feedback_cross_platform.md 跨平台原則（host 預設
    127.0.0.1，可被 env override）。
    2026-06-19 加一層保守 auth-drift fallback：若無 ``OPENCLAW_DATABASE_URL`` 且
    ``POSTGRES_PASSWORD`` 未設，才從
    ``${OPENCLAW_SECRETS_ROOT:-$HOME/BybitOpenClaw/secrets}/environment_files/basic_system_services.env``
    讀 ``POSTGRES_PASSWORD`` 一行補回 env；不 source 全檔、不覆蓋已設 env。

  ── 為什麼只整併「report wrapper 族」而非全 helper_scripts 連線函數 ──
    repo 內另有 ~20 個連線 helper（cron / db / research / calibration），其 DSN
    env-var 解析口徑不同（例：``DB_URL`` vs ``OPENCLAW_DATABASE_URL``、
    ``localhost`` vs ``127.0.0.1``、discrete kwargs vs URL string、secrets-file
    fallback、fail-closed exit-code 慣例不同），且部分是 runtime cron job（誤改
    會改變 production 連線目標）。本 helper 刻意只收口語意完全一致的 report
    wrapper 族（8b/8c/alpha），其餘留待後續分批整併（見報告 follow-up）。
    ``app/governance_routes.py::_get_autonomy_pg_conn`` 屬另一階段，明確不碰。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any


# report wrapper 族預設 statement_timeout（ms）。8b 歷史用 120000，8c / alpha 用
# 180000；保留各 caller 的歷史預設，故由 caller 顯式傳入，不在此設單一全域預設。
DEFAULT_STATEMENT_TIMEOUT_ENV = "OPENCLAW_STAGE0R_STATEMENT_TIMEOUT_MS"


def _load_secrets_pg_password() -> None:
    """缺 PG 密碼 env 時，從 canonical secrets env file 補 POSTGRES_PASSWORD。

    這只服務 ssh 直接 invoke report wrapper 的 auth drift：cron wrapper 會自行 export
    DSN/密碼；互動 shell 也可能已設 env。缺檔或缺 key 不報成功也不 raise，保留下游
    psycopg2 fail-loud 行為。
    """
    if os.environ.get("OPENCLAW_DATABASE_URL") or os.environ.get("POSTGRES_PASSWORD"):
        return

    secrets_root = os.environ.get("OPENCLAW_SECRETS_ROOT")
    if secrets_root:
        env_file = Path(secrets_root) / "environment_files" / "basic_system_services.env"
    else:
        env_file = (
            Path.home()
            / "BybitOpenClaw"
            / "secrets"
            / "environment_files"
            / "basic_system_services.env"
        )
    if not env_file.is_file():
        return

    try:
        for raw in env_file.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line.startswith("POSTGRES_PASSWORD="):
                continue
            val = line.split("=", 1)[1].strip()
            if len(val) >= 2 and val[0] in ("'", '"') and val[-1] == val[0]:
                val = val[1:-1]
            if val:
                os.environ["POSTGRES_PASSWORD"] = val
            return
    except OSError as exc:
        sys.stderr.write(f"WARN: read secrets env failed {env_file}: {exc}\n")


def resolve_report_dsn() -> str:
    """解析 report wrapper 族的 PG DSN。

    為什麼獨立成函數：方便測試 DSN 拼接邏輯，且未來其他 report 可只取 DSN 不連線。
    """
    _load_secrets_pg_password()
    return (
        os.environ.get("OPENCLAW_DATABASE_URL")
        or f"postgresql://{os.environ.get('POSTGRES_USER','')}"
        f":{os.environ.get('POSTGRES_PASSWORD','')}"
        f"@{os.environ.get('POSTGRES_HOST','127.0.0.1')}"
        f":{os.environ.get('POSTGRES_PORT','5432')}"
        f"/{os.environ.get('POSTGRES_DB','')}"
    )


def connect_report_pg(
    application_name: str,
    *,
    statement_timeout_ms_default: int,
    statement_timeout_env: str = DEFAULT_STATEMENT_TIMEOUT_ENV,
) -> Any:
    """連 PG（read-only 報告用），設 application_name 與 statement_timeout。

    為什麼參數化 application_name / timeout：8b/8c/alpha 三個 report wrapper 的
    連線邏輯 byte-identical，唯一差異是 application_name（PG 觀測標籤）與預設
    statement_timeout（8b=120000 / 8c=alpha=180000）。整併後由 caller 傳入其
    歷史值，連線目標與行為完全不變。

    為什麼延遲 import psycopg2：保持「metrics 純 math 層 import-time 無 DB 依賴」
    的既有契約；只有實際連線時才需要 psycopg2。
    連線 / query 失敗不在此吞（保留 psycopg2 fail-loud），由 caller 既有
    fail-closed exit path propagate（與整併前各 wrapper 行為一致）。
    """
    import psycopg2  # type: ignore

    conn = psycopg2.connect(resolve_report_dsn(), application_name=application_name)
    with conn.cursor() as cur:
        cur.execute(
            "SET statement_timeout = %s",
            (int(os.environ.get(statement_timeout_env, str(statement_timeout_ms_default))),),
        )
    conn.commit()
    return conn
