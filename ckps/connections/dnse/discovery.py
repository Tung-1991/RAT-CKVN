"""Signed account preview: GET only, with no trading token or execution access."""
import re
import time

from .account import balances
from .client import DNSEBroker
from .fees import package_fees
from .protocol import BrokerError, rows, unwrap


class AccountReader(DNSEBroker):
    requires_account = False

    def request(self, method, path, **kwargs):
        if getattr(self, 'stopping', None) and self.stopping.is_set():raise BrokerError('Đã dừng đọc tài khoản.')
        if method != 'GET' or kwargs.get('trading') or not re.fullmatch(r'/accounts(?:/\d+/(?:balances|loan-packages))?', path):
            raise BrokerError('Preview tài khoản chỉ đọc tài khoản, ký quỹ và gói phái sinh.')
        return super().request(method, path, **kwargs)

    def profile(self, account='', package=''):
        raw = rows(unwrap(self.request('GET', '/accounts')), 'accounts')
        accounts = [{'id': str(row['id'])} for row in raw if str(row.get('id', '')).isdigit()
            and row.get('derivativeAccount') is True and isinstance(row.get('derivative'), dict)
            and row['derivative'].get('status') == 'ACTIVE']
        if account and account not in {row['id'] for row in accounts}:
            raise BrokerError('Tài khoản đã chọn không phải tài khoản CKPS đang hoạt động của API này.')
        account = account or (accounts[0]['id'] if len(accounts) == 1 else '')
        result = {'accounts': accounts, 'account_no': account, 'loan_package_id': '', 'packages': [],
            'balance': {}, 'fees': {}, 'observed_at': time.time()}
        if not account:return result
        response = unwrap(self.request('GET', f'/accounts/{account}/loan-packages',
            params={'marketType': 'DERIVATIVE', 'symbol': 'VN30F1M'}))
        if isinstance(response,dict) and response.get('marketType') not in {None,'DERIVATIVE'}:
            raise BrokerError('DNSE trả gói không thuộc phái sinh.')
        packages = rows(response, 'loanPackages')
        packages = [row for row in packages if str(row.get('id', '')).isdigit()]
        if len({str(row['id']) for row in packages})!=len(packages):raise BrokerError('Danh sách gói ký quỹ có ID trùng.')
        if package and package not in {str(row['id']) for row in packages}:
            raise BrokerError('Gói ký quỹ đã chọn không còn trong danh sách DNSE của tài khoản này.')
        package = package or (str(packages[0]['id']) if len(packages) == 1 else '')
        value = unwrap(self.request('GET', f'/accounts/{account}/balances'))
        derivative = value.get('derivative') if isinstance(value, dict) else None
        result.update(packages=packages, loan_package_id=package,
            balance=balances(derivative) if isinstance(derivative, dict) else {})
        selected = next((row for row in packages if str(row['id']) == package), None)
        result['fees'] = package_fees(selected)
        return result
