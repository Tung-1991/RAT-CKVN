from copy import deepcopy
from dataclasses import asdict
from datetime import date, timedelta
from types import SimpleNamespace

from ckps.models import Quote
from ckps.services.market_context import context, entry_context, publish_context, analysis_context
from ckps.dashboard.mayin.signal_preview import signal_preview


def analysis(now=1000, **p2):
    return {'contract':'VN30F1M','observed_at':now,'quote_at':now,'quote_price':2007,
            'p2':{'buy_alert':True,'badge':'READY','price_fresh':True,'indicators':{'rsi':60},**p2}}


def test_entry_is_confirmed_result_not_ready_badge_or_notification_switch():
    value=analysis();before=deepcopy(value)
    assert entry_context(value,'VN30F1M',now=1000)=={'state':'READY','price':2007,'observed_at':1000}
    assert value==before
    assert entry_context(analysis(buy_alert=False),'VN30F1M',now=1000)=={'state':'WAIT'}
    assert entry_context(value,'41I1GB000',now=1000)=={'state':'WAIT_SOURCE'}
    assert entry_context(value,'VN30F1M',now=1011)=={'state':'WAIT_SOURCE','reason':'ANALYSIS_STALE'}
    value['quote_at']=900
    assert entry_context(value,'VN30F1M',now=1000)=={'state':'WAIT_SOURCE','reason':'PRICE_STALE'}
    value=analysis();value['quote_at']=995
    assert entry_context(value,'VN30F1M',now=1000)['observed_at']==995
    assert entry_context(analysis(badge='OFF'),'VN30F1M',now=1000)=={'state':'OFF'}
    assert entry_context(analysis(indicators={}), 'VN30F1M',now=1000)=={'state':'WAIT_SOURCE','reason':'ANALYSIS_PENDING'}


def test_shared_preview_uses_same_contract_fresh_analysis_and_local_ma200_only():
    today=date.today()
    rows=[{'time':(today-timedelta(days=220-i)).isoformat(),'high':2002,'low':1998,'close':2000} for i in range(200)]
    snapshot=SimpleNamespace(contract='VN30F1M',quotes={'VN30F1M':Quote('VN30F1M',2007,at=1000)},bars=rows)
    publish_context({'contract':'VN30F1M','observed_at':1000,'entry':entry_context(analysis(),'VN30F1M',now=1000)})
    value=context(snapshot,now=1000)
    assert value['state']=='ABOVE' and value['ma']==2000 and value['entry']['price']==2007
    view={'contract':snapshot.contract,'quotes':{'VN30F1M':asdict(snapshot.quotes['VN30F1M'])},'market_context':value}
    original=deepcopy(view)
    entry,trend=signal_preview(view,now=1000)
    assert entry[0]=='LONG · 2,007.0' and trend[0]=='UP'
    assert 'EMA' not in str((entry,trend)) and 'RSI' not in str((entry,trend))
    assert view==original
    snapshot.quotes['VN30F1M'].last=1990
    view['quotes']['VN30F1M']=asdict(snapshot.quotes['VN30F1M'])
    view['market_context']=context(snapshot,now=1000)
    assert signal_preview(view,now=1000)[1][0]=='DOWN'
    # A down market is not a Short entry signal; the backend result stays Long.
    assert signal_preview(view,now=1000)[0][0].startswith('LONG')
    publish_context({'contract':'41I1GB000','observed_at':1000,'entry':{'state':'READY','price':2007,'observed_at':1000}})
    assert context(snapshot,now=1000)['entry']['state']=='WAIT_SOURCE'
    snapshot.bars=rows[:199]
    assert context(snapshot,now=1000)['state']=='WAIT'
    assert context(snapshot,now=1011)['state']=='WAIT'
    assert all(result[0]=='CHỜ' for result in signal_preview(view,now=1011))
    snapshot.quotes['VN30F1M'].symbol='41I1GB000'
    assert context(snapshot,now=1000)['state']=='WAIT'


def test_stale_or_invalid_shared_entry_cannot_survive_a_fresh_market_quote():
    quote=Quote('VN30F1M',2007,at=1000)
    snapshot=SimpleNamespace(contract=quote.symbol,quotes={quote.symbol:quote},bars=[])
    for candidate in ({'state':'READY','price':float('inf'),'observed_at':1000},
                      {'state':'READY','price':2007,'observed_at':900}):
        # Persist ordinary JSON to simulate a malformed/outdated backend artifact.
        from ckps.config import runtime_root
        import json
        path=runtime_root()/'signals'/'market-context.json';path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps({'contract':quote.symbol,'observed_at':1000,'entry':candidate}),encoding='utf-8')
        assert context(snapshot,now=1000)['entry']=={'state':'WAIT_SOURCE'}


def test_wait_reason_distinguishes_history_backend_failure_and_old_analysis():
    quote=Quote('VN30F1M',1813.4,at=1000)
    snapshot=SimpleNamespace(contract=quote.symbol,quotes={quote.symbol:quote},bars=[])
    cases=[(analysis(indicators={},status='THIẾU LỊCH SỬ 1D'),'HISTORY','Chưa đủ nến 1D'),
           ({**analysis(),'p2':{'status':'THIẾU LỊCH SỬ 1D','badge':'WAIT'}},'HISTORY','Chưa đủ nến 1D'),
           ({**analysis(),'error':'private diagnostic'},'ANALYSIS_ERROR','Phân tích lỗi'),
           (analysis(now=980),'ANALYSIS_STALE','Chờ kết quả phân tích mới')]
    for raw,reason,detail in cases:
        entry=entry_context(raw,quote.symbol,now=1000)
        assert entry=={'state':'WAIT_SOURCE','reason':reason}
        assert 'private diagnostic' not in str(entry)
        publish_context({'contract':quote.symbol,'observed_at':1000,'entry':entry},preview=True)
        shared=context(snapshot,now=1000,preview=True)
        assert shared['entry']==entry
        view={'contract':quote.symbol,'quotes':{quote.symbol:asdict(quote)},'market_context':shared}
        assert signal_preview(view,now=1000)[0][1].startswith(detail)
    view['market_context']['entry']={'state':'WAIT_SOURCE'}
    view['analysis_running']=True
    assert signal_preview(view,now=1000)[0][1]=='Chờ kết quả phân tích'


def test_public_indicator_details_explain_wait_without_granting_a_signal_or_refreshing_old_data():
    raw=analysis(buy_alert=False,status='CHỜ CẮT LÊN',indicators={
        'buy_ema_fast':1998,'buy_ema_slow':2000,'rsi':42.5,'secret':'private','sell_ema_fast':float('nan')})
    public=analysis_context(raw,'VN30F1M',now=1000)
    assert public['p2']['indicators']=={'buy_ema_fast':1998,'buy_ema_slow':2000,'rsi':42.5}
    quote=Quote('VN30F1M',2007,at=1000)
    publish_context({'contract':quote.symbol,'observed_at':1000,'entry':entry_context(raw,quote.symbol,now=1000),
        'analysis':public},preview=True)
    snapshot=SimpleNamespace(contract=quote.symbol,quotes={quote.symbol:quote},bars=[])
    view={'contract':quote.symbol,'quotes':{quote.symbol:asdict(quote)},'market_context':context(snapshot,now=1000,preview=True)}
    result,_=signal_preview(view,now=1000)
    assert result[0]=='CHƯA CÓ ĐIỂM'
    assert 'CHỜ CẮT LÊN' in result[1] and 'EMA nhanh 1,998.0' in result[1] and 'RSI 42.50' in result[1]
    assert 'private' not in str(public)
    assert not analysis_context(raw,'41I1GB000',now=1000)
    assert not analysis_context(raw,quote.symbol,now=1011)
    assert not analysis_context({**raw,'quote_at':980},quote.symbol,now=1000)
    assert not analysis_context({**raw,'error':'private credentials'},quote.symbol,now=1000)
    view['quotes'][quote.symbol]['at']=1011
    view['market_context']['observed_at']=1011
    result,_=signal_preview(view,now=1011)
    assert 'EMA' not in result[1] and 'RSI' not in result[1]
