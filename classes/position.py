from constants import SIDE
from typing import Union
import logging

class Position:

    def __init__(self,
                 time: datetime,
                 text: str,
                 symbol: str,
                 side: SIDE,
                 sl: float,
                 entry: Union[None, float] = None,
                 tp: Union[float, list] = []):

        self.log = logging.getLogger('signals_manipulation')
        self.time = time
        self.text = text
        self.symbol = mt5.Symbol(symbol)
        self.side = side
        self.orders = []

        # add entry
        self.entry = self.add_entry(entry)

        # adds stop loss order
        self.sl = self.add_order(SL(time, SIDE(-self.side), sl, text=text))

        try:  # adds tp order(s)
            for target in tp:
                self.add_order(TP(time, SIDE(-side), target, text=text))
        except TypeError:
            self.add_order(TP(time, SIDE(-side), tp, text=text))

    def __repr__(self):

        output = '{}(\n\ttime = {time},\n\tsymbol = {symbol},\n\tside = {side},\n\ttext = {text},\n\tresult = {result},\n\tentry = {entry},\n\torders = [\n'.format(
            type(self).__name__,
            time=self.time.strftime('%Y-%m-%d %H:%M:%S %z'),
            symbol=self.symbol.name,
            side=str(self.side),
            text=re.sub("\n", " ", self.text),
            result=getattr(self, 'result', None),
            entry=self.entry)
        
        for o in self.get_orders(by='time'):
            output += f'\t\t{o},\n'
            
        output = output[:-2] + '\n\t]\n)'
        
        return output
    
    def add_entry(self, entry: Union[None, float]):
        '''Adds entry order'''

        if entry is None:
            e = MarketOrder(self.time,
                            self.side,
                            name=LABEL.ENTRY,
                            text=self.text)

            # this is so that we don't have to do too many shenanigans with sl_to_be
            sh = self.symbol.history(mt5.TIMEFRAME.M1,
                                     datetime_from=self.time,
                                     count=1)

            e.exe_time = sh.loc[0, 'time']
            e.exe_price = candle_mean(sh.iloc[0])

        else:
            e = LimitOrder(self.time,
                           self.side,
                           entry,
                           name=LABEL.ENTRY,
                           text=self.text)
        return e

    def is_price_reasonable(self, order: Order):

        orders = [self.entry, *self.get_orders()]
        prices = [o.price for o in orders if o.price is not None]

        if order.ordertype == ORDERTYPE.LIMIT and order.price is None:
            raise ValueError(
                f'trying to add limit order without price {order=}')
        
        if order.name == LABEL.SL and self.side*(self.entry.price-order.price)<0: # sl is above/below entry ???
            self.log.warning(f'Trying to add an incoherent SL ({order.time=})')
            
        if order.name == LABEL.TP and self.side*(order.price-self.entry.price)<0: # tp is below/above entry ???
            self.log.warning(f'Trying to add an incoherent TP ({order.time=})')
            return False

        if order.ordertype != ORDERTYPE.MARKET and order.price is not None:

            # checks for validity (must be in reasonable range, this is 200-250 pips)
            if not (order.price * 0.985 < mean(prices) < 1.015 * order.price):
                new_price = self.fix_price(order.price)

                if not (new_price * 0.985 < mean(prices) < 1.015 * new_price):
                    return False

                order.price = new_price

        return True

    def fix_price(self, price: float):
        '''Tries to fix common mistakes (500 instead of 150.500)'''
        orders = [self.entry, *self.get_orders()]
        prices = [o.price for o in orders if o.price is not None]

        delta_array = []
        tick_size = self.symbol.info.trade_tick_size

        for og_p in prices:  # _p here stands for price

            right_p, left_p = math.modf(og_p)  # 150.500 = 150, 500
            new_p = left_p + price * tick_size  # multiplies 500 by tick size = 0.5
            #log.debug(f'{new_p=}')
            #pips100 = 1000 * tick_size
            delta_array.append((new_p, abs(new_p - og_p)))

        #log.debug(f'{delta_array=}')
        return sorted(delta_array, key=lambda x: x[1])[0][0]

    def add_order(self, order: Order):

        if self.is_price_reasonable(order):
            self.orders.append(order)
            return order
        log.error(f'Order price is not valid! {order=}')

    def get_orders(self, by='time'):
        present_orders = [
            o for o in self.orders if getattr(o, by, None) is not None
        ]
        return sorted(present_orders, key=lambda x: getattr(x, by))

    def remove_orders(self, label: LABEL):
        # removes orders with specified label
        for i, o in enumerate(self.orders):
            if o.name == label:
                self.orders.pop(i)