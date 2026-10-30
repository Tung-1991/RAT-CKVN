"""Read every intraday NORMAL order page before reconciling the ledger."""
from ckps.models import quantity
from .protocol import BrokerError, unwrap


def intraday_orders(broker):
    result, seen, expected = [], set(), None
    for page in range(1000):
        body = unwrap(broker.request('GET', f'/accounts/{broker.account_no}/orders', params={
            'marketType': 'DERIVATIVE', 'orderCategory': 'NORMAL', 'pageIndex': page, 'pageSize': 100}))
        rows = body.get('orders') if isinstance(body, dict) else body
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise BrokerError('DNSE thiếu danh sách orders; chưa đối soát sổ lệnh.')
        total = body.get('totalRecords', body.get('total', body.get('totalElements'))) if isinstance(body, dict) else None
        if total is not None:
            total = quantity(total)
            if expected is not None and expected != total:
                raise BrokerError('Sổ lệnh DNSE đổi khi phân trang; chờ đọc lại đầy đủ.')
            expected = total
        if isinstance(body, dict) and body.get('pageIndex') is not None and quantity(body['pageIndex']) != page:
            raise BrokerError('DNSE trả sai trang lệnh; chưa đối soát.')
        for row in rows:
            identifier = str(row.get('id') or row.get('orderId') or '')
            if identifier and identifier in seen:
                raise BrokerError('DNSE trả trùng lệnh giữa các trang; chờ đọc lại.')
            if identifier:seen.add(identifier)
        result.extend(rows)
        if expected is not None:
            if len(result) == expected:return result
            if len(result) > expected or not rows:
                raise BrokerError('DNSE trả sổ lệnh thiếu/thừa trang; chưa đối soát.')
        elif len(rows) < 100:
            return result
    raise BrokerError('Sổ lệnh DNSE vượt giới hạn phân trang; chưa đối soát.')
