from enum import IntEnum, auto

class SIDE(IntEnum):
    BUY = 1
    SELL = -1


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


class FLAG(IntEnum):
    MESSAGE = auto()
    ORDER = auto()
    ERROR = auto()
    PARTIALS = auto()
    MOVE_SL = auto()
    UPDATE_TP = auto()
    CLOSE = auto()
    BREAKEVEN = auto()