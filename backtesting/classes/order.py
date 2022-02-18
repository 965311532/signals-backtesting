from constants import SIDE, ORDERTYPE, LABEL

class Order:

    def __init__(self,
                 time: datetime,
                 side: SIDE,
                 ordertype: ORDERTYPE,
                 price: Union[float, str] = None,
                 name: LABEL = None,
                 text: str = None):

        self.time = time  # time of placing the order
        self.side = side  # buy, sell
        self.ordertype = ordertype  # market, limit
        self.price = price
        self.name = name  # name of the order. Ex: TARGET.SL
        self.text = text  # text that generated the order

    def __repr__(self):
        carr = "\n"
        attrs = "side,ordertype,price,name,text,exe_time,exe_price".split(',')
        return '{}(\n\t\t\ttime = {}\n\t\t\t{}\n\t\t\t)'.format(
            type(self).__name__,
            self.time.strftime('%Y-%m-%d %H:%M:%S %z'),
            ',\n\t\t\t'.join([f'{x} = {re.sub(carr, " ", str(getattr(self, x, None))[:30])}' for x in attrs]))

    @property
    def price(self):
        return self._price

    @price.setter
    def price(self, value):
        '''Adds support for spelling errors, like 1:45345 or 145..890'''
        if value is None:
            self._price = None
        else:
            self._price = float(re.sub(r':|\.{1,2}', '.', str(value)))


class MarketOrder(Order):

    def __init__(self, time: datetime, side: SIDE, **kwargs):
        super().__init__(time, side, ORDERTYPE.MARKET, **kwargs)


class LimitOrder(Order):

    def __init__(self, time: datetime, side: SIDE, price: float, **kwargs):
        super().__init__(time, side, ORDERTYPE.LIMIT, price=price, **kwargs)


class StopOrder(Order):

    def __init__(self, time: datetime, side: SIDE, price: float, **kwargs):
        super().__init__(time, side, ORDERTYPE.STOP, price=price, **kwargs)


class SL(StopOrder):

    def __init__(self, time: datetime, side: SIDE, price: float, **kwargs):
        super().__init__(time, side, price=price, name=LABEL.SL, **kwargs)


class TP(LimitOrder):

    def __init__(self, time: datetime, side: SIDE, price: float, **kwargs):
        super().__init__(time, side, price=price, name=LABEL.TP, **kwargs)