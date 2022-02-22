from dataclasses import dataclass, field
from .constants import SIDE, LABEL, ORDERTYPE
from typing import Union, List
import logging
from .order import Order, MarketOrder, LimitOrder, SL, TP
from .price import Price, Pips, candle_mean
import arrow
import betterMT5 as mt5
from datetime import timedelta

logging.basicConfig()
log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)


class PriceNotReasonableError(ValueError):
    pass

class UnreasonableOrderPlacementError(ValueError):
    pass

class PositionInitMissingDataError(ValueError):
    pass


@dataclass
class Position:
    time: arrow.Arrow
    symbol: Union[str, mt5.Symbol]
    side: Union[str, SIDE]
    entry_price: Union[str, float, None]
    sl_price: Union[str, float]
    tp_prices: List[Union[str, float]] = field(default_factory=list)
    text: str = ""

    def __post_init__(self):

        # needed for orders management
        self.orders = list()

        # enforces self.symbol type
        if isinstance(self.symbol, str):
            self.symbol = mt5.Symbol(self.symbol)

        # enforces self.side type
        if isinstance(self.side, str):
            self.side = SIDE.from_str(self.side)

        # add entry order
        self.entry = self.add_entry(self.entry_price)

        # adds stop loss and tp orders
        tick_size = self.symbol.info.trade_tick_size

        self.sl_price = Price(self.sl_price, tick_size)
        self.sl = self.add_order(SL(self.time, SIDE(-self.side), self.sl_price))

        enforced_tp_prices = list()
        self.tps = list()
        for tp in self.tp_prices:
            tp_price = Price(tp, tick_size)
            enforced_tp_prices.append(tp_price)
            self.tps.append(self.add_order(TP(self.time, SIDE(-self.side), tp_price)))
        self.tp_prices = enforced_tp_prices
    
    @classmethod
    def from_dict(cls, data: dict):
        if (not ('time' in data) or 
            not (all([attr in data['interpretation'] for attr in 'symbol side sl'.split(' ')]))):
            raise PositionInitMissingDataError(data)

        tp_get = data['interpretation'].get('tp')
        tps = [tp_get]
        if isinstance(tp_get, list):
            tps = tp_get

        return cls(
            time=arrow.get(data['time']),
            symbol=data['interpretation']['symbol'],
            side=data['interpretation']['side'],
            entry_price=data['interpretation'].get('entry'),
            sl_price=data['interpretation']['sl'],
            tp_prices=[tp for tp in tps if tp is not None],
            text=data.get('text', ''))

    def add_entry(self, price: Union[str, float, None]):
        """Adds entry order"""

        if price is None:

            entry = MarketOrder(self.time, self.side, name=LABEL.ENTRY)

            # this is so that we don't have to do too many shenanigans with sl_to_be
            sh = self.symbol.history(mt5.TIMEFRAME.M1, datetime_from=self.time, count=1)

            # sets execution so we don't have to look it up again later
            tick_size = self.symbol.info.trade_tick_size
            self.entry_price = Price(candle_mean(sh.iloc[0]), tick_size)
            entry.price = self.entry_price
            entry.set_execution(sh.loc[0, "time"], self.entry_price)
            return entry

        self.entry_price = Price(price, self.symbol.info.trade_tick_size)
        return LimitOrder(self.time, self.side, self.entry_price, name=LABEL.ENTRY)

    def is_price_reasonable(self, order: Order):
        """Checks that the order price is inside a 200 pips range from the
        mean of all of the other order prices."""

        orders = [self.entry, *self.get_orders()]
        all_prices = [o.price.value for o in orders if o.price is not None]
        prices = [p for p in all_prices if p is not None]

        if order.price is not None:
            avg_p = sum(prices) / len(prices)
            pips_range = Pips(150, self.symbol.info.trade_tick_size)
            if not abs(order.price.value - avg_p) < pips_range.value:
                return False

        return True

    def is_placement_reasonable(self, order: Order):
        """Checks whether the placement of the order (SL and TP) makes sense
        compared to the entry (SL MUST be before entry in a long)"""
        if order.price is None:
            return True
        if self.side * (order.price - self.entry.price) < 0:
            if order.name == LABEL.TP:
                return False
            return True
        if order.name == LABEL.SL:
            return False
        return True

    def add_order(self, order: Order):

        if order.time - self.time > timedelta(hours=24):
            log.warning(f'order is over 24 hours after the position was opened')
        if order in self.get_orders():
            log.warning(f'duplicate order')
            return None
        if not self.is_price_reasonable(order):
            raise PriceNotReasonableError(order)
        if not self.is_placement_reasonable(order):
            raise UnreasonableOrderPlacementError(order)
        self.orders.append(order)
        return order

    def get_orders(self, by="time"):
        present_orders = [o for o in self.orders if getattr(o, by, None) is not None]
        return sorted(present_orders, key=lambda x: getattr(x, by))


def main():
    with mt5.connected():
        p1 = Position(
            arrow.get(2022, 2, 17), "EURUSD", "buys", None, 1.1355, [1.1380, 1.1390], "test"
        )
        print(f"{p1=}")

        p1.tps[0].set_execution(arrow.get(2022,2,17,2), Price(1.1381, 0.00001))
        p1.tps[1].set_execution(arrow.get(2022,2,17,1), Price(1.13905, 0.00001))

        print(f'\n{p1.get_orders("execution")=}')

        data = {
            'time': arrow.now(),
            'symbol': 'GBPJPY',
            'entry': 150.5,
            'side': 'longs!!',
            'sl': '150.1'}

        print(f'\n{Position.from_dict(data)}')


if __name__ == "__main__":
    main()
