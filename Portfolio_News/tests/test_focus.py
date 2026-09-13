"""Unit tests for KB Focus / Hold (no live BCS)."""



from __future__ import annotations



import unittest



from sqlalchemy import create_engine

from sqlalchemy.orm import sessionmaker



from portfolio_news.db import Base, TickerFocus

from portfolio_news.focus import (

    list_focus_tickers,

    notify_allowed,

    replace_focus,

    set_focus,

)





class FocusStoreTests(unittest.TestCase):

    def setUp(self):

        engine = create_engine("sqlite:///:memory:")

        Base.metadata.create_all(engine)

        self.Session = sessionmaker(bind=engine, future=True)



    def test_default_hold_and_set_focus(self):

        with self.Session() as s:

            self.assertEqual(list_focus_tickers(s), [])

            self.assertEqual(set_focus(s, "sber", focus=True), "focus")

            self.assertEqual(list_focus_tickers(s), ["SBER"])

            self.assertEqual(set_focus(s, "SBER", focus=False), "hold")

            self.assertEqual(list_focus_tickers(s), [])



    def test_set_focus_exclusive_one_only(self):
        with self.Session() as s:
            self.assertEqual(set_focus(s, "SBER", focus=True), "focus")
            self.assertEqual(set_focus(s, "GAZP", focus=True), "focus")
            self.assertEqual(list_focus_tickers(s), ["GAZP"])
            self.assertEqual(set_focus(s, "GAZP", focus=False), "hold")
            self.assertEqual(list_focus_tickers(s), [])

    def test_replace_focus(self):
        with self.Session() as s:
            replace_focus(s, ["GAZP", "sber", "SBER", ""])
            self.assertEqual(list_focus_tickers(s), ["GAZP", "SBER"])
            replace_focus(s, [])
            self.assertEqual(list_focus_tickers(s), [])

    def test_notify_allowed(self):

        self.assertTrue(notify_allowed("SBER", None))

        self.assertTrue(notify_allowed("SBER", set()))

        self.assertTrue(notify_allowed("SBER", {"SBER", "GAZP"}))

        self.assertFalse(notify_allowed("LKOH", {"SBER"}))





if __name__ == "__main__":

    unittest.main()


