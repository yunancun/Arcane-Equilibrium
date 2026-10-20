"""U6：只使用構造資料，驗收值來自 P4 增補的固定案例。"""

import ast
import copy
import csv
import hashlib
import io
import json
import shutil
import socket
import subprocess
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

# 受控擷取移除 cwd 時仍以目前受審版本作絕對匯入。
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from program_code.research.r8_engine import series
from program_code.research.r8_ledger import ledger as ledger_module
from program_code.research.r8_ledger.ledger import canonical


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def deny(*args, **kwargs):
        raise AssertionError("離線測試禁止 socket 連線")

    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(socket.socket, "connect_ex", deny)
    monkeypatch.setattr(socket, "create_connection", deny)


def test_g1_target_quantity_fill_and_fee():
    quantity = series.target_quantity("100000", "0.5", "99.50", "0.1")
    assert series.decimal_text(quantity) == "502.5"
    price, fee = series.fill_cost(quantity, "100", "10", "0.00055")
    assert series.decimal_text(price) == "100.1"
    assert series.decimal_text(fee) == "27.6651375"


def test_g2_closing_sell():
    price, fee = series.fill_cost("-502.5", "101", "10", "0.00055")
    assert series.decimal_text(price) == "100.899"
    assert series.decimal_text(fee) == "27.885961125"


@pytest.mark.parametrize(
    "before,after,price,rate,expected",
    [
        pytest.param("502.5", "0", "101", "0.0001", "-5.176755", id="G3"),
        pytest.param("-502.5", "-502.5", "101", "0.0001", "4.973745", id="G4"),
        pytest.param("0", "502.5", "101", "0.0001", "-5.176755", id="G5"),
        pytest.param("502.5", "0", "1", "0.02", "-10.251", id="G6-positive"),
        pytest.param("502.5", "0", "1", "-0.02", "0", id="G6-negative"),
    ],
)
def test_g3_g6_funding_uses_adverse_position(before, after, price, rate, expected):
    amount = series.funding_amount(before, after, price, rate, "0.02")
    assert series.decimal_text(amount) == expected


def test_g7_delisting_uses_adverse_extreme():
    price, fee = series.delisting_cost(
        "502.5", {"low": "0.95", "high": "1.02"},
        {"low": "0.97", "high": "1.04"}, "60", "0.00055",
    )
    assert series.decimal_text(price) == "0.9443"
    assert series.decimal_text(fee) == "0.2609809125"


def cost_parameters():
    return {
        "taker_fee_rate": "0.00055", "stress_fee_rate": "0.00075",
        "slippage_tiers_bps": [
            {"min_turnover": "100000000", "bps": "5"},
            {"min_turnover": "10000000", "bps": "10"},
            {"min_turnover": "1000000", "bps": "20"},
        ],
        "untradeable_below_turnover": "1000000",
        "order_cap_fraction": "0.01",
        "forced_reduce_penalty_bps": "60",
        "slippage_multiplier": "1", "funding_delta": "0.02",
        "funding_blank_min_rate": "0.0001", "liquidity_window_days": 12,
    }


def test_g8_reversal_keeps_reducing_leg_when_increase_is_voided():
    legs = series.order_segments(
        "100", "-50", "100", "0.1", "5", "500000", "10000000",
        True, cost_parameters(),
    )
    assert legs == [
        {"quantity": "-100", "slippage_bps": "60",
         "kind": "forced_reduce_penalty"},
        {"quantity": "-50", "reason": "untradeable"},
    ]


@pytest.mark.parametrize("value", [0.5, float("nan"), True, "NaN", "Infinity", "bad"])
def test_rejects_float_and_nonfinite_inputs(value):
    with pytest.raises(series.SeriesError):
        series.decimal_value(value)


def test_negative_target_rounds_toward_zero():
    assert series.decimal_text(
        series.target_quantity("100000", "-0.5", "99.50", "0.1")
    ) == "-502.5"


@pytest.mark.parametrize(
    "position,target,minimum,notional,daily,hourly,history,expected",
    [
        ("100", "99.95", "0.1", "0", "100000000", "10000000", True, "min_qty"),
        ("100", "99.9", "0.1", "11", "100000000", "10000000", True, "min_notional"),
        ("0", "100", "0.1", "0", "100000000", "999999", True, "order_cap"),
        ("0", "1", "0.1", "0", "100000000", "10000000", False, "insufficient_history"),
    ],
)
def test_void_reasons(position, target, minimum, notional, daily, hourly,
                      history, expected):
    legs = series.order_segments(
        position, target, "100", minimum, notional, daily, hourly,
        history, cost_parameters(),
    )
    assert len(legs) == 1
    assert legs[0]["reason"] == expected


def test_full_close_bypasses_minima_and_stresses_penalty():
    cost = {**cost_parameters(), "slippage_multiplier": "3"}
    assert series.order_segments(
        "0.05", "0", "100", "0.1", "100", "0", "0", False, cost,
    ) == [{"quantity": "-0.05", "slippage_bps": "180",
           "kind": "forced_reduce_penalty"}]


def test_estimated_funding_is_adverse_for_short():
    assert series.decimal_text(
        series.funding_amount("-100", "-50", "10", "0.0001", "0.02",
                              estimated=True)
    ) == "-0.102"


def test_short_delisting_uses_high_and_buy_slippage():
    price, fee = series.delisting_cost(
        "-100", {"low": "0.95", "high": "1.02"},
        {"low": "0.97", "high": "1.04"}, "60", "0.00055",
    )
    assert series.decimal_text(price) == "1.04624"
    assert series.decimal_text(fee) == "0.0575432"


def test_host_imports_are_standard_library_or_approved_packages():
    tree = ast.parse(Path(series.__file__).read_text(encoding="utf-8"))
    modules = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0
            modules.append(node.module)
            modules.extend(node.module+'.'+alias.name for alias in node.names)
    allowed = ("program_code.research.r8_engine", "program_code.research.r8_ledger")
    for module in modules:
        assert module.split(".")[0] in sys.stdlib_module_names or any(
            module == prefix or module.startswith(prefix + ".") for prefix in allowed
        )
        assert not (module.endswith(".rules") or module.endswith(".materialize"))


# 以下 fixture 完全構造；不讀取任何 U1 真實輸出。
HOUR = 3600000
DAY = 24 * HOUR
START = 1641427200000  # 2022-01-06 星期四 UTC


def write_materialization(tmp_path, *, hours=4, symbols=('BTCUSDT',), hourly=None,
                          daily=None, funding=None, gaps=None, delistings=None):
    root = tmp_path / 'materialized'
    root.mkdir()
    (root / 'source').mkdir()
    manifest = {
        'schema_version': 'r8_materialization_v1', 'u1_manifest_sha256': 'a'*64,
        'u1_tool_version': 'r8-public-data-2', 'ledger_id': 'test-ledger',
        'hypothesis_id': 'h1', 'generation': 1, 'purpose': 'validation',
        'window': {'start': START, 'end': START+hours*HOUR},
        'warmup': {'start': START-13*DAY, 'end': START}, 'readable': {},
        'symbols': list(symbols), 'strategy_symbols': list(symbols), 'files': {},
        'gaps': gaps or {}, 'first_bar': {s: START-13*DAY for s in symbols},
        'min_notional': {s: '0' for s in symbols},
        'funding_interval_ms': {s: 8*HOUR for s in symbols},
        'delistings': delistings or {}, 'limitations': [],
    }
    def write(name, header, rows):
        buf = io.StringIO(newline=''); writer = csv.writer(buf)
        writer.writerow(header); writer.writerows(rows); raw = buf.getvalue().encode()
        (root / 'source' / name).write_bytes(raw)
        manifest['files']['source/'+name] = {
            'sha256': hashlib.sha256(raw).hexdigest(), 'rows': len(rows),
            'first': rows[0][0] if rows else None, 'last': rows[-1][0] if rows else None,
            'source_file': name+'.gz', 'source_sha256': 'b'*64,
        }
    for symbol in symbols:
        bars = (hourly or {}).get(symbol)
        if bars is None:
            bars = [[t, '100', '100', '100', '100', '10000', '10000000']
                    for t in range(START-13*DAY, START+hours*HOUR, HOUR)]
        days = (daily or {}).get(symbol)
        if days is None:
            days = [[t, '100', '100', '100', '100', '1000000', '20000000']
                    for t in range(START-13*DAY, START, DAY)]
        funds = (funding or {}).get(symbol)
        if funds is None:
            funds = [[t, '0'] for t in range(START-13*DAY, START+hours*HOUR+1, 8*HOUR)]
        write('kline_'+symbol+'_60.csv', ['timestamp','open','high','low','close','volume','turnover'], bars)
        write('kline_'+symbol+'_D.csv', ['timestamp','open','high','low','close','volume','turnover'], days)
        write('funding_'+symbol+'_funding.csv', ['timestamp','funding_rate'], funds)
        write('open_interest_'+symbol+'_4h.csv', ['timestamp','open_interest'], [])
    overlay=''.join('bybit,'+s+',cryptofuture,'+s+',USDT,1,0.01,0.1,'+s+',0.1,\n' for s in symbols).encode()
    (root/'symbol_properties_overlay.csv').write_bytes(overlay)
    manifest['symbol_properties_overlay_sha256']=hashlib.sha256(overlay).hexdigest()
    path=root/'materialization.json';path.write_bytes(canonical(manifest))
    return path


def test_materialization_reads_only_source_slices_and_checks_hashes(tmp_path):
    path = write_materialization(tmp_path)
    data = series.Materialization(path)
    assert data.hourly['BTCUSDT'][START]['close'] == Decimal('100')
    assert data.properties['BTCUSDT']['qty_step'] == Decimal('0.1')
    source = path.parent/'source/kline_BTCUSDT_60.csv'
    source.write_bytes(source.read_bytes().replace(b'100,100', b'101,100', 1))
    with pytest.raises(series.SeriesError, match='SHA'):
        series.Materialization(path)


def test_materialization_overlay_hash_and_path_escape(tmp_path):
    path = write_materialization(tmp_path)
    overlay = path.parent/'symbol_properties_overlay.csv'
    overlay.write_bytes(overlay.read_bytes()+b'\n')
    with pytest.raises(series.SeriesError, match='SHA'):
        series.Materialization(path)
    manifest=json.loads(path.read_bytes());manifest['files']['source/../../outside'] = {}
    path.write_bytes(canonical(manifest))
    with pytest.raises(series.SeriesError):
        series.Materialization(path)


def test_funding_schedule_interior_and_unaligned_edges():
    rows={-8*HOUR: Decimal('0.001'), 0: Decimal('0.002'),
          8*HOUR: Decimal('-0.003'), 12*HOUR: Decimal('0.001')}
    events=series.funding_schedule(rows, -9*HOUR, 20*HOUR, 8*HOUR, '0.0001')
    estimates={r['t']:r['rate'] for r in events if r['estimated']}
    assert estimates == {4*HOUR:'0.003', 16*HOUR:'0.001', 20*HOUR:'0.001'}
    assert series.funding_schedule({}, 1, 16*HOUR, 8*HOUR, '0.0001') == [
        {'t':8*HOUR,'rate':'0.0001','estimated':True},
        {'t':16*HOUR,'rate':'0.0001','estimated':True}]


def test_futures_account_does_not_add_notional_to_equity():
    account=series.Account('1000')
    account.fill('X', Decimal('2'), Decimal('100'), Decimal('1'))
    assert account.cash == Decimal('999')
    assert account.equity({'X':Decimal('110')}) == Decimal('1019')
    account.fill('X', Decimal('-3'), Decimal('110'), Decimal('2'))
    assert account.cash == Decimal('1017')
    assert account.positions == {'X':Decimal('-1')}
    assert account.equity({'X':Decimal('105')}) == Decimal('1022')


@pytest.mark.parametrize('scores,selected', [(['-1','100','-1','-1'],None),
    (['100','-1','-1'],None), (['1','1','1'],0), (['1','2','3'],2)])
def test_grid_selection_qualified_majority_and_ties(scores,selected):
    grid=[{'x':i} for i in range(len(scores))]
    neighborhood={'numeric':{'x':list(range(len(scores)))},'categorical':[]}
    result=series.select_grid_point(grid,neighborhood,scores)
    assert result['selected']==selected
    assert result['no_trade']==(selected is None)


def run_for(path, *, decisions=None, windows=None):
    m=json.loads(path.read_bytes())
    cfg={'trial_id':None,'materialization_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
         'code_commit':'c'*40,'engine_commit':'c'*40,'symbols':m['strategy_symbols'],
         'initial_cash':'100000','leverage':'10','gross_exposure_cap':'1',
         'decision_resolution':'hour','sharpe_frequency_seconds':3600,
         'warmup':m['warmup'],'score_windows':windows or [m['window']], 'folds':[],
         'cost':cost_parameters(),'model_artifact':None,'random_seed':1,
         'strategy':{},'algorithm':{'path':'program_code/research/r8_engine/lean_algo/examples/fixed_schedule.py','class':'FixedSchedule'},
         'mode':'validation'}
    return {'schema_version':'r8_lean_run_v1','materialization_sha256':cfg['materialization_sha256'],
            'run_config_sha256':hashlib.sha256(canonical(cfg)).hexdigest(),'run_config':cfg,
            'image_digest':series.IMAGE_DIGEST,'docker_argv':[],
            'algorithm_config_sha256':hashlib.sha256(canonical({k:v for k,v in cfg.items() if k!='mode'})).hexdigest(),
            'algorithm_files':{},'base_symbol_properties_sha256':'d'*64,
            'started_at':0,'ended_at':1,'exit_code':0,'lean_log_sha256':'e'*64,
            'mode':'validation','status':'completed','failure_reason':None,'failure_t':None,
            'decisions':decisions or [],'steps':[],'orders':[],'fills':[],'voided':[],
            'funding':[],'endpoint_funding':[],'fits':[], 'fill_forward_bars':[],
            'unexplained_cash_residual':{'per_step':[],'total':'0'}}


def test_replay_next_open_and_score_end_costs_from_source(tmp_path):
    path=write_materialization(tmp_path)
    run=run_for(path,decisions=[{'t':START,'targets':{'BTCUSDT':{'quantity':'1'}}}])
    actual=series.replay(series.Materialization(path),run)
    assert actual['fills']==[
        {'order_id':1,'decision_t':START,'change_t':START,'symbol':'BTCUSDT',
         'quantity':'1','price':'100.1','slippage_bps':'10','fee':'0.055055','kind':'normal'},
        {'order_id':2,'decision_t':START+4*HOUR,'change_t':START+4*HOUR,'symbol':'BTCUSDT',
         'quantity':'-1','price':'99.4','slippage_bps':'60','fee':'0.05467','kind':'score_end_liquidation'}]
    assert actual['steps'][-1]=={'t':START+4*HOUR,'cash':'99999.190275','equity':'99999.190275','positions':{}}
    assert actual['orders'][-1]=={'order_id':2,'kind':'score_end_liquidation','decision_t':START+4*HOUR,
                                  'symbol':'BTCUSDT','quantity':'-1','status':'filled'}


def observed_fixed_run(path):
    run=run_for(path,decisions=[{'t':START,'targets':{'BTCUSDT':{'quantity':'1'}}}])
    run['orders']=[{'order_id':1,'kind':'strategy','decision_t':START,'symbol':'BTCUSDT','quantity':'1','status':'filled'},
                   {'order_id':2,'kind':'score_end_liquidation','decision_t':START+4*HOUR,'symbol':'BTCUSDT','quantity':'-1','status':'filled'}]
    run['fills']=[{'order_id':1,'decision_t':START,'change_t':START,'symbol':'BTCUSDT',
                  'quantity':'1','price':'100.1','slippage_bps':'10','fee':'0.055055','kind':'normal'},
                 {'order_id':2,'decision_t':START+4*HOUR,'change_t':START+4*HOUR,'symbol':'BTCUSDT',
                  'quantity':'-1','price':'99.4','slippage_bps':'60','fee':'0.05467','kind':'score_end_liquidation'}]
    run['steps']=[{'t':t,'cash':'100000','equity':'100000','positions':{}}
                  for t in range(START-13*DAY+HOUR,START+1,HOUR)]
    run['steps'] += [{'t':t,'cash':'99999.944945','equity':'99999.844945','positions':{'BTCUSDT':'1'}}
                     for t in range(START+HOUR,START+4*HOUR,HOUR)]
    run['steps'] += [{'t':START+4*HOUR,'cash':'99999.190275','equity':'99999.190275','positions':{}}]
    run['funding']=[{'t':START,'symbol':'BTCUSDT','q_before':'0','q_after':'1','price':'100','rate':'0','amount':'0','estimated':False}]
    return run


def test_recompute_and_period_equity_include_end_liquidation(tmp_path):
    path=write_materialization(tmp_path);run=observed_fixed_run(path)
    report=series.recompute(path,run)
    assert report['recompute_passed'] is True
    values,sidecar=series.make_series(path,run,report)
    assert values['returns'][0] == [START//1000, -0.00000155055]
    assert values['returns'][1][1] == 0
    assert values['filled_periods']==0
    assert sidecar['produced_periods']==4
    assert values['returns'][-1][1] < 0


@pytest.mark.parametrize('section,index,field,value', [
    ('fills',0,'price','100.2'),('fills',0,'quantity','2'),('fills',0,'fee','1'),
    ('funding',0,'amount','-1'),('steps',-1,'equity','100000'),
    ('orders',0,'kind','no_trade_flatten'),
])
def test_recompute_rejects_tampered_observations(tmp_path,section,index,field,value):
    path=write_materialization(tmp_path);run=observed_fixed_run(path)
    run[section][index][field]=value
    report=series.recompute(path,run)
    assert not report['recompute_passed']
    with pytest.raises(series.SeriesError):
        series.make_series(path,run,report)


def test_weekly_grid_is_epoch_aligned_and_excludes_incomplete_periods():
    cfg={'sharpe_frequency_seconds':604800,'score_windows':[
        {'start':START+1,'end':START+3*7*DAY-1}]}
    assert series.periods(cfg)==[START//1000+604800]


def test_failed_run_zero_pads_grid_and_records_actual_periods(tmp_path):
    path=write_materialization(tmp_path);run=observed_fixed_run(path)
    run.update(status='failed',failure_reason='algorithm_exception',failure_t=START+2*HOUR)
    report=series.recompute(path,run)
    values,sidecar=series.make_series(path,run,report)
    assert len(values['returns'])==4
    assert values['returns'][2:]==[[START//1000+7200,0.0],[START//1000+10800,0.0]]
    assert values['filled_periods']==2
    assert sidecar['produced_periods']==2 and sidecar['recompute_passed'] is False


def test_beta_ols_includes_intercept_and_caps():
    assert series.ols_beta([Decimal('1'),Decimal('2'),Decimal('3')],
                           [Decimal('3'),Decimal('5'),Decimal('7')]) == Decimal('2')
    assert series.ols_beta([Decimal('1'),Decimal('2'),Decimal('3')],
                           [Decimal('10'),Decimal('20'),Decimal('30')]) == Decimal('3')


def test_beta_only_uses_fit_data_and_median_for_short_history(tmp_path):
    from decimal import localcontext
    symbols=('BTCUSDT','XUSDT','YUSDT')
    daily={s:[] for s in symbols}
    with localcontext() as ctx:
        ctx.prec=50
        prices={s:Decimal('100') for s in symbols}
        for i in range(102):
            for s in symbols:
                r=Decimal(['0.01','0.02','0.03'][i%3])
                if s=='XUSDT':r=2*r+Decimal('0.01')
                if i:prices[s]*=1+r
                if s=='YUSDT' and i<92:continue
                q=str(prices[s]);daily[s].append([START-(103-i)*DAY,q,q,q,q,'1','20000000'])
    path=write_materialization(tmp_path,symbols=symbols,daily=daily)
    m=json.loads(path.read_bytes());m['warmup']['start']=START-104*DAY;path.write_bytes(canonical(m))
    data=series.Materialization(path)
    betas=series.estimate_betas(data,{'start':START-104*DAY,'end':START})
    assert abs(Decimal(betas['XUSDT'])-2)<Decimal('1e-45')
    assert abs(Decimal(betas['YUSDT'])-Decimal('1.5'))<Decimal('1e-45')
    data.daily['XUSDT'][START+DAY]={'close':Decimal('999999')}
    assert series.estimate_betas(data,{'start':START-104*DAY,'end':START})==betas


def test_baseline_is_deterministic_and_new_position_does_not_receive_gap(tmp_path):
    path=write_materialization(tmp_path)
    run=observed_fixed_run(path)
    result=series.baselines(path,run)
    assert result['beta_matched_btc_v1']['returns']==[[START//1000+i*3600,0.0] for i in range(4)]
    assert canonical(result)==canonical(series.baselines(path,run))
    assert set(result)=={'beta_matched_btc_v1','btc_perp_hold_v1'}
    assert result['btc_perp_hold_v1']['returns'][0][1]<0


def test_stress_reprices_weights_and_reports_four_fixed_scenarios(tmp_path):
    path=write_materialization(tmp_path)
    run=run_for(path,decisions=[{'t':START,'targets':{'BTCUSDT':{'weight':'0.5'}}},
                               {'t':START+2*HOUR,'targets':{'BTCUSDT':{'weight':'0.5'}}}])
    result=series.stress(path,run)
    assert [(x['slippage_multiplier'],x['fee_rate']) for x in result['scenarios']]==[
        ('1','0.00055'),('2','0.00055'),('3','0.00055'),('2','0.00075')]
    assert Decimal(result['scenarios'][2]['net_return']) < Decimal(result['scenarios'][0]['net_return'])
    assert result['stress_passed'] is False
    assert result['breakeven']['multiplier']=='0'
    assert result['decision_approximation']


def test_stress_breakeven_is_recomputed_bracket(tmp_path):
    hourly={'BTCUSDT':[[t,'100','102','100','102' if t>=START else '100','1','100000000']
                       for t in range(START-13*DAY,START+4*HOUR,HOUR)]}
    path=write_materialization(tmp_path,hourly=hourly)
    run=run_for(path,decisions=[{'t':START,'targets':{'BTCUSDT':{'weight':'0.5'}}}])
    result=series.stress(path,run)
    point=Decimal(result['breakeven']['multiplier'])
    assert Decimal('2')<point<Decimal('3')
    assert Decimal(result['breakeven']['lower_net_return'])>=0
    assert Decimal(result['breakeven']['upper_net_return'])<=0


def refresh_run_hashes(run):
    run['run_config_sha256']=series.digest(canonical(run['run_config']))
    run['algorithm_config_sha256']=series.digest(canonical({k:v for k,v in run['run_config'].items() if k!='mode'}))


def synthetic_repo(tmp_path):
    root=tmp_path/'repo';root.mkdir()
    def git(*args):
        return subprocess.run(['git','-C',str(root),*args],check=True,capture_output=True).stdout.decode().strip()
    git('init','-q');git('config','user.name','Offline Fixture');git('config','user.email','fixture@example.invalid')
    names=['program_code/research/r8_engine/series.py','program_code/research/r8_engine/lean_algo/framework.py',
           'program_code/research/r8_ledger/ledger.py','hypothesis.py']
    for name in names:
        path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('# synthetic source '+name+'\n')
    git('add','.');git('-c','core.hooksPath=/dev/null','commit','-qm','synthetic engine')
    sha=git('rev-parse','HEAD');git('update-ref','refs/remotes/origin/main',sha)
    return root,sha,{n:series.digest((root/n).read_bytes()) for n in names},git


def iso(t):
    return datetime.fromtimestamp(t/1000,timezone.utc).isoformat().replace('+00:00','Z')


def submit_fixture(tmp_path):
    repo,sha,files,git=synthetic_repo(tmp_path)
    path=write_materialization(tmp_path,hours=32)
    book=ledger_module.ResearchLedger(tmp_path/'book')
    boundaries=list(map(iso,[START-15*DAY,START-7*DAY,START+32*HOUR,START+30*DAY,START+60*DAY]))
    reg={'hypothesis_id':'h1','generation':1,'family':'fixture','economic_mechanism':'合成測試',
         'decision_period':{'unit':'hour','value':1},'expected_holding_seconds':3600,
         'expected_turnover':1,'pessimistic_cost_ratio':.5,'data_range':{'start':boundaries[0],'end':boundaries[-1]},
         'time_splits':ledger_module.split_intervals(boundaries),'primary_metric':'after_cost_sharpe',
         'candidate_thresholds':{'sharpe':1},'multiple_testing':{'method':'BH','fdr':.05,'members':['h1'],'members_sha256':ledger_module.sha256(['h1'])},
         'max_lookback_seconds':13*86400,'label_period_seconds':3600,'max_holding_seconds':3600,
         'selection':{'type':'time_series','rule':'synthetic','known_at_period_start':boundaries[0],'symbols':['BTCUSDT']},
         'previous_no_go':None,'split_rationale':'synthetic','sharpe_frequency_seconds':3600,
         'oos_protocol':{'scheme':'expanding','initial_train_seconds':8*86400,'test_seconds':32*3600,
                         'step_seconds':32*3600,'purge_seconds':7*86400,'embargo_seconds':7*86400},
         'baselines':[{'id':'no_trade','kind':'strategy_independent'},{'id':'beta_matched_btc_v1','kind':'exposure_matched'}],
         'falsification_rule':{'degradation_z':1}}
    book.preregister(reg)
    folds=ledger_module.walk_forward_folds(reg)
    m=json.loads(path.read_bytes());m.update(purpose='research',ledger_id=book.ledger_id)
    m['window']['start']=START-15*DAY;m['warmup']={'start':START-28*DAY,'end':START-15*DAY}
    path.write_bytes(canonical(m))
    run=run_for(path,windows=[{'start':START,'end':START+32*HOUR}]);cfg=run['run_config']
    cfg.update(mode='trial',trial_id='t1',code_commit=sha,engine_commit=sha,folds=folds,
               algorithm={'path':'hypothesis.py','class':'Hypothesis'},strategy={'grid':[{'x':'1'}],'neighborhood':[[0]]})
    run.update(mode='trial',algorithm_files=files)
    run['fits']=[{'fold':0,'fit_window':folds[0]['fit_window'],'selection':{
        'grid_scores':['1'],'neighborhood_means':['1'],'qualified':[True],'selected':0,
        'selected_minus_neighborhood':'0','no_trade':False},'params':{'x':'1'},'model_sha256':'f'*64}]
    run['decisions']=[{'t':START,'targets':{'BTCUSDT':{'weight':'0.001'}}}]
    refresh_run_hashes(run)
    configuration={'strategy_parameters':{'run':{k:cfg[k] for k in (
        'initial_cash','leverage','gross_exposure_cap','decision_resolution','sharpe_frequency_seconds','algorithm','engine_commit')},'strategy':cfg['strategy']},'cost_model_parameters':cfg['cost']}
    record={'trial_id':'t1','hypothesis_id':'h1','generation':1,'parent_trial_id':None,'variant_parameters':{},
            'data_window':{k:iso(v) for k,v in m['window'].items()},'fit_window':folds[0]['fit_window'],
            'score_window':folds[0]['score_window'],'manifest_sha256':cfg['materialization_sha256'],
            'data_files':{k:v['sha256'] for k,v in m['files'].items()},'code_commit':sha,
            'configuration':configuration,'configuration_sha256':series.digest(canonical(configuration)),
            **series.RUNTIME_METADATA,'random_seed':1,'sharpe_frequency':{'unit':'hour','seconds':3600,'annualized':False},
            'evaluation_kind':'out_of_sample','role':'exploratory','folds':folds,'oos_protocol_sha256':ledger_module.sha256(reg['oos_protocol'])}
    book.begin_trial(record)
    begun=json.loads((book.out/'trials.jsonl').read_bytes().splitlines()[-1])['payload']['record']['started_at']
    query_record={**record,'started_at':begun,'finished':False,'status':'aborted'}
    run['started_at']=run['ended_at']=series.timestamp(begun)
    calls=[]
    def query(directory,trial):
        assert Path(directory)==book.out and trial=='t1'
        return copy.deepcopy(query_record)
    def materialize(**kwargs):
        calls.append(kwargs)
        assert kwargs['trial']=='t1' and kwargs['hypothesis']=='h1'
        assert kwargs['window']==record['data_window']
        shutil.copytree(path.parent,kwargs['out'])
        return Path(kwargs['out'])/'materialization.json'
    rebuilt=series.replay(series.Materialization(path),run)
    for key in ('orders','fills','voided','funding','endpoint_funding','steps'):
        run[key]=rebuilt[key]
    runpath=tmp_path/'run.json'
    def submit():
        runpath.write_bytes(canonical(run))
        return series.submit(book.out,'t1',tmp_path/'unread-u1',runpath,
                             trial_query=query,materializer=materialize,repo=repo)
    return locals()


def test_submit_generated_provenance_baseline_and_real_ledger_acceptance(tmp_path):
    f=submit_fixture(tmp_path);result=f['submit']()
    assert result['status']=='completed'
    assert set(result['baseline_sha256'])=={'no_trade','beta_matched_btc_v1'}
    summary=result['result_summary'];provenance=summary['provenance']
    assert provenance['recompute_passed'] is True and len(provenance['stress_scenarios'])==4
    report=series.recompute(f['path'],f['run'])
    expected,sidecar=series.make_series(f['path'],f['run'],report)
    base=series.baselines(f['path'],f['run']);stress=series.stress(f['path'],f['run'])
    for key,value in [('series',expected),('baseline',base['beta_matched_btc_v1']),('stress',stress),('sidecar',sidecar),('recompute_report',report)]:
        sha=series.digest(canonical(value))
        assert provenance[key+'_sha256']==sha
        assert (f['book'].out/'u6_artifacts'/sha).read_bytes()==canonical(value)
    assert summary['fits']==f['run']['fits']
    assert f['calls'][0]['u1']==tmp_path/'unread-u1'


@pytest.mark.parametrize('mutation',['validation','verification','trial_id','identity','manifest','code','engine','untracked','finished','holdout','recompute'])
def test_submit_rejection_never_finishes_or_changes_ledger(tmp_path,mutation):
    f=submit_fixture(tmp_path);run=f['run'];cfg=run['run_config'];record=f['query_record']
    if mutation in ('validation','verification'):
        run['mode']=cfg['mode']=mutation
    elif mutation=='trial_id':cfg['trial_id']='other'
    elif mutation=='identity':record['configuration']['cost_model_parameters']['taker_fee_rate']='0'
    elif mutation=='manifest':
        m=json.loads(f['path'].read_bytes());m['limitations'].append('changed');f['path'].write_bytes(canonical(m))
    elif mutation=='code':(f['repo']/'hypothesis.py').write_text('# modified\n')
    elif mutation=='engine':(f['repo']/'program_code/research/r8_engine/series.py').write_text('# modified\n')
    elif mutation=='untracked':(f['repo']/'program_code/research/r8_engine/extra.py').write_text('# new\n')
    elif mutation=='finished':record['finished']=True
    elif mutation=='holdout':record['evaluation_kind']='holdout_falsification'
    elif mutation=='recompute':run['fills'][0]['fee']='0'
    refresh_run_hashes(run)
    before={p.relative_to(f['book'].out):p.read_bytes() for p in f['book'].out.rglob('*') if p.is_file()}
    with pytest.raises(series.SeriesError):f['submit']()
    after={p.relative_to(f['book'].out):p.read_bytes() for p in f['book'].out.rglob('*') if p.is_file()}
    assert after==before


def test_submit_failed_full_grid_is_accepted_and_requires_operator_stop(tmp_path):
    f=submit_fixture(tmp_path);run=f['run']
    run.update(status='failed',failure_reason='algorithm_exception',failure_t=START+2*HOUR)
    result=f['submit']()
    assert result['status']=='failed' and result['produced_periods']==32
    summary=result['result_summary']
    assert summary['produced_periods']==2 and summary['operator_stop_required'] is True
    assert summary['provenance']['recompute_passed'] is False
    values=json.loads((f['book'].out/'series'/(result['returns_sha256']+'.json')).read_bytes())
    assert values['filled_periods']==30 and all(r[1]==0 for r in values['returns'][2:])


def test_submit_parser_has_only_authorized_inputs_and_no_status():
    parser=series.argument_parser()
    for option in ('--status','--series','--baseline','--stress','--sidecar','--model'):
        with pytest.raises(SystemExit):parser.parse_args(['submit','--ledger','b','--trial','t','--u1','u','--run','r',option,'x'])


def test_u4_subprocess_contract_does_not_read_u1_or_run_docker(tmp_path,monkeypatch):
    calls=[]
    def execute(argv,**kwargs):
        calls.append((argv,kwargs))
        return subprocess.CompletedProcess(argv,0,b'',b'')
    monkeypatch.setattr(series.subprocess,'run',execute)
    series.rematerialize(u1=tmp_path/'nonexistent',ledger=tmp_path/'book',hypothesis='h1',
                         window={'start':iso(START),'end':iso(START+HOUR)},trial='t1',out=tmp_path/'out',repo=tmp_path)
    argv=calls[0][0]
    assert argv[:3]==[sys.executable,'-m','program_code.research.r8_engine.materialize']
    assert argv[argv.index('--trial')+1]=='t1'
    assert argv[argv.index('--u1-manifest-sha256')+1]=='b6519a7b2f5eae4759612690790ddb6680db62aa4e723427f51c21a7d6257006'
    assert '--validation' not in argv and 'docker' not in argv


def seal_observation(path,run):
    refresh_run_hashes(run)
    result=series.replay(series.Materialization(path),run)
    for key in ('orders','fills','voided','funding','endpoint_funding','steps'):
        run[key]=copy.deepcopy(result[key])
    return result


def test_adjacent_windows_keep_positions_and_endpoint_funding_goes_in_last_period(tmp_path):
    path=write_materialization(tmp_path,funding={'BTCUSDT':[[START-8*HOUR,'0.01'],[START,'0.01'],[START+4*HOUR,'0.01']]})
    run=run_for(path,windows=[{'start':START,'end':START+2*HOUR},{'start':START+2*HOUR,'end':START+4*HOUR}],
                decisions=[{'t':START,'targets':{'BTCUSDT':{'quantity':'1'}}}])
    result=seal_observation(path,run)
    assert [f['change_t'] for f in result['fills']]==[START,START+4*HOUR]
    assert result['endpoint_funding'][0]['amount']=='-1.02'
    assert result['steps'][13*24]['cash']=='99998.924945'  # entry plus START funding
    values,_=series.make_series(path,run,series.recompute(path,run))
    # 最後一步現金未含端點資金費；帳本最後一期含端點資金費。
    before=Decimal(result['steps'][-2]['equity']);after=Decimal(result['steps'][-1]['equity'])-Decimal('1.02')
    assert values['returns'][-1][1]==pytest.approx(float(after/before-1),abs=1e-15)


def test_delisting_partial_bar_order_identity_and_adverse_funding(tmp_path):
    delivery=START+HOUR+HOUR//2
    bars=[[t,'1','1.04','0.97','1','1000','10000000'] for t in range(START-13*DAY,START+HOUR,HOUR)]
    bars.append([START+HOUR,'1','1.02','0.95','1','500','5000000'])
    path=write_materialization(tmp_path,hours=4,hourly={'BTCUSDT':bars},
                              funding={'BTCUSDT':[[delivery,'0.02']]},
                              delistings={'BTCUSDT':{'deliveryTime':delivery,'partial_last_bar':True}})
    run=run_for(path,decisions=[{'t':START,'targets':{'BTCUSDT':{'quantity':'502.5'}}}])
    result=seal_observation(path,run)
    close=result['fills'][-1]
    assert {k:close[k] for k in ('order_id','decision_t','change_t','kind','price','fee')}=={
        'order_id':2,'decision_t':delivery,'change_t':delivery,'kind':'delisting_settlement',
        'price':'0.9443','fee':'0.2609809125'}
    assert result['funding'][-1]['q_after']=='0' and result['funding'][-1]['amount']=='-10.251'
    assert series.recompute(path,run)['recompute_passed']


def test_noop_decision_does_not_consume_order_id(tmp_path):
    path=write_materialization(tmp_path)
    run=run_for(path,decisions=[{'t':START,'targets':{'BTCUSDT':{'weight':'0'}}},
                                {'t':START+HOUR,'targets':{'BTCUSDT':{'quantity':'1'}}}])
    result=series.replay(series.Materialization(path),run)
    assert [o['order_id'] for o in result['orders']]==[1,2]


def test_gap_symbol_not_visible_and_pending_replacement_uses_real_position(tmp_path):
    symbols=('BTCUSDT','XUSDT')
    bars=[[t,'100','100','100','100','10000','10000000'] for t in range(START-13*DAY,START+6*HOUR,HOUR) if t!=START+HOUR]
    path=write_materialization(tmp_path,hours=6,symbols=symbols,hourly={'XUSDT':bars})
    run=run_for(path,decisions=[
        {'t':START,'targets':{'BTCUSDT':{'quantity':'0'},'XUSDT':{'quantity':'1'}}},
        {'t':START+HOUR,'targets':{'BTCUSDT':{'quantity':'0'},'XUSDT':{'quantity':'2'}}},
        {'t':START+2*HOUR,'targets':{'BTCUSDT':{'quantity':'0'}}},
        {'t':START+3*HOUR,'targets':{'BTCUSDT':{'quantity':'0'},'XUSDT':{'quantity':'3'}}}])
    result=series.replay(series.Materialization(path),run)
    assert result['failure_reason'] is None
    assert [(f['change_t'],f['quantity']) for f in result['fills'] if f['kind']=='normal']==[
        (START,'1'),(START+2*HOUR,'1'),(START+3*HOUR,'1')]
    assert result['delayed_fills']==[{'symbol':'XUSDT','t':START+2*HOUR}]
    assert series.filled_periods(series.Materialization(path),run['run_config'],result,series.periods(run['run_config']))=={(START+HOUR)//1000,(START+2*HOUR)//1000}


def test_actual_price_exposure_drift_is_report_only(tmp_path):
    bars=[[t,'100','100','100','100','10000','10000000'] for t in range(START-13*DAY,START,HOUR)]
    bars += [[t,'200','200','200','200','10000','10000000'] for t in range(START,START+4*HOUR,HOUR)]
    path=write_materialization(tmp_path,hourly={'BTCUSDT':bars})
    run=run_for(path,decisions=[{'t':START,'targets':{'BTCUSDT':{'weight':'0.75'}}}])
    result=seal_observation(path,run)
    assert result['failure_reason'] is None and Decimal(result['max_actual_gross_exposure'])>1
    assert series.recompute(path,run)['recompute_passed']


def test_gross_cap_failed_and_false_failure_rejected(tmp_path):
    path=write_materialization(tmp_path)
    run=run_for(path,decisions=[{'t':START,'targets':{'BTCUSDT':{'quantity':'1100'}}}])
    # 單筆上限放寬只是構造測試設定；研究設定仍由身份凍結。
    run['run_config']['cost']['order_cap_fraction']='1';seal_observation(path,run)
    with pytest.raises(series.SeriesError):series.make_series(path,run,series.recompute(path,run))
    run.update(status='failed',failure_reason='gross_exposure_cap',failure_t=START)
    values,sidecar=series.make_series(path,run,series.recompute(path,run))
    assert values['filled_periods']==4 and sidecar['produced_periods']==0
    run['failure_t']=START+HOUR
    with pytest.raises(series.SeriesError,match='曝險失敗未重現'):
        series.make_series(path,run,series.recompute(path,run))


def test_async_rotation_fails_after_increase_fills_before_delayed_reduce(tmp_path):
    bars=[[t,'100','100','100','100','100','10000000'] for t in range(START-13*DAY,START+6*HOUR,HOUR) if t!=START+HOUR]
    path=write_materialization(tmp_path,hours=6,symbols=('BTCUSDT','XUSDT'),hourly={'XUSDT':bars})
    run=run_for(path,decisions=[{'t':START,'targets':{'BTCUSDT':{'quantity':'0'},'XUSDT':{'quantity':'750'}}},
                              {'t':START+HOUR,'targets':{'BTCUSDT':{'quantity':'750'},'XUSDT':{'quantity':'0'}}}])
    result=seal_observation(path,run)
    assert result['failure_reason']=='gross_exposure_cap' and result['failure_t']==START+2*HOUR
    run.update(status='failed',failure_reason='gross_exposure_cap',failure_t=START+2*HOUR)
    values,sidecar=series.make_series(path,run,series.recompute(path,run))
    assert sidecar['produced_periods']==2 and values['filled_periods']>=4


def test_fit_selection_and_params_rederived_and_no_trade_flatten(tmp_path):
    f=submit_fixture(tmp_path);run=f['run'];path=f['path']
    run['fits'][0]['selection']['selected_minus_neighborhood']='999'
    assert 'fits.0' in series.recompute(path,run)['differences']
    run['fits'][0]['selection']['selected_minus_neighborhood']='0'
    run['fits'][0]['params']={'x':'2'}
    assert 'fits.0' in series.recompute(path,run)['differences']
    # 第二折不交易：已持有部位以正常 next-open 訂單平倉。
    run['fits'][0]['params']={'x':'1'}
    fold=run['run_config']['folds'][0];end=fold['score_window']['end'];middle=iso(START+16*HOUR)
    fold['score_window']['end']=middle
    nextfold=copy.deepcopy(fold);nextfold['score_window']={'start':middle,'end':end}
    run['run_config']['folds'].append(nextfold)
    run['run_config']['score_windows']=[f['score_window'] for f in run['run_config']['folds']]
    nextfit=copy.deepcopy(run['fits'][0]);nextfit.update(fold=1,params=None,model_sha256=None,
        selection={'grid_scores':['-1'],'neighborhood_means':['-1'],'qualified':[False],'selected':None,'selected_minus_neighborhood':None,'no_trade':True})
    run['fits'].append(nextfit);result=seal_observation(path,run)
    assert result['orders'][-1]['kind']=='no_trade_flatten'
    assert result['fills'][-1]['change_t']==START+16*HOUR
    assert series.recompute(path,run)['recompute_passed']


def test_trial_quantity_target_rejected(tmp_path):
    f=submit_fixture(tmp_path);f['run']['decisions'][0]['targets']['BTCUSDT']={'quantity':'1'}
    with pytest.raises(series.SeriesError,match='quantity'):series.recompute(f['path'],f['run'])


@pytest.mark.parametrize('field',['fill_forward_bars','unexplained_cash_residual'])
def test_completed_run_cannot_hide_forward_fill_or_cash_residual(tmp_path,field):
    path=write_materialization(tmp_path);run=observed_fixed_run(path)
    run[field]=[{'t':START,'symbol':'BTCUSDT'}] if field=='fill_forward_bars' else {'per_step':[{'t':START,'residual':'0.0000000001'}],'total':'0'}
    with pytest.raises(series.SeriesError):series.make_series(path,run,series.recompute(path,run))


def test_filled_gap_ending_exactly_thursday_marks_recovery_week(tmp_path):
    path=write_materialization(tmp_path,hours=7*24+1);data=series.Materialization(path)
    # 構造部位與可讀切片的缺漏，不以真實行情作測試。
    gap=START-HOUR;data.hourly['BTCUSDT'].pop(gap);data.times['BTCUSDT'].remove(gap)
    cfg=run_for(path,windows=[{'start':START-7*DAY,'end':START+7*DAY}])['run_config'];cfg['sharpe_frequency_seconds']=7*86400
    record={'fills':[{'symbol':'BTCUSDT','change_t':START-2*HOUR,'quantity':'1'}],'delayed_fills':[]}
    assert series.filled_periods(data,cfg,record,series.periods(cfg))=={START//1000-7*86400,START//1000}


def test_filled_funding_blank_stale_price_delay_and_no_position_exclusions(tmp_path):
    path=write_materialization(tmp_path,hours=24,funding={'BTCUSDT':[[START,'0.001'],[START+16*HOUR,'0.001'],[START+24*HOUR,'0.001']]})
    data=series.Materialization(path);cfg=run_for(path)['run_config']
    record={'fills':[{'symbol':'BTCUSDT','change_t':START,'quantity':'1'}],'delayed_fills':[]}
    flags=series.filled_periods(data,cfg,record,series.periods(cfg))
    assert set(range(START//1000,START//1000+16*3600,3600))<=flags
    record['fills']=[]
    assert series.filled_periods(data,cfg,record,series.periods(cfg))==set()
    # 非整點結算須以 T 之前最後一根收盤計價，屬情形 3。
    data.funding['BTCUSDT']={START+HOUR//2:Decimal('0')};data.manifest['funding_interval_ms']['BTCUSDT']=100*HOUR
    record['fills']=[{'symbol':'BTCUSDT','change_t':START,'quantity':'1'}]
    record['delayed_fills']=[{'symbol':'BTCUSDT','t':START+2*HOUR}]
    assert series.filled_periods(data,cfg,record,series.periods(cfg))=={START//1000,(START+2*HOUR)//1000}


def test_beta_baseline_gap_uses_old_position_intraday_uses_adjusted_futures_equity(tmp_path):
    bars=[[t,'100','100','100','100','1000','10000000'] for t in range(START-13*DAY,START+HOUR,HOUR)]
    bars += [[START+HOUR,'200','220','200','220','1000','10000000'],
             [START+2*HOUR,'220','220','220','220','1000','10000000'],
             [START+3*HOUR,'220','220','220','220','1000','10000000']]
    path=write_materialization(tmp_path,hourly={'BTCUSDT':bars})
    run=run_for(path,decisions=[{'t':START,'targets':{'BTCUSDT':{'quantity':'100'}}},
                              {'t':START+HOUR,'targets':{'BTCUSDT':{'quantity':'300'}}}])
    cost=run['run_config']['cost'];cost.update(slippage_multiplier='0',taker_fee_rate='0')
    seal_observation(path,run)
    baseline=series.baselines(path,run)['beta_matched_btc_v1']
    assert baseline['returns'][0][1]==0
    assert baseline['returns'][1][1]==pytest.approx(149/605,abs=1e-15)
    assert baseline['returns'][2][1]==0


def test_hold_baseline_adjacent_fold_boundary_funding_is_not_double_counted(tmp_path):
    path=write_materialization(tmp_path,funding={'BTCUSDT':[[START,'0.01'],[START+2*HOUR,'0.01'],[START+4*HOUR,'0.01']]})
    run=run_for(path,windows=[{'start':START,'end':START+2*HOUR},{'start':START+2*HOUR,'end':START+4*HOUR}])
    cost=run['run_config']['cost'];cost.update(taker_fee_rate='0',slippage_multiplier='0')
    refresh_run_hashes(run)
    actual=series.baselines(path,run)['btc_perp_hold_v1']['returns']
    # 第一折 qty1000，第二折 qty989.8；邊界 T=2h 取較不利的舊部位1000。
    # 初始100000，T=0:-1020，T=2h:-1020，T=4h:-1009.596 =>96950.404。
    compounded=Decimal(1)
    for _,r in actual:compounded*=1+Decimal(str(r))
    assert float(compounded)==pytest.approx(.96950404,abs=1e-15)


def test_source_tamper_with_rehashed_manifest_still_rejected_by_submit(tmp_path):
    f=submit_fixture(tmp_path)
    name='source/kline_BTCUSDT_60.csv';file=f['path'].parent/name
    file.write_bytes(file.read_bytes().replace(b'10000000',b'10000001',1))
    m=json.loads(f['path'].read_bytes());m['files'][name]['sha256']=series.digest(file.read_bytes())
    f['path'].write_bytes(canonical(m))
    before=(f['book'].out/'trials.jsonl').read_bytes()
    with pytest.raises(series.SeriesError):f['submit']()
    assert (f['book'].out/'trials.jsonl').read_bytes()==before


def test_git_rejects_unmerged_engine_and_engine_tree_change(tmp_path):
    f=submit_fixture(tmp_path);cfg=f['run']['run_config'];git=f['git']
    target=f['repo']/'program_code/research/r8_engine/series.py';target.write_text('# changed engine\n')
    git('add','.');git('-c','core.hooksPath=/dev/null','commit','-qm','unreviewed engine')
    new=git('rev-parse','HEAD');cfg['code_commit']=new
    f['run']['algorithm_files'][target.relative_to(f['repo']).as_posix()]=series.digest(target.read_bytes())
    with pytest.raises(series.SeriesError,match='引擎目錄'):series.verify_code(f['repo'],f['run'])
    cfg['engine_commit']=new
    with pytest.raises(series.SeriesError,match='Git 完整性'):series.verify_code(f['repo'],f['run'])


def test_missing_ledger_rejected_without_creating_directory(tmp_path):
    with pytest.raises(series.SeriesError,match='帳本必須已存在'):
        series.submit(tmp_path/'missing','t1',tmp_path/'u1',tmp_path/'run')
    assert not (tmp_path/'missing').exists()


def test_daily_decision_only_midnight_and_next_day_open(tmp_path):
    path=write_materialization(tmp_path,hours=48)
    run=run_for(path,decisions=[{'t':START+DAY,'targets':{'BTCUSDT':{'quantity':'1'}}}])
    run['run_config']['decision_resolution']='day';result=seal_observation(path,run)
    assert result['fills'][0]['change_t']==START+DAY and result['fills'][0]['price']=='100.1'
    run['decisions'][0]['t']+=HOUR;result=series.replay(series.Materialization(path),run)
    assert result['failure_reason']=='invalid_decision'


def test_pending_replacement_zero_difference_and_score_end_cancellation(tmp_path):
    bars=[[t,'100','100','100','100','1000','10000000'] for t in range(START-13*DAY,START,HOUR)]
    path=write_materialization(tmp_path,hours=4,symbols=('BTCUSDT','XUSDT'),hourly={'XUSDT':bars})
    run=run_for(path,decisions=[{'t':START,'targets':{'BTCUSDT':{'quantity':'0'},'XUSDT':{'quantity':'1'}}}])
    result=series.replay(series.Materialization(path),run)
    assert result['orders']==[{'order_id':1,'kind':'strategy','decision_t':START,'symbol':'XUSDT',
        'quantity':'1','status':'cancelled','cancel_t':START+4*HOUR,'cancel_reason':'score_end'}]
    assert not result['fills']


def test_cli_outputs_match_function_bytes(tmp_path):
    path=write_materialization(tmp_path);run=observed_fixed_run(path);record=tmp_path/'run.json';record.write_bytes(canonical(run))
    report=tmp_path/'report.json';values=tmp_path/'values.json';pressure=tmp_path/'stress.json';base=tmp_path/'base'
    for command,out,extra in [('recompute',report,[]),('series',values,['--recompute',str(report)]),('baseline',base,[]),('stress',pressure,[])]:
        assert series.main([command,'--materialization',str(path),'--run',str(record),'--out',str(out),*extra])==0
    assert report.read_bytes()==canonical(series.recompute(path,run))
    expected,sidecar=series.make_series(path,run,json.loads(report.read_bytes()))
    assert values.read_bytes()==canonical(expected) and (tmp_path/'values.json.sidecar.json').read_bytes()==canonical(sidecar)
    assert pressure.read_bytes()==canonical(series.stress(path,run))
    for name,value in series.baselines(path,run).items():assert (base/(name+'.json')).read_bytes()==canonical(value)


@pytest.mark.parametrize('field,delta,accepted',[
    ('price','0.0000001',True),('price','0.000001',False),
    ('fee','0.0000009',True),('fee','0.000002',False),
    ('quantity','0.0000000001',False),('slippage_bps','0.0000000001',False)])
def test_recompute_tolerances_and_exact_quantity_bps(tmp_path,field,delta,accepted):
    path=write_materialization(tmp_path);run=observed_fixed_run(path)
    run['fills'][0][field]=series.decimal_text(Decimal(run['fills'][0][field])+Decimal(delta))
    assert series.recompute(path,run)['recompute_passed'] is accepted


@pytest.mark.parametrize('location',['run','config','cost','materialization'])
def test_section7_rejects_added_fields(tmp_path,location):
    path=write_materialization(tmp_path);run=observed_fixed_run(path)
    if location=='materialization':
        m=json.loads(path.read_bytes());m['extra']=1;path.write_bytes(canonical(m))
    else:
        obj={'run':run,'config':run['run_config'],'cost':run['run_config']['cost']}[location];obj['extra']=1
        refresh_run_hashes(run)
    with pytest.raises(series.SeriesError,match='§7'):series.recompute(path,run)


def test_runtime_metadata_exact_contract():
    image='sha256:2657ed3355efb78d78bd0a5d4f126b01367a635e01bccd220b654d7742d182b6'
    assert series.RUNTIME_METADATA=={
        'cost_model':{'id':'r8_cost_rules','version':'r8-p4-v1'},
        'fill_model':{'id':'r8_next_open_fill','version':'r8-p4-v1'},
        'engine':{'id':'lean','version':image},'dependencies':{'lean_image_digest':image},
        'time_semantics':{'known_at':'bar_end','fill_at':'next_bar_open','simulated_latency_ms':0}}


def test_failed_run_cannot_supply_fabricated_fit_selection(tmp_path):
    f=submit_fixture(tmp_path);run=f['run']
    run.update(status='failed',failure_reason='algorithm_exception',failure_t=START+2*HOUR)
    run['fits'][0]['selection']['selected']=None
    with pytest.raises(series.SeriesError,match='fits'):f['submit']()


def test_failed_baseline_padding_does_not_read_post_failure_prices(tmp_path):
    path=write_materialization(tmp_path);run=observed_fixed_run(path)
    run.update(status='failed',failure_reason='algorithm_exception',failure_t=START+2*HOUR)
    result=series.baselines(path,run)['beta_matched_btc_v1']
    assert result['returns'][2:]==[[(START+2*HOUR)//1000,0.0],[(START+3*HOUR)//1000,0.0]]
    assert result['filled_periods']==2


def test_stress_full_path_hand_values_include_repriced_partial_reduce(tmp_path):
    path=write_materialization(tmp_path)
    run=run_for(path,decisions=[{'t':START,'targets':{'BTCUSDT':{'weight':'0.5'}}},
                              {'t':START+2*HOUR,'targets':{'BTCUSDT':{'weight':'0.5'}}}])
    scenarios=series.stress(path,run)['scenarios']
    # 基準第二次目標499.6；×2 目標499.3；×3 目標499.1，非沿用基準成交量。
    # ×3 期末現金=99972.4175-.54-.0493515-1048.11-26.956391。
    # ×2／壓力費率期末現金=99962.425-.28-.052395-699.02-36.99813。
    assert [s['net_return'] for s in scenarios]==['-0.0040466261','-0.00754025385','-0.011032382425','-0.00773925525']


def test_stress_keeps_failed_scenarios_and_does_not_call_them_passed(tmp_path):
    path=write_materialization(tmp_path)
    run=run_for(path,decisions=[{'t':START,'targets':{'BTCUSDT':{'weight':'1.1'}}}])
    run['run_config']['cost']['order_cap_fraction']='1';refresh_run_hashes(run)
    result=series.stress(path,run)
    assert len(result['scenarios'])==4
    assert all(s['status']=='failed' and s['failure_reason']=='gross_exposure_cap' and s['net_return'] is None for s in result['scenarios'])
    assert result['stress_passed'] is False


def test_submit_rejects_execution_before_trial_began(tmp_path):
    f=submit_fixture(tmp_path);f['run']['started_at']-=1
    before=(f['book'].out/'trials.jsonl').read_bytes()
    with pytest.raises(series.SeriesError,match='begin_trial'):f['submit']()
    assert (f['book'].out/'trials.jsonl').read_bytes()==before


def test_missing_daily_turnover_counts_zero_and_recent_listing_blocks_open(tmp_path):
    path=write_materialization(tmp_path);data=series.Materialization(path);cost=cost_parameters()
    for t in list(data.daily['BTCUSDT'])[-7:]:data.daily['BTCUSDT'].pop(t)
    assert data.liquidity('BTCUSDT',START,cost)==(Decimal(0),Decimal('10000000'),True)
    data.manifest['first_bar']['BTCUSDT']=START-11*DAY
    assert data.liquidity('BTCUSDT',START,cost)[2] is False


@pytest.mark.parametrize('turnover,bps',[('100000000','5'),('10000000','10'),('1000000','20')])
def test_three_liquidity_tiers(turnover,bps):
    assert series.order_segments('0','1','100','0.1','0',turnover,'10000000',True,cost_parameters())[0]['slippage_bps']==bps
