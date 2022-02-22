from functools import partial
import logging
from rich.logging import RichHandler
from rich.traceback import install

#install(show_locals=True, max_frames=10)
from rich.console import Console

console = Console()

logging.basicConfig(
    format="[u]%(funcName)s[/](): %(message)s",
    datefmt="[%x %X]",
    level=logging.DEBUG,
    force=True,
    handlers=[RichHandler(rich_tracebacks=True, markup=True)],
)

log = logging.getLogger(__name__)

import pandas as pd
import betterMT5 as mt5
from . import preprocessing
from .classes.order import Order, MarketOrder, LimitOrder, TP, StopOrder
from .classes.position import (
    Position,
    UnreasonableOrderPlacementError,
    PriceNotReasonableError,
)
from .classes.constants import SIDE, LABEL, ORDERTYPE
from .classes.price import Price, Pips, candle_mean
from typing import Union, List
import arrow
from datetime import timedelta


def has_candle_hit(order: Order, h: float, l: float, spread=None):
    """Determines whether a candle has hit a certain price. You need high and low
    because those are the extremes of the range. You also need to now
    what kind of order it is and which side (buy, sell) you're acting on.
    Supported categories are: limit, stop"""

    ordertype = order.ordertype
    side = order.side
    price = order.price
    # Normalize high and low
    h = Price(h, price.tick_size)
    l = Price(l, price.tick_size)

    if spread is None:
        spread = Pips(1, price.tick_size)

    if ordertype == ORDERTYPE.LIMIT:

        if side == SIDE.BUY:
            if l - price <= 0:
                return True
        else:
            if h - price >= 0:
                return True

    elif ordertype == ORDERTYPE.STOP:

        # on stops we need spreads in order
        # to make sure that sl aren't actually hit

        if side == SIDE.BUY:
            if Price(h - spread, price.tick_size) - price >= 0:
                return True
        else:
            if Price(l + spread, price.tick_size) - price <= 0:
                return True

    return False


def find_hit(order: Order, position: Position):
    # gets rates stored in position obj
    l1 = position.rates

    if order.price is None:
        if order.ordertype == ORDERTYPE.MARKET:
            try:
                return l1[l1["time"] > order.time.datetime].iloc[0]
            except IndexError:
                return None
        raise ValueError(f"trying to find a hit on a limit with no price, {order=}")

    l1["hit"] = l1.apply(lambda x: has_candle_hit(order, x["high"], x["low"]), axis=1)

    # this are the candles where there is a hit, after the order
    hits = l1[l1["hit"] & (l1["time"] > order.time.datetime)]

    try:
        return hits.iloc[0]
    except IndexError:
        return None


def get_pos_eop(time, end_of_period=0, end_of_day="18:30"):
    """Gets position end of period, where 0 means "same day" and 1, 2, 3
    4, 5, 6, 7 mean Monday, Tuesday, Wednesday, Thursday, Friday,
    Saturday, Sunday of the "time" week, respectively"""

    hour_end, minute_end = end_of_day.split(":")
    day_end = time.replace(
        hour=int(hour_end), minute=int(minute_end), second=0, microsecond=0
    )

    # end of week
    start_of_week = day_end - timedelta(days=day_end.weekday())
    weekly = start_of_week + timedelta(days=end_of_period - 1)

    # set end of period that the backtester will look at
    return day_end if end_of_period == 0 else weekly


def make_positions(prep_data: List[dict]):
    """Gets positions data for all messages, including tp and sl updates
    from following ones and close signals as well. (Includes anything
    the interpreter module is able to parse)"""

    positions = []

    for data in prep_data:
        try:
            p = positions[-1] if len(positions) > 0 else None
            tick_size = p.symbol.info.trade_tick_size if p else None
            flag = data["interpretation"]["flag"]

            if flag == "POSITION":
                positions.append(Position.from_dict(data))

            if p is None:
                continue

            if flag == "UPDATE_TP":
                if isinstance(data["interpretation"]["tp"], list):
                    for tp in data["interpretation"]["tp"]:
                        p.add_order(
                            TP(data["time"], SIDE(-p.side), Price(tp, tick_size))
                        )
                else:
                    p.add_order(
                        TP(
                            data["time"],
                            SIDE(-p.side),
                            Price(data["interpretation"]["tp"], tick_size),
                        )
                    )

            elif flag == "UPDATE_PARTIALS":
                p.add_order(
                    MarketOrder(data["time"], SIDE(-p.side), name=LABEL.PARTIALS)
                )

            elif flag == "UPDATE_BREAKEVEN":
                p.add_order(
                    StopOrder(
                        data["time"], SIDE(-p.side), p.entry.price, name=LABEL.SL_TO_BE
                    )
                )

            elif flag == "UPDATE_CLOSE":
                p.add_order(MarketOrder(data["time"], SIDE(-p.side), name=LABEL.CLOSE))

        except (UnreasonableOrderPlacementError, PriceNotReasonableError) as e:
            log.error(e)
            continue

    return positions


class Backtest:
    def __init__(self, path: str, verbose=False):

        # SETS LOGGING LEVELS
        modules = [
            "hermes.core",
            "backtesting.preprocessing",
            "backtesting.classes.position",
            "backtesting.classes.price",
            __name__
        ]
        for mod in modules:
            if verbose is None:
                logging.getLogger(mod).setLevel(logging.CRITICAL)
            elif verbose:
                logging.getLogger(mod).setLevel(logging.DEBUG)
            elif not verbose:
                logging.getLogger(mod).setLevel(logging.INFO)

        self.trades = self.prepare(path)

    def prepare(self, path: str):
        relevant_signals = preprocessing.preprocess(path)
        return make_positions(relevant_signals)

    def run(self, matrix_tf=mt5.TIMEFRAME.M1):

        trades = self.trades[:]
        for i, p in enumerate(trades):

            # get test end of period
            eop = get_pos_eop(p.time)

            # signal was too late, skip it
            if p.time >= eop:
                log.info(f"signal {i} was too late, skip it")
                continue

            if p.sl is None:
                log.warning(f"signal {i} sl is None")
                continue

            # 1. get matrix_tf rates from starting time to eop
            # 2. check for entry hit
            # 3. save matrix_tf R data
            # 4. if no entry, continue
            # 5. check for all other orders hit
            # 6. save data

            try:
                p.rates = p.symbol.history(
                    matrix_tf, datetime_from=p.time, datetime_to=eop, include_last=False
                )["time open high low close".split(" ")]
            except mt5.UnexpectedValueError as e:
                if isinstance(e.diff, int) and e.diff <= 3:
                    p.rates = e.rates
                else:
                    log.error(e)
                    continue

            tick_size = p.symbol.info.trade_tick_size

            if p.entry.execution is None:
                entry_candle = find_hit(order=p.entry, position=p)
                if entry_candle is None:
                    log.info(f"No entry on position {i}")
                    continue
                p.entry.set_execution(
                    entry_candle["time"],
                    Price(candle_mean(entry_candle), tick_size),
                )

            p.sl_delta = abs(p.entry.execution.price - p.sl.price)

            for o in p.get_orders():
                # adjust order time (they must be after entry)
                if o.time < p.entry.execution.time:
                    o.time = p.entry.execution.time
                o_candle = find_hit(order=o, position=p)
                if o_candle is None:
                    continue
                o.set_execution(
                    o_candle["time"],
                    Price(candle_mean(o_candle), tick_size)
                    if o.ordertype == ORDERTYPE.MARKET
                    else o.price,
                )

        self.run_results = [tr for tr in trades if tr.entry.execution]
        return self.make_results(self.run_results)

    @staticmethod
    def _determine_position_result(p: Position, partials=[1]):
        events = p.get_orders(by="execution")
        
        if len(events) == 0:
            last_candle = p.rates.iloc[-1]
            r = p.side * (candle_mean(last_candle) - p.entry.execution.price.value) / p.sl_delta
            return (last_candle.time, r, 'EOP')
        
        result = 0
        for i, partial in enumerate(partials):
            if i == 0:
                result_type = events[i].name.name
            if i == len(partials) - 1:
                close = events[i].execution.time

            r = p.side * (events[i].execution.price - p.entry.execution.price) / p.sl_delta
            
            # Closing events
            if events[i].name in [LABEL.SL, LABEL.SL_TO_BE]:
                # if it's the first event record the loss,
                # otherwise i'm assuming the second losing 
                # partial is always at breakeven
                if i == 0:
                    result = r
                break
            else:
                result += r * partial

        return (close, result, result_type)

    def make_results(self, given=None, partials=[1]):
        '''Returns a dataframe containing data from the test run provided'''
        if given is None:
            given = self.run_results

        results = list()
        for p in given:
            res = Backtest._determine_position_result(p, partials=partials)
            results.append(
                dict(
                    open=p.time,
                    close=res[0],
                    symbol=p.symbol.name,
                    sl_pips=p.sl_delta/p.symbol.info.trade_tick_size/10,
                    result=res[1],
                    type=res[2]
                    )
                )

        return pd.DataFrame(results)


def main():
    with mt5.connected():
        test = Backtest("../chats/results_daniel.json", verbose=None)
        res = test.run()
        console.print(res)


if __name__ == "__main__":
    main()
