from __future__ import annotations

import unittest

from portfolio_news.bcs_client import Holding, classify_asset_class, _row_to_holding


class ClassifyAssetClassTests(unittest.TestCase):
    def test_cash(self):
        self.assertEqual(classify_asset_class(ticker='RUB'), 'cash')

    def test_bond_board(self):
        self.assertEqual(classify_asset_class(ticker='RU000A107RZ0', class_code='TQCB'), 'bond')
        self.assertEqual(classify_asset_class(ticker='X', isin='RU000A10EF52'), 'bond')
        self.assertEqual(classify_asset_class(name='Самолет серия БО-П13', class_code='TQBR'), 'bond')

    def test_fund(self):
        self.assertEqual(classify_asset_class(ticker='FXGD', class_code='TQTF'), 'fund')
        self.assertEqual(classify_asset_class(ticker='BCSR', name='BPIF BCS'), 'fund')
        self.assertEqual(classify_asset_class(ticker='BCSR', class_code='TQBR', db_kind='fund'), 'fund')
        self.assertEqual(classify_asset_class(ticker='GOLD', class_code='TQBR', db_kind='fund'), 'fund')
        # short name without «фонд» / «БПИФ»
        self.assertEqual(
            classify_asset_class(ticker='BCSR', name='Индекс Мосбиржи', class_code='TQBR'),
            'fund',
        )

    def test_stock(self):
        self.assertEqual(classify_asset_class(ticker='SBER', class_code='TQBR'), 'stock')
        self.assertEqual(classify_asset_class(ticker='SBER', isin='RU0009029540', class_code='TQBR'), 'stock')

    def test_row_to_holding(self):
        h = _row_to_holding({'ticker': 'RU000A107RZ0', 'classCode': 'TQCB', 'quantity': 1, 'marketValue': 100})
        self.assertIsInstance(h, Holding)
        self.assertEqual(h.asset_class, 'bond')


if __name__ == '__main__':
    unittest.main()
