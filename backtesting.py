import logging
from rich.logging import RichHandler
logging.basicConfig(format="[u]%(funcName)s[/](): %(message)s",
                    datefmt="[%x %X]",
                    level=logging.DEBUG,
                    force=True,
                    handlers=[RichHandler(rich_tracebacks=True, markup=True)])

import os, sys
dir2 = os.path.abspath('')
dir1 = os.path.dirname(dir2)
if not dir1 in sys.path: sys.path.append(dir1)

import re
import pytz
import time
import math
import json
import numpy as np
# should change these and use a config manager
from secrets import *
from betterMT5 import core as mt5
from typing import Union
from aliases import aliases
from flatten_json import flatten
from datetime import datetime, timedelta
from statistics import mean, StatisticsError
import pandas as pd

mt5_log = logging.getLogger('mt5')
mt5_log.setLevel(logging.WARNING)

conn = mt5.connected(path=r'../MoneyBox/bin/terminal64.exe',
                     portable=True,
                     server=server_mt5,
                     login=login_mt5,
                     password=password_mt5,
                     logger=mt5_log,
                     enable_real_trading=True,
                     raise_on_errors=True)

L1_TF = mt5.TIMEFRAME.M1


def clean_json(json_path, tz_localize=pytz.timezone('Europe/Rome')):
    '''Takes in a messy json and cleans it to use it for backtesting'''
    
    with open(json_path, 'r', encoding="utf8") as f:
        data = json.loads(f.read())
    
    # use flatten module to unnest values
    raw_data = [flatten(d) for d in data['messages']]
    
    # it's easier to manipulate with pandas
    df = pd.DataFrame(raw_data)
    
    # merges different nesting-level texts
    text_cols = df.columns.intersection([f'text_{i}' for i in range(0,100)] +
                                        [f'text_{i}_text' for i in range(0,100)])
    
    df['agg_text'] = df.text.fillna('').str.cat(df[text_cols].fillna(''), sep=' ').str.strip()
    
    # keeps these cols and cleans the rest
    necessary_cols=['id', 'date', 'agg_text']
    clean_df = df[necessary_cols].copy()
    
    # drops empty rows
    clean_df.drop(clean_df[clean_df['agg_text'].str.strip()==""].index, inplace=True)
    clean_df.rename(columns={'agg_text': 'text'}, inplace=True)
    
    # corrects timestamps
    clean_df['time'] = pd.to_datetime(df['date']).dt.tz_localize(tz_localize)
    
    # resets index
    clean_df.reset_index(inplace=True, drop=True)
    
    # the python dict is a bit faster to iterate over
    return clean_df.to_dict(orient='index')

def candle_mean(candle):
    avg = candle['low'] + (candle['high'] - candle['low']) / 2
    return round(avg, 5)

def has_candle_hit(order: Order, h: float, l: float, spread=4e-5):
    '''Determines whether a candle has hit a certain price. You need high and low 
    because those are the extremes of the range. You also need to now
    what kind of order it is and which side (buy, sell) you're acting on.
    Supported categories are: limit, stop
    Spread works by multiplying the 'spread' times the last level value'''

    ordertype = order.ordertype
    side = order.side
    price = order.price
    spread = spread * price

    if ordertype == ORDERTYPE.LIMIT:

        # no spread on limits, it will be checked
        # by the ticks check anyway

        if side == SIDE.BUY:
            if l + spread * 0 <= price:
                return True
        else:
            if h - spread * 0 >= price:
                return True

    elif ordertype == ORDERTYPE.STOP:

        # on stops we need spreads in order
        # to make sure that sl aren't actually hit

        if side == SIDE.BUY:
            if h + spread >= price:
                return True
        else:
            if l - spread <= price:
                return True

    return False

def find_hit(order: Order, position: Position):

    # gets rates stored in position obj
    l1 = position.rates

    if order.price is None:
        if order.ordertype == ORDERTYPE.MARKET:
            try:
                return l1[l1['time'] > order.time].iloc[0]
            except IndexError:
                return None
        raise ValueError(
            f'trying to find a hit on a limit with no price, {order=}')

    l1['hit'] = l1.apply(lambda x: has_candle_hit(order, x['high'], x['low']),
                         axis=1)

    # this are the candles where there is a hit, after the order
    hits = l1[l1['hit'] & (l1['time'] > order.time)]

    try:
        return hits.iloc[0]
    except IndexError:
        return None

class Backtest():

    def __init__(self, positions):

        self.log = logging.getLogger('backtest')
        self.positions = positions

    def get_pos_eop(self, time: datetime, end_of_period=0, end_of_day='18:30'):
        '''Gets position end of period, where 0 means "same day" and 1, 2, 3
        4, 5, 6, 7 mean Monday, Tuesday, Wednesday, Thursday, Friday,
        Saturday, Sunday of the "time" week, respectively'''

        hour_end, minute_end = end_of_day.split(':')
        day_end = time.replace(hour=int(hour_end), minute=int(minute_end))

        # end of week
        start_of_week = day_end - timedelta(days=day_end.weekday())
        weekly = start_of_week + timedelta(days=end_of_period - 1)

        # set end of period that the backtester will look at
        return day_end if end_of_period == 0 else weekly

    def position_to_dict(self, p: Position):

        sl_pips = None
        if getattr(p.entry, 'exe_price', None) is not None:
            sl_pips = (abs(p.entry.exe_price - p.sl.price) /
                       p.symbol.info.trade_tick_size) / 10

        return dict(sig_time=p.time,
                    symbol=p.symbol.name,
                    side=p.side.name,
                    sl_pips=sl_pips,
                    result=getattr(p, 'result', None),
                    result_type=getattr(p, 'result_type',None))

    def run(self):

        for i, p in enumerate(self.positions):

            # get test end of period
            eop = self.get_pos_eop(p.time)

            # signal was too late, skip it
            if p.time >= eop:
                self.log.debug(f'signal {i} was too late, skip it')
                continue
                
            if p.sl is None:
                self.log.warning(f'signal {i} sl is None')
                continue

            # 1. get L1_TF rates from starting time to eop
            # 2. check for entry hit
            # 3. save L1_TF R data
            # 4. if no entry, continue
            # 5. check for all other orders hit
            # 6. save data

            p.rates = p.symbol.history(L1_TF,
                                       datetime_from=p.time,
                                       datetime_to=eop,
                                       include_last=False)

            entry_candle = find_hit(order=p.entry, position=p)
            if entry_candle is None:
                continue

            p.entry.exe_time = entry_candle['time']
            # this could allow for a lot of skewness
            p.entry.exe_price = candle_mean(entry_candle)
            #self.log.debug(f'{p.entry=}')
            
            sl_delta = abs(p.entry.exe_price - p.sl.price)
            p.rates['Rmin'] = (
                (p.rates['low'] if p.side == SIDE.BUY else p.rates['high']) -
                p.entry.exe_price) / sl_delta
            p.rates['Rmax'] = (
                (p.rates['low'] if p.side == SIDE.SELL else p.rates['high']) -
                p.entry.exe_price) / sl_delta

            for o in p.get_orders():
                # adjust order time (they must be after entry)
                if o.time < p.entry.exe_time:
                    o.time = p.entry.exe_time
                o_candle = find_hit(order=o, position=p)
                if o_candle is None:
                    continue
                o.exe_time = o_candle['time']
                o.exe_price = (candle_mean(o_candle)
                               if o.ordertype == ORDERTYPE.MARKET 
                               else o.price)

            # gets first executed order and finds resulting R
            events = p.get_orders(by='exe_time')
            p.result = p.rates['Rmin'].iloc[-1]
            p.result_type = "EOP"
            if len(events) > 0:
                p.result = p.side*(events[0].exe_price - p.entry.exe_price) / sl_delta
                p.result_type = events[0].name.name

        return pd.DataFrame([self.position_to_dict(p) for p in self.positions])