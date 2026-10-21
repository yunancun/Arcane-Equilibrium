"""U5 主機執行器；核對身份後才可由記錄者啟動固定離線映像。"""
from __future__ import annotations

import argparse
import ast
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import tempfile

from program_code.research.r8_engine.lean_algo import rules
from program_code.research.r8_ledger.ledger import ResearchLedger, canonical

ENGINE_ROOT = "program_code/research/r8_engine"
LEDGER_ROOT = "program_code/research/r8_ledger"
EXAMPLE = ENGINE_ROOT + "/lean_algo/examples/fixed_schedule.py"
FRAMEWORK = ENGINE_ROOT + "/lean_algo/framework.py"
IMAGE = "quantconnect/lean@" + rules.IMAGE_DIGEST
ALGORITHM_MEMBERS = {
    "math": set("acos acosh asin asinh atan atan2 atanh ceil comb copysign cos cosh degrees dist e erf erfc exp expm1 fabs factorial floor fmod frexp fsum gamma gcd hypot inf isclose isfinite isinf isnan isqrt lcm ldexp lgamma log log10 log1p log2 modf nan nextafter perm pi pow prod radians remainder sin sinh sqrt tan tanh tau trunc ulp".split()),
    "statistics": set("mean fmean geometric_mean harmonic_mean median median_low median_high median_grouped mode multimode pstdev pvariance stdev variance quantiles".split()),
    "decimal": set("Decimal Context ROUND_CEILING ROUND_DOWN ROUND_FLOOR ROUND_HALF_DOWN ROUND_HALF_EVEN ROUND_HALF_UP ROUND_UP ROUND_05UP InvalidOperation".split()),
    "fractions": {"Fraction"},
    "random": {"Random"},
    ENGINE_ROOT.replace("/", ".") + ".lean_algo.rules": set(
        "decimal number target_quantity fill_price fee funding_amount delisting_price order_segments effective_target milliseconds next_open decision_due exposure liquidity score_end_price positions_at funding_price funding_schedule merge_windows select_grid_point data_view R8Hypothesis apply_fill".split()),
    ENGINE_ROOT.replace("/", ".") + ".lean_algo.framework": {"R8Hypothesis"},
}


def sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def check_algorithm(source):
    """靜態限制降低資訊外洩；不宣稱 Python 同程序隔離。"""
    tree = ast.parse(source)
    allowed_modules = set(ALGORITHM_MEMBERS)
    parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
    imports, random_classes, class_names = {}, set(), set()
    denied_names = {"open", "exec", "eval", "compile", "__import__", "getattr", "setattr",
                    "delattr", "globals", "locals", "vars", "dir", "type", "object",
                    "input", "breakpoint", "help", "memoryview"}
    denied_attributes = set("format format_map gi_frame gi_code gi_yieldfrom cr_frame cr_await cr_code ag_frame ag_code f_back f_locals f_globals f_builtins f_code tb_frame tb_next".split())
    order_names = {"order", "marketorder", "limitorder", "stopmarketorder", "stoplimitorder",
                   "setholdings", "liquidate", "buy", "sell", "calculateorderquantity"}
    for node in tree.body:
        if not isinstance(node, (ast.Import, ast.ImportFrom, ast.ClassDef, ast.FunctionDef,
                                 ast.AsyncFunctionDef)) and not (
                isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str)):
            raise ValueError("禁止模組層級狀態或可執行敘述")
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            defaults = node.args.defaults + [v for v in node.args.kw_defaults if v is not None]
            if any(isinstance(child, (ast.List, ast.Dict, ast.Set, ast.Call,
                                      ast.ListComp, ast.DictComp, ast.SetComp, ast.GeneratorExp))
                   for value in defaults for child in ast.walk(value)):
                raise ValueError("禁止可變或呼叫式預設參數")
        if isinstance(node, ast.ClassDef):
            class_names.add(node.name)
            if node.decorator_list:
                raise ValueError("禁止類別裝飾器")
            for child in node.body:
                if not isinstance(child, (ast.FunctionDef, ast.Pass)) and not (
                        isinstance(child, ast.Expr) and isinstance(child.value, ast.Constant)
                        and isinstance(child.value.value, str)):
                    raise ValueError("禁止類別屬性")
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            if isinstance(node, ast.ImportFrom):
                if node.level or node.module not in allowed_modules:
                    raise ValueError("不允許的匯入")
                for alias in node.names:
                    if alias.name not in ALGORITHM_MEMBERS[node.module]:
                        raise ValueError("不允許的匯入名稱")
                    if node.module.endswith(".framework") and alias.name != "R8Hypothesis":
                        raise ValueError("只可匯入假說介面")
                    if node.module == "random":
                        if alias.name != "Random":
                            raise ValueError("禁止 random 模組層級亂數")
                        random_classes.add(alias.asname or alias.name)
            else:
                for alias in node.names:
                    if alias.name not in allowed_modules or alias.name.endswith(".framework"):
                        raise ValueError("不允許的匯入")
                    if "." in alias.name and not alias.asname:
                        raise ValueError("規則模組須使用明確別名")
                    imports[alias.asname or alias.name.split(".")[0]] = alias.name
        if isinstance(node, (ast.Global, ast.Nonlocal)):
            raise ValueError("禁止 global/nonlocal")
        if isinstance(node, ast.Attribute):
            if node.attr in denied_attributes or node.attr.startswith("_") or node.attr.replace("_", "").lower() in order_names:
                raise ValueError("禁止底線屬性或下單介面")
            if isinstance(node.ctx, (ast.Store, ast.Del)) and not (
                    isinstance(node.value, ast.Name) and node.value.id == "self"):
                raise ValueError("禁止非實例屬性賦值")
        if isinstance(node, ast.Name) and (
                node.id in denied_names or node.id.startswith("__")):
            raise ValueError("禁止動態存取或檔案操作")
        if isinstance(node, ast.Name) and node.id in imports:
            parent = parents.get(node)
            if not (isinstance(parent, ast.Attribute) and parent.value is node
                    and parent.attr in ALGORITHM_MEMBERS[imports[node.id]]):
                raise ValueError("禁止模組轉匯入或別名轉移")
            if imports[node.id] == "random":
                call = parents.get(parent)
                if not isinstance(call, ast.Call) or call.func is not parent:
                    raise ValueError("亂數建構函式不可轉交")
        if isinstance(node, ast.Name) and node.id in random_classes:
            parent = parents.get(node)
            if not isinstance(parent, ast.Call) or parent.func is not node:
                raise ValueError("亂數建構函式不可轉交")
        if isinstance(node, ast.Call):
            func = node.func
            random_call = isinstance(func, ast.Name) and func.id in random_classes
            if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name) and imports.get(func.value.id) == "random":
                if func.attr != "Random":
                    raise ValueError("禁止 random 模組層級亂數")
                random_call = True
            if random_call and not (
                    len(node.args) == 1 and not node.keywords
                    and isinstance(node.args[0], ast.Attribute)
                    and isinstance(node.args[0].value, ast.Name)
                    and node.args[0].value.id == "self" and node.args[0].attr == "random_seed"):
                raise ValueError("亂數只可用 random.Random(self.random_seed)")
    return tree


def merge_properties(base, overlay):
    """同 market/symbol/type 替換，保留映像中其他市場與表頭。"""
    additions = {}
    for row in csv.reader(io.StringIO(overlay.decode("utf-8"))):
        if len(row) != 11 or row[0] != "bybit" or row[2] != "cryptofuture":
            raise ValueError("屬性覆蓋列不合法")
        key = tuple(row[:3])
        if key in additions:
            raise ValueError("重複屬性鍵")
        additions[key] = row
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    emitted = set()
    for line in base.decode("utf-8").splitlines():
        row = next(csv.reader([line]))
        key = tuple(row[:3])
        if key in additions:
            if key not in emitted:
                writer.writerow(additions[key])
                emitted.add(key)
        else:
            output.write(line + "\n")
    for key in sorted(additions):
        if key not in emitted:
            writer.writerow(additions[key])
    return output.getvalue().encode("utf-8")


def safe_file(root, relative):
    rel = PurePosixPath(relative)
    if not relative or rel.is_absolute() or any(p in ("", ".", "..") for p in relative.split("/")):
        raise ValueError("檔案路徑不合法")
    root = Path(root).resolve()
    path = root
    for part in rel.parts:
        path = path / part
        if path.is_symlink():
            raise ValueError("拒絕符號連結")
    if not path.is_file() or not path.resolve().is_relative_to(root):
        raise ValueError("檔案不存在或越界")
    return path


def read_materialization(directory, expected):
    root = Path(directory).resolve()
    raw = safe_file(root, "materialization.json").read_bytes()
    if sha256(raw) != expected:
        raise ValueError("物化 manifest 雜湊不符")
    value = json.loads(raw)
    if canonical(value) != raw or value["schema_version"] != "r8_materialization_v1":
        raise ValueError("物化 schema 或標準化 JSON 不符")
    for prefix in ("lean", "custom"):
        expected_files = {p for p in value["files"] if p.startswith(prefix + "/")}
        actual = {p.relative_to(root).as_posix() for p in (root / prefix).rglob("*")
                  if p.is_file() or p.is_symlink()}
        if actual != expected_files:
            raise ValueError("掛載檔案清單不符")
        for relative in sorted(actual):
            if sha256(safe_file(root, relative).read_bytes()) != value["files"][relative]["sha256"]:
                raise ValueError("物化檔案雜湊不符: " + relative)
    overlay = safe_file(root, "symbol_properties_overlay.csv").read_bytes()
    if sha256(overlay) != value["symbol_properties_overlay_sha256"]:
        raise ValueError("合約屬性雜湊不符")
    return value


def normalized_window(window):
    if set(window) != {"start", "end"}:
        raise ValueError("視窗欄位不符")
    result = {k: rules.milliseconds(v) for k, v in window.items()}
    if result["start"] >= result["end"]:
        raise ValueError("視窗必須非空")
    return result


def algorithm_config(config):
    return canonical({k: v for k, v in config.items() if k != "mode"})


def serialize_model(artifact):
    """序列化集中於主機端；純規則不依賴帳本，canonical 仍只有一份。"""
    if not isinstance(artifact, dict) or set(artifact) != {"params", "model"}:
        raise ValueError("模型須含 params 與 model")
    raw = canonical(artifact)
    return raw, sha256(raw)


def deserialize_model(raw, expected_sha256):
    if sha256(raw) != expected_sha256:
        raise ValueError("模型雜湊不符")
    value = json.loads(raw)
    if serialize_model(value)[0] != raw:
        raise ValueError("模型非標準化 JSON")
    return value


def trial_lookup(ledger_directory):
    """先確認已有帳本，避免 ResearchLedger 建構函式建立新帳。"""
    root = Path(ledger_directory)
    if not root.is_dir() or not (root / "ledger_id.json").is_file():
        raise ValueError("帳本必須已存在")
    ledger = ResearchLedger(root)
    return ledger.trial_record


def validate_config(config, materialization, query=None):
    required = {"trial_id", "materialization_sha256", "code_commit", "engine_commit", "symbols",
                "initial_cash", "leverage", "gross_exposure_cap", "decision_resolution",
                "sharpe_frequency_seconds", "warmup", "score_windows", "folds", "model_artifact",
                "random_seed", "strategy", "algorithm", "mode", "cost"}
    if not required <= set(config) or set(config) - required - {"fit_window"}:
        raise ValueError("run_config 欄位不符")
    if type(config["random_seed"]) is not int:
        raise ValueError("random_seed 須為整數")
    for key in ("code_commit", "engine_commit"):
        if not isinstance(config[key], str) or not re.fullmatch("[0-9a-f]{40}", config[key]):
            raise ValueError("須為完整 commit")
    if (rules.decimal(config["initial_cash"]) <= 0 or rules.decimal(config["leverage"]) <= 0
            or not 0 < rules.decimal(config["gross_exposure_cap"]) <= 1):
        raise ValueError("資金、槓桿或曝險上限不合法")
    rules.decision_due(config["decision_resolution"], 0)
    if type(config["sharpe_frequency_seconds"]) is not int or config["sharpe_frequency_seconds"] <= 0:
        raise ValueError("頻率須為正整數")
    if config["symbols"] != materialization["strategy_symbols"] or len(set(config["symbols"])) != len(config["symbols"]):
        raise ValueError("標的清單不符")
    if config["warmup"] != materialization["warmup"]:
        raise ValueError("暖機不符")
    score_windows = [normalized_window(w) for w in config["score_windows"]]
    expected_windows = ([normalized_window(materialization["window"])]
                        if config["mode"] == "validation" and not config["folds"] else
                        [normalized_window(f["score_window"]) for f in config["folds"]])
    if score_windows != expected_windows:
        raise ValueError("score_windows 與摺表不符")
    rules.merge_windows(score_windows)
    window = normalized_window(materialization["window"])
    for fold in config["folds"]:
        fit, score = normalized_window(fold["fit_window"]), normalized_window(fold["score_window"])
        if not window["start"] <= fit["start"] < fit["end"] <= score["start"] < score["end"] <= window["end"]:
            raise ValueError("摺表越出物化視窗")
    mode = config["mode"]
    if mode == "trial" and PurePosixPath(config["algorithm"]["path"]).is_relative_to(ENGINE_ROOT):
        raise ValueError("trial 假說不得位於引擎目錄")
    if config["model_artifact"] is not None and (config["folds"] or mode != "validation"):
        # 本版尚未啟用 holdout；外部模型只供無摺表的構造評分檢查。
        raise ValueError("外部模型不得跳過樣本外或擬合執行")
    if mode == "validation":
        if config["trial_id"] is not None or config["algorithm"] != {"path": EXAMPLE, "class": "FixedSchedule"}:
            raise ValueError("validation 只允許固定範例且 trial_id 為 null")
        if config["engine_commit"] != config["code_commit"]:
            raise ValueError("驗證 engine_commit 須等於 code_commit")
        return
    if mode not in ("trial", "verification"):
        raise ValueError("未知 mode")
    if materialization["purpose"] != "research":
        raise ValueError("purpose 必須為 research")
    if query is None or not config["trial_id"]:
        raise ValueError("缺少試驗查詢")
    found = query(config["trial_id"])
    if not isinstance(found, dict) or not isinstance(found.get("record"), dict) or type(found.get("finished")) is not bool:
        raise ValueError("查無已開始的試驗紀錄")
    if found["finished"] != (mode == "verification"):
        raise ValueError("試驗結束狀態不符")
    trial = found["record"]
    for key in ("trial_id", "code_commit", "random_seed"):
        if trial.get(key) != config[key]:
            raise ValueError("試驗身份不符: " + key)
    for key, expected in rules.RUNTIME_METADATA.items():
        if trial.get(key) != expected:
            raise ValueError("執行環境身份不符: " + key)
    run_keys = ("initial_cash", "leverage", "gross_exposure_cap", "decision_resolution",
                "sharpe_frequency_seconds", "algorithm", "engine_commit")
    expected_configuration = {
        "strategy_parameters": {"run": {k: config[k] for k in run_keys}, "strategy": config["strategy"]},
        "cost_model_parameters": config["cost"],
    }
    if trial.get("configuration") != expected_configuration or trial.get("configuration_sha256") != sha256(canonical(expected_configuration)):
        raise ValueError("設定身份不符")
    if (trial.get("manifest_sha256") != config["materialization_sha256"]
            or trial.get("data_files") != {p: f["sha256"] for p, f in materialization["files"].items()}
            or trial.get("hypothesis_id") != materialization["hypothesis_id"]
            or trial.get("generation") != materialization["generation"]
            or trial.get("random_seed") != config["random_seed"]
            or trial.get("sharpe_frequency", {}).get("seconds") != config["sharpe_frequency_seconds"]):
        raise ValueError("物化或試驗身份不符")
    if trial.get("evaluation_kind") == "holdout_falsification":
        raise ValueError("本版尚未啟用 holdout")
    if normalized_window(trial["data_window"]) != window or trial.get("folds", []) != config["folds"]:
        raise ValueError("試驗視窗或摺表不符")
    if config["folds"]:
        expected_score = {"start": score_windows[0]["start"], "end": score_windows[-1]["end"]}
        if normalized_window(trial["score_window"]) != expected_score:
            raise ValueError("試驗評分窗不符")
    elif "fit_window" not in config or normalized_window(config["fit_window"]) != normalized_window(trial["fit_window"]):
        raise ValueError("試驗擬合窗不符")


def git_bytes(repo, *args):
    try:
        return subprocess.check_output(
            ["git", "--no-replace-objects", "-C", str(repo), *args],
            stderr=subprocess.PIPE)
    except subprocess.CalledProcessError as exc:
        raise ValueError("Git 來源核對失敗") from exc


def tree_files(repo, commit, paths):
    result = {}
    for record in git_bytes(repo, "ls-tree", "-r", "-z", commit, "--", *paths).split(b"\0"):
        if not record:
            continue
        meta, name = record.split(b"\t", 1)
        mode, kind, blob = meta.split()
        if kind != b"blob" or mode not in (b"100644", b"100755"):
            raise ValueError("來源只能是一般檔案")
        result[name.decode("utf-8")] = git_bytes(repo, "cat-file", "blob", blob.decode("ascii"))
    return result


def verify_source(repo, config):
    repo = Path(repo).resolve()
    roots = [ENGINE_ROOT, LEDGER_ROOT]
    entry = config["algorithm"]["path"]
    safe_file(repo, entry)
    files = tree_files(repo, config["code_commit"], roots + [entry])
    if entry not in files or FRAMEWORK not in files:
        raise ValueError("來源 commit 缺演算法")
    if git_bytes(repo, "status", "--porcelain", "--untracked-files=all", "--", *roots, entry).strip():
        raise ValueError("來源存在未提交改動")
    for name, raw in files.items():
        if safe_file(repo, name).read_bytes() != raw:
            raise ValueError("來源與 code_commit 不符: " + name)
    if config["mode"] != "validation":
        engine = tree_files(repo, config["engine_commit"], roots)
        code_engine = {p: raw for p, raw in files.items()
                       if p.startswith((ENGINE_ROOT + "/", LEDGER_ROOT + "/"))}
        if engine != code_engine:
            raise ValueError("引擎檔案清單或內容不符")
        result = subprocess.run(
            ["git", "--no-replace-objects", "-C", str(repo), "merge-base", "--is-ancestor",
             config["engine_commit"], "origin/main"], capture_output=True)
        if result.returncode != 0:
            raise ValueError("engine_commit 不是 origin/main 祖先")
    return {p: sha256(raw) for p, raw in files.items()}


def outside_repository(path, repo):
    path = Path(path).resolve()
    if path.is_relative_to(Path(repo).resolve()) or any((p / ".git").exists() for p in (path, *path.parents)):
        raise ValueError("輸出目錄不得在倉庫內")
    return path


def write_identical(path, raw):
    """確定性的輸入快照；既有內容不符時拒絕覆寫。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as f:
            f.write(raw)
    except FileExistsError:
        if path.is_symlink() or path.read_bytes() != raw:
            raise ValueError("輸入快照已有不同內容")


def mount(source, destination, readonly=True):
    source = str(Path(source).resolve())
    if "," in source or "\n" in source:
        raise ValueError("掛載路徑不合法")
    return ["--mount", "type=bind,src=" + source + ",dst=" + destination + (",readonly" if readonly else "")]


LAUNCH_SCRIPT = """set -eu
cd /Lean/Launcher/bin/Debug
python3 - <<'PY'
from pathlib import Path
p = Path('config.json')
s = p.read_text()
import re
for key, value in [('algorithm-type-name', 'R8Algorithm'), ('algorithm-language', 'Python'), ('algorithm-location', '/r8/src/program_code/research/r8_engine/lean_algo/framework.py')]:
    s, n = re.subn(r'(^[ \t]*"' + key + r'"\\s*:\\s*")[^"]*(")', lambda m: m[1] + value + m[2], s, flags=re.MULTILINE)
    if n != 1:
        raise RuntimeError('launcher key mismatch: ' + key)
s, n = re.subn(r'^[ \t]*"environment"\\s*:\\s*"[^"]*"\\s*,', '"environment": "backtesting", "close-automatically": true,', s, flags=re.MULTILINE)
if n != 1:
    raise RuntimeError('launcher environment mismatch')
p.write_text(s)
PY
exec dotnet QuantConnect.Lean.Launcher.dll
"""


def assemble_run(config, hashes, argv, base_hash, started, ended, exit_code, log, events):
    """只由受控執行原始紀錄組裝 §7.2；缺少正常結尾視為失敗。"""
    sections = ("steps", "decisions", "orders", "fills", "voided", "funding",
                "endpoint_funding", "fits", "fill_forward_bars")
    result = {k: [] for k in sections}
    residuals, finish = [], None
    for event in events:
        section, record = event["section"], event["record"]
        if section in result:
            result[section].append(record)
        elif section == "cash_residual":
            if rules.decimal(record["residual"]) != 0:
                residuals.append(record)
        elif section == "finished":
            if finish is not None:
                raise ValueError("重複結尾")
            finish = record
        else:
            raise ValueError("未知原始紀錄段")
    finish = finish or {"status": "failed", "failure_reason": "lean_error", "failure_t": None}
    if exit_code != 0:
        finish = {"status": "failed", "failure_reason": "lean_error", "failure_t": finish.get("failure_t")}
    if result["fill_forward_bars"]:
        finish = {"status": "failed", "failure_reason": "fill_forward_bar",
                  "failure_t": result["fill_forward_bars"][0]["t"]}
    if residuals and finish["status"] == "completed":
        finish = {"status": "failed", "failure_reason": "lean_error", "failure_t": residuals[0]["t"]}
    if finish["status"] not in ("completed", "failed") or finish["failure_reason"] not in (
            None, "fill_forward_bar", "gross_exposure_cap", "invalid_decision", "algorithm_exception", "lean_error"):
        raise ValueError("執行結尾不合法")
    sort_keys = {"orders": ("order_id", "_leg_index"), "voided": ("order_id",),
                 "fills": ("change_t", "order_id", "_leg_index"),
                 "funding": ("t", "symbol"), "endpoint_funding": ("t", "symbol"),
                 "decisions": ("t",), "steps": ("t",), "fits": ("fold",)}
    for section, keys in sort_keys.items():
        ordered = sorted(result[section], key=lambda r: tuple(r.get(k, 0) for k in keys))
        result[section] = [{k: v for k, v in row.items() if k != "_leg_index"} for row in ordered]
    result.update({
        "schema_version": "r8_lean_run_v1", "materialization_sha256": config["materialization_sha256"],
        "run_config_sha256": sha256(canonical(config)), "run_config": config,
        "image_digest": rules.IMAGE_DIGEST, "docker_argv": argv,
        "algorithm_config_sha256": sha256(algorithm_config(config)), "algorithm_files": hashes,
        "base_symbol_properties_sha256": base_hash, "started_at": started, "ended_at": ended,
        "exit_code": exit_code, "lean_log_sha256": sha256(log), "mode": config["mode"],
        "status": finish["status"], "failure_reason": finish["failure_reason"], "failure_t": finish["failure_t"],
        "unexplained_cash_residual": {"per_step": residuals, "total": rules.number(
            sum((rules.decimal(r["residual"]) for r in residuals), rules.decimal("0")))},
    })
    return result


def execute(config, materialization, out, *, repo, query=None, ledger=None,
            process=subprocess.run, model_root=None):
    """process 是 docker 邊界；測試注入假函式，絕不啟動容器。"""
    repo = Path(repo).resolve()
    out = outside_repository(out, repo)
    if out.exists():
        raise ValueError("輸出目錄必須不存在")
    materialization = Path(materialization).resolve()
    manifest = read_materialization(materialization, config["materialization_sha256"])
    if config["mode"] != "validation" and query is None:
        query = trial_lookup(ledger)
    validate_config(config, manifest, query)
    hashes = verify_source(repo, config)
    check_algorithm(safe_file(repo, config["algorithm"]["path"]).read_text())
    # 使用提交中的快照，避免核對後來源被其他程序改動。
    sources = tree_files(repo, config["code_commit"], [ENGINE_ROOT, LEDGER_ROOT, config["algorithm"]["path"]])
    info = {k: manifest[k] for k in ("symbols", "strategy_symbols", "first_bar", "delistings",
                                    "min_notional", "funding_interval_ms", "window", "warmup")}
    info["properties"] = {}
    overlay = safe_file(materialization, "symbol_properties_overlay.csv").read_bytes()
    for row in csv.reader(io.StringIO(overlay.decode())):
        info["properties"][row[1]] = {"qty_step": row[7], "min_qty": row[9]}
    # 例外只由固定範例與 null trial_id 推出，不把 mode 傳進容器。
    info["validation_example"] = config["trial_id"] is None and config["algorithm"]["path"] == EXAMPLE
    snapshot_key = sha256(algorithm_config(config) + canonical(info))
    prepared = Path(tempfile.gettempdir()) / "r8-lean-inputs" / snapshot_key
    write_identical(prepared / "algorithm_config.json", algorithm_config(config))
    write_identical(prepared / "framework.json", canonical(info))
    for name, raw in sources.items():
        write_identical(prepared / "src" / name, raw)
    if config["model_artifact"] is not None:
        model = config["model_artifact"]
        raw = safe_file(model_root or repo, model["path"]).read_bytes()
        deserialize_model(raw, model["sha256"])
        write_identical(prepared / "models" / model["path"], raw)
    out.mkdir(parents=True)
    started = rules.milliseconds(datetime.now(timezone.utc))
    base_argv = ["docker", "run", "--rm", "--network", "none", "--entrypoint", "cat",
                 IMAGE, "/Lean/Data/symbol-properties/symbol-properties-database.csv"]
    base = process(base_argv, capture_output=True, check=False)
    if base.returncode:
        raise ValueError("無法讀取固定映像屬性表")
    write_identical(prepared / "symbol-properties.csv", merge_properties(base.stdout, overlay))
    argv = ["docker", "run", "--rm", "--network", "none"]
    for source, destination, readonly in (
        (materialization / "lean/cryptofuture/bybit/hour", "/Lean/Data/cryptofuture/bybit/hour", True),
        (materialization / "custom", "/r8/custom", True),
        (prepared / "src", "/r8/src", True),
        (prepared / "algorithm_config.json", "/r8/algorithm_config.json", True),
        (prepared / "framework.json", "/r8/framework.json", True),
        (prepared / "symbol-properties.csv", "/Lean/Data/symbol-properties/symbol-properties-database.csv", True),
        (out, "/r8/output", False),
    ):
        argv += mount(source, destination, readonly)
    if config["model_artifact"] is not None:
        argv += mount(prepared / "models", "/r8/models")
    argv += ["--env", "PYTHONPATH=/r8/src", "--entrypoint", "/bin/bash", IMAGE, "-c", LAUNCH_SCRIPT]
    completed = process(argv, capture_output=True, check=False)
    log = completed.stdout + completed.stderr
    (out / "lean.log").write_bytes(log)
    raw_events = (out / "events.jsonl").read_bytes() if (out / "events.jsonl").is_file() else b""
    try:
        events = [json.loads(line) for line in raw_events.splitlines() if line.strip()]
    except (ValueError, UnicodeError):
        events = [{"section": "finished", "record": {"status": "failed", "failure_reason": "lean_error", "failure_t": None}}]
    result = assemble_run(config, hashes, argv, sha256(base.stdout), started,
                          rules.milliseconds(datetime.now(timezone.utc)), completed.returncode, log, events)
    (out / "run.json").write_bytes(canonical(result))
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument("--materialization", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--ledger")
    parser.add_argument("--model-root")
    args = parser.parse_args(argv)
    config = json.loads(Path(args.config).read_bytes())
    result = execute(config, args.materialization, args.out, repo=Path(__file__).resolve().parents[3],
                     ledger=args.ledger, model_root=args.model_root)
    return 0 if result["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
