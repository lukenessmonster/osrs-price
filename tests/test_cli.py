import unittest
from io import StringIO

from osrs_price.api import Item
from osrs_price.cli import alch_analysis, all_price_rows, coins, find_items, sort_analysis, write_all_csv


ITEMS = [
    Item(4151, "Abyssal whip", True, 70, 72_000),
    Item(12002, "Occult necklace", True, 100, 30_000),
    Item(12785, "Magic shortbow (i)", True, 70, 1_440),
]


class FakeClient:
    def mapping(self):
        return ITEMS

    def latest_all(self):
        return {
            4151: {"high": 100, "highTime": 1, "low": 90, "lowTime": 2},
            12002: {"high": 200, "highTime": 3, "low": None, "lowTime": None},
        }


class CliTests(unittest.TestCase):
    def test_exact_match_wins(self):
        self.assertEqual(find_items(ITEMS, "ABYSSAL WHIP"), [ITEMS[0]])

    def test_partial_match(self):
        self.assertEqual(find_items(ITEMS, "occult"), [ITEMS[1]])

    def test_typo_is_fuzzy_matched(self):
        self.assertEqual(find_items(ITEMS, "abysal wip"), [ITEMS[0]])

    def test_coin_format(self):
        self.assertEqual(coins(1234567), "1,234,567 gp")
        self.assertEqual(coins(None), "n/a")

    def test_bulk_rows_join_prices_and_mapping(self):
        rows = all_price_rows(FakeClient())
        self.assertEqual([row["id"] for row in rows], [4151, 12002])
        self.assertEqual(rows[0]["buy_sell_profit"], -10)
        self.assertEqual(rows[0]["high_alch"], 72_000)
        self.assertIsNone(rows[1]["buy_sell_profit"])

    def test_members_only_bulk_rows(self):
        items = ITEMS + [Item(2, "Cannonball", False, 11000)]
        client = FakeClient()
        client.mapping = lambda: items
        client.latest_all = lambda: {2: {"high": 5, "highTime": 1, "low": 4, "lowTime": 2}}
        self.assertEqual(all_price_rows(client, members_only=True), [])

    def test_csv_output(self):
        destination = StringIO()
        write_all_csv(all_price_rows(FakeClient()), destination)
        output = destination.getvalue()
        self.assertIn("id,name,members,buy_limit,high_alch,high,high_time,low,low_time,buy_sell_profit", output)
        self.assertIn("4151,Abyssal whip,True,70,72000,100,1,90,2,-10", output)

    def test_alch_analysis_uses_nature_rune_from_csv(self):
        rows = [
            {"id": "561", "name": "Nature rune", "high": "150", "high_alch": "108"},
            {"id": "1", "name": "Test item", "high": "700", "high_alch": "1000"},
        ]
        analyzed, rune_price = alch_analysis(rows)
        self.assertEqual(rune_price, 150)
        self.assertEqual(analyzed[1]["net_alch_profit"], 150)
        self.assertAlmostEqual(analyzed[1]["alch_roi_pct"], 17.6471)

    def test_analysis_sort_descending_and_missing_last(self):
        rows = [
            {"name": "small", "net_alch_profit": 10},
            {"name": "missing", "net_alch_profit": None},
            {"name": "large", "net_alch_profit": 50},
        ]
        result = sort_analysis(rows, "profit", ascending=False)
        self.assertEqual([row["name"] for row in result], ["large", "small", "missing"])


if __name__ == "__main__":
    unittest.main()
