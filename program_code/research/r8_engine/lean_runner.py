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
    verified = any(p.startswith("verification/") for p in value["files"])
    for prefix in (("lean", "custom", "source", "verification") if verified else ("lean", "custom")):
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


def verification_json(raw, *, lines=False):
    """The new evidence wire format is canonical JSON plus exactly one LF."""
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("VERIFICATION_DUPLICATE_KEY")
            result[key] = value
        return result
    def one(line):
        value = json.loads(line, object_pairs_hook=pairs,
                           parse_constant=lambda _: (_ for _ in ()).throw(ValueError("VERIFICATION_NUMBER")))
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode() + b"\n"
        if encoded != line:
            raise ValueError("VERIFICATION_ENCODING")
        return value
    return [one(line) for line in raw.splitlines(keepends=True)] if lines else one(raw)


def verification_keys(value, keys, schema=None):
    if not isinstance(value, dict) or set(value) != set(keys.split()) or (
            schema is not None and value['schema_version'] != schema):
        raise ValueError("VERIFICATION_SCHEMA")


def verification_refs(refs):
    if not isinstance(refs, list):
        raise ValueError("VERIFICATION_SOURCE_REF")
    order = []
    for ref in refs:
        verification_keys(ref, 'kind relative_path url sha256 row request_id list_index byte_start byte_end trade_id line_sha256')
        if ref['kind'] not in ('raw','csv','trade','instruments','policy','plan','report'):
            raise ValueError("VERIFICATION_SOURCE_REF")
        for key in ('row','list_index','byte_start','byte_end'):
            if ref[key] is not None and (type(ref[key]) is not int or ref[key] < (1 if key == 'row' else 0)):
                raise ValueError("VERIFICATION_SOURCE_REF")
        for key in ('sha256','line_sha256'):
            if ref[key] is not None and not re.fullmatch('[0-9a-f]{64}', str(ref[key])):
                raise ValueError("VERIFICATION_SOURCE_REF")
        path = ref['relative_path']
        if path is not None and (not isinstance(path,str) or PurePosixPath(path).is_absolute()
                or any(p in ('','.','..') for p in path.split('/')) or ref['sha256'] is None):
            raise ValueError("VERIFICATION_SOURCE_REF")
        order.append((ref['kind'],path or '',ref['row'] or -1,
                      ref['list_index'] if ref['list_index'] is not None else -1,
                      ref['byte_start'] if ref['byte_start'] is not None else -1))
    if order != sorted(order):
        raise ValueError("VERIFICATION_SOURCE_REF_ORDER")


def verification_bundle(root, manifest):
    """Validate framework inputs, keeping all evidence out of hypothesis parameters."""
    files = manifest['files']
    def raw(name):
        if name not in files:
            raise ValueError('VERIFICATION_MISSING: ' + name)
        result = safe_file(root,name).read_bytes()
        meta = files[name]
        verification_keys(meta, 'sha256 rows first last source_file source_sha256')
        if sha256(result) != meta['sha256']:
            raise ValueError('VERIFICATION_HASH: ' + name)
        if type(meta['rows']) is not int or meta['rows'] < 0:
            raise ValueError('VERIFICATION_METADATA')
        if name.endswith('.json'):
            count, times = 1, []
        elif name.endswith('.jsonl'):
            objects = verification_json(result, lines=True)
            count = len(objects)
            times = [r.get('known_at',r.get('timestamp')) for r in objects
                     if r.get('known_at',r.get('timestamp')) is not None]
        elif name.startswith('custom/turnover_'):
            records = list(csv.reader(io.StringIO(result.decode('utf-8'))))
            count = len(records)
            times = [int(r[1]) for r in records]
        else:
            records = list(csv.reader(io.StringIO(result.decode('utf-8'))))
            count = max(0, len(records)-1)
            times = [int(r[0]) for r in records[1:]]
        if (meta['rows'] != count or meta['first'] != (min(times) if times else None)
                or meta['last'] != (max(times) if times else None)):
            raise ValueError('VERIFICATION_METADATA')
        return result
    policy_raw = raw('verification/policy.json')
    policy = verification_json(policy_raw)
    v2 = policy.get('schema_version') == 'r8_data_verification_policy_v2'
    verification_keys(policy, 'schema_version standard_sha256 approval_event p3b_manifest_sha256 listing sampling turnover l4_price_threshold_pct'
                      + (' volume_semantics_policy' if v2 else ''), 'r8_data_verification_policy_v2' if v2 else 'r8_data_verification_policy_v1')
    if (policy['approval_event'] != ('RH-20261022-05' if v2 else 'RH-20261022-04')
            or v2 and policy['volume_semantics_policy'] != 'v2-terminal-suffix-20261022'
            or not re.fullmatch('[0-9a-f]{64}', str(policy['standard_sha256']))
            or policy['p3b_manifest_sha256'] != manifest['u1_manifest_sha256']
            or policy['listing'] != dict(x_pct='50',y_pct='20',z_pct='20',cooling_days=7,
                quantity='hourly_base_volume_daily_mean',variation='mean_relative_difference',stage_end_ranges=[[1,3],[7,15],[15,30]])
            or policy['sampling'] != dict(seed=20261022,base_per_stratum=300,max_per_stratum=900,
                max_expansions=1,confidence='0.95',upper_limit='0.025')
            or policy['turnover'] != dict(window_days=12,thresholds=['1000000','10000000','100000000'],
                trigger_pct='5',general='exchange_reported',suspect='sum_hourly_reported')
            or policy['l4_price_threshold_pct'] != '1'
            or type(policy['listing']['cooling_days']) is not int
            or any(type(v) is not int for pair in policy['listing']['stage_end_ranges'] for v in pair)
            or any(type(policy['sampling'][k]) is not int for k in
                   ('seed','base_per_stratum','max_per_stratum','max_expansions'))
            or type(policy['turnover']['window_days']) is not int):
        raise ValueError('VERIFICATION_POLICY')
    digest = sha256(policy_raw)
    evidence = verification_json(raw('verification/verification.json'))
    verification_keys(evidence, 'schema_version status policy_sha256 p3b_manifest_sha256 sample_plan_sha256 previous_corrections_sha256 review_refs tool_commit readable counts files reason_codes'
                      + (' standard_sha256 volume_semantics_policy' if v2 else ''),
                      'r8_data_verification_v2' if v2 else 'r8_data_verification_v1')
    if (evidence['status'] != 'READY' or evidence['policy_sha256'] != digest
            or evidence['p3b_manifest_sha256'] != manifest['u1_manifest_sha256']
            or v2 and (evidence['standard_sha256'] != policy['standard_sha256']
                or evidence['volume_semantics_policy'] != policy['volume_semantics_policy'])):
        raise ValueError('VERIFICATION_IDENTITY')
    verification_refs(evidence['review_refs'])
    if v2:
        volume = raw('verification/volume_semantics.jsonl')
        if evidence['files'].get('volume_semantics.jsonl') != {
                'sha256': sha256(volume), 'rows': len(volume.splitlines())}:
            raise ValueError('VERIFICATION_VOLUME_IDENTITY')
    binding = verification_json(raw('verification/hypothesis_binding.json'))
    verification_keys(binding,'schema_version hypothesis_id policy_sha256 family registration_sha256','r8_verification_hypothesis_binding_v1')
    if (binding['hypothesis_id'] != manifest['hypothesis_id'] or binding['policy_sha256'] != digest
            or binding['family'] not in ('ordinary','listing')
            or not re.fullmatch('[0-9a-f]{64}',str(binding['registration_sha256']))):
        raise ValueError('HYPOTHESIS_BINDING_INVALID')
    listing = verification_json(raw('verification/listing_regimes.jsonl'),lines=True)
    grouped = {s: [] for s in manifest['symbols']}
    previous = None
    for row in listing:
        verification_keys(row,'schema_version symbol day_start known_at observed_listing_at launch_time listing_time_mismatch origin_refs stage reason_code cooling quantity_inputs policy_sha256','r8_listing_regime_v1')
        if (row['symbol'] not in grouped or row['policy_sha256'] != digest
                or any(type(row[k]) is not int for k in ('day_start','known_at','observed_listing_at'))
                or row['day_start'] % rules.DAY or row['observed_listing_at'] % rules.HOUR
                or row['stage'] not in ('initial','middle','stabilizing','ordinary')
                or row['cooling'] is not None and type(row['cooling']) is not bool
                or type(row['listing_time_mismatch']) is not bool
                or row['launch_time'] is not None and type(row['launch_time']) is not int
                or not isinstance(row['reason_code'],str) or not row['reason_code']):
            raise ValueError('LISTING_REGIME_INVALID')
        key = (row['known_at'],row['symbol'])
        if previous is not None and key <= previous:
            raise ValueError('LISTING_REGIME_ORDER')
        previous = key
        known = row['observed_listing_at'] + rules.HOUR if not grouped[row['symbol']] else row['day_start']
        if row['known_at'] != known or row['day_start'] > row['known_at']:
            raise ValueError('LISTING_KNOWN_AT')
        earlier = grouped[row['symbol']]
        stage_index = ('initial','middle','stabilizing','ordinary').index(row['stage'])
        age = (row['day_start']-row['observed_listing_at']//rules.DAY*rules.DAY)//rules.DAY+1
        # A first box closing at midnight is represented by its complete daily
        # update, with unchanged known_at and all origin evidence retained.
        initial_age = 2 if (row['observed_listing_at'] % rules.DAY == rules.DAY-rules.HOUR
                           and row['day_start'] == row['known_at'] == row['observed_listing_at']+rules.HOUR) else 1
        if (not earlier and (row['stage'] != 'initial' or age != initial_age)
                or not (1,2,8,16)[stage_index] <= age
                or stage_index < 3 and age > (3,15,30)[stage_index]):
            raise ValueError('LISTING_STAGE_BOUNDARY')
        if earlier:
            prev = earlier[-1]
            previous_stage = ('initial','middle','stabilizing','ordinary').index(prev['stage'])
            if (stage_index not in (previous_stage,previous_stage+1)
                    or row['day_start'] != prev['day_start']+rules.DAY
                    or any(row[k] != prev[k] for k in ('observed_listing_at','launch_time','listing_time_mismatch'))):
                raise ValueError('LISTING_STAGE_ORDER')
        if row['launch_time'] is not None and row['listing_time_mismatch'] != (abs(row['observed_listing_at']-row['launch_time']) > rules.DAY):
            raise ValueError('LISTING_TIME_MISMATCH')
        verification_refs(row['origin_refs'])
        if not isinstance(row['quantity_inputs'],list):
            raise ValueError('LISTING_QUANTITY')
        last_day = None
        for q in row['quantity_inputs']:
            verification_keys(q,'day_start volume_sum hour_count status source_refs')
            if (type(q['day_start']) is not int or q['day_start'] % rules.DAY
                    or q['day_start'] + rules.DAY > row['known_at']
                    or last_day is not None and q['day_start'] <= last_day
                    or type(q['hour_count']) is not int or not 1 <= q['hour_count'] <= 24
                    or q['status'] not in ('FULL','PARTIAL','MISSING')
                    or (q['volume_sum'] is None) != (q['status']=='MISSING')):
                raise ValueError('LISTING_QUANTITY')
            if q['volume_sum'] is not None and rules.decimal(q['volume_sum']) < 0:
                raise ValueError('LISTING_QUANTITY')
            verification_refs(q['source_refs']); last_day = q['day_start']
        grouped[row['symbol']].append(row)
    for symbol, rows in grouped.items():
        projection = raw('custom/listing_regime/'+symbol.lower()+'.csv')
        output = io.StringIO(); writer = csv.writer(output,lineterminator='\n')
        writer.writerow(['known_at','day_start','stage','reason_code','cooling','policy_sha256'])
        for row in rows:
            writer.writerow([row['known_at'],row['day_start'],row['stage'],row['reason_code'],
                             {True:'true',False:'false',None:'null'}[row['cooling']],digest])
        if projection != output.getvalue().encode():
            raise ValueError('LISTING_PROJECTION_MISMATCH')
        if manifest['first_bar'].get(symbol) is not None and not rows:
            raise ValueError('LISTING_ORIGIN_UNKNOWN')
    # Independently bind every 12-day input to manifest-bound, in-scope CSV bytes.
    from fractions import Fraction
    cache = {}
    def market(symbol, interval, original=False, field='turnover'):
        name = ('verification/original/' if original else 'source/') + 'kline_'+symbol+'_'+interval+'.csv'
        key = (name, field)
        if key not in cache:
            records = {}; reader = csv.DictReader(io.StringIO(raw(name).decode('utf-8')))
            if reader.fieldnames != ['timestamp','open','high','low','close','volume','turnover']:
                raise ValueError('TURNOVER_SOURCE_SCHEMA')
            previous_t = None
            for item in reader:
                stamp = int(item['timestamp'])
                if (stamp % (rules.DAY if interval=='D' else rules.HOUR)
                        or previous_t is not None and (stamp < previous_t or stamp == previous_t and not original)):
                    raise ValueError('TURNOVER_SOURCE_ORDER')
                if not rules.milliseconds(manifest['warmup']['start']) <= stamp < rules.milliseconds(manifest['window']['end']):
                    raise ValueError('TURNOVER_SOURCE_OUT_OF_SCOPE')
                try:
                    value = rules.decimal(item[field])
                    if value < 0:
                        raise ValueError('TURNOVER_SOURCE_AMOUNT')
                    value = Fraction(value)
                except ValueError:
                    if not original:
                        raise
                    value = None  # Invalid original evidence is not a usable amount.
                records[stamp] = None if original and stamp in records else value
                previous_t = stamp
            cache[key] = records
        return cache[key]
    origins = {}
    for symbol in manifest['symbols']:
        for stamp, volume in market(symbol, '60', True, 'volume').items():
            if volume is None:
                raise ValueError('TURNOVER_ORIGIN_UNKNOWN')
            if volume > 0:
                origins[symbol] = stamp
                break
        if symbol not in origins:
            raise ValueError('TURNOVER_ORIGIN_UNKNOWN')
    table = verification_json(raw('verification/turnover_decisions.jsonl'),lines=True)
    if not table and any(t is not None for t in manifest['first_bar'].values()):
        raise ValueError('TURNOVER_INPUT_INCOMPLETE')
    previous = None
    for row in table:
        symbol = row.get('symbol')
        if symbol not in grouped or row.get('policy_sha256') != digest:
            raise ValueError('TURNOVER_IDENTITY')
        rules.turnover_liquidity(row,row['decision_utc_day'],manifest['first_bar'].get(symbol),{})
        key = (row['decision_utc_day'],symbol)
        if previous is not None and key <= previous:
            raise ValueError('TURNOVER_ORDER')
        previous = key
        for item in row['inputs']:
            verification_refs(item['source_refs'])
            day = item['day_start']
            for field, original in (('exchange_reported',True),('effective_reported',False)):
                value = market(symbol,'D',original).get(day)
                if day < origins[symbol]:
                    value = None  # The first observed UTC day may be incomplete.
                supplied = None if item[field] is None else Fraction(rules.decimal(item[field]))
                if value != supplied or field=='effective_reported' and ((value is not None) != (item['daily_status']=='VALID')):
                    raise ValueError('TURNOVER_SOURCE_MISMATCH')
            if item['hourly_status'] != 'NOT_EVALUATED':
                hours = market(symbol,'60')
                full = day >= origins[symbol] and all(day+i*rules.HOUR in hours for i in range(24))
                value = sum((hours[day+i*rules.HOUR] for i in range(24)),Fraction(0)) if full else None
                supplied = None if item['sum_hourly_reported'] is None else Fraction(rules.decimal(item['sum_hourly_reported']))
                if value != supplied or full != (item['hourly_status']=='VALID'):
                    raise ValueError('TURNOVER_SOURCE_MISMATCH')
    for symbol in manifest['symbols']:
        for interval, resolution, step in (('D','day',rules.DAY),('60','hour',rules.HOUR)):
            records = market(symbol, interval)
            content = raw('custom/turnover_'+resolution+'/'+symbol.lower()+'.csv')
            rows = list(csv.reader(io.StringIO(content.decode('utf-8'))))
            seen = {}
            for item in rows:
                if len(item) != 3:
                    raise ValueError('TURNOVER_CUSTOM_SCHEMA')
                known, stamp = int(item[0]), int(item[1])
                if known != stamp+step or stamp in seen:
                    raise ValueError('TURNOVER_CUSTOM_TIME')
                seen[stamp] = Fraction(rules.decimal(item[2]))
            if seen != records:
                raise ValueError('TURNOVER_CUSTOM_SOURCE_MISMATCH')
    return binding


def verification_inputs(root, manifest, config, query=None):
    present = any(p.startswith(('verification/','custom/listing_regime/')) for p in manifest['files'])
    if not present:
        # Old artifacts are readable for historical regression only, never a new trial.
        if config['mode'] == 'trial':
            raise ValueError('VERIFICATION_MISSING')
        return None
    binding = verification_bundle(root,manifest)
    if config['mode'] != 'validation':
        found = query(config['trial_id']) if query else None
        if not found or found['record'].get('preregistration_sha256') != binding['registration_sha256']:
            raise ValueError('HYPOTHESIS_BINDING_REGISTRATION_MISMATCH')
    return binding


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
    strategy = config["strategy"]
    if not isinstance(strategy, dict) or not {"grid", "neighborhood"} <= set(strategy):
        raise ValueError("strategy 缺少網格或鄰域")
    rules.validate_grid(strategy["grid"], strategy["neighborhood"])
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
    if residuals and finish["status"] == "completed":
        steps_by_t = {step["t"]: step for step in result["steps"]}
        last_step = result["steps"][-1] if result["steps"] else None
        for residual in sorted(residuals, key=lambda row: row["t"]):
            step = steps_by_t.get(residual["t"])
            # 結束殘差沒有新增 step；§16.2 指定沿用最後一步的框架現金。
            if step is None and last_step is not None and residual["t"] > last_step["t"]:
                step = last_step
            if step is not None:
                cash = rules.decimal(step["cash"])
                exponent = max(cash.adjusted() - 27, -28) if cash else -28
                ulp = rules.decimal(f"1e{exponent}")
                if rules.decimal(residual["residual"]).copy_abs() <= 100 * ulp:
                    continue
            # 缺少可核對的現金也不可把非零殘差解釋成表示誤差。
            finish = {"status": "failed", "failure_reason": "lean_error", "failure_t": residual["t"]}
            break
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
    binding = verification_inputs(materialization, manifest, config, query)
    hashes = verify_source(repo, config)
    check_algorithm(safe_file(repo, config["algorithm"]["path"]).read_text())
    # 使用提交中的快照，避免核對後來源被其他程序改動。
    sources = tree_files(repo, config["code_commit"], [ENGINE_ROOT, LEDGER_ROOT, config["algorithm"]["path"]])
    info = {k: manifest[k] for k in ("symbols", "strategy_symbols", "first_bar", "delistings",
                                    "min_notional", "funding_interval_ms", "window", "warmup")}
    if binding is not None:
        info["verification"] = {k: binding[k] for k in ("family", "policy_sha256")}
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
    if binding is not None:
        relative = "verification/turnover_decisions.jsonl"
        table = safe_file(materialization, relative).read_bytes()
        if sha256(table) != manifest["files"][relative]["sha256"]:
            raise ValueError("TURNOVER_HASH")
        write_identical(prepared / "framework-inputs/turnover_decisions.jsonl", table)
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
    if binding is not None:
        argv += mount(prepared / "framework-inputs", "/r8/framework-inputs")
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
