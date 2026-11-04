"""Timestamped price observations and durable full-exit capture."""
from ckps.connections.dnse.protocol import BrokerError
from .exit_requests import FULL_EXITS, request_exit


class PriceEventsMixin:
    def _observe_price_samples(self, samples):
        """Latch full exits in event order, without submitting at a past price."""
        positions = self.store.positions()
        atr = {p.symbol: self._atr(p.symbol) for p in positions}
        allowed = self.enabled.is_set() and self.consistent
        try:
            self._ready()
        except BrokerError:
            allowed = False
        newest = dict(self.latest.quotes)
        try:
            with self.store.transaction():
                for quote in samples:
                    if (not quote.fresh(self.settings.max_quote_age)
                            or quote.at < self.price_observed_at.get(quote.symbol, 0)):
                        continue
                    self.price_observed_at[quote.symbol] = quote.at
                    self.latest.quotes[quote.symbol] = quote
                    previous = newest.get(quote.symbol)
                    if not previous or quote.at >= previous.at:
                        newest[quote.symbol] = quote
                    for position in positions:
                        if position.symbol != quote.symbol:
                            continue
                        decision = self._decision(position, quote.last, atr_pct=atr[position.symbol])
                        if (decision and decision.reason in FULL_EXITS and allowed and self.enabled.is_set()
                                and position.managed and position.id not in self.suspended):
                            request_exit(position, decision)
                            self._abandon_open_remainders(position)
                        self.store.save_position(position)
        finally:
            self.latest.quotes = newest

    def on_prices(self, quotes, extremes, samples=None):
        if not self.latest or not self.healthy:
            return
        if samples is not None:
            self._observe_price_samples(samples)
        accepted = set()
        for symbol, quote in quotes.items():
            previous = self.latest.quotes.get(symbol)
            if quote.symbol == symbol and quote.fresh(self.settings.max_quote_age) and (
                    not previous or quote.at >= previous.at):
                self.latest.quotes[symbol] = quote
                accepted.add(symbol)
        for position in (self.store.positions() if samples is None else ()):
            if position.symbol in extremes and position.symbol in accepted:
                low, high = extremes[position.symbol]
                position.best = max(position.best or position.entry, high) if position.sign > 0 else min(position.best or position.entry, low)
                position.worst = min(position.worst or position.entry, low) if position.sign > 0 else max(position.worst or position.entry, high)
                self.store.save_position(position)
        self._manage()
