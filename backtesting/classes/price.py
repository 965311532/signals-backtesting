from dataclasses import dataclass
from typing import Union
from math import log10
from pandas import Series
import logging

logging.basicConfig()
log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)


def candle_mean(candle: Union[Series, dict]) -> float:
    avg = candle["low"] + (candle["high"] - candle["low"]) / 2
    return round(avg, 6)


class PriceFormatError(ValueError):
    pass


class Price:
    def __init__(self, value: Union[str, float], tick_size: float):
        self.tick_size = tick_size
        self.digits = abs(int(log10(self.tick_size)))
        self.value = value

    def __repr__(self):
        return f"%.{self.digits}f" % self.value

    def __add__(self, other: Union['Pips', 'Price']) -> float:
        result = self._value + other.value
        return float(f"%.{self.digits}f" % result)

    def __sub__(self, other: Union['Pips', 'Price']) -> float:
        result = self._value - other.value
        return float(f"%.{self.digits}f" % result)

    @property
    def value(self) -> float:
        return self._value

    @value.setter
    def value(self, num: Union[float, str]) -> None:
        subbing = Price.sub_misspells(str(num))
        inferring = self.infer_dot_position(subbing)
        try:
            self._value = float(inferring)
        except ValueError:
            raise PriceFormatError(num)

    @staticmethod
    def sub_misspells(num: str) -> str:
        errors = (":", "..")
        for e in errors:
            if e in num:
                parts = num.split(e)
                return ".".join(parts)
        return num

    def infer_dot_position(self, num: Union[str, float]) -> str:
        if "." not in str(num):
            # most prices have 6 total relevant digits
            # so we can take the 6 leftmost chars and
            # add the dot based on the known number of digits
            new_price = str(num)[: 6 - self.digits] + "." + str(num)[6 - self.digits :]
            log.warning(
                f"inferring dot position for {num} -> {new_price} ({self.tick_size})"
            )
            return new_price
        return str(num)

@dataclass
class Pips:
    _value: int
    tick_size: float

    def __post_init__(self):
        self.value = self._value * self.tick_size * 10
        self.digits = abs(int(log10(self.tick_size)))

    def __repr__(self):
        return f"%.{self.digits}f" % self.value

    def __add__(self, other: Union['Pips', Price]) -> float:
        result = self.value + other.value
        return float(f"%.{self.digits}f" % result)

    def __sub__(self, other: Union['Pips', Price]) -> float:
        result = self.value - other.value
        return float(f"%.{self.digits}f" % result)

def main():
    p1 = Price(10, 0.01)
    p2 = Price("150.55", 0.001)
    print(f"{p1=}, {p2=}")

    mean = candle_mean({'high':10, 'low':8})
    print(f'{mean=}')

    print(f'{Pips(100, 0.001)-Pips(80, 0.001)=}')
    print(f'{Price(151.11, 0.001)-Pips(27, 0.001)=}')


if __name__ == "__main__":
    main()
