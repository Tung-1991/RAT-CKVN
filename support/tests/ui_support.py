"""UI integration fixtures exercise the actual PAPER app without broker I/O."""
from dataclasses import asdict
from datetime import date, timedelta
import queue
import time
from types import SimpleNamespace

from ckps.dashboard.window import App
from ckps.models import Position, Quote, Settings
from ckps.rules.protection import evaluate


def paper_form_app():
    app=App(settings=Settings(),start_runtime=False)
    p=Position.create('VN30F1M','LONG',1,2000,managed=True,history_verified=True,margin_per_contract=40_000_000)
    p.original_quantity=2;p.realized=840_000
    evaluate(p,2012,app.ticket_rules(2000)[0],1.)
    p.metrics['DYN:AUTO']={'count':1,'anchor':2008.4}
    app.view={'mode':'PAPER','contract':p.symbol,'armed':False,'healthy':True,'consistent':True,
        'atr14_pct':1.,'atr14':{'period':14,'pct':1.,'count':20,'contract':p.symbol,
            'as_of':(date.today()-timedelta(days=1)).isoformat()},
        'quotes':{p.symbol:asdict(Quote(p.symbol,2007,source='DNSE'))},'positions':[asdict(p)],
        'orders':[],'history':[],'events':[],
        'account':{'nav':100_000_000,'total_money':100_000_000,'collateral_total':100_000_000,
            'qmax_long':1,'qmax_short':1,'used_margin':40_000_000,'pending_margin':0,'remaining_margin':50_000_000,
            'margin_per_contract':40_000_000,'margin_reference_price':2000},
        'LONG':{'maximum':1},'SHORT':{'maximum':1}}
    def send(name,*args,**kwargs):
        if name=='set_managed':
            row=next(row for row in app.view['positions'] if row['id']==args[0])
            row['managed']=args[1]
            app.render()
    app.send=send
    app.render();app.positions_tree.selection_set(p.id);app._refresh_ticket_preview()

    from ckps.services import connection_probe
    from ckps.dashboard.mayin import connection_window
    class Probe:
        def __init__(self):self.events=queue.Queue();self.revision=0
        def request(self,*args):
            self.revision+=1
            package={'id':'2279','name':'CKPS','tradingFee':{'schemaType':'FIXED','fixedTradingFee':2000,'fixedDailyCloseTradingFee':2000}}
            from ckps.connections.dnse.fees import package_fees
            self.events.put((self.revision,{'accounts':[{'id':'1234567890'}],'account_no':'1234567890',
                'packages':[package],'loan_package_id':'2279','balance':{'remaining_margin':100_000_000,'used_margin':0},
                'fees':package_fees(package),'observed_at':time.time()}))
            return self.revision
        def close(self):pass
    connection_probe.ConnectionProbe=Probe
    def start_backend(app,settings,credentials):
        assert credentials['key'] and credentials['secret']
        app.signal_session=SimpleNamespace(running=True,status='Đang phân tích',close=lambda:None,configure=lambda *args:None)
    connection_window.start_signal_backend=start_backend
    return app
