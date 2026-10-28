from copy import deepcopy
from dataclasses import asdict
from datetime import date, timedelta
from types import SimpleNamespace

from ckps.models import Quote
from ckps.services.market_context import context, entry_context, publish_context
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
    assert entry_context(value,'VN30F1M',now=1011)=={'state':'WAIT_SOURCE'}
    value['quote_at']=900
    assert entry_context(value,'VN30F1M',now=1000)=={'state':'WAIT_SOURCE'}
    value=analysis();value['quote_at']=995
    assert entry_context(value,'VN30F1M',now=1000)['observed_at']==995
    assert entry_context(analysis(badge='OFF'),'VN30F1M',now=1000)=={'state':'OFF'}
    assert entry_context(analysis(indicators={}), 'VN30F1M',now=1000)=={'state':'WAIT_SOURCE'}


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
