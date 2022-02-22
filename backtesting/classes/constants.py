from enum import IntEnum, auto

class SIDEFromStrError(ValueError):
    pass

class SIDE(IntEnum):
    BUY = 1
    SELL = -1

    @classmethod
    def from_str(cls, value: str):
        value = value.lower()
        if 'buy' in value or 'long' in value:
            return cls.BUY
        elif 'sell' in value or 'short' in value: 
            return cls.SELL
        raise SIDEFromStrError(f'Couldn\'t parse SIDE from string {value!r}')


class ORDERTYPE(IntEnum):
    LIMIT = auto()
    STOP = auto()
    MARKET = auto()
    SLTP = auto()


class LABEL(IntEnum):
    ENTRY = auto()
    SL = auto()
    TP = auto()
    CLOSE = auto()
    BREAKEVEN = auto()
    MOVE_SL = auto()
    SL_TO_BE = auto()
    PARTIALS = auto()