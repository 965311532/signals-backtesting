import unittest
import betterMT5 as mt5
from backtesting import backtesting
from datetime import datetime

class TestMT5(unittest.TestCase):

    def setUp(self):
        self.conn = mt5.connected()
    
    def test_connection_on(self):
        with self.conn:
            self.assertIsNotNone(mt5.Symbol('EURUSD').info)

    def test_are_datetimes_eq_true(self):
        t1 = datetime(2020, 1, 5, 10)
        t2 = datetime(2020, 1, 5, 10, 0, 5)
        self.assertTrue(mt5.are_datetimes_eq(t1, t2, window=60))
    
    def test_are_datetimes_eq_false(self):
        t1 = datetime(2020, 1, 5, 10)
        t2 = datetime(2020, 1, 5, 10, 10)
        self.assertFalse(mt5.are_datetimes_eq(t1, t2, window=60))


class TestBacktest(unittest.TestCase):

    def setUp(self) -> None:
        path = 'C:/Users/Gabriele/Desktop/X/SignalBacktesting/tests/dummy_position.json'
        with mt5.connected():
            self.test = backtesting.Backtest(path, verbose=None)
            self.results = self.test.run()
    
    def test_sl_is_correct(self):
        self.assertAlmostEqual(self.test.trades[0].sl.price.value, 154.500)
    
    def test_entry_is_correct(self):
        self.assertAlmostEqual(self.test.trades[0].entry.price.value, 154.700)

    def test_result_is_correct(self):
        self.assertEqual(self.results.loc[0, 'type'], 'TP')
    
    def test_close_time_is_correct(self):
        close_time = self.results.loc[0, 'close']
        expected = datetime.strptime('2022-02-01T08:29:33+0100', '%Y-%m-%dT%H:%M:%S%z')
        self.assertTrue(mt5.are_datetimes_eq(close_time, expected, window=120))


if __name__ == "__main__":
    unittest.main()
    