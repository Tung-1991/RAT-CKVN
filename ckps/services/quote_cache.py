"""Last DNSE prices for display only; never merge these into trading quotes."""
from dataclasses import asdict
import json
from math import isfinite
import os
import time

from ckps.config import runtime_root
from ckps.models import Quote, is_vn30, load_record


class QuoteCache:
    def __init__(self):
        self.value = {}
        self.persisted = {}
        self.written_at = 0.
        self.path = runtime_root() / 'last-market.json'
        try:
            value = json.loads(self.path.read_text(encoding='utf-8'))
            quote = load_record(Quote, value['quote'])
            if value['contract'] == quote.symbol and is_vn30(quote.symbol) and quote.source.startswith('DNSE') and isfinite(quote.last) and quote.last > 0 and 0 < quote.at <= time.time()+2:
                self.value = {'contract': quote.symbol, 'quote': asdict(quote)}
                self.persisted = self.value
        except (OSError, ValueError, TypeError, KeyError, AttributeError):
            pass

    def observe(self, snapshot):
        quote = snapshot.quotes.get(snapshot.contract) if snapshot else None
        if not quote or quote.symbol != snapshot.contract or not quote.source.startswith('DNSE') or not quote.fresh(86400*30):
            return
        value = {'contract': snapshot.contract, 'quote': asdict(quote)}
        if self.value.get('contract') == snapshot.contract and quote.at < self.value['quote']['at']:
            return
        self.value = value
        if value == self.persisted or time.monotonic()-self.written_at < 5:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix('.tmp')
            temporary.write_text(json.dumps(value, allow_nan=False), encoding='utf-8')
            os.replace(temporary, self.path)
            self.persisted = value
            self.written_at = time.monotonic()
        except (OSError, ValueError):
            pass
