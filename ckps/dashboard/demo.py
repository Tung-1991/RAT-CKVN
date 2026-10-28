"""One in-memory Long and three E/M moments. No runtime, ledger or network."""
from dataclasses import asdict, replace
import time

from ckps.models import ExitSettings, Position, Quote, Settings
from ckps.rules.protection import evaluate
from .window import App


def demo_rules():
    return ExitSettings(sl_enabled=True,sl_distance=10,tp_enabled=True,tp_distance=40,
        arm_enabled=True,arm_gain=20,trail_gap=5,arm_close_pct=50,arm_repeat=True,repeat_gap=5,
        dynamic_enabled=True,dynamic_policy='AUTO',dynamic_close_pct=50,dynamic_repeat=True,
        atr_start_multiplier=.5,atr_trail_multiplier=.8,retention_pct=70,retention_until_enabled=False)


def long_sample(stage):
    if stage not in {'DYNAMIC','LẶP','TSL / ARM'}:raise ValueError('Mốc mẫu không hợp lệ.')
    rules=demo_rules()
    position=Position.create('VN30F1M','LONG',2,2000,managed=True,history_verified=True)
    position.id='DEMO-LONG'
    evaluate(position,2012,rules,1.)
    current=2010.
    if stage in {'LẶP','TSL / ARM'}:
        position.quantity=1
        position.realized=840_000
        position.metrics['DYN:AUTO']={'count':1,'anchor':2008.4}
        current=2007.
    if stage=='TSL / ARM':
        evaluate(position,2025,rules,1.)
        current=2022.
    return position,current


class DemoApp(App):
    preview_only=True

    def __init__(self):
        super().__init__(settings=Settings(exit=asdict(demo_rules())),start_runtime=False)
        self.title('RAT VN30 · MẪU E/M · KHÔNG GỬI LỆNH')
        self.show_sample('LẶP')

    def show_sample(self,stage):
        position,current=long_sample(stage)
        self.view={'mode':'PAPER','contract':position.symbol,'armed':False,'healthy':True,'consistent':True,
            'atr14_pct':1.,'quotes':{position.symbol:asdict(Quote(position.symbol,current,source='MẪU'))},
            'positions':[asdict(position)],'orders':[],'history':[],
            'account':{'nav':100_000_000+position.realized+position.pnl(current),'total_money':100_000_000,'collateral_total':100_000_000,
                'qmax_long':1,'qmax_short':1,'used_margin':40_000_000,'pending_margin':0,'remaining_margin':50_000_000,
                'margin_per_contract':40_000_000},'events':[],'LONG':{'maximum':0},'SHORT':{'maximum':0}}
        self.render()
        self.positions_tree.selection_set(position.id)
        self._refresh_ticket_preview()
        self._fit_preview_text()

    def render(self):
        # Samples stay explicitly marked and fresh while their frozen scenario
        # is on screen; never show a DNSE waiting badge beside invented prices.
        for quote in self.view.get('quotes',{}).values():quote['at']=time.time()
        self.view['market_context']={'state':'ABOVE','ma':1985,'observed_at':time.time(),
            'entry':{'state':'READY','price':2007,'observed_at':time.time()}}
        super().render()
        for button in self.open_buttons:button.configure(state='disabled')
        for button in self.action_buttons.values():button.configure(state='disabled')
        self.lbl_brain.configure(text='MẪU OFFLINE',text_color='#F59E0B')
        self.lbl_market.configure(text='GIÁ MẪU · KHÔNG KẾT NỐI DNSE')
        self.lbl_account.configure(text='MẪU · Không dùng sổ giao dịch')
        self.status.grid_remove()

    def _refresh_ticket_preview(self):
        # A sample is a frozen observation, not a live quote that expires while
        # the user reads RULE. This applies only to the explicit demo app.
        for quote in self.view.get('quotes',{}).values():quote['at']=time.time()
        return super()._refresh_ticket_preview()

    def _render_selected_management(self):
        positions=self.view.get('positions',[])
        if len(positions)==1 and not self.positions_tree.selection():
            self.positions_tree.selection_set(positions[0]['id'])
        return super()._render_selected_management()

    def _sync_selection(self):
        super()._sync_selection()
        for button in getattr(self,'action_buttons',{}).values():button.configure(state='disabled')

    def send(self,name,*args,**kwargs):
        if name=='arm':
            self.view['armed']=bool(args[0])
            self.bot_requested=self.view['armed']
            self.render()
            return
        if name=='configure_position':
            position=next(row for row in self.view['positions'] if row['id']==args[0])
            position['exit_overrides']=args[1]
            self.render()
            return
        if name=='set_managed':
            position=next(row for row in self.view['positions'] if row['id']==args[0])
            position['managed']=bool(args[1])
            self.render()
            return
        self.report('Bản mẫu chỉ rà UI/E/M; không gửi lệnh hoặc lưu cấu hình thật.')

    def toggle_bot(self):
        if self.mode_requested or self.switch_pending:
            self.report('Hoàn tất hoặc hủy cấu hình sổ trước khi bật BOT.')
            return
        self.send('arm',not self.view.get('armed',False))

    def save_config(self,settings):
        self.settings=replace(settings,mode='PAPER').validate()
        self.render()
        self.report('Đã áp dụng RULE vào Long mẫu trong phiên; không ghi cấu hình thật.')

    def _start_runtime(self,*args,**kwargs):
        raise ValueError('Bản mẫu chỉ rà giao diện; mở app giao dịch để kết nối DNSE thật.')
