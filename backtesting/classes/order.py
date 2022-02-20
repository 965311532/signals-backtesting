from constants import SIDE, ORDERTYPE, LABEL
from typing import Union, Optional
from price import Price
from dataclasses import dataclass, field
import arrow
import logging

logging.basicConfig()
log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)


class ExecutionAlreadySetError(AttributeError):
    pass


@dataclass
class Execution:
    time: arrow.Arrow
    price: Price

    def __lt__(self, other: 'Execution'):
        if not isinstance(other, Execution):
            log.warning(' < operation is only supported with another Execution instance')
        return self.time < other.time


@dataclass
class Order:
    time: arrow.Arrow
    side: SIDE
    ordertype: ORDERTYPE
    price: Union[None, Price] = None
    name: Union[None, LABEL] = None
    execution: Union[None, Execution] = None

    def set_execution(self, time: arrow.Arrow, price: Price):
        if self.execution is not None:
            raise ExecutionAlreadySetError(self)
        self.execution = Execution(time, price)


class MarketOrder(Order):
    def __init__(self, time: arrow.Arrow, side: SIDE, **kwargs):
        super().__init__(time, side, ORDERTYPE.MARKET, **kwargs)


class LimitOrder(Order):
    def __init__(self, time: arrow.Arrow, side: SIDE, price: Price, **kwargs):
        super().__init__(time, side, ORDERTYPE.LIMIT, price=price, **kwargs)


class StopOrder(Order):
    def __init__(self, time: arrow.Arrow, side: SIDE, price: Price, **kwargs):
        super().__init__(time, side, ORDERTYPE.STOP, price=price, **kwargs)


class SL(StopOrder):
    def __init__(self, time: arrow.Arrow, side: SIDE, price: Price, **kwargs):
        super().__init__(time, side, price=price, name=LABEL.SL, **kwargs)


class TP(LimitOrder):
    def __init__(self, time: arrow.Arrow, side: SIDE, price: Price, **kwargs):
        super().__init__(time, side, price=price, name=LABEL.TP, **kwargs)


def main():
    sl = SL(arrow.now(), SIDE.BUY, Price(150.50, 0.001))
    print(sl)
    sl.set_execution(arrow.now(), Price(150.6, 0.001))
    print(sl)


if __name__ == "__main__":
    main()
