"""Inline PAPER/REAL switching; account discovery never opens a settings window."""
from dataclasses import replace
import os
import queue

from ckps.services.connection_probe import ConnectionProbe


class ModeSwitchMixin:
    def _mode_credentials(self):
        return {key:self.credentials.get(key) or os.environ.get('CKPS_DNSE_API_'+key.upper(),'')
                for key in ('key','secret')}

    def _mode_identity(self):
        return (self.runtime,self.settings.mode,self.settings.account_no,self.settings.loan_package_id,
                self._mode_credentials())

    def _cancel_mode_probe(self):
        probe=getattr(self,'_mode_probe',None)
        if probe:probe.close()
        self._mode_probe=None

    def _mode_failure(self,text):
        self._cancel_mode_probe()
        self.mode_requested=None
        self.mode_choice.set(self.settings.mode)
        self.render()
        self.report(text,error=True)

    def _mode_selected(self,mode):
        if self.closing:return
        if self.switch_pending:
            self.mode_choice.set(self.switch_pending[0].mode)
            return
        if mode not in {'PAPER','REAL'}:
            self._mode_failure('Chỉ có PAPER hoặc REAL.')
            return
        if mode==self.mode_requested and getattr(self,'_mode_probe',None):return
        self._cancel_mode_probe()
        self.clear_confirmation()
        if mode==self.settings.mode and (self.runtime is not None or getattr(self,'preview_only',False)):
            self.mode_requested=None
            self.mode_choice.set(mode)
            self.render()
            return
        if getattr(self,'preview_only',False):
            self._mode_failure('Mẫu offline chỉ dùng PAPER; mở app giao dịch để chọn REAL.')
            return
        if self.order_busy:
            self._mode_failure('Chờ thao tác lệnh hiện tại hoàn tất trước khi đổi sổ.')
            return
        credentials=self._mode_credentials()
        if mode=='PAPER':
            self._apply_mode(replace(self.settings,mode='PAPER').validate(),credentials)
            return
        if not all(credentials.values()):
            self._mode_failure('REAL chưa có API DNSE. Mở KẾT NỐI → DNSE / VỐN để cấu hình.')
            return
        self.mode_requested='REAL'
        self._mode_probe_identity=self._mode_identity()
        self._mode_probe=ConnectionProbe()
        self._mode_probe_revision=self._mode_probe.request(credentials,self.settings.account_no,self.settings.loan_package_id)
        self.mode_choice.set('REAL')
        self.render()
        self.report('Đang xác minh tài khoản CKPS và gói DNSE…')

    def _drain_mode_probe(self):
        probe=getattr(self,'_mode_probe',None)
        if not probe:return
        if self.mode_requested!='REAL':
            self._cancel_mode_probe()
            return
        try:revision,profile=probe.events.get_nowait()
        except queue.Empty:return
        if revision!=self._mode_probe_revision:return
        if self.closing or self.switch_pending or self._mode_probe_identity!=self._mode_identity():
            self._mode_failure('Kết nối đã thay đổi; chọn lại PAPER/REAL để xác minh.')
            return
        if profile.get('error'):
            self._mode_failure('Chưa chuyển REAL: '+profile['error'])
            return
        account,package=profile.get('account_no'),profile.get('loan_package_id')
        if not account or not package:
            self._mode_failure('DNSE chưa có một tài khoản/gói CKPS được chọn. Mở KẾT NỐI → ĐỌC API để chọn.')
            return
        credentials=self._mode_credentials()
        settings=replace(self.settings,mode='REAL',account_no=account,loan_package_id=package).validate()
        self._cancel_mode_probe()
        self._apply_mode(settings,credentials)

    def _apply_mode(self,settings,credentials):
        commands=getattr(self.runtime,'commands',None)
        if commands is not None and not commands.empty():
            self._mode_failure('Chờ thao tác trong sổ hiện tại hoàn tất trước khi đổi PAPER/REAL.')
            return
        self.clear_confirmation()
        self.mode_requested=settings.mode
        self.bot_requested=False
        self.switch_pending=(settings,credentials)
        if self.runtime:
            self.runtime.close()  # Disarms immediately; ledger closes before reopening.
        else:
            self.switch_pending=None
            self._start_runtime(settings,credentials)
        self.render()
