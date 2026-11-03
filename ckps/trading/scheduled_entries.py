"""Durable, explicitly confirmed manual entries. Never retry a submitted request."""
from datetime import date
from math import isfinite

from ckps.models import Order,direction,is_vn30,quantity
from ckps.connections.dnse.protocol import BrokerError
from ckps.services import calendar
from ckps.services.entry_schedule import queue_session,session_hold
from ckps.rules.p2.market import exchange_close_minute
from .portfolio import capacity


class ScheduledEntriesMixin:
    def schedule_manual(self,side,qty,price,symbol,session_date):
        direction(side)
        session=queue_session()
        if not session or session['date']!=session_date:
            raise ValueError('Phiên đã thay đổi; xem và xác nhận lại vé lệnh.')
        if not is_vn30(symbol) or symbol=='VN30F1M' or self.latest and self.latest.contract not in {symbol,'VN30F1M'}:
            raise ValueError('Chưa xác minh đúng mã hợp đồng cho lệnh chờ.')
        if not isinstance(price,(int,float)) or not isfinite(price) or price<=0 or abs(price*10-round(price*10))>1e-6:
            raise ValueError('LO chờ phiên cần giá dương, đúng bước 0,1 điểm.')
        qty=quantity(qty)
        if qty<=0:raise ValueError('Lệnh chờ cần số HĐ cụ thể lớn hơn 0.')
        current=[p for p in self.store.positions() if p.symbol==symbol]
        pending=[o for o in self.store.orders(pending=True) if o.action=='OPEN' and o.symbol==symbol]
        if any(p.side!=side for p in current) or any(o.side!=side for o in pending):
            raise ValueError('Đang có vị thế/lệnh chờ chiều ngược.')
        if current and (not current[0].managed or self._pending_closes(current[0].id)):
            raise ValueError('Vị thế chưa nhận quản lý hoặc đang chờ đóng; không vào thêm.')
        limit=None
        if self.latest and self.latest.contract==symbol:
            limit=capacity(self.settings,self.latest,self.store.positions(),self.store.orders(pending=True),side,price,self.exits())
            if self.broker.mode=='PAPER' and self.latest.margin_per_contract and self.latest.qmax_long is not None and self.latest.qmax_short is not None and qty>limit.maximum:
                raise ValueError(limit.reason or f'Tối đa {limit.maximum} HĐ theo sức mở gần nhất.')
        order=Order.create(symbol,side,qty,kind='LO',price=price,status='SCHEDULED',scheduled_for=session_date,
            margin_per_contract=limit.margin_per_contract if limit else None,margin_reference_price=price,
            parent_position_id=current[0].id if current else '',message='Chờ phiên · Chưa gửi broker')
        with self.store.transaction():
            self.store.save_order(order)
            self.store.event('SCHEDULE',f'LO {side} {symbol} · {qty} HĐ @ {price:g} · phiên {session_date} · lưu tại app')
        return order

    def _scheduled_message(self,order,message,*,status=None):
        if order.message==message and (status is None or order.status==status):return
        order.message=message
        if status:order.status=status
        self.store.save_order(order)
        if status:self.store.event('SCHEDULE',f'{order.symbol} · {message}')

    def _entry_capacity_orders(self,order):
        return [o for o in self.store.orders(pending=True) if o.id!=order.id
            and not (order.scheduled_for and o.status=='SCHEDULED')]

    def _dispatch_scheduled(self):
        if self.entry_stopping.is_set():return
        now=calendar.local_now()
        for order in sorted((o for o in self.store.orders(pending=True) if o.status=='SCHEDULED'),key=lambda o:o.created_at):
            if order.id in self.suspended_entries or order.abandon_remainder:
                self._scheduled_message(order,'Đã hủy lệnh chờ chưa gửi',status='CANCELLED');continue
            try:target=date.fromisoformat(order.scheduled_for)
            except (ValueError,TypeError):
                self._scheduled_message(order,'Phiên chờ không hợp lệ; đặt lại lệnh',status='FAILED');continue
            if now.date()>target or now.date()==target and now.hour*60+now.minute>=exchange_close_minute('VN30'):
                self._scheduled_message(order,'Đã qua phiên hẹn; không tự chuyển ngày',status='EXPIRED');continue
            if self.latest and self.latest.contract not in {order.symbol,'VN30F1M'}:
                self._scheduled_message(order,'Mã hợp đồng đã đổi; không tự chuyển mã',status='EXPIRED');continue
            if now.date()<target or session_hold():continue
            if self.broker.mode=='REAL' and (not getattr(self.broker,'token','') or getattr(self.broker,'token_until',0)<=now.timestamp()):
                self._scheduled_message(order,'Chờ xác thực OTP REAL trong phiên');continue
            try:
                self._ready()
                quote=self._quote(order.symbol)
                self._validate_limit('LO',order.price,quote)
                current=[p for p in self.store.positions() if p.symbol==order.symbol]
                if order.parent_position_id and not any(p.id==order.parent_position_id for p in current):
                    self._scheduled_message(order,'Vị thế gốc đã đóng/đổi; hủy lệnh vào thêm',status='CANCELLED');continue
                if current and (not current[0].managed or self._pending_closes(current[0].id)):
                    raise ValueError('Chờ quyền vị thế / lệnh đóng')
                self._entry_exits(order.side)
                snapshot=self.latest
                if hasattr(self.broker,'opening_limits'):
                    from dataclasses import replace
                    snapshot=replace(snapshot,**self.broker.opening_limits(order.symbol,order.price))
                limit=capacity(self.settings,snapshot,self.store.positions(),self._entry_capacity_orders(order),order.side,order.price,self.exits())
                if order.quantity>limit.maximum:raise ValueError('Chờ sức mở đủ số HĐ đã xác nhận')
                if self.entry_stopping.is_set() or order.id in self.suspended_entries:return
                if session_hold():return
                self._quote(order.symbol)
                order.margin_per_contract=limit.margin_per_contract
                order.message=''
            except (BrokerError,ValueError,TypeError) as exc:
                self._scheduled_message(order,str(exc));continue
            # Same durable ID. SUBMITTING -> UNKNOWN on restart; never back to SCHEDULED.
            try:self._send(order)
            except (BrokerError,ValueError):pass
            break  # Read a new account snapshot before the next submission.
